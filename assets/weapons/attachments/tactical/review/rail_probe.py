"""Reviewer probe: what exactly overlaps between the clamps and the real gun rails, and the moving-part poses
(glTF import sets quaternion rotation mode, so poses are applied via rotation_mode = 'XYZ').
  blender -b --factory-startup -P rail_probe.py
"""
import json
import math
import os
from collections import Counter

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
WEAP = r"F:/git/val etf/assets/weapons"
OUT = os.path.join(HERE, "review", "rail_probe.json")
REP = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        o.rotation_mode = "XYZ"
    return new


def tri_bm(objs):
    bm = bmesh.new()
    for o in objs:
        if o.type != "MESH":
            continue
        me = o.data.copy()
        me.transform(o.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    return bm


def sockets(path, prefix):
    with open(path) as fh:
        d = json.load(fh)
    return {k.replace(prefix + "_SOCKET_", ""): Vector(v["location"]) for k, v in d.items()}


MAKO = sockets(os.path.join(WEAP, "ar7_mako", "sockets.json"), "MAKO")
WARDEN = sockets(os.path.join(WEAP, "vk50_warden", "sockets.json"), "WARDEN")


def place(pid, loc):
    objs = import_glb(os.path.join(HERE, f"ATT_{pid}.glb"))
    root = next(o for o in objs if o.parent is None)
    root.location = loc
    bpy.context.view_layer.update()
    return root, objs


def inside_depth(part_objs, solid_objs):
    """part vertices strictly inside the closed solid (ray parity along 3 axes, majority) + max depth."""
    sb = tri_bm(solid_objs)
    bmesh.ops.remove_doubles(sb, verts=sb.verts, dist=1e-6)
    tree = BVHTree.FromBMesh(sb)
    pb = tri_bm(part_objs)
    cnt = 0
    depth = 0.0
    where = []
    for v in pb.verts:
        votes = 0
        for d in (Vector((0.0, 0.0, 1.0)), Vector((0.31, 0.95, 0.0)).normalized(), Vector((1.0, 0.13, 0.27)).normalized()):
            p = v.co.copy()
            hits = 0
            for _ in range(40):
                loc, n, i, dist = tree.ray_cast(p, d)
                if loc is None:
                    break
                hits += 1
                p = loc + d * 1e-7
            votes += hits % 2
        if votes >= 2:
            loc, n, i, dist = tree.find_nearest(v.co)
            if dist > 2e-5:
                cnt += 1
                depth = max(depth, dist)
                where.append([round(c, 4) for c in v.co])
    sb.free()
    pb.free()
    return cnt, depth, sorted(where, key=lambda w: w[1])[:8]


def overlap_detail(part_objs, gun_objs, origin):
    pb = tri_bm(part_objs)
    gb = tri_bm(gun_objs)
    tp = BVHTree.FromBMesh(pb)
    tg = BVHTree.FromBMesh(gb)
    pairs = tp.overlap(tg)
    cop = 0
    loc_hist = Counter()
    for a, b in pairs:
        fa, fb = pb.faces[a], gb.faces[b]
        na, nb = fa.normal, fb.normal
        # coplanar contact? normals (anti)parallel and same plane
        if abs(abs(na.dot(nb)) - 1) < 1e-4 and abs((fa.verts[0].co - fb.verts[0].co).dot(nb)) < 2e-5:
            cop += 1
            continue
        c = fa.calc_center_median() - origin
        loc_hist[(round(c.x, 3), round(c.z, 3))] += 1
    pb.free()
    gb.free()
    return {"pairs": len(pairs), "coplanar_contact_pairs": cop, "crossing_pairs": len(pairs) - cop,
            "crossing_part_tri_centres_xz_rel_socket": [list(k) + [v] for k, v in loc_hist.most_common(12)]}


def rail_section(rail_obj, y, tol=0.0008):
    ws = [rail_obj.matrix_world @ v.co for v in rail_obj.data.vertices]
    pts = sorted({(round(w.x, 4), round(w.z, 4)) for w in ws if abs(w.y - y) < tol})
    return pts


# ============================================================ Mako
reset()
mako = import_glb(os.path.join(WEAP, "ar7_mako", "mako_default.glb"))
bpy.context.view_layer.update()
mk = {o.name: o for o in mako if o.type == "MESH"}
REP["mako_rail_bottom_section_at_under"] = rail_section(mk["MAKO_RailBottom"], MAKO["Under"].y, 0.006)
REP["mako_rail_top_section_at_shield"] = rail_section(mk["MAKO_Rail"], MAKO["Shield"].y, 0.006)
REP["mako_rail_side_R_section"] = rail_section(mk["MAKO_RailSide_R"], MAKO["Side_R"].y, 0.006)
# rail extents along y
for n in ("MAKO_Rail", "MAKO_RailBottom", "MAKO_RailSide_R", "MAKO_RailSide_L", "MAKO_Handguard", "MAKO_Barrel",
          "MAKO_FlashHider"):
    ws = [mk[n].matrix_world @ v.co for v in mk[n].data.vertices]
    REP[n + "_bounds"] = [[round(min(w[i] for w in ws), 4) for i in range(3)],
                          [round(max(w[i] for w in ws), 4) for i in range(3)]]

for pid, sk, rail in (("grip_vertical", "Under", "MAKO_RailBottom"), ("grip_angled", "Under", "MAKO_RailBottom"),
                      ("grip_stub", "Under", "MAKO_RailBottom"), ("ugl_launcher", "Under", "MAKO_RailBottom"),
                      ("laser_R", "Side_R", "MAKO_RailSide_R"), ("flashlight_L", "Side_L", "MAKO_RailSide_L"),
                      ("shield_front", "Shield", "MAKO_Rail")):
    root, objs = place(pid, MAKO[sk])
    meshes = [o for o in objs if o.type == "MESH"]
    d = overlap_detail(meshes, [mk[rail]], MAKO[sk])
    n, dep, wh = inside_depth(meshes, [mk[rail]])
    d["part_verts_inside_rail"] = n
    d["max_penetration_m"] = round(dep, 5)
    d["inside_samples"] = wh
    # clamp section near the socket
    ws = [root.matrix_world @ v.co - MAKO[sk] for v in root.data.vertices]
    REP["mako_" + pid] = d
    print("MAKO", pid, json.dumps(d))
    for o in objs:
        bpy.data.objects.remove(o)

# ---- UGL closed: what overlaps between Breech and body; UGL vs shield detail
root, ugl = place("ugl_launcher", MAKO["Under"])
sroot, sh = place("shield_front", MAKO["Shield"])
br = next(o for o in ugl if o.name.endswith("_Breech"))
body = [o for o in ugl if o.parent is None]
d = overlap_detail([br], body, MAKO["Under"])
n, dep, wh = inside_depth([br], body)
d["breech_verts_inside_body"] = n
d["max_penetration_m"] = round(dep, 5)
d["inside_samples_rel_world"] = wh
REP["ugl_closed_breech_vs_body"] = d
print("UGL closed breech vs body", json.dumps(d))
d = overlap_detail([o for o in ugl if o.type == "MESH"], [o for o in sh if o.type == "MESH"], MAKO["Under"])
n, dep, wh = inside_depth([o for o in sh if o.type == "MESH"], [br])
d["shield_verts_inside_ugl_tube"] = n
d["max_penetration_m"] = round(dep, 5)
d["samples"] = wh
REP["ugl_vs_shield"] = d
print("UGL vs shield", json.dumps(d))
# ---- open the breech properly
br.rotation_euler = (0, 0, math.radians(br["open_angle_deg"]))
bpy.context.view_layer.update()
muz = next(o for o in ugl if o.name.endswith("_SOCKET_Muzzle"))
r = {"open_muzzle_world": [round(v, 4) for v in muz.matrix_world.translation]}
r.update({"vs_body": overlap_detail([br], body, MAKO["Under"])})
r["vs_shield"] = overlap_detail([br], [o for o in sh if o.type == "MESH"], MAKO["Under"])
r["vs_mako"] = overlap_detail([br], list(mk.values()), MAKO["Under"])
ws = [br.matrix_world @ v.co for v in br.data.vertices]
r["open_bounds"] = [[round(min(w[i] for w in ws), 4) for i in range(3)], [round(max(w[i] for w in ws), 4) for i in range(3)]]
# breech rear end opening: min y of breech rear face corner vs body breech face
REP["ugl_open"] = r
print("UGL open", json.dumps(r))
br.rotation_euler = (0, 0, 0)
tr = next(o for o in ugl if o.name.endswith("_Trigger"))
for ang in (12, -12):
    tr.rotation_euler = (math.radians(ang), 0, 0)
    bpy.context.view_layer.update()
    REP[f"ugl_trigger_{ang}"] = overlap_detail([tr], body, MAKO["Under"])
    print("trigger", ang, REP[f"ugl_trigger_{ang}"])
tr.rotation_euler = (0, 0, 0)
bpy.context.view_layer.update()
REP["ugl_trigger_0"] = overlap_detail([tr], body, MAKO["Under"])
print("trigger 0", REP["ugl_trigger_0"])

# ============================================================ Warden
reset()
war = import_glb(os.path.join(WEAP, "vk50_warden", "warden_default.glb"))
bpy.context.view_layer.update()
wk = {o.name: o for o in war if o.type == "MESH"}
low = sorted(((min((o.matrix_world @ v.co).z for v in o.data.vertices), n) for n, o in wk.items()))[:5]
REP["warden_lowest_meshes"] = [[round(z, 4), n] for z, n in low]
REP["warden_rail_bottom_section"] = rail_section(wk["WARDEN_RailBottom"], WARDEN["Under"].y, 0.006)
root, bp = place("bipod", WARDEN["Under"])
meshes = [o for o in bp if o.type == "MESH"]
d = overlap_detail(meshes, [wk["WARDEN_RailBottom"]], WARDEN["Under"])
n, dep, wh = inside_depth(meshes, [wk["WARDEN_RailBottom"]])
d["verts_inside"] = n
d["max_penetration_m"] = round(dep, 5)
REP["warden_bipod_rail"] = d
print("BIPOD rail", json.dumps(d))
legs = [o for o in bp if "_Leg_" in o.name]
lowers = [o for o in bp if "_LegLower_" in o.name]
print("leg rot", [tuple(round(math.degrees(a), 2) for a in l.rotation_euler) for l in legs])
for lg in legs:
    e = lg.rotation_euler.copy()
    lg.rotation_euler = (math.radians(lg["hinge_euler_x_folded_deg"]), e.y, e.z)
bpy.context.view_layer.update()
r = {"leg_euler_deg": [[round(math.degrees(a), 2) for a in l.rotation_euler] for l in legs]}
r["vs_warden"] = {n: overlap_detail(meshes, [o], WARDEN["Under"])["crossing_pairs"] for n, o in wk.items()}
r["vs_warden"] = {k: v for k, v in r["vs_warden"].items() if v}
r["legs_vs_clamp"] = overlap_detail(legs + lowers, [root], WARDEN["Under"])
r["leg_vs_leg"] = overlap_detail([legs[0]] + [l for l in lowers if l.parent == legs[0]],
                                 [legs[1]] + [l for l in lowers if l.parent == legs[1]], WARDEN["Under"])
ws = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
r["bounds"] = [[round(min(w[i] for w in ws), 4) for i in range(3)], [round(max(w[i] for w in ws), 4) for i in range(3)]]


def mind(a, b):
    ta = BVHTree.FromBMesh(tri_bm(a))
    best = 9
    for o in b:
        for v in o.data.vertices:
            loc, n, i, dd = ta.find_nearest(o.matrix_world @ v.co)
            if dd is not None:
                best = min(best, dd)
    return round(best, 5)


r["clear_vs_barrel"] = mind(legs + lowers, [wk["WARDEN_Barrel"]])
r["clear_vs_handguard"] = mind(legs + lowers, [wk["WARDEN_Handguard"]])
REP["bipod_folded"] = r
print("BIPOD folded", json.dumps(r))
# deployed: knuckle vs head; lower vs upper (telescope)
for lg in legs:
    e = lg.rotation_euler.copy()
    lg.rotation_euler = (math.radians(lg["hinge_euler_x_deployed_deg"]), e.y, e.z)
bpy.context.view_layer.update()
REP["bipod_deployed_legs_vs_clamp"] = overlap_detail(legs + lowers, [root], WARDEN["Under"])
print("BIPOD deployed legs vs clamp", REP["bipod_deployed_legs_vs_clamp"])
# mid fold: sweep the hinge to see if the leg sweeps through the head during folding
sweep = {}
for ang in range(-40, -95, -10):
    for lg in legs:
        e = lg.rotation_euler.copy()
        lg.rotation_euler = (math.radians(ang), e.y, e.z)
    bpy.context.view_layer.update()
    sweep[ang] = {"vs_clamp_crossing": overlap_detail(legs + lowers, [root], WARDEN["Under"])["crossing_pairs"],
                  "vs_warden_crossing": sum(overlap_detail(legs + lowers, [o], WARDEN["Under"])["crossing_pairs"]
                                            for o in wk.values())}
REP["bipod_fold_sweep"] = sweep
print("SWEEP", sweep)

with open(OUT, "w") as fh:
    json.dump(REP, fh, indent=1)
print("wrote", OUT)
