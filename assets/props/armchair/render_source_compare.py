"""Render the supplied full source under the same camera/light as the finish."""
from pathlib import Path
import bpy,sys
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'));import blender_common as bc
SOURCE='C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI/output/valetf_b_armchair_full_00001_.glb'
bc.reset_scene();bpy.ops.import_scene.gltf(filepath=SOURCE,merge_vertices=True)
objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
for ob in objects:
    m=ob.matrix_world.copy();ob.parent=None;ob.matrix_world=m
    bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
lo,hi=bc.world_bounds(objects);center=(lo+hi)*.5;scale=.95/(hi.z-lo.z)
for ob in objects:
    for v in ob.data.vertices:v.co=Vector(((v.co.x-center.x)*scale,(v.co.y-center.y)*scale,(v.co.z-lo.z)*scale))
    ob.data.update()
bc.setup_studio(bg=(.18,.185,.20),strength=.70,floor=True)
bc.render_views(str(OUT/'renders'),'armchair_source_before',objects,views=('three_quarter',),res=(1000,1000),engine='CYCLES',samples=32,
                ortho=True,focus=((0,0,.475),.54),margin=1.15)
