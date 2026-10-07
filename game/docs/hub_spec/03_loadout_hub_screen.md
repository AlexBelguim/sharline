# Loadout (hub screen)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/05_loadout.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/loadout.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/widgets.js",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg",
 "/home/user/sharline/design/ui/mockups/loadout.html"
]

## purpose
A full-screen hub page where the player builds what they spawn with. It has three columns.
- Agent column.
- Weapon column: primary weapon, 6 attachment slots and, new, 6 ORDERED magazines each holding its own ammo type and tier.
- Halo column: core, a tier per arc and coverage.
The page also shows the derived results: weight class, shield, move speed, power drain, gear budget and what enemies can read.

It opens from four places: Main menu > Loadout, Lobby > LOADOUT button, ESC menu > Loadout (NEXT SPAWN), and Death recap > [L] CHANGE LOADOUT. In a match the game keeps running behind it and changes apply on the next spawn.

Keep the visual design exactly. Only the parts marked as adaptations change.

## layout
CANVAS
- Reference size 1920x1080. The root Node is full window.
- UiScale = window_height / 1080 (from the common.css header), so every px below is Val::Px at 1080p.
- Screen background: a BackgroundGradient RadialGradient.
  - Ellipse centred at (50%, 35%), which is page (960, 378).
  - Stops: #18202B at 0%, #0A0D12 at 55%, #06080B at 100% (farthest corner).
  - Fallback colour: --bg0 #07090D.
- Every region below is position:absolute on the root. Gutters between columns are 24px (408 to 432, and 1304 to 1328). Side margins are 48px.

REGION 1: TOP BAR (anchored top, full width)
- Box: left 0, right 0, top 0, height 84. Padding 0 48. Flex row, align-items centre, column gap 28. Transparent background.
- Bottom border: 1px --stroke rgba(255,255,255,.09), drawn at y = 83.
- Order left to right, with measured x ranges:
  - Title "LOADOUT": ink x 49-212.
  - Preset chips: x 246-667, y 23-61.
  - Flexible spacer (flex 1).
  - In-match warning text: x 1265-1566.
  - BACK button: x 1595-1727, y 20-64.
  - CONFIRM button: x 1755-1872, y 20-64. Its right edge is 1920 - 48.

REGION 2: AGENT COLUMN (anchored top-left)
- Box: left 48, top 108, width 360 (x 48-408). Vertical flow:
  - Header row: y 108-132, then margin 10.
  - Agent card 1: y 142-292.
  - Gap 10.
  - Agent card 2: y 302-452.
  - Gap 10. The card margin of 10 and the panel margin of 6 collapse to 10.
  - Abilities panel: y 462-702.
- Free space: y 702-1020, unused in the mockup.

REGION 3: WEAPON COLUMN (anchored top)
- Box: left 432, top 108, width 872 (x 432-1304).
- Mockup stack:
  - Weapon tabs: y 108-170.
  - Preview viewport: y 180-720 (540 tall).
  - Attachment slot row: y 730-806.
  - Stats panel: y 816-963.
- ADAPTED stack, which makes room for the new magazine strip without moving the stats panel or anything else on the page:
  - Tabs: y 108-170.
  - Preview: y 180-610 (430 tall).
  - Attachment slots: y 620-696.
  - Magazine label row: y 706-722.
  - Gap 8.
  - Magazine cards: y 730-806. Same grid as the attachment slots.
  - Stats panel: y 816-963, unchanged.

REGION 4: HALO COLUMN (anchored top and to the right margin)
- Box: left 1328, top 108, width 544 (x 1328-1872).
- Stack:
  - Header row: y 108-132.
  - Core cards: y 142-270.
  - Label "TIER": ink y ~290-300.
  - Tier row: y 311-357.
  - Label "COVERAGE · CLICK A ZONE": ink y ~377-387.
  - Coverage block: y 398-538. It holds the 140px halo widget plus a 2x2 grid of zone tiles at y 419-517.
  - RESULT panel: y 552-763.
  - Gap 12.
  - WHAT OTHERS SEE panel: y 775-893.
- ADAPTED: the RESULT panel grows by about 18px for the gear-budget legend line, to y 552-781. WHAT OTHERS SEE moves to y 793-911.

REGION 5: FOOTER HINTS (anchored bottom-left)
- Box: left 48, right 48, bottom 24. Flex row, align centre, gap 22.
- The keycaps are 22 tall, so the row sits at y 1034-1056.

OVERLAY
- The attachment list or ammo picker popover (see the second screen). It is drawn above everything with a GlobalZIndex.

MOCKUP-ONLY, DO NOT SHIP
- The "MOCKUP 05 · LOADOUT" label at right 12, bottom 8.
- The preview badge "LIVE 3D PREVIEW · VIEWPORTNODE".

## elements
Copy is shown between “ and ”; those marks are not part of the copy. BC = Barlow Condensed. ls = letter-spacing in px.

TOKENS (common.css)
- Backgrounds: --bg0 #07090D, --bg1 #0C1016.
- Panels: --panel rgba(9,12,17,.70), --panel-hi rgba(16,21,29,.82).
- Strokes: --stroke rgba(255,255,255,.09), --stroke-mid rgba(255,255,255,.16), --stroke-hi rgba(255,255,255,.32).
- Text: --text-hi #F3F0E9, --text #D7D4CD, --text-mid #9CA2AB, --text-low #646B75.
- Palette: --bone #C4BFB5, --sand #A29076, --ice #B3EDFF, --teal #00DACE, --coral #FF8C7A.
- Halo tiers: --t1 #EDF1F6, --t2 #59B3FF, --t3 #C46CFF, --t4 #FFCE50. Unlit arc: --unlit #27272C.
- Status: --warn #FFA23A, --good #52E5A5, --bad #FF4D5A.
- PANEL = bg --panel + 1px --stroke border + border radius 2. PANEL-HI = the same with bg --panel-hi.

FONTS
- Display: Barlow Condensed (--fd, fallback Arial Narrow), weights 500, 600 and 700.
- Body: Barlow (--fb), weight 400.

SHARED STYLES
Each is family, weight and size, then ls, colour and case.
- MICRO: BC 600 11px, ls 1.76, --text-low, UPPER.
- LBL: BC 600 13px, ls 1.82, --text-mid, UPPER.
- H2: BC 700 20px, ls 3.6, --text-hi.
- H2-SMALL: BC 700 17px, ls 3.06, --text-hi.
- HINT: BC 600 14px, ls 1.96, --text-mid. Children have a gap of 7.
- KEYCAP-GHOST:
  - Box: min-width 22, height 22, padding 0 6, border radius 2.
  - Fill and border: transparent fill, 1px --stroke-hi border.
  - Text: BC 700 13px, ls 0.52, --text-hi.
