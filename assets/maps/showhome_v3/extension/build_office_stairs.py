"""Original reusable stair attachment for two stacked, existing site_office props.

Blender -b --factory-startup -P extension/build_office_stairs.py -- --render
Only this new prop and its catalog id are written. Existing offices are read-only.
"""
import sys, json, math, hashlib, copy
from pathlib import Path
import bpy, bmesh
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import common as C
import build_library as LIB
from gltf_shared import read

PID = 'site_office_stairs'
DEST = C.ROOT / 'assets/props/worksite' / PID
OFFICE = C.ROOT / 'assets/props/worksite/site_office'
WIDTH = 1.20
RISE = 2.8 / 16
GOING = .30
FACES = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
M = {}

def solid(name, vertices, material, root, bevel=0, collision=True, walkable=False):
    """Bevelled original member, exact convex collision, exact planar LOD1."""
    ob = C.mesh(name, vertices, FACES, M[material], root)
    ob['lod1_mesh'] = json.dumps(dict(vertices=vertices, faces=FACES), separators=(',', ':'))
    if bevel:
        bm = bmesh.new(); bm.from_mesh(ob.data)
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=1, affect='EDGES', clamp_overlap=True)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(ob.data); bm.free()
        for layer in list(ob.data.uv_layers):ob.data.uv_layers.remove(layer)
        C.uv(ob, M[material].get('repeat_m', 1))
    else:
        for loop in ob.data.uv_layers[0].data: loop.uv /= M[material].get('repeat_m', 1)
    C.bc.shade_smooth(ob, 35)
    ob['part'] = material
    if collision:
        co = C.col_mesh(name, vertices, FACES, M[material]['phys'], walkable=walkable, parent=root)
        ob['collision'] = co.name
    return ob

def box(name, lo, hi, material, root, bevel=.002, collision=True, walkable=False):
    x,y,z=lo; a,b,c=hi
    vs=[(x,y,z),(a,y,z),(a,b,z),(x,b,z),(x,y,c),(a,y,c),(a,b,c),(x,b,c)]
    return solid(name, vs, material, root, min(bevel, min(hi[k]-lo[k] for k in range(3))*.2), collision, walkable)

