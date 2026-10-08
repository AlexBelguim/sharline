# Showhome textures (game copy)

Copies of the textures the game uses from the Showhome library in `assets/maps/showhome/textures/` (repo root).
That folder's README is the reference: what each texture is for, metres per repeat, roughness and the palette.
Edit or regenerate them there, then copy them here. `val_etf/src/map_materials.rs` maps the level's looks onto
them and builds the mip chains at load.

Not from the library: the parallax maps `*_depth.png` (16-bit, white = deepest), `*_orm.png` (R = AO) and the
normal maps `asphalt_normal`, `gravel_normal`, `grass_lawn_normal`. `assets/fx/depth/build_depth.py` (repo root)
makes them from the library's own structure code, so they line up with these albedos; rebuild them there with
`--game` whenever a library albedo they belong to changes. `game/assets/data/surface_depth.ron` says which
surface uses which and how deep.
