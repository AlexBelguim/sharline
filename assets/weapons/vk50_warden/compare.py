"""Side-by-side / overlay comparison of the WARDEN build against the concept and the proportion sketch.

Needs renders/warden_exact_side.png (1 px = 1 mm orthographic, transparent background, written by
build_warden.py --render compare|quick|full). Run with the system python (PIL):
    python compare.py
Writes renders/warden_compare.png, renders/warden_compare_overlay.png, renders/warden_silhouette.png and the
labelled contact sheets renders/warden_contact_sheet.png (assembled gun + close-ups) and
renders/warden_contact_parts.png (stocks, magazines, base, alt loadout).

Pixel mapping of the exact render (same as art/concepts/warden/profile_sketch.png top panel):
    px_x = (y + 1.19) * 1000      px_y = (0.335 - z) * 1000
concept_main.png is drawn at ~1 px = 1 mm too: brake front at x=56, bore at y=259.5 -> shift (+34, 0).
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "renders")
C = os.path.join(HERE, "..", "..", "..", "art", "concepts", "warden")
BG = (214, 215, 218)


def font(sz):
    for f in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def on_bg(im, bg=BG):
    b = Image.new("RGBA", im.size, bg + (255,))
    b.alpha_composite(im)
    return b.convert("RGB")


def grid(im, color=(150, 150, 155), label=True):
    d = ImageDraw.Draw(im)
    f = font(13)
    for i in range(-11, 5):
        y = i / 10.0
        x = int(round((y + 1.19) * 1000))
        d.line([(x, 0), (x, im.height)], fill=color, width=1)
        if label:
            d.text((x + 3, im.height - 18), f"y={y:+.1f}", fill=(90, 90, 95), font=f)
    for z in (-0.2, -0.1, 0.0, 0.1, 0.2, 0.3):
        py = int(round((0.335 - z) * 1000))
        d.line([(0, py), (im.width, py)], fill=color, width=1)
        if label:
            d.text((3, py + 2), f"z={z:+.1f}", fill=(90, 90, 95), font=f)
    pz = int(round((0.335 - 0.075) * 1000))
    d.line([(0, pz), (im.width, pz)], fill=(230, 140, 60), width=1)
    return im


def main():
    mine = Image.open(os.path.join(R, "warden_exact_side.png")).convert("RGBA")
    W, H = mine.size
    concept = Image.open(os.path.join(C, "concept_main.png")).convert("RGB")
    cz = Image.new("RGB", (W, H), (211, 211, 213))
    cz.paste(concept, (34, 0))
    sketch = Image.open(os.path.join(C, "profile_sketch.png")).convert("RGB").crop((70, 33, 70 + W, 33 + H))

    alpha = mine.split()[3].point(lambda v: 255 if v > 100 else 0)
    edge = alpha.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
    red = Image.new("RGB", (W, H), (235, 30, 40))

    mine_g = grid(on_bg(mine))
    ov_c = cz.copy()
    ov_c.paste(red, mask=edge)
    ov_s = sketch.copy()
    ov_s.paste(red, mask=edge)
    # translucent blend of the build over the concept
    blend = Image.blend(cz, on_bg(mine, (211, 211, 213)), 0.55)

    rows = [("CONCEPT concept_main.png (style / colour reference, 1 px ~ 1 mm, aligned on brake front + bore)", cz),
            ("BUILD  exact orthographic left side (+X), 1 px = 1 mm (no scope / bipod: separate attachments)", mine_g),
            ("OVERLAY  build silhouette (red) on the concept", ov_c),
            ("OVERLAY  build silhouette (red) on profile_sketch.png (BRIEF proportions proxy, incl. scope + bipod)", ov_s)]
    lab = 30
    sheet = Image.new("RGB", (W, (H + lab) * len(rows)), (245, 245, 247))
    d = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(rows):
        y0 = i * (H + lab)
        d.text((10, y0 + 6), t, fill=(20, 20, 25), font=font(18))
        sheet.paste(im, (0, y0 + lab))
    out = os.path.join(R, "warden_compare.png")
    sheet.save(out)
    # side-by-side (build | concept) at half size for a quick look + blend
    sbs = Image.new("RGB", (W, H * 2 + 2 * lab), (245, 245, 247))
    d = ImageDraw.Draw(sbs)
    d.text((10, 6), "BLEND 55% build over concept", fill=(20, 20, 25), font=font(18))
    sbs.paste(blend, (0, lab))
    d.text((10, H + lab + 6), "BUILD (left side, +X)", fill=(20, 20, 25), font=font(18))
    sbs.paste(on_bg(mine), (0, H + 2 * lab))
    sbs.save(os.path.join(R, "warden_compare_overlay.png"))
    print("wrote", out)



def silhouettes():
    """64 / 128 / 256 px wide black silhouettes of the exact side render (BRIEF section 6 read check)."""
    mine = Image.open(os.path.join(R, "warden_exact_side.png")).convert("RGBA")
    a = mine.split()[3]
    bb = a.getbbox()
    a = a.crop((bb[0] - 20, bb[1] - 20, bb[2] + 20, bb[3] + 20))
    sil = Image.merge("RGB", [a.point(lambda v: 255 - v)] * 3)
    tiles = []
    for w in (64, 128, 256):
        h = max(1, round(sil.height * w / sil.width))
        t = sil.resize((w, h), Image.LANCZOS).resize((w * 4 if w < 256 else w * 2, h * 4 if w < 256 else h * 2),
                                                     Image.NEAREST)
        tiles.append((w, t))
    W = max(t.width for _, t in tiles) + 20
    H = sum(t.height + 34 for _, t in tiles)
    sheet = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    y = 0
    for w, t in tiles:
        d.text((10, y + 6), f"silhouette at {w} px wide (pixel-enlarged)", fill=(0, 0, 0), font=font(16))
        sheet.paste(t, (10, y + 30))
        y += t.height + 34
    sheet.save(os.path.join(R, "warden_silhouette.png"))



def sheet(items, out, cols=3, tile=(760, 430), title=None):
    """Labelled contact sheet: items = [(label, filename in renders/)]; each render letterboxed into a tile."""
    tw, th = tile
    lab = 26
    top = 44 if title else 0
    rows = (len(items) + cols - 1) // cols
    im = Image.new("RGB", (cols * tw, top + rows * (th + lab)), (236, 236, 239))
    d = ImageDraw.Draw(im)
    if title:
        d.text((12, 10), title, fill=(15, 15, 20), font=font(24))
    for i, (label, fn) in enumerate(items):
        r, c = divmod(i, cols)
        x0, y0 = c * tw, top + r * (th + lab)
        p = os.path.join(R, fn)
        d.text((x0 + 8, y0 + 4), label, fill=(25, 25, 30), font=font(17))
        if not os.path.exists(p):
            d.text((x0 + 8, y0 + lab + 8), "(missing) " + fn, fill=(200, 30, 30), font=font(15))
            continue
        src = Image.open(p).convert("RGB")
        s = min(tw / src.width, th / src.height)
        src = src.resize((max(1, int(src.width * s)), max(1, int(src.height * s))), Image.LANCZOS)
        im.paste(src, (x0 + (tw - src.width) // 2, y0 + lab + (th - src.height) // 2))
    im.save(os.path.join(R, out))
    print("wrote", out)


def contact_sheets():
    sheet([("right side (+X camera = gun's LEFT)", "warden_right.png"),
           ("left side (-X camera = gun's RIGHT: bolt, port)", "warden_left.png"),
           ("three-quarter", "warden_three_quarter.png"),
           ("three-quarter back", "warden_three_quarter_back.png"),
           ("top (screen-up = -X, shooter's right)", "warden_top.png"),
           ("low three-quarter", "warden_low.png"),
           ("front (ortho)", "warden_front.png"),
           ("back (ortho)", "warden_back.png"),
           ("close-up: muzzle brake", "warden_cu_brake.png"),
           ("close-up: bolt + knob (-X), closed", "warden_cu_bolt.png"),
           ("bolt lifted 60 deg: root turns behind the receiver", "warden_cu_bolt_lifted.png"),
           ("bolt open (0.13 m): clears stock + riser", "warden_cu_bolt_open.png"),
           ("bolt open, side (-X camera)", "warden_bolt_open_left.png"),
           ("bolt open, shooter's view", "warden_bolt_open_fpv.png"),
           ("close-up: receiver right / ejection port", "warden_cu_receiver_right.png"),
           ("close-up: receiver left", "warden_cu_receiver_left.png"),
           ("close-up: handguard underside, rails", "warden_cu_handguard_under.png"),
           ("close-up: magwell + mag seating", "warden_cu_magwell.png"),
           ("sockets (debug markers)", "warden_sockets_left.png")],
          "warden_contact_sheet.png", cols=4, tile=(640, 400),
          title="VK-50 WARDEN  default loadout (base + stock_standard + mag_5; optic + bipod are separate attachments)")
    sheet([("stock_standard 3/4", "warden_stock_standard_three_quarter.png"),
           ("stock_standard right", "warden_stock_standard_right.png"),
           ("stock_standard 3/4 back", "warden_stock_standard_three_quarter_back.png"),
           ("stock_folding 3/4", "warden_stock_folding_three_quarter.png"),
           ("stock_folding right", "warden_stock_folding_right.png"),
           ("stock_folding 3/4 back", "warden_stock_folding_three_quarter_back.png"),
           ("mag_5 3/4", "warden_mag_5_three_quarter.png"),
           ("mag_5 right", "warden_mag_5_right.png"),
           ("mag_5 feed lips", "warden_mag_5_top_feedlips.png"),
           ("mag_8 3/4", "warden_mag_8_three_quarter.png"),
           ("mag_8 right", "warden_mag_8_right.png"),
           ("mag_8 feed lips", "warden_mag_8_top_feedlips.png"),
           ("mag_5 check: 2 rounds left, follower raised", "warden_mag_5_check_two_left.png"),
           ("mag_5 check: 2 left (3/4)", "warden_mag_5_check_two_left_three_quarter.png"),
           ("mag_5 empty: follower under the lips", "warden_mag_5_check_empty_top.png"),
           ("base only (no stock / mag)", "warden_base_only_three_quarter_back.png"),
           ("alt loadout: stock_folding + mag_8", "warden_alt_three_quarter.png"),
           ("stock_folding folded (top)", "warden_alt_folded_top.png"),
           ("stock_folding: bolt open clears it", "warden_bolt_open_folding_stock.png"),
           ("stock_folding folded 3/4", "warden_alt_folded_three_quarter.png")],
          "warden_contact_parts.png", cols=3, tile=(640, 520),
          title="VK-50 WARDEN  swappable parts (origin of each part = its socket / mount point)")


if __name__ == "__main__":
    main()
    silhouettes()
    contact_sheets()
