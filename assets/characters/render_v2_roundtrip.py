"""Render the serialized skins in a fresh Blender scene, including a shared-scale lineup."""
from pathlib import Path
import json
import sys
import bpy
from mathutils import Vector

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc


def imported(name):
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(HERE/name/'v2'/f'{name}.glb'))
    objects=list(set(bpy.data.objects)-before)
    mesh=[o for o in objects if o.type=='MESH']
    dg=bpy.context.evaluated_depsgraph_get()
    points=[]
    for ob in mesh:
        evaluated=ob.evaluated_get(dg);data=evaluated.to_mesh()
        points.extend(evaluated.matrix_world@v.co for v in data.vertices)
        evaluated.to_mesh_clear()
    mn=[min(v[i]for v in points)for i in range(3)]
    mx=[max(v[i]for v in points)for i in range(3)]
    return objects,dict(min=mn,max=mx,mesh_objects=len(mesh),armatures=sum(o.type=='ARMATURE'for o in objects))


def camera(path,loc,target,res=(1440,1200),ortho=2.25):
    cam=bpy.data.objects.new('_LineupCamera',bpy.data.cameras.new('_LineupCamera'))
    bpy.context.scene.collection.objects.link(cam)
    cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type='ORTHO';cam.data.ortho_scale=ortho
    sc=bpy.context.scene;sc.camera=cam
    sc.render.resolution_x,sc.render.resolution_y=res;sc.render.resolution_percentage=100
    sc.render.filepath=str(path);bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam,do_unlink=True)


def main():
    out=HERE/'v2_renders';out.mkdir(exist_ok=True)
    facts={}
    for name in('kestrel','solace'):
        bc.reset_scene();obs,facts[name]=imported(name)
        bc.setup_studio(floor=True)
        bc.render_views(str(out),name+'_roundtrip',obs,views=('front','right','three_quarter','back'),
                        res=(900,1200),samples=32)
    bc.reset_scene()
    for name,offset in(('kestrel',-.85),('solace',.85)):
        obs,_=imported(name)
        roots=[o for o in obs if not o.parent or o.parent not in obs]
        for ob in roots:ob.location.x+=offset
    bc.setup_studio(floor=True)
    sc=bpy.context.scene
    sc.render.engine='CYCLES';sc.cycles.samples=32;sc.cycles.use_denoising=True
    camera(out/'lineup_front.png',(0,-4,1.08),(0,0,1.00),res=(1600,1000),ortho=3.55)
    camera(out/'lineup_three_quarter.png',(2,-4,1.65),(0,0,1.0),res=(1600,1000),ortho=3.7)
    (HERE/'v2_roundtrip.json').write_text(json.dumps(facts,indent=2)+'\n',encoding='utf8')
    print('ROUNDTRIP',facts)


if __name__=='__main__':main()
