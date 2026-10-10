# Original upholstered armchair

This chair is authored from scratch with radial pressure-fitted cushion lofts, shaped upholstery profiles, clean rolled arms, small sewn welts, and four tapered timber feet. The terracotta concept image guided the proportions and palette; none of its generated geometry, textures, or normals are used. The earlier AI-derived armchair remains separate.

The upholstery has broad, quiet surfaces with soft shoulders. The roll end caps have one controlled inward cloth tuck rather than a layered spiral lump. Seat and back cushions are distinct volumes with broad pressure crowns, rounded corners and restrained warm cream piping. The lower upholstered frame is a supporting apron rather than another loose cushion.

| Property | Result |
|---|---|
| Triangles | 4,496 |
| Materials | 4: terracotta body, cushion, welt, timber |
| Blender dimensions | 0.88 m wide × 0.76 m deep × 0.95 m high |
| Seat top | 0.44 m |
| Coordinates | Metres; Blender Z-up, front −Y; glTF Y-up, front +Z |
| Origin | Centre of the complete footprint at ground Z=0 |
| Editable blend | 20 authored mesh parts, identity transforms |
| Engine export | One mesh, four material primitives |
| UVs | UV0 on every triangle; intentional repeated textile UVs |
| Topology | Closed parts, no nonmanifold edges or degenerate triangles |

`build_armchair.py` rebuilds geometry, texture variants, standard PBR materials, studio renders, exports and fresh import checks. Run:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --disable-autoexec -b --factory-startup -P 'F:/git/val etf/assets/props/armchair_procedural/build_armchair.py'
```

Append `-- --quick` for an editable preview blend and two iteration renders. The full run writes `armchair.blend`, `armchair.glb`, `armchair.fbx`, `QA.json`, six views, a contact sheet, clay view, and separately rendered fresh GLB and FBX imports.

Texture variants are baked from existing `art/textures/fabric_soft.png` (shared Krea2 textile library) and a plank interior from `assets/maps/showhome/kit/textures/oak_boards.png`. They use low-contrast linear-light colour tints and packed ORM maps (R=1, G=roughness, B=0). There are no Blender noise nodes, fake micro-normal maps, new image-model jobs, photoreal grime or metallic upholstery. Both exports carry standard base colour and roughness data; the editable blend packs all images.

The meshes intentionally overlap where cushions meet the upholstered frame, as separately assembled upholstery does. They are independently closed, rather than one watertight sculpt. glTF splits vertices at UV/normal seams; its raw imported edge count consequently includes those boundaries. `QA.json` separately records a 0.0000001 m position-weld topology check, which verifies closed geometric parts after export. The fine piping and rolled tuck are static geometry. No collision mesh, LODs or deformation rig is provided; in-engine placement/performance has not been tested. `QA.json` records the actual export document and fresh import results.
