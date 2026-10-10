# AR-7 "MAKO": build notes

A modernised M4-style assault rifle, built procedurally in Blender. Prefix `MAKO`.
The master reference is `art/concepts/mako/v09.png` (DIRECTION_LOG item 2). v04 and v02 were used to check the straight side
profile. Dimensions come from `art/concepts/mako/BRIEF.md` wherever the direction log or the reviews do not override them.

Every file in this folder (GLB, FBX, blend, `sockets.json`, `tri_counts.json`, `textures/`, `renders/`) comes from one
run of `build_mako.py` (r4, 2026-10-07; log in `_work/r4/final_build.log`). The fixes for the r2 review are listed in
"Review fixes (round 2)" at the end.

## Direction decisions applied
- **No iron sights and no ammo counter.** There is no display and no glow anywhere. The base gun and its parts have **no
  emissive material**. `check_glb.py` reports it as an error, and the build then stops with exit code 1.
- **Free-float handguard:** long and slightly squared, with chamfered corners. It runs to y −0.495, 70 mm short of the
  muzzle face. It has **3 rows of rounded slots** (pills with 8-segment round ends): two rows on each side face and a
  third row on the lower chamfers. A full-length top rail runs from y −0.493 to +0.022, plus a bottom rail and two short
  side rails. A 4.5 mm rear bulkhead closes the handguard where it meets the upper.
- **A slotted birdcage flash hider** (5 slots, closed bottom), with two washer rings behind it. It replaces the brief's angular comp.
- **Graphite receiver.** The pistol grip, magazines and stocks are **bone**. Rubber butt pads, graphite mag floorplates.
- **Mag window:** a long vertical slot (8.8 mm wide) on both sides, with brass cartridges behind it. There is one node per
  visible cartridge, so the engine can show roughly how full the mag is in a mag check (see "Mag check").

