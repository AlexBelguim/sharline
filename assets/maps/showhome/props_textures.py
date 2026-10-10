"""Prop-specific textures for the Showhome props kit (system Python + PIL + numpy). Re-runnable.

  python props_textures.py
Writes kit/tex/:
  greenhouse_twinwall.png   2048 x 1024, a 4.0 m x 2.2 m strip of frosted twin-wall polycarbonate with blurred
                            plant silhouettes behind it (seamless in U). Opaque: the greenhouse walls are solid
                            in collision, so the glazing must not look see-through.
  greenhouse_roof.png       1024 x 1024 frosted roof panel (seamless), lighter, a few leaf shadows.
  wood_boards_grey.png      wood_boards_stained.png as neutral grey, linear mean 0.70, for painted boards
                            (multiply by target_linear / 0.70).
  fabric_weave.png          1024 x 1024 neutral soft fabric weave, linear mean 0.70 (sofa / armchair / cushions).
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "textures")
OUT = os.path.join(HERE, "kit", "tex")


def to_lin(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def to_srgb(a):
    a = np.clip(a, 0, 1)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * a ** (1 / 2.4) - 0.055)


def save(arr_lin, name):
    img = Image.fromarray((to_srgb(arr_lin) * 255 + 0.5).astype(np.uint8))
    img.save(os.path.join(OUT, name))
    print("wrote", name, img.size, "mean lin", np.round(arr_lin.reshape(-1, 3).mean(0), 4))


def wrap_draw(draw_fn, W):
    for dx in (-W, 0, W):
        draw_fn(dx)


def greenhouse(seed=3):
    W, H = 2048, 1024             # 4.0 m x 2.2 m
    ppm_x, ppm_y = W / 4.0, H / 2.2
    rng = np.random.default_rng(seed)
    mask = Image.new("L", (W, H), 0)          # plant density (white = leaf)
    dark = Image.new("L", (W, H), 0)          # stems / bench (darker)
    dm, dd = ImageDraw.Draw(mask), ImageDraw.Draw(dark)

    def yz(z):                                 # metres above the panel bottom (0.35 m) -> image y
        return H - (z - 0.0) * ppm_y

    # bench line at 0.45 m above the panel bottom (0.8 m above ground), pots on it
    def bench(dx):
        dd.rectangle((0 + dx, yz(0.47), W + dx, yz(0.42)), fill=150)
        for k in range(14):
            x = (k + 0.5) * W / 14 + rng.uniform(-20, 20)
            dd.rectangle((x - 26 + dx, yz(0.62), x + 26 + dx, yz(0.47)), fill=120)
    wrap_draw(bench, W)
    # plants: clusters of leaves around stems, most below 1.5 m, a few tall vines
    plants = []
    for k in range(26):
        x = rng.uniform(0, W)
        top = rng.choice([rng.uniform(0.9, 1.35), rng.uniform(1.4, 1.95)], p=[0.65, 0.35])
        plants.append((x, top))
    for (x, top) in plants:
        def stem(dx, x=x, top=top):
            dd.line((x + dx, yz(0.6), x + dx + rng.uniform(-10, 10), yz(top)), fill=110, width=5)
        wrap_draw(stem, W)
        n = int(30 + 40 * top)
        for i in range(n):
            z = rng.uniform(0.6, top)
            spread = 30 + 70 * math.sin(min(1.0, (z - 0.6) / max(top - 0.6, 0.1)) * math.pi * 0.9)
            lx = x + rng.normal(0, spread * 0.6)
            ly = yz(z)
            rx, ry = rng.uniform(10, 26), rng.uniform(7, 16)
            val = int(rng.uniform(170, 255))

            def leaf(dx, lx=lx, ly=ly, rx=rx, ry=ry, val=val):
                dm.ellipse((lx - rx + dx, ly - ry, lx + rx + dx, ly + ry), fill=val)
            wrap_draw(leaf, W)
        # a few tomatoes / flowers as dots on the tall ones
    blur = ImageFilter.GaussianBlur(9)
    m = np.asarray(mask.filter(blur), np.float32) / 255
    d = np.asarray(dark.filter(ImageFilter.GaussianBlur(6)), np.float32) / 255
    frost = np.array([0.6724, 0.7605, 0.7305]) * 0.97
    leaf_c = np.array([0.20, 0.30, 0.10])
    leaf_hi = np.array([0.32, 0.42, 0.14])
    stem_c = np.array([0.24, 0.24, 0.20])
    yy = np.linspace(1, 0, H)[:, None]                     # 1 at the top
    # frosted diffusion: plants pale toward the frost colour; top of the panel brighter (sky light)
    noise = rng.normal(0, 1, (H // 16, W // 16)).astype(np.float32)
    noise = np.asarray(Image.fromarray(noise).resize((W, H), Image.BICUBIC))
    a = np.clip(m * 0.62, 0, 0.62)[..., None]
    col = frost[None, None, :] * (0.94 + 0.08 * yy[..., None]) * (1 + 0.025 * noise[..., None])
    lc = leaf_c + (leaf_hi - leaf_c) * np.clip(noise[..., None] * 0.5 + 0.5, 0, 1)
    col = col * (1 - a) + lc * a
    col = col * (1 - 0.35 * d[..., None]) + stem_c * 0.35 * d[..., None] * 0.0
    # vertical twin-wall flutes every 3 cm (faint), slightly darker lines
    xs = np.arange(W)
    flute = 1 - 0.035 * (np.cos(2 * np.pi * xs / (0.03 * ppm_x)) > 0.92)
    col = col * flute[None, :, None]
    save(col.astype(np.float32), "greenhouse_twinwall.png")


def greenhouse_roof(seed=5):
    S = 1024
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 1, (S // 32, S // 32)).astype(np.float32)
    big = np.asarray(Image.fromarray(noise).resize((S, S), Image.BICUBIC))
    big = np.roll(big, 0, 0)
    # make seamless by blending with a shifted copy
    sh = np.roll(np.roll(big, S // 2, 0), S // 2, 1)
    yy, xx = np.mgrid[0:S, 0:S] / S
    w = (np.sin(np.pi * xx) * np.sin(np.pi * yy))
    n = big * w + sh * (1 - w)
    frost = np.array([0.6724, 0.7605, 0.7305])
    col = frost[None, None, :] * (1.02 + 0.03 * n[..., None])
    xs = np.arange(S)
    flute = 1 - 0.03 * (np.cos(2 * np.pi * xs / (S / 50)) > 0.9)
    col = col * flute[None, :, None]
    save(col.astype(np.float32), "greenhouse_roof.png")


def boards_grey():
    a = np.asarray(Image.open(os.path.join(TEX, "wood_boards_stained.png")).convert("RGB"), np.float32) / 255
    lum = to_lin(a) @ np.array([0.2126, 0.7152, 0.0722])
    # lift the dark stain to a paintable grey, keep the board gaps darker (compress contrast a little)
    lum = lum / lum.mean()
    lum = 1 + (lum - 1) * 0.55
    g = np.clip(lum * 0.70, 0, 1)
    save(np.repeat(g[..., None], 3, axis=2).astype(np.float32), "wood_boards_grey.png")


def fabric(seed=9):
    S = 1024
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    weave = 0.5 + 0.5 * np.sin(2 * np.pi * xx / 8) * np.sin(2 * np.pi * yy / 8)
    n = rng.normal(0, 1, (S // 64, S // 64)).astype(np.float32)
    n = np.asarray(Image.fromarray(n).resize((S, S), Image.BICUBIC))
    n2 = rng.normal(0, 1, (S, S)).astype(np.float32)
    n2 = (n2 + np.roll(n2, 1, 0) + np.roll(n2, 1, 1) + np.roll(n2, -1, 0) + np.roll(n2, -1, 1)) / 5
    # seamless: weave period divides S; blend the low-freq noise with its rolled copy
    sh = np.roll(np.roll(n, S // 2, 0), S // 2, 1)
    w = np.sin(np.pi * xx / S) * np.sin(np.pi * yy / S)
    n = n * w + sh * (1 - w)
    g = 0.70 * (1 + 0.05 * (weave - 0.5) + 0.035 * n + 0.03 * n2)
    g = g / g.mean() * 0.70
    save(np.repeat(g[..., None], 3, axis=2).astype(np.float32), "fabric_weave.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    greenhouse()
    greenhouse_roof()
    boards_grey()
    fabric()
