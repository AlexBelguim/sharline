# Health panel (in-match overlay; left column of mockup 03)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/03_health_panel.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/health_panel.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/widgets.js",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg",
 "/home/user/sharline/design/ui/mockups/health_panel.html"
]

## purpose
The full health readout for one player. It has a large body silhouette with four zone callouts (HP, state, effects), the total HP, the items you can treat with, and your halo shield. In the mockup it is 'the HUD vitals block expanded' and opens on hold H. In our game, H already toggles the heal ring, so this panel should open docked on the left WHILE THE HEAL RING IS OPEN. The player then sees which region needs what while picking an item and then a region. The two right-hand panels of the PNG ('Zone states' matrix and 'Halo widget states') are a reference sheet for the two widgets drawn here, not part of the player screen. They are specified as separate entries below.

## layout
Canvas 1920x1080 with Bevy UiScale = window_height/1080, so every px below is a 1080p value. The mockup draws a presentation backdrop behind the panel: a radial gradient centred at 30% 40%, #141B25 at 0% to #07090D at 70%, plus a 40px grid of 1px rgba(255,255,255,.025) lines. In a match, do NOT draw that backdrop or any full-screen scrim; the panel sits over the live 3D view.

PANEL (anchored top-left): left 48, top 48, width 700, height 984 including the border, so x 48-748 and y 48-1032. Padding 22 top/bottom and 26 left/right inside a 1px border. Content box: x 75-721 (646 wide), y 71-1009.

