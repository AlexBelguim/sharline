"""Small procedural decal textures for the Showhome ground kit (system Python + PIL + numpy). Re-runnable.

  python ground_textures.py
Writes kit/tex/ground/ (sRGB PNGs, painterly-stylized, no baked light, matched to the texture library palette):
  manhole.png       512 x 512  round cast-iron road cover (fills the square; the disc mesh crops it)
  gully.png         512 x 256  kerbside drain grate (bars run along V, the short side)
  inspection.png    512 x 512  square galvanised utility cover for pavements, paving-coloured infill
These are decals: each one maps 0-1 onto one face (no tiling).
"""
import math
import os

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "kit", "tex", "ground")


def to_srgb(a):
    a = np.clip(a, 0, 1)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


def lin(r, g, b):
    def f(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return np.array([f(r), f(g), f(b)])


def noise(h, w, scale, seed):
    """Smooth value noise in 0..1 (bilinear-upscaled random grid, two octaves)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    amp = 1.0
    tot = 0.0
    for o in range(3):
        gh, gw = max(2, int(h / scale) + 2), max(2, int(w / scale) + 2)
        g = rng.random((gh, gw))
        img = Image.fromarray((g * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
        out += amp * np.asarray(img, dtype=float) / 255.0
        tot += amp
        amp *= 0.5
        scale /= 2.2
    return out / tot


def save(arr_lin, name):
    os.makedirs(OUT, exist_ok=True)
    img = Image.fromarray((to_srgb(arr_lin) * 255 + 0.5).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    p = os.path.join(OUT, name)
    img.save(p)
    print("wrote", p, img.size, "mean lin", np.round(arr_lin.reshape(-1, 3).mean(0), 4))


def manhole(S=512):
    y, x = np.mgrid[0:S, 0:S].astype(float)
    cx = cy = (S - 1) / 2
    r = np.hypot(x - cx, y - cy) / (S / 2)
    ang = np.arctan2(y - cy, x - cx)
    iron = lin(58, 56, 60)
    iron_hi = lin(84, 80, 82)
    iron_lo = lin(34, 32, 36)
    col = np.zeros((S, S, 3)) + iron
    # concentric raised rings + radial ribs (raised = lighter, grooves = darker): a stylized tread pattern
    ring = (np.sin(r * 2 * math.pi * 9.0) > 0.55) & (r < 0.80) & (r > 0.16)
    rib = (np.abs(np.sin(ang * 12)) < 0.12) & (r < 0.80) & (r > 0.16)
    col[ring | rib] = iron_hi
    hub = r < 0.16
    col[hub] = iron_lo
    col[(r > 0.155) & (r < 0.175)] = iron_hi
    # two lifting slots
    for sx in (-1, 1):
        m = (np.abs(x - (cx + sx * 0.55 * S / 2)) < S * 0.035) & (np.abs(y - cy) < S * 0.012)
        col[m] = iron_lo * 0.6
    # rim (frame) and the dark gap between frame and lid
    col[(r > 0.80) & (r < 0.845)] = iron_lo * 0.55
    col[r >= 0.845] = lin(92, 88, 90)
    n = noise(S, S, 64, 3)[..., None]
    col = col * (0.85 + 0.30 * n)
    # faint warm dust in the grooves (painterly, no grime)
    col = col * (1.0 - 0.08 * (r[..., None] > 0.6))
    save(col, "manhole.png")


def gully(W=512, H=256):
    y, x = np.mgrid[0:H, 0:W].astype(float)
    frame = lin(70, 66, 68)
    bar = lin(52, 50, 54)
    slot = lin(14, 13, 15)
    col = np.zeros((H, W, 3)) + frame
    inner = (x > W * 0.06) & (x < W * 0.94) & (y > H * 0.12) & (y < H * 0.88)
    col[inner] = bar
    period = W * 0.88 / 11
    ph = (x - W * 0.06) % period
    slots = inner & (ph > period * 0.30) & (ph < period * 0.78) & (y > H * 0.18) & (y < H * 0.82)
    col[slots] = slot
    n = noise(H, W, 48, 5)[..., None]
    col = col * (0.85 + 0.3 * n)
    save(col, "gully.png")


def inspection(S=512):
    y, x = np.mgrid[0:S, 0:S].astype(float)
    steel = lin(128, 126, 124)
    steel_dk = lin(74, 72, 72)
    infill = lin(168, 156, 148)        # paving colour (palette 175 162 154, a touch darker)
    col = np.zeros((S, S, 3)) + infill
    e = np.minimum(np.minimum(x, S - 1 - x), np.minimum(y, S - 1 - y)) / S
    col[e < 0.07] = steel
    col[(e >= 0.07) & (e < 0.085)] = steel_dk
    # slab joint across the infill (the cover takes a paving infill) and two key holes
    col[(np.abs(y - S / 2) < 3) & (e >= 0.085)] = infill * 0.6
    for sx in (-1, 1):
        m = (np.abs(x - (S / 2 + sx * S * 0.3)) < 8) & (np.abs(y - S * 0.2) < 4)
        col[m] = steel_dk * 0.5
    n = noise(S, S, 80, 7)[..., None]
    col = col * (0.88 + 0.24 * n)
    save(col, "inspection.png")


if __name__ == "__main__":
    manhole()
    gully()
    inspection()
