# Prompt 1: the extraction map layout diagram (do this BEFORE any modelling)

You are designing the layout of a medium extraction-shooter map for SHARD/LINE (Rust + Bevy, stylized,
Valorant-like painted look, Tarkov-style extraction with gear risk). **Your output is a top-view diagram plus a
short layout document. Do not model anything.** The rebuilt Showhome (prompt 4) will be the hot zone of this
map, and its TDM version is a cut-out of it.

## Read first

- The user's decisions: `art/DIRECTION_LOG.md`, especially items 16–18.
- The Showhome concept art: `design/maps/tdm/concepts/_candidates/A_showhome_aerial_s11.png`, `_s12`, and the
  `_ground_` views.
- Today's TDM layout: `assets/maps/showhome/layout/LAYOUT.md`, a 72 × 48 m playable rect.
- The materials and collision contract: `art/briefs/MAP_MATERIALS_SPEC.md`.

## The user's idea (their words, lightly edited)

> Showhome should be part of a bigger extraction-shooter map: a **new residential area still under construction**.
> It is a highly contested area surrounded by more open fields and the construction site: work-office containers,
> porta-potties, trucks, a cement truck, cranes. Around it: a big **highway**, some kind of **industrial
> building** (simplified), like a **water treatment plant** or something similar that fits, a **container park**
> like we have in Belgium (recycling park with skips on ramps), a **rental storage facility**, an **abandoned gas
> station**, some **forest patches** to connect things, and a **river** that divides the map, with a **road
> bridge**, a **dirt bridge** and maybe a **third place to cross**.

## Game facts that set the scale

- **Players:** about 12 per raid (solos and small squads). TDM uses 2–10 players, FFA up to 8.
- **Movement:**
  - walk 2.6 m/s, jog 4.8 m/s, sprint 7.0 m/s, so 1 km takes about 2.5 minutes at a sprint;
  - jump 1.0 m, mantle ledges up to 2.2 m, slides;
  - a jetpack: short bursts, about 6 m of climb;
  - ziplines exist.
- **Guns:** hitscan. The AR keeps its full damage to about 35 m and is still strong at 60–90 m; the sniper reaches
  far. Long open sightlines over 150 m are deadly, so open fields need cover rhythm.
- **Buildings:** they need not have full interiors. Key buildings get furnished rooms with lootable cabinets, drawers
  and bags.

## What to design

1. **Size and bounds.** Propose a size (my starting point is about 1.0 × 1.0 km to 1.2 × 0.9 km) and a hard
   boundary that reads as natural: the highway embankment, the river's far bank, dense forest, fences.
2. **Points of interest.** For each one give its location, rough footprint and the loot tier it earns
   (Showhome / the worksite = highest risk, highest loot). The list:
   - the Showhome worksite;
   - the highway, with an overpass or underpass;
   - the water treatment plant: clarifier tanks, pump house, sludge beds, control building;
   - the container park: an elevated ramp ring with skips below, a gate, a guard hut;
   - the self-storage: rows of roll-up units, a perimeter fence, an office;
   - the abandoned gas station: a canopy, a shop, a car wash;
   - forest strips;
   - open fields.

   Add 1–2 small POIs if the map needs them, e.g. a farm, an electrical substation, a bus depot or a canal lock.
   Keep it Belgian/Dutch in flavour and fully original.
3. **The river and its crossings.** The river splits the map into two halves with different characters.
   - The road bridge is fast but exposed.
   - The dirt bridge is out of the way but has cover.
   - The third crossing is a different kind of risk, e.g. the weir at the treatment plant, a pipe bridge or a
     shallow ford.
   - Mark the sightlines each crossing has.
4. **Routes and flow.**
   - Main roads, field paths and forest paths.
   - Where fights will happen (chokepoints).
   - Where a player can move through cover.
   - The highway as a barrier with limited underpasses.
5. **Spawns and extracts.** Mark them as zones and rough points only. The user sets the exact spawn points,
   extracts and every loot spot later in the in-game build mode (prompt 2).
   - Spawn zones at the edges, spread apart.
   - 4–6 extracts, some of them only open after a condition (e.g. after a set time, or only for players who paid);
     some require crossing the river.
6. **The TDM cut-out.** Mark the rectangle around Showhome that becomes the TDM / FFA arena (about 80 × 60 m),
   and where its invisible walls sit (road side, field edges).
7. **Landmarks for orientation:** the cranes, a water tower or the treatment tanks, highway gantries, the gas
   station sign.

## Deliverables

- **Diagram:** `design/maps/extraction/diagram.svg` (also export a PNG).
  - Top view, north up, a 50 m grid with coordinates, a scale bar and a legend.
  - Filled zones per POI, roads, paths, the river and its crossings, forest, fields.
  - Spawns (blue), extracts (green, with conditions noted), the TDM cut-out (dashed).
  - Key sightlines (thin red lines) and chokepoints (red circles).
- **Layout document:** `design/maps/extraction/LAYOUT.md`.
  - One section per POI: size, height levels, loot tier, cover, what makes it interesting to fight in.
  - The routes and crossings, and the spawn and extract rules.
  - A rough travel-time table between POIs.
  - Open questions for the user.
- **Hand-off note:** what prompt 4 (the Showhome rebuild) must respect, i.e. which edges of Showhome connect to
  which neighbours.

Keep it a diagram and a document. Show the user before anything gets modelled.
