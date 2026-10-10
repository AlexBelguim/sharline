"""Reviewer sheets (system python + PIL): silhouettes at 64 px (shown x3 nearest), and labelled grids."""
import os, sys
from PIL import Image, ImageDraw, ImageFont
RD = r"F:/git/val etf/assets/weapons/attachments/optics/review/renders"
SH = r"F:/git/val etf/assets/weapons/attachments/optics/review/sheets"
os.makedirs(SH, exist_ok=True)
OPT = ["optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"]
try:
    F = ImageFont.truetype("arial.ttf", 16)
except Exception:
    F = ImageFont.load_default()

def grid(rows, out, cell=None, title=""):
    """rows: list of (label, [paths])"""
    ims = [[Image.open(p).convert("RGB") if p and os.path.exists(p) else None for p in r[1]] for r in rows]
    cw = cell or max(i.width for r in ims for i in r if i)
    ch = cell or max(i.height for r in ims for i in r if i)
    ncol = max(len(r) for r in ims)
    W, H = 150 + ncol * (cw + 6), 40 + len(rows) * (ch + 6)
    S = Image.new("RGB", (W, H), (20, 21, 26))
    d = ImageDraw.Draw(S)
    d.text((10, 10), title, fill=(230, 230, 230), font=F)
    for ri, (lab, _) in enumerate(rows):
        y = 40 + ri * (ch + 6)
        d.text((8, y + ch // 2 - 8), lab, fill=(220, 220, 220), font=F)
        for ci, im in enumerate(ims[ri]):
            if im is None:
                continue
            im = im.resize((cw, ch), Image.NEAREST if im.width < cw else Image.LANCZOS)
            S.paste(im, (150 + ci * (cw + 6), y))
    S.save(out)
    print("wrote", out)

if "sil" in sys.argv:
    rows = [(o, [os.path.join(RD, "%s_sil64_%s.png" % (o, v)) for v in ("right", "three_quarter", "front", "hip_pov")]) for o in OPT]
    grid(rows, os.path.join(SH, "silhouettes_64px_x3.png"), cell=192, title="64 px silhouettes (shown x3, nearest): right | three_quarter | front | hip POV")
if "extra" in sys.argv:
    rows = [(o, [os.path.join(RD, "%s_%s.png" % (o, v)) for v in ("low_front_right", "under", "rear_right_high", "hip_pov", "rear_left_low")]) for o in OPT]
    grid(rows, os.path.join(SH, "extra_angles.png"), cell=360, title="Reviewer angles from the exported .glb: low front right | under | rear right high | hip POV | rear left low")
if "gloss" in sys.argv:
    rows = [(o, [os.path.join(RD, "%s_gloss_%s.png" % (o, v)) for v in ("three_quarter", "rear_right_high", "left")]) for o in OPT]
    grid(rows, os.path.join(SH, "gloss_clay.png"), cell=420, title="Glossy clay override (shading / bevel check): three_quarter | rear right high | left")
if "wire" in sys.argv:
    rows = [(o, [os.path.join(RD, "%s_wire_%s.png" % (o, v)) for v in ("three_quarter", "left", "rear_right_high")]) for o in OPT]
    grid(rows, os.path.join(SH, "wireframe.png"), cell=420, title="Wireframe overlay on optics.blend source meshes: three_quarter | left | rear right high")
if "ads" in sys.argv:
    rows = [("MAKO", [os.path.join(RD, f) for f in ("optic_reddot_onmako_ADS_fov68.png", "optic_holo_onmako_ADS_fov62.png", "optic_3x_onmako_ADS_fov26.png")]),
            ("WARDEN", [os.path.join(RD, f) for f in ("optic_holo_onwarden_ADS_fov62.png", "optic_sniper_onwarden_ADS_fov13.png", "optic_thermal_onwarden_ADS_fov20.png")])]
    grid(rows, os.path.join(SH, "ads_views.png"), cell=None, title="First-person ADS at catalog eye_relief_m, game vFOV 78/zoom: reddot|holo|3x on MAKO; holo|sniper|thermal on WARDEN")
