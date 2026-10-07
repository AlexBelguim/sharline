# Main menu: PLAY > JOIN GAME flyout (tabs JOIN CODE / DIRECT IP / ON YOUR NETWORK, plus RECENT list)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/04_main_menu.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/main_menu.html (the .fly.join-only block, .tabs/.field/.input/.list/.li styles)",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg (i-copy)",
 "/home/user/sharline/game/crates/vetf_net/src/join_code.rs",
 "/home/user/sharline/game/crates/val_etf/src/net.rs"
]

## purpose
The panel for joining a friend's listen server: by join code (default tab), by direct IP, or by picking a host found on the LAN, plus a list of recent games to rejoin. It is shown to the right of the nav while PLAY > JOIN GAME is selected. This is the default flyout (mockup 04).

## layout
PANEL anchored top-left: left 540, top 300, width 620, auto height (≈550 with 3 recent rows, so y 300-850).
- Padding 26 top, 28 left/right, 24 bottom.
- Borders: top 2 px teal, the others 1 px. Content box x 569-1131 (width 562), starting at y 328.

Content, flex column (absolute y):
1. TITLE 'JOIN GAME' [y 328-364].
2. TAB ROW, margin-top 18 [y 382-422]: flex row, no gap, full width, with a 1 px bottom border across all 562 px at y 421.
   - Tab boxes (height 39): JOIN CODE x 569-688 (119 wide), DIRECT IP x 688-802 (114), ON YOUR NETWORK (1) x 802-1015.7 (213.6).
3. FIELD (JOIN CODE tab), margin-top 18 [y 440-565.7]:
   - label [y 440-456];
   - input, margin-top 8, 562x56 [y 464-520], with the PASTE button inside at its right edge (93.4x36 at x 1020.6-1114, y 474-510);
   - help, margin-top 8 [y 528-565.7, 2 lines].
4. ACTION ROW, margin-top 18 [y 583.7-635.7]: flex row, align centre, column_gap 12.
   - JOIN LOBBY button 175x52 at x 569-744.
   - ENTER keycap 45.6x22 at x 756, y 598.7-620.7.
5. RECENT, margin-top 26 [y 661.7-824.7]:
   - header row, space-between, height 16 [y 661.7-677.7]: 'RECENT' on the left, 'PING · PLAYERS' on the right ending at x 1131;
   - list, margin-top 8, with a 1 px top border at y 685.7;
   - 3 rows of 46 (each including a 1 px bottom border) at y 686.7, 732.7 and 778.7, the last ending at 824.7.
6. Bottom padding 24 plus a 1 px border, so the panel ends at y≈850.

Row grid (CSS grid-template-columns 1fr 110px 70px 60px, padding 0 10 horizontal): name column x 579-881 (302), ping x 881-991 (110), players x 991-1061 (70), status x 1061-1121 (60). Columns 2-4 are right-aligned. In the name column, the bold name sits at y+5.5 (20 tall) and the subline directly below (14 tall).

DIRECT IP tab (not drawn in the mockup; same skeleton): identical geometry to JOIN CODE. Only the label, the value letter-spacing and the help copy change (see elements).

ON YOUR NETWORK tab (not drawn): the FIELD block (3) becomes a one-line help [y 440-459], then the ACTION ROW, then the list block (5) titled 'ON THIS NETWORK' in place of 'RECENT', with the same row grid. Recent is hidden on this tab so the panel height stays about the same.

Cap visible rows at 3 (Recent: the 3 most recent; LAN: Overflow::scroll_y beyond 3). That keeps the panel bottom ≤ ≈850, clear of the player card at y 930.

## elements
PANEL: same as the Host panel.
- Background #10151DD1 (rgba(16,21,29,.82)).
- 1 px rgba(255,255,255,.09) border on left, right and bottom; 2 px #00DACE top border; radius 2.

TITLE 'JOIN GAME': BC 700, 30 px, ls 3.6 px (.12em), #F3F0E9.

TABS:
- Each tab: padding 10 vertical, 18 horizontal; text BC 700, 16 px, ls 2.56 px (.16em). Copy is uppercase: 'JOIN CODE', 'DIRECT IP', 'ON YOUR NETWORK (1)'.
- Unselected: #9CA2AB. Selected: #F3F0E9 plus a 2 px underline #F3F0E9 across the tab's full width at its bottom (the CSS inset box-shadow 0 -2px). In Bevy: a 2 px bottom border, or an absolute child bottom 0, height 2.
- The row's bottom rule: 1 px rgba(255,255,255,.16) (--stroke-mid) across the full 562 px.
- Hover on an unselected tab (recommended): #F3F0E9.

FIELD LABEL (.lbl): BC 600, 13 px, ls 1.82 px, uppercase, #9CA2AB.
- JOIN CODE tab: 'CODE FROM YOUR HOST'.
- DIRECT IP tab: 'HOST ADDRESS'.

