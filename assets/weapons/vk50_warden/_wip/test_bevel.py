import sys, math
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc
import bpy, bmesh
from mathutils import Vector

bc.reset_scene()
G = bc.material("M_G", (0.030, 0.033, 0.040), rough=0.55, metal=0.15)
S = bc.material("M_S", (0.36, 0.28, 0.18), rough=0.70)

def finish(obj, width, segs, harden=True, angle=30):
    for p in obj.data.polygons: p.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(angle))
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width; m.segments = segs; m.limit_method = "ANGLE"; m.angle_limit = math.radians(angle)
    m.harden_normals = harden
    m.miter_outer = "MITER_ARC"
    bc.apply_modifiers(obj)
    print(obj.name, "custom normals:", obj.data.has_custom_normals)

for i, (segs, harden) in enumerate([(1, False), (1, True), (3, False), (3, True)]):
    b = bc.box(f"B{i}", (0.07, 0.3, 0.09), loc=(0, i * 0.4, 0), smooth=None, mat=G if segs == 1 else S)
    c = bc.box("_c", (0.2, 0.05, 0.02), loc=(0, i * 0.4, 0.0))
    bc.add_bevel(c, 0.0099, 4); bc.apply_modifiers(c)
    bc.boolean(b, c)
    finish(b, 0.006 if segs == 1 else 0.01, segs, harden)

bc.setup_studio(bg=(0.55, 0.56, 0.58))
bc.render_views(r"F:/git/val etf/assets/weapons/vk50_warden/_wip", "tb", views=("three_quarter",), engine="CYCLES", samples=32, res=(1000, 700), focus=((0,0.6,0),0.4))
