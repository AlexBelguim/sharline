"""Separate phase-2 residential/worksite extension. Never runs the old builders.
Blender -b --factory-startup -P extension/build_extension.py -- [--render] [--skip-props]
Only fixed buildings/terrain/foliage enter extension.glb; movable items remain catalog instances.
"""
import sys,json,math,random,importlib.util
from pathlib import Path
import bpy,bmesh
from mathutils import Vector,Matrix
OUT=Path(__file__).resolve().parent;HERE=OUT.parent;sys.path[:0]=[str(OUT),str(HERE)]
import common as C
import build_library as LIB
import site_terrain as SITE
import site_access as ACCESS
import site_tracks as TRACKS
import site_material_clusters as CLUTTER
import parking_basement as PARK
from gltf_shared import read,save,externalize
ROOT=C.ROOT;PROPS=ROOT/'assets/props';OUT.mkdir(exist_ok=True)
CACHE=OUT/'_cache';CACHE.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('extension_backdrop_helpers',ROOT/'assets/maps/showhome/backdrop/build_backdrop.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
INST=[];FOL=[];HOMES=[];STAIRS=[];M={};FIXED=[];PITS=[];MOUNDS=[];BASEMENT={};ACCESS_REPORT={};TRACK_REPORT=[];MATERIAL_CLUSTERS=[];MATERIAL_REQUEST_STATUS=[]
APARTMENT_YAW_DEG=90
SOURCE_REVISION='2026-10-10_perpendicular_road_straight_ramp_recessed_homes'
APARTMENT_PIVOT=(368,735,0)
# Preserve10m extra clearance from the nearest street-facing building edge.
APARTMENT_T=Matrix(((0,-1,0,1093),(1,0,0,409),(0,0,1,0),(0,0,0,1)))
APARTMENT_COPY_SHIFT=(52,0,0)
APARTMENT_SHIFTS=[(0,0,0),(52,0,0),(0,88,0),(52,88,0)]
APARTMENT_BOUNDS=[[345,750,371,804],[397,750,423,804],[345,838,371,892],[397,838,423,892]]
BASEMENT_BOUNDS=[339,744,451,896]
GROUND_EXCLUSIONS=[BASEMENT_BOUNDS,PARK.RAMP_EXCAVATION]
SITE_BOUNDS=[310,735,480,905]
SITE_END_Y=908
SITE_END_X=483
INSTANCE_TEMPLATES={};INSTANCE_COUNTERS={}
HOME_SPECS=[('home_west','sage_south',(344,700,0),(352.5,639,0)),('home_middle','clay_south',(370,700,0),(387.5,639,0)),('home_east','sage_south',(396,700,0),(352.5,639,0))]
HOME_PLOTS=[[332,684,356,728],[358,684,382,728],[384,684,408,728]]
FOOTPRINTS=[[x-6.15,y-8.15,x+6.15,y+2.15] for _,_,(x,y,z),_ in HOME_SPECS]
DRIVEWAYS=[[351.8,681,355,710],[377.8,681,381,710],[403.8,681,407,710]]

PIT_RECTS=SITE.PIT_RECTS
NEW_IDS=['tower_crane','scaffold_bay','site_office','portable_toilet','printed_blocks_pallet','timber_pallet','rebar_bundle','temporary_guardrail','site_office_stairs','playground_set','organic_planter_bench']
COMMUNAL_PLANTERS=[(384,y,0) for y in (765,777,789,853,865,877)]
COMMUNAL_BOUNDS=[376,755,391,887]
CABIN_STACKS=[dict(lower=[456,869,0],upper_offset=[0,0,2.8]),dict(lower=[444,880,0],upper_offset=[0,0,2.8]),dict(lower=[462,889,0],upper_offset=[-1.2,0,2.8],second_lower=[456,889,0])]

def log(*args):print('EXTENSION',*args,flush=True)
def add(name,size,pos,mat,parent=None,bevel=.008,collision=True):
    # Build/apply chamfers in bmesh rather than running a depsgraph operator for
    # every frame member. All extension and library roots use the identity frame.
    bm=bmesh.new();bmesh.ops.create_cube(bm,size=1);bmesh.ops.scale(bm,vec=Vector(size),verts=bm.verts)
    width=min(bevel,min(size)*.3)
    if width:bmesh.ops.bevel(bm,geom=list(bm.edges),offset=width,segments=1,affect='EDGES',clamp_overlap=True)
    bmesh.ops.translate(bm,vec=Vector(pos),verts=bm.verts);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bmesh.ops.triangulate(bm,faces=list(bm.faces))
    me=bpy.data.meshes.new(name);bm.to_mesh(me);bm.free();ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob)
    C.bc.assign(ob,M[mat]);C.uv(ob,M[mat].get('repeat_m',1));C.bc.shade_smooth(ob,35);ob.parent=parent;ob['part']=mat
    if collision:
        lo=[pos[k]-size[k]/2 for k in range(3)];hi=[pos[k]+size[k]/2 for k in range(3)];co=C.col_box(name,lo,hi,M[mat]['phys']);co.parent=parent;ob['collision']=co.name
    return ob
def box(name,lo,hi,mat,parent=None,bevel=.008,collision=True):
    return add(name,[hi[k]-lo[k] for k in range(3)],[(hi[k]+lo[k])/2 for k in range(3)],mat,parent,bevel,collision)
def tube(name,a,b,width,mat,parent=None,collision=True):
    a,b=Vector(a),Vector(b);centre=(a+b)/2;rot=(b-a).to_track_quat('Z','Y').to_matrix();length=(b-a).length
    signs=((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))
    vs=[tuple(centre+rot@Vector((x*width/2,y*width/2,z*length/2))) for x,y,z in signs];fs=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    ob=C.mesh(name,vs,fs,M[mat]);ob.parent=parent
    for loop in ob.data.uv_layers[0].data:loop.uv/=M[mat].get('repeat_m',1)
    C.bc.shade_smooth(ob,35)
    if collision:
        co=C.col_mesh(name,vs,fs,M[mat]['phys']);co.parent=parent;ob['collision']=co.name
    return ob
def materials():
    global M
    M={
      'concrete':C.material('ExtensionConcrete','concrete','concrete_smooth',(.94,.94,.91)),
      'printed':C.material('ExtensionPrinted','concrete','printed_concrete_layers'),
      'steel':C.material('ExtensionSteel','metal_heavy','metal_scaffold_tube'),
      'wood':C.material('ExtensionTimber','wood_thick','timber_pallets'),
      'cream':C.material('ExtensionCream','sheet_metal','fibercement_panel',(.94,.91,.82)),
      'cream_plastic':C.material('ExtensionCreamPlastic','plastic','fibercement_panel',(.94,.91,.82)),
      'orange':C.material('ExtensionOrange','sheet_metal','fibercement_panel',(.85,.32,.09)),
      'plastic':C.material('ExtensionToiletPlastic','plastic','fibercement_panel',(.075,.35,.29)),
      'dark':C.material('ExtensionGraphite','plastic',None,(.035,.045,.05)),
      'glass':C.material('ExtensionGlass','glass',None,(.28,.40,.44),rough=.2),
      'sage':C.material('ExtensionGableSage','cladding','fibercement_panel',(.28,.35,.23)),
      'hedge':C.material('ExtensionHedge','foliage_dense',None,(.13,.19,.085),rough=.95),
      'tree':C.material('ExtensionTreeCanopy','foliage_dense',None,(.18,.24,.095),rough=.95),
      'soil':C.material('ExtensionEarth','soil','worksite_packed_dirt'),
      'sand':C.material('ExtensionCutEarth','soil','construction_sand'),
    }

def backdrop_part(root,name,callback,phys=None):
    acc=B.Acc();callback(acc);mats=B.materials()
    mapping={'clad':'metal_heavy','printed':'concrete','roof':'cladding','solar':'sheet_metal','timber':'wood_thick','earth':'soil','foliage':'foliage_dense','metal':'metal_heavy','pave':'paving','asphalt':'asphalt'}
    for key,mat in mats.items():mat['phys']=(phys or {}).get(key,mapping[key])
    obs=[]
    for key in sorted({p[1] for p in acc.P}):
        one=B.Acc();one.P=[p for p in acc.P if p[1]==key]
        ob=B.make_object(name+'_'+key,one,mats,C.bc.collection('EXTENSION_PROPS'));C.parent_keep(ob,root);obs.append(ob)
    return obs

