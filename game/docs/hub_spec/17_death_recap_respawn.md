# Death recap + respawn

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/10_death_recap.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/death.html",
 "/home/user/sharline/design/ui/mockups/death.html",
 "/home/user/sharline/design/ui/mockups/_src/widgets.js"
]

## purpose
Shown while the local player is dead (Vitals.health.dead). It shows:
- who killed you, with their halo and remaining health;
- every hit you took in the last 10 s, split into shield and flesh;
- your own body state at death;
- a respawn countdown with Change Loadout and Scoreboard actions.
It replaces today's centre banner 'ELIMINATED / RESPAWN IN x.x' in hud.rs.

## layout
Full-screen overlay. The in-match HUD is hidden while it is shown.

BACKDROP
- The live 3D view from your death position, desaturated and darkened. The CSS is grayscale(0.85) brightness(0.55).
- In Bevy, put ColorGrading on the view camera while dead: global post_saturation 0.15, exposure about -0.86 EV.
- Fallback: a full-screen rgba(0,0,0,0.45) node.
- On top, a vignette node with BackgroundGradient Radial, ellipse at centre, farthest-corner (Ellipse(px 1357.6, px 763.7)). Stops: rgba(0,0,0,0) at 35%, rgba(0,0,0,0.7) at 100%.

REGIONS (absolute, 1920x1080)
A. TITLE: anchored top-left, left 96, top 96 (w 369, h 122).
   - Kicker 'ELIMINATED' y96 h24.
   - Name y120 h72.
   - Sub-line y198 h20 (margin-top 6).

B. KILLER PANEL: left 96, top 300, 560 x 195 (x 96-656, y 300-495).
   - Padding 18 top/bottom, 20 left/right.
   - Left border 3px --enemy, other borders 1px --stroke.
   - h2 at x119, y319, h22.
   - Body row at y353 (margin-top 12), flex, align centre, gap 18:
     - Halo widget 120x120 at x119, y353.
     - Key/value grid at x257: label column 110 wide, value column 208 wide (to x575), row-gap 7.
     - Rows at y353.5 (h22, because of the 18 px name), 382.5, 407.5, 432.5, 457.5 (h18 each).

C. DAMAGE PANEL: left 700, top 300, 720 x 265.5 (x 700-1420).
   - h2 at x721, y319, h22, with its micro suffix at x902.2, y326.
   - Table at x721, y351, width 678, margin-top 10.
     - Header row h22.5.
     - Data rows h36 at y373.5 / 409.5 / 445.5 / 481.5, each with a 1px top border --stroke.
     - Fixed column x/widths (the HTML was auto, use these): TIME 721/71.4, FROM 792.4/71, WEAPON 863.4/97.3, ZONE 960.8/164.5, SHIELD 1125.2/124.8, FLESH 1250/149.
     - Cell padding 0 8, text vertically centred.
   - Footer line at y529.5, h17 (margin-top 12): two spans with gap 24, at x721 and x889.4.

D. YOU PANEL: left 1460, top 300, 360 x 313 (x 1460-1820).
   - Padding 18/20, column, items centred.
   - h2 at x1481, y319, left-aligned (align-self flex-start).
   - Body silhouette 120x240 at x1580, y351 (margin-top 10), horizontally centred.

E. RESPAWN BLOCK: centred horizontally, bottom 110 (y 860-970), x 679.8-1240.3 (w 560.5), flex row, align centre, gap 26.
   - Ring box 110x110 at x679.8.
   - Text column at x815.8:
     - Title y862.5 (h34 including the sub-line block).
     - Sub-line y896.5 h17.
     - Button row y923.5 h44, margin-top 10, gap 10:
       - CHANGE LOADOUT button x815.8 w221.8 (keycap at x838.8, y934.5).
       - SCOREBOARD button x1047.6 w192.7 (keycap at x1070.6).

## elements
TITLE
- Kicker 'ELIMINATED': BC 700 20px, .24em (4.8px), --enemy #FF4D5A.
- Name 'BY ROOK': BC 700 72px, .08em (5.76px), line-height 72, --text-hi.
- Sub-line: Barlow 400 17px, --text #D7D4CD, copy 'VK-50 Warden · 21 m · headshot through a T2 shield'.

