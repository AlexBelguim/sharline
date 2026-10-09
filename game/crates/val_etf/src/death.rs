//! The death screen (user direction 2026-10-09, after `design/ui/mockups/death.html`): when the local player
//! dies in a live match (team deathmatch, free-for-all, the gun range) it shows
//! - the death cam, no replay: the view stays where you died and turns to look at your killer (their live
//!   position while you can see them, else the last spot you saw them at, else where the killing shot came
//!   from), zoomed in to frame them;
//! - who killed you with what and from how far, and their health and halo left as a rough read (never numbers);
//! - the recap of that life (the host's [`LifeRecap`], item 9-pre), drawn rather than tabled: your kills as
//!   icons (a headshot or a body kill, with the victim's name), YOUR LAST FIGHT (each opponent you hit in the
//!   last few seconds and did not kill, as a silhouette lit where you hit them, with your total damage and the
//!   part of it their halo took: never what they have left), and the damage you took per attacker as bars
//!   (gun, total, the part your halo took, distance). No per-zone numbers anywhere. Damage dealt is per
//!   opponent LIFE: an opponent who died and came back is a new encounter;
//! - LOADOUT (the Loadout screen over this one) and RESPAWN with the match's respawn timer (`rules.ron`
//!   `respawn_s`): it becomes active at 0 and respawns you on a click, Enter or Space. A player who never
//!   presses it is respawned by the host `auto_respawn_s` later.
//!
//! It is [`Screen::Death`], at the bottom of the stack while the host says we wait to respawn
//! (`Vitals::awaiting_respawn`), so the match takes no input and the pointer is free. Esc opens the ESC menu
//! over it. Layout, timings and the rough-read words: `game/assets/data/death_screen.ron`.

use crate::AppState;
use crate::client::{Feedback, LocalControl};
use crate::config::{Cli, CurrentLevel, Data};
use crate::screens::{EscPress, EscSystems, Screen, ScreenRoot, Screens, screen_on_top};
use crate::settings::Settings;
use crate::ui_kit::*;
use bevy::prelude::*;
use bevy::ui::{ColorStop, RadialGradient, RadialGradientShape, UiPosition};
use lightyear::prelude::*;
use serde::Deserialize;
use std::sync::OnceLock;
use vetf_net::*;
use vetf_sim::input::MAX_PITCH;
use vetf_sim::movement::collision::CollisionWorld;
use vetf_sim::{GameData, Zone};

pub struct DeathScreenPlugin;

impl Plugin for DeathScreenPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(DeathScreenData::load())
            .init_resource::<DeathState>()
            .init_resource::<DeathView>()
            .add_systems(OnEnter(AppState::InGame), reset)
            .add_systems(
                Update,
                (
                    receive_recaps,
                    follow_death,
                    spawn_root,
                    keep_esc.in_set(EscSystems::Top).run_if(screen_on_top(Screen::Death)),
                    actions,
                    bot_respawn,
                    track_killer,
                    refresh,
                    rebuild_recap,
                )
                    .chain()
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

// ---------------------------------------------------------------------------------------------- data

/// `death_screen.ron`.
#[derive(Resource, Debug, Clone, PartialEq, Deserialize)]
pub struct DeathScreenData {
    pub cam: CamSpec,
    pub layout: LayoutSpec,
    pub recap: RecapSpec,
    pub reads: Reads,
}

/// What the recap shows (`death_screen.ron` `recap`).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct RecapSpec {
    /// YOUR LAST FIGHT: the opponents hit in this many seconds before the death (and not killed).
    pub last_fight_s: f32,
    pub fight_cards: usize,
    pub fight_cols: usize,
    pub kills_shown: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct CamSpec {
    pub turn_rate: f32,
    pub zoom_rate: f32,
    pub aim_height: f32,
    pub frame_height_m: f32,
    pub min_fov_deg: f32,
    pub sight_slack_m: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct LayoutSpec {
    pub margin_x: f32,
    pub title_top: f32,
    pub killer_top: f32,
    pub killer_w: f32,
    pub recap_top: f32,
    pub recap_w: f32,
    pub recap_rows: usize,
    pub col_player: f32,
    pub col_weapon: f32,
    pub col_bar_min: f32,
    pub col_damage: f32,
    pub col_range: f32,
    pub respawn_bottom: f32,
    pub min_centre_w: f32,
}

impl LayoutSpec {
    /// DAMAGE YOU TOOK's fixed columns: player, weapon, total, shield, distance (the bar takes the rest).
    fn fixed_columns(&self) -> [f32; 5] {
        [self.col_player, self.col_weapon, self.col_damage, self.col_damage, self.col_range]
    }

    /// The width inside the recap panel.
    fn recap_inner(&self) -> f32 {
        self.recap_w - 2.0 * Self::RECAP_PAD - 2.0
    }

    /// Horizontal padding inside the recap panel.
    const RECAP_PAD: f32 = 20.0;
    /// Gap between the recap's cards and tiles.
    const GAP: f32 = 10.0;
}

/// The killer's health and halo as a rough read (see [`Reads::read`]).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct Reads {
    pub segments: u32,
    pub health: Vec<(f32, String)>,
    pub halo: Vec<(f32, String)>,
}

impl Reads {
    /// A share left (0..1) as lit pips of [`Reads::segments`] (any share left lights at least one) and the
    /// word of the first threshold it reaches in `words`: never a number.
    pub fn read<'a>(&self, words: &'a [(f32, String)], frac: f32) -> (u32, &'a str) {
        let frac = if frac.is_finite() { frac.clamp(0.0, 1.0) } else { 0.0 };
        let pips = if frac <= 0.0 { 0 } else { ((frac * self.segments as f32).ceil() as u32).clamp(1, self.segments) };
        let word = words.iter().find(|(t, _)| frac >= *t).or(words.last()).map_or("", |(_, w)| w.as_str());
        (pips, word)
    }
}

const EMBEDDED: &str = include_str!("../../../assets/data/death_screen.ron");

impl DeathScreenData {
    /// The copy compiled into the binary.
    pub fn embedded() -> &'static DeathScreenData {
        static DATA: OnceLock<DeathScreenData> = OnceLock::new();
        DATA.get_or_init(|| ron::from_str(EMBEDDED).expect("game/assets/data/death_screen.ron is valid"))
    }

    /// From the data folder (so it can be tuned without a rebuild), else the built-in copy.
    pub fn load() -> DeathScreenData {
        let path = crate::config::assets_root().join("data").join("death_screen.ron");
        match std::fs::read_to_string(&path).map(|text| ron::from_str(&text)) {
            Ok(Ok(d)) => d,
            Ok(Err(e)) => {
                error!("{} is invalid ({e}); using the built-in copy", path.display());
                Self::embedded().clone()
            }
            Err(_) => Self::embedded().clone(),
        }
    }
}

// ---------------------------------------------------------------------------------------------- death cam

/// What this client sees of the killer now.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct KillerSight {
    /// Where to look on them (their chest).
    pub at: Vec3,
    pub alive: bool,
    /// Nothing that stops bullets lies between our eye and them.
    pub visible: bool,
}

/// The death cam's memory: the last spot it saw the killer at.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct DeathCam {
    pub last_known: Option<Vec3>,
}

impl DeathCam {
    /// Where to look: the killer's live position while they are alive and in view (remembered), else the last
    /// spot they were seen at, else where the killing shot came from (`shot_from`), else nowhere (the view
    /// stays as it is). Never a replay: only where things are now, or were last seen.
    pub fn target(&mut self, killer: Option<KillerSight>, shot_from: Option<Vec3>) -> Option<Vec3> {
        match killer {
            Some(k) if k.alive && k.visible => {
                self.last_known = Some(k.at);
                Some(k.at)
            }
            _ => self.last_known.or(shot_from),
        }
    }
}

/// The view angles (yaw, pitch; `vetf_sim::input::view_dir`'s convention) from `eye` to `target`.
pub fn look_at(eye: Vec3, target: Vec3) -> Option<(f32, f32)> {
    let d = target - eye;
    let len = d.length();
    if !len.is_finite() || len < 1e-3 {
        return None;
    }
    let d = d / len;
    Some((f32::atan2(-d.x, -d.z), d.y.clamp(-1.0, 1.0).asin().clamp(-MAX_PITCH, MAX_PITCH)))
}

/// `cur` eased toward `want` at `rate` (the share of the gap closed per second is 1 - e^-rate), at the same
/// speed at any frame rate.
pub fn approach(cur: f32, want: f32, rate: f32, dt: f32) -> f32 {
    cur + (want - cur) * (1.0 - (-rate.max(0.0) * dt.max(0.0)).exp())
}

/// (yaw, pitch) turned toward `want`, the short way round.
pub fn turn_toward(cur: (f32, f32), want: (f32, f32), rate: f32, dt: f32) -> (f32, f32) {
    use std::f32::consts::{PI, TAU};
    let dy = (want.0 - cur.0 + PI).rem_euclid(TAU) - PI;
    let yaw = approach(0.0, dy, rate, dt) + cur.0;
    (yaw.rem_euclid(TAU), approach(cur.1, want.1, rate, dt))
}

