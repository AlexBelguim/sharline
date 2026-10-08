"""Parallax depth maps (plus AO and, where a surface had none, normal maps) for the Showhome texture library.

The library (assets/maps/showhome/textures, another agent's work: READ ONLY here) builds every structured texture
procedurally in _src/build_textures.py. This script re-runs the same structure code (same seeds, raws, rolls) so
the heights land exactly on the joints, beads, slabs and shingle butts the albedo shows, then adds fine grain from
the same Krea2 raws the albedo used (or, for the organic surfaces, from the albedo itself).

Heights are modelled in METRES (0 = the face of the mesh, negative = carved into it), then written as Bevy depth
maps: 16-bit greyscale, 0 (black) = the top, 65535 (white) = the deepest point. The depth that white stands for is
printed per map and written to out/depth.json; game/assets/data/surface_depth.ron must use it (`depth_cm`), so a
designer can still scale it there.

Outputs (out/):  <maps>_depth.png   16-bit, linear data, the parallax depth
                 <maps>_orm.png     glTF / Bevy ORM: R = ambient occlusion from the height field, G = 1, B = 0
                 <name>_normal.png  only for surfaces that had no normal map (OpenGL / glTF convention)
                 depth.json         depth_cm per map + alignment checks
Previews (preview/): <maps>_check.png: albedo | depth | AO | relief lit by a low sun | albedo x structure overlay.

    python -B build_depth.py [name ...] [--game]     (--game also copies the maps the game uses into
                                                      game/assets/textures/showhome/)
Run it with the ComfyUI venv python or any python with numpy + Pillow. `-B` keeps Python from writing a
__pycache__ into the library's _src folder (its texlib is imported, never modified).
"""
import json
import os
import shutil
import sys

sys.dont_write_bytecode = True

import numpy as np
from PIL import Image

LIB = r"F:\git\val etf\assets\maps\showhome\textures"
SRC = os.path.join(LIB, "_src")
RAW = os.path.join(SRC, "raw")
sys.path.insert(0, SRC)
import texlib as T  # noqa: E402  (the library's helpers, read-only)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
PREV = os.path.join(HERE, "preview")
KREA = os.path.join(HERE, "raw")
GAME = os.path.normpath(os.path.join(HERE, "..", "..", "..", "game", "assets", "textures", "showhome"))
S = 1024


# ============================================================================================== helpers
def albedo(name):
    return np.asarray(Image.open(os.path.join(LIB, name + ".png")).convert("RGB"), np.float32) / 255.0


def raw_rgb(src, crop=None):
    im = Image.open(os.path.join(RAW, src + ".png")).convert("RGB")
    if crop:
        im = im.crop(crop)
    if im.size != (S, S):
        im = im.resize((S, S), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255.0


def ai_detail(src, sigma=60, amount=0.9, seam="xfade", band=0.2, crop=None, clip=2.6):
    """Exactly build_textures.ai_detail: a raw's luminance detail, light fall-off removed, seamless, unit std."""
    y = T.luminance(raw_rgb(src, crop))
    y = T.flatten(y, sigma, amount)
    y = T.quilt_cut(y, band) if seam == "cut" else T.xfade(y, band)
    return T.normalise_detail(y, clip)


def high_pass_lum(rgb, sigma):
    """Albedo luminance minus its soft painterly blotches (periodic): what is left is the small-scale shape."""
    y = T.luminance(rgb)
    return y - T.fft_blur(y, sigma)


def unit_range(a, lo=0.5, hi=99.5):
    """Map the lo..hi percentiles to 0..1 (clipped), so a few outlier texels do not set the whole range."""
    p0, p1 = np.percentile(a, [lo, hi])
    return np.clip((a - p0) / max(p1 - p0, 1e-9), 0, 1).astype(np.float32)


def normal_from_height_m(h_m, texel_m, strength=1.0):
    """Tangent-space normal (OpenGL / glTF: +X right, +Y toward the image top) from a periodic height in metres."""
    dx = (np.roll(h_m, -1, axis=1) - np.roll(h_m, 1, axis=1)) / (2 * texel_m) * strength
    drow = (np.roll(h_m, -1, axis=0) - np.roll(h_m, 1, axis=0)) / (2 * texel_m) * strength
    nx, ny, nz = -dx, drow, np.ones_like(h_m)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5], axis=2).astype(np.float32)


