"""Finish the supplied TRELLIS chair with selective smoothing and quiet painted PBR.

Run Blender 5.2 -b --factory-startup --disable-autoexec -P build_armchair.py.
The tested 4.5k-triangle rebake of the supplied source is the reproducible input.
This script does not run additional collapse decimation.
"""
from pathlib import Path
import bpy,bmesh,numpy as np,sys,json,math,time,subprocess,os,hashlib
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
SOURCE=Path('C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI/output/valetf_b_armchair_full_00001_.glb')
CACHE=OUT/'input/armchair_clean_input.glb'
PYTHON=os.environ.get('VALETF_PYTHON','C:/Users/alexw/miniconda3/python.exe')

def select(ob):
    bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob

def image_node(nt,path,linear=False):
    n=nt.nodes.new('ShaderNodeTexImage');n.image=bpy.data.images.load(str(path),check_existing=True)
    n.image.colorspace_settings.name='Non-Color' if linear else 'sRGB';return n

def pbr_material(name,prefix,normal=False):
    m=bc.material(name,(1,1,1),.76);nt=m.node_tree;p=bc._principled(m)
    al=image_node(nt,OUT/'textures'/f'{prefix}_albedo.png');nt.links.new(al.outputs['Color'],p.inputs['Base Color'])
    orm=image_node(nt,OUT/'textures'/f'{prefix}_orm.png',True)
    separate=nt.nodes.new('ShaderNodeSeparateColor');separate.mode='RGB'
    nt.links.new(orm.outputs['Color'],separate.inputs['Color'])
    nt.links.new(separate.outputs['Green'],p.inputs['Roughness']);nt.links.new(separate.outputs['Blue'],p.inputs['Metallic'])
    if normal:
        tex=image_node(nt,OUT/'textures'/f'{prefix}_normal.png',True)
        nm=nt.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=1
        nt.links.new(tex.outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],p.inputs['Normal'])
    m['PBR']='albedo sRGB; OpenGL tangent normal; linear ORM';return m

def smooth_surface(ob):
    """Taubin diffusion with region weights; protect scroll faces and perimeter seams.

    Eleven passes suppress random local undulations without triangle collapse.
    Opposite signed passes retain broad volume; the final cap is 12mm.
    """
    me=ob.data;p=np.array([v.co[:] for v in me.vertices],dtype=np.float64);original=p.copy()
    edges=np.array([e.vertices[:] for e in me.edges],dtype=np.int64)
    i=np.r_[edges[:,0],edges[:,1]];j=np.r_[edges[:,1],edges[:,0]]
    n=len(p);degree=np.bincount(i,minlength=n)
    x=np.abs(p[:,0]);y=p[:,1];z=p[:,2]
    weight=np.full(n,.42)
    # Back centre and broad side/front apron surfaces receive stronger cleanup.
    weight[(z>.56)&(x<.26)]=.95
    weight[(z>.16)&(z<.35)]=.85
    weight[(x>.32)&(z>.41)&(y>-.23)]=.75
    # Existing seat channel edge and back perimeter keep their defined shapes.
    weight[(z>.35)&(z<.43)&(x<.30)]=.28
    weight[(z>.57)&(x>.275)]=.23
    # Front roll/spiral geometry is a key silhouette landmark, so keep it stable.
    weight[(x>.30)&(y<-.245)]=.32
    weight[z<.145]=0
    for _ in range(11):
        for amount in [.46,-.48]:
            mean=np.empty_like(p)
            for c in range(3):mean[:,c]=np.bincount(i,weights=p[j,c],minlength=n)/np.maximum(degree,1)
            p+=(mean-p)*(weight*amount)[:,None]
            delta=p-original;length=np.linalg.norm(delta,axis=1)
            p=original+delta*np.minimum(1,.009/np.maximum(length,1e-9))[:,None]
    for v,co in zip(me.vertices,p):v.co=co
    me.update()
    # Low-order front/rear cushion fits clean the large upholstered planes.
    # Only depth is changed; border seams and the whole silhouette are pinned.
    normals=np.array([v.normal[:]for v in me.vertices]);fit_count=0
    for side in [-1,1]:
        mask=(p[:,2]>.55)&(p[:,2]<.955)&(np.abs(p[:,0])<.255)&(normals[:,1]*side>.65)
        indices=np.where(mask)[0]
        if len(indices)<18:continue
        q=p[indices];xx=q[:,0];zz=q[:,2]-.75
        A=np.column_stack([np.ones(len(q)),xx,zz,xx*xx,xx*zz,zz*zz,xx*xx*zz,xx*zz*zz,zz**3])
        keep=np.ones(len(q),dtype=bool)
        for _ in range(3):
            fit=np.linalg.lstsq(A[keep],q[keep,1],rcond=None)[0]
            error=np.abs(A@fit-q[:,1]);keep=error<max(.004,np.percentile(error,90))
        rim=np.clip((.255-np.abs(xx))/.065,0,1)
        bottom=np.clip((q[:,2]-.55)/.10,0,1);top=np.clip((.955-q[:,2])/.05,0,1)
        mix=rim*bottom*top*.78
        p[indices,1]+=np.clip(A@fit-q[:,1],-.012,.012)*mix
        fit_count+=int((mix>.25).sum())
    delta=p-original;length=np.linalg.norm(delta,axis=1)
    p=original+delta*np.minimum(1,.012/np.maximum(length,1e-9))[:,None]
    for v,co in zip(me.vertices,p):v.co=co
    me.update();distance=np.linalg.norm(p-original,axis=1)
    return {'method':'weighted nonshrinking Taubin surface diffusion; no further decimation',
            'pairs':11,'broad_cushion_fit_vertices':fit_count,
            'maximum_m':float(distance.max()),'mean_m':float(distance.mean()),
            'protected':'scroll fronts, cushion channel edges, back perimeter seam, leg joints'}

