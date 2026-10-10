# HALO shield kit: notes and engine-integration guide

Armor is a stylized tech halo floating above the head (`art/HALO_SHIELD_SPEC.md`, DIRECTION_LOG items 5-7 and 9).
This folder is the complete kit: 4 core silhouettes split into 4 zone arcs each, one merged frame mesh per weight
class (the Medium and Heavy frames include the weight band), the Medium/Heavy bands on their own, a far LOD set,
centred tier-pip seats, a power cell per core, hit shards, loot cores, VFX sprites, an example armor catalog,
showcase renders and QA scripts.

Rebuild everything from scratch (about 20 s without renders, about a minute with all renders on the GPU, several
minutes on the CPU fallback; absolute paths, the project path contains a space). Every path inside the scripts
is resolved from the script's own location, so any checkout works:

```
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup ^
    -P "F:/git/val etf/assets/shields/build_halo.py" -- [--renders all|none|<list>] [--iter vNN] [--no-export]
<list> = grid,lineup,sil,eye,blind,coverage,underside,pickups,parts,lod,turn,char
```

QA (run after a build; both must report 0 problems), then the in-play QA renders:

```
python "F:/git/val etf/assets/shields/qa/qa_glb.py"
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P "F:/git/val etf/assets/shields/qa/qa_blender.py"
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup ^
    -P "F:/git/val etf/assets/shields/qa/qa_review_render.py" -- <job>
    (job = eyelevel, distance, distance_far, underside, closeups, wire, ingame; one call each)
python "F:/git/val etf/assets/shields/qa/qa_compose.py"
```

| File | What |
|---|---|
| `build_halo.py` | Entry point: sprites, kit, exports, `halo_kit.blend`, catalog, renders |
| `halo_data.py` | Pure Python. Reads `game/assets/data/armor.ron` (weight bands, presets, capacities...), cross-checks it against `design/systems/data/armors.slice.json` and **stops the build if they disagree**. Art-side weight visuals (scale, orbit radius and height) live here |
| `halo_lib.py` | Shapes (circle / hexagon sweeps), mesh builder with strip UVs and per-edge materials, sliver clean-up, split/merge by material (custom normals kept), glyphs, materials |
| `halo_parts.py` | Part builders: arcs per core, weight bands, far LOD, pip seats and pip boards, power cells (generic + one per core), shards, pickup cores |
| `halo_render.py` | Showcase renders and the true-pixel checks (blind core test, LOD switch, arc states). `place_halo()` is the reference assembly for the engine |
| `compose_sheet.py` | Lays out the true-pixel check sheets (system Python + PIL, called by `halo_render.py`) |
| `make_sprites.py` | Procedural VFX sprites + the broken-arc crack map (system Python + PIL + numpy) |
| `make_catalog.py` | Writes `armor_catalog.example.json` from the game data (no copied numbers) |
| `qa/qa_glb.py`, `qa/qa_blender.py` | Checks on the exported files: names, group hierarchy, materials, zero-area triangles, draw and triangle counts per assembled halo, topology (standalone meshes and every assembled halo), arc directions, centred pip rows and their seating, band hang, cell clearance and cell-count visibility. Reports in `qa/*.json` |
| `qa/qa_review_render.py`, `qa/qa_compose.py` | The reviewer's in-play renders re-run on the current kit (exports, engine-style assembly): `qa/renders/Q01`-`Q07` (compare with `review/renders/R01`-`R07`) |
| `halo_kit.blend / .glb / .fbx` | Every kit object at the halo origin, plus empties and material swatches. The .blend opens on one clean Heavy halo per core |
| `export/HALO_<Core>.glb/.fbx` | Per core, six group nodes at the scene root (see "Kit layout"): `_Near` (4 glass arcs), `_Frames` (`Frame_Light/Medium/Heavy`), `_Bands` (`Band_Medium/Heavy`), `_Pips` (`PIP_Centre` + centred rows `PIP_<n>_<i>`), `_Cells` (`HALO_PowerCell_<Core>`), `_Far` (`Far_Glass_<Zone>` x4 + `Far_Frame_<Weight>` x3) |
| `export/HALO_Common.glb/.fbx` | `HALO_TierPip`, shared empties `HALO_PIP_1..4` (the 4-pip row on the Bulwark seat, spec name), the generic `HALO_PowerCell`, `HALO_Shard_A/B/C` |
| `export/HALO_Pickups.glb/.fbx` | Loot cores `HALO_Core_{Bulwark,Mender,Volt,Phase}` |
| `export/HALO_Materials.glb` | One swatch per material (`HALO_Swatch_*`): the glTF material library, incl. the embedded crack map |
| `sprites/*.png` | `hex_hit_flash`, `crack_overlay`, `shard_sprite` (512x512 white/greyscale + alpha), `crack_tile` (512x512 seamless greyscale RGB, emissive map of the broken material). `_preview.png` is a check sheet |
| `armor_catalog.example.json` | JSON Schema, rules and 9 example armors (8 are the game's own presets) |
| `renders/` | Showcase renders and true-pixel checks (list below). `renders/_iterations/vNN/` keeps the look-development history |
| `review/` | The independent reviews and their evidence: round 1 `review/r1_review.json` (+ `review/renders`), round 2 `review/review.json` = `review/critique_latest.json` (+ `review/r2/`). See "Review fixes" |

## Axes and attachment
- Blender: metres, Z up, the wearer faces **−Y**. glTF (what Bevy loads): Y up, the wearer faces **+Z**,
  the same convention as the character exports, so halo and character agree with each other.
- **Bevy: turn the halo root 180° about +Y** (`Quat::from_rotation_y(PI)`), the same fix-up as the character
  glTFs. The game's player faces **−Z** (`game/crates/val_etf/src/render.rs`, `arc_angle`: Head at −Z, Arms at
  −X = the player's left). Without the turn, copying the gameplay yaw onto the halo puts the Head arc behind the
  player and the Arms arc on the player's right.
  **One-line check in the game:** when the player faces the camera, the Head arc (the one carrying the pips)
  faces the camera too, and the Arms arc is on the player's left (the viewer's right).
