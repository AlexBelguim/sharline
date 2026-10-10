"""Scan every exported ATT_*.glb for triangles whose winding (geometric normal) disagrees with the exported vertex
normals by > 120 deg (= flipped winding: culled in-engine with single-sided materials, black in Cycles), and for
zero-area triangles. Writes review/v2/v2_flip_scan.json."""
import bpy, math, os, json
from mathutils import Vector
HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
PARTS = ["grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "bipod", "laser_R", "laser_L",
         "flashlight_R", "flashlight_L", "shield_front"]
out = {}
for pid in PARTS:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(HERE, f"ATT_{pid}.glb"))
    res = {}
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        me = o.data
        cn = [Vector(c.vector) for c in me.corner_normals]
        flipped, zero = [], 0
        for p in me.polygons:
            if p.area < 1e-10:
                zero += 1
                continue
            avg = Vector((0, 0, 0))
            for li in p.loop_indices:
                avg += cn[li]
            if avg.length < 1e-9:
                continue
            ang = math.degrees(avg.angle(p.normal))
            if ang > 120:
                flipped.append({"poly": p.index, "center": [round(v, 4) for v in p.center],
                                "area_mm2": round(p.area * 1e6, 2), "mat": me.materials[p.material_index].name,
                                "angle": round(ang, 1)})
        res[o.name] = {"flipped": len(flipped), "flipped_area_mm2": round(sum(f["area_mm2"] for f in flipped), 2),
                       "zero_area": zero, "samples": flipped[:6]}
    out[pid] = res
    print("SCAN", pid, {k: (v["flipped"], v["flipped_area_mm2"], v["zero_area"]) for k, v in res.items()})
with open(os.path.join(HERE, "review", "v2", "v2_flip_scan.json"), "w") as fh:
    json.dump(out, fh, indent=1)
