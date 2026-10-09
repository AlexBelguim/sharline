//! The LASER side-rail part (attachments.ron `laser`) made visible: a thin red beam from the part's emitter to where
//! its holder aims, and a dot where that aim meets the level or a player. Our own laser comes from the first-person
//! gun (hip or aimed, so the beam runs from the gun on screen to the crosshair); everyone else's from the gun in
//! their hand along their replicated look. Visual only: the laser's gameplay effect is its `hip_spread` stat.
//!
//! The emitter is the laser model's `*_SOCKET_Beam` node (the GLB places it at the lens), found by name when the
//! part's scene spawns ([`tag_emitters`]). Every beam and dot is drawn into ONE mesh, rebuilt each frame into the
//! same buffers as the tracers' (camera-facing ribbons kept between a minimum and a maximum width on screen): no
//! entity per laser and nothing allocated per frame once the buffers have grown. It runs after the transforms
//! propagate, so the beam starts exactly at this frame's gun. Numbers in `feel.ron` ([`LaserFeel`]).

use super::feel::{FeelData, LaserFeel};
use super::tracer_fx::{Geometry, View, fit_ldr, mul_alpha, write_mesh};
use super::{PlayerVisual, ViewCamera, Viewmodel, vfov_of};
use crate::AppState;
use crate::client::LocalControl;
use crate::config::{CurrentLevel, Data};
use bevy::asset::RenderAssetUsages;
use bevy::camera::Hdr;
use bevy::camera::visibility::{NoFrustumCulling, VisibilitySystems};
use bevy::light::{NotShadowCaster, NotShadowReceiver};
use bevy::mesh::PrimitiveTopology;
use bevy::prelude::*;
use bevy::transform::TransformSystems;
use lightyear::prelude::*;
use std::f32::consts::TAU;
use vetf_net::{PlayerLook, PlayerMove, Vitals};
use vetf_sim::hitbox::{self, Pose};
use vetf_sim::input::view_dir;

pub(crate) struct LaserPlugin;

impl Plugin for LaserPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(AppState::InGame), spawn_laser_mesh)
            .add_systems(Update, tag_emitters.run_if(in_state(AppState::InGame)))
            .add_systems(
                PostUpdate,
                draw_lasers
                    .after(TransformSystems::Propagate)
                    .after(VisibilitySystems::VisibilityPropagate)
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

/// Segments round a dot.
const DOT_SIDES: usize = 8;
/// A dot sits this far in front of what it lies on (at most half its distance from the eye), so it never sinks
/// into the wall.
const DOT_LIFT_M: f32 = 0.03;
/// How far up a gun's parents an emitter looks for whose gun it is.
const MAX_DEPTH: usize = 64;

/// A laser model's emitter node: `ATT_laser_<side>_SOCKET_Beam`. The flashlight has a `_SOCKET_Beam` too; it is
/// not a laser.
pub fn is_laser_emitter(name: &str) -> bool {
    name.starts_with("ATT_laser") && name.ends_with("_SOCKET_Beam")
}

/// The emitter of a laser on a gun in the world (the first-person gun's, or a player's held gun's).
#[derive(Component)]
pub(crate) struct LaserEmitter;

#[derive(Component)]
pub(crate) struct LaserMesh;

/// One laser this frame, in world space.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Laser {
    pub emitter: Vec3,
    /// Where the drawn beam stops: where the aim meets something, or `beam_m` from the emitter, whichever is nearer.
    pub end: Vec3,
    /// Where the aim meets the level or a player, within `dot_max_m` of the eye.
    pub dot: Option<Vec3>,
    pub own: bool,
}

impl Laser {
    /// A laser at `emitter` whose holder aims from `eye` along `dir` (unit), the aim meeting something `hit` metres
    /// along it (None: nothing). The beam runs from the emitter to that point (or toward `dot_max_m` along the aim
    /// when nothing is hit), cut at `beam_m`; with the point behind the emitter (a wall closer than the gun's
    /// front) there is no beam, only the dot.
    pub fn aimed(emitter: Vec3, eye: Vec3, dir: Vec3, hit: Option<f32>, own: bool, f: &LaserFeel) -> Laser {
        let hit = hit.filter(|d| *d <= f.dot_max_m);
        let target = eye + dir * hit.unwrap_or(f.dot_max_m);
        let to = target - emitter;
        let len = to.length();
        let end = if to.dot(dir) <= 0.0 || len < 1e-4 {
            emitter
        } else if len > f.beam_m {
            emitter + to / len * f.beam_m
        } else {
            target
        };
        Laser { emitter, end, dot: hit.map(|d| eye + dir * d), own }
    }
}

