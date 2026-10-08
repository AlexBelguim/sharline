//! Blockout rendering: level brushes, lighting, first-person camera + viewmodel, other players with their
//! halos and guns, and tracers. The guns are the glTF models (`weapon_models`); the rest is placeholder art.
//!
//! The feel lives in submodules, all visual only (`feel.ron`): the camera's bob and shot shake and the gun's
//! sway ([`camera_fx`]), tracers ([`tracer_fx`]), and hit markers and halo cracks on the player hit ([`hit_fx`]).

mod camera_fx;
pub mod executor;
pub mod feel;
pub mod hit_fx;
mod tracer_fx;

use crate::AppState;
use crate::client::{LocalControl, Smoothed};
use crate::config::{CurrentLevel, Data};
use crate::settings::{MouseSettings, Settings, vertical_fov, zoomed_fov};
use crate::weapon_models::{GunLook, Scope, WeaponModels, face_ahead};
use bevy::asset::RenderAssetUsages;
use bevy::light::NotShadowCaster;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;
use lightyear::prelude::*;
use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_2, PI, TAU};
use vetf_net::*;
use vetf_sim::data::{WeaponClass, WeightClass};
use vetf_sim::level::Team;
use vetf_sim::movement::Stance;
use vetf_sim::movement::collision::{Brush, Look};
use vetf_sim::{Zone, ZoneTable};

pub struct RenderPlugin;

