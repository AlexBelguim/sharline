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
    /// Blocks movement/bullets but its surface cannot become standing ground.
    /// Authored v3 roofs use this without replacing their exact convex planes.
    SolidNonWalkable,
    /// Blocks players only (invisible map bounds, ceilings).
    PlayerClip,
    /// Blocks bullets and sight only (glass would go here).
    BulletOnly,
}

/// How a brush is drawn (the simulation ignores it).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub enum Look {
    #[default]
    Ground,
    Floor,
    Wall,
    Roof,
    Trim,
    Prop,
    Hedge,
    Fence,
    Glass,
    Vehicle,
    Metal,
    Concrete,
    Water,
    TeamA,
    TeamB,
    Accent,
    Target,
    /// Street and car-park surface.
    Asphalt,
    /// Pavements, front paths, patios.
    Paving,
    Gravel,
    /// Fibre-cement cladding in the west (Sage) and east (Clay) house colours.
    CladSage,
    CladClay,
    /// Not drawn (player clips, invisible bounds).
    Invisible,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Brush {
    pub planes: Vec<Plane>,
    pub min: Vec3,
    pub max: Vec3,
    pub kind: BrushKind,
    pub look: Look,
    /// For ramps: the horizontal direction the top surface rises toward.
    pub ramp: Option<Vec3>,
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
        let look = if kind == BrushKind::PlayerClip { Look::Invisible } else { Look::default() };
        Self { planes, min, max, kind, look, ramp: None }
    }

    pub fn with_look(mut self, look: Look) -> Self {
        self.look = look;
        self
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
            if rise_dir.x > 0.5 {
                min.x
            } else if rise_dir.x < -0.5 {
                max.x
            } else {
                min.x
            },
            min.y,
            if rise_dir.z > 0.5 {
                min.z
            } else if rise_dir.z < -0.5 {
                max.z
            } else {
                min.z
            },
        );
        // The +Y plane stays as an axial bevel: without it a box passing over the high edge would
        // collide early (the plane-offset trick needs bevels at edges between non-axial faces).
        b.planes.push(Plane { normal: n, dist: n.dot(low_edge) });
        b.ramp = Some(rise_dir);
        b
    }

    pub fn blocks_players(&self) -> bool {
        matches!(self.kind, BrushKind::Solid | BrushKind::SolidNonWalkable | BrushKind::PlayerClip)
    }

    pub fn blocks_bullets(&self) -> bool {
        matches!(self.kind, BrushKind::Solid | BrushKind::SolidNonWalkable | BrushKind::BulletOnly)
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
    /// Whether the authored hit surface may be used as standing ground.
    pub walkable: bool,
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
        t.hit().then_some((t.fraction * max_dist, t.normal))
    }

    /// Sweep a box against everything that stops players or bullets (a thrown grenade: it bounces off walls,
    /// glass and the map's invisible bounds alike).
    pub fn trace_solid(&self, start: Vec3, end: Vec3, half: Vec3) -> Trace {
        self.trace_filtered(start, end, half, |b| b.blocks_players() || b.blocks_bullets())
    }

    /// True when nothing that stops bullets lies between `a` and `b`.
    pub fn line_of_sight(&self, a: Vec3, b: Vec3) -> bool {
        let t = self.trace_filtered(a, b, Vec3::ZERO, Brush::blocks_bullets);
        !t.hit() || t.fraction >= 0.999
    }

    /// True when a box (`half` extents) centred at `c` is not inside anything that blocks players.
    pub fn box_free(&self, c: Vec3, half: Vec3) -> bool {
        !self.trace_box(c, c, half).start_solid
    }

    /// The shortest move that gets a box (`half` extents, centred at `c`) out of the player-blocking brushes it
    /// is inside, if any is found: out through one face of a brush, or of two in turn (a box wedged between a
    /// floor and a lintel). A move may rise or drop at most `max_y`, so a box is never pushed up through what is
    /// above it (only out of a floor or a step it sank into) or down through the floor, and goes no further than
    /// twice the box's own half-diagonal (out of a wall, not through a building). `None` when it is free already
    /// or no such move works.
    pub fn push_out(&self, c: Vec3, half: Vec3, max_y: f32) -> Option<Vec3> {
        if self.box_free(c, half) {
            return None;
        }
        let reach = half.length() * 2.0;
        let shorter = |push: Vec3, best: Option<Vec3>| {
            push.y.abs() <= max_y
                && push.length() <= reach
                && best.is_none_or(|b: Vec3| push.length_squared() < b.length_squared())
        };
        let mut best: Option<Vec3> = None;
        let mut wedged = Vec::new();
        for p in self.face_pushes(c, half) {
            if !shorter(p, best) {
                continue;
            }
            if self.box_free(c + p, half) {
                best = Some(p);
            } else {
                wedged.push(p);
            }
        }
        for p in wedged {
            for q in self.face_pushes(c + p, half) {
                if shorter(p + q, best) && self.box_free(c + p + q, half) {
                    best = Some(p + q);
                }
            }
        }
        best
    }

    /// For every player-blocking brush the box is inside: the move out through each of its faces (just past it).
    fn face_pushes(&self, c: Vec3, half: Vec3) -> Vec<Vec3> {
        let mut out = Vec::new();
        let (lo, hi) = (c - half, c + half);
        for b in &self.brushes {
            if !b.blocks_players() || b.max.cmplt(lo).any() || b.min.cmpgt(hi).any() {
                continue;
            }
            // The same expanded planes as the trace: inside means behind (or on) every one of them.
            let depth: Vec<f32> =
                b.planes.iter().map(|p| c.dot(p.normal) - (p.dist + half.dot(p.normal.abs()))).collect();
            if depth.iter().any(|d| *d > 0.0) {
                continue;
            }
            out.extend(b.planes.iter().zip(&depth).map(|(p, d)| p.normal * (-d + SKIN * 2.0)));
        }
        out
    }

    fn trace_filtered(&self, start: Vec3, end: Vec3, half: Vec3, keep: impl Fn(&Brush) -> bool) -> Trace {
        let mut best = Trace { fraction: 1.0, end, normal: Vec3::ZERO, start_solid: false, walkable: true };
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
        best.walkable = b.kind != BrushKind::SolidNonWalkable;
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
        assert!(t.normal.y > 0.9 && t.normal.z > 0.0, "slope faces the low (+Z) side");
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

    /// Out of a floor it sank into: up. Wedged between a floor and a lintel: out sideways, the nearer way, never
    /// up through the lintel. Free already: no move.
    #[test]
    fn push_out_takes_the_shortest_way_but_never_up_through_a_ceiling() {
        let mut w = floor_world();
        let half = Vec3::new(0.32, 0.625, 0.32);
        assert_eq!(w.push_out(Vec3::new(0.0, 0.7, 0.0), half, 0.3), None, "free");
        let sunk = w.push_out(Vec3::new(0.0, 0.6, 0.0), half, 0.3).unwrap();
        assert!(sunk.x == 0.0 && sunk.z == 0.0 && (sunk.y - 0.025).abs() < 0.01, "{sunk}");
        // A thin lintel, 1.1..1.3 m, its south face at z 0.2: the head (1.25 m) is in it.
        w.push(Brush::cuboid(Vec3::new(-5.0, 1.1, -0.5), Vec3::new(1.5, 1.3, 0.2), BrushKind::Solid));
        let c = Vec3::new(0.0, 0.625 + SKIN, 0.0);
        let out = w.push_out(c, half, 0.3).unwrap();
        assert!(out.y <= 0.0 && (out.z - (0.2 + 0.32)).abs() < 0.01 && out.x == 0.0, "{out}");
        assert!(w.box_free(c + out, half));
        // Nothing within reach but up through it: no move at all.
        assert_eq!(w.push_out(c, half, 0.3).map(|p| p.y > 0.3), Some(false));
        let mut boxed = CollisionWorld::default();
        boxed.push(Brush::cuboid(Vec3::new(-50.0, 1.1, -50.0), Vec3::new(50.0, 1.3, 50.0), BrushKind::Solid));
        boxed.push(Brush::cuboid(Vec3::new(-50.0, -1.0, -50.0), Vec3::new(50.0, 0.0, 50.0), BrushKind::Solid));
        assert_eq!(boxed.push_out(c, half, 0.3), None, "only through the slab, the floor or far away");
    }

    #[test]
    fn player_clip_does_not_stop_bullets() {
        let mut w = CollisionWorld::default();
        w.push(Brush::cuboid(Vec3::new(1.0, 0.0, -1.0), Vec3::new(2.0, 3.0, 1.0), BrushKind::PlayerClip));
        assert!(w.raycast(Vec3::new(0.0, 1.0, 0.0), Vec3::X, 10.0).is_none());
        assert!(w.trace_box(Vec3::new(0.0, 1.0, 0.0), Vec3::new(5.0, 1.0, 0.0), Vec3::splat(0.3)).hit());
    }
}
