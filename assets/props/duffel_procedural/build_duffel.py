"""Original procedural duffel, Blender 5.2. No generated/imported geometry.

  blender --disable-autoexec -b --factory-startup -P build_duffel.py
PICK_a_duffel.png is a design reference only. Geometry is authored here.
"""
import bpy, bmesh, json, math, os, struct, sys, time, zlib, shutil
from pathlib import Path
import numpy as np
from mathutils import Vector

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
TEX=HERE/'textures'; RENDERS=HERE/'renders'
for p in (TEX,RENDERS,HERE/'reference'): p.mkdir(parents=True,exist_ok=True)
START=time.time()

def log(*a): print('[DFP]',*a,flush=True)
def write_png(path,a):
    a=np.clip(np.rint(a),0,255).astype(np.uint8);h,w,c=a.shape
    def chunk(t,d): return struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff)
    rows=b''.join(b'\0'+r.tobytes() for r in a)
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows,7))+chunk(b'IEND',b''))
def read_rgb(path):
    im=bpy.data.images.load(str(path),check_existing=False)
    im.colorspace_settings.name='Non-Color'
    w,h=im.size; a=np.array(im.pixels[:],dtype=np.float32).reshape(h,w,4)[::-1,:,:3].copy()
    bpy.data.images.remove(im);return a
def linear(a): return np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
def srgb(a): return np.where(a<=.0031308,a*12.92,1.055*np.maximum(a,0)**(1/2.4)-.055)
def material(key,color,rough,src,normal_src,metal=0,mix=.30):
    original=linear(read_rgb(ROOT/'art/textures'/src))[::2,::2]
    factor=1-mix+mix*original
    rgb=srgb(np.clip(np.array(color)*factor/factor.mean(axis=(0,1)),0,1))
    albedo=TEX/f'DFP_{key}_basecolor.png';orm=TEX/f'DFP_{key}_orm.png';normal=TEX/f'DFP_{key}_normal.png'
    write_png(albedo,rgb*255)
    packed=np.empty_like(rgb);packed[:,:,0]=1
    packed[:,:,1]=np.clip(rough+(original.mean(axis=2)-original.mean())*.055,0,1)
    packed[:,:,2]=metal;write_png(orm,packed*255)
    n=read_rgb(ROOT/'assets/characters/kestrel/v2/textures'/normal_src)[::2,::2]*2-1
    n[:,:,:2]*=.06;n[:,:,2]=np.sqrt(np.maximum(0,1-n[:,:,0]**2-n[:,:,1]**2))
    write_png(normal,(n*.5+.5)*255)
    m=bpy.data.materials.new('M_DFP_'+key);m.use_nodes=True;m.use_backface_culling=True;m.diffuse_color=(*color,1)
    m['roughness_fallback']=rough;m['metallic_fallback']=metal
    nt=m.node_tree;bs=nt.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(1,1,1,1);bs.inputs['Metallic'].default_value=1;bs.inputs['Roughness'].default_value=1
    def image_node(path,space):
        n=nt.nodes.new('ShaderNodeTexImage');n.image=bpy.data.images.load(str(path),check_existing=True);n.image.colorspace_settings.name=space;return n
    a=image_node(albedo,'sRGB');nt.links.new(a.outputs['Color'],bs.inputs['Base Color'])
    p=image_node(orm,'Non-Color');s=nt.nodes.new('ShaderNodeSeparateColor');nt.links.new(p.outputs['Color'],s.inputs['Color'])
    nt.links.new(s.outputs['Green'],bs.inputs['Roughness']);nt.links.new(s.outputs['Blue'],bs.inputs['Metallic'])
    n=image_node(normal,'Non-Color');nm=nt.nodes.new('ShaderNodeNormalMap');nt.links.new(n.outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],bs.inputs['Normal'])
    return m

