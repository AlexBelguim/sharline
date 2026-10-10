"""Phase 1 core and starter instances. Run after build_library.py/build_houses.py.
blender -b --factory-startup -P build_core.py [-- --render]
Never overwrites a handed-off placements.ron. Proposed placements are regenerated.
"""
import sys,json,math,copy,os
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common as C
from gltf_shared import read,save,externalize
HERE=C.HERE;ROOT=C.ROOT;KIT=HERE/'kit';KIT.mkdir(exist_ok=True)
L=json.loads((HERE/'layout.json').read_text());CAT=json.loads((ROOT/'assets/props/catalog.json').read_text());CAT={r['id']:r for r in CAT['props']}
GARDENS=json.loads((HERE/'gardens.json').read_text())
INST=[];BOUNDARY=[];FOL=[];GROUND={};STEP=[]
INSTANCE_TEMPLATES={}
NORTH=L['origin'][1]+L['size'][1];ROAD0=L['front_street'][1];ROAD1=L['front_street'][3];GARDEN_END=L['side_garden_end_y']
def inside(x,y,r):return r[0]-1e-6<=x<=r[2]+1e-6 and r[1]-1e-6<=y<=r[3]+1e-6
def house_rects():
    rs=[]
    for h in L['houses']:
        x,y,_=h['centre'];west=x<370
        rs.append([x-2.15 if west else x-8.15,y-6.15,x+8.15 if west else x+2.15,y+6.15])
        if h.get('attached_garage',h['id'].endswith('south')):
            south=h['id'].endswith('south');rs.append([x-2 if west else x-8.15,y-12 if south else y+5.85,x+8.15 if west else x+2,y-5.85 if south else y+12])
    return rs
def kind(x,y):
    if any(inside(x,y,r) for r in house_rects()):return None
    if inside(x,y,L['front_street']) or inside(x,y,L['central_street']):return 'asphalt'
    if 664<=y<GARDEN_END and (331.65<=x<=360.65 or 379.35<=x<=408.35):return 'grass'
    if 620<=y<=629.7 and 364.15<=x<=375.85:return 'paving'
    if 633<=y<=657 and ((360.65<=x<=364.15) or (375.85<=x<=379.35)):
        return 'paving' if min(abs(y-636),abs(y-648))<1.1 else 'grass'
    if GARDEN_END<=y<=NORTH and 290<=x<=450:return 'paving'
    if 664<=y<GARDEN_END and 364.15<=x<=375.85:return 'paving'
    if 620<=y<664 and (364.15<=x<=366.5 or 373.5<=x<=375.85):return 'paving'
    if 330<=x<=410 and 620<=y<=664:
        if any(inside(x,y,r) for r in house_rects()):return None
        if any(inside(x,y,r) for r in GARDENS['gravel_pads']):return 'gravel'
        if any(inside(x,y,r) for key in ('paths','patios','shed_pads') for r in GARDENS[key]):return 'paving'
        if 656.85<=y<=663 and (360.65<=x<=366.5 or 373.5<=x<=379.35):return 'paving'
        if x<332 or x>408 or y<622:return 'soil'
        return 'grass'
    return 'soil'
def masks(x,y,surface):
    # Broad continuous border masks; never used as opacity or albedo tint.
    edge=min(abs(x-v) for v in (332,339,341,360.65,364.15,366.5,373.5,375.85,379.35,400,402,408))
    edge=min(edge,min(abs(y-v) for v in (622,631.1,636.9,646.1,651.9,664,GARDEN_END,ROAD0,ROAD1,NORTH)))
    wav=.88+.12*math.sin(x*5.3+math.sin(y*3.1))
    r=max(0,1-edge/.9)*.48*wav if surface in ('grass','paving') else 0
    g=max([max(0,1-(abs(x-cx)-2.12)/.5)*max(0,1-(abs(y-cy)-2.9)/.5) for cx in (339,401) for cy in (634,649)])*.25 if surface=='paving' else 0
    b=max(0,1-edge/.48)*.16 if surface in ('grass','paving') else 0
    a=max(0,1-abs(y-NORTH)/2)*.20 if surface in ('asphalt','paving','soil') else 0
    for gate in ((331,660),(409,660),(370,621)):
        r=max(r,max(0,1-math.hypot(x-gate[0],y-gate[1])/2.2)*.8)
    if surface=='grass':r=max(r,max(0,1-math.hypot(x-374,y-637)/3)*.4)
    return (min(1,r),min(1,g),min(1,b),min(1,a))
