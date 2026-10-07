"""Generated UI shapes and post-processing for the hub screens (spec: the hub UI spec's icons section).

Run after ui_raster.cjs:  python3 -I game/tools/ui_shapes.py
Writes white-on-transparent PNGs to game/assets/ui/shapes/ (tint them in Bevy with ImageNode.color),
cuts the dark #0b0e13 detail out of a few icons, and pre-masks the agent portraits into hexagons.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ICONS = os.path.join(ROOT, "game", "assets", "ui", "icons")
SHAPES = os.path.join(ROOT, "game", "assets", "ui", "shapes")
IMG = os.path.join(ROOT, "game", "assets", "ui", "img")
WHITE = (255, 255, 255, 255)


def cutout(name):
    """Dark detail (#0b0e13 in the SVG) becomes transparent: alpha *= luminance, colour = white."""
    p = os.path.join(ICONS, name + ".png")
    im = Image.open(p).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
            px[x, y] = (255, 255, 255, int(round(a * lum)))
    im.save(p)


def supersample(w, h, draw_fn, scale=4):
    big = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(big), scale)
    return big.resize((w, h), Image.LANCZOS)


def pip(w, h, body_w, skew_deg, name):
    """A tier pip: a body_w x h parallelogram leaning like '/' (2x size).

    CSS skewX(a) moves a point by tan(a) * y (y down from the centre), so skewX(-14deg) shifts the top to
    the right: the top edge moves by -tan(a) * h / 2.
    """
    shift = -math.tan(math.radians(skew_deg)) * h / 2

    def d(dr, s):
        cx = w / 2
        pts = [(cx - body_w / 2 + shift, 0), (cx + body_w / 2 + shift, 0), (cx + body_w / 2 - shift, h), (cx - body_w / 2 - shift, h)]
        dr.polygon([(x * s, y * s) for x, y in pts], fill=WHITE)

    supersample(w, h, d).save(os.path.join(SHAPES, name))


def dash_9slice():
    """24x24, 2 px border, dashes 8 on / 6 off (2x): slice with a 2 px border and tile the sides."""
    im = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
    px = im.load()
    for i in range(24):
        on = (i % 14) < 8
        for t in range(2):
            if on:
                px[i, t] = WHITE
                px[i, 23 - t] = WHITE
                px[t, i] = WHITE
                px[23 - t, i] = WHITE
    im.save(os.path.join(SHAPES, "dash_9slice.png"))


def wheel(name, sectors):
    """32x32 (16 px at 2x): ring sectors 50 deg wide with 10 deg gaps, radii 4.5..7.5 (1x). Sector 0 is up."""
    def d(dr, s):
        c = 16 * s
        ro, ri = 7.5 * 2 * s, 4.5 * 2 * s
        for k in sectors:
            mid = k * 60.0
            a0, a1 = mid - 25.0, mid + 25.0
            pts = []
            for i in range(21):
                a = math.radians(a0 + (a1 - a0) * i / 20)
                pts.append((c + ro * math.sin(a), c - ro * math.cos(a)))
            for i in range(21):
                a = math.radians(a1 - (a1 - a0) * i / 20)
                pts.append((c + ri * math.sin(a), c - ri * math.cos(a)))
            dr.polygon(pts, fill=WHITE)

    supersample(32, 32, d).save(os.path.join(SHAPES, name))


def hex_points(w, h):
    return [(0.5 * w, 0), (w, 0.25 * h), (w, 0.75 * h), (0.5 * w, h), (0, 0.75 * h), (0, 0.25 * h)]


def hex_badge():
    supersample(60, 60, lambda dr, s: dr.polygon([(x * s, y * s) for x, y in hex_points(60, 60)], fill=WHITE)).save(
        os.path.join(SHAPES, "hex_badge.png"))


def hex_portrait(src, dst, size=128):
    im = Image.open(os.path.join(IMG, src)).convert("RGBA").resize((size, size), Image.LANCZOS)
    mask = supersample(size, size, lambda dr, s: dr.polygon([(x * s, y * s) for x, y in hex_points(size, size)], fill=WHITE))
    im.putalpha(mask.split()[3])
    im.save(os.path.join(SHAPES, dst))


def key_updown():
    """24x32 (2x): the browser's thin "↑↓" for the [up/down] key cap, drawn at 12x16 centred in the 28x22 cap.

    Measured on mockup 04: 1 px shafts 12 px tall (cap rows 7-18) at cap columns 10 and 17, with small
    5 px wide heads at the top of the up arrow and the bottom of the down arrow.
    """
    def d(dr, s):
        def arrow(cx, up):
            top, bottom = 8, 32
            dr.line([(cx * s, top * s), (cx * s, bottom * s)], fill=WHITE, width=int(2 * s))
            tip, back = (top, top + 7) if up else (bottom, bottom - 7)
            dr.polygon([((cx - 5) * s, back * s), (cx * s, tip * s), ((cx + 5) * s, back * s)], fill=WHITE)
        arrow(5, True)
        arrow(19, False)

    supersample(24, 32, d).save(os.path.join(SHAPES, "key_updown.png"))


def main():
    os.makedirs(SHAPES, exist_ok=True)
    if not os.path.isdir(ICONS):
        sys.exit("run game/tools/ui_raster.cjs first")
    for name in ["bandage", "medkit", "food", "mako", "mag"]:
        cutout(name)
    pip(18, 20, 12, -14, "pip.png")
    pip(16, 20, 10, -14, "pip_ammo.png")
    dash_9slice()
    wheel("wheel_ring.png", range(6))
    wheel("wheel_sector.png", [0])
    hex_badge()
    hex_portrait("kestrel_portrait.jpg", "kestrel_hex.png")
    hex_portrait("solace_portrait.jpg", "solace_hex.png")
    key_updown()
    print("shapes ->", SHAPES)


if __name__ == "__main__":
    main()
