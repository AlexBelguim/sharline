//! Playable levels built from the design layouts in `design/maps/`.
//!
//! The layouts use the Blender / design frame: x = east, y = north, z = up, in metres. Levels live in Bevy's
//! frame (+Y up, north = -Z), so the builders here work in design numbers and convert once:
//! `bevy = (x, z, -y)`. A design plan rect `(x0, y0, x1, y1)` with heights `z0..z1` becomes the Bevy box
//! `(x0, z0, -y1)..(x1, z1, -y0)`.

pub mod range;
pub mod showhome;

pub use range::{RangeTarget, RangeTargetKind, range, range_targets};
pub use showhome::showhome;

use crate::level::Level;
use crate::movement::collision::{Brush, BrushKind, CollisionWorld, Look};
use glam::Vec3;

/// Builds a level by name: "showhome" or "range" (any case).
pub fn by_name(name: &str) -> Option<Level> {
    match name.trim().to_ascii_lowercase().as_str() {
        "showhome" => Some(showhome()),
        "range" => Some(range()),
        _ => None,
    }
}

/// Lengths below this (metres) are treated as zero when cutting walls and floors.
const EPS: f32 = 1e-4;

/// A design-frame point in Bevy coordinates.
pub(crate) fn design(x: f32, y: f32, z: f32) -> Vec3 {
    Vec3::new(x, z, -y)
}

/// Design yaw (degrees, 0 = facing east, counter-clockwise seen from above) to the sim's yaw (radians,
/// 0 = facing north / -Z, increasing to the left). Both turn the same way, so it is a 90 degree shift.
pub(crate) fn design_yaw(deg: f32) -> f32 {
    (deg - 90.0).to_radians()
}

/// Plan rectangle in the design frame, `x0 < x1`, `y0 < y1`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) struct Rect {
    pub x0: f32,
    pub y0: f32,
    pub x1: f32,
    pub y1: f32,
}

impl Rect {
    pub const fn new(x0: f32, y0: f32, x1: f32, y1: f32) -> Self {
        Self { x0, y0, x1, y1 }
    }

    pub fn is_empty(&self) -> bool {
        self.x1 - self.x0 < EPS || self.y1 - self.y0 < EPS
    }

    /// True when the interiors overlap (touching edges do not count).
    pub fn overlaps(&self, o: &Rect) -> bool {
        self.x0 < o.x1 - EPS && o.x0 < self.x1 - EPS && self.y0 < o.y1 - EPS && o.y0 < self.y1 - EPS
    }

    pub fn grow(&self, d: f32) -> Rect {
        Rect::new(self.x0 - d, self.y0 - d, self.x1 + d, self.y1 + d)
    }

    /// Mirror image across the vertical line `x = axis`.
    pub fn mirror_x(&self, axis: f32) -> Rect {
        Rect::new(2.0 * axis - self.x1, self.y0, 2.0 * axis - self.x0, self.y1)
    }

    /// The parts of `self` outside `hole`: full-depth strips west and east of it, then the pieces south and
    /// north of it within its x range. The split is mirror-symmetric, so mirrored inputs give mirrored pieces.
    pub fn subtract(&self, hole: &Rect) -> Vec<Rect> {
        if !self.overlaps(hole) {
            return vec![*self];
        }
        let (cx0, cx1) = (self.x0.max(hole.x0), self.x1.min(hole.x1));
        [
            Rect::new(self.x0, self.y0, hole.x0, self.y1),
            Rect::new(hole.x1, self.y0, self.x1, self.y1),
            Rect::new(cx0, self.y0, cx1, hole.y0),
            Rect::new(cx0, hole.y1, cx1, self.y1),
        ]
        .into_iter()
        .filter(|r| !r.is_empty())
        .collect()
    }

    /// Bevy-space min/max corners of this rect extruded over design heights `z0..z1`.
    pub fn bevy_box(&self, z0: f32, z1: f32) -> (Vec3, Vec3) {
        (Vec3::new(self.x0, z0, -self.y1), Vec3::new(self.x1, z1, -self.y0))
    }
}

/// Design-frame compass direction (for ramps: the way the top surface rises).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Dir {
    North,
    South,
    East,
    West,
}

impl Dir {
    pub fn bevy(self) -> Vec3 {
        match self {
            Dir::North => Vec3::NEG_Z,
            Dir::South => Vec3::Z,
            Dir::East => Vec3::X,
            Dir::West => Vec3::NEG_X,
        }
    }

