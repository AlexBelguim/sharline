"""Reusable Phase-1 props, original geometry and the existing painted kit.
Blender -b --factory-startup -P build_library.py [-- --only id,... --render]
No map placements, game code, source props or user-owned placement files are changed.
"""
import sys,math,json,random
from pathlib import Path
import bpy,bmesh
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common as C
from gltf_shared import read,save,externalize
ROOT=C.ROOT;HERE=C.HERE;PROPS=ROOT/'assets/props';TEXTURES=HERE/'textures';CACHE=HERE/'_cache';CACHE.mkdir(exist_ok=True)
CATALOG=[];M={};PARTS=[]
def mats():
    global M
    M={
      'cream':C.material('Cream','wood_thin','truck_paint_white',(.8,.78,.69)),
      'wood':C.material('Timber','wood_thin','timber_pallets'),
      'post':C.material('Posts','wood_thick','wood_boards_stained'),
      'dark':C.material('Dark','plastic',None,(.035,.045,.05)),
      'steel':C.material('Steel','sheet_metal','metal_scaffold_tube'),
      'tube':C.material('StructuralSteel','metal_heavy','metal_scaffold_tube'),
      'redsteel':C.material('RedSteel','sheet_metal','fibercement_panel',(.73,.28,.13)),
      'concrete':C.material('Concrete','concrete','concrete_smooth'),
      'soil':C.material('Soil','soil','garden_soil'),
      'sage':C.material('Sage','wood_thin','fibercement_panel',(.28,.35,.23)),
      'clay':C.material('Clay','wood_thin','fibercement_panel',(.73,.28,.13)),
      'olive':C.material('OliveSteel','sheet_metal','fibercement_panel',(.20,.24,.13)),
      'yellow':C.material('WorksiteSteel','sheet_metal','metal_painted_yellow'),
      'fabric':C.material('Canvas','fabric','fibercement_panel',(.055,.085,.12),rough=.82),
      'cloth_sand':C.material('SandCanvas','fabric','fibercement_panel',(.38,.28,.18)),
      'glass':C.material('Glass','glass',None,(.43,.57,.55),rough=.22,alpha=.26),
      'liner':C.material('Interior','wood_thin','timber_pallets',(.63,.61,.53)),
      'roof':C.material('Membrane','cladding','roof_shingle_dark'),
      'flat_roof':C.material('FlatMembrane','cladding','fibercement_panel',(.17,.18,.19),rough=.85),
      'darkwood':C.material('DarkPrivacyWood','wood_thin','wood_boards_stained',(.35,.30,.25)),
      'darkpost':C.material('DarkPrivacyPosts','wood_thick','wood_boards_stained',(.35,.30,.25)),
      'printed':C.material('PrintedGardenGarage','concrete','printed_concrete_layers'),
    }
def add(name,size,loc,mat,parent,bevel=.008,collision=True):
    return C.box(name,size,loc,M[mat],bevel,parent,collision,local=True)
def begin(pid,category,container=None,size='medium',mount=None):
    C.bc.reset_scene();mats();root=C.empty('PROP_'+pid);root['id']=pid;root['category']=category;root['front']='design -Y';root['source']='project original procedural kit';root['licence']='project original'
    if container:
        root['container']=container;root['size']=size;root['search_s']=4 if size=='small' else 6;root['lootable']=True
    if mount:root['mount']=mount
    return root
def slot(root,pos,index=0):return C.empty('LOOT_SLOT_'+str(index),pos,root)
def movable(ob,name,kind,pivot,root,axis='Z',max_deg=100,ajar=12,travel=.36):
    co=[o for o in bpy.context.scene.objects if o.name==ob.get('collision')]
    ob.name=kind+'_'+name;C.parent_keep(ob,root)
    mw=ob.matrix_world.copy();shift=Vector(pivot);ob.data.transform(Matrix.Translation(-shift));ob.location=shift
    ob['axis']=axis;ob['ajar']=ajar;ob['pose']='ajar';ob['pose_unit']='metres' if kind=='OPEN_DRAWER' else 'degrees'
    if kind=='OPEN_DRAWER':ob['travel_m']=travel;ob['closed_location']=list(shift);ob.location.y-=ajar
    else:ob['min_deg']=0;ob['max_deg']=max_deg;ob['closed_rotation_deg']=0;ob.rotation_euler['XYZ'.index(axis)]=math.radians(ajar)
    # Collision follows the moving part; rows also carry this parent link.
    for c in co:
        # The closed collision was made in the same root frame. Place in closed local pose.
        c.parent=ob;c.matrix_parent_inverse=Matrix.Identity(4);c.location=-shift
    return ob
def shell(root,w,d,h,mat='cream',thick=.025,bottom=.08,back=True,top=True):
    add('Carcass_L',(thick,d,h-bottom),(-w/2+thick/2,0,(h+bottom)/2),mat,root)
    add('Carcass_R',(thick,d,h-bottom),(w/2-thick/2,0,(h+bottom)/2),mat,root)
    add('Carcass_Base',(w-2*thick,d,thick),(0,0,bottom+thick/2),'liner',root)
    if top:add('Carcass_Top',(w,d,thick),(0,0,h-thick/2),mat,root)
    if back:add('Carcass_Back',(w-2*thick,thick,h-bottom),(0,d/2-thick/2,(h+bottom)/2),'liner',root)
    for x in (-w*.36,w*.36):
        for y in (-d*.3,d*.3):add('Foot',(.055,.055,bottom),(x,y,bottom/2),'post',root)
