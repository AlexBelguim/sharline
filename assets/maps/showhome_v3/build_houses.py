"""Four attached Showhome homes using the established v2 geometry pipeline.
The on-disk original kit/layout are never changed. Variant data is edited in memory.
Two homes per block share a solid 300mm concrete party wall and continuous roof.
"""
import sys,copy,math,importlib.util,ast
from pathlib import Path
import bpy,bmesh
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common as C
from gltf_shared import externalize
import json
OLD=C.ROOT/'assets/maps/showhome';OUT=C.HERE/'kit';OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(OLD));sys.path.insert(0,str(OLD/'layout'))
import layout_lib as LL
CUT_Y=21.85

def module():
    spec=importlib.util.spec_from_file_location('showhome_v2_source',OLD/'build_houses.py');s=importlib.util.module_from_spec(spec)
    tree=ast.parse((OLD/'build_houses.py').read_text(encoding='utf8'))
    tree.body=[n for n in tree.body if not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='main')]
    exec(compile(tree,str(OLD/'build_houses.py'),'exec'),s.__dict__)
    # Keep the9mm printed grooves, with shading normals matching their real slope.
    # The old55degree tilt aliases at street distance in the raster renderer.
    s.BEAD_TILT=math.atan(.009/.020)
    s.KIT=str(C.HERE/'_house_source_cache');s.KTEX=s.KIT+'/textures';Path(s.KIT).mkdir(exist_ok=True)
    s.derive_textures();s.glass_streaks()
    # Prevent the old painted flat bookcases / furnishings becoming fixed kit.
    s.House.props=lambda self:None;s.House.decor=lambda self:None
    s.House.parapets=lambda self:None;s.House.flat_roof_finish=lambda self:None
    s.House.entrance=lambda self:None
    s.House.DOOR_HINGE=dict(s.House.DOOR_HINGE,W_GF_PATIO='both')
    s.WALLS['W_GF_P'].update(kind='ext',ext=-1)
    def main_corners(self):
        for x,side in ((s.G['xw'],-1),(s.G['xe'],1)):
            self.corner((x,21.9),(side,0),(0,-1),0,3.2,w=.42)
            self.corner((x,s.G['yms']),(side,0),(0,-1),3.2,s.G['zeave'],w=.42)
            self.corner((x,s.G['yn']),(side,0),(0,1),0,s.G['zeave'],w=.42)
    s.House.corners=main_corners
    return s
