"""Independent GLB/FBX round-trip check, run in a fresh background Blender."""
from pathlib import Path
import json
import bpy
from mathutils import Vector

HERE=Path(__file__).resolve().parent
required={'root','pelvis','spine_01','spine_02','spine_03','neck_01','head',
          'upperarm_l','upperarm_r','lowerarm_l','lowerarm_r','hand_l','hand_r',
          'thigh_l','thigh_r','calf_l','calf_r','foot_l','foot_r'}
results={}
for fmt in ['glb','fbx']:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path=str(HERE/('solace.'+fmt))
    if fmt=='glb':bpy.ops.import_scene.gltf(filepath=path)
    else:bpy.ops.import_scene.fbx(filepath=path,use_anim=False)
    # Blender's GLTF importer constructs an Icosphere bone display helper;
    # it is absent from the binary GLB and belongs to no exported character.
    helpers=[o.name for o in bpy.context.scene.objects if o.type=='MESH' and not o.name.startswith('SOL_')]
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('SOL_')]
    arms=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
    count=0;bad=[];missing_uv=[];missing_skin=[];maxinf=0;coords=[]
    for ob in meshes:
        me=ob.data;me.calc_loop_triangles();count+=len(me.loop_triangles)
        if not me.uv_layers:missing_uv.append(ob.name)
        if not any(m.type=='ARMATURE' for m in ob.modifiers):missing_skin.append(ob.name)
        for v in me.vertices:
            w=[g.weight for g in v.groups if g.weight>1e-6]
            maxinf=max(maxinf,len(w))
            if len(w)>4 or abs(sum(w)-1)>.001:bad.append((ob.name,v.index,sum(w),len(w)))
            coords.append(ob.matrix_world@v.co)
    lo=[min(p[k] for p in coords) for k in range(3)];hi=[max(p[k] for p in coords) for k in range(3)]
    bones=set(arms[0].data.bones.keys()) if arms else set()
    def center(name):
        ob=next((o for o in meshes if o.name.startswith(name)),None)
        if not ob:return None
        ps=[ob.matrix_world@Vector(c) for c in ob.bound_box]
        return [sum(p[k] for p in ps)/len(ps) for k in range(3)]
    drone=center('SOL_HealDroneShell');bracer=center('SOL_InjectorVial')
    sockets=[o.name for o in bpy.context.scene.objects if o.type=='EMPTY' and 'SOCKET' in o.name]
    emission=[]
    for m in bpy.data.materials:
        if m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type=='BSDF_PRINCIPLED' and n.inputs.get('Emission Strength') and n.inputs['Emission Strength'].default_value>.001:
                    emission.append(m.name);break
    res={'triangles':count,'mesh_objects':len(meshes),'importer_display_helpers':helpers,'armatures':len(arms),'bone_count':len(bones),
         'missing_required_bones':sorted(required-bones),'missing_uv':missing_uv,'missing_skin':missing_skin,
         'bad_weight_vertices':len(bad),'max_influences':maxinf,'bounds_min':lo,'bounds_max':hi,
         'drone_center':drone,'injector_vial_center':bracer,'sockets':sockets,'emissive_materials':emission,
         'animation_actions':len(bpy.data.actions)}
    res['passed']=len(arms)==1 and len(bones)==61 and not (required-bones) and not missing_uv and not missing_skin and not bad and count<=70000 and drone and drone[0]>0 and bracer and bracer[0]<0 and abs(lo[2])<.004 and 1.68<hi[2]<1.80 and len(emission)==1 and not bpy.data.actions
    results[fmt]=res
(HERE/'import_validation.json').write_text(json.dumps(results,indent=2))
print('SOLACE_IMPORT_QA',json.dumps(results))
if not all(v['passed'] for v in results.values()):raise RuntimeError('Solace independent GLB/FBX import QA failed')
