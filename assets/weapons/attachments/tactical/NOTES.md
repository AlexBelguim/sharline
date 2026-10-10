# ATT tactical / underbarrel / shield set

Shared attachments for the Mako (AR-7) and Warden (VK-50). Prefix `ATT`. Everything here is rebuilt from
scratch by one script:

```
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P build_tactical.py
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P render_tactical.py -- --sets alone,detail,fit,open,loadout,sight,closeup
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P render_railfit.py
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P check_fit.py
python make_sheets.py all
```

The build takes about 10 s. It writes `tactical.blend` (one collection per part, plus the Mako and Warden
proxies and a `TestFit` scene), `ATT_<part>.glb` and `.fbx` for each part, `catalog.json` and `textures/` (the baked
detail textures, which are also embedded in every .glb). If any mesh check or triangle budget fails, the build stops
before exporting, so the previous deliverables stay untouched. Helpers live in `att_lib.py` (mirror-aware
primitives, glTF-safe materials, convex-only bevels, explicit triangulation, mesh checks, socket reading from the gun
.glb files). `render_railfit.py` renders true cross-sections of every clamp on the real gun rails
(`renders/railfit/`), and `check_fit.py` puts every part on every real gun it fits (socket nodes from the gun .glb) and
measures penetration both ways (gun vertices inside the part and part vertices inside the gun). `_work/` holds scratch
scripts and iteration renders; `_work/rev3/` has the first review-pass-2 checks (`overlap_scan.py`, `checks_rev3.py`),
`_work/rev4/` the round-2 checks (`checks_rev4.json` on the re-exported Mako, `fit_check.json`) and the pre-round-2
exports and renders in `before/`.

## Conventions (art/WEAPON_MODULAR_SPEC.md)
- Metres, Z up, muzzle toward −Y. **Shooter's right is −X.**
- Every part is modelled in **mount space**. Its origin is the centre of the clamp's contact with the rail:
  - under-mounted (grips, UGL, bipod): the rail's BOTTOM surface, and the part hangs toward −Z;
  - top-mounted (shield): the rail's TOP surface;
  - side-mounted (laser, flashlight): the rail's OUTER face. `_R` sticks out toward −X. `_L` is an exact
    X-mirror: it is built natively with `att_lib.MIRROR = True`, so booleans, bevels and hardened normals are computed
    on the mirrored geometry. Its normals are correct (checked) and its sockets are mirrored too.
- Rail standard: top width 0.021, height 0.0095, slot pitch 0.010. Every clamp uses the same U-channel section
  (`att_lib.clamp_profile`) with 0.3 mm clearance and hooks under the dovetail. The channel has **square corners at
  the contact face**, because the real rails are the full 0.021 wide at their top face (Mako: 0.6 mm corner chamfer,
  Warden: square corners). Clamps get **convex-only** bevels, so no fillet grows into the rail they hug.
  `check_fit.py` on the real Mako and Warden exports: 0.00 mm penetration in both directions for every part on every
  rail it fits; the clamp contact face sits flush on the rail face (`renders/railfit/`).
- Snapping: put the part's root on the gun socket (`<GUN>_SOCKET_Under` / `_Side_R` / `_Side_L` / `_Shield`)
  with zero rotation.
- Moving parts are child objects with their origin on the hinge or pivot. Their custom properties are exported as
  glTF `extras`, including ready-made glTF quaternions for each pose (`pose_*_quat_gltf_xyzw`).
- Compatibility (`compatible_weapon_ids` in `catalog.json`) follows the `fits` lists in
  `game/assets/data/attachments.ron`: grips, UGL and shield fit `ar7_mako`; the bipod fits `vk50_warden`; laser and
  flashlight fit `ar7_mako`, `vk50_warden` and `sk9_skink`.

## Parts

