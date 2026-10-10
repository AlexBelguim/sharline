# Brief: Showhome kit upgrade: painted materials, roofs, ground transitions, sky and worksite (for the modeling agent)

Paste everything below the line into the modeling chat.

---

You are improving the look of "Showhome", the team deathmatch map of SHARD/LINE (repo F:\git\val etf), a stylized
extraction shooter with Valorant-like visuals.

## Start from the existing kit (do not start over)

An earlier modeling session already built a large Showhome kit in assets/maps/showhome/. Read it first and continue
from it, keeping its conventions, helpers and frames.

- **build_houses.py** -> kit/houses.blend and kit/houses.glb: the two houses. They already have:
  - sloped shingle roofs with solar panels, gutters and chimneys;
  - cladding, trims, windows, terraces and interiors.

  Renders are in kit/renders/ (houses_*_close_roof.png, houses_*_aerial.png, houses_compare_*.png and more).
- **build_ground.py**: the ground and boundaries kit.
  - It covers:
    - ground surfaces with real risers at kerbs and paths;
    - fences, hedges, arbours and pylons;
    - the truck and other brush-matched props;
    - a ground skirt outside the play area (ring roads, pavements, finished lots, sand construction plots).
  - It is meant to export kit/ground.glb and ground_alignment.json, but **kit/ground.glb does not exist yet**. Run it,
    fix what stops it, and export it.
- **build_props.py, props_lib.py, props_textures.py** -> kit/props_partial.glb and props_placed_partial.glb: the props.
  The "partial" in the names means unfinished: finish them.
