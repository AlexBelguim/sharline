from pathlib import Path
import bpy,json
ROOT=Path(__file__).resolve().parents[4]
source=next((ROOT/'assets/characters/_shared/_source/blender_studio/bundle').rglob('*.blend'))
with bpy.data.libraries.load(str(source),link=False)as(src,dst):
    dst.objects=list(src.objects)
rows=[]
for ob in dst.objects:
    if ob and ob.type=='MESH':
        lo=[min(v.co[i]for v in ob.data.vertices)for i in range(3)]
        hi=[max(v.co[i]for v in ob.data.vertices)for i in range(3)]
        rows.append(dict(name=ob.name,verts=len(ob.data.vertices),polys=len(ob.data.polygons),bounds=[lo,hi],mods=[(m.name,m.type)for m in ob.modifiers],groups=list(ob.vertex_groups.keys())))
print(json.dumps(rows,indent=2),flush=True)
