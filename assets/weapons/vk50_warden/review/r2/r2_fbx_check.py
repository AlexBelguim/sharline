"""Round-2: every FBX loads; names, hierarchy, world scale/bounds, materials, custom props (read-only)."""
import bpy, os, glob
from mathutils import Vector
D = r"F:/git/val etf/assets/weapons/vk50_warden"
for p in sorted(glob.glob(D + "/*.fbx")):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.import_scene.fbx(filepath=p)
    except Exception as e:
        print("FBX FAIL", os.path.basename(p), e); continue
    obs = list(bpy.data.objects)
    ms = [o for o in obs if o.type == "MESH"]
    mn = Vector((1e9,)*3); mx = -mn
    for o in ms:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c); mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
    roots = [o for o in obs if o.parent is None]
    props = {o.name: [k for k in o.keys() if not k.startswith("_")] for o in obs if [k for k in o.keys() if not k.startswith("_")]}
    nomat = [o.name for o in ms if not o.data.materials or any(m is None for m in o.data.materials)]
    tex = sorted({n.image.name for m in bpy.data.materials if m.use_nodes for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image})
    print("FBX", os.path.basename(p), "objs", len(obs), "meshes", len(ms), "roots", [(r.name, [round(x,3) for x in r.scale]) for r in roots],
          "bounds", [round(x,4) for x in mn], [round(x,4) for x in mx], "nomat", nomat, "mats", sorted(m.name for m in bpy.data.materials),
          "textures", tex)
    print("   props", {k: v for k, v in list(props.items())[:6]})
