"""Round-2 topology check. glTF splits vertices at UV seams / hard edges, so imported meshes look 'open';
here every mesh is welded by POSITION ONLY (1e-6 m) before testing closedness / winding / orientation.
Also opens warden.blend READ-ONLY (never saved) and tests the evaluated source meshes the same way.
Writes review/r2/topology_report.json.   Run: blender -b --factory-startup -P r2_topology.py
"""
import json, math, os
import bmesh, bpy
from mathutils import Vector

D = r"F:/git/val etf/assets/weapons/vk50_warden"
OUT = os.path.join(D, "review", "r2", "topology_report.json")
R = {}


def analyse(o, depsgraph=None):
    if depsgraph:
        oe = o.evaluated_get(depsgraph); me = oe.to_mesh()
    else:
        me = o.data
    bm = bmesh.new(); bm.from_mesh(me)
    if depsgraph:
        oe.to_mesh_clear()
    bm.transform(o.matrix_world)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.edges.ensure_lookup_table()
    nonman = [e for e in bm.edges if not e.is_manifold]
    boundary = [e for e in bm.edges if e.is_boundary]
    wire = [e for e in bm.edges if e.is_wire]
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    tiny = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    badw = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            f1, f2 = e.link_faces
            def d(f):
                vs = list(f.verts); i = vs.index(e.verts[0]); j = vs.index(e.verts[1])
                return 1 if (i + 1) % len(vs) == j else -1
            if d(f1) == d(f2):
                badw += 1
    # components + signed volume (only meaningful for closed comps)
    seen = set(); comps = []
    for f in bm.faces:
        if f.index in seen:
            continue
        st = [f]; comp = []; seen.add(f.index)
        while st:
            g = st.pop(); comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); st.append(h)
        vol = 0.0; closed = all(e.is_manifold and not e.is_boundary for g in comp for e in g.edges)
        for g in comp:
            vs = [v.co for v in g.verts]
            for i in range(1, len(vs) - 1):
                vol += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
        c = sum((v.co for g in comp for v in g.verts), Vector()) / sum(len(g.verts) for g in comp)
        comps.append(dict(faces=len(comp), vol_cm3=round(vol * 1e6, 4), closed=closed, centre=[round(x, 4) for x in c]))
    inward = [c for c in comps if c["closed"] and c["vol_cm3"] < 0]
    open_c = [c for c in comps if not c["closed"]]
    bnd_pts = [[round(x, 4) for x in ((e.verts[0].co + e.verts[1].co) / 2)] for e in boundary[:6]]
    res = dict(faces=len(bm.faces), tris=sum(len(f.verts) - 2 for f in bm.faces), nonmanifold=len(nonman),
               boundary=len(boundary), wire=len(wire), degenerate=degen, tiny_faces_lt_0_01mm2=tiny,
               bad_winding_edges=badw, components=len(comps), open_components=len(open_c),
               inward_closed_components=len(inward), inward_examples=inward[:3], boundary_examples=bnd_pts)
    bm.free()
    return res


def flag(r):
    return any(r[k] for k in ("nonmanifold", "boundary", "wire", "degenerate", "bad_winding_edges",
                              "inward_closed_components", "open_components"))


# ----- exported glbs
bpy.ops.wm.read_factory_settings(use_empty=True)
for fn in ("warden_default.glb", "WARDEN_stock_folding.glb", "WARDEN_mag_8.glb"):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(D, fn))
    new = [o for o in bpy.data.objects if o not in before]
    for o in sorted([o for o in new if o.type == "MESH"], key=lambda o: o.name):
        r = analyse(o)
        R[f"glb:{fn}:{o.name}"] = r
        print(f"GLB {fn:26s} {o.name:34s} f {r['faces']:5d} nm {r['nonmanifold']:3d} bd {r['boundary']:3d} "
              f"deg {r['degenerate']} tiny {r['tiny_faces_lt_0_01mm2']} wind {r['bad_winding_edges']} comp {r['components']} "
              f"open {r['open_components']} inward {r['inward_closed_components']}" + ("  <--" if flag(r) else ""))
        if flag(r):
            print("        boundary ex", r["boundary_examples"], "inward ex", r["inward_examples"])

# ----- source .blend (read only)
bpy.ops.wm.open_mainfile(filepath=os.path.join(D, "warden.blend"), load_ui=False)
vl = bpy.context.view_layer.layer_collection
for c in vl.children:
    c.exclude = False
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
R["blend_collections"] = {c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections}
R["blend_objects_with_modifiers"] = {o.name: [m.type for m in o.modifiers] for o in bpy.data.objects if o.type == "MESH" and o.modifiers}
R["blend_helper_objects"] = sorted(o.name for o in bpy.data.objects if o.name.startswith("_"))
R["blend_images"] = [(i.name, i.packed_file is not None, list(i.size)) for i in bpy.data.images]
for o in sorted([o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("_")], key=lambda o: o.name):
    r = analyse(o, dg)
    R[f"blend:{o.name}"] = r
    print(f"BLEND {o.name:36s} f {r['faces']:5d} nm {r['nonmanifold']:3d} bd {r['boundary']:3d} deg {r['degenerate']} "
          f"wind {r['bad_winding_edges']} comp {r['components']} open {r['open_components']} inward {r['inward_closed_components']}"
          + ("  <--" if flag(r) else ""))
print("collections", R["blend_collections"].keys())
print("helpers in blend", R["blend_helper_objects"])
print("modifiers", R["blend_objects_with_modifiers"])
print("images", R["blend_images"])
json.dump(R, open(OUT, "w"), indent=1)
print("WROTE", OUT)
