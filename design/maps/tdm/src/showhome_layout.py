"""SHOWHOME - small symmetric TDM map. Single source of truth for the layout.

Every diagram, the sightline/timing analysis and data/showhome_layout.json are generated from this file,
so the numbers in MAP_DESIGN.md stay consistent. A later Blender blockout script can read the JSON.

Coordinates (metres): x = east (0..72), y = north (0..48), z = up. Origin = south-west map corner.
Blender uses the same axes (Z-up). glTF / Bevy (Y-up): bevy = (x, z, -y), so map north = Bevy -Z (forward).
The map is MIRROR-symmetric about x = 36. Elements with side "W" are defined once and mirrored to "E"
(Sage -> Clay). Side "C" elements sit on the axis and exist once.
"""
from dataclasses import dataclass, asdict, field
import copy
import math

MAP_W, MAP_H = 72.0, 48.0
AXIS_X = MAP_W / 2.0

# ---------------------------------------------------------------- movement / player assumptions
# Placeholder values. They MUST be aligned with the movement spec; the analysis re-runs from here.
MOVE = dict(
    sprint=6.5,          # m/s (brief)
    run=5.0,             # m/s, not sprinting
    crouch_walk=2.6,     # m/s
    slide_entry=8.5,     # m/s at slide start, decays over ~0.9 s
    slide_dist=5.5,      # m per slide
    jump_apex=1.1,       # m (feet rise)
    vault_max=1.2,       # m, quick vault over low cover (fences, sills)
    mantle_max=2.0,      # m, ledge height above feet that can be mantled
    jet_rise_max=5.5,    # m, max feet rise with jump + both jet bursts from a standing start
    jet_charges=2,
    jet_recharge_s=4.0,  # s per charge
    jet_ascent_speed=4.5,  # m/s average climb while thrusting (for timings)
    zipline_speed=11.0,  # m/s
    zipline_attach_s=0.3,
    stair_factor=0.85,   # sprint multiplier on stairs
)
PLAYER = dict(height=1.8, crouch_height=1.1, slide_height=0.9, eye=1.6, crouch_eye=0.95, radius=0.35)

Z = dict(
    GF=0.0, UF=3.2, UF_CEIL=6.0, EAVES=6.2, RIDGE=11.2,
    EYE=1.6, CHEST=1.2,
    CEIL_SOFT0=8.0, CEIL_SOFT1=9.0,   # jet thrust fades to zero between these heights (above street)
    CEIL_HARD=10.0,                   # invisible player-only ceiling collider
    KILL=-10.0,                       # kill plane below the map
)


# ---------------------------------------------------------------- data types
@dataclass
class El:
    """Axis-aligned solid / prop / zone piece. shape 'circle' uses the rect as its bounding square."""
    id: str
    name: str
    kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    z0: float = 0.0
    z1: float = 1.0
    side: str = "W"
    stand: bool = False      # top surface is a standable surface (perch / roof you can stand on)
    blocks: bool = True      # solid for line-of-sight + bullets
    shape: str = "rect"
    kit: str = ""
    note: str = ""

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    @property
    def r(self):
        return (self.x1 - self.x0) / 2


@dataclass
class Opening:
    """Door / window in a wall. wall='x' -> wall at constant x=c, spanning y in [a0,a1];
    wall='y' -> wall at constant y=c, spanning x in [a0,a1]. z0/z1 absolute (sill / head)."""
    id: str
    kind: str        # door | door2 | roller | window | clerestory | shutter
    wall: str
    c: float
    a0: float
    a1: float
    z0: float
    z1: float
    floor: str       # GF | UF | -
    side: str = "W"
    note: str = ""


@dataclass
class Wall:
    id: str
    x0: float
    y0: float
    x1: float
    y1: float
    z0: float
    z1: float
    t: float
    kind: str        # ext | int | parapet | screen
    floor: str
    side: str = "W"