- BUTTON (.btn):
  - Box: height 44, padding 0 22, gap 10.
  - Text: BC 700 18px, ls 2.16, --text-hi, UPPER.
  - Fill and border: bg rgba(255,255,255,.06), 1px --stroke-mid border.
  - Hover: bg rgba(255,255,255,.12), border --stroke-hi.
  - Primary variant: bg --text-hi, text --bg0, border --text-hi. Hover bg #FFFFFF.
  - Disabled: opacity .35, no interaction.

TOP BAR
1. Title “LOADOUT”: BC 700 40px, ls 5.6, --text-hi.
2. Preset chips:
   - Flex row, gap 6. Each chip is height 38 with padding 0 14.
   - Text: BC 700 16px, ls 2.24, --text-mid. Border 1px --stroke-mid, no fill.
   - Copy and measured x ranges:
     - “A · RIFLE” at 246-345. This chip is ACTIVE.
     - “B · LONG” at 351-447.
     - “C · MEDIC” at 453-555.
     - “+ SAVE AS” at 561-667, with a DASHED 1px --stroke-mid border.
   - The dot is U+00B7 with a space on each side.
   - ACTIVE: bg --text-hi, text --bg0, border --text-hi.
   - Hover (derived from .btn): bg rgba(255,255,255,.12), border --stroke-hi.
3. Warning “In match: changes apply on your next spawn”:
   - HINT style but coloured --warn #FFA23A.
   - Sentence case. Do NOT uppercase it.
4. BACK: secondary BUTTON with the text “BACK”, then a KEYCAP-GHOST “ESC”.
   - The keycap is 20 tall here, not 22.
5. CONFIRM: primary BUTTON “CONFIRM”.

AGENT COLUMN
1. Header row:
   - Flex row, space-between, baseline aligned, margin-bottom 10.
   - H2 “AGENT” on the left. MICRO “1 OF 2” right-aligned (ends at x ~408).
2. Agent card (x2), each 360x150:
   - margin-bottom 10, children clipped (overflow hidden).
   - Border 1px --stroke-mid, bg --bg1 #0C1016.
   a) Portrait: ImageNode 200x200 (cover, centred), absolute at right -20, top -10. In card coordinates that is x 180-380, y -10 to 190, clipped by the card.
   b) Fade overlay over the whole card:
      - LinearGradient at 90deg (left to right).
      - #0C1016 fully opaque from 0 to 38% (137px).
      - Fades to rgba(12,16,22,0) at 75% (270px).
   c) Name block at left 18, top 18:
      - Name: BC 700 34px, ls 4.08, line-height 34. --text-hi when the card is selected, --text-mid otherwise.
      - Copy: “KESTREL” and “SOLACE”.
   d) Role line, margin-top 2:
      - BC 600 13px, ls 2.6, UPPER.
      - Copy: “RECON · MOBILITY” for Kestrel, “MEDIC · SUPPORT” for Solace.
      - Colour: the agent's accent. Kestrel is --teal #00DACE (class c-teal); Solace is --coral #FF8C7A (class c-coral).
      - The PNG shows both in #FF4D5A. That comes from a CSS collision: loadout.html line 81 has .r{color:var(--bad)}, which overrides the accent classes. Use the accent colours; red is the enemy colour.
   e) Ability icon strip at left 18, bottom 16 (card y 100-134):
      - 3 boxes of 34x34, gap 6, bg rgba(0,0,0,.5), border 1px --stroke-mid.
      - Each holds a 22x22 icon tinted --text-hi, centred.
      - Kestrel icons: i-grapple, i-scan, i-kes-ult. Solace icons: i-drone, i-pulse, i-sol-ult.
   f) SELECTED state:
      - Border 2px --teal. The box stays 150 tall (border-box).
      - BoxShadow: rgba(0,218,206,.18), offset 0, spread 0, blur 24.
      - Tag “SELECTED” at right 10, top 10: BC 700 11px, ls 2.2, text --bg0 on --teal, padding 2 7. About 70x19; page x 326-396 on card 1.
   g) Hover on an unselected card (derived): border --stroke-hi.
3. Abilities panel (PANEL):
   - y 462-702, padding 14 16.
   - 3 rows. Each row is a grid of 40px | 1fr with gap 10 and padding 8 0.
   - A 1px --stroke divider sits under every row except the last (dividers at y 547 and 618).
   - Icon box: 40x40, border 1px --stroke-mid, with a 26x26 icon tinted --text-hi.
   - Title: BC 700 16px, ls 1.6, --text-hi. Then a space and a MICRO meta.
   - Description: Barlow 400 12.5px, line-height 1.35 (about 17px), --text-mid, margin-top 1. It wraps inside 278px.
   - Kestrel copy:
     - “Q · GRAPPLE LINE” + “2 CHARGES” / “Fire a line up to 25 m and reel in. Hooks onto any ledge or zipline cable.”
     - “E · EYEPIECE SCAN” + “35 S” / “40 m cone. Marks enemies for 4 s and reveals their halo: core, tier, coverage, shield, power.”
     - “X · WIDE SWEEP” + “7 POINTS” / “Placeholder ultimate: 3 scan pulses across the whole map.”
   - Text ink rows: y 490-538, 561-609 and 632-679.

WEAPON COLUMN
1. Weapon tabs:
   - Flex row, gap 6. Each tab is 433x62: x 432-865 and 871-1304, y 108-170.
   - Padding 0 16, gap 14, align centre. Border 1px --stroke-mid, bg rgba(255,255,255,.03).
   - Silhouette: ImageNode tinted --bone #C4BFB5.
     - Mako: 130x35 (i-mako). Warden: 150x35 (i-warden).
     - The inactive tab's silhouette is at 60% alpha.
   - Name: BC 700 22px, ls 1.76, --text-mid.
   - Subtitle on its own line: BC 600 12px, ls 2.16, --text-low.
   - Copy:
     - “AR-7 MAKO” / “ASSAULT RIFLE · AUTO / SEMI”. This tab is active.
     - “VK-50 WARDEN” / “HEAVY BOLT-ACTION”.
   - ACTIVE: border --text-hi, bg rgba(255,255,255,.07), name --text-hi.
   - Hover (derived): border --stroke-hi, bg rgba(255,255,255,.06).