impl Plugin for RenderPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(ClearColor(Color::srgb(0.62, 0.74, 0.86)))
            .insert_resource(GlobalAmbientLight { color: Color::srgb(0.9, 0.92, 1.0), brightness: 900.0, ..default() })
            .init_resource::<ViewmodelRig>()
            .insert_resource(feel::FeelData::load())
            .init_resource::<camera_fx::ViewFeel>()
            .init_resource::<tracer_fx::Tracers>()
            .init_resource::<hit_fx::HitMemory>()
            .init_resource::<hit_fx::ShardAssets>()
            .init_resource::<SmoothedAds>()
            .init_resource::<StepEye>()
            .add_message::<hit_fx::HaloHit>()
            .add_systems(Startup, setup_menu_camera)
            .add_systems(FixedPostUpdate, (record_ads, record_footing))
            .add_systems(
                OnEnter(AppState::InGame),
                (spawn_level, spawn_view_camera, tracer_fx::spawn_tracer_mesh, hit_fx::spawn_marker_layer),
            )
            .add_systems(OnEnter(AppState::MainMenu), setup_menu_camera)
            .add_systems(
                Update,
                (
                    attach_player_visuals,
                    tint_bodies,
                    sync_held_guns,
                    sync_halos,
                    update_player_visuals,
                    sync_viewmodel,
                    camera_fx::step_feel.before(update_camera),
                    smooth_step_eye.before(update_camera),
                    update_camera,
                )
                    .run_if(in_state(AppState::InGame)),
            )
            // Drawn for this frame's camera and player poses.
            .add_systems(
                Update,
                (
                    tracer_fx::draw_tracers,
                    (hit_fx::demo_hit_fx, hit_fx::take_hits, hit_fx::place_markers).chain(),
                    (hit_fx::watch_halos, hit_fx::crack_halos, hit_fx::flash_arcs, hit_fx::fly_shards).chain(),
                )
                    .after(update_camera)
                    .after(update_player_visuals)
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

/// The vertical field of view (radians) of a camera's projection (a non-perspective one counts as 78 degrees).
pub fn vfov_of(projection: &Projection) -> f32 {
    match projection {
        Projection::Perspective(p) => p.fov,
        _ => 78f32.to_radians(),
    }
}

/// UI-only camera for the menus.
#[derive(Component)]
struct MenuCamera;

/// The first-person camera.
#[derive(Component)]
pub struct ViewCamera;

/// The first-person gun; remembers what it was built as.
#[derive(Component)]
struct Viewmodel(Option<GunLook>);

/// A third-person player's gun, in the right hand; remembers what it was built as and where the hand is.
#[derive(Component)]
struct HeldGun {
    look: Option<GunLook>,
    hand: Vec3,
}

/// Where a gun without a model is held (player space), and the box that stands in for it.
const HELD_PLACEHOLDER: Vec3 = Vec3::new(0.22, 1.35, -0.35);
const HELD_PLACEHOLDER_SIZE: Vec3 = Vec3::new(0.07, 0.1, 0.7);

/// Between the view camera and the viewmodel: squeezes the gun across the view (see [`viewmodel_lens`]).
#[derive(Component)]
struct ViewmodelLens;

#[derive(Component)]
pub(crate) struct PlayerVisual;

/// A player's body material, recoloured when their team or the mode changes (see [`body_color`]).
#[derive(Component)]
struct BodyTint(Handle<StandardMaterial>);

/// A third-person player's body under its root: the capsule, head and halo, squashed when crouched. The gun is
/// beside it, not under it (see [`PlayerPose`]).
#[derive(Component)]
struct Body;

/// What a player's halo was built from (on their [`Body`]): its arcs are rebuilt when the loadout's tiers or
/// weight class change (a new armor pick shows at the respawn), like the held gun.
#[derive(Component, Debug, Clone, Copy, PartialEq)]
struct HaloLook {
    tiers: ZoneTable<u8>,
    weight: WeightClass,
}

impl HaloLook {
    fn of(loadout: &vetf_sim::player::Loadout) -> HaloLook {
        HaloLook { tiers: loadout.halo.tiers, weight: loadout.weight }
    }

    /// The ring's scale and tube radius: everyone reads the weight class from the halo's size.
    fn size(&self) -> (f32, f32) {
        match self.weight {
            WeightClass::Heavy => (1.2, 0.022),
            WeightClass::Medium => (1.0, 0.016),
            _ => (0.85, 0.011),
        }
    }
}

/// The ADS blend between fixed ticks. The simulation moves it once a tick, so the zoom and the gun coming up
/// stepped at the tick rate (8 steps for the Mako's ADS at 60 Hz) while the eye moved smoothly; this keeps the
/// last two ticks' values and blends them by the overstep, like the eye's position.
#[derive(Resource, Debug, Default, Clone, Copy, PartialEq)]
pub struct SmoothedAds {
    prev: f32,
    curr: f32,
}

impl SmoothedAds {
    /// The blend `overstep` (0..1) of the way from the last tick's ADS to this tick's.
    pub fn at(&self, overstep: f32) -> f32 {
        self.prev + (self.curr - self.prev) * overstep.clamp(0.0, 1.0)
    }

    pub fn record(&mut self, ads: f32) {
        (self.prev, self.curr) = (self.curr, ads);
    }
}

fn record_ads(me: Query<&PlayerWeapon, With<Controlled>>, mut ads: ResMut<SmoothedAds>) {
    ads.record(me.iter().next().map_or(0.0, |w| w.0.ads));
}

/// The view over a step: Showhome's kerbs lift the feet 11 cm in one tick and the view jumped with them (map-kit
/// review K9). While our player stands on flat ground (this tick and the last, so a step between two flat
/// surfaces), the eye's height follows the feet over `feel.ron`'s `camera.step_smooth_s`; on a slope, in the air
/// or after a jump larger than a step it follows them at once.
#[derive(Resource, Debug, Default, Clone, Copy, PartialEq)]
pub struct StepEye {
    /// On flat ground now and the tick before.
    steady: bool,
    flat: bool,
    /// The smoothed feet height, and how far the eye is below (or above) the feet's own this frame.
    feet_y: Option<f32>,
    pub offset: f32,
}

/// The smoothed feet height this frame: toward `raw` over `tau` while `steady` and within a step of it, else
/// `raw` at once.
pub fn step_eye(smoothed: Option<f32>, raw: f32, steady: bool, max_step: f32, dt: f32, tau: f32) -> f32 {
    match smoothed {
        Some(y) if steady && (raw - y).abs() <= max_step && tau > 0.0 => y + (raw - y) * (1.0 - (-dt / tau).exp()),
        _ => raw,
    }
}

/// Per tick: whether our player stands on flat ground (grounded, the level's surface under the feet level).
fn record_footing(
    level: Option<Res<CurrentLevel>>,
    me: Query<&PlayerMove, With<Controlled>>,
    mut step: ResMut<StepEye>,
) {
    let flat = match (level, me.iter().next()) {
        (Some(level), Some(mv)) if mv.0.mode == vetf_sim::movement::MoveMode::Ground => {
            level.world.raycast(mv.0.pos + Vec3::Y * 0.3, Vec3::NEG_Y, 0.6).is_some_and(|(_, normal)| normal.y > 0.99)
        }
        _ => false,
    };
    step.steady = flat && step.flat;
    step.flat = flat;
}

/// This frame's eye offset over a step (see [`StepEye`]), from the feet as `update_camera` draws them.
fn smooth_step_eye(
    time: Res<Time>,
    fixed: Res<Time<Fixed>>,
    game: Res<Data>,
    feel: Res<feel::FeelData>,
    me: Query<(&PlayerMove, Option<&Smoothed>, &Vitals), With<Controlled>>,
    mut step: ResMut<StepEye>,
) {
    let Some((mv, smoothed, vitals)) = me.iter().next() else { return };
    let raw = smoothed.map_or(mv.0.pos, |s| s.prev.lerp(s.curr, fixed.overstep_fraction())).y;
    let steady = step.steady && !vitals.health.dead;
    let max = game.movement.ground.step_height;
    let y = step_eye(step.feet_y, raw, steady, max, time.delta_secs(), feel.camera.step_smooth_s);
    step.feet_y = Some(y);
    step.offset = y - raw;
}

/// One arc of a third-person player's halo: its zone, tier, and the ring's radius (its mesh is centred on the
/// halo's middle, the arc `radius` out at [`arc_angle`]).
#[derive(Component)]
pub(crate) struct HaloArc {
    pub zone: Zone,
    pub tier: u8,
    pub radius: f32,
}

/// An arc's glow (emissive) at rest: its tier colour, none for an empty arc.
pub(crate) fn arc_glow(tier: u8) -> LinearRgba {
    if tier > 0 { tier_color(tier) * 1.5 } else { LinearRgba::BLACK }
}

#[derive(Component)]
struct BodyPart;

/// Menus and the connecting screen use a plain 2D camera; the match has its own 3D view camera.
fn setup_menu_camera(mut commands: Commands, existing: Query<(), With<MenuCamera>>) {
    if existing.is_empty() {
        commands.spawn((MenuCamera, Camera2d, DespawnOnEnter(AppState::InGame)));
    }
}

/// Palette from art/STYLE_GUIDE.md (graphite, bone, sand, olive...) plus readable blockout colours.
pub(crate) fn look_color(look: Look) -> (Color, f32) {
    let c = match look {
        Look::Ground => Color::srgb(0.42, 0.47, 0.36),
        Look::Floor => Color::srgb(0.58, 0.52, 0.44),
        Look::Wall => Color::srgb(0.88, 0.83, 0.74),
        Look::Roof => Color::srgb(0.32, 0.30, 0.33),
        Look::Trim => Color::srgb(0.93, 0.91, 0.87),
        Look::Prop => Color::srgb(0.60, 0.49, 0.37),
        Look::Hedge => Color::srgb(0.24, 0.40, 0.22),
        Look::Fence => Color::srgb(0.82, 0.80, 0.74),
        Look::Glass => Color::srgba(0.60, 0.80, 0.92, 0.35),
        Look::Vehicle => Color::srgb(0.80, 0.76, 0.66),
        Look::Metal => Color::srgb(0.36, 0.38, 0.42),
        Look::Concrete => Color::srgb(0.64, 0.64, 0.62),
        Look::Water => Color::srgb(0.22, 0.46, 0.56),
        Look::TeamA => Color::srgb(0.0, 0.62, 0.56),
        Look::TeamB => Color::srgb(0.93, 0.38, 0.32),
        Look::Accent => Color::srgb(0.95, 0.74, 0.22),
        Look::Target => Color::srgb(0.86, 0.86, 0.84),
        Look::Asphalt => Color::srgb_u8(112, 105, 106),
        Look::Paving => Color::srgb_u8(175, 162, 154),
        Look::Gravel => Color::srgb_u8(173, 153, 137),
        Look::CladSage => Color::srgb_u8(145, 153, 114),
        Look::CladClay => Color::srgb_u8(207, 134, 96),
        Look::Invisible => Color::NONE,
    };
    let rough = match look {
        Look::Metal | Look::Vehicle => 0.45,
        Look::Glass | Look::Water => 0.1,
        _ => 0.8,
    };
    (c, rough)
}

fn spawn_level(
    mut commands: Commands,
    level: Res<CurrentLevel>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let showhome = level.name.eq_ignore_ascii_case("showhome");
    if showhome {
        // Showhome's real art scenes and sagging zipline are loaded by ShowhomeKitPlugin. The simulation
        // still uses these brushes for collision; drawing them too would obscure the kit with boxes.
        commands.spawn((
            DirectionalLight {
                color: Color::linear_rgb(1.0, 0.84, 0.66),
                illuminance: 9000.0,
                shadow_maps_enabled: true,
                ..default()
            },
            crate::showhome_kit::sun_transform(),
            DespawnOnExit(AppState::InGame),
        ));
        return;
    }
    let mut mats: HashMap<Look, Handle<StandardMaterial>> = HashMap::new();
    let mut mat = |look: Look, materials: &mut Assets<StandardMaterial>| {
        mats.entry(look)
            .or_insert_with(|| {
                let (color, rough) = look_color(look);
                let alpha = color.alpha() < 1.0;
                materials.add(StandardMaterial {
                    base_color: color,
                    perceptual_roughness: rough,
                    alpha_mode: if alpha { AlphaMode::Blend } else { AlphaMode::Opaque },
                    double_sided: true,
                    cull_mode: None,
                    ..default()
                })
            })
            .clone()
    };
    let root = commands
        .spawn((
            Name::new(format!("Level {}", level.name)),
            Transform::default(),
            Visibility::default(),
            DespawnOnExit(AppState::InGame),
        ))
        .id();
    for b in &level.world.brushes {
        if b.look == Look::Invisible {
            continue;
        }
        let center = (b.min + b.max) * 0.5;
        let mesh = match b.ramp {
            Some(dir) => wedge_mesh(b, dir),
            None => Mesh::from(Cuboid::from_size(b.max - b.min)),
        };
        let material = mat(b.look, &mut materials);
        commands.spawn((
            Mesh3d(meshes.add(mesh)),
            MeshMaterial3d(material),
            Transform::from_translation(center),
            ChildOf(root),
        ));
    }
    // Zipline cables.
    let cable = materials.add(StandardMaterial { base_color: Color::srgb(0.1, 0.1, 0.12), ..default() });
    for z in &level.ziplines {
        let len = z.a.distance(z.b);
        let mid = (z.a + z.b) * 0.5;
        commands.spawn((
            Mesh3d(meshes.add(Cylinder::new(0.025, len))),
            MeshMaterial3d(cable.clone()),
            Transform::from_translation(mid).with_rotation(Quat::from_rotation_arc(Vec3::Y, (z.b - z.a).normalize())),
            ChildOf(root),
        ));
    }
    commands.spawn((
        DirectionalLight { color: Color::WHITE, illuminance: 9000.0, shadow_maps_enabled: true, ..default() },
        Transform::from_xyz(30.0, 60.0, 20.0).looking_at(Vec3::new(36.0, 0.0, -24.0), Vec3::Y),
        DespawnOnExit(AppState::InGame),
    ));
}

/// A ramp's wedge, built rising along +X and rotated to its rise direction. Every face winds counter-clockwise
/// seen from outside, with its normal pointing out, so a material that culls back faces draws its outside (a
/// wedge wound inside out once drew its slope only from inside: the gable roofs and the stairs looked hollow).
fn wedge_mesh(b: &Brush, rise: Vec3) -> Mesh {
    let size = b.max - b.min;
    let along_x = rise.x.abs() > 0.5;
    let (hx, hy, hz) = if along_x { (size.x, size.y, size.z) } else { (size.z, size.y, size.x) };
    let (hx, hy, hz) = (hx * 0.5, hy * 0.5, hz * 0.5);
    let rot = Quat::from_rotation_y((-rise.z).atan2(rise.x));
    let p = |x: f32, y: f32, z: f32| rot * Vec3::new(x, y, z);
    let (a, bb, c, d) = (p(-hx, -hy, -hz), p(hx, -hy, -hz), p(hx, -hy, hz), p(-hx, -hy, hz));
    let (e, f) = (p(hx, hy, -hz), p(hx, hy, hz));
    // Bottom, high end, slope, and the two triangular sides.
    let faces: [&[Vec3]; 5] = [&[a, bb, c, d], &[bb, e, f, c], &[a, d, f, e], &[a, e, bb], &[d, c, f]];
    let mut positions = Vec::new();
    let mut normals = Vec::new();
    let mut indices = Vec::new();
    for face in faces {
        let n = (face[1] - face[0]).cross(face[2] - face[0]).normalize_or_zero();
        let base = positions.len() as u32;
        for v in face {
            positions.push(v.to_array());
            normals.push(n.to_array());
        }
        for i in 1..face.len() as u32 - 1 {
            indices.extend_from_slice(&[base, base + i, base + i + 1]);
        }
    }
    let uvs = vec![[0.0, 0.0]; positions.len()];
    Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
        .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
        .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, uvs)
        .with_inserted_indices(Indices::U32(indices))
}

