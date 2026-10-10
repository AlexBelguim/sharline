# VK-50 "WARDEN": independent review, round 2

**Reviewed:** the build exported at 09:37, 2026-10-07.

**What was checked:** only the exported `.glb` and `.fbx` files and the `.blend`, opened read-only. Nothing in the asset was modified.

**Older material:** the files directly in `review/` (outside `r2/`) are the first review. They predate the review-fix pass, and the builder answered them in NOTES.md "Review fixes". This round lives entirely in `review/r2/`.

**Verdict: accept with fixes.** The asset is a solid, game-ready prototype:
- sockets are exact;
- the rail standard is met;
- the export is clean glTF;
- there is no emissive and no ammo counter;
- handedness is correct;
- the bolt cycle and mag check are verified;
- proportions match `profile_sketch.png`.

Three visible issues should be fixed before it is signed off:
1. a failed boolean on the +X handguard top vents;
2. a see-through upper slot row that reads as light strips;
3. an unconvincing cantilevered cheek riser.

## Scores (1–10)
| Category | Score |
|---|---|
| Silhouette | 7 |
| Style consistency | 8 |
| Craftsmanship | 6.5 |
| Fidelity to the brief and the user's decisions | 8 |
| Game readiness | 8 |

## What passes (all measured on the re-imported exports)

**Sockets** (`check_report.json` → `sockets`)
- All 8 `WARDEN_SOCKET_*` empties are within 0.000 mm of the spec, have zero rotation and are parented to `WARDEN_Root`, which sits at (0,0,0).
- `_Side_R` is at −X and `_Side_L` at +X, following the modular spec.

**Rails**
- Top rail: top surface z 0.1375, top width 0.021 (x ±0.0105), height 0.0095 above the 0.128 base, cross-slot pitch 0.010. It runs from y +0.062 to −0.690.
- Bottom rail: bottom face at z 0.0205, from y −0.650 to −0.540.
- Side rails: outer faces at ±0.0455, 0.060 long, 0.021 tall, centred on y −0.645.

**Attachments**
- All of these seat with no gun-side conflicts: `ATT_optic_sniper`, `ATT_optic_thermal`, `ATT_bipod`, and `ATT_laser_R/L` and `ATT_flashlight_R/L` on both side rails. Their ADS sits 0.0405 and 0.052 m above the rail top, inside the 0.04–0.075 band.
- The clamps overlap the rail by 0.85 mm. That comes from the attachment side and is acceptable.

**Moving parts** (pivots, extras and `warden_anim.json` all consistent)
- Bolt cycle: lift 0→60° in 5° steps, then travel 0→0.13 m in 5 mm steps. No contact with the gun or stock, and none with either optic mounted (39 mm minimum clearance).
- Trigger pulled to +12°: clean.
- Safety at FIRE: 0.05 mm graze with the receiver, which is negligible.
- Riser raised 30 mm and monopod extended 45 mm: clean.
- Folding stock swept 0→−180°: clean against the base and mag_8.
- Mag insertion path, 0–120 mm straight up: no collision. The mag sits 1.0 mm from the magwell.

**Topology and export**
- The source `.blend` meshes are all closed, consistently wound, and have no inward shells (`topology_report.json`, `blend:*`).
- glTF: every primitive has a material, UVs and normals; textures are embedded at 512 px; there are no extensions and no emissive; every baseColorFactor is the palette value.
- The FBX files load at scale 1 with correct names, materials and custom properties. As documented, they carry no textures.

**Budget**
- Default assembly is 20,596 tris, inside the 12k–25k range. The visible mag below the well is 0.100 m (mag_8: 0.150 m).

**Re-runnability**
- A copy of `build_warden.py` with OUT redirected to a scratch folder rebuilt everything from nothing in about 5 s.

**Readability**
- 64 px read (`renders/r2_silhouette_reads.png`): the brake, slotted handguard, mag, stock window and monopod all survive. With the showcase loadout it reads as a heavy sniper from the side, three-quarter and front.
- Mag check (`r2_magcheck_2left_tilted.png` / `_full_tilted.png`): "2 left" (two rounds plus the raised follower) and "full" are easy to tell apart.

## Issues

### MAJOR 1: two of the +X handguard top vents are not cut through, leaving a hairline crack and open edges

**Evidence**
- `renders/r2_cu_topvents_left_failed.png`: shallow ghost pockets with smeared shading, and a crack line beside the rail.
- `renders/r2_cu_handguard_top_ortho.png`: on the −X row all 3 vents are through; on the +X row only 1 of 3 is.
- Compare `r2_cu_topvents_right_ok.png`.

**Measurements**
- After a 1e-6 positional weld, the exported `WARDEN_Handguard` has 4 boundary and 6 non-manifold edges at (0.0175, −0.4375, 0.128) and (0.0175, −0.5025, 0.128), plus 7 zero-area triangles.
- `topology_report.json` → `glb:warden_default.glb:WARDEN_Handguard`.
- Reproduced in a from-scratch rebuild, so this is a deterministic script bug.
- NOTES.md says "all meshes are closed". That is not true for the shipped handguard.

