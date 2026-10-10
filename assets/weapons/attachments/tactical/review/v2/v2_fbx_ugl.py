import bpy, os, math
HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=os.path.join(HERE, "ATT_ugl_launcher.fbx"))
bpy.context.view_layer.update()
for o in bpy.data.objects:
    t = sum(len(p.vertices) - 2 for p in o.data.polygons) if o.type == "MESH" else 0
    ws = [o.matrix_world @ v.co for v in o.data.vertices] if o.type == "MESH" else []
    b = ([round(min(w[i] for w in ws), 4) for i in range(3)], [round(max(w[i] for w in ws), 4) for i in range(3)]) if ws else None
    print("FBX", o.name, o.type, "parent", o.parent.name if o.parent else None, "tris", t, "scale", [round(s, 3) for s in o.matrix_world.to_scale()],
          "loc", [round(v, 4) for v in o.matrix_world.translation], "bounds", b, "props", [k for k in o.keys() if not k.startswith('_')][:6],
          "uv", [u.name for u in o.data.uv_layers] if o.type == "MESH" else None)
