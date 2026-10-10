"""Reviewer's technical checks for the ATT optics (read-only on the asset; writes only into review/).

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P review_checks.py

Per exported .glb (imported in a fresh scene, which also proves the export loads):
  dimensions, root / ADS socket, tris, UVs, non-manifold / boundary edges, loose geometry, degenerate faces,
  inverted islands (negative signed volume), coplanar-overlap (z-fight) candidates between islands,
  glass-vs-body clearance, and on-gun clash / rail-fit checks against the real MAKO / WARDEN exports.
Writes review/checks.json.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
REV = os.path.join(OUT, "review")
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


def world_bm(o):
    bm = bmesh.new()
    dg = bpy.context.evaluated_depsgraph_get()
    bm.from_object(o.evaluated_get(dg), dg)
    bm.transform(o.matrix_world)
    return bm


def islands(bm):
    bm.verts.ensure_lookup_table()
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
    bm.edges.ensure_lookup_table()
    res = {}
    res["tris"] = sum(len(f.verts) - 2 for f in bm.faces)
    res["uv_layers"] = len(o.data.uv_layers)
    res["materials"] = [s.material.name if s.material else None for s in o.material_slots]
    nm = [e for e in bm.edges if not e.is_manifold]
    res["non_manifold_edges"] = len(nm)
    res["boundary_edges"] = sum(1 for e in bm.edges if e.is_boundary)
    res["wire_edges"] = sum(1 for e in bm.edges if e.is_wire)
    res["loose_verts"] = sum(1 for v in bm.verts if not v.link_edges)
    res["degenerate_faces"] = sum(1 for f in bm.faces if f.calc_area() < 1e-11)
    if nm:
        mids = [(e.verts[0].co + e.verts[1].co) / 2 for e in nm[:400]]
        res["non_manifold_sample_bbox"] = [[round(min(m[i] for m in mids), 4) for i in range(3)],
                                           [round(max(m[i] for m in mids), 4) for i in range(3)]]
    isl = islands(bm)
    res["islands"] = len(isl)
    inv = []
    open_isl = 0
    for k, fs in enumerate(isl):
        closed = all(e.is_manifold for f in fs for e in f.edges)
        if not closed:
            open_isl += 1
            continue
        vol = signed_volume(fs)
        if vol < -1e-12:
            c = sum((f.calc_center_median() for f in fs), Vector()) / len(fs)
            inv.append({"centre": [round(x, 4) for x in c], "vol_mm3": round(vol * 1e9, 3)})
    res["open_islands"] = open_isl
    res["inverted_islands"] = inv
    # z-fight candidates: face centres of one island lying on another island's surface with the same normal
    zf = []
    if len(isl) > 1:
        fidx = {}
        for k, fs in enumerate(isl):
            for f in fs:
                fidx[f.index] = k
        verts = [v.co.copy() for v in bm.verts]
        polys = [[v.index for v in f.verts] for f in bm.faces]
        tree = BVHTree.FromPolygons(verts, polys)
        for f in bm.faces:
            if f.calc_area() < 2e-7:
                continue
            c = f.calc_center_median()
            n = f.normal
            # look slightly outward and inward for another island's face that is parallel and coincident
            for hit in (tree.find_nearest_range(c, 6e-5) or []):
                loc, nrm, idx, dist = hit
                if idx is None or idx == f.index or fidx.get(idx) == fidx[f.index]:
                    continue
                if abs(nrm.dot(n)) > 0.995:
                    zf.append({"at": [round(x, 4) for x in c], "dist_mm": round(dist * 1000, 3),
                               "same_dir": nrm.dot(n) > 0})
                    break
        # cluster
    res["zfight_candidates"] = len(zf)
    res["zfight_samples"] = zf[:12]
    bm.free()
    return res


def bbox(objs):
    mn = Vector((1e9,) * 3)
    mx = Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    return mn, mx


def bvh_of(objs):
    verts, polys = [], []
    dg = bpy.context.evaluated_depsgraph_get()
    for o in objs:
        bm = bmesh.new()
        bm.from_object(o.evaluated_get(dg), dg)
        bm.transform(o.matrix_world)
        off = len(verts)
        verts += [v.co.copy() for v in bm.verts]
        polys += [[v.index + off for v in f.verts] for f in bm.faces]
        bm.free()
    return BVHTree.FromPolygons(verts, polys), verts, polys


def main():
    os.makedirs(REV, exist_ok=True)
    cat = {e["id"]: e for e in json.load(open(os.path.join(OUT, "catalog.json")))["optics"]}
    report = {}
    for oid in OPTICS:
        wipe()
        new = import_glb(os.path.join(OUT, "ATT_%s.glb" % oid))
        names = sorted(o.name for o in new)
        meshes = [o for o in new if o.type == "MESH"]
        root = bpy.data.objects.get("ATT_" + oid)
        ads = bpy.data.objects.get("ATT_%s_SOCKET_ADS" % oid)
        mn, mx = bbox(meshes)
        r = {"objects": names,
             "root_loc": [round(x, 5) for x in root.matrix_world.translation] if root else None,
             "ads_loc": [round(x, 5) for x in ads.matrix_world.translation] if ads else None,
             "ads_parent": ads.parent.name if ads and ads.parent else None,
             "ads_rot": [round(x, 4) for x in ads.matrix_world.to_euler()] if ads else None,
             "bbox_min": [round(x, 4) for x in mn], "bbox_max": [round(x, 4) for x in mx],
             "dims": [round(x, 4) for x in (mx - mn)],
             "catalog": {k: cat[oid][k] for k in ("length_m", "width_m", "height_m", "ads_height_m", "tris")}}
        tot = 0
        r["meshes"] = {}
        for o in meshes:
            mc = mesh_checks(o)
            tot += mc["tris"]
            r["meshes"][o.name] = mc
        r["tris_total"] = tot
        # lowest point of the optic vs the rail top (z=0): jaws should go below, flat underside 0.1 mm above
        body = [o for o in meshes if o.name.endswith("_Body")]
        tree, verts, polys = bvh_of(body)
        # clamp underside height on the centreline: ray straight up from below the rail top
        hits = []
        y0, y1 = (cat[oid]["ads_location_m"][1] - 0.2, 0.2)
        for y in [i * 0.002 - 0.2 for i in range(201)]:
            h = tree.ray_cast(Vector((0, y, -0.02)), Vector((0, 0, 1)), 0.2)
            if h[0] is not None and h[0].z < 0.02:
                hits.append(round(h[0].z, 5))
        r["clamp_underside_z_on_centreline"] = sorted(set(hits))[:6]
        # sight-line clearance: ray from the ADS eye point forward along -Y; first body hit (should be none for
        # open sights; for scopes the glass is separate so the body must also be clear)
        if ads:
            eye = ads.matrix_world.translation + Vector((0, cat[oid]["eye_relief_m"], 0))
            h = tree.ray_cast(eye, Vector((0, -1, 0)), 1.0)
            r["sightline_body_hit"] = None if h[0] is None else [round(x, 4) for x in h[0]]
            # how much of the view cone (radius 0.02 at 0.12 m) is blocked by body for 1x sights
            blocked = 0
            tot_r = 0
            for ix in range(-6, 7):
                for iz in range(-6, 7):
                    d = Vector((ix * 0.004, -0.12, iz * 0.004)).normalized()
                    tot_r += 1
                    hh = tree.ray_cast(eye, d, 1.0)
                    if hh[0] is not None:
                        blocked += 1
            r["eye_cone_blocked_frac_(+-18deg_grid)"] = round(blocked / tot_r, 3)
        # glass to body: nearest distance from glass verts to body (embedding is intended; report min/max)
        glass = [o for o in meshes if o.name.endswith("_Glass")]
        glow = [o for o in meshes if o.name.endswith("_Glow")]
        for lab, grp in (("glass", glass), ("glow", glow)):
            if not grp:
                continue
            gt, gv, gp = bvh_of(grp)
            r[lab + "_overlaps_body_pairs"] = len(tree.overlap(gt))
        if glow and glass:
            gt, gv, gp = bvh_of(glass)
            dmin = min(gt.find_nearest(v)[3] for v in bvh_of(glow)[1])
            r["glow_to_glass_min_mm"] = round(dmin * 1000, 3)
        report[oid] = r
        print(oid, json.dumps({k: r[k] for k in ("dims", "ads_loc", "tris_total")}))

    # on-gun: snap at the socket from sockets.json AND from the gun glb's own socket node; clash + rail gaps
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
            root.location = s_json
            bpy.context.view_layer.update()
            obody = [o for o in onew if o.type == "MESH" and o.name.endswith("_Body")]
            oall = [o for o in onew if o.type == "MESH"]
            gt, gv, gp = bvh_of(gmesh)
            ot, ov, op = bvh_of(oall)
            pairs = gt.overlap(ot)
            # where are the clashes (optic face centres)
            locs = []
            for gi, oi in pairs[:4000]:
                c = sum((ov[i] for i in op[oi]), Vector()) / len(op[oi])
                locs.append(c - s_json)
            ent = {"socket_json": [round(x, 4) for x in s_json],
                   "socket_glb": [round(x, 4) for x in s_glb] if s_glb else None,
                   "clash_pairs": len(pairs)}
            if locs:
                ent["clash_local_bbox"] = [[round(min(c[i] for c in locs), 4) for i in range(3)],
                                           [round(max(c[i] for c in locs), 4) for i in range(3)]]
            # rail top under the optic: ray down from 5 cm above the socket at x=0 (optic hidden: use gun BVH)
            tops = []
            for dy in (-0.03, -0.01, 0.0, 0.01, 0.03):
                h = gt.ray_cast(s_json + Vector((0, dy, 0.05)), Vector((0, 0, -1)), 0.2)
                tops.append(None if h[0] is None else round(h[0].z - s_json.z, 5))
            ent["rail_top_rel_socket_z"] = tops
            # rail half width at a few depths under the top (side rays inward)
            widths = {}
            for dz in (-0.0005, -0.002, -0.004, -0.006, -0.0085):
                hp = gt.ray_cast(s_json + Vector((0.05, 0.0, dz)), Vector((-1, 0, 0)), 0.1)
                hn = gt.ray_cast(s_json + Vector((-0.05, 0.0, dz)), Vector((1, 0, 0)), 0.1)
                widths[str(dz)] = [None if hp[0] is None else round(hp[0].x - s_json.x, 5),
                                   None if hn[0] is None else round(hn[0].x - s_json.x, 5)]
            ent["rail_flank_x_at_depth"] = widths
            gun.setdefault(g, {})[oid] = ent
            print(g, oid, ent)
    report["on_gun"] = gun
    with open(os.path.join(REV, "checks.json"), "w") as f:
        json.dump(report, f, indent=1)
    print("WROTE", os.path.join(REV, "checks.json"))


if __name__ == "__main__":
    main()