# ---------------------------------------------------------------- West half + centre (source data)
def _west_and_centre():
    E = []
    a = E.append
    # --- boundary (OOB beyond; an invisible player-only blocker runs up to the hard ceiling)
    a(El("W_HEDGE", "Boundary hedge", "boundary", 0, 1, 1, 47, 0, 3.0, "W", kit="HEDGE_BOUNDARY_4m"))
    a(El("C_NWALL", "North acoustic fence", "boundary", 0, 47, 72, 48, 0, 2.4, "C", kit="BOUNDARY_FENCE_4m"))
    a(El("C_SWALL", "South boundary wall", "boundary", 0, 0, 72, 1, 0, 2.4, "C", kit="BOUNDARY_FENCE_4m"))
    # --- spawn yard enclosure (garden walls 2.6 m, gates at the far-west corners)
    a(El("W_YARD_N", "Yard wall N", "garden_wall", 3.5, 35.85, 9.15, 36.15, 0, 2.6, kit="GARDEN_WALL_2m"))
    a(El("W_YARD_S", "Yard wall S", "garden_wall", 3.5, 11.85, 9.15, 12.15, 0, 2.6, kit="GARDEN_WALL_2m"))
    a(El("W_YARD_EN", "Yard wall NE stub", "garden_wall", 8.85, 32.0, 9.15, 35.85, 0, 2.6, kit="GARDEN_WALL_2m"))
    a(El("W_YARD_ES", "Yard wall SE stub", "garden_wall", 8.85, 12.15, 9.15, 16.0, 0, 2.6, kit="GARDEN_WALL_2m"))
    a(El("W_HOTTUB", "Hot-tub pod", "prop_low", 3.0, 28.0, 5.5, 30.5, 0, 1.0, kit="HOTTUB_2.5"))
    a(El("W_BBQ", "Outdoor-kitchen wall", "prop_full", 1.0, 23.0, 4.0, 24.0, 0, 2.2, kit="BOX_3x1x2.2",
         note="breaks the N-S line through both yard gates"))
    # --- Sage House (solid blocks for exterior analysis; interior detail in walls/openings below)
    a(El("W_HOUSE_MAIN", "Sage House", "house", 9, 22, 21, 32, 0, Z["EAVES"], kit="(walls)",
         note="2 floors, gable roof ridge E-W at y=27, eaves 6.2, ridge 11.2 (45 deg, not standable)"))
    a(El("W_HOUSE_GARAGE", "Sage Garage", "house", 9, 16, 21, 22, 0, Z["UF"], kit="(walls)",
         note="single storey; its roof is the Sage Terrace at z 3.2"))
    a(El("W_TERRACE", "Sage Terrace", "terrace", 9, 16, 21, 22, Z["UF"] - 0.25, Z["UF"], stand=True, blocks=False,
         kit="FLOOR_4x4", note="reached from the UF landing door, or by jetpack"))
    a(El("W_HEATPUMP", "Heat pump", "prop_low", 18.5, 20.7, 20.5, 21.7, Z["UF"], Z["UF"] + 1.2, kit="BOX_2x1x1.2"))
    # interior props (GF)
    a(El("W_ISLAND", "Kitchen island", "prop_low", 10, 24, 12, 26.5, 0, 1.0, kit="COUNTER_2x2.5"))
    a(El("W_STAIR", "Stairs", "stair", 13.8, 25.5, 15.0, 30.5, 0, Z["UF"], kit="STAIR_1.2x5",
         note="bottom at y=30.5 (GF), top at y=25.5 (UF); 18 risers x 0.178 m"))
    a(El("W_GARAGE_CAR", "Garage e-car", "prop_low", 12.6, 16.6, 14.5, 21.0, 0, 1.5, kit="CAR_COMPACT"))
    a(El("W_WORKBENCH", "Workbench", "prop_low", 9.3, 17.0, 10.0, 21.0, 0, 1.0, kit="BOX_0.7x4x1"))
    a(El("W_SHELF", "Shelving", "prop_full", 16.0, 21.3, 20.0, 21.85, 0, 2.2, kit="SHELF_4m"))
    a(El("W_SOFA", "Sofa", "prop_low", 16.5, 28.6, 19.0, 29.5, 0, 0.8, kit="SOFA_2.5"))
    a(El("W_DRESSER", "Dresser", "prop_low", 15.2, 26.0, 15.8, 28.0, Z["UF"], Z["UF"] + 1.2, kit="BOX_0.6x2x1.2"))
    # --- front lawn
    a(El("W_FENCE_FS", "Picket fence", "fence", 27.35, 14.4, 27.65, 25.0, 0, 1.2, kit="FENCE_1.2_2m"))
    a(El("W_FENCE_FN", "Picket fence", "fence", 27.35, 27.0, 27.65, 32.0, 0, 1.2, kit="FENCE_1.2_2m"))
    a(El("W_HEDGE_LAWN", "Lawn hedge", "prop_full", 23.0, 13.6, 28.2, 14.4, 0, 2.0, kit="HEDGE_2m",
         note="closes the lawn from the drive (gap x 21-23 by the garage); breaks N-S and diagonal lines"))
    a(El("W_PLANTER_1", "Lawn planter", "prop_low", 23, 18.5, 26, 19.5, 0, 1.0, kit="PLANTER_3x1"))
    a(El("W_PLANTER_2", "Lawn planter", "prop_low", 23, 29.0, 26, 30.0, 0, 1.0, kit="PLANTER_3x1"))
    # --- patio + garden (north lane)
    a(El("W_GREENHOUSE", "Sage Greenhouse", "building", 21, 32, 26.5, 36, 0, 2.8, kit="GREENHOUSE_POD_5.5x4",
         note="enterable through-room: doors W (patio), N (garden), S (lawn); frosted, opaque; dome not standable"))
    a(El("W_TANK", "Sage Tank", "prop_full", 13.5 - 1.6, 37.5 - 1.6, 13.5 + 1.6, 37.5 + 1.6, 0, 2.8, shape="circle",
         kit="TANK_D3.2", note="rain-water tank; ends the Long Garden sightline"))
    a(El("W_SHED", "Sage Shed", "building", 17, 43, 21, 47, 0, 2.6, kit="SHED_4x4", note="closed; pitched roof"))
    a(El("W_BEDS_1", "Veg beds", "prop_low", 3, 39.5, 7, 40.5, 0, 1.0, kit="PLANTER_4x1"))
    a(El("W_ARBOUR", "Sage Arbour", "prop_full", 8, 39, 11, 45, 0, 2.4, kit="ARBOUR_3x6",
         note="vine-covered trellis arbour, sight-blocking; shields the garden spawn zone from diagonals"))
    a(El("W_BEDS_3", "Veg beds", "prop_low", 22, 39.5, 25, 40.5, 0, 1.0, kit="PLANTER_3x1"))
    a(El("W_PYLON_MAST", "Pylon mast", "mast", 24.75, 45.25, 25.25, 45.75, 0, 6.6, shape="circle", kit="PYLON"))
    a(El("W_PYLON_PAD", "Sage Pylon pad", "perch", 24, 44.5, 26, 46.5, 3.85, 4.0, stand=True, blocks=False,
         kit="PYLON", note="jetpack-only perch + zipline anchor; open grating, 0.3 m toe board, no hard cover"))
    # --- drive (south lane)
    a(El("W_LOWWALL", "Low wall", "prop_low", 3.5, 8.0, 8.0, 8.5, 0, 1.0, kit="LOW_WALL_1m"))
    a(El("W_BINS", "Sage Bins", "prop_full", 12, 4, 15, 10, 0, 2.2, kit="BIN_STORE_3x6", note="lids sloped, not standable"))
    a(El("W_STUDIO", "Sage Studio", "building", 20, 1, 26, 6, 0, 2.8, kit="STUDIO_POD_6x5",
         note="enterable garden office: doors N + E, window N; sloped roof"))
    a(El("W_LOCKERS", "Sage Lockers", "prop_full", 28.2, 10, 30.2, 18, 0, 2.2, kit="PARCEL_LOCKER_2x2",
         note="parcel-locker bank on the sidewalk"))
    # --- street (mid)
    a(El("W_KERBPOD", "Sage Pod", "vehicle", 29.8, 30.5, 31.8, 34.1, 0, 2.2, kit="DELIVERY_POD",
         note="parked autonomous delivery pod; rounded roof, not standable"))
    a(El("W_ARMCHAIR", "Armchair", "prop_low", 33.2, 22.0, 34.4, 23.2, 0, 0.8, kit="ARMCHAIR"))
    a(El("W_CRATE", "Crate", "prop_low", 33.0, 20.2, 34.0, 21.2, 0, 1.0, kit="CRATE_1m"))
    a(El("C_MOVER_BOX", "Mover", "vehicle", 34.75, 19.0, 37.25, 27.0, 0, 3.2, "C", stand=True, kit="MOVER_TRUCK",
         note="driverless removal truck; side skirts closed to 0.2 m; box top = jetpack-only perch"))
    a(El("C_MOVER_CAB", "Cab", "vehicle", 34.85, 27.0, 37.15, 29.5, 0, 2.4, "C", stand=True, kit="MOVER_TRUCK"))
    a(El("C_CHARGER", "Charger", "prop_full", 35.0, 31.0, 37.0, 35.0, 0, 2.4, "C", kit="CHARGER_ISLAND_2x3",
         note="kerbside e-charger island north of the cab; breaks cross-map diagonals; top not standable"))
    a(El("C_CRATE_T", "Crate", "prop_low", 35.5, 16.6, 36.5, 17.6, 0, 1.0, "C", kit="CRATE_1m"))
    a(El("C_HUB", "Hub", "building", 34, 39, 38, 44, 0, 3.0, "C", kit="POSTLINE_HUB_4x5",
         note="parcel hub kiosk in the turning circle; dome top 3.6, not standable"))
    a(El("C_OFFICE", "Office", "building", 30, 1, 42, 8, 0, 3.0, "C", stand=True, kit="SALES_OFFICE_12x7",
         note="showhome sales office: shutters W+E (slide gap 1.1 m), 2 street windows; flat roof = perch"))
    a(El("C_MODEL", "Model table", "prop_low", 34, 3, 38, 5, 0, 1.0, "C", kit="TABLE_4x2",
         note="scale model of the development; pickup PK-S"))
    a(El("C_SHUTTLE", "Shuttle", "prop_full", 34, 8, 38, 10, 0, 2.6, "C", kit="SHUTTLE_STOP_4x2",
         note="shuttle stop shelter against the office front; roof sloped"))
    return E