def ground(root):
    tex={'asphalt':('asphalt','M_GND_Asphalt',4),'paving':('paving_slabs','M_GND_Paving',2.4),'grass':('grass_lawn','M_GND_Grass',2),'soil':('worksite_packed_dirt','M_GND_SoilFar',6),'gravel':('gravel_compacted','M_GND_Gravel',1)}
    acc={k:([],[],[]) for k in tex}
    # 0.5m interior; extra 0.25m positions around border/garden edges and exact footprints.
    xs=set(330+i*.5 for i in range(161));ys=set(620+i*.5 for i in range(int(L['size'][1]*2)+1))
    xs.update((290,310,320,420,430,450));ys.update((600,610,NORTH))
    for a in (332,339,341,360.65,364.15,366.5,373.5,375.85,379.35,400,402,408):xs.update(a+k*.25 for k in range(-4,5))
    for a in (622,631.1,633,634.9,636.9,637.1,645,646.1,646.9,649.1,651.9,657,664,GARDEN_END,ROAD0,ROAD1,NORTH):ys.update(a+k*.25 for k in range(-4,5))
    for r in house_rects():xs.update((r[0],r[2]));ys.update((r[1],r[3]))
    for key in ('paths','patios','gravel_pads','shed_pads'):
        for r in GARDENS[key]:xs.update((r[0],r[2]));ys.update((r[1],r[3]))
    xs=sorted({round(x,6) for x in xs});ys=sorted({round(y,6) for y in ys if y<=NORTH})
    # Each quad belongs to exactly one material and one top collision plane.
    for x0,x1 in zip(xs,xs[1:]):
        for y0,y1 in zip(ys,ys[1:]):
            k=kind((x0+x1)/2,(y0+y1)/2)
            if k is None:continue
            v,f,cs=acc[k];base=len(v);z=.008 if k!='asphalt' else 0
            q=[(x0,y0,z),(x1,y0,z),(x1,y1,z),(x0,y1,z)];v.extend(q);f.append(tuple(base+i for i in range(4)));cs.extend(masks(x,y,k) for x,y,z in q)
    for k,(v,f,cs) in acc.items():
        t,name,rep=tex[k];m=C.material(k,k,t);m.name=name;m['repeat']=[rep,rep];GROUND[k]=m
        ob=C.mesh('SH3_Ground_'+k,v,f,m);uv=ob.data.uv_layers[0]
        ca=ob.data.color_attributes.new(name='Col',type='FLOAT_COLOR',domain='CORNER')
        for p in ob.data.polygons:
            for li in p.loop_indices:
                i=ob.data.loops[li].vertex_index;uv.data[li].uv=(v[i][0]/rep,v[i][1]/rep);ca.data[li].color=cs[i]
        ob.data.color_attributes.active_color=ca;ob.data.color_attributes.render_color_index=ob.data.color_attributes.find('Col');C.parent_keep(ob,root)
        ob['ground_blend']='showhome_height_blend_v2';ob['collision_exception']='ground base volumes plus exact material surface patches'
    # A deep base supports the skirt; exact non-overlapping surface boxes carry phys.
    C.col_box('Ground_Base',(290,600,-.24),(450,NORTH,-.005),'soil')
    # Merge matching X runs through adjacent rows. Lawn collision never enters a house.
    active={};rectangles=[]
    for iy,(y0,y1) in enumerate(zip(ys,ys[1:])):
        runs=[];start=None;last=None
        for x0,x1 in zip(xs,xs[1:]):
            k=kind((x0+x1)/2,(y0+y1)/2)
            want=k is not None
            if want and start is not None and k==last:runs[-1][2]=x1
            elif want:runs.append([x0,y0,x1,y1,k]);start=x0;last=k
            else:start=None;last=None
        current={}
        for x0,y0,x1,y1,k in runs:
            key=(x0,x1,k)
            if key in active and abs(active[key][3]-y0)<1e-6:r=active.pop(key);r[3]=y1
            else:r=[x0,y0,x1,y1,k]
            current[key]=r
        rectangles.extend(active.values());active=current
    rectangles.extend(active.values())
    for n,(x0,y0,x1,y1,k) in enumerate(rectangles):C.col_box('Surface_'+str(n),(x0,y0,-.05),(x1,y1,0 if k=='asphalt' else .008),k)
