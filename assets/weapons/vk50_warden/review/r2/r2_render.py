"""Round-2 review renders, made from the EXPORTED .glb files (so they also verify the export).
Angles the builder did not show: worst angles, underside, stock riser close-ups, joints, magwell without mag,
full showcase loadout (other agents' optic_sniper + bipod) incl. first-person, clay + wireframe, dark backdrop
(see-through slots), mag check pulled out, bolt open with the optic mounted.

Run: blender -b --factory-startup -P r2_render.py -- [only_substring ...]
"""
import math, os, sys
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc

D = r"F:/git/val etf/assets/weapons/vk50_warden"
OUT = os.path.join(D, "review", "r2", "renders")
ATT_O = r"F:/git/val etf/assets/weapons/attachments/optics"
ATT_T = r"F:/git/val etf/assets/weapons/attachments/tactical"
ONLY = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
os.makedirs(OUT, exist_ok=True)
SAMPLES = int(os.environ.get("R2_SAMPLES", "40"))


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def scene_setup(bg=(0.55, 0.56, 0.58)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    bc.setup_studio(sc, bg=bg, strength=1.0)
    bc.setup_cycles_gpu(sc, SAMPLES)
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    try:
        sc.view_settings.look = "AgX - Punchy"
        sc.view_settings.exposure = -0.2
    except Exception:
        pass
    return sc


def load_default():
    objs = imp(os.path.join(D, "warden_default.glb"))
    return {o.name: o for o in objs}, objs


def mount(by, path, sock):
    new = imp(path)
    s = by[f"WARDEN_SOCKET_{sock}"].matrix_world.translation.copy()
    for r in [o for o in new if o.parent is None]:
        r.matrix_world = Matrix.Translation(s) @ r.matrix_world
    bpy.context.view_layer.update()
    return new


def cam_shot(name, loc, target, lens=50, res=(1400, 900), ortho=None):
    if ONLY and not any(k in name for k in ONLY):
        return
    sc = bpy.context.scene
    cd = bpy.data.cameras.get("_cam") or bpy.data.cameras.new("_cam")
    co = bpy.data.objects.get("_cam") or bpy.data.objects.new("_cam", cd)
    if co.name not in sc.collection.objects:
        sc.collection.objects.link(co)
    cd.lens = lens; cd.clip_start = 0.005; cd.clip_end = 100
    if ortho:
        cd.type = "ORTHO"; cd.ortho_scale = ortho
    else:
        cd.type = "PERSP"
    co.location = Vector(loc)
    co.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = co
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, name + ".png")
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("GPU render failed, CPU fallback", e)
        sc.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("RENDERED", name)


def clay(objs, color=(0.62, 0.62, 0.62)):
    m = bpy.data.materials.get("_clay") or bpy.data.materials.new("_clay")
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = 0.6
    for o in objs:
        if o.type == "MESH":
            o.data.materials.clear(); o.data.materials.append(m)


def wire_overlay(objs, thickness=0.00025):
    """Add a wireframe-modifier copy in black over each mesh (for topology density read)."""
    wm = bpy.data.materials.get("_wire") or bpy.data.materials.new("_wire")
    wm.use_nodes = True
    p = next(n for n in wm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (0.01, 0.01, 0.01, 1)
    out = []
    for o in [x for x in objs if x.type == "MESH"]:
        c = o.copy(); c.data = o.data.copy(); c.name = "_w_" + o.name
        bpy.context.scene.collection.objects.link(c)
        c.matrix_world = o.matrix_world.copy()
        c.data.materials.clear(); c.data.materials.append(wm)
        md = c.modifiers.new("w", "WIREFRAME"); md.thickness = thickness; md.use_replace = True
        out.append(c)
    return out


def silhouette_mode(objs, bg=(1, 1, 1)):
    m = bpy.data.materials.get("_black") or bpy.data.materials.new("_black")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (0, 0, 0, 1)
    o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs[0], o.inputs[0])
    for x in objs:
        if x.type == "MESH":
            x.data.materials.clear(); x.data.materials.append(m)
    w = bpy.context.scene.world
    bgn = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bgn.inputs[0].default_value = (*bg, 1); bgn.inputs[1].default_value = 1.0
    for l in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        l.hide_render = True
    bpy.context.scene.view_settings.view_transform = "Standard"
    bpy.context.scene.view_settings.look = "None"


