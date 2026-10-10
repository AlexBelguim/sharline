"""Rebuild and validate the frozen Qwen/TRELLIS graphs; no server writes or GPU jobs."""
import sys,json,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE/'scripts'))
import trellis_gen as tg
import qwen_edit as qe

info=json.loads((HERE/'audit/object_info_snapshot.json').read_text())
prompt=(HERE/'prompts/qwen_clean_prop_edit.txt').read_text().strip()
trellis=tg.build('portapotty_source_krea_s11.png',42,'valetf_prop_trial_trellis_full',info,faces=700000,tex=4096)
qwen=qe.graph(['portapotty_source_krea_s11.png'],prompt,11,25,0,'valetf_prop_trial_qwen21')
for graph,name in ((trellis,'trellis2_seed42_full.api.json'),(qwen,'qwen21_clean_prop_edit.api.json')):
    assert graph==json.loads((HERE/'workflows'/name).read_text()),('graph changed',name)
    for node in graph.values():
        assert node['class_type'] in info,('missing registered node',node['class_type'])
        for value in node['inputs'].values():
            if isinstance(value,list) and len(value)==2 and isinstance(value[0],str) and isinstance(value[1],int):
                assert value[0] in graph,('dangling link',name,value)
manifest=json.loads((HERE/'audit/source_manifest.json').read_text())
for row in manifest['copies']:
    assert hashlib.sha256((HERE/row['copy']).read_bytes()).hexdigest()==row['copied_sha256'],row['copy']
availability=json.loads((HERE/'audit/availability.json').read_text())
assert all(m['listed_by_server'] and m['local_files'] for m in availability['models'].values())
print(json.dumps(dict(passed=True,trellis_nodes=len(trellis),qwen_nodes=len(qwen),
    copied_inputs_checked=len(manifest['copies']),availability_checked_at=availability['audited_at_utc'],
    generation_jobs_submitted=0,mode='offline snapshot audit; no uploads, queue calls or GPU work'),indent=2))
