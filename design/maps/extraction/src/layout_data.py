"""EXTRACTION MAP (working title open) - single source of truth for the layout diagram and LAYOUT.md tables.

Frame (same as Showhome and the range): metres, x = east, y = north, z = up, origin = south-west corner of the
playable rect. Bevy: bevy = (x, z, -y), so map north = Bevy -Z. Playable rect: x 0..1300, y 0..1100.

v0.2 (2026-10-09): the map grew from 1000 x 900 m to 1300 x 1100 m. It was NOT stretched uniformly:
- every POI is a rigid GROUP: its footprint and inner layout keep their v0.1 size and shape and only move
  (GROUP_OFFSET, applied to the v0.1 coordinates, which are kept below as the authoring coordinates);
- the land between the POIs (the river's course, the highway, roads, fields, woods) is scaled by MAP_SCALE, so the
  extra space becomes open fields, hedgerows and woods between the POIs, and wider approaches;
- widths are constants and do not scale: the river (40 m), the highway (deck 34 m, slopes 12 m), the roads;
- the plant and the sluice house are offset so they keep their exact relation to the river and the weir.

Everything here is a DIAGRAM-level proposal: zones and rough points. Exact spawn points, extracts, loot spots and
invisible walls are set later by the user in the in-game build mode (art/briefs/showhome_rebuild/02_BUILD_MODE.md).
"""
import geom as G

MAP_W, MAP_H = 1300.0, 1100.0
GRID = 50.0

# ------------------------------------------------------------------ v0.1 -> v0.2 placement
MAP_SCALE = (1.3, 1100.0 / 900.0)          # land between the POIs (v0.1 coordinates -> v0.2)
GROUP_OFFSET = {                           # rigid moves of the POI groups (v0.1 coordinates + offset)
    "WS": (80.0, 120.0),     # Showhome + worksite (and the TDM cut-out, the inset)
    "FARM": (60.0, 70.0),
    "HUT": (60.0, 175.0),
    "CP": (212.0, 102.0),    # container park: its gate lines up with the plant road (a crossroads on the Old Road)
    "PLANT": (142.0, 57.0),  # keeps the pump house and the weir where they were relative to the river
    "SUB": (267.0, 35.0),
    "STO": (265.0, 150.0),
    "GAS": (285.0, 106.0),
    "SLU": (166.0, 0.0),     # keeps the sluice house on the east bank at the dike
}


def P(g, x, y):
    """A v0.1 point of group g in v0.2 coordinates. g = 'MAP' scales; 'ABS' is already v0.2."""
    if g == "ABS":
        return (float(x), float(y))
    if g == "MAP":
        return (x * MAP_SCALE[0], y * MAP_SCALE[1])
    dx, dy = GROUP_OFFSET[g]
    return (x + dx, y + dy)


def Ps(g, pts):
    return [P(g, x, y) for x, y in pts]


def R(g, x0, y0, x1, y1):
    """A v0.1 rect of group g (rigid groups keep their size)."""
    a, b = P(g, x0, y0), P(g, x1, y1)
    return (a[0], a[1], b[0], b[1])


def C(g, cx, cy, r):
    a = P(g, cx, cy)
    return (a[0], a[1], r)


# ------------------------------------------------------------------ movement (game/assets/data/movement.ron, armor.ron)
SPEED = dict(walk=2.6, jog=4.8, sprint=7.0)          # m/s, no / Light halo. Sprint is the default (DIRECTION_LOG 16).
WEIGHT_MOVE = dict(Light=1.0, Medium=0.95, Heavy=0.88)
ROUTE_FACTOR = 1.12        # straight line → real on-foot route (fences, hedges, buildings, small detours)
CLIMB_PENALTY_S = dict(embankment=4.0, cutting=6.0)  # extra seconds to scramble onto / off the highway deck

# ------------------------------------------------------------------ the river (flows north → south)
RIVER_PTS = Ps("MAP", [(470, 940), (468, 900), (458, 850), (444, 800), (434, 750), (432, 700), (444, 650),
                       (466, 600), (490, 550), (506, 500), (510, 460), (504, 410), (490, 360), (476, 310),
                       (472, 260), (480, 210), (498, 160), (522, 110), (544, 60), (556, 0), (560, -40)])
RIVER_HALF_W = 20.0        # 40 m of water: wider than a full jetpack hop (~25-30 m), see LAYOUT.md
RIVER_BANK_W = 5.0         # riprap / sheet-pile bank strip on each side
TOWPATH_OFF = 30.0         # towpath centre from the river centre line


def river_line():
    return G.catmull_rom(RIVER_PTS, samples=14)


# ------------------------------------------------------------------ the highway (E-road, 2x3 lanes)
HIGHWAY_PTS = Ps("MAP", [(632, 960), (646, 880), (674, 800), (710, 720), (750, 640), (795, 560), (845, 480),
                         (898, 400), (948, 330), (1000, 270), (1050, 215)])
