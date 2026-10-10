"""Independent review renders of the MAKO, built ONLY from the exported GLBs (so the export is verified too).
Run: blender -b --factory-startup -P rv_render.py -- [group,group,...]
Groups: fp, worst, v09, clay, wire, sil, close, variants, fit   (default: all)
Writes PNGs to review/renders/ and fit results to review/fit_report.json."""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
ATT = r"F:/git/val etf/assets/weapons/attachments"
OUT = os.path.join(HERE, "review", "renders")
os.makedirs(OUT, exist_ok=True)
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GROUPS = set((ARGS[0] if ARGS else "fp,worst,v09,clay,wire,sil,close,variants,fit").split(","))
SAMPLES = int(os.environ.get("RV_SAMPLES", "40"))

bc.reset_scene()
SC = bpy.context.scene
SOCK = json.load(open(os.path.join(HERE, "sockets.json")))


def sock(name):
    return Vector(SOCK[f"MAKO_SOCKET_{name}"]["location"])


def import_glb(path, at=(0, 0, 0)):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    tops = [o for o in new if o.parent is None or o.parent not in new]
    for t in tops:
        t.location = Vector(t.location) + Vector(at)
    bpy.context.view_layer.update()
    return new


SETS = {}
SETS["base"] = import_glb(os.path.join(HERE, "mako_base.glb"))
SETS["stock_standard"] = import_glb(os.path.join(HERE, "MAKO_stock_standard.glb"), sock("Stock"))
SETS["stock_precision"] = import_glb(os.path.join(HERE, "MAKO_stock_precision.glb"), sock("Stock"))
SETS["stock_light"] = import_glb(os.path.join(HERE, "MAKO_stock_light.glb"), sock("Stock"))
SETS["mag_30"] = import_glb(os.path.join(HERE, "MAKO_mag_30.glb"), sock("Mag"))
SETS["mag_45"] = import_glb(os.path.join(HERE, "MAKO_mag_45.glb"), sock("Mag"))
SETS["mag_drum60"] = import_glb(os.path.join(HERE, "MAKO_mag_drum60.glb"), sock("Mag"))
SETS["optic_holo"] = import_glb(os.path.join(ATT, "optics", "ATT_optic_holo.glb"), sock("Optic"))
SETS["optic_3x"] = import_glb(os.path.join(ATT, "optics", "ATT_optic_3x.glb"), sock("Optic"))
SETS["grip_vertical"] = import_glb(os.path.join(ATT, "tactical", "ATT_grip_vertical.glb"), sock("Under"))
SETS["ugl"] = import_glb(os.path.join(ATT, "tactical", "ATT_ugl_launcher.glb"), sock("Under"))
SETS["laser_R"] = import_glb(os.path.join(ATT, "tactical", "ATT_laser_R.glb"), sock("Side_R"))
SETS["flashlight_L"] = import_glb(os.path.join(ATT, "tactical", "ATT_flashlight_L.glb"), sock("Side_L"))
SETS["shield"] = import_glb(os.path.join(ATT, "tactical", "ATT_shield_front.glb"), sock("Shield"))


def meshes(keys):
    out = []
    for k in keys:
        out += [o for o in SETS[k] if o.type == "MESH"]
    return out


def show(keys):
    keep = set(o.name for o in meshes(keys))
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = o.name not in keep


# ------------------------------------------------------------------ lighting (neutral studio, like the builder's)
bc.setup_studio(bg=(0.55, 0.55, 0.55), strength=0.28)
for nm, colr in (("L_Key", (1.0, 0.97, 0.93)), ("L_Fill", (0.97, 0.97, 1.0)), ("L_Rim", (0.95, 0.97, 1.0)),
                 ("L_RimL", (1.0, 0.95, 0.92))):
    lo = bpy.data.objects.get(nm)
    if lo:
        lo.data.color = colr
w = SC.world
bgn = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
bgn.inputs[1].default_value = 0.9
try:
    SC.view_settings.view_transform = "Standard"
except TypeError:
    pass
bc.setup_cycles_gpu(SC, SAMPLES)
SC.render.image_settings.file_format = "PNG"
cam_data = bpy.data.cameras.new("_RvCam")
cam = bpy.data.objects.new("_RvCam", cam_data)
SC.collection.objects.link(cam)
SC.camera = cam
cam_data.clip_start = 0.005


def shot(name, loc, target, lens=50, res=(1600, 1000), ortho=None, roll_up=(0, 0, 1)):
    cam.location = Vector(loc)
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho
    else:
        cam_data.type = "PERSP"
        cam_data.lens = lens
    SC.render.resolution_x, SC.render.resolution_y = res
    SC.render.resolution_percentage = 100
    p = os.path.join(OUT, name + ".png")
    SC.render.filepath = p
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("GPU render failed, CPU fallback", e)
        SC.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("RENDERED", p, flush=True)
    return p


