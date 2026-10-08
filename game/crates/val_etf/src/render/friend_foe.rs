//! Telling friend from foe (art/DIRECTION_LOG.md item 17). In a team mode the local player's teammates have a
//! soft rim glow on their bodies in the ally colour (HUD & ACCESSIBILITY's TEAM COLOURS, colour-blind presets,
//! never red), seen in line of sight only: the glow is drawn with the body, so a wall in front hides it and
//! there is no silhouette through walls. A teammate fully behind cover shows as a small name marker above the
//! head instead, fading with distance. Everyone else looks plain: one body colour for all, no glow, no team or
//! enemy colour. The halo arcs keep their tier colours (armour and weight class, not a side), and the kill feed
//! and scoreboard keep theirs (they are UI).
//!
//! The rule is [`is_ally`]: the same side in a mode with sides. The extraction mode's squads are such sides, so
//! squad members will glow and everyone else will look plain without a change here.
//!
//! The numbers live in `game/assets/data/friend_foe.ron` (visual only); the glow is `assets/shaders/ally_rim.wgsl`.
//! `--host <map> --demo-ui friend-foe` stands three still players around the view for screenshots (see
//! [`demo_friend_foe`]).

use super::hit_fx::on_screen;
use super::{PlayerPose, PlayerVisual, ViewCamera, vfov_of};
use crate::AppState;
use crate::config::{Cli, CurrentLevel, Data};
use crate::net::{Role, Session};
use crate::screens::Screens;
use crate::settings::Settings;
use crate::ui_kit::{Face, UiFonts};
use bevy::pbr::{ExtendedMaterial, MaterialExtension, MaterialPlugin};
use bevy::prelude::*;
use bevy::render::render_resource::{AsBindGroup, ShaderType};
use bevy::shader::ShaderRef;
use bevy::window::PrimaryWindow;
use lightyear::prelude::*;
use serde::Deserialize;
use std::collections::HashMap;
use std::sync::OnceLock;
use vetf_net::*;
use vetf_sim::level::Team;
use vetf_sim::movement::Stance;
use vetf_sim::movement::collision::CollisionWorld;

const SHADER: &str = "shaders/ally_rim.wgsl";

/// Below the hit markers (`hit_fx`), above the world.
const MARKER_Z: i32 = -6;

pub struct FriendFoePlugin;

impl Plugin for FriendFoePlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(MaterialPlugin::<BodyMaterial>::default())
            .insert_resource(FriendFoeData::load())
            .add_systems(OnEnter(AppState::InGame), spawn_marker_layer)
            .add_systems(
                Update,
                (demo_friend_foe.run_if(demo_is_friend_foe), mark_allies, place_ally_markers)
                    .chain()
                    .after(super::update_camera)
                    .after(super::update_player_visuals)
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

// ---------------------------------------------------------------------------------------------- data

/// `game/assets/data/friend_foe.ron`.
#[derive(Resource, Debug, Clone, PartialEq, Deserialize)]
pub struct FriendFoeData {
    /// Every player's body and head (sRGB 0..1), whatever their side.
    pub body_color: [f32; 3],
    pub head_color: [f32; 3],
    pub rim: RimData,
    pub marker: MarkerData,
}

/// A teammate's glow.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct RimData {
    /// Emissive (linear) at the silhouette's edge.
    pub strength: f32,
    /// Fresnel exponent: higher keeps the glow to a thinner edge.
    pub power: f32,
    /// A wash over the whole teammate, as a share of the edge's glow.
    pub fill: f32,
}

/// A teammate's name marker, shown while they are behind cover.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct MarkerData {
    pub above_head_m: f32,
    pub font_px: f32,
    pub dot_px: f32,
    pub near_m: f32,
    pub far_m: f32,
    pub far_alpha: f32,
    pub hide_m: f32,
    /// Heights above the feet (standing; scaled down crouched) that count as seeing the teammate.
    pub sight_heights_m: Vec<f32>,
}

const EMBEDDED: &str = include_str!("../../../../assets/data/friend_foe.ron");

