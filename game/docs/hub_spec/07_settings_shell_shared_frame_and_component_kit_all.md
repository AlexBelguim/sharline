# Settings shell: shared frame and component kit (all six tabs)

## source_files
[
 "/home/user/sharline/design/ui/mockups/_src/pages/settings.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg",
 "/home/user/sharline/design/ui/mockups/settings.html",
 "/home/user/sharline/design/ui/mockups/png/08_settings_mouse.png",
 "/home/user/sharline/design/ui/mockups/png/08b_settings_keybinds.png",
 "/home/user/sharline/design/ui/mockups/png/08c_settings_video.png",
 "/home/user/sharline/design/ui/mockups/png/08d_settings_audio.png",
 "/home/user/sharline/design/ui/mockups/png/08e_settings_hud.png"
]

## purpose
One full-screen settings screen with a fixed frame: top bar, left tab rail, a content pane that swaps per tab, and a bottom action bar. All six tabs share it, along with one small control kit (row, segmented control, slider, number field, switch, dropdown, key cap, button). Build the frame and the kit once, then each tab is a list of rows. The user rated the hub screens great, so mirror this closely; no in-match HUD overlays belong here. All geometry was measured with headless Chromium on the built mockup (Google Fonts loaded) at 1920x1080 and cross-checked against the PNGs.

## layout
Reference canvas 1920x1080. Per common.css, every px maps 1:1 to Val::Px with UiScale = window_height / 1080. Things anchored left/right stretch on wider windows. Coordinates are x,y,w,h from the top-left.

ROOT: full screen, absolute, overflow clip. Background is a radial gradient: CSS 'radial-gradient(ellipse at 60% 30%, #141B25 0%, #090C11 60%, #06080B 100%)'. In Bevy: BackgroundGradient(RadialGradient{ position 60%/30%, shape FarthestCorner (the CSS ellipse default), stops #141B25@0, #090C11@60%, #06080B@100% }). It is opaque, even when opened from the in-match ESC menu.

1) TOP BAR: anchored top, left 0, right 0, height 84 (0..84). Flex row, align center, padding 0 48, column gap 24, border-bottom 1px --stroke rgba(255,255,255,.09).
   - Title 'SETTINGS' at x48 y18 (box 184x48), vertically centred.
   - Flex spacer.
   - Hint text at x1393 y33 (323x17), right-aligned group.
   - BACK button at x1741 y20, 131x44, anchored right 48. It holds a ghost key cap 'ESC' (33x20) at x1816 y32.
2) TAB RAIL: anchored left 48, top 112, width 260. Six tabs stacked with no gap, each 260x52: GAMEPLAY y112, MOUSE & AIM y164, KEYBINDS y216, VIDEO y268, AUDIO y320, HUD & ACCESSIBILITY y372 (rail ends y424). Each tab is a flex row, align center, padding-left 18, border-left 3px. Text starts at x69.
3) CONTENT PANE: absolute left 340, top 112, right 48, bottom 104, so 1532x864 at 1080p (x340..1872, y112..976). Flex row, column gap 24. Two columns flex:1 each (754 wide: col A x340..1094, col B x1118..1872). The KEYBINDS tab is the exception: flex 1.05 / 1 gives 771 + 737 (A x340..1111, B x1135..1872). Each column is a flex column with row gap 14, min-width 0.
   - Card = panel with padding 18 top/bottom and 20 left/right, plus a 1px border. Inner content therefore starts at col_x+21 and y+19, and is 712 wide (729 / 695 on keybinds).
   - Two card patterns exist:
     (a) The column itself is the card (Video, Audio, HUD, Gameplay, Keybinds). The card fills the full 864 height, and its children are separated by the 14px column gap, so rows sit on a 64px pitch: first row at y167, then 231, 295, 359, 423, 487, 551, 615.
     (b) A column holds stacked cards (Mouse & Aim). Rows inside a card have no gap, so the pitch is 50px.
