"""Build the foliage card atlases for the game from the Krea2 raws (see gen_raw.py).

Steps for every raw sheet: key the plain white background to a soft alpha, take the colour out of the
half-transparent edge pixels (un-mix the background), cut each cluster out (connected components), re-colour it to
the Showhome palette with a softer contrast, and pack the cards into a fixed grid. Transparent texels get the
nearest leaf colour (so mips never pull white into the edges). The hedge atlas also gets a normal map derived from
the card: a dome from the alpha's distance field plus fine relief from the luminance.

Writes (game textures):
  game/assets/textures/foliage/hedge_cards.png         1024 x 1024, 4 x 4 square cards, sRGB, straight alpha
  game/assets/textures/foliage/hedge_cards_normal.png  linear, OpenGL convention (+Y = image top)
  game/assets/textures/foliage/grass_cards.png         1024 x 1024, 4 x 8 cards of 2:1, bottom = root, sRGB
and previews in preview/.

Usage: python build_atlas.py [--leafy]          (needs numpy, scipy, Pillow)
"""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
PREVIEW = os.path.join(HERE, "preview")
GAME = os.path.normpath(os.path.join(HERE, "..", "..", "..", "game", "assets", "textures", "foliage"))

# Palette albedo (sRGB) from assets/maps/showhome/textures/_src/palette.json (README table).
HEDGE_SRGB = (98, 112, 52)
GRASS_SRGB = (126, 140, 58)

ATLAS = 1024
HEDGE_GRID = (4, 4)        # columns, rows: 16 square cards of 256 px
GRASS_GRID = (4, 8)        # 32 cards of 256 x 128 px (2:1), root on the bottom edge

