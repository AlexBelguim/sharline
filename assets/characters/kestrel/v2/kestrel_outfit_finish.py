"""Authored cloth construction and restrained light-gear finish for Kestrel.

Call apply(builder) after make_clothes/make_gear.  Limb topology, weights, pose,
materials and shared helpers are retained; the finishing meshes use reg().
"""
import math
import bpy
from mathutils import Vector


def _ob(name):
    return bpy.data.objects.get('KES_' + name)


def _drop(b, name):
    ob = _ob(name)
    if ob is not None:
        if ob in b.OWN:
            b.OWN.remove(ob)
        bpy.data.objects.remove(ob, do_unlink=True)


def _crease(t, centre, width):
    # A ridge with a shallow return makes a folded fabric plane, not a tube ring.
    return math.exp(-((t-centre)/width)**2) - .42*math.exp(-((t-centre-width*1.45)/(width*.85))**2)


def _seam(b, name, path, width, mat, region='torso', bone=None, normal=(0,-1,0)):
    pp = b.catmull(path, 2)
    no = Vector(normal).normalized()
    verts = []
    for i, p in enumerate(pp):
        tangent = (pp[min(i+1,len(pp)-1)]-pp[max(0,i-1)]).normalized()
        cross = tangent.cross(no).normalized()
        if cross.length < .1:
            cross = Vector((1,0,0))
        verts.extend((p-cross*width*.5, p+no*.0007, p+cross*width*.5))
    faces = []
    for i in range(len(pp)-1):
        for j in range(2):
            a = i*3+j
            faces.append((a,a+1,a+4,a+3))
    return b.reg(b.mesh(name,verts,faces,mat),region,bone)


def _frame(b, name, center, width, height, bar, depth, mat, region='torso', bone=None):
    c = Vector(center)
    outer = [(-width/2,-height/2),(width/2,-height/2),(width/2,height/2),(-width/2,height/2)]
    inner = [(-width/2+bar,-height/2+bar),(width/2-bar,-height/2+bar),
             (width/2-bar,height/2-bar),(-width/2+bar,height/2-bar)]
    verts = [c+Vector((x,y,z)) for y in (-depth/2,depth/2) for ring in (outer,inner) for x,z in ring]
    faces = []
    for j in range(4):
        k = (j+1)%4
        faces.extend(((j,k,k+4,j+4),(j+8,j+12,k+12,k+8),
                      (j,j+8,k+8,k),(j+4,k+4,k+12,j+12)))
    return b.reg(b.mesh(name,verts,faces,mat,False),region,bone)


