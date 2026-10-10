"""Authored Kestrel facial planes, feature loops and portable intrinsic paint.

This replaces the preliminary smooth-union face while retaining the common rig.
Every landmark is in metres in the neutral character frame. No imported mesh.
"""
import math
import bpy
import numpy as np
from mathutils import Vector
import character_v2 as cv
import blender_common as bc

# Z, half width, front, side centre, back. Chin / jaw / malar / brow / skull.
STATIONS = np.array([
    (1.475,.014,-.046,-.035,-.025),
    (1.483,.027,-.068,-.027,.003),
    (1.494,.036,-.077,-.018,.030),
    (1.509,.048,-.076,-.006,.057),
    (1.524,.057,-.079,.000,.075),
    (1.538,.063,-.079,.003,.086),
    (1.552,.068,-.080,.004,.093),
    (1.568,.070,-.079,.005,.097),
    (1.583,.068,-.077,.005,.099),
    (1.599,.066,-.077,.005,.100),
    (1.615,.066,-.083,.006,.099),
    (1.637,.068,-.086,.008,.096),
    (1.655,.068,-.082,.012,.089),
    (1.677,.058,-.064,.016,.071),
    (1.693,.032,-.030,.020,.041),
    (1.700,.002,.018,.020,.022),
])
EYE_X=.0310
EYE_Z=1.597
MOUTH_Z=1.524

def smooth(a,b,x):
    t=max(0.,min(1.,(x-a)/(b-a)))
    return t*t*(3.-2.*t)

def g(x,z,cx,cz,rx,rz):
    return math.exp(-((x-cx)/rx)**2-((z-cz)/rz)**2)

def row(z):
    # Shape-preserving Hermite interpolation, avoiding visible station bands.
    k=max(0,min(len(STATIONS)-2,int(np.searchsorted(STATIONS[:,0],z)-1)))
    a,b=STATIONS[k],STATIONS[k+1]
    t=max(0.,min(1.,(z-a[0])/(b[0]-a[0])))
    slopes=[]
    for i in(k,k+1):
        lo=max(0,i-1);hi=min(len(STATIONS)-1,i+1)
        slopes.append((STATIONS[hi,1:]-STATIONS[lo,1:])/(STATIONS[hi,0]-STATIONS[lo,0]))
    h=b[0]-a[0]
    return (2*t**3-3*t*t+1)*a[1:]+(t**3-2*t*t+t)*h*slopes[0]+(-2*t**3+3*t*t)*b[1:]+(t**3-t*t)*h*slopes[1]

def front(x,z,socket=True):
    w,yf,cy,yb=row(z)
    xn=min(.999999,abs(x)/max(w,.001))
    y=cy+(yf-cy)*max(0.,1-xn*xn)**.34
    # Malar planes meet a narrow bridge, not a smooth protruding midface blob.
    y-=.0045*g(abs(x),z,.043,1.570,.022,.016)
    y+=.0027*g(abs(x),z,.041,1.540,.019,.015)
    y-=.0020*g(x,z,0,1.493,.022,.009)
    # Bridge and compact tip, alae and columella with a clear underside break.
    nose=(.012*math.exp(-((z-1.578)/.021)**2)+.0125*math.exp(-((z-1.556)/.008)**2))*smooth(1.540,1.550,z)*(1-smooth(1.595,1.614,z))
    nose_w=np.interp(z,[1.535,1.550,1.558,1.575,1.598,1.614],[.007,.0080,.0075,.0058,.0058,.005])
    y-=nose*math.exp(-(x/nose_w)**2.0)
    y-=.0090*g(abs(x),z,.0080,1.552,.0045,.0042)
    y+=.0017*g(abs(x),z,.0125,1.549,.0025,.0050)
    # Philtrum columns, lip cushions and small mentolabial hollow.
    y-=.0012*g(abs(x),z,.0035,1.537,.0020,.008)
    y+=.0012*g(x,z,0,1.537,.0025,.006)
    y-=.0026*g(x,z,0,MOUTH_Z+.0018,.019,.0038)
    y-=.0032*g(x,z,0,MOUTH_Z-.0030,.018,.0040)
    y+=.0017*g(x,z,0,MOUTH_Z-.011,.016,.005)
    if socket:
        dx=(abs(x)-EYE_X)/.0178
        dz=(z-EYE_Z-.085*(abs(x)-EYE_X))/.0070
        rr=math.hypot(dx,dz)
        y+=.0080*(1-smooth(.65,1.70,rr))
    return y

def color(x,y,z):
    # Intrinsic skin colour and soft makeup; never a baked key-light direction.
    c=np.array((.83,.61,.46))
    blush=g(abs(x),z,.040,1.562,.023,.018)
    c*=1+blush*np.array((.025,-.075,-.09))
    eye=g(abs(x),z,EYE_X,1.609,.019,.008)
    c*=1+eye*np.array((-.12,-.21,-.23))
    under=g(abs(x),z,EYE_X,1.590,.019,.006)
    c*=1+under*np.array((-.055,-.07,-.065))
    nose=g(x,z,0,1.551,.013,.009)
    c*=1+nose*np.array((.005,-.035,-.045))
    edge=g(abs(x),z,.057,1.534,.014,.018)
    c*=1+edge*np.array((-.045,-.060,-.060))
    # Fade front paint into the scalp/ear base instead of drawing side stripes.
    fac=smooth(.020,-.025,y)
    return np.array((.83,.61,.46))*(1-fac)+c*fac

