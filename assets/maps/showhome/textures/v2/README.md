# Showhome painted material library v2

Continues v1 palette, helpers and metre UV convention. All four maps are 1024 x 1024 PNG. Albedo is sRGB; normals and ORM are linear; height is unsigned 16-bit linear grayscale (white = high).

Normals use OpenGL / glTF +U red, +V green. ORM = R occlusion, G roughness, B metalness. Use REPEAT samplers on both axes. All tint multipliers are white except neutral fibercement_panel, whose linear mean is .70 and is tinted by concept linear colour / .70. No baked directional light.

Each family shares the exact integrated linear mean from ../_src/palette.json, including cavities. Fresh/weathered variants may be mask blended without brightness changes. Krea2 provides broad paint colour; every seam, layer, shingle joint, tyre tread and height channel is exact procedural structure. No photographic grain and no micro dirt. Foliage cards and decal atlas remain on hold.

## Mapping and physical depth

Wall V runs up. Jointed cladding repeat is 4.8 m: U .125/.375/.625/.875, V .25/.75. Panels are 1.2 x 2.4 m, seams 14 mm wide with 9 mm recession and 2 mm rounded edges. Real panel meshes use seam-free fibercement_panel, so parallax does not duplicate their geometry. The top-of-panel brightening is an intrinsic painted wash, never a cast lighting highlight.

Printed beads are .04 m high, 32 per 1.28 m repeat. Roof V points up slope: .5 m shingle width and .25 m course pitch, half stagger, .010 m max relief. Paving is .6 m; kerb U follows length with joints at .5 and 1.5 m in the 2 m repeat. Low edging and trim profiles take physical depth from geometry. Do not displace their collision meshes.

Trim sheet keeps the v1 15 strips and UV rectangles in trims.json; U is still 4 m. The v2 sheet is square 1024 x 1024 (256 px/m along U); V rectangles are unchanged. It carries mixed strip colours and metalness, so its integrated colour is intentionally exempt from single-colour mean matching. Use the profile strip UV rectangles with a 2 px vertical inset.

## Textures