HW_DECK_HALF = 17.0        # deck incl. hard shoulders and the median barrier
HW_SLOPE_W = 12.0          # embankment / cutting slope on each side (about 27 deg for 6 m)
HW_CUT_ABOVE_Y = 650.0 * MAP_SCALE[1]     # north of this: a cutting (-6 m)
HW_EMB_BELOW_Y = 615.0 * MAP_SCALE[1]     # south of this: an embankment (+6 m); at grade in between
HW_GANTRY_Y = [1020.0, 731.0, 455.0]
HW_LORRY_Y = 635.0          # the jackknifed lorry on the embankment deck


def highway_line():
    return G.catmull_rom(HIGHWAY_PTS, samples=14)


# ------------------------------------------------------------------ roads and paths (polylines, v0.2 coordinates)
# kind: main (Old Road, 9 m), street (6.5 m), gravel (4 m), field (dashed path), cover (dotted, concealed route)
ROADS = [
    dict(id="OLD_ROAD", kind="main", smooth=True, name="Old Road (former national road)",
         pts=Ps("MAP", [(-40, 392), (0, 395), (100, 403), (200, 418), (300, 437), (400, 452), (460, 460), (484, 462),
                        (536, 462), (600, 461), (680, 457), (760, 454), (830, 456), (860, 460), (900, 464),
                        (960, 468), (1000, 471), (1040, 474)])),
    dict(id="FRONT_ST", kind="street", smooth=True, name="Front street (Showhome, open in front)",
         pts=Ps("WS", [(172, 492), (250, 492), (330, 492), (392, 490)])
         + [(520, 603), (566, 584), (590, 568), P("MAP", 460, 460)]),
    dict(id="CENTRAL_ST", kind="street", smooth=False, name="Central street (truck)",
         pts=Ps("WS", [(290, 492), (290, 551)])),
    dict(id="SITE_RD_W", kind="gravel", smooth=True, name="Site road (West Gate)",
         pts=Ps("WS", [(172, 492), (171, 452)]) + [(251, 512)]),
    dict(id="SITE_TRACK_W", kind="gravel", smooth=False, name="Site track", pts=Ps("WS", [(172, 492), (178, 568)])),
    dict(id="BACK_RD", kind="gravel", smooth=False, name="Back road (unfinished)",
         pts=Ps("WS", [(178, 568), (428, 568)])),
    dict(id="SITE_TRACK_N", kind="gravel", smooth=False, name="Track to the Shells",
         pts=Ps("WS", [(290, 568), (290, 590)])),
    dict(id="FOREST_TRACK", kind="gravel", smooth=True, name="Forest Track (Dirt Bridge + Overpass)",
         pts=Ps("MAP", [(345, 680), (378, 712), (404, 738), (433, 746), (466, 751), (530, 755), (600, 758),
                        (660, 760), (694, 760), (730, 760), (785, 752)]) + [P("STO", 818, 738)]),
    dict(id="FARM_LANE", kind="gravel", smooth=True, name="Farm lane",
         pts=[(268, 512), (262, 455), P("FARM", 202, 322)]),
    dict(id="CP_ACCESS", kind="street", smooth=False, name="Container park access",
         pts=[(857, 560), P("CP", 645, 486)]),
    dict(id="PLANT_RD", kind="street", smooth=False, name="Plant access road",
         pts=[(857, 556), P("PLANT", 715, 341)]),
    dict(id="STORAGE_RD", kind="street", smooth=True, name="Storage road",
         pts=[(1170, 568), (1158, 670), P("STO", 880, 613)]),
    dict(id="SUB_TRACK", kind="gravel", smooth=True, name="Substation service track",
         pts=[P("PLANT", 715, 365), (950, 385), (1060, 300), P("SUB", 872, 200)]),
    dict(id="PLANT_RING", kind="gravel", smooth=False, name="Plant internal road",
         pts=Ps("PLANT", [(715, 341), (715, 200), (552, 200)])),
    dict(id="FIELD_LANE_W", kind="gravel", smooth=True, name="Field lane (west fields)",
         pts=[(120, 497), (128, 600), (150, 700), P("WS", 172, 562)]),
    dict(id="PYLON_LANE", kind="gravel", smooth=True, name="Field lane (pylon field)",
         pts=[(990, 557), (1000, 470), (985, 330)]),
]

