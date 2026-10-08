"""Side-by-side crops of library textures (read-only) for look-dev: python peek.py OUT.png name[:x0,y0,size] ..."""
import os
import sys

from PIL import Image, ImageDraw

LIB = r"F:\git\val etf\assets\maps\showhome\textures"
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    out, items = sys.argv[1], sys.argv[2:]
    cell = 400
    sheet = Image.new("RGB", (cell * len(items), cell + 16), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    for i, it in enumerate(items):
        name, _, crop = it.partition(":")
        path = os.path.join(LIB, name + ".png")
        for sub in ("out", "raw"):
            if not os.path.exists(path):
                path = os.path.join(HERE, sub, name + ".png")
        im = Image.open(path)
        if im.mode in ("I;16", "I"):
            im = im.point(lambda v: v / 256).convert("L")
        im = im.convert("RGB")
        if crop:
            x0, y0, s = (int(v) for v in crop.split(","))
            im = im.crop((x0, y0, x0 + s, y0 + s))
        sheet.paste(im.resize((cell, cell), Image.NEAREST if crop else Image.LANCZOS), (i * cell, 16))
        d.text((i * cell + 4, 2), it, fill=(230, 230, 230))
    sheet.save(out)


if __name__ == "__main__":
    main()
