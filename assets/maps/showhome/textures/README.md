# Showhome texture library

The textures for the TDM map **Showhome** (theme A in `art/DIRECTION_LOG.md`, item 10). They are matched to the concept
art in `design/maps/tdm/concepts/_candidates/A_showhome_*.png`: a warm late-afternoon light and a painterly
stylized PBR look with big clean shapes, low contrast and no photoreal grime.

- Tiling textures are **1024 x 1024**, seamless in both directions and sRGB (8-bit PNG). `glass_frost.png` is
  the only RGBA texture.
- `*_normal.png` and `trim_sheet_house_orm.png` are **linear data**, not colour. Normal maps use the OpenGL / glTF
  convention: +X right and +Y toward the top of the image. Bevy and the glTF exporter expect this convention.
- Each albedo's **average linear reflectance equals the palette albedo** sampled from the concept
  (`_src/palette.json`). A material that shows the texture untinted therefore averages to the colour the concept
  shows under a warm sun of about (1.0, 0.84, 0.66). Do not add a second warm tint in the material.
- All structure is procedural, so its lines are exact, level and evenly spaced. This covers the printed-concrete
  beads, slab, kerb and panel joints, shingles, solar cells and the trim sheet. Krea2 raws contribute only the
  painterly grain and mottling on top.
- No texture has baked directional light. Some carry a small cavity darkening in joints and grooves, which is
  painted AO only.

`_src/preview/_contact_sheet.png` shows every albedo. `_src/preview/<name>_wrap.png` shows a 2 x 2 wrap test next
to a copy with 3x the contrast. `_src/preview/lookdev_aerial.png` and `lookdev_street.png` show the library
applied at the scales below, in Blender under the warm sun. `_src/preview/palette_samples.png` shows every
concept box the palette was sampled from.

## Mapping conventions (read before UV-ing)

- **UV scale is metres per repeat.** One UV unit covers that many metres, so UV = world_metres / repeat_m.
  World-space box projection is fine for every tiling texture.
- **Walls: V follows world up** (image top = up). This matters for `printed_concrete_layers`, where the beads must
  run horizontally, and for `fibercement_*` (vertical streaks, 2.4 m tall panels), `picket_wood_white`,
  `wood_boards_stained` and `metal_painted_yellow`, whose grain or streaks run along V.
- **Roof: V runs up the slope** (image top = ridge), because each shingle course has its thick butt edge at the
  bottom.
- **Long thin parts** (kerbs, frames, gutters, sills, copings): U runs along the part.
- Coordinate frames: the layout and Blender are Z-up (x east, y north). Bevy is Y-up with bevy = (x, z, -y). The
  glTF exporter converts the frame and flips V for you. UV rectangles are given in both conventions in
  `trims.json`.
- **Bevy sampler:** Bevy's default sampler clamps to edge. Tiling textures need `AddressMode::Repeat` on U and V.
  A glTF exported from Blender carries a REPEAT sampler, which Bevy's glTF loader honours. For textures loaded by
  hand, set `ImageLoaderSettings { sampler: ImageSampler::Descriptor(ImageSamplerDescriptor { address_mode_u:
  Repeat, address_mode_v: Repeat, ..linear() }), .. }`. Load the `_normal` and `_orm` maps with `is_srgb: false`.
- Tints below are **linear RGB multipliers** for `base_color` in Bevy (`Color::linear_rgb(..)`) or a Multiply
  node in Blender. "none" means use white, because the texture is already in its final colour.

## Textures