PATHS = [
    # cover routes (forest paths, poplar row): concealed movement
    dict(id="FP_SHELLS", kind="cover", pts=[P("WS", 300, 622), (412, 786), P("MAP", 345, 680)]),
    dict(id="FP_NORTH", kind="cover", pts=[(405, 1093), P("MAP", 302, 840), P("MAP", 296, 780), P("MAP", 318, 725),
                                           P("MAP", 345, 680)]),
    dict(id="FP_HUT", kind="cover", pts=[P("MAP", 296, 780), (320, 968), P("HUT", 205, 800), (156, 992), (52, 1002),
                                         (6, 1005)]),
    dict(id="FP_WEST", kind="cover", pts=[P("WS", 182, 656), (250, 860), P("HUT", 200, 790)]),
    dict(id="FP_RIVERSIDE", kind="cover", pts=[P("MAP", 560, 756), P("MAP", 548, 690), P("MAP", 560, 632),
                                               P("CP", 590, 580)]),
    dict(id="FP_NE", kind="cover", pts=[(1145, 1093), P("MAP", 872, 830), P("MAP", 852, 776), P("STO", 820, 740)]),
    dict(id="FP_SE", kind="cover", pts=[(1080, 14), (1056, 75), (1050, 150), P("SUB", 846, 158)]),
    dict(id="FP_WEST_WOODS", kind="cover", pts=[(14, 720), (29, 574), (26, 403), (31, 244), (39, 110), (125, 14)]),
    dict(id="FP_PLANTWOOD", kind="cover", pts=[(702, 552), (736, 513), (780, 483), (852, 470)]),
    # field paths
    dict(id="FD_FARM_WEIR", kind="field", pts=[P("FARM", 212, 285), (350, 345), (455, 328), (585, 316)]),
    dict(id="FD_FARM_SOUTH", kind="field", pts=[P("FARM", 185, 248), (292, 183), (340, 86), (375, 16)]),
    dict(id="FD_SOUTH_WOODS", kind="field", pts=[P("FARM", 150, 248), (163, 250), (146, 147), (125, 14)]),
    dict(id="FD_WESTFIELDS", kind="field", pts=[(14, 720), (70, 716), (150, 700)]),
    dict(id="FD_EMBANK", kind="field", pts=[P("CP", 706, 540), (980, 684), (1020, 720)]),
    dict(id="FD_EAST", kind="field", pts=[(1290, 740), (1215, 733), (1160, 690)]),
    dict(id="FD_DIKE_E", kind="field", pts=[P("SLU", 600, 40), (910, 42), (1030, 20)]),
    dict(id="FD_DIKE_W", kind="field", pts=[(125, 14), (250, 26), (375, 16)]),
    dict(id="FD_VERGE", kind="field", pts=[(470, 552), (500, 590), P("WS", 392, 490)]),
]

# ------------------------------------------------------------------ crossings (centres computed from the lines)
RIVER_CROSSINGS = [
    dict(id="C1", name="Dirt Bridge", road="FOREST_TRACK", deck_w=4.0,
         note="farm-track bridge, timber deck on old piers, 4 m wide; forest down to the water on both banks"),
    dict(id="C2", name="Road Bridge", road="OLD_ROAD", deck_w=13.0,
         note="concrete girder bridge, 13 m wide (2 lanes + footpaths), 1 m parapets, two wrecked cars; fully exposed"),
    dict(id="C3", name="Weir", road=None, y=P("PLANT", 0, 258)[1], deck_w=1.4,
         note="weir with 7 sluice gates and a 1.4 m railed service catwalk; single file, loud water, no cover"),
]
HIGHWAY_CROSSINGS = [
    dict(id="U1", name="Underpass", road="OLD_ROAD",
         note="Old Road passes under the embankment: ~40 m box tunnel under the deck, 2 lanes, centre pillars, dark"),
    dict(id="O1", name="Overpass", road="FOREST_TRACK",
         note="farm-access bridge over the cutting, 5 m wide, 1.1 m parapets; looks straight down the deck"),
]

# ------------------------------------------------------------------ land cover (v0.2 coordinates)
FORESTS = [
    dict(id="NORTH_WOODS", name="North Woods", bank=("W", 809, 1100, -28),
         pts_before=[(-39, 1137), (-39, 855)] + Ps("MAP", [(40, 690), (110, 702), (170, 690), (230, 674), (290, 682),
                                                         (345, 664), (400, 668)]),
         pts_after=[(588, 1137)]),
    dict(id="RIVERSIDE_WOODS", name="Riverside Woods", bank=("E", 745, 1100, 28),
         pts_before=[(832, 794), (760, 760), (676, 731)],
         pts_after=[(634, 1137), (796, 1137), (816, 1039), (835, 972), (858, 904), (881, 843)]),
    dict(id="WEST_WOODS", name="West Woods (boundary)",
         pts=[(-39, 0), (68, 0), (52, 49), (36, 171), (52, 284), (39, 403), (49, 501), (39, 636), (47, 782),
              (52, 843), (-39, 855)]),
    dict(id="SOUTH_WOODS", name="South Woods", pts=Ps("MAP", [(72, 70), (150, 58), (196, 96), (192, 174), (132, 200),
                                                             (76, 166)])),
    dict(id="POPLARS", name="Poplar row", ribbon=("W", 538, 49, -24, -40)),
    dict(id="PLANTWOOD", name="Plant woods",
         pts=[(702, 549), (848, 547), (850, 410), (760, 404), (694, 410), (686, 470)]),
    dict(id="PYLONWOOD", name="Pylon woods",
         pts=Ps("MAP", [(762, 40), (830, 34), (846, 110), (840, 214), (800, 252), (764, 200)])),
    dict(id="SE_WOOD", name="SE woods", pts=[(1149, 0), (1339, 0), (1339, 130), (1157, 127)]),
    dict(id="NE_WOOD", name="NE woods",
         pts=[(910, 1137), (1339, 1137), (1339, 944), (1235, 929), (1170, 946), (1098, 931), (1027, 961),
              (969, 992), (920, 1051)]),
    # v0.2 additions in the wider fields
    dict(id="COPSE_W", name="West copse", pts=[(150, 760), (196, 752), (214, 790), (190, 826), (150, 818)]),
    dict(id="COPSE_FARM", name="Farm copse", pts=[(400, 430), (450, 424), (470, 452), (446, 476), (404, 470)]),
    dict(id="COPSE_EAST", name="East copse", pts=[(1090, 430), (1150, 420), (1170, 458), (1130, 492), (1092, 478)]),
    dict(id="EAST_WOODS", name="East Woods", pts=[(1214, 546), (1339, 550), (1339, 372), (1300, 382), (1264, 426),
                                                  (1226, 492)]),
    dict(id="COPSE_NE", name="NE copse", pts=[(990, 860), (1030, 850), (1046, 884), (1018, 912), (988, 900)]),
]
CLEARINGS = [C("HUT", 200, 800, 22.0), (405, 1084, 18.0)]     # forester's hut, north-woods spawn clearing

