# Concrete Jersey barrier

Original reusable worksite prop, authored through `assets/maps/showhome_v3/build_library.py`.

- Dimensions: 2.0 m long on X, 0.65 m base depth on Y, 1.05 m tall; 0.18 m top depth.
- Pivot: ground centre at (0, 0, 0); front faces Blender -Y. glTF export uses Y-up.
- Shape: cast Jersey profile with a 22 mm single-segment chamfer, flared base ramp and narrow upper taper.
- Materials: existing v2 painted `concrete_smooth` and `fibercement_panel` textures. Cream bands and three orange diagonals on both long faces use original geometry. All surfaces have `phys=concrete`.
- LOD0: 108 triangles. LOD1: 44 triangles, using the exact unbeveled extrusion to preserve painted-face alignment. UVs and exported tangents present in both GLBs.
- Collision: two closed convex extruded volumes meeting at the profile knee, with a minimum plane thickness of 0.30831 m. This preserves the slope change without overfilling the Jersey profile. No moving parts or loot slots.
- Texture storage: six existing shared external images under `assets/maps/showhome_v3/textures`; no embedded image duplication or new AI images.
- QA: built with Blender 5.2, collision/UV/physics audits passed, LOD0 and LOD1 renders inspected.

Rebuild and render from the repository root:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b --factory-startup -P assets/maps/showhome_v3/build_library.py -- --only concrete_barrier --render
```
