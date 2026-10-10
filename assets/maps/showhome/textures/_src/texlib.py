"""Shared helpers for the Showhome texture library: image I/O, colour space, seamless wrapping, periodic noise,
recolouring to a palette albedo and normal maps from height.

The seam functions (xfade = variance-preserving offset cross-fade, quilt_cut = minimum-error boundary cut) follow
the approach of art/textures/_src/process_textures.py (copied here so this folder is self-contained).
Arrays are float32 in 0..1, shape (H, W) for one channel or (H, W, 3/4) for colour.
"""
import numpy as np
from PIL import Image

LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


# ------------------------------------------------------------------------------------------------ I/O + colour
def load(path, size=1024):
    im = Image.open(path).convert("RGB")
    if im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0


def save(arr, path):
    a = np.clip(arr, 0, 1)
    mode = "RGBA" if a.ndim == 3 and a.shape[2] == 4 else ("L" if a.ndim == 2 else "RGB")
    Image.fromarray((a * 255 + 0.5).astype(np.uint8), mode).save(path, optimize=True)


def to_lin(c):
    c = np.asarray(c, dtype=np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float32), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055).astype(np.float32)


def luminance(a):
    return a[..., 0] * LUMA[0] + a[..., 1] * LUMA[1] + a[..., 2] * LUMA[2]


# ------------------------------------------------------------------------------------------------ blurs
def fft_blur(y, sigma):
    """Periodic gaussian blur (exact for an image that already wraps). Works on (H, W) or (H, W, C)."""
    if y.ndim == 3:
        return np.stack([fft_blur(y[..., i], sigma) for i in range(y.shape[2])], axis=2)
    if np.isscalar(sigma):
        sigma = (sigma, sigma)
    h, w = y.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2 * (np.pi ** 2) * ((sigma[0] * fy) ** 2 + (sigma[1] * fx) ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(y) * g)).astype(np.float32)


def reflect_blur(y, sigma):
    """Gaussian blur of a NON-periodic array (reflect padding + FFT)."""
    if y.ndim == 3:
        return np.stack([reflect_blur(y[..., i], sigma) for i in range(y.shape[2])], axis=2)
    pad = min(int(3 * sigma) + 1, y.shape[0] - 1, y.shape[1] - 1)
    yp = np.pad(y, pad, mode="reflect")
    return fft_blur(yp, sigma)[pad:-pad, pad:-pad]


def flatten(a, sigma, amount=1.0):
    """Remove low-frequency light fall-off / blotches from a raw (non-periodic) image, keeping its mean."""
    low = reflect_blur(a, sigma)
    return a - amount * (low - low.mean(axis=(0, 1)))


# ------------------------------------------------------------------------------------------------ seamless
def _ramp(n, band):
    x = np.arange(n, dtype=np.float32)
    d = np.clip(np.minimum(x + 0.5, n - x - 0.5) / band, 0, 1)
    return d * d * (3 - 2 * d)