def _sleeves(b):
    for sign, side in ((1,'L'),(-1,'R')):
        ob = _ob('Sleeve_'+side)
        sh, el, wr = (Vector(b.BASE['joints'][n+'_'+side.lower()]) for n in ('upperarm','lowerarm','hand'))
        ad, fd = (el-sh).normalized(), (wr-el).normalized()
        cuff = el+fd*.102
        points = [Vector((sign*.13,.007,1.365)),sh+Vector((sign*.01,0,.012)),
                  sh+ad*.07,sh+ad*.16,el-ad*.055,el-ad*.020,
                  el+fd*.012,el+fd*.046,el+fd*.076,cuff]
        radii = [.057,.060,.057,.052,.049,.052,.048,.053,.047,.043]
        path = b.catmull(points,4)
        rr = [a+(c-a)*j/4 for a,c in zip(radii[:-1],radii[1:]) for j in range(4)]+[radii[-1]]
        if len(ob.data.vertices) != len(path)*26:
            raise ValueError('Sleeve finish requires the authored sleeve topology')
        for i,(p,radius) in enumerate(zip(path,rr)):
            tangent = (path[min(i+1,len(path)-1)]-path[max(0,i-1)]).normalized()
            front = (Vector((0,-1,0))-tangent*tangent.dot(Vector((0,-1,0)))).normalized()
            cross = front.cross(tangent).normalized()
            t = i/(len(path)-1)
            for j,q in enumerate(b.ring(p,radius,radius,26,2.25,(cross,front))):
                angle = j*math.tau/26
                # Five purposeful folds gathered at the elbow and cuff; the
                # upper arm remains a broad, tailored cloth surface.
                mask = .22+.78*max(0,math.sin(angle))**.7
                slope = .040*math.cos(angle+sign*.45)+.008*math.sin(angle*2+.4)
                amount = sum(amp*_crease(t-slope,c,w) for c,w,amp in
                             ((.46,.040,.0040),(.60,.035,.0050),(.70,.032,.0055),
                              (.81,.031,.0042),(.91,.023,.0030)))
                shoulder = .0033*_crease(t-.035*math.sin(angle),.20,.045)*max(0,-math.sin(angle))
                q += (q-p).normalized()*(amount*mask+shoulder)
                ob.data.vertices[i*26+j].co = q
        ob.data.update()
        ob['cloth_finish'] = 'tailored upper sleeve; diagonal elbow/cuff compression folds; original topology/weights'
        b.bc.shade_smooth(ob,65)
        region = 'arm_'+side.lower()
        # A raised single-needle seam is deliberately subdued in the charcoal.
        seam = []
        for idx in (3,7,11,15,19,23,27,31,35):
            p = path[idx]
            q = ob.data.vertices[idx*26+7].co.copy()
            seam.append(q+(q-p).normalized()*.0009)
        _seam(b,'SleeveConstruction_'+side,seam,.0015,b.M['jacketLight'],region)
        # A broad sewn shoulder yoke follows the same sleeve, never a plate.
        verts = []
        rows,cols = (3,5,7,9,11),(1,2,3,4,5,6)
        for i in rows:
            for j in cols:
                q = ob.data.vertices[i*26+j].co.copy()
                verts.append(q+(q-path[i]).normalized()*.0012)
        faces = []
        for i in range(len(rows)-1):
            for j in range(len(cols)-1):
                a = i*len(cols)+j
                faces.append((a,a+1,a+len(cols)+1,a+len(cols)))
        b.reg(b.mesh('SleeveShoulderYoke_'+side,verts,faces,b.M['jacketLight']),region)
        _seam(b,'SleeveYokeHem_'+side,[verts[-len(cols)+j] for j in range(len(cols))],
              .0018,b.M['jacket'],region)
        # Retain and narrow the existing cuff, giving it a clear turned hem.
        co = _ob('SleeveCuff_'+side)
        for v in co.data.vertices:
            along = (v.co-cuff).dot(fd)
            center = cuff+fd*along
            radial = v.co-center
            if radial.length:
                v.co = center+radial.normalized()*(.043 if along<-.01 else .042)
        co.data.update()