def _west_walls_and_openings():
    W, O = [], []
    uf, gf = Z["UF"], Z["GF"]
    t = 0.3
    # GF exterior + garage partition
    W += [Wall("W_GF_S", 9, 16, 21, 16, gf, uf, t, "ext", "GF"),
          Wall("W_GF_E", 21, 16, 21, 32, gf, uf, t, "ext", "GF"),
          Wall("W_GF_N", 9, 32, 21, 32, gf, uf, t, "ext", "GF"),
          Wall("W_GF_W", 9, 16, 9, 32, gf, uf, t, "ext", "GF"),
          Wall("W_GF_P", 9, 22, 21, 22, gf, uf, 0.2, "int", "GF")]
    # UF exterior + partition
    W += [Wall("W_UF_S", 9, 22, 21, 22, uf, Z["EAVES"], t, "ext", "UF"),
          Wall("W_UF_E", 21, 22, 21, 32, uf, Z["EAVES"], t, "ext", "UF"),
          Wall("W_UF_N", 9, 32, 21, 32, uf, Z["EAVES"], t, "ext", "UF"),
          Wall("W_UF_W", 9, 22, 9, 32, uf, Z["EAVES"], t, "ext", "UF"),
          Wall("W_UF_P", 15, 22, 15, 32, uf, Z["UF_CEIL"], 0.2, "int", "UF")]
    # terrace edge: parapet 1.0 m (45 deg coping, not standable) + privacy screen 2.4 m on the spawn side
    W += [Wall("W_TER_PS", 11, 16, 21, 16, uf, uf + 1.0, 0.25, "parapet", "UF"),
          Wall("W_TER_PE", 21, 16, 21, 22, uf, uf + 1.0, 0.25, "parapet", "UF"),
          Wall("W_TER_SW", 9, 16, 9, 22, uf, uf + 2.4, 0.25, "screen", "UF"),
          Wall("W_TER_SS", 9, 16, 11, 16, uf, uf + 2.4, 0.25, "screen", "UF")]
    # GF openings
    O += [Opening("W_GF_ROLLER", "roller", "y", 16, 12, 16, 0, 1.1, "GF",
                  note="roller door jammed half-open: 1.1 m gap, crouch or slide under"),
          Opening("W_GF_GARWIN", "window", "x", 21, 18.2, 19.8, 0.9, 2.1, "GF", note="vaultable"),
          Opening("W_GF_FRONT", "door2", "x", 21, 25, 27, 0, 2.4, "GF", note="front door, double"),
          Opening("W_GF_LIVWIN", "window", "x", 21, 29, 30.6, 0.9, 2.1, "GF", note="vaultable"),
          Opening("W_GF_PATIO", "door2", "y", 32, 17, 19, 0, 2.4, "GF", note="sliding patio door"),
          Opening("W_GF_KITWIN", "window", "y", 32, 10, 11.6, 0.9, 2.1, "GF", note="vaultable"),
          Opening("W_GF_BACK", "door", "x", 9, 29, 30, 0, 2.1, "GF", note="back door to spawn yard"),
          Opening("W_GF_GARDOOR", "door", "y", 22, 10, 11, 0, 2.1, "GF", note="garage <-> kitchen")]
    # UF openings
    O += [Opening("W_UF_TERDOOR", "door", "y", 22, 10.5, 11.5, uf, uf + 2.1, "UF", note="landing -> terrace"),
          Opening("W_UF_WIN_S", "window", "x", 21, 23.4, 25.0, uf + 1.0, uf + 2.2, "UF", note="street window S"),
          Opening("W_UF_WIN_N", "window", "x", 21, 28.6, 30.2, uf + 1.0, uf + 2.2, "UF", note="street window N"),
          Opening("W_UF_WIN_NF", "window", "y", 32, 17.4, 19.0, uf + 1.0, uf + 2.2, "UF", note="garden window"),
          Opening("W_UF_WIN_T", "window", "y", 22, 17.4, 19.0, uf + 1.0, uf + 2.2, "UF",
                  note="onto terrace, vaultable"),
          Opening("W_UF_CLR_W1", "clerestory", "x", 9, 26.0, 27.6, uf + 1.8, uf + 2.4, "UF",
                  note="sill above eye height: no LOS into spawn"),
          Opening("W_UF_CLR_W2", "clerestory", "x", 9, 29.4, 31.0, uf + 1.8, uf + 2.4, "UF"),
          Opening("W_UF_CLR_N", "clerestory", "y", 32, 10, 11.6, uf + 1.8, uf + 2.4, "UF"),
          Opening("W_UF_PD1", "door", "x", 15, 23, 24, uf, uf + 2.1, "UF", note="landing -> front room"),
          Opening("W_UF_PD2", "door", "x", 15, 30.8, 31.8, uf, uf + 2.1, "UF", note="landing -> front room")]
    # other small buildings (drawn on the main map; no interior walls needed)
    O += [Opening("W_GH_W", "door", "x", 21, 34.2, 35.4, 0, 2.1, "-", note="greenhouse <-> patio"),
          Opening("W_GH_N", "door", "y", 36, 23.0, 24.2, 0, 2.1, "-", note="greenhouse <-> garden"),
          Opening("W_GH_S", "door", "y", 32, 24.6, 25.8, 0, 2.1, "-", note="greenhouse <-> lawn"),
          Opening("W_ST_N", "door", "y", 6, 21, 22, 0, 2.1, "-", note="studio door"),
          Opening("W_ST_E", "door", "x", 26, 3, 4, 0, 2.1, "-", note="studio door to alley"),
          Opening("W_ST_WIN", "window", "y", 6, 23.4, 25.0, 0.9, 2.1, "-", note="studio window"),
          Opening("W_OF_W", "shutter", "x", 30, 3, 4.2, 0, 1.1, "-", note="office shutter half-open: slide gap 1.1 m"),
          Opening("W_OF_WIN", "window", "y", 8, 31.5, 33.5, 0.9, 2.1, "-", note="office street window")]
    return W, O


