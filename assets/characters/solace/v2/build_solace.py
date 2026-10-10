"""Fresh authored Solace v2: loft cloth, shaped clump hair, compact Bloom technology.

Run: Blender 5.2 -b --factory-startup -P this_file -- [--quick]
No input character mesh is imported. The neutral, shared lean female rig is generated
by character_v2; every garment is constructed from deliberately placed joint loops.
"""
import sys, os, math, json
from pathlib import Path
import bpy, bmesh
from mathutils import Vector, Matrix

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'assets/characters/_shared'))
import blender_common as bc
import character_v2 as cv

TAU = 2*math.pi
S = 1.68/1.70
PARTS = []

def lerp(a,b,t): return a+(b-a)*t
def smooth(t): return max(0,min(1,t))**2*(3-2*max(0,min(1,t)))

def authored_material(name, color, rough=.65, metal=0., paint=False, glow=False):
    m=bc.material('M_SOL_'+name,color,rough,metal,emission=color if glow else None,
                  emission_strength=2.2 if glow else 0)
    if paint:
        # Slow, broad brush/value changes authored into an exportable 128px texture.
        # No noise, pores, scan data, or tiny fabric frequencies.
        n=128; im=bpy.data.images.new('SOL_'+name+'_Paint',width=n,height=n,alpha=True)
        px=[]
        for y in range(n):
            v=y/(n-1)
            for x in range(n):
                u=x/(n-1)
                value=.97+.028*math.sin(TAU*(u*1.4+v*.25))+.018*math.cos(TAU*v*2)
                swath=.024*math.exp(-((u-.38-.10*math.sin(v*TAU))/.10)**2)
                linear=[min(1,max(0,q*(value+swath))) for q in color]
                # The albedo image is sRGB encoded from the linear art palette.
                c=[12.92*q if q<=.0031308 else 1.055*q**(1/2.4)-.055 for q in linear]
                px.extend((*c,1))
        im.pixels=px
        im.filepath_raw=str(HERE/'textures'/('SOL_'+name+'_Paint.png'))
        im.file_format='PNG'; im.save(); im.pack()
        p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        tx=m.node_tree.nodes.new('ShaderNodeTexImage');tx.image=im
        m.node_tree.links.new(tx.outputs['Color'],p.inputs['Base Color'])
    return m

def make_mesh(name,verts,faces,mat,mi=None,uv=None):
    me=bpy.data.meshes.new('SOL_'+name);me.from_pydata(verts,[],faces);me.update()
    ob=bpy.data.objects.new('SOL_'+name,me);bpy.context.scene.collection.objects.link(ob)
    for m in mat if isinstance(mat,list) else [mat]: me.materials.append(m)
    if mi:
        for p,i in zip(me.polygons,mi):p.material_index=i
    for p in me.polygons:p.use_smooth=True
    bm=bmesh.new();bm.from_mesh(me);bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:]);bm.to_mesh(me);bm.free()
    if uv:
        layer=me.uv_layers.new(name='UVMap')
        for p in me.polygons:
            for li in p.loop_indices:layer.data[li].uv=uv[me.loops[li].vertex_index]
    else:bc.smart_uv(ob)
    PARTS.append(ob)
    return ob

def attach(ob,base,region='torso',bone=None):
    # Newly created primitives need evaluated matrices before preserving world transforms.
    bpy.context.view_layer.update()
    if ob not in PARTS:PARTS.append(ob)
    if bone:cv.rigid(ob,base,bone)
    else:cv.bind(ob,base,region)
    return ob

def sphere(name,loc,r,scale,mat,base,bone,seg=24,rings=12):
    ob=bc.sphere('SOL_'+name,r,loc,scale,segments=seg,rings=rings,mat=mat)
    return attach(ob,base,bone=bone)

def box(name,size,loc,mat,base,bone,bevel=.003,rot=(0,0,0)):
    ob=bc.box('SOL_'+name,size,loc,rot,mat=mat,bevel=bevel,segments=2)
    bc.apply_modifiers(ob);return attach(ob,base,bone=bone)

def ring_loft(name,rows,mat,base,region='torso',sides=48,fold=0,cap=False,shear=None):
    # rows z, rx, ry, cy, shape exponent (2 ellipse / >2 rounded planar cloth).
    verts=[];uv=[];faces=[]
    for k,(z,rx,ry,cy,p) in enumerate(rows):
        for j in range(sides):
            a=TAU*j/sides;c=math.cos(a);ss=math.sin(a)
            r=1+fold*math.sin(5*a+z*16)*math.sin(math.pi*k/(len(rows)-1))
            x=rx*math.copysign(abs(ss)**(2/p),ss)*r
            y=cy-ry*math.copysign(abs(c)**(2/p),c)*r
            zz=z+(shear(a,k,len(rows)) if shear else 0)
            verts.append((x,y,zz));uv.append((j/sides,k/(len(rows)-1)))
    for i in range(len(rows)-1):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides
            faces.append((a,b,b+sides,a+sides))
    if cap:faces.extend([tuple(range(sides-1,-1,-1)),tuple((len(rows)-1)*sides+j for j in range(sides))])
    ob=make_mesh(name,verts,faces,mat,uv=uv);return attach(ob,base,region)

def resample(points,n=32):
    pts=[Vector(p) for p in points];out=[]
    for i in range(n):
        q=i*(len(pts)-1)/(n-1);k=min(int(q),len(pts)-2);t=q-k
        p0=pts[max(0,k-1)];p1=pts[k];p2=pts[k+1];p3=pts[min(len(pts)-1,k+2)]
        out.append(.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t))
    return out

