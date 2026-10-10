"""Reviewer v2 contact sheets (system python + PIL). Fixed-size cells, letterboxed, labelled."""
import os
from PIL import Image, ImageDraw
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "renders")
O = os.path.dirname(os.path.abspath(__file__))
TAC = os.path.dirname(os.path.dirname(O))


def sheet(files, out, title, cols=3, cw=600, ch=420):
    rows = (len(files) + cols - 1) // cols
    S = Image.new("RGB", (cols * cw, 30 + rows * (ch + 20)), (24, 25, 28))
    d = ImageDraw.Draw(S)
    d.text((8, 8), title, fill=(235, 235, 235))
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        im.thumbnail((cw, ch))
        x = (i % cols) * cw + (cw - im.width) // 2
        y = 30 + (i // cols) * (ch + 20) + (ch - im.height) // 2
        S.paste(im, (x, y))
        d.text(((i % cols) * cw + 6, 30 + (i // cols) * (ch + 20) + ch + 3), os.path.relpath(f, TAC), fill=(210, 210, 210))
    S.save(out)
    print("sheet", out)


uf = [os.path.join(R, "uglfit", f) for f in ("mako_ugl_side_left_of_shooter.png", "mako_ugl_side_right_of_shooter.png",
                                              "mako_ugl_below.png", "fp_inspect_left_ugl.png", "fp_hip_ugl.png",
                                              "kit_closed_wide_left.png", "kit_closed_front_low_left.png",
                                              "kit_closed_side_left.png", "kit_open_below_left.png",
                                              "kit_open_from_below.png", "kit_open_fp_left.png")]
sheet(uf, os.path.join(O, "sheet_v2_uglfit.png"),
      "v2 reviewer: current UGL on mako_default.glb (its own socket nodes) + shield / laser_R / flashlight_L / holo")
holes = [os.path.join(TAC, "renders", "laser_R", "laser_R_top.png"),
         os.path.join(R, "holes", "laser_R_top_eevee_culled.png"),
         os.path.join(R, "ugl", "_crop_right_latch.png"),
         os.path.join(R, "holes", "ugl_left_flank_flank_close_eevee_culled.png"),
         os.path.join(R, "wire", "ugl_wire_right.png"),
         os.path.join(R, "wire", "ugl_wire_left.png")]
sheet(holes, os.path.join(O, "sheet_v2_foldover_tris.png"),
      "v2: fold-over (reverse-wound coplanar) triangles: black wedges in Cycles (builder's laser_R_top, UGL +X flank); "
      "hidden when back-faces are culled (EEVEE). Wire: sliver fan at the UGL latch", cols=2, cw=700, ch=520)
ads = [os.path.join(R, "ads", f) for f in ("ads_holo_shield_game78_eevee.png", "ads_holo_shield_zoom40_eevee.png",
                                            "eye_through_glass_no_optic_zoom40_eevee.png")]
sheet(ads, os.path.join(O, "sheet_v2_ads.png"), "v2: ADS through the shield glass in a sunlit scene (EEVEE)", cols=3,
      cw=640, ch=360)
