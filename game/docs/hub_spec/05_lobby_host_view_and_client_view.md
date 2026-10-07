# Lobby (host view and client view)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/06_lobby.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/lobby.html",
 "/home/user/sharline/design/ui/mockups/lobby.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg",
 "/home/user/sharline/design/ui/mockups/_src/pages/main_menu.html (CREATE LOBBY / JOIN LOBBY lead here)",
 "/home/user/sharline/design/ui/mockups/_src/pages/esc_menu.html (Back to lobby / Stop hosting confirm)"
]

## purpose
The pre-match room after the host clicks CREATE LOBBY (main menu > Play > Host) or a friend clicks JOIN LOBBY. Everyone sees both teams with agent, weapon, halo tier and weight class, ping and ready state. Players chat, open the loadout, switch team and toggle ready. The host shares the join code, sets map, mode, score limit and the other match rules, moves or kicks players and starts the match. A CONNECTION panel shows whether friends can reach the listen server. Non-hosts see the same screen with MATCH SETTINGS read-only. Mockup 06 is the HOST view: the local player is KESTREL_YOU, host, on Team A and not ready, with the host context menu open on ROOK.

## layout
Canvas 1920x1080. All px are at 1080p; use UiScale = window_height / 1080 (as common.css says), so every value maps 1:1 to Val::Px. Screen background (full screen, under everything): radial gradient, ellipse centred at 40% x / 20% y, stops #151C26 at 0%, #090C11 at 60%, #06080B at 100% (CSS farthest-corner). Use Bevy BackgroundGradient(RadialGradient). Measured: about #0B0E14 at the top-left corner and #05070A at the bottom-right.

REGIONS (absolute, x from the left edge, y from the top):
1. TOP BAR: left 0, right 0, top 0, height 96. Flex row, align-items centre, padding 0 48, column gap 24. Bottom border 1px --stroke rgba(255,255,255,.09) at y=95. Contents left to right: the title 'LOBBY' (x 48..160), the lobby name + status block (x 191..460), a flex-1 spacer, and the JOIN CODE box, anchored RIGHT (right edge x 1872 = 48 from the right; measured x 1355..1872, y 12..84, height about 72; it grows LEFT when the code is longer).
2. TEAMS: absolute left 48, top 124, width 1180. Two-column grid (1fr 1fr) with gap 20, so each column is 580 wide. Team A column x 48..628, Team B column x 648..1228. Each column holds the team header (y 124..~187, ending in a 3px bar at y 184..187) and then one 76px row per slot with margin-top 6. Slot tops are y 192, 274, 356, 438, 520 for 5 slots per team; the last slot ends at y 596. The slot count is max_players / 2, so with 8 max there are 4 rows and the column ends at 514.
3. MATCH SETTINGS panel: anchored RIGHT. Absolute right 48 (x 1272..1872), top 124, width 600, padding 18 top/bottom and 20 left/right, height auto (about 657, so it ends at y ~781). Inner content width 558 (x 1293..1851).
4. CHAT panel: anchored BOTTOM-LEFT. Absolute left 48, bottom 112 (y 718..968), width 560, height 250, padding 14 top/bottom and 16 left/right. Flex column.
5. CONNECTION panel: anchored BOTTOM. Absolute left 640, bottom 112 (x 640..1228, y 718..968), width 588, height 250, padding 14 16.
6. BOTTOM BAR: anchored BOTTOM. Absolute left 0, right 0, bottom 0, height 88 (y 992..1080). Flex row, align-items centre, gap 12, padding 0 48. Top border 1px --stroke. Background rgba(5,7,10,.60). Contents: LEAVE (x 48..145), a flex-1 spacer, then right-aligned LOADOUT (x 994..1141), SWITCH TEAM (x 1154..1341), READY (x 1352..1521), the ready counter (right-aligned text ending x 1667, margin-right 6) and START MATCH (x 1687..1872).
7. Floating: the PLAYER CONTEXT MENU (GlobalZIndex above everything), anchored to the clicked row: top = row top, left = row left + 330. In the mockup it is x 978..1198, y 274..460 on ROOK. The proposed VIEW LOADOUT popover (see adaptations) uses the same anchoring.
Do NOT draw the mockup label 'MOCKUP 06 · LOBBY (HOST VIEW)' at the bottom right.

