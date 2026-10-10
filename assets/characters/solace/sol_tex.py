"""Texel-space texture fixes for SOLACE (numpy only, so it runs inside Blender or a plain Python).

Inputs are the TRELLIS base colour (sRGB 0..1, H x W x 3) and per-texel object-space position / normal maps baked
from the stage-A mesh (coverage mask = texels used by visible faces). Everything is decided per texel from colour +
3D position, so it works across the fragmented TRELLIS UV atlas.

Fixes (see NOTES.md):
  - skin regraded toward the brief's "skin deep" (warmer, less orange)
  - face: eye/brow smears erased against a 3D-blurred skin field, then clean painted eyes, brows and lips
  - pants: light grey -> sand; pouch: black -> dark sand (brief: sand pouch)
  - old TRELLIS shoulder mark (coral strokes on her left upper arm) painted out (a Bloom decal replaces it)
  - hair: metallic removed, slightly lifted dark warm brown
  - new ORM: no baked AO, stylised matte roughness per material class, metal 0
"""
import numpy as np

# face layout measured on the stage-A mesh (front projection x, z; metres). Face midline ~x 0.001.
XM = 0.001
EYES = {"R": dict(c=(-0.0355, 1.5468), w=0.0128), "L": dict(c=(0.0375, 1.5468), w=0.0128)}
BROWS = {"R": [(-0.0090, 1.5600, 0.0023), (-0.0290, 1.5668, 0.0019), (-0.0470, 1.5612, 0.0007)],
         "L": [(0.0110, 1.5600, 0.0023), (0.0310, 1.5668, 0.0019), (0.0490, 1.5612, 0.0007)]}
MOUTH = dict(y=1.4752, xl=-0.0242, xr=0.0248, top=1.4808, bottom=1.4632)

SKIN_T = np.array([0.475, 0.335, 0.262])     # target mid skin (sRGB): round 2 ~11 % less saturated (less orange), toward skin deep
SAND_T = np.array([0.655, 0.595, 0.495])    # pants mid sand (sRGB)
POUCH_T = np.array([0.50, 0.44, 0.35])      # pouch: a darker sand
HAIR_T = np.array([0.105, 0.068, 0.056])    # hair mid (sRGB): dark warm brown-black (brief M_SOL_Hair, a bit deeper)
HAIR_ROUGH = 0.80                            # stylised matte hair (TRELLIS hair read as silver-grey plastic at 0.58)

# TRELLIS fringe flakes at her RIGHT temple that carry skin colour (front projection x, z; measured on an ortho
# capture of the finished head). Everything inside is painted hair-dark on the atlas (front half only) and on the
# face texture, so the hair edge reads clean: the notch above the right brow and the flap/crumple at the outer
# corner of the right eye.
SHARD_POLYS = [
    [(-0.0545, 1.5555), (-0.0373, 1.5675), (-0.0365, 1.5830), (-0.0560, 1.5830)],
    [(-0.0660, 1.5600), (-0.0530, 1.5570), (-0.0545, 1.5500), (-0.0532, 1.5458), (-0.0508, 1.5410),
     (-0.0560, 1.5380), (-0.0665, 1.5420)],
]
SHARD_HAIR = np.array([0.095, 0.062, 0.050])  # a shade darker than HAIR_T (the flakes sit in the hair's shadow)


def in_poly(px, pz, poly):
    """Even-odd point-in-polygon test, vectorised over px, pz."""
    inside = np.zeros(np.shape(px), bool)
    n = len(poly)
    for i in range(n):
        x1, z1 = poly[i]
        x2, z2 = poly[(i + 1) % n]
        cond = (z1 > pz) != (z2 > pz)
        xc = x1 + (pz - z1) * (x2 - x1) / ((z2 - z1) if z2 != z1 else 1e-12)
        inside ^= cond & (px < xc)
    return inside


def in_shards(px, pz):
    m = np.zeros(np.shape(px), bool)
    for poly in SHARD_POLYS:
        m |= in_poly(px, pz, poly)
    return m
