"""Geometry QA of the EXPORTED kit (fresh scene, glTF import), reusing the reviewer's methods (review/*.py) but
reading the kit's own parameters (halo_data.WEIGHT_VISUALS, per-core HALO_<Core>_PIP_<n>_<i> empties,
per-core HALO_PowerCell_<Core>).

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/qa/qa_blender.py" [-- --quick]
Writes qa/qa_report.json:
  topology   standalone meshes + every ASSEMBLED near halo (4 glass arcs + HALO_<Core>_Frame_<Weight>, welded):
             tris, edges with > 2 faces, boundary edges, inverted closed islands, coincident faces
             (arc glass and frames are split by material for the engine, so only their union is a closed shell)
  zones      per core: Head arc centre direction (must be Blender -Y = glTF +Z), Arms +X, Torso +Y, Legs -X
  pips       per core + count: centred row (mean x), gap pip bottom -> Head arc below (mm), pip/arc intersection
  vertical   per core + weight: band hang below the ring bottom (mm), total height, outer diameter at scale
  cells      per core + weight: minimum clearance of the core's cell to ring + band over the orbit, collisions
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
from halo_data import WEIGHT_VISUALS as WV  # noqa: E402

EXP = os.path.join(ROOT, "export")
OUT = HERE
CORES = ("Bulwark", "Mender", "Volt", "Phase")
ZONES = ("Head", "Arms", "Torso", "Legs")
ZONE_DIR = {"Head": (0, -1), "Arms": (1, 0), "Torso": (0, 1), "Legs": (-1, 0)}
QUICK = "--quick" in sys.argv
PIP_H = 0.009

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
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
bpy.context.view_layer.update()


def bm_of(parts, mat=None):
    """One bmesh from one or several mesh objects (optionally transformed)."""
    bm = bmesh.new()
    for o in (parts if isinstance(parts, (list, tuple)) else [parts]):
        me = o.data.copy()
        if mat is not None:
            me.transform(mat)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    bm.verts.ensure_lookup_table()
    return bm


def bvh(parts, mat=None):
    bm = bm_of(parts, mat)
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


def topo(parts):
    bm = bm_of(parts)
    # the glTF exporter splits vertices at UV seams / material borders: weld them back (source topology)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.faces.ensure_lookup_table()
    gt2 = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    inv = 0
    for comp in islands(bm):
        edges = {e for f in comp for e in f.edges}
        if all(len(e.link_faces) == 2 for e in edges) and signed_volume(comp) < 0:
            inv += 1
    co = coincident_faces(bm)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    rec = dict(tris=sum(len(f.verts) - 2 for f in bm.faces), edges_gt2_faces=gt2, boundary_edges=boundary,
               inverted_closed_islands=inv, coincident_face_pairs=co, zero_area_faces=zero)
    bm.free()
    return rec


report = {"topology": {}, "zones": {}, "pips": {}, "vertical": {}, "cells": {}, "cell_view": {}}
problems = []
# ------------------------------------------------------------------ topology
split = [f"HALO_{c}_Arc_" for c in CORES] + [f"HALO_{c}_Frame_" for c in CORES]
for name, o in sorted(objs.items()):
    if o.type != "MESH" or name.startswith(tuple(split)):
        continue
    rec = topo(o)
    rec["uv_layers"] = len(o.data.uv_layers)
    report["topology"][name] = rec
    if rec["edges_gt2_faces"] or rec["boundary_edges"] or rec["inverted_closed_islands"] or \
            rec["coincident_face_pairs"] or rec["zero_area_faces"]:
        problems.append(f"topology {name}: {rec}")
for core in CORES:
    arcs = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES]
    for w in ("Light", "Medium", "Heavy"):
        rec = topo(arcs + [objs[f"HALO_{core}_Frame_{w}"]])
        report["topology"][f"assembled {core} {w} (4 arcs + Frame_{w})"] = rec
        if rec["edges_gt2_faces"] or rec["boundary_edges"] or rec["inverted_closed_islands"] or \
                rec["coincident_face_pairs"] or rec["zero_area_faces"]:
            problems.append(f"topology assembled {core} {w}: {rec}")

# ------------------------------------------------------------------ zone directions
for core in CORES:
    rec = {}
    for z in ZONES:
        vs = [v.co for v in objs[f"HALO_{core}_Arc_{z}"].data.vertices]
        c = sum(vs, Vector()) / len(vs)
        d = Vector((c.x, c.y)).normalized()
        want = Vector(ZONE_DIR[z])
        rec[z] = {"centre_xy": [round(c.x, 4), round(c.y, 4)], "ok": d.dot(want) > 0.95}
        if not rec[z]["ok"]:
            problems.append(f"zone {core} {z}: centre {c.x:.3f}, {c.y:.3f} not toward {tuple(want)}")
    report["zones"][core] = rec

# ------------------------------------------------------------------ pips (centred rows, per core)
pipbm = bm_of(objs["HALO_TierPip"])
for core in CORES:
    head_parts = [objs[f"HALO_{core}_Arc_Head"], objs[f"HALO_{core}_Frame_Light"]]
    head = bvh(head_parts)
    centre = objs[f"HALO_{core}_PIP_Centre"].matrix_world.translation
    rec = {"centre_x_mm": round(centre.x * 1000, 2)}
    for n in range(1, 5):
        ps = [objs[f"HALO_{core}_PIP_{n}_{i}"].matrix_world.translation.copy() for i in range(1, n + 1)]
        mean_x = sum(p.x for p in ps) / n
        gaps, inter = [], []
        for p in ps:
            bottom = p - Vector((0, 0, PIP_H))
            hit = head.ray_cast(bottom + Vector((0, 0, 0.0001)), Vector((0, 0, -1)), 0.2)
            g = None if hit[0] is None else round((bottom.z - hit[0].z) * 1000, 2)
            gaps.append(g)
            b2 = pipbm.copy()
            b2.transform(Matrix.Translation(p))
            inter.append(len(BVHTree.FromBMesh(b2).overlap(head)) > 0)
            b2.free()
            if g is None or g > 1.0:
                problems.append(f"pip {core} {n}: gap {g} mm")
        if any(inter):
            problems.append(f"pip {core} {n}: intersects the Head arc")
        if abs(mean_x) > 1e-4:
            problems.append(f"pip row {core} {n}: not centred (mean x {mean_x * 1000:.2f} mm)")
        rec[f"{n}_pips"] = {"x_mm": [round(p.x * 1000, 1) for p in ps], "mean_x_mm": round(mean_x * 1000, 3),
                            "gap_mm_pip_bottom_to_arc_below": gaps, "pip_intersects_arc": inter}
    report["pips"][core] = rec
pipbm.free()


# ------------------------------------------------------------------ vertical extents / band hang
def zr(parts):
    vs = [v.co for o in parts for v in o.data.vertices]
    return min(v.z for v in vs), max(v.z for v in vs), max(math.hypot(v.x, v.y) for v in vs)


for core in CORES:
    ring = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES] + [objs[f"HALO_{core}_Frame_Light"]]
    ring_bot, ring_top, ring_r = zr(ring)
    for w, v in WV.items():
        rec = {"ring_bottom_mm": round(ring_bot * 1000, 1), "ring_top_mm": round(ring_top * 1000, 1)}
        lo, rmax = ring_bot, ring_r
        if v["band"]:
            bz0, bz1, br = zr([objs[f"HALO_{core}_Band_{v['band']}"]])
            rec.update(band_bottom_mm=round(bz0 * 1000, 1), band_top_mm=round(bz1 * 1000, 1),
                       hang_below_ring_mm=round((ring_bot - bz0) * 1000, 1))
            lo, rmax = min(lo, bz0), max(rmax, br)
            if ring_bot - bz0 > 0.030:
                problems.append(f"band {core} {w} hangs {(ring_bot - bz0) * 1000:.1f} mm")
        s = v["scale"]
        rec.update(total_height_mm_at_scale=round((ring_top - lo) * s * 1000, 1),
                   outer_diameter_m_at_scale=round(2 * rmax * s, 3))
        report["vertical"][f"{core}_{w}"] = rec

# ------------------------------------------------------------------ cells: clearance + visibility (per-core cell)
for core in CORES:
    cell = objs[f"HALO_PowerCell_{core}"]
    cellbm = bm_of(cell)
    cell_pts = [v.co.copy() for v in cell.data.vertices][::3]
    arcs = [objs[f"HALO_{core}_Arc_{z}"] for z in ZONES]
    for w, v in WV.items():
        S = Matrix.Scale(v["scale"], 4)
        T = bvh(arcs + [objs[f"HALO_{core}_Frame_{w}"]], S)

        def cell_mat(a):
            return S @ Matrix.Translation((v["orbit_r"] * math.cos(a), v["orbit_r"] * math.sin(a), v["orbit_z"])) @ \
                Matrix.Rotation(a + math.pi / 2, 4, "Z")
        hits, min_d = 0, 9.0
        for k in range(0, 360, 5 if not QUICK else 15):
            b2 = cellbm.copy()
            b2.transform(cell_mat(math.radians(k)))
            if BVHTree.FromBMesh(b2).overlap(T):
                hits += 1
            for vv in list(b2.verts)[::5]:
                r = T.find_nearest(vv.co)
                if r[0] is not None:
                    min_d = min(min_d, r[3])
            b2.free()
        report["cells"][f"{core}_{w}"] = {"cell": cell.name, "orbit_z": v["orbit_z"], "collisions": hits,
                                          "min_clearance_mm": round(min_d * 1000, 1)}
        if hits:
            problems.append(f"cells collide {core} {w}")
        n = v["cells"]
        for elev in (-2.0, -5.0, -10.0):
            e = math.radians(elev)
            view = Vector((0, -math.cos(e), math.sin(e)))     # direction from the halo toward the viewer
            counts = []
            for ph in range(0, 360 // n, 3 if not QUICK else 6):
                mats = [cell_mat(math.radians(ph + k * 360.0 / n)) for k in range(n)]
                # occluders: ring + band + the OTHER cells (cell-on-cell occlusion)
                vis = 0
                for k in range(n):
                    others = bmesh.new()
                    for j in range(n):
                        if j != k:
                            tmp = cellbm.copy()
                            tmp.transform(mats[j])
                            me = bpy.data.meshes.new("_t")
                            tmp.to_mesh(me)
                            tmp.free()
                            others.from_mesh(me)
                            bpy.data.meshes.remove(me)
                    To = BVHTree.FromBMesh(others) if len(others.faces) else None
                    others.free()
                    ok = 0
                    for p in cell_pts:
                        q = mats[k] @ p
                        blocked = T.ray_cast(q + view * 1e-4, view, 5.0)[0] is not None
                        if not blocked and To is not None:
                            blocked = To.ray_cast(q + view * 1e-4, view, 5.0)[0] is not None
                        ok += not blocked
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
for k, v in report["cells"].items():
    print("  cells", k, v)
for k, v in report["pips"].items():
    print("  pips", k, {n: (r["mean_x_mm"], r["gap_mm_pip_bottom_to_arc_below"]) for n, r in v.items() if n != "centre_x_mm"})
for k, v in report["vertical"].items():
    print("  vertical", k, v)
for p in problems:
    print("PROBLEM", p)
print("QA DONE", len(problems), "problems")
