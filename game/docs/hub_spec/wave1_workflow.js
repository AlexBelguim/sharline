export const meta = {
  name: 'hub-screens-wave1',
  description: 'Build the main menu, Loadout and Settings hub screens from the mockup specs in parallel worktrees; critique against the mockups; fix',
  phases: [
    { title: 'Build', detail: 'one implementer per screen, in its own git worktree' },
    { title: 'Critique', detail: 'compare screenshots with the mockup PNGs and the spec' },
    { title: 'Fix', detail: 'implementer pass on the critique, in the same worktree' },
  ],
}

const SCRATCH = '/tmp/claude-0/-home-user-sharline/f1fd711c-0930-5d69-82cd-6289789756d2/scratchpad'
const SPEC = `${SCRATCH}/hubspec`
const PNG = '/home/user/sharline/design/ui/mockups/png'
const SRC = '/home/user/sharline/design/ui/mockups/_src'

const COMMON = `You are implementing one hub screen of SHARD/LINE, a Rust + Bevy 0.19 + lightyear 0.30 game (code in game/, a Cargo workspace: crates vetf_sim (engine-free gameplay), vetf_net (protocol), val_etf (the binary)). The user said the hub screens of the UI mockups are great and must be mirrored CLOSELY (exact layout, sizes, fonts, colours, copy), adapted to our game where the spec says so. You work in your own git worktree (your current directory is the repo root of that worktree); other agents build other screens in parallel in their own worktrees, so stay inside the files you own.

FIRST STEP (mandatory): the worktree you were given may be checked out at an old commit. Run
  git reset --hard fa0e42e472680f787747b992e8388da652dd6b7c
(the tip of branch claude/game-netcode-build-nam9mt, which has all the game code) and check that game/crates/val_etf/src/ui_kit/ exists before anything else. Never push and never touch the branch claude/game-netcode-build-nam9mt itself.

READ FIRST
- The shared style spec: ${SPEC}/style.md (tokens, typography = TextRole, components, icons, fonts, implementation order, cross-screen notes).
- The UI kit already built from it: game/crates/val_etf/src/ui_kit/ (tokens.rs, text.rs = UiFonts + TextRole type scale, look.rs = Looks/Active/Disabled/Ink/OnBar interaction styling, widgets.rs = panels, chrome, buttons, key caps, hints, nav rows, tabs, segments, inputs, stepper, switch, chips, pips, bars; icons.rs = Icon/Shape/Art -> Handle<Image> via the UiImages resource). Use it; do not hand-type sizes that have a TextRole. UiScale makes 1 mockup px = 1 Val::Px at 1080p.
- Contracts: game/crates/val_etf/src/screens.rs (overlay stack: Screens resource, Screen enum, ScreenRoot, screen_on_top; Esc pops the top), game/crates/val_etf/src/user_config.rs (load_or_default / save RON per file in the user's config folder; PlayerProfile), game/crates/val_etf/src/loadout/mod.rs (ActiveLoadout resource = what Hello sends; summary() formats a loadout for the player card / ESC menu).
- The existing code you replace or touch (read it before editing).

RULES
- Follow the project rules in CLAUDE.md (no exact ammo counters anywhere, every gameplay number in game/assets/data, never edit art/, assets/, tools/, design/ at the repo root; game/ is yours).
- Only edit the files listed under YOUR FILES. If you truly need a change elsewhere (e.g. a bug in ui_kit), make it minimal and list it in your report. You may ADD new files under game/crates/val_etf/src/ (your own module files) and new data/asset files under game/assets/.
- Builds share one target dir to save disk. ALWAYS prefix cargo with: CARGO_TARGET_DIR=/home/user/sharline/game/target  (run from game/). Use: cargo fmt --all; cargo clippy -p val_etf --all-targets (must be warning-free); cargo test -p val_etf (and -p vetf_sim / -p vetf_net if you touch them). The cargo lock may make you wait for other agents' builds; that is normal. Disk is limited: never run cargo clean, never create another target dir.
- Screenshots: build, then run the game on the shared X server and compare with the mockup PNGs (Read both images). Command (from game/):
  export DISPLAY=:99 VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json VETF_CONFIG_DIR=<a private temp dir>; CARGO_TARGET_DIR=/home/user/sharline/game/target timeout 120 cargo run -p val_etf -- --width 1920 --height 1080 --demo-ui <your-demo-name> --screenshot <png path> --screenshot-after 4 --exit-after 9
  (--screenshot-after counts from start-up on the menu, or from the match view when --host is used; if you host a match for an in-match overlay, add --host range --port <YOUR PORT> so you do not collide with other agents.) Add your own --demo-ui values inside YOUR module (a system that reads Res<Cli>.demo_ui and opens your screen/state); add the value to the --help text in config.rs only if that file is yours. Save screenshots under ${SCRATCH}/hub_shots/<screen>/. Software rendering is slow; that is expected.
- Keep cargo build/test green; add unit tests for any logic (formatters, persistence round trips, validation, mapping functions).
- Bevy 0.19 API notes: Node has border_radius; BorderColor::all / per side; TextFont::from_font_size(...).with_font(handle); LetterSpacing::Px; LineHeight; EditableText (bevy::text) for inputs with TextCursorStyle; ImageNode::new(handle).with_color(tint); UiTransform::from_rotation(Rot2::degrees(45.0)); BackgroundGradient with LinearGradient/RadialGradient (.in_color_space(InterpolationColorSpace::Srgba)); BoxShadow(vec![ShadowStyle{..}]); GlobalZIndex; Interaction on Button; children![] macro or Children::spawn(SpawnIter(..)); DespawnOnExit(AppState::X). Bevy's observer type is also called On, which is why the kit's selected marker is called Active.
- When done: commit your work in your worktree branch (several commits are fine). Commit messages: imperative with a scope prefix (e.g. "menu: ..."), ending with these two lines exactly:
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HEbP1FHVarbHJVc5MSaiMh
  Do not push. Report your worktree path (pwd), branch (git branch --show-current), the commits, what you built, deviations from the mockup and why, open items, and the screenshot paths.`

