"""Render final assembled collision by physical material; never save/change the source .blend."""
import json,sys
from pathlib import Path
import bpy
from mathutils import Vector
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import common as C
PALETTE={
 'glass':(.22,.82,.90),'wood_thin':(.74,.44,.18),'wood_thick':(.36,.18,.055),
 'sheet_metal':(.75,.80,.87),'metal_heavy':(.16,.22,.29),'drywall':(.96,.72,.42),
 'concrete':(.50,.53,.56),'brick':(.67,.18,.12),'cladding':(.43,.29,.70),
 'foliage_thin':(.40,.80,.24),'foliage_dense':(.09,.36,.12),'fabric':(.83,.21,.63),
 'plastic':(.97,.76,.13),'soil':(.32,.23,.14),'grass':(.19,.48,.13),
 'gravel':(.62,.56,.41),'sand':(.91,.77,.47),'asphalt':(.10,.11,.13),
 'paving':(.73,.71,.65),'water':(.10,.42,.83),
}
def main():
    mats={};counts={}
    for name,rgb in PALETTE.items():
        mat=bpy.data.materials.new('DEBUG_PHYS_'+name);mat.diffuse_color=(*rgb,1);mat.use_nodes=True;p=mat.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*rgb,1);p.inputs['Roughness'].default_value=.8;mat['phys']=name;mats[name]=mat
    for coll in bpy.data.collections:coll.hide_render=False
    for ob in bpy.context.scene.objects:
        if ob.type!='MESH':continue
        if ob.name.startswith('COL_'):
            phys=ob.get('phys');assert phys in mats,(ob.name,phys);ob.hide_render=False;ob.hide_set(False);ob.display_type='SOLID';ob.data.materials.clear();ob.data.materials.append(mats[phys]);counts[phys]=counts.get(phys,0)+1
        else:ob.hide_render=True
    camera=C.stage();sc=bpy.context.scene;sc.cycles.samples=8;sc.render.resolution_x=1440;sc.render.resolution_y=900
    outputs=[]
    for name,eye,target,ortho in [('aerial',(421,600,62),(370,644,2),112),('street_south',(370,616,2.0),(362,635,2.4),None),('street_north',(370,678,2.0),(370,639,2.5),None)]:
        path=HERE/'renders'/('material_debug_'+name+'.png');C.render(camera,path,eye,target,ortho);outputs.append(str(path));print('DEBUG_READY',name,flush=True)
    (HERE/'renders/material_debug_legend.json').write_text(json.dumps(dict(palette_linear_RGB=PALETTE,collision_counts=counts,renders=outputs,source_scene_unchanged=True),indent=2)+'\n',encoding='utf8')
if __name__=='__main__':main()