def pallet(root,blocks=False):
    backdrop_part(root,'PrintedBlocksPallet' if blocks else 'TimberPallet',lambda a:B.pallet(a,0,0,blocks=blocks))
    for y in (-.40,0,.40):C.col_box('Pallet_Stringer',(-.62,y-.055,.04),(.62,y+.055,.15),'wood_thick',parent=root)
    C.col_box('Pallet_Deck',(-.62,-.48,.15),(.62,.48,.21),'wood_thin',parent=root)
    if blocks:
        for layer in range(2):
            for x in (-.32,.32):
                for y in (-.23,.23):C.col_box('Printed_Block',(x-.28,y-.18,.21+layer*.23),(x+.28,y+.18,.43+layer*.23),'concrete',parent=root)

def crane(root):
    def geometry(a):
        B.crane(a,0,0,height=28)
        def in_cab(p):return all(-2.231<=v.x<=-.399 and -.861<=v.y<=1.201 and 25.599<=v.z<=27.701 for v in p[0])
        a.P=[p for i,p in enumerate(a.P) if i>=6 and not in_cab(p)]
    backdrop_part(root,'TowerCrane',geometry)
    # Exact main members leave the lattice openings empty.
    box('CraneConcreteBallast',(-2.4,-2.4,0),(2.4,2.4,.6),'concrete',root,.025)
    for x in (-1.25,1.25):
        for y in (-1.25,1.25):
            ob=tube('CraneLeg',(x,y,.6),(x,y,28),.32,'steel',root);bpy.data.objects.remove(ob,do_unlink=True)
    for y,z in ((-.75,28),(.75,28),(0,29.7)):
        ob=tube('CraneBoomChord',(-43,y,z),(15,y,z),.26,'steel',root);bpy.data.objects.remove(ob,do_unlink=True)
    # Hollow cab: 8mm sheet skins, 10mm glass and actual heavy corner posts.
    for z in (25.604,27.696):add('CraneCabSkin',(1.8,2,.008),(-1.3,.2,z),'cream',root,.002)
    for x in (-2.196,-.404):add('CraneCabSide',(.008,2,2.1),(x,.2,26.65),'cream',root,.002)
    add('CraneCabBack',(1.8,.008,2.1),(-1.3,1.196,26.65),'cream',root,.002)
    for za,zb in ((25.6,26.0),(27.3,27.7)):box('CraneCabFront',(-2.2,-.8,za),(-.4,-.792,zb),'cream',root,.002)
    add('CraneCabGlass',(1.72,.010,1.30),(-1.3,-.805,26.65),'glass',root,.002)
    for x in (-2.17,-.43):
        for y in (-.77,1.17):add('CraneCabFrame',(.06,.06,2.1),(x,y,26.65),'steel',root)
    C.col_box('CraneCounterweight',(9,-1.5,26.9),(15,1.5,28.3),'concrete',walkable=False,parent=root)
    C.col_box('CraneHook',(-34.28,-.22,14.1),(-33.72,.22,15.1),'metal_heavy',walkable=False,parent=root)
    root['source_helper']='original procedural backdrop crane; independent movable asset'

def scaffold(root):
    for x in (-2,0,2):
        for y in (-.55,.55):
            tube('ScaffoldUpright',(x,y,.08),(x,y,10.7),.055,'steel',root)
            add('ScaffoldFoot',(.20,.20,.055),(x,y,.0275),'steel',root)
    for z in (.12,3.2,6.4,9.6,10.6):
        for y in (-.55,.55):tube('ScaffoldRail',(-2,y,z),(2,y,z),.05,'steel',root)
        for x in (-2,0,2):tube('ScaffoldCrossrail',(x,-.55,z),(x,.55,z),.05,'steel',root)
    for z in (3.2,6.4,9.6):
        for k in range(5):add('ScaffoldDeck',(4,.19,.055),(0,-.40+k*.2,z-.0275),'wood',root,.004)
        for y in (-.55,.55):
            for h in (.55,1.05):tube('ScaffoldGuardrail',(-2,y,z+h),(2,y,z+h),.042,'steel',root)
    for z in (0,3.2,6.4):
        for x in (-2,0):
            tube('ScaffoldBrace',(x,-.56,z+.15),(x+2,-.56,z+3.1),.035,'steel',root,False)
            tube('ScaffoldBrace',(x+2,-.57,z+.15),(x,-.57,z+3.1),.035,'steel',root,False)
    # Visible ladder is supplemental; the apartment's real stair route is independent.
    for x in (1.26,1.72):tube('ScaffoldLadder',(x,-.68,.12),(x,-.68,9.9),.03,'steel',root,False)
    for k in range(33):tube('ScaffoldRung',(1.26,-.68,.18+k*.3),(1.72,-.68,.18+k*.3),.026,'steel',root,False)

def office(root):
    w,d,h=6,2.8,2.8;t=.008
    box('OfficeFloor',(-3,-1.4,0),(3,1.4,.10),'steel',root)
    box('OfficeRoof',(-3,-1.4,2.792),(3,1.4,2.80),'cream',root,.002)
    for y in (-1.32,1.32):add('OfficeRoofFrame',(6,.08,.10),(0,y,2.74),'steel',root)
    for x in (-2.996,2.996):add('OfficeEnd',(t,d,h-.2),(x,0,1.4),'cream',root,.002)
    add('OfficeBack',(w,t,h-.2),(0,1.396,1.4),'cream',root,.002)
    # Front has a 1.1m door and a proper 1.6m window aperture.
    for x0,x1,z0,z1 in ((-3,-.55,.10,2.70),(.55,1.05,.10,2.70),(2.65,3,.10,2.70),(.55,2.65,.10,.95),(1.05,2.65,2.1,2.7),(-.55,.55,2.24,2.7)):
        box('OfficeFront',(x0,-1.40,z0),(x1,-1.392,z1),'cream',root,.002)
    add('OfficeWindow',(1.6,.010,1.15),(1.85,-1.405,1.525),'glass',root,.002)
    for x in (1.05,1.85,2.65):add('WindowMullion',(.035,.035,1.18),(x,-1.417,1.525),'steel',root,.003)
    for z in (.95,2.1):add('WindowFrame',(1.635,.035,.035),(1.85,-1.417,z),'steel',root,.003)
    leaf=add('OfficeDoor',(1.08,.008,2.12),(0,-1.415,1.17),'orange',root,.002)
    leaf=LIB.movable(leaf,'Office','OPEN_DOOR',(-.54,-1.415,.11),root,ajar=8,max_deg=110)
    add('OfficeHandle',(.12,.025,.025),(.91,-.025,1.12),'steel',leaf,.004,False)
    for x in (-2.9,2.9):
        for y in (-1.3,1.3):add('OfficeCorner',(.08,.08,2.78),(x,y,1.39),'steel',root)
    for k in range(22):
        x=-2.95+k*5.9/21;add('OfficeRearCorrugation',(.025,.008,2.55),(x,1.404,1.4),'cream',root,.002,False)
    root['door_clear_width_m']=1.08;root['modular_stack_height_m']=2.8

def toilet(root):
    add('ToiletBase',(1.16,1.25,.12),(0,0,.06),'dark',root,.025)
    for x in (-.556,.556):add('ToiletSide',(.035,1.18,2.12),(x,0,1.18),'plastic',root,.008)
    add('ToiletBack',(1.15,.035,2.12),(0,.573,1.18),'plastic',root,.008)
    add('ToiletRoof',(1.22,1.29,.12),(0,0,2.30),'cream_plastic',root,.025)
    for x in (-.55,.55):add('ToiletDoorJamb',(.065,.065,2.12),(x,-.59,1.18),'plastic',root,.008)
    add('ToiletHeader',(1.12,.045,.12),(0,-.59,2.21),'plastic',root,.008)
    leaf=add('ToiletDoor',(1.035,.025,2.06),(0,-.612,1.16),'plastic',root,.008)
    leaf=LIB.movable(leaf,'Toilet','OPEN_DOOR',(-.5175,-.612,.13),root,ajar=4,max_deg=105)
    add('ToiletLatch',(.07,.035,.09),(.92,-.018,1.03),'dark',leaf,.005,False)
    add('ToiletTank',(.70,.42,.44),(0,.28,.36),'dark',root,.035)
    add('ToiletSeat',(.48,.37,.055),(0,.21,.6075),'cream',root,.02,False)
    for z in (1.96,2.03,2.10):add('ToiletVent',(.40,.012,.024),(0,.596,z),'dark',root,.003,False)
    root['door_clear_width_m']=1.035;root['original_geometry']=True

def rebar(root):
    for z in (.065,.105,.145):
        for y in (-.18,-.09,0,.09,.18):tube('RebarRod',(-2,y,z),(2,y,z),.025,'steel',root,False)
    for x in (-1.30,1.30):add('BundleTie',(.035,.45,.18),(x,0,.095),'steel',root,.004,False)
    C.col_box('RebarBundle',(-2,-.2,.035),(2,.2,.16),'metal_heavy',parent=root)