impl FriendFoeData {
    /// The copy compiled into the binary.
    pub fn embedded() -> &'static FriendFoeData {
        static DATA: OnceLock<FriendFoeData> = OnceLock::new();
        DATA.get_or_init(|| ron::from_str(EMBEDDED).expect("game/assets/data/friend_foe.ron is valid"))
    }

    /// From the data folder (so it can be tuned without a rebuild), else the built-in copy.
    pub fn load() -> FriendFoeData {
        let path = crate::config::assets_root().join("data").join("friend_foe.ron");
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

// ---------------------------------------------------------------------------------------------- the rule

/// Whether another player is the local player's teammate: the same side, in a mode with sides (team
/// deathmatch now, the extraction mode's squads later). Free-for-all, the range and anyone without a side are
/// never allies, so they look plain.
pub fn is_ally(mode: Option<MatchMode>, mine: Option<Team>, theirs: Option<Team>) -> bool {
    mode.is_some_and(|m| m.has_teams()) && mine.is_some() && mine == theirs
}

/// How strongly a teammate's marker shows `distance_m` from the camera: full up to `near_m`, fading to
/// `far_alpha` at `far_m`, gone beyond `hide_m`.
pub fn marker_alpha(m: &MarkerData, distance_m: f32) -> f32 {
    if distance_m > m.hide_m {
        return 0.0;
    }
    let t = ((distance_m - m.near_m) / (m.far_m - m.near_m).max(1e-3)).clamp(0.0, 1.0);
    let t = t * t * (3.0 - 2.0 * t);
    1.0 + (m.far_alpha - 1.0) * t
}

/// Whether the camera at `eye` sees any of `points` (a player's sight heights) past the map's walls.
pub fn in_sight(world: &CollisionWorld, eye: Vec3, points: &[Vec3]) -> bool {
    points.iter().any(|p| world.line_of_sight(eye, *p))
}

/// A player's sight points: `heights` above the feet, squashed like the body when crouched or sliding.
pub fn sight_points(feet: Vec3, stance: Stance, heights: &[f32]) -> Vec<Vec3> {
    let squash = if stance == Stance::Stand { 1.0 } else { PlayerPose::CROUCH_SQUASH };
    heights.iter().map(|h| feet + Vec3::Y * h * squash).collect()
}

// ---------------------------------------------------------------------------------------------- the glow

/// Every player body's material: a StandardMaterial with the ally rim (strength 0 for everyone but teammates).
pub type BodyMaterial = ExtendedMaterial<StandardMaterial, AllyRim>;

/// The shader's `Rim` uniform (see ally_rim.wgsl).
#[derive(Clone, Copy, Debug, Default, PartialEq, ShaderType, Reflect)]
pub struct RimUniform {
    /// rgb: the ally colour (linear), a: strength at the edge (0 = no glow).
    pub color: Vec4,
    /// x: fresnel exponent, y: wash over the whole body.
    pub shape: Vec4,
}

impl RimUniform {
    /// The glow for a teammate in `ally` colour, or none (`None`: everyone else).
    pub fn new(rim: &RimData, ally: Option<Color>) -> Self {
        match ally {
            Some(c) => {
                let l = c.to_linear();
                RimUniform {
                    color: Vec4::new(l.red, l.green, l.blue, rim.strength),
                    shape: Vec4::new(rim.power, rim.fill, 0.0, 0.0),
                }
            }
            None => RimUniform::default(),
        }
    }
}

#[derive(Asset, AsBindGroup, Reflect, Debug, Clone, Default)]
pub struct AllyRim {
    #[uniform(100)]
    pub rim: RimUniform,
}

impl MaterialExtension for AllyRim {
    fn fragment_shader() -> ShaderRef {
        SHADER.into()
    }
}

fn srgb(c: [f32; 3]) -> Color {
    Color::srgb(c[0], c[1], c[2])
}

/// A plain body part in `color` (no glow until [`mark_allies`] finds a teammate).
fn plain(color: Color, roughness: f32) -> BodyMaterial {
    ExtendedMaterial {
        base: StandardMaterial { base_color: color, perceptual_roughness: roughness, ..default() },
        extension: AllyRim::default(),
    }
}

/// A player's body and head materials (their own, so one player's glow changes no one else's).
#[derive(Component, Debug, Clone)]
pub struct BodyLook {
    pub body: Handle<BodyMaterial>,
    pub head: Handle<BodyMaterial>,
}

impl BodyLook {
    /// New plain materials for one player, everyone in the same colours.
    pub fn new(data: &FriendFoeData, materials: &mut Assets<BodyMaterial>) -> Self {
        BodyLook {
            body: materials.add(plain(srgb(data.body_color), 0.7)),
            head: materials.add(plain(srgb(data.head_color), 0.6)),
        }
    }
}

/// Teammates glow, everyone else is plain: kept up to date as the mode, the sides and the ally colour change.
fn mark_allies(
    data: Res<FriendFoeData>,
    settings: Res<Settings>,
    matches: Query<&MatchState>,
    me: Query<&PlayerInfo, With<Controlled>>,
    players: Query<(&PlayerInfo, &BodyLook), Without<Controlled>>,
    mut materials: ResMut<Assets<BodyMaterial>>,
) {
    let mode = matches.iter().next().map(|m| m.mode);
    let mine = me.iter().next().and_then(|i| i.team);
    let ally = settings.team_colors().0;
    for (info, look) in &players {
        let want = RimUniform::new(&data.rim, is_ally(mode, mine, info.team).then_some(ally));
        for h in [&look.body, &look.head] {
            if materials.get(h).is_some_and(|m| m.extension.rim != want)
                && let Some(mut m) = materials.get_mut(h)
            {
                m.extension.rim = want;
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------- markers

#[derive(Component)]
struct MarkerLayer;

/// A teammate's name marker: its anchor (at the point above the head) and its parts.
#[derive(Component)]
struct AllyMarker {
    player: Entity,
    text: Entity,
    dot: Entity,
}

fn spawn_marker_layer(mut commands: Commands) {
    commands.spawn((
        MarkerLayer,
        Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
        GlobalZIndex(MARKER_Z),
        Visibility::Inherited,
        Pickable::IGNORE,
        DespawnOnExit(AppState::InGame),
    ));
}

/// Where each teammate behind cover shows its marker this frame, and how strongly.
#[derive(Debug, Clone, PartialEq)]
struct Shown {
    at: Vec2,
    alpha: f32,
    name: String,
}

/// Each teammate fully behind cover gets a small name marker above the head (after the camera and the players
/// have moved this frame); in sight, the glow is enough.
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn place_ally_markers(
    mut commands: Commands,
    data: Res<FriendFoeData>,
    settings: Res<Settings>,
    fonts: Res<UiFonts>,
    screens: Res<Screens>,
    level: Option<Res<CurrentLevel>>,
    matches: Query<&MatchState>,
    windows: Query<&Window, With<PrimaryWindow>>,
    camera: Query<(&Transform, &Projection), With<ViewCamera>>,
    me: Query<&PlayerInfo, With<Controlled>>,
    players: Query<(Entity, &PlayerInfo, &PlayerMove, &Vitals), (With<PlayerVisual>, Without<Controlled>)>,
    mut layer: Query<(Entity, &mut Visibility), With<MarkerLayer>>,
    mut markers: Query<(Entity, &AllyMarker, &mut Node, &mut Visibility), Without<MarkerLayer>>,
    mut texts: Query<(&mut Text, &mut TextColor, &mut TextShadow)>,
    mut dots: Query<&mut BackgroundColor>,
) {
    let Some((layer, mut layer_vis)) = layer.iter_mut().next() else { return };
    // Hidden with the HUD while a hub screen is open over the match.
    layer_vis.set_if_neq(if screens.is_empty() { Visibility::Inherited } else { Visibility::Hidden });
    let m = &data.marker;
    let mode = matches.iter().next().map(|s| s.mode);
    let mine = me.iter().next().and_then(|i| i.team);
    let mut shown: HashMap<Entity, Shown> = HashMap::new();
    if let (Some((cam, projection)), Some(level)) = (camera.iter().next(), level.as_ref()) {
        let aspect = windows.iter().next().map_or(16.0 / 9.0, |w| w.width() / w.height().max(1.0));
        let vfov = vfov_of(projection);
        for (e, info, mv, vitals) in &players {
            if vitals.health.dead || !is_ally(mode, mine, info.team) {
                continue;
            }
            let points = sight_points(mv.0.pos, mv.0.stance, &m.sight_heights_m);
            if in_sight(&level.world, cam.translation, &points) {
                continue;
            }
            let top = points.iter().map(|p| p.y).fold(mv.0.pos.y, f32::max);
            let above = Vec3::new(mv.0.pos.x, top + m.above_head_m, mv.0.pos.z);
            let alpha = marker_alpha(m, above.distance(cam.translation));
            let Some(at) = on_screen(cam, vfov, aspect, above) else { continue };
            if alpha <= 0.0 || !(0.0..=1.0).contains(&at.x) || !(0.0..=1.0).contains(&at.y) {
                continue;
            }
            shown.insert(e, Shown { at, alpha, name: info.name.to_uppercase() });
        }
    }

    let ally = settings.team_colors().0;
    let mut have: HashMap<Entity, Entity> = HashMap::new();
    for (marker, a, mut node, mut vis) in &mut markers {
        if players.get(a.player).is_err() {
            commands.entity(marker).despawn();
            continue;
        }
        have.insert(a.player, marker);
        let Some(s) = shown.get(&a.player) else {
            vis.set_if_neq(Visibility::Hidden);
            continue;
        };
        vis.set_if_neq(Visibility::Inherited);
        (node.left, node.top) = (percent(s.at.x * 100.0), percent(s.at.y * 100.0));
        if let Ok((mut text, mut color, mut shadow)) = texts.get_mut(a.text) {
            if text.0 != s.name {
                text.0 = s.name.clone();
            }
            color.0 = ally.with_alpha(s.alpha);
            shadow.color = Color::BLACK.with_alpha(0.7 * s.alpha);
        }
        if let Ok(mut bg) = dots.get_mut(a.dot) {
            bg.0 = ally.with_alpha(s.alpha);
        }
    }
    for (player, s) in shown.iter().filter(|(p, _)| !have.contains_key(*p)) {
        spawn_marker(&mut commands, &fonts, m, layer, *player, s, ally);
    }
}

fn spawn_marker(
    commands: &mut Commands,
    fonts: &UiFonts,
    m: &MarkerData,
    layer: Entity,
    player: Entity,
    s: &Shown,
    ally: Color,
) {
    let color = ally.with_alpha(s.alpha);
    let anchor = commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                left: percent(s.at.x * 100.0),
                top: percent(s.at.y * 100.0),
                width: px(0),
                height: px(0),
                ..default()
            },
            Pickable::IGNORE,
            ChildOf(layer),
        ))
        .id();
    // The name and its dot stand centred on the anchor, the dot's foot on it.
    let column = commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                left: px(-120),
                width: px(240),
                bottom: px(0),
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                row_gap: px(2),
                ..default()
            },
            Pickable::IGNORE,
            ChildOf(anchor),
        ))
        .id();
    let text = commands
        .spawn((
            fonts.text(s.name.clone(), Face::Display, 600, m.font_px, color, 0.06),
            TextShadow { offset: Vec2::splat(1.0), color: Color::BLACK.with_alpha(0.7 * s.alpha) },
            TextLayout::no_wrap(),
            Pickable::IGNORE,
            ChildOf(column),
        ))
        .id();
    let dot = commands
        .spawn((
            Node { width: px(m.dot_px), height: px(m.dot_px), border_radius: BorderRadius::MAX, ..default() },
            BackgroundColor(color),
            Pickable::IGNORE,
            ChildOf(column),
        ))
        .id();
    commands.entity(anchor).insert(AllyMarker { player, text, dot });
}

