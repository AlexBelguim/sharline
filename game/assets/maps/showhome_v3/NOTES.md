# Showhome v3 core and extension

The TDM core has four homes in two attached sage/clay blocks, mirrored across the two-lane driveway. The existing Showhome remains unchanged. World metres use X east, Y north, Z up; map origin (330,620,0), glTF Bevy=(x,z,-y), TDM offset=(-330,0,+620).

## Latest core layout

The north roadside gardens extend another 5m to y671. The public cross-street is y673-681, with a continuous 2m pavement. The visual kit covers x330-410/y620-685; the playable TDM core ends at y670.35. Side and back hedges are continuous6m volumes. Six concrete barriers span x364.15-375.85, centred at y670.35, aligned with the roadside hedge returns. The public street remains open beyond the TDM closure.

Attached garages serve the north homes, y656.85-663, facing the driveway with the house doors. South standalone garages at y626.9 face north. Garage terraces use 15mm clear glass and dark timber privacy screens. All street upper windows match; each garden facade has one matching full window per floor. Main buildings share 300mm concrete party walls at y645; roofs are not walkable. Hard TDM ceiling is 10m.

The truck body is centred in the drive with an 8-degree skew. The user-marked square holds a blue city car. The marked south sage garden has a large framed hedge next to its gable; the clay garden has a 2.2m dark privacy fence. Garden dividers have nearly solid 20mm boards and open gates. Different gardens keep their own greenhouse, shed, patio and planter arrangements.

Only the six aligned entrance barriers remain; obsolete barriers across the public road are removed. Each barrier has mode=tdm and exact concrete collision. Exclude them in extraction mode. Player clips remain separate editable markers, not fixed art collision. There are121 proposed movable instances; the existing user placements remain preserved.

## Ownership and files

- kit/houses.glb and kit/ground.glb: fixed architecture/terrain, UVs, per-material meshes and physical material extras.
- collision.json: fixed convex collision only, world design axes, inside dot(n,p)<=d.
- kit/ground_steps.json: existing kerbs included in collision.json; do not add them twice.
- kit/foliage.json: volumes for the game's existing bushes/hedges; FOL meshes are preview silhouettes, not final leaves.
- placements.ron: user-owned, preserved. New changes are in placements.proposed.ron and placements.generated.json; runtime deployment names the JSON placements.reference.json.
- assets/props/catalog.json: reusable props, GLB/LOD1, real size, physical materials, convex collision and openable pivots.
- QA.json and phase1_report.json: measured export and alignment checks.
- extension/: separately loadable surrounding residential/worksite kit and its collision/placements; built after the TDM core.

After handoff, builders and deploy never overwrite placements.ron. Build mode must show per-item proposal ghosts and allow accept/reject. Mode defaults to all if absent. The blue city_car colour variant replaces only M_CarSilver with linear RGB (.045,.19,.34), leaving wheels, glass and lamps unchanged.

## Collision and containers

Internal house partitions are 200mm drywall, printed outer walls concrete, cladding cladding, terrace glass 15mm glass, shutters 10mm sheet_metal. Garage shutter clearance 1.1m is intentionally slide-only, not crouch/standing. Follow convex planes for entry/exit thickness rather than AABB depth. Moving collision follows its OPEN parent.

Containers keep OPEN_DOOR/OPEN_DRAWER/OPEN_LID pivots, axis/limits, closed locations and LOOT_SLOT empties. Lootable containers preview ajar; decor containers closed. Structural garden gates keep their authored open pose. Exact loot, spawns, extracts and final clips remain editable user choices.

## Ground contract and textures

COLOR_0 is independent linear RGBA masks, not albedo or opacity: R=worn_dirt, G=gravel, B=grass_verge_weeds (hard/lawn) or wet worksite_mud_tracks (earth), A=construction_sand (hard) or mud_tracks (lawn/earth). Blend sequentially R,G,B,A:

    d=m+0.18*(H1-H0)/0.020
    t=clamp((d-0.25)/0.50,0,1)
    w=t*t*(3-2*t); force w=0 for m<=0, w=1 for m>=1
    mix albedo,height,ORM by w; normalize mixed world-space normals

Contrast 2.0; macro multiplier 1+0.12*(macro_ground(worldXY/32)-0.5). Ground UV0 already contains metre repeats; overlay XY uses design world XY or Bevy(world.x,-world.z). ground_blend_contract.json is authoritative; Blender uses the same preview graph. Generic glTF viewers multiply vertex colour and therefore show these masks incorrectly.

Textures reuse the existing Krea2-painted v2 library: seamless sRGB albedo, linear OpenGL normal/ORM, 16-bit linear height white=high; material extras/manifest give repeat metres and height range. Images are shared externally by content hash and deployment stages sampled layers only. No new AI mesh, leaf cards or grass blades are authored.

## Look development

Use concept_showhome for the core and concept_worksite for its surroundings. The warm painted palette, printed beads, cladding grooves and stepped shingles continue the v2 kit. FOL volumes show intended bush locations; final fluffy leaves/grass depend on the existing game shader. Saved renders compare to the supplied concepts and painted cladding reference. These Blender renders do not prove runtime gameplay or final engine fog.

Sun azimuth188/elevation54, linear RGB(1,.84,.66); fog80-420m, sRGB(.66,.76,.86). Existing sky order +X,-X,+Y,-Y,+Z,-Z uses east,west,up,down,south,north; its strip is right-handed and needs the existing Bevy mirror-Z adapter.

## Extension and build mode order

After the core: three standalone road-facing houses with equal gardens, visible pebble drives and a larger front setback. Three five-storey frames and an open foundation share parking, with stairs reaching the first two upper floors. The latest revision calls for a perpendicular gravel junction, straight basement descent near its back and organic printed-concrete planters with integrated benches. These extension revisions are separate from the prioritized playable TDM core.

The user authorized building mode code on 2026-10-09 after completing the core and extension. Follow art/briefs/showhome_rebuild/02_BUILD_MODE.md and the existing game's foliage/depth/audio/decals systems. Runtime wiring is separately validated; until then, the exported kit is an asset handoff.

## Rebuild

Blender5.2 headless: build_library.py (or --only id), build_houses.py, build_core.py --render; python verify.py; render_final_views.py and compare_renders.py; python deploy.py. Original helpers are loaded without running their old main().