CODE INPUT (.input):
- 562x56, padding 0 16 (horizontal), background rgba(0,0,0,.45), border 1 px rgba(255,255,255,.32), radius 0, flex row, align centre.
- Value: BC 700, 30 px, ls 7.2 px (.24em), #F3F0E9, tnum. Mockup value 'SHRD-4K7Q'.
- CARET (when focused): 2x30, #00DACE, margin-left 4. Blinks with steps: opacity 1 for 0.5 s, then .35 for 0.5 s.
- On the DIRECT IP tab use ls 2.4 px (.08em), so '255.255.255.255:65535' fits beside the PASTE button.

PASTE BUTTON (.btn, sized down), pushed right with margin-left auto:
- 36 tall, padding 0 12 (horizontal), column_gap 10.
- Icon i-copy 16x16 tinted #F3F0E9, then 'PASTE' in BC 700, 14 px, ls 1.68 px (.12em), uppercase, #F3F0E9.
- Background rgba(255,255,255,.06), border 1 px rgba(255,255,255,.16), radius 0.
- Hover: background rgba(255,255,255,.12), border rgba(255,255,255,.32).

HELP: Barlow 400, 13 px, LineHeight 1.45 (18.85), #9CA2AB, wrapping in 562 px.
- Mockup copy: '8 characters, not case-sensitive, dash optional. The code finds the host's lobby; you never need their IP address.' This must change; see adaptations.

JOIN LOBBY (primary):
- 52 tall, padding 0 34 (horizontal), about 175 wide.
- Text BC 700, 20 px, ls 2.4 px, uppercase, #07090D.
- Background #F3F0E9, border 1 px #F3F0E9, radius 0.
- Hover: background #FFFFFF. Disabled: opacity .35. Pressed (recommended): background #DAD6CB.

ENTER KEYCAP (solid .key), next to the button:
- 22 tall, min-width 22, padding 0 6, background #F3F0E9, radius 2.
- Text 'ENTER' in BC 700, 13 px, ls .52 px, #07090D.
- It is only a hint and not clickable.

