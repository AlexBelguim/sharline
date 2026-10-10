"""Review round 2: independent technical checks on the EXPORTED .glb/.fbx files (fresh factory scene import).

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/review/r2/r2_checks.py"
Writes review/r2/r2_checks_report.json and prints a summary.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

ROOT = r"F:/git/val etf/assets/shields"
EXP = os.path.join(ROOT, "export")
OUT = os.path.join(ROOT, "review", "r2")
CORES = ("Bulwark", "Mender", "Volt", "Phase")
ZONES = ("Head", "Arms", "Torso", "Legs")
CAT = json.load(open(os.path.join(ROOT, "armor_catalog.example.json"), encoding="utf-8"))

bpy.ops.wm.read_factory_settings(use_empty=True)


def imp(path):
    before = set(bpy.data.objects)
    if path.endswith(".glb"):
        bpy.ops.import_scene.gltf(filepath=path, merge_vertices=True)
    else:
        bpy.ops.import_scene.fbx(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


objs = {}
for f in ("HALO_Bulwark", "HALO_Mender", "HALO_Volt", "HALO_Phase", "HALO_Common", "HALO_Pickups"):
    for o in imp(os.path.join(EXP, f + ".glb")):
        objs[o.name] = o
for o in objs.values():
    if o.type == "MESH":
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
bpy.context.view_layer.update()
report = {"imported": len(objs)}

# weight visuals from the catalog the build wrote (scale, cells, orbit)
wv = CAT.get("weight_class_visuals") or CAT.get("rules", {}).get("weight_class_visuals")
report["weight_class_visuals"] = wv
print("weight visuals:", wv)


def bm_of(o, mat=None):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    if mat is not None:
        bm.transform(mat)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


def islands(bm):
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
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


def bvh(o, mat=None):
    bm = bm_of(o, mat)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


# ------------------------------------------------------------------ per-mesh topology
report["meshes"] = {}
for name, o in sorted(objs.items()):
    if o.type != "MESH":
        continue
    bm = bm_of(o)
    # glTF splits vertices per primitive and per hard edge: weld by position before judging topology
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    tiny = [f for f in bm.faces if f.calc_area() < 1e-10]
    tiny_loc = [[round(c, 4) for c in f.calc_center_median()] for f in tiny[:4]]
    isl = islands(bm)
    inverted = closed = 0
    for comp in isl:
        edges = {e for f in comp for e in f.edges}
        if all(len(e.link_faces) == 2 for e in edges):
            closed += 1
            if signed_volume(comp) < 0:
                inverted += 1
    # islands of the same object that intersect each other (overlapping triangles between islands)
    t = BVHTree.FromBMesh(bm)
    island_of = {}
    for k, comp in enumerate(isl):
        for f in comp:
            island_of[f.index] = k
    # BVH built on bmesh faces; overlap with itself returns face index pairs
    selfo = t.overlap(t)
    cross_island = {tuple(sorted((island_of[a], island_of[b]))) for a, b in selfo
                    if island_of.get(a) != island_of.get(b)}
    mn = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
    mx = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
    report["meshes"][name] = dict(
        tris=sum(len(f.verts) - 2 for f in bm.faces), uv_layers=len(o.data.uv_layers),
        mats=[m.name if m else None for m in o.data.materials],
        non_manifold=sum(1 for e in bm.edges if not e.is_manifold),
        boundary=sum(1 for e in bm.edges if e.is_boundary),
        loose=sum(1 for v in bm.verts if not v.link_edges),
        zero_area_faces=len(tiny), zero_area_at=tiny_loc, islands=len(isl), closed=closed, inverted=inverted,
        intersecting_island_pairs=len(cross_island),
        bbox_min=[round(x, 4) for x in mn], bbox_max=[round(x, 4) for x in mx])
    bm.free()

# ------------------------------------------------------------------ origin: every arc/band centred on the halo axis
report["origin"] = {}
for core in CORES:
    xs = []
    for z in ZONES:
        o = objs[f"HALO_{core}_Arc_{z}"]
        xs.append(tuple(round(c, 4) for c in o.location))
    report["origin"][core] = xs

# ------------------------------------------------------------------ arcs: zone directions (centroid azimuth)
report["zone_azimuth_deg"] = {}
for core in CORES:
    for z in ZONES:
        o = objs[f"HALO_{core}_Arc_{z}"]
        c = sum((v.co for v in o.data.vertices), Vector()) / len(o.data.vertices)
        report["zone_azimuth_deg"][f"{core}_{z}"] = round(math.degrees(math.atan2(c.y, c.x)) % 360, 1)

# ------------------------------------------------------------------ part-vs-part intersections (arc/arc, arc/band)
report["part_overlap_tri_pairs"] = {}
for core in CORES:
    arcs = {z: bvh(objs[f"HALO_{core}_Arc_{z}"]) for z in ZONES}
    for i, a in enumerate(ZONES):
        for b in ZONES[i + 1:]:
            n = len(arcs[a].overlap(arcs[b]))
            if n:
                report["part_overlap_tri_pairs"][f"{core}_{a}_x_{b}"] = n
    for w in ("Medium", "Heavy"):
        band = bvh(objs[f"HALO_{core}_Band_{w}"])
        for z in ZONES:
            n = len(band.overlap(arcs[z]))
            report["part_overlap_tri_pairs"][f"{core}_Band{w}_x_{z}"] = n

# ------------------------------------------------------------------ coplanar overlapping faces between parts (z-fight)
def face_list(o):
    me = o.data
    return [(p.center.copy(), p.normal.copy(), p.area) for p in me.polygons]


report["zfight_pairs"] = {}
for core in CORES:
    for w in ("Medium", "Heavy"):
        band = face_list(objs[f"HALO_{core}_Band_{w}"])
        kd = KDTree(len(band))
        for i, (c, n, a) in enumerate(band):
            kd.insert(c, i)
        kd.balance()
        cnt = 0
        for z in ZONES:
            for c, n, a in face_list(objs[f"HALO_{core}_Arc_{z}"]):
                for co, j, d in kd.find_range(c, 0.002):
                    c2, n2, a2 = band[j]
                    if abs(n.dot(n2)) > 0.995 and abs((c - c2).dot(n)) < 5e-5:
                        cnt += 1
        report["zfight_pairs"][f"{core}_{w}"] = cnt

# ------------------------------------------------------------------ pips: per-core seat
report["pips"] = {}
pipbm = bm_of(objs["HALO_TierPip"])
pip_h = (max(v.co.z for v in pipbm.verts) - min(v.co.z for v in pipbm.verts)) / 2
for core in CORES:
    head = bvh(objs[f"HALO_{core}_Arc_Head"])
    rows = []
    for i in range(1, 5):
        p = objs[f"HALO_{core}_PIP_{i}"].matrix_world.translation.copy()
        bottom = p - Vector((0, 0, pip_h))
        hit = head.ray_cast(bottom + Vector((0, 0, 1e-4)), Vector((0, 0, -1)), 0.2)
        b2 = pipbm.copy()
        b2.transform(Matrix.Translation(p))
        inter = len(BVHTree.FromBMesh(b2).overlap(head)) > 0
        b2.free()
        rows.append({"pos": [round(c, 4) for c in p],
                     "gap_mm": None if hit[0] is None else round((bottom.z - hit[0].z) * 1000, 2),
                     "intersects": inter})
    report["pips"][core] = rows
pipbm.free()

# ------------------------------------------------------------------ cells: clearance over the orbit, all weights
cellbm = bm_of(objs["HALO_PowerCell"])
report["cells"] = {}
for core in CORES:
    for wname, v in wv.items():
        sc = v.get("halo_scale", v.get("scale"))
        band = v.get("band_mesh") or v.get("band")
        orb_r = v.get("orbit_radius_local", v.get("orbit_r"))
        orb_z = v.get("orbit_height_local", v.get("orbit_z"))
        S = Matrix.Scale(sc, 4)
        parts = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES]
        if band:
            bn = band if band.startswith("HALO_") else f"HALO_{core}_Band_{band}"
            bn = bn.replace("<Core>", core).replace("{core}", core)
            if bn in objs:
                parts.append(objs[bn])
        trees = [bvh(p, S) for p in parts]
        hits, min_d = 0, 9.0
        for k in range(72):
            a = math.radians(k * 5.0)
            M = S @ Matrix.Translation(Vector((orb_r * math.cos(a), orb_r * math.sin(a), orb_z))) @ \
                Matrix.Rotation(a + math.pi / 2, 4, "Z")
            b2 = cellbm.copy()
            b2.transform(M)
            t = BVHTree.FromBMesh(b2)
            if any(t.overlap(tr) for tr in trees):
                hits += 1
            for vv in list(b2.verts)[::5]:
                for tr in trees:
                    r = tr.find_nearest(vv.co)
                    if r[0] is not None:
                        min_d = min(min_d, r[3])
            b2.free()
        report["cells"][f"{core}_{wname}"] = {"colliding_of_72": hits, "min_clearance_mm": round(min_d * 1000, 1),
                                              "parts": [p.name for p in parts]}
cellbm.free()

# ------------------------------------------------------------------ envelope per core x weight
report["envelope"] = {}
for core in CORES:
    for wname, v in wv.items():
        sc = v.get("halo_scale", v.get("scale"))
        band = {"Light": None, "Medium": "Medium", "Heavy": "Heavy"}[wname]
        parts = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES] + (
            [objs[f"HALO_{core}_Band_{band}"]] if band else [])
        zs = [vv.co.z for p in parts for vv in p.data.vertices]
        rmax = max(math.hypot(vv.co.x, vv.co.y) for p in parts for vv in p.data.vertices)
        rmin = min(math.hypot(vv.co.x, vv.co.y) for p in parts for vv in p.data.vertices)
        report["envelope"][f"{core}_{wname}"] = {
            "z_min_mm": round(min(zs) * sc * 1000, 1), "z_max_mm": round(max(zs) * sc * 1000, 1),
            "outer_diam_m": round(2 * rmax * sc, 3), "inner_diam_m": round(2 * rmin * sc, 3),
            "head_clear_mm": round((0.22 + min(zs) * sc) * 1000, 1)}

# ------------------------------------------------------------------ FBX re-import vs GLB bounds
report["fbx_vs_glb"] = {}
for f in ("HALO_Bulwark", "HALO_Volt", "HALO_Common", "HALO_Pickups"):
    new = imp(os.path.join(EXP, f + ".fbx"))
    bpy.context.view_layer.update()
    for o in new:
        if o.type != "MESH":
            continue
        base = o.name.split(".")[0]
        if base not in objs:
            report["fbx_vs_glb"][o.name] = "no glb twin"
            continue
        wm = o.matrix_world
        ws = [wm @ v.co for v in o.data.vertices]
        mn = [min(p[i] for p in ws) for i in range(3)]
        mx = [max(p[i] for p in ws) for i in range(3)]
        g = report["meshes"][base]
        dev = max(max(abs(mn[i] - g["bbox_min"][i]), abs(mx[i] - g["bbox_max"][i])) for i in range(3))
        if dev > 5e-4:
            report["fbx_vs_glb"][o.name] = round(dev * 1000, 2)
    report["fbx_vs_glb"][f] = "ok" if not any(isinstance(v, float) for k, v in report["fbx_vs_glb"].items()
                                               if k.startswith(f)) else "DIFF"
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)

json.dump(report, open(os.path.join(OUT, "r2_checks_report.json"), "w"), indent=1)
print("=== MESH CHECKS ===")
for n, r in report["meshes"].items():
    flag = "" if not (r["non_manifold"] or r["boundary"] or r["loose"] or r["zero_area_faces"] or r["inverted"]) \
        else "  <<<"
    print(f"{n:<30} tris={r['tris']:<5} uv={r['uv_layers']} nonman={r['non_manifold']} bnd={r['boundary']} "
          f"loose={r['loose']} zeroA={r['zero_area_faces']} isl={r['islands']} closed={r['closed']} "
          f"inv={r['inverted']} isl_x={r['intersecting_island_pairs']}{flag} {r['zero_area_at'] if r['zero_area_at'] else ''}")
for k in ("origin", "zone_azimuth_deg", "part_overlap_tri_pairs", "zfight_pairs", "pips", "cells", "envelope",
          "fbx_vs_glb"):
    print("===", k.upper(), "===")
    v = report[k]
    if isinstance(v, dict):
        for kk, vv in v.items():
            print(" ", kk, vv)
print("DONE")
