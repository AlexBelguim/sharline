# Body silhouette widget: zone states (reference panel 'Zone states', top right of mockup 03)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/03_health_panel.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/health_panel.html",
 "/home/user/sharline/design/ui/mockups/_src/widgets.js",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg"
]

## purpose
A state reference sheet for the body silhouette widget, which is used large (w=200) in the health panel and small in the compact readout and the matrix (w=40). It defines how HP fraction, state colour, halo coverage, bleeding and destruction are drawn. It is not a player-facing screen. Build the widget from it, and optionally add a dev-only 'widget gallery' that reproduces this matrix for visual QA.

## layout
PANEL (anchored top-left):
- left 790, top 48, width 1082, so x 790-1871. Height is auto and runs to about 634, where the 'Halo widget states' panel (top 610) overlaps it: a mockup overlap.
- Padding 22 / 26. Content x 817-1845 (1028 wide).
- Style: --panel rgba(9,12,17,.70) (renders ≈ #0B0E14), 1px border rgba(255,255,255,.09), radius 2. No accent bar.

CONTENT:
- h1 'ZONE STATES': caps at y 80-100, x 817-986.
- Sub line: y 113-125.
- Grid: columns 110 + 5 × 1fr, gap 6, margin-top 14.
  - Data columns are about 177.6 wide: x 933-1110, 1117-1293, 1300-1477, 1484-1660, 1667-1844.
  - Header row: name caps at y 143-153, small text caps at 160-167, 2px underline at y 174-175.
  - Four rows of 96px: y 182-277, 284-379, 386-481, 488-583.
  - Row labels sit in the 110px column (x 817-927), vertically centred (e.g. HEAD caps at 223-235).
- Legend row: caps at y 599-609, from x 817, gap 18.

## elements
h1: FD 700, 30px, .1em, #F3F0E9, uppercase.
Sub: FB 400, 14px, #9CA2AB. Copy: 'Silhouette fill height = remaining HP. Colour = state. A tier-coloured outline marks zones covered by the halo shield.'

COLUMN HEADER (.ch)
- FD 700, 14px, .16em, #F3F0E9, centred, padding-bottom 4, border-bottom 2px in the column colour.
- Small second line: FD 600, 11px, .1em, #9CA2AB.
- Columns:
  - HEALTHY / '100 %', #E6E2D8
  - DAMAGED / '55 %', #FFA23A
  - CRITICAL / '20 %', #FF3B4E
  - DESTROYED / '0 HP', #8A8F98
  - BLEEDING / '70 % + bleed', #FF6170

ROW HEADER (.rh)
- Flex row, centre, gap 8. An 18px zone icon (i-head, i-torso, i-arms, i-legs) tinted #F3F0E9, then the name in FD 700, 15px, .16em, #F3F0E9: HEAD, TORSO, ARMS, LEGS.

CELL
- Height 96. Flex row, centred, gap 10.
- Background rgba(255,255,255,.03) (renders ≈ #11141A). 1px border rgba(255,255,255,.09).
- Contents: a body widget at w=40 (40x80), then a text block:
  - value: FD 700, 20px, line-height 20, #F3F0E9;
  - '/ max': FD 600, 11px, .12em, #9CA2AB, on its own line;
  - optional note: FD 600, 11px, .12em, margin-top 3.
- Only the row's zone takes the column's state; the other zones stay full and healthy.
- Values, by row (in column order):
  - head 35, 19, 7, 0, 25 (/35)
  - torso 85, 47, 17, 0, 59 (/85)
  - arms 60, 33, 12, 0, 42 (/60)
  - legs 70, 39, 14, 0, 49 (/70)
- Notes, DESTROYED column only:
  - head and torso: 'DEATH' in #FF6170;
  - arms and legs: 'overflow ×0.7 → torso' in #646B75 (game: ×0.6 for arms, ×0.7 for legs).

LEGEND
- FB 12.5px, #9CA2AB. Each key word in FD (bold), .1em, coloured.
- Copy:
  - 'HEALTHY ≥ 75 %' (#E6E2D8)
  - 'DAMAGED 35–74 %' (#FFA23A)
  - 'CRITICAL 1–34 %, pulses 1.1 s' (#FF3B4E)
  - 'DESTROYED 0, hatched + red outline' (#F3F0E9)
  - 'BLEEDING drip loop + −0.8 HP/s' (#FF6170)

BODY WIDGET SPEC (bodySVG)
Geometry: a 100x200-unit box drawn at w x 2w px (scale k = w/100).
Zone paths:
- head: M42 4H58L64 12V26L58 34H42L36 26V12Z (an octagon)
- torso: M33 39H67L72 47L68 100H32L28 47Z
- arms (one zone, two shapes): M25 41L18 44L9 107L17 110L27 64Z and M75 41L82 44L91 107L83 110L73 64Z
- legs (one zone, two shapes): M32 104H49L48 195H35Z and M51 104H68L65 195H52Z
HP bands (unit y used for the fill): head 4-34, torso 39-100, arms 41-110, legs 104-195.
Layers, bottom to top:
1. Halo coverage glow (covered zones only): the zone outline stroked at 6u in the tier colour, opacity .55, Gaussian blur σ 2.2u.
2. Coverage line: 4.2u stroke in the tier colour, opacity 1, round joins. When that arc's shield is broken: dashed 4u/3u, and both layers at 25% of their opacity.
3. Base: fill #2A2D33 with a 1.5u #0B0E13 stroke.
4. State fill: the zone shape in the state colour, clipped to the band from fillTop = y1 − (y1−y0)·frac down to the bottom.
   - Colours: ok #E6E2D8, damaged #FFA23A, critical #FF3B4E.
   - Critical pulses opacity 1 → .35 → 1 over 1.1 s, ease-in-out.
5. Destroyed zone instead of layers 3-4: a hatch fill (45° stripes on a 5u period, base #15171B, stripes 1.4u wide #FF3B4E at .55) with a 1.6u #FF3B4E outline.
6. Hit flash: white overlay at .55. Our HUD can drive this from damage feedback, about 0.15 s; the mockup gives no duration.
7. Treating / heal: 2u #9CF7C8 stroke, dashed 3u/3u, pulsing over 1.4 s.
8. Bleeding: a drop glyph (path M5 0c2 3 4 5 4 7.5a4 4 0 0 1-8 0C1 5 3 3 5 0z, about 8x11.5u) filled #E0162E with a 0.8u #0B0E13 stroke.
   - Its top-centre sits at: arms (13,96) and (87,96); legs (42,170) and (58,170); head (50,28); torso (50,86).
   - It drips: translateY 0 → 10u while opacity goes 1 → 0, 1.2 s, ease-in, looping.
Sizes: at w=200 every 1u = 2px; at w=40, 1u = 0.4px. At small sizes, clamp the coverage line to at least 1.5px and the glow to at least 3px.

## data_bindings
None on the reference panel itself; it is illustrative. The widget's live inputs:
- frac[z] = Vitals.health.hp[z] / max[z], with the state derived from it;
- covered[z] = PlayerLoadout.halo.tiers[z] > 0, coloured by tier;
- arc broken[z] = tiers[z] > 0 && Vitals.halo.shield[z] == 0;
- bleeding[z] = bleeding.active[z] > bleeding.residual[z], only when rules.bleeding;
- destroyed[z] = hp[z] ≤ 0. A destroyed head or torso means dead, so the widget is not shown.
- treating[z] from PlayerItems.using;
- hit[z] from local damage feedback.
In a dev gallery, show the matrix with the game's real zone max (45/120/70/85) and real spill (arms ×0.6, legs ×0.7). Generate the legend's bleed rate from ammo.ron (Shrapnel 1.5-2.5 HP/s per stack, NPC-only), not −0.8.

## interactions
None (static reference). A dev gallery, if built, is opened from a debug key in the gun range and closed with Esc.

## adaptations
- Use the widget, not the panel.
- Per-arc tiers: each zone's outline uses its own arc's tier colour, and each arc can be broken (dashed) on its own.
- 'DESTROYED' on a limb is called BROKEN when rules.injuries is on (Wounds.broken). In TDM the zone still renders hatched, because it still spills damage.
- Never draw bleeding in TDM (rules.bleeding is off).
- The heal outline means 'item in use on this zone', since there is no heal-over-time.
- Mockup numbers (35/85/60/70, ×0.7 for both limbs, −0.8 HP/s) are placeholders; take them from data.

## assets
No images. Icons: i-head, i-torso, i-arms, i-legs at 18px.

PNG masks to rasterise for the widget. Use white on transparent at 2x the largest use (w=200 → 400x800 px canvas). Keep all masks in the same canvas so they stack with offset 0.
- One fill mask per zone: head, torso, arms (both arms), legs (both legs).
- One outline mask per zone with a 4.2u stroke, and one dashed variant.
- One pre-blurred glow mask per zone: 6u stroke, σ 2.2u.
- One base-stroke mask per zone: 1.5u.
- One hatch-pattern tile: 10x10 px with a 45° stripe, or a pre-hatched mask per zone.
- One heal-dash mask per zone.
- The drop glyph: 16x23 px.
Fill-from-bottom in Bevy: put an absolute Node with Overflow::clip() over the band, top = band top + (1−frac)·band height and bottom = band bottom, then place the full-size mask inside at the matching negative offset. A UiMaterial with a frac uniform is an alternative.