RECENT HEADER:
- Left: 'RECENT' (.lbl).
- Right: 'PING · PLAYERS' micro (BC 600, 11 px, ls 1.76 px, uppercase, #646B75). It is right-aligned to the panel edge, not to the columns.

LIST: 1 px top border rgba(255,255,255,.09).

ROW (.li):
- 46 tall, 1 px bottom border rgba(255,255,255,.09). Hover: background rgba(255,255,255,.05).
- NAME: BC 700, 17 px, ls 1.02 px (.06em), #F3F0E9.
- SUBLINE: Barlow 400, 12 px, #9CA2AB.
- PING and PLAYERS: BC 600, 15 px, #9CA2AB, tnum, right-aligned.
- STATUS: BC 600, 15 px, right-aligned. 'OPEN' and 'LAN' in #52E5A5 (--ally); 'OFFLINE' in #646B75.
- Missing values: '—' (U+2014) in #9CA2AB.

Mockup rows:
1. 'ASH'S GAME' / 'TDM · Showhome · code SHRD-4K7Q' / '34 ms' / '7/10' / 'OPEN'
2. 'JUNO · RANGE NIGHT' / 'Gun range · 192.168.1.40:7777' / '2 ms' / '2/4' / 'LAN'
3. 'PIKE'S SERVER' / 'TDM · last seen 2 days ago' / '—' / '—' / 'OFFLINE'

The tab count '(1)' means one LAN host was found.

## data_bindings
- CODE INPUT value: the text the player types, pastes, or fills from a Recent row. On submit it is sent as NetRequest::Join { address }. JoinCode::parse accepts:
   - a 10-character Crockford code 'XXXX-XXXX-XX', case-insensitive, dashes and spaces optional, O→0 and I/L→1;
   - ip:port;
   - a bare IPv4 address (the default port, 47820, is added).
- DIRECT IP value: the same parser and the same request. The tab only changes labels and help.
- ON YOUR NETWORK: results of the LAN beacon (net.ron lan_beacon_port 47821), which is NOT built yet.
   - Each host's reply should carry lobby name, mode, map name, ip:port, players/max, and a measured ping.
   - The tab label is 'ON YOUR NETWORK (n)' when n > 0, otherwise 'ON YOUR NETWORK'.
- RECENT: a new persisted list (e.g. <config dir>/shardline/recent.ron) of { display name, mode, map, address or code, last_joined unix time }.
   - Write an entry after a successful join, i.e. on reaching AppState::InGame as a client.
   - Name: the lobby name once replicated; until then format!("{}'S GAME", host player's PlayerInfo.name), the host being player id 0.
   - Mode/map: from the match state / CurrentLevel name ('showhome' → 'TDM · Showhome', 'range' → 'Gun range').
   - Subline: '<mode> · <map> · code <code>', or '· <ip:port>' if the entry was joined by IP. If last_joined is more than a day ago: '<mode> · last seen N days ago'.
   - PING and PLAYERS need a status query to the host, which does not exist yet, so show '—' for both.
   - STATUS: show 'LAN' (#52E5A5) when the address is private (10/8, 172.16/12, 192.168/16, or 100.64/10 for Tailscale-style meshes). Otherwise show '—' (#646B75) until a query can report 'OPEN' or 'OFFLINE'.
- ERRORS: net::Session.status (set by handle_requests or on disconnect, e.g. '"abc" is not a join code or address', 'disconnected (Timeout)'). See interactions.

## interactions
- Opening: selecting JOIN GAME in the nav shows this panel. Entering it (Enter, →, or a click) focuses the active tab's input; the default tab is JOIN CODE.
- TABS: click to switch, or use ←/→ while the tab row has focus. Switching keeps the typed text per tab.
- PASTE (click, or Ctrl+V in the field):
   - reads the OS clipboard (bevy_clipboard with the 'system_clipboard' feature, which EditableText already uses for Ctrl+V);
   - trims whitespace;
   - on the JOIN CODE tab, uppercases the text;
   - replaces the field value and places the caret at the end.
- JOIN LOBBY (click, or Enter while the input is focused, as the ENTER keycap shows):
   - Empty field: no request; show the error 'Type a join code or address first.'
   - Otherwise send NetRequest::Join { address }. On success the game moves to AppState::Connecting (existing screen), then InGame. While connecting the menu is gone.
- RECENT / LAN ROW:
   - Hover: background rgba(255,255,255,.05).
   - Single click fills the active input with the row's code or address (switching to JOIN CODE or DIRECT IP to match) and focuses JOIN LOBBY. Mark the row selected with background rgba(255,255,255,.08) (recommended).
   - Double-click, or Enter on a focused row, joins immediately.
   - ↑/↓ move between rows when the list has focus.
   - Rows of any status can be tried.
- Focus order (Tab): tabs → input → PASTE → JOIN LOBBY → list rows.
- Esc returns focus to the nav (onto JOIN GAME).
- ERROR STATE (Session.status is Some while this panel is visible; also when the menu is re-entered after a disconnect, in which case open this panel automatically):
   - the input border turns #FF4D5A;
   - the help text is replaced by the message in Barlow 400 13 px #FF4D5A;
   - typing clears the error and restores the help copy.
- No animations except the caret blink.

## adaptations
J1. CODE FORMAT: real codes are 10 characters, 'XXXX-XXXX-XX' (e.g. '6000-105E-PC'), not 8 like 'SHRD-4K7Q'. At 30 px with .24em spacing, 12 characters ≈ 270 px, which still fits.
   - Use a real-format example wherever sample copy is needed. Leave the field empty by default, with the placeholder 'XXXX-XXXX-XX' in #646B75 in the same font.
   - Help copy must change because the code IS the address (no relay or lobby lookup): '10 characters, not case-sensitive, dashes optional. The code holds the host's address and port, so an IP address works here too.'

J2. DIRECT IP tab copy:
   - Label: 'HOST ADDRESS'.
   - Placeholder: '192.168.1.20 or 192.168.1.20:47820'.
   - Help: 'IPv4 address, with :port if the host changed it (default 47820). Over the internet the host must forward UDP 47820, or you both join a VPN mesh (Tailscale, ZeroTier, Radmin) and use their VPN address.'
   - Both tabs call the same JoinCode::parse, so a code typed here also works.

J3. ON YOUR NETWORK needs the LAN beacon (net.ron lan_beacon_port 47821), which is not implemented. Until it is:
   - the tab reads 'ON YOUR NETWORK' with no count;
   - its body shows one 46 px row of Barlow 13 px #9CA2AB: 'LAN discovery isn't built yet. Ask the host for their join code (TAB or ESC in their match shows it).';
   - JOIN LOBBY is disabled (opacity .35) on this tab.
   Once built: help line 'Games on this network answer automatically. Pick one and press JOIN LOBBY.', rows as specified, and status 'LAN'.

J4. RECENT needs new persistence plus a host status query. Without the query, ping and players show '—'. The status column uses 'LAN' for private addresses, else '—'; 'OPEN' and 'OFFLINE' appear only once a query exists.
   - Empty state (no entries): one 46 px row, Barlow 13 px #9CA2AB, 'Games you join show up here.'
   - Cap at 3 rows.

J5. Recent sublines show the real code or ip:port and the real map labels ('TDM · Showhome', 'Gun range'). The mockup's 7777 port examples become 47820.

J6. Errors that today appear as a red status line in menu.rs move into this panel's help slot, styled as above.

J7. Remove today's inline join field ('Enter a join code (XXXX-XXXX-XX) or an IP address...') from the menu root. This panel replaces it.

## assets
ICON from /home/user/sharline/design/ui/mockups/_src/icons.svg:
- 'i-copy' (viewBox 24x24; a stroked rect plus an L-shaped stroke, stroke-width 2) in the PASTE button at 16x16, colour #F3F0E9.
- Bevy UI has no SVG support, so rasterise it to a white PNG (e.g. 32x32 @2x, so strokes come out about 1.33 px at 16 px) and tint it with ImageNode.color.

No images. Fonts: Barlow Condensed 600/700 and Barlow 400. Glyphs: '·', '—' and '–', all present.

