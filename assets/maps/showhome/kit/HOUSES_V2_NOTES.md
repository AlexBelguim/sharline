# Showhome painted house kit v2

Continue `build_houses.py` from the existing kit. Rebuild with headless Blender 5.2:

```
blender -b --factory-startup -P assets/maps/showhome/build_houses.py -- --quick
```

The source derives exterior faces, openings, floors, terrace and stairs from `layout_lib`. House B remains
the exact geometric mirror of House A about x=36. All coordinates are metres in the design frame (east X,
north Y, up Z). The glTF exporter writes Y-up coordinates `(x,z,-y)`, with identity node transforms. Load
`kit/houses.glb` at the identity transform. The exported `.blend` contains source geometry before render
context objects are added.

## Geometry

- **41,654 triangles per house**, 83,308 total; 31 separate meshes per house, one material per mesh.
- Fibre cement uses a fixed **1.2 x 2.4 m panel grid**, cropped at facade boundaries and around opening trims.
  The joint is **14 mm wide**, its shadow floor is **9 mm behind** the collision plane. Panel faces stay on
  that plane. A **1.8 mm edge bevel**, 2 mm deep, catches the sun; the remaining vertical return reaches the
  recessed backing. No global subdivision is used.
- Every panel carries a deterministic per-panel UV offset into the neutral painted face sheet, value shift
  of at most 5.5%, and hue shift of at most 2.5%, through exported `COLOR_0`.
- Printed-concrete beads now match v2's **40 mm pitch** and **9 mm groove**; their crests remain on the
  collision plane. The small rounded corners retain the established kit's geometry and shading convention.
- Pitched roofs have **250 mm courses** measured up the slope, **10 mm butt thickness**, a maximum course
  per-shingle edge variation of 0.8 mm, and subtle per-course/per-shingle value variation. Each course is
  one contiguous strip across the roof, with half-bond segment boundaries and staggered joints supplied
  by the v2 maps. UV tangential projection keeps butt and height lines aligned.
- Ridge caps are 0.5 m angled segments with 3 mm joints. The barge, fascia, gutter, downpipes and chimney
  flashing are retained and refined. Roof detail stays within 20 mm relief. The chimney remains above
  the 10 m player ceiling, following the existing kit convention.
- Solar modules sit 19.5 mm above the roof plane on real rails, with a gap below the module frame.
- The garage terrace retains its deck and solid-backed opaque parapet. It now has a coping drip lip,
  wall apron, flush drain and grate. The existing unsupported 250 mm entrance canopy was reduced to a
  19 mm proud cream header, eliminating its 21 ghost hits.

## Materials and maps

Main surfaces use `textures/v2/` when present. The full painted family sheet is already coloured; it must
receive a white tint. The **neutral seam-free `fibercement_panel.png`** is the intentional exception on the
real panel meshes: its linear mean is 0.70, and vertex multipliers are concept-palette albedo / 0.70. This
avoids painting a second set of seams inside the modelled joints. `fibercement_sage` and `fibercement_clay`
remain the correctly jointed, coloured sheets for broad surfaces or the game's parallax material.

| Material | Source | Repeat / mapping |
|---|---|---|
| Panel faces and chimney | `fibercement_panel` | 2.4 m, V vertical, per-panel UV offset |
| Printed walls | `printed_concrete_layers` | 1.28 m, 32 level beads |
| Shingle roof | `roof_shingle_dark` | 2.0 m, V up slope |
| Ridge and verge caps | `roof_ridge_verge` | 2.0 m along the cap profile |
| Trims, copings, flashing | `trim_sheet_house` | preserved v1 strip UVs and 4.0 m along U |
| Paving | `paving_slabs` | 2.0 m box projection |
| Timber screens | `wood_boards_stained` | 2.0 m, V vertical |
| Interior slab | `concrete_smooth` | 2.0 m |
| Deck, oak and interior plaster | `kit/textures/` derivations | re-derived from v2 painted sources |
| Solar modules | retained `solar_panel` | one module per UV rectangle |

Normal and ORM maps are loaded as linear data. Normals use OpenGL/glTF +Y. The conventional glTF Material
Output exports ORM.R as occlusion, G as roughness, B as metalness. Materials carry the external 16-bit
height-map path in glTF extras; height maps are for the game shader and are not geometry displacement.
Colours, UVs, face normals, AO and PBR textures survive export; no Blender-only colour shader is required.

## Validation and look development

`houses_stats.json` records the actual mesh budgets and relief dimensions. `houses_validation.json` is
the successful final GLB audit: all 62 meshes have UVs/COLOR_0 and one material, all nodes use identity
transforms, all referenced external height maps exist. `alignment_houses_v2.json` is
the existing checker's 133,860-ray result. There are **zero house or house-prop GHOST/INVISIBLE mismatches**.
The full-map invisible count in that report is expected for a houses-only GLB: the checker also samples
ground, boundaries, other buildings and street props that are delivered by separate kits.

`compare_houses_v2.py` makes every requested close wall, roof, street and aerial view into a comparison
against the concept crops, and places the painted reference beside both 1 m and 5 m wall studies. Results
are in `textures/v2/_preview/house_*_compare.png` and `houses_contact_sheet.png`. Raw house images are in
`kit/renders/`. The render sun uses compass azimuth 188 degrees, elevation 54 degrees, linear RGB
`(1.0,0.84,0.66)`, with energy 2.5 and world strength 0.65. Those exposure values are a documented look-dev
assumption because the exact game lux-to-Blender mapping was not supplied. The scene uses the delivered
sky panorama when available. Real ground and props GLBs
are preferred as context; the older collision preview is only a fallback.

The layout keeps the wider street, east-west ridge and opaque terrace cover required by the collision.
Those shapes therefore differ from the tighter concept composition. The close studies isolate paint,
groove shadows and roof course depth so these can be judged independently of that layout difference.
The primary gable closeups are shaded under the specified south-south-west sun; additional south-facing
`sunlit_wall_1m` and `sunlit_wall_5m` views provide a fair sunlit comparison to the painted reference. The
own-house upper-window roof view correctly shows the fascia underside: the eave hides the pitched
surface at that viewpoint. The terrace and high roof detail views show the shingle surface and rails.

Game-side choices: retain the modelled seams for close views, and keep height/parallax strengths small on
these already modelled faces. A deeper entrance canopy or a larger solar rail clearance needs a matching
collision change; no change to the game source was made here.
