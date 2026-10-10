"""Independent serialized-asset QA. Run with Python after CORE_READY; --library-only is safe during assembly."""
import argparse, collections, hashlib, json, math, struct, sys
from pathlib import Path
import numpy as np
from gltf_shared import read

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PHYS={'glass','wood_thin','wood_thick','sheet_metal','metal_heavy','drywall','concrete','brick','cladding','foliage_thin','foliage_dense','fabric','plastic','soil','grass','gravel','sand','asphalt','paving','water'}
G=np.array([[1,0,0],[0,0,-1],[0,1,0]])
FAIL=[];WARN=[];STATS={};FILES={};PROPS={}

def check(ok,message,detail=None):
    if not ok:FAIL.append(dict(check=message,detail=detail))
    return bool(ok)

def jsonfile(path):
    path=Path(path);FILES[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text(encoding='utf8'))

def matrix(n):
    if 'matrix' in n:return np.array(n['matrix']).reshape(4,4).T
    x,y,z,w=n.get('rotation',[0,0,0,1])
    r=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    m=np.eye(4);m[:3,:3]=r@np.diag(n.get('scale',[1,1,1]));m[:3,3]=n.get('translation',[0,0,0]);return m

class GLB:
    def __init__(self,path,paint=False):
        self.path=Path(path);self.j,self.buf=read(path);self.parents={c:i for i,n in enumerate(self.j['nodes']) for c in n.get('children',[])};self.worlds={}
        raw=self.path.read_bytes();FILES[str(self.path.relative_to(ROOT))]=hashlib.sha256(raw).hexdigest()
        check(struct.unpack_from('<III',raw)==(0x46546c67,2,len(raw)),'GLB header',str(self.path))
        for view in self.j.get('bufferViews',[]):check(view.get('byteOffset',0)+view['byteLength']<=len(self.buf),'GLB buffer bounds',str(self.path))
        for im in self.j.get('images',[]):
            check('uri' in im and (self.path.parent/im['uri']).is_file(),'External image resolves',dict(file=str(self.path),image=im))
        for mat in self.j.get('materials',[]):
            check(mat.get('extras',{}).get('phys') in PHYS,'Material phys',dict(file=str(self.path),material=mat.get('name')))
        count=0
        for mesh in self.j.get('meshes',[]):
            for primitive in mesh['primitives']:
                count+=1;at=primitive['attributes'];n=self.j['accessors'][at['POSITION']]['count']
                needs_paint=paint(mesh['name']) if callable(paint) else paint
                for key in ('POSITION','NORMAL','TEXCOORD_0')+ (('COLOR_0',) if needs_paint else ()):
                    if not check(key in at,'Required vertex attribute',dict(file=str(self.path),mesh=mesh['name'],attribute=key)):continue
                    arr=self.access(at[key]);check(len(arr)==n and np.isfinite(arr).all(),'Finite consistent vertex data',dict(file=str(self.path),mesh=mesh['name'],attribute=key))
                for key in ('TANGENT','COLOR_0'):
                    if key in at:check(np.isfinite(self.access(at[key])).all(),'Finite optional vertex data',dict(file=str(self.path),mesh=mesh['name'],attribute=key))
                if 'indices' in primitive:check(self.access(primitive['indices']).max()<n,'Triangle index bounds',str(self.path))
        self.primitive_count=count

    def access(self,i):
        a=self.j['accessors'][i];v=self.j['bufferViews'][a['bufferView']];dt=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1',5122:'<i2',5120:'i1'}[a['componentType']]);num={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
        return np.ndarray((a['count'],num),dtype=dt,buffer=self.buf,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',num*dt.itemsize),dt.itemsize))

    def world(self,i):
        if i not in self.worlds:self.worlds[i]=(self.world(self.parents[i]) if i in self.parents else np.eye(4))@matrix(self.j['nodes'][i])
        return self.worlds[i]

    def points(self,select=lambda name:True):
        out=[]
        for i,n in enumerate(self.j['nodes']):
            if 'mesh' not in n or not select(n.get('name','')):continue
            for p in self.j['meshes'][n['mesh']]['primitives']:
                vs=self.access(p['attributes']['POSITION']);out.append((np.c_[vs,np.ones(len(vs))]@self.world(i).T)[:,:3]@G.T)
        return np.vstack(out) if out else np.empty((0,3))

def collision(path):
    rows=jsonfile(path)['volumes'];actual=[]
    for r in rows:
        vs=np.array(r['vertices']);ps=np.array(r['planes']);norms=np.linalg.norm(ps[:,:3],axis=1)
        check(r['phys'] in PHYS,'Collision phys',r['name']);check(np.isfinite(vs).all() and np.isfinite(ps).all(),'Collision finite',r['name'])
        check(np.allclose(norms,1,atol=.0002),'Unit collision planes',r['name'])
        check((vs@ps[:,:3].T-ps[:,3]).max()<.00025,'Convex collision planes contain vertices',r['name'])
        spans=np.ptp(vs@(ps[:,:3]/norms[:,None]).T,axis=0);thin=float(spans.min());actual.append((thin,r['name'],r['phys']))
        check(thin>=.00485,'Collision minimum 5mm thickness',dict(name=r['name'],actual_m=thin))
        check(abs(thin-r['thickness_m'])<.00015,'Serialized thickness matches geometry',r['name'])
        check(np.allclose(vs.min(0),r['aabb']['min'],atol=.00002) and np.allclose(vs.max(0),r['aabb']['max'],atol=.00002),'Collision AABB matches vertices',r['name'])
    return rows,sorted(actual)

def library():
    cat=jsonfile(ROOT/'assets/props/catalog.json')['props'];entries=[e for e in cat if 'showhome_v3' in e.get('tags',[])];check(len(entries)>=35,'Required v3 library entries retained',len(entries));check(len({e['id'] for e in entries})==len(entries),'Unique library ids')
    low=[];opened=0;slots=0;vehicles={};skin=[];glass=[]
    for e in entries:
        props=[]
        for key in ('glb','lod1'):props.append(GLB(ROOT/'assets'/e[key]))
        rows,thin=collision(ROOT/'assets'/e['collision']);low.extend(thin);names={n.get('name') for n in props[0].j['nodes']}
        PROPS[e['id']]=(props[0],rows,e)
        check(len(rows)==e['collision_volumes'],'Catalog collision count',e['id'])
        for lod in props:
            ln={n.get('name') for n in lod.j['nodes']}
            for p in e['openable_parts']:check(p['name'] in ln,'LOD moving part retained',dict(prop=e['id'],part=p['name'],file=str(lod.path)))
            for slot in e['loot_slots']:check(slot in ln,'LOD loot slot retained',dict(prop=e['id'],slot=slot,file=str(lod.path)))
        opened+=len(e['openable_parts']);slots+=len(e['loot_slots'])
        for r in rows:check(r['parent'] in names,'Collision moving/root parent resolves',dict(prop=e['id'],volume=r['name'],parent=r['parent']))
        for p in e['openable_parts']:
            check(any(r['parent']==p['name'] for r in rows),'Moving part has moving collision',dict(prop=e['id'],part=p['name']))
        if e['id'] in ('city_car','moving_truck'):
            counts=collections.Counter(r['phys'] for r in rows);vehicles[e['id']]=dict(counts)
            check(all(counts[p]>0 for p in ('glass','sheet_metal','metal_heavy')),'Vehicle has split body/glass/heavy collision',dict(prop=e['id'],materials=dict(counts)))
        for r in rows:
            if r['phys']=='sheet_metal':
                skin.append(r['thickness_m']);check(r['thickness_m']<=.0102,'Sheet-metal skin at most 10mm',dict(prop=e['id'],volume=r['name'],thickness_m=r['thickness_m']))
            if r['phys']=='glass':
                glass.append(r['thickness_m']);check(.00485<=r['thickness_m']<=.0202,'Glass pane uses thin convex collision',dict(prop=e['id'],volume=r['name'],thickness_m=r['thickness_m']))
    if min(glass)<.0098:WARN.append(dict(check='Sloped/bevelled glass prism minimum span is slightly below nominal 10mm',actual_min_m=min(glass)))
    STATS['library']=dict(props=len(entries),moving_parts=opened,loot_slots=slots,thinnest=sorted(low)[:12],vehicle_materials=vehicles,sheet_metal_max_m=max(skin),glass_min_m=min(glass),glass_max_m=max(glass))

def contains(r,p):return all(np.dot(n[:3],p)<=n[3]+.00015 for n in r['planes'])

def house_layout():return jsonfile(HERE/'layout.json')

def garage_offset_for(h):return np.array(h['centre'])-np.array([386 if h['centre'][0]>370 else 354,636,0])

def has_attached_garage(h):return h.get('attached_garage',h['id'].endswith('_south'))

def garage_point_for(h,x,y,z):return np.array([740-x if h['centre'][0]>370 else x,1272-y if h['id'].endswith('_north') else y,z])+garage_offset_for(h)

def building_footprints():
    layout=house_layout();out=[]
    for east in (False,True):
        homes=[h for h in layout['houses'] if (h['centre'][0]>370)==east];x=homes[0]['centre'][0]
        out.append([x-(8.15 if east else 2.15),min(h['centre'][1] for h in homes)-6.15,x+(2.15 if east else 8.15),max(h['centre'][1] for h in homes)+6.15])
        for h in (h for h in homes if has_attached_garage(h)):
            ps=np.array([garage_point_for(h,352,624,0),garage_point_for(h,362.15,630.15,0)]);lo=ps.min(0);hi=ps.max(0);out.append([lo[0],lo[1],hi[0],hi[1]])
    return out

def houses():
    glb=GLB(HERE/'kit/houses.glb',paint=True);rows,thin=collision(HERE/'kit/collision_houses.json');bounds={}
    for h in house_layout()['houses']:
        name=h['id'];pts=glb.points(lambda node:node.startswith('SH3_'+name+'_Garage_'));cs=[r for r in rows if r['name'].startswith('COL_'+name+'_GARAGE_')]
        if not has_attached_garage(h):
            check(not len(pts) and not cs,'Unassigned homes have no attached garage art or collision',name);continue
        vs=np.vstack([r['vertices'] for r in cs]);mn=vs.min(0);mx=vs.max(0);ps=np.array([garage_point_for(h,352,624,-.12),garage_point_for(h,362.165,630.15,5.4)]);expect_min=ps.min(0);expect_max=ps.max(0)
        check(np.allclose(mn,expect_min,atol=.001) and np.allclose(mx,expect_max,atol=.001),'Garage collision world bounds',dict(home=name,min=mn.tolist(),max=mx.tolist()))
        check(np.allclose(pts.min(0),mn,atol=.001) and np.allclose(pts.max(0),mx,atol=.001),'Garage GLB affine world bounds match collision',name)
        point=lambda x,y,z:garage_point_for(h,x,y,z)
        for label,p,phys in [('shutter',point(362.133,627,2),'sheet_metal'),('garden wall',point(352.15,627,1),'concrete'),('end wall',point(357,624.15,1),'concrete'),('header',point(362,627,3),'concrete')]:check(any(contains(r,p) and r['phys']==phys for r in cs),'Positive garage solid collision',dict(home=name,part=label))
        check(not any(contains(r,point(362.133,627,.5)) for r in rows),'Garage slide gap remains open',name)
        for label,p,phys in [('end glass',point(357,624.04,3.7),'glass'),('driveway glass',point(362.11,627,3.7),'glass'),('privacy screen',point(352.01,627.07,4.7),'wood_thin')]:check(any(contains(r,p) and r['phys']==phys for r in cs),'Terrace glass/privacy positive collision',dict(home=name,part=label))
        check(not any('Par_Coping' in r['name'] or r['name'].endswith(('GardenPar','SouthPar','FrontPar')) for r in cs),'Old solid cream terrace parapets removed',name)
        check(all(r.get('exception')=='privacy_screen' for r in cs if '_Privacy' in r['name']),'Privacy screen exception is serialized',name)
        bounds[name]=dict(min=mn.tolist(),max=mx.tolist())
    glass=next((m for m in glb.j['materials'] if m.get('name')=='M_V3_TerraceClearGlass'),{})
    check(glass.get('alphaMode')=='BLEND' and .05<=glass.get('pbrMetallicRoughness',{}).get('baseColorFactor',[0,0,0,1])[3]<=.3,'Terrace glass ordinary transparent BLEND material',glass.get('name'))
    report=jsonfile(HERE/'kit/houses_report.json');windows=[o for o in report['openings'] if o['role']=='street_upper_window'];check(len(windows)==8 and len({(o['width_m'],o['height_m'],o['sill_m'],o['head_m']) for o in windows})==1,'All inward upper windows match',windows)
    garden_windows=[o for o in report['openings'] if o['role']=='garden_window']
    check(len(garden_windows)==8 and all(sum(o['home']==h['id'] and o.get('floor')==floor for o in garden_windows)==1 for h in house_layout()['houses'] for floor in ('GF','UF')),'Exactly one garden window per home floor',garden_windows)
    check(all(abs(o['width_m']-2.364)<.001 and abs(o['height_m']-1.832)<.001 and (o['sill_m'],o['head_m'])==((.75,2.6) if o.get('floor')=='GF' else (3.85,5.7)) for o in garden_windows),'Garden windows match full-size driveway treatment',garden_windows)
    check(len([o for o in report['openings'] if o['role']=='garden_door' and o['width_m']>1])==4,'Garden doors retained with full clear width')
    check({g['home'] for g in report['attached_garages']}=={h['id'] for h in house_layout()['houses'] if has_attached_garage(h)},'Attached garages belong to selected homes')
    for h in house_layout()['houses']:
        angle=math.radians(h['yaw_deg']);c,s=math.cos(angle),math.sin(angle);R=np.array([[c,-s,0],[s,c,0],[0,0,1]])
        def house_point(x,y,z):
            local=np.array([72-x if h['centre'][0]>370 else x,y,z])-np.array(h['old_centre']);return R@local+np.array(h['centre'])
        def garden_point(x,z):
            return house_point(x,22,z)
        trim_points=glb.points(lambda name:name=='SH3_'+h['id']+'_Trim_trim')
        for floor,y,z0,z1,fw in (('GF',21.9,.75,2.6,.14),('UF',21.85,3.85,5.7,.27)):
            for x,yy,z in ((16.5-fw,y-.018,z0),(16.5,y-.018,z1+fw),(18.9+fw,y-.018,z0),(16.5-fw-.05,y-.019,z0-.09)):
                p=house_point(x,yy,z);check(len(trim_points)>0 and np.linalg.norm(trim_points-p,axis=1).min()<.001,'Garden window cream surrounds survive source clipping',dict(home=h['id'],floor=floor,sample_world=p.tolist()))
        for z0,z1 in ((.75,2.6),(3.85,5.7)):
            for x in (16.55,17.7,18.85):
                for z in (z0+.05,(z0+z1)/2,z1-.05):
                    p=garden_point(x,z);check(not any(contains(r,p) for r in rows),'Garden window collision stays open',dict(home=h['id'],sample_world=p.tolist()))
            for x,z in ((16.4,(z0+z1)/2),(19,(z0+z1)/2),(17.7,z0-.10),(17.7,z1+.10)):
                p=garden_point(x,z);check(any(r['phys']=='concrete' and contains(r,p) for r in rows),'Garden window supports remain solid',dict(home=h['id'],sample_world=p.tolist()))
        check(not any(contains(r,garden_point(10.5,1)) for r in rows),'Garden door collision stays open',h['id'])
        if has_attached_garage(h):
            north=h['id'].endswith('_north');face=9 if north else 21
            for u,z in ((29.5 if north else 26,1),(26.8 if north else 24.2,4.2)):
                local=np.array([72-face if h['centre'][0]>370 else face,u,z])-np.array(h['old_centre']);p=R@local+np.array(h['centre']);check(not any(contains(r,p) for r in rows),'Garage house and terrace connections stay open',dict(home=h['id'],sample_world=p.tolist()))
            connections=[o for o in report['openings'] if o['home']==h['id'] and o['role'] in ('garage_connection','garage_deck_door')];check(len(connections)==2 and all(o['width_m']>1 and o['height_m']>=1.8 for o in connections),'Garage house connections have full standing clearances',connections)
        p=np.array([h['centre'][0],house_layout()['party_wall_y'],1.5]);check(any(r['phys']=='concrete' and contains(r,p) for r in rows),'Garden changes retain solid party wall',h['id'])
        oldx=21 if h['id'].endswith('_south') else 9;local=np.array([72-oldx if h['centre'][0]>370 else oldx,27,8])-np.array(h['old_centre']);angle=math.radians(h['yaw_deg']);c,s=math.cos(angle),math.sin(angle);p=np.array([[c,-s,0],[s,c,0],[0,0,1]])@local+np.array(h['centre'])
        check(any(contains(r,p) and r['phys'] in ('cladding','concrete') for r in rows),'Exposed gable wall has solid collision',dict(home=h['id'],sample_world=p.tolist()))
        gable=next((r for r in rows if r['name']=='COL_'+h['id']+'_ExposedGable'),None)
        if check(gable is not None,'Exposed gable has its own convex wall',h['id']):
            cy=h['centre'][1];y0,y1=(cy-6,cy-5.7) if h['id'].endswith('_south') else (cy+5.7,cy+6)
            check(abs(gable['aabb']['min'][1]-y0)<.001 and abs(gable['aabb']['max'][1]-y1)<.001 and abs(gable['thickness_m']-.3)<.001,'Gable thickness entirely inward',h['id'])
            outside=p+np.array([0,-.1 if h['id'].endswith('_south') else .1,0]);check(not any(contains(r,outside) for r in rows),'Gable adds no invisible exterior offset',h['id'])
    STATS['houses']=dict(collision_volumes=len(rows),world_garage_bounds=bounds,garden_windows=len(garden_windows),garden_windows_per_home_per_floor=1,thinnest=thin[:8])

def overlap(a,b):return min(a[2],b[2])-max(a[0],b[0])>.001 and min(a[3],b[3])-max(a[1],b[1])>.001

def ground():
    glb=GLB(HERE/'kit/ground.glb',paint=lambda name:name.startswith('SH3_Ground_'));rows,thin=collision(HERE/'kit/collision_ground.json');surfs=[r for r in rows if r['name'].startswith('COL_Surface_')];footprints=building_footprints()
    pts=glb.points(lambda name:name.startswith('SH3_Ground_'));check(np.allclose(pts.min(0),[290,600,0],atol=.001) and np.allclose(pts.max(0),[450,house_layout()['origin'][1]+house_layout()['size'][1],.008],atol=.001),'Ground GLB affine world bounds',[pts.min(0).tolist(),pts.max(0).tolist()])
    for i,node in enumerate(glb.j['nodes']):
        if 'mesh' not in node or not node.get('name','').startswith('SH3_Ground_'):continue
        for prim in glb.j['meshes'][node['mesh']]['primitives']:
            at=prim['attributes'];colors=glb.access(at['COLOR_0']);ca=glb.j['accessors'][at['COLOR_0']]
            if ca.get('normalized'):colors=colors/np.iinfo(colors.dtype).max
            check(colors.shape[1]==4 and colors.min()>=-.0001 and colors.max()<=1.0001,'Ground RGBA masks in independent 0..1 range',node['name'])
            vs=glb.access(at['POSITION']);vs=(np.c_[vs,np.ones(len(vs))]@glb.world(i).T)[:,:3]@G.T;ix=glb.access(prim['indices']).reshape(-1,3);centres=vs[ix].mean(axis=1)
            for f in footprints:
                count=int(((centres[:,0]>f[0]+.001)&(centres[:,0]<f[2]-.001)&(centres[:,1]>f[1]+.001)&(centres[:,1]<f[3]-.001)).sum());check(count==0,'Ground art triangle centres stay out of building holes',dict(mesh=node['name'],footprint=f,intruding_triangles=count))
    check(bool(surfs),'Ground uses exact compact surface collision')
    rects=[(r['aabb']['min'][0],r['aabb']['min'][1],r['aabb']['max'][0],r['aabb']['max'][1]) for r in surfs]
    for i,r in enumerate(surfs):
        check(not any(overlap(rects[i],f) for f in footprints),'Ground surface stays out of building holes',dict(volume=r['name'],phys=r['phys'],rect=rects[i]))
        for k in range(i):check(not overlap(rects[i],rects[k]),'Ground surface collision does not overlap',dict(first=r['name'],second=surfs[k]['name']))
    for mat in glb.j['materials']:
        if not mat.get('name','').startswith('M_GND_'):continue
        ex=mat.get('extras',{});payload=json.loads(ex.get('showhome_ground_blend','{}'))
        check(ex.get('showhome_ground_colour0')=='blend_masks' and ex.get('showhome_ground_opacity')==1,'Ground mask material extras',mat['name'])
        check(payload.get('vertex_colour_is_albedo') is False and payload.get('colour_attribute_glTF')=='COLOR_0' and payload.get('order')==['R','G','B','A'],'Ground RGBA mask convention',mat['name'])
        check(mat.get('alphaMode','OPAQUE')=='OPAQUE','Ground remains opaque',mat['name'])
        contract=payload.get('contract','');target=(HERE/'ground_blend_contract.json').resolve()
        check(any(candidate.resolve()==target and candidate.is_file() for candidate in (ROOT/contract,ROOT/'assets'/contract)),'Ground references delivered v3 contract',dict(material=mat['name'],contract=contract))
    STATS['ground']=dict(collision_volumes=len(rows),surface_rectangles=len(surfs),surface_materials=dict(collections.Counter(r['phys'] for r in surfs)),thinnest=thin[:8])

def placements():
    path=HERE/'placements.reference.json'
    if not path.exists():path=HERE/'placements.generated.json'
    data=jsonfile(path);items=data['instances'];check(len({r['id'] for r in items})==len(items),'Unique prop-instance ids')
    for key in ('player_clips','spawns','extracts','loot_spots'):
        marker=data.get(key,[]);check(len({r['id'] for r in marker})==len(marker),'Unique editable marker ids',key)
    runs=[];footprints=building_footprints();party_y=house_layout()['party_wall_y']
    for lo,hi in ((332,footprints[0][0]),(footprints[2][2],408)):
        gates=[r for r in items if 'gate' in r['prop_id'] and lo<r['position'][0]<hi and abs(r['position'][1]-party_y)<.001]
        if not check(len(gates)==1,'Exactly one divider gate per garden pair',[lo,hi]):continue
        centre=gates[0]['position'][0]
        panels=[r for r in items if PROPS[r['prop_id']][2]['category']=='fences' and 'gate' not in r['prop_id'] and 'site' not in r['prop_id'] and abs(r['position'][1]-party_y)<.001 and lo-1<r['position'][0]<hi+1]
        def nominal_width(pid):
            source=PROPS[pid][0];posts=[]
            for node in source.j['nodes']:
                if 'mesh' in node and 'post' in node.get('name','').lower():
                    vs=source.points(lambda name:name==node['name']);posts.append((vs[:,0].min()+vs[:,0].max())/2)
            return max(posts)-min(posts) if len(posts)>=2 else 2
        widths={r['prop_id']:nominal_width(r['prop_id']) for r in panels}
        intervals=sorted((r['position'][0]-widths[r['prop_id']]*r['scale']/2,r['position'][0]+widths[r['prop_id']]*r['scale']/2) for r in panels);gaps=[];cursor=lo
        for a,b in intervals:
            if a-cursor>.002:gaps.append([cursor,a])
            check(a>=lo-.002 and b<=hi+.002,'Divider fence inside garden endpoints',[a,b]);cursor=max(cursor,b)
        if hi-cursor>.002:gaps.append([cursor,hi])
        check(len(gaps)==1 and np.allclose(gaps[0],[centre-1,centre+1],atol=.002),'Divider has exactly the intended 2m gate gap',dict(centre=centre,gaps=gaps))
        for r in panels:check(.8<=r['scale']<=1.25 and abs(r['yaw_deg'])<.001,'Divider scale/yaw valid',r['id'])
        runs.append(dict(garden_x=[lo,hi],panels=len(panels),gate_gaps=gaps))
    layout=house_layout();end=layout['side_garden_end_y'];north=layout['origin'][1]+layout['size'][1]
    check(end==671 and layout['front_street'][1]-end==2,'Five metre garden extension retains 2m pavement')
    fol=jsonfile(HERE/'kit/foliage.json')
    for side in ('west','east'):
        row=next((f for f in fol if f['name']=='FOL_hedge_roadside_'+side),None)
        check(row is not None and abs(row['aabb']['max'][1]-end)<.001,'Roadside garden has continuous hedge return',side)
    blue=[r for r in items if r['prop_id']=='city_car' and r.get('color_variant')=='blue'];check(len(blue)==1,'Marked road position has one blue car')
    barriers=[r for r in items if r['prop_id']=='concrete_barrier'];check(len(barriers)>0 and all(r.get('mode')=='tdm' for r in barriers),'Road closures are TDM-only reusable barriers')
    check(len(barriers)==6 and all(abs(r['position'][1]-(layout['side_garden_end_y']-.65))<.001 for r in barriers),'TDM closure aligns with roadside hedges')
    clip=next(r for r in data['player_clips'] if r['id']=='clip_north');check(abs(clip['min'][1]-(layout.get('tdm_clip_north_y',north)-.1))<.001,'TDM clip follows enlarged core')
    front_gates=[r for r in items if r['prop_id']=='garden_gate']
    check(len(front_gates)==4 and {(round(r['position'][0],2),r['position'][1]) for r in front_gates}=={(x,y) for x in (364.15,375.85) for y in (636,648)},'Every street garden has its own entrance gate')
    shorts=[r for r in items if r['prop_id']=='picket_panel_short']
    check(len(shorts)==12 and all(r['position'][1] in (633,layout['party_wall_y'],657) and r['scale']==1 for r in shorts),'Front garden returns and party-seam dividers keep full fence height')
    fronts=[r for r in items if r['prop_id']=='picket_panel']
    check(len(fronts)==20 and all(r['scale']==1 and abs(r['yaw_deg'])==90 for r in fronts),'Both attached pairs have complete picket frontages')
    STATS['placements']=dict(instances=len(items),source_file=path.name,divider_runs=runs,front_gardens=4,front_gates=len(front_gates),front_fence_panels=len(fronts)+len(shorts),handed_off=(HERE/'HANDOFF.json').exists())

def assembled():
    rows,thin=collision(HERE/'collision_assembled_qa.json');by_name={r['name']:r for r in rows};data=jsonfile(HERE/'placements.generated.json');checked=0;H=np.eye(4);H[:3,:3]=G
    fixed=jsonfile(HERE/'kit/collision_houses.json')['volumes']+jsonfile(HERE/'kit/collision_ground.json')['volumes'];payload=jsonfile(HERE/'collision.json')['volumes']
    check(len(payload)==len(fixed),'Fixed runtime collision count matches latest source kit',dict(runtime=len(payload),source=len(fixed)))
    for volume in fixed:
        target=by_name.get(volume['name'])
        if not check(target is not None,'Latest fixed source collision exists in assembly',volume['name']):continue
        expected=np.array(volume['vertices']);actual=np.array(target['vertices']);distances=np.linalg.norm(expected[:,None,:]-actual[None,:,:],axis=2)
        check(float(distances.min(axis=1).max())<.0004 and float(distances.min(axis=0).max())<.0004,'Assembled fixed collision matches latest source world geometry',volume['name'])
    for inst in data['instances']:
        source,local,entry=PROPS[inst['prop_id']];angle=math.radians(inst['yaw_deg']);c,s=math.cos(angle),math.sin(angle);T=np.eye(4);T[:3,:3]=np.array([[c,-s,0],[s,c,0],[0,0,1]])*inst['scale'];T[:3,3]=inst['position'];deltas={}
        if entry['category']=='containers' and not inst['lootable']:
            for i,node in enumerate(source.j['nodes']):
                if not node.get('name','').startswith('OPEN_'):continue
                props=node.get('extras',{});old=H@source.world(i)@np.linalg.inv(H);closed=np.eye(4);closed[:3,3]=props.get('closed_location',old[:3,3]) if node['name'].startswith('OPEN_DRAWER_') else old[:3,3];deltas[node['name']]=closed@np.linalg.inv(old)
        for volume in local:
            name='COL_'+inst['id']+'__'+volume['name'];target=by_name.get(name)
            if not check(target is not None,'Assembled instance collision exists',name):continue
            vs=np.array(volume['vertices']);expected=(np.c_[vs,np.ones(len(vs))]@(T@deltas.get(volume['parent'],np.eye(4))).T)[:,:3];actual=np.array(target['vertices'])
            distances=np.linalg.norm(expected[:,None,:]-actual[None,:,:],axis=2)
            check(float(distances.min(axis=1).max())<.0004 and float(distances.min(axis=0).max())<.0004,'Assembled prop affine pose/scale matches source collision',name);checked+=1
    STATS['assembled']=dict(collision_volumes=len(rows),fixed_source_volumes_compared=len(fixed),prop_volumes_compared_to_source=checked,thinnest=thin[:8])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--library-only',action='store_true');args=parser.parse_args()
    stages=[library] if args.library_only else [library,houses,ground,placements,assembled]
    for stage in stages:
        try:stage()
        except Exception as exc:FAIL.append(dict(check=stage.__name__+' raised',detail=str(exc)))
    report=dict(schema=1,scope='library only' if args.library_only else 'final serialized core and v3 library props',passed=not FAIL,failures=FAIL,warnings=WARN,stats=STATS,input_sha256=FILES)
    (HERE/'QA.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(passed=not FAIL,failure_count=len(FAIL),failure_groups=dict(collections.Counter(r['check'] for r in FAIL)),failures=FAIL[:30],stats={k:{x:y for x,y in v.items() if x!='thinnest'} for k,v in STATS.items()}),indent=2))
    return 0 if not FAIL else 1

if __name__=='__main__':sys.exit(main())
