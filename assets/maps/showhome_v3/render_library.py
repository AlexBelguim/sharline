"""Render the actual exported props and container poses; never modify asset exports."""
from pathlib import Path
import sys,json,math
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE));import common as C
def pose(obs,state):
    for o in obs:
        if not o.name.startswith(('OPEN_DOOR_','OPEN_DRAWER_','OPEN_LID_')):continue
        rotation=o.rotation_quaternion.to_euler('XYZ') if o.rotation_mode=='QUATERNION' else o.rotation_euler.copy();o.rotation_mode='XYZ';o.rotation_euler=rotation
        if o.name.startswith('OPEN_DRAWER_'):
            o.location=Vector(o['closed_location']);o.location.y-=0 if state=='closed' else o['ajar'] if state=='ajar' else o['travel_m']
        else:o.rotation_euler['XYZ'.index(o['axis'])]=math.radians(0 if state=='closed' else o['ajar'] if state=='ajar' else o['min_deg'] if o['min_deg']<0 else o['max_deg'])
def main():
    cat=json.loads((ROOT/'assets/props/catalog.json').read_text())['props'];out=HERE/'renders/library';out.mkdir(parents=True,exist_ok=True)
    for r in cat:
        C.bc.reset_scene();bpy.ops.import_scene.gltf(filepath=str(ROOT/'assets'/r['glb']));obs=list(bpy.context.scene.objects);mn,mx=C.bc.world_bounds([o for o in obs if o.type=='MESH']);centre=(mn+mx)/2;s=max(mx-mn)
        cam=C.stage();sc=bpy.context.scene;sc.cycles.samples=8;sc.render.resolution_x=360;sc.render.resolution_y=360
        states=('closed','ajar','open') if r['category']=='containers' else ('default',)
        for state in states:
            if state!='default':pose(obs,state)
            C.render(cam,out/(r['id']+'_'+state+'.png'),centre+Vector((s*1.6,-s*2,s*1.2)),centre,s*1.8)
        print('PREVIEW_READY',r['id'],flush=True)
if __name__=='__main__':main()
