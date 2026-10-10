"""Stage exported assets. --core-only leaves the extension untouched.

Always preserve user-owned placement files and the original Showhome.
"""
from pathlib import Path
import json,os,shutil,hashlib,sys
from PIL import Image
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))
from gltf_shared import read,save
DEST=ROOT/'game/assets/maps/showhome_v3';ASSETS=ROOT/'game/assets'
PIXEL_IMAGES={}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def sampled_image(p):
    # Exporter PNG recompression must not produce another engine texture for identical pixels.
    with Image.open(p) as im:key=hashlib.sha256(str(im.size).encode()+im.convert('RGBA').tobytes()).hexdigest()
    if key in PIXEL_IMAGES:return PIXEL_IMAGES[key]
    target=DEST/'textures'/(digest(p)[:24]+p.suffix);target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():shutil.copy2(p,target)
    PIXEL_IMAGES[key]=target;return target
def stage_glb(src,dest):
    j,buf=read(src);dest.parent.mkdir(parents=True,exist_ok=True)
    for im in j.get('images',[]):
        p=(src.parent/im['uri']).resolve();target=sampled_image(p)
        im['uri']=os.path.relpath(target,dest.parent).replace('\\','/')
    for m in j.get('materials',[]):
        e=m.get('extras',{})
        for key in ('height_source','height_map'):
            if key not in e:continue
            p=Path(e[key]);p=p if p.is_absolute() else ROOT/p
            if p.exists():
                target=DEST/'height'/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);e[key]=str(target.relative_to(ASSETS)).replace('\\','/')
    save(dest,j,buf)
def stage_extension_ground(extension,extension_dest):
    path=extension/'ground_blend_contract.json'
    if not path.exists():return
    contract=json.loads(path.read_text(encoding='utf8'));j,buf=read(extension_dest/'extension.glb')
    used={m['name'] for m in j.get('materials',[]) if 'showhome_ground_blend' in m.get('extras',{})}
    contract['materials']={k:v for k,v in contract['materials'].items() if k in used}
    source=json.loads((ROOT/'assets/maps/showhome/textures/v2/manifest.json').read_text(encoding='utf8'))['materials'];families=set()
    for row in contract['materials'].values():families.add(row['base_texture']);families.update(c['texture'] for c in row['channels'].values())
    table={}
    for family in sorted(families):
        record=dict(source[family]);maps={}
        for kind,name in record['maps'].items():
            src=ROOT/'assets/maps/showhome/textures/v2'/name
            if kind=='height':
                target=DEST/'height'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
            else:target=sampled_image(src)
            maps[kind]=str(target.relative_to(ASSETS)).replace('\\','/')
        record['maps']=maps;table[family]=record
    contract_path='maps/showhome_v3/extension/ground_blend_contract.json'
    for row in contract['materials'].values():
        row['base_maps']=table[row['base_texture']]['maps'];row['contract']=contract_path
        for c in row['channels'].values():c['maps']=table[c['texture']]['maps']
    contract['maps_root']='maps/showhome_v3';contract['sampled_textures']=table;contract['macro_maps']={'ground':'maps/showhome_v3/textures/macro_ground.png','walls':'maps/showhome_v3/textures/macro_walls.png'}
    for m in j['materials']:
        if m['name'] in contract['materials']:m['extras']['showhome_ground_blend']=json.dumps(contract['materials'][m['name']])
    save(extension_dest/'extension.glb',j,buf);(extension_dest/'ground_blend_contract.json').write_text(json.dumps(contract,indent=2)+'\n',encoding='utf8')

