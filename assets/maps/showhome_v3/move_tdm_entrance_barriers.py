"""Align TDM blocks with hedge returns, preserving user-owned placements.

Run with headless Blender on the existing assembled core; no kit rebuild.
"""
import sys,json
from pathlib import Path
import bpy
from mathutils import Matrix
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import common as C
import build_core as BC
lp=HERE/'layout.json';layout=json.loads(lp.read_text(encoding='utf8'))
y=layout['side_garden_end_y']-.65
run=next(r for r in layout['tdm_barrier_runs'] if r['id']=='four_home_entrance')
run.update(y=y,stable_id_start=52)
layout['tdm_barrier_runs']=[run]
layout['tdm_clip_north_y']=y
layout['tdm_play_bounds_design']=[330,620,410,y]
layout['outer_boundary']='Continuous6m side/back hedges; six TDM concrete barriers align with the roadside hedge returns. The public street remains open beyond this closure.'
C.write(lp,layout)
p=HERE/'placements.generated.json';data=json.loads(p.read_text(encoding='utf8'));moves={}
removed={r['id'] for r in data['instances'] if r['prop_id']=='concrete_barrier' and int(r['id'].rsplit('_',1)[1])<52}
data['instances']=[r for r in data['instances'] if r['id'] not in removed]
for row in data['instances']:
    if row['prop_id']=='concrete_barrier':
        moves[row['id']]=y-row['position'][1];row['position'][1]=y
for row in data['player_clips']:
    if row['id']=='clip_north':row['min'][1]=y-.1;row['max'][1]=y+.1
C.write(p,data);(HERE/'placements.proposed.ron').write_text(BC.ron(data),encoding='utf8')
bpy.ops.wm.open_mainfile(filepath=str(HERE/'showhome_v3.blend'),load_ui=False,use_scripts=False)
delete=set()
for ob in list(bpy.context.scene.objects):
    if ob.type=='EMPTY' and ob.parent and ob.parent.name.startswith('SH3_MapOrigin'):
        rid=ob.name.split('__',1)[0]
        if rid in removed:delete.update([ob,*ob.children_recursive])
        elif rid in moves:ob.location.y+=moves[rid]
    if ob.name.startswith('COL_'):
        rid=ob.get('instance_id')
        if rid in removed:delete.add(ob)
        elif rid in moves:ob.data.transform(Matrix.Translation((0,moves[rid],0)));ob.data.update()
for ob in delete:bpy.data.objects.remove(ob,do_unlink=True)
bpy.context.view_layer.update();cols=[o for o in bpy.context.scene.objects if o.name.startswith('COL_')]
C.export_collision(HERE/'collision_assembled_qa.json',cols);bpy.ops.wm.save_as_mainfile(filepath=str(HERE/'showhome_v3.blend'))
rp=HERE/'phase1_report.json';report=json.loads(rp.read_text(encoding='utf8'));report.update(prop_instances=len(data['instances']),assembled_collision_volumes=len(cols));C.write(rp,report)
print('TDM_HEDGE_ALIGNED',len(moves),'barriers; removed',len(removed),'obsolete road blocks')
