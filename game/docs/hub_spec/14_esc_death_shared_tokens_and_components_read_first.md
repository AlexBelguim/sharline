# esc_death: shared tokens and components (read first)

## source_files
[
 "/home/user/sharline/design/ui/mockups/_src/common.css",
 "/home/user/sharline/design/ui/mockups/_src/widgets.js",
 "/home/user/sharline/design/ui/mockups/_src/icons.svg",
 "/home/user/sharline/design/ui/mockups/_src/pages/esc_menu.html",
 "/home/user/sharline/design/ui/mockups/_src/pages/death.html"
]

## purpose
These are the tokens, type styles and small widgets that the ESC menu, Stop-hosting modal, Death recap and Downed screens all use. Each screen spec below refers to them by name. All geometry was measured in headless Chromium on the built pages at 1920x1080 with the real Google fonts loaded, so the numbers are exact. Canvas rule from common.css: 1 CSS px = 1 Val::Px, with UiScale = window_height / 1080.

## layout
Not a screen. Every screen is a full-window root Node (width 100%, height 100%, position Absolute) holding absolutely positioned children. The coordinates in the screen specs are top-left x,y and size w x h on the 1920x1080 canvas. Each one also says which edge it is anchored to, so it can be laid out with left/right/top/bottom insets instead of hard-coded x values.

## elements
COLOUR TOKENS (CSS var = hex):
- --bg0 #07090D.
- --panel-hi rgba(16,21,29,0.82).
- --stroke rgba(255,255,255,0.09), --stroke-mid rgba(255,255,255,0.16), --stroke-hi rgba(255,255,255,0.32).
- --text-hi #F3F0E9, --text #D7D4CD, --text-mid #9CA2AB, --text-low #646B75.
- --ally #52E5A5, --enemy #FF4D5A.
- Halo tiers: --t1 #EDF1F6, --t2 #59B3FF, --t3 #C46CFF, --t4 #FFCE50, --unlit #27272C.
- Health: --hp-ok #E6E2D8, --hp-dmg #FFA23A, --hp-crit #FF3B4E, --hp-dead #15171B.
- Flesh-damage text #FF6170 (not a variable; also the Downed accent).

FONTS: --fd = Barlow Condensed (weights 500/600/700), --fb = Barlow (weights 400/700). Ship the OFL TTFs in game/assets/fonts/.
- CSS weight 400 on a .num span renders as Barlow Condensed 500, the nearest loaded weight. Use BC 500 wherever this spec says 'num'.
- Letter-spacing is given in em; use Bevy's LetterSpacing::Rem(em). The px value is in brackets.
- 'uppercase' means the copy is already written in capitals; type it that way.
- Barlow has no arrow glyphs (U+2191/2193). The arrow keycap needs a tiny arrow PNG or a fallback font that has them.

TYPE STYLES:
- .lbl: BC 600 13px, .14em (1.82px), uppercase, --text-mid.
- .micro: BC 600 11px, .16em (1.76px), uppercase, --text-low.
- .hint: BC 600 14px, .14em (1.96px), --text-mid, gap 7px after its keycap.

PANEL (.panel.hi): background --panel-hi, 1px border --stroke, border_radius 2px.

KEYCAP (.key):
- Shape: height 22, min-width 22, padding 0 6px, radius 2, content centred.
- Text: BC 700 13px, .04em (0.52px).
- Solid: background --text-hi, text --bg0.
- Ghost (.key.ghost): transparent background, 1px border --stroke-hi, text --text-hi.
- Some keycaps are 20 tall (said where they are).
- Widths at 13px: 'L' 22, 'F' 22, 'Z' 22, 'TAB' 31.3, 'ESC' 33.1, 'WASD' 41.9, 'ENTER' 46.9, arrow keycap 28.

BUTTON (.btn):
- Shape: height 44, padding 0 22px, gap 10px between keycap and label, align centre.
- Text: BC 700 18px, .12em (2.16px), --text-hi.
- Normal: background rgba(255,255,255,0.06), 1px border --stroke-mid.
- Hover: background rgba(255,255,255,0.12), border --stroke-hi.
- Disabled: opacity 0.35, no interaction.
- Danger-solid variant: background and border --enemy #FF4D5A, text #1B0507. Hover is not in the mockup; use #FF6170.

PROGRESS RING (replaces the SVG circles):
- A circular Node: border_radius 50%, border width = stroke.
- BorderGradient Conic: start 0 (12 o'clock), clockwise.
- Stops: [fill colour 0 .. f*TAU, track colour f*TAU .. TAU], as hard stops.
- The number Text sits centred inside it.

BACKDROP:
- In-game backdrops are the LIVE 3D view. The mockup's hud_street.jpg is only a stand-in.
- Gradients use Bevy BackgroundGradient (LinearGradient / RadialGradient).

DO NOT BUILD the bottom-right 'MOCKUP 09/10 ...' label (mockup-only).

## data_bindings
Shared formatting rules for all four screens:
- Damage and HP numbers are integers (round), with a true minus sign U+2212.
- An empty damage value is an em dash U+2014.
- Separators are ' · ' (U+00B7 with a space on each side).
- The multiply sign is U+00D7.
- Team colours are always relative: your team = --ally, the other team = --enemy.
- Exact ammo counts never appear anywhere (hard rule). Magazines can be named by slot and ammo type/tier, but never by rounds.

## interactions
Shared input rules:
- Mouse: Button + Interaction. Hover selects; Pressed activates.
- Keyboard: arrows move the selection, Enter activates, Esc goes back or cancels.
- While any of these screens is open, gameplay input is already zeroed by LocalControl.paused (ESC menu). For the death and downed screens, only the keys listed on them are read.
- The cursor is visible and unlocked while the ESC menu or the death recap is open, and locked again on Resume or respawn.

## adaptations
Bevy 0.19 has what we need, checked in bevy_ui/bevy_text 0.19.1:
- LetterSpacing (Px/Rem) and LineHeight components.
- BackgroundGradient and BorderGradient with Linear, Radial and Conic gradients.
- TextShadow, Outline, BoxShadow.

No SVG support:
- The halo widget, body silhouette and i-heal icon must be rasterised to white PNG masks and tinted with ImageNode.color, or drawn with a UiMaterial.
- The progress rings use the conic BorderGradient trick above, so they need no assets.

## assets
Fonts: Barlow Condensed 500/600/700 and Barlow 400/700 (Google Fonts, OFL), to be added under game/assets/fonts/.

Icons (icons.svg): i-heal, used only by Downed. The ESC menu and Death recap use no icons.svg symbols.

Generated widgets (from widgets.js, rasterise): haloSVG (Death recap killer panel), bodySVG (Death recap YOU panel).

Image: /home/user/sharline/design/ui/mockups/img/hud_street.jpg is a placeholder backdrop only. Do not ship it; the live scene replaces it.

