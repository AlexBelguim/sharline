//! "The Yard": the HQ training range, ported from `design/maps/range/diagrams/layout_data.py`.
//!
//! Design frame: origin = centre of the firing line at floor level, x = east, y = north (downrange), z = up.
//! The blockout has the Ready Room (spawns), the covered Range Deck with eight firing bays and the Recoil Lab,
//! the 300 m field between earth berms, the Aim Lab hall and the movement course. Targets are not collision:
//! the game spawns them from [`range_targets`]. Heights the layout does not give (doors, walls, rack and board
//! sizes) are blockout assumptions and are named as such below.

use super::{Builder, Dir, FloorPlan, Opening, Rect, WallDef, box_walls, design, design_yaw};
use crate::level::{Level, SpawnPoint, Zipline};
use crate::movement::collision::{BrushKind, Look as L};
use glam::Vec3;
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------- site
const SITE: Rect = Rect::new(-80.0, -60.0, 105.0, 325.0);
/// Ground slab bottom (deep enough to hold the course pit).
const GROUND_BOTTOM: f32 = -3.5;
const KILL_Y: f32 = -10.0;
/// Invisible site wall height.
const BOUNDS_TOP: f32 = 50.0;
/// Blockout assumptions (not in the layout): exterior wall thickness, door head height, roof slab thickness.
const WALL_T: f32 = 0.4;
const DOOR_H: f32 = 3.0;
const ROOF_T: f32 = 0.3;

// ---------------------------------------------------------------- 1. Ready Room
const READY_ROOM: Rect = Rect::new(-18.0, -40.0, 18.0, -10.0);
const READY_ROOM_HEIGHT: f32 = 6.0;
const SPAWN_STRIP: Rect = Rect::new(-15.0, -38.5, 15.0, -35.5);
const SPAWN_Y: f32 = -37.0;
/// Ops Table: centre x, y, radius; table top 1.0 m.
const OPS_TABLE: (f32, f32, f32) = (0.0, -27.0, 2.5);
const TEAM_PADS: [(Rect, L); 2] =
    [(Rect::new(-8.0, -22.0, -3.0, -17.0), L::TeamA), (Rect::new(3.0, -22.0, 8.0, -17.0), L::TeamB)];
const WEAPON_WALL: Rect = Rect::new(-18.0, -36.0, -17.4, -22.0);
const HALO_WALL: Rect = Rect::new(17.4, -36.0, 18.0, -22.0);
/// Display rack height (assumption).
const RACK_H: f32 = 3.0;
const LOADOUT_BENCHES: [Rect; 2] = [Rect::new(-14.0, -34.0, -12.8, -28.0), Rect::new(-14.0, -27.0, -12.8, -21.0)];
const BENCH_H: f32 = 0.95;
/// Mannequin plinths (Light / Medium / Heavy): r 0.6, h 0.4.
const MANNEQUINS: [(f32, f32); 3] = [(15.6, -33.0), (15.6, -28.5), (15.6, -24.0)];
const FITTING_PAD: Rect = Rect::new(9.0, -31.0, 12.0, -28.0);
/// Hall record boards on the north wall; z 2.0..4.0 is an assumption.
const HALL_BOARDS: [Rect; 2] = [Rect::new(-15.0, -10.4, -6.0, -10.1), Rect::new(6.0, -10.4, 15.0, -10.1)];

// ---------------------------------------------------------------- 2. Range Deck + Recoil Lab
const DECK: Rect = Rect::new(-20.0, -10.0, 30.0, 0.0);
/// Roof to y +2 (2 m overhang past the line), underside 4.0 m.
const DECK_ROOF: Rect = Rect::new(-20.0, -10.0, 30.0, 2.0);
const DECK_ROOF_Z: f32 = 4.0;
const BAY_COUNT: usize = 8;
const BAY_WIDTH: f32 = 3.5;
const BAY_X0: f32 = -14.0;
/// Bay partitions: 0.2 thick, y -4..0, h 2.2.
const PARTITION: (f32, f32, f32, f32) = (0.2, -4.0, 0.0, 2.2);
/// Firing bench relative to the bay centre (x0, y0, x1, y1), h 0.95.
const FIRING_BENCH: Rect = Rect::new(-1.2, -0.8, 1.2, 0.0);
/// Lane readout: x relative to the bay centre, absolute y; 1.2 x 0.3 m, top 0.45 m.
const LANE_READOUT: (f32, f32) = (1.2, 5.0);
const LANE_READOUT_TOP: f32 = 0.45;
/// Shared damage board on the deck's west end wall, z 1.5..4.5 (clipped to the roof underside).
const RANGE_BOARD: Rect = Rect::new(-20.0, -9.0, -19.7, -1.0);
const RECOIL_LAB: Rect = Rect::new(22.0, 0.0, 30.0, 29.0);
const RECOIL_BAY_CENTRES: [f32; 2] = [24.0, 28.0];
const RECOIL_WALLS: [Rect; 4] = [
    Rect::new(22.0, -4.0, 22.3, 29.0),
    Rect::new(25.9, 0.0, 26.1, 28.0),
    Rect::new(29.7, -4.0, 30.0, 29.0),
    Rect::new(22.0, 28.0, 30.0, 29.0),
];
const RECOIL_WALL_H: f32 = 4.0;

