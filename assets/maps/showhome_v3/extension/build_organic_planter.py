"""Original organic printed-concrete planter with integrated dark timber seats.

Blender -b --factory-startup -P extension/build_organic_planter.py -- --render
References inform style only. No downloaded geometry, generated images or old prop writes.
"""
import sys,math,json
from pathlib import Path
import bpy,bmesh
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import common as C
import build_library as LIB
from gltf_shared import read

PID='organic_planter_bench'
DEST=LIB.PROPS/'garden'/PID
N=72
M={}

def curve(t):
    x=3.50*math.cos(t)+.28*math.cos(2*t)
    y=1.32*math.sin(t)+.25*math.sin(2*t)-.10*math.cos(t)
    if math.sin(t)>0:y-=.68*math.exp(-((x-.10)/1.12)**2)*math.sin(t)
    return Vector((x,y,0))

def normal(t):
    tangent=(curve(t+.0001)-curve(t-.0001)).normalized()
    return Vector((tangent.y,-tangent.x,0))

def sample(count=N):
    return [(curve(i*2*math.pi/count),normal(i*2*math.pi/count)) for i in range(count)]

def sweep_geometry(points,profile,closed):
    vertices=[tuple(p+n*d+Vector((0,0,z))) for p,n in points for d,z in profile]
    k=len(profile);count=len(points);faces=[]
    for i in range(count if closed else count-1):
        j=(i+1)%count
        faces += [(i*k+a,j*k+a,j*k+(a+1)%k,i*k+(a+1)%k) for a in range(k)]
    if not closed:faces += [tuple(reversed(range(k))),tuple((count-1)*k+a for a in range(k))]
    return vertices,faces

def sweep(name,points,profile,material,root,closed=True,low_profile=None,low_points=None):
    vs,fs=sweep_geometry(points,profile,closed)
    ob=C.mesh(name,vs,fs,M[material],root)
    bm=bmesh.new();bm.from_mesh(ob.data);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(ob.data);bm.free()
    # Unwrap the circumference in U and physical height in V. Printed courses
    # remain horizontal even where the outline turns inward.
    arc=[0.]
    for i in range(1,len(points)):arc.append(arc[-1]+(points[i][0]-points[i-1][0]).length)
    uv=ob.data.uv_layers[0];repeat=M[material].get('repeat_m',1);k=len(profile)
    for face in ob.data.polygons:
        indices=[ob.data.loops[li].vertex_index for li in face.loop_indices]
        cap=len({vi//k for vi in indices})==1
        axis=max(range(3),key=lambda a:abs(face.normal[a]));axes=[a for a in range(3) if a!=axis]
        for li in face.loop_indices:
            vi=ob.data.loops[li].vertex_index;i,a=divmod(vi,k)
            if abs(face.normal.z)>.55 or cap:
                # Coping/seat tops and open-run end caps need surface area in
                # UV space, rather than a constant-height line.
                p=ob.data.vertices[vi].co;uv.data[li].uv=(p[axes[0]]/repeat,p[axes[1]]/repeat)
            else:uv.data[li].uv=(arc[i]/repeat,profile[a][1]/repeat)
    C.bc.shade_smooth(ob,65)
    lvs,lfs=sweep_geometry(low_points or points,low_profile or profile,closed)
    ob['lod1_mesh']=json.dumps(dict(vertices=lvs,faces=lfs),separators=(',',':'))
    ob['part']=material
    return ob

def prism(name,poly,z0,z1,phys,root):
    """Exact closed prism over a convex polygon in XY."""
    count=len(poly);vs=[(p.x,p.y,z) for z in (z0,z1) for p in poly]
    fs=[tuple(reversed(range(count))),tuple(range(count,2*count))]
    fs += [(i,(i+1)%count,(i+1)%count+count,i+count) for i in range(count)]
    return C.col_mesh(name,vs,fs,phys,parent=root)

def signed_area(poly):return sum(a.x*b.y-b.x*a.y for a,b in zip(poly,poly[1:]+poly[:1]))/2

def convex(poly):
    signs=[]
    for a,b,c in zip(poly,poly[1:]+poly[:1],poly[2:]+poly[:2]):signs.append((b-a).cross(c-b).z)
    return min(signs)>=-1e-6 or max(signs)<=1e-6

def convex_partition(poly):
    """Merge adjacent tessellation triangles into exact convex pieces."""
    lookup={tuple(p):i for i,p in enumerate(poly)}
    parts=[[v if isinstance(v,int) else lookup[tuple(v)] for v in tri] for tri in tessellate_polygon([poly])]
    for part in parts:
        if signed_area([poly[i] for i in part])<0:part.reverse()
    def merge(a,b):
        edges=[(p,q) for piece in (a,b) for p,q in zip(piece,piece[1:]+piece[:1])]
        edges=[e for e in edges if (e[1],e[0]) not in edges]
        if len(edges)!=len(a)+len(b)-2:return None
        result=[edges[0][0]];current=edges[0][1]
        while current!=result[0]:
            result.append(current);following=[q for p,q in edges if p==current]
            if len(following)!=1:return None
            current=following[0]
            if len(result)>len(edges):return None
        if len(result)>14 or not convex([poly[i] for i in result]):return None
        return result
    changed=True
    while changed:
        changed=False
        for i in range(len(parts)):
            for j in range(i+1,len(parts)):
                joined=merge(parts[i],parts[j])
                if joined:
                    parts[i]=joined;parts.pop(j);changed=True;break
            if changed:break
    return [[poly[i] for i in part] for part in parts]

def segment_collision(name,points,inner,outer,z0,z1,phys,root,closed=True):
    for i in range(len(points) if closed else len(points)-1):
        p,n=points[i];q,m=points[(i+1)%len(points)]
        poly=[p+n*outer,q+m*outer,q+m*inner,p+n*inner]
        if convex(poly):prism(name+'_%03d'%i,poly,z0,z1,phys,root)
        else:
            for j,part in enumerate(convex_partition(poly)):prism(name+'_%03d_%d'%(i,j),part,z0,z1,phys,root)

def bead_profile(inner,outer,height,pitch):
    rows=[];layers=round(height/pitch)
    for i in range(layers):rows += [(outer,i*pitch),(outer+.009,(i+.5)*pitch)]
    rows.append((outer,height))
    reverse=[]
    for i in range(layers):reverse += [(inner,i*pitch),(inner-.009,(i+.5)*pitch)]
    reverse.append((inner,height))
    return rows+list(reversed(reverse))

def bench_arc(t0,t1,root,index):
    # Tangential slats separated by genuine 6 mm gaps, each spanning the seat
    # depth. Their ends follow the planter curve instead of a rectangular bench.
    dense=[(curve(t0+(t1-t0)*i/400),normal(t0+(t1-t0)*i/400)) for i in range(401)]
    total=sum((b[0]-a[0]).length for a,b in zip(dense,dense[1:]));count=math.ceil(total/.115)
    points=[];travel=0;next_distance=0
    for a,b in zip(dense,dense[1:]):
        length=(b[0]-a[0]).length
        while next_distance<=travel+length+1e-8:
            fraction=max(0,min(1,(next_distance-travel)/length));p=a[0].lerp(b[0],fraction);n=a[1].lerp(b[1],fraction).normalized()
            points.append((p,n));next_distance+=total/count
        travel+=length
    if len(points)<count+1:points.append(dense[-1])
    support_points=points[::2]
    if support_points[-1]!=points[-1]:support_points.append(points[-1])
    plinth_profile=bead_profile(.014,.475,.405,.045)
    sweep('Seat_PrintPlinth_%d'%index,support_points,plinth_profile,'printed',root,closed=False,
          low_profile=[(.014,0),(.475,0),(.475,.405),(.014,.405)])
    segment_collision('Seat_Plinth_%d'%index,support_points,.005,.484,0,.405,'concrete',root,False)
    for i,(a,b) in enumerate(zip(points,points[1:])):
        p,n=a;q,m=b;fraction=.003/(q-p).length
        aa=(p.lerp(q,fraction),n.lerp(m,fraction).normalized())
        bb=(p.lerp(q,1-fraction),n.lerp(m,1-fraction).normalized())
        ob=sweep('Seat_DarkWoodSlat_%d_%02d'%(index,i),[aa,bb],[(.022,.405),(.53,.405),(.53,.45),(.022,.45)],'wood',root,False)
        bevel=ob.modifiers.new('Soft timber edge','BEVEL');bevel.width=.003;bevel.segments=1
        C.apply(ob)
        segment_collision('Seat_Slat_%d_%02d'%(index,i),[aa,bb],.022,.53,.405,.45,'wood_thin',root,False)
    return total

def contains(poly,p):
    hit=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a.y>p.y)!=(b.y>p.y) and p.x<(b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x:hit=not hit
    return hit

def foliage(poly,offset):
    output=[]
    for i,(x,y,w,d) in enumerate(((-2.20,0,1.3,1.2),(-.50,-.45,2.1,.80),(2.0,.15,1.65,1.15))):
        for _ in range(16):
            test=[Vector((x+dx*w/2,y+dy*d/2,0)) for dx in (-1,0,1) for dy in (-1,0,1)]
            if all(contains(poly,p) for p in test):break
            w*=.9;d*=.9
        assert all(contains(poly,p) for p in test)
        lo=Vector((x-w/2,y-d/2,.535))+offset;hi=Vector((x+w/2,y+d/2,1.35))+offset
        output.append(dict(name='GREENFOL_OrganicPlanter_%d'%i,foliage='hedge',density=1.15,tint='sage_hedge',
                           aabb=dict(min=list(lo),max=list(hi)),source_prop=PID,render_proxy='existing game foliage system; no leaves baked'))
    return output

def build():
    global M
    root=LIB.begin(PID,'garden')
    M={
        'printed':C.material('OrganicCreamPrintedConcrete','concrete','printed_concrete_layers',(1,1,.96)),
        'coping':C.material('OrganicCreamCoping','concrete','concrete_smooth',(1,1,.98)),
        'wood':C.material('OrganicDarkSeatWood','wood_thin','wood_boards_stained',(.38,.32,.27)),
        'soil':C.material('OrganicPlanterSoil','soil','garden_soil',(.86,.9,.8)),
    }
    points=sample();lowpoints=sample(36)
    wall=sweep('Planter_RealPrintedCourses',points,bead_profile(-.22,0,.60,.04),'printed',root,
        low_profile=[(0,0),(0,.6),(-.22,.6),(-.22,0)],low_points=lowpoints)
    wall['printed_bead_pitch_m']=.04;wall['printed_bead_relief_m']=.009
    wall['collision_detail']='convex wall segments follow maximum bead envelope; 9 mm grooves are visual surface detail'
    segment_collision('Planter_Wall',points,-.229,.009,0,.60,'concrete',root)
    coping=sweep('Planter_BevelledCoping',points,[(.018,.6),(.018,.632),(.001,.65),(-.223,.65),(-.240,.632),(-.240,.6)],'coping',root,
        low_points=lowpoints)
    bed_min,bed_max=C.bc.world_bounds([wall,coping])
    segment_collision('Planter_Coping',points,-.240,.018,.60,.65,'concrete',root)
    inner=[p+n*(-.245) for p,n in points]
    soilparts=convex_partition(inner)
    for i,poly in enumerate(soilparts):
        count=len(poly);vs=[(p.x,p.y,z) for z in (0,.53) for p in poly]
        fs=[tuple(reversed(range(count))),tuple(range(count,2*count))]+[(j,(j+1)%count,(j+1)%count+count,j+count) for j in range(count)]
        ob=C.mesh('Planter_SoilInset_%02d'%i,vs,fs,M['soil'],root);C.uv(ob,M['soil']['repeat_m'])
        for loop in ob.data.uv_layers[0].data:loop.uv/=M['soil']['repeat_m']
        prism('Planter_Soil_%02d'%i,poly,0,.53,'soil',root)
    lengths=[bench_arc(3.67,5.75,root,0),bench_arc(.34,1.14,root,1)]
    obs=C.visuals();mn,mx=C.bc.world_bounds(obs);offset=Vector((-(mn.x+mx.x)/2,-(mn.y+mx.y)/2,-mn.z))
    for ob in root.children:ob.location+=offset
    bpy.context.view_layer.update();mn,mx=C.bc.world_bounds(obs)
    root['pivot']='base bounding-box centre at Z=0';root['outline']='original asymmetric kidney / sweeping wavy outline'
    root['wall_thickness_m']=.22;root['printed_course_pitch_m']=.04;root['printed_relief_m']=.009
    root['seat_top_m']=.45;root['seat_depth_m']=.508;root['soil_top_m']=.53;root['foliage_baked']=False
    root['bench_run_lengths_m']=lengths
    fol=foliage(inner,offset)
    return root,dict(bounds_m=dict(min=list(mn),max=list(mx)),seat_top_m=.45,soil_top_m=.53,
        bed_bounds_m=dict(min=list(bed_min+offset),max=list(bed_max+offset)),
        wall_thickness_m=.22,printed_course_pitch_m=.04,printed_relief_m=.009,bench_run_lengths_m=lengths,
        foliage_baked=False,foliage_local_volumes=fol,base_centre_offset_m=list(offset))

def qa(entry):
    sys.path.insert(0,str(HERE.parent))
    import verify as V
    V.GLB(DEST/(PID+'.glb'));V.GLB(DEST/(PID+'_lod1.glb'));rows,thin=V.collision(DEST/'collision.json')
    assert not V.FAIL,V.FAIL
    j,_=read(DEST/(PID+'.glb'));lod,_=read(DEST/(PID+'_lod1.glb'))
    count=lambda doc:sum(doc['accessors'][p['indices']]['count']//3 for m in doc['meshes'] for p in m['primitives'])
    report=dict(passed=True,phys_ok=True,uv_ok=True,convex_collision_ok=True,external_images_ok=True,
        lod0_triangles=count(j),lod1_triangles=count(lod),collision_volumes=len(rows),
        min_collision_thickness_m=min(r['thickness_m'] for r in rows),original_geometry=True,no_new_images=True,
        printed_courses_are_geometry=True,foliage_volumes=len(entry['foliage_local_volumes']),foliage_baked=False)
    C.write(DEST/'QA.json',report)
    return report

def renders(entry):
    cam=C.stage();sc=bpy.context.scene;sc.cycles.device='CPU';sc.cycles.samples=20
    sc.render.resolution_x=1280;sc.render.resolution_y=900
    C.render(cam,DEST/'renders/bare_planter.png',(9,-12,8),(0,0,.3),10.4)
    # Explicit render proxies make the runtime foliage handoff reviewable;
    # they are added only after base GLB/Blender source exports are complete.
    mat=C.material('OrganicPreviewFoliage','foliage_dense',None,(.14,.25,.105),rough=.95)
    for item in entry['foliage_local_volumes']:
        lo=Vector(item['aabb']['min']);hi=Vector(item['aabb']['max'])
        ob=C.box(item['name'],hi-lo,(lo+hi)/2,mat,bevel=.18,collision=False)
        ob['foliage']='hedge';ob['render_proxy']='no individual leaves; runtime foliage volume';ob['density']=1.15
    C.render(cam,DEST/'renders/foliage_preview.png',(9,-12,8),(0,0,.5),10.4)
    C.render(cam,DEST/'renders/top_plan.png',(0,0,14),(0,0,.3),9.6)

def main():
    root,extra=build();LIB.save_prop(root,PID,'garden','original procedural organic planter/bench; extension/build_organic_planter.py')
    entry=LIB.CATALOG[-1];entry.update(extra,pivot='base-centre at Z=0',front='design -Y',original_geometry=True,
        source_builder='maps/showhome_v3/extension/build_organic_planter.py')
    C.write(DEST/'metadata.json',entry);C.write(DEST/'foliage.json',dict(schema=1,frame='prop local design XYZ metres',volumes=entry['foliage_local_volumes'],leaf_generation='existing game foliage system'))
    result=qa(entry)
    for path in (LIB.PROPS/'catalog.json',LIB.HERE/'library_manifest.json'):
        data=json.loads(path.read_text());data['props']=[e for e in data['props'] if e['id']!=PID]+[entry];C.write(path,data)
    (DEST/'NOTES.md').write_text('''Original reusable organic planter with integrated curved dark timber benches.
Metres/Z-up/front -Y. Base-bounding-box-centre pivot at Z=0; exact bounds and
local foliage volumes are in metadata.json. Place at courtyard grade; yaw 0
puts the long axis along X, with the longest seat on the front/south side.

The original kidney outline is procedural and is not traced third-party mesh
geometry. References inform the sweeping shape, cream print and dark timber
style only. Wall is 220 mm concrete plus 9 mm actual printed bead relief at
40 mm pitch. Coping has a real 17-18 mm chamfer. Convex wall segments follow
the maximum bead envelope; the small print grooves are visual surface detail.
The soil inset is 120 mm below coping and has exact convex decomposition.

Two curving timber seat runs have actual separated slats, 45 mm thickness,
508 mm seat depth and 450 mm top height. Their printed concrete bases are
integrated into the outside wall at 405 mm top height. Exact convex segment
collision preserves the hollow planter and open space around the benches.

Existing painted v2 printed-concrete, concrete, dark wood and soil materials,
UVs, height metadata and external shared images; no new image or leaf cards.
foliage.json supplies conservative local GREENFOL proxy volumes for the
existing game leaf system. They are not baked into the asset GLBs or source
Blender scene. foliage_preview.png shows only coarse runtime volume proxies.

Rebuild: Blender -b --factory-startup -P
assets/maps/showhome_v3/extension/build_organic_planter.py -- --render
LOD1 retains the original curve and seat slats, with smooth wall courses.
''',encoding='utf8')
    if '--render' in sys.argv:renders(entry)
    print('ORGANIC_PLANTER_READY',json.dumps({**result,**extra}),flush=True)

if __name__=='__main__':main()