def edge(root,a,b,style='kerb',drop=False):
    a,b=Vector(a),Vector(b);n=math.ceil((b-a).length);height=.016 if drop else (.11 if style=='kerb' else .012);width=.16 if style=='kerb' else .05
    m=C.material('Kerb' if style=='kerb' else 'Edging','concrete','kerb_concrete' if style=='kerb' else 'edging_strip');direction=(b-a).normalized()
    for k in range(n):
        p=a+(b-a)*(k+.5)/n;length=(b-a).length/n-.004
        ob=C.bc.box('SH3_'+style,(length,width,height+.02),loc=(p.x,p.y,(height-.02)/2),mat=m,bevel=.015 if style=='kerb' else .003,segments=1,smooth=35);ob.rotation_euler.z=math.atan2(direction.y,direction.x);C.apply(ob);C.parent_keep(ob,root)
        # Rectangular kerbs here align to the axes; no phantom turning-circle disk.
        mn,mx=C.bc.world_bounds([ob]);co=C.col_box(style+'_'+str(len(STEP)),list(mn),list(mx),'concrete');ob['collision']=co.name
        if height>.02:STEP.append(dict(name=co.name,height_m=height,min=list(mn),max=list(mx)))
def edges(root):
    for x in (366.42,373.58):edge(root,(x,629.7,0),(x,ROAD0,0))
    for y in (ROAD0-.08,ROAD1+.08):
        for x0,x1 in ((290,366.5),(373.5,450)):edge(root,(x0,y,0),(x1,y,0))
    edge(root,(366.5,ROAD1+.08,0),(373.5,ROAD1+.08,0),drop=True)
    # Pavement/lawn gets one flush strip; no raised garden kerb or grass ring.
    for x in (364.15,375.85):edge(root,(x,633,0),(x,657,0),'edging')
    for x0,x1 in ((332,360.65),(379.35,408)):edge(root,(x0,GARDEN_END,0),(x1,GARDEN_END,0),'edging')
def foliage(root,name,lo,hi,typ='hedge'):
    mat=C.material('FoliageProxy','foliage_dense' if typ=='hedge' else 'foliage_thin',None,(.13,.19,.085),rough=.95)
    bevel=0 if name in ('west','east','south_back','roadside_west','roadside_east') else .30 if typ=='bush' else .12
    ob=C.box('FOL_'+typ+'_'+name,[hi[k]-lo[k] for k in range(3)],[(hi[k]+lo[k])/2 for k in range(3)],mat,bevel)
    ob['foliage']=typ;ob['density']=1;ob['tint']='sage_hedge';ob['render_proxy']='plain silhouette; game generates leaves';C.parent_keep(ob,root)
    co=C.col_box('Foliage_'+name,lo,hi,mat['phys']);C.parent_keep(co,root)
    FOL.append(dict(name=ob.name,foliage=typ,density=1,tint='sage_hedge',aabb={'min':lo,'max':hi}))
def boundaries(root):
    height=L.get('outer_hedge_height_m',6)
    for x,side in ((331,'west'),(409,'east')):
        foliage(root,side,(x-.65,621.85,0),(x+.65,GARDEN_END,height))
    foliage(root,'south_back',(330.35,620.55,0),(409.65,621.85,height))
    for side,x0,x1 in (('west',331.65,L.get('roadside_return_endpoints',{}).get('west',350.35)),('east',L.get('roadside_return_endpoints',{}).get('east',389.65),408.35)):
        foliage(root,'roadside_'+side,(x0,GARDEN_END-1.3,0),(x1,GARDEN_END,height))
    # User-marked framed hedge by the south sage gable; leaves supplied by runtime.
    foliage(root,'marked_west_frame',(346.35,632.25,0),(350.35,633.45,2.75),'hedge')
    for x in (347,393):
        foliage(root,'upper_framed_'+str(x),(x-.60,646.8,0),(x+.60,655.2,2.75),'hedge')
        for y in (647,656):foliage(root,'upper_bush_'+str(x)+str(y),(x-.65,y-.6,0),(x+.65,y+.6,1.2),'bush')
    for x in (362.0,378.0):
        for y in (634.2,638.8,642.3,646.2,650.8,654.3):foliage(root,'front_bush_'+str(x)+str(y),(x-.65,y-.55,0),(x+.65,y+.55,.70),'bush')
    BOUNDARY.extend([
        dict(id='clip_south',kind='player_clip',phys='concrete',min=[330,619.9,-.2],max=[410,620.1,10],mode='tdm'),
        dict(id='clip_north',kind='player_clip',phys='concrete',min=[330,L.get('tdm_clip_north_y',NORTH)-.1,-.2],max=[410,L.get('tdm_clip_north_y',NORTH)+.1,10],mode='tdm'),
        dict(id='clip_west',kind='player_clip',phys='concrete',min=[329.9,620,-.2],max=[330.1,NORTH,10],mode='tdm'),
        dict(id='clip_east',kind='player_clip',phys='concrete',min=[409.9,620,-.2],max=[410.1,NORTH,10],mode='tdm'),
        dict(id='ceiling',kind='player_clip',phys='concrete',min=[330,620,10],max=[410,NORTH,10.2],mode='tdm'),
    ])