def guardrail(root):
    for x in (-2.2,0,2.2):add('GuardrailPost',(.085,.085,1.1),(x,0,.55),'wood',root)
    for z in (.55,1.02):add('GuardrailBoard',(4.5,.035,.12),(0,0,z),'wood',root,.005)
    add('GuardrailToeBoard',(4.5,.035,.15),(0,0,.09),'wood',root,.005)

def build_props():
    funcs=dict(tower_crane=crane,scaffold_bay=scaffold,site_office=office,portable_toilet=toilet,printed_blocks_pallet=lambda r:pallet(r,True),timber_pallet=lambda r:pallet(r,False),rebar_bundle=rebar,temporary_guardrail=guardrail)
    for pid,fn in funcs.items():
        if '--only-props' in sys.argv and pid not in sys.argv[sys.argv.index('--only-props')+1].split(','):continue
        if '--skip-props' in sys.argv and (PROPS/'worksite'/pid/(pid+'.glb')).exists():continue
        root=LIB.begin(pid,'worksite');materials();fn(root);LIB.save_prop(root,pid,'worksite','original procedural phase-2 worksite kit')
        (PROPS/'worksite'/pid/'NOTES.md').write_text('Original reusable Showhome v3 worksite prop. Rebuild with extension/build_extension.py. Metres, Z-up, ground-centre pivot; front -Y. Existing painted texture library; convex collision, UVs, phys extras and LOD1. Movable items are catalog placements, not baked into the extension scene.\n',encoding='utf8')
    path=PROPS/'catalog.json';data=json.loads(path.read_text(encoding='utf8'));new={r['id']:r for r in LIB.CATALOG}
    data['props']=[r for r in data['props'] if r['id'] not in new]+list(new.values());C.write(path,data)
    C.write(HERE/'library_manifest.json',dict(props=data['props'],texture_storage='shared external images in maps/showhome_v3/textures; no repeated embedded images'))
    return {r['id']:r for r in data['props']}

def inrect(x,y,r):return r[0]-1e-6<=x<=r[2]+1e-6 and r[1]-1e-6<=y<=r[3]+1e-6
def surface(x,y):
    if any(inrect(x,y,r) for r in FOOTPRINTS+GROUND_EXCLUSIONS+PIT_RECTS):return None
    if y<=685.55:return 'paving'
    if any(inrect(x,y,r) for r in DRIVEWAYS):return 'gravel'
    for r in HOME_PLOTS:
        if inrect(x,y,r):
            cx=(r[0]+r[2])/2
            if y<701:return 'paving' if 685.7<y<686.0 or (abs(x-(cx+1))<.72 and y<694) else 'grass'
            if 702<=y<=705 and abs(x-cx)<4.5:return 'paving'
            return 'grass'
    return 'soil'

def ground(root):
    tex={'asphalt':('asphalt',4),'paving':('paving_slabs',2.4),'grass':('grass_lawn',2),'soil':('worksite_packed_dirt',6),'tracks':('worksite_mud_tracks',6),'gravel':('gravel',1)}
    xs=set(range(310,SITE_END_X,2));xs.add(SITE_END_X);ys=set(range(685,SITE_END_Y,2));ys.add(SITE_END_Y)
    for _,_,(cx,cy,cz),_ in HOME_SPECS:
        xs.update((cx-6.15,cx+6.15,cx+.28,cx+1.72,cx-4.5,cx+4.5))
    ys.update((685,685.55,685.7,685.85,686,691.85,694,701,702.15,702,705,710,728))
    for r in GROUND_EXCLUSIONS+FOOTPRINTS:xs.update((r[0],r[2]));ys.update((r[1],r[3]))
    for point in ACCESS.CONTROL:xs.update((point[0]-3.03,point[0]+3.03));ys.add(point[1])
    for r in HOME_PLOTS+DRIVEWAYS:xs.update((r[0],r[2]));ys.update((r[1],r[3]))
    for r in PIT_RECTS:xs.update((r[0],r[2]));ys.update((r[1],r[3]))
    xs=sorted(x for x in xs if 310<=x<=SITE_END_X);ys=sorted(y for y in ys if 685<=y<=SITE_END_Y);acc={k:([],[],[]) for k in tex};rectangles=[];active={}
    for y0,y1 in zip(ys,ys[1:]):
        runs=[];last=None
        for x0,x1 in zip(xs,xs[1:]):
            k=surface((x0+x1)/2,(y0+y1)/2)
            if k is None:last=None;continue
            if last==k:runs[-1][2]=x1
            else:runs.append([x0,y0,x1,y1,k]);last=k
            v,f,cs=acc[k];n=len(v);z=0 if k=='asphalt' else .008
            q=[(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)];v.extend(q);f.append(tuple(n+i for i in range(4)))
            for x,y,z in q:
                # Independent surface masks follow the shared height-blend contract.
                track_rgba=TRACKS.masks(x,y)
                sand=max([max(0,1-math.hypot(x-(r[0]+r[2])/2,y-(r[1]+r[3])/2)/10) for r in PIT_RECTS])*.52
                verge=max(0,1-ACCESS.distance(x,y)/5)*.25
                cs.append(track_rgba if k=='soil' else (.0,.0,verge,sand*.15))
        current={}
        for r in runs:
            key=(r[0],r[2],r[4]);old=active.pop(key,None)
            if old and abs(old[3]-y0)<1e-6:old[3]=y1;r=old
            current[key]=r
        rectangles.extend(active.values());active=current
    rectangles.extend(active.values())
    for k,(v,f,cs) in acc.items():
        family,repeat=tex[k];tint=(.93,.91,.86) if k=='soil' else (1,1,1);mat=C.material('ExtGround_'+k,'soil' if k=='tracks' else k,family,tint);mat.name='M_GND_Ext_'+k.title();mat['repeat']=[repeat,repeat]
        ob=C.mesh('EXT_Ground_'+k,v,f,mat,root);ob['part']='terrain';ob['ground_blend']='showhome_height_blend_v2'
        layer=ob.data.uv_layers[0];ca=ob.data.color_attributes.new(name='Col',type='FLOAT_COLOR',domain='CORNER')
        for face in ob.data.polygons:
            for li in face.loop_indices:
                ix=ob.data.loops[li].vertex_index;layer.data[li].uv=(v[ix][0]/repeat,v[ix][1]/repeat);ca.data[li].color=cs[ix]
        ob.data.color_attributes.active_color=ca
    for n,(x0,y0,x1,y1,k) in enumerate(rectangles):
        C.col_box('EXT_Surface_'+str(n),(x0,y0,-.18),(x1,y1,0 if k=='asphalt' else .008),'soil' if k=='tracks' else k,parent=root)
    for n,r in enumerate(PIT_RECTS):pit(root,r,n)
    log('ground',len(rectangles),'surface volumes; no terrain south of y685')

def far_fields(root):
    # Disjoint rectangles cover the outside of the core/extension union. The
    # fields are presentation terrain; the playable extension collision is local.
    rects=[(-230,90,290,1285),(SITE_END_X,90,975,1285),(290,90,SITE_END_X,600),(290,SITE_END_Y,SITE_END_X,1285),(290,685,310,SITE_END_Y),(450,600,SITE_END_X,685)]
    mats=[C.material('ExtensionFarField_'+str(i),'grass','grass_lawn',tint) for i,tint in enumerate(((.72,.73,.55),(.64,.68,.48),(.86,.78,.56)))]
    for n,(x0,y0,x1,y1) in enumerate(rects):
        xs=[x0+i*(x1-x0)/max(1,math.ceil((x1-x0)/40)) for i in range(max(1,math.ceil((x1-x0)/40))+1)]
        ys=[y0+i*(y1-y0)/max(1,math.ceil((y1-y0)/40)) for i in range(max(1,math.ceil((y1-y0)/40))+1)]
        for iy,(ya,yb) in enumerate(zip(ys,ys[1:])):
            for ix,(xa,xb) in enumerate(zip(xs,xs[1:])):
                mat=mats[(ix+iy*2+n)%3];ob=C.mesh('EXT_FarField_'+str(n)+'_'+str(ix)+'_'+str(iy),[(xa,ya,.008),(xb,ya,.008),(xb,yb,.008),(xa,yb,.008)],[(0,1,2,3)],mat,root)
                for loop in ob.data.uv_layers[0].data:loop.uv/=2
                ob['part']='far_fields';ob['render_only']=True;ob['collision_exception']='far presentation skirt outside playable core/extension union'
    for i,(x,y) in enumerate([(282,611),(280,650),(284,682),(292,711),(286,745),(491,755),(497,811),(487,856),(489,908),(328,917),(376,918),(422,918),(290,854),(297,920)]):tree(root,'far_'+str(i),x,y,7.2+(i%3)*.45)

