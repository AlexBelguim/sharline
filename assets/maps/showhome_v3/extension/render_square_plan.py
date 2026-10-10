"""Square overview of the actual saved construction site."""
import sys
from pathlib import Path
import bpy
HERE=Path(__file__).resolve().parent;sys.path[:0]=[str(HERE),str(HERE.parent)]
import common as C
bpy.ops.wm.open_mainfile(filepath=str(HERE/'extension.blend'),load_ui=False,use_scripts=False)
cam=C.stage();bpy.context.scene.cycles.samples=12
bpy.context.scene.render.resolution_x=1024;bpy.context.scene.render.resolution_y=1024
C.render(cam,HERE/'renders/site_plan.png',(380.5,791.5,220),(380.5,791.5,0),164)
