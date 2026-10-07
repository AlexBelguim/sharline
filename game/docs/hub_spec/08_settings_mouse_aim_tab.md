# Settings · Mouse & Aim tab

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/08_settings_mouse.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/settings.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/img/hud_street.jpg"
]

## purpose
Raw-input sensitivity expressed as cm/360 (with DPI, importing from other games, and equivalents), ADS sensitivity scaling per optic, field of view, and a crosshair editor with a live preview. This is the main settings render (08_settings_mouse.png) and the default first tab.

## layout
Pane pattern (b): stacked cards, rows on a 50px pitch with no gaps.

COLUMN A (x340, w754)
- Card SENSITIVITY: x340 y112, 754x422.
  - h2 y131.
  - Row 'Mouse DPI': y153, h50.
  - Row 'Turn distance': y203, min-height 96. The field is at y220; the slider is at y278 with ticks at y288.
  - Import box (.conv): x361 y309, 712x78, margin-top 10.
  - Formula note: y395, 712x36, margin-top 8.
  - Ruler block: y444, h71, margin-top 12. Micro label at y449; ruler line at x361 y473.
- Card AIM DOWN SIGHTS: x340 y548, 754x360.
  - h2 y567.
  - Rows at y589, 639, 689, 739, 789, 839 (each h50, label x361, control x591).

COLUMN B (x1118, w754)
- Card FIELD OF VIEW: x1118 y112, 754x200.
  - h2 y131.
  - Row 'Horizontal FOV': y153, min-height 90. Big field at x1369 y167; slider at y225 (482 wide), ticks at y235.
  - Row 'Viewmodel FOV': y243, h50.
- Card CROSSHAIR: x1118 y326, 754x650 (flex:1, fills to y976).
  - h2 y345.
  - Preview box: x1139 y379, 712x250, margin-top 12.
  - Rows at y629, 679, 729, 779 (h50, label x1139, control x1369).
  - Empty space below to the card bottom.

## elements
SENSITIVITY CARD
- h2 'SENSITIVITY'. Right micro tag 'RAW INPUT, NO ACCELERATION, NO SMOOTHING' (x825 y138).
- Row 1 'MOUSE DPI', sub-label 'Read it from your mouse software'.
  - Number field 90x36 at x591 y160 showing '800' (.num).
  - Unit 'counts per inch' at x693.
- Row 2 'TURN DISTANCE', sub-label 'Mouse travel for one full 360° turn'.
  - Big field 140x44 at x591 y220 showing '40.8' (24px).
  - Unit 'cm / 360°' at x743.
  - Unit '= 16.1 in · 0.0280° per count' at x829 (margin-left 14).
  - Below (margin-top 14): a full-width slider 482x4 at x591 y278, fill 40% (193px), thumb at x≈784.
  - Ticks: '15' at 0%, '30' at 23.1%, '50' at 53.8%, '65' at 76.9%, '80 cm' at 100%.
- Import box (.conv): grid columns 1fr|auto|auto|auto, gap 10, padding 12, bg rgba(255,255,255,.04), border 1px rgba(255,255,255,.09).
  - Col 1 (349 wide): label 'IMPORT FROM ANOTHER GAME' in .lbl style (fd 600 13px ls .14em uppercase), colour overridden to --text #D7D4CD. Under it a note: 'Same DPI. Valorant yaw 0.07°, CS2 / Apex 0.022°, Overwatch 2 0.0066° per count.' (2 lines).
  - Col 2: dropdown 150x36 at x733 y330 'VALORANT' with chevron.
  - Col 3: number field 80x36 at x893 '0.400'.
  - Col 4: primary button 77x36 at x983, 'APPLY' (font 15px, padding 0 16).
- Formula note (12.5px, 2 lines): 'cm/360 = 914.4 ÷ (DPI × sens × yaw). Valorant 0.400 at 800 DPI → 40.8 cm. Your value in other games: Valorant 0.400 · CS2/Apex 1.273 · OW2 4.242'. The three values are bold #F3F0E9.
- Ruler block:
  - Micro 'ONE FULL TURN AT YOUR SETTING (NOT TO SCALE)'.
  - Ruler: width 408 (= cm × 10), height 42, top border 2px #F3F0E9.
  - Five 1px ticks hanging down from the line, colour #9CA2AB, at 0/25/50/75/100% with heights 14/8/12/8/14.
  - Label '40.8 cm' in .unit style coloured #F3F0E9, placed 22px right of the ruler end, 12px above the line (right:-70 top:-12).

AIM DOWN SIGHTS CARD
- h2 'AIM DOWN SIGHTS'.
- Row 'ADS SCALING', sub-label 'How zoomed sensitivity is derived'. Seg: 'MATCH FOCAL LENGTH' (selected, 169w) | 'SAME CM/360' (116w) | 'CUSTOM' (80w).
- Row 'HOLO / RED DOT · 1.25×': slider 400 at 50% + field 70x36 '1.00'.
- Row '3× PRISM': slider 50% + field '1.00'.
- Row 'SNIPER 5–25×', sub-label 'Per zoom step, same feel at every step': slider 46% + field '0.92'.
- Row 'ADS INPUT': seg 'HOLD' (selected, 63w) | 'TOGGLE' (78w).
- Row 'INVERT Y': switch, off.

