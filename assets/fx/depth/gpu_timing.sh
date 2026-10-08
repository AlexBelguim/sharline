#!/usr/bin/env bash
# GPU time of the opaque pass (where the parallax runs) per parallax level, from Bevy's render diagnostics.
# Needs a build with this local measurement patch in game/crates/val_etf/src/main.rs (before `app.run()`; not
# committed, the game does not ship it):
#
#     if std::env::var_os("VETF_GPU_TIMINGS").is_some() {
#         app.add_plugins((
#             bevy::render::diagnostic::RenderDiagnosticsPlugin,
#             bevy::diagnostic::LogDiagnosticsPlugin { wait_duration: std::time::Duration::from_secs(2), ..default() },
#         ));
#     }
#
# Prints the last few logged values of render/main_opaque_pass_3d/elapsed_gpu per view and level.
#
#   assets/fx/depth/gpu_timing.sh <exe> [view ...]
set -u
exe="$1"; shift
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
slot="C:/Users/alexw/AppData/Local/Temp/claude/F--git-val-etf/2097aa01-5216-40bf-b3f2-abfa2a86e2fa/scratchpad/slot.sh"
out="$root/game/target/gpu_depth"
cfg="$root/game/target/perf_config_depth"
mkdir -p "$out" "$cfg"
printf '(video: (frame_limit: Off, vsync: false, overlay: Fps))\n' > "$cfg/settings.ron"
declare -A CAM=(
  [street]="32.5,1.7,-9.5,35,1.2,-30"
  [aerial]="10,14,-2,30,0,-30"
  [gravel]="18,1.6,-12.8,18.5,0,-7"
  [path]="28.6,1.6,-19.5,28.6,0.4,-27.5"
  [lawn]="24,1.7,-16,25,0,-30"
)
views=("$@")
[ ${#views[@]} -eq 0 ] && views=(street gravel)
for v in "${views[@]}"; do
  for level in ${LEVELS:-off medium high ultra}; do
    log="$out/${v}_${level}.log"
    VETF_GPU_TIMINGS=1 VETF_CONFIG_DIR="$cfg" VETF_SURFACE_DEPTH="$level" bash "$slot" game "$exe" --host showhome \
      --live --port $((48100 + RANDOM % 800)) --camera "${CAM[$v]}" --demo-ui overlay \
      --screenshot "$out/${v}_${level}.png" --screenshot-after 3 --exit-after 16 --width 2560 --height 1080 \
      > "$log" 2>&1
    vals=$(grep -a 'main_opaque_pass_3d/elapsed_gpu' "$log" | tail -4 | sed -E 's/.*elapsed_gpu *: *([0-9.]+)ms.*/\1/' | tr '\n' ' ')
    echo "$v $level opaque_gpu_ms: $vals"
  done
done
