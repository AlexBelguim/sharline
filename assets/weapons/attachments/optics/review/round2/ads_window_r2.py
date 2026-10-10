"""Round-2 reviewer: clear-window size of the 1x sights vs eye relief and FOV (read-only; writes ads_window_r2.json).
Ray-casts from the eye point against the Body only (glass/reticle ignored), finds the clear half-angles up/down/
left/right, and the distance from the eye to the nearest body point (near-plane clipping check, game near 0.03).
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
R2 = os.path.join(OUT, "review", "round2")
CAT = {e["id"]: e for e in json.load(open(os.path.join(OUT, "catalog.json")))["optics"]}
ZOOM = {"optic_reddot": 1.15, "optic_holo": 1.25, "optic_3x": 3.0, "optic_sniper": 6.0, "optic_thermal": 4.0}
res = {}
for oid in ("optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(OUT, "ATT_%s.glb" % oid))
    body = bpy.data.objects["ATT_%s_Body" % oid]
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.transform(body.matrix_world)
    t = BVHTree.FromBMesh(bm)
    allv = [v.co.copy() for v in bm.verts]
    s = bpy.data.objects["ATT_%s_SOCKET_ADS" % oid].matrix_world.translation.copy()
    rows = {}
    for er in (0.04, 0.05, 0.065, 0.08, 0.10, CAT[oid]["eye_relief_m"]):
        eye = s + Vector((0, er, 0))
        nearest = min((v - eye).length for v in allv)
        # nearest point on the surface (not just verts)
        loc, n, i, d = t.find_nearest(eye)

        def clear(ax, sign):
            a = 0.0
            while a < 60:
                r = math.radians(a)
                dvec = Vector((0, -1, 0))
                if ax == "x":
                    dvec = Vector((sign * math.sin(r), -math.cos(r), 0))
                else:
                    dvec = Vector((0, -math.cos(r), sign * math.sin(r)))
                h = t.ray_cast(eye, dvec, 3.0)
                if h[0] is not None:
                    return a
                a += 0.1
            return 60.0
        win = {"up": round(clear("z", 1), 1), "down": round(clear("z", -1), 1), "left": round(clear("x", 1), 1),
               "right": round(clear("x", -1), 1)}
        vf = 78.0 / ZOOM[oid]
        hf = math.degrees(2 * math.atan(math.tan(math.radians(vf / 2)) * 16 / 9))
        win["frac_h_at_game_vfov_%.1f" % vf] = round((win["up"] + win["down"]) / vf, 3)
        win["frac_w_at_game_hfov_%.1f" % hf] = round((win["left"] + win["right"]) / hf, 3)
        win["eye_to_nearest_body_mm"] = round(d * 1000, 1)
        win["clipped_by_near_0.03"] = d < 0.03
        rows["%.3f" % er] = win
    res[oid] = rows
    print(oid, json.dumps(rows))
with open(os.path.join(R2, "ads_window_r2.json"), "w") as f:
    json.dump(res, f, indent=1)
