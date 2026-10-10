"""Geometry helpers for build_solace.py: hole filling with thin-plate-spline height patches, clean-texel lookup."""
import numpy as np
import bmesh
from mathutils import Vector

from sol_lib import log


def boundary_loops(edges):
    """Group boundary edges into ordered vertex loops: [(verts, closed)]."""
    es = set(edges)
    adj = {}
    for e in es:
        for v in e.verts:
            adj.setdefault(v, []).append(e)
    loops = []
    used = set()
    for e0 in es:
        if e0 in used:
            continue
        used.add(e0)
        chain = [e0.verts[0], e0.verts[1]]
        closed = False
        while True:
            v = chain[-1]
            nxt = [e for e in adj.get(v, []) if e not in used]
            if not nxt:
                break
            e = nxt[0]
            used.add(e)
            w = e.other_vert(v)
            if w is chain[0]:
                closed = True
                break
            chain.append(w)
        loops.append((chain, closed))
    return loops


def boundary_loops_directed(edges):
    """Closed boundary loops from boundary edges, walked in the winding direction opposite to their face, with
    figure-8 loops (pinch vertices) split into simple sub-loops. Returns [(verts, True)]."""
    out_e = {}
    for e in edges:
        if len(e.link_faces) != 1:
            continue
        f = e.link_faces[0]
        lp = next(l for l in f.loops if l.edge is e)
        a, b = lp.vert, lp.link_loop_next.vert   # face walks a->b, hole walks b->a
        out_e.setdefault(b, []).append((a, e))
    used = set()
    loops = []
    for v0, lst in list(out_e.items()):
        for (_a, e0) in lst:
            if e0 in used:
                continue
            seq = [v0]
            v = v0
            e = e0
            ok = False
            while True:
                used.add(e)
                nxt_v = next(a for (a, ee) in out_e[v] if ee is e)
                v = nxt_v
                if v is v0:
                    ok = True
                    break
                seq.append(v)
                cand = [(a, ee) for (a, ee) in out_e.get(v, []) if ee not in used]
                if not cand:
                    break
                e = cand[0][1]
            if not ok:
                continue
            # split at repeated vertices
            stack = []
            pos = {}
            for w in seq:
                if w in pos:
                    k = pos[w]
                    sub = stack[k:]
                    if len(sub) >= 3:
                        loops.append((sub, True))
                    for q in sub[1:]:
                        pos.pop(q, None)
                    stack = stack[:k + 1]
                else:
                    pos[w] = len(stack)
                    stack.append(w)
            if len(stack) >= 3:
                loops.append((stack, True))
    return loops


def tps_fit(P, h, lam=1e-3, scale=0.1):
    """Thin-plate spline h = f(P) (P: N x 2) with smoothing lam. Returns an evaluator f(Q)."""
    P = np.asarray(P, float) / scale
    n = len(P)
    d = np.linalg.norm(P[:, None, :] - P[None, :, :], axis=2)
    with np.errstate(divide="ignore", invalid="ignore"):
        K = np.where(d > 0, d * d * np.log(np.maximum(d, 1e-12)), 0.0)
    A = np.zeros((n + 3, n + 3))
    A[:n, :n] = K + lam * np.eye(n)
    A[:n, n] = 1
    A[:n, n + 1:] = P
    A[n, :n] = 1
    A[n + 1:, :n] = P.T
    b = np.zeros(n + 3)
    b[:n] = h
    sol = np.linalg.lstsq(A, b, rcond=None)[0]
    w, a = sol[:n], sol[n:]

    def f(Q):
        Q = np.atleast_2d(np.asarray(Q, float)) / scale
        dq = np.linalg.norm(Q[:, None, :] - P[None, :, :], axis=2)
        with np.errstate(divide="ignore", invalid="ignore"):
            Kq = np.where(dq > 0, dq * dq * np.log(np.maximum(dq, 1e-12)), 0.0)
        return Kq @ w + a[0] + Q @ a[1:]
    return f


def basis(axis):
    a = Vector(axis).normalized()
    t = Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))
    e1 = t.cross(a).normalized()
    e2 = a.cross(e1).normalized()
    return a, e1, e2


def ring_samples(loop, radius, exclude=None):
    """Verts connected to the loop and within `radius` of it (excluding the loop itself)."""
    lp = np.array([v.co[:] for v in loop])
    ring = set()
    front = list(loop)
    seen = set(loop)
    while front:
        nxt = []
        for v in front:
            for e in v.link_edges:
                w = e.other_vert(v)
                if w in seen:
                    continue
                seen.add(w)
                if np.min(np.linalg.norm(lp - np.array(w.co[:]), axis=1)) > radius:
                    continue
                if exclude is not None and exclude(w):
                    continue
                ring.add(w)
                nxt.append(w)
        front = nxt
    return ring


