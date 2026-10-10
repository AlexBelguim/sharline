# Prompt 2: an in-game BUILD MODE (game code, before the map rebuild)

This is for the game programmer (Rust + Bevy 0.19, code in `game/`). It is not a modelling job. The goal is to split
map making between the modelling agent and the user:

- **The modelling agent** builds what does not move: terrain, roads, kerbs, building shells and fixed fittings, and
  it delivers the main props as **movable instances**.
- **The user, in a build mode inside the game,** does the rest:
  - moves, rotates, deletes and adds props from the shared prop library;
  - sets every **loot spot**, **player spawn** and **extract**;
  - places invisible walls.

The user sees exactly what players see (lighting, foliage, collision) and can jump straight into a playtest. They
need no Blender.

## Prerequisites (build these first if they are not in the game yet)

- **The physical material and collision contract,** `art/briefs/MAP_MATERIALS_SPEC.md`:
  - `materials.ron`;
  - loading `collision.json` into the simulation's level;
  - `phys` on every surface.
- **The prop library at runtime:**
  - read `assets/props/catalog.json`;
  - load a prop's GLB and its `COL_` volumes (with `phys`) as one instance;
  - openable parts (`OPEN_DOOR_` / `OPEN_DRAWER_` / `OPEN_LID_`) and `LOOT_SLOT_` empties are known to the
    game, in the closed, ajar and open poses (see `03_LOOT_CONTAINERS.md`).

## The data: kit + placements (who owns what)

A map folder `game/assets/maps/<map>/` holds:

- **The kit:**
  - the static scene GLBs and `collision.json`;
  - owned by the modelling agent;
  - never edited in build mode.
- **`placements.ron`**, the editable layer, owned by the user once it has been handed over. Everything in it has a
  stable id:
  - **prop instances:** prop id, position, rotation (yaw plus an optional tilt), uniform scale (default 1, limited
    to 0.8–1.25), colour variant, a `lootable` override for containers, and a `locked` flag;
  - **loot spots:**
    - either a container instance with lootable on;
    - or a loose-loot point: a position, a loot table / tier, a spawn chance and a max count.
  - **player spawns:** mode (TDM team A/B, FFA, extraction), facing, group;
  - **extracts:** shape and radius, kind (always, timed, conditional, paid) and its parameters, a name;
  - **invisible walls:** `player_clip` boxes;
  - later, AI spawns.
- **`placements.proposed.ron`**, optional. When the modelling agent adds or changes props after hand-off, it writes
  them here and never touches `placements.ron`. Build mode shows the proposals as ghosts so the user can accept or
  reject each.
- **Multiplayer:** a hash of the kit plus `placements.ron` goes into the join handshake. A client with a different
  map version is refused with a clear message.

## Features (first version)

- **Enter and leave:**
  - `--build <map>` from the command line, and a BUILD button on the main menu (behind a setting, so it is hidden
    in builds sent to friends);
  - you can flip from editing into play and back with one key (Play from here).
- **Camera:** free-fly (WASD, Space/C for up and down, Shift to go faster, the mouse to look), with a grid overlay
  that can be toggled.
- **Prop browser:**
  - a panel listing the catalog by category with search;
  - thumbnails rendered from the props once and cached;
  - favourites and recently used.
- **Placing:**
  - the prop follows the cursor and snaps to the surface under it (aligned to the ground, or upright);
  - a grid snap (0.25 / 0.5 / 1 m) and an angle snap (15° / 45° / 90°), each toggleable;
  - hold a key to place several.
- **Editing:**
  - select by click or box, with multi-select;
  - move, rotate and scale with a simple gizmo or keyboard nudges (arrows, PgUp/PgDn);
  - duplicate, copy/paste and delete;
  - drop to the ground;
  - lock or unlock;
  - undo/redo with Ctrl+Z / Ctrl+Y, over the whole session.
- **Markers:** place and edit loot spots, spawns, extracts and invisible walls. Each type has a clear colour and
  icon, plus an inspector panel for its fields.
- **Containers:** a lootable / decor toggle, previewed live as ajar or closed.
- **Views** (toggles):
  - loot spots only;
  - spawns and extracts;
  - collision volumes coloured by `phys`;
  - a loot heat map (density per area);
  - sightlines from a spawn.
- **Checks** (warnings list, click to jump there):
  - a prop inside a wall or floating;
  - a doorway or gap blocked below the player sizes;
  - a spawn without free space or too close to another team;
  - a loot spot that cannot be reached;
  - duplicate ids;
  - a placement off the map.
- **Save:**
  - an atomic write;
  - a timestamped backup of the last 10 saves;
  - autosave every 2 minutes;
  - a diff summary on save (added, moved, deleted).

## Rules

- **Deterministic collision:** placed props add their `COL_` volumes to the level in a stable order, so the host
  and every client build the same collision from the same files.
- **Data first:** all editor numbers live in `game/assets/data/build_mode.ron` (snap steps, colours, autosave).
- **Tests:**
  - `placements.ron` round-trips;
  - undo/redo restores exact state;
  - the snapping maths;
  - each check (one test per warning);
  - the map-version hash;
  - collision from placed props matches the props' `COL_` volumes.
- **Not in scope:** terrain sculpting and editing buildings (that stays in Blender), and lighting edits.
- **Testing:** the user playtests. Do not launch long live runs; prove things with tests.

## Order of work

1. The prerequisites.
2. The data format.
3. Camera and browser.
4. Place, select and edit, with undo.
5. Markers.
6. Checks.
7. Save and Play from here.

Then convert today's Showhome:
- the hand-placed props become instances in `placements.ron`;
- its spawns move there too;

so the user can start editing the current map before the rebuild arrives.
