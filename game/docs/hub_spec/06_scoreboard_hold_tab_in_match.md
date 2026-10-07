# Scoreboard (hold TAB, in match)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/07_scoreboard.png",
 "/home/user/sharline/design/ui/mockups/scoreboard.html (built from _src/pages/hud.html with body data-variant=\"tab\")",
 "/home/user/sharline/design/ui/mockups/_src/pages/hud.html (CSS lines 140-170: .tab/.sb/.sbt/.sb-foot/.sb-hint; markup lines 374-404)",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg"
]

## purpose
A full-screen overlay shown while TAB is held during a match. It gives the mode, map, score target, time left and host; the team score; one row per player with agent, name, halo (tier + weight), K / D / A, score, shield damage, flesh damage, headshot % and ping, with your team on top; and four personal stat cards (accuracy, hits by zone, shields broken, server). It replaces today's text-only scoreboard in hud.rs (ScoreboardText). Only the overlay is specified here. The in-match HUD visible underneath in the PNG (minimap, vitals panel, weapon panel, hotbar, status chips, crosshair) and the street backdrop are NOT part of this spec: the backdrop stands in for the live 3D view, and the HUD mockup is not wanted.

## layout
Canvas 1920x1080, UiScale = window_height / 1080.
1. DIM LAYER: full screen (inset 0), background rgba(4,6,9,.62), drawn above the 3D view and the HUD. While it is shown, HIDE the HUD's top-centre score/timer and score progress, the compass, the kill feed, hit markers, damage-direction arrows, world nameplates, the kill banner and interaction prompts. Other HUD panels may stay under the dim.
2. BOARD (.sb): CENTRED horizontally. Width 1240 (x 340..1580), top 120. A flex column:
   a) HEAD: y 120..191. Flex row, space-between, align flex-end, padding-bottom 12, bottom border 1px --stroke-mid rgba(255,255,255,.16) at y 190. Title block at the left (x 340); team score at the right (right edge 1580, digits y ~131..177).
   b) TABLE: margin-top 14, so it starts at y 204.
      - Column header row: y 204..225, about 21 tall.
      - Each player row is 44 tall: a 2px top separator rgba(4,6,9,.60) plus 42 of content.
      - Top block (your team) row tops: y 225, 269, 313, 357, 401 (ends 445).
      - Then a 14px gap (445..459) with no background.
      - Bottom block (other team) row tops: y 459, 503, 547, 591, 635 (ends 679).
      - With fewer players a block simply has fewer rows; there are no placeholder rows.
   c) FOOTER: margin-top 18, so y 697..~786. Flex row with gap 12 and four equal cards, each 301 wide: x 340..641, 653..954, 966..1267, 1279..1580. Each card is about 89 tall.
3. HINT ROW: CENTRED horizontally, anchored BOTTOM 28 (y 1030..1052). Flex row with gap 18.

TABLE COLUMN GEOMETRY (use one Grid per row so the header and every row line up; widths include the 12px left/right cell padding):
| # | Column | x range | Width | Align |
|---|---|---|---|---|
| 1 | agent badge | 340..396 | 56 | centred |
| 2 | PLAYER | 396..674 | 278 (flex 1fr) | left; text starts at x 408 |
| 3 | HALO | 674..814 | 140 | right; content ends at x 802 |
| 4 | K | 814..884 | 70 | right |
| 5 | D | 884..939 | 55 | right |
| 6 | A | 939..995 | 56 | right |
| 7 | SCORE | 995..1101 | 106 | right |
| 8 | SHIELD DMG | 1101..1256 | 155 | right |
| 9 | FLESH DMG | 1256..1402 | 146 | right |
| 10 | HS % | 1402..1493 | 91 | right |
| 11 | PING | 1493..1580 | 87 | right |
Value right edges measured in the PNG: 802, 872, 927, 982, 1089, 1244, 1390, 1481, 1567, which is the cell right edge minus 12.

## elements
TOKENS: --stroke-mid rgba(255,255,255,.16); --stroke-hi rgba(255,255,255,.32); --text-hi #F3F0E9; --text-mid #9CA2AB; --text-low #646B75; --teal #00DACE; --coral #FF8C7A; --t1 #EDF1F6; --t2 #59B3FF; --t3 #C46CFF; --t4 #FFCE50; --ally #52E5A5; --enemy #FF4D5A; --panel rgba(9,12,17,.70); --stroke rgba(255,255,255,.09).
FONTS: fd = Barlow Condensed and fb = Barlow. tnum = tabular numerals. Letter-spacing is in em (Bevy LetterSpacing::Rem), with px in brackets.

