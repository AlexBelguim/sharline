"""Independent review: technical checks on the MAKO .blend and GLB exports (read-only on the asset).
Run: blender -b --factory-startup -P rv_tech.py
Writes review/tech_report.json and prints a summary."""
import json
import math
import os
import sys
from itertools import combinations

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
OUT = os.path.join(HERE, "review")
REP = {}


def log(*a):
    print("[rv]", *a, flush=True)


bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, "mako.blend"))
dg = bpy.context.evaluated_depsgraph_get()

# ------------------------------------------------------------------ hierarchy / collections
cols = {c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections}
REP["collections"] = cols
objs = {o.name: o for o in bpy.data.objects}
REP["objects"] = {}
for o in bpy.data.objects:
    REP["objects"][o.name] = {
        "type": o.type, "parent": o.parent.name if o.parent else None,
        "loc_world": [round(v, 5) for v in o.matrix_world.translation],
        "rot": [round(math.degrees(v), 3) for v in o.matrix_world.to_euler()],
        "scale": [round(v, 4) for v in o.matrix_world.to_scale()],
        "mods": [m.type for m in o.modifiers] if o.type == "MESH" else [],
        "mats": [s.material.name if s.material else None for s in o.material_slots] if o.type == "MESH" else [],
    }


def emesh(o):
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(o.matrix_world)
    oe.to_mesh_clear()
    return bm


# ------------------------------------------------------------------ mesh health
health = {}
bvh = {}
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    bm = emesh(o)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    nm = [e for e in bm.edges if not e.is_manifold]
    boundary = [e for e in bm.edges if e.is_boundary]
    loose_v = [v for v in bm.verts if not v.link_edges]
    loose_e = [e for e in bm.edges if not e.link_faces]
    zero_f = [f for f in bm.faces if f.calc_area() < 1e-10]
    # signed volume: negative => normals point inward (flipped) for a closed mesh
    vol = 0.0
    for f in bm.faces:
        vs = [v.co for v in f.verts]
        for i in range(1, len(vs) - 1):
            vol += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
    # inconsistent normals: count edges where the two faces wind the same way
    bad_wind = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            f0, f1 = e.link_faces
            l0 = next(l for l in e.link_loops if l.face == f0)
            l1 = next(l for l in e.link_loops if l.face == f1)
            if l0.vert == l1.vert:
                bad_wind += 1
    # islands
    seen = set()
    islands = 0
    for f in bm.faces:
        if f.index in seen:
            continue
        islands += 1
        stack = [f]
        seen.add(f.index)
        while stack:
            g = stack.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    me = o.data
    no_mat = sum(1 for p in me.polygons if p.material_index >= len(o.material_slots)
                 or o.material_slots[p.material_index].material is None)
    mn = Vector((min(v.co.x for v in bm.verts), min(v.co.y for v in bm.verts), min(v.co.z for v in bm.verts)))
    mx = Vector((max(v.co.x for v in bm.verts), max(v.co.y for v in bm.verts), max(v.co.z for v in bm.verts)))
    health[o.name] = {
        "tris": tris, "non_manifold_edges": len(nm), "boundary_edges": len(boundary), "loose_verts": len(loose_v),
        "loose_edges": len(loose_e), "zero_area_faces": len(zero_f), "signed_volume_cm3": round(vol * 1e6, 3),
        "inconsistent_wind_edges": bad_wind, "islands": islands, "ngons": ngons, "uv_layers": len(me.uv_layers),
        "faces_without_material": no_mat,
        "bounds": [[round(v, 4) for v in mn], [round(v, 4) for v in mx]],
    }
    bvh[o.name] = BVHTree.FromBMesh(bm)
    bm.free()
REP["mesh_health"] = health

# ------------------------------------------------------------------ intersections between objects
def coll_of(name):
    for c, names in cols.items():
        if name in names:
            return c
    return None


groups = {
    "default": [n for n in health if coll_of(n) in ("MAKO_Base", "MAKO_stock_standard", "MAKO_mag_30")],
}
for extra in ("MAKO_stock_precision", "MAKO_stock_light", "MAKO_mag_45", "MAKO_mag_drum60"):
    groups[extra] = [n for n in health if coll_of(n) == extra]
inter = {}
base_names = [n for n in health if coll_of(n) == "MAKO_Base"]
pairs = list(combinations(groups["default"], 2))
for extra in ("MAKO_stock_precision", "MAKO_stock_light", "MAKO_mag_45", "MAKO_mag_drum60"):
    pairs += [(a, b) for a in groups[extra] for b in base_names]
    pairs += list(combinations(groups[extra], 2))
for a, b in pairs:
    hits = bvh[a].overlap(bvh[b])
    if hits:
        inter[f"{a} x {b}"] = len(hits)