- Arc zones, seen from above: **Head = front** (Blender −Y / glTF +Z), **Arms = +X** (the wearer's left),
  **Torso = back** (Blender +Y / glTF −Z), **Legs = −X** (the wearer's right). `qa/qa_blender.py` checks each
  arc's direction (`zones` in `qa/qa_report.json`).
- Every arc, frame, band and far-LOD mesh has its **origin at the halo centre**, so all parts of one halo share
  one transform. The six group nodes of a per-core file sit at the origin with no transform.
- Attach the halo root at the character's `<P>_SOCKET_Halo` (0.22 m above the top of the head, over the skull).
  Copy the socket's **position** every frame and the body's **yaw** only. No head-bone pitch or roll, so the
  halo stays level and the Head arc always points where the body faces (the arcs map onto body zones).

## Shapes, sizes and triangle budget
Every core has a silhouette that reads **edge-on** (players see each other's halos 1-10° from below), not only
from above, and a power cell of its own shape (see Orbiting cells):

| Core | Ring (from above) | Edge-on signature | Ring height | Outer Ø Light / Medium / Heavy (at scale) |
|---|---|---|---|---|
| Bulwark | thick faceted hexagon, 0.150 m apothem | tall 24 mm glass wall, 6 corner posts 8.5 mm above the ring (small edge lights on top) | 31 mm (40 mm with posts) | 0.34 / 0.43 / 0.60 m |
| Mender | twin thin rings (r 0.143 / 0.177) | the outer ring sits 14 mm lower: two stacked lines, stepped ends; zone bridges on top of both rings | 28 mm | 0.31 / 0.40 / 0.55 m |
| Volt | crown ring, 8 sawtooth teeth | teeth 30 mm above the ring | 22 mm (56 mm with teeth) | 0.30 / 0.39 / 0.53 m |
| Phase | smooth round ring, 30° gap at the back | an electrode fork: two glass prongs rise 28 mm either side of the gap and lean into it | 23 mm (53 mm with prongs) | 0.29 / 0.38 / 0.52 m |

Triangles (`qa/qa_glb_report.json`, `assembled`):

| Core | 4 arc glass | Frame L / M / H | Near ring L / M / H | Far ring L / M / H (glass + far frame) | Core cell |
|---|---|---|---|---|---|
| Bulwark | 548 | 2292 / 2836 / 3672 | 2840 / 3384 / 4220 | 676 / 784 / 808 | 120 |
| Mender | 2716 | 920 / 1944 / 3036 | 3636 / 4660 / 5752 | 696 / 1020 / 1092 | 216 |
| Volt | 1124 | 3292 / 4316 / 5408 | 4416 / 5440 / 6532 | 1036 / 1360 / 1432 | 240 |
| Phase | 1670 | 1446 / 2406 / 3384 | 3116 / 4076 / 5054 | 760 / 1076 / 1148 | 212 |

A whole near halo with its 1 / 2 / 3 cells: Bulwark 2960 / 3624 / 4580, Mender 3852 / 5092 / 6400,
Volt 4656 / 5920 / 7252, Phase 3328 / 4500 / 5690 tris (+ 8 per pip). **Draw calls per halo: ring 6 / 7 / 8**
(4 arc glass + 2 / 3 / 4 frame primitives), **with cells 8 / 11 / 14** (2 primitives per cell; identical cells
batch). Far: ring 6 / 7 / 7 draws. The standalone bands are 544-2116 tris (`HALO_<Core>_Band_*`, alternative
assembly only).

Small parts: `HALO_TierPip` 8 tris (18 mm diamond facing −Y), the generic `HALO_PowerCell` 120 tris (6 cm),
`HALO_PowerCell_<Core>` 120-240 tris (4-6 cm), shards 14-26 tris (~3 cm), pickups 612-1036 tris (8.5-11 cm,
origin at the bottom centre, front −Y).

## Materials (linear RGB, all opaque and single-sided)
| Material | Use | Values |
|---|---|---|
| `M_HALO_Glass_T1..T4` | lit arc glass, pips, cells, band lip, shards, pickup windows | base = 0.12 × tier colour, emissive = tier colour, strength 2.4 (`KHR_materials_emissive_strength`), rough 0.25, clearcoat 0.4 |
| `M_HALO_Glass_Broken_T1..T4` | the spec's **broken** material: an arc whose pool is 0, until it regenerates | tier colour 50 % desaturated, emissive strength 1.0 × `crack_tile.png` (0.18 body, 1.0 fracture lines), base 0.10 × that colour, clearcoat 0.4 |
| `M_HALO_Glass_Off` | the spec's **unlit** material: uncovered arc, dark smoked glass | base (0.02, 0.02, 0.025), rough 0.6, specular 0.2 (glTF `KHR_materials_specular` 0.4, F0 ≈ 0.016; in Bevy `reflectance` ≈ 0.32 if the loader ignores the extension), no clearcoat, no emission. **Opaque** (no alpha sorting) |
| `M_HALO_Edge` | always-on frame light: thin lines on every arc and band | base (0.04, 0.045, 0.05), emissive (0.56, 0.66, 0.80) × 0.30 (cool steel, deliberately not a tier colour) |
| `M_HALO_Graphite` | arc frames, keels, clamps, bands, cell caps, pip boards | (0.030, 0.033, 0.040), rough 0.55, metal 0.15 |
| `M_HALO_Graphite_Far` | far-LOD frames only | (0.030, 0.033, 0.040), rough 0.85, metal 0.05, specular 0.15: the long far sweeps must not catch broad highlights |
| `M_HALO_Gunmetal` | heavy-band bolts | (0.11, 0.115, 0.12), rough 0.35, metal 0.85 |
| `M_HALO_Bone` | pickup grip band | (0.55, 0.52, 0.46), rough 0.6 |

Tier colours: T1 white (0.85, 0.88, 0.92) · T2 blue (0.10, 0.45, 1.0) · T3 violet (0.55, 0.15, 1.0) ·
T4 gold (1.0, 0.62, 0.08). Only the broken material uses a texture; everything else is flat colour.
Per the spec's newest section (each arc has its own tier colour; "one material per tier plus unlit and broken"),
every arc takes its own material: `M_HALO_Glass_T<tier>` (covered), `M_HALO_Glass_Off` (unlit / uncovered) or
`M_HALO_Glass_Broken_T<tier>` (broken; one per tier so the cracked arc keeps its colour). All of them ship in
`HALO_Materials.glb`. All meshes are closed outward-facing shells (each arc's glass + its share of the frame
together), so every material exports `doubleSided: false`.

UVs: arc and band glass is unwrapped as **straight strips** (U along the arc, V around the profile, 1 UV unit =
5 cm), so the tileable crack map runs cleanly along each arc. Every mesh has UVs.

### Kit layout and primitives (what to swap)
Every mesh is one glTF node whose primitives are split per material. **Find primitives by material name only**
(the exporter drops unused materials, so the index of the same material differs between meshes;
`halo_render.slot_of()` does the lookup). As shipped, every swappable glass primitive uses `M_HALO_Glass_T1`.

| Group node (scene root) | Children | Primitives (by material) |
|---|---|---|
| `HALO_<Core>_Near` | `HALO_<Core>_Arc_{Head,Arms,Torso,Legs}` | glass only (`M_HALO_Glass_T1`): swap per arc |
| `HALO_<Core>_Frames` | `HALO_<Core>_Frame_{Light,Medium,Heavy}`: graphite + edge lines of all 4 arcs, plus the weight band for Medium / Heavy | Light: `Graphite`, `Edge`. Medium: `Graphite`, `Edge`, `Glass_T1` (band lip). Heavy: `Graphite`, `Edge`, `Gunmetal`, `Glass_T1` (band lip) |
| `HALO_<Core>_Bands` | `HALO_<Core>_Band_{Medium,Heavy}` (the spec meshes, band alone) | Medium: `Graphite`, `Glass_T1` (lip), `Edge`. Heavy: `Graphite`, `Gunmetal`, `Glass_T1` (lip), `Edge` |
| `HALO_<Core>_Pips` | empties `HALO_<Core>_PIP_Centre` and `HALO_<Core>_PIP_<n>_<i>` (n = 1..4, i = 1..n) | - |
| `HALO_<Core>_Cells` | `HALO_PowerCell_<Core>` | `Glass_T1` (highest arc tier), `Graphite` |
| `HALO_<Core>_Far` | `HALO_<Core>_Far_Glass_<Zone>` x4, `HALO_<Core>_Far_Frame_{Light,Medium,Heavy}` | far glass: glass only (swap per arc). Far frame: `Graphite_Far`, `Edge` (+ `Glass_T1` band lip for Medium / Heavy) |

- **Near halo** = the 4 arcs of `_Near` + exactly ONE `Frame_<weight>` (+ pips + cells).
- **Far halo** = the 4 `Far_Glass_<Zone>` + ONE `Far_Frame_<weight>` (+ cells, no pips).
- `_Bands` keeps the spec names and allows an alternative assembly (`Frame_Light` + `Band_<weight>`, one more
  draw). Never show a band together with `Frame_Medium` / `Frame_Heavy`: they already contain it.
- Spawning `HALO_<Core>.glb#Scene0` as-is draws every group at once. Either spawn the named meshes, or spawn the
  scene and hide `_Bands`, `_Far` and the two unused frames (toggle the group nodes by name).
- Each arc was built as one closed shell (glass, frame lines and edge-light stripes share vertices) and then split
  by material into the glass arc and the frame. The split pieces carry the shell's custom normals, so the border
  between glass and frame shades as one surface.
- `HALO_Common.glb`: generic `HALO_PowerCell` (glass, graphite), `HALO_TierPip` and shards (glass only).
  `HALO_Pickups.glb`: window glass, graphite, bone.

## Assembling a halo in the engine
`halo_render.place_halo(core, arc_tiers, ...)` is the reference implementation. Per player:

1. **Weight class from the arc tiers**: protection score = sum of the 4 arc tiers, weight band from
   `armor.ron weight_bands` (Light 1-4, Medium 5-8, Heavy 9-16). Never store the weight separately.
2. **Root**: one transform at the socket, uniform scale by weight class (Light 0.85, Medium 1.0, Heavy 1.2),
   turned 180° about +Y in Bevy (see Axes).
3. **Arcs**: spawn the 4 `HALO_<core>_Arc_<zone>` meshes as children. Each arc (one glass primitive) gets the
   material of **that arc's tier** (`M_HALO_Glass_T<tier>`); tier 0 (uncovered) gets `M_HALO_Glass_Off`; a broken
   arc gets `M_HALO_Glass_Broken_T<tier>`.
4. **Frame**: exactly one `HALO_<core>_Frame_<weight>` as a child of the same root (Light has no band; Medium and
   Heavy include theirs). Its graphite, gunmetal and edge primitives never change; its band-lip glass
   (`M_HALO_Glass_T1` as shipped) gets the highest arc tier's material.
5. **Tier pips**: n = the **highest arc tier**; spawn n `HALO_TierPip` at `HALO_<core>_PIP_<n>_1 .. _<n>`, a row
   centred on the Head arc. The same positions from the centre empty `HALO_<core>_PIP_Centre`:
   **x_i = (i − (n + 1) / 2) × 16 mm**, i = 1..n (i = 1 on the viewer's left when facing the wearer), same y and z
   as the centre. Never show unlit pip slots: the pip count is the tier. Every core's Head arc has a small
   graphite pip board right behind the row, so the pips read against dark graphite instead of the
   same-coloured glass behind them. (`HALO_PIP_1..4` in `HALO_Common.glb` are the 4-pip row on the Bulwark seat,
   kept for the spec name; use the per-core rows.)
6. **Power cells**: 1 / 2 / 3 `HALO_PowerCell_<core>` for Light / Medium / Heavy (see Orbiting cells), glass in
   the highest arc tier colour.

Bevy notes: the glTF asset exposes the meshes by name (`HALO_Volt_Arc_Head`, …) and the materials by name
(`M_HALO_Glass_T1`, …), so the halo can be built straight from the named meshes with the game's own
`StandardMaterial`s instead of spawning the whole scene. Node extras (`halo_group` on the group nodes,
`halo_core`, `halo_zone`, `halo_weight`, `halo_lod`, `halo_pip_count`, `halo_pip_index`, `halo_pip_spacing_m`,
`halo_lip`) are
exported too (`GltfExtras` on the node entity) if scene spawning is preferred.

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
- Mesh: **`HALO_PowerCell_<core>`**, a miniature of the core. The cells orbit above the ring against the sky and
  are the most visible part of a halo at range, so they carry the core's identity. Each is rotationally
  symmetric about its vertical axis and shows the same shape at every orbit angle:
  Bulwark = a wide, low hex puck (a flat dash at range), Mender = two stacked glass-rimmed discs on a spine
  ("=", two concentric rings from above), Volt = a toothed crown round a tall glass spike (a vertical spike),
  Phase = a glass orb in a thin open ring (a round dot). The generic `HALO_PowerCell` capsule (spec name) stays
  in `HALO_Common.glb` as a fallback. `renders/06_parts.png` shows all of them from the side and from above.
- Radius (halo-local, multiplied by the root scale): Light 0.215, Medium 0.245, Heavy 0.275.
- Height (halo-local, multiplied by the root scale): **Light 0.058, Medium 0.065, Heavy 0.080** (Blender z /
  glTF y), above the ring top, and higher for the bigger banded halos so the far-side cells clear the front band.
  `qa/qa_blender.py`: the true count shows for 100 % of the orbit at −2° and −5° for every core and weight
  (Volt Light 99 % at −5°), counting cell-on-cell occlusion too.
- Period: Light 2.6 s, Medium 3.4 s, Heavy 4.6 s (heavier = slower, heavier orbit). Spread n cells evenly
  (360°/n). A ±3 mm vertical sine bob at 1.3× the orbit frequency keeps them alive.
- Orientation: the cell travels along its local **+X**, the orbit centre is on its local **+Y** (Blender).
  For a cell at orbit angle θ (counter-clockwise from +X, seen from above) use yaw = θ + 90°.
  In glTF terms: travel = +X, orbit centre = −Z of the cell. The short, flat trail fin points along −X and lies
  in the orbit plane (a streak from above, edge-on and invisible from the side).
- Cell glass = the highest arc tier colour. The status effect may tint the trail particles (catalog
  `rules.status_vfx`).

### Far LOD (beyond ~20 m)
Swap the 4 arcs for `HALO_<core>_Far_Glass_<zone>` (same per-arc material swap) and the frame for
`HALO_<core>_Far_Frame_<weight>` (Light has a frame too: its edge lines and core details). Keep the cells and
drop the pips. Beyond 20 m one pixel is 3 cm or more, so the far set carries the core signature at **about twice
the near size**: Bulwark corner posts 18 mm above the ring (near 8.5 mm), Mender ring step 28 mm (near 14 mm),
Volt teeth 45 mm (near 30 mm), Phase prongs 47 mm (near 28 mm). Graphite blocks where the near kit has seam
clamps, zone plates, tooth caps and prong sleeves give the far glass the near kit's lit / dark rhythm; the band
mass, its flush lip glass and the edge outline stay; ticks, bolts, glyphs and pip boards are gone. The far frames
use `M_HALO_Graphite_Far` (rough 0.85) so the long sweeps never bloom. Glass and frame are separate meshes
because the 4 glass primitives must stay swappable per arc.
`renders/07b_far_lod_switch_20m.png` + `07b_far_lod_switch_luma.json`: at the 20 m switch the far halo's mean
brightness is within −6 … +7 % of the near kit for Medium and Heavy and −14 … +8 % for Light (the far Light
halos are slightly darker, never brighter by more than 8 %); near-white pixels 0 % on Medium / Heavy in both.
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
| `02d_core_read_{2,8}deg(_silhouette).png`, `02d_core_read_side_2deg_silhouette.png` | naming the core edge-on at a large size: all cores × weights with game-legal coverage at −2° (~10 m) and −8° (~2.5 m), front and side |
| `02e_core_blind_10m_25m.png` (+ `02e_core_blind_key.json`) | **name-the-core blind test at TRUE 1080p pixels** (vfov 78): 10 m near kit and 25 m far LOD, front and side, daylight / dark / silhouette, 4 rows (Light T1, Light H2 T2, Medium, Heavy), cores shuffled per row; the key is in the json |
| `03c_underside_-35deg.png` | from below (jetpacks, ziplines, lower ground): tier colour on the underside glass, inner walls and band lips |
| `03d_arc_states_range.png` (+ `.json`) | the Head arc lit / broken / uncovered at true pixels, 5 m and 10 m, with the measured Head-arc luma and near-white share (the uncovered arc must stay dark) |
| `07b_far_lod_switch_20m.png` (+ `_luma.json`) | near kit vs far LOD at the 20 m switch, true pixels + large, mean brightness per pair |

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
radius, **orbit height** (0.058 / 0.065 / 0.080) and period.

## Showcase renders
`01_cores_tiers_grid` (4 cores × T1-T4, centred pips), `02*` (weight class and core read, see above),
`03_coverage_head_torso`, `03b_per_arc_tiers` (game presets + the lit / broken / uncovered arc states; each
state halo is rendered with the lights moved along, so all three are lit identically), `03c_underside_-35deg`,
`03d_arc_states_range`, `04_character_{idle,hit,idle_vs_hit,fullbody_idle}` (Kestrel with ONE game preset,
`arm_bulwark_assault` H3 T3 A3 L0 = 9 → Heavy, in both states; the full-body camera stands 28° to her left,
which is why the centred pips sit left of the ring's middle in that picture), `05_pickup_cores`, `06_parts`
(pips, generic cell, shards, the four core cells from the side and from above), `07_far_lod`,
`07b_far_lod_switch_20m`, `halo_{front,right,back,three_quarter}` + `halo_sheet` (`arm_bulwark_jugg`).

## Review fixes (round 2, independent review 2026-10-07, `review/review.json` = `review/critique_latest.json`)
Every critical and major issue and every minor one is addressed in the build scripts; the kit was rebuilt from
scratch, all deliverable renders, true-pixel checks, QA renders and exports were regenerated
(`renders/_iterations/v21`), and both QA scripts report 0 problems. Verification: the scripts alone, copied
into an empty sandbox (with `tools/blender_common.py` and the two armor data files), rebuild all 8 .glb files,
the catalog and the sprites byte-identical (md5) to the shipped ones.

| # | Sev. | Review item | Fix | Proof |
|---|---|---|---|---|
| 1 | major | Core identity lost beyond 8-10 m and from the side (only Volt survived) | (a) Far LOD signatures about 2× (posts 8.5 → 18 mm, Mender ring step 14 → 28 mm, teeth 30 → 45 mm, prongs 28 → 47 mm), the near look unchanged. (b) **A power cell per core**, `HALO_PowerCell_<Core>`: wide hex puck / stacked twin discs / crown + glass spike / orb in an open ring, rotationally symmetric so the shape reads at any orbit angle. (c) New standard render: blind test at true 10 m and 25 m pixels, front and side, shuffled, key in a json | `02e_core_blind_10m_25m.png`: at 10 m, front and side, the Medium and Heavy rows name all 4 cores from the cell shapes (dash / "=" block / spike / round dot) plus the ring cues (Volt teeth, Bulwark box and posts); the Light rows (1 cell) name Volt and Bulwark reliably and Mender vs Phase when the cell is clear of the ring. At 25 m (far LOD, cells 1-2 px) the Volt teeth and Bulwark posts still read; `06_parts.png`, `07_far_lod.png` |
| 2 | minor | Zero-area sliver triangles in every Heavy band (8-18 per core) | `halo_lib.fix_slivers()` in `MB.finish`: n-gon caps are triangulated, each sliver's long edge is rotated, `dissolve_degenerate` as a fallback. `qa_glb.py` fails on any triangle < 1e-10 m², `qa_blender.py` counts zero-area faces per mesh and per assembled halo | `qa/qa_glb_report.json`: 0 zero-area triangles in all 8 files |
| 3 | minor | Tier pips not centred (PIP_1 at −24 mm); Volt pips blend into the glass behind | Centred rows `HALO_<Core>_PIP_<n>_<i>` + `HALO_<Core>_PIP_Centre`, x_i = (i − (n+1)/2) × 16 mm, used by `place_halo`; a graphite pip board behind the row on all four Head arcs. Also fixed while verifying: the centred pip sat on the Head glyph (a glowing drop under the Bulwark pip, a disc under the Mender pip). The Volt / Phase glyphs moved to the rail's inner edge behind the board, the Bulwark board hides its glyph, the Mender Head glyph moved to the bridge's front end | `qa_report.json` `pips`: mean x = 0.000 mm for n = 1-4 on every core, seat gaps 0.2-0.3 mm, no intersections; `qa/renders/Q04_closeups.png` (top 4 rows, T1 and T3), `01_cores_tiers_grid.png`, `halo_sheet.png` |
| 4 | minor | `Glass_Off` almost a mirror: white glints read as T1 glass at range | The review's values (rough 0.32, clearcoat 0.3, spec 0.5) were built and rejected: under a grazing rim light they turned the whole uncovered arc pale blue-white, a worse T1 misread (`_iterations/v20/03b_per_arc_tiers.png`, right panel). Final: rough 0.6, spec 0.2, no clearcoat, base unchanged. `03b` now lights each state halo identically | `03d_arc_states_range.json`: uncovered Head-arc luma 0.03 (Bulwark, Volt) and 0.11-0.17 (thin Mender / Phase rings, edge pixels) vs lit 0.45-0.52, **0 % near-white** at 5 m and 10 m; `03b_per_arc_tiers.png` (bottom right); `Q04_closeups.png` (uncovered Arms rows). Not checked in Bevy (art session; see Known limitations) |
| 5 | minor | Far LOD pops brighter at 20 m (one smooth chamfered sweep catches broad specular) | `M_HALO_Graphite_Far` (rough 0.85, spec 0.15, metal 0.05); far-frame edges sharper than 25° are marked sharp (hard chamfers, narrow highlights); graphite blocks at the near kit's clamps / plates / tooth caps / prong sleeves; the far band lip glass sits flush in the band underside (a lip prism hanging 1 mm below made Medium / Heavy 12-16 % brighter) | `07b_far_lod_switch_luma.json`: far vs near −6 … +7 % (Medium / Heavy), −14 … +8 % (Light, darker side), near-white 0 % on Medium / Heavy; `07_far_lod.png` (far frames dark graphite now) |
| 6 | minor | Cells behind the ring hide at close range (−10°) | Orbit height by weight as suggested: Light 0.058, Medium 0.065, Heavy 0.080 (`halo_data.py`, catalog). No up/down stagger: at −10° a far-side Heavy cell would need ~0.12 m to clear the front band, which a 10-12 mm stagger does not reach and which detaches the cells | `qa_report.json` `cell_view` at −10°: Heavy true count 57-93 % (was 33-47 %), Medium 58-100 %, Light shows no cell for 0-19 % of the orbit (was 11-23 %); −2° / −5° stay 99-100 % |
| 7 | minor | Bevy facing: halo glTF faces +Z, the game's player faces −Z | "Axes and attachment": turn the halo root 180° about +Y; one-line check (player faces the camera → Head arc and pips face the camera, Arms on the player's left) | this file |
| 8 | minor | 17 root nodes per core file: every LOD and both bands draw at once; wrong primitive table | Six group nodes per core file (`_Near`, `_Frames`, `_Bands`, `_Pips`, `_Cells`, `_Far`) with `halo_group` extras; primitive table rewritten per mesh; lookup by material name only (`place_halo` / `slot_of`) | `qa_glb.py` checks the scene roots and every expected child; "Kit layout and primitives" |
| 9 | minor | ~26 draws and ~7.9k tris per Heavy halo; 488-tri cells | Arcs split by material: 4 glass-only arcs + one merged `Frame_<weight>` (graphite + edge of all arcs + band, custom normals kept); cells rebuilt with 8-sided low domes | Heavy halo 14 draws with cells (ring 8, was 16), 4.6-7.3k tris (was up to 7.9k); cells 120-240 tris (was 488); `qa_glb_report.json` `assembled`, `Q05_wireframes.png` |
| 10 | minor | Hard-coded `F:/git/val etf` paths in `build_halo.py` and `halo_render.py` | `HERE` / `REPO` from `__file__` in `build_halo.py`, `halo_render.py` and the `qa/` scripts (only usage examples in docstrings keep the absolute path) | the build runs from any checkout |

Look-development: `renders/_iterations/v19` (round-2 work in progress from the previous session),
`v20` (full set with the review's satin `Glass_Off`, rejected), `v21` (final round 2: smoked `Glass_Off`,
flush far lip, Bulwark pip board, Mender Head glyph, fair arc-state lighting, `03d` check).

## Review fixes (round 1, `review/r1_review.json`)
Kept as history; round 2 changed some numbers (orbit heights, pip seats, triangle counts, `Glass_Off`).

| # | Review item | Fix | Proof |
|---|---|---|---|
| M1 | 3 of 4 cores looked alike edge-on | Edge-on signatures: Bulwark 24 mm glass wall + corner posts 8.5 mm above the ring; Mender outer ring 14 mm lower (two stacked lines); Phase electrode fork (prongs 28 mm, leaning into the back gap); Volt teeth kept | `02d_core_read_*` (standard renders at −2° and −8°, colour + silhouette, front + side) |
| M2 | idle Light halos almost invisible | (a) always-on `M_HALO_Edge` lines on every arc (and band); (b) Light Mender / Phase ring glass now 21 / 20 mm tall at Light scale (25 / 23 mm unscaled; was about 11 / 13 mm); glass on the inner wall, so a lit back arc shows below the front arc at eye level; (c) 02 and 02c re-rendered with game presets next to uniform tiers, dark + daylight | `02_*`, `02c_*`, `02d_*` |
| M3 | wrong cell count at eye level | orbit height 0.004 → 0.058 (above the ring top; round 2: 0.058 / 0.065 / 0.080 by weight) | `qa/qa_report.json` `cell_view` |
| M4 | solid graphite from below | each arc is one shell whose glass wraps outer wall, top, inner wall and both sides of the underside (graphite only as frame lines / keel); band lip glass underneath | `03c_underside_-35deg.png` |
| M5 | no broken material | `M_HALO_Glass_Broken_T1..T4` (desaturated tier colour, `crack_tile.png` emissive map, strip UVs) in `HALO_Materials.glb`; NOTES states table | `03b_per_arc_tiers.png` (arc states row), `qa/qa_glb_report.json` |
| M6 | character showcase broke the weight rule | `place_halo` derives the weight from the arc tiers; both states use `arm_bulwark_assault` (9 → Heavy, heavy band, 3 cells) | `04_character_*` |
| m1 | pips floated on 3 cores | per-core pip seats on the Head arc (round 2: centred rows `HALO_<Core>_PIP_<n>_<i>`) | `qa_report.json` `pips` |
| m2 | heavy band read as a tray | bands clamp around the ring's lower outer wall: hang ≤ 28 mm below the ring (was 70 mm), mass outward, width kept (Bulwark Heavy 0.60 m) | `halo_sheet.png`, `qa_report.json` `vertical` |
| m3 | render cost, no LOD, double-sided | far LOD set, all materials single-sided, segmented single-shell profiles; pickups 612-1036 tris (Phase was 3568, Mender 2544) | `07_far_lod.png`, `qa/qa_glb_report.json` |
| m4 | transparent Off glass, internal faces | `Glass_Off` opaque; welded Head ring glyph and Legs chevron; no coincident caps (bodies stop inside clamps/collars) | `qa_report.json` `topology`: 0 edges with > 2 faces, 0 open edges, 0 coincident faces (standalone meshes and every assembled halo) |
| m5 | Mender glyph hidden | zone bridges sit on top of both rings, 1.5 mm above the inner ring top, glyph on top | `02d_core_read_8deg.png`, `01_cores_tiers_grid.png` |
| m6 | catalog numbers copied by hand | `halo_data.py` parses `armor.ron`, cross-checks the design JSON, fails loudly; docstring fixed | build log, `armor_catalog.example.json` `source` |

## Earlier look-development log (`renders/_iterations/`)
- v01-v12 (first session): core silhouettes, arc split and glyphs, Medium/Heavy bands, tier grid, pickups,
  character placement, hit state (shards, flash, crack) and the weight-class silhouettes.
- v13-v15_final: per-arc tier support, only `tier` pips shown, power-cell fin shortened, raised character
  camera, anti-aliased silhouettes, catalog generated by the build.
- v16-v18 (round 1): first edge-on core read, full set with the new geometry, label/framing fixes, bolder
  broken-arc crack map, cell phases spread in the showcases, lighter pickups, far-LOD shading.

## Known limitations
- Core identity at 25 m and beyond relies on the far-LOD signatures (Volt teeth, Bulwark posts); Mender vs Phase
  is not reliable there, and Light halos (1 cell) are harder to name than Medium / Heavy at 10 m.
- The cells are not LOD'd: a far Heavy Volt halo is 1432 ring tris + 3 × 240 cell tris. Beyond ~40 m (cells
  1 px) the engine can swap in the 120-tri generic `HALO_PowerCell`.
- At −10° (a viewer about 2 m away) a far-side cell can still hide behind the ring for part of the orbit
  (Heavy true count 57-93 %); at that distance the halo is large and the cells move, so the count still reads.
- Far Light halos are up to 14 % darker than the near kit at the 20 m switch (never brighter by more than 8 %).
  Cross-fade or switch on a dithered edge if the step is visible in game.
- `M_HALO_Glass_Off` was judged in Blender (EEVEE, studio and daylight rigs), not in Bevy under the map's
  environment light; check it there (and set `reflectance` ≈ 0.32 if `KHR_materials_specular` is not applied).
- The Kestrel model in the character renders is the TRELLIS test mesh; only the halo is part of this kit.
- `halo_kit.glb` also contains the `HALO_Swatch_*` quads (at x ≈ 0.5-0.8 m), the bands and the far LOD meshes
  (overlapping the near ones); load the per-core files in the game.
- `art/HALO_SHIELD_SPEC.md` (owned by the art lead) still says "1–4 small tier pips on the front of the ring"
  with shared positions `HALO_PIP_1..4`, a single `HALO_PowerCell` and one `HALO_<Core>_Band_*` per weight; the
  kit additionally ships per-core centred pip rows, per-core cells and merged frames (the spec names are kept).
