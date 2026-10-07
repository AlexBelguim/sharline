//! Local player: input, camera, recoil, client-side hit detection (shot claims) and host feedback.
//! Works the same for the host's own player and for a remote client.

use crate::AppState;
use crate::config::{Cli, CurrentLevel, Data, level_by_name};
use crate::net::{NetRequest, Role, Session};
use crate::radial::{HealMenu, HealOption, REGION_ORDER, RELOAD_HOLD_S, Radial, heal_options};
use crate::shared::LocalShot;
use bevy::input::mouse::AccumulatedMouseMotion;
use bevy::prelude::*;
use bevy::render::view::screenshot::{Screenshot, save_to_disk};
use bevy::window::{CursorGrabMode, CursorOptions, PrimaryWindow};
use lightyear::prelude::client::input::InputSystems;
use lightyear::prelude::input::native::{ActionState, InputMarker};
use lightyear::prelude::*;
use std::sync::Arc;
use vetf_net::*;
use vetf_sim::hitbox::{self, HitClaim, Pose};
use vetf_sim::input::{Buttons, MAX_PITCH};
use vetf_sim::items::{ItemScope, encode_pick};
use vetf_sim::recoil::ViewRecoil;
use vetf_sim::weapon::{shot_direction, shot_seed};

pub struct ClientPlugin;

impl Plugin for ClientPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<LocalControl>()
            .init_resource::<Feedback>()
            .add_observer(on_match_state)
            .add_systems(
                RunFixedMainLoop,
                gather_input.in_set(RunFixedMainLoopSystems::BeforeFixedMainLoop).run_if(in_state(AppState::InGame)),
            )
            .add_systems(FixedPreUpdate, write_inputs.in_set(InputSystems::WriteClientInputs))
            .add_systems(FixedPostUpdate, record_smoothing)
            .add_systems(Update, wait_for_player.run_if(in_state(AppState::Connecting)))
            .add_systems(OnEnter(AppState::InGame), (reset_control, grab_cursor))
            .add_systems(OnExit(AppState::InGame), release_cursor)
            .add_systems(
                Update,
                (toggle_pause, fire_claims, recoil_recovery, receive_feedback, tick_feedback)
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
    pub sensitivity: f32,
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
    /// The heal ring, while open (H).
    pub heal: Option<HealMenu>,
    /// An item picked on the heal ring (kit slot 1..=8, region 0..=4), sent with the next tick's input.
    pub item_pick: (u8, u8),
    /// After a ring menu closes, the mouse buttons stay off until released (the click that picked must
    /// not fire the gun or cancel the item).
    pub mouse_block: bool,
}

impl Default for LocalControl {
    fn default() -> Self {
        Self {
            yaw: 0.0,
            pitch: 0.0,
            movement: Vec2::ZERO,
            held: 0,
            latched: 0,
            sensitivity: 0.0022,
            recoil: ViewRecoil::default(),
            paused: false,
            punch: 0.0,
            reload_held_s: None,
            reload_radial: None,
            reload_pick: 0,
            heal: None,
            item_pick: (0, 0),
            mouse_block: false,
        }
    }
}

/// Things the HUD shows briefly.
#[derive(Resource, Default)]
pub struct Feedback {
    pub hit_marker: Option<(HitKind, f32)>,
    /// (world position the damage came from, seconds left)
    pub damage: Vec<(Vec3, f32)>,
    /// (killer, victim, headshot, seconds left)
    pub kills: Vec<(String, String, bool, f32)>,
    /// Tracers to draw: (from, to, seconds left, own shot)
    pub tracers: Vec<(Vec3, Vec3, f32, bool)>,
}

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
    *control = LocalControl { yaw, pitch: look.pitch, sensitivity: control.sensitivity, ..default() };
}

fn grab_cursor(mut cursor: Query<&mut CursorOptions, With<PrimaryWindow>>) {
    for mut c in &mut cursor {
        c.visible = false;
        c.grab_mode = CursorGrabMode::Locked;
    }
}

fn release_cursor(mut cursor: Query<&mut CursorOptions, With<PrimaryWindow>>) {
    for mut c in &mut cursor {
        c.visible = true;
        c.grab_mode = CursorGrabMode::None;
    }
}

