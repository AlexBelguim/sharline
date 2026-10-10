# Showhome rebuild: prompts for the modelling agent

Use these in order when you are ready to rebuild:

1. **`01_EXTRACTION_MAP_DIAGRAM.md`**: the top-view layout of the bigger extraction map. Showhome is its hot zone,
   with the worksite, the highway, the water treatment plant, the container park, self-storage, the gas station,
   forest and the river with three crossings. The output is a diagram and a layout document only, no modelling.
2. **`02_BUILD_MODE.md`**: game code, built before the rebuild. An in-game build mode where you move, rotate,
   delete and add props from the library, and set every loot spot, player spawn, extract and invisible wall. Your
   edits live in `placements.ron`, which the modelling agent never overwrites.
3. **`03_LOOT_CONTAINERS.md`**: a reusable set of loot containers. It includes backpacks, duffel bags, weapon and
   ammo boxes, metal crates, toolboxes, cabinets, PC cases, electrical boxes, safes, barrels and hidden stashes.
   The rule is **lootable means slightly open**: doors stand ajar, drawers stick out and lids are cracked, while
   decor stays closed.
4. **`04_SHOWHOME_REBUILD_MODELING.md`**: the new Showhome, closer to the concept art. The agent builds the kit
   and the main props as movable instances, and you finish it in build mode. It is built from a reusable
   prop library, uses free models that are restyled to our look, and follows the material and collision contract,
   the one-edge-per-boundary rule and open fences. Foliage is placed as volumes, and the game grows the leaves.

All four depend on `art/briefs/MAP_MATERIALS_SPEC.md`, the contract for physical materials, collision volumes
and foliage volumes.

## `refs/`: the user's in-game screenshots

| File | Verdict |
|---|---|
| `good_raised_planter_box.png` | Good. Keep this level of prop detail. |
| `good_hedge_on_frame.png` | Good. These are the game's own hedges, so place foliage as volumes. |
| `good_hot_tub.png` | Good. |
| `good_garage_door_half_open.png` | Good. |
| `good_wooden_crate.png` | Good. |
| `good_garage_workbench_cabinets.png` | Good. Cabinets like these become openable containers. |
| `good_dresser_BAD_flat_bookcase.png` | The dresser is good. The bookcase is a flat texture and must be a real 3D prop. |
| `bad_double_border_planter.png` | Bad. It has a kerb, a grass border and a soft fringe all at once. Use one edge per boundary. |
| `bad_closed_board_fence.png` | Bad. A closed board wall. Fences are open and thin. |

The current Showhome stays in the game. The rebuild ships as a new map id (`showhome_v3`).
