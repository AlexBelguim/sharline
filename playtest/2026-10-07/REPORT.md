# Local playtest on a real GPU: 2026-10-07

**Machine:** the user's PC. i9-14900KF, RTX 5080 (Vulkan backend, driver 616.56), Windows 11. Build: `main` @ a4ab381,
`cargo build --release -p val_etf` (6m19s cold).

## What works
- The release build runs on the RTX 5080. GPU clustering and GPU preprocessing are supported.
- `--host range`: hosts on UDP 47820 and shows a join code. The HUD shows the halo panel, per-zone HP and the
  weapon panel, with no ammo count, as intended.
- **Two processes on one PC:** `--host showhome` plus a second process `--join 127.0.0.1:47820`. The client
  connects, is assigned team B and spawns. The joiner renders the map, its spawn and the HUD correctly
  (`showhome_friend_nobot.png`).
- (`showhome_friend.png` is grey only because the `--bot --yaw 90` bot faces a wall; not a bug.)

## Issues for the game session
1. **Range shows the TDM team score bar** ("0 | GUN RANGE | 0") (`range_host.png`). The range has no teams. Hide
   the team scores there, or show range-specific info instead.
2. **A thin yellow vertical line hangs below the crosshair** on the range, right after spawn
   (`range_host.png`, from screen centre down to about y=63%). Probably a tracer or debug ray drawn from the muzzle
   or camera. Check that it isn't a leftover debug gizmo.
3. HiDPI: `--width 1600 --height 900` produced a 3200x1800 screenshot. The window is scaled by the Windows
   display scale. Fine, but the README could mention it.

## User decisions since the last sync (see `art/DIRECTION_LOG.md` items 9-10)
- Per-arc armor tiers and ammo class × type × tier: accepted. `art/HALO_SHIELD_SPEC.md` is updated so each arc
  shows its own tier colour (plus `unlit` and `broken` states).
- **Map themes:** TDM = **Showhome** (near-future 3D-printed show homes, half-built suburb, delivery truck, crane).
  Range / hub "The Yard" = **Nordic fjord** setting. The local session will make the art pass (Blender → glTF) on
  top of the existing layouts.

## Coming from the local session (assets)
Rigged characters (Kestrel, Solace), modular weapons (Mako, Warden + optics, tactical attachments) with
sockets and an `attachments.json` catalog, and the halo kit, as `.glb` under `assets/`. They are going through
review and fixes now. A follow-up note will list the final paths and node names to load.