def variant(s,end,south,attached=None):
    attached=south if attached is None else attached
    s.House.DOOR_HINGE['W_GF_BACK']='both' if attached and not south else 'hi'
    s.L=LL.load();original=copy.deepcopy(s.OPENINGS)
    s.L.data['brushes']=[b for b in s.L.all if not b['tag']['id'].startswith('W_TER') and b['tag']['id']!='W_GF_S']
    for b in s.L.brushes(tag='W_GF_P'):b['tag']['wall_kind']='ext';b['tag']['note']='200mm concrete garden facade, former garage partition'
    closed={'W_GF_'+end,'W_UF_'+end}
    for wall in closed:
        rows=s.L.brushes(tag=wall);proto=copy.deepcopy(rows[0]);proto['min']=[min(b['min'][k] for b in rows) for k in range(3)];proto['max']=[max(b['max'][k] for b in rows) for k in range(3)]
        proto['tag'].pop('opening',None);proto['tag']['part']='party_wall';proto['tag']['note']='Attached home shared concrete party wall; no facade opening here'
        s.L.data['brushes']=[b for b in s.L.all if b['tag']['id']!=wall]+[proto]
    s.OPENINGS=[o for o in original if o['wall'] not in closed and o['id'] not in ('W_GF_ROLLER','W_GF_GARWIN','W_UF_TERDOOR')]
    if south and attached:
        o=next(o for o in s.OPENINGS if o['id']=='W_UF_WIN_S');o['kind']='door';o['sill']=3.2;o['note']='lower-home garage terrace door'
        s.L.data['brushes']=[b for b in s.L.all if not (b['tag']['id']=='W_UF_E' and b['tag'].get('opening')=='W_UF_WIN_S' and b['tag']['part']=='sill')]
    if attached and not south:
        # Street-end garage connects through the exposed north end of the block.
        gf=next(o for o in s.OPENINGS if o['id']=='W_GF_BACK');gf.update(kind='door2',span=[28.5,30.5],sill=0,head=2.4,note='North-home attached garage connection')
        uf=next(o for o in s.OPENINGS if o['id']=='W_UF_CLR_W1');uf.update(kind='door',sill=3.2,head=5.4,note='North-home attached garage terrace door')
        for wall in ('W_GF_W','W_UF_W'):
            wallrows=s.L.brushes(tag=wall);template=copy.deepcopy(wallrows[0])
            lo=[min(b['min'][k] for b in wallrows) for k in range(3)];hi=[max(b['max'][k] for b in wallrows) for k in range(3)]
            s.L.data['brushes']=[b for b in s.L.all if b['tag']['id']!=wall]
            def end_segment(a,b,z0,z1,part,opening=None):
                row=copy.deepcopy(template);row['min']=[lo[0],a,z0];row['max']=[hi[0],b,z1];row['tag']['part']=part;row['tag'].pop('opening',None)
                if opening:row['tag']['opening']=opening
                s.L.data['brushes'].append(row)
            cursor=lo[1]
            for opening in sorted((o for o in s.OPENINGS if o['wall']==wall),key=lambda o:o['span'][0]):
                a,b=opening['span']
                if a>cursor:end_segment(cursor,a,lo[2],hi[2],'pier')
                if opening['sill']>lo[2]:end_segment(a,b,lo[2],opening['sill'],'sill',opening['id'])
                if opening['head']<hi[2]:end_segment(a,b,opening['head'],hi[2],'lintel',opening['id'])
                cursor=b
            if cursor<hi[1]:end_segment(cursor,hi[1],lo[2],hi[2],'pier')
    # Two equal full upper windows on the inward driveway face of every home.
    street=[('W_UF_CLR_N',9.8,12.2),('W_UF_WIN_NF',16.5,18.9)]
    proto=copy.deepcopy(s.L.brushes(tag='W_UF_N')[0]);s.L.data['brushes']=[b for b in s.L.all if b['tag']['id']!='W_UF_N']
    def segment(a,b,z0,z1,part,opening=None):
        row=copy.deepcopy(proto);row['min']=[a,31.85,z0];row['max']=[b,32.15,z1];row['tag']['part']=part;row['tag'].pop('opening',None)
        if opening:row['tag']['opening']=opening
        s.L.data['brushes'].append(row)
    for a,b in ((8.85,9.8),(12.2,16.5),(18.9,21.15)):segment(a,b,3.2,6.2,'pier')
    for oid,a,b in street:
        segment(a,b,3.2,3.85,'sill',oid);segment(a,b,5.7,6.2,'lintel',oid)
        o=next(o for o in s.OPENINGS if o['id']==oid);o.update(kind='window',span=[a,b],sill=3.85,head=5.7,note='Matching full-size upper driveway window')
    # One matching full window per floor on the garden facade. Keep its GF door.
    garden_span=[16.5,18.9]
    for wall,oid,floor,sill,head in (('W_GF_P','W_GF_WIN_GARDEN','GF',.75,2.6),('W_UF_S','W_UF_WIN_T','UF',3.85,5.7)):
        wallrows=s.L.brushes(tag=wall);template=copy.deepcopy(wallrows[0])
        lo=[min(b['min'][k] for b in wallrows) for k in range(3)];hi=[max(b['max'][k] for b in wallrows) for k in range(3)]
        s.L.data['brushes']=[b for b in s.L.all if b['tag']['id']!=wall]
        o=next((o for o in s.OPENINGS if o['id']==oid),None)
        if o is None:
            o=dict(id=oid,wall=wall,structure='SAGE_HOUSE',floor=floor,line='y = 22',clear_in_collision=True,blockers=[]);s.OPENINGS.append(o)
        o.update(kind='window',span=garden_span[:],sill=sill,head=head,note='One full-size garden window per floor, matching driveway window treatment')
        def garden_segment(a,b,z0,z1,part,opening=None):
            row=copy.deepcopy(template);row['min']=[a,lo[1],z0];row['max']=[b,hi[1],z1];row['tag']['part']=part;row['tag'].pop('opening',None)
            if opening:row['tag']['opening']=opening
            s.L.data['brushes'].append(row)
        cursor=lo[0]
        for opening in sorted((o for o in s.OPENINGS if o['wall']==wall),key=lambda o:o['span'][0]):
            a,b=opening['span']
            if a>cursor:garden_segment(cursor,a,lo[2],hi[2],'pier')
            if opening['sill']>lo[2]:garden_segment(a,b,lo[2],opening['sill'],'sill',opening['id'])
            if opening['head']<hi[2]:garden_segment(a,b,opening['head'],hi[2],'lintel',opening['id'])
            cursor=b
        if cursor<hi[0]:garden_segment(cursor,hi[0],lo[2],hi[2],'pier')
    # Give nominal 1m doors 1.1m raw width: trim leaves >1.0m clear.
    for o in s.OPENINGS:
        if o['kind']!='door' or o['span'][1]-o['span'][0]>=1.1:continue
        ax=s.WALLS[o['wall']]['ax'];ua=1-ax;lo,hi=o['span'];newlo,newhi=lo-.05,hi+.05
        for b in s.L.brushes(tag=o['wall']):
            if abs(b['max'][ua]-lo)<1e-5:b['max'][ua]=newlo
            if abs(b['min'][ua]-hi)<1e-5:b['min'][ua]=newhi
            if b['tag'].get('opening')==o['id']:b['min'][ua]=newlo;b['max'][ua]=newhi
        o['span']=[newlo,newhi]
    s.OPEN_BY_WALL={}
    for o in s.OPENINGS:s.OPEN_BY_WALL.setdefault(o['wall'],[]).append(o)
    return original

