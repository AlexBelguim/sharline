"""Parametric stylized FEMALE BASE BODY generator for headless Blender 5.2.

    import sys; sys.path.insert(0, r"F:/git/val etf/tools")
    import female_base as fb
    res = fb.build_female_base(prefix="KES", height=1.70, build=0.0)

How it works
------------
1.  A recipe (pure numpy) describes the body as an ordered list of signed-distance primitives
    (ellipsoids, tapered capsules, rounded boxes, eyelid shells) combined with smooth union /
    smooth subtraction.  Everything is built in a 1.70 m reference frame and scaled to `height`;
    `build` (0 lean .. 1 strong) widens shoulders, limbs, neck, jaw.
2.  The SDF is polygonised with a sparse (narrow band) naive surface-nets mesher.
3.  The mesh is temporarily *warped* (head and hands enlarged) so that QuadriFlow, which makes
    uniform quads, spends more quads on the face and fingers.  After the remesh every vertex is
    mapped back through the inverse warp (Newton), snapped onto the exact SDF surface and relaxed.
4.  Eyes (sclera/iris/pupil spheres) and eyebrow strips are generated as separate objects.
Result: one watertight, symmetric, all-quad body mesh with UVs, A-pose, feet on Z=0, facing -Y.
"""
import math
import os
import sys
import time

import numpy as np

import bmesh
import bpy
from mathutils import Vector, kdtree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_common as bc  # noqa: E402

REF_H = 1.70
BIG = 1.0


# ============================================================================ small math helpers
def _a(*v):
    return np.array(v[0] if len(v) == 1 else v, dtype=np.float64)


def _unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def _lerp(a, b, t):
    return a + (b - a) * t


def _basis(z_axis, y_hint=(0, -1, 0)):
    """3x3 matrix whose columns are an orthonormal frame with column 2 == z_axis."""
    z = _unit(z_axis)
    y = np.asarray(y_hint, float)
    x = np.cross(y, z)
    if np.linalg.norm(x) < 1e-6:
        x = np.cross((1, 0, 0), z)
    x = _unit(x)
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=1)


def _rot(axis, deg):
    """Rotation matrix about `axis` by `deg` degrees."""
    ax = _unit(axis)
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    x, y, z = ax
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def _nrm(q):
    return np.sqrt(np.einsum("ij,ij->i", q, q))


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


MIRROR = np.diag([-1.0, 1.0, 1.0])


# ============================================================================ SDF primitives
class Prim:
    lo = hi = None

    def mirror(self):
        raise NotImplementedError


class Ellipsoid(Prim):
    """Ellipsoid with radii r along the columns of R (iq's approximate distance)."""

    def __init__(self, c, r, R=None):
        self.c = _a(c)
        self.r = _a(r)
        self.R = np.eye(3) if R is None else np.asarray(R, float)
        ext = np.abs(self.R) @ self.r
        self.lo, self.hi = self.c - ext, self.c + ext

    def __call__(self, P):
        q = (P - self.c) @ self.R
        k0 = _nrm(q / self.r)
        k1 = _nrm(q / (self.r * self.r))
        d = k0 * (k0 - 1.0) / np.maximum(k1, 1e-12)
        return np.where(k1 < 1e-9, -self.r.min(), d)

    def mirror(self):
        return Ellipsoid(self.c * [-1, 1, 1], self.r, MIRROR @ self.R)


class Sphere(Prim):
    def __init__(self, c, r):
        self.c, self.r = _a(c), float(r)
        self.lo, self.hi = self.c - self.r, self.c + self.r

    def __call__(self, P):
        return _nrm(P - self.c) - self.r

    def mirror(self):
        return Sphere(self.c * [-1, 1, 1], self.r)


class ConeSphere(Prim):
    """Sphere around c limited to a cone of half-angle `deg` about axis f (front cap of a sphere)."""

    def __init__(self, c, r, f, deg, k=0.002):
        self.c, self.r, self.f, self.deg, self.k = _a(c), float(r), _unit(f), float(deg), k
        self.cone = math.radians(deg)
        self.lo, self.hi = self.c - self.r, self.c + self.r

    def __call__(self, P):
        q = P - self.c
        rad = _nrm(q)
        ang = np.arccos(np.clip((q @ self.f) / np.maximum(rad, 1e-9), -1, 1))
        return smax(rad - self.r, (ang - self.cone) * self.r, self.k)

    def mirror(self):
        return ConeSphere(self.c * [-1, 1, 1], self.r, self.f * [-1, 1, 1], self.deg, self.k)


class RoundCone(Prim):
    """Tapered capsule between a (radius ra) and b (radius rb) - exact SDF (iq).
    Optional `squash`=(unit_dir, s): cross-section scaled by s along unit_dir (elliptic limbs)."""

    def __init__(self, a, b, ra, rb, squash=None):
        self.a, self.b, self.ra, self.rb = _a(a), _a(b), float(ra), float(rb)
        self.squash = None if squash is None else (_unit(squash[0]), float(squash[1]))
        m = max(ra, rb) * (1.0 if squash is None else max(1.0, squash[1]))
        self.lo = np.minimum(self.a, self.b) - m
        self.hi = np.maximum(self.a, self.b) + m
        ba = self.b - self.a
        self.ba = ba
        self.l2 = float(ba @ ba)
        self.rr = self.ra - self.rb
        self.a2 = self.l2 - self.rr * self.rr
        assert self.a2 > 0, "round cone radii difference larger than its length"

    def __call__(self, P):
        if self.squash is not None:
            u, s = self.squash
            P = P + np.outer(((P - self.a) @ u) * (1.0 / s - 1.0), u)
        pa = P - self.a
        y = pa @ self.ba
        z = y - self.l2
        xv = pa * self.l2 - np.outer(y, self.ba)
        x2 = np.einsum("ij,ij->i", xv, xv)
        y2 = y * y * self.l2
        z2 = z * z * self.l2
        il2 = 1.0 / self.l2
        k = math.copysign(1.0, self.rr) * self.rr * self.rr * x2
        d1 = np.sqrt(x2 + z2) * il2 - self.rb
        d2 = np.sqrt(x2 + y2) * il2 - self.ra
        d3 = (np.sqrt(np.maximum(x2 * self.a2 * il2, 0.0)) + y * self.rr) * il2 - self.ra
        return np.where(np.sign(z) * self.a2 * z2 > k, d1, np.where(np.sign(y) * self.a2 * y2 < k, d2, d3))

    def mirror(self):
        sq = None if self.squash is None else (self.squash[0] * [-1, 1, 1], self.squash[1])
        return RoundCone(self.a * [-1, 1, 1], self.b * [-1, 1, 1], self.ra, self.rb, sq)


class RoundBox(Prim):
    def __init__(self, c, half, R=None, r=0.0):
        self.c, self.half, self.r = _a(c), _a(half), float(r)
        self.R = np.eye(3) if R is None else np.asarray(R, float)
        ext = np.abs(self.R) @ self.half
        self.lo, self.hi = self.c - ext, self.c + ext

    def __call__(self, P):
        q = np.abs((P - self.c) @ self.R) - self.half + self.r
        return _nrm(np.maximum(q, 0.0)) + np.minimum(q.max(axis=1), 0.0) - self.r

    def mirror(self):
        return RoundBox(self.c * [-1, 1, 1], self.half, MIRROR @ self.R, self.r)


class EyeLid(Prim):
    """Spherical shell around an eyeball with an almond-shaped opening cut out of its front.

    Local frame: f = gaze, u = up, s = temporal side.  The opening is described in angles
    (alpha = horizontal, + toward the temple; beta = vertical) between an upper and a lower curve.
    """

    def __init__(self, c, f, u, s, r_in, thick, a_in, a_out, up_h, lo_h, beta_c, tilt, up_skew=-0.25,
                 lo_skew=0.25, cone_deg=78.0, round_k=0.0012):
        self.c = _a(c)
        self.f, self.u, self.s = _unit(f), _unit(u), _unit(s)
        self.r_in, self.thick = float(r_in), float(thick)
        self.a_in, self.a_out = a_in, a_out
        self.up_h, self.lo_h, self.beta_c, self.tilt = up_h, lo_h, beta_c, tilt
        self.up_skew, self.lo_skew = up_skew, lo_skew
        self.cone = math.radians(cone_deg)
        self.round_k = round_k
        rr = self.r_in + self.thick
        self.lo, self.hi = self.c - rr, self.c + rr

    def curves(self, al):
        """Upper and lower lid elevation (radians) at horizontal angle(s) `al`."""
        mid = 0.5 * (self.a_in + self.a_out)
        hw = 0.5 * (self.a_out - self.a_in)
        t = (np.asarray(al, float) - mid) / hw
        base = np.clip(1.0 - t * t, 0.0, None)
        upc = self.beta_c + self.tilt * t + self.up_h * base ** 0.75 * (1.0 + self.up_skew * t)
        loc = self.beta_c + self.tilt * t - self.lo_h * base ** 0.9 * (1.0 + self.lo_skew * t)
        return upc, loc

    def direction(self, al, be):
        return (np.cos(be) * (np.cos(al) * self.f + np.sin(al) * self.s) + np.sin(be) * self.u)

    def opening(self, P):
        """Positive inside the opening (in metres at the lid radius)."""
        q = P - self.c
        qf, qs, qu = q @ self.f, q @ self.s, q @ self.u
        al = np.arctan2(qs, qf)
        be = np.arctan2(qu, np.hypot(qs, qf))
        mid = 0.5 * (self.a_in + self.a_out)
        hw = 0.5 * (self.a_out - self.a_in)
        t = (al - mid) / hw
        base = np.clip(1.0 - t * t, 0.0, None)
        upc = self.beta_c + self.tilt * t + self.up_h * base ** 0.75 * (1.0 + self.up_skew * t)
        loc = self.beta_c + self.tilt * t - self.lo_h * base ** 0.9 * (1.0 + self.lo_skew * t)
        g = np.minimum(np.minimum(upc - be, be - loc), (1.0 - np.abs(t)) * hw)
        return g * self.r_in

    def __call__(self, P):
        q = P - self.c
        rad = _nrm(q)
        shell = np.abs(rad - (self.r_in + 0.5 * self.thick)) - 0.5 * self.thick
        ang = np.arccos(np.clip((q @ self.f) / np.maximum(rad, 1e-9), -1, 1))
        cone = (ang - self.cone) * self.r_in
        d = smax(shell, self.opening(P), self.round_k)
        return smax(d, cone, 0.002)

    def mirror(self):
        return EyeLid(self.c * [-1, 1, 1], self.f * [-1, 1, 1], self.u * [-1, 1, 1], self.s * [-1, 1, 1],
                      self.r_in, self.thick, self.a_in, self.a_out, self.up_h, self.lo_h, self.beta_c,
                      self.tilt, self.up_skew, self.lo_skew, math.degrees(self.cone), self.round_k)


def _catmull(tab, s):
    """Uniform Catmull-Rom spline through tab[0..n-1] evaluated at float index s (clamped)."""
    n = len(tab)
    s = np.clip(s, 0.0, n - 1.000001)
    i = np.floor(s).astype(int)
    t = s - i
    p0 = tab[np.clip(i - 1, 0, n - 1)]
    p1 = tab[i]
    p2 = tab[np.clip(i + 1, 0, n - 1)]
    p3 = tab[np.clip(i + 2, 0, n - 1)]
    return 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)