## Files
| File | What |
|---|---|
| `build_mako.py` | Re-runnable build, from scratch to every output: geometry, sockets, clearance checks, renders, exports, validation. Run `blender -b --factory-startup --python-exit-code 1 -P build_mako.py` (flags and debug switches in the docstring). About 5 min with renders (Cycles, 48 spp, about 100 images), about 10 s with `--no-render`. |
| `mako_lib.py` | Geometry helpers (prisms, lofts, lathes, booleans, rails), the hard-surface finish (per-edge bevel offsets, spike/fold guard, normal-preserving cleanup, see "Hard-surface finish"), glTF-safe materials, UV density. |
| `render_mako.py`, `make_sheets.py` | Preview renders, contact sheets, and the v09 / v04 / v02 comparisons. Set `MAKO_RD=<dir>` to send iteration renders somewhere other than `renders/`. |
| `check_glb.py` | Validates every GLB: names, sockets against `sockets.json`, a material on every primitive, UVs and normals, embedded images, no emissive, no helper nodes, the engine extras (CH stroke, FA push, stock travel, mag-check rounds) and zero-area triangles. Exits 1 on any error. `build_mako.py` runs it after the export and exits 1 if it fails. |
| `mako.blend` | Everything in collections: `MAKO_Base`, `MAKO_stock_standard/_precision/_light`, `MAKO_mag_30/_45/_drum60`. The default loadout is visible. Textures are packed. |
| `mako_base.glb/.fbx` | Base gun: `MAKO_Root` + base meshes + 9 socket empties. No stock, no mag. |
| `MAKO_stock_standard/_precision/_light.glb/.fbx` | Stocks. Origin = stock mount point (`_SOCKET_Stock`). |
| `MAKO_mag_30/_45/_drum60.glb/.fbx` | Magazines. Origin = top-front lip (`_SOCKET_Mag`). |
| `mako_default.glb` | Assembled preview: base + stock_standard + mag_30. |
| `sockets.json`, `tri_counts.json` | Socket table (metres, Blender axes) and evaluated triangle counts. |
| `textures/` | Baked, tinted copies of the shared detail maps (embedded in the GLBs). |
| `renders/` | All views, close-ups, variants, review-fix verification shots (`fix_*` = r2 review, `fix2_*` = round 2), the comparisons and `contact_sheet*.png`. |
| `_work/` | Scratch: camera search for the v09 match, iteration renders, previous script versions, `ch_sweep.json` (clearance report of the last build), `compare_v09_iou.txt`, `r4/` (this pass's probes and iteration shots). |

## Axes, origin, handedness
- Metres. Blender Z-up. Muzzle toward **−Y**. Bore on Y at **z 0.050**. Origin (0,0,0) = pistol-grip hand position.
- Shooter's **RIGHT = −X**: ejection port, dust cover, brass deflector, forward assist, charging-handle latch, mag release.
  Shooter's **LEFT = +X** (the side the player sees): bolt catch, selector, upper panel line.
- glTF exports are Y-up (exporter conversion). FBX uses forward −Z, up Y, scale 1.0. Custom properties travel as glTF
  `extras` and FBX user properties.

## Dimensions (default loadout: base + stock_standard + mag_30, no optic)
| | Value |
|---|---|
| Overall length | 0.844 m (flash hider face y −0.565 to butt pad y +0.279) |
| Height | 0.258 m (butt pad top z 0.0845, rail top z 0.084, to mag_30 floorplate z −0.173) |
| Width | ±0.0325 (side-rail faces). Receiver ±0.0168 (shoulder pads ±0.018), handguard ±0.023 |
| Rail standard | Top width 0.021, height 0.0095 above the base, cross slots every 0.010 (0.0052 wide, 0.003 deep), dovetail base 0.015 |
| Top rail | y −0.493 … +0.022, base z 0.0745, top z 0.084 (51 slots) |
| Bottom rail | y −0.400 … −0.270, base z 0.017, face z 0.0075 |
| Side rails | y −0.474 … −0.424, base x ±0.023, face x ±0.0325, centred z 0.050 |
| Handguard | y −0.495 … −0.168, z 0.017 … 0.0745, 2.8 mm wall, 4.5 mm rear bulkhead; per side 14 side-face slots (2 rows) + 9 lower-chamfer slots, plus a QD cup |
| Grip | Lofted, raked about 20°; beavertail tang, A2-style finger knuckle (z −0.045, ~3.5 mm proud of the front line), palm swell, flared base, stippled side panels; base z −0.115 |
| mag_30 / mag_45 | 0.064 deep inside the well, flaring to 0.0735 below it, 0.025 wide; curve radius 0.48 / 0.46 over 15° / 24°; floorplate low point z −0.173 / −0.246 |
| mag_drum60 | Drum R 0.052, 0.062 wide, centre (y −0.121, z −0.093), low point z −0.146, arc windows on the rear-lower quarter of both faces, primed case heads |
| Stock travel | stock_standard: 4 positions, 0 / 0.0145 / 0.029 / 0.0435 toward −Y |

## Sockets (empties, children of `MAKO_Root`, zero rotation; also in `sockets.json`)
| Socket | Location (x, y, z) | Notes |
|---|---|---|
| `MAKO_SOCKET_Optic` | (0, −0.0855, 0.084) | Rail top, on a cross-slot centre over the receiver |
| `MAKO_SOCKET_Stock` | (0, 0.215, 0.050) | Buffer-tube end on the bore |
| `MAKO_SOCKET_Mag` | (0, −0.152, 0.012) | Top-front lip of a seated mag |
| `MAKO_SOCKET_Under` | (0, −0.335, 0.0075) | Bottom-rail face, on a slot centre |
| `MAKO_SOCKET_Side_R` | (−0.0325, −0.449, 0.050) | Shooter's right (−X), side-rail outer face |
| `MAKO_SOCKET_Side_L` | (+0.0325, −0.449, 0.050) | Shooter's left (+X) |
| `MAKO_SOCKET_Shield` | (0, −0.4755, 0.084) | Front end of the top rail, centreline |
| `MAKO_SOCKET_Muzzle` | (0, −0.565, 0.050) | Flash-hider face on the bore |
| `MAKO_SOCKET_LeftHand` | (0, −0.330, 0.0075) | Support-hand IK target under the handguard |

`_Under` and `_LeftHand` sit at z 0.0075 (the delivered 09:01 build had 0.0155): the handguard is 8 mm deeper to match v09
(r2 review), and the bottom rail moved down with it. The under-rail attachments snap to the socket, so they follow; the r2
review fit all 12 shared attachments on these sockets with 0 mm penetration. The other values differ slightly from the
brief's table because they are the real rail faces and slot centres. **Side_R is at −X**, per the modular spec.
`check_glb.py` compares every GLB's socket nodes with `sockets.json` (1e-4 m tolerance); both come from the same run.

## Moving parts and engine data
Separate objects with the origin on the pivot. Values in **bold** are custom properties (glTF `extras`, FBX user properties).

| Object | Origin (pivot) | Motion |
|---|---|---|
| `MAKO_ChargingHandle` | (0, 0.030, 0.0745) | Translate +Y by **`stroke_m` 0.05**. Clean over the whole stroke, at every stock position |
| `MAKO_ForwardAssist` | (−0.0172, 0.0285, 0.0585) | Translate −Y by **`push_m` 0.004** (the cap stays in its bore) |
| `MAKO_DustCover` | Hinge rod (−0.016, −0.060, 0.041) | Swings open about Y (about −100°) |
| `MAKO_Trigger` | (0, −0.040, 0.012) | Rotates about X |
| `MAKO_BoltCatch` | (0.017, −0.071, 0.006) | Rotates about X |
| `MAKO_MagRelease` | (−0.0152, −0.072, 0.009) | Pushes +X |
| `MAKO_Selector` | Hub (0.0164, 0.006, 0.0125) | Rotates about X (lever forward = safe) |
| `MAKO_stock_standard` | Stock socket | Translate −Y by one of **`travel_positions_m`** [0, 0.0145, 0.029, 0.0435] (0 = delivered, extended). **`ch_stroke_max_m`** gives the clean CH pull per position: 0.05 at all four |

The other stocks are fixed (`ch_stroke_max_m` [0.05]). The build checks this every run: the charging handle is swept in
1 mm steps over its stroke against every base part and every stock position, every stock position against the base, and
every seated magazine against the base (`_work/ch_sweep.json`; any contact logs a WARN). r4 result: no contact anywhere.

## Mag check (DIRECTION_LOG item 8)
Each magazine is `MAKO_<mag>` with these children:
- `MAKO_<mag>_Round`: the top cartridge in the feed lips, **`min_rounds` 1**.
- `MAKO_<mag>_Stack`: an empty with **`capacity`**, **`visible_rounds`** and the **`rule`** text, parenting
  `MAKO_<mag>_Stack_NN`: one node per cartridge that can be seen through the window, each with **`min_rounds`** (and
  **`round_index`** on the box mags).

**Rule:** show a node while `rounds_in_mag >= min_rounds`, hide it otherwise. The stack is physical: rounds sit from the
feed lips down, so a box mag's window empties from the bottom of the window up as the mag runs dry.

| Mag | Window nodes | `min_rounds` range | What the window shows |
|---|---|---|---|
| mag_30 | 17 | 12 … 28 | Full window at 28+ rounds, about half at 20, empty at 11 or fewer |
| mag_45 | 30 | 13 … 42 | Same idea over the longer window |
| mag_drum60 | 8 (both faces per node) | 9 … 60 | One step per 7–8 rounds along the arc window; 00 is the end nearest the neck |

Renders `renders/fix_mag30_{30,20,10,3}rounds_window_plusX.png` show the states.

## Materials (all `M_MAKO_*`; one material per surface; no emissive)
| Material | Colour (linear) | Rough / metal | Detail map (baked into the base colour) |
|---|---|---|---|
| Graphite | (0.030, 0.033, 0.040) | 0.55 / 0.20 | worn_paint, mix 0.55, 5 repeats/m |
| Gunmetal | (0.11, 0.115, 0.12) | 0.35 / 0.85 | brushed_metal, mix 0.30, 8 repeats/m |
| Bone | (0.55, 0.52, 0.46) | 0.60 / 0 | worn_paint, mix 0.22, 6 repeats/m |
| BoneStipple (grip panels) | (0.55, 0.52, 0.46), same hue as Bone | 0.85 / 0 | polymer_stipple, levelled, mix 0.34, 6 repeats/m |
| Rubber, Dark, Brass | Palette values | 0.85 / 0, 0.70 / 0, 0.35 / 0.85 | none (flat colour) |

The drum's case heads carry a Gunmetal primer disc (r 2.2 mm) on the Brass head.

**glTF note (this matters for the engine):** `bc.material` multiplies the detail texture over the colour with a shader Mix
node. Blender's glTF exporter drops that node, so it writes only the raw grey texture and loses the colour. The MAKO avoids
this. `mako_lib.gl_material` bakes *colour × lerp(1, texture, mix)* into a 512² sRGB PNG and wires it straight into Base
Color, so the GLB's `baseColorTexture` alone is the final albedo. Repeats are baked into the UVs (constant texel density per
material), so no `KHR_texture_transform` is needed. Materials are single-sided (closed meshes).

