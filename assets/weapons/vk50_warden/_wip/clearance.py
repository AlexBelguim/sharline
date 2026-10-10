"""Bolt-cycle clearance check on the freshly BUILT scene (no export): runs build_warden.py --no-export in this
Blender session, then sweeps the bolt through its documented cycle (lift 0..60 deg in place, then 0..0.13 m back)
against the base gun and both stocks, and reports the highest point the lifted handle reaches inside the riser's
x band (to size RISER_Z0).

Run: blender -b --factory-startup -P _wip/clearance.py
"""
import math
import runpy
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.argv = [sys.argv[0], "--", "--no-export", "--no-det-check", "--no-gate"]
ns = runpy.run_path(r"F:/git/val etf/assets/weapons/vk50_warden/build_warden.py", run_name="warden_build")
B = ns["B"]
SOCK = ns["SOCKETS"]
bolt = B["bolt"]


def tree(o):
    out = [o]
    for c in o.children:
        out += tree(c)
    return out


for p, sk in ((B["ss"], "Stock"), (B["sf"], "Stock"), (B["m5"], "Mag"), (B["m8"], "Mag")):
    p.matrix_world = Matrix.Translation(Vector(SOCK[sk]))
bpy.context.view_layer.update()


def bvh(o):
    mw = o.matrix_world
    me = o.data
    return BVHTree.FromPolygons([mw @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])


base = [o for o in B["cols"]["base"].objects if o.type == "MESH" and o is not bolt]
groups = {"base": base, "stock_standard": [o for o in tree(B["ss"]) if o.type == "MESH"],
          "stock_folding": [o for o in tree(B["sf"]) if o.type == "MESH"]}
trees = {g: [(o.name, bvh(o)) for o in objs] for g, objs in groups.items()}
loc0, rot0 = bolt.location.copy(), bolt.rotation_euler.copy()


def pose(lift, travel):
    bolt.rotation_euler = (rot0.x, rot0.y + math.radians(lift), rot0.z)
    bolt.location = loc0 + Vector((0, travel, 0))
    bpy.context.view_layer.update()


hits = {}
for lift in range(0, 61, 5):
    pose(lift, 0.0)
    tb = bvh(bolt)
    for g, ts in trees.items():
        for nm, t in ts:
            if tb.overlap(t):
                hits.setdefault(f"lift {lift:2d} deg / {g}", []).append(nm)
first = {}
for i in range(0, 27):
    tr = i * 0.005
    pose(60, tr)
    tb = bvh(bolt)
    for g, ts in trees.items():
        for nm, t in ts:
            if tb.overlap(t) and (g, nm) not in first:
                first[(g, nm)] = tr
print("=" * 80)
print("LIFT-IN-PLACE contacts:", hits or "none")
print("TRAVEL first contacts (m):", {f"{g}/{n}": round(v, 3) for (g, n), v in first.items()} or "none")
# highest point of the lifted bolt inside the riser band |x| <= 0.026, and over the travel
for lift in (30, 45, 60):
    pose(lift, 0.0)
    mw = bolt.matrix_world
    pts = [mw @ v.co for v in bolt.data.vertices]
    band = [p for p in pts if abs(p.x) <= 0.026]
    zmax = max(p.z for p in band)
    print(f"lift {lift}: max z inside |x|<=0.026: {zmax:.4f}   overall max z {max(p.z for p in pts):.4f}")
pose(60, 0.13)
pts = [bolt.matrix_world @ v.co for v in bolt.data.vertices]
print("open: bolt y range %.4f .. %.4f" % (min(p.y for p in pts), max(p.y for p in pts)))
for nm in ("WARDEN_StockStandard_CheekRiser", "WARDEN_StockStandard", "WARDEN_StockFolding_Arm"):
    o = bpy.data.objects[nm]
    ps = [o.matrix_world @ v.co for v in o.data.vertices]
    print(nm, "bounds", [round(min(p[i] for p in ps), 4) for i in range(3)], [round(max(p[i] for p in ps), 4) for i in range(3)])
pose(0, 0)
print("=" * 80)
# folded folding stock vs the base gun (arm rotated fold_angle_deg about its knuckle)
arm = B["sf"].children[0]
arm.rotation_euler[2] = math.radians(arm["fold_angle_deg"])
bpy.context.view_layer.update()
ta = bvh(arm)
print("FOLDED arm overlaps:", [nm for nm, t in trees["base"] if ta.overlap(t)] or "none")
saf = bpy.data.objects["WARDEN_Safety"]
r0s = saf.rotation_euler.copy()
saf.rotation_euler[0] = math.radians(saf["fire_deg"])
bpy.context.view_layer.update()
ts = bvh(saf)
print("SAFETY at FIRE overlaps:", [o.name for o in base if o is not saf and ts.overlap(bvh(o))] or "none",
      "| vs folded arm:", ts.overlap(ta) and "HIT" or "clear")
saf.rotation_euler = r0s
arm.rotation_euler[2] = 0
bpy.context.view_layer.update()