def mesh(name,vertices,faces,mat,smooth=True):
    me=bpy.data.meshes.new('DFP_'+name);me.from_pydata(vertices,[],faces);me.update()
    bm=bmesh.new();bm.from_mesh(me);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(me);bm.free()
    ob=bpy.data.objects.new('DFP_'+name,me);bpy.context.scene.collection.objects.link(ob);bc.assign(ob,mat)
    for p in me.polygons:p.use_smooth=smooth
    return ob
def select(*obs):
    bpy.ops.object.select_all(action='DESELECT')
    for ob in obs:ob.select_set(True)
    bpy.context.view_layer.objects.active=obs[0]
def finish(ob):
    select(ob)
    for m in list(ob.modifiers):bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return ob
def box(name,size,loc,mat,bevel=.003,segments=2):
    return bc.box('DFP_'+name,size,loc=loc,mat=mat,bevel=min(bevel,min(size)*.44),segments=segments,smooth=40)
def gauss(v,c,s):return math.exp(-((v-c)/s)**2)

# A deliberately flattened bottom, bulging canvas shoulders and restrained broad folds.
# Rings are drawn in YZ; longitudinal changes provide actual silhouette deformation.
N=24
BODY_RINGS=[(-.315,.83),(-.307,.93),(-.28,1),(-.23,1.018),(-.17,1.025),(-.11,1.015),(-.055,1.01),(.005,1.015),(.075,1.02),(.135,1.018),(.195,1),(.245,.995),(.28,.98),(.305,.92),(.315,.82)]
def section(x,scale=1,fold=True):
    out=[]
    for i in range(N):
        a=2*math.pi*i/N;c=math.cos(a);s=math.sin(a)
        y=.152*math.copysign(abs(c)**.77,c)*(1-.14*max(s,0))
        z=.143+.137*math.copysign(abs(s)**.76,s)
        if fold:
            # Three authored compression folds, rather than a noisy displacement field.
            side=abs(c)**3
            wrinkle=(.014*gauss(x,-.12,.065)*gauss(z,.066,.043)
                     -.018*gauss(x,.16,.050)*gauss(z,.105+.32*(x-.16),.030)
                     -.018*gauss(x,-.065,.10)*gauss(z,.178+.30*(x+.065),.024)
                     +.009*gauss(x,.23,.055)*gauss(z,.175,.04))
            y+=math.copysign(wrinkle*side,c)
            z-=.008*gauss(x,-.005,.11)*max(s,0)**4
        y*=scale;z=.141+(z-.141)*scale
        out.append((x,y,z))
    return out
def body():
    rings=BODY_RINGS
    v=[p for x,s in rings for p in section(x,s)];f=[]
    for r in range(len(rings)-1):
        for i in range(N):j=(i+1)%N;f.append((r*N+i,r*N+j,(r+1)*N+j,(r+1)*N+i))
    f.extend([tuple(reversed(range(N))),tuple(range((len(rings)-1)*N,len(rings)*N))])
    ob=mesh('Sculpted_Canvas_Body',v,f,NAVY)
    # Cylinder unwrap: weave direction follows the length and perimeter.
    uv=ob.data.uv_layers.new(name='UVMap').data
    for p in ob.data.polygons:
        ids=[ob.data.loops[k].vertex_index for k in p.loop_indices]
        seam=any(i%N==0 for i in ids) and any(i%N==N-1 for i in ids)
        for li,vi in zip(p.loop_indices,ids):
            r,a=divmod(vi,N)
            if len(ids)==N:
                co=ob.data.vertices[vi].co;uv[li].uv=(.5+co.y/.33,.5+(co.z-.141)/.30)
            else:uv[li].uv=(r/(len(rings)-1),1 if seam and a==0 else a/N)
    return ob
