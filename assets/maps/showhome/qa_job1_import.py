"""Job 1 compatibility / frame QA: initialize props PBR, then import the actual exported house and props GLBs.

Run in Blender 5.2 headless. This catches a shared glTF settings-node contract regression before look-dev.
"""
from pathlib import Path
import json
import sys

import bpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import props_lib as PL

bpy.ops.wm.read_factory_settings(use_empty=True)
PL.spec("_QA_ORM", tex=str(HERE / "textures/v2/concrete_smooth.png"),
        normal=str(HERE / "textures/v2/concrete_smooth_normal.png"),
        orm=str(HERE / "textures/v2/concrete_smooth_orm.png"))
PL.M("_QA_ORM")
group = bpy.data.node_groups["glTF Material Output"]
inputs = [i.name for i in group.interface.items_tree if i.item_type == "SOCKET" and i.in_out == "INPUT"]
assert all(k in inputs for k in ("Occlusion", "Thickness", "Dispersion", "Iridescence Factor",
                               "Iridescence Thickness Minimum")), inputs

report = {"glTF_settings_inputs": inputs, "assets": []}
for name in ("houses.glb", "props_placed.glb"):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(HERE / "kit" / name))
    meshes = [o for o in set(bpy.data.objects) - before if o.type == "MESH"]
    points = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    assert all(o.data.uv_layers for o in meshes), name
    assert all(len(o.data.materials) == 1 for o in meshes), name
    bounds = [[round(fn(p[k] for p in points), 5) for k in range(3)] for fn in (min, max)]
    triangles = sum(len(p.vertices) - 2 for o in meshes for p in o.data.polygons)
    mats = {m for o in meshes for m in o.data.materials}
    textured = sum(any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes) for m in mats)
    shader_noise = [m.name for m in mats if any(n.type in ("TEX_NOISE", "TEX_VORONOI", "TEX_WAVE")
                                              for n in m.node_tree.nodes)]
    assert not shader_noise, shader_noise
    report["assets"].append({"file": name, "meshes": len(meshes), "triangles": triangles,
                             "blender_design_bounds": bounds, "materials": len(mats),
                             "textured_materials": textured, "uv_and_single_material": True,
                             "no_shader_only_procedural_colour": True})

out = HERE / "kit/job1_import_validation.json"
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print("JOB1 IMPORT QA PASS", json.dumps(report))
