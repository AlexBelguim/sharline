//! Local player: input, camera, recoil, client-side hit detection (shot claims) and host feedback.
//! Works the same for the host's own player and for a remote client.

use crate::AppState;
use crate::config::{Cli, CurrentLevel, Data, level_by_name};
use crate::net::{NetRequest, Role, Session};
use crate::radial::{HealMenu, HealOption, REGION_ORDER, Radial, heal_options};
use crate::render::hit_fx::ClaimedHit;
use crate::render::{ViewmodelRig, ads_zoom, camera_fov, own_tracer_start, viewmodel_lens};
use crate::scope_zoom::ScopeZoom;
use crate::screens::{EscPress, EscSystems, Screens};
use crate::settings::{
    Action, BindInput, HoldToggle, Keybinds, RadialPick, RadialTuning, Settings, SettingsData, rad_per_count,
};
use crate::shared::LocalShot;
use bevy::ecs::system::SystemParam;
use bevy::input::mouse::{AccumulatedMouseMotion, AccumulatedMouseScroll};
use bevy::prelude::*;
use bevy::render::view::screenshot::{Screenshot, save_to_disk};
use bevy::window::WindowFocused;
use lightyear::prelude::client::input::InputSystems;
use lightyear::prelude::input::native::{ActionState, InputMarker};
use lightyear::prelude::*;
use std::sync::Arc;
use vetf_net::*;
use vetf_sim::data::AttachmentCategory;
use vetf_sim::hitbox::{self, HitClaim, Pose};
use vetf_sim::input::{Buttons, MAX_PITCH};
use vetf_sim::items::{ItemScope, encode_pick};
use vetf_sim::recoil::ViewRecoil;
use vetf_sim::weapon::{WeaponLoadout, shot_direction, shot_seed};

pub struct ClientPlugin;

impl Plugin for ClientPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<LocalControl>()
            .init_resource::<Feedback>()
            .add_observer(on_match_state)
            .add_systems(
                RunFixedMainLoop,
                (crate::scope_zoom::update, gather_input)
                    .chain()
                    .in_set(RunFixedMainLoopSystems::BeforeFixedMainLoop)
                    .run_if(in_state(AppState::InGame)),
            )
            .add_systems(FixedPreUpdate, write_inputs.in_set(InputSystems::WriteClientInputs))
            .add_systems(FixedPostUpdate, record_smoothing)
            .add_systems(Update, wait_for_player.run_if(in_state(AppState::Connecting)))
            .add_systems(OnEnter(AppState::InGame), reset_control)
            .add_systems(
                Update,
                (
                    block_mouse_on_focus,
                    // The base under the screen stack: it only gets Esc while no screen is open.
                    esc_in_match.in_set(EscSystems::Base),
                    fire_claims,
                    recoil_recovery,
                    receive_feedback,
                    tick_feedback,
                )
                    .chain()
                    .run_if(in_state(AppState::InGame)),
            )
            .add_systems(Update, automation);
    }
}

/// The local player's controls. Look angles live here (client-authoritative) and go out with each input.
#[derive(Resource)]
pub struct LocalControl {
    pub yaw: f32,
    pub pitch: f32,
    pub movement: Vec2,
    pub held: u16,
    /// Presses since the last fixed tick, so a short tap is never lost between ticks.
    pub latched: u16,
    /// Sprint, crouch and aim while they are set to TOGGLE.
    pub toggles: Toggles,
    pub recoil: ViewRecoil,
    pub paused: bool,
    /// Short visual camera kick (degrees), decays quickly.
    pub punch: f32,
    /// Seconds reload has been held (`None` when it is up).
    pub reload_held_s: Option<f32>,
    /// The magazine radial, while reload is held long enough.
    pub reload_radial: Option<Radial>,
    /// A magazine picked on the radial (1..=6), sent with the next tick's input.
    pub reload_pick: u8,
    /// The heal ring, while open (the Heal key, B by default).
    pub heal: Option<HealMenu>,
    /// An item picked on the heal ring (kit slot 1..=8, region 0..=4), sent with the next tick's input.
    pub item_pick: (u8, u8),
    /// After a ring menu closes, the mouse buttons stay off until released (the click that picked must
    /// not fire the gun or cancel the item).
    pub mouse_block: bool,
    /// The variable scope in hand and its live zoom (`scope_zoom`).
    pub scope: ScopeZoom,
}

impl Default for LocalControl {
    fn default() -> Self {
        Self {
            yaw: 0.0,
            pitch: 0.0,
            movement: Vec2::ZERO,
            held: 0,
            latched: 0,
            toggles: Toggles::default(),
            recoil: ViewRecoil::default(),
            paused: false,
            punch: 0.0,
            reload_held_s: None,
            reload_radial: None,
            reload_pick: 0,
            heal: None,
            item_pick: (0, 0),
            mouse_block: false,
            scope: ScopeZoom::default(),
        }
    }
}

/// Things the HUD shows briefly.
#[derive(Resource, Default)]
pub struct Feedback {
    /// New hit confirms from the host; `render::hit_fx` turns them into markers on the player hit.
    pub hits: Vec<HitConfirm>,
    /// Our new shot claims (where on the player our shot hit); `render::hit_fx` keeps them for the confirms.
    pub claims: Vec<ClaimedHit>,
    /// (world position the damage came from, seconds left)
    pub damage: Vec<(Vec3, f32)>,
    /// The kill feed's recent lines, oldest first.
    pub kills: Vec<FeedEntry>,
    /// The ASSIST popup's seconds left (0: hidden); an assist of yours sets it.
    pub assist_s: f32,
    /// New tracers: (from, to, seconds since the shot, own shot); `render::tracer_fx` flies them.
    pub tracers: Vec<(Vec3, Vec3, f32, bool)>,
    /// New bullet impacts on the level (point, surface normal); `impacts` turns them into marks and debris.
    pub impacts: Vec<(Vec3, Vec3)>,
}

/// One kill feed line: "KILLER + HELPER +N > VICTIM", or for a death no player caused,
/// "HELPER + FALL > VICTIM" (`hud::feed_text` writes it).
#[derive(Debug, Clone, PartialEq)]
pub struct FeedEntry {
    pub killer: Option<String>,
    /// The players credited with an assist, the most damage first.
    pub helpers: Vec<String>,
    pub cause: DeathCause,
    pub victim: String,
    pub headshot: bool,
    /// Seconds left on screen.
    pub left_s: f32,
}

impl FeedEntry {
    /// A line with no helpers and no cause (the HUD demo).
    pub fn kill(killer: &str, victim: &str, headshot: bool) -> Self {
        FeedEntry {
            killer: Some(killer.into()),
            helpers: Vec::new(),
            cause: DeathCause::Shot,
            victim: victim.into(),
            headshot,
            left_s: FEED_LINE_S,
        }
    }
}

/// How long a kill feed line stays.
pub const FEED_LINE_S: f32 = 6.0;
/// How long the ASSIST popup stays (short, like a kill confirm).
pub const ASSIST_POPUP_S: f32 = 1.1;

/// Visual smoothing of the predicted position between fixed ticks.
#[derive(Component, Default)]
pub struct Smoothed {
    pub prev: Vec3,
    pub curr: Vec3,
}

fn on_match_state(
    trigger: On<Add, MatchState>,
    states: Query<&MatchState>,
    level: Option<Res<CurrentLevel>>,
    mut commands: Commands,
) {
    let Ok(m) = states.get(trigger.entity) else { return };
    let have = level.is_some_and(|l| l.name.eq_ignore_ascii_case(&m.map));
    if !have {
        commands.insert_resource(CurrentLevel(Arc::new(level_by_name(&m.map))));
    }
}

fn wait_for_player(
    me: Query<(), (With<PlayerId>, With<Controlled>)>,
    level: Option<Res<CurrentLevel>>,
    mut next: ResMut<NextState<AppState>>,
    mut waited: Local<f32>,
    time: Res<Time>,
    mut requests: MessageWriter<NetRequest>,
) {
    *waited += time.delta_secs();
    if level.is_some() && !me.is_empty() {
        *waited = 0.0;
        next.set(AppState::InGame);
    } else if *waited > 15.0 {
        *waited = 0.0;
        requests.write(NetRequest::Leave { reason: Some("timed out waiting for the host".into()) });
    }
}

fn reset_control(mut control: ResMut<LocalControl>, me: Query<&PlayerLook, With<Controlled>>, cli: Res<Cli>) {
    let look = me.iter().next().copied().unwrap_or_default();
    let yaw = cli.yaw.map_or(look.yaw, f32::to_radians);
    // A mouse button still held from the menu click that started the match (GUN RANGE, CREATE LOBBY) must
    // not fire the first shot: buttons stay off until released.
    *control = LocalControl { yaw, pitch: look.pitch, mouse_block: true, ..default() };
}

