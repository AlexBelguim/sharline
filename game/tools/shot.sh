#!/usr/bin/env bash
# One 1920x1080 screenshot of the game, for agents and tests on the user's desktop (Git Bash on Windows, or
# any shell with python + Pillow). Run it from the repository root or from game/:
#
#   game/tools/shot.sh OUT.png [game args...]          e.g.  game/tools/shot.sh /tmp/host.png --demo-ui menu-host
#
# - Builds nothing: run `cargo build -p val_etf` first (it uses game/target/debug/val_etf[.exe]).
# - Screenshot runs render 1:1, never grab the mouse, do not take the keyboard focus and ignore the desktop's
#   mouse and keys (see game/README.md, "Screenshot and demo runs"), so the user can keep working.
# - The window really opens on the desktop: it always exits after EXIT seconds (default 8). The screenshot is
#   taken AFTER seconds in (default 4; with --host / --join counted from entering the match).
# - Settings go to a throwaway config dir (VETF_CONFIG_DIR, default game/target/shot_config), never yours.
# - The user may minimise or resize windows while it runs: a wrong-sized image is retried once.
# - The run's log is OUT.log next to the image.
set -u
out="$1"; shift
root="$(cd "$(dirname "$0")/../.." && pwd)"
exe="$root/game/target/debug/val_etf"
[ -f "$exe.exe" ] && exe="$exe.exe"
export VETF_CONFIG_DIR="${VETF_CONFIG_DIR:-$root/game/target/shot_config}"
mkdir -p "$VETF_CONFIG_DIR" "$(dirname "$out")"
size() { python -c "import sys; from PIL import Image; print('%dx%d' % Image.open(sys.argv[1]).size)" "$1" 2>/dev/null; }
for attempt in 1 2; do
  rm -f "$out"
  "$exe" --width 1920 --height 1080 --screenshot "$out" --screenshot-after "${AFTER:-4}" \
    --exit-after "${EXIT:-8}" "$@" > "$out.log" 2>&1
  got="$(size "$out")"
  if [ "$got" = "1920x1080" ]; then
    echo "$out 1920x1080"
    grep -aiE " (ERROR|WARN) " "$out.log" | grep -viE "wgpu|vulkan|naga|winit::state" | tail -5
    exit 0
  fi
  echo "attempt $attempt: got '${got:-no image}', see $out.log" >&2
done
exit 1