    pub fn mirror_x(self) -> Dir {
        match self {
            Dir::East => Dir::West,
            Dir::West => Dir::East,
            d => d,
        }
    }
}

/// The centre line a wall or opening sits on.
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) enum Line {
    /// Constant `x = c`; the wall runs north-south and `a` measures y (layout `wall='x'`).
    X(f32),
    /// Constant `y = c`; the wall runs east-west and `a` measures x (layout `wall='y'`).
    Y(f32),
}

impl Line {
    fn same(self, o: Line) -> bool {
        match (self, o) {
            (Line::X(a), Line::X(b)) | (Line::Y(a), Line::Y(b)) => (a - b).abs() < 1e-3,
            _ => false,
        }
    }

    /// Footprint of the wall piece from `a0` to `a1` along this line, `t` thick (centred on the line).
    fn rect(self, a0: f32, a1: f32, t: f32) -> Rect {
        match self {
            Line::X(c) => Rect::new(c - t / 2.0, a0, c + t / 2.0, a1),
            Line::Y(c) => Rect::new(a0, c - t / 2.0, a1, c + t / 2.0),
        }
    }
}

/// A straight wall of thickness `t` centred on `line`, from `a0` to `a1` along it, heights `z0..z1`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) struct WallDef {
    pub line: Line,
    pub a0: f32,
    pub a1: f32,
    pub z0: f32,
    pub z1: f32,
    pub t: f32,
    pub look: Look,
}

impl WallDef {
    /// Wall along the axis-aligned segment `(x0, y0)-(x1, y1)` (the layout's `Wall` record).
    pub fn seg(x0: f32, y0: f32, x1: f32, y1: f32, z0: f32, z1: f32, t: f32) -> Self {
        let (line, a0, a1) = if (x0 - x1).abs() < EPS {
            (Line::X(x0), y0.min(y1), y0.max(y1))
        } else {
            (Line::Y(y0), x0.min(x1), x0.max(x1))
        };
        Self { line, a0, a1, z0, z1, t, look: Look::Wall }
    }

    pub fn look(mut self, look: Look) -> Self {
        self.look = look;
        self
    }

    pub fn mirror_x(self, axis: f32) -> Self {
        let mut w = self;
        match self.line {
            Line::X(c) => w.line = Line::X(2.0 * axis - c),
            Line::Y(_) => (w.a0, w.a1) = (2.0 * axis - self.a1, 2.0 * axis - self.a0),
        }
        w
    }
}

/// The four walls around a building footprint (centred on its edges), all `z0..z1`.
pub(crate) fn box_walls(r: Rect, z0: f32, z1: f32, t: f32, look: Look) -> [WallDef; 4] {
    [
        WallDef::seg(r.x0, r.y0, r.x1, r.y0, z0, z1, t).look(look),
        WallDef::seg(r.x0, r.y1, r.x1, r.y1, z0, z1, t).look(look),
        WallDef::seg(r.x0, r.y0, r.x0, r.y1, z0, z1, t).look(look),
        WallDef::seg(r.x1, r.y0, r.x1, r.y1, z0, z1, t).look(look),
    ]
}

/// A door / window / shutter: removes `a0..a1` x `z0..z1` (sill to head) from any wall on the same line.
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) struct Opening {
    pub line: Line,
    pub a0: f32,
    pub a1: f32,
    pub z0: f32,
    pub z1: f32,
}

impl Opening {
    /// Opening in a wall on `x = c`, spanning y `a0..a1`.
    pub fn x(c: f32, a0: f32, a1: f32, z0: f32, z1: f32) -> Self {
        Self { line: Line::X(c), a0, a1, z0, z1 }
    }

    /// Opening in a wall on `y = c`, spanning x `a0..a1`.
    pub fn y(c: f32, a0: f32, a1: f32, z0: f32, z1: f32) -> Self {
        Self { line: Line::Y(c), a0, a1, z0, z1 }
    }

    pub fn mirror_x(self, axis: f32) -> Self {
        let mut o = self;
        match self.line {
            Line::X(c) => o.line = Line::X(2.0 * axis - c),
            Line::Y(_) => (o.a0, o.a1) = (2.0 * axis - self.a1, 2.0 * axis - self.a0),
        }
        o
    }
}