## elements
FONTS: --fd = 'Barlow Condensed' (weights 500/600/700); --fb = 'Barlow' (400/500/600/700, plus 400 italic for system chat lines). 'tnum' means tabular numerals (font feature tnum, the CSS .num class). Letter-spacing is given in em, which is Bevy LetterSpacing::Rem(x) (a multiple of the font size), with the px value in brackets. Bevy has no text-transform, so write strings in upper case where marked UPPER. Line height is CSS 'normal', about 1.2x the font size, unless stated.
COLOUR TOKENS: --bg0 #07090D; --panel rgba(9,12,17,.70); --panel-hi rgba(16,21,29,.82); --stroke rgba(255,255,255,.09); --stroke-mid rgba(255,255,255,.16); --stroke-hi rgba(255,255,255,.32); --text-hi #F3F0E9; --text #D7D4CD; --text-mid #9CA2AB; --text-low #646B75; --teal #00DACE; --coral #FF8C7A; --t1 #EDF1F6; --t2 #59B3FF; --t3 #C46CFF; --t4 #FFCE50; --unlit #27272C; --ally #52E5A5; --enemy #FF4D5A; --warn #FFA23A. Panels (.panel) have background --panel, a 1px --stroke border and radius 2; .panel.hi uses background --panel-hi.
SHARED BUTTON (.btn): height 44, padding 0 22, gap 10 between icon and label. Text fd 700 18px, letter-spacing .12em (2.16px), UPPER, colour --text-hi. Background rgba(255,255,255,.06), 1px border --stroke-mid, radius 0. HOVER: background rgba(255,255,255,.12), border --stroke-hi. PRESSED: use hover colours. DISABLED: whole node opacity .35, no interaction. Variants: .primary has background and border --text-hi with text --bg0 #07090D (hover background #FFFFFF); .danger has text --enemy and border rgba(255,77,90,.45); .ally has background and border --ally with text #04140C.
KEY CAP (.key): min-width 22, height 22, padding 0 6, fd 700 13px, letter-spacing .04em, text --bg0 on background --text-hi, radius 2. GHOST variant: transparent background, text --text-hi, 1px border --stroke-hi.
MICRO (.micro): fd 600 11px, letter-spacing .16em (1.76px), UPPER, colour --text-low.

== TOP BAR ==
- Title 'LOBBY': fd 700 40px, letter-spacing .14em (5.6px), --text-hi. Cap height spans about y 36..63.
- Lobby name 'KESTREL_YOU'S GAME': fd 700 22px, letter-spacing .08em (1.76px), --text, UPPER. Text y about 30..50.
- Status line, directly below the name: a flex row with gap 8. It holds an 8x8 dot (radius 50%, --ally) that pulses opacity 1 > .35 > 1 over 1.6 s, looping, then the text 'WAITING · 7 / 10 PLAYERS · 5 READY' in fd 600 15px, letter-spacing .14em (2.1px), --text-mid. Text y about 54..68.
- JOIN CODE box: flex row, align centre, gap 14, padding 10 14. 1px border --stroke-mid, background rgba(255,255,255,.04), radius 0. It holds three children:
  a) A column with the micro 'JOIN CODE · SHARE IT WITH FRIENDS' (11px, --text-low) and, under it, the code 'SHRD-4K7Q' in fd 700 30px, letter-spacing .2em (6px), --text-hi, tnum (glyphs y 45..68).
  b) A COPY button: the .btn variant with height 38, padding 0 12, font 14px (letter-spacing .12em = 1.68px), gap 10, and the i-copy icon at 16x16 in --text-hi (x 1580..1665).
  c) An address block in fb 400 12px, line height 1.35 (16.2px), --text-mid, two lines: 'LAN 192.168.1.24:7777' and 'Direct 84.212.x.x:7777 · ' followed by 'port closed' in --warn #FFA23A. This text is NOT uppercased.

== TEAM HEADER (one per column) ==
- Flex row, space-between, align flex-end, padding-bottom 10, bottom border 3px solid in the team colour. The team colour is relative: your team is --ally #52E5A5 and the other team is --enemy #FF4D5A.
- Left: the name 'TEAM A' / 'TEAM B' in fd 700 28px, letter-spacing .14em (3.92px), team colour. Under it, a block subtitle in fd 600 13px, letter-spacing .2em (2.6px), --text-mid, UPPER: 'WEST HOUSE · YOUR TEAM' (Team A) or 'EAST HOUSE' (Team B). The ' · YOUR TEAM' suffix goes on whichever team you are in.
- Right: the count '4 / 5' in fd 700 18px, letter-spacing .1em (1.8px), --text-mid, tnum.

== PLAYER ROW (.pl) ==
- Node: height 76, margin-top 6, padding 0 12, background rgba(255,255,255,.035), 1px border --stroke, radius 0.
- Grid columns: 52 | 1fr | 92 | 72 | 50 | 40 with column-gap 10, align-items centre. In a 580-wide row the 1fr column is 198. Column x offsets from the row's left edge: portrait 13..65, name 75..273, halo 283..375, ping 385..457, signal 467..517, ready 527..567.
- Col 1, PORTRAIT: 44x44, left-aligned, hexagon shape polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%), so the points are at top and bottom. The agent portrait image fills it ('cover', focus at centre 20%). The fill colour behind the image is --teal for Kestrel or --coral for Solace; it shows only while the image loads.
- Col 2, NAME + SUB (stacked):
  - Name: fd 700 20px, letter-spacing .06em (1.2px), --text-hi, UPPER. It is a flex row with gap 8. The host gets the i-crown icon at 16x16 in --t4 #FFCE50 after the name.
  - Sub: fb 400 12.5px, --text-mid, margin-top 1, NOT uppercased. Format: '{Agent} · {Weapon}', for example 'Solace · AR-7 Mako', 'Kestrel · VK-50 Warden' or 'Solace · AR-7 Mako + UGL'. Your own row starts with 'You · ' and the host's row also has 'host · ', for example 'You · host · Kestrel · AR-7 Mako'.
