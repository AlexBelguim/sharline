"""Inspect the exported hair skin and demonstrate a small cosmetic tip pose."""
from pathlib import Path
import sys,json,math
import bpy
from mathutils import Matrix,Vector
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
bc.reset_scene();bpy.ops.import_scene.gltf(filepath=str(OUT/'kestrel.glb'))
arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
hair=[o for o in bpy.context.scene.objects if o.type=='MESH'and o.get('skin_slot')=='hair']
parts=[o for o in bpy.context.scene.objects if o.type=='MESH'and o.name.startswith('KES_')]
assert len(hair)==9,('Expected fixed scalp + eight solid locks',len(hair))
cosmetic=[b.name for b in arm.data.bones if b.name.startswith('hair_')]
assert len(cosmetic)==6,cosmetic
def positions():
 bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();result={}
 for ob in hair:
  ev=ob.evaluated_get(dg);me=ev.to_mesh()
  result[ob.name]=[(ev.matrix_world@v.co).copy()for v in me.vertices];ev.to_mesh_clear()
 return result
rest=positions()
for name in cosmetic:
 assert arm.data.bones[name].parent.name=='head'or arm.data.bones[name].parent.name.startswith('hair_')
 p=arm.pose.bones[name];p.rotation_mode='XYZ'
 p.rotation_euler.y=math.radians(5 if name.endswith('02')else 2)
moved=positions();fixed=0.;tip=0.;root=0.;rootcount=0
for ob in hair:
 head=ob.vertex_groups.find('head')
 for v,a,b in zip(ob.data.vertices,rest[ob.name],moved[ob.name]):
  distance=(a-b).length
  if 'Scalp'in ob.name:fixed=max(fixed,distance)
  if any(g.group==head and g.weight>.9999 for g in v.groups):root=max(root,distance);rootcount+=1
  tip=max(tip,distance)
assert fixed<1e-5 and root<1e-5,('Roots or scalp moved',fixed,root)
assert tip>.001,('Hair tips did not deform',tip)
report={'fixed_scalp_error_m':fixed,'fixed_root_error_m':root,'fixed_root_vertices':rootcount,
        'max_tip_displacement_m':tip,'cosmetic_bones':cosmetic,'hair_meshes':len(hair),
        'status':'PASS','game_motion_implemented':False,'pose':'2 deg root / 5 deg tip demonstration'}
(OUT/'hair_motion_qa.json').write_text(json.dumps(report,indent=2)+'\n')
for ob in bpy.context.scene.objects:
 if ob.type=='MESH'and ob not in parts:ob.hide_render=True
bc.setup_studio(bg=(.18,.185,.20),strength=.70,floor=True);bpy.data.objects['_Floor'].scale=(4,4,4)
try:bpy.context.scene.view_settings.look='AgX - Medium High Contrast'
except Exception:pass
bc.VIEW_DIRS['three_quarter']=(.60,-1,.07)
bc.render_views(str(OUT/'renders'),'hair_tip_pose',parts,views=('three_quarter',),res=(1000,1000),engine='CYCLES',samples=48,ortho=False,focus=((0,-.015,1.585),.20),margin=1.1,lens=85)
print('HAIR_MOTION_VALID',json.dumps(report),flush=True)
