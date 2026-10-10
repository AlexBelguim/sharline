from pathlib import Path
import bpy,json
ROOT=Path(__file__).resolve().parents[4]
source=ROOT/'assets/characters/_shared/_source/rain/bundle/rain_rig.blend'
with bpy.data.libraries.load(str(source),link=False)as(src,dst):
 print('OBJECTS',json.dumps(src.objects),flush=True)
 dst.objects=[n for n in src.objects if any(t in n.lower()for t in('head','eye','brow','lash','body'))and not n.startswith('WGT')]
for ob in dst.objects:
 if ob and ob.type=='MESH':
  print('MESH',json.dumps(dict(name=ob.name,verts=len(ob.data.vertices),polys=len(ob.data.polygons),bounds=[[min(v.co[i]for v in ob.data.vertices)for i in range(3)],[max(v.co[i]for v in ob.data.vertices)for i in range(3)]],mods=[(m.name,m.type)for m in ob.modifiers],materials=[m.name for m in ob.data.materials if m],shapes=list(ob.data.shape_keys.key_blocks.keys())if ob.data.shape_keys else[])),flush=True)
