"""Probe the laser_R top face (black diagonal sliver in renders/laser_R/laser_R_top.png)."""
import bpy, math, os, sys, json
from mathutils import Vector
HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
for f in ("ATT_laser_R.glb", "ATT_laser_L.glb"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(HERE, f))
    body = next(o for o in bpy.data.objects if o.parent is None and o.type == "MESH")
    me = body.data
    cn = [Vector(c.vector) for c in me.corner_normals]
    print("FILE", f, "polys", len(me.polygons))
    rows = []
    for p in me.polygons:
        c = p.center
        if c.z > 0.0155 and abs(c.x) > 0.004 and abs(c.x) < 0.0365 and -0.034 < c.y < 0.026:
            devs = [round(math.degrees(cn[li].angle(p.normal)), 1) for li in p.loop_indices]
            rows.append((p.index, [round(v, 4) for v in c], [round(v, 3) for v in p.normal], round(p.area * 1e6, 3), devs,
                         p.material_index))
    for r in sorted(rows, key=lambda r: -max(r[4])):
        print("TOP", r)