## Hard-surface finish (r4)
Every hard edge gets a real chamfer from a Bevel modifier (1 segment on the receiver, rails and small parts; 2 on the
stocks, drum, butt pads, cheek comb), with hardened normals and angle-based sharp edges. How it works, in
`mako_lib.finish`:
1. **Micro edges first.** Before the bevel, edges under 50 µm (boolean slivers; nothing modelled is under 0.4 mm) are
   collapsed on the plain boolean result, while the mesh has no custom normals yet.
2. **Per-edge offsets.** Blender's Clamp Overlap is *global*: its overlap test runs on every edge and the worst one scales
   every bevel of the modifier. Until r3 this squashed most of the gun: measured effective chamfers (p90) were Upper
   0.018 mm (of 1.6), Lower 0.036 (of 1.5), mags 0.057 (of 2.0), stock_light 0.036 (of 2.2), dust cover 0.002, forward
   assist 0.010, charging handle 0.074, handguard 0.17. The look was crisp only because of hardened normals.
   `local_bevel_offsets` now runs the same test per edge (collapse of an edge between two bevelled neighbours, a bevel
   sliding along an unbevelled neighbour, two bevelled edges closing across a thin strip of one face) and scales only the
   offending offsets, written as bevel weights. Clamp Overlap stays on as a safety net and no longer finds anything.
   Measured now (p90): Upper 1.58, Lower 0.83, mag_30 1.0, mag_45 0.83, drum 1.72, stock_standard 1.32,
   stock_precision 0.90, stock_light 0.66, handguard 0.52, charging handle 0.80, dust cover 0.50, forward assist 0.60 mm.
   Edges whose safe offset is under 6 % of the width stay sharp (no micro strips).
