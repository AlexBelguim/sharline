"""Look development from the actual exported scenes, with the game's frame/light/fog."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import bpy

HERE=Path(__file__).resolve().parent
SH=HERE.parent
ROOT=SH.parents[2]
sys.path.insert(0,str(SH))
import lookdev_common as LD
import ground_blend as GB

VIEWS={
    'spawn_w_east':((4.5,19.5,1.6),(40,24,2.3),20),
    'spawn_w_west':((4.5,19.5,1.6),(-24,22,3),24),
    'spawn_e_west':((67.5,19.5,1.6),(30,24,2.3),20),
    'spawn_e_east':((67.5,19.5,1.6),(96,22,3),24),
    'upper_north':((18,31.8,4.8),(22,94,5),24),
    'upper_south':((18,22.2,4.8),(18,-55,5),24),
    'upper_east':((20.8,24.2,4.8),(108,32,5),20),
    'upper_west':((9.2,26.8,4.8),(-64,26,5),24),
    'jetpack_centre':((36,24,9.5),(84,100,6),20),
    'aerial_s11':((36,-26,40),(36,25,0),30),
    'aerial_s12':((4,-16,30),(40,28,0),28),
}


def main():
    args=sys.argv[sys.argv.index('--')+1:]if '--'in sys.argv else[]
    views=args[args.index('--views')+1].split(',')if '--views'in args else list(VIEWS)
    out=HERE/'renders';out.mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    hashes={}
    for path in [SH/'kit/houses.glb',SH/'kit/ground.glb',SH/'kit/props_placed.glb',HERE/'backdrop.glb']:
        if not path.exists():raise FileNotFoundError(path)
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        bpy.ops.import_scene.gltf(filepath=str(path))
    GB.install_preview()
    for ob in bpy.context.scene.objects:
        if ob.type=='MESH' and ob.name.startswith('SHB_Far'):
            ob.visible_shadow=False
    cam,sun=LD.setup(quick='--quick'in args,sky=str(HERE/'sky/sky_equirect.png'),fog=True)
    for name in views:
        pos,target,lens=VIEWS[name]
        LD.render(cam,out/f'{name}.png',pos,target,lens=lens,resolution=(1280,720))
    (out/'manifest.json').write_text(json.dumps(dict(views=VIEWS,source_sha256=hashes,
        sun_compass_azimuth=188,sun_elevation=54,sun_linear=[1,.84,.66],sun_energy=2.5,
        world_strength=.65,fog_start=80,fog_end=420,fog_srgb=[.66,.76,.86],
        device=bpy.context.scene.cycles.device),indent=2)+'\n',encoding='utf8')
    subprocess.run(['python',str(HERE/'compare_backdrop.py')],check=True)


if __name__=='__main__':main()