REGIONS IN THE MOCKUP (absolute y, measured on the render):
1 Header, y 71-130. Left block (title + subtitle) at x 75. Right block (TOTAL) right-aligned to x 721, top 71. Flex row, space-between, align flex-start.
2 Figure, a relative container x 75-721, y 146-576 (height 430; CSS margin-top 18).
   - Body silhouette 200x400 at x 325-525, y 146-546 (offset 250 from the container's left).
   - Leader lines, 1px tall: head x 275-359 @ y 186; torso x 275-385 @ y 296; arms x 537-687 @ y 282; legs x 495-685 @ y 452.
   - Four callouts, each 190 wide: HEAD at (75,150) and TORSO at (75,262) are left-aligned. ARMS (top 266) and LEGS (top 436) are right-aligned, placed at x 575-765 in the mockup.
   - MOCKUP BUG: the ARMS and LEGS callouts overrun the panel's right edge (748) by 17px. In game, anchor them at right:0 of the content box, so x 531-721. Shorten their leaders so they stop 15px before the text: arms x 537-643 @ 282, legs x 495-646 @ 452.
3 Section TREAT. 1px rule at y 592 across x 75-721. h2 caps at y 612-622. Card grid y 636-735: three cards 210x100 at x 75-285, 293-503 and 511-721 (3 equal columns, gap 8).
4 Section HALO SHIELD. Rule at y 752. h2 caps at y 772-782. Row y 796-946 (flex, gap 18, align-items centre):
   - Halo widget 150x150 at x 75-225, centre (150,871).
   - Key/value grid from x 243. Label column 110 wide, so values start at x 353. Five rows on a 22px pitch, first label caps at y 825.
5 Section ENERGY & FOOD. Rule at y 965. h2 caps at y 985-995. Two columns x 75-391 and 405-721 (gap 14). Header row caps at y 1012-1022, bar y 1032-1037, note y 1046-1058.
   - MOCKUP BUG: this section runs past the panel's bottom edge (1031).

ADAPTED LAYOUT FOR THE GAME:
- Drop ENERGY & FOOD (see adaptations).
- Kit of 3 items or fewer: keep the mockup geometry exactly. Treat cards stay 100 tall, the halo row is 796-946, and y 947-1009 stays empty.
- Kit of 4-6 items: two card rows.
   - Figure height 410 (y 146-556; the body still fits at 146-546; the legs callout ends at about 550).
   - TREAT rule at 572, h2 caps 592-602, grid top 616.
   - Rows of 84px (descriptions capped at 2 lines), row gap 8, grid ends at 792.
   - HALO SHIELD rule at 808, h2 caps 828, halo row 852-1002.
   - All of this fits above the content bottom (1009).
- Kit of 7-8 items (MAX_KIT = 8): use 4 columns of 155.5 wide. Drop the 20px item icon from the title row and use 14px titles, so 'TRAUMA KIT ×1' fits.

## elements
TOKENS (common.css, CSS variable = hex):
- Text: --text-hi #F3F0E9, --text #D7D4CD, --text-mid #9CA2AB, --text-low #646B75.
- Strokes: --stroke rgba(255,255,255,.09), --stroke-mid rgba(255,255,255,.16), --stroke-hi rgba(255,255,255,.32).
- Surfaces: --panel-hi rgba(16,21,29,.82), --panel rgba(9,12,17,.70), --bg0 #07090D.
- Health states: --hp-ok #E6E2D8, --hp-dmg #FFA23A, --hp-crit #FF3B4E, --hp-dead #15171B, --bleed #E0162E, --heal #9CF7C8.
- Misc: --warn #FFA23A, --coral #FF8C7A, --bone #C4BFB5.
- Halo tiers: --t1 #EDF1F6, --t2 #59B3FF, --t3 #C46CFF, --t4 #FFCE50, --unlit #27272C.
- Literals used: critical/bleed text #FF6170, destroyed grey #8A8F98, silhouette base #2A2D33, silhouette stroke #0B0E13.
- Composites as rendered, for screenshot comparison: panel ≈ #0F131B, panel border ≈ #23282F, card bg ≈ #191E25, card border ≈ #2D3238, coral card border ≈ #754A47, leader ≈ #4B4F55, bar track ≈ #282C34.

FONTS: FD = Barlow Condensed (static 500/600/700). FB = Barlow (400, 700). Both come from Google Fonts under the OFL licence.
- In Bevy 0.19 load one font handle per weight; FontWeight only affects variable fonts.
- Letter-spacing: LetterSpacing::Rem(x), which multiplies the font size like CSS em.
- Line height: LineHeight::Px or LineHeight::RelativeToFont.
- 'Uppercase' means write the string in caps; Bevy has no text-transform.
- '.num' means tabular figures. Barlow figures are near-monospace, so no special handling is needed.

A. PANEL FRAME
- BackgroundColor rgba(16,21,29,.82).
- 1px border rgba(255,255,255,.09), border radius 2px.
- Accent bar: an absolute child at top 0, left 0, right 0, height 2px, colour #F3F0E9. It sits inside the border, at y 49-50.

B. TITLE 'HEALTH'
- FD 700, 30px, letter-spacing .1em (3px), #F3F0E9.
- Top-left (75,71). Caps span y 80-100 and x 76-170.

C. SUBTITLE
- FB 400, 14px, #9CA2AB, margin-top 2. The line spans y 109-126.
- Mockup copy: 'Hold ' + [key H] + ' in match · the HUD vitals block expanded'.
- Inline key cap: min 18x18, padding 0 6, FD 700 12px, letter-spacing .04em, text #07090D on bg #F3F0E9, radius 2.
- Game copy: see adaptations.

D. TOTAL (right-aligned to x 721)
- Label 'TOTAL': FD 600, 13px, .14em, #9CA2AB. Caps at y 75-83.
- Value '136': FD 700, 34px, line-height 34, #F3F0E9.
- Then ' / 250': FD 700, 16px, #9CA2AB.
- The value line's caps span y 93-116 and x 635-720.

E. BODY SILHOUETTE, 200x400 at (325,146)
See the 'Body silhouette widget' entry for every layer and state. Mockup instance:
- Head 100% healthy.
- Torso 61% damaged.
- Arms 23% critical (pulsing) and bleeding: drops at unit points (13,96) and (87,96), which are px (351,338) and (499,338).
- Legs 50% damaged, with a heal outline.
- Head, torso and arms are covered by a T2 halo, shown as a #59B3FF outline with glow. Legs are uncovered.

F. LEADER LINES: 1px, rgba(255,255,255,.25). Positions are under layout.

G. ZONE CALLOUT (190 wide; T = callout top)
Rows:
1. Name row: caps at T+3..T+14. A 16x16 zone icon tinted in the state colour, an 8px gap, then the name. In right callouts the icon comes AFTER the name and the row is justified to the end.
2. HP value: caps at T+24..T+44.
3. Bar: T+58..T+62.
4. Status line: caps at T+71..T+79.
5. Effect text: first line caps at T+88, line pitch 17.
Fonts and colours:
- Name: FD 700, 15px, .16em, #F3F0E9, uppercase.
- Value: FD 700, 30px, line-height 30, #F3F0E9; #FF6170 when critical. Suffix ' / {max}': FD 600, 15px, #9CA2AB.
- Bar: 5px tall, full callout width (190). Track rgba(255,255,255,.10). The fill grows from the left to width = hp/max, coloured by state: healthy #E6E2D8, damaged #FFA23A, critical #FF3B4E.
- Status: FD 600, 12px, .14em, uppercase. One colour for the whole line (rules under data_bindings).
- Effect text: FB 400, 12.5px, #9CA2AB, line-height 1.35 (16.9px), margin-top 3. Text-align follows the callout side.
Exact mockup copy:
- HEAD: icon i-head #E6E2D8. '35' + ' / 35'. Bar 100% #E6E2D8. Status 'HEALTHY · SHIELDED' in #E6E2D8. Effect '0 HP = death.'
- TORSO: icon i-torso #FFA23A. '52 / 85'. Bar 61% #FFA23A. Status 'DAMAGED · SHIELDED' in #FFA23A. Effect '0 HP = death. Overflow from destroyed limbs lands here.'
- ARMS: icon i-arms #FF3B4E. '14 / 60', with the 14 in #FF6170. Bar 23% #FF3B4E. Status 'CRITICAL · BLEEDING · SHIELDED' in #FF6170. Effect 'Sway +30 %. At 0: sway +60 %, ADS and reload +30 %.'
- LEGS: icon i-legs #FFA23A. '35 / 70'. Bar 50% #FFA23A. Status 'DAMAGED · HEALING +4/S · OPEN' in #9CF7C8. Effect 'At 0: no sprint or slide, jet thrust −50 %.'
Measured tops: HEAD T=150, TORSO T=262, ARMS T=266, LEGS T=436.

H. SECTION RULE AND HEADING
- Rule: 1px rgba(255,255,255,.09) across the content width, with 16px above and 14px below.
- h2: FD 700, 16px, .18em, #F3F0E9, uppercase. Copy: 'TREAT', 'HALO SHIELD', 'ENERGY & FOOD'.
- The h2 caps sit 20px below the rule; the content below starts 44px below the rule.

I. TREAT CARD
- Padding 10. Background rgba(255,255,255,.04). 1px border rgba(255,255,255,.09). No radius.
- Title row (flex, align centre, gap 8): key cap 22x22 (min-width 22, padding 0 6, FD 700 13px, .04em, #07090D on #F3F0E9, radius 2), then the 20x20 icon tinted #F3F0E9, then the title in FD 700 15px, .1em, #F3F0E9. The key cap sits at card +11,+11 and the title text starts at card +69.
- Description: FB 400, 12.5px, #9CA2AB, line-height 1.35, margin-top 5. Caps of line 1 sit at card +41.
- Ability variant (third card): border rgba(255,140,122,.4); title and icon #FF8C7A; key-cap background #FF8C7A.
Mockup copy:
- [4] i-bandage 'BANDAGE ×2' / '2.5 s. Stops bleeding on the worst bleeding zone. No HP.'
- [5] i-medkit 'MED-STIM ×1' / '4 s. +40 HP split over damaged zones, worst first. Cannot restore a destroyed zone.'
- [E] i-pulse 'SOLACE PULSE' / 'Solace only. Heals allies in 6 m, stops bleeding, revives a destroyed limb to 1 HP.'

J. HALO SHIELD ROW
Halo widget, size 150, in value mode: '72' with sub 'T2 MENDER'. Full drawing spec in the 'Halo widget' entry. At this size it renders:
- Ring radius 42.5px, Mender band 5px, inner twin arc at radius 33.75px.
- Medium weight band at radius 56px.
- Two power-cell pills, 7.5x12.5, at radius 66px; in the still frame at (183,813) and (117,929).
Key/value grid (columns 110px / 1fr, row-gap 5):
- Labels: FD 600, 12px, .14em, uppercase, #9CA2AB, padding-top 2.
- Values: FB 400, 14px, #D7D4CD.
Mockup rows:
- CORE: 'MENDER' (FB 700, #59B3FF) + ' · twin ring · slow passive regen'.
- TIER: tier chip (two bars 6x10 skewed −14°, gap 3, colour #59B3FF) + ' T2 · blue'. The PNG shows the bars grey because of a CSS specificity bug; the intended colour is the tier colour.
- COVERS: 'Head, Torso, Arms · ' + 'LEGS OPEN' (FD 600, 12px, .14em, #646B75).
- SHIELD: '72 / 120 · regen 4/s after 5 s without damage' (FD 500, 14px, tabular).
- WEIGHT: 'MEDIUM · 2 power cells · move speed −5 %'.

K. ENERGY & FOOD (mockup only; dropped in game)
- Each column header row (flex, space-between): a 14px icon, a 6px gap, then the name in FD 700, 14px, .14em, #F3F0E9. On the right, the value in the same font (e.g. '74 / 100'), followed by a trend in #FFA23A.
- Bar: 6px tall, margin-top 6, track rgba(255,255,255,.10), fill #C4BFB5.
- Note: FB 12.5px, #9CA2AB, margin-top 5.
- Copy: ENERGY '74 / 100 ▼▼ −3.0/min', '2 power cells drain it. Below 20: shield regen stops.' FOOD '81 / 100 ▼ −1.5/min', 'Below 20: sprint and jet recharge −25 %.'

STATES: The panel has no hover states of its own (see interactions). Disabled items are drawn at 35% opacity, the common.css btn[disabled] convention. Bevy UI has no group opacity, so multiply the alpha of every BackgroundColor, BorderColor, TextColor and ImageNode.color in the card by .35.

## data_bindings
Source: the locally controlled player (With<Controlled>), using these components:
- Vitals: health.hp/max/dead/bleeding, halo.shield, halo.regen_wait_s, wounds.broken.
- PlayerLoadout.0: halo (HaloSpec: core, tiers, capacity, regen), weight, kit.
- PlayerItems.0: counts, using.
- MatchState.rules: bleeding, injuries, regional_items.
- Res<Data>: items.ron, armor.ron weight_effects / regen, combat.ron broken_arms / broken_legs, weapons.ron spill_to_torso.

TOTAL: Σ ceil(max(hp,0)) / Σ max. The mockup shows '136 / 250' because it uses zone max 35/85/60/70. The game's max is head 45, torso 120, arms 70, legs 85, so 320 when full. Never hard-code the max.

PER ZONE (Zone::ALL; the label comes from Zone::label):
- frac = hp/max.
- State: frac ≤ 0 → DESTROYED; < .35 → CRITICAL; < .75 → DAMAGED; otherwise HEALTHY. This matches widgets.js hpState and the legend '≥ 75 % / 35–74 % / 1–34 %'.
- Value: ceil(hp) while hp > 0, so a living zone never reads 0. The current HUD uses {:.0}.
- Value colour: #FF6170 when critical. When destroyed, '0' in #8A8F98.
- Status line tokens, joined with ' · ':
  - State word.
  - 'BLEEDING' if bleeding.active[z] > bleeding.residual[z].
  - 'TREATING' (replaces the mockup's 'HEALING +4/S') while items.using targets this zone, or targets every zone for a Body-scope item.
  - 'BROKEN' if wounds.broken contains z (only possible when rules.injuries is on).
  - Shield token: 'SHIELDED' if halo.tiers[z] > 0 and shield[z] > 0; 'SHIELD DOWN' if tiers[z] > 0 and shield[z] == 0; 'OPEN' if tiers[z] == 0.
- Status colour priority: TREATING → #9CF7C8; otherwise CRITICAL, BLEEDING or BROKEN → #FF6170; otherwise the state colour (healthy #E6E2D8, damaged #FFA23A, destroyed #8A8F98).
- Effect text, generated from data (the mockup's sway/jet numbers do not exist in the game):
  - HEAD: '0 HP = death.'
  - TORSO: '0 HP = death. Hits on a destroyed limb spill here.'
  - ARMS with injuries on: 'At 0: sway +100 %, ADS time +30 %, recoil +25 %. Hits then spill ×0.6 to the torso.' The numbers come from broken_arms (sway_mult 2.0, ads_time_mult 1.3, recoil_mult 1.25) and spill_to_torso.arms 0.6.
  - LEGS with injuries on: 'At 0: move speed −30 %. Hits then spill ×0.7 to the torso.' (broken_legs.move_mult 0.7, spill .7)
  - Injuries off (TDM): 'At 0: no penalty in this mode. Hits spill ×0.6 to the torso.' Use ×0.7 for legs.
  - When bleeding, append 'Bleeding −{active:.1} HP/s until treated.'
  - When a residual remains after treatment, append 'Residual −{residual:.1} HP/s until respawn.'
- Body widget inputs:
  - fill = frac, state colour.
  - Coverage outline when tiers[z] > 0, in tier_ui_colour(tiers[z]): T1 #EDF1F6, T2 #59B3FF, T3 #C46CFF, T4 #FFCE50. Use these sRGB UI values, NOT render.rs tier_color, which is linear emissive.
  - Outline dashed at 25% opacity when shield[z] == 0.
  - Drips when bleeding; hatch when destroyed.
  - Mint dashed outline while TREATING.

TREAT CARDS, one per PlayerLoadout.kit slot in heal-ring order (slot 1 at the top, then clockwise):
- Key cap: the slot number 1..n.
- Icon: see assets.
- Title: '{ItemSpec.label} ×{PlayerItems.count(i)}'.
- Description generated from ItemSpec. The use time is formatted as '{use_s} s.' (2.0 → '2 s.', 4.5 → '4.5 s.'). Then:
  - Body scope with heal: 'Every region: +{heal_hp} HP' + (stop_bleed ? ', stops bleeding' : '') + '.'
  - Body scope with shield: 'Every arc: +{shield_frac×100} % shield.' Use 'Refills every arc.' when the fraction is 1.0.
  - Region scope: 'One region, picked on the ring: ' + effects. Gauze has no HP, so it reads 'stops bleeding. No HP.', mirroring the mockup.
  - Shipped data gives:
    - TDM kit: TRAUMA KIT ×2 '4.5 s. Every region: +60 HP, stops bleeding.' and HALO CELL ×3 '3.5 s. Refills every arc.'
    - Range kit: GAUZE ×4, DRESSING ×3, ARC PATCH ×3, TRAUMA KIT ×1, HALO CELL ×1.
- Card states:
  - count 0 → disabled (35%).
  - would_help is false for every target → title in #9CA2AB and the line 'Nothing to treat' appended in #646B75.
  - in use (items.using.slot == i) → border #9CF7C8, plus a 3px progress bar inside the card's bottom edge, fill #9CF7C8, width = 1 − left/total. Region items add ' · {ZONE}' to the title.

HALO SHIELD (no core → see 'no data' below):
- Widget:
  - Each arc is drawn in tier_ui_colour(tiers[z]); an arc with tier 0 is unlit.
  - Arc fill = shield[z]/capacity[z].
  - Centre value = round(halo.total()).
  - Sub label: 'T{n} {CORE}' if every lit arc has the same tier, otherwise just '{CORE}'.
  - Weight band from loadout.weight. Cell count from weight_effects[weight].cells (ArmorStats.power_cells).
- CORE row: Core label in the colour of the halo's highest tier, then a short tagline from data. Suggested taglines:
  - Bulwark: 'hex ring · flinch −50 % while shielded'
  - Mender: 'twin ring · fast regen out of combat'
  - Volt: 'spiked ring · shock pulse when an arc breaks'
  - Phase: 'split ring · immune to slows'
  - The mockup says Mender is 'slow passive regen', but armor.ron makes Mender the FASTEST regen: 20/s after 2.5 s.
- TIER row:
  - Uniform tiers: the mockup format '[chip] T2 · blue' (colour names: T1 white, T2 blue, T3 purple, T4 gold).
  - Mixed tiers: four groups 'H [chip] T2', 'T …', 'A …', 'L …', 12px apart. Zone letter in FD 600 12px #9CA2AB; chip and Tn in the tier colour. A zone with tier 0 shows '—' in #646B75.
  - The chip draws n skewed bars for Tn.
- COVERS row: lit zones in title case, comma-separated, then ' · ' and the open zones in caps + ' OPEN' (FD 600 12px #646B75).
- SHIELD row: '{total:.0} / {total_capacity:.0} · regen {rate_per_s}/s after {delay_s} s without damage', using regen[core]. While regen_wait_s > 0, append ' · regen in {ceil} s' in #FFA23A.
- WEIGHT row: '{WEIGHT} · {cells} power cell(s) · move speed {(move−1)×100:+.0} %'. Medium gives −5 % and Heavy −12 %; Light and None give '±0 %'.

NO DATA YET:
- No Vitals replicated, or the player is dead: hide the panel.
- No halo (core None, preset arm_none):
  - Widget drawn with all arcs unlit, no cells, value '0' in #646B75, sub 'NO HALO'.
  - Rows: CORE 'NO HALO'; TIER '—'; COVERS 'NONE · ALL ZONES OPEN'; SHIELD '0 / 0'; WEIGHT 'NONE · 0 power cells · move speed ±0 %'.
- Empty kit: a single line 'No items in this kit.' in FB 12.5px #9CA2AB, in place of the grid.
- Energy and food: no simulation exists. armor.ron has energy_per_min, but nothing consumes it. Omit the section.
- Agent abilities (Solace pulse): no agents yet. Omit the ability card, but keep its coral style for later.

## interactions
OPEN / CLOSE
- Mockup: hold H.
- Game: H already TOGGLES the heal ring (client.rs heal_input). So the panel is visible exactly while control.heal is Some.
- It closes with the ring: H again, Esc, right-click on the first ring, or after a pick (a Body item closes the ring at once; a Region item closes it after the region pick).
- No separate key is needed.
- Optional: also show it while TAB is held, as the mockup comment says ('also inside TAB'), but only if the scoreboard leaves x 48-748 free.
- No open/close animation is specified. Suggest a 120 ms fade, or none.

INPUT
- While the ring is open, the mouse steers the ring pointer, so the panel is display-only: no buttons, no hover.
- Keyboard hint shown: the key cap 'H' in the subtitle.
- The card key caps are the ring slot numbers 1..n. Recommend also letting digits 1-8 pick a heal-ring slot, the same way 1-6 picks a magazine on the magazine radial; then the caps are real hotkeys.

LINKED HIGHLIGHTS WITH THE RING (RingView / HealMenu)
- Hovered item on the first ring: highlight its card with border rgba(255,255,255,.32) and background rgba(255,255,255,.08).
- For a Body-scope item, also preview a static (non-pulsing) #9CF7C8 dashed outline on every zone it would help (would_help per zone).
- On the region ring, the hovered region gets a static #9CF7C8 dashed outline on its body zone, and its callout name turns #9CF7C8. A region where would_help is false gets no preview.
- After the pick, items.using drives the TREATING state:
  - the zone's outline pulses;
  - the status line reads 'TREATING · {left_s:.1} S' in #9CF7C8;
  - the card shows its progress bar.
- Firing, aiming, reloading or sprinting cancels the use (sim rule), and the highlights clear when using becomes None.

ANIMATIONS (from common.css / widgets.js)
- Critical zone fill: opacity 1 → .35 → 1, 1.1 s, ease-in-out, looping.
- Bleed drop: translateY 0 → 10 units (20px at w=200) while opacity goes 1 → 0, 1.2 s, ease-in, looping.
- Treating outline: opacity 1 → .35 → 1, 1.4 s, looping.
- Halo power cells: the whole cell group orbits 360° in 10 s (14 s with 3 cells), linear.
- Halo hit flare and arc shake, broken shard burst, regen shimmer: see the 'Halo widget' entry.

Navigation: none. The panel never takes focus.

## adaptations
1. TRIGGER: the panel shows with the heal ring (H), not on 'Hold H', because H is the heal-ring toggle. Subtitle copy becomes: [H] + ' heal ring · pick an item, then a region' + ' · ' + [RMB] + ' back'. Key caps use the same 18x18 style; 'RMB' grows to width with padding 0 6.
2. Ring overlap. The heal ring is centred at (960,540), radius 120, chips 104x58. The region ring has radius 92 and is centred on the chosen item.
   - Worst case (5-item kit, slot 5 at 288°): the left region chip reaches x ≈ 710, so it overlaps the panel's right 38px around y 480-526.
   - Draw the ring above the panel (higher GlobalZIndex; ring chips are .86 opaque). Or nudge the ring centre to x 1000 while the panel is open.
3. Per-arc halo (DESIGN_DELTAS 2). Every arc has its own tier and shield pool:
   - each body outline uses its own zone's tier colour;
   - each halo arc has its own colour and drains on its own;
   - an arc whose pool is empty shows 'SHIELD DOWN' on its zone, with a dashed outline at 25%;
   - the TIER row lists per-arc chips when the tiers are mixed.
4. Numbers come from data, never from the mockup:
   - zone max 45/120/70/85, not 35/85/60/70;
   - spill: arms ×0.6, legs ×0.7 (the mockup uses ×0.7 for both);
   - broken-limb penalties from combat.ron, and only at 0 HP (the game has no 'critical' penalty);
   - Mender regen 20/s after 2.5 s (the mockup says 4/s after 5 s);
   - move speed from weight_effects.
5. Healing has no heal-over-time. Items apply when their use finishes, so the mockup's 'HEALING +4/S' becomes 'TREATING · n.n S' while an item is in use on that zone.
6. Ruleset gating (MatchState.rules):
   - TDM has no bleeding and no injuries: never show BLEEDING, BROKEN or drips. A limb at 0 shows DESTROYED and the 'no penalty in this mode, spills to torso' effect text.
   - With rules.regional_items off there are no Region cards (the TDM kit has none anyway).
   - The gun range shows everything.
7. TREAT becomes the kit in heal-ring order:
   - key cap = ring slot number;
   - '×count' from PlayerItems;
   - descriptions generated from ItemSpec;
   - one row for kits of 3 or fewer, two rows of 84px for 4-6 (layout gives the shifted y values);
   - drop the Solace ability card until agents exist.
8. Drop ENERGY & FOOD: there is no system, and in the mockup it overflows the panel. Its power-cell information already appears in the WEIGHT row.
9. Mockup bugs to NOT copy:
   - right callouts overflowing the panel by 17px: re-anchor them at x 531-721;
   - the energy section overflowing the bottom edge;
   - the grey tier chip: use the tier colour.
   'LEGS OPEN' rendering in condensed caps came from the same CSS bug, but it is the intended look, so keep it.
10. HP display uses ceil while alive, so a zone at 0.4 HP never reads '0'.
11. Gun-range 'compact HUD readout' and region-ring styling built from these same widgets: see the 'Heal ring + compact vitals (derived)' entry. Nothing is taken from the rejected HUD mockup.

## assets
IMAGES: none from /home/user/sharline/design/ui/mockups/img are used on this screen. No portraits or backgrounds.

ICONS (symbol ids in icons.svg):
- i-head, i-torso, i-arms, i-legs: callout names; 24x24 viewBox, shown at 16px.
- i-bandage, i-medkit, i-pulse: treat cards; 32x32 viewBox, shown at 20px.
- i-energy, i-food: energy and food; shown at 14px; dropped in game.
Adaptations also use i-bleed (bleeding chip/drop) and i-heal.
Item icon mapping (placeholders until art provides 'arc patch' and 'halo cell' glyphs):
- gauze → i-bandage
- field_dressing → i-heal
- trauma_kit → i-medkit
- arc_patch → i-heal tinted #59B3FF
- halo_cell → i-energy tinted #59B3FF
The two new glyphs must come from the local session: design/ and art/ are local-owned, so list them in the PR description.

RASTERISING (Bevy has no SVG): export each symbol as a white-on-transparent PNG at 2x display size (32, 40 or 28px) and tint it with ImageNode.color. i-bandage and i-medkit contain hard-coded #0B0E13 detail (bandage dots, medkit cross). Rasterise that detail as transparent cut-outs so the tint keeps it readable.

WIDGETS: the body silhouette and the halo are procedural SVG (widgets.js bodySVG / haloSVG). Build them as layered white PNG masks tinted per layer (the approach widgets.js itself proposes) or as one UiMaterial each. Masks are listed in the widget entries.

FONTS: Barlow Condensed (500/600/700) and Barlow (400/700) TTFs from Google Fonts (OFL), placed in game/assets/fonts/.