// ---------------------------------------------------------------- 3. Range field
const BERM_W: Rect = Rect::new(-22.0, 0.0, -16.0, 305.0);
const BERM_E: Rect = Rect::new(16.0, 0.0, 22.0, 305.0);
const BERM_HEIGHT: f32 = 4.0;
const BACKSTOP: Rect = Rect::new(-22.0, 305.0, 22.0, 320.0);
const BACKSTOP_HEIGHT: f32 = 10.0;
const DISTANCE_LINES: [f32; 8] = [10.0, 25.0, 50.0, 100.0, 150.0, 200.0, 250.0, 300.0];
const MARKER_POST_X: [f32; 2] = [-15.5, 15.5];
/// Marker post size (assumption): 0.3 m square, 1.5 m tall.
const MARKER_POST: (f32, f32) = (0.3, 1.5);
/// Lane dummy track x = bay centre + offset.
const LANE_TRACK_OFFSET: f32 = -0.40;
/// The lane dummy's default stop (the 25 m preset).
const LANE_DUMMY_Y: f32 = 25.0;
const LANE_DUMMY_DEFAULT: &str = "L T2 Mender [H,T]";

// ---------------------------------------------------------------- 4. Aim Lab
const AIM_HALL: Rect = Rect::new(-72.0, -20.0, -24.0, 18.0);
const AIM_HALL_HEIGHT: f32 = 7.0;
const AIM_CORRIDOR: Rect = Rect::new(-24.0, -20.0, -18.0, -15.0);
const AIM_BAY_WIDTH: f32 = 12.0;
/// Mode bays west -> east.
const AIM_MODES: [AimMode; 4] = [AimMode::Reaction, AimMode::Precision, AimMode::Tracking, AimMode::Gridshot];
/// Interior partitions (the hall walls stand at x -72 and -24): y -14..18, h 5.
const AIM_PARTITIONS_X: [f32; 3] = [-60.0, -48.0, -36.0];
const AIM_PARTITION: (f32, f32, f32) = (-14.0, 18.0, 5.0);
/// Glass divider between booths A and B (x0 + 6), y -12..18; 3.0 m tall and 0.1 m thick are assumptions.
const AIM_GLASS: (f32, f32, f32) = (-12.0, 18.0, 3.0);
const AIM_PAD_Y: f32 = -10.0;
const AIM_PAD_SIZE: f32 = 1.6;
/// Pad console relative to the pad centre; 0.5 m square, 1.1 m tall (assumption).
const AIM_PAD_CONSOLE_DX: f32 = 1.3;
/// Spectator rail at y -13 with a 2 m gap at each booth (segments relative to the bay x0); 1.0 m (assumption).
const AIM_RAIL_Y: f32 = -13.0;
const AIM_RAIL_SEGMENTS: [(f32, f32); 3] = [(0.3, 2.0), (4.0, 8.0), (10.0, 11.7)];
/// Overhead mode board: x relative to the bay x0, z 3.0..5.2.
const AIM_BOARD: Rect = Rect::new(2.0, -14.2, 10.0, -13.9);
const AIM_BOARD_Z: (f32, f32) = (3.0, 5.2);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum AimMode {
    Reaction,
    Precision,
    Tracking,
    Gridshot,
}

