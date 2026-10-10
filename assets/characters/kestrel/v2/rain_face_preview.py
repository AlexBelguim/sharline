"""Standalone Kestrel/Rain face review; does not write assembled exports."""
from pathlib import Path
import sys,json
import bpy,bmesh
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).parent
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'assets/characters/_shared'),str(OUT)]
import blender_common as bc
import character_v2 as cv
import kestrel_face_rain as face
bc.reset_scene()
base=cv.build_base('KES',1.70,skin=(.62,.42,.33),eye_color=(.13,.065,.032))
head=face.make(base)
objects=[o for o in base['parts']if o.name in ('KES_Head','KES_Eyes','KES_Brows','KES_Lashes')]
for ob in bpy.context.scene.objects:
 if ob.type=='MESH' and ob not in objects:ob.hide_render=True
report={}
for ob in objects:
 bm=bmesh.new();bm.from_mesh(ob.data)
 report[ob.name]={'verts':len(ob.data.vertices),'triangles':sum(len(p.vertices)-2 for p in ob.data.polygons),'boundary_edges':sum(e.is_boundary for e in bm.edges),'source_credit':ob.get('source_credit'),'shape_keys':list(ob.data.shape_keys.key_blocks.keys())if ob.data.shape_keys else []}
 bm.free()
report['dims']=base['dims'];report['bones']=len(base['armature'].data.bones)
(OUT/'rain_face_qa.json').write_text(json.dumps(report,indent=2))
bc.setup_studio(bg=(.16,.175,.19),strength=.7,floor=False)
bc.VIEW_DIRS.update(front=(0,-1,.035),three_quarter=(.6,-1,.05),right=(1,0,.035))
bc.render_views(str(OUT/'renders'),'rain_face',objects,views=('front','three_quarter','right'),res=(900,900),engine='CYCLES',samples=48,ortho=True,focus=((0,-.010,1.596),.131),margin=1.1)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'rain_face_preview.blend'))