/// A torus segment (for halo arcs): `radius` of the ring, `tube` radius, from angle `a0` to `a1` around +Y.
fn arc_mesh(radius: f32, tube: f32, a0: f32, a1: f32) -> Mesh {
    let (seg, ring) = (16u32, 8u32);
    let mut positions = Vec::new();
    let mut normals = Vec::new();
    let mut indices = Vec::new();
    for i in 0..=seg {
        let a = a0 + (a1 - a0) * i as f32 / seg as f32;
        let center = Vec3::new(a.cos() * radius, 0.0, a.sin() * radius);
        let out = Vec3::new(a.cos(), 0.0, a.sin());
        for j in 0..=ring {
            let b = TAU * j as f32 / ring as f32;
            let n = out * b.cos() + Vec3::Y * b.sin();
            positions.push((center + n * tube).to_array());
            normals.push(n.to_array());
        }
    }
    let row = ring + 1;
    for i in 0..seg {
        for j in 0..ring {
            let (k0, k1) = (i * row + j, (i + 1) * row + j);
            indices.extend_from_slice(&[k0, k1, k0 + 1, k0 + 1, k1, k1 + 1]);
        }
    }
    let uvs = vec![[0.0, 0.0]; positions.len()];
    Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default())
        .with_inserted_attribute(Mesh::ATTRIBUTE_POSITION, positions)
        .with_inserted_attribute(Mesh::ATTRIBUTE_NORMAL, normals)
        .with_inserted_attribute(Mesh::ATTRIBUTE_UV_0, uvs)
        .with_inserted_indices(Indices::U32(indices))
}

/// Halo tier colours (art/HALO_SHIELD_SPEC.md), linear RGB.
pub fn tier_color(tier: u8) -> LinearRgba {
    match tier {
        1 => LinearRgba::rgb(0.85, 0.88, 0.92),
        2 => LinearRgba::rgb(0.10, 0.45, 1.0),
        3 => LinearRgba::rgb(0.55, 0.15, 1.0),
        4 => LinearRgba::rgb(1.0, 0.62, 0.08),
        _ => LinearRgba::rgb(0.02, 0.02, 0.025),
    }
}

pub fn team_color(team: Option<Team>) -> Color {
    match team {
        Some(Team::A) => Color::srgb(0.0, 0.70, 0.62),
        Some(Team::B) => Color::srgb(1.0, 0.36, 0.30),
        None => Color::srgb(0.75, 0.75, 0.78),
    }
}

/// The colour another player's body is drawn in: their team's, or in free-for-all the enemy colour (HUD &
/// ACCESSIBILITY's team colours), since everyone else is an enemy there.
pub fn body_color(team: Option<Team>, mode: Option<MatchMode>, enemy: Color) -> Color {
    if mode == Some(MatchMode::Ffa) { enemy } else { team_color(team) }
}

/// Keep every body in the colour [`body_color`] gives (a lobby can switch between team deathmatch and
/// free-for-all, and players between teams).
fn tint_bodies(
    matches: Query<&MatchState>,
    settings: Res<Settings>,
    players: Query<(&PlayerInfo, &BodyTint)>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let mode = matches.iter().next().map(|m| m.mode);
    let enemy = settings.team_colors().1;
    for (info, tint) in &players {
        let want = body_color(info.team, mode, enemy).darker(0.25);
        if materials.get(&tint.0).is_some_and(|m| m.base_color != want)
            && let Some(mut m) = materials.get_mut(&tint.0)
        {
            m.base_color = want;
        }
    }
}

/// Arc centre angle in the player's local frame (facing -Z): front = head, left = arms, back = torso,
/// right = legs (seen from above), per the halo spec.
pub(crate) fn arc_angle(zone: Zone) -> f32 {
    // angle measured from +X toward +Z (arc_mesh convention)
    match zone {
        Zone::Head => -FRAC_PI_2, // -Z, in front
        Zone::Arms => PI,         // -X, the player's left
        Zone::Torso => FRAC_PI_2, // +Z, behind
        Zone::Legs => 0.0,        // +X, the player's right
    }
}

#[allow(clippy::type_complexity)]
fn attach_player_visuals(
    mut commands: Commands,
    players: Query<(Entity, &PlayerInfo, &PlayerLoadout), (With<PlayerId>, Without<Controlled>, Without<PlayerVisual>)>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    for (e, info, loadout) in &players {
        let team = team_color(info.team);
        let body_mat =
            materials.add(StandardMaterial { base_color: team.darker(0.25), perceptual_roughness: 0.7, ..default() });
        let head_mat = materials.add(StandardMaterial { base_color: Color::srgb(0.62, 0.48, 0.40), ..default() });
        let halo = HaloLook::of(&loadout.0);
        commands.entity(e).insert(BodyTint(body_mat.clone()));
        commands.entity(e).insert((PlayerVisual, Transform::default(), Visibility::default())).with_children(|p| {
            p.spawn((Body, halo, Transform::default(), Visibility::default())).with_children(|b| {
                b.spawn((
                    BodyPart,
                    Mesh3d(meshes.add(Capsule3d::new(0.26, 0.9))),
                    MeshMaterial3d(body_mat),
                    Transform::from_xyz(0.0, 0.85, 0.0),
                ));
                b.spawn((
                    BodyPart,
                    Mesh3d(meshes.add(Sphere::new(0.13))),
                    MeshMaterial3d(head_mat),
                    Transform::from_xyz(0.0, 1.6, 0.0),
                ));
                spawn_halo_arcs(b, halo, &mut meshes, &mut materials);
            });
            // The gun is built by `sync_held_guns` (and rebuilt when the loadout changes).
            p.spawn((
                HeldGun { look: None, hand: HELD_PLACEHOLDER },
                Transform::from_translation(HELD_PLACEHOLDER),
                Visibility::default(),
            ));
        });
    }
}

/// A halo's four arcs, one per zone, under a body: each in its tier's colour with its own material (a hit
/// flashes just that arc, `hit_fx`), the ring sized by the weight class.
fn spawn_halo_arcs(
    body: &mut ChildSpawnerCommands,
    halo: HaloLook,
    meshes: &mut Assets<Mesh>,
    materials: &mut Assets<StandardMaterial>,
) {
    let (scale, tube) = halo.size();
    for zone in Zone::ALL {
        let tier = halo.tiers[zone];
        let c = tier_color(tier);
        let mat = materials.add(StandardMaterial {
            base_color: if tier > 0 { Color::from(c) } else { Color::srgba(0.02, 0.02, 0.025, 0.5) },
            emissive: arc_glow(tier),
            alpha_mode: if tier > 0 { AlphaMode::Opaque } else { AlphaMode::Blend },
            ..default()
        });
        let mid = arc_angle(zone);
        let gap = 0.12;
        let radius = 0.16 * scale;
        body.spawn((
            HaloArc { zone, tier, radius },
            Mesh3d(meshes.add(arc_mesh(radius, tube, mid - FRAC_PI_2 * 0.5 + gap, mid + FRAC_PI_2 * 0.5 - gap))),
            MeshMaterial3d(mat),
            Transform::from_xyz(0.0, 1.95, 0.0),
        ));
    }
}

