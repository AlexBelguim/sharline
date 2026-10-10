"""Small readability fixes on the base colour outside the face (pure numpy, object-space masks).

Inputs are per-texel arrays: P (H,W,3) object-space position, N (H,W,3) normal, C (H,W,3) sRGB colour,
cov (H,W) coverage, part (H,W) island label (1 = left hand, 2 = right hand, 0 = rest; see kes_tex.bake_parts).
Returns the new colour and an emission mask (H,W) for the teal jet-pack rings.
"""
import numpy as np

GLOVE = np.array([0.085, 0.085, 0.095])
TEAL = np.array([0.10, 0.80, 0.72])
TEAL_PIPING = np.array([0.08, 0.66, 0.60])


def _skin(c):
    return (c[..., 0] > 0.55) & (c[..., 0] - c[..., 2] > 0.22) & (c[..., 0] > c[..., 1] + 0.12)


def _voxel_frac(p, flag, valid, cell):
    """Fraction of `flag` among `valid` texels in each texel's voxel neighbourhood (3x3x3 cells)."""
    q = np.floor(p / cell).astype(np.int64)
    q -= q.min(0)
    dims = q.max(0) + 3
    key = (q[:, 0] + 1) * dims[1] * dims[2] + (q[:, 1] + 1) * dims[2] + (q[:, 2] + 1)
    tot = np.zeros(dims.prod())
    hit = np.zeros(dims.prod())
    np.add.at(tot, key[valid], 1)
    np.add.at(hit, key[valid & flag], 1)
    tot3 = np.zeros_like(tot)
    hit3 = np.zeros_like(hit)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                off = dx * dims[1] * dims[2] + dy * dims[2] + dz
                tot3 += np.roll(tot, -off)
                hit3 += np.roll(hit, -off)
    return hit3[key] / np.maximum(tot3[key], 1)


def fix_gloves(P, C, cov, part, hand_axes, knuckle=0.58):
    """Fingerless gloves. TRELLIS made each hand a skin island (part label) wrapped by a thin glove shell that
    belongs to the arm; the skin shows through the shell as orange blotches. In the hand frame (t = 0 at the wrist,
    1 at the fingertips) every skin-coloured texel of EITHER shell between the wrist and the knuckles is glove.
    The fingers beyond the knuckles keep their paint (skin, glove-covered bases)."""
    out = C.copy()
    n = 0
    for lab, (wrist, axis, length, _) in hand_axes.items():
        side = 1 if lab == 1 else -1
        m = cov & (side * P[..., 0] > 0.42) & (P[..., 2] < 1.05)
        p = P[m]
        t = (p - wrist) @ axis / length
        radial = np.linalg.norm((p - wrist) - np.outer((p - wrist) @ axis, axis), axis=1)
        c = out[m]
        hand = (t > 0.02) & (radial < 0.08)
        warm = (c[:, 0] - c[:, 2] > 0.08) & (c[:, 0] > 0.22)
        bad = hand & (t < knuckle) & warm
        c[bad] = GLOVE
        # fingers: majority filter in 3D (~12 mm) - orange specks on the glove bases go dark, dark specks on the
        # skin tips go skin
        fz = hand & (t >= knuckle)
        if fz.any():
            sk = _skin(c) | (warm & (c.mean(-1) > 0.35))
            frac = _voxel_frac(p, sk, fz, 0.004)
            skin_col = np.median(c[fz & _skin(c)], axis=0) if (fz & _skin(c)).any() else np.array([0.9, 0.58, 0.45])
            to_glove = fz & (frac < 0.45) & warm
            to_skin = fz & (frac > 0.70) & ~_skin(c)
            c[to_glove] = GLOVE
            c[to_skin] = skin_col
            bad = bad | to_glove | to_skin
        out[m] = c
        n += int(bad.sum())
    return out, n


def _seg_param(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0.0, 1.0)
    return np.linalg.norm(p - (a + np.outer(t, ab)), axis=1), t


GLOVE_PROX = 0.92      # the glove's finger sleeves end at this fraction of the proximal phalanx (just before the PIP)


