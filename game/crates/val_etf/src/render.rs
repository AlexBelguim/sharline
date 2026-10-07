//! Blockout rendering: level brushes, lighting, first-person camera + viewmodel, other players with their
//! halos, and tracers. Placeholder art until the glTF assets are wired in.

use crate::AppState;
use crate::client::{Feedback, LocalControl, Smoothed};
use crate::config::{CurrentLevel, Data};
use bevy::asset::RenderAssetUsages;
use bevy::mesh::{Indices, PrimitiveTopology};
use bevy::prelude::*;
use lightyear::prelude::*;
use std::collections::HashMap;
use std::f32::consts::{FRAC_PI_2, PI, TAU};
use vetf_net::*;
use vetf_sim::Zone;
use vetf_sim::data::{WeaponClass, WeightClass};
use vetf_sim::level::Team;
use vetf_sim::movement::Stance;
use vetf_sim::movement::collision::{Brush, Look};

pub struct RenderPlugin;

impl Plugin for RenderPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(ClearColor(Color::srgb(0.62, 0.74, 0.86)))
            .insert_resource(GlobalAmbientLight { color: Color::srgb(0.9, 0.92, 1.0), brightness: 900.0, ..default() })
            .add_systems(Startup, setup_menu_camera)
            .add_systems(OnEnter(AppState::InGame), (spawn_level, spawn_view_camera))
            .add_systems(OnEnter(AppState::MainMenu), setup_menu_camera)
            .add_systems(
                Update,
                (attach_player_visuals, update_player_visuals, sync_viewmodel, update_camera, draw_tracers)
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

/// UI-only camera for the menus.
#[derive(Component)]
struct MenuCamera;

/// The first-person camera.
#[derive(Component)]
pub struct ViewCamera;

/// The first-person gun; remembers which weapon class its parts were built for.
#[derive(Component)]
struct Viewmodel(Option<WeaponClass>);

#[derive(Component)]
struct PlayerVisual;

#[derive(Component)]
struct HaloArc(Zone);

#[derive(Component)]
struct BodyPart;

/// Menus and the connecting screen use a plain 2D camera; the match has its own 3D view camera.
fn setup_menu_camera(mut commands: Commands, existing: Query<(), With<MenuCamera>>) {
    if existing.is_empty() {
        commands.spawn((MenuCamera, Camera2d, DespawnOnEnter(AppState::InGame)));
    }
}

/// Palette from art/STYLE_GUIDE.md (graphite, bone, sand, olive...) plus readable blockout colours.
fn look_color(look: Look) -> (Color, f32) {
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
            Some(dir) => meshes.add(wedge_mesh(b, dir)),
            None => meshes.add(Cuboid::from_size(b.max - b.min)),
        };
        commands.spawn((
            Mesh3d(mesh),
            MeshMaterial3d(mat(b.look, &mut materials)),
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
        DirectionalLight { illuminance: 9000.0, shadow_maps_enabled: true, ..default() },
        Transform::from_xyz(30.0, 60.0, 20.0).looking_at(Vec3::new(36.0, 0.0, -24.0), Vec3::Y),
        DespawnOnExit(AppState::InGame),
    ));
}

