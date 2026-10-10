"""Isolated hair geometry / binding review; never writes character exports."""
from pathlib import Path
import sys,json,math
import bpy,bmesh
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[3]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'assets/characters/_shared'),str(OUT)]
import blender_common as bc
import kestrel_hair

prefix=next((v.split('=',1)[1]for v in sys.argv if v.startswith('--prefix=')),'hair_polish_01')
bpy.ops.wm.open_mainfile(filepath=str(OUT/'kestrel.blend'))
scene=bpy.context.scene;scene.frame_set(1)
arm=next(o for o in scene.objects if o.type=='ARMATURE'and o.name.startswith('KES_'))
arm.animation_data_clear()
for bone in arm.pose.bones:
    bone.rotation_mode='QUATERNION';bone.rotation_quaternion=(1,0,0,0)
    bone.location=(0,0,0);bone.scale=(1,1,1)
for ob in list(scene.objects):
    if ob.name.startswith('KES_Hair'):bpy.data.objects.remove(ob,do_unlink=True)
    elif ob.type=='MESH'and not ob.name.startswith('KES_'):ob.hide_render=True
parts=kestrel_hair.build({'armature':arm,'scale':1.})
report={'parts':{},'bones':len(arm.data.bones),'hair_bones':[b.name for b in arm.data.bones if b.name.startswith('hair_')]}
for ob in parts:
    ob.data.calc_loop_triangles();bm=bmesh.new();bm.from_mesh(ob.data)
    entry={'verts':len(ob.data.vertices),'triangles':len(ob.data.loop_triangles),'boundary_edges':sum(e.is_boundary for e in bm.edges),'weights_max':max(len(v.groups)for v in ob.data.vertices),'normalization_error':max(abs(1-sum(g.weight for g in v.groups))for v in ob.data.vertices)}
    bm.free();report['parts'][ob.name]=entry
report['hair_triangles']=sum(r['triangles']for r in report['parts'].values())
def positions():
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();result={}
    for ob in parts:
        ev=ob.evaluated_get(dg);me=ev.to_mesh()
        result[ob.name]=[(ev.matrix_world@v.co).copy()for v in me.vertices];ev.to_mesh_clear()
    return result
rest=positions()
for name in report['hair_bones']:
    p=arm.pose.bones[name];p.rotation_mode='XYZ';p.rotation_euler.y=math.radians(5 if name.endswith('02')else 2)
moved=positions();root=0.;tip=0.;fixed=0.
for ob in parts:
    head=ob.vertex_groups.find('head')
    for v,a,b in zip(ob.data.vertices,rest[ob.name],moved[ob.name]):
        d=(a-b).length;tip=max(tip,d)
        if 'Scalp'in ob.name:fixed=max(fixed,d)
        if any(g.group==head and g.weight>.9999 for g in v.groups):root=max(root,d)
report['motion']={'scalp_error_m':fixed,'root_error_m':root,'tip_displacement_m':tip}
assert len(parts)==9 and len(report['hair_bones'])==6
assert root<1e-5 and fixed<1e-5 and tip>.001
assert all(v['weights_max']<=3 and v['normalization_error']<1e-5 for v in report['parts'].values())
for bone in arm.pose.bones:
    bone.rotation_mode='QUATERNION';bone.rotation_quaternion=(1,0,0,0)
(OUT/(prefix+'_qa.json')).write_text(json.dumps(report,indent=2)+'\n')
bc.setup_studio(bg=(.16,.165,.18),strength=.72,floor=False)
bc.VIEW_DIRS.update(front=(0,-1,.025),three_quarter=(.56,-1,.09),right=(1,0,.04),left=(-1,0,.04),back=(0,1,.04))
paths=bc.render_views(str(OUT/'renders'),prefix,views=('front','three_quarter','right','left','back'),res=(900,900),engine='CYCLES',samples=32,ortho=True,focus=((0,0,1.593),.177),margin=1.12)
bc.contact_sheet(paths,str(OUT/'renders'/(prefix+'_sheet.png')),cols=3)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/(prefix+'.blend')))
print('HAIR_POLISH_QA',json.dumps(report),flush=True)