def paint(ob, colors):
    a=ob.data.color_attributes.new(name='FacePaint',type='FLOAT_COLOR',domain='POINT')
    for dst,c in zip(a.data,colors):dst.color=(*c,1.)
    ob.data.color_attributes.active_color=a

def make(base):
    remove=('KES_Head','KES_Lips','KES_MouthLine','KES_Eyelids','KES_Eye_L','KES_Eye_R','KES_Brows','KES_Lashes')
    for name in remove:
        ob=bpy.data.objects.get(name)
        if ob:
            base['parts']=[o for o in base['parts'] if o!=ob]
            bpy.data.objects.remove(ob,do_unlink=True)
    skin=base['materials']['skin']
    bc._set_input(bc._principled(skin),['Roughness'],.56)
    bc._set_input(bc._principled(skin),['Specular IOR Level','Specular'],.30)
    bc._set_input(bc._principled(skin),['Subsurface Weight','Subsurface'],.045)
    def add(name,v,f,mat,colors=None):
        ob=cv.mesh('KES_'+name,v,f,mat)
        if colors is not None:paint(ob,colors)
        elif mat==skin:paint(ob,[color(*p)for p in v])
        base['parts'].append(cv.rigid(ob,base,'head'))
        return ob
    zs=sorted(set([round(z,7)for z in np.concatenate((np.linspace(1.4755,1.6995,47),np.linspace(1.512,1.564,22),np.linspace(1.584,1.614,12)))]))
    n=80;v=[];f=[]
    for z in zs:
        w,yf,cy,yb=row(z)
        for j in range(n):
            # More samples on face; the hidden rear skull is deliberately sparse.
            a=(-math.pi+(j/10)*(math.pi/2)) if j<10 else ((-math.pi/2+(j-10)/60*math.pi) if j<70 else(math.pi/2+(j-70)/10*(math.pi/2)))
            x=w*math.sin(a)
            y=front(x,z) if math.cos(a)>=-1e-6 else cy+(yb-cy)*abs(math.cos(a))
            v.append((x,y,z))
    for k in range(len(zs)-1):
        for j in range(n):
            a=k*n+j;b=k*n+(j+1)%n
            f.append((a,b,b+n,a+n))
    f.extend((tuple(reversed(range(n))),tuple(range((len(zs)-1)*n,len(zs)*n))))
    head=add('Head',v,f,skin)
    head['topology']='authored facial stations, continuous nasal / lip planes; matching concentric lids'
    # Surface-matched lip loops with a true cupid bow and a fuller lower lip.
    lip=bc.material('M_KES_LipPaint',(.24,.083,.060),rough=.43)
    upper=bc.material('M_KES_UpperLipPaint',(.165,.048,.035),rough=.50)
    seam=bc.material('M_KES_LipSeam',(.045,.011,.008),rough=.85)
    def lip_line(x):
        t=x/.0235
        return MOUTH_Z+.00045*(1-t*t)-.0007*t*t
    for isupper in(True,False):
        vv=[];ff=[];count=36
        for i in range(count+1):
            x=-.0235+.047*i/count;t=x/.0235;fade=max(0.,1-t*t)
            mid=lip_line(x)
            border=(.0037+.0010*math.exp(-((abs(x)-.006)/.004)**2)-.0007*math.exp(-(x/.003)**2))*fade**.75 if isupper else -.0054*fade**.7
            for k in range(5):
                q=k/4;z=mid*(1-q)+(MOUTH_Z+border)*q
                y=front(x,z,False)-.00025-.00055*math.sin(math.pi*q)*fade
                vv.append((x,y,z))
        for i in range(count):
            for j in range(4):
                a=i*5+j;ff.append((a,a+5,a+6,a+1))
        add('UpperLip'if isupper else'LowerLip',vv,ff,upper if isupper else lip)
    vv=[];ff=[]
    for i in range(41):
        x=-.0235+.047*i/40;t=x/.0235;z=lip_line(x)
        half=.00015+.00015*(1-t*t)
        for zz in(z-half,z+half):vv.append((x,front(x,zz,False)-.00095,zz))
        if i<40:ff.append((2*i,2*i+2,2*i+3,2*i+1))
    add('MouthLine',vv,ff,seam)
    # Small oval nasal cavities follow the sloping underside, not front dots.
    nostril=bc.material('M_KES_NasalCavity',(.070,.025,.015),rough=.9)
    for sign in(-1,1):
        vv=[]
        for j in range(24):
            a=math.tau*j/24;x=sign*.0070+.0018*math.cos(a);z=1.5488+.00075*math.sin(a)
            vv.append((x,front(x,z,False)-.00012,z))
        add('Nostril_'+str(sign),vv,[tuple(range(24))],nostril)
    sclera=bc.material('M_KES_EyeWhite',(.53,.47,.40),rough=.29)
    iris=bc.material('M_KES_IrisBrown',(.105,.048,.017),rough=.13)
    limbal=bc.material('M_KES_IrisEdge',(.019,.014,.010),rough=.13)
    pupil=bc.material('M_KES_Pupil',(.003,.004,.005),rough=.10)
    for material in(iris,limbal,pupil,sclera):
        bc._set_input(bc._principled(material),['Specular IOR Level','Specular'],.5)
    brow=bc.material('M_KES_BrowPaint',(.018,.012,.012),rough=.74)
    liner=bc.material('M_KES_EyeLiner',(.028,.012,.010),rough=.72)
    for sign,side in((1,'L'),(-1,'R')):
        cx=sign*EYE_X
        def almond(a,expand=1.):
            dx=.0165*math.cos(a)*expand
            dz=(.0047 if math.sin(a)>=0 else .0034)*math.sin(a)*expand+.100*dx
            return sign*(EYE_X+dx),EYE_Z+dz
        # Shared opening, four annular lid loops, thickened upper waterline.
        vv=[];ff=[];cc=[];seg=64
        for ring,exp in enumerate((1.,1.12,1.40,1.95)):
            for j in range(seg):
                x,z=almond(math.tau*j/seg,exp)
                ys=(front(x,z,False)-.00045,front(x,z,False)-.0012,front(x,z,True)-.00035,front(x,z,True)-.00018)
                p=(x,ys[ring],z);vv.append(p)
                c=color(*p)
                if ring<2:
                    isup=z>=EYE_Z+.085*(abs(x)-EYE_X)
                    c*=np.array((.68,.54,.49)) if isup else np.array((.94,.90,.86))
                cc.append(c)
        for ring in range(3):
            for j in range(seg):
                a=ring*seg+j;b=ring*seg+(j+1)%seg
                ff.append((a,b,b+seg,a+seg))
        add('Eyelid_'+side,vv,ff,skin,cc)
        eye_y=front(cx,EYE_Z,False)-.0020
        vv=[(cx,eye_y,EYE_Z)];ff=[];slots=[]
        for ring in range(5):
            for j in range(seg):
                a=math.tau*j/seg;cs,sn=math.cos(a),math.sin(a)
                rho=1/math.sqrt((cs/.0165)**2+(sn/(.0047 if sn>=0 else .0034))**2)
                ir=min(.0072,rho*.99)
                rad=(min(.0025,rho*.92),ir*.90,ir,ir+(rho-ir)*.65,rho)[ring]
                # Project iris from forward gaze; scleral edge meets the lid.
                x=cx+sign*rad*cs;z=EYE_Z+rad*sn+.100*rad*cs
                q=smooth(.0072,rho,rad) if rho>.0073 else 0.
                y=eye_y+.0022*(rad/.0072)**2
                y=y*(1-q)+(front(x,z,False)-.00020)*q
                vv.append((x,y,z))
        for j in range(seg):ff.append((0,1+j,1+(j+1)%seg));slots.append(3)
        for ring in range(4):
            for j in range(seg):
                a=1+ring*seg+j;b=1+ring*seg+(j+1)%seg
                ff.append((a,b,b+seg,a+seg));slots.append(1 if ring==0 else(2 if ring==1 else 0))
        eye=add('Eye_'+side,vv,ff,sclera)
        for mat in(iris,limbal,pupil):eye.data.materials.append(mat)
        for poly,mi in zip(eye.data.polygons,slots):poly.material_index=mi
        # Upper liner, tapered at both canthi; no sphere outlines around eyes.
        vv=[];ff=[]
        for j in range(33):
            a=math.pi*j/32;x,z=almond(a)
            width=.00035+.00085*math.sin(a)**.6
            for zz in(z-.00020,z+width):vv.append((x,front(x,zz,False)-.0010,zz))
            if j<32:ff.append((j*2,j*2+2,j*2+3,j*2+1))
        add('LashLine_'+side,vv,ff,liner)
        # Intentional broad brow arc, tapered tail and an angled inner end.
        vv=[];ff=[]
        for j in range(25):
            t=j/24;x=sign*(.013+.039*t)
            z=1.609+.008*math.sin(math.pi*t*.9)-.0025*t
            thick=.0052*(1-t)**.7+.0005
            for zz in(z-thick*.45,z+thick*.55):vv.append((x,front(x,zz,False)-.00065,zz))
            if j<24:ff.append((j*2,j*2+2,j*2+3,j*2+1))
        add('Brow_'+side,vv,ff,brow)
    base['dims'].update(eye_center_L=(EYE_X,-.077,EYE_Z),eye_center_R=(-EYE_X,-.077,EYE_Z),eye_height=EYE_Z,eye_front_y=front(EYE_X,EYE_Z,False)-.002)
    return head