// ---------------------------------------------------------------- 5. Movement course
const COURSE_PATH: [Rect; 2] = [Rect::new(18.0, -20.0, 36.0, -15.0), Rect::new(32.0, -50.0, 36.0, -15.0)];
const START_GRID: Rect = Rect::new(38.0, -50.0, 46.0, -47.0);
const START_GATE: Rect = Rect::new(37.0, -46.2, 47.0, -45.8);
/// Course lanes (S1 sprint through the corner, S3 mantle lane, S6 final lane).
const COURSE_LANES: [Rect; 3] =
    [Rect::new(37.0, -46.0, 47.0, 20.0), Rect::new(47.0, 12.0, 72.0, 20.0), Rect::new(52.0, -48.0, 96.0, -40.0)];
const S2_RAMP: Rect = Rect::new(37.0, -16.0, 47.0, -10.0);
const S2_PLATFORM: Rect = Rect::new(37.0, -10.0, 47.0, -8.0);
const S2_CHUTE: Rect = Rect::new(37.0, -8.0, 47.0, 4.0);
const S2_HEIGHT: f32 = 2.0;
const SLIDE_TUNNEL: Rect = Rect::new(37.0, 4.0, 47.0, 12.0);
const TUNNEL_CEILING: f32 = 1.3;
const MANTLE_WALLS: [(Rect, f32); 3] = [
    (Rect::new(52.0, 12.0, 52.6, 20.0), 1.0),
    (Rect::new(58.0, 12.0, 58.6, 20.0), 1.5),
    (Rect::new(64.0, 12.0, 64.8, 20.0), 2.0),
];
const JET_WALL: (Rect, f32) = (Rect::new(72.0, 12.0, 78.0, 20.0), 5.0);
const PIT: Rect = Rect::new(78.0, 12.0, 88.0, 20.0);
const PIT_FLOOR: f32 = -3.0;
const TOWER: (Rect, f32) = (Rect::new(88.0, 12.0, 94.0, 20.0), 6.0);
/// Slide gate: open below 1.3 m, panel 1.3..3.3 m.
const SLIDE_GATE: Rect = Rect::new(80.0, -48.0, 80.6, -40.0);
const SLIDE_GATE_Z: (f32, f32) = (1.3, 3.3);
const FINAL_BOX: (Rect, f32) = (Rect::new(66.0, -48.0, 67.2, -40.0), 1.2);
/// S5 zipline anchors (x, y, z): from above the tower down to the final lane.
const ZIPLINE: [(f32, f32, f32); 2] = [(91.0, 11.5, 8.5), (91.0, -40.0, 3.0)];

/// The course pit (Bevy coordinates): the design resets a player who falls in to [`PIT_RESPAWN`]. That reset
/// is game logic; the pit itself is a 3 m deep hole.
pub const PIT_MIN: Vec3 = Vec3::new(78.0, -3.0, -20.0);
pub const PIT_MAX: Vec3 = Vec3::new(88.0, 0.0, -12.0);
/// Where a player who falls into the pit is put back (design (70, 16), in front of the jet wall).
pub const PIT_RESPAWN: Vec3 = Vec3::new(70.0, 0.0, -16.0);

/// A long-field or lane target for the game's target system. Not collision.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RangeTarget {
    /// Dummy halo config "<class> T<tier> <core> [zones]" (see `yard_targets` data), or the plate id.
    pub label: String,
    /// Feet / base centre, Bevy coordinates.
    pub pos: Vec3,
    pub kind: RangeTargetKind,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RangeTargetKind {
    Dummy,
    Plate,
}