def remove_old_feet(ob):
    bm=bmesh.new();bm.from_mesh(ob.data)
    bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),dist=.000001,
                          plane_co=(0,0,.108),plane_no=(0,0,1),clear_inner=True,clear_outer=False)
    boundary=[e for e in bm.edges if e.is_boundary]
    if boundary:bmesh.ops.holes_fill(bm,edges=boundary,sides=0)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free();ob.data.update()

def timber_leg(name,x,y,mat):
    # Four evenly placed tapered legs, capped and beveled with only 2 segments.
    top=.140;bottom=0;wt=.048;wb=.030
    vertices=[]
    for z,w in [(bottom,wb),(top,wt)]:
        for u,v in [(-1,-1),(1,-1),(1,1),(-1,1)]:vertices.append((x+u*w*.5,y+v*w*.5,z))
    faces=[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    me=bpy.data.meshes.new(name+'_Mesh');me.from_pydata(vertices,[],faces);me.update()
    ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob);me.materials.append(mat)
    select(ob);bevel=ob.modifiers.new('Soft timber edges','BEVEL');bevel.width=.0025;bevel.segments=2
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    bc.smart_uv(ob);bc.shade_smooth(ob,40)
    return ob

def measure(objects):
    rows=[]
    for ob in objects:
        me=ob.data;me.calc_loop_triangles();bm=bmesh.new();bm.from_mesh(me)
        rows.append({'object':ob.name,'triangles':len(me.loop_triangles),'vertices':len(me.vertices),
                     'boundary_edges':sum(e.is_boundary for e in bm.edges),
                     'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),
                     'UVs':bool(me.uv_layers),'identity_transform':all(abs(v)<1e-6 for v in ob.location) and
                        all(abs(v)<1e-6 for v in ob.rotation_euler) and all(abs(v-1)<1e-6 for v in ob.scale)})
        bm.free()
    lo,hi=bc.world_bounds(objects)
    return {'triangles':sum(row['triangles']for row in rows),'objects':rows,'dimensions_m':list(hi-lo),'bounds':[list(lo),list(hi)]}

def render(objects):
    bc.setup_studio(bg=(.18,.185,.20),strength=.70,floor=True)
    views=('front','three_quarter','right','back','three_quarter_back')
    paths=bc.render_views(str(OUT/'renders'),'armchair',objects,views=views,res=(1000,1000),engine='CYCLES',samples=40,
                         ortho=True,focus=((0,0,.475),.54),margin=1.15)
    bc.contact_sheet([paths[i]for i in [0,1,2,3]],str(OUT/'renders/contact_sheet.png'),cols=2)
    clay=bc.material('_QA_Clay',(.36,.36,.36),.72);saved=[list(o.data.materials)for o in objects]
    for o in objects:
        o.data.materials.clear();o.data.materials.append(clay)
    bc.render_views(str(OUT/'renders'),'armchair_clay',objects,views=('three_quarter','back'),res=(1000,1000),engine='CYCLES',samples=32,
                    ortho=True,focus=((0,0,.475),.54),margin=1.15)
    for o,mats in zip(objects,saved):
        o.data.materials.clear()
        for m in mats:o.data.materials.append(m)

