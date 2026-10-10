# Prompt 4: rebuild Showhome closer to the concept art (for the modelling agent)

You build maps for SHARD/LINE in Blender with scripted, reproducible Python pipelines. Krea2 (local ComfyUI) makes
the textures. You built the current Showhome kit (`assets/maps/showhome/`), and it is in the game now. **That map
stays as it is.** This job is a **new Showhome** that follows the concept art much more closely. It is built so it
can later sit inside the bigger extraction map (prompt 1). If `design/maps/extraction/LAYOUT.md` exists, follow it
for the surroundings and edges.

## Where it sits, and the order of work (read this first)

The extraction map layout is done:
- `design/maps/extraction/diagram.png`, with the Showhome inset at bottom right;
- `design/maps/extraction/LAYOUT.md`, which includes the hand-off note for this rebuild;
- `design/maps/extraction/data/extraction_layout.json`, which holds every coordinate.

The map is 1300 × 1100 m (layout v0.2) in the usual design frame: metres, x east, y north, origin at the SW corner.
Showhome is its L4 hot zone, and the TDM/FFA arena is an **80 × 60 m cut-out at x 330–410, y 620–680** (local
origin at world (330, 620), not rotated).

- **Author in the extraction map's world frame from the start.** Use the diagram's coordinates, so every later area
  lines up without moving anything. The game will load the TDM arena with an origin offset; note that in NOTES.md.
- **Phase 1: build the Showhome core first, then SAVE and DELIVER it as a playable map before anything else.**
  - Build the TDM cut-out: both houses, gardens, the street, the truck, and the clips on its four edges, as in the
    inset.
  - Deliver it as the new map id `showhome_v3`, through a deploy script into `game/assets/maps/showhome_v3/`. The
    current Showhome stays.
  - Respect the hand-off edges in LAYOUT.md: the south front street is a real through-road; the north edge has the
    back road, the Shells and Crane 1; the west edge the site office; the east edge the material yard toward the
    Road Bridge.
  - Block the 240 m sightline from the Road Bridge to the Clay house front (L8).
  - Leave one gap per side, open in extraction and clipped in TDM.
  - Add cover against the Shells looking into the back gardens.
  - Showhome faces south, toward its front street, as in the concept aerials.
- **Phase 2: the worksite ring around it** (the inset area, x 242–532, y 576–808): the Shells (a half-built row, 3
  floors and scaffold), Crane 1 and Crane 2, the site office, the material yard, the plots and pits, and the back
  road. Deliver it again so the bigger area is playable.
- **Phase 3 and on: expand outward one area at a time,** in the order the user picks. Use the concept art in
  `design/maps/extraction/concepts/` where it exists (it is being made per area); ask the user if an area has none
  yet. Each area is delivered and playable on its own before the next starts.
- **Every phase ends with:**
  - `collision.json`;
  - `placements.ron` (prop instances; the starter version only);
  - the checks;
  - renders next to the concept views;
  - a commit-ready folder.

## What you build, and what the user places in build mode

The game has an in-game **build mode** (`02_BUILD_MODE.md`). The work is split.

- **You build the kit:** what never moves.
  - terrain, roads, kerbs and edging;
  - building shells with their floors, stairs, walls, windows and doors;
  - fixed fittings such as built-in kitchens;
  - its `collision.json`.
- **You deliver the main props as movable instances** in a starter `placements.ron`: the truck, vehicles, the
  crane, site containers, greenhouses, sheds, fences, furniture, containers and planters. These are library props,
  never baked into the kit.
- **You leave to the user:** small set dressing, every loot spot and lootable flag, player spawns, extracts and
  the invisible walls. You may add a few suggested spawns marked `suggested`.
- **After hand-off `placements.ron` belongs to the user.** Never overwrite it. New or changed props go into
  `placements.proposed.ron`, and the user accepts or rejects them in build mode.

## Read first (in this order)

1. **The concept art** is the target:
   - `design/maps/tdm/concepts/_candidates/A_showhome_aerial_s11.png`
   - `design/maps/tdm/concepts/_candidates/A_showhome_aerial_s12.png`
   - `design/maps/tdm/concepts/_candidates/A_showhome_ground_s11.png`
   - `design/maps/tdm/concepts/_candidates/A_showhome_ground_s12.png`
2. **The user's in-game references**, in `art/briefs/showhome_rebuild/refs/`. Files named `good_*` are the quality
   to keep; files named `bad_*` must not happen again.
