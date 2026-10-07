"""Render the ATT tactical set from tactical.blend (headless Blender 5.2).

  blender -b --factory-startup -P render_tactical.py -- [--parts a,b,...] [--sets alone,fit,detail,sight,loadout]
                                                         [--res 800] [--samples 48] [--views right,left,...]
Writes PNGs to renders/<part>/ . Contact sheets / comparisons are made by make_sheets.py (system python + PIL).
"""
import argparse
import math
import os
import sys

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
sys.path.insert(0, r"F:/git/val etf/tools")
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import blender_common as bc  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--parts", default="all")
ap.add_argument("--sets", default="alone,fit,detail")
ap.add_argument("--res", type=int, default=800)
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--views", default="right,left,three_quarter,front,back,top")
a = ap.parse_args(argv)

bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, "tactical.blend"))
scene = bpy.data.scenes["Scene"]
if bpy.context.window:
    bpy.context.window.scene = scene
vl = scene.view_layers[0]
for name in ("_Proxy_Mako", "_Proxy_Warden"):
    vl.layer_collection.children[name].exclude = False
bc.setup_studio(scene)
OUT = os.path.join(HERE, "renders")

MAKO = {k: Vector(v) for k, v in {"Under": (0, -0.360, 0.0165), "Side_R": (-0.0315, -0.440, 0.050),
                                  "Side_L": (0.0315, -0.440, 0.050), "Shield": (0, -0.480, 0.084),
                                  "Optic": (0, -0.085, 0.084)}.items()}
WARDEN = {k: Vector(v) for k, v in {"Under": (0, -0.600, 0.0205)}.items()}
PARTS = {
    "grip_vertical": ("mako", "Under"), "grip_angled": ("mako", "Under"), "grip_stub": ("mako", "Under"),
    "ugl_launcher": ("mako", "Under"), "bipod": ("warden", "Under"), "laser_R": ("mako", "Side_R"),
    "laser_L": ("mako", "Side_L"), "flashlight_R": ("mako", "Side_R"), "flashlight_L": ("mako", "Side_L"),
    "shield_front": ("mako", "Shield"),
}
parts = list(PARTS) if a.parts == "all" else a.parts.split(",")
sets = a.sets.split(",")
views = a.views.split(",")


def hier(o):
    out = [o]
    for c in o.children:
        out += hier(c)
    return out


def proxy(gun):
    col = bpy.data.collections["_Proxy_Mako" if gun == "mako" else "_Proxy_Warden"]
    return [o for o in col.all_objects if o.type == "MESH"]


ALL_MESH = [o for o in scene.objects if o.type == "MESH"]


def show_only(objs):
    keep = set(objs)
    for o in ALL_MESH:
        o.hide_render = o not in keep


def root_of(pid):
    return bpy.data.objects["ATT_" + pid]


def place(pid, loc):
    r = root_of(pid)
    r.location = loc
    bpy.context.view_layer.update()


def meshes(objs):
    return [o for o in objs if o.type == "MESH"]


def render(pid, prefix, objs, vws, res=None, focus=None, lens=85, frame=None):
    out = os.path.join(OUT, pid)
    return bc.render_views(out, prefix, objs=frame or objs, views=vws, res=res or (a.res, a.res), engine="CYCLES",
                           samples=a.samples, lens=lens, focus=focus)


def bounds(objs):
    mn, mx = bc.world_bounds(objs)
    return (mn + mx) / 2, (mx - mn).length / 2


for pid in parts:
    gun, sock = PARTS[pid]
    root = root_of(pid)
    objs = hier(root)
    ms = meshes(objs)
    if "alone" in sets:
        place(pid, Vector((0, 0, 0)))
        show_only(ms)
        render(pid, pid, ms, views)
    if "detail" in sets:
        place(pid, Vector((0, 0, 0)))
        show_only(ms)
        c, r = bounds(ms)
        render(pid, pid + "_detail", ms, ["three_quarter_back", "low"], focus=(c, r * 0.75))
    if "fit" in sets:
        loc = (MAKO if gun == "mako" else WARDEN)[sock]
        place(pid, loc)
        px = proxy(gun)
        show_only(ms + px)
        c, r = bounds(ms)
        r = max(r * 1.9, 0.16)
        fv = ["right", "left", "three_quarter", "front", "low"]
        if pid == "shield_front":
            fv = ["right", "three_quarter", "front", "three_quarter_back", "top"]
        render(pid, pid + "_fit", ms, fv, focus=(c, r))
        if gun == "warden":
            render(pid, pid + "_fit_wide", ms, ["right", "three_quarter"], frame=px)
        else:
            render(pid, pid + "_fit_wide", ms, ["three_quarter"], frame=[o for o in px if not o.name.startswith(
                "_PW_Ground")])
        place(pid, Vector((0, 0, 0)))