**Cause:** `build_warden.py`, around line 616:
`cut(hg, prism("_st", stadium(sx * 0.0175, yc, 0.007, 0.040, 2), "Z", 0.118, 0.140))`
The EXACT boolean only partially applies on +X for yc −0.470 and −0.535.

**Fix**
1. Join the 6 vent cutters into one object and cut once. Do it before the side-slot cuts, or nudge the cutters off coincident planes (x ±0.0178, z 0.112–0.146).
2. After the cut, ray-cast down through each vent centre from z 0.14 and fail the build if the ray hits handguard geometry within the wall.
3. Add an export gate: re-import the glb, weld at 1e-6, and assert boundary == 0 and zero-area == 0 for every mesh.

### MAJOR 2: the upper handguard slot row is see-through and reads as four light strips on a no-emissive gun

**Evidence**
- `renders/r2_cu_handguard_side_ortho_left.png`: upper row light, lower row dark.
- `r2_side_left_skybg.png` vs `r2_side_left_darkbg.png`.
- The builder's own `renders/warden_right.png` and `warden_compare.png` show white pills.
- In the 64 px silhouette the row punches holes.

**Measurement:** the upper slot row spans z 0.0962–0.1107, but the barrel top is at z 0.098 (r 0.023 at z 0.075). The row therefore looks straight through the gun.

**Why it matters**
- `concept_main.png` shows both rows dark.
- On the snowy-fjord range ("The Yard"), the four bright pills become the most eye-catching detail on the handguard, and they read like glow strips (DIRECTION_LOG item 8 and STYLE_GUIDE "no glow strips").

**Fix (any one):**
- Add a dark inner heat-shield liner, a graphite plate at x ±0.0305 covering z 0.09–0.115 over y −0.60 to −0.34, so the upper row reads as dark recesses.
- Lower the upper row so the barrel occludes it (centre z ≈ 0.088 → 0.081–0.095), keeping the 2-row rhythm.
- Make the upper row 3 mm blind pockets.

### MAJOR 3: the cheek riser is a long cantilever on two posts bunched at its rear, so the stock reads as a "Γ" hook rather than the concept's comb and floating riser

**Evidence**
- `renders/r2_cu_stock_riser_right.png`, `r2_worst_rear_high_left.png`.
- Builder `renders/warden_stock_standard_right.png`.
- The overlay in `renders/warden_compare.png`: the concept's stock top line is flat and continuous, while the build has a deep notch between the receiver and the riser.

**Measurements** (on the glb, `r2_riser_probe.py`)
- Riser pad: y 0.162–0.290 (128 mm long), z 0.124–0.146.
- Posts: Ø 9.6 mm, centred at y 0.263 and 0.281, only 18 mm apart.
- Overhang: about 96 mm of the pad is unsupported ahead of the front post.
- The BRIEF had the posts spread at y 0.180 and 0.250 under the riser.

**Why it happened:** the low top beam (z 0.045) and the rear-only posts are the builder's answer to the 0.13 m bolt travel. That reasoning is sound (the bolt path is verified clear), but the result looks structurally implausible and weakens must-read #4, "cheek riser on posts".

**Fix:** keep the bolt path clear and add support outboard on the +X (cheek) side.
- Add a front post or angled web at x 0.026–0.034, y ≈ 0.17–0.19, running from the beam (z 0.045) to the riser underside (0.124). It clears the shroud (|x| < 0.024) and the −X handle path.
- Then spread the rear posts to about 40 mm.
- In the concept's left-side view this restores "riser on two posts".
- Alternatively, give the riser a tapered wedge underside so it reads as one solid cantilever.

### MINOR 4: from the player's view, the shroud end cap and the bolt knob read as two identical balls

**Evidence:** `renders/r2_loadout_fpv_hip.png`, `r2_worst_rear_low_right.png`, `r2_cu_receiver_rear_top.png`.

**Detail**
- Both are Ø ≈ 48 mm, both gunmetal, and both rounded.
- The knob is a dense smooth UV sphere: 370 vertices, inside a 1,252-tri bolt against the BRIEF's 0.8k.
- BRIEF 4.1 asks for a faceted sphere (8×6) or a hex knob, and a shroud with a 0.004 rear chamfer.

**Fix:** make the shroud rear a flat, chamfered cylinder end with a small cocking-indicator stub, and make the knob faceted (8 segments × 6 rings, flat-shaded) or hex. That way only one ball reads in first person, and about 350 tris are saved.

### MINOR 5: the build is not deterministic

**Evidence**
- Two from-scratch rebuilds (OUT redirected to a scratch folder) gave `WARDEN_Receiver` 1,824 tris and 1,836 tris; the shipped file has 1,836. Base total: 13,928 vs 13,940.
- Script: `r2_determinism.py`.