# ---------------------------------------------------------------- gameplay markers (west side, mirrored)
SPAWNS_W = [  # id, x, y, yaw_deg (0 = facing +x / east), zone
    ("W_YARD_1", 2.5, 15.0, 0, "W_YARD"), ("W_YARD_2", 6.5, 15.5, 0, "W_YARD"),
    ("W_YARD_3", 4.5, 19.5, 0, "W_YARD"), ("W_YARD_4", 2.5, 26.5, 0, "W_YARD"),
    ("W_YARD_5", 6.5, 25.5, 0, "W_YARD"), ("W_YARD_6", 4.5, 33.0, 0, "W_YARD"),
    ("W_GARDEN_1", 2.5, 42.0, 0, "W_GARDEN"), ("W_GARDEN_2", 5.5, 42.0, 0, "W_GARDEN"),
    ("W_GARDEN_3", 2.5, 45.5, 0, "W_GARDEN"), ("W_GARDEN_4", 6.0, 45.5, 0, "W_GARDEN"),
    ("W_DRIVE_1", 2.5, 2.5, 0, "W_DRIVE"), ("W_DRIVE_2", 6.0, 2.5, 0, "W_DRIVE"),
    ("W_DRIVE_3", 2.5, 6.0, 0, "W_DRIVE"), ("W_DRIVE_4", 6.0, 5.5, 0, "W_DRIVE"),
]
SPAWN_ZONES_W = {  # rects x0, y0, x1, y1
    "W_YARD": (1.4, 12.4, 8.6, 35.6),
    "W_GARDEN": (1.4, 41.0, 7.6, 46.6),
    "W_DRIVE": (1.4, 1.4, 8.6, 7.6),
}