| Part | Tris | Size (x × y × z, m) | Sockets / moving parts |
|---|---|---|---|
| `ATT_grip_vertical` | 1226 | 0.035 × 0.074 × 0.116 | `_SOCKET_LeftHand` |
| `ATT_grip_angled` | 1236 | 0.035 × 0.105 × 0.070 | `_SOCKET_LeftHand` |
| `ATT_grip_stub` | 784 | 0.035 × 0.050 × 0.045 | `_SOCKET_LeftHand` (on the handguard, behind the stop) |
| `ATT_ugl_launcher` | 5822 | 0.077 × 0.286 × 0.177 | `_SOCKET_LeftHand`, `_Breech` (+ child `_SOCKET_Muzzle`), `_Trigger` |
| `ATT_bipod` | 3792 | 0.198 × 0.207 × 0.224 deployed; 0.107 × 0.289 × 0.061 folded | `_Leg_L/_R` → `_LegSplay_L/_R` → `_LegLower_L/_R` → `_Foot_L/_R` |
| `ATT_laser_R` / `_L` | 1024 | 0.045 × 0.065 × 0.036 | `_Emitter` (red dot), `_SOCKET_Beam` |
| `ATT_flashlight_R` / `_L` | 1432 | 0.053 × 0.122 × 0.037 | `_Lens`, `_SOCKET_Beam` |
| `ATT_shield_front` | 2720 | 0.314 × 0.080 × 0.260 | `_Glass` (alpha 0.38, dark blue tint) |

All parts are within the budgets (grips 0.5k–1.5k, UGL 3k–6k, bipod 1.5k–4k, shield 1.5k–4k, laser and light ≤ 1.5k).

### Foregrips (concept `concepts/grips_v01.png`)
Bone polymer skeleton bodies under a graphite clamp. The clamp jaws carry diagonal lightening slots and a cross bolt.
- **grip_vertical**: a front column with a slight forward rake, a rear brace with three palm grooves, a triangular
  through-window, and a graphite foot cap. The hand-contact faces (column front, brace back) use the stipple material.
- **grip_angled**: a wedge with its deepest point at the front, the palm ramp underneath with three grooves, a
  triangular window, and a graphite tip pad.
- **grip_stub**: a hand stop with a tall front face and a rear ramp, plus triangular stipple recesses on the sides.
  `_SOCKET_LeftHand` sits 45 mm behind it at handguard height.

### UGL (`ATT_ugl_launcher`, concept `concepts/ugl_side_v01.png`)
A 40 mm-class single shot, **0.286 m long** (clamp tail at y +0.111 to the muzzle at y −0.150). A graphite top
housing with a slanted nose, raised front and rear ears on the top line and long chamfered facet slabs on both flanks.
Under it hangs a 45 mm bore gunmetal tube (outer r 0.029, bore r 0.0225, axis z −0.0615): four ribs on the mid tube, a
hinge band, and a plain stepped muzzle collar (r 0.0316). The rear tube is a 24-step lathe and the muzzle collar and
mouth are a 32-step lathe, so the part the camera sees up close stays round. The receiver carries the breech face
(y 0) and firing pin. A crisp panel split line runs the full height of the receiver flank, 30 mm behind the breech
face. The receiver tail slopes down into a bone pistol grip with a **20° rake** (finger hook, palm swell, stipple panel,
triangle inset, graphite base pad) behind a hexagonal trigger-guard window. The barrel release latch is on the
shooter's left (+X). A QD lever sits on the clamp.
- `ATT_ugl_launcher_Breech`: the whole tube swings sideways like an M320. The hinge is a vertical pin at the shooter's
  right front (origin x −0.0365, y −0.074, z −0.0615). Rotate about local Z by `open_angle_deg` = −40 and the
  breech end swings out to the shooter's LEFT. With the pivot opposite the swing side, every point of the tube moves
  forward, so it never cuts into the breech face (`renders/ugl_launcher/ugl_launcher_open_*`).
- `ATT_ugl_launcher_Trigger`: pivots about local X, `pull_angle_deg` 12.
- `ATT_ugl_launcher_SOCKET_Muzzle` is a child of `_Breech`, so it follows the tube when it opens.
- Fit on the re-exported `mako_default.glb` (14:02; its Under socket node is now z 0.0075, 8 mm lower, matching
  `sockets.json`; `_work/rev4/checks_rev4.json`): 23.7 mm from the launcher to `mag_30` (26.0 mm to `mag_45`, 37.3 mm to
  `drum60`), 1.2 mm between the housing top and the handguard, 19.7 mm to the front shield, muzzle 17.5 mm behind the
  shield's back face, nothing hit by the 0 → −40° breech swing, 0.00 mm rail penetration, and the bore line and a
  grenade fired at 0–25° elevation clear the shield port.

