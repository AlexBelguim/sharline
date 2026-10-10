"""Licensed Rain anatomy on the project's rig, used for garment fitting.

Source credit: Rain Rig © Blender Foundation | cloud.blender.org — CC BY 4.0.
No embedded source scripts or native control rig is executed/exported.
"""
from pathlib import Path
import math,re,json
import bpy
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
import blender_common as bc
import character_v2 as cv

ROOT=Path(__file__).resolve().parents[4]
SOURCE=ROOT/'assets/characters/_shared/_source/rain/bundle/rain_rig.blend'
LOW=.0054958784
SCALE=1.70/(1.623896122-LOW)

def position(p):return Vector((p.x*SCALE,p.y*SCALE,(p.z-LOW)*SCALE))

def group_target(name):
 if not name.startswith('DEF-'):return None
 side='l'if name.endswith('.L')else('r'if name.endswith('.R')else None)
 if side:
  for token,target in(('Clavicle','clavicle'),('Upperarm','upperarm'),('Forearm','lowerarm'),('Hand','hand'),('Thigh','thigh'),('Shin','calf'),('Foot','foot'),('Toe','ball')):
   if token in name:return target+'_'+side
  match=re.search(r'(Thumb|Index|Middle|Ring|Pinky)([1-4])',name)
  if match:
   finger=match[1].lower();k=int(match[2])
   if finger!='thumb':
    if k==1:return'hand_'+side
    k-=1
   return f'{finger}_{k:02d}_{side}'
 for token,target in(('Pelvis','pelvis'),('Spine1','pelvis'),('Spine2','spine_01'),('Spine3','spine_02'),('Spine4','spine_03'),('Neck','neck_01')):
  if token in name:return target
 return None

def frame(a,b,hint):
 y=(b-a).normalized();z=Vector(hint);z=(z-y*z.dot(y)).normalized();x=y.cross(z).normalized()
 return Matrix((x,y,z)).transposed()

def fitting_body(base,source_name='GEO-rain_body_nomask',target_name='KES_REF_Anatomy',reference=True):
 with bpy.data.libraries.load(str(SOURCE),link=False)as(src,dst):dst.objects=[source_name]
 ob=dst.objects[0];native_arm=next(m.object for m in ob.modifiers if m.type=='ARMATURE')
 J=base['joints'];B=native_arm.data.bones
 def sp(n):return position(B[n].head_local)
 def st(n):return position(B[n].tail_local)
 segments={
  'pelvis':(sp('DEF-Spine1'),st('DEF-Spine1'),J['pelvis'],J['spine_01']),
  'spine_01':(sp('DEF-Spine2'),st('DEF-Spine2'),J['spine_01'],J['spine_02']),
  'spine_02':(sp('DEF-Spine3'),st('DEF-Spine3'),J['spine_02'],J['spine_03']),
  'spine_03':(st('DEF-Spine3'),st('DEF-Neck'),J['spine_03'],J['neck_01']),
  'neck_01':(sp('DEF-Neck'),st('DEF-Neck'),J['neck_01'],J['head']),
 }
 for sd,side in(('l','L'),('r','R')):
  for target,start,end in(('clavicle','DEF-Clavicle','DEF-Upperarm1'),('upperarm','DEF-Upperarm1','DEF-Forearm1'),('lowerarm','DEF-Forearm1','DEF-Hand'),('thigh','DEF-Thigh1','DEF-Shin1'),('calf','DEF-Shin1','DEF-Foot'),('foot','DEF-Foot','DEF-Toe')):
   bone=base['armature'].data.bones[f'{target}_{sd}']
   segments[f'{target}_{sd}']=(sp(start+'.'+side),sp(end+'.'+side),bone.head_local,bone.tail_local)
  source_a=sp('DEF-Hand.'+side);source_b=st('DEF-Hand.'+side)
  hand=base['armature'].data.bones['hand_'+sd]
  segments['hand_'+sd]=(source_a,source_b,hand.head_local,hand.tail_local)
  for finger in cv.FINGERS:
   for k in range(1,4):
    native_k=k if finger=='thumb'else k+1
    n=f'DEF-{finger.title()}{native_k}.{side}'
    target=f'{finger}_{k:02d}_{sd}';tb=base['armature'].data.bones[target]
    segments[target]=(sp(n),st(n),tb.head_local,tb.tail_local)
  ball=base['armature'].data.bones['ball_'+sd]
  segments['ball_'+sd]=(sp('DEF-Toe.'+side),st('DEF-Toe.'+side),ball.head_local,ball.tail_local)
 transforms={}
 for name,(a,b,c,d)in segments.items():
  hint=(0,0,1)if any(t in name for t in('clavicle','arm','hand','thumb','index','middle','ring','pinky','foot','ball'))else(0,-1,0)
  r0=frame(a,b,hint);r1=frame(c,d,hint)
  stretch=Matrix.Diagonal((1.,(d-c).length/max((b-a).length,1e-6),1.))
  transforms[name]=(a,c,r1@stretch@r0.transposed())
 weights=[]
 for v in ob.data.vertices:
  w={}
  for g in v.groups:
   target=group_target(ob.vertex_groups[g.group].name)
   if target and g.weight>1e-5:w[target]=w.get(target,0)+g.weight
  w=dict(sorted(w.items(),key=lambda p:-p[1])[:4]);total=sum(w.values())
  weights.append({n:a/total for n,a in w.items()}if total else{'pelvis':1.})
 if ob.data.shape_keys:ob.shape_key_clear()
 for v,w in zip(ob.data.vertices,weights):
  p=position(v.co);q=Vector((0,0,0))
  for n,value in w.items():
   a,c,r=transforms[n];q+=(c+r@(p-a))*value
  v.co=q
 for mod in list(ob.modifiers):ob.modifiers.remove(mod)
 ob.parent=None;ob.animation_data_clear();ob.matrix_world=Matrix.Identity(4)
 bpy.context.scene.collection.objects.link(ob)
 ob.name=target_name
 ob.hide_viewport=False;ob.hide_set(False)
 bc.assign(ob,bc.material('M_KES_Reference',(.38,.40,.42),rough=.7))
 cv._write_weights(ob,base,weights)
 ob['source_credit']='Rain Rig © Blender Foundation | cloud.blender.org'
 ob['source_license']='CC BY 4.0'
 ob['purpose']='Private garment fitting reference, excluded from assembled game export'if reference else'Adapted garment geometry for Kestrel'
 ob.hide_render=reference;ob.display_type='WIRE'if reference else'TEXTURED'
 bpy.context.view_layer.update()
 return ob