/// The click that focuses the window again must not fire or aim: mouse buttons stay off until released.
fn block_mouse_on_focus(mut focus: MessageReader<WindowFocused>, mut control: ResMut<LocalControl>) {
    if focus.read().any(|f| f.focused) {
        control.mouse_block = true;
    }
}

/// Esc in the match, when no hub screen is open (`screens::EscSystems::Base`): it closes an open ring menu,
/// else opens the ESC menu (`esc_menu.rs`). The match keeps running; the cursor follows the screen stack
/// (`screens::apply_cursor`).
fn esc_in_match(mut esc: ResMut<EscPress>, mut control: ResMut<LocalControl>, mut screens: ResMut<Screens>) {
    if esc.take() {
        // Esc closes an open ring menu first (and forgets a reload hold, so it does not reopen).
        let heal = control.heal.take().is_some();
        let radial = control.reload_radial.take().is_some();
        if heal || radial {
            control.reload_held_s = None;
            control.mouse_block = true;
            return;
        }
        screens.push(crate::screens::Screen::Esc);
    }
}

/// The input devices as the key map reads them ([`BindInput`]). Screenshot and demo runs ignore the desktop's
/// wheel here (`demo_mode` already clears their keys and mouse buttons).
#[derive(SystemParam)]
pub struct BindDevices<'w, 's> {
    keys: Res<'w, ButtonInput<KeyCode>>,
    mouse: Res<'w, ButtonInput<MouseButton>>,
    scroll: Res<'w, AccumulatedMouseScroll>,
    cli: Res<'w, Cli>,
    wheel_prev: Local<'s, f32>,
}

impl BindDevices<'_, '_> {
    /// This frame's input. Read it once per frame: it remembers the wheel for the next frame's presses.
    pub fn read(&mut self) -> BindInput<'_> {
        let wheel = if self.cli.ignores_desktop_input() { 0.0 } else { self.scroll.delta.y };
        let wheel_prev = std::mem::replace(&mut *self.wheel_prev, wheel);
        BindInput { keys: &self.keys, mouse: &self.mouse, wheel, wheel_prev, taken: Vec::new() }
    }
}

/// Sprint, crouch and aim while set to TOGGLE: each stays on until pressed again (see [`hold_buttons`]).
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Toggles {
    pub sprint: bool,
    pub crouch: bool,
    pub ads: bool,
    /// Forward input on the last frame (a toggled sprint ends when it stops).
    pub forward: bool,
}

/// A button in HOLD or TOGGLE mode: HOLD follows the key, TOGGLE flips `on` with each press.
pub fn hold_or_toggle(mode: HoldToggle, on: &mut bool, held: bool, pressed: bool) -> bool {
    match mode {
        HoldToggle::Hold => {
            *on = false;
            held
        }
        HoldToggle::Toggle => {
            if pressed {
                *on = !*on;
            }
            *on
        }
    }
}

/// This frame's sprint, crouch, walk and aim keys as (held, just pressed), and whether there is forward input.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct HoldKeys {
    pub sprint: (bool, bool),
    pub crouch: (bool, bool),
    pub ads: (bool, bool),
    pub walk: bool,
    pub forward: bool,
    /// An item is in hand, or picked on the heal ring and about to be: sprinting would cancel it, so
    /// auto-sprint waits (the Sprint key still sprints, and cancels the item on purpose).
    pub item: bool,
}

/// Sprint, crouch and aim for this frame, with sprint and crouch in `stance` mode (HUD tab) and aim in `aim`
/// mode (Mouse & Aim tab). A toggled sprint ends when forward input stops or crouch is pressed (a slide);
/// pressing sprint stands a toggled crouch up. Auto-sprint (the default) sprints on any forward input unless
/// walk is held or an item is in hand; the sim keeps the angle, stance and leg rules.
///
/// Firing, aiming and mag checks never end a sprint (user direction 2026-10-08): the sim brings the gun up from
/// the sprint pose in the gun's `sprint_to_fire_s` while the player keeps their speed.
pub fn hold_buttons(stance: HoldToggle, aim: HoldToggle, auto_sprint: bool, t: &mut Toggles, k: HoldKeys) -> [bool; 3] {
    if (t.forward && !k.forward) || k.crouch.1 {
        t.sprint = false;
    }
    if k.sprint.1 {
        t.crouch = false;
    }
    t.forward = k.forward;
    let ads = hold_or_toggle(aim, &mut t.ads, k.ads.0, k.ads.1);
    let sprint = hold_or_toggle(stance, &mut t.sprint, k.sprint.0, k.sprint.1)
        || (auto_sprint && k.forward && !k.walk && !k.item);
    let crouch = hold_or_toggle(stance, &mut t.crouch, k.crouch.0, k.crouch.1);
    [sprint, crouch, ads]
}

/// The optic on a weapon, if it has one.
pub fn optic_of<'a>(data: &vetf_sim::GameData, weapon: &'a WeaponLoadout) -> Option<&'a str> {
    weapon
        .attachments
        .iter()
        .find(|a| data.attachment(a).is_some_and(|s| s.cat == AttachmentCategory::Optic))
        .map(String::as_str)
}

/// View rotation (radians) per mouse count: the turn distance at the mouse's DPI, moving to the optic's ADS
/// sensitivity as the gun comes up (`ads` 0 hip .. 1 aimed). The focal-length part follows the camera's zoom
/// through the blend (`render::camera_fov`); the per-optic multiplier blends in linearly.
pub fn look_per_count(settings: &Settings, optic: Option<&str>, zoom: f32, ads: f32) -> f32 {
    let ads = ads.clamp(0.0, 1.0);
    let mult = optic.map_or(1.0, |o| settings.optic_mult(o));
    rad_per_count(settings.mouse.cm_per_360, settings.mouse.dpi)
        * settings.ads_factor(None, ads_zoom(zoom, ads))
        * (1.0 + (mult - 1.0) * ads)
}

