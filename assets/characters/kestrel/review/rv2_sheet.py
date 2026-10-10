"""Review pass 2: key-issue sheet (resizes the evidence renders to 600x600 and tiles them 4x2)."""
import sys
sys.dont_write_bytecode = True
import bpy, numpy as np
R = r"F:/git/val etf/assets/characters/kestrel/review/renders/"
files = ["pose_rifle_shoulder_r.png", "heat_zipline_front34.png", "nape_down25_yaw35.png", "rv2_lens_front_ortho_with.png",
         "rv2_lens_side_ortho.png", "cu_hand_l_palm.png", "rv2_halo_side_head_down30.png", "rv2_halo_tpcam_rest.png"]
S = 600; cols = 4; rows = 2
buf = np.zeros((S * rows, S * cols, 4), np.float32)
for i, f in enumerate(files):
    im = bpy.data.images.load(R + f, check_existing=False)
    im.scale(S, S)
    px = np.array(im.pixels[:], np.float32).reshape(S, S, 4)
    r, c = divmod(i, cols)
    y0 = (rows - 1 - r) * S
    buf[y0:y0 + S, c * S:(c + 1) * S] = px
out = bpy.data.images.new("_s", S * cols, S * rows)
out.pixels = buf.ravel()
out.filepath_raw = R + "rv2_key_issues_sheet.png"
out.file_format = "PNG"
out.save()
print("[RV2] sheet", out.filepath_raw)