def handle(parent,pos,w=.13):
    add('Handle',(w,.02,.02),pos,'steel',parent,.005,False)
def door(root,w,d,h,x0,x1,z0,z1,mat='cream',index=0):
    y=-d/2-.016;ob=add('Door', (x1-x0,.025,z1-z0),((x0+x1)/2,y,(z0+z1)/2),mat,root,.008)
    pivot=(x0,y,z0);ob=movable(ob,str(index),'OPEN_DOOR',pivot,root,ajar=12)
    # Handle and hinges use the closed leaf's local coordinate system.
    handle(ob,(x1-x0-.065,0,(z1-z0)*.56))
    for zz in (.12,z1-z0-.12):add('Hinge',(.012,.016,.045),(.013,.02,zz),'steel',ob,.003,False)
    return ob
def cabinet(root,w,d,h,mode='doors',mat='cream'):
    shell(root,w,d,h,mat,thick=.01 if M[mat]['phys']=='sheet_metal' else .025)
    if mode=='drawers':
        for n in range(3):
            z0=.10+n*(h-.12)/3;zh=(h-.12)/3-.012;depth=d-.07
            dr=add('Drawer_Front',(w-.06,.01 if M[mat]['phys']=='sheet_metal' else .027,zh),(0,-d/2-.017,z0+zh/2),mat,root)
            dr=movable(dr,str(n),'OPEN_DRAWER',(0,0,0),root,axis='-Y',ajar=.04,travel=depth*.8)
            # Geometry is expressed in closed root coordinates under the sliding part.
            add('Drawer_Bottom',(w-.09,depth,.012),(0,0,z0+.022),'liner',dr,.003)
            for x in (-(w-.08)/2,(w-.08)/2):add('Drawer_Side',(.015,depth,zh*.75),(x,0,z0+zh*.39),'liner',dr,.003)
            add('Drawer_Back',(w-.08,.015,zh*.75),(0,depth/2,z0+zh*.39),'liner',dr,.003)
            handle(dr,(0,-d/2-.039,z0+zh*.64));slot(dr,(0,0,z0+.05),n)
    else:
        for n in range(2):
            x0=-w/2+.03+n*(w-.06)/2;x1=x0+(w-.06)/2-.008;door(root,w,d,h,x0,x1,.10,h-.035,mat,n)
        for n,z in enumerate((h*.34,h*.66)):
            add('Shelf',(w-.055,d-.05,.022),(0,0,z),'liner',root,.003);slot(root,(0,-.03,z+.03),n)
def chest(root,w,d,h,mat='olive',kind='OPEN_LID',wood=False):
    # Six real thin plates around an empty interior; no filled cuboid behind the lid.
    t=.024 if wood else .010
    for x in (-w/2+t/2,w/2-t/2):add('Wall_Side',(t,d,h-.05),(x,0,(h-.05)/2),mat,root,.004)
    for y in (-d/2+t/2,d/2-t/2):add('Wall_End',(w-2*t,t,h-.05),(0,y,(h-.05)/2),mat,root,.004)
    add('Floor',(w-2*t,d-2*t,t),(0,0,t/2),'wood' if wood else mat,root,.003)
    lid_t=.025 if wood else .01
    lid=add('Lid',(w+.02,d+.02,lid_t),(0,0,h-lid_t/2),mat,root,.006)
    lid=movable(lid,'0',kind,(0,d/2,h-lid_t/2),root,axis='X',max_deg=105,ajar=-7)
    lid['min_deg']=-105;lid['max_deg']=0
    handle(lid,(0,-d*.45,.028),min(w*.45,.22))
    for x in (-w*.3,w*.3):add('Clasp',(.028,.025,.075),(x,-d/2-.015,h-.10),'steel',root,.005,False)
    for x in (-w*.39,w*.39):
        for y in (-d*.35,d*.35):add('Foot',(.045,.045,.025),(x,y,.0125),'dark',root,.006,False)
    if wood:
        for z in (.07,h-.07):
            for y in (-d/2-.02,d/2+.02):add('Batten',(w,.04,.07),(0,y,z),'post',root)
    slot(root,(0,0,.04))
def open_bag(root,backpack=False):
    # Convex bulging wall rings with a genuine opening and a darker inner lining.
    w,d,h=(.34,.22,.47) if backpack else (.66,.34,.30);segments=20;rings=[]
    for z,s in ((.02,.76),(.08,.99),(h*.7,1),(h,.78)):
        rings.append([(w/2*math.cos(k*2*math.pi/segments)*s,d/2*math.sin(k*2*math.pi/segments)*s,z) for k in range(segments)])
    verts=[v for r in rings for v in r];faces=[]
    for r in range(3):
        for k in range(segments):q=(k+1)%segments;faces.append((r*segments+k,r*segments+q,(r+1)*segments+q,(r+1)*segments+k))
    faces.append(tuple(reversed(range(segments))))
    ob=C.mesh('Bag_Canvas',verts,faces,M['fabric'],root)
    sol=ob.modifiers.new('Sewn fabric thickness','SOLIDIFY');sol.thickness=.006;C.apply(ob);C.parent_keep(ob,root)
    C.box('Bag_Lining',(w*.70,d*.66,.012),(0,0,.032),M['cloth_sand'],.005,root,False)
    # Perimeter collision only; the loot cavity remains empty.
    for x in (-w*.43,w*.43):C.col_box('Bag_End',(x-.025,-d*.35,.02),(x+.025,d*.35,h*.8),'fabric',parent=root)
    for y in (-d*.4,d*.4):C.col_box('Bag_Side',(-w*.38,y-.025,.02),(w*.38,y+.025,h*.85),'fabric',parent=root)
    flap=add('Flap',(w*.7,d*.80,.012),(0,0,h-.013),'fabric',root,.006)
    flap=movable(flap,'Flap','OPEN_LID',(0,d*.38,h-.013),root,axis='X',max_deg=0,ajar=-28);flap['min_deg']=-120;flap['max_deg']=0
    for sx in (-1,1):
        x=sx*w*.23
        for y in (-d*.37,d*.37):C.bar('HandleRoot',(x,y,h*.75),(x,y,h+.09),.024,M['fabric'],root)
        C.bar('HandleGrip',(x,-d*.37,h+.09),(x,d*.37,h+.09),.024,M['cloth_sand'],root)
    slot(root,(0,0,.06))