IVORY_T = np.array([0.845, 0.822, 0.775])   # ivory (TRELLIS ivory nudged toward the palette)


def lum(c):
    return c[..., :3].mean(-1)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def box_blur_3d(g, w, r):
    """Weighted separable box blur of a voxel grid g (X,Y,Z,C) with weights w (X,Y,Z)."""
    gw = g * w[..., None]
    for ax in range(3):
        gw = _box1d(gw, r, ax)
        w = _box1d(w[..., None], r, ax)[..., 0]
    return gw / np.maximum(w, 1e-6)[..., None], w


def _box1d(a, r, ax):
    c = np.cumsum(np.pad(a, [(r + 1, r) if i == ax else (0, 0) for i in range(a.ndim)], mode="edge"), axis=ax)
    n = a.shape[ax]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=ax)
    lo = np.take(c, np.arange(0, n), axis=ax)
    return (hi - lo) / (2 * r + 1)


class Field3D:
    """Colour field on a voxel grid built from sample texels (position, colour), blurred, sampled anywhere."""

    def __init__(self, P, C, lo, hi, vox=0.004, blur=2):
        self.lo = np.asarray(lo, float)
        self.vox = vox
        shape = np.ceil((np.asarray(hi) - self.lo) / vox).astype(int) + 1
        idx = np.clip(((P - self.lo) / vox).astype(int), 0, shape - 1)
        g = np.zeros((*shape, 3))
        w = np.zeros(shape)
        np.add.at(g, (idx[:, 0], idx[:, 1], idx[:, 2]), C)
        np.add.at(w, (idx[:, 0], idx[:, 1], idx[:, 2]), 1.0)
        g = g / np.maximum(w, 1)[..., None]
        w = (w > 0).astype(float)
        for r in (blur, blur * 2, blur * 4):    # widen until empty voxels are covered
            gb, wb = box_blur_3d(g, w, r)
            fill = (w == 0) & (wb > 1e-4)
            g[fill] = gb[fill]
            w = np.maximum(w, fill.astype(float) * 0.5)
        self.g, _ = box_blur_3d(g, (w > 0).astype(float), max(1, blur // 2))
        self.shape = shape

    def __call__(self, P):
        idx = np.clip(np.round((P - self.lo) / self.vox).astype(int), 0, self.shape - 1)
        return self.g[idx[:, 0], idx[:, 1], idx[:, 2]]


# ------------------------------------------------------------------------------------------- shapes (x, z)
def seg_dist(px, pz, a, b):
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    t = np.clip(((px - ax) * dx + (pz - az) * dz) / max(dx * dx + dz * dz, 1e-12), 0, 1)
    return np.hypot(px - (ax + t * dx), pz - (az + t * dz)), t


def stroke_sdf(px, pz, pts, samples=24):
    """Signed distance to a tapered stroke through pts [(x, z, radius)] (Catmull-Rom-ish resampled)."""
    pts = np.asarray(pts, float)
    # quadratic-ish resample through the points
    ts = np.linspace(0, 1, samples)
    k = len(pts) - 1
    xs = np.interp(ts * k, np.arange(len(pts)), pts[:, 0])
    zs = np.interp(ts * k, np.arange(len(pts)), pts[:, 1])
    rs = np.interp(ts * k, np.arange(len(pts)), pts[:, 2])
    # smooth the polyline (chaikin-like) to soften the kinks
    for _ in range(2):
        xs[1:-1] = 0.25 * xs[:-2] + 0.5 * xs[1:-1] + 0.25 * xs[2:]
        zs[1:-1] = 0.25 * zs[:-2] + 0.5 * zs[1:-1] + 0.25 * zs[2:]
    d = np.full(px.shape, 1e9)
    for i in range(samples - 1):
        di, t = seg_dist(px, pz, (xs[i], zs[i]), (xs[i + 1], zs[i + 1]))
        r = rs[i] + (rs[i + 1] - rs[i]) * t
        d = np.minimum(d, di - r)
    return d


def eye_shape(px, pz, c, w, side):
    """Almond eye: returns (inside_sdf, upper_lid_dist, lower_lid_dist, u) for texels; side 'L' or 'R'."""
    cx, cz = c
    s = 1.0 if side == "L" else -1.0           # +1 = outer corner toward +x
    u = (px - cx) / w * s                        # -1 inner corner .. +1 outer corner
    tilt = 0.0012                                # outer corner a little higher
    base = cz + tilt * u
    q = np.clip(1 - u * u, 0, 1)
    # upper lid peaks slightly toward the inner third; lower lid is flatter and peaks outward
    zu = base + 0.0056 * q ** 0.75 * (1 - 0.18 * u)
    zl = base - 0.0034 * q ** 0.9 * (1 + 0.12 * u)
    inside = np.maximum.reduce([pz - zu, zl - pz, (np.abs(u) - 1) * w])
    return inside, pz - zu, zl - pz, u, zu, zl


def paint(dst, mask, col, alpha):
    a = (alpha * mask)[..., None]
    dst[:] = dst * (1 - a) + np.asarray(col)[None, :] * a


# ------------------------------------------------------------------------------------------------ main
def process(base, pos, nrm, cov, log=print):
    """Returns (new_base HxWx3 sRGB, orm HxWx3 linear 0..1, debug dict)."""
    H, W = cov.shape
    out = base[..., :3].copy()
    P = pos[cov]
    N = nrm[cov]
    C = out[cov].copy()
    x, y, z = P.T
    L = lum(C)
    sat = C.max(1) - C.min(1)
    cls = np.zeros(len(C), np.int8)   # 0 other, 1 skin, 2 hair, 3 ivory, 4 pants, 5 charcoal, 6 coral, 7 pouch
    head = (z > 1.40)
    skin = head & (C[:, 0] - C[:, 2] > 0.17) & (C[:, 0] > 0.28) & (C[:, 0] < 0.78) & (L > 0.18) & (L < 0.55)
    hair = (L < 0.26) & (C[:, 0] >= C[:, 2] - 0.005) & (z > 1.15) & ~skin
    coral = (C[:, 0] > 0.65) & (C[:, 0] - C[:, 1] > 0.28) & (C[:, 1] - C[:, 2] > -0.02) & ~skin
    ivory = (C.min(1) > 0.66) & (sat < 0.12)
    char = (L < 0.30) & (C[:, 2] >= C[:, 0] - 0.01) & ~hair
    pants = (z < 0.99) & (z > 0.10) & (L > 0.30) & (L < 0.74) & (np.abs(C[:, 0] - C[:, 2]) < 0.09) & ~ivory
    # round 2: grey shading on the coat back (pocket creases) is not pants (it turned into tan specks)
    pants &= ~((y > 0.05) & (z > 0.72) & (np.abs(x) > 0.03))
    # round 2: only the pouch itself (its top edge is Z ~1.012, its inner side X ~-0.085); the old box also turned a
    # rectangle of the charcoal under-layer beside it sand
    pouch = (x < -0.084) & (x > -0.19) & (y < 0.0) & (z > 0.86) & (z < 1.013) & (L < 0.32) & (np.abs(x + 0.125) < 0.06)
    cls[skin] = 1
    cls[hair] = 2
    cls[ivory] = 3
    cls[pants] = 4
    cls[char] = 5
    cls[coral] = 6
    cls[pouch] = 7
    log(f"tex classes: skin {skin.sum()} hair {hair.sum()} ivory {ivory.sum()} pants {pants.sum()} "
        f"charcoal {char.sum()} coral {coral.sum()} pouch {pouch.sum()}")

    # ---------------------------------------------------------------- skin regrade (all skin texels)
    ref = np.median(L[skin])
    tgt = SKIN_T[None, :] * (L[skin] / ref)[:, None] ** 0.9
    C[skin] = C[skin] * 0.15 + tgt * 0.85

    # ---------------------------------------------------------------- face: erase smears, paint features
    face = (z > 1.44) & (z < 1.62) & (np.abs(x - XM) < 0.068) & (y < 0.0) & (N[:, 1] < -0.05)
    # face depth fit (quadratic in x, z) on clean skin texels
    fs = face & skin & (np.abs(x - XM) < 0.055)
    A = np.c_[np.ones(fs.sum()), x[fs], z[fs], x[fs] ** 2, z[fs] ** 2, x[fs] * z[fs]]
    coef = np.linalg.lstsq(A, y[fs], rcond=None)[0]
    yfit = np.c_[np.ones(len(x)), x, z, x ** 2, z ** 2, x * z] @ coef
    on_face = face & (y - yfit > -0.006) & (np.abs(x - XM) < 0.064)
    # erase zones: around eyes (wide, catches the wing smears) and brows, plus the lips
    ez = np.zeros(len(x), bool)
    for side, e in EYES.items():
        cx, cz = e["c"]
        ez |= (((x - cx) / 0.027) ** 2 + ((z - cz) / 0.0125) ** 2) < 1.0
        if side == "L":
            ez |= (x > cx) & (x < cx + 0.032) & (np.abs(z - (cz + 0.002 + (x - cx) * 0.12)) < 0.008)
        else:
            ez |= (x < cx) & (x > cx - 0.024) & (np.abs(z - (cz + 0.002)) < 0.007)
    for side, pts in BROWS.items():
        ez |= stroke_sdf(x, z, [(p[0], p[1], 0.0055) for p in pts]) < 0
    ez |= (np.abs(x - XM) < 0.034) & (z > MOUTH["bottom"] - 0.008) & (z < MOUTH["top"] + 0.004)
    ez &= on_face
    good = skin & ~ez & (z > 1.40) & (z < 1.66)
    lo = P[good].min(0) - 0.02
    hi = P[good].max(0) + 0.02
    fld = Field3D(P[good], C[good], lo, hi, vox=0.004, blur=2)
    C[ez] = fld(P[ez])
    # smooth (blur) the whole facial skin a little: kills TRELLIS blotches, keeps large shading
    fsk = on_face & (skin | ez)
    fld2 = Field3D(P[fsk], C[fsk], lo, hi, vox=0.003, blur=1)
    C[fsk] = C[fsk] * 0.45 + fld2(P[fsk]) * 0.55
    log(f"face: {ez.sum()} texels erased, {fsk.sum()} smoothed")


    # ---------------------------------------------------------------- hair
    hr = np.median(L[hair])
    C[hair] = C[hair] * 0.4 + HAIR_T[None, :] * (L[hair] / hr)[:, None] ** 0.8 * 0.6
    # ---------------------------------------------------------------- pants -> sand, pouch -> dark sand
    pr = np.median(L[pants])
    C[pants] = SAND_T[None, :] * (L[pants] / pr)[:, None] ** 1.1
    pq = np.median(L[pouch]) if pouch.any() else 0.15
    C[pouch] = POUCH_T[None, :] * np.clip((L[pouch] / pq), 0.4, 1.6)[:, None] ** 0.7
    # ---------------------------------------------------------------- ivory nudge
    ir = np.median(L[ivory])
    C[ivory] = C[ivory] * 0.5 + IVORY_T[None, :] * (L[ivory] / ir)[:, None] * 0.5
    # ---------------------------------------------------------------- old shoulder mark on her LEFT upper arm
    arm = (x > 0.15) & (x < 0.36) & (z > 1.15) & (z < 1.44) & (y < 0.09)
    mark = arm & (coral | ((L > 0.30) & (L < 0.76) & ~ivory))
    if mark.any():
        ivs = arm & ivory
        fld3 = Field3D(P[ivs], C[ivs], P[arm].min(0) - 0.02, P[arm].max(0) + 0.02, vox=0.005, blur=2)
        C[mark] = fld3(P[mark])
        log(f"shoulder mark: {mark.sum()} texels painted out")

    # ---------------------------------------------------------------- hair shards over her right temple
    # (TRELLIS fringe flakes carrying skin texels: anything clearly in front of the face surface there -> hair)
    tm = (x < XM - 0.048) & (x > XM - 0.090) & (z > 1.530) & (z < 1.625) & (y - yfit < -0.0025) & skin
    if tm.any():
        C[tm] = HAIR_T[None, :] * (0.8 + 0.4 * (L[tm] / max(L[tm].max(), 1e-3)))[:, None]
        log(f"temple hair shards recoloured: {tm.sum()} texels")
    sh = in_shards(x, z) & (y < -0.01)
    C[sh] = SHARD_HAIR[None, :]
    log(f"temple flakes painted hair-dark: {sh.sum()} texels")
    # ---------------------------------------------------------------- back of the thighs: charcoal -> sand
    # TRELLIS painted the back of both thighs (below the coat tail, above the knee straps) charcoal; the concept
    # (v04 back view) has sand pants there with only a strap band behind the knee.
    # The leg axis per 2 cm slice comes from the robust x/y extents of the pants + charcoal texels of that leg (the
    # stance is asymmetric); only texels within 9 cm of it are legs (the coat tail and its lining hang further out).
    legish = ((cls == 4) | (cls == 5)) & (np.abs(x) < 0.26) & (y > -0.16) & (y < 0.105)
    for sx in (1, -1):
        bt = np.zeros(len(x), bool)
        band = np.zeros(len(x), bool)
        for zs in np.arange(0.46, 0.81, 0.02):
            sl = legish & (np.abs(z - zs) < 0.011) & (sx * x > 0.01)
            if sl.sum() < 50:
                continue
            cx = 0.5 * (np.percentile(x[sl], 4) + np.percentile(x[sl], 96))
            cy = 0.5 * (np.percentile(y[sl], 4) + np.percentile(y[sl], 96))
            inr = sl & (np.hypot(x - cx, y - cy) < 0.090)
            bt |= inr & (cls == 5) & (z > 0.515) & (N[:, 1] > -0.30)
            # whitish (ivory-class) TRELLIS texels on the back thigh, below the coat hem
            bt |= inr & (cls == 3) & (z > 0.515) & (z < 0.60) & (N[:, 1] > 0.0)
            # knee strap band behind the knee: fill light notches so its top edge is a clean line at z 0.515
            band |= inr & ((cls == 4) | (cls == 3)) & (z > 0.472) & (z <= 0.515) & (N[:, 1] > 0.25)
        if bt.any():
            rel = np.clip(L[bt] / max(np.median(L[bt]), 1e-3), 0.5, 1.6)
            C[bt] = SAND_T[None, :] * (0.80 + 0.20 * rel)[:, None] * 0.93
            cls[bt] = 4
        if band.any():
            ref = (cls == 5) & (z > 0.45) & (z < 0.515) & (sx * x > 0.01) & (N[:, 1] > 0.25)
            C[band] = np.median(C[ref], axis=0) if ref.sum() > 20 else np.array([0.20, 0.205, 0.22])
            cls[band] = 5
        log(f"back thigh {sx:+d}: {bt.sum()} charcoal texels -> sand, {band.sum()} band notch texels -> charcoal")
    # (the TRELLIS heal drone is cut out of the body in stage A; SOL_Drone replaces it)
    round2_paint(P, N, C, L, cls, x, y, z, coral, ivory, log)
    out[cov] = np.clip(C, 0, 1)
    out = dilate(out, cov, 10)

    # ---------------------------------------------------------------- ORM (R occlusion, G roughness, B metal)
    rough = np.full(len(C), 0.68)
    rough[cls == 1] = 0.55
    rough[cls == 2] = HAIR_ROUGH
    rough[cls == 3] = 0.66
    rough[cls == 4] = 0.80
    rough[cls == 5] = 0.72
    rough[cls == 6] = 0.55
    rough[cls == 7] = 0.78
    orm = np.ones((H, W, 3), np.float32)
    orm[..., 2] = 0.0
    orm[..., 1] = 0.68
    orm[cov, 1] = rough
    orm = dilate(orm, cov, 10)
    return out, orm, dict(cls=cls)



# ---------------------------------------------------------------------------------------------- round 2 paint
# Hair loop round her LEFT ear (side view, Y/Z, for X > 0.05): the skin inside the loop (the ear and the skin behind
# it) is painted hair-dark, so the strand no longer reads as a headset band (Kestrel's identity element).
EAR_LOOP_L = [(-0.027, 1.590), (-0.026, 1.550), (-0.022, 1.530), (-0.014, 1.515), (-0.004, 1.506), (0.010, 1.502),
              (0.030, 1.498), (0.040, 1.497), (0.058, 1.500), (0.058, 1.590)]
# back pocket flap on the coat (her RIGHT back): creases and specks painted out
POCKET_BOX = (np.array([-0.165, 0.05, 0.942]), np.array([-0.020, 0.20, 1.014]))
CORAL_BAND = 0.012          # coral edge band on the coat hem + back split (brief 4d / concept v04)


def _field_fill(P, C, src, dst, pad=0.03, vox=0.005, blur=2):
    if not src.any() or not dst.any():
        return 0
    lo = np.minimum(P[src].min(0), P[dst].min(0)) - pad
    hi = np.maximum(P[src].max(0), P[dst].max(0)) + pad
    f = Field3D(P[src], C[src], lo, hi, vox=vox, blur=blur)
    C[dst] = f(P[dst])
    return int(dst.sum())


def round2_paint(P, N, C, L, cls, x, y, z, coral, ivory, log=print):
    sat = C.max(1) - C.min(1)
    skinish = (C[:, 0] - C[:, 2] > 0.12) & (C[:, 0] > 0.25) & (L > 0.16) & (L < 0.62)
    # ---- left ear loop -> hair
    ear = (x > 0.05) & (y > -0.03) & (z > 1.49) & (z < 1.60) & in_poly(y, z, EAR_LOOP_L) & skinish
    if ear.any():
        C[ear] = HAIR_T[None, :] * (0.7 + 0.3 * np.clip(L[ear] / max(np.median(L[ear]), 1e-3), 0.5, 1.5))[:, None]
        cls[ear] = 2
    # ---- neck skin behind the jaw and at the nape -> charcoal mock-neck (brief: the mock-neck covers the neck;
    # TRELLIS left crumpled skin-coloured bits there under the hair)
    neck = (z > 1.415) & (z < 1.505) & (y > 0.03) & (np.abs(x) < 0.08) & skinish & ~ear
    ref = (cls == 5) & (z > 1.40) & (z < 1.47) & (y < -0.02) & (np.abs(x) < 0.05)
    mock = np.median(C[ref], axis=0) if ref.sum() > 30 else np.array([0.13, 0.135, 0.15])
    if neck.any():
        # soft edge toward the jaw: full mock-neck colour behind Y 0.055 (the nape), blended in from Y 0.03
        w = smoothstep(0.03, 0.055, y[neck])[:, None]
        C[neck] = C[neck] * (1 - w) + w * mock[None, :] * (0.8 + 0.2 * np.clip(L[neck] / max(np.median(L[neck]), 1e-3),
                                                                             0.5, 1.5))[:, None]
        cls[neck] = 5
    # ---- scratches on the jacket by her left strap (grey marks on ivory) -> ivory
    chest = (x > 0.08) & (x < 0.17) & (z > 1.15) & (z < 1.42) & (y < 0.09)
    scr = chest & (L > 0.32) & (L < 0.74) & (sat < 0.10) & ~ivory & ~coral
    n_scr = _field_fill(P, C, chest & ivory, scr)
    # ---- back pocket flap -> plain ivory (creases, tan specks)
    lo, hi = POCKET_BOX
    pk = np.all((P > lo) & (P < hi), axis=1) & (cls != 6)
    ring = np.all((P > lo - 0.03) & (P < hi + 0.03), axis=1) & ivory & ~pk
    n_pk = _field_fill(P, C, ring, pk)
    cls[pk] = 3
    # ---- coral band on the coat hem (back + sides) and the back split edges
    coat = ~np.isin(cls, (1, 2, 4, 5, 7)) & (z < 0.86) & (z > 0.575) & (y > -0.08) & (np.abs(x) < 0.30)
    cc = np.median(C[coral], axis=0) if coral.sum() > 50 else np.array([0.95, 0.45, 0.38])
    # the hem is a fold (outer + inner surface), not a mesh boundary: its rim texels face down; the back-split rims
    # face the split. Band = coat texels within CORAL_BAND of a rim texel (3 mm voxel grid, dilated)
    sgn = np.sign(x)
    # lowest coat texel per 1-degree sector around the body axis: down-facing creases higher up are not the hem
    th = np.degrees(np.arctan2(y - 0.01, x)) % 360.0
    k = np.floor(th).astype(int) % 360
    zh = np.full(360, 9.0)
    np.minimum.at(zh, k[coat], z[coat])
    ok = zh < 9
    if ok.any():
        ii = np.arange(360)
        zh = np.interp(ii, ii[ok], zh[ok], period=360)
    hem = (N[:, 2] < -0.55) & (z - zh[k] < 0.035)
    split = (y > 0.03) & (np.abs(x) < 0.06) & (sgn * N[:, 0] < -0.55) & (z < 0.84)
    rim = coat & (hem | split)
    band = np.zeros(len(x), bool)
    if rim.sum() > 50:
        vox = 0.003
        lo = P[coat].min(0) - 0.02
        idx = np.floor((P - lo) / vox).astype(int)
        shape = idx[coat].max(0) + 2
        G = np.zeros(shape, np.float32)
        ri = idx[rim]
        G[ri[:, 0], ri[:, 1], ri[:, 2]] = 1.0
        r = int(round(CORAL_BAND / vox))
        D = G[..., None]
        for ax in range(3):
            D = _box1d(D, r, ax)
        D = D[..., 0] > 1e-6
        ci = np.clip(idx, 0, shape - 1)
        band = coat & D[ci[:, 0], ci[:, 1], ci[:, 2]]
    band &= coat
    C[band] = cc[None, :] * (0.76 + 0.16 * np.clip(L[band] / max(np.median(L[band]), 1e-3), 0.6, 1.3))[:, None]
    cls[band] = 6
    log(f"round 2 paint: ear loop {ear.sum()}, neck {neck.sum()} (mock-neck {np.round(mock, 3)}), scratches {n_scr}, "
        f"pocket {n_pk}, coral hem/split band {band.sum()} texels")

def dilate(img, mask, iters=None):
    """Fill every non-valid texel from the valid ones (push-pull pyramid), so bilinear sampling at UV chart
    borders never reads stale texels. Valid texels are unchanged."""
    img = np.asarray(img, np.float32)
    w = mask.astype(np.float32)
    levels = []
    c = img * w[..., None]
    while min(w.shape) > 1:
        levels.append((c, w))
        H, W = w.shape
        H2, W2 = H // 2, W // 2
        c = c[:H2 * 2, :W2 * 2].reshape(H2, 2, W2, 2, -1).sum((1, 3))
        w = w[:H2 * 2, :W2 * 2].reshape(H2, 2, W2, 2).sum((1, 3))
    filled = c / np.maximum(w, 1e-8)[..., None]
    for c, w in reversed(levels):
        H, W = w.shape
        up = np.repeat(np.repeat(filled, 2, 0), 2, 1)
        up = np.pad(up, ((0, H - up.shape[0]), (0, W - up.shape[1]), (0, 0)), mode="edge")
        cur = c / np.maximum(w, 1e-8)[..., None]
        a = np.clip(w, 0, 1)[..., None]
        filled = cur * a + up * (1 - a)
    out = img.copy()
    out[~mask] = filled[~mask]
    return out