def clip_acc(s,acc):
    """Clip geometry while interpolating each new corner's UV, color and normal."""
    out=s.Acc()
    for pts,mat,uvs,cols,nrm in acc.P:
        # Garden UF face sits exactly on the cut: retain its existing <=2cm trim.
        cut=CUT_Y-.02 if mat=='trim' and min(p.y for p in pts)>=CUT_Y-.02001 and max(p.y for p in pts)<=CUT_Y+.00001 else CUT_Y
        src=[(p,Vector(uvs[i]),Vector(cols[i]),nrm[i] if nrm else None) for i,p in enumerate(pts)];dst=[]
        for i,b in enumerate(src):
            a=src[i-1];ain=a[0].y>=cut-1e-8;bin=b[0].y>=cut-1e-8
            if ain!=bin:
                t=(cut-a[0].y)/(b[0].y-a[0].y);q=[a[k].lerp(b[k],t) if a[k] is not None else None for k in range(4)];q[0].y=cut;dst.append(q)
            if bin:dst.append(b)
        if len(dst)<3:continue
        clean=[]
        for q in dst:
            if not clean or (q[0]-clean[-1][0]).length>1e-7:clean.append(q)
        if len(clean)>2 and (clean[0][0]-clean[-1][0]).length<1e-7:clean.pop()
        if len(clean)<3 or s.newell([q[0] for q in clean]).length<1e-8:continue
        groups=[clean] if len(clean)<=4 else [[clean[0],clean[i],clean[i+1]] for i in range(1,len(clean)-1)]
        for g in groups:out.P.append(([q[0] for q in g],mat,[tuple(q[1]) for q in g],[tuple(q[2]) for q in g],None if nrm is None else [q[3].normalized() for q in g]))
    return out

def clipped_brush(b):
    if b['max'][1]<=CUT_Y+1e-6:return None
    b=copy.deepcopy(b);b['min'][1]=max(CUT_Y,b['min'][1]);return b

def inward_entrance(s,a):
    o=next(o for o in s.OPENINGS if o['id']=='W_GF_PATIO');u0,u1=o['span'];z=o['head']+.22
    s.box(a['trim'],(u0-.28,32.15,z),(u1+.28,32.168,z+.09),'trim',s.C_TRIM,s.trim_box_uv('coping_cream',0))
    for x in (u0-.28,u1+.22):s.box(a['trim'],(x,32.15,1.86),(x+.06,32.168,2.12),'trim',s.WHITE,s.trim_box_uv('plain_dark',2))
def transform(h):
    return Matrix.Translation(Vector(h['centre']))@Matrix.Rotation(math.radians(h['yaw_deg']),4,'Z')@Matrix.Translation(-Vector(h['old_centre']))

def is_east(h):return h['centre'][0]>370

def has_attached_garage(h):return h.get('attached_garage',h['id'].endswith('_south'))

def paint_team(s,h):return s.TEAMS['E' if h['colour']=='clay' else 'W']

def garage_offset(h):return Vector(h['centre'])-Vector((386 if is_east(h) else 354,636,0))

def garage_transform(h):
    mirror=Matrix.Translation(Vector((740,0,0)))@Matrix.Diagonal(Vector((-1,1,1,1))) if is_east(h) else Matrix.Identity(4)
    north=Matrix.Translation(Vector((0,1272,0)))@Matrix.Diagonal(Vector((1,-1,1,1))) if h['id'].endswith('_north') else Matrix.Identity(4)
    return Matrix.Translation(garage_offset(h))@north@mirror

def mirror_garage_north(s,acc):
    out=s.Acc()
    for pts,mat,uvs,cols,nrm in acc.P:
        out.P.append(([Vector((p.x,1272-p.y,p.z)) for p in reversed(pts)],mat,list(reversed(uvs)),list(reversed(cols)),None if nrm is None else [Vector((q.x,-q.y,q.z)) for q in reversed(nrm)]))
    return out