### Bipod (`ATT_bipod`, concept `concepts/bipod_v01.png`, Warden)
A rail clamp with a QD lever, a bone hinge head (graphite pocket inserts, a graphite belt, a hex cant knob at the back),
a gunmetal cross pin and slotted graphite pivot knobs. Two chunky angular legs: a graphite upper beam with a
lightening slot, a collar and a lock button, then a gunmetal octagonal lower tube with height notches, a graphite boot,
an ankle pin and an angular rubber foot with sole grooves.

Each leg is built **straight**, and every motion is its own node, so both poses are plain local rotations:

| Node (per side) | Motion | Deployed (as exported) | Folded |
|---|---|---|---|
| `ATT_bipod_Leg_<s>` | hinge, local X | euler X −40° (leg 50° below the rail, forward) | −95° (`hinge_euler_x_folded_deg`) |
| `ATT_bipod_LegSplay_<s>` | splay, local Y (glTF −Z) | 12° outward (`splay_euler_y_deployed_deg` −12 L / +12 R) | 0 (`splay_folded_deg`) |
| `ATT_bipod_LegLower_<s>` | telescope, local −Z | 0 (`telescope_max_m` 0.05) | 0 |
| `ATT_bipod_Foot_<s>` | ankle swivel, local X | 0 (soles level) | 54.4° (`swivel_folded_deg`, soles flat) |

- Deployed: both soles sit level at mount-space z −0.2155. On the current Warden (bore z 0.075, Under socket
  z 0.0275) that puts the **bore 0.263 m above the ground**. The older socket at z 0.0205 gave 0.270 m.
- Folded: the legs lie parallel under the handguard, pointing forward and 5° up. The bipod spans x ±0.053 (the
  40 mm feet overhang the Warden handguard by 15 mm a side; it was ±0.099 with the old baked-in splay) and hangs at most
  52 mm below the socket. No leg triangle touches the Warden export (`_work/rev4/checks_rev4.json`).

### Laser (`ATT_laser_R/_L`, concept `concepts/laser_light_v01.png`)
A chamfered graphite box beside the side rail. The front has a hexagonal IR window of near-neutral dark glass (clear
coat) above a gunmetal emitter bezel. The child `_Emitter` carries the red emissive dot (strength 1.2), the part's only
accent. There is a rubber activation pad on top and a rubber rear switch, three screws, a lengthwise groove on the
outer face and a crosswise seam on top that runs out on both top chamfers. `_SOCKET_Beam` sits on the emitter, so the
beam points −Y.

### Flashlight (`ATT_flashlight_R/_L`)
A graphite lathe body with a tail-cap groove, a rubber tail switch and a flared head. It has a crenellated gunmetal
knurl band and a scalloped strike bezel. The child `_Lens` is a dark glass lens (emission 0.2) with a reflector ring and
a warm LED dome (emission 1.5). Its axis is 26.5 mm out from the rail face, and `_SOCKET_Beam` is in front of the lens.

### Front shield (`ATT_shield_front`, concept `concepts/shield_v03.png`, Mako only)
An angular graphite plate, 0.32 × 0.26 (0.314 wide after the wrap). The outline is an octagon with large corner chamfers
and a heavy 45° rim chamfer. It is 14 mm thick, perpendicular to the bore, and its wings fold back 20° beyond
|x| 0.100 (the slight wrap). Chunky raised frames surround the windows. Six hex bolts sit on the front. The back has
stiffener ribs and a boss, joined by an arm to a top-rail clamp with a QD lever (origin = clamp contact on the TOP rail,
Mako `_SOCKET_Shield`).
- `ATT_shield_front_Glass`: ballistic glass with a **dark** blue tint, base (0.020, 0.045, 0.080), alpha 0.38,
  roughness 0.08 (`alphaMode BLEND`). It spans **z +0.030 … +0.100** above the origin and x ±0.095, centred on X.
  The optic sight band (rail top +0.040 … +0.075) is fully inside it.
