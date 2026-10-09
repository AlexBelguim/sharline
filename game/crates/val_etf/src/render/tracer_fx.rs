//! Tracers: every shot's streak flying from the muzzle to where it ended (own shots and other players'), drawn
//! so they read in daylight. Each is a hot core inside a wider glow, both camera-facing ribbons bright at the
//! head and fading toward the tail, plus a faint smoke trail left along the path that fades out after the bullet.
//! Widths are metres but kept between a minimum and a maximum on screen, so a far tracer stays visible and one
//! at the muzzle never blinds. All tracers are one mesh, rebuilt each frame (the ribbons face the camera) into
//! the same buffers: nothing is allocated per frame once they have grown. Numbers in `feel.ron` ([`TracerFeel`]).
//!
//! New tracers arrive in [`Feedback::tracers`] (our shots from `client::fire_claims`, others' from the host's shot
//! fx); this module takes them from there and keeps them while they fly.

use super::feel::{FeelData, Ribbon, TracerFeel};
use super::{ViewCamera, vfov_of};
use crate::AppState;
use crate::client::Feedback;
use bevy::asset::RenderAssetUsages;
use bevy::camera::Hdr;
use bevy::camera::visibility::NoFrustumCulling;
use bevy::light::{NotShadowCaster, NotShadowReceiver};
use bevy::mesh::{Indices, PrimitiveTopology, VertexAttributeValues};
use bevy::prelude::*;

/// At most this many tracers fly at once (the oldest go first).
const MAX_TRACERS: usize = 256;
/// A ribbon is cut into pieces no longer than half their distance from the eye (within these bounds), so its
/// width on screen holds along it, also where it passes close by the camera.
const MIN_PIECE_M: f32 = 0.25;
const MAX_PIECE_M: f32 = 12.0;
const MAX_PIECES: usize = 64;
/// Widths in px are px at 1080p.
const REF_HEIGHT_PX: f32 = 1080.0;

/// One shot's tracer.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Tracer {
    pub from: Vec3,
    pub to: Vec3,
    /// Seconds since the shot.
    pub age: f32,
    pub own: bool,
}

impl Tracer {
    fn len(&self) -> f32 {
        self.from.distance(self.to)
    }

    fn dir(&self) -> Vec3 {
        (self.to - self.from).normalize_or_zero()
    }

    /// How far the head has flown, and the tail behind it (metres from the muzzle).
    pub fn streak(&self, f: &TracerFeel) -> (f32, f32) {
        let head = (self.age * f.speed_mps).min(self.len());
        (head, (self.age * f.speed_mps - f.streak_m).clamp(0.0, head))
    }

    /// Still something to draw: the streak in flight, or its smoke fading.
    pub fn alive(&self, f: &TracerFeel) -> bool {
        let flown = self.len() / f.speed_mps.max(1.0);
        self.age < flown + (f.streak_m / f.speed_mps.max(1.0)).max(f.smoke.life_s)
    }
}

#[derive(Resource, Default)]
pub struct Tracers(pub Vec<Tracer>);

/// Where the camera is and how big a px at 1080p is a metre away.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct View {
    pub eye: Vec3,
    /// Metres per px (at 1080p) one metre from the eye.
    pub m_per_px: f32,
}

impl View {
    pub fn new(eye: Vec3, vfov: f32) -> View {
        View { eye, m_per_px: 2.0 * (vfov * 0.5).tan() / REF_HEIGHT_PX }
    }

    /// `width_m`, kept between `min_px` and `max_px` on screen at `p`.
    pub fn width(&self, p: Vec3, width_m: f32, min_px: f32, max_px: f32) -> f32 {
        let per_px = self.m_per_px * p.distance(self.eye).max(0.01);
        width_m.max(min_px * per_px).min(max_px * per_px)
    }
}

/// The tracer mesh's vertices and triangles.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct Geometry {
    pub positions: Vec<[f32; 3]>,
    pub colors: Vec<[f32; 4]>,
    pub indices: Vec<u32>,
}

impl Geometry {
    pub(super) fn clear(&mut self) {
        self.positions.clear();
        self.colors.clear();
        self.indices.clear();
    }

