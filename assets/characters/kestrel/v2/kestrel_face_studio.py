"""Kestrel adaptation of Blender Studio's CC0 stylized female facial topology.

The anatomy source is reusable; identity, proportions, painted skin and gear
remain SHARD/LINE. Source/license recorded beside the extracted source blend.
"""
from pathlib import Path
import math
import bpy,bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import character_v2 as cv
import blender_common as bc

ROOT=Path(__file__).resolve().parents[4]
SRC_EYE=np.array((.04733059,-.08040389,1.463278))
EYE_X=.030292
EYE_Z=1.596

def smooth(a,b,x):
 t=max(0.,min(1.,(x-a)/(b-a)));return t*t*(3-2*t)

def deform(p,eye=False):
 x,y,z=map(float,p)
 eye_dist=math.sqrt(((abs(x)-SRC_EYE[0])/.042)**2+((z-SRC_EYE[2])/.045)**2)
 # Orbital openings are closed by authored lid rings below, never a whole-face warp.
 w=0.
 if y<-.03 or eye:
  x=math.copysign(SRC_EYE[0]+(abs(x)-SRC_EYE[0])*(1-.14*w),x)
  z=SRC_EYE[2]+(z-SRC_EYE[2])*(1-.56*w)
 x*=.64
 zz=EYE_Z+(z-SRC_EYE[2])*(.694 if z>=SRC_EYE[2] else .85)
 yy=y*.80+.020
 if not eye:
  mouth=math.exp(-(x/.040)**2-((z-1.377)/.029)**2)*(1-smooth(-.09,-.05,y))
  z=1.377+(z-1.377)*(1-.35*mouth)
  zz=EYE_Z+(z-SRC_EYE[2])*(.694 if z>=SRC_EYE[2] else .85)
  front=1-smooth(-.080,-.020,y)
  correction=float(np.interp(z,[1.295,1.320,1.345,1.375,1.400,1.425,1.450,1.47],[.003,.008,.012,.018,.019,.011,0.,0.]))
  yy+=correction*front
  # Firm adult jaw; retain modeled lip, nostril and orbital loops.
  jaw=(1-smooth(1.395,1.455,z))*smooth(1.315,1.355,z)
  x*=1-.06*jaw
  nose=math.exp(-(x/.029)**2-((z-1.416)/.022)**2)*front
  x*=1-.24*nose
  chin=1-smooth(1.332,1.360,z)
  x*=1+.08*chin;zz+=.004*chin
 return Vector((x,yy,zz))

