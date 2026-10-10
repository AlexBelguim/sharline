"""Reviewer close-ups on suspected defects (read-only on the asset; writes review/renders/close_*.png).

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P review_closeups.py
"""
import json
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_render as rr  # noqa: E402
bc = rr.bc

OUT, RD = rr.OUT, rr.RD


def optic_alone(oid):
    rr.wipe()
    bc.setup_studio()
    return [o for o in rr.import_glb(os.path.join(OUT, "ATT_%s.glb" % oid)) if o.type == "MESH"]


def optic_on_gun(oid, gun):
    glb, sj, sock = rr.GUNS[gun]
    rr.wipe()
    bc.setup_studio()
    g = [o for o in rr.import_glb(glb) if o.type == "MESH"]
    s = Vector(json.load(open(sj))[sock]["location"])
    o = [x for x in rr.import_glb(os.path.join(OUT, "ATT_%s.glb" % oid)) if x.type == "MESH"]
    bpy.data.objects.get("ATT_" + oid).location = s
    bpy.context.view_layer.update()
    return g, o, s


# 1) holo: window tunnel vs brow chamfer at the front top (suspected notch / frame poking through)
objs = optic_alone("optic_holo")
for nm, d in (("holo_brow_front_top", (-0.35, -0.8, 0.9)), ("holo_brow_side", (-1.0, -0.15, 0.25)),
              ("holo_brow_topdown", (0.0, -0.25, 1.0))):
    rr.shot("close_" + nm, d, objs, res=800, lens=85, focus=((0.0, -0.020, 0.060), 0.020))

# 2) reddot: coplanar-face candidates on the front face of the deck (y -0.025, z 0.0385) and the shroud top
objs = optic_alone("optic_reddot")
rr.shot("close_reddot_front_deck", (0.25, -1.0, 0.15), objs, res=800, focus=((0.0, -0.025, 0.036), 0.012))
rr.shot("close_reddot_shroud_top", (-0.4, -0.6, 0.8), objs, res=800, focus=((-0.004, -0.019, 0.063), 0.010))

# 3) clamps on the REAL gun rails, looking along the rail from the front-low (jaw / dovetail gap)
for oid, gun in (("optic_reddot", "WARDEN"), ("optic_holo", "MAKO"), ("optic_reddot", "MAKO")):
    g, o, s = optic_on_gun(oid, gun)
    rr.shot("close_clamp_%s_on%s_front" % (oid, gun.lower()), (0.12, -1.0, -0.05), g + o, res=800,
            focus=((s.x, s.y, s.z - 0.002), 0.022))
g, o, s = optic_on_gun("optic_sniper", "WARDEN")
rr.shot("close_clamp_optic_sniper_onwarden_rear", (0.15, 1.0, -0.02), g + o, res=800,
        focus=((s.x, s.y + 0.06, s.z), 0.026))
rr.shot("close_sniper_onwarden_eyeline", (0.9, 0.35, 0.12), g + o, res=900,
        focus=((s.x, s.y + 0.12, s.z + 0.03), 0.09))
