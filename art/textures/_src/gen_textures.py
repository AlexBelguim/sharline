"""Generate the RAW (non-seamless) source images for the shared detail-texture library with the local
Krea2 Turbo model (ComfyUI @127.0.0.1:8188). Seamless processing / normalisation happens afterwards in
process_textures.py, which can apply the same mirror-quilt as `comfy_gen.py --tileable` or a
variance-preserving offset cross-fade (no kaleidoscope symmetry) per texture.

Usage:  python gen_textures.py <name> [<name> ...] [--seed N] [--tag x]
Writes: _src/raw/<name>_s<seed><tag>.png
"""
import argparse
import os
import sys

sys.path.insert(0, r"F:/git/val etf/tools")
import comfy_gen  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

COMMON = ("flat even lighting, no borders, no objects, no text, neutral grey, "
          "stylized hand-painted game texture")

PROMPTS = {
    "worn_paint": "uniform close-up of a stylized hand-painted painted metal surface, visible soft broad brush "
                  "strokes in light grey paint with gentle tonal variation, a few scattered faint thin scratches "
                  "and tiny chipped paint marks, matte, " + COMMON,
    "brushed_metal": "uniform close-up of a stylized brushed metal sheet surface, fine straight horizontal "
                     "directional brushing streaks running across the whole frame, light neutral grey, matte, "
                     "no reflections, " + COMMON,
    "polymer_stipple": "uniform close-up of a fine stippled grip surface on matte polymer plastic, tiny evenly "
                       "distributed raised bumps and pits covering the whole frame, light neutral grey, " + COMMON,
    "fabric_ripstop": "uniform close-up of ripstop nylon fabric, fine tight canvas weave with a regular square "
                      "grid of slightly thicker reinforcement threads, light neutral grey cloth, flat, no folds, "
                      + COMMON,
    "fabric_soft": "uniform close-up of soft stretch knit fabric, fine jersey knit stitch rows covering the whole "
                   "frame, light neutral grey cloth, flat, no folds, no wrinkles, " + COMMON,
    "leather_soft": "uniform close-up of soft smooth leather surface with a subtle fine natural pebbled grain, "
                    "light neutral grey, matte, flat, no stitching, no folds, " + COMMON,
    "carbon_weave": "uniform close-up of carbon fiber twill weave, regular diagonal woven pattern of small "
                    "rectangular fiber bundles, light grey and mid grey, low contrast, matte, " + COMMON,
    # seed 1 used the earlier wording "uniform smooth matte painted surface in a warm light beige peach tone,
    # very subtle soft mottled painterly colour variation ..." -> crisp watercolour blotches (rejected)
    "skin_soft": "very soft smooth airbrushed surface in warm light peach beige, gentle subtle painterly variation "
                 "of warm and slightly cooler tones, soft blurred gradients, almost flat, matte, flat even "
                 "lighting, no borders, no objects, no text, stylized hand-painted game texture",
    # seed 1 used "...dense flowing vertical strands of straight hair..." -> wavy crossing locks (rejected)
    "hair_strands": "stylized hand-painted hair texture, sleek straight hair with long parallel vertical strands "
                    "running from top to bottom, soft painted strand clumps with fine highlight lines, filling the "
                    "whole frame, light neutral grey, flat even lighting, no borders, no objects, no text, "
                    "stylized game texture",
}


# Seeds of the generations the final textures were made from (see process_textures.CONFIG "src").
# carbon_weave: s1..s4 were generated (s2 with "perfectly regular ... 2x2 twill" wording) but all drift or
# break their pattern, so the shipped carbon_weave is procedural (make_carbon.py).
USED_SEEDS = {"worn_paint": 1, "brushed_metal": 1, "polymer_stipple": 1, "fabric_ripstop": 1, "fabric_soft": 1,
              "leather_soft": 1, "skin_soft": 2, "hair_strands": 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="+")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag", default="")
    ap.add_argument("--prompt", default=None, help="override prompt (single name only)")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    for n in a.names:
        p = a.prompt or PROMPTS[n]
        out = os.path.join(RAW, f"{n}_s{a.seed}{a.tag}.png")
        print("GEN", n, "->", out, flush=True)
        comfy_gen.generate(p, out, 1024, 1024, a.seed, 8, tileable=False)


if __name__ == "__main__":
    main()