/// Shared long-field targets: kind, x, y, label (layout `LONG_TARGETS`).
const LONG_TARGETS: [(RangeTargetKind, f32, f32, &str); 24] = {
    use RangeTargetKind::{Dummy as D, Plate as P};
    [
        // 100 m halo gallery: weight increases west -> east
        (D, -14.0, 100.0, "none (no halo)"),
        (D, -11.5, 100.0, "L T1 Phase [H,T]"),
        (D, -9.5, 100.0, "L T2 Mender [H,T]"),
        (D, -7.5, 100.0, "L T3 Volt [T]"),
        (D, -5.5, 100.0, "L T4 Phase [H]"),
        (P, -3.75, 100.0, "P30"),
        (D, -2.0, 100.0, "M T2 Mender [H,T,A,L]"),
        (D, 0.0, 100.0, "M T3 Volt [T,A]"),
        (D, 2.0, 100.0, "M T4 Bulwark [H,T]"),
        (P, 4.25, 100.0, "P50"),
        (D, 6.5, 100.0, "H T3 Bulwark [H,T,A]"),
        (D, 8.5, 100.0, "H T3 Volt [H,T,A,L]"),
        (D, 10.5, 100.0, "H T4 Bulwark [H,T,A,L]"),
        // 200 m core line: one dummy per core type
        (D, -9.0, 200.0, "M T3 Bulwark [H,T]"),
        (D, -3.0, 200.0, "M T3 Mender [H,T]"),
        (D, 3.0, 200.0, "M T3 Volt [H,T]"),
        (D, 9.0, 200.0, "M T3 Phase [H,T]"),
        (P, -13.5, 200.0, "SIL"),
        (P, 13.5, 200.0, "P50"),
        // 300 m: the two extremes + big plates
        (D, -4.0, 300.0, "H T4 Bulwark [H,T,A,L]"),
        (D, 4.0, 300.0, "L T1 Phase [T]"),
        (P, -10.0, 300.0, "P75"),
        (P, 0.0, 300.0, "SIL"),
        (P, 10.0, 300.0, "P100"),
    ]
};

fn bay_centre(i: usize) -> f32 {
    BAY_X0 + BAY_WIDTH * (i as f32 + 0.5)
}

/// The long-field targets plus one lane dummy per firing bay at its 25 m preset.
pub fn range_targets() -> Vec<RangeTarget> {
    let long = LONG_TARGETS.iter().map(|&(kind, x, y, label)| RangeTarget {
        label: label.into(),
        pos: design(x, y, 0.0),
        kind,
    });
    let lanes = (0..BAY_COUNT).map(|i| RangeTarget {
        label: LANE_DUMMY_DEFAULT.into(),
        pos: design(bay_centre(i) + LANE_TRACK_OFFSET, LANE_DUMMY_Y, 0.0),
        kind: RangeTargetKind::Dummy,
    });
    long.chain(lanes).collect()
}

/// Rect of `w` x `d` centred on (x, y).
fn centred(x: f32, y: f32, w: f32, d: f32) -> Rect {
    Rect::new(x - w / 2.0, y - d / 2.0, x + w / 2.0, y + d / 2.0)
}

fn ready_room(b: &mut Builder, g: &mut FloorPlan) {
    let doors = [
        Opening::y(READY_ROOM.y1, -4.0, 4.0, 0.0, DOOR_H), // N to the Range Deck (8 m)
        Opening::x(READY_ROOM.x0, -20.0, -15.0, 0.0, DOOR_H), // W to the Aim Lab
        Opening::x(READY_ROOM.x1, -20.0, -15.0, 0.0, DOOR_H), // E to the course
    ];
    for w in box_walls(READY_ROOM, 0.0, READY_ROOM_HEIGHT, WALL_T, L::Wall) {
        b.wall(&w, &doors);
    }
    b.solid(READY_ROOM.grow(WALL_T / 2.0), READY_ROOM_HEIGHT, READY_ROOM_HEIGHT + ROOF_T, L::Roof);

    g.patch(READY_ROOM, L::Floor);
    g.patch(SPAWN_STRIP, L::Accent);
    for (r, look) in TEAM_PADS {
        g.patch(r, look);
    }
    g.patch(FITTING_PAD, L::Accent);

    let (x, y, r) = OPS_TABLE;
    b.solid(centred(x, y, 2.0 * r, 2.0 * r), 0.0, 1.0, L::Prop);
    b.solid(WEAPON_WALL, 0.0, RACK_H, L::Metal);
    b.solid(HALO_WALL, 0.0, RACK_H, L::Metal);
    for r in LOADOUT_BENCHES {
        b.solid(r, 0.0, BENCH_H, L::Prop);
    }
    for (x, y) in MANNEQUINS {
        b.solid(centred(x, y, 1.2, 1.2), 0.0, 0.4, L::Prop);
    }
    for r in HALL_BOARDS {
        b.solid(r, 2.0, 4.0, L::Accent);
    }
}

