# VK-50 "WARDEN": build notes

A heavy-calibre (12.7 mm class) bolt-action anti-materiel sniper, built as a **modular base gun plus swappable
stocks and magazines**. The scope (`optic_sniper` / `optic_thermal`) and the `bipod` are shared attachments that
other agents build in `assets/weapons/attachments/`. They are not part of this asset (DIRECTION_LOG items 1 and 8).

Sources, in order of authority: `art/DIRECTION_LOG.md` > `art/STYLE_GUIDE.md` > `art/WEAPON_MODULAR_SPEC.md` >
`art/concepts/warden/BRIEF.md` > the concept paintings.

## Rebuild

```
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P build_warden.py -- --render full
python compare.py        # concept comparison, 64 px silhouettes, labelled contact sheets (system python + PIL)
```

- `--render none|quick|full|fitcheck`, `--samples N` (default 48) and `--no-export` are the options.
- The script builds everything from scratch in about 6 s. A full render pass takes 3 to 7 minutes on a shared GPU,
  and falls back to CPU Cycles by itself.
- It also rebuilds the derived textures in `textures/`, so nothing stale is left behind.
- For renders only, the env vars `WARDEN_EXPOSURE` (default -0.2) and `WARDEN_LOOK` (default "AgX - Punchy")
  change the presentation look.

## Files