def horizon_ao(h_m, texel_m, radius_m, dirs=16, steps=10):
    """Ambient occlusion of a periodic height field: per direction the highest horizon within radius_m, AO = 1 -
    the mean sine of the horizon angles (uniform hemisphere). 1 = open, lower = in a groove or joint."""
    rpx = max(radius_m / texel_m, 1.5)
    occl = np.zeros_like(h_m)
    for k in range(dirs):
        a = 2 * np.pi * (k + 0.5) / dirs
        best = np.zeros_like(h_m)
        for s in range(1, steps + 1):
            r = rpx * (s / steps) ** 1.5
            dx, dy = int(round(r * np.cos(a))), int(round(r * np.sin(a)))
            if dx == 0 and dy == 0:
                continue
            dist = np.hypot(dx, dy) * texel_m
            rise = (np.roll(h_m, (-dy, -dx), axis=(0, 1)) - h_m) / dist
            best = np.maximum(best, rise)
        occl += best / np.sqrt(1 + best * best)
    return (1.0 - occl / dirs).astype(np.float32)


def downsample(a, px):
    """Box-filter a periodic S x S map down to px x px (px divides S)."""
    k = S // px
    return a if k <= 1 else a.reshape(px, k, px, k).mean(axis=(1, 3)).astype(np.float32)


def save16(a01, path):
    Image.fromarray(np.round(np.clip(a01, 0, 1) * 65535).astype(np.uint16), "I;16").save(path)


def save8(a, path):
    T.save(a, path)


# ============================================================================================== surfaces
# Each builder returns: dict(h=height in metres (S x S, periodic, same placement as the albedo), repeat=metres per
# repeat, ao_radius=metres, albedo=library albedo to check against, check=(mask, darker) alignment test where the
# structure is procedural: the albedo must be darker inside `mask` (joints / grooves / butts) than outside),
# normal=True to write a new normal map (only where the library has none).

