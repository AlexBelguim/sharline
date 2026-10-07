"""Topology checks on the SOURCE meshes in halo_kit.blend (glTF import splits verts at seams, so manifold
checks must run on the authored data).  Read-only: the .blend is opened, never saved.
Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b "F:/git/val etf/assets/shields/halo_kit.blend" \
      --factory-startup -P "F:/git/val etf/assets/shields/review/review_topology.py"
"""
import json
import math
import os

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

OUT = r"F:/git/val etf/assets/shields/review"


def islands(bm):
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
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


def signed_volume(faces):
    v = 0.0
    for f in faces:
        vs = [l.vert.co for l in f.loops]
        for i in range(1, len(vs) - 1):
            v += vs[0].dot(vs[i].cross(vs[i + 1])) / 6.0
    return v


rep = {}
for o in sorted(bpy.data.objects, key=lambda o: o.name):
    if o.type != "MESH" or not o.name.startswith("HALO_") or o.name.startswith("HALO_Swatch"):
        continue
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    isl = islands(bm)
    closed = inv = 0
    open_isl = 0
    nonman_e = sum(1 for e in bm.edges if not e.is_manifold)
    bound_e = sum(1 for e in bm.edges if e.is_boundary)
    over2 = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    for comp in isl:
        edges = {e for f in comp for e in f.edges}
        if all(len(e.link_faces) == 2 for e in edges):
            closed += 1
            if signed_volume(comp) < 0:
                inv += 1
        else:
            open_isl += 1
    # degenerate / sliver faces
    tiny = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    # self-overlap between islands (interpenetrating pieces are by design; count island pairs that intersect)
    rep[o.name] = dict(islands=len(isl), closed=closed, open=open_isl, inverted=inv, nonmanifold_edges=nonman_e,
                       boundary_edges=bound_e, edges_more_than_2_faces=over2, tiny_faces=tiny, ngons=ngons,
                       faces=len(bm.faces), uv=len(o.data.uv_layers),
                       mats=[m.name for m in o.data.materials])
    bm.free()

json.dump(rep, open(os.path.join(OUT, "topology_report.json"), "w"), indent=1)
for k, r in rep.items():
    print(f"{k:<26} isl={r['islands']:<4} closed={r['closed']:<4} open={r['open']:<3} inv={r['inverted']:<3} "
          f"nonman={r['nonmanifold_edges']:<4} bound={r['boundary_edges']:<4} >2f={r['edges_more_than_2_faces']:<3} "
          f"tiny={r['tiny_faces']} ngons={r['ngons']}")
