"""Build the bullet-hole atlas for the game (game/assets/textures/fx/impacts/).

Every mark is drawn from code (crater outlines, bores, facets, cracks, splinters, chipped rings, dust), so its
shapes are exact and its albedo, height, normals and depth line up. The Krea2 raws in raw/ (gen_raw.py) only give
the painterly grain and mottling of the material a shot exposes. Colours follow the Showhome palette
(assets/maps/showhome/textures/README.md): big clean shapes, low contrast, no grime.

A mark has two layers that share one normal map and one depth map:
- the CORE layer (impacts_albedo.png): what the shot exposes or leaves (crater, bore, bare metal, fresh wood,
  cracks, dust), in its own colour;
- the PAINT layer (impacts_paint.png): the surface itself, bent or lifted (cladding shards, a dent in painted
  metal, wood splinters, cracked plates round a crater). It is white (with painted AO) and the game tints it with
  the colour of the surface that was hit, so one atlas fits every wall colour.

Outputs (square atlas of GRID x GRID cells, cell (col, row) = index % GRID, index // GRID):
  impacts_albedo.png    sRGB RGBA, straight alpha, colour dilated under alpha 0 (no dark mip fringes)
  impacts_paint.png     sRGB RGBA at 1/2 resolution: grey painted AO, alpha = paint coverage
  impacts_normal.png    linear, OpenGL convention (+X right, +Y image up)
  impacts_depth_mr.png  linear: R = depth for parallax (white = deep, 1.0 = DEPTH_REF half-widths), G = roughness,
                        B = metallic (Bevy's metallic_roughness layout, so one image serves both)
  impacts_atlas.ron     the cell of every kind and variant, the sprites, DEPTH_REF
Previews in preview/: contact_sheet.png (every cell over its surface, lit from the upper left) and the maps.

Usage: python build_atlas.py
"""
import math
import os

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
GAME_OUT = os.path.join(ROOT, "game", "assets", "textures", "fx", "impacts")
PREVIEW = os.path.join(HERE, "preview")
RAW = os.path.join(HERE, "raw")

CELL = 192          # px per cell in the atlas
SS = 2              # supersampling while drawing
S = CELL * SS       # px per cell while drawing
GRID = 6            # cells per row and per column (square atlas: parallax shifts U and V alike)
DEPTH_REF = 0.6     # depth map 1.0 = this many decal half-widths below the surface
VARIANTS = 4
CONTENT = 0.86      # nothing is drawn past this radius (half-widths): padding against mip / parallax bleed

KINDS = ["Plaster", "Cladding", "Wood", "Metal", "Glass", "Pavement", "Soil"]
SPRITES = ["puff", "chip", "spark"]

# Surface colours for the previews only (sRGB, the Showhome palette).
PREVIEW_SURFACE = {
    "Plaster": (214, 200, 176),
    "Cladding": (145, 153, 114),
    "Wood": (226, 219, 205),
    "Metal": (231, 223, 218),
    "Glass": (70, 82, 92),
    "Pavement": (112, 105, 106),
    "Soil": (126, 140, 58),
}

ax = (np.arange(S) + 0.5) / S * 2.0 - 1.0
X, Y = np.meshgrid(ax, -ax)  # x right, y up (row 0 = top of the image)
R = np.hypot(X, Y)
TH = np.arctan2(Y, X)
PX = 2.0 / S  # one drawing pixel in half-widths


# ------------------------------------------------------------------------------------------------ colour