def fix_gloves_bones(P, C, cov, hands):
    """Fingerless gloves from the hand JOINTS (review round 2: the colour-based mask missed most of the skin that
    shows through the thin glove shell). Every texel of either layer (skin hand or glove shell) is labelled by its
    nearest hand segment: palm (wrist -> each knuckle), proximal phalanges up to GLOVE_PROX, thumb up to its IP
    joint = glove; middle/distal phalanges and the thumb tip = skin. Glove texels that are not already dark become
    the glove colour, skin texels that are not skin-coloured become the local skin colour."""
    out = C.copy()
    n_g = n_s = 0
    for lab, J in hands.items():
        side = 1 if lab == 1 else -1
        wrist, ax = J["wrist"], J["axis"]
        m = cov & (side * P[..., 0] > 0.40) & (P[..., 2] < 1.06) &             (np.linalg.norm(P - (wrist + ax * 0.06), axis=-1) < 0.16)
        p = P[m]
        c = out[m]
        t_w = (p - wrist) @ ax
        segs = []                                     # (a, b, kind, glove_until)
        for f in ("index", "middle", "ring", "pinky"):
            ch = J[f]
            segs.append((wrist, ch[0], "g", 1.0))
            segs.append((ch[0], ch[1], "f", GLOVE_PROX))
            segs.append((ch[1], ch[2], "s", 0.0))
            segs.append((ch[2], ch[3], "s", 0.0))
        th = J["thumb"]
        segs.append((wrist, th[0], "g", 1.0))
        segs.append((th[0], th[1], "g", 1.0))
        segs.append((th[1], th[2], "f", 0.85))
        segs.append((th[2], th[3], "s", 0.0))
        D = np.empty((len(p), len(segs)))
        T = np.empty((len(p), len(segs)))
        for k, (a, b, _, _) in enumerate(segs):
            D[:, k], T[:, k] = _seg_param(p, a, b)
        k = np.argmin(D, axis=1)
        kind = np.array([sg[2] for sg in segs])[k]
        until = np.array([sg[3] for sg in segs])[k]
        tk = T[np.arange(len(p)), k]
        glove = (kind == "g") | ((kind == "f") & (tk < until))
        glove &= t_w > 0.004                          # the cuff / sleeve beyond the wrist keeps its paint
        near = D[np.arange(len(p)), k] < 0.030
        lum = c.mean(-1)
        warm = (c[:, 0] - c[:, 2] > 0.06) & (c[:, 0] > 0.18)
        g_fix = near & glove & (warm | (lum > 0.20))
        c[g_fix] = GLOVE
        sk = near & ~glove & (t_w > 0.004)
        skin_ok = _skin(c)
        skin_col = np.median(c[sk & skin_ok], axis=0) if (sk & skin_ok).sum() > 20 else np.array([0.9, 0.6, 0.48])
        s_fix = sk & ~skin_ok
        c[s_fix] = skin_col
        out[m] = c
        n_g += int(g_fix.sum())
        n_s += int(s_fix.sum())
    return out, n_g, n_s


def _dense_open(keys_dark, keys_occ, shape, r):
    """3D morphological opening of the dark voxels (erosion against occupied voxels only, radius r)."""
    occ = np.zeros(shape, bool)
    occ[tuple(keys_occ.T)] = True
    dark = np.zeros(shape, bool)
    dark[tuple(keys_dark.T)] = True
    pad = r + 1
    occ_p = np.pad(occ, pad)
    dark_p = np.pad(dark, pad)
    ero = dark.copy()
    rng = range(-r, r + 1)
    sl = lambda d, n: slice(pad + d, pad + d + n)
    X, Y, Z = shape
    for dx in rng:
        for dy in rng:
            for dz in rng:
                o = occ_p[sl(dx, X), sl(dy, Y), sl(dz, Z)]
                d = dark_p[sl(dx, X), sl(dy, Y), sl(dz, Z)]
                ero &= ~o | d
    ero_p = np.pad(ero, pad)
    dil = np.zeros(shape, bool)
    for dx in rng:
        for dy in rng:
            for dz in rng:
                dil |= ero_p[sl(dx, X), sl(dy, Y), sl(dz, Z)]
    return dil


BONE_POD = np.array([0.77, 0.75, 0.71])      # palette bone (linear 0.55, 0.52, 0.46) in sRGB
POD_Z = (1.165, 1.405)                       # pod body between the dark base band and the graphite cap
POD_X = (0.012, 0.215)                       # |x| range of the two pods
POD_BACK_Y = 0.262                           # behind this: the pods' back faces (big graphite panels)