class FaceLoft(Prim):
    """Face block lofted from height tables (head-local units, z up from the menton, face toward -y).

    Each horizontal section is a super-ellipse: half-width w(z) at y0(z), front depth y0 - yf(z),
    exponent n(z) (2 = round, higher = flatter face front); behind y0 an ellipse of depth d_back.
    The under-jaw is cut by a plane through `menton` and `gonion` (y, z)."""

    def __init__(self, origin, hs, z0, dz, w, yf, y0, n, d_back=0.06, menton=(-0.074, 0.0),
                 gonion=(-0.008, 0.034), top=0.205, k_jaw=0.008):
        self.o, self.hs = _a(origin), float(hs)
        self.z0, self.dz = z0, dz
        self.w, self.yf, self.y0, self.n = (np.asarray(t, float) for t in (w, yf, y0, n))
        self.d_back = d_back
        self.men = np.array(menton, float)
        dv = np.array(gonion, float) - self.men
        self.jn = np.array([dv[1], -dv[0]]) / np.linalg.norm(dv)  # (ny, nz) pointing down/forward
        if self.jn[1] > 0:
            self.jn = -self.jn
        self.top, self.k_jaw = top, k_jaw
        self.lo = self.o + self.hs * _a(-0.08, -0.11, -0.03)
        self.hi = self.o + self.hs * _a(0.08, 0.07, top + 0.02)

    def tables_at(self, z):
        s = (z - self.z0) / self.dz
        return (_catmull(self.w, s), _catmull(self.yf, s), _catmull(self.y0, s), _catmull(self.n, s))

    def __call__(self, P):
        q = (P - self.o) / self.hs
        w, yf, y0, n = self.tables_at(q[:, 2])
        u = q[:, 1] - y0
        d = np.where(u < 0, np.maximum(y0 - yf, 1e-3), self.d_back)
        ax = np.abs(q[:, 0]) / w
        au = np.abs(u) / d
        axn, aun = ax ** n, au ** n
        rho = np.maximum((axn + aun) ** (1.0 / n), 1e-4)
        gx = rho ** (1 - n) * ax ** (n - 1) / w
        gu = rho ** (1 - n) * au ** (n - 1) / d
        g = np.maximum(np.sqrt(gx * gx + gu * gu), 1e-3)
        f = (rho - 1.0) / g
        f = np.where(rho > 3, (rho - 1.0) * np.minimum(w, d), f)
        jaw = (q[:, 1] - self.men[0]) * self.jn[0] + (q[:, 2] - self.men[1]) * self.jn[1]
        f = smax(f, jaw, self.k_jaw)
        f = smax(f, q[:, 2] - self.top, 0.02)
        return f * self.hs

    def mirror(self):
        return self


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.maximum(k - np.abs(a - b), 0.0) / k
    return np.minimum(a, b) - h * h * k * 0.25


def smax(a, b, k):
    return -smin(-a, -b, k)


class Op:
    __slots__ = ("mode", "prim", "k", "tag")

    def __init__(self, mode, prim, k, tag=""):
        self.mode, self.prim, self.k, self.tag = mode, prim, float(k), tag


def _apply(f, mode, d, k):
    if mode == "u":
        return smin(f, d, k)
    if mode == "s":
        return smax(f, -d, k)
    return smax(f, d, k)


class Field:
    """Ordered smooth-CSG of primitives built in the 1.70 m reference frame, evaluated at `scale`."""

    def __init__(self, ops, scale=1.0, cell=0.0):
        self.ops = ops
        self.scale = float(scale)
        self.margin = 1.3 * max(op.k for op in ops) + 0.006 + 2 * cell
        self.lo = np.array([op.prim.lo for op in ops])
        self.hi = np.array([op.prim.hi for op in ops])

    def bounds(self):
        u = [i for i, op in enumerate(self.ops) if op.mode == "u"]
        return self.lo[u].min(0) * self.scale, self.hi[u].max(0) * self.scale

    def __call__(self, P, chunk=400000):
        P = np.asarray(P, dtype=np.float64)
        out = np.empty(len(P))
        for s0 in range(0, len(P), chunk):
            out[s0:s0 + chunk] = self._eval(P[s0:s0 + chunk])
        return out

    def _eval(self, P):
        Q = P / self.scale
        f = np.full(len(Q), BIG)
        m = self.margin
        for i, op in enumerate(self.ops):
            lo, hi = self.lo[i] - m, self.hi[i] + m
            inb = np.all((Q >= lo) & (Q <= hi), axis=1)
            idx = np.nonzero(inb)[0]
            if len(idx) == 0:
                continue
            f[idx] = _apply(f[idx], op.mode, op.prim(Q[idx]), op.k)
        return f * self.scale

    def grad(self, P, eps=2e-4):
        P = np.asarray(P, dtype=np.float64)
        g = np.zeros_like(P)
        for ax in range(3):
            d = np.zeros(3)
            d[ax] = eps
            g[:, ax] = (self(P + d) - self(P - d)) / (2 * eps)
        return g

    def project(self, P, iters=6, max_step=0.004):
        P = np.array(P, dtype=np.float64)
        for _ in range(iters):
            f = self(P)
            g = self.grad(P)
            gg = np.maximum(np.einsum("ij,ij->i", g, g), 1e-12)
            step = (f / gg)[:, None] * g
            ln = _nrm(step)
            sc = np.minimum(1.0, max_step / np.maximum(ln, 1e-12))
            P -= step * sc[:, None]
        return P

    def march(self, origin, direction, tmax=1.0, n=400):
        """Distance along a ray (from inside) to the surface (first sign change)."""
        o, d = _a(origin), _unit(direction)
        ts = np.linspace(0, tmax, n)
        f = self(o[None] + ts[:, None] * d[None])
        idx = np.nonzero((f[:-1] < 0) & (f[1:] >= 0))[0]
        if len(idx) == 0:
            return float("nan")
        i = idx[0]
        a, b = ts[i], ts[i + 1]
        for _ in range(30):
            mid = 0.5 * (a + b)
            if self(o[None] + mid * d[None])[0] < 0:
                a = mid
            else:
                b = mid
        return 0.5 * (a + b)


# ============================================================================ sparse surface nets
_CORNERS = [(dx, dy, dz) for dz in (0, 1) for dy in (0, 1) for dx in (0, 1)]  # index = dx + 2dy + 4dz
_EDGES = [(c, c | bit) for c in range(8) for bit in (1, 2, 4) if not c & bit]


def polygonize(field, h=0.002, B=16, log=print):
    """Narrow-band naive surface nets. Returns (V float64 (n,3), Q int64 (m,4)) quads, CCW outward."""
    t0 = time.time()
    lo, hi = field.bounds()
    lo = lo - 0.01
    hi = hi + 0.01
    bs = B * h
    xm = math.ceil(max(abs(lo[0]), abs(hi[0])) / bs) * bs  # symmetric about x = 0 (grid plane)
    O = np.array([-xm, lo[1], lo[2]])
    nb = np.array([int(round(2 * xm / bs)), math.ceil((hi[1] - lo[1]) / bs), math.ceil((hi[2] - lo[2]) / bs)])
    # coarse activity test at block centres
    bidx = np.indices(nb).reshape(3, -1).T
    centers = O + (bidx + 0.5) * bs
    fc = field(centers)
    half_diag = 0.5 * bs * math.sqrt(3)
    active = np.abs(fc) < 2.0 * half_diag + 3 * h
    blocks = bidx[active]
    nba = len(blocks)
    log(f"  polygonize: grid {nb * B} cells, {nba}/{len(bidx)} active blocks")
    lidx = np.indices((B + 1,) * 3).reshape(3, -1).T  # (B+1)^3 local point indices (x fastest last)
    F = np.full((nba, (B + 1) ** 3), BIG, dtype=np.float32)
    bmin_ref = (O + blocks * bs) / field.scale
    bmax_ref = bmin_ref + bs / field.scale
    m = field.margin
    for i, op in enumerate(field.ops):
        lo_o, hi_o = field.lo[i] - m, field.hi[i] + m
        sel = np.nonzero(np.all((bmax_ref >= lo_o) & (bmin_ref <= hi_o), axis=1))[0]
        for s0 in range(0, len(sel), 160):
            ch = sel[s0:s0 + 160]
            gi = (blocks[ch] * B)[:, None, :] + lidx[None]
            P = (O + gi.reshape(-1, 3) * h) / field.scale
            d = op.prim(P).reshape(len(ch), -1)
            F[ch] = _apply(F[ch].astype(np.float64), op.mode, d, op.k / 1.0) * 1.0
    F *= field.scale
    F = F.reshape(nba, B + 1, B + 1, B + 1)
    S = F < 0
    log(f"  polygonize: field {time.time() - t0:.1f}s")
    # ---- cell vertices
    cnt = np.zeros((nba, B, B, B), dtype=np.int8)
    for dx, dy, dz in _CORNERS:
        cnt += S[:, dx:dx + B, dy:dy + B, dz:dz + B]
    bi, ci, cj, ck = np.nonzero((cnt > 0) & (cnt < 8))
    vals = np.stack([F[bi, ci + dx, cj + dy, ck + dz] for dx, dy, dz in _CORNERS], axis=1).astype(np.float64)
    cpos = np.array(_CORNERS, dtype=np.float64)
    acc = np.zeros((len(bi), 3))
    num = np.zeros(len(bi))
    for c0, c1 in _EDGES:
        v0, v1 = vals[:, c0], vals[:, c1]
        cross = (v0 < 0) != (v1 < 0)
        t = np.where(cross, v0 / np.where(cross, v0 - v1, 1.0), 0.0)
        p = cpos[c0][None] + t[:, None] * (cpos[c1] - cpos[c0])[None]
        acc += np.where(cross[:, None], p, 0.0)
        num += cross
    gcell = blocks[bi] * B + np.stack([ci, cj, ck], axis=1)
    V = O + (gcell + acc / num[:, None]) * h
    NX, NY = int(nb[0] * B + 2), int(nb[1] * B + 2)

    def key(g):
        return (g[:, 0] + 1) + NX * ((g[:, 1] + 1) + NY * (g[:, 2] + 1))

    vkey = key(gcell)
    order = np.argsort(vkey)
    skey = vkey[order]
    # ---- quads from sign-changing edges
    quads = []
    base = S[:, :B, :B, :B]
    for axis in range(3):
        if axis == 0:
            other = S[:, 1:, :B, :B]
            offs = [(0, -1, -1), (0, 0, -1), (0, 0, 0), (0, -1, 0)]
        elif axis == 1:
            other = S[:, :B, 1:, :B]
            offs = [(-1, 0, -1), (-1, 0, 0), (0, 0, 0), (0, 0, -1)]
        else:
            other = S[:, :B, :B, 1:]
            offs = [(-1, -1, 0), (0, -1, 0), (0, 0, 0), (-1, 0, 0)]
        b, i, j, k = np.nonzero(base != other)
        inside = S[b, i, j, k]
        g = blocks[b] * B + np.stack([i, j, k], axis=1)
        cells = np.stack([key(g + np.array(o)) for o in offs], axis=1)
        cells[~inside] = cells[~inside][:, ::-1]
        quads.append(cells)
    qk = np.concatenate(quads)
    pos = np.searchsorted(skey, qk)
    pos = np.clip(pos, 0, len(skey) - 1)
    ok = np.all(skey[pos] == qk, axis=1)
    if (~ok).sum():
        log(f"  polygonize: WARNING dropped {(~ok).sum()} quads (inactive neighbour blocks)")
    Q = order[pos[ok]]
    log(f"  polygonize: {len(V)} verts {len(Q)} quads in {time.time() - t0:.1f}s")
    return V, Q