    /// A camera-facing ribbon from `a` to `b`: width and colour at each end come from `at(0..1)`, cut into pieces
    /// so the width holds on screen along a long one (`cuts` is scratch space).
    pub(super) fn ribbon(
        &mut self,
        cuts: &mut Vec<f32>,
        view: &View,
        a: Vec3,
        b: Vec3,
        at: impl Fn(f32) -> (f32, f32, f32, [f32; 4]),
    ) {
        let len = a.distance(b);
        if len < 1e-3 {
            return;
        }
        let dir = (b - a) / len;
        cuts_into(cuts, view.eye, a, dir, len);
        for pair in cuts.windows(2) {
            let (t0, t1) = (pair[0] / len, pair[1] / len);
            let (p0, p1) = (a + dir * pair[0], a + dir * pair[1]);
            let side = dir.cross((p0 + p1) * 0.5 - view.eye).normalize_or_zero();
            if side == Vec3::ZERO {
                continue; // seen end on
            }
            let base = self.positions.len() as u32;
            for (p, t) in [(p0, t0), (p1, t1)] {
                let (width_m, min_px, max_px, color) = at(t);
                let half = side * view.width(p, width_m, min_px, max_px) * 0.5;
                self.positions.push((p - half).to_array());
                self.positions.push((p + half).to_array());
                self.colors.push(color);
                self.colors.push(color);
            }
            self.indices.extend_from_slice(&[base, base + 1, base + 3, base, base + 3, base + 2]);
        }
    }
}

/// Where to cut a ribbon running `len` metres from `a` along `dir` (metres from `a`, both ends included): from the
/// point nearest the eye outward, each piece at most half its distance from the eye.
#[cfg(test)]
pub fn cuts(eye: Vec3, a: Vec3, dir: Vec3, len: f32) -> Vec<f32> {
    let mut out = Vec::new();
    cuts_into(&mut out, eye, a, dir, len);
    out
}

/// [`cuts`] into `out` (cleared first), in order from `a`.
fn cuts_into(out: &mut Vec<f32>, eye: Vec3, a: Vec3, dir: Vec3, len: f32) {
    out.clear();
    let near = (eye - a).dot(dir).clamp(0.0, len);
    let gap = (a + dir * near).distance(eye);
    let step = |s: f32| (0.5 * (gap * gap + (s - near) * (s - near)).sqrt()).clamp(MIN_PIECE_M, MAX_PIECE_M);
    // behind the nearest point, from it toward `a` (reversed below), then ahead of it
    let mut s = near;
    while s > 0.0 && out.len() < MAX_PIECES / 2 {
        s = (s - step(s)).max(0.0);
        out.push(s);
    }
    if s > 0.0 {
        out.push(0.0);
    }
    out.reverse();
    let behind = out.len();
    out.push(near);
    s = near;
    while s < len && out.len() - behind <= MAX_PIECES / 2 {
        s = (s + step(s)).min(len);
        out.push(s);
    }
    if s < len {
        out.push(len);
    }
}

pub(super) fn mul_alpha(c: [f32; 4], a: f32) -> [f32; 4] {
    [c[0], c[1], c[2], c[3] * a.clamp(0.0, 1.0)]
}

/// Without HDR a colour above 1 would clip to white: scale it down, keeping its hue.
pub(super) fn fit_ldr(c: [f32; 4]) -> [f32; 4] {
    let m = c[0].max(c[1]).max(c[2]).max(1.0);
    [c[0] / m, c[1] / m, c[2] / m, c[3]]
}

/// Every tracer's smoke, then glows, then cores (later draws over earlier).
#[cfg(test)]
pub fn build(tracers: &[Tracer], f: &TracerFeel, view: &View, hdr: bool) -> Geometry {
    let mut g = Geometry::default();
    build_into(&mut g, &mut Vec::new(), tracers, f, view, hdr);
    g
}

/// [`build`] into `g` (cleared first), with `cuts` as scratch space.
fn build_into(g: &mut Geometry, cuts: &mut Vec<f32>, tracers: &[Tracer], f: &TracerFeel, view: &View, hdr: bool) {
    g.clear();
    let color = |c: [f32; 4]| if hdr { c } else { fit_ldr(c) };
    for t in tracers {
        let (dir, (head, _)) = (t.dir(), t.streak(f));
        let s = &f.smoke;
        // The smoke was left where the bullet passed: older (fainter, wider) toward the muzzle.
        let skip = if t.own { s.skip_own_m } else { 0.0 };
        let start = ((t.age - s.life_s) * f.speed_mps).max(skip);
        if head > start {
            let smoke_age = |d: f32| ((t.age - d / f.speed_mps) / s.life_s.max(1e-3)).clamp(0.0, 1.0);
            let (a, b) = (t.from + dir * start, t.from + dir * head);
            g.ribbon(cuts, view, a, b, |k| {
                let age = smoke_age(start + (head - start) * k);
                (s.width_m + s.grow_m * age, s.min_px, s.max_px, mul_alpha(color(s.color), 1.0 - age))
            });
        }
    }
    for ribbon in [&f.glow, &f.core] {
        for t in tracers {
            let (head, tail) = t.streak(f);
            if head <= tail {
                continue;
            }
            let Ribbon { width_m, min_px, max_px, own, other } = *ribbon;
            let c = color(if t.own { own } else { other });
            let dir = t.dir();
            // Bright at the head, gone at the tail.
            g.ribbon(cuts, view, t.from + dir * tail, t.from + dir * head, |k| {
                (width_m, min_px, max_px, mul_alpha(c, k))
            });
        }
    }
}

