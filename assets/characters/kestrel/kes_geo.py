"""Stage A (part 2) for build_kestrel.py: face geometry repairs on the TRELLIS mesh (review fixes).

1. rebuild_left_eye: TRELLIS baked the eyepiece as an opaque disc (a ~5 mm thin pillow standing 8-14 mm proud of
   her LEFT eye) whose walls run back into a crumpled eye socket and temple. Projecting those layers onto one
   surface leaves crumpled, z-fighting slivers, so instead we CUT the whole left eye socket out (every layer inside
   an angular window around the old disc) and fill the outer hole with a new, clean patch:
     - target surface T: in a head-centred radial frame (azimuth/elevation around H) the outer skin of her RIGHT
       side is mirrored across the face's symmetry plane, plus a smooth (harmonic) correction measured on the
       clean skin ring around the window (her left side sits a few mm fuller);
     - the outer hole is triangle-filled, refined to ~1.6 mm edges and every new vertex is set radially onto T plus
       a harmonic blend of the boundary mismatch, so the patch meets the old skin exactly; a few relax steps even
       out the triangles;
     - the patch gets its own UV islands, tiled into free texel space of the TRELLIS atlas, so stage B can paint
       the mirrored eye, lids and brow on it like on any other texel.
   The inner shell's hole (inside the head) stays open; it is never visible.
2. flatten_lips: the lips stood out in a pout; push the mouth area back and relax it.

All coordinates: metres, Z up, front = -Y, her left = +X.
"""
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import kes_lib as K
from kes_lib import log

H = np.array([0.005, 0.015, 1.51])        # radial frame centre (inside the head, eye level)
AZ0, AZ1, EL0, EL1, STEP = -100.0, 100.0, -45.0, 50.0, 0.5   # map extent (degrees)
# rebuild window (degrees): the old disc + its side walls + the temple shards, feathered at the edge
WIN_AZ, WIN_AZR = 46.0, 50.0
WIN_EL, WIN_ELR = 3.0, 36.0
MAX_EDGE = 0.0045                          # longer edges in the rebuilt area are split
DEEP = 0.020                               # layers deeper than this under the target are left alone
RELIEF_MAX = 0.005
INNER_GAP = 0.0003                         # collapsed inner layers sit this far under the new skin


def _dirs(az, el):
    a, e = np.radians(az), np.radians(el)
    return np.stack([np.sin(a) * np.cos(e), -np.cos(a) * np.cos(e), np.sin(e)], -1)


def _angles(P):
    d = P - H
    r = np.linalg.norm(d, axis=-1)
    az = np.degrees(np.arctan2(d[..., 0], -d[..., 1]))
    el = np.degrees(np.arcsin(np.clip(d[..., 2] / np.maximum(r, 1e-9), -1, 1)))
    return az, el, r


def window_weight(az, el):
    e = np.hypot((az - WIN_AZ) / WIN_AZR, (el - WIN_EL) / WIN_ELR)
    return 1.0 - K.smoothstep(0.78, 1.0, e)


def _grid_shape():
    return int(round((EL1 - EL0) / STEP)) + 1, int(round((AZ1 - AZ0) / STEP)) + 1


def _to_grid(az, el):
    return (az - AZ0) / STEP, (EL1 - el) / STEP


def _sample(G, az, el):
    h, w = G.shape
    gx, gy = _to_grid(az, el)
    gx = np.clip(gx, 0, w - 1.001)
    gy = np.clip(gy, 0, h - 1.001)
    x0, y0 = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = gx - x0, gy - y0
    return (G[y0, x0] * (1 - fx) * (1 - fy) + G[y0, x0 + 1] * fx * (1 - fy) + G[y0 + 1, x0] * (1 - fx) * fy
            + G[y0 + 1, x0 + 1] * fx * fy)


def _face_flags(obj, vc):
    """Per-face 'hair' flag from the vertex colours (TRELLIS paint)."""
    me = obj.data
    hair_v = K.hair_mask_np(vc)
    nf = len(me.polygons)
    loop_start = np.zeros(nf, np.int64)
    loop_total = np.zeros(nf, np.int64)
    me.polygons.foreach_get("loop_start", loop_start)
    me.polygons.foreach_get("loop_total", loop_total)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    acc = np.zeros(nf)
    np.add.at(acc, np.repeat(np.arange(nf), loop_total), hair_v[lv].astype(float))
    return acc / np.maximum(loop_total, 1) > 0.5


