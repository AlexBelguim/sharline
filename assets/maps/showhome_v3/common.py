"""Shared v3 authoring contract. Blender metres/Z-up; serialized collision is design frame."""
import math,json,sys
from pathlib import Path
import bpy,bmesh
from mathutils import Vector,Matrix
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
PHYS={'glass','wood_thin','wood_thick','sheet_metal','metal_heavy','drywall','concrete','brick','cladding','foliage_thin','foliage_dense','fabric','plastic','soil','grass','gravel','sand','asphalt','paving','water'}
V2=ROOT/'assets/maps/showhome/textures/v2'
TEXTURE_MANIFEST=json.loads((V2/'manifest.json').read_text(encoding='utf8'))['materials']
def plain(v):
    if isinstance(v,(str,int,float,bool)) or v is None:return v
    if hasattr(v,'items'):return {str(k):plain(x) for k,x in v.items()}
    return [plain(x) for x in v]

def write(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(plain(data),indent=2)+'\n',encoding='utf8')
def empty(name,loc=(0,0,0),parent=None):
    ob=bpy.data.objects.new(name,None);bpy.context.scene.collection.objects.link(ob);ob.matrix_basis=Matrix.Translation(Vector(loc))
    if parent:ob.parent=parent
    bpy.context.view_layer.update()
    return ob
def parent_keep(ob,parent):
    mw=ob.matrix_world.copy();ob.parent=parent;ob.matrix_parent_inverse=parent.matrix_world.inverted();ob.matrix_basis=mw
def uv(ob,repeat=1):
    me=ob.data
    if me.uv_layers:return
    layer=me.uv_layers.new(name='UVMap')
    for face in me.polygons:
        axis=max(range(3),key=lambda k:abs(face.normal[k]));axes=[k for k in range(3) if k!=axis]
        for li in face.loop_indices:
            co=me.vertices[me.loops[li].vertex_index].co;layer.data[li].uv=(co[axes[0]]/repeat,co[axes[1]]/repeat)
def apply(ob):
    bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
    for mod in list(ob.modifiers):bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True);uv(ob)
    return ob
def material(name,phys,tex=None,tint=(1,1,1),rough=.75,metal=0,alpha=1):
    m=bc.material('M_V3_'+name,tint,rough,metal,alpha=alpha);m['phys']=phys;m['repeat_m']=TEXTURE_MANIFEST.get(tex,{}).get('repeat_m',1)
    if tex:m['height_range_m']=TEXTURE_MANIFEST.get(tex,{}).get('height_range_m',0)
    if tex:
        nt=m.node_tree;p=nt.nodes.get('Principled BSDF')
        for suffix,space in (('', 'sRGB'),('_normal','Non-Color'),('_orm','Non-Color')):
            path=V2/(tex+suffix+'.png')
            if not path.exists():continue
            ti=nt.nodes.new('ShaderNodeTexImage');ti.image=bpy.data.images.load(str(path),check_existing=True);ti.image.colorspace_settings.name=space
            if suffix=='':
                # Exporter-supported texture factor, not procedural paint.
                mix=nt.nodes.new('ShaderNodeMix');mix.data_type='RGBA';mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1;mix.inputs[7].default_value=(*tint,1);nt.links.new(ti.outputs['Color'],mix.inputs[6]);nt.links.new(mix.outputs[2],p.inputs['Base Color'])
            elif suffix=='_normal':
                nm=nt.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.65;nt.links.new(ti.outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],p.inputs['Normal'])
            else:
                sep=nt.nodes.new('ShaderNodeSeparateColor');nt.links.new(ti.outputs['Color'],sep.inputs['Color']);nt.links.new(sep.outputs['Green'],p.inputs['Roughness']);nt.links.new(sep.outputs['Blue'],p.inputs['Metallic'])
                group=bpy.data.node_groups.get('glTF Material Output')
                if not group:
                    from io_scene_gltf2.blender.com.material_helpers import create_settings_group
                    group=create_settings_group('glTF Material Output')
                gn=nt.nodes.new('ShaderNodeGroup');gn.node_tree=group;nt.links.new(sep.outputs['Red'],gn.inputs['Occlusion'])
        m['height_source']=str(V2/(tex+'_height.png'));m['white_is_high']=True
    return m
