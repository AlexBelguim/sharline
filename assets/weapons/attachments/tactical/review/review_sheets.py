"""Reviewer contact sheets (system python + PIL).  python review_sheets.py [sil|wire|cycles|all]"""
import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

R = r"F:/git/val etf/assets/weapons/attachments/tactical/review/renders"
PARTS = ["grip_vertical", "grip_angled", "grip_stub", "ugl_launcher", "bipod", "laser_R", "laser_L",
         "flashlight_R", "flashlight_L", "shield_front"]
try:
    FONT = ImageFont.truetype("arial.ttf", 16)
    FONT_B = ImageFont.truetype("arial.ttf", 22)
except OSError:
    FONT = FONT_B = ImageFont.load_default()


def grid(cells, cols, cell_w, cell_h, title, out, label_h=24, bg=(24, 26, 30), scale_nearest=None):
    rows = (len(cells) + cols - 1) // cols
    W = cols * cell_w
    H = 40 + rows * (cell_h + label_h)
    sheet = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(sheet)
    d.text((10, 8), title, fill=(235, 235, 235), font=FONT_B)
    for i, (path, label) in enumerate(cells):
        r, c = divmod(i, cols)
        x, y = c * cell_w, 40 + r * (cell_h + label_h)
        if path and os.path.exists(path):
            im = Image.open(path).convert("RGB")
            if scale_nearest:
                im = im.resize((im.width * scale_nearest, im.height * scale_nearest), Image.NEAREST)
            im.thumbnail((cell_w - 6, cell_h - 6), Image.LANCZOS if not scale_nearest else Image.NEAREST)
            sheet.paste(im, (x + (cell_w - im.width) // 2, y + (cell_h - im.height) // 2))
        d.text((x + 6, y + cell_h + 3), label, fill=(210, 210, 210), font=FONT)
    sheet.save(out)
    print("sheet", out)


what = sys.argv[1] if len(sys.argv) > 1 else "all"
if what in ("sil", "all"):
    cells = []
    for pid in PARTS:
        for v in ("side", "tq", "front"):
            cells.append((os.path.join(R, "sil", f"{pid}_{v}_64.png"), f"{pid} {v}"))
    grid(cells, 6, 270, 270, "64 px silhouettes (x4 nearest upscale) - parts alone", os.path.join(R, "..",
         "sheet_silhouettes_parts.png"), scale_nearest=4)
    cells = []
    for f in sorted(glob.glob(os.path.join(R, "sil", "ctx_*_left_160.png"))):
        cells.append((f, os.path.basename(f).replace("ctx_", "").replace("_left_160.png", "")))
    for f in sorted(glob.glob(os.path.join(R, "sil", "ctx_*_front_160.png"))):
        cells.append((f, os.path.basename(f).replace("ctx_", "").replace("_160.png", "")))
    grid(cells, 4, 480, 300, "Gun context silhouettes, 160 px wide (x3 nearest) - third-person read at range",
         os.path.join(R, "..", "sheet_silhouettes_context.png"), scale_nearest=3)
if what in ("wire", "all"):
    cells = []
    for pid in PARTS:
        for v in ("right", "tq", "back_low"):
            cells.append((os.path.join(R, "wire", f"{pid}_wire_{v}.png"), f"{pid} {v}"))
    grid(cells, 6, 420, 420, "Wireframe overlay (exported .glb)", os.path.join(R, "..", "sheet_wireframe.png"))
if what in ("cycles", "all"):
    for sub, cols, cw, ch in (("fp", 2, 900, 560), ("ads", 3, 640, 380), ("clash", 3, 640, 450),
                              ("bipod", 3, 640, 420), ("detail", 5, 420, 420)):
        fs = sorted(glob.glob(os.path.join(R, sub, "*.png")))
        if fs:
            grid([(f, os.path.basename(f)[:-4]) for f in fs], cols, cw, ch, f"Reviewer renders - {sub}",
                 os.path.join(R, "..", f"sheet_{sub}.png"))