def road_details(root):
    paint=C.material('RoadPaint','asphalt',None,(.72,.69,.58),rough=.88)
    for y in range(632,int(ROAD0),5):
        ob=C.box('SH3_Centre_Dash',(.10,2.25,.001),(370,y,.0015),paint,.0);C.parent_keep(ob,root)
    for x in range(292,450,6):
        ob=C.box('SH3_CrossStreet_Dash',(2.6,.10,.001),(x,(ROAD0+ROAD1)/2,.0015),paint,.0);C.parent_keep(ob,root)
    tex=ROOT/'assets/maps/showhome/kit/tex/ground'
    for name,size,points in [('gully',(.40,.72),[(366.72,630),(373.28,650),(351,ROAD1-.35)]),('manhole',(.85,.85),[(368.4,648)]),('inspection',(.60,.60),[(365.35,640),(374.65,655)])]:
        m=C.bc.material('M_V3_Road_'+name,(1,1,1),rough=.74,metal=.30,tex=str(tex/(name+'.png')));m['phys']='metal_heavy'
        for x,y in points:
            ob=C.box('SH3_'+name,(size[0],size[1],.010),(x,y,.003),m,.002,collision=True);C.parent_keep(ob,root)
            # Face projection into the existing square decal; no world-repeat crop.
            for p in ob.data.polygons:
                if abs(p.normal.z)<.9:continue
                for li in p.loop_indices:
                    v=ob.data.vertices[ob.data.loops[li].vertex_index].co;ob.data.uv_layers[0].data[li].uv=((v.x-x)/size[0]+.5,(v.y-y)/size[1]+.5)
    wire=C.material('UtilityWire','sheet_metal',None,(.025,.03,.035),rough=.7,metal=.5)
    for a,b in [((365.25,628,6.4),(374.75,628,6.4)),((365.25,662,6.4),(374.75,662,6.4)),((365.25,628,6.4),(365.25,662,6.4)),((374.75,628,6.4),(374.75,662,6.4))]:
        a,b=Vector(a),Vector(b);pts=[]
        for i in range(17):
            t=i/16;p=a.lerp(b,t);p.z-=4*t*(1-t)*(.3 if (b-a).length<15 else .8);pts.append(p)
        for p,q in zip(pts,pts[1:]):C.bar('SH3_SaggingWire',p,q,.012,wire,root)
def place(pid,pos,yaw=0,lootable=False,locked=False,scale=1,color_variant=None,mode=None):
    assert pid in CAT,pid;rid=pid+'_'+str(sum(i['prop_id']==pid for i in INST));row=dict(id=rid,prop_id=pid,position=list(pos),yaw_deg=yaw,scale=scale,color_variant=color_variant,lootable=lootable,locked=locked)
    if mode:row['mode']=mode
    INST.append(row);return rid
def fence_run(a,b,y,yaw=0,pid='picket_panel'):
    n=math.ceil((b-a)/2);length=(b-a)/n
    assert .8<=length/2<=1.25
    for k in range(n):place(pid,(a+(k+.5)*length,y,0),yaw,scale=length/2)

