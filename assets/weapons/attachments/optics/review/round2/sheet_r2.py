"""Labelled contact sheet (system python + PIL).
python sheet_r2.py out.png cols cell_px file1 file2 ...   (files may be globs)"""
import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

out, cols, cell = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
files = []
for a in sys.argv[4:]:
    files += sorted(glob.glob(a)) or [a]
rows = (len(files) + cols - 1) // cols
W = cell
sheet = Image.new("RGB", (cols * W, rows * (W + 22)), (20, 21, 24))
d = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("arial.ttf", 14)
except Exception:
    font = ImageFont.load_default()
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB")
    im.thumbnail((W, W), Image.NEAREST if im.size[0] <= 128 else Image.LANCZOS)
    if im.size[0] <= 128:
        im = im.resize((W, int(W * im.size[1] / im.size[0])), Image.NEAREST)
    r, c = divmod(i, cols)
    x, y = c * W, r * (W + 22)
    d.text((x + 4, y + 3), os.path.basename(f)[:60], fill=(230, 230, 230), font=font)
    sheet.paste(im, (x + (W - im.size[0]) // 2, y + 22 + (W - im.size[1]) // 2))
sheet.save(out)
print("wrote", out, sheet.size)
