"""Single source of truth for the RANGE / HQ training map layout ("the Yard").

All numbers are metres. Coordinate frame (same as Blender, Z-up):
    X = east (+), Y = north (+, the shooting direction), Z = up.
    Origin (0, 0, 0) = centre of the firing line (front edge of the firing-bay benches), floor level.
glTF export converts to Bevy's Y-up: Bevy (x, y, z) = Blender (X, Z, -Y), so "north" = Bevy -Z.

Rectangles are (x0, y0, x1, y1) with x0 < x1 and y0 < y1. Heights are given separately.
The diagram scripts in this folder draw only from this file, and a Blender blockout script can import it
too, so the plan and the 3D blockout cannot drift apart.
"""
import math

EYE_HEIGHT = 1.60          # camera height of a standing agent (characters are 1.68-1.70 m)
SLIDE_EYE_HEIGHT = 0.85    # from design/systems movement FSM (draft)

# --------------------------------------------------------------------------------------------
# 1. READY ROOM (hub / armory, spawn, match terminal)
# --------------------------------------------------------------------------------------------
READY_ROOM = (-18.0, -40.0, 18.0, -10.0)          # 36 x 30 m, interior height 6 m
READY_ROOM_HEIGHT = 6.0
READY_DOORS = {                                   # wall openings, (x0, y0, x1, y1) on the wall line
    "N to Range Deck": (-4.0, -10.0, 4.0, -10.0),   # 8 m
    "W to Aim Lab": (-18.0, -20.0, -18.0, -15.0),   # 5 m
    "E to Course": (18.0, -20.0, 18.0, -15.0),      # 5 m
}
SPAWN_STRIP = (-15.0, -38.5, 15.0, -35.5)
SPAWNS = [(-13.5 + 3.0 * k, -37.0) for k in range(10)]   # SP1..SP10, facing +Y (north)
OPS_TABLE = (0.0, -27.0, 2.5)                      # centre x, y, radius; table top 1.0 m
OPS_INTERACT_RADIUS = 3.5
TEAM_PADS = {"TEAM A (teal)": (-8.0, -22.0, -3.0, -17.0), "TEAM B (coral)": (3.0, -22.0, 8.0, -17.0)}
WEAPON_WALL = (-18.0, -36.0, -17.4, -22.0)         # display racks, 0.6 m deep, 14 m long
LOADOUT_BENCHES = {"W1": (-14.0, -34.0, -12.8, -28.0), "W2": (-14.0, -27.0, -12.8, -21.0)}  # 1.2 x 6 m, h 0.95
BENCH_SPOTS = [(-12.2, y) for y in (-33.0, -31.0, -29.0, -26.0, -24.0, -22.0)]
HALO_WALL = (17.4, -36.0, 18.0, -22.0)
MANNEQUINS = {"Light": (15.6, -33.0), "Medium": (15.6, -28.5), "Heavy": (15.6, -24.0)}  # plinth r 0.6, h 0.4
FITTING_PAD = (9.0, -31.0, 12.0, -28.0)            # 3 x 3 m, opens loadout in 3rd-person view
HALL_BOARDS = {"Aim records": (-15.0, -10.4, -6.0, -10.1), "Course + range records": (6.0, -10.4, 15.0, -10.1)}

# --------------------------------------------------------------------------------------------
# 2. RANGE DECK (covered firing line) + RECOIL LAB
# --------------------------------------------------------------------------------------------
DECK = (-20.0, -10.0, 30.0, 0.0)
DECK_ROOF = (-20.0, -10.0, 30.0, 2.0)              # roof underside 4.0 m, overhang 2 m past the line
BAY_WIDTH = 3.5
BAY_DEPTH = 4.0                                    # bay floor y -4..0, walkway y -10..-4
BAYS = [{"id": f"B{i + 1}", "x0": -14.0 + BAY_WIDTH * i, "x1": -14.0 + BAY_WIDTH * (i + 1),
         "xc": -12.25 + BAY_WIDTH * i} for i in range(8)]
BAY_PARTITIONS_X = [-14.0 + BAY_WIDTH * k for k in range(9)]   # 0.2 thick, y -4..0, h 2.2
FIRING_BENCH = (-1.2, -0.8, 1.2, 0.0)             # relative to bay centre, h 0.95
BAY_MONITOR = (1.35, -1.0)                         # relative to bay centre (lane console + readout)
BAY_RACK = (1.15, -3.4)                            # relative to bay centre (opens loadout menu)
RANGE_CONTROL = (14.0, -4.0, 22.0, 0.0)            # alcove between B8 and R1, master console
RANGE_BOARD = (-20.0, -9.0, -19.7, -1.0)           # shared damage board on the deck's west end wall, z 1.5-4.5