2. Preview viewport:
   - x 432-1304; y 180-720 in the mockup, 180-610 adapted.
   - Border 1px --stroke, bg #090B0E, children clipped.
   a) Content: a live 3D ViewportNode of the weapon with its current parts.
      - Placeholder in the mockup: img/mako_dark.jpg drawn at 960x540, left -40, top 0.
   b) Floor fade:
      - Bottom 0, full width, height 120.
      - LinearGradient from the bottom up: rgba(9,11,14,.9) to rgba(9,11,14,0).
   c) Control hints at left 14, bottom 12:
      - Flex row, gap 16. Each hint is a KEYCAP-GHOST followed by a label (gap 6).
      - Label style: BC 600 12.5px, ls 1.75, --text-mid.
      - Copy: [LMB] “DRAG TO ROTATE”, [WHEEL] “ZOOM”, [F] “SHOW ON AGENT + HALO”.
   d) Attachment hotspots, one per slot:
      - Dot: 14x14, border radius 50%, border 2px --text-hi, fill rgba(0,0,0,.4).
      - Tag: padding 3 8, bg rgba(7,9,13,.85), border 1px --stroke-mid.
      - Tag text: a slot prefix in BC 600 13px --text-mid with margin-right 6, then the value in BC 700 13px, ls 1.56, --text-hi.
      - The gap between dot and tag is 8 side by side, or 6 when stacked.
      - Mockup dot positions are relative to the preview's inner top-left, which is page (433,181). Each entry is prefix, value, position, tag side:
        - OPTIC “HOLO” at (532,134), tag on the right.
        - STOCK “STANDARD” at (620,200), tag on the left.
        - MAG “30-RND” at (502,410), tag on the right.
        - UNDER “ANGLED GRIP” at (112,393), tag on the left. This one is SELECTED.
        - SIDE R “LASER” at (171,343), tag below.
        - SHIELD “NONE” at (61,330), tag above.
      - SELECTED:
        - The dot's fill and border become --teal.
        - A 5px ring in rgba(0,218,206,.25) goes around the dot: an Outline (width 5, offset 0) or a BoxShadow (spread 5, blur 0).
        - The tag border becomes --teal.
      - Hover (derived): dot fill --text-hi.
3. Attachment slot row:
   - Grid of 6 equal columns with gap 6, so each card is 140.33x76.
   - Column x positions: 432, 578.3, 724.7, 871, 1017.3, 1163.7.
   - y 730-806 in the mockup, 620-696 adapted.
   - Card: padding 9 10, border 1px --stroke-mid, bg rgba(255,255,255,.03).
   - Header row: a 16x16 icon + label, gap 6. BC 600 12px, ls 1.92, --text-mid.
   - Value: BC 700 17px, ls 0.68, --text-hi, margin-top 6, line-height 18. Single line with an ellipsis.
   - States:
     - OPEN/SELECTED: border --teal, bg rgba(0,218,206,.08), header text and icon --teal.
     - EMPTY (value NONE): value in --text-low.
     - HOVER (derived): border --stroke-hi, bg rgba(255,255,255,.06).
     - NO COMPATIBLE PARTS (derived): whole card at opacity .35, not clickable.
   - Copy, in this order:
     1. OPTIC “HOLO” (i-optic)
     2. STOCK “STANDARD” (i-stock)
     3. MAG “30-RND STANAG” (i-magslot)
     4. UNDER “ANGLED GRIP” (i-under). This slot is OPEN.
     5. SIDE “LASER (R)” (i-side)
     6. SHIELD “NONE” (i-gunshield). This slot is EMPTY.
4. NEW: the magazine strip. Its full spec is under adaptations A1 (y 706-806).
5. Stats panel (PANEL):
   - x 432-1304, y 816-963, padding 14 16.
   - Grid of 2 columns with column gap 28 and row gap 9. Each column is 405 wide: x 449-854 and x 882-1287.
   - Each stat row is a grid of 96 | 1fr (=225) | 64, gap 10, align centre. For example, the ADS bar sits at x 555-780.
   - Key: BC 600 12.5px, ls 1.75, --text-mid, UPPER.
   - Bar:
     - Height 6, track rgba(255,255,255,.10), fill --text-hi from the left.
     - Delta segment: an improvement is a --good #52E5A5 segment appended right after the fill. A worsening is a --bad #FF4D5A segment covering the last part of the fill.
   - Value: BC 700 15px, tabular figures, --text-hi, right-aligned. An optional inline delta follows after a space, in --good or --bad.
     - The 64px value column is narrow, so “0.20 s −0.02” wraps onto 2 lines in the mockup. Match that, or widen the column to 84.
   - Mockup rows, row by row (left stat | right stat):
     - ADS TIME (fill 66% + green 4%) “0.20 s” with “−0.02” | FIRE RATE (72%) “750 rpm”
     - RECOIL V (52% + green 3%) “42” with “−4 %” | RECOIL H (38%) “18”
     - HANDLING (64%) “64” | RELOAD (58%) “2.3 s”
     - EFF. RANGE (45%) “40 m” | MAG SIZE (40%) “30”
   - Units stay lower case.
   - Text ink rows: y ~840/858 (the ADS row wraps), 885, 912 and 939.

HALO COLUMN
1. Header: H2 “HALO ARMOR”, with MICRO “ANY AGENT CAN WEAR IT” right-aligned.
2. Core cards:
   - Grid of 4 columns, gap 6. Each card is 131.5x128; x 1328, 1465.5, 1603, 1740.5; y 142-270.
   - Flex column, centred, gap 2. Border 1px --stroke-mid, bg rgba(255,255,255,.03).
   - Children:
     - A 62x62 halo icon: all four arcs lit in the tier colour, Light weight so no band ring, 1 power cell, no centre text, tiny zone letters H/T/A/L.
     - Name: BC 700 15px, ls 2.1, --text-mid.
     - Description: BC 500 11px, ls 0.66, --text-low, UPPER. Centred, line-height 1.25, padding 0 6.
   - SELECTED: border --t2 #59B3FF, bg rgba(89,179,255,.08), name --text-hi.
   - Hover (derived): border --stroke-hi.
   - Copy:
     - BULWARK “MOST SHIELD, SLOW REGEN”
     - MENDER “REGENS OUT OF COMBAT”. This card is SELECTED.
     - VOLT “BREAK = SHOCK PULSE”
     - PHASE “LIGHT, RESISTS SLOW/BLEED”. This wraps to 2 lines, which lifts its name about 6px.
