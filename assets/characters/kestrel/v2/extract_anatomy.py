"""Extract only reusable CC0 facial anatomy, never a hidden nude body."""
from pathlib import Path
import bpy,bmesh,json,sys
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
source=next((ROOT/'assets/characters/_shared/_source/blender_studio/bundle').rglob('*.blend'))
out=ROOT/'assets/characters/_shared/_source/blender_studio'
bc.reset_scene()
names=['GEO-body_female_stylized','GEO-body_female_stylized.eye.L','GEO-body_female_stylized.eye.R']
with bpy.data.libraries.load(str(source),link=False)as(src,dst):dst.objects=names
for ob in dst.objects:bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.update()
offset=dst.objects[0].matrix_world.translation.x
matrices={ob.name:ob.matrix_world.copy()for ob in dst.objects}
skin=bc.material('AnatomySkin',(.49,.31,.23),rough=.6)
parts=[];rows=[]
for ob in dst.objects:
 matrix=matrices[ob.name].copy();ob.parent=None;ob.matrix_world=matrix
 ob.matrix_world.translation.x-=offset
 bpy.context.view_layer.update()
 ob.data=ob.data.copy();ob.data.transform(ob.matrix_world);ob.matrix_world.identity()
 for m in list(ob.modifiers):ob.modifiers.remove(m)
 if ob.name=='GEO-body_female_stylized':
  bm=bmesh.new();bm.from_mesh(ob.data)
  bmesh.ops.delete(bm,geom=[v for v in bm.verts if v.co.z<1.295],context='VERTS')
  bm.to_mesh(ob.data);bm.free();ob.name='CC0_FemaleHead'
  bc.assign(ob,skin)
 else:
  ob.name='CC0_Eye_'+('L'if '.L'in ob.name else'R')
  bc.assign(ob,bc.material('EyeWhite',(.55,.53,.47),rough=.18))
 for p in ob.data.polygons:p.use_smooth=True
 parts.append(ob)
 rows.append(dict(name=ob.name,verts=len(ob.data.vertices),polys=len(ob.data.polygons),matrix=[list(row)for row in matrix],min=[min(v.co[i]for v in ob.data.vertices)for i in range(3)],max=[max(v.co[i]for v in ob.data.vertices)for i in range(3)]))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'stylized_female_head.blend'),compress=True)
(out/'extraction.json').write_text(json.dumps(rows,indent=2))
bc.setup_studio(bg=(.20,.20,.21),strength=.8,floor=False)
bc.VIEW_DIRS.update(three_quarter=(.6,-1,.02),front=(0,-1,.02))
bc.render_views(str(out/'preview'),'anatomy',parts,views=('front','three_quarter','right'),engine='CYCLES',samples=32,res=(800,800),ortho=True,focus=((0,-.020,1.481),.15))
print('EXTRACTED_HEAD',json.dumps(rows),flush=True)