/// The vertical FOV (degrees) that shows `cam.frame_height_m` around someone `dist` metres away, between
/// `cam.min_fov_deg` and `widest` (the normal view).
pub fn frame_fov(cam: &CamSpec, dist: f32, widest: f32) -> f32 {
    let fov = (2.0 * (cam.frame_height_m * 0.5 / dist.max(0.1)).atan()).to_degrees();
    fov.clamp(cam.min_fov_deg.min(widest), widest)
}

/// Is `at` in view from `eye`? Nothing that stops bullets lies on the line, up to `slack` short of it.
pub fn in_sight(world: &CollisionWorld, eye: Vec3, at: Vec3, slack: f32) -> bool {
    let d = at - eye;
    let len = d.length();
    if len <= slack {
        return true;
    }
    world.line_of_sight(eye, eye + d / len * (len - slack))
}

/// The view while dead, for `render::update_camera`: `None` while alive or before the death screen starts.
#[derive(Resource, Debug, Clone, Copy, Default, PartialEq)]
pub struct DeathView(pub Option<DeathAngles>);

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DeathAngles {
    pub yaw: f32,
    pub pitch: f32,
    /// Vertical FOV, degrees.
    pub fov_deg: f32,
}

// ---------------------------------------------------------------------------------------------- state

/// This death, on this client.
#[derive(Resource, Debug, Default)]
pub struct DeathState {
    /// The host's recap of the life that ended (it may arrive a moment after the death).
    pub recap: Option<LifeRecap>,
    pub cam: DeathCam,
    /// The local player is dead and waiting to respawn (the death screen is up).
    pub dead: bool,
    /// RESPAWN was sent for this death.
    pub asked: bool,
    /// The recap the tables show.
    shown: Option<LifeRecap>,
}

fn reset(mut state: ResMut<DeathState>, mut view: ResMut<DeathView>) {
    *state = DeathState::default();
    *view = DeathView::default();
}

/// The host's recaps (its own player's arrive in its in-process client the same way).
fn receive_recaps(mut rx: Query<&mut MessageReceiver<LifeRecap>, With<Client>>, mut state: ResMut<DeathState>) {
    for mut r in &mut rx {
        for recap in r.receive() {
            debug!(
                "life recap: killer {:?}, {} attackers, {} encounters, {} kills",
                recap.killer,
                recap.taken.len(),
                recap.dealt.len(),
                recap.kills.len()
            );
            state.recap = Some(recap);
        }
    }
}

/// The screen follows the host: up while we wait to respawn in a live match, gone once we are back (screens
/// opened over it, such as a LOADOUT still being edited, stay open). The lobby takes over the whole stack
/// instead, and the end board shows once the match is over.
fn follow_death(
    me: Query<&Vitals, With<Controlled>>,
    matches: Query<&MatchState>,
    control: Res<LocalControl>,
    settings: Res<Settings>,
    mut screens: ResMut<Screens>,
    mut state: ResMut<DeathState>,
    mut view: ResMut<DeathView>,
) {
    let live = matches.iter().next().is_none_or(|m| m.phase == MatchPhase::Live);
    let dead = live && me.iter().next().is_some_and(|v| v.health.dead && v.awaiting_respawn);
    if dead && !state.dead {
        state.dead = true;
        state.asked = false;
        state.cam = DeathCam::default();
        // The cam starts from the view at the moment of death.
        let fov = crate::render::camera_fov(&settings.mouse, 1.0, 0.0);
        view.0 = Some(DeathAngles { yaw: control.yaw, pitch: control.pitch, fov_deg: fov });
    } else if !dead && state.dead {
        state.dead = false;
        state.recap = None;
        state.shown = None;
        view.0 = None;
    }
    let lobby = screens.contains(Screen::Lobby);
    if state.dead && !lobby && !screens.contains(Screen::Death) {
        screens.insert_base(Screen::Death);
    } else if (!state.dead || lobby) && screens.contains(Screen::Death) {
        screens.remove(Screen::Death);
    }
}

/// Esc over the death screen opens the ESC menu (leave, settings); it never closes the death screen.
fn keep_esc(mut esc: ResMut<EscPress>, mut screens: ResMut<Screens>) {
    if esc.take() {
        screens.push(Screen::Esc);
    }
}

/// Send RESPAWN once per death.
pub(crate) fn ask_respawn(
    state: &mut DeathState,
    senders: &mut Query<&mut MessageSender<RespawnRequest>, With<Client>>,
) {
    if state.asked {
        return;
    }
    state.asked = true;
    info!("respawn requested");
    for mut s in senders.iter_mut() {
        s.send::<ReliableChannel>(RespawnRequest);
    }
}

/// Seconds until RESPAWN can be pressed (0: now).
pub(crate) fn respawn_left(v: &Vitals) -> f32 {
    v.respawn_s.max(0.0)
}

/// RESPAWN (click, Enter, Space once the timer is out) and LOADOUT (click, L), while the death screen is on top.
fn actions(
    btns: Query<(&Interaction, &DeathBtn), Changed<Interaction>>,
    keys: Res<ButtonInput<KeyCode>>,
    me: Query<&Vitals, With<Controlled>>,
    mut screens: ResMut<Screens>,
    mut state: ResMut<DeathState>,
    mut senders: Query<&mut MessageSender<RespawnRequest>, With<Client>>,
    mut was_top: Local<bool>,
) {
    // Keys count only when the screen was on top the frame before too: the Enter that closed the ESC menu
    // over it must not respawn as well.
    let top = screens.top() == Some(Screen::Death) && state.dead;
    let keys_on = std::mem::replace(&mut *was_top, top);
    if !top {
        return;
    }
    let ready = me.iter().next().is_some_and(|v| respawn_left(v) <= 0.0);
    let mut act = btns.iter().find(|(i, _)| **i == Interaction::Pressed).map(|(_, b)| *b);
    if keys_on && keys.any_just_pressed([KeyCode::Enter, KeyCode::NumpadEnter, KeyCode::Space]) {
        act = Some(DeathBtn::Respawn);
    } else if keys_on && keys.just_pressed(KeyCode::KeyL) {
        act = Some(DeathBtn::Loadout);
    }
    match act {
        Some(DeathBtn::Respawn) if ready => ask_respawn(&mut state, &mut senders),
        Some(DeathBtn::Loadout) => screens.push(Screen::Loadout),
        _ => {}
    }
}

/// `--bot` has nobody to press RESPAWN: it asks as soon as it may.
fn bot_respawn(
    cli: Res<Cli>,
    me: Query<&Vitals, With<Controlled>>,
    mut state: ResMut<DeathState>,
    mut senders: Query<&mut MessageSender<RespawnRequest>, With<Client>>,
) {
    if cli.bot && state.dead && me.iter().next().is_some_and(|v| respawn_left(v) <= 0.0) {
        ask_respawn(&mut state, &mut senders);
    }
}

/// The death cam: turn toward the killer (see [`DeathCam::target`]) and zoom to frame them.
#[allow(clippy::too_many_arguments)]
fn track_killer(
    time: Res<Time>,
    data: Res<DeathScreenData>,
    settings: Res<Settings>,
    feedback: Res<Feedback>,
    level: Option<Res<CurrentLevel>>,
    me: Query<&PlayerMove, With<Controlled>>,
    players: Query<(&PlayerId, &PlayerMove, &Vitals), Without<Controlled>>,
    mut state: ResMut<DeathState>,
    mut view: ResMut<DeathView>,
) {
    let (Some(angles), Some(mv)) = (view.0, me.iter().next()) else { return };
    let cam = data.cam;
    let eye = mv.0.eye_pos();
    let killer = state.recap.as_ref().and_then(|r| r.killer);
    let sight = killer.and_then(|k| players.iter().find(|(id, ..)| id.0 == k)).map(|(_, kmv, kv)| {
        let at = kmv.0.pos + Vec3::Y * kmv.0.eye * cam.aim_height;
        let visible = level.as_ref().is_none_or(|l| in_sight(&l.world, eye, at, cam.sight_slack_m));
        KillerSight { at, alive: !kv.health.dead, visible }
    });
    // Before the recap arrives: where the last damage came from.
    let shot_from = state
        .recap
        .as_ref()
        .and_then(LifeRecap::shot_from)
        .or_else(|| feedback.damage.iter().max_by(|a, b| a.1.total_cmp(&b.1)).map(|(from, _)| *from));
    let target = state.cam.target(sight, shot_from);
    let dt = time.delta_secs();
    let widest = crate::render::camera_fov(&settings.mouse, 1.0, 0.0);
    let mut next = angles;
    if let Some(at) = target
        && let Some(want) = look_at(eye, at)
    {
        (next.yaw, next.pitch) = turn_toward((angles.yaw, angles.pitch), want, cam.turn_rate, dt);
        next.fov_deg = approach(angles.fov_deg, frame_fov(&cam, eye.distance(at), widest), cam.zoom_rate, dt);
    } else {
        next.fov_deg = approach(angles.fov_deg, widest, cam.zoom_rate, dt);
    }
    view.0 = Some(next);
}

