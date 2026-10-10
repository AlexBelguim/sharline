"""Round-2 independent review check for VK-50 WARDEN (reads the exported .glb files only; never touches the asset).

Checks (all on re-imported exports):
  - per-object mesh health: non-manifold / boundary / loose / degenerate / flipped components / UVs / materials
  - bounds + key stations vs BRIEF, sockets vs spec (names, positions, rotation, parent)
  - rail standard measured on the mesh (top width at the top surface, height, slot pitch, bottom / side faces)
  - interpenetration between parts (default pose), coplanar same-facing faces between parts (z-fight risk)
  - bolt cycle sweep (lift 0..60 deg, then travel 0..0.13 m) vs gun, stocks, default optic, thermal optic
  - trigger pull, safety to FIRE, folding stock folded, mag insertion path, cheek riser / monopod travel
  - attachments mounted (optic_sniper, optic_thermal, bipod, laser_R, flashlight_L): seating gaps + overlaps
Writes review/r2/check_report.json

Run: blender -b --factory-startup -P r2_check.py
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

D = r"F:/git/val etf/assets/weapons/vk50_warden"
ATT_O = r"F:/git/val etf/assets/weapons/attachments/optics"
ATT_T = r"F:/git/val etf/assets/weapons/attachments/tactical"
OUTJ = os.path.join(D, "review", "r2", "check_report.json")
R = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def wmesh(o):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    mw = o.matrix_world
    v = [mw @ x.co for x in me.vertices]
    p = [tuple(x.vertices) for x in me.polygons]
    n = [(mw.to_3x3() @ x.normal).normalized() for x in me.polygons]
    c = [mw @ x.center for x in me.polygons]
    a = [x.area for x in me.polygons]
    oe.to_mesh_clear()
    return v, p, n, c, a


def bvh(o):
    v, p, *_ = wmesh(o)
    return BVHTree.FromPolygons(v, p, epsilon=0.0)


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def bounds(objs):
    mn = Vector((1e9,) * 3); mx = -mn
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
    return mn, mx


def r4(v):
    return [round(x, 4) for x in v]


def health(o):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world)
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    loose_v = sum(1 for v in bm.verts if not v.link_edges)
    loose_e = sum(1 for e in bm.edges if not e.link_faces)
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    # inconsistent winding: an interior manifold edge whose two faces traverse it in the same direction
    badwind = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            f1, f2 = e.link_faces
            def dirn(f):
                vs = list(f.verts)
                i = vs.index(e.verts[0]); j = vs.index(e.verts[1])
                return 1 if (i + 1) % len(vs) == j else -1
            if dirn(f1) == dirn(f2):
                badwind += 1
    comps = []; seen = set()
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
        vol = 0.0
        for g in comp:
            vs = [v.co for v in g.verts]
            for i in range(1, len(vs) - 1):
                vol += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
        comps.append((len(comp), vol))
    flipped = [c for c in comps if c[1] < -1e-10]
    uvl = len(o.data.uv_layers)
    res = dict(tris=tris(o), verts=len(bm.verts), nonmanifold=nonman, boundary=boundary, loose_v=loose_v,
               loose_e=loose_e, degenerate=degen, ngons=ngons, bad_winding_edges=badwind, components=len(comps),
               flipped_components=len(flipped), uv_layers=uvl,
               materials=[m.name if m else None for m in o.data.materials])
    bm.free()
    return res


def overlap(a, b, ta=None, tb=None, samples=6000):
    ta = ta or bvh(a); tb = tb or bvh(b)
    pairs = ta.overlap(tb)
    if not pairs:
        return 0, 0.0
    best = 0.0
    for (x, y, tt) in ((a, b, tb), (b, a, ta)):
        v, *_ = wmesh(x)
        mn, mx = bounds([y])
        st = max(1, len(v) // samples)
        for p in v[::st]:
            if not all(mn[i] - 1e-4 <= p[i] <= mx[i] + 1e-4 for i in range(3)):
                continue
            loc, nrm, idx, dist = tt.find_nearest(p)
            if loc is not None and (p - loc).dot(nrm) < 0:
                best = max(best, dist)
    return len(pairs), best


def mindist(a, b, tb=None, step=2):
    tb = tb or bvh(b)
    v, *_ = wmesh(a)
    best = 1e9
    for p in v[::step]:
        loc, n, i, d = tb.find_nearest(p)
        if loc is not None:
            best = min(best, d)
    return best


def pairs_report(meshes, label, min_depth_mm=0.0):
    trees = {o.name: bvh(o) for o in meshes}
    out = []
    for i, a in enumerate(meshes):
        for b in meshes[i + 1:]:
            n, d = overlap(a, b, trees[a.name], trees[b.name])
            if n and d * 1000 >= min_depth_mm:
                out.append(dict(a=a.name, b=b.name, face_pairs=n, depth_mm=round(d * 1000, 2)))
    out.sort(key=lambda r: -r["depth_mm"])
    R[label] = out
    print(f"--- {label}: {len(out)} intersecting pairs")
    for r in out:
        print("    ", r)
    return out


def zfight_report(meshes, label, tol=6e-5):
    """Faces of different objects that lie on top of each other AND face the same way (visible z-fight)."""
    trees = {o.name: bvh(o) for o in meshes}
    data = {o.name: wmesh(o) for o in meshes}
    out = []
    for a in meshes:
        v, p, n, c, ar = data[a.name]
        for b in meshes:
            if b is a:
                continue
            tb = trees[b.name]
            hits = 0; area = 0.0; where = None
            for k in range(len(p)):
                if ar[k] < 2e-7:
                    continue
                loc, nb, idx, dist = tb.find_nearest(c[k])
                if loc is not None and dist < tol and nb.dot(n[k]) > 0.995:
                    hits += 1; area += ar[k]; where = where or r4(c[k])
            if hits and a.name < b.name:
                out.append(dict(a=a.name, b=b.name, faces=hits, area_mm2=round(area * 1e6, 1), example=where))
    R[label] = out
    print(f"--- {label}: {len(out)} pairs with coincident same-facing faces")
    for r in out:
        print("    ", r)


# ================================================================================ 1. default assembly
reset()
objs = imp(os.path.join(D, "warden_default.glb"))
by = {o.name: o for o in objs}
meshes = [o for o in objs if o.type == "MESH"]
mn, mx = bounds(meshes)
R["default_bounds"] = dict(min=r4(mn), max=r4(mx), size=r4(mx - mn))
print("DEFAULT bounds", r4(mn), r4(mx), "size", r4(mx - mn))
per = {}
for o in sorted(meshes, key=lambda o: o.name):
    h = health(o)
    a, b = bounds([o])
    h["bmin"] = r4(a); h["bmax"] = r4(b)
    per[o.name] = h
    bad = any(h[k] for k in ("nonmanifold", "boundary", "loose_v", "loose_e", "degenerate", "flipped_components",
                             "bad_winding_edges")) or not h["uv_layers"]
    print(f"{o.name:34s} tri {h['tris']:5d} nm {h['nonmanifold']} bd {h['boundary']} lv {h['loose_v']} le {h['loose_e']} "
          f"deg {h['degenerate']} ngon {h['ngons']} wind {h['bad_winding_edges']} comp {h['components']} "
          f"flip {h['flipped_components']} uv {h['uv_layers']} {h['materials']} {r4(a)}..{r4(b)}" + ("  <-- CHECK" if bad else ""))
R["objects"] = per
R["default_tris"] = sum(v["tris"] for v in per.values())
print("DEFAULT TRIS", R["default_tris"])

spec = {"Optic": (0, -0.080, 0.1375), "Stock": (0, 0.080, 0.075), "Mag": (0, -0.270, 0.0),
        "Under": (0, -0.600, 0.0205), "Side_R": (-0.0455, -0.645, 0.079), "Side_L": (0.0455, -0.645, 0.079),
        "Muzzle": (0, -1.100, 0.075), "LeftHand": (0, -0.380, 0.030)}
sk = {}
for nm, want in spec.items():
    o = by.get(f"WARDEN_SOCKET_{nm}")
    if o is None:
        sk[nm] = "MISSING"; continue
    got = o.matrix_world.translation
    sk[nm] = dict(got=r4(got), err_mm=round((got - Vector(want)).length * 1000, 3),
                  rot=[round(math.degrees(x), 3) for x in o.matrix_world.to_euler()],
                  parent=o.parent.name if o.parent else None, type=o.type)
    print("SOCKET", nm, sk[nm])
R["sockets"] = sk

# ---- rails measured on mesh
def faces_at(o, axis, value, nsign, tol=2e-4):
    v, p, n, c, a = wmesh(o)
    out = []
    for k in range(len(p)):
        if abs(c[k][axis] - value) < tol and n[k][axis] * nsign > 0.99:
            out.append((c[k], a[k], [v[i] for i in p[k]]))
    return out

rt = by["WARDEN_RailTop"]
top = faces_at(rt, 2, 0.1375, +1)
xs = [q.x for f in top for q in f[2]]
ys_c = sorted({round(f[0].y, 4) for f in top})
R["railtop"] = dict(top_faces=len(top), top_x=(round(min(xs), 4), round(max(xs), 4)) if xs else None,
                    top_y=(round(min(q.y for f in top for q in f[2]), 4), round(max(q.y for f in top for q in f[2]), 4)) if top else None,
                    bounds=[r4(x) for x in bounds([rt])])
# slot pitch from the slot floors (z = top - 0.003)
floors = faces_at(rt, 2, 0.1375 - 0.003, +1, tol=4e-4)
fy = sorted({round(f[0].y, 4) for f in floors})
pitch = [round(fy[i + 1] - fy[i], 4) for i in range(len(fy) - 1)]
R["railtop"]["slot_floor_count"] = len(fy)
R["railtop"]["slot_pitch_set"] = sorted(set(pitch))
print("RAILTOP", R["railtop"])
for nm, axis, val, sgn in (("WARDEN_RailBottom", 2, 0.0205, -1), ("WARDEN_RailSide_R", 0, -0.0455, -1),
                           ("WARDEN_RailSide_L", 0, 0.0455, +1)):
    o = by[nm]
    fs = faces_at(o, axis, val, sgn)
    other = [i for i in range(3) if i != axis]
    ext = {}
    for i in other:
        vals = [q[i] for f in fs for q in f[2]]
        ext["xyz"[i]] = (round(min(vals), 4), round(max(vals), 4)) if vals else None
    R[nm] = dict(contact_faces=len(fs), contact_extent=ext, bounds=[r4(x) for x in bounds([o])])
    print(nm, R[nm])

# ---- stations
def ext(o, ax):
    a, b = bounds([o]); return (round(a[ax], 4), round(b[ax], 4))
st = {}
for nm in ("WARDEN_Brake", "WARDEN_Barrel", "WARDEN_Handguard", "WARDEN_Receiver", "WARDEN_Chassis", "WARDEN_Grip",
           "WARDEN_TriggerGuard", "WARDEN_Trigger", "WARDEN_Bolt", "WARDEN_Mag5", "WARDEN_StockStandard",
           "WARDEN_StockStandard_CheekRiser", "WARDEN_StockStandard_Monopod", "WARDEN_Safety", "WARDEN_BoltRelease",
           "WARDEN_MagRelease", "WARDEN_BrakeCollar"):
    o = by[nm]
    st[nm] = dict(x=ext(o, 0), y=ext(o, 1), z=ext(o, 2), origin=r4(o.matrix_world.translation))
    print("STATION", nm, st[nm])
R["stations"] = st

# barrel radius sampled at a few y stations
bv, *_ = wmesh(by["WARDEN_Barrel"])
rad = {}
for y0 in (-0.30, -0.55, -0.65, -0.72, -0.80, -0.90):
    rs = [math.hypot(p.x, p.z - 0.075) for p in bv if abs(p.y - y0) < 0.02]
    if rs:
        rad[str(y0)] = (round(min(rs), 4), round(max(rs), 4))
R["barrel_radius"] = rad
print("BARREL radius", rad)

# visible mag height below the magwell bottom lip
ch_min_z = bounds([by["WARDEN_Chassis"]])[0].z
mag_min_z = bounds([by["WARDEN_Mag5"]])[0].z
R["mag_visible_below_well_m"] = round(ch_min_z - mag_min_z, 4)
print("visible mag below well", R["mag_visible_below_well_m"])

# ---- intersections + z-fight + mag clearance in the magwell
pairs_report(meshes, "intersections_default")
zfight_report([o for o in meshes if not o.name.startswith("WARDEN_Mag5_Round")], "zfight_default")
R["mag_to_chassis_min_gap_mm"] = round(mindist(by["WARDEN_Mag5"], by["WARDEN_Chassis"]) * 1000, 2)
print("mag body to chassis min gap mm", R["mag_to_chassis_min_gap_mm"])

# mag insertion path: drop the mag 0..0.12 m below seated, test collision with chassis at each step
mag = by["WARDEN_Mag5"]
m_loc = mag.location.copy()
ins = []
tch = bvh(by["WARDEN_Chassis"])
for k in range(0, 13):
    dz = -0.01 * k
    mag.location = m_loc + Vector((0, 0, dz))
    bpy.context.view_layer.update()
    n, d = overlap(mag, by["WARDEN_Chassis"], None, tch)
    ins.append(dict(dz=dz, face_pairs=n, depth_mm=round(d * 1000, 2)))
mag.location = m_loc
bpy.context.view_layer.update()
R["mag_insertion_path"] = ins
print("MAG insertion", ins)

# ---- trigger pull / safety fire
def pose_hits(o, others, label):
    to = bvh(o)
    res = []
    for x in others:
        if x is o:
            continue
        n, d = overlap(o, x, to, None)
        if n:
            res.append(dict(other=x.name, face_pairs=n, depth_mm=round(d * 1000, 2)))
    R[label] = res
    print("---", label, res)

trig = by["WARDEN_Trigger"]; trig.rotation_mode = "XYZ"; r0 = trig.rotation_euler.copy()
trig.rotation_euler = (r0.x + math.radians(12), r0.y, r0.z); bpy.context.view_layer.update()
pose_hits(trig, meshes, "trigger_pulled")
trig.rotation_euler = r0
saf = by["WARDEN_Safety"]; saf.rotation_mode = "XYZ"; s0 = saf.rotation_euler.copy()
saf.rotation_euler = (s0.x + math.radians(-45), s0.y, s0.z); bpy.context.view_layer.update()
pose_hits(saf, meshes, "safety_fire")
saf.rotation_euler = s0
riser = by["WARDEN_StockStandard_CheekRiser"]; rl0 = riser.location.copy()
riser.location = rl0 + Vector((0, 0, 0.03)); bpy.context.view_layer.update()
pose_hits(riser, meshes, "riser_raised_30mm")
riser.location = rl0
mono = by["WARDEN_StockStandard_Monopod"]; ml0 = mono.location.copy()
mono.location = ml0 + Vector((0, 0, -0.045)); bpy.context.view_layer.update()
pose_hits(mono, meshes, "monopod_extended_45mm")
mono.location = ml0
bpy.context.view_layer.update()

# ---- bolt cycle sweep (Blender local axes; imported glb keeps Blender axes after import)
bolt = by["WARDEN_Bolt"]; bolt.rotation_mode = "XYZ"
bl0 = bolt.location.copy(); br0 = bolt.rotation_euler.copy()
print("bolt origin", r4(bolt.matrix_world.translation), "rot", r4(br0))
others = [o for o in meshes if o is not bolt]
oth_t = {o.name: bvh(o) for o in others}

def bolt_sweep(label, extra=()):
    hits = {}
    path = [(l, 0.0) for l in range(0, 61, 5)] + [(60, t / 1000) for t in range(5, 131, 5)]
    for lift, trav in path:
        bolt.rotation_euler = (br0.x, br0.y + math.radians(lift), br0.z)
        bolt.location = bl0 + Vector((0, trav, 0))
        bpy.context.view_layer.update()
        tb = bvh(bolt)
        for x in list(others) + list(extra):
            tx = oth_t.get(x.name) or bvh(x)
            if tb.overlap(tx):
                n, d = overlap(bolt, x, tb, tx)
                k = x.name
                if k not in hits or d > hits[k]["depth_mm"] / 1000:
                    hits[k] = dict(first_at=(lift, trav), depth_mm=round(d * 1000, 2), face_pairs=n)
    bolt.rotation_euler = br0; bolt.location = bl0; bpy.context.view_layer.update()
    R[label] = hits
    print("---", label, hits)

bolt_sweep("bolt_sweep_gun_only")
# lifted-handle check: highest point of the bolt at full lift
bolt.rotation_euler = (br0.x, br0.y + math.radians(60), br0.z); bpy.context.view_layer.update()
bvv, *_ = wmesh(bolt)
R["bolt_lifted_bounds"] = [r4(x) for x in bounds([bolt])]
R["bolt_lifted_knob_top_z"] = round(max(p.z for p in bvv), 4)
bolt.rotation_euler = br0; bpy.context.view_layer.update()
print("bolt lifted bounds", R["bolt_lifted_bounds"])

# ---- attachments
socket = {nm: by[f"WARDEN_SOCKET_{nm}"].matrix_world.translation.copy() for nm in spec}
def mount(path, sock):
    new = imp(path)
    for r in [o for o in new if o.parent is None]:
        r.matrix_world = Matrix.Translation(socket[sock]) @ r.matrix_world
    bpy.context.view_layer.update()
    return new

att_res = {}
for fn, sock in ((os.path.join(ATT_O, "ATT_optic_sniper.glb"), "Optic"), (os.path.join(ATT_O, "ATT_optic_thermal.glb"), "Optic"),
                 (os.path.join(ATT_T, "ATT_bipod.glb"), "Under"), (os.path.join(ATT_T, "ATT_laser_R.glb"), "Side_R"),
                 (os.path.join(ATT_T, "ATT_flashlight_L.glb"), "Side_L"), (os.path.join(ATT_T, "ATT_laser_L.glb"), "Side_L"),
                 (os.path.join(ATT_T, "ATT_flashlight_R.glb"), "Side_R")):
    if not os.path.exists(fn):
        att_res[os.path.basename(fn)] = "MISSING FILE"; continue
    new = mount(fn, sock)
    am = [o for o in new if o.type == "MESH"]
    res = dict(hits=[], min_gap_to_gun_mm=None)
    best = 1e9
    for a in am:
        ta = bvh(a)
        for g in meshes:
            n, d = overlap(a, g, ta, oth_t.get(g.name))
            if n:
                res["hits"].append(dict(att=a.name, gun=g.name, face_pairs=n, depth_mm=round(d * 1000, 2)))
        for g in (by["WARDEN_RailTop"], by["WARDEN_RailBottom"], by["WARDEN_RailSide_R"], by["WARDEN_RailSide_L"]):
            best = min(best, mindist(a, g, step=1))
    res["min_gap_to_rails_mm"] = round(best * 1000, 3)
    # bolt sweep with this attachment
    if "optic" in fn:
        hits = {}
        for lift, trav in [(l, 0.0) for l in range(0, 61, 5)] + [(60, t / 1000) for t in range(5, 131, 5)]:
            bolt.rotation_euler = (br0.x, br0.y + math.radians(lift), br0.z)
            bolt.location = bl0 + Vector((0, trav, 0))
            bpy.context.view_layer.update()
            tb = bvh(bolt)
            for a in am:
                n, d = overlap(bolt, a, tb, None)
                if n:
                    hits.setdefault(a.name, dict(first_at=(lift, trav), depth_mm=round(d * 1000, 2)))
        bolt.rotation_euler = br0; bolt.location = bl0; bpy.context.view_layer.update()
        res["bolt_sweep_hits"] = hits
        # clearance at full open
        bolt.rotation_euler = (br0.x, br0.y + math.radians(60), br0.z); bolt.location = bl0 + Vector((0, 0.13, 0))
        bpy.context.view_layer.update()
        res["bolt_open_min_gap_mm"] = round(min(mindist(bolt, a, step=1) for a in am) * 1000, 2)
        bolt.rotation_euler = (br0.x, br0.y + math.radians(60), br0.z); bolt.location = bl0
        bpy.context.view_layer.update()
        res["bolt_lifted_min_gap_mm"] = round(min(mindist(bolt, a, step=1) for a in am) * 1000, 2)
        bolt.rotation_euler = br0; bolt.location = bl0; bpy.context.view_layer.update()
        # ADS socket height above rail top
        ads = [o for o in new if o.name.endswith("_SOCKET_ADS")]
        if ads:
            res["ADS_world"] = r4(ads[0].matrix_world.translation)
            res["ADS_above_rail_top_m"] = round(ads[0].matrix_world.translation.z - 0.1375, 4)
        # does the optic body occlude the cheek riser? riser top vs optic bottom near y 0.1..0.3
        rz = bounds([riser])[1].z
        res["riser_top_z"] = round(rz, 4)
    att_res[os.path.basename(fn)] = res
    print("ATT", os.path.basename(fn), res)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
R["attachments"] = att_res

# ================================================================================ 2. each file on its own
files = {}
for fn in ("warden_base.glb", "WARDEN_stock_standard.glb", "WARDEN_stock_folding.glb", "WARDEN_mag_5.glb",
           "WARDEN_mag_8.glb"):
    reset()
    ob = imp(os.path.join(D, fn))
    ms = [o for o in ob if o.type == "MESH"]
    roots = [o for o in ob if o.parent is None]
    a, b = bounds(ms)
    bad = {}
    for o in ms:
        h = health(o)
        if any(h[k] for k in ("nonmanifold", "boundary", "loose_v", "loose_e", "degenerate", "flipped_components",
                              "bad_winding_edges")):
            bad[o.name] = h
    files[fn] = dict(roots=[(r.name, r4(r.matrix_world.translation), r4(r.rotation_euler)) for r in roots],
                     meshes=len(ms), tris=sum(tris(o) for o in ms), bounds=[r4(a), r4(b)], bad=bad)
    print("FILE", fn, files[fn])
R["files"] = files

# ================================================================================ 3. folding stock + mag_8
reset()
ob = imp(os.path.join(D, "warden_base.glb"))
byb = {o.name: o for o in ob}
s_stock = byb["WARDEN_SOCKET_Stock"].matrix_world.translation.copy()
s_mag = byb["WARDEN_SOCKET_Mag"].matrix_world.translation.copy()
sf = imp(os.path.join(D, "WARDEN_stock_folding.glb"))
for r in [o for o in sf if o.parent is None]:
    r.matrix_world = Matrix.Translation(s_stock) @ r.matrix_world
m8 = imp(os.path.join(D, "WARDEN_mag_8.glb"))
for r in [o for o in m8 if o.parent is None]:
    r.matrix_world = Matrix.Translation(s_mag) @ r.matrix_world
bpy.context.view_layer.update()
allm = [o for o in ob + sf + m8 if o.type == "MESH"]
pairs_report(allm, "intersections_alt_unfolded")
arm = next(o for o in sf if o.name == "WARDEN_StockFolding_Arm")
arm.rotation_mode = "XYZ"
a0 = arm.rotation_euler.copy()
fold_hits = {}
for ang in range(0, -181, -15):
    arm.rotation_euler = (a0.x, a0.y, a0.z + math.radians(ang))
    bpy.context.view_layer.update()
    ta = bvh(arm)
    for g in allm:
        if g is arm:
            continue
        n, d = overlap(arm, g, ta, None)
        if n:
            fold_hits.setdefault(g.name, []).append((ang, round(d * 1000, 2)))
R["fold_sweep_hits"] = fold_hits
print("FOLD sweep", fold_hits)
a, b = bounds([arm])
R["folded_arm_bounds"] = [r4(a), r4(b)]
arm.rotation_euler = a0
bpy.context.view_layer.update()
R["alt_bounds"] = [r4(x) for x in bounds(allm)]
R["mag8_visible_below_well_m"] = round(bounds([byb["WARDEN_Chassis"]])[0].z - bounds([byb.get("WARDEN_Mag8") or next(o for o in m8 if o.name == "WARDEN_Mag8")])[0].z, 4)

with open(OUTJ, "w") as f:
    json.dump(R, f, indent=1, default=str)
print("WROTE", OUTJ)
