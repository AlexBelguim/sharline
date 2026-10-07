"""How many power cells can a player actually see at in-play angles?  Orthographic rays from a viewer at
elevation e (negative = below the halo), azimuth 0 (in front), against the arcs + band of each core/weight, for
every orbit phase.  A cell counts as visible when >= 25 % of its sample points are unoccluded.
Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/review/review_cell_visibility.py"
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

EXP = r"F:/git/val etf/assets/shields/export"
OUT = r"F:/git/val etf/assets/shields/review"
CORES = ("Bulwark", "Mender", "Volt", "Phase")
WEIGHT = {"Light": (0.85, None, 0.215, 1), "Medium": (1.0, "Medium", 0.245, 2), "Heavy": (1.2, "Heavy", 0.275, 3)}

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


def tree(objs, S):
    bm = bmesh.new()
    for o in objs:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(S)
        me = bpy.data.meshes.new("_t")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


cell_pts = [v.co.copy() for v in K["HALO_PowerCell"].data.vertices][::5]
res = {}
for elev in (-2.0, -5.0, -10.0):
    e = math.radians(elev)
    view = Vector((0, -math.cos(e), math.sin(e)))     # direction from halo toward the viewer
    for core in CORES:
        for w, (sc, band, orb, n) in WEIGHT.items():
            S = Matrix.Scale(sc, 4)
            parts = [K[f"HALO_{core}_Arc_{z}"] for z in ("Head", "Arms", "Torso", "Legs")]
            if band:
                parts.append(K[f"HALO_{core}_Band_{band}"])
            T = tree(parts, S)
            counts = []
            for ph in range(0, 360 // n, 3):
                vis = 0
                for k in range(n):
                    a = math.radians(ph + k * 360.0 / n)
                    M = S @ Matrix.Translation((orb * math.cos(a), orb * math.sin(a), 0.004)) @ \
                        Matrix.Rotation(a + math.pi / 2, 4, "Z")
                    ok = 0
                    for p in cell_pts:
                        q = M @ p
                        hit = T.ray_cast(q + view * 1e-4, view, 5.0)
                        ok += hit[0] is None
                    vis += ok / len(cell_pts) >= 0.25
                counts.append(vis)
            frac = {c: round(counts.count(c) / len(counts), 2) for c in sorted(set(counts))}
            res[f"{elev:g}deg_{core}_{w}"] = {"true_cells": n, "visible_count_fraction_of_orbit": frac}
            print(f"{elev:>5}deg {core:<8} {w:<6} cells={n} visible-count distribution: {frac}")
json.dump(res, open(os.path.join(OUT, "cell_visibility_report.json"), "w"), indent=1)
