"""Stage the original Showhome's props (import_legacy_props.py, catalog tag 'showhome_legacy') into game/assets.

python deploy_legacy_props.py

Copies each prop's GLB and LOD (their textures are deduplicated into game/assets/maps/showhome_v3/textures, as the
v3 props' are), collision.json and metadata.json, and merges the entries into game/assets/props/catalog.json by id.
No map, placement or other catalog entry is touched.
"""
import json, shutil
from pathlib import Path
import deploy as D

def main():
    source = json.loads((D.ROOT / 'assets/props/catalog.json').read_text())
    chosen = [r for r in source['props'] if 'showhome_legacy' in r.get('tags', [])]
    for r in chosen:
        for key in ('glb', 'lod1'):
            D.stage_glb(D.ROOT / 'assets' / r[key], D.ASSETS / r[key])
        p = D.ROOT / 'assets' / r['collision']
        target = D.ASSETS / r['collision']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        shutil.copy2(p.parent / 'metadata.json', target.parent / 'metadata.json')
    catpath = D.ASSETS / 'props/catalog.json'
    current = json.loads(catpath.read_text())
    ids = {r['id'] for r in chosen}
    current['props'] = [r for r in current['props'] if r['id'] not in ids] + chosen
    catpath.write_text(json.dumps(current, indent=2) + '\n', encoding='utf8')
    print('STAGED', len(chosen), 'legacy props;', len(current['props']), 'in the game catalog')

if __name__ == '__main__':
    main()