/// Every laser's beam, then the dots over them.
#[cfg(test)]
pub fn build(lasers: &[Laser], f: &LaserFeel, view: &View, hdr: bool) -> Geometry {
    let mut g = Geometry::default();
    build_into(&mut g, &mut Vec::new(), lasers, f, view, hdr);
    g
}

/// [`build`] into `g` (cleared first), with `cuts` as scratch space.
fn build_into(g: &mut Geometry, cuts: &mut Vec<f32>, lasers: &[Laser], f: &LaserFeel, view: &View, hdr: bool) {
    g.clear();
    let color = |c: [f32; 4]| if hdr { c } else { fit_ldr(c) };
    let b = f.beam;
    for l in lasers {
        let c = color(if l.own { b.own } else { b.other });
        let beam = f.beam_m.max(1e-3);
        let len = l.emitter.distance(l.end);
        // Bright at the emitter, fading to nothing `beam_m` from it.
        g.ribbon(cuts, view, l.emitter, l.end, |k| (b.width_m, b.min_px, b.max_px, mul_alpha(c, 1.0 - k * len / beam)));
    }
    let d = f.dot;
    for l in lasers {
        let Some(at) = l.dot else { continue };
        let c = color(if l.own { d.own } else { d.other });
        g.dot(view, at, d.width_m, d.min_px, d.max_px, c);
    }
}

impl Geometry {
    /// A round camera-facing dot at `at`, lifted a little toward the eye, `width_m` across (kept between `min_px`
    /// and `max_px` on screen); solid in the middle, softer at the rim.
    fn dot(&mut self, view: &View, at: Vec3, width_m: f32, min_px: f32, max_px: f32, color: [f32; 4]) {
        let back = view.eye - at;
        let dist = back.length();
        if dist < 1e-3 {
            return;
        }
        let p = at + back / dist * DOT_LIFT_M.min(dist * 0.5);
        let fwd = -back / dist;
        let right = fwd.cross(Vec3::Y).try_normalize().unwrap_or(Vec3::X);
        let up = right.cross(fwd);
        let r = view.width(p, width_m, min_px, max_px) * 0.5;
        let base = self.positions.len() as u32;
        self.positions.push(p.to_array());
        self.colors.push(color);
        for i in 0..DOT_SIDES {
            let a = i as f32 / DOT_SIDES as f32 * TAU;
            self.positions.push((p + (right * a.cos() + up * a.sin()) * r).to_array());
            self.colors.push(mul_alpha(color, 0.5));
        }
        for i in 0..DOT_SIDES as u32 {
            self.indices.extend_from_slice(&[base, base + 1 + i, base + 1 + (i + 1) % DOT_SIDES as u32]);
        }
    }
}

pub(crate) fn spawn_laser_mesh(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
    write_mesh(&mut mesh, &Geometry::default());
    commands.spawn((
        LaserMesh,
        Name::new("Lasers"),
        Mesh3d(meshes.add(mesh)),
        MeshMaterial3d(materials.add(StandardMaterial {
            base_color: Color::WHITE,
            unlit: true,
            alpha_mode: AlphaMode::Blend,
            double_sided: true,
            cull_mode: None,
            fog_enabled: false,
            ..default()
        })),
        Transform::IDENTITY,
        Visibility::Inherited,
        NoFrustumCulling,
        NotShadowCaster,
        NotShadowReceiver,
        DespawnOnExit(AppState::InGame),
    ));
}

/// Marks each laser emitter node as its part's scene comes into the world.
fn tag_emitters(mut commands: Commands, named: Query<(Entity, &Name), Added<Name>>) {
    for (e, name) in &named {
        if is_laser_emitter(name.as_str()) {
            commands.entity(e).insert(LaserEmitter);
        }
    }
}

/// Whose gun an emitter is on.
#[derive(Debug, Clone, Copy, PartialEq)]
enum Holder {
    /// Our first-person gun.
    Me,
    /// A player's held gun (the player's entity).
    Player(Entity),
}

/// Buffers kept from frame to frame.
#[derive(Default)]
pub(crate) struct Scratch {
    geometry: Geometry,
    cuts: Vec<f32>,
    lasers: Vec<Laser>,
}

