"""Original reusable communal playground, bench and unplanted raised bed.

Blender -b --factory-startup -P extension/build_communal_props.py -- --render
Only these three new ids/assets are written; the existing office stairs are read-only.
"""
import sys, math, json, hashlib
from pathlib import Path
import bpy, bmesh
from mathutils import Vector, Matrix

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import common as C
import build_library as LIB
from gltf_shared import read

IDS=('playground_set','garden_bench','raised_green_bed')
FACES=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
M={}

def materials():
    global M
    M={
        'teal':C.material('CommunalMutedTealSteel','metal_heavy',None,(.22,.49,.43),rough=.78,metal=.02),
        'cream':C.material('CommunalCreamSteel','metal_heavy',None,(.84,.80,.66),rough=.8,metal=.02),
        'steel':C.material('CommunalChainSteel','metal_heavy','metal_scaffold_tube',(.75,.79,.79),metal=.8),
        'slide':C.material('CommunalTealSheet','sheet_metal',None,(.22,.49,.43),rough=.68,metal=.03),
        'wood':C.material('CommunalWarmTimber','wood_thin','timber_pallets',(1,.86,.69)),
        'posts':C.material('CommunalStructuralTimber','wood_thick','timber_pallets',(1,.86,.69)),
        'rubber':C.material('CommunalRubber','plastic',None,(.028,.034,.032),rough=.92),
        'concrete':C.material('CommunalConcrete','concrete','concrete_smooth',(1,.98,.91)),
        'soil':C.material('CommunalGardenSoil','soil','garden_soil',(.88,.91,.80)),
    }
    for name in ('teal','cream','slide'):
        M[name]['surface']='flat painted coating; no photographic grain or new image'
        M[name]['height_range_m']=0.0

def member(name,vs,material,root,bevel=.003,collision=True,walkable=True):
    ob=C.mesh(name,vs,FACES,M[material],root)
    ob['lod1_mesh']=json.dumps(dict(vertices=vs,faces=FACES),separators=(',',':'))
    if bevel:
        bm=bmesh.new();bm.from_mesh(ob.data)
        bmesh.ops.bevel(bm,geom=list(bm.edges),offset=bevel,segments=1,affect='EDGES',clamp_overlap=True)
        bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(ob.data);bm.free()
        for layer in list(ob.data.uv_layers):ob.data.uv_layers.remove(layer)
        C.uv(ob,M[material].get('repeat_m',1))
    else:
        for loop in ob.data.uv_layers[0].data:loop.uv/=M[material].get('repeat_m',1)
    C.bc.shade_smooth(ob,35);ob['part']=material
    if collision:
        co=C.col_mesh(name,vs,FACES,M[material]['phys'],walkable=walkable,parent=root);ob['collision']=co.name
    return ob

def box(name,lo,hi,material,root,bevel=.003,collision=True,walkable=True):
    x,y,z=lo;a,b,c=hi
    vs=[(x,y,z),(a,y,z),(a,b,z),(x,b,z),(x,y,c),(a,y,c),(a,b,c),(x,b,c)]
    return member(name,vs,material,root,min(bevel,min(hi[k]-lo[k] for k in range(3))*.20),collision,walkable)

def beam_vertices(a,b,width,depth):
    a,b=Vector(a),Vector(b);direction=(b-a).normalized();centre=(a+b)/2;length=(b-a).length
    side=direction.cross(Vector((0,0,1)))
    if side.length<.001:side=Vector((1,0,0))
    side.normalize();vertical=direction.cross(side).normalized()
    return [tuple(centre+side*(x*width/2)+vertical*(y*depth/2)+direction*(z*length/2)) for x,y,z in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]

def beam(name,a,b,width,depth,material,root,collision=True,walkable=False):
    return member(name,beam_vertices(a,b,width,depth),material,root,min(.004,min(width,depth)*.15),collision,walkable)

