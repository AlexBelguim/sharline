# SOLACE: build notes

Solace is the female field medic / healer agent. Her base is the TRELLIS.2 image-to-3D generation **seed 42**
(`trellis/solace_trellis_s42.glb`, the art director's pick). `build_solace.py` turns it into a rigged, game-ready
character. It is a **placeholder** until the planned remake (DIRECTION_LOG item 11). The build re-runs from scratch,
starting from the raw glb, and takes about 6 minutes on the RTX 5080 (the GPU is shared): about 3.5 min for stage A,
15 s for B, 15 s each for N and D, a few seconds for C, and 80 s for the stage-E renders.

```
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup
    -P "F:/git/val etf/assets/characters/solace/build_solace.py" -- [--from A|B|N|C|D|E] [--to ...] [--no-renders]
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup
    -P "F:/git/val etf/assets/characters/solace/check_solace.py"          # verification report on solace.glb
```

The stage order is **A B N C D E**. Each stage saves `_work/<stage>.blend`, so you can re-run later stages on their
own with `--from`. `_work/` is git-ignored scratch, and it also holds the diagnostic renders in `_work/diag/`.

| File | Contents |
|---|---|
| `build_solace.py` | Entry point and stage driver |
| `sol_lib.py` | Stage A (import, clean, cull, carve, rebuild, **cut out the TRELLIS drone**); stage B driver (bakes, materials, face texture + face ORM); diagnostics |
| `sol_geo.py` | Hole filling: constrained-Delaunay patches with membrane + Poisson-bulge heights |
| `sol_tex.py`, `sol_face.py` | Texel-space texture fixes and the painted face texture (numpy only) |
| `sol_pose.py` | **Stage N**: rest-pose normalisation onto Kestrel's rest pose (temporary rig, applied to the mesh) |
| `sol_parts.py` | Stage C: Bloom module + bud vanes, harness straps, emblem, glow vial, **procedural `SOL_Drone`** + its dock cradle |
| `sol_joints.py`, `sol_rig.py` | Stage D: joints from mesh cross-sections, Kestrel bone conventions, armature, weights, pose tests |
| `sol_out.py` | Stage E: sockets, export, renders, contact sheets, 64 px silhouette sheet |
| `check_solace.py` | Read-only checks on the exported glb: rig vs Kestrel, hair/bud clipping, weight leaks, open vanes, nodes, symmetry, mesh stats |
| `solace.blend` / `.glb` / `.fbx` | Deliverables (textures packed / embedded) |
| `textures/` | PNG copies of the generated maps (`SOL_BaseColor`, `SOL_ORM`, `SOL_Normal`, `SOL_Face`, `SOL_FaceORM`) |
| `renders/` | Beauty turnaround, head close-ups, Bloom closed/open, pose tests, contact sheets, `silhouette_64.png` |

## Numbers

* Height 1.68 m from the bounding box (hair included; the body is about 2 cm under the style guide's 1.68 m without
  hair). Feet on Z=0, centred, facing −Y. Her RIGHT is −X.
* **53,844 triangles** in total (style-guide target 30–50k, hard max 70k): `SOL_Body` 39,008 · `SOL_Gear` 2,812 ·
  `SOL_Bloom` 5,332 · `SOL_Bloom_Vane_C/L/R` 1,815 / 1,566 / 1,571 · `SOL_Drone` 1,740.
* GLB 9.5 MB. It embeds five PNG textures: base colour 2048², ORM 2048², normal 2048², face 1024² and face ORM 1024².
* 53 bones, at most 4 influences per vertex. Only `JOINTS_0` / `WEIGHTS_0` are used.

## Objects and materials (one material per primitive)

| Object | Kind | Materials |
|---|---|---|
| `SOL_Armature` | armature (UE5 mannequin names, Kestrel's rest frames) | none |
| `SOL_Body` | skinned TRELLIS mesh (the TRELLIS drone is cut out) | `M_SOL_Body` (atlas base / ORM / normal), `M_SOL_Face` (front-projected face texture + face ORM) |
| `SOL_Gear` | skinned extras | `M_SOL_Charcoal` straps, `M_SOL_Sand` + `M_SOL_Coral` emblem, `M_SOL_Glow` vial, `M_SOL_Gunmetal` vial caps, `M_SOL_Graphite` drone dock cradle |
| `SOL_Bloom` | rigid, bone-parented to `spine_03` | `M_SOL_Graphite` (mount, spine, yoke, clamps, hub), `M_SOL_Glow` (core, hub ring, 2 LEDs) |
| `SOL_Bloom_Vane_C/L/R` | rigid children of `SOL_Bloom` | `M_SOL_IvoryHard` shell (outside and inside), `M_SOL_Coral` rim + edge bands |
| `SOL_Drone` | rigid child of `SOL_SOCKET_DroneDock` (origin at its centre, identity local transform) | `M_SOL_IvoryHard` shell, `M_SOL_Graphite` band / bezel / antenna, `M_SOL_Glow` lens + vent |

`M_SOL_Glow` is the only emissive material: coral, strength 4 through `KHR_materials_emissive_strength`. It is used
only on the Bloom core (seen through the two vane seams), the hub ring, the two yoke status LEDs, the injector vial
and the drone's eye lens and underside vent. `M_SOL_Coral` (non-emissive) is linear (0.80, 0.16, 0.10): deeper than
the palette coral, which rendered as pale pink on ivory; it matches the coat's coral piping. Procedural materials are
flat colours and single-sided. The body and face materials are double-sided, because the TRELLIS surface is an open
single sheet.

## Bones

`root > pelvis > spine_01 > spine_02 > spine_03 > neck_01 > head`;
`spine_03 > clavicle_l/r > upperarm > lowerarm > hand > thumb/index/middle/ring/pinky_01..03`;
`pelvis > thigh_l/r > calf > foot > ball` (`_l` = her LEFT = +X).

**Shared rest pose and frames (review round 2).** The skeleton uses Kestrel's rest frames, so one glTF animation set
drives both agents. `check_solace.py` compares the rest local rotations with `kestrel.glb`: on the 23 non-finger
joints the maximum difference is 4.3° (the hands), the median 0.0°, and none is over 10°. The fingers still differ
(median 18°) because they follow the fused TRELLIS mittens.

* **Stage N** first re-poses the mesh. A temporary rig (heat weights with the proxy fallback, plus the weight rules)
  aims the upper arms, forearms, hands, thighs and shins at Kestrel's rest directions (`KES_DIRS`, measured from
  `kestrel.glb`, mirrored and L/R-averaged). The feet only take Kestrel's 20° toe-out, so the soles stay flat. The
  deformation is applied as SOL_Body's new rest shape, and each sole is put back on Z=0 through the lower-leg weights.
  This also fixes the lopsided TRELLIS stance: before, her left leg stood under the body (foot X +0.047 against
  −0.213 on the right) and her left arm hung back.
* **Stage D** finds the joints again from the mesh, then `sol_rig.kestrel_conventions` puts the spine (with
  Kestrel's slight S-curve), neck, head, clavicles and limb chains on Kestrel's directions. The measured segment
  lengths are kept, and the ankles go to Kestrel's 0.09 m height. The shoulders sit at the same depth on both sides.
  L/R joint asymmetry is now at most 3 cm (the TRELLIS hands); it was 17 cm.
* **Rolls (Kestrel's convention):** on the pelvis, spine, neck, head, thigh and calf, local Z points forward (−Y).
  On the clavicle, arm, hand, finger, foot and ball bones, local Z points up (+Z projected). Bone Y always points to
  the child. Elbows flex about local Z, so the pose tests use roll-independent world-axis / target-direction posing.

## Skinning

* Blender bone-heat weighting **fails on the TRELLIS shell** and leaves 100 % of the verts unweighted. The build
  detects this and runs the **voxel-proxy fallback**: a 4 mm solidify plus a 6 mm voxel remesh (about 94k verts),
  heat weights on the proxy, then a nearest-face-interpolated Data Transfer back to the body. Round 2 dropped the
  proxy decimation and added the solidify. On the re-posed body, the bare voxel remesh returned a third of the
  surface and the decimated proxy made every bone fail. The build now asserts that the proxy solve worked.
* Weight rules on top (`apply_weight_rules`):
  * the head, face and scalp hair are rigid on `head` and blend into the neck below the jaw;
  * the **ponytail** blends `head` → `neck_01` → `spine_03` down its length, and takes 35 % `clavicle_r` where it
    lies on her right shoulder;
  * the **bracer** is rigid on `lowerarm_r`, and the **pouch** is rigid on `pelvis`;
  * the **coat tail** below the waist blends `pelvis` with up to 62 % of the thigh on its side (95 % in stage N, so
    the flaps follow the re-aimed legs);
  * Laplacian smoothing of every non-rigid vert;
  * **leak rules (round 2):**
    * leg weights fade out between Z 0.96 and 1.00, so none reaches above the belt;
    * no cross-side weights beyond 6 cm from the midline;
    * finger weights only in front of the wrist;
    * the fused finger pairs (index+middle, ring+pinky) are **tied**: the pair's weights are averaged per segment,
      so a fused mass follows the mean of its two bones instead of shearing;
  * normalisation and a cap of 4 influences.

  `check_solace.py`: 0 verts with leg weight above Z 1.00, 0 cross-side verts, 0 unweighted.
* `SOL_Gear` (straps, emblem, vial, dock cradle) copies its weights from the body surface.

## Bloom module (procedural, brief section 4i)

`SOL_Bloom` holds:

* a graphite mount plate conformed to the rebuilt coat back (+3 mm), Z 1.08–1.395;
* 7 spine vertebrae, spaced 0.048;
* yoke arms kept 13 mm off the coat along their whole path;
* shoulder clamps seated on the shoulder, with two coral status LEDs;
* a hub with a glowing ring;
* the glowing core spindle (0.78 × `bud_r`, Y 0.62), capped at Z 1.425.

The brief's coordinates are used with a +10.6 mm Y offset measured from the coat back.

**Vanes (closed bud).** `SOL_Bloom_Vane_C/L/R` are sectors of the elliptic bud surface (the brief's `bud_r(z)`
table, Y depth 0.62).

* Angles are measured in the XY plane from +X toward the back. C spans 58.5°–121.5°, L spans −66°–48.5° and R mirrors L.
* The two back seams are 10° wide (about 12 mm), and the glowing core shows through them.
* **Upper-bud bend (round 2):** above Z 1.33 the bud bends back along a smooth Y shear, up to 4.5 cm at C's tip
  (Z 1.555). The hair clears it when she looks up 45°. The lower bud, the hinges and the front-view tips do not move.
* L/R flare outward from Z 1.28 to tips at (±0.142, 0.200, 1.540), 1.5 cm higher than before. In the front view both
  tips rise above the shoulders.
* Shells are solidified 6 mm toward the core with a coral rim. **Coral edge bands (round 2):** the outer faces along
  both side edges of every vane are coral (11.5 % of C's span, 7.5 % of L/R's). From behind the seams read as bold
  coral lines, as in v04, and the bud separates from the ivory coat at 64 px.
* The vanes are triangulated in the build, coincident tip verts are welded and zero-area slivers removed. The
  imported glb shows one zero-area sliver on vane R.

**Hinges.** Each vane has its **origin on its hinge**, at the brief's `SOL_PIVOT_Vane_*`. Its **local +X is the hinge
axis**, so opening is a positive rotation about local X. The glTF extras are `open_angle_deg` (C 30, **L/R 21**),
`closed_angle_deg` 0 and `hinge_axis_local` "X". The node's rest rotation is the closed bud, so the engine sets
`rotation = rest * RotX(angle)`. Measured on the glb:

| Vane | Tip moves when open |
|---|---|
| C | 0.194 m back, 0.086 m down |
| L | 0.131 m toward +X, 0.071 m down (X reach 0.273) |
| R | 0.131 m toward −X, 0.071 m down |

## Heal drone (procedural, brief section 4k; round 2)

`SOL_Drone` is a separate object. The game can hide it, or detach it and fly it for MEND DRONE. Its origin is at its
centre (0.175, −0.073, 1.029), on the left hip, and its local transform under `SOL_SOCKET_DroneDock` is identity. It
consists of:

* an ivory shell (r 0.050, Z scale 0.92; the brief says 0.040, enlarged so the hip ball and its eye read at 64 px);
* a graphite thruster band low on the shell;
* a graphite bezel ring with a recessed coral Glow lens and a dark pupil, facing (0.707, −0.707, 0);
* a dim Glow vent underneath;
* a graphite antenna stub tilted 15° back.

The shell sits 4 mm off the hip. A graphite cradle cup in `SOL_Gear` (pelvis-skinned) holds it and stays on the hip
when the drone launches.

Stage A cuts the TRELLIS drone out of the body: 592 shell faces inside 1.10 × the fitted sphere (centre
(0.161, −0.063, 1.024), r 0.058) and 151 antenna faces, plus the antenna piece cut loose. The hip hole is closed with
a 273-face membrane patch.

## Sockets (empties)

| Empty | Position (Blender, m) | Parent | Notes |
|---|---|---|---|
| `SOL_SOCKET_Halo` | (0, 0.029, 1.900), 0.22 above the head top | bone `head` | extras: `use_position_only` true, `halo_anchor_bone` "head", `halo_offset_up_m` 0.42. Engine rule: halo position = head-joint world position + world up × 0.42, world-level. Do not inherit head pitch/yaw, or a 20° nod swings it 0.14 m. |
| `SOL_SOCKET_WeaponR` | (−0.482, −0.014, 0.915) | bone `hand_r` | **grip origin at the web of the hand** (between the index knuckle and the thumb root, 1.2 cm off the palm). Weapon convention: local −Y along the fingers (muzzle), +Z thumb side. Checked with `mako_default.glb` attached. |
| `SOL_SOCKET_WeaponL` | (0.500, −0.014, 0.887) | bone `hand_l` | same |
| `SOL_SOCKET_Injector` | (−0.478, 0.008, 1.020), bracer muzzle | bone `lowerarm_r` | local −Y fires along the forearm toward the hand |
| `SOL_SOCKET_DroneDock` | (0.175, −0.073, 1.029), drone centre | bone `pelvis` | world-aligned; **`SOL_Drone` is its child** |
| `SOL_SOCKET_BloomVFX` | (0, 0.195, 1.330), bud core centre | object `SOL_Bloom` | world-aligned |

These names follow the task. The brief used `SOL_SOCKET_Hand_R/L`, `SOL_SOCKET_Drone` and `SOL_SOCKET_Bloom`.

## What was fixed on the TRELLIS model (round 1)

1. **Normalised**: scaled to 1.68 m, centred, welded (61.7k → 38.4k verts), with tiny loose bits removed.
2. **Hidden inner sheet removed**: TRELLIS.2 shells are double-walled, with an outer surface plus a sheet 3–6 mm
   inside. Faces that no outside view can see were found with flat face-ID renders from 328 orthographic views and
   deleted, keeping a 1-ring safety band.
3. **Back module**: the hallucinated box backpack and the coat surface it hid were deleted. The coat back was rebuilt
   as a constrained-Delaunay membrane patch with a 1.8 cm Poisson bulge. The procedural Bloom module replaces the box.
4. **Shoulder fins**: the pointed plates TRELLIS put on the shoulders were rebuilt as smooth domes.
5. **Eyes**: the eyeliner smear modelled as geometry was cut and refilled with slightly convex lid patches.
6. **Textures** (texel space, from Cycles position/normal bakes):
   * skin regraded;
   * pants grey → sand; pouch → dark sand;
   * back of both thighs → sand;
   * hair dark warm brown-black, non-metallic, roughness 0.80;
   * shoulder mark painted out;
   * new ORM.
7. **Face**: its own 1024² front-projected texture with painted almond eyes, groomed brows and closed lips.
8. **Right-temple flakes** painted hair-dark (`sol_tex.SHARD_POLYS`) with a matte face ORM.
9. **Bloom emblem**: a sand hex patch with three coral almond petals (never four, never a cross) on her LEFT upper arm.
10. **Glow**: the injector vial on the RIGHT bracer.
11. **Harness**: straps from the yoke clamps over both shoulders to the TRELLIS chest straps; the right strap passes
    under the ponytail.

Sides were checked against the brief. The ponytail, bracer and pouch are on her RIGHT (−X). The emblem and drone
are on her LEFT (+X).

## Review fixes (round 2)

These apply `review/critique_latest.json`. Verification comes from `check_solace.py` (output below) and the renders
in `renders/`.

**Majors**

1. **Hair clipping through vane C on look-up: fixed.**
   * The upper bud bends back (4.5 cm at C's tip) and C's tip is lowered 1.565 → 1.555.
   * The glow core is capped at Z 1.425; above that, the hair reached into the bud's front gap.
   * The mount top was lowered 1.42 → 1.395 (vertebrae spaced 0.048), and the yoke root and arms were lowered and
     kept 13 mm off the coat.
   * The shoulder clamps are seated: lifted until their underside clears the coat by 2 mm.

   Head-region faces against vanes C/L/R and the module, with head pitch split 45 % neck / 55 % head:
   * rest, look-up 20/30/40/45°, turns left 45/70/90°, turn right 45° and look-up 25° + turn 60° either way: all 0;
   * a 70–90° right turn: 4–5 pairs, where the ponytail root brushes the right yoke arm.

   Before, the look-up gave 61 pairs at 30° and 112 at 40°; the review also counted 87 yoke/collar pairs at rest.
2. **Heal drone as its own entity: fixed.** The TRELLIS drone is cut out and patched (stage A). The procedural
   `SOL_Drone` (brief 4k) is a child of `SOL_SOCKET_DroneDock` with its origin at its centre, and has a dock cradle
   on the hip. The old drone's torn eye ring and lumpy shell are gone with it.
3. **Bone frames differ from Kestrel's: fixed.** Stage N re-poses onto Kestrel's rest pose; stage D uses Kestrel's
   spine/clavicle/limb directions and rolls. The largest non-finger difference went from 89.5° to 4.3°, and joints
   over 30° (all joints) from 16 / 53 to 3 / 53 (fingers only).

**Minors**

* **Hair loop round the left ear (headset read): fixed (paint).** The skin inside the loop (`sol_tex.EAR_LOOP_L`) is
  painted hair-dark with hair roughness, so it reads as hair over the ear.
* **Ragged nape: partly fixed.** The skin-coloured crumpled bits behind the jaw and at the nape are painted in the
  charcoal mock-neck colour (soft edge toward the jaw). Most of the nape sits behind the bud. The small open
  cavities at the back hair edges remain (TRELLIS hair geometry).
* **Bud ivory-on-ivory from behind: fixed.** Coral edge bands plus the deeper coral read as coral seams at 64 px
  from behind (checked on a 64 px downscale of the back render).
* **Silhouette hooks: partly fixed.** The L/R tips are 1.5 cm higher. The ponytail was not pushed out: it is one
  solid TRELLIS mass, so it still sits inside the torso outline in the front silhouette. Left for the remake.
* **Mitten hands: mitigated.** The fused pairs' weights are tied (see Skinning). A grip now closes each mitten as one
  piece instead of shearing it. Proper per-finger hands are a priority for the remake.
* **Paint artifacts: fixed.**
  * The pouch recolour is limited to the pouch (Z < 1.013, X < −0.084), so the sand rectangle on the charcoal
    under-layer is gone.
  * Grey scratches by the left strap are filled from the surrounding ivory.
  * Tan specks (the old pants mask hitting coat creases) are gone.
  * The smeared pouch flap itself is unchanged.
* **Coral accents: fixed.**
  * A 12 mm coral band runs on the coat hem (back, sides and front wrap) and on both back-split edges. It follows the
    hem fold: rim texels facing down or toward the split, dilated 12 mm.
  * The emblem petals and vane rims use the deeper coral.
  * The lab-coat back pocket flap is painted out to plain ivory; its low relief remains.
* **Brief deviations: partly fixed.**
  * The skin regrade is about 11 % less saturated (`SKIN_T` 0.475/0.335/0.262).
  * The brows are softer: inner ends higher and thinner, painted lighter.
  * The mouth corners are lifted 1.7 mm into the calm half smile.
  * Kept, as the review accepted: the coat length (front to mid-thigh) and the TRELLIS chest straps running to bust
    level. They are relief geometry, and trimming them needs the remake.
* **Lopsided rest skeleton: fixed** by stage N (see Bones). The legs are now square and the feet toed out 20° like
  Kestrel's; the arms are at Kestrel's ~54° A-pose, and the elbows sit near the torso's mid-depth (they hung 4–6 cm further back).
* **Halo socket 0.42 m from the head joint: fixed on the asset side.** The extras carry the engine rule (see
  Sockets). `art/HALO_SHIELD_SPEC.md` is outside this folder. Recommendation for its owner: write the same rule
  (head joint + world up × offset) for every agent; Kestrel has the same offset.
* **Weight leaks: fixed** (leak rules; 0 / 0 / 0 in the check).
* **arms_down pose test: fixed.** It uses target-direction posing (upper arms at (±0.12, 0.02, −1)), and the arms
  hang at the sides (`renders/pose_arms_down_*`). Crouch, run and grip were rewritten roll-independent as well.
* **Technical points:**
  * Weapon sockets moved to the web of the hand.
  * The yoke path is pushed 6 mm off the coat.
  * Vane degenerate faces 9 → 0 / 0 / 1.
  * The review's "892 islands / 215 under 12 verts" came from the glTF import splitting verts at UV seams. In
    Blender SOL_Body has 2 islands (19,371 + 44 verts), so there was nothing to drop.
  * Height is unchanged: the style guide's 1.68 m is meant without hair, and the body is about 2 cm short of it.
    Rescaling would move every measured paint/joint constant, so it is left for the remake.
* **Open vanes reading as wings: fixed.** L/R open 21° (was 32°), reaching X ±0.273 (was ±0.32).

`check_solace.py` on the final build:

```
[RIG]   non-finger joints: max 4.3 deg (hand_r), median 0.0, > 10 deg: 0 / 23
[SYM]   L/R joint asymmetry max 0.030 m (hands; legs 0.016, shoulders 0.000)
[CLIP]  look-up 20-45: 0; turns left 45/70/90: 0; turn right 45: 0, 70: 5, 90: 4 (module only); up 25 + turn 60: 0
[WGT]   leg weight above Z 1.00: 0 verts; cross-side: 0 / 0; max influences 4; unweighted 0
[OPEN]  Vane_L / Vane_R open 21 deg: X reach +-0.273
[NODES] SOL_Drone parent SOL_SOCKET_DroneDock (bone pelvis), identity local transform
```

## Known limitations (honest list)

* **Hair** is TRELLIS geometry: chunky, a little lumpy, with no separate strands. The ponytail is one solid mass and
  does not show in the front silhouette. The left-ear loop now reads as hair over the ear; it is still a modelled
  loop. Small open cavities remain at the back hair edges, and a flat flake and a fold at the right temple show in
  extreme close-ups.
* **The face is painted, not modelled.** It has no eyeball geometry and no blendshapes.
* **Finger joints and mitten hands.** The finger frames do not match Kestrel's (median 18°), and the fingers are
  fused in pairs (tied weights). Finger animation needs per-agent offsets or the remake.
* **Stage N reshapes the TRELLIS limbs** by up to about 40° at the wrists and 35° at the elbows (forearm and hand
  re-aim). Glove cuffs and sleeve folds carry a little stretch.
* **Coat tail** uses blended rigid weights (pelvis + thigh), not cloth bones. A very high kick pushes the thigh
  through the front flap.
* **Knee straps** look patchy in a deep crouch (TRELLIS texture).
* **The yoke clamps are rigid on `spine_03`** while the straps are skinned to the clavicles, so a small gap can open
  at a shrug. On a 70–90° right head turn the ponytail root brushes the right yoke arm (4–5 face pairs).
* **The rebuilt coat back, shoulder caps and drone hip patch** have a flat ivory colour (one pinned texel). The
  module and the drone cover most of it.
* **Paint is texel-resolution**, so the 12 mm coral hem band has slightly stepped edges up close, and a few pale
  texels sit on the very rim.
* **Cycles GI**: the core's glow tints the inner vane faces pink. A real-time engine without GI shows cleaner ivory
  vanes with crisp coral seams.
* **Triangles** total 53.8k, over the 50k target (under the 70k max). The new drone (1.7k) and the vane edge bands
  pushed it up.
