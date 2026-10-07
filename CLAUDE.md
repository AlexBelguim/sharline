# val etf: project guide for Claude sessions

A stylized extraction-shooter prototype. It combines Escape-from-Tarkov-style gear decisions, Valorant-like
visuals and gunplay, and Apex-like movement (sprint, slide, jetpack, ziplines). The target is a playable
slice: a gun range with aim training, a loadout menu, a Valorant/EFT-style HUD with per-zone health, and a
small team deathmatch map. Multiplayer is host-and-join: the user hosts from inside the game and friends join.

## Read these first
- `art/DIRECTION_LOG.md`: the user's decisions. They override everything else.
- `art/STYLE_GUIDE.md`: the art bible. It covers axes and handedness (front = −Y, a character's or shooter's
  RIGHT = −X), palette, budgets and tools.
- `art/WEAPON_MODULAR_SPEC.md`: modular weapons, socket names and rail standard.
- `art/HALO_SHIELD_SPEC.md`: armor is a halo shield above the head. It encodes tier, coverage, core type and
  weight class.
- `design/`: game design for the slice (systems + netcode GDD, maps, UI). Its numbers are the source of truth
  for gameplay.

## Hard rules
- **No exact ammo counters anywhere**, on guns or in the HUD. Players mag-check for an estimate.
- Armor is equipment any agent can wear (a halo). Characters have no built-in armor tiers.
- Everyone can read an enemy's weight class (Light / Medium / Heavy) from their halo.
- Original designs only. Never copy assets, code or maps from other games.

## Engine and tech
- **Rust + Bevy**, code-first with no editor. Game code lives in `game/` (a Cargo workspace).
- Assets are exported from Blender as glTF (`.glb`, Z-up in Blender, Y-up in glTF). Weapons attach through
  named socket nodes (`*_SOCKET_*`). Characters use UE5 mannequin bone names.
- Netcode: a listen server, where the host is server and player at once. The design doc names the chosen
  crate and model.

## Who owns what
- `game/`: Rust/Bevy code. Cloud sessions work here, on their own branch, and open a PR.
- `art/`, `assets/`, `tools/`, `design/`: owned by the local session, because it has the GPU, ComfyUI
  (Krea2 / TRELLIS) and Blender. Cloud sessions must not edit these. If a code task needs an asset change,
  say so in the PR description.
- Large binaries (`.glb`, `.blend`, `.fbx`) are stored in Git LFS.

## Conventions
- Keep `cargo build` and `cargo test` green. Add tests for gameplay math (damage, recoil, movement curves,
  shield and health flow) and for netcode serialization.
- Every gameplay number lives in data (RON or TOML in `game/assets/data/`), not hard-coded, so it can be tuned.
- Commit messages: imperative, with a short scope prefix (e.g. `movement: add slide boost`).
