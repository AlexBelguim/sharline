# Kestrel v2 — current assembled character

The licensed Rain face, fitted draft costume and solid-lock bob are assembled
on one rig. The professional finish benchmark is still not fully met. Solace
remains paused, and these new character files are not wired into the game yet.

The exported character has 54,384 triangles, 61 unchanged body bones and six
optional hair bones (67 total), UVs on all meshes and at most three normalized
joint influences. The preferred 30–50k target is slightly exceeded; the 70k hard
limit is respected. GLB/FBX independently import, and six body poses pass the
weight/rig checks. Hair motion is verified separately against the actual GLB.

Kestrel v06 controls identity: asymmetric blue-black bob, longer RIGHT (-X)
teal-tipped lengths, translucent LEFT (+X) hex lens, high charcoal collar,
cropped jacket, light bone chest rig, cargos, low boots, LEFT grapple and low
twin jets. No tier pips or heavy armor. Metres, front -Y, Blender Z up, glTF Y up,
soles zero and skull crown 1.70 m. Four sockets: Halo, WeaponR/L and BackAbility.

## Source and license

Rain Rig © Blender Foundation | cloud.blender.org
https://studio.blender.org/characters/rain/v2/
CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/

Adaptations include affine Kestrel head proportions, a focused eyelid/brow pose,
intrinsic face/eye PBR maps, nine retained mouth/cheek expression shapes and
binding to the shared game rig. The source control rig/drivers are not used.
The Rain body is posed to the game frame for garment fitting, retained as a
hidden fitting reference only, with covered anatomy excluded from the export.
Costume, hair and gear are the project's authored design. Retain the credit,
license link and modification record with the derived asset and game credits.

The clean bare working base is ../../_shared/base/female_base_source.blend.
It remains an editable reference without final game skinning. The assembled
Kestrel here has the shared rig and does not export a hidden full nude body.

## Wardrobe and hair

kestrel_master.blend contains separately editable wardrobe pieces.
skin_manifest.json inventories 16 slots, nodes, materials, sockets and rig.
Consolidation stays within the same slot/material family. Only the default
outfit is built. See SKINS.md.

Hair is a fixed scalp plus eight solid overlapping locks, with six cosmetic
tip bones. No alpha cards or simulated strands. HAIR.md describes those bones
and the required future game motion. The actual GLB test keeps roots/scalp fixed
and moves the tips about 7.9 mm in a small pose. No in-game hair motion exists yet.

## Build and verification

Run make_surface_maps.py, make_face_map.py and rain_face_maps.py with ordinary
Python if maps need regeneration. Then run Blender 5.2:
-b --factory-startup --disable-autoexec -P build_kestrel.py

The builder imports kestrel_face_rain.py, kestrel_outfit_finish.py,
rain_anatomy.py, kestrel_hair.py and skin_parts.py. Existing shared hand/body
rig helpers and costume frames are preserved. The original placeholders are
separate; no game code was changed.

Embedded standard PBR maps distinguish fabric, webbing, polymer and light
plates. Existing Krea2 detail supplies restrained intrinsic paint/normal detail.
Face/eyes use continuous painted colour maps; hair uses portable vertex paint
and strand normal/roughness maps. No baked directional light or unlit body shader.
Only small tech accents emit.

kestrel_qa.json and pose_qa.json record source rig checks. verify_exports.py
imports GLB and FBX independently; export_import_qa.json records the results.
review_export.py produces fresh GLB renders. verify_hair_motion.py produces
hair_motion_qa.json. Gameplay clips, automatic hair motion and a complete facial
animation system are not included.

Continue final art review against v06 and the user's benchmark. Focus on hair
flow/overlap, face identity and garment/material polish before resuming Solace.
