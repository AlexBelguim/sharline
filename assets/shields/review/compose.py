"""Compose labelled review sheets from review/renders/_raw (system Python + PIL).
Run: python "F:/git/val etf/assets/shields/review/compose.py" [sheet ...]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

R = r"F:/git/val etf/assets/shields/review/renders"
RAW = os.path.join(R, "_raw")
try:
    FONT = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 22)
    FONT_B = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 26)
except OSError:
    FONT = FONT_B = ImageFont.load_default()
BG = (18, 19, 23)


def raw(n):
    return Image.open(os.path.join(RAW, n + ".png"))


def sil(im):
    a = np.asarray(im.convert("RGBA"))[..., 3].astype(np.float32) / 255.0
    v = (255 * (1.0 - np.clip(a / 0.5, 0, 1))).astype(np.uint8)
    return Image.fromarray(np.stack([v, v, v], -1))


def upscale(im, width):
    k = max(1, round(width / im.width))
    return im.resize((im.width * k, im.height * k), Image.NEAREST), k


def label(im, text, h=40, sub=None):
    out = Image.new("RGB", (im.width, im.height + h + (28 if sub else 0)), BG)
    d = ImageDraw.Draw(out)
    d.text((12, 6), text, fill=(230, 232, 238), font=FONT_B)
    if sub:
        d.text((12, 38), sub, fill=(150, 155, 165), font=FONT)
    out.paste(im.convert("RGB"), (0, h + (28 if sub else 0)))
    return out


def vstack(ims, gap=10):
    w = max(i.width for i in ims)
    out = Image.new("RGB", (w, sum(i.height for i in ims) + gap * (len(ims) - 1)), BG)
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def hstack(ims, gap=10):
    h = max(i.height for i in ims)
    out = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) - 1), h), BG)
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + gap
    return out


def sheet_distance():
    rows = []
    order = "Bulwark L/M/H | Mender L/M/H | Volt L/M/H | Phase L/M/H  (idle, realistic presets: L = T1 torso only, " \
            "M = H2 T2 L2, H = H3 T3 A3)"
    for d in (10, 25, 50):
        day, k = upscale(raw(f"dist_{d}m_day"), 1500)
        dark, _ = upscale(raw(f"dist_{d}m_dark"), 1500)
        s, _ = upscale(sil(raw(f"dist_{d}m_alpha")), 1500)
        im = raw(f"dist_{d}m_day")
        rows.append(label(vstack([day, dark, s], 4),
                          f"{d} m  -  true game pixel size ({im.width}x{im.height} px strip at 1080p, vfov 78), "
                          f"shown x{k} nearest", sub="day bg / dark bg / alpha silhouette"))
    out = label(vstack(rows, 16), "IN-GAME DISTANCE READ  (eye 1.6 m, halo ~1.92 m)", sub=order)
    p = os.path.join(R, "R01_distance_read_10_25_50m.png")
    out.save(p)
    print(p)


def sheet_eyelevel():
    a = raw("eyelevel_2_idle").convert("RGB")
    b = sil(raw("eyelevel_2_alpha"))
    c = sil(raw("eyelevel_side_2_alpha"))
    rowlbl = "rows: Bulwark / Mender / Volt / Phase   columns: Light / Medium / Heavy (side view: Heavy / Medium / Light)"
    out = vstack([label(a.resize((1500, 825)), "EYE LEVEL -2 deg (enemy ~10 m), idle, realistic presets", sub=rowlbl),
                  label(b.resize((1500, 825)), "same, alpha silhouette (front)"),
                  label(c.resize((1500, 825)), "same, alpha silhouette (from the side, +X)")], 16)
    p = os.path.join(R, "R02_eyelevel_core_read.png")
    out.save(p)
    print(p)
    d = raw("eyelevel_8_idle").convert("RGB")
    p = os.path.join(R, "R03_eyelevel_8deg_idle.png")
    label(d.resize((1500, 825)), "EYE -8 deg (enemy ~2.5 m), idle, realistic presets", sub=rowlbl).save(p)
    print(p)


def sheet_closeups():
    names = ["close_pips_Bulwark", "close_pips_Mender", "close_pips_Volt", "close_pips_Phase"]
    ims = [label(raw(n).convert("RGB").resize((600, 333)), n.replace("close_pips_", "pips over ")) for n in names]
    top = hstack(ims[:2])
    mid = hstack(ims[2:])
    others = [("close_phase_gap", "Phase gap electrodes (back)"), ("close_volt_tooth", "Volt tooth + collar"),
              ("close_bulwark_seam", "Bulwark arc seam + heavy band corner"),
              ("close_mender_joint", "Mender arc joint + medium band finger"),
              ("close_cell_side", "power cell, side, Heavy orbit"), ("close_cell_top", "power cell from above")]
    oi = [label(raw(n).convert("RGB").resize((600, 400)), t) for n, t in others]
    out = vstack([top, mid, hstack(oi[:2]), hstack(oi[2:4]), hstack(oi[4:6])], 12)
    p = os.path.join(R, "R04_closeups.png")
    out.save(p)
    print(p)


def sheet_wire():
    ns = ["wire_Volt_Arc_Head", "wire_Mender_Arc_Head", "wire_Bulwark_Band_Heavy", "wire_Core_Phase",
          "wire_PowerCell"]
    ims = [label(raw(n).convert("RGB").resize((700, 455)), n.replace("wire_", "")) for n in ns if
           os.path.exists(os.path.join(RAW, n + ".png"))]
    rows = [hstack(ims[i:i + 2]) for i in range(0, len(ims), 2)]
    p = os.path.join(R, "R05_wireframes.png")
    vstack(rows, 12).save(p)
    print(p)


def sheet_under():
    a = raw("underside_35").convert("RGB")
    b, k = upscale(raw("hud_128px").convert("RGB"), 1024)
    out = vstack([label(a.resize((1650, 600)), "FROM BELOW -35 deg (player on lower ground), idle",
                        sub="Bulwark M, Bulwark H, Volt H, Phase L, Mender H"),
                  label(b, f"OWN-HALO HUD at 128 px per halo row (shown x{k}), lit, per-arc tiers",
                        sub="Mender Medic / Volt Line / Bulwark Vanguard / Phase Runner")], 16)
    p = os.path.join(R, "R06_underside_and_hud.png")
    out.save(p)
    print(p)


def sheet_ingame():
    ims = []
    sub = "left: Phase Light (T1 torso)  mid: Volt Medium (H2 T2 L2)  right: Bulwark Heavy (H3 T3 A3)"
    for n, t in (("ingame_5m_day", "5 m daylight"), ("ingame_5m_night", "5 m dark scene")):
        im = raw(n).convert("RGB")
        w, h = im.size
        cr = im.crop((int(w * 0.33), int(h * 0.30), int(w * 0.67), int(h * 0.52)))
        cr = cr.resize((cr.width * 2, cr.height * 2), Image.LANCZOS)
        ims.append(label(cr, f"IN GAME {t}: tight crop at 2x (true 1080p pixels, vfov 78, eye 1.6 m)", sub=sub))
    im = raw("ingame_15m_day").convert("RGB")
    w, h = im.size
    cr = im.crop((int(w * 0.42), int(h * 0.40), int(w * 0.58), int(h * 0.52)))
    cr = cr.resize((cr.width * 4, cr.height * 4), Image.NEAREST)
    ims.append(label(cr, "IN GAME 15 m daylight: tight crop x4 nearest"))
    p = os.path.join(R, "R07_ingame_kestrel.png")
    vstack(ims, 16).save(p)
    print(p)


SHEETS = {"distance": sheet_distance, "eyelevel": sheet_eyelevel, "closeups": sheet_closeups, "wire": sheet_wire,
          "under": sheet_under, "ingame": sheet_ingame}
if __name__ == "__main__":
    for s in (sys.argv[1:] or SHEETS):
        SHEETS[s]()