FIELD OF VIEW CARD
- h2 'FIELD OF VIEW'.
- Row 'HORIZONTAL FOV', sub-label 'Measured at 16:9. Ultrawide adds width (Hor+)' (wraps to 2 lines).
  - Big field 140x44 '103°'.
  - Unit '= 70.5° vertical · Valorant uses 103°'.
  - Slider 482 wide at 76.7% (fill 370px), ticks '80°' (0%) and '110°' (100%).
- Row 'VIEWMODEL FOV', sub-label 'Gun and hands only': slider 400 at 50% + field 70 '68°'.

CROSSHAIR CARD
- h2 'CROSSHAIR'. Right micro 'COPY / PASTE CODE: XH1-W-O1-I7.2.5'.
- Preview box 712x250, border 1px rgba(255,255,255,.16).
  - Background: hud_street.jpg, cover-fit with position centre 55%. Bevy has no cover mode, so use an ImageNode with source rect x0..1920, y223..897 of the 1920x1080 image stretched to 712x250.
  - The crosshair is centred (x1495 y504) and drawn at 1:1 px from the current settings. Default:
    - four arms in #F3F0E9
    - vertical arms 2x7 at y -12..-5 and +5..+12
    - horizontal arms 7x2 at x -12..-5 and +5..+12
    - each arm outlined 1px rgba(0,0,0,.85), i.e. Bevy Outline{width 1px, offset 0}
  - Overlay seg at the top-right (right 10, top 10), bg rgba(7,9,13,.85): 'STREET' (selected) | 'WHITE WALL' | 'SKY'.
- Row 'COLOUR': five swatches 30x30, gap 8, x from 1369: #F3F0E9 (selected), #B3EDFF, #F6FF52, #52E5A5, #FF4DF0.
  - Each swatch has a 2px transparent border. Selected: 2px #FFFFFF border plus a 2px #000000 Outline.
  - Then a hex field 69x30 '#F3F0E9': fd 700 14px, bg rgba(0,0,0,.35), padding 0 10. Note its border is 2px TRANSPARENT, because the swatch rule overrides .inp.
- Row 'OUTLINE · CENTRE DOT': two segs, gap 12: 'OUTLINE 1 PX' (selected) | 'OFF', and 'DOT' | 'NO DOT' (selected).
- Row 'LINES · LENGTH / GAP / WIDTH': three fields 56x36 '7', '5', '2' (gap 12), then unit 'px at 1080p'.
- Row 'HIT MARKERS': seg 'SHIELD + FLESH' (selected) | 'FLESH ONLY' | 'OFF'.

## data_bindings
SETTINGS: control type, range, default
- Mouse DPI: integer field, 100–32000, default 800.
- Turn distance:
  - big field with 1 decimal; typed values accepted 5.0–150.0
  - linear slider 15–80 cm, step 0.1
  - default 40.8 cm (= Valorant 0.400 at 800 DPI)
- Derived units:
  - inches = cm / 2.54 (1 decimal)
  - degrees per count = 360 / ((cm / 2.54) × DPI) (4 decimals)
- Feed the game: LocalControl.sensitivity (rad/count) = TAU × 2.54 / (cm × DPI). This replaces the hard-coded 0.0022 in client.rs. Note 0.0022 is about 9.1 cm/360 at 800 DPI, below the slider minimum.
- Import:
  - dropdown VALORANT (yaw 0.07) / CS2 / APEX (0.022) / OVERWATCH 2 (0.0066), default VALORANT
  - field = that game's sensitivity, 3 decimals, prefilled with the current equivalent
  - APPLY sets cm = 914.4 / (DPI × sens × yaw)
- 'Your value in other games' is live: sens = 914.4 / (DPI × yaw × cm).
- Ruler width = clamp(cm × 10, 150, 620) px; its label shows cm with 1 decimal.
- ADS scaling: seg, default MATCH FOCAL LENGTH.
  - MATCH FOCAL LENGTH: factor = tan(adsVFOV/2) / tan(hipVFOV/2), i.e. 1/zoom in focal terms.
  - SAME CM/360: factor = 1.
  - CUSTOM: factor = 1 and the per-optic value is the whole ADS/hip ratio.
  - The per-optic slider multiplies on top in every mode.
  - This replaces the hard-coded ads_scale 0.6 in client.rs gather_input.