4) BOTTOM BAR: anchored bottom, left 0, right 0, height 80 (y1000..1080). Flex row, align center, padding 0 48, gap 12. Border-top 1px --stroke, background rgba(5,7,10,.60).
   - Left: hint group 1 at x48 y1030 (key caps Q at x48 and E at x77, each 22x22, then the label 'TABS'), and hint group 2 at x150 (R cap, then 'RESET TAB').
   - Spacer.
   - RESET ALL button at x1637 y1019, 134x44.
   - DONE primary button at x1783 y1019, 89x44, anchored right 48.
5) Do not build the mockup's 'MOCKUP 08 · SETTINGS' label (bottom-right). It exists only in the mockup.

## elements
TOKENS (common.css):
- Surfaces: --bg0 #07090D, --panel rgba(9,12,17,.70) (#090C11 at 70%), --panel-solid #10151C, --stroke rgba(255,255,255,.09), --stroke-mid rgba(255,255,255,.16), --stroke-hi rgba(255,255,255,.32).
- Text: --text-hi #F3F0E9, --text #D7D4CD, --text-mid #9CA2AB, --text-low #646B75.
- Accents: --ally #52E5A5, --enemy #FF4D5A, --teal #00DACE, --warn #FFA23A.

FONTS: --fd = 'Barlow Condensed' (500/600/700); --fb = 'Barlow' (400, plus 700 for <b>).
- Bevy 0.19 TextFont.weight only works with variable fonts, so ship static TTFs per weight: BarlowCondensed-SemiBold and BarlowCondensed-Bold, Barlow-Regular and Barlow-Bold.
- Letter-spacing: use the LetterSpacing component. LetterSpacing::Rem(x) equals CSS x em.
- Line height: CSS 'normal' is about 1.2, which is Bevy's default LineHeight::RelativeToFont(1.2).
- Bevy has no text-transform, so write uppercase copy in code. The copy below is given as rendered.
- '.num' fields use tabular figures: TextFont.font_features 'tnum'.

TOP BAR
- Title 'SETTINGS': fd 700, 40px, letter-spacing .14em (5.6px), #F3F0E9.
- Hint 'Changes apply instantly · saved to settings.ron' (mixed case): fd 600, 14px, ls .14em (1.96px), --text-mid #9CA2AB.
- BACK button (.btn): height 44, padding 0 22, gap 10. Text fd 700, 18px, ls .12em (2.16px), uppercase, #F3F0E9. Background rgba(255,255,255,.06), border 1px rgba(255,255,255,.16), radius 0. Hover: bg rgba(255,255,255,.12), border rgba(255,255,255,.32).
- Ghost key cap 'ESC' inside BACK: height 20 (override), min-width 22, padding 0 6. Text fd 700, 13px, ls .04em, #F3F0E9. Transparent bg, border 1px rgba(255,255,255,.32), radius 2.

RAIL TAB
- Text fd 700, 20px, ls .14em (2.8px).
- Idle: text --text-mid #9CA2AB, border-left 3px transparent, no bg.
- Hover: text #F3F0E9.
- Selected: text #F3F0E9, border-left 3px #F3F0E9, background LinearGradient 90deg rgba(255,255,255,.07) to rgba(255,255,255,0) across the 260px.
- Copy: GAMEPLAY / MOUSE & AIM / KEYBINDS / VIDEO / AUDIO / HUD & ACCESSIBILITY.

CARD (.card.panel): bg rgba(9,12,17,.70), border 1px rgba(255,255,255,.09), radius 2px, padding 18/20.
- Card title h2: fd 700, 18px, ls .18em (3.24px), #F3F0E9, 22px tall. It is a flex row with space-between and baseline alignment.
- Optional right-aligned micro tag: fd 600, 11px, ls .16em, uppercase, --text-low #646B75.
- A sub-heading inside a card (e.g. Video 'PERFORMANCE OVERLAY') uses the same h2 style with margin-top 12.