/// Collects brushes in design coordinates.
#[derive(Debug, Default)]
pub(crate) struct Builder {
    world: CollisionWorld,
}

impl Builder {
    pub fn add(&mut self, r: Rect, z0: f32, z1: f32, kind: BrushKind, look: Look) {
        if r.is_empty() || z1 - z0 < EPS {
            return;
        }
        let (min, max) = r.bevy_box(z0, z1);
        self.world.push(Brush::cuboid(min, max, kind).with_look(look));
    }

    pub fn solid(&mut self, r: Rect, z0: f32, z1: f32, look: Look) {
        self.add(r, z0, z1, BrushKind::Solid, look);
    }

    /// Invisible, players only (map bounds, ceilings).
    pub fn clip(&mut self, r: Rect, z0: f32, z1: f32) {
        self.add(r, z0, z1, BrushKind::PlayerClip, Look::Invisible);
    }

    /// Wedge over `r` rising from `z0` at one edge to `z1` at the edge toward `rise`.
    pub fn ramp(&mut self, r: Rect, z0: f32, z1: f32, rise: Dir, kind: BrushKind, look: Look) {
        let (min, max) = r.bevy_box(z0, z1);
        self.world.push(Brush::ramp(min, max, rise.bevy(), kind).with_look(look));
    }

    /// A wall with every matching opening cut out: full-height pieces between openings, a sill below and a
    /// lintel above each one. The ends are extended by `t / 2` so walls meeting at a corner close it.
    pub fn wall(&mut self, w: &WallDef, openings: &[Opening]) {
        let (a0, a1) = (w.a0 - w.t / 2.0, w.a1 + w.t / 2.0);
        let mut holes: Vec<Opening> = openings
            .iter()
            .filter(|o| o.line.same(w.line) && o.a0 < w.a1 && o.a1 > w.a0 && o.z0 < w.z1 && o.z1 > w.z0)
            .map(|o| Opening {
                line: o.line,
                a0: o.a0.max(a0),
                a1: o.a1.min(a1),
                z0: o.z0.max(w.z0),
                z1: o.z1.min(w.z1),
            })
            .collect();
        holes.sort_by(|p, q| p.a0.total_cmp(&q.a0));
        let mut at = a0;
        for h in holes {
            self.solid(w.line.rect(at, h.a0, w.t), w.z0, w.z1, w.look);
            self.solid(w.line.rect(h.a0, h.a1, w.t), w.z0, h.z0, w.look);
            self.solid(w.line.rect(h.a0, h.a1, w.t), h.z1, w.z1, w.look);
            at = at.max(h.a1);
        }
        self.solid(w.line.rect(at, a1, w.t), w.z0, w.z1, w.look);
    }

    pub fn finish(self) -> CollisionWorld {
        self.world
    }
}

/// The ground as flush slab pieces. Each patch (spawn-zone tint, room floor) cuts its footprint out of what is
/// already there, so the walkable surface stays one flat plane with no lips and no overlapping faces.
#[derive(Debug, Clone)]
pub(crate) struct FloorPlan {
    pieces: Vec<(Rect, Look)>,
}

impl FloorPlan {
    pub fn new(r: Rect, look: Look) -> Self {
        Self { pieces: vec![(r, look)] }
    }

    pub fn patch(&mut self, r: Rect, look: Look) {
        self.cut(r);
        self.pieces.push((r, look));
    }

    /// Removes `hole` from the ground (pits).
    pub fn cut(&mut self, hole: Rect) {
        self.pieces =
            self.pieces.iter().flat_map(|&(p, l)| p.subtract(&hole).into_iter().map(move |q| (q, l))).collect();
    }

    pub fn pieces(&self) -> &[(Rect, Look)] {
        &self.pieces
    }
}

#[cfg(test)]
pub(crate) mod test_util {
    use crate::data::GameData;
    use crate::input::{Buttons, InputFrame};
    use crate::level::Level;
    use crate::movement::collision::SKIN;
    use crate::movement::{MoveMode, MoveModifiers, MoveState, Stance, step};
    use glam::{Vec2, Vec3};

    /// Standing player box (capsule radius 0.32, height 1.8).
    pub const HALF: Vec3 = Vec3::new(0.32, 0.9, 0.32);