# ============================================================================ density warp
class Warp:
    """Smooth forward map that enlarges the head (above the neck) and the hands so a uniform
    remesher gives them more quads.  Inverse is solved numerically."""

    def __init__(self, z0, z1, s_head, y_head, hands, s_hand, fans=()):
        self.z0, self.z1, self.sh, self.yh = z0, z1, s_head, y_head
        self.hands = hands  # list of (center, axis, t1, r0, r1)
        self.sk = s_hand
        self.fans = fans  # list of (knuckle, dir, rot_axis, angle_rad, length, radius)

    def _fan(self, X):
        """Rotate each finger about its knuckle (smoothly weighted) so neighbouring fingers separate."""
        if not self.fans:
            return X
        n = len(X)
        wsum = np.full(n, 1e-9)
        acc = np.zeros_like(X)
        wpal = np.zeros(n)
        any_w = np.zeros(n)
        for K, d, ax, ang, ln, rad in self.fans:
            q = X - K
            t = q @ d
            tc = np.clip(t, 0.0, ln)
            dist = _nrm(q - np.outer(tc, d))
            g = np.exp(-(dist / rad) ** 2) * _smoothstep(-0.002, 0.025, t)
            if not g.any():
                continue
            c, s_ = math.cos(ang), math.sin(ang)
            # Rodrigues rotation of q about ax
            cr = np.cross(ax, q)
            qd = (q @ ax)[:, None] * ax[None]
            rq = q * c + cr * s_ + qd * (1 - c)
            acc += g[:, None] * (K + rq)
            wsum += g
            any_w = np.maximum(any_w, g)
        blend = np.clip(any_w * 1.8, 0.0, 1.0)
        rotated = acc / wsum[:, None]
        return X * (1 - blend[:, None]) + rotated * blend[:, None]

    def __call__(self, X):
        X = np.asarray(X, dtype=np.float64)
        Y = self._fan(X)
        for c, ax, t1, r0, r1 in self.hands:
            q = Y - c
            t = q @ ax
            perp = _nrm(q - np.outer(t, ax))
            w = _smoothstep(0.0, t1, t) * (1.0 - _smoothstep(r0, r1, perp))
            s = 1.0 + (self.sk - 1.0) * w
            Y = c + q * s[:, None]
        z = Y[:, 2]
        w = self.z1 - self.z0
        t = np.clip((z - self.z0) / w, 0, 1)
        s = 1.0 + (self.sh - 1.0) * t * t * (3 - 2 * t)
        integ = np.where(z <= self.z0, 0.0, np.where(z >= self.z1, 0.5 * w + (z - self.z1), w * (t ** 3 - 0.5 * t ** 4)))
        out = Y.copy()
        out[:, 0] = Y[:, 0] * s
        out[:, 1] = self.yh + (Y[:, 1] - self.yh) * s
        out[:, 2] = z + (self.sh - 1.0) * integ
        return out

    def inverse(self, Yt, X0, iters=12):
        X = np.array(X0, dtype=np.float64)
        eps = 1e-5
        for _ in range(iters):
            F0 = self(X)
            r = F0 - Yt
            J = np.zeros((len(X), 3, 3))
            for a in range(3):
                d = np.zeros(3)
                d[a] = eps
                J[:, :, a] = (self(X + d) - F0) / eps
            try:
                dx = np.linalg.solve(J, r[:, :, None])[:, :, 0]
            except np.linalg.LinAlgError:
                dx = r
            ln = _nrm(dx)
            dx *= np.minimum(1.0, 0.01 / np.maximum(ln, 1e-12))[:, None]
            X -= dx
        res = _nrm(self(X) - Yt)
        bad = res > 2e-4
        if bad.any():
            X[bad] = X0[bad]
        self.last_bad = int(bad.sum())
        return X


# ============================================================================ the recipe
DEFAULT_FACE = dict(
    eye_r=0.0146,        # eyeball radius (nominal 0.23 m head)
    eye_x=0.0325,        # half inter-pupil distance
    eye_z=0.111,         # eye height above chin
    eye_y=-0.0665,       # eye centre depth (face is -y)
    eye_open=1.0,        # opening height multiplier
    eye_tilt=0.06,       # outer-corner lift (radians)
    jaw_w=1.0,           # jaw width multiplier
    chin_w=1.0,
    cheek=1.0,           # cheekbone prominence
    nose_len=0.95,
    nose_w=1.0,
    lip_full=1.1,
    brow=1.0,            # brow-ridge prominence
)


class Recipe:
    def __init__(self):
        self.ops = []

    def add(self, prim, k, tag="", sym=False):
        self.ops.append(Op("u", prim, k, tag))
        if sym:
            self.ops.append(Op("u", prim.mirror(), k, tag))

    def sub(self, prim, k, tag="", sym=False):
        self.ops.append(Op("s", prim, k, tag))
        if sym:
            self.ops.append(Op("s", prim.mirror(), k, tag))