3. Tier section (margin-top 14):
   - LBL “TIER”, then the row with margin-top 8.
   - Grid of 4 boxes, 131.5x46 each, gap 6, at y 311-357.
   - Each box: centred flex, gap 8, border 1px --stroke-mid, no fill.
   - Text: BC 700 18px, ls 1.8, in the TIER COLOUR.
   - Diamond: a 14x14 square rotated 45deg with UiTransform, filled with the tier colour, plus a glow (BoxShadow in the tier colour, blur 10).
   - SELECTED: border 2px in the tier colour, bg tier colour at 8%. The mockup uses rgba(89,179,255,.08) for T2.
   - Copy:
     - “T1”: #EDF1F6
     - “T2”: #59B3FF. This box is SELECTED.
     - “T3”: #C46CFF
     - “T4”: #FFCE50
4. Coverage section (margin-top 14):
   - LBL “COVERAGE · CLICK A ZONE”.
   - Block: margin-top 8, grid of 150 | 1fr, gap 16, align centre, y 398-538.
   a) Halo widget, 140x140, centred in the 150px column (x 1333-1473):
      - Mockup state: T2, Mender core, arcs head/torso/arms lit, Medium band ring, 2 cells.
      - Centre: “120” in BC 700 about 24.5px --text-hi. Under it, “T2 MENDER” in BC 600 about 9.3px, ls about 1.4, tier colour.
      - Geometry, from widgets.js haloSVG with viewBox 120 scaled by size/120:
        - Arc radius 34. Each arc spans ±39deg around its angle: head -90 (top), legs 0 (right), torso 90 (bottom), arms 180 (left).
        - Stroke width per core: Bulwark 8 (hexagonal outline), Mender 4 plus an inner 2.4 arc at radius 27, Volt 6 plus 3 outward ticks per arc, Phase 5 with the torso arc split by a 16deg gap.
        - Lit arc: tier colour at 85%, with a glow behind it (width +3, 35% opacity, 2px blur).
        - Unlit arc: #27272C plus a 1px white hairline at 13%.
        - Weight band ring:
          - Medium: r 45, stroke 3, #3A3F47, plus a 1px line in the tier colour at 25%.
          - Heavy: r 46, stroke 7, dashed 14/3, #3A3F47, plus a 1px line in the tier colour at 30%.
        - Power cells: pills of 6x10 (radius 3) on r 53. The first is at -60deg, spaced 360/n. Tier colour at 95%. They orbit at 10 s per turn, or 14 s with 3 cells.
   b) Zone tiles:
      - 2x2 grid, gap 6. Each tile is 186x46: x 1494-1680 and 1686-1872, y 419-465 and 471-517.
      - Flex row, centred, gap 10, padding 0 12. Border 1px --stroke-mid.
      - Text: BC 700 16px, ls 2.24, --text-mid.
      - An 18x18 zone icon on the left. An 18x18 checkbox pushed to the right (margin-left auto) with a 2px --stroke-hi border.
      - COVERED: text --text-hi, border rgba(89,179,255,.6), bg rgba(89,179,255,.08). The checkbox fill and border become --t2.
      - Copy:
        - “HEAD” (i-head): covered
        - “TORSO” (i-torso): covered
        - “ARMS” (i-arms): covered
        - “LEGS” (i-legs): not covered
5. RESULT panel:
   - PANEL with a 2px --text-hi top border (y 552-553). y 552-763, padding 16 18, inner width 506 (x 1347-1853).
   a) Header: H2-SMALL “RESULT”, with MICRO “T2 × 3 ZONES + MENDER = 6 PTS” on the right.
   b) Weight class display (read-only):
      - margin-top 8. Flex row, gap 4. Three boxes of 166x36: x 1347-1513, 1517-1683, 1687-1853; y ~599-635.
      - Box: bg rgba(255,255,255,.05). Text: BC 700 15px, ls 2.4, --text-low.
      - ACTIVE: bg --text-hi, text --bg0.
      - Copy: “LIGHT ≤ 4”, “MEDIUM 5–8” (ACTIVE), “HEAVY ≥ 9”.
   c) Result figures:
      - margin-top 14. Grid of 3 columns, 162 wide each, gap 10.
      - Each column:
        - An LBL caption.
        - The value: BC 700 26px, line-height 28, --text-hi. A unit, if any, is BC 600 14px --text-mid.
        - A sub-line: Barlow 400 12px, --text-mid.
      - Copy:
        - “SHIELD” / “120” / “regen 4/s after 5 s”
        - “MOVE SPEED” / “−5 %” / “sprint 6.5 m/s (base 6.8)”
        - “POWER DRAIN” / “2” with unit “cells” / “energy −3.0/min · food −1.5/min”
   d) Gear budget row:
      - margin-top 14. Flex row, centred, gap 10. y ~731-745.
      - LBL “GEAR BUDGET”.
      - Bar: flex 1, height 8, track rgba(255,255,255,.10), fill --text-hi. The mockup fill is 70%, measured at x 1438-1717.
      - Value “14 / 20”: BC 700 16px, tabular figures, --text-hi.
      - MICRO “HOST OPTION”.
6. WHAT OTHERS SEE panel:
   - PANEL with margin-top 12, padding 14 18.
   - Header (margin-bottom 6): H2-SMALL “WHAT OTHERS SEE”, with MICRO “READABILITY LAYERS” on the right.
   - Grid of 86 | 1fr, row gap 7.
     - Left column: LBL at 12px (ls 1.68).
     - Right column: Barlow 400 13px, --text #D7D4CD.
   - Rows:
     - “ALWAYS”: “MEDIUM halo (size, band, 2 cells) in dimmed blue”
     - “ON HIT”: “Lit arcs: Head, Torso, Arms · blue hex shards · cracks”
     - “ON SCAN”: “Everything: Mender, 72/120, 2 cells, status effect”

FOOTER
- HINT groups with a gap of 22. KEYCAP-GHOST 22x22, with a gap of 7 between keycaps and to the text.
  - [Q][E] “SWITCH COLUMN”: Q at x 48-70, E at 77-99, text at 106-210.
  - [1][2][3] “PRESET”: x 234-368.
  - [R] “RESET SLOT”: x 392-497.

## data_bindings
TOP BAR
- Preset chips:
  - Source: the player's saved loadout presets. Store them client-side, for example a loadouts.ron in the user config dir. They are not gameplay data.
  - Label format: “{A|B|C} · {NAME}”, with NAME uppercased and at most 8 characters.
  - If no presets are saved yet, generate three:
    - A · RIFLE = rules.ron default_loadout.
    - B · LONG = vk50_warden with its default_for attachments.
    - C · MEDIC = Mako + the arm_mender_medic tiers.
  - ACTIVE = the preset the current edit was loaded from.
