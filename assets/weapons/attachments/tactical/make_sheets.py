"""Contact sheets + concept comparisons for the ATT tactical set (system python + PIL).

  python make_sheets.py grid <out.png> <cols> <img> [<img> ...]     ad-hoc labelled grid
  python make_sheets.py all                                          per-part sheets + comparisons + overview
"""
import glob
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = str(Path(__file__).resolve().parent)
R = os.path.join(HERE, "renders")
C = os.path.join(HERE, "concepts")


def font(sz):
    for f in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def grid(paths, out, cols=3, cell=420, title=None, cell_h=None):
    """Labelled grid. cell = cell width; cell_h = image area height (default square). Each label sits directly under
    its own image (wide renders such as the 1400x900 loadouts use cell_h = cell * 900 / 1400, so no empty bands)."""
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        print("no images for", out)
        return
    ch = cell_h or cell
    lab = 22
    rows = (len(paths) + cols - 1) // cols
    top = 40 if title else 0
    sheet = Image.new("RGB", (cols * cell, rows * (ch + lab) + top), (24, 26, 30))
    d = ImageDraw.Draw(sheet)
    if title:
        d.text((10, 8), title, fill=(230, 230, 230), font=font(22))
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell - 4, ch - 4))
        r, c = divmod(i, cols)
        x, y = c * cell, top + r * (ch + lab)
        sheet.paste(im, (x + (cell - im.width) // 2, y + (ch - im.height) // 2))
        d.text((x + 6, y + ch + 2), os.path.splitext(os.path.basename(p))[0], fill=(200, 200, 200), font=font(15))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print("sheet", out)


def crop_content(im, bg_tol=10, pad=12):
    """Crop a render to its non-background content (background = corner colour)."""
    im = im.convert("RGB")
    bg = im.getpixel((2, 2))
    px = im.load()
    w, h = im.size
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            p = px[x, y]
            if max(abs(p[0] - bg[0]), abs(p[1] - bg[1]), abs(p[2] - bg[2])) > bg_tol:
                xs.append(x)
                ys.append(y)
    if not xs:
        return im
    return im.crop((max(0, min(xs) - pad), max(0, min(ys) - pad), min(w, max(xs) + pad), min(h, max(ys) + pad)))


def compare(render, concept, out, label_l="render", label_r="concept", h=520, crop=True):
    a = Image.open(render).convert("RGB") if isinstance(render, str) else render
    if crop:
        a = crop_content(a)
    b = Image.open(concept).convert("RGB")
    if crop:
        b = crop_content(b, bg_tol=18)
    a = a.resize((int(a.width * h / a.height), h))
    b = b.resize((int(b.width * h / b.height), h))
    sheet = Image.new("RGB", (a.width + b.width + 10, h + 30), (24, 26, 30))
    sheet.paste(a, (0, 30))
    sheet.paste(b, (a.width + 10, 30))
    d = ImageDraw.Draw(sheet)
    d.text((8, 5), label_l, fill=(230, 230, 230), font=font(18))
    d.text((a.width + 18, 5), label_r, fill=(230, 230, 230), font=font(18))
    sheet.save(out)
    print("compare", out)


def lineup(paths, h=420, gap=40, bg=(54, 58, 66)):
    """Side-by-side, bottom-aligned at the SAME scale (renders share lens/res; scale by part size in metres is
    approximated by cropping each render and scaling by its own framing radius ~ crop size)."""
    ims = [crop_content(Image.open(p)) for p in paths if os.path.exists(p)]
    hmax = max(i.height for i in ims)
    k = h / hmax
    ims = [i.resize((int(i.width * k), int(i.height * k))) for i in ims]
    W = sum(i.width for i in ims) + gap * (len(ims) + 1)
    out = Image.new("RGB", (W, h + 2 * gap), bg)
    x = gap
    for i in ims:
        out.paste(i, (x, gap + h - i.height))
        x += i.width + gap
    return out


PARTS = ["grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "bipod", "laser_R", "laser_L", "flashlight_R",
         "flashlight_L", "shield_front"]
VIEWS = ["right", "left", "three_quarter", "front", "back", "top"]
CONCEPT = {"ugl_launcher": "ugl_side_v01.png", "bipod": "bipod_v01.png", "shield_front": "shield_v03.png",
           "laser_R": "laser_light_v01.png", "flashlight_R": "laser_light_v01.png"}
CMP_VIEW = {"ugl_launcher": "right", "bipod": "three_quarter", "shield_front": "front",
            "laser_R": "detail_v-0.9_-0.8_0.3", "flashlight_R": "three_quarter"}


def all_sheets():
    for pid in PARTS:
        d = os.path.join(R, pid)
        alone = [os.path.join(d, f"{pid}_{v}.png") for v in VIEWS]
        extra = sorted(glob.glob(os.path.join(d, f"{pid}_detail_*.png")) +
                       glob.glob(os.path.join(d, f"{pid}_close_*.png")))
        fit = sorted(glob.glob(os.path.join(d, f"{pid}_fit*.png")))
        sight = sorted(glob.glob(os.path.join(d, f"{pid}_sight*.png")))
        opn = sorted(glob.glob(os.path.join(d, f"{pid}_open*.png")) + glob.glob(os.path.join(d, f"{pid}_folded*.png")))
        grid(alone + extra, os.path.join(R, f"sheet_{pid}.png"), cols=3, cell=420, title=f"ATT_{pid}  (alone + close-ups)")
        if fit or sight or opn:
            grid(fit + sight + opn, os.path.join(R, f"sheet_{pid}_fit.png"), cols=4, cell=380,
                 title=f"ATT_{pid}  (test fit on the Mako / Warden exports, sight line, moving parts)")
        if pid in CONCEPT:
            rp = os.path.join(d, f"{pid}_{CMP_VIEW[pid]}.png")
            cp = os.path.join(C, CONCEPT[pid])
            if os.path.exists(rp) and os.path.exists(cp):
                compare(rp, cp, os.path.join(R, f"compare_{pid}.png"), f"ATT_{pid} ({CMP_VIEW[pid]})",
                        "concept " + CONCEPT[pid])
    # grips: lineup of the three right-side renders vs the concept lineup
    gl = lineup([os.path.join(R, g, f"{g}_right.png") for g in ("grip_vertical", "grip_angled", "grip_stub")])
    compare(gl, os.path.join(C, "grips_v01.png"), os.path.join(R, "compare_grips.png"),
            "grip_vertical / grip_angled / grip_stub (right)", "concept grips_v01", crop=False)
    ov = [os.path.join(R, pid, f"{pid}_three_quarter.png") for pid in PARTS]
    grid(ov, os.path.join(R, "sheet_overview.png"), cols=5, cell=360, title="ATT tactical set - three-quarter")
    loadout_sheet()
    review_sheet()
    review_sheet_r2()
    cmp_ = sorted(glob.glob(os.path.join(R, "compare_*.png")))
    stack(cmp_, os.path.join(R, "sheet_compare.png"), width=1400, title="Render vs concept")


def loadout_sheet():
    lo = sorted(glob.glob(os.path.join(R, "loadouts", "*.png")))
    grid(lo, os.path.join(R, "sheet_loadouts.png"), cols=3, cell=640, cell_h=412,
         title="Test-fit loadouts on the real Mako / Warden exports (sockets read from the .glb nodes)")


def pair(a, b, h=380, la="before", lb="after"):
    """Before | after strip at a common height (images are cropped to content first)."""
    ims = []
    for p in (a, b):
        im = crop_content(Image.open(p)) if os.path.exists(p) else Image.new("RGB", (h, h), (60, 20, 20))
        ims.append(im.resize((max(1, int(im.width * h / im.height)), h)))
    out = Image.new("RGB", (ims[0].width + ims[1].width + 12, h + 26), (24, 26, 30))
    out.paste(ims[0], (0, 26))
    out.paste(ims[1], (ims[0].width + 12, 26))
    d = ImageDraw.Draw(out)
    d.text((6, 4), la, fill=(235, 150, 140), font=font(17))
    d.text((ims[0].width + 18, 4), lb, fill=(150, 230, 160), font=font(17))
    return out


def review_sheet():
    """Review-pass-2 fixes: before (09:44 exports, kept in _work/rev2/before) next to the current renders."""
    B = os.path.join(HERE, "_work", "rev2", "before")
    rows = [
        ("1 shield glass, sunlit range, eye at rail top + 57.5 mm (old light-blue veil | dark tint)",
         os.path.join(R, "shield_front", "shield_front_sight_eye_575_oldglass.png"),
         os.path.join(R, "shield_front", "shield_front_sight_eye_575.png")),
        ("2 laser top face: fold-over triangles (black wedge) | clean groove",
         os.path.join(B, "laser_R_top.png"), os.path.join(R, "laser_R", "laser_R_top.png")),
        ("3 laser IR window: plum | neutral dark glass (red dot is the only accent)",
         os.path.join(B, "laser_R_three_quarter.png"), os.path.join(R, "laser_R", "laser_R_three_quarter.png")),
        ("4 bipod folded on the Warden: splay baked in | straight legs, splay node 0, feet swivelled flat",
         os.path.join(B, "bipod_folded_fit_front.png"), os.path.join(R, "bipod", "bipod_folded_fit_front.png")),
        ("5 bipod folded, right side",
         os.path.join(B, "bipod_folded_fit_right.png"), os.path.join(R, "bipod", "bipod_folded_fit_right.png")),
        ("6 UGL on the Mako, front low left: 20-step tube | 24-step tube + 32-step muzzle collar",
         os.path.join(B, "kit_closed_front_low_left.png"),
         os.path.join(R, "ugl_launcher", "ugl_launcher_close_onmako_front_low_left.png")),
        ("7 grip ramp stipple hue",
         os.path.join(B, "grip_angled_under_back.png"), os.path.join(R, "grip_angled", "grip_angled_close_under_back.png")),
    ]
    strips = []
    f19 = font(19)
    for label, a, b in rows:
        st = pair(a, b)
        lw = int(f19.getlength(label)) + 14 if hasattr(f19, "getlength") else st.width
        canvas = Image.new("RGB", (max(st.width, lw), st.height + 30), (24, 26, 30))
        canvas.paste(st, (0, 30))
        ImageDraw.Draw(canvas).text((6, 6), label, fill=(230, 230, 230), font=f19)
        strips.append(canvas)
    W = max(s_.width for s_ in strips)
    sheet = Image.new("RGB", (W, 44 + sum(s_.height + 10 for s_ in strips)), (24, 26, 30))
    ImageDraw.Draw(sheet).text((10, 10), "ATT tactical: review pass 2 fixes (left = 09:44 exports, right = now)",
                               fill=(240, 240, 240), font=font(22))
    y = 44
    for s_ in strips:
        sheet.paste(s_, (0, y))
        y += s_.height + 10
    out = os.path.join(R, "sheet_review_fixes.png")
    sheet.save(out)
    print("sheet", out)


RAILFIT_FACE = {"bipod_WARDEN": "Under", "grip_vertical_MAKO": "Under", "ugl_launcher_MAKO": "Under",
                "laser_R_MAKO": "Side_R", "laser_R_WARDEN": "Side_R", "flashlight_L_WARDEN": "Side_L",
                "shield_front_MAKO": "Shield"}


def railfit_corners(path, face, half=55, scale=3):
    """The two rail-top corners of a render_railfit.py section (1000 px ortho, 20 px per mm, centred 4 mm off the rail
    face on the part side), cropped and enlarged side by side."""
    im = Image.open(path).convert("RGB") if os.path.exists(path) else Image.new("RGB", (1000, 1000), (60, 20, 20))
    if face == "Under":
        pts = [(290, 420), (710, 420)]
    elif face == "Shield":
        pts = [(290, 580), (710, 580)]
    elif face == "Side_R":
        pts = [(580, 290), (580, 710)]
    else:
        pts = [(420, 290), (420, 710)]
    s = 2 * half * scale
    out = Image.new("RGB", (2 * s + 6, s), (24, 26, 30))
    for k, (x, y) in enumerate(pts):
        out.paste(im.crop((x - half, y - half, x + half, y + half)).resize((s, s), Image.NEAREST), (k * (s + 6), 0))
    return out


def review_sheet_r2():
    """Review round 2 (critique_latest.json + the Warden review's bipod note): clamp/rail sections before (13:32
    exports, kept in _work/rev4/before) and after, plus the re-render on the re-exported Mako."""
    B = os.path.join(HERE, "_work", "rev4", "before")
    f19, f16 = font(19), font(16)
    blocks = []

    def labelled(img, text, col=(230, 230, 230), f=f16):
        c = Image.new("RGB", (img.width, img.height + 24), (24, 26, 30))
        c.paste(img, (0, 24))
        ImageDraw.Draw(c).text((4, 3), text, fill=col, font=f)
        return c

    def hrow(ims, gap=16):
        W = sum(i.width for i in ims) + gap * (len(ims) - 1)
        H = max(i.height for i in ims)
        r = Image.new("RGB", (W, H), (24, 26, 30))
        x = 0
        for i in ims:
            r.paste(i, (x, 0))
            x += i.width + gap
        return r

    # A: rail-top corners, before | after, per gun rail type
    rows = []
    for key in ("bipod_WARDEN", "laser_R_WARDEN", "grip_vertical_MAKO", "shield_front_MAKO"):
        face = RAILFIT_FACE[key]
        a = labelled(railfit_corners(os.path.join(B, "railfit", key + ".png"), face, scale=2), "before",
                     (235, 150, 140))
        b = labelled(railfit_corners(os.path.join(R, "railfit", key + ".png"), face, scale=2), "after",
                     (150, 230, 160))
        rows.append(labelled(hrow([a, b], 24), key.replace("_", " ", 1), f=f19))
    blocks.append(("1 clamp channel vs the real rails: true sections through a rail tooth (orange rail, blue part, dark "
                   "= clearance). The old 1.5 mm channel chamfer bit into the rails' top corners (Warden 0.85 mm, "
                   "Mako 0.42 mm); now square corners with 0.3 mm clearance", rows))
    # B: all sections after
    secs = [labelled(Image.open(p).convert("RGB").resize((300, 300)), os.path.splitext(os.path.basename(p))[0])
            for p in sorted(glob.glob(os.path.join(R, "railfit", "*.png")))]
    blocks.append(("2 every clamp on every rail it fits (after, 50 mm wide sections)",
                   [hrow(secs[i:i + 4]) for i in range(0, len(secs), 4)]))
    # C: re-render on the re-exported Mako (Under socket now z 0.0075 in the glb too) + framing of end-on loadouts
    pairs_ = [("mako_loadout_A_left.png", os.path.join(R, "loadouts", "mako_loadout_A_left.png")),
              ("ugl_launcher_fit_right.png", os.path.join(R, "ugl_launcher", "ugl_launcher_fit_right.png")),
              ("warden_bipod_front.png", os.path.join(R, "loadouts", "warden_bipod_front.png")),
              ("mako_loadout_A_front.png", os.path.join(R, "loadouts", "mako_loadout_A_front.png"))]
    rows = [pair(os.path.join(B, "renders", a), b, h=300, la="before (13:50, old Mako export)", lb="after")
            for a, b in pairs_]
    blocks.append(("3 re-rendered on the re-exported Mako (14:02) and the Warden; end-on loadout views framed on the gun",
                   [hrow(rows[:2]), hrow(rows[2:])]))
    strips = []
    for title, ims in blocks:
        W = max(max(i.width for i in ims), int(f19.getlength(title)) + 14 if hasattr(f19, "getlength") else 0)
        H = 32 + sum(i.height + 10 for i in ims)
        c = Image.new("RGB", (W, H), (24, 26, 30))
        ImageDraw.Draw(c).text((6, 6), title, fill=(240, 240, 240), font=f19)
        y = 32
        for i in ims:
            c.paste(i, (0, y))
            y += i.height + 10
        strips.append(c)
    W = max(s_.width for s_ in strips)
    sheet = Image.new("RGB", (W, 44 + sum(s_.height + 16 for s_ in strips)), (24, 26, 30))
    ImageDraw.Draw(sheet).text((10, 10), "ATT tactical: review round 2 fixes", fill=(240, 240, 240), font=font(22))
    y = 44
    for s_ in strips:
        sheet.paste(s_, (0, y))
        y += s_.height + 16
    out = os.path.join(R, "sheet_review_fixes_r2.png")
    sheet.save(out)
    print("sheet", out)


def stack(paths, out, width=1400, title=None, gap=14):
    """Stack images vertically at their natural aspect (for wide comparison strips)."""
    ims = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((width, int(im.height * width / im.width))))
    top = 40 if title else 0
    sheet = Image.new("RGB", (width, top + sum(i.height + gap for i in ims)), (24, 26, 30))
    if title:
        ImageDraw.Draw(sheet).text((10, 8), title, fill=(230, 230, 230), font=font(22))
    y = top
    for i in ims:
        sheet.paste(i, (0, y))
        y += i.height + gap
    sheet.save(out)
    print("stack", out)


if __name__ == "__main__":
    if sys.argv[1] == "grid":
        grid(sys.argv[4:], sys.argv[2], cols=int(sys.argv[3]), cell=400)
    elif sys.argv[1] == "all":
        all_sheets()
    elif sys.argv[1] == "loadouts":
        loadout_sheet()