def make(base):
 old=('KES_Head','KES_Lips','KES_MouthLine','KES_Eyelids','KES_Eye_L','KES_Eye_R','KES_Brows','KES_Lashes','KES_Ears')
 for name in old:
  ob=bpy.data.objects.get(name)
  if ob:
   base['parts']=[o for o in base['parts']if o!=ob];bpy.data.objects.remove(ob,do_unlink=True)
 source=ROOT/'assets/characters/_shared/_source/blender_studio/stylized_female_head.blend'
 with bpy.data.libraries.load(str(source),link=False)as(src,dst):
  dst.objects=['CC0_FemaleHead','CC0_Eye_L','CC0_Eye_R']
 head=dst.objects[0]
 skin=base['materials']['skin']
 bc._set_input(bc._principled(skin),['Roughness'],.56)
 bc._set_input(bc._principled(skin),['Specular IOR Level','Specular'],.28)
 bc._set_input(bc._principled(skin),['Subsurface Weight','Subsurface'],.04)
 sclera=bc.material('M_KES_AnatomySclera',(.55,.48,.40),rough=.21)
 iris=bc.material('M_KES_AnatomyIris',(.105,.041,.014),rough=.15)
 irisrim=bc.material('M_KES_AnatomyIrisRim',(.023,.012,.008),rough=.15)
 pupil=bc.material('M_KES_AnatomyPupil',(.002,.003,.004),rough=.10)
 for ob in dst.objects:
  bpy.context.scene.collection.objects.link(ob)
  ob.animation_data_clear();ob.parent=None
  for m in list(ob.modifiers):ob.modifiers.remove(m)
  iseye=ob!=head
  if not iseye:
   native=[v.co.copy()for v in ob.data.vertices]
   ob.name='KES_Head';bc.assign(ob,skin)
   attr=ob.data.color_attributes.get('FacePaint')or ob.data.color_attributes.new(name='FacePaint',type='FLOAT_COLOR',domain='POINT')
   for v,d in zip(ob.data.vertices,attr.data):
    x,y,z=map(float,v.co);ax=abs(x)
    c=np.array((.84,.62,.48))
    cheek=math.exp(-((ax-.058)/.039)**2-((z-1.413)/.025)**2)
    c*=1+cheek*np.array((.025,-.08,-.08))
    upperlid=math.exp(-((ax-.047)/.029)**2-((z-1.481)/.013)**2)*(1-smooth(-.07,-.03,y))
    c*=1+upperlid*np.array((-.12,-.23,-.24))
    # The mouth is genuine facial geometry; its portable paint follows authored loops.
    width=.041
    fade=max(0,1-(x/width)**2)
    center=1.377+.0022*fade
    up=(.012+.004*math.exp(-((ax-.011)/.008)**2))*fade**.7
    down=.018*fade**.65
    if abs(x)<width and center-down<z<center+up and y<-.128:
     edge=min(smooth(center-down,center-down+.003,z),1-smooth(center+up-.003,center+up,z))
     lc=np.array((.43,.18,.13)) if z<center else np.array((.36,.14,.105))
     c=c*(1-edge)+lc*edge
    d.color=(*c,1.)
    v.co=deform(v.co)
   ob.data.color_attributes.active_color=attr
   ob['anatomy_source']='Blender Studio human base meshes v1.4.1, CC0; Kestrel proportions / paint authored here'
   # Continuous texture paint removes the coarse vertex boundary around lips.
   face_material=bc.material('M_KES_FacePaint',(1,1,1),rough=.56)
   fp=bc._principled(face_material)
   bc._set_input(fp,['Specular IOR Level','Specular'],.28)
   bc._set_input(fp,['Subsurface Weight','Subsurface'],.04)
   image=face_material.node_tree.nodes.new('ShaderNodeTexImage')
   image.image=bpy.data.images.load(str(Path(__file__).parent/'textures/face_paint.png'),check_existing=True)
   face_material.node_tree.links.new(image.outputs['Color'],fp.inputs['Base Color'])
   bc.assign(ob,face_material)
   ob.data.color_attributes.remove(attr)
   uv=ob.data.uv_layers.active
   for po in ob.data.polygons:
    isfront=sum(native[i].y for i in po.vertices)/len(po.vertices)<-.025
    for li in po.loop_indices:
     p=native[ob.data.loops[li].vertex_index]
     uu=(p.x/.28+.5)*.5+(.0 if isfront else .5)
     uv.data[li].uv=(uu,(p.z-1.295)/(1.613162-1.295))
  else:
   side='L'if ob.name.endswith('_L')else'R';ob.name='KES_Eye_'+side
   bc.assign(ob,sclera)
   for mat in(iris,irisrim,pupil):ob.data.materials.append(mat)
   sign=1 if side=='L'else-1
   center=SRC_EYE*np.array((sign,1,1))
   for po in ob.data.polygons:
    c=po.center;rad=math.hypot(c.x-center[0],c.z-center[2])
    if c.y<center[1]-.019:
     po.material_index=3 if rad<.0048 else(1 if rad<.0105 else(2 if rad<.0118 else 0))
   for v in ob.data.vertices:v.co=deform(v.co,True)
   eye_material=bc.material('M_KES_EyePaint',(1,1,1),rough=.14)
   nt=eye_material.node_tree;p=bc._principled(eye_material)
   image=nt.nodes.new('ShaderNodeTexImage');image.image=bpy.data.images.load(str(Path(__file__).parent/'textures/eye_paint.png'),check_existing=True)
   nt.links.new(image.outputs['Color'],p.inputs['Base Color'])
   bc.assign(ob,eye_material)
   uv=ob.data.uv_layers.active
   for po in ob.data.polygons:
    po.material_index=0
    for li in po.loop_indices:
     p=ob.data.vertices[ob.data.loops[li].vertex_index].co
     uv.data[li].uv=(.5+(p.x-sign*EYE_X)/.050,.5+(p.z-EYE_Z)/.050)
  for p in ob.data.polygons:p.use_smooth=True
  # Source crease/selection attributes are sculpt editor helpers, never export data.
  for a in list(ob.data.attributes):
   if a.name in('.sculpt_mask','.sculpt_face_set','crease_edge','sharp_face'):
    ob.data.attributes.remove(a)
  ob.data.update();bc.uv_all([ob]);cv.rigid(ob,base,'head');base['parts'].append(ob)
 bpy.context.view_layer.update()
 scalp=BVHTree.FromObject(head,bpy.context.evaluated_depsgraph_get())
 def facepoint(x,z,offset):
  hit,normal,_,_=scalp.ray_cast(Vector((x,-.25,z)),Vector((0,1,0)),.4)
  return hit+Vector((0,-offset,0)) if hit else Vector((x,-.09,z))
 browmat=bc.material('M_KES_AnatomyBrow',(.020,.012,.011),rough=.74)
 linermat=bc.material('M_KES_UpperLiner',(.018,.008,.007),rough=.75)
 bm=bmesh.new();bm.from_mesh(head.data)
 for sign,side in((1,'L'),(-1,'R')):
  border=set()
  for e in bm.edges:
   if not e.is_boundary:continue
   a,b=[v.co.copy()for v in e.verts];mid=(a+b)*.5
   if abs(mid.x-sign*EYE_X)>.035 or not EYE_Z-.035<mid.z<EYE_Z+.035 or mid.y>-.025:continue
   border.update(e.verts)
  outer=[v.co.copy()for v in border]
  outer.sort(key=lambda p:math.atan2((p.z-EYE_Z)/.020,(p.x-sign*EYE_X)/.027))
  eye=bpy.data.objects['KES_Eye_'+side]
  eye_surface=BVHTree.FromObject(eye,bpy.context.evaluated_depsgraph_get())
  vv=[];ff=[];cc=[];inner=[];n=len(outer)
  for p in outer:
   a=math.atan2((p.z-EYE_Z)/.020,(p.x-sign*EYE_X)/.027)
   dx=.0165*math.cos(a);sn=math.sin(a)
   z=EYE_Z+(.0062 if sn>=0 else .0042)*sn+.080*dx*sign
   x=sign*EYE_X+dx
   hit,normal,_,_=eye_surface.ray_cast(Vector((x,-.25,z)),Vector((0,1,0)),.4)
   inner.append(hit+Vector((0,-.00045,0))if hit else Vector((x,-.086,z)))
  for ring,q in enumerate((0.,.14,.48,1.)):
   for a,b in zip(inner,outer):
    p=a.lerp(b,q);p.y-=.0008*math.sin(math.pi*q)
    vv.append(p)
    c=np.array((.84,.62,.48))
    if ring<2 and p.z>EYE_Z:c*=np.array((.82,.72,.67))
    cc.append(c)
  for ring in range(3):
   for j in range(n):
    a=ring*n+j;b=ring*n+(j+1)%n;ff.append((a,b,b+n,a+n))
  if ff:
   ob=cv.mesh('KES_Eyelid_'+side,vv,ff,skin)
   attr=ob.data.color_attributes.new(name='FacePaint',type='FLOAT_COLOR',domain='POINT')
   for dst,c in zip(attr.data,cc):dst.color=(*c,1.)
   ob.data.color_attributes.active_color=attr
   cv.rigid(ob,base,'head');base['parts'].append(ob)
   lashv=[];lashf=[]
   for j,p in enumerate(inner):
    nxt=inner[(j+1)%n]
    if(p.z+nxt.z)*.5<EYE_Z:continue
    start=len(lashv)
    for pt in(p,nxt):lashv.extend((pt+Vector((0,-.00020,-.00008)),pt+Vector((0,-.00020,.00070))))
    lashf.append((start,start+2,start+3,start+1))
   lash=cv.mesh('KES_LashLine_'+side,lashv,lashf,linermat)
   cv.rigid(lash,base,'head');base['parts'].append(lash)
 bm.free()
 for sign,side in((1,'L'),(-1,'R')):
  vv=[];ff=[]
  for i in range(29):
   t=i/28;x=sign*(.012+.043*t)
   z=1.610+.006*math.sin(math.pi*t*.94)-.004*t
   thick=.0048*(1-t)**.65+.00055
   for zz in(z-thick*.45,z+thick*.55):vv.append(facepoint(x,zz,.00075))
   if i<28:ff.append((i*2,i*2+2,i*2+3,i*2+1))
  ob=cv.mesh('KES_Brow_'+side,vv,ff,browmat);cv.rigid(ob,base,'head');base['parts'].append(ob)
 base['dims'].update(eye_center_L=(EYE_X,-.077,EYE_Z),eye_center_R=(-EYE_X,-.077,EYE_Z),eye_front_y=-.078,eye_height=EYE_Z)
 return head
