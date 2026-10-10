"""Stage N for build_solace.py: normalise the TRELLIS rest pose to the shared agent rest pose (Kestrel's).

Review round 2: the TRELLIS stance was lopsided (her left leg stood under the body, the right foot 0.17 m further
out; the arms hung ~65 deg below horizontal with the elbows behind the torso and the left arm swung back) and the
rig's rest frames differed from Kestrel's by up to 90 deg, so one animation set could not drive both agents.

This stage runs between the texture stage (B) and the parts stage (C):
  1. joints from mesh cross-sections (sol_joints), a temporary armature and skin weights (sol_rig: heat weights with
     the voxel-proxy fallback + the weight rules);
  2. the limb bones are aimed at Kestrel's rest directions (her glb, measured once and written below; mirrored and
     L/R-averaged so the target is symmetric): upper arm, forearm, hand, thigh, shin; the feet only get Kestrel's
     yaw (toe-out) so the soles stay flat; the clavicles swing about Z so both shoulder joints sit at the same depth;
  3. the deformation is applied to SOL_Body as its new rest shape and the temporary rig is deleted.
Stages C (parts on the corrected body) and D (final rig, built with Kestrel's conventions) then run on it.
"""
import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

import sol_rig as R
from sol_lib import log, body, activate

# Kestrel's rest bone directions (kestrel.glb, Blender axes, her LEFT side; R mirrors X). L/R averaged.
KES_DIRS = {
    "upperarm": (0.592, 0.037, -0.805),
    "lowerarm": (0.576, -0.073, -0.814),
    "hand": (0.812, -0.350, -0.459),
    "thigh": (0.168, 0.104, -0.980),
    "calf": (0.139, 0.099, -0.985),
}
KES_FOOT_YAW = math.degrees(math.atan2(0.309, 0.847))     # toe-out of foot_l (ankle -> ball), ~20 deg


def side_dir(key, s):
    d = Vector(KES_DIRS[key])
    return Vector((s * d.x, d.y, d.z)).normalized()


def bone_dir(arm, name):
    bpy.context.view_layer.update()
    pb = arm.pose.bones[name]
    M = arm.matrix_world @ pb.matrix
    return (M.to_3x3() @ Vector((0, 1, 0))).normalized(), M.translation.copy()


def rot_about(arm, name, R3, pivot):
    pb = arm.pose.bones[name]
    bpy.context.view_layer.update()
    M = arm.matrix_world @ pb.matrix
    T = Matrix.Translation(pivot) @ R3.to_4x4() @ Matrix.Translation(-pivot)
    pb.matrix = arm.matrix_world.inverted() @ (T @ M)
    bpy.context.view_layer.update()


def aim(arm, name, target):
    cur, head = bone_dir(arm, name)
    q = cur.rotation_difference(Vector(target).normalized())
    ang = math.degrees(q.angle)
    rot_about(arm, name, q.to_matrix(), head)
    return ang


def normalise_pose(arm, J):
    """Pose the temporary rig into the shared rest pose; returns a dict of applied angles (deg)."""
    done = {}
    for s, sd in ((1, "l"), (-1, "r")):
        # (the shoulder girdle itself is symmetric; sol_joints puts both shoulder pivots at the same depth, so the
        # arm re-aim below also brings her left arm forward)
        for k in ("upperarm", "lowerarm", "hand", "thigh", "calf"):
            done[f"{k}_{sd}"] = aim(arm, f"{k}_{sd}", side_dir(k, s))
        # feet: yaw only (keep the sole flat)
        d, ank = bone_dir(arm, f"foot_{sd}")
        cur = math.degrees(math.atan2(s * d.x, -d.y))
        # toe-out: about +Z for her left foot (toes -Y -> +X), about -Z for her right
        rot_about(arm, f"foot_{sd}", Matrix.Rotation(math.radians(KES_FOOT_YAW - cur) * s, 3, "Z"), ank)
        done[f"foot_{sd}"] = KES_FOOT_YAW - cur
    log("rest-pose normalisation (deg): " + ", ".join(f"{k} {v:+.1f}" for k, v in done.items()))
    return done


def apply_pose_to_mesh(obj, arm):
    activate(obj)
    m = obj.modifiers.get("Armature")
    bpy.ops.object.modifier_apply(modifier=m.name)
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = mw
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    ad = arm.data
    bpy.data.objects.remove(arm, do_unlink=True)
    bpy.data.armatures.remove(ad)


def stage_n():
    import sol_joints as SJ
    b = body()
    co, tris = R.mesh_tris(b)
    J = SJ.find_joints(co, tris, log=log)
    arm = R.build_armature(J, name="_PoseArm")
    bad = R.heat_weights(b, arm)
    if bad > 0.002:
        for g in list(b.vertex_groups):
            b.vertex_groups.remove(g)
        b.parent = None
        for m in list(b.modifiers):
            b.modifiers.remove(m)
        R.proxy_weights(b, arm, voxel=0.006)
    R.apply_weight_rules(b, arm, J, coat_max=0.95)    # the coat flaps follow the re-aimed legs
    R.bind(b, arm)
    z0 = float(np.min(co[:, 2]))
    normalise_pose(arm, J)
    # lower-leg weights per side (calf + foot + ball), to put each sole back on the floor after the re-aim
    W = R.get_weights(b, R.deform_names(arm))
    names = R.deform_names(arm)
    legw = {sd: W[:, [names.index(n) for n in (f"calf_{sd}", f"foot_{sd}", f"ball_{sd}")]].sum(1) for sd in "lr"}
    apply_pose_to_mesh(b, arm)
    from sol_lib import mesh_co, set_mesh_co
    co2 = mesh_co(b.data)
    # soles: each foot's lowest point back on Z = 0 (the re-aimed legs lift or sink a foot by a few mm); the shift
    # rides on the lower-leg weights, so it fades out over the knee (a < 1 cm stretch of the thigh)
    msg = []
    for s, sd in ((1, "l"), (-1, "r")):
        foot = (s * co2[:, 0] > 0.02) & (co2[:, 2] < 0.10) & (legw[sd] > 0.5)
        dz = float(co2[foot, 2].min()) - z0
        co2[:, 2] -= dz * np.clip(legw[sd], 0, 1)
        msg.append(f"{sd} {-dz * 1000:+.1f} mm")
    set_mesh_co(b.data, co2)
    log("stage N done: soles re-grounded (" + ", ".join(msg) + ")")
