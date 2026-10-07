"""Material sanity check: each library texture applied through bc.material at its README-recommended
tex_mix / tex_scale on a palette colour, rendered as a 3x3 grid of rounded blocks.

"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P test_render.py
Writes _src/preview/material_test.png
"""
import os
import sys

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

TEX = bc.TEXTURES
OUT = os.path.join(TEX, "_src", "preview")

# name, palette colour (linear), rough, metal, tex_mix, tex_scale
ROWS = [
    ("worn_paint",      (0.55, 0.52, 0.46),   0.60, 0.0,  0.35, 1.5),   # bone
    ("brushed_metal",   (0.11, 0.115, 0.12),  0.35, 0.85, 0.30, 2.5),   # gunmetal
    ("polymer_stipple", (0.36, 0.28, 0.18),   0.70, 0.0,  0.40, 4.0),   # sand
    ("fabric_ripstop",  (0.12, 0.13, 0.08),   0.75, 0.0,  0.45, 3.5),   # olive
    ("fabric_soft",     (0.035, 0.037, 0.045), 0.70, 0.0, 0.55, 4.0),   # charcoal-cloth (dark: upper mix)
    ("leather_soft",    (0.16, 0.10, 0.06),   0.55, 0.0,  0.35, 3.0),   # brown leather
    ("carbon_weave",    (0.030, 0.033, 0.040), 0.45, 0.0, 0.55, 3.0),   # graphite (dark: upper mix)
    ("skin_soft",       (0.62, 0.42, 0.33),   0.55, 0.0,  0.20, 1.0),   # skin light
    ("hair_strands",    (0.20, 0.12, 0.07),   0.50, 0.0,  0.50, 1.5),   # mid brown hair
]


def main():
    bc.reset_scene()
    for i, (name, col, rough, metal, mix, scale) in enumerate(ROWS):
        r, c = divmod(i, 3)
        mat = bc.material(f"M_Test_{name}", col, rough, metal, tex=os.path.join(TEX, name + ".png"),
                          tex_mix=mix, tex_scale=scale)
        bc.box(f"T_{name}", (0.42, 0.42, 0.42), loc=((c - 1) * 0.6, 0, (2 - r) * 0.6 + 0.21),
               rot=(0, 0, 35), mat=mat, bevel=0.04, segments=3)
    bc.uv_all()
    bc.setup_studio(strength=0.8)
    bc.render_views(OUT, "material_test", views=("front",), res=(1100, 1100), engine="EEVEE", samples=32,
                    lens=60, margin=1.02)
    # close-ups so the overlay detail can actually be judged
    paths = []
    for i, (name, *_rest) in enumerate(ROWS):
        r, c = divmod(i, 3)
        center = ((c - 1) * 0.6, 0, (2 - r) * 0.6 + 0.21)
        paths += bc.render_views(os.path.join(OUT, "_close"), name, views=("three_quarter",), res=(440, 440),
                                 engine="EEVEE", samples=32, lens=85, focus=(center, 0.27))
    bc.contact_sheet(paths, os.path.join(OUT, "material_test_closeups.png"), cols=3)


main()
