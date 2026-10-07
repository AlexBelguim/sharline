# Settings · Gameplay & Network tab (built from settings.html; no PNG render)

## source_files
[
 "/home/user/sharline/design/ui/mockups/_src/pages/settings.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/settings.html"
]

## purpose
Player name, movement preferences (auto-sprint, jetpack input, slide), the mag-check card duration, and network defaults (host port, net graph). This is the first rail tab. It has no PNG; it was rendered from the source for this spec, and its layout is the same as the other column-card tabs.

## layout
Pane pattern (a). Two 754-wide column cards.

COLUMN A 'GAMEPLAY' (x340)
- h2 y131.
- Rows at y167 (Player name), 231 (Auto-sprint), 295 (Jetpack), 359 (Slide), 423 (Mag check card), on a 64 pitch.
- Controls at x591.

COLUMN B 'NETWORK' (x1118)
- h2 y131.
- Rows at y167 (Default host port), 231 (Show net graph).
- Controls at x1369.

Both cards fill to y976; the space below the rows is empty.

## elements
GAMEPLAY
- 'PLAYER NAME': text field 280x36 at x591 y174, 'KESTREL_YOU'. .inp style: fd 700 18px #F3F0E9, not tabular.
- 'AUTO-SPRINT': switch OFF.
- 'JETPACK': seg 'HOLD JUMP IN AIR' (selected, 144w) | 'SEPARATE KEY' (122w).
- 'SLIDE': seg 'CROUCH WHILE SPRINTING' (selected, 196w) | 'OFF'.
- 'MAG CHECK CARD': seg '3 S' (selected) | 'WHILE HELD'.

NETWORK
- 'DEFAULT HOST PORT': number field '7777'. The mockup stretches it to 482 wide; make it 140x36.
- 'SHOW NET GRAPH': switch OFF.

## data_bindings
SETTINGS: control, range, default
- Player name: text field (EditableText).
  - 1–16 chars, A–Z 0–9 _ - only, forced uppercase.
  - Default: the OS user name uppercased, 'AGENT' if none (config.rs default_name).
  - Writes Session.local_name and Cli.name. --name on the command line overrides it for the run.
- Auto-sprint: switch, default OFF. Holds Buttons::SPRINT while moving forward.
- Jetpack: seg, default HOLD JUMP IN AIR. SEPARATE KEY adds a 'Jetpack (hold)' row to Keybinds.
- Slide: seg CROUCH WHILE SPRINTING / OFF, default CROUCH WHILE SPRINTING.
- Mag check card: seg 3 S / WHILE HELD, default 3 S. Sets how long the HUD mag-check estimate card stays (hud.rs mag check card).
- Default host port: integer field 1024–65535. Default 47820, the game's port from assets/data/net.ron; NOT the mockup's 7777. --port overrides it.
- Show net graph: switch, default OFF. The same setting as Video ▸ Performance overlay '+ NETWORK'.

## interactions
- The name field commits on Enter or blur. Invalid characters are dropped as typed.
- Proposed: show a micro hint 'Applies next time you host or join' under the field while in a match, because names travel in Hello.
- The port field clamps to the range on commit.
- Other controls work as in the shell.

## adaptations
1. PORT: show and default to 47820. DESIGN_DELTAS.md section 5 already records that the mockup's 7777 is wrong. Also fix the stretched field width to 140.
2. The jetpack copy 'HOLD JUMP IN AIR' is close to, but not, the current behaviour (README: press jump again in the air and hold). Either change the game to 'hold jump in air' or relabel the option 'PRESS AGAIN IN AIR'. Raise this with the user rather than guessing.
3. ADD a sub-heading 'RADIAL MENUS', in the Video 'PERFORMANCE OVERLAY' style (h2 with margin-top 12), under the Gameplay rows (y487 onward). Rows:
   - 'RADIAL HOLD TIME', sub-label 'Hold reload or heal this long to open the ring': slider 400 + field 70, 0.10–0.50 s, step 0.05, default '0.20 s'. Today it is the constant RELOAD_HOLD_S in radial.rs; move it to data.
   - 'RADIAL PICK', sub-label 'Mag slot 1 is at the top, then clockwise': seg 'RELEASE' (default) | 'CLICK'. Today the game picks on release; number keys 1–6 pick directly.
   - Proposed 'RADIAL POINTER' slider: deadzone 10–30 mouse counts, default 18 (DEADZONE in radial.rs).
   This serves the new 6-slot ordered magazine direction and the coming heal radial (full-body ring, then region ring).
4. Network extras the game supports that the user may want (optional, proposed): 'LAN beacon port' (47821, from net.ron) as a read-only number. Skip it if the screen should mirror the mockup strictly.

## assets
No images, no icons.

