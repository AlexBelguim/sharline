"""Face repaint for KESTREL (pure numpy, runs in Blender and in plain Python).

The TRELLIS face texture is ~1.2 mm/texel, spread over dozens of tiny UV charts. Instead of editing the atlas, we
work on a FRONT-PROJECTED CANVAS of the face (x, z plane, 0.5 mm pixels):

  1. splat the front-most non-hair face texels into the canvas (their object-space positions come from a bake);
  2. build a clean skin layer (skin texels only, hole-filled, softly blurred);
  3. in the edit regions (both eyes + brows + the old baked lens on her left) replace the TRELLIS paint with the
     clean skin plus procedurally drawn features: almond eyes with a brown iris, a dark upper lash line, and
     straight, determined brows (inner end lower), all mirror-symmetric about the face's symmetry plane;
  4. write the canvas back into the texels that see it (front-facing, front layer, not hair), feathered.

Her LEFT eye gets the same paint as her right eye (mirrored), so it reads correctly through the teal glass lens.
Colours are sRGB-encoded 0..1.
"""
import numpy as np

# canvas frame (metres) and resolution
X0, X1, Z0, Z1, RES = -0.115, 0.125, 1.420, 1.640, 0.0005

# symmetry plane (same as kes_lib.FACE_MID / FACE_N)
_MID = np.array([0.005, -0.05, 0.0])
_phi = np.radians(-2.0)
_N = np.array([np.cos(_phi), np.sin(_phi), 0.0])


def mirror(P):
    d = ((P - _MID) * _N).sum(-1, keepdims=True)
    return P - 2.0 * d * _N


# ------------------------------------------------------------------------------------------------- basics
def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lum(c):
    return c[..., :3].mean(-1)


