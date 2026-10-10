"""Pose tests for KESTREL's rig (used by stage E and while tuning the weights).

Each pose is built from world-space "bends" applied parent-first: a bone is rotated about its head so its tail
swings toward a world direction (or twists about a world axis). The root is lowered afterwards so the lowest
foot point touches Z=0.

Review round 2 added the poses the review stressed: rifle-ready (the pose opponents see most), the two-arm and
one-arm zipline hang, head pitched down / up and turned 60 deg (nape), and a weapon grip (fingers curled around a
pistol grip) for the socket check.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import kes_rig as R

FWD = Vector((0, -1, 0))
BACK = Vector((0, 1, 0))
DOWN = Vector((0, 0, -1))
UP = Vector((0, 0, 1))


def _dir(pb):
    return (pb.tail - pb.head).normalized()


def bend(arm, name, toward, deg):
    """Rotate bone `name` about its head so its direction turns toward the world vector `toward`."""
    pb = arm.pose.bones[name]
    d = _dir(pb)
    ax = d.cross(Vector(toward))
    if ax.length < 1e-6:
        return
    rot = Matrix.Rotation(math.radians(deg), 4, ax.normalized())
    _apply(arm, pb, rot)


def aim(arm, name, target, frac=1.0):
    """Rotate bone `name` about its head so it points along the world direction `target` (frac of the way)."""
    pb = arm.pose.bones[name]
    d = _dir(pb)
    t = Vector(target).normalized()
    ax = d.cross(t)
    if ax.length < 1e-6:
        return
    ang = math.acos(max(-1.0, min(1.0, d.dot(t)))) * frac
    _apply(arm, pb, Matrix.Rotation(ang, 4, ax.normalized()))


def twist(arm, name, axis, deg):
    pb = arm.pose.bones[name]
    _apply(arm, pb, Matrix.Rotation(math.radians(deg), 4, Vector(axis).normalized()))


def _apply(arm, pb, rot):
    M = pb.matrix.copy()
    h = M.translation.copy()
    pb.matrix = Matrix.Translation(h) @ rot @ Matrix.Translation(-h) @ M
    bpy.context.view_layer.update()


def reset(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def _root_drop(arm, dz):
    pb = arm.pose.bones["root"]
    M = pb.matrix.copy()
    M.translation.z -= dz
    pb.matrix = M
    bpy.context.view_layer.update()


def palm_dir(arm, s):
    """Palm normal (from the rest-pose hand analysis, flipped to the palm side in kes_skin) carried through the
    hand bone's current pose rotation."""
    hf = arm.get(f"kes_hand_{s}")
    n = Vector(hf["n"]) if hf else DOWN
    pb = arm.pose.bones[f"hand_{s}"]
    rot = pb.matrix.to_3x3() @ arm.data.bones[f"hand_{s}"].matrix_local.to_3x3().inverted()
    return (rot @ n).normalized()


def curl_fingers(arm, s, amounts=(70, 85, 60), thumb_sweep=55, thumb=(20, 30)):
    """Fist test: every finger bone bends toward the palm side. The thumb sweeps across the palm about the hand's
    long axis (sign chosen so its tip ends nearest the middle knuckle), then its two outer joints fold."""
    pd = palm_dir(arm, s)
    for f in R.FINGERS:
        for k, a in zip((1, 2, 3), amounts):
            pb = arm.pose.bones[f"{f}_0{k}_{s}"]
            ax = _dir(pb).cross(pd)
            if ax.length > 1e-6:
                _apply(arm, pb, Matrix.Rotation(math.radians(a), 4, ax.normalized()))
    hand = arm.pose.bones[f"hand_{s}"]
    long_ax = _dir(hand)
    t1 = arm.pose.bones[f"thumb_01_{s}"]
    target = arm.pose.bones[f"middle_01_{s}"].head.copy()
    M0 = t1.matrix.copy()
    best = None
    for sign in (1, -1):
        t1.matrix = M0
        bpy.context.view_layer.update()
        _apply(arm, t1, Matrix.Rotation(math.radians(sign * thumb_sweep), 4, long_ax))
        d = (arm.pose.bones[f"thumb_03_{s}"].tail - target).length
        if best is None or d < best[0]:
            best = (d, sign)
    t1.matrix = M0
    bpy.context.view_layer.update()
    _apply(arm, t1, Matrix.Rotation(math.radians(best[1] * thumb_sweep), 4, long_ax))
    for k, a in zip((2, 3), thumb):
        pb = arm.pose.bones[f"thumb_0{k}_{s}"]
        tgt = (target - pb.head).normalized()
        ax = _dir(pb).cross(tgt)
        if ax.length > 1e-6:
            _apply(arm, pb, Matrix.Rotation(math.radians(a), 4, ax.normalized()))