| File | Content |
|---|---|
| `warden_base.glb/.fbx` | `WARDEN_Root` with all base meshes and the 8 socket empties |
| `WARDEN_stock_standard.glb/.fbx` | default stock; origin = stock mount point (`_SOCKET_Stock`) |
| `WARDEN_stock_folding.glb/.fbx` | folding skeleton stock; origin = stock mount point |
| `WARDEN_mag_5.glb/.fbx`, `WARDEN_mag_8.glb/.fbx` | magazines with child cartridges and follower; origin = `_SOCKET_Mag` |
| `warden_default.glb` | base + stock_standard + mag_5, each parented to its socket empty (`Root > SOCKET_Stock > WARDEN_StockStandard`, ...) |
| `warden_anim.json` | every moving part's pivot, axis, angle and travel, in Blender **and** glTF/Bevy axes (same data as the node extras) |
| `warden.blend` | collections `WARDEN_Base`, `WARDEN_Stock_Standard`, `WARDEN_Stock_Folding`, `WARDEN_Mag_5`, `WARDEN_Mag_8`. The default is assembled; the variant collections are excluded from the view layer. Textures are packed. |
| `sockets.json` | `{socket: {location, rotation_deg}}`, in metres and Blender axes, all rotations zero |
| `textures/` | 512 px derived detail textures (see Materials), embedded in every glb |
| `compare.py` | comparison, silhouette and contact-sheet generator |
| `renders/` | see the end of this file |
| `_wip/` | scratch and checks: `tris.json` (written by every build), `roundtrip.py`, `clearance.py` (bolt-cycle sweep on the built scene), `look.py` (quick iteration renders), `verify_check.py` / `verify_bolt_fold.py` / `verify_topology.py` / `verify_render.py` (the reviewer's checks pointed at the new file names; reports and renders land in `_wip/`) |
| `review/` | the independent review (scripts, reports, renders) that the "Review fixes" section answers; left untouched |

## Axes, origin, handedness

- Metres, Blender Z-up, **muzzle toward -Y**, bore axis at x = 0, z = 0.075.
- Origin (0,0,0) is the top centre of the pistol grip. glTF export is Y-up: Blender (x, y, z) becomes glTF
  (x, z, -y), so the muzzle points to glTF +Z.
- **Shooter's RIGHT = -X:** ejection port, bolt handle and oversized knob, and `_SOCKET_Side_R`.
  **LEFT = +X:** bolt-release button, rotary safety lever, and `_SOCKET_Side_L`.
  This follows WEAPON_MODULAR_SPEC. The BRIEF's older note that put Side_R at +X is superseded.
- Overall default length: y -1.100 (brake face) to +0.320 (recoil pad), so 1.42 m.

## Sockets (children of `WARDEN_Root`, zero rotation)

| Socket | Location (x, y, z) | Notes |
|---|---|---|
| `WARDEN_SOCKET_Optic` | (0, -0.080, 0.1375) | on the top-rail top surface over the receiver |
| `WARDEN_SOCKET_Stock` | (0, +0.080, 0.075) | receiver rear on the bore axis; every stock's hinge block clamps over the chassis lug here |
| `WARDEN_SOCKET_Mag` | (0, -0.270, 0.000) | top-front of the magwell opening |
| `WARDEN_SOCKET_Under` | (0, -0.600, 0.0205) | bottom-rail bottom surface (bipod) |
| `WARDEN_SOCKET_Side_R` | (-0.0455, -0.645, 0.079) | outer face of the right (-X) side rail |
| `WARDEN_SOCKET_Side_L` | (+0.0455, -0.645, 0.079) | outer face of the left (+X) side rail |
| `WARDEN_SOCKET_Muzzle` | (0, -1.100, 0.075) | brake front face (VFX) |
| `WARDEN_SOCKET_LeftHand` | (0, -0.380, 0.030) | under the handguard, ahead of the magwell |

**Rail standard check.** These numbers were measured on the re-imported `warden_default.glb`:
- top rail: top width 0.021, top surface z 0.1375, base 0.128, cross slots every 0.010, running y +0.062 to -0.690 (full length);
- bottom rail: bottom surface z 0.0205, y -0.650 to -0.540;
- side rails: outer faces x ±0.0455, 0.060 long, centred at y -0.645.

`renders/warden_fitcheck_*` mounts the other agents' `ATT_bipod`, `ATT_laser_R` and `ATT_flashlight_L` exports on
`_Under`, `_Side_R` and `_Side_L`. Everything seats correctly. These attachments are imported only for those
renders and are never saved or exported with the Warden.

## Hierarchy, moving parts, custom properties

All custom properties below are exported: as glTF node `extras` (`export_extras=True`) and as FBX user properties
(`use_custom_props=True`). `warden_anim.json` repeats them with the glTF/Bevy axes spelled out.

**Base:** `WARDEN_Receiver`, `WARDEN_Chassis` (lower bed + magwell + chin + rear stock-adapter lug), `WARDEN_Handguard`
(free-float shell with 2x4 side slots, 2 bottom slots and 6 top vents; clamp screws merged in), `WARDEN_RailTop`,
`WARDEN_RailBottom`, `WARDEN_RailSide_R/_L`, `WARDEN_Barrel` (0.72 m, six flutes, step-down), `WARDEN_Brake` (dual chamber,
two see-through ports plus a relief port and four top vents), `WARDEN_BrakeCollar`, `WARDEN_Grip` (sand, with stipple
panels), `WARDEN_TriggerGuard`, `WARDEN_MagRelease`, `WARDEN_BoltRelease`.

The moving parts are separate objects with their origin on the pivot:
- `WARDEN_Bolt`: origin on the bolt axis at its rear (0, +0.112, 0.075). It holds the shroud, the bolt body
  visible in the ejection port, and the handle with the 48 mm knob on -X. The handle root sits on the shroud
  **behind the receiver rear face** (y 0.085 to 0.107), so it turns in free air.
  - Cycle: lift **+60 deg about local +Y in Blender** (-60 deg about local +Z in glTF), then slide 0.13 m toward the
    butt (Blender +Y, glTF -Z). Close in reverse. The whole path is clear of the receiver, both stocks, the cheek
    riser and the default optic (checked by a sweep, see "Review fixes").
  - Extras: `lift_deg`, `lift_axis`, `travel_m`, `travel_axis`, `note`.
- `WARDEN_Trigger`: pivot (0, -0.054, 0). Pull is +12 deg about local +X (`pull_deg`, `pivot_axis`).
- `WARDEN_Safety`: rotary lever on +X, origin at its hub. SAFE as modelled; FIRE = `fire_deg` -45 about local +X.

**stock_standard** (`WARDEN_StockStandard`, root = mount point):
- The root holds the graphite hinge block, the sand skeleton frame (low top beam, big chamfered triangular window,
  rear upright), the thick rubber pad with grooves, the riser-height knob (+X, on the upright), the QD cups and the
  monopod housing.
- `WARDEN_StockStandard_CheekRiser` (child) sits on two gunmetal posts on the rear upright with a 12 mm visible gap
  and overhangs forward over the bolt path. Extras: `slide_axis` Z, `travel_min_m` 0, `travel_max_m` 0.03 (up only).
- `WARDEN_StockStandard_Monopod` (child) has a knurled collar and a spike. Extras: `slide_axis` Z,
  `travel_min_m` -0.045, `travel_max_m` 0.

**stock_folding** (`WARDEN_StockFolding`, root = mount point, holding the hinge block and knuckle):
- `WARDEN_StockFolding_Arm` (child) is a lighter double-window Z skeleton with a pad. Its origin is the hinge knuckle
  (0.0315, 0.111, 0.015), 1.5 mm further out than before, so the folded arm clears the +X safety lever and the receiver side.
- Folding: rotate `fold_angle_deg` -180 about local Z (`fold_axis`), so the stock lies along the LEFT (+X) side, clear
  of the bolt handle. The `warden_alt_folded_*` renders show this pose.

**Magazines** (`WARDEN_Mag5` / `WARDEN_Mag8`, root = `_SOCKET_Mag`):
- A single-stack 12.7 mm column with real feed lips (16 mm lip gap and a 45 deg undercut). The top round stands
  3 mm proud of the lips, so it reads when the mag is out.
- A vertical **window slot** on both sides shows the stacked rounds for the mag check (DIRECTION_LOG item 8).
  There is no counter and no emissive.
- The sand base plate makes the mag read as a separate, lootable item.
- Children `WARDEN_Mag5_Round` (the top round, used for the feed/visual) and `_Round_02..` (the rest of the column)
  each carry `round_index` (1 = top). They are two-tone: light-steel case and gunmetal bullet. The game hides rounds
  from the bottom up (highest index first) to show an approximate fill level.
- Child `WARDEN_Mag5_Follower` / `WARDEN_Mag8_Follower` (origin at its centre) rides under the column. With n rounds
  left, raise it along local +Z by `min((capacity - n) * travel_per_round_m, travel_max_m)`: `travel_per_round_m`
  0.021 puts it right under the lowest remaining round; `travel_max_m` (0.094 for mag_5, 0.157 for mag_8) is the
  empty position, just under the feed lips.
- Extras on the mag root: `capacity`, `part`, `socket`.

## Triangles (evaluated, from `_wip/tris.json`)

| Part | Tris (before review) | Tris now |
|---|---|---|
| base | 15,124 | 13,940 |
| stock_standard | 4,750 | 4,484 |
| stock_folding | 3,988 | 3,390 |
| mag_5 | 2,612 | 2,172 |
| mag_8 | 3,332 | 2,604 |
| **default (base + stock_standard + mag_5)** | **22,486** | **20,596** (target 12k to 25k) |

The largest objects are the stock body (3.7k), the handguard (3.3k), the brake (2.0k) and the receiver (1.8k).
With the other agents' default `ATT_optic_sniper` (4,728) and `ATT_bipod` (3,820), the full showcase set is about
**29.1k**. That is under the 35k hard max but over the BRIEF's 25k target for the whole set (see "Review fixes").

## Materials (glTF-safe; no emissive anywhere on the gun)

| Material | Linear base colour | Rough / Metal | Detail texture (multiply strength, tile size) | Used on |
|---|---|---|---|---|
| `M_Warden_Graphite` | (0.030, 0.033, 0.040) | 0.55 / 0.15 | worn_paint 0.35, 0.30 m | receiver, chassis, handguard, rails, guard, mag body, hinge blocks |
| `M_Warden_Gunmetal` | (0.11, 0.115, 0.12) | 0.35 / 0.85 | brushed_metal 0.30, 0.16 m | barrel, brake, bolt, trigger, controls, posts, monopod, bullets |
| `M_Warden_Sand` | (0.36, 0.28, 0.18) | 0.70 / 0 | worn_paint 0.30, 0.30 m | grip, stocks, cheek riser, mag base plate |
| `M_Warden_SandStipple` | (0.36, 0.28, 0.18) | 0.78 / 0 | polymer_stipple 0.50, 0.07 m | grip stipple panels |
| `M_Warden_Rubber` | (0.035, 0.037, 0.045) | 0.90 / 0 | none | recoil pads |
| `M_Warden_Cartridge` | (0.36, 0.34, 0.30) | 0.38 / 0.35 | brushed_metal 0.30, 0.16 m | cartridge cases (steel, no brass) |

**Export details** (all checked in the exported files):
- **Colour:** each material exports as `baseColorFactor` = the palette colour multiplied by an embedded
  `baseColorTexture`. glTF cannot store a "mix strength", so `build_warden.py` bakes the subtle multiply into
  512 px derived textures: `textures/warden_<src>_<mix>.png`, computed as linear `1 - mix * (1 - src / p99.5)`.
  The renders and the engine therefore get the same colour.
  - Note: `bc.material(tex=..., tex_mix<1)` loses the colour factor in glTF, because the exporter drops a mix whose
    factor is not 1. Assets built that way export as plain grey texture.
- **Texture scale:** tiling is baked into the UVs at a constant world texel density, so there is no Mapping node
  and no `KHR_texture_transform`.
- **Primitives:** every primitive has a real material. Empty slots left by boolean unions are reassigned and removed.
- **Closed meshes:** all meshes are closed, so materials are single-sided (backface culling). A sealing pass closes
  the rare boolean/bevel sliver holes.
- **Mesh names:** mesh data is named like its object.

## Design deviations / decisions

- **No ammo counter and no emissive** (DIRECTION_LOG item 8). The BRIEF's `WARDEN_Counter`, counter recess and
  `M_Warden_CounterGlow` were left out. The LEFT side gets panel lines, a bolt-release button and a safety lever instead.
- **Scope and bipod are not part of the gun**, since they are attachments. The `stock_standard` monopod is part of the stock.
- **Proportions follow the BRIEF / `profile_sketch.png`**, which match closely (`renders/warden_compare.png`, bottom
  panel). The concept painting is drawn more compact vertically: lower rail line, shorter mag, smaller stock and
  grip. Per the BRIEF, its numbers win over the painting. The painting was used for colour blocking (dark gun,
  sand grip, stock and mag foot), the handguard slot rhythm, the chin under the receiver, and the blocky
  see-through brake.
- **Brief deviations kept from the concept list:**
  - the cheek riser is sand;
  - the bolt is on -X;
  - the brake is a rectangular 0.070 x 0.150 x 0.062 block with rectangular ports;
  - the barrel is gunmetal, not chrome;
  - there are no flip caps and no finger grooves.
- **Stock adapter:** the chassis has a rear lug (y 0.076 to 0.094) that sits inside every stock's hinge block, so
  the base gun alone still reads as finished.
- **Bolt cycle beats the BRIEF's numbers** (review fix, see below). The BRIEF never checked the bolt travel:
  - the handle root moved from the receiver notch (y 0.060) onto the shroud behind the receiver (y 0.096), so the
    knob centre is now at y 0.112 instead of 0.078. The notch became a small cam-ramp relief;
  - the stock top beam stays at z 0.045 back to y 0.238 (BRIEF: comb at 0.088 from y 0.140), and only the rear
    upright (y 0.252 to 0.292, top z 0.112) rises behind the open bolt;
  - the cheek riser is at z 0.124 to 0.146 (BRIEF 0.100 to 0.136), on posts at y 0.263 / 0.281 (BRIEF 0.180 / 0.250).
    Its top now sits about 9 mm above the rail top, which matches the concept paintings, where the riser lines up
    with the rail.

## Known limitations

- Detail textures are subtle multiplies only. There are no normal or roughness maps and no baked AO, because the
  stylized look is carried by flat colour plus geometry chamfers.
- Smart-UV islands are not packed into 0-1. They are scaled to world size and rely on repeat-wrapped tileable
  textures, which is the glTF default sampler. A future lightmap or decal pass would need a second UV set.
- The bolt is one rigid object (shroud, body, handle, knob). It does not separate the shroud from the rotating
  handle, so the shroud rotates with the bolt during the lift. At 60 deg this is barely visible.
- The magazine has no spring mesh. Below the follower, the window shows daylight, which reads as "empty here".
  The review's optional dark septum at x = 0 was left out: it would cut through every round.
- The cheek riser can only go up (`travel_min_m` 0). Lowering it would put it into the bolt path.
- The FBX files carry the flat palette colours and every custom property, but not the detail textures. Blender's
  FBX exporter cannot follow the colour x texture Mix node. This was already the case before the review. The glb
  files are the engine format and embed everything.
- The magazine is single-stack. 8 rounds therefore need the taller `mag_8` body (0.200 deep). That is intended,
  because the extended mag should read clearly.

## Review fixes (independent review in `review/`)

Each fix was verified with the reviewer's own checks, pointed at the new file names (`_wip/verify_*.py`, reports in
`_wip/`), plus renders I looked at.

