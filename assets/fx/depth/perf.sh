#!/usr/bin/env bash
# Frame cost of the parallax depth: the same fixed cameras with VETF_SURFACE_DEPTH off / medium / high / ultra,
# no frame cap, the performance overlay on, at 2560x1080 so the GPU (not the CPU) sets the frame time.
#
#   assets/fx/depth/perf.sh <exe> [view ...]        (views as in shots.sh; default: street aerial gravel)
#
# Writes game/target/shots/depth/perf_<view>_<level>.png and a sheet of the overlay readouts,
# game/target/shots/depth/_perf.png. The GPU is shared with ComfyUI and other agents: repeat to trust a number.
set -u
exe="$1"; shift
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
slot="C:/Users/alexw/AppData/Local/Temp/claude/F--git-val-etf/2097aa01-5216-40bf-b3f2-abfa2a86e2fa/scratchpad/slot.sh"
out="$root/game/target/shots/depth"
cfg="$root/game/target/perf_config_depth"
mkdir -p "$out" "$cfg"
# Partial settings: every missing field keeps its default (HIGH preset). No frame cap, no v-sync.
printf '(video: (frame_limit: Off, vsync: false, overlay: Fps))\n' > "$cfg/settings.ron"
declare -A CAM=(
  [street]="32.5,1.7,-9.5,35,1.2,-30"
  [aerial]="10,14,-2,30,0,-30"
  [gravel]="18,1.6,-12.8,18.5,0,-7"
  [path]="28.6,1.6,-19.5,28.6,0.4,-27.5"
  [wall]="21.7,1.6,-15.2,21.15,1.3,-22"
)
views=("$@")
[ ${#views[@]} -eq 0 ] && views=(street aerial gravel)
items=()
for v in "${views[@]}"; do
  for level in off medium high ultra; do
    img="$out/perf_${v}_${level}.png"
    rm -f "$img"
    VETF_CONFIG_DIR="$cfg" VETF_SURFACE_DEPTH="$level" bash "$slot" game "$exe" --host showhome --live \
      --port $((48100 + RANDOM % 800)) --camera "${CAM[$v]}" --demo-ui overlay --screenshot "$img" \
      --screenshot-after 8 --exit-after 10 --width 2560 --height 1080 > "$img.log" 2>&1
    [ -f "$img" ] && items+=("$img") || echo "FAILED $v $level"
  done
done
python - "$out/_perf.png" "${items[@]}" <<'EOF'
import os, sys
from PIL import Image, ImageDraw
out, files = sys.argv[1], sys.argv[2:]
crops = []
for f in files:
    im = Image.open(f).convert("RGB")
    crops.append((os.path.basename(f)[5:-4], im.crop((0, 0, 360, 40)).resize((540, 60))))
sheet = Image.new("RGB", (540 + 200, 64 * len(crops)), (20, 20, 24))
d = ImageDraw.Draw(sheet)
for i, (name, c) in enumerate(crops):
    sheet.paste(c, (200, i * 64))
    d.text((6, i * 64 + 24), name, fill=(235, 235, 235))
sheet.save(out)
print(out)
EOF