#[derive(Component)]
pub(crate) struct TracerMesh;

pub(crate) fn spawn_tracer_mesh(
    mut commands: Commands,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut tracers: ResMut<Tracers>,
) {
    tracers.0.clear();
    let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
    write_mesh(&mut mesh, &Geometry::default());
    commands.spawn((
        TracerMesh,
        Name::new("Tracers"),
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
        Visibility::Hidden,
        NoFrustumCulling,
        NotShadowCaster,
        NotShadowReceiver,
        DespawnOnExit(AppState::InGame),
    ));
}

/// The mesh's buffers from `g` (a degenerate triangle when there is nothing, so the buffers are never empty),
/// written into the buffers the mesh already has: they only grow, nothing is allocated per frame.
pub(super) fn write_mesh(mesh: &mut Mesh, g: &Geometry) {
    let empty = g.indices.is_empty();
    let n = if empty { 3 } else { g.positions.len() };
    match mesh.attribute_mut(Mesh::ATTRIBUTE_POSITION) {
        Some(VertexAttributeValues::Float32x3(v)) => {
            v.clear();
            if empty { v.extend([[0.0; 3]; 3]) } else { v.extend_from_slice(&g.positions) }
        }
        _ => {
            mesh.insert_attribute(Mesh::ATTRIBUTE_POSITION, if empty { vec![[0.0; 3]; 3] } else { g.positions.clone() })
        }
    }
    match mesh.attribute_mut(Mesh::ATTRIBUTE_COLOR) {
        Some(VertexAttributeValues::Float32x4(v)) => {
            v.clear();
            if empty { v.extend([[0.0; 4]; 3]) } else { v.extend_from_slice(&g.colors) }
        }
        _ => mesh.insert_attribute(Mesh::ATTRIBUTE_COLOR, if empty { vec![[0.0; 4]; 3] } else { g.colors.clone() }),
    }
    // The material is unlit: constant normals and UVs, only resized.
    match mesh.attribute_mut(Mesh::ATTRIBUTE_NORMAL) {
        Some(VertexAttributeValues::Float32x3(v)) => v.resize(n, [0.0, 1.0, 0.0]),
        _ => mesh.insert_attribute(Mesh::ATTRIBUTE_NORMAL, vec![[0.0, 1.0, 0.0]; n]),
    }
    match mesh.attribute_mut(Mesh::ATTRIBUTE_UV_0) {
        Some(VertexAttributeValues::Float32x2(v)) => v.resize(n, [0.0, 0.0]),
        _ => mesh.insert_attribute(Mesh::ATTRIBUTE_UV_0, vec![[0.0, 0.0]; n]),
    }
    match mesh.indices_mut() {
        Some(Indices::U32(i)) => {
            i.clear();
            if empty { i.extend([0, 1, 2]) } else { i.extend_from_slice(&g.indices) }
        }
        _ => mesh.insert_indices(Indices::U32(if empty { vec![0, 1, 2] } else { g.indices.clone() })),
    }
}

/// Buffers kept from frame to frame: the geometry and a ribbon's cuts.
#[derive(Default)]
pub(crate) struct Scratch {
    geometry: Geometry,
    cuts: Vec<f32>,
}