const SCREENS = [
  {
    key: 'menu', port: 47830,
    task: `YOUR SCREEN: the MAIN MENU (shell, PLAY > HOST GAME flyout, PLAY > JOIN GAME flyout).
Specs: ${SPEC}/00_main_menu_shell_backdrop_wordmark_left_nav_with_pl.md, ${SPEC}/01_main_menu_play_host_game_flyout.md, ${SPEC}/02_main_menu_play_join_game_flyout_tabs_join_code_dir.md (read every section: layout, elements, data_bindings, interactions, adaptations, assets).
Mockups: ${PNG}/04_main_menu.png (join open), ${PNG}/04b_main_menu_host.png (host open); sources ${SRC}/pages/main_menu.html, ${SRC}/common.css, ${SRC}/widgets.js.
YOUR FILES: game/crates/val_etf/src/menu.rs (rewrite; you may turn it into a menu/ folder), game/crates/val_etf/src/net.rs (host settings such as max players -> the netcode server's max clients and the port; recent servers; errors), game/crates/val_etf/src/user_config.rs (add types if needed), game/crates/val_etf/src/config.rs (the --name vs profile name, --help), game/crates/val_etf/src/main.rs (only resource insertion if needed), game/README.md (controls / menu section).
Decisions already made (follow them): CREATE LOBBY hosts Team Deathmatch on Showhome directly for now (the lobby screen comes later; use the spec's phase-1 copy). GUN RANGE hosts the range (right label 'FRIENDS CAN JOIN'). LOADOUT and SETTINGS rows are ENABLED and push Screen::Loadout / Screen::Settings(SettingsTab::Gameplay) on the Screens stack (other agents build those screens; until merged they show nothing, that is fine). QUIT exits. The password field is rendered disabled ('optional · not available yet'); no protocol change. LAN discovery is not built: follow adaptation J3. The player card uses loadout::summary(&ActiveLoadout.0, &data) for the loadout line, the MAGS line (six slots, '—' for unused) and the GEAR cost / budget readout (OVER BUDGET in --bad). Name editing persists PlayerProfile (profile.ron); --name on the command line overrides it; Session.local_name must follow it before connecting. Keep the command-line --host / --join automation and the connect / error flow working. Version line per adaptation S3.
Demo values to add: --demo-ui menu-join (join flyout open, code tab), menu-join-ip (direct IP tab), menu-host (host flyout open).`,
  },
  {
    key: 'loadout', port: 47840,
    task: `YOUR SCREEN: the LOADOUT hub screen (incl. the attachment list popover and the ammo picker for the new 6-slot ordered magazine strip).
Specs: ${SPEC}/03_loadout_hub_screen.md, ${SPEC}/04_loadout_attachment_list_popover_and_the_magazine_a.md, ${SPEC}/21_halo_widget_states_and_weight_classes_reference_pa.md (halo widget), plus style.md.
Mockups: ${PNG}/05_loadout.png, ${PNG}/05b_loadout_attachment_list.png; sources ${SRC}/pages/loadout.html, ${SRC}/common.css, ${SRC}/widgets.js (haloSVG) and ${SRC}/icons.svg.
YOUR FILES: game/crates/val_etf/src/loadout/ (the screen, presets persistence loadouts.ron with presets A/B/C, the ActiveLoadout contract: keep summary() and ActiveLoadout working for the other screens and update them if LoadoutChoice changes), game/crates/vetf_net/src/protocol.rs (LoadoutChoice changes, a new LoadoutUpdate client->host message, PROTOCOL_VERSION bump, serialization tests), game/crates/val_etf/src/server.rs (loadout_from_choice validation + tests, applying a LoadoutUpdate at the next spawn), game/crates/val_etf/src/config.rs (loadout_choice from the CLI), game/crates/vetf_sim/ (a shared gear-cost function used by the host and the UI; custom per-arc armor resolution), game/assets/data/*.ron (new display fields such as names / blurbs; keep crates/vetf_sim/tests/design_sync.rs green), game/tools/ and game/assets/ui/ (e.g. halo widget layer PNGs rendered with Playwright like game/tools/ui_raster.cjs does; run node with PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers).
Decisions already made: magazines are a CONTIGUOUS ordered list of 1..=6 (slot 1 is in the gun at spawn; no gaps, so the sim's slot index = the reload-wheel position): '+ ADD MAG' appears only on the first empty slot, a mag can be removed only from the end, and dragging a card onto another swaps their ammo. Each mag's ammo is picked in the ammo picker (type x tier, only what the gun can load, players' ammo only), with its gear cost; the RESULT panel shows halo + all mags vs the TDM gear budget; CONFIRM is disabled while over budget. Armor becomes a custom halo: one core + a tier per arc (head/torso/arms/legs) within loadout_tier_caps, instead of a preset id (the CLI --armor preset id still works and converts). Agents (Kestrel, Solace) are cosmetic for now: show the cards as in the mockup; the choice is stored but does nothing in game. There are THREE weapons (AR-7 Mako, VK-50 Warden, SK-9 Skink SMG); the icon set has no Skink silhouette: use a text-only or reused silhouette and note it as an art request. The screen opens from the main menu and over a running match (Screen::Loadout); in a match, CONFIRM sends LoadoutUpdate and the host applies it at the next spawn ('In match: changes apply on your next spawn'). Esc / BACK pops the screen. CONFIRM updates ActiveLoadout and saves the preset.
Demo values to add: --demo-ui loadout (on the main menu), loadout-ammo (ammo picker open on MAG 1), loadout-attach (attachment popover open on the optic slot).`,
  },
  {
    key: 'settings', port: 47850,
    task: `YOUR SCREEN: the SETTINGS hub screen: the shared frame and all tabs (gameplay & network, mouse & aim, keybinds, video, audio, HUD & accessibility).
Specs: ${SPEC}/07_settings_shell_shared_frame_and_component_kit_all.md, ${SPEC}/08_settings_mouse_aim_tab.md, ${SPEC}/09_settings_keybinds_tab.md, ${SPEC}/10_settings_video_tab.md, ${SPEC}/11_settings_audio_tab.md, ${SPEC}/12_settings_hud_accessibility_tab.md, ${SPEC}/13_settings_gameplay_network_tab_built_from_settings.md, plus style.md.
Mockups: ${PNG}/08_settings_mouse.png, 08b_settings_keybinds.png, 08c_settings_video.png, 08d_settings_audio.png, 08e_settings_hud.png; sources ${SRC}/pages/settings.html, ${SRC}/common.css.
YOUR FILES: game/crates/val_etf/src/settings/ (all tabs; a Settings resource persisted as settings.ron via user_config), game/crates/val_etf/src/client.rs (input: replace hard-coded keys with the rebindable Keybinds; mouse sensitivity in cm/360 with DPI; invert; ADS multiplier; the reload tap/hold time instead of the RELOAD_HOLD_S const), game/crates/val_etf/src/radial.rs (only the hold-time constant / its use), game/crates/val_etf/src/render.rs (FOV and anything video the spec needs that can be applied), game/crates/val_etf/src/hud.rs (crosshair / HUD options that apply to the current HUD), game/crates/val_etf/src/main.rs (window mode / vsync / resolution application if needed).
Decisions already made: settings apply live where cheap and persist on APPLY / leaving (follow the spec). Keybinds include the reload tap / hold-radial row, the heal ring key (H) and the static 1-6 magazine pick row. Audio values are stored; Master drives Bevy's GlobalVolume. Options the game cannot honour yet are rendered disabled (opacity .35) with the spec's copy. The screen opens from the main menu and over a running match (Screen::Settings(tab)); Esc pops it; the tab rail switches with Screens::replace_top.
Demo values to add: --demo-ui settings-gameplay, settings-mouse, settings-keybinds, settings-video, settings-audio, settings-hud (each opens Settings on that tab from the main menu).`,
  },
]

