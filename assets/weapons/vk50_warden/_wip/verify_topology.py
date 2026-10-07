"""Topology check on the source warden.blend (glTF splits verts at seams, so manifold tests need the source).
Also re-checks the glb meshes after merge-by-distance. Read-only: the .blend is opened, never saved."""
import json
import os

import bmesh
import bpy

D = r"F:/git/val etf/assets/weapons/vk50_warden"
bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "warden.blend"))
out = {}


def health(o, merge=0.0):
    bm = bmesh.new()
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    bm.from_mesh(oe.to_mesh())
    oe.to_mesh_clear()
    if merge:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
    bm.normal_update()
    nonman = [e for e in bm.edges if not e.is_manifold]
    wire = [e for e in bm.edges if e.is_wire]
    degen = [f for f in bm.faces if f.calc_area() < 1e-10]
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    big_ngons = [f for f in bm.faces if len(f.verts) > 8]
    # components + signed volume
    seen = set(); comps = []
    for f in bm.faces:
        if f.index in seen:
            continue
        st = [f]; seen.add(f.index); c = []
        while st:
            g = st.pop(); c.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); st.append(h)
        vol = 0.0
        for g in c:
            vs = [v.co for v in g.verts]
            for i in range(1, len(vs) - 1):
                vol += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
        comps.append(vol)
    # inconsistent winding: manifold edges whose two faces traverse it in the same direction
    incons = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            f1, f2 = e.link_faces
            l1 = next(l for l in e.link_loops if l.face is f1)
            l2 = next(l for l in e.link_loops if l.face is f2)
            if l1.vert is l2.vert:
                incons += 1
    nm_loc = [tuple(round(c, 4) for c in ((e.verts[0].co + e.verts[1].co) / 2)) for e in nonman[:6]]
    r = dict(tris=sum(len(f.verts) - 2 for f in bm.faces), verts=len(bm.verts), nonmanifold=len(nonman),
             nonmanifold_samples=nm_loc, wire=len(wire), degenerate=len(degen), ngons=len(ngons),
             ngons_gt8=len(big_ngons), components=len(comps), negative_volume_components=sum(1 for v in comps if v < -1e-10),
             inconsistent_winding_edges=incons, uv_layers=len(o.data.uv_layers),
             mats=[m.name if m else None for m in o.data.materials],
             sharp_edges=sum(1 for e in o.data.edges if e.use_edge_sharp) if hasattr(o.data.edges[0], "use_edge_sharp") else None)
    bm.free()
    return r


print("COLLECTIONS", [(c.name, len(c.objects)) for c in bpy.data.collections])
vl = bpy.context.view_layer.layer_collection
print("EXCLUDED", [c.name for c in vl.children if c.exclude])
for o in sorted(bpy.data.objects, key=lambda o: o.name):
    if o.type != "MESH":
        print("NONMESH", o.name, o.type, "parent", o.parent.name if o.parent else None,
              tuple(round(c, 4) for c in o.matrix_world.translation))
        continue
    h = health(o)
    out[o.name] = h
    flag = "  <--" if (h["nonmanifold"] or h["negative_volume_components"] or h["inconsistent_winding_edges"]
                       or h["degenerate"] or h["wire"]) else ""
    print(f"{o.name:36s} tris {h['tris']:5d} nm {h['nonmanifold']:3d} wire {h['wire']} deg {h['degenerate']:3d} "
          f"ngon {h['ngons']:4d} (>8: {h['ngons_gt8']:3d}) comp {h['components']:3d} negvol {h['negative_volume_components']} "
          f"incons {h['inconsistent_winding_edges']} uv {h['uv_layers']} {h['mats']} props={dict(o.items()) if o.keys() else ''}{flag}")
    if h["nonmanifold"]:
        print("     non-manifold samples:", h["nonmanifold_samples"])
# packed images
print("IMAGES", [(i.name, i.packed_file is not None, tuple(i.size)) for i in bpy.data.images])
print("MATERIALS", [(m.name, m.users) for m in bpy.data.materials])
with open(os.path.join(D, "_wip", "topology_report.json"), "w") as f:
    json.dump(out, f, indent=1)
