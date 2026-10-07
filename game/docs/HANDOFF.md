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

## Conventions for screens
Hub screens (Loadout, Settings, the ESC menu, modals, later the lobby and death recap) live on the screen stack in
`crates/val_etf/src/screens.rs`. The main menu and the match are the base under it (`AppState`).

- **Opening and closing:** `Screens::push(Screen::X)` opens over the current top (return to opener);
  `Screens::pop()` closes the top. Spawn your root (with `ScreenRoot(Screen::X)`) when your screen becomes the top;
  `despawn_closed` removes it when it leaves the stack. Z-order: `GlobalZIndex(100 + 10 × stack depth)`.
- **Esc: one press, one owner.** Never read `KeyCode::Escape` (a test fails if any module but `screens.rs` does).
  Take the press from the `EscPress` resource with `esc.take()`, which returns true once per press, from a system
  in the right `EscSystems` set. The sets run in this order in `Update`:
  1. `EscSystems::Read`: the key goes into `EscPress` (also `--esc-at`, below).
  2. `EscSystems::Top`: the top screen's own handler, gated with `.run_if(screen_on_top(Screen::X))`. Close the
     innermost open layer first (a listening key cap, an edited field, a popover, a dropdown). Take Esc only when
     you have such a layer, or when leaving needs work (Settings saving, a confirm). Example: `loadout::esc`.
  3. `EscSystems::Back`: `back_on_esc` pops the top screen when nobody in `Top` took the press. This is the default
     BACK, so a screen with nothing to close needs no Esc code: the ESC menu's Esc = RESUME and a modal's Esc =
     CANCEL come for free.
  4. `EscSystems::Base`: the base, which only ever sees Esc while no screen is open: `menu::keyboard` (name edit,
     then flyout back to the nav) and `client::esc_in_match` (a ring menu first, then the pause overlay).
  Inside a chain, put just the handler in the set: `(…, esc.in_set(EscSystems::Top), keys, …).chain()`.
- **Cursor and match input are derived, never set by a screen.** `screens::apply_cursor` (PostUpdate) is the only
  system that writes `CursorOptions`: free on the menus, over any open screen and while `LocalControl.paused`,
  locked in play, never grabbed in hands-off runs (`Cli::hands_off`). `client::gather_input` takes no input while
  a screen is open. So when a screen closes, the screen below (or the match) gets its own state back without any
  bookkeeping. Do not toggle `LocalControl.paused` from a screen.
- **The ESC menu (wave 2):** in `client::esc_in_match`, replace the `paused` toggle with
  `screens.push(Screen::Esc)` (after the ring-menu check) and retire the legacy pause overlay in `hud.rs`
  (`PauseRoot`, `pause_buttons`). RESUME = `screens.pop()`. Loadout and Settings opened from it return to it.
- **Mouse after a click that changes screens:** `LocalControl.mouse_block` keeps the mouse buttons off until they
  are released (set on entering the match, while paused or under a screen, and when the window regains focus), so
  the click on CONFIRM, RESUME or CREATE LOBBY never fires a shot.
- **Colours: the kit is the only place that blend-corrects.** Bevy blends UI in linear light, CSS in sRGB, so
  translucent mockup colours need another alpha in Bevy. Every translucent token and helper in
  `ui_kit/tokens.rs` (`STROKE*`, `W03`..`W70`, `PANEL*`, `white(a)`, `hexa(rgb, a)`, `translucent(c, a)`,
  `fade(c, a)`) already carries the corrected alpha: pass the CSS alpha, use the result as it is, and never
  correct it again (no `with_alpha` on a CSS `rgba(...)`). Over the main-menu art or the live match use
  `hexa_over(rgb, a, ART_REF)` (`PANEL_HI_OVER_ART`). A dark shade or scrim over anything: `scrim(rgb, a)` or
  `scrim_stops(..)` + `hexa_exact` for gradients (`MODAL_BACKDROP` and `SCOREBOARD_DIM` already are). Bevy does
  not paint a node's fill under its border while CSS does, so a border on a filled element uses
  `white_on(stroke_a, fill_a)` / `stroke_on_fill(..)` (the kit's `BTN`, `TILE`, `CHIP`, `LIST_ROW` looks do).
  Measured against the mockup PNGs, the menu and Loadout fills and hairlines land within about 5 levels.
- **Demo runs:** add a `--demo-ui <screen>` value that opens your screen (see `loadout::demo_open`), and check
  Esc with `--esc-at S,S,..` (Esc presses at those seconds after start-up).

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