/// Keyboard + mouse into [`LocalControl`] through the player's key map and settings (every frame, before the
/// fixed ticks, so a changed setting applies at once). Nothing reaches the match while it is paused or a hub
/// screen is open over it.
fn gather_input(
    mut devices: BindDevices,
    motion: Res<AccumulatedMouseMotion>,
    time: Res<Time>,
    cli: Res<Cli>,
    data: Res<Data>,
    settings: Res<Settings>,
    tables: Res<SettingsData>,
    screens: Res<Screens>,
    me: Query<(&PlayerLoadout, &PlayerItems, Option<&Vitals>, Option<&PlayerWeapon>), With<Controlled>>,
    mut control: ResMut<LocalControl>,
    mut logged: Local<Option<(f32, u32)>>,
) {
    if cli.bot {
        return;
    }
    let mut input = devices.read();
    let (kb, m, g) = (&settings.keybinds, &settings.mouse, &settings.gameplay);
    // Aimed through a variable scope the zoom binds have the wheel (and their keys): nothing else reads them.
    if control.scope.active {
        input.take(kb, &crate::settings::ZOOM);
    }
    if *logged != Some((m.cm_per_360, m.dpi)) {
        *logged = Some((m.cm_per_360, m.dpi));
        let deg = rad_per_count(m.cm_per_360, m.dpi).to_degrees();
        info!("look: {} cm/360 at {} DPI = {deg:.4} deg per count", m.cm_per_360, m.dpi);
    }
    if control.paused || !screens.is_empty() {
        control.movement = Vec2::ZERO;
        control.held = 0;
        control.toggles = Toggles::default();
        control.reload_held_s = None;
        control.reload_radial = None;
        control.heal = None;
        // The click on RESUME (or on a screen's CONFIRM) is still down when play resumes: not a shot.
        control.mouse_block = true;
        return;
    }
    let me = me.iter().next();
    let item_in_hand = me.is_some_and(|(_, it, ..)| it.0.using.is_some());
    // No ring menus while dead, and toggles come back off.
    if me.is_some_and(|(_, _, v, _)| v.is_some_and(|v| v.health.dead)) {
        control.heal = None;
        control.reload_radial = None;
        control.reload_held_s = None;
        control.toggles = Toggles::default();
    }
    let mags = me.map_or(1, |(l, ..)| l.0.weapon.mags.len());
    let kit: Vec<HealOption> = me.map(|(l, it, v, _)| heal_options(&data, &l.0, &it.0, v)).unwrap_or_default();
    // Screenshot and demo runs ignore the desktop's mouse: it must not turn the view.
    let mouse_delta = if cli.ignores_desktop_input() { Vec2::ZERO } else { motion.delta };
    // The ring menus steer an on-screen cursor in pixels, the same hand distance at any DPI.
    let tuning = tables.radial;
    let ring_delta = mouse_delta * crate::radial::px_per_count(m.dpi, &tuning);
    heal_input(&mut control, kb, &input, ring_delta, &kit, &tuning);
    let dt = time.delta_secs();
    let ring = RingSettings { hold_s: g.radial_hold_s, pick: g.radial_pick, tuning };
    let tap_reload = control.heal.is_none() && reload_input(&mut control, kb, &input, ring_delta, dt, mags, ring);
    let ring_open = control.heal.is_some() || control.reload_radial.is_some();
    if ring_open {
        control.mouse_block = true;
        control.toggles.ads = false;
    } else if !kb.pressed(Action::Fire, &input) && !kb.pressed(Action::Ads, &input) {
        control.mouse_block = false;
    }
    if !ring_open {
        let (optic, zoom) =
            me.map_or((None, 1.0), |(l, ..)| (optic_of(&data, &l.0.weapon), control.scope.of(&l.0.weapon)));
        let ads = me.and_then(|(.., w)| w).map_or(0.0, |w| w.0.ads);
        let s = look_per_count(&settings, optic, zoom, ads);
        let dy = if m.invert_y { -mouse_delta.y } else { mouse_delta.y };
        control.yaw = (control.yaw - mouse_delta.x * s).rem_euclid(std::f32::consts::TAU);
        control.pitch = (control.pitch - dy * s).clamp(-MAX_PITCH, MAX_PITCH);
    }

    let held = |a: Action| kb.pressed(a, &input);
    let pressed = |a: Action| kb.just_pressed(a, &input);
    let axis = |neg: Action, pos: Action| (held(pos) as i32 - held(neg) as i32) as f32;
    control.movement =
        Vec2::new(axis(Action::MoveLeft, Action::MoveRight), axis(Action::MoveBack, Action::MoveForward));
    // Fire and aim stay off after a ring menu or a focus click until they are released.
    let free = !control.mouse_block;
    let keys = HoldKeys {
        sprint: (held(Action::Sprint), pressed(Action::Sprint)),
        crouch: (held(Action::Crouch), pressed(Action::Crouch)),
        ads: (free && held(Action::Ads), free && pressed(Action::Ads)),
        walk: held(Action::Walk),
        forward: control.movement.y > 0.0,
        item: item_in_hand || control.item_pick.0 != 0,
    };
    let [sprint, crouch, ads] =
        hold_buttons(settings.hud.hold_toggle, m.ads_input, g.auto_sprint, &mut control.toggles, keys);

    let mut bits = demo_held(&cli);
    for (bit, on) in [
        (Buttons::JUMP, held(Action::Jump)),
        (Buttons::CROUCH, crouch),
        (Buttons::SPRINT, sprint),
        (Buttons::WALK, held(Action::Walk)),
        (Buttons::FIRE, free && held(Action::Fire)),
        (Buttons::ADS, ads),
        (Buttons::MAG_CHECK, held(Action::MagCheck)),
        (Buttons::FIRE_MODE, held(Action::FireMode)),
        (Buttons::INTERACT, held(Action::Interact)),
    ] {
        if on {
            bits |= bit;
        }
    }
    control.latched |= bits & !control.held;
    control.held = bits;
    if tap_reload {
        control.latched |= Buttons::RELOAD;
    }
}

/// Buttons a demo run holds: `--demo-ui ads` aims down sights, for a player and a `--bot` alike (scripted ADS
/// tests over the network); `sprint` and `sprint-ads` hold sprint (and aim) for a `--bot` running forward (with
/// `--yaw`, its first seconds), and so does `dry-fire-sprint` (`sound::demo_dry_fire`, with quick trigger
/// taps). Held, not a one-tick pulse: a frame can run two ticks.
fn demo_held(cli: &Cli) -> u16 {
    match cli.demo_ui.as_deref() {
        Some("ads") => Buttons::ADS,
        Some("sprint" | "dry-fire-sprint") => Buttons::SPRINT,
        Some("sprint-ads") => Buttons::SPRINT | Buttons::ADS,
        _ => 0,
    }
}

/// Heal ring (the Heal key toggles it). Fire on an item: a whole-body item is used at once; a region item
/// opens a second ring of regions around it, where Fire picks the region. Aim steps back; Esc or Heal
/// closes. Dimmed options (none left, or nothing to treat) ignore Fire. A pick turns a toggled sprint off:
/// sprinting would stop the item from starting (the Sprint key pressed again sprints, and cancels it).
fn heal_input(
    control: &mut LocalControl,
    kb: &Keybinds,
    input: &BindInput,
    mouse_delta: Vec2,
    kit: &[HealOption],
    tuning: &RadialTuning,
) {
    if kb.just_pressed(Action::Heal, input) {
        control.heal = match control.heal {
            Some(_) => None,
            None if !kit.is_empty() => Some(HealMenu::new(kit.len(), tuning)),
            None => None,
        };
        control.reload_radial = None;
        control.reload_held_s = None;
    }
    let Some(menu) = &mut control.heal else { return };
    match menu.item {
        None => menu.ring.steer(mouse_delta),
        Some(_) => menu.regions.steer(mouse_delta),
    }
    if kb.just_pressed(Action::Ads, input) {
        if menu.item.take().is_none() {
            control.heal = None;
        }
        return;
    }
    if !kb.just_pressed(Action::Fire, input) {
        return;
    }
    match menu.item {
        None => {
            let Some(i) = menu.ring.selected() else { return };
            let Some(opt) = kit.get(i).filter(|o| o.enabled) else { return };
            match opt.scope {
                ItemScope::Body => {
                    control.item_pick = encode_pick(i as u8, None);
                    control.heal = None;
                    control.toggles.sprint = false;
                }
                ItemScope::Region => {
                    menu.item = Some(i);
                    menu.regions = Radial::regions(tuning);
                }
            }
        }
        Some(i) => {
            let Some(r) = menu.regions.selected() else { return };
            if !kit.get(i).is_some_and(|o| o.regions[r]) {
                return;
            }
            control.item_pick = encode_pick(i as u8, Some(REGION_ORDER[r]));
            control.heal = None;
            control.toggles.sprint = false;
        }
    }
}

/// How the ring menus open and pick: the Gameplay tab's radial hold time and pick mode, and the cursor's tuning
/// (settings.ron).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RingSettings {
    pub hold_s: f32,
    pub pick: RadialPick,
    pub tuning: RadialTuning,
}

/// Reload key: a tap (released before `hold_s`, the Gameplay tab's radial hold time) reloads the next
/// magazine in slot order; holding opens the magazine radial. With RELEASE pick, releasing over a slot picks
/// it; with CLICK pick the ring stays open after the release until Fire picks the slot under the pointer (Aim
/// or another reload press closes it). Number keys 1-6 pick directly while it is open. Returns true on a tap.
fn reload_input(
    control: &mut LocalControl,
    kb: &Keybinds,
    input: &BindInput,
    mouse_delta: Vec2,
    dt: f32,
    mags: usize,
    ring: RingSettings,
) -> bool {
    let RingSettings { hold_s, pick, tuning } = ring;
    const DIGITS: [KeyCode; 6] =
        [KeyCode::Digit1, KeyCode::Digit2, KeyCode::Digit3, KeyCode::Digit4, KeyCode::Digit5, KeyCode::Digit6];
    if kb.just_pressed(Action::Reload, input) {
        // A ring that CLICK pick left open: the next press closes it.
        if control.reload_radial.take().is_some() {
            control.reload_held_s = None;
            return false;
        }
        control.reload_held_s = Some(0.0);
    }
    if kb.pressed(Action::Reload, input)
        && let Some(held) = &mut control.reload_held_s
    {
        *held += dt;
        if *held >= hold_s && control.reload_radial.is_none() {
            control.reload_radial = Some(Radial::new(mags, &tuning));
        }
    }
    if let Some(radial) = &mut control.reload_radial {
        radial.steer(mouse_delta);
        let click = pick == RadialPick::Click;
        let digit = DIGITS.iter().take(mags).position(|k| input.keys.just_pressed(*k));
        let slot = digit.or(radial.selected().filter(|_| click && kb.just_pressed(Action::Fire, input)));
        if slot.is_some() || (click && kb.just_pressed(Action::Ads, input)) {
            control.reload_pick = slot.map_or(0, |i| i as u8 + 1);
            control.reload_radial = None;
            control.reload_held_s = None;
        }
    }
    if !kb.just_released(Action::Reload, input) {
        return false;
    }
    let was_held = control.reload_held_s.take().is_some();
    match (pick, control.reload_radial) {
        (_, None) => was_held,
        (RadialPick::Click, Some(_)) => false,
        (RadialPick::Release, Some(radial)) => {
            if let Some(i) = radial.selected() {
                control.reload_pick = i as u8 + 1;
            }
            control.reload_radial = None;
            false
        }
    }
}

