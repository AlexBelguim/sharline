"""Fresh, read-only QA for the current optics; preserve earlier review evidence.

Run with Blender --background --factory-startup --python review/verify_cleanup.py.
Writes review/cleanup_checks.json and fails if source geometry, exports or flap
clearance disagree with the delivered catalog.
"""
import json
from pathlib import Path
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT = Path(__file__).resolve().parents[1]
if "--out" in sys.argv:
    OUT = Path(sys.argv[sys.argv.index("--out") + 1]).resolve()
REPORT = OUT / "review" / "cleanup_checks.json"
DECALS = ("_Reticle", "_Glint", "_Hologram")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validate_exports as exports


def geometry(obj):
    graph = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object(obj.evaluated_get(graph), graph)
    bm.transform(obj.matrix_world)
    return bm


def mesh_stats(obj, require_closed):
    bm = geometry(obj)
    stats = {
        "tris": sum(len(f.verts) - 2 for f in bm.faces),
        "uv_layers": len(obj.data.uv_layers),
        "degenerate_faces": sum(f.calc_area() < 1e-11 for f in bm.faces),
        "wire_edges": sum(e.is_wire for e in bm.edges),
        "loose_verts": sum(not v.link_edges for v in bm.verts),
        "non_manifold_edges": sum(not e.is_manifold for e in bm.edges),
        "invalid_material_faces": sum(f.material_index >= len(obj.data.materials) or
                                      obj.data.materials[f.material_index] is None for f in bm.faces),
        "require_closed": require_closed,
    }
    bm.faces.ensure_lookup_table()
    unseen = set(bm.faces)
    inverted = 0
    islands = 0
    while unseen:
        todo = [unseen.pop()]
        faces = []
        while todo:
            f = todo.pop()
            faces.append(f)
            for edge in f.edges:
                for other in edge.link_faces:
                    if other in unseen:
                        unseen.remove(other)
                        todo.append(other)
        islands += 1
        if all(e.is_manifold for f in faces for e in f.edges):
            volume = 0.0
            for f in faces:
                vs = [v.co for v in f.verts]
                volume += sum(vs[0].dot(vs[i].cross(vs[i + 1])) / 6 for i in range(1, len(vs) - 1))
            inverted += volume < -1e-12
    stats["islands"] = islands
    stats["inverted_closed_islands"] = inverted
    bm.free()
    failures = [k for k in ("degenerate_faces", "wire_edges", "loose_verts", "invalid_material_faces",
                            "inverted_closed_islands") if stats[k]]
    if not stats["uv_layers"]:
        failures.append("missing_uv")
    if require_closed and stats["non_manifold_edges"]:
        failures.append("non_manifold_edges")
    stats["failures"] = failures
    return stats


def tree(obj):
    bm = geometry(obj)
    value = BVHTree.FromBMesh(bm, epsilon=1e-7)
    bm.free()
    return value


def main():
    catalog = json.loads((OUT / "catalog.json").read_text())
    result = {"source": {}, "exports": {}, "raw_exports": {}, "flap_sweep": {}, "failures": []}
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "optics.blend"))
    bpy.context.scene.frame_set(0)
    for entry in catalog["optics"]:
        oid = entry["id"]
        mesh_results = {}
        for name in filter(None, entry["nodes"].values()):
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != "MESH":
                result["failures"].append(f"source: missing mesh {name}")
                continue
            stats = mesh_stats(obj, not name.endswith(DECALS))
            mesh_results[name] = stats
            result["failures"].extend(f"source {name}: {fail}" for fail in stats["failures"])
        count = sum(stats["tris"] for stats in mesh_results.values())
        result["source"][oid] = {"tris": count, "catalog_tris": entry["tris"], "meshes": mesh_results}
        if count != entry["tris"]:
            result["failures"].append(f"source {oid}: {count} triangles differs from catalog {entry['tris']}")
    projector = next(e for e in catalog["optics"] if e["id"] == "optic_projector")
    names = projector["nodes"]
    duration = projector["projector"]["animation"]["duration_s"]
    fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    end = round(duration * fps)
    for frame in range(end + 1):
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()
        body, left, right = (tree(bpy.data.objects[names[r]]) for r in ("body", "flap_l", "flap_r"))
        overlap = {"left_body": len(left.overlap(body)), "right_body": len(right.overlap(body)),
                   "left_right": len(left.overlap(right))}
        result["flap_sweep"][str(frame)] = overlap
        if any(overlap.values()):
            result["failures"].append(f"projector frame {frame}: flap intersection {overlap}")
    for entry in catalog["optics"]:
        j, _ = exports.load_glb(OUT / entry["file"])
        stats = exports.triangle_geometry(OUT / entry["file"], j)
        result["raw_exports"][entry["id"]] = stats
        if stats["degenerate_triangles"]:
            result["failures"].append(f"raw export {entry['id']}: degenerate triangles")
        if stats["opposing_normal_triangles"]:
            result["failures"].append(f"raw export {entry['id']}: opposing corner normals")
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(OUT / entry["file"]))
        mesh_results = {}
        for name in filter(None, entry["nodes"].values()):
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != "MESH":
                result["failures"].append(f"export: missing mesh {name}")
                continue
            # glTF duplicates vertices at material/UV/normal seams, so closure is
            # checked on the original Blender mesh instead of the split export.
            stats = mesh_stats(obj, False)
            mesh_results[name] = stats
            result["failures"].extend(f"export {name}: {fail}" for fail in stats["failures"])
        count = sum(stats["tris"] for stats in mesh_results.values())
        result["exports"][entry["id"]] = {"tris": count, "meshes": mesh_results}
        if count != entry["tris"]:
            result["failures"].append(f"export {entry['id']}: triangle count differs from catalog")
    result["ok"] = not result["failures"]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, indent=2) + "\n")
    print("CLEANUP QA:", "ALL OK" if result["ok"] else "FAIL")
    print("Report:", REPORT)
    for failure in result["failures"]:
        print("ERROR:", failure)
    if not result["ok"]:
        raise RuntimeError("Optics cleanup QA failed")


main()
