"""make_projector_reticle.py - the optic_projector hologram reticle, made procedurally with PIL.

  python "F:/git/val etf/assets/weapons/attachments/optics/make_projector_reticle.py" --out <png> [--json <layout.json>]

512 x 512 RGBA, WHITE on transparent (RGB is 255 everywhere, only alpha carries the shapes), so the engine tints it
with the material's base / emissive factor (ice by default). Drawn at 4x and downsampled (LANCZOS) for clean
anti-aliased edges. Layout (texels of the 512 texture; 1 texel is about 1 px at 1080p when the quad is placed as
build_optics.py places it):
  - four rounded corner brackets of a 4:3 frame (the target area), 3.5 texel lines;
  - short inward ticks at the middle of each frame side (subtle);
  - a centre dot (~7 texels) inside a faint thin ring with four gaps;
  - three subtle range (holdover) ticks under the dot, each shorter and fainter than the one above;
  - a soft glow round everything (hologram bloom, low alpha).
The layout (frame box in texels) is written to --json so the build can size the quad on screen.
"""
import argparse
import json
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SIZE = 512
SS = 4                                   # supersampling factor
FRAME_W, FRAME_H = 440, 330              # frame box (outer bracket corners), texels, 4:3
LINE = 3.5                               # bracket line width
ARM = 62                                 # bracket arm length along each side (from the corner)
RAD = 20                                 # bracket corner radius
TICK = (10, 2.4, 0.70)                   # mid-side ticks: length, width, alpha
DOT_R = 3.4                              # centre dot radius
RING = (15.0, 1.6, 0.45, 26.0)           # faint ring round the dot: radius, width, alpha, gap angle (deg) at N/E/S/W
RANGE = [(40, 13, 2.4, 0.80), (64, 10, 2.2, 0.62), (88, 7, 2.0, 0.45)]   # (y below centre, half length, width, a)
GLOW = (5.0, 0.32)                       # glow blur radius (texels), strength


def _s(v):
    return v * SS


def draw_layer(size):
    """Alpha layer (L mode) with every shape, at the supersampled size."""
    a = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(a)
    c = size / 2
    hw, hh = _s(FRAME_W / 2), _s(FRAME_H / 2)
    lw, r, arm = _s(LINE), _s(RAD), _s(ARM)
    # corner brackets: an arc + two straight arms per corner
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = c + sx * (hw - r), c + sy * (hh - r)        # arc centre
            # arc (stroke) between the two arms
            a0 = {(1, -1): 270, (-1, -1): 180, (-1, 1): 90, (1, 1): 0}[(sx, sy)]
            bb = [cx - r, cy - r, cx + r, cy + r]       # PIL strokes inward from the bbox
            d.arc(bb, a0, a0 + 90, fill=255, width=int(round(lw)))
            # horizontal arm (along the top / bottom edge) and vertical arm (along the side)
            yh = c + sy * (hh - lw / 2)
            x0, x1 = sorted((cx, c + sx * (hw - arm)))
            d.rectangle([x0, yh - lw / 2, x1, yh + lw / 2], fill=255)
            xv = c + sx * (hw - lw / 2)
            y0, y1 = sorted((cy, c + sy * (hh - arm)))
            d.rectangle([xv - lw / 2, y0, xv + lw / 2, y1], fill=255)
    # mid-side ticks (pointing inward from the frame line position)
    tl, tw, ta = _s(TICK[0]), _s(TICK[1]), int(255 * TICK[2])
    for sx in (-1, 1):
        x_out = c + sx * (hw - lw / 2)
        x0, x1 = sorted((x_out, x_out - sx * tl))
        d.rectangle([x0, c - tw / 2, x1, c + tw / 2], fill=ta)
    for sy in (-1, 1):
        y_out = c + sy * (hh - lw / 2)
        y0, y1 = sorted((y_out, y_out - sy * tl))
        d.rectangle([c - tw / 2, y0, c + tw / 2, y1], fill=ta)
    # faint ring with four gaps round the dot
    rr, rw, ra, gap = _s(RING[0]), _s(RING[1]), int(255 * RING[2]), RING[3]
    for k in range(4):
        start = k * 90 + gap / 2
        d.arc([c - rr, c - rr, c + rr, c + rr], start - 45, start - 45 + 90 - gap, fill=ra, width=int(round(rw)))
    # centre dot
    dr = _s(DOT_R)
    d.ellipse([c - dr, c - dr, c + dr, c + dr], fill=255)
    # range ticks under the dot (image y grows downward)
    for (yb, hl, w, al) in RANGE:
        y = c + _s(yb)
        d.rectangle([c - _s(hl), y - _s(w) / 2, c + _s(hl), y + _s(w) / 2], fill=int(255 * al))
    return a


def make(out, layout_json=None):
    big = draw_layer(SIZE * SS)
    core = big.resize((SIZE, SIZE), Image.LANCZOS)
    glow = core.filter(ImageFilter.GaussianBlur(GLOW[0])).point(lambda v: int(v * GLOW[1]))
    alpha = ImageChops.lighter(core, glow)
    rgba = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 0))
    rgba.putalpha(alpha)
    rgba.save(out)
    layout = {"size": SIZE, "frame_px": [FRAME_W, FRAME_H], "line_px": LINE, "dot_r_px": DOT_R,
              "range_ticks_px_below_centre": [r[0] for r in RANGE], "colour": "white on transparent (tint in engine)"}
    if layout_json:
        with open(layout_json, "w") as f:
            json.dump(layout, f, indent=1)
    print("reticle", out, json.dumps(layout))
    return layout


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    make(a.out, a.json)
