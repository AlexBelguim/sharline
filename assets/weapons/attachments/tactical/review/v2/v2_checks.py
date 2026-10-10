"""Independent review v2 (headless Blender 5.2) - checks on the CURRENT exports (UGL was rebuilt at 09:44,
after the first review pass).

  blender -b --factory-startup -P v2_checks.py

Writes review/v2/v2_checks.json.
1. Every ATT_*.glb re-imported in a fresh scene: nodes, parents, tris, UVs, materials, bounds, topology.
2. UGL on the real Mako (mako_default.glb) at BOTH Under heights: the glb's own socket node (z 0.0155) and the
   current sockets.json (z 0.0075, the Mako is being reworked: handguard bottom drops 8 mm).
   Clearances vs mag_30 / mag_45 / drum60, vs Mako meshes, vs shield; breech open sweep; trigger pull;
   muzzle vs shield; LeftHand.
3. Folded bipod width vs Warden handguard; laser top-face shading normals; shield glass layers.
"""
import json
import math
import os

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
WEAP = r"F:/git/val etf/assets/weapons"
OUT = os.path.join(HERE, "review", "v2", "v2_checks.json")
PARTS = ["grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "bipod", "laser_R", "laser_L",
         "flashlight_R", "flashlight_L", "shield_front"]
R = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def imp(path, loc=None):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        o.rotation_mode = "XYZ"
    root = next(o for o in new if o.parent is None)
    if loc is not None:
        root.location = loc
    bpy.context.view_layer.update()
    return root, new


def M(objs):
    return [o for o in objs if o.type == "MESH"]


def wbm(objs, merge=False):
    bm = bmesh.new()
    for o in objs:
        if o.type != "MESH":
            continue
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    if merge:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    return bm


def bvh(objs):
    bm = wbm(objs)
    t = BVHTree.FromBMesh(bm)
    vs = [v.co.copy() for v in bm.verts]
    bm.free()
    return t, vs


def overlap(a, b):
    return len(bvh(a)[0].overlap(bvh(b)[0]))


def clearance(a, b):
    ta, va = bvh(a)
    tb, vb = bvh(b)
    best = 1e9
    for v in va:
        d = tb.find_nearest(v)[3]
        if d is not None and d < best:
            best = d
    for v in vb:
        d = ta.find_nearest(v)[3]
        if d is not None and d < best:
            best = d
    return round(best, 5)


def inside_count(a_objs, b_objs):
    """vertices of a that lie inside closed mesh b (ray parity along +X)."""
    tb, _ = bvh(b_objs)
    _, va = bvh(a_objs)
    n = 0
    deepest = 0.0
    for v in va:
        hits = 0
        p = v.copy()
        for _ in range(40):
            loc, nor, i, d = tb.ray_cast(p, Vector((1, 0.0001, 0.0002)))
            if loc is None:
                break
            hits += 1
            p = loc + Vector((1e-6, 0, 0))
        if hits % 2 == 1:
            n += 1
            dd = tb.find_nearest(v)[3]
            deepest = max(deepest, dd or 0)
    return n, round(deepest, 5)


def bounds(objs):
    ws = [o.matrix_world @ v.co for o in M(objs) for v in o.data.vertices]
    return (Vector([min(w[i] for w in ws) for i in range(3)]), Vector([max(w[i] for w in ws) for i in range(3)]))


def r5(v):
    return [round(x, 5) for x in v]


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def topo(objs):
    bm = wbm(objs, merge=True)
    r = {"open_edges": sum(1 for e in bm.edges if len(e.link_faces) == 1),
         "nonmanifold_edges": sum(1 for e in bm.edges if len(e.link_faces) > 2),
         "loose_verts": sum(1 for v in bm.verts if not v.link_faces),
         "zero_area_faces": sum(1 for f in bm.faces if f.calc_area() < 1e-11),
         "sliver_tris_aspect_gt_60": 0}
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    for f in bm.faces:
        es = sorted(e.calc_length() for e in f.edges)
        a = f.calc_area()
        if a > 1e-12 and es[2] * es[2] / (2 * a) > 60:
            r["sliver_tris_aspect_gt_60"] += 1
    bm.free()
    return r


