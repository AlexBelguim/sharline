"""Private cloth/gear QA renders; never writes the assembled character exports."""
from pathlib import Path
import sys
import json
import importlib.util
import bpy

OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('outfit_finish_builder',OUT/'build_kestrel.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
from kestrel_outfit_finish import apply

b.bc.reset_scene()
b.BASE = b.cv.build_base(prefix='KES',height=1.70,skin=(.62,.42,.33),eye_color=(.13,.065,.032))
b.make_materials()
b.make_clothes()
b.make_gear()

def tris(obs):
    dg = bpy.context.evaluated_depsgraph_get()
    count = 0
    for ob in obs:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        count += sum(len(p.vertices)-2 for p in me.polygons)
        ev.to_mesh_clear()
    return count

before = tris(b.OWN)
if '--before' not in sys.argv:
    apply(b)
after = tris(b.OWN)
print('OUTFIT_TRIANGLES',before,after,'DELTA',after-before,flush=True)
objs = b.BASE['parts']+b.OWN
b.bc.uv_all(objs)
b.skin_parts.tag(objs)
check = b.cv.report(b.BASE,objs)
(OUT/'outfit_finish_qa.json').write_text(json.dumps({'before':before,'after':after,'delta':after-before,
    'errors':check['errors'],'max_influences':max(m['max_influences'] for m in check['meshes']),
    'bad_weight_sums':sum(m['bad_sum'] for m in check['meshes'])},indent=2))
b.bc.setup_studio(bg=(.18,.185,.20),strength=.70,floor=True)
bpy.data.objects['_Floor'].scale=(4,4,4)
try:
    bpy.context.scene.view_settings.look='AgX - Medium High Contrast'
except Exception:
    pass
name = 'outfit_finish_before' if '--before' in sys.argv else 'outfit_finish_after'
b.bc.render_views(str(OUT/'renders'),name,objs,views=('front','three_quarter'),res=(900,1000),
    engine='EEVEE',samples=24,ortho=True,focus=((0,0,.87),.93),margin=1.12)
b.bc.VIEW_DIRS.update(three_quarter=(.6,-1,.08))
b.bc.render_views(str(OUT/'renders'),name+'_torso',objs,views=('three_quarter',),res=(1000,900),
    engine='EEVEE',samples=32,ortho=True,focus=((0,-.02,1.23),.39),margin=1.1)
print('OUTFIT_PREVIEW_DONE',flush=True)