| File | Use | Repeat (m) | Tint (linear) | Extra maps / notes |
|---|---|---|---|---|
| `printed_concrete_layers.png` | Cream 3D-printed walls: curved lower volumes, towers, parapets | **1.28** (32 beads = 4 cm each); 1.0 to 1.6 is fine | none (cream, sRGB 214 200 176) | `printed_concrete_layers_normal.png` (strength 1). Roughness 0.8. The beads are perfectly level and evenly spaced. On curved volumes run U around the perimeter (cylindrical) and V up. Never rotate it. |
| `fibercement_sage.png` | Sage fibre-cement cladding (house A), with joints | **4.8** (4 x 2 panels of 1.2 x 2.4 m) | none | `fibercement_panel_joints_normal.png`. Roughness 0.65. Joints sit at U 0.125 + k·0.25 and V 0.25 / 0.75. Align the UV offset to the facade edges. |
| `fibercement_clay.png` | Terracotta / clay fibre-cement cladding (house B), with joints | **4.8** | none | As sage. |
| `fibercement_panel_joints.png` | Neutral grey jointed cladding for any other colour | **4.8** | multiply by target_linear / 0.70 (see palette below) | Linear mean 0.66, panel faces 0.70. Same normal map as above. |
| `fibercement_panel.png` | Neutral grey board without joints, for tinting (chimneys, soffits, panel infills, sheds, other houses) | **2.4** | sage `(0.405, 0.454, 0.241)`, clay `(0.892, 0.340, 0.165)`, chimney sage `(0.331, 0.419, 0.284)`, chimney clay `(0.723, 0.270, 0.169)` | Linear mean exactly 0.70 grey with faint vertical streaks. |
| `roof_shingle_dark.png` | Dark charcoal pitched roofs | **2.0** (50 x 25 cm shingles, half bond) | none | `roof_shingle_dark_normal.png`. Roughness 0.7. Image top = toward the ridge. |
| `solar_panel.png` | One solar module (6 x 10 cells, dark frame) | **not tiling per metre:** 0–1 UV = one 1.0 x 1.65 m module, U on the short side | none | Roughness 0.25 (a small specular sheen sells it). Repeat the UV per module to make an array. Frame edges: trim strip `solar_frame`. |
| `asphalt.png` | Street and car-park asphalt | **4.0** | none | Roughness 0.85. No markings: model the yellow centre / edge lines and kerb paint as separate decals. |
| `asphalt_cracked.png` | Older asphalt: patches near kerbs, the half-built-plot road, under the truck | **4.0** | none | Same base as `asphalt` (1.5 % darker) so the two blend: mask between them with vertex colour. |
| `paving_slabs.png` | Pavements, front paths, terrace floors | **2.4** (0.6 m slabs) | none | `paving_slabs_normal.png`. Roughness 0.8. Joints at U/V 0.125 + k·0.25 (the wrap edges fall mid-slab). |
| `kerb_concrete.png` | Kerb stones, path edging, low concrete steps | **2.0** along U (1 m kerb units) | none | Roughness 0.8. Joints at U 0.25 / 0.75. U along the kerb. |
| `grass_lawn.png` | Lawns and verge strips | **2.0** | none | Roughness 0.9. For big lawns, break the repeat with a 0.9–1.1 vertex-colour value variation. |
| `hedge_leaves.png` | Clipped hedges (box shapes with soft bevels) | **1.5** (1.5–2.0) | none | Roughness 0.85. Deeper green than the lawn. Use a darker vertex colour (about 0.75) toward the bottom and inside corners. |
| `picket_wood_white.png` | White picket fences, rails, gates | **1.0** | none | Roughness 0.6. Grain runs along V: map V along each picket. |
| `garden_soil.png` | Flower beds, planters, greenhouse beds | **1.0** | none | Roughness 0.95. |
| `construction_sand.png` | Half-built plots, earth mounds, site roads (out of bounds) | **4.0–6.0** (6 for the large plots) | none | Roughness 0.95. Fully procedural with no stamp features. Break up the large areas with vertex colour, and with `gravel` / `garden_soil` patches. |
| `gravel.png` | Gravel drives, site paths, rail beds | **1.0** | none | Roughness 0.9. |
| `cardboard.png` | Plain kraft cardboard (tiling): flattened boxes, tubes | **1.0** | none | Roughness 0.85. |
| `cardboard_box_face.png` | **Not tiling:** one box face per 0–1 UV square (the spilled delivery boxes) | per face | none | A flap seam runs under brown packing tape across the middle, with slightly worn edges. Apply it to every face. |
| `truck_paint_white.png` | White box truck body and cab, other white painted metal (utility cabinet, bins) | **3.0** | none | Roughness 0.4 (the cab can go to 0.3). Paint the details in other materials: lights, tyres, glass. |
| `metal_painted_yellow.png` | Yellow construction crane, site barriers, skips | **2.0** | none | Roughness 0.5, metallic 0. V along each member. It has faint vertical weathering and a few small chips. |
| `glass_frost.png` | Greenhouse glass (domed), glass railings | **1.5** | none | **RGBA**: alpha 0.20–0.45 (smudges are a little more opaque). Use alpha blend, roughness 0.1. For house windows, tint it about `(0.15, 0.17, 0.2)` with alpha forced to 1, or use a dark glass material with interiors behind. |
| `concrete_smooth.png` | Plain cast concrete: carports, utility poles, site blocks, terrace soffits | **2.0** | none | Roughness 0.8. |
| `wood_boards_stained.png` | Brown stained vertical boards: garden sheds, rear fences | **2.0** | none | Roughness 0.8. Grain along V. |

