"""Krea2 raws for the bullet-hole atlas: painterly grain and colour of the material a shot exposes.

The structure of every mark (crater, bore, cracks, splinters, chipped rings) is procedural (build_atlas.py);
these raws only give the painterly grain and mottling inside it, like the Showhome texture library does
(assets/maps/showhome/textures/README.md). Prompts describe the surface only and never say "tile".

Usage:  python gen_raw.py [name ...] [--seeds 11 12] [--force]      (no names = all)
Writes: _src/raw/<name>_s<seed>.png  (existing files are skipped unless --force)
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "tools")))
import comfy_gen  # noqa: E402

RAW = os.path.join(HERE, "raw")

TAIL = "flat even lighting, no borders, no objects, no text, stylized hand-painted game texture, soft painterly brushwork"
TOP = "seen from directly above"
FRONT = "viewed straight on"

PROMPTS = {
    # the inside of a crater in the cream printed concrete / plaster
    "rubble_cream": f"uniform close-up of crushed cream concrete and plaster crumbs with fine pale dust {TOP}, small "
                    f"angular chips, warm cream and light beige, {TAIL}",
    # the core a shot exposes in fibre-cement cladding and slate
    "fibre_core": f"uniform close-up of the broken fibrous core of a grey fibre cement board {TOP}, short pale grey "
                  f"fibres and fine grit, {TAIL}",
    # torn fresh wood under paint or stain
    "wood_fresh": f"uniform close-up of freshly split pale pine wood {FRONT}, long straight torn fibres running "
                  f"vertically, light honey and cream tones, {TAIL}",
    # the bright rim of a hole punched through painted steel
    "bare_steel": f"uniform close-up of bright bare steel {FRONT}, fine scratches and soft brushed streaks, cool light "
                  f"grey, {TAIL}",
    # chipped asphalt, paving and kerb stone
    "stone_chips": f"uniform close-up of freshly chipped grey stone aggregate and asphalt grit {TOP}, small angular "
                   f"light grey chips and fine dust, {TAIL}",
    # a scuffed puff of lawn, soil or gravel
    "soil_dark": f"uniform close-up of dark brown loose soil crumbs {TOP}, crumbly earth with tiny clumps and fine "
                 f"dust, no plants, no stones, {TAIL}",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--seeds", type=int, nargs="+", default=[11, 12])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(RAW, exist_ok=True)
    for n in a.names or list(PROMPTS):
        for s in a.seeds:
            out = os.path.join(RAW, f"{n}_s{s}.png")
            if os.path.exists(out) and not a.force:
                print("skip", out)
                continue
            print("GEN", n, s, flush=True)
            comfy_gen.generate(PROMPTS[n], out, 1024, 1024, s, 8, tileable=False)


if __name__ == "__main__":
    main()