def fit_garments(objects,reference,base):
 """Keep garment shells outside the posed anatomical reference by 5 mm."""
 bpy.context.view_layer.update();body=BVHTree.FromObject(reference,bpy.context.evaluated_depsgraph_get());J=base['joints']
 stats=[]
 for ob in objects:
  stem=ob.name.removeprefix('KES_')
  eligible=stem.startswith(('Jacket','UnderSuit','Sleeve','Pants','PantOuterSeam'))
  if not eligible or ob.type!='MESH':continue
  moved=0;largest=0.
  for v in ob.data.vertices:
   p=v.co.copy();center=Vector((0,.008,p.z))
   if stem.startswith('Sleeve'):
    sd='l'if p.x>0 else'r'
    candidates=[]
    for start,end in(('upperarm','lowerarm'),('lowerarm','hand')):
     a,b=J[f'{start}_{sd}'],J[f'{end}_{sd}'];d=b-a
     t=max(0,min(1,(p-a).dot(d)/d.length_squared));c=a+d*t
     candidates.append(((p-c).length,c))
    center=min(candidates,key=lambda q:q[0])[1]
   elif stem.startswith('PantsLeg'):
    sd='l'if p.x>0 else'r'
    a,b=(J['thigh_'+sd],J['calf_'+sd])if p.z>J['calf_'+sd].z else(J['calf_'+sd],J['foot_'+sd])
    d=b-a;t=max(0,min(1,(p-a).dot(d)/d.length_squared));center=a+d*t
   d=p-center
   if d.length<1e-5:continue
   direction=d.normalized();hit,normal,_,distance=body.ray_cast(center,direction,.28)
   if hit and distance+.005>d.length:
    amount=min(.025,distance+.005-d.length)
    v.co=p+direction*amount;moved+=1;largest=max(largest,amount)
  ob.data.update();stats.append({'mesh':ob.name,'vertices_adjusted':moved,'largest_adjustment_m':largest})
 return stats