FIELDS = [   # arable (striped); everything else is meadow / pasture
    dict(id="F_SW_A", pts=Ps("MAP", [(40, 30), (232, 30), (238, 238), (40, 232)]), stripe=60),
    dict(id="F_SW_B", pts=Ps("MAP", [(244, 30), (432, 30), (436, 162), (250, 158)]), stripe=-60),
    dict(id="F_SW_C", pts=Ps("MAP", [(240, 340), (428, 344), (436, 428), (236, 412)]), stripe=60),
    dict(id="F_W", pts=[(52, 520), (215, 530), (220, 590), (52, 586)], stripe=-60),
    dict(id="F_WN", pts=[(60, 640), (225, 646), (232, 740), (60, 744)], stripe=60),
    dict(id="F_SE", pts=Ps("MAP", [(600, 30), (760, 30), (760, 112), (600, 116)]), stripe=60),
    dict(id="F_NE", pts=[(1242, 684), (1300, 684), (1300, 929), (1242, 919)], stripe=-60),
    dict(id="F_MID_E", pts=[(915, 345), (1078, 330), (1084, 412), (915, 420)], stripe=-60),
    dict(id="F_VERGE", pts=[(540, 604), (608, 596), (606, 660), (540, 668)], stripe=60),
]
NURSERY = dict(x0=346, x1=499, y0=205, y1=393, row_dx=8.0, row_w=2.4)   # tree nursery rows (cover rhythm)

HEDGEROWS = [Ps("MAP", h) for h in [
    [(40, 474), (160, 480)], [(96, 505), (100, 660)], [(128, 600), (164, 640)], [(60, 380), (160, 386)],
    [(240, 352), (330, 362)], [(228, 60), (238, 150)], [(320, 152), (420, 160)], [(140, 52), (220, 48)],
    [(735, 482), (772, 598)], [(820, 560), (920, 566)], [(640, 58), (740, 60)], [(560, 590), (585, 600)],
    [(52, 250), (52, 330)],
]] + [
    # v0.2: cover rhythm in the wider fields
    [(60, 610), (215, 616)], [(232, 650), (240, 800)], [(70, 800), (140, 812)],
    [(300, 560), (430, 572)], [(530, 640), (556, 720)], [(590, 610), (600, 700)],
    [(70, 420), (200, 430)], [(230, 220), (330, 228)], [(80, 300), (170, 306)],
    [(520, 460), (590, 470)], [(510, 90), (520, 200)], [(380, 120), (470, 126)],
    [(910, 600), (930, 700)], [(700, 650), (780, 700)], [(660, 840), (720, 870)],
    [(930, 280), (1080, 290)], [(890, 230), (900, 160)], [(1000, 100), (1080, 96)],
    [(1180, 680), (1240, 690)], [(1230, 520), (1290, 510)], [(1220, 820), (1280, 840)],
    [(780, 190), (790, 120)], [(880, 450), (960, 440)],
    # v0.2 second pass (guided by the cover check)
    [(1110, 300), (1150, 370)], [(950, 362), (1030, 382)], [(1040, 500), (1080, 560)], [(1000, 578), (1080, 584)],
    [(990, 820), (1040, 900)], [(950, 760), (1010, 772)], [(1135, 600), (1140, 700)], [(1245, 700), (1250, 800)],
    [(1215, 262), (1290, 272)], [(1150, 330), (1196, 304)], [(540, 60), (600, 70)],
    [(560, 730), (575, 800)], [(330, 40), (420, 46)],
]
DITCHES = [
    [(52, 284), (195, 288), (341, 274), (494, 254), (600, 249)],               # SW drainage ditch to the river
    [(13, 469), (130, 480), (260, 497), (390, 521), (520, 539), (588, 549)],   # Old Road roadside ditch (south)
    [(99, 503), (98, 550), (96, 596)],
    [(700, 640), (800, 700), (880, 740)],                                      # east-bank meadow ditch
    [(905, 300), (1000, 250), (1090, 250)],                                    # pylon-field ditch
]
HAY = Ps("MAP", [(120, 548), (64, 612), (138, 648), (100, 300), (296, 112), (366, 82), (770, 528), (980, 640),
                 (690, 606), (412, 400), (310, 380), (60, 520), (630, 90), (720, 90), (930, 700)]) + [
    (180, 470), (320, 440), (540, 420), (420, 290), (250, 130), (470, 60), (150, 650), (90, 760), (330, 820),
    (520, 720), (620, 650), (760, 640), (980, 500), (1040, 380), (950, 180), (880, 60), (1250, 860), (1180, 720),
    # v0.2 second pass
    (1180, 340), (1010, 470), (920, 512), (1060, 530), (1050, 800), (960, 930), (1125, 622), (1270, 640),
    (1250, 300), (1232, 205), (1268, 232), (575, 130), (400, 52), (460, 30), (740, 110), (560, 760), (665, 700),
    (1100, 380), (1270, 470), (250, 40), (620, 20), (1000, 30), (1100, 120),
    (1265, 160), (738, 598), (1282, 880), (1272, 705), (1076, 335), (268, 452), (876, 122), (238, 566),
]

