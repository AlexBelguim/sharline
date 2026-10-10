"""Independent serialized extension checks, including player box clearance."""
import sys,json
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
import verify as V
j=V.GLB(HERE/'extension.glb');rows,thin=V.collision(HERE/'collision.json');report=V.jsonfile(HERE/'report.json');route=V.jsonfile(HERE/'stairs_route.json')
V.check(report.get('source_revision')=='2026-10-10_perpendicular_road_straight_ramp_recessed_homes','Latest revised extension source was rebuilt before delivery')
V.check(len(report['homes'])==3,'Three extension homes')
V.check(all(h['front']=='-Y' for h in report['homes']),'All extension homes face the road')
V.check(all(h.get('added_gable') and not h.get('attached_garage',True) for h in report['homes']),'All three homes stand separately with closed former party gables and no attached garage')
V.check(report.get('residential_plots')==[[332,684,356,728],[358,684,382,728],[384,684,408,728]],'Three equal24x44m roadside plots')
V.check([h['centre'] for h in report['homes']]==[[344,700,0],[370,700,0],[396,700,0]],'Standalone homes are recessed4m for visible drive-ups')
V.check(report['apartment']['storeys']==5 and report['apartment']['floor_elevations_m']==[0,3.2,6.4,9.6,12.8],'Five-storey apartment elevations')
V.check(report['homes'][2].get('added_gable') is not None,'Detached former party end closed')
V.check(report['apartment'].get('yaw_deg')==90,'Apartment rotation exported as90 degrees')
V.check(report['apartment'].get('count')==4 and report['apartment'].get('standing_count')==3,'Four campus footprints with three standing frames')
V.check(report['apartment']['building_bounds']==[[345,750,371,804],[397,750,423,804],[345,838,371,892],[397,838,423,892]],'Four widely spaced campus footprints')
site=report['site_bounds'];V.check(site[2]-site[0]==site[3]-site[1] and site[2]-site[0]>=140,'Construction perimeter is a larger square')
V.check(len(report.get('pits',[]))>=5 and len(report.get('mounds',[]))>=5,'Excavations and physical spoil hills added')
routes=route.get('building_routes',[route]);V.check(len(routes)==3,'All three standing frames have upper-floor stair routes')
for prefix,shift in zip(('EXT_Stair','EXT_B1_Stair','EXT_B2_Stair'),((0,0),(52,0),(0,88))):
    visual_stairs=j.points(lambda name:name.startswith(prefix));dx,dy=shift
    V.check(len(visual_stairs)>0 and visual_stairs[:,0].min()>362+dx and visual_stairs[:,0].max()<369+dx and visual_stairs[:,1].min()>751+dy and visual_stairs[:,1].max()<758+dy,'Actual exported stair meshes follow each east-facing frame',prefix)
for prefix,bounds in zip(('EXT_ApartmentFloor','EXT_B1_ApartmentFloor','EXT_B2_ApartmentFloor'),report['apartment']['building_bounds']):
    pts=j.points(lambda name:name.startswith(prefix));V.check(len(pts)>0 and np.allclose(pts.min(0)[:2],bounds[:2],atol=.001) and np.allclose(pts.max(0)[:2],bounds[2:],atol=.001),'Exported building floor bounds match the square-site plan',prefix)
parking=report['parking_basement']
V.check(len(j.j.get('extensions',{}).get('KHR_lights_punctual',{}).get('lights',[]))>=10,'Garage work lights are exported as real glTF punctual lights')
V.check(parking['minimum_under_fixture_clearance_m']>=2.7,'Garage fixtures preserve player headroom')
V.check(parking['shared_open_space'] and parking['internal_partition_walls']==0,'Parking is one connected basement')
V.check(parking['bounds'][0]<min(r[0] for r in report['apartment']['building_bounds']) and parking['bounds'][2]>max(r[2] for r in report['apartment']['building_bounds']),'Parking extends beyond the apartment footprints')
V.check(parking['integrated_route_qa']['passed'] and parking['clear_height_m']>=2.7,'Integrated basement stairs/lift exits and vehicle ramp pass')
vehicle_tests=parking['vehicle_ramp'].get('integrated_two_way_vehicle_qa',[])
V.check(len(vehicle_tests)==2 and all(r['passed'] and r['player_radius_m']==1.2 and r['player_height_m']==2.4 for r in vehicle_tests),'Both vehicle lanes clear complete integrated road/ramp collision with2.4m proxies')
V.check(len(j.points(lambda name:name.startswith('EXT_B3_ApartmentFloor')))==0 and len(j.points(lambda name:name.startswith('EXT_FoundationStarter')))>0,'Fourth structure exposes the parking basement at foundation stage')
V.check(report['gravel_access']['surface']=='gravel' and report['gravel_access'].get('alignment')=='straight_perpendicular_to_public_street' and report['gravel_access']['polyline']==[[447,681],[447,847]],'Grey haul road forms a90degree street junction without overlapping public street')
V.check(parking['bounds']==[339,744,451,896],'Expanded east parking wing contains direct back ramp')
V.check(parking['vehicle_ramp']['clear_bounds']==[444.15,849,449.85,867] and parking['vehicle_ramp'].get('connector_turns')==0,'Basement ramp descends directly from the road near the back')
textures=[m.get('extras',{}).get('height_source','') for m in j.j['materials']]
V.check(any('worksite_mud_tracks_height' in t for t in textures),'Tyre track material retains real16bit depth source')
tracked=report.get('tracked_paths',[])
V.check(len(tracked)==6 and all(p['height_range_m']==.032 and p['uv_repeat_m']==6 and p['openings_clipped'] for p in tracked),'Six light worn-earth paths retain path UVs and32mm track depth, with all openings clipped')
clusters=report.get('material_clusters',[]);V.check(len(clusters)==6 and sum(p['items'] for p in clusters)==23,'Six rational material dropzones add23 existing reusable props')
for mesh in j.j['meshes']:
    if not mesh.get('name','').startswith(('EXT_TrackedEarth_','EXT_GravelHaulRoad')):continue
    for primitive in mesh['primitives']:V.check('COLOR_0' in primitive['attributes'],'Wheel wear meshes keep independent RGBA depth masks',mesh['name'])
