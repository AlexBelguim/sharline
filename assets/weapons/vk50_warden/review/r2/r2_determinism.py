"""Round-2: compare per-mesh triangle counts + handguard open edges between the shipped warden_base.glb and a
from-scratch rebuild (made by a copy of build_warden.py whose OUT points to a scratch folder; the asset is untouched).
Usage: blender -b --factory-startup -P r2_determinism.py -- <rebuild_dir>"""
import bpy, bmesh, os, sys
D = r"F:/git/val etf/assets/weapons/vk50_warden"
RB = sys.argv[sys.argv.index("--") + 1]
def load(p):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=p)
    out = {}
    for o in bpy.data.objects:
        if o.type != "MESH": continue
        bm = bmesh.new(); bm.from_mesh(o.data); bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        out[o.name] = (sum(len(p.vertices) - 2 for p in o.data.polygons), sum(1 for e in bm.edges if e.is_boundary))
        bm.free()
    return out
a = load(os.path.join(D, "warden_base.glb")); b = load(os.path.join(RB, "warden_base.glb"))
for k in sorted(set(a) | set(b)):
    flag = "" if a.get(k) == b.get(k) else "   <-- DIFFERS"
    print(f"DET {k:28s} shipped tris/open {a.get(k)}  rebuild {b.get(k)}{flag}")