RECOIL_BAYS = [{"id": "R1", "x0": 22.0, "x1": 26.0, "xc": 24.0}, {"id": "R2", "x0": 26.0, "x1": 30.0, "xc": 28.0}]
RECOIL_WALLS = [(22.0, -4.0, 22.3, 29.0), (25.9, 0.0, 26.1, 28.0), (29.7, -4.0, 30.0, 29.0),
                (22.0, 28.0, 30.0, 29.0)]           # h 4.0 m
RECOIL_BOARD_STOPS = [10.0, 15.0, 25.0]            # board carriage stops (default 15 m)
RECOIL_BOARD_W, RECOIL_BOARD_Z = 3.0, (0.4, 3.8)
RECOIL_AIM_Z = 1.2                                 # aim marker height; 2.6 m headroom = 5.9 deg at 25 m

# --------------------------------------------------------------------------------------------
# 3. RANGE FIELD (open air, 0-300 m)
# --------------------------------------------------------------------------------------------
FIELD = (-16.0, 0.0, 16.0, 305.0)
BERM_W = (-22.0, 0.0, -16.0, 305.0)                # 4 m tall earth berm
BERM_E = (16.0, 0.0, 22.0, 305.0)
BERM_HEIGHT = 4.0
BACKSTOP = (-22.0, 305.0, 22.0, 320.0)             # 10 m tall
BACKSTOP_HEIGHT = 10.0
DISTANCE_LINES = [10, 25, 50, 100, 150, 200, 250, 300]
MARKER_POST_X = (-15.5, 15.5)

LANE_TRACK_OFFSET = -0.40                          # lane dummy track x = bay centre - 0.40
LANE_TRACK_Y = (8.0, 50.0)                         # dummy can stop anywhere 8-50 m; presets 10/25/50
LANE_PRESETS = [10, 25, 50]
LANE_READOUT = (1.2, 5.0)                          # relative x to bay centre, absolute y; 1.2 x 0.3 m, top 0.45 m
PLATE_STAND_OFFSET = 1.20                          # plate tree x = bay centre + 1.20

# Steel plate catalogue: id -> (shape, width_cm, height_cm)
PLATES = {
    "P10": ("round", 10, 10), "P20": ("round", 20, 20), "P30": ("round", 30, 30),
    "P50": ("round", 50, 50), "P75": ("round", 75, 75), "P100": ("round", 100, 100),
    "TORSO": ("rect", 45, 60), "SIL": ("silhouette", 55, 175),
}
# per-lane plate trees: distance -> [(plate, centre height z)]
LANE_READOUT_TOP = 0.45
LANE_PLATES = {10: [("P20", 1.60), ("P10", 1.10)],
               25: [("P20", 1.60), ("TORSO", 1.10)],
               50: [("P30", 1.60), ("TORSO", 1.10)]}

RUNNER_TRACK = (-14.0, 60.0, 14.0, 60.0)           # shared moving dummy, lateral

# Training dummy ("HQ-D1") hit zones, front view. Matches the 4 halo coverage zones.
# zone -> list of (shape, centre_x, centre_z, width, height); metres
DUMMY_HEIGHT = 1.75
DUMMY_ZONES = {
    "Head": [("ellipse", 0.0, 1.60, 0.22, 0.26)],
    "Torso": [("rect", 0.0, 1.145, 0.44, 0.65)],                         # z 0.82-1.47 (neck + pelvis incl.)
    "Arms": [("rect", -0.29, 1.11, 0.12, 0.62), ("rect", 0.29, 1.11, 0.12, 0.62)],   # z 0.80-1.42
    "Legs": [("rect", -0.11, 0.41, 0.15, 0.82), ("rect", 0.11, 0.41, 0.15, 0.82)],   # z 0.00-0.82
}
HALO_Z = 1.73 + 0.22                               # head top + socket offset (HALO_SHIELD_SPEC)
HALO_RADIUS = 0.16
HALO_SCALE = {"L": 0.85, "M": 1.0, "H": 1.2}

