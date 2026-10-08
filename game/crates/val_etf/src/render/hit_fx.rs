//! Hit feedback on the player that was hit, not on the crosshair (user direction):
//!
//! - **Hit markers**: a small X where our shot landed on them, held on that spot of their body as they move, in
//!   the HUD's colours (shield blue, flesh white, head gold, kill in the enemy colour; a broken arc and a kill add
//!   a ring), popping in and fading fast. MOUSE & AIM's HIT MARKERS picks which kinds show. They come from the
//!   host's [`HitConfirm`]; the spot is the one our shot claimed ([`ClaimedHit`], matched by shot number), or the
//!   confirm's world point when the claim is not known.
//! - **Halo cracks**: the arc that took the hit flashes, swells and sheds shards; the arc that breaks shatters
//!   (more shards and a ring flash). Driven by the replicated shield values, so everyone sees them.
//!
//! Numbers in `feel.ron` ([`HitFeel`], [`HaloFeel`]).

use super::feel::{FeelData, HitFeel, Shards};
use super::{HaloArc, PlayerVisual, ViewCamera, arc_angle, arc_glow, tier_color, vfov_of};
use crate::AppState;
use crate::client::Feedback;
use crate::config::Cli;
use crate::settings::{HitMarkers, Settings};
use crate::ui_kit as kit;
use bevy::light::{NotShadowCaster, NotShadowReceiver};
use bevy::prelude::*;
use bevy::window::PrimaryWindow;
use lightyear::prelude::*;
use std::collections::HashMap;
use std::f32::consts::SQRT_2;
use vetf_net::*;
use vetf_sim::Zone;

/// Markers on screen at once (the oldest gives way).
const SLOTS: usize = 8;
/// The markers' layer: over the scope picture (-10), under the HUD.
const MARKER_Z: i32 = -5;
const MARKER_OUTLINE: Color = Color::srgba(0.0, 0.0, 0.0, 0.55);

/// One of our shots hit a player on our screen (the claim we sent the host): the spot, in that player's own
/// frame (feet at the origin, turned to their yaw), so a marker can stay on it as they move.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ClaimedHit {
    pub seq: u32,
    pub victim: u64,
    pub local: Vec3,
}

impl ClaimedHit {
    /// A hit at world `point` on a player standing at `feet`, turned to `yaw`.
    pub fn new(seq: u32, victim: u64, point: Vec3, feet: Vec3, yaw: f32) -> ClaimedHit {
        ClaimedHit { seq, victim, local: Quat::from_rotation_y(-yaw) * (point - feet) }
    }
}

/// Where a marker sits: on a player (their id, a spot in their frame) or at a fixed world point.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Anchor {
    On { victim: u64, local: Vec3 },
    At(Vec3),
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Marker {
    pub anchor: Anchor,
    pub kind: HitKind,
    pub head: bool,
    pub broke: bool,
    pub age: f32,
}

impl Marker {
    /// The marker of a confirm: on the spot our claim with its shot number hit, else at the confirm's point.
    pub fn of(confirm: &HitConfirm, claims: &[(ClaimedHit, f32)]) -> Marker {
        let claim = claims.iter().rev().find(|(c, _)| c.seq == confirm.seq && c.victim == confirm.victim);
        Marker {
            anchor: match claim {
                Some((c, _)) => Anchor::On { victim: c.victim, local: c.local },
                None => Anchor::At(confirm.point),
            },
            kind: confirm.kind,
            head: confirm.zone == Zone::Head,
            broke: confirm.shield_broke,
            age: 0.0,
        }
    }

    /// (scale, alpha) at its age: it pops in large, shrinks to size, holds, then fades out; `None` when done.
    pub fn look(&self, h: &HitFeel) -> Option<(f32, f32)> {
        if self.age >= h.life_s {
            return None;
        }
        let pop = (self.age / h.pop_s.max(1e-3)).min(1.0);
        let base = match (self.kind, self.head) {
            (HitKind::Kill, _) => h.kill_scale,
            (_, true) => h.head_scale,
            _ => 1.0,
        };
        let half = h.life_s * 0.5;
        let alpha = if self.age < half { 1.0 } else { 1.0 - (self.age - half) / half };
        Some((base * (h.pop_scale + (1.0 - h.pop_scale) * pop), alpha.clamp(0.0, 1.0)))
    }

