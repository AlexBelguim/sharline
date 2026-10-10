"""SOLACE face texture (numpy only): a 1024^2 front-projected texture for the front face faces.

Input: an orthographic flat-shaded capture of the regraded base colour on the face faces (RGBA, Blender pixel order:
row 0 = bottom). The TRELLIS eye/brow smears are erased against a smooth skin fill, then clean stylised features are
painted at 0.2 mm per pixel: almond eyes (warm sclera, large dark-brown iris, catch light, strong upper lash line with
a small lift), groomed brows, and calm closed lips with a slight smile. Calm, kind, confident (brief section 5).
"""
import numpy as np

from sol_tex import smoothstep, dilate, in_shards, SHARD_HAIR

X0, Z0, S, N = 0.001 - 0.105, 1.42, 0.21, 1024
XM = 0.001
EYE_W = 0.0136
EYES = {"R": (-0.0360, 1.5458), "L": (0.0380, 1.5458)}
BROWS = {"R": [(-0.0110, 1.5605, 0.0019), (-0.0230, 1.5648, 0.0017), (-0.0395, 1.5664, 0.0013),
               (-0.0525, 1.5622, 0.0005)],
         "L": [(0.0130, 1.5605, 0.0019), (0.0250, 1.5648, 0.0017), (0.0415, 1.5664, 0.0013),
               (0.0545, 1.5622, 0.0005)]}
# round 2 (review: neutral-stern read): softer brows (inner ends 0.8 mm higher and thinner, painted lighter) and
# mouth corners lifted a little more into the calm half smile
BROWS_SOFT = {k: [(p[0], p[1] + (0.0008 if i == 0 else 0.0004 if i == 1 else 0.0), p[2] * (0.80 if i == 0 else 0.9))
                  for i, p in enumerate(v)] for k, v in BROWS.items()}
BROW_ALPHA = 0.80
CORNER_LIFT = 0.0017
MOUTH = dict(y=1.4755, xl=-0.0188, xr=0.0208, top=1.4800, bottom=1.4668)

SKIN_LIP_U = np.array([0.335, 0.190, 0.160])
SKIN_LIP_L = np.array([0.375, 0.215, 0.180])
BROW_C = np.array([0.075, 0.046, 0.038])
SCLERA = np.array([0.83, 0.77, 0.71])
IRIS = np.array([0.26, 0.145, 0.085])
IRIS_D = np.array([0.095, 0.052, 0.033])
LASH = np.array([0.040, 0.026, 0.023])
LID_SH = np.array([0.30, 0.19, 0.14])


def _blur(a, r):
    """Separable box blur (3 passes ~ gaussian) of an H x W x C array."""
    for _ in range(3):
        for ax in (0, 1):
            pad = [(r + 1, r) if i == ax else (0, 0) for i in range(a.ndim)]
            c = np.cumsum(np.pad(a, pad, mode="edge"), axis=ax)
            n = a.shape[ax]
            a = (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax) - np.take(c, np.arange(n), axis=ax)) / (
                2 * r + 1)
    return a


def norm_fill(img, valid, r):
    """Normalised blur: average of valid pixels around each pixel. Where no valid pixel is in reach (the middle of
    a big erased area) the radius grows until one is."""
    w = valid.astype(np.float32)[..., None]
    out = None
    for rr in (r, r * 3, r * 8):
        num = _blur(img * w, rr)
        den = _blur(w, rr)
        cur = num / np.maximum(den, 1e-6)
        ok = den[..., 0] > 0.02
        if out is None:
            out = np.where(ok[..., None], cur, 0.0)
            have = ok
        else:
            out = np.where((~have & ok)[..., None], cur, out)
            have |= ok
    return out


def seg_dist(px, pz, a, b):
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    t = np.clip(((px - ax) * dx + (pz - az) * dz) / max(dx * dx + dz * dz, 1e-12), 0, 1)
    return np.hypot(px - (ax + t * dx), pz - (az + t * dz)), t


def stroke(px, pz, pts, samples=40):
    pts = np.asarray(pts, float)
    k = len(pts) - 1
    ts = np.linspace(0, k, samples)
    xs = np.interp(ts, np.arange(len(pts)), pts[:, 0])
    zs = np.interp(ts, np.arange(len(pts)), pts[:, 1])
    rs = np.interp(ts, np.arange(len(pts)), pts[:, 2])
    for _ in range(3):
        xs[1:-1] = 0.25 * xs[:-2] + 0.5 * xs[1:-1] + 0.25 * xs[2:]
        zs[1:-1] = 0.25 * zs[:-2] + 0.5 * zs[1:-1] + 0.25 * zs[2:]
    d = np.full(px.shape, 1e9)
    for i in range(samples - 1):
        di, t = seg_dist(px, pz, (xs[i], zs[i]), (xs[i + 1], zs[i + 1]))
        d = np.minimum(d, di - (rs[i] + (rs[i + 1] - rs[i]) * t))
    return d