/// Rebuilds a player's halo when their loadout's tiers or weight class differ from what it was built from (a new
/// armor pick at a respawn): the old arcs go, new ones in the new tiers and size take their place.
fn sync_halos(
    mut commands: Commands,
    players: Query<(&PlayerLoadout, &Children), With<PlayerVisual>>,
    mut bodies: Query<(Entity, &mut HaloLook, &Children), With<Body>>,
    arcs: Query<(), With<HaloArc>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    for (loadout, children) in &players {
        let want = HaloLook::of(&loadout.0);
        let mut iter = bodies.iter_many_mut(children);
        while let Some((body, mut built, parts)) = iter.fetch_next() {
            if *built == want {
                continue;
            }
            for part in parts.iter().filter(|p| arcs.contains(*p)) {
                commands.entity(part).despawn();
            }
            commands.entity(body).with_children(|b| spawn_halo_arcs(b, want, &mut meshes, &mut materials));
            *built = want;
        }
    }
}

/// Builds (or rebuilds) each other player's gun from their loadout: the model at real scale with its
/// attachments, gripped in the right hand, or a box for a gun without a model.
fn sync_held_guns(
    mut commands: Commands,
    data: Res<Data>,
    models: Res<WeaponModels>,
    players: Query<(&PlayerLoadout, &Children), With<PlayerVisual>>,
    mut held: Query<(Entity, &mut HeldGun)>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut box_material: Local<Option<Handle<StandardMaterial>>>,
) {
    for (loadout, children) in &players {
        let look = models.look(&data, &loadout.0.weapon);
        let mut iter = held.iter_many_mut(children);
        while let Some((e, mut gun)) = iter.fetch_next() {
            if gun.look.as_ref() == Some(&look) {
                continue;
            }
            commands.entity(e).despawn_children();
            match &look {
                GunLook::Model(key) => {
                    gun.hand = models.hand(key);
                    models.spawn(&mut commands, e, key, Transform::from_rotation(face_ahead()), false);
                }
                GunLook::Boxes(_) => {
                    gun.hand = HELD_PLACEHOLDER;
                    let material = box_material
                        .get_or_insert_with(|| {
                            materials.add(StandardMaterial { base_color: Color::srgb(0.08, 0.085, 0.10), ..default() })
                        })
                        .clone();
                    commands.spawn((
                        BodyPart,
                        Mesh3d(meshes.add(Cuboid::from_size(HELD_PLACEHOLDER_SIZE))),
                        MeshMaterial3d(material),
                        ChildOf(e),
                    ));
                }
            }
            gun.look = Some(look.clone());
        }
    }
}

#[allow(clippy::type_complexity)]
fn update_player_visuals(
    mut players: Query<
        (
            &PlayerMove,
            &PlayerLook,
            &Vitals,
            &PlayerLoadout,
            &mut Transform,
            &mut Visibility,
            &Children,
            Has<Controlled>,
        ),
        With<PlayerVisual>,
    >,
    tree: Query<&Children>,
    mut bodies: Query<&mut Transform, (With<Body>, Without<PlayerVisual>)>,
    mut arcs: Query<(&HaloArc, &mut Visibility), Without<PlayerVisual>>,
    mut guns: Query<(&HeldGun, &mut Transform), (Without<PlayerVisual>, Without<Body>)>,
) {
    for (mv, look, vitals, loadout, mut t, mut vis, children, mine) in &mut players {
        let pose = PlayerPose::new(mv.0.pos, look, mv.0.stance);
        *t = pose.root;
        // Our own body never shows (it can get visuals if it arrived a frame before `Controlled` did).
        *vis = if vitals.health.dead || mine { Visibility::Hidden } else { Visibility::Inherited };
        for child in children.iter() {
            if let Ok(mut b) = bodies.get_mut(child) {
                *b = pose.body;
                for part in tree.get(child).into_iter().flatten() {
                    if let Ok((arc, mut v)) = arcs.get_mut(*part) {
                        // A broken arc goes dark (it flares back when it regenerates).
                        let up = loadout.0.halo.tiers[arc.zone] == 0 || vitals.halo.shield[arc.zone] > 0.0;
                        *v = if up { Visibility::Inherited } else { Visibility::Hidden };
                    }
                }
            }
            if let Ok((gun, mut g)) = guns.get_mut(child) {
                *g = pose.gun(gun.hand);
            }
        }
    }
}

/// A third-person player's transforms: the root at the feet turned to the yaw, the body under it (squashed
/// when crouched or sliding), and the gun beside the body, under the root. The gun lowers with the hand but is
/// never scaled, so it points exactly along the look: under the body's non-uniform squash its pitch would
/// shear, aiming flatter than the player looks (review finding).
#[derive(Debug, Clone, Copy, PartialEq)]
struct PlayerPose {
    root: Transform,
    body: Transform,
    pitch: f32,
}

impl PlayerPose {
    /// The body's height crouched or sliding, as a share of standing.
    const CROUCH_SQUASH: f32 = 0.68;

    fn new(feet: Vec3, look: &PlayerLook, stance: Stance) -> PlayerPose {
        let squash = if stance == Stance::Stand { 1.0 } else { Self::CROUCH_SQUASH };
        PlayerPose {
            root: Transform::from_translation(feet).with_rotation(Quat::from_rotation_y(look.yaw)),
            body: Transform::from_scale(Vec3::new(1.0, squash, 1.0)),
            pitch: look.pitch,
        }
    }

    /// The gun gripped at `hand` (player space, standing): the grip lowers with the body, the gun turns to the
    /// look's pitch.
    fn gun(&self, hand: Vec3) -> Transform {
        Transform::from_translation(hand * self.body.scale).with_rotation(Quat::from_rotation_x(self.pitch))
    }
}

/// How far the optic has zoomed at an ADS blend (0 hip .. 1 aimed): 1 at the hip, the optic's zoom aimed.
pub fn ads_zoom(zoom: f32, ads: f32) -> f32 {
    1.0 + (zoom.max(1.0) - 1.0) * ads.clamp(0.0, 1.0)
}

/// The view camera's vertical FOV (degrees): the player's FOV (horizontal at 16:9; Bevy keeps the vertical
/// one, so wider screens see more), narrowed by the optic as the gun comes up so that ADS sensitivity has a
/// focal length to match.
pub fn camera_fov(mouse: &MouseSettings, zoom: f32, ads: f32) -> f32 {
    zoomed_fov(vertical_fov(mouse.fov_h), ads_zoom(zoom, ads))
}

/// The viewmodel has no camera of its own. Instead it is squeezed across the view (view-space x and y, by
/// this factor) so it looks drawn with its own vertical FOV `vm_fov` whatever the world camera's `cam_fov`
/// (zoom included): the gun keeps its size on screen. Depth is untouched.
pub fn viewmodel_lens(cam_fov: f32, vm_fov: f32) -> f32 {
    (cam_fov.to_radians() * 0.5).tan() / (vm_fov.clamp(1.0, 179.0).to_radians() * 0.5).tan()
}

fn lens_scale(lens: f32) -> Vec3 {
    Vec3::new(lens, lens, 1.0)
}

/// The visual camera kick (degrees) after the screen-shake setting (percent). The recoil itself turns the
/// view in `client` and is never scaled.
pub fn visual_punch(punch_deg: f32, shake_percent: f32) -> f32 {
    punch_deg * (shake_percent / 100.0).clamp(0.0, 1.0)
}

