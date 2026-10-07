"""Turn the raw Krea2 generations in _src/raw/ into the final seamless, low-contrast detail textures in
art/textures/ (1024x1024 sRGB PNG), meant to be MULTIPLIED over flat colours (bc.material tex=..., tex_mix).

Per texture (see CONFIG):
  seam    "mirror": 2x2 mirror-quilt + downscale (identical to `comfy_gen.py --tileable`)
          "cut"   : image-quilting style minimum-error boundary cut (crisp regular weaves)
          "xfade_ymirror": X cross-fade + Y mirror of the top half (vertical hair strands)
          "none"  : source already periodic (carbon_weave: procedural twill from make_carbon.py)
          "xfade" : variance-preserving offset cross-fade (separable, X then Y) — seamless without the
                    kaleidoscope symmetry the mirror quilt shows on directional / painterly textures.
  flatten removes low-frequency light falloff / blotches (periodic FFT gaussian high-pass, 0..1).
  mean/std target luminance (sRGB 0-1) — mid-to-light grey, low contrast.
  Output is neutral grey (luminance only); tint: optional RGB multiplier (skin).

Usage: python process_textures.py [name ...]      (no names = all)
Also writes previews to _src/preview/ (2x2 wrap test + multiply-over-colour swatch) and a contact sheet.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.dirname(HERE)
PREV = os.path.join(HERE, "preview")
SIZE = 1024

CONFIG = {
    "worn_paint":      dict(src="worn_paint_s1.png", seam="xfade", band=0.22, flatten=0.5, sigma=90,
                            mean=0.68, std=0.055),
    "brushed_metal":   dict(src="brushed_metal_s1.png", seam="xfade", band=0.22, flatten=1.0, sigma=30,
                            mean=0.68, std=0.045),
    "polymer_stipple": dict(src="polymer_stipple_s1.png", seam="xfade", band=0.2, flatten=0.9, sigma=40,
                            mean=0.66, std=0.06),
    "fabric_ripstop":  dict(src="fabric_ripstop_s1.png", seam="xfade", band=0.12, search=24, flatten=0.9,
                            sigma=40, mean=0.66, std=0.06, grid=dict(period=128, gap=5, width=1.0, amp=1.0)),
    "fabric_soft":     dict(src="fabric_soft_s1.png", seam="xfade", band=0.2, search=16, flatten=0.9, sigma=40,
                            mean=0.67, std=0.045),
    "leather_soft":    dict(src="leather_soft_s1.png", seam="xfade", band=0.22, flatten=0.8, sigma=60,
                            mean=0.67, std=0.05),
    "carbon_weave":    dict(src="carbon_weave_proc.png", seam="none", flatten=0.0,  # see make_carbon.py
                            mean=0.65, std=0.06, clip=3.5),
    "skin_soft":       dict(src="skin_soft_s2.png", seam="xfade", band=0.3, flatten=0.2, sigma=200,
                            mean=0.72, std=0.025, soften=2, tint=(1.05, 0.99, 0.93)),
    "hair_strands":    dict(src="hair_strands_s2.png", seam="xfade", band=(0.2, 0.48), search=16, flatten=0.6, sigma=80,
                            mean=0.66, std=0.07),
}


# ----------------------------------------------------------------------------------------- helpers
def load(path):
    im = Image.open(path).convert("RGB")
    if im.size != (SIZE, SIZE):
        im = im.resize((SIZE, SIZE), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0


def save(arr, path):
    Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path, optimize=True)


def mirror_quilt(a):
    im = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8))
    w, h = im.size
    q = Image.new("RGB", (w * 2, h * 2))
    q.paste(im, (0, 0))
    q.paste(ImageOps.mirror(im), (w, 0))
    q.paste(ImageOps.flip(im), (0, h))
    q.paste(ImageOps.flip(ImageOps.mirror(im)), (w, h))
    return np.asarray(q.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255.0


def _ramp(n, band):
    """1 in the middle, smoothstep down to 0 at both ends over `band` pixels."""
    x = np.arange(n, dtype=np.float32)
    d = np.minimum(x + 0.5, n - x - 0.5) / band
    d = np.clip(d, 0, 1)
    return d * d * (3 - 2 * d)


def reflect_blur(y, sigma):
    """Gaussian blur of a NON-periodic 2D array (reflect padding, FFT)."""
    pad = int(3 * sigma) + 1
    pad = min(pad, y.shape[0] - 1, y.shape[1] - 1)
    yp = np.pad(y, pad, mode="reflect")
    return fft_blur(yp, sigma)[pad:-pad, pad:-pad]


def _best_shift(a, m, axis, search):
    """Shift near n/2 whose rolled copy best matches `a` (fine detail) inside the blend bands, so
    regular weaves cross-fade in phase instead of turning into moire mush."""
    n = a.shape[axis]
    if not search:
        return n // 2
    hi = a - reflect_blur(a, 6)
    w = m * (1 - m)
    best, best_s = -2, n // 2
    for sh in range(n // 2 - search, n // 2 + search + 1):
        b = np.roll(hi, sh, axis=axis)
        c = (w * hi * b).sum() / np.sqrt((w * hi * hi).sum() * (w * b * b).sum() + 1e-12)
        if c > best:
            best, best_s = c, sh
    print(f"    xfade axis {axis}: shift {best_s} (corr {best:.2f})")
    return best_s


def xfade(y, band_frac=0.2, split_sigma=12, search=0, axes=(1, 0)):
    """Separable offset cross-fade of a 2D luminance array.  Pass X: blend the image with itself rolled
    by W/2; the rolled copy (whose own seam sits in the middle, where the weight is 1 for the original) is
    used at the borders, so the result wraps continuously.  Same again along Y.
    The fine detail (above split_sigma) is blended variance-preserving (no washed-out ghost bands); the
    soft low-frequency part is blended linearly (no amplified blotches)."""
    out = y.copy()
    for axis in axes:
        n = out.shape[axis]
        bf = band_frac if np.isscalar(band_frac) else band_frac[0 if axis == 1 else 1]
        m = _ramp(n, bf * n)
        m = m[None, :] if axis == 1 else m[:, None]
        b = np.roll(out, _best_shift(out, m, axis, search), axis=axis)
        lo_a, lo_b = reflect_blur(out, split_sigma), reflect_blur(b, split_sigma)
        hi_a, hi_b = out - lo_a, b - lo_b
        norm = np.sqrt(m * m + (1 - m) ** 2)
        out = lo_a * m + lo_b * (1 - m) + (hi_a * m + hi_b * (1 - m)) / norm
    return out


def _min_path(cost):
    """Min-cost top-to-bottom path through cost (h x w), 8-connected. Returns column index per row."""
    h, w = cost.shape
    e = cost.copy()
    back = np.zeros((h, w), np.int8)
    for i in range(1, h):
        prev = e[i - 1]
        left = np.r_[np.inf, prev[:-1]]
        right = np.r_[prev[1:], np.inf]
        stack = np.stack([left, prev, right])
        k = stack.argmin(axis=0)
        e[i] += stack[k, np.arange(w)]
        back[i] = k - 1
    path = np.zeros(h, np.int64)
    path[-1] = int(e[-1].argmin())
    for i in range(h - 1, 0, -1):
        path[i - 1] = path[i] + back[i, path[i]]
    return path


def quilt_cut(y, band_frac=0.15, search=0, feather=1.2, margin=12):
    """Seamless via minimum-error boundary cuts (image-quilting style) instead of a cross-fade:
    for regular weaves this keeps every thread crisp (no ghosted double image).  Pass X: B = image rolled
    by ~W/2 (phase-matched); B is used in a border strip whose inner edge follows the path where A and B
    agree best; then the same along Y (where B may also be shifted in X to match the weave phase)."""
    out = y.copy()
    for axis in (1, 0):
        a = out if axis == 1 else out.T
        n = a.shape[1]
        band = int(band_frac * n)
        m = _ramp(n, band)[None, :]
        sx = _best_shift(a, m, 1, search)
        b = np.roll(a, sx, axis=1)
        if axis == 0 and search:
            # also allow a small shift along the already-seamless direction to match phase
            hi_a = a - reflect_blur(a, 6)
            w = (m * (1 - m))
            best, best_t = -2, 0
            for t in range(-search, search + 1):
                hb = np.roll(b, t, axis=0)
                hb = hb - reflect_blur(hb, 6)
                c = (w * hi_a * hb).sum() / np.sqrt((w * hi_a ** 2).sum() * (w * hb ** 2).sum() + 1e-12)
                if c > best:
                    best, best_t = c, t
            b = np.roll(b, best_t, axis=0)
            print(f"    cut axis {axis}: cross shift {best_t} (corr {best:.2f})")
        diff = reflect_blur((a - b) ** 2, 1.0)
        mask = np.ones_like(a)
        lp = _min_path(diff[:, margin:band]) + margin
        rp = _min_path(diff[:, n - band:n - margin]) + n - band
        cols = np.arange(n)[None, :]
        mask[cols < lp[:, None]] = 0.0
        mask[cols > rp[:, None]] = 0.0
        if feather:
            mask = np.clip(reflect_blur(mask, feather), 0, 1)
        res = a * mask + b * (1 - mask)
        out = res if axis == 1 else res.T
    return out


def fft_blur(y, sigma):
    """Periodic gaussian blur (the image already wraps, so FFT is exact)."""
    h, w = y.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2 * (np.pi * sigma) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(y) * g))


def luminance(a):
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def seam_ratio(a):
    """|wrap-edge difference| / |typical neighbour difference| — ~1.0 means no visible seam."""
    y = luminance(a)
    inner_x = np.abs(np.diff(y, axis=1)).mean()
    inner_y = np.abs(np.diff(y, axis=0)).mean()
    edge_x = np.abs(y[:, 0] - y[:, -1]).mean()
    edge_y = np.abs(y[0, :] - y[-1, :]).mean()
    return edge_x / max(inner_x, 1e-6), edge_y / max(inner_y, 1e-6)


def process(name, cfg):
    a = load(os.path.join(RAW, cfg["src"]))
    y = luminance(a)
    # 1) remove light fall-off / big blotches from the raw image (non-periodic blur, before seaming)
    if cfg.get("flatten"):
        low = reflect_blur(y, cfg.get("sigma", 60))
        y = y - cfg["flatten"] * (low - low.mean())
    # 2) make it wrap
    if cfg["seam"] == "none":
        pass  # source already periodic (procedural)
    elif cfg["seam"] == "mirror":
        y = mirror_quilt(np.repeat(y[..., None], 3, axis=2))[..., 0]
    elif cfg["seam"] == "xfade_ymirror":
        # vertical strands (hair): cross-fade across X, but wrap Y by mirroring the top half — a mirror
        # is invisible on near-vertical strands, while a vertical cross-fade would double them.
        y = xfade(y, cfg.get("band", 0.2), search=cfg.get("search", 0), axes=(1,))
        top = y[: y.shape[0] // 2]
        y = np.concatenate([top, top[::-1]], axis=0)
    elif cfg["seam"] == "cut":
        y = quilt_cut(y, cfg.get("band", 0.15), search=cfg.get("search", 0))
    else:
        y = xfade(y, cfg.get("band", 0.2), search=cfg.get("search", 0))
    if cfg.get("soften"):
        y = fft_blur(y, cfg["soften"])  # periodic blur: keeps the wrap
    # 3) soft-clip outliers (dark scratches, specks) to +-k sigma so nothing punches a hole in the colour
    k = cfg.get("clip", 2.8)
    d = (y - y.mean()) / max(y.std(), 1e-6)
    d = k * np.tanh(d / k)
    # 4) normalise to a mid-light grey with low contrast
    y = cfg["mean"] + d * (cfg["std"] / max(d.std(), 1e-6))
    # 5) optional stylised ripstop grid: slightly raised (lighter) double threads, period divides 1024
    if cfg.get("grid"):
        g = cfg["grid"]
        x = np.arange(SIZE, dtype=np.float32)
        prof = np.zeros(SIZE, np.float32)
        for off in (g["period"] / 2, g["period"] / 2 + g.get("gap", 5.0)):
            dd = (x - off) % g["period"]
            dd = np.minimum(dd, g["period"] - dd)
            prof = np.maximum(prof, np.exp(-0.5 * (dd / g.get("width", 1.1)) ** 2))
        grid = np.maximum(prof[None, :], prof[:, None])
        y = y + grid * g.get("amp", 1.0) * cfg["std"] * (1.0 + 0.6 * d / k)
    out = np.repeat(y[..., None], 3, axis=2)
    if cfg.get("tint"):
        t = np.array(cfg["tint"], dtype=np.float32)
        out = out * (t / (t[0] * 0.2126 + t[1] * 0.7152 + t[2] * 0.0722))
    out = np.clip(out, 0, 1)
    path = os.path.join(OUT, name + ".png")
    save(out, path)
    sx, sy = seam_ratio(out)
    L = luminance(out)
    print(f"{name:16s} mean={L.mean():.3f} std={L.std():.3f} min={L.min():.2f} max={L.max():.2f} "
          f"seam x{sx:.2f} y{sy:.2f}  -> {path}")
    preview(name, out)
    return out


def preview(name, out):
    os.makedirs(PREV, exist_ok=True)
    # 2x2 wrap test at full res, shown at 1024
    t = np.tile(out, (2, 2, 1))
    im = Image.fromarray((t * 255).astype(np.uint8)).resize((SIZE, SIZE), Image.LANCZOS)
    # contrast-boosted strip on the right half so faint structure / seams are easy to judge
    tb = np.clip(0.5 + (t - t.mean()) * 4.0, 0, 1)
    imb = Image.fromarray((tb * 255).astype(np.uint8)).resize((SIZE, SIZE), Image.LANCZOS)
    sheet = Image.new("RGB", (SIZE * 2, SIZE))
    sheet.paste(im, (0, 0))
    sheet.paste(imb, (SIZE, 0))
    sheet.save(os.path.join(PREV, f"{name}_wrap.png"))


def contact_sheet(names):
    cell = 340
    cols = 3
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 24)), (24, 26, 30))
    dr = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        p = os.path.join(OUT, n + ".png")
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB").resize((cell - 8, cell - 8), Image.LANCZOS)
        r, c = divmod(i, cols)
        sheet.paste(im, (c * cell + 4, r * (cell + 24) + 4))
        dr.text((c * cell + 8, r * (cell + 24) + cell - 2), n, fill=(230, 230, 230))
    sheet.save(os.path.join(PREV, "_contact_sheet.png"))


if __name__ == "__main__":
    names = sys.argv[1:] or list(CONFIG)
    for n in names:
        if os.path.exists(os.path.join(RAW, CONFIG[n]["src"])):
            process(n, CONFIG[n])
        else:
            print("missing raw for", n)
    contact_sheet(list(CONFIG))