def front_garden_fences():
    # Four complete street gardens, split at the actual party-wall seam.
    # Exact1.75m return units keep the same1.2m height as the2m frontage units.
    for x,inner,yaw in ((364.15,360.65,90),(375.85,379.35,-90)):
        for lo,gate,hi in ((633,636,645),(645,648,657)):
            for a,b in ((lo,gate-1),(gate+1,hi)):
                n=round((b-a)/2)
                for k in range(n):place('picket_panel',(x,a+1+2*k,0),90)
            place('garden_gate',(x,gate,0),yaw)
        lo,hi=sorted((inner,x))
        for y in (633,645,657):
            for k in range(2):place('picket_panel_short',(lo+.875+1.75*k,y,0))
def starter():
    # Centre the whole asymmetrical vehicle, not just its cargo-box pivot.
    # Local vehicle AABB centre is y=1.2; compensate after its 8-degree skew.
    truck_yaw=188;angle=math.radians(truck_yaw);cx=370+1.2*math.sin(angle);cy=648.85-1.2*math.cos(angle)
    place('moving_truck',(cx,cy,0),truck_yaw);place('armchair',(372.25,650.4,0),15)
    for prop in GARDENS['props']:place(prop['id'],prop['position'],prop['yaw'])
    for cx,side in ((339,'west'),(401,'east')):
        lo,hi=(332,350.35) if side=='west' else (389.65,408)
        fence_run(lo,cx-1,645,pid='privacy_panel');fence_run(cx+1,hi,645,pid='privacy_panel')
        place('privacy_gate',(cx,645,0),0)
    for x in (367.1,372.9):
        place('rear_garage',(x,626.9,0),180);place('city_car',(x,626.9,0),0)
    for x,yaw in ((355.5,-90),(384.5,90)):place('city_car',(x,659.9,0),yaw)
    for x in (347,393):
        for y in (649,653):place('hedge_frame',(x,y,0),90)
    front_garden_fences()
    for x in (365.25,374.75):
        for y in (628,662):place('utility_pole',(x,y,0))
    # Reusable furniture instances follow each home's original room coordinates.
    for h in L['houses']:
        angle=math.radians(h['yaw_deg']);T=Matrix.Translation(Vector(h['centre']))@Matrix.Rotation(angle,4,'Z')@Matrix.Translation(-Vector(h['old_centre']))
        west=h['centre'][0]<370
        def oldpos(x,y,z=0):return tuple(T@Vector((x if west else 72-x,y,z)))
        for pid,p,yaw in [('kitchen_base',(9.75,25,0),90),('kitchen_drawer',(9.75,26.1,0),90),('kitchen_wall',(9.15,25,1.55),90),('dining_table',(12.3,27.5,0),0),('sofa',(17.8,29,0),180),('bookcase',(18,22.5,0),180),('dresser',(15.6,27,3.2),-90),('wardrobe',(20.3,27,3.2),90),('bed',(18,24,3.2),0),('nightstand',(19.5,24.6,3.2),0)]:
            gyaw=h['yaw_deg']+(yaw if west else -yaw);place(pid,oldpos(*p),gyaw,locked=pid.startswith('kitchen_'))
        if h.get('attached_garage',h['id'].endswith('south')):
            place('garage_cabinet',(351.0 if west else 389.0,659.9,0),90 if west else -90)
            place('heat_pump',(352.5 if west else 387.5,660.5,3.2),0)
        else:place('heat_pump',(349.3 if west else 390.7,641,0),0)
    car=L['marked_blue_car'];place('city_car',car['position'],car['yaw_deg'],color_variant=car['color_variant'])
    fence_run(389.65,397.65,632.85,pid='privacy_panel')
    place('hedge_frame',(348.35,632.85,0))
    for run in L['tdm_barrier_runs']:
        a,b=(run['y0'],run['y1']) if run['axis']=='Y' else (run['x0'],run['x1']);n=math.ceil((b-a)/2);step=(b-a)/n
        for k in range(n):
            p=(run['x'],a+(k+.5)*step,0) if run['axis']=='Y' else (a+(k+.5)*step,run['y'],0)
            place('concrete_barrier',p,90 if run['axis']=='Y' else 0,scale=step/2,mode='tdm')
            if 'stable_id_start' in run:INST[-1]['id']='concrete_barrier_'+str(run['stable_id_start']+k)

