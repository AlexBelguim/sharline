"""Independent reviewer checks for the ATT tactical set (headless Blender 5.2).

  blender -b --factory-startup -P review_checks.py

1. Each exported ATT_*.glb is imported into a fresh scene: node names / hierarchy / custom props, tris, UVs,
   materials per object, bounds; topology on a merged-by-distance copy: open edges, non-manifold edges,
   loose verts, zero-area faces, per-shell inward normals (ray parity test per closed shell).
2. Fit on the real gun exports (mako_default.glb, warden_default.glb, alt mags) placed via sockets.json:
   triangle overlaps (BVH) and clearances between parts and gun meshes / between attachments.
3. Sight line: optic_holo ADS point -> rays forward through the mounted shield.
Writes review/review_checks.json and prints a summary.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
WEAP = r"F:/git/val etf/assets/weapons"
OUT = os.path.join(HERE, "review", "review_checks.json")
PARTS = ["grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "bipod", "laser_R", "laser_L",
         "flashlight_R", "flashlight_L", "shield_front"]
REPORT = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def world_bm(objs, merge=True):
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


def bvh_of(objs):
    bm = world_bm(objs, merge=False)
    t = BVHTree.FromBMesh(bm)
    nverts = [v.co.copy() for v in bm.verts]
    bm.free()
    return t, nverts


def shells(bm):
    seen = set()
    out = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        comp = []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        out.append(comp)
    return out


def topo(objs):
    bm = world_bm(objs, merge=True)
    open_e = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    nm_e = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    loose_v = sum(1 for v in bm.verts if not v.link_faces)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-11)
    sh = shells(bm)
    inward = 0
    inward_faces = 0
    open_shells = 0
    shell_report = []
    for comp in sh:
        closed = all(len(e.link_faces) == 2 for f in comp for e in f.edges)
        if not closed:
            open_shells += 1
            continue
        sbm = bmesh.new()
        vmap = {}
        for f in comp:
            vs = []
            for v in f.verts:
                if v.index not in vmap:
                    vmap[v.index] = sbm.verts.new(v.co)
                vs.append(vmap[v.index])
            try:
                sbm.faces.new(vs)
            except ValueError:
                pass
        sbm.faces.ensure_lookup_table()
        tree = BVHTree.FromBMesh(sbm)
        # signed volume
        vol = 0.0
        for f in sbm.faces:
            vs = [v.co for v in f.verts]
            for i in range(1, len(vs) - 1):
                vol += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
        bad = 0
        for f in sbm.faces:
            if f.calc_area() < 1e-10:
                continue
            c = f.calc_center_median()
            n = f.normal
            o = c + n * 1e-6
            hits = 0
            d = 0.0
            p = o
            for _ in range(50):
                loc, nor, idx, dist = tree.ray_cast(p, n)
                if loc is None:
                    break
                hits += 1
                p = loc + n * 1e-6
            if hits % 2 == 1:
                bad += 1
        nf = len(sbm.faces)
        if vol < 0 or bad > 0.5 * nf:
            inward += 1
        inward_faces += bad
        shell_report.append({"faces": nf, "vol_cm3": round(vol * 1e6, 4), "inward_faces": bad})
        sbm.free()
    r = {"verts": len(bm.verts), "faces": len(bm.faces), "open_edges": open_e, "nonmanifold_edges": nm_e,
         "loose_verts": loose_v, "zero_area_faces": zero, "shells": len(sh), "open_shells": open_shells,
         "inverted_shells": inward, "inward_facing_faces_in_closed_shells": inward_faces,
         "worst_shells": sorted(shell_report, key=lambda s: -s["inward_faces"])[:4]}
    bm.free()
    return r


def tris_of(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def bounds(objs):
    ws = [o.matrix_world @ v.co for o in objs if o.type == "MESH" for v in o.data.vertices]
    mn = Vector([min(w[i] for w in ws) for i in range(3)])
    mx = Vector([max(w[i] for w in ws) for i in range(3)])
    return mn, mx


# ============================================================================================ 1. export checks
exp = {}
for pid in PARTS:
    reset()
    objs = import_glb(os.path.join(HERE, f"ATT_{pid}.glb"))
    bpy.context.view_layer.update()
    meshes = [o for o in objs if o.type == "MESH"]
    r = {"objects": {}}
    for o in objs:
        e = {"type": o.type, "parent": o.parent.name if o.parent else None,
             "loc_world": [round(v, 5) for v in o.matrix_world.translation],
             "rot_world_deg": [round(math.degrees(a), 2) for a in o.matrix_world.to_euler()],
             "props": {k: (o[k] if isinstance(o[k], (int, float, str)) else str(o[k])) for k in o.keys()
                       if not k.startswith("_")}}
        if o.type == "MESH":
            me = o.data
            e["tris"] = tris_of(o)
            e["uv_layers"] = [u.name for u in me.uv_layers]
            e["materials"] = [m.name if m else None for m in me.materials]
            # UV sanity: any NaN / all-zero
            uvs = [d.uv for d in me.uv_layers[0].data] if me.uv_layers else []
            e["uv_range"] = ([round(min(u.x for u in uvs), 3), round(max(u.x for u in uvs), 3),
                              round(min(u.y for u in uvs), 3), round(max(u.y for u in uvs), 3)] if uvs else None)
            # zero-area UV faces
            zuv = 0
            if me.uv_layers:
                uvl = me.uv_layers[0].data
                for p in me.polygons:
                    pts = [uvl[li].uv for li in p.loop_indices]
                    a = 0.0
                    for i in range(1, len(pts) - 1):
                        a += abs((pts[i] - pts[0]).cross(pts[i + 1] - pts[0])) / 2
                    if a < 1e-12:
                        zuv += 1
            e["zero_area_uv_faces"] = zuv
            mn, mx = bounds([o])
            e["bounds"] = [[round(v, 4) for v in mn], [round(v, 4) for v in mx]]
        r["objects"][o.name] = e
    r["total_tris"] = sum(tris_of(o) for o in meshes)
    mn, mx = bounds(meshes)
    r["bounds"] = [[round(v, 4) for v in mn], [round(v, 4) for v in mx]]
    r["size"] = [round(v, 4) for v in (mx - mn)]
    r["topology_all"] = topo(meshes)
    r["topology_per_object"] = {o.name: topo([o]) for o in meshes}
    exp[pid] = r
    print("EXPORT", pid, r["total_tris"], r["size"], r["topology_all"])
REPORT["exports"] = exp


# ============================================================================================ 2. fit checks
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


def overlap(a, b):
    ta, _ = bvh_of(a)
    tb, _ = bvh_of(b)
    return len(ta.overlap(tb))


def clearance(a, b, sample=None):
    """min distance from vertices of a to surface of b (and vice versa)."""
    ta, va = bvh_of(a)
    tb, vb = bvh_of(b)
    best = 1e9
    for v in va:
        loc, n, i, d = tb.find_nearest(v)
        if d is not None and d < best:
            best = d
    for v in vb:
        loc, n, i, d = ta.find_nearest(v)
        if d is not None and d < best:
            best = d
    return best


def M(objs):
    return [o for o in objs if o.type == "MESH"]


fit = {}
# ---------------- Mako
reset()
mako = import_glb(os.path.join(WEAP, "ar7_mako", "mako_default.glb"))
bpy.context.view_layer.update()
mk = {o.name: o for o in mako if o.type == "MESH"}
mag = [mk[n] for n in mk if n.startswith("MAKO_mag_30")]
rails = {n: mk[n] for n in ("MAKO_Rail", "MAKO_RailBottom", "MAKO_RailSide_L", "MAKO_RailSide_R")}
gun_all = list(mk.values())
print("MAKO meshes", list(mk))

placed = {}
for pid, sk in (("grip_vertical", "Under"), ("ugl_launcher", "Under"), ("laser_R", "Side_R"),
                ("flashlight_L", "Side_L"), ("shield_front", "Shield")):
    placed[pid] = place(pid, MAKO[sk])
for pid, (root, objs) in placed.items():
    r = {"overlap_tris_vs_mako": overlap(M(objs), gun_all)}
    rail = {"grip_vertical": "MAKO_RailBottom", "ugl_launcher": "MAKO_RailBottom", "laser_R": "MAKO_RailSide_R",
            "flashlight_L": "MAKO_RailSide_L", "shield_front": "MAKO_Rail"}[pid]
    clamp_objs = [o for o in M(objs) if o.parent is None]
    r["overlap_vs_rail"] = overlap(clamp_objs, [rails[rail]])
    r["clearance_to_rail_m"] = round(clearance(clamp_objs, [rails[rail]]), 5)
    per = {}
    for n, o in mk.items():
        k = overlap(M(objs), [o])
        if k:
            per[n] = k
    r["overlap_by_gun_mesh"] = per
    fit["mako_" + pid] = r
    print("FIT", pid, r)

ugl_root, ugl = placed["ugl_launcher"]
sh_root, sh = placed["shield_front"]
r = {}
r["ugl_vs_mag30_clear_m"] = round(clearance(M(ugl), mag), 5)
r["ugl_vs_shield_overlap"] = overlap(M(ugl), M(sh))
r["ugl_vs_shield_clear_m"] = round(clearance(M(ugl), M(sh)), 5)
br = next(o for o in ugl if o.name.endswith("_Breech"))
# muzzle socket world
muz = next(o for o in ugl if o.name.endswith("_SOCKET_Muzzle"))
r["ugl_muzzle_world"] = [round(v, 4) for v in muz.matrix_world.translation]
shield_mesh_bounds = bounds([o for o in M(sh) if o.parent is None])
r["shield_bounds_world"] = [[round(v, 4) for v in b] for b in shield_mesh_bounds]
# ray from UGL bore forward: does the grenade path hit the shield?
tsh, _ = bvh_of(M(sh))
hits = []
mw = muz.matrix_world.translation
for dx, dz in ((0, 0), (0, 0.0225), (0.0225, 0), (-0.0225, 0), (0, -0.0225), (0.016, 0.016), (-0.016, 0.016)):
    o_ = mw + Vector((dx, 0.05, dz))
    loc, n, i, d = tsh.ray_cast(o_, Vector((0, -1, 0)), 2.0)
    hits.append({"offset": [dx, dz], "hit": loc is not None, "dist": round(d, 4) if d else None})
r["ugl_bore_rays_vs_shield"] = hits
# open breech
br.rotation_euler.z = math.radians(br["open_angle_deg"])
bpy.context.view_layer.update()
r["ugl_open_overlap_vs_mako"] = overlap([br], gun_all)
r["ugl_open_overlap_vs_ugl_body"] = overlap([br], [o for o in M(ugl) if o.parent is None])
r["ugl_open_overlap_vs_shield"] = overlap([br], M(sh))
r["ugl_open_clear_vs_shield_m"] = round(clearance([br], M(sh)), 5)
r["ugl_open_muzzle_world"] = [round(v, 4) for v in muz.matrix_world.translation]
mnb, mxb = bounds([br])
r["ugl_open_breech_bounds"] = [[round(v, 4) for v in mnb], [round(v, 4) for v in mxb]]
br.rotation_euler.z = 0
bpy.context.view_layer.update()
# trigger pull
tr = next(o for o in ugl if o.name.endswith("_Trigger"))
tr.rotation_euler.x = math.radians(tr["pull_angle_deg"])
bpy.context.view_layer.update()
r["ugl_trigger_pulled_overlap_vs_body"] = overlap([tr], [o for o in M(ugl) if o.parent is None])
tr.rotation_euler.x = -math.radians(tr["pull_angle_deg"])
bpy.context.view_layer.update()
r["ugl_trigger_pulled_neg_overlap_vs_body"] = overlap([tr], [o for o in M(ugl) if o.parent is None])
tr.rotation_euler.x = 0
bpy.context.view_layer.update()
# lights vs shield
r["laser_R_vs_shield_clear_m"] = round(clearance(M(placed["laser_R"][1]), M(sh)), 5)
r["flashlight_L_vs_shield_clear_m"] = round(clearance(M(placed["flashlight_L"][1]), M(sh)), 5)
r["laser_R_vs_shield_overlap"] = overlap(M(placed["laser_R"][1]), M(sh))
r["flashlight_L_vs_shield_overlap"] = overlap(M(placed["flashlight_L"][1]), M(sh))
r["shield_vs_barrel_clear_m"] = round(clearance(M(sh), [mk["MAKO_Barrel"], mk["MAKO_FlashHider"]]), 5)
r["shield_vs_handguard_clear_m"] = round(clearance(M(sh), [mk["MAKO_Handguard"]]), 5)
# beam sockets -> do beams hit the shield?
for pid in ("laser_R", "flashlight_L"):
    bs = next(o for o in placed[pid][1] if o.name.endswith("_SOCKET_Beam"))
    loc, n, i, d = tsh.ray_cast(bs.matrix_world.translation, Vector((0, -1, 0)), 2.0)
    r[pid + "_beam_hits_shield"] = loc is not None
fit["mako_combo"] = r
print("COMBO", r)

# flashlight_R and laser_L too (other sides) vs shield
for pid, sk in (("flashlight_R", "Side_R"), ("laser_L", "Side_L")):
    root, objs = place(pid, MAKO[sk])
    fit["mako_" + pid] = {"overlap_tris_vs_mako": overlap(M(objs), gun_all),
                          "clear_vs_shield_m": round(clearance(M(objs), M(sh)), 5),
                          "overlap_vs_shield": overlap(M(objs), M(sh))}
    print("FIT", pid, fit["mako_" + pid])
    for o in objs:
        bpy.data.objects.remove(o)

# other grips on the Mako
for pid in ("grip_angled", "grip_stub"):
    root, objs = place(pid, MAKO["Under"])
    fit["mako_" + pid] = {"overlap_tris_vs_mako": overlap(M(objs), gun_all),
                          "clearance_to_rail_m": round(clearance([o for o in M(objs) if o.parent is None],
                                                                 [rails["MAKO_RailBottom"]]), 5),
                          "clear_vs_mag30_m": round(clearance(M(objs), mag), 5)}
    lh = next(o for o in objs if o.name.endswith("SOCKET_LeftHand"))
    fit["mako_" + pid]["lefthand_world"] = [round(v, 4) for v in lh.matrix_world.translation]
    print("FIT", pid, fit["mako_" + pid])
    for o in objs:
        bpy.data.objects.remove(o)

# alt magazines vs UGL
for magf in ("MAKO_mag_45.glb", "MAKO_mag_drum60.glb"):
    p = os.path.join(WEAP, "ar7_mako", magf)
    if not os.path.exists(p):
        continue
    mo = import_glb(p)
    mroot = next(o for o in mo if o.parent is None)
    mroot.location = MAKO["Mag"]
    bpy.context.view_layer.update()
    fit["ugl_vs_" + magf] = {"overlap": overlap(M(ugl), M(mo)), "clear_m": round(clearance(M(ugl), M(mo)), 5)}
    print("MAG", magf, fit["ugl_vs_" + magf])
    for o in mo:
        bpy.data.objects.remove(o)

# grip LeftHand / UGL LeftHand world positions
lh = next(o for o in ugl if o.name.endswith("SOCKET_LeftHand"))
fit["ugl_lefthand_world"] = [round(v, 4) for v in lh.matrix_world.translation]
fit["ugl_lefthand_to_mag30_m"] = round(min((v - lh.matrix_world.translation).length
                                           for o in mag for v in (o.matrix_world @ w.co for w in o.data.vertices)), 4)

# ---------------- sight line: optic_holo on the Mako + shield
holo = import_glb(os.path.join(WEAP, "attachments", "optics", "ATT_optic_holo.glb"))
hroot = next(o for o in holo if o.parent is None)
hroot.location = MAKO["Optic"]
bpy.context.view_layer.update()
ads = next(o for o in holo if o.name.endswith("SOCKET_ADS")).matrix_world.translation.copy()
sl = {"ads_world": [round(v, 4) for v in ads], "ads_above_rail_m": round(ads.z - MAKO["Optic"].z, 4)}
tplate, _ = bvh_of([o for o in M(sh) if o.parent is None])
tglass, _ = bvh_of([o for o in M(sh) if o.name.endswith("_Glass")])
grid = []
blocked = 0
total = 0
for ax in range(-8, 9):         # yaw deg
    for az in range(-8, 9):     # pitch deg
        d = Vector((math.tan(math.radians(ax)), -1.0, math.tan(math.radians(az)))).normalized()
        lp, _, _, dp = tplate.ray_cast(ads, d, 3.0)
        lg, _, _, dg = tglass.ray_cast(ads, d, 3.0)
        total += 1
        if lp is not None and (lg is None or dp < dg):
            blocked += 1
            grid.append((ax, az))
sl["blocked_dirs_of_17x17_(+-8deg)"] = blocked
sl["blocked_dirs"] = grid
# vertical free window through the glass on the centre line (deg)
free = [az / 4 for az in range(-60, 61) if (lambda d: (lambda lp, lg: lp[0] is None or (lg[0] is not None and lg[3] < lp[3]))(
    tplate.ray_cast(ads, d, 3.0), tglass.ray_cast(ads, d, 3.0)))(Vector((0, -1, math.tan(math.radians(az / 4)))).normalized())]
sl["centre_vertical_clear_deg_range"] = [min(free), max(free)] if free else None
freeh = [ax / 4 for ax in range(-80, 81) if (lambda d: (lambda lp, lg: lp[0] is None or (lg[0] is not None and lg[3] < lp[3]))(
    tplate.ray_cast(ads, d, 3.0), tglass.ray_cast(ads, d, 3.0)))(Vector((math.tan(math.radians(ax / 4)), -1, 0)).normalized())]
sl["centre_horizontal_clear_deg_range"] = [min(freeh), max(freeh)] if freeh else None
# distance eye -> shield glass
lg, _, _, dg = tglass.ray_cast(ads, Vector((0, -1, 0)), 3.0)
sl["ads_to_glass_m"] = round(dg, 4) if dg else None
fit["sightline_holo"] = sl
print("SIGHT", {k: v for k, v in sl.items() if k != "blocked_dirs"})

# ---------------- Warden + bipod
reset()
war = import_glb(os.path.join(WEAP, "vk50_warden", "warden_default.glb"))
bpy.context.view_layer.update()
wk = {o.name: o for o in war if o.type == "MESH"}
wall = list(wk.values())
root, bp = place("bipod", WARDEN["Under"])
r = {"overlap_vs_warden": overlap(M(bp), wall),
     "clearance_to_rail_m": round(clearance([root], [wk["WARDEN_RailBottom"]]), 5),
     "overlap_vs_rail": overlap([root], [wk["WARDEN_RailBottom"]])}
mnw, mxw = bounds(M(bp))
r["foot_lowest_world_z"] = round(mnw.z, 4)
r["bore_z"] = WARDEN["Muzzle"].z
r["bore_above_ground_m"] = round(WARDEN["Muzzle"].z - mnw.z, 4)
# lowest point of the gun itself (mag, monopod) vs ground: would the gun rest on the bipod?
mng, mxg = bounds(wall)
r["warden_lowest_z"] = round(mng.z, 4)
r["warden_lowest_above_bipod_ground_m"] = round(mng.z - mnw.z, 4)
legs = [o for o in bp if "_Leg_" in o.name]
lowers = [o for o in bp if "_LegLower_" in o.name]
# foot contact: soles level?
soles = []
for o in lowers:
    ws = [o.matrix_world @ v.co for v in o.data.vertices]
    zmin = min(w.z for w in ws)
    soles.append(round(zmin, 5))
    flat = [w for w in ws if w.z < zmin + 0.0005]
    soles.append(len(flat))
r["soles_zmin_and_flat_vert_count"] = soles
# folded pose
for lg in legs:
    lg.rotation_euler.x = math.radians(lg["hinge_euler_x_folded_deg"])
bpy.context.view_layer.update()
r["folded_overlap_vs_warden"] = overlap(M(bp), wall)
per = {}
for n, o in wk.items():
    k = overlap(M(bp), [o])
    if k:
        per[n] = k
r["folded_overlap_by_mesh"] = per
r["folded_overlap_leg_vs_leg"] = overlap([legs[0]] + [l for l in lowers if l.parent == legs[0]],
                                         [legs[1]] + [l for l in lowers if l.parent == legs[1]])
r["folded_overlap_legs_vs_clamp"] = overlap(legs + lowers, [root])
mnf, mxf = bounds(M(bp))
r["folded_bounds"] = [[round(v, 4) for v in mnf], [round(v, 4) for v in mxf]]
r["folded_clear_vs_barrel_m"] = round(clearance(legs + lowers, [wk["WARDEN_Barrel"]]), 5)
r["folded_clear_vs_handguard_m"] = round(clearance(legs + lowers, [wk["WARDEN_Handguard"]]), 5)
for lg in legs:
    lg.rotation_euler.x = math.radians(lg["hinge_euler_x_deployed_deg"])
# telescoped
for lo in lowers:
    lo.location = lo.location + lo.matrix_basis.to_3x3() @ Vector((0, 0, -lo["telescope_max_m"]))
bpy.context.view_layer.update()
mnt, mxt = bounds(M(bp))
r["telescoped_max_bore_above_ground_m"] = round(WARDEN["Muzzle"].z - mnt.z, 4)
# deployed: overlap upper/lower leg (telescoped) -- tube must stay inside the upper
fit["warden_bipod"] = r
print("BIPOD", r)

# grips + lights on the Warden (catalog claims compatibility)
for pid, sk in (("grip_vertical", "Under"), ("laser_R", "Side_R"), ("flashlight_L", "Side_L")):
    root, objs = place(pid, WARDEN[sk])
    fit["warden_" + pid] = {"overlap_vs_warden": overlap(M(objs), wall)}
    print("WARDEN FIT", pid, fit["warden_" + pid])
    for o in objs:
        bpy.data.objects.remove(o)

REPORT["fit"] = fit
with open(OUT, "w") as fh:
    json.dump(REPORT, fh, indent=1, default=str)
print("wrote", OUT)
