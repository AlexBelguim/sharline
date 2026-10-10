"""Kestrel v2: clean authored clothing / hair, shared deforming heroine rig.

Run: Blender 5.2 -b --factory-startup -P this_file.py -- [--quick]
No image-to-3D geometry is read. Direction log supersedes old armor / monocle brief.
"""
import os
import sys
import math
import json
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'assets/characters/_shared'))
import blender_common as bc
import character_v2 as cv
sys.path.insert(0, str(OUT))
import kestrel_face_rain as kestrel_face
import kestrel_hair
import kestrel_outfit_finish
import kestrel_cloth_polish
import rain_anatomy
import skin_parts

QUICK = '--quick' in sys.argv
OWN = []
BASE = None
M = {}


def mesh(name, verts, faces, mat, smooth=True):
    me = bpy.data.meshes.new('KES_' + name)
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('KES_' + name, me)
    bpy.context.scene.collection.objects.link(ob)
    bc.assign(ob, mat)
    if smooth:
        bc.shade_smooth(ob, 48)
    OWN.append(ob)
    return ob


def reg(ob, region='torso', bone=None):
    if ob not in OWN:
        OWN.append(ob)
    # Freeze garment transforms before the weight function reads global vertices.
    bpy.context.view_layer.update()
    if ob.type == 'MESH':
        if len(ob.modifiers):
            bc.apply_modifiers(ob)
        ob.data.transform(ob.matrix_world)
        ob.matrix_world = Matrix.Identity(4)
        if bone:
            cv.rigid(ob, BASE, bone)
        else:
            cv.bind(ob, BASE, region)
    return ob


def catmull(path, samples=5):
    pts = [Vector(path[0])] + [Vector(p) for p in path] + [Vector(path[-1])]
    out = []
    for i in range(1, len(pts)-2):
        a,b,c,d=pts[i-1:i+3]
        for j in range(samples):
            t=j/samples
            out.append(((b*2)+(c-a)*t+(a*2-b*5+c*4-d)*t*t+(-a+b*3-c*3+d)*t*t*t)*.5)
    return out+[Vector(path[-1])]


def ring(c, rx, ry, n=32, power=2.2, axes=None):
    u,v=axes or (Vector((1,0,0)),Vector((0,1,0)))
    c=Vector(c)
    out=[]
    for j in range(n):
        a=j*math.tau/n
        ca,sa=math.cos(a),math.sin(a)
        out.append(c + u*rx*math.copysign(abs(ca)**(2/power),ca)+v*ry*math.copysign(abs(sa)**(2/power),sa))
    return out


def loft(name, rings, mat, cap=False, region='torso', bone=None):
    n=len(rings[0]); v=[p for r in rings for p in r]; f=[]
    for k in range(len(rings)-1):
        for j in range(n):
            f.append((k*n+j,k*n+(j+1)%n,(k+1)*n+(j+1)%n,(k+1)*n+j))
    if cap:
        f.extend((tuple(reversed(range(n))), tuple(range((len(rings)-1)*n,len(rings)*n))))
    ob=mesh(name,v,f,mat)
    return reg(ob,region,bone)


def body(name, rows, mat, sides=40, region='torso', cap=False):
    # Four interpolation rings per authored station make clean deformation contours.
    rr=[]
    for a,b in zip(rows[:-1],rows[1:]):
        for j in range(3):
            t=j/3; row=[a[k]*(1-t)+b[k]*t for k in range(5)]
            z,rx,ry,cy,p=row
            rr.append(ring((0,cy,z),rx,ry,sides,p))
    z,rx,ry,cy,p=rows[-1];rr.append(ring((0,cy,z),rx,ry,sides,p))
    return loft(name,rr,mat,cap,region)


def tube(name, points, radii, mat, sides=32, samples=4, region='torso', bone=None, cap=True, fold=0):
    pts=[Vector(p) for p in points]; path=catmull(pts,samples); rs=[]
    for a,b in zip(radii[:-1],radii[1:]):
        a=(a,a) if isinstance(a,(float,int)) else a
        b=(b,b) if isinstance(b,(float,int)) else b
        for j in range(samples):
            t=j/samples;rs.append((a[0]*(1-t)+b[0]*t,a[1]*(1-t)+b[1]*t))
    r=radii[-1];rs.append((r,r) if isinstance(r,(float,int)) else r)
    rr=[]
    for i,(p,r) in enumerate(zip(path,rs)):
        t=(path[min(i+1,len(path)-1)]-path[max(i-1,0)]).normalized()
        ref=Vector((0,-1,0)) if abs(t.y)<.9 else Vector((0,0,1))
        v=(ref-t*ref.dot(t)).normalized();u=v.cross(t).normalized()
        sec=ring(p,r[0],r[1],sides,2.25,(u,v))
        phase=.83 if name.endswith('_L') else -.46
        if name.startswith('PantsLeg') and p.z<.57:
            # Wrinkles are stronger on the front/outer faces, not full circular
            # rings. Smooth reference radii retain the slightly loose calf.
            stations=[(.135,.047,.052),(.241,.052,.054),(.385,.065,.068),(.472,.055,.058),(.57,.065,.067)]
            arow,brow=stations[0],stations[-1]
            for aa,bb in zip(stations[:-1],stations[1:]):
                if aa[0]<=p.z<=bb[0]:arow,brow=aa,bb;break
            tt=max(0,min(1,(p.z-arow[0])/(brow[0]-arow[0])))
            r0=arow[1]*(1-tt)+brow[1]*tt;r1=arow[2]*(1-tt)+brow[2]*tt
            neutral=ring(p,r0,r1,sides,2.25,(u,v))
            sec=[neutral[k].lerp(q,.30+.70*max(0,math.sin(k*math.tau/sides+phase))**2) for k,q in enumerate(sec)]
        if fold:
            for k,q in enumerate(sec):
                a=k*math.tau/sides
                # A few broad fabric folds, no random surface noise.
                q += (q-p).normalized()*(fold*math.sin(i*.8+a*2+phase)*(.35+.65*math.sin(i/max(len(path)-1,1)*math.pi)**2))
                # Folds slope across the limb rather than forming machined rings.
                q += t*(fold*2.4*math.sin(a+i*.17+phase))
        rr.append(sec)
    return loft(name,rr,mat,cap,region,bone)


