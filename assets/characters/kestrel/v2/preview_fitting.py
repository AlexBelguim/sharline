"""Check the posed Rain reference against existing wardrobe, without main exports."""
from pathlib import Path
import sys,importlib.util,json
import bpy
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'assets/characters/_shared'));sys.path.insert(0,str(OUT))
import blender_common as bc
import character_v2 as cv
import rain_anatomy
spec=importlib.util.spec_from_file_location('kes_fit_builder',OUT/'build_kestrel.py');k=importlib.util.module_from_spec(spec);spec.loader.exec_module(k)
bc.reset_scene()
k.BASE=cv.build_base(prefix='KES',height=1.70,skin=(.62,.42,.33),eye_color=(.13,.065,.032))
k.make_materials();k.make_clothes();k.make_gear()
ref=rain_anatomy.fitting_body(k.BASE)
adjustments=rain_anatomy.fit_garments(k.OWN,ref,k.BASE)
(OUT/'fitting_adjustments.json').write_text(json.dumps(adjustments,indent=2))
bc.uv_all(k.OWN)
ref.hide_render=False
for ob in k.BASE['parts']:ob.hide_render=True
for ob in k.OWN:ob.hide_render=True
bc.setup_studio(bg=(.18,.185,.20),strength=.7,floor=True)
bpy.data.objects['_Floor'].scale=(4,4,4)
bc.render_views(str(OUT/'renders'),'fitting_body', [ref],views=('front','three_quarter'),res=(900,1100),engine='EEVEE',samples=24,ortho=True,focus=((0,0,.89),.91))
ref.hide_render=True
for ob in k.BASE['parts']+k.OWN:ob.hide_render=False
bc.render_views(str(OUT/'renders'),'fitting_outfit',k.BASE['parts']+k.OWN,views=('front','three_quarter'),res=(900,1100),engine='EEVEE',samples=24,ortho=True,focus=((0,0,.89),.91))
print('FITTING_READY',sum(r['vertices_adjusted']for r in adjustments),flush=True)