HEAD
- Title 'TEAM DEATHMATCH': fd 700 34px, letter-spacing .08em (2.72px), --text-hi (x 340..608).
- Subtitle, a block directly under the title: 'SHOWHOME (placeholder) · FIRST TO 50 · 06:41 LEFT · HOST: ASH' in fd 600 13px, letter-spacing .2em (2.6px), --text-mid. It is NOT forced uppercase; the parts are uppercase except '(placeholder)'.
- Team score: a flex row, align centre, gap 16, fd 700 48px, tnum. Your team's score is in --ally ('32'). Then 'VS' in fd 700 16px, letter-spacing .2em (3.2px), --text-mid. Then the other team's score in --enemy ('28').

COLUMN HEADER ROW
- Labels: fd 600 12px, letter-spacing .16em (1.92px), --text-mid, UPPER, padding 0 12 6, right-aligned except PLAYER (left). Copy: '' (agent column), 'PLAYER', 'HALO', 'K', 'D', 'A', 'SCORE', 'SHIELD DMG', 'FLESH DMG', 'HS %', 'PING'. No background.

PLAYER ROW
- Height 44, of which the top 2px is a separator in rgba(4,6,9,.60). Cell padding 0 12.
- Cell text: fd 600 19px, --text-hi, tnum for numbers.
- Backgrounds (full row width):
  - Your team: rgba(82,229,165,.12).
  - Other team: rgba(255,77,90,.11).
  - Your own row: rgba(82,229,165,.26).
- Left accent: a 3px inset bar at the row's left edge (x 340..343) in --ally for your team or --enemy for the other team.
- DEAD row: all cell text --text-mid, agent badge opacity .45. The halo chip keeps its colours.
- Agent badge: a 30x30 hexagon (points top and bottom), filled --teal for Kestrel or --coral for Solace, with the agent initial 'K' / 'S' centred in fd 700 14px, colour #0B0E13.
- PLAYER cell: a flex row, align centre, gap 8.
  - Name in fd 600 19px --text-hi, UPPER.
  - Optional tag in fd 600 12px, letter-spacing .14em (1.68px), --text-mid, UPPER:
    - '· YOU' on your own row.
    - On the host's row, the i-crown icon (14x14, --t4 #FFCE50) followed by 'HOST'.
    - '· RESPAWN 3 S' on a dead player.
- HALO cell (right-aligned): the tier chip (pips 6x10, skewed -14 degrees, gap 3, tier colour), a ~5px gap, then the weight squares (three 7x7 with gap 2; lit --text-hi, unlit rgba(255,255,255,.20)). See the adaptations for per-arc pips.
- K / D / A / SCORE / SHIELD DMG / FLESH DMG / HS %: integers, right-aligned. Use a thousands separator ',' for values >= 1000 ('1,240').
- PING: fd 600 16px, --text-mid, right-aligned.
- Mockup rows. Top block (ally):
  | Badge | Name and tag | Halo | K | D | A | Score | Shield | Flesh | HS% | Ping | Row style |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | K | KESTREL_YOU · YOU | T2, 2 lit | 11 | 6 | 3 | 1,240 | 1,380 | 1,020 | 27 | 34 | me |
  | S | ASH (crown) HOST | T3, 3 lit | 8 | 5 | 9 | 1,105 | 980 | 760 | 18 | 0 | |
  | K | JUNO | T1, 1 lit | 7 | 7 | 2 | 820 | 890 | 640 | 22 | 41 | |
  | S | DACE | T2, 2 lit | 4 | 6 | 7 | 610 | 520 | 430 | 12 | 58 | |
  | K | KIT · RESPAWN 3 S | T4, 3 lit | 2 | 4 | 1 | 300 | 410 | 220 | 9 | 72 | dead |
  Bottom block (enemy):
  | Badge | Name and tag | Halo | K | D | A | Score | Shield | Flesh | HS% | Ping | Row style |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | K | PIKE | T3, 3 lit | 10 | 7 | 2 | 1,150 | 1,240 | 900 | 31 | 45 | |
  | K | ROOK | T3, 3 lit | 7 | 8 | 3 | 890 | 1,010 | 700 | 24 | 38 | |
  | S | MOTH | T2, 1 lit | 6 | 6 | 8 | 840 | 720 | 610 | 15 | 52 | |
  | S | VESPER · RESPAWN 2 S | T1, 1 lit | 3 | 7 | 5 | 450 | 380 | 300 | 11 | 66 | dead |
  | K | BRANN | T4, 3 lit | 2 | 4 | 1 | 260 | 300 | 190 | 8 | 90 | |

