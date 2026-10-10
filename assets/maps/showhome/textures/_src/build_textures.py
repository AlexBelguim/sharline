"""Build the Showhome texture library (assets/maps/showhome/textures/*.png) from the Krea2 raws in _src/raw/
(made by gen_raw.py) and procedural structure, matched to the concept palette in _src/palette.json
(made by sample_palette.py).

Every output is 1024x1024 sRGB, seamless in both directions, low contrast and painterly, with its average linear
reflectance equal to the palette albedo (so "what the texture averages to" is what the concept shows).
Structured surfaces (printed-concrete ridges, slab grids, shingles, solar cells, panel joints) are procedural so
their lines are exact, level and evenly spaced; the AI raws add the painterly grain and mottling on top.

Usage:  python build_textures.py [name ...]      (no names = all; names = keys of BUILDERS)
Writes the textures next to _src/, plus _src/preview/<name>_wrap.png (2x2 wrap test + contrast-boosted copy)
and _src/preview/_contact_sheet.png. Prints mean-vs-target and the seam ratio (about 1.0 = no seam) per file.
The trim sheet has its own script: make_trim_sheet.py.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import texlib as T

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.dirname(HERE)
PREV = os.path.join(HERE, "preview")
S = 1024
PAL = json.load(open(os.path.join(HERE, "palette.json")))["materials"]


def alb(mat):
    m = PAL[mat]
    return np.array(m["albedo_srgb"], np.float32) / 255.0, np.array(m["albedo_linear"], np.float32)


def raw_rgb(src, crop=None):
    im = Image.open(os.path.join(RAW, src + ".png")).convert("RGB")
    if crop:
        im = im.crop(crop)
    if im.size != (S, S):
        im = im.resize((S, S), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255.0


def ai_detail(src, sigma=60, amount=0.9, seam="xfade", band=0.2, crop=None, clip=2.6):
    """Luminance detail of a raw: light fall-off removed, made seamless, zero mean / unit std."""
    y = T.luminance(raw_rgb(src, crop))
    y = T.flatten(y, sigma, amount)
    y = T.quilt_cut(y, band) if seam == "cut" else T.xfade(y, band)
    return T.normalise_detail(y, clip)


def ai_colour(src, sigma=60, amount=0.8, band=0.22, crop=None):
    """Colour raw: per-channel light fall-off removed, made seamless (keeps the raw's own hue variation)."""
    a = raw_rgb(src, crop)
    a = T.flatten(a, sigma, amount)
    return T.xfade(a, band)


def finish(rgb, mat_or_lin):
    target = alb(mat_or_lin)[1] if isinstance(mat_or_lin, str) else np.asarray(mat_or_lin, np.float32)
    return T.match_mean_linear(np.clip(rgb, 0, 1), target)


# =============================================================================================== builders
def printed_concrete_layers():
    """Cream 3D-printed concrete: 32 perfectly level, evenly spaced extruded layers per repeat (32 px each).
    The albedo carries only a soft cavity tone in each groove (no hard lines, no per-layer plank banding) so it
    reads as rounded printed beads, not timber siding; the normal map does the relief."""
    base, _ = alb("printed_concrete")
    N, P = 32, S // 32
    rng = np.random.default_rng(7)
    rows = np.arange(S, dtype=np.float32)[:, None] + P / 2      # grooves sit mid-image, beads on the wrap edge
    # a gentle sub-pixel waviness ALONG each bead (printed look) that never changes the spacing
    wob = T.periodic_noise(S, S, None, 3, aniso=(P * 0.6, 110)) * 0.6
    yy = rows + wob
    t = (yy % P) / P
    layer = np.floor(yy / P).astype(np.int64) % N
    bead = np.sin(np.pi * t) ** 0.6                       # rounded bead, soft groove at t = 0 / 1
    cav = T.fft_blur(((1.0 - bead) ** 1.6).astype(np.float32), 0.8)
    tone = rng.normal(0, 1, N).astype(np.float32)
    streak = T.periodic_noise(S, S, None, 5, aniso=(1.4, 70))     # extrusion streaks along the bead
    paint = T.fft_blur(ai_detail("concrete_smooth_s11", 50, 0.9), 3.0)   # painterly mottling (pores blurred out)
    blot = T.fbm(S, S, 11, (150, 60), (1.0, 0.5))                  # big soft brush patches
    d = T.normalise_detail(0.18 * tone[layer] + 0.40 * streak + 0.22 * paint + 0.40 * blot)
    col = T.colourise(d, base, 0.018, shadow_tint=(-0.04, -0.02, 0.06), light_tint=(0.06, 0.03, -0.06))
    col = col * (1.0 - 0.20 * cav - 0.05 * (1.0 - bead))[..., None] * np.array([1.0, 0.985, 0.965], np.float32)
    col = finish(col, "printed_concrete")
    height = bead + 0.01 * paint
    nrm = T.normal_from_height(height, 3.0)
    return {"printed_concrete_layers": col, "printed_concrete_layers_normal": nrm}


def _fibercement_grey():
    y = ai_detail("fibercement_s11", 80, 0.7)
    streak = T.periodic_noise(S, S, None, 21, aniso=(110, 2.6))    # faint, soft vertical streaks
    d = T.normalise_detail(0.85 * y + 0.28 * streak)
    g = float(T.to_srgb(0.70))
    return T.colourise(d, (g, g, g), 0.030), d


def fibercement_panel():
    """Neutral light-grey fibre-cement board (no joints), linear mean 0.70, for tinting sage / clay."""
    grey, _ = _fibercement_grey()
    return {"fibercement_panel": finish(grey, (0.70, 0.70, 0.70))}


def fibercement_panels_jointed():
    """Fibre-cement cladding with joints: 4 x 2 panels per repeat (256 x 512 px each = 1.2 x 2.4 m at a 4.8 m
    repeat), 6 px shadow-gap joints, per-panel tone. Grey (for any tint) + pre-tinted sage and clay versions."""
    grey, d = _fibercement_grey()
    rng = np.random.default_rng(31)
    x = np.arange(S)[None, :]
    y = np.arange(S)[:, None]
    pw, ph, jw = 256, 512, 4
    jx = np.minimum(x % pw, pw - x % pw)          # distance to the nearest vertical joint centre
    jy = np.minimum(y % ph, ph - y % ph)
    dist = np.minimum(jx + 0 * y, jy + 0 * x).astype(np.float32)
    joint = np.clip((jw / 2 + 0.5 - dist), 0, 1)                 # 1 inside the gap (anti-aliased)
    edge = np.clip(1.0 - (dist - jw / 2) / 3.0, 0, 1) * (1 - joint)   # 3 px soft edge (bevel) next to the gap
    pid = (y // ph) * (S // pw) + (x // pw)
    npan = (S // pw) * (S // ph)
    lum_j = rng.normal(0, 0.040, npan).astype(np.float32)
    hue_j = rng.normal(0, 0.03, (npan, 3)).astype(np.float32)
    # per-panel soft diagonal wash (the concept's panels each carry one painterly tone patch)
    ang = rng.uniform(0, 2 * np.pi, npan)
    u = ((x % pw) / pw - 0.5) * np.cos(ang[pid]) + ((y % ph) / ph - 0.5) * np.sin(ang[pid])
    wash = (0.05 * u).astype(np.float32)
    shade = (1.0 + lum_j[pid] + wash)[..., None]
    gap = (1.0 - 0.42 * joint - 0.08 * edge)[..., None]
    height = 1.0 - joint - 0.35 * edge
    nrm = T.normal_from_height(height.astype(np.float32), 2.0)
    out = {"fibercement_panel_joints": finish(np.clip(grey * shade, 0, 1) * gap, (0.66, 0.66, 0.66)),
           "fibercement_panel_joints_normal": nrm}
    glin = T.to_lin(np.clip(grey * shade, 0, 1)) / 0.70
    for mat, name in (("fibercement_sage", "fibercement_sage"), ("fibercement_clay", "fibercement_clay")):
        _, lin = alb(mat)
        c = glin * lin[None, None, :] * (1.0 + hue_j[pid])
        c = T.to_srgb(np.clip(c, 0, 1)) * gap
        out[name] = finish(c, mat)
    # move the joints off the wrap edges (the image stays periodic; edges now fall mid-panel)
    return {k: np.roll(v, (ph // 2, pw // 2), axis=(0, 1)) for k, v in out.items()}


def roof_shingle_dark():
    """Dark slate-like shingles: 8 courses x 4 shingles per repeat (2 m repeat -> 50 x 25 cm), half-bond.
    Image top = toward the ridge (each course's thick butt edge is its bottom edge)."""
    base, _ = alb("roof_dark")
    rows, per, rh, sw = 8, 4, S // 8, S // 4
    rng = np.random.default_rng(17)
    y = np.arange(S)[:, None] + np.zeros((1, S), np.int64)
    x = np.arange(S)[None, :] + np.zeros((S, 1), np.int64)
    r = y // rh
    off = (r % 2) * (sw // 2) + (rng.integers(-10, 11, rows))[r % rows]
    xs = (x + off) % S
    c = xs // sw
    ty = (y % rh) / rh                                              # 0 top of the course .. 1 butt edge
    tx = np.minimum(xs % sw, sw - xs % sw).astype(np.float32)       # px to the side joint
    sid = r * per + c
    joint = np.clip(2.0 - tx, 0, 1)                                  # 3-4 px side gap
    butt = np.clip((ty - (1 - 3.5 / rh)) * rh / 3.5, 0, 1)           # thin shadow line under the butt edge
    under = np.clip(1.0 - ty * rh / 7.0, 0, 1)                       # cavity just below the course above
    tone = rng.normal(0, 1, rows * per).astype(np.float32)
    hue = rng.normal(0, 0.008, (rows * per, 3)).astype(np.float32)
    grain = T.fft_blur(ai_detail("concrete_smooth_s12", 30, 1.0), 1.0)
    paint = T.fbm(S, S, 4, (60, 20), (1.0, 0.6))
    d = T.normalise_detail(0.45 * tone[sid] + 0.45 * grain + 0.45 * paint)
    col = T.colourise(d, base, 0.024, shadow_tint=(-0.1, -0.05, 0.2), light_tint=(0.1, 0.05, -0.05))
    col = col * (1.0 + hue[sid])
    col = col * (1.0 - 0.55 * joint - 0.45 * butt - 0.18 * under)[..., None]
    col = finish(col, "roof_dark")
    height = (0.3 + 0.7 * ty) * (1 - joint) * (1 - butt)
    nrm = T.normal_from_height(height.astype(np.float32) + 0.02 * grain, 2.5)
    sh = (rh // 2, 37)   # wrap edges mid-course (periodic roll)
    return {"roof_shingle_dark": np.roll(col, sh, axis=(0, 1)), "roof_shingle_dark_normal": np.roll(nrm, sh, axis=(0, 1))}


def solar_panel():
    """One solar module (6 x 10 cells, dark frame) on the full 0-1 UV square; meant for a 1.0 x 1.65 m module
    (U = short side). Tiled across a roof plane it forms a continuous array."""
    cell_s, _ = alb("solar_cell")
    frame_c = np.array([62, 64, 72], np.float32) / 255
    frame_hi = np.array([128, 132, 142], np.float32) / 255
    back_c = np.array([112, 117, 134], np.float32) / 255     # backsheet showing between cells
    bus_c = np.array([70, 76, 100], np.float32) / 255
    W = H = S
    fw_u, fw_v = 22, int(round(22 / 1.65))                    # frame 2.2 cm on both sides
    mg_u, mg_v = 8, int(round(8 / 1.65))
    img = np.zeros((H, W, 3), np.float32)
    img[:] = frame_c
    # frame inner lip highlight (thin)
    img[fw_v - 2:H - fw_v + 2, fw_u - 2:W - fw_u + 2] = frame_hi
    img[fw_v:H - fw_v, fw_u:W - fw_u] = back_c
    x0, x1, y0, y1 = fw_u + mg_u, W - fw_u - mg_u, fw_v + mg_v, H - fw_v - mg_v
    nx, ny, gap = 6, 10, 3
    cw = (x1 - x0 - gap * (nx - 1)) / nx
    ch = (y1 - y0 - int(round(gap / 1.65)) * (ny - 1)) / ny
    gv = int(round(gap / 1.65))
    rng = np.random.default_rng(5)
    sheen = T.fbm(H, W, 9, (120, 40), (1.0, 0.4))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    for j in range(ny):
        for i in range(nx):
            cx0 = x0 + i * (cw + gap)
            cy0 = y0 + j * (ch + gv)
            cx1, cy1 = cx0 + cw, cy0 + ch
            m = (xx >= cx0) & (xx < cx1) & (yy >= cy0) & (yy < cy1)
            # pseudo-square cell: clipped corners (in metres the cut is equal on both axes)
            du = np.minimum(xx - cx0, cx1 - xx)
            dv = np.minimum(yy - cy0, cy1 - yy) * 1.65
            m &= (du + dv) > 16
            tint = cell_s * (1.0 + rng.normal(0, 0.035)) + np.array([0, 0, rng.normal(0, 0.01)])
            img[m] = tint
            # 3 busbars per cell (thin, vertical = along the module's long side)
            for k in (1, 2, 3):
                bx = cx0 + cw * k / 4
                mb = m & (np.abs(xx - bx) < 1.0)
                img[mb] = bus_c
    img = img * (1.0 + 0.03 * sheen)[..., None]
    return {"solar_panel": np.clip(img, 0, 1)}


def paving_slabs():
    """Light-grey concrete slabs, 4 x 4 per repeat (2.4 m repeat -> 0.6 m slabs), 5 px sanded joints."""
    base, _ = alb("paving")
    n, sp, jw = 4, S // 4, 5
    rng = np.random.default_rng(23)
    y, x = np.mgrid[0:S, 0:S]
    jx = np.minimum(x % sp, sp - x % sp).astype(np.float32)
    jy = np.minimum(y % sp, sp - y % sp).astype(np.float32)
    dist = np.minimum(jx, jy)
    joint = np.clip(jw / 2 + 0.5 - dist, 0, 1)
    bevel = np.clip((dist - jw / 2) / 5.0, 0, 1)                   # 5 px rounded slab edge
    sid = (y // sp) * n + (x // sp)
    tone = rng.normal(0, 1, n * n).astype(np.float32)
    hue = rng.normal(0, 0.007, (n * n, 3)).astype(np.float32)
    ang = rng.uniform(0, 2 * np.pi, n * n)
    u = ((x % sp) / sp - 0.5) * np.cos(ang[sid]) + ((y % sp) / sp - 0.5) * np.sin(ang[sid])
    grain = ai_detail("concrete_smooth_s12", 40, 0.9)
    blot = T.fbm(S, S, 41, (90, 30), (1.0, 0.5))
    d = T.normalise_detail(0.55 * tone[sid] + 0.6 * u + 0.5 * grain + 0.35 * blot)
    col = T.colourise(d, base, 0.026, shadow_tint=(-0.03, -0.01, 0.05), light_tint=(0.03, 0.015, -0.03))
    col = col * (1.0 + hue[sid])
    grime = np.clip(1.0 - (dist - jw / 2) / 14.0, 0, 1) * (1 - joint)   # faint dirt along the joints
    jc = np.array([0.66, 0.63, 0.60], np.float32)                       # sand / dirt in the joint
    col = col * (1.0 - 0.06 * grime)[..., None]
    col = col * (1 - joint[..., None]) + col * jc * joint[..., None]
    col = finish(col, "paving")
    height = bevel ** 0.6 * (1 - joint) + 0.03 * grain * 0.2
    nrm = T.normal_from_height(height.astype(np.float32), 2.0)
    sh = (sp // 2, sp // 2)   # wrap edges mid-slab (periodic roll)
    return {"paving_slabs": np.roll(col, sh, axis=(0, 1)), "paving_slabs_normal": np.roll(nrm, sh, axis=(0, 1))}


def kerb_concrete():
    """Kerb stone concrete: joints every 512 px along U (2 m repeat -> 1 m kerb units). U runs along the kerb."""
    base, _ = alb("kerb")
    grain = ai_detail("concrete_smooth_s12", 30, 1.0)
    mott = T.fft_blur(ai_detail("concrete_smooth_s11", 120, 0.6), 3.0)
    streak = T.periodic_noise(S, S, None, 61, aniso=(2.0, 80))
    d = T.normalise_detail(0.6 * grain + 0.3 * mott + 0.3 * streak)
    col = T.colourise(d, base, 0.022, shadow_tint=(-0.04, -0.02, 0.06), light_tint=(0.04, 0.02, -0.04))
    x = np.arange(S)[None, :]
    jx = np.minimum(x % 512, 512 - x % 512).astype(np.float32)
    joint = np.clip(2.0 - jx, 0, 1)
    edge = np.clip(1.0 - (jx - 1.5) / 6.0, 0, 1) * (1 - joint)
    col = col * (1.0 - 0.45 * joint - 0.08 * edge)[..., None] + np.zeros((S, 1, 1), np.float32)
    return {"kerb_concrete": np.roll(finish(col, "kerb"), 256, axis=1)}   # joints at U = 0.25 / 0.75


def _asphalt_detail():
    sp = ai_detail("asphalt_s12", 40, 1.0, band=0.22)
    blot = T.fbm(S, S, 71, (140, 50), (1.0, 0.5))
    return T.normalise_detail(0.75 * sp + 0.45 * blot)


def _asphalt_colour(d):
    base, _ = alb("asphalt")
    return T.colourise(d, base, 0.034, shadow_tint=(-0.1, -0.08, 0.3), light_tint=(0.18, 0.08, -0.12))


def asphalt():
    """Smooth stylized asphalt with fine aggregate and soft painterly patches, no markings."""
    return {"asphalt": finish(_asphalt_colour(_asphalt_detail()), "asphalt")}


def asphalt_cracked():
    """The same asphalt plus thin branching cracks (extracted from a Krea2 raw, wrapped with a boundary cut)."""
    d = np.roll(_asphalt_detail(), (S // 3, S // 2), axis=(0, 1))
    y = T.luminance(raw_rgb("asphalt_cracked_v2_s12"))
    y = T.flatten(y, 30, 1.0)
    y = T.quilt_cut(y, 0.16)
    crack = np.clip(T.fft_blur(y, 3.0) - y, 0, None)                 # thin dark lines (black top-hat)
    crack = np.clip((crack - 0.025) / 0.07, 0, 1)
    crack = T.fft_blur(crack, 0.6)
    col = _asphalt_colour(d)
    cc = np.array([0.50, 0.50, 0.55], np.float32)                    # crack interior, slightly cool
    halo = np.clip(T.fft_blur(crack, 2.5) * 2.0, 0, 1) * (1 - crack)    # faint darker rim
    col = col * (1 - crack[..., None]) + col * cc * crack[..., None]
    col = col * (1.0 - 0.06 * halo)[..., None]
    _, lin = alb("asphalt")
    return {"asphalt_cracked": finish(col, lin * 0.985)}


def grass_lawn():
    a = ai_colour("grass_s12", 60, 0.8, 0.22)
    base, _ = alb("grass")
    return {"grass_lawn": finish(T.recolour_rgb(a, base, 0.055), "grass")}


def hedge_leaves():
    # the raw shows a lighter hedge top in its first ~100 rows: crop it away
    a = ai_colour_crop("hedge_s11", (0, 110, 914, 1024))
    base, _ = alb("hedge")
    return {"hedge_leaves": finish(T.recolour_rgb(a, base, 0.062), "hedge")}


def ai_colour_crop(src, crop):
    a = raw_rgb(src, crop)
    a = T.flatten(a, 60, 0.8)
    return T.xfade(a, 0.22)


def picket_wood_white():
    """White painted wood, grain runs VERTICALLY (along V): map V along each picket."""
    base, _ = alb("picket_white")
    d = ai_detail("picket_wood_s11", 80, 0.8)
    col = T.colourise(d, base, 0.020, shadow_tint=(-0.2, -0.05, 0.25), light_tint=(0.05, 0.03, -0.05))
    return {"picket_wood_white": finish(col, "picket_white")}


def garden_soil():
    a = ai_colour("soil_s12", 60, 0.8)
    base, _ = alb("garden_soil")
    a = T.fft_blur(a, 0.8)
    return {"garden_soil": finish(T.recolour_rgb(a, base, 0.036), "garden_soil")}


def painterly_steps(m, step=0.6, mix=0.55, soften=2.5):
    """Push smooth noise toward flat painted patches: soft quantisation blended with the original, edges softened."""
    q = np.round(m / step) * step
    return T.fft_blur(((1 - mix) * m + mix * q).astype(np.float32), soften)


def construction_sand():
    """Compacted site sand / earth, procedural: flat painted patches (soft-quantised fbm), fine grain, faint long
    rake / tyre smears and sparse small pebbles. (Every Krea2 sand raw had big round blotches whose outlines stamped
    a visible grid over the 80 m plots, so no raw is used here.)"""
    base, _ = alb("construction_sand")
    mott = painterly_steps(T.fbm(S, S, 101, (90, 36, 12), (0.6, 0.55, 0.35)), step=0.55, mix=0.75, soften=1.4)
    grain = T.periodic_noise(S, S, 0.9, 107)
    smear = T.periodic_noise(S, S, None, 103, aniso=(10, 120))
    d = T.normalise_detail(0.80 * mott + 0.38 * grain + 0.20 * smear)
    col = T.colourise(d, base, 0.024, shadow_tint=(-0.05, -0.03, 0.06), light_tint=(0.05, 0.02, -0.05))
    drift = T.periodic_noise(S, S, 120, 105)[..., None] * np.array([0.006, 0.0, -0.007], np.float32)
    col = col + drift
    # pebbles: a few px blobs, light top / darker underside
    pn = T.periodic_noise(S, S, 2.0, 109)
    peb = T.fft_blur(np.clip((pn - 2.7) / 0.3, 0, 1).astype(np.float32), 0.5)
    under = np.clip(np.roll(peb, 2, axis=0) - peb, 0, 1)
    col = col * (1.0 + 0.10 * peb - 0.18 * under)[..., None]
    return {"construction_sand": finish(col, "construction_sand")}


def gravel():
    a = ai_colour(pick("gravel", 11), 50, 0.9)
    base, _ = alb("gravel")
    return {"gravel": finish(T.recolour_rgb(a, base, 0.06), "gravel")}


def cardboard():
    a = ai_colour(pick("cardboard", 11), 60, 0.9)
    base, _ = alb("cardboard")
    return {"cardboard": finish(T.recolour_rgb(a, base, 0.03, hue_keep=0.5), "cardboard")}


def cardboard_box_face():
    """NOT tiling: one box face on the 0-1 UV square (use it on every face of a delivery box): flap seam across
    the middle under a strip of brown packing tape, slightly darker worn edges."""
    col = cardboard()["cardboard"].copy()
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    edge = np.minimum(np.minimum(x, S - 1 - x), np.minimum(y, S - 1 - y))
    wear = np.clip(1.0 - edge / 18.0, 0, 1)
    col = col * (1.0 - 0.12 * wear)[..., None]
    seam = np.exp(-0.5 * ((y - S / 2) / 1.6) ** 2)
    col = col * (1.0 - 0.35 * seam)[..., None]
    tape_half = 0.075 * S
    tape = np.clip(tape_half + 0.5 - np.abs(y - S / 2), 0, 1)
    tape_c = np.array([0.80, 0.60, 0.36], np.float32)
    wrinkle = 1.0 + 0.04 * T.periodic_noise(S, S, None, 77, aniso=(3, 40))
    tcol = tape_c[None, None, :] * wrinkle[..., None]
    tape_edge = np.exp(-0.5 * ((np.abs(y - S / 2) - tape_half) / 1.2) ** 2)
    col = col * (1 - tape[..., None]) + tcol * tape[..., None]
    col = col * (1.0 - 0.10 * tape_edge)[..., None]
    return {"cardboard_box_face": np.clip(col, 0, 1)}


def truck_paint_white():
    base, _ = alb("truck_white")
    d = ai_detail(pick("white_paint", 12), 60, 0.9, crop=(40, 40, 984, 984))
    col = T.colourise(d, base, 0.012, shadow_tint=(-0.2, -0.05, 0.3), light_tint=(0.05, 0.03, -0.05))
    return {"truck_paint_white": finish(col, "truck_white")}


def metal_painted_yellow():
    """Crane paint: weathered ochre-yellow, soft painterly mottling, faint vertical weathering streaks (V = down
    the member) and sparse small clustered chips showing grey primer. Only the fine brush grain of the Krea2 raw
    is used: its big diagonal strokes repeated like a stamp and read as wood grain on the crane."""
    base, _ = alb("crane_yellow")
    chip_s, _ = alb("metal_chip")
    fine = ai_detail(pick("yellow_paint", 12), 8, 1.0, crop=(70, 70, 954, 954), clip=2.4)
    mott = T.fbm(S, S, 91, (170, 60, 16), (1.0, 0.5, 0.25))
    weather = T.periodic_noise(S, S, None, 93, aniso=(90, 3.0))      # long thin vertical streaks
    d = T.normalise_detail(0.40 * fine + 0.75 * mott + 0.30 * weather)
    col = T.colourise(d, base, 0.030, shadow_tint=(-0.08, -0.12, 0.0), light_tint=(0.06, 0.05, -0.04))
    spots = T.periodic_noise(S, S, 2.2, 95)
    cluster = np.clip((T.periodic_noise(S, S, 70, 97) - 0.6) / 0.8, 0, 1)
    chip = np.clip((spots - 2.55) / 0.35, 0, 1) * cluster
    chip = T.fft_blur(chip.astype(np.float32), 0.6) * 0.9
    rim = np.clip(T.fft_blur(chip, 1.5) * 2.5, 0, 1) * (1 - chip)       # darker paint lip around each chip
    col = col * (1.0 - 0.08 * rim)[..., None]
    col = col * (1 - chip[..., None]) + chip_s[None, None, :] * chip[..., None]
    return {"metal_painted_yellow": finish(col, "crane_yellow")}


def glass_frost():
    """Greenhouse glass, RGBA: pale tint in RGB, opacity in A (about 0.22-0.42, smudges slightly more opaque)."""
    base, _ = alb("glass")
    # the raw shows a framed pane on grey: use the inside of the pane only
    d = ai_detail(pick("glass_smudge", 11), 60, 0.9, crop=(170, 120, 850, 800))
    col = T.colourise(d, base, 0.015)
    col = finish(col, "glass")
    a = np.clip(0.30 + 0.05 * d, 0.20, 0.45)[..., None]
    return {"glass_frost": np.concatenate([col, a], axis=2)}


def concrete_smooth():
    """Plain cast concrete (carports, utility poles, terrace coping, site blocks)."""
    base, _ = alb("pole_concrete")
    d = T.normalise_detail(0.7 * T.fft_blur(ai_detail("concrete_smooth_s11", 60, 0.9), 1.5)
                           + 0.5 * T.fbm(S, S, 81, (120, 40)) + 0.25 * T.periodic_noise(S, S, 1.0, 83))
    col = T.colourise(d, base, 0.020, shadow_tint=(-0.04, -0.02, 0.06), light_tint=(0.04, 0.02, -0.04))
    return {"concrete_smooth": finish(col, "pole_concrete")}


def wood_boards_stained():
    """Stained vertical shed / fence boards (out-of-bounds sheds); grain along V."""
    a = ai_colour(pick("wood_boards", 13), 80, 0.8)
    base, _ = alb("shed_wood")
    return {"wood_boards_stained": finish(T.recolour_rgb(a, base, 0.05), "shed_wood")}


# which raw seed each AI texture uses (chosen after looking at the candidates; see README)
CHOSEN = {}


def pick(name, default_seed):
    return CHOSEN.get(name, f"{name}_s{default_seed}")


BUILDERS = {
    "printed_concrete_layers": printed_concrete_layers,
    "fibercement_panel": fibercement_panel,
    "fibercement_panels_jointed": fibercement_panels_jointed,
    "roof_shingle_dark": roof_shingle_dark,
    "solar_panel": solar_panel,
    "asphalt": asphalt,
    "asphalt_cracked": asphalt_cracked,
    "paving_slabs": paving_slabs,
    "kerb_concrete": kerb_concrete,
    "grass_lawn": grass_lawn,
    "hedge_leaves": hedge_leaves,
    "picket_wood_white": picket_wood_white,
    "garden_soil": garden_soil,
    "construction_sand": construction_sand,
    "gravel": gravel,
    "cardboard": cardboard,
    "cardboard_box_face": cardboard_box_face,
    "truck_paint_white": truck_paint_white,
    "metal_painted_yellow": metal_painted_yellow,
    "glass_frost": glass_frost,
    "concrete_smooth": concrete_smooth,
    "wood_boards_stained": wood_boards_stained,
}


# =============================================================================================== output
def preview(name, out):
    os.makedirs(PREV, exist_ok=True)
    rgb = out[..., :3]
    t = np.tile(rgb, (2, 2, 1))
    im = Image.fromarray((np.clip(t, 0, 1) * 255).astype(np.uint8)).resize((S, S), Image.LANCZOS)
    tb = np.clip(0.5 + (t - t.mean(axis=(0, 1))) * 3.0, 0, 1)
    imb = Image.fromarray((tb * 255).astype(np.uint8)).resize((S, S), Image.LANCZOS)
    sheet = Image.new("RGB", (S * 2, S))
    sheet.paste(im, (0, 0))
    sheet.paste(imb, (S, 0))
    sheet.save(os.path.join(PREV, f"{name}_wrap.png"))


def contact_sheet():
    files = sorted(f for f in os.listdir(OUT) if f.endswith(".png") and not f.endswith("_normal.png")
                   and not f.startswith("trim_sheet"))
    cell, cols = 300, 5
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 20)), (24, 26, 30))
    dr = ImageDraw.Draw(sheet)
    for i, f in enumerate(files):
        im = Image.open(os.path.join(OUT, f)).convert("RGB").resize((cell - 6, cell - 6), Image.LANCZOS)
        r, c = divmod(i, cols)
        sheet.paste(im, (c * cell + 3, r * (cell + 20) + 3))
        dr.text((c * cell + 6, r * (cell + 20) + cell - 1), f[:-4], fill=(230, 230, 230))
    sheet.save(os.path.join(PREV, "_contact_sheet.png"))


def main():
    names = sys.argv[1:] or list(BUILDERS)
    for n in names:
        outs = BUILDERS[n]()
        for fname, arr in outs.items():
            path = os.path.join(OUT, fname + ".png")
            T.save(arr, path)
            sx, sy = T.seam_ratio(arr)
            msg = f"{fname:32s} seam x{sx:.2f} y{sy:.2f}"
            if not fname.endswith("_normal") and fname != "solar_panel":
                lin = T.to_lin(np.clip(arr[..., :3], 0, 1)).reshape(-1, 3).mean(axis=0)
                L = T.luminance(np.clip(arr[..., :3], 0, 1))
                msg += f"  mean_lin {np.round(lin, 3)}  sRGB-lum std {L.std():.3f}"
            print(msg, flush=True)
            preview(fname, arr)
    contact_sheet()


if __name__ == "__main__":
    main()
