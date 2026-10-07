# ESC menu (in match): host and client variants

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/09_esc_menu.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/esc_menu.html",
 "/home/user/sharline/design/ui/mockups/esc_menu.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css"
]

## purpose
The in-match pause menu opened with Esc. The match keeps running (it is a listen server), and the menu says so. On the left is a big text menu: Resume / Loadout / Settings / Controls. Below that is a host-only group (Players, Restart match, Back to lobby) and a danger row (Stop hosting for the host, Leave match for clients). On the right is a match-info card: mode and map, live score and clock, join code, player count, server, ping, and your loadout. It replaces today's PauseRoot (the 'PAUSED' title, scoreboard text and two white buttons) in game/crates/val_etf/src/hud.rs.

## layout
Full-screen overlay, drawn above the in-match HUD (hide the HUD while the menu is open).

1. BACKDROP: the live game view, plus a full-screen dim node with BackgroundGradient linear TO_RIGHT and stops:
   - rgba(5,7,10,0.94) at 0%
   - rgba(5,7,10,0.86) at 36% (x=691)
   - rgba(5,7,10,0.55) at 100%
   The left side is the darkest, under the menu.

2. LIVE INDICATOR: anchored top-left, left 96, top 72, a row 334x16 with gap 10.
   - Dot: 10x10 circle at (96,75).
   - Label starts at x=116.

3. MENU COLUMN: anchored top-left, left 96, top 150, width 460 (right edge x=556), a column. Row boxes (x=96, w=460):
   - RESUME y150 h60
   - LOADOUT y210 h60
   - SETTINGS y270 h60
   - CONTROLS y330 h60
   - Host group: margin-top 22, then a 1px top border --stroke at y=412 spanning x96-556, then padding-top 14.
     - Group label at x=118, y=427, h13, with margin-bottom 4.
     - PLAYERS y444 h46
     - RESTART MATCH y490 h46
     - BACK TO LOBBY y536 h46
   - Danger group: 1px top border --stroke at y=604, padding-top 14; STOP HOSTING y619 h46.
   - The menu column ends at y=665.
   - Each row is flex row, space-between, align centre, padding-left 22, so the label text starts at x=118. The right-hand hint is right-aligned to x=556.

4. INFO CARD: anchored top-right, right 96, top 150 (x 1264-1824), width 560, height 293 (content-driven), padding 22 top/bottom and 24 left/right; inner content x 1289-1799 (510 wide).
   - Title h2 at y173, h24.
   - Score row at y207, h56 (margin-top 10).
   - Key/value grid at y279 (margin-top 16): column 1 = 150 px at x1289, column 2 at x1439 (360 wide), row-gap 10. Rows:
     - JOIN CODE y279 h29
     - PLAYERS y318 h18
     - SERVER y346 h18
     - WORST PING y374 h18
     - YOUR LOADOUT y402 h18
   - Adaptation rows (MAGAZINES, GEAR) continue below at the same 10 px gap and grow the card downward.

5. KEY HINTS: anchored bottom-left, left 96, bottom 40 (y 1018-1040), a row with gap 22. Groups start at x 96, 201.5 and 334.1.

## elements
LIVE INDICATOR
- Dot: 10x10 circle, colour --enemy #FF4D5A, pulsing opacity 1 -> 0.35 -> 1 over 1.2 s ease-in-out, infinite.
- Label: .lbl style but coloured --text-hi #F3F0E9 (BC 600 13px, .14em / 1.82px).
- Copy: 'MATCH STILL RUNNING · THE GAME DOES NOT PAUSE'.

MENU ROWS (primary)
- Label: BC 700 36px, .1em (3.6px), uppercase, colour --text-mid #9CA2AB.
- Selected (.on): colour --text-hi #F3F0E9, plus a 4 px wide bar of --text-hi at x=96, inset 14 px from the row's top and bottom. For 60 px rows the bar is y+14..y+46 (32 tall); for 46 px rows it is 18 tall.
- Copy and right hints:
  - 'RESUME', with a ghost ESC keycap 33.1x20 at (522.9,170).
  - 'LOADOUT', hint 'NEXT SPAWN'.
  - 'SETTINGS', no hint.
  - 'CONTROLS', hint 'KEY REFERENCE'.
- Hint style (small): BC 600 13px, .16em (2.08px), --text-low #646B75, uppercase, right-aligned to x=556, vertically centred.

HOST GROUP (host only)
- Label: .micro (BC 600 11px, .16em / 1.76px, --text-low), copy 'HOST · ONLY YOU SEE THIS', padding-left 22.
- Rows: BC 700 24px, .1em (2.4px), same colours and selection as above.
  - 'PLAYERS', hint 'MOVE · KICK'.
  - 'RESTART MATCH', no hint.
  - 'BACK TO LOBBY', hint 'KEEPS EVERYONE'.

