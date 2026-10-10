"""Attach authored work lamps as standard KHR punctual nodes; mesh buffer untouched."""
import sys,math,json
from pathlib import Path
import bpy
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent))
from gltf_shared import read,save
bpy.ops.wm.open_mainfile(filepath=str(HERE/'extension.blend'),load_ui=False,use_scripts=False)
j,buf=read(HERE/'extension.glb')
if j.get('extensions',{}).get('KHR_lights_punctual',{}).get('lights'):raise RuntimeError('Lights already exported; repair not needed')
lamps=sorted([o for o in bpy.context.scene.objects if o.type=='LIGHT' and o.name.startswith('EXT_ParkingWorkLamp')],key=lambda o:o.name)
values=[]
for index,o in enumerate(lamps):
    light=o.data;energy=light.energy
    if not light.normalize:energy*=light.area(matrix_world=o.matrix_world)
    intensity=energy/(4*math.pi)*683*(2**light.exposure)
    values.append({'name':o.name,'type':'point','color':list(light.color),'intensity':intensity})
    p=o.matrix_world.translation;node={'name':o.name,'translation':[p.x,p.z,-p.y],'extensions':{'KHR_lights_punctual':{'light':index}},'extras':{'part':'parking_basement/lights','source':'authored work lamp; Blender SPEC photometric conversion'}}
    j['scenes'][j.get('scene',0)]['nodes'].append(len(j['nodes']));j['nodes'].append(node)
j.setdefault('extensions',{})['KHR_lights_punctual']={'lights':values}
j.setdefault('extensionsUsed',[]).append('KHR_lights_punctual')
save(HERE/'extension.glb',j,buf)
print('LIGHTS_REPAIRED',len(values),values[0]['intensity'],flush=True)
