from pathlib import Path
import bpy,json
ROOT=Path(__file__).resolve().parents[3]
source=ROOT/'assets/characters/_shared/_source/rain/bundle/rain_rig.blend'
with bpy.data.libraries.load(str(source),link=False)as(src,dst):dst.objects=['GEO-rain_body_nomask','GEO-rain_head']
body,head=dst.objects
arm=next(m.object for m in body.modifiers if m.type=='ARMATURE')
used=set();maxweights=0
for v in body.data.vertices:
 names=[body.vertex_groups[g.group].name for g in v.groups if g.weight>1e-5]
 used.update(names);maxweights=max(maxweights,len(names))
print('SOURCE_RIG',arm.name,len(arm.data.bones),'MAX',maxweights,flush=True)
print('SOURCE_GROUPS',json.dumps(sorted(used)),flush=True)
for name in sorted(used):
 b=arm.data.bones.get(name)
 if b:print('BONE',json.dumps({'name':name,'head':list(b.head_local),'tail':list(b.tail_local),'parent':b.parent.name if b.parent else None}),flush=True)
print('HEAD_GROUPS',json.dumps(list(head.vertex_groups.keys())),flush=True)