### Trim sheet: `trim_sheet_house.png` (2048 x 1024)

The trim sheet is procedural and has three maps: albedo `trim_sheet_house.png` (sRGB), `trim_sheet_house_normal.png`
(linear) and `trim_sheet_house_orm.png` (linear: R = occlusion, G = roughness, B = metallic). The ORM packing is
the glTF / Bevy layout, so the same image goes into `metallic_roughness_texture` and `occlusion_texture`.

- Every strip spans the full width and **tiles along U**. Map a part's long axis to U and its profile across the
  strip's V range.
- Texel density is **512 px/m**, so U repeat = **4.0 m**. A strip of h px is drawn for a profile h/512 m wide.
  Scale V to fit other widths.
- `trims.json` holds the exact rectangles in pixels, in `uv_gltf` (V down, glTF / Bevy) and in `uv_blender`
  (V up), along with the use, profile width, roughness and metallic of each strip.
- Inset each strip's V range by about 2 px (0.002) from its edges, so mips do not bleed the neighbouring strip.

| Strip | px rows | Use |
|---|---|---|
| `window_frame_dark` | 0–64 | Dark aluminium window frames and mullions |
| `window_frame_cream` | 64–128 | Cream glazing frames inside the big window surrounds |
| `window_surround_cream` | 128–256 | Deep (25 cm) cream window surrounds / reveals |
| `door_frame_cream` | 256–320 | Door frames, architraves, door canopy edge |
| `sill_cream` | 320–384 | Sills and ledges (top, rounded nose, drip groove) |
| `coping_cream` | 384–480 | Rounded coping on printed parapets / terrace walls, chimney caps |
| `gutter_dark` | 480–544 | Half-round gutters; wrapped around a cylinder for downpipes |
| `fascia_dark` | 544–640 | Fascia / barge boards along eaves and gables |
| `railing_cap_steel` | 640–672 | Brushed steel handrail cap and glass-railing clamps (metallic) |
| `vent_louvre` | 672–800 | Wall vents / AC grilles (frame them with `window_frame_dark`) |
| `garage_door_slats` | 800–928 | Garage / carport store doors, dark wood-look slats |
| `solar_frame` | 928–960 | Solar module frames, roof-window frames (anodised) |
| `flashing_dark` | 960–992 | Flashing around chimneys and roof edges, ridge capping |
| `seal_rubber` | 992–1008 | Gaskets / glazing seals |
| `plain_dark` | 1008–1024 | Flat dark for tiny parts (hinges, bolts) |

## Palette (albedo sRGB, from `_src/palette.json`)

