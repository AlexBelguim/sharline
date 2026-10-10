"""Isolated clean budget/bake from the user's immutable raw TRELLIS source.

Shared experiments may be updated by another task; final assets never depend on
their mutable outputs. Reuse the tested helper implementation in a private run.
"""
from pathlib import Path
import sys,json,hashlib
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent/'input'
SOURCE=Path('C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI/output/valetf_a_duffel_full_00001_.glb')
HELPER=OUT/'prepare_helpers.py'
sys.argv=['prepare_input.py','--','duffel',str(SOURCE),str(OUT),'0','4500']
script=HELPER.read_text().split('# ----------------------------------------------------------------------------------------- rendering')[0]
namespace={'__name__':'duffel_preparation','__file__':str(HELPER)}
exec(compile(script,str(HELPER),'exec'),namespace)
bpy.ops.wm.read_factory_settings(use_empty=True)
full=namespace['import_glb'](str(SOURCE),'DFL_Source')
vertices=[v.co for v in full.data.vertices]
lo=Vector(tuple(min(v[i]for v in vertices)for i in range(3)));hi=Vector(tuple(max(v[i]for v in vertices)for i in range(3)))
scale=1/max(hi-lo);center=(lo+hi)*.5
for v in full.data.vertices:v.co=Vector(((v.co.x-center.x)*scale,(v.co.y-center.y)*scale,(v.co.z-lo.z)*scale))
full.data.update()
low=namespace['decimate_copy'](full,4500,'DFL_Clean',strip_uv=True,voxel=.004)
namespace['bake_to'](low,full,2048)
namespace['export_glb'](low,str(OUT/'duffel_clean_input.glb'))
report=namespace['mesh_stats'](low)
report['raw_source']=str(SOURCE);report['source_sha256']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
report['preparation']='normalized 1m source, 4mm voxel cleanup, target4500, own UV and bake'
(OUT/'input_qa.json').write_text(json.dumps(report,indent=2)+'\n')
print('ISOLATED_INPUT_READY',json.dumps(report),flush=True)