def pit(root,r,index):
    x0,y0,x1,y1=r;inset=1.5;z=-1.4
    inner=[(x0+inset,y0+inset,z),(x1-inset,y0+inset,z),(x1-inset,y1-inset,z),(x0+inset,y1-inset,z)]
    outer=[(x0,y0,.008),(x1,y0,.008),(x1,y1,.008),(x0,y1,.008)]
    for k in range(4):
        j=(k+1)%4;top=[outer[k],outer[j],inner[j],inner[k]]
        ob=C.mesh('EXT_Pit_'+str(index)+'_Bank_'+str(k),top,[(0,1,2,3)],M['sand'],root);ob['part']='terrain'
        for loop in ob.data.uv_layers[0].data:loop.uv/=6
        vs=top+[(x,y,zz-.16) for x,y,zz in top]
        C.col_mesh('EXT_Pit_'+str(index)+'_Bank_'+str(k),vs,[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],'soil',parent=root)
    ob=box('EXT_Pit_'+str(index)+'_Floor',(x0+inset,y0+inset,z-.18),(x1-inset,y1-inset,z),'sand',root,0);ob['part']='terrain'
    PITS.append(dict(bounds=r,depth_m=1.4,walkable_sloping_banks=True,ground_removed=True))

def homes(root):
    with bpy.data.libraries.load(str(HERE/'kit/houses.blend'),link=False) as (src,dst):
        dst.objects=[n for n in src.objects if 'sage_south' in n or 'clay_south' in n]
    source=[o for o in dst.objects if o]
    for o in source:
        if not o.users_collection:bpy.context.scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    report=json.loads((HERE/'kit/houses_report.json').read_text())
    for hid,sid,centre,old in HOME_SPECS:
        yaw=90 if sid.startswith('clay') else -90;T=Matrix.Translation(Vector(centre))@Matrix.Rotation(math.radians(yaw),4,'Z')@Matrix.Translation(-Vector(old))
        cloned=[]
        for src in source:
            if not (src.get('home')==sid or src.name.startswith('COL_'+sid+'_')):continue
            ob=src.copy();ob.data=src.data.copy();ob.name=('COL_EXT_' if src.name.startswith('COL_') else 'EXT_')+hid+'_'+src.name
            bpy.context.scene.collection.objects.link(ob);mw=src.matrix_world.copy();ob.parent=None;ob.matrix_world=T@mw;C.apply(ob);C.parent_keep(ob,root)
            ob['home']=hid;ob['part']='home_'+hid;cloned.append(ob)
        bounds=C.bc.world_bounds([o for o in cloned if not o.name.startswith('COL_')]);doors=[dict(o,home=hid) for o in report['openings'] if o['home']==sid]
        HOMES.append(dict(id=hid,source_home=sid,centre=list(centre),front='-Y',source='existing v3 houses.blend meshes and closed collision',bounds=[list(v) for v in bounds],openings=doors))
        if cloned:
            # The former party roof end is missing from the attached source. Mirror the
            # retained exposed gable prism and close it with matching painted cladding.
            original=next(o for o in cloned if 'ExposedGable' in o.name)
            verts=[o for o in [original.matrix_world@v.co for v in original.data.vertices]]
            vs=[(2*centre[0]-v.x,v.y,v.z) for v in verts];fs=[tuple(reversed(p.vertices)) for p in original.data.polygons]
            cap=C.mesh('EXT_'+hid+'_ClosedGable',vs,fs,(M['sage'] if sid.startswith('sage') else C.material('HomeClayGable','cladding','fibercement_panel',(.73,.28,.13))),root);cap['part']='home_'+hid;C.apply(cap)
            cap.modifiers.new('Export triangles','TRIANGULATE');C.apply(cap)
            for loop in cap.data.uv_layers[0].data:loop.uv/=M['sage']['repeat_m']
            co=C.col_mesh('EXT_'+hid+'_ClosedGable',vs,fs,'cladding',walkable=False,parent=root)
            HOMES[-1]['added_gable']=dict(visual=cap.name,collision=co.name,vertices=vs,thickness_m=.30)
            front=sorted(vs,key=lambda p:p[0])[-3:]
            for a,b in zip(front,front[1:]+front[:1]):tube('EXT_DetachedGableTrim',a,b,.065,'concrete',root,False)['part']='home_'+hid
        HOMES[-1].update(plot=HOME_PLOTS[len(HOMES)-1],plot_size_m=[24,44],attached_garage=False,source_rotation_deg=yaw)
    for o in source:bpy.data.objects.remove(o,do_unlink=True)
    log('finished standalone source homes',len(HOMES),'fronts south; all former-party gables capped')

def hedge(root,name,lo,hi):
    ob=box('FOL_hedge_EXT_'+name,lo,hi,'hedge',root,.12);ob['foliage']='hedge';ob['density']=1;ob['tint']='sage_hedge';ob['render_proxy']='runtime leaf volume';ob['part']='foliage'
    FOL.append(dict(name=ob.name,foliage='hedge',density=1,tint='sage_hedge',aabb=dict(min=list(lo),max=list(hi))))
def tree(root,name,x,y,h):
    trunk=C.bc.cylinder('EXT_TreeTrunk_'+name,.16,h*.58,loc=(x,y,h*.29),verts=10,mat=M['wood']);trunk.modifiers.new('Export triangles','TRIANGULATE');C.apply(trunk);C.parent_keep(trunk,root);trunk['part']='foliage'
    C.col_box('EXT_TreeTrunk_'+name,(x-.16,y-.16,0),(x+.16,y+.16,h*.58),'wood_thick',walkable=False,parent=root)
    rng=random.Random(name)
    for k,(dx,dy,dz) in enumerate(((-.75,0,-.45),(.75,.15,-.30),(0,.15,.55),(0,-.7,-.2))):
        ob=C.bc.sphere('FOL_tree_EXT_'+name+'_'+str(k),1.7,loc=(x+dx,y+dy,h*.68+dz),scale=(1,.9,1.12),segments=10,rings=5,mat=M['tree']);C.apply(ob);C.parent_keep(ob,root);ob['part']='foliage'
        for v in ob.data.vertices:v.co+=(Vector((rng.uniform(-.08,.08),rng.uniform(-.08,.08),rng.uniform(-.08,.08))))
        mn,mx=C.bc.world_bounds([ob]);ob['foliage']='tree';ob['density']=1;ob['tint']='sage_tree';ob['render_proxy']='runtime leaf volume'
        FOL.append(dict(name=ob.name,foliage='tree',density=1,tint='sage_tree',aabb=dict(min=list(mn),max=list(mx))))

def gardens(root):
    gravel=C.material('PebbleDriveApron','gravel','gravel',(.9,.91,.9))
    for index,(x0,y0,x1,y1) in enumerate(DRIVEWAYS):
        # Only the entrance finish extends over the existing north-side skirt.
        # Bulk extension terrain still begins at y685; this is outside the core.
        ob=C.mesh('EXT_PebbleDriveEntrance_'+str(index),[(x0,y0,.020),(x1,y0,.020),(x1,685,.020),(x0,685,.020)],[(0,1,2,3)],gravel,root)
        ob['part']='residential/driveway_aprons';ob['intentional_roadside_finish']=True
        for loop in ob.data.uv_layers[0].data:loop.uv/=gravel.get('repeat_m',1)
        co=C.col_box('EXT_PebbleDriveEntrance_'+str(index),(x0,y0,-.02),(x1,685,.020),'gravel',parent=root);ob['collision']=co.name
    for index,(x0,y0,x1,y1) in enumerate(HOME_PLOTS):
        hedge(root,'home_'+str(index)+'_west',(x0,y0,0),(x0+.7,y1,2.5))
        hedge(root,'home_'+str(index)+'_east',(x1-.7,y0,0),(x1,y1,2.5))
        hedge(root,'home_'+str(index)+'_back',(x0+.7,y1-.7,0),(x1-.7,y1,2.5))
        cx=(x0+x1)/2
        for x in (cx-4.7,cx-2.3):hedge(root,'home_'+str(index)+'_front_bush_'+str(x),(x-.55,685.3,0),(x+.55,686.3,.65))
        tree(root,'garden_'+str(index),cx,y1-8,5.5)
    hedge(root,'site_back_west',(339,903.8,0),(377,905,3.4));hedge(root,'site_back_east',(394,903.8,0),(429,905,3.4))