    /// Its colour (HUD rules) and whether it has a ring.
    pub fn color(&self, enemy: Color) -> (Color, bool) {
        match self.kind {
            HitKind::Kill => (enemy, true),
            HitKind::Shield => (kit::TIERS[2], self.broke),
            HitKind::Health if self.head => (kit::TIERS[4], self.broke),
            HitKind::Health => (Color::WHITE, self.broke),
        }
    }
}

/// Whether HIT MARKERS shows a hit of this kind.
pub fn hit_marker_shown(setting: HitMarkers, kind: HitKind) -> bool {
    match setting {
        HitMarkers::ShieldFlesh => true,
        HitMarkers::FleshOnly => kind != HitKind::Shield,
        HitMarkers::Off => false,
    }
}

/// Where a world point shows on screen, as a share of the width and height from the top left; `None` behind
/// the camera. `vfov` is the vertical field of view (radians), `aspect` width / height.
pub fn on_screen(cam: &Transform, vfov: f32, aspect: f32, p: Vec3) -> Option<Vec2> {
    let v = cam.rotation.inverse() * (p - cam.translation);
    if v.z > -0.05 {
        return None;
    }
    let t = (vfov * 0.5).tan();
    let ndc = Vec2::new(v.x / (-v.z * t * aspect), v.y / (-v.z * t));
    Some(Vec2::new(0.5 + ndc.x * 0.5, 0.5 - ndc.y * 0.5))
}

/// Our recent claims (waiting for the host's confirm) and the markers showing.
#[derive(Resource, Default)]
pub struct HitMemory {
    claims: Vec<(ClaimedHit, f32)>,
    markers: Vec<Marker>,
}

#[derive(Component)]
pub(crate) struct MarkerLayer;
#[derive(Component)]
pub(crate) struct MarkerSlot(usize);
#[derive(Component)]
pub(crate) struct MarkerBar;
#[derive(Component)]
pub(crate) struct MarkerRing;

pub(crate) fn spawn_marker_layer(mut commands: Commands, feel: Res<FeelData>, mut memory: ResMut<HitMemory>) {
    *memory = HitMemory::default();
    let h = &feel.hits;
    let layer = commands
        .spawn((
            MarkerLayer,
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
            GlobalZIndex(MARKER_Z),
            Visibility::Inherited,
            Pickable::IGNORE,
            DespawnOnExit(AppState::InGame),
        ))
        .id();
    // Four short bars on the diagonals with a gap in the middle, and a ring for a broken arc or a kill.
    let reach = (h.gap_px + h.size_px * 0.5) / SQRT_2;
    for i in 0..SLOTS {
        let slot = commands
            .spawn((
                MarkerSlot(i),
                Node { position_type: PositionType::Absolute, width: px(0), height: px(0), ..default() },
                UiTransform::IDENTITY,
                Visibility::Hidden,
                Pickable::IGNORE,
                ChildOf(layer),
            ))
            .id();
        for (sx, sy) in [(-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)] {
            let angle: f32 = if sx == sy { 45.0 } else { -45.0 };
            commands.spawn((
                MarkerBar,
                Node {
                    position_type: PositionType::Absolute,
                    left: px(sx * reach - h.size_px * 0.5),
                    top: px(sy * reach - h.thickness_px * 0.5),
                    width: px(h.size_px),
                    height: px(h.thickness_px),
                    ..default()
                },
                BackgroundColor(Color::WHITE),
                Outline::new(px(1), px(0), MARKER_OUTLINE),
                UiTransform::from_rotation(Rot2::degrees(angle)),
                ChildOf(slot),
            ));
        }
        commands.spawn((
            MarkerRing,
            Node {
                position_type: PositionType::Absolute,
                left: px(-h.ring_px * 0.5),
                top: px(-h.ring_px * 0.5),
                width: px(h.ring_px),
                height: px(h.ring_px),
                border: UiRect::all(px(2)),
                border_radius: BorderRadius::MAX,
                ..default()
            },
            BorderColor::all(Color::WHITE),
            Visibility::Hidden,
            ChildOf(slot),
        ));
    }
}