def make_recipe(build=0.0, face=None):
    """Returns (ops, joints, info) in the 1.70 m reference frame (joints for the +X side get _L)."""
    b = float(np.clip(build, 0.0, 1.0))

    def L(lean, strong):
        return lean + (strong - lean) * b

    fc = dict(DEFAULT_FACE)
    fc["jaw_w"] = L(1.0, 1.04)
    fc["chin_w"] = L(1.0, 1.06)
    fc["brow"] = L(1.0, 1.08)
    fc["nose_w"] = L(1.0, 1.05)
    fc["eye_open"] = L(1.0, 0.94)
    if face:
        fc.update(face)
    R = Recipe()
    J = {}
    info = {}
    H = REF_H
    # ------------------------------------------------------------------ skeleton (reference)
    hh = H / 7.5
    z_chin = H - hh
    hs = hh / 0.23
    yc = 0.020
    info.update(z_chin=z_chin, head_h=hh, hs=hs, yc=yc)

    def hp(x, y, z):
        return _a(x * hs, yc + y * hs, z_chin + z * hs)

    sh_w = L(0.168, 0.184)
    S = _a(sh_w, 0.012, 1.383)  # shoulder joint
    a = math.radians(42.0)
    d_ua = _a(math.cos(a), 0.0, -math.sin(a))
    n_up = _a(math.sin(a), 0.0, math.cos(a))
    E = S + 0.272 * d_ua
    d_fa = _unit(_rot(n_up, -8.0) @ d_ua)  # slight forward bend at the elbow
    Wr = E + 0.240 * d_fa
    hip = _a(L(0.086, 0.092), 0.0, 0.873)
    knee = _a(L(0.097, 0.104), -0.004, 0.476)
    ank = _a(L(0.104, 0.112), 0.022, 0.074)
    J.update(pelvis=_a(0, 0.004, 0.925), spine1=_a(0, 0.010, 1.005), spine2=_a(0, 0.016, 1.115),
             spine3=_a(0, 0.012, 1.240), neck=_a(0, 0.030, 1.405), head=_a(0, 0.032, z_chin + 0.03),
             head_top=_a(0, yc, H))
    J.update(clavicle_L=_a(0.022, -0.012, 1.392), upperarm_L=S, forearm_L=E, hand_L=Wr,
             thigh_L=hip, calf_L=knee, foot_L=ank)

    # ------------------------------------------------------------------ torso
    k_t = 0.045
    R.add(Ellipsoid((0, 0.016, 1.215), (L(0.124, 0.140), L(0.084, 0.093), 0.160)), 0.0, "ribcage")
    R.add(Ellipsoid((0, 0.006, 1.300), (L(0.142, 0.160), L(0.072, 0.080), 0.075)), k_t, "upperchest")
    # bust: modest, athletic, blended into one soft form (base for clothing)
    R.add(Ellipsoid((L(0.050, 0.055), -0.046, 1.226), (L(0.054, 0.058), 0.046, L(0.050, 0.053)), _basis((0.22, -1, -0.12), (0, 0, 1))), 0.05, "bust", sym=True)
    R.add(Ellipsoid((0, -0.050, 1.228), (0.040, 0.036, 0.050)), 0.04, "sternumfill")
    R.add(Ellipsoid((0, 0.006, 1.060), (L(0.123, 0.130), L(0.080, 0.086), 0.115)), k_t, "abdomen")
    R.add(Ellipsoid((0, -0.036, 1.015), (0.082, 0.045, 0.080)), 0.04, "belly")
    R.add(Ellipsoid((0, 0.012, 0.920), (L(0.123, 0.134), L(0.092, 0.097), 0.100)), k_t, "pelvis")
    R.add(Ellipsoid((L(0.080, 0.084), 0.010, 0.890), (L(0.045, 0.049), 0.060, 0.068)), 0.04, "hipflare", sym=True)
    R.add(Ellipsoid((0.058, 0.052, 0.862), (0.061, 0.054, 0.074)), 0.035, "glute", sym=True)
    R.add(Ellipsoid((0.072, 0.072, 1.265), (0.050, 0.026, 0.066), _basis((0.2, 0, 1), (0, -1, 0))), 0.035, "scapula", sym=True)
    R.add(Ellipsoid((0.102, 0.034, 1.185), (L(0.046, 0.052), 0.062, 0.105)), 0.04, "lat", sym=True)
    R.sub(RoundCone((0, 0.112, 0.98), (0, 0.112, 1.34), 0.010, 0.010), 0.03, "spinegroove")
    # neck + trapezius + clavicles
    nb_r, nt_r = L(0.043, 0.052), L(0.0395, 0.0475)
    R.add(RoundCone((0, 0.046, 1.37), hp(0, 0.008, 0.042), nb_r, nt_r), 0.03, "neck")
    R.add(Ellipsoid((0, 0.020, 1.362), (L(0.150, 0.164), 0.064, 0.046)), 0.04, "girdle")
    R.add(RoundCone((0.0, 0.050, 1.420), (S[0] - 0.012, 0.018, 1.400), L(0.030, 0.034), L(0.025, 0.028)), 0.045, "trap", sym=True)
    R.add(RoundCone((0.026, -0.036, 1.378), (S[0] - 0.030, -0.010, 1.398), 0.0050, 0.0055), 0.02, "clavicle", sym=True)

    # ------------------------------------------------------------------ arms (+X, mirrored)
    def arm():
        ops = []
        side = _unit(np.cross(d_ua, (0, -1, 0)))  # = n_up-ish
        # deltoid
        ops.append((Ellipsoid(S + 0.030 * d_ua + 0.010 * n_up,
                              (L(0.058, 0.065), L(0.056, 0.062), 0.082), _basis(d_ua, (0, -1, 0))), 0.035, "deltoid"))
        ops.append((RoundCone(S - 0.005 * d_ua, E, L(0.045, 0.056), L(0.034, 0.041), squash=((0, 1, 0), 0.95)), 0.03, "upperarm"))
        ops.append((Ellipsoid(S + 0.15 * d_ua + _a(0, -0.014, 0) - 0.004 * n_up,
                              (L(0.030, 0.038), L(0.030, 0.038), 0.080), _basis(d_ua, (0, -1, 0))), 0.025, "biceps"))
        ops.append((Ellipsoid(S + 0.12 * d_ua + _a(0, 0.016, 0) + 0.004 * n_up,
                              (L(0.032, 0.040), L(0.032, 0.040), 0.085), _basis(d_ua, (0, -1, 0))), 0.025, "triceps"))
        # axillary folds (front: pec -> arm, back: lat -> arm)
        ops.append((RoundCone(_a(0.085, -0.050, 1.290), S + 0.075 * d_ua + _a(0, -0.012, 0), 0.026, 0.020), 0.045, "pecfold"))
        ops.append((RoundCone(_a(0.095, 0.060, 1.250), S + 0.075 * d_ua + _a(0, 0.016, 0), 0.028, 0.020), 0.045, "latfold"))
        ops.append((Ellipsoid(_a(S[0] - 0.040, 0.016, S[2] - 0.105), (0.030, L(0.044, 0.050), 0.040)), 0.04, "axilla"))
        ops.append((Sphere(E + 0.004 * n_up + _a(0, 0.006, 0), L(0.031, 0.037)), 0.02, "elbow"))
        ops.append((RoundCone(E, Wr, L(0.034, 0.041), L(0.023, 0.026), squash=((0, 1, 0), 1.18)), 0.02, "forearm"))
        ops.append((Ellipsoid(E + 0.065 * d_fa + 0.004 * n_up, (L(0.036, 0.044), L(0.034, 0.040), 0.075),
                              _basis(d_fa, (0, -1, 0))), 0.02, "forearm_mass"))
        return ops

    for prim, k, tag in arm():
        R.add(prim, k, tag, sym=True)

    # ------------------------------------------------------------------ hand (+X, mirrored)
    X_h = d_fa
    T0 = _a(0, -1, 0)
    T = _unit(T0 - (T0 @ X_h) * X_h)          # thumb side
    D = np.cross(T, X_h)                      # dorsal (back of hand)
    hsc = L(1.07, 1.12)

    def hpt(u, v, w):
        return Wr + hsc * (u * X_h + v * T + w * D)

    Rh = np.stack([X_h, T, D], axis=1)
    R.add(RoundBox(hpt(0.046, 0.000, 0.001), np.array((0.040, 0.037, 0.0135)) * hsc, Rh, 0.0115 * hsc), 0.018, "palm", sym=True)
    R.add(Ellipsoid(hpt(0.050, 0.000, 0.006), np.array((0.045, 0.036, 0.012)) * hsc, Rh), 0.012, "handback", sym=True)
    R.add(Ellipsoid(hpt(0.034, 0.020, -0.008), np.array((0.030, 0.017, 0.013)) * hsc, Rh), 0.012, "thenar", sym=True)
    R.add(Ellipsoid(hpt(0.045, -0.026, -0.006), np.array((0.035, 0.012, 0.011)) * hsc, Rh), 0.010, "hypothenar", sym=True)
    fingers = [  # name, v, u_knuckle, lengths, r0, r1, spread(deg)
        ("index", 0.0280, 0.088, (0.038, 0.023, 0.019), 0.0079, 0.0070, 10.0),
        ("middle", 0.0094, 0.091, (0.042, 0.026, 0.020), 0.0081, 0.0072, 2.0),
        ("ring", -0.0094, 0.088, (0.039, 0.024, 0.019), 0.0077, 0.0068, -6.5),
        ("pinky", -0.0280, 0.081, (0.030, 0.019, 0.017), 0.0068, 0.0060, -15.0),
    ]
    curl = (12.0, 16.0, 12.0)
    fan_extra = {"index": 30.0, "middle": 10.0, "ring": -10.0, "pinky": -30.0}
    info["fans"] = []
    for name, v, u0, lens, r0, r1, spread in fingers:
        p = hpt(u0, v, 0.0015)
        d = _rot(D, spread) @ X_h
        info["fans"].append((p.copy(), d.copy(), _unit(D), math.radians(fan_extra[name]), sum(lens) * hsc, 0.0125))
        J[f"{name}_01_L"] = p
        rr = np.linspace(r0, r1, 4) * hsc
        for si, ln in enumerate(lens):
            d = _rot(np.cross(d, D), curl[si]) @ d  # flex toward palm
            q = p + d * ln * hsc
            R.add(RoundCone(p, q, rr[si], rr[si + 1], squash=(D, 0.92)), 0.0025 if si else 0.004, f"{name}{si}", sym=True)
            p = q
            if si < 2:
                J[f"{name}_{si + 2:02d}_L"] = p
        J[f"{name}_tip_L"] = p
    # thumb
    p = hpt(0.016, 0.024, -0.006)
    d = _unit(0.62 * X_h + 0.62 * T - 0.42 * D)
    J["thumb_01_L"] = p
    for si, (ln, ra, rb) in enumerate([(0.037, 0.0122, 0.0104), (0.028, 0.0102, 0.0096), (0.022, 0.0094, 0.0088)]):
        q = p + d * ln * hsc
        R.add(RoundCone(p, q, ra * hsc, rb * hsc), 0.010 if si == 0 else 0.004, f"thumb{si}", sym=True)
        p = q
        d = _unit(_rot(np.cross(d, X_h), -9.0) @ d)
        if si < 2:
            J[f"thumb_{si + 2:02d}_L"] = p
    J["thumb_tip_L"] = p
    info["hand_axes"] = (X_h, T, D)

    # ------------------------------------------------------------------ legs (+X, mirrored)
    d_th = _unit(knee - hip)
    d_sh = _unit(ank - knee)
    Rth = _basis(d_th, (0, -1, 0))
    Rsh = _basis(d_sh, (0, -1, 0))
    leg = []
    leg.append((RoundCone(hip + _a(0.002, 0.004, 0.0), knee + _a(0, 0, 0.02), L(0.077, 0.088), L(0.055, 0.061)), 0.05, "thigh"))
    leg.append((Ellipsoid(_lerp(hip, knee, 0.42) + _a(0.008, -0.026, 0), (L(0.046, 0.052), L(0.042, 0.048), 0.165), Rth), 0.03, "quads"))
    leg.append((Ellipsoid(_lerp(hip, knee, 0.45) + _a(0.0, 0.028, 0), (L(0.048, 0.054), L(0.040, 0.046), 0.16), Rth), 0.03, "hamstring"))
    leg.append((Ellipsoid(knee + _a(-0.014, -0.016, 0.085), (0.027, 0.025, 0.050), Rth), 0.03, "vmo"))
    leg.append((Ellipsoid(_a(0.068, 0.004, 0.805), (0.036, 0.050, 0.075), _basis(d_th, (0, -1, 0))), 0.03, "adductor"))
    leg.append((Sphere(knee + _a(0, 0.002, 0.005), L(0.044, 0.049)), 0.05, "knee"))
    leg.append((Ellipsoid(knee + _a(0, -0.040, 0.010), (0.021, 0.012, 0.025)), 0.016, "patella"))
    leg.append((RoundCone(knee, ank, L(0.052, 0.058), L(0.030, 0.033)), 0.03, "shin"))
    leg.append((Ellipsoid(knee + _a(-0.012, 0.030, -0.118), (L(0.033, 0.038), L(0.036, 0.040), 0.090), Rsh), 0.025, "calf_med"))
    leg.append((Ellipsoid(knee + _a(0.013, 0.027, -0.102), (L(0.029, 0.034), L(0.032, 0.036), 0.078), Rsh), 0.025, "calf_lat"))
    leg.append((Sphere(ank, 0.033), 0.02, "ankle"))
    # foot
    heel = _a(ank[0], 0.046, 0.040)
    ball = _a(ank[0] + 0.006, -0.100, 0.026)
    toe = _a(ank[0] + 0.010, -0.136, 0.022)
    leg.append((Ellipsoid(heel, (0.031, 0.036, 0.040)), 0.02, "heel"))
    leg.append((RoundCone(_a(ank[0], 0.020, 0.055), ball, 0.040, 0.026, squash=((1, 0, 0), 1.3)), 0.025, "foot"))
    leg.append((Ellipsoid(toe + _a(0, 0.010, 0.001), (0.040, 0.034, 0.023)), 0.016, "toes"))
    for prim, k, tag in leg:
        R.add(prim, k, tag, sym=True)
    J.update(toe_L=ball, toe_end_L=toe + _a(0, -0.02, 0), heel_L=heel)
    R.add(Ellipsoid((0, 0.004, 0.815), (0.032, 0.050, 0.032)), 0.03, "crotchfill")

    # ------------------------------------------------------------------ head
    # nominal 0.23 m head: z measured up from the menton (chin bottom), y from the ear canal (face -y)
    jw, cw, ck = fc["jaw_w"], fc["chin_w"], fc["cheek"]

    def HE(c, r, Rm=None):
        return Ellipsoid(hp(*c), np.array(r) * hs, Rm)

    def HC(a_, b_, ra, rb):
        return RoundCone(hp(*a_), hp(*b_), ra * hs, rb * hs)

    def HS(c, r):
        return Sphere(hp(*c), r * hs)

    R.add(HE((0, 0.000, 0.138), (0.070, 0.087, 0.092)), 0.0, "cranium")
    R.add(HE((0, 0.014, 0.155), (0.0725, 0.070, 0.074)), 0.03, "parietal")
    # lofted face block: knots every 15 mm from z = -0.015
    w_t = np.array([0.015, 0.018, 0.029, 0.041, 0.050, 0.058, 0.0625, 0.0645, 0.0655, 0.0665, 0.068, 0.069, 0.069, 0.066, 0.059, 0.048])
    w_t[:6] *= np.array([1.0, cw, _lerp(cw, jw, 0.5), jw, jw, _lerp(jw, 1.0, 0.5)])
    yf_t = np.array([-0.054, -0.077, -0.0915, -0.0885, -0.0855, -0.0865, -0.0870, -0.0855, -0.084, -0.085, -0.091, -0.092, -0.088, -0.078, -0.066, -0.050])
    y0_t = np.array([-0.040, -0.045, -0.040, -0.020, -0.012, -0.015, -0.020, -0.025, -0.025, -0.022, -0.016, -0.010, -0.006, -0.005, -0.005, -0.005])
    n_t = np.array([2.0, 2.0, 2.05, 2.2, 2.45, 2.6, 2.6, 2.6, 2.6, 2.6, 2.6, 2.6, 2.5, 2.4, 2.3, 2.2])
    loft = FaceLoft(hp(0, 0, 0), hs, -0.015, 0.015, w_t, yf_t, y0_t, n_t, top=0.205)
    R.add(loft, 0.012, "faceloft")
    info["face_loft"] = loft
    R.add(HE((0, -0.0805, 0.016), (0.017 * cw, 0.012, 0.013)), 0.010, "chin")
    R.add(HE((0.037, -0.058, 0.064), (0.024, 0.022, 0.026)), 0.016, "cheekfill", sym=True)
    R.add(HE((0.049 * ck, -0.054, 0.097), (0.016, 0.019, 0.012), _basis((0.45, -1, 0), (0, 0, 1))), 0.014, "cheekbone", sym=True)
    br = fc["brow"]
    R.add(HC((0.010, -0.0855, 0.138), (0.046, -0.0755, 0.141), 0.0055 * br, 0.0045 * br), 0.010, "brow", sym=True)
    # nose
    nl, nw = fc["nose_len"], fc["nose_w"]
    tip = (0.0, -0.1050, 0.120 - 0.0455 * nl)
    R.add(HC((0, -0.0790, 0.122), (0, -0.0915, tip[2] + 0.006), 0.0062 * nw, 0.0118 * nw), 0.007, "nosebody")
    R.add(HC((0, -0.0835, 0.122), (0, -0.1000, tip[2] + 0.012), 0.0042, 0.0048), 0.004, "nosebridge")
    R.add(HS(tip, 0.0082), 0.005, "nosetip")
    R.add(HS((0.0094 * nw, tip[1] + 0.0098, tip[2] - 0.0040), 0.0060 * nw), 0.0045, "ala", sym=True)
    R.add(HC((0, tip[1] + 0.004, tip[2] - 0.0045), (0, -0.0890, tip[2] - 0.0085), 0.0036, 0.0036), 0.006, "columella")
    R.add(HE((0, -0.0860, tip[2] - 0.006), (0.012 * nw, 0.0060, 0.0075)), 0.009, "nosebase")
    # lips: bow-shaped upper lip (tubercle + two lobes), two-lobed lower lip
    lf = fc["lip_full"]
    zl = 0.0445
    Rul = _rot((0, 0, 1), 24.0) @ _rot((1, 0, 0), -16.0)
    Rll = _rot((0, 0, 1), 22.0) @ _rot((1, 0, 0), 14.0)
    R.add(HE((0, -0.0868, zl + 0.0135), (0.0110, 0.0058, 0.0095)), 0.006, "philtrumfill")
    R.add(HE((0.0102, -0.0868, zl + 0.0044), (0.0135, 0.0052 * lf, 0.0042 * lf), Rul), 0.005, "upperlip", sym=True)
    R.add(HS((0, -0.0888, zl + 0.0034), 0.0035 * lf), 0.004, "tubercle")
    R.add(HE((0.0080, -0.0860, zl - 0.0058), (0.0125, 0.0060 * lf, 0.0056 * lf), Rll), 0.005, "lowerlip", sym=True)
    R.sub(HE((0, -0.0965, zl), (0.0255, 0.0090, 0.0015)), 0.0022, "mouthline")
    R.sub(HS((0.0262, -0.0815, zl), 0.0030), 0.004, "mouthcorner", sym=True)
    R.sub(HE((0, -0.0905, 0.030), (0.012, 0.005, 0.004)), 0.006, "mentolabial")
    info["lip_prims"] = [op.prim for op in R.ops if op.tag in ("upperlip", "tubercle", "lowerlip")]
    info["mouth_prim"] = next(op.prim for op in R.ops if op.tag == "mouthline")
    # ears
    # ear frame: n = outward normal, u = toward the back, v = up (flared back 18 deg, tilted 12 deg)
    Re = _rot((0, 0, 1), -24.0) @ _rot((1, 0, 0), -12.0)
    en, eu, ev = Re[:, 0], Re[:, 1], Re[:, 2]
    ear0 = hp(0.066, -0.002, 0.100)

    def ept(u, v, n=0.0):
        return ear0 + (u * eu + v * ev + n * en) * hs

    R.add(Ellipsoid(ept(0.012, 0.003, 0.0035), np.array((0.0068, 0.0130, 0.0255)) * hs, Re), 0.006, "ear", sym=True)
    helix = [(0.002, 0.019), (0.006, 0.0255), (0.012, 0.0285), (0.018, 0.0280), (0.0228, 0.0240), (0.0252, 0.016),
             (0.0245, 0.006), (0.021, -0.004), (0.017, -0.012), (0.013, -0.019)]
    for i in range(len(helix) - 1):
        (u0, v0), (u1, v1) = helix[i], helix[i + 1]
        R.add(RoundCone(ept(u0, v0, 0.0055), ept(u1, v1, 0.0055), 0.0033 * hs, 0.0033 * hs), 0.003, "helix", sym=True)
    R.add(Ellipsoid(ept(0.012, -0.020, 0.004), np.array((0.0035, 0.0065, 0.0075)) * hs, Re), 0.004, "lobe", sym=True)
    R.sub(Ellipsoid(ept(0.011, 0.002, 0.0125), np.array((0.0072, 0.0092, 0.0155)) * hs, Re), 0.0025, "concha", sym=True)
    # eyes: carve around the eyeball, open the pocket, add the lids back as a shell with an almond cut
    er = fc["eye_r"] * hs
    ec = hp(fc["eye_x"], fc["eye_y"], fc["eye_z"])
    gaze = _unit(_a(0.0, -1.0, 0.0))
    thick = 0.0033 * hs
    r_in = er + 0.0004
    R.sub(ConeSphere(ec, r_in + thick + 0.0010, gaze, 76.0), 0.003, "eyecarve", sym=True)
    R.sub(Sphere(ec, r_in), 0.0008, "pocket", sym=True)
    lid = EyeLid(ec, gaze, (0, 0, 1), (1, 0, 0), r_in, thick,
                 a_in=math.radians(-68), a_out=math.radians(72),
                 up_h=math.radians(23) * fc["eye_open"], lo_h=math.radians(18) * fc["eye_open"],
                 beta_c=math.radians(1.5), tilt=fc["eye_tilt"], cone_deg=82.0)
    R.add(lid, 0.002, "lid", sym=True)
    info.update(eye_c=ec, eye_r=er, gaze=gaze, lid=lid, lip_c=hp(0, -0.088, zl), blush_c=hp(0.040, -0.072, 0.082))
    J["eye_L"] = ec
    # foot sole flatten (z >= 0)
    R.sub(RoundBox(_a(0.1, -0.04, -0.05), (0.12, 0.2, 0.05)), 0.006, "sole", sym=True)
    info.update(S=S, E=E, Wr=Wr, d_ua=d_ua, d_fa=d_fa, hip=hip, knee=knee, ank=ank, face=fc, hsc=hsc)
    # complete R side joints
    for k in list(J):
        if k.endswith("_L"):
            J[k[:-2] + "_R"] = J[k] * [-1, 1, 1]
    return R.ops, J, info