/// A ramp's wedge, built rising along +X and rotated to its rise direction.
fn wedge_mesh(b: &Brush, rise: Vec3) -> Mesh {
    let size = b.max - b.min;
    let along_x = rise.x.abs() > 0.5;
    let (hx, hy, hz) = if along_x { (size.x, size.y, size.z) } else { (size.z, size.y, size.x) };
    let (hx, hy, hz) = (hx * 0.5, hy * 0.5, hz * 0.5);
    let rot = Quat::from_rotation_y((-rise.z).atan2(rise.x));
    let p = |x: f32, y: f32, z: f32| rot * Vec3::new(x, y, z);
    let (a, bb, c, d) = (p(-hx, -hy, -hz), p(hx, -hy, -hz), p(hx, -hy, hz), p(-hx, -hy, hz));
    let (e, f) = (p(hx, hy, -hz), p(hx, hy, hz));
    let faces: [&[Vec3]; 5] = [&[a, d, c, bb], &[bb, c, f, e], &[a, e, f, d], &[a, bb, e], &[d, f, c]];
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

/// Arc centre angle in the player's local frame (facing -Z): front = head, left = arms, back = torso,
/// right = legs (seen from above), per the halo spec.
fn arc_angle(zone: Zone) -> f32 {
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
        let gun_mat = materials.add(StandardMaterial { base_color: Color::srgb(0.08, 0.085, 0.10), ..default() });
        let halo = loadout.0.halo;
        let scale = match loadout.0.weight {
            WeightClass::Heavy => 1.2,
            WeightClass::Medium => 1.0,
            _ => 0.85,
        };
        let tube = match loadout.0.weight {
            WeightClass::Heavy => 0.022,
            WeightClass::Medium => 0.016,
            _ => 0.011,
        };
        commands.entity(e).insert((PlayerVisual, Transform::default(), Visibility::default())).with_children(|p| {
            p.spawn((
                BodyPart,
                Mesh3d(meshes.add(Capsule3d::new(0.26, 0.9))),
                MeshMaterial3d(body_mat),
                Transform::from_xyz(0.0, 0.85, 0.0),
            ));
            p.spawn((
                BodyPart,
                Mesh3d(meshes.add(Sphere::new(0.13))),
                MeshMaterial3d(head_mat),
                Transform::from_xyz(0.0, 1.6, 0.0),
            ));
            p.spawn((
                BodyPart,
                Mesh3d(meshes.add(Cuboid::new(0.07, 0.1, 0.7))),
                MeshMaterial3d(gun_mat),
                Transform::from_xyz(0.22, 1.35, -0.35),
            ));
            for zone in Zone::ALL {
                let tier = halo.tiers[zone];
                let c = tier_color(tier);
                let mat = materials.add(StandardMaterial {
                    base_color: if tier > 0 { Color::from(c) } else { Color::srgba(0.02, 0.02, 0.025, 0.5) },
                    emissive: if tier > 0 { c * 1.5 } else { LinearRgba::BLACK },
                    alpha_mode: if tier > 0 { AlphaMode::Opaque } else { AlphaMode::Blend },
                    ..default()
                });
                let mid = arc_angle(zone);
                let gap = 0.12;
                p.spawn((
                    HaloArc(zone),
                    Mesh3d(meshes.add(arc_mesh(
                        0.16 * scale,
                        tube,
                        mid - FRAC_PI_2 * 0.5 + gap,
                        mid + FRAC_PI_2 * 0.5 - gap,
                    ))),
                    MeshMaterial3d(mat),
                    Transform::from_xyz(0.0, 1.95, 0.0),
                ));
            }
        });
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
    mut arcs: Query<(&HaloArc, &mut Visibility), Without<PlayerVisual>>,
) {
    for (mv, look, vitals, loadout, mut t, mut vis, children, mine) in &mut players {
        t.translation = mv.0.pos;
        t.rotation = Quat::from_rotation_y(look.yaw);
        t.scale = Vec3::new(1.0, if mv.0.stance == Stance::Stand { 1.0 } else { 0.68 }, 1.0);
        // Our own body never shows (it can get visuals if it arrived a frame before `Controlled` did).
        *vis = if vitals.health.dead || mine { Visibility::Hidden } else { Visibility::Inherited };
        for child in children.iter() {
            if let Ok((arc, mut v)) = arcs.get_mut(child) {
                // A broken arc goes dark (it flares back when it regenerates).
                let up = loadout.0.halo.tiers[arc.0] == 0 || vitals.halo.shield[arc.0] > 0.0;
                *v = if up { Visibility::Inherited } else { Visibility::Hidden };
            }
        }
    }
}

fn spawn_view_camera(mut commands: Commands) {
    commands
        .spawn((
            ViewCamera,
            Camera3d::default(),
            Projection::from(PerspectiveProjection { fov: 78f32.to_radians(), near: 0.03, ..default() }),
            DistanceFog {
                color: Color::srgb(0.66, 0.76, 0.86),
                falloff: FogFalloff::Linear { start: 80.0, end: 420.0 },
                ..default()
            },
            Transform::from_xyz(0.0, 1.6, 0.0),
            DespawnOnExit(AppState::InGame),
        ))
        .with_children(|cam| {
            cam.spawn((
                Viewmodel(None),
                Transform::from_xyz(0.2, -0.2, -0.5).with_scale(Vec3::splat(0.6)),
                Visibility::default(),
            ));
        });
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

/// Build (or rebuild) the viewmodel when our weapon class changes.
fn sync_viewmodel(
    mut commands: Commands,
    data: Res<Data>,
    me: Query<&PlayerLoadout, With<Controlled>>,
    mut viewmodel: Query<(Entity, &mut Viewmodel)>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let Some(loadout) = me.iter().next() else { return };
    let class = loadout.0.weapon.spec(&data).cls;
    for (e, mut vm) in &mut viewmodel {
        if vm.0 == Some(class) {
            continue;
        }
        vm.0 = Some(class);
        commands.entity(e).despawn_children();
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
                ChildOf(e),
            ));
        }
    }
}

#[allow(clippy::type_complexity)]
fn update_camera(
    control: Res<LocalControl>,
    fixed: Res<Time<Fixed>>,
    me: Query<(&PlayerMove, Option<&Smoothed>, &PlayerWeapon, &Vitals), With<Controlled>>,
    mut camera: Query<&mut Transform, (With<ViewCamera>, Without<Viewmodel>)>,
    mut viewmodel: Query<(&mut Transform, &mut Visibility), With<Viewmodel>>,
) {
    let Some((mv, smoothed, weapon, vitals)) = me.iter().next() else { return };
    let alpha = fixed.overstep_fraction();
    let feet = smoothed.map_or(mv.0.pos, |s| s.prev.lerp(s.curr, alpha));
    let dead = vitals.health.dead;
    let eye = if dead { feet + Vec3::Y * 3.0 } else { feet + Vec3::Y * mv.0.eye };
    for mut t in &mut camera {
        t.translation = eye;
        let pitch = if dead { -0.6 } else { control.pitch + control.punch.to_radians() };
        t.rotation = Quat::from_euler(EulerRot::YXZ, control.yaw, pitch, 0.0);
    }
    let ads = weapon.0.ads;
    for (mut t, mut v) in &mut viewmodel {
        let hip = Vec3::new(0.2, -0.2, -0.5);
        let aimed = Vec3::new(0.0, -0.075, -0.3);
        let sprint = if mv.0.sprinting { Vec3::new(0.05, -0.06, 0.04) } else { Vec3::ZERO };
        t.translation = hip.lerp(aimed, ads) + sprint;
        t.rotation = if mv.0.sprinting { Quat::from_rotation_y(0.5) } else { Quat::IDENTITY };
        t.scale = Vec3::splat(0.6);
        *v = if dead { Visibility::Hidden } else { Visibility::Inherited };
    }
}

fn draw_tracers(feedback: Res<Feedback>, mut gizmos: Gizmos) {
    for (from, to, _, own) in &feedback.tracers {
        let c = if *own { Color::srgb(1.0, 0.92, 0.6) } else { Color::srgb(1.0, 0.75, 0.45) };
        gizmos.line(*from, *to, c);
    }
}