- Warning text:
  - Visible only when the screen was opened during a match. The host applies LoadoutChoice at the next spawn (vetf_net protocol.rs).
  - Hidden when opened from the main menu.
  - When over budget it is replaced by “Over gear budget: {used} / {budget} pts” in --bad.
- CONFIRM enabled only when all of these hold:
  - gear used ≤ budget;
  - MAG 1 holds ammo;
  - every arc ≤ loadout_tier_caps;
  - every ammo is legal for the weapon class.

AGENT COLUMN
- The game has no agents yet. Bind to a new data file, game/assets/data/agents.ron, with these fields:
  - id, name, role, accent (teal | coral);
  - portrait (image path);
  - abilities: a list of (key, name, meta, text, icon).
- Seed it with the Kestrel and Solace copy above.
- “1 OF 2” = the selected agent's index / the agent count.
- Abilities are not implemented: see adaptation A5.
- LoadoutChoice gains agent: String, cosmetic for now.

WEAPON TABS
- Source: weapons.ron weapons[].
- Name: name uppercased, for example “AR-7 MAKO”.
- Subtitle = class label + fire modes:
  - Class labels: assault_rifle “ASSAULT RIFLE”, bolt_sniper “HEAVY BOLT-ACTION”, smg “SMG”.
  - Fire modes: if there is more than one, append “ · ” + the modes joined with “ / ”, for example [auto, semi] gives “ · AUTO / SEMI”. A bolt-only gun appends nothing.
  - Put these labels in a UI strings data table, not in code.

PREVIEW
- Content: the weapon model with the equipped parts.
- Hotspot positions: the weapon's *_SOCKET_* nodes (art/WEAPON_MODULAR_SPEC.md), projected into the viewport every frame.
- Hotspot tag: the slot name + the equipped part's short name, or “NONE”.

ATTACHMENT SLOT CARDS
- Fixed order: OPTIC, STOCK, MAG, UNDER, SIDE, SHIELD. This matches the attachments.ron categories optic, stock, mag, under, side, shield.
- Value: the display name of the equipped part. This needs a new name field in attachments.ron. Suggested names:
  - Optics: optic_holo “HOLO”, optic_reddot “RED DOT”, optic_3x “3× SCOPE”, optic_sniper “6/12× SCOPE”, optic_thermal “THERMAL”.
  - Stocks: mako_stock_standard “STANDARD”, mako_stock_precision “PRECISION”, mako_stock_light “LIGHT”, warden_stock_standard “STANDARD”, warden_stock_folding “FOLDING”.
  - Mags: mag_30 “30-RND STANAG” (short name “30-RND”), mag_45 “45-RND”, mag_drum60 “60-RND DRUM”, mag_5 “5-RND”, mag_8 “8-RND”.
  - Under: grip_vertical “VERTICAL GRIP”, grip_angled “ANGLED GRIP”, grip_stub “STUB GRIP”, ugl_launcher “UGL-40 LAUNCHER”, bipod “BIPOD”.
  - Side: laser “LASER”, flashlight “FLASHLIGHT”.
  - Shield: shield_front “FRONT SHIELD”.
- An empty optional slot shows “NONE” in --text-low.
- A slot with no part that fits the weapon is disabled and shows “—”. Example: SHIELD on the Warden.

STATS PANEL
Computed for the current weapon + ModifierTotals.
- ADS TIME = ads_s × ads_time multiplier, shown as “0.22 s” for a stock Mako. Mockup values are illustrative.
- FIRE RATE = rpm, shown as “720 rpm”. Attachments do not change it.
- RECOIL V and RECOIL H = 100 × the recoil_v / recoil_h multiplier, as an index (100 = the stock pattern). The data has no absolute recoil score.
- HANDLING has no data. Replace it with MOBILITY = 100 × move_mult_held × the move multiplier, shown as “100 %”.
- RELOAD = reload_tactical_s × the reload multiplier, shown as “2.1 s”.
- EFF. RANGE = the largest falloff distance that still deals full damage: Mako “25 m”, Warden “60 m”.
- MAG SIZE = the equipped mag's capacity, shown as “30”. This is a spec value, not a live count, so it is allowed.
- Bar fill = normalised “goodness” over a per-stat range kept in data, for example a new stat_bars table in game/assets/data/ui.ron. Suggested ranges (worst to best):
  - ADS: 0.60 to 0.10 s
  - RPM: 0 to 1000
  - Recoil index: 150 to 50
  - Mobility: 85 to 105 %
  - Reload: 4.0 to 1.0 s
  - Range: 0 to 100 m
  - Mag: 0 to 60
- Deltas:
  - When a slot is open: the equipped part's contribution compared with NONE or the default part. This is the mockup state.
  - While hovering a list row: the hovered part compared with the equipped part.
  - When no slot is open: no deltas.

HALO
- Core cards:
  - Source: armor.ron cores. Display order: BULWARK, MENDER, VOLT, PHASE.
  - Descriptions come from a new per-core blurb field in data. Copy that matches the game:
    - BULWARK “MOST SHIELD, SLOW REGEN” (capacity 65-165, regen 10/s after 5 s).
    - MENDER “REGENS OUT OF COMBAT” (20/s after 2.5 s).
    - VOLT “BREAK = SHOCK PULSE”.
    - PHASE “IMMUNE TO SLOW”. In the data, Phase is immune to slow effects but has no bleed resistance, so the mockup's copy is wrong.
- Tier row and zone tiles: one tier per arc, with caps from loadout_tier_caps (head 4, torso 4, arms 3, legs 2). See adaptation A3.
- Halo widget: draws the resolved ArmorStats.
  - Each arc uses its own tier colour.
  - Centre value = ArmorStats.capacity = Σ capacity[core][tier−1] × zone_capacity_share. Example: Mender T2 on head + torso + arms = 36 + 60 + 36 = 132 (the mockup shows 120).
  - Band ring = weight_class. Number of cells = power_cells.
- RESULT header micro: the protection score (Σ arc tiers). See A2.
- Weight class boxes:
  - Bands come from armor.ron weight_bands: Light 1-4, Medium 5-8, Heavy 9-16.
  - Labels: “LIGHT ≤ 4”, “MEDIUM 5–8”, “HEAVY ≥ 9”.
  - Score 0 (WeightClass::None): no box is highlighted.
- SHIELD:
  - Value: capacity.
  - Sub-line: “regen {regen_per_s}/s after {regen_delay_s} s”, for example Mender gives “regen 20/s after 2.5 s”.
  - No halo: “0” / “no shield”.
