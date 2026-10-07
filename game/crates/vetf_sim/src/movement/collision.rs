//! Static collision world: convex brushes (boxes, ramps) and a swept-box trace against them.
//!
//! Players collide as an axis-aligned box (half-width = capsule radius), the classic FPS approach:
//! exact, cheap and deterministic, which matters because the same trace runs on the host and inside
//! client prediction rollback. Brushes are plane sets, so ramps and wedges work like boxes.

use glam::Vec3;
use serde::{Deserialize, Serialize};

/// Small gap kept between the player box and surfaces so traces never start inside a brush.
pub const SKIN: f32 = 0.002;

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Plane {
    pub normal: Vec3,
    /// Plane: dot(normal, p) = dist. Solid side is where dot(normal, p) < dist.
    pub dist: f32,
}

/// Which gameplay surfaces a brush belongs to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BrushKind {
    /// Blocks players and bullets.
    Solid,
    /// Blocks players only (invisible map bounds, ceilings).
    PlayerClip,
    /// Blocks bullets and sight only (glass would go here).
    BulletOnly,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Brush {
    pub planes: Vec<Plane>,
    pub min: Vec3,
    pub max: Vec3,
    pub kind: BrushKind,
}

impl Brush {
    pub fn cuboid(min: Vec3, max: Vec3, kind: BrushKind) -> Self {
        let planes = vec![
            Plane { normal: Vec3::X, dist: max.x },
            Plane { normal: Vec3::NEG_X, dist: -min.x },
            Plane { normal: Vec3::Y, dist: max.y },
            Plane { normal: Vec3::NEG_Y, dist: -min.y },
            Plane { normal: Vec3::Z, dist: max.z },
            Plane { normal: Vec3::NEG_Z, dist: -min.z },
        ];
        Self { planes, min, max, kind }
    }

    /// A ramp inside the box `min..max` that rises from `y = min.y` at the `low` edge to `max.y` at the
    /// opposite edge. `rise_dir` is the horizontal unit axis the ramp climbs along (+/-X or +/-Z).
    pub fn ramp(min: Vec3, max: Vec3, rise_dir: Vec3, kind: BrushKind) -> Self {
        let mut b = Self::cuboid(min, max, kind);
        let h = max.y - min.y;
        let run = if rise_dir.x.abs() > 0.5 { max.x - min.x } else { max.z - min.z };
        // Top surface: passes through the low edge at min.y and the high edge at max.y.
        let n = Vec3::new(-rise_dir.x * h, run, -rise_dir.z * h).normalize();
        let low_edge = Vec3::new(
            if rise_dir.x > 0.5 { min.x } else if rise_dir.x < -0.5 { max.x } else { min.x },
            min.y,
            if rise_dir.z > 0.5 { min.z } else if rise_dir.z < -0.5 { max.z } else { min.z },
        );
        // The +Y plane stays as an axial bevel: without it a box passing over the high edge would
        // collide early (the plane-offset trick needs bevels at edges between non-axial faces).
        b.planes.push(Plane { normal: n, dist: n.dot(low_edge) });
        b
    }

    pub fn blocks_players(&self) -> bool {
        matches!(self.kind, BrushKind::Solid | BrushKind::PlayerClip)
    }

    pub fn blocks_bullets(&self) -> bool {
        matches!(self.kind, BrushKind::Solid | BrushKind::BulletOnly)
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Trace {
    /// Fraction of the move completed, 0..=1.
    pub fraction: f32,
    pub end: Vec3,
    /// Surface normal of what was hit (zero if nothing).
    pub normal: Vec3,
    pub start_solid: bool,
}

impl Trace {
    pub fn hit(&self) -> bool {
        self.fraction < 1.0
    }
}

/// All static geometry of a map.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct CollisionWorld {
    pub brushes: Vec<Brush>,
}

impl CollisionWorld {
    pub fn push(&mut self, b: Brush) {
        self.brushes.push(b);
    }

    /// Sweep an axis-aligned box (`half` extents, centred on the moving point) from `start` to `end`.
    pub fn trace_box(&self, start: Vec3, end: Vec3, half: Vec3) -> Trace {
        self.trace_filtered(start, end, half, Brush::blocks_players)
    }

    /// Ray against bullet-blocking geometry: returns the hit distance along `dir` (unit), if any.
    pub fn raycast(&self, origin: Vec3, dir: Vec3, max_dist: f32) -> Option<(f32, Vec3)> {
        let t = self.trace_filtered(origin, origin + dir * max_dist, Vec3::ZERO, Brush::blocks_bullets);
        t.hit().then(|| (t.fraction * max_dist, t.normal))
    }

    /// True when nothing that stops bullets lies between `a` and `b`.
    pub fn line_of_sight(&self, a: Vec3, b: Vec3) -> bool {
        let t = self.trace_filtered(a, b, Vec3::ZERO, Brush::blocks_bullets);
        !t.hit() || t.fraction >= 0.999
    }

