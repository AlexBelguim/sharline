"""Re-import every Warden .fbx (default importer settings) and report bounds, sockets, materials, textures."""
import bpy, os, glob
from mathutils import Vector
D = r"F:/git/val etf/assets/weapons/vk50_warden"
for p in sorted(glob.glob(D + "/*.fbx")):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=p)
    ms = [o for o in bpy.data.objects if o.type == "MESH"]
    mn = Vector((1e9,)*3); mx = -mn
    for o in ms:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c); mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
    socks = {o.name: tuple(round(c, 4) for c in o.matrix_world.translation) for o in bpy.data.objects if "SOCKET" in o.name}
    roots = [(o.name, o.type, tuple(round(c,3) for c in o.matrix_world.to_scale()), tuple(round(c,3) for c in o.matrix_world.to_euler())) for o in bpy.data.objects if o.parent is None]
    imgs = [(i.name, i.packed_file is not None or os.path.exists(bpy.path.abspath(i.filepath))) for i in bpy.data.images]
    print(os.path.basename(p), "meshes", len(ms), "bounds", tuple(round(c,4) for c in mn), tuple(round(c,4) for c in mx))
    print("   roots", roots)
    print("   sockets", socks)
    print("   mats", sorted({m.name for o in ms for m in o.data.materials if m}), "images", imgs)
