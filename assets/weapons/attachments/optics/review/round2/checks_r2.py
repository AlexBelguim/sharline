"""Round-2 reviewer: technical checks on the exported optics (read-only on the asset; writes review/round2/).

"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P checks_r2.py

Per .glb (imported in a fresh scene = proves it loads): node names, extras, ADS socket, bounds vs the spec,
tris, UVs, manifold / boundary / loose / degenerate, inverted islands, z-fight candidates between islands,
sight-line ray tests from the eye point (what does the eye hit first; is the reticle visible; is the glint visible
from the front), and the on-gun snap (socket from sockets.json and from the gun .glb, clash pairs, rail under it).
Per .fbx: loads, node names, bounds/axes after import, materials and packed images.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
R2 = os.path.join(OUT, "review", "round2")
OPTICS = ["optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"]
GUNS = {"MAKO": (r"F:/git/val etf/assets/weapons/ar7_mako/mako_base.glb",
                 r"F:/git/val etf/assets/weapons/ar7_mako/sockets.json", "MAKO_SOCKET_Optic"),
        "WARDEN": (r"F:/git/val etf/assets/weapons/vk50_warden/warden_base.glb",
                   r"F:/git/val etf/assets/weapons/vk50_warden/sockets.json", "WARDEN_SOCKET_Optic")}


def wipe():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def world_bm(o):
    bm = bmesh.new()
    dg = bpy.context.evaluated_depsgraph_get()
    bm.from_object(o.evaluated_get(dg), dg)
    bm.transform(o.matrix_world)
    return bm


def islands(bm):
    seen = set()
    out = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        isl = []
        seen.add(f.index)
        while stack:
            cf = stack.pop()
            isl.append(cf)
            for e in cf.edges:
                for lf in e.link_faces:
                    if lf.index not in seen:
                        seen.add(lf.index)
                        stack.append(lf)
        out.append(isl)
    return out


def signed_volume(faces):
    v = 0.0
    for f in faces:
        vs = [l.vert.co for l in f.loops]
        for i in range(1, len(vs) - 1):
            v += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
    return v


def mesh_checks(o):
    bm = world_bm(o)
    bm.faces.ensure_lookup_table()
    res = {"tris": sum(len(f.verts) - 2 for f in bm.faces), "uv_layers": len(o.data.uv_layers),
           "materials": [s.material.name if s.material else None for s in o.material_slots]}
    nm = [e for e in bm.edges if not e.is_manifold]
    res["non_manifold_edges"] = len(nm)
    res["boundary_edges"] = sum(1 for e in bm.edges if e.is_boundary)
    res["loose_verts"] = sum(1 for v in bm.verts if not v.link_edges)
    res["degenerate_faces"] = sum(1 for f in bm.faces if f.calc_area() < 1e-11)
    res["tiny_faces_lt_0.01mm2"] = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    if nm:
        mids = [(e.verts[0].co + e.verts[1].co) / 2 for e in nm[:400]]
        res["non_manifold_bbox"] = [[round(min(m[i] for m in mids), 4) for i in range(3)],
                                    [round(max(m[i] for m in mids), 4) for i in range(3)]]
    isl = islands(bm)
    res["islands"] = len(isl)
    inv, open_isl = [], 0
    for fs in isl:
        if not all(e.is_manifold for f in fs for e in f.edges):
            open_isl += 1
            continue
        vol = signed_volume(fs)
        if vol < -1e-12:
            c = sum((f.calc_center_median() for f in fs), Vector()) / len(fs)
            inv.append({"centre": [round(x, 4) for x in c], "vol_mm3": round(vol * 1e9, 3)})
    res["open_islands"] = open_isl
    res["inverted_islands"] = inv
    # z-fight candidates: a face of one island coplanar (within 0.06 mm) with a face of another island
    zf = []
    if len(isl) > 1:
        fidx = {}
        for k, fs in enumerate(isl):
            for f in fs:
                fidx[f.index] = k
        tree = BVHTree.FromPolygons([v.co.copy() for v in bm.verts], [[v.index for v in f.verts] for f in bm.faces])
        for f in bm.faces:
            if f.calc_area() < 2e-7:
                continue
            c = f.calc_center_median()
            for hit in (tree.find_nearest_range(c, 6e-5) or []):
                loc, nrm, idx, dist = hit
                if idx is None or idx == f.index or fidx.get(idx) == fidx[f.index]:
                    continue
                if abs(nrm.dot(f.normal)) > 0.995:
                    zf.append([round(x, 4) for x in c])
                    break
    res["zfight_candidates"] = len(zf)
    res["zfight_samples"] = zf[:10]
    bm.free()
    return res


def bvh_of(objs):
    verts, polys, owner = [], [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        bm = bmesh.new()
        bm.from_object(o.evaluated_get(dg), dg)
        bm.transform(o.matrix_world)
        off = len(verts)
        verts += [v.co.copy() for v in bm.verts]
        for f in bm.faces:
            polys.append([v.index + off for v in f.verts])
            owner.append(o.name)
        bm.free()
    return BVHTree.FromPolygons(verts, polys), verts, polys, owner


def bounds(objs):
    mn = Vector((1e9,) * 3)
    mx = Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    return mn, mx


def first_hits(tree, owner, origin, direction, maxn=6):
    """Successive hits along a ray (re-cast from just past each hit)."""
    out = []
    o = origin.copy()
    d = direction.normalized()
    for _ in range(maxn):
        h = tree.ray_cast(o, d, 2.0)
        if h[0] is None:
            break
        out.append((owner[h[2]], round((h[0] - origin).length, 4), round(h[1].dot(d), 3)))
        o = h[0] + d * 1e-5
    return out


def rv(v, n=4):
    return [round(x, n) for x in v]


def main():
    os.makedirs(R2, exist_ok=True)
    cat = {e["id"]: e for e in json.load(open(os.path.join(OUT, "catalog.json")))["optics"]}
    report = {}
    for oid in OPTICS:
        wipe()
        new = import_glb(os.path.join(OUT, "ATT_%s.glb" % oid))
        meshes = [o for o in new if o.type == "MESH"]
        root = bpy.data.objects.get("ATT_" + oid)
        ads = bpy.data.objects.get("ATT_%s_SOCKET_ADS" % oid)
        mn, mx = bounds(meshes)
        c = cat[oid]
        r = {"objects": sorted((o.name, o.type, o.parent.name if o.parent else None) for o in new),
             "root_extras": {k: (v if isinstance(v, (int, float, str)) else str(v)) for k, v in root.items()
                             if not k.startswith("_")} if root else None,
             "ads_loc": rv(ads.matrix_world.translation) if ads else None,
             "ads_rot_deg": rv([math.degrees(a) for a in ads.matrix_world.to_euler()], 2) if ads else None,
             "ads_extras": {k: (v if isinstance(v, (int, float, str)) else str(v)) for k, v in ads.items()} if ads else None,
             "bbox_min": rv(mn), "bbox_max": rv(mx), "dims": rv(mx - mn),
             "catalog_dims": [c["width_m"], c["length_m"], c["height_m"]],
             "catalog_ads": c["ads_location_m"], "eye_relief": c["eye_relief_m"]}
        r["ads_height_in_band_0.04_0.075"] = bool(ads and 0.04 <= ads.matrix_world.translation.z <= 0.075)
        tot = 0
        r["meshes"] = {}
        for o in meshes:
            mc = mesh_checks(o)
            tot += mc["tris"]
            r["meshes"][o.name] = mc
        r["tris_total"] = tot
        r["budget_ok_1.5k_5k"] = 1500 <= tot <= 5000
        tree, verts, polys, owner = bvh_of(meshes)
        # lowest body point, clamp underside on the centreline (should be ~ +0.0001 above the rail top)
        body = [o for o in meshes if o.name.endswith("_Body")]
        bt, bv, bp, bo = bvh_of(body)
        und = []
        for i in range(161):
            y = mn.y + (mx.y - mn.y) * i / 160
            h = bt.ray_cast(Vector((0, y, -0.03)), Vector((0, 0, 1)), 0.2)
            if h[0] is not None and h[0].z < 0.02:
                und.append(round(h[0].z, 5))
        r["centreline_underside_z_min_max"] = [min(und), max(und)] if und else None
        r["lowest_z"] = round(mn.z, 4)
        # sight-line rays from the eye point (socket + Y * eye relief)
        if ads:
            s = ads.matrix_world.translation.copy()
            eye = s + Vector((0, c["eye_relief_m"], 0))
            r["eye_point"] = rv(eye)
            r["sightline_hits_from_eye"] = first_hits(tree, owner, eye, Vector((0, -1, 0)))
            r["sightline_hits_from_front"] = first_hits(tree, owner, Vector((0, mn.y - 0.3, s.z)), Vector((0, 1, 0)))
            # blocked fraction of a +-12 deg cone from the eye (1x sights) using the body only
            blocked, n = 0, 0
            for ia in range(-6, 7):
                for ib in range(-6, 7):
                    a, b = math.radians(ia * 2.0), math.radians(ib * 2.0)
                    d = Vector((math.sin(a), -1.0, math.sin(b))).normalized()
                    n += 1
                    h = bt.ray_cast(eye, d, 1.0)
                    if h[0] is not None:
                        blocked += 1
            r["body_blocks_frac_of_+-12deg_cone"] = round(blocked / n, 3)
            # the reticle / glint: where are they relative to the socket and glass
            for suf in ("Reticle", "Glint", "Glass", "Ocular", "Objective", "Display", "StatusLight"):
                ob = bpy.data.objects.get("ATT_%s_%s" % (oid, suf))
                if ob:
                    a0, a1 = bounds([ob])
                    r["bounds_" + suf] = [rv(a0), rv(a1)]
            ret = bpy.data.objects.get("ATT_%s_Reticle" % oid)
            if ret:
                a0, a1 = bounds([ret])
                rc = (a0 + a1) / 2
                r["reticle_centre"] = rv(rc, 5)
                r["reticle_offset_from_sightline_mm"] = rv((rc - Vector((0, rc.y, s.z))) * 1000, 2)
                r["reticle_diam_mm"] = round((a1.x - a0.x) * 1000, 2)
                dist = (eye - rc).length
                r["reticle_ang_diam_moa"] = round(math.degrees(2 * math.atan((a1.x - a0.x) / 2 / dist)) * 60, 1)
                r["eye_to_reticle_hits"] = first_hits(tree, owner, eye, rc - eye)
            gl = bpy.data.objects.get("ATT_%s_Glint" % oid)
            if gl:
                a0, a1 = bounds([gl])
                gc = (a0 + a1) / 2
                r["glint_centre"] = rv(gc, 5)
                r["glint_diam_mm"] = round((a1.x - a0.x) * 1000, 2)
                frm = gc + Vector((0.05, -1.0, 0.25))
                r["front_3q_to_glint_hits"] = first_hits(tree, owner, frm, gc - frm)
                frm = gc + Vector((0.0, -1.0, 0.0))
                r["front_to_glint_hits"] = first_hits(tree, owner, frm, gc - frm)
        report[oid] = r
        print(oid, json.dumps({k: r[k] for k in ("dims", "ads_loc", "tris_total")}))

    # FBX
    fbx = {}
    for oid in OPTICS:
        wipe()
        new = import_fbx(os.path.join(OUT, "ATT_%s.fbx" % oid))
        meshes = [o for o in new if o.type == "MESH"]
        mn, mx = bounds(meshes)
        ads = bpy.data.objects.get("ATT_%s_SOCKET_ADS" % oid)
        imgs = [(im.name, im.packed_file is not None, tuple(im.size)) for im in bpy.data.images]
        mats = sorted({s.material.name for o in meshes for s in o.material_slots if s.material})
        texmats = []
        for m in bpy.data.materials:
            if m.use_nodes and any(n.type == "TEX_IMAGE" and n.image for n in m.node_tree.nodes):
                texmats.append(m.name)
        fbx[oid] = {"objects": sorted(o.name for o in new), "dims": rv(mx - mn), "bbox_min": rv(mn), "bbox_max": rv(mx),
                    "ads_loc": rv(ads.matrix_world.translation) if ads else None,
                    "scales": sorted({tuple(rv(o.matrix_world.to_scale(), 3)) for o in new}),
                    "materials": mats, "textured_materials": texmats, "images": imgs,
                    "tris": sum(len(p.vertices) - 2 for o in meshes for p in o.data.polygons)}
        print("FBX", oid, fbx[oid]["dims"], fbx[oid]["ads_loc"], len(imgs))
    report["fbx"] = fbx

    # on-gun snap
    gun = {}
    for g, (glb, sj, sock) in GUNS.items():
        for oid in OPTICS:
            if g not in cat[oid]["compatible_weapons"]:
                continue
            wipe()
            gnew = import_glb(glb)
            gmesh = [o for o in gnew if o.type == "MESH"]
            sn = bpy.data.objects.get(sock)
            s_glb = sn.matrix_world.translation.copy() if sn else None
            s_json = Vector(json.load(open(sj))[sock]["location"])
            onew = import_glb(os.path.join(OUT, "ATT_%s.glb" % oid))
            root = bpy.data.objects.get("ATT_" + oid)
            root.location = s_glb if s_glb is not None else s_json
            bpy.context.view_layer.update()
            oall = [o for o in onew if o.type == "MESH"]
            gt, gv, gp, go = bvh_of(gmesh)
            ot, ov, op, oo = bvh_of(oall)
            pairs = gt.overlap(ot)
            locs = [sum((ov[i] for i in op[oi]), Vector()) / len(op[oi]) - root.location for gi, oi in pairs[:4000]]
            gparts = sorted({go[gi] for gi, oi in pairs})
            ent = {"socket_json": rv(s_json), "socket_glb": rv(s_glb) if s_glb else None,
                   "json_vs_glb_mm": round((s_json - s_glb).length * 1000, 2) if s_glb else None,
                   "clash_pairs": len(pairs), "clash_gun_parts": gparts}
            if locs:
                ent["clash_local_bbox"] = [[round(min(c[i] for c in locs), 4) for i in range(3)],
                                           [round(max(c[i] for c in locs), 4) for i in range(3)]]
            tops = []
            for dy in (-0.04, -0.02, 0.0, 0.02, 0.04):
                h = gt.ray_cast(root.location + Vector((0, dy, 0.05)), Vector((0, 0, -1)), 0.2)
                tops.append(None if h[0] is None else round(h[0].z - root.location.z, 5))
            ent["rail_top_rel_socket_z"] = tops
            # gun's own sights / parts above the rail inside the optic footprint (e.g. a rear sight under the optic)
            mn, mx = bounds(oall)
            above = []
            for o in gmesh:
                a0, a1 = bounds([o])
                if a1.z > root.location.z + 0.002 and a0.y < mx.y and a1.y > mn.y and abs((a0.x + a1.x) / 2) < 0.05:
                    above.append((o.name, round(a1.z - root.location.z, 4)))
            ent["gun_parts_above_rail_in_footprint"] = above
            # eye point to the gun's rear (stock/charging handle): does the gun block the sight line?
            ads = bpy.data.objects.get("ATT_%s_SOCKET_ADS" % oid)
            eye = ads.matrix_world.translation + Vector((0, cat[oid]["eye_relief_m"], 0))
            h = gt.ray_cast(eye, Vector((0, -1, 0)), 3.0)
            ent["eye_forward_hits_gun"] = None if h[0] is None else [go[h[2]], round((h[0] - eye).length, 3)]
            gun.setdefault(g, {})[oid] = ent
            print(g, oid, ent)
    report["on_gun"] = gun
    with open(os.path.join(R2, "checks_r2.json"), "w") as f:
        json.dump(report, f, indent=1)
    print("WROTE", os.path.join(R2, "checks_r2.json"))


if __name__ == "__main__":
    main()