// ---------------------------------------------------------------------------------------------- the screen

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
enum DeathBtn {
    Loadout,
    Respawn,
}

/// The texts that follow the death.
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
enum Field {
    Title,
    Sub,
    KillerName,
    KillerWeapon,
    KillerRange,
    KillerHealth,
    KillerHalo,
    Countdown,
    RespawnTitle,
    RespawnNote,
}

/// A pip of the killer's health (`false`) or halo (`true`) read.
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
struct Pip {
    halo: bool,
    i: u32,
}

#[derive(Component)]
struct KillerCard;

/// The recap tables (rebuilt when the recap changes).
#[derive(Component)]
struct RecapBox;

/// The respawn timer's bar fill.
#[derive(Component)]
struct TimerFill;

/// Under the hub screens (100 and up, so the ESC menu and LOADOUT open over it), over the HUD and the
/// scoreboard.
const DEATH_Z: i32 = 90;

fn spawn_root(
    screens: Res<Screens>,
    roots: Query<&ScreenRoot>,
    data: Res<DeathScreenData>,
    fonts: Res<UiFonts>,
    mut commands: Commands,
) {
    if !screens.contains(Screen::Death) || roots.iter().any(|r| r.0 == Screen::Death) {
        return;
    }
    let l = &data.layout;
    let fonts = &*fonts;
    let vignette = BackgroundGradient::from(RadialGradient::new(
        UiPosition::CENTER,
        RadialGradientShape::FarthestCorner,
        vec![ColorStop::new(black(0.0), percent(35)), ColorStop::new(black(0.7), percent(100))],
    ));
    commands
        .spawn((
            ScreenRoot(Screen::Death),
            GlobalZIndex(DEATH_Z),
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
            vignette,
        ))
        .with_children(|r| {
            // ELIMINATED / BY <NAME> / weapon · distance · headshot
            r.spawn(Node {
                flex_direction: FlexDirection::Column,
                width: px(l.killer_w + 200.0),
                ..abs(Some(l.margin_x), None, Some(l.title_top), None)
            })
            .with_children(|t| {
                t.spawn(fonts.text("ELIMINATED", Face::Display, 700, 20.0, ENEMY, 0.24));
                t.spawn((Field::Title, fonts.role(TextRole::DeathName, "")));
                t.spawn((
                    Field::Sub,
                    fonts.role(TextRole::BodyL, ""),
                    Node { margin: UiRect::top(px(6)), ..default() },
                ));
            });
            killer_card(r, fonts, &data);
            r.spawn((
                RecapBox,
                panel_of(
                    PanelKind::Hi,
                    Node {
                        width: px(l.recap_w),
                        flex_direction: FlexDirection::Column,
                        padding: UiRect::axes(px(LayoutSpec::RECAP_PAD), px(18)),
                        row_gap: px(6),
                        ..abs(None, Some(l.margin_x), Some(l.recap_top), None)
                    },
                ),
            ));
            respawn_bar(r, fonts, l);
        });
}

fn killer_card(r: &mut ChildSpawnerCommands, fonts: &UiFonts, data: &DeathScreenData) {
    let l = &data.layout;
    r.spawn((
        KillerCard,
        panel_of(
            PanelKind::Killer,
            Node {
                width: px(l.killer_w),
                flex_direction: FlexDirection::Column,
                padding: UiRect::axes(px(20), px(18)),
                row_gap: px(12),
                ..abs(Some(l.margin_x), None, Some(l.killer_top), None)
            },
        ),
    ))
    .with_children(|c| {
        c.spawn(fonts.role(TextRole::H2Card, "Killer"));
        c.spawn(Node {
            display: Display::Grid,
            grid_template_columns: vec![GridTrack::px(110.0), GridTrack::flex(1.0)],
            row_gap: px(9),
            align_items: AlignItems::Center,
            ..default()
        })
        .with_children(|g| {
            let row = |g: &mut ChildSpawnerCommands, label: &str, field: Field| {
                g.spawn(fonts.role(TextRole::StatKey, label));
                g.spawn((field, fonts.role(TextRole::KvValue, "")));
            };
            row(g, "Player", Field::KillerName);
            row(g, "Weapon", Field::KillerWeapon);
            row(g, "Distance", Field::KillerRange);
            for (label, field, halo) in [("Health", Field::KillerHealth, false), ("Halo", Field::KillerHalo, true)] {
                g.spawn(fonts.role(TextRole::StatKey, label));
                g.spawn(Node { column_gap: px(10), align_items: AlignItems::Center, ..default() }).with_children(|v| {
                    v.spawn(Node { column_gap: px(3), ..default() }).with_children(|p| {
                        for i in 0..data.reads.segments {
                            p.spawn((
                                Pip { halo, i },
                                Node { width: px(22), height: px(8), ..default() },
                                BackgroundColor(W10),
                            ));
                        }
                    });
                    v.spawn((field, fonts.role(TextRole::KvValue, "")));
                });
            }
        });
    });
}

fn respawn_bar(r: &mut ChildSpawnerCommands, fonts: &UiFonts, l: &LayoutSpec) {
    r.spawn(Node {
        justify_content: JustifyContent::Center,
        ..abs(Some(0.0), Some(0.0), None, Some(l.respawn_bottom))
    })
    .with_children(|row| {
        row.spawn(Node { column_gap: px(26), align_items: AlignItems::Center, ..default() }).with_children(|b| {
            b.spawn((
                Node {
                    width: px(96),
                    height: px(96),
                    align_items: AlignItems::Center,
                    justify_content: JustifyContent::Center,
                    border: UiRect::all(px(4)),
                    border_radius: BorderRadius::all(percent(50)),
                    ..default()
                },
                BorderColor::all(W15),
                BackgroundColor(PANEL),
            ))
            .with_children(|ring| {
                ring.spawn((Field::Countdown, fonts.role(TextRole::ScoreXl, "")));
            });
            b.spawn(Node { flex_direction: FlexDirection::Column, row_gap: px(8), ..default() }).with_children(|c| {
                c.spawn((Field::RespawnTitle, fonts.role(TextRole::RespawnTitle, "")));
                // The timer as a bar under the title.
                c.spawn((Node { width: px(360), height: px(4), ..default() }, BackgroundColor(W10))).with_children(
                    |bar| {
                        bar.spawn((
                            TimerFill,
                            Node { width: percent(0), height: percent(100), ..default() },
                            BackgroundColor(TEXT_HI),
                        ));
                    },
                );
                c.spawn((Field::RespawnNote, fonts.role(TextRole::Micro, "")));
                c.spawn(Node { column_gap: px(10), margin: UiRect::top(px(4)), ..default() }).with_children(|a| {
                    a.spawn((DeathBtn::Loadout, button_with_key(fonts, "Loadout", "L", BtnKind::Normal, BtnSize::M)));
                    let looks = BtnKind::Primary.looks();
                    a.spawn((
                        DeathBtn::Respawn,
                        Button,
                        button_node(BtnSize::M),
                        BackgroundColor(looks.idle.bg),
                        BorderColor::all(looks.idle.border),
                        looks,
                        Disabled,
                        children![
                            (fonts.role_color(TextRole::Btn, "Respawn", looks.idle.ink), Ink),
                            keycap(fonts, "Space", KeyStyle::Ghost, 20.0)
                        ],
                    ));
                });
            });
        });
    });
}

/// What the killer card says about the killer.
#[derive(Debug, Clone, PartialEq)]
pub struct KillerLines {
    pub title: String,
    pub sub: String,
    pub name: String,
    pub weapon: String,
    pub range: String,
    /// (lit pips, word) of health and halo; `None` when there is nothing to read (they died or left).
    pub health: Option<(u32, String)>,
    pub halo: Option<(u32, String)>,
    /// The halo's tier, for its pips' colour (0: none).
    pub tier: u8,
    /// There is a killer to show (not a fall).
    pub card: bool,
}

/// The killer as this client knows them now: name, gun, health and halo (`None`: left the match).
pub struct KillerNow<'a> {
    pub name: &'a str,
    pub vitals: &'a Vitals,
    pub loadout: &'a vetf_sim::player::Loadout,
}

