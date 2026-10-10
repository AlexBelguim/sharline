"""Fresh import checks for the GLB/FBX exports, plus a round-trip PBR render."""
from pathlib import Path
import bpy,bmesh,numpy as np,json,sys,struct
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT));sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
from build_armchair import measure

def imported_check(fmt):
    bc.reset_scene()
    if fmt=='glb':bpy.ops.import_scene.gltf(filepath=str(OUT/'armchair.glb'),merge_vertices=True)
    else:bpy.ops.import_scene.fbx(filepath=str(OUT/'armchair.fbx'))
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
    for o in objects:
        world=o.matrix_world.copy();o.parent=None;o.matrix_world=world
        # Check position topology after intentional glTF vertex splits.
        bm=bmesh.new();bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000002)
        bm.to_mesh(o.data);bm.free();o.data.update()
    report=measure(objects)
    report['all_named']=all(o.name.startswith('ACH_')for o in objects)
    report['materials']=sorted({m.name for o in objects for m in o.data.materials})
    report['all_uvs']=all(o.data.uv_layers for o in objects)
    report['minimum_z_m']=report['bounds'][0][2]
    report['closed_manifold']=all(row['boundary_edges']==0 and row['nonmanifold_edges']==0 for row in report['objects'])
    report['identity_transforms']=all(row['identity_transform']for row in report['objects'])
    report['passes']=report['triangles']<=5000 and report['all_uvs'] and report['all_named'] and report['closed_manifold'] and report['identity_transforms'] and abs(report['minimum_z_m'])<.00001 and abs(report['dimensions_m'][2]-.95)<.0001
    if fmt=='glb':
        bc.setup_studio(bg=(.18,.185,.20),strength=.70,floor=True)
        bc.render_views(str(OUT/'renders'),'armchair_roundtrip',objects,views=('three_quarter',),res=(1000,1000),engine='CYCLES',samples=32,
                        ortho=True,focus=((0,0,.475),.54),margin=1.15)
    return report

def main():
    result={fmt:imported_check(fmt)for fmt in ['glb','fbx']}
    raw=(OUT/'armchair.glb').read_bytes();length,kind=struct.unpack_from('<II',raw,12)
    gltf=json.loads(raw[20:20+length]);materials=[]
    for m in gltf.get('materials',[]):
        p=m.get('pbrMetallicRoughness',{})
        materials.append({'name':m['name'],'basecolor_texture':'baseColorTexture'in p,
                          'ORM_texture':'metallicRoughnessTexture'in p,'normal_texture':'normalTexture'in m,
                          'metallicFactor':p.get('metallicFactor',1),'extensions':list(m.get('extensions',{}))})
    result['gltf_materials']=materials
    result['GLB_geometry_triangles']=sum(gltf['accessors'][p['indices']]['count']//3 for m in gltf['meshes']for p in m['primitives'])
    result['all_pbr_maps_embedded']=all('bufferView'in image for image in gltf.get('images',[]))
    result['export_axes']='GLB Y-up; FBX -Z forward / Y-up; imported back to Blender Z-up'
    (OUT/'armchair_import_qa.json').write_text(json.dumps(result,indent=2)+'\n')
    print('ARMCHAIR_IMPORT_QA',json.dumps(result),flush=True)
    if not all(result[f]['passes']for f in ['glb','fbx']):raise RuntimeError('Export QA failed')

if __name__=='__main__':main()
