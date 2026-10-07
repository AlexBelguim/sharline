# Handoff: where the game code stands and what is next

Branch: `claude/game-netcode-build-nam9mt` (PR #1). Everything below is committed and pushed. Read `CLAUDE.md`,
`game/README.md` and `game/DESIGN_DELTAS.md` first: the deltas file lists every place the code deliberately differs
from `design/` because of the user's direction.

## Done
- **Sim + netcode** (Bevy 0.19, lightyear 0.30, listen server, prediction, lag-compensated shot claims).
- **Damage model:** per-zone HP, per-arc halo shields (shield is a buffer; pen multiplies shield damage per tier),
  ammo = class × type × tier (STD, AP I-III, RIP I-III SMG-only, Slug, NPC-only Shrapnel). Balance pass v2 applied;
  `crates/vetf_sim/tests/balance.rs` pins the breakpoints. Three guns: AR-7 Mako, VK-50 Warden, SK-9 Skink (SMG).
- **Six ordered magazines** per loadout, each with its own ammo (tap R = next slot with rounds, hold R = magazine
  ring, 1-6 pick), gear budget 13 priced per magazine.
- **Rulesets:** TDM has per-region shields/HP but no bleeding or broken-limb penalties; the range runs full rules.
- **Healing items** (`assets/data/items.ron`), heal ring on H with a second region ring; TDM only gets whole-body items.
- **HUD:** compact boss-bar vitals (shield strip per arc over segmented HP, BLEED/BROKEN chips), no gun panel,
  mag-check card only.
- **UI kit** (`crates/val_etf/src/ui_kit/`): mockup tokens, Barlow fonts + `TextRole` type scale, interaction looks,
  widgets, icons rasterised from the mockups (`game/tools/ui_raster.cjs`, `game/tools/ui_shapes.py`).
- **Screen stack** (`screens.rs`), per-user RON config (`user_config.rs`), `ActiveLoadout` + `summary()` contract.
- **Hub screens, wave 1** (spec: `game/docs/hub_spec/`, agent reports: `game/docs/hub_spec/wave1_reports.md`,
  screenshots: `game/docs/hub_spec/shots/`):
  - **Main menu** (`menu/`): built and merged (shell, HOST GAME and JOIN GAME flyouts, player card with MAGS and GEAR).
    Its critique and fix pass did not run.
  - **Loadout** (`loadout/`): built and merged (6-slot magazine strip, ammo picker, attachment popover, custom
    per-arc halo, presets, `LoadoutUpdate` message). The critique ran (issues listed in `wave1_reports.md` under
    `critique:loadout`); the fix pass did not run.
  - **Settings** (`settings/`): work in progress only (model, persistence, bindings; `controls.rs` and
    `keybinds.rs` exist but are not wired in). The tab UI is not built.

## Next, in order
1. **Settings screen:** finish it from `game/docs/hub_spec/07_*.md` to `13_*.md` + `style.md` (all six tabs, wire
   keybinds / sensitivity / FOV / reload hold time into `client.rs`, `render.rs`, `radial.rs`).
2. **Loadout fix pass:** work through the `critique:loadout` issues in `wave1_reports.md`.
3. **Main menu critique + fix:** compare `shots/menu-*_final.png` with `design/ui/mockups/png/04*.png`.
4. **Kit-wide colour issue** (from the menu report): translucent kit tokens render 2-3× too bright because Bevy
   blends in linear light; the menu worked around it locally (`menu::browser*`). Move that fix into the kit.
5. **Wave 2:** ESC menu + confirm modals (`15_*.md`, `16_*.md`), scoreboard (`06_*.md`), death recap (`17_*.md`).
6. **Wave 3:** lobby (`05_*.md`): replicated lobby state, ready, teams, chat, START MATCH; CREATE LOBBY goes there.
7. Review the merged diff (bugs + mockup fidelity) and fix findings.

## Working notes
- Build: `cd game && cargo build -p val_etf`, `cargo test --workspace`, `cargo clippy --workspace --all-targets`
  (keep both warning-free and green).
- Screenshots in a headless container: Xvfb + lavapipe:
  `DISPLAY=:99 VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json ./target/debug/val_etf --width 1920 --height 1080
  --demo-ui <value> --screenshot out.png --screenshot-after 4 --exit-after 9`. Demo values: `menu-join`,
  `menu-join-ip`, `menu-host`, `loadout`, `loadout-ammo`, `loadout-attach`, `reload`, `heal`, `heal-region`, `hud`
  (see `--help`). Set `VETF_CONFIG_DIR` to a temp dir so test runs do not touch your saved settings.
- Parallel agents in git worktrees: worktrees are cut from the default branch, so reset each to this branch's tip
  first. Do not share one `CARGO_TARGET_DIR` between worktrees: cargo can reuse another worktree's build of the
  same package (see the hazard in `wave1_reports.md`).
- Art/asset requests for the local session (cloud sessions must not edit `art/`, `assets/`, `design/`): a Skink
  model and weapon-tab silhouette, per-arc halo tier colours, the mockups' port 7777 -> 47820. The UI icons and
  images in `game/assets/ui` are derived from `design/ui/mockups`.
