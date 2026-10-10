"""Review round 2 (system Python + PIL): compose the raw reviewer renders into labelled sheets.
Run: python "F:/git/val etf/assets/shields/review/r2/r2_compose.py" [sheet ...]
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

R2 = r"F:/git/val etf/assets/shields/review/r2/renders"
RAW = os.path.join(R2, "_raw")
BG = (16, 17, 21)


def font(sz):
    for f in ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, sz)
    return ImageFont.load_default()


def raw(name):
    return Image.open(os.path.join(RAW, name + ".png")).convert("RGBA")


def flat(im, bg=(255, 255, 255)):
    """alpha render -> black silhouette on white."""
    a = im.split()[-1]
    out = Image.new("RGB", im.size, bg)
    out.paste((0, 0, 0), mask=a)
    return out


def up(im, k):
    return im.resize((im.width * k, im.height * k), Image.NEAREST)


def sheet(blocks, out, width=None, pad=14):
    """blocks: list of (title, subtitle, image)."""
    f1, f2 = font(26), font(19)
    w = width or max(b[2].width for b in blocks) + 2 * pad
    h = sum(b[2].height + 78 for b in blocks) + pad
    S = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(S)
    y = pad
    for title, sub, im in blocks:
        d.text((pad, y), title, font=f1, fill=(235, 236, 240))
        d.text((pad, y + 32), sub, font=f2, fill=(160, 165, 175))
        y += 66
        S.paste(im.convert("RGB"), (pad, y))
        y += im.height + 12
    S.save(out)
    print("wrote", out, S.size)


def labels(im, cols, rows, col_names, row_names, color=(255, 255, 255)):
    im = im.convert("RGB")
    d = ImageDraw.Draw(im)
    f = font(max(12, im.width // 70))
    for i, n in enumerate(col_names):
        d.text((int((i + 0.5) * im.width / cols) - 30, 4), n, font=f, fill=color)
    for j, n in enumerate(row_names):
        d.text((4, int((j + 0.15) * im.height / rows)), n, font=f, fill=color)
    return im


def blind():
    for d, k in ((5, 3), (10, 5)):
        blocks = []
        for yaw, yname in ((0, "FRONT (wearer faces you)"), (90, "SIDE (wearer's left toward you)"),
                           (180, "BACK (Phase gap toward you)")):
            day = up(raw(f"blind_{d}m_yaw{yaw}_day"), k)
            dark = up(raw(f"blind_{d}m_yaw{yaw}_dark"), k)
            sil = up(flat(raw(f"blind_{d}m_yaw{yaw}_alpha")), k)
            row = Image.new("RGB", (day.width * 3 + 20, day.height), BG)
            row.paste(day.convert("RGB"), (0, 0))
            row.paste(dark.convert("RGB"), (day.width + 10, 0))
            row.paste(sil, (2 * day.width + 20, 0))
            blocks.append((f"{d} m, {yname}  -  true 1080p pixels (vfov 78), shown x{k} nearest",
                           "columns: Bulwark / Mender / Volt / Phase   rows: Light T1 torso / Light H2 T2 / "
                           "Medium H2 T2 L2 / Heavy H3 T3 A3      [daylight | dark | silhouette]", row))
        sheet(blocks, os.path.join(R2, f"V01_blind_core_read_{d}m.png"))


def edgeon():
    blocks = []
    for tag, title in (("back_m2", "From BEHIND, eye 2 deg below (Phase gap faces the viewer)"),
                       ("q34_m2", "Three-quarter (45 deg), eye 2 deg below"),
                       ("front_0", "Exactly edge-on (0 deg), front"),
                       ("front_p4", "Viewer 4 deg ABOVE the ring (stairs, ledge), front")):
        col = raw(f"edge_{tag}").convert("RGB")
        sil = flat(raw(f"edge_{tag}_alpha"))
        col = col.resize((col.width // 2, col.height // 2), Image.LANCZOS)
        sil = sil.resize((sil.width // 2, sil.height // 2), Image.LANCZOS)
        row = Image.new("RGB", (col.width * 2 + 10, col.height), BG)
        row.paste(col, (0, 0))
        row.paste(sil, (col.width + 10, 0))
        blocks.append((title, "rows: Bulwark / Mender / Volt / Phase   columns: Light (T1 torso) / Medium (H2 T2 L2) / "
                              "Heavy (H3 T3 A3)", row))
    sheet(blocks, os.path.join(R2, "V02_worst_angles.png"))


def closeups():
    names = ["close_pips_Bulwark_T1", "close_pips_Bulwark_T2", "close_pips_Volt_T1", "close_pips_Volt_T2"]
    ims = [raw(n).convert("RGB") for n in names]
    grid = Image.new("RGB", (ims[0].width * 2 + 10, ims[0].height * 2 + 10), BG)
    for i, im in enumerate(ims):
        grid.paste(im, ((i % 2) * (im.width + 10), (i // 2) * (im.height + 10)))
    seams = [raw(f"close_seam_{c}").convert("RGB") for c in ("Bulwark", "Mender", "Volt", "Phase")]
    sg = Image.new("RGB", (seams[0].width * 2 + 10, seams[0].height * 2 + 10), BG)
    for i, im in enumerate(seams):
        sg.paste(im, ((i % 2) * (im.width + 10), (i // 2) * (im.height + 10)))
    fork = raw("close_phase_fork_back").convert("RGB")
    bands = [raw(f"close_band_{c}").convert("RGB") for c in ("Bulwark", "Volt")]
    bg_ = Image.new("RGB", (bands[0].width * 2 + 10, bands[0].height), BG)
    for i, im in enumerate(bands):
        bg_.paste(im, (i * (im.width + 10), 0))
    sheet([("Tier pips, front at eye level (unscaled halo)",
            "top: Bulwark T1 (1 pip) / T2 (2 pips)   bottom: Volt T1 / T2   - the pip row is left-justified "
            "(PIP_1..PIP_n), not centred", grid),
           ("Arc seams at the Head/Arms joint (Head lit T3, Arms uncovered), low three-quarter",
            "Bulwark / Mender / Volt / Phase", sg),
           ("Phase Light from BEHIND at eye level (-3 deg): the electrode fork over the back gap", "", fork),
           ("Heavy band clamp, from 12 deg below", "Bulwark Heavy / Volt Heavy", bg_)],
          os.path.join(R2, "V03_closeups.png"), width=2030)


def wire():
    names = ["wire_Bulwark_Arc_Head", "wire_Mender_Arc_Head", "wire_Phase_Arc_Torso", "wire_Volt_Band_Heavy",
             "wire_PowerCell", "wire_Core_Mender"]
    ims = [raw(n).convert("RGB") for n in names]
    g = Image.new("RGB", (ims[0].width * 3 + 20, ims[0].height * 2 + 10), BG)
    for i, im in enumerate(ims):
        g.paste(im, ((i % 3) * (im.width + 10), (i // 3) * (im.height + 10)))
    g = g.resize((g.width * 2 // 3, g.height * 2 // 3), Image.LANCZOS)
    sheet([("Wireframes (exported glTF, re-imported)",
            "Bulwark Arc_Head / Mender Arc_Head / Phase Arc_Torso   |   Volt Band_Heavy / PowerCell (488 tris) / "
            "Core_Mender", g)], os.path.join(R2, "V04_wireframes.png"))


def states():
    blocks = []
    for d, k in ((5, 3), (10, 5)):
        day = up(raw(f"states_{d}m_day"), k)
        dark = up(raw(f"states_{d}m_dark"), k)
        row = Image.new("RGB", (day.width * 2 + 10, day.height), BG)
        row.paste(day.convert("RGB"), (0, 0))
        row.paste(dark.convert("RGB"), (day.width + 10, 0))
        blocks.append((f"{d} m, true 1080p pixels shown x{k}: Head arc IDLE-LIT / BROKEN / UNCOVERED",
                       "rows: Bulwark Medium, Volt Medium (H2 T2 L2 / H-broken / H0 A2)   [daylight | dark]", row))
    big = raw("states_large_day").convert("RGB")
    big = big.resize((big.width * 2 // 3, big.height * 2 // 3), Image.LANCZOS)
    blocks.append(("Large reference (6 deg below, daylight)", "lit idle / broken (M_HALO_Glass_Broken_T2) / "
                                                              "uncovered (M_HALO_Glass_Off)", big))
    sheet(blocks, os.path.join(R2, "V05_arc_states_ingame.png"))


def char():
    ims = [raw(n).convert("RGB") for n in ("char_ledge_8m", "char_behind_4m", "char_front_1p8m",
                                             "char_front_1p8m_dark")]
    ims = [im.resize((im.width // 2, im.height // 2), Image.LANCZOS) for im in ims]
    g = Image.new("RGB", (ims[0].width * 2 + 10, ims[0].height * 2 + 10), BG)
    for i, im in enumerate(ims):
        g.paste(im, ((i % 2) * (im.width + 10), (i // 2) * (im.height + 10)))
    sheet([("In context: Phase Light (T1 torso) / Volt Medium (H2 T2 L2) / Bulwark Heavy (H3 T3 A3)",
            "from a ledge 3 m up at 8 m (vfov 78) | behind + above at 4 m | eye level 1.8 m, daylight | same, dark",
            g)], os.path.join(R2, "V06_in_context.png"))
    # crops at native res of the ledge view (halos only)
    im = raw("char_ledge_8m").convert("RGB")
    W, H = im.size
    crop = im.crop((int(W * 0.30), int(H * 0.30), int(W * 0.70), int(H * 0.55)))
    crop = up(crop, 3)
    sheet([("Ledge view crop, native 1080p pixels x3", "", crop)], os.path.join(R2, "V06b_ledge_crop.png"))


def farlod():
    a = up(raw("farlod_20m_day"), 6)
    b = raw("farlod_large_day").convert("RGB")
    b = b.resize((b.width * 2 // 3, b.height * 2 // 3), Image.LANCZOS)
    sheet([("Near kit (top 3 rows) vs far LOD (bottom 3 rows) at 20 m, true pixels x6",
            "Bulwark / Mender / Volt / Phase; Light / Medium / Heavy presets; daylight", a),
           ("Same, large (6 deg below)", "", b)], os.path.join(R2, "V07_far_lod_switch.png"))


JOBS = {"blind": blind, "edgeon": edgeon, "closeups": closeups, "wire": wire, "states": states, "char": char,
        "farlod": farlod}
for j in (sys.argv[1:] or JOBS):
    try:
        JOBS[j]()
    except FileNotFoundError as e:
        print("skip", j, e)
