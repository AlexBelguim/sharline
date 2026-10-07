# Main menu: PLAY > HOST GAME flyout

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/04b_main_menu_host.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/main_menu.html (the .fly.host-only block, .grid2/.toggle/.stepper/.input.sm styles)",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/game/crates/val_etf/src/net.rs",
 "/home/user/sharline/game/assets/data/net.ron",
 "/home/user/sharline/game/assets/data/rules.ron",
 "/home/user/sharline/game/DESIGN_DELTAS.md (section 5, port)"
]

## purpose
The panel for hosting a listen-server lobby from inside the game: name the lobby, choose how friends reach you, set max players, port and an optional password, then CREATE LOBBY. It is shown to the right of the nav while PLAY > HOST GAME is selected.

## layout
PANEL anchored top-left: left 540, top 300, width 620, auto height (≈494, so y 300-794).
- Padding 26 top, 28 left/right, 24 bottom.
- Borders: top 2 px, the others 1 px. Content box x 569-1131 (width 562), starting at y 328.

Content, flex column (absolute y in brackets):
1. TITLE 'HOST GAME' [y 328-364, height 36].
2. INTRO help, margin-top 6 [y 370-389, one line].
3. FORM GRID, margin-top 18 [y 406.8-694.8]. CSS grid with columns 170 px (labels, x 569-739) and 1fr (controls, x 739-1131, width 392), row_gap 14, align_items centre.
   Every '.input' also carries margin-top 8. That is why each input sits 8 px below its row's start and its label's centre is 4 px above the input's centre. Reproduce the absolute positions below.
   Row 1 LOBBY NAME: label y 424.8-440.8. Input 392x44 at (739, 414.8-458.8).
   Row 2 WHO CAN JOIN: label y 482.8-498.8. Segmented toggle 392x36 at (739, 472.8-508.8).
   Row 3 MAX PLAYERS: label y 534.8-550.8. Control row y 522.8-562.8:
     - stepper 152x40 at x 739-891;
     - help text starting at x 901 (column_gap 10).
   Row 4 PORT: label y 594.8-610.8. Control row y 576.8-628.8:
     - input 136x44 (CSS width 140, which flex-shrinks to 135.6) at (739, 584.8-628.8);
     - help text at x 884.6, width ≈246, wrapping to 2 lines, y 584-622.
   Row 5 PASSWORD: label y 660.8-676.8. Input 392x44 at (739, 650.8-694.8).
4. ACTION ROW, margin-top 22 [y 716.8-768.8]: flex row, align centre, column_gap 12.
   - CREATE LOBBY button 201x52 at x 569-770.
   - Help text at x≈782, vertically centred (y≈733-752).
5. Bottom padding 24 plus a 1 px border, so the panel ends at y≈794.

## elements
PANEL:
- Background #10151DD1 (--panel-hi, rgba(16,21,29,.82)).
- Border 1 px rgba(255,255,255,.09) on left, right and bottom; the TOP border is 2 px #00DACE (--teal). Use Bevy BorderColor { top: teal, right/bottom/left: stroke } with border UiRect { top: 2, others: 1 }.
- border_radius 2 px. No blur, no shadow.

TITLE 'HOST GAME': BC 700, 30 px, ls 3.6 px (.12em), #F3F0E9. Copy is already uppercase.

INTRO (help style): Barlow 400, 13 px, LineHeight 1.45 (18.85 px), #9CA2AB. Copy: 'You play and host at the same time (listen server). If you leave, the match ends for everyone.'

LABELS (.lbl): BC 600, 13 px, ls 1.82 px (.14em), uppercase, #9CA2AB. Copy: 'LOBBY NAME', 'WHO CAN JOIN', 'MAX PLAYERS', 'PORT', 'PASSWORD'.

