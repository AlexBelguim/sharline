"""Round-2: measure cheek-riser posts (gunmetal faces of the riser mesh), riser pad extent, bolt-knob and shroud-cap
geometry from the exported warden_default.glb."""
import bpy, os
from mathutils import Vector
D = r"F:/git/val etf/assets/weapons/vk50_warden"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(D, "warden_default.glb"))
r = bpy.data.objects["WARDEN_StockStandard_CheekRiser"]; mw = r.matrix_world
mats = [m.name for m in r.data.materials]
for mi, mn in enumerate(mats):
    vs = {v for p in r.data.polygons if p.material_index == mi for v in p.vertices}
    pts = [mw @ r.data.vertices[i].co for i in vs]
    ys = sorted({round(p.y, 3) for p in pts})
    print("RISER", mn, "x", round(min(p.x for p in pts),4), round(max(p.x for p in pts),4), "y", round(min(p.y for p in pts),4), round(max(p.y for p in pts),4),
          "z", round(min(p.z for p in pts),4), round(max(p.z for p in pts),4), "distinct y (first/last 6)", ys[:6], ys[-6:])
b = bpy.data.objects["WARDEN_Bolt"]; mw = b.matrix_world
pts = [mw @ v.co for v in b.data.vertices]
cap = [p for p in pts if p.y > 0.112 and abs(p.x) < 0.03]
print("SHROUD rear region y>0.112 |x|<0.03:", len(cap), "y max", round(max(p.y for p in cap),4) if cap else None)
kn = [p for p in pts if p.x < -0.068]
print("KNOB verts", len(kn), "tris of bolt", sum(len(p.vertices)-2 for p in b.data.polygons))