def box(name, size, loc, mat, bevel=.004, region='torso', bone=None, rot=(0,0,0)):
    return reg(bc.box('KES_'+name,size,loc,rot,mat=mat,bevel=bevel,segments=2),region,bone)


def ribbon(name,path,width,depth,mat,region='torso',bone=None,normal=(0,-1,0)):
    pp=catmull(path,7);rr=[]
    for i,p in enumerate(pp):
        t=(pp[min(i+1,len(pp)-1)]-pp[max(0,i-1)]).normalized()
        no=Vector(normal);u=t.cross(no).normalized()
        if u.length<.1:u=Vector((1,0,0))
        no=u.cross(t).normalized()
        rr.append([p+u*width/2+no*depth/2,p-u*width/2+no*depth/2,p-u*width/2-no*depth/2,p+u*width/2-no*depth/2])
    return loft(name,rr,mat,True,region,bone)


def panel(name,outline,center,thick,mat,wrap=1.6,region='torso',bone=None,bevel=.003):
    cx,cy,cz=center; n=len(outline)
    verts=[]
    for depth in (-thick/2,thick/2):
        for x,z in outline:
            y=cy+depth+wrap*(x*x+1.2*z*z)*(1 if cy<0 else -1)
            verts.append((cx+x,y,cz+z))
    f=[tuple(reversed(range(n))),tuple(range(n,2*n))]
    f.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    ob=mesh(name,verts,f,mat,False)
    bc.add_bevel(ob,bevel,2)
    return reg(ob,region,bone)


def paint(ob, key, strength=.20):
    """Intrinsic painted colour lives in baked PBR maps, without normal-based tints."""
    ob['surface_paint']='restrained shared Krea2 brush colour, portable baked PBR'