DANGER ROW
- 'STOP HOSTING': BC 700 24px, .1em, colour --enemy #FF4D5A.
- Hint 'ENDS MATCH FOR ALL': 13px BC 600 .16em, colour rgba(255,77,90,0.7).
- Selected: keep the red text; draw the 4 px bar in --enemy (not in the mockup, chosen so the bar does not look like a confirmation).

DISABLED ROW: opacity 0.35. It is skipped by arrow keys and ignores clicks.

INFO CARD: .panel.hi (bg rgba(16,21,29,0.82), 1px --stroke, radius 2).
- Title h2: BC 700 20px, .18em (3.6px), --text-hi. Copy 'TEAM DEATHMATCH · SHOWHOME'.
- Score row (flex, align centre, gap 18):
  - Ally score: BC 700 56px, line-height 56, tabular, --ally #52E5A5 (e.g. '32'; box 55.8 wide).
  - 'VS': .lbl (13px BC 600 .14em --text-mid) at x1362.8, y227.
  - Enemy score: same style, --enemy #FF4D5A, at x1396 (e.g. '28').
  - Right block (margin-left auto, right-aligned at x1799, starting y216.5, 84 wide x 37 tall):
    - Line 1: .micro 'FIRST TO 50'.
    - Line 2: '06:41' in BC 700 20px --text-hi tabular (letter-spacing 1.76px inherited), followed by ' LEFT' in .micro.
- Key/value labels: BC 600 13px, .14em (1.82px), --text-mid, uppercase, padding-top 2. Copy: 'JOIN CODE', 'PLAYERS', 'SERVER', 'WORST PING', 'YOUR LOADOUT'.
- Values:
  - JOIN CODE: BC 700 24px, .2em (4.8px), --text-hi, e.g. 'SHRD-4K7Q'.
  - PLAYERS: num (BC 500 15px), --text #D7D4CD, '10 / 10 · 5 v 5'.
  - SERVER: num, 'Listen server (you) · 60 Hz · CPU 2.1 ms / tick'.
  - WORST PING: num, 'Brann 90 ms · 1.2 % loss'.
  - YOUR LOADOUT: Barlow 400 15px --text, 'Kestrel · AR-7 Mako · T2 Mender (Medium)'.

KEY HINTS (ghost keycaps 22 tall plus .hint labels)
- [↑↓] 'SELECT'.
- [ENTER] 'CONFIRM'.
- [ESC] 'RESUME'.

## data_bindings
Host vs client: Session.role (Role::Host / Role::Client).

TITLE
- MatchState.mode Tdm -> 'TEAM DEATHMATCH · ' + MatchState.map uppercased ('SHOWHOME').
- Range -> 'GUN RANGE · FREE PRACTICE'.

SCORE
- Ally = your team's score (PlayerInfo.team of the Controlled player: A -> score_a, B -> score_b); enemy = the other score.
- Line 1: 'FIRST TO {score_limit}'.
- Clock: mm:ss of ceil(MatchState.time_left_s).
- When MatchPhase::Ended: replace the clock line with 'MATCH OVER' in BC 700 20px --text-hi.
- Range mode (no score): hide the whole score row.

JOIN CODE
- Session.join_code. The host gets the encoded code (e.g. '6000-105E-PC', which fits in 360 px). A client gets the code or address they joined with.
- None -> '—'.
- Optional, host only: Session.lan_addr as a second .micro line 'LAN 192.168.1.20:47820'.

PLAYERS
- '{connected} / {rules.tdm.max_players} · {allyCount} v {enemyCount}', counting PlayerInfo entities by team (allies first).
- Range: '{connected} / {max}' without the 'v' part.

SERVER
- Host: 'Listen server (you) · {net.tick_hz} Hz · CPU {avg FixedUpdate ms over the last 1 s, 1 dp} ms / tick'. If the CPU time is not measured yet, omit the ' · CPU …' part.
- Client: '{host PlayerInfo.name (PlayerId 0)} hosts · {tick_hz} Hz'.

WORST PING
- Host: the remote player with the highest link RTT: '{name} {rtt} ms', plus ' · {loss:.1} % loss' when lightyear exposes loss. No remote players -> 'No one else connected'.
- Client: relabel the row 'YOUR PING', value '{own link RTT} ms' (plus loss if available). Unknown -> '—'.

YOUR LOADOUT
- '{weapon name from weapons.ron} · {halo tier label} {Core} ({WeightClass})', e.g. 'AR-7 Mako · T2 Mender (Medium)'.
- Tier label: 'T{n}' when every covered arc has the same tier, else 'T{min}-T{max}'.
- No agents exist yet, so omit the mockup's leading 'Kestrel · ' until agents ship.
- No halo (arm_none): 'AR-7 Mako · No halo (Light)'.

