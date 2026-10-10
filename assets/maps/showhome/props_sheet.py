"""Contact sheet for the Showhome props kit (system Python + PIL; called by build_props.py).

  python props_sheet.py <renders/props/_tiles.json>
Lays out every prop tile with its name, category, size and triangle count.
"""
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

CAT_COL = {"matched": (64, 160, 120), "detail": (200, 160, 60), "free": (110, 140, 200), "backdrop": (170, 110, 190)}
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def concept_crop(name):
    """Matching original concept region for each reusable prop category; keep reference pixels unpainted."""
    aerial = "A_showhome_aerial_s12.png"
    street = "A_showhome_ground_s11.png"
    if "Mover" in name or "KerbPod" in name or "Car" in name:
        fn, box = street, (0.38, 0.43, 0.60, 0.73)
    elif any(x in name for x in ("Box", "Crate", "Armchair", "Sofa")):
        fn, box = street, (0.52, 0.57, 0.68, 0.76)
    elif "Fence" in name:
        fn, box = street, (0.03, 0.58, 0.26, 0.76)
    elif "Hedge" in name or "Arbour" in name:
        fn, box = aerial, (0.06, 0.37, 0.23, 0.70)
    elif "Pylon" in name or "Wire" in name or "Zipline" in name:
        fn, box = street, (0.30, 0.05, 0.43, 0.72)
    elif "Greenhouse" in name:
        fn, box = aerial, (0.72, 0.63, 0.85, 0.88)
    elif "Shed" in name or "Bin" in name:
        fn, box = aerial, (0.06, 0.39, 0.19, 0.64)
    elif "Studio" in name or "Office" in name or "Hub" in name:
        fn, box = aerial, (0.49, 0.24, 0.71, 0.46)
    elif any(x in name for x in ("Block", "Cement", "Rebar", "Pallet", "Mound", "Cone", "Barrier", "Rock", "Pebble")):
        fn, box = aerial, (0.66, 0.0, 1.0, 0.24)
    else:
        fn, box = street, (0.0, 0.26, 0.27, 0.58)
    path = os.path.join(ROOT, "design/maps/tdm/concepts/_candidates", fn)
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = tuple(round(v * (w if i % 2 == 0 else h)) for i, v in enumerate(box))
    return im.crop(px), dict(concept=path, crop_normalized=box)


def comparison_sheet(d, tw=240, cols=4):
    tiles = d["tiles"]
    outdir = os.path.dirname(d["out"])
    cols = min(cols, len(tiles))
    cellw, cellh = tw * 2, tw + 52
    sheet = Image.new("RGB", (cols * cellw, math.ceil(len(tiles) / cols) * cellh + 40), (27, 29, 32))
    dr = ImageDraw.Draw(sheet)
    dr.text((10, 8), "SHOWHOME PROPS — render / matching concept crop", font=font(19), fill=(235, 230, 220))
    crops = []
    for i, t in enumerate(tiles):
        ref, md = concept_crop(t["name"])
        render = Image.open(t["path"]).convert("RGB")
        # Letterbox each comparison instead of stretching the object or the concept.
        pair = Image.new("RGB", (2 * tw, tw + 52), (34, 35, 38))
        pd = ImageDraw.Draw(pair)
        for j, im in enumerate((render, ref)):
            im.thumbnail((tw, tw), Image.Resampling.LANCZOS)
            pair.paste(im, (j * tw + (tw - im.width) // 2, (tw - im.height) // 2))
        pd.text((8, tw + 3), t["name"] + " | " + str(t["tris"]) + " tris", font=font(14), fill=(234, 229, 218))
        pd.text((tw + 8, tw + 26), "Concept crop (collision governs form)", font=font(11), fill=(168, 171, 177))
        pair.save(os.path.join(outdir, "compare_" + t["name"].replace(" ", "_") + ".png"))
        x, y = (i % cols) * cellw, 40 + (i // cols) * cellh
        sheet.paste(pair, (x, y))
        crops.append(dict(render=t["path"], **md))
    base = os.path.splitext(os.path.basename(d["out"]))[0]
    path = os.path.join(outdir, base + "_concept_compare.png")
    sheet.save(path)
    json.dump(crops, open(os.path.join(outdir, base + "_concept_crops.json"), "w"), indent=2)
    print("comparison", path)


def font(sz):
    for f in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def main(man):
    d = json.load(open(man))
    tiles = d["tiles"]
    if not tiles:
        return
    tw = d.get("tw", 300)
    lab = 46
    cols = min(d.get("cols", 8), max(1, len(tiles)))
    rows = math.ceil(len(tiles) / cols)
    w0, h0 = Image.open(tiles[0]["path"]).size
    th = round(tw * h0 / w0)
    W, H = cols * tw, rows * (th + lab) + 40
    sheet = Image.new("RGB", (W, H), (24, 25, 29))
    dr = ImageDraw.Draw(sheet)
    f1, f2, f0 = font(15), font(12), font(20)
    dr.text((10, 8), "Showhome props kit  -  green: on collision brush, yellow: small in-map detail, "
                     "blue: free (out of bounds), violet: backdrop", fill=(220, 220, 220), font=f0)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        x, y = c * tw, 40 + r * (th + lab)
        im = Image.open(t["path"]).convert("RGB").resize((tw, th), Image.LANCZOS)
        sheet.paste(im, (x, y))
        col = CAT_COL.get(t["cat"], (150, 150, 150))
        dr.rectangle((x, y + th, x + tw - 1, y + th + lab - 1), fill=(34, 35, 40))
        dr.rectangle((x, y + th, x + 5, y + th + lab - 1), fill=col)
        dr.text((x + 10, y + th + 4), t["name"], fill=(235, 235, 235), font=f1)
        s = t["size"]
        dr.text((x + 10, y + th + 25), f"{s[0]:.2f} x {s[1]:.2f} x {s[2]:.2f} m   {t['tris']} tris",
                fill=(170, 170, 175), font=f2)
    sheet.save(d["out"])
    print("sheet", d["out"])
    comparison_sheet(d)


if __name__ == "__main__":
    main(sys.argv[1])
