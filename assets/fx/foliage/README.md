# Foliage cards (Showhome hedges and lawn grass)

Art sources for the card atlases that `game/crates/val_etf/src/foliage.rs` puts on Showhome's hedges and lawns. The
look numbers (density, card size, AO, wind, fade distances per quality preset) are in `game/assets/data/foliage.ron`.

| File | What |
|---|---|
| `gen_raw.py` | Krea2 prompts and seeds (local ComfyUI through `tools/comfy_gen.py`). Each raw is a sheet of separate clusters on white. |
| `raw/` | The raws the atlases use: `hedge_paint_s11..13` (hedge), `grass_tuft_s11..13` (grass), and `hedge_clump_s12`, `hedge_box_s13`, `hedge_privet_s12` for the leafy first try. The other prompts' raws come back with `python gen_raw.py <name> --seeds 11 12 13`. |
| `build_atlas.py` | Keys the white to a soft alpha, un-mixes the edge colour, cuts the clusters out, re-colours them to the palette (hedge 98 112 52, grass 126 140 58 sRGB, from `assets/maps/showhome/textures`), packs the grid, bleeds leaf colour into the transparent texels and derives the hedge normal map. `--leafy` builds the first try. |
| `atlas_report.json` | Which raw each card came from, the mean colour against the palette, alpha coverage. |
| `preview/` | The atlases over grey, the leafy first try, and the concept's hedges cropped for comparison. |

Game textures (written by `build_atlas.py`) in `game/assets/textures/foliage/`:

- `hedge_cards.png`: 1024 x 1024, 4 x 4 square cards, sRGB, straight alpha. The clumps are painted lit from above,
  so side cards stay roughly upright in the game (`roll_deg`).
- `hedge_cards_normal.png`: linear, OpenGL convention (+Y = image top): a dome per card plus stroke relief.
- `grass_cards.png`: 1024 x 1024, 4 x 8 cards of 2:1, root on the bottom edge, sRGB. Every row is brought to the
  same brightness, then the root gets 0.9 of the lawn colour and the tips 1.1 (a little yellower).

The game builds the mip chains at load and scales each level's alpha so the share of texels passing the alpha test
stays the same (alpha-tested cards would otherwise thin out with distance).

## What was tried

- **Leafy clusters first** (box, privet and "irregular clump" prompts). Close up they are lively and leafy, but from
  a few metres the hedge reads as a pile of separate rosettes with busy small-leaf detail, unlike the concept.
- **Painterly clumps** ("a few big flat painterly brush strokes, no individual leaves visible"): the concept paints
  its hedges this way (big soft strokes, lit tops, darker sides), so these are the hedge atlas now.
- Prompts never say "tile" or "tileable" (Krea2 would draw literal tiles).

Rebuild: `python gen_raw.py` (skips existing raws), then `python build_atlas.py`.
