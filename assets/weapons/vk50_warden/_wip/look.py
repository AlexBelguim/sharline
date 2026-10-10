"""Quick look renders while iterating (writes _wip/look_*.png). Builds with --no-export in this session.
Run: blender -b --factory-startup -P _wip/look.py -- <group> [<group> ...]   groups: stock, bolt, mag, hg, rec, gun, under, all
"""
import math
import os
import runpy
import sys

import bpy
from mathutils import Matrix, Vector

groups = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["all"]
sys.argv = [sys.argv[0], "--", "--no-export", "--no-det-check", "--no-gate"]
ns = runpy.run_path(r"F:/git/val etf/assets/weapons/vk50_warden/build_warden.py", run_name="warden_build")
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

B, SOCK, BZ = ns["B"], ns["SOCKETS"], ns["BZ"]
OUTD = r"F:/git/val etf/assets/weapons/vk50_warden/_wip"
ns["render_world"]()


def tree(o):
    out = [o]
    for c in o.children:
        out += tree(c)
    return out


for p, sk in ((B["ss"], "Stock"), (B["sf"], "Stock"), (B["m5"], "Mag"), (B["m8"], "Mag")):
    p.matrix_world = Matrix.Translation(Vector(SOCK[sk]))
bpy.context.view_layer.update()
base = list(B["cols"]["base"].objects)
default = base + tree(B["ss"]) + tree(B["m5"])
alt = base + tree(B["sf"]) + tree(B["m8"])


def show(objs):
    keep = {o.name for o in objs}
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.hide_render = o.name not in keep


def R(prefix, objs, views, res=(1400, 900), focus=None, margin=1.1, lens=85, samples=32, ortho=False):
    show(objs)
    return bc.render_views(OUTD, "look_" + prefix, objs=[o for o in objs if o.type == "MESH"], views=views, res=res,
                           engine="CYCLES", samples=samples, lens=lens, margin=margin, focus=focus, ortho=ortho)


bolt = B["bolt"]
loc0, rot0 = bolt.location.copy(), bolt.rotation_euler.copy()


def bolt_pose(lift, travel):
    bolt.rotation_euler = (rot0.x, rot0.y + math.radians(lift), rot0.z)
    bolt.location = loc0 + Vector((0, travel, 0))
    bpy.context.view_layer.update()


if "stock" in groups or "all" in groups:
    R("stock_closed", default, ("left", "right"), focus=((0, 0.15, 0.0), 0.22))
    R("stock_closed", default, ((-0.9, 0.6, 0.45),), focus=((0, 0.12, 0.04), 0.22))
    R("stock_ss", tree(B["ss"]), ("three_quarter", "right"), margin=1.25)
    R("stock_sf", alt, ("left",), focus=((0, 0.15, 0.0), 0.22))
if "bolt" in groups or "all" in groups:
    bolt_pose(60, 0.0)
    R("bolt_lifted", default, ((-0.6, 1.0, 0.55),), focus=((0, 0.09, 0.09), 0.10))
    bolt_pose(60, 0.13)
    R("bolt_open", default, ("left",), focus=((0, 0.15, 0.05), 0.20))
    R("bolt_open", default, ((-0.22, 1.0, 0.40),), lens=40, margin=0.8, focus=((0, 0.05, 0.08), 0.30))
    R("bolt_open", default, ((-0.9, 0.6, 0.45),), focus=((0, 0.15, 0.07), 0.20))
    bolt_pose(60, 0.13)
    R("bolt_open_fold", alt, ((-0.9, 0.6, 0.45),), focus=((0, 0.15, 0.05), 0.20))
    bolt_pose(0, 0)
    R("bolt_closed", default, ((-1.0, 0.55, 0.45),), res=(1200, 900), focus=((-0.04, 0.06, 0.06), 0.14))
if "mag" in groups or "all" in groups:
    m = B["m5"]
    fol = next(o for o in m.children if o.name.endswith("Follower"))
    rounds = sorted([o for o in m.children if "_Round" in o.name], key=lambda o: o["round_index"])
    R("mag5_full", tree(m), ("right",), res=(900, 1000), margin=1.25)
    for o in rounds[2:]:
        o.hide_render = True
    fol.location.z += float(fol["offset_by_rounds_left_m"].split(",")[2])   # 2 rounds left
    bpy.context.view_layer.update()
    show([m, fol] + rounds[:2])
    bc.render_views(OUTD, "look_mag5_two", objs=[m], views=("right", (0.6, -0.5, 0.25)), res=(900, 1000),
                    engine="CYCLES", samples=32, margin=1.25)
if "hg" in groups or "all" in groups:
    R("hg", default, ((0.9, -0.35, 0.25),), focus=((0, -0.50, 0.08), 0.13))
    R("hg", default, ((-0.9, -0.35, 0.25),), focus=((0, -0.50, 0.08), 0.13))
if "rec" in groups or "all" in groups:
    R("rec", default, ((1.0, -0.35, 0.3), (-1.0, -0.25, 0.25)), focus=((0, -0.20, 0.05), 0.17))
if "gun" in groups:
    R("gun", default, ("right", "left"), res=(1600, 800), margin=1.04)
    R("gun", default, ("three_quarter", "three_quarter_back"), res=(1600, 800), margin=0.86,
      focus=((0, -0.40, 0.0), 0.70))
if "under" in groups:
    R("under", default, ((0.5, 0.45, -1.0),), focus=((0, 0.20, -0.07), 0.10))
    mono = next(o for o in B["ss"].children if o.name.endswith("Monopod"))
    mono.location.z += mono["travel_min_m"]
    bpy.context.view_layer.update()
    R("under_mono_out", default, ("left",), focus=((0, 0.20, -0.08), 0.16))
    mono.location.z -= mono["travel_min_m"]
    bpy.context.view_layer.update()
print("LOOK DONE")