/// The title, the line under it and the killer card's values for `recap`.
pub fn killer_lines(
    game: &GameData,
    reads: &Reads,
    recap: Option<&LifeRecap>,
    killer: Option<KillerNow>,
) -> KillerLines {
    let line = recap.and_then(LifeRecap::killer_line);
    let gun = line.and_then(|l| game.weapon(&l.weapon)).map(|w| w.name.clone());
    let range = line.map(|l| format!("{:.0} m", l.range_m));
    let name = killer.as_ref().map(|k| k.name.to_uppercase());
    let headshot = recap.is_some_and(|r| r.zone == Some(Zone::Head) && r.killer.is_some());
    let (title, sub) = match (recap, &name) {
        (None, _) => (String::new(), String::new()),
        (Some(r), _) if r.killer.is_none() => {
            ("YOU DIED".into(), if r.zone == Some(Zone::Legs) { "A fall".into() } else { String::new() })
        }
        (Some(_), n) => {
            let who = n.clone().unwrap_or_else(|| "A PLAYER WHO LEFT".into());
            let mut sub: Vec<String> = [gun.clone(), range.clone()].into_iter().flatten().collect();
            if headshot {
                sub.push("headshot".into());
            }
            (format!("BY {who}"), sub.join(" · "))
        }
    };
    let (health, halo) = match &killer {
        Some(k) if !k.vitals.health.dead => {
            let hp: f32 = k.vitals.health.hp.iter().map(|(_, v)| v.max(0.0)).sum();
            let max: f32 = k.vitals.health.max.iter().map(|(_, v)| *v).sum();
            let (pips, word) = reads.read(&reads.health, if max > 0.0 { hp / max } else { 0.0 });
            let health = Some((pips, word.to_uppercase()));
            let cap = k.loadout.halo.total_capacity();
            let halo = if cap <= 0.0 {
                Some((0, "NO HALO".into()))
            } else {
                let (pips, word) = reads.read(&reads.halo, k.vitals.halo.total() / cap);
                Some((pips, format!("{} · {}", word.to_uppercase(), halo_words(game, k.loadout))))
            };
            (health, halo)
        }
        _ => (None, None),
    };
    let alive_word = match &killer {
        None if recap.is_some_and(|r| r.killer.is_some()) => "Left the match",
        Some(k) if k.vitals.health.dead => "Down since",
        _ => "",
    };
    KillerLines {
        title,
        sub,
        name: name.unwrap_or_else(|| "--".into()),
        weapon: gun.unwrap_or_else(|| "--".into()),
        range: range.unwrap_or_else(|| "--".into()),
        health: health.or_else(|| (!alive_word.is_empty()).then(|| (0, alive_word.to_uppercase()))),
        halo,
        tier: killer.as_ref().map_or(0, |k| halo_tier(game, k.loadout)),
        card: recap.is_some_and(|r| r.killer.is_some()),
    }
}

/// The halo's tier as everyone reads it: the deathmatch armor tier, else its best arc (the gun range).
fn halo_tier(game: &GameData, l: &vetf_sim::player::Loadout) -> u8 {
    let t = l.halo.tiers;
    game.rules.deathmatch_loadout.tier_of(t).unwrap_or(t.head.max(t.torso).max(t.arms).max(t.legs))
}

/// The halo as everyone reads it: its tier and weight class (`T2 · MEDIUM`).
fn halo_words(game: &GameData, l: &vetf_sim::player::Loadout) -> String {
    format!("T{} · {}", halo_tier(game, l), l.weight.label())
}

/// The respawn block's texts for `left` seconds to go (`auto_left`: until the host respawns us anyway).
pub fn respawn_lines(left: f32, auto_left: f32, asked: bool) -> (String, String, String) {
    let secs = left.max(0.0).ceil() as u32;
    if asked {
        ("0".into(), "RESPAWNING".into(), String::new())
    } else if secs > 0 {
        (secs.to_string(), format!("RESPAWN IN {secs} S"), String::new())
    } else {
        let auto = auto_left.max(0.0).ceil() as u32;
        ("0".into(), "READY TO RESPAWN".into(), format!("RESPAWNS BY ITSELF IN {auto} S"))
    }
}

#[allow(clippy::too_many_arguments)]
fn refresh(
    screens: Res<Screens>,
    data: Res<DeathScreenData>,
    game: Res<Data>,
    state: Res<DeathState>,
    matches: Query<&MatchState>,
    me: Query<&Vitals, With<Controlled>>,
    players: Query<(&PlayerId, &PlayerInfo, &Vitals, &PlayerLoadout), Without<Controlled>>,
    btns: Query<(Entity, &DeathBtn, Has<Disabled>)>,
    mut texts: Query<(&Field, &mut Text)>,
    mut pips: Query<(&Pip, &mut BackgroundColor), Without<TimerFill>>,
    mut fill: Query<&mut Node, With<TimerFill>>,
    mut card: Query<&mut Node, (With<KillerCard>, Without<TimerFill>)>,
    mut commands: Commands,
) {
    if !screens.contains(Screen::Death) {
        return;
    }
    let Some(v) = me.iter().next() else { return };
    let killer_id = state.recap.as_ref().and_then(|r| r.killer);
    let killer = killer_id.and_then(|k| players.iter().find(|(id, ..)| id.0 == k)).map(|(_, info, kv, kl)| KillerNow {
        name: info.name.as_str(),
        vitals: kv,
        loadout: &kl.0,
    });
    let lines = killer_lines(&game, &data.reads, state.recap.as_ref(), killer);
    let mode = matches.iter().next().map_or(MatchMode::Range, |m| m.mode);
    let rules = game.rules.deathmatch(mode);
    let left = respawn_left(v);
    let (count, title, note) = respawn_lines(left, rules.auto_respawn_s + v.respawn_s.min(0.0), state.asked);
    let ready = left <= 0.0 && !state.asked;
    for (field, mut text) in &mut texts {
        let want: &str = match field {
            Field::Title => &lines.title,
            Field::Sub => &lines.sub,
            Field::KillerName => &lines.name,
            Field::KillerWeapon => &lines.weapon,
            Field::KillerRange => &lines.range,
            Field::KillerHealth => lines.health.as_ref().map_or("", |h| h.1.as_str()),
            Field::KillerHalo => lines.halo.as_ref().map_or("", |h| h.1.as_str()),
            Field::Countdown => &count,
            Field::RespawnTitle => &title,
            Field::RespawnNote => &note,
        };
        if text.0 != want {
            text.0 = want.to_string();
        }
    }
    for (pip, mut bg) in &mut pips {
        let read = if pip.halo { &lines.halo } else { &lines.health };
        let lit = read.as_ref().is_some_and(|(n, _)| pip.i < *n);
        let color = if !lit {
            W10
        } else if pip.halo {
            tier_color(lines.tier.max(1))
        } else {
            HP_OK
        };
        if bg.0 != color {
            bg.0 = color;
        }
    }
    for mut node in &mut card {
        let want = if lines.card { Display::Flex } else { Display::None };
        if node.display != want {
            node.display = want;
        }
    }
    // The host's lobby setting (the mode's `rules.ron` value until it changes it).
    let total = matches.iter().next().map_or(rules.respawn_s, |m| m.settings.respawn_s).max(0.01);
    for mut node in &mut fill {
        let want = percent(((1.0 - left / total) * 100.0).clamp(0.0, 100.0));
        if node.width != want {
            node.width = want;
        }
    }
    for (e, kind, disabled) in &btns {
        if *kind == DeathBtn::Respawn && disabled == ready {
            if ready {
                commands.entity(e).remove::<Disabled>();
            } else {
                commands.entity(e).insert(Disabled);
            }
        }
    }
}

/// The recap (rebuilt when a new recap arrives): the life's numbers at a glance, KILLS THIS LIFE, YOUR LAST
/// FIGHT and DAMAGE YOU TOOK.
#[allow(clippy::too_many_arguments)]
fn rebuild_recap(
    data: Res<DeathScreenData>,
    game: Res<Data>,
    settings: Res<Settings>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    mut state: ResMut<DeathState>,
    boxes: Query<Entity, With<RecapBox>>,
    added: Query<(), Added<RecapBox>>,
    players: Query<(&PlayerId, &PlayerInfo)>,
    mut commands: Commands,
) {
    let Some(e) = boxes.iter().next() else { return };
    if state.shown == state.recap && added.is_empty() {
        return;
    }
    state.shown = state.recap.clone();
    let names =
        |id: u64| players.iter().find(|(p, _)| p.0 == id).map_or_else(|| "--".into(), |(_, i)| i.name.to_uppercase());
    let gun = |id: &str| game.weapon(id).map_or_else(|| id.to_uppercase(), |w| w.name.to_uppercase());
    let ink = RecapInk { enemy: settings.team_colors().1 };
    let (l, spec) = (data.layout, data.recap);
    let (fonts, images) = (&*fonts, &*images);
    let recap = state.recap.clone();
    commands.entity(e).despawn_children().with_children(|p| {
        let Some(recap) = recap else {
            p.spawn(fonts.role(TextRole::H2Card, "Your life"));
            p.spawn(fonts.role(TextRole::Note, "Waiting for the host..."));
            return;
        };
        stat_tiles(p, fonts, &l, &recap);
        section(p, fonts, "Kills this life", None);
        kill_row(p, fonts, images, &spec, &recap, &names);
        let window = format!("{} s", spec.last_fight_s.max(0.0).round() as u32);
        section(p, fonts, "Your last fight", Some(format!("Hit in your last {window}, not killed by you")));
        last_fight(p, fonts, &l, &spec, &recap, ink, &names, &gun);
        section(p, fonts, "Damage you took", None);
        damage_taken(p, fonts, images, &l, &recap, ink, &names, &gun);
    });
}