fn deck(b: &mut Builder, g: &mut FloorPlan) {
    let (rw, z) = (WALL_T / 2.0, DECK_ROOF_Z);
    g.patch(DECK, L::Concrete);
    g.patch(RECOIL_LAB, L::Concrete);
    // Enclosure: west end wall (Range Board side), back walls either side of the Ready Room, east end wall
    // up to the Recoil Lab. The deck is open to the field.
    b.solid(Rect::new(DECK.x0 - 0.3, DECK.y0 - rw, DECK.x0, DECK.y1), 0.0, z, L::Wall);
    b.solid(Rect::new(DECK.x0 - 0.3, DECK.y0 - rw, READY_ROOM.x0 - rw, DECK.y0 + rw), 0.0, z, L::Wall);
    b.solid(Rect::new(READY_ROOM.x1 + rw, DECK.y0 - rw, DECK.x1, DECK.y0 + rw), 0.0, z, L::Wall);
    b.solid(Rect::new(DECK.x1 - 0.3, DECK.y0 + rw, DECK.x1, -4.0), 0.0, z, L::Wall);
    let roof = Rect::new(DECK_ROOF.x0 - 0.3, DECK_ROOF.y0 - rw, DECK_ROOF.x1, DECK_ROOF.y1);
    b.solid(roof, z, z + ROOF_T, L::Roof);
    b.solid(RANGE_BOARD, 1.5, z, L::Accent);

    let (t, y0, y1, h) = PARTITION;
    for k in 0..=BAY_COUNT {
        let x = BAY_X0 + BAY_WIDTH * k as f32;
        b.solid(Rect::new(x - t / 2.0, y0, x + t / 2.0, y1), 0.0, h, L::Wall);
    }
    for i in 0..BAY_COUNT {
        let xc = bay_centre(i);
        let f = FIRING_BENCH;
        b.solid(Rect::new(xc + f.x0, f.y0, xc + f.x1, f.y1), 0.0, BENCH_H, L::Prop);
        let (dx, y) = LANE_READOUT;
        b.solid(centred(xc + dx, y, 1.2, 0.3), 0.0, LANE_READOUT_TOP, L::Accent);
    }

    // Recoil Lab: two enclosed lanes, roofed at the deck height.
    for r in RECOIL_WALLS {
        b.solid(r, 0.0, RECOIL_WALL_H, L::Wall);
    }
    b.solid(Rect::new(RECOIL_LAB.x0, DECK_ROOF.y1, RECOIL_LAB.x1, RECOIL_LAB.y1), z, z + ROOF_T, L::Roof);
    for xc in RECOIL_BAY_CENTRES {
        b.solid(Rect::new(xc - 0.4, -0.8, xc + 0.4, 0.0), 0.0, BENCH_H, L::Prop);
    }
}

fn field(b: &mut Builder) {
    b.solid(BERM_W, 0.0, BERM_HEIGHT, L::Ground);
    b.solid(BERM_E, 0.0, BERM_HEIGHT, L::Ground);
    b.solid(BACKSTOP, 0.0, BACKSTOP_HEIGHT, L::Ground);
    let (w, h) = MARKER_POST;
    for d in DISTANCE_LINES {
        for x in MARKER_POST_X {
            b.solid(centred(x, d, w, w), 0.0, h, L::Accent);
        }
    }
}

