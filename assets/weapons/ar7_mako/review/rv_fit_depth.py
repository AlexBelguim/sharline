"""Penetration depth of attachment vertices into the current MAKO GLB (nearest-face side test)."""
import json, os, sys
import bmesh, bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
ATT = r"F:/git/val etf/assets/weapons/attachments"
SOCK = json.load(open(os.path.join(HERE, "sockets.json")))
bpy.ops.wm.read_factory_settings(use_empty=True)
def imp(p, at):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=p)
    new = [o for o in bpy.data.objects if o not in before]
    for t in new:
        if t.parent is None or t.parent not in new:
            t.location = Vector(t.location) + Vector(at)
    bpy.context.view_layer.update()
    return [o for o in new if o.type == "MESH"]
def bm_of(objs):
    bm = bmesh.new()
    for o in objs:
        tmp = bmesh.new(); tmp.from_mesh(o.data); tmp.transform(o.matrix_world)
        m2 = bpy.data.meshes.new("_t"); tmp.to_mesh(m2); bm.from_mesh(m2); bpy.data.meshes.remove(m2); tmp.free()
    bm.normal_update()
    return bm
gun = imp(os.path.join(HERE, "mako_base.glb"), (0,0,0))
gun += imp(os.path.join(HERE, "MAKO_stock_standard.glb"), SOCK["MAKO_SOCKET_Stock"]["location"])
gun += imp(os.path.join(HERE, "MAKO_mag_30.glb"), SOCK["MAKO_SOCKET_Mag"]["location"])
gbm = bm_of(gun); gbvh = BVHTree.FromBMesh(gbm)
names = {}
for o in gun:
    pass
res = {}
for key, f, s in (("grip_vertical","tactical/ATT_grip_vertical.glb","Under"),("ugl","tactical/ATT_ugl_launcher.glb","Under"),
                  ("laser_R","tactical/ATT_laser_R.glb","Side_R"),("flashlight_L","tactical/ATT_flashlight_L.glb","Side_L"),
                  ("shield","tactical/ATT_shield_front.glb","Shield"),("optic_holo","optics/ATT_optic_holo.glb","Optic")):
    objs = imp(os.path.join(ATT, f), SOCK[f"MAKO_SOCKET_{s}"]["location"])
    abm = bm_of(objs)
    worst = 0.0; n_in = 0; wpt = None
    for v in abm.verts:
        loc, nrm, idx, d = gbvh.find_nearest(v.co)
        if loc is None or d > 0.01: continue
        side = (v.co - loc).dot(nrm)
        if side < -0.0003:
            n_in += 1
            if -side > worst: worst = -side; wpt = [round(c,4) for c in v.co]
    res[key] = {"verts_inside_gun_gt_0.3mm": n_in, "max_depth_m": round(worst,4), "deepest_vertex": wpt}
    for o in objs: bpy.data.objects.remove(o, do_unlink=True)
print("DEPTH", json.dumps(res, indent=0))
json.dump(res, open(os.path.join(HERE, "review", "fit_depth.json"), "w"), indent=1)