def over(dst, col, a):
    a = np.clip(a, 0, 1)[..., None]
    dst[:] = dst * (1 - a) + np.asarray(col, np.float32) * a


def eye_curves(px, c, side):
    cx, cz = c
    s = 1.0 if side == "L" else -1.0
    u = (px - cx) / EYE_W * s                       # -1 inner .. +1 outer
    base = cz + 0.0011 * u                          # gentle lift toward the outer corner
    q = np.clip(1 - u * u, 0, 1)
    zu = base + 0.0060 * q ** 0.72 * (1 - 0.20 * u)
    zl = base - 0.0035 * q ** 0.85 * (1 + 0.15 * u)
    return u, zu, zl


def paint_face(cap, log=print):
    """cap: N x N x 4 float RGBA (row 0 = bottom). Returns the finished N x N x 4 face texture."""
    img = cap[..., :3].astype(np.float32).copy()
    valid = cap[..., 3] > 0.5
    jj, ii = np.mgrid[0:N, 0:N]
    px = X0 + (ii + 0.5) / N * S
    pz = Z0 + (jj + 0.5) / N * S
    aa = 0.00028
    # ---------------------------------------------------------------- erase old features
    er = np.zeros((N, N), bool)
    for side, (cx, cz) in EYES.items():
        er |= ((px - cx) / 0.025) ** 2 + ((pz - cz - 0.001) / 0.0135) ** 2 < 1.0
    for side, pts in BROWS.items():
        er |= stroke(px, pz, [(p[0], p[1], 0.0060) for p in pts]) < 0
    er |= (np.abs(px - XM) < 0.034) & (pz > MOUTH["bottom"] - 0.007) & (pz < MOUTH["top"] + 0.004)
    # dark leftovers anywhere in the upper face that are not hair (hair texels sit outside the face faces)
    lum = img.mean(-1)
    er |= valid & (lum < 0.22) & (pz > 1.53) & (pz < 1.585) & (np.abs(px - XM) < 0.058)
    er &= valid
    keep = valid & ~er
    fill = norm_fill(img, keep, 18)
    soft = np.clip(_blur(er.astype(np.float32)[..., None], 3)[..., 0] * 1.4, 0, 1)
    img = img * (1 - soft[..., None]) + fill * soft[..., None]
    # light overall smoothing of the skin (TRELLIS blotches / chart-border cracks), keeps big shading
    sm = norm_fill(img, valid, 5)
    img = np.where(valid[..., None], img * 0.5 + sm * 0.5, img)
    log(f"face texture: erased {er.sum()} px")

    # ---------------------------------------------------------------- brows
    for side, pts in BROWS_SOFT.items():
        d = stroke(px, pz, pts)
        # hair-like texture: fine strokes along the brow
        streak = 0.85 + 0.15 * np.sin((px * 9000.0) + (pz * 2500.0))
        over(img, BROW_C, (1 - smoothstep(-aa, aa * 1.5, d)) * BROW_ALPHA * streak)
    # ---------------------------------------------------------------- eyes
    for side, c in EYES.items():
        cx, cz = c
        s = 1.0 if side == "L" else -1.0
        u, zu, zl = eye_curves(px, c, side)
        ins = np.maximum.reduce([pz - zu, zl - pz, (np.abs(u) - 1) * EYE_W])
        inside = 1 - smoothstep(-aa, aa, ins)
        # crease / lid shadow above the eye
        crease_z = zu + 0.0032 * np.clip(1 - u * u, 0, 1) ** 0.6
        dcr = np.abs(pz - crease_z) - 0.00035
        over(img, LID_SH, (1 - smoothstep(-aa, aa * 3, dcr)) * (np.abs(u) < 0.95) * 0.45)
        band = (pz > zu) & (pz < crease_z)
        over(img, LID_SH, band * 0.18)
        # sclera (darker in the corners and under the upper lid)
        q = np.clip(1 - u * u, 0, 1)
        scl = SCLERA[None, None, :] * (0.78 + 0.22 * q[..., None]) * (
            1 - 0.18 * smoothstep(-0.0025, 0.0, -(zu - pz))[..., None])
        a = inside[..., None]
        img[:] = img * (1 - a) + scl * a
        # iris, pupil, catch light (gaze straight ahead, iris tucked under the upper lid)
        ix = cx - s * 0.0004
        iz = cz + 0.0006
        dr = np.hypot(px - ix, pz - iz)
        ri = 0.0050
        iris = (1 - smoothstep(ri - aa, ri + aa, dr)) * inside
        ring = smoothstep(ri * 0.45, ri, dr)
        icol = IRIS[None, None, :] * (1 - ring[..., None]) + IRIS_D[None, None, :] * ring[..., None]
        # lighter lower half of the iris (painted light)
        icol = icol * (1 + 0.35 * smoothstep(0.0, -0.004, pz - iz)[..., None] * (1 - ring[..., None]))
        a = iris[..., None]
        img[:] = img * (1 - a) + icol * a
        over(img, (0.025, 0.017, 0.015), (1 - smoothstep(0.0021 - aa, 0.0021 + aa, dr)) * inside)
        # upper-lid shadow on the eyeball
        sh = smoothstep(-0.0016, 0.0, pz - zu) * inside
        over(img, (0.10, 0.06, 0.05), sh * 0.45)
        # upper lash line: thicker toward the outer corner, plus a small upward flick
        th = 0.00055 + 0.00085 * smoothstep(-0.7, 0.85, u)
        dl = np.abs(pz - (zu + th * 0.55)) - th * 0.75
        over(img, LASH, (1 - smoothstep(-aa, aa, dl)) * (np.abs(u) < 1.03) * 0.97)
        ox, oz = cx + s * EYE_W * 0.98, cz + 0.0011
        dfl, tfl = seg_dist(px, pz, (ox - s * 0.0012, oz + 0.0006), (ox + s * 0.0034, oz + 0.0029))
        over(img, LASH, (1 - smoothstep(-aa, aa, dfl - (0.0008 * (1 - tfl) + 0.00015))) * 0.95)
        # lower lash line (thin, soft, outer two-thirds)
        dlo = np.abs(pz - zl) - 0.0003
        over(img, LASH * 1.5, (1 - smoothstep(-aa, aa * 2, dlo)) * smoothstep(-0.5, 0.0, u) * (u < 1.0) * 0.55)
        # inner corner (caruncle) warm tint
        dcar = np.hypot(px - (cx - s * EYE_W * 0.92), pz - (cz - 0.0002))
        over(img, (0.55, 0.30, 0.26), (1 - smoothstep(0.0006, 0.0011, dcar)) * inside * 0.8)
        # catch lights
        hl = 1 - smoothstep(0.00060, 0.00085, np.hypot(px - (ix + s * 0.0019), pz - (iz + 0.0019)))
        over(img, (0.97, 0.95, 0.92), hl * inside * 0.95)
        hl2 = 1 - smoothstep(0.00025, 0.0004, np.hypot(px - (ix - s * 0.0015), pz - (iz - 0.0017)))
        over(img, (0.80, 0.74, 0.70), hl2 * inside * 0.6)
    # ---------------------------------------------------------------- lips (closed, calm half smile)
    m = MOUTH
    half = (m["xr"] - m["xl"]) / 2
    mx = (m["xl"] + m["xr"]) / 2
    uu = (px - mx) / half
    qq = np.clip(1 - uu * uu, 0, 1)
    line_z = m["y"] + CORNER_LIFT * uu * uu - 0.0003 * qq
    bow = 1 - 0.22 * np.exp(-(uu / 0.11) ** 2)
    top_z = line_z + (m["top"] - m["y"]) * qq ** 0.55 * bow
    bot_z = line_z - (m["y"] - m["bottom"]) * qq ** 0.5
    fade = smoothstep(1.0, 0.82, np.abs(uu))
    up = (1 - smoothstep(-aa, aa, np.maximum(pz - top_z, line_z - pz))) * fade
    lo = (1 - smoothstep(-aa, aa, np.maximum(bot_z - pz, pz - line_z))) * fade
    # soft edges: lips fade into the skin instead of a cut-out shape
    up = up * smoothstep(0.0, 0.0009, top_z - pz + 0.0003)
    lo = lo * smoothstep(0.0, 0.0016, pz - bot_z + 0.0004)
    over(img, SKIN_LIP_U, up * 0.80)
    lcol = SKIN_LIP_L[None, None, :] * (1 + 0.15 * np.exp(-((pz - (line_z - (m["y"] - m["bottom"]) * 0.45))
                                                             / 0.0018) ** 2 - (uu / 0.5) ** 2))[..., None]
    a = (lo * 0.70)[..., None]
    img[:] = img * (1 - a) + lcol * a
    dline = np.abs(pz - line_z) - 0.00032 * (0.5 + 0.5 * qq)
    over(img, (0.17, 0.09, 0.075), (1 - smoothstep(-aa, aa, dline)) * (np.abs(uu) < 1.04) * 0.8)
    # tiny smile tucks at the corners
    for sx in (-1, 1):
        cxk = mx + sx * half * 1.03
        dk, tk = seg_dist(px, pz, (cxk, m["y"] + CORNER_LIFT * 0.8), (cxk + sx * 0.0018, m["y"] + CORNER_LIFT + 0.0016))
        over(img, (0.26, 0.15, 0.12), (1 - smoothstep(-aa, aa * 2, dk - 0.0002)) * 0.32)
    # TRELLIS fringe flakes at her right temple (same polygons as the atlas fix): hair-dark, soft 1-px edge
    shm = in_shards(px, pz).astype(np.float32)[..., None]
    shm = np.clip(_blur(shm, 1) * 1.6, 0, 1)
    img = img * (1 - shm) + SHARD_HAIR[None, None, :] * shm
    out = dilate(np.clip(img, 0, 1), valid)
    return np.concatenate([out, np.ones((N, N, 1), np.float32)], axis=2)