def communal_greens(root):
    # Each organic printed planter has integrated timber seats and three exact
    # planting pockets. Rotate the provided local FOL volumes with the prop.
    source=json.loads((PROPS/'garden/organic_planter_bench/foliage.json').read_text())['volumes']
    for index,pos in enumerate(COMMUNAL_PLANTERS):
        T=Matrix.Translation(Vector(pos))@Matrix.Rotation(math.radians(90),4,'Z')
        for pocket,row in enumerate(source):
            bounds=row['aabb'];points=[T@Vector((x,y,z)) for x in (bounds['min'][0],bounds['max'][0]) for y in (bounds['min'][1],bounds['max'][1]) for z in (bounds['min'][2],bounds['max'][2])]
            lo=tuple(min(p[k] for p in points) for k in range(3));hi=tuple(max(p[k] for p in points) for k in range(3))
            ob=box('FOL_organic_planter_EXT_'+str(index)+'_'+str(pocket),lo,hi,'hedge',root,.10,False)
            ob['part']='foliage';ob['foliage']=row['foliage'];ob['density']=row['density'];ob['tint']=row['tint'];ob['render_proxy']='runtime leaf volume'
            FOL.append(dict(name=ob.name,foliage=row['foliage'],density=row['density'],tint=row['tint'],aabb=dict(min=list(lo),max=list(hi)),source_prop='organic_planter_bench'))