FOOTER CARDS (.panel: background --panel rgba(9,12,17,.70), 1px --stroke border, radius 2, padding 12 14)
- Label (.lbl): fd 600 13px, letter-spacing .14em (1.82px), --text-mid, UPPER, block.
- Big value: fd 700 28px, --text-hi, tnum.
- Micro: fd 600 11px, letter-spacing .16em (1.76px), --text-low, UPPER.
- Card 1: 'YOUR ACCURACY' / '31 %' / '212 SHOTS · 66 HITS'.
- Card 2: 'HITS BY ZONE (YOU DEALT)', then a flex row (gap 14, margin-top 6, fd 700 18px, --text-hi): 'H 18', 'T 31', 'A 9', 'L 8'. Each is a letter + space + number (tnum). No micro line.
- Card 3: 'SHIELDS BROKEN' / '7' / 'MOST: T3 BULWARK (PIKE)'.
- Card 4: 'SERVER' / '60 Hz · 34 ms' (big value at 22px, margin-top 4, NOT uppercased) / 'LISTEN SERVER · JOIN CODE SHRD-4K7Q'.

HINT ROW
- Each hint: a flex row, gap 6, fd 600 13px, letter-spacing .14em (1.82px), --text-mid, UPPER, preceded by a GHOST key cap: min-width 22, height 22, padding 0 6, transparent background, 1px border --stroke-hi, text --text-hi, fd 700 13px, letter-spacing .04em, radius 2.
- Copy: [TAB] 'HOLD TO VIEW', then [RMB] 'UNLOCK CURSOR (MUTE / REPORT)'.

## data_bindings
EXISTING DATA
- MatchState (replicated):
  - mode: Tdm -> 'TEAM DEATHMATCH', Range -> 'GUN RANGE'.
  - map: display name 'SHOWHOME'. Drop '(placeholder)'.
  - score_limit -> 'FIRST TO {n}'.
  - time_left_s -> '{mm:ss} LEFT', zero-padded ('06:41').
  - score_a / score_b: the left score is the local player's team's score (--ally), the right is the other team's (--enemy).
- Host name: PlayerInfo.name of PlayerId(0) -> 'HOST: {NAME}'.
- Rows: every entity with PlayerInfo + Score.
  - Grouping: PlayerInfo.team; your team is the TOP block.
  - Sorting: by SCORE descending, then kills descending, then deaths ascending. Until the score stat exists, sort by kills, which is what hud.rs does today.
- K / D: Score.kills / Score.deaths.
- Dead state + '· RESPAWN {ceil(respawn_s)} S': Vitals.health.dead and Vitals.respawn_s (already replicated).
- HALO: PlayerLoadout armor arc tiers + WeightClass (as in the lobby).
- '· YOU': the Controlled player.
- Crown + 'HOST': PlayerId(0).

NEW STATS NEEDED (host-authoritative). Extend Score, or add a replicated MatchStats component:
- assists: u16. Damage dealt to a victim within N s before another player kills them; the window goes in data.
- score: u32. Formula in rules.ron, e.g. score: (kill: 100, assist: 50, ...). The mockup numbers are illustrative.
- shield_dmg: u32 (damage absorbed by enemy halo arcs).
- flesh_dmg: u32 (zone HP removed).
- hits and head_hits: u32. HS % = round(100 * head_hits / hits), or '0' when hits = 0.
- PING: replicated PlayerNet.ping_ms (shared with the lobby). The host shows '0', as the mockup does for ASH.

FOOTER (local player only; mostly computable on the client)
- ACCURACY: shots = trigger pulls that fired a round (count each shotgun shot once); hits = shots with at least one HitConfirm. Show '{round(100*hits/shots)} %' and '{shots} SHOTS · {hits} HITS'. With 0 shots: '-- %' and '0 SHOTS · 0 HITS'.
- HITS BY ZONE: count of HitConfirm per Zone (Head/Torso/Arms/Legs) -> H/T/A/L.
- SHIELDS BROKEN: count of HitConfirm.shield_broke. Micro 'MOST: T{tier} {CORE} ({VICTIM})' names the highest arc tier you broke this match (ties go to the most recent). Get the tier from the victim's PlayerLoadout arc for that zone and the core from the armor preset. With none: big '0', micro 'NONE YET'.
- SERVER: big '{net.tick_hz} Hz · {your ping} ms'; on the host, '{tick_hz} Hz · HOST'. Micro 'LISTEN SERVER · JOIN CODE {code}' from Session.join_code, or the code or address the client joined with.
- Reset all stats when a match starts.

