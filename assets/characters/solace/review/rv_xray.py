"""Independent review of SOLACE: x-ray of the exported skeleton inside the body (front + her right side + top)."""
import math, os, sys
import bpy
from mathutils import Vector
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc
OUT = r"F:/git/val etf/assets/characters/solace/review/renders"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r"F:/git/val etf/assets/characters/solace/solace.glb")
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere") or o.name.startswith("SOL_Bloom"):
        o.hide_render = True
arm = bpy.data.objects["SOL_Armature"]
ghost = bpy.data.materials.new("_ghost")
ghost.use_nodes = True
nt = ghost.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputMaterial")
tr = nt.nodes.new("ShaderNodeBsdfTransparent")
em = nt.nodes.new("ShaderNodeEmission"); em.inputs[0].default_value = (0.6, 0.65, 0.75, 1); em.inputs[1].default_value = 0.6
mix = nt.nodes.new("ShaderNodeMixShader"); mix.inputs[0].default_value = 0.25
nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs[0])
bpy.context.view_layer.material_override = ghost
red = bc.material("_bone", (1, 0.2, 0.1), emission=(1, 0.25, 0.1), emission_strength=6)
yel = bc.material("_joint", (1, 0.9, 0.1), emission=(1, 0.9, 0.1), emission_strength=6)
col = bc.collection("_bones")
for b in arm.data.bones:
    if b.name == "root":
        continue
    h = arm.matrix_world @ b.head_local; t = arm.matrix_world @ b.tail_local
    d = t - h; L = d.length
    bpy.ops.mesh.primitive_cylinder_add(radius=0.004, depth=L, location=(h + t) / 2)
    c = bpy.context.active_object; c.rotation_euler = d.to_track_quat("Z", "Y").to_euler(); c.data.materials.append(red)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.009, location=h)
    s = bpy.context.active_object; s.data.materials.append(yel)
# material_override hits the bones too: keep them visible by excluding via holdout trick -> render bones in a second view layer is overkill;
# instead override only the body objects
bpy.context.view_layer.material_override = None
for o in bpy.data.objects:
    if o.name in ("SOL_Body", "SOL_Gear"):
        o.data.materials.clear() if False else None
        for i in range(len(o.material_slots)):
            o.material_slots[i].link = "OBJECT"; o.material_slots[i].material = ghost
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else sc.render.engine
try:
    sc.render.engine = "CYCLES"
except TypeError:
    pass
bc.setup_studio(); bc.setup_cycles_gpu(sc, 24)
bc.render_views(OUT, "rv_xray", views=["front", "left", (0.0, -0.001, 1)], res=(700, 900), engine="CYCLES", samples=24, lens=85, ortho=True)