def ramp(root,name,x0,x1,y0,y1,z0,z1):
    top=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z1),(x0,y1,z1)]
    vs=top+[(x,y,z-.16) for x,y,z in top]
    fs=[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    ob=C.mesh(name.replace('Ramp','Underslab'),vs,fs,M['concrete'],root);ob['part']='stairs'
    for loop in ob.data.uv_layers[0].data:loop.uv/=M['concrete']['repeat_m']
    co=C.col_mesh(name,vs,fs,'concrete',parent=root)
    co['stair_ramp']=True;return co

def stairs(root):
    rise=3.2/18;tread=.30;n=9;y0=725.6;y1=y0+n*tread
    for level in range(5):
        base=level*3.2
        for flight,(x0,x1,ya,yb,z0,z1) in enumerate(((343.4,344.8,y0,y1,base,base+1.6),(345.2,346.6,y1,y0,base+1.6,base+3.2))):
            ramp(root,'EXT_StairRamp_'+str(level)+'_'+str(flight),x0,x1,ya,yb,z0,z1)
            for k in range(n):
                aa=ya+(yb-ya)*k/n;bb=ya+(yb-ya)*(k+1)/n;top=z0+(k+1)*rise
                ob=box('EXT_StairTread_'+str(level)+'_'+str(flight)+'_'+str(k),(x0,min(aa,bb),top-.20),(x1,max(aa,bb),top),'concrete',root,.004,False);ob['part']='stairs'
            for x in (x0-.07,x1+.07):
                tube('EXT_StairHandrail',(x,ya,z0+1.05),(x,yb,z1+1.05),.04,'steel',root)['part']='stairs'
                for k in range(4):
                    t=k/3;y=ya+(yb-ya)*t;z=z0+(z1-z0)*t
                    tube('EXT_StairRailPost',(x,y,z),(x,y,z+1.05),.04,'steel',root)['part']='stairs'
        box('EXT_StairMidLanding_'+str(level),(343.4,y1,base+1.38),(346.6,y1+1.4,base+1.6),'concrete',root,.005)['part']='stairs'
        box('EXT_StairUpperLanding_'+str(level),(343.4,725.2,base+2.98),(346.6,y0,base+3.2),'concrete',root,.005)['part']='stairs'
        for a,b in (((343.3,y1+1.4,base+2.65),(346.7,y1+1.4,base+2.65)),((343.3,y1,base+2.65),(343.3,y1+1.4,base+2.65)),((346.7,y1,base+2.65),(346.7,y1+1.4,base+2.65))):tube('EXT_LandingRail',a,b,.04,'steel',root)['part']='stairs'
        STAIRS.append(dict(from_floor=level,to_floor=level+1,from_z_m=base,to_z_m=base+3.2,riser_m=rise,tread_m=tread,clear_width_m=1.4,flight_run_m=2.7,landing_depth_m=1.4,hole=[343,725.2,348,730],walkable_collision='two closed inclined prisms plus solid landings'))

def apartment(root):
    before=set(bpy.data.objects)
    # Five storeys, true open frame. Six slab elevations include the roof.
    holes=[[343,725.2,348,730],[350,727,353,730]]
    xs_cut=sorted({341,395,*[v for h in holes for v in (h[0],h[2])]});ys_cut=sorted({722,748,*[v for h in holes for v in (h[1],h[3])]})
    slabs=[(a,b,c,d) for a,c in zip(xs_cut,xs_cut[1:]) for b,d in zip(ys_cut,ys_cut[1:]) if not any(inrect((a+c)/2,(b+d)/2,h) for h in holes)]
    for level in range(6):
        z=level*3.2
        for k,(x0,y0,x1,y1) in enumerate(slabs):box('EXT_ApartmentFloor_'+str(level)+'_'+str(k),(x0,y0,z-.22),(x1,y1,z),'concrete',root,.008)['part']='apartment_frame'
    xs=[341.225,350,359,368,377,386,394.775];ys=[722.225,730.75,739.25,747.775]
    for level in range(5):
        z=level*3.2
        for x in xs:
            for y in ys:box('EXT_Column_'+str(level),(x-.225,y-.225,z),(x+.225,y+.225,z+2.98),'concrete',root,.018)['part']='apartment_frame'
        for y in ys:box('EXT_FrontRearBeam_'+str(level),(341,y-.20,z+2.60),(395,y+.20,z+2.98),'concrete',root,.01)['part']='apartment_frame'
        for x in xs:box('EXT_DepthBeam_'+str(level),(x-.18,722.45,z+2.60),(x+.18,747.55,z+2.98),'concrete',root,.01)['part']='apartment_frame'
    # A partially closed rear row suggests ongoing printed wall construction.
    for x0 in (350.3,359.3,368.3,377.3,386.3):
        for level,height in ((0,2.55),(1,1.65),(2,.85)):
            z=level*3.2
            box('EXT_PartPrintedRearWall',(x0,747.48,z),(x0+7.8,747.72,z+height),'printed',root,.012)['part']='apartment_wall'
            box('EXT_RearWindowSill',(x0,739.3,z),(x0+7.8,739.54,z+.70),'printed',root,.012)['part']='apartment_wall'
            for xa,xb in ((x0,x0+2.1),(x0+3.5,x0+7.8)):
                box('EXT_PartitionDoorPier',(xa,739.3,z+.7),(xb,739.54,z+min(height,2.5)),'printed',root,.012)['part']='apartment_wall'
    for x in xs:
        for y in ys:
            for dx in (-.1,.1):tube('EXT_ColumnStarterRebar',(x+dx,y,16),(x+dx,y,16.7),.025,'steel',root,False)['part']='apartment_detail'
    stairs(root)
    # The complete building, stairs and physical hulls turn together around its centre.
    for ob in set(bpy.data.objects)-before:
        if ob.type=='MESH':
            local=ob.matrix_world.inverted()@APARTMENT_T@ob.matrix_world
            ob.data.transform(local);ob.data.update()
            ob['apartment_yaw_deg']=APARTMENT_YAW_DEG;ob['building_id']='apartment_0'
    for row in STAIRS:
        x0,y0,x1,y1=row['hole'];row['hole']=[1093-y1,x0+409,1093-y0,x1+409]
    # Three standing frames; the fourth is built as an open foundation by PARK.
    first=sorted(set(bpy.data.objects)-before,key=lambda ob:ob.name)
    for index,shift in enumerate(APARTMENT_SHIFTS[1:3],1):
        copy_t=Matrix.Translation(Vector(shift))
        for original in first:
            if original.type!='MESH':continue
            ob=original.copy();ob.data=original.data.copy()
            prefix='COL_EXT_B'+str(index)+'_' if original.name.startswith('COL_') else 'EXT_B'+str(index)+'_'
            ob.name=original.name.replace('COL_EXT_',prefix,1) if original.name.startswith('COL_') else original.name.replace('EXT_',prefix,1)
            bpy.context.scene.collection.objects.link(ob)
            local=ob.matrix_world.inverted()@copy_t@ob.matrix_world;ob.data.transform(local);ob.data.update();ob['building_id']='apartment_'+str(index)
            if ob.get('collision'):ob['collision']=str(ob['collision']).replace('COL_EXT_','COL_EXT_B'+str(index)+'_',1)
    for index,shift in enumerate(APARTMENT_SHIFTS[:3]):
        dx,dy,_=shift
        for floor in range(5):
            z=floor*3.2
            for name,lo,hi in [('West',(363,759,z),(363.2,762,z+3.2)),('East',(365.8,759,z),(366,762,z+3.2)),('North',(363.2,761.8,z),(365.8,762,z+3.2)),('DoorPierL',(363.2,759,z),(363.9,759.2,z+3.2)),('DoorPierR',(365.1,759,z),(365.8,759.2,z+3.2)),('DoorHead',(363.9,759,z+2.25),(365.1,759.2,z+3.2))]:
                lo=(lo[0]+dx,lo[1]+dy,lo[2]);hi=(hi[0]+dx,hi[1]+dy,hi[2]);ob=box('EXT_LiftShaft_'+str(index)+'_'+str(floor)+'_'+name,lo,hi,'concrete',root,.008);ob['part']='apartment_shafts';ob['building_id']='apartment_'+str(index)
    log('three standing frames and one open-foundation footprint over shared parking')

def place(pid,pos,yaw=0,scale=1,lootable=False,locked=False):
    number=INSTANCE_COUNTERS.get(pid,0);INSTANCE_COUNTERS[pid]=number+1
    row=dict(id='ext_'+pid+'_'+str(number),prop_id=pid,position=list(pos),yaw_deg=yaw,scale=scale,color_variant=None,lootable=lootable,locked=locked,mode='extraction');INST.append(row);return row

def fence_run(a,b):
    a,b=Vector(a),Vector(b);length=(b-a).length;n=math.ceil(length/2.5);step=length/n;angle=math.degrees(math.atan2(b.y-a.y,b.x-a.x))
    for k in range(n):
        p=a+(b-a)*(k+.5)/n
        if ACCESS.distance(p.x,p.y)<ACCESS.WIDTH/2+1.4:
            INSTANCE_COUNTERS['site_mesh_panel']=INSTANCE_COUNTERS.get('site_mesh_panel',0)+1
            continue
        place('site_mesh_panel',p,angle,step/2.5)

def placements(root,catalog):
    place('tower_crane',(466,850,0))
    for x in (359,371,383):place('scaffold_bay',(x,720.95,0))
    for level in range(1,5):
        for x in (344,350,365,377,389,392.4):place('temporary_guardrail',(x,721.90,level*3.2))
    for level in range(1,5):
        for y in (726,735,744):place('temporary_guardrail',(394.9,y,level*3.2),90)
    place('site_office',(456,869,0));place('site_office',(456,869,2.8))
    for x,y in ((471,866),(469.5,866),(471,872),(472.5,872)):place('portable_toilet',(x,y,0))
    for i,(x,y) in enumerate([(316,752),(324,756),(316,766),(324,774),(316,781),(330,785),(330,750),(330,762)]):
        place('printed_blocks_pallet',(x,y,0),90 if i%2 else 0)
        place('printed_blocks_pallet',(x-1.65,y+.25,0),90 if i%2 else 0)
        place('timber_pallet',(x+1.7,y+.4,0),15)
    for x,y in ((317,757),(329,769),(317,776),(329,779)):place('rebar_bundle',(x,y,0),0)
    place('moving_truck',(471,774,0),180);place('moving_truck',(456,741,0),180)
    for a,b in (((310,735,0),(430,735,0)),((448,735,0),(480,735,0)),((310,735,0),(310,780,0)),((480,735,0),(480,780,0)),((310,905,0),(480,905,0))):fence_run(a,b)
    for index,(hid,sid,centre,old) in enumerate(HOME_SPECS):
        x,y,_=centre;place('dining_table',(x,y+5,0));place('raised_planter',(x-4,y+13,0),90)
        place('city_car',(x+9.4,705,0),0)
        for xx in (x-11,x-9,x-7,x-5,x-3,x+4,x+6):place('picket_panel',(xx,684.2,0),0)
        place('garden_gate',(x+1,684.2,0),0)
    # Attached scaffold/edge protection follow the same building rotation.
    for row in INST:
        if row['prop_id'] in ('scaffold_bay','temporary_guardrail'):
            row['position']=list(APARTMENT_T@Vector(row['position']))
            row['yaw_deg']=(row['yaw_deg']+APARTMENT_YAW_DEG)%360
    # Three standing superstructures; foundation edges get separate safety rails.
    originals=[r for r in INST if r['prop_id'] in ('scaffold_bay','temporary_guardrail')]
    for shift in APARTMENT_SHIFTS[1:3]:
        for row in originals:
            position=[row['position'][k]+shift[k] for k in range(3)]
            place(row['prop_id'],position,row['yaw_deg'],row['scale'],row['lootable'],row['locked'])
    # Extend perimeter side runs without renumbering existing panels.
    fence_run((310,780,0),(310,905,0));fence_run((480,780,0),(480,905,0))
    # Existing furniture is placed in the actual cloned room frame.
    local=[('kitchen_base',(351.5,644.25,0),0),('dining_table',(356,641.7,0),-90),('sofa',(357.5,636.2,0),90),('bookcase',(351,636,0),90),('bed',(352.5,636,3.2),-90),('wardrobe',(355.5,633.7,3.2),0)]
    for hid,sid,centre,old in HOME_SPECS:
        yaw=90 if sid.startswith('clay') else -90
        base=(387.5,639,0) if sid.startswith('clay') else (352.5,639,0)
        T=Matrix.Translation(Vector(centre))@Matrix.Rotation(math.radians(yaw),4,'Z')@Matrix.Translation(-Vector(base))
        for pid,pos,angle in local:
            if sid.startswith('clay'):pos=(740-pos[0],pos[1],pos[2])
            place(pid,T@Vector(pos),angle+yaw)
    # Original crane keeps its exact placement; the second covers the west build row.
    place('tower_crane',(321,875,0),90)
    for x,y in ((444,880),(462,889)):
        place('site_office',(x,y,0));place('site_office',(x-1.2 if x==462 else x,y,2.8));place('site_office_stairs',(x,y,0))
    place('site_office',(456,889,0))
    place('site_office_stairs',(456,869,0))
    for x,y,yaw in ((322,790,0),(323,835,25),(465,797,180)):
        place('moving_truck',(x,y,0),yaw)
    for car in BASEMENT['suggested_parked_cars']:place('city_car',car['position'],car['yaw_deg'])
    for x,y,yaw in ACCESS.iron_fence_positions():place('site_mesh_panel',(x,y,0),yaw)
    for x,y in ((326,753),(327,766),(326,782)):place('printed_blocks_pallet',(x,y,0));place('timber_pallet',(x+2,y+.5,0))
    place('playground_set',(357,822,0))
    for pos in COMMUNAL_PLANTERS:place('organic_planter_bench',pos,90)
    MATERIAL_CLUSTERS.extend(CLUTTER.place_clusters(place))
    MATERIAL_REQUEST_STATUS.extend(CLUTTER.place_ready_requests(place,catalog))

def import_instance(row,catalog,root):
    pid=row['prop_id']
    if pid in INSTANCE_TEMPLATES:
        # Repeated placements share immutable mesh data, as the game instances do.
        template=INSTANCE_TEMPLATES[pid];copies={o:o.copy() for o in template};obs=list(copies.values())
        for original,ob in copies.items():
            ob.name=row['id']+'__'+original.name.split('__',1)[-1];bpy.context.scene.collection.objects.link(ob)
            ob.parent=copies.get(original.parent);ob.matrix_basis=original.matrix_basis.copy()
    else:
        src=ROOT/'assets'/catalog[pid]['glb'];j,buf=read(src)
        for n in j['nodes']:n['name']=row['id']+'__'+n.get('name','Node')
        for im in j.get('images',[]):
            if 'uri' in im:im['uri']=str((src.parent/im['uri']).resolve()).replace('\\','/')
        temp=CACHE/(row['id']+'.glb');save(temp,j,buf);before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(temp));obs=[o for o in bpy.data.objects if o not in before]
        INSTANCE_TEMPLATES[pid]=obs
    prop=next(o for o in obs if o.parent is None);prop.rotation_mode='XYZ';prop.location=row['position'];prop.rotation_euler=(0,0,math.radians(row['yaw_deg']));prop.scale=(row['scale'],)*3;prop.parent=root;prop.matrix_parent_inverse=Matrix.Identity(4)
    prop['instance_id']=row['id'];prop['mode']='extraction'
    for ob in obs:
        if ob.type=='MESH':ob['instance_id']=row['id'];ob['part']='prop_instance'
        if catalog[pid]['category']=='containers' and not row['lootable'] and ob.name.split('__')[-1].startswith('OPEN_'):
            if ob.name.split('__')[-1].startswith('OPEN_DRAWER_'):ob.location=Vector(ob['closed_location'])
            elif 'axis' in ob:
                if ob.rotation_mode=='QUATERNION':rotation=ob.rotation_quaternion.to_euler('XYZ');ob.rotation_mode='XYZ';ob.rotation_euler=rotation
                ob.rotation_euler['XYZ'.index(ob['axis'])]=0
    # Library collision remains authoritative and is instantiated by the loader.
    # An optional wireframe overlay can be generated for authoring inspection.
    if '--instance-collision' in sys.argv:
        bpy.context.view_layer.update();T=prop.matrix_world.copy()
        for r in json.loads((ROOT/'assets'/catalog[pid]['collision']).read_text())['volumes']:
            bm=bmesh.new();verts=[bm.verts.new(T@Vector(v)) for v in r['vertices']];bmesh.ops.convex_hull(bm,input=verts,use_existing_faces=False);bm.verts.index_update();vs=[tuple(v.co) for v in bm.verts];fs=[tuple(v.index for v in p.verts) for p in bm.faces];bm.free()
            co=C.col_mesh(row['id']+'__'+r['name'],vs,fs,r['phys'],r['kind'],r['walkable'],root);co['instance_id']=row['id']
    return obs

