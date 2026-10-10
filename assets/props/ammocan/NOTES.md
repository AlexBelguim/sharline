# Ammo can — clean SHARD/LINE prop

An open olive-painted ammunition can with broad flat panels, regular chamfers, a folded carrying handle, and a stamped end latch. The fictional bone stencil replaces the source's distorted generated lettering; a small ochre latch mark is the only accent colour.

This is a **source-guided reconstruction**, not a cleaned decimation of the TRELLIS topology. The open-lid silhouette, proportions, paint family, handle arrangement and closure layout came from the supplied design. The body, rim, lid, handle, hinge and latch were rebuilt. No TRELLIS triangles, albedo atlas, or normal bake remain in the final asset. That distinction matters: retaining the high-resolution normals would reintroduce the wavy metal panels even after flattening the geometry.

## Delivered asset

- `ammocan.glb`: 2,256 triangles, one mesh node, seven standard PBR material primitives, embedded textures, no glTF extensions.
- `ammocan.fbx`: same geometry, metre scale, Y-up, embedded textures; separate PBR maps are also supplied for engines that need explicit FBX material assignment.
- `ammocan.blend`: 35 individually editable construction parts, studio lights, camera and preview floor. The helpers are excluded from exports.
- `build_ammocan.py`: rebuilds geometry, derives the painted textures, renders previews, exports both formats and performs fresh import checks.
- `QA.json`: immutable source hash, source/export statistics, material checks and fresh GLB/FBX geometry checks.
- `renders/`: six views, contact sheet, material-free clay view and a render of the freshly imported GLB.
- `reference/PICK_c_ammocan.png`: frozen design reference.

The exported bounds are **0.573 × 0.255 × 0.557 m** in Blender X/Y/Z. The body is 0.534 m wide; the extra width comes from hinge and latch hardware. Origin is at the centre of the body's base, Z=0; glTF uses Y-up with an identity mesh-node transform and ground at Y=0. Front is Blender −Y. The lid is a static 22° open pose.

## Material treatment

The existing Krea2 `worn_paint.png`, `brushed_metal.png` and `polymer_stipple.png` library textures supply the broad, restrained variation. They are precomposited with the palette into normal image textures so the result uses standard glTF PBR rather than Blender-only multiply nodes.

Base-colour maps are sRGB. ORM maps are linear, with R=1 (unoccluded), G=roughness and B=metallic. Painted panels use roughness around 0.61–0.73 with zero metallic; exposed steel uses metallic 0.72 and roughness around 0.43. The shared OpenGL tangent-space normal is deliberately flat. All edge shape is real geometry. Every part has UVs, and the large stencil panels have intentional rectangular UVs. Surfaces are opaque and single-sided, with real shell interior geometry.

## Verification and remaining limits

Fresh GLB and FBX imports preserve triangle count, dimensions, UVs, identity transforms and the ground pivot. Both have zero degenerate triangles and zero boundary/nonmanifold edges when coincident hard-normal/UV seam positions are welded on a disposable inspection mesh. The actual exported vertex splits remain intact. GLB material records contain base colour, metallic/roughness and normal textures for every material. The freshly imported GLB was rendered and visually inspected alongside the authoring and clay views.

There are intentional separate intersecting construction pieces, as on most game props. This is not a single printable solid. No collision mesh, hinge animation, contents, LOD or engine hookup is included. Seven material primitives are acceptable for this prototype but an atlas could reduce draw calls further. The rim and hardware are regularized rather than exact replicas of the source's melted detail, and the label artwork is deliberately different.

## TRELLIS cost assessment

The supplied raw GLB contains **699,081 triangles**. Its shape/design reference was useful; its wavy panels and hardware were not economical to keep for a clean hard-surface prop. The main cleanup cost here was effectively rebuilding a simple can, plus inspection and export verification. This example therefore does **not** demonstrate a speed advantage over starting with a procedural can and the same image reference. Automated reruns took roughly 14–26 seconds with the already-written build script; that is not the original modeling/cleanup effort, and there is no timed equivalent from-scratch baseline.

Read-only source: `C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI/output/valetf_c_ammocan_full_00001_.glb`

SHA-256: `39574a36e7561792a18e462eb743dacf8f8eab7fcb1664413c21869bc8520927`

Rebuild command:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --disable-autoexec -b --factory-startup -P 'F:/git/val etf/assets/props/ammocan/build_ammocan.py'
```
