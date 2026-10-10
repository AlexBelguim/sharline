# KESTREL: finished character (from TRELLIS.2 seed 123)

The recon and mobility agent, finished from the TRELLIS.2 image-to-3D generation `trellis/kestrel_trellis_s123.glb`.
The base was chosen by the art director and the user. The result is a game-ready, rigged and skinned character.

## Files
| File | What |
|---|---|
| `kestrel.glb` | Game asset (Bevy). Skinned meshes, 53-joint skin, sockets as child nodes of their bones, textures embedded. Y-up. |
| `kestrel.fbx` | Same content for Unreal/Unity (armature + meshes + socket nulls, `add_leaf_bones=False`, textures embedded). |
| `kestrel.blend` | Final Blender scene (images packed). |
| `textures/` | Copies of the four 2048² maps: `KES_BaseColor` (sRGB), `KES_Normal`, `KES_ORM` (R = AO, G = roughness, B = metallic), `KES_Emission`. |
| `renders/` | Cycles, 900×1200: `kestrel_{front,three_quarter,right,back,left,three_quarter_back}.png` + `kestrel_sheet.png`; head close-ups `kestrel_head_*.png` + `kestrel_head_sheet.png`; pose tests `pose_*.png` + `kestrel_pose_sheet.png`; socket check `sockets_*.png` (gold ring = halo socket, red blocks = weapon sockets, muzzle along −Y). View names follow Blender: `*_right.png` is the camera at +X, so it shows **her left** (tech) side. `*_left.png` shows her right (hair) side. |
| `build_kestrel.py` + `kes_*.py` | The re-runnable build (below). |
| `trellis/` | Raw TRELLIS generations (inputs, untouched). |

## Rebuild (from the raw glb, about 4 min including renders)
```
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
    -P "F:/git/val etf/assets/characters/kestrel/build_kestrel.py" -- [--from A|B|C|D|E] [--to A..E] [--no-renders]
```
Each stage saves `_work/<stage>.blend` (gitignored), so later stages can be re-run alone. `KES_HEAT_CACHE=1` reuses the last heat-weight
solve while you tune weight overrides. It is for development only, and a clean build never uses it.

| Stage | Module | Does |
|---|---|---|
| A | `kes_lib.py` | Import, normalise (1.70 m, feet on Z=0, centred, facing −Y), weld split UV seams (62k→39k verts), remove the TRELLIS "glasses arm" wire, fill holes, relax creases at the left temple, decimate 79.4k→66.0k tris (face and hands protected, UVs kept). |
| B | `kes_tex.py`, `kes_face.py`, `kes_fix.py` | Texture fixes in object space: Cycles bakes the position/normal of every texel (the TRELLIS atlas is hundreds of tiny charts), numpy edits, then a Cycles AO bake and a Cycles hair-dye bake. |
| C | `kes_eyepiece.py` | Eyepiece: hex glass lens, glowing rim, graphite housing, straps, earpiece. |
| D | `kes_rig.py`, `kes_skin.py` | Joints from mesh cross-sections and a hand analysis, UE5-named armature, heat weights on a voxel proxy, hand/finger weights, rigid parts. |
| E | `kes_export.py`, `kes_pose.py` | Sockets, export, renders, pose tests. |

## Numbers
- **Triangles: 66,898.** `KES_Body` 66,000 + `KES_Eyepiece` 898. That is under the style guide's 70k hard max and the task's 80k. The budget target is 30k–50k, so this is TRELLIS density. No LODs.
- **Height** 1.70 m (hair top). The skin is 32,289 verts (56.6k after glTF splits UV seams). Max 4 influences per vertex, no unweighted vertices.
- **Materials (4):**
  - `M_KES_Body`: the single body PBR. Base colour + TRELLIS normal + ORM. Roughness/metallic are TRELLIS's (matte, 0.6–0.96 rough). The occlusion channel is a new Cycles AO bake, because TRELLIS's R channel was per-chart black/white noise. The emission map lights only the teal jet rings, strength 4.
  - `M_KES_EyeGlass`: teal, alpha 0.42, BLEND, faint emission 0.12.
  - `M_KES_EyeGlow`: emissive teal 3.5, on the lens rim and the earpiece status light.
  - `M_KES_Graphite`: eyepiece housing, straps, earpiece.

## Rig (53 bones, UE5 mannequin names; `_l` = her left = +X)
`root` (non-deforming, at the origin) → `pelvis` → `spine_01` → `spine_02` → `spine_03` → `neck_01` → `head`;
`spine_03` → `clavicle_l/r` → `upperarm_l/r` → `lowerarm_l/r` → `hand_l/r` →
`thumb_01..03_l/r`, `index_01..03_l/r`, `middle_01..03_l/r`, `ring_01..03_l/r`, `pinky_01..03_l/r`;
`pelvis` → `thigh_l/r` → `calf_l/r` → `foot_l/r` → `ball_l/r`.

The rest pose is the A-pose as modelled: arms about 54° below horizontal, wide stance. Main joints, her left side:

| Joint | Position (x, y, z) |
|---|---|
| hip | (0.085, 0, 0.865) |
| knee | (0.148, 0.039, 0.495) |
| ankle | (0.205, 0.080, 0.090) |
| ball | (0.247, −0.034, 0.032) |
| shoulder | (0.170, 0, 1.352) |
| elbow | (0.345, 0.011, 1.114) |
| wrist | (0.495, −0.013, 0.914) |

The head bone runs from 1.47 to 1.70. Legs, clavicles and upper arms are symmetrised. Hands and fingers follow each hand's own mesh. Bone axes use Blender's convention (Y along the bone). For UE5, retarget with an IK Rig (the names match).