const REPORT = {
  type: 'object',
  properties: {
    worktree: { type: 'string', description: 'absolute path of the worktree (pwd)' },
    branch: { type: 'string' },
    commits: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    deviations: { type: 'string' },
    open_items: { type: 'string' },
    screenshots: { type: 'array', items: { type: 'string' } },
    files_outside_ownership: { type: 'array', items: { type: 'string' } },
    tests_green: { type: 'boolean' },
  },
  required: ['worktree', 'branch', 'commits', 'summary', 'deviations', 'open_items', 'screenshots', 'files_outside_ownership', 'tests_green'],
}

const CRITIQUE = {
  type: 'object',
  properties: {
    worktree: { type: 'string' },
    branch: { type: 'string' },
    issues: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          area: { type: 'string' },
          problem: { type: 'string' },
          expected: { type: 'string', description: 'what the mockup/spec says, with numbers' },
        },
        required: ['severity', 'area', 'problem', 'expected'],
      },
    },
  },
  required: ['worktree', 'branch', 'issues'],
}

const results = await pipeline(
  SCREENS,
  s => agent(`${COMMON}\n\n${s.task}\nYOUR PORT (only if you host for screenshots): ${s.port}.`, {
    label: `build:${s.key}`, phase: 'Build', schema: REPORT, isolation: 'worktree',
  }),
  (impl, s) => impl && agent(`You are a strict UI reviewer. A teammate built the ${s.key.toUpperCase()} hub screen of a Bevy game to mirror the UI mockups closely. Their worktree: ${impl.worktree} (branch ${impl.branch}). Their report: ${JSON.stringify(impl)}.
Do NOT edit files. Compare their screenshots (Read each PNG: ${impl.screenshots.join(', ')}) with the mockup PNGs in ${PNG} and with the spec files in ${SPEC} for this screen (and ${SPEC}/style.md). Also read their code in ${impl.worktree}/game/crates/val_etf/src/ to check interactions, states, data bindings, and the decisions in their task (listed below), and that no exact ammo/round counts are shown anywhere.
Their task was:\n${s.task}\n
If a screenshot is missing for a state, you may build and run it yourself from ${impl.worktree}/game with CARGO_TARGET_DIR=/home/user/sharline/game/target and the screenshot command (DISPLAY=:99, VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json, VETF_CONFIG_DIR=<temp dir>, --width 1920 --height 1080 --demo-ui <value> --screenshot <path under ${SCRATCH}/hub_shots/${s.key}/review_*.png> --screenshot-after 4 --exit-after 9), but do not modify any file.
List every concrete discrepancy (geometry, typography, colour, copy, missing element or state, broken interaction, spec decision not followed), most severe first, with the expected values from the mockup/spec. Echo the worktree and branch.`, {
    label: `critique:${s.key}`, phase: 'Critique', schema: CRITIQUE,
  }),
  (crit, s) => crit && agent(`${COMMON}\n\n${s.task}\nYOUR PORT (only if you host for screenshots): ${s.port}.\n\nThis is a FIX PASS. The screen is already built in the worktree ${crit.worktree} (branch ${crit.branch}): cd there and work in it (do not create another worktree). A reviewer compared it with the mockups and the spec and found these issues (most severe first):\n${JSON.stringify(crit.issues, null, 1)}\nFix all high and medium issues and as many low ones as reasonable, re-take the screenshots, keep clippy and tests green, and commit in that branch. Report as before (worktree = ${crit.worktree}).`, {
    label: `fix:${s.key}`, phase: 'Fix', schema: REPORT,
  }),
)
return results