def make_clothes():
    suit=body('UnderSuit',[(.98,.149,.105,.006,2.3),(1.02,.134,.098,.004,2.3),(1.07,.118,.087,0,2.3),(1.13,.126,.094,0,2.3),(1.19,.135,.103,0,2.3)],M['suit']);paint(suit,'suit')
    jacket=body('Jacket',[(1.14,.132,.098,0,2.4),(1.17,.136,.102,0,2.4),(1.22,.148,.110,-.004,2.4),(1.27,.156,.118,-.008,2.4),(1.32,.160,.112,-.004,2.5),(1.37,.163,.100,0,2.6),(1.405,.150,.086,.004,2.8),(1.425,.110,.074,.008,2.4),(1.437,.072,.066,.008,2)],M['jacket']);paint(jacket,'jacket')
    body('JacketHem',[(1.139,.136,.102,0,2.4),(1.147,.137,.103,0,2.4),(1.157,.137,.103,0,2.4),(1.169,.138,.103,0,2.4)],M['graph'])
    for z in (1.145,1.155,1.164):
        body('HemRib_'+str(z),[(z-.001,.138,.104,0,2.4),(z+.001,.138,.104,0,2.4)],M['jacket'],sides=40)
    for s in (-1,1):
        ribbon('JacketSideSeam_'+str(s),[(s*.139,-.076,1.17),(s*.154,-.081,1.245),(s*.159,-.069,1.337)],.003,.0015,M['jacketLight'])
    # Funnel collar has a clean V opening and a continuous teal inside / top lip.
    n=60;rr=[]
    for z,rx,ry,cy in [(1.404,.090,.083,.008),(1.45,.081,.077,.008),(1.504,.087,.083,.003)]:
        sec=[]
        for j in range(n):
            a=math.tau*j/n; x=rx*math.cos(a); y=cy+ry*math.sin(a)
            zz=z
            if z>1.5:
                zz+=.035*(math.sin(a)+1)/2
                if math.sin(a)<-.75:
                    zz-=.042*max(0,1-abs(x)/.035)
            sec.append(Vector((x,y,zz)))
        rr.append(sec)
    co=loft('Collar',rr,M['jacket']);paint(co,'jacket')
    inner=[[Vector((p.x*.91,(p.y-.006)*.90+.006,p.z-.001)) for p in r] for r in rr]
    loft('CollarLining',inner,M['graph'])
    # Connect lip rather than exposed sheet edge.
    vv=rr[-1]+inner[-1];ff=[(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)]
    reg(mesh('CollarLip',vv,ff,M['teal']))
    ribbon('SuitZip',[(.006,-.103,.995),(.006,-.090,1.07),(.006,-.098,1.14)],.003,.0016,M['teal'])
    ribbon('CollarZip',[(.002,-.080,1.43),(.004,-.084,1.463)],.004,.002,M['gun'])
    box('ZipPull',(.007,.004,.015),(.004,-.087,1.447),M['gun'],.001)

    # Shaped crotch hem arches upward over the thighs. Separate clothing surfaces
    # overlap internally, avoiding the horizontal pelvis apron of a blockout.
    pelvis=body('PantsPelvis',[(.80,.120,.073,.010,2.2),(.890,.170,.115,.010,2.3),(.96,.160,.110,.008,2.2),(1.001,.152,.106,.006,2.2)],M['pants'],region='pelvis')
    for vert in pelvis.data.vertices:
        w=max(0,1-(vert.co.z-.80)/.09)
        vert.co.z += .073*(abs(vert.co.x)/.120)**.7*w
    pelvis.data.update();paint(pelvis,'pants')
    for s,side in ((1,'L'),(-1,'R')):
        region='leg_'+side.lower()
        pp=[(s*.085,.005,.88),(s*.094,0,.77),(s*.100,-.004,.66),
            (s*.104,-.006,.565),(s*.105,-.007,.535),(s*.107,-.008,.505),
            (s*.110,-.008,.472),(s*.113,.002,.385),(s*.115,.006,.300),
            (s*.117,.006,.241),(s*.118,.006,.214),(s*.118,.006,.187),
            (s*.118,.006,.162),(s*.118,.006,.135)]
        radii=[(.091,.097),(.088,.092),(.078,.082),(.064,.066),(.069,.068),(.059,.060),
               (.055,.058),(.065,.068),(.059,.062),(.052,.054),(.059,.058),(.0485,.050),(.0545,.056),(.047,.052)]
        legs=tube('PantsLeg_'+side,pp,radii,M['pants'],sides=32,samples=3,region=region,fold=.0025);paint(legs,'pants')
        # Broad seam and angular stitched patches give cloth the designed
        # painted plane rhythm seen in the concepts without high-frequency grime.
        ribbon('PantOuterSeam_'+side,[(s*.176,-.006,.855),(s*.170,-.005,.752),(s*.159,-.007,.646),(s*.155,-.006,.539)],.0023,.0012,M['pantsLight'],region,normal=(s,0,0))
        for z,x,r in [( .478,.11,.063),(.507,.108,.063)]:
            loft('KneeStrap_'+side+'_'+str(z),[ring((s*x,-.006,z-.011),r,r,32),ring((s*x,-.006,z+.011),r,r,32)],M['web'],False,region)
        out=[(-.026,.063),(.026,.063),(.049,.038),(.046,-.030),(.028,-.064),(-.028,-.064),(-.047,-.030),(-.049,.038)]
        panel('KneePad_'+side,out,(s*.11,-.079,.476),.015,M['bone'],wrap=2.6,region=region,bone='calf_'+side.lower(),bevel=.004)
        panel('KneeInset_'+side,[(-.025,.039),(.025,.039),(.033,.021),(.029,-.026),(0,-.039),(-.029,-.026),(-.033,.021)],(s*.11,-.091,.479),.008,M['boneShade'],wrap=2.6,region=region,bone='calf_'+side.lower(),bevel=.004)
        panel('KneeLowerFacet_'+side,[(-.024,-.031),(0,-.042),(.024,-.031),(.022,-.047),(0,-.058),(-.022,-.047)],(s*.11,-.091,.479),.004,M['padShadow'],wrap=2.6,region=region,bone='calf_'+side.lower(),bevel=.003)
        box('KneeVent_'+side,(.038,.005,.007),(s*.11,-.092,.524),M['graph'],.002,region,'calf_'+side.lower())
        # Lean ankle boot with separate broad sole / toe cap / heel counter.
        profile=[(.065,.020),(-.195,.020),(-.207,.033),(-.202,.052),(-.15,.073),(-.070,.09),(-.045,.151),(.050,.155),(.061,.092),(.073,.039)]
        boot=bc.profile_extrude('KES_Boot_'+side,profile,.096,loc=(s*.118,.010,0),mat=M['jacket'],bevel=.007,segments=3)
        boot.rotation_euler.z=math.radians(-s*8);reg(boot,region,'foot_'+side.lower())
        sole=bc.profile_extrude('KES_BootSole_'+side,[(.069,0),(-.196,0),(-.211,.012),(-.206,.027),(.074,.027)],.102,loc=(s*.118,.010,0),mat=M['graph'],bevel=.004)
        sole.rotation_euler.z=math.radians(-s*8);reg(sole,region,'foot_'+side.lower())
        toe=bc.profile_extrude('KES_BootToe_'+side,[(-.203,.031),(-.200,.052),(-.154,.071),(-.127,.070),(-.133,.038)],.098,loc=(s*.118,.010,0),mat=M['bone'],bevel=.004)
        toe.rotation_euler.z=math.radians(-s*8);reg(toe,region,'foot_'+side.lower())
        box('BootHeel_'+side,(.096,.019,.052),(s*.118,.071,.045),M['boneShade'],.005,region,'foot_'+side.lower())
        for k in range(3):
            box('BootLace_'+side+str(k),(.047,.006,.006),(s*.118,-.058+.013*k,.093+.014*k),M['graph'],.001,region,'foot_'+side.lower())
        joint=BASE['joints']
        sh=Vector(joint['upperarm_'+side.lower()]);el=Vector(joint['lowerarm_'+side.lower()]);wr=Vector(joint['hand_'+side.lower()])
        ad=(el-sh).normalized();fd=(wr-el).normalized();cuff=el+fd*.102
        sr='arm_'+side.lower()
        path=[(s*.13,.007,1.365),sh+Vector((s*.01,0,.012)),sh+ad*.07,sh+ad*.16,
              el-ad*.055,el-ad*.020,el+fd*.012,el+fd*.046,el+fd*.076,cuff]
        rad=[.057,.061,.058,.054,.050,.061,.048,.060,.048,.045]
        sl=tube('Sleeve_'+side,path,rad,M['jacket'],sides=26,samples=4,region=sr,fold=.0045);paint(sl,'jacket')
        tube('SleeveCuff_'+side,[cuff-fd*.023,cuff+fd*.006],[.046,.044],M['graph'],samples=3,region=sr)
        upper=Vector((0,0,1));up=(upper-fd*fd.z).normalized()
        # Small teal seam, follows sleeve top / outer line.
        seam=[sh+Vector((0,-.016,.058)),sh+ad*.10+Vector((0,-.043,.028)),el-ad*.015+up*.052,el+fd*.05+up*.054,cuff+up*.044]
        tube('SleevePiping_'+side,seam,[.0018]*len(seam),M['teal'],sides=8,samples=5,region=sr)
        tube('GloveCuff_'+side,[wr-fd*.027,wr+fd*.009],[.032,.031],M['graph'],sides=28,samples=3,region=sr,bone='hand_'+side.lower())
        # Fingerless glove follows actual palm topology and keeps the shared
        # articulated fingers, instead of floating a global box over the hand.
        hand=bpy.data.objects['KES_Hand_'+side]
        hand.data.materials.append(M['graph'])
        for po in hand.data.polygons:
            if (po.center-wr).dot(fd)<.108:
                po.material_index=len(hand.data.materials)-1
        h=wr+fd*.060+Vector((0,.017,0))
        gp=bc.box('KES_GlovePanel_'+side,(.043,.006,.045),h,mat=M['boneShade'],bevel=.005,segments=2)
        gp.rotation_euler=fd.to_track_quat('Z','Y').to_euler()
        reg(gp,sr,'hand_'+side.lower())
        if s==1:
            tube('GrappleBracer',[wr-fd*.120,wr-fd*.035],[.041,.035],M['graph'],sides=32,samples=5,region=sr,bone='lowerarm_l')
            tube('GrappleHousing',[wr-fd*.128+up*.037,wr-fd*.045+up*.037,wr+fd*.019+up*.037],[(.026,.019),(.027,.020),(.017,.014)],M['bone'],sides=12,samples=4,region=sr,bone='lowerarm_l')
            tube('GrappleRail',[wr-fd*.14+up*.055,wr+fd*.048+up*.055],[(.011,.010),(.011,.010)],M['graph'],sides=8,samples=4,region=sr,bone='lowerarm_l')
            tube('GrappleAccent',[wr-fd*.11+up*.057,wr+fd*.012+up*.052],[.0025,.0025],M['teal'],sides=8,samples=4,region=sr,bone='lowerarm_l')
            tube('GrappleHook',[wr+fd*.043+up*.055,wr+fd*.072+up*.054],[.009,.004],M['gun'],sides=12,samples=2,region=sr,bone='lowerarm_l')
            spool=bc.cylinder('KES_GrappleSpool',.020,.016,loc=wr-fd*.069+up*.038+Vector((0,.036,0)),rot=(90,0,0),verts=24,mat=M['gun'],bevel=.002)
            reg(spool,sr,'lowerarm_l')


