# Loadout · attachment list popover (and the magazine ammo picker that reuses it)

## source_files
[
 "/home/user/sharline/design/ui/mockups/png/05b_loadout_attachment_list.png",
 "/home/user/sharline/design/ui/mockups/_src/pages/loadout.html",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg",
 "/home/user/sharline/design/ui/mockups/loadout.html"
]

## purpose
A non-modal popover on the Loadout screen. It opens when the player clicks an attachment slot card or its hotspot in the preview.
- It lists every part that fits the slot, each with a one-line description and its two biggest stat changes.
- Hovering a row previews the part on the 3D model and in the stats panel. Clicking a row equips it.

The same component is reused as the AMMO PICKER for a magazine card in the new 6-slot load-order strip. The mockup source is the .alist block in loadout.html (CSS lines 70-81, markup lines 183-191), shown with the URL hash #attach.

## layout
MOCKUP PLACEMENT
- Box: absolute, left 446, top 330, width 420. Height follows the content: 51 + 70 × rows.
  - With 5 rows that is 401, so the box spans y 330-731. Its bottom edge overlaps the attachment slot row's top border by 1px.
- It is NOT aligned horizontally with the open slot: UNDER is column 4 at x 871, while the popover spans x 446-866.
- It covers the left part of the preview and is drawn above everything with a GlobalZIndex.
- The rest of the page stays interactive.

ADAPTED PLACEMENT
The preview now spans y 180-610 and the slot row starts at y 620.
- Attachment list: left 446, width 420, bottom edge at y 621 (1px over the slot row). With 5 rows it spans y 220-621.
- Ammo picker: same left and width, bottom edge at y 731 (1px over the mag cards).
  - Mako has 5 rows (NO MAG, STANDARD, AP I-III), so the picker spans y 330-731. That is exactly the mockup's box.
- More than 6 rows (the SMG has 8): use compact rows, padding 6 (58 tall + 4 gap). Height = 51 + 62 × 8 = 547, so y 184-731.
- If a list would ever pass y 100, clip it and make it scroll with the mouse wheel.

INTERNAL LAYOUT
- Padding 12.
- Header row: margin 2 4 6, about 24px tall including the margins.
- Rows: each 396x66 with margin-top 4.
- Measured row tops in the mockup: y 372, 442, 512, 582, 652. The equipped row is at 512-578 and the hovered row at 652-718.

## elements
Copy is shown between “ and ”; those marks are not part of the copy. BC = Barlow Condensed. ls = letter-spacing in px.

1. CONTAINER (PANEL-HI)
   - bg --panel-hi rgba(16,21,29,.82). Border 1px --stroke rgba(255,255,255,.09), radius 2.
   - The top border is 2px --teal #00DACE. In Bevy: border widths top 2, others 1; BorderColor top --teal, other sides --stroke.
   - BoxShadow: offset (0, 20), blur 60, rgba(0,0,0,.6).
   - The panel is translucent, so the preview's hotspot tags and hint row show through faintly. The PNG shows this; keep it.

2. HEADER
   - Flex row, space-between, baseline aligned.
   - Left: BC 700 17px, ls 3.06, --text-hi, copy “UNDER · 5 PARTS”.
   - Right: MICRO (BC 600 11px, ls 1.76, --text-low, UPPER), copy “HOVER = PREVIEW + STAT DELTA”.

3. ROW
   - Grid of 44 | 1fr | auto, gap 12, align centre. Padding 10, border 1px transparent.
   a) Icon box:
      - 44x44, bg rgba(255,255,255,.05).
      - A 28x28 glyph tinted --text-hi, centred.
      - The UGL row uses i-gl drawn at 34x17.
      - The NONE row shows an em dash “—” in --text-low.
   b) Name: BC 700 17px, ls 1.02, --text-hi.
      - The equipped row appends i-check: 14x14, --teal, gap 4, nudged 2px down.
   c) Description: Barlow 400 12.5px, --text-mid, margin-top 1, one line.
      - It can contain an inline KEYCAP-GHOST: height 16, min-width 16, 11px text. Example: the UGL row's “G”.
   d) Delta column: BC 600 13px, ls 0.78, UPPER, right-aligned, line-height 17, at most 2 lines.
      - Each line is --good #52E5A5 if better, --bad #FF4D5A if worse, --text-mid #9CA2AB if neutral.
   e) States:
      - Default: transparent border.
      - EQUIPPED: border --stroke-mid rgba(255,255,255,.16), bg rgba(255,255,255,.04).
      - HOVER or keyboard focus: border --text-hi #F3F0E9, bg rgba(255,255,255,.08).
      - Hovering the equipped row: the hover style wins and the check mark stays.

