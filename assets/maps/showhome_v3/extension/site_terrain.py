"""Additional excavations and original low-poly spoil heaps for phase 2.

Import PIT_RECTS into the extension ground cutter; its existing pit() helper owns
the 1.4m excavations. Call build_mounds(root, materials) once for fixed spoil heaps.
No scene reset, exports, catalog writes or new texture generation happen here.
All positions are design world metres, X east/Y north/Z up.
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import common as C


# Existing excavations are retained first to preserve their stable names.
PIT_RECTS = [
    [313, 736, 323, 744],
    [454, 748, 465, 759],
    [315, 806, 326, 817],
    [326, 850, 337, 861],
    [453, 895, 467, 903],
]

# (centre X/Y, major/minor diameter, height, yaw, material, crest skew X/Y).
# The skirt surrounds the pit banks rather than sitting over their cut faces.
MOUND_SPECS = [
    (326, 741, 5.6, 4.2, 1.15, 10, "soil", .08, -.07),
    (317, 824, 8.2, 5.6, 1.75, -8, "sand", -.07, .09),
    (330, 814, 5.7, 4.4, 1.15, 12, "soil", .09, .06),
    (332.5, 873, 7.4, 5.2, 1.70, -6, "sand", -.06, -.09),
    (472, 844, 7.6, 2.6, .80, 0, "sand", .04, -.06),
    (474.5, 898, 9.4, 6.4, 2.00, -10, "soil", -.08, .09),
]

# These are recommendations/authoring checks, not extra invisible collision.
# Individual vehicle/material pads are included to avoid changing their support.
CLEAR_RECTS = [
    ("shared_basement", [339,744,451,896]),
    ("vehicle_ramp", [443.85,847,450.15,873]),
    ("material_yard", [310,748,334,782]),
    ("east_crane_ballast", [463.6,847.6,468.4,852.4]),
    ("west_crane_ballast", [318.6,872.6,323.4,877.4]),
    ("east_cabin_yard", [439.5,862,465,891]),
    ("toilet_door_pad", [469,864,474,867]),
    ("delivery_truck_southeast", [454.3,735,457.7,747]),
    ("delivery_truck_east", [469.3,768,472.7,780]),
    ("delivery_truck_west", [319.8,784,324.2,796]),
    ("delivery_truck_northwest", [318,829,328,841]),
    ("delivery_truck_northeast", [463.3,791,466.7,803]),
]


def _overlap(a, b, epsilon=1e-4):
    return min(a[2], b[2]) - max(a[0], b[0]) > epsilon and min(a[3], b[3]) - max(a[1], b[1]) > epsilon


def _heap_geometry(spec, seed):
    x, y, width, depth, height, yaw, _, skew_x, skew_y = spec
    rx, ry = width / 2, depth / 2
    angle = math.radians(yaw)
    ca, sa = math.cos(angle), math.sin(angle)
    points = []
    # Convex rounded profile: the toe is the steepest part, and the crest flattens.
    # A small linear shear makes the heap asymmetric without introducing a cavity.
    for fraction, radius in ((0, 1), (.70, .48), (.96, .20), (1, .08)):
        for k in range(12):
            a = k * 2 * math.pi / 12
            irregular = 1 + .025 * math.sin(2 * a + seed * .73) + .020 * math.cos(3 * a - seed * .41)
            lx = rx * (radius * irregular * math.cos(a) + skew_x * fraction)
            ly = ry * (radius * irregular * math.sin(a) + skew_y * fraction)
            z = -.06 if fraction == 0 else height * fraction
            points.append((x + ca * lx - sa * ly, y + sa * lx + ca * ly, z))
    bm = bmesh.new()
    vertices = [bm.verts.new(p) for p in points]
    bmesh.ops.convex_hull(bm, input=vertices, use_existing_faces=False)
    unused = [v for v in bm.verts if not v.link_faces]
    if unused:
        bmesh.ops.delete(bm, geom=unused, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    bm.verts.index_update()
    result = ([tuple(v.co) for v in bm.verts], [tuple(v.index for v in face.verts) for face in bm.faces])
    bm.free()
    return result


def build_mounds(root, materials):
    """Build six fixed convex spoil heaps and return JSON-ready metadata records.

    materials must supply existing painted 'soil' and 'sand' Blender materials,
    both with phys='soil' and their repeat_m values. Their shared nodes are kept.
    """
    for key in ("soil", "sand"):
        if key not in materials or materials[key].get("phys") != "soil":
            raise ValueError("Spoil heaps require existing soil/sand materials with phys=soil")
    records = []
    for index, spec in enumerate(MOUND_SPECS):
        verts, faces = _heap_geometry(spec, index)
        lo = [min(v[k] for v in verts) for k in range(3)]
        hi = [max(v[k] for v in verts) for k in range(3)]
        rect = [lo[0], lo[1], hi[0], hi[1]]
        assert 310 <= rect[0] < rect[2] <= 480 and 735 < rect[1] < rect[3] < 905
        for label, protected in CLEAR_RECTS:
            assert not _overlap(rect, protected), ("Spoil heap obstructs protected pad", index, label, rect)
        for pit in PIT_RECTS:
            assert not _overlap(rect, pit), ("Spoil heap overlaps excavation", index, rect, pit)
        for previous in records:
            aabb = previous["aabb"]
            assert not _overlap(rect, [aabb["min"][0], aabb["min"][1], aabb["max"][0], aabb["max"][1]])
        name = "EXT_SpoilMound_" + str(index)
        mat = materials[spec[6]]
        ob = C.mesh(name, verts, faces, mat, root)
        for loop in ob.data.uv_layers[0].data:
            loop.uv /= mat.get("repeat_m", 6)
        C.bc.shade_smooth(ob, 42)
        # Broad, restrained painted-value shifts; this is standard albedo colour,
        # not the independent RGBA mask attribute used on the flat ground meshes.
        colour = ob.data.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
        for face in ob.data.polygons:
            z = sum(ob.data.vertices[i].co.z for i in face.vertices) / len(face.vertices)
            value = .96 + .045 * max(0, z) / spec[4]
            for li in face.loop_indices:
                colour.data[li].color = (value, value, value, 1)
        ob.data.color_attributes.active_color = colour
        ob["part"] = "terrain/mounds"
        ob["source"] = "project original procedural convex spoil heap"
        ob["nominal_size_m"] = [spec[2], spec[3], spec[4]]
        co = C.col_mesh(name, verts, faces, "soil", walkable=True, parent=root)
        ob["collision"] = co.name
        row = C.collision_rows([co])[0]
        records.append(dict(
            name=name, position=[spec[0], spec[1], 0], nominal_size_m=[spec[2], spec[3], spec[4]],
            yaw_deg=spec[5], painted_material=mat.name, phys="soil", part="terrain/mounds",
            triangles=C.triangles([ob]), collision=co.name, collision_volumes=1,
            convex_collision=True, closed_collision=True, walkable=True,
            min_thickness_m=row["thickness_m"], aabb=row["aabb"],
            uv_repeat_m=mat.get("repeat_m", 6), actor_pads_clear=True,
        ))
    return records
