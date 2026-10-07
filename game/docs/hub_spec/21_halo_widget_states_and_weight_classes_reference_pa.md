# Halo widget: states and weight classes (reference panel 'Halo widget states', bottom right of mockup 03)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/03_health_panel.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/health_panel.html",
 "/home/user/sharline/design/ui/mockups/_src/widgets.js",
 "/home/user/sharline/design/ui/mockups/_src/common.css"
]

## purpose
A reference sheet for the player's own halo as a top-down widget. It covers 5 shield states (idle, hit, low, broken, regen) and how core, tier, cell count and weight class change its silhouette (light, medium, heavy, Bulwark hex, partial coverage). The widget appears at 150px in the health panel, and can be reused small in the compact readout. Not a player-facing screen.

## layout
PANEL (anchored top-left):
- left 790, top 610, width 1082, height auto (the render ends at y 1071).
- Padding 20 / 26. Content x 817-1845.
- Style: --panel rgba(9,12,17,.70), 1px border rgba(255,255,255,.09), radius 2.

CONTENT:
- h1 'HALO WIDGET STATES': caps at y 640-660.
- Sub line: y 672-685.
- Two rows (.hs-row: flex, gap 10, margin-top 12), each of 5 equal cards about 197.6 wide: x 817-1015, 1025-1222, 1232-1430, 1440-1637, 1647-1845.
- Row 1: cards y 698-879; halo size 104; name caps at y 821-831; description caps from y 843.
- Row 2: cards y 892-1050; halo size 96; name caps at y 1007-1017; description caps at y 1029-1036.
- Mockup footer label at bottom-right (right 12, bottom 8): 'MOCKUP 03 · HEALTH + HALO CLOSE-UP, ALL STATES', FD 12px, .14em, rgba(255,255,255,.28). Omit in game.

## elements
h1: FD 700, 30px, .1em, #F3F0E9.
Sub: FB 14px, #9CA2AB. Copy: 'Your own halo in the HUD (top-down: Head front/up, Arms left, Torso back/down, Legs right; same order as the 3D halo).'

CARD (.hs)
- Flex column, centred, gap 4, padding 8 / 4 / 10.
- Background rgba(255,255,255,.03). 1px border rgba(255,255,255,.09).
- Name: FD 700, 14px, .14em.
- Description: FD 500, 11.5px, .06em, UPPERCASE, #9CA2AB, centred, line-height 1.3, padding 0 4. The global '.d' class makes it condensed caps; keep that look.

