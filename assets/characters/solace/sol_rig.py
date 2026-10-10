"""Stage D for build_solace.py: UE5-mannequin-named armature, skin weights, rigid parts.

Bones (UE5 mannequin names; _l = her LEFT = +X):
  root > pelvis > spine_01 > spine_02 > spine_03 > neck_01 > head
  spine_03 > clavicle_l/r > upperarm > lowerarm > hand > thumb/index/middle/ring/pinky _01.._03
  pelvis > thigh_l/r > calf > foot > ball
Rest frames follow Kestrel's rig exactly (review round 2: one glTF animation set drives both agents): the spine,
neck, head and clavicles sit on Kestrel's rest directions (kestrel_conventions), the limbs too (stage N re-aimed the
mesh's limbs onto them first), and the rolls are Kestrel's: pelvis / spine / neck / head / thigh / calf local Z
forward (-Y); clavicle / arm / hand / finger / foot / ball local Z up (+Z projected).

Weights: Blender heat weighting on the body; if it fails (verts left unweighted) the voxel-proxy fallback runs
(4 mm solidify + 6 mm voxel remesh of the body -> heat weights on the proxy -> nearest-face-interpolated transfer).
Then rule-based fixes: head/hair rigid to head, ponytail head -> neck_01 -> spine_03 blend, coat tail pelvis/thigh
blend (no tearing), bracer rigid to lowerarm_r, pouch rigid to pelvis; smoothing; leak rules (no leg weight above
the belt, no cross-side weights, finger weights only in front of the wrist, fused finger pairs tied); max 4.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree

import blender_common as bc
from sol_lib import log, body, mesh_co, activate, img_to_np, smoothstep, hair_like, face_tex_colors

FINGERS = ("thumb", "index", "middle", "ring", "pinky")
DEFORM = None


# Kestrel's rest spine directions (kestrel.glb, Blender axes): the shared agent skeleton convention (review round 2)
KES_SPINE = {"pelvis": (0.0, -0.130, 0.991), "spine_01": (0.0, -0.023, 1.0), "spine_02": (0.0, 0.057, 0.998),
             "spine_03": (0.0, 0.050, 0.999), "neck_01": (0.0, 0.0, 1.0)}
KES_CLAVICLE = (0.958, 0.064, -0.278)      # her LEFT clavicle (sternum end -> shoulder); R mirrors X


def kestrel_conventions(J):
    """Move the spine / neck / head / clavicle joints onto Kestrel's rest directions (same rest frames -> one glTF
    animation set drives both agents). The spine keeps its measured heights; one Y offset is fitted to the
    measured joints so the chain stays inside the torso. The clavicle's sternum end is placed on Kestrel's
    clavicle line through the measured shoulder."""
    J = dict(J)
    chain = ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01"]
    zs = [float(J[n][2]) for n in chain]
    rel = [0.0]
    for k in range(len(chain) - 1):
        d = KES_SPINE[chain[k]]
        rel.append(rel[-1] + (zs[k + 1] - zs[k]) * d[1] / d[2])
    meas = np.array([float(J[n][1]) for n in chain])
    y0 = float(np.mean(meas - np.array(rel)))
    for n, z, r in zip(chain, zs, rel):
        J[n] = np.array([0.0, y0 + r, z])
    yn = y0 + rel[-1]
    J["head"] = np.array([0.0, yn, float(J["head"][2])])
    J["_head_top"] = np.array([0.0, yn, float(J["_head_top"][2])])
    moved = []
    for s, sd in ((1, "l"), (-1, "r")):
        sh = np.asarray(J[f"upperarm_{sd}"], float)
        d = np.array([s * KES_CLAVICLE[0], KES_CLAVICLE[1], KES_CLAVICLE[2]])
        L = (abs(sh[0]) - 0.022) / KES_CLAVICLE[0]
        J[f"clavicle_{sd}"] = sh - d * L

        def kd(key):
            v = KES_LIMBS[key]
            return np.array([s * v[0], v[1], v[2]]) / np.linalg.norm(v)

        # arm: the limbs were re-aimed onto these directions in stage N; keep the measured segment lengths
        el0, wr0 = np.asarray(J[f"lowerarm_{sd}"], float), np.asarray(J[f"hand_{sd}"], float)
        el = sh + kd("upperarm") * np.linalg.norm(el0 - sh)
        wr = el + kd("lowerarm") * np.linalg.norm(wr0 - el0)
        hend0 = 0.5 * (np.asarray(J[f"middle_01_{sd}"]) + np.asarray(J[f"index_01_{sd}"]))
        J[f"lowerarm_{sd}"], J[f"hand_{sd}"] = el, wr
        J[f"_hand_end_{sd}"] = wr + kd("hand") * np.linalg.norm(hend0 - wr0)
        moved += [np.linalg.norm(el - el0), np.linalg.norm(wr - wr0)]
        # leg: hip -> knee -> ankle (ankle at Kestrel's height 0.09) -> ball (Z 0.032) -> toe
        hip, kn0, an0 = (np.asarray(J[k], float) for k in (f"thigh_{sd}", f"calf_{sd}", f"foot_{sd}"))
        kn = hip + kd("thigh") * np.linalg.norm(kn0 - hip)
        dc = kd("calf")
        an = kn + dc * (kn[2] - 0.090) / -dc[2]
        df = kd("foot")
        ball = an + df * (0.090 - 0.032) / -df[2]
        J[f"calf_{sd}"], J[f"foot_{sd}"], J[f"ball_{sd}"] = kn, an, ball
        J[f"_toe_{sd}"] = ball + kd("ball") * 0.060
        moved += [np.linalg.norm(kn - kn0), np.linalg.norm(an - an0)]
    log(f"Kestrel limb directions: joints moved by at most {max(moved) * 100:.1f} cm from the measured ones")
    return J


# Kestrel's limb rest directions (her LEFT side, Blender axes; L/R averaged). Stage N aims the mesh onto them.
KES_LIMBS = {"upperarm": (0.592, 0.037, -0.805), "lowerarm": (0.576, -0.073, -0.814), "hand": (0.812, -0.350, -0.459),
             "thigh": (0.168, 0.104, -0.980), "calf": (0.139, 0.099, -0.985), "foot": (0.309, -0.847, -0.432),
             "ball": (0.111, -0.993, -0.028)}


def bone_specs(J):
    """[(name, head, tail, parent, roll_vector)]. Rolls follow Kestrel's rig (kes_rig.build_armature): pelvis, spine,
    neck, head, thigh and calf: local Z forward (-Y); foot, ball, clavicle, arm, hand and finger bones: local Z up
    (+Z projected). Bone Y always points from the joint to its child."""
    v = lambda k: Vector(J[k])  # noqa: E731
    fwd, up = (0, -1, 0), (0, 0, 1)
    B = []
    B.append(("root", Vector((0, 0, 0)), Vector((0, 0, 0.12)), None, fwd))
    B.append(("pelvis", v("pelvis"), v("spine_01"), "root", fwd))
    B.append(("spine_01", v("spine_01"), v("spine_02"), "pelvis", fwd))
    B.append(("spine_02", v("spine_02"), v("spine_03"), "spine_01", fwd))
    B.append(("spine_03", v("spine_03"), v("neck_01"), "spine_02", fwd))
    B.append(("neck_01", v("neck_01"), v("head"), "spine_03", fwd))
    B.append(("head", v("head"), v("_head_top"), "neck_01", fwd))
    for sd in ("l", "r"):
        B.append((f"clavicle_{sd}", v(f"clavicle_{sd}"), v(f"upperarm_{sd}"), "spine_03", up))
        B.append((f"upperarm_{sd}", v(f"upperarm_{sd}"), v(f"lowerarm_{sd}"), f"clavicle_{sd}", up))
        B.append((f"lowerarm_{sd}", v(f"lowerarm_{sd}"), v(f"hand_{sd}"), f"upperarm_{sd}", up))
        if f"_hand_end_{sd}" in J:
            mid = v(f"_hand_end_{sd}")
        elif f"middle_01_{sd}" in J and f"index_01_{sd}" in J:
            mid = (v(f"middle_01_{sd}") + v(f"index_01_{sd}")) / 2      # Kestrel: hand end = index/middle MCPs
        else:
            mid = v(f"hand_{sd}") + (v(f"_tip_{sd}") - v(f"hand_{sd}")) * 0.45
        B.append((f"hand_{sd}", v(f"hand_{sd}"), mid, f"lowerarm_{sd}", up))
        for fg in FINGERS:
            if f"{fg}_01_{sd}" not in J:
                continue
            chain = [v(f"{fg}_01_{sd}"), v(f"{fg}_02_{sd}"), v(f"{fg}_03_{sd}"), v(f"_{fg}_tip_{sd}")]
            par = f"hand_{sd}"
            for i in range(3):
                nm = f"{fg}_0{i + 1}_{sd}"
                B.append((nm, chain[i], chain[i + 1], par, up))
                par = nm
        B.append((f"thigh_{sd}", v(f"thigh_{sd}"), v(f"calf_{sd}"), "pelvis", fwd))
        B.append((f"calf_{sd}", v(f"calf_{sd}"), v(f"foot_{sd}"), f"thigh_{sd}", fwd))
        B.append((f"foot_{sd}", v(f"foot_{sd}"), v(f"ball_{sd}"), f"calf_{sd}", up))
        B.append((f"ball_{sd}", v(f"ball_{sd}"), v(f"_toe_{sd}"), f"foot_{sd}", up))
    return B


def build_armature(J, name="SOL_Armature"):
    arm = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(obj)
    activate(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    for nm, h, t, par, rollv in bone_specs(J):
        b = eb.new(nm)
        b.head = h
        b.tail = t
        if (b.tail - b.head).length < 0.004:
            b.tail = b.head + Vector((0, 0, 0.01))
        b.align_roll(Vector(rollv))
        if par:
            b.parent = eb[par]
            b.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    arm.display_type = "OCTAHEDRAL"
    obj.show_in_front = True
    log(f"armature: {len(arm.bones)} bones")
    return obj


def mesh_tris(obj):
    me = obj.data
    me.calc_loop_triangles()
    tris = np.zeros(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tris)
    return mesh_co(me), tris.reshape(-1, 3)


def bone_viz(arm_obj, name="VIZ_bones"):
    """Visible stand-in for the bones (renders do not draw armatures): a thin pyramid per bone + joint balls."""
    bm = bmesh.new()
    for b in arm_obj.data.bones:
        h = arm_obj.matrix_world @ b.head_local
        t = arm_obj.matrix_world @ b.tail_local
        d = (t - h)
        L = d.length
        if L < 1e-5:
            continue
        r = max(0.0025, min(0.012, L * 0.08))
        q = d.to_track_quat("Z", "Y")
        mat = q.to_matrix().to_4x4()
        mat.translation = h
        ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=r, radius2=0.0005, depth=L,
                                    matrix=mat @ __import__("mathutils").Matrix.Translation((0, 0, L / 2)))
        ret = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=r * 1.2,
                                        matrix=__import__("mathutils").Matrix.Translation(h))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    m = bc.material("_bone_viz", (1.0, 0.05, 0.02), emission=(1, 0.05, 0.02), emission_strength=2.0)
    m.diffuse_color = (1, 0.05, 0.02, 1)
    me.materials.append(m)
    return o


def xray_shots(prefix, views, center, radius, res=(600, 900), viz="VIZ_bones"):
    """Body render (dimmed) with the bone stand-ins composited on top (always visible)."""
    import os
    import sol_lib as S
    sc = bpy.context.scene
    vo = bpy.data.objects[viz]
    out = []
    for v in views:
        vo.hide_render = True
        pa = S.shoot(prefix + "_a", [v], center, radius, engine="WB", res=res, color_type="TEXTURE")[0]
        vo.hide_render = False
        hid = [o for o in sc.objects if o is not vo and not o.hide_render]
        for o in hid:
            o.hide_render = True
        sc.render.film_transparent = True
        sc.display.shading.color_type = "MATERIAL"
        pb = S.shoot(prefix + "_b", [v], center, radius, engine="WB", res=res, color_type="MATERIAL")[0]
        sc.render.film_transparent = False
        for o in hid:
            o.hide_render = False
        A = S.img_to_np(bpy.data.images.load(pa))
        Bm = S.img_to_np(bpy.data.images.load(pb))
        a = Bm[..., 3:4]
        C = A.copy()
        C[..., :3] = A[..., :3] * 0.55 * (1 - a) + Bm[..., :3] * a
        name = v if isinstance(v, str) else "v" + "_".join(str(round(q, 2)) for q in v)
        po = os.path.join(S.DIAG, f"{prefix}_{name}.png")
        img = S.np_to_img("_xr", C)
        S.save_png(img, po)
        out.append(po)
    return out


# ================================================================================================ weights
def deform_names(arm_obj):
    return [b.name for b in arm_obj.data.bones if b.name != "root"]


def get_weights(obj, names):
    me = obj.data
    W = np.zeros((len(me.vertices), len(names)), np.float32)
    gi = {obj.vertex_groups[n].index: k for k, n in enumerate(names) if n in obj.vertex_groups}
    for v in me.vertices:
        for g in v.groups:
            k = gi.get(g.group)
            if k is not None:
                W[v.index, k] = g.weight
    return W


def set_weights(obj, W, names, eps=0.004):
    for n in names:
        if n in obj.vertex_groups:
            obj.vertex_groups.remove(obj.vertex_groups[n])
    groups = [obj.vertex_groups.new(name=n) for n in names]
    for k, g in enumerate(groups):
        col = W[:, k]
        idx = np.where(col > eps)[0]
        if not len(idx):
            continue
        # bucket by rounded weight to keep the number of add() calls small
        q = np.round(col[idx], 3)
        for val in np.unique(q):
            sel = idx[q == val].tolist()
            g.add(sel, float(val), "REPLACE")


def limit_normalize(W, k=4, eps=0.01):
    W = W.copy()
    if W.shape[1] > k:
        part = np.argpartition(-W, k, axis=1)[:, k:]
        np.put_along_axis(W, part, 0.0, axis=1)
    W[W < eps] = 0
    s = W.sum(1, keepdims=True)
    return np.where(s > 0, W / np.maximum(s, 1e-8), W)


def vert_adjacency(me):
    ev = np.zeros(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", ev)
    return ev.reshape(-1, 2)


def smooth_weights(W, edges, mask, iters=4, f=0.5):
    """Laplacian smoothing of the weight rows for verts in mask (others fixed)."""
    W = W.copy()
    n = len(W)
    deg = np.zeros(n)
    np.add.at(deg, edges[:, 0], 1)
    np.add.at(deg, edges[:, 1], 1)
    for _ in range(iters):
        acc = np.zeros_like(W)
        np.add.at(acc, edges[:, 0], W[edges[:, 1]])
        np.add.at(acc, edges[:, 1], W[edges[:, 0]])
        avg = acc / np.maximum(deg, 1)[:, None]
        W[mask] = W[mask] * (1 - f) + avg[mask] * f
    return W


def heat_weights(obj, arm_obj):
    """Blender bone-heat automatic weights. Returns the fraction of verts left unweighted."""
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    names = deform_names(arm_obj)
    W = get_weights(obj, names)
    bad = (W.sum(1) < 1e-4).mean()
    log(f"heat weights: {bad * 100:.2f}% verts unweighted")
    return bad


def proxy_weights(obj, arm_obj, voxel=0.006):
    """Fallback: heat weights on a closed voxel-remeshed proxy, transferred to the body (nearest face interp)."""
    proxy = obj.copy()
    proxy.data = obj.data.copy()
    proxy.name = "_proxy"
    bpy.context.scene.collection.objects.link(proxy)
    proxy.modifiers.clear()
    proxy.vertex_groups.clear()
    proxy.parent = None
    # a 4 mm solidify first closes the open TRELLIS sheet: the voxel remesher's inside/outside test on the bare open
    # sheet is fragile (at 6 mm it returned a third of the surface for the re-posed body and every bone failed)
    so = proxy.modifiers.new("Solidify", "SOLIDIFY")
    so.thickness = 0.004
    so.offset = 0.0
    rm = proxy.modifiers.new("Remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = voxel
    bc.apply_modifiers(proxy)
    log(f"proxy: {len(proxy.data.vertices)} verts after the voxel remesh")
    # no decimation: on the re-posed body the decimated proxy made the heat solver fail for every bone
    bad = heat_weights(proxy, arm_obj)
    assert bad < 0.01, f"proxy heat weighting failed ({bad * 100:.1f}% unweighted)"
    for n in deform_names(arm_obj):
        if n not in obj.vertex_groups:
            obj.vertex_groups.new(name=n)
    dt = obj.modifiers.new("DT", "DATA_TRANSFER")
    dt.object = proxy
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    activate(obj)
    bpy.ops.object.modifier_apply(modifier=dt.name)
    bpy.data.objects.remove(proxy, do_unlink=True)
    log("proxy weights transferred")


# ================================================================================================ poses
from mathutils import Matrix  # noqa: E402


def _rot_world(pb, axis, deg, arm_obj):
    """Rotate a pose bone about a world axis through its head (applied on top of its current pose)."""
    bpy.context.view_layer.update()
    M = arm_obj.matrix_world @ pb.matrix
    h = M.translation.copy()
    R = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, Vector(axis)) @ Matrix.Translation(-h)
    pb.matrix = arm_obj.matrix_world.inverted() @ (R @ M)
    bpy.context.view_layer.update()


def _rot_local(pb, axis, deg):
    pb.rotation_mode = "XYZ"
    e = list(pb.rotation_euler)
    e["XYZ".index(axis)] += math.radians(deg)
    pb.rotation_euler = e
    bpy.context.view_layer.update()


def reset_pose(arm_obj):
    for pb in arm_obj.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


PALM = {}     # palm normals (world, rest) per side, set from the joints by set_palms(J) before the grip test


def set_palms(J):
    for sd in ("l", "r"):
        back = Vector(J[f"_hand_e3_{sd}"])
        if back.z < 0:
            back = -back
        PALM[sd] = tuple(-back)


def aim_bone(arm_obj, bone, target_dir):
    """Rotate a pose bone about its head so its (world) direction becomes target_dir (roll-independent)."""
    bpy.context.view_layer.update()
    pb = arm_obj.pose.bones[bone]
    M = arm_obj.matrix_world @ pb.matrix
    cur = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    q = cur.rotation_difference(Vector(target_dir).normalized())
    h = M.translation.copy()
    R = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
    pb.matrix = arm_obj.matrix_world.inverted() @ (R @ M)
    bpy.context.view_layer.update()


def _curl(arm_obj, nm, deg, palm):
    """Curl a finger bone toward the palm by deg (world axis = bone dir x palm normal)."""
    bpy.context.view_layer.update()
    pb = arm_obj.pose.bones[nm]
    M = arm_obj.matrix_world @ pb.matrix
    d = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
    ax = d.cross(palm)
    if ax.length < 1e-6:
        return
    _rot_world(pb, tuple(ax.normalized()), deg, arm_obj)


def pose(arm_obj, name):
    P = arm_obj.pose.bones
    reset_pose(arm_obj)
    if name == "arms_down":
        # target-direction posing (the old +38 deg about Y over-rotated the arms into the crotch)
        aim_bone(arm_obj, "upperarm_l", (0.12, 0.02, -1))
        aim_bone(arm_obj, "upperarm_r", (-0.12, 0.02, -1))
        aim_bone(arm_obj, "lowerarm_l", (0.06, -0.10, -1))
        aim_bone(arm_obj, "lowerarm_r", (-0.06, -0.10, -1))
    elif name == "crouch":
        M = arm_obj.matrix_world @ P["root"].matrix
        P["root"].matrix = arm_obj.matrix_world.inverted() @ (Matrix.Translation((0, 0.03, -0.42)) @ M)
        bpy.context.view_layer.update()
        for sd, sp in (("l", 1), ("r", -1)):
            _rot_world(P[f"thigh_{sd}"], (1, 0, 0), -88, arm_obj)
            _rot_world(P[f"thigh_{sd}"], (0, 0, 1), sp * 12, arm_obj)
            _rot_world(P[f"calf_{sd}"], (1, 0, 0), 112, arm_obj)
            _rot_world(P[f"foot_{sd}"], (1, 0, 0), -22, arm_obj)
        _rot_world(P["spine_01"], (1, 0, 0), 16, arm_obj)
        _rot_world(P["spine_02"], (1, 0, 0), 10, arm_obj)
        _rot_world(P["neck_01"], (1, 0, 0), -12, arm_obj)
        aim_bone(arm_obj, "upperarm_l", (0.25, -0.35, -0.90))
        aim_bone(arm_obj, "upperarm_r", (-0.25, -0.35, -0.90))
    elif name == "run":
        _rot_world(P["thigh_l"], (1, 0, 0), -45, arm_obj)
        _rot_world(P["calf_l"], (1, 0, 0), 55, arm_obj)
        _rot_world(P["thigh_r"], (1, 0, 0), 28, arm_obj)
        _rot_world(P["calf_r"], (1, 0, 0), 70, arm_obj)
        _rot_world(P["foot_r"], (1, 0, 0), 25, arm_obj)
        _rot_world(P["spine_02"], (0, 0, 1), -8, arm_obj)
        aim_bone(arm_obj, "upperarm_l", (0.15, 0.45, -0.88))       # left arm swings back
        aim_bone(arm_obj, "lowerarm_l", (0.10, -0.25, -0.96))
        aim_bone(arm_obj, "upperarm_r", (-0.15, -0.55, -0.82))     # right arm swings forward
        aim_bone(arm_obj, "lowerarm_r", (-0.05, -0.95, 0.30))
    elif name == "head_turn":
        _rot_world(P["neck_01"], (0, 0, 1), 22, arm_obj)
        _rot_world(P["head"], (0, 0, 1), 30, arm_obj)
        _rot_world(P["head"], (1, 0, 0), 8, arm_obj)
    elif name == "grip":
        for sd, s in (("l", 1), ("r", -1)):
            aim_bone(arm_obj, f"lowerarm_{sd}", (s * 0.30, -0.80, -0.52))
            bpy.context.view_layer.update()
            pb = P[f"hand_{sd}"]
            Mh = (arm_obj.matrix_world @ pb.matrix).to_3x3()
            M0 = (arm_obj.matrix_world @ pb.bone.matrix_local).to_3x3()
            palm = (Mh @ M0.inverted() @ Vector(PALM.get(sd, (0, 0, -1)))).normalized()
            for fg in ("index", "middle", "ring", "pinky"):
                for i, a in ((1, 60), (2, 75), (3, 55)):
                    nm = f"{fg}_0{i}_{sd}"
                    if nm in P:
                        _curl(arm_obj, nm, a, palm)
            for i, a in ((1, 15), (2, 30), (3, 30)):
                nm = f"thumb_0{i}_{sd}"
                if nm in P:
                    _curl(arm_obj, nm, a, palm)
    bpy.context.view_layer.update()


# ================================================================================================ weight rules
DRONE_C, DRONE_R = np.array([0.165, -0.058, 1.012]), 0.060
POUCH_BOX = (np.array([-0.185, -0.20, 0.862]), np.array([-0.065, -0.040, 1.055]))


def vertex_tex_colors(obj):
    """Texture colour per vertex from the body atlas (face-material verts get NaN)."""
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor"])
    h, w = px.shape[:2]
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    mi = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("material_index", mi)
    lm = np.repeat(mi, [len(p.vertices) for p in me.polygons])
    ix = np.clip((uv[:, 0] * w).astype(int), 0, w - 1)
    iy = np.clip((uv[:, 1] * h).astype(int), 0, h - 1)
    lc = px[iy, ix, :3]
    ok = lm == 0
    vc = np.zeros((len(me.vertices), 3))
    cnt = np.zeros(len(me.vertices))
    np.add.at(vc, lv[ok], lc[ok])
    np.add.at(cnt, lv[ok], 1)
    vc = vc / np.maximum(cnt, 1)[:, None]
    vc[cnt == 0] = np.nan
    return vc


def seg_param(P, a, b):
    a = np.asarray(a)
    b = np.asarray(b)
    d = b - a
    t = ((P - a) @ d) / (d @ d)
    q = a + np.clip(t, 0, 1)[:, None] * d
    return t, np.linalg.norm(P - q, axis=1)


def apply_weight_rules(obj, arm_obj, J, coat_max=0.62):
    names = deform_names(arm_obj)
    ix = {n: k for k, n in enumerate(names)}
    W = get_weights(obj, names)
    co = mesh_co(obj.data)
    x, y, z = co.T
    vc = vertex_tex_colors(obj)
    lum = np.nanmean(vc, 1)
    hairc = np.nan_to_num((lum < 0.30) & (vc[:, 0] >= vc[:, 2] - 0.005), nan=0).astype(bool)
    locked = np.zeros(len(co), bool)

    def setrow(mask, weights, blend=None):
        R = np.zeros((mask.sum(), len(names)), np.float32)
        for n, w in weights.items():
            R[:, ix[n]] = w if np.ndim(w) == 0 else w[mask]
        if blend is None:
            W[mask] = R
        else:
            b = blend[mask][:, None]
            W[mask] = W[mask] * (1 - b) + R * b

    # ---- head + scalp hair (rigid), neck blend below the jaw
    hc = np.array([0.0, 0.015, 1.565])
    inhead = (((x - hc[0]) / 0.115) ** 2 + ((y - hc[1]) / 0.125) ** 2 + ((z - hc[2]) / 0.14) ** 2) < 1.0
    headm = inhead & (z > 1.445)
    hb = smoothstep(1.445, 1.475, z)
    pony = hairc & (z < 1.50) & (z > 1.10) & (x < 0.0) & (x > -0.20) & (y > -0.16) & (y < 0.13) & ~(inhead & (z > 1.47))
    headm &= ~pony
    setrow(headm, {"head": 1.0}, blend=hb)
    locked |= headm & (z > 1.475)
    # ---- ponytail: head -> neck_01 -> spine_03 (+ right clavicle where it lies on the shoulder)
    wz_head = smoothstep(1.40, 1.47, z)
    wz_neck = smoothstep(1.30, 1.40, z) * (1 - wz_head)
    wz_sp = 1 - wz_head - wz_neck
    clav = smoothstep(-0.075, -0.105, x) * smoothstep(1.32, 1.36, z) * (1 - smoothstep(1.43, 1.47, z)) * 0.35
    setrow(pony, {"head": wz_head * (1 - clav), "neck_01": wz_neck * (1 - clav), "spine_03": wz_sp * (1 - clav),
                  "clavicle_r": clav})
    locked |= pony
    # ---- bracer: rigid on the right forearm
    t, dist = seg_param(co, J["lowerarm_r"], J["hand_r"])
    br = (t > 0.10) & (t < 0.93) & (dist < 0.08) & (x < -0.22)
    setrow(br, {"lowerarm_r": 1.0})
    locked |= br
    # ---- pouch (right hip): rigid to the pelvis (the heal drone is a separate object now: SOL_Drone)
    lo, hi = POUCH_BOX
    pu = np.all((co > lo) & (co < hi), axis=1)
    dr = np.zeros(len(co), bool)
    setrow(pu, {"pelvis": 1.0})
    locked |= pu
    # ---- coat tail: pelvis / thigh blend (no tearing at the split, follows the legs partially)
    sand = np.nan_to_num((np.abs(vc[:, 0] - 0.62) < 0.12) & (vc[:, 0] - vc[:, 2] > 0.08) & (lum > 0.35), nan=0)
    coat = (z < 0.975) & (z > 0.58) & (np.abs(x) < 0.27) & ~sand.astype(bool) & ~locked
    # exclude the legs themselves (pants inside the coat): distance to the thigh axes
    for sd in ("l", "r"):
        tt, dd = seg_param(co, J[f"thigh_{sd}"], J[f"calf_{sd}"])
        coat &= ~((dd < 0.072) & (tt > -0.05) & (tt < 1.0))
    wt = np.clip((0.955 - z) / 0.30, 0, 1) ** 0.9 * coat_max
    cx = 0.5 * (J["thigh_l"][0] + J["thigh_r"][0])
    sl = smoothstep(cx - 0.035, cx + 0.035, x)
    rule = {"pelvis": 1 - wt, "thigh_l": wt * sl, "thigh_r": wt * (1 - sl)}
    blend = smoothstep(0.975, 0.90, z)
    setrow(coat, rule, blend=blend)
    # ---- smooth everything that is not rigid, then limit
    edges = vert_adjacency(obj.data)
    W = smooth_weights(W, edges, ~locked, iters=3, f=0.5)
    W = smooth_weights(W, edges, coat, iters=4, f=0.5)
    W = leak_rules(W, co, names, J)
    W = limit_normalize(W, 4)
    set_weights(obj, W, names)
    log(f"weight rules: head {headm.sum()}, ponytail {pony.sum()}, bracer {br.sum()}, "
        f"pouch {pu.sum()}, coat tail {coat.sum()}; max influences 4")
    return W


def _move(W, src_cols, dst_col, keep):
    """Scale the src columns by keep (0..1 per vert) and give the removed weight to dst_col."""
    for c in src_cols:
        rem = W[:, c] * (1 - keep)
        W[:, c] -= rem
        W[:, dst_col] += rem


def leak_rules(W, co, names, J):
    """Review round 2 weight-leak fixes:
    - no leg weight above the belt: thigh/calf/foot/ball fade out between Z 0.96 and 1.00 (-> pelvis);
    - no cross-side weights: a vert more than 6 cm to one side of the midline loses the other side's bones
      (fade 3..6 cm; -> pelvis below the waist, spine_03 above);
    - finger weights only in front of the wrist (fade 0..3 cm along the hand axis; -> hand);
    - the TRELLIS fingers are fused in two mittens per hand (index+middle, ring+pinky): each pair's weights are
      tied (averaged) per segment, so the fused mass follows the mean of its two bones instead of shearing."""
    W = W.copy()
    ix = {n: k for k, n in enumerate(names)}
    x, y, z = co.T
    legs = [ix[n] for n in names if n.startswith(("thigh", "calf", "foot", "ball"))]
    _move(W, legs, ix["pelvis"], 1 - smoothstep(0.96, 1.00, z))
    for s, own, other in ((1, "_l", "_r"), (-1, "_r", "_l")):
        cols = [ix[n] for n in names if n.endswith(other)]
        keep = 1 - smoothstep(0.03, 0.06, s * x)
        upper = z > 1.0
        for c in cols:
            rem = W[:, c] * (1 - keep)
            W[:, c] -= rem
            W[upper, ix["spine_03"]] += rem[upper]
            W[~upper, ix["pelvis"]] += rem[~upper]
    for sd in ("l", "r"):
        wr = np.asarray(J[f"hand_{sd}"], float)
        e1 = np.asarray(J[f"_tip_{sd}"], float) - wr
        e1 /= np.linalg.norm(e1)
        t = (co - wr) @ e1
        fing = [ix[n] for n in names if n.startswith(FINGERS) and n.endswith("_" + sd)]
        _move(W, fing, ix[f"hand_{sd}"], smoothstep(0.0, 0.03, t))
        for a, b in (("index", "middle"), ("ring", "pinky")):
            for k in (1, 2, 3):
                ca, cb = ix.get(f"{a}_0{k}_{sd}"), ix.get(f"{b}_0{k}_{sd}")
                if ca is None or cb is None:
                    continue
                m = 0.5 * (W[:, ca] + W[:, cb])
                W[:, ca] = m
                W[:, cb] = m
    return W


# ================================================================================================ stage D
def transfer_weights(dst, src, arm_obj):
    """Skin weights for extra meshes (straps, emblem) copied from the body surface (nearest face interpolated)."""
    names = deform_names(arm_obj)
    for n in names:
        if n not in dst.vertex_groups:
            dst.vertex_groups.new(name=n)
    dt = dst.modifiers.new("DT", "DATA_TRANSFER")
    dt.object = src
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    activate(dst)
    bpy.ops.object.modifier_apply(modifier=dt.name)
    W = limit_normalize(get_weights(dst, names), 4)
    set_weights(dst, W, names)


def bind(obj, arm_obj):
    mw = obj.matrix_world.copy()
    obj.parent = arm_obj
    obj.matrix_parent_inverse = arm_obj.matrix_world.inverted()
    obj.matrix_world = mw
    m = obj.modifiers.get("Armature") or obj.modifiers.new("Armature", "ARMATURE")
    m.object = arm_obj
    m.use_vertex_groups = True


def parent_to_bone(obj, arm_obj, bone):
    mw = obj.matrix_world.copy()
    obj.parent = arm_obj
    obj.parent_type = "BONE"
    obj.parent_bone = bone
    bpy.context.view_layer.update()
    pb = arm_obj.pose.bones[bone]
    # bone-parent space: the tail of the bone in armature space
    M = arm_obj.matrix_world @ pb.matrix @ Matrix.Translation((0, pb.length, 0))
    obj.matrix_parent_inverse = M.inverted()
    obj.matrix_world = mw
    bpy.context.view_layer.update()


def stage_d():
    import sol_joints as SJ
    b = body()
    co, tris = mesh_tris(b)
    J = kestrel_conventions(SJ.find_joints(co, tris, log=log))
    log(f"spine (Kestrel directions): pelvis {np.round(J['pelvis'], 3)} s1 {np.round(J['spine_01'], 3)} "
        f"s2 {np.round(J['spine_02'], 3)} s3 {np.round(J['spine_03'], 3)} neck {np.round(J['neck_01'], 3)}; "
        f"clavicle_l {np.round(J['clavicle_l'], 3)}")
    arm = build_armature(J)
    bad = heat_weights(b, arm)
    if bad > 0.002:
        log("heat weighting failed on the TRELLIS shell -> voxel-proxy fallback")
        for g in list(b.vertex_groups):
            b.vertex_groups.remove(g)
        b.parent = None
        for m in list(b.modifiers):
            b.modifiers.remove(m)
        proxy_weights(b, arm, voxel=0.006)
    apply_weight_rules(b, arm, J)
    bind(b, arm)
    gear = bpy.data.objects.get("SOL_Gear")
    if gear:
        transfer_weights(gear, b, arm)
        bind(gear, arm)
    bloom = bpy.data.objects.get("SOL_Bloom")
    if bloom:
        parent_to_bone(bloom, arm, "spine_03")
    return arm, J
