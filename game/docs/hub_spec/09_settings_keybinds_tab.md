# Settings · Keybinds tab

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/08b_settings_keybinds.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/settings.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css"
]

## purpose
The full input map: action, primary key, secondary key, and gamepad reference. It shows a listening state and a conflict state. It has to reflect our real controls, including tap/hold reload with the 6-slot magazine radial and the upcoming heal radial.

## layout
Pane pattern (a). Columns flex 1.05 and 1.

CARD A: x340 y112, 771x864, inner x361..1090 (729 wide).
- h2 at y131.
- Table at y167 after the 14px gap.
- Column x/w: ACTION x361 w352 | PRIMARY x713 w158 | SECONDARY x872 w116 | GAMEPAD x987 w103.
- Header row y167 h26.
- Group row MOVEMENT y193 h34.
- Action rows h38 at y227, 265, 303, 341, 379.
- Group COMBAT y417.
- Rows at y451, 489, 527, 565, 603, 641, 679, 717 (table ends y755).

CARD B: x1135 y112, 737x864, inner x1156..1851 (695 wide). No h2: the table starts at y131.
- Column x/w: ACTION x1156 w303 | PRIMARY x1459 w116 | SECONDARY x1575 w125 | GAMEPAD x1700 w151.
- Header y131.
- ABILITIES y157, rows at 191, 229, 267.
- ITEMS & HEALTH y305, rows at 339, 377, 415.
- INTERFACE y453, rows at 487, 525, 563, 601, 639 (ends y677).
- Footnote pinned to the bottom (margin-top auto): x1156 y909, 695x48.

In Bevy, make each table a Display::Grid with the fixed column widths above; the last column can be 1fr. Cells have padding 0 10, so key caps start at column x + 10.

## elements
CARD A
- h2 'KEYBOARD & MOUSE'. Right micro 'CLICK A KEY TO REBIND · BACKSPACE CLEARS · ESC CANCELS' (x766 y138).

TABLE STYLES
- Header cells: fd 600, 12px, ls .16em (1.92px), uppercase, --text-mid #9CA2AB, padding 6 10, left-aligned. Text: 'ACTION', 'PRIMARY', 'SECONDARY', 'GAMEPAD'.
- Group rows span all columns: fd 700, 13px, ls .18em (2.34px), #F3F0E9, padding-top 12, height 34, no border.
- Action rows: height 38, border-top 1px rgba(255,255,255,.09).
  - Action text: Barlow 400, 14.5px, --text #D7D4CD.
  - Gamepad cells: fd 600, 14px, --text-mid.
- Key cap (.kc): inline-flex, min-width 44, height 28, padding 0 10, vertically centred in the 38 row (y+5). Border 1px rgba(255,255,255,.32), no bg. Text fd 700, 15px, ls .04em (0.6px), #F3F0E9. Two caps in one cell sit 4px apart.
  - Unbound: '—', text --text-low #646B75, border dashed (see shell adaptation 2).
  - Listening: 'PRESS A KEY…', border and text --teal #00DACE, opacity pulsing 1 → .35 → 1 over 1 s, 108 wide in the mockup.
  - Conflict: border and text --warn #FFA23A. The action text also gets an inline note in --warn at 12.5px, e.g. '· V is also Laser'.

