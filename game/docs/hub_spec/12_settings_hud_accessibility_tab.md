# Settings · HUD & Accessibility tab

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/08e_settings_hud.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/settings.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css"
]

## purpose
HUD scale and placement, HUD element options, colour-blind team colours, enemy outline, screen shake, damage flash, flashing reduction, text size, and hold/toggle. It is a settings (hub) screen, so build it even though the in-match HUD mockup itself is rejected. Its rows bind to whatever HUD the game has.

## layout
Pane pattern (a). Two 754-wide column cards.

COLUMN A 'HUD' (x340)
- h2 y131.
- Rows at y167, 231, 295, 359, 423, 487, 551, 615 (64 pitch).
- Controls at x591. Slider rows: slider 400 + field 70 at x1003.

COLUMN B 'COLOUR & COMFORT' (x1118)
- h2 y131.
- Row 'Team colours' at y167, min-height 76: seg at y174, colour preview line at y218.
- Later rows at y257, 321, 385, 449, 513, 577.
- Controls at x1369. The slider row field is at x1781.

## elements
HUD
- 'HUD SCALE': slider at 50%, ticks '80 %' (0%) and '120 %' (100%), field '100 %'.
- 'SAFE AREA MARGIN', sub-label 'Pushes HUD in from the screen edge': slider at 30% + field '32 px'.
- 'ULTRAWIDE HUD WIDTH': seg '16:9 CENTRE' (selected) | 'FULL WIDTH'.
- 'HEALTH NUMBERS': seg 'SHOW' (selected) | 'BARS ONLY'.
- 'MINIMAP': seg 'ROTATE' | 'NORTH UP' (selected).
- 'DAMAGE NUMBERS': seg 'OFF' (selected) | 'ON'.
- 'KILL FEED LINES': seg '3' | '5' (selected) | '7'.
- 'SHOW ENEMY NAMES': seg 'ON SCAN / AIM' (selected) | 'NEVER'.

COLOUR & COMFORT
- 'TEAM COLOURS', sub-label 'Halo tier colours never change; tiers also show as I–IV pips' (2 lines).
  - Seg 'DEFAULT' (selected) | 'DEUTAN' | 'PROTAN' | 'TRITAN'.
  - 10px below it, a preview line (flex, gap 10). Each item is a flex span (gap 6, fd 700 14px ls .1em) with a 14x14 colour square:
    - [■ #52E5A5] 'ALLY' in #52E5A5
    - [■ #FF4D5A] 'ENEMY' in #FF4D5A
    - '· Deutan/Protan: ally [■ #3FA9F5] enemy [■ #FFB000]' in --text-mid
- 'ENEMY OUTLINE': seg 'ON' (selected) | 'THICK' | 'OFF'.
- 'SCREEN SHAKE': slider 400 at 60% + field '60 %'.
- 'DAMAGE FLASH', sub-label 'Red / hex edge flash when hit': seg 'OFF' | 'SOFT' (selected) | 'FULL'.
- 'REDUCE FLASHING': switch OFF.
- 'TEXT SIZE': seg 'S' | 'M' (selected) | 'L'.
- 'HOLD / TOGGLE', sub-label 'Sprint, crouch, ADS, health panel': seg 'HOLD' (selected) | 'TOGGLE'.

## data_bindings
SETTINGS: control, range, default
- HUD scale: slider + field 80–120 %, step 5, default 100 %. Applies as a factor on the HUD root only, via UiTransform scale or by multiplying HUD px; global UiScale stays height/1080.
- Safe area margin: slider + field 0–100 px, step 1, default 32 px. The HUD mockups use 32px edge offsets. The mockup draws the fill at 30%; use value/100 for the fill.
- Ultrawide HUD width: seg, default 16:9 CENTRE. The HUD root width becomes min(window logical width, height × 16/9), centred.
- Health numbers: seg, default SHOW.
- Minimap: seg, default NORTH UP.
- Damage numbers: seg, default OFF.
- Kill feed lines: seg 3/5/7, default 5. Caps the lines in hud.rs update_feed / Feedback.kills.
- Show enemy names: seg, default ON SCAN / AIM.
- Team colours: seg, default DEFAULT.
  - DEFAULT: ally #52E5A5, enemy #FF4D5A.
  - DEUTAN and PROTAN: ally #3FA9F5, enemy #FFB000.
  - TRITAN: the mockup gives no pair. Proposed ally #00C2C7, enemy #FF3D7F; flag for design.
  - Swaps the ally/enemy colour tokens everywhere: scoreboard, kill feed, HUD, player tints. Halo tier colours T1 #EDF1F6, T2 #59B3FF, T3 #C46CFF, T4 #FFCE50 never change.
  - The preview's first two chips use the selected preset's colours.
- Enemy outline: seg, default ON.
- Screen shake: slider + field 0–100 %, step 5, default 60 %. Scales the visual camera punch only (client.rs LocalControl.punch); never the recoil pattern.
- Damage flash: seg, default SOFT. Scales the damage chevron / edge flash.
- Reduce flashing: switch, default OFF. Caps flash alpha and disables the pulse animations.
- Text size: seg S/M/L, default M. Proposed scale 0.9 / 1.0 / 1.15 on body and label text in menus and HUD.
- Hold / toggle: seg, default HOLD. Applies to sprint, crouch and the health panel.

## interactions
- Changes preview live in match: HUD scale and margin move the HUD immediately when settings are opened from the ESC menu.
- Team colour seg updates the preview chips instantly.
- All other controls work as in the shell.

## adaptations
1. Several rows target HUD features the game does not have: minimap, damage numbers, enemy names / scan, enemy outline rendering, damage flash beyond chevrons, and health numbers in the new HUD. The user rejected the in-match HUD mockup and will redesign the HUD, so show these rows disabled (opacity .35) at their defaults until the redesigned HUD has the feature.
   Wired today: HUD scale, safe area, ultrawide width, kill feed lines, team colours, screen shake, reduce flashing, text size, hold/toggle.
2. Rule conflict: the Video tab says 'settings may never hide halos, hex shards or enemy outlines', yet Enemy outline offers 'OFF'. Recommend shipping 'ON | THICK' only and raising it with the local session or design; do not silently keep OFF.
3. Duplicate: 'Hold / toggle' lists ADS, but the Mouse & Aim tab has its own 'ADS INPUT' HOLD/TOGGLE.
   - Bind ADS to the Mouse tab setting only.
   - Change the sub-label here to 'Sprint, crouch, health panel', or keep the copy and have both rows edit one value.
   - The game has no toggle mode yet; it needs latching in client.rs gather_input.
4. No exact numbers rule: 'HEALTH NUMBERS: SHOW' concerns zone HP, which is allowed. No setting may ever add an ammo count; do not add one.
5. Tier pips 'I–IV' use an en dash, which Barlow has.

## assets
No images, no icons. The colour squares are plain 14x14 nodes.