def surface_y(x,z):
    # Sample the actual polygonal loft, including its broad sculpted folds.
    for (x0,s0),(x1,s1) in zip(BODY_RINGS,BODY_RINGS[1:]):
        if x0<=x<=x1:
            t=(x-x0)/(x1-x0);a=section(x0,s0);b=section(x1,s1)
            ring=[(x,p[1]*(1-t)+q[1]*t,p[2]*(1-t)+q[2]*t) for p,q in zip(a,b)]
            ys=[]
            for p,q in zip(ring,ring[1:]+ring[:1]):
                if p[1]>=-1e-8 and q[1]>=-1e-8 and min(p[2],q[2])<=z<=max(p[2],q[2]) and abs(p[2]-q[2])>1e-8:
                    t=(z-p[2])/(q[2]-p[2]);ys.append(p[1]*(1-t)+q[1]*t)
            return max(ys) if ys else .085
    return .085
def end_panel(x,mat):
    # Convex sewn end panel, with two large inward crease facets.
    outer=section(x,.805,False);mid=[]
    for i,(xx,y,z) in enumerate(outer):
        a=2*math.pi*i/N
        xx+=.005+.009*math.sin(a)**2
        y*=.81;z=.141+(z-.141)*.80
        crease=.003*gauss(z,.10,.026)
        xx-=crease*abs(math.cos(a))
        mid.append((xx,y,z))
    back=[(x-.006,y,z) for _,y,z in outer]
    v=outer+mid+[(x+.014,0,.145)]+back;f=[]
    for i in range(N):j=(i+1)%N;f.append((i,j,N+j,N+i));f.append((N+i,N+j,2*N))
    for i in range(N):j=(i+1)%N;f.append((i,2*N+1+i,2*N+1+j,j))
    f.append(tuple(reversed(range(2*N+1,3*N+1))))
    ob=mesh('Teal_End_Panel',v,f,mat);ob.data.polygons[-1].use_smooth=False
    return ob
def tube(name,points,radius,mat,sides=6,closed=False):
    pts=[Vector(p) for p in points];v=[];f=[]
    for i,p in enumerate(pts):
        tangent=(pts[(i+1)%len(pts)]-pts[(i-1)%len(pts)]) if closed else (pts[min(i+1,len(pts)-1)]-pts[max(i-1,0)])
        tangent.normalize();axis=Vector((1,0,0))
        if abs(tangent.dot(axis))>.95:axis=Vector((0,1,0))
        u=tangent.cross(axis).normalized();w=tangent.cross(u).normalized()
        for k in range(sides):v.append(tuple(p+radius*(u*math.cos(k*2*math.pi/sides)+w*math.sin(k*2*math.pi/sides))))
    count=len(pts) if closed else len(pts)-1
    for i in range(count):
        for k in range(sides):j=(k+1)%sides;ni=(i+1)%len(pts);f.append((i*sides+k,i*sides+j,ni*sides+j,ni*sides+k))
    if not closed:f.extend([tuple(reversed(range(sides))),tuple(range((len(pts)-1)*sides,len(pts)*sides))])
    return mesh(name,v,f,mat)
def ribbon(name,points,width,thick,mat,width_axis=(0,1,0),plane_normal=None):
    pts=[Vector(p) for p in points];v=[];f=[]
    # Eight corners form softened webbing edges with only one chamfer facet.
    cross=[(-.5,-.25),(-.45,-.5),(.45,-.5),(.5,-.25),(.5,.25),(.45,.5),(-.45,.5),(-.5,.25)]
    for i,p in enumerate(pts):
        t=(pts[min(i+1,len(pts)-1)]-pts[max(i-1,0)]).normalized()
        if plane_normal is not None:u=Vector(plane_normal).cross(t).normalized()
        else:
            u=Vector(width_axis);u=(u-t*u.dot(t)).normalized()
        n=t.cross(u).normalized()
        for a,b in cross:v.append(tuple(p+u*a*width+n*b*thick))
    for r in range(len(pts)-1):
        for i in range(8):j=(i+1)%8;f.append((r*8+i,r*8+j,(r+1)*8+j,(r+1)*8+i))
    f.extend([tuple(reversed(range(8))),tuple(range((len(pts)-1)*8,len(pts)*8))])
    return mesh(name,v,f,mat)
