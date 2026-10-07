"""Bolt-open clearance with the folding stock UNFOLDED, and the minimum bolt travel at which the bolt first hits
each stock (standard + folding). Read-only."""
import math, os, bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
D = r"F:/git/val etf/assets/weapons/vk50_warden"
def imp(p, at=None):
    b = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=p)
    n = [o for o in bpy.data.objects if o not in b]
    if at is not None:
        for r in [o for o in n if o.parent is None]:
            r.matrix_world = Matrix.Translation(at) @ r.matrix_world
    bpy.context.view_layer.update(); return n
def bvh(o):
    dg = bpy.context.evaluated_depsgraph_get(); oe = o.evaluated_get(dg); me = oe.to_mesh()
    t = BVHTree.FromPolygons([o.matrix_world @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    oe.to_mesh_clear(); return t
for stock in ("WARDEN_stock_standard.glb", "WARDEN_stock_folding.glb"):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    b = {o.name: o for o in imp(os.path.join(D, "warden_base.glb"))}
    st = imp(os.path.join(D, stock), b["WARDEN_SOCKET_Stock"].matrix_world.translation.copy())
    bolt = b["WARDEN_Bolt"]; bolt.rotation_mode = "XYZ"
    l0 = bolt.location.copy(); r0 = bolt.rotation_euler.copy()
    stm = [o for o in st if o.type == "MESH"]
    trees = {o.name: bvh(o) for o in stm}
    first = {}
    for i in range(0, 27):
        tr = i * 0.005
        bolt.rotation_euler = (r0.x, r0.y + math.radians(60), r0.z); bolt.location = l0 + Vector((0, tr, 0))
        bpy.context.view_layer.update()
        tb = bvh(bolt)
        for o in stm:
            if o.name not in first and tb.overlap(trees[o.name]):
                first[o.name] = round(tr, 3)
    print("STOCK", stock, "first bolt contact at travel (m):", first, "(documented travel 0.130)")
