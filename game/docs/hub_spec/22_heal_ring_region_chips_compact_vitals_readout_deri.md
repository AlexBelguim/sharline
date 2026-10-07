# Heal ring region chips + compact vitals readout (derived from the health panel; not in any mockup)

## source_files
[
 "/home/user/sharline/design/ui/mockups/_src/pages/health_panel.html",
 "/home/user/sharline/design/ui/mockups/_src/widgets.js",
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/png/03_health_panel.png"
]

## purpose
How to carry the health panel's visual language into (a) the per-region heal radial and (b) a compact, stylised readout of the same information during play. The user rejected the HUD mockup, so this uses only the health panel's widgets, tokens and type. Treat it as a proposal, aligned to the panel.

## layout
(a) HEAL RING (radial.rs; geometry unchanged)
- Ring: centre (960,540), radius 120, chips 104x58.
- Region ring: radius 92, chips 88x46, centred on the chosen item chip.
- The health panel shows docked on the left at the same time (see the first entry).

(b) COMPACT VITALS (proposal), anchored bottom-left: left 32, bottom 32, width 236, height 132 (+22 when the status-chip row shows). Inside, with 12px padding:
- body widget w=52 (52x104) at (12,14);
- halo widget 96 at x 72, vertically centred;
- right column x 180-224: label 'HP' over the total;
- chip row along the bottom, full width.

## elements
(a) RING CHIPS, restyled to the panel's tokens. Today they are CHIP_BG with teal selection.
- Chip: background rgba(16,21,29,.86). 1px border rgba(255,255,255,.09), and rgba(255,255,255,.32) when current or focused. Radius 2 (was 6).
- Selected chip: background rgba(255,255,255,.12) with a 2px top bar in #F3F0E9, the panel's accent-top idiom, in place of the teal fill.
- Item chip: key = item label in FD 700 15px .1em #F3F0E9; label = '×{n} · ALL' or '×{n} · REGION' in FD 600 11px .14em #9CA2AB.
- Region chip:
  - key = a 14px zone icon + zone name in FD 700 16px .16em #F3F0E9;
  - label = '{hp}/{max}' in FD 600 12px, coloured by zone state (ok #E6E2D8, damaged #FFA23A, critical #FF6170, destroyed #8A8F98);
  - a 3px bar inside the chip's bottom edge: state colour, width hp/max;
  - when bleeding, an i-bleed icon 12px #E0162E at the top-right;
  - for shield items, the label is 'ARC {s}/{cap}' in the arc's tier colour, or 'NO ARC' in #646B75.
- Disabled chip (would_help false, or count 0): all alphas × .35.
- Ring title ('HEAL'): FD 600 13px .14em #9CA2AB.
- Pointer dot: 10px circle in #F3F0E9 (was teal).

(b) COMPACT VITALS
- Panel: rgba(9,12,17,.70), 1px rgba(255,255,255,.09) border, radius 2, plus a 2px #F3F0E9 accent bar on top.
- Body widget at w=52: same layers; coverage line at least 1.5px and glow at least 3px.
- Halo widget at 96 in value mode (total shield, 'T2 MENDER').
- 'HP' label: FD 600 11px .16em #646B75.
- HP total: FD 700 22px #F3F0E9, tabular, ceil. #FF6170 when head or torso is critical.
- Status chips: height 18, padding 0 6, gap 6, FD 700 11px .14em, background rgba(255,255,255,.06), 1px border rgba(255,255,255,.09).
  - BLEED: i-bleed 12px #E0162E + zone letters (H T A L) in #FF6170.
  - BROKEN: zone names in #8A8F98.
  - TREATING: text in #9CF7C8, with a 2px progress underline in #9CF7C8.
  - REGEN IN n S: text in #9CA2AB.
  - SPAWN PROTECTED: text in #F3F0E9.
- No exact ammo anywhere, as always.

## data_bindings
Same sources as the health panel: Vitals, PlayerLoadout (halo, kit), PlayerItems (counts, using), MatchState.rules, items.ron.
The ring options are built in radial.rs fill_rings:
- RingOption.key and label stay.
- Add the zone, the state colour, the frac and the bleeding flag to RingOption so the chip can draw its bar and icon.
- Chips appear only when rules allow: BLEED needs rules.bleeding, BROKEN needs rules.injuries.
- With no halo: the halo widget is unlit and the value is '0'.
- With no kit: H does nothing (the current behaviour), so the panel never opens.

## interactions
Heal ring (unchanged mechanics):
- H toggles the ring.
- The mouse steers the pointer.
- LMB picks: a Body item is used at once; a Region item opens the region ring.
- RMB steps back, then closes.
- Esc or H closes.
Recommended additions:
- Digits 1-8 pick an item slot, like the magazine radial.
- Hovering a region previews it on the health panel's body (static mint dashed outline).
Compact readout: display-only; it updates every frame from Vitals.

## adaptations
- Built only from the health panel: tokens, Barlow type, the accent-top bar, the body widget and the halo widget.
- Replace the current ad-hoc colours: the HUD and ring use TEAL, CORAL, INK and MUTED constants; switch to the common.css tokens listed in the first entry.
- TDM (no bleeding or injuries) shows only the HP, shield and treating/regen chips.
- The gun range shows everything.

## assets
Icons: i-head, i-torso, i-arms, i-legs, i-bleed, i-heal, i-bandage, i-medkit, rasterised white and tinted. No images from /home/user/sharline/design/ui/mockups/img are used.

