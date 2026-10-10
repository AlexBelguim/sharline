"""Small helper: tile PNGs into a labelled sheet. usage: python r2_sheet.py out.png cols w h img1 img2 ..."""
import sys, os
from PIL import Image, ImageDraw, ImageFont
out, cols, w, h = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
paths = sys.argv[5:]
rows = (len(paths) + cols - 1) // cols
sheet = Image.new("RGB", (cols * w, rows * (h + 28)), (20, 20, 24))
d = ImageDraw.Draw(sheet)
try:
    f = ImageFont.truetype("arial.ttf", 20)
except Exception:
    f = ImageFont.load_default()
for i, p in enumerate(paths):
    im = Image.open(p).convert("RGB")
    im.thumbnail((w, h))
    x, y = (i % cols) * w, (i // cols) * (h + 28)
    sheet.paste(im, (x + (w - im.width) // 2, y + 28))
    d.text((x + 6, y + 4), os.path.splitext(os.path.basename(p))[0], fill=(235, 235, 235), font=f)
sheet.save(out)
print("sheet", out, sheet.size)