def attached_garage(s,mats,root,h,objs):
    """Mirror the garage into its block and attach it at the selected exposed end."""
    east=is_east(h);T=garage_transform(h);offset=Matrix.Translation(garage_offset(h))
    x0,x1,y0,y1=352,362.15,624,630.15;door0,door1=625,629;gh=s.House(paint_team(s,h));a=gh.acc;cols=[]
    def collider(name,lo,hi,phys):
        v,f=LL.box_polys(lo,hi);ob=C.col_mesh(h['id']+'_GARAGE_'+name,[tuple(T@Vector(q)) for q in v],f,phys);C.parent_keep(ob,root);cols.append(ob)
    def solid(name,lo,hi,mat='concrete',phys='concrete',skip=()):
        s.box(a['interior'],lo,hi,mat,s.WHITE,s.uv_box(2),skip);collider(name,lo,hi,phys)
    walls=[('Garden',(x0,y0,0),(x0+.3,629.85,3.2),(0,-1,x0)),('South',(x0,y0,0),(x1,y0+.3,3.2),(1,-1,y0)),('FrontLow',(x1-.3,y0,0),(x1,door0,3.2),(0,1,x1)),('FrontHigh',(x1-.3,door1,0),(x1,629.85,3.2),(0,1,x1)),('FrontLintel',(x1-.3,door0,2.75),(x1,door1,3.2),(0,1,x1))]
    for p,na,nb in [((x0,y0),(-1,0),(0,-1)),((x1,y0),(0,-1),(1,0))]:gh.corner(p,na,nb,0,3.2,w=.38,r=.045)
    def printed(plane,r):
        covered=[rr for pk,rs in gh.extra_cover.items() if s.same_plane(pk,plane) for rr in rs]
        for rr in s.rect_subtract(r,covered):gh.emit_face(plane,rr,('shell','printed',('box',1.28),('ao',),0))
    for name,lo,hi,plane in walls:
        solid(name,lo,hi,skip=((plane[0],plane[1]),));ua=1-plane[0];printed(plane,(lo[ua],lo[2],hi[ua],hi[2]))
    solid('Floor',(x0,y0,-.12),(x1,y1,0))
    solid('DeckSlab',(x0,y0,2.95),(x1,y1,3.16))
    s.box(a['roof'],(x0+.15,y0+.15,3.16),(x1-.15,y1-.15,3.17),'roof',s.C_ROOF,s.uv_box(2));collider('Membrane',(x0+.15,y0+.15,3.16),(x1-.15,y1-.15,3.17),'cladding')
    for k in range(19):
        ya=y0+.32+k*(y1-y0-.64)/19;yb=y0+.32+(k+1)*(y1-y0-.64)/19-.008
        s.box(a['roof'],(x0+.32,ya,3.17),(x1-.32,yb,3.2),'deck',s.WHITE,s.uv_box(2))
    collider('DeckBoards',(x0+.32,y0+.32,3.17),(x1-.32,y1-.32,3.2),'wood_thin')
    # Ordinary clear BLEND glass replaces the two cream parapets, with true 15mm panes.
    for name,lo,hi in [('SouthGlass',(x0+.065,y0+.0325,3.26),(x1-.065,y0+.0475,4.17)),('DrivewayGlass',(x1-.0475,y0+.065,3.26),(x1-.0325,y1-.065,4.17))]:
        s.box(a['trim'],lo,hi,'terrace_glass',s.WHITE,s.uv_box(2));collider(name,lo,hi,'glass')
    for k in range(6):
        x=x0+.035+(x1-x0-.07)*k/5;solid('SouthRailPost_'+str(k),(x-.02,y0+.02,3.2),(x+.02,y0+.06,4.2),'heavy_metal','metal_heavy')
    for k in range(1,4):
        y=y0+.035+(y1-y0-.07)*k/3;solid('DrivewayRailPost_'+str(k),(x1-.06,y-.02,3.2),(x1-.02,y+.02,4.2),'heavy_metal','metal_heavy')
    solid('SouthHandrail',(x0,y0+.02,4.17),(x1,y0+.06,4.2),'heavy_metal','metal_heavy')
    solid('DrivewayHandrail',(x1-.06,y0,4.17),(x1-.02,y1,4.2),'heavy_metal','metal_heavy')
    # The outer/back edge is the deliberate dark timber privacy-screen exception.
    board_count=41
    for k in range(board_count):
        ya=y0+k*(y1-y0)/board_count;yb=y0+(k+1)*(y1-y0)/board_count-.001
        solid('PrivacyBoard_'+str(k),(x0,ya,3.2),(x0+.02,yb,5.4),'privacy_wood','wood_thin')
        cols[-1]['exception']='privacy_screen'
    for k,y in enumerate((y0+.07,y1-.07)):
        solid('PrivacyPost_'+str(k),(x0+.02,y-.035,3.2),(x0+.09,y+.035,5.4),'privacy_post','wood_thick');cols[-1]['exception']='privacy_screen'
    collider('HalfOpenShutter',(x1-.022,door0,1.1),(x1-.012,door1,2.75),'sheet_metal')
    for k in range(8):
        za=1.1+k*1.65/8;zb=1.1+(k+1)*1.65/8
        s.box(a['doors'],(x1-.022,door0,za),(x1-.012,door1,zb),'metal',paint_team(s,h)['door'],s.trim_box_uv('garage_door_slats',1))
        if k:s.box(a['doors'],(x1-.012,door0,za-.002),(x1-.011,door1,za+.002),'metal',s.C_STEEL,s.trim_box_uv('plain_dark',1))
    for ya,yb in ((door0-.035,door0+.025),(door1-.025,door1+.035)):
        s.box(a['trim'],(x1-.04,ya,0),(x1+.015,yb,2.8),'heavy_metal',s.C_STEEL,s.trim_box_uv('plain_dark',2));collider('ShutterGuide_'+str(ya),(x1-.04,ya,0),(x1+.015,yb,2.8),'metal_heavy')
    coll=C.bc.collection('SH3_'+h['id']+'_GARAGE');partobjs=[]
    for key,acc in a.items():
        if h['id'].endswith('_north'):acc=mirror_garage_north(s,acc)
        if east:acc=acc.mirrored(370)
        for mk in sorted({p[1] for p in acc.P}):
            aa=s.Acc();aa.P=[p for p in acc.P if p[1]==mk];ob=s.make_object('SH3_'+h['id']+'_Garage_'+key+'_'+mk,aa,mats,coll);ob.data.transform(offset);ob['home']=h['id'];ob['material_family']=mk
            if mk.startswith('privacy_'):ob['exception']='privacy_screen'
            C.parent_keep(ob,root);objs.append(ob);partobjs.append(ob)
    corners=[T@Vector((x,y,0)) for x,y in ((x0,y0),(x1,y1))]
    footprint=[round(min(p.x for p in corners),6),round(min(p.y for p in corners),6),round(max(p.x for p in corners),6),round(max(p.y for p in corners),6)]
    return dict(home=h['id'],colour=h['colour'],geometry_side='east' if east else 'west',attached_end='north' if h['id'].endswith('_north') else 'south',centre_offset_m=list(garage_offset(h)),footprint=footprint,shutter_face='+X' if not east else '-X',shutter_plane_x=round((T@Vector((x1,0,0))).x,6),shutter_clear_width_m=door1-door0-.05,shutter_clear_height_m=1.1,shutter_thickness_m=.01,slide_only=True,garage_house_connection_width_m=1.964,garage_house_connection_height_m=2.382,deck_height_m=3.2,deck_door_clear_width_m=1.564,deck_door_clear_height_m=2.182,terrace_glass_thickness_m=.015,terrace_glass_alpha=.18,privacy_screen=dict(exception='privacy_screen',thickness_m=.02,height_m=2.2,phys='wood_thin',edge='east' if east else 'west'),triangles=C.triangles(partobjs),collision_volumes=len(cols))