- MOVE SPEED:
  - Value: weight_effects[wc].move − 1, as a signed percent: Medium “−5 %”, Heavy “−12 %”, Light/None “0 %”.
  - Sub-line: “sprint {7.0 × move:.1} m/s (base 7.0)”, using movement.ron speed.sprint = 7.0.
- POWER DRAIN:
  - Value: power_cells, with the unit “cells”.
  - Sub-line: “energy −{energy_per_min:.1}/min”. Medium is 4.0.
  - The game has no food stat, so drop “· food …” until survival stats exist.
- Gear budget:
  - Budget: rules.ron tdm.gear_budget (12 today; the mockup shows 20).
  - Used: halo gear_cost (Σ arc tiers) + ammo gear cost (see A1 and A2).
  - “HOST OPTION” stays, because the host's match settings set the budget.
- WHAT OTHERS SEE: generated text.
  - ALWAYS: “{WEIGHT} halo (size, band, {cells} cells) in dimmed {colour}”.
    - Colour names: T1 white, T2 blue, T3 purple, T4 gold.
    - With mixed tiers: “in dimmed tier colours”.
  - ON HIT: “Lit arcs: {covered zones, Title Case, comma list} · {colour} hex shards · cracks”. With mixed tiers: “hex shards in tier colours”.
  - ON SCAN: “Everything: {Core}, {capacity}/{capacity}, {cells} cells, status effect”.
  - No halo: ALWAYS “No halo: nothing to read”, ON HIT “Hits go straight to health”, ON SCAN “No halo”.

MAGAZINE STRIP
- See A1.

## interactions
NAVIGATION
- Opens from:
  - Main menu nav “Loadout”
  - Lobby button “LOADOUT”
  - ESC menu “Loadout · NEXT SPAWN”
  - Death recap “[L] CHANGE LOADOUT”
- In a match the game keeps running and the cursor is released while this screen is open.
- BACK button or Esc:
  - Returns to whichever screen opened this one and discards unconfirmed edits.
  - If a popover is open, Esc closes the popover first.
- CONFIRM:
  - Validates the build (see data bindings) and saves it into the active preset.
  - If connected, sends LoadoutChoice to the host, which applies it on the next spawn.
  - Returns to the screen that opened this one.
  - Disabled (opacity .35) while the build is invalid.

TOP BAR
- Load a preset: click its chip or press 1, 2 or 3. This replaces the current edit.
- “+ SAVE AS”:
  - The chip turns into an EditableText (placeholder “NAME”, forced uppercase, max 8 characters).
  - Enter saves the build to the first free letter, or overwrites the active letter if A-C are all used.
  - Esc cancels.

AGENT
- Click a card to select that agent:
  - The SELECTED tag and the teal border move to it.
  - The name colours swap (--text-hi for the selected card, --text-mid for the other).
  - The ability panel shows the selected agent's abilities.

WEAPON
- Click a tab to switch the primary weapon:
  - Attachments load that weapon's last-used set, or its default_for parts.
  - The preview swaps model.
  - Mags holding ammo the new gun cannot load (RIP on a non-SMG, SLUG on a non-shotgun) fall back to STANDARD with a 1 s --warn border flash.
- Preview controls:
  - LMB drag rotates: yaw is free, pitch is clamped to about ±25deg.
  - Wheel zooms, clamped.
  - F toggles SHOW ON AGENT + HALO. The camera frames the selected agent holding the gun and wearing the current halo. While on, the F label is --text-hi.
- Hotspot click: does the same as clicking that slot's card.
- Attachment slot card:
  - Click opens that slot's attachment list (see the second screen). The card and its hotspot take the teal SELECTED style.
  - Clicking the open card again, or clicking outside the popover, closes it.
  - R resets the focused slot to the weapon's default part.
- Magazine cards: see A1.

HALO
- Click a core card to set the core.
- Click a zone tile to select that arc for tier editing. Click the tile's checkbox to toggle the arc on or off.
- Click a tier to set the selected arc to it. Shift+click a tier to set every covered arc, each clamped to its cap.
- Tiers above the selected arc's cap are disabled.
- Read-only parts: Stats, RESULT (including the weight-class boxes) and WHAT OTHERS SEE. They update live on every edit and on hover previews.

KEYBOARD AND GAMEPAD
- Q and E move focus between columns: Agent ↔ Weapon ↔ Halo.
- Arrow keys move within a column. In the weapon column the order is tabs → slots → mags.
- Enter or gamepad A activates.
- 1, 2, 3 load presets. R resets the focused slot.
- Focus ring: an Outline of 2px --teal with offset 2. It is not in the mockup but keyboard use needs it.
- The footer hints are labels only, not buttons.
- Hover transitions: the mockup has none, so state changes are instant.

## adaptations
A1. SIX-SLOT ORDERED MAGAZINE STRIP (new, weapon column)

Geometry
- The preview shrinks from 540 to 430 (y 180-610) and the attachment slots move up to y 620-696.
- New label row: y 706-722.
- Mag cards: y 730-806, on exactly the same 6-column grid as the attachment slots. Columns are 140.33 wide with gap 6, at x 432, 578.3, 724.7, 871, 1017.3 and 1163.7.
- Stats stay at y 816-963. Nothing else on the page moves.

Label row
- Flex, space-between, baseline aligned.
- Left: LBL “MAGAZINES · LOAD ORDER”.
- Right: MICRO “SLOT = RELOAD WHEEL POSITION · AMMO {n} PTS”. The “{n} PTS” part is --text-hi when n > 0.

Card base
- Same as an attachment slot card: padding 9 10, 1px --stroke-mid border, bg rgba(255,255,255,.03).

Card content
1. Header row: BC 600 12px, ls 1.92, --text-mid, gap 6.
   - A reload-wheel glyph, 16x16: six ring sectors, each 50deg wide with 10deg gaps. This slot's sector is filled --text-hi; the others are rgba(255,255,255,.18). Slot 1 is at 12 o'clock and the rest follow clockwise. This replaces the category icon an attachment card has.
   - Then “MAG {n}”.
   - Slot 1 adds a right-aligned tag “IN GUN”: BC 700 10px, ls 1.6, --bg0 on --text-hi, padding 1 5. It is styled like the SELECTED tag.
2. Value row: margin-top 6, line-height 18.
   - Ammo name: BC 700 17px, ls 0.68, in the AMMO COLOUR. Names: “STANDARD”, “AP I/II/III”, “RIP I/II/III”, “SLUG I/II”. Each is the ammo.ron type label + a roman numeral tier.
   - 6px after the name: up to 3 tier pips. Each pip is a 5x10 parallelogram skewed −14deg, gap 3. Filled pips use the ammo colour; empty pips use rgba(255,255,255,.12). STANDARD has no pips.
   - Cost, pushed to the right edge: “{cost} PTS” in BC 600 11px, ls 1.76, --text-mid. Hidden when the cost is 0.
