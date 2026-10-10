"""Kestrel garment polish: rebuilt collar, cargo topology, rounded boots and rig shell.

Trouser topology adapted from Rain (CC BY 4.0) and refitted to the existing
game frame. Other new parts are original procedural costume construction.
"""
import math
import bpy,bmesh
from mathutils import Vector
import character_v2 as cv
import rain_anatomy

def _drop(b,stems):
 for ob in list(b.OWN):
  if any(ob.name.removeprefix('KES_').startswith(s)for s in stems):
   b.OWN.remove(ob);bpy.data.objects.remove(ob,do_unlink=True)

def _pants(b):
 _drop(b,('PantsPelvis','PantsLeg_','PantOuterSeam_','PantsTailorSeam_'))
 pants=rain_anatomy.fitting_body(b.BASE,'GEO-rain_jeans','KES_PantsTailored',False)
 b.bc.assign(pants,b.M['pants'])
 # Use the authored stitched crotch/waist topology and soften the jeans-specific
 # narrow cuffs into tactical cargo gathering above the new ankle boots.
 for v in pants.data.vertices:
  p=v.co
  if p.z<.37:
   sd='l'if p.x>=0 else'r';c=b.BASE['joints']['calf_'+sd]
   amount=.0045*math.exp(-((p.z-.275)/.062)**2)
   radial=Vector((p.x-c.x,p.y-c.y,0))
   if radial.length:p+=radial.normalized()*amount
 bm=bmesh.new();bm.from_mesh(pants.data)
 bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.co.z<.185],context='VERTS')
 bm.to_mesh(pants.data);bm.free();pants.data.update()
 pants['source_modifications']='Kestrel cargo trouser proportions, shortened boot cuffs, charcoal painted material, shared body rig binding'
 b.OWN.append(pants)
 # Constructed front fly and pocket mouths sit on the new torso/hip volume.
 for sign in(-1,1):
  b.ribbon('PantsFrontPocket_'+str(sign),[(sign*.081,-.116,.981),(sign*.129,-.106,.947),(sign*.150,-.084,.899)],.005,.0015,b.M['pantsLight'],'pelvis')
 b.ribbon('PantsFly',[(.012,-.120,.984),(.014,-.121,.940),(.015,-.113,.897)],.004,.0015,b.M['graph'],'pelvis')

def _boots(b):
 _drop(b,('Boot',))
 n=40
 # A round toe, narrow arch and curved heel give a real boot last instead of
 # extruding the same side profile across a rectangular width.
 for sign,side in((1,'L'),(-1,'R')):
  region='leg_'+side.lower();yaw=math.radians(-sign*8)
  def world(x,y,z):return Vector((sign*.118+x*math.cos(yaw)-y*math.sin(yaw),.006+x*math.sin(yaw)+y*math.cos(yaw),z))
  outline=[]
  for j in range(n):
   a=math.tau*j/n;sn,cs=math.sin(a),math.cos(a)
   y=-.067+.140*sn
   width=.047+.010*math.exp(-((y+.132)/.066)**2)-.007*math.exp(-((y+.015)/.038)**2)
   x=width*math.copysign(abs(cs)**.82,cs)
   outline.append((x,y,a))
  rr=[]
  for z,factor in((0.,.94),(.008,1.015),(.022,1.012),(.029,.98)):
   rr.append([world(x*factor,-.067+(y+.067)*factor,z)for x,y,a in outline])
  b.loft('BootSole_'+side,rr,b.M['graph'],True,region,'foot_'+side.lower())
  upper=[]
  for row in range(7):
   ring=[]
   for x,y,a in outline:
    toe=max(0,min(1,(-y-.075)/.130))
    if row==0:xx,yy,z=x*.965,y,.029
    elif row==1:xx,yy,z=x,y,.047+.019*(1-toe)
    elif row==2:xx,yy,z=x*.97,y*.98,.070+.026*(1-toe)
    else:
     q=(row-2)/4
     ankle_x=.042*math.cos(a);ankle_y=.002+.043*math.sin(a)
     xx=x*.97*(1-q)+ankle_x*q;yy=y*.98*(1-q)+ankle_y*q
     start=.070+.026*(1-toe);z=start*(1-q)+(.221+.008*max(0,-math.sin(a)))*q
    ring.append(world(xx,yy,z))
   upper.append(ring)
  boot=b.loft('BootUpper_'+side,upper,b.M['graph'],False,region)
  boot['construction']='rounded last, sculpted instep/heel, turned ankle cuff'
  cuff=[b.ring(world(0,.002,z),rx,ry,32)for z,rx,ry in((.215,.043,.044),(.228,.046,.046),(.235,.044,.044))]
  b.loft('BootCuff_'+side,cuff,b.M['jacket'],False,region)
  tongue=b.mesh('BootTongue_'+side,[world(x,y,z)for x,y,z in((- .026,-.089,.100),(.026,-.089,.100),(-.028,-.064,.155),(.028,-.064,.155),(-.025,-.052,.227),(.025,-.052,.227))],[(0,1,3,2),(2,3,5,4)],b.M['jacket'])
  b.reg(tongue,region)
  for k in range(5):
   z=.113+k*.021;y=-.083+k*.0065
   for flip in(-1,1):
    b.tube('BootLace_'+side+str(k)+'_'+str(flip),[world(flip*.022,y,z),world(-flip*.022,y+.006,z+.014)],[.00125,.00125],b.M['graph'],sides=6,samples=1,region=region)
  # Narrow rubber heel counter; all footwear stays dark as in the concept.
  b.box('BootHeelCounter_'+side,(.068,.008,.038),world(0,.070,.054),b.M['graph'],.004,region,'foot_'+side.lower())

