# Downed state (host option)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/10b_downed.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/death.html",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg"
]

## purpose
An optional knocked-down state (labelled 'host option' in the mockup). Instead of dying instantly you bleed out over a timer, can crawl, see that a teammate is coming, can give up, or ping for help. A teammate revives you by holding F. The game has NO downed state yet, so this screen is only shown once a ruleset flag enables it.

## layout
Full-screen overlay. The in-match HUD is hidden except the kill feed.

BACKDROP
- The live view, desaturated like the death screen (grayscale 0.85, brightness 0.55).
- Red vignette: BackgroundGradient Radial, ellipse farthest-corner at centre. Stops: rgba(60,0,8,0) at 30%, rgba(90,0,12,0.75) at 100%.

CENTRE COLUMN
- Centred horizontally, its vertical centre at 40% of the height (y=432). Occupies x 721-1199, y 252-612, column, align centre, gap 10.
- Ring box 150x150 at x885, y252.
- 'DOWNED' at y412, h64 (box x831-1089).
- Sub-line at y486, h22.
- Help pill at x763.6, y528, 392.8x44 (margin-top 10 extra).
- Hint row at y590, h22 (margin-top 8 extra), gap 20. Hints start at x 721.2, 886.2 and 1071.9.

REVIVER EXPLAINER PANEL
- Anchored bottom-right, right 80, bottom 80: x1320, y737, 520x263, padding 16/18.
- h2 at x1339, y754.
- Image box 482x200 at x1339, y783.
- Inside it, a prompt column centred at (1580, 58% of the box): ring 70x70 at x1545, y839.8, then two text lines at y915.8 and y939.8.
- It is a design explainer, see adaptations.

## elements
RING (150 box)
- The circle Node is 143x143, centred, with a 7 px border.
- Remaining bleed-out fraction in #FF6170, track rgba(255,255,255,0.15), from 12 o'clock clockwise. The mockup shows 0.667 = 10 of 15 s.
- Centre number: BC 700 56px --text-hi, tabular, '10'.

'DOWNED': BC 700 64px, .16em (10.24px), line-height 64, #FF6170.

Sub-line: BC 600 18px, .14em (2.52px), --text-hi, 'BLEEDING OUT · CRAWL TO COVER'.

HELP PILL
- Style: bg rgba(9,12,17,0.8), 1px border rgba(82,229,165,0.5), no radius, padding 10/16, row, gap 10, align centre.
- Contents:
  - Icon i-heal 20x20 in --ally #52E5A5.
  - 'JUNO IS COMING · 8 M' in BC 700 18px .1em (1.8px) --ally.
  - .micro (11px BC 600 .16em) coloured --text-mid: 'SOLACE REVIVES 2× FASTER'.

HINT ROW (ghost keycaps 22 tall + .hint labels)
- [WASD] 'CRAWL 1.0 M/S'.
- [F] 'HOLD 2 S TO GIVE UP'.
- [Z] 'PING FOR HELP'.

REVIVER PANEL (.panel.hi)
- h2: BC 700 16px, .18em (2.88px), --text-mid, 'WHAT THE REVIVER SEES'.
- Image box: 1px --stroke-mid border, background image (live-view stand-in).
- Reviver ring 70x70:
  - Inner disc r30 filled rgba(9,12,17,0.6).
  - Track rgba(255,255,255,0.2), 5 px.
  - Progress --ally #52E5A5, 5 px, showing the done fraction (0.57 in the mockup).
  - Centred i-heal 24x24 in --ally.
- Text lines: BC 700 15px, .14em (2.1px), --text-hi, TextShadow 0 1px 3px #000.
  - Line 1: 'REVIVING KESTREL_YOU · 2.1 S'.
  - Line 2: 'HOLD F · 5 S (SOLACE 2.5 S)' in the .micro face but coloured --text-hi (rendered BC 700 15px in the build).

## data_bindings
Everything here needs new sim state; none of it exists today.
- Ring and number: bleed-out seconds left / total (the mockup implies 15 s), as ceil.
- Help pill: the nearest alive teammate who is reviving or moving to you: '{NAME} IS COMING · {distance m} M'.
  - Nobody coming: '{nearest teammate} · {d} M AWAY' in --text-mid, with a --stroke-mid border.
  - No teammates alive: hide the pill.
  - Micro line: only when agents exist (the Solace revive bonus); hide it until then.
- Crawl speed: from movement.ron (new crawl entry), formatted 1 dp + ' M/S'.
- Give-up hold seconds and revive time: new rules.ron values (the mockup shows 2 s and 5 s).

## interactions
- WASD crawls (no sprint, jump, jetpack, zipline or weapon).
- Hold F for 2 s to give up: goes straight to the Death recap. While F is held, fill the 'F' keycap's hint label from --text-mid to --text-hi, left to right (not in the mockup).
- Z pings for help: hide this hint until a ping system exists.
- Esc opens the ESC menu.
- Being revived returns you to the HUD. The bleed-out timer reaching 0 goes to the Death recap.

## adaptations
1. GATING: add `downed: bool` to each ruleset in rules.ron (TDM false, Range false). Implement the screen only behind it. Until the sim has a downed state, this screen is never shown.

2. REVIVER PANEL: the 'WHAT THE REVIVER SEES' panel is a mockup explainer. Do NOT show it to the downed player. The reviver's progress ring and text are a HUD overlay on the reviver's screen. The user said to skip HUD overlays, so it is out of scope; its numbers are listed above for later.

3. KEY CLASH: F is the zipline key while alive. While downed, F means give up only. The reviver's 'HOLD F' needs an interact binding that does not conflict with zipline grab when standing next to a downed teammate.

4. AGENT NAMES: no agents yet, so drop the 'SOLACE REVIVES 2× FASTER' line and the '(SOLACE 2.5 S)' text.

## assets
Icon: i-heal from icons.svg, viewBox 24, a plus shape: 'M9 3h6v6h6v6h-6v6H9v-6H3V9h6z'. Rasterise to white PNG at 2x (48x48) and tint --ally. It is used at 20x20 in the help pill and at 24x24 in the reviver ring.

Image: /home/user/sharline/design/ui/mockups/img/hud_street.jpg is a placeholder backdrop and reviver thumbnail only. The live view replaces it.