# ======================================================================= A. default gun, new angles
sc = scene_setup()
by, objs = load_default()
C = Vector((0, -0.39, 0.0))   # rough gun centre
cam_shot("r2_worst_front_high_left", (0.75, -1.65, 0.75), (0, -0.45, 0.05), lens=50, res=(1600, 900))
cam_shot("r2_worst_below", (0.0, -0.39, -1.6), (0, -0.39, 0.0), lens=50, res=(1600, 700))
cam_shot("r2_worst_rear_low_right", (-0.55, 0.85, -0.30), (0, -0.05, 0.0), lens=50, res=(1400, 900))
cam_shot("r2_worst_rear_high_left", (0.55, 0.75, 0.55), (0, 0.0, 0.05), lens=50, res=(1400, 900))
cam_shot("r2_cu_stock_riser_right", (-0.42, 0.24, 0.16), (0, 0.21, 0.07), lens=60)
cam_shot("r2_cu_stock_riser_top", (0.18, 0.36, 0.42), (0, 0.20, 0.07), lens=60)
cam_shot("r2_cu_receiver_rear_top", (-0.12, 0.42, 0.36), (0, 0.06, 0.09), lens=55)
cam_shot("r2_cu_handguard_front_low", (0.22, -0.95, -0.02), (0, -0.66, 0.06), lens=60)
cam_shot("r2_cu_rail_joint_top", (0.10, -0.18, 0.40), (0, -0.30, 0.13), lens=70)
cam_shot("r2_cu_grip_guard_below_left", (0.25, -0.15, -0.30), (0, -0.04, -0.04), lens=60)
cam_shot("r2_cu_handguard_top_vents", (-0.10, -0.30, 0.36), (0, -0.48, 0.12), lens=60)
cam_shot("r2_cu_receiver_left_safety", (0.40, 0.05, 0.12), (0, 0.0, 0.05), lens=60)
# side, dark backdrop (game backdrops vary): see-through slots
w = sc.world; bgn = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
old = tuple(bgn.inputs[0].default_value)
bgn.inputs[0].default_value = (0.02, 0.022, 0.026, 1)
cam_shot("r2_side_left_darkbg", (1.9, -0.39, 0.05), (0, -0.39, 0.0), lens=50, res=(1600, 700))
bgn.inputs[0].default_value = (0.9, 0.92, 0.95, 1)
cam_shot("r2_side_left_skybg", (1.9, -0.39, 0.05), (0, -0.39, 0.0), lens=50, res=(1600, 700))
bgn.inputs[0].default_value = old

# magwell with no mag (base only look from below)
for o in [o for o in objs if o.name.startswith("WARDEN_Mag5")]:
    o.hide_render = True
cam_shot("r2_cu_magwell_empty_below", (0.16, -0.30, -0.36), (0, -0.20, -0.02), lens=55)
for o in [o for o in objs if o.name.startswith("WARDEN_Mag5")]:
    o.hide_render = False

# ======================================================================= B. clay + wireframe
meshes = [o for o in objs if o.type == "MESH"]
clay(meshes)
cam_shot("r2_clay_three_quarter", (0.95, -1.35, 0.45), (0, -0.40, 0.03), lens=50, res=(1600, 900))
cam_shot("r2_clay_cu_receiver_left", (0.38, -0.12, 0.16), (0, -0.10, 0.05), lens=55)
cam_shot("r2_clay_cu_stock_left", (0.40, 0.22, 0.08), (0, 0.20, 0.0), lens=55)
ws = wire_overlay(meshes)
cam_shot("r2_wire_three_quarter", (0.95, -1.35, 0.45), (0, -0.40, 0.03), lens=50, res=(1600, 900))
cam_shot("r2_wire_cu_receiver_right", (-0.38, -0.10, 0.14), (0, -0.10, 0.06), lens=55)
for c in ws:
    bpy.data.objects.remove(c, do_unlink=True)

