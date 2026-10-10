"""Reviewer test (does NOT touch the asset): same eye-through-glass view as v2_render.py 'ads', but with the imported
glass material re-tinted in this scratch scene, to show the recommended fix. EEVEE."""
import math, os, sys
sys.path.insert(0, r"F:/git/val etf/tools")
import bpy
from mathutils import Vector
import blender_common as bc
HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
WEAP = r"F:/git/val etf/assets/weapons"
OUT = os.path.join(HERE, "review", "v2", "renders", "ads")
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)

def imp(path, loc=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    root = next(o for o in new if o.parent is None)
    if loc is not None:
        root.location = loc
    bpy.context.view_layer.update()
    return root, new

for tag, col, alpha in (("current", None, None), ("fix_dark_a40", (0.02, 0.045, 0.08), 0.40),
                        ("fix_dark_a30", (0.02, 0.045, 0.08), 0.30)):
    reset()
    bc.setup_studio(bpy.context.scene)
    sc = bpy.context.scene
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            pass
    g, gobjs = imp(os.path.join(WEAP, "ar7_mako", "mako_default.glb"))
    S = {o.name.replace("MAKO_SOCKET_", ""): o.matrix_world.translation.copy() for o in gobjs if "_SOCKET_" in o.name}
    _, holo = imp(os.path.join(WEAP, "attachments", "optics", "ATT_optic_holo.glb"), S["Optic"])
    _, sh = imp(os.path.join(HERE, "ATT_shield_front.glb"), S["Shield"])
    if col:
        m = bpy.data.materials["M_ATT_ShieldGlass"]
        p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        for l in list(p.inputs["Base Color"].links):
            m.node_tree.links.remove(l)
        p.inputs["Base Color"].default_value = (*col, 1)
        for l in list(p.inputs["Alpha"].links):
            m.node_tree.links.remove(l)
        p.inputs["Alpha"].default_value = alpha
    sun = bpy.data.objects.new("_Sun", bpy.data.lights.new("_Sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    sc.collection.objects.link(sun)
    sc.world.use_nodes = True
    bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.55, 0.65, 0.8, 1)
    bg.inputs[1].default_value = 1.0
    ads = next(x for x in holo if x.name.endswith("SOCKET_ADS")).matrix_world.translation.copy()
    for i in range(6):
        for j in range(6):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(-0.75 + i * 0.3, -8.0, ads.z - 0.75 + j * 0.3))
            t = bpy.context.active_object
            t.scale = (0.3, 0.05, 0.3)
            bc.assign(t, bc.material(f"_Chk{(i + j) % 2}", (0.9, 0.9, 0.9) if (i + j) % 2 else (0.02, 0.02, 0.02), rough=0.6))
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.9, -8.0, ads.z - 0.2))
    p_ = bpy.context.active_object
    p_.scale = (0.45, 0.05, 1.8)
    bc.assign(p_, bc.material("_Tgt", (0.9, 0.3, 0.05), rough=0.6))
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, -10, ads.z - 1.55))
    bc.assign(bpy.context.active_object, bc.material("_Gnd", (0.2, 0.22, 0.17), rough=0.9))
    for ob in holo:
        ob.hide_render = True
    cd = bpy.data.cameras.new("_C"); cam = bpy.data.objects.new("_C", cd); sc.collection.objects.link(cam)
    cd.sensor_fit = "HORIZONTAL"; cd.angle = math.radians(40); cd.clip_start = 0.002
    cam.location = ads + Vector((0, 0.06, 0))
    cam.rotation_euler = (Vector((0, -5, 0))).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.filepath = os.path.join(OUT, f"glass_test_{tag}_eevee.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", sc.render.filepath)
