# ESC menu: Stop hosting confirm modal (and reused Leave / Restart confirms)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/09b_esc_stop_hosting.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/esc_menu.html"
]

## purpose
A destructive-action confirmation shown over the ESC menu when the host picks STOP HOSTING. The same component is reused for a client's LEAVE MATCH and the host's RESTART MATCH (with different copy and accent).

## layout
1. BACKDROP: a full-screen Node above the whole ESC menu, background rgba(0,0,0,0.6). It dims the menu and the info card too.

2. MODAL: centred on screen (left 50%, top 50%, translate -50%/-50%), width 620, height 222 (content-driven), so x 650-1270, y 429-651.
   - Background solid #11161D (overrides panel-hi).
   - 1px border --stroke on the left, right and bottom; 3px top border --enemy #FF4D5A; radius 2.
   - Padding 28 top/bottom, 30 left/right. Inner content x 681-1239 (558 wide).

3. CONTENTS (top to bottom):
   - Title h3 at y460, h38.
   - Body paragraph at y508, h48 (two 24 px lines), margin-top 10.
   - Action row at y578, h44, margin-top 22: right-aligned, gap 12.
     - CANCEL button x911.3, w152.
     - STOP HOSTING button x1075.4, w163.6, right edge 1239.

## elements
TITLE h3
- Style: BC 700 32px, .1em (3.2px), --text-hi #F3F0E9.
- Copy: 'STOP HOSTING?'.

BODY p
- Style: Barlow 400 16px, line-height 24 (1.5), colour --text #D7D4CD, wraps at 558 px.
- Copy: 'The match ends for all 9 other players and everyone returns to the main menu. Scores are not saved.' The mockup wraps after 'main menu.'

CANCEL BUTTON (.btn)
- Style: h44, padding 0 22, gap 10; bg rgba(255,255,255,0.06), 1px --stroke-mid.
- Label: 'CANCEL' in BC 700 18px .12em (2.16px) --text-hi, followed by a ghost keycap 'ESC' 33.1x20 (at x1007.3, y590).
- Hover/focus: bg rgba(255,255,255,0.12), border --stroke-hi.

CONFIRM BUTTON
- Style: h44, padding 0 22; bg #FF4D5A, border #FF4D5A.
- Label: 'STOP HOSTING' in BC 700 18px .12em, colour #1B0507.
- Hover/focus: bg #FF6170 (not in the mockup).
- Keyboard focus ring (not in the mockup): Outline 2px --text-hi, offset 2, on the focused button.

## data_bindings
OTHER-PLAYER COUNT
- '{n}' = connected players minus the host. Singular: 'for the 1 other player'.
- n = 0 -> body 'No one else is connected. The match ends and you return to the main menu.'
- Scores are not persisted anywhere today, so 'Scores are not saved.' is accurate.

## interactions
- Opens with focus on CANCEL (the safe default).
- Esc or a click on CANCEL closes the modal and returns to the ESC menu with STOP HOSTING still selected.
- Left/Right (or Tab) moves focus between the two buttons. Enter activates the focused button.
- Clicking the dim backdrop does nothing.
- Confirm: send a HostClosing message to clients, then NetRequest::Leave { reason: None }. The host ends on the main menu.
- The bottom-left ESC-menu hints stay visible under the dim; do not change them.

## adaptations
Reuse this component with the copy and accents below.

1. CLIENT LEAVE
   - Title 'LEAVE MATCH?'.
   - Body 'You return to the main menu. The match keeps running for everyone else, and you can rejoin with the join code.'
   - Confirm label 'LEAVE MATCH', same red styling.

2. HOST RESTART
   - Accent: 3px top border --warn #FFA23A instead of red.
   - Title 'RESTART MATCH?'.
   - Body 'Scores reset to 0 - 0, the clock restarts and everyone respawns. No one is disconnected.'
   - Confirm label 'RESTART': solid --text-hi background, --bg0 text (the .btn.primary style); hover #FFFFFF.

None of these extra variants is drawn in the mockup; they follow the same geometry.

## assets
None. The keycap is drawn with a Node and border, no image.