def greenhouse(root):
    w,d=4.0,5.6;h=1.85;r=w/2
    add('Foundation',(w,d,.08),(0,0,.04),'concrete',root)
    for x in (-w/2,w/2):add('Lower_Rail',(.08,d,.10),(x,0,.13),'cream',root)
    # Glazed barrel panels are 15mm convex prisms, individually collidable.
    n=12
    for k in range(n):
        a,b=k*math.pi/n,(k+1)*math.pi/n
        p=Vector((r*math.cos(a),0,h+r*.48*math.sin(a)));q=Vector((r*math.cos(b),0,h+r*.48*math.sin(b)))
        normal=Vector((q.z-p.z,0,p.x-q.x)).normalized()*.0075
        vs=[tuple(v+Vector((0,y,0))+s*normal) for s in (-1,1) for y in (-d/2,d/2) for v in (p,q)]
        fs=[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
        ob=C.mesh('Glazed_Roof_'+str(k),vs,fs,M['glass'],root);co=C.col_mesh('Glass_Roof_'+str(k),vs,fs,'glass',parent=root);ob['collision']=co.name
    for y in (-d/2,-d/4,0,d/4,d/2):
        points=[(r*math.cos(k*math.pi/n),y,h+r*.48*math.sin(k*math.pi/n)) for k in range(n+1)]
        for p,q in zip(points,points[1:]):C.bar('Cream_Arch',p,q,.055,M['cream'],root)
    for x in (-w/2,w/2):
        add('Side_Glass',(.015,d,h-.17),(x,0,(h+.17)/2),'glass',root,.002)
        for y in (-d/2,0,d/2):add('Upright',(.06,.06,h),(x,y,h/2),'cream',root)
    # Front 1.1m walk-through door, with glazing above and on either side.
    for y in (-d/2,d/2):
        for x in (-1.275,1.275):add('End_Glass',(1.45,.015,1.80),(x,y,1.0),'glass',root,.002)
        for x in (-.55,.55):add('Door_Frame',(.065,.065,2.05),(x,y,1.025),'cream',root)
        add('Door_Header',(1.165,.07,.07),(0,y,2.025),'cream',root)
    leaf=add('Door_Glass',(1.03,.015,1.94),(0,-d/2-.01,1.01),'glass',root,.002)
    leaf=movable(leaf,'Greenhouse','OPEN_DOOR',(-.515,-d/2-.01,.04),root,ajar=95,max_deg=110)
    for x in (0,1.03):add('Door_Rail',(.035,.035,1.94),(x,0,.97),'cream',leaf,.003,False)
    for z in (.02,1.92):add('Door_Rail',(1.06,.035,.035),(.515,0,z),'cream',leaf,.003,False)
    leaf['ajar']=12;leaf['pose']='open';handle(leaf,(.95,-.02,1.02),.06)
def carport(root,pergola=False):
    w,d,h=(5.0,4.0,2.6) if pergola else (7.6,5.6,3.0765)
    for x in (-w/2+.10,w/2-.10):
        for y in (-d/2+.10,d/2-.10):add('Post',(.18,.18,h),(x,y,h/2),'post',root,.012)
    for y in (-d/2+.08,d/2-.08):add('Beam',(w,.20,.23),(0,y,h-.05),'post',root)
    if pergola:
        for k in range(11):add('Rafter',(.12,d+.3,.16),(-w/2+k*w/10,0,h+.08),'post',root,.008)
    else:
        add('Coping',(w+.18,d+.18,.18),(0,0,h),'cream',root)
        add('Roof',(w-.10,d-.10,.035),(0,0,h+.106),'flat_roof',root,.005)
        add('Rear_Wall',(w,.14,h-.16),(0,d/2,h/2),'wood',root)
        # Short side wings, rather than a wall across the open front.
        for x in (-w/2,w/2):add('Screen',(.10,d*.35,h-.3),(x,d*.325,h/2),'wood',root)
def fence(root,mesh_site=False,gate=False,width_override=None):
    width=width_override if width_override is not None else (2 if gate else (2.5 if mesh_site else 2))
    for x in (-width/2,width/2):add('Post',(.07,.07,2 if mesh_site else 1.2),(x,0,(2 if mesh_site else 1.2)/2),'tube' if mesh_site else 'cream',root)
    leaf=C.empty('GateLeaf') if gate else root
    for z in ((.10,1.90) if mesh_site else (.25,.80)):
        add('Rail',(width,.022 if mesh_site else .030,.035 if mesh_site else .065),(0,0,z),'tube' if mesh_site else 'cream',leaf)
    if mesh_site:
        # Real open lattice: 5mm wires, no opaque backing sheet.
        for k in range(13):add('Mesh_Wire',(.005,.005,1.8),(-width/2+k*width/12,0,1),'steel',leaf,.001,False)
        for k in range(10):add('Mesh_Wire',(width,.005,.005),(0,0,.10+k*.20),'steel',leaf,.001,False)
    else:
        for k in range(15):
            x=-width/2+.07+k*(width-.14)/14
            add('Picket',(.065,.020,1.03),(x,-.016,.62),'cream',leaf,.005)
    if gate:
        # All leaves remain independent; attach the hinge to an actual mesh.
        kids=[o for o in C.visuals() if o.parent==leaf]
        bpy.ops.object.select_all(action='DESELECT')
        for o in kids:o.select_set(True)
        bpy.context.view_layer.objects.active=kids[0];bpy.ops.object.join();ob=bpy.context.object;C.apply(ob);C.parent_keep(ob,root)
        for c in list(bpy.context.scene.objects):
            if c.parent==leaf:C.parent_keep(c,root)
        bpy.data.objects.remove(leaf,do_unlink=True)
        ob=movable(ob,'Garden','OPEN_DOOR',(-width/2,0,0),root,ajar=95,max_deg=110)
        ob['ajar']=12;ob['pose']='open'
        for c in list(bpy.context.scene.objects):
            if c.name.startswith('COL_') and 'Post' not in c.name:
                c.parent=ob;c.location=(width/2,0,0)
def planter(root):
    w,d,h=2.4,1.2,.48
    for x in (-w/2+.05,w/2-.05):add('Planter_End',(.10,d,h),(x,0,h/2),'post',root)
    for y in (-d/2+.05,d/2-.05):add('Planter_Wall',(w-.20,.10,h),(0,y,h/2),'post',root)
    add('Soil',(w-.20,d-.20,.08),(0,0,h-.12),'soil',root)
def bookcase(root):
    shell(root,1.3,.36,1.9,'wood',bottom=.06)
    rng=random.Random(63)
    for n,z in enumerate((.10,.46,.82,1.18,1.54)):
        add('Shelf',(1.24,.34,.022),(0,0,z),'wood',root,.004)
        x=-.57
        while x<.55:
            w=rng.uniform(.045,.10);h=rng.uniform(.20,.30)
            add('Book',(w,.20,h),(x+w/2,-.04,z+.02+h/2),rng.choice(('sage','clay','cream','fabric')),root,.004,False);x+=w+.015
def furniture(root,pid):
    if pid=='dining_table':
        add('Table_Top',(1.8,.9,.055),(0,0,.765),'wood',root)
        for x in (-.73,.73):
            for y in (-.32,.32):add('Table_Leg',(.085,.085,.72),(x,y,.36),'post',root)
    elif pid=='bed':
        add('Bed_Frame',(1.7,2.1,.24),(0,0,.21),'wood',root)
        add('Mattress',(1.6,2.0,.22),(0,0,.44),'cloth_sand',root,.05)
        add('Headboard',(1.7,.065,.78),(0,.97,.50),'wood',root)
        for x in (-.40,.40):add('Pillow',(.62,.43,.12),(x,.68,.59),'cream',root,.05,False)
        add('Blanket',(1.62,1.1,.035),(0,-.30,.575),'fabric',root,.012,False)
    else:bookcase(root)
def pole(root):
    add('Pole',(.24,.24,6.4),(0,0,3.2),'concrete',root,.028)
    add('Crossbar',(1.4,.14,.14),(0,0,6.15),'wood',root)
    add('Junction_Box',(.33,.28,.55),(0,-.18,4.65),'cream',root)
    for x in (-.55,0,.55):add('Insulator',(.09,.09,.16),(x,0,6.31),'cream',root,.015,False)
def concrete_barrier(root):
    """Original cast Jersey profile; its knee needs two convex collision prisms."""
    root['pivot']='ground centre';root['nominal_size_m']=[2,.65,1.05]
    root['profile']='Jersey base ramp and narrow upper taper'
    M['barrier_cream']=C.material('BarrierCream','concrete','fibercement_panel',(.94,.91,.82))
    M['barrier_orange']=C.material('BarrierOrange','concrete','fibercement_panel',(.88,.32,.09))
    profile=[(-.325,0),(.325,0),(.325,.12),(.155,.43),(.09,1.05),(-.09,1.05),(-.155,.43),(-.325,.12)]
    def prism(points):
        n=len(points);vs=[(x,y,z) for x in (-1,1) for y,z in points]
        fs=[tuple(reversed(range(n))),tuple(range(n,2*n))]
        fs += [(k,(k+1)%n,(k+1)%n+n,k+n) for k in range(n)]
        return vs,fs
    vs,fs=prism(profile);body=C.mesh('Barrier_CastConcrete',vs,fs,M['concrete'],root)
    body['lod1_mesh']=json.dumps(dict(vertices=vs,faces=fs),separators=(',',':'))
    C.bc.add_bevel(body,.022,segments=1,limit='NONE');C.apply(body)
    body.modifiers.new('Export triangles','TRIANGULATE');C.apply(body);C.bc.shade_smooth(body,30)
    for loop in body.data.uv_layers[0].data:loop.uv/=M['concrete']['repeat_m']
    for name,points in (
        ('BaseRamp',[(-.325,0),(.325,0),(.325,.12),(.155,.43),(-.155,.43),(-.325,.12)]),
        ('UpperTaper',[(-.155,.43),(.155,.43),(.09,1.05),(-.09,1.05)]),
    ):
        vs,fs=prism(points);co=C.col_mesh('Barrier_'+name,vs,fs,'concrete',parent=root)
        body['collision_'+name]=co.name
    # Painted bands are thin face geometry, following the tapered cast face.
    # They use existing shared paint textures and add no collision thickness.
    z0,z1=.57,.89;left,right=-.78,.78
    def paint(name,points,mat,side,offset):
        vs=[(x,side*(.155-(z-.43)*(.065/.62)+offset),z) for x,z in points]
        face=tuple(range(len(vs))) if side<0 else tuple(reversed(range(len(vs))))
        ob=C.mesh(name,vs,[face],M[mat],root)
        for loop in ob.data.uv_layers[0].data:loop.uv/=M[mat]['repeat_m']
        ob['surface_detail']='painted marking; visual only'
    for side,label in ((-1,'Front'),(1,'Back')):
        paint('Barrier_'+label+'_CreamBand',[(left,z0),(right,z0),(right,z1),(left,z1)],'barrier_cream',side,.001)
        for index,x in enumerate((-.64,-.18,.28)):
            paint('Barrier_'+label+'_OrangeStripe_'+str(index),[(x,z0),(x+.15,z0),(x+.34,z1),(x+.19,z1)],'barrier_orange',side,.0015)

def hedge_frame(root):
    for x in (-2,0,2):add('Frame_Post',(.16,.16,2.85),(x,0,1.425),'darkpost',root)
    add('Frame_Header',(4.16,.16,.20),(0,0,2.81),'darkpost',root)
    add('Frame_Base',(4.16,.10,.12),(0,0,.08),'darkpost',root)
def privacy(root,gate=False):
    root['privacy_screen']=True;root['exception']='User requested tall dark timber garden dividers, 2026-10-09'
    w,h=2,2.2
    for x in (-1,1):add('Privacy_Post',(.09,.09,h),(x,0,h/2),'darkpost',root)
    group=C.empty('PrivacyLeaf') if gate else root
    for z in (.22,1.80):add('Privacy_Rail',(w,.055,.09),(0,.027,z),'darkpost',group)
    for k in range(20):
        x=-1+.05+k*.10;add('Privacy_Board',(.097,.020,h-.12),(x,-.02,h/2),'darkwood',group,.002)
    if gate:
        kids=[o for o in C.visuals() if o.parent==group]
        bpy.ops.object.select_all(action='DESELECT')
        for o in kids:o.select_set(True)
        bpy.context.view_layer.objects.active=kids[0];bpy.ops.object.join();ob=bpy.context.object;C.apply(ob);C.parent_keep(ob,root)
        cols=[o for o in bpy.context.scene.objects if o.parent==group and o.name.startswith('COL_')]
        for co in cols:C.parent_keep(co,root)
        bpy.data.objects.remove(group,do_unlink=True);ob=movable(ob,'Privacy','OPEN_DOOR',(-1,0,0),root,ajar=95,max_deg=110);ob['ajar']=12;ob['pose']='open'
        for co in cols:co.parent=ob;co.location=(1,0,0)
        handle(ob,(1.88,-.06,1.0),.08)
def rear_garage(root):
    w,d,h=4.6,5.6,3.2
    for x in (-w/2+.10,w/2-.10):add('RearGarage_Side',(.20,d,h-.12),(x,0,(h-.12)/2),'printed',root)
    add('RearGarage_Back',(w-.40,.20,h-.12),(0,d/2-.1,(h-.12)/2),'printed',root)
    add('RearGarage_Lintel',(w,.30,.24),(0,-d/2+.10,h-.24),'concrete',root)
    add('RearGarage_Coping',(w+.14,d+.14,.14),(0,0,h-.07),'concrete',root)
    add('RearGarage_Membrane',(w-.18,d-.18,.025),(0,0,h-.065),'flat_roof',root,.004)
    add('RearGarage_Floor',(w-.2,d-.1,.05),(0,0,.025),'concrete',root)
def shed(root):
    w,d,h=2.8,3.4,2.2;t=.06
    for x in (-w/2+t/2,w/2-t/2):add('Shed_Side',(t,d,h),(x,0,h/2),'wood',root)
    add('Shed_Back',(w,t,h),(0,d/2-t/2,h/2),'wood',root)
    for x in (-.975,.975):add('Shed_Front',(.85,t,h),(x,-d/2+t/2,h/2),'wood',root)
    add('Shed_Lintel',(1.1,t,.20),(0,-d/2+t/2,h-.10),'wood',root)
    add('Shed_Floor',(w,d,.05),(0,0,.025),'wood',root)
    for k in range(19):
        x=-w/2+k*w/18
        if abs(x)>.56:add('Board_Joint',(.013,.012,h-.06),(x,-d/2-.004,h/2),'post',root,.002,False)
    for sx in (-1,1):
        vs=[(sx*.01,-d/2-.12,h+.44),(sx*(w/2+.10),-d/2-.12,h),(sx*(w/2+.10),d/2+.12,h),(sx*.01,d/2+.12,h+.44)]
        ob=C.mesh('Shed_Roof',vs,[(0,1,2,3)],M['roof'],root);mod=ob.modifiers.new('Roof thickness','SOLIDIFY');mod.thickness=.065;C.apply(ob)
        verts=[*vs,*[(x,y,z-.065) for x,y,z in vs]];fs=[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
        C.col_mesh('Shed_Roof',verts,fs,'cladding',parent=root)
    leaf=add('Shed_Door',(1.04,.035,1.97),(0,-d/2-.01,1.015),'sage',root)
    leaf=movable(leaf,'Shed','OPEN_DOOR',(-.52,-d/2-.01,.03),root,ajar=100,max_deg=110);leaf['ajar']=12;leaf['pose']='open';handle(leaf,(.95,-.025,.95),.08)
def reuse(root,path,name=None):
    path=Path(path)
    if name:
        j,buf=read(path);idx=next(i for i,n in enumerate(j['nodes']) if n.get('name')==name)
        j['scenes']=[{'nodes':[idx]}];j['scene']=0;temp=CACHE/(name+'.glb');save(temp,j,buf);path=temp
    before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path))
    obs=[o for o in bpy.data.objects if o not in before]
    if name:
        chosen=next(o for o in obs if o.name==name);keep={chosen,*chosen.children_recursive}
        for o in list(obs):
            if o not in keep:bpy.data.objects.remove(o,do_unlink=True)
        obs=list(keep)
    for o in obs:
        if o.name not in bpy.context.scene.collection.objects:bpy.context.scene.collection.objects.link(o)
        if o.parent is None:C.parent_keep(o,root)
        if o.type!='MESH':continue
        for m in o.data.materials:
            nm=m.name.lower();phys='plastic'
            if any(x in nm for x in ('wood','timber','oak','batten','plywood','shed')):phys='wood_thin'
            elif any(x in nm for x in ('fabric','cloth','cushion')):phys='fabric'
            elif 'glass' in nm:phys='glass'
            elif any(x in nm for x in ('steel','alu','rim','chassis','metal','truck','car','white','trim')):phys='sheet_metal'
            m['phys']=phys
    bpy.context.view_layer.update()
    return obs