# ------------------------------------------------------------------------------------------- shield sight line
if "sight" in sets:
    pid = "shield_front"
    S = MAKO["Shield"]
    place(pid, S)
    ms = meshes(hier(root_of(pid)))
    px = [o for o in proxy("mako") if o.name != "_PX_Optic"]
    tmp = []
    # target board 4 m ahead with marks at the sight-line band (rail top + 0.040 / 0.0575 / 0.075)
    board = bpy.data.meshes.new("_board")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.6)
    bm.to_mesh(board)
    bm.free()
    bo = bpy.data.objects.new("_board", board)
    scene.collection.objects.link(bo)
    bo.rotation_euler = (math.radians(90), 0, 0)
    bo.location = (0, S.y - 4.0, S.z + 0.06)
    bo.data.materials.append(bc.material("_M_Board", (0.55, 0.56, 0.58), rough=0.8))
    tmp.append(bo)
    red = bc.material("_M_Mark", (1, 0.05, 0.02), emission=(1, 0.05, 0.02), emission_strength=6)
    grn = bc.material("_M_Band", (0.1, 1.0, 0.2), emission=(0.1, 1.0, 0.2), emission_strength=4)
    for dz, m in ((0.040, grn), (0.0575, red), (0.075, grn)):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.012, location=(0, S.y - 3.99, S.z + dz))
        sp = bpy.context.active_object
        sp.data.materials.append(m)
        tmp.append(sp)
    # sight-line rods (thin emissive) from the eye forward, for the side check
    eye_y = MAKO["Optic"].y + 0.036
    rods = []
    for dz in (0.040, 0.075):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.0007, depth=0.9, location=(0, eye_y - 0.45, S.z + dz),
                                            rotation=(math.radians(90), 0, 0))
        rd = bpy.context.active_object
        rd.data.materials.append(grn)
        rods.append(rd)
    ALL_MESH.extend(tmp + rods)
    out = os.path.join(OUT, pid)
    cam_d = bpy.data.cameras.new("_EyeCam")
    cam = bpy.data.objects.new("_EyeCam", cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam
    bc.setup_cycles_gpu(scene, a.samples)
    scene.render.resolution_x, scene.render.resolution_y = 1200, 800
    for dz in (0.040, 0.0575, 0.075):
        show_only(ms + px + tmp)
        cam_d.lens = 30
        cam_d.clip_start = 0.005
        cam.location = (0, eye_y, S.z + dz)
        cam.rotation_euler = (math.radians(90), 0, 0)
        scene.render.filepath = os.path.join(out, f"shield_front_sight_eye_{int(dz * 10000):03d}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", scene.render.filepath)
    # orthographic side view with the band rods
    show_only(ms + px + rods)
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 0.62
    cam.location = (1.0, S.y + 0.15, S.z + 0.02)
    cam.rotation_euler = (math.radians(90), 0, math.radians(90))
    scene.render.resolution_x, scene.render.resolution_y = 1400, 700
    scene.render.filepath = os.path.join(out, "shield_front_sight_side.png")
    bpy.ops.render.render(write_still=True)
    place(pid, Vector((0, 0, 0)))

# ------------------------------------------------------------------------------------------- loadouts
if "loadout" in sets:
    px = proxy("mako")
    A = {"shield_front": MAKO["Shield"], "laser_R": MAKO["Side_R"], "flashlight_L": MAKO["Side_L"],
         "ugl_launcher": MAKO["Under"]}
    vis = list(px)
    for pid, loc in A.items():
        place(pid, loc)
        vis += meshes(hier(root_of(pid)))
    show_only(vis)
    render("loadouts", "mako_loadout_A", vis, ["three_quarter", "right", "left", "three_quarter_back", "front"],
           res=(1400, 900))
    for pid in A:
        place(pid, Vector((0, 0, 0)))
    B = {"grip_angled": MAKO["Under"], "laser_L": MAKO["Side_L"], "flashlight_R": MAKO["Side_R"]}
    vis = list(px)
    for pid, loc in B.items():
        place(pid, loc)
        vis += meshes(hier(root_of(pid)))
    show_only(vis)
    render("loadouts", "mako_loadout_B", vis, ["three_quarter", "left"], res=(1400, 900))
    for pid in B:
        place(pid, Vector((0, 0, 0)))
    pw = proxy("warden")
    place("bipod", WARDEN["Under"])
    vis = pw + meshes(hier(root_of("bipod")))
    show_only(vis)
    render("loadouts", "warden_bipod", vis, ["three_quarter", "right", "front"], res=(1400, 900),
           frame=[o for o in pw if o.name != "_PW_Ground"])
    place("bipod", Vector((0, 0, 0)))
print("RENDER DONE")