fn toggle_pause(
    keys: Res<ButtonInput<KeyCode>>,
    mut control: ResMut<LocalControl>,
    mut cursor: Query<&mut CursorOptions, With<PrimaryWindow>>,
) {
    if keys.just_pressed(KeyCode::Escape) {
        // Esc closes an open ring menu first (and forgets a reload hold, so it does not reopen).
        let heal = control.heal.take().is_some();
        let radial = control.reload_radial.take().is_some();
        if heal || radial {
            control.reload_held_s = None;
            control.mouse_block = true;
            return;
        }
        control.paused = !control.paused;
        for mut c in &mut cursor {
            c.visible = control.paused;
            c.grab_mode = if control.paused { CursorGrabMode::None } else { CursorGrabMode::Locked };
        }
    }
}

/// Keyboard + mouse into [`LocalControl`] (every frame, before the fixed ticks).
fn gather_input(
    keys: Res<ButtonInput<KeyCode>>,
    mouse: Res<ButtonInput<MouseButton>>,
    motion: Res<AccumulatedMouseMotion>,
    time: Res<Time>,
    cli: Res<Cli>,
    data: Res<Data>,
    me: Query<(&PlayerLoadout, &PlayerItems, Option<&Vitals>), With<Controlled>>,
    mut control: ResMut<LocalControl>,
) {
    if cli.bot {
        return;
    }
    if control.paused {
        control.movement = Vec2::ZERO;
        control.held = 0;
        control.reload_held_s = None;
        control.reload_radial = None;
        control.heal = None;
        return;
    }
    let me = me.iter().next();
    // No ring menus while dead.
    if me.is_some_and(|(.., v)| v.is_some_and(|v| v.health.dead)) {
        control.heal = None;
        control.reload_radial = None;
        control.reload_held_s = None;
    }
    let mags = me.map_or(1, |(l, ..)| l.0.weapon.mags.len());
    let kit: Vec<HealOption> = me.map(|(l, it, v)| heal_options(&data, &l.0, &it.0, v)).unwrap_or_default();
    heal_input(&mut control, &keys, &mouse, motion.delta, &kit);
    let tap_reload = control.heal.is_none() && reload_input(&mut control, &keys, motion.delta, time.delta_secs(), mags);
    if control.heal.is_some() || control.reload_radial.is_some() {
        control.mouse_block = true;
    } else if !mouse.pressed(MouseButton::Left) && !mouse.pressed(MouseButton::Right) {
        control.mouse_block = false;
    }
    if control.reload_radial.is_none() && control.heal.is_none() {
        let ads_scale = if control.held & Buttons::ADS != 0 { 0.6 } else { 1.0 };
        let s = control.sensitivity * ads_scale;
        control.yaw = (control.yaw - motion.delta.x * s).rem_euclid(std::f32::consts::TAU);
        control.pitch = (control.pitch - motion.delta.y * s).clamp(-MAX_PITCH, MAX_PITCH);
    }

    let axis = |neg: KeyCode, pos: KeyCode| (keys.pressed(pos) as i32 - keys.pressed(neg) as i32) as f32;
    control.movement = Vec2::new(axis(KeyCode::KeyA, KeyCode::KeyD), axis(KeyCode::KeyS, KeyCode::KeyW));

    let mut held = 0u16;
    let mut set = |bit: u16, on: bool| {
        if on {
            held |= bit;
        }
    };
    set(Buttons::JUMP, keys.pressed(KeyCode::Space));
    set(Buttons::CROUCH, keys.pressed(KeyCode::ControlLeft) || keys.pressed(KeyCode::KeyC));
    set(Buttons::SPRINT, keys.pressed(KeyCode::ShiftLeft));
    set(Buttons::WALK, keys.pressed(KeyCode::AltLeft));
    let mouse_free = !control.mouse_block;
    set(Buttons::FIRE, mouse_free && mouse.pressed(MouseButton::Left));
    set(Buttons::ADS, mouse_free && mouse.pressed(MouseButton::Right));
    set(Buttons::MAG_CHECK, keys.pressed(KeyCode::KeyT));
    set(Buttons::FIRE_MODE, keys.pressed(KeyCode::KeyB));
    set(Buttons::INTERACT, keys.pressed(KeyCode::KeyF));
    control.latched |= held & !control.held;
    control.held = held;
    if tap_reload {
        control.latched |= Buttons::RELOAD;
    }
}

