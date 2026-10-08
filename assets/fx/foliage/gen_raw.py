"""Krea2 raws for the foliage card atlases (hedge leaf clusters, lawn grass tufts).

Each raw is a sheet of separate clusters on a plain white background. `build_atlas.py` keys the background to alpha,
cuts the clusters out and packs them into the game atlases, so the raw's colour and layout only need to be close:
the build re-colours every card to the Showhome palette (hedge 98 112 52, grass 126 140 58 sRGB).

Prompts describe the subject only (never "tile" / "tileable": the model would draw literal tiles).

Usage:  python gen_raw.py [name ...] [--seeds 11 12] [--force]      (no names = all)
Writes: raw/<name>_s<seed>.png (existing files are skipped unless --force)
Needs ComfyUI with Krea2 Turbo at http://127.0.0.1:8188 (tools/comfy_gen.py).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "tools")))
import comfy_gen  # noqa: E402

RAW = os.path.join(HERE, "raw")

TAIL = ("stylized hand-painted game asset, soft painterly brushwork, flat even lighting, no cast shadows, "
        "plain flat white background, nothing touches the edges")

PROMPTS = {
    # dense rounded leaf bunches: the hedge shell is made of these, so they must be nearly solid in the middle
    "hedge_box": "a sheet of nine separate small rounded clusters of dense boxwood foliage arranged in a loose three "
                 "by three grid with white space between them, each cluster a tight bushy clump of many small oval "
                 "leaves overlapping each other, deep olive green leaves with warm yellow-green highlights on the leaf "
                 f"tips and darker green between them, seen from the front, {TAIL}",
    "hedge_privet": "a sheet of nine separate small bushy clumps of privet hedge leaves arranged in a loose three by "
                    "three grid with white space between them, each clump a dense rounded bunch of many small pointed "
                    "oval leaves, deep green with soft yellow-green sunlit leaf edges, painterly, seen from the front, "
                    f"{TAIL}",
    # less symmetric than the two above (their rosette centres repeat when many cards overlap)
    "hedge_clump": "a sheet of nine separate irregular lumpy clumps of clipped hedge foliage arranged in a loose three "
                   "by three grid with white space between them, each clump an uneven asymmetric bushy mass of many "
                   "small soft leaves with a bumpy leafy outline, olive green with warm yellow-green tips and deeper "
                   f"green in the hollows, seen from the front, {TAIL}",
    # The concept paints its hedges with big soft flat strokes, no single leaves: these match it best.
    "hedge_paint": "a sheet of nine separate soft rounded clumps of clipped hedge foliage arranged in a loose three "
                   "by three grid with white space between them, each clump painted with a few big flat painterly "
                   "brush strokes like a stylized oil painting, no individual leaves visible, soft lumpy outline with "
                   "a few small leafy bumps, olive green with warm yellow-green light on the upper strokes and deeper "
                   f"green lower down, {TAIL}",
    # short tufts, root at the bottom: the lawn cards stand upright on the ground
    "grass_tuft": "a sheet of twelve separate small tufts of short mown lawn grass arranged in a loose grid with white "
                  "space between them, each tuft a dense fan of short soft grass blades growing upward from one narrow "
                  "base, seen from the side, olive green at the base and fresh yellow-green blade tips, no soil, "
                  f"no flowers, {TAIL}",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    for name in a.names or list(PROMPTS):
        for seed in a.seeds:
            out = os.path.join(RAW, f"{name}_s{seed}.png")
            if os.path.exists(out) and not a.force:
                print("skip", out)
                continue
            comfy_gen.generate(PROMPTS[name], out, 1024, 1024, seed)


if __name__ == "__main__":
    main()
