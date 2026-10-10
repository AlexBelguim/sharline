"""Reviewer: FBX import sanity per part + contiguous sight window through the shield from the optic ADS points.
  blender -b --factory-startup -P fbx_and_sight.py
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
WEAP = r"F:/git/val etf/assets/weapons"
PARTS = ["grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "bipod", "laser_R", "laser_L",
         "flashlight_R", "flashlight_L", "shield_front"]
REP = {"fbx": {}}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


for pid in PARTS:
    reset()
    try:
        bpy.ops.import_scene.fbx(filepath=os.path.join(HERE, f"ATT_{pid}.fbx"))
    except Exception as e:  # noqa: BLE001
        REP["fbx"][pid] = {"error": str(e)}
        continue
    bpy.context.view_layer.update()
    objs = list(bpy.data.objects)
    ms = [o for o in objs if o.type == "MESH"]
    ws = [o.matrix_world @ v.co for o in ms for v in o.data.vertices]
    mn = [round(min(w[i] for w in ws), 4) for i in range(3)]
    mx = [round(max(w[i] for w in ws), 4) for i in range(3)]
    REP["fbx"][pid] = {
        "objects": sorted(f"{o.name}<{o.type}>{'^' + o.parent.name if o.parent else ''}" for o in objs),
        "tris": sum(len(p.vertices) - 2 for o in ms for p in o.data.polygons),
        "bounds": [mn, mx], "uv": all(o.data.uv_layers for o in ms),
        "props": {o.name: [k for k in o.keys() if not k.startswith("_")] for o in objs if len(o.keys())},
        "root_scale": [round(v, 4) for v in next(o for o in objs if o.parent is None).matrix_world.to_scale()],
    }
    print("FBX", pid, REP["fbx"][pid]["tris"], REP["fbx"][pid]["bounds"], REP["fbx"][pid]["root_scale"])


def sockets(path, prefix):
    with open(path) as fh:
        d = json.load(fh)
    return {k.replace(prefix + "_SOCKET_", ""): Vector(v["location"]) for k, v in d.items()}


MAKO = sockets(os.path.join(WEAP, "ar7_mako", "sockets.json"), "MAKO")


def import_glb(path, loc):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    next(o for o in new if o.parent is None).location = loc
    bpy.context.view_layer.update()
    return new


def bvh(objs):
    bm = bmesh.new()
    for o in objs:
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


reset()
sh = import_glb(os.path.join(HERE, "ATT_shield_front.glb"), MAKO["Shield"])
plate = bvh([o for o in sh if o.type == "MESH" and not o.name.endswith("_Glass")])
glass = bvh([o for o in sh if o.name.endswith("_Glass")])
REP["sight"] = {}
for opt in ("reddot", "holo", "3x"):
    p = os.path.join(WEAP, "attachments", "optics", f"ATT_optic_{opt}.glb")
    ob = import_glb(p, MAKO["Optic"])
    ads = next(o for o in ob if o.name.endswith("SOCKET_ADS")).matrix_world.translation.copy()
    for o in ob:
        bpy.data.objects.remove(o)

    def clear(d):
        lp = plate.ray_cast(ads, d, 3.0)
        lg = glass.ray_cast(ads, d, 3.0)
        if lp[0] is None:
            return "open"
        if lg[0] is not None and lg[3] < lp[3]:
            return "glass"
        return "plate"

    # contiguous range around 0 along the vertical and horizontal centre lines (0.1 deg steps)
    def run(axis):
        res = {}
        for sgn in (1, -1):
            a = 0.0
            while a < 40:
                d = Vector((math.tan(math.radians(sgn * a)) if axis == "h" else 0.0, -1.0,
                            math.tan(math.radians(sgn * a)) if axis == "v" else 0.0)).normalized()
                if clear(d) == "plate":
                    break
                a += 0.1
            res[sgn] = round(sgn * a, 1)
        return [res[-1], res[1]]
    REP["sight"][opt] = {"ads_above_rail_m": round(ads.z - MAKO["Optic"].z, 4), "ads_world": [round(v, 4) for v in ads],
                         "vertical_clear_deg": run("v"), "horizontal_clear_deg": run("h"),
                         "centre_ray": clear(Vector((0, -1, 0)))}
    print("SIGHT", opt, REP["sight"][opt])

with open(os.path.join(HERE, "review", "fbx_and_sight.json"), "w") as fh:
    json.dump(REP, fh, indent=1)
print("DONE")
