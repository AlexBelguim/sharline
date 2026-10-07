"""Independent reviewer check for the VK-50 WARDEN exports (does NOT touch the asset).

Imports the exported .glb files into fresh scenes and reports:
  dimensions vs BRIEF, socket names/positions vs spec, tri counts, UVs, materials,
  non-manifold / boundary / loose / degenerate geometry, flipped components (signed volume),
  floating (disconnected-looking) components, and BVH interpenetration between parts in the
  default pose, the bolt-open pose, the folded folding stock and with the default optic / bipod mounted.
Writes review/check_report.json.

Run: blender -b --factory-startup -P review_check.py
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

D = r"F:/git/val etf/assets/weapons/vk50_warden"
ATT = r"F:/git/val etf/assets/weapons/attachments"
OUTJ = os.path.join(D, "review", "check_report.json")
REPORT = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def world_mesh(o):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    mw = o.matrix_world
    verts = [mw @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    oe.to_mesh_clear()
    return verts, polys


def bvh(o):
    v, p = world_mesh(o)
    return BVHTree.FromPolygons(v, p, epsilon=0.0)


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def bounds(objs):
    mn = Vector((1e9, 1e9, 1e9)); mx = -mn
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
    return mn, mx


def r4(v):
    return [round(x, 4) for x in v]


def mesh_health(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    loose_v = sum(1 for v in bm.verts if not v.link_edges)
    loose_e = sum(1 for e in bm.edges if not e.link_faces)
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    # connected components, signed volume per component (negative => inward normals)
    comps = []
    seen = set()
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]; comp = []
        seen.add(f.index)
        while stack:
            g = stack.pop(); comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); stack.append(h)
        vol = 0.0
        for g in comp:
            vs = [v.co for v in g.verts]
            for i in range(1, len(vs) - 1):
                vol += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
        comps.append((len(comp), vol, comp))
    flipped = [(n, v) for (n, v, _) in comps if v < -1e-9]
    uv = len(o.data.uv_layers)
    uv_zero = 0
    if uv:
        lay = bm.loops.layers.uv.active
        for f in bm.faces:
            a = 0.0
            ls = list(f.loops)
            for i in range(len(ls)):
                u0 = ls[i][lay].uv; u1 = ls[(i + 1) % len(ls)][lay].uv
                a += u0.x * u1.y - u1.x * u0.y
            if abs(a) < 1e-12:
                uv_zero += 1
    res = dict(tris=tris(o), nonmanifold_edges=nonman, boundary_edges=boundary, loose_verts=loose_v,
               loose_edges=loose_e, degenerate_faces=degen, ngons=ngons, components=len(comps),
               flipped_components=len(flipped), uv_layers=uv, zero_area_uv_faces=uv_zero,
               materials=[m.name if m else None for m in o.data.materials])
    comp_pts = [[v.co.copy() for g in c for v in g.verts] for (_, _, c) in comps]
    bm.free()
    return res, comp_pts


def penetration(a, b, ta, tb, samples=4000):
    """Max depth (m) of a's vertices inside b (nearest-face normal test), plus overlap pair count."""
    pairs = ta.overlap(tb)
    if not pairs:
        return 0, 0.0
    va, _ = world_mesh(a)
    mnb, mxb = bounds([b])
    depth = 0.0
    step = max(1, len(va) // samples)
    for v in va[::step]:
        if not all(mnb[i] - 1e-4 <= v[i] <= mxb[i] + 1e-4 for i in range(3)):
            continue
        loc, nrm, idx, dist = tb.find_nearest(v)
        if loc is None:
            continue
        if (v - loc).dot(nrm) < 0:
            depth = max(depth, dist)
    return len(pairs), depth


def pair_report(objs, label, skip=()):
    meshes = [o for o in objs if o.type == "MESH"]
    trees = {o.name: bvh(o) for o in meshes}
    out = []
    for i, a in enumerate(meshes):
        for b in meshes[i + 1:]:
            key = tuple(sorted((a.name, b.name)))
            if key in skip:
                continue
            n, d1 = penetration(a, b, trees[a.name], trees[b.name])
            if n:
                _, d2 = penetration(b, a, trees[b.name], trees[a.name])
                out.append(dict(a=a.name, b=b.name, overlapping_face_pairs=n, max_depth_mm=round(max(d1, d2) * 1000, 2)))
    out.sort(key=lambda r: -r["max_depth_mm"])
    REPORT[label] = out
    print(f"--- {label}: {len(out)} intersecting pairs")
    for r in out:
        print("   ", r)
    return out


def floating_report(objs, label, tol=0.0004):
    """Components (loose parts inside an object, or whole objects) that touch nothing else within tol."""
    meshes = [o for o in objs if o.type == "MESH"]
    trees = {o.name: bvh(o) for o in meshes}
    out = []
    for o in meshes:
        _, comps = mesh_health(o)
        for ci, pts in enumerate(comps):
            # distance of this component to every other mesh, and to its own object's other components
            best = 1e9
            for other in meshes:
                if other is o:
                    continue
                t = trees[other.name]
                for p in pts[:: max(1, len(pts) // 400)]:
                    loc, nrm, idx, dist = t.find_nearest(p)
                    if loc is not None:
                        best = min(best, dist)
            if len(comps) > 1:
                rest = [p for cj, q in enumerate(comps) if cj != ci for p in q]
                if rest:
                    from mathutils.kdtree import KDTree
                    kd = KDTree(len(rest))
                    for k, p in enumerate(rest):
                        kd.insert(p, k)
                    kd.balance()
                    for p in pts[:: max(1, len(pts) // 400)]:
                        _, _, dist = kd.find(p)
                        best = min(best, dist)
            if best > tol:
                c = sum(pts, Vector()) / len(pts)
                out.append(dict(object=o.name, component=ci, verts=len(pts), centre=r4(c), gap_mm=round(best * 1000, 2)))
    REPORT[label] = out
    print(f"--- {label}: {len(out)} components with no contact within {tol*1000} mm (vertex-sampled)")
    for r in out:
        print("   ", r)


# ===================================================================================== 1. default assembly
reset()
objs = imp(os.path.join(D, "warden_default.glb"))
byname = {o.name: o for o in objs}
meshes = [o for o in objs if o.type == "MESH"]
mn, mx = bounds(meshes)
REPORT["default_bounds"] = dict(min=r4(mn), max=r4(mx), size=r4(mx - mn))
print("DEFAULT bounds", r4(mn), r4(mx), "size", r4(mx - mn))
per = {}
for o in sorted(meshes, key=lambda o: o.name):
    a, b = bounds([o])
    h, _ = mesh_health(o)
    h["bounds_min"] = r4(a); h["bounds_max"] = r4(b)
    per[o.name] = h
    flag = "" if not (h["nonmanifold_edges"] or h["boundary_edges"] or h["loose_verts"] or h["loose_edges"]
                      or h["degenerate_faces"] or h["flipped_components"] or not h["uv_layers"]) else "  <-- CHECK"
    print(f"{o.name:38s} tris {h['tris']:6d} nm {h['nonmanifold_edges']} bd {h['boundary_edges']} "
          f"lv {h['loose_verts']} le {h['loose_edges']} deg {h['degenerate_faces']} ngon {h['ngons']} "
          f"comp {h['components']} flip {h['flipped_components']} uv {h['uv_layers']} uv0 {h['zero_area_uv_faces']} "
          f"{h['materials']} [{r4(a)} .. {r4(b)}]{flag}")
REPORT["default_objects"] = per
REPORT["default_tris"] = sum(per[k]["tris"] for k in per)
print("DEFAULT TOTAL TRIS", REPORT["default_tris"])

# sockets
spec = {"Optic": (0, -0.080, 0.1375), "Stock": (0, 0.080, 0.075), "Mag": (0, -0.270, 0.0),
        "Under": (0, -0.600, 0.0205), "Side_R": (-0.0455, -0.645, 0.079), "Side_L": (0.0455, -0.645, 0.079),
        "Muzzle": (0, -1.100, 0.075), "LeftHand": (0, -0.380, 0.030)}
sk = {}
for nm, want in spec.items():
    o = byname.get(f"WARDEN_SOCKET_{nm}")
    if o is None:
        sk[nm] = "MISSING"; print("SOCKET MISSING", nm); continue
    got = o.matrix_world.translation
    rot = [round(math.degrees(a), 3) for a in o.matrix_world.to_euler()]
    err = (got - Vector(want)).length
    sk[nm] = dict(got=r4(got), want=list(want), err_mm=round(err * 1000, 3), rot_deg=rot, parent=o.parent.name if o.parent else None)
    print(f"SOCKET {nm:9s} got {r4(got)} want {want} err {err*1000:.3f} mm rot {rot} parent {o.parent.name if o.parent else None}")
REPORT["sockets"] = sk
root = byname.get("WARDEN_Root")
REPORT["root"] = dict(exists=root is not None, loc=r4(root.matrix_world.translation) if root else None)

# rail measurements (independent)
def rail_measure(o, axis_out):
    v, _ = world_mesh(o)
    xs = [p.x for p in v]; ys = [p.y for p in v]; zs = [p.z for p in v]
    return dict(x=(round(min(xs), 4), round(max(xs), 4)), y=(round(min(ys), 4), round(max(ys), 4)),
                z=(round(min(zs), 4), round(max(zs), 4)))
rails = {n: rail_measure(byname[n], None) for n in ("WARDEN_RailTop", "WARDEN_RailBottom", "WARDEN_RailSide_R", "WARDEN_RailSide_L")}
REPORT["rails"] = rails
for k, v in rails.items():
    print("RAIL", k, v)
# slot pitch on the top rail: find the z-top faces' y centres
rt = byname["WARDEN_RailTop"]
v, p = world_mesh(rt)
tops = sorted({round(sum(v[i].y for i in f) / len(f), 4) for f in p if all(abs(v[i].z - 0.1375) < 2e-4 for i in f)})
REPORT["railtop_top_faces_y"] = tops[:12]
print("RAILTOP top-face y centres (first 12):", tops[:12], "count", len(tops))

# key stations vs BRIEF
def ext(o, ax):
    a, b = bounds([o]); return round(a[ax], 4), round(b[ax], 4)
st = dict(
    brake_front_y=ext(byname["WARDEN_Brake"], 1)[0],
    brake_size=r4(bounds([byname["WARDEN_Brake"]])[1] - bounds([byname["WARDEN_Brake"]])[0]),
    barrel_y=ext(byname["WARDEN_Barrel"], 1),
    handguard_y=ext(byname["WARDEN_Handguard"], 1), handguard_x=ext(byname["WARDEN_Handguard"], 0),
    handguard_z=ext(byname["WARDEN_Handguard"], 2),
    receiver_x=ext(byname["WARDEN_Receiver"], 0), receiver_z=ext(byname["WARDEN_Receiver"], 2),
    receiver_y=ext(byname["WARDEN_Receiver"], 1),
    chassis_z=ext(byname["WARDEN_Chassis"], 2), grip_z=ext(byname["WARDEN_Grip"], 2), grip_x=ext(byname["WARDEN_Grip"], 0),
    mag_z=ext(byname["WARDEN_Mag5"], 2), mag_x=ext(byname["WARDEN_Mag5"], 0),
    stock_y=ext(byname["WARDEN_StockStandard"], 1), stock_x=ext(byname["WARDEN_StockStandard"], 0),
    monopod_z=ext(byname["WARDEN_StockStandard_Monopod"], 2),
    bolt_x=ext(byname["WARDEN_Bolt"], 0), bolt_z=ext(byname["WARDEN_Bolt"], 2), bolt_y=ext(byname["WARDEN_Bolt"], 1),
    riser_z=ext(byname["WARDEN_StockStandard_CheekRiser"], 2),
)
REPORT["stations"] = st
for k, v in st.items():
    print("STATION", k, v)

# origins of moving parts
REPORT["pivots"] = {n: r4(byname[n].matrix_world.translation) for n in
                    ("WARDEN_Bolt", "WARDEN_Trigger", "WARDEN_Safety", "WARDEN_StockStandard",
                     "WARDEN_StockStandard_CheekRiser", "WARDEN_StockStandard_Monopod", "WARDEN_Mag5", "WARDEN_Mag5_Round")}
print("PIVOTS", REPORT["pivots"])
REPORT["extras_on_bolt"] = {k: str(byname["WARDEN_Bolt"][k]) for k in byname["WARDEN_Bolt"].keys()} if byname["WARDEN_Bolt"].keys() else {}
REPORT["extras_on_round"] = {k: str(byname["WARDEN_Mag5_Round_02"][k]) for k in byname["WARDEN_Mag5_Round_02"].keys()}
print("EXTRAS bolt", REPORT["extras_on_bolt"], "round", REPORT["extras_on_round"])

# intersections in the default pose
pair_report(objs, "intersections_default")
floating_report(objs, "floating_default")

# bolt open pose (as documented: +60 deg about local +Y, then +0.13 m along parent +Y)
bolt = byname["WARDEN_Bolt"]
bolt.rotation_mode = "XYZ"
base_loc = bolt.location.copy(); base_rot = bolt.rotation_euler.copy()
for lift, travel, lab in ((60, 0.0, "bolt_lifted"), (60, 0.065, "bolt_half_open"), (60, 0.13, "bolt_open")):
    bolt.rotation_euler = (base_rot.x, base_rot.y + math.radians(lift), base_rot.z)
    bolt.location = base_loc + Vector((0, travel, 0))
    bpy.context.view_layer.update()
    tb = bvh(bolt)
    res = []
    for o in meshes:
        if o is bolt:
            continue
        n, d = penetration(bolt, o, tb, bvh(o))
        if n:
            _, d2 = penetration(o, bolt, bvh(o), tb)
            res.append(dict(other=o.name, overlapping_face_pairs=n, max_depth_mm=round(max(d, d2) * 1000, 2)))
    REPORT[f"intersections_{lab}"] = res
    print(f"--- {lab}: bolt collides with", res)
bolt.rotation_euler = base_rot; bolt.location = base_loc

# trigger pulled (+12 deg about local X)
trig = byname["WARDEN_Trigger"]
trig.rotation_mode = "XYZ"
r0 = trig.rotation_euler.copy()
trig.rotation_euler = (r0.x + math.radians(12), r0.y, r0.z)
bpy.context.view_layer.update()
tt = bvh(trig)
res = []
for o in meshes:
    if o is trig:
        continue
    n, d = penetration(trig, o, tt, bvh(o))
    if n:
        res.append(dict(other=o.name, overlapping_face_pairs=n, max_depth_mm=round(d * 1000, 2)))
REPORT["intersections_trigger_pulled"] = res
print("--- trigger pulled collides with", res)
trig.rotation_euler = r0

# default optic + bipod mounted (other agents' exports, read-only) -> clearance with bolt/knob/riser
sock = {nm: byname[f"WARDEN_SOCKET_{nm}"].matrix_world.translation.copy() for nm in spec}
att = []
for path, s in ((os.path.join(ATT, "optics", "ATT_optic_sniper.glb"), "Optic"),
                (os.path.join(ATT, "tactical", "ATT_bipod.glb"), "Under")):
    new = imp(path)
    roots = [o for o in new if o.parent is None]
    for r in roots:
        r.matrix_world = Matrix.Translation(sock[s]) @ r.matrix_world
    att += [o for o in new if o.type == "MESH"]
bpy.context.view_layer.update()
res = []
for a in att:
    ta = bvh(a)
    for o in meshes:
        n, d = penetration(a, o, ta, bvh(o))
        if n:
            _, d2 = penetration(o, a, bvh(o), ta)
            res.append(dict(att=a.name, gun=o.name, overlapping_face_pairs=n, max_depth_mm=round(max(d, d2) * 1000, 2)))
REPORT["intersections_with_default_optic_bipod"] = res
print("--- optic/bipod vs gun", res)
# bolt open with optic mounted
bolt.rotation_euler = (base_rot.x, base_rot.y + math.radians(60), base_rot.z)
bolt.location = base_loc + Vector((0, 0.13, 0))
bpy.context.view_layer.update()
tb = bvh(bolt)
res = []
for a in att:
    n, d = penetration(bolt, a, tb, bvh(a))
    if n:
        res.append(dict(att=a.name, overlapping_face_pairs=n, max_depth_mm=round(d * 1000, 2)))
REPORT["intersections_bolt_open_vs_optic"] = res
print("--- bolt open vs optic", res)
# clearance knob <-> scope (min distance)
knob_pts, _ = world_mesh(bolt)
best = 1e9
for a in att:
    t = bvh(a)
    for p in knob_pts[::3]:
        loc, n, i, dd = t.find_nearest(p)
        if loc is not None:
            best = min(best, dd)
REPORT["bolt_open_min_clearance_to_attachments_mm"] = round(best * 1000, 2)
print("bolt open min clearance to attachments (mm)", round(best * 1000, 2))
bolt.rotation_euler = base_rot; bolt.location = base_loc

# ===================================================================================== 2. part files on their own
for fn in ("warden_base.glb", "warden_stock_standard.glb", "warden_stock_folding.glb", "warden_mag_5.glb", "warden_mag_8.glb"):
    reset()
    ob = imp(os.path.join(D, fn))
    ms = [o for o in ob if o.type == "MESH"]
    roots = [o for o in ob if o.parent is None]
    a, b = bounds(ms)
    REPORT[f"file_{fn}"] = dict(roots=[(r.name, r4(r.matrix_world.translation)) for r in roots], meshes=len(ms),
                               tris=sum(tris(o) for o in ms), bounds=[r4(a), r4(b)],
                               bad=[(o.name, mesh_health(o)[0]) for o in ms
                                    if any(mesh_health(o)[0][k] for k in ("nonmanifold_edges", "boundary_edges", "loose_verts", "flipped_components"))])
    print("FILE", fn, REPORT[f"file_{fn}"]["roots"], "meshes", len(ms), "tris", REPORT[f"file_{fn}"]["tris"], "bounds", r4(a), r4(b))

# ===================================================================================== 3. folding stock folded + mag_8 on the base
reset()
ob = imp(os.path.join(D, "warden_base.glb"))
byb = {o.name: o for o in ob}
s_stock = byb["WARDEN_SOCKET_Stock"].matrix_world.translation.copy()
s_mag = byb["WARDEN_SOCKET_Mag"].matrix_world.translation.copy()
sf = imp(os.path.join(D, "warden_stock_folding.glb"))
for r in [o for o in sf if o.parent is None]:
    r.matrix_world = Matrix.Translation(s_stock) @ r.matrix_world
m8 = imp(os.path.join(D, "warden_mag_8.glb"))
for r in [o for o in m8 if o.parent is None]:
    r.matrix_world = Matrix.Translation(s_mag) @ r.matrix_world
bpy.context.view_layer.update()
allo = ob + sf + m8
pair_report(allo, "intersections_alt_unfolded")
arm = next(o for o in sf if o.name == "WARDEN_StockFolding_Arm")
arm.rotation_mode = "XYZ"
arm.rotation_euler.z += math.radians(-180)
bpy.context.view_layer.update()
pair_report(allo, "intersections_alt_folded")
a, b = bounds([arm])
REPORT["folded_arm_bounds"] = [r4(a), r4(b)]
print("folded arm bounds", r4(a), r4(b))
# bolt open with the stock folded (bolt must still cycle? report only)
bolt = byb["WARDEN_Bolt"]; bolt.rotation_mode = "XYZ"
bolt.rotation_euler.y += math.radians(60); bolt.location.y += 0.13
bpy.context.view_layer.update()
tb = bvh(bolt)
res = []
for o in [x for x in allo if x.type == "MESH" and x is not bolt]:
    n, d = penetration(bolt, o, tb, bvh(o))
    if n:
        res.append(dict(other=o.name, overlapping_face_pairs=n, max_depth_mm=round(d * 1000, 2)))
REPORT["intersections_bolt_open_folding_stock_folded"] = res
print("--- bolt open, folding stock folded:", res)

with open(OUTJ, "w") as f:
    json.dump(REPORT, f, indent=1, default=str)
print("WROTE", OUTJ)
