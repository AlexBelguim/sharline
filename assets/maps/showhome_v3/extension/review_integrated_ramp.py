"""Fast integrated ramp check against all latest serialized fixed collision.
Run with Blender -b --factory-startup -P extension/review_integrated_ramp.py.
Writes route QA only; does not change scene geometry, game files or placements.
"""
import sys,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path[:0]=[str(HERE),str(HERE.parent)]
import parking_basement as PARK
rows=json.loads((HERE/'collision.json').read_text())['volumes'];report=json.loads((HERE/'parking_report.json').read_text())
tests=[dict(direction=lane['direction'],**PARK.validate_basement_routes(dict(access_cores=[],vehicle_ramp=dict(route_samples=lane['route_samples'])),rows,radius=1.2,height=2.4)) for lane in report['vehicle_ramp']['lanes']]
report['vehicle_ramp']['integrated_two_way_vehicle_qa']=tests
(HERE/'parking_report.json').write_text(json.dumps(report,indent=2)+'\n')
source=json.loads((HERE/'report.json').read_text());source['parking_basement']=report;(HERE/'report.json').write_text(json.dumps(source,indent=2)+'\n')
print('INTEGRATED_RAMP',[(r['direction'],r['passed'],r['supported_samples']) for r in tests])