def _face_flags_skin(obj, vc):
    """Per-face 'skin colour' flag (majority of its vertices)."""
    me = obj.data
    sk = K.skin_mask_np(vc)
    nf = len(me.polygons)
    loop_total = np.zeros(nf, np.int64)
    me.polygons.foreach_get("loop_total", loop_total)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    acc = np.zeros(nf)
    np.add.at(acc, np.repeat(np.arange(nf), loop_total), sk[lv].astype(float))
    return acc / np.maximum(loop_total, 1) > 0.5


def _radial_skin_map(bvh, face_hair):
    """Outer non-hair surface radius along every map direction (NaN where none), and a flag map that is True
    where hair lies in front of that skin (under the fringe TRELLIS left a crumpled, unusable surface)."""
    h, w = _grid_shape()
    els = EL1 - np.arange(h) * STEP
    azs = AZ0 + np.arange(w) * STEP
    R = np.full((h, w), np.nan)
    HC = np.zeros((h, w), bool)
    Hv = Vector(H.tolist())
    for iy, el in enumerate(els):
        D = _dirs(azs, np.full_like(azs, el))
        for ix in range(w):
            d = Vector(D[ix].tolist())
            p = Hv + d * 0.25
            for _ in range(8):
                loc, nrm, fi, dist = bvh.ray_cast(p, -d, 0.25)
                if loc is None:
                    break
                r = (loc - Hv).dot(d)
                if r < 0.03:
                    break
                if nrm.dot(d) > 0 and not face_hair[fi]:
                    R[iy, ix] = r
                    break
                if face_hair[fi] and r > 0.03:
                    HC[iy, ix] = True
                p = loc - d * 0.0002
    return R, HC


def _fill(G, levels=8):
    """Push-pull hole fill of NaNs in a 2D map."""
    import kes_face
    w = np.isfinite(G).astype(float)
    out = kes_face.push_pull(np.nan_to_num(G)[..., None], w, levels)[..., 0]
    return np.where(np.isfinite(G), G, out)


def harmonic_fill(G, known, domain, iters=2500):
    """Laplace fill of the unknown cells inside `domain` (Jacobi; cells outside the domain are ignored, i.e. a
    zero-flux boundary)."""
    T = _fill(np.where(known, G, np.nan))
    unk = domain & ~known
    dom = domain.astype(float)
    for _ in range(iters):
        P = np.pad(T * dom, 1)
        D = np.pad(dom, 1)
        s = P[:-2, 1:-1] + P[2:, 1:-1] + P[1:-1, :-2] + P[1:-1, 2:]
        n = D[:-2, 1:-1] + D[2:, 1:-1] + D[1:-1, :-2] + D[1:-1, 2:]
        T = np.where(unk & (n > 0), s / np.maximum(n, 1), T)
    return T


def _debug_maps(R, T, win, Mm):
    import os
    d = os.path.join(K.WORK, "dev")
    if not os.path.isdir(d):
        return
    def norm(a, lo=0.055, hi=0.10):
        return np.clip((np.nan_to_num(a, nan=lo) - lo) / (hi - lo), 0, 1)
    img = np.stack([norm(R), norm(T), win], -1)
    K.save_png(K.np_to_img("_dbg_maps", img[::-1].copy()), os.path.join(d, "radial_maps.png"))
    img2 = np.stack([norm(Mm), norm(T), np.clip((T - np.nan_to_num(R, nan=0.0)) * 50 + 0.5, 0, 1)], -1)
    K.save_png(K.np_to_img("_dbg_maps2", img2[::-1].copy()), os.path.join(d, "radial_maps2.png"))


