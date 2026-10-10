# Map physical materials and collision: authoring spec (draft v1, 2026-10-08)

This is the contract between the map build in Blender and the game. Every surface a bullet or a player can touch
gets a **physical material**: what it is made of, not how it looks. The game reads it for bullet penetration, bullet
holes and debris, footstep and impact sounds, and later for breakable glass. Because the collision comes from the
same Blender file as the art, visuals and collision always line up, and **thickness is never typed in by hand**: the
game measures how far a bullet travels inside each collision volume.

## 1. The material table (ids are fixed; the game's numbers live in `game/assets/data/materials.ron`)

| id | Use it for | Bullets (default, tunable) | Holes / effects |
|---|---|---|---|
| `glass` | window panes, greenhouse, pod and car windows | pass through, almost no loss | crack ring with a clear centre |
| `wood_thin` | fence boards, doors, crates, pallets, sheds, furniture | pass up to ~10 cm, small loss | see-through hole, splinters |
| `wood_thick` | posts, beams, sleepers, thick tabletops | stop beyond ~15 cm | dark hole, splinters |
| `sheet_metal` | corrugated sheets, shutters, car bodies, pods, bins, signs | pass up to ~1 cm, medium loss | see-through hole, sparks |
| `metal_heavy` | engine blocks, steel beams, pylons, machinery, kerb-height steel | stop | dent, sparks |
| `drywall` | interior partition walls, ceilings | pass up to ~15 cm, large loss (user-confirmed: wallbangs through interior walls) | dusty hole |
| `concrete` | structural walls, slabs, kerbs, blocks, pillars | stop | crater, dust |
| `brick` | brick walls, chimneys | stop | crater, red dust |
| `cladding` | fibre-cement / timber cladding over a stud wall (house outer walls) | stop (user-confirmed: outer walls stop bullets) | panel hole |
| `foliage_thin` | low bushes, hedge edges, climbers, tall grass clumps | pass up to ~60 cm, small loss | leaf puff, no decal |
| `foliage_dense` | hedge cores, tree trunks are NOT this (use `wood_thick`) | pass up to ~30 cm, medium loss | leaf puff, no decal |
| `fabric` | tarps, awnings, umbrellas, curtains, sofas | pass, almost no loss | small tear |
| `plastic` | chairs, bins, barriers, crates, toys | pass up to ~5 cm, small loss | hole, chips |
| `soil` / `grass` / `gravel` / `sand` | ground surfaces | stop | puff (no mark on lawns), footsteps |
| `asphalt` / `paving` | roads, pavements, patios | stop | pock mark, footsteps |
| `water` | ponds, puddles deeper than 5 cm | stop after ~50 cm | splash |

A bullet can cross at most two penetrable volumes. Each crossing costs damage by material × distance travelled
inside it. AP rounds lose less (user-confirmed: the ammo pick matters for wallbangs). So the corner of a thick hedge (20 cm of leaves) lets a bullet through and its
middle (1.5 m) stops it. New ids may be added later. Ask before inventing one; use the closest existing id
meanwhile.

## 2. Visual meshes

- Every Blender **material** gets a custom property `phys` = one id from the table. Export with glTF "Custom
  Properties" on, so it lands in the material's `extras`.
- Mixed objects (a door with a glass panel) use separate materials per part, each with its own `phys`.
- Purely decorative meshes no player or bullet can reach (backdrop, sky ring, far props) may leave `phys` off. They
  must also have no collision.

## 3. Collision volumes

- Put collision in its own collection `COLLISION`, exported to the game as data, never drawn.
- Each collision object is named `COL_<name>`. It must be **convex**: a box, wedge, prism or convex hull. Split
  anything concave into several convex pieces. Overlaps between pieces are fine; gaps are not.
- Custom properties on each `COL_` object:
  - `phys` (required): an id from the table.
  - `kind` (optional, default `solid`): `solid` blocks players and bullets; `player_clip` blocks players only
    (invisible bounds, roof clips); `bullet_only` blocks bullets and sight only.
  - `walkable` (optional, default from slope): `false` forces slide-off on a surface (e.g. gables).
- **Use real thicknesses**, because the game measures them:
  - glass panes 1–2 cm;
  - fence boards as boxes about 2 cm thick;
  - corrugated sheet 1 cm;
  - a bush as a convex volume slightly inside its leaf silhouette;
  - a hedge as a core volume (`foliage_dense`) plus edge volumes (`foliage_thin`) if its edges should be easier to
    shoot through.