def pose_rifle(arm):
    """Rifle ready: upper arms down-forward, elbows bent ~95 deg, forearms forward, torso turned slightly."""
    aim(arm, "upperarm_r", (0.25, -0.45, -1.0))
    aim(arm, "lowerarm_r", (0.35, -1.0, 0.05))
    aim(arm, "upperarm_l", (0.05, -0.75, -0.6))
    aim(arm, "lowerarm_l", (-0.35, -1.0, 0.15))
    for s in ("l", "r"):
        aim(arm, f"hand_{s}", (0.0, -1.0, -0.2), 0.5)
    twist(arm, "spine_02", UP, -8)
    twist(arm, "spine_03", UP, -8)


def pose_zipline(arm, one_arm=False):
    """Zipline hang: arm(s) straight up, slightly forward, clavicles raised; legs bent a little."""
    sides = (("r", -1),) if one_arm else (("l", 1), ("r", -1))
    for s, x in sides:
        aim(arm, f"clavicle_{s}", (x * 0.8, 0.0, 0.6), 0.6)
        aim(arm, f"upperarm_{s}", (x * 0.18, -0.15, 1.0))
        aim(arm, f"lowerarm_{s}", (x * 0.05, -0.2, 1.0))
    if one_arm:
        aim(arm, "upperarm_l", (0.25, 0.0, -1.0))
    for s, x in (("l", 1), ("r", -1)):
        aim(arm, f"thigh_{s}", (x * 0.1, -0.5, -1.0))
        aim(arm, f"calf_{s}", (x * 0.05, 0.6, -1.0))


def pose(arm, name):
    reset(arm)
    if name == "rest":
        return
    if name in ("arms_down", "fists", "run", "crouch", "head_turn", "head_down", "head_yaw60"):
        for s in ("l", "r"):
            bend(arm, f"upperarm_{s}", DOWN, 34)
            bend(arm, f"lowerarm_{s}", FWD, 12)
    if name == "fists":
        for s in ("l", "r"):
            bend(arm, f"lowerarm_{s}", FWD, 55)
            curl_fingers(arm, s)
    elif name == "grip":
        for s in ("l", "r"):
            curl_fingers(arm, s, amounts=(55, 70, 45), thumb_sweep=35, thumb=(10, 15))
    elif name == "crouch":
        bend(arm, "spine_01", FWD, 12)
        bend(arm, "spine_02", FWD, 10)
        bend(arm, "spine_03", FWD, 6)
        bend(arm, "neck_01", BACK, 14)
        for s in ("l", "r"):
            bend(arm, f"thigh_{s}", FWD, 100)
            bend(arm, f"calf_{s}", BACK, 125)
            bend(arm, f"foot_{s}", DOWN, 10)
            bend(arm, f"upperarm_{s}", FWD, 45)
            bend(arm, f"lowerarm_{s}", UP, 40)
    elif name == "run":
        bend(arm, "spine_01", FWD, 6)
        twist(arm, "spine_02", UP, 8)
        twist(arm, "spine_03", UP, 8)
        bend(arm, "thigh_l", FWD, 55)
        bend(arm, "calf_l", BACK, 75)
        bend(arm, "thigh_r", BACK, 28)
        bend(arm, "calf_r", BACK, 85)
        bend(arm, "foot_r", DOWN, 25)
        bend(arm, "upperarm_r", FWD, 40)
        bend(arm, "lowerarm_r", UP, 75)
        bend(arm, "upperarm_l", BACK, 35)
        bend(arm, "lowerarm_l", FWD, 60)
    elif name == "head_turn":
        twist(arm, "neck_01", UP, 20)
        twist(arm, "head", UP, 25)
    elif name == "head_yaw60":
        twist(arm, "neck_01", UP, 25)
        twist(arm, "head", UP, 35)
    elif name == "head_down":
        twist(arm, "neck_01", Vector((1, 0, 0)), 10)
        twist(arm, "head", Vector((1, 0, 0)), 20)
    elif name == "rifle":
        pose_rifle(arm)
    elif name == "zipline":
        pose_zipline(arm)
    elif name == "zipline_one":
        pose_zipline(arm, one_arm=True)
    bpy.context.view_layer.update()


def drop_to_floor(arm, objs):
    dg = bpy.context.evaluated_depsgraph_get()
    zmin = 1e9
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        mw = np.array(o.matrix_world)
        co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        zmin = min(zmin, float(co[:, 2].min()))
        ev.to_mesh_clear()
    _root_drop(arm, zmin)
