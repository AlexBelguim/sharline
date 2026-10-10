"""Sample the Showhome concept art (design/maps/tdm/concepts/_candidates/A_showhome_*) with PIL and derive the
albedo palette every texture in this library is matched to.

For every material a few boxes (x0, y0, x1, y1 in the 1536x864 concept pixels) were picked on SUN-LIT,
unoccluded parts of that material (see BOXES for the statistic used per box), then the boxes are averaged.

The concept is a lit painting, so the samples contain the warm late-afternoon sun. The albedo removes most of that
warm cast (measured on the lit white truck roof) and scales exposure so the truck white lands at WHITE_ALBEDO; the
relative brightness and hue of every material therefore comes straight from the concept. A few materials whose lit
samples clip or are polluted get an art-director override (OVERRIDES, each with its reason).
Both the raw samples and the final albedo go to palette.json; build_textures.py matches every texture to it.

Outputs:  _src/palette.json  and  _src/preview/palette_samples.png (every box crop + its swatch, for checking).
Usage:    python sample_palette.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
CONCEPTS = r"F:/git/val etf/design/maps/tdm/concepts/_candidates"
A11, A12, G11, G12 = "A_showhome_aerial_s11", "A_showhome_aerial_s12", "A_showhome_ground_s11", "A_showhome_ground_s12"

# The concept's sun is warm and strong. Its colour is measured on the sun-lit top of the white delivery truck
# ("reference_white"). Albedo (linear) = lit_sample / sun_cast ** NEUTRALISE * EXPOSURE, where sun_cast is the
# reference white normalised to its red channel and EXPOSURE maps the lit truck white to WHITE_ALBEDO.
NEUTRALISE = 0.5    # remove half of the warm cast: the textures keep the concept's warmth, a warm sun adds the rest
                    # (0.75 was tried first: under a neutral-ish engine light it read cold and grey vs the concept)
WHITE_ALBEDO = 0.80  # linear albedo of the white truck paint (max channel)

# Boxes: (image, x0, y0, x1, y1, stat) on SUN-LIT parts of each material (the shade side of the concept is
# lavender sky-light and is not used). stat: "med" = median of the 25-85th luminance percentile,
# "p90" = mean of the brightest 10 % (box mixes the material with gaps / shadow), "sat" = median of the most
# saturated 15 % (thin structures over a different background, e.g. the crane lattice).
BOXES = {
    "reference_white": [(A11, 730, 400, 800, 440, "med"), (A12, 700, 350, 820, 420, "med")],
    "printed_concrete": [(A11, 527, 380, 543, 500, "med"), (A11, 482, 520, 498, 560, "med"),
                         (A12, 555, 260, 600, 420, "p90")],
    "fibercement_sage": [(G11, 20, 230, 150, 330, "med"), (G12, 20, 170, 95, 320, "med"),
                         (A12, 555, 260, 600, 420, "med")],
    "fibercement_clay": [(G11, 1360, 230, 1520, 380, "med"), (G12, 1330, 220, 1500, 350, "med"),
                         (A12, 620, 195, 690, 215, "med")],
    "roof_dark": [(A12, 505, 245, 560, 275, "med")],
    "solar_cell": [(A11, 420, 140, 560, 300, "med"), (G11, 100, 70, 380, 160, "med"), (G12, 1150, 70, 1450, 170, "med")],
    "asphalt": [(G11, 650, 630, 1000, 690, "med"), (G12, 700, 620, 1000, 690, "med"), (A12, 380, 640, 600, 720, "med"),
                (A11, 700, 300, 820, 340, "med")],
    "paving": [(G11, 80, 625, 400, 645, "med"), (G12, 1150, 605, 1400, 630, "med"), (A12, 420, 560, 500, 620, "med")],
    "kerb": [(G11, 0, 672, 300, 690, "p90"), (G12, 0, 665, 300, 690, "p90")],
    "grass": [(A11, 480, 600, 560, 680, "med"), (A12, 860, 610, 1050, 700, "med"), (A11, 1260, 520, 1340, 600, "med")],
    "hedge": [(A11, 0, 640, 440, 700, "med"), (A12, 1340, 470, 1395, 690, "med"), (A11, 1080, 640, 1500, 700, "med")],
    "picket_white": [(G12, 1050, 525, 1480, 580, "med"), (G11, 30, 560, 60, 600, "med"), (A12, 760, 630, 800, 690, "p90")],
    "garden_soil": [(A11, 90, 590, 210, 630, "med")],
    "construction_sand": [(A11, 880, 25, 1000, 80, "med"), (A12, 40, 150, 250, 200, "med"), (A12, 740, 50, 900, 90, "med"),
                          (A11, 450, 30, 560, 90, "med")],
    "cardboard": [(A11, 742, 622, 764, 636, "med"), (G11, 818, 468, 858, 492, "p90"), (G11, 880, 520, 900, 545, "p90")],
    "truck_white": [(A11, 730, 400, 800, 440, "med"), (A12, 700, 350, 820, 420, "med")],
    "crane_yellow": [(A11, 1370, 90, 1430, 230, "sat"), (A11, 1290, 0, 1536, 80, "sat")],
    "glass": [(A11, 70, 520, 240, 630, "p90"), (A12, 1100, 610, 1260, 700, "p90")],
    "trim_cream": [(G11, 150, 188, 340, 205, "med"), (G11, 0, 410, 100, 422, "med")],
    "frame_dark": [(A11, 330, 360, 345, 430, "med"), (A12, 455, 290, 470, 360, "med"), (A12, 975, 380, 995, 450, "med")],
    "door_sage": [(G11, 40, 430, 95, 540, "med")],
    "door_clay": [(G11, 1400, 430, 1460, 540, "med"), (G12, 1330, 410, 1380, 520, "med")],
    "pole_concrete": [(G11, 563, 220, 585, 480, "med")],
    "chimney_clay": [(G11, 1080, 10, 1130, 60, "med")],
    "chimney_sage": [(G11, 370, 10, 400, 50, "med")],
    "shed_wood": [(A12, 100, 400, 200, 470, "med"), (A11, 1340, 540, 1480, 630, "med")],
    "tree_canopy": [(A11, 80, 750, 250, 860, "med"), (A12, 0, 560, 200, 750, "med")],
}

# Art-director overrides (sRGB albedo) where the concept's lit samples clip or are polluted. Each has a reason.
OVERRIDES = {
    "printed_concrete": ((214, 200, 176), "the sun-lit printed walls clip near white in the concept; the shade "
                                          "side is lavender sky-light. Cream greige kept just below the truck white"),
    "garden_soil": ((96, 74, 56), "barely visible in the concept (under plants / behind glass): dark warm brown"),
    "crane_yellow": ((206, 148, 62), "the concept crane is a weathered ochre / orange-yellow; lifted a little toward "
                                     "yellow so it reads as construction-site yellow from the playable area"),
    "glass": ((214, 226, 222), "glass is mostly transparent; a pale cool grey-green tint (alpha does the work)"),
    "solar_cell": ((42, 47, 72), "cells read as dark blue-violet in the concept; lit samples include the light frame "
                                 "lines and sky reflection, so the cell body is set darker and bluer"),
    "picket_white": ((226, 219, 205), "painted white pickets; the ground-view samples are partly in shade and read "
                                      "pinkish, the sun-lit aerial pickets are a clean warm white"),
    "trim_cream": ((221, 211, 191), "window surrounds / sills read as a warm off-white in the concept"),
    # second look-dev pass (after rendering the library under the warm sun):
    "grass": ((126, 140, 58), "sampled hue is ~55 deg (olive): the concept lawns only read green next to its "
                              "lavender shade, and a warm in-engine sun pushed the sampled albedo to mustard. Same "
                              "luminance, hue moved to ~70 deg"),
    "hedge": ((98, 112, 52), "as grass: sampled ~59 deg read khaki under the warm sun; same luminance, hue ~74 deg, "
                             "a touch deeper than the lawn like the concept's hedges"),
    "roof_dark": ((86, 79, 80), "the sampled sun-lit roof includes bright ridge / edge highlights; the concept roofs "
                                "read as a dark warm charcoal (the first pass rendered as light taupe)"),
    "asphalt": ((112, 105, 106),"lit samples carry the sun's warmth; the concept road reads as a mid-dark, slightly "
                                 "violet grey, clearly darker than the pavement (the first pass read as brown dirt "
                                 "from the aerial view)"),
}

# Materials the concept does not show clearly: (parts (material, weight), gain, reason); mixed in linear space.
DERIVED = {
    "gravel": ([("paving", 0.5), ("construction_sand", 0.5)], 0.85,
               "pale grey-beige between the paving and the site sand, a little darker (pebble shadows)"),
    "metal_chip": ([("frame_dark", 0.5), ("roof_dark", 0.5)], 1.9, "grey primer / bare metal showing through chipped crane paint"),
}

# Chroma multipliers (applied to the albedo around its own luminance). Lit-only sampling overstates the warmth of
# the grey materials: the concept's shade side of the same surfaces is lavender, the overall read is a neutral grey.
CHROMA = {"asphalt": 0.6, "paving": 0.65, "kerb": 0.65, "pole_concrete": 0.7, "roof_dark": 0.7,
          # the hero cladding colours get a small stylisation boost (the concept is saturated and painterly)
          "fibercement_sage": 1.15, "fibercement_clay": 1.12}


def srgb_to_lin(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def sample_box(img, box, stat):
    x0, y0, x1, y1 = box
    a = np.asarray(img.crop((x0, y0, x1, y1)), dtype=np.float64).reshape(-1, 3) / 255.0
    lum = a @ np.array([0.2126, 0.7152, 0.0722])
    if stat == "p90":
        return a[lum >= np.percentile(lum, 90)].mean(axis=0)
    if stat == "sat":
        mx, mn = a.max(1), a.min(1)
        sat = (mx - mn) / np.maximum(mx, 1e-6)
        return np.median(a[sat >= np.percentile(sat, 85)], axis=0)
    lo, hi = np.percentile(lum, [25, 85])
    sel = a[(lum >= lo) & (lum <= hi)]
    return np.median(sel if len(sel) >= 10 else a, axis=0)


def main():
    imgs = {}
    results = {}
    crops = []
    for mat, boxes in BOXES.items():
        vals = []
        for (name, x0, y0, x1, y1, stat) in boxes:
            if name not in imgs:
                imgs[name] = Image.open(os.path.join(CONCEPTS, name + ".png")).convert("RGB")
            v = sample_box(imgs[name], (x0, y0, x1, y1), stat)
            vals.append(v)
            crops.append((mat, name, (x0, y0, x1, y1), v))
        results[mat] = np.mean(vals, axis=0)

    ref = srgb_to_lin(results["reference_white"])
    cast = ref / ref.max()
    exposure = WHITE_ALBEDO / ref.max()
    pal = {"_doc": "Showhome albedo palette sampled from the concept art (see _src/sample_palette.py). "
                   "'sampled_srgb' = sun-lit colour in the concept (0-255); 'albedo_srgb' / 'albedo_linear' = the "
                   "value the textures are matched to (warm cast mostly removed, truck white = %.2f linear). "
                   "Linear values go straight into a Blender / Bevy base colour." % WHITE_ALBEDO,
           "sun_cast_linear": [round(float(x), 4) for x in cast],
           "neutralise": NEUTRALISE, "exposure": round(float(exposure), 4),
           "materials": {}}
    for mat, v in results.items():
        lin = srgb_to_lin(v)
        alb_lin = np.clip(lin / cast ** NEUTRALISE * exposure, 0, 1)
        entry = {"sampled_srgb": [int(round(x * 255)) for x in v]}
        if mat in CHROMA:
            y = float(alb_lin @ np.array([0.2126, 0.7152, 0.0722]))
            alb_lin = np.clip(y + (alb_lin - y) * CHROMA[mat], 0, 1)
            entry["chroma"] = CHROMA[mat]
        if mat in OVERRIDES:
            col, why = OVERRIDES[mat]
            entry["formula_srgb"] = [int(round(x * 255)) for x in lin_to_srgb(alb_lin)]
            alb_lin = srgb_to_lin(np.array(col) / 255.0)
            entry["override"] = why
        entry["albedo_srgb"] = [int(round(x * 255)) for x in lin_to_srgb(alb_lin)]
        entry["albedo_linear"] = [round(float(x), 4) for x in alb_lin]
        pal["materials"][mat] = entry
    # derived materials (not visible enough in the concept to sample): mixes of sampled albedos, linear space
    for mat, (parts, gain, why) in DERIVED.items():
        lin = sum(w * np.array(pal["materials"][m]["albedo_linear"]) for m, w in parts) * gain
        pal["materials"][mat] = {"derived": why, "albedo_srgb": [int(round(x * 255)) for x in lin_to_srgb(lin)],
                                 "albedo_linear": [round(float(x), 4) for x in np.clip(lin, 0, 1)]}
    with open(os.path.join(HERE, "palette.json"), "w") as f:
        json.dump(pal, f, indent=1)

    # verification sheet: sampled swatch | albedo swatch | label | every box crop with its own sample
    cw, ch = 150, 96
    W = 260 + 5 * (cw + 6)
    H = len(BOXES) * (ch + 8) + 8
    sheet = Image.new("RGB", (W, H), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for r, mat in enumerate(BOXES):
        y = 8 + r * (ch + 8)
        m = pal["materials"][mat]
        d.rectangle([4, y, 60, y + ch], fill=tuple(m["sampled_srgb"]))
        d.rectangle([62, y, 118, y + ch], fill=tuple(m["albedo_srgb"]))
        d.text((122, y + 4), mat, fill=(240, 240, 240))
        d.text((122, y + 20), "lit %s" % (m["sampled_srgb"],), fill=(200, 200, 200))
        d.text((122, y + 36), "alb %s" % (m["albedo_srgb"],), fill=(200, 200, 200))
        if "override" in m:
            d.text((122, y + 52), "override", fill=(255, 190, 90))
        row = [c for c in crops if c[0] == mat]
        for i, (_, name, box, v) in enumerate(row[:5]):
            x = 260 + i * (cw + 6)
            c = imgs[name].crop(box)
            c.thumbnail((cw, ch - 18))
            sheet.paste(c, (x, y))
            d.rectangle([x, y + ch - 16, x + cw, y + ch], fill=tuple(int(t * 255) for t in v))
    os.makedirs(os.path.join(HERE, "preview"), exist_ok=True)
    sheet.save(os.path.join(HERE, "preview", "palette_samples.png"))
    for mat, m in pal["materials"].items():
        if "sampled_srgb" not in m:
            print(f"{mat:18s} derived  albedo {m['albedo_srgb']}")
            continue
        print(f"{mat:18s} lit {m['sampled_srgb']}  albedo {m['albedo_srgb']}  {'(override)' if 'override' in m else ''}")
    print("sun cast", pal["sun_cast_linear"], "exposure", pal["exposure"])


if __name__ == "__main__":
    main()
