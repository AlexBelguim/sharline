"""Stage D (part 2) for build_kestrel.py: skin weights for KESTREL.

  0. the hair shell is split from the collar along the nape (TRELLIS fused the bob into the collar; with one surface
     a head turn or pitch stretches the hair into streaks): the edges between hair faces and collar faces are ripped;
  1. heat weights (Blender ARMATURE_AUTO) on a closed voxel remesh of the body - the raw TRELLIS shell is
     non-manifold and double-layered, so heat weighting fails on it - transferred back with a DataTransfer
     modifier (nearest face, interpolated), then lightly smoothed;
  2. hands/fingers: geometric weights (soft-min of the distance to each bone segment), ramped in over the wrist
     (the voxel proxy fuses the fingers);
  3. arm limits (review round 2): the heat weights let the upper arm / clavicle reach far into the chest, back and
     chest plate, which tore the torso when the arms are raised. The arm-vs-torso split is sharpened and the
     upper arm / clavicle influence is capped by the distance to their bone segments;
  4. rigid parts: head + all hair (incl. the long bob, the teal tips and the whole nape above the collar rim) ->
     head; collar -> spine_03 rising to neck_01 at the rim; neck skin -> neck_01/head; jet pack -> spine_03; chest
     plate (its whole outline, both layers) -> spine_03 (bottom row up to 30 % spine_02); elbow pads -> lowerarm;
     belt pouches -> pelvis; holster -> thigh_r; then a soft ring around the rigid chest plate;
  5. normalise, max 4 influences, drop weights < 1 %.
"""
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector

import blender_common as bc
import kes_lib as K
import kes_rig as R
from kes_lib import log


def deform_bones(arm):
    return [b.name for b in arm.data.bones if b.use_deform]


def vgroup_matrix(obj, names):
    idx = {obj.vertex_groups[n].index: k for k, n in enumerate(names) if n in obj.vertex_groups}
    W = np.zeros((len(obj.data.vertices), len(names)))
    for v in obj.data.vertices:
        for g in v.groups:
            k = idx.get(g.group)
            if k is not None:
                W[v.index, k] = g.weight
    return W


def heat_proxy_weights(body, arm, voxel=0.0065):
    """Heat weights on a closed voxel remesh of the body, transferred back to the body. Returns (nv, nb) array."""
    names = deform_bones(arm)
    proxy = body.copy()
    proxy.data = body.data.copy()
    proxy.name = "_heat_proxy"
    bpy.context.scene.collection.objects.link(proxy)
    proxy.modifiers.clear()
    for vg in list(proxy.vertex_groups):
        proxy.vertex_groups.remove(vg)
    m = proxy.modifiers.new("Remesh", "REMESH")
    m.mode = "VOXEL"
    m.voxel_size = voxel
    m.adaptivity = 0.0
    bc.apply_modifiers(proxy)
    n0 = len(proxy.data.vertices)
    remove_cavities(proxy)
    log(f"heat proxy: {n0} -> {len(proxy.data.vertices)} verts after removing inner cavity surfaces "
        f"(voxel {voxel * 1000:.1f} mm)")
    # Blender's heat solver fails on small-scale meshes (mm-sized faces): solve at 10x scale
    SC = 10.0
    proxy.scale = (SC, SC, SC)
    arm.scale = (SC, SC, SC)
    bpy.context.view_layer.update()
    K.activate(proxy)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    proxy.parent = None
    proxy.scale = (1, 1, 1)
    arm.scale = (1, 1, 1)
    proxy.modifiers.clear()
    bpy.context.view_layer.update()
    pw = vgroup_matrix(proxy, names)
    log(f"heat weights: {(pw.sum(1) < 1e-6).sum()} / {len(pw)} proxy verts without weights")
    for nm in names:
        if nm not in body.vertex_groups:
            body.vertex_groups.new(name=nm)
    dt = body.modifiers.new("_wt", "DATA_TRANSFER")
    dt.object = proxy
    dt.use_vert_data = True
    dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"
    dt.layers_vgroup_select_src = "ALL"
    dt.layers_vgroup_select_dst = "NAME"
    K.activate(body)
    with bpy.context.temp_override(object=body, active_object=body):
        bpy.ops.object.datalayout_transfer(modifier=dt.name)
        bpy.ops.object.modifier_apply(modifier=dt.name)
    W = vgroup_matrix(body, names)
    bpy.data.objects.remove(proxy, do_unlink=True)
    return W, names


