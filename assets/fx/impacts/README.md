# Bullet holes: sources

The sources of the bullet-hole atlas in `game/assets/textures/fx/impacts/` (see the README there for the files the
game reads and their conventions).

Every mark's structure is drawn from code in `_src/build_atlas.py`: crater outlines (random star polygons with
straight chipped edges), bowls and fracture facets, bores, cracks (random walks rasterised with tapering widths),
cladding shards, wood tears and splinters, metal lips, chipped paint rings and dents, glass star cracks, loose chips
and dust. So albedo, height, normals and depth line up exactly. Krea2 only gives the painterly grain and mottling of
the material a shot exposes, recoloured to a fixed mean from the Showhome palette, the same split the Showhome
texture library uses (`assets/maps/showhome/textures/README.md`).

## Rebuilding

From `_src/` (Python 3 with numpy, scipy and Pillow):

1. `python gen_raw.py [name ...] [--seeds 11 12] [--force]`: the Krea2 raws through local ComfyUI
   (127.0.0.1:8188, Krea2 Turbo, 1024 x 1024, 8 steps, `tools/comfy_gen.py`) into `_src/raw/<name>_s<seed>.png`.
   Existing files are skipped. Prompts describe the surface only and never say "tile".
2. `python build_atlas.py`: writes the four atlas maps and `impacts_atlas.ron` into `game/assets/textures/fx/impacts/`
   and the previews into `_src/preview/`. Every cell is seeded (`1000 * (kind + 1) + variant`), so a rebuild gives
   the same atlas.

## Raws (seeds 11 and 12 each)

| Raw | Used for | Prompt (plus the common tail: flat even lighting, no borders, no objects, no text, stylized hand-painted game texture, soft painterly brushwork) |
|---|---|---|
| `rubble_cream` | Plaster crater floor | uniform close-up of crushed cream concrete and plaster crumbs with fine pale dust seen from directly above, small angular chips, warm cream and light beige |
| `fibre_core` | Cladding flaked ring | uniform close-up of the broken fibrous core of a grey fibre cement board seen from directly above, short pale grey fibres and fine grit |
| `wood_fresh` | Torn wood | uniform close-up of freshly split pale pine wood viewed straight on, long straight torn fibres running vertically, light honey and cream tones |
| `bare_steel` | Metal lip | uniform close-up of bright bare steel viewed straight on, fine scratches and soft brushed streaks, cool light grey |
| `stone_chips` | Pavement pock mark | uniform close-up of freshly chipped grey stone aggregate and asphalt grit seen from directly above, small angular light grey chips and fine dust |
| `soil_dark` | Soil puff | uniform close-up of dark brown loose soil crumbs seen from directly above, crumbly earth with tiny clumps and fine dust, no plants, no stones |

## Previews

- `_src/preview/contact_sheet.png`: every cell over its typical surface colour, lit from the upper left (the paint
  layer tinted with that colour).
- `_src/preview/normal.png`, `depth.png`, `paint_alpha.png`: the maps.