def col_mesh(name,vertices,faces,phys,kind='solid',walkable=True,parent=None):
    if phys not in PHYS:raise ValueError(phys)
    coll=bc.collection('COLLISION');me=bpy.data.meshes.new('COL_'+name);me.from_pydata(vertices,[],faces);me.update()
    bm=bmesh.new();bm.from_mesh(me);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(me);bm.free()
    ob=bpy.data.objects.new('COL_'+name,me);coll.objects.link(ob);ob['phys']=phys;ob['kind']=kind;ob['walkable']=walkable;ob.hide_render=True;ob.display_type='WIRE'
    if parent:parent_keep(ob,parent)
    return ob
def col_box(name,lo,hi,phys,kind='solid',walkable=True,parent=None):
    a,b,c=lo;d,e,f=hi
    v=[(a,b,c),(d,b,c),(d,e,c),(a,e,c),(a,b,f),(d,b,f),(d,e,f),(a,e,f)]
    return col_mesh(name,v,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],phys,kind,walkable,parent)
def box(name,size,loc,mat,bevel=.01,parent=None,collision=False,local=False):
    ob=bc.box(name,size,loc=loc,mat=mat,bevel=min(bevel,min(size)*.3),segments=1,smooth=35);apply(ob)
    if mat.get('repeat_m',1)!=1:
        for loop in ob.data.uv_layers[0].data:loop.uv/=mat['repeat_m']
    if parent:
        if local:ob.parent=parent
        else:parent_keep(ob,parent)
    if collision:
        v=[Vector(loc)[i]-size[i]/2 for i in range(3)];w=[Vector(loc)[i]+size[i]/2 for i in range(3)]
        co=col_box(name,v,w,mat['phys'])
        if parent:
            if local:co.parent=parent
            else:parent_keep(co,parent)
        ob['collision']=co.name
    return ob
def mesh(name,verts,faces,mat,parent=None):
    me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update();ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob);bc.assign(ob,mat);uv(ob)
    if parent:parent_keep(ob,parent)
    return ob
def bar(name,a,b,width,mat,parent=None,collision=False):
    a,b=Vector(a),Vector(b);length=(b-a).length
    ob=bc.box(name,(width,width,length),loc=(a+b)/2,mat=mat,bevel=width*.1,segments=1,smooth=35);ob.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();apply(ob)
    if parent:parent_keep(ob,parent)
    if collision:
        # Convex beam, preserving true thickness and orientation.
        rot=(b-a).to_track_quat('Z','Y').to_matrix();cen=(a+b)/2
        verts=[tuple(cen+rot@Vector((x*width/2,y*width/2,z*length/2))) for x,y,z in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        co=col_mesh(name,verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],mat['phys'])
        if parent:parent_keep(co,parent)
        ob['collision']=co.name
    return ob
def collision_rows(objects):
    bpy.context.view_layer.update()
    rows=[]
    for ob in objects:
        if not ob.name.startswith('COL_'):continue
        phys=ob.get('phys');assert phys in PHYS,(ob.name,phys)
        verts=[ob.matrix_world@v.co for v in ob.data.vertices];centre=sum(verts,Vector())/len(verts);planes=[]
        for face in ob.data.polygons:
            ps=[verts[i] for i in face.vertices];n=(ps[1]-ps[0]).cross(ps[2]-ps[0]).normalized()
            if n.dot(sum(ps,Vector())/len(ps)-centre)<0:n=-n
            d=n.dot(ps[0]);p=[*n,d]
            if not any(max(abs(a-b) for a,b in zip(p,q))<1e-6 for q in planes):planes.append(p)
            assert max(n.dot(v)-d for v in verts)<.0002,('non-convex',ob.name)
        spans=[max(Vector(p[:3]).dot(v) for v in verts)-min(Vector(p[:3]).dot(v) for v in verts) for p in planes]
        thickness=min(spans);assert thickness>=.004999,('thin',ob.name,thickness)
        bm=bmesh.new();bm.from_mesh(ob.data);closed=all(e.is_manifold for e in bm.edges);bm.free();assert closed,('open collision',ob.name)
        rows.append(dict(name=ob.name,phys=phys,kind=ob.get('kind','solid'),walkable=ob.get('walkable',True),planes=[[round(v,7) for v in p] for p in planes],aabb={'min':[round(min(v[k] for v in verts),6) for k in range(3)],'max':[round(max(v[k] for v in verts),6) for k in range(3)]},thickness_m=round(thickness,6),vertices=[list(v) for v in verts],parent=ob.parent.name if ob.parent else None))
    return rows