# ======================================================================= C. full showcase loadout
sc = scene_setup()
by, objs = load_default()
opt = mount(by, os.path.join(ATT_O, "ATT_optic_sniper.glb"), "Optic")
bip = mount(by, os.path.join(ATT_T, "ATT_bipod.glb"), "Under")
cam_shot("r2_loadout_left_side", (1.9, -0.39, 0.02), (0, -0.39, 0.0), lens=50, res=(1600, 800))
cam_shot("r2_loadout_three_quarter", (0.95, -1.35, 0.45), (0, -0.40, 0.0), lens=50, res=(1600, 900))
cam_shot("r2_loadout_rear_right", (-0.85, 0.95, 0.35), (0, -0.25, 0.03), lens=50, res=(1600, 900))
# first person: eye a bit above + right of the ADS line, hip-ish viewmodel framing (camera looks down the gun)
cam_shot("r2_loadout_fpv_hip", (-0.13, 0.42, 0.24), (0.02, -0.75, 0.05), lens=22, res=(1600, 900))
cam_shot("r2_loadout_fpv_ads_eye", (0.0, 0.16, 0.178), (0.0, -1.0, 0.178), lens=30, res=(1600, 900))
# bolt open with optic mounted, shooter's right view
bolt = by["WARDEN_Bolt"]; bolt.rotation_mode = "XYZ"
r0 = bolt.rotation_euler.copy(); l0 = bolt.location.copy()
bolt.rotation_euler = (r0.x, r0.y + math.radians(60), r0.z); bolt.location = l0 + Vector((0, 0.13, 0))
bpy.context.view_layer.update()
cam_shot("r2_loadout_bolt_open_right", (-0.55, 0.30, 0.30), (0, 0.08, 0.10), lens=55)
cam_shot("r2_loadout_bolt_open_fpv", (-0.10, 0.36, 0.26), (0.0, -0.3, 0.08), lens=28)
bolt.rotation_euler = r0; bolt.location = l0
# silhouettes (side / front / top / 3q) for the 64 px read with the full loadout
allm = [o for o in bpy.data.objects if o.type == "MESH"]
silhouette_mode(allm)
cam_shot("r2_sil_loadout_side", (3.0, -0.39, 0.0), (0, -0.39, 0.0), res=(1600, 600), ortho=1.6)
cam_shot("r2_sil_loadout_three_quarter", (0.95, -1.35, 0.45), (0, -0.40, 0.0), lens=50, res=(1600, 900))
cam_shot("r2_sil_loadout_front", (0, -3.0, 0.02), (0, 0, 0.02), res=(900, 900), ortho=0.6)

# ======================================================================= D. bare gun silhouette (no attachments)
sc = scene_setup()
by, objs = load_default()
silhouette_mode([o for o in objs if o.type == "MESH"])
cam_shot("r2_sil_gun_side", (3.0, -0.39, 0.0), (0, -0.39, 0.0), res=(1600, 600), ortho=1.6)
cam_shot("r2_sil_gun_top", (0.0, -0.39, 3.0), (0, -0.39, 0.0), res=(1600, 600), ortho=1.6)

# ======================================================================= E. mag check (mag_5, 2 rounds left, pulled out)
sc = scene_setup()
m5 = imp(os.path.join(D, "WARDEN_mag_5.glb"))
byk = {o.name: o for o in m5}
fol = byk["WARDEN_Mag5_Follower"]
for nm in ("WARDEN_Mag5_Round_03", "WARDEN_Mag5_Round_04", "WARDEN_Mag5_Round_05"):
    byk[nm].hide_render = True
fol.location.z += 3 * 0.021
root = byk["WARDEN_Mag5"]
root.rotation_euler = (math.radians(-20), math.radians(0), math.radians(35))
bpy.context.view_layer.update()
mn, mx = bc.world_bounds([o for o in m5 if o.type == "MESH"])
cen = (mn + mx) / 2
eye = cen + Vector((0.42, -0.12, 0.10))
cam_shot("r2_magcheck_2left_tilted", eye, cen, lens=60, res=(1200, 900))
for nm in ("WARDEN_Mag5_Round_03", "WARDEN_Mag5_Round_04", "WARDEN_Mag5_Round_05"):
    byk[nm].hide_render = False
fol.location.z -= 3 * 0.021
cam_shot("r2_magcheck_full_tilted", eye, cen, lens=60, res=(1200, 900))
print("DONE")