/// Heal ring (H toggles it). Click an item: a whole-body item is used at once; a region item opens a second
/// ring of regions around it, where a click picks the region. Right click steps back; Esc or H closes.
/// Dimmed options (none left, or nothing to treat) ignore clicks.
fn heal_input(
    control: &mut LocalControl,
    keys: &ButtonInput<KeyCode>,
    mouse: &ButtonInput<MouseButton>,
    mouse_delta: Vec2,
    kit: &[HealOption],
) {
    if keys.just_pressed(KeyCode::KeyH) {
        control.heal = match control.heal {
            Some(_) => None,
            None if !kit.is_empty() => Some(HealMenu::new(kit.len())),
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
    if mouse.just_pressed(MouseButton::Right) {
        if menu.item.take().is_none() {
            control.heal = None;
        }
        return;
    }
    if !mouse.just_pressed(MouseButton::Left) {
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
                }
                ItemScope::Region => {
                    menu.item = Some(i);
                    menu.regions = Radial::new(REGION_ORDER.len());
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
        }
    }
}

/// Reload key: a tap (released before [`RELOAD_HOLD_S`]) reloads the next magazine in slot order; holding
/// opens the magazine radial, and releasing over a slot picks it (number keys 1-6 pick directly while it is
/// open). Returns true on a tap.
fn reload_input(
    control: &mut LocalControl,
    keys: &ButtonInput<KeyCode>,
    mouse_delta: Vec2,
    dt: f32,
    mags: usize,
) -> bool {
    const DIGITS: [KeyCode; 6] =
        [KeyCode::Digit1, KeyCode::Digit2, KeyCode::Digit3, KeyCode::Digit4, KeyCode::Digit5, KeyCode::Digit6];
    if keys.just_pressed(KeyCode::KeyR) {
        control.reload_held_s = Some(0.0);
    }
    if keys.pressed(KeyCode::KeyR)
        && let Some(held) = &mut control.reload_held_s
    {
        *held += dt;
        if *held >= RELOAD_HOLD_S && control.reload_radial.is_none() {
            control.reload_radial = Some(Radial::new(mags));
        }
        if let Some(radial) = &mut control.reload_radial {
            radial.steer(mouse_delta);
            if let Some(i) = DIGITS.iter().take(mags).position(|k| keys.just_pressed(*k)) {
                control.reload_pick = i as u8 + 1;
                control.reload_radial = None;
                control.reload_held_s = None;
            }
        }
    }
    if !keys.just_released(KeyCode::KeyR) {
        return false;
    }
    let was_held = control.reload_held_s.take().is_some();
    match control.reload_radial.take() {
        Some(radial) => {
            if let Some(i) = radial.selected() {
                control.reload_pick = i as u8 + 1;
            }
            false
        }
        None => was_held,
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
    level: Option<Res<CurrentLevel>>,
    session: Res<Session>,
    timeline: Res<LocalTimeline>,
    interp: Option<Res<InterpolationTimeline>>,
    me: Query<(&PlayerLoadout, &PlayerInfo), With<Controlled>>,
    others: Query<(&PlayerId, &PlayerInfo, &PlayerMove, &PlayerLook, &Vitals), Without<Controlled>>,
    mut senders: Query<&mut MessageSender<ShotClaim>, With<Client>>,
    mut control: ResMut<LocalControl>,
    mut feedback: ResMut<Feedback>,
) {
    let Some(level) = level else { return };
    let Some((loadout, my_info)) = me.iter().next() else { return };
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
        if let vetf_sim::data::RecoilSpec::Pattern(p) = &spec.recoil {
            control.punch = p.view_punch_visual_deg;
        }

        let dir = shot_direction(s.yaw, s.pitch, s.shot.spread_deg, shot_seed(s.player, s.shot.seq));
        let range = spec.max_range_m;
        let world_t = level.world.raycast(s.origin, dir, range).map_or(range, |(d, _)| d);
        let mut best: Option<(u64, vetf_sim::Zone, f32)> = None;
        for (id, info, mv, look, vitals) in &others {
            if vitals.health.dead || (my_info.team.is_some() && info.team == my_info.team) {
                continue;
            }
            let pose = Pose { pos: mv.0.pos, yaw: look.yaw, stance: mv.0.stance };
            if let Some((zone, t)) = hitbox::raycast(&data, &pose, s.origin, dir, world_t)
                && best.is_none_or(|b| t < b.2)
            {
                best = Some((id.0, zone, t));
            }
        }
        debug!("local shot {} spread {:.2} hit {:?} (world at {world_t:.1} m)", s.shot.seq, s.shot.spread_deg, best);
        let end_t = best.map_or(world_t, |b| b.2);
        let muzzle = s.origin + dir * 0.6 + Vec3::new(0.0, -0.12, 0.0);
        feedback.tracers.push((muzzle, s.origin + dir * end_t, 0.08, true));
        if let Some((victim, zone, t)) = best {
            let hit = HitClaim { origin: s.origin, dir, view_tick, zone, point: s.origin + dir * t };
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
    control.punch = (control.punch - dt * 2.0).max(0.0);
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
    mut feedback: ResMut<Feedback>,
) {
    let name = |id: u64| {
        players.iter().find(|(p, _)| p.0 == id).map(|(_, i)| i.name.clone()).unwrap_or_else(|| format!("{id:x}"))
    };
    for mut rx in &mut hits {
        for h in rx.receive() {
            debug!("hit confirmed: {:?} {:?}", h.zone, h.kind);
            feedback.hit_marker = Some((h.kind, 0.25));
        }
    }
    for mut rx in &mut damage {
        for d in rx.receive() {
            feedback.damage.push((d.from, 1.2));
        }
    }
    for mut rx in &mut kills {
        for k in rx.receive() {
            debug!("kill feed: {:?} -> {:x}", k.killer, k.victim);
            let killer = k.killer.map(name).unwrap_or_default();
            feedback.kills.push((killer, name(k.victim), k.zone == Some(vetf_sim::Zone::Head), 6.0));
        }
    }
    for mut rx in &mut fx {
        for s in rx.receive() {
            feedback.tracers.push((s.origin, s.end, 0.08, false));
        }
    }
}

fn tick_feedback(time: Res<Time>, mut feedback: ResMut<Feedback>) {
    let dt = time.delta_secs();
    if let Some((_, t)) = &mut feedback.hit_marker {
        *t -= dt;
        if *t <= 0.0 {
            feedback.hit_marker = None;
        }
    }
    feedback.damage.retain_mut(|(_, t)| {
        *t -= dt;
        *t > 0.0
    });
    feedback.kills.retain_mut(|(.., t)| {
        *t -= dt;
        *t > 0.0
    });
    feedback.tracers.retain_mut(|(.., t, _)| {
        *t -= dt;
        *t > 0.0
    });
    if feedback.kills.len() > 5 {
        let n = feedback.kills.len() - 5;
        feedback.kills.drain(..n);
    }
}

/// `--bot`, `--screenshot` and `--exit-after` for automated runs.
fn automation(
    cli: Res<Cli>,
    time: Res<Time>,
    state: Res<State<AppState>>,
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
        let since = t - in_game_since.unwrap_or(t);
        // Wander, look around and fire short bursts.
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
        let firing = (t * 2.0) as i32 % 3 == 0 && (cli.yaw.is_none() || since > 3.5);
        control.held = if firing { Buttons::FIRE } else { 0 };
        if (t as i32) % 7 == 3 && cli.yaw.is_none() {
            control.held |= Buttons::JUMP;
        }
        // Tap reload now and then (a full magazine ignores it).
        if (t as i32) % 5 == 4 {
            control.latched |= Buttons::RELOAD;
        }
    }
    // Open a ring menu for screenshots.
    if let Some(demo) = cli.demo_ui.as_deref()
        && in_game_since.is_some_and(|s| t - s > 1.0)
        && let Some((lo, _)) = me.iter().next()
    {
        match demo {
            "reload" => {
                let mut radial = Radial::new(lo.0.weapon.mags.len());
                radial.steer(Vec2::new(40.0, -12.0));
                control.reload_radial = Some(radial);
            }
            // The HUD with wounds (see server::demo_wounds) and a mag check card.
            "hud" if !*demo_checked && t - in_game_since.unwrap_or(t) > 1.5 => {
                *demo_checked = true;
                control.latched |= Buttons::MAG_CHECK;
            }
            "heal" | "heal-region" => {
                let mut menu = HealMenu::new(lo.0.kit.len());
                menu.ring.steer(Vec2::new(30.0, -40.0));
                if demo == "heal-region" {
                    menu.item = menu.ring.selected();
                    menu.regions.steer(Vec2::new(0.0, 40.0));
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