def export_collision(path,objects,frame='design metres east X north Y up Z'):
    rows=collision_rows(objects);write(path,dict(schema=1,frame=frame,plane_convention='inside: dot(normal,point) <= d',volumes=rows));return rows
def visuals():return [o for o in bpy.context.scene.objects if o.type=='MESH' and not o.name.startswith('COL_')]
def audit_visuals(obs):
    for ob in obs:
        assert len(ob.data.uv_layers),(ob.name,'no UV')
        for mat in ob.data.materials:assert mat and mat.get('phys') in PHYS,(ob.name,mat.name if mat else None,'no phys')
def export_glb(path,obs):
    audit_visuals([o for o in obs if o.type=='MESH' and not o.name.startswith('COL_')]);bpy.ops.object.select_all(action='DESELECT')
    for ob in obs:ob.select_set(True)
    bpy.context.view_layer.objects.active=obs[0]
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,export_apply=True,export_yup=True,export_normals=True,export_tangents=True,export_extras=True,export_lights=True,export_image_format='AUTO',export_vertex_color='NAME',export_vertex_color_name='Col',export_all_vertex_colors=False)
def triangles(obs):
    n=0
    for o in obs:
        if o.type=='MESH':o.data.calc_loop_triangles();n+=len(o.data.loop_triangles)
    return n
def stage():
    sc=bpy.context.scene;sc.render.engine='CYCLES';sc.cycles.samples=24;sc.cycles.use_denoising=True
    sc.render.resolution_x=1280;sc.render.resolution_y=800;sc.render.resolution_percentage=100
    sc.world=bpy.data.worlds.new('V3_WarmSky');sc.world.use_nodes=True;bg=sc.world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(.66,.76,.86,1);bg.inputs['Strength'].default_value=.65
    sky=ROOT/'assets/maps/showhome/backdrop/sky/sky_equirect.png'
    if sky.exists():
        nt=sc.world.node_tree;ti=nt.nodes.new('ShaderNodeTexEnvironment');ti.image=bpy.data.images.load(str(sky));nt.links.new(ti.outputs['Color'],bg.inputs['Color'])
    data=bpy.data.lights.new('V3_Sun','SUN');data.energy=2.5;data.angle=math.radians(4);data.color=(1,.84,.66)
    ob=bpy.data.objects.new('V3_Sun',data);sc.collection.objects.link(ob);az=math.radians(188);el=math.radians(54);direction=Vector((math.sin(az)*math.cos(el),math.cos(az)*math.cos(el),math.sin(el)));ob.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler()
    sc.view_settings.view_transform='AgX';sc.view_settings.look='AgX - Medium Low Contrast'
    data=bpy.data.cameras.new('V3_Camera');cam=bpy.data.objects.new('V3_Camera',data);sc.collection.objects.link(cam);sc.camera=cam;data.clip_start=.03;data.clip_end=1600;return cam
def render(cam,path,eye,target,ortho=None):
    cam.location=eye;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO' if ortho else 'PERSP';cam.data.ortho_scale=ortho or 6;cam.data.lens=35
    bpy.context.scene.render.filepath=str(path);Path(path).parent.mkdir(parents=True,exist_ok=True);bpy.ops.render.render(write_still=True)
