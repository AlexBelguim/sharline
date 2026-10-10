# Paste this to the modelling agent

You are building the new Showhome map for SHARD/LINE. Everything you need is in this folder,
`art/briefs/showhome_v3_handoff/`, a snapshot of the originals in the repo. If something here and the repo
disagree, the repo wins.

Read and follow, in this order:
1. `01_BRIEF_showhome_rebuild.md` is your main brief. Read its section "Where it sits, and the order of work" first.
2. `layout/diagram.png`, `layout/LAYOUT.md` and `layout/extraction_layout.json` are the extraction map layout. The
   Showhome inset is at the bottom right of the diagram. Work in the extraction map's world frame from the start:
   metres, x east, y north, origin at the map's south-west corner. The map is 1300 × 1100 m (layout v0.2), and
   Showhome's TDM cut-out is x 330–410, y 620–680. All callouts are in English.
   Build the Showhome core around one map-origin empty at the cut-out's south-west corner, so the area can still be
   moved with a single offset if the layout shifts again.
3. `02_MAP_MATERIALS_SPEC.md` covers the physical materials, the convex `COL_` collision volumes exported as
   `collision.json`, the `FOL_` foliage volumes (the game grows the leaves), and the placements contract.
4. `03_LOOT_CONTAINERS.md` covers the loot containers. The rule is "lootable means slightly open".
5. `refs_ingame/` holds good and bad in-game examples. The verdicts are in `VERDICTS.md`.
6. `USER_VISION.md` is the user's own words for this map. Read it.
7. The look references:
   - **The Showhome core follows `concept_showhome/` (the original concept art) and `current_map/`** (renders and an
     in-game shot of the Showhome kit we already built). Keep what works there: the two houses with the painted
     cladding, the hedges, greenhouses, gardens, street and truck. Make it follow the concept more closely, with
     bigger gardens, now FITTED INTO the construction site.
   - **The construction site around it follows `concept_worksite/`.** These new concepts show the construction
     look better: half-built rows with scaffold, cranes, site office containers, porta-potties, pits, material
     stacks, mesh fences, trucks and a cement mixer. Do not copy their generic houses; the Showhome houses come
     from the original concept and the current map.
   - **KEY reference for the Showhome core: `concept_showhome/KEY_showhome_layout.png`.** It sets the homes, their
     general placement (two houses either side of the driveway with the truck, carports at the back, sheds and the
     greenhouse, white picket fences at the front) and the HIGH HEDGES around the plots.
     - Make it a little MORE SPACIOUS than in that picture: about the size of the current map (72 × 48 m playable)
       or a bit bigger (the TDM cut-out is 80 × 60 m).
     - The STREET at the bottom left of that picture is the SAME street as the one at the bottom right of the
       composition crop below (the road with the truck). Make it one continuous front street that runs along the
       Showhome plots and on past the construction site.
   - **Composition (the user's pick):** `concept_worksite/COMPOSITION_showhome_in_front_of_site.png`. The Showhome
     houses sit IN FRONT of the construction site, as in that crop:
     - the finished show homes and their gardens line the street at the site's front edge, with the street and the
       truck in front;
     - the construction site starts directly BEHIND the back gardens: half-built rows, site office containers,
       porta-potties, the excavator, trucks and sand piles.
     This matches the layout's inset (the front street south, the Shells and cranes north).
   - `concept_areas/` holds concept art for the other areas of the extraction map: an aerial and a ground view per
     area, for mood and materials only (its `README.md` says which layout area each image belongs to). The layout
     wins over the images.
8. `style/` holds the look rules: the art bible (`STYLE_GUIDE.md`), the painted, deep-seam material look
   (`SHOWHOME_BACKDROP_BRIEF.md` and `painted_cladding_ref.png`), and the user's decisions (`DIRECTION_LOG.md`,
   items 11 and 16–18).

For any textures, depth, height or normal maps, decals or painted detail, use the local models through ComfyUI
(Krea2 and Qwen Image 2.1). The brief's section "Local image models for textures and depth" says how, and lists
the GPU etiquette.

Start with Phase 1, the Showhome core:
- both houses;
- the gardens, bigger and more open behind the houses than in today's map;
- the street and the truck;
- the clips on the cut-out's four edges, matching the inset.

First show me your step-0 plan: a layout sketch over the concept, the prop list with its sources, and the edge
treatment for each boundary. Then build it, and deliver it as the playable map `showhome_v3` before you start
anything else. The current Showhome stays.

Then:
- Phase 2: the worksite ring around Showhome.
- After that: expand area by area, in the order the user picks.

Deliver each phase so it is playable on its own.