def paving_slabs():
    """build_textures.paving_slabs: 4 x 4 slabs of 0.6 m, 5 px sanded joints, 5 px rounded slab edge. Joints sit
    9 mm deep on their sand, the slab edge rolls off 4 mm, and each slab sits up to 0.8 mm off its neighbours."""
    n, sp, jw = 4, S // 4, 5
    y, x = np.mgrid[0:S, 0:S]
    jx = np.minimum(x % sp, sp - x % sp).astype(np.float32)
    jy = np.minimum(y % sp, sp - y % sp).astype(np.float32)
    dist = np.minimum(jx, jy)
    joint = np.clip(jw / 2 + 0.5 - dist, 0, 1)
    bevel = np.clip((dist - jw / 2) / 5.0, 0, 1)
    sid = (y // sp) * n + (x // sp)
    grain = ai_detail("concrete_smooth_s12", 40, 0.9)
    lip = np.random.default_rng(2301).uniform(-0.0008, 0.0008, n * n).astype(np.float32)
    slab = lip[sid] - 0.004 * (1.0 - bevel ** 0.6) + 0.00012 * grain
    sand = -0.009 + 0.0006 * T.fft_blur(grain, 1.0)
    h = slab * (1 - joint) + sand * joint
    sh = (sp // 2, sp // 2)
    roll = lambda a: np.roll(a, sh, axis=(0, 1))  # noqa: E731
    return dict(h=roll(h), repeat=2.4, ao_radius=0.02, albedo="paving_slabs", check=roll(joint) > 0.5)


def printed_concrete_layers():
    """build_textures.printed_concrete_layers: 32 level beads per repeat (4 cm each, 32 px), the same sub-pixel
    waviness along each bead. The grooves are 6 mm deep; each layer stands up to 0.4 mm proud of its neighbours
    and the extrusion streaks of the albedo add a 0.15 mm ripple along the bead."""
    N, P = 32, S // 32
    rows = np.arange(S, dtype=np.float32)[:, None] + P / 2
    wob = T.periodic_noise(S, S, None, 3, aniso=(P * 0.6, 110)) * 0.6
    yy = rows + wob
    t = (yy % P) / P
    layer = np.floor(yy / P).astype(np.int64) % N
    bead = np.sin(np.pi * t) ** 0.6
    streak = T.periodic_noise(S, S, None, 5, aniso=(1.4, 70))
    paint = T.fft_blur(ai_detail("concrete_smooth_s11", 50, 0.9), 3.0)
    proud = np.random.default_rng(3201).uniform(-0.0004, 0.0004, N).astype(np.float32)
    h = 0.006 * (bead - 1.0) + bead * proud[layer] + 0.00015 * streak * bead + 0.0002 * paint
    return dict(h=h.astype(np.float32), repeat=1.28, ao_radius=0.015, albedo="printed_concrete_layers",
                check=bead < 0.35)


def roof_shingle_dark():
    """build_textures.roof_shingle_dark: 8 courses x 4 shingles (50 x 25 cm), half bond with the same random
    shifts. Each course is a wedge rising to its butt edge (12 mm), the thin shadow line under the butt and the
    3-4 px side joints go to the bottom; each shingle sits up to 0.6 mm off its neighbours."""
    rows, per, rh, sw = 8, 4, S // 8, S // 4
    rng = np.random.default_rng(17)
    y = np.arange(S)[:, None] + np.zeros((1, S), np.int64)
    x = np.arange(S)[None, :] + np.zeros((S, 1), np.int64)
    r = y // rh
    off = (r % 2) * (sw // 2) + (rng.integers(-10, 11, rows))[r % rows]
    xs = (x + off) % S
    c = xs // sw
    ty = (y % rh) / rh
    tx = np.minimum(xs % sw, sw - xs % sw).astype(np.float32)
    sid = r * per + c
    joint = np.clip(2.0 - tx, 0, 1)
    butt = np.clip((ty - (1 - 3.5 / rh)) * rh / 3.5, 0, 1)
    grain = T.fft_blur(ai_detail("concrete_smooth_s12", 30, 1.0), 1.0)
    wedge = (0.3 + 0.7 * ty) * (1 - joint) * (1 - butt)
    var = np.random.default_rng(1701).uniform(-0.0006, 0.0006, rows * per).astype(np.float32)
    h = 0.012 * (wedge - 1.0) + var[sid] * (1 - joint) * (1 - butt) + 0.0002 * grain
    sh = (rh // 2, 37)
    roll = lambda a: np.roll(a, sh, axis=(0, 1))  # noqa: E731
    return dict(h=roll(h.astype(np.float32)), repeat=2.0, ao_radius=0.02, albedo="roof_shingle_dark",
                check=roll(np.maximum(joint, butt)) > 0.5)


def fibercement_panel_joints():
    """build_textures.fibercement_panels_jointed: 4 x 2 panels of 1.2 x 2.4 m, 4 px shadow-gap joints with a
    3 px edge. The gaps are 12 mm deep, the panel edge eases off 4 mm. Shared by the sage, clay and grey versions."""
    pw, ph, jw = 256, 512, 4
    x = np.arange(S)[None, :]
    y = np.arange(S)[:, None]
    jx = np.minimum(x % pw, pw - x % pw)
    jy = np.minimum(y % ph, ph - y % ph)
    dist = np.minimum(jx + 0 * y, jy + 0 * x).astype(np.float32)
    joint = np.clip((jw / 2 + 0.5 - dist), 0, 1)
    edge = np.clip(1.0 - (dist - jw / 2) / 3.0, 0, 1) * (1 - joint)
    h = 0.012 * (-joint - 0.35 * edge)
    sh = (ph // 2, pw // 2)
    roll = lambda a: np.roll(a, sh, axis=(0, 1))  # noqa: E731
    return dict(h=roll(h.astype(np.float32)), repeat=4.8, ao_radius=0.03, albedo="fibercement_sage",
                check=roll(joint) > 0.5, depth_px=512)


def kerb_concrete():
    """build_textures.kerb_concrete: a joint every 1 m along U (U = along the kerb), 6 mm deep, 2.5 mm edge."""
    x = np.arange(S)[None, :] + np.zeros((S, 1), np.int64)
    jx = np.minimum(x % 512, 512 - x % 512).astype(np.float32)
    joint = np.clip(2.0 - jx, 0, 1)
    edge = np.clip(1.0 - (jx - 1.5) / 6.0, 0, 1) * (1 - joint)
    grain = ai_detail("concrete_smooth_s12", 30, 1.0)
    h = -0.006 * joint - 0.0025 * edge + 0.00015 * T.fft_blur(grain, 0.8)
    roll = lambda a: np.roll(a, 256, axis=1)  # noqa: E731
    return dict(h=roll(h.astype(np.float32)), repeat=2.0, ao_radius=0.015, albedo="kerb_concrete",
                check=roll(joint) > 0.5, normal=True)


def _asphalt_grain():
    """The fine aggregate of build_textures._asphalt_detail (the painterly blotches are colour, not shape)."""
    return ai_detail("asphalt_s12", 40, 1.0, band=0.22)


def asphalt():
    """Asphalt: the aggregate the albedo shows (lighter chips) stands up to about 2 mm out of the binder."""
    sp = T.fft_blur(_asphalt_grain(), 0.7)
    h = 0.0022 * (unit_range(sp, 1, 99.7) - 1.0)
    return dict(h=h, repeat=4.0, ao_radius=0.01, albedo="asphalt", normal=True)


def asphalt_cracked():
    """asphalt_cracked: the same aggregate (rolled like the albedo) plus the Krea2 cracks, 6 mm deep."""
    sp = np.roll(T.fft_blur(_asphalt_grain(), 0.7), (S // 3, S // 2), axis=(0, 1))
    y = T.luminance(raw_rgb("asphalt_cracked_v2_s12"))
    y = T.flatten(y, 30, 1.0)
    y = T.quilt_cut(y, 0.16)
    crack = np.clip(T.fft_blur(y, 3.0) - y, 0, None)
    crack = np.clip((crack - 0.025) / 0.07, 0, 1)
    crack = T.fft_blur(crack, 0.6)
    walls = np.clip(T.fft_blur(crack, 1.2) * 1.6, 0, 1)
    h = 0.0022 * (unit_range(sp, 1, 99.7) - 1.0) - 0.006 * walls
    return dict(h=h.astype(np.float32), repeat=4.0, ao_radius=0.012, albedo="asphalt_cracked",
                check=crack > 0.5, normal=True)


def _organic(name, sigma, blur, depth_m, krea=None, mix=0.0):
    """Height of an organic surface from its own albedo (lighter = higher: pebble tops, clump tops, blade tips):
    luminance minus the soft painterly blotches, lightly smoothed. With `krea`, a Krea2 height picture made from
    this albedo is mixed in (only if it lines up: see krea_alignment)."""
    rgb = albedo(name)
    hp = T.fft_blur(high_pass_lum(rgb, sigma), blur)
    h01 = unit_range(hp, 0.5, 99.5)
    if krea and mix > 0:
        k = krea_height(krea)
        if k is None:
            print(f"  {krea} missing: {name} uses its albedo only")
        else:
            k = T.fft_blur(k, blur)
            # Krea2's edit is not seamless at the wrap edges: fade it out there (the albedo height is seamless
            # and lines up), over the outer 24 px.
            ramp = np.clip(np.minimum(np.arange(S), S - 1 - np.arange(S)) / 24.0, 0, 1).astype(np.float32)
            w = mix * np.minimum(ramp[:, None], ramp[None, :])
            h01 = (1 - w) * h01 + w * k
    return depth_m * (h01 - 1.0)


def krea_height(path):
    """A Krea2 height picture (krea_heights.sh) as 0..1, its soft blotches removed like the albedo's."""
    p = os.path.join(KREA, path)
    if not os.path.exists(p):
        return None
    k = T.luminance(np.asarray(Image.open(p).convert("RGB").resize((S, S), Image.LANCZOS), np.float32) / 255.0)
    k = k - T.reflect_blur(k, 40) + k.mean()
    return unit_range(k, 0.5, 99.5)


def krea_alignment(name, path, sigma=10):
    """How well a Krea2 height picture lines up with the albedo: normalised correlation of the two high-passed
    luminances at zero shift, the best shift (phase correlation) and the correlation there, in 4 quadrants
    (an edit can drift in one part of the image only)."""
    a = high_pass_lum(albedo(name), sigma)
    k = krea_height(path)
    k = k - T.fft_blur(k, sigma)
    out = []
    h = S // 2
    for qy in (0, h):
        for qx in (0, h):
            pa, pk = a[qy:qy + h, qx:qx + h], k[qy:qy + h, qx:qx + h]
            pa, pk = (pa - pa.mean()) / pa.std(), (pk - pk.mean()) / pk.std()
            zero = float((pa * pk).mean())
            f = np.fft.fft2(pa) * np.conj(np.fft.fft2(pk))
            c = np.real(np.fft.ifft2(f / np.maximum(np.abs(f), 1e-9)))
            dy, dx = np.unravel_index(np.argmax(c), c.shape)
            dy, dx = (dy + h // 2) % h - h // 2, (dx + h // 2) % h - h // 2
            out.append((round(zero, 3), (int(dy), int(dx))))
    return out


def gravel():
    """Gravel: rounded pebbles about 2-4 cm across, standing 10 mm out of the gaps (16 mm read as a dark, noisy
    speckle at a grazing view: the concept's ground is low contrast). The normal map keeps the rounder 16 mm
    pebbles (normal_gain). Krea2's height picture of this very albedo (correlation 0.95 at zero shift, see
    krea_alignment) gives each pebble a clean dome, which the albedo's luminance alone cannot (a darker pebble is
    not a lower one). The depth map is 512 px: its pebbles alias less far away."""
    h = _organic("gravel", 10, 0.8, 0.010, krea="krea_height_gravel_s11.png", mix=0.75)
    return dict(h=h, repeat=1.0, ao_radius=0.012, ao_floor=0.85, albedo="gravel", normal=True, normal_gain=1.6,
                depth_px=512)


def grass_lawn():
    """Lawn: blade tips (the lighter strokes) up to 8 mm above the darker ground between them. Subtle on purpose.
    Half from Krea2's height picture of the albedo (correlation 0.95), half from the albedo."""
    h = _organic("grass_lawn", 12, 0.8, 0.008, krea="krea_height_grass_lawn_s11.png", mix=0.5)
    return dict(h=h, repeat=2.0, ao_radius=0.012, ao_floor=0.85, albedo="grass_lawn", normal=True, depth_px=512)


def garden_soil():
    """Garden soil: clumps up to 12 mm above the flat soil."""
    h = _organic("garden_soil", 14, 1.0, 0.012)
    return dict(h=h, repeat=1.0, ao_radius=0.015, ao_floor=0.75, albedo="garden_soil", normal=True)


BUILDERS = {
    "paving_slabs": paving_slabs,
    "printed_concrete_layers": printed_concrete_layers,
    "roof_shingle_dark": roof_shingle_dark,
    "fibercement_panel_joints": fibercement_panel_joints,
    "kerb_concrete": kerb_concrete,
    "asphalt": asphalt,
    "asphalt_cracked": asphalt_cracked,
    "gravel": gravel,
    "grass_lawn": grass_lawn,
    "garden_soil": garden_soil,
}

# What the game uses (game/assets/data/surface_depth.ron): copied into game/assets/textures/showhome/ by --game.
# Asphalt has AO and a normal map but no parallax (its 2 mm aggregate is under a pixel of offset).
GAME_DEPTH = ["paving_slabs", "printed_concrete_layers", "roof_shingle_dark", "fibercement_panel_joints", "gravel",
              "grass_lawn"]
GAME_ORM = GAME_DEPTH + ["asphalt"]
GAME_NORMALS = ["asphalt", "gravel", "grass_lawn"]

# AO: how dark a fully enclosed texel may get (the albedos already carry a painted cavity tone: keep it gentle;
# 0.55 doubled the joints' darkness in shade).
AO_FLOOR = 0.72
# AO is smooth: half resolution is plenty and a quarter of the memory.
AO_PX = 512


# ============================================================================================== output
def lit(h_m, texel_m, rgb, sun=(-0.55, 0.45, 0.70)):
    """The albedo lit by a low sun through the height's normals (preview only)."""
    n = normal_from_height_m(h_m, texel_m) * 2 - 1
    l = np.asarray(sun, np.float32) / np.linalg.norm(sun)
    ndl = np.clip(n[..., 0] * l[0] + n[..., 1] * l[1] + n[..., 2] * l[2], 0, 1)
    return np.clip(rgb * (0.35 + 0.9 * ndl)[..., None], 0, 1)


def check_sheet(name, rgb, depth01, ao, h_m, texel_m):
    cell = 384
    crop = slice(0, 384)

    def tile(a):
        a = a[crop, crop]
        if a.ndim == 2:
            a = np.repeat(a[..., None], 3, axis=2)
        return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))

    over = rgb.copy()
    edges = np.abs(np.roll(depth01, 1, 0) - depth01) + np.abs(np.roll(depth01, 1, 1) - depth01)
    over[edges > 0.08] = (1.0, 0.1, 0.6)
    panels = [rgb, 1.0 - depth01, ao, lit(h_m, texel_m, rgb), over]
    sheet = Image.new("RGB", (cell * len(panels), cell))
    for i, p in enumerate(panels):
        sheet.paste(tile(p), (i * cell, 0))
    sheet.save(os.path.join(PREV, f"{name}_check.png"))


def build(name):
    r = BUILDERS[name]()
    h = r["h"].astype(np.float32)
    texel = r["repeat"] / S
    hmax, hmin = float(h.max()), float(h.min())
    depth01 = (hmax - h) / max(hmax - hmin, 1e-9)
    depth_cm = (hmax - hmin) * 100.0
    save16(downsample(depth01, r.get("depth_px", S)), os.path.join(OUT, f"{name}_depth.png"))
    # AO relative to the surface's own open level (its 90th percentile = 1): an evenly bumpy surface (gravel)
    # must not darken as a whole, since the albedo is already calibrated to the concept. The deepest groove
    # reaches AO_FLOOR at most.
    ao = horizon_ao(h, texel, r["ao_radius"])
    ao = np.clip(ao / float(np.percentile(ao, 90)), 0, 1)
    floor = r.get("ao_floor", AO_FLOOR)
    ao = 1.0 - (1.0 - ao) * min(1.0, (1.0 - floor) / max(1.0 - float(ao.min()), 1e-6))
    ao_small = downsample(ao, AO_PX)
    orm = np.stack([ao_small, np.ones_like(ao_small), np.zeros_like(ao_small)], axis=2)
    save8(orm, os.path.join(OUT, f"{name}_orm.png"))
    if r.get("normal"):
        nrm = normal_from_height_m(h, texel, r.get("normal_gain", 1.0))
        save8(nrm, os.path.join(OUT, f"{name}_normal.png"))
    rgb = albedo(r["albedo"])
    info = dict(depth_cm=round(depth_cm, 3), repeat_m=r["repeat"], ao_min=round(float(ao.min()), 3),
                ao_mean=round(float(ao.mean()), 3))
    if "check" in r:
        # Alignment: the albedo is darker in the structure's joints / grooves than elsewhere (ratio < 1). A wrong
        # roll or seed puts the mask on plain surface and the ratio goes to about 1.
        lum = T.luminance(rgb)
        m = r["check"]
        ratio = float(lum[m].mean() / lum[~m].mean())
        shifted = float(lum[np.roll(m, (S // 7, S // 5), axis=(0, 1))].mean() / lum.mean())
        info.update(align_ratio=round(ratio, 3), misaligned_ratio=round(shifted, 3))
    check_sheet(name, rgb, depth01, ao, h, texel)
    print(f"{name:28s} {json.dumps(info)}", flush=True)
    return info


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    game = "--game" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(PREV, exist_ok=True)
    jpath = os.path.join(OUT, "depth.json")
    allinfo = json.load(open(jpath)) if os.path.exists(jpath) else {}
    for n in args or list(BUILDERS):
        allinfo[n] = build(n)
    with open(jpath, "w") as f:
        json.dump(allinfo, f, indent=1, sort_keys=True)
    if game:
        for names, suffix in ((GAME_DEPTH, "_depth"), (GAME_ORM, "_orm"), (GAME_NORMALS, "_normal")):
            for n in names:
                shutil.copy2(os.path.join(OUT, n + suffix + ".png"), os.path.join(GAME, n + suffix + ".png"))
        print("copied into", GAME)


if __name__ == "__main__":
    main()
