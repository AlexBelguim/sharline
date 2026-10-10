"""Private export roundtrip/parent-transform check for the shared v2 contract."""
from pathlib import Path
import sys
import json
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import character_v2 as cv
import blender_common as bc

bc.reset_scene()
base = cv.build_base()
gear = bc.box('KES_QATransformProbe', (.03, .03, .03), loc=(.17, -.06, 1.22),
              mat=bc.material('M_KES_QAProbe', (.03, .03, .04)))
cv.rigid(gear, base, 'spine_03')
bc.smart_uv(gear)
assert (gear.matrix_world.translation - Vector((.17, -.06, 1.22))).length < 1e-6
assert (base['sockets'][0].matrix_world.translation - Vector((0, .004, 1.92))).length < 1e-5
cv.export_character(base, str(HERE / 'qa/base_private'), objects=base['parts'] + [gear])
out = {'mesh_transform_probe': tuple(gear.matrix_world.translation),
       'sockets': {o.name: tuple(o.matrix_world.translation) for o in base['sockets']},
       'weights': cv.report(base, base['parts'] + [gear])}
(HERE / 'qa/export_qa.json').write_text(json.dumps(out, indent=2))
