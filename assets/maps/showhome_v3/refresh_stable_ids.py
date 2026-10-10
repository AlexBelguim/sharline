"""Keep established ids when adding new props; no geometry/user placement changes."""
from pathlib import Path
import sys,json,collections
import bpy
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import common as C
import build_core as BC
j=json.loads((HERE/'placements.generated.json').read_text(encoding='utf8'))
def fresh(r):
    return r['prop_id']=='concrete_barrier' or r.get('color_variant')=='blue' or (r['prop_id'] in ('privacy_panel','hedge_frame') and abs(r['position'][1]-632.85)<.0001)
items=[r for r in j['instances'] if not fresh(r)]+[r for r in j['instances'] if fresh(r)];counts=collections.Counter();mapping={}
for r in items:
    pid=r['prop_id'];new=pid+'_'+str(counts[pid]);counts[pid]+=1;mapping[r['id']]=new;r['id']=new
j['instances']=items;C.write(HERE/'placements.generated.json',j);(HERE/'placements.proposed.ron').write_text(BC.ron(j),encoding='utf8')
def rename(name):
    pre='COL_' if name.startswith('COL_') else '';tail=name[len(pre):]
    if '__' in tail:
        rid,rest=tail.split('__',1)
        if rid in mapping:return pre+mapping[rid]+'__'+rest
    return name
p=HERE/'collision_assembled_qa.json';col=json.loads(p.read_text(encoding='utf8'))
for r in col['volumes']:
    r['name']=rename(r['name'])
    if r.get('parent'):r['parent']=rename(r['parent'])
C.write(p,col)
bpy.ops.wm.open_mainfile(filepath=str(HERE/'showhome_v3.blend'),load_ui=False,use_scripts=False)
targets={o:rename(o.name) for o in bpy.data.objects if rename(o.name)!=o.name}
for o in targets:o.name='STABLEID_TMP_'+o.name
for o,name in targets.items():o.name=name
for o in bpy.data.objects:
    if o.get('instance_id') in mapping:o['instance_id']=mapping[o['instance_id']]
bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'showhome_v3.blend'))
print('STABLE_IDS_REFRESHED',len(targets),'object names; user placements untouched',flush=True)