// ---------------------------------------------------------------------------------------------- demo

fn demo_is_friend_foe(cli: Res<Cli>, session: Res<Session>) -> bool {
    session.role == Role::Host && cli.demo_ui.as_deref() == Some("friend-foe")
}

/// A still stand-in player for screenshots: drawn like any other player on the host, never simulated, hit or
/// sent to anyone.
#[derive(Component)]
struct Puppet;

/// `--host <map> --demo-ui friend-foe`: a second into the match, three still players stand around the view: a
/// teammate in sight, a teammate behind a wall and an enemy in sight (in free-for-all all three are just other
/// players). In team deathmatch every player who joins is put on the host's team and, a few seconds after they
/// appear, set down in sight too (a `--bot` joiner: a real teammate over the network).
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn demo_friend_foe(
    mut commands: Commands,
    time: Res<Time>,
    data: Res<Data>,
    ff: Res<FriendFoeData>,
    level: Option<Res<CurrentLevel>>,
    matches: Query<&MatchState>,
    camera: Query<&Transform, With<ViewCamera>>,
    mut players: Query<(Entity, &mut PlayerInfo, &mut PlayerMove, Has<Controlled>), Without<Puppet>>,
    mut since: Local<Option<f32>>,
    mut placed: Local<bool>,
    mut joined: Local<HashMap<Entity, (f32, bool)>>,
) {
    let (Some(level), Some(cam)) = (level, camera.iter().next()) else { return };
    let t = time.elapsed_secs();
    let entered = *since.get_or_insert(t);
    let mode = matches.iter().next().map(|m| m.mode).unwrap_or(MatchMode::Tdm);
    let host_team = players.iter().find(|p| p.3).and_then(|p| p.1.team);
    let spots = || DemoSpots::around(&level.world, cam, &ff.marker.sight_heights_m);
    // Joined players: the host's side, then into view.
    for (e, mut info, mut mv, mine) in &mut players {
        if mine {
            continue;
        }
        if mode.has_teams() && host_team.is_some() && info.team != host_team {
            info.team = host_team;
        }
        let (first, moved) = joined.entry(e).or_insert((t, false));
        if !*moved && t - *first > 4.0 {
            *moved = true;
            let at = spots().joiner;
            mv.0.pos = at;
            mv.0.vel = Vec3::ZERO;
            info!("demo: {} set down at {at:.1} in sight of the host", info.name);
        }
    }
    if *placed || t - entered < 1.0 {
        return;
    }
    *placed = true;
    let spots = spots();
    let other = match host_team {
        Some(Team::A) => Some(Team::B),
        Some(Team::B) => Some(Team::A),
        None => None,
    };
    let (ally, enemy) = if mode.has_teams() { (host_team, other) } else { (None, None) };
    let stand =
        [("KESTREL", ally, spots.ally_seen), ("SOLACE", ally, spots.ally_hidden), ("RIVAL", enemy, spots.enemy_seen)];
    for (i, (name, team, feet)) in stand.into_iter().enumerate() {
        let loadout = vetf_sim::player::Loadout::default_for(&data, mode);
        let to_cam = cam.translation - feet;
        let yaw = (-to_cam.x).atan2(-to_cam.z);
        let seen = level.world.line_of_sight(cam.translation, feet + Vec3::Y * 1.2);
        info!("demo: {name} ({team:?}) stands at {feet:.1}, in sight of the camera: {seen}");
        commands.spawn((
            Puppet,
            Name::new(format!("Demo player {name}")),
            PlayerId(0xD3_0000 + i as u64),
            PlayerInfo { name: name.into(), team },
            PlayerMove(vetf_sim::movement::MoveState::spawn(feet, 0.0)),
            PlayerLook { yaw, pitch: 0.0 },
            PlayerWeapon(vetf_sim::weapon::WeaponState::new(&data, &loadout.weapon)),
            Vitals {
                health: vetf_sim::combat::Health::new(data.armor.zone_hp),
                halo: vetf_sim::combat::HaloState::full(&loadout.halo),
                wounds: Default::default(),
                respawn_s: 0.0,
                protected_s: 0.0,
            },
            PlayerLoadout(loadout),
        ));
    }
}

