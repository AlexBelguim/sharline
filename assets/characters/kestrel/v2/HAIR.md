# Kestrel hair: solid overlapping locks

The default bob contains a fixed scalp and eight closed 3D locks. They use one
opaque PBR material and UVs, with blue-black intrinsic paint and teal tips.
The scalp closes the root areas; longer locks are separately editable in the
master. This supports changing their outline and arrangement for another skin.
No alpha cards, per-strand geometry, cloth simulation or transparency are used.

The user's SophieJu image guides the construction method. This is original
procedural geometry, not a downloaded Sketchfab hairstyle. An artist profile
alone does not establish a license for individual models.

## Cosmetic rig

The shared body core stays at 61 bones. Six optional children of `head` control
three hair regions, with two bones each:

- `hair_front_r_01`, `hair_front_r_02`: long right-front sweep.
- `hair_side_r_01`, `hair_side_r_02`: right side and rear-side lengths.
- `hair_back_01`, `hair_back_02`: rear bob ends.

Root vertices and scalp are bound only to `head`. Tip influences fade in through
the length, with at most three joint influences on the hair. The left temple
locks stay rigid so the ear device and lens remain clear.

`verify_hair_motion.py` imports the actual GLB and demonstrates 2-degree root and
5-degree tip rotations. `hair_motion_qa.json` proves the fixed roots/scalp remain
unchanged while the ends deform. The test pose is in
`renders/hair_tip_pose_three_quarter.png`.

## Game work still required

The default GLB has the bones and weights. It contains no automatic hair motion.
The game can add damped secondary rotations to these cosmetic bones after its
body animation update. Keep movement small, initially within about 7 degrees,
and check head/collar clearance; long hair variants need separate collision and
motion limits. Preserve bind/rest transforms. Body animation sharing only needs
the unchanged 61-bone core; optional cosmetic bones may vary between hairstyles.

The character is still below the user's full professional finish benchmark.
Geometry/rig validation is not an art-quality approval.