POWERLINE = Ps("MAP", [(850, 150), (760, 100), (640, 84), (498, 86), (370, 100), (240, 116), (110, 132), (-40, 150)])

# small field structures (v0.2): cover and L1 loot in the open fields
FIELD_STRUCTURES = [
    dict(id="FIELD_BARN_W", name="field barn", rect=(140, 690, 160, 700), style="bldg"),
    dict(id="HIGH_SEAT_S", name="high seat", rect=(268, 228, 271, 231), style="bldg"),
    dict(id="TRACTOR", name="tractor + trailer", rect=(440, 140, 456, 144), style="vehicle"),
    dict(id="PUMP_SHED", name="pump shed", rect=(512, 300, 520, 306), style="bldg"),
    dict(id="BUS_SHELTER", name="bus shelter", rect=(470, 556, 476, 558.5), style="low"),
    dict(id="CATTLE_SHELTER", name="cattle shelter", rect=(968, 640, 984, 648), style="canopy"),
    dict(id="FIELD_BARN_E", name="field barn", rect=(1010, 410, 1032, 420), style="bldg"),
    dict(id="CAMPER", name="camper van", rect=(1205, 770, 1212, 773), style="vehicle"),
    dict(id="BEEHIVES", name="beehives", rect=(722, 700, 734, 704), style="low"),
    dict(id="SHEEPFOLD", name="sheepfold", rect=(80, 240, 96, 252), style="canopy"),
    dict(id="STALLED_LORRY", name="stalled lorry", rect=(952, 555, 966, 558.5), style="vehicle", lab=(0, -16)),
    dict(id="WRECKED_CAR", name="wrecked car", rect=(1072, 561, 1077, 563.5), style="vehicle"),
    dict(id="MACHINE_SHED", name="machine shed", rect=(1000, 790, 1016, 800), style="bldg"),
    dict(id="PUMP_STATION", name="pumping station", rect=(1222, 214, 1232, 222), style="bldg"),
]

# ------------------------------------------------------------------ points of interest
# tier: loot tier L1 (low) .. L4 (highest). footprint: rect (x0, y0, x1, y1), circle or polygon (v0.2 coordinates).
POIS = [
    dict(id="SHOWHOME", name="Showhome", tier=4, kind="hot", group="WS",
         rect=R("WS", 250, 500, 330, 560), node=P("WS", 290, 528),
         label="SHOWHOME", sub="2 show homes · hot zone"),
    dict(id="WORKSITE", name="Worksite", tier=3, kind="hot", group="WS",
         poly=Ps("WS", [(168, 497), (400, 497), (436, 510), (438, 600), (430, 655), (300, 662), (182, 658),
                        (166, 600)]),
         node=P("WS", 300, 600), label="WORKSITE", sub="cranes · Shells · site office"),
    dict(id="FARM", name="Farm", tier=2, kind="small", group="FARM", rect=R("FARM", 124, 244, 232, 330),
         node=P("FARM", 170, 285), label="FARM", sub="square farm · silo"),
    dict(id="HUT", name="Forester's Hut", tier=2, kind="micro", group="HUT", circle=C("HUT", 200, 800, 22),
         node=P("HUT", 200, 800), label="FORESTER'S HUT", sub=""),
    dict(id="CONTAINER", name="Container Park", tier=2, kind="poi", group="CP", rect=R("CP", 585, 484, 708, 578),
         node=P("CP", 645, 530), label="CONTAINER PARK", sub="ramp ring · skips"),
    dict(id="PLANT", name="Water Treatment Plant", tier=3, kind="poi", group="PLANT",
         # west edge follows the east bank (computed in make_diagram from `bank`)
         poly_east=Ps("PLANT", [(760, 340), (760, 124), (548, 124)]), bank=("E", 27.0),
         node=P("PLANT", 705, 316), label="WATER TREATMENT PLANT", sub="tanks · pump house · control bldg"),
    dict(id="SUBSTATION", name="Substation", tier=2, kind="small", group="SUB", rect=R("SUB", 846, 116, 934, 200),
         node=P("SUB", 890, 158), label="SUBSTATION", sub=""),
    dict(id="STORAGE", name="Self-Storage", tier=3, kind="poi", group="STO", rect=R("STO", 812, 612, 952, 740),
         node=P("STO", 880, 676), label="SELF-STORAGE", sub="roll-up rows · office"),
    dict(id="GAS", name="Gas Station", tier=2, kind="poi", group="GAS", rect=R("GAS", 908, 474, 994, 542),
         node=P("GAS", 950, 505), label="GAS STATION", sub="abandoned"),
    dict(id="SLUICE", name="Sluice House", tier=2, kind="micro", group="SLU", rect=R("SLU", 570, 12, 612, 50),
         node=P("SLU", 590, 32), label="SLUICE HOUSE", sub=""),
]

