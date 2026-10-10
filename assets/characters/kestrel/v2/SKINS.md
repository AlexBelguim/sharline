# Kestrel skin construction

Use **a modular source character on one common rig**, with **an assembled GLB
for each skin**. The default skin is the first complete outfit; alternate skins
have not been made yet. Game wardrobe selection is outside this asset change.

## Source parts

`kestrel_master.blend` retains the unjoined source meshes and the common skeleton.
`skin_manifest.json` inventories the slots, actual nodes, materials, triangle
counts, sockets and rig. Each mesh carries portable glTF extras:
`character_id`, `skin_id`, `skin_slot`, `wardrobe_rig`.

Slots are: identity, neck, arms, hands, hair, eyewear, jacket, underlayer,
trousers, footwear, gloves, chest rig, knee pads, waist gear, left ability and
back ability. Consolidation is limited to the same slot and material family.
Hair and the eye lens are cosmetic parts; garments use the same deformation rig.
The bob has a fixed scalp and eight solid overlapping locks, with six optional
hair-tip bones under the shared head bone. See HAIR.md for the motion contract.

Keep Kestrel's recognizable face consistent between skins. Face makeup may be
changed through textures. Hair can be replaced by another head-bound mesh.
The teal lens, straps and earpiece remain one cosmetic eyewear assembly.
Ability skins retain their original grip/socket frames and gameplay silhouette.

## Exports and body coverage

The game loads one finished `kestrel.glb` at identity. A future skin gets its own
assembled GLB with the same bone names, rest pose, weights and socket conventions.
It does not need a duplicate armature for each garment or a clothing simulator.

Each assembled outfit includes only the skin/body surfaces that are visible.
Remove or mask covered anatomical faces in the offline builder. Do not place a
full hidden body under tightly fitted clothes, and do not hide it with alpha
blending. Loose coat/skirt variants need explicit deformation clearance checks.

Start alternate skins with texture/material changes. New outfits and hairstyles
can then replace individual source slots while preserving the base rig.
No alternate outfit or hair is implied by a declared slot: the manifest lists
only parts actually built.

## Art and licensing

Kestrel v06 controls identity and design. The user's polished shooter-character
image controls finish quality; it is not a source of reusable geometry.
The current GLB uses adapted Rain facial anatomy, under CC BY 4.0. Retain
`Rain Rig © Blender Foundation | cloud.blender.org`, the license link, and the
modification record with the asset and credits. The posed Rain body remains
a fitting reference in the master, excluded from the dressed game export.

The character is still in art refinement. Export/rig checks passing does not
mean that the face, hair or overall finish have met the user's quality bar.