| # | Severity | Issue | Fix | Verified by |
|---|---|---|---|---|
| 1 | critical | The open bolt ran through the stock comb and both riser posts (first contact after 15 to 20 mm of the 130 mm travel). | Both stocks were redesigned around the bolt path. The top beam stays at z 0.045 back to y 0.238 (folding: 0.044 to 0.240), below the shroud bottom (0.051); the comb rises only in the rear upright behind the open shroud (rear face y 0.242). The cheek riser is carried by two posts on that upright (y 0.263 / 0.281) and overhangs forward with its underside at z 0.124, above the lifted handle (highest point 0.118 within the riser's width). | `verify_bolt_fold.py`: no contact for either stock over the full 0.130 m travel. `verify_check.py`: `bolt_half_open` and `bolt_open` have no intersections. `_wip/clearance.py` sweeps lift 0 to 60 deg and travel 0 to 0.130 m in 5 mm steps: no contact. Renders: `warden_cu_bolt_open`, `warden_bolt_open_left`, `warden_bolt_open_fpv`, `warden_bolt_open_folding_stock`. |
| 2 | critical | Lifting the bolt drove the handle root 16 mm into the receiver. | Option (a): the root block moved onto the shroud behind the receiver rear face (y 0.085 to 0.107), so it turns in free air. The arm and knob moved back with it (+0.035 m). The closed-position notch shrank to a small cam-ramp relief (y 0.071 to 0.090, x < -0.027). | `verify_check.py`: `bolt_lifted` has no intersections. Render `warden_cu_bolt_lifted`. |
| 3 | major | No custom properties reached the exports. | A local `export_files()` helper exports with `export_extras=True` (glTF) and `use_custom_props=True` (FBX), since `tools/` is read-only. List properties became scalars (`travel_min_m` / `travel_max_m`) so FBX keeps them. `warden_anim.json` repeats every number with glTF axes. The material tile size no longer rides on the materials. | `review/glb_inspect.py` shows extras on `WARDEN_Bolt`, `WARDEN_Trigger`, `WARDEN_Safety`, every `WARDEN_Mag*_Round*`, `WARDEN_Mag*_Follower`, `WARDEN_Mag5/8`, `WARDEN_StockFolding_Arm`, the riser and the monopod. The property names also appear in every FBX. |
| 4 | major | Part file names broke the `<prefix>_<part>.glb` rule. | The parts now export as `WARDEN_stock_standard`, `WARDEN_stock_folding`, `WARDEN_mag_5` and `WARDEN_mag_8` (.glb + .fbx). `warden_base` and `warden_default` keep their names (like `mako_base` / `mako_default`). The build deletes the old lower-case files, and only when the on-disk name really is lower-case, because Windows ignores case. | File listing. |
| 5 | minor | A soft diagonal shading wedge sat on the handguard flank between slot columns 3 and 4. | Cause: a twisted bevel corner at a slot end shared a smooth fan with the big side face. `flat_big_faces()` marks every edge where a big planar face meets anything bent by more than 4 deg as sharp, then rebuilds the normals with a face-area WeightedNormal. | Corner-normal scan: no corner of a flat side face deviates from the face normal (before: corners bent by up to 52 deg). Clay renders `_wip/verify_renders/clay_cu_handguard_left/right.png` and `_wip/look_hg_*.png` are flat. |
| 6 | minor | A hairline crease and sliver ran along the stock top beam; zero-area faces were left on several meshes. | The window-chamfer hull now reaches only 1 mm past the outer face (was 4 mm). `dissolve_degenerate` (1e-5) runs after the booleans **and** after every bevel. The bevel itself was making most of the zero-area faces. | `verify_topology.py`: 0 degenerate faces on every mesh (review: StockStandard 60, StockFolding 20, StockFolding_Arm 8, Mag5/8 16, Grip 1). Clay render `_wip/verify_renders/clay_cu_stock.png`. |
| 7 | minor | The follower was welded into the mag, so hidden rounds left a gap above a static follower. | `WARDEN_Mag5_Follower` / `WARDEN_Mag8_Follower` are separate children (origin at their centre, 0.25 mm side clearance so they never z-fight the channel), with `travel_per_round_m` 0.021 and `travel_max_m` (empty, just under the feed lips). | Renders `warden_mag_5_check_two_left*` (2 rounds left, follower right under them) and `warden_mag_5_check_empty_top`. `_wip/verify_renders/mag5_two_left_check.png`. The optional septum was left out (see Known limitations). |
| 8 | minor | Triangle budget: the default gun was 22.5k; with the default optic and bipod it was 31k. | Trims with no visible cost: the window-only rounds use 8 sides and a reduced profile; the handguard bevels only the outer shell (the slot rims on the inner wall stay hard, -1.1k); the QD cups are lathed instead of boolean-cut; the folding pad bevel went from 3 to 2 segments; degenerate cleanup. Default gun: **20.6k** (-1.9k). | `_wip/tris.json`. |

Not done, and why:
- **Budget, item 8.** The full showcase set (gun 20.6k + the optic agent's `ATT_optic_sniper` 4.7k + the bipod 3.8k)
  is **29.1k**. That is under the 35k hard max but above the BRIEF's 25k target. Reaching 25k would mean cutting the
  gun to about 16.5k. The remaining weight is all visible in first person: the bolt knob, the slotted handguard
  outer shell, the brake ports, the stock windows. Cutting it there would lower quality where the player looks
  most. The optic, at 4.7k against the BRIEF's 4k, belongs to another agent.
- **Septum, item 7 (optional).** The dark septum at x = 0 was not added: it would pass through every cartridge.
  Below the raised follower, the window shows daylight, and that reads as "empty here", which is what the mag
  check needs.

**Git note for the rename (item 4):** this repo runs with `core.ignorecase`, so `git status` lists the new
`WARDEN_*` files as *modified* under their old lower-case names. Unless the rename is recorded with
`git mv -f warden_stock_standard.glb WARDEN_stock_standard.glb` (and the same for the other 7 files), the
committed names stay lower-case, and Linux checkouts would miss the parts again.

Side effect found and fixed: with the lower top beam, the **folded** folding stock touched the +X safety lever
(1.45 mm). The hinge knuckle moved out to x 0.0315 (`KNUCKLE_X`), so the folded arm now clears the safety and the
receiver side (the old 1 mm receiver touch is gone too). `_wip/clearance.py` reports "FOLDED arm overlaps: none".

## Renders (`renders/`)

- **Assembled default (no scope or bipod):** `warden_right`, `_left`, `_three_quarter`, `_three_quarter_back`, `_top`,
  `_front`, `_back`, `_low`, `_fpv` (roughly the player's view) and `_exact_side` (1 px = 1 mm ortho, transparent).
- **Close-ups:** `warden_cu_brake`, `_bolt`, `_bolt_lifted`, `_bolt_open`, `_receiver_right`, `_receiver_left`,
  `_handguard_under`, `_magwell`.
- **Bolt cycle (review fixes 1 and 2):** `warden_cu_bolt_lifted` (lifted in place, root turns behind the receiver),
  `warden_cu_bolt_open`, `warden_bolt_open_left` (side), `warden_bolt_open_fpv` (shooter's view) and
  `warden_bolt_open_folding_stock`.
- **Variants:** `warden_stock_standard_*`, `warden_stock_folding_*`, `warden_mag_5_*`, `warden_mag_8_*` (incl.
  `_top_feedlips`), `warden_mag_5_check_*` (2 rounds left with the follower raised; empty with the follower under
  the lips), `warden_base_only_*`, `warden_alt_*` (folding stock + mag_8) and `warden_alt_folded_*`.
- **Checks:**
  - `warden_sockets_*`: coloured socket markers;
  - `warden_fitcheck_*`: other agents' bipod, laser and flashlight mounted;
  - `warden_compare.png`: the concept, the build with a metric grid, and the build outline over the concept and over `profile_sketch.png`;
  - `warden_compare_overlay.png`: a 55 % blend of the build over the concept;
  - `warden_silhouette.png`: 64, 128 and 256 px reads.
- **Contact sheets:** `warden_contact_sheet.png` (assembled gun and close-ups) and `warden_contact_parts.png`
  (stocks, mags, base, alternative loadout).
