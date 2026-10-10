"""Side-by-side / overlay comparison of the WARDEN build against concept_main.png (the proportion reference).

Needs renders/warden_exact_side.png (1 px = 1 mm orthographic, transparent background, written by
build_warden.py --render compare|quick|full). Run with the system python (PIL):
    python compare.py
Writes renders/warden_compare.png (concept, build, overlay, both outlines + IoU), renders/warden_compare_zoom.png
(part-by-part 2 px/mm crops), renders/warden_compare_overlay.png, renders/warden_silhouette.png and the
labelled contact sheets renders/warden_contact_sheet.png (assembled gun + close-ups) and
renders/warden_contact_parts.png (stocks, magazines, base, alt loadout).

Pixel mapping of the exact render (same as art/concepts/warden/profile_sketch.png top panel):
    px_x = (y + 1.19) * 1000      px_y = (0.335 - z) * 1000
concept_main.png is drawn at ~1 px = 1 mm too: brake front at x=56, bore at y=259.5 -> shift (+34, 0).
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont  # numpy is used too

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


def concept_mask(cz):
    """Trace the concept's gun silhouette (no scope, no bipod): everything clearly off the grey background, minus
    the scope above the rail line over the receiver and the bipod under the handguard front."""
    import numpy as np
    a = np.asarray(cz).astype(np.int32)
    H, W = a.shape[:2]
    d = np.abs(a - a[5:40, 5:40].reshape(-1, 3).mean(0)).sum(2)
    m = d > 40
    yy, xx = np.mgrid[0:H, 0:W]
    m &= ~((xx > PX(-0.47)) & (xx < PX(0.0)) & (yy < PZ(0.122)))      # scope + rings
    m &= ~((xx > PX(-0.66)) & (xx < PX(-0.50)) & (yy > PZ(0.033)))     # bipod
    m[:, :40] = False
    return m


def PX(y):
    return int(round((y + 1.19) * 1000))


def PZ(z):
    return int(round((0.335 - z) * 1000))


def edge_of(mask):
    import numpy as np
    im = Image.fromarray((mask * 255).astype(np.uint8))
    return im.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))


def main():
    import numpy as np
    mine = Image.open(os.path.join(R, "warden_exact_side.png")).convert("RGBA")
    W, H = mine.size
    concept = Image.open(os.path.join(C, "concept_main.png")).convert("RGB")
    cz = Image.new("RGB", (W, H), (211, 211, 213))
    cz.paste(concept, (34, 0))
    bm = np.asarray(mine)[:, :, 3] > 100
    cm = concept_mask(cz)
    e_b, e_c = edge_of(bm), edge_of(cm)
    red = Image.new("RGB", (W, H), (235, 30, 40))
    cyan = Image.new("RGB", (W, H), (0, 190, 215))

    mine_g = grid(on_bg(mine))
    ov_c = cz.copy()
    ov_c.paste(red, mask=e_b)
    both = Image.new("RGB", (W, H), (250, 250, 250))
    grid(both, (215, 215, 220))
    both.paste(cyan, mask=e_c)
    both.paste(red, mask=e_b)
    iou = (cm & bm).sum() / max(1, (cm | bm).sum())
    blend = Image.blend(cz, on_bg(mine, (211, 211, 213)), 0.55)

    rows = [("CONCEPT concept_main.png (THE proportion reference, DIRECTION_LOG 13; 1 px ~ 1 mm, aligned on brake front + bore)", cz),
            ("BUILD  exact orthographic left side (+X), 1 px = 1 mm (no scope / bipod: separate attachments)", mine_g),
            ("OVERLAY  build silhouette (red) on the concept", ov_c),
            (f"OUTLINES  concept traced without scope / bipod (cyan) vs build (red)   silhouette IoU {iou:.3f}", both)]
    lab = 30
    sheet = Image.new("RGB", (W, (H + lab) * len(rows)), (245, 245, 247))
    d = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(rows):
        y0 = i * (H + lab)
        d.text((10, y0 + 6), t, fill=(20, 20, 25), font=font(18))
        sheet.paste(im, (0, y0 + lab))
    out = os.path.join(R, "warden_compare.png")
    sheet.save(out)
    # blend + plain build
    sbs = Image.new("RGB", (W, H * 2 + 2 * lab), (245, 245, 247))
    d = ImageDraw.Draw(sbs)
    d.text((10, 6), "BLEND 55% build over concept", fill=(20, 20, 25), font=font(18))
    sbs.paste(blend, (0, lab))
    d.text((10, H + lab + 6), "BUILD (left side, +X)", fill=(20, 20, 25), font=font(18))
    sbs.paste(on_bg(mine), (0, H + 2 * lab))
    sbs.save(os.path.join(R, "warden_compare_overlay.png"))
    # zoomed part-by-part crops (2 px per mm): concept painting + both outlines
    ov = np.asarray(cz).copy()
    ov[np.asarray(e_c) > 0] = (0, 190, 215)
    ov[np.asarray(e_b) > 0] = (235, 30, 40)
    ovi = Image.fromarray(ov)
    crops = [("muzzle brake + barrel", -1.12, -0.62), ("handguard, receiver, magazine", -0.72, -0.10),
             ("grip, stock", -0.20, 0.34)]
    tiles = []
    for nm, y0, y1 in crops:
        c = ovi.crop((PX(y0), PZ(0.16), PX(y1), PZ(-0.15)))
        c = c.resize((c.width * 2, c.height * 2), Image.NEAREST)
        dr = ImageDraw.Draw(c)
        g = round(y0 + 0.05 - (y0 % 0.05), 2)
        while g <= y1:
            x = (PX(g) - PX(y0)) * 2
            dr.line([(x, 0), (x, 10)], fill=(0, 0, 0))
            dr.text((x + 2, 0), f"y{g:+.2f}", fill=(0, 0, 0), font=font(12))
            g = round(g + 0.05, 2)
        for gz in (-0.10, -0.05, 0.0, 0.05, 0.10, 0.15):
            yv = (PZ(gz) - PZ(0.16)) * 2
            dr.line([(0, yv), (10, yv)], fill=(0, 0, 0))
            dr.text((12, yv - 7), f"z{gz:+.2f}", fill=(0, 0, 0), font=font(12))
        tiles.append((nm, c))
    Wz = max(t.width for _, t in tiles)
    zs = Image.new("RGB", (Wz, sum(t.height + lab for _, t in tiles)), (245, 245, 247))
    d = ImageDraw.Draw(zs)
    y = 0
    for nm, t in tiles:
        d.text((10, y + 6), f"ZOOM 2 px/mm  {nm}: concept outline cyan, build outline red", fill=(20, 20, 25),
               font=font(18))
        zs.paste(t, (0, y + lab))
        y += t.height + lab
    zs.save(os.path.join(R, "warden_compare_zoom.png"))
    print(f"wrote {out}  (silhouette IoU vs concept without scope / bipod: {iou:.3f})")


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
           ("close-up: handguard left (slots stay dark)", "warden_cu_handguard_left.png"),
           ("close-up: stock left", "warden_cu_stock_left.png"),
           ("stock underside: monopod foot flush (retracted)", "warden_cu_stock_under.png"),
           ("monopod extended (optional, -0.105 m)", "warden_cu_monopod_extended.png"),
           ("bright snow backdrop: no see-through slots", "warden_check_brightbg_left.png"),
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
