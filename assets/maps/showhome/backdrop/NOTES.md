# Showhome suburb backdrop

`build_backdrop.py` continues the existing kit and ground skirt. It loads the house builder's accumulator,
world-metre UV projection, material exporter and exact printed-concrete bead helpers, and uses
`props_lib.Prop` for the established bmesh cylinders, tubes, lattice bars and foliage clumps. It never runs
the house builder's main or replaces the existing kit. Everything is generated procedurally; no
image-to-3D or foliage cards are used.

Rebuild with Blender 5.2:

```
blender -b --factory-startup -P assets/maps/showhome/backdrop/build_backdrop.py
python assets/maps/showhome/backdrop/audit_backdrop.py
```

The `.blend` and `.glb` contain only the backdrop geometry. The render script imports the actual houses,
ground, placed props and backdrop GLBs before adding the delivered sky, specified sun and distance fog.

## Geometry and budgets

| Ring | Triangles | Meshes | Contents |
|---|---:|---:|---|
| Near | **69,774** | 6 | Three shells at different print stages, full 4 cm beads on broad close faces, scaffold rails/boards, foundation pads, survey stakes/string, printed-block pallets, dirt mounds, cement bags, rebar, cone/barrier, pickets/hedges, cypress and round young trees, poles/wires, corrugated site fence with original abstract banner |
| Mid | **25,488** | 9 | 18 completed or partial houses, pitched roofs and solar modules, continued outer streets, parked delivery truck, lights/poles/wires, trees, NE tower crane |
| Far | **12,240** | 5 | 180 very low-poly tree silhouettes, fourteen rolling hills, eighty small town masses with roof silhouettes |
| Total | **107,502** | **20** | Render only, no collision |

The crane stands at design `(117,104)`, with a 42 m tower and support mast up to about 49 m. Its lattice
members were widened after reviewing the integrated jetpack view, so the construction landmark reads
clearly from the map. The geometry budget stayed unchanged.

The Near shell plots lie at `(18,66)..(28,76)`, `(-28,20)..(-18,32)` and `(90,18)..(101,30)`. Their visible
construction stages are a low started print, ground-floor print with scaffold, and an unfinished upper
volume. Upper print returns and outward-facing openings distinguish the stages. The boundary remains
closed; no gate or opening through Showhome's hedge is suggested.

The existing ground kit supplies the roads, pavements, sand/dirt lots and transitions over
`x=-80..152`, `y=-60..110`. These surfaces are reused rather than covered with another ground mesh.
New outer road strips at `y=115..123` and `y=-74..-66` extend beyond that skirt; their pavements and kerbs
are also outside it. The far hills emerge from the existing far plane.

## Ten shared materials

Every exported mesh uses exactly one of the following materials. Every mesh has world-metre UVs and
linear `COLOR_0`. Coloured v2 surfaces receive a white multiplier. The neutral panel face sheet is the
intentional exception: Sage, Clay and crane ochre use their concept-palette linear albedo divided by
its 0.70 neutral mean. These colours export as vertex colours, with no Blender-only colour shader.

| Material | Texture family | Mapping |
|---|---|---|
| `M_SHB_Printed` | v2 `printed_concrete_layers` | 1.28 m; 4 cm bead pitch / 9 mm groove on real near faces |
| `M_SHB_Clad` | v2 `fibercement_panel` | 2.4 m; shared neutral painted faces, trims, crane and banner graphic geometry |
| `M_SHB_Roof` | v2 `roof_shingle_dark` | 2.0 m; V follows roof slope, 25 cm course strips |
| `M_SHB_Solar` | retained v1 `solar_panel` | One module per UV rectangle |
| `M_SHB_Timber` | v2 `timber_pallets` | Library repeat, world projection |
| `M_SHB_Earth` | v2 `worksite_packed_dirt` | Library repeat, world projection |
| `M_SHB_Foliage` | v2 `grass_lawn` | Muted canopy vertex tint; solid low-poly leaf masses |
| `M_SHB_Metal` | v2 `metal_scaffold_tube` | Library repeat; real corrugation geometry on site-fence backing |
| `M_SHB_Pave` | v2 `paving_slabs` | Library repeat; outer pavements and kerbs |
| `M_SHB_Asphalt` | v2 `asphalt` | Library repeat; outer road extensions |