def make_gear():
    out=[(-.042,.100),(.042,.100),(.060,.084),(.092,.084),(.126,.042),(.127,-.010),(.100,-.067),(.050,-.073),(.034,-.101),(-.034,-.101),(-.050,-.073),(-.100,-.067),(-.127,-.010),(-.126,.042),(-.092,.084),(-.060,.084)]
    panel('ChestPlate',out,(0,-.137,1.269),.014,M['bone'],wrap=1.7,bevel=.004)
    panel('ChestFacet',[(-.038,.087),(.038,.087),(.055,.073),(.084,.070),(.110,.037),(.084,-.008),(-.083,-.008),(-.110,.037),(-.084,.070),(-.055,.073)],(0,-.149,1.269),.004,M['boneLight'],wrap=1.5,bevel=.002)
    # The raised upper facet is the plane break; no built-in tier glyphs.
    panel('BackPlate',[(-.073,.085),(.073,.085),(.104,.054),(.102,-.046),(.048,-.083),(.027,-.069),(-.027,-.069),(-.048,-.083),(-.102,-.046),(-.104,.054)],(0,.124,1.312),.015,M['bone'],wrap=1.5,bevel=.004)
    panel('BackFacet',[(-.061,.067),(.061,.067),(.076,.048),(.035,.013),(-.035,.013),(-.076,.048)],(0,.136,1.312),.004,M['boneLight'],wrap=1.5,bevel=.002)
    for s in (-1,1):
        ribbon('ShoulderHarness_'+str(s),[(s*.084,-.127,1.366),(s*.105,-.084,1.411),(s*.112,.008,1.438),(s*.100,.091,1.411),(s*.077,.130,1.389)],.032,.007,M['web'],normal=(s*.1,-.8,.5))
        ribbon('RibHarness_'+str(s),[(s*.118,-.112,1.214),(s*.145,-.066,1.202),(s*.144,.06,1.205),(s*.114,.116,1.220)],.025,.006,M['web'],normal=(s,0,0))
        box('HarnessBuckle_'+str(s),(.025,.009,.021),(s*.103,-.115,1.367),M['gun'],.002)
    body('Belt',[(.958,.166,.118,.006,2.3),(.969,.164,.118,.006,2.3),(.993,.160,.114,.006,2.3)],M['graph'],region='pelvis')
    box('BeltBuckle',(.044,.015,.027),(0,-.121,.976),M['gun'],.004,'pelvis')
    for i,(x,y,r) in enumerate(((.074,-.117,20),(.133,-.081,40))):
        box('Pouch'+str(i),(.044,.033,.061),(x,y,.945),M['web'],.006,'pelvis',rot=(0,0,r))
        box('PouchFlap'+str(i),(.046,.012,.024),(x,y-.018,.965),M['webLight'],.004,'pelvis',rot=(0,0,r))
        box('PouchSnap'+str(i),(.009,.005,.008),(x,y-.026,.958),M['gun'],.001,'pelvis',rot=(0,0,r))
    box('CargoPocket',(.028,.10,.125),(.184,-.001,.687),M['pants'],.006,'leg_l','thigh_l')
    box('CargoFlap',(.034,.106,.033),(.190,-.001,.737),M['jacket'],.004,'leg_l','thigh_l')
    for z,x,r in ((.72,.10,.086),(.646,.104,.077)):
        loft('HolsterStrap'+str(z),[ring((-x,0,z-.013),r,r,40),ring((-x,0,z+.013),r,r,40)],M['web'],False,'leg_r','thigh_r')
        box('HolsterBuckle'+str(z),(.021,.010,.027),(-x,-r-.003,z),M['gun'],.002,'leg_r','thigh_r')
    h=bc.profile_extrude('KES_Holster',[(-.057,.105),(.053,.105),(.063,.070),(.055,-.080),(.037,-.10),(-.031,-.10),(-.058,-.076)],.035,loc=(-.196,-.005,.736),mat=M['web'],bevel=.006)
    reg(h,'leg_r','thigh_r')
    box('HolsterGrip',(.025,.035,.065),(-.196,.028,.867),M['graph'],.005,'leg_r','thigh_r',rot=(12,0,0))
    ribbon('HolsterDrop',[(-.153,0,.974),(-.177,-.005,.893),(-.197,-.005,.833)],.025,.006,M['web'],'leg_r','thigh_r',normal=(-1,0,0))
    box('JetPackBody',(.211,.079,.132),(0,.156,1.171),M['graph'],.016)
    box('JetPackSpine',(.052,.019,.077),(0,.131,1.254),M['graph'],.006)
    for s,side in ((1,'L'),(-1,'R')):
        p=Vector((s*.100,.186,1.130));d=Vector((s*.31,.55,-.78)).normalized()
        pod=bc.lathe('KES_Thruster_'+side,[(0,-.025),(.035,-.025),(.045,-.017),(.046,.031),(.042,.051),(.034,.060),(0,.060)],steps=32,loc=p,mat=M['bone'])
        pod.rotation_euler=d.to_track_quat('Z','Y').to_euler();reg(pod)
        nozzle=bc.lathe('KES_Nozzle_'+side,[(.028,.055),(.033,.060),(.045,.105),(.045,.112),(.039,.112),(.037,.104),(.025,.060),(.028,.055)],steps=32,loc=p,mat=M['gun'])
        nozzle.rotation_euler=d.to_track_quat('Z','Y').to_euler();reg(nozzle)
        core=bc.cylinder('KES_JetCore_'+side,.030,.004,loc=p+d*.092,verts=32,mat=M['glow']);core.rotation_euler=d.to_track_quat('Z','Y').to_euler();reg(core)
        band=bc.lathe('KES_JetBand_'+side,[(.034,.056),(.036,.056),(.038,.064),(.036,.066),(.034,.056)],steps=32,loc=p,mat=M['teal']);band.rotation_euler=d.to_track_quat('Z','Y').to_euler();reg(band)


