"""Preview only: replaces hair in the saved character without main exports."""
import sys
from pathlib import Path
import bpy

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT/'tools'))
sys.path.insert(0, str(ROOT/'assets/characters/_shared'))
sys.path.insert(0, str(OUT))
import blender_common as bc
import kestrel_hair

bpy.ops.wm.open_mainfile(filepath=str(OUT/'kestrel.blend'))
scene = bpy.context.scene
scene.frame_set(1)
arm = next(o for o in scene.objects if o.type == 'ARMATURE' and o.name.startswith('KES_'))
arm.animation_data_clear()
for bone in arm.pose.bones:
    bone.rotation_mode='QUATERNION'
    bone.rotation_quaternion=(1,0,0,0)
    bone.location=(0,0,0)
    bone.scale=(1,1,1)
for ob in list(scene.objects):
    if ob.name.startswith('KES_Hair'):
        bpy.data.objects.remove(ob, do_unlink=True)
    elif ob.type == 'MESH' and (ob.name.startswith('_') or not ob.name.startswith('KES_')):
        ob.hide_render=True
parts = kestrel_hair.build({'armature':arm})
for ob in parts:
    ob.data.calc_loop_triangles()
    print('HAIR_FINISH',ob.name,len(ob.data.vertices),len(ob.data.loop_triangles))
bc.setup_studio(bg=(.16,.165,.18),strength=.72,floor=False)
bc.VIEW_DIRS.update(front=(0,-1,.025),three_quarter=(.56,-1,.09),right=(1,0,.04),left=(-1,0,.04),back=(0,1,.04))
paths=bc.render_views(str(OUT/'renders'),'hair_finish',views=('front','three_quarter','right','left','back'),res=(900,900),engine='CYCLES',samples=32,ortho=True,focus=((0,0,1.593),.177),margin=1.12)
bc.contact_sheet(paths,str(OUT/'renders/hair_finish_sheet.png'),cols=3)