def reused_collision(root,pid):
    if pid=='moving_truck':
        for x in (-1.245,1.245):C.col_box('Truck_Side',(x-.005,-4,1.05),(x+.005,4,3.2),'sheet_metal',parent=root)
        for z in (1.05,3.195):C.col_box('Truck_Plate',(-1.25,-4,z),(1.25,4,z+.01),'sheet_metal',parent=root)
        for y in (-3.995,3.995):C.col_box('Truck_End',(-1.25,y-.005,1.05),(1.25,y+.005,3.2),'sheet_metal',parent=root)
        # Engine/chassis are heavy; body and windows have their real thin material.
        C.col_box('Truck_Engine',(-.80,5.30,.2),(.80,6.25,.92),'metal_heavy',parent=root)
        for x in (-1.075,1.075):C.col_box('Truck_Cab_Plate',(x-.005,4,.1),(x+.005,6.4,1.05),'sheet_metal',parent=root)
        for z in (.10,2.395):C.col_box('Truck_Cab_Plate',(-1.08,4,z),(1.08,6.4,z+.01),'sheet_metal',parent=root)
        C.col_box('Truck_Chassis',(-.94,-3.7,.05),(.94,4.2,1.05),'metal_heavy',parent=root)
    else:
        obs=[o for o in C.visuals()];mn,mx=C.bc.world_bounds(obs)
        if pid=='hot_tub':
            w,d,h=mx.x-mn.x,mx.y-mn.y,mx.z
            for x in (mn.x+.08,mx.x-.08):C.col_box('Tub_End',(x-.08,mn.y,0),(x+.08,mx.y,h),'plastic',parent=root)
            for y in (mn.y+.08,mx.y-.08):C.col_box('Tub_Side',(mn.x+.16,y-.08,0),(mx.x-.16,y+.08,h),'plastic',parent=root)
            C.col_box('Tub_Base',(mn.x,mn.y,0),(mx.x,mx.y,.12),'plastic',parent=root)
        elif pid=='city_car':
            C.col_box('Car_Engine',(mn.x+.15,mx.y-.70,.14),(mx.x-.15,mx.y-.08,.76),'metal_heavy',parent=root)
            C.col_box('Car_Chassis',(mn.x+.1,mn.y+.1,.06),(mx.x-.1,mx.y-.1,.16),'metal_heavy',parent=root)
            for x in (mn.x+.005,mx.x-.005):C.col_box('Car_Body',(x-.005,mn.y,.16),(x+.005,mx.y,.82),'sheet_metal',parent=root)
            for y in (mn.y+.005,mx.y-.005):C.col_box('Car_End',(mn.x,y-.005,.16),(mx.x,y+.005,.82),'sheet_metal',parent=root)
            C.col_box('Car_Roof',(mn.x,mn.y,mx.z-.01),(mx.x,mx.y,mx.z),'sheet_metal',parent=root)
        else:C.col_box(pid,list(mn),list(mx),'wood_thin' if pid=='shed' else ('fabric' if pid in ('sofa','armchair') else 'metal_heavy'),parent=root)
    if pid in ('city_car','moving_truck'):
        # Exact visual glass triangles become 15mm prisms; no filled cab collider.
        number=0
        for ob in C.visuals():
            for face in ob.data.polygons:
                m=ob.data.materials[face.material_index]
                if m.get('phys')!='glass':continue
                ps=[ob.matrix_world@ob.data.vertices[k].co for k in face.vertices]
                if len(ps)<3:continue
                for i in range(1,len(ps)-1):
                    pts=[ps[0],ps[i],ps[i+1]];n=(pts[1]-pts[0]).cross(pts[2]-pts[0])
                    longest=max((pts[(k+1)%3]-pts[k]).length for k in range(3))
                    if n.length<.005 or n.length/longest<.006:continue
                    n.normalize();v=[tuple(p-n*.0075) for p in pts]+[tuple(p+n*.0075) for p in pts]
                    C.col_mesh('Vehicle_Glass_'+str(number),v,[(0,2,1),(3,4,5),(0,1,4,3),(1,2,5,4),(2,0,3,5)],'glass',parent=root);number+=1
