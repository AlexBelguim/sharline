"""Import a GLB, report stats, normalise placement (optional) and render turnaround previews.

blender -b --factory-startup -P tools/inspect_glb.py -- <in.glb> <out_dir> <prefix> [height_m] [engine]
height_m: if given, uniformly scale so the model is that tall, put its feet on Z=0 and centre it on X/Y.
"""
import sys

sys.path.insert(0, r"F:/git/val etf/tools")
import bpy  # noqa: E402
import blender_common as bc  # noqa: E402
from mathutils import Vector  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
src, out_dir, prefix = argv[0], argv[1], argv[2]
height = float(argv[3]) if len(argv) > 3 and argv[3] != "-" else None
engine = argv[4] if len(argv) > 4 else "CYCLES"

bc.reset_scene()
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
mn, mx = bc.world_bounds(meshes)
print("RAW BOUNDS", tuple(round(v, 3) for v in mn), tuple(round(v, 3) for v in mx))
if height:
    roots = [o for o in bpy.context.scene.objects if o.parent is None]
    s = height / (mx.z - mn.z)
    for r in roots:
        r.scale = r.scale * s
        r.location = r.location * s
    bpy.context.view_layer.update()
    mn, mx = bc.world_bounds(meshes)
    off = Vector((-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z))
    for r in roots:
        r.location += off
    bpy.context.view_layer.update()
for o in meshes:
    print("MESH", o.name, len(o.data.vertices), "verts", len(o.data.polygons), "faces",
          "mats", [m.name for m in o.data.materials if m], "uv", len(o.data.uv_layers))
bc.stats(meshes)
bc.setup_studio()
paths = bc.render_views(out_dir, prefix, objs=meshes,
                        views=("front", "three_quarter", "right", "back", "left", "three_quarter_back"),
                        res=(700, 900), engine=engine, samples=48, lens=70)
bc.contact_sheet(paths, out_dir + f"/{prefix}_sheet.png", cols=3)
mn, mx = bc.world_bounds(meshes)
head_c = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mx.z - 0.13))
bc.render_views(out_dir, prefix + "_head", objs=meshes, views=("front", "three_quarter"), res=(700, 700),
                engine=engine, samples=48, lens=85, focus=(head_c, 0.2))
