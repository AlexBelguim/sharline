"""Contact sheets of the depth screenshots (game/target/shots/depth): before / after pairs side by side.

  python sheet.py OUT.png view:suffix [view:suffix ...] [--cols N] [--w W] [--crop x0,y0,x1,y1]

Each cell is labelled with its file name; --crop cuts the same region from every shot first (a close-up).
"""
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "game", "target", "shots", "depth"))


def main():
    args = sys.argv[1:]
    out = args.pop(0)
    cols, width, crop = 2, 800, None
    items = []
    while args:
        a = args.pop(0)
        if a == "--cols":
            cols = int(args.pop(0))
        elif a == "--w":
            width = int(args.pop(0))
        elif a == "--crop":
            crop = tuple(int(v) for v in args.pop(0).split(","))
        else:
            items.append(a)
    ims = []
    for it in items:
        view, suffix = it.split(":")
        im = Image.open(os.path.join(SHOTS, f"{view}_{suffix}.png")).convert("RGB")
        if crop:
            im = im.crop(crop)
        h = round(im.height * width / im.width)
        ims.append((f"{view}_{suffix}", im.resize((width, h), Image.LANCZOS)))
    rows = (len(ims) + cols - 1) // cols
    ch = max(i.height for _, i in ims) + 18
    sheet = Image.new("RGB", (cols * width, rows * ch), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    for k, (name, im) in enumerate(ims):
        r, c = divmod(k, cols)
        sheet.paste(im, (c * width, r * ch + 18))
        d.text((c * width + 6, r * ch + 3), name, fill=(235, 235, 235))
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
