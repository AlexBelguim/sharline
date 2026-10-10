"""Independent review of SOLACE: head-pitch / head-yaw clipping of hair into the Bloom bud (exported glb).

blender -b --factory-startup -P rv_clip.py
Prints overlap counts and renders two close-ups into review/renders/.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

GLB = r"F:/git/val etf/assets/characters/solace/solace.glb"
OUT = r"F:/git/val etf/assets/characters/solace/review/renders"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
for o in list(bpy.data.objects):
    if o.name.startswith("Icosphere"):
        o.hide_render = True
arm = bpy.data.objects["SOL_Armature"]
body = bpy.data.objects["SOL_Body"]
vanes = [bpy.data.objects[n] for n in ("SOL_Bloom_Vane_C", "SOL_Bloom_Vane_L", "SOL_Bloom_Vane_R", "SOL_Bloom")]


def rot_world(bone, axis, deg):
    pb = arm.pose.bones[bone]
    bpy.context.view_layer.update()
    M = arm.matrix_world @ pb.matrix
    h = M.translation.copy()
    R = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, Vector(axis)) @ Matrix.Translation(-h)
    pb.matrix = arm.matrix_world.inverted() @ (R @ M)
    bpy.context.view_layer.update()


def reset():
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def bvh(o, zmin=None):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    m = oe.to_mesh()
    vs = [o.matrix_world @ v.co for v in m.vertices]
    polys = [tuple(p.vertices) for p in m.polygons if zmin is None or (o.matrix_world @ p.center).z > zmin]
    t = BVHTree.FromPolygons(vs, polys)
    oe.to_mesh_clear()
    return t


def test(label):
    hb = bvh(body, zmin=1.35)   # head, hair, ponytail, collar region only
    tot = 0
    per = []
    for v in vanes:
        n = len(hb.overlap(bvh(v)))
        per.append(n)
        tot += n
    print("[RC] %-34s overlaps head-region x (C, L, R, module) = %s" % (label, per))


reset()
test("rest")
for pitch in (10, 20, 30, 40):
    reset()
    rot_world("neck_01", (1, 0, 0), -pitch * 0.45)
    rot_world("head", (1, 0, 0), -pitch * 0.55)
    test(f"look up {pitch} deg (neck+head)")
for yaw in (45, 70, 90):
    for sgn, nm in ((1, "left"), (-1, "right")):
        reset()
        rot_world("neck_01", (0, 0, 1), sgn * yaw * 0.45)
        rot_world("head", (0, 0, 1), sgn * yaw * 0.55)
        test(f"turn {nm} {yaw} deg")
for yaw in (60,):
    reset()
    rot_world("neck_01", (0, 0, 1), yaw * 0.45)
    rot_world("head", (0, 0, 1), yaw * 0.55)
    rot_world("head", (1, 0, 0), -20)
    test("turn left 60 + look up 20")
# render the 30 deg look-up and a 70 deg turn
bc.setup_studio()
bc.setup_cycles_gpu(bpy.context.scene, 40)
reset()
rot_world("neck_01", (1, 0, 0), -30 * 0.45)
rot_world("head", (1, 0, 0), -30 * 0.55)
bc.render_views(OUT, "rv_clip_lookup30", views=[(1, 0.25, 0.15)], res=(700, 700), engine="CYCLES", samples=40,
                lens=60, focus=((0, 0.1, 1.5), 0.22))
reset()
rot_world("neck_01", (0, 0, 1), -70 * 0.45)
rot_world("head", (0, 0, 1), -70 * 0.55)
bc.render_views(OUT, "rv_clip_turnR70", views=[(-0.6, 1, 0.5)], res=(700, 700), engine="CYCLES", samples=40,
                lens=60, focus=((0, 0.1, 1.5), 0.25))
# first-person view: camera just in front of the face, rifle-ish arm pose
reset()


def aim_bone(bone, target_dir):
    bpy.context.view_layer.update()
    pb = arm.pose.bones[bone]
    M = arm.matrix_world @ pb.matrix
    cur = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    q = cur.rotation_difference(Vector(target_dir).normalized())
    h = M.translation.copy()
    R = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
    pb.matrix = arm.matrix_world.inverted() @ (R @ M)
    bpy.context.view_layer.update()


aim_bone("upperarm_r", (-0.25, -0.75, -0.6))
aim_bone("lowerarm_r", (0.35, -0.9, 0.1))
aim_bone("upperarm_l", (0.35, -0.8, -0.45))
aim_bone("lowerarm_l", (-0.45, -0.85, 0.15))
sc = bpy.context.scene
cd = bpy.data.cameras.new("_fp")
cam = bpy.data.objects.new("_fp", cd)
sc.collection.objects.link(cam)
cd.lens = 18
cd.clip_start = 0.02
cam.location = Vector((0.0, -0.13, 1.56))
cam.rotation_euler = (Vector((-0.08, -0.6, 1.2)) - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.camera = cam
sc.render.resolution_x, sc.render.resolution_y = 960, 540
sc.render.filepath = os.path.join(OUT, "rv_fp_view.png")
bpy.ops.render.render(write_still=True)
print("[RC] fp rendered")
