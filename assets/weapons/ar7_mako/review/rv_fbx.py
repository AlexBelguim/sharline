import bpy, os, json
from mathutils import Vector
HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
res = {}
for f in ("mako_base.fbx", "MAKO_stock_standard.fbx", "MAKO_mag_30.fbx", "MAKO_mag_drum60.fbx"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=os.path.join(HERE, f))
    bpy.context.view_layer.update()
    mn = Vector((1e9,)*3); mx = Vector((-1e9,)*3)
    for o in bpy.data.objects:
        if o.type == "MESH":
            for c in o.bound_box:
                w = o.matrix_world @ Vector(c)
                mn = Vector([min(mn[i], w[i]) for i in range(3)]); mx = Vector([max(mx[i], w[i]) for i in range(3)])
    socks = {o.name: [round(v, 4) for v in o.matrix_world.translation] for o in bpy.data.objects if "SOCKET" in o.name}
    rots = {o.name: [round(v, 3) for v in o.matrix_world.to_euler()] for o in bpy.data.objects if "SOCKET" in o.name}
    res[f] = {"bounds": [[round(v, 4) for v in mn], [round(v, 4) for v in mx]], "n_obj": len(bpy.data.objects),
              "sockets": socks, "socket_rot_nonzero": {k: v for k, v in rots.items() if any(abs(x) > 1e-3 for x in v)},
              "textures_packed_or_found": [(i.name, i.has_data or bool(i.packed_file)) for i in bpy.data.images],
              "root_scale": [round(v, 4) for v in bpy.data.objects[0].matrix_world.to_scale()]}
print("FBXRES", json.dumps(res, indent=0))