# ============================================================================ blender mesh utils
def _mesh_from_numpy(name, V, F):
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", np.asarray(V, dtype=np.float32).ravel())
    F = np.asarray(F)
    n, k = F.shape
    me.loops.add(n * k)
    me.loops.foreach_set("vertex_index", F.astype(np.int32).ravel())
    me.polygons.add(n)
    me.polygons.foreach_set("loop_start", np.arange(0, n * k, k, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    return me


def _get_verts(me):
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3).astype(np.float64)


def _set_verts(me, V):
    me.vertices.foreach_set("co", np.asarray(V, dtype=np.float32).ravel())
    me.update()


def _edges(me):
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def _relax(V, E, field, iters=3, lam=0.35, pin=None, midline=None):
    n = len(V)
    for _ in range(iters):
        acc = np.zeros_like(V)
        cnt = np.zeros(n)
        np.add.at(acc, E[:, 0], V[E[:, 1]])
        np.add.at(acc, E[:, 1], V[E[:, 0]])
        np.add.at(cnt, E[:, 0], 1)
        np.add.at(cnt, E[:, 1], 1)
        avg = acc / np.maximum(cnt, 1)[:, None]
        g = field.grad(V)
        nrm = g / np.maximum(_nrm(g), 1e-9)[:, None]
        dv = lam * (avg - V)
        dv -= np.einsum("ij,ij->i", dv, nrm)[:, None] * nrm
        if pin is not None:
            dv[pin] = 0
        if midline is not None:
            dv[midline, 0] = 0.0
        V = V + dv
        free = np.ones(n, bool) if pin is None else ~pin
        V[free] = field.project(V[free], iters=3)
        if midline is not None:
            V[midline, 0] = 0.0
    return V


def _weld_short_edges(me, dist, log=print):
    """QuadriFlow refuses meshes with any edge shorter than 1e-4 per axis: weld them away."""
    for it in range(4):
        bm = bmesh.new()
        bm.from_mesh(me)
        short = [e for e in bm.edges if (e.verts[0].co - e.verts[1].co).length < dist]
        if not short:
            bm.free()
            break
        verts = list({v for e in short for v in e.verts})
        bmesh.ops.remove_doubles(bm, verts=verts, dist=dist * 1.01)
        bmesh.ops.dissolve_degenerate(bm, dist=dist * 0.5, edges=bm.edges[:])
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        bm.to_mesh(me)
        bm.free()
        log(f"  welded {len(short)} short edges (pass {it}), non-manifold edges now {nm}")
    me.update()


def _quadriflow_symmetric(obj, target_faces, log=print):
    """Bisect at x = 0, QuadriFlow the +X half with its boundary preserved, mirror and weld.
    Gives an exactly mirror-symmetric, watertight all-quad mesh."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-6,
                           plane_co=(0, 0, 0), plane_no=(1, 0, 0), clear_inner=True)
    for v in bm.verts:
        if abs(v.co.x) < 1e-5:
            v.co.x = 0.0
    bm.to_mesh(me)
    bm.free()
    _weld_short_edges(me, 2.5e-4, log)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    snapshot = obj.data.copy()
    res = {"CANCELLED"}
    for seed in (0, 1, 2, 3):
        res = bpy.ops.object.quadriflow_remesh(use_mesh_symmetry=False, use_preserve_sharp=False,
                                               use_preserve_boundary=True, smooth_normals=False,
                                               mode="FACES", target_faces=max(100, target_faces // 2), seed=seed)
        if "FINISHED" in res and len(obj.data.polygons) < 2 * target_faces:
            break
        log(f"  quadriflow seed {seed} failed ({res}), retrying")
        obj.data = snapshot.copy()
    if "FINISHED" not in res:
        raise RuntimeError("QuadriFlow remesh failed")
    bpy.data.meshes.remove(snapshot)
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for v in bm.verts:
        if v.is_boundary and abs(v.co.x) < 2e-3:
            v.co.x = 0.0
    ret = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
    nv = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    nf = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMFace)]
    for v in nv:
        v.co.x = -v.co.x
    bmesh.ops.reverse_faces(bm, faces=nf)
    mid = [v for v in bm.verts if abs(v.co.x) < 1e-7]
    bmesh.ops.remove_doubles(bm, verts=mid, dist=1e-5)
    nb = sum(1 for e in bm.edges if e.is_boundary)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bad = [e for e in bm.edges if not e.is_manifold]
    if bad:
        log("    non-manifold after mirror at: " + str([tuple(round(c, 3) for c in ((e.verts[0].co + e.verts[1].co) * 0.5))
                                                     for e in bad[:8]]) + " faces/edge " + str([len(e.link_faces) for e in bad[:8]]))
        nb, nm = _repair_nonmanifold(bm, log)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.update()
    return nb, nm


def _repair_nonmanifold(bm, log=print, rings=1):
    """Delete the faces around non-manifold edges/verts (plus `rings` neighbours) and re-fill the hole."""
    for it in range(3):
        bad_e = [e for e in bm.edges if not e.is_manifold]
        bad_v = [v for v in bm.verts if not v.is_manifold]
        if not bad_e and not bad_v:
            break
        faces = set()
        for e in bad_e:
            faces.update(e.link_faces)
        for v in bad_v:
            faces.update(v.link_faces)
        for _ in range(rings + it):
            grow = set()
            for f in faces:
                for v in f.verts:
                    grow.update(v.link_faces)
            faces |= grow
        bmesh.ops.delete(bm, geom=list(faces), context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        loose_e = [e for e in bm.edges if not e.link_faces]
        if loose_e:
            bmesh.ops.delete(bm, geom=loose_e, context="EDGES")
        bnd = [e for e in bm.edges if e.is_boundary]
        res = bmesh.ops.holes_fill(bm, edges=bnd, sides=0)
        newf = res.get("faces", [])
        if newf:
            bmesh.ops.triangulate(bm, faces=newf, quad_method="BEAUTY", ngon_method="BEAUTY")
        log(f"    repaired: removed {len(faces)} faces, filled {len(newf)} holes")
    # merge any triangles produced into quads where possible
    tris = [f for f in bm.faces if len(f.verts) == 3]
    if tris:
        bmesh.ops.join_triangles(bm, faces=tris, angle_face_threshold=math.radians(40),
                                 angle_shape_threshold=math.radians(40))
    nb = sum(1 for e in bm.edges if e.is_boundary)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    return nb, nm


def _weld_midline(me):
    """Weld the open seam QuadriFlow's symmetry leaves on x = 0 by pairing each boundary vertex
    with its mirror partner. Returns (boundary edges, non-manifold edges) after welding."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bverts = list({v for e in bm.edges if e.is_boundary for v in e.verts})
    pos = [v for v in bverts if v.co.x >= 0]
    neg = [v for v in bverts if v.co.x < 0]
    targetmap = {}
    if pos and neg:
        kd = kdtree.KDTree(len(neg))
        for i, v in enumerate(neg):
            kd.insert(v.co, i)
        kd.balance()
        used = set()
        for v in sorted(pos, key=lambda v: v.co.x):
            m = Vector((-v.co.x, v.co.y, v.co.z))
            for co, i, d in kd.find_n(m, 3):
                if i not in used and d < 0.01:
                    used.add(i)
                    u = neg[i]
                    mid = (v.co + Vector((-u.co.x, u.co.y, u.co.z))) * 0.5
                    v.co = Vector((0.0, mid.y, mid.z))
                    targetmap[u] = v
                    break
    if targetmap:
        bmesh.ops.weld_verts(bm, targetmap=targetmap)
    # remaining coincident vertices on the plane
    mid = [v for v in bm.verts if abs(v.co.x) < 1e-6]
    bmesh.ops.remove_doubles(bm, verts=mid, dist=1e-5)
    nb = sum(1 for e in bm.edges if e.is_boundary)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bad = [e for e in bm.edges if not e.is_manifold or e.is_boundary]
    if bad:
        print("    bad edges at:", [tuple(round(c, 3) for c in ((e.verts[0].co + e.verts[1].co) * 0.5)) for e in bad[:12]],
              "faces/edge:", [len(e.link_faces) for e in bad[:12]])
    bm.to_mesh(me)
    bm.free()
    me.update()
    return nb, nm


def _flipped_faces(me, X, field):
    """Indices of faces whose geometric normal opposes the SDF gradient (folded geometry)."""
    n = len(me.polygons)
    ls = np.empty(n, dtype=np.int32)
    lt = np.empty(n, dtype=np.int32)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", lv)
    a, b, c = X[lv[ls]], X[lv[ls + 1]], X[lv[ls + 2]]
    nrm = np.cross(b - a, c - a)
    cen = (a + b + c) / 3.0
    g = field.grad(cen)
    return np.nonzero(np.einsum("ij,ij->i", nrm, g) < 0)[0], ls, lt, lv


def _untangle(me, X, field, log=print, iters=6):
    """Smooth (then re-project) the neighbourhood of folded faces until none remain."""
    for it in range(iters):
        bad, ls, lt, lv = _flipped_faces(me, X, field)
        if len(bad) == 0:
            break
        verts = set()
        for f in bad:
            verts.update(lv[ls[f]:ls[f] + lt[f]].tolist())
        E = _edges(me)
        ring = set(verts)
        for e0, e1 in E:
            if e0 in verts or e1 in verts:
                ring.add(int(e0))
                ring.add(int(e1))
        mask = np.zeros(len(X), bool)
        mask[list(ring)] = True
        acc = np.zeros_like(X)
        cnt = np.zeros(len(X))
        np.add.at(acc, E[:, 0], X[E[:, 1]])
        np.add.at(acc, E[:, 1], X[E[:, 0]])
        np.add.at(cnt, E[:, 0], 1)
        np.add.at(cnt, E[:, 1], 1)
        avg = acc / np.maximum(cnt, 1)[:, None]
        X[mask] = avg[mask]
        X[mask] = field.project(X[mask], iters=3)
        log(f"  untangle pass {it}: {len(bad)} folded faces, smoothed {mask.sum()} verts")
    bad = _flipped_faces(me, X, field)[0]
    if len(bad):
        log(f"  WARNING: {len(bad)} folded faces remain")
    return X


def _non_manifold(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    ne = sum(1 for e in bm.edges if not e.is_manifold)
    nv = sum(1 for v in bm.verts if not v.is_manifold)
    bm.free()
    return ne, nv


def _symmetrize(V, tol=0.004):
    """Make vertex positions exactly mirror-symmetric (pairs found by nearest mirrored vertex)."""
    kd = kdtree.KDTree(len(V))
    for i, p in enumerate(V):
        kd.insert(p, i)
    kd.balance()
    V2 = V.copy()
    for i, p in enumerate(V):
        m = Vector((-p[0], p[1], p[2]))
        co, j, dist = kd.find(m)
        if dist < tol:
            q = V[j]
            V2[i] = 0.5 * (np.array(p) + np.array((-q[0], q[1], q[2])))
    V2[np.abs(V2[:, 0]) < 1e-5, 0] = 0.0
    return V2


# ============================================================================ procedural hand topology
def _ray_exit(field, O, Dd, tmax, n=96, fallback=None):
    """First inside->outside crossing along each ray O + t*D (vectorised, bisection refined)."""
    O = np.asarray(O, float)
    Dd = np.asarray(Dd, float)
    m = len(O)
    ts = np.linspace(0.0, tmax, n)
    P = O[:, None, :] + ts[None, :, None] * Dd[:, None, :]
    inside = field(P.reshape(-1, 3)).reshape(m, n) < 0
    cross = inside[:, :-1] & ~inside[:, 1:]
    has = cross.any(axis=1)
    first = np.argmax(cross, axis=1)
    a, b = ts[first], ts[first + 1]
    for _ in range(16):
        mid = 0.5 * (a + b)
        fin = field(O + mid[:, None] * Dd) < 0
        a = np.where(fin, mid, a)
        b = np.where(fin, b, mid)
    t = 0.5 * (a + b)
    fb_ = np.zeros(m) if fallback is None else np.asarray(fallback, float)
    t = np.where(has, t, fb_)
    return O + t[:, None] * Dd


def _perp_frame(axis, ref_a, ref_b):
    """Orthonormal (A, B) perpendicular to `axis`, A closest to ref_a, B closest to ref_b."""
    ax = _unit(axis)
    A = np.asarray(ref_a, float) - (np.asarray(ref_a, float) @ ax) * ax
    A = _unit(A)
    B = np.asarray(ref_b, float) - (np.asarray(ref_b, float) @ ax) * ax - (np.asarray(ref_b, float) @ A) * A
    B = _unit(B)
    return A, B


def _polyline_at(pts, s_):
    """Point and tangent at arc length s_ along polyline pts (extrapolates past the end)."""
    seg = [np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1)]
    acc = 0.0
    for i, ln in enumerate(seg):
        if s_ <= acc + ln or i == len(seg) - 1:
            d = _unit(pts[i + 1] - pts[i])
            return pts[i] + d * (s_ - acc), d
        acc += ln


def build_hand_template(field, J, info, s, u_cut=-0.022):
    """Quad template for the +X hand, every vertex ray-marched onto the SDF (world units).
    Returns (verts (n,3), faces [tuple], wrist_loop [vertex indices in order])."""
    X, T, D = info["hand_axes"]
    hsc = info["hsc"]
    Wr = info["Wr"] * s
    verts = []
    faces = []

    def addv(p):
        verts.append(np.asarray(p, float))
        return len(verts) - 1

    # ---- palm tube: 7 stations x 20-vertex rounded-rectangle rings
    a_, h_ = 0.036, 0.013
    ring_vw = ([(-a_ + 2 * a_ * i / 8, h_) for i in range(9)] + [(a_, 0.0)]
               + [(a_ - 2 * a_ * i / 8, -h_) for i in range(9)] + [(-a_, 0.0)])
    st_u = [u_cut, -0.004, 0.014, 0.032, 0.050, 0.068, 0.084]
    rings = []
    for u in st_u:
        c = Wr + hsc * s * (u * X + 0.001 * D)
        dirs = np.array([_unit(v * T + w * D) for v, w in ring_vw])
        O = np.repeat(c[None], len(dirs), 0)
        P = _ray_exit(field, O, dirs, 0.07 * s, fallback=np.full(len(dirs), 0.02 * s))
        rings.append([addv(p) for p in P])
    nst = len(rings)
    thumb_cells = {(1, 8), (1, 9), (2, 8), (2, 9)}  # (station k, ring j) cells removed for the thumb
    for k in range(nst - 1):
        for j in range(20):
            if (k, j) in thumb_cells:
                continue
            faces.append((rings[k][j], rings[k][(j + 1) % 20], rings[k + 1][(j + 1) % 20], rings[k + 1][j]))
    # ---- knuckle cap: grid (i = 0..8 across v, row 0 palmar / 1 mid / 2 dorsal) shared with the last ring
    last = rings[-1]

    def grid(i, row):
        if row == 2:
            return last[i]
        if row == 0:
            return last[18 - i] if i < 9 else None
        return None

    web = {}
    for i in (2, 4, 6):
        v_ = -a_ + 2 * a_ * i / 8
        c = Wr + hsc * s * ((st_u[-1] - 0.012) * X + v_ * T + 0.001 * D)
        web[i] = addv(_ray_exit(field, c[None], X[None], 0.06 * s, fallback=np.array([0.02 * s]))[0])

    def gid(i, row):
        if row == 1:
            if i == 0:
                return last[19]
            if i == 8:
                return last[9]
            return web[i]
        return grid(i, row)

    finger_names = ["pinky", "ring", "middle", "index"]
    ring_dirs = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]

    def digit_field(prefix):
        ops = [op for op in field.ops if op.tag.startswith(prefix) and op.tag[len(prefix):].isdigit()
               and isinstance(op.prim, RoundCone) and op.prim.a[0] > 0]
        return Field(ops, field.scale) if ops else field

    def tube(base_ring, pts, radii_hint, frame_ref, stations, tip_r, dfield):
        prev = base_ring
        for st in stations:
            p, d = _polyline_at(pts, st)
            A, B = _perp_frame(d, *frame_ref)
            dirs = np.array([_unit(ca * A + cb * B) for ca, cb in ring_dirs])
            P = _ray_exit(dfield, np.repeat(p[None], 8, 0), dirs, 0.03 * s, fallback=np.full(8, radii_hint * s))
            cur = [addv(q) for q in P]
            for k in range(8):
                faces.append((prev[k], prev[(k + 1) % 8], cur[(k + 1) % 8], cur[k]))
            prev = cur
        # mini ring + pole
        L = sum(np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1))
        p, d = _polyline_at(pts, L + 0.6 * tip_r)
        A, B = _perp_frame(d, *frame_ref)
        dirs = np.array([_unit(ca * A + cb * B) for ca, cb in ring_dirs])
        P = _ray_exit(dfield, np.repeat(p[None], 8, 0), dirs, 0.02 * s, fallback=np.full(8, 0.7 * tip_r))
        cur = [addv(q) for q in P]
        for k in range(8):
            faces.append((prev[k], prev[(k + 1) % 8], cur[(k + 1) % 8], cur[k]))
        pe, de = _polyline_at(pts, L)
        pole = addv(_ray_exit(dfield, pe[None], de[None], 0.03 * s, fallback=np.array([tip_r]))[0])
        for k in (0, 2, 4, 6):
            faces.append((pole, cur[k], cur[k + 1], cur[(k + 2) % 8]))

    for fi, name in enumerate(finger_names):
        i0 = 2 * fi
        base = [gid(i0, 0), gid(i0 + 1, 0), gid(i0 + 2, 0), gid(i0 + 2, 1),
                gid(i0 + 2, 2), gid(i0 + 1, 2), gid(i0, 2), gid(i0, 1)]
        pts = [J[f"{name}_01_L"] * s, J[f"{name}_02_L"] * s, J[f"{name}_03_L"] * s, J[f"{name}_tip_L"] * s]
        segs = [np.linalg.norm(pts[i + 1] - pts[i]) for i in range(3)]
        st = [0.45 * segs[0], 0.85 * segs[0], segs[0] + 0.05 * segs[1], segs[0] + 0.55 * segs[1],
              segs[0] + segs[1] + 0.05 * segs[2], segs[0] + segs[1] + 0.55 * segs[2], sum(segs)]
        tube(base, pts, 0.008, (T, D), st, 0.0072 * hsc * s, digit_field(name))
    # ---- thumb on the side wall (stations 1..3, ring verts 8..10)
    r1, r2, r3 = rings[1], rings[2], rings[3]
    base = [r1[8], r1[9], r1[10], r2[10], r3[10], r3[9], r3[8], r2[8]]
    # base order corresponds to directions (-X,+D),(-X,0),(-X,-D),(0,-D),(+X,-D),(+X,0),(+X,+D),(0,+D)
    pts = [J["thumb_01_L"] * s, J["thumb_02_L"] * s, J["thumb_03_L"] * s, J["thumb_tip_L"] * s]
    segs = [np.linalg.norm(pts[i + 1] - pts[i]) for i in range(3)]
    st = [0.55 * segs[0], segs[0] + 0.05 * segs[1], segs[0] + 0.55 * segs[1],
          segs[0] + segs[1] + 0.08 * segs[2], segs[0] + segs[1] + 0.55 * segs[2], sum(segs)]
    # thumb ring_dirs index k maps (ca, cb) with A ~ -X, B ~ -D so that (-1,-1)->(+X? ) ... use explicit refs:
    tube_dirs_ref = (-X, -D)
    saved = list(ring_dirs)
    # reorder so k=0 -> (-X,+D): with A=-X, B=-D:  (-X,+D) = (A=+1, B=-1)
    ring_dirs[:] = [(1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1)]
    tube(base, pts, 0.009, tube_dirs_ref, st, 0.0084 * hsc * s, digit_field("thumb"))
    ring_dirs[:] = saved
    if any(v is None for f in faces for v in f):
        raise RuntimeError("hand template: unresolved vertex")
    return np.array(verts), faces, list(rings[0])


