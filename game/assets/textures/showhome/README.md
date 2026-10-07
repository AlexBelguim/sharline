# Showhome textures (game copy)

Copies of the textures the game uses from the Showhome library in `assets/maps/showhome/textures/` (repo root).
That folder's README is the reference: what each texture is for, metres per repeat, roughness and the palette.
Edit or regenerate them there, then copy them here. `val_etf/src/map_materials.rs` maps the level's looks onto
them and builds the mip chains at load.
