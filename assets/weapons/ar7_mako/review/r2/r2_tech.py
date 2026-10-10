"""Review r2: technical checks (read-only on the asset).
Run: blender -b --factory-startup -P r2_tech.py -- <mako.blend> <glb_dir> <out_json>
Checks: hierarchy/collections, pivots of moving parts, mesh health (non-manifold, loose, zero-area, winding,
signed volume, n-gons, UVs), dimensions, rail geometry, intersections, moving-part sweeps (charging handle pull,
mag drop), part origins, FBX re-import, and fit of the shared attachments on every socket."""
import json
import math
import os
import sys
from itertools import combinations

import bmesh
import bpy
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
BLEND, GLBDIR, OUTJ = ARGS[0], ARGS[1], ARGS[2]
ATT = r"F:/git/val etf/assets/weapons/attachments"
R = {}


def log(*a):
    print("[r2]", *a, flush=True)


bpy.ops.wm.open_mainfile(filepath=BLEND)
dg = bpy.context.evaluated_depsgraph_get()
OB = {o.name: o for o in bpy.data.objects}


def coll(o):
    return o.users_collection[0].name if o.users_collection else None


def wbm(o, matrix=None):
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(matrix if matrix is not None else o.matrix_world)
    oe.to_mesh_clear()
    return bm


# ------------------------------------------------------------------ hierarchy + pivots
R["collections"] = {c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections}
R["modifiers_left"] = {o.name: [m.type for m in o.modifiers] for o in bpy.data.objects
                       if o.type == "MESH" and o.modifiers}
piv_brief = {"MAKO_Trigger": (0, -0.040, 0.012), "MAKO_ChargingHandle": (0, 0.030, 0.068),
             "MAKO_DustCover": (-0.0175, -0.060, 0.041), "MAKO_BoltCatch": None, "MAKO_MagRelease": None,
             "MAKO_Selector": (0.016, -0.006, 0.013), "MAKO_ForwardAssist": None}
R["pivots"] = {}
for n, ref in piv_brief.items():
    o = OB.get(n)
    if not o:
        R["pivots"][n] = "MISSING"
        continue
    R["pivots"][n] = {"origin": [round(v, 4) for v in o.matrix_world.translation],
                      "brief": ref, "parent": o.parent.name if o.parent else None,
                      "custom_props": {k: (v if isinstance(v, (int, float, str)) else str(v)) for k, v in o.items()}}
R["parts_origin"] = {}
for n in ("MAKO_stock_standard", "MAKO_stock_precision", "MAKO_stock_light", "MAKO_mag_30", "MAKO_mag_45",
          "MAKO_mag_drum60"):
    o = OB[n]
    R["parts_origin"][n] = {"origin": [round(v, 4) for v in o.matrix_world.translation],
                            "children": sorted(c.name for c in o.children)}