MOCKUP ROWS (as drawn: action | primary | secondary | gamepad)
MOVEMENT
- Move | W A S D | — | Left stick
- Jump · hold in air: jetpack | SPACE | WHEEL ↓ | A / ✕
- Sprint (hold) | L-SHIFT | — | L3 click
- Crouch · while sprinting: slide | L-CTRL | C | B / ◯
- Interact · grab zipline · revive | F | — | X / ▢ hold
COMBAT
- Fire · aim down sights | LMB RMB | — | RT · LT
- Reload · double-tap: fast reload (drop mag) | R | — | X / ▢ tap
- Mag check (bold #F3F0E9, shown listening) | PRESS A KEY… | — | D-pad ↑
- Fire mode | B | — | D-pad ↑ hold
- Underbarrel launcher | G | — | D-pad →
- Laser / flashlight | V | — | D-pad ↓
- Melee · V is also Laser (conflict demo) | V (amber) | 3 | R3 tap
- Hold breath (Warden scope) | L-SHIFT | — | L3 while ADS

CARD B (table only)
ABILITIES
- Ability 1 (Grapple · Mend Drone) | Q | — | LB / L1
- Signature (Scan · Triage Pulse) | E | — | RB / R1
- Ultimate | X | — | LB + RB
ITEMS & HEALTH
- Bandage (stops bleeding) | 4 | — | D-pad ← tap
- Med-stim | 5 | — | D-pad ← hold
- Health panel (hold) | H | — | View tap (toggle)
INTERFACE
- Scoreboard (hold) | TAB | — | View hold
- Ping / mark | MMB | Z | R3 hold
- Team chat · all chat | ENTER | Y | —
- Change loadout (when dead) | L | — | Y / △
- Match menu | ESC | — | Menu / Options

FOOTNOTE (.note): 'Conflicts are allowed only between contexts that never run at once (Sprint and Hold breath share Shift because you cannot sprint while aiming). Any other clash turns the key amber and names the other action.'

## data_bindings
Keybinds live in Settings.keybinds: action → [primary, secondary], each an Option<Binding>. A Binding is KeyCode, MouseButton, or WheelUp/WheelDown.
- client.rs gather_input and reload_input must read these instead of the hard-coded KeyCodes.
- Mouse wheel bindings need the MouseWheel / AccumulatedMouseScroll input, since there is no ButtonInput for the wheel.
- 'Move' is a composite of four keys (forward/left/back/right) shown as one cap.

Display names: ShiftLeft 'L-SHIFT', ControlLeft 'L-CTRL', AltLeft 'L-ALT', Space 'SPACE', Tab 'TAB', Enter 'ENTER', Escape 'ESC', Backspace 'BKSP', letters and digits as the character, Mouse Left/Right/Middle 'LMB'/'RMB'/'MMB', Back/Forward 'M4'/'M5', wheel 'WHEEL ↑'/'WHEEL ↓'.

Defaults must equal today's game controls (client.rs, README):
- W A S D move; SPACE jump/jetpack; L-SHIFT sprint; L-ALT walk; L-CTRL and C crouch/slide; F interact/zipline
- LMB fire; RMB ADS; R reload; T mag check; B fire mode; TAB scoreboard + join code; ESC match menu
- 1–6 pick a slot while the reload radial is open

Gamepad column: the game reads no gamepad yet. Show the strings as a static, non-interactive reference.

## interactions
- Clicking a key cap puts it into listening state. The next key, mouse button or wheel input binds it.
  - BACKSPACE clears the binding to '—'.
  - ESC cancels.
  - Clicking another cap moves listening to that cap.
  - Clicking 'Move' listens for four keys in sequence (FORWARD…, LEFT…, BACK…, RIGHT…) inside the same cap.
- After binding, run the conflict check per input context:
  - a clash within the same context turns both caps --warn and appends '· <KEY> is also <Other action>' to the later row
  - allowed shares (no warning): Sprint and Hold breath (Shift); digits 1–6 (only active while a radial is open) with item and other keys
- ESC (Match menu) and the settings-screen hotkeys are fixed: ESC cannot be bound, and the Match menu row shows ESC as a static cap.
- R (reset tab) restores the default bindings.
- Bindings apply immediately in match.

## adaptations
CHANGE THE ROWS TO MATCH OUR GAME. Left card in order:
MOVEMENT
- Move: W A S D | — | Left stick
- 'Jump · in air, press again and hold: jetpack': SPACE | WHEEL ↓ | A / ✕. Our jetpack is a second press held in the air. If the Gameplay 'Jetpack' setting is SEPARATE KEY, insert a 'Jetpack (hold)' row here, default unbound.
- Sprint (hold): L-SHIFT
- ADD 'Walk (silent)': L-ALT | — | —. The game has it; the mockup lacks it.
- Crouch · while sprinting: slide: L-CTRL | C
- Interact · grab zipline · revive: F. 'Revive' is not in the game yet; keep the copy.
COMBAT
- Fire · aim down sights: LMB RMB. Each cap rebinds its own action.
- 'Reload · tap: next mag in order · hold: mag radial': R | — | X / ▢. This REPLACES 'double-tap: fast reload (drop mag)', which the game does not have. Tap loads the next slot in order. Holding 0.2 s opens the 6-slot ring with slot 1 at the top, clockwise.
- ADD 'Pick mag (radial open)': a single static cap '1 – 6' in --text-mid, not rebindable. The user wants players to learn which slot holds their high-end mags.
- Mag check: default T (README/client.rs). The mockup shows this row in the listening state as a demo.
- Fire mode: B
- Underbarrel launcher G, Laser / flashlight V, Melee, Hold breath L-SHIFT: these features are not in the prototype. Keep the rows bindable, but show the action text in --text-mid with a trailing micro tag 'LATER' (fd 600 11px ls .16em #646B75).
- Melee default: '3' as primary, unbound secondary. The amber V in the mockup is only a conflict demo, so do not ship a conflicting default.

Right card:
- ABILITIES rows (Q, E, X): abilities are not built yet, so use the 'LATER' styling.
- ITEMS & HEALTH: REPLACE Bandage 4 and Med-stim 5 with one row 'Heal · hold: item radial · tap: last item': 4 | — | D-pad ← hold. This follows the new direction that healing items are used from a radial: the first ring holds full-body items, then a second ring holds per-region items.
- Keep 'Health panel (hold)': H.
- INTERFACE:
  - 'Scoreboard + join code (hold)': TAB. Our scoreboard shows the join code.
  - Ping / mark, Team chat, and Change loadout (when dead) are 'LATER' until those features exist.
  - Match menu: ESC, fixed.
- Extend the footnote: 'Number keys 1–6 pick magazines only while the reload radial is open.'

GLYPHS: ↓ ↑ ← → ✕ ◯ ▢ △ need a symbol font or PNGs (shell adaptation 1). Fallback text: 'WHEEL DN', 'D-pad UP', 'A / X', 'B / O', 'X / SQ', 'Y / TRI'.

SPACE: the extra rows still fit. Left table about 26+34+6×38+34+9×38 = 664 px, ending y831 of 957 available.

## assets
No images. No icons.svg icons. Dashed-cap 9-slice PNG (for unbound '—'). Symbol glyphs (arrows, ✕ ◯ ▢ △) as a font span or 14px PNGs.