def chain(name,x,y,root):
    # Thirteen alternating faceted oval steel links, static and original.
    vs=[];fs=[]
    for link in range(13):
        centre=Vector((x,y,.66+link*.15));normal=Vector((0,1,0)) if link%2==0 else Vector((1,0,0))
        horizontal=Vector((1,0,0)) if link%2==0 else Vector((0,1,0))
        start=len(vs)
        for k in range(6):
            angle=2*math.pi*k/6
            p=centre+horizontal*(.031*math.cos(angle))+Vector((0,0,.092*math.sin(angle)))
            tangent=horizontal*(-.031*math.sin(angle))+Vector((0,0,.092*math.cos(angle)))
            radial=tangent.normalized().cross(normal).normalized()
            for j in range(4):
                theta=2*math.pi*j/4;vs.append(tuple(p+(radial*math.cos(theta)+normal*math.sin(theta))*.009))
        for k in range(6):
            for j in range(4):fs.append((start+k*4+j,start+((k+1)%6)*4+j,start+((k+1)%6)*4+(j+1)%4,start+k*4+(j+1)%4))
    ob=C.mesh(name,vs,fs,M['steel'],root);C.bc.shade_smooth(ob,30)
    # At distance a tension line replaces link holes; the four chains retain
    # their roots and actual suspension length in both exports.
    low=beam_vertices((x,y,.55),(x,y,2.58),.022,.022)
    ob['lod1_mesh']=json.dumps(dict(vertices=low,faces=FACES),separators=(',',':'))
    co=C.col_mesh(name+'_TensionLine',beam_vertices((x,y,.55),(x,y,2.58),.018,.018),FACES,'metal_heavy',walkable=False,parent=root)
    ob['collision']=co.name;ob['collision_note']='18 mm static tension-line proxy for linked chain; open ring holes remain visual'
    return ob

def playground(root):
    root['nominal_footprint_m']=[8,6];root['static_equipment']=True
    # Broad 8 x 6 m footprint; independently supported swing and slide.
    for x in (-3.80,-.30):
        for y in (-1.3,1.3):
            beam('Swing_AFrameLeg',(x,y,.07),(x,0,2.59),.11,.11,'teal',root)
            box('Swing_GroundShoe',(x-.20,y-.15,0),(x+.20,y+.15,.07),'cream',root)
        beam('Swing_EndTie',(x,-.77,1.02),(x,.77,1.02),.075,.075,'cream',root)
    box('Swing_TopBeam',(-3.98,-.075,2.55),(-.12,.075,2.70),'teal',root)
    for centre in (-2.95,-1.15):
        box('Swing_RubberSeat',(centre-.34,-.19,.46),(centre+.34,.19,.54),'rubber',root,bevel=.012)
        for x in (centre-.25,centre+.25):
            chain('Swing_StaticChain',x,0,root)
            box('Swing_SeatHanger',(x-.023,-.045,.52),(x+.023,.045,.62),'cream',root)
            box('Swing_TopHanger',(x-.032,-.042,2.51),(x+.032,.042,2.59),'cream',root)
    # Chunky timber platform, 1.25 m above ground, with cream steel guards.
    for x in (2.60,3.80):
        for y in (.50,1.50):
            box('Slide_TowerPost',(x-.055,y-.055,.07),(x+.055,y+.055,1.92),'teal',root)
            box('Slide_TowerShoe',(x-.20,y-.17,0),(x+.20,y+.17,.07),'cream',root)
    for i in range(7):
        y=.40+i*1.2/7
        box('Slide_PlatformBoard',(2.50,y,1.20),(3.90,y+1.2/7-.006,1.25),'wood',root)
    for x in (2.60,3.80):
        beam('Slide_PlatformStringer',(x,.4,1.16),(x,1.6,1.16),.08,.08,'teal',root)
        for h in (1.58,1.92):beam('Slide_PlatformGuard',(x,.5,h),(x,1.5,h),.045,.045,'cream',root)
    for x0,x1 in ((2.60,2.76),(3.64,3.80)):
        for h in (1.58,1.92):beam('Slide_RearEntryGuard',(x0,1.5,h),(x1,1.5,h),.045,.045,'cream',root)
    # A real closed 10 mm slide sheet with independent shallow side lips.
    x0,x1=2.77,3.63;y0,y1=-2.80,.40;z0,z1=.16,1.25
    vs=[(x0,y0,z0-.01),(x1,y0,z0-.01),(x1,y1,z1-.01),(x0,y1,z1-.01),
        (x0,y0,z0),(x1,y0,z0),(x1,y1,z1),(x0,y1,z1)]
    member('Slide_ActualRamp',vs,'slide',root,.001,walkable=True)
    incline=Vector((0,y1-y0,z1-z0)).normalized()
    upper_normal=Vector((0,-incline.z,incline.y))
    for x,flange_x in ((2.745,2.758),(3.655,3.642)):
        # An actual folded 8 mm L section: two separate closed sheet prisms
        # retain the open space around the fold, rather than a filled bar hull.
        a=Vector((x,y0,z0))+upper_normal*.071
        b=Vector((x,y1,z1))+upper_normal*.071
        beam('Slide_SideLipSheet',a,b,.008,.15,'slide',root,walkable=False)
        a=Vector((flange_x,y0,z0))-upper_normal*.004
        b=Vector((flange_x,y1,z1))-upper_normal*.004
        beam('Slide_SideLipFold',a,b,.036,.008,'slide',root,walkable=False)
        beam('Slide_LowRail',(x,y0,z0+.16),(x,y1,z1+.16),.035,.035,'cream',root)
    box('Slide_ExitFoot',(2.70,-3.0,0),(3.70,-2.62,.15),'cream',root)
    for x in (2.89,3.51):
        beam('Slide_LadderStringer',(x,2.82,.11),(x,1.58,1.20),.07,.11,'teal',root)
        box('Slide_LadderFoot',(x-.12,2.68,0),(x+.12,3.0,.07),'cream',root)
        beam('Slide_LadderHandRail',(x,2.78,.68),(x,1.48,1.92),.045,.045,'cream',root)
        for y in (2.78,2.16,1.58):
            lower=.11+(2.82-y)/1.24*1.09
            upper=.68+(2.78-y)/1.30*1.24
            beam('Slide_LadderRailPost',(x,y,lower),(x,y,upper),.045,.045,'cream',root)
    for i in range(6):
        y=2.78-i*.20;z=.13+i*.20
        box('Slide_LadderStep',(2.86,y-.105,z),(3.54,y+.105,z+.045),'wood',root)
    root['slide_platform_height_m']=1.25;root['slide_clear_width_m']=.86
    root['swing_seat_count']=2;root['swing_seat_height_m']=.54
    root['static_chain_links']=13