def _boundary_loops(edges):
    """Group boundary edges into ordered closed vertex loops."""
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    loops, seen = [], set()
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = next((n for n in adj[cur] if n is not prev and n not in seen), None)
            if nxt is None:
                break
            loop.append(nxt)
            seen.add(nxt)
            prev, cur = cur, nxt
        loops.append(loop)
    return loops


def _zip_loops(bm, A, B, center, axis):
    """Bridge two closed vertex loops around `axis` with quads (triangles where counts differ)."""
    axis = _unit(axis)
    r1 = _unit(np.cross(axis, (0.0, 0.0, 1.0)) if abs(axis[2]) < 0.9 else np.cross(axis, (1.0, 0.0, 0.0)))
    r2 = np.cross(axis, r1)

    def prep(L):
        th = []
        for v in L:
            q = np.array(v.co) - center
            q = q - (q @ axis) * axis
            th.append(math.atan2(q @ r2, q @ r1))
        th = np.unwrap(np.array(th))
        if th[-1] < th[0]:
            L = L[::-1]
            th = th[::-1]
        th = np.mod(th, 2 * math.pi)
        k = int(np.argmin(th))
        L = L[k:] + L[:k]
        th = np.concatenate([th[k:], th[:k]])
        th = np.unwrap(th)
        th = th - th[0] + (th[0] % (2 * math.pi))
        return L, list(th) + [th[0] + 2 * math.pi]

    A, ta = prep(A)
    B, tb = prep(B)
    n, m = len(A), len(B)
    tol = 0.3 * min(2 * math.pi / n, 2 * math.pi / m)
    i = j = 0
    made = []
    while i < n or j < m:
        ai, aj = A[i % n], A[(i + 1) % n]
        bi, bj = B[j % m], B[(j + 1) % m]
        if i < n and j < m and abs(ta[i + 1] - tb[j + 1]) < tol:
            fv = (ai, aj, bj, bi)
            i += 1
            j += 1
        elif j >= m or (i < n and ta[i + 1] < tb[j + 1]):
            fv = (ai, aj, bi)
            i += 1
        else:
            fv = (ai, bj, bi)
            j += 1
        if len(set(fv)) == len(fv):
            try:
                made.append(bm.faces.new(fv))
            except ValueError:
                pass
    return made


def _drop_islands(bm, min_faces=60):
    seen = set()
    for f in bm.faces:
        if f in seen:
            continue
        comp, stack = [], [f]
        seen.add(f)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
        if len(comp) < min_faces:
            bmesh.ops.delete(bm, geom=comp, context="FACES")


