# VK-50 "WARDEN": build notes

A heavy-calibre (12.7 mm class) bolt-action anti-materiel sniper, built as a **modular base gun plus swappable
stocks and magazines**. The scope (`optic_sniper` / `optic_thermal`) and the `bipod` are shared attachments that
other agents build in `assets/weapons/attachments/`. They are not part of this asset (DIRECTION_LOG items 1 and 8).

Sources, in order of authority: `art/DIRECTION_LOG.md` (item 13: **proportions follow
`art/concepts/warden/concept_main.png`**) > `art/STYLE_GUIDE.md` > `art/WEAPON_MODULAR_SPEC.md` >
`art/concepts/warden/BRIEF.md`. The BRIEF's numbers and `profile_sketch.png` are superseded wherever they disagree
with the concept painting.

## Proportion revision (user feedback: "more bulky and stumpy than the concept art")

The first build followed the BRIEF's profile sketch. This revision re-traces `concept_main.png` at 1 px = 1 mm,
aligned on the brake front and the bore (`compare.py` traces the concept outline without scope and bipod).

| Part | Before | Now (concept) |
|---|---|---|
| Upper (handguard + receiver) | one 0.16 m block, rail top z 0.1375 | slim handguard, 56 mm wide x 70 mm tall + rail; **rail top z 0.117** (42 mm over the bore); separate upper receiver over a separate lower (chassis) |
| Handguard length | to y -0.700, little barrel showing | nose tip y -0.677 with the concept's raked nose; 0.31 m of fluted barrel shows |
| Slots | 2 x 4 | 2 staggered rows of 3, at the concept's slot centres (within 4 mm) |
| Magazine | 158 mm long, base plate down to z -0.168, sand base plate | **145 mm long**, base plate at z -0.064 (front) to -0.076 (rear), all graphite like the concept |
| Stock | tall block, riser on posts, big pad, monopod spike | slim sand skeleton: top line z 0.063, big chamfered window, diagonal brace, dark riser on 2 posts + lock block, pad z -0.086..0.090; **no spike** (retracted monopod, foot flush in a pocket) |
| Pistol grip / guard | larger, steeper | concept rake and size; guard y -0.140..-0.056 |
| Bolt | domed shroud Ø 48 mm | flat-ended shroud Ø 30 mm (concept), body r 0.0142, hex knob at z 0.025 like the concept |

Result: **silhouette IoU 0.919** against the traced concept (the original build: 0.538, measured on its
`warden_exact_side.png` from git HEAD with the same trace). Station by station the outline is within 3 mm; the
top line reads ±6 mm only where the concept's rail teeth and scope rings are cut out of the trace. The remaining
differences are deliberate:
- the magazine starts 15 mm further forward than the painting, because a real 12.7 x 99 mm cartridge is 138 mm
  long and the painted mag (130 mm) could not hold it. Its rear face, depth and slope match;
- the side rails (in the nose) and the bottom rail are required by WEAPON_MODULAR_SPEC; the painting has neither;
- the bolt handle is on the shooter's right (-X) per the modular spec, so in the left-side view it hides behind
  the chassis, while the painting draws it on the visible side.

## Rebuild

```
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P build_warden.py -- --render full
python compare.py        # concept comparison + IoU, zoomed outline crops, silhouettes, labelled contact sheets
```

- `--render none|quick|compare|full|fitcheck`, `--samples N` (default 48), `--no-export`; debug-only:
  `--no-det-check`, `--no-gate`, `--out <folder>`.
