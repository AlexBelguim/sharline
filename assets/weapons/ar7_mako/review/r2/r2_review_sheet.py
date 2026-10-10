"""Annotated evidence sheet for review r2 (system python + PIL)."""
import os
from PIL import Image, ImageDraw, ImageFont
R = "renders"
panels = [
    ("dlv_side_ortho_plusX.png", "1 DELIVERED ortho +X: reads as an M4; receiver/grip plainer and mag slimmer than v09"),
    ("dlv_cu_ch_castle_rear_minusX.png", "2 CH wings sunk ~7 mm into castle nut / 3.6 mm into tube; nut lugs 'melted'"),
    ("dlv_motion_ch_pulled_dc_open.png", "3 CH at 0.06 stroke: still in tube, wing enters stock front (37 tri pairs)"),
    ("dlv_cu_receiver_plusX.png", "4 player-facing +X upper = featureless slab; cool-grey stipple 'sticker'"),
    ("dlv_cu_precision_cheek.png", "5 precision cheek riser hovers (1.5 mm gap, posts hidden)"),
    ("dlv_cu_drum_minusX.png", "6 drum: hub + lower arc window = smiley; -X shows bullet tips only"),
    ("dlv_cu_hg_bottom_rail.png", "7 'rounded' slots: 2-3 seg caps read as pointed hexagons"),
    ("dlv_clay_receiver_3q.png", "8 DELIVERED clay: crisp planar shading (good)"),
    ("pnd_clay_receiver_3q.png", "9 PENDING script (not exported): bake_clean melts lower/magwell/guard"),
    ("pnd_cu_ch_castle_rear_minusX.png", "10 PENDING: CH rides above nut, clean 0.05 stroke (keep)"),
    ("pnd_cu_drum_minusX.png", "11 PENDING: rear-arc drum window + case heads (keep)"),
    ("dlv_sil_64_128.png", "12 64/128 px silhouettes: all loadouts read (good)"),
]
W, H, LH = 700, 467, 30
cols = 3
rows = (len(panels) + cols - 1) // cols
head = 150
sheet = Image.new("RGB", (cols * W, head + rows * (H + LH)), (18, 18, 22))
d = ImageDraw.Draw(sheet)
try:
    f = ImageFont.truetype("arial.ttf", 17)
    fb = ImageFont.truetype("arialbd.ttf", 22)
except Exception:
    f = fb = ImageFont.load_default()
d.text((10, 8), "AR-7 MAKO - independent review r2 (2026-10-07). DELIVERED = exports on disk (09:01). PENDING = current build_mako.py re-run in scratch.", fill=(255, 255, 255), font=fb)
lines = [
    "FOLDER OUT OF SYNC: sockets.json says Under/LeftHand z 0.0075, every GLB/FBX has 0.0155 (8 mm); tri_counts.json = 25,642 default (exports 20,998, script 20,772);",
    "textures/*.png re-baked 09:44 differ from the GLB-embedded maps; NOTES/renders describe the 09:01 build. check_glb.py would fail but build_mako.py runs it with check=False.",
    "GLBs themselves: 9 sockets correct + zero rotation, Side_R=-X, 1 material/primitive, UVs+normals, textures embedded, no emissive, FBX scale 1, 12 shared attachments fit with 0 mm penetration,",
    "mags drop 6 cm with 0 overlap. NOTES' stock travel 0.083 would push stock_standard 31.5 mm into the castle nut (max clear travel 0.0515).",
]
for i, t in enumerate(lines):
    d.text((10, 44 + i * 24), t, fill=(255, 200, 120), font=f)
for i, (fn, label) in enumerate(panels):
    im = Image.open(os.path.join(R, fn)).convert("RGB")
    im.thumbnail((W, H))
    x, y = (i % cols) * W, head + (i // cols) * (H + LH)
    sheet.paste(im, (x + (W - im.width) // 2, y + LH))
    d.text((x + 6, y + 6), label, fill=(235, 235, 235), font=f)
out = os.path.join("..", "review_sheet_r2.png")
sheet.save(out)
print(out, sheet.size)
