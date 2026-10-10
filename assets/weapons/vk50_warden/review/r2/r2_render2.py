"""Round-2 review renders, pass 2 (from the exported warden_default.glb):
underside (correct framing), in-place wireframe overlays (modifier + material offset), top ortho of the
handguard top vents / side rails, and the bolt-shroud cap vs knob from the player's eye.
Run: blender -b --factory-startup -P r2_render2.py
"""
import math, os, sys
import bpy
from mathutils import Matrix, Vector, Euler
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc

D = r"F:/git/val etf/assets/weapons/vk50_warden"
OUT = os.path.join(D, "review", "r2", "renders")


def setup(bg=(0.55, 0.56, 0.58)):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    bc.setup_studio(sc, bg=bg, strength=1.0)
    bc.setup_cycles_gpu(sc, 40)
    sc.view_settings.look = "AgX - Punchy"; sc.view_settings.exposure = -0.2
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(D, "warden_default.glb"))
    objs = [o for o in bpy.data.objects if o not in before]
    return sc, {o.name: o for o in objs}, objs


def shot(name, loc, rot_deg=None, target=None, lens=50, res=(1400, 900), ortho=None):
    sc = bpy.context.scene
    cd = bpy.data.cameras.get("_cam") or bpy.data.cameras.new("_cam")
    co = bpy.data.objects.get("_cam") or bpy.data.objects.new("_cam", cd)
    if co.name not in sc.collection.objects:
        sc.collection.objects.link(co)
    cd.lens = lens; cd.clip_start = 0.005
    cd.type = "ORTHO" if ortho else "PERSP"
    if ortho:
        cd.ortho_scale = ortho
    co.location = Vector(loc)
    if rot_deg is not None:
        co.rotation_euler = Euler([math.radians(a) for a in rot_deg])
    else:
        co.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = co
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, name + ".png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name)


sc, by, objs = setup()
# underside: camera below looking up (+Z), image-right = muzzle side (-Y) -> rotate 180 about X then 90 about Z
shot("r2_worst_below", (0, -0.39, -1.0), rot_deg=(180, 0, 90), res=(1800, 600), ortho=1.5)
# top ortho close-up of the handguard top (vents beside the rail) + side rails; image-up = -X (shooter's right)
shot("r2_cu_handguard_top_ortho", (0, -0.50, 1.0), rot_deg=(0, 0, 90), res=(1600, 600), ortho=0.42)
# receiver top ortho (rail over receiver, bolt shroud, riser from above)
shot("r2_cu_receiver_top_ortho", (0, -0.06, 1.0), rot_deg=(0, 0, 90), res=(1600, 600), ortho=0.42)
# side ortho of the front handguard from +X (left side): side rail + slots, 1:1-ish detail
shot("r2_cu_handguard_side_ortho_left", (1.0, -0.52, 0.08), rot_deg=(90, 0, 90), res=(1600, 600), ortho=0.40)

# wireframe overlay in place: add wire material as last slot, WIREFRAME modifier (no replace) with offset
wm = bpy.data.materials.new("_wire"); wm.use_nodes = True
p = next(n for n in wm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
p.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1); p.inputs["Roughness"].default_value = 1.0
clay = bpy.data.materials.new("_clay"); clay.use_nodes = True
pc = next(n for n in clay.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
pc.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1); pc.inputs["Roughness"].default_value = 0.6
for o in [x for x in objs if x.type == "MESH"]:
    o.data.materials.clear(); o.data.materials.append(clay); o.data.materials.append(wm)
    for poly in o.data.polygons:
        poly.material_index = 0
    md = o.modifiers.new("wire", "WIREFRAME")
    md.thickness = 0.00022; md.use_replace = False; md.material_offset = 1; md.use_even_offset = True
shot("r2_wire_three_quarter", (0.95, -1.35, 0.45), target=(0, -0.40, 0.03), lens=50, res=(1800, 1000))
shot("r2_wire_cu_receiver_right", (-0.40, -0.10, 0.12), target=(0, -0.10, 0.06), lens=50)
shot("r2_wire_cu_stock_right", (-0.42, 0.20, 0.05), target=(0, 0.20, 0.0), lens=50)
shot("r2_wire_cu_brake", (0.30, -1.25, 0.22), target=(0, -1.02, 0.075), lens=60)
print("DONE")