# shared long-field targets: (kind, x, y, label). Dummy labels: "<class> T<tier> <core> [zones]".
# Weight class follows design/systems: points = tier x covered zones; Light 1-4, Medium 5-8, Heavy 9-16.
# So Medium starts at T2 and Heavy at T3 - the gallery shows every valid tier/weight combination,
# weight increasing from left (west) to right (east). Configs live in data (yard_targets.ron), not in the mesh.
GALLERY = [
    ("dummy", -14.0, 100.0, "none (no halo)"),
    ("dummy", -11.5, 100.0, "L T1 Phase [H,T]"), ("dummy", -9.5, 100.0, "L T2 Mender [H,T]"),
    ("dummy", -7.5, 100.0, "L T3 Volt [T]"), ("dummy", -5.5, 100.0, "L T4 Phase [H]"),
    ("plate", -3.75, 100.0, "P30"),
    ("dummy", -2.0, 100.0, "M T2 Mender [H,T,A,L]"), ("dummy", 0.0, 100.0, "M T3 Volt [T,A]"),
    ("dummy", 2.0, 100.0, "M T4 Bulwark [H,T]"),
    ("plate", 4.25, 100.0, "P50"),
    ("dummy", 6.5, 100.0, "H T3 Bulwark [H,T,A]"), ("dummy", 8.5, 100.0, "H T3 Volt [H,T,A,L]"),
    ("dummy", 10.5, 100.0, "H T4 Bulwark [H,T,A,L]"),
]
LONG_TARGETS = GALLERY + [
    # Core Line at 200 m: one dummy per core type, all M T3 [H,T] so only the ring shape differs
    ("dummy", -9.0, 200.0, "M T3 Bulwark [H,T]"), ("dummy", -3.0, 200.0, "M T3 Mender [H,T]"),
    ("dummy", 3.0, 200.0, "M T3 Volt [H,T]"), ("dummy", 9.0, 200.0, "M T3 Phase [H,T]"),
    ("plate", -13.5, 200.0, "SIL"), ("plate", 13.5, 200.0, "P50"),
    # 300 m: the two extremes + big plates
    ("dummy", -4.0, 300.0, "H T4 Bulwark [H,T,A,L]"), ("dummy", 4.0, 300.0, "L T1 Phase [T]"),
    ("plate", -10.0, 300.0, "P75"), ("plate", 0.0, 300.0, "SIL"), ("plate", 10.0, 300.0, "P100"),
]
RUNNER_DEFAULT = "M T3 Volt [T,A]"
LANE_DUMMY_DEFAULT = "L T2 Mender [H,T]"


def tier_of(label):
    """1-4 from a dummy label like 'M T3 Volt [T,A]', 0 for no halo."""
    import re
    m = re.search(r"T(\d)", label)
    return int(m.group(1)) if m else 0


# --------------------------------------------------------------------------------------------
# 4. AIM LAB ("Reflex Hall")
# --------------------------------------------------------------------------------------------
AIM_HALL = (-72.0, -20.0, -24.0, 18.0)             # 48 x 38 m, height 7 m
AIM_CORRIDOR = (-24.0, -20.0, -18.0, -15.0)        # to the Ready Room west door
AIM_CONCOURSE = (-72.0, -20.0, -24.0, -14.0)
AIM_BAY_WIDTH = 12.0
AIM_MODES = ["REACTION", "PRECISION", "TRACKING", "GRIDSHOT"]          # west -> east
AIM_BAYS = [{"mode": m, "x0": -72.0 + AIM_BAY_WIDTH * i, "x1": -60.0 + AIM_BAY_WIDTH * i,
             "booths": {"A": -69.0 + AIM_BAY_WIDTH * i, "B": -63.0 + AIM_BAY_WIDTH * i}}
            for i, m in enumerate(AIM_MODES)]
AIM_PARTITIONS_X = [-72.0, -60.0, -48.0, -36.0, -24.0]                 # y -14..18, h 5
AIM_PAD_Y = -10.0                                  # pad centre y; pad 1.6 x 1.6
AIM_PAD_SIZE = 1.6
AIM_PAD_CONSOLE = (1.3, 0.0)                       # relative to pad centre
AIM_RAIL_Y = -13.0                                 # spectator rail, gap of 2 m at each booth centre
AIM_BOARD = (2.0, -14.2, 10.0, -13.9)              # x relative to bay x0; double-sided, z 3.0-5.2

# mode geometry, relative to the booth centre x (xb) and absolute y
GRID = {"plane_y": 0.0, "cols_dx": [-2.0, -1.0, 0.0, 1.0, 2.0], "rows_z": [0.6, 1.6, 2.6],
        "target_d": 0.40, "live": 3, "backing": (-2.8, 0.5, 2.8, 0.6), "backing_z": (0.2, 3.0)}
