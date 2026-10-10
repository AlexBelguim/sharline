# Concept art for the other areas of the extraction map

There is one aerial view and one ground view per area. They were made with Krea2 text-to-image, using the same
style suffix as the Showhome concepts. `_ALL_PICKS.png` is a contact sheet of all of them. The originals, the
other candidates and the prompts are in `design/maps/extraction/concepts/` (see `_prompts.json`).

How to use them:
- **For mood and materials only.** The positions, sizes, footprints and routes come from `../layout/LAYOUT.md`
  and `extraction_layout.json`. Where an image and the layout disagree, the layout wins.
- **Never copy an image's houses into Showhome.** The Showhome houses come from `../concept_showhome/` and
  `../current_map/`.
- **No image-to-3D.** Model the architecture and the hard-surface props in Blender (see the brief).

| Files | Area (LAYOUT.md) | Notes |
|---|---|---|
| `01_worksite_*` | Worksite (§3), the Phase 2 ring around Showhome | Flat-roofed concrete Shells, cranes, site containers. Use it together with `../concept_worksite/`. |
| `02_river_bridge_*` | C2 Road Bridge (§4) | Ignore the car park on the far bank. |
| `03_dirt_bridge_*` | C1 Dirt Bridge (§4) | A timber deck on old piers, with forest down to the water. |
| `04_weir_*` | C3 Weir (§4) | |
| `05_treatment_plant_*` | Water treatment plant (§3) | The sludge beds only read as empty basins; follow the layout for them. |
| `06_container_park_*` | Container park (§3) | The skips sit along the deck's outer edge, with their rims level with the deck. |
| `07_self_storage_*` | Self-storage (§3) | Alone in a clearing among woods. |
| `08_gas_station_*` | Abandoned gas station (§3) | |
| `09_highway_*`, `09_underpass_ground.png` | Highway, O1 Overpass and U1 Underpass (§3, §4) | The lorry is only skewed across the lanes; the layout's jackknife pose is a note to follow, not something the image shows. |
| `10_farm_*` | Farm (§3, small POIs) | |
| `11_substation_*`, `11_foresters_hut_*` | Substation and Forester's Hut (§3, small POIs) | Two separate places. |
| `12_dike_sluice_*` | The dike and the Sluice House, X3 Sluice Boat and X6 Dike Culvert (§4, §6) | |

Ask the user before you start an area: they pick the order after Phase 2.