def save_prop(root,pid,category,source='original procedural v3',container=None):
    dest=PROPS/category/pid;dest.mkdir(parents=True,exist_ok=True);bpy.context.view_layer.update()
    obs=C.visuals();C.audit_visuals(obs);C.bc.uv_all(obs)
    for ob in obs:
        for mod in list(ob.modifiers):C.apply(ob)
    cols=[o for o in bpy.context.scene.objects if o.name.startswith('COL_')]
    rows=C.export_collision(dest/'collision.json',cols,'prop-local design metres X/Y/Z; default exported pose; parent tracks moving part')
    parts=[o for o in obs if o.name.startswith(('OPEN_DOOR_','OPEN_DRAWER_','OPEN_LID_'))]
    entry=dict(id=pid,category=category,tags=[category,'showhome_v3']+([container] if container else []),glb=str((dest/(pid+'.glb')).relative_to(ROOT/'assets')).replace('\\','/'),lod1=str((dest/(pid+'_lod1.glb')).relative_to(ROOT/'assets')).replace('\\','/'),collision=str((dest/'collision.json').relative_to(ROOT/'assets')).replace('\\','/'),source=source,licence='project original',openable_parts=[dict(name=o.name,properties={k:o[k] for k in o.keys() if k not in ('collision',)}) for o in parts])
    mn,mx=C.bc.world_bounds(obs);entry.update(size_m=list(mx-mn),triangles=C.triangles(obs),collision_volumes=len(rows),loot_slots=[o.name for o in bpy.context.scene.objects if o.name.startswith('LOOT_SLOT_')]);entry=C.plain(entry)
    export=[o for o in bpy.context.scene.objects if not o.name.startswith('COL_') and o.type in ('MESH','EMPTY')]
    C.export_glb(dest/(pid+'.glb'),export);externalize(dest/(pid+'.glb'),TEXTURES)
    # LOD retains names/pivots, slots and collision; only large curved meshes are reduced.
    mods=[];swaps=[]
    for o in obs:
        if o.get('lod1_mesh'):
            # Optional exact planar LOD: collapse must not move a painted face.
            spec=json.loads(o['lod1_mesh']);original=o.data;low=bpy.data.meshes.new(o.name+'_LOD1')
            low.from_pydata(spec['vertices'],[],spec['faces']);low.update()
            bm=bmesh.new();bm.from_mesh(low);bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.to_mesh(low);bm.free()
            for mat in original.materials:low.materials.append(mat)
            o.data=low;C.uv(o,low.materials[0].get('repeat_m',1));C.bc.shade_smooth(o,30);swaps.append((o,original,low))
        elif len(o.data.polygons)>16:
            m=o.modifiers.new('LOD1','DECIMATE');m.ratio=.45;mods.append((o,m))
    C.export_glb(dest/(pid+'_lod1.glb'),export);externalize(dest/(pid+'_lod1.glb'),TEXTURES)
    base,_=read(dest/(pid+'.glb'));lod,lbuf=read(dest/(pid+'_lod1.glb'));extras={m['name']:m.get('extras',{}) for m in base['materials']}
    for m in lod['materials']:m['extras']=extras[m['name']]
    save(dest/(pid+'_lod1.glb'),lod,lbuf)
    for o,m in mods:o.modifiers.remove(m)
    for o,original,low in swaps:o.data=original;bpy.data.meshes.remove(low)
    C.write(dest/'metadata.json',entry);bpy.ops.wm.save_as_mainfile(filepath=str(dest/(pid+'.blend')))
    C.write(dest/'QA.json',dict(phys_ok=True,uv_ok=True,convex_collision_ok=True,min_thickness_m=min((r['thickness_m'] for r in rows),default=0),lod0_triangles=entry['triangles'],openables=len(parts)))
    CATALOG.append(entry);print('PROP_READY',pid,entry['triangles'],len(rows),flush=True)
    if '--render' in sys.argv:
        cam=C.stage();bpy.context.scene.render.resolution_x=560;bpy.context.scene.render.resolution_y=560;bpy.context.scene.cycles.samples=12
        centre=(mn+mx)/2;s=max(mx-mn);C.render(cam,dest/'renders/three_quarter.png',centre+Vector((s*1.5,-s*2,s*1.1)),centre,s*1.65)
        if parts:
            # Three poses are rendered from the same camera, with the actual moving collision.
            for pose in ('closed','ajar','open'):
                for o in parts:
                    if o.name.startswith('OPEN_DRAWER_'):
                        o.location=Vector(o['closed_location']);o.location.y-=0 if pose=='closed' else (o['ajar'] if pose=='ajar' else o['travel_m'])
                    else:o.rotation_euler['XYZ'.index(o['axis'])]=math.radians(0 if pose=='closed' else o['ajar'] if pose=='ajar' else o['min_deg'] if o['min_deg']<0 else o['max_deg'])
                C.render(cam,dest/('renders/'+pose+'.png'),centre+Vector((s*1.5,-s*2,s*1.1)),centre,s*1.65)

