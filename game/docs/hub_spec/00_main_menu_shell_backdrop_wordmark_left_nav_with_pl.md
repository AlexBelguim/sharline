# Main menu: shell (backdrop, wordmark, left nav with PLAY submenu, player card, agent tag, key hints, version)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/04_main_menu.png",
 "/home/user/sharline/design/ui/mockups/png/04b_main_menu_host.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/main_menu.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/main_menu.html",
 "/home/user/sharline/game/crates/val_etf/src/menu.rs (current implementation, to be replaced)"
]

## purpose
The first screen after launch, shown in AppState::MainMenu and again after leaving a match. It holds everything outside the PLAY flyouts: a full-bleed agent backdrop, the SHARD/LINE wordmark, a big left-hand nav (PLAY with HOST GAME / JOIN GAME sub-items, GUN RANGE, LOADOUT, SETTINGS, QUIT), a player card (name plus loadout summary), the agent and halo tag at bottom-right, centred key hints and a version/network line. The PLAY flyout panel (Host or Join, specified as separate screens) sits to the right of the nav at x=540. It replaces the current debug-style menu in game/crates/val_etf/src/menu.rs (plain HOST GAME / GUN RANGE / join field / QUIT on #090B0F).

## layout
Reference canvas 1920x1080. Every px value maps 1:1 to Val::Px with UiScale = window_height / 1080 (as stated in common.css). All regions are position_type Absolute children of one full-screen root, listed in z-order:

0. ROOT: 100% x 100%, BackgroundColor #07090D (--bg0), DespawnOnExit(AppState::MainMenu).
1. BACKDROP (full-bleed, centred, 'cover'): ImageNode menu_kestrel (1920x1080). To get cover behaviour at any aspect ratio: Node{position Absolute, left 50%, top 50%, width Vw(100), min_width Vh(177.78), min_height Vh(100), aspect_ratio 16/9} with UiTransform translation (-50%,-50%). At 16:9 it fills the canvas exactly. The character (Kestrel with her glowing halo) stands at about x 1100-1420. The art is static.
2. SHADE (full-screen, 0,0 1920x1080): one node with BackgroundGradient holding 2 LinearGradients. Both use the colour rgb(5,7,10), so their order does not matter:
   a) angle LinearGradient::TO_RIGHT (CSS 90deg): stops 0% alpha .96 (#05070AF5), 30% .88 (#05070AE0), 56% .35 (#05070A59), 72% 0 (#05070A00), then transparent to 100%.
   b) angle LinearGradient::TO_TOP (CSS 0deg, starting at the bottom edge): 0% alpha .85 (#05070AD9), 26% 0 (transparent above y≈799).
   The left 30% is almost black, so the nav and flyout read cleanly. The right side shows the art. The bottom band darkens behind the player card, hints and version.
3. LOGO block, anchored top-left: left 96, top 72, auto size ≈484x102 (x 96-580, y 72-174).
   - Wordmark line: x 96, y 72, height 80 (line-height 80).
   - Tagline row: margin-top 6, so y 158-174, height 16, flex row, align centre, column_gap 10. A 40x2 teal bar at (96,165), then the label starting at x 146.
4. NAV, anchored top-left: left 96, top 300, width 400, flex column. Fixed rows, top to bottom:
   - PLAY row y 300-366 (height 66)
   - SUB list y 366-468 (padding top 2, bottom 12, left 44): HOST GAME y 368-412, JOIN GAME y 412-456 (44 each, x from 140)
   - GUN RANGE y 468-534
   - LOADOUT y 534-600
   - SETTINGS y 600-666
   - spacer 18 (y 666-684)
   - QUIT y 684-740 (height 56)
   Each top-level row: flex row, justify space-between, align centre, padding-left 22 (label text starts at x 118), right micro label right-aligned to x 496. Keep the SUB list always expanded so the layout never shifts (the mockup only shows this state).
5. PLAY FLYOUT PANEL: left 540, top 300, width 620, auto height (Join ≈550, ending y≈850; Host ≈494, ending y≈794). See the Host and Join screen specs. Its bottom must stay above y≈910 because it overlaps the player card's x range (540-638).
6. PLAYER CARD, anchored bottom-left: left 96, bottom 60, so y 930-1020, height 90. Auto width (≈534-542 with the mockup copy; cap it at max_width 700 so it never reaches the hints at x 804). Flex row, align centre, column_gap 16, padding 12/18/12/12 (top/right/bottom/left). Portrait 64x64 at (109,943). Text column starts at x 189 and is vertically centred: name line ≈29 tall at y≈951, loadout line 16 tall at y≈982.
7. AGENT TAG, anchored bottom-right: right 120 (right edge x 1800), bottom 120 (bottom edge y 960), ≈242x100 (x≈1558-1800, y 860-960). Flex column, align_items FlexEnd, text right-aligned. Role line y 860-878 (18), name y 878-934 (56), halo row margin-top 10 at y 944-960 (16).
8. KEY HINTS, centred at the bottom: a full-width row (left 0, right 0, bottom 28) with justify Center and column_gap 22. Content ≈312x22 (x≈804-1116, y 1030-1052).
9. VERSION block, anchored bottom-right: right 40 (x 1880), bottom 28. Two right-aligned lines of 13 px height: y 1023-1036, then margin-top 3, y 1039-1052. Width ≈233.
(Do NOT implement the faint bottom-left 'MOCKUP 04 · MAIN MENU · PLAY > JOIN OPEN' label. It is a mockup annotation.)

Other aspect ratios: left-anchored blocks (logo, nav, flyout, player card) keep their left offsets, right-anchored blocks (agent tag, version) keep their right offsets, hints stay centred, and the backdrop stays 'cover'.

## elements
Colour tokens (common.css :root): --bg0 #07090D, --text-hi #F3F0E9, --text #D7D4CD, --text-mid #9CA2AB, --text-low #646B75, --teal #00DACE, --ally #52E5A5, --bad #FF4D5A, --warn #FFA23A, --t1 #EDF1F6, --t2 #59B3FF, --t3 #C46CFF, --t4 #FFCE50, --panel rgba(9,12,17,.70)=#090C11B3, --panel-hi rgba(16,21,29,.82)=#10151DD1, --stroke rgba(255,255,255,.09), --stroke-mid rgba(255,255,255,.16), --stroke-hi rgba(255,255,255,.32).
Fonts: 'BC' = Barlow Condensed (SemiBold 600 and Bold 700 files) and 'Barlow' = Barlow Regular 400. Letter-spacing in CSS em converts to px = em x font-size; use bevy_text LetterSpacing::Px(...). Text set to 'uppercase' must be uppercased in code (Bevy has no text-transform). Numbers that change use font_features 'tnum' (Barlow ships tnum).

WORDMARK 'SHARD/LINE': BC 700, 84 px, LetterSpacing 11.76 px (.14em), LineHeight::Px(80), colour #F3F0E9. The '/' is a TextSpan in --teal #00DACE. Measured box 483.6x80 at (96,72).
TAGLINE BAR: node 40x2, BackgroundColor #00DACE, at (96,165).
TAGLINE TEXT 'WORKING TITLE · PROTOTYPE 0.1' (copy is 'Working title · prototype 0.1', uppercased): class .lbl = BC 600, 13 px, ls 1.82 px (.14em), #9CA2AB, at x 146 y 158.

NAV TOP ITEMS ('PLAY', 'GUN RANGE', 'LOADOUT', 'SETTINGS'): BC 700, 44 px, ls 4.4 px (.1em), uppercase. Row height 66, padding-left 22. Default colour #9CA2AB (--text-mid). Hover: #F3F0E9. Active/focused (.on): #F3F0E9 plus an ACTIVE BAR, absolute left 0, top 14, bottom 14 (4x38 at x 96, e.g. y 314-352 for PLAY), BackgroundColor #00DACE. Exactly one top item is .on; the default is PLAY. No transitions; changes are instant.
NAV RIGHT MICRO LABELS (the CSS <small>): BC 600, 13 px, ls 2.34 px (.18em), uppercase, #646B75, right-aligned at x 496, vertically centred in the row. PLAY carries 'HOST · JOIN' (80.8 wide, x 415-496, y 325). GUN RANGE carries 'OFFLINE' (53.4 wide, x 443-496, y 493); see adaptations for the copy. LOADOUT, SETTINGS and QUIT have none.
SUB ITEMS ('HOST GAME', 'JOIN GAME'): row height 44, x from 140, flex row, align centre, column_gap 12. Text is BC 700, 24 px, ls 3.36 px (.14em), uppercase, starting at x 162. DIAMOND: a 10x10 node rotated 45° (UiTransform rotation; its visual extent is ≈14 px), placed before the text.
   - Selected (.on): diamond filled #F3F0E9, text #F3F0E9.
   - Unselected: diamond hollow (Outline or 1 px border #646B75, no fill), text #9CA2AB.
   - Hover (not in the CSS, recommended): text #F3F0E9, diamond unchanged.
   Mockup 04 has JOIN GAME selected; 04b has HOST GAME selected.
QUIT: BC 700, 32 px, ls 3.2 px (.1em), uppercase, #646B75, row height 56, padding-left 22. In the CSS, .ni.quit outranks .ni:hover, so the mockup's QUIT never brightens. Recommended: #F3F0E9 on hover/focus, plus the active bar when focused by keyboard.

PLAYER CARD: BackgroundColor #090C11B3 (--panel), 1 px border rgba(255,255,255,.09) on all sides, border_radius 2 px.
   - PORTRAIT: 64x64 ImageNode of a pre-masked pointy-top hexagon (polygon 50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%). Bevy has no clip-path, so bake the mask into the PNG alpha.
   - NAME: 'KESTREL_YOU' in BC 700, 24 px, ls 1.92 px (.08em), #F3F0E9. Inline after a space comes the 'EDIT NAME' micro (BC 600, 11 px, ls 1.76 px (.16em), uppercase, #646B75, baseline-aligned, at x≈337). EDIT NAME hover (recommended): #9CA2AB.
   - LOADOUT LINE: margin-top 2. Mockup copy 'Loadout A · Kestrel · AR-7 Mako (holo, angled grip, laser) · T2 Mender, 3 zones' in Barlow 400, 13 px, #9CA2AB, single line (no wrap, clip overflow).
   - New lines for the game (MAGS line, GEAR readout): see adaptations.

AGENT TAG:
   - ROLE: 'RECON · MOBILITY' in BC 600, 15 px, ls 3.3 px (.22em), #00DACE.
   - NAME: 'KESTREL' in BC 700, 56 px, ls 8.96 px (.16em), LineHeight::Px(56), #F3F0E9.
   - HALO ROW: flex row, column_gap 10, justify FlexEnd, align centre, margin-top 10.
     a) TIER CHIP: row with column_gap 3. It holds N pips, where N = tier number (T2 = 2 pips). Each pip is 6x10, skewX(-14°) (a parallelogram ≈8.5 wide visually), coloured with the tier token: T1 #EDF1F6, T2 #59B3FF, T3 #C46CFF, T4 #FFCE50. After a non-breaking space follows the text 'T2 MENDER' in BC 700, 13 px, ls 1.04 px (.08em), in the same tier colour. Measured chip 84.4x16 at x 1590.
     b) '· MEDIUM · AR-7 MAKO' as a micro (BC 600, 11 px, ls 1.76 px, uppercase) coloured #9CA2AB (overrides the micro's default #646B75).

