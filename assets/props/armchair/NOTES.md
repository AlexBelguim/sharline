# Armchair — SHARD/LINE prop finish

Supplied TRELLIS scroll-arm chair, cleaned into broad terracotta upholstered forms with dark timber feet. This is a static environmental prop.

- **4,902 triangles**: 4,470 upholstery + four 108-triangle legs. Original source: 699,034 triangles.
- **0.879 × 0.670 × 0.950 m**. Metres, base centre at the origin, Blender Z-up / front −Y. Object transforms are identity. GLB exports Y-up; FBX uses −Z forward / Y-up.
- All five meshes use the `ACH_` prefix, have UVs, and are closed/manifold. Fresh GLB and FBX imports preserve triangle count, scale, ground placement, names, and UVs.
- `armchair.blend`, `armchair.glb`, `armchair.fbx`; `armchair_qa.json`, `armchair_import_qa.json`; colour/clay/round-trip previews under `renders/`.

## What changed

The original clean 4mm voxel / 4,500-triangle budget was reproduced from the immutable supplied source into `input/`, then frozen locally. The final cleanup does not perform another collapse decimation.

Weighted nonshrinking surface smoothing removes random local bumps. A broad low-order depth fit quiets the central front and rear cushion planes while pinning their perimeter. The mean original-mesh displacement is 3.3mm; the largest is 9.8mm. Scroll fronts, back perimeter seams, and the seat channel receive gentler treatment. Uneven generated feet are cut away and replaced with four capped, tapered, softly beveled timber legs.

The supplied painted colour layout remains an atlas; it is not converted into per-triangle colour classes. Its excessive intensity swings and false wear are reduced. Existing Krea2 `art/textures/fabric_soft.png` supplies subdued upholstery detail; `worn_paint.png` supplies quiet timber variation. Source normal detail is reduced to 20% lateral strength. Matte upholstery roughness is approximately 0.76; timber is 0.62; both are dielectric.

The GLB uses standard core glTF PBR maps, all embedded: sRGB albedo, OpenGL tangent normal, and linear packed ORM (R=1, G=roughness, B=0). External PNG maps are included under `textures/` for other importers. The FBX's embedded media includes albedo/normal; a destination that does not support packed ORM should bind its green channel as roughness and use zero metalness. GLB is the verified material reference.

## Rebuild and checks

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b --factory-startup --disable-autoexec -P 'F:/git/val etf/assets/props/armchair/build_armchair.py'
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' -b --factory-startup --disable-autoexec -P 'F:/git/val etf/assets/props/armchair/check_armchair.py'
```

`build_armchair.py` uses the owned clean input and invokes `paint_atlas.py` with workspace Python (Pillow/numpy). Override that interpreter with `VALETF_PYTHON` if needed. If the local input is absent, it invokes `prepare_clean_input.py`, which reads the supplied original GLB, reconstructs the initial budget and bakes local maps. No active `_tests` cache is a build dependency.

Original source SHA-256: `aed22e00fea01d91a46d8c29f1dc7f942fb3ebaffb9201556e00ceaf2515c8f2`.

## Remaining limitations

A small dent/slit remains in the right scroll face and a few shallow creases remain on the front cushion/back rim. Those are source geometry artifacts, visible in the clay preview; reducing the normal map cannot remove them. The back perimeter and arm-to-back junctions retain some source asymmetry. They are much quieter than the raw surface, but this is not hand-authored upholstery topology. Triangle spacing remains irregular, suitable for a static prop rather than deformation or close-up hero furniture. No collision mesh, LOD chain, or game integration is included.
