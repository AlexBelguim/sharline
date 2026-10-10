"""Review r2 renders (read-only on the asset). Imports the exported GLBs into a fresh scene (this also verifies the
exports), assembles loadouts on the sockets and renders the angles the builder did not show.

Run: blender -b --factory-startup -P r2_render.py -- <glb_dir> <tag> [groups]
  glb_dir: folder holding mako_base.glb + MAKO_<part>.glb   tag: prefix for the output files
  groups : comma list of fp,worst,close,variants,clay,wire,sil,motion (default all)
Writes review/r2/renders/<tag>_*.png
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:]
SRC, TAG = ARGS[0], ARGS[1]
GROUPS = set(ARGS[2].split(",")) if len(ARGS) > 2 else {"fp", "worst", "close", "variants", "clay", "wire", "sil",
                                                         "motion"}
OUT = r"F:/git/val etf/assets/weapons/ar7_mako/review/r2/renders"
os.makedirs(OUT, exist_ok=True)
SAMPLES = 40

bc.reset_scene()
SC = bpy.context.scene


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


PARTS = {}
PARTS["base"] = imp(os.path.join(SRC, "mako_base.glb"))
for k in ("stock_standard", "stock_precision", "stock_light", "mag_30", "mag_45", "mag_drum60"):
    PARTS[k] = imp(os.path.join(SRC, f"MAKO_{k}.glb"))
sock = {o.name: o.matrix_world.translation.copy() for o in PARTS["base"] if "_SOCKET_" in o.name}
for k, objs in PARTS.items():
    if k == "base":
        continue
    root = [o for o in objs if o.parent is None][0]
    root.location = sock["MAKO_SOCKET_Stock"] if k.startswith("stock") else sock["MAKO_SOCKET_Mag"]
bpy.context.view_layer.update()

# ------------------------------------------------------------------ studio (same presentation as the builder)
bc.setup_studio(bg=(0.55, 0.55, 0.55), strength=0.28)
SC.world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
SC.view_settings.view_transform = "Standard"
SC.view_settings.look = "None"
bc.setup_cycles_gpu(SC, SAMPLES)
cam_d = bpy.data.cameras.new("_RvCam")
CAM = bpy.data.objects.new("_RvCam", cam_d)
SC.collection.objects.link(CAM)
SC.camera = CAM
cam_d.clip_start = 0.005


def meshes(keys):
    out = []
    for k in keys:
        out += [o for o in PARTS[k] if o.type == "MESH"]
    return out


def show(keys):
    keep = set(meshes(keys))
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = o not in keep


def render(name, loc=None, target=None, lens=50, res=(1500, 1000), focus=None, d=None, ortho=None):
    """Either loc+target, or focus=(center, radius) + direction d (auto distance)."""
    SC.render.resolution_x, SC.render.resolution_y = res
    SC.render.resolution_percentage = 100
    cam_d.lens = lens
    cam_d.type = "PERSP"
    if focus is not None:
        c, r = Vector(focus[0]), focus[1]
        dv = Vector(d).normalized()
        if ortho:
            cam_d.type = "ORTHO"
            cam_d.ortho_scale = ortho
            loc = c + dv * 2.0
        else:
            fov = 2 * math.atan(cam_d.sensor_width / (2 * lens))
            loc = c + dv * (r / math.sin(fov / 2))
        target = c
    CAM.location = Vector(loc)
    CAM.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    p = os.path.join(OUT, f"{TAG}_{name}.png")
    SC.render.filepath = p
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("GPU render failed, CPU fallback:", e)
        SC.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("rendered", p, flush=True)


DEFAULT = ["base", "stock_standard", "mag_30"]

# ------------------------------------------------------------------ first-person / gameplay views
if "fp" in GROUPS:
    show(DEFAULT)
    # hip-fire viewmodel: eye at +X (shooter's left of the gun), above and behind, looking straight ahead
    render("fp_hip", loc=(0.15, 0.40, 0.16), target=(0.08, -1.0, 0.06), lens=22, res=(1600, 900))
    # ADS without optic: eye on the sight line looking down the rail
    render("fp_ads_sightline", loc=(0.0, 0.33, 0.116), target=(0.0, -1.0, 0.08), lens=30, res=(1600, 900))
    # reload pose: gun canted toward the camera, magwell side (+X) at chest height
    render("fp_reload", loc=(0.30, 0.10, 0.22), target=(0.0, -0.12, -0.02), lens=28, res=(1600, 900))
    # third person / enemy view at range: small side view
    render("tp_far_side", focus=((0, -0.14, -0.03), 0.48), d=(1, -0.15, 0.05), lens=200, res=(480, 270))

# ------------------------------------------------------------------ worst angles (whole gun)
if "worst" in GROUPS:
    show(DEFAULT)
    render("worst_under", focus=((0, -0.14, -0.03), 0.46), d=(0.15, 0.05, -1), lens=60)
    render("worst_rear_eye", focus=((0, 0.0, -0.02), 0.16), d=(0.0, 1, 0.12), lens=85, res=(1000, 1000))
    render("worst_front_low_minusX", focus=((0, -0.14, -0.03), 0.46), d=(-0.7, -1, -0.35), lens=50)
    render("worst_minusX_high", focus=((0, -0.14, -0.03), 0.46), d=(-0.9, -0.55, 0.75), lens=50)
    render("worst_top_rear_plusX", focus=((0, -0.10, 0.02), 0.40), d=(0.45, 1.0, 0.9), lens=50)
    render("side_ortho_plusX", focus=((0, -0.143, -0.044), 0.5), d=(1, 0, 0), ortho=0.92, res=(1800, 900))
    render("side_ortho_minusX", focus=((0, -0.143, -0.044), 0.5), d=(-1, 0, 0), ortho=0.92, res=(1800, 900))
    render("top_ortho", focus=((0, -0.143, 0.0), 0.5), d=(0.0005, 0, 1), ortho=0.92, res=(1800, 500))

# ------------------------------------------------------------------ close-ups
if "close" in GROUPS:
    show(DEFAULT)
    render("cu_ch_castle_rear_minusX", focus=((0.0, 0.035, 0.058), 0.040), d=(-0.75, 0.85, 0.55), lens=85)
    render("cu_ch_top", focus=((0.0, 0.03, 0.07), 0.035), d=(0.001, 0.25, 1), lens=85)
    render("cu_receiver_plusX", focus=((0, -0.07, 0.01), 0.11), d=(1.0, -0.1, 0.15), lens=85)
    render("cu_receiver_minusX", focus=((0, -0.07, 0.01), 0.11), d=(-1.0, -0.1, 0.15), lens=85)
    render("cu_grip_rear_low", focus=((0, 0.03, -0.04), 0.07), d=(0.55, 0.85, -0.35), lens=85)
    render("cu_magwell_front_low", focus=((0, -0.13, -0.03), 0.06), d=(0.6, -0.9, -0.35), lens=85)
    render("cu_hg_upper_joint_top", focus=((0, -0.17, 0.065), 0.045), d=(-0.6, -0.5, 0.75), lens=85)
    render("cu_hg_front_minusX", focus=((0, -0.49, 0.045), 0.05), d=(-0.8, -0.7, 0.25), lens=85)
    render("cu_hg_bottom_rail", focus=((0, -0.34, 0.02), 0.08), d=(0.5, -0.3, -0.8), lens=85)
    render("cu_trigger_plusX", focus=((0, -0.045, -0.012), 0.035), d=(1, 0.1, 0.05), lens=85)
    render("cu_mag_window_plusX", focus=((0, -0.13, -0.08), 0.06), d=(1, -0.15, 0.05), lens=85)
    render("cu_stock_under", focus=((0, 0.19, -0.005), 0.08), d=(0.6, 0.35, -0.7), lens=85)
    render("cu_dustcover_minusX", focus=((0, -0.06, 0.05), 0.04), d=(-1, -0.1, 0.25), lens=85)
    render("cu_muzzle_3q", focus=((0, -0.54, 0.05), 0.035), d=(0.7, -0.8, 0.3), lens=85)

# ------------------------------------------------------------------ variants
if "variants" in GROUPS:
    show(["base", "stock_precision", "mag_45"])
    render("var_precision_mag45_3q", focus=((0, -0.13, -0.05), 0.48), d=(0.75, -1, 0.35), lens=50)
    render("cu_precision_cheek", focus=((0, 0.175, 0.075), 0.06), d=(0.8, 0.3, 0.35), lens=85)
    render("cu_precision_cheek_rear", focus=((0, 0.175, 0.075), 0.06), d=(-0.4, 1, 0.35), lens=85)
    show(["base", "stock_light", "mag_drum60"])
    render("var_light_drum_3q_minusX", focus=((0, -0.13, -0.03), 0.46), d=(-0.75, -1, 0.3), lens=50)
    render("cu_drum_minusX", focus=((0, -0.12, -0.09), 0.07), d=(-1, 0.05, 0.0), lens=85)
    render("cu_drum_plusX", focus=((0, -0.12, -0.09), 0.07), d=(1, 0.05, 0.0), lens=85)
    render("cu_light_stock_3q_back", focus=((0, 0.19, 0.01), 0.08), d=(-0.6, 0.8, 0.3), lens=85)

# ------------------------------------------------------------------ clay (form read without textures)
if "clay" in GROUPS:
    show(DEFAULT)
    clay = bc.material("_Clay", (0.6, 0.6, 0.6), rough=0.6)
    SC.view_layers[0].material_override = clay
    render("clay_3q_plusX", focus=((0, -0.14, -0.03), 0.46), d=(0.75, -1, 0.35), lens=50)
    render("clay_3q_minusX_rear", focus=((0, -0.14, -0.03), 0.46), d=(-0.8, 0.9, 0.35), lens=50)
    render("clay_receiver_3q", focus=((0, -0.06, 0.0), 0.12), d=(0.8, -0.7, 0.35), lens=85)
    SC.view_layers[0].material_override = None

# ------------------------------------------------------------------ wireframe overlay (exported, triangulated mesh)
if "wire" in GROUPS:
    show(DEFAULT)
    wire_m = bc.material("_Wire", (0.0, 0.0, 0.0), rough=1.0, emission=(0.9, 0.25, 0.05), emission_strength=3.0)
    dups = []
    for o in meshes(DEFAULT):
        d = o.copy()
        d.data = o.data.copy()
        SC.collection.objects.link(d)
        d.data.materials.clear()
        d.data.materials.append(wire_m)
        m = d.modifiers.new("W", "WIREFRAME")
        m.thickness = 0.00018
        m.use_replace = True
        m.use_even_offset = False
        d.hide_render = False
        dups.append(d)
    clay = bc.material("_Clay2", (0.55, 0.55, 0.57), rough=0.7)
    origs = meshes(DEFAULT)
    for o in origs:
        o["_mats"] = [s.material.name if s.material else "" for s in o.material_slots]
        for s in o.material_slots:
            s.material = clay
    render("wire_receiver_minusX", focus=((0, -0.07, 0.01), 0.11), d=(-1.0, -0.1, 0.15), lens=85, res=(1800, 1200))
    render("wire_receiver_plusX", focus=((0, -0.07, 0.01), 0.11), d=(1.0, -0.1, 0.15), lens=85, res=(1800, 1200))
    render("wire_handguard_3q", focus=((0, -0.36, 0.045), 0.14), d=(0.8, -0.6, 0.3), lens=85, res=(1800, 1200))
    render("wire_stock_mag", focus=((0, 0.06, -0.04), 0.22), d=(1.0, 0.0, 0.05), lens=85, res=(1800, 1200))
    for o in origs:
        for s, n in zip(o.material_slots, o["_mats"]):
            s.material = bpy.data.materials.get(n)
    for d in dups:
        bpy.data.objects.remove(d, do_unlink=True)

# ------------------------------------------------------------------ silhouettes (black on white, downsampled later)
if "sil" in GROUPS:
    blk = bc.material("_Black", (0, 0, 0), rough=1.0)
    SC.view_layers[0].material_override = blk
    for l in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        l.hide_render = True
    SC.world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    SC.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    for cfg, keys in (("default", DEFAULT), ("precision45", ["base", "stock_precision", "mag_45"]),
                      ("lightdrum", ["base", "stock_light", "mag_drum60"])):
        show(keys)
        render(f"sil_{cfg}_side", focus=((0, -0.143, -0.044), 0.5), d=(1, 0, 0), ortho=0.92, res=(1024, 512))
        render(f"sil_{cfg}_3q", focus=((0, -0.14, -0.03), 0.46), d=(0.75, -1, 0.35), lens=50, res=(1024, 683))
    SC.view_layers[0].material_override = None

# ------------------------------------------------------------------ moving parts at end of travel
if "motion" in GROUPS:
    show(DEFAULT)
    ch = bpy.data.objects["MAKO_ChargingHandle"]
    ch.location.y += 0.06
    dc = bpy.data.objects["MAKO_DustCover"]
    dc.rotation_mode = "XYZ"
    dc.rotation_euler.y += math.radians(-100)   # swing down/out on the -X side
    bpy.context.view_layer.update()
    render("motion_ch_pulled_dc_open", focus=((0.0, 0.0, 0.05), 0.09), d=(-0.8, 0.6, 0.45), lens=85)
print("R2 RENDER DONE", flush=True)