def bench(root):
    root['nominal_size_m']=[1.8,.70,.9]
    for x in (-.65,.65):
        for y in (-.235,.235):
            box('Bench_Leg',(x-.035,y-.035,.025),(x+.035,y+.035,.44),'teal',root)
            box('Bench_Foot',(x-.085,y-.075,0),(x+.085,y+.075,.025),'teal',root)
        beam('Bench_SeatSupport',(x,-.28,.405),(x,.29,.405),.055,.07,'teal',root)
        beam('Bench_BackSupport',(x,.245,.38),(x,.37,.87),.05,.05,'teal',root)
    for i in range(5):
        y=-.27+i*.108
        box('Bench_SeatSlat',(-.90,y,.44),(.90,y+.096,.48),'wood',root)
    for z in (.57,.70,.83):
        # The back follows the lean of the metal support, not a vertical slab.
        y=.245+(z-.38)*(.125/.49)
        vs=[(-.90,y-.019,z-.048),(.90,y-.019,z-.048),(.90,y+.009,z+.048),(-.90,y+.009,z+.048),
            (-.90,y+.016,z-.048),(.90,y+.016,z-.048),(.90,y+.044,z+.048),(-.90,y+.044,z+.048)]
        member('Bench_BackSlat',vs,'wood',root,.002)
    for x in (-.78,.78):
        box('Bench_ArmPost',(x-.025,-.23,.47),(x+.025,-.18,.65),'teal',root)
        box('Bench_Armrest',(x-.045,-.27,.64),(x+.045,.32,.68),'wood',root)
    root['seat_top_m']=.48;root['seating_length_m']=1.8

