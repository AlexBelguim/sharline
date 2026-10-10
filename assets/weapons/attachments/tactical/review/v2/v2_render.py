"""Reviewer v2 renders, built from the CURRENT exported .glb files (UGL rebuilt at 09:44 after review pass 1).

  blender -b --factory-startup -P v2_render.py -- --sets ugl,uglfit,holes,ads,sil,wire

ugl    : UGL alone, all standard views + worst angles (Cycles)
uglfit : UGL on the real Mako (+ shield, lights, holo): sides, below, first-person inspect, breech open
holes  : EEVEE (honours single-sided / backface culling like the game) close-ups of the flipped triangles
         on laser_R top, laser_L top and the UGL's left (+X) receiver flank
ads    : EEVEE view from the holo ADS point through the shield glass at a high-contrast target (game-like)
sil    : 64 px silhouettes of the new UGL + Mako context at 160 px
wire   : wireframe overlay of the new UGL
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, r"F:/git/val etf/tools")
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import blender_common as bc  # noqa: E402

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
WEAP = r"F:/git/val etf/assets/weapons"
OUT = os.path.join(HERE, "review", "v2", "renders")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--sets", default="ugl,uglfit,holes,ads,sil,wire")
ap.add_argument("--samples", type=int, default=40)
a = ap.parse_args(argv)
SETS = a.sets.split(",")
os.makedirs(OUT, exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def imp(path, loc=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        o.rotation_mode = "XYZ"
    root = next(o for o in new if o.parent is None)
    if loc is not None:
        root.location = loc
    bpy.context.view_layer.update()
    return root, new


def part(pid, loc=None):
    return imp(os.path.join(HERE, f"ATT_{pid}.glb"), loc)


def meshes(objs):
    return [o for o in objs if o.type == "MESH"]


def gun_sockets(objs, prefix):
    return {o.name.replace(prefix + "_SOCKET_", ""): o.matrix_world.translation.copy() for o in objs
            if "_SOCKET_" in o.name}


def cam_at(loc, target, lens=None, hfov_deg=None, ortho_scale=None, res=(1000, 700)):
    scene = bpy.context.scene
    cd = bpy.data.cameras.get("_RevCam") or bpy.data.cameras.new("_RevCam")
    cam = bpy.data.objects.get("_RevCam") or bpy.data.objects.new("_RevCam", cd)
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)
    cd.clip_start = 0.002
    cd.clip_end = 200
    cd.sensor_fit = "HORIZONTAL"
    if ortho_scale:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho_scale
    else:
        cd.type = "PERSP"
        if hfov_deg:
            cd.angle = math.radians(hfov_deg)
        else:
            cd.lens = lens or 50
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    return cam


def cycles(samples=None):
    scene = bpy.context.scene
    bc.setup_cycles_gpu(scene, samples or a.samples)
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"


def eevee(samples=32):
    scene = bpy.context.scene
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            continue
    try:
        scene.eevee.taa_render_samples = samples
    except Exception:
        pass
    scene.render.image_settings.file_format = "PNG"


def shoot(path):
    scene = bpy.context.scene
    scene.render.filepath = path
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("render failed, CPU fallback:", e)
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("rendered", path)


def frame_dir(objs, d, margin=1.15, lens=85):
    mn, mx = bc.world_bounds(objs)
    c = (mn + mx) / 2
    r = (mx - mn).length / 2
    d = Vector(d).normalized()
    fov = 2 * math.atan(36 / (2 * lens))
    return c + d * (r * margin / math.sin(fov / 2)), c


def mako(atts, optic=True, floor=False, engine="cycles"):
    reset()
    bc.setup_studio(bpy.context.scene, floor=floor)
    cycles() if engine == "cycles" else eevee()
    g, gobjs = imp(os.path.join(WEAP, "ar7_mako", "mako_default.glb"))
    S = gun_sockets(gobjs, "MAKO")       # the glb's own socket nodes (what the game reads)
    out = {"gun": gobjs, "S": S}
    if optic:
        out["optic_holo"] = imp(os.path.join(WEAP, "attachments", "optics", "ATT_optic_holo.glb"), S["Optic"])[1]
    for pid, sk in atts:
        out[pid] = part(pid, S[sk])[1]
    return out


# ------------------------------------------------------------------------------------------------ UGL alone
if "ugl" in SETS:
    d = os.path.join(OUT, "ugl")
    reset()
    bc.setup_studio(bpy.context.scene)
    root, objs = part("ugl_launcher")
    ms = meshes(objs)
    bc.render_views(d, "ugl", objs=ms, views=("right", "left", "front", "back", "top", "three_quarter",
                                                "three_quarter_back", "low", (0.0, 0.25, -1.0),
                                                (-0.7, -0.6, -0.5), (0.9, 0.5, -0.35)),
                    res=(1000, 1000), engine="CYCLES", samples=a.samples)
    br = next(o for o in objs if o.name.endswith("_Breech"))
    br.rotation_euler = (0, 0, math.radians(br["open_angle_deg"]))
    bpy.context.view_layer.update()
    bc.render_views(d, "ugl_open", objs=ms, views=("top", "three_quarter", (-0.8, 0.9, 0.5)), res=(1000, 1000),
                    engine="CYCLES", samples=a.samples)

# ------------------------------------------------------------------------------------------------ UGL on Mako
if "uglfit" in SETS:
    d = os.path.join(OUT, "uglfit")
    os.makedirs(d, exist_ok=True)
    o = mako([("ugl_launcher", "Under")])
    U = o["S"]["Under"]
    for tag, dvec, lens in (("side_left_of_shooter", (1, 0, 0.02), 60), ("side_right_of_shooter", (-1, 0, 0.02), 60),
                            ("below", (0.15, 0.05, -1), 50)):
        cam_at(U + Vector((0, 0.08, -0.06)) + Vector(dvec).normalized() * 0.75, U + Vector((0, 0.08, -0.06)),
               lens=lens, res=(1200, 800))
        shoot(os.path.join(d, f"mako_ugl_{tag}.png"))
    # first-person support-hand inspect + hip view
    cam_at((0.30, -0.20, -0.06), (0.0, -0.36, 0.02), lens=40, res=(1200, 750))
    shoot(os.path.join(d, "fp_inspect_left_ugl.png"))
    cam_at((0.10, 0.22, 0.20), (0.0, -0.40, 0.02), hfov_deg=70, res=(1200, 750))
    shoot(os.path.join(d, "fp_hip_ugl.png"))
    # full kit: + shield + lights, closed and breech open
    o = mako([("ugl_launcher", "Under"), ("shield_front", "Shield"), ("laser_R", "Side_R"),
              ("flashlight_L", "Side_L")])
    U = o["S"]["Under"]
    muz = next(x for x in o["ugl_launcher"] if x.name.endswith("_SOCKET_Muzzle")).matrix_world.translation.copy()
    cam_at(muz + Vector((0.20, -0.14, -0.05)), muz + Vector((0, 0.02, 0.03)), lens=50, res=(1200, 800))
    shoot(os.path.join(d, "kit_closed_front_low_left.png"))
    cam_at(muz + Vector((0.42, 0.06, 0.0)), muz + Vector((0, 0.03, 0.03)), lens=50, res=(1200, 800))
    shoot(os.path.join(d, "kit_closed_side_left.png"))
    cam_at((0.95, -0.15, 0.05), (0.0, -0.22, 0.0), lens=40, res=(1400, 800))
    shoot(os.path.join(d, "kit_closed_wide_left.png"))
    br = next(x for x in o["ugl_launcher"] if x.name.endswith("_Breech"))
    br.rotation_euler = (0, 0, math.radians(br["open_angle_deg"]))
    bpy.context.view_layer.update()
    cam_at(U + Vector((0.30, -0.05, -0.32)), U + Vector((0.0, -0.06, -0.05)), lens=40, res=(1200, 800))
    shoot(os.path.join(d, "kit_open_below_left.png"))
    cam_at(U + Vector((0.0, -0.06, -0.55)), U + Vector((0.0, -0.06, 0.0)), lens=40, res=(1200, 800))
    shoot(os.path.join(d, "kit_open_from_below.png"))
    cam_at((0.30, 0.10, 0.05), (0.0, -0.33, -0.05), lens=35, res=(1200, 800))
    shoot(os.path.join(d, "kit_open_fp_left.png"))

# ------------------------------------------------------------------------------------------------ holes (EEVEE)
if "holes" in SETS:
    d = os.path.join(OUT, "holes")
    os.makedirs(d, exist_ok=True)
    for pid, views in (("laser_R", [("top", (0, 0.0001, 1)), ("tq_top", (-0.5, -0.6, 0.8))]),
                       ("laser_L", [("top", (0, 0.0001, 1)), ("tq_top", (0.5, -0.6, 0.8))])):
        reset()
        bc.setup_studio(bpy.context.scene)
        eevee()
        root, objs = part(pid)
        for tag, dv in views:
            loc, c = frame_dir(meshes(objs), dv, margin=1.1)
            cam_at(loc, c, lens=85, res=(900, 900))
            shoot(os.path.join(d, f"{pid}_{tag}_eevee_culled.png"))
    reset()
    bc.setup_studio(bpy.context.scene)
    eevee()
    root, objs = part("ugl_launcher")
    c = Vector((0.0315, 0.033, -0.045))
    for tag, dv, dist in (("flank_close", (1, 0.05, 0.05), 0.16), ("flank_tq", (1, 0.6, 0.2), 0.20)):
        cam_at(c + Vector(dv).normalized() * dist, c, lens=60, res=(1000, 800))
        shoot(os.path.join(d, f"ugl_left_flank_{tag}_eevee_culled.png"))
    loc, cc = frame_dir(meshes(objs), (1, 0, 0.05), margin=1.1)
    cam_at(loc, cc, lens=85, res=(1000, 1000))
    shoot(os.path.join(d, "ugl_right_view_eevee_culled.png"))

# ------------------------------------------------------------------------------------------------ ADS glass (EEVEE)
if "ads" in SETS:
    d = os.path.join(OUT, "ads")
    os.makedirs(d, exist_ok=True)
    o = mako([("shield_front", "Shield")], engine="eevee")
    sc = bpy.context.scene
    # outdoor-ish light: sun + bright sky so the glass is judged against a lit scene, not a dark studio
    sun = bpy.data.objects.new("_Sun", bpy.data.lights.new("_Sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    sc.collection.objects.link(sun)
    sc.world.use_nodes = True
    bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.55, 0.65, 0.8, 1)
    bg.inputs[1].default_value = 1.0
    ads = next(x for x in o["optic_holo"] if x.name.endswith("SOCKET_ADS")).matrix_world.translation.copy()
    # checker target board 8 m out + figure-sized orange post + ground
    for i in range(6):
        for j in range(6):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(-0.75 + i * 0.3, -8.0, ads.z - 0.75 + j * 0.3))
            t = bpy.context.active_object
            t.scale = (0.3, 0.05, 0.3)
            bc.assign(t, bc.material(f"_Chk{(i + j) % 2}", (0.9, 0.9, 0.9) if (i + j) % 2 else (0.02, 0.02, 0.02),
                                     rough=0.6))
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.9, -8.0, ads.z - 0.2))
    p = bpy.context.active_object
    p.scale = (0.45, 0.05, 1.8)
    bc.assign(p, bc.material("_Tgt", (0.9, 0.3, 0.05), rough=0.6))
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, -10, ads.z - 1.55))
    bc.assign(bpy.context.active_object, bc.material("_Gnd", (0.2, 0.22, 0.17), rough=0.9))
    for hf, tag in ((78, "game78"), (40, "zoom40")):
        cam_at(ads + Vector((0, 0.06, 0)), ads + Vector((0, -5, 0)), hfov_deg=hf, res=(1280, 720))
        shoot(os.path.join(d, f"ads_holo_shield_{tag}_eevee.png"))
    # same, without the optic: the shield glass alone from eye height (is the target readable through it?)
    for ob in o["optic_holo"]:
        ob.hide_render = True
    cam_at(ads + Vector((0, 0.06, 0)), ads + Vector((0, -5, 0)), hfov_deg=40, res=(1280, 720))
    shoot(os.path.join(d, "eye_through_glass_no_optic_zoom40_eevee.png"))

# ------------------------------------------------------------------------------------------------ silhouettes
def workbench_flat():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "FLAT"
    sh.color_type = "SINGLE"
    sh.single_color = (0, 0, 0)
    sh.show_shadows = False
    sh.show_cavity = False
    sh.show_object_outline = False
    scene.display.render_aa = "8"
    if not scene.world:
        scene.world = bpy.data.worlds.new("W")
    scene.world.color = (1, 1, 1)
    scene.view_settings.view_transform = "Standard"


if "sil" in SETS:
    d = os.path.join(OUT, "sil")
    os.makedirs(d, exist_ok=True)
    reset()
    workbench_flat()
    root, objs = part("ugl_launcher")
    for v, dv in (("side", (1, 0, 0.0)), ("tq", (0.75, -1, 0.35)), ("front", (0, -1, 0.0))):
        loc, c = frame_dir(meshes(objs), dv, margin=1.08)
        cam_at(loc, c, lens=85, res=(64, 64))
        shoot(os.path.join(d, f"ugl_{v}_64.png"))
    reset()
    workbench_flat()
    g, gobjs = imp(os.path.join(WEAP, "ar7_mako", "mako_default.glb"))
    S = gun_sockets(gobjs, "MAKO")
    imp(os.path.join(WEAP, "attachments", "optics", "ATT_optic_holo.glb"), S["Optic"])
    part("ugl_launcher", S["Under"])
    mn, mx = bc.world_bounds([x for x in gobjs if x.type == "MESH"])
    c = (mn + mx) / 2
    cam_at(c + Vector((-3, 0, 0)), c, ortho_scale=(mx - mn).y * 1.25, res=(160, 100))
    shoot(os.path.join(d, "ctx_mako_ugl_left_160.png"))

# ------------------------------------------------------------------------------------------------ wireframe
if "wire" in SETS:
    d = os.path.join(OUT, "wire")
    os.makedirs(d, exist_ok=True)
    reset()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "OBJECT"
    scene.display.render_aa = "16"
    scene.world = bpy.data.worlds.new("W")
    scene.world.color = (0.16, 0.17, 0.2)
    scene.view_settings.view_transform = "Standard"
    root, objs = part("ugl_launcher")
    ms = meshes(objs)
    for o in ms:
        o.color = (0.72, 0.72, 0.72, 1)
        w = o.copy()
        w.data = o.data.copy()
        w.parent = None
        w.matrix_world = o.matrix_world.copy()
        scene.collection.objects.link(w)
        m = w.modifiers.new("wf", "WIREFRAME")
        m.thickness = 0.0002
        m.use_relative_offset = False
        m.use_even_offset = False   # even offset spikes on the UGL's zero-area triangles
        w.color = (0.02, 0.05, 0.12, 1)
    for v, dv in (("right", (1, 0, 0.05)), ("tq", (0.75, -1, 0.35)), ("left", (-1, 0, 0.05))):
        loc, c = frame_dir(ms, dv, margin=1.08)
        cam_at(loc, c, lens=85, res=(1100, 1100))
        shoot(os.path.join(d, f"ugl_wire_{v}.png"))
print("DONE")