def main():
    only=None
    if '--only' in sys.argv:only=set(sys.argv[sys.argv.index('--only')+1].split(','))
    specs=[
     ('kitchen_base','containers','kitchen_cabinet',(.9,.60,.90,'doors','sage')),
     ('kitchen_wall','containers','kitchen_cabinet',(.9,.34,.75,'doors','cream')),
     ('kitchen_drawer','containers','kitchen_cabinet',(.60,.60,.90,'drawers','sage')),
     ('dresser','containers','dresser',(1.25,.50,1.0,'drawers','wood')),
     ('nightstand','containers','dresser',(.5,.40,.55,'drawers','wood')),
     ('wardrobe','containers','dresser',(1.4,.6,2.05,'doors','wood')),
     ('garage_cabinet','containers','toolbox',(1.4,.60,.92,'drawers','olive')),
    ]
    for pid,cat,cnt,dims in specs:
        if only and pid not in only:continue
        root=begin(pid,cat,cnt,mount='wall' if pid=='kitchen_wall' else None);cabinet(root,*dims)
        if pid=='kitchen_wall':
            for ob in root.children:ob.location.y-=dims[1]/2
        save_prop(root,pid,cat,container=cnt)
    specs=[('ammo_box','ammo_box',.52,.25,.38,'olive',False),('ammo_crate','ammo_box',.65,.42,.38,'wood',True),('weapon_case','weapon_case',1.12,.34,.16,'olive',False),('weapon_crate','weapon_case',1.25,.44,.32,'wood',True),('metal_crate','metal_crate',.85,.55,.55,'olive',False),('toolbox','toolbox',.48,.24,.26,'redsteel',False),('gang_box','toolbox',1.2,.65,.72,'yellow',False)]
    for pid,cnt,w,d,h,mat,wood in specs:
        if only and pid not in only:continue
        root=begin(pid,'containers',cnt,'small' if w<.6 else 'large');chest(root,w,d,h,mat,wood=wood);save_prop(root,pid,'containers',container=cnt)
    for pid in ('backpack','duffel_bag'):
        if only and pid not in only:continue
        root=begin(pid,'containers',pid,'small');open_bag(root,pid=='backpack');save_prop(root,pid,'containers',container=pid)
    models={'privacy_panel':('fences',privacy),'privacy_gate':('fences',lambda r:privacy(r,True)),'rear_garage':('garden',rear_garage),'greenhouse':('garden',greenhouse),'shed':('garden',shed),'carport':('garden',carport),'pergola':('garden',lambda r:carport(r,True)),'picket_panel':('fences',fence),'picket_panel_short':('fences',lambda r:fence(r,width_override=1.75)),'garden_gate':('fences',lambda r:fence(r,gate=True)),'site_mesh_panel':('fences',lambda r:fence(r,mesh_site=True)),'concrete_barrier':('worksite',concrete_barrier),'hedge_frame':('garden',hedge_frame),'raised_planter':('garden',planter),'bookcase':('furniture',bookcase),'dining_table':('furniture',lambda r:furniture(r,'dining_table')),'bed':('furniture',lambda r:furniture(r,'bed')),'utility_pole':('utilities',pole)}
    for pid,(cat,fn) in models.items():
        if only and pid not in only:continue
        root=begin(pid,cat);fn(root);save_prop(root,pid,cat)
    models={'moving_truck':('vehicles','MoverTruck'),'city_car':('vehicles','GarageCar'),'hot_tub':('garden','HotTub'),'sofa':('furniture','Sofa'),'heat_pump':('utilities','HeatPump')}
    for pid,(cat,old) in models.items():
        if only and pid not in only:continue
        root=begin(pid,cat);reuse(root,ROOT/'assets/maps/showhome/kit/props.glb','PROP_'+old+'_Root');reused_collision(root,pid);save_prop(root,pid,cat,'original assets/maps/showhome procedural '+old)
    if not only or 'armchair' in only:
        root=begin('armchair','furniture');reuse(root,PROPS/'armchair_procedural/armchair.glb');reused_collision(root,'armchair');save_prop(root,'armchair','furniture','original assets/props/armchair_procedural')
    # Merge by id; do not discard other sessions' catalog entries.
    p=PROPS/'catalog.json';existing=json.loads(p.read_text()) if p.exists() else {'schema':1,'props':[]}
    existing['props']=[r for r in existing.get('props',[]) if r['id'] not in {r['id'] for r in CATALOG}]+CATALOG
    existing.update(frame='prop-local metres; Blender X/Y/Z, glTF X/Z/-Y',schema=1);C.write(p,existing)
    C.write(HERE/'library_manifest.json',dict(props=existing['props'],texture_storage='shared external images in maps/showhome_v3/textures; no repeated embedded images'))
if __name__=='__main__':main()