def pod_masks(p):
    """Texel masks (for points p) of the two jet-pack pod bodies, their side faces and their back faces."""
    ax = np.abs(p[:, 0])
    pod = (p[:, 2] > POD_Z[0]) & (p[:, 2] < POD_Z[1]) & (ax > POD_X[0]) & (ax < POD_X[1]) & (p[:, 1] > 0.140)
    back = pod & (p[:, 1] > POD_BACK_Y)
    side = pod & ~back
    return pod, side, back


def fix_jetpack(P, N, C, cov):
    """Bone pods: remove the black smudge marks (dark texels whose 3D neighbourhood is mostly bone) and turn the
    tan band at the pod base into a teal ring (emissive, the jet glow from the concept)."""
    out = C.copy()
    jp = cov & (P[..., 1] > 0.125) & (P[..., 2] > 1.05) & (P[..., 2] < 1.50) & (np.abs(P[..., 0]) < 0.22)
    p = P[jp]
    c = out[jp]
    L = c.mean(-1)
    bone = (L > 0.62) & (np.abs(c[:, 0] - c[:, 2]) < 0.12)
    # two scales: small specks (36 mm neighbourhood) and the larger "W"-like marks on the pod sides (54 mm)
    frac = np.maximum(_voxel_frac(p, bone, np.ones(len(p), bool), 0.012),
                      _voxel_frac(p, bone, np.ones(len(p), bool), 0.018) - 0.05)
    smudge = ~bone & (frac > 0.55) & (L < 0.55) & (p[:, 2] > 1.15)
    # local bone colour: mean bone colour of the voxel neighbourhood
    bone_col = np.median(c[bone], axis=0) if bone.any() else np.array([0.85, 0.83, 0.78])
    # the big painted marks (a "W" / "4") in the middle of each pod's outer side panel, clear of the graphite side
    # boxes at the back edge
    n_ = N[jp]
    side_mark = (np.abs(p[:, 0]) > 0.11) & (np.abs(n_[:, 0]) > 0.55) & (p[:, 1] > 0.155) & (p[:, 1] < 0.255) &         (p[:, 2] > 1.19) & (p[:, 2] < 1.37) & (L < 0.6)
    smudge = smudge | side_mark
    c[smudge] = bone_col
    # review round 2: clean the WHOLE pod body, not just the front band. The pod bodies are found geometrically
    # (two upright capsules behind the shoulder blades, between the base band and the caps). On them every mid-tone
    # texel (grey grime) becomes flat bone, and dark texels become bone unless they survive a 3D morphological
    # opening, i.e. belong to a large dark area: the graphite back panels and side boxes keep their paint, thin
    # strokes (the "W"/"4" glyphs, scribbles) do not. The pods' outer/inner side faces carry the big glyphs, so
    # they get the stronger opening; the back face (big panel) a lighter one.
    pod, side_f, back_f = pod_masks(p)
    L = c.mean(-1)
    bone2 = (L > 0.62) & (np.abs(c[:, 0] - c[:, 2]) < 0.12)
    teal_t = (c[:, 1] > c[:, 0] + 0.2) & (c[:, 2] > c[:, 0] + 0.15)
    pod &= ~teal_t
    cell = 0.004
    q = np.floor((p - p.min(0)) / cell).astype(np.int64)
    shape = tuple(q.max(0) + 1)
    dark = L < 0.33
    kept_b = _dense_open(q[pod & dark], q[pod], shape, r=2)[tuple(q.T)]
    kept_s = _dense_open(q[pod & dark], q[pod], shape, r=4)[tuple(q.T)]
    kept = np.where(side_f, kept_s, kept_b)
    stroke = pod & dark & ~kept
    grime = pod & ~dark & ~bone2
    # mid-tone texels right at the edge of a kept dark area are its anti-aliased border: keep them
    near_panel = _voxel_frac(p, pod & dark & ~stroke, pod, 0.004) > 0.35
    grime &= ~near_panel
    # one flat bone over the whole pod body (the median of the TRELLIS bone paint, so the pods match the chest
    # plate and elbow pads; the AO bake adds the soft shading)
    flat_bone = np.median(c[pod & bone2], axis=0) if (pod & bone2).sum() > 50 else BONE_POD
    c[stroke | grime | (pod & bone2)] = flat_bone
    smudge = smudge | stroke | grime
    # tan ring at the pod base -> teal
    tan = (c[:, 0] > 0.40) & (c[:, 0] - c[:, 2] > 0.12) & (p[:, 2] > 1.085) & (p[:, 2] < 1.15) & (p[:, 1] > 0.13)
    c[tan] = TEAL
    out[jp] = c
    emit = np.zeros(cov.shape)
    e = np.zeros(len(p))
    e[tan] = 1.0
    emit[jp] = e
    return out, emit, int(smudge.sum()), int(tan.sum())