fn aim_lab(b: &mut Builder, g: &mut FloorPlan) {
    let door = [Opening::x(AIM_HALL.x1, AIM_CORRIDOR.y0, AIM_CORRIDOR.y1, 0.0, DOOR_H)];
    for w in box_walls(AIM_HALL, 0.0, AIM_HALL_HEIGHT, WALL_T, L::Wall) {
        b.wall(&w, &door);
    }
    b.solid(AIM_HALL.grow(WALL_T / 2.0), AIM_HALL_HEIGHT, AIM_HALL_HEIGHT + ROOF_T, L::Roof);
    // Corridor to the Ready Room's west door, roofed at door height.
    let c = AIM_CORRIDOR;
    b.wall(&WallDef::seg(c.x0, c.y0, c.x1, c.y0, 0.0, DOOR_H, WALL_T), &[]);
    b.wall(&WallDef::seg(c.x0, c.y1, c.x1, c.y1, 0.0, DOOR_H, WALL_T), &[]);
    b.solid(Rect::new(c.x0, c.y0 - WALL_T / 2.0, c.x1, c.y1 + WALL_T / 2.0), DOOR_H, DOOR_H + ROOF_T, L::Roof);
    g.patch(AIM_HALL, L::Floor);
    g.patch(AIM_CORRIDOR, L::Floor);

    let (py0, py1, ph) = AIM_PARTITION;
    for x in AIM_PARTITIONS_X {
        b.solid(Rect::new(x - 0.15, py0, x + 0.15, py1), 0.0, ph, L::Wall);
    }
    for (i, mode) in AIM_MODES.into_iter().enumerate() {
        let x0 = AIM_HALL.x0 + AIM_BAY_WIDTH * i as f32;
        let (gy0, gy1, gh) = AIM_GLASS;
        b.solid(Rect::new(x0 + 5.95, gy0, x0 + 6.05, gy1), 0.0, gh, L::Glass);
        for (a, z) in AIM_RAIL_SEGMENTS {
            b.solid(Rect::new(x0 + a, AIM_RAIL_Y - 0.05, x0 + z, AIM_RAIL_Y + 0.05), 0.0, 1.0, L::Metal);
        }
        let r = AIM_BOARD;
        b.solid(Rect::new(x0 + r.x0, r.y0, x0 + r.x1, r.y1), AIM_BOARD_Z.0, AIM_BOARD_Z.1, L::Accent);
        for xb in [x0 + 3.0, x0 + 9.0] {
            g.patch(centred(xb, AIM_PAD_Y, AIM_PAD_SIZE, AIM_PAD_SIZE), L::Accent);
            b.solid(centred(xb + AIM_PAD_CONSOLE_DX, AIM_PAD_Y, 0.5, 0.5), 0.0, 1.1, L::Prop);
            match mode {
                // target panel band
                AimMode::Reaction => b.solid(Rect::new(xb - 2.0, -2.15, xb + 2.0, -1.85), 0.4, 2.8, L::Target),
                // three cover rails the heads pop up behind
                AimMode::Precision => {
                    for ry in [5.0, 10.0, 15.0] {
                        b.solid(Rect::new(xb - 2.5, ry - 0.15, xb + 2.5, ry + 0.15), 0.0, 1.0, L::Concrete);
                    }
                }
                // the bot strafes in the open
                AimMode::Tracking => {}
                // backing wall behind the target grid
                AimMode::Gridshot => b.solid(Rect::new(xb - 2.8, 0.5, xb + 2.8, 0.6), 0.2, 3.0, L::Concrete),
            }
        }
    }
}

fn course(b: &mut Builder, g: &mut FloorPlan) {
    for r in COURSE_PATH.into_iter().chain(COURSE_LANES) {
        g.patch(r, L::Concrete);
    }
    g.patch(START_GRID, L::Accent);
    g.patch(START_GATE, L::Accent);

    // S2: ramp up 2 m over 6 m, platform, slide chute down 2 m over 12 m, slide tunnel (ceiling 1.3 m).
    b.ramp(S2_RAMP, 0.0, S2_HEIGHT, Dir::North, BrushKind::Solid, L::Concrete);
    b.solid(S2_PLATFORM, 0.0, S2_HEIGHT, L::Concrete);
    b.ramp(S2_CHUTE, 0.0, S2_HEIGHT, Dir::South, BrushKind::Solid, L::Concrete);
    let t = SLIDE_TUNNEL;
    b.solid(t.grow(0.3), TUNNEL_CEILING, TUNNEL_CEILING + 0.3, L::Concrete);
    b.solid(Rect::new(t.x0 - 0.3, t.y0, t.x0, t.y1), 0.0, TUNNEL_CEILING, L::Concrete);
    b.solid(Rect::new(t.x1, t.y0, t.x1 + 0.3, t.y1), 0.0, TUNNEL_CEILING, L::Concrete);

    // S3 mantles, S4 jet wall, pit and tower.
    for (r, h) in MANTLE_WALLS {
        b.solid(r, 0.0, h, L::Accent);
    }
    b.solid(JET_WALL.0, 0.0, JET_WALL.1, L::Concrete);
    g.cut(PIT);
    b.solid(PIT, GROUND_BOTTOM, PIT_FLOOR, L::Concrete);
    b.solid(TOWER.0, 0.0, TOWER.1, L::Concrete);

    // S5 zipline poles beside the cable (east of it, so riders do not hit them).
    let [(x, y, z), (x2, y2, z2)] = ZIPLINE;
    b.solid(centred(x + 0.75, y - 0.2, 0.3, 0.3), 0.0, z + 0.3, L::Metal);
    b.solid(centred(x2 + 0.75, y2, 0.3, 0.3), 0.0, z2 + 0.3, L::Metal);

    // S6: slide gate (panel on two posts) and the mantle box.
    let s = SLIDE_GATE;
    b.solid(s, SLIDE_GATE_Z.0, SLIDE_GATE_Z.1, L::Accent);
    b.solid(Rect::new(s.x0, s.y0 - 0.3, s.x1, s.y0), 0.0, SLIDE_GATE_Z.1, L::Metal);
    b.solid(Rect::new(s.x0, s.y1, s.x1, s.y1 + 0.3), 0.0, SLIDE_GATE_Z.1, L::Metal);
    b.solid(FINAL_BOX.0, 0.0, FINAL_BOX.1, L::Accent);
}