def roof_collision(s,b,T,name):
    x0,y0,z0=b['min'];x1,y1,z1=b['max'];rise=b['ramp']['rise_toward']
    if rise=='N':ps=[Vector((x0,y0,z0)),Vector((x1,y0,z0)),Vector((x1,y1,z1)),Vector((x0,y1,z1))]
    else:ps=[Vector((x0,y0,z1)),Vector((x1,y0,z1)),Vector((x1,y1,z0)),Vector((x0,y1,z0))]
    n=(ps[1]-ps[0]).cross(ps[2]-ps[0]).normalized()
    if n.z<0:n=-n
    v=[tuple(T@p) for p in ps]+[tuple(T@(p-n*.12)) for p in ps]
    return C.col_mesh(name,v,[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],'cladding',walkable=False)

def exposed_gable_collision(s,h,root):
    """Close the exposed roof end with a triangular wall whose 300mm thickness is inward."""
    south=h['id'].endswith('_south');face=s.G['rx1'] if south else s.G['rx0'];x0,x1=(face-.3,face) if south else (face,face+.3)
    triangle=[(s.G['eave_ys'],s.G['zeave']),(s.G['eave_yn'],s.G['zeave']),(s.G['ridge_y'],s.G['zridge'])]
    vertices=[(x,y,z) for x in (x0,x1) for y,z in triangle]
    if is_east(h):vertices=[(72-x,y,z) for x,y,z in vertices]
    T=transform(h);vertices=[tuple(T@Vector(p)) for p in vertices]
    co=C.col_mesh(h['id']+'_ExposedGable',vertices,[(0,2,1),(3,4,5),(0,1,4,3),(1,2,5,4),(2,0,3,5)],'cladding',walkable=False);C.parent_keep(co,root)
    return dict(home=h['id'],name=co.name,thickness_m=.3,phys='cladding',end='south' if south else 'north',aabb=dict(min=[min(p[k] for p in vertices) for k in range(3)],max=[max(p[k] for p in vertices) for k in range(3)]))
