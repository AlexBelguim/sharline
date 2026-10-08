#!/usr/bin/env bash
# Krea2 test: ask Krea2 (identity edit, the albedo as the reference) for a greyscale height picture of the
# organic surfaces, whose structure is not procedural (gravel, lawn, soil). The results land in raw/ and
# build_depth.py compares them with the albedo-derived heights (alignment + look) before using any of them.
# ComfyUI must run on 127.0.0.1:8188. Albedos are read from the Showhome library (read-only).
set -u
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
lib="F:/git/val etf/assets/maps/showhome/textures"
mkdir -p "$here/raw"
gen() {  # name prompt seed
  python "$root/tools/comfy_gen.py" --ref "$lib/$1.png" --prompt "$2" --seed "$3" --ref-boost 6 \
    --out "$here/raw/krea_height_$1_s$3.png"
}
P="Convert this exact texture into a greyscale height map seen straight from above: the same shapes in the same \
places, white where the surface is high, black where it is low, smooth soft gradients, no colour, no lighting, no \
shadows, no highlights, no text."
gen gravel "$P Each pebble is a smooth rounded dome, brightest at its centre, the gaps between pebbles are black." 11
gen garden_soil "$P Each soil clump is a soft rounded lump, brightest on top, the flat soil between them is dark." 11
gen grass_lawn "$P Each grass blade is a bright soft stroke, its tip brightest, the ground between blades is dark." 11