    /// Every spawn stands on walkable ground (a box dropped from 1 m above lands at the spawn height) and does
    /// not start inside anything.
    pub fn assert_spawns_grounded(level: &Level) {
        assert!(!level.spawns.is_empty());
        for s in &level.spawns {
            let c = s.pos + Vec3::Y * HALF.y;
            let t = level.world.trace_box(c + Vec3::Y, c - Vec3::Y * 2.0, HALF);
            assert!(t.hit() && !t.start_solid, "spawn {:?}: no ground below ({t:?})", s.pos);
            let feet = t.end.y - HALF.y;
            assert!((feet - s.pos.y).abs() < 0.1, "spawn {:?}: ground at {feet}", s.pos);
            assert!(t.normal.y > 0.9, "spawn {:?}: ground not flat ({:?})", s.pos, t.normal);
            let c = c + Vec3::Y * 0.01;
            let t = level.world.trace_box(c, c + Vec3::Y * 0.05, HALF);
            assert!(!t.start_solid, "spawn {:?} starts inside a brush", s.pos);
        }
    }

    /// Height of the first surface below `from` (a point trace straight down).
    pub fn surface_below(level: &Level, from: Vec3) -> f32 {
        let t = level.world.trace_box(from, from - Vec3::Y * 50.0, Vec3::ZERO);
        assert!(t.hit() && !t.start_solid, "nothing below {from:?}");
        t.end.y
    }

    /// Runs the real character controller holding forward at `yaw` for `secs`; returns the final feet position.
    pub fn walk(level: &Level, from: Vec3, yaw: f32, secs: f32) -> Vec3 {
        let data = GameData::embedded();
        let mods = MoveModifiers::unarmored(&data);
        let mut st = MoveState::spawn(from, data.movement.jetpack.fuel_s);
        let input = InputFrame { movement: Vec2::Y, yaw, pitch: 0.0, buttons: Buttons(0), ..Default::default() };
        let dt = 1.0 / 60.0;
        for _ in 0..(secs / dt).round() as usize {
            step(&data, level, &mut st, &input, &mods, dt);
        }
        st.pos
    }

    /// Runs the real character controller from `st` for `secs` at 60 Hz, with `buttons(tick)` held and
    /// `movement` at `yaw`; returns the state after every tick.
    pub fn run(
        level: &Level,
        mut st: MoveState,
        movement: Vec2,
        yaw: f32,
        buttons: impl Fn(usize) -> u16,
        secs: f32,
    ) -> Vec<MoveState> {
        let data = GameData::embedded();
        let mods = MoveModifiers::unarmored(&data);
        let dt = 1.0 / 60.0;
        (0..(secs / dt).round() as usize)
            .map(|i| {
                let input =
                    InputFrame { movement, yaw, pitch: 0.0, buttons: Buttons(buttons(i)), ..Default::default() };
                step(&data, level, &mut st, &input, &mods, dt);
                st
            })
            .collect()
    }

    /// True when the player's box (for its stance) is inside something that blocks players.
    pub fn inside_solid(level: &Level, st: &MoveState) -> bool {
        let c = GameData::embedded().movement.capsule;
        let h = match st.stance {
            Stance::Stand => c.height_stand,
            Stance::Crouch => c.height_crouch,
            Stance::Slide => c.height_slide,
        };
        let half = Vec3::new(c.radius, h * 0.5, c.radius);
        !level.world.box_free(st.pos + Vec3::Y * (half.y + SKIN), half)
    }

    /// Grab the map's zipline from `from` (feet, in `mode`) facing `yaw` and ride it with no input for `secs`,
    /// pressing jump on tick `jump_at` if given. Asserts the grab works, the ride ends, and the player is never
    /// inside anything; returns the state after every tick and the tick the ride ended on.
    pub fn ride_zipline(
        level: &Level,
        from: Vec3,
        mode: MoveMode,
        yaw: f32,
        jump_at: Option<usize>,
        secs: f32,
    ) -> (Vec<MoveState>, usize) {
        let data = GameData::embedded();
        let mut st = MoveState::spawn(from, data.movement.jetpack.fuel_s);
        st.mode = mode;
        let buttons = |i: usize| match i {
            0 => Buttons::INTERACT,
            i if Some(i) == jump_at => Buttons::JUMP,
            _ => 0,
        };
        let ticks = run(level, st, Vec2::ZERO, yaw, buttons, secs);
        assert_eq!(ticks[0].mode, MoveMode::Zipline, "grab the line from {from}");
        let off = ticks.iter().position(|s| s.mode != MoveMode::Zipline).expect("the ride ends");
        for (i, s) in ticks.iter().enumerate() {
            assert!(!inside_solid(level, s), "tick {i} (ride ended on {off}): inside something at {}", s.pos);
        }
        (ticks, off)
    }