def bound(obs):
    mn,mx=bc.world_bounds(obs);return {'min':[round(v,6) for v in mn],'max':[round(v,6) for v in mx],'size':[round(v,6) for v in mx-mn]}
def qa(obs):
    rows=[]
    for ob in obs:
        me=ob.data;me.calc_loop_triangles();bm=bmesh.new();bm.from_mesh(me);bmesh.ops.remove_doubles(bm,verts=bm.verts,dist=1e-7)
        row={'name':ob.name,'triangles':len(me.loop_triangles),'vertices':len(me.vertices),'uv_layers':len(me.uv_layers),'boundary_edges':sum(e.is_boundary for e in bm.edges),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),'degenerate_triangles':sum(t.area<1e-12 for t in me.loop_triangles)}
        row['identity_transform']=all(abs(ob.matrix_world[i][j]-(1 if i==j else 0))<1e-6 for i in range(4) for j in range(4));bm.free();rows.append(row)
    return {'triangles':sum(r['triangles'] for r in rows),'mesh_objects':len(rows),'all_uvs':all(r['uv_layers'] for r in rows),'all_identity_transforms':all(r['identity_transform'] for r in rows),'nonmanifold_edges':sum(r['nonmanifold_edges'] for r in rows),'boundary_edges':sum(r['boundary_edges'] for r in rows),'degenerate_triangles':sum(r['degenerate_triangles'] for r in rows),'bounds_blender_z_up_m':bound(obs),'objects':rows}
