"""Round-2: 64/128 px silhouette read sheet + labelled review contact sheet (system python + PIL)."""
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps
R = r"F:/git/val etf/assets/weapons/vk50_warden/review/r2/renders"
try:
    F = ImageFont.truetype("arial.ttf", 22); FS = ImageFont.truetype("arial.ttf", 18)
except Exception:
    F = FS = ImageFont.load_default()

def crop_sil(p):
    im = Image.open(p).convert("L")
    bb = ImageOps.invert(im).point(lambda v: 255 if v > 60 else 0).getbbox()
    return im.crop(bb) if bb else im

rows = [("gun only, side (+X)", "r2_sil_gun_side.png"),
        ("showcase loadout (optic_sniper + bipod), side", "r2_sil_loadout_side.png"),
        ("showcase loadout, three-quarter", "r2_sil_loadout_three_quarter.png"),
        ("showcase loadout, front", "r2_sil_loadout_front.png")]
W = 1500; y = 10
sheet = Image.new("RGB", (W, 3000), (240, 240, 240)); d = ImageDraw.Draw(sheet)
for label, fn in rows:
    im = crop_sil(os.path.join(R, fn))
    d.text((10, y), label, fill=(0, 0, 0), font=F); y += 30
    x = 10; hmax = 0
    for w in (64, 128, 256):
        s = im.resize((w, max(1, round(im.height * w / im.width))), Image.LANCZOS)
        big = s.resize((s.width * (512 // w) if w < 512 else s.width, s.height * (512 // w) if w < 512 else s.height), Image.NEAREST)
        if big.width > 480:
            big = big.resize((480, round(big.height * 480 / big.width)), Image.NEAREST)
        sheet.paste(big.convert("RGB"), (x, y)); d.text((x, y + big.height + 2), f"{w}px", fill=(90, 90, 90), font=FS)
        x += big.width + 20; hmax = max(hmax, big.height)
    y += hmax + 34
sheet = sheet.crop((0, 0, W, y)); sheet.save(os.path.join(R, "r2_silhouette_reads.png"))

items = [("r2_cu_topvents_left_failed.png", "1  +X top vents y-0.535/-0.470: boolean failed (ghost pockets, crack, smudges)"),
         ("r2_cu_handguard_top_ortho.png", "1b top ortho: -X row cut through, +X row 2 of 3 ghost"),
         ("r2_cu_handguard_side_ortho_left.png", "2  upper slot row (z .096-.111) above barrel top (.098): see-through pills"),
         ("r2_side_left_skybg.png", "2b same on a bright backdrop (Yard = snowy fjord)"),
         ("r2_cu_stock_riser_right.png", "3  riser: 130 mm cantilever on 2 posts 18 mm apart at its rear end"),
         ("r2_loadout_fpv_hip.png", "4  first person: domed shroud cap reads as a 2nd knob next to the knob"),
         ("r2_worst_rear_low_right.png", "4b rear-low: shroud cap + knob = two balls"),
         ("r2_magcheck_2left_tilted.png", "OK  mag check: 2 left + follower reads"),
         ("r2_loadout_left_side.png", "OK  showcase loadout side"),
         ("r2_loadout_bolt_open_right.png", "OK  bolt open with optic: 39 mm clearance"),
         ("r2_clay_three_quarter.png", "OK  clay: clean planar shading"),
         ("r2_wire_three_quarter.png", "wire: boolean fan triangulation, dense knob")]
cw, ch = 700, 450
cols = 3; rws = (len(items) + cols - 1) // cols
cs = Image.new("RGB", (cw * cols, (ch + 36) * rws + 50), (235, 235, 235)); d = ImageDraw.Draw(cs)
d.text((10, 10), "VK-50 WARDEN  round-2 independent review (renders from the exported .glb)", fill=(0, 0, 0), font=F)
for i, (fn, lab) in enumerate(items):
    r, c = divmod(i, cols)
    im = Image.open(os.path.join(R, fn)).convert("RGB")
    im.thumbnail((cw - 10, ch - 10))
    x0, y0 = c * cw + 5, 50 + r * (ch + 36)
    cs.paste(im, (x0, y0)); d.text((x0, y0 + im.height + 4), lab, fill=(0, 0, 0), font=FS)
cs.save(os.path.join(R, "r2_review_contact_sheet.png"))
print("ok")