ROW (.row): CSS grid with columns 230px | 1fr, align-items center, min-height 50, border-bottom 1px rgba(255,255,255,.09). The last row in a card has no border.
- Label (.k): fd 600, 14px, ls .12em (1.68px), uppercase, --text #D7D4CD.
- Optional sub-label (.k small): block, Barlow 400, 12px, no letter-spacing, normal case, --text-mid #9CA2AB, margin-top 1. It may wrap onto 2 lines within 230px.
- Control column = x+230, 482 wide.
- Control group (.ctl): flex row, align center, gap 12.

NUMBER/TEXT FIELD (.inp): height 36, min-width 90 (often overridden: 70 / 64 / 56 / 80 / 280). Padding 0 10, border 1px rgba(255,255,255,.32), bg rgba(0,0,0,.35). Text fd 700, 18px, #F3F0E9, no letter-spacing, left-aligned, vertically centred.
- Big variant (.inp.big): height 44, text 24px, min-width 140.
- Unit text (.unit): fd 600, 14px, ls .08em (1.12px), --text-mid.

SLIDER: track height 4, bg rgba(255,255,255,.14), flex:1.
- Fill: from the left to the value, #F3F0E9.
- Thumb: 16x16 #F3F0E9 square rotated 45deg (UiTransform rotation), centred on the value (its bounding box is about 23x23).
- Optional tick labels: fd 500, 11px, --text-low, 10px below the track top, centred on their % positions, no wrap. The mockup wraps '80 cm' and '120 %'; keep them on one line.
- Slider + field rows: slider 400 wide, gap 12, field 70x36 at control x+412. Audio meters use a 340 slider, gap 10, field 64x36.

SEGMENTED (.seg): flex row. Each option is height 34, padding 0 14, centred. Border 1px rgba(255,255,255,.16), margin-left -1 so borders overlap.
- Option text: fd 700, 15px, ls .08em (1.2px), --text-mid. The copy is NOT force-uppercased: write it exactly as given, e.g. 'NIGHT (compressed)'.
- Selected: bg #F3F0E9, text #07090D, border #F3F0E9.
- Hover (not in CSS; proposed): unselected text becomes #F3F0E9 and border rgba(255,255,255,.32).

SWITCH (.sw): 46x24, radius 12.
- Off: bg rgba(255,255,255,.14), knob 18x18 circle at x3 y3, #9CA2AB.
- On: bg --ally #52E5A5, knob at x25 y3, #06140D.
- Hover (proposed): knob brightens to #F3F0E9 when off.

DROPDOWN (.dd): height 36, min-width 150 (often fixed: 240 / 300). Padding 0 10, flex space-between, gap 16. Border 1px rgba(255,255,255,.32), transparent bg. Text fd 700, 16px, ls .06em (0.96px), #F3F0E9. Chevron icon i-chev 12x12, #F3F0E9, at the right.
- Open list (not in mockup; proposed): panel-solid #10151C, border 1px rgba(255,255,255,.32), 36px rows in the same font. Hover row bg rgba(255,255,255,.06); the selected row's text is #F3F0E9 with an i-check icon.

NOTE TEXT (.note): Barlow 400, 12.5px, line-height 1.45, --text-mid. Inline <b> is Barlow 700 #F3F0E9.

BOTTOM BAR
- Hint group: flex row, gap 7.
  - Ghost key caps 22x22: fd 700, 13px, ls .04em, #F3F0E9, border 1px rgba(255,255,255,.32), radius 2.
  - Labels 'TABS' and 'RESET TAB': fd 600, 14px, ls .14em, --text-mid.
- RESET ALL: same as .btn above.
- DONE: .btn.primary, i.e. bg #F3F0E9, text #07090D, border #F3F0E9. Hover bg #FFFFFF.

DISABLED (any control or row): opacity .35, no interaction. This matches .btn[disabled]; use it for features the prototype does not have yet.