def glb_summary(path):
    raw=Path(path).read_bytes();size,kind=struct.unpack('<II',raw[12:20]);d=json.loads(raw[20:20+size]);ps=[p for m in d['meshes'] for p in m['primitives']]
    return {'triangles':sum(d['accessors'][p['indices']]['count']//3 for p in ps),'meshes':len(d['meshes']),'materials':len(d.get('materials',[])),'images':len(d.get('images',[])),'all_uv0':all('TEXCOORD_0' in p['attributes'] for p in ps),'extensions_used':d.get('extensionsUsed',[]),'node_transforms':{n.get('name',str(i)):{k:n[k] for k in ('matrix','translation','rotation','scale') if k in n} for i,n in enumerate(d['nodes'])},'pbr_materials':[{'name':m['name'],'basecolor_texture':'baseColorTexture' in m.get('pbrMetallicRoughness',{}),'roughness_metallic_texture':'metallicRoughnessTexture' in m.get('pbrMetallicRoughness',{}),'normal_texture':'normalTexture' in m} for m in d.get('materials',[])]}
def studio():
    bc.setup_studio(bg=(.18,.185,.20),strength=.7,floor=True)
    for ob in bpy.data.objects:
        if ob.type=='LIGHT':
            ob.location*=.4;ob.data.energy*=.16;ob.data.size*=.4
            ob.rotation_euler=(Vector((0,0,.18))-ob.location).to_track_quat('-Z','Y').to_euler()

bc.reset_scene()
NAVY=material('Navy_Canvas',(.023,.047,.09),.73,'fabric_ripstop.png','jacket_normal.png',mix=.28)
TEAL=material('Teal_Canvas',(.008,.33,.32),.71,'fabric_ripstop.png','jacket_normal.png',mix=.40)
BONE=material('Bone_Binding',(.55,.52,.46),.59,'fabric_soft.png','webLight_normal.png',mix=.25)
DARK=material('Graphite_Webbing',(.024,.029,.034),.65,'leather_soft.png','web_normal.png',mix=.38)
body();end_panel(.318,TEAL)
# Bone binding hugs the curved teal seam as a real solid band.
outer1=section(.282,.995,True);outer2=section(.305,.944,True)
inner1=[(x,y*.975,.141+(z-.141)*.975) for x,y,z in outer1]
inner2=[(x,y*.975,.141+(z-.141)*.975) for x,y,z in outer2]
v=outer1+outer2+inner2+inner1;f=[]
for r in range(4):
    for i in range(N):j=(i+1)%N;f.append((r*N+i,r*N+j,((r+1)%4)*N+j,((r+1)%4)*N+i))
mesh('Bone_End_Binding',v,f,BONE)
tube('Teal_Seam_Piping',section(.321,.811,False),.0032,TEAL,4,True)
tube('Navy_End_Piping',section(-.318,.84,False),.003,DARK,4,True)
# Continuous top zipper tape. Closed bag avoids unmodelled cavities and has a real pull.
zip_points=[(-.275,0,.267),(-.23,0,.280),(-.14,0,.280),(-.05,0,.271),(.045,0,.274),(.14,0,.279),(.23,0,.278),(.275,0,.266)]
ribbon('Zipper_Tape',zip_points,.025,.004,DARK)
for i in range(27):
    x=-.253+i*.0195;z=.280-.007*gauss(x,0,.10)-.009*gauss(abs(x),.272,.032)
    box(f'Zipper_Tooth_{i:02}',(.012,.012,.004),(x,0,z+.002),BONE,0,1)
box('Zipper_Slider',(.022,.024,.009),(.226,0,.286),DARK,.002,1)
pull=[(.231,-.004,.288),(.246,-.010,.287),(.271,-.013,.282),(.277,-.006,.281),(.27,.004,.282),(.248,.009,.288)]
tube('Zipper_Pull',pull,.0026,BONE,4,True)
# Webbing wraps onto the base; the two carry arches use thick, gently rounded strips.
for x in (-.181,.181):
    for side in (-1,1):
        ribbon(f'Body_Webbing_{x}_{side}',[(x,side*(surface_y(x,z)+.007),z) for z in (.029,.053,.080,.107,.135,.164,.192,.220,.247,.262)],.025,.006,DARK,(1,0,0))
        anchor_y=surface_y(x,.171)+.008
        box(f'Sewn_Anchor_{x}_{side}',(.035,.008,.046),(x,side*anchor_y,.171),DARK,.002,1)
        for dx in (-.012,.012):
            tube(f'Anchor_Stitch_{x}_{side}_{dx}',[(x+dx,side*(anchor_y+.005),.155),(x+dx,side*(anchor_y+.005),.187)],.00065,BONE,4)
for side in (-1,1):
    y=side*.086
    pts=[(-.182,side*.142,.214),(-.172,y,.285),(-.138,y,.342),(-.091,y,.382),(-.055,y,.391),(.055,y,.391),(.094,y,.380),(.14,y,.338),(.171,y,.282),(.182,side*.142,.214)]
    ribbon(f'Carry_Handle_{side}',pts,.025,.009,DARK,plane_normal=(0,1,0))
    ribbon(f'Padded_Grip_{side}',[(-.064,y,.393),(-.054,y,.395),(.054,y,.395),(.064,y,.393)],.028,.016,NAVY,plane_normal=(0,1,0))
# Shoulder strap is draped across the front; its diagonal cushion is actual padding.
strap=[(-.306,-.035,.246),(-.329,-.084,.218),(-.328,-.151,.139),(-.294,-.181,.061),(-.238,-.19,.026),(-.13,-.191,.021),(-.040,-.189,.050),(.051,-.180,.094),(.143,-.168,.150),(.235,-.131,.198),(.313,-.043,.246)]
ribbon('Shoulder_Strap',strap,.025,.007,DARK,(0,0,1))
pad=[(-.037,-.198,.055),(-.025,-.197,.061),(.135,-.182,.150),(.145,-.181,.156)]
ribbon('Shoulder_Pad_Shell',pad,.065,.018,DARK,(0,0,1))
ribbon('Shoulder_Pad_Navy_Insert',[(-.026,-.209,.060),(.005,-.207,.076),(.113,-.196,.135),(.133,-.194,.148)],.049,.008,NAVY,(0,0,1))
for sign in (-1,1):
    # Solid rounded metal-look gate clips and sewn attachment tabs.
    x=sign*.312
    box(f'Shoulder_Attachment_Tab_{sign}',(.018,.044,.018),(x,-.022,.244),DARK,.003,1)
    loop=[(x,-.047,.248),(x,-.064,.255),(x,-.078,.247),(x,-.079,.228),(x,-.064,.221),(x,-.047,.229)]
    tube(f'Shoulder_Gate_Clip_{sign}',loop,.003,BONE,4,True)
    tube(f'Shoulder_Clip_Gate_{sign}',[(x,-.047,.232),(x,-.047,.246)],.002,DARK,4)
# Small plain woven label: no invented legible text or extra accent colour.
box('Woven_Label',(.042,.004,.020),(-.054,-.156,.146),BONE,.002,1)
box('Label_Inset',(.027,.002,.005),(-.054,-.159,.145),NAVY,.0006,1)

ASSET=[o for o in bpy.context.scene.objects if o.type=='MESH']
for ob in ASSET:finish(ob)
# Base-centre origin and grounded body; no authoring-object transforms in export.
mn,mx=bc.world_bounds(ASSET)
for ob in ASSET:
    for v in ob.data.vertices:v.co.z-=mn.z
bc.uv_all(ASSET)
reference=ROOT/'assets/props/_tests/trellis2/inputs/PICK_a_duffel.png'
shutil.copyfile(reference,HERE/'reference/PICK_a_duffel.png')
QA={'asset':'duffel_procedural','method':'Original procedural mesh geometry. Image reference informs the design only; no generated geometry, no TRELLIS source, no baked lighting.','source_prefix':'DFP_','reference':'reference/PICK_a_duffel.png','texture_sources':['art/textures/fabric_ripstop.png','art/textures/fabric_soft.png','art/textures/leather_soft.png','assets/characters/kestrel/v2/textures/jacket_normal.png','assets/characters/kestrel/v2/textures/webLight_normal.png','assets/characters/kestrel/v2/textures/web_normal.png'],'pbr':'sRGB albedo; linear ORM R=1, G=roughness, B=metalness; existing OpenGL normal relief attenuated to 6%; no baked illumination','built':qa(ASSET)}
assert QA['built']['triangles']<=6000
assert QA['built']['all_uvs'] and QA['built']['all_identity_transforms']
assert QA['built']['nonmanifold_edges']==0 and QA['built']['degenerate_triangles']==0
log('built',QA['built']['triangles'],'triangles',QA['built']['bounds_blender_z_up_m'])
studio()
paths=bc.render_views(str(RENDERS),'duffel',objs=ASSET,views=('front','right','back','three_quarter','three_quarter_back','top'),res=(1000,1000),samples=48,ortho=True,margin=1.08)
bc.contact_sheet(paths,str(RENDERS/'contact_sheet.png'),cols=3)
clay=bc.material('_QA_Clay',(.35,.37,.40),rough=.7)
bpy.context.scene.view_layers[0].material_override=clay
bc.render_views(str(RENDERS),'clay',objs=ASSET,views=('three_quarter',),res=(1000,1000),samples=32,ortho=True,margin=1.08)
bpy.context.scene.view_layers[0].material_override=None
# Editable individual source parts in BLEND; one engine mesh with four material primitives.
clones=[]
for ob in ASSET:
    c=ob.copy();c.data=ob.data.copy();bpy.context.scene.collection.objects.link(c);clones.append(c)
select(*clones);bpy.ops.object.join();export=bpy.context.view_layer.objects.active
export.name='DFP_Duffel';export.data.name='DFP_Duffel';select(export)
bm=bmesh.new();bm.from_mesh(export.data)
bmesh.ops.triangulate(bm,faces=list(bm.faces),quad_method='BEAUTY',ngon_method='BEAUTY')
bm.to_mesh(export.data);bm.free();export.data.update()
base=str(HERE/'duffel')
bpy.ops.export_scene.gltf(filepath=base+'.glb',export_format='GLB',use_selection=True,export_apply=True,export_yup=True,export_normals=True,export_tangents=True)
# FBX cannot carry glTF's packed ORM channel graph. Give it faithful matte scalar
# fallbacks rather than the glTF texture multipliers (=1), which would look metallic.
fbx_links=[]
for m in (NAVY,TEAL,BONE,DARK):
    nt=m.node_tree;bs=nt.nodes.get('Principled BSDF')
    for key,prop in (('Roughness','roughness_fallback'),('Metallic','metallic_fallback')):
        socket=bs.inputs[key]
        for link in list(socket.links):fbx_links.append((nt,link.from_socket,socket));nt.links.remove(link)
        socket.default_value=m[prop]
bpy.ops.export_scene.fbx(filepath=base+'.fbx',use_selection=True,axis_forward='-Z',axis_up='Y',apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',use_mesh_modifiers=True,mesh_smooth_type='FACE',path_mode='COPY',embed_textures=True,object_types={'MESH'},bake_anim=False)
for nt,source,target in fbx_links:target.default_value=1;nt.links.new(source,target)
bpy.data.objects.remove(export,do_unlink=True)
QA['export_document']=glb_summary(base+'.glb')
QA['fbx_material_fallback']='Embedded albedo and normal; scalar roughness (.73/.71/.59/.65) and metalness=0 because FBX does not preserve glTF packed ORM channel graph. Full ORM maps are supplied in textures/ and GLB.'
assert QA['export_document']['all_uv0'] and QA['export_document']['materials']==4
assert all(not v for v in QA['export_document']['node_transforms'].values())
assert all(m['basecolor_texture'] and m['roughness_metallic_texture'] and m['normal_texture'] for m in QA['export_document']['pbr_materials'])
QA['pivot']='Origin at body base-centre, metres, front -Y, Blender Z up; glTF Y up, identity root mesh.'
for im in bpy.data.images:
    if im.filepath and Path(bpy.path.abspath(im.filepath)).is_relative_to(TEX):im.filepath=bpy.path.relpath(im.filepath,start=str(HERE))
bpy.ops.wm.save_as_mainfile(filepath=base+'.blend')
for kind in ('glb','fbx'):
    bc.reset_scene()
    if kind=='glb':bpy.ops.import_scene.gltf(filepath=base+'.glb',merge_vertices=True)
    else:bpy.ops.import_scene.fbx(filepath=base+'.fbx')
    imported=[o for o in bpy.context.scene.objects if o.type=='MESH']
    QA['fresh_'+kind+'_import']=qa(imported)
    QA['fresh_'+kind+'_import']['materials']=sorted({m.name for o in imported for m in o.data.materials})
    assert QA['fresh_'+kind+'_import']['triangles']==QA['built']['triangles']
    assert QA['fresh_'+kind+'_import']['all_uvs'] and QA['fresh_'+kind+'_import']['nonmanifold_edges']==0
    b=QA['built']['bounds_blender_z_up_m'];q=QA['fresh_'+kind+'_import']['bounds_blender_z_up_m']
    assert max(abs(a-c) for a,c in zip(b['size'],q['size']))<1e-5
    studio();bc.render_views(str(RENDERS),'imported_'+kind,objs=imported,views=('three_quarter',),res=(1000,1000),samples=48,ortho=True,margin=1.08)
QA['wall_seconds']=round(time.time()-START,2)
(HERE/'QA.json').write_text(json.dumps(QA,indent=2))
log('done',QA['wall_seconds'],'seconds')