Normal/ORM textures are linear data. Normals use OpenGL/glTF +Y. ORM.R is exported as occlusion, G as
roughness, B as metalness. All material alpha modes are **OPAQUE**; there are no alpha-blended surfaces.
The tree shapes intentionally remain solid until the separate grass/hedge/leaf technique is settled.

## Frame, clearance and exported checks

The only scene roots in the exported GLB are **`SHB_Near`, `SHB_Mid`, `SHB_Far`**. Every node uses the
identity transform. Vertex positions are metres in the design frame; Blender is X east / Y north / Z up,
and the glTF exporter writes Y-up `(x,z,-y)`. Load the GLB at the origin with no scale or rotation.

`backdrop_stats.json` records per-ring and per-mesh triangle counts, materials, bounds, UV/colour flags
and minimum distances from the play rectangle. `backdrop_validation.json` audits the actual GLB header,
root hierarchy, identity transforms, attributes, triangle counts and **262,642 exported position samples**.
The final export has **zero clearance violations**:

- Geometry stays at least 1 m outside the play rectangle / outer boundary hedge.
- Geometry within 6 m stays below 2.5 m.
- Geometry within 20 m stays below 10 m.
- Near/Mid/Far stay within 70k/35k/15k triangles, and the full backdrop is below 120k.

The outside utility lines align with the map pylon X axes, **25 and 47**. Their connection endpoints are
`(25,54.1,6.3)` and `(47,54.1,6.3)`, continuing to poles at north Y=67. Starting the high cable at Y=54.1
keeps it beyond the six-metre height restriction. The main map pylon anchors remain `(25,45.5,6.3)` and
`(47,45.5,6.3)`, supplied by the ground kit; any joining spur belongs to that kit and must be treated as
thin utility detail when considering the local boundary-height rule.

## Sun, fog, sky axes and game setup

Sun azimuth is **188 degrees clockwise from north**, elevation **54 degrees**, linear RGB
**`(1.0,0.84,0.66)`**. The direction toward the sun in design axes is approximately
`(-0.0818,-0.5821,0.8090)`; its light rays propagate along the opposite direction. Integrated look-dev
uses Blender sun energy 2.5 / environment strength 0.65; this exposure is a documented assumption rather
than an exact conversion from game lux.

Distance fog starts at **80 m**, ends at **420 m**, and uses sRGB **`(0.66,0.76,0.86)`**. Apply it to all
rings. Disable shadow casting from every `SHB_Far` descendant; both roots and mesh extras carry
`cast_shadows=false` for that ring. Keep Near/Mid shadows and ordinary opaque PBR rendering. Add no
physics or player collision to the backdrop.

Sky cubemap face order is **+X, -X, +Y, -Y, +Z, -Z in glTF/Bevy axes**. In design directions those are
east, west, up, down, south, north. The 1024 px faces form a **1024 x 6144** vertical strip in that order;
the blurred irradiance strip uses 256 px faces. The lower hemisphere uses ground haze matching the fog.
Use the delivered sky image and calibrate Skybox brightness against the look-dev environment exposure;
sky brightness is not numerically identical to Blender world strength. Sky generation prompt, seed and
image provenance are in `sky/PROMPT.md`.

Integrated images and their paired concept comparisons live in `renders/`; their manifest records the
exact exported input hashes. These views retain the collision-required east-west roof orientation,
wider street and solid terrace cover. The added suburb removes the empty horizon while leaving those
layout constraints intact. Far shapes deliberately fade into the fog instead of competing with the map.
