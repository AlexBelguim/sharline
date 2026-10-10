"""Stage D for build_kestrel.py: UE5-mannequin-named armature + skinning for KESTREL.

Joints come from the mesh: limb centres are found by ray-casting cross-sections from inside each limb (the TRELLIS
shell is a thin double layer, so rays from the inside land on it from any direction), the hands are analysed in
their own PCA frame (fingers = lateral clusters of the distal vertices, thumb = the vertices beyond the palm edge).

Skinning: Blender heat weights on a closed voxel-remeshed proxy (the raw TRELLIS shell is non-manifold, so heat
weighting on it fails), transferred to the real mesh with a DataTransfer modifier; geometric (distance-to-bone)
weights for the hands and fingers (the voxel proxy fuses the fingers); rigid overrides for the hair/head, jet pack,
chest plate, collar, pouches and holster; finally normalised and limited to 4 influences.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import blender_common as bc
import kes_lib as K
import kes_tex
from kes_lib import log

ARM_NAME = "KES_Armature"
FINGERS = ("index", "middle", "ring", "pinky")


# =============================================================================================== cross-sections
class Slicer:
    def __init__(self, obj):
        dg = bpy.context.evaluated_depsgraph_get()
        self.bvh = BVHTree.FromObject(obj, dg)

    def centre(self, c, d, rmax=0.12, n=36, iters=3, keep=None):
        """Centre of the cross-section through point c, perpendicular to direction d (rays from inside)."""
        d = Vector(d).normalized()
        a = d.orthogonal().normalized()
        b = d.cross(a).normalized()
        c = Vector(c)
        rad, pts = 0.0, []
        for _ in range(iters):
            pts = []
            for i in range(n):
                ang = 2 * math.pi * i / n
                r = a * math.cos(ang) + b * math.sin(ang)
                h = self.bvh.ray_cast(c, r, rmax)
                if h[0] is not None and (keep is None or keep(h[0])):
                    pts.append(h[0])
            if len(pts) < n // 3:
                break
            P = np.array([p[:] for p in pts])
            pa, pb = (P - np.array(c[:])) @ np.array(a[:]), (P - np.array(c[:])) @ np.array(b[:])
            # bbox middle in the slice plane: robust to one-sided bulges (pockets, straps)
            c = c + a * float((pa.min() + pa.max()) / 2) + b * float((pb.min() + pb.max()) / 2)
            rad = float(np.median(np.hypot(pa, pb)))
        return c, rad


# =============================================================================================== joints
def hand_frame(co, idx, side):
    p = co[idx]
    mu = p.mean(0)
    _, _, vt = np.linalg.svd(p - mu, full_matrices=False)
    a = vt[0] * np.sign(vt[0][0] * side)
    q = p - mu
    t = q @ a
    lat_ax = vt[1]
    lat = q @ lat_ax
    # thumb side = the lateral side with the larger extent among the proximal half (the thumb sticks out there)
    prox = t < np.percentile(t, 55)
    if abs(lat[prox].min()) > lat[prox].max():
        lat_ax = -lat_ax
    n = np.cross(a, lat_ax)
    return mu, a, lat_ax, n


def analyse_hand(co, idx, side):
    """Return joints for the hand: wrist, hand end (middle MCP), finger chains (MCP, PIP, DIP, tip) and the thumb
    chain (CMC, MCP, IP, tip), plus the frame."""
    mu, a, L, n = hand_frame(co, idx, side)
    p = co[idx] - mu
    t, lat, dep = p @ a, p @ L, p @ n
    tmin, tmax = t.min(), t.max()
    # ---- thumb: points beyond the palm edge on the thumb side in the proximal 70 %
    palm_band = (t > tmin + 0.25 * (tmax - tmin)) & (t < tmin + 0.45 * (tmax - tmin))
    palm_edge = np.percentile(lat[palm_band], 80)
    th = (lat > palm_edge + 0.004) & (t < tmin + 0.75 * (tmax - tmin))
    # ---- fingers: lateral clusters of the distal points
    fingers = []
    t_split = None
    for t0 in np.linspace(tmin + 0.55 * (tmax - tmin), tmax - 0.012, 30):
        band = (np.abs(t - t0) < 0.0035) & ~th
        xs = np.sort(lat[band])
        if len(xs) < 8:
            continue
        gaps = np.where(np.diff(xs) > 0.0045)[0]
        if len(gaps) >= 3:
            t_split = t0
            break
    if t_split is None:
        t_split = tmin + 0.70 * (tmax - tmin)
    dist = (t > t_split) & ~th
    # cluster lateral positions of the distal points into 4 groups (1D k-means, init by quantiles)
    xs = lat[dist]
    cs = np.percentile(xs, [12, 38, 62, 88])
    for _ in range(20):
        lab = np.argmin(np.abs(xs[:, None] - cs[None, :]), axis=1)
        cs = np.array([xs[lab == k].mean() if (lab == k).any() else cs[k] for k in range(4)])
    order = np.argsort(-cs)          # thumb side first: index, middle, ring, pinky
    cs = cs[order]
    bounds = [np.inf] + [(cs[k] + cs[k + 1]) / 2 for k in range(3)] + [-np.inf]
    out = {}
    w_lat = lat
    for k, name in enumerate(FINGERS):
        cell = (w_lat <= bounds[k]) & (w_lat > bounds[k + 1]) & (t > t_split - 0.025) & ~th
        tc = t[cell]
        tip_t = np.percentile(tc, 99) if cell.any() else tmax
        tip_sel = cell & (t > tip_t - 0.006)
        tip = np.array([tip_t, lat[tip_sel].mean(), dep[tip_sel].mean()])
        mcp_t = t_split - 0.016
        near = cell & (np.abs(t - (t_split + 0.004)) < 0.006)
        mcp = np.array([mcp_t, lat[near].mean() if near.any() else cs[k], dep[near].mean() if near.any() else 0.0])
        # bend: sample the finger centre at 45 % / 75 %
        L_f = tip_t - mcp_t
        chain = [mcp]
        for f in (0.45, 0.75):
            tt = mcp_t + f * L_f
            sel = cell & (np.abs(t - tt) < 0.004)
            chain.append(np.array([tt, lat[sel].mean(), dep[sel].mean()]) if sel.sum() > 2 else mcp + (tip - mcp) * f)
        chain.append(tip)
        out[name] = chain
    # thumb chain
    tp = p[th]
    tmu = tp.mean(0)
    _, _, tv = np.linalg.svd(tp - tmu, full_matrices=False)
    tax = tv[0]
    if (tp - tmu) @ tax @ np.ones(len(tp)) < 0 or tax @ L < 0:
        tax = -tax if tax @ L < 0 else tax
    s = (tp - tmu) @ tax
    tip3 = tmu + tax * np.percentile(s, 99)
    root3 = tmu + tax * np.percentile(s, 1)
    tipl = np.array([tip3 @ a, tip3 @ L, tip3 @ n])
    # CMC: inside the palm, between the wrist and the thumb root
    cmc = np.array([tmin + 0.14 * (tmax - tmin), palm_edge * 0.45, float(np.median(dep[palm_band]))])
    rootl = np.array([root3 @ a, root3 @ L, root3 @ n])
    mcp_th = rootl + (tipl - rootl) * 0.18
    ip = rootl + (tipl - rootl) * 0.62
    out["thumb"] = [cmc, mcp_th, ip, tipl]
    # wrist and hand end
    wrist_sel = t < tmin + 0.03
    wrist = np.array([tmin + 0.012, lat[wrist_sel].mean(), dep[wrist_sel].mean()])
    to_world = lambda v: Vector((mu + a * v[0] + L * v[1] + n * v[2]).tolist())
    res = {k: [to_world(v) for v in ch] for k, ch in out.items()}
    res["wrist"] = to_world(wrist)
    res["hand_end"] = (res["middle"][0] + res["index"][0]) / 2
    res["frame"] = (Vector(a.tolist()), Vector(L.tolist()), Vector(n.tolist()))
    res["t_split"] = t_split
    return res


def compute_joints(obj):
    co = K.mesh_co(obj.data)
    sl = Slicer(obj)
    isl, _ = kes_tex.hand_islands(obj)
    J = {}
    # ---------------------------------------------------------------- legs
    for s, sfx in ((1, "l"), (-1, "r")):
        thigh_mid, _ = sl.centre((s * 0.10, 0.0, 0.74), (0, 0, 1))
        thigh_lo, _ = sl.centre((s * 0.12, 0.01, 0.64), (0, 0, 1))
        knee, _ = sl.centre((s * 0.145, 0.02, 0.495), (0, 0, 1))
        calf, _ = sl.centre((s * 0.17, 0.06, 0.30), (0, 0, 1))
        ankle, _ = sl.centre((s * 0.205, 0.075, 0.115), (0, 0, 1), rmax=0.09)
        # hip: extend the thigh line up to Z 0.865
        d = (thigh_mid - knee).normalized()
        hip = thigh_mid + d * ((0.865 - thigh_mid.z) / d.z)
        hip.y = 0.0
        ankle.z = 0.090
        # foot: toe tip and ball from the foot outline (lowest band)
        foot = co[(s * co[:, 0] > 0.10) & (co[:, 2] < 0.06)]
        toe_y = np.percentile(foot[:, 1], 1)
        heel_y = np.percentile(foot[:, 1], 99)
        ball_y = heel_y + 0.72 * (toe_y - heel_y)
        band = foot[np.abs(foot[:, 1] - ball_y) < 0.012]
        ball = Vector(((band[:, 0].min() + band[:, 0].max()) / 2, ball_y, 0.032))
        tband = foot[foot[:, 1] < toe_y + 0.015]
        toe = Vector(((tband[:, 0].min() + tband[:, 0].max()) / 2, toe_y + 0.006, 0.030))
        J[f"thigh_{sfx}"] = (hip, knee)
        J[f"calf_{sfx}"] = (knee, ankle)
        J[f"foot_{sfx}"] = (ankle, ball)
        J[f"ball_{sfx}"] = (ball, toe)
        log(f"leg {sfx}: hip {tuple(round(v, 3) for v in hip)} knee {tuple(round(v, 3) for v in knee)} "
            f"ankle {tuple(round(v, 3) for v in ankle)} ball {tuple(round(v, 3) for v in ball)}")
    # ---------------------------------------------------------------- spine (centre line, slightly behind middle)
    torso_keep = lambda p: p.y < 0.115   # ignore the jet pack behind the back
    zs = [0.93, 1.00, 1.10, 1.22, 1.385, 1.47]
    sp = []
    for z in zs:
        c, _ = sl.centre((0.0, -0.005, z), (0, 0, 1), rmax=0.2, keep=torso_keep)
        sp.append(Vector((0.0, min(max(c.y + 0.012, -0.01), 0.02), z)))
    head_top = Vector((0.0, 0.02, 1.70))
    names = ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01"]
    for i, nm in enumerate(names):
        J[nm] = (sp[i], sp[i + 1])
    J["head"] = (sp[-1], head_top)
    # ---------------------------------------------------------------- arms + hands
    for s, sfx, lab in ((1, "l", 1), (-1, "r", 2)):
        H = analyse_hand(co, isl[lab], s)
        wrist = H["wrist"]
        sh_guess = Vector((s * 0.172, 0.0, 1.355))
        d = (wrist - sh_guess).normalized()
        # centre line samples along the arm
        cl = []
        for f in np.linspace(0.12, 0.92, 9):
            c, r = sl.centre(sh_guess + (wrist - sh_guess) * f, d, rmax=0.09)
            cl.append(c)
        # elbow at 54 % (upper arm 0.29 : forearm 0.25 in the brief), nudged to the centre line
        fe = 0.54
        el_line = sh_guess + (wrist - sh_guess) * fe
        el, _ = sl.centre(el_line, d, rmax=0.09)
        shoulder = Vector((s * 0.170, cl[0].y * 0.5, 1.352))
        clav = Vector((s * 0.022, -0.010, 1.395))
        J[f"clavicle_{sfx}"] = (clav, shoulder)
        J[f"upperarm_{sfx}"] = (shoulder, el)
        J[f"lowerarm_{sfx}"] = (el, wrist)
        J[f"hand_{sfx}"] = (wrist, H["hand_end"])
        for fn in FINGERS + ("thumb",):
            ch = H[fn]
            for k in range(3):
                J[f"{fn}_0{k + 1}_{sfx}"] = (ch[k], ch[k + 1])
        J[f"_handinfo_{sfx}"] = H
        log(f"arm {sfx}: shoulder {tuple(round(v, 3) for v in shoulder)} elbow {tuple(round(v, 3) for v in el)} "
            f"wrist {tuple(round(v, 3) for v in wrist)} fingers split at t={H['t_split']:.3f}")
    symmetrise(J, ("thigh", "calf", "foot", "ball", "clavicle", "upperarm"))
    return J


def symmetrise(J, prefixes):
    """Average each bilateral joint with the mirror of its partner (the mesh is near-symmetric; holster / cargo
    pocket bias the leg slices). Only the body chains, not the hands (they follow their own meshes)."""
    def mir(v):
        return Vector((-v.x, v.y, v.z))
    for pre in prefixes:
        l, r = J[f"{pre}_l"], J[f"{pre}_r"]
        hl = (l[0] + mir(r[0])) / 2
        tl = (l[1] + mir(r[1])) / 2
        J[f"{pre}_l"] = (hl, tl)
        J[f"{pre}_r"] = (mir(hl), mir(tl))
    # keep chains connected after averaging
    for s in ("l", "r"):
        J[f"calf_{s}"] = (J[f"thigh_{s}"][1], J[f"calf_{s}"][1])
        J[f"foot_{s}"] = (J[f"calf_{s}"][1], J[f"foot_{s}"][1])
        J[f"ball_{s}"] = (J[f"foot_{s}"][1], J[f"ball_{s}"][1])
        J[f"upperarm_{s}"] = (J[f"clavicle_{s}"][1], J[f"upperarm_{s}"][1])
        J[f"lowerarm_{s}"] = (J[f"upperarm_{s}"][1], J[f"lowerarm_{s}"][1])


PARENT = {
    "pelvis": "root", "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02", "neck_01": "spine_03",
    "head": "neck_01",
}
for _s in ("l", "r"):
    PARENT.update({f"clavicle_{_s}": "spine_03", f"upperarm_{_s}": f"clavicle_{_s}",
                   f"lowerarm_{_s}": f"upperarm_{_s}", f"hand_{_s}": f"lowerarm_{_s}",
                   f"thigh_{_s}": "pelvis", f"calf_{_s}": f"thigh_{_s}", f"foot_{_s}": f"calf_{_s}",
                   f"ball_{_s}": f"foot_{_s}"})
    for _f in FINGERS + ("thumb",):
        PARENT[f"{_f}_01_{_s}"] = f"hand_{_s}"
        PARENT[f"{_f}_02_{_s}"] = f"{_f}_01_{_s}"
        PARENT[f"{_f}_03_{_s}"] = f"{_f}_02_{_s}"
CONNECT = {"spine_01", "spine_02", "spine_03", "neck_01", "head", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r",
           "calf_l", "calf_r", "foot_l", "foot_r", "ball_l", "ball_r"}
for _s in ("l", "r"):
    for _f in FINGERS + ("thumb",):
        CONNECT |= {f"{_f}_02_{_s}", f"{_f}_03_{_s}"}


def bone_order():
    order = ["root"]
    while len(order) < len(PARENT) + 1:
        for b, p in PARENT.items():
            if b not in order and p in order:
                order.append(b)
    return order


def build_armature(J):
    arm = bpy.data.armatures.new(ARM_NAME)
    arm.display_type = "OCTAHEDRAL"
    ob = bpy.data.objects.new(ARM_NAME, arm)
    bpy.context.scene.collection.objects.link(ob)
    K.activate(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm.edit_bones
    root = eb.new("root")
    root.head = (0, 0, 0)
    root.tail = (0, 0, 0.12)
    for nm in bone_order()[1:]:
        h, t = J[nm]
        b = eb.new(nm)
        b.head = h
        b.tail = t
        if (b.tail - b.head).length < 0.004:
            b.tail = b.head + Vector((0, 0, 0.004))
        b.parent = eb[PARENT[nm]]
        b.use_connect = nm in CONNECT and (eb[PARENT[nm]].tail - b.head).length < 1e-4
        b.use_deform = nm != "root"
    root.use_deform = False
    # rolls: Z axis forward/up-ish, mirrored consistently between sides
    for b in eb:
        if b.name == "root":
            continue
        if b.name.startswith(("thigh", "calf", "foot", "ball", "pelvis", "spine", "neck", "head")):
            b.align_roll(Vector((0, -1, 0)) if not b.name.startswith(("foot", "ball")) else Vector((0, 0, 1)))
        else:
            b.align_roll(Vector((0, 0, 1)) if not b.name.startswith(FINGERS + ("thumb",)) else Vector((0, 0, 1)))
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob
