"""Contact sheets + concept comparison images for the MAKO renders (system python + PIL).
Run: python make_sheets.py   (build_mako.py calls it after rendering)"""
import glob
import os

from PIL import Image, ImageChops, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
RD = os.path.join(HERE, "renders")
CON = os.path.join(HERE, "..", "..", "..", "art", "concepts", "mako")


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


def sheet(paths, out, cols=2, cell_w=900, title=None):
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        return
    cells = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        h = int(im.height * cell_w / im.width)
        im = im.resize((cell_w, h), Image.LANCZOS)
        label(im, os.path.splitext(os.path.basename(p))[0])
        cells.append(im)
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    top = 50 if title else 0
    H = top + sum(max(c.height for c in r) for r in rows)
    W = cols * cell_w
    S = Image.new("RGB", (W, H), (30, 32, 36))
    if title:
        label(S, title, 30)
    y = top
    for r in rows:
        for i, c in enumerate(r):
            S.paste(c, (i * cell_w, y))
        y += max(c.height for c in r)
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
    g = lambda pat: sorted(glob.glob(os.path.join(RD, pat)))  # noqa: E731
    order = ["right", "left", "three_quarter", "three_quarter_back", "low", "front", "back", "top"]
    main_p = [os.path.join(RD, f"mako_default_{v}.png") for v in order]
    sheet(main_p, os.path.join(RD, "contact_sheet_default.png"), cols=2, title="AR-7 MAKO - default loadout "
          "(base + stock_standard + mag_30, no optic)")
    sheet(g("close_*.png"), os.path.join(RD, "contact_sheet_closeups.png"), cols=3, cell_w=700,
          title="MAKO close-ups")
    sheet(g("ongun_*.png"), os.path.join(RD, "contact_sheet_variants_ongun.png"), cols=2,
          title="MAKO swappable stocks / magazines on the gun")
    sheet(g("part_*.png"), os.path.join(RD, "contact_sheet_parts.png"), cols=3, cell_w=600,
          title="MAKO parts alone (origin = mount point)")
    v09 = os.path.join(CON, "v09.png")
    cmp3 = g("cmp_v09_*.png")
    if cmp3 and os.path.exists(v09):
        a = Image.open(v09).convert("RGB")
        b = Image.open(cmp3[0]).convert("RGB").resize(a.size, Image.LANCZOS)
        S = Image.new("RGB", (a.width * 2 + 30, a.height + 50), (232, 232, 232))
        S.paste(a, (0, 50))
        S.paste(b, (a.width + 30, 50))
        d = ImageDraw.Draw(S)
        d.text((10, 10), "concept v09 (master)", fill=(20, 20, 20), font=font(28))
        d.text((a.width + 40, 10), "build (same framing, no optic)", fill=(20, 20, 20), font=font(28))
        S.save(os.path.join(RD, "compare_v09.png"))
        print("compare", os.path.join(RD, "compare_v09.png"))
    side = os.path.join(RD, "cmp_side_ortho_right.png")
    for ref in ("v04", "v02"):
        rp = os.path.join(CON, f"{ref}.png")
        if os.path.exists(side) and os.path.exists(rp):
            side_by_side(rp, side, os.path.join(RD, f"compare_side_{ref}.png"), f"concept {ref} (side)",
                         "build, orthographic right view (camera +X)")
    allp = main_p + g("close_*.png")[:6]
    sheet([p for p in allp if os.path.exists(p)], os.path.join(RD, "contact_sheet.png"), cols=3, cell_w=640,
          title="AR-7 MAKO - contact sheet")


if __name__ == "__main__":
    main()