3. Effect line: margin-top 4, MICRO in --text-mid.
   - AP: “SHIELD ×{pen_mult}”, which gives ×1.30, ×1.60 and ×2.00.
   - RIP: “FLESH +{flesh−1}%”, which gives +12, +20 and +28 %.
   - SLUG: “DAMAGE ×{damage_mult}”.
   - STANDARD: “BASELINE”.

Ammo colours
- New tokens. They can't clash with the halo tier colours, which only appear in the halo column.
  - STANDARD: --bone #C4BFB5
  - AP: --ice #B3EDFF
  - RIP: --coral #FF8C7A
  - SLUG: --sand #A29076

States
- HOVER: border --stroke-hi, bg rgba(255,255,255,.06).
- OPEN (the ammo picker is showing for this card): identical to an open attachment slot. Border --teal, bg rgba(0,218,206,.08), header text and glyph --teal.
- EMPTY (slots 2-6 only):
  - Dashed 1px --stroke-mid border.
  - Header in --text-low.
  - Value “+ ADD MAG” in BC 700 17px --text-low.
  - No effect line.
- DRAGGING: the card follows the cursor at 90% opacity with a BoxShadow (offset 0,8, blur 24, rgba(0,0,0,.5)). The drop target gets a 2px --teal border.
- INVALID AFTER A WEAPON SWITCH: a 1 s --warn border flash, then the card shows STANDARD.

Default content
- rules.ron default_loadout has 1 mag in the gun + spare_mags 3, so the default is four STANDARD mags:
  - MAG 1 [IN GUN] “STANDARD” / “BASELINE”
  - MAG 2, MAG 3, MAG 4: “STANDARD”
  - MAG 5 and MAG 6: “+ ADD MAG”
- Example of a high-end mag: MAG 1 “AP II”, pips ▮▮▯, “4 PTS”, effect line “SHIELD ×1.60”.

