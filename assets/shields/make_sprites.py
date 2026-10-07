"""Procedural VFX sprites for the halo shield (system Python + PIL + numpy, no Blender needed).

  python "F:/git/val etf/assets/shields/make_sprites.py"

Writes 512x512 RGBA PNGs to assets/shields/sprites/. All sprites are white/greyscale: RGB carries the
intensity and alpha the coverage, so the engine tints them with the tier colour (multiply) and can use them
either alpha-blended or additive (RGB * A).
  hex_hit_flash.png  impact flash: hot core, crisp hex ring, fading honeycomb, 6 corner rays
  crack_overlay.png  impact crack: jagged branching cracks over broken honeycomb cell edges
  shard_sprite.png   one faceted hex-glass shard with a bright rim (for 2D/billboard particles)
  crack_tile.png     seamless shattered-glass map (opaque greyscale RGB), the emissive map of the
                     M_HALO_Glass_Broken_T* materials (arc glass UVs run as straight strips along each arc)
Geometry is drawn at 4x and downsampled (LANCZOS) for crisp anti-aliased edges.
"""
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprites")
N = 512
SS = 4
S = N * SS
C = S / 2


def hexagon(cx, cy, r, rot=0.0):
    return [(cx + r * math.cos(math.radians(60 * i + rot)), cy + r * math.sin(math.radians(60 * i + rot)))
            for i in range(6)]


def layer():
    return Image.new("L", (S, S), 0)


def radial(power=1.0):
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    r = np.sqrt((x - C) ** 2 + (y - C) ** 2) / (S / 2)
    return r


def honeycomb(draw, cell, width, clip_r, center=(C, C), keep=None, rot=30.0):
    """Draw honeycomb cell edges inside radius clip_r. keep(cx, cy) -> bool filters cells."""
    w = cell * math.sqrt(3)
    h = cell * 1.5
    rows = int(S / h) + 3
    cols = int(S / w) + 3
    for j in range(-rows // 2, rows // 2 + 1):
        for i in range(-cols // 2, cols // 2 + 1):
            cx = center[0] + i * w + (w / 2 if j % 2 else 0)
            cy = center[1] + j * h
            if math.hypot(cx - center[0], cy - center[1]) > clip_r:
                continue
            if keep and not keep(cx, cy):
                continue
            pts = hexagon(cx, cy, cell, rot)
            draw.line(pts + [pts[0]], fill=255, width=width, joint="curve")


def finish(L_rgb, L_a, name):
    rgb = L_rgb.resize((N, N), Image.LANCZOS)
    a = L_a.resize((N, N), Image.LANCZOS)
    img = Image.merge("RGBA", (rgb, rgb, rgb, a))
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    img.save(p)
    print("wrote", p)
    return p


def to_img(arr):
    return Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), "L")


# --------------------------------------------------------------------------------------------- hit flash
def hit_flash():
    r = radial()
    core = np.exp(-(r / 0.16) ** 2) * 1.0 + np.exp(-(r / 0.42) ** 2) * 0.35
    # crisp hex ring
    ring = layer()
    d = ImageDraw.Draw(ring)
    pts = hexagon(C, C, S * 0.30, 30)
    d.line(pts + [pts[0]], fill=255, width=int(S * 0.016), joint="curve")
    pts2 = hexagon(C, C, S * 0.235, 30)
    d.line(pts2 + [pts2[0]], fill=150, width=int(S * 0.005), joint="curve")
    # 6 rays from the ring corners
    rays = layer()
    dr = ImageDraw.Draw(rays)
    for i in range(6):
        a = math.radians(60 * i + 30)
        r0, r1, wdt = S * 0.31, S * 0.47, S * 0.016
        px, py = -math.sin(a), math.cos(a)
        tip = (C + r1 * math.cos(a), C + r1 * math.sin(a))
        b0 = (C + r0 * math.cos(a) + px * wdt, C + r0 * math.sin(a) + py * wdt)
        b1 = (C + r0 * math.cos(a) - px * wdt, C + r0 * math.sin(a) - py * wdt)
        dr.polygon([b0, tip, b1], fill=200)
    # honeycomb fading outward
    hc = layer()
    honeycomb(ImageDraw.Draw(hc), S * 0.052, int(S * 0.0035), S * 0.29)
    hc_a = np.asarray(hc, np.float32) / 255.0 * np.clip(1.0 - (r / 0.58) ** 2, 0, 1) * 0.55
    ring_a = np.asarray(ring, np.float32) / 255.0
    rays_a = np.asarray(rays, np.float32) / 255.0
    a = np.clip(core + ring_a + rays_a * 0.85 + hc_a, 0, 1)
    rgb = np.clip(0.75 + 0.25 * core + ring_a, 0, 1) * np.ones_like(a)
    # soft bloom of the crisp shapes
    glow = to_img(np.clip(ring_a + rays_a, 0, 1)).filter(ImageFilter.GaussianBlur(S * 0.012))
    a = np.clip(a + np.asarray(glow, np.float32) / 255.0 * 0.5, 0, 1)
    return finish(to_img(rgb), to_img(a), "hex_hit_flash.png")