def hair_clump(name,path,width,thick,teal=.30):
    raw=catmull(path,8);rr=[];c=Vector((0,.006,1.588));pp=[]
    for point in raw:
        p=point.copy()
        if p.z>1.565:
            d=p-c
            r=math.sqrt((d.x/.084)**2+(d.y/.105)**2+(d.z/.128)**2)
            wanted=1+(thick*.23+.001)/.10
            if r>wanted:
                blend=max(0,min(1,(p.z-1.565)/.085));blend=blend*blend*(3-2*blend)
                p=p.lerp(c+d*(wanted/r),blend)
        pp.append(p)
    for i,p in enumerate(pp):
        t=i/max(len(pp)-1,1)
        tan=(pp[min(i+1,len(pp)-1)]-pp[max(i-1,0)]).normalized()
        norm=Vector((p.x/.084**2,(p.y-.004)/.104**2,(p.z-1.588)/.122**2)).normalized()
        u=tan.cross(norm).normalized()
        if u.length<.2:u=Vector((1,0,0))
        norm=u.cross(tan).normalized()
        if norm.dot(p-c)<0:norm=-norm
        if t<.20:
            p=p-norm*(.013*(1-t/.20))
        taper=max(.04,(1-t)**.4)
        # A broad lens section with flattened fronts makes painted hair wedges.
        section=[(1,0),(.75,.60),(.28,.90),(-.28,.90),(-.75,.60),(-1,0),(-.75,-.5),(-.28,-.7),(.28,-.7),(.75,-.5)]
        rr.append([p+u*sx*width/2*taper+norm*sy*thick/2*taper for sx,sy in section])
    ob=loft(name,rr,M['hair'],True,'head','head')
    for mm in (M['hairLight'],M['hairShade'],M['hairTeal'],M['hairTealLight']):ob.data.materials.append(mm)
    for po in ob.data.polygons:
        # Infer station from vertex indices: cap polygons appear at the end of
        # the face list but their roots must never inherit dyed tip material.
        idx=sum(vi//10 for vi in po.vertices)/len(po.vertices)
        t=idx/max(len(pp)-1,1);sec=po.index%10
        if teal and t>1-teal:po.material_index=3 if sec<5 else 4
        elif 1<=sec<=3:po.material_index=1
        elif sec>=6:po.material_index=2
        po.use_smooth=False
    return ob


def make_hair():
    # Open cap follows scalp, does not become a full helmet around the face.
    rr=[];n=56
    for i in range(13):
        q=i/12;sec=[]
        for j in range(n):
            a=j*math.tau/n;front=max(0,-math.sin(a));left=max(0,math.cos(a))
            bottom=1.535+.115*front+.065*left
            z=1.716*(1-q)+bottom*q
            dz=(z-1.588)/.128
            r=math.sqrt(max(.01,1-dz*dz))
            sec.append((.084*r*math.cos(a),.006+.105*r*math.sin(a),z))
        rr.append(sec)
    cap=loft('HairCap',rr,M['hair'],True,'head','head')
    cap.data.materials.append(M['hairLight'])
    for p in cap.data.polygons:
        if (p.index%n)//7 in (1,5):p.material_index=1
    vv=[];ff=[];nz=12;na=14
    head=bpy.data.objects['KES_Head']
    scalp=BVHTree.FromObject(head,bpy.context.evaluated_depsgraph_get())
    for k in range(nz):
        z=1.586+(1.644-1.586)*k/(nz-1)
        q=math.sqrt(max(.01,1-((z-1.588)/.114)**2))
        for j in range(na):
            a=-.12+1.30*j/(na-1)
            p=Vector((.076*q*math.cos(a),.004+.096*q*math.sin(a),z))
            hit,norm,_,_=scalp.find_nearest(p)
            vv.append(hit+norm*.0015)
    for k in range(nz-1):
        for j in range(na-1):
            a=k*na+j;cy=sum(vv[idx][1] for idx in (a,a+1,a+na,a+na+1))/4;cz=sum(vv[idx][2] for idx in (a,a+1,a+na,a+na+1))/4
            if -.013<cy<.035 and 1.586<cz<1.601:continue
            ff.append((a,a+1,a+na+1,a+na))
    reg(mesh('HairBuzz',vv,ff,M['hairBuzz']),'head','head')
    clumps=[
      ('Fringe',[(.030,-.084,1.675),(-.017,-.107,1.651),(-.061,-.103,1.610),(-.085,-.081,1.546),(-.081,-.062,1.468)],.057,.018,.31),
      ('RightFront',[(.016,-.047,1.713),(-.053,-.066,1.691),(-.094,-.056,1.623),(-.100,-.040,1.548),(-.091,-.044,1.488)],.065,.025,.28),
      ('RightBack',[(.009,.030,1.716),(-.054,.044,1.690),(-.096,.050,1.614),(-.095,.052,1.542),(-.084,.042,1.490)],.063,.024,.28),
      ('BackRight',[(0,.079,1.699),(-.047,.106,1.651),(-.064,.114,1.580),(-.062,.104,1.514)],.058,.022,.28),
      ('BackCentre',[(.021,.085,1.699),(.003,.118,1.645),(-.005,.118,1.565),(.000,.100,1.509)],.060,.022,.3),
      ('BackLeft',[(.043,.083,1.695),(.060,.105,1.642),(.065,.103,1.584),(.058,.091,1.549)],.052,.020,.3),
      ('LeftSweep',[(.031,-.077,1.674),(.070,-.063,1.650),(.092,-.041,1.623)],.050,.018,0),
      ('LeftCrown',[(.031,-.002,1.710),(.071,.013,1.674),(.092,.033,1.632)],.051,.018,0),
      ('Crown',[(.034,-.060,1.702),(-.010,-.024,1.722),(-.053,.020,1.701),(-.083,.051,1.656)],.065,.026,0),
    ]
    for name,path,w,t,tip in clumps:hair_clump('Hair_'+name,path,w,t,tip)


def make_lens():
    # Direction v06: LEFT eye is visible through a small six-sided tinted lens.
    ec=Vector(BASE['dims']['eye_center_L'])
    eye_delta=ec.z-1.596
    c=Vector((ec.x,BASE['dims']['eye_front_y']-.012,ec.z))
    a=math.radians(15);u=Vector((math.cos(a),math.sin(a),0));v=Vector((0,0,1));nf=u.cross(v)
    poly=[(.023,0),(.0135,.017),(-.0135,.017),(-.023,0),(-.0135,-.017),(.0135,-.017)]
    n=6;verts=[]
    for k in (1,.88):
        verts.extend(c+u*x*k+v*z*k for x,z in poly)
    rim=mesh('LensRim',verts,[(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)],M['glow'])
    sol=rim.modifiers.new('ThinFrame','SOLIDIFY');sol.thickness=.0025
    bc.add_bevel(rim,.0008,2);reg(rim,'head','head')
    verts=[c+u*x*.87+v*z*.87-nf*.0005 for x,z in poly]
    reg(mesh('LensGlass',verts,[tuple(range(6))],M['glass']),'head','head')
    box('Earpiece',(.019,.028,.037),(.084,.009,1.579+eye_delta),M['graph'],.005,'head','head',rot=(0,0,-8))
    for label,pts in [('Upper',[(.050,-.095,1.604),(.070,-.055,1.605),(.078,-.012,1.595),(.088,-.002,1.590)]),('Lower',[(.050,-.095,1.580),(.070,-.049,1.567),(.078,-.006,1.563),(.088,-.002,1.568)]),('Forehead',[(.016,-.100,1.609),(-.002,-.095,1.622),(-.023,-.084,1.640),(-.036,-.067,1.650)])]:
        pts=[(x,y,z+eye_delta)for x,y,z in pts]
        if label=='Forehead':
            scalp=BVHTree.FromObject(bpy.data.objects['KES_Head'],bpy.context.evaluated_depsgraph_get())
            fitted=[]
            for x,y,z in pts:
                hit,normal,_,_=scalp.ray_cast(Vector((x,-.25,z)),Vector((0,1,0)),.4)
                fitted.append(tuple(hit+Vector((0,-.002,0)))if hit else(x,y,z))
            pts=fitted
        ribbon('LensStrap'+label,pts,.0033,.0013,M['graph'],'head','head')
    box('EarStatus',(.0025,.009,.006),(.095,.002,1.586+eye_delta),M['glow'],.001,'head','head')


def make_materials():
    desc={
      'jacket':((.035,.037,.045),.73,0),'suit':((.020,.025,.050),.65,0),'pants':((.028,.030,.036),.77,0),
      'jacketLight':((.045,.047,.056),.73,0),'pantsLight':((.038,.040,.049),.77,0),'hairBuzz':((.042,.035,.045),.88,0),
      'bone':((.55,.52,.46),.63,0),'boneLight':((.66,.62,.53),.64,0),'boneShade':((.36,.33,.28),.66,0),'padShadow':((.12,.11,.095),.7,0),
      'graph':((.025,.027,.034),.67,0),'gun':((.095,.105,.112),.48,.55),'web':((.018,.020,.027),.78,0),'webLight':((.027,.030,.038),.78,0),
      'teal':((.00,.45,.39),.68,0),'hair':((.006,.008,.017),.78,0),'hairLight':((.011,.018,.035),.78,0),'hairShade':((.003,.004,.010),.78,0),
      'hairTeal':((.007,.17,.16),.78,0),'hairTealLight':((.009,.27,.24),.78,0),
    }
    for k,(c,r,m) in desc.items():
        M[k]=bc.material('M_KES_'+k,c,r,m)
        p=bc._principled(M[k])
        surface=OUT/'textures'/f'{k}.png'
        if surface.exists():
            nt=M[k].node_tree
            tex=nt.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(surface),check_existing=True)
            nt.links.new(tex.outputs['Color'],p.inputs['Base Color'])
            normal=nt.nodes.new('ShaderNodeTexImage');normal.image=bpy.data.images.load(str(OUT/'textures'/f'{k}_normal.png'),check_existing=True)
            normal.image.colorspace_settings.name='Non-Color'
            bump=nt.nodes.new('ShaderNodeNormalMap');bump.inputs['Strength'].default_value=.5
            nt.links.new(normal.outputs['Color'],bump.inputs['Color']);nt.links.new(bump.outputs['Normal'],p.inputs['Normal'])
            orm=nt.nodes.new('ShaderNodeTexImage');orm.image=bpy.data.images.load(str(OUT/'textures'/f'{k}_orm.png'),check_existing=True)
            orm.image.colorspace_settings.name='Non-Color'
            channels=nt.nodes.new('ShaderNodeSeparateColor');channels.mode='RGB'
            nt.links.new(orm.outputs['Color'],channels.inputs['Color'])
            nt.links.new(channels.outputs['Green'],p.inputs['Roughness']);nt.links.new(channels.outputs['Blue'],p.inputs['Metallic'])
        if 'Specular IOR Level' in p.inputs:
            p.inputs['Specular IOR Level'].default_value=.10 if k.startswith('hair') else (.25 if m==0 else .5)
    M['glow']=bc.material('M_KES_Glow',(.0,.55,.47),.4,emission=(0,.55,.47),emission_strength=.75)
    M['glass']=bc.material('M_KES_EyeGlass',(.006,.22,.18),.21,alpha=.23)
    M['glass'].use_backface_culling=False