# ====================================================================================== 1. exports
exp = {}
for pid in PARTS:
    reset()
    root, objs = imp(os.path.join(HERE, f"ATT_{pid}.glb"))
    e = {"nodes": {}}
    for o in objs:
        d = {"type": o.type, "parent": o.parent.name if o.parent else None,
             "loc_local": r5(o.location), "rot_local_deg": [round(math.degrees(a), 3) for a in o.rotation_euler],
             "loc_world": r5(o.matrix_world.translation)}
        if o.type == "MESH":
            d["tris"] = tris(o)
            d["uv"] = [u.name for u in o.data.uv_layers]
            d["mats"] = [m.name if m else None for m in o.data.materials]
            d["custom_normals"] = bool(o.data.has_custom_normals)
        e["nodes"][o.name] = d
    e["total_tris"] = sum(tris(o) for o in M(objs))
    mn, mx = bounds(objs)
    e["bounds"] = [r5(mn), r5(mx)]
    e["size"] = r5(mx - mn)
    e["topology"] = topo(M(objs))
    exp[pid] = e
    print("EXP", pid, e["total_tris"], e["size"], e["topology"])
R["exports"] = exp


# ====================================================================================== 2. UGL on the Mako
def socks(path, prefix):
    with open(path) as fh:
        d = json.load(fh)
    return {k.replace(prefix + "_SOCKET_", ""): Vector(v["location"]) for k, v in d.items()}