## data_bindings
Back the whole screen with one Settings resource (serde, RON) with sub-structs gameplay, network, mouse, crosshair, keybinds, video, audio, hud.
- Defaults and ranges: a new game/assets/data/settings.ron. Per the project rule that tunable numbers live in data, slider ranges and steps live here too.
- User values: written to the user config dir as settings.ron, e.g. $XDG_CONFIG_HOME/shardline/settings.ron or %APPDATA%\shardline\settings.ron. That is the file the top-bar hint names.
- 'Changes apply instantly': every control writes the resource immediately and systems react on Changed<Settings>. Save to disk debounced (about 0.5 s after the last change) and again on DONE/BACK.
- If saving fails, replace the top-bar hint with 'Could not save settings.ron' in --warn #FFA23A.
- Command-line flags (--name, --port) override the saved values for that run only.

## interactions
ENTRY POINTS
- Main menu nav item 'Settings' (main_menu mockup).
- In-match ESC menu item 'Settings'. There the match keeps running underneath, and settings must swallow all game input.
- ESC menu 'Controls · KEY REFERENCE' opens this screen on the KEYBINDS tab.
- The screen opens on the last tab used. The first time, it opens on MOUSE & AIM, as the default mockup render does.

TABS: click a rail tab to switch. Q = previous tab, E = next tab, wrapping around.

RESET
- R resets the current tab's settings to defaults.
- RESET ALL resets everything. Proposed: confirm first with a small modal 'Reset all settings to default?' offering CANCEL and RESET ALL (danger style: text --enemy, border rgba(255,77,90,.45)).

LEAVING: BACK (ESC) and DONE both save and return to the opener (main menu or ESC menu). Values already applied, so there is no 'discard' path.

HOTKEY SUPPRESSION: Q/E/R/ESC hotkeys are off while a text or number field has focus, and while a key cap is listening for a rebind.
- In those states ESC cancels the edit or listen instead of leaving the screen.
- Enter commits a field. Escape reverts it. Clicking outside commits.

INPUT
- Mouse: Button + Interaction drive all hover and press states.
- Sliders: drag the thumb, click the track to jump, mouse wheel over a slider moves one step. The field next to a slider is editable and clamps to the range on commit.
- The in-game ESC pause toggle (client.rs toggle_pause) must not fire while settings are open.

## adaptations
1. Mockup glyphs Barlow lacks. Measured with fontTools: Barlow / Barlow Condensed have no ↓ ↑ ← → ✕ ◯ ▢ △ (they do have × ° · … — – ÷). Bevy needs a font that has every glyph, so either:
   - render these as a separate TextSpan using a symbol font (e.g. Noto Sans Symbols 2 or DejaVu Sans) in game/assets/fonts, or
   - use small PNG glyphs.
   The affected strings are the WHEEL ↓ cap, the D-pad arrows and pad face buttons in Keybinds, 'T1 → T4' in Audio, and '800 DPI → 40.8 cm' in Mouse.
2. Bevy has no dashed borders. For the unbound key cap, use a 9-slice dashed-rect PNG, or a solid rgba(255,255,255,.16) border as a fallback.
3. Bevy has no CSS text-transform or tables. Write copy in uppercase in code. Use Display::Grid with fixed column widths for the keybinds tables.
4. Fonts must be added to game/assets/fonts (Barlow and Barlow Condensed, OFL). The game currently uses the default font (menu.rs).
5. Gameplay pane mockup bug: the 'Default host port' field stretches the full 482px. Make it 140 wide.

## assets
Icons from icons.svg used on settings: i-chev only (12x12 viewBox, path 'M2 3l4 4 4-4', stroke 2, currentColor), used as the dropdown chevron. Rasterise it to a white PNG (24x24 for 2x) and tint it via ImageNode.color.

Images: /home/user/sharline/design/ui/mockups/img/hud_street.jpg (1920x1080) for the crosshair preview, see the Mouse & Aim tab. Copy it into game/assets/ui/.

New rasters to make:
- a dashed key-cap 9-slice
- arrow and pad-glyph PNGs, unless a symbol font is used
- the i-check icon (icons.svg) if the proposed dropdown list is built