3. **The contract with the game:** `art/briefs/MAP_MATERIALS_SPEC.md`. It covers:
   - a physical material on every surface;
   - convex `COL_` collision volumes, exported as `collision.json`;
   - foliage as `FOL_` volumes that the game dresses.

   This is mandatory.
4. **The look:** `art/briefs/SHOWHOME_BACKDROP_BRIEF.md`, the painted look with deep seams, the Krea2 rules and the
   transitions. Also `art/STYLE_GUIDE.md` and `art/DIRECTION_LOG.md` (items 11 and 16–18).
5. **Your current pipeline:**
   - in `assets/maps/showhome/`: `NOTES.md` (frames, the ground blend contract), `build_houses.py`,
     `build_ground.py`, `build_props.py`, `props_lib.py`, `deploy_kit.py`, `textures/v2/`;
   - `layout/` (the alignment checks).

   Reuse what works.

## What the map is

A new housing development still being built: two finished show homes on a fresh street, in the middle of an
active worksite. It is a high-risk, high-loot zone in the extraction map and a symmetric TDM/FFA arena on its own.

- **The two houses**, one on each side of the central driveway, as in the concept:
  - the west house in sage, the east house in clay/terracotta;
  - 3D-printed concrete ground floors, cladding upper floors;
  - solar roofs with chimneys, the balcony terrace on the curved ground floor.
- **Gardens:** tall hedges around each plot, as in the concept. Behind the houses the gardens are **bigger and more
  open** than today. Each garden has:
  - a greenhouse;
  - a shed;
  - a carport at the back;
  - the raised planters and the hot tub (see `refs/`).
- **The street and centre:**
  - the moving truck in the middle with boxes and an armchair;
  - utility poles with sagging cables;
  - **an open street in front**: players are kept in by invisible `player_clip` walls at the road side, not by
    fences across the road.
- **The worksite around it**, like the concept:
  - the tower crane;
  - dug plots and foundations with rebar;
  - material stacks and pallets;
  - site office containers;
  - porta-potties;
  - skips;
  - a cement mixer truck, tipper trucks, an excavator;
  - mesh site fencing (open panels);
  - open fields beyond.
- **TDM/FFA:**
  - a playable rect of about 80 × 60 m, mirrored and fair for two teams, each starting near its own house;
  - routes through the street, the back gardens and through the houses;
  - the worksite beyond is visible and partly playable in extraction, and walled with `player_clip` for TDM.

## Interiors: not full, but real where you can see in

There is no need to furnish every room. Every room a player can see into or enter gets proper furniture:
kitchen cabinets, drawers, wardrobes, beds, a sofa, a table, bookcases, and bags or boxes from the move.

- **Furniture is modelled 3D props, never flat textures.** A bookcase has real shelves and book meshes; see
  `refs/good_dresser_BAD_flat_bookcase.png`: the dresser is good, the flat bookcase is not.
- **Loot containers** come from the set in `03_LOOT_CONTAINERS.md` (build it first, or together with this map).
  Lootable furniture shows a door or drawer slightly ajar; decor furniture stays closed. The user decides which
  containers are lootable in build mode.
- **Containers the extraction mode will open later are built openable:**
  - doors and drawers are separate meshes with their pivot in the right place;
  - name them `OPEN_DOOR_<name>` (hinged; custom properties `axis`, `min_deg`, `max_deg`) or `OPEN_DRAWER_<name>`
    (sliding; `axis`, `travel_m`);
  - put an empty `LOOT_SLOT_<n>` inside each;
  - containers include kitchen cabinets, dressers, wardrobes, desk drawers, the garage tool cabinets, duffel bags
    and toolboxes.

## Build a reusable prop library, not one-off props

Every prop goes into a shared library that other maps reuse. A prop is anything from a crate to a car, a
porta-potty or a site office.

- **Layout:** each prop lives in `assets/props/<category>/<id>/` with its `.blend` and its `.glb`.
  - **Scale:** real-world, in metres.
  - **Frame and pivot:** the design frame (Z up in Blender), with the pivot at the base centre.
  - **Variants:** LOD0, plus an LOD1 for anything over about 2k triangles.
  - **Materials:** each carries its `phys`.
  - **Collision:** the prop's own `COL_` volumes.
  - **Openable parts:** follow the convention above.
