"""make_sheets.py - labelled contact sheets + concept comparisons for the ATT optics renders.
Run with the system python (needs PIL):  python "F:/git/val etf/assets/weapons/attachments/optics/make_sheets.py"
"""
import glob
import os

from PIL import Image, ImageDraw, ImageFont

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
REN = os.path.join(OUT, "renders")
CON = r"F:/git/val etf/art/concepts"
IDS = ["optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"]
ORDER = ["right", "left", "three_quarter", "three_quarter_back", "front", "back", "top", "eye",
         "onrail_right", "onrail_three_quarter", "onrail_front", "onrail_back"]


def font(sz):
    for f in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, sz)
        except OSError:
            continue
    return ImageFont.load_default()


def label(im, text, sz=22):
    d = ImageDraw.Draw(im)
    f = font(sz)
    d.rectangle([0, 0, im.width, sz + 12], fill=(12, 13, 16))
    d.text((8, 4), text, fill=(235, 235, 235), font=f)
    return im


def sheet(paths, labels, out, cols=4, cell=420, title=None):
    if not paths:
        return
    rows = (len(paths) + cols - 1) // cols
    top = 46 if title else 0
    sh = Image.new("RGB", (cols * cell, rows * cell + top), (20, 21, 24))
    if title:
        d = ImageDraw.Draw(sh)
        d.text((12, 8), title, fill=(240, 240, 240), font=font(28))
    for i, (p, lb) in enumerate(zip(paths, labels)):
        im = Image.open(p).convert("RGB").resize((cell, cell), Image.LANCZOS)
        label(im, lb, 18)
        r, c = divmod(i, cols)
        sh.paste(im, (c * cell, top + r * cell))
    sh.save(out)
    print("sheet", out)


def side_by_side(a, b, out, la, lb, h=600):
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    ia = ia.resize((int(ia.width * h / ia.height), h), Image.LANCZOS)
    ib = ib.resize((int(ib.width * h / ib.height), h), Image.LANCZOS)
    sh = Image.new("RGB", (ia.width + ib.width + 10, h), (20, 21, 24))
    sh.paste(label(ia, la), (0, 0))
    sh.paste(label(ib, lb), (ia.width + 10, 0))
    sh.save(out)
    print("compare", out)


def crop_center(p, frac=0.62):
    """Crop the central part of a render (renders are auto-framed with margin)."""
    im = Image.open(p).convert("RGB")
    w, h = im.size
    cw, ch = int(w * frac), int(h * frac * 0.75)
    box = ((w - cw) // 2, (h - ch) // 2, (w + cw) // 2, (h + ch) // 2)
    tmp = os.path.join(REN, "_tmp_" + os.path.basename(p))
    im.crop(box).save(tmp)
    return tmp


def main():
    os.makedirs(os.path.join(REN, "sheets"), exist_ok=True)
    overview = []
    for oid in IDS:
        pre = os.path.join(REN, "ATT_" + oid + "_")
        files = sorted(glob.glob(pre + "*.png"))
        if not files:
            continue
        keyed = {os.path.basename(f)[len("ATT_" + oid + "_"):-4]: f for f in files}
        paths, labels = [], []
        for k in ORDER:
            if k in keyed:
                paths.append(keyed[k])
                labels.append(k.replace("onrail_", "on rail: "))
        for k in sorted(keyed):
            if k.startswith("close_"):
                paths.append(keyed[k])
                labels.append(k.replace("close_", "close-up: ").replace("_", " "))
        sheet(paths, labels, os.path.join(REN, "sheets", "ATT_%s_sheet.png" % oid), cols=4,
              title="ATT_" + oid)
        if "three_quarter" in keyed:
            overview.append((keyed["three_quarter"], oid))
        if "onrail_three_quarter" in keyed:
            overview.append((keyed["onrail_three_quarter"], oid + " (on rail)"))
    if overview:
        sheet([p for p, _ in overview], [l for _, l in overview], os.path.join(REN, "sheets", "ATT_optics_overview.png"),
              cols=4, title="ATT optics set")

    # concept comparisons
    v09 = os.path.join(CON, "mako", "v09.png")
    if os.path.exists(v09):
        crop = os.path.join(OUT, "_ref", "v09_holo_crop.png")
        if not os.path.exists(crop):
            Image.open(v09).crop((780, 140, 1080, 360)).save(crop)
        for view in ("three_quarter", "onrail_three_quarter", "right"):
            p = os.path.join(REN, "ATT_optic_holo_%s.png" % view)
            if os.path.exists(p):
                side_by_side(p, crop, os.path.join(REN, "sheets", "compare_holo_%s_vs_v09.png" % view),
                             "optic_holo " + view, "concept mako v09 (holo crop)")
    wmain = os.path.join(CON, "warden", "concept_main.png")
    if os.path.exists(wmain):
        crop = os.path.join(OUT, "_ref", "warden_scope_side_crop_raw.png")
        Image.open(wmain).crop((670, 80, 1170, 250)).save(crop)
        for view in ("onrail_right", "right"):
            p = os.path.join(REN, "ATT_optic_sniper_%s.png" % view)
            if os.path.exists(p):
                side_by_side(crop_center(p, 0.98), crop,
                             os.path.join(REN, "sheets", "compare_sniper_%s_vs_warden.png" % view),
                             "optic_sniper " + view, "concept warden main (scope crop)", h=420)
    w34 = os.path.join(CON, "warden", "concept_34.png")
    if os.path.exists(w34):
        crop = os.path.join(OUT, "_ref", "warden_scope_34_crop_raw.png")
        Image.open(w34).crop((760, 20, 1240, 260)).save(crop)
        p = os.path.join(REN, "ATT_optic_sniper_three_quarter.png")
        if os.path.exists(p):
            side_by_side(p, crop, os.path.join(REN, "sheets", "compare_sniper_34_vs_warden.png"),
                         "optic_sniper three_quarter", "concept warden 3/4 (scope crop)", h=500)
    for t in glob.glob(os.path.join(REN, "_tmp_*.png")):
        os.remove(t)


if __name__ == "__main__":
    main()
