"""Shared campus parking basement, four access cores and a direct north-descending ramp.

Build-only helper: no scene reset, source edits, catalog writes or exports.
Call build_basement(root, materials, building_bounds), then cut its returned stair
and lift rectangles through the standing buildings' own GF/upper slabs. Exclude
ground_exclusions from terrain. Call validate_basement_routes with the integrated
serialized COLL rows before export. All coordinates are design world XYZ metres.
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import common as C

FLOOR_Z = -3.2
DECK_Z = 0.0
DECK_THICKNESS = .25
DEFAULT_BUILDINGS = [[345, 750, 371, 804], [397, 750, 423, 804], [345, 838, 371, 892], [397, 838, 423, 892]]
# The perpendicular service road x447 continues directly into the east-wing
# ramp. Grade is at the south mouth; the basement exit is near its north/back.
RAMP_EXCAVATION = [443.85, 847, 450.15, 873]
RAMP_CLEAR = [444.15, 849, 449.85, 867]
_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def _geometry(root, name, verts, faces, mat, collision=True, walkable=True, part="parking_basement"):
    bm = bmesh.new()
    vv = [bm.verts.new(v) for v in verts]
    for f in faces:
        bm.faces.new([vv[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.verts.index_update()
    verts = [tuple(v.co) for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    ob = C.mesh(name, verts, faces, mat, root)
    for loop in ob.data.uv_layers[0].data:
        loop.uv /= mat.get("repeat_m", 1)
    ob["part"] = part
    ob["source"] = "project original shared campus parking basement"
    if collision:
        co = C.col_mesh(name, verts, faces, mat["phys"], walkable=walkable, parent=root)
        co["part"] = part
        ob["collision"] = co.name
    return ob


def _box(root, name, lo, hi, mat, collision=True, part="parking_basement"):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    assert x1 > x0 and y1 > y0 and z1 > z0, (name, lo, hi)
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    return _geometry(root, name, verts, _FACES, mat, collision, part=part)


def _bar(root, name, a, b, width, mat, collision=True, part="parking_basement/stairs"):
    a, b = Vector(a), Vector(b)
    centre = (a + b) / 2
    rotation = (b - a).to_track_quat("Z", "Y").to_matrix()
    length = (b - a).length
    signs = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
    verts = [tuple(centre + rotation @ Vector((x * width / 2, y * width / 2, z * length / 2))) for x, y, z in signs]
    return _geometry(root, name, verts, _FACES, mat, collision, part=part)


def _slope(root, name, top, mat, thickness=.20, part="parking_basement/stairs"):
    verts = top + [(x, y, z - thickness) for x, y, z in top]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    return _geometry(root, name, verts, faces, mat, part=part)


def _paint(root, name, points, mat):
    # Thin surface markings add neither collision thickness nor a second deck.
    ob = _geometry(root, name, points, [tuple(range(len(points)))], mat, collision=False, part="parking_basement/markings")
    ob["surface_detail"] = "painted parking marking; visual only"
    return ob


def _rect_contains(x, y, rect):
    return rect[0] < x < rect[2] and rect[1] < y < rect[3]


def _deck_rectangles(bounds, exclusions):
    xs = sorted({bounds[0], bounds[2], *[v for r in exclusions for v in (r[0], r[2]) if bounds[0] < v < bounds[2]]})
    ys = sorted({bounds[1], bounds[3], *[v for r in exclusions for v in (r[1], r[3]) if bounds[1] < v < bounds[3]]})
    rectangles = []
    for y0, y1 in zip(ys, ys[1:]):
        start = None
        for x0, x1 in zip(xs, xs[1:]):
            clear = not any(_rect_contains((x0 + x1) / 2, (y0 + y1) / 2, r) for r in exclusions)
            if clear and start is None:
                start = x0
            if start is not None and (not clear or x1 == xs[-1]):
                rectangles.append([start, y0, x0 if not clear else x1, y1])
                start = None
    return rectangles


def _path_segment(path, a, b, count=18):
    for k in range(count + 1):
        path.append([a[i] + (b[i] - a[i]) * k / count for i in range(3)])


def _access_core(root, materials, index, bounds, foundation):
    concrete, steel = materials["concrete"], materials["steel"]
    dx, dy = bounds[0] - 355, bounds[1] - 732
    p = lambda x, y, z: (x + dx, y + dy, z)
    hole = [373 + dx, 734 + dy, 377.8 + dx, 739 + dy]
    shaft = [373 + dx, 741 + dy, 376 + dx, 744 + dy]
    name = "EXT_ParkingCore_" + str(index)
    rise, tread = 3.2 / 18, .30
    # The two flights follow the same footprint/orientation as the rotated frame.
    for flight, (y0, y1, xa, xb, za, zb) in enumerate(((734.4, 735.8, 377.4, 374.7, -3.2, -1.6), (736.2, 737.6, 374.7, 377.4, -1.6, 0))):
        top = [p(xa, y0, za), p(xb, y0, zb), p(xb, y1, zb), p(xa, y1, za)]
        _slope(root, name + "_StairUnderslab_" + str(flight), top, concrete)
        for k in range(9):
            aa, bb = xa + (xb - xa) * k / 9, xa + (xb - xa) * (k + 1) / 9
            z = za + (k + 1) * rise
            _box(root, name + "_Tread_" + str(flight) + "_" + str(k), p(min(aa, bb), y0, z - .20), p(max(aa, bb), y1, z), concrete, collision=False, part="parking_basement/stairs")
        for y in (y0 - .07, y1 + .07):
            _bar(root, name + "_Handrail", p(xa, y, za + 1.05), p(xb, y, zb + 1.05), .04, steel)
            for k in range(4):
                t = k / 3
                x, z = xa + (xb - xa) * t, za + (zb - za) * t
                _bar(root, name + "_RailPost", p(x, y, z), p(x, y, z + 1.05), .04, steel)
    _box(root, name + "_MidLanding", p(373.3, 734.4, -1.82), p(374.7, 737.6, -1.6), concrete, part="parking_basement/stairs")
    # Only the 0.4m tongue occupies the hole; standing GF slabs supply the east
    # landing area. There is no double surface over a normal building's GF floor.
    _box(root, name + "_GFLandingTongue", p(377.4, 734.4, -.22), p(377.8, 737.6, 0), concrete, part="parking_basement/stairs")
    for a, b in ((p(373.23, 734.3, -.55), p(373.23, 737.7, -.55)), (p(373.23, 734.3, -.55), p(374.7, 734.3, -.55)), (p(373.23, 737.7, -.55), p(374.7, 737.7, -.55))):
        _bar(root, name + "_LandingRail", a, b, .04, steel)
    x0, y0, x1, y1 = shaft
    t = .25
    _box(root, name + "_LiftWallWest", (x0, y0, FLOOR_Z), (x0 + t, y1, 0), concrete)
    _box(root, name + "_LiftWallEast", (x1 - t, y0, FLOOR_Z), (x1, y1, 0), concrete)
    _box(root, name + "_LiftWallBack", (x0 + t, y1 - t, FLOOR_Z), (x1 - t, y1, 0), concrete)
    for xa, xb in ((x0 + t, x0 + .7), (x1 - .7, x1 - t)):
        _box(root, name + "_LiftDoorPier", (xa, y0, FLOOR_Z), (xb, y0 + t, 0), concrete)
    _box(root, name + "_LiftDoorHeader", (x0 + .7, y0, -.4), (x1 - .7, y0 + t, 0), concrete)
    if foundation:
        # The fourth footprint is open; narrow fixed bridges let workers leave
        # the stairs and approach its future lift without inventing a full GF slab.
        _box(root, name + "_FoundationStairBridge", p(377.8, 734.4, -.22), p(381, 737.6, 0), concrete, part="parking_basement/foundation")
        _box(root, name + "_FoundationLiftBridge", p(373, 739.5, -.22), p(381, 741, 0), concrete, part="parking_basement/foundation")
    stairs = []
    _path_segment(stairs, p(380.4, 735.1, FLOOR_Z), p(377.4, 735.1, FLOOR_Z))
    _path_segment(stairs, p(377.4, 735.1, FLOOR_Z), p(374.7, 735.1, -1.6), 27)
    _path_segment(stairs, p(374.7, 735.1, -1.6), p(373.9, 735.1, -1.6), 8)
    _path_segment(stairs, p(373.9, 735.1, -1.6), p(373.9, 736.9, -1.6))
    _path_segment(stairs, p(373.9, 736.9, -1.6), p(374.7, 736.9, -1.6), 8)
    _path_segment(stairs, p(374.7, 736.9, -1.6), p(377.4, 736.9, 0), 27)
    # GF exit support in the first three buildings is supplied by their own slab.
    # Route QA can run standalone up to the tongue, then fully after integration.
    _path_segment(stairs, p(377.4, 736.9, 0), p(377.65, 736.9, 0), 3)
    lifts = []
    _path_segment(lifts, p(374.5, 739.7, FLOOR_Z), p(374.5, 742, FLOOR_Z), 23)
    return dict(id="parking_core_" + str(index), building_index=index, foundation_only=foundation,
                building_bounds=list(bounds), stair_opening=hole, lift_opening=shaft,
                stair_clear_width_m=1.4, stair_riser_m=rise, stair_tread_m=tread,
                landing_depth_m=1.4, basement_z_m=FLOOR_Z, ground_floor_z_m=0,
                lift_clear_size_m=[2.5, 2.5], lift_basement_door_width_m=1.6,
                lift_basement_door_height_m=2.8, lift_door_side="south",
                lift_simulation=False, route_samples=stairs, lift_route_samples=lifts,
                gf_exit_sample=list(p(380.4, 736.9, 0)))


def _vehicle_ramp(root, materials, basement_bounds):
    concrete, steel = materials["concrete"], materials["steel"]
    x0, y0, x1, y1 = RAMP_CLEAR
    cut_x0, cut_y0, cut_x1, cut_y1 = RAMP_EXCAVATION
    centre_x = (x0 + x1) / 2
    assert basement_bounds[0] < cut_x0 < cut_x1 < basement_bounds[2]
    assert basement_bounds[1] < cut_y0 < cut_y1 < basement_bounds[3]
    # The public-road approach remains at grade until the south mouth. Its
    # single continuous axis descends north, with no transverse connector.
    top = [(x0, y0, 0), (x1, y0, 0), (x1, y1, FLOOR_Z), (x0, y1, FLOOR_Z)]
    _slope(root, "EXT_ParkingVehicleRamp", top, concrete, .24, "parking_basement/vehicle_ramp")
    _box(root, "EXT_ParkingRampTopLanding", (cut_x0, cut_y0, -.24), (cut_x1, y0, 0), concrete, part="parking_basement/vehicle_ramp")
    # Side walls follow the underside of the slope, with a low grade parapet.
    for index, (xa, xb) in enumerate(((cut_x0, x0), (x1, cut_x1))):
        verts = [(xa, y0, -.24), (xb, y0, -.24), (xb, y1, FLOOR_Z - .24), (xa, y1, FLOOR_Z - .24),
                 (xa, y0, .35), (xb, y0, .35), (xb, y1, .35), (xa, y1, .35)]
        _geometry(root, "EXT_ParkingRampRetaining_" + str(index), verts, _FACES, concrete, part="parking_basement/vehicle_ramp")
    # The exposed bottom landing is the existing shared basement floor. Roof
    # cutting continues through y873 so vehicles enter the covered parking only
    # after reaching their normal floor elevation, preserving2.95m headroom.
    _box(root, "EXT_ParkingRampDrainLip", (x0, y0 - .62, -.01), (x1, y0 - .35, .02), concrete, part="parking_basement/vehicle_ramp")
    for k in range(22):
        x = x0 + .08 + k * (x1 - x0 - .16) / 21
        _box(root, "EXT_ParkingDrainGrate_" + str(k), (x - .035, y0 - .59, .021), (x + .035, y0 - .38, .033), steel, collision=False, part="parking_basement/vehicle_ramp")
    def lane_path(x):
        path=[]
        _path_segment(path, (x, cut_y0 + .5, 0), (x, y0, 0), 15)
        _path_segment(path, (x, y0, 0), (x, y1, FLOOR_Z), 72)
        _path_segment(path, (x, y1, FLOOR_Z), (x, cut_y1 + .4, FLOOR_Z), 32)
        return path
    path=lane_path(centre_x)
    lanes=[dict(direction=direction, centre_x_m=x, route_samples=lane_path(x)) for direction,x in
           (("inbound",x0+(x1-x0)*.25),("outbound",x0+(x1-x0)*.75))]
    return dict(excavation=list(RAMP_EXCAVATION), clear_bounds=list(RAMP_CLEAR), clear_width_m=x1 - x0,
                slope_deg=math.degrees(math.atan(3.2 / (y1 - y0))), run_m=y1-y0,
                alignment="straight_south_top_to_north_basement", axis_x_m=centre_x,
                top_entry_m=[centre_x, cut_y0+.5, 0], bottom_exit_m=[centre_x,cut_y1,FLOOR_Z],
                top_landing_bounds=[cut_x0,cut_y0,cut_x1,y0],bottom_landing_bounds=[cut_x0,y1,cut_x1,cut_y1],
                roof_opening=list(RAMP_EXCAVATION),connector_turns=0,two_way=True,lanes=lanes,
                drain_lip_m=.02,route_samples=path,
                recommended_service_road_connection=[x0,cut_y0-6,x1,cut_y0])


def _parking_markings(root, materials, building_bounds, basement_bounds, lane_x):
    paint = materials.get("cream", materials["concrete"]).copy()
    paint.name = "M_V3_BasementParkingPaint"
    paint["phys"] = "concrete"
    z = FLOOR_Z + .006
    bays = []
    for block, (footprint, y_offset) in enumerate(zip(building_bounds, (12.7, 39.7, 15.7, 34.7))):
        x0, y0 = footprint[0] + 1.3, footprint[1] + y_offset
        for k in range(6):
            x = x0 + k * 2.65
            for xx in (x, x + 2.5):
                _paint(root, "EXT_ParkingBay_" + str(block) + "_" + str(k), [(xx, y0, z), (xx + .065, y0, z), (xx + .065, y0 + 5, z), (xx, y0 + 5, z)], paint)
            _paint(root, "EXT_ParkingBayBack", [(x, y0 + 5, z), (x + 2.565, y0 + 5, z), (x + 2.565, y0 + 5.065, z), (x, y0 + 5.065, z)], paint)
            bays.append(dict(block=block, slot=k, bounds=[x, y0, x + 2.5, y0 + 5], centre=[x + 1.25, y0 + 2.5, FLOOR_Z]))
    for y in range(math.ceil(basement_bounds[1] + 4), math.floor(basement_bounds[3] - 3), 5):
        _paint(root, "EXT_ParkingThroughLaneDash", [(lane_x - .05, y, z), (lane_x + .05, y, z), (lane_x + .05, y + 2, z), (lane_x - .05, y + 2, z)], paint)
    for x, y in [(lane_x, basement_bounds[1] + (basement_bounds[3] - basement_bounds[1]) * t) for t in (.18, .52, .84)]:
        points = [(x - .13, y - .75, z), (x + .13, y - .75, z), (x + .13, y + .1, z), (x + .42, y + .1, z), (x, y + .80, z), (x - .42, y + .1, z), (x - .13, y + .1, z)]
        _paint(root, "EXT_ParkingDirectionArrow", points, paint)
    return bays


def build_basement(root, materials, building_bounds):
    """Create one open shared basement; return geometry/access/QA metadata.

    The fourth bounds record is foundation-only. The first three buildings own
    their GF slabs; none of their slabs or upper frame meshes are created here.
    """
    assert len(building_bounds) == 4, "The campus basement expects three standing footprints and one open foundation"
    for key, phys in (("concrete", "concrete"), ("steel", "metal_heavy")):
        assert materials[key].get("phys") == phys, (key, phys)
    before = set(bpy.context.scene.objects)
    concrete = materials["concrete"]
    bounds = [min(r[0] for r in building_bounds) - 6, min(r[1] for r in building_bounds) - 6,
              max(r[2] for r in building_bounds) + 28, max(r[3] for r in building_bounds) + 4]
    assert all(r[2] - r[0] >= 22.8 and r[3] - r[1] >= 12 for r in building_bounds), "Footprints must contain their local stair and shaft cores"
    assert bounds[0] < RAMP_EXCAVATION[0] < RAMP_EXCAVATION[2] < bounds[2] and bounds[1] < RAMP_EXCAVATION[1] < RAMP_EXCAVATION[3] < bounds[3], "Direct ramp must lie inside the east basement wing"
    x0, y0, x1, y1 = bounds
    _box(root, "EXT_ParkingSharedFloor", (x0, y0, FLOOR_Z - .28), (x1, y1, FLOOR_Z), concrete)
    _box(root, "EXT_ParkingWallWest", (x0, y0, FLOOR_Z), (x0 + .30, y1, 0), concrete)
    _box(root, "EXT_ParkingWallSouth", (x0 + .30, y0, FLOOR_Z), (x1, y0 + .30, 0), concrete)
    _box(root, "EXT_ParkingWallNorth", (x0 + .30, y1 - .30, FLOOR_Z), (x1, y1, 0), concrete)
    _box(root, "EXT_ParkingWallEast", (x1-.30,y0+.30,FLOOR_Z), (x1,y1-.30,0), concrete)
    deck_rectangles = _deck_rectangles(bounds, building_bounds + [RAMP_EXCAVATION])
    for index, (a, b, c, d) in enumerate(deck_rectangles):
        _box(root, "EXT_ParkingRoofDeck_" + str(index), (a, b, -DECK_THICKNESS), (c, d, DECK_Z), concrete)
    columns = []
    for index, r in enumerate(building_bounds):
        # Match the rotated upper-frame column grid. The common central lane
        # between the two building rows and the cross lanes remain unpartitioned.
        xs = [r[0] + .225, r[0] + 8.75, r[0] + 17.25, r[2] - .225]
        ys = [r[1] + .225, *[r[1] + 9 + k * 9 for k in range(5)], r[3] - .225]
        for x in xs:
            for y in ys:
                # Match the standing GF slab underside; exposed foundation
                # columns continue to their +0m starter stubs without an air gap.
                top_z = -.22 if index < 3 else 0
                _box(root, "EXT_ParkingColumn_" + str(index), (x - .225, y - .225, FLOOR_Z), (x + .225, y + .225, top_z), concrete)
                columns.append([x, y])
                if index == 3:
                    _box(root, "EXT_FoundationStarter", (x - .225, y - .225, 0), (x + .225, y + .225, .48), concrete, part="parking_basement/foundation")
                    for dx in (-.10, .10):
                        _bar(root, "EXT_FoundationStarterRebar", (x + dx, y, .48), (x + dx, y, 1.05), .025, materials["steel"], collision=False, part="parking_basement/foundation")
    # A separate column row supports the new east parking wing while leaving
    # the direct x447 road/ramp axis open above and below the deck.
    for y in (756,774,792,810,828,846,864,882):
        _box(root,"EXT_ParkingEastWingColumn",(437.775,y-.225,FLOOR_Z),(438.225,y+.225,-DECK_THICKNESS),concrete)
        columns.append([438,y])
    cores = [_access_core(root, materials, i, r, i == 3) for i, r in enumerate(building_bounds)]
    ramp = _vehicle_ramp(root, materials, bounds)
    lane_x = (building_bounds[0][2] + building_bounds[1][0]) / 2
    bays = _parking_markings(root, materials, building_bounds, bounds, lane_x)
    parked = [dict(position=next(b["centre"] for b in bays if b["block"] == index and b["slot"] == slot), yaw_deg=0 if index % 2 == 0 else 180) for index, slot in ((0, 0), (1, 1), (2, 1), (3, 1))]
    new = [o for o in bpy.context.scene.objects if o not in before]
    visual = [o for o in new if o.type == "MESH" and not o.name.startswith("COL_")]
    collision = [o for o in new if o.name.startswith("COL_")]
    C.audit_visuals(visual)
    rows = C.collision_rows(collision)
    report = dict(schema=1, bounds=bounds, floor_z_m=FLOOR_Z, deck_top_z_m=DECK_Z,
                  deck_underside_z_m=-DECK_THICKNESS, clear_height_m=2.95, concrete_wall_thickness_m=.30,
                  shared_open_space=True, internal_partition_walls=0, columns=columns,
                  building_bounds=[list(r) for r in building_bounds], foundation_building_index=3,
                  deck_excludes_all_building_footprints=True, roof_rectangles=deck_rectangles,
                  ground_exclusions=[bounds, list(RAMP_EXCAVATION)],
                  ground_floor_stair_openings=[r["stair_opening"] for r in cores],
                  lift_shaft_openings=[r["lift_opening"] for r in cores], access_cores=cores, vehicle_ramp=ramp,
                  parking_bays=bays, central_through_lane=[lane_x - 3.5, y0 + 2, lane_x + 3.5, y1 - 2],
                  cross_through_lanes=[[x0 + .3, building_bounds[0][1] + 28.5, x1 - .3, building_bounds[0][1] + 33.5], [x0 + .3, RAMP_CLEAR[3], x1 - .3, RAMP_EXCAVATION[3]], [x0 + .3, (building_bounds[0][3] + building_bounds[2][1]) / 2 - 3.5, x1 - .3, (building_bounds[0][3] + building_bounds[2][1]) / 2 + 3.5]],
                  suggested_parked_cars=parked,
                  triangles=C.triangles(visual), collision_volumes=len(rows),
                  min_collision_thickness_m=min(r["thickness_m"] for r in rows), uv_ok=True, phys_ok=True,
                  convex_collision_ok=True, integration_requirements=[
                      "Exclude ground_exclusions from flat terrain and relocate conflicting pits/spoil heaps",
                      "Cut returned stair and shaft rectangles through GF and all standing upper slabs",
                      "First three GF slabs supply stair exits beyond their 0.4m landing tongues",
                      "Extend standing lift-shaft walls upward with clear south-facing door apertures",
                      "Keep the fourth footprint open except its starters and narrow access bridges",
                      "Run validate_basement_routes on complete integrated collision rows",
                  ], runtime_playtest=False)
    # Standalone validation stops normal GF routes at their tongues; full GF exit
    # samples are enabled by the caller after the standing slabs have been cut.
    report["standalone_route_qa"] = validate_basement_routes(report, rows)
    report["vehicle_ramp"]["two_way_pedestrian_qa"] = [validate_basement_routes(dict(access_cores=[], vehicle_ramp=dict(route_samples=lane["route_samples"])), rows) for lane in ramp["lanes"]]
    return report


def _inside(row, p, epsilon=.002):
    return all(q[0] * p[0] + q[1] * p[1] + q[2] * p[2] <= q[3] + epsilon for q in row["planes"])


def validate_basement_routes(report, rows, include_gf_exits=False, radius=.32, height=1.8):
    """Check floor support and the simulation's swept standing box on all routes.

    Call again with integrated COLL rows and include_gf_exits=True. No scene,
    files, actual props or game state are modified by this check.
    """
    routes = []
    for core in report["access_cores"]:
        path = list(core["route_samples"])
        if include_gf_exits:
            _path_segment(path, path[-1], core["gf_exit_sample"], 15)
        routes.append((core["id"] + "_stairs", path))
        routes.append((core["id"] + "_lift", core["lift_route_samples"]))
    routes.append(("vehicle_ramp_pedestrian", report["vehicle_ramp"]["route_samples"]))
    checked = []
    half = [radius, radius, height / 2 - .01]
    for label, path in routes:
        for p in path:
            x, y, want = p
            near = [r for r in rows if r["aabb"]["min"][0] - radius <= x <= r["aabb"]["max"][0] + radius and r["aabb"]["min"][1] - radius <= y <= r["aabb"]["max"][1] + radius]
            tops = []
            for row in near:
                if not row.get("walkable", True):
                    continue
                for nx, ny, nz, d in row["planes"]:
                    if nz < .7:
                        continue
                    z = (d - nx * x - ny * y) / nz
                    if abs(z - want) <= .06 and _inside(row, (x, y, z)):
                        tops.append(z)
            assert tops, ("Basement route lacks floor support", label, p)
            support = max(tops)
            # Uphill corner sets standing foot height on a ramp, as in the sim.
            for row in near:
                if not row.get("walkable", True):
                    continue
                for nx, ny, nz, d in row["planes"]:
                    if nz < .7:
                        continue
                    z = (d - nx * x - ny * y + abs(nx) * radius + abs(ny) * radius) / nz
                    if want - .03 <= z <= want + .35:
                        support = max(support, z)
            centre = [x, y, support + height / 2 + .01]
            for row in near:
                lo, hi = row["aabb"]["min"], row["aabb"]["max"]
                if any(centre[k] + half[k] < lo[k] or centre[k] - half[k] > hi[k] for k in range(3)):
                    continue
                separations = [q[0] * centre[0] + q[1] * centre[1] + q[2] * centre[2] - q[3] - sum(abs(q[k]) * half[k] for k in range(3)) for q in row["planes"]]
                assert not all(v < -.0001 for v in separations), ("Basement standing route blocked", label, p, row["name"])
            checked.append([x, y, support])
    return dict(passed=True, supported_samples=len(checked), supported_path=checked,
                player_radius_m=radius, player_height_m=height, routes=len(routes),
                ground_floor_exits_checked=include_gf_exits, integrated_collision_required=True)
