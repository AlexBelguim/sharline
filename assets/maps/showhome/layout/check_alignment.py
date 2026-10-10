"""Art-vs-collision alignment check for Showhome (run in headless Blender).

The art must sit on the game's collision brushes within 2 cm: what players see is what they collide with.
This script casts the SAME rays into two worlds and compares the first hit:
  * collision world: the visible brushes from showhome_annotated.json (exact, built here),
  * art world:       every mesh of the art scene (a .glb you pass, or the open .blend).
Ray origins are a 3D grid in open space (outside every brush) inside the playable rect, at heights
0.3 / 1.0 / 1.6 / 2.5 / 3.5 / 4.8 / 5.6 m, each casting 6 rays (+-x, +-y, down, up) up to 3 m.

Mismatch classes (|d_art - d_col| > tol):
  GHOST     art is hit first: visual geometry where collision is open (blocks a view the game does not).
  INVISIBLE collision is hit first: a collision face with no art on it (invisible wall / missing art).
Hits within `edge` (default 6 cm) of a brush edge use the looser `edge_tol` (default 12 cm) for bevels.
Stair ramps (part "stair_ramp") accept art up to STAIR_TOL (0.30 m) INSIDE the ramp (treads below the slope).
Art outside the playable rect (x 0..72, y 0..48) is ignored (free set dressing).

Usage
  blender -b --factory-startup -P check_alignment.py -- --art <file.glb> [--tol 0.02] [--out report.json]
  blender -b <art.blend> -P check_alignment.py -- [--collection NAME] [--exclude-prefix _]
  blender -b --factory-startup -P check_alignment.py -- --selftest
      (imports showhome_collision_preview.glb as the "art": must give 0 mismatches; then moves the Mover
       box 10 cm, deletes a wall piece and adds a ghost tree and checks that all three are reported)
Writes renders/alignment_report.json (or --out) with every mismatch; summarise / plot with
  python plot_alignment.py [report.json]
"""
import json
import math
import os
import sys
import time

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = r"F:/git/val etf/assets/maps/showhome/layout"
sys.path.insert(0, HERE)
import layout_lib as LL  # noqa: E402

MAP = (0.0, 0.0, 72.0, 48.0)
HEIGHTS = (0.3, 1.0, 1.6, 2.5, 3.5, 4.8, 5.6)
# Art may sit up to one step (0.178 m rise, 0.278 m going) inside the stair ramp's sloped face.
STAIR_TOL = 0.30
DIRS = [Vector(d) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, -1), (0, 0, 1))]


def parse():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = dict(art=None, tol=0.02, edge=0.06, edge_tol=0.12, step=1.0, ray=3.0, out=None, collection=None,
             exclude_prefix=("_", "COLPREVIEW_IGNORE"), selftest=False)
    it = iter(range(len(a)))
    i = 0
    while i < len(a):
        k = a[i]
        if k == "--art":
            o["art"] = a[i + 1]; i += 1
        elif k in ("--tol", "--edge", "--edge-tol", "--step", "--ray"):
            o[k[2:].replace("-", "_")] = float(a[i + 1]); i += 1
        elif k == "--out":
            o["out"] = a[i + 1]; i += 1
        elif k == "--collection":
            o["collection"] = a[i + 1]; i += 1
        elif k == "--exclude-prefix":
            o["exclude_prefix"] = tuple(a[i + 1].split(",")); i += 1
        elif k == "--selftest":
            o["selftest"] = True
        i += 1
    del it
    return o


# ------------------------------------------------------------------------------------------ worlds
def collision_bvh(L):
    verts, polys, owner = [], [], []
    for b in L.visible():
        v, f = LL.brush_polys(b)
        base = len(verts)
        verts += v
        for face in f:
            polys.append([base + i for i in face])
            owner.append(b)
    return BVHTree.FromPolygons(verts, polys, epsilon=0.0), verts, polys, owner