DEFAULT = ["base", "stock_standard", "mag_30"]

# ------------------------------------------------------------------ fit check (BVH) of attachments vs the current gun
if "fit" in GROUPS:
    def bvh_of(objs):
        bm = bmesh.new()
        dg = bpy.context.evaluated_depsgraph_get()
        for o in objs:
            me = o.evaluated_get(dg).to_mesh()
            tmp = bmesh.new()
            tmp.from_mesh(me)
            tmp.transform(o.matrix_world)
            m2 = bpy.data.meshes.new("_t")
            tmp.to_mesh(m2)
            bm.from_mesh(m2)
            bpy.data.meshes.remove(m2)
            tmp.free()
            o.evaluated_get(dg).to_mesh_clear()
        return BVHTree.FromBMesh(bm), bm

    gun_keys = ["base", "stock_standard", "mag_30"]
    fit = {}
    gun_bvh, gun_bm = bvh_of(meshes(gun_keys))
    for k in ("optic_holo", "optic_3x", "grip_vertical", "ugl", "laser_R", "flashlight_L", "shield"):
        b, bm = bvh_of(meshes([k]))
        hits = gun_bvh.overlap(b)
        # min distance from attachment verts to the gun
        md = 1e9
        for v in bm.verts:
            r = gun_bvh.find_nearest(v.co)
            if r[0] is not None:
                md = min(md, r[3])
        fit[k] = {"overlapping_tri_pairs": len(hits), "min_vertex_gap_m": round(md, 5)}
        bm.free()
    # drum and mag_45 vs UGL / grip (loadout combos)
    for a, b in (("ugl", "mag_30"), ("ugl", "mag_45"), ("ugl", "mag_drum60"), ("grip_vertical", "mag_drum60"),
                 ("shield", "laser_R"), ("shield", "flashlight_L")):
        ba, bma = bvh_of(meshes([a]))
        bb, bmb = bvh_of(meshes([b]))
        md = 1e9
        for v in bma.verts:
            r = bb.find_nearest(v.co)
            if r[0] is not None:
                md = min(md, r[3])
        fit[f"{a} vs {b}"] = {"overlapping_tri_pairs": len(ba.overlap(bb)), "min_vertex_gap_m": round(md, 5)}
        bma.free()
        bmb.free()
    # optic sight line clearance: ray from the holo ADS point forward along -Y; does it hit the gun or shield?
    ads = sock("Optic") + Vector((0, -0.0124, 0.045))
    hit = gun_bvh.ray_cast(ads, Vector((0, -1, 0)), 2.0)
    fit["holo_sightline_hits_gun"] = None if hit[0] is None else [round(v, 4) for v in hit[0]]
    sb, sbm = bvh_of(meshes(["shield"]))
    hit = sb.ray_cast(ads, Vector((0, -1, 0)), 2.0)
    fit["holo_sightline_hits_shield_at"] = None if hit[0] is None else [round(v, 4) for v in hit[0]]
    # imported GLB node names / hierarchy summary
    fit["glb_nodes"] = {k: sorted(o.name for o in v) for k, v in SETS.items() if k in
                        ("base", "stock_standard", "mag_30", "mag_drum60")}
    with open(os.path.join(HERE, "review", "fit_report.json"), "w") as f:
        json.dump(fit, f, indent=1)
    print("FIT", json.dumps(fit, indent=0), flush=True)

# ------------------------------------------------------------------ first-person / ADS (the views the player sees 90 % of the time)
if "fp" in GROUPS:
    show(DEFAULT + ["optic_holo"])
    # hip/viewmodel: eye ~0.13 m left (+X) of the gun, ~0.17 m above the grip, ~0.33 m behind it; 70 deg-ish FOV
    shot("fp_hip_holo", (0.13, 0.33, 0.17), (0.02, -0.45, 0.02), lens=24, res=(1600, 900))
    show(DEFAULT)
    shot("fp_hip_nooptic", (0.13, 0.33, 0.17), (0.02, -0.45, 0.02), lens=24, res=(1600, 900))
    show(DEFAULT + ["optic_holo"])
    ads = sock("Optic") + Vector((0, -0.0124, 0.045))
    shot("fp_ads_holo", (0, 0.16, ads.z), (0, -1.0, ads.z), lens=28, res=(1600, 900))
    show(DEFAULT + ["optic_holo", "grip_vertical", "laser_R", "flashlight_L", "shield"])
    shot("fp_ads_holo_shield", (0, 0.16, ads.z), (0, -1.0, ads.z), lens=28, res=(1600, 900))
    shot("fp_hip_full", (0.13, 0.33, 0.17), (0.02, -0.45, 0.02), lens=24, res=(1600, 900))
    # third-person enemy view at ~8 m equivalent framing (small on screen) for readability
    show(DEFAULT + ["optic_holo"])
    shot("tp_small_side", (1.6, -0.14, 0.05), (0, -0.14, -0.02), lens=50, res=(480, 270))