/// Takes the new tracers, ages them, drops the finished ones and rebuilds the mesh for this frame's camera.
#[allow(clippy::too_many_arguments)]
pub(crate) fn draw_tracers(
    time: Res<Time>,
    feel: Res<FeelData>,
    mut feedback: ResMut<Feedback>,
    mut tracers: ResMut<Tracers>,
    camera: Query<(&Transform, &Projection, Has<Hdr>), With<ViewCamera>>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut shown: Query<(&Mesh3d, &mut Visibility), With<TracerMesh>>,
    mut scratch: Local<Scratch>,
) {
    let f = &feel.tracers;
    let dt = time.delta_secs();
    for t in &mut tracers.0 {
        t.age += dt;
    }
    for (from, to, age, own) in feedback.tracers.drain(..) {
        tracers.0.push(Tracer { from, to, age, own });
    }
    tracers.0.retain(|t| t.alive(f));
    let extra = tracers.0.len().saturating_sub(MAX_TRACERS);
    tracers.0.drain(..extra);
    let Some((cam, projection, hdr)) = camera.iter().next() else { return };
    let view = View::new(cam.translation, vfov_of(projection));
    let Scratch { geometry: g, cuts } = &mut *scratch;
    build_into(g, cuts, &tracers.0, f, &view, hdr);
    for (handle, mut vis) in &mut shown {
        let on = !g.indices.is_empty();
        vis.set_if_neq(if on { Visibility::Inherited } else { Visibility::Hidden });
        if !on {
            continue;
        }
        if let Some(mut mesh) = meshes.get_mut(&handle.0) {
            write_mesh(&mut mesh, g);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn feel() -> TracerFeel {
        FeelData::embedded().tracers
    }

    fn shot(len: f32, age: f32, own: bool) -> Tracer {
        Tracer { from: Vec3::ZERO, to: Vec3::NEG_Z * len, age, own }
    }

    /// The streak flies at the tracer speed, a streak's length long, and stops at the end; the smoke outlasts it.
    #[test]
    fn a_tracer_flies_to_the_hit_and_its_smoke_fades_after() {
        let f = feel();
        let t = shot(100.0, 0.1, true);
        let (head, tail) = t.streak(&f);
        assert!((head - f.speed_mps * 0.1).abs() < 1e-3 && (head - tail - f.streak_m).abs() < 1e-3, "{head} {tail}");
        assert!(f.streak_m > 5.0, "longer than the old 5 m streak");
        let (head, tail) = shot(100.0, 1.0, true).streak(&f);
        assert_eq!((head, tail), (100.0, 100.0), "arrived: nothing left of the streak");
        let flown = 100.0 / f.speed_mps;
        assert!(shot(100.0, flown + f.smoke.life_s * 0.5, true).alive(&f), "the smoke still shows");
        assert!(!shot(100.0, flown + f.smoke.life_s + 0.01, true).alive(&f), "then it is gone");
        // A shot into a wall at a metre still flashes its streak.
        assert!(shot(1.0, 0.0, false).alive(&f));
    }

    /// Ribbons face the camera, bright at the head, and keep their width on screen between min and max px.
    #[test]
    fn ribbons_face_the_camera_and_hold_their_width_on_screen() {
        let f = feel();
        let view = View::new(Vec3::new(0.0, 0.0, 10.0), 70f32.to_radians());
        // Far: never thinner than min_px; near: never fatter than max_px.
        let far = Vec3::new(0.0, 0.0, -300.0);
        let px = |p: Vec3, w: f32| w / (view.m_per_px * p.distance(view.eye));
        assert!((px(far, view.width(far, 0.02, 2.0, 4.0)) - 2.0).abs() < 1e-3);
        let near = Vec3::new(0.0, 0.0, 9.5);
        assert!((px(near, view.width(near, 0.02, 2.0, 4.0)) - 4.0).abs() < 1e-3);

        // A tracer crossing the view left to right, mid flight.
        let t = Tracer { from: Vec3::new(-50.0, 0.0, -20.0), to: Vec3::new(50.0, 0.0, -20.0), age: 0.12, own: false };
        let g = build(&[t], &f, &view, true);
        assert!(!g.indices.is_empty() && g.indices.iter().all(|&i| (i as usize) < g.positions.len()));
        // Side by side across the ribbon (y), not in depth: the quads face the camera.
        for pair in g.positions.chunks(2) {
            let (a, b) = (Vec3::from(pair[0]), Vec3::from(pair[1]));
            assert!((a.z - b.z).abs() < 1e-4 && (a.x - b.x).abs() < 1e-4 && (a.y - b.y).abs() > 1e-4);
        }
        // The core (built last) is brightest at its head: alpha 1 there.
        let core = &g.colors[g.colors.len() - 4..];
        assert_eq!(core[2][3], 1.0);
        assert!(g.colors.iter().all(|c| c[3] <= 1.0 && c[3] >= 0.0));
        let others = f.core.other;
        assert!(core[2][0] == others[0] && core[2][1] == others[1], "HDR colours as given");
        // Without HDR the colour keeps its hue under 1.
        let ldr = build(&[t], &f, &view, false);
        let c = ldr.colors[ldr.colors.len() - 2];
        assert!(c[0] <= 1.0 && c[1] <= 1.0 && (c[1] / c[0] - others[1] / others[0]).abs() < 1e-5);
    }

    /// A shot passing a metre from the eye (fired at us) is cut finely where it passes, so it stays thin on screen
    /// there instead of fanning out between two far cut points (screenshot finding); far off, the pieces are long.
    #[test]
    fn a_ribbon_passing_close_by_is_cut_finely_there() {
        let eye = Vec3::new(0.0, 1.0, 0.0);
        let (a, len) = (Vec3::new(-60.0, 0.0, 0.0), 100.0);
        let c = cuts(eye, a, Vec3::X, len);
        assert_eq!((c[0], *c.last().unwrap()), (0.0, len));
        assert!(c.windows(2).all(|w| w[1] > w[0]), "{c:?}");
        assert!(c.len() <= MAX_PIECES + 2, "{} pieces", c.len());
        for w in c.windows(2) {
            let nearest = (a + Vec3::X * 60.0f32.clamp(w[0], w[1])).distance(eye);
            let piece = w[1] - w[0];
            assert!(piece <= (0.5 * nearest).clamp(MIN_PIECE_M, MAX_PIECE_M) + 1e-3, "{w:?} at {nearest} m");
        }
        assert!(c.windows(2).any(|w| w[1] - w[0] > 5.0), "long pieces far away");
        // Seen from far off, a short streak is one piece.
        assert_eq!(cuts(Vec3::new(0.0, 0.0, 500.0), a, Vec3::X, 9.0).len(), 2);
    }

    /// The smoke trail fills the path the bullet flew, faded toward the muzzle, and none in front of our own gun.
    /// Finding tracer-mesh-churn: the mesh is rewritten in its own buffers, every attribute as long as the
    /// positions, and back to the placeholder triangle when nothing flies.
    #[test]
    fn the_mesh_is_rewritten_in_place() {
        let mut mesh = Mesh::new(PrimitiveTopology::TriangleList, RenderAssetUsages::default());
        write_mesh(&mut mesh, &Geometry::default());
        assert_eq!(mesh.count_vertices(), 3);
        let view = View::new(Vec3::new(5.0, 2.0, 0.0), 70f32.to_radians());
        let g = build(&[shot(100.0, 0.1, true), shot(40.0, 0.05, false)], &feel(), &view, true);
        let mut scratch = Geometry::default();
        build_into(
            &mut scratch,
            &mut vec![9.0; 4],
            &[shot(100.0, 0.1, true), shot(40.0, 0.05, false)],
            &feel(),
            &view,
            true,
        );
        assert_eq!(scratch, g, "built into old buffers: the same");
        for _ in 0..2 {
            write_mesh(&mut mesh, &g);
            let n = g.positions.len();
            assert!(n > 3);
            assert_eq!(mesh.count_vertices(), n);
            for a in [Mesh::ATTRIBUTE_NORMAL, Mesh::ATTRIBUTE_UV_0, Mesh::ATTRIBUTE_COLOR] {
                assert_eq!(mesh.attribute(a).map(|v| v.len()), Some(n), "{a:?}");
            }
            assert_eq!(mesh.indices().map(|i| i.len()), Some(g.indices.len()));
        }
        write_mesh(&mut mesh, &Geometry::default());
        assert_eq!(mesh.count_vertices(), 3);
        assert_eq!(mesh.attribute(Mesh::ATTRIBUTE_UV_0).map(|v| v.len()), Some(3));
    }

    #[test]
    fn the_smoke_follows_the_path() {
        let f = feel();
        let view = View::new(Vec3::new(5.0, 2.0, 0.0), 70f32.to_radians());
        let t = shot(200.0, 0.3, true);
        let g = build(&[t], &f, &view, true);
        // The streak is past 100 m by now, the smoke reaches back toward the gun.
        let (_, tail) = t.streak(&f);
        assert!(g.positions.iter().any(|p| -p[2] < tail - 50.0), "smoke behind the streak");
        // Fainter toward the muzzle: the smoke's alpha grows along the path.
        let smoke_alpha: Vec<f32> = g.colors.iter().take(4).map(|c| c[3]).collect();
        assert!(smoke_alpha[0] < smoke_alpha[2], "{smoke_alpha:?}");
        let nearest = g.positions.iter().map(|p| -p[2]).fold(f32::MAX, f32::min);
        assert!(nearest >= f.smoke.skip_own_m - 1e-3, "own smoke starts {} m out", f.smoke.skip_own_m);
        let other = build(&[Tracer { own: false, ..t }], &f, &view, true);
        let nearest = other.positions.iter().map(|p| -p[2]).fold(f32::MAX, f32::min);
        assert!(nearest < 0.1, "another player's starts at their muzzle");
    }
}