def sweep(name,points,radii,mat,base,region='torso',bone=None,n=32,sides=20,up=(0,-1,0),cap=True,fold=0,accent_end=False,cloth_paint=False):
    pp=resample(points,n);verts=[];uv=[];faces=[];indices=[]
    rr=[(r,r) if isinstance(r,(int,float)) else r for r in radii]
    for i,p in enumerate(pp):
        t=(pp[min(i+1,n-1)]-pp[max(i-1,0)]).normalized()
        u=Vector(up);u=(u-t*u.dot(t)).normalized();v=t.cross(u).normalized()
        q=i*(len(rr)-1)/(n-1);k=min(int(q),len(rr)-2);f=q-k
        rx=lerp(rr[k][0],rr[k+1][0],f);ry=lerp(rr[k][1],rr[k+1][1],f)
        for j in range(sides):
            a=TAU*j/sides
            progress=i/(n-1)
            dr=1+fold*(.65*math.sin(progress*math.pi*6+a*2)+.35*math.sin(progress*math.pi*10-a))*math.sin(math.pi*progress)
            if cloth_paint:
                # Four local, slanted asymmetric cloth creases, 3-6mm deep.
                front=.25+.75*((1+math.cos(a))*.5)**2
                centers=(.61+.040*math.sin(a+.6),.68+.030*math.sin(a+.6),
                         .90+.030*math.sin(a-.5),.95+.010*math.sin(a+.5))
                crease=(.0055*math.exp(-((progress-centers[0])/.027)**2)
                        -.0035*math.exp(-((progress-centers[1])/.020)**2)
                        +.0060*math.exp(-((progress-centers[2])/.024)**2)
                        -.0030*math.exp(-((progress-centers[3])/.022)**2))*front
                dr+=crease/max((rx+ry)*.5,.001)
            verts.append(tuple(p+u*(rx*math.cos(a)*dr)+v*(ry*math.sin(a)*dr)))
            uv.append((j/sides,i/(n-1)))
    for i in range(n-1):
        for j in range(sides):
            a=i*sides+j;b=i*sides+(j+1)%sides
            faces.append((a,a+sides,b+sides,b))
            shade=0
            indices.append(1 if accent_end and i>n-4 else shade)
    if cap:
        faces.extend([tuple(range(sides-1,-1,-1)),tuple((n-1)*sides+j for j in range(sides))]);indices.extend([0,0])
    ob=make_mesh(name,verts,faces,mat,mi=indices,uv=uv)
    if cloth_paint:
        attr=ob.data.color_attributes.new('SOL_ClothPaint','FLOAT_COLOR','POINT')
        colors=[]
        for i in range(n):
            u=i/(n-1)
            for j in range(sides):
                ang=TAU*j/sides
                front=((1+math.cos(ang))*.5)**2
                # Soft elongated paint planes with only 2-3% value variation.
                value=(1-.026*math.exp(-((u-(.62+.07*math.sin(ang+.4)))/.065)**2)*front
                       +.020*math.exp(-((u-(.83+.04*math.sin(ang)))/.095)**2)*front
                       -.022*math.exp(-((u-(.95+.035*math.sin(ang-.5)))/.045)**2)*front)
                colors.extend((.44*value,.37*value,.27*value,1))
        attr.data.foreach_set('color',colors);ob.data.color_attributes.active_color=attr
    return attach(ob,base,region,bone)

def ribbon(name,points,width,mat,base,region='torso',bone=None,normal=(0,-1,0),n=32):
    pts=resample(points,n);verts=[];faces=[];uv=[]
    for i,p in enumerate(pts):
        t=(pts[min(i+1,n-1)]-pts[max(i-1,0)]).normalized()
        nn=Vector(normal);nn=(nn-t*nn.dot(t)).normalized();w=t.cross(nn).normalized()
        for sign in [-1,1]:verts.append(tuple(p+w*width*.5*sign));uv.append(((sign+1)*.5,i/(n-1)))
    for i in range(n-1):faces.append((2*i,2*i+1,2*i+3,2*i+2))
    ob=make_mesh(name,verts,faces,mat,uv=uv)
    so=ob.modifiers.new('Cloth return','SOLIDIFY');so.thickness=.003;so.offset=0
    bc.apply_modifiers(ob)
    return attach(ob,base,region,bone)

def interp_rows(keys,n):
    out=[]
    for i in range(n):
        q=i*(len(keys)-1)/(n-1);k=min(int(q),len(keys)-2);f=q-k
        out.append(tuple(lerp(a,b,f) for a,b in zip(keys[k],keys[k+1])))
    return out

def scalp_clump(name,points,width,thick,mat,base):
    """A lenticular lock lying flush on the sculpted scalp, with a free tapered tip."""
    center=Vector((0,.004,1.574));radii=Vector((.084,.105,.123))
    ps=resample(points,24);vv=[];uv=[];ff=[];sides=10
    for i,p in enumerate(ps):
        u=i/(len(ps)-1)
        if p.z>1.527:
            d=p-center;k=math.sqrt(sum((d[a]/radii[a])**2 for a in range(3)))
            p=center+d*(1.045/max(k,1e-6))
        t=(ps[min(i+1,len(ps)-1)]-ps[max(0,i-1)]).normalized()
        radial=Vector(((p.x-center.x)/radii.x**2,(p.y-center.y)/radii.y**2,(p.z-center.z)/radii.z**2)).normalized()
        normal=(radial-t*radial.dot(t)).normalized();wide=t.cross(normal).normalized()
        taper=1-.82*smooth((u-.68)/.32)
        for j in range(sides):
            a=TAU*j/sides
            vv.append(tuple(p+normal*(thick*.50*math.cos(a)*taper)+wide*(width*.5*math.sin(a)*taper)))
            uv.append((j/sides,u))
    for i in range(len(ps)-1):
        for j in range(sides):a=i*sides+j;b=i*sides+(j+1)%sides;ff.append((a,b,b+sides,a+sides))
    ff.extend([tuple(range(sides-1,-1,-1)),tuple((len(ps)-1)*sides+j for j in range(sides))])
    ob=make_mesh(name,vv,ff,mat,uv=uv);attach(ob,base,bone='head');return ob

