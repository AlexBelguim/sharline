# Showhome completed props kit

Run `build_props.py` in headless Blender 5.2 with `--no-render --check` to rebuild the complete library,
placed scene and alignment checks. Omit `--no-render` to regenerate all prop tiles and concept comparisons.
`--only` remains a development tool and writes legacy `_partial` filenames; the completed files below are
the game deliverables. No game sources are changed.

Load **`houses.glb`, `ground.glb`, and `props_placed.glb` at identity**. All are in the design frame and
exported glTF Y-up: Bevy `(x, z, -y)` from design `(x east, y north, z up)`. `props.glb` is a reusable
local-origin library; loading its entire scene as a map would pile the assets at the origin. Its root names
are `PROP_<Name>_Root`, with one child mesh per material. Source meshes in `props.blend` retain the existing
`PROP_<Name>` convention and the `Prop` helpers.

`props_placements.json` describes every matched placement, including `owner`. The sole owner is:

| GLB | Geometry |
|---|---|
| `ground.glb` | Mover truck, delivery pods, picket fence runs, boundary/lawn hedges, arbours, pylons and sagging cable |
| `houses.glb` | Kitchen islands, sofas, dressers, garage shelving/workbenches/cars and terrace heat pumps |
| `props_placed.glb` | Street cartons/crates/chairs; hot tubs, outdoor kitchens, tanks, bins, parcel lockers, charger, model display, shuttle shelter; greenhouses, studios, sheds, sales office and parcel hub |
| `props.glb` library only | Free cardboard sizes, modular fences/hedges/wires, pallets, printed block stacks, rebar, cement bags, cones, barriers, rocks, pebbles and dirt/sand mounds |

Never add the free props in the play rectangle without placing them within an existing collision volume or
supplying matching collision. They are intended for the render-only backdrop and for future collision-aware
dressing. The source builder API is unchanged, so the ground and backdrop builders can request selected
assets with `build({'only': set(names)})` and access each row's `obj`.

The small site kit contains: pallet, six-course printed blocks on a pallet, eighteen tied rebar rods,
folded cement bag and stacked bag pallet, a 0.75 m two-band cone, a two-metre water-filled plastic barrier,
two faceted rocks, nine-pebble cluster, earth mound and sand mound. All have UVs in metres, bevelled edges
where appropriate and ordinary glTF PBR colours. Original graphics are geometric marks only, with no brands
or text. Sharp planar rocks use 20 triangles apiece; the softer piles use 80. Grass/leaf cards and decals
remain on hold.

The new architectural props come directly from the annotated layout's wall pieces, leaving every doorway
and window empty. Printed wall beads are real 4 cm geometry with 6 mm recessed joints. Flat roof slabs have
a recessed membrane or opaque twin-wall surface, 12 mm proud perimeter coping, physical underside drip
detail and a corner drain. Coping stays at the existing collision cap; no unsupported parapet wall is added.
The greenhouse stays flat and opaque, as its solid collision requires. Tank, bin store, hub and shelter
remain visibly closed at their solid brush faces. Thin cabinet joints have opaque backing to avoid invisible
collision gaps. The hot tub has an insulated closed cover.

Painted v2 material preference uses `printed_concrete_layers`, `concrete_smooth`, `fibercement_sage`,
`fibercement_clay`, `timber_pallets`, `wood_boards_stained`, `metal_scaffold_tube`, `metal_painted_yellow`,
`garden_soil`, `worksite_packed_dirt`, `gravel` and `construction_sand`, each with normal and ORM maps. The
builder temporarily falls back to the old textures if a v2 set does not yet exist. Specialist cardboard,
vehicle white paint, solar cells, cloth, opaque greenhouse sheets and the held foliage use the established
library. No shader noise changes exported colour: albedo/tint/vertex contact shade are exported as ordinary
base colour, baseColorFactor and COLOR_0. Height maps are game-side parallax inputs and are not baked into
the glTF shader. Refer to the v2 README for physical ranges and repeat scales.

`props_manifest.json` reports every source asset's triangles, bounds and materials, plus the **placed**
triangle sum. `props_export_audit.json` checks the actual binary GLBs: all meshes have UVs and exactly one
material primitive; material/texture counts, normal/ORM counts and roots are recorded. Source library
triangles include optional fixtures already owned by other GLBs and are not the playable-map prop budget.

Final geometry: **58 library assets, 175,896 triangles**; **107,780 placed triangles** in the additional
map props scene. The requested small site / rock kit totals **10,976 triangles**:

| Asset | Triangles |
|---|---:|
| Pallet | 352 |
| Printed block stack | 3,592 |
| Rebar bundle | 664 |
| Cement bag / bag pallet | 284 / 4,896 |
| Traffic cone / plastic barrier | 264 / 544 |
| Low rock / tall rock / pebble cluster | 20 / 20 / 180 |
| Earth mound / sand mound | 80 / 80 |

`props_check.json` contains dense 10 cm surface coverage / vertex checks for every brush-matched library
placement. `props_alignment.json` is the global ray checker run on the actual `props_placed.glb`, and
`props_alignment_summary.json` filters it to this file's owned brush tags. Invisible samples for houses or
ground in the global standalone report are expected because those GLBs are deliberately absent.
Existing truck camera wings and pylon hardware use the original named small-detail allowance; they belong
to the ground audit. Newly added brush fixtures have no extra collision exemptions.

Look development uses the game sun (azimuth 188 degrees from north, elevation 54 degrees, linear RGB
`1.0, 0.84, 0.66`, energy 2.5, world strength 0.65) and low-contrast AgX. `renders/props/props_contact_sheet_concept_compare.png` and each
`compare_<Name>.png` pair the rendered prop with a matching concept crop. Crop provenance is saved in JSON.
The palette and broad clean forms match the concept; collision forces flatter, closed silhouettes for the
greenhouses, shelters and flat-roof pods. The site kit follows the concept worksite's clean cream, warm earth,
quiet timber and safety orange. It does not copy the concept's deliberately unsupported rounded cover.

Open art choice: switching those closed or flat silhouettes to enterable shelters, a domed greenhouse or
tall parapets requires new collision from the game owner. The delivered kit keeps the current gameplay.