ROW 1 (all T2 Mender, covering head/torso/arms, medium weight, 2 cells, value shown):
- 'IDLE' (#F3F0E9): value 120, shield 100%. 'Full. Arcs at 85 %.'
- 'HIT' (#59B3FF): value 84, 70%. '0.25 s flare + white rim, the hit arc shakes 2 px.'
- 'LOW < 25 %' (#FFA23A): value 22, 18%. 'Arcs drain clockwise. Crack sprite overlay.'
- 'BROKEN' (#FF3B4E): value 0 in #FF3B4E, 0%. 'Shard burst 0.4 s, outlines dashed on the body.'
- 'REGEN' (#9CF7C8): value 54, 45%. 'Sweep shimmer while it refills.'

ROW 2 (tier mode: no value, centre 'Tn' plus H/T/A/L letters):
- 'LIGHT': T1 Phase, head+torso, 1 cell, no band. 'T1 Phase · 1 cell · no band'
- 'MEDIUM': T2 Mender, head/torso/arms, 2 cells, thin band. 'T2 Mender · 2 cells · thin band'
- 'HEAVY': T3 Volt, all four zones, 3 cells, armored band. 'T3 Volt · 3 cells · armored band'
- 'HEAVY': T4 Bulwark, all four zones, 3 cells. 'T4 Bulwark · hex ring'
- 'COVERAGE': T3 Bulwark, head+torso, heavy, 3 cells. 'Head + Torso lit, Arms + Legs dark'

HALO WIDGET SPEC (haloSVG)
Box: a 120x120-unit viewBox drawn at size S (k = S/120). Centre (60,60). Ring radius R = 34u.
- Arc positions (angle clockwise from +x on screen): Head centred at −90° (top), Legs at 0° (right), Torso at 90° (bottom), Arms at 180° (left). Each arc spans centre ±39°, leaving 12° gaps.
- Band width bw by core:
  - Bulwark 8u. Its arcs follow a pointy-top hexagon: r(θ) = R·cos30°/cos(((θ+90) mod 60) − 30).
  - Mender 4u, plus an inner 'twin' arc at radius 27u spanning a0+3° to a1−3°, 2.4u wide, tier colour at .8.
  - Volt 6u, plus 3 radial spikes per arc at a0+10°, the midpoint and a1−10°, from R+bw/2 outward by 6u, 3.2u wide (#33363D when unlit).
  - Phase 5u. The bottom (Torso) arc is split by a 16° gap at its centre.
- Lit arc: a glow stroke bw+3u in the tier colour (opacity .35 idle, .7 otherwise; blur σ 2u, 3.2u on hit) under a crisp bw stroke (opacity .85 idle, 1.0 otherwise).
- Remaining shield per arc: overlay a bw+0.5u #0B0E13 stroke at .62 from a0+(a1−a0)·frac to a1. The arc empties from its clockwise end.
- Unlit arc: bw stroke #27272C, plus a 1u white hairline at .13.
- Weight band:
  - Light: none.
  - Medium: circle r=45u, 3u #3A3F47 stroke, plus 1u tier colour at .25.
  - Heavy: r=46u, 7u #3A3F47 stroke dashed 14u/3u, plus 1u tier colour at .30.
- Power cells: n pills of 6x10u (corner radius 3u) at radius 53u, the first at −60°, spaced 360°/n. Tier colour at .95 (.35 when broken). The group orbits 360° in 10 s (14 s with 3 cells).
- Centre, value mode: the number in FD 700 21u, #F3F0E9 (#FF3B4E when broken), baseline 62u. Sub label 'T2 MENDER' in FD 600 8u, letter-spacing 1.2u, tier colour, baseline 73u.
- Centre, tier mode: 'T2' in FD 700 13u #F3F0E9, baseline 64u. Zone letters H/L/T/A in FD 700 9.5u at radius R−15u (Mender) or R−12u (others); tier colour when lit, #5A6069 when not.
- Broken: all arcs unlit, plus 4 shard marks (2u strokes, tier colour at .9): M30 34l6 4-2 6, M88 30l-5 6 4 4, M84 90l-6-3-1 6, M33 86l6-2 1 6.
- Hit: a 1.2u white rim on lit arcs at .9.
- Pixel sizes: at S=150 (k 1.25), R=42.5px and the value is 26px; at 104, R=29.5px; at 96, R=27.2px.

## data_bindings
Reference only. In game:
- tier per arc = PlayerLoadout.halo.tiers[z]; lit = tier > 0 and shield > 0.
- frac per arc = Vitals.halo.shield[z] / halo.capacity[z].
- value = round(Σ shield).
- core = halo.core.
- weight band = PlayerLoadout.weight; cells = weight_effects[weight].cells.
State:
- broken: per arc, when shield[z] == 0 with tier > 0. That arc goes unlit, its body outline goes dashed, and the shard burst plays the frame it hits 0.
- low: Σ shield < 25% of Σ capacity. Name/value cue in #FFA23A.
- regen: halo.regen_wait_s == 0, some arc below capacity, and the core has regen. Glow opacity .7 plus the shimmer.
- hit: when any shield[z] dropped since the last frame. Flare for 0.25 s and a 2px shake on that arc.
- idle: otherwise.

## interactions
None (static reference).
Animation timings from the sheet:
- hit flare 0.25 s (brightness 1.8 → 1, opacity 1 → .9);
- hit arc shake 2px;
- shard burst 0.4 s;
- cells orbit 10 s or 14 s.
Not specified in the mockup; suggestions:
- regen 'sweep shimmer': a bright 20° highlight travelling along the lit arcs every 0.8 s;
- LOW 'crack sprite overlay': a crack texture over the ring at .6.

## adaptations
- Per-arc tiers (DESIGN_DELTAS 2): colour and drain each arc separately. Row 2's single-colour rings become mixed when the tiers differ.
- Sub label: 'Tn CORE' only when every lit arc has the same tier, otherwise 'CORE'.
- ORDER MISMATCH to resolve:
  - The halo puts Legs on the RIGHT and Torso at the BOTTOM.
  - The heal ring's region ring (radial.rs REGION_ORDER) puts Torso on the RIGHT and Legs at the BOTTOM.
  - Keep both, because they are different metaphors (top-down halo vs body). But label the region-ring chips with zone icons and names so the player never has to map one onto the other.
- No halo (arm_none): draw every arc unlit, with no band, no cells, and centre value '0' in #646B75.

## assets
No images or icons.
PNG masks to rasterise (white, tinted), one canvas per core so they stack:
- per core, an arc-segment mask per zone: 4 arcs (Phase torso = 2 pieces), crisp and pre-blurred glow;
- the Mender inner arc;
- Volt spikes;
- Bulwark hex arcs;
- weight bands: medium solid ring, heavy dashed ring;
- the cell pill;
- the 4-shard broken overlay;
- a crack overlay (new art).
The per-arc drain needs either a UiMaterial (angle cut-off uniform) or a radial-wipe shader. Bevy UI has no stroke-dash or arc-clip primitive. One UiMaterial for the whole widget is the simplest route.

