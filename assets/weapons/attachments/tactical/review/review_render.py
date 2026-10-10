"""Reviewer renders for the ATT tactical set, built from the EXPORTED .glb files (so they also verify the export).

  blender -b --factory-startup -P review_render.py -- --sets sil,wire,fp,ads,clash,bipod,detail

sil    : 64 px black silhouettes per part (side + three-quarter) and of the Mako/Warden with each attachment
wire   : flat-grey + wireframe overlay (topology / bevel density) per part
fp     : first-person viewmodel angles (hip + support-hand side) of the Mako with each Mako attachment
ads    : view from the optic_holo ADS point through the shield (game-like ~78 deg HFOV) + wide
clash  : UGL + shield combination close-ups (closed and breech open)
bipod  : Warden + bipod at ground level (side, front, low 3/4), folded pose
detail : worst-angle close-ups (underside, back) of parts alone
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
OUT = os.path.join(HERE, "review", "renders")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--sets", default="sil,wire,fp,ads,clash,bipod,detail")
ap.add_argument("--samples", type=int, default=40)
a = ap.parse_args(argv)
SETS = a.sets.split(",")
PARTS = ["grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "bipod", "laser_R", "laser_L",
         "flashlight_R", "flashlight_L", "shield_front"]
os.makedirs(OUT, exist_ok=True)


def sockets(path, prefix):
    with open(path) as fh:
        d = json.load(fh)
    return {k.replace(prefix + "_SOCKET_", ""): Vector(v["location"]) for k, v in d.items()}


MAKO = sockets(os.path.join(WEAP, "ar7_mako", "sockets.json"), "MAKO")
WARDEN = sockets(os.path.join(WEAP, "vk50_warden", "sockets.json"), "WARDEN")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(path, loc=None):
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
    return import_glb(os.path.join(HERE, f"ATT_{pid}.glb"), loc)


def meshes(objs):
    return [o for o in objs if o.type == "MESH"]


def cam_at(loc, target, lens=None, hfov_deg=None, ortho_scale=None, res=(900, 700)):
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


def shoot(path):
    scene = bpy.context.scene
    scene.render.filepath = path
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("GPU render failed, CPU fallback:", e)
        scene.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("rendered", path)


def studio(floor=False):
    bc.setup_studio(bpy.context.scene, floor=floor)


def frame_dir(objs, d, margin=1.15, lens=85):
    mn, mx = bc.world_bounds(objs)
    c = (mn + mx) / 2
    r = (mx - mn).length / 2
    d = Vector(d).normalized()
    fov = 2 * math.atan(36 / (2 * lens))
    dist = r * margin / math.sin(fov / 2)
    return c + d * dist, c


# ------------------------------------------------------------------------------------------------ silhouettes
def workbench_flat(color=(0, 0, 0), bg=(1, 1, 1)):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "FLAT"
    sh.color_type = "SINGLE"
    sh.single_color = color
    sh.show_shadows = False
    sh.show_cavity = False
    sh.show_object_outline = False
    scene.display.render_aa = "8"
    if not scene.world:
        scene.world = bpy.data.worlds.new("W")
    scene.world.color = bg
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.film_transparent = False


if "sil" in SETS:
    sd = os.path.join(OUT, "sil")
    os.makedirs(sd, exist_ok=True)
    for pid in PARTS:
        reset()
        workbench_flat()
        root, objs = part(pid)
        for v, d in (("side", (1, 0, 0.0)), ("tq", (0.75, -1, 0.35)), ("front", (0, -1, 0.0))):
            loc, c = frame_dir(meshes(objs), d, margin=1.08)
            cam_at(loc, c, lens=85, res=(64, 64))
            shoot(os.path.join(sd, f"{pid}_{v}_64.png"))
    # gun context: Mako bare / + each attachment, 160 px wide side view (third-person ~ 15-20 m)
    for gun, combos in (("mako", [None, "grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "laser_R",
                                  "flashlight_R", "shield_front"]),
                        ("warden", [None, "bipod"])):
        for att in combos:
            reset()
            workbench_flat()
            if gun == "mako":
                g, gobjs = import_glb(os.path.join(WEAP, "ar7_mako", "mako_default.glb"))
                S = MAKO
                import_glb(os.path.join(WEAP, "attachments", "optics", "ATT_optic_holo.glb"), S["Optic"])
                sk = {"laser_R": "Side_R", "flashlight_R": "Side_R", "shield_front": "Shield"}.get(att, "Under")
            else:
                g, gobjs = import_glb(os.path.join(WEAP, "vk50_warden", "warden_default.glb"))
                S = WARDEN
                import_glb(os.path.join(WEAP, "attachments", "optics", "ATT_optic_sniper.glb"), S["Optic"])
                sk = "Under"
            if att:
                part(att, S[sk])
            allm = [o for o in bpy.data.objects if o.type == "MESH"]
            for v, d in (("left", (-1, 0, 0.0)), ("front", (0, -1, 0.05))):
                # fixed framing per gun so the attachment's added silhouette is comparable
                mn, mx = bc.world_bounds([o for o in gobjs if o.type == "MESH"])
                c = (mn + mx) / 2
                span = (mx - mn).y * 1.25 if v == "left" else 0.55
                cam_at(c + Vector(d).normalized() * 3.0, c, ortho_scale=span, res=(160, 100))
                shoot(os.path.join(sd, f"ctx_{gun}_{att or 'bare'}_{v}_160.png"))

# ------------------------------------------------------------------------------------------------ wireframe
if "wire" in SETS:
    wd = os.path.join(OUT, "wire")
    os.makedirs(wd, exist_ok=True)
    for pid in PARTS:
        reset()
        scene = bpy.context.scene
        scene.render.engine = "BLENDER_WORKBENCH"
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.color_type = "OBJECT"
        sh.show_cavity = False
        scene.display.render_aa = "16"
        scene.world = bpy.data.worlds.new("W")
        scene.world.color = (0.16, 0.17, 0.2)
        scene.view_settings.view_transform = "Standard"
        root, objs = part(pid)
        ms = meshes(objs)
        for o in ms:
            o.color = (0.72, 0.72, 0.72, 1)
            w = o.copy()
            w.data = o.data.copy()
            w.parent = None
            w.matrix_world = o.matrix_world.copy()
            bpy.context.scene.collection.objects.link(w)
            m = w.modifiers.new("wf", "WIREFRAME")
            m.thickness = 0.00022
            m.use_relative_offset = False
            m.use_even_offset = False
            w.color = (0.02, 0.05, 0.12, 1)
        for v, d in (("right", (1, 0, 0.05)), ("tq", (0.75, -1, 0.35)), ("back_low", (-0.6, 0.9, -0.4))):
            loc, c = frame_dir(ms, d, margin=1.08)
            cam_at(loc, c, lens=85, res=(1000, 1000))
            shoot(os.path.join(wd, f"{pid}_wire_{v}.png"))


# ------------------------------------------------------------------------------------------------ helpers (cycles)
def mako_scene(atts, floor=False, optic=True):
    reset()
    studio(floor)
    cycles()
    g, gobjs = import_glb(os.path.join(WEAP, "ar7_mako", "mako_default.glb"))
    out = {"gun": gobjs}
    if optic:
        out["optic_holo"] = import_glb(os.path.join(WEAP, "attachments", "optics", "ATT_optic_holo.glb"),
                                       MAKO["Optic"])[1]
    for pid, sk in atts:
        out[pid] = part(pid, MAKO[sk])[1]
    return out


if "fp" in SETS:
    fd = os.path.join(OUT, "fp")
    os.makedirs(fd, exist_ok=True)
    combos = {
        "grip_vertical": [("grip_vertical", "Under")],
        "grip_angled": [("grip_angled", "Under")],
        "grip_stub": [("grip_stub", "Under")],
        "ugl": [("ugl_launcher", "Under")],
        "lights_shield": [("laser_R", "Side_R"), ("flashlight_L", "Side_L"), ("shield_front", "Shield")],
        "full": [("ugl_launcher", "Under"), ("laser_R", "Side_R"), ("flashlight_L", "Side_L"),
                 ("shield_front", "Shield")],
    }
    for name, atts in combos.items():
        mako_scene(atts)
        # hip viewmodel: eye above-left (+X = shooter's left) and behind the gun, 90 deg-ish HFOV crop
        cam_at((0.10, 0.22, 0.20), (0.0, -0.40, 0.02), hfov_deg=70, res=(1000, 620))
        shoot(os.path.join(fd, f"fp_hip_{name}.png"))
        # support-hand side, slightly below (where the left hand + grip are seen during inspect)
        cam_at((0.30, -0.20, -0.06), (0.0, -0.36, 0.02), lens=40, res=(1000, 620))
        shoot(os.path.join(fd, f"fp_inspect_left_{name}.png"))

if "ads" in SETS:
    ad = os.path.join(OUT, "ads")
    os.makedirs(ad, exist_ok=True)
    o = mako_scene([("shield_front", "Shield"), ("laser_R", "Side_R"), ("flashlight_L", "Side_L")])
    ads = next(x for x in o["optic_holo"] if x.name.endswith("SOCKET_ADS")).matrix_world.translation.copy()
    # target board 10 m out: 1.8 m tall human-ish post centred on the aim point
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -10.0, ads.z - 0.35))
    tb = bpy.context.active_object
    tb.scale = (0.5, 0.05, 1.8)
    bc.assign(tb, bc.material("_Tgt", (0.8, 0.25, 0.1), rough=0.6))
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, -10, ads.z - 1.6))
    bc.assign(bpy.context.active_object, bc.material("_Gnd", (0.18, 0.2, 0.17), rough=0.9))
    for hf, tag in ((78, "game78"), (52, "zoomed52")):
        cam_at(ads + Vector((0, 0.06, 0)), ads + Vector((0, -5, 0)), hfov_deg=hf, res=(1280, 720))
        shoot(os.path.join(ad, f"ads_holo_shield_{tag}.png"))
    # hip view of the shield at typical camera height above the bore
    cam_at((0.06, 0.20, 0.17), (0.0, -3.0, 0.05), hfov_deg=90, res=(1280, 720))
    shoot(os.path.join(ad, "hip_shield_game90.png"))

if "clash" in SETS:
    cd_ = os.path.join(OUT, "clash")
    os.makedirs(cd_, exist_ok=True)
    o = mako_scene([("ugl_launcher", "Under"), ("shield_front", "Shield"), ("laser_R", "Side_R"),
                    ("flashlight_L", "Side_L")], optic=True)
    muz = Vector((0, -0.5055, -0.046))
    cam_at(muz + Vector((0.16, -0.10, -0.03)), muz + Vector((0, 0.01, 0.025)), lens=60, res=(1000, 700))
    shoot(os.path.join(cd_, "ugl_shield_closed_low_left.png"))
    cam_at(muz + Vector((0.0, -0.25, -0.07)), muz + Vector((0, 0.0, 0.03)), lens=60, res=(1000, 700))
    shoot(os.path.join(cd_, "ugl_shield_closed_front_low.png"))
    cam_at(muz + Vector((0.32, 0.0, 0.0)), muz + Vector((0, 0.02, 0.02)), lens=85, res=(1000, 700))
    shoot(os.path.join(cd_, "ugl_shield_closed_side.png"))
    br = next(x for x in o["ugl_launcher"] if x.name.endswith("_Breech"))
    br.rotation_euler = (0, 0, math.radians(br["open_angle_deg"]))
    bpy.context.view_layer.update()
    cam_at(muz + Vector((-0.12, -0.2, -0.12)), muz + Vector((0, 0.02, 0.02)), lens=50, res=(1000, 700))
    shoot(os.path.join(cd_, "ugl_shield_open_front_low_right.png"))
    cam_at((0.0, -0.33, -0.45), (0.0, -0.40, -0.03), lens=40, res=(1000, 700))
    shoot(os.path.join(cd_, "ugl_shield_open_below.png"))

if "bipod" in SETS:
    bd = os.path.join(OUT, "bipod")
    os.makedirs(bd, exist_ok=True)
    reset()
    studio()
    cycles()
    g, gobjs = import_glb(os.path.join(WEAP, "vk50_warden", "warden_default.glb"))
    import_glb(os.path.join(WEAP, "attachments", "optics", "ATT_optic_sniper.glb"), WARDEN["Optic"])
    root, bp = part("bipod", WARDEN["Under"])
    gz = min((o.matrix_world @ v.co).z for o in meshes(bp) for v in o.data.vertices)
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, -0.4, gz))
    gnd = bpy.context.active_object
    bc.assign(gnd, bc.material("_Gnd", (0.25, 0.26, 0.24), rough=0.85))
    U = WARDEN["Under"]
    cam_at((1.6, -0.45, gz + 0.03), (0, -0.45, gz + 0.12), lens=50, res=(1400, 600))
    shoot(os.path.join(bd, "warden_bipod_ground_side.png"))
    cam_at((0.0, -1.9, gz + 0.06), (0, -0.5, gz + 0.14), lens=60, res=(900, 700))
    shoot(os.path.join(bd, "warden_bipod_ground_front.png"))
    cam_at(U + Vector((0.28, -0.32, -0.16)), U + Vector((0, -0.05, -0.12)), lens=50, res=(1000, 750))
    shoot(os.path.join(bd, "warden_bipod_low_tq.png"))
    gnd.hide_render = True
    cam_at(U + Vector((-0.10, 0.25, -0.30)), U + Vector((0, -0.05, -0.05)), lens=50, res=(1000, 750))
    shoot(os.path.join(bd, "warden_bipod_from_below_back.png"))
    gnd.hide_render = False
    # first-person prone view (eye behind scope)
    cam_at((0.0, 0.25, 0.20), (0, -0.7, 0.0), hfov_deg=80, res=(1280, 720))
    shoot(os.path.join(bd, "warden_bipod_fp_prone.png"))
    gnd.hide_render = True
    legs = [o for o in bp if "_Leg_" in o.name]
    for lg in legs:
        lg.rotation_euler = (math.radians(lg["hinge_euler_x_folded_deg"]), 0, 0)
    bpy.context.view_layer.update()
    cam_at(U + Vector((0.45, -0.15, -0.10)), U + Vector((0, -0.12, -0.02)), lens=50, res=(1000, 700))
    shoot(os.path.join(bd, "warden_bipod_folded_side.png"))
    cam_at(U + Vector((0.20, -0.45, -0.25)), U + Vector((0, -0.12, -0.02)), lens=50, res=(1000, 700))
    shoot(os.path.join(bd, "warden_bipod_folded_low_front.png"))
    cam_at(U + Vector((0.0, -0.9, 0.02)), U + Vector((0, -0.12, -0.0)), lens=50, res=(1000, 700))
    shoot(os.path.join(bd, "warden_bipod_folded_front.png"))
    cam_at(U + Vector((0.0, -0.12, -0.6)), U + Vector((0, -0.12, 0.0)), lens=50, res=(1000, 700))
    shoot(os.path.join(bd, "warden_bipod_folded_from_below.png"))

if "detail" in SETS:
    dd = os.path.join(OUT, "detail")
    os.makedirs(dd, exist_ok=True)
    views = {
        "grip_vertical": [("under_back", (-0.5, 0.8, -0.6)), ("top_rear", (0.3, 0.9, 0.9))],
        "grip_angled": [("under_back", (-0.5, 0.8, -0.6)), ("left_low", (1, 0.1, -0.35))],
        "grip_stub": [("under_back", (-0.5, 0.8, -0.6)), ("left", (1, 0.0, 0.0))],
        "ugl_launcher": [("under_back", (-0.5, 0.8, -0.6)), ("under_front", (0.4, -0.8, -0.7)),
                         ("top_back_right", (-0.6, 0.7, 0.8))],
        "bipod": [("under", (0.2, -0.3, -1.0)), ("head_back", (0.5, 0.9, 0.2))],
        "laser_R": [("inner_back", (0.7, 0.8, 0.4)), ("under_front", (-0.6, -0.8, -0.6))],
        "flashlight_R": [("inner_back", (0.7, 0.8, 0.4)), ("front_on", (0, -1, 0.02))],
        "shield_front": [("back_low", (-0.3, 1.0, -0.4)), ("edge_on_top", (0.95, -0.1, 0.6)),
                         ("front_low_right", (-0.5, -1.0, -0.5))],
    }
    for pid, vs in views.items():
        reset()
        studio()
        cycles()
        root, objs = part(pid)
        for tag, d in vs:
            loc, c = frame_dir(meshes(objs), d, margin=1.08)
            cam_at(loc, c, lens=85, res=(900, 900))
            shoot(os.path.join(dd, f"{pid}_{tag}.png"))
print("DONE")