def main():
    C.bc.reset_scene();s=module();mats=s.materials()
    phys={'clad':'cladding','printed':'concrete','concrete':'concrete','trim':'concrete','roof':'cladding','roof_edge':'cladding','solar':'sheet_metal','plaster':'drywall','deck':'wood_thin','timber':'wood_thin','oak':'wood_thin','fabric':'fabric','metal':'sheet_metal','paint':'wood_thin','lamp':'plastic','glass':'glass','frost':'concrete'}
    phys['paving']='paving'
    for k,m in mats.items():m['phys']=phys[k]
    mats['heavy_metal']=mats['metal'].copy();mats['heavy_metal'].name='M_SH_GarageGuideSteel';mats['heavy_metal']['phys']='metal_heavy'
    mats['terrace_glass']=C.material('TerraceClearGlass','glass',None,(.82,.90,.96),rough=.10,alpha=.18)
    mats['privacy_wood']=C.material('TerracePrivacyWood','wood_thin','wood_boards_stained',(.16,.12,.085),rough=.82)
    mats['privacy_post']=mats['privacy_wood'].copy();mats['privacy_post'].name='M_V3_TerracePrivacyPost';mats['privacy_post']['phys']='wood_thick'
    # Importer needs the full settings group even though these sources only use AO.
    from io_scene_gltf2.blender.com.material_helpers import create_settings_group
    group=bpy.data.node_groups.get('glTF Material Output')
    if group:
        for name in ('Iridescence Factor','Iridescence Thickness','Thickness'):
            if name not in [i.name for i in group.interface.items_tree]:group.interface.new_socket(name=name,in_out='INPUT',socket_type='NodeSocketFloat')
    layout=json.loads((C.HERE/'layout.json').read_text());root=C.empty('SH3_MapOrigin',layout['origin']);counts={};openings=[];dedupe=set();objs=[];garages=[];footprints=[];gables=[]
    original=copy.deepcopy(s.OPENINGS)
    for h in layout['houses']:
        south=h['id'].endswith('_south');attached=has_attached_garage(h);east=is_east(h);s.OPENINGS=copy.deepcopy(original);variant(s,h['party_end'],south,attached);team=paint_team(s,h);a=s.House(team).build();inward_entrance(s,a);T=transform(h);end_x=9 if h['party_end']=='W' else 21
        # Strip the internal gable's external roof trim/panels; the roof itself joins.
        for key in ('trim','clad','shell'):
            a[key].P=[p for p in a[key].P if not (all(abs(v.x-end_x)<.205 for v in p[0]) and (key!='shell' or min(v.z for v in p[0])>=6.19))]
        partobjs=[];coll=C.bc.collection('SH3_'+h['id'])
        for key,acc in a.items():
            acc=clip_acc(s,acc)
            if east:acc=acc.mirrored(36)
            for mk in sorted({p[1] for p in acc.P}):
                aa=s.Acc();aa.P=[p for p in acc.P if p[1]==mk]
                ob=s.make_object('SH3_'+h['id']+'_'+s.PARTS[key]+'_'+mk,aa,mats,coll);ob.data.transform(T);ob['home']=h['id'];ob['material_family']=mk;C.parent_keep(ob,root);objs.append(ob);partobjs.append(ob)
        counts[h['id']]=C.triangles(partobjs)
        footprints.append(dict(home=h['id'],colour=h['colour'],geometry_side='east' if east else 'west',main=[h['centre'][0]-8.15 if east else h['centre'][0]-2.15,h['centre'][1]-6.15,h['centre'][0]+2.15 if east else h['centre'][0]+8.15,h['centre'][1]+6.15],driveway_entrance_face='-X' if east else '+X'))
        bs=s.L.brushes(structure='SAGE_HOUSE')
        bs += [b for b in s.L.all if b['tag'].get('part')=='building_floor' and b['min'][0]>=8.6 and b['max'][0]<=21.4 and b['min'][1]>=15.6 and b['max'][1]<=32.4]
        for k,b in enumerate(bs):
            if b['kind']=='PlayerClip':continue
            b=clipped_brush(b)
            if b is None:continue
            v,f=LL.brush_polys(b)
            if east:v=[(72-x,y,z) for x,y,z in v]
            tag=b['tag'];p='drywall' if tag.get('wall_kind')=='int' else 'concrete'
            if b['look']=='Roof' and b['shape']=='ramp':
                rb=copy.deepcopy(b)
                if east:rb['min'][0],rb['max'][0]=72-b['max'][0],72-b['min'][0]
                co=roof_collision(s,rb,T,h['id']+'_'+tag['id']);C.parent_keep(co,root);continue
            vs=[tuple(T@Vector(q)) for q in v];key=(p,tuple(round(t,5) for t in sorted([tuple(round(z,5) for z in q) for q in vs])[0]),tuple(round(min(q[i] for q in vs),5) for i in range(3)),tuple(round(max(q[i] for q in vs),5) for i in range(3)))
            if key in dedupe:continue
            dedupe.add(key);co=C.col_mesh(h['id']+'_'+tag['id']+'_'+str(k),vs,f,p);C.parent_keep(co,root)
        gables.append(exposed_gable_collision(s,h,root))
        for o in s.OPENINGS:
            width=o['span'][1]-o['span'][0]-.036;height=o['head']-o['sill']-.018
            openings.append(dict(home=h['id'],id=o['id'],kind=o['kind'],floor=o['floor'],wall=o['wall'],width_m=round(width,3),height_m=round(height,3),sill_m=o['sill'],head_m=o['head'],slide_only=False,role='street_upper_window' if o['id'] in ('W_UF_CLR_N','W_UF_WIN_NF') else 'garden_window' if o['id'] in ('W_GF_WIN_GARDEN','W_UF_WIN_T') else 'driveway_entrance' if o['id']=='W_GF_PATIO' else 'garden_door' if o['id']=='W_GF_GARDOOR' else 'garage_connection' if attached and o['id']==('W_GF_FRONT' if south else 'W_GF_BACK') else 'garage_deck_door' if attached and o['id']==('W_UF_WIN_S' if south else 'W_UF_CLR_W1') else 'opening'))
        if attached:
            garage=attached_garage(s,mats,root,h,objs);garages.append(garage);counts[h['id']]+=garage['triangles'];openings.append(dict(home=h['id'],id='ATTACHED_GARAGE_SHUTTER',kind='roller',width_m=garage['shutter_clear_width_m'],height_m=1.1,sill_m=0,slide_only=True,role='driveway_garage'))
    bpy.context.view_layer.update();cols=[o for o in bpy.context.scene.objects if o.name.startswith('COL_')]
    rows=C.export_collision(OUT/'collision_houses.json',cols)
    for row in rows:
        if '_GARAGE_Privacy' in row['name']:row['exception']='privacy_screen'
    payload=json.loads((OUT/'collision_houses.json').read_text());payload['volumes']=rows;C.write(OUT/'collision_houses.json',payload)
    street_windows=[o for o in openings if o['role']=='street_upper_window'];assert len(street_windows)==8
    assert len({(o['width_m'],o['height_m'],o['sill_m'],o['head_m']) for o in street_windows})==1,'Inward upper windows must match'
    garden_windows=[o for o in openings if o['role']=='garden_window'];assert len(garden_windows)==8
    assert all(sum(o['home']==h['id'] and o['floor']==floor for o in garden_windows)==1 for h in layout['houses'] for floor in ('GF','UF')),'One garden window per home floor required'
    assert all(abs(o['width_m']-2.364)<.001 and abs(o['height_m']-1.832)<.001 for o in garden_windows),'Garden windows must match full driveway window size'
    def inside_volume(row,p):return all(Vector(q[:3]).dot(p)<=q[3]+.0002 for q in row['planes'])
    sample_count=0
    for h in layout['houses']:
        T=transform(h);east=is_east(h)
        face=s.G['rx1'] if h['id'].endswith('_south') else s.G['rx0'];p=T@Vector((72-face if east else face,s.G['ridge_y'],8));assert any(r['phys']=='cladding' and inside_volume(r,p) for r in rows),('exposed gable collision absent',h['id']);sample_count+=1
        for x in (11,17.7):
            for z in (3.90,4.80,5.65):
                p=T@Vector((72-x if east else x,32,z));assert not any(inside_volume(r,p) for r in rows),('upper window blocked',h['id'],tuple(p));sample_count+=1
        for z0,z1 in ((.75,2.6),(3.85,5.7)):
            for x in (16.55,17.7,18.85):
                for z in (z0+.05,(z0+z1)/2,z1-.05):
                    p=T@Vector((72-x if east else x,22,z));assert not any(inside_volume(r,p) for r in rows),('garden window blocked',h['id'],tuple(p));sample_count+=1
            for x,z in ((16.4,(z0+z1)/2),(19,(z0+z1)/2),(17.7,z0-.10),(17.7,z1+.10)):
                p=T@Vector((72-x if east else x,22,z));assert any(r['phys']=='concrete' and inside_volume(r,p) for r in rows),('garden window wall support absent',h['id'],tuple(p));sample_count+=1
        p=T@Vector((72-10.5 if east else 10.5,22,1));assert not any(inside_volume(r,p) for r in rows),('garden door blocked',h['id']);sample_count+=1
        if has_attached_garage(h):
            GT=garage_transform(h)
            for name,p,phys in [('south glass',(357,624.04,3.7),'glass'),('driveway glass',(362.11,627,3.7),'glass'),('privacy screen',(352.01,627.07,4.7),'wood_thin'),('shutter',(362.133,627,2),'sheet_metal')]:
                p=GT@Vector(p);assert any(r['phys']==phys and inside_volume(r,p) for r in rows),('positive collision absent',h['id'],name,tuple(p));sample_count+=1
            p=GT@Vector((362.133,627,.5));assert not any(inside_volume(r,p) for r in rows),'Garage slide gap blocked';sample_count+=1
            north=h['id'].endswith('_north');face=9 if north else 21
            for u,z in ((29.5 if north else 26,1),(26.8 if north else 24.2,4.2)):
                p=T@Vector((72-face if east else face,u,z));assert not any(inside_volume(r,p) for r in rows),('garage house connection blocked',h['id'],tuple(p));sample_count+=1
        else:
            assert not any('_'+h['id']+'_GARAGE_' in r['name'] for r in rows),('unassigned attached garage emitted',h['id'])
    C.export_glb(OUT/'houses.glb',[root]+objs);externalize(OUT/'houses.glb',C.HERE/'textures')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'houses.blend'))
    C.write(OUT/'houses_report.json',dict(triangles=counts,total_triangles=sum(counts.values()),collision_volumes=len(rows),openings=openings,main_footprints=footprints,attached_garages=garages,exposed_gables=gables,street_upper_window=dict(raw_width_m=2.4,clear_width_m=2.364,clear_height_m=1.832,sill_m=3.85,head_m=5.7,count=8,equality_verified=True),garden_windows=dict(raw_width_m=2.4,clear_width_m=2.364,clear_height_m=1.832,count=8,per_home_per_floor=1,GF=dict(sill_m=.75,head_m=2.6),UF=dict(sill_m=3.85,head_m=5.7),garden_door_retained=True,equality_verified=True),positive_negative_collision_samples=sample_count,upper_garages='separate movable structures placed by build_core',source_clip_y=CUT_Y,party_wall_m=.30,interior_partition_m=.20,outer_wall_m=.30,garden_GF_wall_m=.20,roof_skin_m=.12,origin=layout['origin'],closed_party_wall_y=layout['party_wall_y'],collision_by_material={p:sum(r['phys']==p for r in rows) for p in sorted({r['phys'] for r in rows})},thinnest_volumes=sorted([dict(name=r['name'],phys=r['phys'],thickness_m=r['thickness_m']) for r in rows],key=lambda r:r['thickness_m'])[:10]))
    assert all(o['width_m']>1 for o in openings if o['kind'] in ('door','door2')), 'Door width failed'
    print('HOUSES_READY',counts,len(rows),flush=True)
    if '--render' in sys.argv:
        cam=C.stage();bpy.context.scene.cycles.samples=8
        C.render(cam,C.HERE/'renders/houses_blockout.png',(420,597,54),(370,layout['party_wall_y'],4),85)
        west=next(h for h in layout['houses'] if not is_east(h) and has_attached_garage(h));GT=garage_transform(west)
        C.render(cam,C.HERE/'renders/houses_garage_driveway.png',GT@Vector((370,617,3)),GT@Vector((362,632,2.5)),None)
        C.render(cam,C.HERE/'renders/houses_terrace.png',GT@Vector((370,620,6.5)),GT@Vector((357,627,3.5)),None)
        C.render(cam,C.HERE/'renders/houses_garden_windows.png',(329,647,4.3),(350.35,645,3.2),None)
if __name__=='__main__':main()