def build_clothing(base,m):
    # Drape bridges the bust: a single front plane with no underbust tuck.
    keys=[(.900,.175,.105,.012,2.25),(.950,.147,.105,.007,2.18),(.995,.120,.100,.004,2.10),
          (1.06,.133,.102,.004,2.12),(1.14,.149,.108,.005,2.12),(1.22,.157,.113,.002,2.08),
          (1.30,.157,.103,.003,2.05),(1.375,.162,.093,.016,2),(1.402,.129,.078,.017,2),
          (1.426,.059,.060,.020,2)]
    jacket=ring_loft('Jacket',interp_rows(keys,24),m['ivory'],base,sides=40,fold=.010)
    jacket['construction']='Authored draped cloth; front ends at .900m; shared torso joint skinning'
    # Shallow tailored seams are cloth-coloured, bevelled strips with broad value difference.
    def front_y(x,z):
        for i in range(len(keys)-1):
            if z<=keys[i+1][0]:
                row=tuple(lerp(a,b,(z-keys[i][0])/(keys[i+1][0]-keys[i][0])) for a,b in zip(keys[i],keys[i+1]))
                _,rx,ry,cy,p=row
                return cy-ry*max(0,1-(abs(x)/rx)**p)**(1/p)-.0045
        return -.074
    for sign in [-1,1]:
        zz=[.913,1.00,1.115,1.28];xx=[.10,.081,.10,.12]
        ribbon('JacketDart_'+str(sign),[(sign*x,front_y(x,z)-.001,z) for x,z in zip(xx,zz)],.0017,m['seam'],base,n=24)
    wrap=[(-.065,-.052,1.434),(-.048,-.077,1.401),(.010,-.111,1.355),(.072,-.116,1.307),(.086,-.111,1.265),(.063,-.110,1.15),(.048,-.106,1.045),(.071,-.106,.952),(.090,-.106,.900)]
    wrap=[(x,front_y(x,z)-(.012 if z>1.05 else .003) if z<1.40 else y-.008,z) for x,y,z in wrap]
    # A genuine overlapping panel with a fixed outer edge, rather than a stripe.
    # Its edge sits behind the piping; the broad centre rises into a draped fold.
    pp=resample(wrap,40);vv=[];ff=[];uv=[]
    for i,p in enumerate(pp):
        for k in range(3):
            x=p.x-.032*k;z=p.z
            offset=.009 if z>1.05 else .0015
            y=front_y(x,z)-offset-.004*math.sin(math.pi*k/2)
            vv.append((x,y,z));uv.append((k/2,i/39))
    for i in range(39):
        for k in range(2):a=i*3+k;ff.append((a,a+1,a+4,a+3))
    flap=make_mesh('WrapOverlap',vv,ff,m['ivory'],uv=uv)
    so=flap.modifiers.new('Wrap hem return','SOLIDIFY');so.thickness=.003;so.offset=-1;bc.apply_modifiers(flap);attach(flap,base)
    ribbon('WrapCoralPiping',wrap,.007,m['coral'],base,n=48)
    # Jacket front hem is visibly short. Back/side coat-tail is a curved cut, never an apron.
    hemkeys=[(0,.900),(35,.900),(60,.840),(90,.760),(120,.700),(150,.660),(172,.645),(180,.645)]
    def hem(angle):
        aa=abs(((angle+180)%360)-180)
        for k in range(len(hemkeys)-1):
            a,z=hemkeys[k];b,w=hemkeys[k+1]
            if aa<=b:return lerp(z,w,(aa-a)/(b-a))
        return .645
    # Two continuous panels, from side/front cutaway to a widening centre-back split.
    for side in [-1,1]:
        verts=[];faces=[];uv=[];rows=12;cols=20
        for i in range(rows):
            u=i/(rows-1)
            for j in range(cols):
                a=math.radians(side*lerp(35,180-8*u,j/(cols-1)))
                z=lerp(.900,hem(math.degrees(a)),u)
                rx=lerp(.176,.208,u);ry=lerp(.105,.121,u);cy=lerp(.012,.026,u)
                ss=math.sin(a);c=math.cos(a);w=1+.012*math.sin(j/cols*math.pi*5)*math.sin(math.pi*u)
                verts.append((rx*math.copysign(abs(ss)**(2/2.3),ss)*w,cy-ry*math.copysign(abs(c)**(2/2.3),c)*w,z))
                uv.append((j/(cols-1),u))
        for i in range(rows-1):
            for j in range(cols-1):a=i*cols+j;faces.append((a,a+1,a+cols+1,a+cols))
        ob=make_mesh('Tail_'+('L' if side>0 else 'R'),verts,faces,[m['ivory'],m['coral']],uv=uv)
        for p in ob.data.polygons:
            js=[v%cols for v in p.vertices];rs=[v//cols for v in p.vertices]
            p.material_index=int(max(rs)>=rows-2 or min(js)==0 or max(js)==cols-1)
        so=ob.modifiers.new('Hem return','SOLIDIFY');so.thickness=.004;so.offset=-1;bc.apply_modifiers(ob)
        attach(ob,base,'coat');ob['hem']='Hip front .900 -> mid-thigh split back .645m'
    ring_loft('FrontHem',[(.900,.176,.106,.012,2.25),(.908,.173,.106,.011,2.25)],m['coral'],base,sides=64)
    # Neck layers: wrap collar is rounded and leans away from the jaw.
    ring_loft('MockNeck',[(1.395,.052,.055,.018,2),(1.430,.051,.054,.018,2),(1.454,.048,.051,.020,2)],m['charcoal'],base,sides=40)
    rows=[(1.414,.091,.085,.015,2),(1.432,.080,.079,.016,2),(1.439,.079,.080,.018,2),(1.443,.085,.086,.018,2)]
    col=ring_loft('SoftWrapCollar',interp_rows(rows,8),[m['ivory'],m['coral']],base,sides=32,shear=lambda a,k,n:.043*(1-math.cos(a))*.5)
    for p in col.data.polygons:p.material_index=int(max(col.data.vertices[v].co.z for v in p.vertices)>1.480)
    so=col.modifiers.new('Soft rolled collar','SOLIDIFY');so.thickness=.007;so.offset=0;bc.apply_modifiers(col)
    attach(col,base,bone='neck_01')
    # An extra scarf fold crossing in front provides the asymmetric cloth overlap.
    ribbon('CollarFrontFold',[(-.08,-.050,1.459),(-.055,-.069,1.434),(-.005,-.076,1.423),(.054,-.064,1.447),(.080,-.044,1.466)],.022,m['ivory'],base,n=40)
    ribbon('CollarFrontCoral',[(-.080,-.052,1.450),(-.054,-.070,1.425),(-.005,-.079,1.414),(.054,-.066,1.438),(.080,-.046,1.457)],.004,m['coral'],base,n=40)
    # Limbs are continuous multi-loop lofts centred on the actual shared rig.
    J=base['joints']
    for side,sgn in [('l',1),('r',-1)]:
        sh=J['upperarm_'+side];el=J['lowerarm_'+side];wr=J['hand_'+side]
        f=(wr-el).normalized();end=wr-f*.082
        points=[sh-Vector((sgn*.040,0,-.015)),sh,(sh+el)*.5,el,el+f*.07,end]
        sweep('Sleeve_'+side,points,[(.066,.065),(.061,.061),(.052,.048),(.046,.042),(.042,.037),(.038,.036)],
              [m['ivory'],m['coral']],base,'arm_'+side,n=26,sides=22,fold=.15,accent_end=True)
        sweep('Gauntlet_'+side,[wr-f*.105,wr-f*.06,wr+f*.01],[.039,.033,.028],m['glove'],base,'arm_'+side,n=10,sides=20)
        # Skin generated for the bare hand is recoloured into a thin full-finger glove.
        for ob in base['parts']:
            if ('Hand_'+side.upper() in ob.name or 'Forearm_'+side.upper() in ob.name or
                ('Hand' in ob.name and ob.name.lower().endswith('_'+side))):
                ob.data.materials.clear();ob.data.materials.append(m['glove'])
        # utility pants follow hip/knee/ankle, with generous cloth volumes at bends.
        hip=J['thigh_'+side];kn=J['calf_'+side];ank=J['foot_'+side]
        p=[Vector((hip.x,hip.y,.913)),hip,lerp(hip,kn,.22),lerp(hip,kn,.50),lerp(hip,kn,.76),kn,
           lerp(kn,ank,.22),lerp(kn,ank,.52),Vector((ank.x,ank.y,.165))]
        rr=[(.086,.084),(.082,.077),(.078,.079),(.074,.074),(.068,.068),(.069,.065),(.065,.064),(.060,.056),(.051,.047)]
        sweep('Pants_'+side,p,rr,m['pantspaint'],base,'leg_'+side,n=28,sides=24,fold=.016,cloth_paint=True)
        ribbon('PantsSideSeam_'+side,[(hip.x+sgn*.080,.006,.84),(kn.x+sgn*.066,.007,.49),(ank.x+sgn*.049,.013,.19)],.003,m['sandshade'],base,'leg_'+side,normal=(sgn,0,0),n=32)
        # Slim knee cap floats a few mm off a charcoal fabric strap.
        sweep('KneeStrap_'+side,[kn+Vector((0,0,.017)),kn-Vector((0,0,.017))],[.071,.071],m['charcoal'],base,'leg_'+side,n=3,sides=32)
        cx=kn.x;cy=-.083;cz=kn.z+.008
        outline=[(-.031,.052),(.031,.052),(.043,.028),(.040,-.033),(.022,-.055),(-.022,-.055),(-.040,-.033),(-.043,.028)]
        vv=[]
        for depth in [0,.014]:
            vv.extend((cx+x,cy-depth+4.5*x*x,cz+z) for x,z in outline)
        ff=[tuple(range(7,-1,-1)),tuple(range(8,16))]+[(j,(j+1)%8,(j+1)%8+8,j+8) for j in range(8)]
        kp=make_mesh('KneePad_'+side,vv,ff,m['hard']);bc.add_bevel(kp,.004,3);bc.apply_modifiers(kp);attach(kp,base,bone='calf_'+side)
        # Inset broad bone plane with generous chamfer, like the painted weapon furniture.
        inset=[(-.021,.034),(.021,.034),(.029,.016),(.025,-.023),(.013,-.035),(-.013,-.035),(-.025,-.023),(-.029,.016)]
        vv=[]
        for depth in [.016,.020]:vv.extend((cx+x,cy-depth+4.5*x*x,cz+z) for x,z in inset)
        ins=make_mesh('KneeInset_'+side,vv,ff,m['hardshade']);bc.add_bevel(ins,.0015,2);bc.apply_modifiers(ins);attach(ins,base,bone='calf_'+side)
        # Boot is a shaped last with flat ground sole and padded shaft, no primitive boxes.
        rows=[(.020,.049,.122,-.036,2.5),(.036,.050,.118,-.035,2.4),(.057,.047,.095,-.024,2.3),
              (.083,.043,.070,-.007,2.2),(.115,.041,.049,.006,2.1),(.158,.044,.048,.009,2.1),(.165,.046,.048,.009,2)]
        boot=ring_loft('Boot_'+side,interp_rows(rows,12),m['boot'],base,'leg_'+side,sides=28,cap=True)
        for v in boot.data.vertices:v.co.x+=ank.x
        sole=ring_loft('BootSole_'+side,[(0,.050,.124,-.036,2.5),(.010,.052,.125,-.036,2.5),(.021,.051,.123,-.036,2.5)],m['graphite'],base,'leg_'+side,sides=40,cap=True)
        for v in sole.data.vertices:v.co.x+=ank.x
        box('BootHeelTab_'+side,(.012,.006,.023),(ank.x,.060,.154),m['coral'],base,'foot_'+side,.002)
    ring_loft('PantsPelvis',[(.846,.154,.087,.010,2.25),(.88,.174,.099,.010,2.25),(.914,.166,.091,.008,2.2)],m['sand'],base,'pelvis',sides=40)
    ring_loft('Belt',[(.972,.137,.110,.002,2.1),(.988,.135,.110,.002,2.1),(1.005,.134,.108,.002,2.1)],m['charcoal'],base,sides=56)
    box('BeltBuckle',(.040,.010,.030),(0,-.113,.988),m['gunmetal'],base,'pelvis')
    box('MedicPouch',(.058,.035,.074),(-.115,-.112,.944),m['sand'],base,'pelvis',.006,rot=(5,0,-25))
    box('PouchFlap',(.060,.009,.025),(-.115,-.136,.966),m['sandshade'],base,'pelvis',.004,rot=(5,0,-25))
    box('PouchCoralPull',(.010,.005,.015),(-.115,-.142,.955),m['coral'],base,'pelvis',.002)

def build_hair(base,m):
    # Sculpted cap follows the actual authored head, excludes face and visible ear lobes.
    vv=[];ff=[];uv=[];nr=13;ns=32
    for i in range(nr):
        t=i/(nr-1)
        for j in range(ns):
            a=TAU*j/ns
            # front hairline high, side/nape lower; part is deliberately asymmetric.
            phi_end=lerp(1.18,2.23,(1-math.cos(a))*.5)
            ph=.035+t*phi_end
            vv.append((.084*math.sin(ph)*math.sin(a),.004-.105*math.sin(ph)*math.cos(a),1.575+.123*math.cos(ph)))
            uv.append((j/ns,t))
    for i in range(nr-1):
        for j in range(ns):a=i*ns+j;b=i*ns+(j+1)%ns;ff.append((a,b,b+ns,a+ns))
    ob=make_mesh('HairCap',vv,ff,m['hair'],uv=uv);attach(ob,base,bone='head')
    # Wide, flattened directional clumps. The visible ridges are authored geometry.
    guides=[
      ([(-.035,-.078,1.650),(.005,-.092,1.674),(.050,-.082,1.653),(.085,-.040,1.618),(.090,.015,1.596),(.068,.072,1.552),(.015,.100,1.540),(-.040,.101,1.535)],(.040,.014)),
      ([(.040,-.082,1.645),(.072,-.066,1.612),(.088,-.040,1.572),(.093,-.028,1.535),(.087,-.030,1.500),(.091,-.022,1.468)],(.017,.006)),
      ([(-.040,-.080,1.645),(-.068,-.070,1.615),(-.085,-.046,1.576),(-.089,-.033,1.538),(-.084,-.030,1.505)],(.014,.006)),
      ([(-.042,-.070,1.662),(-.076,-.045,1.642),(-.091,.005,1.600),(-.083,.055,1.560),(-.058,.092,1.540)],(.033,.011)),
      ([(.020,-.020,1.702),(.056,.040,1.682),(.071,.085,1.612),(.040,.106,1.560),(-.030,.104,1.538)],(.034,.011)),
      ([(-.015,-.030,1.704),(-.005,.050,1.697),(0,.106,1.632),(-.015,.111,1.575),(-.042,.104,1.540)],(.034,.011)),
      ([(-.035,-.040,1.692),(-.060,.030,1.677),(-.075,.080,1.612),(-.066,.100,1.560),(-.052,.101,1.540)],(.031,.011)),
      ([(-.036,-.062,1.684),(0,-.052,1.706),(.045,-.022,1.702),(.076,.020,1.662)],(.037,.014)),
      ([(.058,.062,1.545),(.030,.088,1.530),(-.030,.097,1.532)],(.023,.009)),
      ([(-.070,.058,1.545),(-.054,.092,1.534)],(.020,.009))]
    for i,(pts,rad) in enumerate(guides):
        pts=[(x,y-.016,z) for x,y,z in pts]
        # Lens thickness normal points approximately along front/back while broad face follows scalp.
        scalp_clump('HairClump_%02d'%i,pts,rad[0]*1.7,rad[1]*.95,m['hair'] if i%3 else m['hairlight'],base)
    bundle=[(-.05,.084,1.535),(-.104,.060,1.518),(-.133,.007,1.470),(-.129,-.082,1.408),(-.112,-.119,1.34),(-.104,-.143,1.27),(-.102,-.146,1.21),(-.110,-.134,1.16)]
    r=[.022,.027,.029,.030,.029,.024,.017,.002]
    for i in range(3):
        pp=[];rr=[]
        for k,p in enumerate(bundle):
            q=k/(len(bundle)-1);phase=i*TAU/3+q*math.pi
            pp.append((p[0]+.008*math.cos(phase)+.006*math.sin(q*math.pi*3.5),p[1]+.008*math.sin(phase)+.004*math.sin(q*math.pi*3),p[2]))
            rr.append((r[k]*.73,r[k]*.85))
        ob=sweep('Ponytail_%d'%i,pp,rr,m['hairlight'] if i==1 else m['hair'],base,bone='head',n=28,sides=10,up=(0,-1,0))
        ob['direction']='Low ponytail draped over her RIGHT (-X) shoulder'
    sweep('PonytailWisp',[bundle[-3],(-.125,-.151,1.198),(-.132,-.142,1.166),(-.119,-.123,1.157)],[.008,.007,.004,.001],m['hair'],base,bone='head',n=24,sides=12)
    sweep('CoralHairTie',[(-.066,.080,1.537),(-.089,.072,1.527)],[.025,.024],m['coral'],base,bone='head',n=3,sides=24,up=(0,0,1))
    for sign in [-1,1]:sphere('CoralStud_'+str(sign),(sign*.079,.004,1.528),.0037,(.60,1,1),m['coral'],base,'head',12,6)

def build_bloom(base,m):
    box('BloomMount',(.085,.015,.322),(0,.119,1.252),m['graphite'],base,'spine_03',.016)
    for i in range(7):box('BloomSpine_%d'%i,(.040,.025,.032),(0,.143,1.09+.051*i),m['graphite'],base,'spine_03',.006)
    for s in [-1,1]:
        sweep('BloomYoke_'+str(s),[(0,.142,1.401),(s*.052,.132,1.407),(s*.108,.080,1.413)],[(.011,.009)]*3,m['graphite'],base,bone='spine_03',n=20,sides=12)
        box('BloomClamp_'+str(s),(.035,.040,.017),(s*.110,.080,1.412),m['graphite'],base,'spine_03',.004,rot=(-25,0,0))
        sphere('BloomLED_'+str(s),(s*.110,.102,1.420),.0038,(1,1,1),m['glow'],base,'spine_03',12,6)
        ribbon('Harness_'+str(s),[(s*.110,.082,1.420),(s*.115,.020,1.440),(s*.115,-.030,1.410),(s*.111,-.058,1.362)],.024,m['charcoal'],base,bone='spine_03',normal=(0,0,1),n=24)
        box('HarnessClip_'+str(s),(.025,.011,.026),(s*.111,-.063,1.357),m['gunmetal'],base,'spine_03',.003)
    budkeys=[(1.15,.016),(1.19,.048),(1.25,.074),(1.32,.082),(1.40,.070),(1.47,.049),(1.53,.024),(1.565,.0005)]
    def rad(z):
        for i in range(len(budkeys)-1):
            a,r=budkeys[i];b,q=budkeys[i+1]
            if z<=b:return lerp(r,q,smooth((z-a)/(b-a)))
        return .0005
    keys=[('C',58.5,121.5,1.497,None),('L',-66,48.5,1.466,(.122,.150)),('R',131.5,246,1.466,(-.122,.150))]
    for key,a0,a1,zt,tip in keys:
        vv=[];ff=[];uv=[];nr=22;nc=11
        for i in range(nr):
            u=i/(nr-1);z=lerp(1.15,zt,u);zr=lerp(1.15,1.565,u);r=rad(zr);cy=lerp(.180,.188,u)
            w=smooth((u-.39)/.61)**1.4 if tip else 0
            ox=tip[0]*w if tip else 0;oy=(tip[1]-.199)*w if tip else 0
            for j in range(nc):
                v=j/(nc-1);a=math.radians(lerp(a0,a1,v));puff=1+.08*math.sin(math.pi*v)
                vv.append((r*math.cos(a)*puff+ox,cy+r*.62*math.sin(a)*puff+oy,z));uv.append((v,u))
        for i in range(nr-1):
            for j in range(nc-1):a=i*nc+j;ff.append((a,a+nc,a+nc+1,a+1))
        ob=make_mesh('BloomVane_'+key,vv,ff,[m['hard'],m['coral']],uv=uv)
        for p in ob.data.polygons:p.material_index=int(min(v%nc for v in p.vertices)<2 or max(v%nc for v in p.vertices)>=nc-2)
        so=ob.modifiers.new('Petal shell rim','SOLIDIFY');so.thickness=.006;so.offset=-1;so.material_offset_rim=1;bc.apply_modifiers(ob)
        pivot=Vector((0 if key=='C' else (.015 if key=='L' else -.015),.172 if key=='C' else .167,1.150))
        ob.data.transform(Matrix.Translation(-pivot));ob.location=pivot
        attach(ob,base,bone='spine_03');ob['open_angle_deg']=30;ob['closed_angle_deg']=0
        ob['hinge_axis']= 'X' if key=='C' else 'Y';ob['ability']='Bloom regen; three folded vanes, never wings'
        cv.socket('SOL_PIVOT_Vane_'+key,base,'spine_03',pivot)
    core=ring_loft('BloomCore',[(z,r*.78,r*.78*.62,.185,2) for z,r in budkeys[:-2]],m['glow'],base,sides=32,cap=True)
    # override generic torso skin on the technological rigid core.
    core.vertex_groups.clear();cv.rigid(core,base,'spine_03')
    sphere('BloomHub',(0,.184,1.147),.028,(1,.78,.70),m['graphite'],base,'spine_03',24,10)
    sweep('BloomHubRing',[(0,.184,1.155),(0,.184,1.160)],[.027,.027],m['glow'],base,bone='spine_03',n=2,sides=32,up=(0,1,0),cap=False)

def orient_cylinder(name,center,axis,r,depth,mat,base,bone,verts=24):
    ob=bc.cylinder('SOL_'+name,r,depth,center,verts=verts,mat=mat,bevel=.001,segments=1)
    ob.rotation_euler=Vector(axis).to_track_quat('Z','Y').to_euler();bc.apply_modifiers(ob)
    return attach(ob,base,bone=bone)

def build_tech(base,m):
    J=base['joints'];wr=J['hand_r'];f=(wr-J['lowerarm_r']).normalized()
    mount=Vector((-.581,-.373,.724));mount=(mount-f*mount.dot(f)).normalized();b=f.cross(mount).normalized()
    def local(q):return wr+f*q[0]+b*q[1]+mount*q[2]
    # Housing side rails leave a clean exposed channel for the cylindrical luminous vial.
    for sign in [-1,1]:
        ob=bc.box('SOL_InjectorRail_'+str(sign),(.086,.008,.017),mat=m['hard'],bevel=.004,segments=2)
        ob.matrix_world=Matrix.Translation(local((-.046,sign*.014,.043)))@Matrix((f,b,mount)).transposed().to_4x4()
        bc.apply_modifiers(ob);attach(ob,base,bone='lowerarm_r')
    sweep('InjectorBand',[wr-f*.090,wr-f*.018],[.040,.033],m['graphite'],base,bone='lowerarm_r',n=8,sides=28)
    orient_cylinder('InjectorVial',local((-.047,0,.047)),f,.0085,.058,m['glow'],base,'lowerarm_r')
    for x in [-.079,-.015]:orient_cylinder('VialCap_'+str(x),local((x,0,.047)),f,.010,.006,m['gunmetal'],base,'lowerarm_r')
    orient_cylinder('InjectorNozzle',local((.006,0,.043)),f,.008,.025,m['gunmetal'],base,'lowerarm_r')
    orient_cylinder('InjectorBore',local((.019,0,.043)),f,.003,.001,m['graphite'],base,'lowerarm_r',16)
    c=Vector((.210,-.049,.937));e=Vector((.707,-.707,0))
    sphere('HealDroneShell',c,.043,(1,1,.94),m['hard'],base,'pelvis',28,14)
    # Horizontal equator band has a broad dark read from the front.
    ring=ring_loft('DroneBand',[(c.z-.007,.045,.045,c.y,2),(c.z+.007,.045,.045,c.y,2)],m['graphite'],base,'pelvis',sides=40)
    for v in ring.data.vertices:v.co.x+=c.x
    orient_cylinder('DroneEyeBezel',c+e*.039,e,.018,.010,m['graphite'],base,'pelvis',32)
    orient_cylinder('DroneEyeCoral',c+e*.044,e,.012,.002,m['glow'],base,'pelvis',32)
    orient_cylinder('DroneVent',c+Vector((0,0,-.040)),(0,0,-1),.014,.003,m['glow'],base,'pelvis')
    orient_cylinder('DroneAntenna',c+Vector((0,.005,.050)),(0,.25,1),.0023,.020,m['graphite'],base,'pelvis',12)
    sphere('DroneDock',(.177,-.037,.937),.043,(.35,1,1),m['graphite'],base,'pelvis',24,12)
    ribbon('DroneDockTab',[(.135,-.033,.990),(.178,-.035,.972)],.017,m['graphite'],base,bone='pelvis',normal=(0,-1,0),n=10)
    # Original three almond petals, oriented on the left upper-arm sleeve.
    sh=J['upperarm_l'];el=J['lowerarm_l'];p=lerp(sh,el,.32)+Vector((.008,-.053,.022))
    normal=Vector((.473,-.708,.526)).normalized();up=(sh-el).normalized();up=(up-normal*up.dot(normal)).normalized();right=up.cross(normal).normalized()
    outline=[(math.sin(TAU*i/6)*.029,math.cos(TAU*i/6)*.029) for i in range(6)]
    vv=[tuple(p+right*x+up*z+normal*d) for d in [0,.003] for x,z in outline]
    ff=[tuple(range(5,-1,-1)),tuple(range(6,12))]+[(i,(i+1)%6,(i+1)%6+6,i+6) for i in range(6)]
    ob=make_mesh('BloomEmblemPatch',vv,ff,m['sand']);bc.add_bevel(ob,.002,2);bc.apply_modifiers(ob);attach(ob,base,bone='upperarm_l')
    for pet,angle,length,width in [(0,0,.027,.011),(1,42,.023,.009),(2,-42,.023,.009)]:
        ang=math.radians(angle);u=up*math.cos(ang)+right*math.sin(ang);v=right*math.cos(ang)-up*math.sin(ang)
        origin=p-up*.013+normal*.0045;vv=[]
        for sign in [-1,1]:
            for i in range(13):
                t=i/12 if sign<0 else 1-i/12
                vv.append(tuple(origin+u*(length*t)+v*(sign*width*.5*math.sin(math.pi*t))))
        ob=make_mesh('BloomEmblemPetal_%d'%pet,vv,[tuple(range(len(vv)))],m['coral']);so=ob.modifiers.new('Petal relief','SOLIDIFY');so.thickness=.0015;bc.apply_modifiers(ob);attach(ob,base,bone='upperarm_l')
    for nm,loc,bone in [('Bloom',(0,.185,1.330),'spine_03'),('Drone',c,'pelvis'),('Injector',local((.019,0,.043)),'lowerarm_r')]:
        en=bpy.data.objects.get('SOL_SOCKET_'+nm)
        if en:bpy.data.objects.remove(en,do_unlink=True)
        cv.socket('SOL_SOCKET_'+nm,base,bone,loc,yaxis=-f if nm=='Injector' else (0,1,0),zhint=mount if nm=='Injector' else (0,0,1))
    for sd,label in [('l','L'),('r','R')]:
        source=bpy.data.objects.get('SOL_SOCKET_Weapon'+label)
        if source:
            en=source.copy();en.name='SOL_SOCKET_Hand_'+label;bpy.context.scene.collection.objects.link(en)

def qa_report(base):
    objs=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.name.startswith('SOL_')]
    dg=bpy.context.evaluated_depsgraph_get();tris=0;bad=[];maxweights=0
    for o in objs:
        me=o.evaluated_get(dg).to_mesh();me.calc_loop_triangles();tris+=len(me.loop_triangles)
        if not o.data.uv_layers:bc.smart_uv(o)
        for v in o.data.vertices:
            ww=[q.weight for q in v.groups if q.weight>.00001];maxweights=max(maxweights,len(ww))
            if len(ww)>4 or abs(sum(ww)-1)>.001:bad.append([o.name,v.index,len(ww),sum(ww)])
        o.evaluated_get(dg).to_mesh_clear()
    missingmods=[o.name for o in objs if not any(m.type=='ARMATURE' and m.object==base['armature'] for m in o.modifiers)]
    report={'triangles':tris,'mesh_objects':len(objs),'max_vertex_influences':maxweights,'bad_weight_vertices':len(bad),'missing_armature_modifiers':missingmods,
            'bad_weight_examples':bad[:8],'skull_height_m':1.68,'rest_pose':'shared 45-degree A-pose; front -Y; feet Z0',
            'source':'Fresh authored geometry; no TRELLIS or existing character mesh imported',
            'emissive_materials':[m.name for m in bpy.data.materials if m.use_nodes and any(n.type=='BSDF_PRINCIPLED' and n.inputs.get('Emission Strength') and n.inputs['Emission Strength'].default_value>0 for n in m.node_tree.nodes)]}
    (HERE/'validation.json').write_text(json.dumps(report,indent=2))
    print('SOLACE_V2_QA',json.dumps(report));return objs,report