- Sight checks in a sunlit range (sun + sky, a 2 % / 80 % checker board and an orange post 6 m out), eye at rail top
  +0.040 / +0.0575 / +0.075 and through the real holo optic: `renders/shield_front/shield_front_sight_*.png` and
  `shield_front_sight_daylight.json`. Through the glass the checker keeps a 4.77 : 1 contrast (8.37 : 1 with no glass)
  and the post stays orange.
- Port (x ±0.080, z −0.066 … −0.008): the Mako barrel and flash hider (bore 34 mm below the rail top, r 12.6 mm)
  pass through it, as do the side lights' heads and beams. The plate's back face sits 7.5 mm in front of the
  handguard end. Clearances checked against the real Mako export with the lights mounted together: laser 13.9 mm,
  flashlight head 2.4 mm from the port edge, no contact with the barrel or hider.

## Materials (glTF-safe)
`baseColorFactor` = palette colour × a baked grey detail texture (Mix MULTIPLY at factor 1, exported as factor ×
texture; tiling is baked into world-scale box UVs, so no texture transform is needed). Every closed mesh is single-sided
(backface culling). There is one material per surface.

| Material | Colour / notes |
|---|---|
| `M_ATT_Graphite` | graphite (0.030, 0.033, 0.040), rough 0.52, metal 0.2, worn paint 0.5 |
| `M_ATT_Gunmetal` | gunmetal (0.11, 0.115, 0.12), rough 0.35, metal 0.85, brushed 0.3 |
| `M_ATT_Bone` | bone (0.55, 0.52, 0.46), rough 0.6, worn paint 0.3 |
| `M_ATT_BoneStipple` | bone hue (0.47, 0.45, 0.40), rough 0.78, polymer stipple 0.6 (grip contact surfaces) |
| `M_ATT_Rubber` | near-black, rough 0.88 (feet, pads, switches) |
| `M_ATT_Bore` | UGL bore interior |
| `M_ATT_ShieldGlass` | dark blue tint (0.020, 0.045, 0.080), alpha 0.38, rough 0.08, BLEND |
| `M_ATT_LaserEmitter` | red emissive dot (strength 1.2) |
| `M_ATT_IRWindow` | near-neutral dark glass (0.015, 0.017, 0.022), clear coat 1 |
| `M_ATT_LightLens`, `M_ATT_LightLED` | lens slightly emissive (0.2), LED dome 1.5 |

There are no ammo counters and no emissive on any gun part. The only glows are the laser dot and the flashlight lens.

## Mesh validation
- `att_lib.tri_clean` triangulates every mesh explicitly (BEAUTY for quads and n-gons, which is what the exporters
  write), removes degenerate slivers, and restores the hardened corner normals afterwards.
- Thin panel lines and seams are cut **after** the bevel (`att_lib.cut_crisp`). Cut before it, a groove ending near
  an edge made the clamped bevel collapse into self-overlapping n-gons (the black wedges of review pass 2).
- `att_lib.check_mesh` fails the build on exploded vertices, missing materials, degenerate polygons, zero-area
  triangles, triangles whose winding disagrees with their corner normals by more than 120°, and triangles wound
  against their own polygon.
- An independent scan of the exported .glb files (`_work/rev4/overlap_scan.py`) finds 0 flipped and 0 zero-area
  triangles in every part and no coplanar overlaps on any visible surface. The coplanar pairs it lists are all internal
  contact faces between touching joined pieces, back to back and enclosed: the UGL housing/receiver at the breech
  face, the two tube lathes at the collar seam, the pin/knob ends of the bipod, the QD lever bosses buried in the clamp
  jaws, and the shield arm/clamp. They are never visible.

