"""Independent review of SOLACE: labelled contact sheet of the reviewer's renders (Pillow). python rv_sheet.py"""
import os

from PIL import Image, ImageDraw, ImageFont

R = r"F:/git/val etf/assets/characters/solace/review/renders"
B = r"F:/git/val etf/assets/characters/solace/renders"
CELLS = [
    (R + "/rv_clip_lookup30_v1_0.25_0.15.png", "MAJOR: 30deg look-up, hair clips vane C"),
    (B + "/../renders/head_side_l.png", "hair loop round left ear = headset read"),
    (R + "/rv_close_collar_back.png", "back of head: holes / ragged nape"),
    (R + "/rv_close_drone.png", "drone: torn eye edge, baked into body"),
    (R + "/rv_close_pouch_belt.png", "sand repaint rectangle beside pouch"),
    (R + "/rv_close_emblem.png", "emblem OK (3 petals) but low contrast"),
    (R + "/rv_clay_hands.png", "fused mitten fingers vs 15 finger bones"),
    (R + "/rv_weapon_hold_side.png", "Mako on WeaponR: socket axes OK"),
    (R + "/rv_fp_view.png", "first-person: bracer + vial visible"),
    (R + "/rv_pose_armsdown_front.png", "true arms-down: shoulders deform OK"),
    (R + "/rv_pose_overhead_front.png", "arms overhead: OK"),
    (R + "/rv_pose_stride_low.png", "stride: tail follows, no tearing"),
    (R + "/rv_xray_front.png", "skeleton: right leg splayed, asym stance"),
    (R + "/rv_xray_v0.0_-0.0_1.png", "top: shoulder line rotated ~13deg"),
    (R + "/rv_close_hem_back.png", "back hem: coral edging thin / faint"),
    (R + "/rv_far_back.png", "~14 m: bud ivory-on-ivory"),
]
W, H = 420, 420
cols = 4
rows = (len(CELLS) + cols - 1) // cols
sheet = Image.new("RGB", (W * cols, (H + 34) * rows), (24, 26, 30))
d = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("arial.ttf", 17)
except Exception:
    font = ImageFont.load_default()
for k, (p, lab) in enumerate(CELLS):
    p = os.path.normpath(p)
    if not os.path.exists(p):
        continue
    im = Image.open(p).convert("RGB")
    if "far_back" in p:   # crop the tiny far figure and scale it (nearest) to show the read at game distance
        w, h = im.size
        im = im.crop((w // 2 - 60, h // 2 - 75, w // 2 + 60, h // 2 + 75)).resize((280, 350), Image.NEAREST)
    im.thumbnail((W, H))
    x, y = (k % cols) * W, (k // cols) * (H + 34)
    sheet.paste(im, (x + (W - im.width) // 2, y + 34 + (H - im.height) // 2))
    d.text((x + 8, y + 8), lab, fill=(235, 235, 235), font=font)
out = os.path.join(R, "review_sheet.png")
sheet.save(out)
print("wrote", out)