/// New claims and confirms from `client` become markers (the kinds HIT MARKERS shows); old ones age out.
pub(crate) fn take_hits(
    time: Res<Time>,
    feel: Res<FeelData>,
    settings: Res<Settings>,
    mut feedback: ResMut<Feedback>,
    mut memory: ResMut<HitMemory>,
) {
    let (dt, h) = (time.delta_secs(), &feel.hits);
    let HitMemory { claims, markers } = &mut *memory;
    for (_, age) in claims.iter_mut() {
        *age += dt;
    }
    claims.retain(|(_, age)| *age < h.remember_s);
    claims.extend(feedback.claims.drain(..).map(|c| (c, 0.0)));
    for m in markers.iter_mut() {
        m.age += dt;
    }
    markers.retain(|m| m.look(h).is_some());
    for confirm in feedback.hits.drain(..) {
        if hit_marker_shown(settings.crosshair.hit_markers, confirm.kind) {
            let m = Marker::of(&confirm, claims);
            debug!("hit marker {:?} (head {}, broke {}) {:?}", m.kind, m.head, m.broke, m.anchor);
            markers.push(m);
        }
    }
    let extra = markers.len().saturating_sub(SLOTS);
    markers.drain(..extra);
}

/// Each marker on its player's body this frame (after the camera and the players have moved).
pub(crate) fn place_markers(
    feel: Res<FeelData>,
    settings: Res<Settings>,
    screens: Res<crate::screens::Screens>,
    memory: Res<HitMemory>,
    windows: Query<&Window, With<PrimaryWindow>>,
    camera: Query<(&Transform, &Projection), With<ViewCamera>>,
    players: Query<(&PlayerId, &Transform), (With<PlayerVisual>, Without<ViewCamera>)>,
    mut layer: Query<&mut Visibility, With<MarkerLayer>>,
    mut slots: Query<(&MarkerSlot, &mut Node, &mut UiTransform, &mut Visibility, &Children), Without<MarkerLayer>>,
    mut bars: Query<&mut BackgroundColor, With<MarkerBar>>,
    mut rings: Query<
        (&mut BorderColor, &mut Visibility),
        (With<MarkerRing>, Without<MarkerSlot>, Without<MarkerLayer>),
    >,
) {
    // Hidden with the HUD while a hub screen is open over the match.
    let open = screens.is_empty();
    for mut v in &mut layer {
        v.set_if_neq(if open { Visibility::Inherited } else { Visibility::Hidden });
    }
    let Some((cam, projection)) = camera.iter().next() else { return };
    let aspect = windows.iter().next().map_or(16.0 / 9.0, |w| w.width() / w.height().max(1.0));
    let vfov = vfov_of(projection);
    let enemy = settings.team_colors().1;
    for (slot, mut node, mut transform, mut vis, children) in &mut slots {
        let placed = memory.markers.get(slot.0).and_then(|m| {
            let world = match m.anchor {
                Anchor::At(p) => p,
                Anchor::On { victim, local } => {
                    players.iter().find(|(id, _)| id.0 == victim).map(|(_, t)| t.transform_point(local))?
                }
            };
            Some((m, on_screen(cam, vfov, aspect, world)?, m.look(&feel.hits)?))
        });
        let Some((m, at, (scale, alpha))) = placed else {
            vis.set_if_neq(Visibility::Hidden);
            continue;
        };
        vis.set_if_neq(Visibility::Inherited);
        (node.left, node.top) = (percent(at.x * 100.0), percent(at.y * 100.0));
        transform.scale = Vec2::splat(scale);
        let (color, ring) = m.color(enemy);
        let color = color.with_alpha(alpha);
        for child in children.iter() {
            if let Ok(mut bg) = bars.get_mut(child) {
                bg.0 = color;
            }
            if let Ok((mut border, mut v)) = rings.get_mut(child) {
                *border = BorderColor::all(color);
                v.set_if_neq(if ring { Visibility::Inherited } else { Visibility::Hidden });
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------- halo cracks

/// An arc of a player's halo lost shield (`broke`: down to nothing).
#[derive(Message, Debug, Clone, Copy, PartialEq)]
pub struct HaloHit {
    pub player: Entity,
    pub zone: Zone,
    pub broke: bool,
}

/// Which arcs (by `Zone::index`) cracked between two readings of a halo's shields, and whether each broke.
pub fn halo_drops(before: [f32; 4], now: [f32; 4], min_drop: f32) -> Vec<(usize, bool)> {
    (0..4)
        .filter_map(|i| {
            let broke = before[i] > 0.0 && now[i] <= 0.0;
            (broke || before[i] - now[i] >= min_drop).then_some((i, broke))
        })
        .collect()
}

/// Other players' shields, read each frame: a drop cracks that arc.
pub(crate) fn watch_halos(
    feel: Res<FeelData>,
    players: Query<(Entity, &Vitals), (With<PlayerVisual>, Without<Controlled>)>,
    mut last: Local<HashMap<Entity, [f32; 4]>>,
    mut out: MessageWriter<HaloHit>,
) {
    for (e, v) in &players {
        if v.health.dead {
            last.remove(&e);
            continue;
        }
        let now = Zone::ALL.map(|z| v.halo.shield[z]);
        if let Some(before) = last.insert(e, now) {
            for (i, broke) in halo_drops(before, now, feel.halo.min_drop) {
                out.write(HaloHit { player: e, zone: Zone::ALL[i], broke });
            }
        }
    }
    last.retain(|e, _| players.contains(*e));
}

/// An arc flashing after a hit: seconds left.
#[derive(Component)]
pub(crate) struct ArcFlash(f32);

/// A shard of a cracked or shattered arc, flying.
#[derive(Component)]
pub(crate) struct Shard {
    vel: Vec3,
    axis: Vec3,
    spin: f32,
    age: f32,
    life: f32,
    size: f32,
}

/// The ring flash of a breaking arc: its own material, fading as it grows.
#[derive(Component)]
pub(crate) struct BreakRing {
    age: f32,
    material: Handle<StandardMaterial>,
    color: LinearRgba,
}

/// The shards' mesh and a glowing material per halo tier.
#[derive(Resource, Default)]
pub(crate) struct ShardAssets {
    mesh: Option<Handle<Mesh>>,
    materials: HashMap<u8, Handle<StandardMaterial>>,
}

/// A small repeatable random number stream for the shards' directions.
fn next_random(state: &mut u32) -> f32 {
    *state ^= *state << 13;
    *state ^= *state >> 17;
    *state ^= *state << 5;
    (*state & 0xFFFF) as f32 / 65535.0
}

/// A cracked arc flashes and sheds a few shards; a broken one shatters with more and a ring flash.
#[allow(clippy::too_many_arguments)]
pub(crate) fn crack_halos(
    mut commands: Commands,
    feel: Res<FeelData>,
    mut hits: MessageReader<HaloHit>,
    tree: Query<&Children>,
    arcs: Query<(&HaloArc, &GlobalTransform, &Mesh3d)>,
    shards: Query<(), With<Shard>>,
    mut assets: ResMut<ShardAssets>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
    mut seed: Local<u32>,
) {
    let f = &feel.halo;
    let mut room = f.max_shards.saturating_sub(shards.iter().count());
    for hit in hits.read() {
        let found = tree
            .iter_descendants(hit.player)
            .find_map(|e| arcs.get(e).ok().filter(|(a, ..)| a.zone == hit.zone).map(|a| (e, a)));
        let Some((arc_e, (arc, at, arc_mesh))) = found else { continue };
        commands.entity(arc_e).insert(ArcFlash(f.flash_s));
        let mid = arc_angle(arc.zone);
        let spot = at.transform_point(Vec3::new(mid.cos(), 0.0, mid.sin()) * arc.radius);
        let out = (spot - at.translation()).normalize_or(Vec3::Y);
        let spec: Shards = if hit.broke { f.shatter } else { f.crack };
        let mesh = assets.mesh.get_or_insert_with(|| meshes.add(Tetrahedron::default())).clone();
        let material = assets
            .materials
            .entry(arc.tier)
            .or_insert_with(|| {
                materials.add(StandardMaterial {
                    base_color: Color::from(tier_color(arc.tier) * 1.8),
                    unlit: true,
                    ..default()
                })
            })
            .clone();
        let mut state = if *seed == 0 { 0x2545_F491 } else { *seed };
        let n = (spec.count as usize).min(room);
        room -= n;
        for _ in 0..n {
            let mut r = || next_random(&mut state) * 2.0 - 1.0;
            let scatter = Vec3::new(r(), r(), r()) * 0.8 + Vec3::Y * 0.4;
            let dir = (out + scatter).normalize_or(Vec3::Y);
            let speed = spec.speed_mps * (0.75 + 0.25 * r());
            let axis = Vec3::new(r(), r(), r()).normalize_or(Vec3::X);
            let size = spec.size_m * (0.8 + 0.4 * r().abs());
            commands.spawn((
                Shard {
                    vel: dir * speed,
                    axis,
                    spin: f.spin_rps * std::f32::consts::TAU,
                    age: 0.0,
                    life: spec.life_s,
                    size,
                },
                Mesh3d(mesh.clone()),
                MeshMaterial3d(material.clone()),
                Transform::from_translation(spot + scatter * arc.radius * 0.3).with_scale(Vec3::splat(size)),
                NotShadowCaster,
                NotShadowReceiver,
                DespawnOnExit(AppState::InGame),
            ));
        }
        *seed = state;
        if hit.broke {
            let color = tier_color(arc.tier) * 2.0;
            let material = materials.add(StandardMaterial {
                base_color: Color::from(color),
                unlit: true,
                alpha_mode: AlphaMode::Blend,
                ..default()
            });
            commands.spawn((
                BreakRing { age: 0.0, material: material.clone(), color },
                Mesh3d(arc_mesh.0.clone()),
                MeshMaterial3d(material),
                at.compute_transform(),
                NotShadowCaster,
                NotShadowReceiver,
                DespawnOnExit(AppState::InGame),
            ));
        }
    }
}

/// Flashing arcs glow hotter and swell, back to normal over the flash.
pub(crate) fn flash_arcs(
    mut commands: Commands,
    time: Res<Time>,
    feel: Res<FeelData>,
    mut arcs: Query<(Entity, &HaloArc, &mut ArcFlash, &MeshMaterial3d<StandardMaterial>, &mut Transform)>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let f = &feel.halo;
    for (e, arc, mut flash, material, mut t) in &mut arcs {
        flash.0 -= time.delta_secs();
        let k = (flash.0 / f.flash_s.max(1e-3)).clamp(0.0, 1.0);
        if let Some(mut m) = materials.get_mut(&material.0) {
            m.emissive = arc_glow(arc.tier) * (1.0 + f.flash_gain * k);
        }
        t.scale = Vec3::splat(1.0 + f.pulse_scale * k);
        if flash.0 <= 0.0 {
            commands.entity(e).remove::<ArcFlash>();
        }
    }
}

/// Shards fly out, fall, spin and shrink away; break rings grow and fade.
pub(crate) fn fly_shards(
    mut commands: Commands,
    time: Res<Time>,
    feel: Res<FeelData>,
    mut shards: Query<(Entity, &mut Shard, &mut Transform), Without<BreakRing>>,
    mut rings: Query<(Entity, &mut BreakRing, &mut Transform), Without<Shard>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let (dt, f) = (time.delta_secs(), &feel.halo);
    for (e, mut s, mut t) in &mut shards {
        s.age += dt;
        if s.age >= s.life {
            commands.entity(e).despawn();
            continue;
        }
        s.vel.y -= f.gravity_mps2 * dt;
        s.vel *= (1.0 - 2.0 * dt).max(0.0);
        t.translation += s.vel * dt;
        t.rotate(Quat::from_axis_angle(s.axis, s.spin * dt));
        let k = s.age / s.life;
        t.scale = Vec3::splat(s.size * (1.0 - k * k));
    }
    for (e, mut r, mut t) in &mut rings {
        r.age += dt;
        let k = r.age / f.ring_s.max(1e-3);
        if k >= 1.0 {
            commands.entity(e).despawn();
            continue;
        }
        t.scale = Vec3::splat(1.0 + (f.ring_grow - 1.0) * k);
        if let Some(mut m) = materials.get_mut(&r.material) {
            m.base_color = Color::from(r.color.with_alpha(1.0 - k));
        }
    }
}

/// When `--demo-ui hit-fx` fires the next tracer and the next hit, and how many of each so far.
#[derive(Default)]
pub(crate) struct DemoClock {
    tracer_at: f32,
    hit_at: f32,
    tracers: u32,
    hits: u32,
}

/// `--demo-ui hit-fx`: for screenshots, the nearest other player is hit over and over, cycling through the
/// marker kinds (a shield hit, flesh, a headshot, a broken arc, a kill) and cracking their halo arcs in turn
/// (every fourth one shatters), while tracers fly both ways: ours from the gun to them, theirs past our head.
#[allow(clippy::too_many_arguments)]
pub(crate) fn demo_hit_fx(
    cli: Res<Cli>,
    time: Res<Time>,
    settings: Res<Settings>,
    rig: Res<super::ViewmodelRig>,
    control: Res<crate::client::LocalControl>,
    me: Query<(&PlayerMove, &PlayerWeapon, &PlayerLoadout), With<Controlled>>,
    players: Query<(Entity, &PlayerId, &PlayerMove, &PlayerLook), (With<PlayerVisual>, Without<Controlled>)>,
    mut feedback: ResMut<Feedback>,
    mut halo: MessageWriter<HaloHit>,
    mut clock: Local<DemoClock>,
) {
    if cli.demo_ui.as_deref() != Some("hit-fx") {
        return;
    }
    let Some((mine, weapon, loadout)) = me.iter().next() else { return };
    let eye = mine.0.eye_pos();
    let Some((e, id, mv, look)) =
        players.iter().min_by(|a, b| a.2.0.pos.distance_squared(eye).total_cmp(&b.2.0.pos.distance_squared(eye)))
    else {
        return;
    };
    let t = time.elapsed_secs();
    if t >= clock.tracer_at {
        clock.tracer_at = t + 0.12;
        clock.tracers += 1;
        let theirs = mv.0.eye_pos();
        if clock.tracers.is_multiple_of(2) {
            let ads = weapon.0.ads;
            let fov = super::camera_fov(&settings.mouse, loadout.0.weapon.zoom, ads);
            let lens = super::viewmodel_lens(fov, settings.mouse.viewmodel_fov);
            let at = vetf_sim::input::view_rotation(control.yaw, control.pitch);
            let from = eye + at * super::own_tracer_start(&rig, ads, lens);
            feedback.tracers.push((from, mv.0.pos + Vec3::Y * 1.3, 0.0, true));
        } else {
            let past = (eye - theirs).normalize_or(Vec3::X);
            let side = past.cross(Vec3::Y).normalize_or(Vec3::X) * 0.8;
            // Long, so one is always in flight: a screenshot catches a streak.
            feedback.tracers.push((theirs, eye + side + past * 60.0, 0.0, false));
        }
    }
    if t < clock.hit_at {
        return;
    }
    clock.hit_at = t + 0.3;
    clock.hits += 1;
    let n = clock.hits;
    debug!("demo hit {n} on {:x} standing at {}", id.0, mv.0.pos);
    // Each kind's spot (height, across), on the side facing us: chest, a little right, the head, a little left,
    // the hips.
    let toward = Quat::from_rotation_y(-look.yaw) * (eye - mv.0.pos).with_y(0.0).normalize_or(Vec3::NEG_Z);
    let spots = [(1.25, 0.0), (1.15, 0.12), (1.62, 0.0), (1.3, -0.15), (1.0, 0.05)];
    let (height, across) = spots[n as usize % spots.len()];
    let local = toward * 0.25 + toward.cross(Vec3::Y) * across + Vec3::Y * height;
    let (kind, zone, broke) = match n % 5 {
        0 => (HitKind::Shield, Zone::Torso, false),
        1 => (HitKind::Health, Zone::Torso, false),
        2 => (HitKind::Health, Zone::Head, false),
        3 => (HitKind::Shield, Zone::Arms, true),
        _ => (HitKind::Kill, Zone::Torso, false),
    };
    let seq = 1_000_000 + n;
    feedback.claims.push(ClaimedHit { seq, victim: id.0, local });
    let point = mv.0.pos + Quat::from_rotation_y(look.yaw) * local;
    feedback.hits.push(HitConfirm { victim: id.0, zone, kind, shield_broke: broke, seq, point });
    if n.is_multiple_of(2) {
        halo.write(HaloHit { player: e, zone: Zone::ALL[(n as usize / 2) % 4], broke: n.is_multiple_of(8) });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn confirm(seq: u32, kind: HitKind, zone: Zone) -> HitConfirm {
        HitConfirm { victim: 7, zone, kind, shield_broke: false, seq, point: Vec3::new(1.0, 1.4, -10.0) }
    }

    /// A claim's spot is kept in the victim's own frame, so it follows them as they move and turn.
    #[test]
    fn a_claimed_spot_stays_on_the_player() {
        let (feet, yaw) = (Vec3::new(3.0, 0.5, -8.0), 0.9);
        let point = Vec3::new(3.2, 1.9, -8.3);
        let c = ClaimedHit::new(4, 7, point, feet, yaw);
        let root = Transform::from_translation(feet).with_rotation(Quat::from_rotation_y(yaw));
        assert!(root.transform_point(c.local).abs_diff_eq(point, 1e-5), "the same spot where it hit");
        let moved = Transform::from_translation(feet + Vec3::X * 2.0).with_rotation(Quat::from_rotation_y(yaw + 1.0));
        let there = moved.transform_point(c.local);
        assert!((there.y - point.y).abs() < 1e-5 && there.distance(moved.translation) - point.distance(feet) < 1e-5);
    }

    /// A confirm finds our claim by shot number and victim; without one it marks the confirm's point.
    #[test]
    fn a_confirm_marks_the_spot_our_shot_claimed() {
        let claims = [
            (ClaimedHit { seq: 3, victim: 7, local: Vec3::Y }, 0.1),
            (ClaimedHit { seq: 4, victim: 8, local: Vec3::X }, 0.0),
        ];
        let m = Marker::of(&confirm(3, HitKind::Health, Zone::Head), &claims);
        assert_eq!(m.anchor, Anchor::On { victim: 7, local: Vec3::Y });
        assert!(m.head);
        let lost = Marker::of(&confirm(4, HitKind::Shield, Zone::Torso), &claims);
        assert_eq!(lost.anchor, Anchor::At(Vec3::new(1.0, 1.4, -10.0)), "seq 4 hit another player");
    }

    /// Colours follow the HUD's rules; a broken arc and a kill get a ring; the markers pop, then fade fast.
    #[test]
    fn markers_pop_fade_and_take_the_hud_colours() {
        let h = FeelData::embedded().hits;
        let enemy = kit::ENEMY;
        let mk = |kind, head, broke| Marker { anchor: Anchor::At(Vec3::ZERO), kind, head, broke, age: 0.0 };
        assert_eq!(mk(HitKind::Shield, false, false).color(enemy), (kit::TIERS[2], false));
        assert_eq!(mk(HitKind::Shield, false, true).color(enemy), (kit::TIERS[2], true), "a broken arc rings");
        assert_eq!(mk(HitKind::Health, false, false).color(enemy), (Color::WHITE, false));
        assert_eq!(mk(HitKind::Health, true, false).color(enemy).0, kit::TIERS[4], "a headshot is gold");
        assert_eq!(mk(HitKind::Kill, true, false).color(enemy), (enemy, true));
        let mut m = mk(HitKind::Health, false, false);
        let (pop, a0) = m.look(&h).unwrap();
        assert!(pop > 1.2 && a0 == 1.0, "pops in");
        m.age = h.pop_s;
        assert!((m.look(&h).unwrap().0 - 1.0).abs() < 1e-5, "settles at its size");
        m.age = h.life_s * 0.75;
        let (_, a) = m.look(&h).unwrap();
        assert!(a > 0.0 && a < 1.0, "fading");
        m.age = h.life_s;
        assert_eq!(m.look(&h), None, "gone");
        assert!(h.life_s < 0.6, "fast");
        let kill = Marker { age: h.pop_s, ..mk(HitKind::Kill, false, false) };
        assert!(kill.look(&h).unwrap().0 > 1.0, "a kill marker is bigger");
    }

    #[test]
    fn hit_markers_follow_the_setting() {
        assert!(hit_marker_shown(HitMarkers::ShieldFlesh, HitKind::Shield));
        assert!(!hit_marker_shown(HitMarkers::FleshOnly, HitKind::Shield));
        assert!(hit_marker_shown(HitMarkers::FleshOnly, HitKind::Health));
        assert!(hit_marker_shown(HitMarkers::FleshOnly, HitKind::Kill));
        assert!(!hit_marker_shown(HitMarkers::Off, HitKind::Kill));
    }

    /// The marker sits where the world point is drawn: centre ahead, right to the right, nothing behind.
    #[test]
    fn markers_land_where_the_point_is_drawn() {
        let cam = Transform::from_xyz(0.0, 1.6, 0.0).with_rotation(Quat::from_rotation_y(0.4));
        let vfov = 70f32.to_radians();
        let ahead = cam.translation + cam.forward() * 20.0;
        assert!(on_screen(&cam, vfov, 16.0 / 9.0, ahead).unwrap().abs_diff_eq(Vec2::splat(0.5), 1e-5));
        let right = on_screen(&cam, vfov, 16.0 / 9.0, ahead + cam.right() * 2.0).unwrap();
        let up = on_screen(&cam, vfov, 16.0 / 9.0, ahead + Vec3::Y * 2.0).unwrap();
        assert!(right.x > 0.5 && (right.y - 0.5).abs() < 1e-5 && up.y < 0.5);
        assert_eq!(on_screen(&cam, vfov, 16.0 / 9.0, cam.translation - cam.forward() * 5.0), None);
        // The top edge of the view is the top of the screen.
        let edge = cam.translation + cam.rotation * Vec3::new(0.0, (vfov * 0.5).tan() * 10.0, -10.0);
        assert!(on_screen(&cam, vfov, 16.0 / 9.0, edge).unwrap().y.abs() < 1e-5);
    }

    /// A shield drop cracks its arc; the arc that runs out breaks; regenerating or tiny drops do nothing.
    #[test]
    fn shield_drops_crack_and_break_arcs() {
        let min = FeelData::embedded().halo.min_drop;
        assert_eq!(halo_drops([30.0, 20.0, 10.0, 0.0], [22.0, 20.0, 10.0, 0.0], min), vec![(0, false)]);
        assert_eq!(halo_drops([30.0, 20.0, 4.0, 0.0], [30.0, 20.0, 0.0, 0.0], min), vec![(2, true)]);
        assert!(halo_drops([30.0, 20.0, 10.0, 0.0], [30.0, 20.5, 10.0, 0.0], min).is_empty(), "regen");
        assert!(halo_drops([30.0; 4], [30.0 - min * 0.5, 30.0, 30.0, 30.0], min).is_empty(), "too small");
        assert_eq!(halo_drops([0.3, 0.0, 0.0, 0.0], [0.0; 4], min), vec![(0, true)], "a sliver breaking still breaks");
    }
}
