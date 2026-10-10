"""Final presentation views from the actual assembled saved scene, no scene changes saved."""
import sys,json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent));import common as C
def main():
    bpy.ops.wm.open_mainfile(filepath=str(C.HERE/'showhome_v3.blend'),load_ui=False,use_scripts=False)
    layout=json.loads((C.HERE/'layout.json').read_text(encoding='utf8'));road=layout['front_street'][1]
    cam=C.stage();bpy.context.scene.cycles.samples=20
    for name,eye,target,ortho in [('street',(370,road+4,1.6),(370,647,3),None),('upper_garden',(344.2,649,1.6),(347,653,1.5),None),('front_garden',(365.8,634,1.6),(357,641,2.4),None),('terrace',(355,660,4.8),(363,644,4.2),None),('rear_windows',(343.5,645,4.8),(350.35,645,3.1),None)]:C.render(cam,C.HERE/('renders/'+name+'.png'),eye,target,ortho)
if __name__=='__main__':main()