TRACK = {"band_y": 4.0, "half_range": 2.4, "bot_d": 0.50, "bot_h": 1.75, "head_d": 0.25}
REACT = {"panel_y": -2.0, "half_w": 2.0, "z": (0.4, 2.8)}
PRECISION = {"rails_y": [5.0, 10.0, 15.0], "rail_half_w": 2.5, "rail_h": 1.0, "spawn_half_w": 2.2,
             "head_d": 0.22, "head_z": {"stand": 1.60, "crouch": 1.20}}

# --------------------------------------------------------------------------------------------
# 5. MOVEMENT COURSE ("Kinetic Yard")
# --------------------------------------------------------------------------------------------
COURSE_AREA = (32.0, -52.0, 97.0, 22.0)
COURSE_PATH = [(18.0, -20.0, 36.0, -15.0), (32.0, -50.0, 36.0, -15.0)]   # walkway from the Ready Room
START_GRID = (38.0, -50.0, 46.0, -47.0)
START_SPOTS = [(39.0, -48.5), (41.0, -48.5), (43.0, -48.5), (45.0, -48.5)]
# course pieces: (name, rect, z_from, z_to, note)
COURSE = [
    ("START GATE", (37.0, -46.2, 47.0, -45.8), 0, 0, "timer GO"),
    ("S1 SPRINT", (37.0, -46.0, 47.0, -16.0), 0, 0, "30 m flat"),
    ("S2 RAMP UP", (37.0, -16.0, 47.0, -10.0), 0, 2.0, "+2.0 m over 6 m (18 deg)"),
    ("S2 PLATFORM", (37.0, -10.0, 47.0, -8.0), 2.0, 2.0, ""),
    ("S2 SLIDE CHUTE", (37.0, -8.0, 47.0, 4.0), 2.0, 0, "-2.0 m over 12 m (9.5 deg)"),
    ("S2 SLIDE TUNNEL", (37.0, 4.0, 47.0, 12.0), 0, 0, "ceiling 1.3 m"),
    ("CORNER", (37.0, 12.0, 47.0, 20.0), 0, 0, ""),
    ("S3 MANTLE LANE", (47.0, 12.0, 72.0, 20.0), 0, 0, ""),
    ("S4 JET WALL", (72.0, 12.0, 78.0, 20.0), 5.0, 5.0, "top 5.0 m"),
    ("S4 JET GAP (pit)", (78.0, 12.0, 88.0, 20.0), 0, 0, "10 m gap, fall = reset to (70, 16)"),
    ("S4 TOWER", (88.0, 12.0, 94.0, 20.0), 6.0, 6.0, "top 6.0 m"),
    ("S6 FINAL LANE", (52.0, -48.0, 96.0, -40.0), 0, 0, "run west"),
]
MANTLE_WALLS = [("M1 1.0 m", (52.0, 12.0, 52.6, 20.0), 1.0), ("M2 1.5 m", (58.0, 12.0, 58.6, 20.0), 1.5),
                ("M3 2.0 m", (64.0, 12.0, 64.8, 20.0), 2.0)]
SLIDE_GATE = ("SLIDE GATE", (80.0, -48.0, 80.6, -40.0), 1.3)           # opening below 1.3 m, panel 1.3-3.3 m
FINAL_BOX = ("MANTLE BOX 1.2 m", (66.0, -48.0, 67.2, -40.0), 1.2)
ZIPLINE = ((91.0, 11.5, 8.5), (91.0, -40.0, 3.0))                      # start anchor, end anchor (x, y, z)
CHECKPOINTS = {"CP1": (37.0, 12.0, 47.0, 12.0), "CP2": (68.0, 12.0, 68.0, 20.0),
               "CP3": (91.0, 12.0, 91.0, 20.0), "CP4": (86.0, -42.0, 96.0, -42.0),
               "FINISH": (52.0, -48.0, 52.0, -40.0)}
PIT_RESPAWN = (70.0, 16.0)

SITE_BOUNDS = (-80.0, -60.0, 105.0, 325.0)


def zipline_length():
    (x0, y0, z0), (x1, y1, z1) = ZIPLINE
    return math.dist((x0, y0, z0), (x1, y1, z1))


def angular(size_m, dist_m):
    """Return (mrad, degrees, MOA) subtended by size_m at dist_m."""
    rad = 2 * math.atan(size_m / (2 * dist_m))
    return rad * 1000.0, math.degrees(rad), math.degrees(rad) * 60.0