def main():
    start=time.time();OUT.mkdir(parents=True,exist_ok=True);(OUT/'renders').mkdir(exist_ok=True)
    if not CACHE.exists():
        subprocess.run([bpy.app.binary_path,'-b','--factory-startup','--disable-autoexec','-P',str(OUT/'prepare_clean_input.py')],check=True)
    subprocess.run([PYTHON,str(OUT/'paint_atlas.py')],check=True)
    bc.reset_scene();bpy.context.preferences.filepaths.save_version=0
    bpy.ops.import_scene.gltf(filepath=str(CACHE),merge_vertices=True)
    ob=next(o for o in bpy.context.scene.objects if o.type=='MESH')
    for o in list(bpy.context.scene.objects):
        if o is not ob:bpy.data.objects.remove(o,do_unlink=True)
    world=ob.matrix_world.copy();ob.parent=None;ob.matrix_world=world
    select(ob);bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    # glTF duplicates vertices at UV/normal seams. Weld POSITION topology while
    # retaining distinct per-loop UVs so diffusion cannot open those seams.
    bm=bmesh.new();bm.from_mesh(ob.data);initial_vertices=len(bm.verts)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.000002)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bm.to_mesh(ob.data);bm.free();ob.data.update()
    ob.name='ACH_Upholstery';before=measure([ob]);before['UV_split_vertices_welded']=initial_vertices-len(ob.data.vertices)
    cleanup=smooth_surface(ob);remove_old_feet(ob)
    upholstery=pbr_material('M_Armchair_Terracotta','armchair',True)
    upholstery['detail_source']='art/textures/fabric_soft.png; subdued supplied painted atlas/normal'
    ob.data.materials.clear();ob.data.materials.append(upholstery)
    for face in ob.data.polygons:face.material_index=0;face.use_smooth=True
    # Source custom split normals carry generated faceting. Recompute from cleaned geometry.
    select(ob)
    try:bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except Exception:pass
    wood=pbr_material('M_Armchair_DarkTimber','timber')
    wood['detail_source']='art/textures/worn_paint.png at low contrast'
    objects=[ob]
    for x,label in [(-.250,'L'),(.250,'R')]:
        for y,end in [(-.265,'Front'),(.150,'Rear')]:objects.append(timber_leg('ACH_Leg_'+label+'_'+end,x,y,wood))
    # Normalize to 0.95m tall, centered horizontally with identity object transforms.
    lo,hi=bc.world_bounds(objects);scale=.95/(hi.z-lo.z);center=(lo+hi)*.5
    for o in objects:
        for v in o.data.vertices:v.co=Vector(((v.co.x-center.x)*scale,(v.co.y-center.y)*scale,(v.co.z-lo.z)*scale))
        o.data.update();o['asset']='SHARD/LINE armchair';o['frame']='metres, base-center origin, Z up/front -Y'
    bc.uv_all(objects);bpy.data.orphans_purge(do_recursive=True)
    result={'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'clean_input_sha256':hashlib.sha256(CACHE.read_bytes()).hexdigest(),
            'clean_mesh_cache':str(CACHE),'before':before,'finished':measure(objects),
            'surface_cleanup':cleanup,'source_triangles':699034,'budget_target_triangles':[3000,5000],
            'materials':[upholstery.name,wood.name],'maps':'sRGB albedo, OpenGL tangent normal, linear ORM',
            'UV_layout':'isolated source rebake retained for upholstery; smart unwrap for rebuilt timber feet',
            'outputs':['armchair.blend','armchair.glb','armchair.fbx'],'game_code_changed':False,
            'known_limits':['Single generated upholstery shell retains a few irregular seam junctions.',
                            'Scroll faces retain source asymmetry; those defining folds were deliberately protected.',
                            'Budget topology has uneven triangle size and is suitable for a static environmental prop.']}
    bc.export_all(str(OUT/'armchair'),objects)
    (OUT/'armchair_qa.json').write_text(json.dumps(result,indent=2)+'\n')
    render(objects)
    print('ARMCHAIR_DONE',json.dumps(result),round(time.time()-start,1),flush=True)

if __name__=='__main__':main()
