"""Round-2 reviewer: precise gap between reticle/glint decals and the glass / lens they sit on (read-only)."""
import os, json
import bpy, bmesh
from mathutils.bvhtree import BVHTree
OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
res = {}
for oid, pairs in (("optic_reddot", [("Reticle", "Glass"), ("Glint", "Glass")]),
                   ("optic_holo", [("Reticle", "Glass"), ("Glint", "Glass")]),
                   ("optic_3x", [("Reticle", "Ocular")])):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(OUT, "ATT_%s.glb" % oid))
    for a, b in pairs:
        oa = bpy.data.objects["ATT_%s_%s" % (oid, a)]
        ob = bpy.data.objects["ATT_%s_%s" % (oid, b)]
        bm = bmesh.new(); bm.from_mesh(ob.data); bm.transform(ob.matrix_world)
        t = BVHTree.FromBMesh(bm)
        ds = []
        for v in oa.data.vertices:
            p = oa.matrix_world @ v.co
            loc, n, i, d = t.find_nearest(p)
            ds.append(d)
        res["%s %s->%s" % (oid, a, b)] = [round(min(ds) * 1e6, 1), round(max(ds) * 1e6, 1)]
print(json.dumps(res, indent=1))
json.dump(res, open(os.path.join(OUT, "review", "round2", "decal_gap_r2.json"), "w"), indent=1)
