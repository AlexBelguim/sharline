//! The LASER side-rail part (attachments.ron `laser`) made visible: a thin red beam from the part's emitter to where
//! its holder aims, and a dot where that aim meets the level or a player. Our own laser comes from the first-person
//! gun (hip or aimed, so the beam runs from the gun on screen to the crosshair); everyone else's from the gun in
//! their hand along their replicated look. Visual only: the laser's gameplay effect is its `hip_spread` stat, which
//! counts only while the laser is on.
//!
//! D2 (user): V turns the laser on and off (`WeaponState::laser_on`, replicated), so a beam shows only while its
//! holder has it on. With the gun up the beam runs to the aim point as before; once the barrel points away from the
//! aim (the sprint pose, a mag check, an item: any pose with the gun down or busy) it leaves along the BARREL and
//! the dot lands where the barrel points ([`barrel_follow`], [`Laser::along`]), on our own gun and on everyone
//! else's. Fully aimed through a magnified optic our gun is hidden, but our own dot still shows in the scope view
//! where the aim lands ([`Laser::scoped`]).
//!
//! The emitter is the laser model's `*_SOCKET_Beam` node (the GLB places it at the lens), found by name when the
//! part's scene spawns ([`tag_emitters`]). Every beam and dot is drawn into ONE mesh, rebuilt each frame into the
//! same buffers as the tracers' (camera-facing ribbons kept between a minimum and a maximum width on screen): no
//! entity per laser and nothing allocated per frame once the buffers have grown. It runs after the transforms
//! propagate, so the beam starts exactly at this frame's gun. Numbers in `feel.ron` ([`LaserFeel`]).

use super::feel::{FeelData, LaserFeel};
use super::tracer_fx::{Geometry, View, fit_ldr, mul_alpha, write_mesh};
use super::{HeldGun, PlayerVisual, SmoothedAds, ViewCamera, Viewmodel, ViewmodelRig, vfov_of};
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
use vetf_net::{PlayerLook, PlayerMove, PlayerWeapon, Vitals};
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

    /// A laser at `emitter` pointing along `dir` (unit: the barrel's way, see [`beam_dir`]), meeting something
    /// `hit` metres along it (None: nothing). The beam runs to that point, cut at `beam_m`; the dot sits on it
    /// within `dot_max_m`.
    pub fn along(emitter: Vec3, dir: Vec3, hit: Option<f32>, own: bool, f: &LaserFeel) -> Laser {
        let hit = hit.filter(|d| *d <= f.dot_max_m);
        let end = emitter + dir * hit.map_or(f.beam_m, |d| d.min(f.beam_m));
        Laser { emitter, end, dot: hit.map(|d| emitter + dir * d), own }
    }

    /// Our own laser fully aimed through a magnified optic, the gun hidden: no beam, only the dot where the aim
    /// from `eye` along `dir` meets something `hit` metres away (within `dot_max_m`), in the middle of the scope.
    pub fn scoped(eye: Vec3, dir: Vec3, hit: Option<f32>, f: &LaserFeel) -> Laser {
        let at = hit.filter(|d| *d <= f.dot_max_m).map(|d| eye + dir * d);
        let p = at.unwrap_or(eye);
        Laser { emitter: p, end: p, dot: at, own: true }
    }
}

/// How far the beam follows the barrel instead of the aim (0: the gun is up, the beam goes to the aim point; 1: the
/// gun is down or busy, it goes where the barrel points), from the angle between the aim `dir` and the `barrel`'s
/// way (both unit): eased between the two angles of `follow_barrel_deg`.
pub fn barrel_follow(dir: Vec3, barrel: Vec3, f: &LaserFeel) -> f32 {
    let deg = dir.angle_between(barrel).to_degrees();
    let (lo, hi) = f.follow_barrel_deg;
    let t = ((deg - lo) / (hi - lo).max(1e-3)).clamp(0.0, 1.0);
    t * t * (3.0 - 2.0 * t)
}

/// The way the beam leaves the `emitter`: toward the aim's `target` with the gun up (`follow` 0), along the
/// `barrel` with it down (1), between the two on the way. A target behind the emitter (a wall nearer than the
/// gun's front) counts as the barrel's way.
pub fn beam_dir(emitter: Vec3, target: Vec3, barrel: Vec3, follow: f32) -> Vec3 {
    let to = (target - emitter).normalize_or_zero();
    let to = if to != Vec3::ZERO && to.dot(barrel) > -0.99 { to } else { barrel };
    to.lerp(barrel, follow.clamp(0.0, 1.0)).normalize_or(barrel)
}