def remove_cavities(proxy, samples=160):
    """The TRELLIS body is a hollow double-layer shell, so its voxel remesh is a thick hollow skin: an outer
    surface plus closed inner cavity surfaces around the bones. Those cavity walls hide the bones from the outer
    surface and make heat weighting fail. Keep only the islands whose vertices can see out (a ray along the outward
    normal escapes for a good share of them); drop cavity walls and tiny specks."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    me = proxy.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    bm.verts.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    rng = np.random.default_rng(0)
    kill = []
    kept = 0
    for isl in K.islands(bm):
        if len(isl) < 60:
            kill += isl
            continue
        pick = rng.choice(isl, size=min(samples, len(isl)), replace=False)
        esc = 0
        for i in pick:
            v = bm.verts[int(i)]
            h = bvh.ray_cast(v.co + v.normal * 0.0008, v.normal, 3.0)
            esc += h[0] is None
        if esc / len(pick) < 0.12:
            kill += isl
        else:
            kept += 1
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in kill], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    log(f"proxy: kept {kept} outer islands, removed {len(kill)} cavity/speck verts")


def write_weights(obj, W, names, limit=4, floor=0.01):
    W = W.copy()
    if W.shape[1] > limit:
        thr = -np.sort(-W, axis=1)[:, limit - 1:limit]
        W[W < thr] = 0.0
    W[W < floor] = 0.0
    s = W.sum(1, keepdims=True)
    W = np.where(s > 0, W / np.maximum(s, 1e-9), 0.0)
    for vg in list(obj.vertex_groups):
        obj.vertex_groups.remove(vg)
    for k, nm in enumerate(names):
        vg = obj.vertex_groups.new(name=nm)
        nz = np.where(W[:, k] > 0)[0]
        if not len(nz):
            continue
        vals = np.round(W[nz, k], 4)
        for val in np.unique(vals):
            vg.add(nz[vals == val].tolist(), float(val), "REPLACE")
    return W


def seg_dist(P, a, b):
    a, b = np.array(a[:]), np.array(b[:])
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)


def hand_weights(co, W, names, arm, J, sigma=0.0028):
    """Geometric weights for hands/fingers (nearest bone segment, soft-min blend), ramped in over the wrist."""
    bones = arm.data.bones
    for s in ("l", "r"):
        H = J[f"_handinfo_{s}"]
        a = H["frame"][0]
        wrist = np.array(H["wrist"][:])
        ax = np.array(a[:])
        t = (co - wrist) @ ax
        centre = wrist + ax * 0.06
        near = (np.linalg.norm(co - centre, axis=1) < 0.20) & (t > -0.06)
        cand = [f"lowerarm_{s}", f"hand_{s}"] + [f"{f}_0{k}_{s}" for f in R.FINGERS + ("thumb",) for k in (1, 2, 3)]
        P = co[near]
        D = np.stack([seg_dist(P, bones[c].head_local, bones[c].tail_local) for c in cand], axis=1)
        G = np.exp(-(D - D.min(1, keepdims=True)) / sigma)
        G[G < 0.02] = 0.0
        G /= G.sum(1, keepdims=True)
        ramp = K.smoothstep(-0.045, -0.012, t[near])[:, None]
        Wn = W[near] * (1 - ramp)
        for k, c in enumerate(cand):
            Wn[:, names.index(c)] += ramp[:, 0] * G[:, k]
        W[near] = Wn
    return W


def set_rigid(W, names, mask, weights):
    W[mask] = 0.0
    for b, w in weights.items():
        W[mask, names.index(b)] = w
    return W


CHEST_OUTLINE = (   # (z, x_min, x_max) of the bone chest plate, measured from its texels (it sits 1 cm to her left)
    (1.155, -0.090, 0.108), (1.170, -0.103, 0.120), (1.190, -0.118, 0.135), (1.210, -0.127, 0.144),
    (1.240, -0.124, 0.145), (1.270, -0.116, 0.135), (1.300, -0.109, 0.128), (1.320, -0.097, 0.117),
    (1.342, -0.085, 0.103))
ELBOW = {}          # elbow joint positions, filled by build_rig from the joints


def chest_plate_mask(co, pad=0.006):
    """All vertices (front plate AND the layers behind it) inside the chest plate's outline, in front of the
    chest centre line."""
    x, y, z = co.T
    zs = np.array([r[0] for r in CHEST_OUTLINE])
    lo = np.interp(z, zs, [r[1] for r in CHEST_OUTLINE]) - pad
    hi = np.interp(z, zs, [r[2] for r in CHEST_OUTLINE]) + pad
    return (z > zs[0] - pad) & (z < zs[-1] + pad) & (x > lo) & (x < hi) & (y < -0.035)


def nape_rim(x, y):
    """Collar rim height around the neck (behind / beside it), and the angle from straight back (deg)."""
    ang = np.degrees(np.arctan2(x - 0.005, y - 0.008))
    a = np.clip(np.abs(ang) / 90.0, 0.0, 1.35)
    return 1.455 - 0.012 * a ** 2, ang


def nape_zone(x, y, z):
    """Behind / beside the neck, between the neck skin and the outside of the collar / bob (the shoulders stay
    out): radius 6.2 cm .. 14.5 cm at the back, narrowing to 11.5 cm at the sides."""
    rad = np.hypot(x - 0.005, y - 0.008)
    _, ang = nape_rim(x, y)
    r_max = 0.145 - 0.030 * K.smoothstep(40.0, 90.0, np.abs(ang)) - 0.010 * K.smoothstep(90.0, 120.0, np.abs(ang))
    return (np.abs(ang) < 120.0) & (rad > 0.062) & (rad < r_max) & (z > 1.33) & (z < 1.56)


def grow(me, mask, rings=1):
    e = K.edge_array(me)
    m = mask.copy()
    for _ in range(rings):
        g = m.copy()
        g[e[m[e[:, 0]], 1]] = True
        g[e[m[e[:, 1]], 0]] = True
        m = g
    return m


def split_hair_collar(body):
    """Rip the nape: TRELLIS fused the bottom of the bob into the collar. Faces are classed hair (head) or collar by
    the rim height and the paint (as in part_masks), the classes are cleaned with a majority filter over neighbouring
    faces, and every edge between a hair face and a collar face in the nape zone is split, so the hair can follow
    the head without dragging the collar (and the collar without stretching the hair)."""
    me = body.data
    M = part_masks(body)
    head_v = M["head"]
    co = K.mesh_co(me)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    nf = len(bm.faces)
    C = np.array([f.calc_center_median()[:] for f in bm.faces])
    zone = nape_zone(C[:, 0], C[:, 1], C[:, 2]) & (C[:, 2] < 1.53)
    hv = np.array([np.mean([head_v[v.index] for v in f.verts]) for f in bm.faces]) > 0.5
    adj = [[g.index for e in f.edges for g in e.link_faces if g is not f] for f in bm.faces]
    for _ in range(3):
        new = hv.copy()
        for i in np.where(zone)[0]:
            nb = adj[i]
            if nb:
                frac = np.mean(hv[nb])
                if frac > 0.67:
                    new[i] = True
                elif frac < 0.33:
                    new[i] = False
        hv = new
    cut = [e for e in bm.edges if len(e.link_faces) == 2 and
           zone[e.link_faces[0].index] and zone[e.link_faces[1].index] and
           hv[e.link_faces[0].index] != hv[e.link_faces[1].index]]
    n0 = len(bm.verts)
    bmesh.ops.split_edges(bm, edges=cut)
    bm.to_mesh(me)
    bm.free()
    me.update()
    log(f"nape: hair split from the collar along {len(cut)} edges (+{len(me.vertices) - n0} verts)")


def limit_arm_weights(W, names, co, arm):
    """Review round 2. (a) Sharpen the arm-vs-torso split of the heat weights (the arm chain's share A -> a
    smoothstep of A), so the armpit blend band is narrow. (b) Cap the upper arm by the distance to its bone segment
    (full within 7.5 cm, none beyond 10.5 cm) and the clavicle (full within 6.5 cm, none beyond 10 cm): the chest,
    the chest plate, the lats and the jet-pack strap area go back to the spine. (c) No arm weight across the
    mid-line. Removed weight goes to the remaining (spine) bones of each vertex, or spine_03."""
    bones = arm.data.bones
    sp3 = names.index("spine_03")
    W = W.copy()
    x = co[:, 0]
    for s_, sx in (("l", 1), ("r", -1)):
        chain = [f"upperarm_{s_}", f"lowerarm_{s_}", f"hand_{s_}"] + \
            [f"{f}_0{k}_{s_}" for f in R.FINGERS + ("thumb",) for k in (1, 2, 3)]
        ci = [names.index(c) for c in chain]
        A = W[:, ci].sum(1)
        A2 = K.smoothstep(0.22, 0.78, A)
        rest = 1.0 - A
        scale_arm = np.where(A > 1e-6, A2 / np.maximum(A, 1e-6), 0.0)
        scale_rest = np.where(rest > 1e-6, (1.0 - A2) / np.maximum(rest, 1e-6), 0.0)
        others = [i for i in range(W.shape[1]) if i not in ci]
        W[:, ci] *= scale_arm[:, None]
        W[:, others] *= scale_rest[:, None]
        # where everything was arm and the sharpening removed some, the spine takes it
        miss = 1.0 - W.sum(1)
        W[:, sp3] += np.clip(miss, 0, None)
        ua, la = bones[f"upperarm_{s_}"], bones[f"lowerarm_{s_}"]
        a0, a1 = np.array(ua.head_local[:]), np.array(ua.tail_local[:])
        t_ua = np.clip(((co - a0) @ (a1 - a0)) / ((a1 - a0) @ (a1 - a0)), 0.0, 1.0)
        d_ua = seg_dist(co, ua.head_local, ua.tail_local)
        d_la = seg_dist(co, la.head_local, la.tail_local)
        d_arm = np.minimum(d_ua, d_la)
        t_ua = np.where(d_la < d_ua, 1.0, t_ua)
        # near the shoulder the torso is close (tight cap); toward the elbow the puffy sleeve reaches 12 cm from the
        # bone line and the torso is far away (wide cap)
        r_ua = 0.075 + 0.06 * K.smoothstep(0.35, 0.9, t_ua)
        for bn, r0, r1 in ((f"upperarm_{s_}", r_ua, r_ua + 0.035), (f"clavicle_{s_}", 0.065, 0.10)):
            b = bones[bn]
            # the upper arm is measured to the whole arm (elbow / forearm verts keep their upper-arm share)
            d = d_arm if bn.startswith("upperarm") else seg_dist(co, b.head_local, b.tail_local)
            k = names.index(bn)
            keep = 1.0 - np.clip((d - r0) / (r1 - r0), 0.0, 1.0) ** 2 * (3 - 2 * np.clip((d - r0) / (r1 - r0), 0.0, 1.0))
            keep = np.where(sx * x < 0.0, 0.0, keep)
            removed = W[:, k] * (1.0 - keep)
            W[:, k] -= removed
            # hand the removed weight to the spine bones the vertex already uses (or spine_03)
            spines = [names.index(n) for n in ("spine_01", "spine_02", "spine_03", "neck_01")]
            ssum = W[:, spines].sum(1)
            share = np.where(ssum[:, None] > 1e-6, W[:, spines] / np.maximum(ssum, 1e-6)[:, None], 0.0)
            share[ssum <= 1e-6, spines.index(sp3)] = 1.0
            W[:, spines] += share * removed[:, None]
        # (d) arm core: past the shoulder, every vertex of the sleeve belongs to the arm alone. The voxel proxy fuses
        # the back of the bulky sleeve with the back panel / jet pods, so the heat solve leaves 30-50 % spine on
        # the sleeve's back and top, which tore into big sheets with the arms raised. A vertex is arm core when it
        # is within 7.5 cm of the arm's bone line, or within 9.5 cm and facing away from the torso (the
        # armpit / torso side keeps its sharpened blend).
        ax = (a1 - a0) / np.linalg.norm(a1 - a0)
        foot = a0 + np.outer(np.clip((co - a0) @ ax, 0.0, None), ax)
        radial = co - foot
        radial -= np.outer(radial @ ax, ax)
        rn = radial / np.maximum(np.linalg.norm(radial, axis=1), 1e-9)[:, None]
        med = np.array([-sx, 0.0, 0.0])
        med = med - (med @ ax) * ax
        med /= np.linalg.norm(med)
        cos_med = rn @ med
        core = (t_ua > 0.22) & (sx * x > 0.12) & ((d_arm < 0.075) | ((d_arm < 0.095) & (cos_med < 0.2)))
        A = W[:, ci].sum(1)
        has = core & (A > 0.05)
        W[has] = np.where(np.isin(np.arange(W.shape[1]), ci)[None, :], W[has] / A[has][:, None], 0.0)
        none = core & ~has
        W[none] = 0.0
        W[none, names.index(f"upperarm_{s_}")] = np.where(d_la[none] < d_ua[none], 0.0, 1.0)
        W[none, names.index(f"lowerarm_{s_}")] = np.where(d_la[none] < d_ua[none], 1.0, 0.0)
        ARM_CORE[s_] = core
    return W


ARM_CORE = {}       # per side: vertex mask of the arm core (filled by limit_arm_weights, used by the jet-pack mask)
ARMPIT_Z = 1.335    # below this the sleeve and the torso are separate surfaces (TRELLIS fused them behind the arm)


def rip_arm_seams(body, W, names):
    """TRELLIS filled the gap between the back of each sleeve and the back panel / jet pods, so the arm and the torso
    are one surface far below the armpit, and raising the arms (zipline, overhead) dragged that surface into a big
    sheet. Faces are classed arm / torso by the arm chain's weight share; every edge between an arm face and a torso
    face below the armpit height (ARMPIT_Z) on the side of the body is ripped, and the vertices on each side of
    the rip become pure arm / pure torso. In the rest pose and most poses the two copies coincide; with the arms up
    the sleeve lifts off the side of the jacket instead of tearing it."""
    me = body.data
    co = K.mesh_co(me)
    nv0 = len(co)
    shares = {}
    for s_ in ("l", "r"):
        ci = [names.index(n) for n in names if n.endswith("_" + s_) and
              n.startswith(("upperarm", "lowerarm", "hand") + R.FINGERS + ("thumb",))]
        shares[s_] = (ci, W[:, ci].sum(1))
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = bm.verts.layers.int.new("_orig")
    for v in bm.verts:
        v[lay] = v.index
    bm.faces.ensure_lookup_table()
    cut = []
    side_of = {}
    for s_, sx in (("l", 1), ("r", -1)):
        _, A = shares[s_]
        fa = np.array([np.mean([A[v.index] for v in f.verts]) > 0.5 for f in bm.faces])
        zone = np.array([sx * f.calc_center_median().x > 0.12 and f.calc_center_median().z < ARMPIT_Z + 0.05
                         for f in bm.faces])
        adj = [[g.index for e in f.edges for g in e.link_faces if g is not f] for f in bm.faces]
        for _ in range(3):
            new_fa = fa.copy()
            for i in np.where(zone)[0]:
                nb = adj[i]
                if nb:
                    m_ = np.mean(fa[nb])
                    if m_ > 0.67:
                        new_fa[i] = True
                    elif m_ < 0.33:
                        new_fa[i] = False
            fa = new_fa
        for e in bm.edges:
            if len(e.link_faces) != 2:
                continue
            f0, f1 = e.link_faces
            if fa[f0.index] == fa[f1.index]:
                continue
            c = (e.verts[0].co + e.verts[1].co) / 2
            if c.z < ARMPIT_Z and sx * c.x > 0.12:
                cut.append(e)
                side_of[e] = s_
        shares[s_] = shares[s_] + (fa,)
    bmesh.ops.split_edges(bm, edges=cut)
    bm.verts.ensure_lookup_table()
    orig = np.array([v[lay] for v in bm.verts])
    # below the armpit the arm / torso split becomes binary (each vertex by the class of its faces), blending back to
    # the sharpened heat weights over 5 cm above ARMPIT_Z (the shoulder / armpit keeps a soft transition)
    W2 = W[orig].copy()
    zz = np.array([v.co.z for v in bm.verts])
    xx = np.array([v.co.x for v in bm.verts])
    fixed = 0
    for s_, sx in (("l", 1), ("r", -1)):
        ci, A, fa = shares[s_]
        others = [i for i in range(W.shape[1]) if i not in ci]
        isarm = np.zeros(W.shape[1], bool)
        isarm[ci] = True
        bf = 1.0 - K.smoothstep(ARMPIT_Z - 0.01, ARMPIT_Z + 0.04, zz)
        for v in bm.verts:
            i = v.index
            if not v.link_faces or sx * xx[i] <= 0.12 or bf[i] <= 0.0:
                continue
            frac = np.mean([fa[f.index] for f in v.link_faces])
            w = W2[i].copy()
            a_ = w[ci].sum()
            if frac >= 0.5:
                tgt = np.where(isarm, w, 0.0)
                if a_ > 1e-4:
                    tgt /= a_
                else:
                    tgt[names.index(f"upperarm_{s_}")] = 1.0
            else:
                tgt = np.where(isarm, 0.0, w)
                r = tgt.sum()
                if r > 1e-4:
                    tgt /= r
                else:
                    tgt[names.index("spine_03")] = 1.0
            W2[i] = w * (1.0 - bf[i]) + tgt * bf[i]
            fixed += 1
    bm.verts.layers.int.remove(lay)
    bm.to_mesh(me)
    bm.free()
    me.update()
    for s_ in list(ARM_CORE):
        ARM_CORE[s_] = ARM_CORE[s_][orig]
    log(f"arm seams: {len(cut)} edges ripped below the armpits (+{len(me.vertices) - nv0} verts), "
        f"{fixed} verts below the armpits made arm / torso")
    return W2


def part_masks(body):
    """Vertex masks for the rigid parts (by position + texture colour)."""
    me = body.data
    co = K.mesh_co(me)
    img = bpy.data.images.get("KES_BaseColor")
    vc = K.vertex_colors_from_texture(me, K.img_to_np(img))
    x, y, z = co.T
    lum = vc.mean(1)
    lin = np.where(vc <= 0.04045, vc / 12.92, ((vc + 0.055) / 1.055) ** 2.4)
    hairish = (lin[:, 2] / (np.maximum(lin[:, 0], lin[:, 1]) + 0.0015) > 1.3) & (lum < 0.30)
    teal = (vc[:, 1] > vc[:, 0] + 0.2) & (vc[:, 2] > vc[:, 0] + 0.15)
    skin = (vc[:, 0] > 0.55) & (vc[:, 0] - vc[:, 2] > 0.22)
    rad_neck = np.hypot(x - 0.005, y - 0.008)
    rad_head = np.hypot(x - 0.005, y - 0.015)
    # teal is both the dyed hair tips and the collar piping: a teal vertex is hair when most of its neighbours
    # (two rings) are hair or teal, piping when it sits in charcoal
    e = K.edge_array(me)
    ht = (hairish | teal).astype(np.float64)
    cnt = np.zeros(len(co))
    np.add.at(cnt, e[:, 0], 1)
    np.add.at(cnt, e[:, 1], 1)
    for _ in range(2):
        acc = np.zeros(len(co))
        np.add.at(acc, e[:, 0], ht[e[:, 1]])
        np.add.at(acc, e[:, 1], ht[e[:, 0]])
        ht = acc / np.maximum(cnt, 1)
    tip = teal & (ht > 0.6) & (z > 1.33)
    M = {}
    M["collar"] = (~hairish) & (~skin) & ~tip & (rad_neck > 0.045) & (rad_neck < 0.115) & (z > 1.36) & (z < 1.53) & \
        ~((z > 1.47) & (rad_neck < 0.085) & (y < -0.02))
    # head / neck split along a tilted jaw plane: under the chin at the front (y -0.08, z 1.415) rising to the
    # nape at the back (y +0.06, z 1.50)
    z_jaw = 1.415 + (y + 0.08) * (0.085 / 0.14)
    M["head"] = (((z > z_jaw) & (rad_head < 0.17)) | ((hairish | tip) & (z > 1.33) & (rad_head < 0.17))) & \
        ~M["collar"]
    M["neck"] = skin & (z > 1.36) & (z <= z_jaw) & (rad_neck < 0.075) & ~M["head"]
    # nape (review round 2): behind and beside the neck everything above the collar rim is hair -> head, whatever
    # its paint (TRELLIS shaded the bob's underside grey); below the rim and not hair-coloured is collar
    z_rim, ang = nape_rim(x, y)
    nape = nape_zone(x, y, z)
    M["head"] |= nape & (z >= z_rim)
    M["collar"] |= nape & (z < z_rim) & ~(hairish | tip) & (np.abs(ang) < 65.0)
    M["collar"] &= ~M["head"]
    M["neck"] &= ~M["collar"]
    M["_zjaw"] = z_jaw
    M["_zrim"] = z_rim
    M["jet"] = (y > 0.118) & (z > 0.98) & (z < 1.52) & (np.abs(x) < 0.218)
    bone = (lum > 0.58) & (np.abs(vc[:, 0] - vc[:, 2]) < 0.12)
    M["chest"] = chest_plate_mask(co)
    # elbow pads: bone-coloured caps on the back of each elbow -> rigid on the forearm
    # (TRELLIS's puffy sleeves put the pads 9-18 cm behind the elbow joint)
    pad = bone & (np.abs(x) > 0.22) & (np.abs(x) < 0.48) & (z > 0.95) & (z < 1.25) & (y > 0.06)
    near_el = np.linalg.norm(co - np.where(x[:, None] > 0, ELBOW["l"], ELBOW["r"]), axis=1) < 0.21
    M["elbow"] = grow(me, pad, 1) & near_el & (y > 0.05) & (np.abs(x) > 0.22)
    bm = bmesh.new()
    bm.from_mesh(me)
    pouch = np.zeros(len(co), bool)
    for isl in K.islands(bm):
        c = co[isl].mean(0)
        if 0.10 < c[0] < 0.23 and 0.9 < c[2] < 1.08 and len(isl) < 800:
            pouch[isl] = True
    bm.free()
    # the front pouch's flap and the back pouch are fused with the belt / trousers: everything in the pouches' box
    # (above the hip joint, not the hand that hangs next to it) is pouch too
    box = (x > 0.10) & (x < 0.215) & (y > -0.125) & (y < 0.06) & (z > 0.93) & (z < 1.06)
    M["pouch"] = pouch | (box & (np.abs(x) < 0.30))
    M["holster"] = (x < -0.178) & (x > -0.26) & (z > 0.60) & (z < 0.93) & (y > -0.11) & (y < 0.10)
    M["_z"] = z
    return M


def rigid_overrides(body, W, names):
    M = part_masks(body)
    z = M["_z"]
    co = K.mesh_co(body.data)
    W = set_rigid(W, names, M["head"], {"head": 1.0})
    zj = M["_zjaw"][M["neck"]]
    f = K.smoothstep(zj - 0.05, zj, z[M["neck"]])
    Wn = np.zeros((M["neck"].sum(), W.shape[1]))
    Wn[:, names.index("neck_01")] = 1 - f
    Wn[:, names.index("head")] = f
    W[M["neck"]] = Wn
    # collar: spine_03 at the base rising to 50 % neck_01 at the rim (the rim follows the neck a little, the hair
    # above it is split off and rigid on the head)
    zr = np.maximum(M["_zrim"][M["collar"]], 1.44)
    fz = K.smoothstep(1.38, zr, z[M["collar"]])
    Wc = np.zeros((M["collar"].sum(), W.shape[1]))
    Wc[:, names.index("spine_03")] = 1 - 0.5 * fz
    Wc[:, names.index("neck_01")] = 0.5 * fz
    W[M["collar"]] = Wc
    # jet pack: rigid on spine_03, but never the arm's sleeve that the box around it reaches
    for s_ in ("l", "r"):
        if s_ in ARM_CORE and len(ARM_CORE[s_]) == len(z):
            M["jet"] &= ~ARM_CORE[s_]
    W = set_rigid(W, names, M["jet"], {"spine_03": 1.0})
    # chest plate: both layers inside its outline rigid on spine_03; the bottom row takes up to 30 % spine_02
    ch = M["chest"]
    fb = 1.0 - K.smoothstep(CHEST_OUTLINE[0][0], CHEST_OUTLINE[0][0] + 0.035, z[ch])
    Wp = np.zeros((ch.sum(), W.shape[1]))
    Wp[:, names.index("spine_03")] = 1.0 - 0.3 * fb
    Wp[:, names.index("spine_02")] = 0.3 * fb
    W[ch] = Wp
    for s_ in ("l", "r"):
        m = M["elbow"] & ((co[:, 0] > 0) == (s_ == "l"))
        W = set_rigid(W, names, m, {f"lowerarm_{s_}": 1.0})
    W = set_rigid(W, names, M["pouch"], {"pelvis": 1.0})
    W = set_rigid(W, names, M["holster"], {"thigh_r": 1.0})
    # soft ring around the rigid chest plate and the collar base (jacket only): a few smoothing passes over the
    # vertices within 3 cm of them, the rigid parts themselves stay fixed
    fixed = M["chest"] | M["head"] | M["jet"] | M["collar"] | M["elbow"] | M["pouch"] | M["holster"] | M["neck"]
    ring = (grow(body.data, M["chest"], 4) | grow(body.data, M["pouch"], 2)) & ~fixed
    for _ in range(4):
        Ws = smooth_weights(body, W, iters=1, factor=0.5)
        W[ring] = Ws[ring]
    log("rigid: " + ", ".join(f"{k} {int(v.sum())}" for k, v in M.items() if not k.startswith("_")) +
        f", chest / pouch ring {int(ring.sum())}")
    return W


def despeckle(body, W, thresh=0.9, passes=2):
    """Single vertices whose weights disagree with ALL their neighbours (which agree among themselves) are set to
    the neighbours' mean: one stray vertex on a rigid part or across a classification border is a needle in poses."""
    e = K.edge_array(body.data)
    n = len(W)
    total = 0
    for _ in range(passes):
        S = np.zeros_like(W)
        cnt = np.zeros(n)
        np.add.at(S, e[:, 0], W[e[:, 1]])
        np.add.at(S, e[:, 1], W[e[:, 0]])
        np.add.at(cnt, e[:, 0], 1)
        np.add.at(cnt, e[:, 1], 1)
        mean = S / np.maximum(cnt, 1)[:, None]
        # spread of the neighbours around their mean
        D = np.zeros(n)
        np.add.at(D, e[:, 0], np.abs(W[e[:, 1]] - mean[e[:, 0]]).sum(1))
        np.add.at(D, e[:, 1], np.abs(W[e[:, 0]] - mean[e[:, 1]]).sum(1))
        spread = D / np.maximum(cnt, 1)
        off = np.abs(W - mean).sum(1)
        bad = (cnt >= 2) & (off > thresh) & (spread < 0.35 * off)
        W[bad] = mean[bad]
        total += int(bad.sum())
    log(f"despeckle: {total} stray vertices set to their neighbours' weights")
    return W