# ------------------------------------------------------------------ worst angles
if "worst" in GROUPS:
    show(DEFAULT)
    c = Vector((0, -0.14, -0.04))
    shot("worst_bottom", (0.0005, -0.14, -1.6), c, lens=50, res=(1800, 700))
    shot("worst_rear_high", (-0.05, 0.75, 0.42), (0, -0.05, 0.02), lens=45, res=(1400, 1000))
    shot("worst_front_low", (-0.35, -0.95, -0.25), c, lens=50, res=(1400, 1000))
    shot("worst_right_below", (-0.75, -0.25, -0.45), c, lens=50, res=(1600, 1000))
    shot("worst_left_high_rear", (0.55, 0.55, 0.45), (0, -0.1, 0.02), lens=40, res=(1600, 1000))
    shot("worst_straight_rear_eyelevel", (0, 1.2, 0.06), (0, 0, 0.0), lens=85, res=(900, 900))

# ------------------------------------------------------------------ v09 comparison with the default optic mounted
if "v09" in GROUPS:
    show(DEFAULT + ["optic_holo"])
    d = Vector((0.72, -0.45, 0.52)).normalized()
    cen = Vector((0.0, -0.16, -0.03))
    shot("v09dir_with_holo", cen + d * 1.55, cen, lens=50, res=(1536, 896))
    show(DEFAULT)
    shot("side_ortho_plus_x", (1.0, -0.143, -0.04), (0, -0.143, -0.04), ortho=0.92, res=(1600, 800))

# ------------------------------------------------------------------ clay (form, bevels, shading artefacts without colour)
if "clay" in GROUPS:
    clay = bpy.data.materials.new("_clay")
    p = next(n for n in clay.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (0.62, 0.62, 0.62, 1)
    p.inputs["Roughness"].default_value = 0.5
    SC.view_layers[0].material_override = clay
    show(DEFAULT)
    shot("clay_three_quarter", (0.62, -0.75, 0.38), (0, -0.14, -0.02), lens=50, res=(1800, 1100))
    shot("clay_receiver_minusX", (-0.42, -0.02, 0.12), (0, -0.06, 0.01), lens=60, res=(1600, 1100))
    shot("clay_receiver_plusX_high", (0.38, 0.10, 0.26), (0, -0.06, 0.01), lens=60, res=(1600, 1100))
    shot("clay_grip_rear_low", (0.20, 0.30, -0.20), (0, 0.03, -0.05), lens=70, res=(1400, 1100))
    shot("clay_handguard_front", (0.18, -0.78, 0.12), (0, -0.45, 0.05), lens=70, res=(1400, 1000))
    SC.view_layers[0].material_override = None

# ------------------------------------------------------------------ wireframe overlay
if "wire" in GROUPS:
    show(DEFAULT)
    wmat = bpy.data.materials.new("_wire")
    wn = wmat.node_tree.nodes
    pb = next(n for n in wn if n.type == "BSDF_PRINCIPLED")
    em = wn.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.0, 0.25, 0.9, 1)
    em.inputs["Strength"].default_value = 1.0
    outn = next(n for n in wn if n.type == "OUTPUT_MATERIAL")
    wmat.node_tree.links.new(em.outputs[0], outn.inputs[0])
    dups = []
    for o in meshes(DEFAULT):
        d = o.copy()
        d.data = o.data.copy()
        SC.collection.objects.link(d)
        m = d.modifiers.new("w", "WIREFRAME")
        m.thickness = 0.00022
        m.use_replace = True
        d.data.materials.clear()
        d.data.materials.append(wmat)
        dups.append(d)
    for d in dups:
        d.hide_render = False
    shot("wire_three_quarter", (0.62, -0.75, 0.38), (0, -0.14, -0.02), lens=50, res=(2000, 1250))
    shot("wire_receiver_plusX", (0.40, -0.05, 0.05), (0, -0.05, 0.0), lens=55, res=(1800, 1200))
    shot("wire_handguard_minusX", (-0.30, -0.33, 0.10), (0, -0.33, 0.045), lens=55, res=(1800, 1100))
    for d in dups:
        bpy.data.objects.remove(d, do_unlink=True)