TEXT INPUT (.input.sm), shared by Lobby name, Port and Password:
- Height 44, padding 0 16 (horizontal), flex row, align centre.
- Background rgba(0,0,0,.45) (#00000073), border 1 px rgba(255,255,255,.32) (--stroke-hi), radius 0.
- Value text: BC 700, 20 px, ls 1.2 px (.06em), #F3F0E9. The port also uses tnum.
- CARET (focused field only): 2x30 node, #00DACE, margin-left 4 after the text. It blinks with steps: opacity 1 for 0.5 s, then .35 for 0.5 s (CSS pulse 1s steps(1)). If EditableText draws its own cursor, style it with TextCursorStyle to 2 px wide, teal.
- PLACEHOLDER: same font, colour #646B75 (--text-low). Password copy: 'optional'.
- Mockup values: Lobby name 'ASH'S GAME' (with caret, so it is focused), Port '7777' (see adaptations), Password empty showing the placeholder.
- The mockup has no focus border change; focus shows only by the caret. Recommended error state: border #FF4D5A.

SEGMENTED TOGGLE (WHO CAN JOIN):
- Container 392x36, 1 px border rgba(255,255,255,.32), transparent, flex row. Segments are left-packed with no dividers, and the rest of the width stays empty.
- Each segment: padding 8 vertical, 14 horizontal, text BC 700, 15 px, ls 1.8 px (.12em).
- Segments: 'JOIN CODE' (100.2 wide), 'LAN ONLY' (93.4), 'DIRECT IP' (95.2).
- Selected: BackgroundColor #F3F0E9, text #07090D. Unselected: transparent, text #9CA2AB. Hover on an unselected segment (recommended): text #F3F0E9.
- Mockup: JOIN CODE selected.

STEPPER (MAX PLAYERS):
- 152x40, 1 px border rgba(255,255,255,.32), flex row, align centre, no dividers.
- Cells: '−' (U+2212) 40 wide; value 70 wide; '+' 40 wide. All text centred, BC 700, 20 px.
- '−' and '+' are #9CA2AB (hover #F3F0E9; at the limit opacity .35). The value is #F3F0E9 with tnum. Mockup value '10'.
- Help after the stepper (help style, margin 0): '2–10 · 5 v 5 max on Showhome' (en dash U+2013).

PORT help: 'UDP. Only needed for Direct IP (port-forward).' It wraps to 2 lines in about 246 px.

PRIMARY BUTTON 'CREATE LOBBY':
- Height 52, padding 0 34 (horizontal), auto width (≈201).
- Text BC 700, 20 px, ls 2.4 px (.12em), uppercase, colour #07090D.
- BackgroundColor #F3F0E9, border 1 px #F3F0E9, radius 0.
- Hover: background #FFFFFF. Disabled: opacity .35, not interactive.
- Pressed (recommended): background #DAD6CB.

ACTION help (help style, margin 0): 'Map, mode and score limit are set in the lobby.'

## data_bindings
Hold this in a new resource, HostSettings { lobby_name, access: JoinCode | LanOnly | DirectIp, max_players, port, password }. Persist it across menu visits and pass it with the host request.

- LOBBY NAME: default format!("{}'S GAME", Session.local_name). Mockup 'ASH'S GAME'. Max 24 characters.
- WHO CAN JOIN: HostSettings.access, default JOIN CODE.
- MAX PLAYERS: range 2..=min(rules.ron tdm.max_players (10), net.ron max_remote_clients + 1 (10)); default 10.
   - Help text from data: format!("2–{max} · {half} v {half} max on Showhome"), with half = tdm.max_players / 2. That gives the mockup's '2–10 · 5 v 5 max on Showhome'.
   - Pass the value to NetcodeServer max_clients, which today is hard-wired to max_remote_clients + 1 in net.rs.
- PORT: default --port, else net.ron port = 47820 (NOT the mockup's 7777).
   - Use it as the LocalAddr port when hosting. The join code encodes this port, so it matters even without port forwarding.
- PASSWORD: HostSettings.password (Option<String>); empty = none.
- CREATE LOBBY: sends NetRequest::Host. Extend it to Host { map, settings } or read HostSettings in handle_requests.
- ERRORS: if hosting fails (e.g. the UDP port is in use) and net.rs sets Session.status, show it in the panel (see interactions).

## interactions
- Opening: selecting HOST GAME in the nav shows this panel. Entering it (Enter, → or a click) focuses LOBBY NAME, with the caret placed at the end of the text.
- Field order (Tab / Shift+Tab, and also ↓/↑ inside the panel): LOBBY NAME → WHO CAN JOIN → MAX PLAYERS → PORT → PASSWORD → CREATE LOBBY.
- WHO CAN JOIN: click a segment, or use ←/→ while focused. Selection is instant.
- MAX PLAYERS: click − or +, or use ←/→ (or -/+) while focused. Clamp to 2..=10; holding may auto-repeat.
- PORT: digits only, max 5 characters. Valid range 1024-65535. When invalid:
   - the input border turns #FF4D5A;
   - the help text becomes 'Port must be 1024–65535.' in #FF4D5A;
   - CREATE LOBBY is disabled (opacity .35).
- PASSWORD: typed characters show as '•' (U+2022, present in Barlow).
- LOBBY NAME: when empty on submit, fall back to the default name.
- CREATE LOBBY: a click, or Enter in any field, sends NetRequest::Host. On success the game moves to AppState::Connecting (existing 'CONNECTING...' screen), then to the lobby (or straight into the match; see adaptations).
- ERROR SLOT: if Session.status is set while this panel is open:
   - show it under the action row, margin-top 12;
   - style Barlow 400 13 px, #FF4D5A;
   - the panel grows by ≈31 px.
- Esc returns focus to the nav (onto HOST GAME). Mouse hover on the button changes the background to #FFFFFF.
- Hints at the bottom of the screen stay '↑↓ SELECT · ENTER CONFIRM · ESC BACK' (or the optional field variant from the shell spec).

## adaptations
H1. PORT default is 47820, from net.ron, not 7777. The game already uses 47820, and DESIGN_DELTAS.md section 5 says the mockup should be updated.

H2. MAX PLAYERS comes from data (rules.ron tdm.max_players = 10, net.ron max_remote_clients = 9) and must actually limit NetcodeServer max_clients.

H3. WHO CAN JOIN semantics in this build. A join code is just the Crockford-base32 encoding of host IPv4 + port (vetf_net::join_code), and there is no relay. So JOIN CODE and DIRECT IP reach exactly the same hosts (LAN, VPN mesh, or a forwarded port). Today the setting only controls what the lobby, scoreboard and ESC menu display:
   - JOIN CODE: shows the code (e.g. '6000-105E-PC').
   - DIRECT IP: shows ip:port.
   - LAN ONLY: shows neither, and (once the LAN beacon on net.ron lan_beacon_port 47821 exists) advertises only on the LAN.
   Until the beacon exists, consider rendering LAN ONLY disabled (opacity .35). Keep all three segments so the layout matches the mockup.

H4. PASSWORD is not in the protocol. Hello has only name, loadout and data_fingerprint. Either add `password: Option<String>` to vetf_net Hello, have the host compare it and disconnect with the reason 'wrong password', and add a netcode serialization test (CLAUDE.md rule); or render the field disabled (opacity .35, placeholder 'optional · not available yet') until that lands.

H5. LOBBY NAME is not replicated. Add it to the replicated match info so clients can show it in their lobby and Recent list. Until then it is local to the host's lobby and scoreboard.

H6. There is no LOBBY screen yet (README 'Not done yet').
   - Phase 1: CREATE LOBBY hosts Team Deathmatch on Showhome directly (NetRequest::Host { map: "showhome" }, today's HostTdm). Change the action help to 'Starts Team Deathmatch on Showhome · first to 50.' (score from rules.ron tdm.score_limit).
   - Phase 2: once the lobby (mockup 06) exists, CREATE LOBBY goes to the lobby, map, mode and score limit are set there, and the mockup copy 'Map, mode and score limit are set in the lobby.' comes back.

H7. The host's own loadout (shown on the player card) is validated against the gear budget like any client's. If it is over budget, the host gets the default loadout; the GEAR readout on the player card warns about this before CREATE LOBBY.

## assets
No images and no icons from icons.svg in this panel. It is built only from nodes, borders and text. Fonts: Barlow Condensed 600/700 and Barlow 400. Glyphs used: U+2212 '−', U+2013 '–', '·', and '•' for the masked password; all are present in Barlow and Barlow Condensed.

