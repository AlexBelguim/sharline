# Shared v2 character builder

`character_v2.py` supplies the same lean anatomy, rest frames and 61-bone hierarchy to Kestrel and Solace.
Kestrel's reference skull height is 1.70 m; every anatomical coordinate and bone length is uniformly scaled
by `height / 1.70` for Solace's 1.68 m. The halo's 0.22 m clearance stays a world-space equipment dimension.
Facing -Y, her left is +X. Feet remain at Z=0 in outfit builds.

The existing authored `female_base.make_recipe` face and joined hand template are reused as procedural
recipes. No mesh imports, image-to-3D, voxel remeshing, heat weights or proxy transfers are used. Only visible
skin is generated: head, ears, neck, forearms and connected five-digit hands. Clothing shells supply the torso,
upper arms, pelvis, legs and footwear. Each hand has three articulated segments per finger and an attached
thumb. Head geometry has explicit horizontal loops, extra lip/eye rows, sculpted nose/lips/cheeks and a smooth
orbital recess; each eye is a spherical almond surface with concentric pupil, iris and limbal geometry.

```python
import character_v2 as cv
base = cv.build_base(prefix='KES', height=1.70,
                     skin=(.62,.42,.33), eye_color=(.16,.30,.26))
shell = cv.body_loft('KES_Jacket', rows, material, sides=32)
cv.bind(shell, base, 'torso')
cv.rigid(hard_gear, base, 'spine_03')
cv.export_character(base, absolute_path_without_suffix)
```

`base` contains `armature`, `joints`, `parts`, `sockets`, `dims`, `materials`, `hand_axes`, `prefix` and `scale`.
`joints` exposes lowercase UE5 bone head coordinates plus uppercase left/right aliases for the source hand
recipe. `dims` includes both eye centres, eye-front Y, eye height/radius, head bounds and requested height.
The primitive helpers `mesh`, `body_loft` and `tube` add UVs. Existing Blender primitives should receive
`bc.smart_uv` or `bc.uv_all` before export.

`bind` takes explicit `torso`, `coat`, `arm_l`, `arm_r`, `leg_l`, `leg_r`, `head` or `pelvis` regions. Joint bands
are normalized and limited to four weights. Clothing regions cannot pick unrelated limb/finger bones.
`rigid` writes one bone weight per vertex, so hard gear remains a portable skinned primitive. Every parent
assignment preserves current world transforms after updating the dependency graph.

Sockets: `<P>_SOCKET_Halo` (head anchor plus position-only/world-up extras), `WeaponR`, `WeaponL` and
`BackAbility`. Weapon origins sit at the web of each hand, with local -Y following finger direction and +Z
toward the thumb. Additional ability sockets use `socket(name, base, bone, location, yaxis, zhint)`.

`pose`, `aim`, `bend`, `twist` and `reset_pose` make static deformation checks without authoring actions.
`export_character` resets the pose, includes the skeleton and sockets, rejects missing UVs or unnormalized
weights, writes a JSON report, and exports GLB/FBX/Blend with no animation clips. Outfit builders own the final
fully clothed exports and rendered previews.

`qa_base.py` creates private head-only views. `qa_export.py` checks a newly created rigid primitive's retained
world transform, exact halo height, normalized weights and the common export path. The private diagnostic
Blend/GLB must not be used as a public full-body screenshot or shipped as a character asset.
