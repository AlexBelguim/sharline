"""Independent review of SOLACE: extra renders from the EXPORTED glb (imported into a fresh scene).

blender -b --factory-startup -P rv_render.py -- <mode> [<mode> ...]
modes: rest, clay, wire, close, poses, weapon
Writes only to F:/git/val etf/assets/characters/solace/review/renders/.
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

GLB = r"F:/git/val etf/assets/characters/solace/solace.glb"
MAKO = r"F:/git/val etf/assets/weapons/ar7_mako/mako_default.glb"
OUT = r"F:/git/val etf/assets/characters/solace/review/renders"
os.makedirs(OUT, exist_ok=True)
SAMPLES = int(os.environ.get("RV_SAMPLES", "40"))


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=GLB)
    for o in list(bpy.data.objects):
        if o.name.startswith("Icosphere"):
            o.hide_render = True
            o.hide_viewport = True
    bc.setup_studio()
    sc = bpy.context.scene
    bc.setup_cycles_gpu(sc, SAMPLES)
    sc.render.film_transparent = False
    return bpy.data.objects["SOL_Armature"]


def cam_shot(name, loc, target, lens=50, res=(700, 900), ortho=None):
    sc = bpy.context.scene
    cd = bpy.data.cameras.get("_rvcam") or bpy.data.cameras.new("_rvcam")
    cam = bpy.data.objects.get("_rvcam") or bpy.data.objects.new("_rvcam", cd)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cd.lens = lens
    cd.clip_start = 0.005
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.type = "PERSP"
    cam.location = Vector(loc)
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    p = os.path.join(OUT, name + ".png")
    sc.render.filepath = p
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("GPU render failed, CPU fallback", e)
        sc.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("rendered", p)
    return p


def around(target, direction, dist):
    d = Vector(direction).normalized()
    return tuple(Vector(target) + d * dist)


def shot(name, target, direction, dist, lens=50, res=(700, 900)):
    return cam_shot(name, around(target, direction, dist), target, lens, res)


# ------------------------------------------------------------------------------------------- posing
def rot_world(arm, bone, axis, deg):
    pb = arm.pose.bones[bone]
    bpy.context.view_layer.update()
    M = arm.matrix_world @ pb.matrix
    h = M.translation.copy()
    R = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, Vector(axis)) @ Matrix.Translation(-h)
    pb.matrix = arm.matrix_world.inverted() @ (R @ M)
    bpy.context.view_layer.update()


def bone_dir(arm, bone):
    b = arm.data.bones[bone]
    return (arm.matrix_world @ b.tail_local - arm.matrix_world @ b.head_local).normalized()


def aim_bone(arm, bone, target_dir):
    """Rotate a bone (world space, about its head) so its direction becomes target_dir."""
    bpy.context.view_layer.update()
    pb = arm.pose.bones[bone]
    M = arm.matrix_world @ pb.matrix
    cur = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    q = cur.rotation_difference(Vector(target_dir).normalized())
    h = M.translation.copy()
    R = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
    pb.matrix = arm.matrix_world.inverted() @ (R @ M)
    bpy.context.view_layer.update()


def reset(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


# ------------------------------------------------------------------------------------------- modes
def mode_rest(arm):
    c = (0, 0.02, 0.86)
    shot("rv_top", (0, 0.04, 1.2), (0, -0.25, 1), 2.6, lens=50)
    shot("rv_low_front", (0, -0.02, 0.95), (0.35, -1, -0.75), 2.4, lens=50)
    shot("rv_low_back", (0, 0.05, 0.95), (-0.3, 1, -0.6), 2.4, lens=50)
    shot("rv_side_left_ortho", c, (-1, 0, 0), 3.0, lens=50)
    shot("rv_far_front", c, (0.3, -1, 0.05), 14.0, lens=50, res=(360, 480))   # game distance ~14 m
    shot("rv_far_back", c, (-0.3, 1, 0.05), 14.0, lens=50, res=(360, 480))


def mode_clay(arm):
    clay = bc.material("_rv_clay", (0.5, 0.5, 0.5), rough=0.6)
    bpy.context.view_layer.material_override = clay
    c = (0, 0.02, 0.86)
    shot("rv_clay_front", c, (0, -1, 0.06), 3.0)
    shot("rv_clay_tq", c, (0.8, -1, 0.3), 3.0)
    shot("rv_clay_back_tq", c, (-0.8, 1, 0.3), 3.0)
    shot("rv_clay_head", (0, 0.0, 1.56), (0.6, -1, 0.15), 0.75, lens=60, res=(700, 700))
    shot("rv_clay_hands", (-0.43, -0.02, 0.9), (-0.3, -1, 0.1), 0.6, lens=60, res=(700, 700))
    bpy.context.view_layer.material_override = None


def mode_wire(arm):
    body = bpy.data.objects["SOL_Body"]
    w = body.copy()
    w.data = body.data.copy()
    bpy.context.scene.collection.objects.link(w)
    dark = bc.material("_rv_wire", (0.0, 0.0, 0.0), rough=0.9, emission=(0.02, 0.9, 1.0), emission_strength=1.5)
    w.data.materials.clear()
    w.data.materials.append(dark)
    m = w.modifiers.new("wf", "WIREFRAME")
    m.thickness = 0.0007
    m.use_relative_offset = False
    m.offset = 1.0
    w.parent = body.parent
    shot("rv_wire_head", (0, 0.0, 1.56), (0.5, -1, 0.15), 0.7, lens=60, res=(800, 800))
    shot("rv_wire_body_front", (0, 0.0, 0.86), (0.3, -1, 0.1), 3.0, lens=50, res=(700, 900))
    shot("rv_wire_back", (0, 0.1, 1.15), (-0.3, 1, 0.2), 1.6, lens=50, res=(700, 900))
    bpy.data.objects.remove(w)


def mode_close(arm):
    shot("rv_close_emblem", (0.255, -0.02, 1.30), (0.8, -0.9, 0.25), 0.42, lens=60, res=(700, 700))
    shot("rv_close_bracer_front", (-0.42, -0.03, 1.04), (-0.4, -1, 0.35), 0.55, lens=60, res=(700, 700))
    shot("rv_close_bracer_top", (-0.40, -0.03, 1.06), (-0.1, -0.35, 1), 0.55, lens=60, res=(700, 700))
    shot("rv_close_drone", (0.17, -0.06, 1.0), (0.7, -1, 0.15), 0.45, lens=60, res=(700, 700))
    shot("rv_close_pouch_belt", (-0.08, -0.08, 0.98), (-0.4, -1, 0.1), 0.6, lens=60, res=(700, 700))
    shot("rv_close_collar_back", (0, 0.04, 1.42), (-0.5, 0.8, 0.8), 0.55, lens=60, res=(700, 700))
    shot("rv_close_shoulder_r", (-0.14, 0.0, 1.38), (-1, -0.4, 0.5), 0.55, lens=60, res=(700, 700))
    shot("rv_close_bud_side", (0.0, 0.15, 1.33), (1, 0.15, 0.1), 0.85, lens=60, res=(700, 800))
    shot("rv_close_hem_back", (0, 0.10, 0.76), (0.15, 1, -0.2), 0.75, lens=60, res=(700, 700))
    shot("rv_close_boots", (-0.08, 0.0, 0.08), (0.4, -1, 0.35), 0.8, lens=60, res=(800, 600))
    # first-person view of the right forearm: camera at the eyes, arm raised as if holding a rifle
    reset(arm)
    aim_bone(arm, "upperarm_r", (-0.25, -0.75, -0.6))
    aim_bone(arm, "lowerarm_r", (0.35, -0.9, 0.1))
    aim_bone(arm, "upperarm_l", (0.35, -0.8, -0.45))
    aim_bone(arm, "lowerarm_l", (-0.45, -0.85, 0.15))
    cam_shot("rv_fp_view", (0.0, -0.06, 1.57), (-0.05, -0.6, 1.25), lens=24, res=(960, 540))
    reset(arm)


def mode_poses(arm):
    c = (0, 0.0, 0.86)
    # 1. a real arms-down (upper arms hanging vertically at the sides, slight outward)
    reset(arm)
    aim_bone(arm, "upperarm_l", (0.12, 0.02, -1))
    aim_bone(arm, "upperarm_r", (-0.12, 0.02, -1))
    aim_bone(arm, "lowerarm_l", (0.05, -0.15, -1))
    aim_bone(arm, "lowerarm_r", (-0.05, -0.15, -1))
    aim_bone(arm, "hand_l", (0.03, -0.1, -1))
    aim_bone(arm, "hand_r", (-0.03, -0.1, -1))
    shot("rv_pose_armsdown_front", c, (0, -1, 0.06), 3.0)
    shot("rv_pose_armsdown_back", c, (0, 1, 0.06), 3.0)
    shot("rv_pose_armsdown_shoulder", (-0.17, 0.0, 1.3), (-0.6, -1, 0.3), 0.7, lens=60, res=(700, 700))
    # 2. rifle hold
    reset(arm)
    aim_bone(arm, "upperarm_r", (-0.25, -0.75, -0.6))
    aim_bone(arm, "lowerarm_r", (0.35, -0.9, 0.1))
    aim_bone(arm, "upperarm_l", (0.35, -0.8, -0.45))
    aim_bone(arm, "lowerarm_l", (-0.45, -0.85, 0.15))
    shot("rv_pose_rifle_tq", (0, -0.1, 1.15), (0.8, -1, 0.25), 2.2)
    shot("rv_pose_rifle_back_tq", (0, 0.0, 1.15), (-0.8, 1, 0.3), 2.2)
    shot("rv_pose_rifle_shoulder_r", (-0.16, -0.02, 1.32), (-0.9, -0.5, 0.35), 0.7, lens=60, res=(700, 700))
    # 3. arms overhead (zipline hang)
    reset(arm)
    aim_bone(arm, "upperarm_l", (0.25, -0.05, 1))
    aim_bone(arm, "upperarm_r", (-0.25, -0.05, 1))
    aim_bone(arm, "lowerarm_l", (0.05, -0.05, 1))
    aim_bone(arm, "lowerarm_r", (-0.05, -0.05, 1))
    shot("rv_pose_overhead_front", (0, 0, 1.1), (0.3, -1, 0.1), 3.4)
    shot("rv_pose_overhead_back", (0, 0.05, 1.3), (-0.4, 1, 0.2), 2.0)
    # 4. long stride, side and back (coat tail + cross-side weights)
    reset(arm)
    rot_world(arm, "thigh_l", (1, 0, 0), -55)
    rot_world(arm, "calf_l", (1, 0, 0), 40)
    rot_world(arm, "thigh_r", (1, 0, 0), 30)
    rot_world(arm, "calf_r", (1, 0, 0), 35)
    shot("rv_pose_stride_side", c, (1, 0, 0.05), 3.0)
    shot("rv_pose_stride_back", c, (-0.2, 1, 0.1), 3.0)
    shot("rv_pose_stride_low", (0, 0, 0.75), (0.5, -1, -0.5), 1.8)
    # 5. leg side-raise (straddle / ledge step): thigh_l out 45 deg
    reset(arm)
    rot_world(arm, "thigh_l", (0, 1, 0), -45)
    rot_world(arm, "thigh_r", (1, 0, 0), -70)
    rot_world(arm, "calf_r", (1, 0, 0), 80)
    shot("rv_pose_legs_front", c, (0.2, -1, 0.05), 3.0)
    shot("rv_pose_legs_back", c, (-0.2, 1, 0.05), 3.0)
    # 6. aim pitch: head down + torso twist
    reset(arm)
    rot_world(arm, "spine_02", (0, 0, 1), 25)
    rot_world(arm, "spine_03", (0, 0, 1), 15)
    rot_world(arm, "neck_01", (1, 0, 0), 20)
    rot_world(arm, "head", (1, 0, 0), 20)
    shot("rv_pose_twist_lookdown_tq", (0, 0, 1.2), (0.8, -1, 0.3), 2.0)
    shot("rv_pose_twist_lookdown_back", (0, 0.05, 1.3), (-0.5, 1, 0.3), 1.6)
    reset(arm)
    rot_world(arm, "neck_01", (1, 0, 0), -18)
    rot_world(arm, "head", (1, 0, 0), -22)
    shot("rv_pose_lookup_side", (0, 0.0, 1.4), (-1, -0.1, 0.1), 1.1)
    reset(arm)


def mode_weapon(arm):
    reset(arm)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=MAKO)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.name.startswith("Icosphere"):
            o.hide_render = True
    root = next(o for o in new if o.parent is None and o.name.startswith("MAKO_Root")) if any(
        o.name.startswith("MAKO_Root") for o in new) else None
    tops = [o for o in new if o.parent is None]
    print("mako top-level", [o.name for o in tops])
    sock = bpy.data.objects["SOL_SOCKET_WeaponR"]
    bpy.context.view_layer.update()
    for o in tops:
        mw = o.matrix_world.copy()
        o.parent = sock
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.matrix_basis = mw   # weapon origin = grip; its world transform at import becomes local to the socket
    bpy.context.view_layer.update()
    shot("rv_weapon_rest_front", (-0.40, -0.1, 0.95), (-0.3, -1, 0.2), 1.3, lens=50, res=(700, 700))
    shot("rv_weapon_rest_side", (-0.40, -0.1, 0.95), (-1, -0.1, 0.1), 1.3, lens=50, res=(700, 700))
    # rifle-hold pose with the gun in the right hand
    aim_bone(arm, "upperarm_r", (-0.25, -0.75, -0.6))
    aim_bone(arm, "lowerarm_r", (0.35, -0.9, 0.1))
    aim_bone(arm, "upperarm_l", (0.35, -0.8, -0.45))
    aim_bone(arm, "lowerarm_l", (-0.45, -0.85, 0.15))
    shot("rv_weapon_hold_tq", (-0.1, -0.3, 1.1), (0.6, -1, 0.3), 1.8)
    shot("rv_weapon_hold_side", (-0.1, -0.3, 1.1), (-1, 0, 0.1), 1.8)
    reset(arm)


if __name__ == "__main__":
    modes = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["rest"]
    arm = setup()
    for md in modes:
        globals()["mode_" + md](arm)
