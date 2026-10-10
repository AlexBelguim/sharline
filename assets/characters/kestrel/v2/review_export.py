"""Fresh-import rendered proof: show the exported GLB, not a source-only shader."""
from pathlib import Path
import bpy,sys,json
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
bc.reset_scene()
bpy.ops.import_scene.gltf(filepath=str(OUT/'kestrel.glb'))
parts=[o for o in bpy.context.scene.objects if o.type=='MESH'and o.name.startswith('KES_')]
for ob in bpy.context.scene.objects:
 if ob.type=='MESH'and ob not in parts:ob.hide_render=True
bc.setup_studio(bg=(.18,.185,.20),strength=.70,floor=True)
bpy.data.objects['_Floor'].scale=(4,4,4)
try:bpy.context.scene.view_settings.look='AgX - Medium High Contrast'
except Exception:pass
bc.VIEW_DIRS.update(front=(0,-1,.035),three_quarter=(.60,-1,.07),right=(1,0,.035))
bc.render_views(str(OUT/'renders'),'glb_face',parts,views=('front','three_quarter','right'),res=(1000,1000),engine='CYCLES',samples=64,ortho=False,focus=((0,-.015,1.585),.20),margin=1.10,lens=85)
bc.VIEW_DIRS['three_quarter']=(.8,-.9,.35)
bc.render_views(str(OUT/'renders'),'glb_full',parts,views=('three_quarter',),res=(1000,1200),engine='CYCLES',samples=48,ortho=True,focus=((0,0,.88),.94),margin=1.12)
print('FRESH_GLB_RENDER_COMPLETE',flush=True)
