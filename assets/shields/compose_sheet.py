"""Compose labelled review sheets from raw renders (system Python + PIL; halo_render.py calls it).

  python compose_sheet.py spec.json

spec = {"out": "sheet.png", "bg": [14, 15, 18],
        "blocks": [{"title": str, "subtitle": str,
                    "panels": [{"img": "raw.png", "scale": 5, "caption": str}, ...]}, ...],
        "notes": ["footer line", ...]}
Panels in a block sit side by side (nearest-neighbour upscale by `scale`, so true-pixel renders stay honest);
blocks stack vertically.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont


def font(size, bold=False):
    names = (["segoeuib.ttf", "arialbd.ttf"] if bold else []) + ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    for n in names:
        for d in ("", os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")):
            try:
                return ImageFont.truetype(os.path.join(d, n) if d else n, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def main(spec_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    bg = tuple(spec.get("bg", (14, 15, 18)))
    pad, gap = 14, 10
    f_title, f_sub, f_cap, f_note = font(26, True), font(17), font(17), font(17)
    rows = []
    for b in spec["blocks"]:
        ims = []
        for p in b["panels"]:
            im = Image.open(p["img"]).convert("RGB")
            s = p.get("scale", 1)
            if s != 1:
                im = im.resize((round(im.width * s), round(im.height * s)), Image.NEAREST if s > 1 else Image.LANCZOS)
            ims.append((im, p.get("caption", "")))
        rows.append((b, ims))
    width = max(sum(im.width for im, _ in ims) + gap * (len(ims) - 1) for _, ims in rows) + 2 * pad
    height = pad
    for b, ims in rows:
        height += 34 + (24 if b.get("subtitle") else 0) + max(im.height for im, _ in ims)
        height += 24 if any(c for _, c in ims) else 0
        height += pad
    height += 24 * len(spec.get("notes", [])) + pad
    sheet = Image.new("RGB", (width, height), bg)
    dr = ImageDraw.Draw(sheet)
    y = pad
    for b, ims in rows:
        dr.text((pad, y), b["title"], fill=(235, 237, 242), font=f_title)
        y += 34
        if b.get("subtitle"):
            dr.text((pad, y), b["subtitle"], fill=(150, 156, 168), font=f_sub)
            y += 24
        x = pad
        for im, cap in ims:
            sheet.paste(im, (x, y))
            if cap:
                dr.text((x, y + im.height + 2), cap, fill=(150, 156, 168), font=f_cap)
            x += im.width + gap
        y += max(im.height for im, _ in ims) + (24 if any(c for _, c in ims) else 0) + pad
    for line in spec.get("notes", []):
        dr.text((pad, y), line, fill=(150, 156, 168), font=f_note)
        y += 24
    sheet.save(spec["out"])
    print("COMPOSED", spec["out"], sheet.size)


if __name__ == "__main__":
    main(sys.argv[1])