/// Hand the latest controls to lightyear for this tick. Not during rollback replays: they read inputs from
/// lightyear's buffer, and consuming the one-tick pulses (tap reload, radial and heal picks) there would
/// lose them.
fn write_inputs(
    rollback: Option<Res<Rollback>>,
    mut control: ResMut<LocalControl>,
    mut inputs: Query<&mut ActionState<PlayerInput>, With<InputMarker<PlayerInput>>>,
) {
    if rollback.is_some() {
        return;
    }
    for mut a in &mut inputs {
        a.0 = PlayerInput {
            move_x: control.movement.x,
            move_y: control.movement.y,
            yaw: control.yaw,
            pitch: control.pitch,
            buttons: control.held | control.latched,
            reload_slot: control.reload_pick,
            use_item: control.item_pick.0,
            use_zone: control.item_pick.1,
        };
    }
    control.latched = 0;
    control.reload_pick = 0;
    control.item_pick = (0, 0);
}

fn record_smoothing(
    mut commands: Commands,
    mut me: Query<(Entity, &PlayerMove, Option<&mut Smoothed>), With<Controlled>>,
) {
    for (e, mv, smoothed) in &mut me {
        match smoothed {
            Some(mut s) => {
                s.prev = s.curr;
                s.curr = mv.0.pos;
                if s.prev.distance_squared(s.curr) > 4.0 {
                    s.prev = s.curr; // teleport (respawn): do not smear
                }
            }
            None => {
                commands.entity(e).insert(Smoothed { prev: mv.0.pos, curr: mv.0.pos });
            }
        }
    }
}

/// Our shots: recoil, tracer, and (if a player was hit on our screen) a claim to the host.
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn fire_claims(
    mut shots: MessageReader<LocalShot>,
    data: Res<Data>,
    settings: Res<Settings>,
    rig: Res<ViewmodelRig>,
    level: Option<Res<CurrentLevel>>,
    session: Res<Session>,
    timeline: Res<LocalTimeline>,
    interp: Option<Res<InterpolationTimeline>>,
    me: Query<(&PlayerLoadout, &PlayerInfo, Option<&PlayerWeapon>), With<Controlled>>,
    others: Query<(&PlayerId, &PlayerInfo, &PlayerMove, &PlayerLook, &Vitals), Without<Controlled>>,
    mut senders: Query<&mut MessageSender<ShotClaim>, With<Client>>,
    mut control: ResMut<LocalControl>,
    mut feedback: ResMut<Feedback>,
) {
    let Some(level) = level else { return };
    let Some((loadout, my_info, weapon)) = me.iter().next() else { return };
    let ads = weapon.map_or(0.0, |w| w.0.ads);
    let spec = loadout.0.weapon.spec(&data);
    let view_tick = match (&session.role, interp) {
        (Role::Client, Some(i)) if i.is_synced() => i.tick().0 as f32 + i.overstep().to_f32(),
        _ => timeline.tick().0 as f32,
    };
    for s in shots.read() {
        // Recoil: the kick rotates our view (yaw right = negative yaw).
        let pitch_deg = control.pitch.to_degrees();
        control.recoil.on_shot(spec, pitch_deg, s.shot.kick_pitch);
        control.pitch = (control.pitch + s.shot.kick_pitch.to_radians()).clamp(-MAX_PITCH, MAX_PITCH);
        control.yaw -= s.shot.kick_yaw.to_radians();
        control.punch = vetf_sim::recoil::view_punch(spec);

        let dir = shot_direction(s.yaw, s.pitch, s.shot.spread_deg, shot_seed(s.player, s.shot.seq));
        let range = spec.max_range_m;
        let world_hit = level.world.raycast(s.origin, dir, range);
        let world_t = world_hit.map_or(range, |(d, _)| d);
        let mut best: Option<(u64, vetf_sim::Zone, f32, Pose)> = None;
        for (id, info, mv, look, vitals) in &others {
            if vitals.health.dead || (my_info.team.is_some() && info.team == my_info.team) {
                continue;
            }
            let pose = Pose { pos: mv.0.pos, yaw: look.yaw, stance: mv.0.stance };
            if let Some((zone, t)) = hitbox::raycast(&data, &pose, s.origin, dir, world_t)
                && best.is_none_or(|b| t < b.2)
            {
                best = Some((id.0, zone, t, pose));
            }
        }
        debug!("local shot {} spread {:.2} hit {:?} (world at {world_t:.1} m)", s.shot.seq, s.shot.spread_deg, best);
        let end_t = best.map_or(world_t, |b| b.2);
        // From the viewmodel's muzzle (lower right on screen), not from under the eye: a tracer from a point
        // straight below the camera drew a vertical line hanging under the crosshair (playtest 2026-10-07).
        // Through a scope the gun is hidden, so it leaves the scope's centre instead.
        let lens = viewmodel_lens(
            camera_fov(&settings.mouse, control.scope.of(&loadout.0.weapon), ads),
            settings.mouse.viewmodel_fov,
        );
        let start = s.origin + vetf_sim::input::view_rotation(s.yaw, s.pitch) * own_tracer_start(&rig, ads, lens);
        feedback.tracers.push((start, s.origin + dir * end_t, 0.0, true));
        if let (None, Some((d, normal))) = (best, world_hit) {
            feedback.impacts.push((s.origin + dir * d, normal));
        }
        if let Some((victim, zone, t, pose)) = best {
            let hit = HitClaim { origin: s.origin, dir, view_tick, zone, point: s.origin + dir * t };
            // Where on them it hit, for the hit marker once the host confirms it.
            feedback.claims.push(ClaimedHit::new(s.shot.seq, victim, hit.point, pose.pos, pose.yaw));
            for mut sender in &mut senders {
                sender.send::<ClaimChannel>(ShotClaim { seq: s.shot.seq, victim, hit });
            }
        }
    }
}

fn recoil_recovery(
    time: Res<Time>,
    data: Res<Data>,
    me: Query<&PlayerLoadout, With<Controlled>>,
    mut control: ResMut<LocalControl>,
) {
    let Some(loadout) = me.iter().next() else { return };
    let spec = loadout.0.weapon.spec(&data);
    let dt = time.delta_secs();
    let pitch_deg = control.pitch.to_degrees();
    let down = control.recoil.tick(spec, pitch_deg, dt);
    control.pitch -= down.to_radians();
    control.punch = vetf_sim::recoil::settle_punch(spec, control.punch, dt);
}

/// Host feedback. Each receiver gets its own query: lightyear inserts a `MessageReceiver<M>` only once the
/// first `M` arrives, so one query over all four would match nothing until every type had been received.
#[allow(clippy::too_many_arguments)]
fn receive_feedback(
    mut hits: Query<&mut MessageReceiver<HitConfirm>, With<Client>>,
    mut damage: Query<&mut MessageReceiver<DamageTaken>, With<Client>>,
    mut kills: Query<&mut MessageReceiver<KillFeed>, With<Client>>,
    mut fx: Query<&mut MessageReceiver<ShotFx>, With<Client>>,
    players: Query<(&PlayerId, &PlayerInfo)>,
    me: Query<&PlayerId, With<Controlled>>,
    level: Option<Res<CurrentLevel>>,
    mut feedback: ResMut<Feedback>,
    mut sounds: MessageWriter<crate::sound::FeedbackSound>,
) {
    let me = me.iter().next().map(|p| p.0);
    let name = |id: u64| {
        players.iter().find(|(p, _)| p.0 == id).map(|(_, i)| i.name.clone()).unwrap_or_else(|| format!("{id:x}"))
    };
    for mut rx in &mut hits {
        for h in rx.receive() {
            debug!("hit confirmed: {:?} {:?}", h.zone, h.kind);
            sounds.write(crate::sound::FeedbackSound::Hit(h));
            feedback.hits.push(h);
        }
    }
    for mut rx in &mut damage {
        for d in rx.receive() {
            feedback.damage.push((d.from, 1.2));
            sounds.write(crate::sound::FeedbackSound::Damage(d));
        }
    }
    for mut rx in &mut kills {
        for k in rx.receive() {
            let entry = FeedEntry {
                killer: k.killer.map(name),
                helpers: k.assists.iter().copied().map(name).collect(),
                cause: k.cause,
                victim: name(k.victim),
                headshot: k.zone == Some(vetf_sim::Zone::Head) && !k.cause.is_environmental(),
                left_s: FEED_LINE_S,
            };
            info!("kill feed: {}", crate::hud::feed_text(&entry).line(&entry.victim));
            feedback.kills.push(entry);
            // Only a helper gets the popup and the sound.
            if me.is_some_and(|m| k.assisted_by(m)) {
                feedback.assist_s = ASSIST_POPUP_S;
                sounds.write(crate::sound::FeedbackSound::Assist);
            }
        }
    }
    for mut rx in &mut fx {
        for s in rx.receive() {
            feedback.tracers.push((s.origin, s.end, 0.0, false));
            // The host sends where the shot met the level; find the surface it hit for the decal.
            let len = s.origin.distance(s.end);
            if let Some(level) = &level
                && len > 0.01
                && let Some((d, normal)) = level.world.raycast(s.origin, (s.end - s.origin) / len, len + 0.1)
                && (d - len).abs() < 0.05
            {
                feedback.impacts.push((s.origin + (s.end - s.origin) / len * d, normal));
            }
        }
    }
}