for mound in report.get('mounds',[]):
    names=[r['name'] for r in rows if r['name']==mound['collision']]
    V.check(len(names)==1,'Each dirt heap has one matching physical soil hull',mound['name'])
path=[p for r in routes for p in r['supported_path']];hits=[]
for n,p in enumerate(path):
    foot=np.array(p);half=np.array([.32,.32,.89]);support=foot[2]
    # Match the simulation's swept-box expansion. On a ramp the uphill corner,
    # not the centre point, determines the standing foot height.
    for r in rows:
        if not r.get('walkable',True):continue
        lo=np.array(r['aabb']['min']);hi=np.array(r['aabb']['max'])
        if np.any(foot[:2]+.32<lo[:2]) or np.any(foot[:2]-.32>hi[:2]):continue
        for nx,ny,nz,d in r['planes']:
            if nz<.7:continue
            top=(d-nx*foot[0]-ny*foot[1]+abs(nx)*.32+abs(ny)*.32)/nz
            if foot[2]-.03<=top<=foot[2]+.35:support=max(support,top)
    centre=foot.copy();centre[2]=support+.91
    for r in rows:
        lo=np.array(r['aabb']['min']);hi=np.array(r['aabb']['max'])
        if np.any(centre+half<lo) or np.any(centre-half>hi):continue
        planes=np.array(r['planes']);separation=planes[:,:3]@centre-planes[:,3]-np.abs(planes[:,:3])@half
        if np.all(separation<-.0001):hits.append({'sample':n,'point':p,'volume':r['name']})
V.check(not hits,'Standing game player box clear on all three upper-floor stair routes',hits[:20])
V.check(len(path)>=250 and path[-1][2]>=6.39,'Supported route reaches second upper floor')
# Near-ground art must not overlay the core export rectangular footprint.
for i,node in enumerate(j.j['nodes']):
    if 'mesh' not in node or 'Ground' not in node.get('name',''):continue
    for prim in j.j['meshes'][node['mesh']]['primitives']:
        p=j.access(prim['attributes']['POSITION']);p=(np.c_[p,np.ones(len(p))]@j.world(i).T)[:,:3]@V.G.T
        faces=j.access(prim['indices']).reshape(-1,3);c=p[faces].mean(axis=1)
        bad=((c[:,0]>290.001)&(c[:,0]<449.999)&(c[:,1]>600.001)&(c[:,1]<684.999)&(np.abs(c[:,2])<.1)).sum()
        V.check(bad==0,'Extension ground does not overlay core ground',{'mesh':node['name'],'triangles':int(bad)})
        for bounds in report['apartment']['building_bounds']:
            overlap=((c[:,0]>bounds[0]+.001)&(c[:,0]<bounds[2]-.001)&(c[:,1]>bounds[1]+.001)&(c[:,1]<bounds[3]-.001)).sum()
            V.check(overlap==0,'Site ground respects the concrete apartment slabs',{'mesh':node['name'],'triangles':int(overlap)})
