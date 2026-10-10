"""Generate the RAW (non-seamless) Krea2 source images for the Showhome texture library
(local ComfyUI @127.0.0.1:8188, Krea2 Turbo). Seamless processing, palette matching and the procedural
structure (ridges, slab grids, cells) happen afterwards in build_textures.py.

Prompts describe the SURFACE only (never "tile"/"tileable": the model draws literal tiles). Colour in the raw
does not matter much: build_textures.py re-colours every texture to the albedo sampled from the concept art
(palette.json, written by sample_palette.py).

Usage:  python gen_raw.py [name ...] [--seeds 1 2] [--force]      (no names = all)
Writes: _src/raw/<name>_s<seed>.png  (existing files are skipped unless --force)
"""
import argparse
import os
import sys

sys.path.insert(0, r"F:/git/val etf/tools")
import comfy_gen  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")

TAIL = "flat even lighting, no borders, no objects, no text, stylized hand-painted game texture, soft painterly brushwork"
TOP = "seen from directly above"
FRONT = "viewed straight on"

PROMPTS = {
    # painterly detail for the cream 3D-printed walls (the ridges themselves are procedural, perfectly level)
    "printed_concrete": f"uniform close-up of a 3D printed concrete wall made of stacked horizontal extruded layers, "
                        f"rounded beads running perfectly horizontal and evenly spaced, warm cream concrete, {FRONT}, "
                        f"{TAIL}",
    "fibercement": f"uniform close-up of a smooth matte fibre cement facade board, faint fine vertical streaks and "
                   f"subtle soft painted mottling, light neutral grey, {FRONT}, no joints, no screws, {TAIL}",
    "roof_slate": f"uniform close-up of dark charcoal grey slate roof shingles laid in neat staggered horizontal rows, "
                  f"{FRONT}, matte, {TAIL}",
    "asphalt": f"uniform close-up of a smooth dark grey asphalt road surface {TOP}, fine aggregate speckles and "
               f"subtle soft mottling, no road markings, no cracks, {TAIL}",
    "asphalt_cracked": f"uniform close-up of an old dark grey asphalt road surface {TOP}, fine aggregate speckles, "
                       f"a few thin branching hairline cracks and a faint darker sealed patch, no road markings, {TAIL}",
    # v2: the first wording gave a big dark oil-stain blob that would repeat visibly
    "asphalt_cracked_v2": f"uniform close-up of an old smooth dark grey asphalt road surface {TOP}, fine aggregate "
                          f"speckles, several long thin branching hairline cracks spread evenly across the whole "
                          f"surface, no stains, no patches, no puddles, no road markings, {TAIL}",
    "concrete_smooth": f"uniform close-up of light grey smooth cast concrete surface {TOP}, subtle soft mottling and "
                       f"a few tiny pores, matte, no joints, no cracks, {TAIL}",
    "grass": f"uniform close-up of a neatly mown lawn {TOP}, short grass painted in small soft brush strokes, warm olive "
             f"green and fresh yellow green tones, no flowers, no soil, {TAIL}",
    "hedge": f"uniform close-up of the flat side of a dense trimmed boxwood hedge, many small leaves in clustered "
             f"painterly clumps, deep green with warm yellow-green highlights, no sky, no gaps, {TAIL}",
    "picket_wood": f"uniform close-up of a white painted wooden board, faint straight vertical wood grain showing "
                   f"through the paint, {FRONT}, no knots, no nails, no joints, {TAIL}",
    "soil": f"uniform close-up of dark brown garden soil {TOP}, crumbly loose earth with small soft clumps, no plants, "
            f"no stones, {TAIL}",
    "sand": f"uniform close-up of compacted construction site sand and earth {TOP}, warm tan, faint soft ripples and a "
            f"few small pebbles, no footprints, no tyre tracks, {TAIL}",
    # v2: the first wording drew strong desert ripples (reads as a beach, not a building plot)
    "sand_v2": f"uniform close-up of flat compacted sandy earth on a building plot {TOP}, warm tan, soft broad "
               f"painterly colour patches and a few tiny pebbles, no ripples, no dunes, no footprints, no tyre tracks, "
               f"{TAIL}",
    "gravel": f"uniform close-up of fine pale grey beige gravel {TOP}, small rounded pebbles packed evenly, {TAIL}",
    "cardboard": f"uniform close-up of a plain brown kraft cardboard surface, faint paper fibres and subtle mottling, "
                 f"no tape, no print, no folds, no corrugation, {TAIL}",
    "white_paint": f"uniform close-up of a clean off-white painted metal panel, very subtle soft brush strokes and a "
                   f"few faint smudges, matte, no rivets, no seams, {TAIL}",
    "yellow_paint": f"uniform close-up of a warm yellow painted steel surface with slightly worn paint, a few small "
                    f"chips and soft painterly brush strokes, matte, no rivets, no seams, {TAIL}",
    "wood_boards": f"uniform close-up of weathered brown stained wooden cladding boards running vertically, soft "
                   f"straight wood grain, {FRONT}, no knots, no nails, {TAIL}",
    "glass_smudge": f"uniform close-up of a sheet of slightly frosted clear glass over a plain light grey background, "
                    f"faint soft smudges and dried water marks, no reflections, no frame, {TAIL}",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--seeds", type=int, nargs="+", default=[11])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--prompt", default=None, help="override prompt (single name only)")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    for n in a.names or list(PROMPTS):
        for s in a.seeds:
            out = os.path.join(RAW, f"{n}_s{s}{a.tag}.png")
            if os.path.exists(out) and not a.force:
                print("skip", out)
                continue
            print("GEN", n, s, flush=True)
            comfy_gen.generate(a.prompt or PROMPTS[n], out, 1024, 1024, s, 8, tileable=False)


if __name__ == "__main__":
    main()