PICKUPS = [  # id, name, x, y, z, respawn_s, note
    ("PK_C", "Overcharge cell", 36.0, 23.0, 3.2, 90, "on Mover Top (jetpack-only); optional, see open questions"),
    ("PK_S", "Shield cell", 36.0, 4.0, 1.0, 30, "on the office model table"),
    ("PK_N", "Shield cell", 36.0, 45.5, 0.0, 30, "turning circle, under the zipline"),
]

ZIPLINE = dict(id="ZL_POSTLINE", name="Postline", a=(25.0, 45.5, 6.3), b=(47.0, 45.5, 6.3), sag=0.8,
               note="bidirectional; attach from either pad or mid-air (jetpack); detach any time")

PERCHES = [  # id, name, element id, top z, access
    ("J_MOVER", "Mover Top", "C_MOVER_BOX", 3.2, "jetpack only (cab roof 2.4 m, no climbable prop within 2.5 m)"),
    ("J_OFFICE", "Office Roof", "C_OFFICE", 3.0, "jetpack only"),
    ("J_PAD_W", "Sage Pylon pad", "W_PYLON_PAD", 4.0, "jetpack only (or zipline from the other pad)"),
    ("J_PAD_E", "Clay Pylon pad", "E_PYLON_PAD", 4.0, "jetpack only (or zipline from the other pad)"),
]

