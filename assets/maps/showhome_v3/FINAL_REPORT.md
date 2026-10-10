# Current delivery

The enlarged Showhome v3 core and separate residential/worksite extension are exported and staged. Both phases passed serialized geometry, UV, texture-path, material and convex-collision checks. The 544-sample stair routes passed at the game player width/height. The original in-game Showhome and user placements are preserved.

## Core

Four attached homes; five-metre roadside garden extension with hedge returns; marked framed bush and high dark fence; blue car; reusable TDM-only concrete road/pavement barriers.

Architecture: 233,988 triangles; ground/proxy kit: 116,410. 950 fixed volumes, 197 movable instances, 22 foliage volumes, 396 raised kerb entries.

## Extension

Two attached road-facing homes plus a detached home shifted east. The connector street is removed and larger gardens fill the space. Four campus footprints share one parking basement: three standing five-storey frames and one open foundation stage. The basement extends beyond their footprints, with four stair/lift cores, a 10.08 degree vehicle ramp and visible parking beneath the foundation. The gravel haul road has iron barriers and height/normal tyre-track materials. The original crane remains, a second covers the west row, and extra trucks and three stacked worker-cabin pairs have metal stairs.

Final counts are measured in extension/report.json and parking_report.json. Independent checks cover 816 standing-floor stair samples and 757 basement/ramp/lift samples, plus 201 samples on the new office-stair asset. Render comparisons include the user sketch and supplied site references.

## Runtime files

`game/assets/maps/showhome_v3/`: houses.glb, ground.glb, collision.json, ground_steps.json, foliage.json, layout.json, ground_blend_contract.json, sky/, placements.ron (preserved), placements.proposed.ron and placements.reference.json.

`extension/`: extension.glb, collision.json, foliage.json, separate placements/proposals/reference and ground contract. `game/assets/props/catalog.json` points to the 48 reusable GLB/LOD1 prop pairs and their collision/metadata. External textures are shared, not embedded per scene.

## Texture and render comparison

Ground families sampled: asphalt, construction_sand, grass_lawn, grass_verge_weeds, gravel, gravel_compacted, paving_slabs, worksite_mud_tracks, worksite_packed_dirt, worn_dirt. Architecture/worksite/props continue the existing painted v2 cladding, printed/smooth concrete, dark shingles, roof edges, trim sheet, stained boards, pallet timber, solar panels and painted/scaffold metal. No new textures or foliage cards were required. Albedo is sRGB; normal/ORM/height linear; height white=high with metres in the v2 manifest.

The render comparisons retain the concept architecture and warm painted palette, with the user's revised four-home layout and larger gardens. The extension is more open and less densely dressed than the worksite illustration. Foliage is shown as volumes; the existing game grows the fluffy leaves/grass. Engine fog and runtime gameplay still require the loader/editor integration.

## Building mode

The engine-free building-mode foundation is implemented and tested: 17 focused tests and all 266 simulation tests passed. Placement/marker data, snapping, atomic backups, transactions/undo/redo, stable-ID proposals, SHA256 version hashing and full convex collision transforms are implemented. A read-only example successfully inspected the staged core and extension. See `game/BUILD_MODE_PROGRESS.md` for the current foundation and remaining camera/UI/runtime integration. Interactive editing and selecting v3 from the match menu are still next. Exact spawn/loot/extraction markers remain user choices; additions are proposals until accepted.

Hedge placement/resizing is now supported in the builder data model, including independent width/depth/height, yaw, duplication, locks and undo/redo. Prop uniform scaling remains 0.8-1.25. The interactive editor UI is not ready yet.

## Final campus measurements

Fixed extension kit: 271,670 triangles, 2642 closed convex volumes, 492 movable instances. Shared parking: 2.95m clear height; 757 validated basement, lift-core and ramp samples. Three standing frames have 816 tested route samples. Five trucks, six cabins, three metal stair attachments and two cranes are present in the proposed layout. All user-owned placement files are preserved.