/// The training range.
pub fn range() -> Level {
    let mut b = Builder::default();
    let mut g = FloorPlan::new(SITE, L::Ground);
    ready_room(&mut b, &mut g);
    deck(&mut b, &mut g);
    field(&mut b);
    aim_lab(&mut b, &mut g);
    course(&mut b, &mut g);
    for &(r, look) in g.pieces() {
        b.solid(r, GROUND_BOTTOM, 0.0, look);
    }
    // Invisible site walls.
    let s = SITE;
    for r in [
        Rect::new(s.x0 - 1.0, s.y0 - 1.0, s.x0, s.y1 + 1.0),
        Rect::new(s.x1, s.y0 - 1.0, s.x1 + 1.0, s.y1 + 1.0),
        Rect::new(s.x0, s.y0 - 1.0, s.x1, s.y0),
        Rect::new(s.x0, s.y1, s.x1, s.y1 + 1.0),
    ] {
        b.clip(r, GROUND_BOTTOM, BOUNDS_TOP);
    }

    let spawns = (0..10)
        .map(|k| SpawnPoint { pos: design(-13.5 + 3.0 * k as f32, SPAWN_Y, 0.0), yaw: design_yaw(90.0), team: None })
        .collect();
    let [a, z] = ZIPLINE;
    Level {
        name: "Range".into(),
        world: b.finish(),
        ziplines: vec![Zipline { a: design(a.0, a.1, a.2), b: design(z.0, z.1, z.2) }],
        spawns,
        kill_y: KILL_Y,
    }
}

#[cfg(test)]
mod tests {
    use super::super::test_util::{HALF, assert_spawns_grounded, surface_below};
    use super::*;

    #[test]
    fn spawns_stand_on_ground_facing_downrange() {
        let l = range();
        assert_eq!(l.spawns.len(), 10);
        assert_spawns_grounded(&l);
        assert!(l.spawns.iter().all(|s| s.team.is_none() && s.yaw.abs() < 1e-6));
        assert_eq!(l.spawns[0].pos, Vec3::new(-13.5, 0.0, 37.0));
    }

    #[test]
    fn field_is_open_to_the_backstop() {
        let l = range();
        let eye = Vec3::new(0.0, 1.6, 0.0);
        assert!(l.world.line_of_sight(eye, Vec3::new(0.0, 1.6, -300.0)));
        let (d, n) = l.world.raycast(eye, Vec3::NEG_Z, 400.0).expect("backstop");
        // The backstop face is at 305 m (the trace stops a skin short of it).
        assert!((304.9..=320.0).contains(&d), "{d}");
        assert_eq!(n, Vec3::Z);
        // Every long-field target is visible from just in front of the benches.
        for t in range_targets() {
            let from = Vec3::new(t.pos.x.clamp(-12.0, 12.0), 1.6, -0.5);
            assert!(l.world.line_of_sight(from, t.pos + Vec3::Y * 1.0), "{t:?}");
        }
        // The berms keep stray shots in.
        assert!(!l.world.line_of_sight(Vec3::new(0.0, 1.6, -50.0), Vec3::new(-40.0, 1.6, -50.0)));
    }

    #[test]
    fn targets() {
        let t = range_targets();
        assert_eq!(t.len(), 24 + BAY_COUNT);
        assert_eq!(t.iter().filter(|t| t.kind == RangeTargetKind::Plate).count(), 7);
        let lanes: Vec<_> = t.iter().skip(24).collect();
        assert!((lanes[0].pos - Vec3::new(-12.65, 0.0, -25.0)).length() < 1e-4, "{:?}", lanes[0]);
        assert!(lanes.iter().all(|l| l.label == LANE_DUMMY_DEFAULT));
        assert!(t.iter().all(|t| t.pos.x.abs() < 16.0 && t.pos.y == 0.0 && t.pos.z < 0.0));
    }