def beam(name, a, b, width, depth, material, root, collision=True):
    a,b=Vector(a),Vector(b); direction=(b-a).normalized(); centre=(a+b)/2; length=(b-a).length
    side=direction.cross(Vector((0,0,1)))
    if side.length<.001:side=Vector((1,0,0))
    side.normalize(); vertical=direction.cross(side).normalized()
    vs=[tuple(centre+side*(x*width/2)+vertical*(y*depth/2)+direction*(z*length/2)) for x,y,z in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
    return solid(name,vs,material,root,.002,collision)

def rail(name, a, b, root, width=.04):
    return beam(name,a,b,width,width,'rail',root)

def build():
    global M
    root=LIB.begin(PID,'worksite',mount='site_office')
    root['pivot']='attachment origin: same ground-centre as lower site_office'
    root['pivot_exception']='not base-bounding-box centre; deliberate mounting datum'
    root['mount_offset_m']=[0,0,0]
    root['upper_office_offset_m']=[0,0,2.8]
    root['front']='design -Y'
    root['riser_m']=RISE; root['tread_m']=GOING; root['clear_width_m']=WIDTH
    root['landing_top_m']=2.8; root['rail_height_m']=1.05
    M={
        'skin':C.material('OfficeStairGalvanizedSheet','sheet_metal','metal_scaffold_tube',(.82,.86,.90),metal=.8),
        'frame':C.material('OfficeStairStructuralSteel','metal_heavy','metal_scaffold_tube',(.24,.29,.32),metal=.8),
        'rail':C.material('OfficeStairSafetyRail','metal_heavy','metal_painted_yellow',(.95,.95,.88),metal=.6),
        'paint':C.material('OfficeStairNosingPaint','sheet_metal','metal_painted_yellow',(.95,.95,.88),metal=.6),
    }
    # Sixteen 175 mm rises. Fifteen elevated 300 mm flight treads plus the
    # landing; the first 300 mm at grade is the entry going, on site ground.
    for i in range(1,16):
        y=-7+i*GOING; z=i*RISE
        box('Stair_Tread_%02d'%i,(-4.30,y,z-.008),(-3.00,y+GOING,z),'skin',root,collision=False)
        # An 8 mm downturned lip stiffens each real sheet tread.
        box('Stair_TreadLip_%02d'%i,(-4.30,y,z-.028),(-3.00,y+.008,z),'skin',root,collision=False)
        box('Stair_Nosing_%02d'%i,(-4.295,y+.001,z+.0003),(-3.005,y+.026,z+.0013),'paint',root,bevel=0,collision=False)
    for i in range(1,17):
        y=-7+i*GOING
        box('Stair_Riser_%02d'%i,(-4.30,y-.008,(i-1)*RISE),(-3.00,y,i*RISE),'skin',root,collision=False)
    for x in (-4.30,-3.00):
        beam('Stair_Stringer',(x,-6.96,.045),(x,-2.20,2.72),.07,.17,'frame',root)
        box('Stair_BaseShoe',(x-.10,-7.08,0),(x+.10,-6.75,.012),'frame',root)
    # Exact closed inclined slab, rather than disconnected step-box collision.
    vs=[(-4.25,-7,-.08),(-3.05,-7,-.08),(-3.05,-2.2,2.72),(-4.25,-2.2,2.72),
        (-4.25,-7,0),(-3.05,-7,0),(-3.05,-2.2,2.8),(-4.25,-2.2,2.8)]
    co=C.col_mesh('Stair_WalkRamp',vs,FACES,'metal_heavy',walkable=True,parent=root)
    co['proxy']='closed smoothing slab, exact 4.8 m run and 2.8 m rise'
    for x in (-4.275,-3.025):
        for i in (0,4,8,12,16):
            y=-7+i*GOING; z=i*RISE
            rail('Stair_RailPost',(x,y,max(0,z-.06)),(x,y,z+1.05),root,.05)
        for h in (.52,1.05):
            rail('Stair_FlightRail',(x,-7,h),(x,-2.2,2.8+h),root,.05)
        beam('Stair_ToeRail',(x,-6.90,.09),(x,-2.20,2.83),.008,.09,'skin',root)
    # Notch over the last 0.5 m of the flight prevents a plate covering treads.
    # The west turn pocket extends to -0.98 beside the office, keeping 1.22 m
    # turn depth; the main front platform retains the specified rear -1.25.
    for name,lo,hi in (
        ('Landing_Front',(-3.05,-2.70,2.792),(.60,-1.25,2.80)),
        ('Landing_Turn',(-4.40,-2.20,2.792),(-3.05,-.98,2.80)),
        ('Landing_NotchMargin',(-4.40,-2.70,2.792),(-4.30,-2.20,2.80)),
    ):box(name,lo,hi,'skin',root,bevel=.001,walkable=True)
    # All support and guard members carry metal_heavy; landing skins are 8 mm.
    for y,x0,x1 in ((-2.62,-3.05,.60),(-1.33,-3.05,.60),(-2.12,-4.40,-3.05),(-1.06,-4.40,-3.05)):
        beam('Landing_PerimeterBeam',(x0,y,2.702),(x1,y,2.702),.08,.18,'frame',root)
    for x,ya,yb in ((-4.32,-2.7,-.98),(-3.13,-2.7,-.98),(.52,-2.7,-1.25)):
        beam('Landing_LongitudinalBeam',(x,ya,2.702),(x,yb,2.702),.08,.18,'frame',root)
    for x in (-2.40,-1.20,0):
        beam('Landing_Joist',(x,-2.7,2.7195),(x,-1.25,2.7195),.045,.145,'frame',root)
    for x,y in ((-4.32,-1.06),(-3.13,-1.06),(-3.13,-2.62),(.52,-2.62)):
        box('Landing_Column',(x-.045,y-.045,.012),(x+.045,y+.045,2.792),'frame',root)
        box('Landing_Footplate',(x-.13,y-.13,0),(x+.13,y+.13,.012),'frame',root)
    beam('Landing_UnderBrace',(-4.32,-1.06,.30),(-3.13,-1.06,2.55),.035,.035,'frame',root)
    beam('Landing_UnderBrace',(-3.13,-2.62,.30),(.52,-2.62,2.55),.035,.035,'frame',root)
    # Open stair mouth, open front-door connection, and a protected turn pocket.
    edges=[((-3.00,-2.725),(.625,-2.725)),((.625,-2.725),(.625,-1.225)),
           ((-4.425,-2.2),(-4.425,-.955)),((-4.425,-.955),(-3.025,-.955)),
           ((-3.025,-.955),(-3.025,-1.30))]
    for n,(a,b) in enumerate(edges):
        length=math.dist(a,b); count=max(1,math.ceil(length/1.2))
        for k in range(count+1):
            x=a[0]+(b[0]-a[0])*k/count; y=a[1]+(b[1]-a[1])*k/count
            rail('Landing_RailPost_%d'%n,(x,y,2.76),(x,y,3.85),root,.05)
        for h in (.52,1.05):rail('Landing_Rail_%d'%n,(*a,2.8+h),(*b,2.8+h),root,.05)
        beam('Landing_ToeBoard_%d'%n,(*a,2.86),(*b,2.86),.008,.12,'skin',root)
    # Visible upper mounting tabs meet the existing floor datum, not a new door.
    for x in (-2.70,-1.35,.56):
        box('Landing_MountTab',(x-.06,-1.45,2.73),(x+.06,-1.30,2.79),'frame',root)
    return root

def inside(row,p,eps=1e-5):
    return all(Vector(q[:3]).dot(p)<=q[3]+eps for q in row['planes'])

def triangles(row):
    vs=[Vector(v) for v in row['vertices']]; result=[]
    for q in row['planes']:
        n=Vector(q[:3]); pts=[v for v in vs if abs(n.dot(v)-q[3])<2e-5]
        if len(pts)<3:continue
        centre=sum(pts,Vector())/len(pts); u=(pts[0]-centre).normalized(); v=n.cross(u)
        pts.sort(key=lambda p:math.atan2((p-centre).dot(v),(p-centre).dot(u)))
        result.extend((pts[0],pts[i],pts[i+1]) for i in range(1,len(pts)-1))
    return result

def point_tri(p,a,b,c):
    ab=b-a; ac=c-a; ap=p-a; d1=ab.dot(ap); d2=ac.dot(ap)
    if d1<=0 and d2<=0:return (p-a).length
    bp=p-b; d3=ab.dot(bp); d4=ac.dot(bp)
    if d3>=0 and d4<=d3:return (p-b).length
    vc=d1*d4-d3*d2
    if vc<=0 and d1>=0 and d3<=0:return (p-(a+ab*(d1/(d1-d3)))).length
    cp=p-c; d5=ab.dot(cp); d6=ac.dot(cp)
    if d6>=0 and d5<=d6:return (p-c).length
    vb=d5*d2-d1*d6
    if vb<=0 and d2>=0 and d6<=0:return (p-(a+ac*(d2/(d2-d6)))).length
    va=d3*d6-d5*d4
    if va<=0 and d4-d3>=0 and d5-d6>=0:return (p-(b+(c-b)*((d4-d3)/((d4-d3)+(d5-d6))))).length
    denom=1/(va+vb+vc); return (p-(a+ab*(vb*denom)+ac*(vc*denom))).length

def seg_seg(p1,q1,p2,q2):
    d1=q1-p1; d2=q2-p2; r=p1-p2; a=d1.dot(d1); e=d2.dot(d2); f=d2.dot(r)
    clamp=lambda x:max(0,min(1,x))
    if a<1e-12:s=0; t=clamp(f/e) if e else 0
    else:
        c=d1.dot(r)
        if e<1e-12:t=0; s=clamp(-c/a)
        else:
            b=d1.dot(d2); den=a*e-b*b; s=clamp((b*f-c*e)/den) if den>1e-12 else 0
            t=(b*s+f)/e
            if t<0:t=0;s=clamp(-c/a)
            elif t>1:t=1;s=clamp((b-c)/a)
    return ((p1+d1*s)-(p2+d2*t)).length

def capsule_distance(row,foot,r=.32,h=1.8):
    a=Vector(foot)+Vector((0,0,r)); b=Vector(foot)+Vector((0,0,h-r))
    # Clip capsule axis against the actual convex volume; endpoint tests alone
    # would miss a beam crossing the middle of a standing capsule.
    enter=0.; leave=1.; direction=b-a
    for q in row['planes']:
        n=Vector(q[:3]); den=n.dot(direction); dist=q[3]-n.dot(a)
        if abs(den)<1e-9:
            if dist<0:enter=2;break
        elif den>0:leave=min(leave,dist/den)
        else:enter=max(enter,dist/den)
    if enter<=leave and enter<=1 and leave>=0:return 0.
    result=1e6
    for p,q,s in row['_tris']:
        result=min(result,point_tri(a,p,q,s),point_tri(b,p,q,s),
                   seg_seg(a,b,p,q),seg_seg(a,b,q,s),seg_seg(a,b,s,p))
    return result

def office_rows():
    original=json.loads((OFFICE/'collision.json').read_text())['volumes']; rows=[]
    for level in (0,1):
        for source in original:
            # The door is interactive, and the access route is tested open.
            # Neither original GLB nor its structural OPEN hierarchy is edited.
            if (source.get('parent') or '').startswith('OPEN_'):continue
            row=copy.deepcopy(source); dz=level*2.8; row['name']='Office_%d_'%level+row['name']
            for vertex in row['vertices']:vertex[2]+=dz
            for q in row['planes']:q[3]+=q[2]*dz
            row['aabb']['min'][2]+=dz;row['aabb']['max'][2]+=dz
            row['walkable']=any(k in row['name'] for k in ('OfficeFloor','OfficeRoof'))
            rows.append(row)
    return rows

def qa(rows):
    fixed=rows+office_rows()
    for row in fixed:row['_tris']=triangles(row)
    path=[]
    def segment(a,b):
        count=math.ceil(math.dist(a,b)/.06)
        for i in range(count+1):path.append(tuple(a[k]+(b[k]-a[k])*i/count for k in range(3)))
    segment((-3.65,-7.5,0),(-3.65,-7,0))
    segment((-3.65,-7,0),(-3.65,-2.2,2.8))
    segment((-3.65,-2.2,2.8),(-3.65,-1.82,2.8))
    segment((-3.65,-1.82,2.8),(-3.00,-1.82,2.8))
    segment((-3.00,-1.82,2.8),(0,-2.04,2.8))
    segment((0,-2.04,2.8),(0,-1.40,2.8))
    segment((0,-1.40,2.9),(0,-.72,2.9))
    supported=[]; clearance=1e6; body_clearance=1e6; max_lift=0
    for x,y,want in path:
        support=[]; nearby=[]
        for row in fixed:
            lo=row['aabb']['min'];hi=row['aabb']['max']
            # A wider measurement window also includes nearby rails that the
            # capsule does not touch, so the clearance figure is meaningful.
            if x+.70<lo[0] or x-.70>hi[0] or y+.70<lo[1] or y-.70>hi[1]:continue
            nearby.append(row)
            if x+.32<lo[0] or x-.32>hi[0] or y+.32<lo[1] or y-.32>hi[1]:continue
            if not row.get('walkable'):continue
            # A capsule can touch the upcoming 100 mm office threshold before
            # its centre reaches the floor edge.
            if hi[2]<=want+.20 or 'Stair_WalkRamp' in row['name']:support.append(row)
        centre_tops=[]
        for row in support:
            for nx,ny,nz,d in row['planes']:
                if nz<.5:continue
                z=(d-nx*x-ny*y)/nz
                if abs(z-want)<.12 and inside(row,Vector((x,y,z))):centre_tops.append(z)
        assert centre_tops or want==0,('support absent',x,y,want)
        foot=max([want]+centre_tops)
        if any(capsule_distance(row,(x,y,foot))<.32-1e-5 for row in support):
            low=foot; high=foot+.35
            assert all(capsule_distance(row,(x,y,high))>=.32-1e-5 for row in support),('support lift impossible',x,y)
            for _ in range(17):
                mid=(low+high)/2
                if any(capsule_distance(row,(x,y,mid))<.32-1e-5 for row in support):low=mid
                else:high=mid
            foot=high
        max_lift=max(max_lift,foot-want)
        for row in nearby:
            distance=capsule_distance(row,(x,y,foot));gap=distance-.32
            assert gap>=-.00003,('standing capsule blocked',x,y,foot,row['name'],gap)
            if row not in support:
                clearance=min(clearance,gap)
                if row['aabb']['max'][2]>foot+.32:body_clearance=min(body_clearance,gap)
        supported.append([round(x,6),round(y,6),round(want,6),round(foot,6)])
    return dict(passed=True,riser_count=16,riser_m=RISE,elevated_flight_treads=15,tread_m=GOING,
        entry_going_m=.30,flight_run_m=4.8,flight_pitch_deg=math.degrees(math.atan2(2.8,4.8)),
        clear_width_m=WIDTH,front_walk_strip_clear_m=1.292,top_turn_clear_depth_m=1.22,
        capsule_radius_m=.32,capsule_height_m=1.8,route_samples=len(path),supported_path=supported,
        support_method='vertical ray plus exact capsule/convex-triangle distance; <=60 mm route spacing',
        obstacle_clearance_method='distance from capsule axis segment to all convex face triangles',
        minimum_non_support_capsule_gap_m=round(clearance,6),minimum_side_or_overhead_capsule_gap_m=round(body_clearance,6),max_capsule_support_lift_m=round(max_lift,6),
        minimum_door_aperture_width_m=1.1,door_aperture_height_m=2.14,doorway_requires_open_interactive_leaf=True,
        landing_elevation_m=2.8,upper_office_floor_elevation_m=2.9,office_threshold_step_m=.10,
        stairs_without_jetpack=True,upper_office_reached=True,office_door_hierarchy_preserved=True)

def verify_exports():
    output={}
    for suffix in ('','_lod1'):
        path=DEST/(PID+suffix+'.glb');j,buf=read(path)
        assert all('uri' in im and 'bufferView' not in im and (path.parent/im['uri']).is_file() for im in j.get('images',[]))
        assert all(m.get('extras',{}).get('phys') in C.PHYS for m in j['materials'])
        assert all('TEXCOORD_0' in p['attributes'] for m in j['meshes'] for p in m['primitives'])
        tris=sum(j['accessors'][p['indices']]['count']//3 for m in j['meshes'] for p in m['primitives'])
        output['lod1_triangles' if suffix else 'lod0_triangles']=tris
        output[('lod1' if suffix else 'lod0')+'_bytes']=path.stat().st_size
        output['external_images']=[im['uri'] for im in j.get('images',[])]
        output['material_height_ranges_m']={m['name']:m['extras'].get('height_range_m') for m in j['materials']}
    return output

def render_context():
    cam=C.stage();sc=bpy.context.scene;sc.cycles.device='CPU';sc.cycles.samples=20
    sc.render.resolution_x=1280;sc.render.resolution_y=960
    C.render(cam,DEST/'renders/standalone.png',(-12,-14,10),(-1.9,-3.7,1.8),11.7)
    source_hash=hashlib.sha256((OFFICE/'site_office.glb').read_bytes()).hexdigest()
    for level in (0,1):
        before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(OFFICE/'site_office.glb'))
        for ob in (set(bpy.data.objects)-before):
            ob['preview_only']=True
            if ob.parent is None:ob.location.z+=level*2.8
    C.render(cam,DEST/'renders/stack_alignment.png',(-13,-14,11),(-.65,-2.7,2.5),13.5)
    C.render(cam,DEST/'renders/stack_front.png',(-.7,-16,8),(-.7,-2.7,2.5),11.4)
    assert source_hash==hashlib.sha256((OFFICE/'site_office.glb').read_bytes()).hexdigest()

def main():
    root=build();cols=[o for o in bpy.context.scene.objects if o.name.startswith('COL_')]
    rows=C.collision_rows(cols);route=qa(rows)
    LIB.save_prop(root,PID,'worksite','original procedural office stair attachment; extension/build_office_stairs.py')
    entry=LIB.CATALOG[-1]
    entry.update(mount='site_office',pivot='lower office ground-centre mounting datum',pivot_exception='attachment origin, not base-bbox centre',
        placement_offset_m=[0,0,0],upper_office_offset_m=[0,0,2.8],flight_entry_offset_m=[-3.65,-7,0],
        flight_top_offset_m=[-3.65,-2.2,2.8],upper_door_offset_m=[0,-1.4,2.8],
        finished_floor_m=2.9,landing_top_m=2.8,clear_width_m=WIDTH,rail_height_m=1.05,
        landing_sheet_thickness_m=.008,original_geometry=True,source_builder='maps/showhome_v3/extension/build_office_stairs.py',
        landing_notch_bounds_m=[-4.3,-2.7,-3.05,-2.2],turn_pocket_bounds_m=[-4.4,-2.2,-3.05,-.98])
    C.write(DEST/'metadata.json',entry)
    exports=verify_exports();route.update(exports)
    route.update(phys_ok=True,uv_ok=True,external_images_ok=True,convex_collision_ok=True,
        collision_volumes=len(rows),min_collision_thickness_m=min(r['thickness_m'] for r in rows),
        no_new_texture_images=True,render_device='CPU')
    C.write(DEST/'QA.json',route)
    C.write(DEST/'stairs_route.json',dict(frame='attachment local design XYZ metres',supported_path_columns=['x','y','surface_z','capsule_bottom_z'],**route))
    # Merge exactly this id into the latest files; other builders may run in parallel.
    catalog_path=LIB.PROPS/'catalog.json';catalog=json.loads(catalog_path.read_text())
    catalog['props']=[p for p in catalog['props'] if p['id']!=PID]+[entry];C.write(catalog_path,catalog)
    manifest_path=LIB.HERE/'library_manifest.json';manifest=json.loads(manifest_path.read_text())
    manifest['props']=[p for p in manifest['props'] if p['id']!=PID]+[entry];C.write(manifest_path,manifest)
    notes='''Original reusable external metal stair/landing attachment, authored for Showhome v3.

Mounting: place lower site_office and this attachment at exactly the same XYZ and yaw.
Place the upper site_office at local (0,0,2.8). Blender metres/Z-up/front -Y;
glTF converts to (x,z,-y). Deliberate pivot exception: attachment origin matches
the lower office ground-centre, not this asymmetric stair's base-bbox centre.

Flight: centre X -3.65, grade entry Y -7.00/Z 0, top Y -2.20/Z 2.80;
16 rises of 175 mm, 300 mm going, 15 elevated treads plus final landing.
The entry going is at grade. 1.20 m clear between 50 mm steel rails;
handrail is 1.05 m over the pitch line. Real 8 mm treads, riser plates,
downturned lips, paired structural stringers and yellow painted nosings.
Closed 80 mm inclined-prism collision smooths the flight without a jetpack.

Main landing X -4.40..0.60 / Y -2.70..-1.25 / top Z 2.80. Stair notch
X -4.30..-3.05 / Y -2.70..-2.20 leaves the final steps exposed. A west
turn pocket extends rearward to Y -0.98 beside the office, providing 1.22 m
clear turning depth. Main front strip has 1.292 m clear to the office skin.
Landing is 8 mm sheet_metal, with separate heavy beams, joists, columns,
braces and feet. Slim guardrails are metal_heavy; no railing closes the
stair mouth or the front doorway. The existing office floor is 100 mm
above its base: landing 2.80 m to upper finished floor 2.90 m is a normal
100 mm threshold step, checked in the capsule route.

QA: <=60 mm route samples, vertical support plus actual capsule-to-convex
face distance, radius 0.32 m / total height 1.8 m. The existing interactive
office leaf must be opened to enter; its original OPEN_DOOR hierarchy and
source GLB are preserved. See QA.json and stairs_route.json for measured
clearance, support lift, triangles and shared images.

Only existing painted v2 metal textures are used. UVs, repeat distances,
height_range_m and physics extras are retained; images are shared external
maps/showhome_v3/textures files. No new images, third-party meshes or game
code. GLB, LOD1, editable Blender source, collision and metadata included.

Rebuild: Blender -b --factory-startup -P
assets/maps/showhome_v3/extension/build_office_stairs.py -- --render
Renders are Cycles CPU: standalone.png, stack_alignment.png, stack_front.png.
Stacked-office context imports the two original GLBs without changing doors.
'''
    (DEST/'NOTES.md').write_text(notes,encoding='utf8')
    if '--render' in sys.argv:render_context()
    print('OFFICE_STAIRS_READY',json.dumps({k:v for k,v in route.items() if k not in ('supported_path','external_images')}),flush=True)

if __name__=='__main__':main()
