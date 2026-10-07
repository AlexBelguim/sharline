"""Geometry QA of the EXPORTED kit (fresh scene, glTF import), reusing the reviewer's methods (review/*.py) but
reading the kit's own parameters (halo_data.WEIGHT_VISUALS, per-core HALO_<Core>_PIP_* empties).

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/qa/qa_blender.py" [-- --quick]
Writes qa/qa_report.json:
  topology   per mesh: tris, edges with > 2 faces, boundary edges, inverted closed islands, coincident faces
  pips       per core: gap from each pip bottom to the Head arc below it (mm) and pip/arc intersection
  vertical   per core + weight: band hang below the ring bottom (mm), total height, outer diameter at scale
  cells      per core + weight: minimum clearance to ring + band over the orbit (mm), collisions
  cell_view  per elevation (-2 / -5 / -10 deg) + core + weight: fraction of the orbit showing the TRUE count
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
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
from halo_data import WEIGHT_VISUALS as WV  # noqa: E402

EXP = os.path.join(ROOT, "export")
OUT = os.path.join(ROOT, "qa")
CORES = ("Bulwark", "Mender", "Volt", "Phase")
ZONES = ("Head", "Arms", "Torso", "Legs")
QUICK = "--quick" in sys.argv

bpy.ops.wm.read_factory_settings(use_empty=True)
objs = {}
for f in ("HALO_Bulwark", "HALO_Mender", "HALO_Volt", "HALO_Phase", "HALO_Common", "HALO_Pickups"):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(EXP, f + ".glb"))
    for o in set(bpy.data.objects) - before:
        objs[o.name] = o
bpy.context.view_layer.update()
for o in objs.values():
    if o.type == "MESH":
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
bpy.context.view_layer.update()


def bm_of(o, mat=None):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    if mat is not None:
        bm.transform(mat)
    bm.verts.ensure_lookup_table()
    return bm


def bvh(o, mat=Matrix.Identity(4)):
    bm = bm_of(o, mat)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def bvh_many(parts, mat):
    bm = bmesh.new()
    for o in parts:
        tmp = bm_of(o, mat)
        me = bpy.data.meshes.new("_t")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


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
        vs = [lp.vert.co for lp in f.loops]
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


report = {"topology": {}, "pips": {}, "vertical": {}, "cells": {}, "cell_view": {}}
problems = []
# ------------------------------------------------------------------ topology
for name, o in sorted(objs.items()):
    if o.type != "MESH":
        continue
    bm = bm_of(o)
    # the glTF exporter splits vertices at UV seams / material borders: weld them back (source topology)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    gt2 = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    inv = 0
    for comp in islands(bm):
        edges = {e for f in comp for e in f.edges}
        if all(len(e.link_faces) == 2 for e in edges) and signed_volume(comp) < 0:
            inv += 1
    co = coincident_faces(bm)
    report["topology"][name] = dict(tris=sum(len(f.verts) - 2 for f in bm.faces), edges_gt2_faces=gt2,
                                    boundary_edges=boundary, inverted_closed_islands=inv, coincident_face_pairs=co,
                                    uv_layers=len(o.data.uv_layers))
    if gt2 or boundary or inv or co:
        problems.append(f"topology {name}: >2f={gt2} boundary={boundary} inverted={inv} coincident={co}")
    bm.free()

# ------------------------------------------------------------------ pips (per-core empties)
pip_h = 0.009
pipbm = bm_of(objs["HALO_TierPip"])
for core in CORES:
    head = bvh(objs[f"HALO_{core}_Arc_Head"])
    gaps, inter = [], []
    for i in range(1, 5):
        p = objs[f"HALO_{core}_PIP_{i}"].matrix_world.translation.copy()
        bottom = p - Vector((0, 0, pip_h))
        hit = head.ray_cast(bottom + Vector((0, 0, 0.0001)), Vector((0, 0, -1)), 0.2)
        g = None if hit[0] is None else round((bottom.z - hit[0].z) * 1000, 2)
        gaps.append(g)
        b2 = pipbm.copy()
        b2.transform(Matrix.Translation(p))
        inter.append(len(BVHTree.FromBMesh(b2).overlap(head)) > 0)
        b2.free()
        if g is None or g > 1.0:
            problems.append(f"pip {core} {i}: gap {g} mm")
    report["pips"][core] = {"gap_mm_pip_bottom_to_arc_below": gaps, "pip_intersects_arc": inter}
pipbm.free()


# ------------------------------------------------------------------ vertical extents / band hang
def zr(o, mat=Matrix.Identity(4)):
    vs = [mat @ v.co for v in o.data.vertices]
    return min(v.z for v in vs), max(v.z for v in vs), max(math.hypot(v.x, v.y) for v in vs)


for core in CORES:
    arcs = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES]
    ring_bot = min(zr(a)[0] for a in arcs)
    ring_top = max(zr(a)[1] for a in arcs)
    for w, v in WV.items():
        rec = {"ring_bottom_mm": round(ring_bot * 1000, 1), "ring_top_mm": round(ring_top * 1000, 1)}
        lo, rmax = ring_bot, max(zr(a)[2] for a in arcs)
        if v["band"]:
            b = objs[f"HALO_{core}_Band_{v['band']}"]
            bz0, bz1, br = zr(b)
            rec.update(band_bottom_mm=round(bz0 * 1000, 1), band_top_mm=round(bz1 * 1000, 1),
                       hang_below_ring_mm=round((ring_bot - bz0) * 1000, 1))
            lo, rmax = min(lo, bz0), max(rmax, br)
            if ring_bot - bz0 > 0.030:
                problems.append(f"band {core} {w} hangs {(ring_bot - bz0) * 1000:.1f} mm")
        s = v["scale"]
        rec.update(total_height_mm_at_scale=round((ring_top - lo) * s * 1000, 1),
                   outer_diameter_m_at_scale=round(2 * rmax * s, 3))
        report["vertical"][f"{core}_{w}"] = rec

# ------------------------------------------------------------------ cells: clearance + visibility
cell = objs["HALO_PowerCell"]
cellbm = bm_of(cell)
cell_pts = [v.co.copy() for v in cell.data.vertices][::5]
for core in CORES:
    for w, v in WV.items():
        S = Matrix.Scale(v["scale"], 4)
        parts = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES]
        if v["band"]:
            parts.append(objs[f"HALO_{core}_Band_{v['band']}"])
        T = bvh_many(parts, S)
        hits, min_d = 0, 9.0
        for k in range(0, 360, 5 if not QUICK else 15):
            a = math.radians(k)
            M = S @ Matrix.Translation((v["orbit_r"] * math.cos(a), v["orbit_r"] * math.sin(a), v["orbit_z"])) @ \
                Matrix.Rotation(a + math.pi / 2, 4, "Z")
            b2 = cellbm.copy()
            b2.transform(M)
            if BVHTree.FromBMesh(b2).overlap(T):
                hits += 1
            for vv in list(b2.verts)[::7]:
                r = T.find_nearest(vv.co)
                if r[0] is not None:
                    min_d = min(min_d, r[3])
            b2.free()
        report["cells"][f"{core}_{w}"] = {"collisions": hits, "min_clearance_mm": round(min_d * 1000, 1)}
        if hits:
            problems.append(f"cells collide {core} {w}")
        n = v["cells"]
        for elev in (-2.0, -5.0, -10.0):
            e = math.radians(elev)
            view = Vector((0, -math.cos(e), math.sin(e)))     # direction from the halo toward the viewer
            counts = []
            for ph in range(0, 360 // n, 3 if not QUICK else 6):
                vis = 0
                for k in range(n):
                    a = math.radians(ph + k * 360.0 / n)
                    M = S @ Matrix.Translation((v["orbit_r"] * math.cos(a), v["orbit_r"] * math.sin(a),
                                                v["orbit_z"])) @ Matrix.Rotation(a + math.pi / 2, 4, "Z")
                    ok = 0
                    for p in cell_pts:
                        q = M @ p
                        ok += T.ray_cast(q + view * 1e-4, view, 5.0)[0] is None
                    vis += ok / len(cell_pts) >= 0.25
                counts.append(vis)
            true_frac = round(counts.count(n) / len(counts), 3)
            report["cell_view"][f"{elev:g}deg_{core}_{w}"] = {
                "true_cells": n, "true_count_fraction": true_frac,
                "distribution": {c: round(counts.count(c) / len(counts), 2) for c in sorted(set(counts))}}
            if elev > -6 and true_frac < 0.90:
                problems.append(f"cell count at {elev:g} deg {core} {w}: true count only {true_frac:.0%}")
cellbm.free()

report["problems"] = problems
json.dump(report, open(os.path.join(OUT, "qa_report.json"), "w"), indent=1)
for k, v in report["cell_view"].items():
    print(f"  {k:<28} true count {v['true_count_fraction']:.0%}   {v['distribution']}")
for k, v in report["pips"].items():
    print("  pips", k, v)
for k, v in report["vertical"].items():
    print("  vertical", k, v)
for p in problems:
    print("PROBLEM", p)
print("QA DONE", len(problems), "problems")