def compact_skinned_parts(base):
    """Join authored rest meshes while retaining all named bone vertex groups."""
    def combine(name,prefixes,exclude=()):
        obs=[o for o in bpy.context.scene.objects if o.type=='MESH' and
             any(o.name.startswith('SOL_'+p) for p in prefixes) and
             not any(o.name.startswith('SOL_'+p) for p in exclude)]
        if not obs:return
        bpy.ops.object.select_all(action='DESELECT')
        for o in obs:o.select_set(True)
        # Every member carries the exact same armature modifier. Blender joins
        # data and bone groups, preserving the active armature modifier.
        bpy.context.view_layer.objects.active=obs[0]
        bpy.ops.object.join();ob=bpy.context.object;ob.name='SOL_'+name;ob.data.name=ob.name
        ob['topology']='Authored joint-loop shells; group-preserving rest mesh join'
        if not any(m.type=='ARMATURE' for m in ob.modifiers):raise RuntimeError('Join lost skin: '+ob.name)
    combine('Face',['Head','Ears','Eyelids','Neck','Eye_','Brows','Lashes'])
    combine('Hair',['HairCap','HairClump','Ponytail','CoralHairTie','CoralStud'])
    combine('JacketOutfit',['Jacket','Sleeve','SoftWrapCollar','MockNeck','Wrap','Collar','FrontHem','Tail'])
    combine('PantsOutfit',['Pants'])
    combine('Gloves',['Hand_','Forearm','Gauntlet'])
    combine('Boots',['Boot'])
    combine('KneePads',['Knee'])
    combine('ClothAccessories',['Belt','MedicPouch','Pouch','Harness'])
    combine('ShoulderBloomMark',['BloomEmblem'])
    combine('BloomBody',['Bloom'],exclude=('BloomVane','BloomEmblem'))
    combine('HealDroneShell',['HealDroneShell','Drone'])
    combine('InjectorBody',['Injector','VialCap'],exclude=('InjectorVial',))