- **Catalog:** `assets/props/catalog.json` lists for each prop:
  - id, category and tags;
  - size and triangle count;
  - its openable parts;
  - its source and licence.
- **Maps place instances of library props** by id, position, rotation and an optional colour variant. Do not
  bake copies into the map. A prop must never be a flat texture of a prop.
- **Use the good references as the bar for detail:** `refs/good_wooden_crate.png`,
  `refs/good_garage_workbench_cabinets.png`, `refs/good_garage_door_half_open.png`, `refs/good_hot_tub.png`,
  `refs/good_raised_planter_box.png`.

## Use free models first, then restyle them to our look

Cars, vans, trucks, the cement mixer, the excavator, the crane, porta-potties, site containers and generic props
take long to model. **Before modelling one, search for free models you may modify:**

- **Where:** Poly Haven, Poly Pizza, Kenney, Quaternius, and Sketchfab filtered to downloadable CC0 / CC-BY. The
  Blender MCP's `search_assets` covers Poly Haven, Sketchfab and Poly Pizza.
- **Allowed licences:** CC0 or CC-BY only, with the credit recorded. Never NC, ND, "editorial" or unclear
  licences, and never models ripped from other games.
- **Restyle every one to match our kit.** That is the point:
  - simplify heavy meshes;
  - fix proportions to our chunky, readable style;
  - bevel and soften edges like our props;
  - re-UV where needed;
  - **replace all materials with our palette and our Krea2 painted textures**, including the deep seams;
  - add `phys`, `COL_` volumes and openable parts.

  A model that cannot be restyled cleanly to sit next to our houses is not used: model it yourself instead.
- **Records:** add each source to `assets/CREDITS.md` (name, author, URL, licence, what you changed) and to the
  catalog.
- **Downloads:** list the candidates for the user first (a contact sheet with the licences), if your session needs
  approval before downloading.

## Foliage: place volumes, the game grows the leaves

The user likes the game's hedges and bushes (`refs/good_hedge_on_frame.png`). **Do not model leaves or grass
blades.**

- **Hedges, bushes, climbers and tree canopies** are `FOL_` volumes, as in spec section 3b. The hedge's wooden frame
  and tree trunks are normal props.
- **Lawns** are ground with `phys = grass`. The game adds the mown fuzz and the edge tufts.

## Edges and transitions: ONE edge per boundary

`refs/bad_double_border_planter.png` has a kerb frame **and** a grass strip **and** a soft fringe all around it, so
it reads as nonsense. Every boundary between two surfaces gets exactly one treatment:

- **road ↔ pavement:** a kerb (boordsteen), and nothing else.
- **pavement ↔ lawn:** EITHER a thin flush edging strip (opsluitband) with the grass growing right up to it, OR no
  strip, with the grass slightly overgrowing the paving edge. Never a raised kerb plus a grass border.
- **planter or bed ↔ paving:** the planter's own wall is the edge. No extra kerb or grass ring around it.
- **lawn ↔ bed:** a cut spade edge or steel edging, with a slight soil lip.
- **anything ↔ worksite dirt:** a soft, worn transition from the ground blend masks, with no hard border.

Kerbs belong along roads and driveways only. Write the rule per boundary type into the ground build so it cannot
double up again.

## Fences: open and thin

`refs/bad_closed_board_fence.png` is a closed wall of boards, and it looks bad. Fences are open and thin, so you see
and shoot through them:
- white pickets with real gaps, as in the concept;
- slim steel bar fences;
- mesh site panels.

Boards are about 2 cm thick with gaps of 5–8 cm. A privacy screen, if one is ever wanted, is a deliberate exception
and gets marked as such. Gates are separate props.

## Materials, collision, gameplay sizes

Follow `MAP_MATERIALS_SPEC.md`. Highlights:
- **Materials:** `phys` on every material.
- **Walls:** interior walls are `drywall` (bullets go through with a big loss); house outer walls are `cladding` or
  `concrete` (they stop bullets).
- **Collision:** convex `COL_` volumes at real thickness; glass panes 1–2 cm.

Player sizes:
- **Capsule:** radius 0.32 m.
- **Heights:** standing 1.8 m, crouching 1.25 m, sliding 1.0 m.
- **Climbing:** step-up 0.35 m, jump 1.0 m, mantle ledges 0.6–2.2 m.
- **Slopes:** walkable up to 46°.