def bed(root):
    root['nominal_size_m']=[4,2,.45];root['greenery']='root places separate GREENFOL volume; no foliage baked into prop'
    for y in (-.93,.93):box('Bed_ConcreteWall',(-2,y-.07,0),(2,y+.07,.405),'concrete',root,bevel=.007)
    for x in (-1.93,1.93):box('Bed_ConcreteEnd',(x-.07,-.86,0),(x+.07,.86,.405),'concrete',root,bevel=.007)
    for y in (-.93,.93):box('Bed_TimberRim',(-2,y-.07,.405),(2,y+.07,.45),'wood',root)
    for x in (-1.93,1.93):box('Bed_TimberEnd',(x-.07,-.86,.405),(x+.07,.86,.45),'wood',root)
    box('Bed_SoilInset',(-1.855,-.855,0),(1.855,.855,.355),'soil',root,bevel=.002)
    root['soil_top_m']=.355;root['foliage_local_min']=[-1.80,-.80,.36];root['foliage_local_max']=[1.80,.80,.85]

def inspect_prop(pid,entry):
    dest=LIB.PROPS/'garden'/pid
    rows=json.loads((dest/'collision.json').read_text())['volumes']
    output=dict(passed=True,phys_ok=True,uv_ok=True,convex_collision_ok=True,
                collision_volumes=len(rows),minimum_collision_thickness_m=min(r['thickness_m'] for r in rows))
    images=set()
    for suffix in ('','_lod1'):
        path=dest/(pid+suffix+'.glb');j,buf=read(path)
        assert all(m.get('extras',{}).get('phys') in C.PHYS for m in j['materials'])
        assert all('TEXCOORD_0' in p['attributes'] for m in j['meshes'] for p in m['primitives'])
        assert all('uri' in im and 'bufferView' not in im and (path.parent/im['uri']).is_file() for im in j.get('images',[]))
        images.update(im['uri'] for im in j.get('images',[]))
        output['lod1_triangles' if suffix else 'lod0_triangles']=sum(j['accessors'][p['indices']]['count']//3 for m in j['meshes'] for p in m['primitives'])
    for row in rows:
        # Check serialized convex half-spaces, not just authoring mesh topology.
        assert len(row['planes'])>=4 and row['thickness_m']>=.005
        if row['phys']=='sheet_metal':assert row['thickness_m']<=.0102,('sheet skin exceeds 10 mm',row['name'],row['thickness_m'])
        for point in row['vertices']:
            assert all(sum(p[k]*point[k] for k in range(3))<=p[3]+.0001 for p in row['planes'])
    output.update(external_images_ok=True,external_images=sorted(images),no_new_images=True,
                  base_centre_pivot_ok=True,footprint_m=entry['size_m'][:2],height_m=entry['size_m'][2])
    output['sheet_metal_max_m']=max((r['thickness_m'] for r in rows if r['phys']=='sheet_metal'),default=0)
    C.write(dest/'QA.json',output)
    return output

def recenter(root):
    obs=C.visuals();mn,mx=C.bc.world_bounds(obs)
    offset=Vector((-(mn.x+mx.x)/2,-(mn.y+mx.y)/2,-mn.z))
    for ob in list(root.children):ob.location+=offset
    bpy.context.view_layer.update();mn,mx=C.bc.world_bounds(obs)
    assert abs(mn.z)<1e-6 and abs(mn.x+mx.x)<1e-6 and abs(mn.y+mx.y)<1e-6
    root['pivot']='base bounding-box centre, Z=0';root['authoring_recenter_m']=list(offset)
    return offset

def combined_render():
    C.bc.reset_scene()
    for pid,position in zip(IDS,((-.15,1.10,0),(-4.3,-4.1,0),(1.6,-4.2,0))):
        before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(LIB.PROPS/'garden'/pid/(pid+'.glb')))
        for ob in set(bpy.data.objects)-before:
            if ob.parent is None:ob.location+=Vector(position)
    ground=C.material('CommunalPreviewGround','grass',None,(.21,.28,.20),rough=.95)
    C.box('Preview_Ground',(17,15,.08),(0,0,-.04),ground,bevel=0)
    cam=C.stage();sc=bpy.context.scene;sc.cycles.device='CPU';sc.cycles.samples=20
    sc.render.resolution_x=1280;sc.render.resolution_y=960
    C.render(cam,LIB.PROPS/'garden/playground_set/renders/communal_set.png',(13,-18,12),(0,-.6,.9),16.8)