def ron(data):
    def val(v):
        if v is None:return 'None'
        if isinstance(v,bool):return str(v).lower()
        if isinstance(v,str):return json.dumps(v)
        if isinstance(v,(int,float)):return str(v)
        if isinstance(v,list):return '['+', '.join(val(x) for x in v)+']'
        if isinstance(v,dict):return '('+', '.join(k+': '+val(x) for k,x in v.items())+')'
        raise TypeError(type(v))
    return '// Design frame XYZ; build-mode contract schema 1. Runtime integration follows.\n'+val(data)+'\n'
def import_instance(row,maproot):
    key=(row['prop_id'],row.get('color_variant'))
    if key in INSTANCE_TEMPLATES:
        template=INSTANCE_TEMPLATES[key];copies={o:o.copy() for o in template};obs=list(copies.values())
        for original,ob in copies.items():
            ob.name=row['id']+'__'+original['source_node_name']
            bpy.context.scene.collection.objects.link(ob);ob.parent=copies.get(original.parent)
            ob.matrix_basis=original.matrix_basis.copy()
        bpy.context.view_layer.update()
    else:
        src=ROOT/'assets'/CAT[row['prop_id']]['glb'];j,buf=read(src)
        if row.get('color_variant')=='blue' and row['prop_id']=='city_car':
            for m in j['materials']:
                if m['name']=='M_CarSilver':m['name']='M_CarBlue';m['pbrMetallicRoughness']['baseColorFactor']=[.045,.19,.34,1]
        for n in j['nodes']:n['name']=row['id']+'__'+n.get('name','Node')
        # Keep original texture paths when importing through a temporary file.
        for im in j.get('images',[]):
            if 'uri' in im:im['uri']=str((src.parent/im['uri']).resolve()).replace('\\','/')
        temp=HERE/'_cache'/('instance_'+row['id']+'.glb');save(temp,j,buf)
        before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(temp));obs=[o for o in bpy.data.objects if o not in before]
        # Snapshot the unposed hierarchy; instances share immutable mesh data.
        originals={o:o.copy() for o in obs}
        for original,ob in originals.items():
            ob['source_node_name']=original.name.split('__',1)[-1]
            ob.parent=originals.get(original.parent);ob.matrix_basis=original.matrix_basis.copy()
        INSTANCE_TEMPLATES[key]=list(originals.values())
    parents={};root=next(o for o in obs if o.parent is None);deltas={}
    for o in obs:
        if o.name.startswith(row['id']+'__OPEN_') and o.get('pose'):
            old=o.matrix_world.copy()
            rotation=o.rotation_quaternion.to_euler('XYZ') if o.rotation_mode=='QUATERNION' else o.rotation_euler.copy();o.rotation_mode='XYZ';o.rotation_euler=rotation
            if CAT[row['prop_id']]['category']=='containers':
                if o.name.split('__')[-1].startswith('OPEN_DRAWER_') and not row['lootable']:o.location=Vector(o['closed_location'])
                elif not row['lootable'] and 'axis' in o:o.rotation_euler['XYZ'.index(o['axis'])]=0
            bpy.context.view_layer.update();deltas[o.name[len(row['id'])+2:]]=o.matrix_world@old.inverted()
    root.rotation_mode='XYZ';root.location=row['position'];root.rotation_euler=(0,0,math.radians(row['yaw_deg']));root.scale=(row['scale'],)*3;bpy.context.view_layer.update();T=root.matrix_world.copy();C.parent_keep(root,maproot)
    if row.get('mode'):root['mode']=row['mode']
    for r in json.loads((ROOT/'assets'/CAT[row['prop_id']]['collision']).read_text())['volumes']:
        delta=deltas.get(r['parent'],Matrix.Identity(4));vs=[tuple(T@delta@Vector(v)) for v in r['vertices']]
        # Reconstruct the exact convex hull from its exported vertices.
        import bmesh
        bm=bmesh.new();verts=[bm.verts.new(v) for v in vs];bmesh.ops.convex_hull(bm,input=verts,use_existing_faces=False);bm.verts.index_update();v=[tuple(x.co) for x in bm.verts];f=[tuple(x.index for x in p.verts) for p in bm.faces];bm.free()
        co=C.col_mesh(row['id']+'__'+r['name'],v,f,r['phys'],r['kind'],r['walkable']);co['instance_id']=row['id'];co['mode']=row.get('mode','all');co['dynamic_parent']=r['parent'] or '';C.parent_keep(co,maproot)
    return obs
