"""User-marked road and garden details, from the assembled scene."""
import sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
import common as C
bpy.ops.wm.open_mainfile(filepath=str(C.HERE/'showhome_v3.blend'),load_ui=False,use_scripts=False)
cam=C.stage();bpy.context.scene.cycles.samples=16
for name,eye,target,ortho in [
    ('road_barriers',(337,677,1.6),(331.5,677,1.0),None),
    ('blue_car',(366,636,1.6),(370,641,1.0),None),
    ('garden_separators',(402,627,1.6),(390,633,1.5),None),
    ('roadside_gardens',(426,620,72),(370,650,2),124)
]:C.render(cam,C.HERE/('renders/'+name+'.png'),eye,target,ortho)
