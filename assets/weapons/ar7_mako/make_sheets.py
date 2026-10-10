"""Contact sheets + concept comparison images for the MAKO renders (system python + PIL).
Run: python make_sheets.py   (build_mako.py calls it after rendering)"""
import glob
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont

SOURCE = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.abspath(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else os.environ.get("MAKO_OUT", SOURCE)
RD = os.environ.get("MAKO_RD") or os.path.join(HERE, "renders")   # MAKO_RD: iteration renders elsewhere
CON = os.path.join(SOURCE, "..", "..", "..", "art", "concepts", "mako")
try:  # studio background colour, sampled from a full-gun render (close-ups may have geometry in the corners)
    BGC = Image.open(os.path.join(RD, "mako_default_right.png")).convert("RGB").getpixel((2, 2))
except OSError:
    BGC = (187, 187, 187)


def font(sz):
    for f in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def label(im, text, sz=22):
    d = ImageDraw.Draw(im)
    f = font(sz)
    d.rectangle([0, 0, im.width, sz + 12], fill=(20, 22, 26))
    d.text((8, 4), text, fill=(235, 235, 235), font=f)
    return im


def sheet(paths, out, cols=2, cell_w=900, title=None, aspect=0.62):
    """Grid of renders; every cell has the same size (images are fitted and padded with their own background)."""
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return
    cell_h = int(cell_w * aspect)
    cells = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        k = min(cell_w / im.width, cell_h / im.height)
        im2 = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
        c = Image.new("RGB", (cell_w, cell_h), BGC)
        c.paste(im2, ((cell_w - im2.width) // 2, (cell_h - im2.height) // 2))
        label(c, os.path.splitext(os.path.basename(p))[0])
        cells.append(c)
    rows = (len(cells) + cols - 1) // cols
    top = 50 if title else 0
    S = Image.new("RGB", (cols * cell_w, top + rows * cell_h), (30, 32, 36))
    if title:
        label(S, title, 30)
    for i, c in enumerate(cells):
        S.paste(c, ((i % cols) * cell_w, top + (i // cols) * cell_h))
    S.save(out)
    print("sheet", out)


def bbox_fg(im, thresh=28):
    """Bounding box of everything that differs from the corner background colour."""
    rgb = im.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((3, 3)))
    diff = ImageChops.difference(rgb, bg).convert("L").point(lambda v: 255 if v > thresh else 0)
    return diff.getbbox()


def bore_row(im, frac=0.02, thresh=28):
    rgb = im.convert("RGB")
    bgc = rgb.getpixel((rgb.width - 2, 2))
    cols = max(2, int(rgb.width * frac))
    rows = []
    for x in range(cols):
        for y in range(rgb.height):
            p = rgb.getpixel((x, y))
            if sum(abs(p[i] - bgc[i]) for i in range(3)) > thresh * 2:
                rows.append(y)
    return int(sum(rows) / len(rows)) if rows else rgb.height // 2


def side_by_side(a_path, b_path, out, la, lb, match="width", overlay=True):
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    ca = a.crop(bbox_fg(a))
    cb = b.crop(bbox_fg(b))
    if match == "width":  # same gun length
        W = 1400
        ca = ca.resize((W, int(ca.height * W / ca.width)), Image.LANCZOS)
        cb = cb.resize((W, int(cb.height * W / cb.width)), Image.LANCZOS)
    pad = 40
    H = ca.height + cb.height + 3 * pad + (max(ca.height, cb.height) + pad if overlay else 0)
    S = Image.new("RGB", (W + 2 * pad, H), (232, 232, 232))
    S.paste(ca, (pad, pad))
    S.paste(cb, (pad, 2 * pad + ca.height))
    d = ImageDraw.Draw(S)
    f = font(26)
    d.text((pad, 6), la, fill=(20, 20, 20), font=f)
    d.text((pad, pad + ca.height + 6), lb, fill=(20, 20, 20), font=f)
    if overlay:
        # align on the bore line: mean row of the foreground in the first 2% of columns (the muzzle)
        ra, rb = bore_row(ca), bore_row(cb)
        off = rb - ra
        hh = max(ca.height + max(off, 0), cb.height + max(-off, 0))
        A = Image.new("RGB", (W, hh), (232, 232, 232))
        B = Image.new("RGB", (W, hh), (232, 232, 232))
        A.paste(ca, (0, max(off, 0)))
        B.paste(cb, (0, max(-off, 0)))
        ov = Image.blend(A, B, 0.5)
        y0 = 3 * pad + ca.height + cb.height
        S.paste(ov, (pad, y0))
        d.text((pad, y0 - pad + 6), "50/50 overlay (scaled to equal overall length)", fill=(20, 20, 20), font=f)
    S.save(out)
    print("compare", out)


def main():
    J = lambda *n: [os.path.join(RD, x + ".png") for x in n]  # noqa: E731
    main_p = J(*[f"mako_default_{v}" for v in ("right", "left", "three_quarter", "three_quarter_back", "low",
                                               "front", "back", "top")])
    sheet(main_p, os.path.join(RD, "contact_sheet_default.png"), cols=2, title="AR-7 MAKO - default loadout "
          "(base + stock_standard + mag_30, no optic)")
    close_p = J("close_receiver_right", "close_receiver_left", "close_receiver_v09", "close_receiver_front_right",
                "close_handguard_v09", "close_handguard_under", "close_muzzle_three_quarter", "close_muzzle_right",
                "close_muzzle_front", "close_stock_right", "close_stock_rear", "close_mag_right", "close_mag_front")
    sheet(close_p, os.path.join(RD, "contact_sheet_closeups.png"), cols=3, cell_w=700, title="MAKO close-ups",
          aspect=0.78)
    ongun = J(*[f"ongun_{k}_right" for k in ("stock_standard", "stock_precision", "stock_light", "mag_30", "mag_45",
                                             "mag_drum60")])
    sheet(ongun, os.path.join(RD, "contact_sheet_variants_ongun.png"), cols=2,
          title="MAKO swappable stocks / magazines on the gun")
    parts_p = []
    for k in ("stock_standard", "stock_precision", "stock_light"):
        parts_p += J(*[f"part_{k}_{v}" for v in ("right", "three_quarter", "three_quarter_back")])
    for k in ("mag_30", "mag_45", "mag_drum60"):
        parts_p += J(*[f"part_{k}_{v}" for v in ("right", "three_quarter", "left")])
    sheet(parts_p, os.path.join(RD, "contact_sheet_parts.png"), cols=3, cell_w=600,
          title="MAKO parts alone (origin = mount point)", aspect=1.0)
    fixes = sorted(glob.glob(os.path.join(RD, "fix_*.png")))
    sheet(fixes, os.path.join(RD, "contact_sheet_review_fixes.png"), cols=4, cell_w=600,
          title="MAKO review fixes (clay = shading check; mag30_N = mag-check state with N rounds)", aspect=0.75)
    fixes2 = sorted(glob.glob(os.path.join(RD, "fix2_*.png")))
    sheet(fixes2, os.path.join(RD, "contact_sheet_review_fixes_r2.png"), cols=4, cell_w=600,
          title="MAKO review fixes, round 2 (clay = real per-edge bevels; grip knuckle, sling, mag flare, drum)",
          aspect=0.75)
    v09 = os.path.join(CON, "v09.png")
    cmp3 = os.path.join(RD, "cmp_v09.png")
    if os.path.exists(cmp3) and os.path.exists(v09):
        a = Image.open(v09).convert("RGB")
        b = Image.open(cmp3).convert("RGB").resize(a.size, Image.LANCZOS)
        S = Image.new("RGB", (a.width * 2 + 30, a.height + 50), (232, 232, 232))
        S.paste(a, (0, 50))
        S.paste(b, (a.width + 30, 50))
        d = ImageDraw.Draw(S)
        d.text((10, 10), "concept v09 (master)", fill=(20, 20, 20), font=font(28))
        d.text((a.width + 40, 10), "build (same view direction, no optic: optics are separate attachments)",
               fill=(20, 20, 20), font=font(28))
        # silhouette overlay, both cropped to their bounding boxes (optic masked out of the concept)
        import numpy as np

        def mask(im, thr=40):
            arr = np.asarray(im.convert("RGB")).astype(int)
            return np.abs(arr - arr[2, 2]).sum(-1) > thr

        def norm(m, W=a.width, H=int(a.width * 0.42)):
            ys, xs = np.nonzero(m)
            c = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            return np.asarray(Image.fromarray((c * 255).astype(np.uint8)).resize((W, H))) > 127
        mv = mask(a)
        h, w = mv.shape
        mv[int(h * 0.14):int(h * 0.42), int(w * 0.33):int(w * 0.45)] = False
        nv, nb = norm(mv), norm(mask(b))
        ov = np.full(nv.shape + (3,), 235, np.uint8)
        ov[nv & ~nb] = (220, 60, 60)
        ov[nb & ~nv] = (40, 150, 220)
        ov[nb & nv] = (70, 70, 70)
        iou = (nv & nb).sum() / max((nv | nb).sum(), 1)
        O = Image.fromarray(ov)
        S2 = Image.new("RGB", (S.width, S.height + O.height + 50), (232, 232, 232))
        S2.paste(S, (0, 0))
        S2.paste(O, (0, S.height + 50))
        d = ImageDraw.Draw(S2)
        d.text((10, S.height + 10), f"silhouettes cropped to their bounding boxes: grey = both, red = concept only, "
               f"blue = build only (optic masked out). IoU {iou:.2f}", fill=(20, 20, 20), font=font(28))
        S = S2
        S.save(os.path.join(RD, "compare_v09.png"))
        with open(os.path.join(HERE, "_work", "compare_v09_iou.txt"), "w") as fh:
            fh.write(f"{iou:.3f}" + chr(10))
        print("compare", os.path.join(RD, "compare_v09.png"))
    side = os.path.join(RD, "cmp_side_ortho_right.png")
    for ref in ("v04", "v02"):
        rp = os.path.join(CON, f"{ref}.png")
        if os.path.exists(side) and os.path.exists(rp):
            side_by_side(rp, side, os.path.join(RD, f"compare_side_{ref}.png"), f"concept {ref} (side)",
                         "build, orthographic right view (camera +X)")
    allp = J("cmp_v09") + main_p + J("close_receiver_v09", "close_receiver_front_right", "close_handguard_v09", "close_muzzle_three_quarter",
                      "close_stock_rear", "close_mag_front", "ongun_mag_45_right", "ongun_mag_drum60_right",
                      "ongun_stock_precision_right", "ongun_stock_light_right")
    sheet([p for p in allp if os.path.exists(p)], os.path.join(RD, "contact_sheet.png"), cols=3, cell_w=640,
          title="AR-7 MAKO - contact sheet")


if __name__ == "__main__":
    main()