- The script builds everything from scratch **twice** (about 3 s each) and exports only if both builds are
  identical, every mesh passes the closed-mesh gate and the opening checks pass (see "Build safety"). A full
  render pass takes about 3 minutes on the GPU and falls back to CPU Cycles by itself.
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
| `compare.py` | concept comparison (outline trace, IoU, zoom crops), silhouettes, contact sheets |
| `renders/` | see the end of this file |
| `_wip/` | scratch and checks: `tris.json`, `signature.json`, `gate_blend.json`, `gate_glb.json` (written by every build); `clearance.py` (bolt-cycle / fold / safety sweep on the built scene); `attach_check.py` (other agents' optics, bipod, laser, flashlight mounted: overlaps, bolt sweep with each optic, renders `att_*.png`); `verify_r2_check.py` (the round-2 reviewer's check, spec values updated, report `verify_r2_check_report.json`); `look.py` (quick iteration renders); `det_probe.py` / `nm_probe.py` (debug: boolean determinism, non-manifold trace). The `verify_check.py` / `verify_bolt_fold.py` / `verify_topology.py` / `verify_render.py` files are round-1 checks with the old spec values. |
| `review/` | the independent reviews (round 1 and `r2/`, `critique_latest.json`); left untouched |

## Axes, origin, handedness

- Metres, Blender Z-up, **muzzle toward -Y**, bore axis at x = 0, z = 0.075.
- Origin (0,0,0) is the top centre of the pistol grip. glTF export is Y-up: Blender (x, y, z) becomes glTF
  (x, z, -y), so the muzzle points to glTF +Z.
- **Shooter's RIGHT = -X:** ejection port, bolt handle and hex knob, and `_SOCKET_Side_R`.
  **LEFT = +X:** bolt window (shows the bolt), bolt-release button, rotary safety lever, maker-plate recess and
  `_SOCKET_Side_L`. This follows WEAPON_MODULAR_SPEC.
- Overall default length: y -1.100 (brake face) to +0.320 (recoil pad), so 1.42 m.

## Sockets (children of `WARDEN_Root`, zero rotation)

The revision moved every socket except Muzzle with its part. **Game side: re-read the socket nodes / `sockets.json`;
the optic now sits 20.5 mm lower and 0.11 m further forward than in the first build.**

| Socket | Location (x, y, z) | Before | Notes |
|---|---|---|---|
| `WARDEN_SOCKET_Optic` | (0, -0.190, 0.117) | (0, -0.080, 0.1375) | top-rail top surface over the receiver (concept ring centre) |
| `WARDEN_SOCKET_Stock` | (0, +0.022, 0.075) | (0, +0.080, 0.075) | chassis rear face on the bore axis; every stock clamps over the chassis lug here |
| `WARDEN_SOCKET_Mag` | (0, -0.299, 0.046) | (0, -0.270, 0.000) | top-front of the magwell opening (mag top-front lip) |
| `WARDEN_SOCKET_Under` | (0, -0.600, 0.0275) | (0, -0.600, 0.0205) | bottom-rail bottom surface (bipod) |
| `WARDEN_SOCKET_Side_R` | (-0.0375, -0.643, 0.066) | (-0.0455, -0.645, 0.079) | outer face of the right (-X) side rail |
| `WARDEN_SOCKET_Side_L` | (+0.0375, -0.643, 0.066) | (+0.0455, -0.645, 0.079) | outer face of the left (+X) side rail |
| `WARDEN_SOCKET_Muzzle` | (0, -1.100, 0.075) | same | brake front face (VFX) |
| `WARDEN_SOCKET_LeftHand` | (0, -0.450, 0.037) | (0, -0.380, 0.030) | under the handguard, between the bottom rail and the magwell |

**Rail standard check** (measured on the re-imported `warden_default.glb` by `_wip/verify_r2_check.py`; all 8
sockets 0.000 mm off, zero rotation, parented to the root):
- top rail: top surface z 0.117, top width 0.021, base 0.1075 (height 0.0095), cross slots every 0.010,
  y -0.640 to -0.110 (0.53 m), 45-degree ramped ends;
- bottom rail: bottom surface z 0.0275, y -0.655 to -0.545;
- side rails: outer faces x ±0.0375, 0.040 long (4 slots), y -0.663 to -0.623, centred z 0.066 in the nose, ahead
  of the lower slot row.