# ------------------------------------------------------------------ the TDM / FFA cut-out (Showhome v3)
TDM = dict(rect=R("WS", 250.0, 500.0, 330.0, 560.0),
           walls=[dict(side="S", what="road side: player_clip along the front-street kerb (street visible, open)"),
                  dict(side="W", what="field edge: clip above the Sage garden hedge (site office beyond)"),
                  dict(side="E", what="field edge: clip above the Clay garden hedge (material yard beyond)"),
                  dict(side="N", what="plot edge: clip on the mesh site fence behind the carports")])
INSET_EXT = (P("WS", 162, 0)[0], P("WS", 452, 0)[0], P("WS", 0, 456)[1], P("WS", 0, 688)[1])   # same shape as v0.1

# ------------------------------------------------------------------ spawns (blue) and extracts (green)
# side: which half a spawn group belongs to. Extract sets are chosen per spawn side (see LAYOUT.md).
# only16: zones that open only when the raid has 16 players (8 groups).
SPAWNS = [
    dict(id="S1", name="West Fields", side="W", rect=(0, 670, 16, 770)),
    dict(id="S2", name="Dike West", side="W", rect=(320, 0, 430, 16)),
    dict(id="S3", name="North Woods", side="W", rect=(350, 1084, 460, 1100)),
    dict(id="S4", name="NE Woods", side="E", rect=(1090, 1084, 1200, 1100)),
    dict(id="S5", name="East Field", side="E", rect=(1284, 690, 1300, 790)),
    dict(id="S6", name="Dike East", side="E", rect=(1030, 0, 1130, 16)),
    dict(id="S7", name="South-West Field", side="W", rect=(0, 250, 16, 350), only16=True),
    dict(id="S8", name="Riverside North", side="E", rect=(650, 1084, 750, 1100), only16=True),
]
EXTRACTS = [
    dict(id="X1", name="Logging Track", at=(8, 1005), kind="always", cond="always open", for_side="E",
         note="logging track into the West Woods at the west edge"),
    dict(id="X2", name="Cement Truck", at=P("WS", 184, 508), kind="timed", cond="opens at 20:00, one squad",
         for_side="ALL", note="the mixer truck at the West Gate leaves 60 s after the first squad boards (engine noise)"),
    dict(id="X3", name="Sluice Boat", at=P("SLU", 566, 22), kind="paid", cond="pay, boat comes in 40 s",
         for_side="ALL", note="call post on the sluice-house jetty (east bank); price: open question 6"),
    dict(id="X4", name="Substation Gate", at=(1290, 185), kind="conditional", cond="throw the kiosk breaker",
         for_side="W", note="the gate opens 60 s after the breaker is thrown, and an alarm sounds"),
    dict(id="X5", name="Hard Shoulder", at=None, at_y=1082.0, kind="always", cond="always open", for_side="W",
         note="hard shoulder in the highway cutting at the north edge, under the Overpass"),
    dict(id="X6", name="Dike Culvert", at=(125, 10), kind="conditional", cond="no backpack", for_side="E",
         note="a drainage culvert through the dike, too tight for a backpack"),
]
EXTRACT_R = 10.0

# ------------------------------------------------------------------ landmarks
LANDMARKS = [
    dict(id="CRANE1", name="Crane 1", at=P("WS", 353, 587), jib_to=P("WS", 314, 550), counter=P("WS", 366, 600)),
    dict(id="CRANE2", name="Crane 2", at=P("WS", 225, 625), jib_to=P("WS", 262, 598), counter=P("WS", 214, 633)),
    dict(id="EGGS", name="Digester eggs", at=P("PLANT", 735, 254)),
    dict(id="PYLON_SIGN", name="Price pylon", at=P("GAS", 914, 486)),
    dict(id="SILO", name="Silo", at=P("FARM", 222, 300)),
    dict(id="CHAPEL", name="Chapel", at=(279, 525)),
]