def art_objects(o):
    objs = []
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH" or ob.name.startswith(o["exclude_prefix"]) or ob.hide_render:
            continue
        if o["collection"] and not any(c.name == o["collection"] for c in ob.users_collection):
            continue
        objs.append(ob)
    return objs


def art_bvh(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    for ob in objs:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        tmp = bmesh.new()
        tmp.from_mesh(me)
        tmp.transform(ob.matrix_world)
        m2 = bpy.data.meshes.new("_tmp_bvh")
        tmp.to_mesh(m2)
        tmp.free()
        bm.from_mesh(m2)
        bpy.data.meshes.remove(m2)
        ev.to_mesh_clear()
    bvh = BVHTree.FromBMesh(bm, epsilon=0.0)
    bm.free()
    return bvh


# ------------------------------------------------------------------------------------------ helpers
def in_map(p, pad=0.0):
    return MAP[0] - pad <= p.x <= MAP[2] + pad and MAP[1] - pad <= p.y <= MAP[3] + pad


def edge_distance(p, poly_pts):
    """Distance from p (on the polygon's plane) to the polygon's nearest edge."""
    best = 1e9
    n = len(poly_pts)
    for i in range(n):
        a, b = poly_pts[i], poly_pts[(i + 1) % n]
        ab = b - a
        t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
        best = min(best, (a + ab * t - p).length)
    return best


def run(o, L, objs):
    t0 = time.time()
    cbvh, cverts, cpolys, owner = collision_bvh(L)
    cverts = [Vector(v) for v in cverts]
    abvh = art_bvh(objs)
    vis = L.visible()
    mism = []
    n_rays = 0
    nx, ny = int((MAP[2] - MAP[0]) / o["step"]), int((MAP[3] - MAP[1]) / o["step"])
    for z in HEIGHTS:
        for i in range(nx + 1):
            for j in range(ny + 1):
                p = Vector((MAP[0] + 0.25 + i * o["step"], MAP[1] + 0.25 + j * o["step"], z))
                if not in_map(p):
                    continue
                pt = (p.x, p.y, p.z)
                if any(LL.inside(b, pt, eps=-0.005) for b in vis if b["min"][2] < z < b["max"][2] + 0.01
                       and b["min"][0] - 0.01 < p.x < b["max"][0] + 0.01 and b["min"][1] - 0.01 < p.y < b["max"][1] + 0.01):
                    continue  # origin inside (or within 5 mm of) collision
                for d in DIRS:
                    n_rays += 1
                    hc = cbvh.ray_cast(p, d, o["ray"])
                    ha = abvh.ray_cast(p, d, o["ray"])
                    dc = hc[3] if hc[0] is not None else None
                    da = ha[3] if ha[0] is not None and in_map(ha[0], 0.0) else None
                    if dc is None and da is None:
                        continue
                    tol = o["tol"]
                    near_edge = False
                    if dc is not None:
                        poly = [cverts[k] for k in cpolys[hc[2]]]
                        if edge_distance(hc[0], poly) < o["edge"]:
                            near_edge = True
                    elif da is not None:
                        q = (ha[0].x, ha[0].y, ha[0].z)
                        if min(LL.box_distance(b, q) for b in vis) < o["edge"]:
                            near_edge = True
                    if near_edge:
                        tol = o["edge_tol"]
                    if dc is not None and da is not None and abs(dc - da) <= tol:
                        continue
                    if da is not None and (dc is None or da < dc):
                        kind = "GHOST"
                        hit = ha[0]
                        q = (hit.x, hit.y, hit.z)
                        nb = min(vis, key=lambda b: LL.box_distance(b, q))
                        ref = nb
                    else:
                        kind = "INVISIBLE"
                        hit = hc[0]
                        ref = owner[hc[2]]
                        # stairs: the collision is a smooth ramp; treads/risers may sit inside it by one step
                        if ref["tag"].get("part") == "stair_ramp" and (da is None or da - dc <= STAIR_TOL):
                            if da is not None:
                                continue
                    mism.append(dict(kind=kind, origin=[round(p.x, 3), round(p.y, 3), round(p.z, 3)],
                                     dir=[int(d.x), int(d.y), int(d.z)], hit=[round(hit.x, 3), round(hit.y, 3),
                                                                             round(hit.z, 3)],
                                     d_col=None if dc is None else round(dc, 4),
                                     d_art=None if da is None else round(da, 4),
                                     near_edge=near_edge, brush=ref["i"], tag=ref["tag"]["id"],
                                     part=ref["tag"].get("part"), structure=ref["tag"]["structure"]))
    # summary per structure / tag
    by = {}
    for m in mism:
        k = (m["structure"], m["tag"], m["kind"])
        by[k] = by.get(k, 0) + 1
    summary = sorted(([s, t, k, n] for (s, t, k), n in by.items()), key=lambda r: -r[3])
    rep = dict(tol=o["tol"], edge=o["edge"], edge_tol=o["edge_tol"], rays=n_rays, mismatches=len(mism),
               ghost=sum(m["kind"] == "GHOST" for m in mism), invisible=sum(m["kind"] == "INVISIBLE" for m in mism),
               seconds=round(time.time() - t0, 1), art_objects=len(objs), by_tag=summary, items=mism)
    return rep


def selftest_perturb():
    """Move the Mover box 10 cm east, delete one wall piece, add a ghost tree on the Sage lawn."""
    changed = []
    for ob in bpy.context.scene.objects:
        if "C_MOVER_BOX" in ob.name:
            ob.location.x += 0.10
            changed.append("moved " + ob.name)
    for ob in list(bpy.context.scene.objects):
        if "W_GF_E_pier" in ob.name:
            changed.append("deleted " + ob.name)
            bpy.data.objects.remove(ob, do_unlink=True)
            break
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.2, location=(24.5, 24.0, 2.6))
    bpy.context.active_object.name = "GHOST_TREE"
    changed.append("added GHOST_TREE at (24.5, 24, 2.6)")
    return changed