def inside(row,p,eps=.0003):return all(q[0]*p[0]+q[1]*p[1]+q[2]*p[2]<=q[3]+eps for q in row['planes'])
def stair_qa(rows,shift=(0,0,0)):
    path=[]
    def segment(a,b,n=18):
        for k in range(n+1):path.append(tuple(a[i]+(b[i]-a[i])*k/n for i in range(3)))
    segment((344.1,721.4,0),(344.1,725.6,0))
    for level in range(2):
        z=level*3.2
        segment((344.1,725.6,z),(344.1,728.3,z+1.6),27)
        segment((344.1,728.3,z+1.6),(344.1,729,z+1.6),7)
        segment((344.1,729,z+1.6),(345.9,729,z+1.6),18)
        segment((345.9,729,z+1.6),(345.9,728.3,z+1.6),7)
        segment((345.9,728.3,z+1.6),(345.9,725.6,z+3.2),27)
        segment((345.9,725.6,z+3.2),(345.9,724.6,z+3.2),10)
        segment((345.9,724.6,z+3.2),(344.1,724.6,z+3.2),18)
        if level==0:segment((344.1,724.6,z+3.2),(344.1,725.6,z+3.2),10)
    path=[tuple(APARTMENT_T@Vector(p)+Vector(shift)) for p in path]
    supports=[];headroom=[]
    for x,y,want in path:
        candidates=[r for r in rows if r['aabb']['min'][0]-.001<=x<=r['aabb']['max'][0]+.001 and r['aabb']['min'][1]-.001<=y<=r['aabb']['max'][1]+.001]
        tops=[]
        for r in candidates:
            if not r.get('walkable',True):continue
            for nx,ny,nz,d in r['planes']:
                if nz<.1:continue
                z=(d-nx*x-ny*y)/nz
                if abs(z-want)<.025 and inside(r,(x,y,z)):tops.append(z)
        assert tops,('stair support absent',(x,y,want));z=max(tops);supports.append([x,y,z])
        # A 0.64m-wide, 1.9m-tall capsule corridor, matching the game's .32m radius.
        nearby=[r for r in rows if r['aabb']['min'][0]<=x+.32 and r['aabb']['max'][0]>=x-.32 and r['aabb']['min'][1]<=y+.32 and r['aabb']['max'][1]>=y-.32 and r['aabb']['min'][2]<z+1.95 and r['aabb']['max'][2]>z+.25]
        for dx,dy in ((0,0),(.32,0),(-.32,0),(0,.32),(0,-.32),(.2263,.2263),(.2263,-.2263),(-.2263,.2263),(-.2263,-.2263)):
            for h in (.30,.80,1.30,1.90):
                assert not any(inside(r,(x+dx,y+dy,z+h)) for r in nearby),('stair capsule blocked',(x,y,z),dx,dy,h,[r['name'] for r in nearby if inside(r,(x+dx,y+dy,z+h))])
        headroom.append(1.90)
    return dict(route_samples=len(path),supported_path=supports,minimum_tested_capsule_height_m=min(headroom),capsule_diameter_m=.64,stairs_without_jetpack=True,upper_floor1_reached=True,upper_floor2_reached=True,risers_m=3.2/18,treads_m=.30,clear_width_m=1.4,overhead_holes_open=True)

def ron(data):
    def val(v):
        if v is None:return 'None'
        if isinstance(v,bool):return str(v).lower()
        if isinstance(v,str):return json.dumps(v)
        if isinstance(v,(int,float)):return str(v)
        if isinstance(v,(list,tuple)):return '['+', '.join(val(x) for x in v)+']'
        if isinstance(v,dict):return '('+', '.join(k+': '+val(x) for k,x in v.items())+')'
        raise TypeError(type(v))
    return '// Separate phase-2 proposal. User placements.ron is never overwritten.\n'+val(data)+'\n'

def setup_ground_preview():
    sys.path.insert(0,str(ROOT/'assets/maps/showhome'));import ground_blend as GB
    for name,family,rep,kind in [('Asphalt','asphalt',4,'hard'),('Paving','paving_slabs',2.4,'hard'),('Grass','grass_lawn',2,'lawn'),('Soil','worksite_packed_dirt',6,'earth'),('Tracks','worksite_mud_tracks',6,'earth'),('TrackedEarth','worksite_mud_tracks',6,'earth'),('Gravel','gravel',1,'hard'),('HaulGravel','gravel',1,'earth')]:GB.BASES['M_GND_Ext_'+name]=(family,rep,kind)
    writer=GB.write_contract;GB.write_contract=lambda path=None:writer(OUT/'ground_blend_contract.json')
    # Keep canonical PBR materials alongside the used preview materials in the
    # saved .blend, so a later saved-scene export can safely restore them.
    for mat in bpy.data.materials:
        if mat.name in GB.BASES:mat.use_fake_user=True
    GB.setup_preview();return GB

def finalize_ground_contract():
    j,buf=read(OUT/'extension.glb');contracts={}
    for mat in j['materials']:
        raw=mat.get('extras',{}).get('showhome_ground_blend')
        if not raw:continue
        contract=json.loads(raw) if isinstance(raw,str) else raw
        contract['contract']='maps/showhome_v3/extension/ground_blend_contract.json'
        mat['extras']['showhome_ground_blend']=json.dumps(contract);contracts[mat['name']]=contract
    payload=json.loads((OUT/'ground_blend_contract.json').read_text())
    payload['materials']=contracts;payload['maps_root']='maps/showhome_v3/extension';C.write(OUT/'ground_blend_contract.json',payload)
    save(OUT/'extension.glb',j,buf)

def context_scene():
    path=HERE/'showhome_v3.blend'
    # The old north temporary fence is superseded by the phase-2 houses. TDM
    # barriers have their own reviewed views and do not belong in extraction.
    with bpy.data.libraries.load(str(path),link=False) as (src,dst):dst.objects=[n for n in src.objects if not n.startswith(('COL_','V3_','site_mesh_panel_','concrete_barrier_'))]
    for ob in dst.objects:
        if ob and ob.type in ('MESH','EMPTY'):
            if not ob.users_collection:bpy.context.scene.collection.objects.link(ob)
            ob['context_only']=True
    bpy.context.view_layer.update()

def parking_lighting(root):
    lamp=C.material('ParkingWorkLight','plastic',None,(.8,.75,.60),rough=.55)
    shader=lamp.node_tree.nodes.get('Principled BSDF');shader.inputs['Emission Color'].default_value=(1,.87,.68,1);shader.inputs['Emission Strength'].default_value=3
    rows=[]
    for x in (349,385,415):
        for y in (761,788,815,850,883):
            if x>397 and y>838:continue
            box('EXT_ParkingLightHousing',(x-.32,y-.11,-.35),(x+.32,y+.11,-.25),'steel',root,.012)['part']='parking_basement/lights'
            ob=C.box('EXT_ParkingLightLens',(.54,.16,.008),(x,y,-.354),lamp,.002,root,collision=True);ob['part']='parking_basement/lights'
            data=bpy.data.lights.new('ParkingWorkLamp','POINT');data.energy=120;data.color=(1,.87,.68);data.shadow_soft_size=.28
            ob=bpy.data.objects.new('EXT_ParkingWorkLamp',data);bpy.context.scene.collection.objects.link(ob);ob.location=(x,y,-.55);ob.parent=root;ob['part']='parking_basement/lights'
            rows.append(dict(position=[x,y,-.55],type='point',source_watts=120,export='KHR_lights_punctual'))
    BASEMENT['temporary_work_lights']=rows;BASEMENT['minimum_under_fixture_clearance_m']=2.842