# --------------------------------------------------------------------------------------------- crack overlay
def jagged(rnd, p0, ang, length, step, wobble):
    pts = [p0]
    x, y = p0
    travelled = 0.0
    while travelled < length:
        ang += rnd.uniform(-wobble, wobble)
        s = step * rnd.uniform(0.6, 1.3)
        x += math.cos(ang) * s
        y += math.sin(ang) * s
        travelled += s
        pts.append((x, y))
    return pts, ang


def crack_overlay(seed=4):
    rnd = random.Random(seed)
    lines = layer()
    d = ImageDraw.Draw(lines)
    hit = (C + S * 0.04, C - S * 0.03)
    # broken honeycomb near the impact: only cells close to the hit, with random cells missing
    cells = layer()

    def keep(cx, cy):
        dist = math.hypot(cx - hit[0], cy - hit[1]) / S
        return dist < 0.30 and rnd.random() < (1.0 - dist / 0.33)
    honeycomb(ImageDraw.Draw(cells), S * 0.045, int(S * 0.0045), S * 0.5, center=hit, keep=keep)
    # main cracks + branches
    n_main = 7
    for i in range(n_main):
        ang = 2 * math.pi * i / n_main + rnd.uniform(-0.25, 0.25)
        length = S * rnd.uniform(0.30, 0.46)
        pts, end_ang = jagged(rnd, hit, ang, length, S * 0.07, 0.22)
        for k in range(len(pts) - 1):
            t = k / max(1, len(pts) - 1)
            wdt = int(S * (0.011 * (1 - t) + 0.003))
            d.line([pts[k], pts[k + 1]], fill=255, width=wdt, joint="curve")
        # branches
        for _ in range(rnd.randint(1, 3)):
            k = rnd.randint(2, max(2, len(pts) - 3))
            bang = end_ang + rnd.choice((-1, 1)) * rnd.uniform(0.5, 1.1)
            bpts, _ = jagged(rnd, pts[k], bang, S * rnd.uniform(0.06, 0.16), S * 0.05, 0.25)
            d.line(bpts, fill=220, width=int(S * 0.0045), joint="curve")
    # impact pit: small crushed hex
    pts = hexagon(hit[0], hit[1], S * 0.03, 12)
    d.polygon(pts, fill=255)
    la = np.asarray(lines, np.float32) / 255.0
    ca = np.asarray(cells, np.float32) / 255.0 * 0.45
    a = np.clip(la + ca, 0, 1)
    glow = to_img(la).filter(ImageFilter.GaussianBlur(S * 0.006))
    a = np.clip(a + np.asarray(glow, np.float32) / 255.0 * 0.35, 0, 1)
    rgb = np.clip(0.8 + 0.2 * la, 0, 1)
    return finish(to_img(rgb), to_img(a), "crack_overlay.png")


# --------------------------------------------------------------------------------------------- shard
def shard_sprite():
    R = S * 0.36
    hexp = hexagon(C, C, R, 0)
    # snap one corner off and chip the opposite edge -> a broken hex shard
    poly = [hexp[0], (C + R * 0.62, C + R * 0.55), (C + R * 0.18, C + R * 0.80), hexp[2], hexp[3],
            (C - R * 0.62, C - R * 0.62), (C - R * 0.15, C - R * 0.74), hexp[5]]
    centre = (C - R * 0.08, C + R * 0.02)
    fill = layer()
    df = ImageDraw.Draw(fill)
    # facets: fan from an off-centre apex, alternating greys (faceted glass)
    shades = [235, 175, 210, 150, 195, 165, 225, 185]
    for i in range(len(poly)):
        df.polygon([centre, poly[i], poly[(i + 1) % len(poly)]], fill=shades[i % len(shades)])
    mask = layer()
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    rim = layer()
    ImageDraw.Draw(rim).line(poly + [poly[0]], fill=255, width=int(S * 0.018), joint="curve")
    # inner bevel line
    inner = [(C + (x - C) * 0.80, C + (y - C) * 0.80) for x, y in poly]
    ImageDraw.Draw(rim).line(inner + [inner[0]], fill=130, width=int(S * 0.006), joint="curve")
    f = np.asarray(fill, np.float32) / 255.0
    m = np.asarray(mask, np.float32) / 255.0
    rm = np.asarray(rim, np.float32) / 255.0
    rgb = np.clip(f * 0.85 + rm, 0, 1)
    a = np.clip(m * 0.82 + rm, 0, 1)
    glow = to_img(m).filter(ImageFilter.GaussianBlur(S * 0.02))
    a = np.maximum(a, np.asarray(glow, np.float32) / 255.0 * 0.35)
    rgb = np.where(m > 0.01, rgb, 1.0)
    return finish(to_img(rgb), to_img(a), "shard_sprite.png")