# ------------------------------------------------------------------ ziplines (suggestions)
ZIPLINES = [
    dict(id="Z1", a=P("WS", 318, 612), b=P("WS", 392, 548), note="Shells roof (9 m) → material yard"),
    dict(id="Z2", a=P("PLANT", 708, 328), b=P("PLANT", 530, 292), note="control building roof (10 m) → pump house roof"),
]

# ------------------------------------------------------------------ key sightlines (thin red) and chokepoints (red)
# An endpoint is either a point, or ("C2", dx, dy) = a crossing centre + offset, or ("X5", dx, dy) = an extract
# + offset, or ("GANTRY", i) = the centre of gantry i on the deck.
SIGHTLINES = [
    dict(id="L1", a=("C2", 0, -10), b=("C3", 0, 8), note="Road Bridge ↔ Weir, along the water"),
    dict(id="L2", a=P("CP", 604, 556), b=("C2", 12, 4), note="Container-park ramp deck → Road Bridge"),
    dict(id="L3", a=P("PLANT", 528, 296), b=P("PLANT", 452, 262), note="Pump-house roof → Weir catwalk + west bank"),
    dict(id="L4", a=("O1", 3, 8), b=("X5", 12, 3), note="Overpass → Hard Shoulder (X5), down the cutting"),
    dict(id="L5", a=("O1", 3, -8), b=("GANTRY", 1), note="Overpass → highway deck south (gantry)"),
    dict(id="L6", a=("U1", -12, -1), b=(845, 558), note="Underpass mouth → Old Road west (stalled lorry at x 960)"),
    dict(id="L7", a=P("WS", 300, 616), b=P("WS", 286, 556), note="Shells top floor → Showhome carports + street"),
    dict(id="L8", a=("C2", -26, 4), b=P("WS", 332, 532), note="Road Bridge → Clay house front (break it)"),
    dict(id="L9", a=P("FARM", 214, 316), b=(390, 232), note="Farm hayloft → nursery + SW fields"),
    dict(id="L10", a=("C1", -1, -4), b=("C1", 8, 44), note="Dirt Bridge: forest keeps lines short"),
    dict(id="L11", a=("C3", 2, -8), b=P("SLU", 560, 30), note="Weir → Sluice House along the river"),
]
CHOKEPOINTS = [
    dict(id="K1", name="Road Bridge", at="C2", r=34),
    dict(id="K2", name="Dirt Bridge", at="C1", r=30),
    dict(id="K3", name="Weir", at="C3", r=30),
    dict(id="K4", name="Underpass", at="U1", r=30),
    dict(id="K5", name="Overpass", at="O1", r=30),
    dict(id="K6", name="Showhome street", at=P("WS", 290, 516), r=13),
    dict(id="K7", name="Plant gate", at=P("PLANT", 715, 344), r=16),
    dict(id="K8", name="Storage front gate", at=P("STO", 880, 614), r=16),
    dict(id="K9", name="Container-park gate / plant crossroads", at=P("CP", 645, 486), r=18),
]


# ------------------------------------------------------------------ structures (simplified footprints)
# shape: rect (x0,y0,x1,y1) | circle (cx,cy,r); style: bldg, tank, low, deck, vehicle, plot, pit, canopy, ...
def _grp(g, items):
    out = []
    for it in items:
        it = dict(it)
        if "rect" in it:
            it["rect"] = R(g, *it["rect"])
        else:
            it["circle"] = C(g, *it["circle"])
        out.append(it)
    return out