MAKO_JSON = socks(os.path.join(WEAP, "ar7_mako", "sockets.json"), "MAKO")
WARDEN = socks(os.path.join(WEAP, "vk50_warden", "sockets.json"), "WARDEN")
ugl_res = {}
for tag in ("glb_socket", "sockets_json"):
    reset()
    groot, gun = imp(os.path.join(WEAP, "ar7_mako", "mako_default.glb"))
    gsock = {o.name.replace("MAKO_SOCKET_", ""): o.matrix_world.translation.copy() for o in gun
             if "SOCKET" in o.name}
    S = gsock if tag == "glb_socket" else MAKO_JSON
    mk = {o.name: o for o in M(gun)}
    mag30 = [o for n, o in mk.items() if n.startswith("MAKO_mag")]
    gun_nomag = [o for n, o in mk.items() if not n.startswith("MAKO_mag")]
    rails = [mk[n] for n in mk if n.startswith("MAKO_Rail")]
    _, ugl = imp(os.path.join(HERE, "ATT_ugl_launcher.glb"), S["Under"])
    _, sh = imp(os.path.join(HERE, "ATT_shield_front.glb"), S["Shield"])
    _, lzr = imp(os.path.join(HERE, "ATT_laser_R.glb"), S["Side_R"])
    _, fl = imp(os.path.join(HERE, "ATT_flashlight_L.glb"), S["Side_L"])
    body = [o for o in M(ugl) if o.parent is None]
    br = next(o for o in ugl if o.name.endswith("_Breech"))
    tr = next(o for o in ugl if o.name.endswith("_Trigger"))
    muz = next(o for o in ugl if o.name.endswith("_SOCKET_Muzzle"))
    lh = next(o for o in ugl if o.name.endswith("_SOCKET_LeftHand"))
    r = {"under_socket_used": r5(S["Under"])}
    r["ugl_vs_mag30_clear"] = clearance(M(ugl), mag30)
    r["ugl_vs_mag30_overlap"] = overlap(M(ugl), mag30)
    r["ugl_vs_gun_nonrail_overlap"] = {o.name: overlap(M(ugl), [o]) for o in gun_nomag
                                       if o not in rails and overlap(M(ugl), [o])}
    r["ugl_vs_gun_nonrail_clear"] = clearance(M(ugl), [o for o in gun_nomag if o not in rails])
    r["ugl_verts_inside_rails"] = inside_count(body, rails)
    r["ugl_top_vs_handguard_clear"] = clearance(M(ugl), [mk["MAKO_Handguard"]]) if "MAKO_Handguard" in mk else None
    r["ugl_vs_shield_overlap"] = overlap(M(ugl), M(sh))
    r["ugl_vs_shield_clear"] = clearance(M(ugl), M(sh))
    r["muzzle_world"] = r5(muz.matrix_world.translation)
    smn, smx = bounds([o for o in M(sh) if o.parent is None])
    r["shield_bounds"] = [r5(smn), r5(smx)]
    # shield plate back face y at the bore height band: nearest shield surface in +Y from the UGL muzzle
    tsh, _ = bvh(M(sh))
    hits = []
    mw = muz.matrix_world.translation
    for dx, dz in ((0, 0), (0, 0.0225), (0.0225, 0), (-0.0225, 0), (0, -0.0225), (0.016, 0.016), (-0.016, 0.016),
                   (0, 0.035)):
        loc, n, i, d = tsh.ray_cast(mw + Vector((dx, 0.0, dz)), Vector((0, -1, 0)), 3.0)
        hits.append({"offset_xz": [dx, dz], "hit": loc is not None})
    r["bore_rays_hit_shield"] = hits
    # grenade arc: launched at 0..15 deg elevation from the muzzle top edge - does it hit the shield?
    arc = {}
    for el in (0, 5, 10, 15, 25):
        d = Vector((0, -math.cos(math.radians(el)), math.sin(math.radians(el))))
        loc, n, i, dd = tsh.ray_cast(mw + Vector((0, 0, 0.0225)), d, 1.0)
        arc[el] = None if loc is None else round(dd, 4)
    r["grenade_top_edge_ray_vs_shield_by_elev_deg"] = arc
    r["lefthand_world"] = r5(lh.matrix_world.translation)
    r["lefthand_to_mag30"] = round(min((o.matrix_world @ v.co - lh.matrix_world.translation).length
                                       for o in mag30 for v in o.data.vertices), 4)
    # grip-to-mag gap per z slice (front of the UGL grip vs back... mag front surface)
    gbm = wbm(body)
    mbm = wbm(mag30)
    slices = {}
    for z in [x / 1000 for x in range(-20, -170, -10)]:
        gy = [v.co.y for v in gbm.verts if abs(v.co.z - z) < 0.004 and abs(v.co.x) < 0.02]
        my = [v.co.y for v in mbm.verts if abs(v.co.z - z) < 0.004 and abs(v.co.x) < 0.02]
        if gy and my:
            slices[round(z, 3)] = {"ugl_rear_y": round(max(gy), 4), "mag_front_y": round(min(my), 4),
                                   "gap": round(min(my) - max(gy), 4)}
    gbm.free()
    mbm.free()
    r["grip_to_mag_gap_by_z"] = slices
    # breech swing sweep
    sweep = {}
    for ang in (0, -10, -20, -30, -40):
        br.rotation_euler = (0, 0, math.radians(ang))
        bpy.context.view_layer.update()
        mn, mx = bounds([br])
        sweep[ang] = {"vs_body": overlap([br], body), "vs_body_inside": inside_count([br], body)[0],
                      "vs_mako_overlap": overlap([br], list(mk.values())),
                      "vs_shield_overlap": overlap([br], M(sh)), "vs_laser": overlap([br], M(lzr)),
                      "vs_flashlight": overlap([br], M(fl)), "breech_x_range": [round(mn.x, 4), round(mx.x, 4)],
                      "breech_y_range": [round(mn.y, 4), round(mx.y, 4)]}
    # which way does the breech END (rear of tube) move?
    br.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    rear0 = br.matrix_world @ Vector((0.0365, 0.074, 0.0))       # tube axis at the breech face, hinge-relative
    br.rotation_euler = (0, 0, math.radians(-40))
    bpy.context.view_layer.update()
    rear1 = br.matrix_world @ Vector((0.0365, 0.074, 0.0))
    sweep["tube_rear_centre_closed_to_open"] = [r5(rear0), r5(rear1)]
    br.rotation_euler = (0, 0, 0)
    r["breech_sweep"] = sweep
    # trigger
    trg = {}
    for ang in (0, 12):
        tr.rotation_euler = (math.radians(ang), 0, 0)
        bpy.context.view_layer.update()
        trg[ang] = {"overlap_body": overlap([tr], body), "inside_body": inside_count([tr], body)}
    tr.rotation_euler = (0, 0, 0)
    r["trigger"] = trg
    # alt mags
    for magf in ("MAKO_mag_45.glb", "MAKO_mag_drum60.glb"):
        p = os.path.join(WEAP, "ar7_mako", magf)
        _, mo = imp(p, gsock["Mag"])
        r["vs_" + magf] = {"overlap": overlap(M(ugl), M(mo)), "clear": clearance(M(ugl), M(mo))}
        for o in mo:
            bpy.data.objects.remove(o)
    ugl_res[tag] = r
    print("UGL", tag, json.dumps(r)[:1500])