4. MOCKUP COPY (UNDER slot on the Mako, top to bottom)
Each row: name / description / delta line 1 / delta line 2.
   1. “NONE” / “Lightest. Best sprint-to-fire.” / “ADS −0.03 S” (good) / “RECOIL +6 %” (bad)
   2. “VERTICAL GRIP” / “Steady full-auto sprays.” / “RECOIL V −8 %” (good) / “ADS +0.01 S” (bad)
   3. “ANGLED GRIP” + check (EQUIPPED) / “Equipped. Fast to aim.” / “ADS −0.02 S” (good) / “RECOIL V −4 %” (good)
   4. “STUB GRIP” / “Hand stop. Less sway.” / “SWAY −6 %” (good) / “NO ADS CHANGE” (neutral)
   5. “UGL-40 LAUNCHER” (HOVERED) / “1 grenade loaded, 2 spare. [G] to switch.” / “ADS +0.04 S” (bad) / “HANDLING −10” (bad)

5. AMMO PICKER VARIANT (new, opened from a magazine card)
   - Header: “MAG {n} · AMMO”, with MICRO “HOVER = STAT DELTA · COST”.
   - Rows, in this order:
     a) MAG 2-6 only: “NO MAG” / “Leave this slot empty.” / no deltas.
     b) “STANDARD” / “Baseline round.” / “BASELINE” (neutral).
     c) “AP I”, “AP II”, “AP III” / “Armor-piercing. Shield breaker.” / “SHIELD ×1.30” (good) + “DAMAGE +5 %” (good). AP II gives ×1.60 / +10 %, AP III gives ×2.00 / +15 %.
     d) SMG only: “RIP I”, “RIP II”, “RIP III” / “Expanding. Shreds flesh, weak into shields.” / “FLESH +12 %” (good) + “SHIELD ×0.85” (bad). Use the data values for each tier.
     e) Shotgun only: “SLUG I”, “SLUG II” / “One heavy projectile.” / “DAMAGE ×1.80” (good) + “SHIELD ×0.80” (bad).
   - Icon box: the i-mag glyph (16x28) tinted with the ammo colour. The colours are STANDARD #C4BFB5, AP #B3EDFF, RIP #FF8C7A, SLUG #A29076.
   - Name in --text-hi, followed by:
     - tier pips in the ammo colour;
     - a cost chip “{cost} PTS” in MICRO --text-mid. If picking this ammo would exceed the budget, the chip turns --bad and reads “{cost} PTS · OVER”.
   - The mag's current ammo gets the teal check and the EQUIPPED row style.

## data_bindings
ATTACHMENT LIST
- Rows: attachments.ron entries where cat == the slot and fits contains the current weapon id, in file order.
  - Optional categories (under, side, shield) get a NONE row first.
  - Optic, stock and mag always need a part.
  - Make optional a per-category data flag.
- Header count includes NONE: “{SLOT} · {n} PARTS”.
  - Mako UNDER: NONE, grip_vertical, grip_angled, grip_stub, ugl_launcher, which is 5 and matches the mockup.
  - Warden UNDER: NONE, bipod.
- Name and description come from new name and blurb fields in attachments.ron. Suggested blurbs where the mockup has none:
  - bipod: “Deploy on cover: sway −80 %, recoil −40 %.”
  - laser: “Tighter hip fire. Beam visible within 25 m.”
  - flashlight: “Blinds enemies up close.”
  - shield_front: “250 HP front plate. Blocks bullets only.”
  - optic_reddot: “Fastest sight.”
  - optic_3x: “3× zoom. Glints past 40 m.”
  - optic_thermal: “Bodies glow, the world greys out. No glint.”
  - The UGL's grenade count must come from the UGL table in design/; the data's other field only says “see UGL table”.
- Deltas: computed from ModifierTotals.
  - Non-equipped rows compare the resulting stats with the currently equipped part.
  - The equipped row shows its own effect compared with NONE or the default part. That is what the mockup's equipped row shows.
  - Show the 2 largest changes, by relative size.
  - Formats:
    - Times as signed seconds with 2 decimals: “ADS −0.02 S” = 0.22 × (0.92 − 1).
    - Multipliers as a signed percent: “RECOIL H −6 %”.
    - Capacity as rounds: “+15 RND”.
    - Zoom as “ZOOM 3×”, neutral.
  - Lower is better for ads_time, recoil_v, recoil_h, sway, hip_spread, sprint_to_fire and reload.
  - Higher is better for move, ads_move and capacity.
  - Zoom is neutral.
  - No change at all shows “NO CHANGE” in --text-mid.
  - The mockup's numbers are illustrative. From the data:
    - Angled grip: “ADS −0.02 S / RECOIL H −6 %”.
    - Vertical grip: “RECOIL V −12 % / ADS +0.01 S”.
    - Stub grip: “HIP SPREAD −12 % / SPRINT-FIRE −0.02 S”.
    - UGL: “ADS +0.03 S / SWAY +10 %”.
    - Do NOT use HANDLING; there is no data behind it.