# ------------------------------------------------------------------ silhouettes (64 px read test)
if "sil" in GROUPS:
    blk = bpy.data.materials.new("_blk")
    pb = next(n for n in blk.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    pb.inputs["Base Color"].default_value = (0, 0, 0, 1)
    pb.inputs["Roughness"].default_value = 1.0
    pb.inputs["Specular IOR Level"].default_value = 0.0
    SC.view_layers[0].material_override = blk
    bgn.inputs[0].default_value = (1, 1, 1, 1)
    bgn.inputs[1].default_value = 1.0
    for k in ("L_Key", "L_Fill", "L_Rim", "L_RimL"):
        if bpy.data.objects.get(k):
            bpy.data.objects[k].hide_render = True
    show(DEFAULT + ["optic_holo"])
    shot("sil_side_holo", (1.0, -0.143, -0.02), (0, -0.143, -0.02), ortho=0.95, res=(800, 400))
    shot("sil_three_quarter_holo", (0.62, -0.75, 0.38), (0, -0.14, -0.02), lens=50, res=(800, 500))
    show(DEFAULT)
    shot("sil_side_nooptic", (1.0, -0.143, -0.04), (0, -0.143, -0.04), ortho=0.95, res=(800, 400))
    for k in ("L_Key", "L_Fill", "L_Rim", "L_RimL"):
        if bpy.data.objects.get(k):
            bpy.data.objects[k].hide_render = False
    SC.view_layers[0].material_override = None
    bgn.inputs[0].default_value = (0.55, 0.55, 0.55, 1)
    bgn.inputs[1].default_value = 0.9

# ------------------------------------------------------------------ close-ups the builder did not show
if "close" in GROUPS:
    show(DEFAULT)
    shot("cu_ch_fa_castle_rear_minusX", (-0.16, 0.20, 0.16), (0, 0.025, 0.058), lens=70, res=(1400, 1000))
    shot("cu_ch_top_rear", (0.02, 0.24, 0.20), (0, 0.03, 0.065), lens=80, res=(1400, 1000))
    shot("cu_dustcover_minusX", (-0.22, -0.06, 0.10), (0, -0.06, 0.05), lens=80, res=(1400, 1000))
    shot("cu_grip_junction_rear_below", (0.12, 0.22, -0.16), (0, 0.03, -0.02), lens=70, res=(1400, 1000))
    shot("cu_magwell_front_below", (-0.10, -0.40, -0.16), (0, -0.13, -0.02), lens=70, res=(1400, 1000))
    shot("cu_stock_front_tube_entry", (0.14, 0.02, 0.02), (0, 0.13, 0.04), lens=60, res=(1400, 1000))
    shot("cu_stock_under", (0.10, 0.12, -0.22), (0, 0.20, 0.0), lens=60, res=(1400, 1000))
    shot("cu_handguard_bottom", (0.03, -0.33, -0.30), (0, -0.33, 0.03), lens=55, res=(1800, 900))
    shot("cu_handguard_rear_joint_top", (0.16, -0.10, 0.22), (0, -0.18, 0.06), lens=70, res=(1400, 1000))
    shot("cu_rail_front_end", (0.10, -0.62, 0.15), (0, -0.48, 0.07), lens=70, res=(1400, 1000))
    shot("cu_mag_window_plusX", (0.22, -0.13, -0.06), (0, -0.13, -0.07), lens=80, res=(1000, 1200))
    show(["base", "stock_precision", "mag_30"])
    shot("cu_precision_cheek", (0.20, 0.05, 0.16), (0, 0.17, 0.06), lens=60, res=(1400, 1000))
    shot("cu_precision_side_plusX", (0.45, 0.165, 0.01), (0, 0.165, 0.01), lens=70, res=(1400, 1000))
    show(["base", "stock_light", "mag_drum60"])
    shot("cu_light_stock_3q", (0.25, 0.42, 0.10), (0, 0.20, 0.02), lens=60, res=(1400, 1000))
    shot("cu_drum_front_low_minusX", (-0.30, -0.42, -0.14), (0, -0.12, -0.07), lens=60, res=(1400, 1000))
    shot("cu_drum_minusX_side", (-0.45, -0.12, -0.08), (0, -0.12, -0.08), lens=70, res=(1400, 1000))

# ------------------------------------------------------------------ variants: 3/4 hero of the non-default sets + full loadout
if "variants" in GROUPS:
    hero = ((0.62, -0.75, 0.38), (0, -0.14, -0.02))
    show(["base", "stock_precision", "mag_45", "optic_3x"])
    shot("var_precision_mag45_3x", *hero, lens=50, res=(1600, 1000))
    show(["base", "stock_light", "mag_drum60", "optic_holo"])
    shot("var_light_drum_holo", *hero, lens=50, res=(1600, 1000))
    show(DEFAULT + ["optic_holo", "ugl", "laser_R", "flashlight_L"])
    shot("var_full_ugl", *hero, lens=50, res=(1600, 1000))
    show(DEFAULT + ["optic_holo", "grip_vertical", "laser_R", "flashlight_L", "shield"])
    shot("var_full_shield", (0.75, -0.95, 0.40), (0, -0.16, -0.02), lens=50, res=(1600, 1000))
print("RV DONE", flush=True)
