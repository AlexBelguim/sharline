#!/usr/bin/env bash
# Before / after screenshots of the Showhome parallax depth (agent "depth"): the same fixed cameras for any
# build. Run from anywhere:
#
#   assets/fx/depth/shots.sh <exe> <suffix> [view ...]   e.g.  assets/fx/depth/shots.sh game/target/debug/val_etf.exe after
#
# Images land in game/target/shots/depth/<view>_<suffix>.png. VETF_SURFACE_DEPTH=off|low|medium|high|ultra forces
# the parallax level (map_materials.rs) without touching the saved settings; settings come from a throwaway
# config dir (defaults: the HIGH preset). Every run goes through the machine-wide slot script.
# "Before" shots: the same exe with VETF_SURFACE_DEPTH=off (LOW gives every surface its library look back).
set -u
exe="$1"; suffix="$2"; shift 2
root="$(cd "$(dirname "$0")/../../.." && pwd)"
slot="C:/Users/alexw/AppData/Local/Temp/claude/F--git-val-etf/2097aa01-5216-40bf-b3f2-abfa2a86e2fa/scratchpad/slot.sh"
out="$root/game/target/shots/depth"
export VETF_CONFIG_DIR="${VETF_CONFIG_DIR:-$root/game/target/shot_config_depth}"
mkdir -p "$out" "$VETF_CONFIG_DIR"
# name -> camera (Bevy x,y,z,tx,ty,tz; design (x, y, z) is Bevy (x, z, -y))
declare -A CAM=(
  [path]="28.6,1.6,-19.5,28.6,0.4,-27.5"     # eye 1.6 m on the street pavement, looking north along it
  [wall]="21.7,1.6,-15.2,21.15,1.3,-22"      # along Sage House's printed east wall (ground floor)
  [roofpod]="18.2,4.8,-32.1,23.5,2.8,-34.5"  # from the upper-floor north window down at the greenhouse roof
  [gable]="13,4.8,-16.6,15,8.7,-24.5"        # from the terrace's south edge up the 45 degree gable (grazing)
  [gableclose]="15,4.8,-18.5,15.5,8.2,-24"    # the pitched main roof from the upper-floor terrace, 3-9 m away
  [gravel]="18,1.6,-12.8,18.5,0,-7"          # the gravel drive, looking south
  [asphalt]="31.5,1.6,-12,32,0,-18"          # the street asphalt, looking north
  [clad]="11.5,4.8,-21.3,20,4.6,-21.85"      # along the upper-floor fibre-cement cladding from the terrace
  [gravelnear]="18,1.6,-12.8,18.3,0,-10"     # the gravel drive at your feet (about 3 m ahead)
  [pathnear]="28.6,1.6,-19.5,28.4,0,-22.5"   # the pavement at your feet
  [lawn]="26.7,1.7,-15,26,0,-24"             # the Sage front lawn, looking north past the planters
  [lawnnear]="26.7,1.6,-15.5,26.4,0,-18.5"   # the lawn at your feet (about 3 m ahead)
  [reveal]="22,1.5,-17,21,1.5,-19"           # a window reveal in the printed garage wall (thin faces, edges)
  [parapet]="11.5,4.8,-16.5,20,4.2,-16"      # along the 25 cm terrace parapet top (a thin printed part)
  [gravelmv]="18.02,1.6,-12.8,18.52,0,-7"    # gravel, the camera moved 2 cm: the far ground's change = shimmer
  [streetmv]="32.52,1.7,-9.5,35.02,1.2,-30"  # street, moved 2 cm
  [street]="32.5,1.7,-9.5,35,1.2,-30"        # a normal playing view up the street
  [aerial]="10,14,-2,30,0,-30"               # overview
)
views=("$@")
[ ${#views[@]} -eq 0 ] && views=(pathnear path wall roofpod gable gableclose gravelnear gravel asphalt clad lawn lawnnear   street aerial reveal parapet)
size() { python -c "import sys; from PIL import Image; print('%dx%d' % Image.open(sys.argv[1]).size)" "$1" 2>/dev/null; }
for v in "${views[@]}"; do
  img="$out/${v}_${suffix}.png"
  # The desktop may minimise or resize the window mid-run: a wrong-sized image is retried.
  for attempt in 1 2 3; do
    rm -f "$img"
    # Its own port: other agents' games may be hosting on the default one at the same time.
    bash "$slot" game "$exe" --host showhome --live --port $((48100 + RANDOM % 800)) --camera "${CAM[$v]}" \
      --screenshot "$img" \
      --screenshot-after "${AFTER:-4}" --exit-after "${EXIT:-7}" --width 1600 --height 900 > "$img.log" 2>&1
    [ "$(size "$img")" = "1600x900" ] && break
  done
  if [ "$(size "$img")" = "1600x900" ]; then echo "$img"; else echo "FAILED $v (see $img.log)"; tail -3 "$img.log"; fi
done
