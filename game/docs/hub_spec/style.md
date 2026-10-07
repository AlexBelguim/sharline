## tokens
Scope note: these are the shared tokens for the HUB screens: main menu with its Host and Join flyouts, Loadout with its popover, Lobby, Settings, ESC menu and its modals. The in-match HUD mockups 01 and 02 are out of scope, per the user ("the hud is bad, the hub is great").

Sources: /home/user/sharline/design/ui/mockups/_src/common.css :root (lines 6-27), plus the colour literals that recur in pages/*.html.

In Rust, build colours with Color::srgb / Color::srgba using the exact float alpha. Do not round alpha to a hex byte.

/home/user/sharline/game/crates/val_etf/src/ui_kit.rs already exists (untracked). It defines most of group A under the names given in [brackets]; add the rest.

== A. CSS VARIABLES (common.css) ==
SURFACES
- --bg0 #07090D [BG0]: screen base; text on light fills (primary button, selected segment).
- --bg1 #0C1016 [BG1]: agent-card fill and the stop of its fade.
- --bg2 #121821 [BG2]: fallback map-card fill.
- --panel rgba(9,12,17,.70) = #090C11B3 [PANEL].
- --panel-hi rgba(16,21,29,.82) = #10151DD1 [PANEL_HI].
- --panel-solid #10151C [PANEL_SOLID]: open dropdown list.
- --stroke rgba(255,255,255,.09) = #FFFFFF17 [STROKE].
- --stroke-mid rgba(255,255,255,.16) = #FFFFFF29 [STROKE_MID].
- --stroke-hi rgba(255,255,255,.32) = #FFFFFF52 [STROKE_HI].

TEXT
- --text-hi #F3F0E9 [TEXT_HI]
- --text #D7D4CD [TEXT]
- --text-mid #9CA2AB [TEXT_MID]
- --text-low #646B75 [TEXT_LOW]

ART-BIBLE PALETTE
- --graphite #303338 (unused in UI)
- --gunmetal #5D5F61 (unused)
- --bone #C4BFB5 [BONE]
- --sand #A29076
- --olive #616550 (unused)
- --ivory #DAD6CB
- --teal #00DACE [TEAL]
- --coral #FF8C7A [CORAL]
- --ice #B3EDFF [ICE]

HALO TIERS
- --t1 #EDF1F6
- --t2 #59B3FF
- --t3 #C46CFF
- --t4 #FFCE50
- --unlit #27272C
These map to [TIERS[0..=4]] with index 0 = unlit, and to [UNLIT].

TEAMS (always relative to the viewer)
- --ally #52E5A5 [ALLY]
- --enemy #FF4D5A [ENEMY]

HEALTH
- --hp-ok #E6E2D8
- --hp-dmg #FFA23A
- --hp-crit #FF3B4E
- --hp-dead #15171B
- --bleed #E0162E
- --heal #9CF7C8

MISC
- --warn #FFA23A [WARN]
- --good #52E5A5 (same as ally)
- --bad #FF4D5A (same as enemy)

FONTS
- --fd: 'Barlow Condensed', fallback 'Arial Narrow'.
- --fb: 'Barlow', fallback 'Segoe UI'.

MOCKUP-ONLY, NEVER SHIP
- .anno #FFE27A
- .mock-label rgba(255,255,255,.28)

== B. SEMANTIC ALIASES (new consts, defined in terms of A) ==
- ACCENT_FOCUS = TEAL. Used for the main-menu active bar, the flyout and popover top borders, the input caret, the keyboard focus ring, an open slot or mag card, the selected agent, and a listening key cap.
- SELECT_FILL = TEXT_HI, with SELECT_INK = BG0. Used for the selected segment or toggle, the active preset chip, the active weight-class box and the primary button.
- AMMO colours, by ammo TYPE (from the Loadout spec; use them everywhere ammo is named):
  - AMMO_STD = BONE #C4BFB5
  - AMMO_AP = ICE #B3EDFF
  - AMMO_RIP = CORAL #FF8C7A
  - AMMO_SLUG = SAND #A29076
- Agent accents: AGENT_KESTREL = TEAL, AGENT_SOLACE = CORAL. These are never team colours.
- FLESH_TEXT #FF6170: flesh damage, critical HP numbers, the Downed title.
- DESTROYED_GREY #8A8F98.

== C. ALPHA LADDERS (page literals as named consts) ==
WHITE, rgba(255,255,255,a):
- W03 .03 (#FFFFFF08): fill of slot, core and mag cards and of weapon tabs.
- W035 .035 (#FFFFFF09): lobby player row.
- W04 .04 (#FFFFFF0A): join-code box, import box, equipped popover row, mag chip.
- W05 .05 (#FFFFFF0D): list-row hover, weight-class box, popover icon box.
- W06 .06 (#FFFFFF0F): .btn fill, card hover, dropdown-row hover, segment hover (proposed).
- W07 .07 (#FFFFFF12): active weapon tab; start of the settings-rail gradient.
- W08 .08 (#FFFFFF14): context-menu hover, popover row hover, selected list row.
- W10 .10 (#FFFFFF1A): bar tracks.
- W12 .12 (#FFFFFF1F): .btn hover, empty ammo pip.
- W13 .13 (#FFFFFF21): unlit-arc hairline and unlit-pip outline.
- W14 .14 (#FFFFFF24): slider track, switch off.
- W15 .15 (#FFFFFF26): progress-ring track.
- W18 .18 (#FFFFFF2E): unlit sectors of the reload-wheel glyph.
- W20 .20 (#FFFFFF33): unlit weight square.
- W70 .70 (#FFFFFFB3): border of your own lobby row.

BLACK:
- K35 .35: settings field fill.
- K40 .40: hotspot dot fill.
- K45 .45: main-menu input fill.
- K50 .50: agent-card ability box.
- K60 .60: modal backdrop; popover and context-menu shadows.
- K85 .85: crosshair outline.

INK and SCRIMS:
- rgb(5,7,10) = #05070A:
  - main-menu horizontal shade at .96 / .88 / .35 / 0 (stops 0 / 30 / 56 / 72 %);
  - main-menu bottom shade .85 → 0 at 26 %;
  - ESC dim .94 / .86 / .55 (stops 0 / 36 / 100 %);
  - bottom bars .60 (#05070A99).
- rgb(4,6,9) #040609: .62 scoreboard dim; .60 row separator.
- BG0 at .85: hotspot tag and crosshair-overlay segment background.
- #090B0E: preview fill; its floor fade runs .9 → 0.
- rgb(6,8,11) #06080B: map-card overlay .9 → 0.
- BG1 → 0: agent-card fade.

TINTED:
- TEAL .08: open slot or mag background.
- TEAL .18: selected-agent glow.
- TEAL .25: hotspot ring.
- Any tier colour: .08 for a selected tile background, .60 for a covered zone border. The mockup's T2 values are rgba(89,179,255,.08) and .60.
- ALLY .10: own lobby row.
- ALLY .12: ally scoreboard row.
- ALLY .26: own scoreboard row.
- ALLY .50: Downed help pill border.
- ENEMY .45: danger button border.
- ENEMY .70: danger hint text.
- ENEMY .11: enemy scoreboard row.

== D. OPAQUE SPECIALS ==
- MENU_SURFACE #141A22: lobby context menu, VIEW LOADOUT popover, ESC players menu.
- MODAL_SURFACE #11161D: confirm modals.
- READY_INK #06140D: ready check, switch knob when on, background of the READY 'F' key cap.
- ALLY_BTN_INK #04140C.
- DANGER_INK #1B0507.
- ICON_CUT #0B0E13: icon detail, agent-badge initial, halo drain overlay (used at .62).
- PREVIEW_BG #090B0E.
- Halo and body widget colours:
  - BAND #3A3F47
  - VOLT_TICK_UNLIT #33363D
  - ZONE_LETTER_UNLIT #5A6069
  - BODY_BASE #2A2D33
  - BODY_STROKE #0B0E13
- PROPOSED (not in any mockup):
  - PRIMARY_PRESSED #DAD6CB (= --ivory).
  - DANGER_SOLID_HOVER #FF6170.
  - Colour-blind team pairs: DEUTAN and PROTAN ally #3FA9F5 / enemy #FFB000 (these come from settings.html); TRITAN ally #00C2C7 / enemy #FF3D7F (proposal).
  - Crosshair swatches: #F3F0E9, #B3EDFF, #F6FF52, #52E5A5, #FF4DF0.

== E. SCREEN BACKGROUNDS ==
- Loadout: radial gradient centred at 50% 35%: #18202B 0%, #0A0D12 55%, #06080B 100%.
- Lobby: radial at 40% 20%: #151C26 0%, #090C11 60%, #06080B 100%.
- Settings: radial at 60% 30%: #141B25 0%, #090C11 60%, #06080B 100%.
- Main menu: BG0, then the menu_kestrel art set to cover, then the two shades listed in C.
- ESC menu: the live view, then a linear gradient to the right.
- Scoreboard: flat #0406099E.
- Modal backdrop: #00000099.

Bevy 0.19 gotchas (checked in bevy_ui-0.19.1/src/gradients.rs):
- The default radial shape is ClosestCorner and the default interpolation is Oklaba. CSS uses farthest-corner and sRGB.
- Build every gradient as RadialGradient::new(UiPosition::TOP_LEFT.at_percent(x, y), RadialGradientShape::FarthestCorner, stops).in_color_space(InterpolationColorSpace::Srgba).
- For linear gradients use LinearGradient::to_right(..) or to_top(..), plus .in_color_space(Srgba).

== F. ALPHA → HEX BYTE ==
.03 08 · .035 09 · .04 0A · .05 0D · .06 0F · .07 12 · .08 14 · .09 17 · .10 1A · .12 1F · .13 21 · .14 24 · .15 26 · .16 29 · .18 2E · .20 33 · .25 40 · .32 52 · .35 59 · .45 73 · .50 80 · .55 8C · .60 99 · .62 9E · .70 B3 · .82 D1 · .85 D9 · .86 DB · .88 E0 · .90 E6 · .94 F0 · .96 F5.

## typography
FAMILIES
Ship static TTFs and load one Handle<Font> per weight. In Bevy 0.19, TextFont.weight only affects variable fonts.
- Display 'Barlow Condensed' (BC):
  - 700 Bold: titles, nav items, buttons, values, key caps.
  - 600 SemiBold: labels, micro text, hints, table text.
  - 500 Medium: only where the CSS asks for weight 400 on the display face (.num values, slider ticks, loadout core descriptions via the global .d class). Browsers fall back to 500 there because 400 is not loaded.
- Body 'Barlow' (B):
  - 400 Regular: help text, descriptions, chat, table text.
  - 700 Bold: inline <b> in notes; the killer panel's HALO value.
  - 400 Italic: lobby system chat lines. This file is missing; see fonts_plan.
  - Barlow 500 and 600 are bundled but no hub page uses them.

RULES
- LETTER-SPACING: px = em × font size, applied as LetterSpacing::Px(..).
  - Do NOT use LetterSpacing::Rem. In bevy_text 0.19.1 (text.rs:1049) Rem multiplies the global RemSize, not the font size.
  - Several reader specs say Rem; that is wrong. ui_kit.rs already uses Px(size × em), which is correct.
  - CSS adds the spacing after every glyph, including the last; parley does the same, so right-aligned and centred text matches the mockups.
- LINE HEIGHT: CSS 'normal' is 1.2 for both families (hhea metrics checked). That equals Bevy's default LineHeight::RelativeToFont(1.2). Explicit line heights are listed per role below.
- CASE: Bevy has no text-transform, so uppercase roles marked UP in code.
  Mixed-case exceptions (do NOT uppercase):
  - the Loadout in-match warning;
  - the Settings top-bar hint;
  - segment options that contain units or lowercase: '5 min', '4 s', 'NIGHT (compressed)', 'OFF (AutoNoVsync)', 'ON (AutoVsync)';
  - units: 'rpm', 's', 'm', 'cells', 'cm / 360°', 'px at 1080p', 'counts per inch';
  - the lobby join-code address lines;
  - the scoreboard '(placeholder)';
  - the ESC info-card values;
  - all Barlow body copy.
- NUMBERS that change use TextFont.font_features = [FontFeatureTag::TABULAR_FIGURES]. 'tnum' is present in both families (GSUB checked).
- SIZE ROUNDING: Bevy rounds font size × UiScale to whole pixels, so 12.5 and 14.5 px render as 12-13 and 14-15 px at 1080p. This is acceptable.
- GLYPHS: '· × − – — • ° ≤ ≥ … ÷ ‹ › ◊' are present. '↑ ↓ ← → ✕ ◯ ▢ △ ■ ▼ ⇅' are missing (see fonts_plan and icons).

TYPE SCALE
Format: ROLE: face weight, size px / letter-spacing em = px / line height / case / default colour. Then where it is used.

DISPLAY
- WORDMARK: BC700 84 / .14 = 11.76 / LH 80 / UP / text-hi, with the '/' in teal. Main menu.
- DEATH_NAME: BC700 72 / .08 = 5.76 / LH 72. Death recap.
- DOWNED: BC700 64 / .16 = 10.24 / LH 64 / #FF6170. In-match.
- AGENT_XL: BC700 56 / .16 = 8.96 / LH 56. Main-menu agent tag.
- SCORE_XL: BC700 56 / 0 / LH 56 / tnum / ally or enemy. ESC info card.
- NAV_XL: BC700 44 / .10 = 4.4 / UP / text-mid, text-hi when on. Main nav.
- SCREEN_TITLE: BC700 40 / .14 = 5.6 / UP / text-hi. LOADOUT, LOBBY, SETTINGS.
- NAV_L: BC700 36 / .10 = 3.6 / UP. ESC menu rows.
- AGENT_L: BC700 34 / .12 = 4.08 / LH 34. Loadout agent cards.
- SB_TITLE: BC700 34 / .08 = 2.72. Scoreboard.
- NAV_QUIT and MODAL_TITLE: BC700 32 / .10 = 3.2.
- FLYOUT_TITLE: BC700 30 / .12 = 3.6. HOST GAME, JOIN GAME.
- CODE_XL: BC700 30 / .24 = 7.2 / tnum. Join-code input. The lobby code box uses .20 = 6.0.
- TEAM_NAME, MAP_NAME, RESPAWN_TITLE: BC700 28 / .14 = 3.92. MAP_NAME has LH 28.
- VALUE_L: BC700 26 / LH 28. Loadout RESULT figures. Scoreboard footer values are 28.
- NAV_M: BC700 24 / .10 = 2.4. ESC host and danger rows.
- NAV_SUB: BC700 24 / .14 = 3.36. HOST GAME / JOIN GAME sub-items.
- PLAYER_NAME: BC700 24 / .08 = 1.92. Player card.
- CODE_M: BC700 24 / .20 = 4.8. ESC join code.
- INPUT_BIG: BC700 24 / 0.
- TAB_WEAPON: BC700 22 / .08 = 1.76. With 3 weapon tabs: 20 / 1.6.
- LOBBY_NAME: BC700 22 / .08 = 1.76 / text.

HEADINGS (BC700, UP, text-hi)
- H2: 20 / .18 = 3.6. AGENT, HALO ARMOR, MATCH SETTINGS, CHAT, CONNECTION, ESC info title.
- H2_CARD: 18 / .18 = 3.24. Settings card titles, death recap panels.
- H2_SMALL: 17 / .18 = 3.06. RESULT, WHAT OTHERS SEE, popover header.

CONTROLS (BC700)
- BTN_L: 20 / .12 = 2.4 / UP. CREATE LOBBY, JOIN LOBBY, START MATCH.
- BTN: 18 / .12 = 2.16 / UP. The standard .btn.
- APPLY: 15 / 1.8.
- BTN_S: 14 / .12 = 1.68. PASTE, COPY.
- BTN_XS: 13 / 1.56. CHANGE MAP.
- RAIL_TAB: 20 / .14 = 2.8. Settings tab rail.
- INPUT_M: 20 / .06 = 1.2. input.sm.
- STEPPER: 20 / 0.
- ROW_NAME: 20 / .06 = 1.2 / UP. Lobby player rows.
- FIELD: 18 / 0. Settings .inp.
- TIER_BOX: 18 / .10 = 1.8.
- LIST_NAME: 17 / .06 = 1.02. Recent rows, popover rows.
- SLOT_VALUE: 17 / .04 = .68. Slot and mag cards.
- TAB: 16 / .16 = 2.56. Join-flyout tabs.
- CHIP: 16 / .14 = 2.24. Preset chips, zone tiles.
- SELECT: 16 / .06 = .96. .sel and .dd.
- ABILITY_TITLE: 16 / .10 = 1.6.
- SEG: 15 / .08 = 1.2. Settings and lobby segmented controls.
- TOGGLE: 15 / .12 = 1.8. Main-menu toggle.
- CORE_NAME: 15 / .14 = 2.1.
- WCLASS: 15 / .16 = 2.4.
- MENU_ITEM: 15 / .12 = 1.8. Context menu.
- KEYBIND_CAP: 15 / .04 = .6.
- KEYCAP: 13 / .04 = .52. Uses 12 px in 18-tall inline caps and 11 px in 16-tall inline caps.
- TIER_TEXT: 13 / .08 = 1.04.
- HOTSPOT_VALUE: 13 / .12 = 1.56.
- STATUS_WORD: 13 / .10 = 1.3. RUNNING, GOOD, PORT CLOSED.
- GROUP_ROW: 13 / .18 = 2.34. Keybind groups.
- TAG: 11 / .20 = 2.2. SELECTED.
- TAG_XS: 10 / .16 = 1.6. IN GUN (new).

LABELS (BC600)
- ROLE_LINE: 15 / .22 = 3.3 / teal. Agent tag.
- STATUS_LINE: 15 / .14 = 2.1. Lobby status.
- NUM_CELL: 15 / 0 / tnum. Ping and player counts.
- EMPTY_SLOT: 15 / .16 = 2.4 / text-low.
- HINT: 14 / .14 = 1.96 / text-mid. Key-hint labels. The Settings hint and the Loadout warning (in warn) use the same style in mixed case.
- ROW_LABEL: 14 / .12 = 1.68 / UP / text. Settings rows.
- UNIT: 14 / .08 = 1.12 / text-mid.
- LBL: 13 / .14 = 1.82 / UP / text-mid. Field labels, key/value keys, option keys, section labels.
- NAV_SMALL: 13 / .18 = 2.34 / UP / text-low. In the ESC menu the spacing is .16 = 2.08.
- SUBTITLE: 13 / .20 = 2.6 / UP. Team subtitle, agent-card role line.
- STAT_KEY: 12.5 / .14 = 1.75 / UP. Stat keys, preview hints.
- TABLE_HEAD and SLOT_HEAD: 12 / .16 = 1.92 / UP / text-mid.
- TAB_SUB: 12 / .18 = 2.16 / text-low.
- MICRO: 11 / .16 = 1.76 / UP / text-low.

BC500
- NUM: 14.5-15 / tnum. ESC and killer values.
- TICK: 11 / text-low. Slider ticks.
- CORE_DESC: 11 / .06 = .66 / UP / text-low / LH 1.25.

BODY (Barlow 400)
- BODY_L: 17. Death sub-line.
- MODAL_BODY: 16 / LH 24 / text.
- KV_VALUE: 15 / text.
- CHAT: 14.5 / LH 23.2 / text.
  - The speaker is BC700 .06 em, UP, in the team colour.
  - A system line is Barlow italic, text-mid.
- TABLE_CELL: 14.5.
- BODY: 14. Connection values, chat input.
- HELP: 13 / LH 18.85 / text-mid.
- CARD_LINE: 13 / text-mid.
- NOTE: 12.5 / LH 1.45 / text-mid. Inline <b> is Barlow 700, text-hi.
- DESC: 12.5 / LH 1.35 / text-mid.
- SUB: 12 / text-mid. Settings sub-labels, list sublines, result sub-lines, code-box address lines (LH 1.35).

API SUGGESTION
Add `enum TextRole` to ui_kit, with `fonts.role(TextRole::Lbl, "COPY")`. It returns Text, TextFont (handle, size, tnum flag), LetterSpacing::Px, LineHeight and TextColor, so screens never hand-type sizes.

## components
Bevy 0.19 primitives (checked in the bevy_ui-0.19.1 and bevy_text-0.19.1 sources):
- Styling: Node.border_radius; BorderColor per side; Outline; BoxShadow(Vec<ShadowStyle>); UiTransform (translation, scale, rotation; no skew); BackgroundGradient and BorderGradient (Linear, Radial, Conic); NodeImageMode::Sliced(TextureSlicer) and Tiled; ImageNode.color for tint; GlobalZIndex; ViewportNode.
- Interaction markers: InteractionDisabled, Pressed, Checked, Selected.
- bevy_ui_widgets is on by default: Button (Activate), Checkbox, RadioGroup, Slider (SliderValue, SliderRange, SliderStep, TrackClick), ScrollArea and Scrollbar, ListBox, MenuButton, Popover.
- Text input: EditableText (max_characters; cursor_width relative to font size; cursor_blink_period) with EditableTextFilter and TextCursorStyle.
- There is NO group opacity.

GLOBAL CONVENTIONS
- Radius:
  - 2 for panels, key caps, chips and popovers;
  - 0 for buttons, inputs, tiles, segments, tabs and list rows;
  - 12 for the switch;
  - 50% for dots.
- State changes are instant. The mockups have no hover transitions.
- DISABLED:
  - Visual: multiply the alpha of every BackgroundColor, BorderColor, TextColor and ImageNode.color in the subtree by .35.
  - Behaviour: add InteractionDisabled, skip the element in arrow-key navigation, and show no hover.
  - Build it once as a kit system that stores the base colours.
- KEYBOARD FOCUS RING: Outline { width 2 px, offset 2 px, color TEAL }, drawn only for keyboard focus.
  - Nav rows, list rows and segments show focus with their own 'on' style instead.
  - The modal spec proposed a TEXT_HI ring; use teal everywhere.
- HOVER on mouse-driven elements uses Interaction::Hovered. Pressed reuses the hover colours unless stated.

1. PANEL
Base: 1 px STROKE border, radius 2, no blur. Variants:
- panel: PANEL background. Settings cards use padding 18/20; scoreboard cards 12/14.
- panel.hi: PANEL_HI background. The ESC info card uses padding 22/24.
- flyout (main menu): PANEL_HI, top border 2 px TEAL (border widths top 2, other sides 1), width 620, padding 26/28/24/28.
- popover (Loadout attachment list): PANEL_HI, top 2 px TEAL, BoxShadow 0/20 offset, blur 60, K60. Padding 12, width 420, GlobalZIndex above the page.
- result (Loadout): PANEL with a 2 px TEXT_HI top border, padding 16/18.
- killer (death recap): PANEL_HI with a 3 px ENEMY left border.
- context menu: MENU_SURFACE #141A22, 1 px STROKE, radius 2, BoxShadow 0/12, blur 40, K60. Padding 6, width 220.
- modal: MODAL_SURFACE #11161D, 1 px STROKE plus a 3 px top border in ENEMY (or WARN for restart). Width 620, padding 28/30, centred over a K60 backdrop.
API: `panel(kind).top_accent(px, color).left_accent(..)`.

2. SCREEN CHROME
- TOP BAR: left 0, right 0, top 0. Height 84 (Loadout, Settings) or 96 (Lobby). Padding 0 48, align centre. Gap 28 (Loadout) or 24 (others). 1 px STROKE bottom border. Transparent. Title uses SCREEN_TITLE.
- BOTTOM BAR: left 0, right 0, bottom 0. Height 80 (Settings) or 88 (Lobby). Padding 0 48, gap 12, 1 px STROKE top border, background #05070A99.
- HINT ROW (footer):
  - Main menu: centred, bottom 28.
  - Loadout: left 48, bottom 24.
  - ESC menu: left 96, bottom 40.
  - Scoreboard: centred, bottom 28, gap 18.

3. BUTTON (.btn)
- Base: height 44, padding 0 22, gap 10, align centre, BTN text.
- Colours: background W06, 1 px STROKE_MID border.
- States:
  - Hover and pressed: background W12, border STROKE_HI.
  - Disabled: .35.
- Variants:
  - primary: background and border TEXT_HI, text BG0. Hover #FFFFFF. Pressed #DAD6CB (proposed).
  - danger: text ENEMY, border ENEMY .45. Hover: background W12, border ENEMY .70 (proposed).
  - danger-solid: background and border ENEMY, text #1B0507. Hover #FF6170 (proposed).
  - ally: background and border ALLY, text #04140C, used for READY. It holds an 18 px i-check plus an 'F' cap: height 20, background #06140D, text ALLY.
- Sizes:
  - L: height 52, padding 0 34 (START MATCH uses 0 30), BTN_L text.
  - M: height 44, the default.
  - S: height 36-38, padding 0 12, gap 10, BTN_S text, 16 px icon. COPY, PASTE.
  - XS: height 34, padding 0 12, 13 px text. CHANGE MAP.
  - APPLY: height 36, padding 0 16, 15 px text, primary.
- Optional leading icon (16-18 px, tinted with the text colour) and trailing key cap (ghost, 20 tall), for example 'BACK [ESC]' and 'CANCEL [ESC]'.

4. KEY CAP
- Solid: min-width 22, height 22, padding 0 6, radius 2. Background TEXT_HI, KEYCAP text in BG0, content centred.
- Ghost: transparent background, 1 px STROKE_HI border, text TEXT_HI.
- Heights:
  - 22 default;
  - 20 inside buttons;
  - 18 inline in body text, 12 px text (lobby chat input, health subtitle);
  - 16 inline in list descriptions, 11 px text (the UGL row's [G]).
- Measured widths at 13 px:
  - 1-letter keys 22;
  - TAB 31.3;
  - ESC 33.1-33.6;
  - WASD 41.9;
  - ENTER 45.6-47.6;
  - the arrow cap 28 (holds a 12x12 up/down arrow icon).
- Caps are hints only, never clickable.
- KEYBIND CAP (Settings > Keybinds; a separate component):
  - Min-width 44, height 28, padding 0 10, 1 px STROKE_HI border, no fill, radius 0, KEYBIND_CAP text TEXT_HI.
  - Two caps in one cell sit 4 px apart.
  - States:
    - unbound: '—' in TEXT_LOW, DASHED 1 px border (9-slice);
    - listening: 'PRESS A KEY…', border and text TEAL, opacity pulse 1 → .35 → 1 over 1 s;
    - conflict: border and text WARN.

5. HINT
- One hint = cap(s) + 7 px gap + HINT label. Caps within a group are 7 px apart.
- Hints sit 22 px apart.
- Preview-hint variant: gap 6, STAT_KEY label, groups 16 px apart.

6. NAV ROW (main menu and ESC menu)
- Layout: flex row, space-between, align centre, padding-left 22 (label text starts 22 px in).
- Right-hand micro label: NAV_SMALL, TEXT_LOW, right-aligned.
- Sizes:
  - XL: height 66, NAV_XL. Main menu PLAY, GUN RANGE, LOADOUT, SETTINGS.
  - QUIT: height 56, 32 px, colour TEXT_LOW.
  - L: height 60, NAV_L. ESC RESUME, LOADOUT, SETTINGS, CONTROLS.
  - M: height 46, NAV_M. ESC host and danger rows.
- States:
  - idle: TEXT_MID;
  - hover: TEXT_HI;
  - on (focused or selected): TEXT_HI plus an ACTIVE BAR, an absolute node at left 0, top 14, bottom 14, width 4.
- Bar colour by context:
  - TEAL on the main menu;
  - TEXT_HI in the ESC menu;
  - ENEMY on the danger row.
- Danger row: text ENEMY, right label ENEMY .70.
- Not built yet: .35 and right label 'LATER'.
- SUB-NAV ITEM (main menu):
  - Height 44, items start 44 px in, gap 12, NAV_SUB text.
  - Diamond: a 10x10 node with UiTransform rotation 45°.
  - On: diamond filled TEXT_HI, text TEXT_HI. Off: hollow diamond (1 px TEXT_LOW border), text TEXT_MID.
- A group separator in the ESC menu: margin-top 22, then a 1 px STROKE top border, then padding-top 14, then a MICRO group label.

7. TABS
- UNDERLINE TABS (join flyout):
  - The row has a 1 px STROKE_MID bottom rule across its full width. No gap between tabs.
  - Tab: padding 10 18, TAB text, height about 39.
  - States: idle TEXT_MID; hover TEXT_HI; selected TEXT_HI plus a 2 px TEXT_HI bar at the tab's inner bottom (an absolute child: bottom 0, height 2).
- RAIL TAB (Settings): 260x52, padding-left 18, RAIL_TAB text.
  - idle: TEXT_MID, 3 px transparent left border;
  - hover: TEXT_HI;
  - selected: TEXT_HI, 3 px TEXT_HI left border, background LinearGradient to the right, W07 → transparent.
- WEAPON TAB (Loadout):
  - Two tabs: 433x62 each, gap 6. Three tabs: 286.7 wide each.
  - Padding 0 16, gap 14, 1 px STROKE_MID border, background W03.
  - Silhouette ImageNode tinted BONE: 130x35 for i-mako, 150x35 for i-warden, contained in 96x26 when there are 3 tabs. The inactive tab's silhouette is at .6 alpha.
  - Name uses TAB_WEAPON in TEXT_MID; subtitle uses TAB_SUB.
  - States: active has a TEXT_HI border, W07 background and a TEXT_HI name; hover has a STROKE_HI border and W06 background.
- PRESET CHIP (Loadout):
  - Height 38, padding 0 14, gap 6 between chips, 1 px STROKE_MID border, no fill, CHIP text in TEXT_MID.
  - States: active has background and border TEXT_HI with BG0 text; hover has a W12 background and STROKE_HI border.
  - '+ SAVE AS' has a DASHED border (9-slice) and turns into an EditableText (max 8 characters, uppercase).

8. SEGMENTED (one component with three looks)
- TOGGLE (main-menu WHO CAN JOIN):
  - Container: 1 px STROKE_HI border, fixed width 392, height 36. Segments are packed to the left with no dividers.
  - Segment: padding 8 14, TOGGLE text.
  - Selected: TEXT_HI background, BG0 text. Idle: TEXT_MID. Hover (proposed): TEXT_HI.
- SEG HUG (Settings):
  - Each option: height 34, padding 0 14, 1 px STROKE_MID border, margin-left −1 so neighbouring borders overlap, SEG text.
  - Selected: background and border TEXT_HI, text BG0, ZIndex(1) so its border draws on top.
  - Hover (proposed): TEXT_HI text, STROKE_HI border.
- SEG FILL (Lobby): the same, but cells are flex 1, height 32 and evenly filled.
  - Read-only for non-hosts: no hover.
- OVERLAY SEG (crosshair preview): SEG HUG on a BG0 .85 background, at right 10, top 10.
- WEIGHT-CLASS BAR (read-only, Loadout RESULT):
  - Three flex-1 boxes, height 36, gap 4, background W05, WCLASS text in TEXT_LOW.
  - The active box: TEXT_HI background, BG0 text.
- Behaviour: use bevy_ui_widgets RadioGroup and RadioButton. Set the copy exactly; do not force uppercase.

9. SELECT and DROPDOWN
- SELECT (lobby .sel): height 32, padding 0 10, 1 px STROKE_MID border, space-between.
  - Value uses SELECT text in TEXT_HI.
  - The '‹ ›' arrows are TEXT_MID with a 14 px gap. The glyphs exist in Barlow.
  - Clicking the left or right half cycles the option.
- DROPDOWN (settings .dd): height 36, min-width 150 (or a fixed 240 / 300), padding 0 10, gap 16, 1 px STROKE_HI border, transparent background, SELECT text.
  - Chevron: i-chev at 12x12, TEXT_HI.
  - Open list (proposed): PANEL_SOLID with a 1 px STROKE_HI border; rows 36 tall; hover row W06; the selected row has TEXT_HI text and an i-check.
  - Behaviour: bevy_ui_widgets MenuButton or Popover.

10. TEXT INPUT
- INPUT (main-menu code field): height 56, padding 0 16, background K45, 1 px STROKE_HI border, CODE_XL text. Field and button sit in a flex row; PASTE is pushed right with margin-left auto.
- INPUT.SM: height 44, INPUT_M text.
- FIELD (settings .inp): height 36, min-width 90, padding 0 10, background K35, 1 px STROKE_HI border, FIELD text, tnum for numbers.
  - FIELD BIG: height 44, 24 px text, min-width 140.
- CHAT INPUT: height 38, padding 0 10, 1 px STROKE_MID border, BODY text in TEXT_LOW while idle. When focused the border is STROKE_HI and the text TEXT_HI.
- CARET (focused field only): 2 px wide, 30 px tall, TEAL, 4 px after the text.
  - Mockup blink is CSS steps(1) over 1 s: opacity 1, then .35. Bevy's EditableText blinks on and off; set TextCursorStyle.color = TEAL and cursor_width = 2 / font_size.
  - Selection colour: TEAL at .35 (proposed).
- Placeholder: same font, TEXT_LOW.
- ERROR state: border BAD; the help slot below becomes Barlow 13 in BAD.
- INVALID numeric field (Settings): border WARN, and the value reverts when the field loses focus.
- Password fields mask with '•'.

11. STEPPER: 152x40, 1 px STROKE_HI border. Cells are 40 / 70 / 40, BC700 20 px.
- '−' (U+2212) and '+': TEXT_MID; hover TEXT_HI; at the limit .35.
- Value: TEXT_HI, tnum.

12. SLIDER
- Track: height 4, background W14, flex 1.
- Fill: TEXT_HI from the left.
- Thumb: a 16x16 TEXT_HI square, rotated 45°, centred on the value (its rotated extent is about 22.6 px).
- Ticks: TICK text, top 10 px below the track top, centred on their % position, no wrap.
- Combos:
  - slider 400 + gap 12 + FIELD 70x36;
  - meter: slider 340 + gap 10 + FIELD 64x36;
  - a full-width slider under a big field: margin-top 14.
- Behaviour: bevy_ui_widgets Slider with TrackClick, and a mouse-wheel step.

13. SWITCH, CHECKBOX, READY BOX
- SWITCH: 46x24, radius 12.
  - Off: background W14, an 18x18 circular knob at (3,3) in TEXT_MID.
  - On: background ALLY, knob at (25,3) in #06140D.
  - Hover (proposed): the off knob turns TEXT_HI.
  - Behaviour: bevy_ui_widgets Checkbox.
- ZONE CHECKBOX: 18x18 with a 2 px STROKE_HI border. Checked: fill and border in the tier colour.
- READY BOX: 30x30, 1 px STROKE_HI border, an 18 px i-check that is transparent. Ready: background and border ALLY, check #06140D.

14. SELECTABLE TILES
Base: 1 px STROKE_MID border, W03 fill. Hover: STROKE_HI border, W06 fill. Disabled: .35.
- SLOT CARD (Loadout):
  - 140.33x76, padding 9 10.
  - Header: 16 px icon + gap 6 + SLOT_HEAD text.
  - Value: SLOT_VALUE, LH 18, margin-top 6, single line with an ellipsis.
  - Open: TEAL border, TEAL .08 fill, header and icon TEAL.
  - Empty: value 'NONE' in TEXT_LOW.
- MAG CARD (new): the same box.
  - Header: the reload-wheel glyph (16 px) + 'MAG n'. Slot 1 adds the IN GUN tag.
  - Value: the ammo name in the ammo colour + up to 3 ammo pips + a right-aligned 'n PTS' cost in MICRO, TEXT_MID.
  - Effect line: MICRO in TEXT_MID, margin-top 4.
  - Empty: DASHED border, '+ ADD MAG' in TEXT_LOW.
  - Dragging: 90% alpha, BoxShadow 0/8 offset, blur 24, K50; the drop target gets a 2 px TEAL border.
  - Invalid: a 1 s WARN border flash.
- CORE CARD: 131.5x128, flex column, centred, gap 2.
  - Contents: a 62 px halo widget, CORE_NAME in TEXT_MID, CORE_DESC.
  - Selected: border in the highest tier colour, fill at that colour .08, name TEXT_HI.
- TIER BOX: 131.5x46, centred, gap 8, no fill, TIER_BOX text in the tier colour.
  - Diamond: 14x14 filled with the tier colour, rotated 45°, BoxShadow in the tier colour with blur 10.
  - Selected: 2 px border in the tier colour and a fill at that colour .08.
  - Above the arc's cap: .35.
- ZONE TILE: 186x46, padding 0 12, gap 10, CHIP text in TEXT_MID, 18 px zone icon, checkbox pushed right with margin-left auto.
  - Covered: TEXT_HI text, border at tier colour .60, fill at tier colour .08, and a 'T2' in TIER_TEXT left of the checkbox.
  - The arc being edited gets a 2 px TEAL Outline.
- AGENT CARD: 360x150, overflow clip, 1 px STROKE_MID border, BG1 fill.
  - Portrait: 200x200 at right −20, top −10.
  - Fade: LinearGradient to the right, BG1 at 38% → transparent at 75%.
  - Name uses AGENT_L; the role line uses SUBTITLE in the agent accent.
  - Ability strip: three 34x34 boxes, gap 6, K50 fill, STROKE_MID border, 22 px icons.
  - Selected: 2 px TEAL border, BoxShadow blur 24 at TEAL .18, and the SELECTED tag.

15. ROWS
- LIST ROW (main-menu Recent / LAN):
  - Height 46, grid 1fr | 110 | 70 | 60, padding 0 10, 1 px STROKE bottom border. The list has a 1 px STROKE top border.
  - Name: LIST_NAME in TEXT_HI; subline: SUB.
  - Number columns: NUM_CELL in TEXT_MID, right-aligned.
  - Status: BC600 15, ALLY or TEXT_LOW.
  - Hover W05; selected W08 (proposed).
- POPOVER ROW: grid 44 | 1fr | auto, gap 12, padding 10, 1 px transparent border, margin-top 4.
  - Icon box: 44x44, W05 fill, 28 px glyph.
  - Name: LIST_NAME. The equipped row adds a 14 px TEAL i-check.
  - Description: DESC.
  - Deltas: BC600 13, .78 px spacing, UP, LH 17, right-aligned; GOOD, BAD or TEXT_MID.
  - Equipped: STROKE_MID border, W04 fill. Hover or focus: TEXT_HI border, W08 fill.
  - Compact variant for more than 6 rows: padding 6.
- MENU ITEM (context menu): padding 9 12 (36 tall), MENU_ITEM text in TEXT.
  - Hover: W08 fill, TEXT_HI text. The danger item is ENEMY.
  - The header item (padding 6 12 4) is not hoverable.
- SETTINGS ROW: grid 230 | 1fr, min-height 50, align centre, 1 px STROKE bottom border (none on the last row). Label uses ROW_LABEL with an optional SUB below it (margin-top 1). Controls sit in a flex row with gap 12.
- OPTION ROW (lobby): grid 180 | 1fr, height 42, 1 px STROKE bottom border, LBL key.
- KV GRID: label column 150 (ESC) or 110 (killer), row gap 10 or 7. Keys use LBL with padding-top 2; values use KV_VALUE or NUM.
- PLAYER ROW (lobby):
  - 76 tall, margin-top 6, padding 0 12, W035 fill, 1 px STROKE border.
  - Grid 52 | 1fr | 92 | 72 | 50 | 40, gap 10.
  - Own row: W70 border, ALLY .10 fill. Context-menu target: TEXT_HI border. Hover (host): STROKE_HI.
  - EMPTY SLOT: transparent, DASHED STROKE_MID border, EMPTY_SLOT text.
- TABLE ROW (keybinds and scoreboard): use Display::Grid with fixed column widths.
  - Keybinds: 38-tall rows with a 1 px STROKE top border; group rows 34 tall with padding-top 12.
  - Scoreboard: 44-tall rows with a 2 px #04060999 top separator.

16. POPOVER and MODAL behaviour
- Floating nodes use GlobalZIndex and are anchored with absolute coordinates (row or card relative).
- Close on Esc, on an outside click or on right-click.
- Esc closes the innermost popover first.
- Modal: focus starts on the SAFE button (CANCEL). Left/Right or Tab move focus. A backdrop click does nothing. Actions are right-aligned, gap 12, margin-top 22.

17. CHIPS and TAGS
- SELECTED TAG: TAG text, BG0 on TEAL, padding 2 7, at right 10, top 10.
- IN GUN TAG: TAG_XS text, BG0 on TEXT_HI, padding 1 5.
- MAG CHIP (main-menu MAGS line, ESC MAGAZINES row, death recap):
  - Height 22, padding 0 6, 1 px STROKE_MID border, radius 2, W04 fill.
  - Contents: slot number (BC600 11, TEXT_LOW), 4 px gap, short ammo label (BC700 13, .78 px spacing) in the AMMO colour.
  - 'In gun at death' variant: TEXT_HI border, fill rgba(243,240,233,.10).
  - Never show round counts.
- COST CHIP: 'n PTS' in MICRO, TEXT_MID. When over budget: 'n PTS · OVER' in BAD.
- STATUS WORD: STATUS_WORD text in ALLY, WARN or ENEMY.
- HOTSPOT: a 14 px dot (radius 50%, 2 px TEXT_HI border, K40 fill) + a tag.
  - Tag: padding 3 8, BG0 .85 fill, STROKE_MID border. A prefix in BC600 13 TEXT_MID with margin-right 6, then HOTSPOT_VALUE.
  - Selected: dot fill and border TEAL, plus an Outline of 5 px at TEAL .25; the tag border turns TEAL.
- LIVE / STATUS DOT: 8x8 ALLY pulsing over 1.6 s (lobby), or 10x10 ENEMY pulsing over 1.2 s (ESC).

18. HALO and TIER GLYPHS
- PIP: a 6x10 body skewed −14° (it leans like '/'), bounding box 8.5x10, gap 3. Bevy has no skew, so it is a tinted PNG (see icons).
- TIER PIPS (the CSS .tier): N pips in the tier colour, then a non-breaking space and TIER_TEXT ('T2 MENDER') in the same colour.
- ARC CHIP (new, for per-arc halos): always 4 pips in the order H, T, A, L, each in its own arc's tier colour.
  - A tier-0 arc is UNLIT #27272C with a 1 px W13 outline.
  - Width about 36.
  - Use it for EVERY player halo summary (see cross_screen_notes).
- AMMO PIPS: up to 3 pips, 5x10, gap 3. Filled pips use the ammo colour; empty pips use W12. STANDARD has none.
- WEIGHT SQUARES: three 7x7 squares, gap 2. Lit TEXT_HI, unlit W20. 0, 1, 2, 3 lit = None, Light, Medium, Heavy. They sit 5 px after the chip.
- DIAMOND: a square node rotated 45°. 10 px (nav), 14 px (tier box), 16 px (slider thumb).

19. BARS
- BAR: track W10, height 4-8. Fill from the left, TEXT_HI or a state colour.
- STAT BAR (Loadout): height 6.
  - An improvement appends a GOOD segment after the fill.
  - A worsening covers the tail of the fill with a BAD segment.
- BUDGET BAR: height 8, two segments with a 2 px gap: halo points in TEXT_HI, ammo points in TEXT_HI .55. Over budget: fill and value BAD.
- PROGRESS RING (respawn): a circular node with border_radius 50% and a border of width = stroke.
  - BorderGradient Conic with start 0 and hard stops: [fill 0 .. f·TAU, track f·TAU .. TAU], track W15.
  - The number is centred inside.

20. PORTRAITS
- Hex portraits: a pointy-top hexagon. Pre-masked PNGs, drawn at 64 (player card) or 44 (lobby rows).
- AGENT BADGE: a 30x30 white hex PNG tinted TEAL or CORAL, with the initial centred in BC700 14 #0B0E13.

21. TEAM HEADER (lobby)
- Flex row, space-between, align flex-end, padding-bottom 10, 3 px bottom border in the team colour.
- Name: TEAM_NAME in the team colour; subtitle: SUBTITLE in TEXT_MID; count: BC700 18 .1 em, TEXT_MID, tnum.
- Range mode: the bar is BONE.
- Scoreboard rows use a 3 px inset left bar in ALLY or ENEMY, plus the tinted row fills from tokens C.

22. HALO WIDGET (static for the hub; Loadout at 62 and 140 px)
- Geometry follows widgets.js haloSVG: viewBox 120, arc radius 34, ±39°.
- Band widths: Bulwark 8 (hex), Mender 4 plus an inner arc at radius 27, Volt 6 plus ticks, Phase 5 with the torso arc split.
- Each arc is tinted with its OWN tier colour.
- Rings: medium at r45 / 3 px; heavy at r46 / 7 px, dashed.
- Cells: 6x10 pills on r53, orbiting in 10 s (14 s with 3 cells).
- Centre text is Bevy Text: value mode, or tier mode with H/T/A/L letters.
- Build it from tinted PNG layers. The per-arc drain (death recap) is out of hub scope and later needs a UiMaterial.

23. ANIMATIONS
- pulse: opacity 1 → .35 → 1 (ease-in-out).
- caret: 1 s, steps.
- listening cap: 1 s.
- status dots: 1.6 s and 1.2 s.
- halo cells: orbit 10 s or 14 s, linear.
- Nothing else moves. In particular, flyouts swap instantly.

## icons
SOURCE
/home/user/sharline/design/ui/mockups/_src/icons.svg holds 37 <symbol> elements. They use currentColor. Some contain hard-coded #0b0e13 detail.

UI GLYPHS (24x24 viewBox)
- i-copy: two overlapping rects (copy). PASTE (main menu, 16 px) and COPY (lobby, 16 px).
- i-check: a check mark, stroke 3. Lobby ready box and READY button (18 px); equipped popover row (14 px, teal); dropdown selected row.
- i-crown: a 3-point crown. Lobby host marker (16 px, --t4); scoreboard (14 px).
- i-signal: three rising bars. Lobby ping column (22 px; ally / warn / enemy).
- i-swap: two opposed arrows. Lobby SWITCH TEAM (18 px).
- i-zipline: a figure on a cable. HUD only.

DROPDOWN CHEVRON (12x12 viewBox)
- i-chev: a down chevron, stroke 2. Settings dropdowns (12 px).

BODY ZONES (24x24 viewBox)
- i-head: a rounded head plus a faint neck arc (opacity .35).
- i-torso: a torso plate.
- i-arms: two arm shapes.
- i-legs: two leg shapes.
Used 18 px in the Loadout zone tiles; 16 px in health callouts (in-match).

AGENT ABILITIES (32x32 viewBox)
Used 22 px in agent cards and 26 px in the abilities list.
- Kestrel:
  - i-grapple: a dashed line and a hook.
  - i-scan: a hex eye with ticks.
  - i-kes-ult: a radar sweep.
- Solace:
  - i-drone: a drone with antenna.
  - i-pulse: a dashed ring with a cross. Also the health-panel ability card.
  - i-sol-ult: a hexagon with a heartbeat line.

CONSUMABLES and STATUS
- 32x32 viewBox:
  - i-bandage: a rotated bandage with 4 #0b0e13 dots.
  - i-medkit: a case with a #0b0e13 cross.
- 24x24 viewBox:
  - i-energy: a lightning bolt.
  - i-food: a can with a lid at .55 and #0b0e13 lines.
  - i-bleed: a drop.
  - i-heal: a plus. Downed help pill, 20 px.
  - i-jet: jetpack flames. HUD only.

KILL FEED (24x24 viewBox; HUD only, unused on hub screens)
- i-headshot
- i-shieldbreak
- i-wall

WEAPONS (muzzle right)
- i-mako (240x64): AR silhouette with #0b0e13 vents at .55. Loadout weapon tab, 130x35, tinted --bone.
- i-warden (280x64): bolt sniper silhouette. Loadout tab, 150x35.
- i-gl (48x24): underbarrel launcher. Popover UGL row, 34x17.
- i-mag (16x28): magazine with a #0b0e13 window at .7. Ammo-picker rows, tinted with the ammo colour.

ATTACHMENT SLOTS (32x32 viewBox)
Used 16 px in slot-card headers and 28 px in popover rows.
- i-optic: a sight. Also the lobby LOADOUT button icon (18 px).
- i-stock: a stock.
- i-magslot: a mag outline.
- i-under: a rail with a grip.
- i-side: a box with a dashed beam.
- i-gunshield: a shield.

HUB USE BY SCREEN
- Main menu: i-copy.
- Loadout: the 6 ability icons, i-mako, i-warden, the 6 slot glyphs, the 4 zone icons, i-check, i-gl, i-mag.
- Lobby: i-copy, i-signal, i-check, i-crown, i-optic, i-swap.
- Settings: i-chev (and i-check if the dropdown list is built).
- ESC menu: none.
Not needed for the hub: i-jet, i-headshot, i-shieldbreak, i-wall, i-zipline, i-energy, i-food.

TOOLS IN THIS CONTAINER (checked)
Available:
- Playwright 1.56.1 (global, /opt/node22/lib/node_modules/playwright) with Chromium builds in /opt/pw-browsers (chromium-1194 and headless_shell-1194).
  - Tested: rendered i-copy at deviceScaleFactor 2 with omitBackground to a 32x32 RGBA PNG.
  - Run it with: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers node script.cjs, and require('/opt/node22/lib/node_modules/playwright').
- librsvg-2.so.2 + libcairo.so.2 shared libraries, driven through Python ctypes (rsvg_handle_new_from_data + rsvg_handle_render_document).
  - Tested OK on a standalone SVG that sets color="#fff" on its root.
- Pillow 12.3 and numpy 2.5.3: post-processing, generated shapes, JPEG→PNG conversion.
- ImageMagick 6.9.12 (convert).

Not available:
- rsvg-convert, inkscape, resvg, cairosvg, svglib, wand, pycairo.
- ImageMagick SVG reading (its delegate calls the missing rsvg-convert and fails).
- Python gi: Rsvg typelib missing; the 3.13 gi is broken.

RECOMMENDED PIPELINE
Use Playwright Chromium. It is the same engine that rendered the mockup PNGs, so <use>, currentColor, opacity, filters and widgets.js output come out exactly as designed. librsvg via ctypes is the fallback.

1. Put the generator in game/ (for example game/tools/ui_raster.cjs plus game/tools/ui_shapes.py). Top-level tools/ belongs to the local session.
   - It loads icons.svg once and, for each symbol, renders <svg width=W height=H style="color:#fff"><use href="#id"/></svg> with omitBackground.
   - Output: white-on-transparent PNGs in game/assets/ui/icons/<id>.png.
   - Commit the PNGs, so the cargo build never needs Chromium. Say in the PR that they derive from design/ui/mockups/_src/icons.svg.
2. Output size = viewBox × 2 or more, covering 2× the largest draw size:
   - 24-unit icons at 48x48;
   - 32-unit icons at 64x64;
   - i-chev at 24x24;
   - i-mag at 32x56;
   - i-gl at 96x48;
   - i-mako at 480x128;
   - i-warden at 560x128.
   (At 2160p UiScale = 2, so 2× assets are exactly 1:1.)
3. CUT-OUTS for the symbols with #0b0e13 detail (i-bandage, i-medkit, i-food, i-mako, i-mag):
   - Render them as above with the detail left black.
   - In Pillow set alpha = alpha × luminance and RGB = white.
   - The detail becomes transparent: partly transparent for the .55 vents. Tinting with ImageNode.color then keeps it readable on any panel.
4. In Bevy: ImageNode::new(handle).with_color(token), Node width and height = the draw size. Use the default linear sampler.

GENERATED SHAPES (Pillow, white unless noted, in game/assets/ui/shapes/)
- pip.png 18x20: a 6x10 parallelogram skewed −14° (top shifted +1.25 px right, bottom −1.25 px left, at 2×). Drawn at 9x10, tinted per tier.
- pip_ammo.png 16x20: a 5x10 body. Drawn at 8x10.
- dash_9slice.png 24x24:
  - 2 px border (1 px at 1×); dashes 8 on / 6 off at 2× (4 / 3 at 1×).
  - Use NodeImageMode::Sliced(TextureSlicer { border: 2 px, sides_scale_mode: SliceScaleMode::Tile { stretch_value: 1.0 }, .. }).
  - Tint STROKE_MID or STROKE_HI. Used for empty lobby slots, empty mags, + SAVE AS and unbound key caps.
- wheel_ring.png 32x32 (16 px at 2×): 6 ring sectors, each 50° wide with 10° gaps, outer radius 7.5 and inner radius 4.5 at 1×. Tint W18.
- wheel_sector.png 32x32: the slot-1 sector only, centred at 12 o'clock. Overlay it with UiTransform rotation (n−1)·60° clockwise, tinted TEXT_HI (TEAL when open). This matches radial.rs, where sector index 0 is up and the order runs clockwise.
- hex_badge.png 60x60: a pointy-top hexagon, polygon 50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%.
- Pre-masked portraits from img/kestrel_portrait.jpg and solace_portrait.jpg (640x640):
  - kestrel_hex.png and solace_hex.png at 128x128 (hex alpha mask), used at 64 and 44;
  - the 200 px card crops use the unmasked JPG.
- key_updown.png 24x24: up and down arrows for the [↑↓] key cap, drawn at 12x12 inside a 28-wide cap.
- Optional pad glyphs (✕ ◯ ▢ △ and D-pad arrows) at 28x28, or use the DejaVu text span (fonts_plan).

HALO WIDGET LAYERS (for the Loadout core cards and coverage widget)
- Render with Playwright from a copy of widgets.js haloSVG, with every colour set to white and one element per render, at 300x300 (viewBox 120 × 2.5).
- Per core (bulwark, mender, volt, phase):
  - arc_{head,legs,torso,arms} crisp;
  - arc_glow_* (blur σ 2);
  - unlit hairline masks;
  - mender inner arcs;
  - volt ticks;
  - the split phase torso arc.
- Shared layers: band_medium, band_heavy (dashed), cell pill (6x10 rx3).
- Stack them absolutely in one size×size node and tint each with ImageNode.color: tier colour at .85 / .35 glow when lit; #27272C plus white .13 hairline when unlit.
- The centre text and H/T/A/L letters are Bevy Text.
- The per-arc drain (death recap, health) needs an angle cut-off: a UiMaterial later, outside hub scope.

IMAGES
In /home/user/sharline/design/ui/mockups/img:
- menu_kestrel.jpg (1920x1080): main-menu backdrop, cover.
- kestrel_portrait.jpg and solace_portrait.jpg (640x640).
- hud_street.jpg (1920x1080): lobby map card at about Rect(0,371,1920,880); crosshair preview at y 223-897.
- mako_dark.jpg (1280x720): Loadout preview placeholder only, until the ViewportNode exists.
- warden_dark.jpg: listed in build.py but missing.

Copy them to game/assets/ui/img/. Bevy's 'jpeg' feature is NOT in the default set (checked), so either:
- add features = ["default", "jpeg"] to bevy in game/crates/val_etf/Cargo.toml (recommended; keeps the files at 38-220 KB), or
- convert them to PNG with Pillow (about 2-3 MB each for the photos).

## fonts_plan
STATUS
The fonts are already present but NOT committed. /home/user/sharline/game/assets/fonts/ is untracked ('??' in git status) and holds:
- BarlowCondensed-Medium.ttf (103,360 B)
- BarlowCondensed-SemiBold.ttf (109,428 B)
- BarlowCondensed-Bold.ttf (109,912 B)
- Barlow-Regular.ttf (104,068 B)
- Barlow-Medium.ttf (103,536 B)
- Barlow-SemiBold.ttf (108,348 B)
- Barlow-Bold.ttf (108,220 B)
- OFL.txt (4,377 B)

The byte sizes are identical to the Google Fonts repo files. The untracked game/crates/val_etf/src/ui_kit.rs embeds them with include_bytes! (UiFonts: body 400-700, display 500-700), so menus never wait on asset loading. Commit both.
.gitattributes puts only .glb, .blend, .fbx, .bin, .exr, .hdr, .ogg and .wav in LFS, so the TTFs and PNGs go in as normal binary blobs.

NEEDED BY THE HUB SCREENS
- BarlowCondensed-Bold (700): titles, nav, buttons, values, key caps.
- BarlowCondensed-SemiBold (600): labels, micro text, hints, tables.
- BarlowCondensed-Medium (500): .num values, slider ticks, core descriptions.
- Barlow-Regular (400): body copy.
- Barlow-Bold (700): inline <b> in notes.
- NEW: Barlow-Italic.ttf (400 italic), for the lobby system chat lines ('Juno joined Team A.'). Add it as a 5th body handle, or a separate field, and select it via the role, not via FontStyle. FontStyle on a static face would only fake an oblique slant.
- Barlow-Medium and Barlow-SemiBold are unused by the hub pages. Keep them (they cost about 210 KB) or drop them from UiFonts.

LICENCE
- SIL Open Font License 1.1 for both families. Copyright 2017 The Barlow Project Authors.
- Ship OFL.txt next to the fonts (already there), and name it in the PR or README credits.
- Embedding the fonts in the binary is allowed. They must not be sold on their own.

DOWNLOAD URLS
All tested from this container with `curl -sI -L` and returned HTTP/2 200. Use raw.githubusercontent.com; github.com/google/fonts/raw/... returns 403 through the agent proxy.
- https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/BarlowCondensed-Medium.ttf (103,360)
- https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/BarlowCondensed-SemiBold.ttf (109,428)
- https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/BarlowCondensed-Bold.ttf (109,912)
- https://raw.githubusercontent.com/google/fonts/main/ofl/barlowcondensed/OFL.txt (4,377)
- https://raw.githubusercontent.com/google/fonts/main/ofl/barlow/Barlow-Regular.ttf (104,068)
- https://raw.githubusercontent.com/google/fonts/main/ofl/barlow/Barlow-Bold.ttf (108,220)
- https://raw.githubusercontent.com/google/fonts/main/ofl/barlow/Barlow-Italic.ttf (109,624): the only file to add.
- https://raw.githubusercontent.com/google/fonts/main/ofl/barlow/OFL.txt (4,377)
I downloaded nothing into the repo.

GLYPH COVERAGE (fc-query on the bundled files)
- Present: · × − – — • ° ≤ ≥ … ÷ ‹ › ◊ and Latin-1 / Latin Extended. tnum is in GSUB, and the normal line height is 1.2.
- Missing: ↑ ↓ ← → ✕ ◯ ▢ △ ■ ▼ ⇅ ★.
- Fixes:
  1. Preferred: icon PNGs (key_updown.png for the [↑↓] key cap; see icons).
  2. Optional symbol fallback, for the Keybinds gamepad column, '800 DPI → 40.8 cm' and 'T1 → T4': a TextSpan in DejaVu Sans Bold. DejaVu Sans Bold has every missing glyph, including ⇅.
     - It is already on this machine at /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf (about 700 KB).
     - Licence: Bitstream Vera / DejaVu, permissive. https://raw.githubusercontent.com/dejavu-fonts/dejavu-fonts/master/LICENSE returns 200.
     - Noto Sans Symbols 2 (OFL; https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssymbols2/NotoSansSymbols2-Regular.ttf, 1.23 MB, 200) has ✕ ◯ ▢ △ ■ ▼ but NO arrows. I checked it in the scratchpad, so it is not enough on its own.
  3. Or use ASCII fallbacks, as the keybinds spec lists ('WHEEL DN', 'D-pad UP', 'A / X'...).

BEVY USE
- One TextFont per role: TextFont::from_font_size(px).with_font(handle_for_weight). Add font_features [FontFeatureTag::TABULAR_FIGURES] for numbers.
- LetterSpacing::Px(px × em) and LineHeight as components on the same entity.
- Do not rely on TextFont.weight; it only works with variable fonts.

## implementation_order
SCOPE
The user said "the hud is bad, the hub is great". So build the HUB screens first, and do NOT build the HUD mockup 01/02, the compact vitals readout or the reviver overlay.

Several specs cover in-match overlays: the scoreboard, the death recap, the Downed state and the health panel ("the HUD vitals block expanded"). Treat them as phase 7 and confirm with the user before building them. The Downed state is gated off anyway, because the sim has no downed state.

MODULE PLAN (game/crates/val_etf/src)
- ui_kit/: grows from the existing untracked ui_kit.rs.
  - mod.rs: UiKitPlugin and UiScale. Change follow_window_scale to UiScale = min(h/1080, w/1920) so 4:3 and 16:10 windows never clip the 1824-wide Loadout and Lobby.
  - tokens.rs: groups A-F.
  - text.rs: the TextRole enum and the font handles. Add Barlow-Italic.
  - icons.rs: an Icon enum mapped to Handle<Image>.
  - state.rs: hover, pressed, selected and disabled styling. Disabled stores base colours and applies ×.35.
  - focus.rs: keyboard navigation, the teal focus ring, and an Esc / back stack.
  - anim.rs: pulse, caret and orbit.
  - widgets/: one file each for panel, chrome (top and bottom bars, backgrounds), button, keycap (and hints), nav_row, tabs, segmented, select (and dropdown), input, stepper, slider, switch (and checkbox), tiles, rows, popover (and modal), chips, pips (TierPips, ArcChip, AmmoPips, WeightSquares), bars (and ring), portrait, halo_widget.
- screens.rs:
  - AppState: MainMenu, Connecting, Lobby, InGame.
  - A Screen stack resource (or SubStates) for overlays that can open over a running match: EscMenu, Loadout{from}, Settings{tab, from}, Confirm(kind), Popover. The stack gives "return to opener" semantics.
- main_menu.rs: the shell, plus join_flyout and host_flyout (or a main_menu/ folder). It replaces menu.rs.
- loadout/: mod.rs (layout, columns, top bar), mags.rs (the 6-slot strip and ammo picker), popover.rs (attachment list), halo_col.rs, preview.rs (placeholder image now, ViewportNode later).
- settings/: mod.rs (shell, rail, Settings resource, persistence), plus gameplay.rs, mouse.rs, keybinds.rs, video.rs, audio.rs, hud_access.rs.
- esc_menu.rs: includes the confirm modal. It replaces hud.rs PauseRoot.
- lobby.rs.
- Later: scoreboard.rs (replaces hud.rs ScoreboardText) and death_recap.rs.
- Support:
  - user_config.rs: <config>/shardline/settings.ron (including player_name and the default host port), loadouts.ron (presets plus the last attachments per weapon) and recent.ron.
  - loadout_text.rs: the shared formatters for tier labels, ammo labels, gear cost text and loadout summaries.
- Data:
  - game/assets/data/ui.ron: UI strings, stat-bar ranges, signal thresholds, option lists, map cards.
  - agents.ron.
  - settings.ron (defaults and ranges).
  - New fields: ammo.ron 'name'; attachments.ron 'name', 'short', 'blurb', 'optional'; armor.ron core blurb and tagline.

ORDER (each step keeps cargo build and cargo test green)

0. FOUNDATIONS
   - Commit the fonts and ui_kit.rs.
   - Finish tokens and TextRole.
   - Build Panel, Button, KeyCap, Hint, NavRow, the state, disabled and focus systems, and the gradient helper (Srgba, FarthestCorner).
   - Run the rasteriser for icons, shapes and halo layers, and copy the images.
   - Enable bevy 'jpeg' and 'system_clipboard'.
   - Add the Screen stack and user_config persistence.
   - Tests:
     - token hex values;
     - em → px spacing;
     - the tier-label rule;
     - the weight class from arc tiers;
     - short and long ammo labels;
     - the shared gear-cost function, moved into vetf_sim;
     - settings.ron round-trip.

1. MAIN MENU: shell, Join flyout, Host flyout.
   - Depends only on the kit and on net.rs.
   - Add a HostSettings resource: lobby name, access, max players (even values), port 47820, password.
   - Recent list persistence.
   - Show the error slot from Session.status.
   - Player card with the MAGS line and the GEAR readout.
   - Render LOADOUT and SETTINGS disabled ('LATER') until steps 2 and 3 land.
   - CREATE LOBBY hosts TDM directly (phase 1).

2. LOADOUT: page, popover, ammo picker, 6-mag strip.
   - It carries the user's new direction: ordered mags with ammo per mag, learned against the reload radial.
   - Change LoadoutChoice:
     - mags as [Option<AmmoChoice>; 6], so gaps keep their slot; add a serialization test;
     - custom armor { core, tiers[4] } instead of a preset id;
     - agent (cosmetic).
   - Add a LoadoutUpdate client→host message, applied at the next spawn. The ESC menu and the lobby reuse it.
   - Presets go in loadouts.ron.
   - The halo widget uses static PNG layers.
   - The preview starts with mako_dark.jpg and fixed hotspot positions; the ViewportNode with projected *_SOCKET_* hotspots comes after.
   - Enable the main-menu LOADOUT row.

3. SETTINGS: shell and control kit (seg, slider, switch, dropdown, fields, keybind caps).
   - Build the tabs in this order:
     a. Mouse & Aim: sensitivity in cm/360 feeding client.rs; FOV feeding render.rs and hud.rs.
     b. Keybinds: rebinding, including the Reload tap/hold radial row and the static '1 – 6' row.
     c. Gameplay: name, port, radial hold time (moved from the RELOAD_HOLD_S const).
     d. Video: window mode, V-sync, AA, shadows, brightness, performance overlay.
     e. HUD & Accessibility: rows that bind to the current HUD; the rest disabled.
     f. Audio: values stored; Master drives GlobalVolume.
   - Enable the main-menu SETTINGS row.

4. ESC MENU and confirm modals (stop hosting, leave, restart).
   - Reuses NavRow and Modal.
   - LOADOUT and SETTINGS open as Screen-stack overlays over the running match; CONTROLS opens Settings on Keybinds.
   - RESTART MATCH needs a host reset.
   - PLAYERS and BACK TO LOBBY stay disabled ('LATER') until step 5.
   - Add the HostClosing message so clients see 'The host stopped hosting.' in the Join flyout.

5. LOBBY. This is the largest backend change.
   - Lobby phase in a replicated LobbyState: settings, ready flags.
   - Chat messages.
   - PlayerNet ping, loss and jitter.
   - Kick and move.
   - START MATCH.
   - Then switch the Host flyout CREATE LOBBY to the lobby (phase 2), enable ESC BACK TO LOBBY and PLAYERS, and return to the lobby when the match ends.

6. POLISH
   - Gamepad and keyboard focus pass.
   - The colour-blind token swap.
   - 4:3 and 21:9 checks.
   - Screenshots against the PNGs at 1920x1080.

7. IN-MATCH OVERLAYS (only after user confirmation)
   - Scoreboard: needs the new MatchStats.
   - Death recap: needs DamageTaken, HitConfirm and KillFeed extensions, plus the halo UiMaterial for the drain.
   - Skip the health panel, compact vitals, Downed and the reviver.

## cross_screen_notes
NAVIGATION GRAPH
1. Launch goes to MainMenu, which hosts the PLAY flyouts.
2. PLAY > HOST GAME > CREATE LOBBY:
   - phase 1: Connecting → InGame (TDM on Showhome);
   - phase 2: Lobby, as host.
3. PLAY > JOIN GAME > JOIN LOBBY → Connecting → Lobby. If the match is already live, go straight to InGame.
4. GUN RANGE: host the range → Connecting → InGame.
5. Main-menu LOADOUT opens Loadout; BACK or CONFIRM returns to MainMenu.
6. Main-menu SETTINGS opens Settings; BACK or DONE returns to MainMenu.
7. QUIT exits the app.
8. In the Lobby:
   - LOADOUT opens Loadout; it returns to the Lobby and sends LoadoutUpdate.
   - START MATCH goes to InGame for everyone.
   - LEAVE: a client goes to MainMenu; the host first sees the STOP HOSTING? modal, then goes to MainMenu.
   - Clicking your own row also opens Loadout.
9. In InGame, Esc opens the ESC menu as an overlay:
   - RESUME closes it.
   - LOADOUT opens Loadout in next-spawn mode; it returns to the ESC menu.
   - SETTINGS opens Settings on the last-used tab; CONTROLS opens Settings on Keybinds.
   - PLAYERS opens the host players card.
   - RESTART MATCH opens a warn modal.
   - BACK TO LOBBY sends everyone to the Lobby.
   - STOP HOSTING (host) or LEAVE MATCH (client) opens a confirm modal, then goes to MainMenu.
10. Holding TAB shows the scoreboard (phase 7), also over the ESC menu and over the death recap.
11. On death the death recap shows (phase 7): L opens Loadout, TAB opens the scoreboard, Esc opens the ESC menu.
12. When the match ends (MatchPhase::Ended), go to the Lobby after N seconds (phase 2).

Because Loadout and Settings must open over a RUNNING match, they cannot be top-level AppStates. The main-menu spec's 'AppState::Loadout' and 'AppState::Settings' conflict with this. Use AppState {MainMenu, Connecting, Lobby, InGame} plus a Screen stack with 'return to opener' semantics.

Esc means 'back one level' everywhere:
- main-menu nav: no effect;
- a flyout: back to the nav;
- a popover or context menu: closes it;
- Loadout: BACK (discards unconfirmed edits);
- Settings: BACK (saves; values already apply live);
- a modal: CANCEL;
- the ESC menu: RESUME;
- a focused or listening field: cancels the edit first.

INCONSISTENCIES BETWEEN THE GROUP SPECS (and how to resolve each)
1. LETTER-SPACING: the lobby, scoreboard, settings and esc/death specs say LetterSpacing::Rem(em). In bevy_text 0.19.1, Rem multiplies the global RemSize, not the font size. Use Px(size × em) everywhere, as ui_kit.rs and the main-menu and loadout specs do.

2. MAGAZINES:
   - LoadoutChoice ALREADY has `mags: Vec<AmmoChoice>` (commit f23e252), and rules.ron default_loadout already lists 4 STANDARD mags. The main-menu spec's "today one AmmoChoice + spare_mags" is stale.
   - Gear cost is already summed PER MAG (vetf_sim weapon.rs ammo_gear_cost and the server test gear_budget_prices_armor_and_each_magazine). Loadout open question 1 is therefore answered: per mag.
   - A Vec cannot hold gaps, but the Loadout spec allows them ('+ ADD MAG' in any slot; right-click empties MAG 2-6). Gaps matter because the user wants slot positions learned. Change the field to [Option<AmmoChoice>; 6] with index 0 required, and add a serialization test.
   - The ammo.ron header comment ('ONE ammo… no per-magazine sorting') is stale.

3. AMMO LABELS: ammo.ron labels are 'STD', 'AP', 'RIP', 'SLUG'. SLUG has 2 tiers, so it is 'SLUG I' / 'SLUG II', not a bare 'SLUG'.
   - Short label (chips, MAGS line, popover cells, death weapon cell) = label + roman tier: STD, AP I-III, RIP I-III, SLUG I-II.
   - Long name (mag card, ammo picker) needs a new `name` field: STANDARD, AP II, and so on. Standard has a single tier and therefore no numeral.

4. AMMO COLOUR: the specs use three schemes:
   - Loadout: by type (bone / ice / coral / sand);
   - ESC menu fallback: by tier (t1 / t2 / t3);
   - Lobby VIEW LOADOUT: tier-coloured borders.
   Use the BY-TYPE colours everywhere, with tier shown as a numeral and pips. Halo tier colours must keep one meaning, because enemies read them.

5. HALO TIER DISPLAY for per-arc tiers:
   - The specs differ: highest-tier N pips (main-menu agent tag), 4-pip arc chip (lobby and scoreboard), 'T{min}-T{max}' (ESC), 'T2 CORE only if uniform' (loadout and health).
   - Unify:
     - ArcChip (H, T, A, L pips in per-arc colours) for every player-halo summary: agent tag, lobby rows, scoreboard, VIEW LOADOUT.
     - Tier label: 'T{n}' when every covered arc has the same tier; 'T{min}–T{max}' (en dash) when mixed; 'NO HALO' with no arcs. The label is coloured with the highest tier.
     - Weight from armor.ron weight_bands on Σ arc tiers. The default Mender Scout (H2 T2) is LIGHT, not the mockup's MEDIUM.

6. GEAR BUDGET is 12 everywhere (rules.ron tdm.gear_budget), not 20.
   - The cost function is armor.gear_cost (Σ arc tiers) + Σ per-mag ammo gear_cost. Share ONE function from vetf_sim across the player card, the Loadout RESULT, the ESC GEAR row, the lobby own-row suffix and the server.
   - The effective budget depends on context:
     - lobby setting (OFF / 20 / 12, default 12) when in a lobby;
     - 'TDM DEFAULT' 12 from the main menu;
     - 'NO LIMIT' in the gun range.

7. PORT and CODE:
   - Use 47820 (net.ron), never 7777: Host flyout PORT, Settings 'Default host port', lobby address lines, CONNECTION panel, Recent sublines.
   - The Host flyout default comes from Settings, then --port overrides it.
   - Join codes are 'XXXX-XXXX-XX' (12 characters) everywhere, never 'SHRD-4K7Q'. The lobby code box is right-anchored and grows to the left. The ESC value column is 360 px wide, which fits.
   - No relay: JOIN CODE and DIRECT IP reach the same hosts, and the copy must say so.

8. MAX PLAYERS: the Host stepper allows any value from 2 to 10, while the lobby select offers [2, 4, 6, 8, 10] as '{n} ({n/2} v {n/2})'. Use EVEN values only in both (the stepper moves in steps of 2), limited to rules.tdm.max_players and net max_remote_clients + 1.

9. NOT-BUILT LABEL: three different words are used (main menu 'SOON', ESC 'NOT YET', keybinds 'LATER'). Use 'LATER' everywhere; it is already the lobby mockup's word ('+ ADD BOT (LATER)'). Style: .35 opacity and a MICRO label.

10. FOCUS and SELECTION ACCENT:
    - Keyboard focus ring: TEAL Outline 2 px, offset 2 (the modal spec proposed TEXT_HI).
    - The active bar is TEAL on the main menu but TEXT_HI in the ESC menu. Keep that per the mockups as a NavRow parameter. The danger row uses ENEMY.

11. SETTINGS ENTRY TAB: the ESC spec says 'first tab'; the Settings spec says 'last-used tab' (first time: MOUSE & AIM). Use last-used. CONTROLS always opens KEYBINDS.

12. PLAYER NAME:
    - The main-menu spec stores it in profile.ron with any 16 non-control characters; the Settings spec stores it in settings.ron with A–Z 0–9 _ - only, forced uppercase.
    - Unify: one value, Settings.gameplay.player_name, in <config>/shardline/settings.ron. Rules: 1–16 characters, A–Z 0–9 _ -, forced uppercase. --name overrides it for the run.
    - The main-menu EDIT NAME and the Settings field edit the same value.

13. HEAL KEY: the Keybinds adaptation proposes Heal = 4 and Health panel = H. In the game, H toggles the heal ring (client.rs heal_input), and the health-panel spec opens the panel with the ring.
    - Default 'Heal · item radial (toggle)' to H, matching the game.
    - Drop the separate 'Health panel' bind, or leave it unbound.
    - Number keys 1–6 pick mags only while the reload radial is open; 1/2/3 load presets on the Loadout screen. Both are allowed context overlaps.

14. ESC MENU vs LOADOUT 'Kestrel ·': the ESC menu and death recap drop the agent, while the lobby and scoreboard show 'Kestrel' for everyone. Once Loadout ships LoadoutChoice.agent, every screen reads it; until then show nothing (ESC) or 'Kestrel' (lobby), as each spec says.

15. TEAM COLOURS are relative (ALLY / ENEMY) on every screen. hud.rs 'TEAM TEAL' / 'TEAM CORAL' must go. TEAL and CORAL remain the agent accents and TEAL remains the focus accent.

16. DUPLICATE SETTINGS:
    - 'Show net graph' (Gameplay) and Video '+ NETWORK' are one value.
    - HUD 'Hold / toggle' and Mouse 'ADS INPUT' overlap: keep ADS on the Mouse tab only.
    - Video 'never hide enemy outlines' conflicts with HUD 'Enemy outline OFF': ship ON | THICK and ask design.

17. HALO ORDER: the halo puts Legs on the right and Torso at the bottom; the radial.rs REGION_ORDER puts Torso on the right and Legs at the bottom. Label the region-ring chips with icon and name. This matters only in-match. The mag reload-wheel glyph must match radial.rs: slot 1 at the top, then clockwise.

18. OPAQUE SURFACES: #141A22 (context menu), #11161D (modal) and #10151C (dropdown) differ by 1-4 levels. Keep three tokens to mirror the mockups.

19. DATA OVER MOCKUP NUMBERS:
    - Mender regen 20/s after 2.5 s;
    - shield 132 for the default;
    - sprint 7.0;
    - Mako 720 rpm and 25 m range;
    - PHASE 'IMMUNE TO SLOW';
    - no 'SIDE R';
    - HANDLING becomes MOBILITY;
    - no food drain.

20. ASPECT RATIO: only the main-menu spec covers it. With UiScale = height/1080, a 4:3 window is 1440 logical px wide and clips the Loadout (content to x 1872) and the Lobby. Use UiScale = min(h/1080, w/1920). Left- and right-anchored blocks keep their insets, and extra width appears between them.

21. NO AMMO COUNTS anywhere: no rounds left on mag cards, chips, popovers, the lobby or the scoreboard. MAG SIZE (capacity) appears only in the MAG attachment slot and the stats panel.

22. MOCKUP-ONLY elements, never ship:
    - 'MOCKUP 0x …' labels;
    - the Loadout badge 'LIVE 3D PREVIEW · VIEWPORTNODE';
    - the main-menu 'REGION: AUTO · RELAY REACHABLE';
    - hud_street.jpg as an in-match backdrop.

