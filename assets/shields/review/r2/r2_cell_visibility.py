"""Review round 2: how many power cells does a player actually see?  Orthographic rays from a viewer at
elevation e (negative = below the halo), azimuth 0, for every orbit phase.  Unlike the builder's QA this also counts
cells hidden by OTHER cells (near and far cell lined up along the line of sight).  A cell counts as visible when
>= 35 % of its sample points reach the viewer unoccluded by the ring, the band or another cell.
Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/review/r2/r2_cell_visibility.py"
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

EXP = r"F:/git/val etf/assets/shields/export"
OUT = r"F:/git/val etf/assets/shields/review/r2"
CORES = ("Bulwark", "Mender", "Volt", "Phase")
WEIGHT = {"Light": (0.85, None, 0.215, 1), "Medium": (1.0, "Medium", 0.245, 2), "Heavy": (1.2, "Heavy", 0.275, 3)}
ORBIT_Z = 0.058

bpy.ops.wm.read_factory_settings(use_empty=True)
K = {}
for f in CORES + ("Common",):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(EXP, f"HALO_{f}.glb"))
    for o in set(bpy.data.objects) - before:
        K[o.name] = o
for o in K.values():
    if o.type == "MESH":
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)


def tree(items):
    bm = bmesh.new()
    for o, M in items:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(M)
        me = bpy.data.meshes.new("_t")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


cell = K["HALO_PowerCell"]
cell_pts = [v.co.copy() for v in cell.data.vertices][::4]
res = {}
for elev in (-2.0, -5.0, -10.0):
    e = math.radians(elev)
    view = Vector((0, -math.cos(e), math.sin(e)))
    for core in CORES:
        for w, (sc, band, orb, n) in WEIGHT.items():
            S = Matrix.Scale(sc, 4)
            parts = [(K[f"HALO_{core}_Arc_{z}"], S) for z in ("Head", "Arms", "Torso", "Legs")]
            if band:
                parts.append((K[f"HALO_{core}_Band_{band}"], S))
            counts = []
            for ph in range(0, 360 // n, 3):
                Ms = []
                for k in range(n):
                    a = math.radians(ph + k * 360.0 / n)
                    Ms.append(S @ Matrix.Translation((orb * math.cos(a), orb * math.sin(a), ORBIT_Z)) @
                              Matrix.Rotation(a + math.pi / 2, 4, "Z"))
                vis = 0
                for k in range(n):
                    T = tree(parts + [(cell, Ms[j]) for j in range(n) if j != k])
                    ok = sum(T.ray_cast(Ms[k] @ p + view * 1e-4, view, 5.0)[0] is None for p in cell_pts)
                    vis += ok / len(cell_pts) >= 0.35
                counts.append(vis)
            frac = {c: round(counts.count(c) / len(counts), 2) for c in sorted(set(counts))}
            res[f"{elev:g}deg_{core}_{w}"] = {"true_cells": n, "visible_count_fraction_of_orbit": frac,
                                              "true_count_fraction": frac.get(n, 0.0)}
            print(f"{elev:>5}deg {core:<8} {w:<6} cells={n} true count shown {frac.get(n, 0.0):.0%}  dist {frac}")
json.dump(res, open(os.path.join(OUT, "r2_cell_visibility_report.json"), "w"), indent=1)
print("DONE")