def render():
    bc.setup_studio(bg=(.18,.185,.20),strength=.70,floor=True)
    # A vast continuous floor keeps the horizon outside the orthographic frame.
    bpy.data.objects['_Floor'].scale=(4,4,4)
    sc=bpy.context.scene
    try:sc.view_settings.look='AgX - Medium High Contrast'
    except Exception:pass
    objs=BASE['parts']+OWN
    full=bc.render_views(str(OUT/'renders'),'kestrel',objs,views=('front','three_quarter') if QUICK else ('front','three_quarter','right','back'),res=(1000,1100),engine='EEVEE',samples=32,ortho=True,focus=((0,0,.88),.94),margin=1.12)
    bc.contact_sheet(full,str(OUT/'renders'/'contact_sheet.png'),cols=2)
    if not QUICK:
        old_dirs=bc.VIEW_DIRS.copy()
        bc.VIEW_DIRS.update(front=(0,-1,.035),three_quarter=(.60,-1,.07),right=(1,0,.035))
        bc.render_views(str(OUT/'renders'),'face',objs,views=('front','three_quarter','right'),res=(1000,1000),engine='CYCLES',samples=64,ortho=False,focus=((0,-.015,1.585),.20),margin=1.10,lens=85)
        bc.VIEW_DIRS.update(old_dirs)