**Likely cause:** `seal()` passes `list({v for e in nm for v in e.verts})`, a set of BMVerts with id-based ordering, to `remove_doubles`. Other set iteration may contribute too.

**Fix:** sort vertex lists by index before every bmesh op, and add a CI-style check that two consecutive builds produce identical per-mesh tri counts.

### MINOR 6: sliver and zero-area triangles in the glb exports

**Counts** (after a 1e-6 weld, `topology_report.json`): Barrel 5, Handguard 7, StockStandard 9, StockFolding_Arm 20 zero-area triangles. The receiver has 512 faces under 0.01 mm².

**Topology:** the receiver and handguard flats are long boolean triangle fans (`r2_wire_cu_receiver_right.png`, `r2_wire_cu_handguard_left.png`). Shading holds up because the big faces are flagged sharp, but the slivers are fragile for future normal maps, LODs and tangents.

**Fix:** triangulate (beauty) in Blender before export, run `dissolve_degenerate` (1e-6) after triangulating, and keep the re-import gate from Major 1.

### MINOR 7: git case trap on the part files

**Evidence:** `git ls-files` tracks `warden_stock_standard.glb`, `warden_mag_5.glb`, and so on (lowercase), while the disk and NOTES use `WARDEN_*`. `core.ignorecase=true`.

**Risk:** a plain `git add` records the new content under the lowercase paths. Linux checkouts (cloud `game/` sessions) will then not find `WARDEN_stock_standard.glb`. The builder documented this, but it is still unresolved.

**Fix:** before the commit, run `git mv -f warden_<part>.<ext> WARDEN_<part>.<ext>` for all 8 part files. Then verify with `git ls-files assets/weapons/vk50_warden | grep -i stock`.

### MINOR 8: the triangle budget for the full showcase set is over the BRIEF target

**Numbers**
- The gun alone is 20.6k (in range).
- The BRIEF's 25k target covers base + stock + mag_5 + optic_sniper + bipod together. That is 29.1k with the other agents' parts (35k is the hard max).

**Over the BRIEF 4.7 split** (whole gun 12.7k planned)
| Part | Build | BRIEF |
|---|---|---|
| stock_standard | 4.5k | 2.5k |
| mag_5 | 2.2k | 0.7k |
| brake + collar | 2.2k | 0.8k |
| handguard | 3.3k | 2.0k |
| chassis | 1.5k | 0.6k |
| bolt | 1.25k | 0.8k |

The mag_5 rounds alone are about 960 tris, and 3 of them sit hidden inside the well when the mag is seated.

**Fix:** aim for 17k or less for the gun:
- faceted knob;
- 6–8-sided simplified rounds 2–5, or merge rounds hidden in the well;
- fewer brake top-vent segments;
- trim hidden overlaps (barrel 39 mm into the receiver, collar 16 mm over the barrel).

### MINOR 9: the mag window shows daylight under the follower even on a full, seated mag

**Evidence:** `renders/r2_side_left_skybg.png` and builder `warden_right.png`. Below the magwell lip, the window shows round 5, the follower, and then about 13 mm of background. It reads as a hole in the mag foot.

**Fix:** end the window slot at the follower's full-mag bottom (z ≈ −0.114 in gun coordinates), or add a static dark spring plate only below the full-mag follower position. That plate never crosses a cartridge, so the builder's septum objection does not apply.

### MINOR 10: the receiver's left (+X) side is a large plain slab

**Evidence:** `renders/warden_cu_receiver_left.png`, `r2_clay_cu_receiver_left.png`.

**Detail:** the counter was removed per the user's decision. The concept's other focal detail on this side, a raised bolt housing with a gunmetal bolt raceway along the top-rear, is not modelled. The hero view (+X, the concept's side) therefore has no focal point between the handguard and the stock.

**Fix:** add a stepped raised bolt-housing band along the receiver's top-rear with a narrow gunmetal raceway strip, or a recessed maker plate with two take-down pins. No emissive.

## Documentation note

The builder's hand-off summary quotes the pre-fix numbers: base 15,124 and default 22,486. NOTES.md and `_wip/tris.json` (13,940 / 20,596) are correct and match the exports.

## Files in this folder

| File | What it does |
|---|---|
| `r2_glb_json.py` → `glb_json_report.txt` | raw glTF JSON check |
| `r2_check.py` → `check_report.json` | sockets, rails, stations, intersections, z-fight, bolt, trigger, safety, riser and monopod sweeps, attachments, fold, mag insertion |
| `r2_topology.py` → `topology_report.json` | welded topology check, glb and blend |
| `r2_fbx_check.py` | FBX load check |
| `r2_probe.py`, `r2_riser_probe.py` | targeted measurements |
| `r2_determinism.py` | rebuild comparison |
| `r2_render.py`, `r2_render2.py`, `r2_render3.py` | review renders, all made from the exported glb |
| `r2_sheets.py` | builds `renders/r2_review_contact_sheet.png` and `renders/r2_silhouette_reads.png` |