# --------------------------------------------------------------------------------------------- crack tile
def crack_tile(seed=11):
    """Seamless shattered-glass map for M_HALO_Glass_Broken_T* (emissive texture, opaque greyscale RGB).
    Background 118/255 (= 0.18 linear: the dim broken glow), crack lines white.  Toroidal Voronoi cell edges
    (big cells + a finer secondary network) give crisp, straight-ish fracture lines that tile in U and V."""
    rnd = random.Random(seed)
    n = N * 2                                     # 2x supersampling
    y, x = np.mgrid[0:n, 0:n].astype(np.float32) / n

    def tdist(a, b):
        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        return math.hypot(min(dx, 1 - dx), min(dy, 1 - dy))

    def edges(npts, width):
        pts = []
        min_d = 0.55 / math.sqrt(npts)            # spaced seeds: no near-degenerate (smeared) edges
        while len(pts) < npts:
            p = (rnd.random(), rnd.random())
            if all(tdist(p, q) > min_d for q in pts):
                pts.append(p)
        d1 = np.full((n, n), 9.0, np.float32)
        d2 = np.full((n, n), 9.0, np.float32)
        for px, py in pts:
            dx = np.abs(x - px)
            dy = np.abs(y - py)
            dx = np.minimum(dx, 1.0 - dx)
            dy = np.minimum(dy, 1.0 - dy)
            d = np.sqrt(dx * dx + dy * dy)
            closer = d < d1
            d2 = np.where(closer, d1, np.minimum(d2, d))
            d1 = np.where(closer, d, d1)
        g = d2 - d1                               # 0 on a cell edge
        return np.clip(1.0 - g / width, 0.0, 1.0) ** 1.5
    big = edges(6, 0.0105)
    fine = edges(14, 0.0045) * 0.6
    crack = np.clip(np.maximum(big, fine), 0, 1)
    bg = 118.0 / 255.0
    v = bg + (1.0 - bg) * crack
    img = to_img(v).resize((N, N), Image.LANCZOS).convert("RGB")
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "crack_tile.png")
    img.save(p)
    print("wrote", p)
    return p


def preview(paths):
    """Contact sheet on dark + tinted backgrounds (sprites/_preview.png) to check the alpha."""
    tiles = []
    tints = [(0.85, 0.88, 0.92), (0.10, 0.45, 1.0), (0.55, 0.15, 1.0), (1.0, 0.62, 0.08)]
    for p, tint in zip(paths, tints[1:]):
        im = Image.open(p).convert("RGBA")
        arr = np.asarray(im, np.float32) / 255.0
        bg = np.zeros((N, N, 3), np.float32) + np.array([0.03, 0.035, 0.045])
        col = arr[..., :3] * np.array(tint)
        out = bg * (1 - arr[..., 3:4]) + col * arr[..., 3:4]
        tiles.append(Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)))
        chk = np.indices((N, N)).sum(0) // 32 % 2
        bg2 = np.where(chk[..., None] == 0, 0.6, 0.75) * np.ones((N, N, 3))
        out2 = bg2 * (1 - arr[..., 3:4]) + arr[..., :3] * arr[..., 3:4]
        tiles.append(Image.fromarray((np.clip(out2, 0, 1) * 255).astype(np.uint8)))
    sheet = Image.new("RGB", (N * 2, N * len(paths)))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 2) * N, (i // 2) * N))
    sheet.save(os.path.join(OUT, "_preview.png"))


if __name__ == "__main__":
    ps = [hit_flash(), crack_overlay(), shard_sprite()]
    preview(ps)
    crack_tile()