**Skinning:**
- Heat weights solve on a 6.5 mm voxel remesh of the body, at 10× scale, because Blender's heat solver fails on mm-sized faces. A DataTransfer modifier carries them back to the mesh.
- Hands and fingers get distance-to-bone weights, because the proxy fuses the fingers.
- Rigid parts:

| Part | Bones |
|---|---|
| head, face, hair incl. the teal tips | `head` |
| eyepiece | `head` |
| neck skin | `neck_01`/`head` along a jaw plane |
| collar | `spine_03` + up to 45 % `neck_01` |
| jet pack, chest plate | `spine_03` |
| belt pouches | `pelvis` |
| holster | `thigh_r` |

Pose tests (arms down, deep crouch, running stride, head turned 45°, fists) are in `renders/kestrel_pose_sheet.png`.

## Sockets (empties, bone-parented; glTF nodes carry a `usage` extra)
| Socket | Parent bone | Rest position | Notes |
|---|---|---|---|
| `KES_SOCKET_Halo` | `head` | (0.005, 0.02, 1.92), 0.22 m above the top of the hair | **Use position only.** The halo stays level and does not follow head rotation (HALO_SHIELD_SPEC). |
| `KES_SOCKET_WeaponR` | `hand_r` | (−0.538, −0.026, 0.890), palm centre lifted 2 cm to the centre of a grip | Local −Y = hand forward (wrist→knuckles, the muzzle convention); +Z = thumb side (the weapon's "up"). The weapon's grip origin snaps here. Expect a small per-weapon offset in-engine. |
| `KES_SOCKET_WeaponL` | `hand_l` | (0.527, −0.028, 0.876) | Same convention, mirrored hand. |

## What was fixed (against v06 / ref_sheet)
- **Left eye and eyepiece (DIRECTION_LOG 3).**
  - TRELLIS baked the eyepiece as an opaque light-blue disc, ~5 mm thick, standing 6–12 mm proud of her left eye. A strap was painted across her right brow, and a wire loop stuck out of the temple.
  - The wire is removed.
  - The face is repainted on a front-projected canvas. That gives new almond eyes with dark-brown irises, a lash line and a soft lower lid, and straight, determined brows with the inner end lower. The baked strap and smears are gone. Her left eye is the mirror of her right and is painted on the old disc.
  - A new **translucent teal hex lens** (7.4 × 5.4 cm, yawed 15° to follow the face) sits in front, with a glowing teal rim and a slim graphite housing that encloses the disc's rim. The eye is clearly visible through the glass.
  - Two thin straps run along the temple to a compact earpiece on her left ear, with a teal status light. A third strap runs diagonally up across the forehead and tucks under the fringe on her right (v06).
  - The normal/AO maps are flattened where the paint changed.
- **Hair:** blue-black with **teal-dyed tips**. A Cycles bake of mix(base, teal, mask), where the mask = hair-coloured texels (blue/red ratio in linear space) × low-on-the-hair (object-space Z, about 6 cm gradient band). The band sits higher on her short left side. The navy collar lining that matches the hair colour is excluded spatially.
- **Collar:** teal piping painted along the top rim, matching v06. The teal zip piping was already there.
- **Gloves:** the skin hand shows through TRELLIS's thin glove shell as orange blotches. Repainted as black fingerless gloves (wrist to knuckles), with a majority filter on the fingers.
- **Jet pack:** black smudges and the "W"/"4" marks on the bone pods are removed. The tan band at each pod base is now a **teal glow ring** (emissive, front_apose).
- **Misc:** brown smear on her right cheek, temple scribbles, proper AO.

## Known limitations (honest)
1. **Face quality is capped by TRELLIS.** The head is a coarse double-layer shell and the face texture is about 1.2 mm/texel, so painted features go soft in tight close-ups.
   - Her right cheek shows a dark vertical line. It's the real gap where the fringe hangs in front of the face, and it reads like a crease in front and head-turn views.
   - Her left temple, between the lens and the ear, is patchy (repaint plus TRELLIS creases). It's mostly under the straps.
2. **Her left eye has no lid geometry.** It is paint on the old lens disc inside the eyepiece housing. Through the tinted glass it reads correctly from the front and three-quarter views. From steep side angles the eye sits slightly forward. Her right eye keeps TRELLIS's slit lids.
3. **The lens is larger than v06's** because it must cover the old disc. It clears the brow but covers a little of the upper cheek.
4. **The hair is rigid on the head bone** (no hair bones). On a 45° head turn the long bob's teal tips pass through the collar. The collar shears slightly on big turns (it is 45 % neck at the top).
5. **Hands:**
   - The skin hand and the glove shell are two TRELLIS layers. Fists close properly in the tests, but extreme curls can show a little skin through the glove, and a few orange specks remain on the gloves.
   - The thumb chain is short (`thumb_02` ≈ 1–1.5 cm) because TRELLIS's thumb is stubby.
6. **The jet pack is fully rigid on `spine_03`.** There are no thruster bones and no separate nozzle mesh; the glow is the emissive ring. The cleaned pod side panels read a little flatter than the rest of the painted bone.
7. **Leftover TRELLIS geometry:** about 21 open boundary edges at non-manifold spots (left temple, under the strap) and internal double layers. They're harmless for rendering and skinning (weights come from the voxel proxy).
8. **The texture is still the TRELLIS atlas** (hundreds of tiny charts). Hand-painting it in Krita/Substance is impractical, so make edits through the object-space scripts in `kes_face.py` / `kes_fix.py`.
9. **Over the style-guide target** of 30–50k tris (66.9k, under the 70k max). There's no retopology or LOD chain.
