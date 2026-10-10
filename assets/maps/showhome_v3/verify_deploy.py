"""Check the staged runtime package without Blender or a game run."""
from pathlib import Path
import json,hashlib,sys
from gltf_shared import read
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];ASSETS=ROOT/'game/assets';MAP=ASSETS/'maps/showhome_v3'
PHYS={'glass','wood_thin','wood_thick','sheet_metal','metal_heavy','drywall','concrete','brick','cladding','foliage_thin','foliage_dense','fabric','plastic','soil','grass','gravel','sand','asphalt','paving','water'}
fail=[];checked=0
manifest=json.loads((MAP/'map_manifest.json').read_text(encoding='utf8'));catalog={r['id']:r for r in json.loads((ASSETS/'props/catalog.json').read_text(encoding='utf8'))['props']}
def scene(p):
    global checked
    j,buf=read(p);checked+=1
    for im in j.get('images',[]):
        if 'uri' not in im or not (p.parent/im.get('uri','')).is_file():fail.append(str(p)+': missing image '+str(im))
    for mat in j.get('materials',[]):
        ex=mat.get('extras',{})
        if ex.get('phys') not in PHYS:fail.append(str(p)+': missing phys '+mat['name'])
        for key in ('height_source','height_map'):
            if key in ex and not (ASSETS/ex[key]).is_file():fail.append(str(p)+': missing height '+ex[key])
    for m in j.get('meshes',[]):
        for primitive in m['primitives']:
            if not {'POSITION','NORMAL','TEXCOORD_0'}<=primitive['attributes'].keys():fail.append(str(p)+': missing vertex attributes')
for name in manifest['kit_scenes']:scene(MAP/name)
for pid in manifest['props']:
    r=catalog[pid]
    for key in ('glb','lod1'):scene(ASSETS/r[key])
    for key in ('collision',):
        if not (ASSETS/r[key]).is_file():fail.append(pid+': missing '+key)
if 'extension' in manifest:
    for name in manifest['extension']['kit_scenes']:scene(MAP/name)
    if not json.loads((MAP/'extension/QA.json').read_text(encoding='utf8'))['passed']:fail.append('Extension QA failed')
for name in ('houses.glb','ground.glb'):
    a,ab=read(HERE/'kit'/name);b,bb=read(MAP/name)
    if ab!=bb:fail.append(name+': staging modified mesh buffer')
handoff=json.loads((HERE/'HANDOFF.json').read_text(encoding='utf8'));sha=hashlib.sha256((MAP/'placements.ron').read_bytes()).hexdigest()
if sha!=handoff['placements_sha256']:fail.append('User placement checksum differs from handoff')
report={'passed':not fail,'failures':fail,'scenes_checked':checked,'props':len(manifest['props']),'user_placements_sha256':sha,'extension_staged':'extension' in manifest}
(HERE/'deployment_QA.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(json.dumps(report,indent=2));sys.exit(bool(fail))