3. **Spike / fold guard** (`fix_bevel_spikes`). After the bevel, every evaluated vertex must lie on the original surface
   (within 0.35 × width), every triangle centroid within 0.8 × width of it, and no triangle may face more than 100° away
   from the surface under it. Around any offender the bevel weights are halved (then zeroed). This caught a fold across
   the trigger-guard opening, a torn tube-channel rim on stock_standard, a slash on mag_45 and folds under
   stock_precision during development; the delivered build is clean in every `fix2_bevel_*` clay render.
4. **Normal-preserving cleanup** (`bake_clean`). After the modifiers are applied, the final corner normals are read,
   carried through every topology edit in loop attributes, and written back with `normals_split_custom_set`, so no
   shading can "melt" any more. The edits: collapse edges under 20 µm, triangulate n-gons whose tessellation has a
   zero-area triangle (the handguard's slotted faces), drop T-junction slivers by inserting their middle vertex into the
   neighbour, rotate any remaining zero-area triangle into its coplanar neighbour, and replace any back-facing carried
   normal with its face normal. Result: **0 zero-area triangles** in every GLB (checked by `check_glb.py`), down from 363
   in the r3 base export.

## Triangle counts (evaluated, after modifiers)
| Group | Tris |
|---|---|
| Base | 17,798 |
| stock_standard / precision / light | 1,944 / 2,600 / 1,600 |
| mag_30 / mag_45 / mag_drum60 | 2,124 / 2,538 / 7,644 |
| **Default loadout** (base + stock_standard + mag_30) | **21,866** (target 10–22k, hard max 30k) |
| Heaviest loadout (base + precision + drum60) | 28,042 |

The largest objects are the handguard (5,956: 46 round-ended slots through a 2.8 mm wall), the drum body (4,292), the
lower (1,868), the top rail (1,692) and the grip (1,568). Per-object counts are in `tri_counts.json`.

## Renders
Presentation lighting uses the Standard view transform with a soft neutral studio. Main views: `mako_default_*` (right,
left, three_quarter, three_quarter_back, low, front, back, top, ortho right/left). Close-ups: `close_*`. Variants: `ongun_*`
and `part_*`. Review-fix verification: `fix_*` (r2 review items: clay shading checks, moving parts at rest and pulled,
collapsed stock, precision comb, mag-check states, drum windows, first-person angle) in `contact_sheet_review_fixes.png`,
and `fix2_*` (round 2: every major part in clay to show the real chamfers, the grip knuckle, the sling swivel, the mag
flare, the drum's primed case heads) in `contact_sheet_review_fixes_r2.png`.
`compare_v09.png` puts v09 next to a build render from the camera that best matches it: (0.72, −0.45, 0.52), 50 mm. Its
silhouette overlay is cropped to bounding boxes and reaches IoU 0.73 (optic masked out of the concept). The concept is
painted a bit chunkier: a bigger mag and grip. The rail and bore heights were kept, because other agents' attachments
depend on them. `compare_side_v04/v02.png` overlay the orthographic right view on the side concepts.

## Review fixes (round 2)
Fixes for the r2 review (`review/critique_latest.json`, scores 7/6/7/7/6 on the 09:01 exports). Two passes: r3 (13:16–
14:02, interrupted before NOTES were finished) and r4 (this pass, which also re-checked every r3 fix). "Verified in" lists
renders from the delivered r4 run.

| # | Severity | Issue | Fix | Verified in |
|---|---|---|---|---|
| 1 | Critical | Folder out of sync (script edited after the export; sockets.json, tri_counts.json, textures, NOTES and renders from different runs); `check_glb.py` ran with `check=False`; NOTES claimed it failed the build | One full run produces every file (stale renders moved to `_work/stale_renders_r2/` and `_work/stale_renders_r3/` first; the build deletes Blender's `.blend1` backup so nothing from an earlier run is left). `check_glb.py` exits 1 on any error and checks the engine extras and zero-area triangles; `build_mako.py` raises `SystemExit(1)` when it fails, so Blender run with `--python-exit-code 1` exits 1. NOTES rewritten (sockets, tri counts, Stack_NN nodes and extras, stock travel) | `_work/r4/final_build.log`: `check_glb.py OK`, sockets identical in all GLBs and `sockets.json` |
| 2 | Major | Charging handle sunk into the castle nut and tube and colliding over its whole pull, into stock_standard at full stroke; FA cap poking into the tube and nut | CH rides at z ≥ 0.0702 (wing top 0.0792, under the rail top), shaft long enough to stay in the upper's channel; `stroke_m` 0.05. FA cap in its own bore, y 0.013–0.0285, ends before the tube. The build sweeps the CH in 1 mm steps against everything | `fix_rear_rest_minusX`, `fix_rear_pulled_minusX`, `fix_motion_ch_pulled_dc_open`, `fix_clay_rear_minusX`; sweep: no contact |
| 3 | Major | `bake_clean` edited topology after the hardened-normal bevel and "melted" the lower, magwell, guard, upper flank, cheek and FA cap | r3 moved the cleanup before the bevel. r4 found two more problems behind it: the zero-area faces left after the bevel were mostly the debris of bevels that Blender's global clamp had squashed to microns, and 363 zero-area triangles still reached the base GLB. Now: micro-edge collapse before the bevel, per-edge bevel offsets, and a post-bevel cleanup that carries the exact corner normals through its edits (see "Hard-surface finish") | `fix_clay_receiver_3q/plusX/minusX`, `fix_clay_magwell_front_low`, `fix2_bevel_*` (crisp, real chamfers); `check_glb.py`: 0 zero-area triangles |
| 4 | Major | Mag check could only show all or nothing (one merged `_Stack` mesh) | One node per visible cartridge with `min_rounds` / `round_index`, under a `_Stack` empty with `capacity` / `visible_rounds` / `rule`; exported as glTF extras and FBX user properties (see "Mag check") | `fix_mag30_{30,20,10,3}rounds_window_plusX`; `check_glb.py` reads the extras back |
| 5 | Major | NOTES told the engine to slide stock_standard 0.083 m (buries it 31.5 mm in the nut); a collapsed stock sat in the CH's path | `travel_positions_m` stored on the stock. A second limit the review missed: past 0.044 the tube end runs into the stock's blind channel (the review's 0.0495 pushed it 5 mm through the stock's rear wall), so the channel runs to y 0.2595 and the travel is 0 / 0.0145 / 0.029 / 0.0435. The front 48 mm of the stock top were lowered to z 0.0694 (the review's option b), so the full 0.05 CH pull is clean at every position and the engine needs no clamp | `fix_stock_collapsed_ch_clamped_minusX` (fully collapsed, CH fully pulled), `fix_stock_collapsed_right`; sweep: no contact |
| 6 | Major | Player-facing (+X) receiver plainer than v09 | +X panel-line frame on the upper, 2 mm raised shoulder pads at the front of both flanks, a swept upper/lower parting line (r 0.012) into the tube tower, pin bosses, a 13.6 × 23 mm bolt-catch paddle with grip ribs and a lever 1.5 mm proud, magwell lip 2.8 mm per side and 4 mm forward (a lip, not a bucket), handguard 8 mm deeper, mag window 8.8 mm. r4: real chamfers on every receiver edge now catch the light (they were 0.01–0.04 mm wide before), and the visible magazine flares to 0.0735 (was 0.070) | `fix_receiver_plusX`, `fix_receiver_v09`, `fix_magwell_front_low`, `close_receiver_*`, `fix2_mag_flare_plusX`, `compare_v09` (IoU 0.69 → 0.73) |
| 7 | Major | Precision cheek riser looked like a floating slab (gap, hidden posts) | Fixed comb seated on the stock (its base sinks 1.5 mm into the stock), framed by a 0.6 mm panel-line groove, 3 mm narrower per side than the stock top. No posts, no gap | `fix_precision_cheek`, `fix_precision_cheek_rear`, `fix_precision_side`, `fix2_bevel_stock_precision_3q` |
| 8 | Minor | Drum: hub + symmetric window read as a smiley; −X face showed only bullet tips; 28-step outline faceted; 10-step case heads read as octagons; spikes at the window cap joins | Window on the rear-lower arc, case heads on both faces, 40-step drum. r4: case heads 14 steps with a Gunmetal primer disc (they read as cartridges, not brass coins); window end caps 8 steps (22.5°) instead of 30° steps, which sat right on the 30° bevel limit and got stray bevels: no more spikes | `fix_drum_plusX/minusX`, `fix2_drum_window_minusX` |
| 9 | Minor | "Rounded" handguard slots were pointed hexagons; QD cup 10 segments | r3 had only gone to 4-segment caps (octagons up close, to save tris). r4: **8-segment caps** as the review asked; 22.5° steps stay under the bevel and sharp-edge limits, so the ends shade round. The tris came back from the cleanup in #3. QD cup 16 segments | `fix_handguard_slots_plusX/3q`, `fix2_bevel_Handguard_3q` |
| 10 | Minor | Grip stipple read as a cool-grey sticker; grip was a straight raked paddle without v09's finger swell, beavertail or flared base | Bone-hue stipple (tex_mix 0.34, levelled); beavertail, palm swell, base flare. r4: one A2-style finger knuckle on the front strap at z −0.045 (~3.5 mm proud of the front line, shallow valleys above and below), finer loft over the knuckle and the beavertail (it shaded lumpy), the beavertail's top no longer pokes out behind the lower, and the stipple panel's ends sit between loft rings (they left zero-area triangles) | `fix2_grip_plusX_ortho`, `fix2_grip_v09`, `close_receiver_*` |
| 11 | Minor | Castle nut: chrome glints in the hip view, pinched highlights on the lugs | Graphite, planar radial quads, sharp lug edges; r4: per-edge 0.5 mm chamfers like the other parts | `fix_fp_hip`, `fix_clay_rear_minusX` |
| 12 | Minor | Zero-area faces (DustCover 48, cheek 24, …) | See #3: 0 in every mesh and every GLB (the review's own test: faces under 1e-10 m²) | build log (`micro / zero-area faces … -> 0`), `check_glb.py` |
| 13 | Minor | stock_standard QD sling loop was a thin wire ring that vanished at gameplay distance | Chunky swivel: 4 mm ring section, 4.4 mm thick, rounded-square ring (21 × 21 mm) on a 5 mm swivel post | `fix2_sling_3q`, `close_stock_right` |

### Found while verifying
- r3, **handguard open at the back:** it is wider than the upper, so from the first-person angle its hollow inside (and
  daylight through the slots) showed at the receiver joint. Added a 4.5 mm rear bulkhead. `fix_fp_hip`, `fix_fp_reload`.
- r3, **key-slot floor = stock bottom:** the tube-key slot's floor (z 0.030) lay exactly on the bottom of stock_light's
  collar and of stock_standard's front, leaving a paper-thin skin and a bad face fill that bridged the slot on the light
  stock's front face. The slot floor moved up 0.5 mm and both bottoms down 2.5–3 mm. `fix_stock_light_front`,
  `fix_stock_standard_front`.
- r3, **clearance checks** use Blender's real triangulation (a naive fan over a ring-shaped n-gon gave false hits) and cover
  every stock position against the base. r4 adds every seated magazine against the base (the flared mags clear the lip).
- r4, **the bevels were not there:** see "Hard-surface finish". The upper moved to one-segment 1.6 mm chamfers like the
  lower (the two-segment round had never actually existed), which keeps the default loadout under 22k with the rounder slots.
- r4, **magazine flare:** the box mags flare to 0.0735 below the well over 30 mm with 8 outline samples (5 left a visible
  kink); the part inside the well keeps the 0.064 that fits the cavity, and the build checks the seated mags against the lower.

## Known limitations
- No LODs. No collision mesh (the engine can use boxes).
- The mag window shows cartridges only; there is no follower plate, so a nearly empty box mag shows an empty dark window.
- Side rails are short (5 slots), so a laser or light fits at one position only.
- The handguard is wider than the upper (free-float style). From straight above, the step at y −0.168 is visible by design.
- `stock_precision`'s cheek comb is fixed (no adjustment animation).
- A few tight spots (where the spike guard zeroed the weights, mostly around boolean unions such as the lower's guard
  roots and the charging-handle latch ridges) keep sharp edges instead of chamfers.
- The concept is still a little chunkier in the grip than the build (silhouette IoU 0.73).
- The renders exclude the optic (`optic_holo` is built by the attachments agent).