# ------------------------------------------------------------------ mesh health
health = {}
BVH = {}
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    bm = wbm(o)
    bm.verts.ensure_lookup_table()
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    loose_v = sum(1 for v in bm.verts if not v.link_edges)
    loose_e = sum(1 for e in bm.edges if not e.link_faces)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    vol = 0.0
    for f in bm.faces:
        vs = [v.co for v in f.verts]
        for i in range(1, len(vs) - 1):
            vol += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
    badw = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            l0, l1 = e.link_loops[0], e.link_loops[1]
            if l0.vert == l1.vert:
                badw += 1
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    big_ngons = sum(1 for f in bm.faces if len(f.verts) > 8)
    # islands
    seen, isl = set(), 0
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        if f.index in seen:
            continue
        isl += 1
        st = [f]
        seen.add(f.index)
        while st:
            g = st.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        st.append(h)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    me = o.data
    uvl = me.uv_layers.active
    uv_zero = 0
    if uvl:
        for p in me.polygons:
            us = [uvl.data[li].uv for li in p.loop_indices]
            a = 0.0
            for i in range(1, len(us) - 1):
                a += abs((us[i] - us[0]).cross(us[i + 1] - us[0])) / 2
            if a < 1e-12:
                uv_zero += 1
    mn = [min(v.co[i] for v in bm.verts) for i in range(3)]
    mx = [max(v.co[i] for v in bm.verts) for i in range(3)]
    health[o.name] = {"tris": tris, "non_manifold": nm, "loose_v": loose_v, "loose_e": loose_e, "zero_area": zero,
                      "signed_vol_cm3": round(vol * 1e6, 3), "bad_winding_edges": badw, "ngons": ngons,
                      "ngons_gt8": big_ngons, "islands": isl, "uv_layers": len(me.uv_layers),
                      "uv_zero_area_faces": uv_zero, "mats": [s.material.name if s.material else None
                                                             for s in o.material_slots],
                      "bounds": [[round(v, 4) for v in mn], [round(v, 4) for v in mx]], "coll": coll(o)}
    BVH[o.name] = BVHTree.FromBMesh(bm)
    bm.free()
R["health"] = health
log("health done", len(health))

# ------------------------------------------------------------------ dimensions
def bounds(names):
    mn = [min(health[n]["bounds"][0][i] for n in names) for i in range(3)]
    mx = [max(health[n]["bounds"][1][i] for n in names) for i in range(3)]
    return mn, mx


base_n = [n for n, h in health.items() if h["coll"] == "MAKO_Base"]
def_n = base_n + [n for n, h in health.items() if h["coll"] in ("MAKO_stock_standard", "MAKO_mag_30")]
R["default_bounds"] = bounds(def_n)
R["default_tris"] = sum(health[n]["tris"] for n in def_n)
R["group_tris"] = {c: sum(h["tris"] for h in health.values() if h["coll"] == c) for c in R["collections"]}

# ------------------------------------------------------------------ rail geometry (top rail)
rail = OB["MAKO_Rail"]
bm = wbm(rail)
topz = max(v.co.z for v in bm.verts)
top_faces = [f for f in bm.faces if f.normal.z > 0.99 and abs(f.calc_center_median().z - topz) < 1e-4]
xs = [v.co.x for f in top_faces for v in f.verts]
ys = sorted(set(round(f.calc_center_median().y, 4) for f in top_faces))
slot_floor = [f for f in bm.faces if f.normal.z > 0.99 and f.calc_center_median().z < topz - 0.001
              and f.calc_center_median().z > topz - 0.006]
slot_y = sorted(set(round(f.calc_center_median().y, 4) for f in slot_floor))
pitch = [round(b - a, 4) for a, b in zip(slot_y, slot_y[1:])]
basez = min(v.co.z for v in bm.verts)
maxw = max(v.co.x for v in bm.verts) - min(v.co.x for v in bm.verts)
R["rail_top"] = {"top_z": round(topz, 4), "base_z": round(basez, 4), "height": round(topz - basez, 4),
                 "top_face_width": round(max(xs) - min(xs), 4), "max_width": round(maxw, 4),
                 "slot_floor_z": sorted(set(round(f.calc_center_median().z, 4) for f in slot_floor))[:3],
                 "n_slots": len(slot_y), "pitch_set": sorted(set(pitch))[:6],
                 "y_range": [round(min(v.co.y for v in bm.verts), 4), round(max(v.co.y for v in bm.verts), 4)]}
bm.free()
for rn in ("MAKO_RailBottom", "MAKO_RailSide_R", "MAKO_RailSide_L"):
    R[rn] = health[rn]["bounds"]

# ------------------------------------------------------------------ intersections (BVH overlap pairs)
def overlap(a, b):
    return len(BVH[a].overlap(BVH[b]))


inter = {}
for a, b in combinations(def_n, 2):
    k = overlap(a, b)
    if k:
        inter[f"{a} x {b}"] = k
