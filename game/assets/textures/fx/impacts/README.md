# Bullet-hole atlas

Built by `assets/fx/impacts/_src/build_atlas.py` (repo root). Do not edit these files by hand: change the script and
run it again. The game reads them in `val_etf/src/impacts.rs`; the tuning (sizes, life, caps, which look is which
kind, debris) is in `game/assets/data/impacts.ron`.

The atlas is square, 6 x 6 cells of 192 px (1152 px). Cell `i` is column `i % 6`, row `i / 6` (row 0 at the top).
`impacts_atlas.ron` lists the cells of every surface kind (4 variants each), the kinds that have a paint layer, the
debris sprites and `depth_ref`.

| File | Content |
|---|---|
| `impacts_albedo.png` | sRGB RGBA, **straight alpha**: the core layer (what the shot exposes: crater, bore, bare metal, fresh wood, cracks, dust). Colour under alpha 0 is dilated from the nearest visible texel, so mips do not bleed a dark fringe. |
| `impacts_paint.png` | sRGB RGBA at half resolution, same layout: the paint layer (the hit surface itself, bent or lifted: cladding shards, a dent in painted metal, wood splinters). RGB is grey painted AO, alpha its coverage. The game tints it with the surface's colour per mark (vertex colour), so one atlas fits every wall colour. |
| `impacts_normal.png` | Linear tangent-space normals, OpenGL / glTF convention (+X right, +Y toward the top of the image), shared by both layers. |
| `impacts_depth_mr.png` | Linear. R = depth for Bevy's parallax (`StandardMaterial::depth_map`: white = deep, 1.0 = `depth_ref` half-widths of a mark, so a mark's depth scales with its size). G = roughness, B = metallic (the `metallic_roughness_texture` layout), so one image serves both. |
| `impacts_atlas.ron` | The cells, written with the atlas. |

Conventions: a mark's up is the image's top (wood marks are turned so that is the grain). Nothing is drawn past
0.86 of a cell's half-width, so neither mips nor parallax reach a neighbour. The game samples the atlas with a
clamped, anisotropic sampler and builds the mip chain at load (`map_materials::mip_chain`).

Kinds: Plaster (printed concrete, plaster, trim: a chipped crumbly crater, a deep bore, hairline cracks, a pale dust
ring), Cladding (fibre-cement, slate: a punched hole, flaked paint over the grey fibrous core, brittle cracks,
shards), Wood (an oval hole along the grain, torn fresh wood, lifted splinters), Metal (a clean punched hole, a bright
bare-metal lip, a chipped paint ring, a dent), Glass (a star crack; the map has no glass yet), Pavement (asphalt,
paving: a shallow chipped pock mark, loose chips, a dust splash), Soil (lawn, gravel: a dark scuffed puff, no hole).
Sprites: `puff` (a soft dust cloud), `chip` (a debris chip), `spark` (a streak), all white and tinted per piece.
