"""Wireframe-over-clay renders of the exported default GLB (Cycles wireframe node, 1 px lines) + castle-nut / handguard-bore close-ups."""
import os, sys, json
import bpy
from mathutils import Vector
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc
HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
OUT = os.path.join(HERE, "review", "renders")
bc.reset_scene(); SC = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=os.path.join(HERE, "mako_default.glb"))
bc.setup_studio(bg=(0.55, 0.55, 0.55), strength=0.28)
try: SC.view_settings.view_transform = "Standard"
except TypeError: pass
bc.setup_cycles_gpu(SC, 32)
cam = bpy.data.objects.new("_c", bpy.data.cameras.new("_c")); SC.collection.objects.link(cam); SC.camera = cam
cam.data.clip_start = 0.003
def shot(name, loc, tgt, lens, res):
    cam.location = Vector(loc); cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = lens; SC.render.resolution_x, SC.render.resolution_y = res
    SC.render.filepath = os.path.join(OUT, name + ".png")
    try: bpy.ops.render.render(write_still=True)
    except RuntimeError: SC.cycles.device = "CPU"; bpy.ops.render.render(write_still=True)
    print("RENDERED", name, flush=True)
# normal-material close-ups first
shot("cu_castle_nut_plusX", (0.10, 0.10, 0.10), (0, 0.04, 0.05), 90, (1400, 1000))
shot("cu_handguard_bore_front", (0.0, -0.75, 0.056), (0, 0, 0.056), 120, (1200, 1000))
# wire over clay
m = bpy.data.materials.new("_wireclay"); nt = m.node_tree; N = nt.nodes
p = next(n for n in N if n.type == "BSDF_PRINCIPLED"); p.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1); p.inputs["Roughness"].default_value = 0.6
w = N.new("ShaderNodeWireframe"); w.use_pixel_size = True; w.inputs[0].default_value = 1.0
d = N.new("ShaderNodeBsdfDiffuse"); d.inputs[0].default_value = (0.0, 0.05, 0.35, 1)
mix = N.new("ShaderNodeMixShader"); out = next(n for n in N if n.type == "OUTPUT_MATERIAL")
nt.links.new(w.outputs[0], mix.inputs[0]); nt.links.new(p.outputs[0], mix.inputs[1]); nt.links.new(d.outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], out.inputs[0])
SC.view_layers[0].material_override = m
shot("wire_three_quarter", (0.62, -0.75, 0.38), (0, -0.14, -0.02), 50, (2000, 1250))
shot("wire_receiver_plusX", (0.36, -0.06, 0.06), (0, -0.06, 0.0), 55, (1800, 1200))
shot("wire_receiver_minusX", (-0.36, -0.06, 0.08), (0, -0.06, 0.0), 55, (1800, 1200))
shot("wire_handguard_minusX", (-0.30, -0.33, 0.10), (0, -0.33, 0.045), 55, (1800, 1100))
shot("wire_stock_mag", (0.45, 0.05, -0.05), (0, 0.02, -0.04), 45, (1800, 1200))