## Renders
`renders/<part>/`: right, left, three_quarter, front, back and top, three close-ups (`_detail_*`), review close-ups
(`_close_*`: UGL muzzle collar and latch flank, UGL on the Mako in first person, laser top and front, grip ramps), and
the fit on the real `mako_default.glb` / `warden_default.glb`, placed on the socket nodes read from those .glb files
(`_fit_*`, `_fit_wide_*`). There are also the UGL breech open, the bipod folded alone and on the Warden, and the shield
sight checks. `renders/railfit/` holds true cross-sections of every clamp on every real rail it fits
(`render_railfit.py`; orange = rail, blue = part, dark = clearance). Sheets: `renders/sheet_<part>.png`,
`sheet_<part>_fit.png`, `sheet_overview.png`, `sheet_loadouts.png`, `sheet_compare.png` (render vs concept,
`compare_*.png`), `sheet_review_fixes.png` (before / after for the first fix pass on review pass 2) and
`sheet_review_fixes_r2.png` (before / after for round 2).

## Review fixes (round 2)
Round 2 applies `review/critique_latest.json` (review pass 2 on the 09:44 exports; the same nine issues as
`review/review.json`) plus the Warden review's note that the `ATT_bipod` clamp overlaps the Warden's bottom rail by
0.85 mm. A first fix pass (13:xx) handled items 1–9. Round 2 re-checked every one of them on a fresh from-scratch build
(`build_tactical.py`, about 10 s), fixed the clamp/rail overlap on the attachment side (item 10), and re-rendered every
deliverable on the re-exported Mako (item 11). "Verified by" names the renders that were looked at for each fix. Every
render and sheet in `renders/` comes from this round.