/// The recap's colours: the enemy colour follows the player's team colours setting.
#[derive(Clone, Copy)]
struct RecapInk {
    enemy: Color,
}

/// The halo's part of a damage bar.
const SHIELD_INK: Color = TIERS[2];
/// The health part of a damage bar.
const FLESH_INK: Color = FLESH_TEXT;

fn section(p: &mut ChildSpawnerCommands, fonts: &UiFonts, title: &str, sub: Option<String>) {
    p.spawn(Node { margin: UiRect::top(px(14)), column_gap: px(12), align_items: AlignItems::Baseline, ..default() })
        .with_children(|h| {
            h.spawn(fonts.role(TextRole::H2Card, title));
            if let Some(sub) = sub {
                h.spawn(fonts.role(TextRole::Micro, sub));
            }
        });
}

/// KILLS, HEADSHOTS and DAMAGE DEALT this life, big.
fn stat_tiles(p: &mut ChildSpawnerCommands, fonts: &UiFonts, l: &LayoutSpec, recap: &LifeRecap) {
    let w = (l.recap_inner() - 2.0 * LayoutSpec::GAP) / 3.0;
    p.spawn(Node { column_gap: px(LayoutSpec::GAP), ..default() }).with_children(|row| {
        let tiles = [
            ("Kills", recap.kills.len().to_string(), TEXT_HI),
            ("Headshot kills", recap.headshot_kills().to_string(), TIERS[4]),
            ("Damage dealt", whole(recap.dealt_total()), TEXT_HI),
        ];
        for (label, value, color) in tiles {
            row.spawn((
                Node {
                    width: px(w),
                    flex_direction: FlexDirection::Column,
                    row_gap: px(2),
                    padding: UiRect::axes(px(14), px(10)),
                    border: UiRect::left(px(3)),
                    ..default()
                },
                BackgroundColor(W04),
                BorderColor::all(if color == TEXT_HI { STROKE_MID } else { color }),
            ))
            .with_children(|t| {
                t.spawn(fonts.role_color(TextRole::ValueL, value, color));
                t.spawn(fonts.role(TextRole::StatKey, label));
            });
        }
    });
}

/// One icon per kill (a headshot or a body kill) with the victim's name under it.
fn kill_row(
    p: &mut ChildSpawnerCommands,
    fonts: &UiFonts,
    images: &UiImages,
    spec: &RecapSpec,
    recap: &LifeRecap,
    names: &dyn Fn(u64) -> String,
) {
    if recap.kills.is_empty() {
        p.spawn(fonts.role(TextRole::Note, "No kills this life."));
        return;
    }
    let shown = fold(&recap.kills, spec.kills_shown);
    p.spawn(Node { column_gap: px(8), align_items: AlignItems::FlexStart, ..default() }).with_children(|row| {
        for k in shown.items {
            let head = k.headshot();
            let color = if head { TIERS[4] } else { TEXT_HI };
            row.spawn(Node {
                width: px(KILL_CHIP_W),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(4),
                ..default()
            })
            .with_children(|c| {
                c.spawn((
                    Node {
                        width: px(46),
                        height: px(46),
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        border: UiRect::all(px(1)),
                        border_radius: BorderRadius::all(px(3)),
                        ..default()
                    },
                    BackgroundColor(if head { fade(TIERS[4], 0.14) } else { W06 }),
                    BorderColor::all(if head { fade(TIERS[4], 0.6) } else { STROKE_MID }),
                    children![icon(images, kill_icon(k), 28.0, color)],
                ));
                c.spawn((
                    Node { max_width: px(KILL_CHIP_W), overflow: Overflow::clip(), ..default() },
                    children![(fonts.role_color(TextRole::Micro, names(k.victim), TEXT), TextLayout::no_wrap())],
                ));
            });
        }
        if shown.more > 0 {
            row.spawn((
                Node { height: px(46), align_items: AlignItems::Center, ..default() },
                children![fonts.role(TextRole::ValueL, format!("+{}", shown.more))],
            ));
        }
    });
}

/// A kill icon's width.
const KILL_CHIP_W: f32 = 64.0;

/// The icon of a kill: the headshot mark, or a body.
pub fn kill_icon(k: &KillMark) -> Icon {
    if k.headshot() { Icon::Headshot } else { Icon::Torso }
}

/// YOUR LAST FIGHT: a card per opponent you hit in the last seconds and did not kill.
#[allow(clippy::too_many_arguments)]
fn last_fight(
    p: &mut ChildSpawnerCommands,
    fonts: &UiFonts,
    l: &LayoutSpec,
    spec: &RecapSpec,
    recap: &LifeRecap,
    ink: RecapInk,
    names: &dyn Fn(u64) -> String,
    gun: &dyn Fn(&str) -> String,
) {
    let fight = recap.last_fight(spec.last_fight_s);
    if fight.is_empty() {
        p.spawn(fonts.role(TextRole::Note, last_fight_note(recap, spec.last_fight_s)));
        return;
    }
    let shown = fold(&fight, spec.fight_cards);
    let cols = spec.fight_cols.max(1);
    let w = (l.recap_inner() - (cols - 1) as f32 * LayoutSpec::GAP) / cols as f32;
    p.spawn(Node {
        flex_wrap: FlexWrap::Wrap,
        column_gap: px(LayoutSpec::GAP),
        row_gap: px(LayoutSpec::GAP),
        ..default()
    })
    .with_children(|grid| {
        for e in shown.items {
            fight_card(grid, fonts, w, e, ink, names, gun);
        }
    });
    if shown.more > 0 {
        p.spawn(fonts.role(TextRole::Micro, format!("+{} more", shown.more)));
    }
}

/// Why YOUR LAST FIGHT is empty.
pub fn last_fight_note(recap: &LifeRecap, window_s: f32) -> String {
    let secs = window_s.max(0.0).round() as u32;
    let any = recap.dealt.iter().any(|e| e.total() > 0.0 && recap.died_at_s - e.at_s <= window_s.max(0.0) as f64);
    if any {
        format!("You killed everyone you hit in your last {secs} s.")
    } else {
        format!("You hit no one in your last {secs} s.")
    }
}

fn fight_card(
    grid: &mut ChildSpawnerCommands,
    fonts: &UiFonts,
    w: f32,
    e: &Encounter,
    ink: RecapInk,
    names: &dyn Fn(u64) -> String,
    gun: &dyn Fn(&str) -> String,
) {
    grid.spawn((
        Node {
            width: px(w),
            column_gap: px(14),
            padding: UiRect::all(px(10)),
            border: UiRect::all(px(1)),
            align_items: AlignItems::Center,
            ..default()
        },
        BackgroundColor(W04),
        BorderColor::all(STROKE),
    ))
    .with_children(|c| {
        silhouette(c, e, ink.enemy);
        c.spawn(Node { flex_direction: FlexDirection::Column, flex_grow: 1.0, row_gap: px(3), ..default() })
            .with_children(|t| {
                t.spawn((
                    Node { overflow: Overflow::clip(), ..default() },
                    children![(
                        fonts.text(names(e.player), Face::Display, 700, 16.0, ink.enemy, 0.04),
                        TextLayout::no_wrap()
                    )],
                ));
                t.spawn(fonts.role(TextRole::Micro, gun(&e.weapon)));
                t.spawn(Node {
                    column_gap: px(6),
                    align_items: AlignItems::Baseline,
                    margin: UiRect::top(px(4)),
                    ..default()
                })
                .with_children(|v| {
                    v.spawn(fonts.role(TextRole::ValueL, whole(e.total())));
                    v.spawn(fonts.role(TextRole::Unit, "DMG"));
                });
                damage_bar(t, e.shield, e.total(), e.total(), 6.0);
                t.spawn(fonts.role_color(TextRole::Micro, format!("{} into shield", whole(e.shield)), SHIELD_INK));
            });
    });
}

/// One part of the silhouette (px in a [`SIL_W`] x [`SIL_H`] box).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BodyPart {
    pub zone: Zone,
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
    pub r: f32,
}

pub const SIL_W: f32 = 48.0;
pub const SIL_H: f32 = 92.0;

