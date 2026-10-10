"""Normal-only refinement of the existing kit; positions, UVs and COLL stay fixed."""
import sys,json,math,hashlib,shutil
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import common as C
from gltf_shared import externalize

ratio=(.009/.020)/math.tan(math.radians(55))
backup=HERE/'_cache'/'before_printed_normal_refinement';backup.mkdir(parents=True,exist_ok=True)
records=[]
for path in (HERE/'kit/houses.glb',HERE/'kit/houses.blend',HERE/'showhome_v3.blend'):
    target=backup/(path.name+'.bak')
    if not target.exists():shutil.copy2(path,target)

for path in (HERE/'kit/houses.blend',HERE/'showhome_v3.blend'):
    bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False,use_scripts=False)
    modified=0;meshes=[]
    for ob in bpy.context.scene.objects:
        if ob.type!='MESH' or ob.name.startswith('COL_'):continue
        mesh=ob.data
        painted={i for i,m in enumerate(mesh.materials) if m and m.name.split('.')[0]=='M_SH_PrintedConcrete'}
        if not painted:continue
        before=[tuple(n.vector) for n in mesh.corner_normals];normals=list(before);count=0
        for face in mesh.polygons:
            if face.material_index not in painted:continue
            for li in face.loop_indices:
                v=Vector(normals[li])
                if .025<abs(v.z)<.9:
                    v.z*=ratio;v.normalize();normals[li]=tuple(v);count+=1
        if count:
            mesh.normals_split_custom_set(normals);mesh.update();modified+=count;meshes.append(ob.name)
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    if path.name=='houses.blend':
        roots=[o for o in bpy.context.scene.objects if o.type=='EMPTY' and o.parent is None and o.name.startswith('SH3_')]
        C.export_glb(HERE/'kit/houses.glb',roots+C.visuals())
        externalize(HERE/'kit/houses.glb',HERE/'textures')
    records.append(dict(file=str(path.relative_to(HERE)),corners=modified,meshes=meshes))
out=dict(old_tilt_deg=55,new_max_tilt_deg=math.degrees(math.atan(.009/.020)),groove_depth_m=.009,half_course_pitch_m=.020,positions_uv_collision_unchanged=True,records=records)
C.write(HERE/'printed_normal_refinement.json',out)
print('PRINTED_NORMAL_REFINED',json.dumps(out),flush=True)