- Per-optic multiplier: slider + field, 0.10–2.00, step 0.01 (the drawn fill implies a 0–2 track: 1.00 at 50%, 0.92 at 46%). Default 1.00; the mockup's 0.92 is a user-tuned value.
- ADS input: seg HOLD/TOGGLE, default HOLD (Buttons::ADS).
- Invert Y: switch, default off; negates the pitch delta.
- Horizontal FOV:
  - big field + slider 80–110°, step 1, default 103°
  - vertical = 2·atan(tan(h/2)·9/16), giving 70.5° at 103°
  - set PerspectiveProjection.fov (vertical) to that value; Bevy keeps vertical FOV fixed, so ultrawide gains width (Hor+)
  - replaces the hard-coded 78° vertical in render.rs (about 110° horizontal) and the 78° in hud.rs update_crosshair's focal length
- Viewmodel FOV: slider + field 54–82°, step 1, default 68° (50% fill implies centred on 68).
- Crosshair:
  - colour: preset swatch or hex, default #F3F0E9
  - outline: 1 px or off, default 1 px
  - centre dot: default NO DOT; dot size = line width
  - length: 0–20, default 7
  - gap: 0–20, default 5; this is the minimum gap, and the game's live spread gap (hud.rs) is added to it
  - width: 1–6, default 2
  - all in px at 1080p, scaled by UiScale
- Hit markers: seg, default SHIELD + FLESH. Maps to hud.rs HitKind Shield/Health/Kill:
  - FLESH ONLY hides Shield markers
  - OFF hides all markers except Kill
- Preview background: STREET / WHITE WALL / SKY, preview only, not saved, default STREET.
- Crosshair code, defined as XH1-<colour>-O<outline px>-I<length>.<width>.<gap>[-D when the dot is on]:
  - colour letters: W #F3F0E9, I #B3EDFF, Y #F6FF52, G #52E5A5, M #FF4DF0, or 6 hex digits for a custom colour
  - so 'XH1-W-O1-I7.2.5' = white, outline 1, length 7, width 2, gap 5

## interactions
- Number fields: click to edit (EditableText, digits and '.'). Enter or blur commits and clamps. Invalid input shows a --warn #FFA23A border and reverts on blur.
- Turn distance:
  - the slider and big field stay in sync
  - changing DPI keeps cm/360 constant (the physical feel) and recomputes rad/count
  - the unit line and the 'other games' values update live
- Import dropdown opens a 3-item list. APPLY sets turn distance and pulses the big field (border #F3F0E9 for 0.3 s; proposed).
- ADS rows: slider drag/click, or type in the field.
- Crosshair:
  - Swatches: click to select. Hover gives a 2px rgba(255,255,255,.32) border (proposed).
  - Hex field: typing a valid #RRGGBB selects 'custom', and no swatch is selected.
  - Clicking the micro code copies it. Bevy 0.19's clipboard is in-process only, so the OS clipboard needs the arboard crate. Proposed: clicking the code also turns it into a field where a code can be pasted and applied.
  - The preview redraws on every change.

## adaptations
1. Optic rows must come from our data, not the mockup list (assets/data/attachments.ron):
   - 'HOLO / RED DOT · 1.25×' covers optic_holo 1.25× and optic_reddot 1.15×
   - '3× PRISM' = optic_3x
   - add 'THERMAL 4×' for optic_thermal, which the mockup lacks
   - relabel 'SNIPER 5–25×' to 'SNIPER 6× / 12×' (optic_sniper zoom_levels [6, 12]), keeping the 'per zoom step' note
   Generate one row per optic id and save multipliers keyed by optic id. When the SMG lands with an optic or iron sights, the rows follow the data.
2. The game does not narrow the FOV on ADS yet (render.rs only moves the viewmodel). MATCH FOCAL LENGTH needs adsVFOV = 2·atan(tan(hipVFOV/2)/zoom). Implement that zoom, or the scaling has nothing to match.
3. Viewmodel FOV needs a second camera with RenderLayers for the gun and hands, since there is only one Camera3d today. Until that exists, show the row disabled at 68°.
4. Current defaults differ: client sens 0.0022 rad/count (about 9.1 cm/360 at 800 DPI) and 78° vertical FOV (about 110° horizontal). Switching to the mockup defaults (40.8 cm, 103°) is a noticeable change; tell the user.
5. The crosshair in hud.rs is dynamic (gap = 4 + spread). Keep that: settings set the colour, the arm length and width, and the base gap, and spread adds to the gap.
6. Only STREET has an image (hud_street.jpg). WHITE WALL = flat #DAD6CB (--ivory). SKY = a vertical gradient #9CC9F0 to #DCEEFB. Both are proposals.
7. Glyph: '→' in the formula note is missing from Barlow; use a symbol-font span or write '=' instead.
8. Copy shows 'Valorant' as the reference game. That is a factual sensitivity conversion, not a copied asset, so it is fine.

## assets
/home/user/sharline/design/ui/mockups/img/hud_street.jpg (preview background, cropped source rect y223..897). Icon i-chev (import dropdown). No other icons.

