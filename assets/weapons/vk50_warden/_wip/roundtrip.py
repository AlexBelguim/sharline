"""Round-trip check: import warden_default.glb into an empty scene, report rail dimensions, render it."""
import sys
sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc
import bpy
from mathutils import Vector
OUT = r"F:/git/val etf/assets/weapons/vk50_warden"
bc.reset_scene()
bpy.ops.import_scene.gltf(filepath=OUT + "/warden_default.glb")
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
print("RT meshes", len(meshes), "tris", sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in meshes))
rt = bpy.data.objects["WARDEN_RailTop"]
ws = [rt.matrix_world @ v.co for v in rt.data.vertices]
xs = [w.x for w in ws]; zs = [w.z for w in ws]
print("RT railtop x", round(min(xs), 4), round(max(xs), 4), "z", round(min(zs), 4), round(max(zs), 4))
for nm in ("WARDEN_SOCKET_Optic", "WARDEN_SOCKET_Under", "WARDEN_SOCKET_Side_R", "WARDEN_SOCKET_Side_L",
           "WARDEN_SOCKET_Mag", "WARDEN_SOCKET_Stock", "WARDEN_Bolt", "WARDEN_StockStandard", "WARDEN_Mag5"):
    o = bpy.data.objects[nm]
    print("RT", nm, tuple(round(c, 4) for c in o.matrix_world.translation))
rb = bpy.data.objects["WARDEN_RailBottom"]
zb = [(rb.matrix_world @ v.co).z for v in rb.data.vertices]
print("RT railbottom z", round(min(zb), 4), round(max(zb), 4))
for nm in ("WARDEN_RailSide_R", "WARDEN_RailSide_L"):
    o = bpy.data.objects[nm]
    xx = [(o.matrix_world @ v.co).x for v in o.data.vertices]
    print("RT", nm, "x", round(min(xx), 4), round(max(xx), 4))
bc.setup_studio(bg=(0.24, 0.25, 0.27))
bpy.context.scene.view_settings.exposure = -0.2
try:
    bpy.context.scene.view_settings.look = "AgX - Punchy"
except TypeError:
    pass
bc.render_views(OUT + "/_wip", "roundtrip", objs=meshes, views=("three_quarter",), res=(1400, 700),
                engine="CYCLES", samples=32, margin=0.9)