/// Where the demo's players stand, worked out from the camera and the map's walls.
#[derive(Debug, Clone, Copy, PartialEq)]
struct DemoSpots {
    ally_seen: Vec3,
    ally_hidden: Vec3,
    enemy_seen: Vec3,
    joiner: Vec3,
}

impl DemoSpots {
    /// `heights`: the sight heights a teammate is seen by ([`MarkerData::sight_heights_m`]).
    fn around(world: &CollisionWorld, cam: &Transform, heights: &[f32]) -> Self {
        let eye = cam.translation;
        let fwd = cam.forward().with_y(0.0).normalize_or(Vec3::NEG_Z);
        let right = fwd.cross(Vec3::Y);
        let feet = |p: Vec3| ground_under(world, p, eye.y);
        // In sight: `ahead` metres out and `side` to the right, nearer when a wall comes first.
        let seen = |ahead: f32, side: f32| {
            let dir = (fwd * ahead + right * side).normalize();
            let reach = (fwd * ahead + right * side).length();
            let free = world.raycast(eye, dir, reach + 1.0).map_or(reach, |(d, _)| (d - 1.0).clamp(2.0, reach));
            feet(eye + dir * free)
        };
        let ally_seen = seen(7.0, -1.6);
        let enemy_seen = seen(10.0, 2.2);
        let joiner = seen(5.5, 0.6);
        // Behind the first wall straight ahead or a little to the side: the nearest spot past it that is clear
        // of the walls and hidden from the camera.
        let mut ally_hidden = feet(eye + fwd * 14.0);
        'search: for deg in [0.0f32, 6.0, -6.0, 12.0, -12.0, 18.0, -18.0, 24.0, -24.0] {
            let dir = Quat::from_rotation_y(deg.to_radians()) * fwd;
            let Some((d, _)) = world.raycast(eye, dir, 30.0) else { continue };
            if d < 3.0 {
                continue;
            }
            for past in [1.5, 2.5, 3.5, 5.0] {
                let p = feet(eye + dir * (d + past));
                let body = p + Vec3::Y * 0.95;
                let clear = !world.trace_box(body, body + Vec3::Y * 0.01, Vec3::new(0.3, 0.85, 0.3)).start_solid;
                // Wholly hidden: the body's sides too, not just its middle.
                let side = dir.cross(Vec3::Y) * 0.6;
                let hidden = [Vec3::ZERO, side, -side]
                    .iter()
                    .all(|s| !in_sight(world, eye, &sight_points(p + *s, Stance::Stand, heights)));
                if clear && hidden {
                    ally_hidden = p;
                    break 'search;
                }
            }
        }
        DemoSpots { ally_seen, ally_hidden, enemy_seen, joiner }
    }
}

