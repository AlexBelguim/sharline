"""Audit the actual character GLBs: geometry, skin weights, bones, UVs and sockets."""
from pathlib import Path
import json
import struct
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'assets/maps/showhome'))
from verify_kit import read_glb,accessor

REQUIRED=['root','pelvis','spine_01','spine_02','spine_03','neck_01','head']
for side in('l','r'):
    REQUIRED += [p+'_'+side for p in ('clavicle','upperarm','lowerarm','hand','thigh','calf','foot','ball')]
    REQUIRED += [f'{finger}_{n:02d}_{side}' for finger in('thumb','index','middle','ring','pinky')for n in(1,2,3)]


def audit(path):
    if not path.exists():return dict(path=str(path),status='pending')
    d,b=read_glb(path);issues=[];triangles=0;weighted=0;max_error=0.;rigid=0
    names={n.get('name','')for n in d.get('nodes',[])}
    bones=set()
    for skin in d.get('skins',[]):
        bones.update(d['nodes'][i].get('name','')for i in skin['joints'])
        if 'inverseBindMatrices' not in skin:issues.append('Missing inverse bind matrices')
    for name in REQUIRED:
        if name not in bones:issues.append('Missing bone '+name)
    for mesh in d.get('meshes',[]):
        for p in mesh['primitives']:
            at=p['attributes'];triangles+=d['accessors'][p['indices']]['count']//3
            for key in('POSITION','NORMAL','TEXCOORD_0'):
                if key not in at:issues.append(mesh.get('name','')+' missing '+key)
            if 'WEIGHTS_1' in at:issues.append('More than four skin influences')
            if 'WEIGHTS_0' in at:
                if 'JOINTS_0' not in at:issues.append('Weights without joints')
                for row in accessor(d,b,at['WEIGHTS_0']):
                    weighted+=1;error=abs(sum(row)-1);max_error=max(max_error,error)
                    if sum(v>1e-5 for v in row)>4:issues.append('Too many weights')
                    if sum(row)<.999-1/255:issues.append('Unweighted skin vertex')
            else:rigid+=1
    if not weighted:issues.append('No skinned vertices')
    if max_error>.004:issues.append('Weights not normalized')
    if triangles>70000:issues.append('Character exceeds 70k triangle hard limit')
    sockets=sorted(n for n in names if '_SOCKET_'in n)
    if not any(n.endswith('_SOCKET_Halo')for n in sockets):issues.append('Halo socket missing')
    for mat in d.get('materials',[]):
        if 'KHR_materials_unlit'in mat.get('extensions',{}):issues.append('Unlit body material: '+mat.get('name',''))
    return dict(path=str(path),status='PASS'if not issues else'REVIEW',triangles=triangles,
                skins=len(d.get('skins',[])),bones=sorted(bones),materials=[m.get('name')for m in d.get('materials',[])],
                weighted_vertices=weighted,rigid_primitives=rigid,max_weight_sum_error=max_error,sockets=sockets,issues=sorted(set(issues)))


def main():
    actors=[audit(HERE/name/'v2'/f'{name}.glb')for name in('kestrel','solace')]
    ready=[a for a in actors if a['status']!='pending']
    # Optional hairstyle bones do not alter the shared body animation contract.
    body_bones=lambda actor:[b for b in actor['bones']if not b.startswith('hair_')]
    shared=not(len(ready)==2)or body_bones(ready[0])==body_bones(ready[1])
    report=dict(actors=actors,compatible_bone_names=shared,frame='metres, Blender Z up facing-Y, glTF Y up')
    (HERE/'v2_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    for a in actors:print(Path(a['path']).name,a['status'],a.get('triangles'),a.get('issues'))
    print('Shared body bone names:',shared)


if __name__=='__main__':main()
