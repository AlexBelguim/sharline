"""Render representative views of the current/staged optics without rebuilding exports.

Blender --background --factory-startup --python review/render_cleanup.py
Optional: -- --out <asset-directory>. Writes review/cleanup_visuals/.
"""
import json
from pathlib import Path
import sys

import bpy

SOURCE = Path(__file__).resolve().parents[1]
PROJECT = SOURCE.parents[3]
OUT = Path(sys.argv[sys.argv.index("--out") + 1]).resolve() if "--out" in sys.argv else SOURCE
sys.path.insert(0, str(PROJECT / "tools"))
import blender_common as bc


def main():
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "optics.blend"))
    catalog = json.loads((OUT / "catalog.json").read_text())
    scene = bpy.context.scene
    bc.setup_studio(scene)
    # Cycles renders both sides regardless of the glTF culling flag; match the
    # intended one-sided reticle/glint shader for these forward views.
    for mat in bpy.data.materials:
        if mat.name.startswith(("M_ATT_Reticle", "M_ATT_IceGlint")):
            nt = mat.node_tree
            output = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
            shader = output.inputs["Surface"].links[0].from_socket
            back = nt.nodes.new("ShaderNodeNewGeometry")
            clear = nt.nodes.new("ShaderNodeBsdfTransparent")
            mix = nt.nodes.new("ShaderNodeMixShader")
            nt.links.new(back.outputs["Backfacing"], mix.inputs[0])
            nt.links.new(shader, mix.inputs[1])
            nt.links.new(clear.outputs[0], mix.inputs[2])
            nt.links.new(mix.outputs[0], output.inputs["Surface"])
    folder = OUT / "review" / "cleanup_visuals"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for entry in catalog["optics"]:
        scene.frame_set(12)
        meshes = [bpy.data.objects[name] for name in filter(None, entry["nodes"].values())]
        selected = set(meshes)
        for obj in scene.objects:
            if obj.type == "MESH":
                obj.hide_render = obj not in selected
        paths += bc.render_views(str(folder), "ATT_" + entry["id"], objs=meshes, views=("three_quarter",),
                                 res=(600, 600), engine="CYCLES", samples=24, lens=85)
        if entry["id"] == "optic_projector":
            scene.frame_set(0)
            meshes = [m for m in meshes if not m.name.endswith("_Hologram")]
            bpy.data.objects[entry["nodes"]["hologram"]].hide_render = True
            paths += bc.render_views(str(folder), "ATT_optic_projector_folded", objs=meshes,
                                     views=("three_quarter",), res=(600, 600), engine="CYCLES", samples=24, lens=85)
    (folder / "index.json").write_text(json.dumps(paths, indent=2) + "\n")
    print("CLEANUP VISUALS:", folder)


main()