R["ugl_on_mako"] = ugl_res

# ====================================================================================== 3. bipod folded width / Warden
reset()
_, war = imp(os.path.join(WEAP, "vk50_warden", "warden_default.glb"))
wk = {o.name: o for o in M(war)}
_, bp = imp(os.path.join(HERE, "ATT_bipod.glb"), WARDEN["Under"])
legs = [o for o in bp if "_Leg_" in o.name]
b = {}
mn, mx = bounds(bp)
b["deployed_x"] = [round(mn.x, 4), round(mx.x, 4)]
for lg in legs:
    lg.rotation_euler = (math.radians(lg["hinge_euler_x_folded_deg"]), 0, 0)
bpy.context.view_layer.update()
mn, mx = bounds(bp)
b["folded_bounds"] = [r5(mn), r5(mx)]
hg = [o for n, o in wk.items() if "Handguard" in n or "Chassis" in n]
if hg:
    hmn, hmx = bounds(hg)
    b["warden_handguard_x"] = [round(hmn.x, 4), round(hmx.x, 4)]
    b["folded_feet_stick_out_beyond_handguard_m"] = round(max(mx.x - hmx.x, hmn.x - mn.x), 4)
lows = [o for o in bp if "_LegLower_" in o.name]
b["folded_foot_lowest_z_below_socket"] = round(mn.z - WARDEN["Under"].z, 4)
R["bipod"] = b
print("BIPOD", b)

# ====================================================================================== 4. laser top shading normals
reset()
_, lz = imp(os.path.join(HERE, "ATT_laser_R.glb"))
body = next(o for o in lz if o.parent is None)
me = body.data
me.calc_loop_triangles() if hasattr(me, "calc_loop_triangles") else None
bad = []
cn = [Vector(cl.vector) for cl in me.corner_normals] if hasattr(me, "corner_normals") else None
for p in me.polygons:
    if p.normal.z > 0.95 and p.center.z > 0.0165:
        for li in p.loop_indices:
            n = cn[li] if cn else Vector(me.loops[li].normal)
            dev = math.degrees(n.angle(p.normal)) if n.length > 0 else 180
            if dev > 20:
                bad.append({"poly": p.index, "center": r5(p.center), "dev_deg": round(dev, 1), "nverts": len(p.vertices),
                            "area_mm2": round(p.area * 1e6, 2)})
R["laser_top_split_normal_deviation_gt20"] = {"count": len(bad), "samples": bad[:20]}
top_polys = [p for p in me.polygons if p.normal.z > 0.95 and p.center.z > 0.0165]
R["laser_top_faces"] = [{"i": p.index, "c": r5(p.center), "n": len(p.vertices), "area_mm2": round(p.area * 1e6, 2)}
                        for p in top_polys]
print("LASER TOP", R["laser_top_split_normal_deviation_gt20"]["count"], len(top_polys))

# ====================================================================================== 5. shield glass
reset()
_, sh = imp(os.path.join(HERE, "ATT_shield_front.glb"))
gl = next(o for o in sh if o.name.endswith("_Glass"))
mn, mx = bounds([gl])
mat = gl.data.materials[0]
R["shield_glass"] = {"bounds": [r5(mn), r5(mx)], "thickness_y": round(mx.y - mn.y, 4), "faces": len(gl.data.polygons),
                     "faces_facing_back(+Y)": sum(1 for p in gl.data.polygons if p.normal.y > 0.9),
                     "faces_facing_front(-Y)": sum(1 for p in gl.data.polygons if p.normal.y < -0.9),
                     "material": mat.name, "blend": getattr(mat, "surface_render_method", None),
                     "backface_culling": mat.use_backface_culling}
print("GLASS", R["shield_glass"])

with open(OUT, "w") as fh:
    json.dump(R, fh, indent=1, default=str)
print("wrote", OUT)