| Name | Use | Repeat m | Tint | Roughness | Height range m |
|---|---|---:|---|---:|---:|
| `fibercement_sage` | 1.2 x 2.4 m fibre cement panels; jointed sheet | 4.8 | white | 0.65 | 0–0.00900 |
| `fibercement_sage_weathered` | Soft painted water streaks below joints | 4.8 | white | 0.67 | 0–0.00900 |
| `fibercement_clay` | 1.2 x 2.4 m fibre cement panels; jointed sheet | 4.8 | white | 0.65 | 0–0.00900 |
| `fibercement_clay_weathered` | Soft painted water streaks below joints | 4.8 | white | 0.67 | 0–0.00900 |
| `printed_concrete_layers` | Horizontal printed beads at 40 mm pitch | 1.28 | white | 0.8 | 0–0.00900 |
| `printed_concrete_layers_dusty` | Printed beads with soft dusty base wash | 1.28 | white | 0.82 | 0–0.00900 |
| `trim_sheet_house` | Frames, sills, coping, gutters, fascia, flashing; see trims.json | 4 | white | 0.65 | 0–0.00600 |
| `roof_shingle_dark` | Half-bond shingles, 500 x 250 mm | 2 | white | 0.7 | 0–0.01000 |
| `roof_shingle_dark_lichen` | Sparse subtle painted lichen spots | 2 | white | 0.74 | 0–0.01000 |
| `roof_ridge_verge` | Ridge cap and verge pieces, joints every .5 m along U | 2 | white | 0.7 | 0–0.00800 |
| `paving_slabs` | 600 mm paving slabs, 10 mm recessed joints | 2.4 | white | 0.8 | 0–0.01000 |
| `paving_slabs_moss` | Paving with soft moss only in the joints | 2.4 | white | 0.84 | 0–0.01000 |
| `kerb_concrete` | One metre kerb units, U runs along kerb | 2 | white | 0.8 | 0–0.00900 |
| `edging_strip` | Concrete garden edging; one metre units along U | 2 | white | 0.8 | 0–0.00600 |
| `asphalt` | Fresh calm violet grey asphalt | 4 | white | 0.85 | 0–0.00300 |
| `asphalt_patched` | Repaired square patches, same average as fresh asphalt | 4 | white | 0.87 | 0–0.00400 |
| `asphalt_cracked` | Sparse cracks sealed with broad tar lines | 4 | white | 0.82 | 0–0.00400 |
| `grass_lawn` | Lush lawn ground; foliage cards intentionally on hold | 2 | white | 0.9 | 0–0.01400 |
| `grass_lawn_dry` | Dry patchy lawn, same family mean | 2 | white | 0.93 | 0–0.01000 |
| `grass_verge_weeds` | Verge with simple broad painted weed marks | 2 | white | 0.9 | 0–0.01600 |
| `garden_soil` | Soft garden soil | 1 | white | 0.95 | 0–0.01400 |
| `worn_dirt` | Trodden garden dirt without photographic grit | 1 | white | 0.93 | 0–0.01000 |
| `bark_mulch` | Broad stylized bark pieces, same soil family mean | 1 | white | 0.96 | 0–0.02400 |
| `gravel` | Loose stylized pebbles | 1 | white | 0.9 | 0–0.02800 |
| `gravel_compacted` | Compacted gravel path | 1 | white | 0.92 | 0–0.01500 |
| `worksite_packed_dirt` | Packed worksite dirt | 6 | white | 0.95 | 0–0.02200 |
| `worksite_mud_tracks` | Two repeating tyre track lanes in painted mud | 6 | white | 0.8 | 0–0.03200 |
| `construction_sand` | Soft construction sand; no stamped round blotches | 6 | white | 0.95 | 0–0.02200 |
| `foundation_slab` | Printed concrete foundation slab, .6 m sections | 2.4 | white | 0.84 | 0–0.00800 |
| `timber_pallets` | Unbranded pallet timber; V follows board length | 2 | white | 0.8 | 0–0.00700 |
| `wood_boards_stained` | Stained garden boards and fences | 2 | white | 0.8 | 0–0.00800 |
| `metal_corrugated_site` | Painted cream corrugated site fence; .1 m flutes | 2 | white | 0.6 | 0–0.01800 |
| `metal_scaffold_tube` | Muted galvanized scaffold metal | 1 | white | 0.48 | 0–0.00080 |
| `fibercement_panel` | Seam-free neutral painted panel face; real mesh seams supply depth | 2.4 | white | 0.65 | 0–0.00035 |
| `concrete_smooth` | Cast concrete blocks, rocks, coping and poles | 2 | white | 0.8 | 0–0.00300 |
| `picket_wood_white` | Painted white pickets; V follows timber length | 1 | white | 0.65 | 0–0.00300 |
| `metal_painted_yellow` | Crane and barrier yellow painted metal | 2 | white | 0.55 | 0–0.00100 |
| `truck_paint_white` | Plain white painted props and delivery vehicle | 3 | white | 0.42 | 0–0.00050 |
| `cardboard` | Plain kraft cardboard for unbranded site bags | 1 | white | 0.85 | 0–0.00100 |

Every row has `.png`, `_normal.png`, `_orm.png` and `_height.png`. Compatibility support surfaces are included for the existing kit rather than rewriting its material names.

## Macro breakup

`macro_ground.png` and `macro_walls.png`: seamless 1024², 16-bit linear greyscale, 32 m repeat, neutral .5. Suggested subtle multiplier: `1 + (mask - .5) * .12`; ground and walls use different seeds. Do not multiply AO or height by this mask.

## Rebuild and checks

1. `python assets/maps/showhome/textures/v2/_src/generate_painted_raws.py` (ComfyUI 8188; no use of 8199).
2. `python assets/maps/showhome/textures/v2/_src/build_v2.py`.
3. Inspect `_preview/contact_sheet.png`, `_preview/material_reference_board.png` and every `<name>_wrap.png`; each includes the matching concept crop. House wall, roof and street geometry renders are produced by build_houses.py.

Seed/prompt/reference provenance is `_src/KREA_PROVENANCE.json`. The repository helper uses its required Krea2 identity-edit adapter for `--ref`; no LoRAs are loaded for text-to-image. Reference raws are filtered to broad colour and mean-normalized; image structure is never used as geometry.

`manifest.json` is the machine-readable mapping contract. `validation.json` records dimensions, linear mean errors, seam ratios, height encoding and normal unit-length errors. Texture data and wrap tests cannot alone certify in-game parallax response; the separate game session implements height blending and sampler colour spaces.