def write_notes(report):
    (HERE/'NOTES.md').write_text(f'''# Solace v2 — authored medic model

Fresh, reproducible Blender geometry built by `build_solace.py` and the shared
`assets/characters/_shared/character_v2.py`. No TRELLIS or old character geometry
is imported. The earlier Solace files remain in the parent directory.

Authoritative design references: main v09, face v05, turnaround v08, Bloom back
v04, interpreted through the full Solace BRIEF and art direction log.

- Lean athletic female proportions, skull height 1.68 m, feet Z0, front -Y.
- Common 61-bone UE5-named skeleton/rest axes shared with Kestrel; 45° A-pose.
- Warm deep brown modeled face; dark brown eyes; brown-black side-parted hair.
- Ponytail, injector bracer and sand medic pouch on her RIGHT (-X).
- Three-petal Bloom emblem and docked single-eye heal drone on LEFT (+X).
- Ivory wrap jacket front ends at Z .900; curved split back tails reach .645.
- Soft collar, charcoal mock-neck, sand trousers, slim ivory knee pads, charcoal
  finger gloves and shaped ankle boots. Broad color planes and creases are authored.
- Compact closed three-vane Bloom: coral seams, charcoal yoke, two LEDs, lower hub;
  vane objects have hinge origins and exported pivot sockets for a healing burst.
- Painted coral cloth, tie, studs and emblem have no emission. `M_SOL_Glow` is the
  sole emissive material and belongs to Bloom, injector vial and drone technology.

## Technical validation

Evaluated triangles: **{report['triangles']:,}** including all hair and gear.
Mesh objects: {report['mesh_objects']}. Maximum vertex influences:
**{report['max_vertex_influences']}**. Unnormalized/unweighted/over-four vertices:
**{report['bad_weight_vertices']}**. Every mesh has UVs. PBR paint textures are
embedded in GLB and packed in the Blender scene; FBX copies textures.

Static deformation renders: sprint, crouch (60° hip/95° knee bends), two-hand aim,
and overhead zipline reach. These are QA poses only; exports contain no animation
clips. `solace_qa.json` records per-mesh exported checks; `validation.json` contains
the compact whole-model checks. Render folder includes front, left-side-facing
right camera, back, front/rear three-quarter, face and Bloom close-ups, pose sheet,
and 64-pixel front/side/back silhouettes.

## Exports and rebuild

`solace.blend`, `solace.glb`, `solace.fbx` all use the shared neutral rest rig.
Rebuild with Blender 5.2:

    blender -b --factory-startup -P build_solace.py

Use `-- --quick` for neutral front/three-quarter previews. No game code is changed.

## Limits

Hair clumps are weighted to the head, and coat tails use pelvis/thigh blends.
Secondary hair/cloth simulation and production facial blendshapes are future
animation work. Bloom deployment has mechanical origins and sockets but no clip.
''',encoding='utf-8')

