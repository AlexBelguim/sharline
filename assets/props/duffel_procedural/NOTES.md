# Original procedural duffel

Civilian navy canvas carry bag with one teal end panel, bone seam binding, graphite webbing, two rounded carry handles, a closed top zipper with a pull, and a draped shoulder strap with a separate padded cushion. The PICK image is a visual reference only. Every vertex is created by `build_duffel.py`; no imported, TRELLIS, or generated mesh geometry is used.

The body is an authored longitudinal loft with a flat grounded base, narrower shoulders, an asymmetric top sag, and three broad compression folds. The convex teal end is a separate sewn panel. Binding and piping are actual closed geometry. Body webbing follows the sampled polygonal canvas surface. This is a static full bag with a closed zipper, suitable as a pickup or environment prop; no unseen open cavity or unmodelled underside is used.

## Deliverables and rebuild

- `duffel.blend`: editable individual source parts, UVs, four standard PBR materials, and studio setup.
- `duffel.glb`: one mesh / four material primitives, embedded PNG textures, glTF Y up, identity mesh node.
- `duffel.fbx`: one mesh, embedded albedo/normal PNGs, matte material fallbacks, -Z forward / Y up.
- `renders/`: front, right, back, three-quarter, rear three-quarter, top, contact sheet, clay geometry check, and fresh GLB/FBX import renders.
- `QA.json`: source, topology, transform, bounds, standard PBR, and fresh export/import checks.

Run with Blender 5.2:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --disable-autoexec -b --factory-startup -P 'F:/git/val etf/assets/props/duffel_procedural/build_duffel.py'
```

Geometry is 3,890 triangles, under the 6,000 hard limit and within the intended 2–4k range. The prop is approximately 0.67 m long × 0.38 m deep including its draped strap × 0.40 m high including its handles; the canvas body is approximately 0.63 × 0.32 × 0.28 m. Base-centre origin is on Z=0, front faces Blender -Y, metres. Mesh transforms are applied before export.

## Material sources

Four materials: `M_DFP_Navy_Canvas`, `M_DFP_Teal_Canvas`, `M_DFP_Bone_Binding`, and `M_DFP_Graphite_Webbing`. Each uses standard basecolor, ORM, and OpenGL tangent normal maps at 512 px. Basecolor is sRGB. ORM is linear (R=1 unoccluded, G=roughness, B=0 metalness). The clean neutral hardware shares the bone binding response to stay within four materials.

The existing local Krea2 library is reused: `art/textures/fabric_ripstop.png` for both canvas colors, `fabric_soft.png` for binding, and `leather_soft.png` for the webbing/pad response. These images are tinted in linear space with the palette mean preserved. Existing `jacket_normal.png`, `webLight_normal.png`, and `web_normal.png` from Kestrel v2 are attenuated to 6% lateral relief. No new Krea/Qwen image generation, photogrime, procedural noise, AO bake, or directional light bake is added. Large cloth folds are real geometry.

GLB embeds all 12 PBR maps and carries explicit tangents with no material extensions. FBX embeds albedo/normal maps and uses faithful matte scalar roughness (navy .73, teal .71, bone .59, webbing .65) and metalness 0. FBX does not preserve the packed glTF ORM channel graph; those maps remain available in `textures/` for engine material setup. The fresh FBX preview checks this fallback visually.

All parts have UVs. Canvas uses a custom length/perimeter unwrap and planar end-cap islands; the remaining parts use Blender smart projection. All parts are closed manifold solids. Intersecting sewn/attached solids are intentional, so no cloth simulation or collision-ready single continuous surface is implied. Source names use `DFP_`. Fresh imports validate triangle count, welded-position manifold topology, UVs, and dimensions. Studio previews use the shared helper with background (0.18, 0.185, 0.20), strength 0.7, a floor, and AgX Medium High Contrast.