def _chk(loop, what):
    bad = [i for i, v in enumerate(loop) if not v.is_valid]
    if bad:
        raise RuntimeError(f"{what}: {len(bad)} loop verts removed")


def _point_in_poly(pts, poly):
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cond = (y0 > y) != (y1 > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
        inside ^= cond & (x < xi)
    return inside


def _dist_to_poly(pts, poly):
    d = np.full(len(pts), 1e9)
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        ab = b - a
        t = np.clip(((pts - a) @ ab) / max(ab @ ab, 1e-18), 0, 1)
        q = a + t[:, None] * ab
        d = np.minimum(d, np.linalg.norm(pts - q, axis=1))
    return d


def _simple_fill(bm, loop, a, uvl, uv_pin, patch_layer, patch_id):
    """Fallback: plain n-gon fill + beauty triangulation (no interior verts)."""
    vs = []
    for v in loop:
        if v not in vs:
            vs.append(v)
    if len(vs) < 3:
        return []
    try:
        f0 = bm.faces.new(vs)
    except ValueError:
        return []
    tri = bmesh.ops.triangulate(bm, faces=[f0], quad_method="BEAUTY", ngon_method="BEAUTY")
    patch = [f_ for f_ in tri["faces"] if f_.is_valid] or ([f0] if f0.is_valid else [])
    for f_ in patch:
        f_.smooth = True
        f_.normal_update()
        if f_.normal.dot(a) < 0:
            f_.normal_flip()
        for l_ in f_.loops:
            l_[uvl].uv = uv_pin
        if patch_layer is not None:
            f_[patch_layer] = patch_id
    return patch


def fill_loop_tps(bm, loop, axis, uv_pin, ring_radius=0.035, edge_len=0.010, lam=2e-3, exclude=None,
                  patch_layer=None, patch_id=1, extra_samples=None, mode="membrane", bulge=0.0):
    """Close one boundary loop with a new triangulated patch whose height along `axis` continues the surrounding
    surface (thin-plate spline through a ring of verts within ring_radius of the loop, plus a harmonic correction
    so it meets the loop exactly). The patch is a constrained Delaunay triangulation of the loop (projected on the
    plane normal to axis) plus a grid of interior points. New faces take UV `uv_pin` (one clean texel), face +axis."""
    from mathutils.geometry import delaunay_2d_cdt
    a, e1, e2 = basis(axis)
    uvl = bm.loops.layers.uv.active
    _chk(loop, "start")
    if len(loop) <= 4 or len(set(loop)) < len(loop):
        return _simple_fill(bm, loop, a, uvl, uv_pin, patch_layer, patch_id)

    def proj(co):
        return np.array([co.dot(e1), co.dot(e2), co.dot(a)])

    ring = ring_samples(loop, ring_radius, exclude)
    samples = [v for v in ring if v.normal.dot(a) > 0.15] + list(loop)
    S = np.array([proj(v.co) for v in samples])
    if extra_samples is not None and len(extra_samples):
        S = np.vstack([S, np.array([proj(Vector(p)) for p in extra_samples])])
    if len(S) > 900:
        S = S[np.linspace(0, len(S) - 1, 900).astype(int)]
    f = tps_fit(S[:, :2], S[:, 2], lam=lam)
    L = np.array([proj(v.co) for v in loop])
    poly = L[:, :2]
    # interior grid (hex), kept inside the polygon and away from its edges
    lo, hi = poly.min(0), poly.max(0)
    pts = []
    row = 0
    yv = lo[1] + edge_len * 0.5
    while yv < hi[1]:
        xo = (edge_len * 0.5) if row % 2 else 0.0
        xs = np.arange(lo[0] + xo, hi[0], edge_len)
        pts += [(xx, yv) for xx in xs]
        yv += edge_len * 0.866
        row += 1
    pts = np.array(pts) if pts else np.zeros((0, 2))
    if len(pts):
        keep = _point_in_poly(pts, poly) & (_dist_to_poly(pts, poly) > edge_len * 0.55)
        pts = pts[keep]
    nl = len(loop)
    coords = [Vector((p[0], p[1])) for p in poly] + [Vector((p[0], p[1])) for p in pts]
    cons = [(i, (i + 1) % nl) for i in range(nl)]
    out = delaunay_2d_cdt(coords, cons, [list(range(nl))], 1, 1e-7, True)
    vco, _e, faces, orig_v = out[0], out[1], out[2], out[3]
    # map output verts -> bm verts
    vmap = {}
    newverts = []
    for k, ov in enumerate(orig_v):
        src = [i for i in ov if i < len(coords)]
        if src and src[0] < nl:
            vmap[k] = loop[src[0]]
        else:
            nv = bm.verts.new((0, 0, 0))
            vmap[k] = nv
            newverts.append((nv, np.array(vco[k][:2])))
    patch = []
    for fc in faces:
        vs = [vmap[k] for k in fc]
        if len(set(vs)) < 3:
            continue
        try:
            patch.append(bm.faces.new(vs))
        except ValueError:
            pass
    inner = [nv for nv, _ in newverts]
    P = np.array([p for _, p in newverts]).reshape(-1, 2)
    allv = inner + list(loop)
    aidx = {v: i for i, v in enumerate(allv)}
    Pall = np.vstack([P, poly])
    nbr = [[aidx[e.other_vert(v)] for e in v.link_edges if e.other_vert(v) in aidx] for v in inner]
    ni = len(inner)
    for _ in range(40):
        for i, nb in enumerate(nbr):
            if nb:
                Pall[i] = Pall[nb].mean(0)
    r = np.zeros(len(allv))
    if mode != "membrane":
        r[ni:] = L[:, 2] - f(poly)
        for _ in range(600):
            for i, nb in enumerate(nbr):
                if nb:
                    r[i] = r[nb].mean()
    if mode == "membrane":
        # harmonic interpolation of the loop heights (no overshoot) + a scaled Poisson bulge (gentle convexity)
        ei = np.array([i for i, nb in enumerate(nbr) for _ in nb], np.int64)
        ej = np.array([j for nb in nbr for j in nb], np.int64)
        deg = np.array([max(len(nb), 1) for nb in nbr], float)
        hgt = np.zeros(len(allv))
        hgt[ni:] = L[:, 2]
        hgt[:ni] = L[:, 2].mean()
        bl = np.zeros(len(allv))
        for _ in range(2500):
            sh = np.zeros(ni)
            sb = np.zeros(ni)
            np.add.at(sh, ei, hgt[ej])
            np.add.at(sb, ei, bl[ej])
            hgt[:ni] = sh / deg
            bl[:ni] = sb / deg + 1.0
        if ni and bl[:ni].max() > 0:
            bl /= bl[:ni].max()
        hi_ = hgt[:ni] + bulge * bl[:ni]
    else:
        hi_ = f(Pall[:ni]) + r[:ni] if ni else np.zeros(0)
    for i, v in enumerate(inner):
        v.co = e1 * Pall[i, 0] + e2 * Pall[i, 1] + a * hi_[i]
    for f_ in patch:
        f_.smooth = True
        f_.normal_update()
        if f_.normal.dot(a) < 0:
            f_.normal_flip()
        for l_ in f_.loops:
            l_[uvl].uv = uv_pin
        if patch_layer is not None:
            f_[patch_layer] = patch_id
    if len(patch) < nl - 2:
        log(f"  warning: only {len(patch)} faces for a {nl}-loop -> simple fill")
        for f_ in patch:
            bm.faces.remove(f_)
        for v in inner:
            if v.is_valid and not v.link_faces:
                bm.verts.remove(v)
        return _simple_fill(bm, loop, a, uvl, uv_pin, patch_layer, patch_id)
    log(f"  filled loop of {nl} verts: {len(patch)} faces, {ni} new verts, {len(S)} ring samples")
    return patch


def find_clean_uv(bm, px, pred, near, k=3):
    """UV of a texel whose (2k+1)^2 neighbourhood satisfies pred(rgb array), on a vertex near world point `near`."""
    uvl = bm.loops.layers.uv.active
    h, w = px.shape[:2]
    cands = sorted(bm.verts, key=lambda v: (v.co - Vector(near)).length)[:800]
    for v in cands:
        for lp_ in v.link_loops:
            uv = lp_[uvl].uv
            x, y = int(uv.x * w), int(uv.y * h)
            blk = px[max(y - k, 0):y + k + 1, max(x - k, 0):x + k + 1, :3].reshape(-1, 3)
            if len(blk) == (2 * k + 1) ** 2 and np.all(pred(blk)):
                return uv.copy(), px[y, x, :3].copy()
    raise RuntimeError(f"no clean texel near {tuple(near)}")


def is_ivory(c):
    c = np.asarray(c)
    return (c.min(-1) > 0.72) & (c.max(-1) - c.min(-1) < 0.10)
