# Prompt 3: loot containers (find or design a reusable set)

You build props for SHARD/LINE (stylized, painted look, Blender + Krea2). The extraction mode needs many kinds of
**containers that hold loot**. Players must recognise at a glance what can be searched and roughly what is inside.
Build a reusable container set for the prop library (`assets/props/containers/`, catalog
`assets/props/catalog.json`). Follow the prop library, free-models-first and restyle rules in
`04_SHOWHOME_REBUILD_MODELING.md`, and the materials, collision and foliage contract in
`art/briefs/MAP_MATERIALS_SPEC.md`.

## The visual rule: lootable means slightly open

A container that can be searched always shows it, the same way on every map:
- **Doors** stand ajar by 10–15°.
- **Drawers** stick out 3–5 cm.
- **Lids** are cracked 5–10°.
- **Bags** have their zipper or flap half open.

The same furniture that is NOT lootable stays fully closed, so the open gap itself is the signal. After a search
the game swings it fully open. Model each container's parts so all three poses work: closed, ajar and fully open.

- **Movable parts:** each door, drawer, lid or flap is a separate mesh with its pivot where it really turns or
  slides. Name them `OPEN_DOOR_<n>`, `OPEN_DRAWER_<n>` or `OPEN_LID_<n>`, with the custom properties `axis`,
  `min_deg` / `max_deg` or `travel_m`, and `ajar` (the slightly open value).
- **Loot slots:** one or more empties named `LOOT_SLOT_<n>` inside, where the game places item models.
- **Container data:** custom properties on the root:
  - `container` (the type id from the table);
  - `size` (`small` | `medium` | `large`);
  - `search_s` (the suggested search time);
  - `lootable` (default `true`; `false` makes the always-closed decor version).
- **Interiors:** give the inside real depth, a back panel and shelves, and a slightly darker inside material, so the
  ajar gap reads as an opening and not a texture.

## Placed by the user in build mode

The user places containers and sets which are lootable in the in-game build mode (`02_BUILD_MODE.md`). A
container's root properties are its defaults there. Every container must therefore work as a stand-alone instance:
- its pivot sits at the base centre;
- it rests cleanly on a floor or a wall (wall-mounted ones have their pivot on the back face, with `mount = wall`);
- its collision is included.

## The set

The type ids are fixed and the game's loot tables will key on them. The first batch is in bold.

| id | What it looks like | What it suggests inside |
|---|---|---|
| **`backpack`** | civilian and tactical backpack, flap half open | random gear |
| **`duffel_bag`** | sports and travel duffel, zipper half open | random gear, ammo |
| **`weapon_case`** | long hard case and a wooden weapon crate | guns, attachments |
| **`ammo_box`** | metal ammo can and wooden ammo crate | ammo, magazines |
| **`metal_crate`** | military-style steel crate with clasps | high-tier gear |
| **`toolbox`** | red toolbox and the worksite steel "gang box" (job box) | tools, barter parts |
| **`kitchen_cabinet`** | base and wall cabinets and kitchen drawers | food, water, misc |
| **`dresser`** | dresser, nightstand and wardrobe (see `refs/good_dresser_BAD_flat_bookcase.png`) | clothes, valuables |
| `pc_case` | desktop PC tower with its side panel off or ajar | electronics |
| `electrical_box` | wall-mounted electrical cabinet and a street utility cabinet | fuses, wires, electronics |
| `filing_cabinet` | office drawers | documents, keys, intel |
| `medical` | wall first-aid cabinet and a medic bag | meds |
| `safe` | small floor safe, door ajar | valuables, rare items |
| `barrel` | steel drum with its lid cracked, and a plastic barrel | misc, barter |
| `cooler` | camping cool box | food, drink |
| `site_locker` | changing-room lockers in a site office container | random gear |
| `hidden_stash` | a hidden spot with a subtle tell: a loose floorboard, a taped panel in a wall, disturbed soil with a marker stone, a bag in a bush | rare, random |
| `jacket` | a hanging jacket with its pockets | small items |

Add more of the same kind of thing if a map needs it, e.g. a fridge, a cash register or a mailbox. Ask before
inventing many.

## Rules

- **Free models first, then restyle.** See prompt 4. Bags, ammo cans, barrels and toolboxes are often available as
  CC0. Restyle them to our palette and painted Krea2 textures, simplify them, and add the parts and properties above.
  Model the rest yourself. Credit everything in `assets/CREDITS.md`.
- **Colour language** helps players read the tier from a distance; keep it consistent:
  - civilian: muted, worn colours;
  - worksite: safety yellow or orange;
  - military: olive and dark grey with stencils;
  - medical: white with a green cross. NEVER a red cross: it is a protected emblem.
- **Sizes are real-world.** Bags sit on the floor or hang on hooks, and cabinets fit the house interiors.
- **Collision:** each container gets `COL_` volumes and `phys`:
  - wood: `wood_thin`;
  - steel cases and crates: `sheet_metal`;
  - safes: `metal_heavy`;
  - bags: `fabric`;
  - plastic: `plastic`.
- **Budgets:** small containers stay under about 1.5k triangles and large ones under about 5k, each with an LOD1.

## Deliverables

- **The batch:** the props in `assets/props/containers/<id>/`, each with closed, ajar and open poses checked, and
  their catalog entries.
- **A contact sheet:** every container in all three poses side by side, plus a "decor" (closed, not lootable)
  version of the furniture ones.
- **A line-up render:** one shot at about 6 m in game lighting showing that a lootable dresser reads differently
  from a decor one.
- **`assets/props/containers/NOTES.md`:** the type list, the pivot and naming conventions, and what the game needs
  to build: search, the ajar to open animation, and loot slots.