- Hover preview:
  - The ViewportNode model swaps in the hovered part.
  - That slot's hotspot tag shows the hovered part's short name.
  - The stats panel shows hovered-versus-equipped delta segments and inline deltas.

AMMO PICKER
- Rows: ammo.ron types where player_loadout is not false and only (if set) contains the weapon class, with one row per tier. Shrapnel is excluded because it is NPC-only.
  - Mako: STANDARD, AP I-III.
  - SMG: also RIP I-III.
  - Shotgun: SLUG I-II.
- Deltas: from pen_mult, damage_mult, flesh_mult and spill_mult. Spill reads, for example, “SPILL +35 %”.
- Cost: the tier's gear_cost.
- The over-budget check uses the gear-budget sum: halo Σ arc tiers + the per-mag ammo cost, against rules.ron tdm.gear_budget.

## interactions
OPEN
- Attachment list: click a slot card or its hotspot.
- Ammo picker: click a mag card.
- The opened card and its hotspot take the teal SELECTED style.
- Opening another slot swaps the content and moves the selection.

HOVER
- Hovering a row shows the live preview: model, hotspot tag and stat deltas.
- Moving the pointer out of the list restores the equipped preview.

CLICK A ROW
- Equips the part, or sets that mag's ammo.
- Every readout updates: preview, hotspot, slot card, stats, gear budget, and the RESULT figures for the shield.
- Then the popover closes.
- Clicking the equipped row just closes it.

CLOSE WITHOUT CHANGES
- Click the open slot card again, click anywhere outside, right-click, or press Esc.
- Esc closes the popover before it would trigger BACK.

KEYBOARD AND GAMEPAD
- Up and Down move the hover highlight, wrapping around.
- Enter or gamepad A equips.
- Esc or gamepad B closes.
- R resets the slot to its default (default_for, or STANDARD for a mag) and closes.
- The wheel scrolls if the list is clipped.

THE “G” KEYCAP
- The G in the UGL row is only a hint about the in-match binding. It does nothing here.

## adaptations
1. Placement
   - Anchor the popover to the new weapon-column geometry: bottom edge 1px over the row of the card that opened it (y 621 for attachments, y 731 for mags), left 446, width 420.
   - It grows upward with the number of rows.
   - Use compact rows when there are more than 6.

2. Ammo picker
   - The same component, with the ammo-picker content described above.
   - It is how the per-mag ammo type and tier is chosen for the 6-slot ordered strip.
   - The cost chip shows each row's effect on the gear budget.
   - Picking an over-budget ammo is allowed: the player can try it out, and CONFIRM is disabled until they fix it.

3. Data, not hard-coded copy
   - All names, descriptions and deltas come from data: the new name, blurb and optional fields in attachments.ron, plus ammo.ron.
   - Mockup delta values are illustrative; use the computed ones.
   - Never show HANDLING.
   - Drop “SIDE R” and “(R)”: the game has one side rail.

4. Bevy details
   - Top border colour per side, through BorderColor.
   - BoxShadow for the drop shadow.
   - GlobalZIndex above the preview and slots.
   - The panel stays translucent.
   - The check and glyph icons are rasterised PNGs.
   - Uppercase the delta lines in code.
   - Letter-spacing in px: name 1.02, deltas 0.78, header 3.06, micro 1.76.

5. No ammo counters
   - Ammo picker rows show no round counts. Only the type, tier, effect and cost.

## assets
IMAGES
- None.

ICONS (from _src/icons.svg, rasterised to white PNG at 2x and tinted)
- i-under: 28px in the grip rows.
- i-gl: viewBox 48x24, drawn at 34x17 in the UGL row.
- i-check: 14px, tinted --teal, after the equipped row's name.
- i-mag: viewBox 16x28, for ammo picker rows, tinted with the ammo colour.
- The other slots' lists use their category glyph at 28px: i-optic, i-stock, i-magslot, i-side, i-gunshield.

TEXT GLYPHS
- The NONE row's icon is the text glyph “—”.
- The inline keycap is the text “G”.

NEW ASSETS
- The tier-pip parallelogram PNG, shared with the magazine strip.

