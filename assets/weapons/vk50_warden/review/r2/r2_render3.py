"""Round-2 pass 3: close-up of the +X handguard top vents (boolean failure) and wireframe overlays
(even offset OFF so degenerate slivers do not explode the overlay)."""
import math, os, sys
import bpy
from mathutils import Vector, Euler
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc
D = r"F:/git/val etf/assets/weapons/vk50_warden"
OUT = os.path.join(D, "review", "r2", "renders")
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bc.setup_studio(sc, bg=(0.55, 0.56, 0.58)); bc.setup_cycles_gpu(sc, 40)
sc.view_settings.look = "AgX - Punchy"; sc.view_settings.exposure = -0.2
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=os.path.join(D, "warden_default.glb"))
objs = [o for o in bpy.data.objects if o not in before]
def shot(name, loc, target, lens=60, res=(1400, 900)):
    cd = bpy.data.cameras.get("_cam") or bpy.data.cameras.new("_cam")
    co = bpy.data.objects.get("_cam") or bpy.data.objects.new("_cam", cd)
    if co.name not in sc.collection.objects: sc.collection.objects.link(co)
    cd.lens = lens; cd.clip_start = 0.005; cd.type = "PERSP"
    co.location = Vector(loc); co.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = co; sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = os.path.join(OUT, name + ".png"); bpy.ops.render.render(write_still=True); print("RENDERED", name)
shot("r2_cu_topvents_left_failed", (0.16, -0.40, 0.30), (0.012, -0.475, 0.128), lens=70)
shot("r2_cu_topvents_right_ok", (-0.16, -0.40, 0.30), (-0.012, -0.475, 0.128), lens=70)
# wire overlay
wm = bpy.data.materials.new("_wire"); wm.use_nodes = True
p = next(n for n in wm.node_tree.nodes if n.type == "BSDF_PRINCIPLED"); p.inputs["Base Color"].default_value = (0, 0, 0, 1)
clay = bpy.data.materials.new("_clay"); clay.use_nodes = True
pc = next(n for n in clay.node_tree.nodes if n.type == "BSDF_PRINCIPLED"); pc.inputs["Base Color"].default_value = (0.72, 0.72, 0.72, 1)
for o in [x for x in objs if x.type == "MESH"]:
    o.data.materials.clear(); o.data.materials.append(clay); o.data.materials.append(wm)
    for poly in o.data.polygons: poly.material_index = 0
    md = o.modifiers.new("wire", "WIREFRAME"); md.thickness = 0.00018; md.use_replace = False
    md.material_offset = 1; md.use_even_offset = False; md.use_relative_offset = False
shot("r2_wire_three_quarter", (0.95, -1.35, 0.45), (0, -0.40, 0.03), lens=50, res=(1800, 1000))
shot("r2_wire_cu_receiver_right", (-0.40, -0.10, 0.12), (0, -0.10, 0.06), lens=50)
shot("r2_wire_cu_stock_right", (-0.42, 0.20, 0.05), (0, 0.20, 0.0), lens=50)
shot("r2_wire_cu_brake", (0.30, -1.25, 0.22), (0, -1.02, 0.075), lens=60)
shot("r2_wire_cu_handguard_left", (0.40, -0.48, 0.14), (0, -0.48, 0.08), lens=50)
print("DONE")
