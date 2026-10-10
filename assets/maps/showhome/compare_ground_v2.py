"""Pair each actual Job 2 ground render with its matching concept crop and the in-game box reference."""
from pathlib import Path
import json
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONCEPTS = ROOT / "design/maps/tdm/concepts/_candidates"
OLD = ROOT / "art/briefs/refs/ingame_today_box_roof.png"


def font(size):
    for name in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def fitted(canvas, im, rect):
    x, y, w, h = rect
    im = ImageOps.contain(im.convert("RGB"), (w, h), Image.Resampling.LANCZOS)
    canvas.paste(im, (x + (w - im.width) // 2, y + (h - im.height) // 2))


def pair(tile, out):
    # Give the actual render enough room to judge both relief and blending at normal player height.
    width, height, header, footer = 780, 500, 42, 72
    reference_width = 360
    sheet = Image.new("RGB", (width + 2 * reference_width, header + height + footer), (239, 234, 221))
    dr = ImageDraw.Draw(sheet)
    dr.text((16, 10), tile["label"] + " — eye 1.6 m", font=font(20), fill=(59, 63, 65))
    dr.text((width + 14, 11), "Concept edge / palette crop", font=font(17), fill=(59, 63, 65))
    dr.text((width + reference_width + 14, 11), "In-game today reference", font=font(17), fill=(59, 63, 65))
    fitted(sheet, Image.open(tile["path"]), (8, header, width - 16, height))
    concept = Image.open(CONCEPTS / tile["concept"])
    c = tile["crop"]
    rect = tuple(round(v * (concept.width if i % 2 == 0 else concept.height)) for i, v in enumerate(c))
    fitted(sheet, concept.crop(rect), (width + 8, header, reference_width - 16, height))
    fitted(sheet, Image.open(OLD), (width + reference_width + 8, header, reference_width - 16, height))
    dr.text((16, header + height + 8), tile["detail"], font=font(17), fill=(75, 79, 81))
    dr.text((16, header + height + 36), "Actual houses + ground + placed props GLBs; documented RGBA / height blend restored for look-dev.",
            font=font(14), fill=(92, 94, 96))
    path = out / (tile["name"] + "_compare.png")
    sheet.save(path)
    return path, dict(render=tile["path"], concept=str(CONCEPTS / tile["concept"]), crop_normalized=c,
                      crop_pixels=rect, in_game_reference=str(OLD), comparison=str(path))


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "kit/renders/ground/v2/render_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    out = path.parent
    records, images = [], []
    for tile in manifest["tiles"]:
        image, record = pair(tile, out)
        images.append(image)
        records.append(record)
    tw = 1500
    th = 614
    contact = Image.new("RGB", (tw, th * len(images) + 48), (239, 234, 221))
    dr = ImageDraw.Draw(contact)
    dr.text((16, 11), "SHOWHOME — ground transitions: actual render / concept crop / in-game today", font=font(23), fill=(55, 61, 63))
    for i, path in enumerate(images):
        fitted(contact, Image.open(path), (0, 48 + i * th, tw, th))
    contact.save(out / "contact_sheet.png")
    (out / "concept_crops.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    print("Wrote", len(images), "ground triptych comparisons and contact_sheet.png to", out)


if __name__ == "__main__":
    main()