- Keep collision simple: about 1 volume per wall segment, door frame or prop. Small decorative bits (handles,
  gutters, bolts) get no collision.
- Stairs and ramps are wedges. Kerbs and steps under 35 cm are just boxes; the game steps up automatically.
- Holes players or bullets can pass through (windows without glass, door gaps, garage gaps) are real gaps in the
  collision. Check the clearance against the player sizes:
  - standing needs 1.8 m;
  - crouching needs 1.25 m;
  - between 1.0 and 1.25 m only a slide fits, and the game keeps you low there;
  - under 1.0 m nobody fits.

  Make slide-only gaps deliberate and list them in the report.

## 3b. Foliage volumes (the game grows the leaves)

The user likes the hedges and bushes the game makes (`refs/good_hedge_on_frame.png` in
`art/briefs/showhome_rebuild/`). They are generated in code: a dark core plus a shell of painted leaf cards that
sway in the wind, with quality presets. So **do not model leaves or grass blades.** Place foliage as volumes, and
the game dresses them:

- **Hedges, bushes, climbers and tree canopies:**
  - Make a simple object (a box, a rounded box or a convex blob) named `FOL_<kind>_<name>`.
  - Give it the custom properties `foliage` = `hedge` | `bush` | `climber` | `canopy`, and optionally `density`
    (0.5–1.5) and `tint` (a palette colour name).
  - The object's shape is the leaf silhouette.
  - Also give it a matching `COL_` volume, `foliage_dense` or `foliage_thin`, unless players should walk through it.
  - Trunks, branches and frames (like the hedge's wooden frame) are normal modelled props.
- **Lawns:** a ground surface with `phys = grass`. The game adds the mown-lawn fuzz and the taller tufts along
  fences, walls, kerbs and hedge bases by itself. Worn or dirt spots come from the ground blend masks, as today.
- **Game side:** today the game dresses box-shaped hedges. Rounded bushes, climbers and canopies need the foliage
  code extended (planned). Until then they render as their plain volume.

## 4. Export and checks (the build script must do these)

- Write `collision.json` next to the scene GLBs. It uses the design frame (metres, X east, Y north, Z up, origin
  south-west corner, the same as `ground_steps.json`). For each `COL_` object it holds: name, `phys`, `kind`,
  `walkable`, the convex volume as outward planes `(nx, ny, nz, d)`, and its AABB.
- Fail the export if any of these is true:
  - a `COL_` object is non-convex or has no or an unknown `phys`;
  - a reachable visual material has no `phys`;
  - a volume is thinner than 5 mm.
- Write a short report: volume count per material, the thinnest volumes, and any visual surface farther than 5 cm
  from its collision (art and collision out of step).
- Render one **material debug view**: an aerial plus two street shots with every collision volume coloured by `phys`.

## 5. What the game does with it

- Builds the map's collision brushes from `collision.json`. No more hand-written brushes in code. The current
  Showhome's code brushes stay until the remade map ships this file.
- **Hitscan penetration:** the trace continues through penetrable volumes, losing damage by material × path length.
  Tracers continue, and holes appear at entry and exit.
- **Holes:**
  - glass gets clear-centre cracks;
  - thin wood and metal get real see-through holes (the surface is cut where the bullet passed);
  - bushes get a leaf puff and no decal;
  - lawns get no marks.
- Footsteps, impact sounds, debris and spark colours by material.
- The `phys` on visual materials is used where a bullet hits art without collision behind it (decals), and to check
  that the art and the collision agree.

## 6. Kit, prop instances and placements (with the in-game build mode)

See `art/briefs/showhome_rebuild/02_BUILD_MODE.md`. A map folder holds:
- **the kit:** the static scene GLBs and `collision.json`, owned by the modelling agent;
- **`placements.ron`:** prop instances by library id, and every marker (loot spots, spawns, extracts, invisible
  walls). The user owns it after hand-off and edits it in the game.

The modelling agent therefore:
- exports movable props as **instances** of `assets/props/` library entries, never baked into the kit;
- writes the starter `placements.ron` only once;
- puts later prop changes into `placements.proposed.ron`.

A library prop carries its own `COL_` volumes and `phys`. The game adds them to the level wherever the prop is
placed.