def smooth_weights(body, W, iters=2, factor=0.5):
    e = K.edge_array(body.data)
    for _ in range(iters):
        S = np.zeros_like(W)
        cnt = np.zeros(len(W))
        np.add.at(S, e[:, 0], W[e[:, 1]])
        np.add.at(S, e[:, 1], W[e[:, 0]])
        np.add.at(cnt, e[:, 0], 1)
        np.add.at(cnt, e[:, 1], 1)
        avg = S / np.maximum(cnt, 1)[:, None]
        W = W * (1 - factor) + avg * factor
    return W


def build_rig():
    body = K.body()
    J = R.compute_joints(body)
    arm = R.build_armature(J)
    for s_ in ("l", "r"):
        ELBOW[s_] = np.array(J[f"upperarm_{s_}"][1][:])
    split_hair_collar(body)
    cache = os.path.join(K.WORK, "heat_weights.npz")
    if os.environ.get("KES_HEAT_CACHE") and os.path.exists(cache):   # development shortcut only
        d = np.load(cache, allow_pickle=True)
        W, names = d["W"], list(d["names"])
        assert len(W) == len(body.data.vertices)
        log("heat weights loaded from the development cache")
    else:
        W, names = heat_proxy_weights(body, arm)
        np.savez(cache, W=W, names=np.array(names))
    co = K.mesh_co(body.data)
    W = smooth_weights(body, W, iters=2, factor=0.5)
    W = hand_weights(co, W, names, arm, J)
    # light smoothing over the hands so the glove shell and the skin hand under it move together
    hand_zone = np.zeros(len(co), bool)
    for s_ in ("l", "r"):
        hand_zone |= np.linalg.norm(co - np.array(J[f"_handinfo_{s_}"]["hand_end"][:]), axis=1) < 0.13
    Ws = smooth_weights(body, W, iters=2, factor=0.5)
    W[hand_zone] = Ws[hand_zone]
    W = limit_arm_weights(W, names, co, arm)
    W = rigid_overrides(body, W, names)
    W = rip_arm_seams(body, W, names)          # after the rigid parts: the elbow pads / jet pods have their final side
    W = despeckle(body, W)
    W = write_weights(body, W, names)
    log(f"skin: {len(names)} deform bones, {(W.sum(1) == 0).sum()} unweighted verts, "
        f"max influences {(W > 0).sum(1).max()}")
    for ob in (body, bpy.data.objects.get("KES_Eyepiece")):
        if ob is None:
            continue
        ob.parent = arm
        ob.matrix_parent_inverse.identity()
        for m in [m for m in ob.modifiers if m.type == "ARMATURE"]:
            ob.modifiers.remove(m)
        md = ob.modifiers.new("Armature", "ARMATURE")
        md.object = arm
    ep = bpy.data.objects.get("KES_Eyepiece")
    if ep is not None:
        for vg in list(ep.vertex_groups):
            ep.vertex_groups.remove(vg)
        vg = ep.vertex_groups.new(name="head")
        vg.add(list(range(len(ep.data.vertices))), 1.0, "REPLACE")
    # hand frames for the weapon sockets / fist test
    for s in ("l", "r"):
        H = J[f"_handinfo_{s}"]
        a, L, n = H["frame"]
        # n = a x lat points to the palm on one hand and to the back of the other: the palm faces the body
        # (A-pose, thumbs forward), so flip it to the medial side for both
        medial = Vector((-1.0 if s == "l" else 1.0, 0.0, 0.0))
        palm = n if n.dot(medial) > 0 else -n
        arm[f"kes_hand_{s}"] = {"a": list(a), "lat": list(L), "n": list(palm), "wrist": list(H["wrist"]),
                                "thumb_tip": list(H["thumb"][3]), "index_mcp": list(H["index"][0]),
                                "pinky_mcp": list(H["pinky"][0]), "middle_mcp": list(H["middle"][0])}
    return arm