def main():
    only=set(sys.argv[sys.argv.index('--only')+1].split(',')) if '--only' in sys.argv else set(IDS)
    assert only and only<=set(IDS),('unknown communal prop id',only)
    stair_file=LIB.PROPS/'worksite/site_office_stairs/site_office_stairs.glb'
    stair_hash=hashlib.sha256(stair_file.read_bytes()).hexdigest() if stair_file.exists() else None
    results=[]
    for pid,fn in zip(IDS,(playground,bench,bed)):
        if pid not in only:continue
        root=LIB.begin(pid,'garden');materials();fn(root);offset=recenter(root)
        # Bed foliage hints follow its base-centre authoring adjustment.
        if pid=='raised_green_bed':
            root['foliage_local_min']=[a+b for a,b in zip(root['foliage_local_min'],offset)]
            root['foliage_local_max']=[a+b for a,b in zip(root['foliage_local_max'],offset)]
        LIB.save_prop(root,pid,'garden','original procedural communal kit; extension/build_communal_props.py')
        entry=LIB.CATALOG[-1];entry.update(pivot='base-centre at Z=0',front='design -Y',original_geometry=True,
            source_builder='maps/showhome_v3/extension/build_communal_props.py')
        if pid=='raised_green_bed':entry.update(soil_top_m=.355,foliage_local_min=list(root['foliage_local_min']),foliage_local_max=list(root['foliage_local_max']),foliage_baked=False)
        C.write(LIB.PROPS/'garden'/pid/'metadata.json',entry)
        result=inspect_prop(pid,entry);results.append(dict(id=pid,**result))
        notes=(f'Original reusable {pid}. Metres/Z-up/front -Y; base-bounding-box-centre pivot at Z=0.\n'
               'Rebuild with assets/maps/showhome_v3/extension/build_communal_props.py -- --render.\n'
               'Original clean low-poly geometry, shared existing painted v2 timber/metal/concrete/soil images.\n'
               'Teal and cream metal use flat paint coats for clean colour silhouettes; no new texture image.\n'
               'UVs, physical material extras and height metadata preserved. Exact planar LOD1 members.\n'
               'Closed convex collision follows actual boards, frames, skin thickness and soil inset.\n')
        if pid=='playground_set':notes+=('Static two-seat swing: thick 80 mm rubber seats, alternating faceted oval metal links.\n'
            'Four chains use closed 18 mm tension-line collision proxies; visual ring holes remain open.\n'
            'Independent small slide: actual closed 10 mm ramp, timber play platform, folded 8 mm L-section side lips, guards and six steps.\n'
            'Each side lip has separate closed wall and fold-flange collision; open space around the fold is preserved.\n'
            'Muted teal and cream paint; no brands, photographic textures, AI meshes or new images.\n')
        if pid=='raised_green_bed':notes+=('4 x 2 m concrete walls, 45 mm timber rim, recessed soil top at 0.355 m.\n'
            'No leaves or grass mesh: root places a separate GREENFOL volume using the local metadata bounds.\n')
        (LIB.PROPS/'garden'/pid/'NOTES.md').write_text(notes,encoding='utf8')
    # Load latest files and replace only ids built during this invocation.
    new={e['id']:e for e in LIB.CATALOG}
    for path in (LIB.PROPS/'catalog.json',LIB.HERE/'library_manifest.json'):
        data=json.loads(path.read_text());data['props']=[e for e in data['props'] if e['id'] not in new]+list(new.values());C.write(path,data)
    if '--render' in sys.argv:combined_render()
    if stair_hash:assert stair_hash==hashlib.sha256(stair_file.read_bytes()).hexdigest(), 'existing stairs changed'
    print('COMMUNAL_PROPS_READY',json.dumps([{k:v for k,v in r.items() if k!='external_images'} for r in results]),flush=True)

if __name__=='__main__':main()