`_wip/attach_check.py` and the reviewer's check mount the other agents' exports: `ATT_optic_sniper` (ADS line
z 0.1575, 40.5 mm over the rail top) and `ATT_optic_thermal` (ADS z 0.169) have no overlap with the gun and clear
the whole bolt cycle by 23 mm and more; `ATT_bipod`, `ATT_laser_R/_L` and `ATT_flashlight_L/_R` clamp onto their
rails with no contact with anything else. `renders/warden_fitcheck_*` shows them; they are never saved or exported
with the Warden.

## Hierarchy, moving parts, custom properties

All custom properties below are exported: as glTF node `extras` (`export_extras=True`) and as FBX user properties
(`use_custom_props=True`). `warden_anim.json` repeats them with the glTF/Bevy axes spelled out.

**Base:**
- `WARDEN_Receiver`: the slim upper, y -0.336 to -0.100, x ±0.030, z 0.054 to the rail base. It has the raceway,
  the -X ejection port and the +X bolt window (both with 45-degree lead-in chamfers), and a short chamfered rear face.
- `WARDEN_Chassis`: the lower receiver, y -0.3375 to +0.022, x ±0.0275, top line z 0.063 with a **bolt channel**
  (r 0.0165) that the shroud and the open bolt ride in. It holds the concept's front corner and sloped magwell lip,
  the chin under the handguard, the trapezoid relief, the maker-plate recess, stock-release latch recesses,
  take-down pins (both sides) and the rear stock-adapter lug.
- `WARDEN_Handguard`: a slim free-float shell, y -0.677 (raked nose) to -0.336, with 2 staggered rows of 3 side
  slots, 2 bottom slots and hex clamp screws.
- Rails: `WARDEN_RailTop`, `WARDEN_RailBottom`, `WARDEN_RailSide_R/_L`.
- Barrel and brake: `WARDEN_Barrel` (r 0.0175, six flutes), `WARDEN_Brake` (108 x 52 x 47 mm, three see-through
  ports), `WARDEN_BrakeCollar`.
- `WARDEN_Grip` (sand, with stipple panels), `WARDEN_TriggerGuard`, `WARDEN_MagRelease` (paddle in front of the
  guard), `WARDEN_BoltRelease`.

The moving parts are separate objects with their origin on the pivot:
- `WARDEN_Bolt`: origin on the bolt axis at the shroud's flat rear face, (0, -0.045, 0.075). It holds the shroud
  (with its cocking-indicator stub), the bolt body (fluted toward the port and the window) and the handle with the
  hex knob on -X. The handle root sits on the shroud **behind the receiver rear face** (y -0.093 to -0.077), so it
  turns in free air. The arm leans out 32 degrees, so it clears the chassis top edge by 2.5 mm.
  - Cycle: lift **+60 deg about local +Y in Blender** (-60 deg about local +Z in glTF), then slide 0.13 m toward the
    butt (Blender +Y, glTF -Z). Close in reverse. `_wip/clearance.py` sweeps lift 0 to 60 deg and travel 0 to
    0.13 m in 5 mm steps against the base, both stocks and the riser: no contact. The reviewer's sweep (exports,
    with both optics) agrees.
  - Extras: `lift_deg`, `lift_axis`, `travel_m`, `travel_axis`, `note`.
- `WARDEN_Trigger`: pivot (0, -0.090, 0.012). Pull is +12 deg about local +X (`pull_deg`, `pivot_axis`).
- `WARDEN_Safety`: rotary lever on +X, origin at its hub (0.028, -0.036, 0.034), 0.5 mm off the chassis side.
  SAFE as modelled; FIRE = `fire_deg` -45 about local +X. Collision-free in both positions.