| # | Severity | Issue | Fix | Verified by |
|---|---|---|---|---|
| 1 | major | Shield glass was a bright veil: light base (0.24, 0.50, 0.85) at alpha 0.4 crushed contrast and colour in daylight | Dark tint (0.020, 0.045, 0.080), alpha 0.38, roughness 0.08 (`GLASS_*` in `build_tactical.py`). The sight renders run in a sunlit range scene and sample the board | `shield_front_sight_eye_575.png` vs `_oldglass.png`: checker contrast 4.77 : 1 through the glass (8.37 : 1 with no glass, old glass 1.46 : 1); orange post through the glass (166, 121, 97) vs (176, 179, 193) with the old glass |
| 2 | major | UGL renders, sheets and NOTES were stale | Everything re-rendered from this build (`render_tactical.py`, all sets) and re-sheeted (`make_sheets.py all`). `sheet_loadouts.png` cells follow the 1400 × 900 aspect with labels under their images. The end-on loadout views (`mako_loadout_A_front`, `warden_bipod_front`) are now framed on the gun's cross-section instead of its 0.8–1.4 m bounding sphere, where they were tiny. The parts table and UGL section above match `catalog.json` | `renders/ugl_launcher/*`, `compare_ugl_launcher.png`, `sheet_loadouts.png`, `sheet_review_fixes_r2.png` row 3 |
| 3 | major | Fold-over triangles on the laser top (both sides) and the UGL +X flank; zero-area triangles in the UGL, grips and lower legs | Seams cut after the bevel (`att_lib.cut_crisp`) and run out over the chamfers; `tri_clean` (BEAUTY) on every mesh; `check_mesh` fails the build on flipped, folded or zero-area triangles | `laser_R_top.png`, `laser_R_close_top*.png`, `ugl_launcher_close_latch_*`; `_work/rev4/overlap_scan.json`: 0 flipped and 0 zero-area triangles in every exported part |
| 4 | major | Folded bipod unusable: the 12° splay was baked into the leg, so the folded feet stuck out 61 mm a side | Straight legs; the splay is the `LegSplay` node (12° deployed, 0 folded); fold −95°; the feet swivel flat on the ankle pin (all values exported as extras) | `bipod_folded_fit_front.png`, `bipod_folded_fit_right.png`, `loadouts/warden_bipod_folded_*.png`; folded span ±0.053 m, 0 leg triangles touching the Warden (`_work/rev4/checks_rev4.json`) |
| 5 | minor | The sight line sits low in the glass (≈2.2° clear below the aim point, 7.7° above) | **Not changed; this needs the user's decision.** The brief fixes the glass at z 0.030–0.100. The option is to centre the window on the sight band, e.g. z 0.015–0.095 (there is 38 mm of plate between the glass and the port) | `shield_front_sight_ads_holo.png` |
| 6 | minor | Test fits used `sockets.json` while the Mako glb's socket nodes differed by 8 mm | Test fits read the socket nodes from the gun .glb (engine truth) and fall back to `sockets.json`. The Mako has since been re-exported (14:02): its glb nodes and `sockets.json` now agree (Under / LeftHand z 0.0075), `catalog.json` `test_socket_json_vs_glb_mismatch` is empty for both guns, and every fit was re-checked and re-rendered | `ugl_launcher_fit_*.png`, `loadouts/mako_*`; `checks_rev4.json`: UGL 23.7 mm from `mag_30`, 19.7 mm from the shield, breech swing clear |
| 7 | minor | Off-palette hues: plum IR window, brown-taupe stipple | IR window (0.015, 0.017, 0.022) + clear coat; stipple pulled to the bone hue (0.47, 0.45, 0.40) | `laser_R_close_front.png`, `grip_*_close_under_back.png` |
| 8 | minor | The 20-step UGL tube looked faceted in first person | Rear tube, ribs and hinge band 24 steps; muzzle collar and mouth 32 steps; paid for by rim-only bevels on screws and pins (UGL 5822 / 6000 tris) | `ugl_launcher_close_muzzle_*`, `ugl_launcher_close_onmako_*` |
| 9 | minor | `catalog.json` compatibility disagreed with `attachments.ron` | `compatible_weapon_ids` copy the `fits` lists (grips, UGL, shield: `ar7_mako`; bipod: `vk50_warden`; laser and light: all three guns) | `catalog.json` |
| 10 | major (Warden review) | The bipod clamp overlapped the Warden's bottom rail by 0.85 mm (76 face pairs). Root cause: `att_lib.clamp_profile` gave the channel a 1.5 mm chamfer at the contact face, sized for a chamfered rail top, but the real rails are the full 0.021 wide at the top face (Warden: square corners; Mako: 0.6 mm chamfer). So **every** clamp bit into **every** real rail: 0.85 mm on all Warden rails, 0.42 mm on all Mako rails | Fixed on the attachment side, in the shared profile: the channel now has square corners at the contact face (0.3 mm clearance to a 0.021 rail all the way down to the dovetail), so all seven clamps fit both guns. `att_lib.rail_profile` (proxy rails) now matches the real section. Each clamp has 16 fewer triangles | `renders/railfit/*.png` and `sheet_review_fixes_r2.png` rows 1–2 (rail corners before / after); `check_fit.py` → `_work/rev4/fit_check.json`: max penetration 0.00 mm (was 0.85 / 0.42) in all 14 part-on-gun fits, with the clamp face flush on the rail face |
| 11 | — | The Mako was re-exported after the first fix pass (14:02: Under socket node and bottom rail 8 mm lower) | Rebuilt, re-checked and re-rendered on the new export. Loadout clearances (`check_fit.py`): shield to flashlight head 2.4 mm, shield to laser 12.1–14.0 mm, UGL to shield 19.7 mm, every part to the gun body 1.2 mm (clamp jaw tips above the handguard) | `sheet_review_fixes_r2.png` row 3, `sheet_loadouts.png` |

## Known limitations
- The Mako proxy in `tactical.blend` (`_Proxy_Mako`) is a simplified stand-in built from `build_mako.py`'s numbers.
  The renders and checks use the real exports when they exist. After the next Mako or Warden export, re-run the build,
  `render_tactical.py`, `render_railfit.py`, `check_fit.py` and `make_sheets.py all`.
- The shield's sight line sits low in the glass (review item 5). Changing the window height needs the user's go-ahead.
- The flashlight head passes through the shield port with only 2.4 mm to the port edge. That is fine for a static
  mount, but a bigger future light would need a bigger port.
- The UGL bore is open. When the breech swings open, the gunmetal firing-pin disc on the breech face is visible, but
  there is no grenade mesh (that belongs to VFX or ammo).
- The folded bipod feet overhang the Warden handguard by about 15 mm a side (the 40 mm pads are wider than the legs).
- The laser's IR window is cosmetic (no separate IR beam socket); `_SOCKET_Beam` is the visible red laser.
- The shared `assets/weapons/attachments.json` catalog is not written here, because it is outside this folder. Merge
  `catalog.json` into it.