CALLOUTS_W = [  # name, x, y, level ('G' ground / 'U' upper)
    ("Sage Yard", 5.0, 22.0, "G"), ("Sage N Gate", 2.3, 37.3, "G"), ("Sage S Gate", 2.3, 10.7, "G"),
    ("Sage Garage", 17.5, 18.5, "G"), ("Sage Kitchen", 11.0, 30.6, "G"), ("Sage Living", 18.0, 25.3, "G"),
    ("Sage Terrace", 15.0, 19.0, "U"), ("Sage Landing", 11.5, 27.0, "U"), ("Sage Front", 18.0, 27.0, "U"),
    ("Sage Patio", 15.5, 34.0, "G"), ("Sage Greenhouse", 23.75, 34.0, "G"), ("Sage Tank", 13.5, 37.5, "G"),
    ("Sage Beds", 5.0, 40.0, "G"), ("Sage Arbour", 9.5, 42.0, "G"), ("Sage Shed", 19.0, 45.0, "G"), ("Sage Pylon", 25.0, 45.5, "U"),
    ("Sage Lawn", 24.5, 23.0, "G"), ("Sage Drive", 18.0, 12.5, "G"), ("Sage Bins", 13.5, 7.0, "G"),
    ("Sage Studio", 23.0, 3.5, "G"), ("Sage Alley", 28.0, 3.5, "G"), ("Sage Lockers", 29.2, 13.0, "G"),
    ("Sage Gap", 29.2, 9.0, "G"), ("Sage Pod", 30.8, 32.3, "G"),
]
CALLOUTS_C = [
    ("Mover", 36.0, 23.0, "G"), ("Cab", 36.0, 28.25, "G"), ("Tail", 36.0, 17.1, "G"),
    ("Hub", 36.0, 41.5, "G"), ("North Cross", 36.0, 45.8, "G"), ("Office", 36.0, 6.0, "G"),
    ("Shuttle", 36.0, 9.0, "G"), ("Street", 36.0, 13.0, "G"), ("Charger", 36.0, 33.0, "G"), ("Long Garden", 36.0, 37.4, "G"),
]