for c in ("MAKO_stock_precision", "MAKO_stock_light", "MAKO_mag_45", "MAKO_mag_drum60"):
    cn = [n for n, h in health.items() if h["coll"] == c]
    for a in cn:
        for b in base_n:
            k = overlap(a, b)
            if k:
                inter[f"{a} x {b}"] = k
R["intersections"] = inter


# penetration depth of object a's vertices inside closed mesh b (nearest-face normal test)
def penetration(a_name, b_name, matrix_a=None):
    oa = OB[a_name]
    bma = wbm(oa, matrix_a)
    tb = BVH[b_name]
    worst = 0.0
    cnt = 0
    for v in bma.verts:
        loc, nrm, idx, dist = tb.find_nearest(v.co)
        if loc is None:
            continue
        if (v.co - loc).dot(nrm) < -1e-6 and dist > 2e-4:
            cnt += 1
            worst = max(worst, dist)
    bma.free()
    return cnt, round(worst * 1000, 2)


pen = {}
for key in inter:
    a, b = key.split(" x ")
    c1, w1 = penetration(a, b)
    c2, w2 = penetration(b, a)
    pen[key] = {"a_in_b_verts": c1, "a_in_b_max_mm": w1, "b_in_a_verts": c2, "b_in_a_max_mm": w2}
R["penetration"] = pen
log("intersections done", len(inter))

# ------------------------------------------------------------------ charging handle pull sweep
ch = OB["MAKO_ChargingHandle"]
sweep = {}
others = [n for n in def_n if n != "MAKO_ChargingHandle"]
for dy in (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06):
    M = Matrix.Translation((0, dy, 0)) @ ch.matrix_world
    bm = wbm(ch, M)
    t = BVHTree.FromBMesh(bm)
    hits = {n: len(t.overlap(BVH[n])) for n in others}
    sweep[str(dy)] = {n: k for n, k in hits.items() if k}
    bm.free()
R["ch_pull_sweep"] = sweep

# ------------------------------------------------------------------ mag drop (straight down 6 cm) vs lower
mags = {}
for m in ("MAKO_mag_30", "MAKO_mag_45", "MAKO_mag_drum60"):
    res = {}
    for dz in (0.0, -0.01, -0.02, -0.04, -0.06):
        k = 0
        for part in [m] + [c.name for c in OB[m].children if c.type == "MESH"]:
            o = OB[part]
            M = Matrix.Translation((0, 0, dz)) @ o.matrix_world
            bm = wbm(o, M)
            t = BVHTree.FromBMesh(bm)
            k += len(t.overlap(BVH["MAKO_Lower"]))
            bm.free()
        res[str(dz)] = k
    mags[m] = res
R["mag_drop_overlaps_with_lower"] = mags

# ------------------------------------------------------------------ magazine fit in the well (clearances)
def ray_gap(origin, direction, target):
    hit = BVH[target].ray_cast(Vector(origin), Vector(direction).normalized(), 0.2)
    return None if hit[0] is None else round((hit[0] - Vector(origin)).length * 1000, 2)


R["mag30_side_clearance_mm"] = {
    "+X": ray_gap((0.0, -0.12, -0.03), (1, 0, 0), "MAKO_Lower"),
    "mag_half_width_at_z-0.03": None,
}
# ------------------------------------------------------------------ sockets
R["sockets"] = {o.name: [round(v, 5) for v in o.matrix_world.translation] for o in bpy.data.objects
                if "_SOCKET_" in o.name}
R["sockets_rot"] = {o.name: [round(math.degrees(v), 3) for v in o.matrix_world.to_euler()] for o in bpy.data.objects
                    if "_SOCKET_" in o.name}

# ------------------------------------------------------------------ attachment fit (shared parts on the sockets)
def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


