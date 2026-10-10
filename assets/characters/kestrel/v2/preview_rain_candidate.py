"""Render the licensed Rain head before adaptation; source, not a Kestrel export."""
from pathlib import Path
import bpy,sys
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'assets/characters/_shared/_source/rain'
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
bc.reset_scene()
names=['GEO-rain_head','GEO-rain_eyes_viewport','GEO-rain_eyebrows','GEO-rain_eyelashes']
with bpy.data.libraries.load(str(OUT/'bundle/rain_rig.blend'),link=False)as(src,dst):dst.objects=names
skin=bc.material('CandidateSkin',(.49,.31,.23),rough=.56)
brow=bc.material('CandidateBrow',(.022,.012,.010),rough=.7)
eye_mats=[bc.material('CandidateWhite',(.58,.55,.49),rough=.22),bc.material('CandidateIris',(.12,.050,.024),rough=.15),bc.material('CandidatePupil',(.003,.004,.005),rough=.12)]
parts=[]
for ob in dst.objects:
 bpy.context.scene.collection.objects.link(ob)
 ob.animation_data_clear();ob.parent=None
 if ob.data.shape_keys:
  ob.data.shape_keys.animation_data_clear()
  for key in ob.data.shape_keys.key_blocks:key.value=0
 for mod in list(ob.modifiers):
  if mod.type not in('MIRROR','SUBSURF'):ob.modifiers.remove(mod)
  elif mod.type=='SUBSURF':mod.levels=1;mod.render_levels=1
 ob.hide_render=False;ob.hide_viewport=False;ob.hide_set(False)
 if ob.name=='GEO-rain_head':bc.assign(ob,skin)
 elif 'eyes_viewport'in ob.name:
  slots=[p.material_index for p in ob.data.polygons]
  ob.data.materials.clear()
  for mat in eye_mats:ob.data.materials.append(mat)
  for p,mi in zip(ob.data.polygons,slots):p.material_index=min(mi,2)
 else:bc.assign(ob,brow)
 parts.append(ob)
bc.setup_studio(bg=(.18,.185,.20),strength=.7,floor=False)
bc.VIEW_DIRS.update(front=(0,-1,.035),three_quarter=(.6,-1,.07))
bc.render_views(str(OUT/'preview'),'rain_candidate',parts,views=('front','three_quarter'),res=(900,900),engine='CYCLES',samples=48,ortho=True,focus=((0,-.015,1.475),.19),margin=1.1)