# Named sightlines (3D endpoints, eye heights). Lengths are computed and verified by build_diagrams.py.
SIGHTLINES = [
    ("SL_LONG_GARDEN", "Long Garden", (15.2, 37.5, 1.6), (56.8, 37.5, 1.6), "N lane sniper line (Warden)"),
    ("SL_STREET_LONG", "Street Long", (32.9, 8.3, 1.6), (32.9, 46.7, 1.6), "mid N-S crossing watch (Warden)"),
    ("SL_WINDOW_DUEL", "Window Duel", (21.2, 24.2, 4.8), (50.8, 24.2, 4.8), "UF street windows, over the Mover"),
    ("SL_TERRACE_DUEL", "Terrace Duel", (20.7, 18.0, 4.8), (51.3, 18.0, 4.8), "terrace parapet to parapet"),
    ("SL_TAIL", "Tail Line", (21.4, 18.0, 1.6), (50.6, 18.0, 1.6), "garage windows, past the Mover tail"),
    ("SL_PYLON", "Pylon Duel", (25.6, 45.5, 5.6), (46.4, 45.5, 5.6), "pad to pad along the zipline"),
    ("SL_OFFICE_ROOF", "Office Roof", (32.5, 7.6, 4.6), (32.5, 46.5, 1.6), "roof perch down the street"),
    ("SL_GARDEN_WIN", "Garden Window", (18.2, 32.25, 4.8), (46.4, 45.0, 5.6), "UF garden window to enemy pad"),
]

# Routes for the WEST team (east is mirrored). 'STAIR' marks the next segment as a stair (slower).
# 'JET:<m>' adds a jetpack climb of <m> metres; 'ZIP:<m>' adds a zipline ride of <m> metres.
ROUTES_W = [
    ("R_MID", "Spawn -> Mover via house (back door, kitchen, front door)",
     [(5, 24), (8.5, 29.5), (9.6, 29.5), (13.4, 25.0), (21.0, 26.0), (27.5, 26.0), (34.3, 24.0)]),
    ("R_UFWIN", "Spawn -> own UF street window (stairs)",
     [(5, 24), (8.5, 29.5), (9.6, 29.5), (14.4, 31.3), "STAIR", (14.4, 25.2), (15.0, 23.5), (20.6, 24.2)]),
    ("R_TERRACE", "Spawn -> own Terrace east parapet",
     [(5, 24), (8.5, 29.5), (9.6, 29.5), (14.4, 31.3), "STAIR", (14.4, 25.2), (11.0, 22.6), (11.0, 21.5),
      (20.4, 18.5)]),
    ("R_NORTH", "Spawn -> North crossing (Long Garden band) via N Gate",
     [(5, 24), (2.3, 35.5), (2.6, 37.4), (11.0, 39.5), (15.6, 39.5), (36.0, 37.5)]),
    ("R_ZIP", "Spawn -> enemy pad via jetpack + Postline zipline",
     [(5, 24), (2.3, 35.5), (2.6, 37.4), (11.0, 39.5), (15.6, 39.6), (24.0, 44.0), "JET:4.0", (25.0, 45.5),
      "ZIP:22.0", (47.0, 45.5)]),
    ("R_SOUTH", "Spawn -> Office (model table) via S Gate, alley, shutter",
     [(5, 24), (2.3, 12.5), (2.6, 11.0), (9.0, 10.5), (16.5, 10.5), (27.2, 7.0), (29.4, 3.6), (30.6, 3.6),
      (33.5, 6.0), (36.0, 6.0)]),
    ("R_GAP", "Spawn -> Shuttle (south street) via Sage Gap",
     [(5, 24), (2.3, 12.5), (2.6, 11.0), (9.0, 10.5), (16.5, 10.5), (27.6, 9.0), (33.6, 9.0)]),
    ("R_OFFICE_ROOF", "Spawn -> Office Roof (jetpack from the alley)",
     [(5, 24), (2.3, 12.5), (2.6, 11.0), (9.0, 10.5), (16.5, 10.5), (27.2, 7.0), (29.3, 5.0), "JET:3.0",
      (31.0, 5.0)]),
]

