"""Trace non-manifold edges after every boolean / finish on chosen objects (debug)."""
import os, runpy, sys
import bmesh, bpy
sys.argv = [sys.argv[0], "--", "--no-export", "--no-det-check", "--no-gate"]
ns = runpy.run_path(r"F:/git/val etf/assets/weapons/vk50_warden/build_warden.py", run_name="warden_defs")
G = ns["build_all"].__globals__
WATCH = tuple(os.environ.get("WATCH", "_frame,_mbody").split(","))

def nm(o):
    bm = bmesh.new(); bm.from_mesh(o.data)
    r = [e for e in bm.edges if not e.is_manifold]
    out = (len(r), [tuple(round(c, 4) for c in (e.verts[0].co + e.verts[1].co) / 2) for e in r[:2]])
    bm.free()
    return out

for fn in ("boolean", "finish", "finish_outer", "seal", "tri_clean", "degen", "flat_big_faces"):
    orig = G[fn]
    def wrap(obj, *a, _orig=orig, _fn=fn, **k):
        name = obj.name
        cname = a[0].name if _fn == "boolean" and hasattr(a[0], "name") else ""
        r = _orig(obj, *a, **k)
        if name.startswith(WATCH):
            print("NM", name, _fn, cname, nm(obj))
        return r
    G[fn] = wrap
G["build_all"]()