def render_character(base,objs,quick=False):
    bc.setup_studio(bg=(.075,.083,.099),strength=.72,floor=True)
    scene=bpy.context.scene
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
    # Long portrait framing makes the human proportions and tailor details assessable.
    paths=bc.render_views(str(HERE/'renders'),'solace',objs,views=('front','three_quarter') if quick else ('front','right','back','three_quarter','three_quarter_back'),res=(800,1000),ortho=True,margin=1.04,focus=((0,0,.86),.94),samples=48,engine='CYCLES')
    bc.contact_sheet(paths,str(HERE/'renders'/'solace_sheet.png'),cols=2)
    if not quick:
        bc.render_views(str(HERE/'renders'),'face',objs,views=('front','three_quarter'),res=(900,900),ortho=True,margin=1.06,focus=((0,-.02,1.575),.173),samples=64,engine='CYCLES')
        bc.render_views(str(HERE/'renders'),'bloom',objs,views=('back','three_quarter_back'),res=(900,900),ortho=True,margin=1.04,focus=((0,.12,1.35),.235),samples=48,engine='CYCLES')
    return paths

def render_silhouettes(base,objs):
    black=bc.material('_SOL_Silhouette',(0.003,0.003,0.003),rough=1)
    saved={o.name:list(o.data.materials) for o in objs}
    for o in objs:
        for k in range(len(o.data.materials)):o.data.materials[k]=black
    # Retain deliberate silhouette rendering in the deliverable, without changing exports.
    paths=bc.render_views(str(HERE/'renders'),'silhouette',objs,views=('front','right','back'),res=(256,320),ortho=True,margin=1.04,focus=((0,0,.86),.94),samples=24,engine='CYCLES')
    bc.contact_sheet(paths,str(HERE/'renders'/'silhouette_sheet.png'),cols=3)
    for o in objs:
        for k,m in enumerate(saved[o.name]):o.data.materials[k]=m
    # The 64-pixel comparison uses the same three silhouettes downsampled with Blender pixels.
    import numpy as np
    small=[]
    for p in paths:
        im=bpy.data.images.load(p,check_existing=False);im.scale(52,64);small.append(im)
    buf=np.ones((64,156,4),dtype=np.float32)
    for i,im in enumerate(small):buf[:,i*52:(i+1)*52]=np.array(im.pixels[:]).reshape(64,52,4)
    im=bpy.data.images.new('_64px_silhouette',156,64);im.pixels=buf.ravel();im.filepath_raw=str(HERE/'renders'/'silhouette_64.png');im.file_format='PNG';im.save()

