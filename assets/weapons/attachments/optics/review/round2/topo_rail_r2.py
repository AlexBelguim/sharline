"""Round-2 reviewer: topology on the .blend (true manifoldness; glTF import splits verts at seams) + dense probe of
the real gun rails under the optic socket (read-only; writes review/round2/topo_rail_r2.json).

"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P topo_rail_r2.py
"""
import json
import os

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
R2 = os.path.join(OUT, "review", "round2")
OPTICS = ["optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"]
res = {"blend": {}, "glb_merged": {}, "rails": {}}

# ---------------------------------------------------------------- .blend topology
bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, "optics.blend"))
res["blend"]["collections"] = sorted(c.name for c in bpy.data.collections)
res["blend"]["objects"] = sorted((o.name, o.type, o.users_collection[0].name if o.users_collection else None)
                                 for o in bpy.data.objects)
res["blend"]["materials"] = sorted(m.name for m in bpy.data.materials)
res["blend"]["images"] = sorted((i.name, i.packed_file is not None) for i in bpy.data.images)
for oid in OPTICS:
    ent = {}
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.name.startswith("ATT_%s_" % oid):
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        e = {"modifiers": [m.type for m in o.modifiers], "tris": sum(len(f.verts) - 2 for f in bm.faces),
             "boundary_edges": sum(1 for x in bm.edges if x.is_boundary),
             "non_manifold_edges": sum(1 for x in bm.edges if not x.is_manifold),
             "ngons": sum(1 for f in bm.faces if len(f.verts) > 4),
             "max_ngon": max((len(f.verts) for f in bm.faces), default=0),
             "sharp_edges": sum(1 for x in bm.edges if not x.smooth),
             "custom_normals": o.data.has_custom_normals}
        if e["boundary_edges"]:
            mids = [(x.verts[0].co + x.verts[1].co) / 2 for x in bm.edges if x.is_boundary][:500]
            e["boundary_bbox"] = [[round(min(m[i] for m in mids), 4) for i in range(3)],
                                  [round(max(m[i] for m in mids), 4) for i in range(3)]]
        # self-intersection between disjoint islands is normal (joined parts); count faces of one island that
        # pierce faces of another as a sanity number only
        bm.free()
        ent[o.name] = e
    res["blend"][oid] = ent

# ---------------------------------------------------------------- glb with merge_vertices (true topology of export)
for oid in OPTICS:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(OUT, "ATT_%s.glb" % oid), merge_vertices=True)
    ent = {}
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        ent[o.name] = {"boundary_edges": sum(1 for x in bm.edges if x.is_boundary),
                       "non_manifold_edges": sum(1 for x in bm.edges if not x.is_manifold)}
        bm.free()
    res["glb_merged"][oid] = ent

# ---------------------------------------------------------------- dense rail probe on the real guns
GUNS = {"MAKO": (r"F:/git/val etf/assets/weapons/ar7_mako/mako_base.glb", "MAKO_SOCKET_Optic"),
        "WARDEN": (r"F:/git/val etf/assets/weapons/vk50_warden/warden_base.glb", "WARDEN_SOCKET_Optic")}
for g, (glb, sock) in GUNS.items():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    s = bpy.data.objects[sock].matrix_world.translation.copy()
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys, owner = [], [], []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_object(o.evaluated_get(dg), dg)
        bm.transform(o.matrix_world)
        off = len(verts)
        verts += [v.co.copy() for v in bm.verts]
        for f in bm.faces:
            polys.append([v.index + off for v in f.verts])
            owner.append(o.name)
        bm.free()
    t = BVHTree.FromPolygons(verts, polys)
    prof = []
    for i in range(-60, 61):
        dy = i * 0.001
        h = t.ray_cast(s + Vector((0, dy, 0.08)), Vector((0, 0, -1)), 0.3)
        prof.append(None if h[0] is None else round((h[0].z - s.z) * 1000, 2))
    vals = [p for p in prof if p is not None]
    # rail width at the top
    wid = {}
    for dz in (-0.0005, -0.0015, -0.003, -0.005, -0.007):
        z = s.z + max(vals) / 1000 + dz
        hp = t.ray_cast(Vector((0.06, s.y, z)), Vector((-1, 0, 0)), 0.2)
        hn = t.ray_cast(Vector((-0.06, s.y, z)), Vector((1, 0, 0)), 0.2)
        wid[str(dz)] = [None if hp[0] is None else round(hp[0].x * 1000, 2),
                        None if hn[0] is None else round(hn[0].x * 1000, 2)]
    res["rails"][g] = {"socket": [round(x, 4) for x in s], "top_profile_mm_rel_socket_every_1mm_dy-60..60": prof,
                       "max_mm": max(vals), "min_mm": min(vals), "flank_x_mm_below_top": wid}
    print(g, "rail top rel socket: max %.2f mm, min %.2f mm" % (max(vals), min(vals)), wid)

with open(os.path.join(R2, "topo_rail_r2.json"), "w") as f:
    json.dump(res, f, indent=1)
for oid in OPTICS:
    print(oid, json.dumps(res["blend"][oid]))
    print(oid, "glb merged", json.dumps(res["glb_merged"][oid]))
print("collections", res["blend"]["collections"])
print("materials", res["blend"]["materials"])
print("images", res["blend"]["images"])
print("WROTE")