_WS = [
    # Showhome (schematic, prompt 4 decides): two houses, truck, carports
    dict(rect=(262, 512, 276, 540), style="bldg", poi="SHOWHOME"),
    dict(rect=(304, 512, 318, 540), style="bldg", poi="SHOWHOME"),
    dict(rect=(288.2, 514, 291.8, 528), style="vehicle", poi="SHOWHOME"),
    dict(rect=(278, 548, 288, 557), style="canopy", poi="SHOWHOME"),
    dict(rect=(292, 548, 302, 557), style="canopy", poi="SHOWHOME"),
    # worksite
    dict(rect=(190, 510, 203, 513), style="bldg"), dict(rect=(190, 516, 203, 519), style="bldg"),
    dict(rect=(206, 510, 219, 513), style="bldg"), dict(rect=(206, 516, 219, 519), style="bldg"),
    dict(rect=(224, 510, 236, 512.5), style="low"), dict(rect=(190, 534, 203, 537), style="bldg"),
    dict(rect=(206, 534, 219, 537), style="bldg"), dict(rect=(224, 528, 229, 533), style="low"),
    dict(rect=(176, 500, 180, 510), style="vehicle"),                                  # cement mixer (X2)
    dict(rect=(245, 590, 335, 616), style="shell"),                                    # the Shells
    dict(rect=(342, 504, 352, 512), style="low"), dict(rect=(356, 504, 366, 512), style="low"),
    dict(rect=(342, 518, 352, 526), style="low"), dict(rect=(370, 516, 392, 520), style="low"),
    dict(rect=(370, 526, 392, 529), style="low"), dict(rect=(356, 534, 366, 544), style="low"),
    dict(rect=(380, 542, 384, 553), style="vehicle"), dict(rect=(398, 512, 404, 518), style="vehicle"),
    dict(rect=(346, 572, 370, 586), style="plot"), dict(rect=(376, 572, 402, 586), style="plot"),
    dict(rect=(346, 598, 370, 614), style="plot"), dict(rect=(376, 598, 402, 614), style="plot"),
    dict(rect=(188, 578, 214, 596), style="plot"), dict(rect=(188, 604, 214, 620), style="plot"),
    dict(rect=(408, 516, 426, 546), style="pit"), dict(rect=(346, 622, 368, 644), style="pit"),
    dict(rect=(240, 630, 270, 648), style="pit"),
    dict(circle=(414, 612, 8), style="heap"), dict(circle=(404, 638, 6), style="heap"),
]
_FARM = [
    dict(rect=(130, 250, 182, 262), style="bldg"), dict(rect=(130, 262, 142, 318), style="bldg"),
    dict(rect=(142, 306, 194, 318), style="bldg"), dict(rect=(198, 250, 210, 300), style="bldg"),
    dict(rect=(140, 222, 176, 238), style="canopy"), dict(circle=(222, 300, 4.5), style="tank"),
]
_HUT = [dict(rect=(195, 795, 205, 803), style="bldg")]
_CP = [
    dict(rect=(602, 505, 688, 520), style="deck"), dict(rect=(602, 545, 688, 560), style="deck"),
    dict(rect=(602, 520, 617, 545), style="deck"), dict(rect=(673, 520, 688, 545), style="deck"),
    dict(rect=(602, 490, 617, 505), style="ramp"), dict(rect=(673, 490, 688, 505), style="ramp"),
    dict(rect=(624, 526, 666, 539), style="canopy"),
    dict(rect=(628, 476, 638, 483), style="bldg"), dict(rect=(692, 492, 704, 504), style="low"),
] + [dict(rect=(605 + 8.4 * i, 561, 611 + 8.4 * i, 568), style="skip") for i in range(10)] \
  + [dict(rect=(594, 522 + 8 * i, 600, 528 + 8 * i), style="skip") for i in range(3)] \
  + [dict(rect=(690, 522 + 8 * i, 696, 528 + 8 * i), style="skip") for i in range(3)]
_PLANT = [
    dict(rect=(686, 300, 728, 330), style="bldg"),                      # control building (3 floors)
    dict(rect=(512, 274, 542, 302), style="bldg"),                      # pump house / inlet works
    dict(rect=(498, 252, 507, 263), style="bldg"),                      # weir gate house
    dict(circle=(576, 304, 15), style="tank"), dict(circle=(576, 236, 15), style="tank"),
    dict(circle=(634, 222, 14), style="tank"), dict(circle=(680, 222, 14), style="tank"),
    dict(rect=(610, 262, 676, 318), style="basin"),
    dict(circle=(735, 268, 8), style="egg"), dict(circle=(735, 240, 8), style="egg"),
    dict(rect=(712, 140, 746, 172), style="bldg"),
] + [dict(rect=(556 + 25 * i, 138, 578 + 25 * i, 184), style="bed") for i in range(6)]
_STO = [dict(rect=(830 + 20 * i, 646, 838 + 20 * i, 726), style="bldg") for i in range(5)] + [
    dict(rect=(924, 646, 946, 728), style="bldg"), dict(rect=(864, 617, 880, 630), style="bldg")]
_GAS = [dict(rect=(924, 480, 956, 500), style="canopy"), dict(rect=(962, 484, 988, 504), style="bldg"),
        dict(rect=(924, 516, 976, 526), style="bldg")]
_SUB = [dict(rect=(858 + 16 * i, 140 + 22 * j, 868 + 16 * i, 150 + 22 * j), style="low")
        for i in range(4) for j in range(3)] + [dict(rect=(906, 120, 920, 132), style="bldg")]
_SLU = [dict(rect=(578, 26, 598, 42), style="bldg"), dict(rect=(566, 28, 578, 31), style="low")]

STRUCTURES = (_grp("WS", _WS) + _grp("FARM", _FARM) + _grp("HUT", _HUT) + _grp("CP", _CP) + _grp("PLANT", _PLANT)
              + _grp("STO", _STO) + _grp("GAS", _GAS) + _grp("SUB", _SUB) + _grp("SLU", _SLU)
              + [dict(rect=(276, 522, 282, 528), style="bldg")]                      # the chapel
              + [dict(rect=f["rect"], style=f["style"]) for f in FIELD_STRUCTURES])

# ------------------------------------------------------------------ travel-time graph nodes
# The graph links every pair of nodes whose straight line does not cross the river or the highway (x ROUTE_FACTOR),
# plus the explicit crossings. It is a rough model: players cut across fields, so it follows the open ground.
TRAVEL_POIS = ["SHOWHOME", "FARM", "CONTAINER", "PLANT", "STORAGE", "GAS", "SUBSTATION", "SLUICE", "HUT"]