**stock_standard** (`WARDEN_StockStandard`, root = mount point):
- The root holds the sand skeleton frame (front block with sling slot and joint seam, top beam at z 0.063 with the
  bolt channel up to y 0.093, big chamfered window, diagonal brace, rear upright, corner pockets), the riser
  collars and lock block with a knurled knob on +X, the QD cups, the length-of-pull rods, the sand spacer plate and
  the grooved rubber pad. The frame uses one crisp chamfer, like the concept's painted chamfer bands.
- `WARDEN_StockStandard_CheekRiser` (child): a dark pad, z 0.0725 to 0.1025, y 0.087 to 0.2475, on two posts
  60 mm apart (y 0.135 / 0.195) with the lock block between them. Its nose has a steep underside chamfer, so it
  reaches over the open shroud's rear face with 2 mm to spare. Extras: `slide_axis` Z, `travel_min_m` 0,
  `travel_max_m` 0.012 (up only).
- `WARDEN_StockStandard_Monopod` (child, optional detail): retracted, the column is hidden in the rear upright and
  only the knurled foot shows, flush in a pocket under the upright (nothing below the stock line). Origin = foot
  underside centre. Extras: `slide_axis` Z, `travel_min_m` -0.105 (extended foot at z -0.185), `travel_max_m` 0.

**stock_folding** (`WARDEN_StockFolding`, root = mount point, holding the hinge block and knuckles):
- `WARDEN_StockFolding_Arm` (child) is a lighter double-window skeleton with a pad, top line z 0.0585 with the bolt
  channel. Its origin is the hinge knuckle (0.030, 0.034, 0.032).
- Folding: rotate `fold_angle_deg` -180 about local Z (`fold_axis`), so the stock lies along the LEFT (+X) side,
  clear of the bolt handle. The folded arm touches nothing (safety lever included). The `warden_alt_folded_*`
  renders show this pose.

**Magazines** (`WARDEN_Mag5` / `WARDEN_Mag8`, root = `_SOCKET_Mag`):
- A double-stack 12.7 mm box, 145 mm long (2.5 mm walls, 140 mm channel for the 138 mm round), 39 mm wide. The top
  round sits centred in real feed lips (16 mm gap, 45-degree undercut) and stands 3 mm proud of them; rounds 2+
  alternate ±6 mm.
