"""Make reproducible concept/reference comparisons for the upgraded house kit. Run with system Python."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[3]
SH = ROOT / "assets/maps/showhome"
R = SH / "kit/renders"
OUT = SH / "textures/v2/_preview"
C = ROOT / "design/maps/tdm/concepts/_candidates"
OUT.mkdir(parents=True, exist_ok=True)
try:
    FONT = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 19)
except OSError:
    FONT = ImageFont.load_default()


def sheet(name, panels, width=560, height=480):
    image = Image.new("RGB", (len(panels) * width, height + 38), (239, 234, 221))
    d = ImageDraw.Draw(image)
    for i, (label, path, crop) in enumerate(panels):
        src = Image.open(path).convert("RGB")
        if crop:
            src = src.crop(crop)
        tile = ImageOps.contain(src, (width - 16, height - 16), Image.Resampling.LANCZOS)
        image.paste(tile, (i * width + (width - tile.width) // 2, 38 + (height - tile.height) // 2))
        d.text((i * width + 12, 9), label, font=FONT, fill=(66, 67, 68))
    path = OUT / name
    image.save(path)
    return path


def main():
    comparisons = []
    reference = ROOT / "art/briefs/refs/painted_cladding_ref.png"
    for team in ("sage", "clay"):
        crop = (0, 90, 340, 535) if team == "sage" else (1160, 90, 1536, 535)
        for kind, distance in ((kind, distance) for kind in ("wall", "sunlit_wall") for distance in (1, 5)):
            raw = R / f"houses_{team}_{kind}_{distance}m.png"
            if raw.exists():
                comparisons.append(sheet(f"house_{team}_{kind}_{distance}m_compare.png", [
                    ("Painted cladding reference", reference, None),
                    (f"{team.title()} concept crop", C / "A_showhome_ground_s11.png", crop),
                    (f"{team.title()} {kind.replace('_', ' ')}: {distance} m", raw, None),
                ], height=600))
        for view in ("close_roof", "roof_upper_window", "roof_terrace", "close_corner", "close_terrace", "street", "aerial"):
            raw = R / f"houses_{team}_{view}.png"
            if not raw.exists():
                continue
            if view == "roof_upper_window":
                concept, crop = "A_showhome_ground_s11.png", (0, 135, 420, 365) if team == "sage" else (1115, 145, 1536, 375)
            elif "roof" in view:
                concept, crop = "A_showhome_aerial_s12.png", (185, 95, 755, 390) if team == "sage" else (833, 187, 1326, 498)
            elif view == "close_corner":
                concept, crop = "A_showhome_aerial_s12.png", (345, 350, 560, 605) if team == "sage" else (875, 340, 1120, 655)
            elif view == "close_terrace":
                concept, crop = "A_showhome_aerial_s11.png", (275, 392, 563, 570) if team == "sage" else (1015, 392, 1288, 570)
            elif view == "street":
                concept = "A_showhome_ground_s11.png"
                crop = (0, 0, 420, 635) if team == "sage" else (1120, 0, 1536, 635)
            else:
                concept, crop = "A_showhome_aerial_s12.png", None
            comparisons.append(sheet(f"house_{team}_{view}_compare.png", [
                ("Concept: " + concept.removesuffix(".png"), C / concept, crop),
                (team.title() + ": " + view.replace("_", " "), raw, None),
            ]))
    for view, concept in (("concept_aerial_s11", "A_showhome_aerial_s11.png"),
                          ("concept_aerial_s12", "A_showhome_aerial_s12.png"),
                          ("concept_ground_street", "A_showhome_ground_s11.png")):
        raw = R / f"houses_{view}.png"
        if raw.exists():
            comparisons.append(sheet(f"house_{view}_compare.png", [
                ("Concept", C / concept, None), ("Upgraded house kit in map", raw, None),
            ], width=720, height=405))
    thumb_w = 840
    thumb_h = 310
    rows = (len(comparisons) + 1) // 2
    contact = Image.new("RGB", (thumb_w * 2, rows * thumb_h), (239, 234, 221))
    for i, path in enumerate(comparisons):
        tile = ImageOps.contain(Image.open(path), (thumb_w, thumb_h), Image.Resampling.LANCZOS)
        contact.paste(tile, ((i % 2) * thumb_w, (i // 2) * thumb_h))
    contact.save(OUT / "houses_contact_sheet.png")
    print(f"Wrote {len(comparisons)} paired comparisons and houses_contact_sheet.png to {OUT}")


if __name__ == "__main__":
    main()
