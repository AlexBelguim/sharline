"""Stable source wardrobe slots on one rig; assembled GLBs for the game."""
from pathlib import Path
import json
import bpy

SLOTS={
 'identity':{'replaceable':False,'rule':'Kestrel head, eyes and facial identity stay consistent'},
 'body_neck':{'replaceable':False,'rule':'Common anatomy, body-rig weights'},
 'body_arms':{'replaceable':False,'rule':'Common exposed arms, body-rig weights'},
 'body_hands':{'replaceable':False,'rule':'Common articulated hands, finger rig; glove paint may vary'},
 'hair':{'replaceable':True,'rule':'Static scalp/roots, thick 3D locks with optional cosmetic tip bones; preserve head clearance'},
 'eyewear':{'replaceable':True,'rule':'LEFT lens/strap/earpiece; preserve the identity silhouette'},
 'jacket':{'replaceable':True,'rule':'Skinned garment using the common torso/arm rig'},
 'underlayer':{'replaceable':True,'rule':'Skinned under-suit; hide fully covered surfaces in an assembled skin'},
 'trousers':{'replaceable':True,'rule':'Skinned to the same pelvis/leg rig'},
 'footwear':{'replaceable':True,'rule':'Foot/ball weights; soles Z=0 in neutral pose'},
 'gloves':{'replaceable':True,'rule':'Hand/finger compatibility and weapon-grip clearance'},
 'chest_rig':{'replaceable':True,'rule':'Light costume rig; no armor stats or tier pips'},
 'knee_pads':{'replaceable':True,'rule':'Knee accessories retain calf/leg attachment and bend clearance'},
 'waist_gear':{'replaceable':True,'rule':'Belt, pouches and holster; pelvis/thigh attachments'},
 'ability_left':{'replaceable':True,'rule':'Grapple cosmetics keep the LEFT forearm socket/frame'},
 'ability_back':{'replaceable':True,'rule':'Jet cosmetics retain back/ability sockets and silhouette'},
}

def slot(name):
 s=name.removeprefix('KES_')
 if s.startswith(('Lens','Earpiece','EarStatus')):return'eyewear'
 if s.startswith(('Head','Eye_','Eyes','Eyelid','Brow','Lash','Lip','UpperLip','LowerLip','Mouth','Ears')):return'identity'
 if s.startswith('Neck'):return'body_neck'
 if s.startswith('Forearm'):return'body_arms'
 if s.startswith('Hand_'):return'body_hands'
 if s.startswith('Hair'):return'hair'
 if s.startswith('UnderSuit')or s.startswith('SuitZip'):return'underlayer'
 if s.startswith(('Jacket','Sleeve','Collar','HemRib'))or s=='ZipPull':return'jacket'
 if s.startswith(('Pants','PantOuter','Cargo')):return'trousers'
 if s.startswith('Boot'):return'footwear'
 if s.startswith('Glove'):return'gloves'
 if s.startswith(('Chest','BackPlate','BackFacet','ShoulderHarness','RibHarness','HarnessBuckle')):return'chest_rig'
 if s.startswith(('Knee','KneeStrap')):return'knee_pads'
 if s.startswith(('Belt','Pouch','Holster')):return'waist_gear'
 if s.startswith('Grapple'):return'ability_left'
 if s.startswith(('Jet','Thruster','Nozzle')):return'ability_back'
 raise ValueError('Assign a wardrobe slot to '+name)

def tag(objects):
 for ob in objects:
  if ob.type=='MESH':
   ob['skin_slot']=slot(ob.name)
   ob['skin_id']='kestrel_default'
   ob['character_id']='kestrel'
   ob['wardrobe_rig']=ob.parent.name if ob.parent and ob.parent.type=='ARMATURE'else'KES_Armature'

def manifest(base,objects,out):
 rows={s:{**meta,'nodes':[],'materials':[],'triangles':0}for s,meta in SLOTS.items()}
 for ob in objects:
  if ob.type!='MESH':continue
  s=ob['skin_slot'];r=rows[s]
  r['nodes'].append(ob.name)
  r['materials']+= [m.name for m in ob.data.materials if m]
  r['triangles']+=sum(len(p.vertices)-2 for p in ob.data.polygons)
 for r in rows.values():
  r['nodes'].sort();r['materials']=sorted(set(r['materials']))
 payload={'schema_version':1,'character_id':'kestrel','skin_id':'kestrel_default',
          'status':'art_refinement','assembled_asset':'kestrel.glb','source_master':'kestrel_master.blend',
          'frame':{'units':'metres','blender_up':'Z','front':'-Y','gltf_up':'Y','sole_z':0},
          'rig':{'name':base['armature'].name,'bones':list(base['armature'].data.bones.keys()),'one_shared_rig':True},
          'cosmetic_bones':[b.name for b in base['armature'].data.bones if b.name.startswith('hair_')],
          'sockets':[s.name for s in base['sockets']],'slots':rows,
          'available_skins':['kestrel_default'],'alternative_parts_built':False,
          'runtime_policy':'Load an assembled skin GLB. No separate part armatures or clothing simulation required.',
          'body_visibility_policy':'Export only visible anatomy for each outfit. Do not rely on transparency to hide body intersections.'}
 Path(out).write_text(json.dumps(payload,indent=2)+'\n')
 return payload

def save_master(out):
 # Keep complete unjoined source parts and the shared rig for future outfit work.
 bpy.ops.file.pack_all()
 bpy.ops.wm.save_as_mainfile(filepath=str(out),compress=True)