Interactions
- Click a card: opens the ammo picker (the second screen's variant).
- Drag a card with LMB onto another: swaps their ammo. The slot numbers stay with the positions.
- Right-click MAG 2-6: empties that slot.
- R on a focused mag: resets it to STANDARD.
- Shift+← or Shift+→ on a focused card: moves it one slot.
- MAG 1 can never be empty.
- Gaps are allowed. A gap shows as an empty sector on the reload wheel.
- Add a footer hint after “RESET SLOT”: [LMB] “DRAG TO REORDER MAGS”.
- The glyph layout (slot 1 at the top, then clockwise) must match the in-match reload radial, so that the loadout teaches the radial positions.

No ammo counters
- Show no round count on any card and add no “total rounds” readout. Capacity stays only in the MAG attachment slot and the MAG SIZE stat.

Data
- In LoadoutChoice, replace ammo: AmmoChoice and spare_mags with mags: [Option<AmmoChoice>; 6]. Index 0 is required. Put the maximum count in data, for example max_mags: 6 in rules.ron.
- Add a serialization test for the new shape.

Open design questions (the numbers belong to design/)
1. Per-mag ammo cost. The UI assumes cost is per mag: the sum of each mag's tier gear_cost. With a budget of 12 that allows, for example, 2× AP II next to a 4-point halo. If cost stays per ammo type instead, show the cost once per distinct ammo.
2. Whether carrying more mags should cost budget or weight.

A2. GEAR BUDGET READOUT (whole loadout)

Placement
- Keep the row where the mockup has it, at the bottom of RESULT, but it now covers the whole loadout.

Bar
- Two stacked segments with a 2px gap: halo points in --text-hi, then ammo points in rgba(243,240,233,.55).
- Track rgba(255,255,255,.10). Total fill = used / budget.

Value
- “{used} / {budget}”, for example “10 / 12”. MICRO “HOST OPTION” stays.

New legend line under the row
- margin-top 6, flex row, gap 14, MICRO style.
- An 8x8 --text-hi swatch + “HALO {h} PTS”, then an 8x8 swatch at 55% + “AMMO {a} PTS”.
- This adds about 18px, so RESULT spans y 552-781 and WHAT OTHERS SEE moves to y 793-911.

RESULT header micro
- Uniform tiers: “T2 × 3 ZONES = 6 PTS”.
- Mixed tiers: “H2 · T3 · A1 · L0 = 6 PTS”.
- Cores cost nothing in the game, so drop “+ MENDER”.
- No halo: “NO HALO · 0 PTS”.

Over budget
- Bar fill and value turn --bad.
- The legend becomes “OVER BY {x} PTS: LOWER AN ARC TIER OR A MAG'S AMMO” in --bad.
- CONFIRM is disabled.
- The top-bar warning changes as described in data bindings.

Modes without a budget
- Gun range: hide the bar, show “NO LIMIT” in --text-mid with the micro “GUN RANGE”.
- Main menu with no lobby: use the TDM budget with the micro “TDM DEFAULT”.

Ammo subtotal
- The ammo subtotal also appears in the magazine label row, where the points are spent.

A3. TIER PER ARC (the game differs from the mockup)

The mockup has one TIER plus coverage on/off. In the game each arc has its own tier from 0 to 4, capped at head 4, torso 4, arms 3, legs 2. Keep the same widgets and change what they mean:

- Zone tiles:
  - Clicking a tile selects the arc that the TIER row edits. The selected tile gets an Outline of 2px --teal. Default selection: TORSO.
  - The TIER label reads “TIER · TORSO”.
- Covered tile styling:
  - Each tile uses its own arc's tier colour: border at 60%, bg tint at 8%, filled checkbox in the tier colour.
  - A “T2” in BC 700 13px, in the tier colour, sits just left of the checkbox.
  - An uncovered arc (tier 0) uses the mockup's unchecked style.
- Checkbox:
  - Turning an arc off sets it to tier 0.
  - Turning it on restores its last tier, or T1 if it never had one.
- TIER row:
  - Shows the selected arc's tier as SELECTED. Clicking a tier sets it.
  - Tiers above the arc's cap are disabled: opacity .35, no hover.
  - A MICRO right of the “TIER” label shows the cap, for example “LEGS CAP T2 · HIGHER IS RARE LOOT”.
  - Shift+click sets every covered arc, each clamped to its cap. When no cap message is showing, that MICRO reads “SHIFT+CLICK: ALL ARCS”.
- Halo widget:
  - Each arc is drawn in its own tier colour, as game/DESIGN_DELTAS.md §2 asks.
  - The selected arc gets a 1.2px --text-hi inner stroke.
  - Centre sub-label: “T2 MENDER” when all lit arcs share one tier; otherwise “MENDER” in the highest tier's colour.
- Core cards: the icons and the selected border/bg use the colour of the highest current arc tier, falling back to T2 blue.
- All arcs at 0 means no halo: weight None, and the core is kept but inactive.
- Protocol: LoadoutChoice.armor is a preset id today. It must carry a custom {core, tiers}; ArmorPreset already has that shape.

A4. MOCKUP NUMBERS THAT DIFFER FROM GAME DATA
Always bind to data. In the default examples:
- Shield: 132, not 120.
- Regen: 20/s after 2.5 s, not 4/s after 5 s.
- Sprint base: 7.0, not 6.8.
- Gear budget: 12, not 20.
- No food drain.
- PHASE description: “IMMUNE TO SLOW”.
- “SIDE R” / “LASER (R)”: the game has no left or right side rail, so show “SIDE” / “LASER”.
- Fire rate: 720 rpm, not 750.
- ADS: 0.22 s.
- Reload: 2.1 s.
- Effective range: 25 m.

A5. AGENTS DON'T EXIST IN THE GAME YET
- Keep the column, since the user likes the hub. Ship agents.ron with Kestrel and Solace.
- Until abilities exist, the AGENT header micro reads “1 OF 2 · ABILITIES NOT IN THIS BUILD”.
- Selecting an agent changes only the third-person model and the agent id.

A6. THREE WEAPONS (an SMG is being added)
- Three tabs: each is (872−12)/3 = 286.7 wide.
- Fit silhouettes into 96x26 (contain).
- Name: 20px, ls 1.6. Subtitle: 11px, ls 1.98. This lets “VK-50 WARDEN” fit.
- The SMG has no silhouette yet. Until the local session supplies one, show the tab without it.
- Selecting the SMG unlocks the RIP rows in the ammo picker.

A7. STATS
- HANDLING becomes MOBILITY.
- Recoil is shown as an index (100 = stock).
- Values come from data, as listed in data bindings.

A8. ATTACHMENT DATA FIELDS
- Add to attachments.ron: name, short name, blurb, and an optional flag per category. Copy must not be hard-coded.

A9. BEVY IMPLEMENTATION NOTES
- Letter-spacing:
  - Use LetterSpacing::Px(font_px × em). Every ls value above is already in px.
  - Do not use LetterSpacing::Rem, which multiplies RemSize rather than the font size.
- Text case: Bevy has no text-transform, so uppercase strings in code.
- Font weights: TextFont weight only affects variable fonts. Load a separate static TTF per weight.
- Numbers: add FontFeatureTag::TABULAR_FIGURES to numeric text.
- Gradients: use BackgroundGradient, RadialGradient for the screen and LinearGradient for the card fade and floor fade.
- Glows and shadows: use BoxShadow.
- Rotations: rotate the tier diamonds with UiTransform.
- Dashed borders: Bevy has none. Use a 9-slice dashed-rectangle PNG (ImageNode with NodeImageMode::Sliced) tinted --stroke-mid. This covers “+ SAVE AS” and empty mags.
- Tier pips: a tiny parallelogram PNG, because there is no skew.
- Radii: Node.border_radius of 2 for panels and keycaps, 50% for the hotspot dots.
- Preview: a ViewportNode with its own render-target camera and lighting.
- Hotspots: absolute nodes repositioned each frame from the socket world positions.
- Halo widget: no SVG support, so build it from layered white PNGs tinted with ImageNode.color. Needed layers: an arc per zone per core shape, the Mender inner arc, Volt ticks, the Phase split torso arc, the band rings and the cell pill. A UiMaterial is an alternative.

A10. REMOVE MOCKUP-ONLY ITEMS
- The preview badge “LIVE 3D PREVIEW · VIEWPORTNODE”.
- The bottom-right mock label.

A11. FUTURE HEALING ITEMS
- Reserve x 48-408, y 714-1010 in the agent column, empty in the mockup, for a later “MEDS · WHEEL ORDER” panel.
- It should use the same card pattern as the mag strip: full-body items, then per-region items, each in radial order.
- Hidden until the items exist.

## assets
IMAGES (/home/user/sharline/design/ui/mockups/img)
- kestrel_portrait.jpg: 640x640, drawn at 200x200 in agent card 1.
- solace_portrait.jpg: 640x640, drawn in agent card 2.
- mako_dark.jpg: 1280x720, the placeholder weapon render, drawn at 960x540 in the preview. The live ViewportNode replaces it.
- warden_dark is listed in _src/build.py but is missing from img/, so there is no Warden placeholder.
- hud_street.jpg and menu_kestrel.jpg are not used on this screen.
- Copy the portraits into game/assets/ui/ and note it in the PR, because art/ and assets/ belong to the local session.

ICONS (symbol ids in _src/icons.svg)
None of these can be used as SVG in Bevy. Rasterise each to a white-on-transparent PNG at 2x and tint it with ImageNode.color. Sizes given are the draw sizes on this screen.
- Agent abilities (viewBox 32): i-grapple, i-scan, i-kes-ult, i-drone, i-pulse, i-sol-ult.
  - 22px in the card strips, 26px in the ability list.
- Weapon silhouettes:
  - i-mako: viewBox 240x64, drawn at 130x35.
  - i-warden: viewBox 280x64, drawn at 150x35.
  - Both contain #0B0E13 detail at 55% (vents); bake it as dark or as cutouts.
- Attachment slot glyphs (viewBox 32): i-optic, i-stock, i-magslot, i-under, i-side, i-gunshield.
  - 16px in slot headers.
- Halo zone glyphs (viewBox 24): i-head, i-torso, i-arms, i-legs.
  - 18px in the zone tiles.
- i-mag (viewBox 16x28): new use, as the ammo glyph in the ammo picker.
- The halo widget is generated by haloSVG in _src/widgets.js. It is drawn at 62px (core cards) and 140px (coverage); see A9.

NEW ASSETS NEEDED
- A reload-wheel slot glyph: a 16px six-sector ring. Either 6 variants, or one sector image rotated with UiTransform.
- An i-smg silhouette. Request it from the local session.
- A 9-slice dashed-border PNG.
- A tier-pip parallelogram PNG.
- A diamond, which can be a plain square rotated 45deg.

FONTS
- Barlow Condensed 500, 600 and 700, and Barlow 400: TTFs from Google Fonts (OFL), placed in game/assets/fonts.