def _collar(b):
 _drop(b,('Collar','ZipPull'))
 n=48;rr=[]
 for row in range(7):
  t=row/6;ring=[]
  for j in range(n):
   a=math.tau*j/n;x=math.cos(a);y=math.sin(a)
   rx=.084-.006*math.sin(math.pi*t)+.003*t;ry=.078-.005*math.sin(math.pi*t)+.005*t
   front=max(0,-y);side=x
   top=1.522+.010*y-.047*front**7*(1-.25*side)
   z=1.409*(1-t)+top*t
   # Deliberate folded side planes and a slanted front wrap, rather than a tube.
   crease=.0035*math.sin(a*2+.8)*math.sin(math.pi*t)
   xx=rx*x+x*crease;yy=.005+ry*y+y*crease
   if front>.5:
    yy+=.0030*math.exp(-((t-.56-.22*side)/.12)**2)*front
   ring.append(Vector((xx,yy,z)))
  rr.append(ring)
 b.loft('CollarOuter',rr,b.M['jacket'],False,'torso')
 inner=[[Vector((p.x*.94,(p.y-.005)*.94+.005,p.z-.001))for p in ring]for ring in rr]
 b.loft('CollarInside',inner,b.M['graph'],False,'torso')
 vv=rr[-1]+inner[-1];ff=[(j,(j+1)%n,(j+1)%n+n,j+n)for j in range(n)]
 b.reg(b.mesh('CollarTurnedRim',vv,ff,b.M['teal']))
 b.ribbon('CollarOverlap',[(.012,-.079,1.415),(.006,-.078,1.448),(-.006,-.074,1.477)],.018,.002,b.M['jacketLight'])
 b.box('ZipPull',(.007,.004,.013),(.008,-.084,1.443),b.M['gun'],.001)

def _chest(b):
 _drop(b,('ChestPlate','ChestFacet','ChestLowerPlane','ChestDiagonalBreak'))
 outline=[(-.039,.088),(.039,.088),(.058,.076),(.090,.068),(.120,.035),(.118,-.020),(.091,-.065),(.047,-.073),(.027,-.098),(-.027,-.098),(-.047,-.073),(-.091,-.065),(-.118,-.020),(-.120,.035),(-.090,.068),(-.058,.076)]
 n=len(outline);verts=[];faces=[]
 # Raised front, central break and rolled bevel are actual connected shell
 # topology; no extra flat polygons floating across the same plate.
 for scale,offset in((1.,.001),(.97,-.003),(.84,-.008),(.35,-.014)):
  for x,z in outline:
   xx,zz=x*scale,z*scale
   yy=-.143+1.9*xx*xx+.35*zz*zz+offset-.005*max(0,zz/.088)
   verts.append((xx,yy,1.277+zz))
 for k in range(3):
  for j in range(n):
   a=k*n+j;c=k*n+(j+1)%n;faces.append((a,c,c+n,a+n))
 center=len(verts);verts.append((0,-.161,1.277))
 for j in range(n):faces.append((3*n+j,3*n+(j+1)%n,center))
 frontlen=len(faces)
 back=len(verts)
 for x,z in outline:verts.append((x,-.131+1.9*x*x,1.277+z))
 for j in range(n):faces.append((j,back+j,back+(j+1)%n,(j+1)%n))
 faces.append(tuple(range(back,back+n)))
 plate=b.mesh('ChestSculptedRig',verts,faces,b.M['bone'])
 plate.data.materials.append(b.M['boneLight']);plate.data.materials.append(b.M['boneShade'])
 for p in plate.data.polygons:
  if p.index<frontlen:
   p.material_index=1 if p.center.z>1.292 else(2 if p.center.z<1.253 else 0)
 b.reg(plate,'torso')
 plate['construction']='connected curved light-polymer shell, recessed lower notch and rolled edge'

def apply(b):
 _pants(b);_boots(b);_collar(b);_chest(b)
 return b.OWN