/// Where the aim from `eye` along `dir` first meets the level or a living player other than `skip` (metres).
fn aim_hit(
    data: &vetf_sim::GameData,
    level: Option<&CurrentLevel>,
    players: &Query<(Entity, &PlayerMove, &PlayerLook, &Vitals, Has<Controlled>), With<PlayerVisual>>,
    skip: impl Fn(Entity, bool) -> bool,
    eye: Vec3,
    dir: Vec3,
    max: f32,
) -> Option<f32> {
    let wall = level.and_then(|l| l.world.raycast(eye, dir, max)).map(|(d, _)| d);
    let body = players
        .iter()
        .filter(|(e, _, _, v, mine)| !v.health.dead && !skip(*e, *mine))
        .filter_map(|(_, mv, look, ..)| {
            let pose = Pose { pos: mv.0.pos, yaw: look.yaw, stance: mv.0.stance };
            hitbox::raycast(data, &pose, eye, dir, max).map(|(_, t)| t)
        })
        .min_by(f32::total_cmp);
    match (wall, body) {
        (Some(a), Some(b)) => Some(a.min(b)),
        (a, b) => a.or(b),
    }
}

/// Finds each visible laser's holder and aim, and rebuilds the mesh for this frame's camera.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub(crate) fn draw_lasers(
    feel: Res<FeelData>,
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    control: Res<LocalControl>,
    camera: Query<(&GlobalTransform, &Projection, Has<Hdr>), With<ViewCamera>>,
    emitters: Query<(Entity, &GlobalTransform, &InheritedVisibility), With<LaserEmitter>>,
    parents: Query<&ChildOf>,
    viewmodels: Query<(), With<Viewmodel>>,
    players: Query<(Entity, &PlayerMove, &PlayerLook, &Vitals, Has<Controlled>), With<PlayerVisual>>,
    mut meshes: ResMut<Assets<Mesh>>,
    shown: Query<&Mesh3d, With<LaserMesh>>,
    mut scratch: Local<Scratch>,
) {
    let Some((cam, projection, hdr)) = camera.iter().next() else { return };
    let f = &feel.laser;
    let level = level.as_deref();
    let Scratch { geometry: g, cuts, lasers } = &mut *scratch;
    lasers.clear();
    for (e, at, visible) in &emitters {
        // A hidden gun (ours behind a scope or while dead, our own third-person body, a dead player's) draws none.
        if !visible.get() {
            continue;
        }
        let mut node = e;
        let mut holder = None;
        for _ in 0..MAX_DEPTH {
            if viewmodels.contains(node) {
                holder = Some(Holder::Me);
                break;
            }
            if players.contains(node) {
                holder = Some(Holder::Player(node));
                break;
            }
            let Ok(up) = parents.get(node) else { break };
            node = up.parent();
        }
        let emitter = at.translation();
        let laser = match holder {
            Some(Holder::Me) => {
                let (eye, dir) = (cam.translation(), view_dir(control.yaw, control.pitch));
                let hit = aim_hit(&data.0, level, &players, |_, mine| mine, eye, dir, f.dot_max_m);
                Laser::aimed(emitter, eye, dir, hit, true, f)
            }
            Some(Holder::Player(p)) => {
                let Ok((_, mv, look, ..)) = players.get(p) else { continue };
                let (eye, dir) = (mv.0.eye_pos(), view_dir(look.yaw, look.pitch));
                let hit = aim_hit(&data.0, level, &players, |other, _| other == p, eye, dir, f.dot_max_m);
                Laser::aimed(emitter, eye, dir, hit, false, f)
            }
            // A gun somewhere else (none in a match today): no aim to follow.
            None => continue,
        };
        lasers.push(laser);
    }
    let view = View::new(cam.translation(), vfov_of(projection));
    build_into(g, cuts, lasers, f, &view, hdr);
    for handle in &shown {
        if let Some(mut mesh) = meshes.get_mut(&handle.0) {
            write_mesh(&mut mesh, g);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn feel() -> LaserFeel {
        FeelData::embedded().laser
    }

    #[test]
    fn only_the_laser_emits_a_beam() {
        assert!(is_laser_emitter("ATT_laser_R_SOCKET_Beam"));
        assert!(is_laser_emitter("ATT_laser_L_SOCKET_Beam"));
        assert!(!is_laser_emitter("ATT_flashlight_R_SOCKET_Beam"), "the flashlight's beam is not a laser");
        assert!(!is_laser_emitter("ATT_laser_R_Emitter"));
        assert!(!is_laser_emitter("AR7_Mako_SOCKET_Side_R"));
    }

    /// The laser's GLB has the emitter node this module looks for.
    #[test]
    fn the_laser_model_has_its_emitter() {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../assets/models/weapons/tactical/ATT_laser_R.glb");
        let Ok(bytes) = std::fs::read(&path) else { return }; // LFS not pulled: nothing to check
        if bytes.get(0..4) != Some(b"glTF") {
            return;
        }
        let n = u32::from_le_bytes(bytes[12..16].try_into().unwrap()) as usize;
        let json: serde_json::Value = serde_json::from_slice(&bytes[20..20 + n]).unwrap();
        let names: Vec<&str> = json["nodes"].as_array().unwrap().iter().filter_map(|n| n["name"].as_str()).collect();
        assert!(names.iter().any(|n| is_laser_emitter(n)), "{names:?}");
    }

    /// Up close the beam runs from the gun to the hit and the dot sits on it.
    #[test]
    fn the_beam_ends_on_a_near_hit_with_the_dot() {
        let f = feel();
        let (eye, dir, emitter) = (Vec3::new(0.0, 1.6, 0.0), Vec3::NEG_Z, Vec3::new(0.15, 1.45, -0.4));
        let l = Laser::aimed(emitter, eye, dir, Some(8.0), true, &f);
        let at = eye + dir * 8.0;
        assert_eq!((l.end, l.dot), (at, Some(at)));
    }

    /// Past `beam_m` (the blurb's 25 m) the beam stops there; the dot still shows on what the aim meets, up to
    /// `dot_max_m`, and with nothing hit there is no dot.
    #[test]
    fn the_beam_shows_within_its_range_and_the_dot_beyond() {
        let f = feel();
        let (eye, dir, emitter) = (Vec3::ZERO, Vec3::NEG_Z, Vec3::new(0.1, -0.1, -0.3));
        let far = Laser::aimed(emitter, eye, dir, Some(60.0), false, &f);
        assert!((far.end.distance(emitter) - f.beam_m).abs() < 1e-3, "{far:?}");
        assert_eq!(far.dot, Some(Vec3::new(0.0, 0.0, -60.0)));
        let sky = Laser::aimed(emitter, eye, dir, None, false, &f);
        assert!((sky.end.distance(emitter) - f.beam_m).abs() < 1e-3 && sky.dot.is_none(), "{sky:?}");
        let beyond = Laser::aimed(emitter, eye, dir, Some(f.dot_max_m + 1.0), false, &f);
        assert_eq!(beyond.dot, None, "too far for the dot");
        // A wall nearer than the gun's front: just the dot.
        let wall = Laser::aimed(emitter, eye, dir, Some(0.1), true, &f);
        assert_eq!((wall.end, wall.dot), (emitter, Some(Vec3::new(0.0, 0.0, -0.1))));
    }

    /// The beam fades out toward `beam_m`, the dot is a camera-facing disc on top, and nothing builds no geometry.
    #[test]
    fn beams_fade_out_and_dots_face_the_camera() {
        let f = feel();
        let view = View::new(Vec3::ZERO, 70f32.to_radians());
        assert!(build(&[], &f, &view, true).indices.is_empty());
        let l = Laser::aimed(Vec3::new(5.0, 0.0, 0.0), Vec3::new(5.0, 1.0, 0.0), Vec3::NEG_Z, None, false, &f);
        let g = build(&[l], &f, &view, true);
        assert!(!g.indices.is_empty() && g.indices.iter().all(|&i| (i as usize) < g.positions.len()));
        let first = g.colors[0][3];
        let last = g.colors[g.colors.len() - 1][3];
        assert!((first - f.beam.other[3]).abs() < 1e-5 && last.abs() < 1e-3, "{first} .. {last}");
        // With a dot: its centre and rim lie in a plane facing the eye.
        let hit = Laser::aimed(Vec3::new(0.2, -0.2, -0.3), Vec3::ZERO, Vec3::NEG_Z, Some(10.0), true, &f);
        let g = build(&[hit], &f, &view, false);
        let disc = &g.positions[g.positions.len() - (DOT_SIDES + 1)..];
        let centre = Vec3::from(disc[0]);
        assert!(centre.z > -10.0 && centre.z < -9.9, "lifted off the wall toward the eye: {centre}");
        for p in &disc[1..] {
            let p = Vec3::from(*p);
            assert!((p - centre).dot(centre.normalize()).abs() < 1e-5, "faces the eye");
        }
        assert!(g.colors.iter().all(|c| c.iter().all(|v| (0.0..=1.0).contains(v))), "LDR colours fit");
    }

    /// The blurb's range is the beam's.
    #[test]
    fn the_blurb_says_the_beam_range() {
        let d = vetf_sim::GameData::embedded();
        let blurb = &d.attachment("laser").expect("a laser").blurb;
        let range = format!("within {} m", feel().beam_m);
        assert!(blurb.contains(&range), "{blurb:?} should say {range:?}");
    }
}
