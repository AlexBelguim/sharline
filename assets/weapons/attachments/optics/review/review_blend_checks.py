"""Reviewer: checks on the source optics.blend (manifoldness before the glTF split) + fine rail sampling on the
real gun exports. Read-only on the asset; writes review/blend_checks.json.

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P review_blend_checks.py
"""
import json
import os
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_checks as rc  # noqa: E402  (re-uses islands / signed_volume; main() guarded below)

OUT = rc.OUT
REV = rc.REV


def main():
    res = {}
    bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, "optics.blend"))
    res["collections"] = {c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections}
    res["scene_objects"] = len(bpy.context.scene.objects)
    res["materials"] = sorted(m.name for m in bpy.data.materials)
    res["images"] = sorted((i.name, i.filepath, i.packed_file is not None) for i in bpy.data.images)
    meshes = {}
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or not o.name.startswith("ATT_"):
            continue
        bm = rc.world_bm(o)
        isl = rc.islands(bm)
        open_isl = []
        inv = []
        for fs in isl:
            closed = all(e.is_manifold for f in fs for e in f.edges)
            c = sum((f.calc_center_median() for f in fs), Vector()) / len(fs)
            if not closed:
                nb = sum(1 for f in fs for e in f.edges if e.is_boundary) // 1
                open_isl.append({"centre": [round(x, 4) for x in c], "faces": len(fs), "boundary_edge_refs": nb})
            elif rc.signed_volume(fs) < -1e-12:
                inv.append([round(x, 4) for x in c])
        meshes[o.name] = {"tris": sum(len(f.verts) - 2 for f in bm.faces), "islands": len(isl),
                          "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold),
                          "open_islands": open_isl[:20], "open_island_count": len(open_isl),
                          "inverted_islands": inv,
                          "ngons_gt4": sum(1 for f in bm.faces if len(f.verts) > 4),
                          "max_ngon": max((len(f.verts) for f in bm.faces), default=0),
                          "degenerate": sum(1 for f in bm.faces if f.calc_area() < 1e-11),
                          "modifiers": [m.type for m in o.modifiers],
                          "has_custom_normals": o.data.has_custom_normals,
                          "parent": o.parent.name if o.parent else None,
                          "collection": [c.name for c in o.users_collection]}
        bm.free()
    res["meshes"] = meshes

    # fine rail sampling on the real gun exports under the optic socket
    rails = {}
    for g, (glb, sj, sock) in rc.GUNS.items():
        rc.wipe()
        new = rc.import_glb(glb)
        gm = [o for o in new if o.type == "MESH"]
        tree, _, _ = rc.bvh_of(gm)
        s = Vector(json.load(open(sj))[sock]["location"])
        prof = []
        for i in range(-60, 61):
            dy = i * 0.0005
            h = tree.ray_cast(s + Vector((0, dy, 0.05)), Vector((0, 0, -1)), 0.2)
            prof.append((round(dy, 4), None if h[0] is None else round(h[0].z - s.z, 5)))
        zs = [p[1] for p in prof if p[1] is not None]
        rails[g] = {"socket": list(s), "rail_top_max_rel": max(zs), "rail_slot_bottom_rel": min(zs),
                    "profile_dy_z": prof[::4]}
        # where along Y is the rail present (full-length top rail?) at the socket x=0
        tops = []
        for i in range(-80, 81):
            y = s.y + i * 0.005
            h = tree.ray_cast(Vector((0, y, s.z + 0.1)), Vector((0, 0, -1)), 0.3)
            tops.append((round(y, 3), None if h[0] is None else round(h[0].z, 4)))
        rails[g]["top_along_y"] = tops[::4]
    res["rails"] = rails
    with open(os.path.join(REV, "blend_checks.json"), "w") as f:
        json.dump(res, f, indent=1)
    print("WROTE blend_checks.json")


main()