What that means for the build:
- **Doors and gaps:** doors at least 1.0 m wide; slide-only gaps (1.0–1.25 m) only on purpose, and listed.
- **Windows:** windows you can vault through have sills at 0.6–1.2 m.
- **Roofs:**
  - flat roofs that are perches have a way up;
  - gables are not standable (`walkable = false`);
  - there is a hard ceiling about 10 m above the street.
- **Sightlines:** avoid unbroken lines over 60 m into either spawn.

## Look and textures

- Match the concept palette and the painted, deep-seam material look from the backdrop brief.
- **Krea2:**
  - load no LoRAs;
  - for seamless textures use the `--tileable` flag of `tools/comfy_gen.py`, and never the word "tileable" in a
    prompt.
- **Lighting:** look-dev uses the same sun as `NOTES.md` (azimuth 188°, elevation 54°) and the same fog.

## Local image models for textures and depth (use them freely)

Whenever the map needs textures, trims, decals, height or depth maps, normal-map sources or painted detail, use the
LOCAL models through ComfyUI. ComfyUI runs at http://127.0.0.1:8188; never touch port 8199, a private app.

- **Krea2:** for painted albedo textures, trims, decals and concept checks.
  - Use `tools/comfy_gen.py` and load no LoRAs.
  - For seamless textures use the `--tileable` flag. Never write the word "tileable" in a prompt.
  - `--ref image.png` runs the Krea2 identity/style edit, which keeps a look consistent.
- **Qwen Image 2.1:** installed in ComfyUI (custom node pack ComfyUI-QwenImageRefPack). Use it for edits and
  variants of an existing image (e.g. a worn, wet or mossy version of a texture, or the same prop open or closed).
  Check its node inputs at http://127.0.0.1:8188/object_info.
- **Depth, height and normal maps:**
  - Derive them from the albedo with the depth estimator that ComfyUI has installed (comfyui-depthanythingv2), or
    bake them from real geometry in Blender.
  - Height maps are 16-bit, white = high. The game's depth convention is in the material and NOTES docs.
- **GPU etiquette:** other agents share this GPU.
  - Before a batch, wait until this file does not exist:
    `C:/Users/alexw/AppData/Local/Temp/claude/F--git-val-etf/2097aa01-5216-40bf-b3f2-abfa2a86e2fa/scratchpad/slots/gpu_busy`.
    Then create it.
  - Keep batches short, and delete the flag after.
  - If ComfyUI stops answering, tell the user rather than restarting it yourself.

## Lessons from the last kit (the game-side review found these)

- **Images:** reference them externally and share them between scene GLBs. Do not embed a copy per GLB: the last
  kit loaded 43 images 2–4 times.
- **Deploy:** ship only the textures the game samples. Pack only the ground array layers the shader uses: 23 of 39
  layers were never sampled.
- **Mips:** prefer mipped KTX2 so the game does not build mips at load.
- **Sky:** the sky cube strip must be left-handed for Bevy (+Z = north, as the game expects), or say clearly that it
  is not.
- **Material tints** belong in the blend contract, not only in glTF base colours.

## Steps inside each delivery (show the user the step-0 plan before building Phase 1)

0. **Plan.**
   - A top-view layout sketch over the concept aerial, with the TDM rect, both houses, the gardens, the street,
     the worksite and the player clips.
   - A prop list: id, category, the free source found (with licence) or "model", and openable parts.
   - The boundary types and their edge treatment.
1. **Prop library.** Start with the props this map needs most: furniture and containers, garden props, fences and
   gates, vehicles, worksite props.
2. **Blockout and collision.**
   - Houses and grounds with `COL_` volumes, `FOL_` volumes and the clips.
   - `collision.json` and the material debug view.
   - Check walkability and every opening's clearance.
3. **Art pass:** materials, textures, trims, edges, set dressing, the backdrop and the sky.
4. **Checks and hand-off.**
   - The export checks from the spec.
   - An alignment check: art against collision.
   - Renders next to each concept view: the aerial, the street at 1.6 m eye height, a garden and an interior.
   - A prop contact sheet.
   - `NOTES.md` covering the frames, the contracts and what the game must do. The likely game work: loading
     `collision.json`, prop instances and openables, and foliage volumes for rounded shapes. Build mode handles
     placements.
   - A deploy script that writes the kit to `game/assets/maps/showhome_v3/`, plus the starter `placements.ron` the
     first time only. That is a new map id; the current Showhome keeps working.