def _cloth(b):
    jacket = _ob('Jacket')
    for v in jacket.data.vertices:
        p = v.co
        angle = math.atan2(p.y-.002,p.x)
        side = abs(math.cos(angle))**6
        # Fabric gathers against the cropped hem and under the rib strap.
        fold = .0048*_crease(p.z+.014*math.sin(angle*2),1.186,.012)
        fold += .0035*_crease(p.z-.013*math.sin(angle),1.225,.016)
        fold *= side
        p.x += math.cos(angle)*fold
        p.y += math.sin(angle)*fold
        if p.z>1.35:
            p.x *= 1-.021*min(1,(p.z-1.35)/.06)
    jacket.data.update()
    jacket['cloth_finish'] = 'side gathers at hem and harness; narrowed shoulder transition'
    _collar(b)
    for sign,side in ((1,'L'),(-1,'R')):
        ob = _ob('PantsLeg_'+side)
        n = 32
        for k in range(len(ob.data.vertices)//n):
            vv = list(ob.data.vertices[k*n:(k+1)*n])
            c = sum((v.co for v in vv),Vector())/n
            for v in vv:
                d = v.co-c
                angle = math.atan2(d.y,d.x)
                front = .25+.75*max(0,-math.sin(angle))**.65
                # Diagonal tension from hip/pocket and knee; calf retains the
                # original looser folds and contour.
                shift = .40*sign*d.x
                amount = sum(a*_crease(v.co.z+shift,z,w) for z,w,a in
                             ((.814,.016,.0045),(.746,.019,.0040),(.591,.018,.0065),
                              (.550,.014,.0060),(.272,.016,.0030),(.193,.012,.0035)))
                if d.length:
                    v.co += d.normalized()*amount*front
        ob.data.update()
        ob['cloth_finish'] = 'hip and knee tension folds; original topology/weights'
        reg = 'leg_'+side.lower()
        _seam(b,'PantsTailorSeam_'+side,[(sign*.162,-.054,.857),(sign*.168,-.041,.791),
               (sign*.161,-.042,.714),(sign*.150,-.036,.642),(sign*.145,-.034,.581)],
              .0015,b.M['pantsLight'],reg)
    # Subtle front-panel darts make the visible navy waist read as sewn fabric.
    for sign in (-1,1):
        _seam(b,'UnderSuitDart_'+str(sign),[(sign*.092,-.074,1.012),(sign*.084,-.067,1.065),
              (sign*.090,-.073,1.114)],.0018,b.M['graph'])


def _collar(b):
    # Extra vertical stations describe an actual folded collar, while a modest
    # angular resolution spends fewer triangles around the invisible rear.
    for name in ('Collar','CollarLining','CollarLip'):
        _drop(b,name)
    n = 48
    rows = [(1.404,.090,.083,.008),(1.427,.084,.078,.008),
            (1.450,.081,.077,.008),(1.468,.082,.078,.006),
            (1.485,.084,.080,.005),(1.504,.087,.083,.003)]
    rings = []
    for z,rx,ry,cy in rows:
        sec = []
        u = (z-1.404)/.100
        for j in range(n):
            a = j*math.tau/n
            x,y = rx*math.cos(a),cy+ry*math.sin(a)
            zz = z
            if z>1.50:
                zz += .035*(math.sin(a)+1)/2
                if math.sin(a)<-.75:
                    zz -= .042*max(0,1-abs(x)/.035)
            radial = Vector((x,y-cy,0)).normalized()
            amount = .0026*math.sin(a*3+.55)*math.sin(u*math.pi)
            front = max(0,-math.sin(a))**4
            amount += .007*_crease(z+.31*x,1.454,.012)*front*math.sin(u*math.pi)
            p = Vector((x,y,zz))+radial*amount
            p.z += .0023*math.sin(a*2+.4)*u*u
            sec.append(p)
        rings.append(sec)
    co = b.loft('Collar',rings,b.M['jacket'])
    inner = [[Vector((p.x*.91,(p.y-.006)*.90+.006,p.z-.001)) for p in sec] for sec in rings]
    b.loft('CollarLining',inner,b.M['graph'])
    vv = rings[-1]+inner[-1]
    ff = [(j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n)]
    b.reg(b.mesh('CollarLip',vv,ff,b.M['teal']))
    co['cloth_finish'] = 'continuous shaped collar; diagonal compression plane; sewn teal lip'


def _side_panel(b,name,outline,x,depth,mat,region,bone):
    n = len(outline)
    verts = [(x+dx,y,z) for dx in (-depth/2,depth/2) for y,z in outline]
    faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces.extend((j,(j+1)%n,(j+1)%n+n,j+n) for j in range(n))
    ob = b.mesh(name,verts,faces,mat,False)
    b.bc.add_bevel(ob,.0025,1)
    return b.reg(ob,region,bone)


def _gear(b):
    # Reshape the two existing rig surfaces; this is the same light bone rig,
    # with a softer lower notch and a deliberate sloping central plane.
    for name in ('ChestPlate','ChestFacet'):
        _drop(b,name)
    outline = [(-.041,.093),(.041,.093),(.058,.081),(.087,.077),(.119,.041),
               (.119,-.015),(.096,-.064),(.046,-.073),(.028,-.095),
               (-.028,-.095),(-.046,-.073),(-.096,-.064),(-.119,-.015),
               (-.119,.041),(-.087,.077),(-.058,.081)]
    b.panel('ChestPlate',outline,(0,-.139,1.271),.014,b.M['bone'],wrap=1.7,bevel=.0035)
    b.panel('ChestFacet',[(-.036,.080),(.036,.080),(.053,.068),(.079,.063),
            (.105,.034),(.078,-.002),(-.079,-.002),(-.105,.034),(-.079,.063),(-.053,.068)],
            (0,-.151,1.271),.003,b.M['boneLight'],wrap=1.4,bevel=.0016)
    b.panel('ChestLowerPlane',[(-.075,-.012),(.078,-.012),(.084,-.045),
            (.040,-.056),(.023,-.078),(-.023,-.078),(-.040,-.056),(-.080,-.046)],
            (0,-.150,1.271),.0025,b.M['boneShade'],wrap=1.5,bevel=.0014)
    _seam(b,'ChestDiagonalBreak',[(.043,-.139,1.350),(.023,-.147,1.320),
          (-.005,-.153,1.277)],.0023,b.M['bone'],normal=(0,-1,0))
    for sign in (-1,1):
        _drop(b,'HarnessBuckle_'+str(sign))
        _frame(b,'HarnessBuckle_'+str(sign),(sign*.086,-.133,1.374),.025,.020,.0032,.003,
               b.M['gun'])
        _seam(b,'ShoulderHarnessEdge_'+str(sign),[(sign*.088,-.136,1.366),
               (sign*.109,-.091,1.412),(sign*.116,-.003,1.441)],.002,b.M['webLight'])
    for z,x,r in ((.72,.10,.086),(.646,.104,.077)):
        _drop(b,'HolsterBuckle'+str(z))
        _frame(b,'HolsterBuckle'+str(z),(-x,-r-.009,z),.023,.027,.003,.003,
               b.M['gun'],'leg_r','thigh_r')
    _drop(b,'CargoPocket');_drop(b,'CargoFlap')
    _side_panel(b,'PantsCargoPocket',[(-.047,.743),(.047,.743),(.047,.682),
                (.034,.624),(-.032,.626),(-.048,.686)],.185,.021,b.M['pants'],'leg_l','thigh_l')
    _side_panel(b,'PantsCargoFlap',[(-.052,.747),(.052,.747),(.050,.726),
                (.031,.715),(-.033,.717),(-.052,.732)],.198,.006,b.M['jacket'],'leg_l','thigh_l')
    _seam(b,'PantsCargoGusset',[ (.197,-.042,.725),(.197,-.037,.682),(.197,-.027,.638)],
              .002,b.M['pantsLight'],'leg_l','thigh_l',normal=(1,0,0))
    _seam(b,'PantsCargoHem',[(.198,-.031,.634),(.198,0,.631),(.198,.031,.634)],
              .002,b.M['pantsLight'],'leg_l','thigh_l',normal=(1,0,0))
    # Grip gets two broad traction ribs, not many tiny decorative mechanical bits.
    for i,z in enumerate((.855,.876)):
        b.box('HolsterGripRib'+str(i),(.027,.004,.004),(-.196,.010,z),b.M['web'],.001,
              'leg_r','thigh_r')
    # A recessed rail line makes the existing compact grapple read as machined.
    sh,el,wr = (Vector(b.BASE['joints'][n+'_l']) for n in ('upperarm','lowerarm','hand'))
    fd = (wr-el).normalized()
    up = (Vector((0,0,1))-fd*fd.z).normalized()
    _seam(b,'GrappleRailInset',[wr-fd*.118+up*.061,wr-fd*.042+up*.061,
          wr+fd*.025+up*.061],.003,b.M['gun'],'arm_l','lowerarm_l',normal=tuple(up))
    # Replace the three floating horizontal lace bars with a simple crossed
    # cord pattern on the existing low boot. Original foot/ball rig is retained.
    for sign,side in ((1,'L'),(-1,'R')):
        for k in range(3):
            _drop(b,'BootLace_'+side+str(k))
        a = math.radians(-sign*8)
        def boot_point(x,y,z):
            return (sign*.118+x*math.cos(a)-y*math.sin(a),
                    .010+x*math.sin(a)+y*math.cos(a),z)
        for k in range(3):
            for flip in (-1,1):
                p = boot_point(flip*.024,-.077+k*.006,.091+k*.015)
                q = boot_point(-flip*.024,-.071+k*.006,.106+k*.015)
                b.tube('BootLaceCross_'+side+str(k)+'_'+str(flip),[p,q],[.0015,.0015],
                       b.M['graph'],sides=6,samples=1,region='leg_'+side.lower(),bone='foot_'+side.lower())


def apply(builder):
    if builder.BASE is None:
        raise ValueError('Build shared anatomy before finishing the Kestrel outfit')
    _sleeves(builder)
    _cloth(builder)
    _gear(builder)
    return builder.OWN
