"""Side-by-side sheets: concept art (design/maps/tdm/concepts/_candidates/A_showhome_*) vs the collision preview.

    python compare_concept.py      (after collision_preview.py)   -> renders/compare_concept_*.png
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
CON = os.path.join(ROOT, "design", "maps", "tdm", "concepts", "_candidates")
R = os.path.join(HERE, "renders")

PAIRS = [
    ("aerial", [("A_showhome_aerial_s11.png", "collision_aerial_s11.png"),
                ("A_showhome_aerial_s12.png", "collision_aerial_s12.png")]),
    ("ground", [("A_showhome_ground_s11.png", "collision_ground_street.png"),
                ("A_showhome_ground_s12.png", "collision_ground_lawn.png")]),
]


def font(sz):
    for f in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    W = 960
    for name, pairs in PAIRS:
        tiles = []
        for c, r in pairs:
            a = Image.open(os.path.join(CON, c)).convert("RGB")
            b = Image.open(os.path.join(R, r)).convert("RGB")
            a = a.resize((W, int(a.height * W / a.width)))
            b = b.resize((W, int(b.height * W / b.width)))
            tiles.append((a, c, b, r))
        h = sum(max(a.height, b.height) + 34 for a, _, b, _ in tiles)
        sheet = Image.new("RGB", (2 * W + 10, h), (24, 24, 28))
        d = ImageDraw.Draw(sheet)
        f = font(20)
        y = 0
        for a, cn, b, rn in tiles:
            d.text((8, y + 6), "CONCEPT  " + cn, fill=(235, 235, 235), font=f)
            d.text((W + 18, y + 6), "GAME COLLISION  " + rn, fill=(235, 235, 235), font=f)
            sheet.paste(a, (0, y + 34))
            sheet.paste(b, (W + 10, y + 34))
            y += max(a.height, b.height) + 34
        p = os.path.join(R, f"compare_concept_{name}.png")
        sheet.save(p)
        print("wrote", p)


if __name__ == "__main__":
    main()
