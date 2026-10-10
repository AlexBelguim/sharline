"""Reviewer: import every ATT_<optic>.fbx in a fresh scene and compare with the .glb (scale, axes, ADS socket,
materials, embedded textures). Read-only on the asset; prints a table and writes review/fbx_check.json.

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P review_fbx_check.py
"""
import json
import os

import bpy
from mathutils import Vector

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
OPTICS = ["optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"]


def bbox(objs):
    mn = Vector((1e9,) * 3)
    mx = Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    return mn, mx


res = {}
for oid in OPTICS:
    r = {}
    for ext in ("glb", "fbx"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        p = os.path.join(OUT, "ATT_%s.%s" % (oid, ext))
        if ext == "glb":
            bpy.ops.import_scene.gltf(filepath=p)
        else:
            bpy.ops.import_scene.fbx(filepath=p)
        ms = [o for o in bpy.data.objects if o.type == "MESH"]
        mn, mx = bbox(ms)
        ads = next((o for o in bpy.data.objects if o.name.startswith("ATT_%s_SOCKET_ADS" % oid)), None)
        root = next((o for o in bpy.data.objects if o.name == "ATT_" + oid), None)
        r[ext] = {"objects": sorted(o.name for o in bpy.data.objects),
                  "bbox_min": [round(v, 4) for v in mn], "bbox_max": [round(v, 4) for v in mx],
                  "ads": [round(v, 4) for v in ads.matrix_world.translation] if ads else None,
                  "root_scale": [round(v, 4) for v in root.matrix_world.to_scale()] if root else None,
                  "materials": sorted(m.name for m in bpy.data.materials),
                  "images": sorted((i.name, bool(i.packed_file), i.size[0]) for i in bpy.data.images
                                   if i.type == "IMAGE"),
                  "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in ms)}
    res[oid] = r
    print(oid)
    for ext in ("glb", "fbx"):
        print("  ", ext, {k: v for k, v in r[ext].items() if k != "objects"})
json.dump(res, open(os.path.join(OUT, "review", "fbx_check.json"), "w"), indent=1)