- **layout/**: the game's collision layout as JSON, plus alignment checks (check_alignment.py, collision_preview,
  LAYOUT.md). The visuals must stay aligned with the collision.
- **textures/**: the texture library v1 and its README.

**Where the game is today:**
- It does NOT use this kit yet. In-game, Showhome is drawn from its collision boxes with tiled textures. See
  art/briefs/refs/ingame_today_box_roof.png: a flat box "roof" with a shingle texture, and grass that meets a dirt
  path with a hard edge.
- The game session loads houses.glb, ground.glb and the props next, aligned to the collision, so everything you
  export must be game-ready:
  - glTF Y-up in the design frame;
  - loaded at the identity transform;
  - separate meshes per material;
  - no Blender-only shader tricks for colour.

## Your jobs, in this order
1. **Painted materials and house kit upgrade:**
   - texture library v2;
   - better roofs;
   - the painted look with deep seams.
2. **Ground transitions:** kerbs (Dutch: boordsteen), edging, worn dirt and spill between surfaces.
3. **Sky and worksite backdrop:** around the map, like the concept. Extend the ground skirt you already have.

**On hold for now:** the decal atlas and the foliage cards (grass, hedge and tree leaves). The game session is
prototyping fluffy hedges, grass, bullet holes and parallax depth first to settle the technique; those follow later.

**Not your job:** game code. Do not edit anything under game/; the game session wires your files in.

Report briefly after each job.

## Look target 1: the concept art
- **Images.** Everything must look like these:
  - design/maps/tdm/concepts/_candidates/A_showhome_aerial_s11.png and _s12.png
  - design/maps/tdm/concepts/_candidates/A_showhome_ground_s11.png and _s12.png
- **Style:** the same palette, the same warm late-afternoon light, painterly stylized PBR, big clean shapes, low
  contrast, no photoreal grime.
- **How to check:**
  - Open the images first and keep them open.
  - For every texture and every render, put it side by side with the matching crop of a concept image.
  - Iterate until it matches. If a choice is unclear, the concept wins.

## Look target 2: the painted look with deep seams (the user's reference)
- **Reference:** art/briefs/refs/painted_cladding_ref.png, a close crop of the terracotta cladding. The user wants the
  houses and the main materials to have this effect.
- **Panel faces:** hand-painted, not noisy.
  - Soft broad brush strokes, running vertically.
  - Gentle mottling: slightly lighter and darker patches within a panel.
  - A soft gradient, a little lighter toward the top.
  - Each panel slightly different from its neighbours.
  - No photographic grain and no dirt.
- **Seams with real depth:**
  - Every joint is a recessed groove, about 10-15 mm wide and 8-10 mm deep.
  - The groove shows a dark shadow line; the rounded panel edge next to it catches a thin light highlight.
  - Trims stand proud of the wall: the cream top band overhangs and throws a soft shadow line onto the panels below.
- **Apply it to:**
  - the house cladding (sage and clay fibre-cement);
  - printed-concrete walls (soft painted shading on the layer beads, with real groove depth);
  - trims, sills, copings and roofs;
  - paving, kerbs, and wood boards and fences.
- **Keep it subtle at 10-30 m.** From the street it must still read as the calm concept, and get richer as you walk
  up to a wall.
- **How to get the depth:**
  - On the house meshes, model the seams as REAL geometry (inset or grooved panel edges with a small bevel). This is
    cheap on flat walls and gives true sun shadows and highlights.
  - In the tiling textures, use matching height, normal and AO maps. The game uses the height for parallax depth.
- **How to paint:**
  - Krea2 gives the painterly brush colour.
  - Exact structure comes from procedural code, so seams line up between albedo, height and geometry.
  - Add a slight per-panel value and hue shift (per-panel UV offset into a larger painted sheet, or vertex colour),
    so walls never show a repeat.

## Read first
- **art/STYLE_GUIDE.md:** the art bible, units, tools (Blender headless, tools/blender_common.py, tools/comfy_gen.py
  for Krea2) and deliverables.
- **art/DIRECTION_LOG.md**, items 10, 11 and 16:
  - near-future 3D-printed show homes in a half-built suburb with a construction crane;
  - NEVER use TRELLIS or any image-to-3D for maps; build procedurally in Blender as a kit;
  - Krea2 for stylized textures.
- **assets/maps/showhome/textures/README.md:** the v1 library rules. Keep them:
  - 1024 seamless sRGB albedo whose average matches the concept palette (_src/palette.json);
  - procedural structure with Krea2 on top;
  - OpenGL / glTF normals;
  - no baked directional light;
  - metres per repeat.
- **design/maps/tdm/src/showhome_layout.py and assets/maps/showhome/layout/LAYOUT.md:** the layout source of truth.

## Krea2 / ComfyUI
- **Where:** C:\Users\alexw\AppData\Roaming\StabilityMatrix\Packages\ComfyUI.
- **Start it if it is down:** ./venv/Scripts/python.exe main.py --listen 127.0.0.1 --port 8188
  It may already be running, because the game session uses it too; jobs queue.
- **Port 8199 is NOT ComfyUI:** never touch it.
- **Use tools/comfy_gen.py:**
  - For seamless results, pass --tileable and do NOT write "tile" or "tileable" in the prompt.
  - --ref img.png keeps a design consistent. Use --ref art/briefs/refs/painted_cladding_ref.png to steer the brush
    style.
  - Load no LoRAs for text-to-image.

## Job 1: painted materials and house kit upgrade

### A) Texture library v2
Put it in assets/maps/showhome/textures/v2/, with a README like the v1 one. For each texture the README gives:
- use;
- metres per repeat;
- tint;
- roughness;
- height range in metres.

Every tiling material gets four maps:
- `<name>.png`: albedo, sRGB, hand-painted.
- `<name>_normal.png`: linear, OpenGL / glTF convention.
- `<name>_orm.png`: linear. R = AO, G = roughness, B = metalness.
- `<name>_height.png`: 16-bit greyscale, linear, white = high. Seams are clearly recessed, and the real height range
  in metres goes in the README.

Make 2-3 variants per main surface, each with the same average colour so a mask can blend them:

| Surface | Variants |
|---|---|
| Fibre-cement cladding, sage | clean, lightly weathered (soft painted water streaks under joints) |
| Fibre-cement cladding, clay | clean, lightly weathered (soft painted water streaks under joints) |
| Printed concrete | clean, dusty near the base |
| Trims, sills, copings | one trim sheet |
| Roof shingles | clean, subtle painted lichen spots |
| Roof ridge and verge pieces | one set |
| Paving slabs | clean, weathered with moss in the joints |
| Kerb stone | one set |
| Edging strip | one set |
| Asphalt | fresh, patched (repaired squares), cracked with tar-sealed cracks |
| Grass ground | lush lawn, dry and patchy lawn, verge with weeds |
| Bare soil | garden soil, worn trodden dirt, bark mulch |
| Gravel | loose gravel, compacted gravel path |
| Worksite ground | packed dirt, mud with tyre tracks, construction sand, printed-concrete foundation slab |
| Timber | pallets, boards |
| Metal | corrugated site fencing panels, scaffold tube metal |

### B) Macro variation
- **What:** two large, soft, low-frequency greyscale breakup masks: one for the ground, one for walls. About a 32 m
  repeat.
- **Why:** the game blends them over the tiling textures, so no repeat shows from a roof.

### C) Better sloped roofs (the user asked for real texture and depth)
The houses already have sloped shingle roofs: upgrade them so they hold up close (from an upper floor, a terrace or
a jetpack jump) and read clearly from the street:
- **Shingles:** model the courses as real geometry. Use stepped rows with a visible butt thickness of about
  8-12 mm, staggered joints and a little per-shingle tilt and colour variation. Keep it light: one row strip per
  course, not separate shingles, with the stagger in the texture and height map.
- **Roof edges:**
  - ridge caps that sit on top as a rounded or angled cap row;
  - verge / barge boards along the gable edges, with a small overhang;
  - an eaves overhang with fascia board, gutter and downpipes (already there: make them proud and shadowed).
- **Joins to other parts:**
  - flashing where the roof meets the chimney and walls;
  - solar panels on visible rails with a gap and a soft shadow under them.
- **Flat roofs (garage, terrace, studio):** a real parapet or coping with a drip edge, a membrane or gravel ballast
  surface, a gutter outlet. No more box tops.
- **Material:** roof textures v2 with height maps for the game's parallax.
- **Collision:** the gable roof's collision is a steeper invisible clip (players can't stand on the 45-degree roof),
  and there is a 10 m hard ceiling. Keep the visual roof within the layout's roof planes so players never see
  themselves standing on air or sinking into tiles.

### D) House cladding, trims and printed concrete
- **Cladding:** recessed panel seams and bevelled panel edges as geometry (1.2 x 2.4 m panels, joints matching the
  textures).
- **Trims:** trims, window frames, sills, copings and the top trim band stand proud and cast soft shadows.
- **Printed concrete:** beads with real depth on the lower volumes, where players get close.
- **Panels:** per-panel colour variation.
- **Budget:** report triangles per house. Grooves on flat walls are cheap, so don't subdivide.

### E) Small mesh kit
- **What:** low-poly rocks, pebble clusters and dirt mounds, plus site props:
  - stacked printed blocks;
  - a rebar bundle;
  - cement bags;
  - a traffic cone;
  - a plastic barrier.
- **How:** with UVs, v2 materials and the painted look. Finish the props in props_partial and export the full props
  glb.

### F) Look-dev renders
Put them in v2/_preview/:
- a contact sheet;
- wrap tests;
- clay and sage walls at 1 m and 5 m next to painted_cladding_ref.png (the seams must read as deep grooves);
- a roof close-up from an upper-floor window and from a terrace;
- street and aerial views of the upgraded houses, each next to its concept image.

## Job 2: ground transitions (boordsteen and friends)
Today every ground surface meets the next one with a hard straight line. Real streets and gardens have edges and
wear between materials. Add them to build_ground.py.

### Kerbs and edging as geometry
- **Real kerb stones (boordsteen):** between road and pavement, and around the islands and the turning circle.
  - About 10-12 cm high on the road side, with a chamfered or rounded top edge, in 1 m units with visible joints.
  - Dropped kerbs at driveways and crossings.
  - A painted gully grate here and there (kit/tex/ground has gully, inspection and manhole textures).
- **Low edging strips (opsluitbanden):** between paving and lawn or beds, about 5 cm wide, flush to 3 cm proud.
- **Steel or timber edging:** where gravel meets lawn, and a gravel drip strip with steel edging along the house
  walls.
- **Collision:** the current rule keeps ground art flush within 2 cm of the flat collision ground. Kerbs may now be
  real height (up to 12 cm). Players step over that easily, but the game needs to know where they are.
  - List every kerb or edging run whose top is more than 2 cm above z 0 in kit/ground_steps.json (polyline or
    boxes, with height). The game adds matching collision steps.
  - Nothing else may rise above 2 cm without being in a collision box.

### Wear and spill between materials
Blend with masks, not hard lines:
- **Lawn edges:**
  - grass thins into worn trodden dirt along path and kerb edges;
  - more wear at corners, gates and where people would cut across.
- **Spill onto hard surfaces:**
  - gravel spilling a little onto adjacent paving;
  - sand and mud washed onto the road next to the construction plots;
  - tyre-worn mud on the verge where the truck stands.
- **Joints and beds:**
  - moss and small grass tufts in paving joints next to lawns;
  - bark mulch beds under hedges, with a soft soil edge.
- **Format the game can use.** Each ground mesh carries vertex colours COLOR_0:
  - R = worn dirt;
  - G = gravel spill;
  - B = moss or wet;
  - A = sand or mud.

  Subdivide the meshes enough near borders (about 0.25 m) for smooth masks. Blend with height-based transitions
  (use the v2 height maps), so grass ends in ragged tufts, not a straight fade.
- **Write the blend down.** Put the exact blend in ground NOTES.md: which v2 texture each channel blends toward, the
  height-blend formula and the contrast. Build the same blend in your Blender shader, so the renders show what the
  game will show; the game session implements the same blend in its ground shader.

### Renders
Street-level close-ups at 1.6 m, each next to the concept and next to art/briefs/refs/ingame_today_box_roof.png:
- a kerb with road and pavement;
- a paving / lawn edge;
- a gravel / lawn edge;
- the truck verge;
- a construction-plot edge.

## Job 3: sky and worksite backdrop
Make the world continue past the hedges, so the map reads as one finished plot in a bigger, half-built suburb, as in
the concepts:
- empty dirt plots with survey stakes and pallets;
- unfinished streets with kerbs;
- hedges and picket fences;
- more printed-concrete houses;
- power poles with sagging wires;
- the big yellow tower crane;
- tall cypress and round trees;
- a soft late-afternoon sky with a few cumulus clouds.

Build on the ground skirt you already have in build_ground.py (ring roads, lots, sand plots, far plane).

### The frame
- **Design frame:**
  - metres, with x = east (0..72), y = north (0..48), z = up;
  - origin at the south-west map corner;
  - Blender uses the same axes;
  - export glTF Y-up (Bevy = x, z, -y).
- **Play area:**
  - 72 x 48 m, mirror-symmetric about x = 36;
  - a 3 m boundary hedge with an invisible player clip above it, up to a hard ceiling at 10 m.
- **Viewpoints:** players see over the hedge from the street (eye 1.6 m), from upper floors (about 4.8 m), from roofs
  and terraces, and from jetpack jumps (up to about 9.5 m).
- **Sun:** from the south-south-west, azimuth about 188 deg, elevation about 54 deg, warm linear RGB
  (1.0, 0.84, 0.66).
- **Fog:** linear distance fog from 80 m to 420 m, colour sRGB (0.66, 0.76, 0.86).

### Sky
- **Look:** a painted late-afternoon sky in the same brush style.
  - A warm horizon fading to a soft blue zenith.
  - A few soft cumulus clouds, lit on the sun side.
  - No sun disc, birds, aircraft or text.
- **Source:** a Krea2 equirectangular panorama, 2:1, at least 4096 x 2048, with the seam blended.
- **Deliver:**
  - sky_equirect.png;
  - six faces of 1024 x 1024: sky_cube_px.png .. sky_cube_nz.png;
  - sky_cube_strip.png, a 1024 x 6144 vertical strip with faces in the order +X, -X, +Y, -Y, +Z, -Z in glTF / Bevy
    axes, ready for a Bevy Skybox;
  - sky_cube_irradiance_strip.png, blurred, with 256 px faces;
  - PROMPT.md with the prompt and seed.
- **Lower hemisphere:** a plain ground-haze colour matching the fog.

### Backdrop geometry
Render only, with no collision. Three rings outside the hedge:

- **NEAR (hedge to about 40 m):** low-poly but real 3D that holds up at 5-10 m, in v2 painted materials, with the new
  kerbs and transitions.
  - Contents:
    - the street continuing, with kerbs, footpaths and a turning circle;
    - empty plots with stakes and string lines, dirt mounds, and pallets of printed blocks;
    - two or three half-printed house shells with scaffolding, at different build stages;
    - fences, hedges (simple shapes for now) and young trees;
    - power poles with wires lining up with the map's poles;
    - a site fence with original banner graphics.
  - Constraints:
    - Nothing may look enterable or climbable from inside the map: no gaps or open gates at the hedge.
    - Everything within 6 m of the hedge stays under 2.5 m.
- **MID (about 40-150 m):** silhouettes matter more than detail.
  - more finished and half-finished houses with roofs and solar panels;
  - the tower crane as the landmark, north-east like the concept;
  - a road with a parked delivery truck and street lights.
- **FAR (about 150-600 m):** cards and very low-poly shapes that fade into the fog.
  - a tree line;
  - low rolling hills;
  - a distant town silhouette.

### Budgets and rules
- **Triangles:** about 120k for the backdrop: near 70k, mid 35k, far 15k.
- **Materials:** 10 or fewer.
- **Transparency:** alpha-masked cards only, never alpha-blended.
- **Clearance:**
  - stay at least 1 m outside the hedge;
  - nothing within 20 m of the hedge may be taller than 10 m.
- **UVs and names:** UVs on everything, and names SHB_<Ring>_<Part>.
- **Originality:** original designs only, no real logos or text, nothing copied from other games.

### Deliverables
Put them in assets/maps/showhome/backdrop/:
- **build_backdrop.py:** re-runnable in headless Blender (-b --factory-startup -P).
- **backdrop.blend.**
- **backdrop.glb:** root nodes SHB_Near, SHB_Mid and SHB_Far, in the design frame, so it is loaded at the origin.
- **sky/.**
- **renders/:** made with the houses, ground and props glbs, and the game's sun and fog. Each view sits next to its
  concept image.
  - Street level at 1.6 m from both spawns, both ways.
  - Upper-floor windows at 4.8 m, looking north, south, east and west over the hedge.
  - From 9.5 m above the map centre.
  - An aerial like the concept.
  - A contact sheet.
- **NOTES.md:**
  - triangle counts per ring;
  - materials;
  - the cubemap face order and axes;
  - the sun direction;
  - what the game side must do (e.g. no shadows from SHB_Far, Skybox brightness).

## Finish
Report, per job:
- what you made;
- triangle counts and texture list;
- the exported glbs and JSON files the game should load (houses.glb, ground.glb, ground_steps.json, the props glb,
  backdrop.glb, sky/);
- how the renders compare to the concepts and the painted reference;
- open choices for the user.