/// Our first-person gun's barrel in the world: the gun's forward (the way it points in its `up` pose, the rig's
/// hip-to-aimed pose this frame, which looks down the view) carried through the gun's world transform (the
/// lowering, the sway, the lens squeeze), so it follows the gun as drawn.
pub fn viewmodel_barrel(gun: &GlobalTransform, up: Quat) -> Vec3 {
    gun.affine().transform_vector3(up.inverse() * Vec3::NEG_Z).normalize_or_zero()
}

/// A player's held gun's barrel in the world: its forward (it points along the look when up).
fn held_barrel(gun: &GlobalTransform) -> Vec3 {
    gun.affine().transform_vector3(Vec3::NEG_Z).normalize_or_zero()
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
    /// Our first-person gun (the viewmodel's entity).
    Me(Entity),
    /// A player's held gun (the player's entity, and the held gun's).
    Player(Entity, Option<Entity>),
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
    view_gun: (Res<ViewmodelRig>, Res<SmoothedAds>, Res<Time<Fixed>>),
    camera: Query<(&GlobalTransform, &Projection, Has<Hdr>), With<ViewCamera>>,
    emitters: Query<(Entity, &GlobalTransform, &InheritedVisibility), With<LaserEmitter>>,
    parents: Query<&ChildOf>,
    viewmodels: Query<&GlobalTransform, With<Viewmodel>>,
    held: Query<&GlobalTransform, With<HeldGun>>,
    players: Query<(Entity, &PlayerMove, &PlayerLook, &Vitals, Has<Controlled>), With<PlayerVisual>>,
    weapons: Query<(&PlayerWeapon, Has<Controlled>)>,
    mut meshes: ResMut<Assets<Mesh>>,
    shown: Query<&Mesh3d, With<LaserMesh>>,
    mut scratch: Local<Scratch>,
) {
    let Some((cam, projection, hdr)) = camera.iter().next() else { return };
    let (rig, smoothed_ads, fixed) = view_gun;
    let ads = smoothed_ads.at(fixed.overstep_fraction());
    let f = &feel.laser;
    let level = level.as_deref();
    let my_laser_on = weapons.iter().find(|(_, mine)| *mine).is_some_and(|(w, _)| w.0.laser_on);
    let my_alive = players.iter().find(|p| p.4).is_some_and(|p| !p.3.health.dead);
    let Scratch { geometry: g, cuts, lasers } = &mut *scratch;
    lasers.clear();
    for (e, at, visible) in &emitters {
        let mut node = e;
        let mut holder = None;
        let mut held_gun = None;
        for _ in 0..MAX_DEPTH {
            if viewmodels.contains(node) {
                holder = Some(Holder::Me(node));
                break;
            }
            if players.contains(node) {
                holder = Some(Holder::Player(node, held_gun));
                break;
            }
            if held.contains(node) {
                held_gun = Some(node);
            }
            let Ok(up) = parents.get(node) else { break };
            node = up.parent();
        }
        let emitter = at.translation();
        let laser = match holder {
            Some(Holder::Me(gun)) => {
                if !my_laser_on {
                    continue;
                }
                let (eye, dir) = (cam.translation(), view_dir(control.yaw, control.pitch));
                let skip = |_, mine| mine;
                let hit = aim_hit(&data.0, level, &players, skip, eye, dir, f.dot_max_m);
                if !visible.get() {
                    // Hidden behind a magnified scope: only our dot, where the aim lands (D2). Hidden for anything
                    // else (dead, a fixed camera): nothing.
                    if my_alive && crate::weapon_models::scoped(&rig, ads) {
                        lasers.push(Laser::scoped(eye, dir, hit, f));
                    }
                    continue;
                }
                let barrel = viewmodels.get(gun).map_or(dir, |t| viewmodel_barrel(t, rig.pose(ads).rotation));
                pointed(&data.0, level, &players, skip, (emitter, eye, dir, barrel), hit, true, f)
            }
            Some(Holder::Player(p, gun)) => {
                // A hidden gun (our own third-person body, a dead player's) draws none, nor does a laser turned off.
                if !visible.get() || !weapons.get(p).is_ok_and(|(w, _)| w.0.laser_on) {
                    continue;
                }
                let Ok((_, mv, look, ..)) = players.get(p) else { continue };
                let (eye, dir) = (mv.0.eye_pos(), view_dir(look.yaw, look.pitch));
                let skip = |other, _| other == p;
                let hit = aim_hit(&data.0, level, &players, skip, eye, dir, f.dot_max_m);
                let barrel = gun.and_then(|g| held.get(g).ok()).map_or(dir, held_barrel);
                pointed(&data.0, level, &players, skip, (emitter, eye, dir, barrel), hit, false, f)
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

/// One laser from its `emitter` whose holder aims from `eye` along `dir` (the aim meeting something `hit` metres
/// along it) with the barrel pointing along `barrel`: to the aim point with the gun up, along the barrel (cast
/// again from the emitter) once the barrel turns away from the aim.
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn pointed(
    data: &vetf_sim::GameData,
    level: Option<&CurrentLevel>,
    players: &Query<(Entity, &PlayerMove, &PlayerLook, &Vitals, Has<Controlled>), With<PlayerVisual>>,
    skip: impl Fn(Entity, bool) -> bool,
    (emitter, eye, dir, barrel): (Vec3, Vec3, Vec3, Vec3),
    hit: Option<f32>,
    own: bool,
    f: &LaserFeel,
) -> Laser {
    let follow = if barrel == Vec3::ZERO { 0.0 } else { barrel_follow(dir, barrel, f) };
    if follow <= 0.0 {
        return Laser::aimed(emitter, eye, dir, hit, own, f);
    }
    let target = eye + dir * hit.map_or(f.dot_max_m, |d| d.min(f.dot_max_m));
    let way = beam_dir(emitter, target, barrel, follow);
    let hit = aim_hit(data, level, players, skip, emitter, way, f.dot_max_m);
    Laser::along(emitter, way, hit, own, f)
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

    /// D2: fully aimed through a magnified optic (the gun hidden), our dot sits where the aim lands, in the middle of
    /// the scope view, with no beam; past `dot_max_m` or with nothing hit there is none.
    #[test]
    fn the_scoped_dot_sits_where_the_aim_lands() {
        let f = feel();
        let (eye, dir) = (Vec3::new(3.0, 1.6, -2.0), view_dir(0.7, -0.1));
        let l = Laser::scoped(eye, dir, Some(42.0), &f);
        let at = eye + dir * 42.0;
        assert_eq!(l.dot, Some(at));
        assert!(l.own && l.emitter == l.end, "no beam: {l:?}");
        // On screen: dead centre of the zoomed view (a 4x scope's narrow FOV), drawn as just the dot.
        let view = View::new(eye, 12f32.to_radians());
        let g = build(&[l], &f, &view, true);
        assert_eq!(g.positions.len(), DOT_SIDES + 1, "only the dot");
        let centre = Vec3::from(g.positions[0]);
        assert!((centre - eye).normalize().angle_between(dir) < 1e-4, "on the crosshair: {centre}");
        assert_eq!(Laser::scoped(eye, dir, Some(f.dot_max_m + 1.0), &f).dot, None);
        assert_eq!(Laser::scoped(eye, dir, None, &f).dot, None);
        assert!(build(&[Laser::scoped(eye, dir, None, &f)], &f, &view, true).indices.is_empty());
    }

    /// Our gun in view space at the hip, with a lean like a model rig's, and the camera.
    fn own_gun(lowered: Quat, lens: f32) -> (GlobalTransform, Quat, Vec3) {
        let up = Quat::from_euler(EulerRot::YXZ, 0.04, 0.02, -0.03) * Quat::from_rotation_y(std::f32::consts::PI);
        let cam = Transform::from_xyz(1.0, 1.6, 4.0).with_rotation(Quat::from_rotation_y(0.4));
        let lens = Transform::from_scale(Vec3::new(lens, lens, 1.0));
        let gun = Transform::from_xyz(0.2, -0.2, -0.5).with_rotation(lowered * up);
        let world = GlobalTransform::from(cam) * GlobalTransform::from(lens) * GlobalTransform::from(gun);
        (world, up, cam.rotation * Vec3::NEG_Z)
    }

    /// With the gun up the beam goes to the crosshair as before: the barrel looks down the view.
    #[test]
    fn with_the_gun_up_the_beam_goes_to_the_aim() {
        let f = feel();
        let (gun, up, aim) = own_gun(Quat::IDENTITY, 0.92);
        let barrel = viewmodel_barrel(&gun, up);
        assert!(barrel.angle_between(aim) < 1e-4, "{barrel} vs {aim}");
        assert_eq!(barrel_follow(aim, barrel, &f), 0.0);
        // the sway's turns stay under the threshold too
        let (gun, up, aim) = own_gun(Quat::from_rotation_x(4f32.to_radians()), 1.0);
        assert_eq!(barrel_follow(aim, viewmodel_barrel(&gun, up), &f), 0.0, "a landing's dip is still aimed");
    }

    /// D2: lowered (the sprint pose's turn) the beam leaves along the barrel and the dot lands where the barrel
    /// points, not on the crosshair.
    #[test]
    fn lowered_the_beam_follows_the_barrel() {
        let f = feel();
        let sprint = FeelData::embedded().gun.sprint_pose;
        let lowered = Quat::from_rotation_y(sprint.yaw_deg.to_radians());
        let (gun, up, aim) = own_gun(lowered, 0.95);
        let barrel = viewmodel_barrel(&gun, up);
        assert!(barrel.angle_between(aim).to_degrees() > f.follow_barrel_deg.1, "the sprint pose turns it away");
        let follow = barrel_follow(aim, barrel, &f);
        assert_eq!(follow, 1.0);
        let emitter = gun.translation();
        let eye = Vec3::new(1.0, 1.6, 4.0);
        let target = eye + aim * 20.0;
        let way = beam_dir(emitter, target, barrel, follow);
        assert!(way.angle_between(barrel) < 1e-5, "along the barrel: {way} vs {barrel}");
        let l = Laser::along(emitter, way, Some(8.0), true, &f);
        let dot = l.dot.unwrap();
        assert!((dot - (emitter + barrel * 8.0)).length() < 1e-4 && l.end == dot, "{l:?}");
        let off = (dot - eye).normalize().angle_between(aim).to_degrees();
        assert!(off > 10.0, "the dot is not on the crosshair: {off} deg off");
        // Far: the beam stops at `beam_m` along the barrel, the dot beyond it on what the barrel points at.
        let far = Laser::along(emitter, way, Some(60.0), false, &f);
        assert!((far.end - (emitter + way * f.beam_m)).length() < 1e-4 && far.dot == Some(emitter + way * 60.0));
        assert_eq!(Laser::along(emitter, way, None, false, &f).dot, None);
        // Half way up the beam is between the two, and it eases in from the threshold.
        let mid = beam_dir(emitter, target, barrel, 0.5);
        let to = (target - emitter).normalize();
        assert!(mid.angle_between(to) > 0.0 && mid.angle_between(barrel) < to.angle_between(barrel));
        let (lo, hi) = f.follow_barrel_deg;
        let at = |deg: f32| barrel_follow(Vec3::NEG_Z, Quat::from_rotation_y(deg.to_radians()) * Vec3::NEG_Z, &f);
        assert!(at(lo * 0.9) == 0.0 && at((lo + hi) / 2.0) > 0.4 && at((lo + hi) / 2.0) < 0.6 && at(hi + 1.0) == 1.0);
    }

    /// Another player's gun: along their look when up, along its barrel while they check the magazine (the gun
    /// turns its window toward them).
    #[test]
    fn another_players_beam_follows_their_barrel() {
        let f = feel();
        let look = PlayerLook { yaw: 1.1, pitch: 0.2 };
        let pose = super::super::PlayerPose::new(Vec3::new(2.0, 0.0, 1.0), &look, vetf_sim::movement::Stance::Stand);
        let held = FeelData::embedded().gun.mag_inspect.third_person;
        let at = |inspect: f32| {
            let mut gun = pose.gun(Vec3::new(0.2, 1.3, -0.3));
            gun.rotation *= super::super::inspect::held_turn(&held, inspect);
            held_barrel(&(GlobalTransform::from(pose.root) * GlobalTransform::from(gun)))
        };
        let aim = view_dir(look.yaw, look.pitch);
        assert!(at(0.0).angle_between(aim) < 1e-4 && barrel_follow(aim, at(0.0), &f) == 0.0);
        assert_eq!(barrel_follow(aim, at(1.0), &f), 1.0, "checking the magazine, the beam follows the barrel");
    }

    /// The blurb's range is the beam's.
    #[test]
    fn the_blurb_says_the_beam_range() {
        let d = vetf_sim::GameData::embedded();
        let blurb = &d.attachment("laser").expect("a laser").blurb;
        let range = format!("within {} m", feel().beam_m);
        assert!(blurb.contains(&range), "{blurb:?} should say {range:?}");
        // So does its tag in the attachment list (item B: every effect shown).
        let tag = format!("BEAM WITHIN {} M", feel().beam_m);
        let tags = crate::loadout::text::part_tags(d.attachment("laser").unwrap());
        assert!(tags.iter().any(|t| t.text.contains(&tag) && !t.not_yet), "{tags:?} should say {tag:?}");
    }
}