def target_map(obj):
    """Radial target map T (metres from H) for her left eye region: mirrored right-side outer skin + a harmonic
    correction measured on the clean skin ring around the window. Also returns the per-vertex texture colours."""
    me = obj.data
    px = K.img_to_np(K.base_image())
    vc = K.vertex_colors_from_texture(me, px)
    face_hair = _face_flags(obj, vc)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    R, HC = _radial_skin_map(bvh, face_hair)
    h, w = R.shape
    els = EL1 - np.arange(h) * STEP
    azs = AZ0 + np.arange(w) * STEP
    AZ, EL = np.meshgrid(azs, els)
    win = window_weight(AZ, EL)
    # mirrored right-side skin points -> left target samples (her right temple, az < -65, is under the long bob)
    # (skin under the fringe on her right forehead is crumpled TRELLIS filler: not used, the harmonic fill bridges it)
    hc = HC.copy()
    for _ in range(3):                      # grow by 1.5 deg so the strand edges are excluded too
        hc = hc | np.roll(hc, 1, 0) | np.roll(hc, -1, 0) | np.roll(hc, 1, 1) | np.roll(hc, -1, 1)
    hc &= EL > 20.0                         # the fringe crosses her right eye too, but the eye skin there is fine
    right = np.isfinite(R) & (AZ < -1.0) & (AZ > -65.0) & (R > 0.05) & ~hc
    P = H + _dirs(AZ[right], EL[right]) * R[right][:, None]
    Pm = K.face_mirror_np(P)
    maz, mel, mr = _angles(Pm)
    M = np.zeros((h, w))
    C = np.zeros((h, w))
    gx, gy = _to_grid(maz, mel)
    ix, iy = np.rint(gx).astype(int), np.rint(gy).astype(int)
    ok = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
    np.add.at(M, (iy[ok], ix[ok]), mr[ok])
    np.add.at(C, (iy[ok], ix[ok]), 1)
    Mm = np.where(C > 0, M / np.maximum(C, 1), np.nan)
    import kes_face
    ear = (AZ > 88.0) & (np.abs(EL) < 28.0)
    own = np.where((win < 0.02) & (AZ > -1.0) & ~ear, R, np.nan)
    Mf = _fill(Mm)
    off = own - Mf
    known = np.isfinite(off) & (np.abs(off) < 0.02)
    O = harmonic_fill(np.where(known, off, np.nan), known, domain=(win >= 0.02) | known)
    T = kes_face.blur(Mf + O, 1.5)          # ~1 mm: removes TRELLIS facet noise
    _debug_maps(R, T, win, Mm)
    return T, vc


def _boundary_groups(bm):
    groups, seen = [], set()
    for e0 in bm.edges:
        if not e0.is_boundary or e0 in seen:
            continue
        grp, stack = [], [e0]
        seen.add(e0)
        while stack:
            e = stack.pop()
            grp.append(e)
            for v in e.verts:
                for e2 in v.link_edges:
                    if e2.is_boundary and e2 not in seen:
                        seen.add(e2)
                        stack.append(e2)
        groups.append(grp)
    return groups


class _Atlas:
    """Free-space allocator on the atlas coverage map: first-fit k x k squares (coverage dilated by pad)."""

    def __init__(self, cov, pad=3):
        occ = cov.copy()
        for _ in range(pad):
            occ = occ | np.roll(occ, 1, 0) | np.roll(occ, -1, 0) | np.roll(occ, 1, 1) | np.roll(occ, -1, 1)
        occ[:pad + 1] = True
        occ[-pad - 1:] = True
        occ[:, :pad + 1] = True
        occ[:, -pad - 1:] = True
        self.occ, self.pad = occ, pad

    def take(self, k):
        I = np.pad(np.cumsum(np.cumsum(self.occ.astype(np.int32), 0), 1), ((1, 0), (1, 0)))
        S = I[k:, k:] - I[:-k, k:] - I[k:, :-k] + I[:-k, :-k]
        free = np.argwhere(S == 0)
        if not len(free):
            return None
        r, c = (int(x) for x in free[0])
        p = self.pad
        self.occ[max(r - p, 0):r + k + p, max(c - p, 0):c + k + p] = True
        return r, c


def _win(P):
    """Cut window in (azimuth, elevation): a rounded box (superellipse, power 3) around the old disc, its walls,
    the crumpled temple behind it and the outer brow."""
    a, e, _ = _angles(np.atleast_2d(P))
    return (np.abs((a - CORE_AZ) / CORE_AZR) ** 3 + np.abs((e - CORE_EL) / CORE_ELR) ** 3) ** (1 / 3)


RM = 0.075                          # metres per radian in the (azimuth, elevation) parameter plane


def _cycle(grp):
    """Order a group of boundary edges into one vertex cycle (None if it is not a simple loop)."""
    adj = {}
    for e in grp:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    if any(len(n) != 2 for n in adj.values()):
        return None
    start = grp[0].verts[0]
    cyc, prev, cur = [start], None, start
    while True:
        nxt = adj[cur][0] if adj[cur][0] is not prev else adj[cur][1]
        if nxt is start:
            break
        cyc.append(nxt)
        prev, cur = cur, nxt
        if len(cyc) > len(adj):
            return None
    return cyc if len(cyc) == len(adj) else None


