"""Stage only this kit into the game's asset root; preserve existing foliage/depth assets.

python assets/maps/showhome/deploy_kit.py
The scene GLBs embed ordinary PBR textures. External v2 heights and shader
maps are copied as well. Bevy depth maps invert white-is-high into depth.
"""
from pathlib import Path
import hashlib
import json
import shutil
import numpy as np
from PIL import Image

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
DEST=ROOT/'game/assets/maps/showhome'


def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
    return dict(source=str(source.relative_to(ROOT)),destination=str(target.relative_to(ROOT)),
                bytes=source.stat().st_size,sha256=hashlib.sha256(source.read_bytes()).hexdigest())


def main():
    records=[]
    for name in ('houses.glb','ground.glb','props_placed.glb'):
        records.append(copy(HERE/'kit'/name,DEST/name))
    backdrop=HERE/'backdrop/backdrop.glb'
    if not backdrop.exists():raise FileNotFoundError('Finish backdrop.glb before staging the complete scene')
    records.append(copy(backdrop,DEST/'backdrop.glb'))
    for name in ('ground_steps.json','ground_blend_contract.json','props_placements.json'):
        records.append(copy(HERE/'kit'/name,DEST/name))
    v2=HERE/'textures/v2'
    for source in list(v2.glob('*.png'))+[v2/'manifest.json',v2/'trims.json']:
        records.append(copy(source,DEST/'textures/v2'/source.name))
        if source.stem.endswith('_height'):
            pixels=np.asarray(Image.open(source),np.uint16)
            Image.fromarray(65535-pixels,'I;16').save(DEST/'textures/v2'/(source.stem[:-7]+'_depth.png'))
    for source in (HERE/'backdrop/sky').glob('sky_*.png'):
        if source.name=='sky_compare.png':continue
        records.append(copy(source,DEST/'sky'/source.name))
    records.append(copy(HERE/'backdrop/sky/PROMPT.md',DEST/'sky/PROMPT.md'))
    (DEST/'deployment.json').write_text(json.dumps(dict(version=2,identity_scene_load=True,
        frame='glTF Y up; design-to-Bevy=(x,z,-y)',files=records),indent=2)+'\n',encoding='utf8')
    print('STAGED SHOWHOME',DEST,len(records),'files')


if __name__=='__main__':main()
