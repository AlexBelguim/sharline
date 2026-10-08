"""Shimmer check: how much a region of the image changes when the camera moves 2 cm (shots.sh views `gravel` vs
`gravelmv`, `street` vs `streetmv`). Aliasing in the parallax (Bevy samples the depth map at mip 0 only) shows up
as a much larger change in the far ground than the same move gives without parallax.

  python shimmer.py <view> <moved view> <suffix> [<suffix> ...] [--rows y0,y1]
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
COLS = (200, 1400)
SHOTS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "game", "target", "shots", "depth"))


def load(name):
    return np.asarray(Image.open(os.path.join(SHOTS, name + ".png")).convert("L"), np.float32)


def main():
    args = sys.argv[1:]
    rows = (150, 450)
    if "--rows" in args:
        i = args.index("--rows")
        rows = tuple(int(v) for v in args[i + 1].split(","))
        del args[i:i + 2]
    view, moved, suffixes = args[0], args[1], args[2:]
    for s in suffixes:
        a, b = load(f"{view}_{s}"), load(f"{moved}_{s}")
        band = slice(*rows), slice(*COLS)
        d = np.abs(a[band] - b[band])
        print(f"{view} {s:10s} rows {rows}: mean |diff| {d.mean():.2f}  p99 {np.percentile(d, 99):.1f}  "
              f"(image std {a[band].std():.2f})")


if __name__ == "__main__":
    main()
