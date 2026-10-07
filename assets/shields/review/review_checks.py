"""Independent technical checks of the HALO kit, run on the EXPORTED .glb files (fresh scene import).

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/review/review_checks.py"
Writes review/checks_report.json and prints a summary.
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

ROOT = r"F:/git/val etf/assets/shields"
EXP = os.path.join(ROOT, "export")
OUT = os.path.join(ROOT, "review")
CORES = ("Bulwark", "Mender", "Volt", "Phase")
ZONES = ("Head", "Arms", "Torso", "Legs")
WEIGHT = {"Light": (0.85, None, 0.215), "Medium": (1.0, "Medium", 0.245), "Heavy": (1.2, "Heavy", 0.275)}
ORBIT_Z = 0.004

bpy.ops.wm.read_factory_settings(use_empty=True)


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


objs = {}
for f in ("HALO_Bulwark", "HALO_Mender", "HALO_Volt", "HALO_Phase", "HALO_Common", "HALO_Pickups",
          "HALO_Materials"):
    for o in imp(os.path.join(EXP, f + ".glb")):
        objs[o.name] = o
print("IMPORTED", len(objs), "objects")
# importer may leave Y-up -> Z-up conversion on the objects; bake world matrices into the data for analysis
for o in objs.values():
    if o.type == "MESH":
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
bpy.context.view_layer.update()


def bm_of(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.verts.ensure_lookup_table()
    return bm


def islands(bm):
    seen = set()
    out = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        comp = []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        out.append(comp)
    return out


def signed_volume(faces):
    v = 0.0
    for f in faces:
        vs = [l.vert.co for l in f.loops]
        for i in range(1, len(vs) - 1):
            v += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
    return v


def coincident_faces(bm, tol=2e-5):
    kd = KDTree(len(bm.faces))
    cents = []
    for f in bm.faces:
        c = f.calc_center_median()
        cents.append((c, f.normal.copy(), f.calc_area()))
        kd.insert(c, f.index)
    kd.balance()
    pairs = 0
    for i, (c, n, a) in enumerate(cents):
        for (co, j, d) in kd.find_range(c, tol):
            if j <= i:
                continue
            if abs(n.dot(cents[j][1])) > 0.999 and a > 1e-9 and abs(cents[j][2] - a) / a < 0.05:
                pairs += 1
    return pairs


report = {"meshes": {}}
for name, o in sorted(objs.items()):
    if o.type != "MESH" or name.startswith("HALO_Swatch"):
        continue
    me = o.data
    bm = bm_of(o)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    nonman = [e for e in bm.edges if not e.is_manifold]
    boundary = [e for e in bm.edges if e.is_boundary]
    loose_v = [v for v in bm.verts if not v.link_edges]
    loose_e = [e for e in bm.edges if not e.link_faces]
    tiny = [f for f in bm.faces if f.calc_area() < 1e-10]
    isl = islands(bm)
    inverted, closed = 0, 0
    for comp in isl:
        edges = {e for f in comp for e in f.edges}
        if all(len(e.link_faces) == 2 for e in edges):
            closed += 1
            if signed_volume(comp) < 0:
                inverted += 1
    co = coincident_faces(bm)
    mn = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
    mx = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
    rmax = max(math.hypot(v.co.x, v.co.y) for v in bm.verts)
    rmin = min(math.hypot(v.co.x, v.co.y) for v in bm.verts)
    report["meshes"][name] = dict(
        tris=tris, verts=len(bm.verts), uv_layers=len(me.uv_layers), materials=[m.name if m else None for m in
                                                                                   me.materials],
        non_manifold_edges=len(nonman), boundary_edges=len(boundary), loose_verts=len(loose_v),
        loose_edges=len(loose_e), zero_area_faces=len(tiny), islands=len(isl), closed_islands=closed,
        inverted_closed_islands=inverted, coincident_face_pairs=co,
        bbox_min=[round(x, 4) for x in mn], bbox_max=[round(x, 4) for x in mx],
        r_min=round(rmin, 4), r_max=round(rmax, 4))
    bm.free()

# ---------------------------------------------------------------- arc seams: gaps between neighbouring arcs
# ---------------------------------------------------------------- pip float gap per core (pip bottom vs arc top)
PIPS = [objs[f"HALO_PIP_{i}"].matrix_world.translation.copy() for i in range(1, 5)]
pip_h = 0.009
report["pips"] = {"positions_blender": [[round(c, 4) for c in p] for p in PIPS]}


def bvh(o, mat=Matrix.Identity(4)):
    bm = bm_of(o)
    bm.transform(mat)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


for core in CORES:
    head = bvh(objs[f"HALO_{core}_Arc_Head"])
    gaps = []
    for p in PIPS:
        bottom = p - Vector((0, 0, pip_h))
        hit = head.ray_cast(bottom + Vector((0, 0, 0.0001)), Vector((0, 0, -1)), 0.2)
        gaps.append(None if hit[0] is None else round((bottom.z - hit[0].z) * 1000, 2))
    # also: does the pip intersect the arc?
    pipbm = bm_of(objs["HALO_TierPip"])
    inter = []
    for p in PIPS:
        b2 = pipbm.copy()
        b2.transform(Matrix.Translation(p))
        t = BVHTree.FromBMesh(b2)
        inter.append(len(t.overlap(head)) > 0)
        b2.free()
    pipbm.free()
    report["pips"][core] = {"gap_mm_pip_bottom_to_arc_below": gaps, "pip_intersects_arc": inter}

# ---------------------------------------------------------------- cells vs ring + band (collision sweep)
cell = objs["HALO_PowerCell"]
cellbm = bm_of(cell)
report["cells"] = {}
for core in CORES:
    for wname, (sc, band, orb) in WEIGHT.items():
        S = Matrix.Scale(sc, 4)
        parts = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES]
        if band:
            parts.append(objs[f"HALO_{core}_Band_{band}"])
        trees = [bvh(p, S) for p in parts]
        hits = 0
        min_d = 9.0
        for k in range(72):
            a = math.radians(k * 5.0)
            M = Matrix.Translation(Vector((orb * math.cos(a), orb * math.sin(a), ORBIT_Z)) * 1.0)
            M = S @ M @ Matrix.Rotation(a + math.pi / 2, 4, "Z")
            b2 = cellbm.copy()
            b2.transform(M)
            t = BVHTree.FromBMesh(b2)
            if any(t.overlap(tr) for tr in trees):
                hits += 1
            for v in list(b2.verts)[::7]:
                for tr in trees:
                    r = tr.find_nearest(v.co)
                    if r[0] is not None:
                        min_d = min(min_d, r[3])
            b2.free()
        report["cells"][f"{core}_{wname}"] = {"orbit_samples_colliding_of_72": hits,
                                              "min_clearance_mm": round(min_d * 1000, 1)}
cellbm.free()

# ---------------------------------------------------------------- vertical extents per weight (head clearance)
report["vertical"] = {}
for core in CORES:
    for wname, (sc, band, orb) in WEIGHT.items():
        parts = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES] + ([objs[f"HALO_{core}_Band_{band}"]] if band else [])
        zmin = min(v.co.z for p in parts for v in p.data.vertices) * sc
        zmax = max(v.co.z for p in parts for v in p.data.vertices) * sc
        rmax = max(math.hypot(v.co.x, v.co.y) for p in parts for v in p.data.vertices) * sc
        report["vertical"][f"{core}_{wname}"] = {"z_min_mm": round(zmin * 1000, 1), "z_max_mm": round(zmax * 1000, 1),
                                                 "height_mm": round((zmax - zmin) * 1000, 1),
                                                 "outer_diameter_m": round(2 * rmax, 3),
                                                 "clearance_above_head_top_mm": round((0.22 + zmin) * 1000, 1)}

# ---------------------------------------------------------------- arc angular coverage of glass per core/zone
report["glass_coverage_deg"] = {}
for core in CORES:
    for z in ZONES:
        o = objs[f"HALO_{core}_Arc_{z}"]
        me = o.data
        angs = set()
        for p in me.polygons:
            if p.material_index == 0:
                for vi in p.vertices:
                    v = me.vertices[vi].co
                    angs.add(round(math.degrees(math.atan2(v.y, v.x)) % 360, 0))
        report["glass_coverage_deg"][f"{core}_{z}"] = len(angs)

# ---------------------------------------------------------------- materials after import
report["materials"] = {}
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if p is None:
        continue
    report["materials"][m.name] = {
        "base": [round(x, 3) for x in p.inputs["Base Color"].default_value[:3]],
        "alpha": round(p.inputs["Alpha"].default_value, 3),
        "emission": [round(x, 3) for x in p.inputs["Emission Color"].default_value[:3]],
        "emission_strength": round(p.inputs["Emission Strength"].default_value, 3),
        "rough": round(p.inputs["Roughness"].default_value, 3),
        "metal": round(p.inputs["Metallic"].default_value, 3)}

json.dump(report, open(os.path.join(OUT, "checks_report.json"), "w"), indent=1)
print("=== MESH CHECKS ===")
for n, r in report["meshes"].items():
    print(f"{n:<26} tris={r['tris']:<5} uv={r['uv_layers']} nonman={r['non_manifold_edges']:<4} "
          f"boundary={r['boundary_edges']:<4} looseV={r['loose_verts']} looseE={r['loose_edges']} "
          f"zeroA={r['zero_area_faces']} isl={r['islands']:<3} closed={r['closed_islands']:<3} "
          f"inv={r['inverted_closed_islands']} coinc={r['coincident_face_pairs']} r={r['r_min']}..{r['r_max']}")
print("=== PIPS ===")
for k, v in report["pips"].items():
    print(k, v)
print("=== CELLS ===")
for k, v in report["cells"].items():
    print(k, v)
print("=== VERTICAL ===")
for k, v in report["vertical"].items():
    print(k, v)
print("=== GLASS COVERAGE (distinct whole degrees with glass verts) ===")
print(report["glass_coverage_deg"])
print("=== MATERIALS (re-imported) ===")
for k, v in report["materials"].items():
    print(k, v)
