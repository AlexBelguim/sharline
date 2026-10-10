"""Clean editable Rain anatomy source for the wardrobe workflow (CC BY 4.0).

Geometry/shape-key source only, not a finished rigged gameplay character.
Run in Blender 5.2 with --disable-autoexec; no embedded source scripts run.
"""
from pathlib import Path
import bpy,sys,json
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
OUT=ROOT/'assets/characters/_shared/base'
SOURCE=ROOT/'assets/characters/_shared/_source/rain/bundle/rain_rig.blend'
NAMES=['GEO-rain_body_nomask','GEO-rain_head','GEO-rain_eyes_viewport','GEO-rain_eyebrows','GEO-rain_eyelashes']
bc.reset_scene();bpy.context.preferences.filepaths.save_version=0
with bpy.data.libraries.load(str(SOURCE),link=False)as(src,dst):dst.objects=NAMES
parts=[];low=.0054958784;high=1.623896122;scale=1.70/(high-low)
clay=bc.material('M_Base_Clay',(.38,.40,.42),rough=.65)
brow=bc.material('M_Base_Brow',(.030,.030,.035),rough=.75)
eyes=[bc.material('M_Base_Sclera',(.55,.52,.46),rough=.20),bc.material('M_Base_Iris',(.10,.044,.019),rough=.15),bc.material('M_Base_Pupil',(.003,.004,.005),rough=.12)]
col=bc.collection('CHAR_Base_Anatomy')
for ob in dst.objects:
 if not ob:continue
 bpy.context.scene.collection.objects.link(ob)
 ob.parent=None;ob.animation_data_clear()
 if ob.data.shape_keys:
  ob.data.shape_keys.animation_data_clear()
  for key in ob.data.shape_keys.key_blocks:key.value=0
 for mod in list(ob.modifiers):
  if mod.type!='MIRROR':ob.modifiers.remove(mod)
 # Freeze the neutral source frame; shape keys receive the same affine transform.
 ob.matrix_world=Matrix.Identity(4)
 transform=Matrix(((scale,0,0,0),(0,scale,0,0),(0,0,scale,-low*scale),(0,0,0,1)))
 ob.data.transform(transform,shape_keys=True)
 original=ob.name
 if original=='GEO-rain_body_nomask':ob.name='BASE_Body';bc.assign(ob,clay);ob['wardrobe_slot']='body_reference'
 elif original=='GEO-rain_head':ob.name='BASE_Head';bc.assign(ob,clay);ob['wardrobe_slot']='identity_reference'
 elif original=='GEO-rain_eyes_viewport':
  ob.name='BASE_Eyes';slots=[p.material_index for p in ob.data.polygons]
  ob.data.materials.clear()
  for mat in eyes:ob.data.materials.append(mat)
  for po,mi in zip(ob.data.polygons,slots):po.material_index=min(mi,2)
  ob['wardrobe_slot']='eyes_reference'
 else:ob.name='BASE_'+('Brows'if'eyebrows'in original else'Lashes');bc.assign(ob,brow)
 ob.hide_render=False;ob.hide_viewport=False;ob.hide_set(False)
 ob.vertex_groups.clear()
 ob['source_credit']='Rain Rig © Blender Foundation | cloud.blender.org'
 ob['source_license']='CC BY 4.0'
 ob['source_url']='https://studio.blender.org/characters/rain/v2/'
 ob['modifications']='Unmasked anatomy selected, wardrobe/rig removed, neutral source scaled to 1.70 m, clay review materials'
 for p in ob.data.polygons:p.use_smooth=True
 bc.link(ob,col);parts.append(ob)
bc.uv_all(parts)
OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
for ob in parts:ob.select_set(True)
bpy.context.view_layer.objects.active=bpy.data.objects['BASE_Body']
# Keep the anatomy and native face shape-key topology editable in the master.
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'female_base_source.blend'),compress=True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'female_base_source.glb'),export_format='GLB',use_selection=True,export_yup=True,export_animations=False,export_extras=True,export_skins=False)
lo,hi=bc.world_bounds(parts)
report={'source':'Rain v2.2','license':'CC BY 4.0','credit':'Rain Rig © Blender Foundation | cloud.blender.org',
        'status':'editable_anatomy_source','rigged':False,'game_ready_character':False,'height_m':1.70,
        'bounds':[list(lo),list(hi)],'triangles':sum(sum(len(p.vertices)-2 for p in ob.data.polygons)for ob in parts),
        'parts':[{'name':ob.name,'verts':len(ob.data.vertices),'uv':bool(ob.data.uv_layers),
                  'shape_keys':list(ob.data.shape_keys.key_blocks.keys())if ob.data.shape_keys else[]}for ob in parts]}
(OUT/'source_qa.json').write_text(json.dumps(report,indent=2)+'\n')
bc.setup_studio(bg=(.18,.185,.20),strength=.7,floor=True)
bpy.data.objects['_Floor'].scale=(4,4,4)
bc.render_views(str(OUT/'renders'),'base_anatomy',parts,views=('front','three_quarter','right','back'),res=(800,1000),engine='EEVEE',samples=32,ortho=True,focus=((0,0,.87),.92),margin=1.10)
bc.contact_sheet([str(OUT/'renders'/f'base_anatomy_{v}.png')for v in('front','three_quarter','right','back')],str(OUT/'renders/base_contact_sheet.png'),cols=2)
print('BASE_SOURCE_READY',json.dumps(report),flush=True)