fn tick_feedback(time: Res<Time>, mut feedback: ResMut<Feedback>) {
    let dt = time.delta_secs();
    feedback.damage.retain_mut(|(_, t)| {
        *t -= dt;
        *t > 0.0
    });
    feedback.kills.retain_mut(|k| {
        k.left_s -= dt;
        k.left_s > 0.0
    });
    feedback.assist_s = (feedback.assist_s - dt).max(0.0);
    // As many as the longest KILL FEED LINES choice; the HUD shows the player's number of them.
    let keep = crate::settings::KillFeed::ALL.iter().map(|k| k.lines()).max().unwrap_or(5);
    if feedback.kills.len() > keep {
        let n = feedback.kills.len() - keep;
        feedback.kills.drain(..n);
    }
}

/// `--bot` drives the controls instead of the keyboard and mouse (`t` seconds since start-up, `since` in the
/// match): wander, look around and fire short bursts, plus what a demo run holds (`--demo-ui ads` aims).
fn bot_controls(cli: &Cli, t: f32, since: f32, control: &mut LocalControl) {
    let phase = (t * 0.5) as i32 % 4;
    control.movement = match phase {
        0 => Vec2::Y,
        1 => Vec2::new(1.0, 0.3),
        2 => Vec2::NEG_Y,
        _ => Vec2::new(-1.0, 0.3),
    };
    match cli.yaw {
        // Hold a heading and strafe (aim tests): only side-to-side movement.
        Some(yaw) => {
            // Close in for the first few seconds, then hold position and strafe a little.
            control.movement = if since < 3.5 { Vec2::Y } else { Vec2::new((t * 1.5).sin() * 0.15, 0.0) };
            control.yaw = yaw.to_radians();
            control.pitch = -0.01;
        }
        None => {
            control.yaw = (t * 0.6).sin() * 1.2 + std::f32::consts::FRAC_PI_2 * if phase < 2 { 1.0 } else { -1.0 };
            control.pitch = (t * 1.3).sin() * 0.08;
        }
    }
    // Bursts of half a second every 1.5 s; `dry-fire-sprint` runs forward only (so it sprints) and taps the
    // trigger for a tenth of a second instead (a hip tap on the run, the gun still coming up from the sprint).
    let firing = if cli.demo_ui.as_deref() == Some("dry-fire-sprint") {
        control.movement = Vec2::Y;
        (t * 10.0) as i32 % 15 == 0
    } else {
        (t * 2.0) as i32 % 3 == 0 && (cli.yaw.is_none() || since > 3.5)
    };
    control.held = demo_held(cli) | if firing { Buttons::FIRE } else { 0 };
    if (t as i32) % 7 == 3 && cli.yaw.is_none() {
        control.held |= Buttons::JUMP;
    }
    // Tap reload now and then (a full magazine ignores it).
    if (t as i32) % 5 == 4 {
        control.latched |= Buttons::RELOAD;
    }
}