These values are for materials that need a flat colour without a texture, such as props, trees and doors. Use the
`albedo_linear` values from `palette.json` in Bevy and Blender.

| Material | sRGB | Material | sRGB |
|---|---|---|---|
| printed concrete (cream) | 214 200 176 | truck white | 231 223 218 |
| fibre-cement sage | 145 153 114 | crane yellow | 206 148 62 |
| fibre-cement clay | 207 134 96 | trim cream | 221 211 191 |
| roof charcoal | 86 79 80 | frame dark | 54 49 54 |
| solar cell | 42 47 72 | door sage | 66 73 70 |
| asphalt | 112 105 106 | door clay | 84 52 53 |
| paving | 175 162 154 | pole concrete | 178 165 158 |
| kerb | 159 147 141 | chimney clay | 188 120 97 |
| grass | 126 140 58 | chimney sage | 132 147 123 |
| hedge | 98 112 52 | shed wood | 83 72 66 |
| picket white | 226 219 205 | tree canopy (round trees / cypress) | 89 89 37 |
| garden soil | 96 74 56 | cardboard | 208 164 118 |
| construction sand | 197 168 141 | gravel | 173 153 137 |

How the palette was made: boxes on sun-lit parts of each material in the four concept images were averaged. Half
of the sun's warm cast, measured on the truck roof, was then removed, and the exposure was set so that truck white
= 0.80 linear. Overrides, each with its reason in `_src/sample_palette.py`, cover clipped or polluted samples. They
also cover the **grass, hedge, asphalt and roof** values, which were corrected after the look-dev render:

- The sampled greens read as mustard under a warm sun, so their hue was moved toward green at the same luminance.
- The sampled asphalt read as brown dirt, so it is now a darker, slightly violet grey.
- The sampled roof included its bright edges, so it is now a dark charcoal.

The tree canopy value is still the raw sample. If trees read khaki next to the corrected lawn, give them the same
green shift (about `98 108 44`).

## Rebuilding (every step is a re-runnable script; run from `_src/`)

1. `python gen_raw.py [name ...] [--seeds 11 12] [--force]`: Krea2 raws through local ComfyUI (127.0.0.1:8188)
   into `_src/raw/`. Existing files are skipped. The raws are generated **non-tiling**: the build makes them
   seamless with an offset cross-fade or a minimum-error boundary cut, and the printed seam ratio stays at or below
   about 1.0. Prompts describe only the surface and never say "tile".
2. `python sample_palette.py`: writes `palette.json` and `preview/palette_samples.png`.
3. `python build_textures.py [name ...]`: builds every texture (or the named builders). It prints the seam ratio
   and checks the mean against the palette, then writes the wrap previews and the contact sheet. The log of the
   last full run is `_src/_rebuild_log.txt`.
4. `python make_trim_sheet.py`: writes the trim sheet (3 maps), `trims.json` and `preview/trim_sheet_labelled.png`.
5. `"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P preview_render.py`:
   renders the look-dev vignette. This is a texture check, not the map.

Raw sources used by the build:

| Texture | Raw source |
|---|---|
| fibre-cement | `fibercement_s11` |
| asphalt | `asphalt_s12` |
| cracks | `asphalt_cracked_v2_s12` |
| grass | `grass_s12` |
| hedge | `hedge_s11`, cropped |
| picket | `picket_wood_s11` |
| soil | `soil_s12` |
| gravel | `gravel_s11` |
| cardboard | `cardboard_s11` |
| truck | `white_paint_s12` |
| crane | `yellow_paint_s12`, fine grain only |
| glass | `glass_smudge_s11` |
| shed wood | `wood_boards_s13` |
| painterly grain on concrete, roof and paving | `concrete_smooth_s11` / `s12` |

Sand, solar panel and the trim sheet are 100 % procedural. Every Krea2 sand raw had big round blotches that
stamped a grid over the plots, so no sand raw is used.