def lin(c):
    c = np.asarray(c, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb8(c):
    c = np.clip(c, 0.0, 1.0)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return np.clip(np.round(s * 255.0), 0, 255).astype(np.uint8)


_raw_cache = {}


def raw(name):
    if name not in _raw_cache:
        img = np.asarray(Image.open(os.path.join(RAW, name + ".png")).convert("RGB"), dtype=np.float64)
        _raw_cache[name] = lin(img)
    return _raw_cache[name]


def grain(rng, name, target_srgb, contrast=1.0, zoom=1.0, rotate=False):
    """A crop of a Krea2 raw at drawing size, recoloured so its mean is `target_srgb` (linear mean), with its
    detail scaled by `contrast` (1 = the raw's own)."""
    src = raw(rng.choice([name + "_s11", name + "_s12"]))
    h, w, _ = src.shape
    size = int(min(h, w) * 0.5 / zoom)
    y0 = rng.integers(0, h - size)
    x0 = rng.integers(0, w - size)
    crop = src[y0:y0 + size, x0:x0 + size]
    if rotate:
        crop = np.rot90(crop, rng.integers(0, 4))
    img = np.asarray(Image.fromarray(to_srgb8(crop)).resize((S, S), Image.BICUBIC), dtype=np.float64)
    img = lin(img)
    mean = img.reshape(-1, 3).mean(0)
    detail = img / np.maximum(mean, 1e-4)
    detail = 1.0 + (detail - 1.0) * contrast
    return np.clip(detail, 0.0, 3.0) * lin(target_srgb)


def luminance(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


# ------------------------------------------------------------------------------------------------ shapes

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def noise(rng, sigma_px, octaves=3):
    """Smooth value noise in about -1..1 (sum of blurred white noise)."""
    out = np.zeros((S, S))
    amp = 1.0
    total = 0.0
    for o in range(octaves):
        n = ndimage.gaussian_filter(rng.standard_normal((S, S)), sigma_px / (2 ** o), mode="wrap")
        n /= n.std() + 1e-9
        out += n * amp
        total += amp
        amp *= 0.5
    return out / total


def lobes(rng, kmin, kmax, amp):
    out = np.zeros_like(TH)
    for k in range(kmin, kmax + 1):
        out += rng.uniform(0.3, 1.0) * amp / k ** 0.6 * np.cos(k * TH + rng.uniform(0, 2 * np.pi))
    return out


def polygon_radius(rng, n, base, amp, aspect=(1.0, 1.0), centre=(0.0, 0.0)):
    """Radius of a random star-shaped polygon (straight chipped edges) around `centre`, at every pixel's angle.
    Returns (radius at the pixel's angle, pixel's distance from centre); `aspect` stretches it along x / y."""
    angles = np.sort(rng.uniform(0.0, 2 * np.pi, n))
    # keep the vertices from bunching up: at least a third of the even spacing apart
    angles = np.sort(np.mod(np.linspace(0, 2 * np.pi, n, endpoint=False) + rng.uniform(-0.33, 0.33, n) * 2 * np.pi / n
                            + rng.uniform(0, 2 * np.pi), 2 * np.pi))
    radii = base * (1.0 + amp * rng.uniform(-1.0, 1.0, n))
    pts = radii[:, None] * np.stack([np.cos(angles), np.sin(angles)], 1)
    px = (X - centre[0]) / aspect[0]
    py = (Y - centre[1]) / aspect[1]
    th = np.mod(np.arctan2(py, px), 2 * np.pi)
    idx = np.mod(np.searchsorted(angles, th) - 1, n)
    a = pts[idx]
    b = pts[(idx + 1) % n]
    e = b - a
    d = np.stack([np.cos(th), np.sin(th)], -1)
    cross = lambda u, v: u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]  # noqa: E731
    t = cross(a, e) / np.where(np.abs(cross(d, e)) < 1e-9, 1e-9, cross(d, e))
    return t, np.hypot(px, py)


def at(field, x, y):
    """A field's value at cell coordinates (x right, y up, half-widths)."""
    col = int(np.clip((x + 1.0) / 2.0 * S, 0, S - 1))
    row = int(np.clip((1.0 - y) / 2.0 * S, 0, S - 1))
    return float(field[row, col])


def inside(dist_px):
    """Anti-aliased coverage from a signed distance in drawing pixels (positive = inside)."""
    return np.clip(dist_px + 0.5, 0.0, 1.0)


def edge_px(radius, r):
    """Signed distance in drawing pixels to a radial outline (positive inside), good near the outline."""
    return (radius - r) / PX


def walk(rng, start, angle, length, step=0.012, wander=0.25, kink=0.0):
    """A crack's polyline from `start` heading `angle`, wandering a little (and kinking now and then)."""
    pts = [np.array(start, dtype=np.float64)]
    a = angle
    travelled = 0.0
    while travelled < length:
        a += rng.normal(0.0, wander) * step / 0.012
        if kink and rng.random() < kink:
            a += rng.choice([-1, 1]) * rng.uniform(0.25, 0.6)
        p = pts[-1] + step * np.array([math.cos(a), math.sin(a)])
        if np.hypot(*p) > CONTENT - 0.02:
            break
        pts.append(p)
        travelled += step
    return np.array(pts)


def strokes(lines):
    """Rasterise polylines with tapering widths (half-widths units, full width) into coverage and a V-groove
    profile (1 on the centre line, 0 at the edge). `lines` = [(points Nx2, width at start, width at end)]."""
    mask = np.zeros((S, S), dtype=bool)
    wmap = np.zeros((S, S))
    for pts, w0, w1 in lines:
        if len(pts) < 2:
            continue
        seg = np.diff(pts, axis=0)
        lens = np.hypot(seg[:, 0], seg[:, 1])
        total = lens.sum() + 1e-9
        acc = 0.0
        for p, s, ln in zip(pts[:-1], seg, lens):
            n = max(2, int(ln / PX * 2) + 1)
            for k in range(n):
                f = k / (n - 1)
                q = p + s * f
                w = w0 + (w1 - w0) * (acc + ln * f) / total
                col = int((q[0] + 1.0) / 2.0 * S)
                row = int((1.0 - q[1]) / 2.0 * S)
                if 0 <= row < S and 0 <= col < S and w > wmap[row, col]:
                    mask[row, col] = True
                    wmap[row, col] = w
            acc += ln
    if not mask.any():
        z = np.zeros((S, S))
        return z, z
    dist, (iy, ix) = ndimage.distance_transform_edt(~mask, return_indices=True)
    half = wmap[iy, ix] / PX * 0.5
    cov = np.clip(half - dist + 0.5, 0.0, 1.0)
    groove = np.clip(1.0 - dist / np.maximum(half, 0.5), 0.0, 1.0) * (cov > 0)
    return cov, groove


def facets(rng, n, region, amp, slope):
    """Faceted fracture planes: Voronoi cells over `region`, each a random tilted plane."""
    ys, xs = np.nonzero(region)
    if len(xs) == 0:
        return np.zeros((S, S))
    pick = rng.choice(len(xs), size=min(n, len(xs)), replace=False)
    seeds = np.stack([X[ys[pick], xs[pick]], Y[ys[pick], xs[pick]]], 1)
    tree = cKDTree(seeds)
    _, idx = tree.query(np.stack([X.ravel(), Y.ravel()], 1))
    idx = idx.reshape(S, S)
    off = rng.uniform(-amp, amp, len(seeds))
    ang = rng.uniform(0, 2 * np.pi, len(seeds))
    mag = rng.uniform(0, slope, len(seeds))
    gx = np.cos(ang) * mag
    gy = np.sin(ang) * mag
    return off[idx] + gx[idx] * (X - seeds[idx, 0]) + gy[idx] * (Y - seeds[idx, 1])


def scatter_blobs(rng, n, rmin, rmax, size, rays=None):
    """Small irregular blobs (chips, clods) scattered between radii rmin..rmax; returns coverage and a dome."""
    cov = np.zeros((S, S))
    dome = np.zeros((S, S))
    for _ in range(n):
        if rays is not None:
            a = rng.choice(rays) + rng.normal(0, 0.18)
        else:
            a = rng.uniform(0, 2 * np.pi)
        rr = rng.uniform(rmin, rmax)
        c = (rr * math.cos(a), rr * math.sin(a))
        s = rng.uniform(*size)
        rad, d = polygon_radius(rng, int(rng.integers(5, 8)), s, 0.35, centre=c)
        k = inside(edge_px(rad, d))
        cov = np.maximum(cov, k)
        dome = np.maximum(dome, k * np.clip(1.0 - d / np.maximum(rad, 1e-3), 0, 1) ** 0.5)
    return cov, dome


class Mark:
    """The fields of one cell at drawing size."""

    def __init__(self, rough=0.9):
        self.core = np.zeros((S, S, 3))
        self.core_a = np.zeros((S, S))
        self.paint_g = np.ones((S, S))
        self.paint_a = np.zeros((S, S))
        self.h = np.zeros((S, S))
        self.rough = np.full((S, S), rough)
        self.metal = np.zeros((S, S))
        self.normal_gain = 1.0

    def over(self, rgb, a):
        """Paint `rgb` (linear, HxWx3 or 3) over the core layer with coverage `a`."""
        a = np.clip(a, 0.0, 1.0)
        rgb = np.broadcast_to(np.asarray(rgb, dtype=np.float64), (S, S, 3))
        out_a = a + self.core_a * (1.0 - a)
        w = np.where(out_a > 1e-6, a / np.maximum(out_a, 1e-6), 0.0)[..., None]
        self.core = self.core * (1.0 - w) + rgb * w
        self.core_a = out_a

    def fade_out(self):
        k = smoothstep(CONTENT, CONTENT - 0.06, R)
        self.core_a *= k
        self.paint_a *= k
        self.h *= k


def dust(rng, m, r_in, width, alpha, colour, rays=0):
    """A soft dust ring from radius `r_in` outward (r_in may be an array: the crater's outline)."""
    d = R - r_in
    a = alpha * (1.0 - smoothstep(0.0, width, d)) * (d > -0.01)
    a *= np.clip(0.75 + 0.45 * noise(rng, 6.0), 0.2, 1.3)
    if rays:
        a *= np.clip(0.55 + 0.6 * np.cos(rays * TH + rng.uniform(0, 6.3)) * (0.5 + 0.5 * noise(rng, 20.0, 1)), 0.15, 1.2)
    m.over(lin(colour), np.clip(a, 0.0, 1.0) * (1.0 - m.core_a))


# ------------------------------------------------------------------------------------------------ kinds

def plaster(rng):
    """Printed concrete / plaster: a chipped crumbly crater round a deep dark bore, hairline cracks, a pale dust
    ring. Concrete does not bend, so there is no paint layer: the crater's broken rim is the edge."""
    m = Mark(rough=0.92)
    centre = (rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03))
    rc, rd = polygon_radius(rng, int(rng.integers(10, 15)), rng.uniform(0.4, 0.5), 0.2, centre=centre)
    rc = rc * (1.0 + lobes(rng, 5, 11, 0.035))
    t = np.clip(rd / rc, 0.0, 1.5)
    crater = inside(edge_px(rc, rd))
    # crumbly floor: a bowl, gentle fracture facets and the rubble grain itself as relief
    rgb = grain(rng, "rubble_cream", (206, 192, 168), contrast=0.5, zoom=rng.uniform(1.5, 2.5), rotate=True)
    lum = ndimage.gaussian_filter(luminance(rgb), 1.0)
    lum = (lum - lum.mean()) / (lum.std() + 1e-6)
    bowl = 0.035 + 0.15 * (1.0 - np.clip(t, 0, 1) ** 2.0)
    fac = facets(rng, int(rng.integers(6, 10)), crater > 0.5, 0.012, 0.045)
    h_crater = -np.maximum(bowl + (fac - 0.01 * lum) * smoothstep(1.0, 0.75, t), 0.02)
    rb, bd = polygon_radius(rng, 9, rng.uniform(0.1, 0.125), 0.15, centre=centre)
    bore = smoothstep(rb * 1.8, rb * 0.7, bd)
    h = np.where(crater > 0, np.minimum(h_crater, -0.45 * bore), 0.0) * crater
    # painted AO: the freshly broken rim stays light, the cavity darkens toward the bore, the bore near black
    inner = np.clip(1.0 - t, 0.0, 1.0)
    rgb *= (1.0 - 0.5 * smoothstep(0.05, 0.85, inner))[..., None]
    rim = crater * (1.0 - smoothstep(0.0, 0.07, inner))
    rgb = rgb * (1 - 0.35 * rim[..., None]) + lin((238, 230, 214)) * 0.35 * rim[..., None]
    rgb = rgb * (1 - bore[..., None]) + lin((36, 31, 28)) * bore[..., None]
    m.over(rgb, crater)
    # hairline cracks from the rim
    lines = []
    for _ in range(int(rng.integers(2, 5))):
        a = rng.uniform(0, 2 * np.pi)
        start_r = at(rc, centre[0] + 0.3 * math.cos(a), centre[1] + 0.3 * math.sin(a)) * 0.95
        start = (centre[0] + start_r * math.cos(a), centre[1] + start_r * math.sin(a))
        pts = walk(rng, start, a, rng.uniform(0.1, 0.28), wander=0.35)
        lines.append((pts, 0.009, 0.002))
        if rng.random() < 0.35 and len(pts) > 6:
            k = int(rng.integers(len(pts) // 3, len(pts) - 2))
            lines.append((walk(rng, pts[k], a + rng.choice([-1, 1]) * rng.uniform(0.5, 0.9), rng.uniform(0.05, 0.12),
                               wander=0.4), 0.005, 0.0015))
    cov, groove = strokes(lines)
    h -= 0.02 * groove * (1 - crater)
    m.over(lin((120, 110, 96)), cov * 0.65 * (1 - crater))
    dust(rng, m, rc + 0.01, rng.uniform(0.14, 0.24), 0.32, (240, 233, 218))
    m.h = h
    m.rough[:] = 0.92
    m.fade_out()
    return m


def cladding(rng):
    """Fibre-cement cladding (and slate): a sharp punched hole, a ring of flaked paint showing the grey fibrous
    core, brittle radial cracks, and the shards between them pushed in or lifted (paint layer)."""
    m = Mark(rough=0.85)
    rb, bd = polygon_radius(rng, 8, rng.uniform(0.11, 0.14), 0.1)
    rbm = float(np.mean(rb))
    bore = smoothstep(rbm * 1.15, rbm * 0.85, bd)
    rr, rd = polygon_radius(rng, int(rng.integers(15, 22)), rbm * rng.uniform(1.8, 2.3), 0.3)
    ring = inside(edge_px(rr, rd))
    # brittle radial cracks from the hole
    n = int(rng.integers(4, 8))
    base = rng.uniform(0, 2 * np.pi)
    angles = np.sort(np.mod(base + np.arange(n) * 2 * np.pi / n + rng.uniform(-0.35, 0.35, n), 2 * np.pi))
    lines = []
    lengths = []
    for a in angles:
        ln = rng.uniform(0.38, 0.74)
        lengths.append(ln)
        start = (0.12 * math.cos(a), 0.12 * math.sin(a))
        pts = walk(rng, start, a, ln, wander=0.08, kink=0.06)
        lines.append((pts, 0.016, 0.004))
        if rng.random() < 0.4 and len(pts) > 10:
            k = int(rng.integers(len(pts) // 2, len(pts) - 2))
            lines.append((walk(rng, pts[k], a + rng.choice([-1, 1]) * rng.uniform(0.4, 0.8), rng.uniform(0.08, 0.18),
                               wander=0.1), 0.008, 0.003))
    cov, groove = strokes(lines)
    # shards: the sectors between consecutive cracks, each pushed in (or lifted a little) toward the hole
    th = np.mod(TH, 2 * np.pi)
    sector = np.mod(np.searchsorted(angles, th) - 1, n)
    reach = np.array([min(lengths[i], lengths[(i + 1) % n]) for i in range(n)]) * rng.uniform(0.75, 1.0, n)
    push = rng.uniform(-1.0, 0.5, n)
    twist = rng.uniform(-1.0, 1.0, n)
    p_r = reach[sector]
    u = np.clip(R / p_r, 0, 1)
    a0 = angles[sector]
    a1 = angles[(sector + 1) % n]
    span = np.mod(a1 - a0, 2 * np.pi) + 1e-6
    across = np.mod(th - a0, 2 * np.pi) / span * 2 - 1
    plate = (R < p_r)
    h = np.where(plate, (0.08 * push[sector] + 0.03 * twist[sector] * across) * (1 - u) ** 1.2, 0.0)
    m.paint_a = np.where(plate, 0.92 * (1 - smoothstep(0.8, 1.0, u)), 0.0) * (1 - ring)
    m.paint_g = np.where(plate, 1.0 - 0.12 * (1 - u), 1.0)
    # flaked ring and hole
    h = np.where(ring > 0, -0.03 + 0.006 * noise(rng, 3.0), h)
    h = np.minimum(h, -0.5 * bore)
    h -= 0.035 * groove
    core = grain(rng, "fibre_core", (180, 176, 167), contrast=0.35, zoom=rng.uniform(1.0, 2.0), rotate=True)
    core *= (1.0 - 0.3 * smoothstep(np.mean(rr), rbm, R))[..., None]
    m.over(core, ring)
    m.over(lin((28, 27, 28)), bore)
    # a thin light broken edge along each crack (the board's core shows where the paint split), then the crack
    edge = np.clip(ndimage.maximum_filter(cov, 5) - cov, 0, 1) * (1 - ring)
    m.over(lin((196, 192, 184)), edge * 0.18)
    m.over(lin((44, 42, 40)), cov * 0.92 * (1 - ring))
    dust(rng, m, np.mean(rr) + 0.02, rng.uniform(0.15, 0.25), 0.16, (205, 202, 196))
    m.h = h
    m.rough = np.where(m.core_a > 0.5, 0.85, 0.65)
    m.fade_out()
    return m


def wood(rng):
    """Wood (pickets, boards, props), grain along +Y: an oval hole stretched along the grain, a torn patch of fresh
    wood with raised fibres ending in long tears, and splinters of the painted surface lifted along the grain
    (paint layer), each with a thin shadow."""
    m = Mark(rough=0.85)
    m.normal_gain = 1.2
    rbx = rng.uniform(0.085, 0.105)
    rb, bd = polygon_radius(rng, 9, 1.0, 0.12, aspect=(rbx, rbx * rng.uniform(1.35, 1.7)))
    bore = smoothstep(rb * 1.3, rb * 0.75, bd)
    tx = rng.uniform(0.17, 0.24)
    ty = rng.uniform(0.36, 0.5)
    tr, td = polygon_radius(rng, int(rng.integers(16, 24)), 1.0, 0.3, aspect=(tx, ty))
    # the torn patch runs out into long pointed tears along the grain
    tears = np.zeros((S, S))
    for _ in range(int(rng.integers(3, 6))):
        side = rng.choice([-1.0, 1.0])
        x0 = rng.uniform(-tx * 0.7, tx * 0.7)
        y0 = side * ty * 0.8
        ln = rng.uniform(0.12, 0.3)
        w = rng.uniform(0.03, 0.06)
        v = (Y - y0) * side / ln
        k = inside((w * 0.5 * (1 - np.clip(v, 0, 1)) - np.abs(X - x0 - rng.normal(0, 0.05) * (Y - y0))) / PX)
        tears = np.maximum(tears, k * (v > -0.3) * (v < 1))
    torn = np.maximum(inside((tr - td) * min(tx, ty) / PX), tears)
    fibres = grain(rng, "wood_fresh", (214, 194, 158), contrast=0.45, zoom=rng.uniform(1.2, 1.8))
    lum = luminance(fibres)
    lum = (lum - lum.mean()) / (lum.std() + 1e-6)
    h = np.where(torn > 0, -0.035 - 0.014 * lum, 0.0)
    h = np.minimum(h, -0.5 * bore) * np.maximum(torn, bore)
    depth = np.clip(-h / 0.3, 0, 1)
    fibres *= (1.0 - 0.5 * depth ** 0.6)[..., None]
    fibres = fibres * (1 - bore[..., None]) + lin((40, 30, 22)) * bore[..., None]
    m.over(fibres, torn)
    # splinters: thin strips of the painted surface lifted along the grain, fresh wood along one edge, a thin
    # shadow along the other
    splinter = np.zeros((S, S))
    lift = np.zeros((S, S))
    fresh_edge = np.zeros((S, S))
    shadow = np.zeros((S, S))
    for _ in range(int(rng.integers(8, 14))):
        side = rng.choice([-1.0, 1.0])
        x0 = rng.uniform(-tx * 0.9, tx * 0.9)
        y0 = side * ty * np.sqrt(max(0.0, 1 - (x0 / tx) ** 2)) * rng.uniform(0.6, 0.95)
        ln = rng.uniform(0.12, 0.34)
        w = rng.uniform(0.02, 0.045)
        lean = rng.normal(0, 0.06)
        y1 = y0 + side * ln
        v = np.clip((Y - y0) / (y1 - y0), 0, 1) * ((Y - y0) * side >= 0) * ((Y - y1) * side <= 0)
        cx = x0 + lean * (Y - y0)
        width = w * (1 - v) ** 0.8
        d = X - cx
        k = inside((width * 0.5 - np.abs(d)) / PX) * (v > 0) * (v < 1)
        splinter = np.maximum(splinter, k)
        lift = np.maximum(lift, k * 0.045 * (1 - v) * (0.6 + 0.4 * (1 - np.abs(d) / np.maximum(width * 0.5, 1e-4))))
        flip = rng.choice([-1.0, 1.0])
        fresh_edge = np.maximum(fresh_edge, k * (d * flip > width * 0.15))
        sh = inside((width * 0.5 + 0.012 - np.abs(d)) / PX) * (v > 0) * (v < 1) * (1 - k) * (d * flip < 0)
        shadow = np.maximum(shadow, sh * (1 - v))
    h = np.where(splinter > 0, np.maximum(h, lift), h)
    m.paint_a = np.maximum(splinter * (1 - torn), 0.0)
    m.paint_g = 1.0 - 0.2 * splinter * (1 - np.clip(lift / 0.045, 0, 1))
    m.over(lin((222, 204, 170)), fresh_edge * 0.9 * (1 - torn))
    m.over(lin((70, 58, 46)), shadow * 0.45 * (1 - torn) * (1 - splinter))
    dust(rng, m, tx, rng.uniform(0.05, 0.1), 0.1, (206, 186, 150))
    m.h = h
    m.rough = np.where(m.core_a > 0.5, 0.85, 0.6)
    m.fade_out()
    return m


def metal(rng):
    """Painted metal (truck, crane, tank, lockers): a clean round punched hole, a bright bare-metal lip bent into
    it, a ring of chipped paint showing the grey metal, and the painted sheet dented round it with a little crown
    (paint layer)."""
    m = Mark(rough=0.4)
    m.normal_gain = 1.1
    centre = (rng.uniform(-0.015, 0.015), rng.uniform(-0.015, 0.015))
    rb_base = rng.uniform(0.14, 0.17)
    rb, bd = polygon_radius(rng, 12, rb_base, 0.03, centre=centre)
    lw = rng.uniform(0.035, 0.055)
    hole = inside(edge_px(rb, bd))
    lip = inside(edge_px(rb + lw, bd)) * (1 - hole)
    rr, rd = polygon_radius(rng, int(rng.integers(22, 30)), rb_base + lw + rng.uniform(0.035, 0.08), 0.28,
                            centre=centre)
    chip = inside(edge_px(rr, rd)) * (1 - lip - hole).clip(0, 1)
    rdent = rng.uniform(0.42, 0.55)
    dent = np.clip(1 - bd / rdent, 0, 1)
    h = -0.16 * dent ** 1.8 + 0.022 * np.exp(-((bd - rdent * 0.92) / 0.05) ** 2)
    u = np.clip((bd - rb) / lw, 0, 1)
    h = np.where(lip > 0, h - 0.08 * (1 - u) ** 1.5, h)
    h = np.where(chip > 0, h - 0.012, h)
    h = np.minimum(h, -0.9 * smoothstep(rb_base * 1.02, rb_base * 0.75, bd))
    # a few short tears in the lip on some variants
    lines = []
    for _ in range(int(rng.integers(0, 4))):
        a = rng.uniform(0, 2 * np.pi)
        r0 = rb_base * 0.95
        lines.append((walk(rng, (centre[0] + r0 * math.cos(a), centre[1] + r0 * math.sin(a)), a,
                           rng.uniform(0.04, 0.09), wander=0.1), 0.008, 0.002))
    cov, groove = strokes(lines)
    h -= 0.02 * groove
    steel = grain(rng, "bare_steel", (205, 207, 212), contrast=0.5, zoom=rng.uniform(1.5, 2.5), rotate=True)
    m.over(lin((112, 114, 120)) * (1.0 + 0.08 * noise(rng, 4.0))[..., None], chip)
    m.over(steel * (0.8 + 0.2 * u)[..., None], lip)
    m.over(lin((12, 12, 14)), hole)
    m.over(lin((60, 60, 64)), cov * 0.8)
    # a faint grey smear round the hole (lead / copper wipe), soft: it reads at distance on white paint
    smear = 0.3 * smoothstep(rb_base + lw + rng.uniform(0.16, 0.26), rb_base + lw, bd) * (1 - m.core_a)
    m.over(lin((92, 92, 96)), smear * np.clip(0.7 + 0.4 * noise(rng, 5.0), 0, 1))
    m.paint_a = 0.9 * smoothstep(rdent * 1.05, rdent * 0.8, bd) * (1 - np.clip(hole + lip + chip, 0, 1))
    m.paint_g = 1.0 - 0.25 * dent ** 1.5
    m.h = h
    m.rough = np.where(lip > 0.5, 0.28, np.where(chip > 0.5, 0.45, 0.4))
    m.metal = np.where(lip > 0.5, 1.0, np.where(chip > 0.5, 0.6, 0.0))
    m.fade_out()
    return m


def glass(rng):
    """Glass: a small crushed pit with a white star of radial cracks and one or two broken rings."""
    m = Mark(rough=0.15)
    m.normal_gain = 0.8
    rp, pd = polygon_radius(rng, 9, rng.uniform(0.04, 0.065), 0.3)
    pit = inside(edge_px(rp, pd))
    n = int(rng.integers(9, 15))
    base = rng.uniform(0, 2 * np.pi)
    angles = np.sort(np.mod(base + np.arange(n) * 2 * np.pi / n + rng.uniform(-0.25, 0.25, n), 2 * np.pi))
    lines = []
    tips = []
    for a in angles:
        ln = rng.uniform(0.32, 0.8)
        pts = walk(rng, (0.03 * math.cos(a), 0.03 * math.sin(a)), a, ln, step=0.015, wander=0.04, kink=0.03)
        lines.append((pts, 0.008, 0.0025))
        tips.append(pts)
    rings = [rng.uniform(0.14, 0.26), rng.uniform(0.33, 0.5)][: int(rng.integers(1, 3))]
    for rr in rings:
        for i in range(n):
            if rng.random() > 0.65:
                continue
            a0, a1 = angles[i], angles[(i + 1) % n]
            if a1 < a0:
                a1 += 2 * np.pi
            k = 8
            pts = np.array([[(rr + rng.normal(0, 0.01)) * math.cos(a0 + (a1 - a0) * j / k),
                             (rr + rng.normal(0, 0.01)) * math.sin(a0 + (a1 - a0) * j / k)] for j in range(k + 1)])
            lines.append((pts, 0.005, 0.004))
    cov, groove = strokes(lines)
    haze = 0.4 * smoothstep(np.mean(rp) * 2.8, np.mean(rp), R) * np.clip(0.6 + 0.5 * noise(rng, 2.0), 0, 1)
    h = -0.012 * groove - 0.05 * pit
    m.over(lin((226, 234, 238)), haze)
    m.over(lin((236, 242, 245)), cov * 0.8)
    m.over(lin((244, 248, 250)), pit * 0.95)
    m.h = h
    m.rough[:] = 0.15
    m.fade_out()
    return m


def pavement(rng):
    """Asphalt, paving and kerb: a shallow chipped pock mark (no deep hole), lighter fresh stone, loose chips and
    a dust splash."""
    m = Mark(rough=0.9)
    rc, rd = polygon_radius(rng, int(rng.integers(9, 14)), rng.uniform(0.3, 0.4), 0.28)
    crater = inside(edge_px(rc, rd))
    t = np.clip(rd / rc, 0, 1.5)
    fac = facets(rng, int(rng.integers(5, 9)), crater > 0.5, 0.008, 0.05)
    h = -np.maximum(0.015 + 0.06 * (1 - np.clip(t, 0, 1) ** 1.6) + fac * smoothstep(1.0, 0.6, t), 0.01) * crater
    rp, pd = polygon_radius(rng, 7, rng.uniform(0.05, 0.07), 0.3)
    pit = smoothstep(rp * 1.3, rp * 0.7, pd)
    h = np.minimum(h, -0.16 * pit)
    stone = grain(rng, "stone_chips", (160, 156, 152), contrast=0.25, zoom=rng.uniform(2.5, 3.5), rotate=True)
    stone *= (1.0 - 0.45 * smoothstep(0.0, 0.9, 1.0 - np.clip(t, 0, 1)))[..., None]
    stone = stone * (1 - pit[..., None]) + lin((52, 48, 48)) * pit[..., None]
    m.over(stone, crater)
    rays = rng.uniform(0, 2 * np.pi, int(rng.integers(3, 6)))
    cov, dome = scatter_blobs(rng, int(rng.integers(5, 10)), 0.42, 0.74, (0.012, 0.022), rays=rays)
    cov *= (1 - crater)
    h = np.where(cov > 0, np.maximum(h, 0.02 * dome * cov), h)
    m.over(lin((150, 146, 142)), cov)
    dust(rng, m, rc + 0.01, rng.uniform(0.18, 0.3), 0.32, (192, 186, 180), rays=int(rng.integers(5, 9)))
    m.h = h
    m.fade_out()
    return m


def soil(rng):
    """Lawn, soil and gravel: a dark scuffed puff of thrown-up earth with a shallow dimple and clods; no hole."""
    m = Mark(rough=0.95)
    r0 = rng.uniform(0.34, 0.46)
    rs = r0 * (1 + lobes(rng, 2, 7, 0.22))
    t = R / rs
    blotch = 0.92 * smoothstep(1.0, 0.4, t) * np.clip(0.85 + 0.3 * noise(rng, 8.0), 0, 1.1)
    earth = grain(rng, "soil_dark", (74, 57, 44), contrast=0.6, zoom=rng.uniform(1.0, 1.6), rotate=True)
    h = -0.05 * (1 - np.clip(t, 0, 1) ** 2)
    earth *= (1.0 - 0.25 * smoothstep(0.6, 0.0, t))[..., None]
    m.over(earth, blotch)
    rays = rng.uniform(0, 2 * np.pi, int(rng.integers(3, 6)))
    cov, dome = scatter_blobs(rng, int(rng.integers(10, 20)), r0 * 0.7, 0.75, (0.02, 0.045), rays=rays)
    h = np.where(cov > 0, np.maximum(h, 0.035 * dome), h)
    m.over(lin((92, 72, 54)) * (0.85 + 0.3 * dome)[..., None], cov)
    # thrown streaks along the rays
    streak = np.zeros((S, S))
    for a in rays:
        d = np.abs(np.angle(np.exp(1j * (TH - a))))
        streak = np.maximum(streak, smoothstep(0.22, 0.0, d) * smoothstep(0.8, r0, R) * (R > r0 * 0.8))
    m.over(lin((96, 78, 60)), streak * 0.35 * np.clip(0.6 + 0.5 * noise(rng, 3.0), 0, 1))
    m.h = h
    m.fade_out()
    return m


RECIPES = {
    "Plaster": plaster,
    "Cladding": cladding,
    "Wood": wood,
    "Metal": metal,
    "Glass": glass,
    "Pavement": pavement,
    "Soil": soil,
}


# ------------------------------------------------------------------------------------------------ sprites

def sprite(name, rng):
    m = Mark(rough=0.95)
    if name == "puff":
        a = smoothstep(0.92, 0.15, R * (1 + lobes(rng, 2, 6, 0.12))) ** 1.3
        a *= np.clip(0.7 + 0.35 * noise(rng, 10.0), 0, 1)
        shade = 1.0 - 0.15 * smoothstep(-0.8, 0.8, -Y)
        m.over(np.ones(3) * shade[..., None], a)
    elif name == "chip":
        rc, rd = polygon_radius(rng, 6, 0.55, 0.3)
        a = inside(edge_px(rc, rd))
        shade = 0.85 + 0.15 * np.clip(X * 0.7 + Y * 0.7, -1, 1)
        m.over(np.ones(3) * shade[..., None], a)
    elif name == "spark":
        a = np.exp(-(Y / 0.06) ** 2) * np.clip(1 - np.abs(X) ** 2, 0, 1)
        core = np.exp(-(Y / 0.025) ** 2) * np.clip(1 - np.abs(X) ** 3, 0, 1)
        m.over(np.ones(3), np.clip(a * 0.8 + core, 0, 1))
    m.fade_out()
    return m


# ------------------------------------------------------------------------------------------------ assembly

def normals(h, gain):
    hb = ndimage.gaussian_filter(h, 1.1)
    gy, gx = np.gradient(hb, PX)  # gy: per row (downward)
    nx = -gx * gain
    ny = gy * gain  # d/d(up) = -d/d(row)
    nz = np.ones_like(h)
    n = np.stack([nx, ny, nz], -1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


def down(a, f):
    """Box filter by an integer factor (first two axes)."""
    h, w = a.shape[:2]
    return a.reshape(h // f, f, w // f, f, *a.shape[2:]).mean(axis=(1, 3))


def dilate_rgb(rgb, alpha):
    """Fill the colour under alpha 0 with the nearest visible colour, so mips do not bleed a dark fringe."""
    solid = alpha > 0.02
    if not solid.any():
        return rgb
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    return rgb[iy, ix]


def build():
    os.makedirs(GAME_OUT, exist_ok=True)
    os.makedirs(PREVIEW, exist_ok=True)
    N = GRID * CELL
    albedo = np.zeros((N, N, 4))
    paint = np.zeros((N, N, 4))
    normal = np.zeros((N, N, 3))
    normal[..., 2] = 1.0
    depth_mr = np.zeros((N, N, 3))
    depth_mr[..., 1] = 0.9
    cells = {}
    marks = []
    index = 0
    for k, kind in enumerate(KINDS):
        cells[kind] = []
        for v in range(VARIANTS):
            rng = np.random.default_rng(1000 * (k + 1) + v)
            marks.append((index, kind, RECIPES[kind](rng)))
            cells[kind].append(index)
            index += 1
    sprites = {}
    for s, name in enumerate(SPRITES):
        sprites[name] = index
        marks.append((index, name, sprite(name, np.random.default_rng(9000 + s))))
        index += 1
    assert index <= GRID * GRID
    with_paint = {kind for _, kind, m in marks if kind in KINDS and m.paint_a.max() > 0.05}
    for i, kind, m in marks:
        col, row = i % GRID, i // GRID
        y0, x0 = row * CELL, col * CELL
        a = down(m.core_a, SS)
        rgb = down(m.core * m.core_a[..., None], SS) / np.maximum(a, 1e-6)[..., None]
        rgb = dilate_rgb(rgb, a)
        albedo[y0:y0 + CELL, x0:x0 + CELL, :3] = rgb
        albedo[y0:y0 + CELL, x0:x0 + CELL, 3] = a
        paint[y0:y0 + CELL, x0:x0 + CELL, :3] = down(m.paint_g, SS)[..., None]
        paint[y0:y0 + CELL, x0:x0 + CELL, 3] = down(m.paint_a, SS)
        n = down(normals(m.h, m.normal_gain), SS)
        normal[y0:y0 + CELL, x0:x0 + CELL] = n / np.linalg.norm(n, axis=-1, keepdims=True)
        d = np.clip(-ndimage.gaussian_filter(m.h, 1.5) / DEPTH_REF, 0.0, 1.0)
        depth_mr[y0:y0 + CELL, x0:x0 + CELL, 0] = down(d, SS)
        depth_mr[y0:y0 + CELL, x0:x0 + CELL, 1] = down(m.rough, SS)
        depth_mr[y0:y0 + CELL, x0:x0 + CELL, 2] = down(m.metal, SS)
        print(f"cell {i:2d} {kind:9s} core {a.mean():.3f} paint {m.paint_a.mean():.3f} "
              f"deepest {(-m.h).max():.2f}")

    a8 = (np.clip(albedo[..., 3], 0, 1) * 255).round().astype(np.uint8)
    Image.fromarray(np.dstack([to_srgb8(albedo[..., :3]), a8]), "RGBA").save(os.path.join(GAME_OUT, "impacts_albedo.png"))
    p = down(paint, 2)
    p8 = np.dstack([to_srgb8(p[..., :3]), (np.clip(p[..., 3], 0, 1) * 255).round().astype(np.uint8)])
    Image.fromarray(p8, "RGBA").save(os.path.join(GAME_OUT, "impacts_paint.png"))
    n8 = np.clip(np.round((normal * 0.5 + 0.5) * 255), 0, 255).astype(np.uint8)
    Image.fromarray(np.dstack([n8, np.full(n8.shape[:2], 255, np.uint8)]), "RGBA").save(
        os.path.join(GAME_OUT, "impacts_normal.png"))
    dm8 = np.clip(np.round(depth_mr * 255), 0, 255).astype(np.uint8)
    Image.fromarray(np.dstack([dm8, np.full(dm8.shape[:2], 255, np.uint8)]), "RGBA").save(
        os.path.join(GAME_OUT, "impacts_depth_mr.png"))

    lines = ["// Generated by assets/fx/impacts/_src/build_atlas.py: do not edit by hand.",
             "// Cell i of the GRID x GRID atlas is column i % grid, row i / grid (row 0 at the top).",
             "(", f"    grid: {GRID},", f"    depth_ref: {DEPTH_REF},", "    kinds: {"]
    for kind in KINDS:
        lines.append(f"        {kind}: {cells[kind]},")
    lines += ["    },",
              "    // Kinds with a paint layer (the surface bent or lifted, tinted with its colour).",
              "    paint: [" + ", ".join(k for k in KINDS if k in with_paint) + "],",
              "    sprites: (" + ", ".join(f"{k}: {v}" for k, v in sprites.items()) + "),", ")", ""]
    with open(os.path.join(GAME_OUT, "impacts_atlas.ron"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    preview(albedo, paint, normal, depth_mr, cells)


def preview(albedo, paint, normal, depth_mr, cells):
    """Each cell over its surface colour, lit from the upper left (Lambert + a little specular on metal), plus the
    paint layer tinted with the surface colour, and the raw maps side by side."""
    L = np.array([-0.45, 0.55, 0.7])
    L /= np.linalg.norm(L)
    N = GRID * CELL
    out = np.zeros((N, N, 3))
    for kind, idx in list(cells.items()) + [("Sprites", [28, 29, 30])]:
        base = lin(PREVIEW_SURFACE.get(kind, (90, 90, 96)))
        for i in idx:
            col, row = i % GRID, i // GRID
            sl = (slice(row * CELL, (row + 1) * CELL), slice(col * CELL, (col + 1) * CELL))
            n = normal[sl]
            ndl = np.clip(n @ L, 0, 1)
            shade = (0.42 + 0.75 * ndl)[..., None]
            flat = 0.42 + 0.75 * L[2]
            c = np.broadcast_to(base * flat, (CELL, CELL, 3)).copy()
            pa = paint[sl][..., 3:4]
            c = c * (1 - pa) + base * paint[sl][..., :3] * shade * pa
            ca = albedo[sl][..., 3:4]
            spec = (depth_mr[sl][..., 2:3] * np.clip(n @ np.array([0.0, 0.0, 1.0]), 0, 1)[..., None] ** 8) * 0.3
            c = c * (1 - ca) + (albedo[sl][..., :3] * shade + spec) * ca
            out[sl] = c
    Image.fromarray(to_srgb8(out)).save(os.path.join(PREVIEW, "contact_sheet.png"))
    Image.fromarray((np.clip(normal * 0.5 + 0.5, 0, 1) * 255).astype(np.uint8)).save(os.path.join(PREVIEW, "normal.png"))
    Image.fromarray((np.clip(depth_mr[..., 0], 0, 1) * 255).astype(np.uint8)).save(os.path.join(PREVIEW, "depth.png"))
    Image.fromarray((np.clip(paint[..., 3], 0, 1) * 255).astype(np.uint8)).save(os.path.join(PREVIEW, "paint_alpha.png"))


if __name__ == "__main__":
    build()
