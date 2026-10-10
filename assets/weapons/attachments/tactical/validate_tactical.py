"""Validate delivered tactical meshes independently of the builder.

Run with Blender 5.2:
  blender -b --factory-startup --python-exit-code 1 -P validate_tactical.py -- [--source DIR] [--out FILE]
Writes _work/validation/exports.json by default. Historical review reports are preserved.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
# Two enclosed housing/receiver chamfer contacts at the UGL breech plane. Welding the separate closed shells
# joins these edges artificially. Their positions are recorded narrowly; other nonmanifold edges still fail.
UGL_CONTACT_EDGES = [((-0.0299, 0, -0.013663), (-0.025337, 0, -0.0091)),
                     ((0.025337, 0, -0.0091), (0.0299, 0, -0.013663))]


def known_contact(obj, edge):
    if obj.name != "ATT_ugl_launcher":
        return False
    ends = sorted(tuple(v.co) for v in edge.verts)
    return any(all(abs(a - b) <= 2e-6 for actual, expected in zip(ends, pair)
                   for a, b in zip(actual, expected)) for pair in UGL_CONTACT_EDGES)


def mesh_report(obj):
    mesh = obj.data
    mesh.calc_loop_triangles()
    normals = [Vector(n.vector) for n in mesh.corner_normals]
    zero = flipped = 0
    for tri in mesh.loop_triangles:
        if tri.area < 1e-10:
            zero += 1
            continue
        average = sum((normals[i] for i in tri.loops), Vector())
        if average.length > 1e-9 and average.dot(tri.normal) / average.length < -0.5:
            flipped += 1
    bm = bmesh.new()
    bm.from_mesh(mesh)
    # glTF splits vertices at UV, material and hard-normal seams. Weld a temporary copy to inspect geometric
    # topology; the authored seam vertices and their exported normals remain untouched.
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-6)
    nonmanifold = [e for e in bm.edges if len(e.link_faces) > 2]
    topology = {"open_edges": sum(len(e.link_faces) == 1 for e in bm.edges),
                "nonmanifold_edges": len(nonmanifold),
                "enclosed_contact_edges": sum(known_contact(obj, e) for e in nonmanifold),
                "unexpected_nonmanifold_edges": sum(not known_contact(obj, e) for e in nonmanifold),
                "loose_vertices": sum(not v.link_faces for v in bm.verts),
                "nonmanifold_edge_locations": [[[round(c, 6) for c in v.co] for v in e.verts]
                                               for e in bm.edges if len(e.link_faces) > 2]}
    bm.free()
    return {"triangles": len(mesh.loop_triangles), **topology,
            "zero_area_triangles": zero, "flipped_triangles": flipped,
            "missing_material_faces": sum(p.material_index >= len(mesh.materials)
                                          or mesh.materials[p.material_index] is None for p in mesh.polygons),
            "has_uvs": bool(mesh.uv_layers),
            "finite_vertices": all(math.isfinite(c) for v in mesh.vertices for c in v.co)}


def bounds(objects):
    vertices = [o.matrix_world @ v.co for o in objects if o.type == "MESH" for v in o.data.vertices]
    return [[round(fn(v[i] for v in vertices), 5) for i in range(3)] for fn in (min, max)]


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=HERE)
    parser.add_argument("--out", type=Path, default=HERE / "_work" / "validation" / "exports.json")
    args = parser.parse_args(argv)
    source = args.source.resolve()
    catalog = json.loads((source / "catalog.json").read_text())
    report = {"source": str(source), "catalog_sha256": hashlib.sha256((source / "catalog.json").read_bytes()).hexdigest(),
              "files": {}, "errors": []}
    for part in catalog["parts"]:
        expected_hierarchy = None
        for extension in ("glb", "fbx"):
            bpy.ops.wm.read_factory_settings(use_empty=True)
            path = source / (part["id"] + "." + extension)
            if extension == "glb":
                bpy.ops.import_scene.gltf(filepath=str(path))
            else:
                bpy.ops.import_scene.fbx(filepath=str(path))
            objects = list(bpy.data.objects)
            meshes = {o.name: mesh_report(o) for o in objects if o.type == "MESH"}
            triangles = sum(m["triangles"] for m in meshes.values())
            result = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "triangles": triangles, "bounds": bounds(objects), "meshes": meshes,
                      "hierarchy": {o.name: o.parent.name if o.parent else None for o in objects}}
            if extension == "glb":
                expected_hierarchy = result["hierarchy"]
            elif result["hierarchy"] != expected_hierarchy:
                report["errors"].append(f"{path.name}: FBX hierarchy differs from GLB")
            report["files"][path.name] = result
            if triangles != part["tris"]:
                report["errors"].append(f"{path.name}: catalog says {part['tris']} triangles, export has {triangles}")
            for name, mesh in meshes.items():
                defects = [key for key in ("open_edges", "unexpected_nonmanifold_edges", "loose_vertices",
                                          "zero_area_triangles", "flipped_triangles", "missing_material_faces")
                           if mesh[key]]
                if defects or not mesh["has_uvs"] or not mesh["finite_vertices"]:
                    report["errors"].append(f"{path.name}/{name}: {defects}, UVs={mesh['has_uvs']}, finite={mesh['finite_vertices']}")
            if extension == "glb":
                names = {o.name for o in objects}
                if names != set(part["objects"]):
                    report["errors"].append(f"{path.name}: node names differ from catalog")
                for i, key in enumerate(("bounds_min", "bounds_max")):
                    if any(abs(a - b) > 0.00011 for a, b in zip(result["bounds"][i], part[key])):
                        report["errors"].append(f"{path.name}: {key} differs from catalog")
                if part["id"] == "ATT_bipod":
                    for obj in objects:
                        obj.rotation_mode = "XYZ"
                        if "_Leg_" in obj.name:
                            obj.rotation_euler = (math.radians(obj["hinge_euler_x_folded_deg"]), 0, 0)
                        elif "_LegSplay_" in obj.name:
                            obj.rotation_euler = (0, math.radians(obj["splay_euler_y_folded_deg"]), 0)
                        elif "_Foot_" in obj.name:
                            obj.rotation_euler = (math.radians(obj["swivel_folded_deg"]), 0, 0)
                    bpy.context.view_layer.update()
                    result["folded_bounds"] = bounds(objects)
                    if result["folded_bounds"][1][0] - result["folded_bounds"][0][0] > 0.11:
                        report["errors"].append("ATT_bipod: folded width exceeds 110 mm")
            if part["id"] == "ATT_ugl_launcher":
                muzzle = next(o for o in objects if o.name.endswith("_SOCKET_Muzzle"))
                if muzzle.parent is None or muzzle.parent.name != "ATT_ugl_launcher_Breech":
                    report["errors"].append(f"{path.name}: muzzle must follow the breech")
            print("VALIDATE", path.name, triangles)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    if report["errors"]:
        raise RuntimeError("Tactical export validation failed: " + "; ".join(report["errors"]))
    print("TACTICAL VALIDATION PASSED", args.out)


main()