def consolidate_body():
    """Keep analytic weights: join only body surfaces sharing a PBR family.

    Blender's mesh join preserves vertex-group membership and the active
    armature modifier. No skin modifier is applied and no inverse bind changes.
    Sockets and ability / armor / holster gear stay individual parts.
    """
    groups={}
    skin=BASE['materials']['skin']
    for ob in BASE['parts']:
        if skin in ob.data.materials.values():groups.setdefault((ob['skin_slot'],'skin'),[]).append(ob)
    stems=('UnderSuit','Jacket','Sleeve','Collar','HemRib','SuitZip','Pants','PantOuterSeam','Boot_','BootSole_','BootLace_','GloveCuff','Hair_','HairCap','Belt','ShoulderHarness','RibHarness','KneeStrap')
    for ob in OWN:
        stem=ob.name[4:]
        if stem.startswith(stems):
            key=ob.data.materials[0].name.replace('M_KES_','')
            groups.setdefault((ob['skin_slot'],key),[]).append(ob)
    records=[]
    for (skin_slot,key),obs in groups.items():
        if len(obs)<2:continue
        names=[ob.name for ob in obs]
        body_sources=[ob for ob in obs if ob in BASE['parts']]
        own_sources=[ob for ob in obs if ob in OWN]
        BASE['parts']=[ob for ob in BASE['parts'] if ob not in body_sources]
        OWN[:]=[ob for ob in OWN if ob not in own_sources]
        bpy.ops.object.select_all(action='DESELECT')
        for ob in obs:ob.select_set(True)
        bpy.context.view_layer.objects.active=obs[0]
        bpy.ops.object.join()
        joined=bpy.context.active_object
        joined.name='KES_Part_'+skin_slot+'_'+key
        joined.data.name=joined.name
        joined['joined_source_parts']=json.dumps(names)
        joined['skin_join']='neutral mesh join; group weights preserved; armature modifier not applied'
        joined['skin_slot']=skin_slot
        if body_sources:BASE['parts'].append(joined)
        else:OWN.append(joined)
        records.append({'result':joined.name,'sources':names})
    (OUT/'body_join.json').write_text(json.dumps(records,indent=2))
    bpy.context.view_layer.update()