# Road shoulders must sit on terrain/deck, never expose background through a raster gap.
core_rows=V.jsonfile(HERE.parent/'kit/collision_ground.json')['volumes']
supports=[r for r in rows+core_rows if r['name'].startswith(('COL_EXT_Surface_','COL_Surface_','COL_EXT_ParkingRoofDeck_','COL_EXT_ParkingRampTopLanding'))]
lo=np.array([r['aabb']['min'] for r in supports]);hi=np.array([r['aabb']['max'] for r in supports]);road=j.points(lambda name:name.startswith('EXT_GravelHaulRoad'))
unique=np.unique(np.round(road[:,:2],4),axis=0);missing=[]
for x,y in unique:
    if not (310<=x<=483 and 600<=y<=908):continue
    mask=(lo[:,0]<=x+.001)&(hi[:,0]>=x-.001)&(lo[:,1]<=y+.001)&(hi[:,1]>=y-.001)&(lo[:,2]<=.001)&(hi[:,2]>=-.001)
    if not mask.any():missing.append([float(x),float(y)])
V.check(not missing,'Gravel road edges have continuous ground/deck support',missing[:20])
# Flat road COLL must never bridge the descending clear ramp.
clear=parking['vehicle_ramp']['clear_bounds'];bad=[]
for r in rows:
    if not r['name'].startswith('COL_EXT_HaulRoad'):continue
    p=np.mean(np.array(r['vertices'])[:3],axis=0)
    if clear[0]+.001<p[0]<clear[2]-.001 and clear[1]+.001<p[1]<clear[3]-.001:bad.append(r['name'])
V.check(not bad,'Flat haul-road collision leaves vehicle slope uncapped',bad)
placements=V.jsonfile(HERE/'placements.generated.json')['instances'];counts={pid:sum(p['prop_id']==pid for p in placements) for pid in set(p['prop_id'] for p in placements)}
V.check(counts.get('tower_crane',0)==2 and counts.get('moving_truck',0)>=5 and counts.get('site_office',0)>=7 and counts.get('portable_toilet',0)>=4,'Active campus has two cranes, five trucks, seven cabins and toilet cluster',counts)
V.check(counts.get('playground_set',0)>=1 and counts.get('organic_planter_bench',0)==6,'Two organic printed-planter runs combine greenery and integrated timber benches',counts)
fol=V.jsonfile(HERE/'foliage.json')['volumes'];V.check(sum(r.get('source_prop')=='organic_planter_bench' for r in fol)==18,'All six organic planters carry three runtime planting volumes')
stairs_instances=[p for p in placements if p['prop_id']=='site_office_stairs'];stacks=[]
for stair in stairs_instances:
    x,y,z=stair['position'];spec=next(r for r in report['cabin_stacks'] if np.allclose(r['lower'],[x,y,z],atol=.001));upper=[spec['lower'][k]+spec['upper_offset'][k] for k in range(3)]
    matching=[p for p in placements if p['prop_id']=='site_office' and p['yaw_deg']==stair['yaw_deg'] and any(np.allclose(p['position'],q,atol=.001) for q in ([x,y,z],upper))]
    V.check(len(matching)==2,'Cabin stairs match the intended lower/upper mounting datums',stair['id']);stacks.append(dict(stair=stair['id'],position=stair['position'],office_ids=[p['id'] for p in matching],upper_offset=spec['upper_offset']))
ground_props={'tower_crane','portable_toilet','printed_blocks_pallet','timber_pallet','rebar_bundle','moving_truck','city_car','organic_planter_bench','playground_set','toolbox','gang_box','loose_construction_pipes','loose_timber_boards','printed_block_offcuts'}
ground_support_fail=[];ground_prop_samples=0
for p in placements:
    if p['prop_id'] not in ground_props:continue
    x,y,want=p['position'];ground_prop_samples+=1;tops=[]
    for r in rows:
        if not r.get('walkable',True):continue
        lo,hi=r['aabb']['min'],r['aabb']['max']
        if not(lo[0]-.001<=x<=hi[0]+.001 and lo[1]-.001<=y<=hi[1]+.001):continue
        for nx,ny,nz,d in r['planes']:
            if nz<.7:continue
            z=(d-nx*x-ny*y)/nz
            if abs(z-want)<.035 and V.contains(r,(x,y,z)):tops.append(z)
    if not tops:ground_support_fail.append(dict(id=p['id'],position=p['position']))
V.check(not ground_support_fail,'Ground-level vehicles/materials/courtyard props have terrain or deck support',ground_support_fail)
output={'passed':not V.FAIL,'failures':V.FAIL,'warnings':V.WARN,'standing_route_samples':len(path),'radius_m':.32,'player_height_m':1.8,'fixed_volumes':len(rows),'cabin_stacks':stacks,'instance_counts':counts,'road_support_vertices':len(unique),'ground_prop_support_samples':ground_prop_samples,'inputs_sha256':V.FILES}
(HERE/'serialized_QA.json').write_text(json.dumps(output,indent=2)+'\n',encoding='utf8');print(json.dumps({k:v for k,v in output.items() if k!='inputs_sha256'},indent=2));sys.exit(bool(V.FAIL))