def xfade(img, band_frac=0.2, split_sigma=12, axes=(1, 0)):
    """Separable offset cross-fade (X then Y): blend the image with itself rolled by half its size, using the
    rolled copy at the borders, so the result wraps. Fine detail is blended variance-preserving (no washed-out
    ghost band); the soft low-frequency part linearly. Works on (H, W) or (H, W, C)."""
    out = img.astype(np.float32).copy()
    for axis in axes:
        n = out.shape[axis]
        bf = band_frac if np.isscalar(band_frac) else band_frac[0 if axis == 1 else 1]
        m = _ramp(n, bf * n)
        m = m[None, :] if axis == 1 else m[:, None]
        if out.ndim == 3:
            m = m[..., None]
        b = np.roll(out, n // 2, axis=axis)
        lo_a, lo_b = reflect_blur(out, split_sigma), reflect_blur(b, split_sigma)
        hi_a, hi_b = out - lo_a, b - lo_b
        norm = np.sqrt(m * m + (1 - m) ** 2)
        out = lo_a * m + lo_b * (1 - m) + (hi_a * m + hi_b * (1 - m)) / norm
    return out


def _min_path(cost):
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


def quilt_cut(img, band_frac=0.15, feather=1.5, margin=12):
    """Seamless via minimum-error boundary cuts (image quilting): keeps crisp features (cracks, pebbles) crisp
    instead of ghosting them. Works on (H, W) or (H, W, C)."""
    out = img.astype(np.float32).copy()
    col = out.ndim == 3
    for axis in (1, 0):
        a = out if axis == 1 else np.swapaxes(out, 0, 1)
        n = a.shape[1]
        band = int(band_frac * n)
        b = np.roll(a, n // 2, axis=1)
        diff = (a - b) ** 2
        if col:
            diff = diff.sum(axis=2)
        diff = reflect_blur(diff, 1.0)
        lp = _min_path(diff[:, margin:band]) + margin
        rp = _min_path(diff[:, n - band:n - margin]) + n - band
        cols = np.arange(n)[None, :]
        mask = np.ones(a.shape[:2], np.float32)
        mask[cols < lp[:, None]] = 0.0
        mask[cols > rp[:, None]] = 0.0
        if feather:
            mask = np.clip(reflect_blur(mask, feather), 0, 1)
        if col:
            mask = mask[..., None]
        res = a * mask + b * (1 - mask)
        out = res if axis == 1 else np.swapaxes(res, 0, 1)
    return out


def seam_ratio(a):
    """|wrap-edge difference| / |typical neighbour difference| (about 1.0 = no visible seam)."""
    y = luminance(a[..., :3]) if a.ndim == 3 else a
    ix = np.abs(np.diff(y, axis=1)).mean()
    iy = np.abs(np.diff(y, axis=0)).mean()
    ex = np.abs(y[:, 0] - y[:, -1]).mean()
    ey = np.abs(y[0, :] - y[-1, :]).mean()
    return ex / max(ix, 1e-6), ey / max(iy, 1e-6)


# ------------------------------------------------------------------------------------------------ noise
def periodic_noise(h, w, sigma, seed, aniso=None):
    """Smooth periodic gaussian noise, zero mean, unit std. aniso=(sy, sx) for stretched noise."""
    rng = np.random.default_rng(seed)
    n = rng.standard_normal((h, w)).astype(np.float32)
    n = fft_blur(n, aniso if aniso else sigma)
    n -= n.mean()
    return n / max(n.std(), 1e-6)


def fbm(h, w, seed, sigmas=(64, 24, 8), weights=(1.0, 0.5, 0.25)):
    out = np.zeros((h, w), np.float32)
    for i, (s, wt) in enumerate(zip(sigmas, weights)):
        out += wt * periodic_noise(h, w, s, seed + 101 * i)
    out -= out.mean()
    return out / max(out.std(), 1e-6)


def periodic_wave(n, cycles, rng, amp=1.0, harmonics=3):
    """1D periodic smooth wave over n samples with integer cycles (tiles exactly)."""
    x = np.arange(n, dtype=np.float32) / n
    out = np.zeros(n, np.float32)
    for k in range(harmonics):
        c = cycles * (k + 1) + int(rng.integers(0, 2))
        out += (0.6 ** k) * np.sin(2 * np.pi * (c * x + rng.random()))
    return amp * out / max(np.abs(out).max(), 1e-6)


# ------------------------------------------------------------------------------------------------ recolour
def normalise_detail(y, clip=2.6):
    """Zero-mean unit-std detail with soft-clipped outliers (no dark speck punches a hole in the colour)."""
    d = (y - y.mean()) / max(y.std(), 1e-6)
    d = clip * np.tanh(d / clip)
    return (d - d.mean()) / max(d.std(), 1e-6)


def colourise(d, base_srgb, std, shadow_tint=(0.0, 0.0, 0.0), light_tint=(0.0, 0.0, 0.0)):
    """Luminance detail d (zero mean, unit std) -> sRGB colour around base_srgb (0..1). std = luminance std in
    sRGB units. shadow/light tints: sRGB offsets per unit of negative / positive detail (painterly hue shift)."""
    base = np.asarray(base_srgb, np.float32)
    out = base[None, None, :] * (1.0 + d[..., None] * std / max(float(base @ LUMA), 1e-3))
    neg = np.clip(-d, 0, None)[..., None]
    pos = np.clip(d, 0, None)[..., None]
    out = out + neg * np.asarray(shadow_tint, np.float32) * std + pos * np.asarray(light_tint, np.float32) * std
    return out


def recolour_rgb(src, base_srgb, std, hue_keep=1.0):
    """Keep an AI raw's own hue variation (scaled by hue_keep, 0 = luminance only) but move its mean to base_srgb
    and its luminance std to `std`."""
    m = src.reshape(-1, 3).mean(axis=0)
    dev = src - m
    if hue_keep != 1.0:
        ld = luminance(dev)[..., None]
        dev = ld + (dev - ld) * hue_keep
    s = luminance(dev).std()
    return np.asarray(base_srgb, np.float32)[None, None, :] + dev * (std / max(s, 1e-6))


def match_mean_linear(rgb_srgb, target_lin, iters=4):
    """Per-channel gain in linear space so the texture's average reflectance equals the palette albedo exactly."""
    out = np.clip(rgb_srgb, 0, 1)
    t = np.asarray(target_lin, np.float32)
    for _ in range(iters):
        lin = to_lin(out)
        g = t / np.maximum(lin.reshape(-1, 3).mean(axis=0), 1e-6)
        out = to_srgb(np.clip(lin * g[None, None, :], 0, 1))
    return out


# ------------------------------------------------------------------------------------------------ normals
def normal_from_height(h, strength):
    """Tangent-space normal map (OpenGL / glTF convention: +X right, +Y up = toward the top of the image)
    from a periodic height field (0..1). strength = height-to-pixel slope scale."""
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5 * strength
    drow = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5 * strength
    nx, ny, nz = -dx, drow, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5], axis=2)
