# Solace v2 — authored medic model

Fresh, reproducible Blender geometry built by `build_solace.py` and the shared
`assets/characters/_shared/character_v2.py`. No TRELLIS or old character geometry
is imported. The earlier Solace files remain in the parent directory.

Authoritative design references: main v09, face v05, turnaround v08, Bloom back
v04, interpreted through the full Solace BRIEF and art direction log.

- Lean athletic female proportions, skull height 1.68 m, feet Z0, front -Y.
- Common 61-bone UE5-named skeleton/rest axes shared with Kestrel; 45° A-pose.
- Warm deep brown modeled face; dark brown eyes; brown-black side-parted hair.
- Ponytail, injector bracer and sand medic pouch on her RIGHT (-X).
- Three-petal Bloom emblem and docked single-eye heal drone on LEFT (+X).
- Ivory wrap jacket front ends at Z .900; curved split back tails reach .645.
- Soft collar, charcoal mock-neck, sand trousers, slim ivory knee pads, charcoal
  finger gloves and shaped ankle boots. Broad color planes and creases are authored.
- Compact closed three-vane Bloom: coral seams, charcoal yoke, two LEDs, lower hub;
  vane objects have hinge origins and exported pivot sockets for a healing burst.
- Painted coral cloth, tie, studs and emblem have no emission. `M_SOL_Glow` is the
  sole emissive material and belongs to Bloom, injector vial and drone technology.

## Technical validation

Evaluated triangles: **49,692** including all hair and gear.
Mesh objects: 18. Maximum vertex influences:
**3**. Unnormalized/unweighted/over-four vertices:
**0**. Every mesh has UVs. PBR paint textures are
embedded in GLB and packed in the Blender scene; FBX copies textures.

Static deformation renders: sprint, crouch (60° hip/95° knee bends), two-hand aim,
and overhead zipline reach. These are QA poses only; exports contain no animation
clips. `solace_qa.json` records per-mesh exported checks; `validation.json` contains
the compact whole-model checks. Render folder includes front, left-side-facing
right camera, back, front/rear three-quarter, face and Bloom close-ups, pose sheet,
and 64-pixel front/side/back silhouettes.

## Exports and rebuild

`solace.blend`, `solace.glb`, `solace.fbx` all use the shared neutral rest rig.
Rebuild with Blender 5.2:

    blender -b --factory-startup -P build_solace.py

Use `-- --quick` for neutral front/three-quarter previews. No game code is changed.

## Limits

Hair clumps are weighted to the head, and coat tails use pelvis/thigh blends.
Secondary hair/cloth simulation and production facial blendshapes are future
animation work. Bloom deployment has mechanical origins and sockets but no clip.