def attach_hands(me, field, J, info, s, log=print, u_cut_body=-0.030):
    """Replace QuadriFlow's (mitten) hands with the procedural template hands, zipped at the wrist."""
    bm = bmesh.new()
    bm.from_mesh(me)
    X0, T0, D0 = info["hand_axes"]
    tv, tf, loop = build_hand_template(field, J, info, s)
    for sx in (1, -1):
        M = np.array([sx, 1.0, 1.0])
        Wr = info["Wr"] * s * M
        X = X0 * M
        kill = []
        for f in bm.faces:
            q = np.array(f.calc_center_median()) - Wr
            u = q @ X
            if u > u_cut_body * s and np.linalg.norm(q - u * X) < 0.12 * s:
                kill.append(f)
        bmesh.ops.delete(bm, geom=kill, context="FACES")
        _drop_islands(bm)
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bnd = [e for e in bm.edges if e.is_boundary and
               np.linalg.norm(np.array((e.verts[0].co + e.verts[1].co) * 0.5) - Wr) < 0.10 * s]
        body_loops = _boundary_loops(bnd)
        body_loop = max(body_loops, key=len)
        new = [bm.verts.new(tuple(p * M)) for p in tv]
        for f in tf:
            vs = [new[i] for i in (f if sx > 0 else f[::-1])]
            try:
                bm.faces.new(vs)
            except ValueError:
                pass
        lone = [v for v in new if not v.link_faces]
        if lone:
            bmesh.ops.delete(bm, geom=lone, context="VERTS")
        hand_loop = [new[i] for i in loop]
        made = _zip_loops(bm, body_loop, hand_loop, Wr + u_cut_body * 0.85 * s * X, X)
        tris = [f for f in made if len(f.verts) == 3]
        if tris:
            bmesh.ops.join_triangles(bm, faces=tris, angle_face_threshold=math.radians(50),
                                     angle_shape_threshold=math.radians(50))
        log(f"  hand {'L' if sx > 0 else 'R'}: removed {len(kill)} faces, body loop {len(body_loop)} verts "
            f"({len(body_loops)} loops), hand loop {len(hand_loop)}, zipped {len(made)} faces")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    nb = sum(1 for e in bm.edges if e.is_boundary)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return nb, nm


def mesh_report(me):
    """(verts, faces, tris, quads, other, boundary edges, non-manifold edges, components)."""
    bm = bmesh.new()
    bm.from_mesh(me)
    nb = sum(1 for e in bm.edges if e.is_boundary)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    seen, comps = set(), 0
    for f in bm.faces:
        if f in seen:
            continue
        comps += 1
        stack = [f]
        seen.add(f)
        while stack:
            g = stack.pop()
            for e in g.edges:
                for h in e.link_faces:
                    if h not in seen:
                        seen.add(h)
                        stack.append(h)
    q = sum(1 for f in bm.faces if len(f.verts) == 4)
    t = sum(1 for f in bm.faces if len(f.verts) == 3)
    o = len(bm.faces) - q - t
    out = dict(verts=len(bm.verts), faces=len(bm.faces), tris=sum(len(f.verts) - 2 for f in bm.faces), quads=q,
               triangles=t, ngons=o, boundary_edges=nb, nonmanifold_edges=nm, components=comps)
    bm.free()
    return out


# ============================================================================ eyes + brows
def _eye_object(name, center, radius, gaze, mats, col):
    """UV-sphere eyeball with its pole on the gaze axis; faces get sclera / iris / pupil slots."""
    lat = [0, 5, 9.5, 14, 19, 23.5, 27.5, 32, 40, 52, 66, 82, 100, 120, 140, 160, 180]
    seg = 24
    verts, faces = [], []
    verts.append((0, 0, 1))
    for la in lat[1:-1]:
        t = math.radians(la)
        for s in range(seg):
            ph = 2 * math.pi * s / seg
            verts.append((math.sin(t) * math.cos(ph), math.sin(t) * math.sin(ph), math.cos(t)))
    verts.append((0, 0, -1))
    nr = len(lat) - 2
    mid_ids = []
    for s in range(seg):
        faces.append((0, 1 + s, 1 + (s + 1) % seg))
        mid_ids.append(lat[1] * 0.5)
    for r in range(nr - 1):
        for s in range(seg):
            a0 = 1 + r * seg + s
            a1 = 1 + r * seg + (s + 1) % seg
            faces.append((a0, a0 + seg, a1 + seg, a1))
            mid_ids.append(0.5 * (lat[r + 1] + lat[r + 2]))
    last = 1 + (nr - 1) * seg
    for s in range(seg):
        faces.append((last + s, len(verts) - 1, last + (s + 1) % seg))
        mid_ids.append(179)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(radius * c for c in v) for v in verts], [], faces)
    for m in mats:
        me.materials.append(m)
    for p, la in zip(me.polygons, mid_ids):
        p.material_index = 2 if la < 9.5 else (1 if la < 27.5 else 0)
        p.use_smooth = True
    obj = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(obj)
    # local +Z -> gaze
    obj.rotation_euler = Vector(gaze).to_track_quat("Z", "Y").to_euler()
    obj.location = Vector(center)
    return obj


def _brow_object(name, field, scale, info, mat, col):
    """Two thin tapered strips laid on the brow ridge (projected on the SDF surface)."""
    hs = info["hs"] * scale
    yc, zc = info["yc"] * scale, info["z_chin"] * scale
    ez = info["eye_c"][2] * scale
    verts, faces = [], []
    n = 12
    bp = info.get("brow_shape", {})
    x0, x1 = bp.get("x0", 0.012), bp.get("x1", 0.056)
    z0, arch, drop = bp.get("z0", 0.0255), bp.get("arch", 0.0050), bp.get("drop", 0.0060)
    w0, w1 = bp.get("w0", 0.0044), bp.get("w1", 0.0017)
    for sx in (1, -1):
        base = len(verts)
        for i in range(n + 1):
            t = i / n
            x = (x0 + (x1 - x0) * t) * hs
            z = ez + (z0 + arch * math.sin(0.5 * math.pi * min(1.0, t / 0.7)) - drop * max(0.0, t - 0.7) / 0.3) * hs
            w = (w0 * (1 - t) + w1 * t) * hs * (0.85 + 0.15 * min(1.0, t / 0.1))
            for dz in (-0.5 * w, 0.5 * w):
                verts.append(np.array([sx * x, yc - 0.15 * scale, z + dz]))
        for i in range(n):
            a0 = base + 2 * i
            q = (a0, a0 + 2, a0 + 3, a0 + 1) if sx > 0 else (a0, a0 + 1, a0 + 3, a0 + 2)
            faces.append(q)
    V = np.array(verts)
    # project onto the skin: march along +y from in front of the face
    ydir = np.array([0, 1.0, 0])
    steps = np.linspace(0, 0.3 * scale, 1201)
    for i in range(len(V)):
        o = V[i].copy()
        fv = field(o[None] + steps[:, None] * ydir[None])
        idx = np.nonzero(fv < 0)[0]
        if len(idx):
            j = idx[0]
            a_, b_ = steps[max(j - 1, 0)], steps[j]
            for _ in range(25):
                m = 0.5 * (a_ + b_)
                if field((o + m * ydir)[None])[0] < 0:
                    b_ = m
                else:
                    a_ = m
            V[i] = o + a_ * ydir
    g = field.grad(V)
    nrm = g / _nrm(g)[:, None]
    V = V + nrm * 0.0007 * scale
    me = _mesh_from_numpy(name, V, np.array(faces))
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(obj)
    mod = obj.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = 0.0006 * scale
    mod.offset = 1.0
    bc.apply_modifiers(obj)
    return obj


def _lash_object(name, info, scale, mat, col, field=None):
    """Upper lash line: a dark strip hugging the upper lid margin, flaring out and up toward the
    outer corner (stylised eyeliner/lashes - gives the eye its almond read)."""
    lid = info["lid"]
    verts, faces = [], []
    n = 18
    for sx in (1, -1):
        base = len(verts)
        for i in range(n + 1):
            t = i / n
            al = lid.a_in + (lid.a_out - lid.a_in) * (0.04 + 0.98 * t)
            up, lo = lid.curves(al)
            up = float(up)
            r0 = lid.r_in + lid.thick * 0.55
            ln = (0.0007 + 0.0018 * t ** 1.5) * info["hs"]
            wing = max(0.0, t - 0.8) / 0.2
            d_in = lid.direction(al, up - math.radians(1.5))
            d_out = lid.direction(al + math.radians(5.0) * wing, up + math.radians(4.0 + 6.0 * t))
            pa = lid.c + d_in * r0
            pb = lid.c + d_out * (lid.r_in + lid.thick + ln)
            for p in (pa, pb):
                q = np.array(p) * scale
                q[0] *= sx
                verts.append(q)
        for i in range(n):
            a0 = base + 2 * i
            faces.append((a0, a0 + 2, a0 + 3, a0 + 1) if sx > 0 else (a0, a0 + 1, a0 + 3, a0 + 2))
    me = _mesh_from_numpy(name, np.array(verts), np.array(faces))
    me.materials.append(mat)
    for p in me.polygons:
        p.use_smooth = True
    obj = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(obj)
    mod = obj.modifiers.new("Solidify", "SOLIDIFY")
    mod.thickness = 0.00045 * scale
    mod.offset = 0.0
    bc.apply_modifiers(obj)
    return obj


