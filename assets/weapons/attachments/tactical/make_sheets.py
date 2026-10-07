"""Contact sheets + concept comparisons for the ATT tactical set (system python + PIL).

  python make_sheets.py grid <out.png> <cols> <img> [<img> ...]     ad-hoc labelled grid
  python make_sheets.py all                                          per-part sheets + comparisons + overview
"""
import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
R = os.path.join(HERE, "renders")
C = os.path.join(HERE, "concepts")


def font(sz):
    for f in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def grid(paths, out, cols=3, cell=420, title=None):
    paths = [p for p in paths if os.path.exists(p)]
    if not paths:
        print("no images for", out)
        return
    rows = (len(paths) + cols - 1) // cols
    top = 40 if title else 0
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 22) + top), (24, 26, 30))
    d = ImageDraw.Draw(sheet)
    if title:
        d.text((10, 8), title, fill=(230, 230, 230), font=font(22))
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell, cell))
        r, c = divmod(i, cols)
        x, y = c * cell, top + r * (cell + 22)
        sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        d.text((x + 6, y + cell + 2), os.path.splitext(os.path.basename(p))[0], fill=(200, 200, 200), font=font(15))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print("sheet", out)


def compare(render, concept, out, label_l="render", label_r="concept", h=520):
    a = Image.open(render).convert("RGB")
    b = Image.open(concept).convert("RGB")
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


PARTS = ["grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "bipod", "laser_R", "laser_L", "flashlight_R",
         "flashlight_L", "shield_front"]
VIEWS = ["right", "left", "three_quarter", "front", "back", "top"]
CONCEPT = {"grip_vertical": "grips_v01.png", "grip_angled": "grips_v01.png", "grip_stub": "grips_v01.png",
           "ugl_launcher": "ugl_side_v01.png", "bipod": "bipod_v01.png", "laser_R": "laser_light_v01.png",
           "flashlight_R": "laser_light_v01.png", "shield_front": "shield_v03.png"}
CMP_VIEW = {"grip_vertical": "right", "grip_angled": "right", "grip_stub": "right", "ugl_launcher": "right",
            "bipod": "three_quarter", "laser_R": "three_quarter", "flashlight_R": "three_quarter",
            "shield_front": "three_quarter"}


def all_sheets():
    for pid in PARTS:
        d = os.path.join(R, pid)
        alone = [os.path.join(d, f"{pid}_{v}.png") for v in VIEWS]
        extra = sorted(glob.glob(os.path.join(d, f"{pid}_detail_*.png")))
        fit = sorted(glob.glob(os.path.join(d, f"{pid}_fit*.png")))
        sight = sorted(glob.glob(os.path.join(d, f"{pid}_sight*.png")))
        grid(alone + extra, os.path.join(R, f"sheet_{pid}.png"), cols=4, cell=380, title=f"ATT_{pid}  (alone)")
        if fit or sight:
            grid(fit + sight, os.path.join(R, f"sheet_{pid}_fit.png"), cols=4, cell=380,
                 title=f"ATT_{pid}  (test fit on proxy)")
        if pid in CONCEPT:
            rp = os.path.join(d, f"{pid}_{CMP_VIEW[pid]}.png")
            cp = os.path.join(C, CONCEPT[pid])
            if os.path.exists(rp) and os.path.exists(cp):
                compare(rp, cp, os.path.join(R, f"compare_{pid}.png"), f"ATT_{pid} ({CMP_VIEW[pid]})",
                        "concept " + CONCEPT[pid])
    ov = [os.path.join(R, pid, f"{pid}_three_quarter.png") for pid in PARTS]
    grid(ov, os.path.join(R, "sheet_overview.png"), cols=5, cell=360, title="ATT tactical set - three-quarter")
    lo = sorted(glob.glob(os.path.join(R, "loadouts", "*.png")))
    grid(lo, os.path.join(R, "sheet_loadouts.png"), cols=3, cell=560, title="Test-fit loadouts on proxies")


if __name__ == "__main__":
    if sys.argv[1] == "grid":
        grid(sys.argv[4:], sys.argv[2], cols=int(sys.argv[3]), cell=400)
    elif sys.argv[1] == "all":
        all_sheets()