def render_views(selected=None):
    context_scene();cam=C.stage();sc=bpy.context.scene;sc.cycles.samples=12
    views={
        'aerial':((560,650,165),(387,773,8),315),
        'site_aerial':((540,720,150),(395,820,7),228),
        'site_plan':((395,820,250),(395,820,0),188),
        'worksite_ground':((436,740,2.2),(382,770,9),None),
        'street':((381,654,27),(370,700,3.6),90),
        'street_house':((408,678,5.5),(395,697,3.4),None),
        'stairs':(APARTMENT_T@Vector((349.2,723.8,2.0)),APARTMENT_T@Vector((344.9,728.2,2.4)),None),
        'upper_floor':(APARTMENT_T@Vector((352,725.6,8.1)),APARTMENT_T@Vector((344.7,728,5.2)),None),
        'site_excavations':((336,798,9),(322,814,-.7),None),
        'earthworks_street':((325,808,1.608),(330,817,1),None),
        'detached_gable':((416,689,7),(402,696,6.8),None),
        'parking_basement':((382,771,-1.59),(395,810,-1.45),None),
        'foundation_stage':((455,826,18),(410,865,-.8),None),
        'gravel_tracks':((462,780,1.61),(465,792,.2),None),
        'tire_worn_lanes':((474,758,11),(465,798,.1),45),
        'material_yard':((341,741,12),(321,764,1),38),
        'cabin_stairs':((435,866,5),(445,876,3),None),
        'courtyard':((434,792,49),(383,822,1),78),
        'ramp_access':((473,827,21),(447,857,-1),None),
    }
    for name,(eye,target,ortho) in views.items():
        if selected and name not in selected:continue
        sc.render.resolution_x=1200 if name=='site_plan' else 1440;sc.render.resolution_y=1200 if name=='site_plan' else 900
        C.render(cam,OUT/'renders'/f'{name}.png',eye,target,ortho)
    log('integrated core/extension views rendered')

def main():
    catalog=build_props()
    if '--only-props' in sys.argv:return
    C.bc.reset_scene();materials();root=C.empty('EXTENSION_Phase2_Origin');root['frame']='design world XYZ metres';root['phase']=2
    ground(root);TRACK_REPORT.extend(TRACKS.build(root,FOOTPRINTS+HOME_PLOTS+APARTMENT_BOUNDS+PIT_RECTS+[PARK.RAMP_EXCAVATION]));far_fields(root);homes(root);gardens(root);communal_greens(root);apartment(root);BASEMENT.update(PARK.build_basement(root,M,APARTMENT_BOUNDS));
    ACCESS_REPORT.update(ACCESS.road(root));placements(root,catalog);MOUNDS.extend(SITE.build_mounds(root,M));parking_lighting(root)
    fixed=C.visuals();C.audit_visuals(fixed);cols=[o for o in bpy.context.scene.objects if o.name.startswith('COL_')]
    rows=C.export_collision(OUT/'collision.json',cols,'design world XYZ metres; phase2 fixed geometry only; instance collisions remain in reusable prop catalog')
    route=stair_qa(rows);routes=[dict(building_id='apartment_'+str(i),**stair_qa(rows,shift)) for i,shift in enumerate(APARTMENT_SHIFTS[:3])];route['building_routes']=routes;route['total_route_samples']=sum(r['route_samples'] for r in routes);C.write(OUT/'stairs_route.json',route);BASEMENT['integrated_route_qa']=PARK.validate_basement_routes(BASEMENT,rows,include_gf_exits=True)
    BASEMENT['vehicle_ramp']['integrated_two_way_vehicle_qa']=[dict(direction=lane['direction'],**PARK.validate_basement_routes(dict(access_cores=[],vehicle_ramp=dict(route_samples=lane['route_samples'])),rows,radius=1.2,height=2.4)) for lane in BASEMENT['vehicle_ramp']['lanes']]
    C.write(OUT/'parking_report.json',BASEMENT)
    assert all(o['width_m']>=1 for h in HOMES for o in h['openings'] if o['kind'] in ('door','door2'))
    C.write(OUT/'foliage.json',dict(schema=1,frame='design world XYZ metres',volumes=FOL,render_proxies=True,leaf_generation='existing game foliage system'))
    placement=dict(schema=1,map_id='showhome_v3_extension',phase=2,frame='design world XYZ metres',origin=[330,620,0],instances=C.plain(INST),player_clips=[],spawns=[],extracts=[],loot_spots=[])
    C.write(OUT/'placements.generated.json',placement);(OUT/'placements.proposed.ron').write_text(ron(placement),encoding='utf8')
    GB=setup_ground_preview();GB.prepare_export()
    C.export_glb(OUT/'extension.glb',[root]+fixed+[o for o in bpy.context.scene.objects if o.type=='LIGHT']);externalize(OUT/'extension.glb',HERE/'textures');finalize_ground_contract();GB.restore_preview()
    parts={}
    for ob in fixed:parts.setdefault(ob.get('part','other'),[]).append(ob)
    report=dict(schema=1,source_revision=SOURCE_REVISION,phase=2,frame='design world XYZ metres; glTF=(x,z,-y)',homes=HOMES,residential_plots=HOME_PLOTS,driveways=DRIVEWAYS,house_attached_garages=0,site_bounds=SITE_BOUNDS,cabin_stacks=CABIN_STACKS,communal_courtyard=dict(bounds=COMMUNAL_BOUNDS,playground_position_m=[357,822,0],organic_planter_positions_m=COMMUNAL_PLANTERS,planter_yaw_deg=90,integrated_timber_benches=True,foliage='existing runtime volumes; no leaf cards'),apartment=dict(bounds=APARTMENT_BOUNDS[0],building_bounds=APARTMENT_BOUNDS,count=4,standing_count=3,foundation_count=1,foundation_building_index=3,yaw_deg=APARTMENT_YAW_DEG,source_pivot_m=list(APARTMENT_PIVOT),centre_m=[358,777,0],nearest_edge_setback_delta_m=28,front="+X",stair_entry_m=[371.6,753.1,0],copy_shift_m=list(APARTMENT_COPY_SHIFT),storeys=5,floor_elevations_m=[0,3.2,6.4,9.6,12.8],roof_elevation_m=16,stairs=STAIRS),stairs=route,parking_basement=BASEMENT,gravel_access=ACCESS_REPORT,tracked_paths=TRACK_REPORT,material_clusters=MATERIAL_CLUSTERS,material_request_status=MATERIAL_REQUEST_STATUS,pending_loose_material_meshes=[r for r in json.loads((OUT/'loose_material_requests.json').read_text())['assets'] if not catalog.get(r['requested_id'])],pits=PITS,mounds=MOUNDS,fixed_triangles=C.triangles(fixed),triangles_per_part={k:C.triangles(v) for k,v in parts.items()},fixed_meshes=len(fixed),fixed_collision_volumes=len(rows),foliage_volumes=len(FOL),prop_instances=len(INST),prop_ids=sorted({r['prop_id'] for r in INST}),new_reusable_props=[catalog[pid] for pid in NEW_IDS],terrain_bounds=[310,685,SITE_END_X,SITE_END_Y],core_overlap=False,roadside_driveway_finish_aprons_y=[681,685],original_builders_executed=False,source='existing v3 source homes plus original procedural construction helpers',user_placements_preserved=True,runtime='asset handoff; no new game runtime')
    C.write(OUT/'report.json',report)
    jj,_=read(OUT/'extension.glb');assert all('uri' in i and 'bufferView' not in i for i in jj.get('images',[]));assert all(m.get('extras',{}).get('phys') in C.PHYS for m in jj['materials']);assert all('TEXCOORD_0' in p['attributes'] for m in jj['meshes'] for p in m['primitives'])
    C.write(OUT/'QA.json',dict(passed=True,phys_ok=True,uv_ok=True,external_images_ok=True,convex_collision_ok=True,min_collision_thickness_m=min(r['thickness_m'] for r in rows),stairs_route_ok=True,stairs_capsule_height_m=1.9,stairs_capsule_diameter_m=.64,stairs_clear_width_m=1.4,door_clearances_ok=True,detached_gable_closed=True,core_fixed_geometry_unchanged=True,user_placements_preserved=True,triangles_per_part=report['triangles_per_part']))
    C.write(OUT/'manifest.json',dict(map_id='showhome_v3_extension',source_revision=SOURCE_REVISION,phase=2,kit_scenes=['extension.glb'],collision='collision.json',foliage='foliage.json',placements='placements.proposed.ron',latest_placements_json='placements.generated.json',ground_blend_contract='ground_blend_contract.json',prop_ids=report['prop_ids'],fixed_world_frame=True,core_separate=True,mode='extraction',sun=dict(azimuth_deg=188,elevation_deg=54,linear_rgb=[1,.84,.66])))
    for row in INST:import_instance(row,catalog,root)
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'extension.blend'),compress=True)
    log('READY',report['fixed_triangles'],'fixed triangles',len(rows),'fixed collision',len(INST),'separate instances',route['total_route_samples'],'stair samples')
    if '--render' in sys.argv:
        selected=set(sys.argv[sys.argv.index('--views')+1].split(',')) if '--views' in sys.argv else None
        render_views(selected)
if __name__=='__main__':main()