## interactions
- Show while TAB is held (keys.pressed(KeyCode::Tab)) and hide on release.
- It does not pause the game. Movement and firing continue.
- It does NOT open on Esc. Today hud.rs shows the board when control.paused; Esc gets the separate ESC menu (mockup 09).
- RMB while the board is shown unlocks the cursor instead of aiming down sights, so the player can click a row. This is the hint 'UNLOCK CURSOR (MUTE / REPORT)'.
  - With the cursor unlocked, hovering a row gives it a 1px --stroke-hi outline. Clicking it opens a small menu in the lobby context-menu style: 'MUTE CHAT' and 'REPORT' (REPORT disabled, opacity .35, until it exists).
  - Releasing TAB re-locks the cursor and closes the menu.
  - Until in-match chat or mute exists, omit the RMB hint and the behaviour. Show only '[TAB] HOLD TO VIEW'.
- Updates live, each frame or when the data changes: the timer, scores, respawn countdowns, stats and ping.
- Optional, matching the ended phase: at MatchPhase::Ended, show the board pinned (no TAB needed). The title becomes 'VICTORY' (--ally), 'DEFEAT' (--enemy) or 'DRAW' (--text-hi), and the subtitle becomes 'SHOWHOME · FINAL {a} - {b} · RETURNING TO LOBBY IN {n} S'. The death recap screen (mockup 10) links here with a 'TAB SCOREBOARD' button.

## adaptations
1. HALO COLUMN, PER-ARC TIERS: use the same 4-pip H/T/A/L chip as the lobby. Each pip is in its arc's tier colour; tier-0 arcs are --unlit #27272C with a 1px rgba(255,255,255,.13) outline. Follow it with the weight squares from WeightClass. Halo tier and weight are public, being visible on the in-world halo. Exact shield values are NOT shown (README: exact enemy halo values only after a scan).
2. AGENT BADGE: agents are not in the game yet. Show 'K' on --teal for everyone until LoadoutChoice carries an agent; then K/--teal for Kestrel and S/--coral for Solace.
3. RELATIVE TEAM COLOURS: your team is always --ally on top and the enemy is --enemy below. This replaces hud.rs's 'TEAM TEAL' / 'TEAM CORAL' text blocks and the teal/coral team colours in the UI.
4. GUN RANGE (MatchMode::Range, no teams):
   - Title 'GUN RANGE'. Subtitle '{MAP} · FREE PRACTICE · HOST: {NAME}'.
   - Hide the team score and the gap row.
   - Show all players in one block with neutral rows: background rgba(255,255,255,.035), no accent bar, your own row rgba(82,229,165,.26).
   - Keep the footer cards; accuracy and hits by zone are the useful aim-training readout there.
5. NO AMMO INFORMATION anywhere on the board, per the genre rule. Never show magazines, ammo type or counts for anyone. The 6-slot magazine order and the gear budget belong to the lobby and loadout, not here.
6. COLUMNS WITHOUT DATA: until the new stats exist, show the A, SCORE, SHIELD DMG, FLESH DMG and HS % cells as '–' in --text-low. Keep the columns so the layout matches the mockup.
7. JOIN CODE: the old board printed 'JOIN CODE ...' at the top. It now lives only in the SERVER card micro. Its format is ours (XXXX-XXXX-XX), not 'SHRD-4K7Q'.
8. HUD BEHIND: only the hide list in the layout applies. Do not build the mockup HUD; the user rejected that mockup.

## assets
- IMAGES: none. The street picture behind the board in 07_scoreboard.png is /home/user/sharline/design/ui/mockups/img/hud_street.jpg standing in for the live game view. Do not draw it.
- ICONS (from /home/user/sharline/design/ui/mockups/_src/icons.svg, rasterised white PNG at 2x and tinted): i-crown (14x14, --t4) for the host tag.
- GENERATED SHAPES:
  - A hexagon mask/shape for the 30x30 agent badges: a UiMaterial SDF hex, or a 60x60 white hex PNG tinted --teal/--coral with a centred Text initial.
  - The tier pip parallelogram (16x20 white PNG shown at 8x10), shared with the lobby.
  - Key caps are plain Nodes (border + text); no image needed.
- FONTS: Barlow Condensed 600/700 (all board text is condensed). Bundle it under game/assets/fonts/ as for the lobby.

