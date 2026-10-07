# HALO shield kit: notes and engine-integration guide

Armor is a stylized tech halo floating above the head (`art/HALO_SHIELD_SPEC.md`, DIRECTION_LOG items 5-7 and 9).
This folder is the complete kit: 4 core silhouettes split into 4 zone arcs each, Medium/Heavy weight bands,
a far LOD set, tier pips, power cells, hit shards, loot cores, VFX sprites, an example armor catalog,
showcase renders and QA scripts.

Rebuild everything from scratch (about 15 s without renders, about 5 min with all renders; absolute paths,
the project path contains a space):

```
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup ^
    -P "F:/git/val etf/assets/shields/build_halo.py" -- [--renders all|none|<list>] [--iter vNN] [--no-export]
<list> = grid,lineup,sil,eye,coverage,underside,pickups,parts,lod,turn,char
```

QA (run after a build; both must report 0 problems):

```
python "F:/git/val etf/assets/shields/qa/qa_glb.py"
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P "F:/git/val etf/assets/shields/qa/qa_blender.py"
```

| File | What |
|---|---|
| `build_halo.py` | Entry point: sprites, kit, exports, `halo_kit.blend`, catalog, renders |
| `halo_data.py` | Pure Python. Reads `game/assets/data/armor.ron` (weight bands, presets, capacities...), cross-checks it against `design/systems/data/armors.slice.json` and **stops the build if they disagree**. Art-side weight visuals (scale, orbit) live here |
| `halo_lib.py` | Shapes (circle / hexagon sweeps), mesh builder with strip UVs and per-edge materials, glyphs, materials |
| `halo_parts.py` | Part builders: arcs per core, weight bands, far LOD, pip, power cell, shards, pickup cores |
| `halo_render.py` | Showcase renders. `place_halo()` is the reference assembly for the engine |
| `make_sprites.py` | Procedural VFX sprites + the broken-arc crack map (system Python + PIL + numpy) |
| `make_catalog.py` | Writes `armor_catalog.example.json` from the game data (no copied numbers) |
| `qa/qa_glb.py`, `qa/qa_blender.py` | Checks on the exported files: names, materials, topology, pip seating, band hang, cell clearance and cell-count visibility. Reports in `qa/*.json` |
| `qa/qa_review_render.py`, `qa/qa_compose.py` | The reviewer's in-play renders (`review/review_render.py`, `review/compose.py`) re-run on the fixed kit with its current parameters: `qa/renders/Q01_distance_read_10_25_50m.png`, `Q01b_distance_far_lod.png`, `Q06_underside_and_hud.png`, `Q07_ingame_kestrel.png` (compare with `review/renders/R01/R06/R07`) |
| `halo_kit.blend / .glb / .fbx` | Every kit object at the halo origin, plus empties and material swatches |
| `export/HALO_<Core>.glb/.fbx` | Per core: `HALO_<Core>_Arc_{Head,Arms,Torso,Legs}`, `HALO_<Core>_Band_{Medium,Heavy}`, empties `HALO_<Core>_PIP_1..4`, far LOD `HALO_<Core>_Far_Glass_<Zone>` + `HALO_<Core>_Far_Frame_{Light,Medium,Heavy}` |
| `export/HALO_Common.glb/.fbx` | `HALO_TierPip`, shared empties `HALO_PIP_1..4` (= the Bulwark seat), `HALO_PowerCell`, `HALO_Shard_A/B/C` |
| `export/HALO_Pickups.glb/.fbx` | Loot cores `HALO_Core_{Bulwark,Mender,Volt,Phase}` |
| `export/HALO_Materials.glb` | One swatch per material (`HALO_Swatch_*`): the glTF material library, incl. the embedded crack map |
| `sprites/*.png` | `hex_hit_flash`, `crack_overlay`, `shard_sprite` (512x512 white/greyscale + alpha), `crack_tile` (512x512 seamless greyscale RGB, emissive map of the broken material). `_preview.png` is a check sheet |
| `armor_catalog.example.json` | JSON Schema, rules and 9 example armors (8 are the game's own presets) |
| `renders/` | Showcase renders (list below). `renders/_iterations/vNN/` keeps the look-development history |
| `review/` | The independent review (2026-10-07) and its evidence; see "Review fixes" |

## Axes and attachment
- Blender: metres, Z up, the wearer faces **−Y**. glTF (what Bevy loads): Y up, the wearer faces **+Z**,
  the same convention as the character exports, so halo and character agree without extra rotation.
- Arc zones, seen from above: **Head = front** (Blender −Y / glTF +Z), **Arms = +X** (the wearer's left),
  **Torso = back** (Blender +Y / glTF −Z), **Legs = −X** (the wearer's right).
- Every arc, band and far-LOD mesh has its **origin at the halo centre**, so all parts of one halo share one transform.
- Attach the halo root at the character's `<P>_SOCKET_Halo` (0.22 m above the top of the head, over the skull).
  Copy the socket's **position** every frame and the body's **yaw** only. No head-bone pitch or roll, so the
  halo stays level and the Head arc always points where the body faces (the arcs map onto body zones).

## Shapes, sizes and triangle budget
Every core has a silhouette that reads **edge-on** (players see each other's halos 1-10° from below), not only
from above:

| Core | Ring (from above) | Edge-on signature | Ring height | Outer Ø Light / Medium / Heavy (at scale) |
|---|---|---|---|---|
| Bulwark | thick faceted hexagon, 0.150 m apothem | tall 24 mm glass wall, 6 corner posts 8.5 mm above the ring (small edge lights on top) | 31 mm (40 mm with posts) | 0.34 / 0.43 / 0.60 m |
| Mender | twin thin rings (r 0.143 / 0.177) | the outer ring sits 14 mm lower: two stacked lines, stepped ends; zone bridges on top of both rings | 28 mm | 0.31 / 0.40 / 0.55 m |
| Volt | crown ring, 8 sawtooth teeth | teeth 30 mm above the ring | 22 mm (56 mm with teeth) | 0.30 / 0.39 / 0.53 m |
| Phase | smooth round ring, 30° gap at the back | an electrode fork: two glass prongs rise 28 mm either side of the gap and lean into it | 23 mm (53 mm with prongs) | 0.29 / 0.38 / 0.52 m |

| Core | Tris 4 arcs | + Medium band | + Heavy band | Far LOD: 4 glass arcs + frame L / M / H |
|---|---|---|---|---|
| Bulwark | 2796 | 544 | 1380 | 208 + 204 / 324 / 348 |
| Mender | 3608 | 1024 | 2116 | 352 + 264 / 624 / 696 |
| Volt | 4356 | 1024 | 2116 | 368 + 252 / 612 / 684 |
| Phase | 3056 | 960 | 1938 | 308 + 248 / 596 / 668 |

Small parts: `HALO_TierPip` 8 tris (18 mm diamond facing −Y), `HALO_PowerCell` 488 tris (87 mm long),
shards 14-26 tris (~3 cm), pickups 612-1036 tris (8.5-11 cm, origin at the bottom centre, front −Y).
Worst case near: a Heavy Volt halo with 3 cells ≈ 7.9k tris; far LOD ≤ 1.05k tris + cells.

## Materials (linear RGB, all opaque and single-sided)
| Material | Use | Values |
|---|---|---|
| `M_HALO_Glass_T1..T4` | lit arc glass, pips, cells, band lip, shards, pickup windows | base = 0.12 × tier colour, emissive = tier colour, strength 2.4 (`KHR_materials_emissive_strength`), rough 0.25, clearcoat 0.4 |
| `M_HALO_Glass_Broken_T1..T4` | an arc whose pool is 0, until it regenerates | tier colour 50 % desaturated, emissive strength 1.0 × `crack_tile.png` (0.18 body, 1.0 fracture lines), base 0.10 × that colour, clearcoat 0.4 |
| `M_HALO_Glass_Off` | uncovered arc: dark smoked glass | base (0.02, 0.02, 0.025), rough 0.08, clearcoat 1.0, no emission. **Opaque** (no alpha sorting) |
| `M_HALO_Edge` | always-on frame light: thin lines on every arc and band | base (0.04, 0.045, 0.05), emissive (0.56, 0.66, 0.80) × 0.30 (cool steel, deliberately not a tier colour) |
| `M_HALO_Graphite` | arc frames, keels, clamps, bands, cell caps | (0.030, 0.033, 0.040), rough 0.55, metal 0.15 |
| `M_HALO_Gunmetal` | heavy-band bolts | (0.11, 0.115, 0.12), rough 0.35, metal 0.85 |
| `M_HALO_Bone` | pickup grip band | (0.55, 0.52, 0.46), rough 0.6 |

Tier colours: T1 white (0.85, 0.88, 0.92) · T2 blue (0.10, 0.45, 1.0) · T3 violet (0.55, 0.15, 1.0) ·
T4 gold (1.0, 0.62, 0.08). Only the broken material uses a texture; everything else is flat colour.
All meshes are closed outward-facing shells, so every material exports `doubleSided: false`.

UVs: arc and band glass is unwrapped as **straight strips** (U along the arc, V around the profile, 1 UV unit =
5 cm), so the tileable crack map runs cleanly along each arc. Every mesh has UVs.

### Primitive layout (what to swap)
Every mesh is one glTF node whose primitives are split per material. Find primitives by material name.
- Arcs `HALO_<Core>_Arc_<Zone>`: **primitive 0 = glass** (swap per arc), then graphite, then edge.
- Bands: graphite, gunmetal, **lip glass** (swap to the highest arc tier), edge.
- Far LOD: `HALO_<Core>_Far_Glass_<Zone>` is glass only (swap per arc); `HALO_<Core>_Far_Frame_<Weight>` is
  graphite + edge (+ lip glass for Medium/Heavy).
- Cell: glass (highest arc tier), graphite. Pip, shards: glass only. Pickups: window glass, graphite, bone.

## Assembling a halo in the engine
`halo_render.place_halo(core, arc_tiers, ...)` is the reference implementation. Per player:

1. **Weight class from the arc tiers**: protection score = sum of the 4 arc tiers, weight band from
   `armor.ron weight_bands` (Light 1-4, Medium 5-8, Heavy 9-16). Never store the weight separately.
2. **Root**: one transform at the socket, uniform scale by weight class (Light 0.85, Medium 1.0, Heavy 1.2).
3. **Arcs**: spawn the 4 `HALO_<core>_Arc_<zone>` meshes as children. Each glass primitive gets the material of
   **that arc's tier** (`M_HALO_Glass_T<tier>`); tier 0 (uncovered) gets `M_HALO_Glass_Off`; a broken arc gets
   `M_HALO_Glass_Broken_T<tier>`. The graphite and edge primitives never change.
4. **Weight band**: none for Light, `HALO_<core>_Band_Medium` or `_Band_Heavy` as a child of the same root;
   its lip glass gets the highest arc tier's material.
5. **Tier pips**: spawn `HALO_TierPip` at `HALO_<core>_PIP_1 .. HALO_<core>_PIP_<top>` (per-core empties in
   `HALO_<Core>.glb`, seated on that core's Head arc), where top = the **highest arc tier**. Never show unlit
   pip slots: the pip count is the tier. (`HALO_PIP_1..4` in `HALO_Common.glb` are the Bulwark seat, kept as a
   generic default; they float above the other cores.)
6. **Power cells**: 1 / 2 / 3 cells for Light / Medium / Heavy (see Orbiting cells), highest arc tier colour.

Bevy notes: the glTF asset exposes the meshes by name (`HALO_Volt_Arc_Head`, …) and the materials by name
(`M_HALO_Glass_T1`, …), so the halo can be built straight from the named meshes with the game's own
`StandardMaterial`s instead of spawning the whole scene. Node extras (`halo_core`, `halo_zone`, `halo_weight`,
`halo_lod`, `halo_pip_index`) are exported too (`GltfExtras` on the node entity) if scene spawning is preferred.

### States and brightness
Relative emission strengths used in the renders, which work well with bloom (threshold ≈ 1):
**idle 0.9 · lit 2.4 · flare 6.0** (≈ 1 : 2.7 : 6.7); edge lines stay at 0.30 in every state.
Scale the absolute values to the game's exposure and keep the ratios.

| State | Arcs | Pips | Cells | Notes |
|---|---|---|---|---|
| **Idle** (always, any range) | covered arcs at idle 0.9, uncovered `Glass_Off` + edge line | idle | 1.4 | Never invisible: weight class, tier colour and core silhouette must always read |
| **Hit** | covered arcs flare to 6.0 in ~0.05 s, ease back to idle over ~0.6 s; the struck arc stays brighter longest | flare | 6.0 | shards + hit flash, see below |
| **Arc broken** | after a 0.15 s white flash the arc switches to `M_HALO_Glass_Broken_T<tier>` | - | - | shard burst (2-3× hit count); Volt adds its shock ring |
| **Regenerating** | the refilling arc goes back to its tier material and ramps from 0.25 to idle over the refill | - | brief pulse | Mender: bright edge sweeping in from both arc ends |
| **Scanned** | everything at lit 2.4 for the scan duration | lit | lit | exact numbers are UI, not mesh |

### Orbiting cells
- Radius (halo-local, multiplied by the root scale): Light 0.215, Medium 0.245, Heavy 0.275.
- Height: **z = +0.058 (Blender) / y = +0.058 (glTF)** halo-local, i.e. above the ring top, so the cell count
  can't hide behind the ring. `qa/qa_blender.py`: the true count shows for 100 % of the orbit at −2° and −5°
  for every core and weight (it was 30-70 % with the old in-plane orbit).
- Period: Light 2.6 s, Medium 3.4 s, Heavy 4.6 s (heavier = slower, heavier orbit). Spread n cells evenly
  (360°/n). A ±3 mm vertical sine bob at 1.3× the orbit frequency keeps them alive.
- Orientation: the cell travels along its local **+X**, the orbit centre is on its local **+Y** (Blender).
  For a cell at orbit angle θ (counter-clockwise from +X, seen from above) use yaw = θ + 90°.
  In glTF terms: travel = +X, orbit centre = −Z of the cell. The trail fin is pre-bent for the Medium radius.
- Cell glass = the highest arc tier colour. The status effect may tint the trail particles (catalog
  `rules.status_vfx`).

### Far LOD (beyond ~20 m)
Swap the 4 arcs for `HALO_<core>_Far_Glass_<zone>` (same per-arc material swap) and the band for
`HALO_<core>_Far_Frame_<weight>` (Light has a frame too: its edge lines and core details). Keep the cells and
drop the pips. The far set keeps the core signature (posts, stacked rings, teeth, prongs), the band mass and
the edge outline; ticks, bolts, glyphs and plates are gone. Glass and frame are separate meshes because the
4 glass primitives must stay swappable per arc (one merged glTF mesh could not tell its glass primitives apart).
At 25-50 m the ring is only 0.3-0.6 px tall at 1080p; if halos must stay visible that far, scale the far LOD
root's **local vertical axis** by `max(1, distance / 20 m)` so the ring keeps about 1 px of height
(`qa/renders/Q01b_distance_far_lod.png`: at 50 m the stretched far LOD keeps the tier colour and the
Light / Medium / Heavy size read, where the unstretched kit fades to grey).

### Hit and break VFX
- **Shards** (`HALO_Shard_A/B/C`, origin at the centroid, ~3 cm): spawn 6-12 per hit at the impact point on
  the struck arc, 25-35 on a break. Random rotation, 1.5-3 m/s outward from the impact plus a little upward
  bias, ~30 % gravity, spin, lifetime 0.35-0.7 s, scale to 0 at the end. Material = the struck arc's tier glass
  at flare strength, fading. Shards always use the arc's tier colour (that is how players read tier on hit).
- **`hex_hit_flash.png`**: camera-facing quad at the impact, ~0.15 m (× halo scale), 0.12 s, scale 0.8 → 1.2,
  tinted by the tier colour. Additive (RGB × A) or alpha-blended: both work, the RGB is white/grey.
- **`crack_overlay.png`**: quad on the struck arc's outer face, ~0.06 m, tinted white-ish (0.95, 0.9, 1.0) or
  the tier colour; opacity = 1 − arc_pool / arc_capacity, so remaining shield reads as cracks. At 0 the arc
  itself switches to the broken material (its crack map is `crack_tile.png`).
- **`shard_sprite.png`**: cheap billboard alternative to the mesh shards (far LOD or many hits at once).

### Readability (DIRECTION_LOG 7): what to check after any change
| Render | Shows |
|---|---|
| `02_weight_lineup(_silhouette).png` | Light / Medium / Heavy from 20° above: full coverage T1/T2/T3 and the game presets (`arm_phase_runner`, `arm_volt_line`, `arm_bulwark_assault`), colour + pure silhouette |
| `02b_weight_silhouette_all_cores.png` | the weight read without colour for all 4 cores |
| `02c_weight_eyelevel_idle(_day).png`, `02c_weight_eyelevel_silhouette.png` | the in-play angle (eye 5° below), idle, dark scene and daylight, uniform + presets |
| `02d_core_read_{2,8}deg(_silhouette).png`, `02d_core_read_side_2deg_silhouette.png` | **naming the core edge-on**: all cores × weights with game-legal coverage at −2° (~10 m) and −8° (~2.5 m), front and side |
| `03c_underside_-35deg.png` | from below (jetpacks, ziplines, lower ground): tier colour on the underside glass, inner walls and band lips |

### Own halo in the HUD
Render the same meshes with an orthographic camera from ~60° above into a small render target (or a separate
camera layer), front arc toward the bottom of the widget, using the same per-arc materials and states.

## Loot cores (pickups)
`HALO_Core_<Core>`: hand-sized devices (8.5-11 cm) whose top echoes the ring silhouette (hex crown, stepped
twin rings, toothed crown, gapped ring with a small prong fork) with a glowing glass window (primitive 0,
`M_HALO_Glass_T<tier>`, render strength 3.0). Origin at the bottom centre, front −Y (glTF +Z). Graphite body
with a bone grip band.

## Catalog
`armor_catalog.example.json` (generated by `make_catalog.py`): schema + rules + 9 examples covering all cores,
tiers 1-4 and Light/Medium/Heavy; 8 of them are the game's own presets (`source` field). Every gameplay
number (capacity, zone share, regen, weight bands and effects, cells, loadout tier caps, presets) is parsed
from `game/assets/data/armor.ron` at build time and cross-checked against the design JSON; a mismatch stops
the build (`HALO_ALLOW_DATA_DRIFT=1` turns it into a warning). Food/energy drain multipliers are art-side
placeholders. The visual block (`weight_class_visuals`) carries halo scale, band mesh, cell count, orbit
radius, **orbit height** and period.

## Showcase renders
`01_cores_tiers_grid` (4 cores × T1-T4), `02*` (weight class, see above), `03_coverage_head_torso`,
`03b_per_arc_tiers` (game presets + the lit / broken / uncovered arc states), `03c_underside_-35deg`,
`04_character_{idle,hit,idle_vs_hit,fullbody_idle}` (Kestrel with ONE game preset, `arm_bulwark_assault`
H3 T3 A3 L0 = 9 → Heavy, in both states), `05_pickup_cores`, `06_parts`, `07_far_lod`, `halo_{front,right,
back,three_quarter}` + `halo_sheet` (`arm_bulwark_jugg`).

## Review fixes (independent review 2026-10-07, `review/review.json`)
| # | Review item | Fix | Proof |
|---|---|---|---|
| M1 | 3 of 4 cores looked alike edge-on | Edge-on signatures: Bulwark 24 mm glass wall + corner posts 8.5 mm above the ring; Mender outer ring 14 mm lower (two stacked lines); Phase electrode fork (prongs 28 mm, leaning into the back gap); Volt teeth kept | `02d_core_read_*` (new standard renders at −2° and −8°, colour + silhouette, front + side) |
| M2 | idle Light halos almost invisible | (a) always-on `M_HALO_Edge` lines on every arc (and band); (b) Light Mender / Phase ring glass now 21 / 20 mm tall at Light scale (25 / 23 mm unscaled; was about 11 / 13 mm); glass on the inner wall, so a lit back arc shows below the front arc at eye level; (c) 02 and 02c re-rendered with game presets next to uniform tiers, dark + daylight | `02_*`, `02c_*`, `02d_*` |
| M3 | wrong cell count at eye level | orbit height 0.004 → 0.058 (above the ring top); `halo_data.py`, catalog `orbit_height_local` | `qa/qa_report.json` `cell_view`: 100 % true count at −2° and −5° for all 12 core × weight cases |
| M4 | solid graphite from below | each arc is one shell whose glass wraps outer wall, top, inner wall and both sides of the underside (graphite only as frame lines / keel); band lip glass underneath | `03c_underside_-35deg.png` |
| M5 | no broken material | `M_HALO_Glass_Broken_T1..T4` (desaturated tier colour, `crack_tile.png` emissive map, strip UVs) in `HALO_Materials.glb`; NOTES states table | `03b_per_arc_tiers.png` (arc states row), `qa/qa_glb_report.json` |
| M6 | character showcase broke the weight rule | `place_halo` derives the weight from the arc tiers; both states use `arm_bulwark_assault` (9 → Heavy, heavy band, 3 cells) | `04_character_*` |
| m1 | pips floated on 3 cores | per-core empties `HALO_<Core>_PIP_1..4` on per-core pip rails (Head arc) | `qa_report.json` `pips`: 0.2-0.3 mm gaps, no intersections |
| m2 | heavy band read as a tray | bands clamp around the ring's lower outer wall: hang ≤ 28 mm below the ring (was 70 mm), mass outward, width kept (Bulwark Heavy 0.60 m) | `halo_sheet.png`, `qa_report.json` `vertical` |
| m3 | render cost, no LOD, double-sided | far LOD set (≤ 1.05k tris per halo), all materials single-sided, segmented single-shell profiles (near Heavy Volt 7.9k, was 8.5k + doubleSided); pickups 612-1036 tris (Phase was 3568, Mender 2544) | `07_far_lod.png`, `qa/qa_glb_report.json` |
| m4 | transparent Off glass, internal faces | `Glass_Off` opaque; welded Head ring glyph and Legs chevron; no coincident caps (bodies stop inside clamps/collars) | `qa_report.json` `topology`: 0 edges with > 2 faces, 0 open edges, 0 coincident faces |
| m5 | Mender glyph hidden | zone bridges sit on top of both rings, 1.5 mm above the inner ring top, glyph on top | `02d_core_read_8deg.png`, `01_cores_tiers_grid.png` |
| m6 | catalog numbers copied by hand | `halo_data.py` parses `armor.ron`, cross-checks the design JSON, fails loudly; docstring fixed | build log, `armor_catalog.example.json` `source` |

Look-development: `renders/_iterations/v16` (first edge-on core read) to `v18` (final): v17 full set with the
new geometry, v18 label/framing fixes, bolder broken-arc crack map, cell phases spread in the showcases,
lighter pickups, far-LOD shading.

Not changed on purpose: the cells stay 1 / 2 / 3 and orbit level (a tilted orbit would hide them from some
yaw angles). At −10° (a viewer about 2 m away) a back cell can still hide behind the ring for part of the
orbit: the true count shows 38-100 % of the time (Heavy 38-50 %; the old Bulwark Heavy showed it 0 %). Raising
the orbit further (about 0.10 m) would fix that too but makes the cells look detached; at 2 m the halo is
large and the cells move, so the count is still easy to read. Minimum cell clearance to ring and band is
22.7 mm, no collisions at any orbit phase.

Verification: rebuilt from scratch with every generated output moved away (`--renders none`): all 8 .glb
files, the catalog and the sprites are byte-identical (md5) to the shipped ones. `qa/qa_glb.py` and
`qa/qa_blender.py` report 0 problems on the shipped exports.

## Earlier look-development log (`renders/_iterations/`)
- v01-v12 (first session): core silhouettes, arc split and glyphs, Medium/Heavy bands, tier grid, pickups,
  character placement, hit state (shards, flash, crack) and the weight-class silhouettes.
- v13-v15_final: per-arc tier support, only `tier` pips shown, power-cell fin shortened, raised character
  camera, anti-aliased silhouettes, catalog generated by the build.

## Known limitations
- The cell trail fin is bent for the Medium orbit radius; on Light/Heavy orbits the mismatch is a few mm.
- The Kestrel model in the character renders is the TRELLIS test mesh; only the halo is part of this kit.
- `halo_kit.glb` also contains the `HALO_Swatch_*` quads (at x ≈ 0.5-0.8 m) and the far LOD meshes (overlapping
  the near ones); load the per-core files in the game.
- The far-LOD band is one continuous chamfered sweep, so it catches a little more specular than the segmented
  near band; at the >20 m switch distance that is a few pixels. Cross-fade or switch on a dithered edge if the
  pop is visible in game.
- `art/HALO_SHIELD_SPEC.md` still says "1–4 small tier pips on the front of the ring" with shared positions;
  the kit now ships per-core pip seats (`HALO_<Core>_PIP_*`). The spec text is owned by the art lead.