def pose_qa():
    arm=BASE['armature'];objs=BASE['parts']+OWN;paths=[];checks=[]
    for name in ('sprint','crouch','aim','elbow','knee','fist'):
        arm.location=(0,0,0)
        cv.reset_pose(arm)
        if name in ('elbow','knee'):
            if name=='elbow':cv.bend(arm,'lowerarm_l',(0,-1,0),105)
            else:cv.bend(arm,'calf_l',(0,1,0),110)
        else:cv.pose(arm,name)
        if name in ('sprint','crouch'):
            # Body joins retain the foot groups. Measure the evaluated boot
            # vertices through those groups rather than obsolete part names.
            foot_z=[];dg=bpy.context.evaluated_depsgraph_get()
            for ob in objs:
                fi={g.index for g in ob.vertex_groups if g.name in ('foot_l','foot_r','ball_l','ball_r')}
                if not fi:continue
                ev=ob.evaluated_get(dg);me=ev.to_mesh()
                for vert in ob.data.vertices:
                    if any(g.group in fi and g.weight>.5 for g in vert.groups):
                        foot_z.append((ev.matrix_world@me.vertices[vert.index].co).z)
                ev.to_mesh_clear()
            arm.location.z=-min(foot_z)
            bpy.context.view_layer.update()
        paths+=bc.render_views(str(OUT/'renders'),'qa_'+name,objs,views=('three_quarter',),res=(800,900),engine='EEVEE',samples=24,ortho=True,focus=((0,0,.86),.94),margin=1.16)
        report=cv.report(BASE,objs)
        checks.append({'pose':name,'errors':report['errors'],'max_influences':max(m['max_influences'] for m in report['meshes']),'bad_weight_sums':sum(m['bad_sum'] for m in report['meshes'])})
    bc.contact_sheet(paths,str(OUT/'renders'/'pose_qa_sheet.png'),cols=3)
    (OUT/'pose_qa.json').write_text(json.dumps(checks,indent=2))
    arm.location=(0,0,0);cv.reset_pose(arm)


def main():
    global BASE
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'renders').mkdir(exist_ok=True)
    bc.reset_scene()
    bpy.context.preferences.filepaths.save_version=0
    BASE=cv.build_base(prefix='KES',height=1.70,skin=(.62,.42,.33),eye_color=(.13,.065,.032))
    kestrel_face.make(BASE)
    make_materials();make_clothes();make_gear()
    kestrel_outfit_finish.apply(sys.modules[__name__])
    kestrel_cloth_polish.apply(sys.modules[__name__])
    reference=rain_anatomy.fitting_body(BASE)
    fit=rain_anatomy.fit_garments(OWN,reference,BASE)
    (OUT/'fitting_adjustments.json').write_text(json.dumps(fit,indent=2))
    OWN.extend(kestrel_hair.build(BASE))
    make_lens()
    objs=BASE['parts']+OWN
    bc.uv_all(objs)
    bpy.data.orphans_purge(do_recursive=True)
    skin_parts.tag(objs)
    skin_parts.save_master(OUT/'kestrel_master.blend')
    consolidate_body()
    objs=BASE['parts']+OWN
    tris=bc.stats(objs)
    print('KESTREL_V2_TRIANGLES',tris,flush=True)
    # Save exports before render so failure in a display pass cannot prevent delivery.
    cv.export_character(BASE,str(OUT/'kestrel'),objects=objs + BASE['sockets'])
    skin_parts.manifest(BASE,objs,OUT/'skin_manifest.json')
    render()
    if not QUICK:pose_qa()
    # Open the saved source ready for an artist to inspect the neutral rig.
    for area in bpy.context.screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.shading.type='MATERIAL'
            area.spaces.active.region_3d.view_distance=2.8
            area.spaces.active.region_3d.view_location=(0,0,.91)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'kestrel.blend'),compress=True)
    print('KESTREL_V2_DONE',flush=True)


if __name__=='__main__':main()