SECTIONS = [  # id, axis ('y' = E-W cut at y=c, 'x' = N-S cut at x=c), c
    ("A", "y", 26.0, "E-W through both houses, front doors and the Mover"),
    ("B", "y", 45.5, "E-W through gardens, sheds, pylons and the zipline"),
    ("C", "x", 36.0, "N-S through the Office, Shuttle, Mover and Hub (map axis)"),
    ("D", "x", 14.4, "N-S through Sage drive, garage roller door, stairs, patio and tank"),
]


# ---------------------------------------------------------------- mirroring + assembly
def _mx(x):
    return MAP_W - x


def _mid(s):
    return s.replace("W_", "E_", 1) if s.startswith("W_") else s


def _mname(s):
    return s.replace("Sage", "Clay")


def mirror_el(e):
    m = copy.copy(e)
    m.id, m.name, m.side = _mid(e.id), _mname(e.name), "E"
    m.x0, m.x1 = _mx(e.x1), _mx(e.x0)
    return m


def mirror_wall(w):
    m = copy.copy(w)
    m.id, m.side = _mid(w.id), "E"
    m.x0, m.x1 = _mx(w.x0), _mx(w.x1)
    return m


def mirror_opening(o):
    m = copy.copy(o)
    m.id, m.side = _mid(o.id), "E"
    if o.wall == "x":
        m.c = _mx(o.c)
    else:
        m.a0, m.a1 = _mx(o.a1), _mx(o.a0)
    return m


def build():
    els = _west_and_centre()
    els += [mirror_el(e) for e in els if e.side == "W"]
    walls, opens = _west_walls_and_openings()
    walls += [mirror_wall(w) for w in walls]
    opens += [mirror_opening(o) for o in opens]
    spawns = [dict(id=s[0], x=s[1], y=s[2], yaw=s[3], zone=s[4], team_side="W") for s in SPAWNS_W]
    spawns += [dict(id=_mid(s[0]), x=_mx(s[1]), y=s[2], yaw=180, zone=_mid(s[4]), team_side="E") for s in SPAWNS_W]
    zones = dict(SPAWN_ZONES_W)
    zones.update({_mid(k): (_mx(v[2]), v[1], _mx(v[0]), v[3]) for k, v in SPAWN_ZONES_W.items()})
    callouts = [dict(name=c[0], x=c[1], y=c[2], level=c[3]) for c in CALLOUTS_W]
    callouts += [dict(name=_mname(c[0]), x=_mx(c[1]), y=c[2], level=c[3]) for c in CALLOUTS_W]
    callouts += [dict(name=c[0], x=c[1], y=c[2], level=c[3]) for c in CALLOUTS_C]
    return dict(elements=els, walls=walls, openings=opens, spawns=spawns, spawn_zones=zones,
                callouts=callouts, pickups=PICKUPS, zipline=ZIPLINE, perches=PERCHES,
                sightlines=SIGHTLINES, routes=ROUTES_W, sections=SECTIONS)


def el_by_id(L, i):
    for e in L["elements"]:
        if e.id == i:
            return e
    raise KeyError(i)


def to_jsonable(L):
    out = {}
    for k, v in L.items():
        if isinstance(v, list) and v and hasattr(v[0], "__dataclass_fields__"):
            out[k] = [asdict(x) for x in v]
        else:
            out[k] = v
    return out