def _in_poly(P, Q):
    """Even-odd point-in-polygon test of 2D points P (n, 2) against polygon Q (m, 2)."""
    x, y = P[:, 0], P[:, 1]
    inside = np.zeros(len(P), bool)
    for k in range(len(Q)):
        x1, y1 = Q[k]
        x2, y2 = Q[(k + 1) % len(Q)]
        cross = ((y1 > y) != (y2 > y))
        xi = x1 + (y - y1) * (x2 - x1) / np.where(y2 != y1, y2 - y1, 1e-12)
        inside ^= cross & (x < xi)
    return inside


CORE_AZ, CORE_AZR = 47.0, 38.0      # cut window (degrees): old disc + walls + temple + outer brow
CORE_EL, CORE_ELR = 5.0, 29.0
PATCH_EDGE = 0.0020                 # target edge length of the new patch
UV_TEXEL = 0.0011                   # patch texel size (m/px), a bit finer than the TRELLIS face (~1.2 mm)
UV_CELL = 0.016                     # patch UV tiles (m); each tile is one UV island


def rebuild_left_eye(obj):
    me = obj.data
    T, vc = target_map(obj)
    co = K.mesh_co(me)
    az, el, r = _angles(co)
    rt = _sample(T, az, el)
    real_hair = K.hair_mask_np(vc) & ((co[:, 2] > 1.553) | (co[:, 0] > 0.088)) & (r > rt + 0.0025)
    # ---- 1. cut every layer inside the window that is near or in front of the target skin
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    kill = []
    for f in bm.faces:
        vs = [v.index for v in f.verts]
        c = co[vs].mean(0)
        if c[0] <= 0.0 or _win(c)[0] > 1.0 or real_hair[vs].sum() >= 2:
            continue
        a, e, rr = _angles(c[None])
        if rr[0] > _sample(T, a, e)[0] - 0.012:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # trim faces hanging off the cut edge by one edge, so the hole boundary is a clean loop
    for _ in range(6):
        spikes = [f for f in bm.faces if sum(e.is_boundary for e in f.edges) >= 2 and
                  _win(np.array(f.calc_center_median()[:]))[0] < 1.4]
        if not spikes:
            break
        bmesh.ops.delete(bm, geom=spikes, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    isl = K.islands(bm)
    bm.verts.ensure_lookup_table()
    scraps = [bm.verts[j] for i in isl if len(i) < 60 for j in i]
    if scraps:
        bmesh.ops.delete(bm, geom=scraps, context="VERTS")
    log(f"left eye: cut {len(kill)} faces (all layers) in the socket window, {len(scraps)} scrap verts")
    if os.environ.get("KES_DEBUG_STOP") == "cut":
        bm.to_mesh(me)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(K.WORK, "dev2", "cut.blend"), compress=False)
        raise SystemExit("debug stop after the cut")
    # ---- 2. the outer hole: the largest boundary loop around the window whose vertices sit on the target skin
    #        (the inner shell's loop lies ~6 mm under it and stays open, inside the head)
    def uvw(P):
        a, e, _ = _angles(np.atleast_2d(P))
        return np.stack([np.radians(a), np.radians(e)], -1) * RM

    def outer_loop():
        """The hole loop of the OUTER skin. The inner shell leaves a loop of almost the same size a few mm deeper,
        so the loops are ranked by how many of their vertices are covered by another surface right outside them
        (the outer loop is not covered), then by their area in the parameter plane."""
        best = None
        bm.faces.ensure_lookup_table()
        cbvh = BVHTree.FromBMesh(bm)
        Hv_ = Vector(H.tolist())
        for grp in _boundary_groups(bm):
            verts = list({v for e in grp for v in e.verts})
            P = np.array([v.co[:] for v in verts])
            a, e, rr = _angles(P)
            dev = rr - _sample(T, a, e)
            if os.environ.get("KES_DEBUG"):
                log(f"  boundary group {len(grp)} edges: in-window {(_win(P) < 1.5).mean():.2f}, "
                    f"median dev {np.median(dev) * 1000:.1f} mm")
            if len(grp) < 8 or (_win(P) < 1.6).mean() < 0.8 or np.median(dev) < -0.004:
                continue
            cyc = _cycle(grp)
            if cyc is None:
                continue
            Q = uvw(np.array([v.co[:] for v in cyc]))
            area = 0.5 * abs(np.sum(Q[:, 0] * np.roll(Q[:, 1], -1) - np.roll(Q[:, 0], -1) * Q[:, 1]))
            covered = 0
            for v in cyc:
                d = (v.co - Hv_).normalized()
                covered += cbvh.ray_cast(v.co + d * 0.0015, d, 0.03)[0] is not None
            key = (-round(covered / len(cyc), 1), area)
            if os.environ.get("KES_DEBUG"):
                log(f"  loop {len(cyc)}: area {area * 1e4:.1f} cm2, covered {covered}/{len(cyc)}")
            if best is None or key > best[0]:
                best = (key, cyc, Q)
        assert best is not None, "left eye: no outer hole found"
        return best[1], best[2]

    # second cut: every remaining layer inside the outer hole that would sit within 12 mm under the new skin
    # (rings of deeper layers whose face centres fell outside the window ellipse) - they would z-fight the patch
    for _ in range(3):
        cyc, Q = outer_loop()
        cset = set(cyc)
        cand = [f for f in bm.faces if not any(v in cset for v in f.verts)]
        C = np.array([f.calc_center_median()[:] for f in cand])
        inside = _in_poly(uvw(C), Q) & (C[:, 0] > 0.0)
        a, e, rr = _angles(C)
        near = rr > _sample(T, a, e) - 0.012
        kill2 = [f for f, k in zip(cand, inside & near) if k]
        if not kill2:
            break
        bmesh.ops.delete(bm, geom=kill2, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        log(f"left eye: second cut {len(kill2)} faces inside the outer hole")
    cyc, Q = outer_loop()
    # ---- 3. fill: constrained Delaunay triangulation of the hole polygon + a triangular lattice of interior
    #        points (PATCH_EDGE spacing) in the (azimuth, elevation) parameter plane
    lo, hi = Q.min(0), Q.max(0)
    sp = PATCH_EDGE
    pts = []
    for j, yv in enumerate(np.arange(lo[1], hi[1] + sp, sp * 0.866)):
        xs = np.arange(lo[0] + (sp / 2 if j % 2 else 0.0), hi[0] + sp, sp)
        pts += [(x, yv) for x in xs]
    pts = np.array(pts)
    pts = pts[_in_poly(pts, Q)]
    # keep lattice points away from the boundary polygon
    dmin = np.full(len(pts), np.inf)
    for k in range(len(Q)):
        a2, b2 = Q[k], Q[(k + 1) % len(Q)]
        ab = b2 - a2
        t = np.clip(((pts - a2) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        dmin = np.minimum(dmin, np.linalg.norm(pts - (a2 + np.outer(t, ab)), axis=1))
    pts = pts[dmin > 0.6 * sp]
    ccw = np.sum(Q[:, 0] * np.roll(Q[:, 1], -1) - np.roll(Q[:, 0], -1) * Q[:, 1]) > 0
    order = list(range(len(Q))) if ccw else list(range(len(Q)))[::-1]
    allp = [Vector((float(x), float(y))) for x, y in np.vstack([Q, pts])]
    from mathutils import geometry
    out_v, _, out_f, orig_v, _, _ = geometry.delaunay_2d_cdt(allp, [], [order], 1, 1e-7)
    nb = len(Q)
    newv = {}
    vmap = []
    for i, ov in enumerate(orig_v):
        src = ov[0] if ov else None
        if src is not None and src < nb:
            vmap.append(cyc[src])
        else:
            q = np.array(out_v[i][:])
            az_ = np.degrees(q[0] / RM)
            el_ = np.degrees(q[1] / RM)
            d = _dirs(np.array([az_]), np.array([el_]))[0]
            rr = _sample(T, np.array([az_]), np.array([el_]))[0]
            vmap.append(bm.verts.new((H + d * rr).tolist()))
    tag = bm.faces.layers.int.new("_patch")
    nf = 0
    for fv in out_f:
        try:
            f = bm.faces.new([vmap[i] for i in fv])
        except ValueError:
            continue
        f[tag] = 1
        nf += 1
    pset = {f for f in bm.faces if f[tag]}
    bverts = set(cyc)
    pverts = {v for f in pset for v in f.verts}
    interior = [v for v in pverts if v not in bverts]
    log(f"left eye: patch {len(pset)} faces ({len(interior)} interior verts) on a {len(cyc)}-edge hole")
    if os.environ.get("KES_DEBUG_STOP") == "fill":
        bm.to_mesh(me)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(K.WORK, "dev2", "fill.blend"), compress=False)
        raise SystemExit("debug stop after the fill")
    # ---- 4. place the patch on T + a harmonic blend of the boundary mismatch, relax the triangles
    idx_i = {v: k for k, v in enumerate(interior)}
    bl = list(bverts)
    Pb = np.array([v.co[:] for v in bl])
    ab, eb, rb = _angles(Pb)
    res_b = dict(zip(bl, (rb - _sample(T, ab, eb)).tolist()))
    nbrs = [[e.other_vert(v) for e in v.link_edges if e.other_vert(v) in pverts] for v in interior]
    nb_i = [[idx_i[u] for u in nb if u in idx_i] for nb in nbrs]
    nb_b = [[res_b[u] for u in nb if u in res_b] for nb in nbrs]
    res_i = np.zeros(len(interior))
    for _ in range(500):
        res_i = np.array([(res_i[ii].sum() + sum(bb)) / max(len(ii) + len(bb), 1) for ii, bb in zip(nb_i, nb_b)])
    Pi = np.array([v.co[:] for v in interior])
    Pall = {v: np.array(v.co[:]) for v in pverts}
    for it in range(5):
        if it:
            for k, v in enumerate(interior):
                Pall[v] = Pi[k]
            avg = np.array([np.mean([Pall[u] for u in nb], 0) if nb else Pi[k] for k, nb in enumerate(nbrs)])
            Pi = Pi + 0.4 * (avg - Pi)
        a, e, rr = _angles(Pi)
        rn = _sample(T, a, e) + res_i
        Pi = H + (Pi - H) / np.maximum(rr, 1e-9)[:, None] * rn[:, None]
    for k, v in enumerate(interior):
        v.co = Pi[k].tolist()
    # ---- 4b. any other layer left under the patch (inner shell rings, big TRELLIS triangles) is pushed radially to
    #         at least 4 mm under the new skin, so it cannot poke through it
    bm.verts.index_update()
    bm.verts.ensure_lookup_table()
    pbvh = BVHTree.FromPolygons([tuple(v.co) for v in bm.verts], [[v.index for v in f.verts] for f in pset])
    Hv = Vector(H.tolist())
    pushed = 0
    # only vertices well inside the hole outline (>= 2 mm from it), so the skin around the patch is left alone
    others = [v for v in bm.verts if v not in pverts and v.co.x > 0.0]
    W2 = uvw(np.array([v.co[:] for v in others]))
    ins = _in_poly(W2, Q)
    dmin = np.full(len(W2), np.inf)
    for k in range(len(Q)):
        a2, b2 = Q[k], Q[(k + 1) % len(Q)]
        ab = b2 - a2
        t = np.clip(((W2 - a2) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        dmin = np.minimum(dmin, np.linalg.norm(W2 - (a2 + np.outer(t, ab)), axis=1))
    for v, ok in zip(others, ins & (dmin > 0.002)):
        if not ok:
            continue
        d = (v.co - Hv)
        r0 = d.length
        d.normalize()
        hit = pbvh.ray_cast(Hv + d * 0.3, -d, 0.3)
        if hit[0] is None:
            continue
        rp = (hit[0] - Hv).length
        if r0 > rp - 0.004 and r0 < rp + 0.006:
            v.co = Hv + d * (rp - 0.004)
            pushed += 1
    log(f"left eye: {pushed} verts of other layers pushed under the patch")
    # ---- 5. winding from the neighbours, smooth shading
    for f in pset:
        f.smooth = True
    K.orient_like_neighbours(list(pset))
    for f in bm.faces:
        f.select = bool(f[tag])
    bm.faces.layers.int.remove(tag)
    bm.to_mesh(me)
    bm.free()
    # ---- 6. UVs: tile the patch into islands and pack them into free atlas space
    sel = np.zeros(len(me.polygons), bool)
    me.polygons.foreach_get("select", sel)
    pidx = np.where(sel)[0]
    import kes_tex
    img = kes_tex.bake_emit(obj, lambda nt: kes_tex._const(nt, (1, 1, 1)), "_cov_a", margin=0)
    cov = K.img_to_np(img)[..., 0] > 0.5
    bpy.data.images.remove(img)
    co = K.mesh_co(me)
    rmean = 0.075
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    cells = {}
    for fi in pidx:
        p = me.polygons[fi]
        a, e, _ = _angles(co[list(p.vertices)].mean(0)[None])
        key = (int(np.floor(np.radians(a[0]) * rmean / UV_CELL)), int(np.floor(np.radians(e[0]) * rmean / UV_CELL)))
        cells.setdefault(key, []).append(fi)
    Hh, Ww = cov.shape
    isl = []
    for key, fis in sorted(cells.items()):
        loops = [me.polygons[fi].loop_start + k for fi in fis for k in range(me.polygons[fi].loop_total)]
        a, e, _ = _angles(co[lv[loops]])
        isl.append((loops, np.radians(a) * rmean, np.radians(e) * rmean))
    for texel in (UV_TEXEL, UV_TEXEL * 1.2, UV_TEXEL * 1.45, UV_TEXEL * 1.75):
        atlas = _Atlas(cov)
        place = []
        for loops, u, v in sorted(isl, key=lambda t: -max(np.ptp(t[1]), np.ptp(t[2]))):
            k = int(np.ceil(max(np.ptp(u), np.ptp(v)) / texel)) + 4
            rc = atlas.take(k)
            if rc is None:
                break
            place.append((loops, u, v, rc))
        if len(place) == len(isl):
            break
    assert len(place) == len(isl), "left eye: no free atlas space for the patch UVs"
    for loops, u, v, (r0, c0) in place:
        uv[loops, 0] = (c0 + 2.0 + (u - u.min()) / texel) / Ww
        uv[loops, 1] = (r0 + 2.0 + (v - v.min()) / texel) / Hh
    worst = texel
    me.uv_layers.active.data.foreach_set("uv", uv.ravel())
    # remember the patch faces for stage B (its texels get a clean skin base before the eye/brow paint)
    at = me.attributes.get("_kes_patch") or me.attributes.new("_kes_patch", "FLOAT", "FACE")
    at.data.foreach_set("value", sel.astype(np.float32))
    for p in me.polygons:
        p.select = False
    me.update()
    log(f"left eye: patch UVs in {len(cells)} islands at {worst * 1000:.2f} mm/texel")
    return T


def _outer_flags(bvh, face_hair, P, r):
    """True where the point is (within 1.5 mm) the outermost non-hair outward surface along its direction."""
    Hv = Vector(H.tolist())
    out = np.zeros(len(P), bool)
    for k in range(len(P)):
        d = Vector(((P[k] - H) / max(r[k], 1e-9)).tolist())
        p = Hv + d * 0.25
        for _ in range(8):
            loc, nrm, fi, dist = bvh.ray_cast(p, -d, 0.25)
            if loc is None:
                break
            rr = (loc - Hv).dot(d)
            if nrm.dot(d) > 0 and not face_hair[fi]:
                out[k] = r[k] >= rr - 0.0015
                break
            p = loc - d * 0.0002
    return out


def flatten_lips(obj, push=0.0035):
    """Push the pouting lips back (front layer only) and relax the mouth area."""
    me = obj.data
    co = K.mesh_co(me)
    cx, cz, rx, rz = 0.010, 1.455, 0.026, 0.017
    e = np.hypot((co[:, 0] - cx) / rx, (co[:, 2] - cz) / rz)
    cand = np.where((e < 1.0) & (co[:, 1] < -0.03))[0]
    fl = K.front_layer_mask(obj, cand, tol=0.003)
    sel = cand[fl]
    w = 1.0 - K.smoothstep(0.35, 1.0, e[sel])
    co[sel, 1] += push * w
    K.set_mesh_co(me, co)
    n = K.smooth_heightfield(obj, (cx, cz), (rx, rz), iters=12, strength=0.5)
    log(f"lips: {len(sel)} verts pushed back up to {push * 1000:.1f} mm, {n} relaxed")


def under_patch(P):
    """True for a boundary (array of points) that lies in the rebuilt left-eye window (the inner shell's hole)."""
    P = np.atleast_2d(P)
    return bool(((_win(P) < 1.4) & (P[:, 0] > 0.0)).mean() > 0.6)


def smooth_patch_rim(obj, iters=16, strength=0.6):
    """Blend the new eye patch into the old skin: radial (heightfield) relaxation of the OUTER skin over the patch
    and a band of old skin around it (the old skin edge along the brow zig-zags in depth). Hair, inner layers and
    anything outside the band are left alone. Front-most faces in the band that show their back side (folded
    TRELLIS slivers) are sunk 4 mm under the skin."""
    me = obj.data
    co = K.mesh_co(me)
    pa = np.zeros(len(me.polygons), np.float32)
    me.attributes["_kes_patch"].data.foreach_get("value", pa)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    lt = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", lt)
    pv = np.zeros(len(co), bool)
    pv[lv[np.repeat(pa > 0.5, lt)]] = True
    vc = K.vertex_colors_from_texture(me, K.img_to_np(K.base_image()))
    hair = K.hair_mask_np(vc) & ~pv
    w = _win(co)
    band = (w < 1.45) & (co[:, 0] > -0.01) & (co[:, 1] < 0.03) & ~hair
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(obj, dg)
    Hv = Vector(H.tolist())
    outer = np.zeros(len(co), bool)
    for i in np.where(band)[0]:
        p = Vector(co[i].tolist())
        d = (p - Hv).normalized()
        hit = bvh.ray_cast(p + d * 0.05, -d, 0.06)
        outer[i] = hit[0] is not None and (hit[0] - p).dot(d) < 0.0015
    sel = (band & outer) | pv
    # weight: a band across the patch rim (w ~1): the patch interior keeps its mirrored eye relief, the old skin
    # is relaxed up to w 1.2, fading out by w 1.45
    wt = np.where(pv, K.smoothstep(0.72, 0.95, w), 1.0 - K.smoothstep(1.2, 1.45, w)) * sel * strength
    d = co - H
    r = np.linalg.norm(d, axis=1)
    u = d / np.maximum(r, 1e-9)[:, None]
    e = K.edge_array(me)
    # only edges between selected vertices carry the smoothing (no pull from inner layers or hair)
    ok = sel[e[:, 0]] & sel[e[:, 1]]
    e = e[ok]
    for _ in range(iters):
        s = np.zeros(len(co))
        n = np.zeros(len(co))
        np.add.at(s, e[:, 0], r[e[:, 1]])
        np.add.at(n, e[:, 0], 1)
        np.add.at(s, e[:, 1], r[e[:, 0]])
        np.add.at(n, e[:, 1], 1)
        avg = np.where(n > 0, s / np.maximum(n, 1), r)
        r = r + wt * (avg - r)
    co2 = H + u * r[:, None]
    moved = np.linalg.norm(co2 - co, axis=1)
    # other layers within 3 mm under the (new) outer skin of the band are pushed to 3 mm under it
    K.set_mesh_co(me, co2)
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(obj, dg)
    co = co2
    sunk = 0
    for i in np.where((w < 1.5) & (co[:, 0] > -0.01) & ~sel & ~hair)[0]:
        p = Vector(co[i].tolist())
        d_ = (p - Hv).normalized()
        hit = bvh.ray_cast(p + d_ * 0.0004, d_, 0.004)
        if hit[0] is not None:
            gap = (hit[0] - p).dot(d_)
            if gap < 0.003:
                co[i] = np.array((p - d_ * (0.003 - gap))[:])
                sunk += 1
    # front-most faces seen from their back: sink their vertices
    nrm = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    cen = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    wf = _win(cen)
    flipped = 0
    for fi in np.where((wf < 1.5) & (cen[:, 0] > -0.01) & (pa < 0.5))[0]:
        c = Vector(cen[fi].tolist())
        d_ = (c - Hv).normalized()
        if Vector(nrm[fi].tolist()).dot(d_) >= 0:
            continue
        hit = bvh.ray_cast(c + d_ * 0.05, -d_, 0.06)
        if hit[2] == fi:
            for vi in me.polygons[fi].vertices:
                if not pv[vi]:
                    co[vi] = co[vi] - u[vi] * 0.004
            flipped += 1
    K.set_mesh_co(me, co)
    log(f"patch rim: {int(sel.sum())} outer-skin verts relaxed (max move {moved.max() * 1000:.1f} mm), "
        f"{sunk} under-layer verts sunk, {flipped} back-facing front faces sunk")