fn spawn_view_camera(mut commands: Commands, settings: Res<Settings>) {
    let fov = camera_fov(&settings.mouse, 1.0, 0.0);
    commands
        .spawn((
            ViewCamera,
            Camera3d::default(),
            Projection::from(PerspectiveProjection { fov: fov.to_radians(), near: 0.03, ..default() }),
            DistanceFog {
                color: Color::srgb(0.66, 0.76, 0.86),
                falloff: FogFalloff::Linear { start: 80.0, end: 420.0 },
                ..default()
            },
            Transform::from_xyz(0.0, 1.6, 0.0),
            DespawnOnExit(AppState::InGame),
        ))
        .with_children(|cam| {
            let lens = viewmodel_lens(fov, settings.mouse.viewmodel_fov);
            cam.spawn((ViewmodelLens, Transform::from_scale(lens_scale(lens)), Visibility::default())).with_child((
                Viewmodel(None),
                ViewmodelRig::default().hip,
                Visibility::default(),
            ));
        });
}

/// Where the placeholder viewmodel sits in view space (camera-local, -Z forward): from the hip and aimed.
const VIEWMODEL_HIP: Vec3 = Vec3::new(0.2, -0.2, -0.5);
const VIEWMODEL_ADS: Vec3 = Vec3::new(0.0, -0.075, -0.3);
const VIEWMODEL_SCALE: f32 = 0.6;

/// The first-person gun's pose in view space (camera-local, -Z forward) from the hip and aimed, and its muzzle
/// in gun space. A gun model's comes from its sockets (`weapon_models::first_person_rig`); a gun without one
/// uses the placeholder boxes'.
#[derive(Resource, Clone, Copy, Debug, PartialEq)]
pub struct ViewmodelRig {
    pub hip: Transform,
    pub ads: Transform,
    pub muzzle: Vec3,
    /// A magnified optic's picture: fully aimed, the scope view replaces the gun (`weapon_models::scoped`).
    pub scope: Option<Scope>,
}

impl ViewmodelRig {
    pub fn placeholder(class: WeaponClass) -> Self {
        let muzzle = viewmodel_parts(class)
            .into_iter()
            .map(|(size, offset, _)| offset - Vec3::Z * size.z * 0.5)
            .min_by(|a, b| a.z.total_cmp(&b.z))
            .unwrap_or(Vec3::ZERO);
        let scale = Vec3::splat(VIEWMODEL_SCALE);
        ViewmodelRig {
            hip: Transform::from_translation(VIEWMODEL_HIP).with_scale(scale),
            ads: Transform::from_translation(VIEWMODEL_ADS).with_scale(scale),
            muzzle,
            scope: None,
        }
    }

    /// The pose at an ADS blend `ads` (0 hip .. 1 aimed).
    pub fn pose(&self, ads: f32) -> Transform {
        let a = ads.clamp(0.0, 1.0);
        Transform {
            translation: self.hip.translation.lerp(self.ads.translation, a),
            rotation: self.hip.rotation.slerp(self.ads.rotation, a),
            scale: self.hip.scale.lerp(self.ads.scale, a),
        }
    }
}

impl Default for ViewmodelRig {
    fn default() -> Self {
        Self::placeholder(WeaponClass::AssaultRifle)
    }
}

/// The viewmodel's muzzle in view space (camera-local, -Z forward) at an ADS blend `ads` (0 hip .. 1 aimed),
/// through the viewmodel `lens`: own tracers start here, so they come out of the gun on screen instead of
/// hanging under the crosshair.
pub fn viewmodel_muzzle(rig: &ViewmodelRig, ads: f32, lens: f32) -> Vec3 {
    rig.pose(ads).transform_point(rig.muzzle) * lens_scale(lens)
}

/// How far ahead of the eye (metres, on the view axis) an own tracer starts through a magnified scope.
const SCOPED_TRACER_AHEAD: f32 = 0.5;

/// Where an own tracer starts in view space at an ADS blend `ads`: the viewmodel's muzzle, or, fully aimed through
/// a magnified optic (the scope picture shows and the gun is hidden), on the view axis just ahead of the eye, so
/// it leaves the scope's centre instead of streaking up from the hidden muzzle under the reticle.
pub fn own_tracer_start(rig: &ViewmodelRig, ads: f32, lens: f32) -> Vec3 {
    if crate::weapon_models::scoped(rig, ads) {
        Vec3::NEG_Z * SCOPED_TRACER_AHEAD
    } else {
        viewmodel_muzzle(rig, ads, lens)
    }
}

/// Placeholder viewmodel parts per weapon class: (size, offset, material) in gun space (muzzle toward -Z,
/// origin at the grip). Palette from the art bible: graphite receivers, bone furniture, an ice optic glint.
fn viewmodel_parts(class: WeaponClass) -> Vec<(Vec3, Vec3, Part)> {
    use Part::*;
    let v = Vec3::new;
    match class {
        WeaponClass::Smg | WeaponClass::LightAssault => vec![
            (v(0.05, 0.075, 0.26), v(0.0, 0.0, -0.04), Graphite), // compact receiver
            (v(0.035, 0.035, 0.14), v(0.0, 0.005, -0.23), Graphite), // short barrel + shroud
            (v(0.04, 0.10, 0.05), v(0.0, -0.08, 0.02), Bone),     // grip
            (v(0.035, 0.16, 0.045), v(0.0, -0.11, -0.1), Bone),   // straight mag
            (v(0.03, 0.05, 0.16), v(0.0, -0.005, 0.17), Bone),    // stub stock
            (v(0.035, 0.035, 0.04), v(0.0, 0.055, -0.06), Graphite), // red dot body
            (v(0.008, 0.008, 0.004), v(0.0, 0.058, -0.08), Glint),
        ],
        WeaponClass::BoltSniper => vec![
            (v(0.055, 0.075, 0.48), v(0.0, 0.0, -0.02), Graphite),
            (v(0.03, 0.03, 0.62), v(0.0, 0.01, -0.55), Graphite),
            (v(0.04, 0.11, 0.05), v(0.0, -0.08, 0.02), Sand),
            (v(0.035, 0.08, 0.06), v(0.0, -0.07, -0.12), Graphite),
            (v(0.045, 0.09, 0.26), v(0.0, -0.02, 0.32), Sand),
            (v(0.045, 0.045, 0.30), v(0.0, 0.075, -0.05), Graphite), // scope tube
            (v(0.012, 0.012, 0.004), v(0.0, 0.075, 0.102), Glint),
        ],
        _ => vec![
            (v(0.05, 0.07, 0.42), v(0.0, 0.0, 0.0), Graphite),
            (v(0.045, 0.05, 0.36), v(0.0, 0.0, -0.38), Graphite),
            (v(0.04, 0.11, 0.05), v(0.0, -0.08, -0.02), Bone),
            (v(0.04, 0.13, 0.06), v(0.0, -0.09, 0.1), Bone),
            (v(0.045, 0.06, 0.2), v(0.0, -0.01, 0.28), Bone),
            (v(0.05, 0.05, 0.08), v(0.0, 0.06, -0.02), Bone),
            (v(0.012, 0.012, 0.004), v(0.0, 0.065, -0.062), Glint),
        ],
    }
}

#[derive(Clone, Copy)]
enum Part {
    Graphite,
    Bone,
    Sand,
    Glint,
}