REP["intersections"] = inter

# ------------------------------------------------------------------ bounds of the default loadout
def bounds(names):
    mn = Vector((1e9,) * 3)
    mx = Vector((-1e9,) * 3)
    for n in names:
        b = health[n]["bounds"]
        mn = Vector([min(mn[i], b[0][i]) for i in range(3)])
        mx = Vector([max(mx[i], b[1][i]) for i in range(3)])
    return [[round(v, 4) for v in mn], [round(v, 4) for v in mx], [round(v, 4) for v in (mx - mn)]]


REP["bounds_default"] = bounds(groups["default"])
for g in groups:
    if g != "default":
        REP[f"bounds_{g}"] = bounds(groups[g])
REP["tris_default"] = sum(health[n]["tris"] for n in groups["default"])


# ------------------------------------------------------------------ rail measurements via ray casts
def ray(o_name, origin, direction, dist=1.0):
    loc, nrm, idx, d = bvh[o_name].ray_cast(Vector(origin), Vector(direction).normalized(), dist)
    return None if loc is None else [round(v, 5) for v in loc]


rail = {}
# top rail width at a tooth (socket Optic y) - cast from +-X sideways at z just below rail top
for y in (-0.0855, -0.090, -0.30, -0.4755):
    row = {}
    row["top_z_center"] = ray("MAKO_Rail", (0, y, 0.2), (0, 0, -1))
    for z in (0.0835, 0.082, 0.079, 0.0765):
        l = ray("MAKO_Rail", (0.1, y, z), (-1, 0, 0))
        r = ray("MAKO_Rail", (-0.1, y, z), (1, 0, 0))
        row[f"width_at_z{z}"] = round(l[0] - r[0], 5) if (l and r) else None
    rail[f"top_y{y}"] = row
# slot pitch along the top: scan y and record where the rail top is low (slot) vs high
prof = []
y = -0.50
while y < 0.03:
    h = ray("MAKO_Rail", (0, y, 0.2), (0, 0, -1))
    prof.append((round(y, 4), h[2] if h else None))
    y += 0.0005
slots = []
inside = False
for yy, z in prof:
    low = z is not None and z < 0.0825
    if low and not inside:
        start = yy
        inside = True
    if not low and inside:
        slots.append((start + yy) / 2)
        inside = False
pitches = [round(slots[i + 1] - slots[i], 4) for i in range(len(slots) - 1)]
rail["top_slot_centres_first5"] = [round(s, 4) for s in slots[:5]]
rail["top_slot_count"] = len(slots)
rail["top_slot_pitch_set"] = sorted(set(pitches))
rail["top_rail_extent_y"] = [p[0] for p in prof if p[1] is not None][:1] + [p[0] for p in prof if p[1] is not None][-1:]
# bottom rail face and side rail face
rail["bottom_face_at_under"] = ray("MAKO_RailBottom", (0, -0.335, -0.2), (0, 0, 1))
rail["side_R_face"] = ray("MAKO_RailSide_R", (-0.2, -0.449, 0.050), (1, 0, 0))
rail["side_L_face"] = ray("MAKO_RailSide_L", (0.2, -0.449, 0.050), (-1, 0, 0))
# bottom rail width
for nm_, o_, d_ in (("bottom", (0, -0.335, 0.0165), None),):
    l = ray("MAKO_RailBottom", (0.1, -0.335, 0.017), (-1, 0, 0))
    r = ray("MAKO_RailBottom", (-0.1, -0.335, 0.017), (1, 0, 0))
    rail["bottom_width_near_face"] = round(l[0] - r[0], 5) if (l and r) else None
REP["rail"] = rail

# ------------------------------------------------------------------ sockets
sock = {}
for o in bpy.data.objects:
    if "_SOCKET_" in o.name:
        sock[o.name] = {"parent": o.parent.name if o.parent else None,
                        "loc": [round(v, 5) for v in o.matrix_world.translation],
                        "rot_deg": [round(math.degrees(v), 4) for v in o.matrix_world.to_euler()],
                        "type": o.empty_display_type if o.type == "EMPTY" else o.type}
REP["sockets"] = sock

# ------------------------------------------------------------------ magazine fit: can the mag slide straight down out of the well?
# move mag_30 down in 5 mm steps along -Z (and along its own curve is not modeled) and count overlaps with the lower
fit = {}
for mk in ("MAKO_mag_30", "MAKO_mag_45", "MAKO_mag_drum60"):
    if mk not in objs:
        continue
    o = objs[mk]
    bm = emesh(o)
    res = []
    for dz in (0.0, -0.01, -0.02, -0.03, -0.04, -0.05):
        bm2 = bm.copy()
        bmesh.ops.translate(bm2, verts=bm2.verts, vec=(0, 0, dz))
        t = BVHTree.FromBMesh(bm2)
        res.append((dz, len(t.overlap(bvh["MAKO_Lower"]))))
        bm2.free()
    bm.free()
    fit[mk] = res