/// The silhouette: a head, a torso, two arms and two legs.
pub const BODY: [BodyPart; 6] = [
    BodyPart { zone: Zone::Head, x: 17.0, y: 0.0, w: 14.0, h: 14.0, r: 7.0 },
    BodyPart { zone: Zone::Torso, x: 14.0, y: 16.0, w: 20.0, h: 32.0, r: 3.0 },
    BodyPart { zone: Zone::Arms, x: 5.0, y: 17.0, w: 7.0, h: 30.0, r: 3.0 },
    BodyPart { zone: Zone::Arms, x: 36.0, y: 17.0, w: 7.0, h: 30.0, r: 3.0 },
    BodyPart { zone: Zone::Legs, x: 14.0, y: 50.0, w: 9.0, h: 42.0, r: 3.0 },
    BodyPart { zone: Zone::Legs, x: 25.0, y: 50.0, w: 9.0, h: 42.0, r: 3.0 },
];

/// How brightly a zone you hit `hits` times lights up (0: unlit). More hits glow more; no numbers shown.
pub fn zone_glow(hits: u16) -> f32 {
    match hits {
        0 => 0.0,
        1 => 0.55,
        2 => 0.78,
        _ => 1.0,
    }
}

fn silhouette(c: &mut ChildSpawnerCommands, e: &Encounter, lit: Color) {
    c.spawn(Node { width: px(SIL_W), height: px(SIL_H), flex_shrink: 0.0, ..default() }).with_children(|s| {
        for part in BODY {
            let glow = zone_glow(e.hits[part.zone]);
            s.spawn((
                Node {
                    width: px(part.w),
                    height: px(part.h),
                    border_radius: BorderRadius::all(px(part.r)),
                    ..abs(Some(part.x), None, Some(part.y), None)
                },
                BackgroundColor(if glow > 0.0 { fade(lit, glow) } else { W10 }),
            ));
        }
    });
}

/// A damage bar: `total` of `max` filled, the halo's part (`shield`) first.
fn damage_bar(p: &mut ChildSpawnerCommands, shield: f32, total: f32, max: f32, height: f32) {
    let (fill, shield_part) = bar_split(shield, total, max);
    p.spawn((Node { width: percent(100), height: px(height), ..default() }, BackgroundColor(W06))).with_children(
        |track| {
            track.spawn(Node { width: percent(fill * 100.0), height: percent(100), ..default() }).with_children(|f| {
                f.spawn((
                    Node { width: percent(shield_part * 100.0), height: percent(100), ..default() },
                    BackgroundColor(SHIELD_INK),
                ));
                f.spawn((Node { flex_grow: 1.0, height: percent(100), ..default() }, BackgroundColor(FLESH_INK)));
            });
        },
    );
}

/// A damage bar's (filled share of the track, the halo's share of the fill), both 0..1.
pub fn bar_split(shield: f32, total: f32, max: f32) -> (f32, f32) {
    let ok = |v: f32| if v.is_finite() { v.max(0.0) } else { 0.0 };
    let (shield, total, max) = (ok(shield), ok(total), ok(max));
    let fill = if max > 0.0 { (total / max).min(1.0) } else { 0.0 };
    let part = if total > 0.0 { (shield / total).min(1.0) } else { 0.0 };
    (fill, part)
}

/// DAMAGE YOU TOOK: per attacker, their gun, a bar of their damage (your halo's part first), the total, the
/// halo's part and the distance; the killer marked.
#[allow(clippy::too_many_arguments)]
fn damage_taken(
    p: &mut ChildSpawnerCommands,
    fonts: &UiFonts,
    images: &UiImages,
    l: &LayoutSpec,
    recap: &LifeRecap,
    ink: RecapInk,
    names: &dyn Fn(u64) -> String,
    gun: &dyn Fn(&str) -> String,
) {
    if recap.taken.is_empty() {
        p.spawn(fonts.role(TextRole::Note, "No player hit you this life."));
        return;
    }
    let rows = fold(&recap.taken, l.recap_rows);
    let max = recap.taken.iter().map(DamageLine::total).fold(0.0, f32::max);
    p.spawn(taken_grid(l, 26.0)).with_children(|h| {
        for (i, head) in ["Player", "Weapon", "Damage", "Total", "Shield", "Dist"].into_iter().enumerate() {
            h.spawn(cell(i >= 3)).with_children(|c| {
                c.spawn(fonts.role(TextRole::TableHead, head));
            });
        }
    });
    for line in rows.items {
        let killer = Some(line.player) == recap.killer;
        p.spawn((Node { border: UiRect::top(px(1)), ..taken_grid(l, 36.0) }, BorderColor::all(STROKE))).with_children(
            |r| {
                r.spawn(cell(false)).with_children(|c| {
                    c.spawn((
                        Node { overflow: Overflow::clip(), ..default() },
                        children![(
                            fonts.text(names(line.player), Face::Display, 700, 15.0, ink.enemy, 0.04),
                            TextLayout::no_wrap()
                        )],
                    ));
                    if killer {
                        if recap.zone == Some(Zone::Head) {
                            c.spawn(icon(images, Icon::Headshot, 14.0, TIERS[4]));
                        }
                        c.spawn((
                            Node { padding: UiRect::axes(px(5), px(1)), ..default() },
                            BackgroundColor(ink.enemy),
                            children![fonts.role(TextRole::TagXs, "Killer")],
                        ));
                    }
                });
                r.spawn(cell(false)).with_children(|c| {
                    c.spawn(fonts.role(TextRole::TableCell, gun(&line.weapon)));
                });
                r.spawn(cell(false)).with_children(|c| damage_bar(c, line.shield, line.total(), max, 8.0));
                r.spawn(cell(true)).with_children(|c| {
                    c.spawn(fonts.role_color(TextRole::Num, whole(line.total()), TEXT_HI));
                });
                r.spawn(cell(true)).with_children(|c| {
                    c.spawn(fonts.role_color(TextRole::Num, whole(line.shield), SHIELD_INK));
                });
                r.spawn(cell(true)).with_children(|c| {
                    c.spawn(fonts.role_color(TextRole::Num, format!("{:.0} m", line.range_m), TEXT));
                });
            },
        );
    }
    if rows.more > 0 {
        p.spawn(fonts.role(TextRole::Micro, format!("+{} more", rows.more)));
    }
    let (shield, total) = recap.taken_totals();
    p.spawn(fonts.role(TextRole::CardLine, format!("Total {} · {} into your shield", whole(total), whole(shield))));
}

/// A DAMAGE YOU TOOK row: the columns of `death_screen.ron`, the bar taking what is left.
fn taken_grid(l: &LayoutSpec, height: f32) -> Node {
    let [player, weapon, total, shield, range] = l.fixed_columns();
    Node {
        display: Display::Grid,
        grid_template_columns: vec![
            GridTrack::px(player),
            GridTrack::px(weapon),
            GridTrack::flex(1.0),
            GridTrack::px(total),
            GridTrack::px(shield),
            GridTrack::px(range),
        ],
        height: px(height),
        align_items: AlignItems::Center,
        ..default()
    }
}

fn cell(right: bool) -> Node {
    Node {
        column_gap: px(6),
        padding: UiRect::horizontal(px(4)),
        align_items: AlignItems::Center,
        justify_content: if right { JustifyContent::FlexEnd } else { JustifyContent::FlexStart },
        ..default()
    }
}

/// Whole damage points.
pub fn whole(v: f32) -> String {
    if v.is_finite() { (v.max(0.0).round() as i64).to_string() } else { "0".into() }
}

/// The items a list shows (at most `max`, at least one) and how many more there were.
pub struct Fold<'a, T> {
    pub items: &'a [T],
    pub more: usize,
}

