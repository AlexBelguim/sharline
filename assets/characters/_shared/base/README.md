# Editable female anatomy base

`female_base_source.blend` is the clean working base: full unmasked body, head,
eyes, brows and lashes in the source reference pose, front -Y and Blender Z up.
It has UVs and retains the native facial/body shape-key topology. Height is
1.70 m, with the lowest foot vertices at Z=0. `female_base_source.glb` is a
static geometry preview in glTF Y-up; it is not a finished gameplay character.

The working base has no final game skeleton or skin weights. The original
rigged Rain remains in `../_source/rain/bundle/rain_rig.blend`. Fit the working
base to the shared game rig and costume pose before a character export. Use
the same proportions/rig contract for skins; save only visible anatomical
surfaces in each assembled dressed character. Kestrel is still the priority.

## Attribution and license

**Rain Rig © Blender Foundation | cloud.blender.org**

Source: https://studio.blender.org/characters/rain/v2/
License: **CC BY 4.0** — https://creativecommons.org/licenses/by/4.0/

Modifications: the unmasked anatomy and facial meshes were selected; wardrobe,
animation drivers and original rig modifiers were removed; geometry and shape
keys were scaled to 1.70 m; standard clay review materials were applied. Keep
this credit, license link and modification record with derived assets and in
the game's asset credits. The source permits commercial use and adaptation.

Rebuild with Blender 5.2:
`-b --factory-startup --disable-autoexec -P assets/characters/_shared/build_female_source.py`
No embedded source Python scripts execute during the extraction.

`source_qa.json` lists bounds, UVs and retained shape keys. Renders are in
`renders/`. The source anatomy is a starting point; it still needs Kestrel's
adult face/proportions, painted finish, hairstyle and authored costume.
