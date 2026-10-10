"""Street-eye inspection of the painted spoil heap and excavation bank."""
import sys
from pathlib import Path
import bpy
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent)]
import common as C
bpy.ops.wm.open_mainfile(filepath=str(HERE/'extension.blend'),load_ui=False,use_scripts=False)
cam=C.stage();bpy.context.scene.cycles.samples=16
C.render(cam,HERE/'renders/earthworks_street.png',(430,732,1.608),(424,740,1.1),None)
