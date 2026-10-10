"""Private head-only QA for shared v2 anatomy, no nude full-body renders."""
from pathlib import Path
import sys
import json
import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import character_v2 as cv
import blender_common as bc

bc.reset_scene()
base = cv.build_base()
out = HERE / 'qa'
out.mkdir(exist_ok=True)
(out / 'base_qa.json').write_text(json.dumps(cv.report(base, base['parts']), indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'base_private.blend'), compress=True)
bc.setup_studio(bg=(.08, .09, .105), strength=1.0)
for ob in bpy.context.scene.objects:
    if ob.type == 'LIGHT' and ob.name == 'L_Fill':
        ob.data.energy *= .38
        ob.data.color = (1., .96, .92)
    elif ob.type == 'LIGHT' and ob.name == 'L_Key':
        ob.data.energy *= .82
        ob.data.color = (1., .90, .80)
bc.render_views(str(out), 'face', views=('front', 'three_quarter', 'right'), res=(700, 800),
                samples=32, focus=((0, -.002, 1.587), .131), engine='EEVEE')