## interactions
OPEN / CLOSE
- Esc toggles the menu (existing toggle_pause). It opens with RESUME selected.
- The game does NOT pause. Movement input is zeroed while the menu is open, so the player stands still.
- The menu can be opened while dead. It covers the death recap, the respawn timer keeps running, and the recap shows again when the menu closes.

NAVIGATION
- Up/Down moves the selection through the enabled rows and wraps.
- Mouse hover selects a row (there is no separate hover style: hover == selected).
- Enter or a left click activates the row.
- Esc anywhere in the menu = RESUME (cursor re-locked).

ROW ACTIONS
- RESUME: close the menu.
- LOADOUT: open the Loadout hub screen (mockup 05) as an overlay over the running match, in next-spawn mode. Back or Esc returns to this menu.
- SETTINGS: open the Settings hub (mockup 08) on its first tab. Back or Esc returns here.
- CONTROLS: open Settings on the Keybinds tab (mockup 08b).
- PLAYERS (host): swap the right info card for a host players card listing every player (team colour, name, ping). Each row has the lobby context actions 'MOVE TO TEAM A/B' and 'KICK' (danger), styled like the Lobby ctx menu. Esc returns to the info card.
- RESTART MATCH (host): confirm modal (see the modal spec, warn variant), then the host resets the match.
- BACK TO LOBBY (host): send everyone to the lobby screen (mockup 06), connections kept.
- STOP HOSTING (host): open the Stop-hosting confirm modal.
- LEAVE MATCH (client): open the Leave confirm modal, then NetRequest::Leave { reason: None }.

## adaptations
1. CLIENT VARIANT (not drawn in the mockup; derived from its HTML comment 'HOST · ONLY YOU SEE THIS'):
   - Remove the whole host group.
   - The danger group sits 22 px under CONTROLS (separator at y=412, row at y=427).
   - Danger row copy: 'LEAVE MATCH', hint 'BACK TO MAIN MENU', same red styling.
   - Relabel WORST PING to YOUR PING (see data).

2. GUN RANGE: title 'GUN RANGE · FREE PRACTICE', score row hidden. Host rows:
   - RESTART MATCH becomes 'RESET RANGE' (respawn everyone, no hint).
   - BACK TO LOBBY stays.

3. FEATURES NOT BUILT YET: show those rows disabled (opacity 0.35) with the hint text replaced by 'NOT YET', not hidden, so the layout matches the mockup:
   - LOADOUT: needs the loadout screen plus a client->host 'LoadoutChoice' message applied at next spawn (Hello already carries one).
   - PLAYERS: needs host-side kick and move.
   - BACK TO LOBBY: needs the lobby state.
   RESTART MATCH is implementable now: reset MatchState scores, time and phase, reset every Score, respawn all.

4. MAGAZINES ROW (user direction, not in the mockup):
   - Add a key/value row under YOUR LOADOUT: label 'MAGAZINES'. Value: one chip per loadout magazine in slot order (up to 6), gap 4.
   - Chip shape: h22, padding 0 6, 1px --stroke-mid, radius 2, bg rgba(255,255,255,0.04).
   - Chip text: slot number in BC 600 11px --text-low, 4 px gap, then the ammo short label in BC 700 13px .06em ('STD', 'AP I', 'AP II', 'AP III', 'RIP I'-'RIP III', 'SLUG'). Use the AmmoSpec label.
   - Ammo text colour: use the Loadout screen's ammo chip colour if it defines one; fallback is the tier palette by ammo tier (I = --t1 #EDF1F6, II = --t2 #59B3FF, III = --t3 #C46CFF).
   - Never show fill state or round counts here.

5. GEAR ROW (TDM only):
   - Label 'GEAR'. Value '{used} / {rules.tdm.gear_budget}' in BC 700 15px --text-hi.
   - Followed by .micro '  HALO {arc tier sum} + MAGS {mag gear cost sum}'.
   - Hidden in Range.

6. HOST LEAVES: when the host stops, clients currently see a generic 'disconnected (...)'. Add a host->client 'HostClosing' message so the client's main menu status reads 'The host stopped hosting.'

7. The old PauseRoot scoreboard text is dropped. Hold Tab still shows the scoreboard, also while this menu is open.

## assets
No images or icons.svg symbols.

The arrow keycap needs ↑ and ↓ glyphs, which are not in Barlow: use a 10x12 white arrow PNG pair or a fallback font.

The backdrop is the live game view (the mockup used /home/user/sharline/design/ui/mockups/img/hud_street.jpg as a stand-in).

