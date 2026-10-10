"""Independent Blender import check for both final character interchange files."""
from pathlib import Path
import json
import sys
import bpy

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc

results=[]
for ext in ('glb','fbx'):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    file=OUT/('kestrel.'+ext)
    if ext=='glb':bpy.ops.import_scene.gltf(filepath=str(file))
    else:bpy.ops.import_scene.fbx(filepath=str(file))
    armatures=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
    # The glTF importer makes an unweighted Icosphere for bone display. It is
    # an editor helper, not a mesh in the interchange asset.
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('KES_')]
    assert len(armatures)==1, 'Expected exactly one shared rig'
    arm=armatures[0]
    required={'root','pelvis','head','upperarm_l','lowerarm_l','hand_l','thigh_l','calf_l','foot_l','upperarm_r','hand_r'}
    assert required.issubset(arm.data.bones.keys()), 'Missing UE5 mannequin names'
    errors=[];maxinf=0;tris=0
    for ob in meshes:
        if not ob.data.uv_layers:errors.append(ob.name+': missing UV')
        tris+=sum(len(p.vertices)-2 for p in ob.data.polygons)
        for v in ob.data.vertices:
            weights=[g.weight for g in v.groups if g.weight>1e-6]
            maxinf=max(maxinf,len(weights))
            if not weights or len(weights)>4 or abs(sum(weights)-1)>1e-4:
                errors.append(ob.name+': invalid imported skin weights');break
    sockets=[o.name for o in bpy.context.scene.objects if '_SOCKET_' in o.name]
    assert 'KES_SOCKET_Halo' in sockets,'Missing Halo socket'
    lo,hi=bc.world_bounds(meshes)
    # Blender import converts glTF Y-up and FBX transforms back to Z-up.
    if abs(lo.z)>.001 or not 1.70<hi.z<1.77:errors.append('Incorrect metre scale or sole height')
    assert not errors,errors
    results.append({'format':ext,'bytes':file.stat().st_size,'rigs':1,'bones':len(arm.data.bones),'meshes':len(meshes),'tris':tris,'uv_all':True,'max_influences':maxinf,'min':list(lo),'max':list(hi),'sockets':sockets,'errors':errors})
    print('IMPORTED_EXPORT_VALID',ext,len(meshes),tris,maxinf,flush=True)
(OUT/'export_import_qa.json').write_text(json.dumps(results,indent=2))