/// Build (or rebuild) the viewmodel when our gun changes: its model with the loadout's attachments, or the
/// placeholder boxes for a gun without one (and until the model's files have loaded).
fn sync_viewmodel(
    mut commands: Commands,
    data: Res<Data>,
    models: Res<WeaponModels>,
    me: Query<&PlayerLoadout, With<Controlled>>,
    mut viewmodel: Query<(Entity, &mut Viewmodel)>,
    mut rig: ResMut<ViewmodelRig>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let Some(loadout) = me.iter().next() else { return };
    let look = models.look(&data, &loadout.0.weapon);
    for (e, mut vm) in &mut viewmodel {
        if vm.0.as_ref() == Some(&look) {
            continue;
        }
        vm.0 = Some(look.clone());
        commands.entity(e).despawn_children();
        let class = match &look {
            GunLook::Model(key) => {
                *rig = models.rig(key).unwrap_or_default();
                models.spawn(&mut commands, e, key, Transform::IDENTITY, true);
                continue;
            }
            GunLook::Boxes(class) => *class,
        };
        *rig = ViewmodelRig::placeholder(class);
        let mut mat = |p: Part| {
            let m = match p {
                Part::Graphite => StandardMaterial {
                    base_color: Color::srgb(0.10, 0.105, 0.12),
                    perceptual_roughness: 0.5,
                    ..default()
                },
                Part::Bone => StandardMaterial {
                    base_color: Color::srgb(0.78, 0.74, 0.66),
                    perceptual_roughness: 0.6,
                    ..default()
                },
                Part::Sand => StandardMaterial {
                    base_color: Color::srgb(0.55, 0.45, 0.32),
                    perceptual_roughness: 0.7,
                    ..default()
                },
                Part::Glint => StandardMaterial {
                    base_color: Color::BLACK,
                    emissive: LinearRgba::rgb(0.45, 0.85, 1.0) * 3.0,
                    ..default()
                },
            };
            materials.add(m)
        };
        for (size, offset, part) in viewmodel_parts(class) {
            commands.spawn((
                Mesh3d(meshes.add(Cuboid::from_size(size))),
                MeshMaterial3d(mat(part)),
                Transform::from_translation(offset),
                NotShadowCaster,
                ChildOf(e),
            ));
        }
    }
}

/// The view follows our player; its FOV follows the settings and the optic's zoom, the gun's lens keeps the
/// viewmodel FOV, and the visual kick follows the screen-shake setting (all applied every frame, so a
/// changed setting shows at once). The feel ([`camera_fx`]: bob, shake, the gun's sway and kick) goes on top as a
/// render-only offset: `control`'s yaw and pitch, the aim, are never changed here.
#[allow(clippy::type_complexity)]
fn update_camera(
    cli: Res<crate::config::Cli>,
    control: Res<LocalControl>,
    settings: Res<Settings>,
    fixed: Res<Time<Fixed>>,
    smoothed_ads: Res<SmoothedAds>,
    step: Res<StepEye>,
    rig: Res<ViewmodelRig>,
    feel: Res<camera_fx::ViewFeel>,
    data: Res<feel::FeelData>,
    me: Query<(&PlayerMove, Option<&Smoothed>, &PlayerLoadout, &Vitals), With<Controlled>>,
    mut camera: Query<
        (&mut Transform, &mut Projection),
        (With<ViewCamera>, Without<Viewmodel>, Without<ViewmodelLens>),
    >,
    mut lens: Query<&mut Transform, (With<ViewmodelLens>, Without<Viewmodel>)>,
    mut viewmodel: Query<(&mut Transform, &mut Visibility), With<Viewmodel>>,
    mut logged: Local<Option<(f32, f32)>>,
) {
    let Some((mv, smoothed, loadout, vitals)) = me.iter().next() else { return };
    let m = &settings.mouse;
    if *logged != Some((m.fov_h, m.viewmodel_fov)) {
        *logged = Some((m.fov_h, m.viewmodel_fov));
        info!(
            "view: {} deg horizontal FOV = {:.1} deg vertical, viewmodel {} deg",
            m.fov_h,
            vertical_fov(m.fov_h),
            m.viewmodel_fov
        );
    }
    // Blended between ticks (the sim's ADS steps at the tick rate), as the eye's position is.
    let ads = smoothed_ads.at(fixed.overstep_fraction());
    let fov = camera_fov(m, loadout.0.weapon.zoom, ads);
    for (_, mut projection) in &mut camera {
        let want = fov.to_radians();
        let stale = matches!(&*projection, Projection::Perspective(p) if (p.fov - want).abs() > 1e-6);
        if stale && let Projection::Perspective(p) = &mut *projection {
            p.fov = want;
        }
    }
    for mut t in &mut lens {
        t.scale = lens_scale(viewmodel_lens(fov, m.viewmodel_fov));
    }
    let alpha = fixed.overstep_fraction();
    let feet = smoothed.map_or(mv.0.pos, |s| s.prev.lerp(s.curr, alpha));
    let dead = vitals.health.dead;
    let eye = if dead { feet + Vec3::Y * 3.0 } else { feet + Vec3::Y * (mv.0.eye + step.offset) };
    if let Some((at, target)) = cli.camera {
        for (mut t, _) in &mut camera {
            *t = Transform::from_translation(at).looking_at(target, Vec3::Y);
        }
        // A fixed camera (map and third-person shots) shows no gun of its own.
        for (_, mut v) in &mut viewmodel {
            *v = Visibility::Hidden;
        }
        return;
    }
    let now = if dead { camera_fx::Feel::default() } else { feel.now };
    for (mut t, _) in &mut camera {
        // Aimed, the visual kick is calmed like the shot shake (`feel.ron` camera.ads_shot_mult): both are the
        // same per-shot camera kick, and both lift the sight off where the bullets go while they last.
        let calm = 1.0 + (data.camera.ads_shot_mult - 1.0) * ads.clamp(0.0, 1.0);
        let punch = visual_punch(control.punch, settings.hud.screen_shake) * calm;
        let pitch = if dead { -0.6 } else { control.pitch + punch.to_radians() };
        let view = Quat::from_euler(EulerRot::YXZ, control.yaw, pitch, 0.0);
        t.translation = eye + view * now.camera.shift;
        t.rotation = view * now.camera.rotation();
    }
    let inspect = cli.demo_ui.as_deref().and_then(inspect_side);
    let sprint = &data.gun.sprint_pose;
    for (mut t, mut v) in &mut viewmodel {
        *t = rig.pose(ads);
        // Down while a sprint (an item, a mantle) lowers the gun and while it comes back up; aiming takes over.
        // Eased in and out (`feel.ron`).
        t.translation += Vec3::from(sprint.shift) * now.sprint;
        t.rotation = Quat::from_rotation_y(sprint.yaw_deg.to_radians() * now.sprint) * t.rotation;
        *t = now.gun.move_gun(*t, now.ads);
        if let Some(left) = inspect {
            *t = inspect_pose(&rig, left);
        }
        // Through a magnified optic the scope view takes over from the gun.
        let hidden = dead || crate::weapon_models::scoped(&rig, ads);
        *v = if hidden { Visibility::Hidden } else { Visibility::Inherited };
    }
}

/// `--demo-ui inspect` / `inspect-left`: which side of the gun faces the camera (`true` for the left).
fn inspect_side(demo: &str) -> Option<bool> {
    match demo {
        "inspect" => Some(false),
        "inspect-left" => Some(true),
        _ => None,
    }
}