    #[test]
    fn course_heights() {
        let l = range();
        let at = |x: f32, y: f32| surface_below(&l, design(x, y, 12.0));
        assert!((at(42.0, -13.0) - 1.0).abs() < 0.01, "ramp halfway");
        assert!((at(42.0, -9.0) - 2.0).abs() < 0.01, "platform");
        assert!((at(42.0, -2.0) - 1.0).abs() < 0.01, "chute halfway");
        assert!((at(75.0, 16.0) - 5.0).abs() < 0.01, "jet wall");
        assert!((at(83.0, 16.0) - PIT_FLOOR).abs() < 0.01, "pit");
        assert!((at(91.0, 16.0) - 6.0).abs() < 0.01, "tower");
        assert!((at(0.0, -5.0) - (DECK_ROOF_Z + ROOF_T)).abs() < 0.01, "deck roof");
        assert!((PIT_MIN.y - PIT_FLOOR).abs() < 1e-6 && PIT_MAX.x == 88.0);
        let zl = l.ziplines[0];
        assert!(zl.a.y > zl.b.y && (zl.a - design(91.0, 11.5, 8.5)).length() < 1e-4);
    }

    #[test]
    fn slide_tunnel_needs_a_slide() {
        let l = range();
        // From the corner (y 13) back into the tunnel: standing hits the 1.3 m ceiling, sliding fits.
        let stand = l.world.trace_box(design(42.0, 13.0, 0.92), design(42.0, 6.0, 0.92), HALF);
        assert!(stand.hit() && !stand.start_solid);
        let slide = Vec3::new(0.32, 0.45, 0.32);
        let t = l.world.trace_box(design(42.0, 13.0, 0.47), design(42.0, 4.5, 0.47), slide);
        assert!(!t.hit() && !t.start_solid, "{t:?}");
    }

    #[test]
    fn doors_connect_the_hub() {
        let l = range();
        let y = HALF.y + 0.02;
        // Ready Room -> deck (north door), -> Aim Lab corridor (west), -> course path (east).
        for (from, to) in [
            (design(0.0, -14.0, y), design(0.0, -6.0, y)),
            (design(-15.0, -17.5, y), design(-30.0, -17.5, y)),
            (design(15.0, -17.5, y), design(30.0, -17.5, y)),
        ] {
            let t = l.world.trace_box(from, to, HALF);
            assert!(!t.hit() && !t.start_solid, "{from} -> {to}: {t:?}");
        }
        // ... and a wall elsewhere.
        assert!(l.world.trace_box(design(0.0, -38.0, y), design(0.0, -45.0, y), HALF).hit());
    }

    #[test]
    fn brush_budget() {
        let l = range();
        let n = l.world.brushes.len();
        assert!(n > 100 && n < 1500, "{n} brushes");
        assert_eq!(l.name, "Range");
        assert_eq!(l.kill_y, -10.0);
    }

    /// S5: riding the zipline down from the tower, or up to it, without jumping off ends clear of everything,
    /// and the rider can walk away.
    #[test]
    fn zipline_rides_end_clear() {
        use super::super::test_util::{assert_walks_away, ride_zipline};
        use crate::movement::MoveMode;
        let l = range();
        // Down: grab from the tower's edge facing south.
        let (ticks, _) = ride_zipline(&l, design(91.0, 12.33, 6.0), MoveMode::Ground, design_yaw(-90.0), None, 7.0);
        let last = *ticks.last().unwrap();
        assert_eq!(last.mode, MoveMode::Ground, "{last:?}");
        assert_walks_away(&l, last, design_yaw(-90.0));
        // Up: grab the low end in mid-jump facing north.
        let (ticks, _) = ride_zipline(&l, design(91.0, -39.0, 0.8), MoveMode::Air, design_yaw(90.0), None, 9.0);
        let last = *ticks.last().unwrap();
        assert_eq!(last.mode, MoveMode::Ground, "{last:?}");
        assert_walks_away(&l, last, design_yaw(-90.0));
    }
}