KEY HINTS (three items, column_gap 22). Each is a keycap + 7 px gap + label.
   - KEYCAP (ghost): height 22, min-width 22, padding 0 6, transparent background, 1 px border rgba(255,255,255,.32), border_radius 2, centred text in BC 700, 13 px, ls .52 px (.04em), #F3F0E9.
   - LABEL: BC 600, 14 px, ls 1.96 px (.14em), #9CA2AB.
   - Copy: [↑↓] SELECT (keycap 28 wide, item 82.8), [ENTER] CONFIRM (keycap 47.6, item 111.3), [ESC] BACK (keycap 33.6, item 73.4). Barlow has no ↑/↓ glyphs, so the first keycap needs an icon (see assets).

VERSION: two micro lines (BC 600, 11 px, ls 1.76 px, uppercase, #646B75), right-aligned. Copy: 'V0.1.0-PROTO · BEVY 0.19 · LIGHTYEAR 0.30' and 'REGION: AUTO · RELAY REACHABLE'. Line 2 is replaced in the game; see adaptations.

## data_bindings
- WORDMARK and TAGLINE: static. 'PROTOTYPE 0.1' can come from env!("CARGO_PKG_VERSION") (workspace version 0.1.0), trimmed to major.minor.
- NAV: static items. GUN RANGE right label: see adaptations.
- PLAYER CARD NAME: net::Session.local_name. It comes from --name, else $USER/$USERNAME uppercased, else 'AGENT'. The host truncates to 16 non-control characters (server.rs), so limit editing to 16.
- PLAYER CARD PORTRAIT: static Kestrel portrait. There is no agent selection yet.
- PLAYER CARD LOADOUT LINE: from config::loadout_choice(&cli, &data), the same LoadoutChoice sent in Hello.
   - Weapon name from weapons.ron 'name' ('AR-7 Mako', 'VK-50 Warden', later the SMG).
   - Attachment ids → short labels. attachments.ron has no display names yet: add a 'short' field, or map in code: optic_holo 'holo', mako_stock_standard 'std stock', mag_30 '30 mag'.
   - Armor preset name from armor.ron presets 'name' (e.g. 'Mender Scout') plus per-arc tiers.
   - Proposed copy: 'Default loadout · AR-7 Mako (holo, std stock, 30 mag) · Mender Scout H2 T2'. Name only covered arcs (tier > 0) as H/T/A/L + tier. 'No halo' for arm_none.
   - 'Loadout A' becomes the saved loadout's name once saved loadouts exist; until then 'Default loadout'.
- AGENT TAG ROLE + NAME: static 'RECON · MOBILITY' / 'KESTREL', which matches the backdrop art. There are no agents in code yet.
- AGENT TAG HALO ROW: from the resolved armor preset after loadout_tier_caps.
   - Tier = the HIGHEST arc tier. It sets the pip count, the colour token (t1..t4) and the 'T<n>' text.
   - Core = core name uppercased ('MENDER', 'BULWARK', 'VOLT', 'PHASE').
   - Weight class from armor.ron weight_bands applied to the protection score (sum of arc tiers): 1-4 LIGHT, 5-8 MEDIUM, 9-16 HEAVY.
   - Weapon = weapon name uppercased.
   - The default loadout (Mender Scout, head 2 + torso 2 = 4) therefore reads '[2 pips, #59B3FF] T2 MENDER · LIGHT · AR-7 MAKO'. The mockup's 'MEDIUM' is sample copy; the data wins.
   - If the armor is arm_none: hide the chip and show the micro 'NO HALO · AR-7 MAKO'.
- VERSION line 1: format!("v{} -proto · Bevy 0.19 · lightyear 0.30"), uppercased, using CARGO_PKG_VERSION.
- VERSION line 2: see adaptations (network status).
- STATUS / ERRORS: net::Session.status (for example '"xyz" is not a join code or address' or 'disconnected (Timeout)') shows inside the open flyout (see the Join/Host specs), not in the shell. If no flyout is open, open JOIN GAME to show it.

## interactions
FOCUS MODEL: two zones, the NAV (left) and the FLYOUT (right).
- On entering MainMenu, focus is in the NAV on PLAY (active bar on PLAY). The sub-item selected last time is open (default JOIN GAME, matching mockup 04); remember it per session.
- The SUB list stays expanded, so the layout is fixed.

MOUSE (Button + Interaction on every nav row):
- Hover → text #F3F0E9.
- Click PLAY → focus moves to the selected sub-item.
- Click HOST GAME / JOIN GAME → that item becomes selected (filled diamond), its flyout replaces the other one instantly (no animation in the mockup), and focus goes to the flyout's first field (Host: Lobby name input; Join: the code input of the active tab).
- Click GUN RANGE → NetRequest::Host { map: "range" } (current behaviour), which leads to AppState::Connecting (existing 'CONNECTING...' screen in hud.rs) and then InGame.
- Click LOADOUT → the Loadout screen (mockup 05; needs a new AppState, e.g. AppState::Loadout).
- Click SETTINGS → the Settings screen (mockup 08; new AppState::Settings).
- Click QUIT → AppExit::Success immediately. The mockup has no confirmation.
- Click EDIT NAME (or the name) → the name turns into an EditableText in the same font (BC 700 24 px #F3F0E9) with the teal 2x30 caret; max 16 characters. Enter saves (Session.local_name plus persistence), Esc cancels.

KEYBOARD (matches the hints '↑↓ SELECT · ENTER CONFIRM · ESC BACK'):
- In the NAV: ↑/↓ move focus through PLAY → HOST GAME → JOIN GAME → GUN RANGE → LOADOUT → SETTINGS → QUIT (wrapping).
- The active bar marks the focused top-level item. While focus is on a sub-item, the bar stays on PLAY.
- Moving onto HOST GAME / JOIN GAME also selects it and swaps the flyout (live preview).
- Enter (or →) on a sub-item moves focus into the flyout. Enter on any other item does what a click does.
- In the FLYOUT, Esc returns focus to the NAV (onto the open sub-item). Esc in the NAV does nothing (there is no parent screen).
- Optional extension: while a text field is focused, swap the hints to '[TAB] NEXT · [ENTER] JOIN LOBBY (or CREATE LOBBY) · [ESC] BACK' in the same style.

## adaptations
S1. Replace the current menu.rs layout (HOST GAME and GUN RANGE big buttons, inline join field, 'udp 47820 | playing as X' footer) with this design. Hosting TDM moves under PLAY > HOST GAME, and joining moves under PLAY > JOIN GAME.

S2. GUN RANGE right label: 'OFFLINE' is wrong for this build. The range is hosted as a listen server on UDP 47820 that friends can join (README; Session gets a join code). Use 'FRIENDS CAN JOIN' (≈117 px wide at 13 px/2.34 ls, so it starts at x≈379 and clears the 'GUN RANGE' text, which ends at x≈333). Use 'OFFLINE' only if a socket-less solo range is added later.

S3. VERSION line 2: there is no relay and no region, so 'REGION: AUTO · RELAY REACHABLE' must not be shown.
   - Show the network facts instead: 'UDP 47820 · LAN 192.168.1.23', using the port from --port or net.ron port (47820) and net::local_ipv4().
   - If no route is found (local_ipv4 is None or loopback), show 'UDP 47820 · NO NETWORK' with the second segment in --warn #FFA23A.
   - This replaces the old 'udp 47820' footer.

S4. PLAYER CARD for our loadout model:
   (a) Drop 'Kestrel' from the loadout line (there are no agents in code).
   (b) Add a third text line for the NEW 6-magazine order, so the player sees on the menu which slots hold their high-end mags:
      - margin-top 2, height 15.
      - The micro 'MAGS' (BC 600, 11 px, ls 1.76, #646B75), then 8 px gap, then six slot entries separated by 10 px.
      - Each entry: slot number '1'..'6' in BC 600 12 px #646B75, a 3 px gap, then the ammo label in BC 700 12 px ls .5 px #D7D4CD. Labels come from ammo.ron 'label' plus a roman tier for tiered types: 'STD', 'AP I', 'AP II', 'AP III', 'RIP I'-'RIP III' (SMG only), 'SLUG' (shotgun only).
      - Unused slots show '—' in #646B75.
      - Example: 'MAGS  1 AP III  2 AP III  3 AP II  4 STD  5 STD  6 —'.
      - Until LoadoutChoice carries per-mag ammo (today it has one AmmoChoice plus rules.ron spare_mags 3), show 1 + spare_mags slots, all with the single ammo, and '—' for the rest.
      - The text column is then 29 + 2 + 16 + 2 + 15 = 64, the same as the portrait, so the card keeps its 90 px height.
      - No exact round counts anywhere (genre rule): show mag capacity or type only, never rounds left.
   (c) Add a GEAR BUDGET readout inline after 'EDIT NAME' (margin-left 14):
      - Micro 'GEAR' (BC 600, 11 px, ls 1.76, #9CA2AB), then the numbers 'cost / budget' in BC 700, 13 px, tnum, #F3F0E9. Example: 'GEAR 4 / 12'.
      - budget = rules.ron tdm.gear_budget (12). cost = the same formula the host uses in server.rs loadout_from_choice: resolved armor.gear_cost (sum of capped arc tiers) + ammo gear_cost, later summed over the 6 mags per the loadout screen's rule. Move that formula into vetf_sim so the menu and the host share it.
      - If cost > budget, colour the numbers #FF4D5A and append ' · OVER BUDGET'. The host refuses over-budget loadouts and silently keeps the default, so the warning matters.
      - Hide the readout when the budget does not apply.

S5. AGENT TAG: compute tier, core and weight from data as described in data_bindings. With per-arc tiers the shown tier is the highest arc. The mockup's 'MEDIUM' becomes 'LIGHT' for the default Mender Scout.

S6. LOADOUT and SETTINGS screens do not exist yet (README 'Not done yet'). Until they do, render those rows disabled:
   - Opacity .35 (CSS .btn[disabled] convention), no hover change.
   - Right micro label 'SOON' (same style as 'OFFLINE').
   - Enter/click does nothing.

S7. NAME EDITING needs persistence. Add a small user settings file (e.g. <config dir>/shardline/profile.ron) read at start-up. --name still overrides it. The name must be set before connecting, because Hello carries it.

S8. Text rendering in Bevy 0.19:
   - Use TextFont { font: handle to the right weight file, font_size }, plus the LetterSpacing::Px and LineHeight components (both exist in bevy_text 0.19).
   - Uppercase in code.
   - The ↑↓ glyphs are missing from Barlow / Barlow Condensed (checked: no U+2191/U+2193), so use an icon. U+2212 '−', U+2013 '–', U+2014 '—', '·' and '•' are present.

S9. The CSS skewX tier pips cannot be expressed in Bevy UI (UiTransform has rotation and scale, but no skew). Use a small white parallelogram PNG tinted per tier (ImageNode.color), or accept plain 6x10 rectangles.

S10. No HUD overlays belong here. This is a hub screen only.

## assets
IMAGES (in /home/user/sharline/design/ui/mockups/img):
- menu_kestrel.jpg: 1920x1080 backdrop (Kestrel with her halo in a hangar at sunset). Use it full-bleed with 'cover', centred.
- kestrel_portrait.jpg: 640x640 portrait, shown at 64x64 inside a pointy-top hexagon. Bake the hex mask into a PNG (e.g. 128x128 @2x with alpha). Square into square, so the CSS 'center 20%' position has no effect.

These are placeholder concept art. Bevy's default features do not include JPEG decoding, so either convert both to PNG or enable bevy's 'jpeg' feature. The copies the game uses go in game/assets/ui/. If the art itself must change, note it in the PR (art/ and assets/ belong to the local session).

ICONS (icons.svg): none in the shell itself. Icons needed beyond icons.svg, as white PNGs tinted with ImageNode.color:
(1) an up/down-arrows glyph for the [↑↓] keycap, about 12x12 drawn at 13 px, #F3F0E9;
(2) the tier pip parallelogram, 6x10 skewed -14°, ≈9x10 bounding box (18x20 @2x).
The diamond markers need no asset: use a 10x10 node with UiTransform rotation of 45°.

FONTS (Google Fonts, OFL), to add under game/assets/fonts/:
- BarlowCondensed-SemiBold.ttf (600)
- BarlowCondensed-Bold.ttf (700)
- Barlow-Regular.ttf (400)
Barlow Condensed 500 and Barlow 500-700 are loaded by the mockup but not used on this page.