    /// From `st`, walking forward at `yaw` for a second moves the player at least 2 m, never inside anything.
    pub fn assert_walks_away(level: &Level, st: MoveState, yaw: f32) {
        let ticks = run(level, st, Vec2::Y, yaw, |_| 0, 1.0);
        assert!(ticks.iter().all(|s| !inside_solid(level, s)), "walked into something from {}", st.pos);
        let end = ticks.last().unwrap().pos;
        let moved = Vec2::new(end.x - st.pos.x, end.z - st.pos.z).length();
        assert!(moved > 2.0, "stuck at {}: moved {moved} m", st.pos);
    }

    /// Jump on tick 0, let go, then light the jetpack on tick 8 and hold it (the fuel runs out by itself).
    pub fn jump_then_jet(tick: usize) -> u16 {
        if tick == 0 || tick >= 8 { Buttons::JUMP } else { 0 }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn by_name_is_case_insensitive() {
        assert_eq!(by_name("Showhome").map(|l| l.name), Some("Showhome".to_string()));
        assert_eq!(by_name("RANGE").map(|l| l.name), Some("Range".to_string()));
        assert!(by_name("dust").is_none());
    }

    #[test]
    fn subtract_leaves_a_ring() {
        let big = Rect::new(0.0, 0.0, 10.0, 10.0);
        let pieces = big.subtract(&Rect::new(4.0, 4.0, 6.0, 6.0));
        assert_eq!(pieces.len(), 4);
        let area: f32 = pieces.iter().map(|r| (r.x1 - r.x0) * (r.y1 - r.y0)).sum();
        assert!((area - 96.0).abs() < 1e-3);
        assert!(pieces.iter().all(|p| !p.overlaps(&Rect::new(4.0, 4.0, 6.0, 6.0))));
        assert_eq!(big.subtract(&Rect::new(20.0, 0.0, 30.0, 10.0)), vec![big]);
    }

    #[test]
    fn wall_openings_leave_sill_and_lintel() {
        let mut b = Builder::default();
        let w = WallDef::seg(0.0, 0.0, 10.0, 0.0, 0.0, 3.0, 0.2);
        b.wall(&w, &[Opening::y(0.0, 2.0, 3.0, 0.0, 2.1), Opening::y(0.0, 5.0, 6.0, 0.9, 2.1)]);
        let world = b.finish();
        // 3 full pieces + door lintel + window sill and lintel
        assert_eq!(world.brushes.len(), 6);
        let half = Vec3::new(0.3, 0.9, 0.3);
        // through the door (x 2..3 at design y 0, Bevy z 0)
        assert!(
            !world.trace_box(Vec3::new(2.5, 0.95, 1.0), Vec3::new(2.5, 0.95, -1.0), Vec3::new(0.2, 0.9, 0.2)).hit()
        );
        // the window needs a vault: blocked at standing height, open at chest height for a ray
        assert!(world.trace_box(Vec3::new(5.5, 0.95, 1.0), Vec3::new(5.5, 0.95, -1.0), half).hit());
        assert!(world.line_of_sight(Vec3::new(5.5, 1.5, 1.0), Vec3::new(5.5, 1.5, -1.0)));
        assert!(!world.line_of_sight(Vec3::new(8.0, 1.5, 1.0), Vec3::new(8.0, 1.5, -1.0)));
    }

    #[test]
    fn design_frame_conversion() {
        assert_eq!(design(1.0, 2.0, 3.0), Vec3::new(1.0, 3.0, -2.0));
        let (min, max) = Rect::new(1.0, 2.0, 3.0, 5.0).bevy_box(0.0, 4.0);
        assert_eq!((min, max), (Vec3::new(1.0, 0.0, -5.0), Vec3::new(3.0, 4.0, -2.0)));
        // design yaw 0 faces east: forward = (-sin, 0, -cos) must be +X
        let y = design_yaw(0.0);
        assert!((Vec3::new(-y.sin(), 0.0, -y.cos()) - Vec3::X).length() < 1e-5);
        let y = design_yaw(90.0);
        assert!((Vec3::new(-y.sin(), 0.0, -y.cos()) - Vec3::NEG_Z).length() < 1e-5);
    }
}