def main():
    os.makedirs(HERE/'renders',exist_ok=True);os.makedirs(HERE/'textures',exist_ok=True)
    bc.reset_scene();base=cv.build_base(prefix='SOL',height=1.68,skin=(.26,.14,.085),eye_color=(.10,.055,.030))
    m={}
    for name,key,col,rough,paint in [('Ivory','ivory',(.70,.67,.60),.68,True),('IvoryHard','hard',(.70,.67,.60),.45,False),('BoneInset','hardshade',(.53,.50,.44),.52,False),
        ('Sand','sand',(.44,.37,.27),.76,True),('SandFold','sandshade',(.355,.285,.19),.76,False),('SandPaintLight','sandlight',(.50,.43,.32),.76,False),('IvorySeam','seam',(.54,.52,.47),.70,False),
        ('Charcoal','charcoal',(.035,.037,.045),.72,True),('Glove','glove',(.028,.030,.037),.60,False),
        ('Boot','boot',(.032,.035,.043),.65,False),('Graphite','graphite',(.030,.033,.040),.55,False),
        ('Gunmetal','gunmetal',(.11,.115,.12),.38,False),('Coral','coral',(.85,.20,.13),.53,False),
        ('Hair','hair',(.022,.012,.009),.70,True),('HairPlanes','hairlight',(.031,.018,.014),.70,True)]:
        m[key]=authored_material(name,col,rough,.6 if key=='gunmetal' else 0,paint)
    m['glow']=authored_material('Glow',(1,.36,.30),.40,glow=True)
    m['pantspaint']=m['sand'].copy();m['pantspaint'].name='M_SOL_TrouserFoldPaint'
    pn=next(n for n in m['pantspaint'].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    for link in list(pn.inputs['Base Color'].links):m['pantspaint'].node_tree.links.remove(link)
    vc=m['pantspaint'].node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='SOL_ClothPaint'
    m['pantspaint'].node_tree.links.new(vc.outputs['Color'],pn.inputs['Base Color'])
    for key in ['hair','hairlight','ivory','sand']:
        p=next(n for n in m[key].node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        if 'Specular IOR Level' in p.inputs:p.inputs['Specular IOR Level'].default_value=.20
    build_clothing(base,m);build_hair(base,m);build_bloom(base,m);build_tech(base,m)
    compact_skinned_parts(base)
    objs,report=qa_report(base);write_notes(report)
    # Save the rigged neutral model before static QA poses; exports remain animation-free.
    allobs=objs+[base['armature']]+[o for o in bpy.context.scene.objects if o.type=='EMPTY' and o.name.startswith('SOL_')]
    cv.export_character(base,str(HERE/'solace'),objects=allobs)
    render_character(base,objs,'--quick' in sys.argv)
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'solace.blend'),compress=True)
    if '--quick' not in sys.argv:
        posepaths=[]
        for pose in ['sprint','crouch','aim','zipline']:
            cv.pose(base['armature'],pose)
            bpy.context.view_layer.update()
            # Place the lowest boot on the ground for a readable static QA stance.
            boots=[o for o in objs if o.name.startswith('SOL_Boot')]
            low,high=bc.world_bounds(boots)
            rt=base['armature'].pose.bones['root'];rt.matrix=Matrix.Translation((0,0,-low.z))@rt.matrix
            bpy.context.view_layer.update()
            posepaths+=bc.render_views(str(HERE/'renders'),'pose_'+pose,objs,views=('three_quarter',),res=(800,1000),ortho=True,margin=1.04,focus=((0,0,.83),1.02),samples=32,engine='CYCLES')
        bc.contact_sheet(posepaths,str(HERE/'renders'/'pose_sheet.png'),cols=2)
        cv.reset_pose(base['armature'])
        render_silhouettes(base,objs)
        bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'solace.blend'),compress=True)

if __name__=='__main__':main()