def main():
    assert (HERE/'phase1_report.json').exists(),'Build and verify core first'
    DEST.mkdir(parents=True,exist_ok=True)
    for name in ('houses.glb','ground.glb'):stage_glb(HERE/'kit'/name,DEST/name)
    for name in ('collision.json','layout.json','ground_blend_contract.json','phase1_report.json','NOTES.md','QA.json'):
        shutil.copy2(HERE/name,DEST/name)
    for name in ('ground_steps.json','foliage.json'):shutil.copy2(HERE/'kit'/name,DEST/name)
    source=json.loads((ROOT/'assets/props/catalog.json').read_text());ids={r['prop_id'] for r in json.loads((HERE/'placements.generated.json').read_text())['instances']}
    # Ship the whole reusable first container batch, including unplaced examples.
    chosen=[r for r in source['props'] if 'showhome_v3' in r.get('tags',[]) or r['id'] in ids]
    for r in chosen:
        for key in ('glb','lod1'):stage_glb(ROOT/'assets'/r[key],ASSETS/r[key])
        p=ROOT/'assets'/r['collision'];target=ASSETS/r['collision'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        meta=p.parent/'metadata.json';shutil.copy2(meta,target.parent/'metadata.json')
    # The custom ground shader samples overlays/macro maps that are not PBR GLB slots.
    ground,_=read(DEST/'ground.glb');used={m['name'] for m in ground['materials'] if 'showhome_ground_blend' in m.get('extras',{})}
    contract=json.loads((HERE/'ground_blend_contract.json').read_text());contract['materials']={k:v for k,v in contract['materials'].items() if k in used}
    manifest=json.loads((ROOT/'assets/maps/showhome/textures/v2/manifest.json').read_text())['materials'];families=set()
    for mat in contract['materials'].values():families.add(mat['base_texture']);families.update(c['texture'] for c in mat['channels'].values())
    texture_table={}
    for family in sorted(families):
        record=dict(manifest[family]);maps={}
        for kind,name in record['maps'].items():
            p=ROOT/'assets/maps/showhome/textures/v2'/name
            if kind=='height':
                target=DEST/'height'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
            else:target=sampled_image(p)
            maps[kind]=str(target.relative_to(ASSETS)).replace('\\','/')
        record['maps']=maps;texture_table[family]=record
    for mat in contract['materials'].values():
        mat['base_maps']=texture_table[mat['base_texture']]['maps']
        mat['contract']='maps/showhome_v3/ground_blend_contract.json'
        for channel in mat['channels'].values():channel['maps']=texture_table[channel['texture']]['maps']
    for name in ('macro_ground.png','macro_walls.png'):
        target=DEST/'textures'/name;shutil.copy2(ROOT/'assets/maps/showhome/textures/v2'/name,target)
    contract['maps_root']='maps/showhome_v3';contract['sampled_textures']=texture_table;contract['macro_maps']={'ground':'maps/showhome_v3/textures/macro_ground.png','walls':'maps/showhome_v3/textures/macro_walls.png'}
    (DEST/'ground_blend_contract.json').write_text(json.dumps(contract,indent=2)+'\n',encoding='utf8')
    for mat in ground['materials']:
        if mat['name'] in contract['materials']:mat['extras']['showhome_ground_blend']=json.dumps(contract['materials'][mat['name']])
    _,groundbuf=read(DEST/'ground.glb');save(DEST/'ground.glb',ground,groundbuf)
    catpath=ASSETS/'props/catalog.json';current=json.loads(catpath.read_text()) if catpath.exists() else {'schema':1,'props':[]}
    current['props']=[r for r in current.get('props',[]) if r['id'] not in {r['id'] for r in chosen}]+chosen
    catpath.parent.mkdir(parents=True,exist_ok=True);catpath.write_text(json.dumps(current,indent=2)+'\n',encoding='utf8')
    target=DEST/'placements.ron'
    if not target.exists():shutil.copy2(HERE/'placements.ron',target)
    shutil.copy2(HERE/'placements.proposed.ron',DEST/'placements.proposed.ron')
    shutil.copy2(HERE/'placements.generated.json',DEST/'placements.reference.json')
    sky=ROOT/'assets/maps/showhome/backdrop/sky';sd=DEST/'sky';sd.mkdir(exist_ok=True)
    for p in sky.glob('sky_*.png'):
        if p.name!='sky_compare.png':shutil.copy2(p,sd/p.name)
    shutil.copy2(sky/'PROMPT.md',sd/'PROMPT.md')
    manifest=dict(map_id='showhome_v3',phase=1,frame='design world metres, Bevy=(x,z,-y)',tdm_scene_offset_bevy=[-330,0,620],kit_scenes=['houses.glb','ground.glb'],collision='collision.json',foliage='foliage.json',placements='placements.ron',catalog='props/catalog.json',runtime_integration='pending game build-mode and penetration loader',props=[r['id'] for r in chosen],sun={'azimuth_deg':188,'elevation_deg':54,'linear_rgb':[1,.84,.66]},fog={'start_m':80,'end_m':420,'srgb':[.66,.76,.86]})
    extension=HERE/'extension';extension_dest=DEST/'extension'
    if '--core-only' not in sys.argv and (extension/'extension.glb').exists():
        assert json.loads((extension/'QA.json').read_text(encoding='utf8'))['passed'],'Extension QA must pass before deploy'
        stage_glb(extension/'extension.glb',extension_dest/'extension.glb')
        stage_extension_ground(extension,extension_dest)
        for name in ('collision.json','foliage.json','report.json','QA.json','serialized_QA.json','parking_report.json','stairs_route.json','NOTES.md','manifest.json'):
            if (extension/name).exists():shutil.copy2(extension/name,extension_dest/name)
        for src,dst in (('placements.generated.json','placements.reference.json'),('placements.proposed.ron','placements.proposed.ron')):
            if (extension/src).exists():shutil.copy2(extension/src,extension_dest/dst)
        if not (extension_dest/'placements.ron').exists():
            shutil.copy2(extension/'placements.proposed.ron',extension_dest/'placements.ron')
        manifest['extension']={'kit_scenes':['extension/extension.glb'],'collision':'extension/collision.json','foliage':'extension/foliage.json','placements':'extension/placements.ron','latest_placements_proposal':'extension/placements.proposed.ron','mode':'extraction'}
    manifest['core_bounds_design']=[330,620,410,685]
    manifest['tdm_play_bounds_design']=json.loads((HERE/'layout.json').read_text(encoding='utf8')).get('tdm_play_bounds_design',[330,620,410,685])
    manifest['latest_placements_proposal']='placements.proposed.ron';manifest['existing_user_placements_preserved']=True
    (DEST/'map_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    (HERE/'HANDOFF.json').write_text(json.dumps(dict(phase=1,staged=str(DEST),placements_sha256=digest(target),user_owns_placements=True),indent=2)+'\n',encoding='utf8')
    print('STAGED',DEST,len(chosen),'props; existing placements preserved')
if __name__=='__main__':main()