/// `--bot`, `--screenshot` and `--exit-after` for automated runs.
fn automation(
    cli: Res<Cli>,
    time: Res<Time>,
    state: Res<State<AppState>>,
    tables: Option<Res<SettingsData>>,
    me: Query<(&PlayerLoadout, &PlayerItems), With<Controlled>>,
    mut control: ResMut<LocalControl>,
    mut commands: Commands,
    mut taken: Local<bool>,
    mut demo_checked: Local<bool>,
    mut in_game_since: Local<Option<f32>>,
    mut exit: MessageWriter<AppExit>,
) {
    let t = time.elapsed_secs();
    if *state.get() != AppState::InGame {
        *in_game_since = None;
    }
    if *state.get() == AppState::InGame {
        in_game_since.get_or_insert(t);
    }
    if cli.bot && *state.get() == AppState::InGame {
        bot_controls(&cli, t, t - in_game_since.unwrap_or(t), &mut control);
    }
    // Open a ring menu for screenshots, the cursor resting on the second option (the bottom region).
    let on_option = |r: &mut Radial, i: usize| r.steer(crate::radial::option_offset(i, r.options, r.reach));
    let tuning = tables.map_or_else(|| crate::settings::embedded().radial, |t| t.radial);
    if let Some(demo) = cli.demo_ui.as_deref()
        && in_game_since.is_some_and(|s| t - s > 1.0)
        && let Some((lo, _)) = me.iter().next()
    {
        match demo {
            "reload" => {
                let mut radial = Radial::new(lo.0.weapon.mags.len(), &tuning);
                on_option(&mut radial, 1);
                control.reload_radial = Some(radial);
            }
            // The HUD with wounds (see server::demo_wounds) and a mag check card.
            "hud" if !*demo_checked && t - in_game_since.unwrap_or(t) > 1.5 => {
                *demo_checked = true;
                control.latched |= Buttons::MAG_CHECK;
            }
            "heal" | "heal-region" => {
                let mut menu = HealMenu::new(lo.0.kit.len(), &tuning);
                on_option(&mut menu.ring, 1);
                if demo == "heal-region" {
                    menu.item = menu.ring.selected();
                    on_option(&mut menu.regions, 2);
                }
                control.heal = Some(menu);
            }
            _ => {}
        }
    }
    // With --host / --join the screenshot clock starts when the match view appears.
    let clock = if cli.host.is_some() || cli.join.is_some() { in_game_since.map_or(-1.0, |s| t - s) } else { t };
    if let Some(path) = &cli.screenshot
        && !*taken
        && clock >= cli.screenshot_after
    {
        *taken = true;
        info!("saving screenshot to {}", path.display());
        commands.spawn(Screenshot::primary_window()).observe(save_to_disk(path.clone()));
    }
    if cli.exit_after.is_some_and(|e| t >= e) {
        exit.write(AppExit::Success);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::{AdsScaling, Binding};
    use std::f32::consts::{PI, TAU};

    fn near(a: f32, b: f32) -> bool {
        (a - b).abs() <= 1e-5 * b.abs()
    }

    #[test]
    fn hold_follows_the_key_and_toggle_flips_on_each_press() {
        let mut on = false;
        assert!(hold_or_toggle(HoldToggle::Hold, &mut on, true, true));
        assert!(!hold_or_toggle(HoldToggle::Hold, &mut on, false, false));
        assert!(hold_or_toggle(HoldToggle::Toggle, &mut on, true, true), "pressed: on");
        assert!(hold_or_toggle(HoldToggle::Toggle, &mut on, false, false), "released: still on");
        assert!(!hold_or_toggle(HoldToggle::Toggle, &mut on, true, true), "pressed again: off");
        on = true;
        hold_or_toggle(HoldToggle::Hold, &mut on, false, false);
        assert!(!on, "switching to HOLD forgets a toggle");
    }

    #[test]
    fn toggled_sprint_crouch_and_aim() {
        use HoldToggle::{Hold, Toggle};
        let mut t = Toggles::default();
        let frame = |t: &mut Toggles, k: HoldKeys| hold_buttons(Toggle, Toggle, false, t, k);
        let fwd = HoldKeys { forward: true, ..default() };
        // sprint stays on after the key is let go, until forward input stops
        assert!(frame(&mut t, HoldKeys { sprint: (true, true), ..fwd })[0]);
        assert!(frame(&mut t, fwd)[0]);
        assert!(!frame(&mut t, HoldKeys::default())[0], "stopped: sprint ends");
        assert!(!frame(&mut t, fwd)[0], "and stays off when moving again");
        // crouch (a slide) ends a toggled sprint; sprint stands a toggled crouch up and keeps a toggled aim
        frame(&mut t, HoldKeys { sprint: (true, true), ..fwd });
        let [sprint, crouch, _] = frame(&mut t, HoldKeys { crouch: (true, true), ..fwd });
        assert!(!sprint && crouch);
        assert_eq!(frame(&mut t, fwd), [false, true, false], "crouch stays on");
        frame(&mut t, HoldKeys { ads: (true, true), ..fwd });
        assert_eq!(frame(&mut t, fwd), [false, true, true], "aim stays on");
        assert_eq!(frame(&mut t, HoldKeys { sprint: (true, true), ..fwd }), [true, false, true], "an aimed sprint");
        // HOLD follows the keys; auto-sprint runs on forward input unless walking
        let mut t = Toggles::default();
        let crouching = HoldKeys { crouch: (true, false), ..fwd };
        assert_eq!(hold_buttons(Hold, Hold, false, &mut t, crouching), [false, true, false]);
        assert!(hold_buttons(Hold, Hold, true, &mut t, fwd)[0], "auto-sprint");
        let walking = HoldKeys { walk: true, ..fwd };
        assert!(!hold_buttons(Hold, Hold, true, &mut t, walking)[0], "walk beats auto-sprint");
        assert!(!hold_buttons(Hold, Hold, true, &mut t, HoldKeys::default())[0], "standing still");
        // with auto-sprint on, holding the Sprint key just sprints as well (nothing odd)
        let both = HoldKeys { sprint: (true, true), ..fwd };
        assert!(hold_buttons(Hold, Hold, true, &mut t, both)[0]);
    }

    /// Aiming, firing and mag checks never end a sprint (user direction 2026-10-08): the sim brings the gun up
    /// from the sprint pose instead. They used to end it, so that the lowered gun could come up at all.
    #[test]
    fn aiming_firing_and_mag_checks_keep_the_sprint() {
        use HoldToggle::{Hold, Toggle};
        let fwd = HoldKeys { forward: true, ..default() };
        let mut t = Toggles::default();
        assert!(hold_buttons(Toggle, Hold, false, &mut t, HoldKeys { sprint: (true, true), ..fwd })[0]);
        let aim = HoldKeys { ads: (true, true), ..fwd };
        assert_eq!(hold_buttons(Toggle, Hold, false, &mut t, aim), [true, false, true], "a toggled sprint goes on");
        assert!(hold_buttons(Toggle, Hold, false, &mut t, fwd)[0], "and stays on");
        let mut t = Toggles::default();
        assert_eq!(hold_buttons(Hold, Hold, true, &mut t, aim), [true, false, true], "auto-sprint with aim");
        let mut t = Toggles::default();
        let held = HoldKeys { sprint: (true, false), ads: (true, true), ..fwd };
        assert_eq!(hold_buttons(Hold, Toggle, false, &mut t, held), [true, false, true], "held sprint, toggled aim");
    }

    /// Sprinting cancels an item, so auto-sprint waits while one is in hand or just picked; the Sprint key
    /// still sprints (and cancels it on purpose).
    #[test]
    fn auto_sprint_waits_for_an_item() {
        use HoldToggle::{Hold, Toggle};
        let mut t = Toggles::default();
        let healing = HoldKeys { forward: true, item: true, ..default() };
        assert!(!hold_buttons(Hold, Hold, true, &mut t, healing)[0]);
        assert!(hold_buttons(Hold, Hold, true, &mut t, HoldKeys { sprint: (true, true), ..healing })[0]);
        assert!(hold_buttons(Hold, Hold, true, &mut t, HoldKeys { item: false, ..healing })[0], "done: sprinting");
        // TOGGLE: a Sprint press while an item is in hand sprints and stays on (the frames until the fixed
        // tick still see the item in hand); the heal pick itself turns the toggle off (`heal_input`)
        for auto in [false, true] {
            let mut t = Toggles::default();
            assert!(!hold_buttons(Toggle, Hold, auto, &mut t, healing)[0], "auto-sprint {auto}: healing");
            assert!(hold_buttons(Toggle, Hold, auto, &mut t, HoldKeys { sprint: (true, true), ..healing })[0]);
            assert!(hold_buttons(Toggle, Hold, auto, &mut t, healing)[0], "auto-sprint {auto}: still toggled");
        }
    }

    #[test]
    fn look_speed_is_the_turn_distance_and_the_optics_ads_factor() {
        let mut s = Settings::default();
        s.mouse.cm_per_360 = 40.8;
        s.mouse.dpi = 800;
        s.mouse.ads_scaling = AdsScaling::MatchFocal;
        let hip = rad_per_count(40.8, 800);
        assert!(near(look_per_count(&s, Some("optic_3x"), 3.0, 0.0), hip), "hip fire ignores the optic");
        // one turn of the mouse (40.8 cm at 800 DPI) is one turn of the view
        let counts = 40.8 / 2.54 * 800.0;
        assert!((look_per_count(&s, None, 1.0, 0.0) * counts - TAU).abs() < 1e-3);
        s.mouse.optic_mult.insert("optic_3x".into(), 0.9);
        let aimed = look_per_count(&s, Some("optic_3x"), 3.0, 1.0);
        assert!(near(aimed, hip * s.ads_factor(Some("optic_3x"), 3.0)), "fully aimed: the ADS factor");
        assert!((aimed / hip - 0.3).abs() < 1e-3, "1/3 for the zoom times the 0.9 multiplier");
        let half = look_per_count(&s, Some("optic_3x"), 3.0, 0.5);
        assert!(half < hip && half > aimed, "slows down as the gun comes up");
        s.mouse.ads_scaling = AdsScaling::SameCm;
        assert!(near(look_per_count(&s, Some("optic_3x"), 3.0, 1.0), hip * 0.9));
        assert!(near(look_per_count(&s, None, 1.0, 1.0), hip), "iron sights at SAME CM/360");
        s.mouse.cm_per_360 = 20.4;
        assert!(near(look_per_count(&s, None, 1.0, 0.0), 2.0 * hip), "half the distance, twice the turn");
    }

    fn ring(hold_s: f32, pick: RadialPick) -> RingSettings {
        RingSettings { hold_s, pick, tuning: crate::settings::embedded().radial }
    }

    fn bind_input<'a>(keys: &'a ButtonInput<KeyCode>, mouse: &'a ButtonInput<MouseButton>) -> BindInput<'a> {
        BindInput { keys, mouse, wheel: 0.0, wheel_prev: 0.0, taken: Vec::new() }
    }

    /// Hold the reload key for `frames` frames of 50 ms (steering on the last one), then release it.
    fn hold_reload(c: &mut LocalControl, kb: &Keybinds, steer: Vec2, hold_s: f32, pick: RadialPick) -> bool {
        let (mut keys, mouse) = (ButtonInput::<KeyCode>::default(), ButtonInput::<MouseButton>::default());
        keys.press(KeyCode::KeyR);
        let frames = 6;
        for f in 0..frames {
            let delta = if f == frames - 1 { steer } else { Vec2::ZERO };
            reload_input(c, kb, &bind_input(&keys, &mouse), delta, 0.05, 6, ring(hold_s, pick));
            keys.clear();
        }
        keys.release(KeyCode::KeyR);
        reload_input(c, kb, &bind_input(&keys, &mouse), Vec2::ZERO, 0.05, 6, ring(hold_s, pick))
    }

    #[test]
    fn the_radial_hold_time_and_pick_mode_come_from_the_settings() {
        let kb = Settings::default().keybinds;
        let up = Vec2::new(0.0, -50.0);
        // 0.3 s is a tap with a 0.5 s hold time, and opens the ring with 0.2 s (released over slot 1)
        let mut c = LocalControl::default();
        assert!(hold_reload(&mut c, &kb, up, 0.5, RadialPick::Release), "a tap reloads");
        assert!(c.reload_radial.is_none() && c.reload_pick == 0);
        let mut c = LocalControl::default();
        assert!(!hold_reload(&mut c, &kb, up, 0.2, RadialPick::Release));
        assert_eq!(c.reload_pick, 1, "released over the top slot");
        assert!(c.reload_radial.is_none());
        // CLICK: the ring stays open after the release and Fire picks
        let mut c = LocalControl::default();
        assert!(!hold_reload(&mut c, &kb, Vec2::new(50.0, 30.0), 0.2, RadialPick::Click));
        assert!(c.reload_radial.is_some() && c.reload_pick == 0, "still open, nothing picked");
        let (keys, mut mouse) = (ButtonInput::<KeyCode>::default(), ButtonInput::<MouseButton>::default());
        mouse.press(MouseButton::Left);
        reload_input(&mut c, &kb, &bind_input(&keys, &mouse), Vec2::ZERO, 0.05, 6, ring(0.2, RadialPick::Click));
        assert_eq!((c.reload_pick, c.reload_radial), (3, None), "Fire picks the slot under the pointer");
        // a rebound reload key: R does nothing any more
        let mut kb = kb;
        kb.set(Action::Reload, 0, Some(Binding::Key(KeyCode::KeyG)));
        let mut c = LocalControl::default();
        assert!(!hold_reload(&mut c, &kb, up, 0.2, RadialPick::Release));
        assert!(c.reload_pick == 0 && c.reload_held_s.is_none());
    }

    /// A test app around [`gather_input`], with no player.
    fn input_app() -> App {
        let mut app = App::new();
        app.init_resource::<ButtonInput<KeyCode>>()
            .init_resource::<ButtonInput<MouseButton>>()
            .init_resource::<AccumulatedMouseMotion>()
            .init_resource::<AccumulatedMouseScroll>()
            .init_resource::<Time>()
            .init_resource::<Screens>()
            .init_resource::<LocalControl>()
            .insert_resource(Cli::default())
            .insert_resource(Data(Arc::new(vetf_sim::GameData::embedded())))
            .insert_resource(Settings::default())
            .insert_resource(crate::settings::embedded().clone())
            .add_systems(Update, (crate::scope_zoom::update, gather_input).chain());
        app
    }

    /// One frame with these keys down and this mouse motion: the held buttons, movement, and the yaw and
    /// pitch it turned.
    fn frame(app: &mut App, press: &[KeyCode], motion: Vec2) -> (u16, Vec2, f32, f32) {
        let (yaw, pitch) = {
            let c = app.world().resource::<LocalControl>();
            (c.yaw, c.pitch)
        };
        for k in press {
            app.world_mut().resource_mut::<ButtonInput<KeyCode>>().press(*k);
        }
        app.world_mut().resource_mut::<AccumulatedMouseMotion>().delta = motion;
        app.update();
        let mut keys = app.world_mut().resource_mut::<ButtonInput<KeyCode>>();
        keys.release_all();
        keys.clear();
        let c = app.world().resource::<LocalControl>();
        (c.held, c.movement, (c.yaw - yaw + PI).rem_euclid(TAU) - PI, c.pitch - pitch)
    }

    /// Item 8d in the running input: aimed through the Warden's 6-12x scope the wheel zooms (wheel down no longer
    /// jumps), the zoom is saved in the settings and turns the look slower; from the hip the wheel jumps again
    /// and the zoom stays.
    #[test]
    fn aimed_through_a_variable_scope_the_wheel_zooms() {
        let mut app = input_app();
        let data = vetf_sim::GameData::embedded();
        let mut lo = vetf_sim::player::Loadout::default_for(&data, vetf_sim::data::Mode::Range);
        lo.weapon = WeaponLoadout::resolve(&data, "vk50_warden", &[], &["optic_sniper".into()]).unwrap();
        let items = vetf_sim::items::ItemState::new(&lo.kit);
        app.world_mut().spawn((PlayerLoadout(lo), PlayerItems(items), Controlled));
        let wheel = |app: &mut App, notches: f32| {
            app.world_mut().resource_mut::<AccumulatedMouseScroll>().delta = Vec2::new(0.0, notches);
        };
        let aim = |app: &mut App, on: bool| {
            let mut m = app.world_mut().resource_mut::<ButtonInput<MouseButton>>();
            if on { m.press(MouseButton::Right) } else { m.release(MouseButton::Right) }
        };
        let scope = |app: &App| app.world().resource::<LocalControl>().scope.clone();
        frame(&mut app, &[], Vec2::ZERO);
        assert_eq!((scope(&app).optic.as_deref(), scope(&app).target), (Some("optic_sniper"), 6.0));
        // hip: wheel down jumps, nothing zooms
        wheel(&mut app, -1.0);
        let (held, ..) = frame(&mut app, &[], Vec2::ZERO);
        assert_ne!(held & Buttons::JUMP, 0, "from the hip the wheel jumps");
        assert_eq!(scope(&app).target, 6.0);
        wheel(&mut app, 0.0);
        frame(&mut app, &[], Vec2::ZERO);
        // aim (the ADS button goes out this frame; the zoom binds take the wheel from the next)
        aim(&mut app, true);
        let (held, ..) = frame(&mut app, &[], Vec2::ZERO);
        assert_ne!(held & Buttons::ADS, 0);
        wheel(&mut app, 3.0);
        frame(&mut app, &[], Vec2::ZERO);
        let zoomed = scope(&app).target;
        assert!(zoomed > 6.0 && zoomed < 12.0 && scope(&app).active, "{zoomed}");
        let saved = app.world().resource::<Settings>().optic_zoom.get("optic_sniper").copied();
        assert_eq!(saved, Some((zoomed * 100.0).round() / 100.0), "remembered in the settings");
        wheel(&mut app, -1.0);
        let (held, ..) = frame(&mut app, &[], Vec2::ZERO);
        assert_eq!(held & Buttons::JUMP, 0, "aimed through the scope wheel down zooms out, no jump");
        assert!(scope(&app).target < zoomed);
        // the look follows the live zoom
        {
            let mut c = app.world_mut().resource_mut::<LocalControl>();
            c.scope.live = 12.0;
        }
        let s = app.world().resource::<Settings>().clone();
        let at12 = look_per_count(&s, Some("optic_sniper"), app.world().resource::<LocalControl>().scope.live, 1.0);
        assert!((at12 / look_per_count(&s, Some("optic_sniper"), 6.0, 1.0) - 0.5).abs() < 1e-3);
        // release: the wheel jumps again, the zoom stays where it was
        aim(&mut app, false);
        wheel(&mut app, 0.0);
        frame(&mut app, &[], Vec2::ZERO);
        let kept = scope(&app).target;
        wheel(&mut app, -1.0);
        frame(&mut app, &[], Vec2::ZERO);
        let (held, ..) = frame(&mut app, &[], Vec2::ZERO);
        assert_ne!(held & Buttons::JUMP, 0, "the wheel jumps again");
        assert_eq!(scope(&app).target, kept, "from the hip the wheel never zooms");
        assert!(!scope(&app).active);
    }

    #[test]
    fn the_key_map_and_look_settings_reach_the_input() {
        let mut app = input_app();
        let (held, movement, ..) = frame(&mut app, &[KeyCode::KeyW, KeyCode::Space], Vec2::ZERO);
        assert_eq!(movement, Vec2::Y);
        assert_ne!(held & Buttons::JUMP, 0, "Space jumps by default");
        // rebound keys: the old ones do nothing, the new ones work
        let mut s = app.world_mut().resource_mut::<Settings>();
        s.keybinds.set(Action::Jump, 0, Some(Binding::Key(KeyCode::KeyJ)));
        s.keybinds.set(Action::MoveForward, 0, Some(Binding::Key(KeyCode::ArrowUp)));
        let (held, movement, ..) = frame(&mut app, &[KeyCode::Space, KeyCode::KeyW], Vec2::ZERO);
        assert_eq!((held & Buttons::JUMP, movement), (0, Vec2::ZERO));
        let (held, movement, ..) = frame(&mut app, &[KeyCode::KeyJ, KeyCode::ArrowUp], Vec2::ZERO);
        assert_ne!(held & Buttons::JUMP, 0);
        assert_eq!(movement, Vec2::Y);
        // look: the turn distance and invert Y apply on the next frame (yaw wraps at a full turn, so it is
        // only good to f32 precision there)
        let per = rad_per_count(40.8, 800);
        let turned = |got: f32, want: f32| (got - want).abs() < 2e-6;
        let (.., yaw, pitch) = frame(&mut app, &[], Vec2::new(10.0, 5.0));
        assert!(turned(yaw, -10.0 * per) && turned(pitch, -5.0 * per), "{yaw} {pitch}");
        let mut s = app.world_mut().resource_mut::<Settings>();
        s.mouse.cm_per_360 = 20.4;
        s.mouse.invert_y = true;
        let (.., yaw, pitch) = frame(&mut app, &[], Vec2::new(10.0, 5.0));
        assert!(turned(yaw, -20.0 * per) && turned(pitch, 10.0 * per), "{yaw} {pitch}");
        // toggle crouch stays on after a tap, until the next tap (of either crouch key)
        app.world_mut().resource_mut::<Settings>().hud.hold_toggle = HoldToggle::Toggle;
        assert_ne!(frame(&mut app, &[KeyCode::ControlLeft], Vec2::ZERO).0 & Buttons::CROUCH, 0);
        assert_ne!(frame(&mut app, &[], Vec2::ZERO).0 & Buttons::CROUCH, 0, "still crouched");
        assert_eq!(frame(&mut app, &[KeyCode::KeyC], Vec2::ZERO).0 & Buttons::CROUCH, 0);
    }

    /// The defaults (user direction 2026-10-08): running forward sprints, Shift held walks, B heals and H switches
    /// the fire mode; with auto-sprint off, the Sprint key (Alt) sprints. End to end: the keys, then the sim.
    #[test]
    fn auto_sprint_and_shift_to_walk_by_default() {
        use vetf_sim::movement::{MoveModifiers, MoveState, step};
        let mut app = input_app();
        let data = vetf_sim::GameData::embedded();
        let mut level = vetf_sim::level::Level::default();
        level.world.push(vetf_sim::movement::collision::Brush::cuboid(
            Vec3::new(-100.0, -1.0, -100.0),
            Vec3::new(100.0, 0.0, 100.0),
            vetf_sim::movement::collision::BrushKind::Solid,
        ));
        // hold these keys for a second; the sim's speed and sprint state at the end
        let run = |app: &mut App, keys: &[KeyCode]| {
            let mut st = MoveState::spawn(Vec3::ZERO, 1.6);
            let mods = MoveModifiers::unarmored(&data);
            let mut bits = 0;
            for _ in 0..60 {
                let (held, movement, ..) = frame(app, keys, Vec2::ZERO);
                bits = held;
                let input = vetf_sim::input::InputFrame { movement, buttons: Buttons(held), ..default() };
                step(&data, &level, &mut st, &input, &mods, data.tick_dt());
            }
            (bits, st.sprinting, st.horizontal_speed())
        };
        let (bits, sprinting, speed) = run(&mut app, &[KeyCode::KeyW]);
        assert!(bits & Buttons::SPRINT != 0 && sprinting, "W alone sprints");
        assert!((speed - data.movement.speed.sprint).abs() < 1e-3, "{speed}");
        let (bits, sprinting, speed) = run(&mut app, &[KeyCode::KeyW, KeyCode::ShiftLeft]);
        assert!(bits & Buttons::WALK != 0 && bits & Buttons::SPRINT == 0 && !sprinting, "Shift walks");
        assert!((speed - data.movement.speed.walk).abs() < 1e-3, "{speed}");
        let (_, sprinting, _) = run(&mut app, &[KeyCode::KeyD]);
        assert!(!sprinting, "strafing does not sprint");
        let (bits, sprinting, _) = run(&mut app, &[KeyCode::KeyW, KeyCode::KeyT]);
        assert!(bits & Buttons::MAG_CHECK != 0 && sprinting, "a mag check keeps the sprint");
        app.world_mut().resource_mut::<Settings>().gameplay.auto_sprint = false;
        let (_, sprinting, speed) = run(&mut app, &[KeyCode::KeyW]);
        assert!(!sprinting && (speed - data.movement.speed.jog).abs() < 1e-3, "auto-sprint off: a jog");
        let (_, sprinting, _) = run(&mut app, &[KeyCode::KeyW, KeyCode::AltLeft]);
        assert!(sprinting, "and the Sprint key sprints");
        // H switches the fire mode now, B does not (it opens the heal ring)
        assert_ne!(frame(&mut app, &[KeyCode::KeyH], Vec2::ZERO).0 & Buttons::FIRE_MODE, 0);
        assert_eq!(frame(&mut app, &[KeyCode::KeyB], Vec2::ZERO).0 & Buttons::FIRE_MODE, 0);
    }

    /// The review of round 1: with SPRINT set to TOGGLE, a sprint toggled on before the heal ring opened was
    /// still on when an item was picked, so SPRINT went out with the pick, the sim refused to start the item
    /// (sprinting lowers the gun) and the pick was lost. A pick now turns the toggle off; pressing Sprint during
    /// the item still sprints (cancelling it on purpose) and stays toggled. Auto-sprint on or off.
    #[test]
    fn a_heal_pick_turns_a_toggled_sprint_off() {
        use vetf_sim::items::{ItemState, ItemUse};
        for auto_sprint in [false, true] {
            let mut app = input_app();
            let data = vetf_sim::GameData::embedded();
            let lo = vetf_sim::player::Loadout::default_for(&data, vetf_sim::data::Mode::Tdm);
            let items = ItemState::new(&lo.kit);
            let kit = lo.kit.len();
            assert_eq!(data.items.spec(&lo.kit[0]).scope, ItemScope::Body, "the TDM kit's first item is whole-body");
            let me = app.world_mut().spawn((PlayerLoadout(lo), PlayerItems(items), Controlled)).id();
            {
                let mut s = app.world_mut().resource_mut::<Settings>();
                s.hud.hold_toggle = HoldToggle::Toggle;
                s.gameplay.auto_sprint = auto_sprint;
            }
            let sprint = |held: u16| held & Buttons::SPRINT != 0;
            // toggle sprint on (Alt) while running forward
            assert!(sprint(frame(&mut app, &[KeyCode::KeyW, KeyCode::AltLeft], Vec2::ZERO).0));
            assert!(sprint(frame(&mut app, &[KeyCode::KeyW], Vec2::ZERO).0), "toggled on");
            // B opens the heal ring; push the cursor up onto the first item
            let tuning = crate::settings::embedded().radial;
            let up = crate::radial::option_offset(0, kit, Radial::new(kit, &tuning).reach);
            assert!(sprint(frame(&mut app, &[KeyCode::KeyW, KeyCode::KeyB], up).0), "the ring is open, still running");
            assert!(app.world().resource::<LocalControl>().heal.is_some());
            // click: the pick goes out without SPRINT, and the toggle is off
            app.world_mut().resource_mut::<ButtonInput<MouseButton>>().press(MouseButton::Left);
            let (held, ..) = frame(&mut app, &[KeyCode::KeyW], Vec2::ZERO);
            {
                let mut mouse = app.world_mut().resource_mut::<ButtonInput<MouseButton>>();
                mouse.release_all();
                mouse.clear();
            }
            let c = app.world().resource::<LocalControl>();
            assert_eq!(c.item_pick, encode_pick(0, None), "auto-sprint {auto_sprint}: the item is picked");
            assert!(!sprint(held) && !c.toggles.sprint, "auto-sprint {auto_sprint}: no sprint with the pick");
            // the item starts (the next tick sends the pick): running on keeps it, as auto-sprint waits
            app.world_mut().resource_mut::<LocalControl>().item_pick = (0, 0);
            let using = ItemUse { slot: 0, zone: None, left: 100, total: 100 };
            app.world_mut().get_mut::<PlayerItems>(me).unwrap().0.using = Some(using);
            assert!(!sprint(frame(&mut app, &[KeyCode::KeyW], Vec2::ZERO).0), "auto-sprint {auto_sprint}: healing");
            // pressing Sprint sprints (and cancels the item on purpose), and stays toggled
            assert!(sprint(frame(&mut app, &[KeyCode::KeyW, KeyCode::AltLeft], Vec2::ZERO).0));
            assert!(sprint(frame(&mut app, &[KeyCode::KeyW], Vec2::ZERO).0), "auto-sprint {auto_sprint}: toggled");
        }
    }

    /// `--demo-ui ads` holds aim down sights every frame, for a player and for a `--bot` (review finding: the
    /// bot path skips the keyboard input, so a bot run stopped aiming).
    #[test]
    fn demo_ui_ads_holds_aim_for_players_and_bots() {
        let ads = || Some("ads".to_string());
        let mut app = input_app();
        app.insert_resource(Cli { demo_ui: ads(), ..Cli::default() });
        for _ in 0..3 {
            assert_ne!(frame(&mut app, &[], Vec2::ZERO).0 & Buttons::ADS, 0, "a player run aims");
        }
        app.insert_resource(Cli::default());
        assert_eq!(frame(&mut app, &[], Vec2::ZERO).0 & Buttons::ADS, 0, "no demo, no aim");

        let bot = Cli { bot: true, demo_ui: ads(), ..Cli::default() };
        let mut c = LocalControl::default();
        let mut fired = false;
        for i in 0..40 {
            let t = i as f32 * 0.25;
            bot_controls(&bot, t, t, &mut c);
            assert_ne!(c.held & Buttons::ADS, 0, "the bot aims at {t} s");
            fired |= c.held & Buttons::FIRE != 0;
        }
        assert!(fired, "and still fires its bursts");
        bot_controls(&Cli { bot: true, ..Cli::default() }, 1.0, 1.0, &mut c);
        assert_eq!(c.held & Buttons::ADS, 0, "a plain bot run does not aim");
        let sprint_ads = Cli { bot: true, demo_ui: Some("sprint-ads".into()), ..Cli::default() };
        bot_controls(&sprint_ads, 1.0, 1.0, &mut c);
        assert_eq!(c.held & (Buttons::SPRINT | Buttons::ADS), Buttons::SPRINT | Buttons::ADS, "an aimed sprint");
        // the sprinting dry-fire demo: sprint held, the trigger only tapped (a tenth of a second every 1.5 s)
        let taps =
            Cli { bot: true, host: Some("range".into()), demo_ui: Some("dry-fire-sprint".into()), ..Cli::default() };
        let firing: Vec<bool> = (0..300)
            .map(|i| {
                let t = i as f32 / 100.0;
                bot_controls(&taps, t, t, &mut c);
                assert_ne!(c.held & Buttons::SPRINT, 0, "sprinting at {t} s");
                c.held & Buttons::FIRE != 0
            })
            .collect();
        let pulls = firing.windows(2).filter(|w| w[1] && !w[0]).count() + firing[0] as usize;
        assert_eq!((pulls, firing.iter().filter(|f| **f).count()), (2, 20), "two taps of 0.1 s in 3 s");
    }
}
