"""For each flipped triangle found by v2_flip_scan: is it a hidden coplanar duplicate (another triangle with the
correct winding covers the same spot) or a real wrongly-wound piece of the surface (=> hole when culled)?"""
import bpy, os, json
from mathutils import Vector
from mathutils.geometry import intersect_point_tri
HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
scan = json.load(open(os.path.join(HERE, "review", "v2", "v2_flip_scan.json")))
out = {}
for pid, objs in scan.items():
    for oname, r in objs.items():
        if not r["flipped"]:
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.join(HERE, f"ATT_{pid}.glb"))
        o = bpy.data.objects[oname]
        me = o.data
        me.calc_loop_triangles()
        for s in r["samples"]:
            p = me.polygons[s["poly"]]
            pts = [p.center.lerp(me.vertices[v].co, t) for v in p.vertices for t in (0.3, 0.6)] + [p.center]
            cover = []
            for q in me.polygons:
                if q.index == p.index:
                    continue
                if abs((q.center - p.center).dot(p.normal)) > 2e-5 or abs(abs(q.normal.dot(p.normal)) - 1) > 1e-3:
                    continue
                vs = [me.vertices[v].co for v in q.vertices]
                hit = sum(1 for pt in pts if any(intersect_point_tri(pt, vs[0], vs[i], vs[i + 1]) for i in range(1, len(vs) - 1)))
                if hit:
                    cover.append({"poly": q.index, "same_dir": q.normal.dot(p.normal) > 0, "pts_covered": hit,
                                  "area_mm2": round(q.area * 1e6, 2)})
            key = f"{pid}/{oname}/{s['poly']}"
            out[key] = {"area_mm2": s["area_mm2"], "sample_pts": len(pts), "coplanar_covering": cover}
            print("DUP", key, s["area_mm2"], cover[:6])
json.dump(out, open(os.path.join(HERE, "review", "v2", "v2_dup_probe.json"), "w"), indent=1)
