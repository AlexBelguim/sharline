import sys,json
from pathlib import Path
import bpy
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import common as C
import build_core as BC
p=HERE/'placements.generated.json';data=json.loads(p.read_text(encoding='utf8'))
removed={r['id'] for r in data['instances'] if r['prop_id']=='site_mesh_panel' and 684.9<r['position'][1]<688.1}
data['instances']=[r for r in data['instances'] if r['id'] not in removed];C.write(p,data);(HERE/'placements.proposed.ron').write_text(BC.ron(data),encoding='utf8')
bpy.ops.wm.open_mainfile(filepath=str(HERE/'showhome_v3.blend'),load_ui=False,use_scripts=False)
for ob in list(bpy.context.scene.objects):
    rid=ob.name.split('__',1)[0];colid=ob.get('instance_id')
    if rid in removed or colid in removed:bpy.data.objects.remove(ob,do_unlink=True)
rows=C.export_collision(HERE/'collision_assembled_qa.json',[o for o in bpy.context.scene.objects if o.name.startswith('COL_')]);bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'showhome_v3.blend'))
report=json.loads((HERE/'phase1_report.json').read_text(encoding='utf8'));report['prop_instances']=len(data['instances']);report['assembled_collision_volumes']=len(rows);C.write(HERE/'phase1_report.json',report)
print('OBSOLETE_PANELS_REMOVED',len(removed),'userfiles preserved')
