# Showhome v3 extension source plan

The latest revision is `2026-10-10_perpendicular_road_straight_ramp_recessed_homes`. The extension is rebuilt, exported and independently verified: 268,934 fixed triangles, 2,485 fixed convex volumes, 579 movable instances and 103 foliage volumes. Current aerial/street/courtyard/direct-ramp review renders are updated. Source and game assets retain separate fixed scenes and editable catalog placements; user-owned RON files remain preserved.

Coordinates are design-world metres: X east, Y north, Z up; glTF converts to `(x,z,-y)`. Bulk terrain remains x310..483/y685..908. Three20mm gravel entrance finish aprons cover only y681..685, outside the updated TDM clip at y670.35.

Three standalone sage/clay/sage source houses now have centres (344,700), (370,700) and (396,700),4m farther behind the public street. Equal24x44m plots stay [332,684,356,728], [358,684,382,728] and [384,684,408,728]. All three former party roof ends are capped with matching painted cladding and300mm convex gables. No attached garages are added. Side drives span xcentre+7.8..centre+11/y681..710; pickets and shrubs leave those drive mouths open. The larger front gardens have a pedestrian gate and path; rear hedges/trees retain the equal garden layout.

The6m grey gravel road is perpendicular to the X-oriented public street: constantx447, starting exactly at the northern street edgey681 and endingy847. It does not overlay the public roadway. Its complete matched gravel albedo/normal/ORM/height family uses(.58,.76,.98) neutralizing tint,1m repeat and28mm physical pebble height range. Tyre tracks retain their existing matched maps,6m repeat and32mm depth. Terrain or basement roof stays under the road, avoiding raster gaps.

The road continues directly into a single north-descending ramp, with no lateral bottom connector or U-shaped forecourt. Clear slope is [444.15,849,449.85,867], from south grade0m to north basement floor-3.2m. Excavation/roof opening is [443.85,847,450.15,873]; the bottom exit at (447,873,-3.2) is near the basement back. Shared parking extends to [339,744,451,896] to contain this direct east-wing entrance. It retains2.95m clear height, four stair/lift cores and one connected parking space. An extra column rowx438 supports the east wing while keeping the x447 route open. The source road is clipped only over the descent; no flat slab caps it.

The170x170m campus perimeter remains [310,735,480,905]. Three standing five-storey frames are [345,750,371,804], [397,750,423,804] and [345,838,371,892]; the fourth open foundation is [397,838,423,892]. Primary transform is (1093-y,x+409,z), total yaw90degrees, with copy shifts (52,0), (0,88), (52,88). Real stair/lift holes pass through GF and every upper slab. Floor levels0/3.2/6.4/9.6/12.8m and roof16m remain unchanged.

Two landscaped north/south runs occupy the central strip between west/east buildings. Six reusable organic_planter_bench units sit at x384, y765/777/789 and y853/865/877, yaw90degrees. They have curved printed-concrete walls and integrated dark timber seats. Each unit contributes three exact rotated FOL planting-pocket volumes from its metadata, using the existing leaf system without baked leaf cards. The reusable playground remains at (357,822). The superseded scattered courtyard greenbed/bench placements are removed from the source placement function.

Six broad light wheel-worn paths now use the existingworksite_mud_tracks matched maps,6m path-aligned UVs and32mm physical height data. The two previous solid mud bands are removed. Paired wheel masks and only three small wet spots keep heavy wet mud restrained. Thin14mm visual finish ribbons clip out all house/building/foundation/pit/ramp openings and retain existing terrain/deck collision. Main grey road also gains paired wheel wear through the same RGBA height contract.

Six material dropzones add23 reusable pallet/rebar/toolbox/gang-box instances with varied yaw/scale, beside the receiving yard, standing frames and exposed foundation floor. Their nominal footprints clear the protected road, ramp, stair/lift approaches and cabin stairs. Actual loose steel pipes, timberboards and concrete offcuts are three explicit deferred mesh requests in `loose_material_requests.json`; no placeholders are installed or catalog entries changed. When those exact IDs are later catalogued by an approved asset build, the extension can place them at the documented positions without starting generation itself. `source_plan_QA.json` validates the source path meshes/masks and material placement data only.

Two cranes, five trucks, seven cabins in three stacks, three matching external stairs, four portable toilets, five excavations and six convex spoil heaps remain. East-side excavations/spoil heaps move clear of the enlarged basement and direct ramp. Materials use the west yard; cabins/toilets stay northeast. The northeast upperoffice shifts1.2m west over two loweroffices, matching the latest offset-cabin reference; its stairs remain on the original lower datum and the landing route follows the shifted upperdoor. Other stacks remain aligned. Movable objects remain catalog instances in generated/proposed placements; user-owned RON files are preserved.

The latest candidate passes816 standing stair samples,746 integrated basement/access samples, both122-sample direct vehicle proxies,603 exact cabin capsule samples and all material/vehicle ground-support checks. `serialized_QA.json` and `cabin_routes_QA.json` record the results. Cabin door leaves are tested open for entry. Three requested loose-material meshes remain explicitly queued; no placeholder geometry is claimed. The game loader additionally checks the complete standing/basement route against its actual full-world collision.

Rebuild and verify from the repository root:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b --factory-startup -P assets/maps/showhome_v3/extension/build_extension.py -- --skip-props --render
python assets/maps/showhome_v3/extension/verify_extension.py
python assets/maps/showhome_v3/extension/verify_cabin_routes.py
python assets/maps/showhome_v3/extension/compare_renders.py
```

Use `--views aerial,site_aerial,site_plan,street,courtyard,ramp_access` for focused rendering. The builder exports fixed scene content only and imports movable props only for the saved authoring scene/preview. Canonical ground PBR materials keep fake users alongside preview shaders so later saved-scene exports can restore them safely. The source helpers remain import-safe; old builder main() functions are never executed. Latest supplied marks/frontage/cabin feedback are frozen under `art/briefs/showhome_v3_handoff/user_revisions/2026-10-10_tdm_and_campus/`.