def main():
    C.bc.reset_scene();root=C.empty('SH3_MapOrigin',L['origin']);ground(root);edges(root);boundaries(root);road_details(root);starter();static=C.visuals()
    sys.path.insert(0,str(ROOT/'assets/maps/showhome'));import ground_blend as GB
    # Avoid the legacy helper's default write into the current Showhome kit.
    original_write=GB.write_contract;GB.write_contract=lambda path=None:original_write(HERE/'ground_blend_contract.json')
    GB.BASES['M_GND_SoilFar']=('worksite_packed_dirt',6,'earth');GB.BASES['M_GND_Gravel']=('gravel_compacted',1,'earth');GB.setup_preview();GB.prepare_export()
    for mat in GB.STANDARD.values():
        raw=mat.get('showhome_ground_blend')
        if raw is not None:
            contract=json.loads(raw) if isinstance(raw,str) else C.plain(raw);contract['contract']='maps/showhome_v3/ground_blend_contract.json';mat['showhome_ground_blend']=json.dumps(contract)
    C.export_glb(KIT/'ground.glb',[root]+static);externalize(KIT/'ground.glb',HERE/'textures');GB.restore_preview()
    cols=[o for o in bpy.context.scene.objects if o.name.startswith('COL_')];C.export_collision(KIT/'collision_ground.json',cols);C.write(KIT/'ground_steps.json',STEP);C.write(KIT/'foliage.json',FOL)
    bpy.ops.wm.save_as_mainfile(filepath=str(KIT/'ground.blend'))
    with bpy.data.libraries.load(str(KIT/'houses.blend'),link=False) as (src,dst):dst.objects=[n for n in src.objects if n.startswith(('SH3_','COL_'))]
    for o in dst.objects:
        if o is not None:
            bpy.context.scene.collection.objects.link(o)
            if o.name.startswith('COL_'):o.hide_render=True
    for row in INST:import_instance(row,root)
    # Editable markers are kept separate from the fixed collision payload.
    data=dict(schema=1,map_id='showhome_v3',frame='design world XYZ metres',origin=L['origin'],instances=INST,player_clips=BOUNDARY,spawns=[],extracts=[],loot_spots=[],suggested_spawn_regions=[{'team':'A','suggested':True,'aabb':[332,623,345,641]},{'team':'B','suggested':True,'aabb':[395,623,408,641]}])
    C.write(HERE/'placements.generated.json',data);proposal=HERE/'placements.proposed.ron';proposal.write_text(ron(data),encoding='utf8');starterfile=HERE/'placements.ron'
    if not (HERE/'HANDOFF.json').exists():starterfile.write_text(ron(data),encoding='utf8')
    allcols=[o for o in bpy.context.scene.objects if o.name.startswith('COL_')];rows=C.export_collision(HERE/'collision_assembled_qa.json',allcols)
    fixed=json.loads((KIT/'collision_houses.json').read_text())['volumes']+json.loads((KIT/'collision_ground.json').read_text())['volumes'];C.write(HERE/'collision.json',dict(schema=1,frame='design world XYZ metres',plane_convention='dot(n,p)<=d',volumes=fixed,instances_are_separate=True))
    C.write(HERE/'phase1_report.json',dict(houses=json.loads((KIT/'houses_report.json').read_text()),fixed_collision_volumes=len(fixed),assembled_collision_volumes=len(rows),prop_instances=len(INST),ground_triangles=C.triangles(static),foliage_volumes=len(FOL),kerb_steps=len(STEP),runtime_integration='build mode and loader follow; assets ready, not currently selectable as a game map'))
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'showhome_v3.blend'))
    if '--render' in sys.argv:
        cam=C.stage();bpy.context.scene.cycles.samples=16
        for name,eye,target,ortho in [('aerial',(430,594,72),(370,645,3),115),('street',(370,ROAD0+4,1.6),(370,635,3),None),('garden',(339,646,1.6),(342,636,1.6),None),('interior',(355,635,1.6),(358,640,1.4),None),('layout_top',(370,649,105),(370,649,0),104)]:C.render(cam,HERE/('renders/'+name+'.png'),eye,target,ortho)
    print('CORE_READY',len(INST),'instances',len(fixed),'fixed collision volumes',flush=True)
if __name__=='__main__':main()