- Col 3, HALO: a tier chip, then a 5px gap, then the weight squares.
  - Tier chip: N parallelogram pips (N = tier), each 6x10 and skewed -14 degrees, with gap 3, in the tier colour (--t1/t2/t3/t4).
  - Weight squares: three 7x7 squares with gap 2. Lit squares are --text-hi; unlit squares are rgba(255,255,255,.20). 1 lit = Light, 2 = Medium, 3 = Heavy.
  - Mockup values: ASH T3 + 3 lit; KESTREL_YOU T2 + 2; JUNO T1 + 1; DACE T2 + 2; PIKE T3 + 3; ROOK T3 + 3; MOTH T2 + 1.
  - See the adaptations for per-arc tiers.
- Col 4, PING: fd 600 15px, --text-mid, right-aligned, tnum. Copy '22 ms', or 'host' on the host's row.
- Col 5, SIGNAL: the i-signal icon at 22x22, left-aligned in its column. Tint: --ally when good, --warn when fair, --enemy when bad. Mockup: DACE at 58 ms is --warn; ASH is --text-mid, which is a mockup slip, so treat it as good.
- Col 6, READY BOX: 30x30, centred, 1px border --stroke-hi, with the i-check icon at 18x18 in transparent colour. When READY: background and border --ally, check colour #06140D.
- Row STATES:
  - Your own row: border rgba(255,255,255,.70), background rgba(82,229,165,.10).
  - Context-menu target (open menu) row: border --text-hi #F3F0E9.
  - Hover (host hovering another player's row; proposed): border --stroke-hi.

== EMPTY SLOT (.pl.empty) ==
- Same 76px box with a transparent background and a 1px DASHED border --stroke-mid. Bevy has no dashed borders, so use a 9-slice dashed-border image (see assets).
- Grid columns 1fr | auto.
- Both spans are fd 600 15px, letter-spacing .16em (2.4px), --text-low, UPPER. (The right span is .micro, but the .pl.empty span rule wins, so it is ALSO 15px, not 11px.)
- Copy, in this order:
  - The first empty slot on YOUR team: left 'OPEN SLOT · SHARE CODE SHRD-4K7Q', right '+ ADD BOT (LATER)'.
  - The first empty slot on the OTHER team: left 'OPEN SLOT', right 'JOIN TEAM B' (or 'JOIN TEAM A').
  - Every other empty slot: 'OPEN SLOT' with no right text.

== PLAYER CONTEXT MENU (host actions, mockup on ROOK) ==
- Panel: width 220, padding 6, background #141A22 (opaque), 1px border --stroke, radius 2, BoxShadow 0 12px 40px rgba(0,0,0,.60).
- Header: '{NAME} · HOST ACTIONS' ('ROOK · HOST ACTIONS') in fd 700 15px, letter-spacing .12em (1.8px), --text, UPPER, padding 6 12 4 (about 28 tall). It is not hoverable.
- Items: padding 9 12 (36 tall), fd 700 15px, letter-spacing .12em, --text, UPPER. Copy: 'MOVE TO TEAM A' (or 'MOVE TO TEAM B'), 'VIEW LOADOUT', 'MUTE CHAT', 'KICK'. KICK is --enemy.
- Item HOVER (the mockup shows 'MOVE TO TEAM A' hovered): background rgba(255,255,255,.08), text --text-hi.
- Total height about 186.

== MATCH SETTINGS PANEL (.panel.hi) ==
- Header row: flex, space-between, baseline-aligned. Left 'MATCH SETTINGS' in fd 700 20px, letter-spacing .18em (3.6px), --text-hi. Right, the micro 'HOST ONLY · OTHERS SEE READ-ONLY' (11px, --text-low).
- MAP CARD: margin-top 12, height 150 (x 1293..1851, y ~180..330), 1px border --stroke-mid.
  - Image hud_street.jpg drawn as 'cover', positioned centre 65%. With ImageNode.rect on the 1920x1080 texture that is about Rect(0, 371, 1920, 880).
  - Overlay: a linear gradient from the bottom up, rgba(6,8,11,.90) at 0% to rgba(6,8,11,0) at 60%.
  - Title block at left 14, bottom 10, three stacked lines:
    - Micro 'MAP · PLACEHOLDER ART' in --text-mid (overrides micro's --text-low).
    - Map name 'SHOWHOME' in fd 700 28px, letter-spacing .14em (3.92px), --text-hi, line height 28.
    - Micro '2 HOUSES · 1 STREET · 4 V 4 TO 5 V 5' in --text-mid.
  - A CHANGE MAP .btn at right 12, bottom 12: height 34, padding 0 12, font 13px (x ~1737..1839).
- OPTIONS LIST: margin-top 12. Ten rows, each height 42, grid 180 | 1fr, align centre, bottom border 1px --stroke (none on the last row). Row tops: y 342, 384, 426, 468, 510, 552, 594, 636, 678, 720 (ends 762).
  - Label: fd 600 13px, letter-spacing .14em (1.82px), --text-mid, UPPER. Control column x 1473..1851 (378 wide).
  - SELECT control (.sel): height 32, padding 0 10, 1px border --stroke-mid, flex space-between. Value in fd 700 16px, letter-spacing .06em (0.96px), --text-hi. At the right, the arrows '‹ ›' in --text-mid with a 14px gap between them.
  - SEGMENTED control (.seg): equal flex-1 cells, each height 32 with a 1px --stroke-mid border, overlapped by -1px so neighbouring borders merge. Text fd 700 15px, letter-spacing .08em (1.2px), --text-mid, centred. SELECTED cell: background --text-hi, text --bg0 #07090D, border --text-hi. HOVER on an unselected cell (host only; proposed, not in the CSS): background rgba(255,255,255,.06), text --text-hi.
  - Rows (selected value in brackets):
    - 'MODE': select 'TEAM DEATHMATCH ‹ ›'.
    - 'SCORE LIMIT': 25 | [50] | 75 | 100.
    - 'TIME LIMIT': 5 min | 8 min | [10 min] | 15 min. These are NOT uppercased: lowercase 'min'.
    - 'RESPAWN DELAY': 2 s | 3 s | [4 s] | 6 s.
    - 'DOWNED STATE': [OFF] | ON · 15 s.
    - 'FRIENDLY FIRE': [OFF] | 25 % | ON.
    - 'GUNFIRE ON MINIMAP': OFF | [ON · 2 s].
    - 'GEAR BUDGET': [OFF] | 20 PTS | 12 PTS.
    - 'TEAM BALANCE': MANUAL | [AUTO ON START].
    - 'MAX PLAYERS': select '10 (5 v 5) ‹ ›' (tnum).

== CHAT PANEL (.panel) ==
- Title 'CHAT' in fd 700 20px, letter-spacing .18em, --text-hi, followed inline by the micro 'LOBBY' (11px, --text-low, about 10px gap).
- Message list: flex 1, margin-top 8 (from y ~764 to the input at 916), fb 400 14.5px, line height 1.6 (23.2px), --text. Fits 6 lines; anchor to the bottom and clip the oldest lines at the top.
  - Player line: the speaker name 'KESTREL_YOU:' in fd 700, letter-spacing .06em, UPPER, coloured --ally for your team and --enemy for the other team. Then a space and the message in fb 400 --text.
  - System line: fb 400 ITALIC, --text-mid.
  - Mockup lines: (sys) 'Juno joined Team A.'; 'KESTREL_YOU: ten minutes, first to 50, no downs'; 'PIKE: two Wardens on B again, sorry not sorry'; 'JUNO: I'll take the truck lane'; (sys) 'Moth changed loadout.'
- Input: height 38, padding 0 10, 1px border --stroke-mid, fb 400 14px, --text-low, flex align centre (y 916..954). Idle copy: 'Press ', a key cap 'ENTER' (height 18, font 12px, margin 0 6), then ' to chat'. While focused: EditableText in fb 400 14px --text-hi, with the border --stroke-hi.

== CONNECTION PANEL (.panel) ==
- Title 'CONNECTION' in fd 700 20px, letter-spacing .18em, --text-hi.
- Five rows, each height 36, grid 150 | 1fr | auto, align centre, bottom border 1px --stroke (none on the last row). Rows start at y ~756.
  - Key: fd 600 13px, letter-spacing .14em, --text-mid, UPPER.
  - Value: fb 400 14px --text. Values marked num use fd 400-600 14px tnum (condensed).
  - Status: fd 700 13px, letter-spacing .1em (1.3px), right-aligned, --ally (ok) or --warn (warning).
  - Mockup rows (key / value / status):
    - 'SERVER' / 'Listen server on this PC · 60 Hz tick' / 'RUNNING' (ok).
    - 'WORST CLIENT' / 'Dace 58 ms · 0.4 % loss · jitter 6 ms' (num) / 'GOOD' (ok).
    - 'JOIN CODE' / 'Relay rendezvous reachable' / 'ON' (ok).
    - 'DIRECT IP' / 'UDP 7777 not reachable from outside' / 'PORT CLOSED' (warn).
    - 'BUILD' / 'v0.1.0-proto · all players match' (num) / 'OK' (ok).

== BOTTOM BAR ==
- 'LEAVE': .btn.danger.
- 'LOADOUT': .btn with the i-optic icon at 18x18.
- 'SWITCH TEAM': .btn with the i-swap icon at 18x18.
- 'READY': .btn.ally, min-width 170, content centred. It holds the i-check icon (18x18, colour #04140C), the label, then a key cap 'F' with background #06140D, text --ally, height 20.
- Ready counter: a column aligned flex-end. Top line '5 / 7 READY' in fd 700 20px, letter-spacing .08em (1.6px), --text-hi, tnum. Under it the micro 'HOST CAN START ANYWAY'.
- 'START MATCH': .btn.primary, height 52, padding 0 30, font 20px (letter-spacing 2.4px), y 1010..1062.

## data_bindings
NEW STATE NEEDED: today the host spawns the match immediately (net.rs NetRequest::Host -> server::spawn_match). Add a lobby phase: AppState::Lobby on clients and MatchPhase::Lobby on the replicated MatchState, or a separate replicated LobbyState entity. It should hold: lobby_name, host PlayerId (0 = host), settings {mode, map, score_limit, time_limit_s, respawn_s, gear_budget: Option<u32>, max_players, team_balance}, and per-player {ready: bool}. Add a replicated per-player PlayerNet {ping_ms: u16, loss_pct: f32, jitter_ms: u16}, which the host updates about once per second from the lightyear link stats.

TOP BAR
- Title: static 'LOBBY'.
- Lobby name: the host's name + ''S GAME' (main menu Host flyout 'Lobby name', default '{HOSTNAME}'S GAME'), UPPER.
- Status: 'WAITING · {players} / {max_players} PLAYERS · {ready_count} READY'. During the start countdown (if added): 'STARTING IN {n}'.
- Code box:
  - Code: Session.join_code, for example '6000-105E-PC'. Our format is XXXX-XXXX-XX (12 chars), so the box is wider than the 9-char mockup code; it is right-anchored and grows left.
  - Line 1: 'LAN {Session.lan_addr}', for example 'LAN 192.168.1.24:47820'.
  - Line 2: 'Direct ' + the public address if known, else 'Internet: forward UDP {net.port} or use a VPN'. Then ' · ' and the reachability word: 'port closed' (--warn), 'open' (--ally), or 'not checked' (--warn) until UPnP/reachability exists.
  - Clients see the code they joined with (store it in Session.join_code on join) and a 'LAN' line with the host address.

TEAMS
- Column assignment: PlayerInfo.team, with Team::A on the left and Team::B on the right, always.
- Team colour: --ally if the team equals the local player's team, else --enemy.
- Subtitles: Team A 'WEST HOUSE', Team B 'EAST HOUSE' (Showhome spawn sides). Put them in map data.
- Count: '{n} / {max_players/2}'.
- Rows, ordered by join order with the host first in their team:
  - Name: PlayerInfo.name.
  - Crown: shown when PlayerId == host.
  - Sub: agent name (NOT in the game yet; see adaptations, default 'Kestrel'), then ' · ', then the weapon display name from weapons.ron 'name' (PlayerLoadout/LoadoutChoice.weapon, for example 'AR-7 Mako', 'VK-50 Warden' and the SMG when added), then ' + UGL' only if an underbarrel launcher attachment exists (none today, so omit).
  - Portrait: the agent's portrait.
  - Halo: from the armor preset tiers (armor.ron presets, capped by loadout_tier_caps) and WeightClass from weight_bands (sum of arc tiers: Light 1..4, Medium 5..8, Heavy 9..16, None 0).
  - Ping: PlayerNet.ping_ms; 'host' for PlayerId 0.
  - Signal tint thresholds in data (new game/assets/data/ui.ron): good < 55 ms (--ally), fair 55..99 (--warn), bad >= 100 (--enemy).
  - Ready: Lobby ready flag.
- Empty-slot share code: Session.join_code.

MATCH SETTINGS (host writes, everyone reads; defaults from rules.ron tdm)
- MODE: MatchMode {Tdm -> 'TEAM DEATHMATCH', Range -> 'GUN RANGE'}.
- Map card: map display name ('SHOWHOME' / 'GUN RANGE'), blurb ('2 HOUSES · 1 STREET · 4 V 4 TO 5 V 5') and card image. Store these per map in data (maps list in a new lobby/ui RON), not in code.
- SCORE LIMIT: tdm.score_limit, options [25, 50, 75, 100], default 50.
- TIME LIMIT: tdm.time_limit_s, options [300, 480, 600, 900] shown as '5 min'.., default 600 = '10 min'.
- RESPAWN DELAY: tdm.respawn_s, options [2, 3, 4, 6], default 4.
- GEAR BUDGET: tdm.gear_budget, options [OFF, 20, 12], DEFAULT 12 (our data; the mockup shows OFF selected). OFF means no budget check in server::loadout_from_choice.
- TEAM BALANCE: new setting {Manual, AutoOnStart}.
- MAX PLAYERS: tdm.max_players, options [2, 4, 6, 8, 10] shown as '{n} ({n/2} v {n/2})'. It must be <= net.max_remote_clients + 1.
- DOWNED STATE, FRIENDLY FIRE, GUNFIRE ON MINIMAP: no game data yet; see adaptations.
- Every option list lives in RON (CLAUDE.md: numbers in data).

CHAT
- New reliable messages: ChatSend {text} (client -> host) and ChatLine {from: Option<u64>, text, system: bool} (host -> all). The host relays them.
- System lines generated by the host: '{Name} joined Team {A|B}.', '{Name} left.', '{Name} moved to Team {X}.', '{Name} changed loadout.', '{Name} was kicked.', 'Host changed {setting} to {value}.'
- Speaker name colour: relative team.
- Keep the last 50 lines and render what fits (6 lines).
- Max message length 120 chars (data).

CONNECTION
- SERVER:
  - Host: 'Listen server on this PC · {net.tick_hz} Hz tick' / 'RUNNING' (--ally).
  - Client: 'Hosted by {host name} · {tick_hz} Hz tick' / 'CONNECTED'.
- WORST CLIENT: the remote client with the highest RTT: '{Name} {ping} ms · {loss} % loss · jitter {j} ms'. Status 'GOOD' (--ally) if ping < 80 and loss < 2 %, 'FAIR' (--warn), or 'BAD' (--enemy); thresholds in ui.ron. With no remote clients: value 'No one connected yet' in --text-low and status '—' in --text-low.
- JOIN CODE: we have no relay. Value 'Code encodes {lan_addr} (share a VPN IP for internet play)', status 'LAN' (--ally).
- DIRECT IP: value 'UDP {net.port} reachability not checked (no UPnP yet)', status 'NOT CHECKED' (--warn). Later 'OPEN' (--ally) or 'PORT CLOSED' (--warn).
- BUILD: 'v{CARGO_PKG_VERSION} · ' + 'all players match' or '{Name} runs different data' (compare Hello.data_fingerprint, which the host already checks). Status 'OK' (--ally) or 'MISMATCH' (--enemy).

BOTTOM BAR
- Ready counter: '{ready} / {players} READY'.
- Micro: host 'HOST CAN START ANYWAY'; clients 'WAITING FOR HOST'.

NO DATA YET (what to show)
- Agent: 'Kestrel' with the Kestrel portrait for everyone.
- Ping before the first measurement: '-- ms' with the signal icon in --text-low.
- A missing portrait image: the hex in --teal or --coral with the agent initial (fd 700 20px, #0B0E13).

## interactions
ENTRY
- Main menu Host flyout 'CREATE LOBBY' -> host starts the listen server and enters the Lobby. The match is not spawned yet.
- Main menu 'JOIN LOBBY' -> Connecting -> Lobby. If the match is already Live, skip straight to InGame.
- ESC menu (mockup 09) 'Back to lobby' (host) returns everyone to the Lobby.
- At MatchPhase::Ended, return to the Lobby after N seconds (data).

TOP BAR
- COPY: copies Session.join_code to the clipboard (for example the arboard crate). The button then shows the label 'COPIED' with the i-check icon for 1.5 s.
- The address lines are not interactive.

PLAYER ROWS
- HOST: left-click or right-click another player's row opens the CONTEXT MENU anchored at row top / row left + 330. The row gets the --text-hi border while the menu is open. Esc or a click outside closes it.
  - 'MOVE TO TEAM {other}': disabled (opacity .35) if that team is full.
  - 'VIEW LOADOUT': opens the popover (see adaptations).
  - 'MUTE CHAT': toggles to 'UNMUTE CHAT'; local only.
  - 'KICK': the host disconnects that client; adds a system chat line.
- CLIENTS: clicking a player row opens the same menu with the header '{NAME}' only, and only VIEW LOADOUT (own team) and MUTE CHAT.
- Clicking your own row opens the Loadout screen.
- Empty slot 'JOIN TEAM {X}': sends a team-switch request. It brightens to --text-hi on hover.
- '+ ADD BOT (LATER)': disabled, no hover.

MATCH SETTINGS
- Host only: clicking a segment selects it and sends the change to the server, which replicates it to all. MODE / MAX PLAYERS '‹ ›' (and click on the left or right half of the select) cycle the options.
- CHANGE MAP cycles the maps for the current mode. Disable it (opacity .35) when the mode has only one map, which is true today.
- Clients: the controls are not interactive and show no hover. Hide the '‹ ›' arrows and the CHANGE MAP button. Keep the micro 'HOST ONLY · OTHERS SEE READ-ONLY'.
- Changing GEAR BUDGET re-validates every loadout. Players now over budget are un-readied and flagged (see adaptations).

CHAT
- ENTER focuses the input (EditableText) and replaces the 'Press ENTER to chat' copy with a caret.
- ENTER sends. Esc cancels and unfocuses.
- While the input is focused, the F (ready) hotkey is suppressed.

BOTTOM BAR
- LEAVE:
  - Client: disconnect -> Main menu (NetRequest::Leave).
  - Host: show the 'STOP HOSTING?' confirm from mockup 09b (CANCEL [ESC] / STOP HOSTING), then stop the server -> Main menu.
- LOADOUT: opens the Loadout screen (mockup 05). Its back button returns to the Lobby. Saving sends LoadoutChoice to the host (re-Hello or a new LoadoutUpdate message).
- SWITCH TEAM: request to move to the other team. Disabled (opacity .35) if the other team is full or the mode is GUN RANGE (hide it there).
- READY [F]: the F key or a click toggles your ready flag.
  - Not ready: ally-filled 'READY' as in the mockup.
  - Ready: the plain .btn style with 'CANCEL READY' and a ghost key cap 'F'.
  - Disabled while your loadout is invalid or over budget.
- START MATCH (host): starts the match with the chosen settings: spawn_match, then all clients go to InGame. It works with any number ready ('HOST CAN START ANYWAY'). If TEAM BALANCE is AUTO ON START, the server evens the teams first.
  - Clients see it disabled (opacity .35) with the label 'HOST STARTS'.
  - Optional: a 3 s countdown in the status line.

KEYBOARD HINTS SHOWN: the 'F' cap on READY and the 'ENTER' cap in the chat input. Esc closes the context menu or popover, or unfocuses chat; with nothing open it does nothing (use LEAVE).

## adaptations
1. HALO PER ARC: our halo has its own tier on each arc (head/torso/arms/legs) plus a core type. The mockup's single-tier chip cannot express that. Keep the same visual vocabulary (6x10 pips skewed -14 degrees, gap 3, then the weight squares):
   - Show exactly 4 pips in the fixed order H, T, A, L. Each pip is coloured by that arc's tier (--t1 #EDF1F6, --t2 #59B3FF, --t3 #C46CFF, --t4 #FFCE50).
   - An arc with tier 0 is --unlit #27272C with a 1px rgba(255,255,255,.13) outline, the same as unlit arcs in widgets.js haloSVG.
   - Example: Mender Scout (H2 T2 A0 L0) = blue, blue, unlit, unlit. Bulwark Vanguard (2/4/2/1) = blue, gold, blue, white.
   - Weight squares come from WeightClass via armor.ron weight_bands: None 0 lit, Light 1, Medium 2, Heavy 3.
   - The same component is used in the scoreboard.
   - Optional: on hover, a tooltip '{CORE} · H{h} T{t} A{a} L{l} · {WEIGHT}'. Halo tier and weight are public, since they are visible in the world (CLAUDE.md).
2. GEAR BUDGET READOUT (TDM gear budget = sum of arc tiers + gear_cost of every magazine; server.rs loadout_from_choice):
   - Your own row's sub line appends ' · {cost} / {budget} PTS', for example 'You · host · Kestrel · AR-7 Mako · 4 / 12 PTS', in --text-mid.
   - When over budget, that suffix becomes 'OVER BUDGET {cost} / {budget}' in --warn. READY is disabled and the LOADOUT button gets a 1px --warn border.
   - When GEAR BUDGET is OFF, omit the suffix.
   - Other players' rows never show points.
3. MAGAZINE ORDER (6 ordered mags, each with its own ammo type/tier): the lobby does not edit mags; LOADOUT opens the Loadout screen, which owns the 6-slot editor. Add a VIEW LOADOUT popover, a new element in the context-menu style:
   - Panel: width 320, padding 12, background #141A22, 1px --stroke, radius 2, shadow 0 12 40 rgba(0,0,0,.6).
   - Header: '{NAME} · LOADOUT' in fd 700 15px, letter-spacing .12em, --text.
   - Rows (label micro, value fd 600 15px --text-hi):
     - WEAPON: name + attachments.
     - HALO: '{CORE} · H2 T2 A0 L0 · LIGHT' with the 4-pip chip.
     - MAGS: six 40x22 cells in a row with gap 4, numbered 1-6 (micro, top-left). Each shows the ammo label 'STD', 'AP I', 'AP II', 'AP III', 'RIP II' or 'SLUG' in fd 700 13px. The cell border is coloured by ammo tier (Standard --stroke-mid, tier I --t1, II --t2, III --t3); empty slots get a dashed --stroke border.
     - GEAR: '{cost} / {budget} PTS'.
   - Visibility: your own team and yourself only. For enemies, show only WEAPON and HALO (public info) and omit MAGS and GEAR.
   - Never show round counts.
4. AGENTS do not exist in the game yet (Kestrel and Solace are art/design only).
   - Add 'agent' to LoadoutChoice / PlayerLoadout.
   - Until then, every player shows 'Kestrel' with the Kestrel portrait (hex), and the sub line still reads '{Agent} · {Weapon}'.
5. HEX PORTRAITS, TIER PIPS AND DASHED BORDERS: Bevy UI has no clip-path, skew or dashed borders.
   - Implement a small UiMaterial HexMask (texture + fallback colour + SDF hex with points at top and bottom), or pre-mask the portraits to 88x88 PNGs with alpha.
   - Tier pip: a 16x20 white parallelogram PNG, displayed at 8x10 and tinted.
   - Empty slot: a 9-slice dashed-border PNG, or 4 tiled dash strips.
6. TEAM COLOURS ARE RELATIVE here: your team is --ally #52E5A5 and the other is --enemy #FF4D5A. Agent colours are separate (Kestrel --teal, Solace --coral). The current game uses teal/coral for team A/B ('TEAM TEAL'/'TEAM CORAL' in hud.rs); the lobby and scoreboard must switch to relative ally/enemy.
7. MATCH SETTINGS rows with no game support yet. Keep all 10 rows so the panel matches the mockup:
   - DOWNED STATE: only OFF works; render 'ON · 15 s' disabled (opacity .35) until downed is built.
   - FRIENDLY FIRE: only OFF; '25 %' and 'ON' disabled.
   - GUNFIRE ON MINIMAP: there is no minimap yet, so the whole row is disabled with OFF selected.
   - TEAM BALANCE: implement (cheap).
   - GEAR BUDGET: options OFF / 20 PTS / 12 PTS, but default to 12 (rules.ron tdm.gear_budget).
   - Range mode (MODE = 'GUN RANGE'):
     - Map card 'GUN RANGE' with blurb 'LANES · AIM LAB · MOVEMENT COURCE', spelled 'LANES · AIM LAB · MOVEMENT COURSE'.
     - SCORE LIMIT, TIME LIMIT, RESPAWN DELAY, GEAR BUDGET and TEAM BALANCE are disabled (opacity .35).
     - There are no teams: the column headers become 'PLAYERS' (left, slots 1-5) and 'PLAYERS' (right, slots 6-10) with a --bone #C4BFB5 3px bar. Subtitles 'FREE PRACTICE' / blank.
     - SWITCH TEAM and MOVE TO TEAM are hidden.
8. CONNECTION panel copy must reflect our netcode: no relay, the join code encodes the LAN/VPN address, UDP port 47820 (not 7777), no UPnP yet (see data bindings). Keep the five rows and the GOOD/warn styling.
9. Port numbers and the join code format differ from the mockup ('SHRD-4K7Q' / 7777 are mockup only).
10. Drop the mockup-only label 'MAP · PLACEHOLDER ART' once real map art exists. Keep it while hud_street.jpg is used.
11. FONTS: bundle Barlow Condensed (500/600/700) and Barlow (400/500/600/700, 400 italic) TTFs (SIL OFL) under game/assets/fonts/. Use FontWeight and LetterSpacing::Rem as specified, and enable the 'tnum' font feature for numbers. Today the game only uses Bevy's default font.

## assets
IMAGES (from /home/user/sharline/design/ui/mockups/img; copy them into game/assets/ui/ and say so in the PR, because design/ is local-owned):
- /home/user/sharline/design/ui/mockups/img/kestrel_portrait.jpg (640x640): Kestrel agent portrait, hex-masked at 44x44.
- /home/user/sharline/design/ui/mockups/img/solace_portrait.jpg (640x640): Solace agent portrait, hex-masked at 44x44.
- /home/user/sharline/design/ui/mockups/img/hud_street.jpg (1920x1080): the Showhome map card. Cover-crop to 558x148, focus centre 65%, ImageNode.rect about (0,371)-(1920,880).
- The Gun Range map card has no mockup image. Candidate: /home/user/sharline/design/maps/range/concepts/themeA_ground_v2_s51.png (ask the local session for a proper card), or fall back to --bg2 #121821 with the title only.
- Not used here: mako_dark.jpg, menu_kestrel.jpg.

ICONS (symbols in /home/user/sharline/design/ui/mockups/_src/icons.svg). Rasterise each to a white-on-transparent PNG at 2x and tint with ImageNode.color:
- i-copy (24 viewBox): COPY button, 16x16.
- i-signal (24): ping column, 22x22.
- i-check (24): ready box 18x18 and READY button 18x18.
- i-crown (24): host marker, 16x16, --t4.
- i-optic (32): LOADOUT button, 18x18.
- i-swap (24): SWITCH TEAM button, 18x18.

GENERATED SHAPES (no SVG in Bevy):
- A hexagon mask (UiMaterial or pre-masked PNGs) for portraits.
- A tier pip: a white parallelogram skewed -14 degrees, 16x20 PNG shown at 8x10 (6x10 visible body).
- A 9-slice dashed-border image for empty slots (1px dashes, about 4 on / 3 off, white, tinted --stroke-mid).

FONTS: Barlow Condensed 500/600/700 and Barlow 400/400-italic/500/600/700 TTF (Google Fonts, OFL).