/// The floor under `p` (looked for from height `from_y` down), or `p` at its own height without one.
fn ground_under(world: &CollisionWorld, p: Vec3, from_y: f32) -> Vec3 {
    let start = Vec3::new(p.x, from_y, p.z);
    match world.raycast(start, Vec3::NEG_Y, 30.0) {
        Some((d, _)) => start - Vec3::Y * d,
        None => Vec3::new(p.x, 0.0, p.z),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::{TeamColours, team_pair};
    use vetf_sim::movement::collision::{Brush, BrushKind};

    fn data() -> &'static FriendFoeData {
        FriendFoeData::embedded()
    }

    /// Item 17: only a teammate in a mode with sides glows; free-for-all, the range and anyone without a side
    /// are plain, whoever they are.
    #[test]
    fn only_teammates_in_a_team_mode_are_allies() {
        use MatchMode::*;
        let (a, b) = (Some(Team::A), Some(Team::B));
        assert!(is_ally(Some(Tdm), a, a) && is_ally(Some(Tdm), b, b));
        assert!(!is_ally(Some(Tdm), a, b) && !is_ally(Some(Tdm), b, a), "the other team");
        for mode in [Some(Ffa), Some(Range), None] {
            assert!(!is_ally(mode, a, a), "{mode:?}: no sides, so no allies");
        }
        assert!(!is_ally(Some(Tdm), None, None), "no side yet");
        assert!(!is_ally(Some(Tdm), a, None) && !is_ally(Some(Tdm), None, a));
        // every mode with sides has allies (the extraction mode's squads will be such sides)
        for mode in MatchMode::ALL {
            assert_eq!(is_ally(Some(mode), a, a), mode.has_teams(), "{mode:?}");
        }
    }

    /// Nothing about an enemy's look tells their side: the material of anyone who is not a teammate is the
    /// same plain one, with no glow, whatever their team or the mode; a teammate's glows in the ally colour.
    #[test]
    fn enemies_look_plain_and_teammates_glow() {
        let d = data();
        let plain = RimUniform::new(&d.rim, None);
        assert_eq!(plain, RimUniform::default());
        assert_eq!(plain.color.w, 0.0, "no glow");
        let mut materials = Assets::<BodyMaterial>::default();
        let (x, y) = (BodyLook::new(d, &mut materials), BodyLook::new(d, &mut materials));
        let get = |h: &Handle<BodyMaterial>| materials.get(h).unwrap().clone();
        assert_eq!(get(&x.body).base.base_color, get(&y.body).base.base_color, "one body colour for all");
        assert_eq!(get(&x.body).extension.rim, plain, "a new body is plain");
        assert_ne!(x.body, y.body, "each player has their own material");
        for preset in TeamColours::ALL {
            let (ally, _) = team_pair(*preset);
            let glow = RimUniform::new(&d.rim, Some(ally));
            assert_eq!(glow.color.w, d.rim.strength, "{preset:?}");
            let l = ally.to_linear();
            assert_eq!(glow.color.truncate(), Vec3::new(l.red, l.green, l.blue), "{preset:?}: the ally colour");
        }
    }

    /// The glow is never red, in every colour-blind preset (red reads as an enemy), and stands apart from the
    /// enemy colour.
    #[test]
    fn the_ally_glow_is_never_red() {
        for preset in TeamColours::ALL {
            let (ally, enemy) = team_pair(*preset);
            let h = Hsla::from(ally);
            assert!((60.0..=300.0).contains(&h.hue), "{preset:?}: ally hue {}", h.hue);
            assert!(h.saturation > 0.3 && h.lightness > 0.3, "{preset:?}: a clear colour, not grey or dark");
            let e = Hsla::from(enemy);
            let apart = (h.hue - e.hue).abs().min(360.0 - (h.hue - e.hue).abs());
            assert!(apart > 60.0, "{preset:?}: ally {} vs enemy {}", h.hue, e.hue);
        }
    }

    #[test]
    fn the_data_file_parses_with_sane_numbers() {
        let d = data();
        assert_eq!(*d, ron::from_str::<FriendFoeData>(EMBEDDED).unwrap());
        let r = d.rim;
        assert!(r.strength > 0.0 && r.strength < 5.0 && r.power >= 1.0 && (0.0..0.5).contains(&r.fill));
        let m = &d.marker;
        assert!(0.0 < m.near_m && m.near_m < m.far_m && m.far_m <= m.hide_m, "{m:?}");
        assert!((0.0..=1.0).contains(&m.far_alpha) && m.font_px >= 10.0 && m.above_head_m > 0.0);
        assert!(!m.sight_heights_m.is_empty() && m.sight_heights_m.iter().all(|h| (0.0..2.0).contains(h)));
        // a neutral body: no channel stands out (no team colour sneaks back in)
        let c = d.body_color;
        let spread = c.iter().cloned().fold(f32::MIN, f32::max) - c.iter().cloned().fold(f32::MAX, f32::min);
        assert!(spread < 0.1, "{c:?}");
        let shader = crate::config::assets_root().join(SHADER);
        let wgsl = std::fs::read_to_string(&shader).unwrap_or_else(|e| panic!("{}: {e}", shader.display()));
        assert!(wgsl.contains("@binding(100) var<uniform> rim: Rim"), "the shader reads the uniform at 100");
    }

    /// Markers fade with distance: full close by, the data's floor far away, gone past the hide distance.
    #[test]
    fn markers_fade_with_distance() {
        let m = &data().marker;
        assert_eq!(marker_alpha(m, 0.0), 1.0);
        assert_eq!(marker_alpha(m, m.near_m), 1.0);
        assert!((marker_alpha(m, m.far_m) - m.far_alpha).abs() < 1e-5);
        assert!((marker_alpha(m, m.hide_m) - m.far_alpha).abs() < 1e-5);
        assert_eq!(marker_alpha(m, m.hide_m + 1.0), 0.0);
        let mut last = 1.0;
        for i in 0..=200 {
            let a = marker_alpha(m, i as f32);
            assert!(a <= last + 1e-6, "{i} m: {a} > {last}");
            last = a;
        }
    }

    /// A teammate behind a wall is out of sight (their marker shows); one peeking over it or beside it is in
    /// sight (the glow is enough). Crouched, the sight points come down with the body.
    #[test]
    fn walls_hide_a_teammate_from_the_camera() {
        let mut w = CollisionWorld::default();
        // a 2.2 m wall across the view, 5 m ahead
        w.push(Brush::cuboid(Vec3::new(-3.0, 0.0, -5.2), Vec3::new(3.0, 2.2, -5.0), BrushKind::Solid));
        // an invisible player clip stops players only, never sight
        w.push(Brush::cuboid(Vec3::new(-10.0, 0.0, -2.0), Vec3::new(10.0, 3.0, -1.9), BrushKind::PlayerClip));
        let eye = Vec3::new(0.0, 1.7, 0.0);
        let heights = &data().marker.sight_heights_m;
        let behind = Vec3::new(0.0, 0.0, -9.0);
        assert!(!in_sight(&w, eye, &sight_points(behind, Stance::Stand, heights)), "behind the wall");
        assert!(!in_sight(&w, eye, &sight_points(behind, Stance::Crouch, heights)), "crouched behind it");
        let beside = Vec3::new(6.0, 0.0, -9.0);
        assert!(in_sight(&w, eye, &sight_points(beside, Stance::Stand, heights)), "beside the wall");
        // on a 1 m step behind the wall the head shows over it
        let raised = Vec3::new(0.0, 1.0, -9.0);
        assert!(in_sight(&w, Vec3::new(0.0, 2.6, 0.0), &sight_points(raised, Stance::Stand, heights)));
        let crouched = sight_points(Vec3::ZERO, Stance::Crouch, &[1.0]);
        assert!(crouched[0].y < 1.0, "crouched points squash with the body");
    }

    /// The demo's spots: the two in sight are in sight, the hidden teammate is behind the wall and not inside it.
    #[test]
    fn the_demo_puts_one_teammate_behind_a_wall() {
        let mut w = CollisionWorld::default();
        w.push(Brush::cuboid(Vec3::new(-50.0, -1.0, -50.0), Vec3::new(50.0, 0.0, 50.0), BrushKind::Solid));
        w.push(Brush::cuboid(Vec3::new(-4.0, 0.0, -13.0), Vec3::new(4.0, 3.0, -12.4), BrushKind::Solid));
        let cam = Transform::from_xyz(0.0, 1.7, 0.0).looking_to(Vec3::NEG_Z, Vec3::Y);
        let heights = &data().marker.sight_heights_m;
        let s = DemoSpots::around(&w, &cam, heights);
        for p in [s.ally_seen, s.enemy_seen, s.joiner] {
            assert!(p.y.abs() < 0.01, "on the floor: {p}");
            assert!(in_sight(&w, cam.translation, &sight_points(p, Stance::Stand, heights)), "{p}");
        }
        assert!(s.ally_hidden.z < -12.4 && s.ally_hidden.y.abs() < 0.01, "past the wall: {}", s.ally_hidden);
        assert!(!in_sight(&w, cam.translation, &sight_points(s.ally_hidden, Stance::Stand, heights)));
    }
}
