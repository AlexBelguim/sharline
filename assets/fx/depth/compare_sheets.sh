#!/usr/bin/env bash
# The before / after comparison sheets of the depth work (same camera, before on the left), from the shots that
# shots.sh took with suffixes `before` (the build without parallax) and `after` (plus `medium` / `ultra` for the
# quality levels). Writes game/target/shots/depth/cmp_*.png.
set -eu
here="$(cd "$(dirname "$0")" && pwd)"
d="$here/../../../game/target/shots/depth"
s() { python "$here/sheet.py" "$@"; }
s "$d/cmp_path.png" pathnear:before pathnear:after --w 800 --crop 400,300,1200,900
s "$d/cmp_wall.png" wall:before wall:after --w 800 --crop 340,100,740,500
s "$d/cmp_roof.png" roofpod:before roofpod:after --w 800 --crop 560,330,1000,700
s "$d/cmp_gravel.png" gravelnear:before gravelnear:after gravel:before gravel:after --w 800 --crop 400,350,1200,900
s "$d/cmp_asphalt.png" asphalt:before asphalt:after --w 800 --crop 500,450,1300,900
s "$d/cmp_normal_view.png" street:before street:after aerial:before aerial:after --w 800
s "$d/cmp_thin_parts.png" reveal:before reveal:after parapet:before parapet:after --w 800 --crop 640,240,1040,700
s "$d/cmp_levels.png" gravelnear:medium gravelnear:after gravelnear:ultra roofpod:medium roofpod:after \
  roofpod:ultra --cols 3 --w 600 --crop 600,500,1000,800
