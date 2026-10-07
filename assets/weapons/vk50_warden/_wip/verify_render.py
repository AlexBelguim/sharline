"""Reviewer renders for the VK-50 WARDEN, built ONLY from the exported .glb files (also verifies the export).

Run: blender -b --factory-startup -P review_render.py -- <group> [<group> ...]
Groups: clay, wire, worst, bolt, loadout, mag, fold, sil
Writes into review/renders/. Never modifies the asset.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

D = r"F:/git/val etf/assets/weapons/vk50_warden"
ATT = r"F:/git/val etf/assets/weapons/attachments"
OUT = os.path.join(D, "_wip", "verify_renders")
os.makedirs(OUT, exist_ok=True)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["clay"]
SAMPLES = 40


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bc.setup_studio(bg=(0.24, 0.25, 0.27))
    sc = bpy.context.scene
    sc.view_settings.exposure = -0.2
    try:
        sc.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass


def imp(path, at=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    if at is not None:
        for r in [o for o in new if o.parent is None]:
            r.matrix_world = Matrix.Translation(Vector(at)) @ r.matrix_world
    bpy.context.view_layer.update()
    return new


def default():
    objs = imp(os.path.join(D, "warden_default.glb"))
    return {o.name: o for o in objs}


def cam_render(name, target, direction, dist, lens=60, res=(1400, 900), ortho=None, transparent=False):
    sc = bpy.context.scene
    bc.setup_cycles_gpu(sc, SAMPLES)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    cd = bpy.data.cameras.get("_RC") or bpy.data.cameras.new("_RC")
    cam = bpy.data.objects.get("_RC") or bpy.data.objects.new("_RC", cd)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cd.clip_start = 0.005
    cd.clip_end = 100
    if ortho:
        cd.type = "ORTHO"; cd.ortho_scale = ortho
    else:
        cd.type = "PERSP"; cd.lens = lens
    d = Vector(direction).normalized()
    cam.location = Vector(target) + d * dist
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    p = os.path.join(OUT, name + ".png")
    sc.render.filepath = p
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("GPU render failed, CPU fallback:", e)
        sc.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("RENDERED", p)
    return p


def flat_mat(name, color, rough=0.6, metal=0.0, alpha=1.0, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Alpha"].default_value = alpha
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = 1.5
    try:
        m.surface_render_method = "BLENDED" if alpha < 1 else "DITHERED"
    except Exception:
        pass
    return m


def override(objs, mat):
    for o in objs:
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(mat)
            for p in o.data.polygons:
                p.material_index = 0


def wire_mat():
    m = bpy.data.materials.new("_wire")
    m.use_nodes = True
    nt = m.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Roughness"].default_value = 0.7
    w = nt.nodes.new("ShaderNodeWireframe"); w.use_pixel_size = True; w.inputs[0].default_value = 1.0
    mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"
    mx.inputs[6].default_value = (0.62, 0.62, 0.64, 1); mx.inputs[7].default_value = (0.02, 0.05, 0.12, 1)
    nt.links.new(w.outputs[0], mx.inputs[0])
    nt.links.new(mx.outputs[2], p.inputs["Base Color"])
    return m


def meshes(d):
    return [o for o in d.values() if o.type == "MESH"]


def pose_bolt(b, lift=60, travel=0.13):
    b.rotation_mode = "XYZ"
    b.rotation_euler.y += math.radians(lift)
    b.location.y += travel
    bpy.context.view_layer.update()


# =================================================================================================== groups
def g_clay():
    reset(); d = default()
    override(meshes(d), flat_mat("_clay", (0.55, 0.55, 0.56), 0.55))
    cam_render("clay_three_quarter", (0, -0.40, 0.02), (0.75, -1, 0.35), 1.55, 50, (1800, 900))
    cam_render("clay_left_bolt_side", (0, -0.40, 0.02), (-1, 0, 0.05), 1.75, 50, (1800, 900))
    cam_render("clay_cu_handguard_right", (0, -0.50, 0.08), (-1, -0.35, 0.35), 0.42, 60, (1400, 900))
    cam_render("clay_cu_handguard_left", (0, -0.50, 0.08), (1, -0.25, 0.25), 0.42, 60, (1400, 900))
    cam_render("clay_cu_receiver_rear", (-0.02, 0.05, 0.05), (-0.8, 0.9, 0.5), 0.35, 60, (1400, 900))
    cam_render("clay_cu_stock", (0, 0.20, 0.0), (0.9, 0.5, 0.25), 0.55, 60, (1400, 900))
    cam_render("clay_cu_brake", (0, -1.02, 0.075), (0.8, -1, 0.5), 0.28, 60, (1400, 900))


def g_wire():
    reset(); d = default()
    override(meshes(d), wire_mat())
    cam_render("wire_left", (0, -0.40, 0.02), (-1, 0, 0.05), 1.75, 50, (2200, 1100))
    cam_render("wire_three_quarter", (0, -0.40, 0.02), (0.75, -1, 0.35), 1.55, 50, (2200, 1100))
    cam_render("wire_cu_receiver", (0, -0.12, 0.05), (-1, 0.2, 0.3), 0.5, 60, (1800, 1100))
    cam_render("wire_cu_stock", (0, 0.20, 0.0), (1, 0.2, 0.2), 0.55, 60, (1600, 1100))


def g_worst():
    reset(); d = default()
    cam_render("worst_below", (0, -0.40, -0.02), (0.12, -0.15, -1), 1.6, 50, (1800, 900))
    cam_render("worst_rear_high_right", (0, -0.30, 0.05), (-0.45, 1, 0.75), 1.5, 50, (1800, 1000))
    cam_render("worst_front_low_right", (0, -0.40, 0.03), (-0.75, -1, -0.25), 1.55, 50, (1800, 900))
    cam_render("worst_shooter_eye", (0, -0.6, 0.12), (0, 1, 0.12), 0.95, 35, (1600, 900))
    cam_render("worst_cu_stock_hinge_below", (0, 0.09, 0.0), (-0.5, 0.25, -0.8), 0.25, 60, (1400, 900))
    cam_render("worst_cu_trigger_below", (0, -0.05, -0.05), (0.6, -0.3, -0.75), 0.30, 60, (1400, 900))
    cam_render("worst_cu_magwell_below", (0, -0.19, -0.08), (-0.4, -0.6, -0.7), 0.35, 60, (1400, 900))
    cam_render("worst_cu_rail_joint_top", (0, -0.30, 0.13), (-0.35, -0.5, 0.8), 0.22, 60, (1400, 900))
    cam_render("worst_cu_handguard_front", (0, -0.68, 0.075), (-0.6, -1, 0.15), 0.25, 60, (1400, 900))
    cam_render("worst_top_rear", (0, 0.08, 0.05), (0, 0.0001, 1), 0.7, 60, (1400, 900))


def g_bolt():
    # 1. lifted in place: handle root vs receiver
    reset(); d = default()
    b = d["WARDEN_Bolt"]
    pose_bolt(b, 60, 0.0)
    cam_render("bolt_lifted_rear_right", (-0.02, 0.06, 0.09), (-0.6, 0.9, 0.55), 0.32, 60, (1400, 900))
    ghost = flat_mat("_ghost", (0.6, 0.65, 0.75), 0.5, alpha=0.18)
    hot = flat_mat("_hot", (1.0, 0.25, 0.05), 0.4, emit=(1.0, 0.25, 0.05))
    override([d["WARDEN_Receiver"], d["WARDEN_RailTop"]], ghost)
    override([b], hot)
    cam_render("bolt_lifted_xray", (-0.02, 0.06, 0.09), (-0.6, 0.9, 0.55), 0.32, 60, (1400, 900))
    # 2. fully open: bolt body vs stock comb + riser posts
    reset(); d = default()
    b = d["WARDEN_Bolt"]
    pose_bolt(b, 60, 0.13)
    cam_render("bolt_open_left_side", (0, 0.13, 0.07), (-1, 0, 0.12), 0.55, 60, (1600, 900))
    cam_render("bolt_open_shooter_view", (-0.02, 0.10, 0.10), (-0.25, 1, 0.55), 0.42, 45, (1600, 900))
    override([d["WARDEN_StockStandard"], d["WARDEN_StockStandard_CheekRiser"], d["WARDEN_Receiver"]],
             flat_mat("_ghost", (0.6, 0.65, 0.75), 0.5, alpha=0.18))
    override([b], flat_mat("_hot", (1.0, 0.25, 0.05), 0.4, emit=(1.0, 0.25, 0.05)))
    cam_render("bolt_open_xray_side", (0, 0.13, 0.07), (-1, 0, 0.12), 0.55, 60, (1600, 900))
    cam_render("bolt_open_xray_top", (0, 0.10, 0.07), (0, 0.0001, 1), 0.55, 60, (1600, 900))


def g_loadout():
    reset(); d = default()
    s = {k[len("WARDEN_SOCKET_"):]: o.matrix_world.translation.copy() for k, o in d.items() if "SOCKET" in k}
    imp(os.path.join(ATT, "optics", "ATT_optic_sniper.glb"), s["Optic"])
    imp(os.path.join(ATT, "tactical", "ATT_bipod.glb"), s["Under"])
    cam_render("loadout_right_vs_concept", (0, -0.39, 0.01), (1, 0, 0.0), 1.9, 50, (1800, 800))
    cam_render("loadout_three_quarter", (0, -0.40, 0.0), (0.75, -1, 0.35), 1.6, 50, (1800, 900))
    cam_render("loadout_left", (0, -0.39, 0.01), (-1, 0, 0.05), 1.9, 50, (1800, 800))
    cam_render("loadout_shooter_eye", (0, -0.5, 0.15), (-0.08, 1, 0.25), 0.85, 35, (1600, 900))
    # thermal on the same rail
    reset(); d = default()
    s = {k[len("WARDEN_SOCKET_"):]: o.matrix_world.translation.copy() for k, o in d.items() if "SOCKET" in k}
    imp(os.path.join(ATT, "optics", "ATT_optic_thermal.glb"), s["Optic"])
    imp(os.path.join(ATT, "tactical", "ATT_bipod.glb"), s["Under"])
    cam_render("loadout_thermal_three_quarter_back", (0, -0.30, 0.03), (-0.8, 0.9, 0.35), 1.5, 50, (1800, 900))


def g_mag():
    reset()
    m = {o.name: o for o in imp(os.path.join(D, "WARDEN_mag_5.glb"))}
    root = m["WARDEN_Mag5"]
    # mag check pose: held tilted, window side toward the camera
    root.rotation_mode = "XYZ"; root.rotation_euler = (math.radians(-20), math.radians(15), 0)
    bpy.context.view_layer.update()
    cam_render("mag5_full_check", (0, 0.07, -0.08), (1, 0.1, 0.05), 0.42, 60, (1200, 1000))
    for k in ("WARDEN_Mag5_Round_03", "WARDEN_Mag5_Round_04", "WARDEN_Mag5_Round_05"):
        m[k].hide_render = True
    f = m["WARDEN_Mag5_Follower"]   # raise it under the 2 remaining rounds (Blender +Z after import)
    f.matrix_world = f.matrix_world @ __import__("mathutils").Matrix.Translation((0, 0, f["travel_per_round_m"] * 3))
    bpy.context.view_layer.update()
    cam_render("mag5_two_left_check", (0, 0.07, -0.08), (1, 0.1, 0.05), 0.42, 60, (1200, 1000))
    for k in ("WARDEN_Mag5_Round_02",):
        m[k].hide_render = True
    m["WARDEN_Mag5_Round"].hide_render = True
    f.matrix_world = f.matrix_world @ __import__("mathutils").Matrix.Translation((0, 0, f["travel_max_m"] - f["travel_per_round_m"] * 3))
    bpy.context.view_layer.update()
    cam_render("mag5_empty_check", (0, 0.07, -0.08), (1, 0.1, 0.05), 0.42, 60, (1200, 1000))
    # inserted, as the player sees it from the side at full and at 2 rounds
    reset(); d = default()
    cam_render("mag5_inserted_full", (0, -0.20, -0.08), (1, -0.1, -0.05), 0.40, 60, (1200, 900))
    for k in ("WARDEN_Mag5_Round_03", "WARDEN_Mag5_Round_04", "WARDEN_Mag5_Round_05"):
        d[k].hide_render = True
    f = d["WARDEN_Mag5_Follower"]
    f.matrix_world = f.matrix_world @ __import__("mathutils").Matrix.Translation((0, 0, f["travel_per_round_m"] * 3))
    bpy.context.view_layer.update()
    cam_render("mag5_inserted_two_left", (0, -0.20, -0.08), (1, -0.1, -0.05), 0.40, 60, (1200, 900))


def g_fold():
    reset()
    b = {o.name: o for o in imp(os.path.join(D, "warden_base.glb"))}
    s_st = b["WARDEN_SOCKET_Stock"].matrix_world.translation.copy()
    s_mg = b["WARDEN_SOCKET_Mag"].matrix_world.translation.copy()
    sf = {o.name: o for o in imp(os.path.join(D, "WARDEN_stock_folding.glb"), s_st)}
    imp(os.path.join(D, "WARDEN_mag_8.glb"), s_mg)
    arm = sf["WARDEN_StockFolding_Arm"]
    arm.rotation_mode = "XYZ"; arm.rotation_euler.z += math.radians(-180)
    bpy.context.view_layer.update()
    cam_render("fold_left_side", (0, -0.25, 0.0), (1, 0, 0.1), 1.45, 50, (1800, 900))
    cam_render("fold_cu_hinge_rear", (0.04, 0.0, 0.03), (0.7, 0.8, 0.45), 0.40, 60, (1400, 900))
    cam_render("fold_top", (0, -0.25, 0.0), (0, 0.0001, 1), 1.45, 50, (1800, 900))


def g_sil():
    reset(); d = default()
    s = {k[len("WARDEN_SOCKET_"):]: o.matrix_world.translation.copy() for k, o in d.items() if "SOCKET" in k}
    black = flat_mat("_black", (0, 0, 0), 1.0)
    override(meshes(d), black)
    sc = bpy.context.scene
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sc.view_settings.view_transform = "Standard"
    for nm, dirn, ortho in (("front", (0, -1, 0.0), 0.42), ("top", (0, 0.0001, 1), 1.55), ("back", (0, 1, 0), 0.42),
                            ("three_quarter", (0.75, -1, 0.35), None)):
        cam_render(f"sil_{nm}", (0, -0.39, 0.0) if nm in ("top", "three_quarter") else (0, -0.39, -0.03), dirn,
                   1.6 if nm == "three_quarter" else 3.0, 50, (1000, 1000) if nm in ("front", "back") else (1600, 800),
                   ortho=ortho)


G = dict(clay=g_clay, wire=g_wire, worst=g_worst, bolt=g_bolt, loadout=g_loadout, mag=g_mag, fold=g_fold, sil=g_sil)
for a in argv:
    G[a]()