def _iris_material(name, color):
    """Iris with a darker limbal ring and lighter centre (object-space radial gradient)."""
    m = bc.material(name, color, rough=0.08)
    nt = m.node_tree
    p = bc._principled(m)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    vm = nt.nodes.new("ShaderNodeVectorMath")
    vm.operation = "LENGTH"
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(sep.outputs[0], comb.inputs[0])
    nt.links.new(sep.outputs[1], comb.inputs[1])
    nt.links.new(comb.outputs[0], vm.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = 1.0
    m["_map_range"] = mr.name
    nt.links.new(vm.outputs["Value"], mr.inputs["Value"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    c = np.array(color[:3])
    cr.elements[0].position = 0.3
    cr.elements[0].color = (*np.clip(c * 1.9 + 0.03, 0, 1), 1)
    cr.elements[1].position = 0.97
    cr.elements[1].color = (*(c * 0.25), 1)
    e = cr.elements.new(0.75)
    e.color = (*c, 1)
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    return m


# ============================================================================ materials
def _face_paint(obj, field, info, s, lip_mult=(0.91, 0.71, 0.69), blush_mult=(0.975, 0.91, 0.89)):
    """Per-vertex multiplicative tint: lips + a soft blush. Stored as colour attribute 'FacePaint'
    (white = no change) so glTF exports it as COLOR_0, which engines multiply with the base colour."""
    me = obj.data
    V = _get_verts(me) / s
    w_lip = np.zeros(len(V))
    near = _nrm(V - info["lip_c"]) < 0.06
    if near.any():
        d = np.min(np.stack([pr(V[near]) for pr in info["lip_prims"]]), axis=0)
        w_lip[near] = _smoothstep(0.0022, -0.0008, d)
    w_ml = np.zeros(len(V))
    if near.any() and info.get("mouth_prim") is not None:
        dm = info["mouth_prim"](V[near])
        w_ml[near] = 1 - _smoothstep(0.0, 0.0024, dm)
    w_bl = np.zeros(len(V))
    for sx in (1, -1):
        c = info["blush_c"] * [sx, 1, 1]
        w_bl = np.maximum(w_bl, 0.6 * (1 - _smoothstep(0.004, 0.026, _nrm(V - c))))
    col = np.ones((len(V), 4))
    lm, bm_ = np.array(lip_mult), np.array(blush_mult)
    col[:, :3] = col[:, :3] * (1 - w_bl[:, None]) + bm_ * w_bl[:, None]
    col[:, :3] = col[:, :3] * (1 - w_lip[:, None]) + (col[:, :3] * lm) * w_lip[:, None]
    ml = np.array((0.62, 0.46, 0.45))
    col[:, :3] = col[:, :3] * (1 - w_ml[:, None]) + (col[:, :3] * ml) * w_ml[:, None]
    attr = me.color_attributes.get("FacePaint") or me.color_attributes.new("FacePaint", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", col.astype(np.float32).ravel())
    me.color_attributes.active_color = attr
    try:
        me.color_attributes.render_color_index = me.color_attributes.find("FacePaint")
    except Exception:
        pass
    return attr


def _skin_material(name, color):
    m = bc.material(name, color, rough=0.52)
    p = bc._principled(m)
    nt = m.node_tree
    ca = nt.nodes.new("ShaderNodeVertexColor")
    ca.layer_name = "FacePaint"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    mix.inputs[6].default_value = (*color[:3], 1.0)
    nt.links.new(ca.outputs["Color"], mix.inputs[7])
    nt.links.new(mix.outputs[2], p.inputs["Base Color"])
    bc._set_input(p, ["Subsurface Weight", "Subsurface"], 0.12)
    if "Subsurface Radius" in p.inputs:
        p.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.3)
    bc._set_input(p, "Subsurface Scale", 0.01)
    bc._set_input(p, ["Specular IOR Level", "Specular"], 0.4)
    return m


# ============================================================================ measurements
def _measure(field, J, info, s, height):
    def m(o, d, tmax=0.6):
        return field.march(np.asarray(o) * s, d, tmax=tmax * s)

    dims = {"height": height}
    for nm, z in (("chest", 1.232), ("underbust", 1.17), ("waist", 1.06), ("hip", 0.885), ("neck", 1.45)):
        zz = z
        rx = m((0, 0.01, zz), (1, 0, 0), 0.3)
        yf = m((0, 0.01, zz), (0, -1, 0), 0.3)
        yb = m((0, 0.01, zz), (0, 1, 0), 0.3)
        ry = 0.5 * (yf + yb)
        circ = math.pi * (3 * (rx + ry) - math.sqrt((3 * rx + ry) * (rx + 3 * ry)))
        dims[nm] = {"z": zz * s, "rx": rx, "ry": ry, "front_y": 0.01 * s - yf, "back_y": 0.01 * s + yb, "circ": circ}
    # shoulder width: widest x at deltoid level
    best = 0
    for dz in np.linspace(-0.06, 0.02, 9):
        r = m((0.12, 0.012, 1.383 + dz), (1, 0, 0), 0.3)
        if r == r:
            best = max(best, 0.12 * s + r)
    dims["shoulder_width"] = 2 * best
    dims["biacromial"] = 2 * J["upperarm_L"][0] * s
    # limb radii (perpendicular to the limb)
    def limb_r(p, axis, perp):
        return m(p, perp, 0.15)

    S, E, Wr = info["S"], info["E"], info["Wr"]
    du, df = info["d_ua"], info["d_fa"]
    dims["upperarm_r"] = limb_r(_lerp(S, E, 0.5), du, (0, -1, 0))
    dims["forearm_r"] = limb_r(_lerp(E, Wr, 0.3), df, (0, -1, 0))
    dims["wrist_r"] = {"width": limb_r(Wr - 0.012 * df, df, (0, -1, 0)),
                       "thick": limb_r(Wr - 0.012 * df, df, info["hand_axes"][2])}
    hip, knee, ank = info["hip"], info["knee"], info["ank"]
    dims["thigh_r"] = limb_r(_lerp(hip, knee, 0.2), None, (1, 0, 0))
    dims["knee_r"] = limb_r(knee, None, (1, 0, 0))
    dims["calf_r"] = limb_r(knee + _a(0, 0, -0.11), None, (0, 1, 0))
    dims["ankle_r"] = limb_r(ank + _a(0, 0, 0.03), None, (1, 0, 0))
    # crotch / inseam: lowest point on the midline
    zs = np.linspace(0.6, 1.0, 400)
    P = np.stack([np.zeros_like(zs), np.full_like(zs, 0.0), zs], 1) * s
    fv = field(P)
    inside = np.nonzero(fv < 0)[0]
    dims["crotch_z"] = float(zs[inside[0]] * s) if len(inside) else float("nan")
    dims["inseam"] = dims["crotch_z"]
    ec = info["eye_c"] * s
    dims["eye_height"] = float(ec[2])
    dims["eye_center_L"] = tuple(ec)
    dims["eye_radius"] = info["eye_r"] * s
    hc = _a(0, info["yc"], info["z_chin"] + 0.115 * info["hs"]) * s
    dims["head_center"] = tuple(hc)
    dims["head_height"] = info["head_h"] * s
    dims["head_width"] = 2 * m(hc / s, (1, 0, 0), 0.2)
    dims["head_depth"] = m(hc / s, (0, -1, 0), 0.2) + m(hc / s, (0, 1, 0), 0.2)
    dims["chin_z"] = info["z_chin"] * s
    dims["hand_length"] = float(np.linalg.norm(J["middle_tip_L"] - J["hand_L"]) * s)
    dims["foot_length"] = float((J["heel_L"][1] + 0.036 - (J["toe_end_L"][1] + 0.0)) * s)
    dims["arm_angle_deg"] = 42.0
    dims["sole_z"] = 0.0
    return dims


# ============================================================================ main entry
def build_female_base(prefix="FB", height=1.70, build=0.0, skin=(0.62, 0.42, 0.33), eye_color=(0.25, 0.18, 0.12),
                      col=None, brow_color=(0.05, 0.032, 0.022), face=None, target_faces=9600, cell=0.0017,
                      head_density=3.0, hand_density=2.5, remesh_voxel=0.003, verbose=True):
    """Build the base body. Returns dict(body, eyes, brows, joints, dims, materials, field, info)."""
    log = print if verbose else (lambda *a, **k: None)
    t0 = time.time()
    s = height / REF_H
    ops, Jref, info = make_recipe(build, face)
    field = Field(ops, s, cell)
    log(f"[female_base] {prefix}: {len(ops)} SDF ops, scale {s:.3f}")
    V, Q = polygonize(field, h=cell, log=log)
    # ---- density warp (world units)
    zc = info["z_chin"] * s
    hands = []
    for sx in (1, -1):
        Wr = info["Wr"] * [sx, 1, 1] * s
        ax = info["d_fa"] * [sx, 1, 1]
        c = Wr - 0.045 * s * ax
        hands.append((c, ax, 0.045 * s, 0.10 * s, 0.17 * s))
    fans = []
    for sx in (1, -1):
        for K, d, ax, ang, ln, rad in info["fans"]:
            M = np.array([sx, 1, 1])
            fans.append((K * M * s, d * M, ax * M, ang * sx, ln * s, rad * s))
    warp = Warp(zc - 0.060 * s, zc + 0.020 * s, head_density, info["yc"] * s, hands, hand_density, ())
    Vw = warp(V)
    tmp = bpy.data.objects.new("_fb_tmp", _mesh_from_numpy("_fb_tmp", Vw, Q))
    bpy.context.scene.collection.objects.link(tmp)
    ne, nv = _non_manifold(tmp)
    log(f"  surface-nets mesh: non-manifold edges {ne}, verts {nv}")
    bpy.ops.object.select_all(action="DESELECT")
    tmp.select_set(True)
    bpy.context.view_layer.objects.active = tmp
    # voxel remesh in warped space: guarantees a clean manifold input and sets QuadriFlow's input density
    mod = tmp.modifiers.new("vox", "REMESH")
    mod.mode = "VOXEL"
    mod.voxel_size = remesh_voxel * s
    bc.apply_modifiers(tmp)
    log(f"  voxel remesh -> {len(tmp.data.polygons)} faces ({time.time() - t0:.1f}s)")
    _weld_short_edges(tmp.data, 2.5e-4, log)
    t1 = time.time()
    nb_edges, nm_edges = _quadriflow_symmetric(tmp, target_faces, log)
    obj = tmp
    me = obj.data
    log(f"  quadriflow (half + mirror) -> {len(me.polygons)} faces in {time.time() - t1:.1f}s; "
        f"boundary edges {nb_edges}, non-manifold edges {nm_edges}")
    Yq = _get_verts(me)
    # ---- map back through the warp: init from nearest fine vertex
    kd = kdtree.KDTree(len(Vw))
    for i, p in enumerate(Vw):
        kd.insert(p, i)
    kd.balance()
    X0 = np.array([V[kd.find(p)[1]] for p in Yq])
    X = warp.inverse(Yq, X0)
    log(f"  warp inverse: {warp.last_bad} vertices fell back to nearest")
    midv = np.abs(Yq[:, 0]) < 1e-6
    X[midv, 0] = 0.0
    X = field.project(X, iters=8)
    X[midv, 0] = 0.0
    _set_verts(me, X)
    nbh, nmh = attach_hands(me, field, Jref, info, s, log)
    log(f"  hands attached: boundary edges {nbh}, non-manifold edges {nmh}")
    X = _get_verts(me)
    midv = np.abs(X[:, 0]) < 1e-6
    pin = np.zeros(len(X), bool)
    for sx in (1, -1):
        Wr = info["Wr"] * [sx, 1, 1] * s
        ax = info["d_fa"] * [sx, 1, 1]
        q = X - Wr
        u = q @ ax
        pin |= (u > 0.080 * info["hsc"] * s) & (_nrm(q - np.outer(u, ax)) < 0.12 * s)
    X[~pin] = field.project(X[~pin], iters=4)
    X[midv, 0] = 0.0
    seam = np.zeros(len(X), bool)
    for sx in (1, -1):
        Wr = info["Wr"] * [sx, 1, 1] * s
        ax = info["d_fa"] * [sx, 1, 1]
        q = X - Wr
        u = q @ ax
        seam |= (u > -0.055 * s) & (u < -0.005 * s) & (_nrm(q - np.outer(u, ax)) < 0.12 * s)
    E = _edges(me)
    X = _relax(X, E, field, iters=6, lam=0.5, pin=~seam, midline=midv)
    X = _relax(X, E, field, iters=4, lam=0.4, pin=pin, midline=midv)
    X = _untangle(me, X, field, log)
    X = _symmetrize(X)
    _set_verts(me, X)
    # ---- finalize body object
    name = f"{prefix}_Body"
    obj.name = name
    me.name = name
    if col is not None:
        bc.link(obj, col)
    skin_mat = _skin_material(f"M_{prefix}_Skin", skin)
    bc.assign(obj, skin_mat)
    for p in me.polygons:
        p.use_smooth = True
    bc.smart_uv(obj, angle=60, margin=0.01)
    _face_paint(obj, field, info, s)
    # ---- eyes
    ec = info["eye_c"] * s
    er = info["eye_r"] * s
    m_scl = bc.material(f"M_{prefix}_EyeSclera", (0.80, 0.78, 0.75), rough=0.12)
    m_iris = _iris_material(f"M_{prefix}_EyeIris", eye_color)
    mr = m_iris.node_tree.nodes.get(m_iris.get("_map_range", ""))
    if mr is not None:
        mr.inputs["From Max"].default_value = info["eye_r"] * s * math.sin(math.radians(27.5))
    m_pup = bc.material(f"M_{prefix}_EyePupil", (0.01, 0.01, 0.012), rough=0.08)
    eyes = []
    for sx, side in ((1, "L"), (-1, "R")):
        c = ec * [sx, 1, 1]
        g = info["gaze"] * [sx, 1, 1]
        eyes.append(_eye_object(f"{prefix}_Eye_{side}", c, er, g, [m_scl, m_iris, m_pup], col))
    # ---- brows
    m_brow = bc.material(f"M_{prefix}_Brow", brow_color, rough=0.8)
    brows = _brow_object(f"{prefix}_Brows", field, s, info, m_brow, col)
    bc.smart_uv(brows)
    m_lash = bc.material(f"M_{prefix}_Lash", (0.012, 0.008, 0.007), rough=0.7)
    lashes = _lash_object(f"{prefix}_Lashes", info, s, m_lash, col)
    bc.smart_uv(lashes)
    for e in eyes:
        bc.smart_uv(e)
    joints = {k: tuple(float(x) for x in v * s) for k, v in Jref.items()}
    dims = _measure(field, Jref, info, s, height)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    dims["body_tris"] = tris
    rep = mesh_report(me)
    dims["body_quads"] = rep["quads"]
    dims["body_faces"] = rep["faces"]
    dims["mesh_report"] = rep
    log(f"  mesh report: {rep}")
    log(f"[female_base] {prefix}: body {len(me.vertices)} verts / {tris} tris, total {time.time() - t0:.1f}s")
    return {"body": obj, "eyes": eyes, "brows": brows, "lashes": lashes, "joints": joints, "dims": dims,
            "materials": {"skin": skin_mat, "sclera": m_scl, "iris": m_iris, "pupil": m_pup, "brow": m_brow,
                          "lash": m_lash},
            "field": field, "info": info, "scale": s}