- A vertical **window slot** on both sides (z 0.027 down to the follower's full-mag bottom) shows the rounds for
  the mag check (DIRECTION_LOG item 8). Seated, the part of the window above the magwell lip is covered by the
  magwell walls, and nothing below the follower shows daylight. There is no counter and no emissive.
- Children `WARDEN_Mag5_Round` (the top round) and `_Round_02..` each carry `round_index` (1 = top). The rounds are
  two-tone: light-steel case and gunmetal bullet. The game hides rounds from the bottom up (highest index first).
- Child `WARDEN_Mag5_Follower` / `WARDEN_Mag8_Follower` (7 mm thick, origin at its centre) rides under the
  column. With n rounds left, raise it along local +Z by `offset_by_rounds_left_m[n]` (a comma string in the
  extras, a list in `warden_anim.json`), because the step under the centred top round is bigger than
  `travel_per_round_m` (0.017):
  - mag_5: 0.0797, 0.0708, 0.0510, 0.0340, 0.0170, 0.0 for 0..5 rounds left;
  - mag_8: 0.1307, 0.1218, 0.1020, 0.0850, 0.0680, 0.0510, 0.0340, 0.0170, 0.0 for 0..8 rounds left.
- Extras on the mag root: `capacity`, `part`, `socket`.

## Triangles (evaluated, from `_wip/tris.json`)

| Part | Round-2 review build | Now |
|---|---|---|
| base | 13,940 | 11,130 |
| stock_standard | 4,484 | 3,956 |
| stock_folding | 3,390 | 2,958 |
| mag_5 | 2,172 | 1,808 |
| mag_8 | 2,604 | 2,144 |
| **default (base + stock_standard + mag_5)** | **20,596** | **16,894** (target 12k to 25k; reviewer's aim ≤ 17k) |

The largest objects are the stock body (3.3k), the handguard (2.3k), the chassis (1.7k) and the brake (1.5k). With
the other agents' `ATT_optic_sniper` (4,728) and `ATT_bipod` (3,820), the full showcase set is about **25.4k**
(BRIEF target 25k, hard max 35k). The savings came from the MANIFOLD booleans (fewer stray vertices), exact
stadium polygons, and single crisp chamfers on the stock frame, chassis, receiver and mag base plate.

## Materials (glTF-safe; no emissive anywhere on the gun)

| Material | Linear base colour | Rough / Metal | Detail texture (multiply strength, tile size) | Used on |
|---|---|---|---|---|
| `M_Warden_Graphite` | (0.030, 0.033, 0.040) | 0.55 / 0.15 | worn_paint 0.35, 0.30 m | receiver, chassis, handguard, rails, guard, mag body + base plate, riser, hinge block |
| `M_Warden_Gunmetal` | (0.11, 0.115, 0.12) | 0.35 / 0.85 | brushed_metal 0.30, 0.16 m | barrel, brake, bolt, trigger, controls, posts, monopod, pins, bullets |
| `M_Warden_Sand` | (0.36, 0.28, 0.18) | 0.70 / 0 | worn_paint 0.30, 0.30 m | grip, stocks, spacer plate |
| `M_Warden_SandStipple` | (0.36, 0.28, 0.18) | 0.78 / 0 | polymer_stipple 0.50, 0.07 m | grip stipple panels |
| `M_Warden_Rubber` | (0.035, 0.037, 0.045) | 0.90 / 0 | none | recoil pads |
| `M_Warden_Cartridge` | (0.36, 0.34, 0.30) | 0.38 / 0.35 | brushed_metal 0.30, 0.16 m | cartridge cases (steel, no brass) |

**Export details** (all checked in the exported files):
- **Colour:** each material exports as `baseColorFactor` = the palette colour multiplied by an embedded
  `baseColorTexture`. glTF cannot store a "mix strength", so `build_warden.py` bakes the subtle multiply into
  512 px derived textures: `textures/warden_<src>_<mix>.png`, computed as linear `1 - mix * (1 - src / p99.5)`.
  The renders and the engine therefore get the same colour.
- **Texture scale:** tiling is baked into the UVs at a constant world texel density, so there is no Mapping node
  and no `KHR_texture_transform`.
- **Primitives:** every primitive has a real material. Empty slots left by boolean unions are reassigned and removed.
- **Closed meshes, triangles only:** all meshes are closed and triangulated in Blender (beauty), so materials are
  single-sided (backface culling) and the glb ships exactly the checked triangles.
- **Mesh names:** mesh data is named like its object.

## Build safety (gates in `build_warden.py`)

- **MANIFOLD booleans.** Blender 5.2's EXACT solver is not deterministic: the same two prisms gave different vertex
  positions in about 1 run in 4, even with `-t 1` (`_wip/det_probe.py`). Every boolean now goes through a local
  `boolean()` with the MANIFOLD solver, which is deterministic and leaves fewer stray vertices. A boolean whose
  cutter reaches the object but changes nothing is logged (MANIFOLD refuses non-manifold operands).
- **Determinism:** the script builds twice and compares a per-mesh signature (tris, verts, sum of |coords| within
  1e-5 m). Any difference stops the build before export.
- **Mesh gate** before export: after a 1e-6 m positional weld, 0 boundary edges, 0 non-manifold edges, 0 zero-area
  triangles and no n-gons on every mesh (`_wip/gate_blend.json`). `tri_clean()` removes zero-area triangles by
  rotating the long edge of needle triangles and collapsing sub-0.05 mm crumbs; `rounded_rect()` makes exact
  stadiums (the old 0.999 radius clamp left 19 µm edges that turned into slivers).
- **Opening checks** on the final meshes: rays through every handguard slot must pass through cleanly, and 9 rays
  up through the magwell must reach the bridge under the receiver. A 1 mm magwell wall once made the bevel build
  faces right across the well, which a closed-mesh gate cannot see.
- **Re-import gate:** every exported glb is re-imported, welded at 1e-6 m and gated again (`_wip/gate_glb.json`:
  66 meshes in 6 files, 0 failing).

## Design deviations / decisions

- **No ammo counter and no emissive** (DIRECTION_LOG item 8). The concept's cyan counter on the lower receiver is a
  plain maker-plate recess. The concept's gunmetal strip on the upper is a real chamfered window onto the bolt.
- **Scope and bipod are not part of the gun**, since they are attachments. The `stock_standard` monopod is a
  retracted, optional detail (the concept has no spike).
- **Concept deviations kept:**
  - magazine 15 mm longer than painted (real cartridge length), see above;
  - side rails in the nose and a short bottom rail (modular spec);
  - bolt handle on -X (modular spec handedness);
  - the cheek riser is dark graphite, as painted (the first build had it sand).
- **Stock adapter:** the chassis has a rear lug (y 0.018 to 0.036) that sits inside every stock's front block, so
  the base gun alone still reads as finished.
- **Bolt channel:** the chassis and stock tops sit at the concept's line (z 0.063) and carry a channel
  (r 16.5 mm, 23 mm wide at the top face) for the bolt. The closed shroud sits 3 mm down in it, so no daylight shows under it from the side, and the open
  bolt slides through with 1.5 mm radial clearance.

## Known limitations

- Detail textures are subtle multiplies only. There are no normal or roughness maps and no baked AO, because the
  stylized look is carried by flat colour plus geometry chamfers.
- Smart-UV islands are not packed into 0-1. They are scaled to world size and rely on repeat-wrapped tileable
  textures, which is the glTF default sampler. A future lightmap or decal pass would need a second UV set.
- The bolt is one rigid object (shroud, body, handle, knob), so the shroud rotates with the bolt during the lift.
  At 60 deg this is barely visible.
- The magazine has no spring mesh. With few rounds left the window shows the follower high up and daylight below
  it, which is the intended "almost empty" read of the mag check.
- The cheek riser can only go up (`travel_min_m` 0). Lowering it would put it into the bolt path.
- Hidden interior overlaps are intended: riser posts, monopod column and the chassis lug sit inside the stock body.
- The chassis bridge over the magwell is solid (no feed path is modelled; feeding is not animated).
- The FBX files carry the flat palette colours and every custom property, but not the detail textures (Blender's
  FBX exporter cannot follow the colour x texture Mix node). The glb files are the engine format and embed
  everything.

## Review round 2 (`review/critique_latest.json`): what was done

| # | Severity | Issue | Fix in this revision | Verified by |
|---|---|---|---|---|
| 1 | major | Two +X handguard top vents were ghost pockets; the handguard was not closed. | The slim handguard has no top vents (the concept has none). Every slot is ray-tested on the final mesh; mesh and re-import gates require 0 boundary edges. | build log "slot check"; `_wip/gate_*.json` |
| 2 | major | The upper slot row was see-through (bright "glow" pills). | Both rows lie inside the barrel's side silhouette (upper z 0.081 to 0.091, lower 0.0595 to 0.0695; barrel 0.0575 to 0.0925). | `renders/warden_check_brightbg_*` (snow-bright backdrop: slots stay dark) |
| 3 | major | The riser was a 128 mm pad on two posts 18 mm apart at its rear ("Γ" hook). | The concept layout: a continuous top beam (the bolt runs in a channel), riser on two posts 60 mm apart with the lock block between them. | `renders/warden_cu_stock_left.png`, bolt sweep |
| 4 | minor | Domed shroud and smooth knob read as two balls. | Flat shroud end with one chamfer and a cocking-indicator stub; 6-sided hex knob. | `renders/warden_fpv.png`, `warden_cu_bolt.png` |
| 5 | minor | The build was not deterministic. | MANIFOLD solver (EXACT was the cause, see Build safety), index-sorted `seal()`, build-twice check. | build log "two builds identical" |
| 6 | minor | Zero-area and sliver triangles in the glb. | Blender-side beauty triangulation + `tri_clean()`, exact stadiums, gates. | `_wip/gate_glb.json` (0 zero-area) |
| 7 | minor | Git case trap on the part files. | **Not done here** (no git operations in this session). Before committing: `git mv -f warden_<part>.<ext> WARDEN_<part>.<ext>` for the 8 part files, then check `git ls-files assets/weapons/vk50_warden`. | — |
| 8 | minor | Showcase set over the 25k target. | Default gun 20.6k → **16.9k**; with optic + bipod about 25.4k. | `_wip/tris.json` |
| 9 | minor | Daylight under the follower of a full, seated mag. | The window ends at the full-mag follower bottom. | `renders/warden_right.png`, `warden_cu_magwell.png` |
| 10 | minor | The +X hero side had no focal point. | Chamfered bolt window showing the bolt (the concept's strip), maker-plate recess, take-down pins, trapezoid relief, bolt release, safety. | `renders/warden_cu_receiver_left.png` |

Also found and fixed in this pass:
- a 1 mm see-through slit between the handguard rear and the chassis front (the chassis now runs 1.5 mm into it);
- daylight under the bolt shroud (bolt channel);
- coplanar end caps of the chassis channel and the receiver raceway (the reviewer's z-fight check now finds none);
- the safety hub sat flush on the chassis side (now 0.5 mm off).

## Renders (`renders/`)

- **Assembled default (no scope or bipod):** `warden_right`, `_left`, `_three_quarter`, `_three_quarter_back`, `_top`,
  `_front`, `_back`, `_low`, `_fpv` (roughly the player's view) and `_exact_side` (1 px = 1 mm ortho, transparent).
- **Close-ups:** `warden_cu_brake`, `_bolt`, `_bolt_lifted`, `_bolt_open`, `_receiver_right`, `_receiver_left`,
  `_handguard_under`, `_handguard_left`, `_magwell`, `_stock_left`, `_stock_under` (monopod foot flush),
  `_monopod_extended`.
- **Bolt cycle:** `warden_cu_bolt_lifted`, `warden_cu_bolt_open`, `warden_bolt_open_left` / `_right` (side),
  `warden_bolt_open_fpv` (shooter's view) and `warden_bolt_open_folding_stock`.
- **Variants:** `warden_stock_standard_*`, `warden_stock_folding_*`, `warden_mag_5_*`, `warden_mag_8_*` (incl.
  `_top_feedlips`), `warden_mag_5_check_*` (2 rounds left; empty), `warden_base_only_*`, `warden_alt_*` (folding
  stock + mag_8) and `warden_alt_folded_*`.
- **Checks:**
  - `warden_compare.png`: the concept, the build with a metric grid, the build outline over the concept, and both
    outlines (concept traced without scope and bipod in cyan, build in red) with the silhouette IoU;
  - `warden_compare_zoom.png`: the same outlines at 2 px/mm for the front, middle and rear of the gun;
  - `warden_compare_overlay.png`: a 55 % blend of the build over the concept;
  - `warden_silhouette.png`: 64, 128 and 256 px reads;
  - `warden_check_brightbg_*`: snow-bright backdrop (no see-through slots);
  - `warden_sockets_*`: coloured socket markers;
  - `warden_fitcheck_*`: other agents' bipod, laser and flashlight mounted (`_wip/att_*.png` adds both optics).
- **Contact sheets:** `warden_contact_sheet.png` (assembled gun and close-ups) and `warden_contact_parts.png`
  (stocks, mags, base, alternative loadout).