    fn trace_filtered(&self, start: Vec3, end: Vec3, half: Vec3, keep: impl Fn(&Brush) -> bool) -> Trace {
        let mut best = Trace { fraction: 1.0, end, normal: Vec3::ZERO, start_solid: false };
        let lo = start.min(end) - half - Vec3::splat(SKIN);
        let hi = start.max(end) + half + Vec3::splat(SKIN);
        for b in &self.brushes {
            if !keep(b) || b.max.cmplt(lo).any() || b.min.cmpgt(hi).any() {
                continue;
            }
            clip_to_brush(b, start, end, half, &mut best);
        }
        if best.fraction < 1.0 {
            best.end = start + (end - start) * best.fraction;
        }
        best
    }
}

/// Quake-style trace of a box against one convex brush (planes pushed out by the box extents).
fn clip_to_brush(b: &Brush, start: Vec3, end: Vec3, half: Vec3, best: &mut Trace) {
    let mut enter = -1.0_f32;
    let mut leave = 1.0_f32;
    let mut enter_normal = Vec3::ZERO;
    let mut starts_out = false;
    let mut ends_out = false;
    for p in &b.planes {
        // Distance the box reaches past its centre along this normal.
        let offset = half.dot(p.normal.abs());
        let dist = p.dist + offset;
        let d1 = start.dot(p.normal) - dist;
        let d2 = end.dot(p.normal) - dist;
        if d1 > 0.0 {
            starts_out = true;
        }
        if d2 > 0.0 {
            ends_out = true;
        }
        // Completely in front of a face: no hit with this brush.
        if d1 > 0.0 && (d2 >= SKIN || d2 >= d1) {
            return;
        }
        if d1 <= 0.0 && d2 <= 0.0 {
            continue;
        }
        if d1 > d2 {
            // Entering the brush.
            let f = (d1 - SKIN) / (d1 - d2);
            if f > enter {
                enter = f;
                enter_normal = p.normal;
            }
        } else {
            // Leaving.
            let f = (d1 + SKIN) / (d1 - d2);
            leave = leave.min(f);
        }
    }
    if !starts_out {
        // Started inside: report it so the mover can push out, but allow moves that get out.
        best.start_solid = true;
        if !ends_out {
            best.fraction = 0.0;
            best.normal = Vec3::ZERO;
        }
        return;
    }
    if enter < leave && enter > -1.0 && enter < best.fraction {
        best.fraction = enter.max(0.0);
        best.normal = enter_normal;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn floor_world() -> CollisionWorld {
        let mut w = CollisionWorld::default();
        w.push(Brush::cuboid(Vec3::new(-50.0, -1.0, -50.0), Vec3::new(50.0, 0.0, 50.0), BrushKind::Solid));
        w.push(Brush::cuboid(Vec3::new(2.0, 0.0, -5.0), Vec3::new(3.0, 3.0, 5.0), BrushKind::Solid));
        w
    }

    #[test]
    fn falls_onto_floor() {
        let w = floor_world();
        let half = Vec3::new(0.32, 0.9, 0.32);
        let t = w.trace_box(Vec3::new(0.0, 5.0, 0.0), Vec3::new(0.0, -5.0, 0.0), half);
        assert!(t.hit());
        assert!((t.end.y - 0.9).abs() < 0.01, "{:?}", t.end);
        assert_eq!(t.normal, Vec3::Y);
    }

    #[test]
    fn stops_at_wall() {
        let w = floor_world();
        let half = Vec3::new(0.32, 0.9, 0.32);
        let t = w.trace_box(Vec3::new(0.0, 1.0, 0.0), Vec3::new(5.0, 1.0, 0.0), half);
        assert!(t.hit());
        assert!((t.end.x - (2.0 - 0.32)).abs() < 0.01, "{:?}", t.end);
        assert_eq!(t.normal, Vec3::NEG_X);
    }

    #[test]
    fn misses_when_clear() {
        let w = floor_world();
        let t = w.trace_box(Vec3::new(0.0, 1.0, 0.0), Vec3::new(0.0, 1.0, -10.0), Vec3::new(0.3, 0.9, 0.3));
        assert!(!t.hit());
    }

    #[test]
    fn ramp_surface_height() {
        let mut w = CollisionWorld::default();
        // rises 2 m over 6 m toward -Z
        w.push(Brush::ramp(Vec3::new(-5.0, 0.0, -6.0), Vec3::new(5.0, 2.0, 0.0), Vec3::NEG_Z, BrushKind::Solid));
        let t = w.trace_box(Vec3::new(0.0, 5.0, -3.0), Vec3::new(0.0, -1.0, -3.0), Vec3::ZERO);
        assert!((t.end.y - 1.0).abs() < 0.01, "{:?}", t.end);
        assert!(t.normal.y > 0.9 && t.normal.z < 0.0);
    }

    #[test]
    fn raycast_and_los() {
        let w = floor_world();
        let (d, n) = w.raycast(Vec3::new(0.0, 1.0, 0.0), Vec3::X, 100.0).unwrap();
        assert!((d - 2.0).abs() < 0.01);
        assert_eq!(n, Vec3::NEG_X);
        assert!(!w.line_of_sight(Vec3::new(0.0, 1.0, 0.0), Vec3::new(10.0, 1.0, 0.0)));
        assert!(w.line_of_sight(Vec3::new(0.0, 4.0, 0.0), Vec3::new(10.0, 4.0, 0.0)));
    }

    #[test]
    fn player_clip_does_not_stop_bullets() {
        let mut w = CollisionWorld::default();
        w.push(Brush::cuboid(Vec3::new(1.0, 0.0, -1.0), Vec3::new(2.0, 3.0, 1.0), BrushKind::PlayerClip));
        assert!(w.raycast(Vec3::new(0.0, 1.0, 0.0), Vec3::X, 10.0).is_none());
        assert!(w.trace_box(Vec3::new(0.0, 1.0, 0.0), Vec3::new(5.0, 1.0, 0.0), Vec3::splat(0.3)).hit());
    }
}
