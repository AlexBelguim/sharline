# Showhome v2 handoff

The existing kit remains in the design frame: metres, X east, Y north, Z up,
origin at the south-west play-area corner. glTF is Y-up `(x,z,-y)`. Load scenes
at identity; do not centre, rotate, or rescale them.

## Scene ownership

- `kit/houses.glb`: both houses and their original interior furnishings.
- `kit/ground.glb`: ground, the existing skirt and boundaries, truck, delivery
  pods, fences, hedges, arbours, pylons and utility cable.
- `kit/props_placed.glb`: other placed fixtures and the completed secondary
  structures. `kit/props.glb` is a reusable local-origin library, not another
  map scene. Loading the library as a scene duplicates assets at the origin.
- `kit/props_placements.json` records owners. Ground and house placements are
  excluded from the placed-props scene.

## Ground geometry and collision

Ground surfaces remain at 0–16 mm. Kerb stones stand 110 mm above road level,
with chamfered tops, short end joints and nominal 1 m units. Gate crossings
and the delivery-pod bay have 16 mm dropped units. Paving restraint strips
are 50 mm wide and 28 mm high. Steel gravel restraints stand 18 mm high.

`kit/ground_steps.json` lists every emitted unit exceeding 20 mm: 344 units
inside the playable rectangle, plus render-only skirt units. Each has design
frame AABB bounds, an exact footprint polygon, width and top height. Apply
only `collision_required: true` rows to movement collision. Curved kerbs have
quad footprints, rather than an imaginary solid full turning-circle disk.
Chamfers and narrow joints are decorative relief within the step tolerance.
Existing outside-play dirt mounds remain render only.

The rebuilt ground has 370,702 instanced triangles, including its boundaries,
vehicles and 139,632 triangles of skirt. Playable surfaces and near borders
carry 25 cm interpolation vertices; outer interiors are coarser.

## Exact ground blend

The ground shader must treat `COLOR_0` as **linear independent RGBA masks**,
with opacity fixed at one. It is neither an albedo multiplier nor alpha.
All exported ground surface meshes carry actual RGBA, checked in the GLB.
Props and wall meshes retain their ordinary vertex colour/AO convention.

Start with the base texture sampled using UV0. UV0 already includes the
paving origin and east-side mirror. Overlay textures sample design world
XY divided by their metre repeat; in Bevy this is `(world.x,-world.z)`.
Apply channels sequentially in the order R, G, B, A:

| Channel | Target | Repeat |
|---|---|---:|
| R | `worn_dirt` | 1 m |
| G | `gravel` | 1 m |
| B, hard surfaces/lawn | `grass_verge_weeds` (moss colour) | 2 m |
| B, earth | `worksite_mud_tracks` (wet) | 6 m |
| A, hard surfaces | `construction_sand` | 6 m |
| A, lawn/earth | `worksite_mud_tracks` | 6 m |

Convert white-is-high height to metres using the v2 manifest range. For each
layer with mask `m`, current physical height `H0`, and incoming height `H1`:

```text
d = m + 0.18 * (H1 - H0) / 0.020
t = clamp((d - 0.25) / 0.50, 0, 1)
w = t * t * (3 - 2 * t)
if m <= 0: w = 0
if m >= 1: w = 1
albedo = mix(albedo, incoming_albedo, w)
height = mix(height, H1, w)
ORM = mix(ORM, incoming_ORM, w)
normal = normalize(mix(normal, incoming_normal, w))
```

Transition contrast is 2.0; ORM contrast remains 1.0. Transform all normals
into the same frame before mixing. Base normals use the UV0 tangent frame;
ground overlays use design XYZ. Finally multiply albedo by
`1 + 0.12 * (macro_ground(worldXY / 32) - 0.5)`.

`ground_blend.py` builds this same graph for Blender and preserves canonical
PBR materials for export. `kit/ground_blend_contract.json` gives the full
machine-readable texture/repeat/height contract and is stored in material
extras. Standard glTF viewers will multiply the mask as colour; the game
must select the ground shader from this metadata. Colour is supplied by
ordinary v2 sRGB albedo files, not Blender procedural colour.

Masks thin lawns into dirt, intensify at gates/corners, spill gravel onto
paving, place moss beside lawns, wash sand onto worksite streets and drag
mud along the truck approach. Bare hedge beds use bark mulch. Grass/hedge/
tree foliage cards and the decal atlas remain on hold.

## Verification and comparisons

`verify_kit.py` audits serialized GLBs for UVs, normals, material separation
and actual mask values. `check_assembled.py` tests the identity-loaded three
scenes against the unchanged layout plus the registered steps. The current
133,860-ray audit has zero invisible faces and zero actionable mismatches:
five deliberate thin utility-cable hits and six tangent truck-edge samples
are documented; the latter were verified again 1 mm inward on the perch.

`kit/renders/ground/v2/contact_sheet.png` contains five street-level 1.6 m
studies beside appropriate concept crops and the current-game reference.
Kerbs and joints now have true side faces and sun shadows. Broad painted
colour remains calm; grass geometry detail is intentionally pending the
foliage technique. House panels retain real depth and the concept palette.

Lighting in all v2 studies: compass azimuth 188 degrees, elevation 54,
linear sun colour `(1,.84,.66)`, Blender sun energy 2.5 and sky strength .65.
The latter two are look-development settings, not a claim about game lux.
Linear distance fog runs from 80 to 420 m, colour sRGB `(.66,.76,.86)`.
