"""Build a perfectly periodic stylised 2x2 carbon twill (raw/carbon_weave_proc.png).

Why procedural: the Krea2 weave generations (raw/carbon_weave_s1..s4.png) looked good but drift / break
their pattern, so any seam fix shows faults on such a strictly regular weave. Here the tow layout is
exact (period divides 1024) and the fibre detail inside each tow comes from the AI-made brushed_metal.png
streaks (horizontal for weft, rotated 90 deg for warp), so it still has the painted texture feel.
Run process_textures.py afterwards (seam="none") for the final normalisation.
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
N = 1024
C = 32          # cell size in px -> 32 tows across the texture, twill period 4 cells = 128 px


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def main():
    streak_src = os.path.join(os.path.dirname(HERE), "brushed_metal.png")
    st = np.asarray(Image.open(streak_src).convert("L"), dtype=np.float32) / 255.0
    st = (st - st.mean()) / st.std()          # zero-mean unit streak detail, horizontal
    st_h, st_v = st, st.T                     # weft (horizontal) / warp (vertical) fibres

    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    q = (xx // C).astype(int)                 # column of cells
    r = (yy // C).astype(int)                 # row of cells
    u = (xx % C) / C                          # 0..1 inside the cell across x
    v = (yy % C) / C                          # 0..1 inside the cell across y
    warp_top = ((r + q) % 4) < 2              # 2-over-2-under, shifted one cell per column -> twill

    # position along the visible 2-cell float (0..2), used to darken the ends where the tow dives under
    s_warp = ((r + q) % 4).astype(np.float32) + v          # 0..2 when warp on top
    s_weft = ((r + q) % 4 - 2).astype(np.float32) + u      # 0..2 when weft on top (shift by 2)

    def tow(across, along):
        rounded = 0.62 + 0.38 * np.maximum(np.sin(np.pi * np.clip(across, 0, 1)), 0) ** 0.6   # rounded bundle
        gap = smoothstep(0.0, 0.10, across) * smoothstep(1.0, 0.90, across)   # thin dark gap lines
        ends = 0.80 + 0.20 * np.maximum(np.sin(np.pi * np.clip(along / 2.0, 0, 1)), 0) ** 0.5
        return rounded * (0.55 + 0.45 * gap) * ends

    warp = tow(u, s_warp) * 1.00 + 0.05 * st_v       # warp slightly brighter (anisotropic sheen)
    weft = tow(v, s_weft) * 0.80 + 0.05 * st_h
    img = np.where(warp_top, warp, weft)

    # soften a touch so it reads painted rather than CG-sharp (periodic blur via FFT)
    f = np.fft.fftfreq(N)
    g = np.exp(-2 * (np.pi * 0.8) ** 2 * (f[:, None] ** 2 + f[None, :] ** 2))
    img = np.real(np.fft.ifft2(np.fft.fft2(img) * g))

    img = (img - img.min()) / (img.max() - img.min())
    out = os.path.join(HERE, "raw", "carbon_weave_proc.png")
    Image.fromarray((img * 255 + 0.5).astype(np.uint8)).save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