def fix_collar_piping(P, N, C, cov):
    """Teal piping along the collar's top rim (v06), review round 2: TRELLIS painted a wobbly teal stripe with pale
    teal splotches on the collar. All teal paint on the collar (not the front zip piping, not the dyed hair tips) is
    first turned back into charcoal, then a constant ~3.5 mm band is painted along the rim: texels within 3.5 mm
    (in the radial / vertical plane) of the rim line, which is the smoothed top of the collar in 2-degree steps."""
    out = C.copy()
    cx, cy = 0.005, 0.008
    r = np.hypot(P[..., 0] - cx, P[..., 1] - cy)
    zone = cov & (r > 0.040) & (r < 0.108) & (P[..., 2] > 1.37) & (P[..., 2] < 1.515)
    p = P[zone]
    c = out[zone]
    rz = r[zone]
    L = c.mean(-1)
    tealish = (c[:, 1] > c[:, 0] + 0.15) & (c[:, 2] > c[:, 0] + 0.08)
    hairy = ((c[:, 2] - c[:, 0] > 0.03) & (L < 0.34)) | ((c[:, 2] >= c[:, 0] - 0.005) & (L < 0.11))
    frac_hair = _voxel_frac(p, hairy, np.ones(len(p), bool), 0.006)
    zip_ = (np.abs(p[:, 0] - 0.005) < 0.014) & (p[:, 1] < -0.03) & (p[:, 2] < 1.47)
    charcoal = (L < 0.35) & (np.abs(c[:, 0] - c[:, 2]) < 0.06) & (c[:, 2] - c[:, 1] < 0.03) & ~tealish
    char_col = np.median(c[charcoal], axis=0) if charcoal.sum() > 50 else np.array([0.13, 0.135, 0.15])
    clean = tealish & ~zip_ & (frac_hair < 0.35)
    c[clean] = char_col
    collar = (charcoal | clean) & ~zip_
    # rim line: highest collar texel per 2-degree bin, smoothed around the neck
    ang = np.arctan2(p[:, 1] - cy, p[:, 0] - cx)
    nb = 180
    b = ((ang + np.pi) / (2 * np.pi) * nb).astype(int) % nb
    zmax = np.full(nb, np.nan)
    rmax = np.full(nb, np.nan)
    for i in range(nb):
        m = collar & (b == i)
        if m.sum() > 5:
            k = np.argmax(np.where(m, p[:, 2], -1))
            zmax[i] = p[k, 2]
            rmax[i] = rz[k]
    ok = np.isfinite(zmax)
    idx = np.arange(nb)
    zs = np.interp(idx, idx[ok], zmax[ok], period=nb)
    rs = np.interp(idx, idx[ok], rmax[ok], period=nb)
    k5 = np.ones(5) / 5
    zs = np.convolve(np.r_[zs[-2:], zs, zs[:2]], k5, "valid")
    rs = np.convolve(np.r_[rs[-2:], rs, rs[:2]], k5, "valid")
    d = np.hypot(p[:, 2] - zs[b], rz - rs[b])
    band = collar & (d < 0.0035)
    c[band] = TEAL_PIPING
    out[zone] = c
    return out, int(band.sum()), zs


def misc_fixes(P, N, C, cov, part=None, hand_axes=None, hands=None, log=print):
    C = C.copy()
    emit = np.zeros(cov.shape)
    if part is not None and hand_axes:
        C, n = fix_gloves(P, C, cov, part, hand_axes)
        log(f"gloves: {n} texels cleaned")
    if hands:
        C, ng, ns = fix_gloves_bones(P, C, cov, hands)
        log(f"gloves (joint mask): {ng} texels -> glove, {ns} -> skin")
    C, emit, ns, nt = fix_jetpack(P, N, C, cov)
    log(f"jet pack: {ns} smudge texels -> bone, {nt} ring texels -> teal (emissive)")
    C, nr, _ = fix_collar_piping(P, N, C, cov)
    log(f"collar: {nr} rim texels -> teal piping (constant band, old teal splotches cleaned)")
    return C, emit