KILLER PANEL (.panel.hi with 3px --enemy left border)
- h2 'KILLER': BC 700 18px, .18em (3.24px), --text-hi.
- Key labels: BC 600 12.5px, .14em (1.75px), --text-mid, uppercase, padding-top 2. Copy: 'PLAYER', 'WEAPON', 'HALO', 'SHIELD LEFT', 'HP LEFT'.
- Values (14.5px):
  - PLAYER: 'ROOK' in BC 700 18px --enemy, then ' · Kestrel' in Barlow 400 14.5 --text.
  - WEAPON: Barlow 400 'VK-50 Warden · sniper 8× · bipod'.
  - HALO: 'T3 Bulwark' in Barlow 700 14.5 tier colour (--t3 #C46CFF), then ' · Heavy · Head + Torso' in Barlow 400 --text.
  - SHIELD LEFT: num (BC 500 14.5) '121 / 195 (you hit it for 74)'.
  - HP LEFT: num 'Arms 31 / 60 · rest full'.
- HALO WIDGET 120x120 (haloSVG, 1:1 viewBox 120, centre 60,60):
  - Arcs at radius 34. Centres: head -90° (top), legs 0° (right), torso 90° (bottom), arms 180° (left). Each spans ±39°.
  - Band width by core: Bulwark 8 (hexagonal ring path), Mender 4 (plus an inner arc at r27, width 2.4, opacity 0.8), Volt 6 (plus 3 outward 6 px ticks per arc), Phase 5 (torso arc split with a 16° gap).
  - Lit arc: tier colour, opacity 0.85, plus a blurred glow of width band+3 at opacity 0.35.
  - Unlit arc: #27272C plus a 1 px white line at 13%.
  - Remaining shield: the clockwise tail of each lit arc, past the fraction left, is overdrawn with #0B0E13 at 0.62.
  - Weight band:
    - Medium: circle r45, #3A3F47, 3 px, plus a tier-colour 1 px circle at 0.25.
    - Heavy: circle r46, #3A3F47, 7 px, dashed 14/3, plus a tier-colour 1 px circle at 0.3.
    - Light: none.
  - Power cells: 6x10 rounded (rx 3) pills at r53 in tier colour, opacity 0.95, starting at -60° and evenly spaced. They orbit 360° in 10 s (14 s for 3 cells).
  - Centre text: shield value, BC 700 21px --text-hi, baseline y62. Below it '{T3} {BULWARK}' in BC 600 8px, letter-spacing 1.2px, tier colour, baseline y73.

DAMAGE PANEL (.panel.hi)
- h2 'DAMAGE YOU TOOK' (BC 700 18px .18em --text-hi), then .micro 'LAST 10 S · NEWEST FIRST' with margin-left 8.
- Table header: BC 600 12px, .16em (1.92px), --text-mid, uppercase, left-aligned, padding 4 8. Copy: TIME / FROM / WEAPON / ZONE / SHIELD / FLESH.
- Cell styles (14.5px):
  - TIME: num BC 500 --text, '−0.0 s'.
  - FROM: BC 700 .04em in the attacker's team colour, '--enemy' for enemies ('ROOK').
  - WEAPON: Barlow 400 --text, 'Warden'.
  - ZONE: Barlow 400 --text, 'TORSO'. The killing hit's zone is BC 700 .04em --text-hi ('HEAD').
  - SHIELD: BC 700 --t2 #59B3FF, '−30 · broken' or '−42'. When the zone had no shield, 'open' in Barlow 400 --text-low.
  - FLESH: BC 700 #FF6170, '−35 · destroyed', '−22', '−79 · bleeding', or '—' for none.
- Mockup rows (newest first):
  - '−0.0 s | ROOK | Warden | HEAD | −30 · broken | −35 · destroyed'
  - '−2.4 s | PIKE | Mako | TORSO | −42 | —'
  - '−2.6 s | PIKE | Mako | LEGS | open | −22'
  - '−6.1 s | MOTH | UGL-40 | ARMS + TORSO | −48 | −79 · bleeding'
- Footer: Barlow 400 14px --text-mid.
  - 'Total ' + '120 shield' (BC 700 --t2) + ' · ' + '136 flesh' (BC 700 #FF6170).
  - 'You dealt ' + '74' (BC 700 --text-hi) + ' to Rook, ' + '61' (BC 700 --text-hi) + ' to Pike'.

YOU PANEL (.panel.hi)
- h2 'YOU'.
- BODY SILHOUETTE 120x240 (bodySVG, viewBox 100x200 scaled 1.2). Zone polygons in viewBox units:
  - head M42 4H58L64 12V26L58 34H42L36 26V12Z
  - torso M33 39H67L72 47L68 100H32L28 47Z
  - arms M25 41L18 44L9 107L17 110L27 64Z and M75 41L82 44L91 107L83 110L73 64Z
  - legs M32 104H49L48 195H35Z and M51 104H68L65 195H52Z
- Base fill #2A2D33, stroke #0B0E13 1.5.
- HP fill rises from the bottom of each zone's y-range (head 4-34, torso 39-100, arms 41-110, legs 104-195) in proportion to hp/max. In Bevy use a clipping parent of that height anchored at the bottom.
- Fill colour by fraction:
  - >= 0.75: --hp-ok #E6E2D8
  - >= 0.35: --hp-dmg #FFA23A
  - > 0: --hp-crit #FF3B4E, pulsing opacity 1 -> 0.35 over 1.1 s
  - = 0: dead hatch, #15171B with #FF3B4E stripes 1.4 wide every 5 units at 45° (opacity 0.55), and stroke #FF3B4E 1.6
- Shield coverage outline under the zones, per covered zone: tier colour stroke 4.2 plus a glow stroke 6 at 0.55 opacity (blur 2.2). A broken arc is drawn at 0.25 opacity and dashed 4/3.
- Mockup state: head 0 (hatched), torso 0.61 (orange), arms 0.23 (red), legs 0.69 (orange). Head, torso and arms are covered in T2, all broken.

RESPAWN BLOCK
- RING (110 box): the circle Node is 106x106, centred, with a 6 px border.
  - Remaining fraction in --text-hi #F3F0E9, track rgba(255,255,255,0.15), starting at 12 o'clock clockwise. The mockup shows 0.75 = 3 of 4 s.
  - Centre number: BC 700 48px --text-hi, tabular, '3'.
- Title: BC 700 28px, .14em (3.92px), --text-hi, 'RESPAWN IN 3 S'.
- Sub-line: BC 600 14px, .16em (2.24px), --text-mid, 'WEST HOUSE · SPAWN PROTECTION 2 S'.
- Buttons (.btn):
  - [solid keycap 'L'] 'CHANGE LOADOUT'.
  - [solid keycap 'TAB'] 'SCOREBOARD'.

## data_bindings
SNAPSHOTS
- Take the recap snapshot on the frame Vitals.health.dead turns true. Freeze it and hide it when dead turns false (respawned).

TITLE
- Name: 'BY ' + killer PlayerInfo.name uppercased, from the KillFeed whose victim == my PlayerId.
- killer None -> name 'BY YOURSELF', kicker unchanged, and hide the KILLER panel.
- Sub-line: '{killer weapon name from weapons.ron} · {range m, integer} m · {zone phrase} {shield phrase}'.
  - Zone phrase: Head 'headshot', Torso 'torso shot', Arms 'arm shot', Legs 'leg shot'.
  - Shield phrase: 'through a T{n} shield' if the killing hit damaged that arc; 'T{n} arc already down' if the arc was at 0; 'no shield there' if that arc's tier is 0.
  - Use my Loadout.halo.tiers[zone] for n.

KILLER PANEL
- Halo widget: killer's PlayerLoadout.halo (core, per-arc tiers, coverage) and weight. Their Vitals.halo shield per arc gives the fraction; the centre value is round(total shield). Each arc uses its OWN tier colour (DESIGN_DELTAS 2).
- PLAYER: name; the part after ' · ' is the agent (not in game) -> show ' · {kills} / {deaths}' from their Score instead.
- WEAPON: '{weapon name} · {ammo label of the killing round, e.g. AP II} · {attachment display names, excluding defaults}'.
- HALO: '{tier label} {Core}' in the colour of the highest tier, then ' · {WeightClass} · {covered zones joined with ' + '}' ('Head + Torso').
- SHIELD LEFT: '{round total shield} / {round total capacity}' + ' (you hit it for {my shield damage to them this life})'. Omit the parenthesis if 0.
- HP LEFT: the zones below max as '{Zone} {hp} / {max}', joined with ' · ', then ' · rest full' if any zone is full. All full -> 'Full'.

DAMAGE TABLE
- A client-side ring buffer of incoming hits from the last 10 s before death, newest first.
- TIME = hit time minus death time, 1 dp.
- WEAPON = short weapon name ('Mako', 'Warden', 'SMG name'). Adaptation: append the round's ammo when not Standard, e.g. 'Warden · AP II'.
- SHIELD = round(absorbed); add ' · broken' if the arc broke. 'open' if tier 0 or the arc was already down.
- FLESH = round(HP lost, including spill); add ' · destroyed' if the zone reached 0. Add ' · bleeding' only when the ruleset has bleeding and the hit started a bleed (never in TDM).
- Footer totals: sum of shield and flesh over the shown window. 'You dealt' lists my outgoing damage (shield + flesh) this life per victim, top 3, descending. None -> 'You dealt no damage'.

YOU PANEL
- My Vitals.health (hp, max) at death; my Loadout.halo tiers per zone; broken = my Vitals.halo.shield[zone] == 0.

RESPAWN
- Ring fraction = Vitals.respawn_s / rules.tdm.respawn_s (4.0). Number and title = ceil(respawn_s).
- Sub-line: '{SIDE} · SPAWN PROTECTION {rules.tdm.spawn_protection_s} S'. The value is 1.5 today: print an integer when whole, else 1 dp.
  - SIDE: Showhome team A 'WEST SIDE', team B 'EAST SIDE'; Range 'RANGE'. The host picks the exact spawn at respawn time, so the mockup's 'WEST HOUSE' is not known in advance.
- MatchPhase::Ended: hide the respawn block (the match-end banner takes over).

## interactions
- Appears immediately on death, with a 150 ms fade in (not in the mockup; there is no kill-cam).
- Cursor unlocked while it is shown; re-locked on respawn unless another menu is open.
- L key or a click on CHANGE LOADOUT: open the Loadout hub as an overlay. The change applies at next spawn. The respawn timer keeps running; if it hits 0 while the loadout screen is open, the player still respawns, and the loadout overlay stays open with movement input zeroed.
- Hold Tab or click SCOREBOARD: show the scoreboard over this screen while held. A click toggles it.
- Esc: ESC menu (it covers the recap).
- No other input is read while dead.

## adaptations
1. NETWORK DATA NEEDED (the game sends too little today):
   - Extend DamageTaken (host -> victim) with: attacker id, weapon index, ammo choice, absorbed, hp lost (incl. spill) and the spill zone, shield_broke, zone_destroyed, bleed_added, range_m. Keep `from` for the hit-direction chevrons.
   - Extend HitConfirm (host -> shooter) with absorbed and hp, for 'You dealt' and 'you hit it for'.
   - Extend KillFeed, or send a victim-only DeathRecap message, with weapon, ammo of the killing round, range_m, zone and arc state.
   The host already has all of this in HitReport.

2. ROW MERGING (fast guns would flood the table):
   - Merge consecutive hits from the same attacker + weapon + ammo + zone within 1.0 s into one row, showing the zone as 'TORSO ×3'.
   - Show at most 6 rows. If there are more, the last row reads '+{n} older hits' in .micro.
   - The panel height grows by 36 per row (6 rows -> panel ends at about y=637, still clear of the respawn block at 860).

3. SPILL: when limb damage spilled to the torso, the ZONE cell reads 'LEGS → TORSO' (replaces the mockup's grenade-splash 'ARMS + TORSO'; there are no explosives yet).

4. PER-ARC TIERS: the halo widget and the body outlines colour each arc or zone by its own tier, not one ring colour.

5. NO AGENTS YET: 'Kestrel' becomes the K/D. The mockup's '8×' optic text becomes the attachment display name. attachments.ron has no display names: add a `name` field (e.g. 'Sniper 6-12×', 'Bipod') or derive one.

6. MAGAZINE STRIP (user direction, not in the mockup):
   - Under the body in the YOU panel, margin-top 12: the ESC-menu magazine chips in slot order.
   - The magazine that was in the gun at death is highlighted: 1px --text-hi border, bg rgba(243,240,233,0.10).
   - Preceded by .micro 'IN GUN AT DEATH' on its own line.
   - No round counts. The YOU panel grows to about 360 tall.

7. TDM RULES: no bleeding or broken suffixes, because the TDM ruleset disables status effects. ' · destroyed' still shows.

## assets
No images or icons.svg symbols.

Generated widgets to rasterise or draw:
- Halo: per-core white arc masks per zone, weight-band rings, cell pill. Tint with ImageNode.color, or use a UiMaterial.
- Body: 4 zone fill masks plus 4 outline masks (solid and dashed) and the hatch texture, as white PNGs at 2x (240x480 canvas).

Rings use the conic BorderGradient.

The backdrop is the live view (mockup stand-in: /home/user/sharline/design/ui/mockups/img/hud_street.jpg, filtered).