# Which raws feed which atlas, in the order the cards are taken (the best sheets first).
# The painterly sheets match the concept's big soft strokes. `--leafy` builds the first try instead (small-leaf
# clusters: livelier up close but busy, a pile of rosettes from a few metres; see README.md).
HEDGE_RAWS = ["hedge_paint_s11", "hedge_paint_s12", "hedge_paint_s13"]
HEDGE_RAWS_LEAFY = ["hedge_clump_s12", "hedge_box_s13", "hedge_privet_s12"]
GRASS_RAWS = ["grass_tuft_s11", "grass_tuft_s12", "grass_tuft_s13"]


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def luminance(lin):
    return lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def key_sheet(path):
    """RGB float (sRGB 0..1) with the background un-mixed, and a soft alpha."""
    img = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
    border = np.concatenate([img[:8].reshape(-1, 3), img[-8:].reshape(-1, 3),
                             img[:, :8].reshape(-1, 3), img[:, -8:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.linalg.norm(img - bg, axis=-1)
    # Leaves are saturated; the white sheet and its faint paper noise are not.
    sat = img.max(-1) - img.min(-1)
    alpha = np.maximum(smoothstep(0.10, 0.34, dist), smoothstep(0.10, 0.30, sat) * smoothstep(0.05, 0.2, dist))
    alpha = ndimage.median_filter(alpha, size=3)
    a = np.clip(alpha, 1e-3, 1.0)[..., None]
    fg = np.clip((img - (1 - a) * bg) / a, 0.0, 1.0)
    return fg, alpha


def blobs(alpha, min_area):
    """Bounding boxes (y0, y1, x0, x1) and label masks of the separate clusters, biggest first."""
    lab, n = ndimage.label(alpha > 0.5)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        area = int((lab[sl] == i).sum())
        if area < min_area:
            continue
        out.append((area, sl, i))
    out.sort(key=lambda t: -t[0])
    return lab, out


def cut(fg, alpha, lab, sl, idx, margin=6):
    """One cluster with its own soft edge (other clusters masked out), padded by `margin` px."""
    y0, y1 = max(sl[0].start - margin, 0), min(sl[0].stop + margin, alpha.shape[0])
    x0, x1 = max(sl[1].start - margin, 0), min(sl[1].stop + margin, alpha.shape[1])
    own = ndimage.binary_dilation(lab[y0:y1, x0:x1] == idx, iterations=4)
    a = alpha[y0:y1, x0:x1] * own
    return fg[y0:y1, x0:x1].copy(), a


def recolour(fg_srgb, alpha, target_srgb, contrast, chroma_keep, gain=1.0):
    """Shift a card's mean (alpha-weighted, linear) onto the palette colour; luminance contrast and the
    leaf-to-leaf hue variation are kept partly."""
    lin = srgb_to_linear(fg_srgb)
    w = alpha[..., None]
    mean = (lin * w).sum((0, 1)) / max(w.sum(), 1e-6)
    y = luminance(lin)
    ym = luminance(mean[None, None, :])[0, 0]
    rel_y = y / max(ym, 1e-6)
    rel_y = 1.0 + (rel_y - 1.0) * contrast
    chroma = lin / np.maximum(y[..., None], 1e-6)
    mean_chroma = mean / max(ym, 1e-6)
    target = srgb_to_linear(np.array(target_srgb) / 255.0) * gain
    t_y = luminance(target[None, None, :])[0, 0]
    t_chroma = target / t_y
    out_chroma = t_chroma * (1.0 + (chroma / mean_chroma - 1.0) * chroma_keep)
    out = out_chroma * (t_y * rel_y)[..., None]
    return linear_to_srgb(out)


def fit(rgb, a, w, h, bottom=False, margin=4):
    """Scale a card into a w x h cell keeping its aspect: centred, or standing on the bottom edge."""
    ch, cw = a.shape
    s = min((w - 2 * margin) / cw, (h - 2 * margin) / ch)
    nw, nh = max(1, int(round(cw * s))), max(1, int(round(ch * s)))
    rgba = np.dstack([rgb, a])
    im = Image.fromarray((np.clip(rgba, 0, 1) * 255).astype(np.uint8), "RGBA")
    # Resize premultiplied so the edge colour does not darken.
    pre = np.asarray(im, dtype=np.float64) / 255.0
    pre[..., :3] *= pre[..., 3:4]
    pim = Image.fromarray((pre * 255).astype(np.uint8), "RGBA").resize((nw, nh), Image.LANCZOS)
    p = np.asarray(pim, dtype=np.float64) / 255.0
    cell = np.zeros((h, w, 4))
    ox = (w - nw) // 2
    oy = h - margin - nh if bottom else (h - nh) // 2
    cell[oy:oy + nh, ox:ox + nw] = p
    al = cell[..., 3:4]
    cell[..., :3] = np.where(al > 1e-4, cell[..., :3] / np.maximum(al, 1e-4), 0.0)
    return cell


def bleed(rgba, erode=2):
    """Every texel outside the card's solid interior takes the nearest interior colour. The interior is the
    alpha > 0.5 area eroded by `erode` px: its rim still carries some of the white sheet (a pale fringe), and
    filtering and mips must only ever pull in leaf colour."""
    solid = ndimage.binary_erosion(rgba[..., 3] > 0.5, iterations=erode)
    if not solid.any():
        return rgba
    _, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    out = rgba.copy()
    out[..., :3] = np.where(solid[..., None], rgba[..., :3], rgba[iy, ix, :3])
    # Far from any card, a soft blur so the fill is not streaky.
    blurred = np.dstack([ndimage.gaussian_filter(out[..., c], 3) for c in range(3)])
    far = ndimage.distance_transform_edt(~solid) > 6
    out[..., :3] = np.where(far[..., None], blurred, out[..., :3])
    return out


def normal_map(rgba, strength_dome=2.2, strength_detail=3.5):
    """Tangent-space normals (OpenGL, +Y = image top): a dome from each card's alpha plus leaf relief."""
    a = rgba[..., 3]
    inside = a > 0.5
    dome = ndimage.distance_transform_edt(inside)
    dome = np.sqrt(np.clip(dome / 40.0, 0, 1))
    lin = srgb_to_linear(rgba[..., :3])
    detail = ndimage.gaussian_filter(luminance(lin), 1.0)
    detail = detail / max(detail[inside].mean() if inside.any() else 1.0, 1e-6)
    h = dome * strength_dome + detail * strength_detail * 0.05
    h = ndimage.gaussian_filter(h, 1.2)
    gy, gx = np.gradient(h)
    # Image y grows downward; tangent-space +Y points to the image top.
    n = np.dstack([-gx, gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    flat = ~ndimage.binary_dilation(inside, iterations=6)
    n[flat] = (0.0, 0.0, 1.0)
    out = n * 0.5 + 0.5
    return np.dstack([out, np.ones_like(h)])


def gradient_grass(rgb, a, base_gain, tip_gain, tip_yellow):
    """Grass card: every row is brought to the same mean brightness first (the raws paint a dark base that reads
    as a separate object on the lawn), then the root gets `base_gain` of the lawn colour and the blade tips
    `tip_gain`, a little yellower. The blade-to-blade variation inside each row stays."""
    h = rgb.shape[0]
    lin = srgb_to_linear(rgb)
    y = luminance(lin)
    w = (a > 0.3).astype(float)
    row_mean = (y * w).sum(1) / np.maximum(w.sum(1), 1.0)
    card_mean = (y * w).sum() / max(w.sum(), 1.0)
    flat = np.where(row_mean > 1e-4, card_mean / np.maximum(row_mean, 1e-4), 1.0)
    lin = lin * flat[:, None, None]
    rows = np.where(a.max(1) > 0.3)[0]
    top, bottom = (rows.min(), rows.max()) if len(rows) else (0, h - 1)
    t = np.clip((bottom - np.arange(h)) / max(bottom - top, 1), 0, 1)[:, None, None]
    tip = np.array([1.0 + tip_yellow, 1.0 + tip_yellow * 0.6, 1.0 - tip_yellow]) * tip_gain
    gain = base_gain + (tip - base_gain) * t ** 1.2
    return linear_to_srgb(lin * gain)


def save_rgba(path, rgba):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray((np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(path, optimize=True)


def preview(path, rgba, bg=(0.55, 0.55, 0.55)):
    a = rgba[..., 3:4]
    out = rgba[..., :3] * a + np.array(bg) * (1 - a)
    Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), "RGB").save(path)


def build(raws, grid, cell_wh, bottom, colour, min_area):
    cols, rows = grid
    cw, ch = cell_wh
    atlas = np.zeros((rows * ch, cols * cw, 4))
    cards = []
    for name in raws:
        p = os.path.join(RAW, name + ".png")
        if not os.path.exists(p):
            continue
        fg, alpha = key_sheet(p)
        lab, found = blobs(alpha, min_area)
        for _, sl, idx in found:
            rgb, a = cut(fg, alpha, lab, sl, idx)
            cards.append((name, colour(rgb, a), a))
    if len(cards) < cols * rows:
        raise SystemExit(f"only {len(cards)} cards for a {cols}x{rows} atlas")
    # Interleave the sheets so neighbouring cells come from different raws.
    by_raw = {}
    for c in cards:
        by_raw.setdefault(c[0], []).append(c)
    order = []
    while len(order) < cols * rows:
        for name in list(by_raw):
            if by_raw[name]:
                order.append(by_raw[name].pop(0))
            if len(order) == cols * rows:
                break
    used = []
    for i, (name, rgb, a) in enumerate(order):
        cx, cy = i % cols, i // cols
        atlas[cy * ch:(cy + 1) * ch, cx * cw:(cx + 1) * cw] = fit(rgb, a, cw, ch, bottom)
        used.append(name)
    return atlas, used


def main():
    global HEDGE_RAWS
    if "--leafy" in sys.argv:
        HEDGE_RAWS = HEDGE_RAWS_LEAFY
    os.makedirs(PREVIEW, exist_ok=True)
    report = {}

    def hedge_colour(rgb, a):
        return recolour(rgb, a, HEDGE_SRGB, contrast=0.62, chroma_keep=0.45, gain=1.0)

    hedge, used = build(HEDGE_RAWS, HEDGE_GRID, (ATLAS // 4, ATLAS // 4), False, hedge_colour, 8000)
    hedge = bleed(hedge)
    save_rgba(os.path.join(GAME, "hedge_cards.png"), hedge)
    save_rgba(os.path.join(GAME, "hedge_cards_normal.png"), normal_map(hedge))
    preview(os.path.join(PREVIEW, "hedge_cards_on_grey.png"), hedge)
    report["hedge"] = {"cards": used, "grid": HEDGE_GRID, "palette_srgb": HEDGE_SRGB}

    def grass_colour(rgb, a):
        rgb = recolour(rgb, a, GRASS_SRGB, contrast=0.6, chroma_keep=0.5, gain=0.95)
        return gradient_grass(rgb, a, base_gain=0.9, tip_gain=1.1, tip_yellow=0.06)

    grass, used = build(GRASS_RAWS, GRASS_GRID, (ATLAS // 4, ATLAS // 8), True, grass_colour, 3000)
    grass = bleed(grass)
    save_rgba(os.path.join(GAME, "grass_cards.png"), grass)
    preview(os.path.join(PREVIEW, "grass_cards_on_grey.png"), grass)
    report["grass"] = {"cards": used, "grid": GRASS_GRID, "palette_srgb": GRASS_SRGB}

    # Mean card colour (alpha-weighted, linear) against the palette, as a check.
    for key, img, pal in (("hedge", hedge, HEDGE_SRGB), ("grass", grass, GRASS_SRGB)):
        lin = srgb_to_linear(img[..., :3])
        w = img[..., 3:4]
        mean = (lin * w).sum((0, 1)) / w.sum()
        report[key]["mean_linear"] = [round(float(v), 4) for v in mean]
        report[key]["palette_linear"] = [round(float(v), 4) for v in srgb_to_linear(np.array(pal) / 255.0)]
        report[key]["coverage"] = round(float((img[..., 3] > 0.5).mean()), 3)
    with open(os.path.join(HERE, "atlas_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