/// The gun held across the view with its right (or left) side to the camera, the muzzle toward that side of the
/// screen, so screenshots show how the attachments sit. Its middle (a quarter of the way from the grip to the
/// muzzle, the stock being behind the grip) sits in front of the eye, further away for a longer gun.
pub fn inspect_pose(rig: &ViewmodelRig, left: bool) -> Transform {
    let turn = Quat::from_rotation_y(if left { FRAC_PI_2 } else { -FRAC_PI_2 });
    let rotation = turn * rig.ads.rotation;
    let middle = rig.ads.scale * rig.muzzle * 0.25;
    let ahead = 0.5 + middle.length();
    Transform { translation: Vec3::new(0.0, -0.03, -ahead) - rotation * middle, rotation, scale: rig.ads.scale }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Arcs under the players' bodies: (tier, radius) by zone, in `Zone::ALL` order.
    fn halo_arcs(app: &mut App) -> Vec<(Zone, u8, f32)> {
        let mut q = app.world_mut().query::<&HaloArc>();
        let mut arcs: Vec<(Zone, u8, f32)> = q.iter(app.world()).map(|a| (a.zone, a.tier, a.radius)).collect();
        arcs.sort_by_key(|a| Zone::ALL.iter().position(|z| *z == a.0));
        arcs
    }

    /// Finding halo-not-rebuilt-on-loadout-change: a new armor pick (another tier per arc, another weight class)
    /// rebuilds the halo in the new tiers and size, so everyone reads the new weight class from it.
    #[test]
    fn a_new_armor_pick_rebuilds_the_halo() {
        let mut app = App::new();
        app.add_plugins(MinimalPlugins);
        app.init_resource::<Assets<Mesh>>().init_resource::<Assets<StandardMaterial>>();
        app.add_systems(Update, (attach_player_visuals, sync_halos).chain());
        let data = vetf_sim::GameData::embedded();
        let mut loadout = vetf_sim::player::Loadout::default_for(&data, vetf_sim::data::Mode::Tdm);
        loadout.halo.tiers = ZoneTable { head: 1, torso: 1, arms: 1, legs: 1 };
        loadout.weight = WeightClass::Light;
        let player = app
            .world_mut()
            .spawn((PlayerId(7), PlayerInfo { name: "LARK".into(), team: None }, PlayerLoadout(loadout.clone())))
            .id();
        app.update();
        let light = halo_arcs(&mut app);
        assert_eq!(light.len(), 4);
        assert!(light.iter().all(|a| a.1 == 1 && (a.2 - 0.16 * 0.85).abs() < 1e-6), "{light:?}");
        // a respawn with the heavy T4 pick
        loadout.halo.tiers = ZoneTable { head: 4, torso: 4, arms: 3, legs: 2 };
        loadout.weight = WeightClass::Heavy;
        app.world_mut().entity_mut(player).insert(PlayerLoadout(loadout));
        app.update();
        app.update();
        let heavy = halo_arcs(&mut app);
        assert_eq!(heavy.iter().map(|a| a.1).collect::<Vec<_>>(), [4, 4, 3, 2], "{heavy:?}");
        assert!(heavy.iter().all(|a| (a.2 - 0.16 * 1.2).abs() < 1e-6), "the heavy ring: {heavy:?}");
    }

    /// Map-kit review K9: a kerb step on flat ground eases the view up over the time constant instead of a jump;
    /// slopes and jumps (not steady), and anything bigger than a step, follow at once.
    #[test]
    fn a_kerb_step_eases_the_view_up() {
        let (tau, max, dt) = (0.04, 0.35, 1.0 / 240.0);
        let mut y = step_eye(None, 0.0, true, max, dt, tau);
        assert_eq!(y, 0.0);
        y = step_eye(Some(y), 0.11, true, max, dt, tau);
        assert!(y > 0.0 && y < 0.02, "one frame after the step: {y}");
        for _ in 0..72 {
            y = step_eye(Some(y), 0.11, true, max, dt, tau);
        }
        assert!((y - 0.11).abs() < 0.001, "settled after 0.3 s: {y}");
        assert_eq!(step_eye(Some(0.0), 0.11, false, max, dt, tau), 0.11, "not on flat ground: at once");
        assert_eq!(step_eye(Some(0.0), 1.2, true, max, dt, tau), 1.2, "more than a step: at once");
        assert_eq!(step_eye(Some(0.0), 0.11, true, max, dt, 0.0), 0.11, "no smoothing");
    }

    /// Finding ads-blend-steps-at-tick-rate: between two ticks the ADS blend moves smoothly.
    #[test]
    fn the_ads_blend_is_smooth_between_ticks() {
        let mut ads = SmoothedAds::default();
        ads.record(0.25);
        ads.record(0.375);
        assert_eq!(ads.at(0.0), 0.25);
        assert_eq!(ads.at(0.5), 0.3125);
        assert_eq!(ads.at(1.0), 0.375);
        assert_eq!(ads.at(7.0), 0.375, "never past the last tick");
    }

    /// Ramps (the Showhome gables and stairs) draw the brush the sim collides with, wound so back-face culling
    /// keeps the outside: every triangle faces away from the wedge, its stored normal agrees with its winding,
    /// every corner is inside the brush box, and the slope lies on the collision ramp plane.
    #[test]
    fn wedges_face_outward_and_match_the_collision_ramp() {
        use vetf_sim::movement::collision::BrushKind;
        for rise in [Vec3::X, Vec3::NEG_X, Vec3::Z, Vec3::NEG_Z] {
            let (min, max) = (Vec3::new(9.0, 6.2, -27.0), Vec3::new(21.0, 11.2, -22.0));
            let brush = Brush::ramp(min, max, rise, BrushKind::Solid);
            let mesh = wedge_mesh(&brush, rise);
            let centre = (min + max) * 0.5;
            let p = mesh.attribute(Mesh::ATTRIBUTE_POSITION).unwrap().as_float3().unwrap().to_vec();
            let n = mesh.attribute(Mesh::ATTRIBUTE_NORMAL).unwrap().as_float3().unwrap().to_vec();
            let Some(Indices::U32(idx)) = mesh.indices() else { panic!("no indices") };
            // The wedge's own centroid (two thirds of the way to the high end is inside the solid part).
            let inside = centre - Vec3::Y * (max.y - min.y) / 6.0 + rise * (max - min).dot(rise.abs()) / 6.0;
            let slope = brush.planes.last().unwrap();
            let mut slope_tris = 0;
            for t in idx.chunks(3) {
                let [v0, v1, v2] = [0, 1, 2].map(|k| Vec3::from(p[t[k] as usize]) + centre);
                let wound = (v1 - v0).cross(v2 - v0).normalize();
                let stored = Vec3::from(n[t[0] as usize]);
                assert!(wound.dot(stored) > 0.999, "{rise}: winding {wound} vs normal {stored}");
                let mid = (v0 + v1 + v2) / 3.0;
                assert!((mid - inside).dot(wound) > 0.0, "{rise}: triangle at {mid} faces into the wedge");
                for v in [v0, v1, v2] {
                    assert!(v.cmpge(min - 1e-4).all() && v.cmple(max + 1e-4).all(), "{rise}: {v} outside");
                }
                if wound.dot(slope.normal) > 0.999 {
                    slope_tris += 1;
                    for v in [v0, v1, v2] {
                        assert!((v.dot(slope.normal) - slope.dist).abs() < 1e-3, "{rise}: {v} off the ramp plane");
                    }
                }
            }
            assert_eq!(slope_tris, 2, "{rise}: the slope is one quad on the collision plane");
        }
    }

    /// A Mako rig from its real socket places (mako_base.glb, ATT_optic_holo.glb).
    fn mako_rig() -> ViewmodelRig {
        use crate::weapon_models::{Layout, ModelData, RawNode, first_person_rig};
        let node = |name: &str, t: Vec3, extras: Option<&str>| RawNode {
            name: name.into(),
            transform: Transform::from_translation(t),
            children: Vec::new(),
            extras: extras.map(str::to_string),
        };
        let base = Layout::from_nodes(&[
            node("MAKO_SOCKET_Optic", Vec3::new(0.0, 0.084, 0.0855), None),
            node("MAKO_SOCKET_Muzzle", Vec3::new(0.0, 0.05, 0.565), None),
        ]);
        let holo = Layout::from_nodes(&[node(
            "ATT_optic_holo_SOCKET_ADS",
            Vec3::new(0.0, 0.045, -0.0294),
            Some(r#"{"eye_relief_m": 0.0541}"#),
        )]);
        let row = ModelData::embedded().guns.iter().find(|g| g.weapon == "ar7_mako").unwrap();
        first_person_rig(row, &base, Some((&holo, None))).unwrap()
    }

    /// Own tracers start at the gun on screen: right of and below the crosshair from the hip, in front of the
    /// camera, and on the centre line when aimed. The Mako's comes from its muzzle socket; the Skink keeps its
    /// placeholder boxes.
    #[test]
    fn tracers_leave_the_viewmodel_muzzle() {
        let rigs = [
            ("mako model", mako_rig()),
            ("skink boxes", ViewmodelRig::placeholder(WeaponClass::Smg)),
            ("rifle boxes", ViewmodelRig::placeholder(WeaponClass::AssaultRifle)),
        ];
        for (what, rig) in rigs {
            let hip = viewmodel_muzzle(&rig, 0.0, 1.0);
            assert!(hip.x > 0.1 && hip.y < -0.1 && hip.z < -0.5, "{what} hip muzzle {hip}");
            let ads = viewmodel_muzzle(&rig, 1.0, 1.0);
            assert!(ads.x.abs() < 0.01 && ads.y < 0.0 && ads.z < -0.4, "{what} aimed muzzle {ads}");
            // through a lens the muzzle moves across the view, never in depth
            let squeezed = viewmodel_muzzle(&rig, 0.0, 0.5);
            assert!((squeezed - Vec3::new(hip.x * 0.5, hip.y * 0.5, hip.z)).length() < 1e-6, "{what}");
        }
        // Aimed, the Mako's muzzle socket (0.565 m ahead of the grip) is ahead of the eye point by its distance
        // from the holo's eye point (the optic socket, back to the ADS socket, back by the eye relief).
        let aimed = viewmodel_muzzle(&mako_rig(), 1.0, 1.0);
        assert!((aimed.z + (0.565 - (0.0855 - 0.0294 - 0.0541))).abs() < 1e-4, "{aimed}");
        assert!((aimed.y + (0.084 + 0.045 - 0.05)).abs() < 1e-4, "the bore under the sight line: {aimed}");
    }

    /// Fully aimed through a magnified optic the gun hides behind the scope picture, so an own tracer starts on the
    /// view axis just ahead of the eye, the scope's centre, not at the hidden muzzle under the reticle (review
    /// finding: a vertical streak under the scope's cross). Short of fully aimed, or through a 1x sight, it
    /// leaves the muzzle.
    #[test]
    fn scoped_tracers_leave_the_scope_centre() {
        let mut scoped = mako_rig();
        scoped.scope = Some(Scope::Prism);
        let holo = mako_rig();
        let raising = vetf_sim::weapon::ADS_AIMED - 0.05;
        assert!(crate::weapon_models::scoped(&scoped, 1.0) && !crate::weapon_models::scoped(&scoped, raising));
        for lens in [1.0, 0.4] {
            let start = own_tracer_start(&scoped, 1.0, lens);
            assert!(start.truncate().length() < 1e-6 && (-1.0..-0.1).contains(&start.z), "{start}");
            assert!(viewmodel_muzzle(&scoped, 1.0, lens).y < -0.01, "the hidden muzzle is under the centre");
            assert_eq!(own_tracer_start(&scoped, raising, lens), viewmodel_muzzle(&scoped, raising, lens), "gun shown");
            assert_eq!(own_tracer_start(&holo, 1.0, lens), viewmodel_muzzle(&holo, 1.0, lens), "a 1x sight");
        }
        assert_eq!(on_screen(own_tracer_start(&scoped, 1.0, 1.0), 20.0), Vec2::ZERO, "on the scope's centre");
    }

    /// Where a view-space point lands on screen (normalised device units) through a vertical FOV in degrees.
    fn on_screen(p: Vec3, fov: f32) -> Vec2 {
        Vec2::new(p.x, p.y) / (-p.z * (fov.to_radians() * 0.5).tan())
    }

    /// The FOV setting is horizontal at 16:9; aiming narrows it by the optic's zoom, and the viewmodel lens
    /// keeps the gun where a camera with the viewmodel FOV would draw it, at any camera FOV.
    #[test]
    fn fov_zoom_and_viewmodel_lens() {
        let mut mouse = Settings::default().mouse;
        mouse.fov_h = 103.0;
        assert!((camera_fov(&mouse, 3.0, 0.0) - 70.5).abs() < 0.1, "hip: the 16:9 vertical FOV");
        assert_eq!(camera_fov(&mouse, 1.0, 1.0), camera_fov(&mouse, 1.0, 0.0), "no optic, no zoom");
        let aimed = camera_fov(&mouse, 3.0, 1.0);
        let ratio = (aimed.to_radians() * 0.5).tan() / (70.5f32.to_radians() * 0.5).tan();
        assert!((ratio - 1.0 / 3.0).abs() < 0.01, "a 3x optic triples the focal length ({aimed})");
        assert!(camera_fov(&mouse, 3.0, 0.5) < camera_fov(&mouse, 3.0, 0.0), "zooms in as the gun comes up");
        mouse.fov_h = 80.0;
        assert!(camera_fov(&mouse, 1.0, 0.0) < 70.5, "a smaller FOV setting narrows the camera");
        assert_eq!(ads_zoom(0.5, 1.0), 1.0, "a zoom below 1 never widens the view");

        let rig = mako_rig();
        let muzzle = viewmodel_muzzle(&rig, 0.0, 1.0);
        let want = on_screen(muzzle, 68.0);
        for cam in [70.5, 50.0, 26.0] {
            let got = on_screen(viewmodel_muzzle(&rig, 0.0, viewmodel_lens(cam, 68.0)), cam);
            assert!((got - want).length() < 1e-4, "{cam}: {got} vs {want}");
        }
        assert!((viewmodel_lens(68.0, 68.0) - 1.0).abs() < 1e-6);
    }

    /// `--demo-ui inspect`: the gun across the view, its right side to the camera and the muzzle to the right
    /// (`inspect-left` the mirror), in front of the eye.
    #[test]
    fn inspect_turns_a_side_of_the_gun_to_the_camera() {
        let rig = mako_rig();
        assert_eq!(inspect_side("inspect"), Some(false));
        assert_eq!(inspect_side("inspect-left"), Some(true));
        assert_eq!(inspect_side("ads"), None);
        for (left, side) in [(false, Vec3::NEG_X), (true, Vec3::X)] {
            let pose = inspect_pose(&rig, left);
            assert!((pose.rotation * side).z > 0.99, "left {left}: that side faces the camera");
            let grip = pose.transform_point(Vec3::ZERO);
            let muzzle = pose.transform_point(rig.muzzle);
            assert_eq!(muzzle.x > grip.x, !left, "the muzzle toward that side of the screen");
            assert!(grip.z < -0.4 && muzzle.z < -0.4 && grip.x.abs() < 0.5, "{grip} {muzzle}");
        }
    }

    /// Another player's gun points exactly where they look at any pitch, unsheared, crouched or not, and its grip
    /// goes down with the body (review finding: under the squashed root a crouched player's gun sheared and aimed
    /// flatter than their look).
    #[test]
    fn a_crouched_players_gun_aims_along_the_look() {
        let (feet, hand) = (Vec3::new(3.0, 1.0, -2.0), Vec3::new(-0.2, 1.3, -0.3));
        for stance in [Stance::Stand, Stance::Crouch, Stance::Slide] {
            for pitch in [-1.2f32, -0.5, 0.0, 0.6, 1.3] {
                let look = PlayerLook { yaw: 0.7, pitch };
                let pose = PlayerPose::new(feet, &look, stance);
                let root = GlobalTransform::from(pose.root);
                let gun = root.mul_transform(pose.gun(hand));
                let m = Mat3::from(gun.affine().matrix3);
                assert!((m * m.transpose()).abs_diff_eq(Mat3::IDENTITY, 1e-5), "{stance:?} {pitch}: sheared {m}");
                let ahead = gun.affine().transform_vector3(Vec3::NEG_Z);
                let look_dir = vetf_sim::input::view_dir(look.yaw, pitch);
                assert!(ahead.abs_diff_eq(look_dir, 1e-5), "{stance:?} {pitch}: {ahead} vs {look_dir}");
                let grip = root.mul_transform(pose.body).transform_point(hand);
                assert!(gun.translation().abs_diff_eq(grip, 1e-5), "{stance:?}: the grip lowers with the body");
            }
        }
        let crouched = PlayerPose::new(feet, &PlayerLook::default(), Stance::Crouch);
        assert!(crouched.body.scale.y < 1.0 && crouched.root.scale == Vec3::ONE, "the body squashes, not the root");
    }

    #[test]
    fn screen_shake_scales_only_the_visual_kick() {
        assert_eq!(visual_punch(2.0, 100.0), 2.0);
        assert!((visual_punch(2.0, 60.0) - 1.2).abs() < 1e-6);
        assert_eq!(visual_punch(2.0, 0.0), 0.0);
        assert_eq!(visual_punch(2.0, 250.0), 2.0, "never more than the full kick");
    }
}