def hair_mask(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    L = lum(c)
    return ((b - r > 0.03) & (L < 0.34)) | ((b >= r - 0.005) & (L < 0.11))


def skin_mask(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    return (r > 0.62) & (r - b > 0.28) & (r > g + 0.15)


def blur(img, sigma):
    """Separable gaussian blur (sigma in pixels) for 2D or 3D arrays."""
    if sigma <= 0:
        return img
    rad = int(3 * sigma + 0.5)
    k = np.exp(-0.5 * (np.arange(-rad, rad + 1) / sigma) ** 2)
    k /= k.sum()
    out = img.astype(np.float64)
    for ax in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[ax] = (rad, rad)
        p = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        for i, kv in enumerate(k):
            sl = [slice(None)] * out.ndim
            sl[ax] = slice(i, i + out.shape[ax])
            acc += kv * p[tuple(sl)]
        out = acc
    return out


def push_pull(img, w, levels=10):
    """Fill pixels with zero weight from their neighbourhood (pyramid push-pull). img (H,W,C), w (H,W) in 0..1."""
    img = img.astype(np.float64)
    w = w.astype(np.float64)
    pyr = [(img * w[..., None], w)]
    for _ in range(levels):
        a, b = pyr[-1]
        H, W = b.shape
        if H < 2 or W < 2:
            break
        H2, W2 = H // 2 * 2, W // 2 * 2
        a = a[:H2, :W2]
        b = b[:H2, :W2]
        a2 = a.reshape(H2 // 2, 2, W2 // 2, 2, -1).sum((1, 3))
        b2 = b.reshape(H2 // 2, 2, W2 // 2, 2).sum((1, 3))
        pyr.append((a2, b2))
    # pull: coarse -> fine
    a, b = pyr[-1]
    col = a / np.maximum(b, 1e-9)[..., None]
    for a, b in reversed(pyr[:-1]):
        H, W = b.shape
        up = np.repeat(np.repeat(col, 2, 0), 2, 1)
        up = np.pad(up, ((0, max(0, H - up.shape[0])), (0, max(0, W - up.shape[1])), (0, 0)), mode="edge")[:H, :W]
        own = a / np.maximum(b, 1e-9)[..., None]
        t = np.clip(b, 0, 1)[..., None]
        col = own * t + up * (1 - t)
    return col


def to_px(x, z):
    return (x - X0) / RES, (Z1 - z) / RES


def canvas_shape():
    return int(round((Z1 - Z0) / RES)), int(round((X1 - X0) / RES))


def splat(P, C, sel):
    """Average-splat texels into the canvas. Returns colour (H,W,3) and weight (H,W)."""
    H, W = canvas_shape()
    px, pz = to_px(P[sel, 0], P[sel, 2])
    ix = np.clip(np.round(px).astype(int), 0, W - 1)
    iz = np.clip(np.round(pz).astype(int), 0, H - 1)
    acc = np.zeros((H, W, 3))
    cnt = np.zeros((H, W))
    np.add.at(acc, (iz, ix), C[sel, :3])
    np.add.at(cnt, (iz, ix), 1)
    col = acc / np.maximum(cnt, 1)[..., None]
    return col, (cnt > 0).astype(np.float64)


def sample(canvas, x, z):
    """Bilinear sample of the canvas at object-space (x, z)."""
    H, W = canvas.shape[:2]
    px, pz = to_px(x, z)
    px = np.clip(px, 0, W - 1.001)
    pz = np.clip(pz, 0, H - 1.001)
    x0 = np.floor(px).astype(int)
    z0 = np.floor(pz).astype(int)
    fx = (px - x0)[..., None]
    fz = (pz - z0)[..., None]
    c = canvas if canvas.ndim == 3 else canvas[..., None]
    v = (c[z0, x0] * (1 - fx) * (1 - fz) + c[z0, x0 + 1] * fx * (1 - fz) + c[z0 + 1, x0] * (1 - fx) * fz
         + c[z0 + 1, x0 + 1] * fx * fz)
    return v if canvas.ndim == 3 else v[..., 0]


def front_layer(P, valid, tol=0.004, cell=0.001):
    """True for texels within tol of the front-most valid texel in their (x, z) cell."""
    gx = np.floor((P[:, 0] - X0) / cell).astype(int)
    gz = np.floor((P[:, 2] - Z0) / cell).astype(int)
    Wc = int((X1 - X0) / cell) + 2
    Hc = int((Z1 - Z0) / cell) + 2
    ok = valid & (gx >= 0) & (gx < Wc) & (gz >= 0) & (gz < Hc)
    zb = np.full((Hc, Wc), 9.0)
    np.minimum.at(zb, (gz[ok], gx[ok]), P[ok, 1])
    # a 3x3 min so sparse cells do not let back layers through
    zp = np.pad(zb, 1, constant_values=9.0)
    zb3 = np.min([zp[1 + dy:1 + dy + Hc, 1 + dx:1 + dx + Wc] for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=0)
    out = np.zeros(len(P), bool)
    out[ok] = P[ok, 1] < zb3[gz[ok], gx[ok]] + tol
    return out


# ------------------------------------------------------------------------------------------ feature shapes
# All feature coordinates are for her RIGHT eye (x < mid) in the front projection; the left side is mirrored.
EYE = dict(
    inner=(-0.0045, 1.5185),      # inner corner (near the nose)
    outer=(-0.0515, 1.5210),      # outer corner (slightly raised: almond)
    top=1.5262,                   # upper lid apex height (= the geometric lid edge)
    top_x=-0.0260,
    bot=1.5118,                   # lower lid low point
    bot_x=-0.0300,
    iris=(-0.0280, 1.5186),       # iris centre (top slightly hidden by the upper lid: calm, determined)
    iris_r=0.0066,
    pupil_r=0.0026,
)
BROW = [  # (x, z, half-thickness) along the brow, inner -> outer: straight, inner end lower and thicker
    (-0.0065, 1.5380, 0.0029),
    (-0.0150, 1.5414, 0.0031),
    (-0.0290, 1.5452, 0.0027),
    (-0.0430, 1.5476, 0.0019),
    (-0.0545, 1.5480, 0.0010),
]

SCLERA = np.array([0.90, 0.86, 0.80])
IRIS_OUT = np.array([0.16, 0.09, 0.06])
IRIS_IN = np.array([0.40, 0.24, 0.13])
PUPIL = np.array([0.04, 0.025, 0.02])
LASH = np.array([0.07, 0.045, 0.045])
LOWLID = np.array([0.55, 0.33, 0.26])
BROWC = np.array([0.075, 0.075, 0.12])   # blue-black like the hair


def _lid_curves(u, v):
    """Upper / lower lid heights at x=u (parabolic-ish almond through the corners and apexes)."""
    xi, zi = EYE["inner"]
    xo, zo = EYE["outer"]
    t = np.clip((u - xi) / (xo - xi), 0.0, 1.0)  # 0 inner .. 1 outer
    base = zi + (zo - zi) * t
    ta = (EYE["top_x"] - xi) / (xo - xi)
    tb = (EYE["bot_x"] - xi) / (xo - xi)
    # asymmetric bumps (power curves peaking at ta / tb)
    def bump(t, tp):
        s = np.where(t < tp, t / tp, (1 - t) / (1 - tp))
        return np.sin(np.clip(s, 0, 1) * np.pi / 2) ** 1.2
    up = base + (EYE["top"] - (zi + (zo - zi) * ta)) * bump(t, ta)
    lo = base - ((zi + (zo - zi) * tb) - EYE["bot"]) * bump(t, tb)
    inside_x = (u - xi) * (u - xo) < 0
    return up, lo, inside_x, t


def _seg_dist(px, pz, ax, az, bx, bz):
    vx, vz = bx - ax, bz - az
    L2 = vx * vx + vz * vz
    t = np.clip(((px - ax) * vx + (pz - az) * vz) / L2, 0, 1)
    dx = px - (ax + t * vx)
    dz = pz - (az + t * vz)
    return np.hypot(dx, dz), t


def paint_features(u, v, skin):
    """Paint eye + brow onto `skin` (N,3) at right-side coordinates (u, v). Returns colour and a coverage alpha."""
    col = skin.copy()
    up, lo, inside_x, t = _lid_curves(u, v)
    aa = 0.0009  # anti-alias width (m); the face texture is ~1.2 mm/texel
    # ---------------- eye opening
    a_open = smoothstep(-aa, aa, up - v) * smoothstep(-aa, aa, v - lo) * inside_x
    d_ir = np.hypot(u - EYE["iris"][0], v - EYE["iris"][1])
    sclera = SCLERA * (0.88 + 0.12 * smoothstep(EYE["top"] - 0.004, lo + 0.002, v))[..., None]  # lid shadow
    sclera = sclera * (0.85 + 0.15 * np.sin(np.clip(t, 0, 1) * np.pi))[..., None]                 # corners darker
    ir_t = np.clip(d_ir / EYE["iris_r"], 0, 1)[..., None]
    iris = IRIS_IN * (1 - ir_t) + IRIS_OUT * ir_t
    iris = np.where((d_ir < EYE["pupil_r"])[..., None], PUPIL, iris)
    a_iris = smoothstep(EYE["iris_r"] + aa * 0.6, EYE["iris_r"] - aa * 0.6, d_ir)
    eye = sclera * (1 - a_iris[..., None]) + iris * a_iris[..., None]
    # specular dot (upper outer)
    hl = smoothstep(0.0016, 0.0010, np.hypot(u - (EYE["iris"][0] - 0.0028), v - (EYE["iris"][1] + 0.0030)))
    eye = eye * (1 - hl[..., None]) + np.array([0.97, 0.97, 0.95]) * hl[..., None]
    col = col * (1 - a_open[..., None]) + eye * a_open[..., None]
    # ---------------- upper lash line (thick, with a short wing past the outer corner)
    d_up = np.abs(v - up)
    thick = 0.0011 + 0.0012 * np.clip(t, 0, 1)
    a_lash = smoothstep(thick + aa, thick - aa * 0.3, d_up) * (smoothstep(-0.002, 0.0005, u - EYE["inner"][0]) * 0 + 1)
    a_lash *= ((u - EYE["inner"][0]) * (u - EYE["outer"][0] - 0.004) < 0)
    # wing: a tapered segment from the outer corner up/out
    xo, zo = EYE["outer"]
    dw, tw = _seg_dist(u, v, xo + 0.002, zo + 0.0005, xo - 0.0055, zo + 0.0035)
    a_wing = smoothstep(0.0012 * (1 - tw) + 0.0003 + aa, 0.0012 * (1 - tw), dw)
    a_l = np.maximum(a_lash * (v > up - 0.0004 - thick * 0.6), a_wing)
    col = col * (1 - a_l[..., None]) + LASH * a_l[..., None]
    # ---------------- lower lid line (thin, soft brown)
    d_lo = np.abs(v - lo)
    a_lo = smoothstep(0.0007 + aa, 0.0003, d_lo) * inside_x * (0.35 + 0.45 * np.clip(t, 0, 1))
    col = col * (1 - a_lo[..., None]) + LOWLID * a_lo[..., None]
    # ---------------- crease shadow above the upper lid
    d_cr = (up + 0.0035) - v
    a_cr = smoothstep(0.0022, 0.0, np.abs(d_cr)) * inside_x * 0.18
    col = col * (1 - a_cr[..., None] * 0.35)
    # ---------------- brow (tapered polyline)
    a_b = np.zeros_like(u)
    for (ax, az, ar), (bx, bz, br) in zip(BROW[:-1], BROW[1:]):
        d, ts = _seg_dist(u, v, ax, az, bx, bz)
        r = ar + (br - ar) * ts
        a_b = np.maximum(a_b, smoothstep(r + aa, r - aa * 0.5, d))
    # inner end squared off slightly (no point)
    col = col * (1 - a_b[..., None]) + BROWC * a_b[..., None]
    alpha = np.clip(np.maximum.reduce([a_open, a_l, a_lo, a_b]), 0, 1)
    return col, alpha


MOUTH_C = (0.010, 1.4585)       # mouth centre (front projection); the TRELLIS mouth line sits at z ~1.458-1.46
MOUTH_HW = 0.0215               # half width of the new mouth line
MOUTH_DROP = 0.0016             # the corners sit this much lower than the centre (calm, determined)
LIPLINE = np.array([0.42, 0.22, 0.20])


def mouth_region(x, z):
    """Where the TRELLIS pout (full pink lips) is replaced: an ellipse around the mouth, feathered."""
    e = np.hypot((x - MOUTH_C[0]) / 0.034, (z - MOUTH_C[1] + 0.001) / 0.0125)
    return 1.0 - smoothstep(0.72, 1.0, e)


def paint_mouth(x, z, skin):
    """Review round 2: a narrow, straight mouth with slightly down-turned corners on clean skin (the TRELLIS mouth
    read as a pout). A thin dark rose line, a faint shadow under the lower lip, a touch of colour on the lower lip."""
    col = skin.copy()
    t = np.clip((x - MOUTH_C[0]) / MOUTH_HW, -1.0, 1.0)
    zl = MOUTH_C[1] - MOUTH_DROP * t ** 2                      # gentle downward arc to the corners
    inside = np.abs(x - MOUTH_C[0]) < MOUTH_HW
    taper = 1.0 - smoothstep(0.65, 1.0, np.abs(t))             # thinner and fainter toward the corners
    half = 0.0008 + 0.0005 * taper
    a_line = smoothstep(half + 0.0009, half - 0.0003, np.abs(z - zl)) * inside * (0.55 + 0.45 * taper)
    # lower lip: a slightly rosier band 1-4 mm under the line, and its soft shadow at ~6 mm
    d = zl - z
    a_lip = smoothstep(0.0005, 0.0015, d) * (1 - smoothstep(0.0032, 0.0045, d)) * inside * taper * 0.22
    a_sh = smoothstep(0.0045, 0.0060, d) * (1 - smoothstep(0.0065, 0.0085, d)) * inside * taper * 0.10
    col = col * (1 - a_lip[:, None]) + (skin * np.array([0.98, 0.80, 0.80])) * a_lip[:, None]
    col = col * (1 - a_sh[:, None] * 0.6)
    col = col * (1 - a_line[:, None]) + LIPLINE * a_line[:, None]
    return col


def edit_weight(u, v):
    """Where the TRELLIS paint is replaced (right-side coords): eye + brow band, feathered."""
    e = np.hypot((u + 0.027) / 0.040, (v - 1.530) / 0.031)
    return 1.0 - smoothstep(0.80, 1.0, e)


def strap_zone(u, v):
    """Her right forehead: TRELLIS painted the eyepiece strap across the brow (dark, hair-like texels). Inside this
    zone dark texels are skin to be repainted, not fringe hair."""
    return (v > 1.532) & (v < 1.559) & (u > -0.044 - np.clip(1.556 - v, 0, 1) * 0.8) & (u < _MID[0] + 0.003)


def lens_region_weight(x, z):
    """Her LEFT side: the old baked lens + frame + strap band, replaced completely by the mirrored paint."""
    e = np.hypot((x - 0.050) / 0.050, (z - 1.522) / 0.040)
    return 1.0 - smoothstep(0.85, 1.0, e)


# the baked lens disc (kept as the eye surface behind the new glass; its side walls hide inside the new frame)
DISC_C = (0.052, 1.512)
DISC_R = (0.034, 0.029)
GRAPHITE = np.array([0.12, 0.125, 0.14])


def disc_weight(x, z, grow=1.0):
    e = np.hypot((x - DISC_C[0]) / (DISC_R[0] * grow), (z - DISC_C[1]) / (DISC_R[1] * grow))
    return 1.0 - smoothstep(0.9, 1.0, e)


# ---------------------------------------------------------------------------------------------- main entry
def repaint_face(P, N, C, cov, patch=None):
    """P, N: (H,W,3) object-space position / normal per texel; C: (H,W,3|4) sRGB colour; cov: (H,W) bool;
    patch: (H,W) bool texels of the rebuilt left-eye area (stage A, kes_geo) - new UV space without paint, so
    they are painted completely (mirrored skin + eye + brow) and never read.
    Returns the new colour array (same shape as C) and a dict of debug canvases."""
    Hh, Ww = cov.shape
    C = C.copy()
    if patch is None:
        patch = np.zeros(cov.shape, bool)
    flat = cov & (P[..., 2] > Z0) & (P[..., 2] < Z1) & (P[..., 0] > X0) & (P[..., 0] < X1) & (P[..., 1] < 0.04)
    flat |= patch & cov
    idx = np.where(flat.ravel())[0]
    p = P.reshape(-1, 3)[idx].astype(np.float64)
    n = N.reshape(-1, 3)[idx].astype(np.float64)
    c = C.reshape(-1, C.shape[-1])[idx, :3].astype(np.float64)
    pt = patch.ravel()[idx]
    c[pt] = (0.90, 0.62, 0.50)               # neutral skin placeholder (never splatted, always overwritten)
    facing = n[:, 1] < -0.15
    hair = hair_mask(c) & ~pt
    nonhair = facing & ~hair
    fl = front_layer(p, nonhair)
    sel = nonhair & fl & ~pt
    # ---- canvas of the current paint and a clean skin layer
    canvas, w = splat(p, c, sel)
    canvas = push_pull(canvas, w)
    sk = sel & skin_mask(c)
    skin_c, skin_w = splat(p, c, sk)
    skin = push_pull(skin_c, skin_w)
    skin = blur(skin, 3.0)
    # ---- right-side coordinates for every texel (mirror the left side)
    q = p.copy()
    left = p[:, 0] > _MID[0]
    q[left] = mirror(p[left])
    u, v = q[:, 0], q[:, 2]
    base_skin = sample(skin, u, v)
    col, a = paint_features(u, v, base_skin)
    # ---- weights: edit region (both sides) + the old lens region on her left
    w_edit = np.maximum(edit_weight(u, v), np.where(left, lens_region_weight(p[:, 0], p[:, 2]), 0.0))
    # facing feather and front layer
    w_face = smoothstep(-0.15, -0.45, n[:, 1]) * fl * ~hair
    # on her left, the lens region is replaced even where TRELLIS painted it hair-dark (frame / strap band)
    w_face_l = smoothstep(-0.15, -0.45, n[:, 1]) * front_layer(p, facing) * (lens_region_weight(p[:, 0], p[:, 2]) > 0.01)
    w_face = np.where(left, np.maximum(w_face, w_face_l * ~(hair & (p[:, 0] > 0.085))), w_face)
    # her right forehead: the baked strap band (dark texels in the strap zone, on the skin surface)
    w_strap = smoothstep(-0.15, -0.45, n[:, 1]) * front_layer(p, facing) * strap_zone(u, v) * ~left
    w_face = np.maximum(w_face, w_strap)
    W = np.clip(w_edit * w_face, 0, 1)
    W[pt] = 1.0                              # the new patch is painted completely
    new = c * (1 - W[:, None]) + col * W[:, None]
    # disc side walls (inside the new eyepiece frame): graphite
    # her right cheek beside the fringe: TRELLIS painted a brown smear there -> clean skin
    e_ch = np.hypot((p[:, 0] + 0.056) / 0.016, (p[:, 2] - 1.497) / 0.030)
    w_ch = (1.0 - smoothstep(0.6, 1.0, e_ch)) * (~left) * (~hair) * smoothstep(-0.05, -0.35, n[:, 1]) * fl
    skin_here = sample(skin, p[:, 0], p[:, 2])
    new = new * (1 - 0.85 * w_ch[:, None]) + skin_here * (0.85 * w_ch[:, None])
    # her left temple: the baked strap / wire scribbles between the eye and the ear -> flat local skin (the new
    # strap runs here). Side-facing, so no canvas: use the mean of the clean skin texels around it.
    tz = left & (p[:, 0] > 0.062) & (p[:, 1] > -0.048) & (p[:, 1] < 0.006) & (p[:, 2] > 1.503) & (p[:, 2] < 1.562)
    ring = left & (p[:, 0] > 0.055) & (p[:, 1] > -0.06) & (p[:, 1] < 0.02) & (p[:, 2] > 1.47) & (p[:, 2] < 1.59)
    sk_ring = ring & skin_mask(c) & ~tz
    if sk_ring.sum() > 20:
        skin_t = np.median(c[sk_ring], axis=0)
        dirty = tz & ~skin_mask(new) & (lum(new) < 0.45) & ~(hair_mask(c) & (p[:, 1] > -0.005))
        new[dirty] = skin_t
    # her left eye area: stage A (kes_geo.rebuild_left_eye) flattened the old baked lens disc onto a mirrored eye
    # socket. Texels the canvas repaint did not reach (side-facing, inner layers) but that still carry the disc's
    # light-blue paint or its dark frame/strap paint become local skin (sampled at the mirrored position)
    real_hair = hair & ((p[:, 2] > 1.553) | (p[:, 0] > 0.088))
    lensreg = left & (lens_region_weight(p[:, 0], p[:, 2]) > 0.2)
    walls = lensreg & (W < 0.5) & ~skin_mask(new) & ~real_hair
    new[walls] = sample(skin, u[walls], v[walls])
    # her right cheek beside the fringe (review round 2): TRELLIS left two dark vertical lines on the cheek next to
    # the strand. Dark texels that lie ON the cheek surface (within 2.5 mm of the skin depth at their (x, z)), not
    # on the strand hanging in front of it, become local skin.
    zone = (p[:, 0] > -0.068) & (p[:, 0] < -0.030) & (p[:, 2] > 1.435) & (p[:, 2] < 1.515) & (n[:, 1] < -0.1)
    if zone.any():
        skd, skw = splat(np.c_[p[:, 0], p[:, 1], p[:, 2]], np.repeat(p[:, 1:2], 3, 1), sk)
        skin_y = push_pull(skd, skw)[..., 0]
        sy = sample(skin_y, p[:, 0], p[:, 2])
        on_cheek = zone & (np.abs(p[:, 1] - sy) < 0.0025) & (lum(new) < 0.5) & ~skin_mask(new)
        new[on_cheek] = sample(skin, p[on_cheek, 0], p[on_cheek, 2])
    # dark painted strokes on the cheeks and along the jaw (TRELLIS baked dotted outline strokes there): skin texels
    # much darker than the clean local skin, away from the painted features (eyes, brows, lens area, mouth, nose),
    # become local skin
    skin_here = sample(skin, p[:, 0], p[:, 2])
    feat = (edit_weight(u, v) > 0.02) | (left & (lens_region_weight(p[:, 0], p[:, 2]) > 0.02)) |         (mouth_region(p[:, 0], p[:, 2]) > 0.02) | ((np.abs(p[:, 0] - 0.006) < 0.022) & (p[:, 2] > 1.462)) | pt
    strokes = (p[:, 2] > 1.415) & (p[:, 2] < 1.53) & (p[:, 1] < -0.005) & ~hair & ~feat &         (lum(new) < 0.78 * lum(skin_here)) & (np.abs(p[:, 0] - 0.005) < 0.075)
    new[strokes] = skin_here[strokes]
    # ... and the near-black dotted strokes along the face outline, which the colour tests take for hair: dark
    # texels whose ~1 cm neighbourhood is mostly skin (real hair locks are large dark areas)
    from kes_fix import _voxel_frac
    zone = (p[:, 2] > 1.415) & (p[:, 2] < 1.53) & (p[:, 1] < 0.0) & (np.abs(p[:, 0] - 0.005) < 0.085)
    if zone.sum() > 100:
        dark = zone & ~feat & (hair_mask(new) | (lum(new) < 0.30))
        frac = np.zeros(len(p))
        frac[zone] = _voxel_frac(p[zone], skin_mask(new[zone]), np.ones(int(zone.sum()), bool), 0.0035)
        dots = dark & (frac > 0.55)
        new[dots] = skin_here[dots]
    # the mouth: clean skin + a narrow straight mouth (front-facing front-layer skin only)
    w_m = mouth_region(p[:, 0], p[:, 2]) * smoothstep(-0.2, -0.5, n[:, 1]) * fl * ~hair
    if (w_m > 0).any():
        mcol = paint_mouth(p[:, 0], p[:, 2], sample(skin, p[:, 0], p[:, 2]))
        new = new * (1 - w_m[:, None]) + mcol * w_m[:, None]
    out = C.reshape(-1, C.shape[-1])
    out[idx, :3] = new
    # normal / AO flattening weight: full on the disc and the strap zone, half over the repainted right eye
    fw = np.maximum(np.where(left, lens_region_weight(p[:, 0], p[:, 2]), 0.0), 0.5 * W)
    fw = np.maximum(fw, W * (strap_zone(u, v) & ~left))
    flat_w = np.zeros(Hh * Ww)
    flat_w[idx] = np.clip(fw, 0, 1) * (w_face > 0)
    flat_w[idx[walls]] = 1.0
    flat_w[idx[pt]] = 1.0
    flat_w[idx] = np.maximum(flat_w[idx], 0.7 * w_m)
    dbg = dict(canvas=canvas, skin=skin, flat_w=flat_w.reshape(Hh, Ww))
    return out.reshape(C.shape), dbg
