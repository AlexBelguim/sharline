"""Fit check of the shared attachments on the freshly BUILT Warden (no export): optic_sniper / optic_thermal on
_Optic, bipod on _Under, laser_R / flashlight_L on _Side_R / _Side_L. Reports each attachment's bounds and any mesh
overlap with the base gun / default stock, sweeps the bolt cycle with each optic mounted, and renders side views
(_wip/att_*.png).
Run: blender -b --factory-startup -P _wip/attach_check.py
"""
import math
import os
import runpy
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.argv = [sys.argv[0], "--", "--no-export", "--no-det-check", "--no-gate"]
ns = runpy.run_path(r"F:/git/val etf/assets/weapons/vk50_warden/build_warden.py", run_name="warden_build")
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

B, SOCK = ns["B"], ns["SOCKETS"]
OUTD = r"F:/git/val etf/assets/weapons/vk50_warden/_wip"
ATT = r"F:/git/val etf/assets/weapons/attachments"


def tree(o):
    out = [o]
    for c in o.children:
        out += tree(c)
    return out


for p, sk in ((B["ss"], "Stock"), (B["sf"], "Stock"), (B["m5"], "Mag"), (B["m8"], "Mag")):
    p.matrix_world = Matrix.Translation(Vector(SOCK[sk]))
bpy.context.view_layer.update()
bolt = B["bolt"]
base = [o for o in B["cols"]["base"].objects if o.type == "MESH" and o is not bolt]
default = list(B["cols"]["base"].objects) + tree(B["ss"]) + tree(B["m5"])
gun = [o for o in base + tree(B["ss"]) + tree(B["m5"]) if o.type == "MESH"]


def bvh(o):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    me = ev.to_mesh()
    mw = o.matrix_world
    t = BVHTree.FromPolygons([mw @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    ev.to_mesh_clear()
    return t


def load(fn, sk):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=fn)
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None or o.parent not in new]
    for r in roots:
        r.matrix_world = Matrix.Translation(Vector(SOCK[sk])) @ r.matrix_world
    bpy.context.view_layer.update()
    return new


def bounds(objs):
    ps = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    return [round(min(p[i] for p in ps), 4) for i in range(3)], [round(max(p[i] for p in ps), 4) for i in range(3)]


gtrees = [(o.name, bvh(o)) for o in gun]
loc0, rot0 = bolt.location.copy(), bolt.rotation_euler.copy()


def pose(lift, travel):
    bolt.rotation_euler = (rot0.x, rot0.y + math.radians(lift), rot0.z)
    bolt.location = loc0 + Vector((0, travel, 0))
    bpy.context.view_layer.update()


ns["render_world"]()
plan = [("optics/ATT_optic_sniper.glb", "Optic"), ("optics/ATT_optic_thermal.glb", "Optic"),
        ("tactical/ATT_bipod.glb", "Under"), ("tactical/ATT_laser_R.glb", "Side_R"),
        ("tactical/ATT_flashlight_L.glb", "Side_L")]
for rel, sk in plan:
    fn = os.path.join(ATT, rel)
    if not os.path.exists(fn):
        print("ATT missing", rel)
        continue
    new = load(fn, sk)
    meshes = [o for o in new if o.type == "MESH"]
    at = [(o.name, bvh(o)) for o in meshes]
    hits = sorted({(a, g) for a, ta in at for g, tg in gtrees if ta.overlap(tg)})
    print(f"ATT {rel} on {sk}: bounds {bounds(meshes)}  overlaps with gun: {hits or 'none'}")
    if sk == "Optic":
        bh = []
        for lift in range(0, 61, 10):
            pose(lift, 0)
            tb = bvh(bolt)
            bh += [(lift, 0, a) for a, ta in at if tb.overlap(ta)]
        for i in range(0, 27, 2):
            pose(60, i * 0.005)
            tb = bvh(bolt)
            bh += [(60, i * 0.005, a) for a, ta in at if tb.overlap(ta)]
        pose(0, 0)
        ads = [o for o in new if o.name.endswith("_SOCKET_ADS")]
        ads_z = ads[0].matrix_world.translation.z if ads else None
        print(f"    bolt cycle vs optic: {bh or 'clear'}   ADS z {ads_z}  (rail top {SOCK['Optic'][2]})")
    objs = default + meshes
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.hide_render = o not in objs
    tag = os.path.splitext(os.path.basename(rel))[0]
    bc.render_views(OUTD, "att_" + tag, objs=[o for o in objs if o.type == "MESH"], views=("right",),
                    res=(1400, 700), engine="CYCLES", samples=24, margin=1.04)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
print("ATT DONE")