pub fn fold<T>(items: &[T], max: usize) -> Fold<'_, T> {
    let n = items.len().min(max.max(1));
    Fold { items: &items[..n], more: items.len() - n }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::f32::consts::{FRAC_PI_2, PI};
    use vetf_sim::movement::collision::{Brush, BrushKind};

    fn data() -> &'static DeathScreenData {
        DeathScreenData::embedded()
    }

    /// The death cam looks at the killer while it can see them, keeps looking where it last saw them when they
    /// hide or die, and turns toward the killing shot before it has seen them at all; it never invents a spot.
    #[test]
    fn the_death_cam_picks_its_target() {
        let shot = Some(Vec3::new(0.0, 1.6, -30.0));
        let mut cam = DeathCam::default();
        assert_eq!(cam.target(None, None), None, "nothing known: the view stays");
        assert_eq!(cam.target(None, shot), shot, "the killer is unknown here: where the shot came from");
        let hidden = KillerSight { at: Vec3::new(5.0, 1.3, -20.0), alive: true, visible: false };
        assert_eq!(cam.target(Some(hidden), shot), shot, "behind a wall from the start: the shot");
        let seen = KillerSight { at: Vec3::new(4.0, 1.3, -22.0), alive: true, visible: true };
        assert_eq!(cam.target(Some(seen), shot), Some(seen.at), "in view: their live position");
        let moved = KillerSight { at: Vec3::new(6.0, 1.3, -22.0), ..seen };
        assert_eq!(cam.target(Some(moved), shot), Some(moved.at), "followed while in view");
        let gone = KillerSight { at: Vec3::new(30.0, 1.3, -2.0), alive: true, visible: false };
        assert_eq!(cam.target(Some(gone), shot), Some(moved.at), "out of view: the last spot seen");
        let dead = KillerSight { at: Vec3::new(31.0, 1.3, -2.0), alive: false, visible: true };
        assert_eq!(cam.target(Some(dead), shot), Some(moved.at), "they died: the last spot seen");
        assert_eq!(cam.target(None, shot), Some(moved.at), "they left: the last spot seen");
    }

    /// The angles to a target follow `view_dir`, the view turns the short way round at the same speed at any
    /// frame rate, and the zoom frames the killer without going past the normal view.
    #[test]
    fn the_death_cam_turns_and_zooms_smoothly() {
        let eye = Vec3::new(0.0, 1.6, 0.0);
        for target in [Vec3::new(0.0, 1.6, -10.0), Vec3::new(-10.0, 4.0, 0.0), Vec3::new(3.0, -2.0, 8.0)] {
            let (yaw, pitch) = look_at(eye, target).unwrap();
            let dir = vetf_sim::input::view_dir(yaw, pitch);
            assert!(dir.distance((target - eye).normalize()) < 1e-4, "{target}: {dir}");
        }
        assert_eq!(look_at(eye, eye), None);
        // Short way round: from just left of north to just right of it.
        let (y, _) = turn_toward((0.1, 0.0), (std::f32::consts::TAU - 0.1, 0.0), 4.0, 0.05);
        assert!(!(0.1..PI).contains(&y), "turned through north: {y}");
        // Frame-rate independent: two half steps make one whole step.
        let rate = data().cam.turn_rate;
        let once = turn_toward((0.0, 0.0), (FRAC_PI_2, 0.3), rate, 0.1);
        let half = turn_toward((0.0, 0.0), (FRAC_PI_2, 0.3), rate, 0.05);
        let twice = turn_toward(half, (FRAC_PI_2, 0.3), rate, 0.05);
        assert!((once.0 - twice.0).abs() < 1e-4 && (once.1 - twice.1).abs() < 1e-4);
        // It gets there, smoothly (no snap on the first frame).
        assert!(once.0 > 0.0 && once.0 < FRAC_PI_2 * 0.6);
        let mut a = (0.0, 0.0);
        for _ in 0..120 {
            a = turn_toward(a, (FRAC_PI_2, 0.3), rate, 1.0 / 60.0);
        }
        assert!((a.0 - FRAC_PI_2).abs() < 0.01 && (a.1 - 0.3).abs() < 0.01, "{a:?}");
        // Zoom: closer is wider, never past the normal view, never tighter than the minimum.
        let cam = data().cam;
        let widest = 70.0;
        assert_eq!(frame_fov(&cam, 0.5, widest), widest);
        assert!(frame_fov(&cam, 8.0, widest) > frame_fov(&cam, 12.0, widest));
        assert_eq!(frame_fov(&cam, 1000.0, widest), cam.min_fov_deg);
    }

    /// Line of sight for the death cam: a wall between hides the killer; a killer standing against the wall
    /// (within the slack) is still in view.
    #[test]
    fn the_killer_is_out_of_view_behind_a_wall() {
        let mut world = CollisionWorld::default();
        world.push(Brush::cuboid(Vec3::new(-2.0, 0.0, -10.5), Vec3::new(2.0, 3.0, -10.0), BrushKind::Solid));
        let eye = Vec3::new(0.0, 1.6, 0.0);
        assert!(!in_sight(&world, eye, Vec3::new(0.0, 1.3, -20.0), 0.5), "behind the wall");
        assert!(in_sight(&world, eye, Vec3::new(10.0, 1.3, -20.0), 0.5), "beside it");
        assert!(in_sight(&world, eye, Vec3::new(0.0, 1.3, -9.8), 0.5), "in front of it");
        assert!(in_sight(&world, eye, Vec3::new(0.0, 1.3, -10.3), 0.5), "inside the slack");
        assert!(in_sight(&world, eye, eye, 0.5));
    }

    /// The killer's health and halo are a rough read: pips and a word, never a number.
    #[test]
    fn the_killer_reads_roughly() {
        let r = &data().reads;
        assert_eq!(r.read(&r.health, 1.0), (r.segments, "Healthy"));
        assert_eq!(r.read(&r.health, 0.01).0, 1, "any health left lights a pip");
        assert_eq!(r.read(&r.health, 0.01).1, "Critical");
        assert_eq!(r.read(&r.health, 0.5).1, "Hurt");
        assert_eq!(r.read(&r.halo, 0.0), (0, "Broken"));
        assert_eq!(r.read(&r.halo, f32::NAN), (0, "Broken"));
        for words in [&r.health, &r.halo] {
            assert!(words.windows(2).all(|w| w[0].0 > w[1].0), "thresholds go down");
            assert_eq!(words.last().map(|w| w.0), Some(0.0), "the last word covers nothing left");
            for (_, w) in words.iter() {
                assert!(!w.chars().any(|c| c.is_ascii_digit()), "words, not numbers: {w}");
            }
        }
        // Every share gives at most `segments` pips, and more health never fewer.
        let mut last = 0;
        for i in 0..=100 {
            let (pips, _) = r.read(&r.health, i as f32 / 100.0);
            assert!(pips <= r.segments && pips >= last);
            last = pips;
        }
    }

    /// The killer card and title for a recap: the killer's name, gun and distance, the headshot, their health
    /// and halo as words; a fall has no killer; a killer who left is said so.
    #[test]
    fn the_killer_card_says_who_with_what_from_how_far() {
        let game = GameData::embedded();
        let reads = &data().reads;
        let mut log = LifeLog::default();
        log.took(&Hit {
            shooter: 7,
            victim: 1,
            victim_life: 0,
            weapon: "ar7_mako",
            zone: Zone::Head,
            shield: 10.0,
            health: 40.0,
            range_m: 21.4,
            from: Vec3::ZERO,
            at_s: 3.0,
        });
        let recap = log.recap(Some(7), Some(Zone::Head));
        let loadout = vetf_sim::player::Loadout::default_for(&game, MatchMode::Tdm);
        let mut vitals = Vitals {
            health: vetf_sim::combat::Health::new(game.armor.zone_hp),
            halo: vetf_sim::combat::HaloState::full(&loadout.halo),
            wounds: Default::default(),
            respawn_s: 0.0,
            protected_s: 0.0,
            awaiting_respawn: false,
        };
        fn now<'a>(vitals: &'a Vitals, loadout: &'a vetf_sim::player::Loadout) -> KillerNow<'a> {
            KillerNow { name: "Rook", vitals, loadout }
        }
        let k = killer_lines(&game, reads, Some(&recap), Some(now(&vitals, &loadout)));
        let mako = game.weapon("ar7_mako").unwrap().name.clone();
        assert_eq!(k.title, "BY ROOK");
        assert_eq!(k.sub, format!("{mako} · 21 m · headshot"));
        assert_eq!((k.name.as_str(), k.weapon.as_str(), k.range.as_str()), ("ROOK", mako.as_str(), "21 m"));
        assert_eq!(k.health, Some((reads.segments, "HEALTHY".into())));
        assert!(k.card && k.tier >= 1, "the default loadout wears a halo");
        let halo = k.halo.unwrap().1;
        assert!(halo.starts_with("FULL · T"), "{halo}");
        // Hurt: a rough read, no numbers anywhere but the tier and the distance.
        vitals.health.hp.torso *= 0.2;
        vitals.health.hp.head *= 0.2;
        vitals.halo.shield = Default::default();
        let k = killer_lines(&game, reads, Some(&recap), Some(now(&vitals, &loadout)));
        assert_eq!(k.halo.as_ref().map(|h| h.0), Some(0));
        assert!(k.halo.unwrap().1.starts_with("BROKEN"));
        assert!(!k.health.unwrap().1.chars().any(|c| c.is_ascii_digit()));
        // They died since, or left.
        vitals.health.dead = true;
        let k = killer_lines(&game, reads, Some(&recap), Some(now(&vitals, &loadout)));
        assert_eq!(k.health, Some((0, "DOWN SINCE".into())));
        let k = killer_lines(&game, reads, Some(&recap), None);
        assert_eq!(k.title, "BY A PLAYER WHO LEFT");
        assert_eq!(k.health, Some((0, "LEFT THE MATCH".into())));
        // A fall: no killer.
        let fall = LifeLog::default().recap(None, Some(Zone::Legs));
        let k = killer_lines(&game, reads, Some(&fall), None);
        assert_eq!((k.title.as_str(), k.sub.as_str(), k.health), ("YOU DIED", "A fall", None));
        assert!(!k.card, "no killer card for a fall");
        // Before the recap arrives: nothing yet.
        assert_eq!(killer_lines(&game, reads, None, None).title, "");
    }

    /// The respawn block: the countdown while the timer runs, then READY with the fallback's seconds.
    #[test]
    fn the_respawn_block_counts_down_then_offers_respawn() {
        assert_eq!(respawn_lines(3.2, 13.2, false), ("4".into(), "RESPAWN IN 4 S".into(), String::new()));
        assert_eq!(
            respawn_lines(0.0, 10.0, false),
            ("0".into(), "READY TO RESPAWN".into(), "RESPAWNS BY ITSELF IN 10 S".into())
        );
        assert_eq!(respawn_lines(0.0, 2.5, false).2, "RESPAWNS BY ITSELF IN 3 S");
        assert_eq!(respawn_lines(0.0, 2.5, true).1, "RESPAWNING");
    }

    fn dealt(victim: u64, life: u32, zone: Zone, shield: f32, health: f32, at_s: f64) -> Hit<'static> {
        Hit {
            shooter: 1,
            victim,
            victim_life: life,
            weapon: "ar7_mako",
            zone,
            shield,
            health,
            range_m: 15.0,
            from: Vec3::ZERO,
            at_s,
        }
    }

    /// Whole damage points; long lists fold into "+N more"; a damage bar splits the halo's part from the rest
    /// and never overflows its track.
    #[test]
    fn the_recap_stays_compact() {
        assert_eq!([whole(0.4), whole(41.6), whole(-3.0), whole(f32::NAN)], ["0", "42", "0", "0"]);
        let max = data().layout.recap_rows;
        let items: Vec<u32> = (0..8).collect();
        let f = fold(&items, max);
        assert_eq!((f.items.len(), f.more), (max, 8 - max));
        let f = fold(&items[..2], max);
        assert_eq!((f.items.len(), f.more), (2, 0));
        assert_eq!(fold(&items, 0).items.len(), 1, "always at least one");
        assert_eq!(bar_split(30.0, 120.0, 240.0), (0.5, 0.25));
        assert_eq!(bar_split(0.0, 80.0, 80.0), (1.0, 0.0));
        assert_eq!(bar_split(10.0, 0.0, 0.0), (0.0, 0.0));
        assert_eq!(bar_split(500.0, 300.0, 100.0), (1.0, 1.0), "clamped");
        assert_eq!(bar_split(f32::NAN, f32::INFINITY, 10.0), (0.0, 0.0));
    }

    /// KILLS THIS LIFE: one icon per kill, the headshot mark for a headshot kill and a body for the rest (a
    /// bleed-out included), and the count matches the kills.
    #[test]
    fn kill_icons_tell_headshots_from_body_kills() {
        let mut log = LifeLog::default();
        log.dealt(&dealt(3, 0, Zone::Head, 40.0, 80.0, 10.0));
        log.killed(3, 0, Some(Zone::Head));
        log.killed(4, 1, Some(Zone::Legs));
        log.killed(5, 0, None);
        let r = log.recap(None, None);
        let icons: Vec<Icon> = r.kills.iter().map(kill_icon).collect();
        assert_eq!(icons, [Icon::Headshot, Icon::Torso, Icon::Torso]);
        assert_eq!((r.kills.len(), r.headshot_kills()), (3, 1));
        assert_eq!(r.kills.iter().map(|k| k.victim).collect::<Vec<_>>(), [3, 4, 5], "in order, each with a name");
    }

    /// YOUR LAST FIGHT reads the data file's window: the user's case, two opponents hurt in a gunfight just
    /// before the death and neither killed, plus an older fight and a kill that stay out. The silhouette lights
    /// only the zones hit, brighter for more hits; an empty fight says why.
    #[test]
    fn the_last_fight_shows_who_got_away() {
        let spec = data().recap;
        assert_eq!(spec.last_fight_s, 5.0, "the user's 5 s");
        let mut log = LifeLog::default();
        log.dealt(&dealt(3, 0, Zone::Torso, 50.0, 30.0, 20.0)); // long before
        log.dealt(&dealt(4, 2, Zone::Head, 30.0, 0.0, 57.0));
        log.dealt(&dealt(4, 2, Zone::Torso, 20.0, 15.0, 58.0));
        log.dealt(&dealt(4, 2, Zone::Torso, 0.0, 25.0, 59.0));
        log.dealt(&dealt(6, 0, Zone::Legs, 0.0, 22.0, 58.5));
        log.dealt(&dealt(7, 1, Zone::Torso, 0.0, 90.0, 56.0));
        log.killed(7, 1, Some(Zone::Torso));
        log.died(60.0);
        let r = log.recap(Some(4), Some(Zone::Torso));
        let fight = r.last_fight(spec.last_fight_s);
        let got: Vec<(u64, f32, f32)> = fight.iter().map(|e| (e.player, e.total(), e.shield)).collect();
        assert_eq!(got, [(4, 90.0, 50.0), (6, 22.0, 0.0)]);
        let glow: Vec<f32> = Zone::ALL.iter().map(|z| zone_glow(fight[0].hits[*z])).collect();
        assert_eq!(glow, [zone_glow(1), zone_glow(2), 0.0, 0.0], "head once, torso twice, nothing else");
        assert!(zone_glow(1) > 0.0 && zone_glow(2) > zone_glow(1) && zone_glow(9) >= zone_glow(3));
        assert_eq!(zone_glow(9), 1.0);
        // Nobody left: say why.
        let mut killed_all = LifeLog::default();
        killed_all.dealt(&dealt(7, 0, Zone::Torso, 0.0, 90.0, 9.0));
        killed_all.killed(7, 0, Some(Zone::Torso));
        killed_all.died(10.0);
        let r = killed_all.recap(None, None);
        assert!(r.last_fight(spec.last_fight_s).is_empty());
        assert_eq!(last_fight_note(&r, spec.last_fight_s), "You killed everyone you hit in your last 5 s.");
        let quiet = LifeLog::default().recap(None, None);
        assert_eq!(last_fight_note(&quiet, spec.last_fight_s), "You hit no one in your last 5 s.");
    }

    /// The silhouette has every zone, inside its box.
    #[test]
    fn the_silhouette_covers_every_zone() {
        for z in Zone::ALL {
            assert!(BODY.iter().any(|p| p.zone == z), "{z:?}");
        }
        for p in BODY {
            assert!(p.x >= 0.0 && p.y >= 0.0 && p.x + p.w <= SIL_W && p.y + p.h <= SIL_H, "{p:?}");
        }
    }

    /// The layout keeps the centre clear for the death cam, and the recap's columns and cards fit its panel.
    #[test]
    fn the_layout_leaves_the_centre_clear() {
        let l = data().layout;
        let centre = REF_WIDTH - 2.0 * l.margin_x - l.killer_w - l.recap_w;
        assert!(centre >= l.min_centre_w, "{centre} px between the columns");
        let cols: f32 = l.fixed_columns().iter().sum::<f32>() + l.col_bar_min;
        assert!(cols <= l.recap_inner(), "{cols} px of columns");
        assert!(l.recap_rows >= 1);
        let r = data().recap;
        assert!(r.fight_cards >= 1 && r.fight_cols >= 1 && r.kills_shown >= 1 && r.last_fight_s > 0.0);
        // A fight card fits a silhouette and a damage number beside it.
        let card = (l.recap_inner() - (r.fight_cols - 1) as f32 * LayoutSpec::GAP) / r.fight_cols as f32;
        assert!(card >= SIL_W + 150.0, "{card} px per fight card");
        // The kill icons fit one row.
        let kills = r.kills_shown as f32 * (KILL_CHIP_W + 8.0) + 48.0;
        assert!(kills <= l.recap_inner(), "{kills} px of kill icons");
        let cam = data().cam;
        assert!(cam.turn_rate > 0.0 && cam.zoom_rate > 0.0 && cam.min_fov_deg > 5.0);
        assert!((0.0..=1.0).contains(&cam.aim_height));
    }

    /// Every system's queries can run side by side (Bevy panics on conflicting access when a system is first
    /// set up; the missing resources only make these runs return an error).
    #[test]
    fn the_systems_have_no_conflicting_queries() {
        use bevy::ecs::system::RunSystemOnce;
        let mut world = World::new();
        let _ = world.run_system_once(receive_recaps);
        let _ = world.run_system_once(follow_death);
        let _ = world.run_system_once(spawn_root);
        let _ = world.run_system_once(actions);
        let _ = world.run_system_once(bot_respawn);
        let _ = world.run_system_once(track_killer);
        let _ = world.run_system_once(refresh);
        let _ = world.run_system_once(rebuild_recap);
        // The check itself: a system with conflicting queries does panic here.
        let clash = std::panic::catch_unwind(|| {
            let mut world = World::new();
            let _ = world.run_system_once(|_: Query<&mut Node>, _: Query<&mut Node, With<TimerFill>>| {});
        });
        assert!(clash.is_err());
    }

    /// The file in the data folder is the one compiled in.
    #[test]
    fn the_data_file_loads() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets/data/death_screen.ron");
        let text = std::fs::read_to_string(path).unwrap();
        assert_eq!(&ron::from_str::<DeathScreenData>(&text).unwrap(), data());
    }
}