def main():
    o = parse()
    L = LL.load()
    if o["selftest"]:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.join(HERE, "showhome_collision_preview.glb"))
        rep = run(o, L, art_objects(o))
        print(f"SELFTEST clean: rays {rep['rays']}, mismatches {rep['mismatches']} ({rep['seconds']} s)")
        ok_clean = rep["mismatches"] == 0
        changes = selftest_perturb()
        rep2 = run(o, L, art_objects(o))
        tags = {r[1] for r in rep2["by_tag"]}
        print("SELFTEST perturbed:", changes)
        for r in rep2["by_tag"][:12]:
            print("   ", r)
        ok_dirty = "C_MOVER_BOX" in tags and "W_GF_E" in tags and any(m["kind"] == "GHOST" and
                                                                       abs(m["hit"][0] - 24.5) < 1.5 for m in rep2["items"])
        print("SELFTEST", "PASS" if ok_clean and ok_dirty else "FAIL", f"(clean={ok_clean}, detects={ok_dirty})")
        out = o["out"] or os.path.join(HERE, "renders", "alignment_selftest.json")
        json.dump(rep2, open(out, "w"), indent=1)
        return
    if o["art"]:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        ext = os.path.splitext(o["art"])[1].lower()
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=o["art"])
        elif ext == ".blend":
            bpy.ops.wm.open_mainfile(filepath=o["art"])
        else:
            raise SystemExit("--art must be .glb/.gltf/.blend")
    objs = art_objects(o)
    if not objs:
        raise SystemExit("no art meshes found")
    rep = run(o, L, objs)
    out = o["out"] or os.path.join(HERE, "renders", "alignment_report.json")
    json.dump(rep, open(out, "w"), indent=1)
    print(f"alignment: {rep['art_objects']} art objects, {rep['rays']} rays, {rep['mismatches']} mismatches "
          f"(GHOST {rep['ghost']}, INVISIBLE {rep['invisible']}) in {rep['seconds']} s -> {out}")
    for r in rep["by_tag"][:40]:
        print("   ", r)


main()