fits = {}
plan = [("optics/ATT_optic_holo.glb", "MAKO_SOCKET_Optic"), ("optics/ATT_optic_3x.glb", "MAKO_SOCKET_Optic"),
        ("optics/ATT_optic_reddot.glb", "MAKO_SOCKET_Optic"),
        ("tactical/ATT_grip_vertical.glb", "MAKO_SOCKET_Under"), ("tactical/ATT_grip_angled.glb", "MAKO_SOCKET_Under"),
        ("tactical/ATT_grip_stub.glb", "MAKO_SOCKET_Under"), ("tactical/ATT_ugl_launcher.glb", "MAKO_SOCKET_Under"),
        ("tactical/ATT_laser_R.glb", "MAKO_SOCKET_Side_R"), ("tactical/ATT_flashlight_L.glb", "MAKO_SOCKET_Side_L"),
        ("tactical/ATT_flashlight_R.glb", "MAKO_SOCKET_Side_R"), ("tactical/ATT_laser_L.glb", "MAKO_SOCKET_Side_L"),
        ("tactical/ATT_shield_front.glb", "MAKO_SOCKET_Shield")]
for rel, sname in plan:
    p = os.path.join(ATT, rel)
    if not os.path.exists(p):
        fits[rel] = "missing"
        continue
    new = import_glb(p)
    roots = [o for o in new if o.parent is None]
    for r in roots:
        r.location = OB[sname].matrix_world.translation
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    worst = 0.0
    nin = 0
    pairs = 0
    gap = 1.0
    for o in new:
        if o.type != "MESH":
            continue
        bm = wbm(o)
        t = BVHTree.FromBMesh(bm)
        for b in base_n + [n for n, h in health.items() if h["coll"] in ("MAKO_mag_30", "MAKO_stock_standard")]:
            k = len(t.overlap(BVH[b]))
            pairs += k
        for v in bm.verts:
            for b in ("MAKO_Rail", "MAKO_RailBottom", "MAKO_RailSide_R", "MAKO_RailSide_L", "MAKO_Handguard",
                      "MAKO_Upper", "MAKO_FlashHider", "MAKO_Barrel", "MAKO_mag_30"):
                loc, nrm, idx, dist = BVH[b].find_nearest(v.co)
                if loc is None:
                    continue
                gap = min(gap, dist)
                if (v.co - loc).dot(nrm) < -1e-6 and dist > 3e-4:
                    nin += 1
                    worst = max(worst, dist)
        bm.free()
    fits[rel] = {"socket": sname, "overlap_tri_pairs": pairs, "verts_inside_gun": nin,
                 "max_penetration_mm": round(worst * 1000, 2), "min_gap_mm": round(gap * 1000, 2)}
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
R["attachment_fit"] = fits
log("fits", json.dumps(fits))

# ------------------------------------------------------------------ FBX re-import
fbx = {}
for fn in ("mako_base.fbx", "MAKO_mag_30.fbx", "MAKO_stock_standard.fbx"):
    p = os.path.join(GLBDIR, fn)
    if not os.path.exists(p):
        continue
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=p)
    new = [o for o in bpy.data.objects if o not in before]
    socks = {o.name: [round(v, 4) for v in o.matrix_world.translation] for o in new if "_SOCKET_" in o.name}
    scl = {o.name: [round(v, 4) for v in o.matrix_world.to_scale()] for o in new if o.parent is None}
    mesh_b = None
    ms = [o for o in new if o.type == "MESH"]
    if ms:
        pts = [o.matrix_world @ Vector(c) for o in ms for c in o.bound_box]
        mesh_b = [[round(min(p[i] for p in pts), 4) for i in range(3)], [round(max(p[i] for p in pts), 4)
                                                                          for i in range(3)]]
    fbx[fn] = {"objects": len(new), "root_scale": scl, "sockets": socks, "bounds": mesh_b}
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
R["fbx"] = fbx

json.dump(R, open(OUTJ, "w"), indent=1, default=str)
log("WROTE", OUTJ)
