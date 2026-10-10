"""make_sheets.py - labelled contact sheets + concept comparisons for the ATT optics renders.
Run with the system python (needs PIL):  python "F:/git/val etf/assets/weapons/attachments/optics/make_sheets.py"
"""
import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SOURCE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(SOURCE, "..", "..", "..", ".."))
OUT = os.path.abspath(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else SOURCE
REN = os.path.join(OUT, "renders")
CON = os.path.join(PROJECT, "art", "concepts")
IDS = ["optic_reddot", "optic_holo", "optic_projector", "optic_3x", "optic_sniper", "optic_thermal"]
ORDER = ["right", "left", "three_quarter", "three_quarter_back", "front", "back", "top", "v0.85_-0.75_0.5", "eye",
         "folded_three_quarter", "folded_right", "folded_left", "folded_front", "folded_back", "folded_top",
         "folded_three_quarter_back", "folded_v0.85_-0.75_0.5", "folded_onrail_three_quarter",
         "half_three_quarter", "half_right", "half_front", "open_three_quarter", "open_front", "open_v0.55_1.0_0.35",
         "onrail_right", "onrail_three_quarter", "onrail_front", "onrail_back",
         "onmako_right", "onmako_three_quarter", "onmako_folded_right", "onmako_folded_three_quarter",
         "onwarden_right", "onwarden_three_quarter", "ads_onmako", "ads_onmako_measured",
         "ads_onwarden"]


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
    """Labelled grid; every image is fitted into a cell (aspect kept, letterboxed). cols == 1 -> cell = width and
    each row takes the image's own height."""
    if not paths:
        return
    ims = [Image.open(p).convert("RGB") for p in paths]
    if cols == 1:
        ims = [im.resize((cell, int(cell * im.height / im.width)), Image.LANCZOS) for im in ims]
        heights = [im.height for im in ims]
    else:
        fitted = []
        for im in ims:
            k = min(cell / im.width, cell / im.height)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
            bg = Image.new("RGB", (cell, cell), (20, 21, 24))
            bg.paste(im, ((cell - im.width) // 2, (cell - im.height) // 2))
            fitted.append(bg)
        ims = fitted
        heights = [cell] * len(ims)
    rows = (len(ims) + cols - 1) // cols
    row_h = [max(heights[r * cols:(r + 1) * cols]) for r in range(rows)]
    top = 46 if title else 0
    sh = Image.new("RGB", (cols * cell, sum(row_h) + top), (20, 21, 24))
    if title:
        d = ImageDraw.Draw(sh)
        d.text((12, 8), title, fill=(240, 240, 240), font=font(28))
    for i, (im, lb) in enumerate(zip(ims, labels)):
        label(im, lb, 18)
        r, c = divmod(i, cols)
        sh.paste(im, (c * cell, top + sum(row_h[:r])))
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


def measured_overlays():
    """Draw the build's pixel measurement (fitcheck.json ads_measure, 1920 x 1080 on the Mako) onto the ADS renders:
    clear window edges (green), frame / hood edge runs (orange), hologram frame (ice) and a caption with the numbers."""
    import json
    fp = os.path.join(OUT, "fitcheck.json")
    if not os.path.exists(fp):
        return
    fits = json.load(open(fp))
    for oid, f in fits.items():
        am = f.get("ads_measure")
        src = os.path.join(REN, "ATT_%s_ads_onmako.png" % oid)
        if not am or not os.path.exists(src):
            continue
        im = Image.open(src).convert("RGB")
        W, H = am["res_px"]
        if im.size != (W, H):
            continue
        d = ImageDraw.Draw(im)
        wp, fr = am["window_px"], am["frame_px"]
        ow = am.get("optic_window_px", wp)
        cx, cy = W // 2, H // 2
        g, o, ice = (40, 220, 90), (255, 150, 30), (120, 220, 255)
        if wp["width"] < W:                         # window edges along the centre row / column
            d.line([(wp["left"], cy - 60), (wp["left"], cy + 60)], fill=g, width=3)
            d.line([(wp["right"], cy - 60), (wp["right"], cy + 60)], fill=g, width=3)
            d.line([(wp["left"], cy), (wp["right"], cy)], fill=g, width=1)
            d.line([(wp["left"] - fr["left"], cy + 24), (wp["left"], cy + 24)], fill=o, width=6)
            d.line([(wp["right"], cy + 24), (wp["right"] + fr["right"], cy + 24)], fill=o, width=6)
        if wp["top"] > 0:
            d.line([(cx - 60, wp["top"]), (cx + 60, wp["top"])], fill=g, width=3)
            d.line([(cx + 24, wp["top"] - fr["top"]), (cx + 24, wp["top"])], fill=o, width=6)
        if wp["bottom"] < H - 1:
            d.line([(cx - 60, wp["bottom"]), (cx + 60, wp["bottom"])], fill=g, width=3)
        if ow["bottom"] != wp["bottom"] and ow["bottom"] < H - 1:
            d.line([(cx - 90, ow["bottom"]), (cx + 90, ow["bottom"])], fill=(40, 160, 70), width=2)
        if wp["top"] > 0 or wp["bottom"] < H - 1:
            d.line([(cx, wp["top"]), (cx, wp["bottom"])], fill=g, width=1)
        hf = am.get("hologram_frame_px")
        if hf:
            x0, y0 = cx - hf["width"] / 2, cy - hf["height"] / 2
            d.rectangle([x0, y0, x0 + hf["width"], y0 + hf["height"]], outline=ice, width=2)
        t = am.get("targets", {})
        cap = ["%s  |  %d x %d px at %.1f deg vFOV (settings fov_h 103 through zoom)" % (oid, W, H, am["vfov_deg"])]
        if wp["width"] < W:
            cap.append("clear on the Mako %d x %d px = %.1f %% W x %.1f %% H  (target >= %d %% W, >= %d %% H)" % (
                wp["width"], wp["height"], 100 * am["window_frac_w"], 100 * am["window_frac_h"],
                round(100 * t.get("window_frac_w_min", 0)), round(100 * t.get("window_frac_h_min", 0))))
            if ow is not wp:
                cap.append("optic window alone %d x %d px = %.1f %% W x %.1f %% H (lower edge: the gun rail)" % (
                    ow["width"], ow["height"], 100 * ow["width"] / W, 100 * ow["height"] / H))
            cap.append("frame edge L / R / top %d / %d / %d px = %.1f / %.1f / %.1f %% W  (target <= 2.5 %%)" % (
                fr["left"], fr["right"], fr["top"], 100 * am["frame_frac_w"]["left"],
                100 * am["frame_frac_w"]["right"], 100 * am["frame_frac_w"]["top"]))
        if hf:
            cap.append("no glass, view open; hologram frame %d x %d px = %.0f %% W x %.0f %% H (ice box)" % (
                hf["width"], hf["height"], 100 * am["hologram_frame_frac"][0], 100 * am["hologram_frame_frac"][1]))
        cap.append("%.0f %% of the screen clear of optic + gun" % (100 * am["screen_clear_frac"]))
        f30 = font(30)
        d.rectangle([0, 0, W, 16 + 40 * len(cap)], fill=(12, 13, 16))
        for i, line in enumerate(cap):
            d.text((16, 8 + 40 * i), line, fill=(240, 240, 240), font=f30)
        out = os.path.join(REN, "ATT_%s_ads_onmako_measured.png" % oid)
        im.save(out)
        print("measured", out)


def before_after():
    """Pre-revision renders (kept in _ref/before_revision) next to the revised ones."""
    bdir = os.path.join(OUT, "_ref", "before_revision")
    sd = os.path.join(REN, "sheets")
    for oid in ("optic_holo", "optic_reddot"):
        for view in ("ads_onmako", "three_quarter"):
            a = os.path.join(bdir, "ATT_%s_%s.png" % (oid, view))
            b = os.path.join(REN, "ATT_%s_%s.png" % (oid, view))
            if os.path.exists(a) and os.path.exists(b):
                side_by_side(a, b, os.path.join(sd, "before_after_%s_%s.png" % (oid, view)),
                             "%s %s BEFORE (review round 2)" % (oid, view),
                             "%s %s AFTER (aperture revision)" % (oid, view),
                             h=540 if view.startswith("ads") else 600)


def main():
    os.makedirs(os.path.join(REN, "sheets"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "_ref"), exist_ok=True)
    measured_overlays()
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
                labels.append(k.replace("ads_onmako_measured", "ADS on MAKO, measured").replace(
                    "ads_onmako", "ADS on MAKO (game FOV)").replace("ads_onwarden",
                                                                                         "ADS on WARDEN (game FOV)")
                              .replace("onrail_", "on rail: ").replace("onmako_", "on MAKO: ")
                              .replace("v0.85_-0.75_0.5", "concept angle")
                              .replace("onwarden_", "on WARDEN: "))
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
    sd = os.path.join(REN, "sheets")
    v09 = os.path.join(CON, "mako", "v09.png")
    if os.path.exists(v09):
        crop = os.path.join(OUT, "_ref", "v09_holo_crop.png")
        Image.open(v09).crop((800, 140, 1060, 350)).save(crop)
        for view in ("v0.85_-0.75_0.5", "three_quarter", "right"):
            p = os.path.join(REN, "ATT_optic_holo_%s.png" % view)
            if os.path.exists(p):
                side_by_side(p, crop, os.path.join(sd, "compare_holo_%s_vs_v09.png" % view.replace(".", "")),
                             "optic_holo " + view, "concept mako v09 (holo crop)")
        p = os.path.join(REN, "ATT_optic_holo_onmako_three_quarter.png")
        if os.path.exists(p):
            side_by_side(p, v09, os.path.join(sd, "compare_holo_onmako_vs_v09.png"),
                         "optic_holo on the MAKO export", "concept mako v09 (master)", h=520)
    wmain = os.path.join(CON, "warden", "concept_main.png")
    if os.path.exists(wmain):
        crop = os.path.join(OUT, "_ref", "warden_scope_side_crop_raw.png")
        Image.open(wmain).crop((670, 80, 1170, 250)).save(crop)
        for view in ("onwarden_right", "right"):
            p = os.path.join(REN, "ATT_optic_sniper_%s.png" % view)
            if os.path.exists(p):
                side_by_side(crop_center(p, 0.98), crop, os.path.join(sd, "compare_sniper_%s_vs_warden.png" % view),
                             "optic_sniper " + view, "concept warden main (scope crop)", h=420)
    w34 = os.path.join(CON, "warden", "concept_34.png")
    if os.path.exists(w34):
        crop = os.path.join(OUT, "_ref", "warden_scope_34_crop_raw.png")
        Image.open(w34).crop((760, 20, 1240, 260)).save(crop)
        p = os.path.join(REN, "ATT_optic_sniper_v0.85_-0.75_0.5.png")
        if os.path.exists(p):
            side_by_side(p, crop, os.path.join(sd, "compare_sniper_34_vs_warden.png"),
                         "optic_sniper 3/4", "concept warden 3/4 (scope crop)", h=500)
        p = os.path.join(REN, "ATT_optic_sniper_onwarden_three_quarter.png")
        if os.path.exists(p):
            side_by_side(p, w34, os.path.join(sd, "compare_sniper_onwarden_vs_warden34.png"),
                         "optic_sniper on the WARDEN export", "concept warden 3/4", h=520)
    # first-person ADS sight pictures at the game FOV (78 deg / zoom) on each optic's main gun
    ads = []
    for oid in IDS:
        for g in ("mako", "warden"):
            p = os.path.join(REN, "ATT_%s_ads_on%s.png" % (oid, g))
            pm = os.path.join(REN, "ATT_%s_ads_on%s_measured.png" % (oid, g))
            if os.path.exists(pm):
                ads.append((pm, "%s on %s (measured)" % (oid, g.upper())))
            elif os.path.exists(p):
                ads.append((p, "%s on %s" % (oid, g.upper())))
    if ads:
        sheet([p for p, _ in ads], [l for _, l in ads], os.path.join(sd, "ATT_optics_ads_sheet.png"), cols=3,
              cell=640, title="ADS sight pictures at the effective game FOV (settings fov_h 103 through each zoom)")
    lineup = [os.path.join(REN, "ATT_optics_lineup_%s.png" % v) for v in ("three_quarter", "right")]
    lineup = [p for p in lineup if os.path.exists(p)]
    if lineup:
        sheet(lineup, [os.path.basename(p)[4:-4] for p in lineup], os.path.join(sd, "ATT_optics_lineup_sheet.png"),
              cols=1, cell=900, title="ATT optics line-up (each on a dummy rail segment)")
    before_after()
    # projector poses: folded -> half -> open -> ADS
    seq = [os.path.join(REN, "ATT_optic_projector_%s.png" % k) for k in (
        "folded_three_quarter", "half_three_quarter", "three_quarter", "ads_onmako")]
    seq = [p for p in seq if os.path.exists(p)]
    if seq:
        sheet(seq, ["folded (hip fire)", "opening (half)", "open + hologram", "ADS on MAKO (hologram tinted ice)"][
            :len(seq)], os.path.join(sd, "ATT_optic_projector_poses.png"), cols=len(seq), cell=560,
            title="optic_projector: the flaps fold open on ADS (0.12 s) and project the hologram")
    for t in glob.glob(os.path.join(REN, "_tmp_*.png")):
        os.remove(t)


def iter_sheet(index_json, out):
    """Quick labelled sheet of the renders listed in an iteration index (build_optics.py --render iter)."""
    import json
    paths = [p for p in json.load(open(index_json)) if os.path.exists(p)]
    labels = [os.path.basename(p)[:-4] for p in paths]
    cols = min(4, max(1, len(paths)))
    sheet(paths, labels, out, cols=cols, cell=480)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 3 and sys.argv[1] == "--iter":
        iter_sheet(sys.argv[2], sys.argv[3])
    else:
        main()