REP["mag_drop_overlap_with_lower"] = fit

# mag origin sanity: in local space the top-front lip should be at the origin
for mk in ("MAKO_mag_30", "MAKO_mag_45", "MAKO_mag_drum60", "MAKO_stock_standard", "MAKO_stock_precision",
           "MAKO_stock_light"):
    o = objs.get(mk)
    if not o:
        continue
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    xs = [v.co for v in me.vertices]
    REP.setdefault("part_local_bounds", {})[mk] = {
        "origin_world": [round(v, 5) for v in o.matrix_world.translation],
        "min": [round(min(c[i] for c in xs), 4) for i in range(3)],
        "max": [round(max(c[i] for c in xs), 4) for i in range(3)]}
    oe.to_mesh_clear()

# ------------------------------------------------------------------ materials
mats = {}
for m in bpy.data.materials:
    if m.users == 0:
        continue
    info = {"users": m.users, "nodes": [n.type for n in m.node_tree.nodes] if m.use_nodes else []}
    p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m.use_nodes else None
    if p:
        def g(nm_):
            s = p.inputs.get(nm_)
            if s is None:
                return None
            if s.is_linked:
                return "linked:" + s.links[0].from_node.type
            v = s.default_value
            try:
                return [round(x, 3) for x in v]
            except TypeError:
                return round(v, 3)
        info.update({k: g(k) for k in ("Base Color", "Roughness", "Metallic", "Emission Color", "Emission Strength",
                                        "Alpha")})
    info["backface_culling"] = m.use_backface_culling
    mats[m.name] = info
REP["materials"] = mats
imgs = {i.name: {"size": list(i.size), "packed": bool(i.packed_file), "cs": i.colorspace_settings.name}
        for i in bpy.data.images if i.users}
REP["images"] = imgs

# ------------------------------------------------------------------ texel density sanity (uv area vs world area)
td = {}
for o in bpy.data.objects:
    if o.type != "MESH" or not o.data.uv_layers:
        continue
    me = o.data
    uv = me.uv_layers.active.data
    wa = 0.0
    ua = 0.0
    flipped_uv = 0
    for p in me.polygons:
        wa += p.area
        pts = [uv[li].uv for li in p.loop_indices]
        a = 0.0
        for i in range(len(pts)):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % len(pts)]
            a += x1 * y2 - x2 * y1
        ua += abs(a) / 2
        if a < 0:
            flipped_uv += 1
    sc = o.matrix_world.to_scale()
    wa *= sc.x * sc.y
    td[o.name] = {"uv_area": round(ua, 4), "world_area_cm2": round(wa * 1e4, 2),
                  "uv_per_m": round(math.sqrt(ua / wa), 2) if wa else None, "flipped_uv_faces": flipped_uv,
                  "faces": len(me.polygons)}
REP["uv"] = td

with open(os.path.join(OUT, "tech_report.json"), "w") as f:
    json.dump(REP, f, indent=1)
log("wrote tech_report.json")

# short console summary
log("TRIS default", REP["tris_default"], "BOUNDS", REP["bounds_default"])
for n, h in health.items():
    flags = []
    if h["non_manifold_edges"]:
        flags.append(f"nonman {h['non_manifold_edges']}")
    if h["loose_verts"] or h["loose_edges"]:
        flags.append(f"loose {h['loose_verts']}/{h['loose_edges']}")
    if h["zero_area_faces"]:
        flags.append(f"zero {h['zero_area_faces']}")
    if h["signed_volume_cm3"] < 0:
        flags.append(f"NEG VOL {h['signed_volume_cm3']}")
    if h["inconsistent_wind_edges"]:
        flags.append(f"wind {h['inconsistent_wind_edges']}")
    if h["faces_without_material"]:
        flags.append(f"nomat {h['faces_without_material']}")
    if h["uv_layers"] == 0:
        flags.append("NO UV")
    log(f"{n:34s} tris {h['tris']:5d} isl {h['islands']:3d} ngons {h['ngons']:3d} vol {h['signed_volume_cm3']:9.3f} "
        + " ".join(flags))
log("INTERSECTIONS")
for k, v in sorted(inter.items(), key=lambda kv: -kv[1]):
    log(f"   {k}: {v}")
log("RAIL", json.dumps(rail, indent=0))
log("MAGFIT", fit)
log("PARTS", json.dumps(REP["part_local_bounds"]))
for n, s in sock.items():
    log("SOCK", n, s)
for n, m in mats.items():
    log("MAT", n, m)
log("IMG", imgs)
