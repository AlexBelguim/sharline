# VARGA — modeler's build brief (character, Armor Tier 4)

Authoritative spec for the procedural Blender build. **If a concept image disagrees with this text, this text wins.**
Follow `art/STYLE_GUIDE.md` for everything not covered here (units, budgets, `bc.*` helpers, export).

## 0. Orientation (read first)
- Metres, Blender Z-up, feet on Z = 0, centred on X = Y = 0. **She faces −Y**, so the Blender Front view looks at her face.
- **Her LEFT is +X** (the right side of the screen in Front view). **Her RIGHT is −X.**
  - Pauldron = her LEFT shoulder = **+X**. Gauntlet = her RIGHT forearm = **−X**.
  - Suffix `_L` = her left (+X), `_R` = her right (−X).
- A-pose: arms 45° below horizontal, in the XZ plane (Y = 0), palms facing the thighs.
  **Recommended method:** build each arm and everything attached to it (sleeve, gauntlet, glove, pauldron) in a
  **T-pose** (arm along ±X at Z = 1.430), then rotate the group about the world Y axis through the shoulder joint:
  left group **+45°**, right group **−45°**. Exception: the pauldron has its own pivot (+50°, see §4.3).
  Shoulder joints: J_L = (+0.185, 0, 1.430), J_R = (−0.185, 0, 1.430).
- Object names `VAR_<Part>`, materials `M_VAR_<Surface>`, helpers/cutters start with `_`.
- Height 1.76 m to the top of the skull; the ponytail loop rises to ≈ 1.79 m.

## 1. Identity and silhouette
Varga is the heavy breacher / support: a tall (1.76 m), strong, athletic woman in her early 30s with broad
shoulders, muscular bare forearms and a strong jaw. She is clearly a woman and is not bulked up into a male
frame: her waist is narrower than her shoulders and her hips are wider than her waist. She crafts abilities with a
fabricator gauntlet on her right forearm.
She wears the heaviest armor in the game. Tier 4 is a graphite plate carrier with chest, back and side plates, a
segmented collar and one large three-lame pauldron on her left shoulder. The armor sits over an olive short-sleeve
compression shirt, and the outfit continues with olive cargo pants, heavy graphite knee guards, a sand belt with
pouches and chunky sand boots. Her dark-auburn hair is pulled into a high ponytail that loops back and becomes one
thick braid down to mid-back. The sides of her head are shaved, with a three-line pattern on the right side.
In silhouette she is top-heavy and asymmetric:
- a stepped armored mass over the **left** shoulder;
- a blocky gauntlet on the **right** forearm;
- the ponytail loop and braid seen in side and back views;
- bare arms between the armored parts.
Amber is the only accent colour, and it appears in exactly three places (§6).

## 2. Body proportions (metres)
Stylised hero proportions: about 7.3 heads tall, with slightly large head, hands and feet. Build only the skin that
can be seen. Do not model skin under the shirt, carrier or pants.

| Landmark | Z | Notes |
|---|---|---|
| Ponytail loop apex | 1.790 | hair volume, above the 1.76 height |
| Crown (skull top) | 1.760 | |
| Hairline (front) | 1.705 | |
| Brow line | 1.668 | |
| Eye line | 1.645 | eye centres X ±0.031 |
| Nose tip | 1.598 | Y −0.112 |
| Mouth | 1.561 | |
| Chin | 1.520 | head height crown→chin **0.240** |
| Collar base / neck base | 1.425 | |
| Shoulder joint (J) | 1.430 | X ±0.185 |
| Armpit | 1.315 | |
| Bust (widest chest) | 1.300 | |
| Underbust | 1.220 | |
| Waist (narrowest) | 1.095 | |
| Belt centre | 1.030 | |
| Hip joint | 0.920 | X ±0.095 |
| Crotch | 0.830 | **inseam 0.83** |
| Knee centre | 0.480 | X ±0.120, Y −0.010 |
| Ankle centre | 0.085 | X ±0.140 (feet ≈ 0.28 apart) |
| Boot top | 0.230 | |

| Measure | Value |
|---|---|
| Head (cranium) W × D × H | 0.154 × 0.208 × 0.240 (ears add to 0.170 W) |
| Neck diameter | 0.112 (radius 0.056), Z 1.43–1.56, centre Y +0.012, top tilted 8° forward |
| Shoulder width (bideltoid, over shirt) | **0.50** (±0.25) |
| Chest W × D (shirt) | 0.36 × 0.25 |
| Waist W × D | 0.28 × 0.19 |
| Hip width (pants, without pockets) | 0.40 |
| Upper arm / forearm / hand length | 0.30 / 0.26 / 0.19 |
| Upper-arm radius (deltoid → bicep → elbow) | 0.060 → 0.054 → 0.043 |
| Forearm radius (below elbow → mid → wrist) | 0.047 → 0.043 → 0.030 (wrist is an ellipse 0.034 Y × 0.024 Z): **thick, muscular** |
| Foot / boot length | 0.315 boot (sole); upper 0.125 wide, sole 0.135 wide |

Front-view silhouette targets, for checking renders:
- Right fingertips to left fingertips ≈ 1.43 m (fingertips at X ±0.715, Z 0.90).
- Elbows at (±0.397, 1.218); wrists at (±0.581, 1.034).
- Pauldron outer edge ≈ X +0.42. Right shoulder edge ≈ X −0.25.

## 3. Layering (inside → out); keep ≥ 3 mm between stacked surfaces
1. **Skin**: head, neck, arms from the sleeve hems down, and fingers.
2. **Shirt** (olive): torso, shoulder caps and short sleeves. It shows at the sleeves, around the armholes and on the
   bare right shoulder. Where it pokes slightly out at the armpits above the side plates, that is intended.
3. **Pants** (olive): from the waist (under the belt) down to the boot tops. The cuffs tuck into the boots.
4. **Boots**: over the pant cuffs.
5. **Carrier cloth** (charcoal): torso shell, shoulder straps.
6. **Plates** (graphite): chest, abdomen, back, sides. They sit on the carrier cloth.
7. **Collar** (graphite): on top of the carrier and straps, around the neck.
8. **Belt** (sand): over the pants waist, just under the carrier's lower edge. **Pouches and craft kit** hang on the belt.
9. **Pauldron**: over the left shoulder strap and left sleeve. **Gauntlet**: over the right forearm.
   **Gloves**: over the hands.
10. **Knee guards and straps**: over the pants.
11. **Hair**: over the head. The braid hangs outside the back plate.

## 4. Part list
Coordinates are world space unless the text says "T-frame". The T-frame is the arm laid along ±X at Z = 1.430, with
distance **u** measured outward from the shoulder joint, **s** = Y (−s is the front/thumb side) and **h** = Z offset
from the arm axis (+h is the back of the hand).
Tri estimates are evaluated triangles.

### 4.1 Head, face, skin (`M_VAR_Skin` unless noted), ≈ 7 k tris
| Object | Size / position | Method |
|---|---|---|
| `VAR_Head` cranium | ellipsoid semi-axes 0.077 X, 0.100 Y, 0.105 Z, centre (0, +0.008, 1.655): top 1.760, forehead Y −0.092, back Y +0.108 | `sphere` scaled. **Alternative (recommended for a clean organic join):** make cranium + jaw + cheekbones + brow as metaball ellipsoids (or overlapping meshes + Remesh voxel 0.004), convert/apply, then Decimate to ≈ 3 k tris |
| jaw (part of `VAR_Head`) | strong square jaw: block 0.125 W × 0.115 D × 0.075 H centred (0, −0.022, 1.556). Front-bottom verts narrowed to a 0.050-wide square chin at Z 1.520, Y −0.085; jaw angle (gonion) 0.115 wide at Z 1.548, Y +0.020 | `box` with the chin verts scaled in X, Subsurf 2, union with the cranium |
| cheekbones | 2 flattened ellipsoids r 0.025 at (±0.045, −0.070, 1.615) | `sphere`, merged into head |
| brow ridge | 0.115 × 0.020 × 0.018 at (0, −0.088, 1.668) | `box` + bevel, merged |
| `VAR_Nose` | straight, medium: side profile bridge (Y −0.088, Z 1.660) → tip (−0.112, 1.598) → base (−0.095, 1.588); 0.020 wide at the bridge, 0.032 at the nostrils | `profile_extrude` of the side profile, bevel 0.004 |
| `VAR_Lips` (`M_VAR_Lips`) | mouth 0.048 wide, upper lip Z 1.566, lower lip Z 1.556, front Y −0.093; full but not exaggerated; neutral-confident set (corners level) | 2 flattened capsules |
| `VAR_Eyes` (`M_VAR_EyeWhite` + `M_VAR_Iris`) | eyeballs r 0.012 at (±0.031, −0.080, 1.645), set into shallow sockets; iris disc r 0.0065 on the front, dark brown; upper lash line = charcoal strip 0.026 × 0.003 over each eye; almond shape, looking straight ahead | `sphere` + `cylinder` (disc) |
| `VAR_Brows` (`M_VAR_Hair`) | thick straight brows, each 0.036 × 0.007 × 0.004, over X ±0.012…±0.048 at Z 1.670, inner ends 8° lower (determined look). **Her RIGHT brow (−X) is split by a 0.004 gap at X −0.033** | `box` + bevel |
| `VAR_Scar` (`M_VAR_Scar`) | **right eyebrow (−X)**: a pale line 0.003 W × 0.026 H × 0.002, tilted 10°, through the brow gap at (−0.033, −0.093, 1.668), running about 8 mm above and below the brow | `box`, shrink-wrapped onto the head |
| `VAR_Ears` | flattened ellipsoids 0.012 × 0.032 × 0.055 at (±0.079, +0.012, 1.632), tilted back 10°. Fully visible because the sides are shaved | `sphere` scaled |
| `VAR_Neck` | see §2 | `cylinder` r 0.056 tapered to 0.052, or a loft |
| `VAR_Arm_L/R` (skin) | T-frame rings (u, radius): (0.10, 0.058), (0.16, 0.054), (0.22, 0.050), (0.30, 0.043) elbow, (0.35, 0.047) forearm bulge, (0.42, 0.043), (0.50, 0.035), (0.56, 0.030) wrist. Visible from the sleeve hem (u 0.125) down. The right forearm under the gauntlet can be left out | ring loft along the arm (write a small `loft_rings()` helper in the build script; **do not edit `blender_common.py`**), then rotate ±45° |
| `VAR_Hand_L/R` | T-frame: palm box 0.085 (s) × 0.100 (u 0.565–0.665) × 0.032 (h); 4 fingers as capsules r 0.0095, lengths 0.085 / 0.095 / 0.090 / 0.075, curled 15° toward the palm; thumb capsule r 0.0115, 0.065 long, rooted at the front (−s) side at u 0.585 and angled 40° forward/down. Palm faces −Z in the T-pose (inward/down once rotated) | `box` + bevel, `cylinder` + `sphere` caps |

### 4.2 Hair (`M_VAR_Hair`, `M_VAR_Shaved`; ties are `M_VAR_Cloth`), ≈ 5 k tris
| Object | Size / position | Method |
|---|---|---|
| shaved sides | Material zone on `VAR_Head`: every face above Z 1.600 and behind the ear-front line (Y ≥ −0.055), excluding the top hair band → `M_VAR_Shaved`. No extra geometry | face material assignment |
| `VAR_ShavePattern` | **Her RIGHT side (−X) only.** 3 parallel lines, each 0.055 long × 0.005 wide, 0.013 apart, rising toward the front at 40°. Centred over and slightly behind the right ear at (−0.077, +0.025, 1.680) | `boolean` grooves 2 mm deep into a shaved shell, **or** skin-coloured strips 1 mm proud (`M_VAR_Skin`), shrink-wrapped |
| `VAR_HairTop` | Swept-back top band 0.115 wide (X ±0.057), so the shaved sides show. Runs from the front hairline (Y −0.100, Z 1.705, overhanging the forehead by 0.008) to the tie, standing 0.012–0.020 off the skull. Build it as **5 side-by-side clumps** (elongated ellipsoids, about r 0.026 × 0.115 long) that converge on the tie, giving shallow strand grooves | `sphere` scaled and rotated ×5, join |
| `VAR_HairTie` (`M_VAR_Cloth`) | at (0, +0.075, 1.752), r 0.020, 0.022 long, axis pointing back and up 35° | `cylinder` + bevel |
| `VAR_Ponytail` | Loop from the tie: path (0, 0.075, 1.752) → apex (0, 0.120, 1.790) → (0, 0.175, 1.775) → (0, 0.205, 1.720) → (0, 0.205, 1.665). Built from 3 tapered clumps, r 0.036 → 0.030, overlapping along the path. **The loop is a side-view silhouette hook** | `sphere` scaled and oriented along the path |
| `VAR_Braid` | **12 lobes**, centreline (0, +0.205…0.208, 1.665 → 1.215), spaced 0.0375. Each lobe is an ellipsoid 0.060 long along the path, width (X) 0.062 at the top tapering to 0.040 at the bottom, thickness (Y) 0.042 → 0.030. Lobes alternate rotation ±28° about the Y axis and X offset ±0.008, so the back view reads as chevrons (classic stylised 3-strand braid). From Z 1.44 down, the braid hangs just off the back plate: plate surface Y +0.178, braid inner face ≥ Y +0.186 | `sphere` ×12, join, `shade_smooth` |
| `VAR_BraidEnd` | tie (`M_VAR_Cloth`) r 0.016 × 0.016 at Z 1.200; tuft = 3 cones r 0.022 → 0.004, 0.075 long, fanned ±12°, tips at Z ≈ 1.125 (mid-back) | `cylinder` (radius2 for cones) |

### 4.3 Armor and torso gear, ≈ 12 k tris
| Object | Material | Size / position | Method |
|---|---|---|---|
| `VAR_Shirt` torso | `M_VAR_Shirt` | ring loft, centre Y 0 (Z: rx, ry): 1.475: 0.070, 0.065 (under the collar) / 1.455: 0.150, 0.085 / 1.420: 0.180, 0.105 / 1.340: 0.175, 0.122 / 1.260: 0.163, 0.122 / 1.150: 0.140, 0.105 / 1.060: 0.150, 0.110 / 0.990: 0.165, 0.115 (tucked into the pants). Plus shoulder caps = spheres r 0.066 at J_L / J_R | ring loft + `sphere` |
| `VAR_Sleeve_L/R` | `M_VAR_Shirt` | T-frame u 0.0 → 0.125, r 0.066 → 0.061, with a hem roll ring r 0.063 × 0.010 at u 0.125. Short sleeve to mid-bicep | `cylinder`(radius2) + ring |
| `VAR_Carrier` (plate bag + cummerbund) | `M_VAR_Cloth` | torso shell, centre Y 0 (Z: rx, ry): 1.430: 0.150, 0.120 / 1.360: 0.165, 0.148 / 1.280: 0.172, 0.150 / 1.200: 0.168, 0.135 / 1.120: 0.160, 0.125 / 1.065: 0.162, 0.125. Open top, 0.012 Solidify | ring loft + Solidify |
| `VAR_ShoulderStrap_L/R` | `M_VAR_Cloth` | padded arch over each shoulder at X ±0.115, 0.075 wide (X). Side profile (Y, Z): from the chest-plate top (−0.150, 1.420) over (0, 1.478) down to the back-plate top (+0.150, 1.420), 0.022 thick | `profile_extrude` of the arch-band side profile, width 0.075 |
| `VAR_ChestPlate` | `M_VAR_Graphite` | Front-view outline (x, z): (−0.11, 1.43) (0.11, 1.43) (0.16, 1.38) (0.16, 1.24) (0.12, 1.19) (−0.12, 1.19) (−0.16, 1.24) (−0.16, 1.38): 0.32 W × 0.24 H, 0.030 thick. **Faceted:** centre facet 0.18 wide, front face at Y −0.185 (at Z 1.30); two side facets angled back 28°; whole plate tilted top-back 6°. Raised sternum sub-panel 0.12 W × 0.09 H × 0.006 at Z 1.29–1.38 (the IV sits on it). Horizontal panel groove at Z 1.25 | `profile_extrude` of the outline, rotated 90° about Z so the thickness runs along Y; cut into 3 facets (or SimpleDeform Bend ≈ 50°); bevel 0.006 / 2 seg; `boolean` groove |
| `VAR_TierPips` **(emissive)** | `M_VAR_Amber` | **Raised Roman numeral "IV"**, centred at X 0, Z 1.335 on the sternum panel, 0.004 proud. "I": bar 0.012 W × 0.055 H at X −0.026. "V": two bars 0.012 W × 0.058 H, rotated ±16° in the XZ plane, meeting at the bottom, centred X +0.012. Whole numeral ≈ 0.065 W × 0.058 H, tilted with the plate | `box` ×3 + bevel 0.002 |
| `VAR_AbPlate` | `M_VAR_Graphite` | outline (x, z): (−0.13, 1.20) (0.13, 1.20) (0.13, 1.10) (0.09, 1.065) (−0.09, 1.065) (−0.13, 1.10); 0.025 thick; front at Y −0.150. Its top slides 0.01 under the chest plate. Optional horizontal split into 2 tiers (as in the concepts) | `profile_extrude` rotated, bevel 0.005 |
| `VAR_BackPlate` | `M_VAR_Graphite` | outline (x, z): (−0.12, 1.44) (0.12, 1.44) (0.15, 1.40) (0.15, 1.18) (0.12, 1.14) (−0.12, 1.14) (−0.15, 1.18) (−0.15, 1.40); 0.028 thick; outer surface Y +0.178; flatter than the chest plate. **No grab handle** (the braid hangs there) | `profile_extrude` rotated, bevel 0.006 |
| `VAR_SidePlate_L/R` | `M_VAR_Graphite` | side-view outline (y, z): (−0.07, 1.31) (0.07, 1.31) (0.085, 1.29) (0.085, 1.14) (0.065, 1.12) (−0.065, 1.12) (−0.085, 1.14) (−0.085, 1.29); 0.025 thick (X), centred X ±0.183. Plain rounded rectangles, no disc (ignore the disc in the turnaround) | `profile_extrude` (native YZ, width along X), bevel 0.005 |
| `VAR_Collar` | `M_VAR_Graphite` | **Closed, segmented high collar** (style of `concept_head.png`), centre (0, +0.012). Inner radius 0.072, outer radius 0.105 at the base → 0.098 at the top. Base at Z 1.425. The top edge slopes from **1.535 at the back to 1.500 at the front** so the chin (1.520) clears it | `lathe` with **steps = 8** (octagonal segments) or 16; `boolean` the sloped top with a tilted box; 2 shallow horizontal grooves; bevel 0.004 |
| `VAR_Pauldron` (3 lames) | `M_VAR_Graphite` | **Her LEFT shoulder (+X).** It has its own pivot: an empty `_PauldronPivot` at **(0.200, 0, 1.440)**, rotated **+50° about Y**. Each lame is built in the pivot's local frame as a **faceted, flared open shell**: a frustum along local +X (radius grows outward, so it reads as a bell), with an elliptical cross-section (Y radius = 1.12 × r) and **8 flat facets over a 240° arc** centred on local +Z. The 120° opening faces local −Z, toward the armpit. Solidify 0.022 inward, bevel 0.004 / 2 seg, `shade_smooth(25°)`, so the facets stay crisp. **Lame 1 (top):** x −0.050 → +0.060, r 0.085 → 0.125. **Lame 2:** x +0.035 → +0.130, r 0.090 → 0.128. **Lame 3:** x +0.105 → +0.195, r 0.093 → 0.130. Each lower lame starts tucked *under* the lame above it (shingle overlap, 3–5 mm clearance) and clears the arm by ≥ 15 mm. **Verified world bounds** (blockout): L1 X 0.135–0.334, Z 1.354–1.533; L2 X 0.188–0.382, Z 1.299–1.471; L3 X 0.232–0.425, Z 1.249–1.419; Y ±0.146. Top at about collar height, outer edge ≈ X +0.42 | the `lame()` helper in §10 (bmesh arc rows → faces → Solidify), parented to the pivot. The left shoulder strap runs *under* lame 1; small overlap hidden inside the shell is fine |
| `VAR_PauldronStrip` **(emissive)** | `M_VAR_Amber` | **One** thin strip on **lame 1 only**, in the same pivot frame: local x 0.025 → 0.037 (≈ 0.012 wide), r 0.1185 → 0.123 (≈ 3 mm proud of lame 1). It is a 96° arc running from the **front horizontal (facing −Y) up over the top**, made with the same `lame()` helper (arc 96°, 4 facets, Solidify 0.004) and then rotated +42° about local X. In the Front view it reads as a short amber line near the top of the pauldron, and in the 3/4 and side views as a curve over the shoulder (verified) | `lame()` |
| `VAR_PauldronStrap` (optional) | `M_VAR_Cloth` | ring r 0.060, 0.022 wide around the left upper arm at u 0.15 (arm frame, rotated +45°) | `cylinder` ring |

### 4.4 Gauntlet (her RIGHT forearm, −X), ≈ 3.5 k tris
Build it in the right-arm T-frame (arm along −X, u outward from J_R), then rotate with the arm **−45° about Y through
J_R**.
| Object | Material | Size / position (T-frame) | Method |
|---|---|---|---|
| `VAR_Gauntlet` housing | `M_VAR_Graphite` | u 0.315 → 0.545 (0.23 long). Octagonal cross-section **0.145 (s) × 0.135 (h)**, centred s 0, h +0.008. Corner chamfers 0.025, **except the top-front corner (between +h and −s): a big 0.070 chamfer facet (0.099 wide)** that carries the display. Wrist end tapered to 88 % | `profile_extrude` of the octagon (points in Y,Z; width 0.23 along X), centre X −0.615 in the T-pose; scale the wrist-end verts; bevel 0.008 / 2 seg |
| elbow flare | `M_VAR_Graphite` | u 0.305 → 0.335, frustum r 0.074 → 0.068 | `cylinder(radius2)` along X |
| wrist cuff | `M_VAR_Gunmetal` | u 0.545 → 0.565, ring r 0.052 | `cylinder` |
| dorsal rail | `M_VAR_Graphite` | 0.17 (u) × 0.030 (s) × 0.012 on the top face, centred u 0.43, s +0.030 | `box` + bevel |
| `VAR_GauntletBezel` | `M_VAR_Gunmetal` | hexagonal prism, circumradius 0.055, 0.012 thick, centred u 0.43 on the top-front facet, normal (0, −0.707, +0.707) in the T-pose, with two flats parallel to the forearm axis (0.095 across the 0.099 facet). After the arm rotation its normal is (−0.5, −0.707, +0.5): it faces up, out and **toward the camera**, so it reads in the Front view (verified) | `cylinder(verts=6)` |
| `VAR_GauntletDisplay` **(emissive)** | `M_VAR_Amber` | hexagonal prism, circumradius 0.044 (0.076 flat-to-flat), 0.006 thick, 0.002 proud of the bezel. Optional: a thin graphite inner hex ring (r 0.022, 0.002 proud) hints at a honeycomb | `cylinder(verts=6)` |
| vents | (cut) | 3 slots 0.045 (u) × 0.008 (h), 0.008 deep, 0.018 apart, on the back (+s) face, centred u 0.45 | `boolean` |
| feed cartridge | `M_VAR_Bone` | 0.060 (u) × 0.012 (s) × 0.035 (h), on the back (+s) face at u 0.35 | `box` + bevel |
| fabricator emitter | `M_VAR_Gunmetal` | 2 prongs 0.045 × 0.012 × 0.012 at s ±0.022, h +0.045, reaching from u 0.53 to 0.575 (just past the wrist, over the back of the hand) | `box` + bevel |
| `VAR_HandPlate_R` | `M_VAR_Graphite` | armored back-of-hand plate 0.085 (u 0.570 → 0.655) × 0.075 (s) × 0.014, on the glove at h +0.026 | `box` + bevel 0.004 |

### 4.5 Gloves, belt, pouches, kit, ≈ 4 k tris
| Object | Material | Size / position | Method |
|---|---|---|---|
| `VAR_Glove_L/R` | `M_VAR_Cloth` | **Fingerless**: a shell 3 mm over the palm box plus the first 0.025 of each finger and thumb; wrist band 0.020 wide. Fingers stay skin | duplicate the palm and finger bases, scaled 1.06 |
| `VAR_Belt` | `M_VAR_Sand` | Z 1.005 → 1.055, ring loft rx 0.178, ry 0.132, 0.012 thick (outer face at Y −0.144 front, +0.144 back) | ring loft + Solidify |
| `VAR_Buckle` | `M_VAR_Graphite` | 0.065 × 0.018 × 0.045 at (0, −0.150, 1.030) | `box` + bevel |
| `VAR_Pouch_L/R` (front) | `M_VAR_Sand` | double-cell ammo pouches 0.095 W × 0.045 D × 0.085 H, centred (±0.100, −0.167, 1.010) (tops ≈ belt top, 12 mm below the ab plate). Vertical groove between the cells; flap 0.100 × 0.050 × 0.012 on top; small graphite snap tab per cell | `box` + bevel 0.006, `boolean` groove |
| `VAR_Pouch_Hip` | `M_VAR_Sand` | her left hip side: 0.050 (X) × 0.080 (Y) × 0.090 (Z) at (+0.215, +0.010, 0.990) | `box` + bevel |
| `VAR_CraftKit` | `M_VAR_Sand` + `M_VAR_Bone` + `M_VAR_Gunmetal` | **Back of her RIGHT hip.** Cradle: a sand open-top box 0.170 (X) × 0.055 (Y) × 0.060 (Z) at (−0.100, +0.172, 0.990). Canister: lying along X, centre (−0.100, +0.185, 1.025), bone body r 0.032 × 0.150 with 2 grooves, gunmetal end caps r 0.034 × 0.018. Small graphite clip strap over it | `box` + `boolean`, `lathe` (profile r/h, then `rot=(0,90,0)`) |

### 4.6 Legs, ≈ 9 k tris
| Object | Material | Size / position | Method |
|---|---|---|---|
| `VAR_Pants` pelvis | `M_VAR_Pants` | ring loft, centre Y 0 (Z: rx, ry): 1.070: 0.170, 0.125 / 0.980: 0.190, 0.130 / 0.880: 0.200, 0.135 / 0.800: 0.190, 0.130, capped at the bottom | ring loft |
| `VAR_Pants` legs ×2 | `M_VAR_Pants` | tubes along the leg axis hip (±0.095, 0, 0.92) → knee (±0.120, −0.010, 0.48) → ankle (±0.140, 0, 0.085). Rings (Z: rx, ry around the axis): 0.86: 0.110, 0.120 / 0.72: 0.100, 0.108 / 0.58: 0.085, 0.092 / 0.48: 0.078, 0.085 / 0.36: 0.080, 0.086 (bloused) / 0.26: 0.075, 0.080 (blouses over the boot top) / 0.20: 0.058, 0.064 (cuff, inside the boot shaft). The tops overlap into the pelvis piece | ring loft per leg; join with the pelvis |
| `VAR_CargoPocket_L/R` | `M_VAR_Pants` | on the outer thighs: 0.130 (Y) × 0.150 (Z) × 0.025 (X), centre (±0.218, −0.010, 0.680); flap 0.140 × 0.050 × 0.012 at Z 0.735–0.760 | `box` + bevel 0.006 |
| `VAR_KneeGuard_L/R` | `M_VAR_Graphite` | heavy shield over the knee, centre (±0.120, −0.115, 0.490), 0.130 W × 0.170 H × **0.040** thick (back face at Y −0.095). Outline (x, z rel.): (−0.05, 0.085) (0.05, 0.085) (0.065, 0.04) (0.065, −0.03) (0.03, −0.085) (−0.03, −0.085) (−0.065, −0.03) (−0.065, 0.04). Faceted (centre facet plus 2 side facets back 30°); raised horizontal ridge 0.10 × 0.015 × 0.008 at z +0.01 | `profile_extrude` rotated, bevel 0.006 |
| `VAR_KneeStrap_L/R` | `M_VAR_Cloth` | 2 bands per leg, r ≈ 0.088 × 0.020 tall, at Z 0.43 and 0.55 | `cylinder` rings |
| `VAR_Boot_L/R` upper | `M_VAR_Sand` | ankle centre (±0.140, 0, 0.085), toes turned out 6°. Side profile (Y relative to the ankle, Z absolute): (0.080, 0.040) (0.085, 0.230) (−0.050, 0.230) (−0.058, 0.150) (−0.130, 0.105) (−0.185, 0.085) (−0.205, 0.060) (−0.200, 0.040); width **0.125**. The shaft (0.125 × 0.135) must be bigger than the pant cuff at Z 0.20, so the cuff tucks in and the Z 0.26 ring blouses over the boot top | `profile_extrude`, bevel **0.018 / 3 seg** (chunky, rounded) |
| `VAR_BootSole_L/R` | `M_VAR_Graphite` | profile: (0.095, 0) (0.095, 0.045) (−0.210, 0.045) (−0.225, 0.030) (−0.215, 0); width 0.135; 3 tread grooves underneath | `profile_extrude`, bevel 0.008, `boolean` |
| `VAR_BootToe_L/R` | `M_VAR_Graphite` | toe cap from Y −0.130 to −0.212, Z 0.035–0.100, 0.130 wide | `profile_extrude`, bevel 0.012 |
| boot details | `M_VAR_Graphite` / `M_VAR_Cloth` | instep strap 0.130 × 0.025 × 0.035 at Y −0.060, Z 0.130, tilted 35° (graphite); padded top collar ring r 0.072 × 0.030 at Z 0.215 (charcoal cloth) | `box`, `cylinder` |

**Budget:** ≈ 41–45 k tris in total. Targets are 30–50 k, hard max 70 k. Use bevel modifiers with 1–3 segments and
`bc.shade_smooth`, and use Subsurf only on the head and hair.

## 5. Hair breakdown (summary for modeling)
1. **Top band**: 5 swept-back clumps, 0.115 wide in total, from the forehead hairline back to the tie.
2. **Shaved sides**: a material zone on the head (dark-auburn stubble over skin). **Right side only:** 3 diagonal
   lines (§4.2).
3. **Tie**: high on the back of the crown, at Z 1.752.
4. **Ponytail loop**: 3 clumps arcing up and back (apex Z 1.79), then falling.
5. **Braid**: 12 alternating chevron lobes hanging straight down the **back** (Y ≈ +0.205) to Z ≈ 1.215.
6. **End**: a tie and a 3-cone tuft, tips at Z ≈ 1.125.
No loose bangs and nothing in front of the face. The face must be fully visible.

## 6. Colour and material table (linear RGB, `bc.material`)
| Material | Token | Base colour | Rough | Metal | Optional tex (`art/textures/`, multiply) | Used on |
|---|---|---|---|---|---|---|
| `M_VAR_Graphite` | graphite | (0.030, 0.033, 0.040) | 0.55 | 0.15 | `worn_paint.png` mix 0.30 | all hard plates, collar, pauldron, gauntlet housing, knee guards, boot soles and toes, buckle |
| `M_VAR_Gunmetal` | gunmetal | (0.11, 0.115, 0.12) | 0.35 | 0.85 | `brushed_metal.png` 0.25 | hex bezel, wrist cuff, emitter prongs, canister caps |
| `M_VAR_Cloth` | charcoal-cloth | (0.035, 0.037, 0.045) | 0.85 | 0 | `fabric_soft.png` 0.35 | carrier shell, straps, gloves, hair ties, knee straps |
| `M_VAR_Shirt` | olive | (0.12, 0.13, 0.08) | 0.80 | 0 | `fabric_soft.png` 0.30 | shirt and sleeves |
| `M_VAR_Pants` | olive | (0.12, 0.13, 0.08) | 0.80 | 0 | `fabric_ripstop.png` 0.40 | pants, cargo pockets |
| `M_VAR_Sand` | sand | (0.36, 0.28, 0.18) | 0.75 | 0 | `leather_soft.png` 0.30 | belt, pouches, kit cradle, boot uppers |
| `M_VAR_Bone` | bone | (0.55, 0.52, 0.46) | 0.50 | 0 | `polymer_stipple.png` 0.25 | canister body, gauntlet feed cartridge |
| `M_VAR_Skin` | skin medium | (0.38, 0.22, 0.14) | 0.55 | 0 | `skin_soft.png` 0.20 | head, neck, arms, fingers |
| `M_VAR_Hair` | dark auburn *(brief-defined)* | (0.100, 0.022, 0.012) | 0.55 | 0 | `hair_strands.png` 0.45 | hair clumps, braid, brows |
| `M_VAR_Shaved` | stubble *(brief-defined)* | (0.17, 0.085, 0.055) | 0.75 | 0 | — | shaved sides |
| `M_VAR_Scar` | *(brief-defined)* | (0.52, 0.33, 0.24) | 0.50 | 0 | — | eyebrow scar (and the shave lines if made as strips) |
| `M_VAR_Lips` | *(brief-defined)* | (0.20, 0.09, 0.065) | 0.50 | 0 | — | lips |
| `M_VAR_EyeWhite` / `M_VAR_Iris` | *(brief-defined)* | (0.62, 0.58, 0.52) / (0.025, 0.012, 0.006) | 0.30 | 0 | — | eyes |
| **`M_VAR_Amber`** | **amber (Varga)** | (1.0, 0.32, 0.04), **emission (1.0, 0.32, 0.04)**, strength 4 | 0.40 | 0 | — | **ONLY:** ① gauntlet hex display, ② raised "IV" on the chest plate, ③ the single strip on pauldron lame 1 |

The accent rule: amber is the one accent colour, and it lives only in those three emissive zones. There is **no**
other amber anywhere: no amber bullet tips, wrist slits, belt lights or second pauldron strip.
Colour blocking from top to bottom:
- dark graphite armor mass on the upper body;
- skin-coloured bare arms;
- sand belt band;
- olive legs;
- graphite knees;
- sand boots.
Keep that read, and do not add other colours.

## 7. Silhouette hooks and the 5 things that MUST read correctly
Silhouette hooks: a **big stepped LEFT pauldron**, a **chunky RIGHT gauntlet**, and the **high ponytail loop with a
long braid**.
1. **Pauldron on her LEFT shoulder (+X)**: three stacked graphite lames with one amber strip. It makes the clear
   asymmetric top-left mass in the Front view (outer edge ≈ X +0.42, versus about −0.25 on the right). Her right
   shoulder has only the olive sleeve.
2. **Gauntlet on her RIGHT forearm (−X)**: a blocky graphite housing about 0.145 × 0.135, clearly wider than the
   forearm. The amber hex display must face up, out and toward the camera so it is visible in the Front view. Her left
   forearm is **bare** (fingerless glove only).
3. **Hair**: the ponytail loop above and behind the crown, plus a thick chevron braid hanging straight down the back to
   mid-back. It must read in the side and back silhouettes. The shaved sides make the head narrow at the temples.
4. **Tier-4 heavy armor**:
   - chest, back and side plates;
   - a segmented high collar;
   - the pauldron;
   - a raised glowing **IV** on the chest.
   All of it is graphite, chunky and bevelled. It should read as heavier than Tier 3 at a glance.
5. **A strong, clearly female hero**:
   - broad shoulders and muscular bare forearms;
   - a waist narrower than shoulders and hips;
   - an un-occluded face with a strong square jaw, the scar through her RIGHT brow, and a confident neutral expression.
   - She is fully clothed, with no exaggerated anatomy.

Check: render the Front, Right and Back views as a flat black silhouette and downscale it to 64 px tall. Points 1–3 must
still be identifiable.

## 8. Which concept image to trust for what
All images are in `art/concepts/varga/`. Images were generated with Krea2. Generated images often put both
accessories on the same arm, so **trust this brief for left/right placement, not the images.**

| File | Trust it for | Where it deviates (the brief wins) |
|---|---|---|
| **`concept_main.png`** (= v06), front | Overall look and colour blocking; the faceted tiered carrier; IV placement on the chest; the stepped pauldron with its amber slot; how massive the gauntlet is; knee guards; sand boots; sand belt and pouches; correct sides (gauntlet on the image-left arm = her right; pauldron on the image-right shoulder = her left) | The braid drapes forward over her left shoulder (brief: it hangs straight down the back). The left forearm has an extra graphite bracer (brief: bare, fingerless glove only). The right hand is a full robotic glove (brief: fingerless glove plus back-of-hand plate). The pauldron shows about 4 lames (brief: 3). The IV is flat paint (brief: raised and emissive). No scar, shave pattern or craft kit is visible |
| **`concept_turnaround.png`** (= v02), front/side/back | Proportions (head : shoulders : legs, wide stance); side-view depths (torso, ponytail loop and braid path, boot length); back view (back plate, braid down the spine); the segmented high collar; the slab gauntlet with its fingerless glove and bare left forearm; correct sides in both the front and back views | Extra amber: bullet tips in the belt pouch, two pips at the chest corners, a second strip on the pauldron (brief: only the 3 zones). No IV numeral. The side plate shows a big round disc (ignore it: plain side plate). The canister sits on the front belt (brief: back of the right hip). Dark boots (brief: sand uppers, graphite soles and toes) |
| **`concept_head.png`** (= v08), head study | Face shape (strong square jaw, brows, nose, lips); the hair system (swept-back top, high tie, ponytail loop, braid, end tie and tuft); the shaved sides and the **3 diagonal shave lines** (on her right side, as seen in the side profile); the segmented collar style | No eyebrow scar is visible (add it on her RIGHT brow per §4.1). The collar is drawn as a uniform-height ring (brief: slopes lower at the front). The shirt neckline is drawn without a carrier |
| v04, front | Alternative front with correct sides; reference for **hex display size and readability**, and for the pauldron stair-step | Shirt is sand (brief: olive). Carrier is cropped above the waist (brief: down to the belt). Soft fabric collar (brief: armored). Black boots |
| v01, v03, v05, v07 | **Rejected for placement**: the gauntlet is on her LEFT arm. Use them only for detail flavour: the gauntlet panelling in v03 and v05, the braid side profile in v07, the hair in v01 | Gauntlet on the wrong arm. Darkened lower legs in v01 and v03. Extra amber on the wrist in v05 |

## 9. Build and verification notes
- Suggested order:
  1. landmarks (empties at J, elbow, wrist, hip, knee and ankle, named `_J_L` and so on);
  2. head and hair;
  3. shirt, carrier, plates, collar;
  4. arms in the T-frame, with sleeves, gauntlet, gloves and pauldron; then rotate;
  5. pants, knees, boots;
  6. belt, pouches, kit;
  7. materials, `bc.uv_all()`, `bc.stats()`.
- Use parent empties for the arm groups (`_ArmPivot_L/R` at J), so the A-pose angle stays one number.
- Check renders with `bc.setup_studio` + `bc.render_views` (front, right, back, three_quarter):
  - The pauldron must be on screen-right in the Front render.
  - The gauntlet display must be visible in the Front render.
  - The braid must be visible in the Right and Back renders.
- Known simplifications that are fine for the prototype:
  - no skin under clothing;
  - cloth is lofted rings, not simulated;
  - hair is clumps, not strands;
  - no rig or weights.

## 10. Tested helper for the pauldron lames (put it in your own build script)
The pauldron and gauntlet numbers above were checked in a quick Blender 5.2 blockout. These are the A-pose rotation
signs, the pauldron bounds, the strip placement and the display normal.
`blockout_check.png` shows it (front / three-quarter / right / back), with a proxy body plus the final pauldron, gauntlet
and display. The strip uses the same ky 1.12 ellipse, so after the 42° roll it can sit up to about 2 mm off the lame
in places. Nudge r by ±0.002 if it floats or sinks.
```python
def lame(name, x0, x1, r0, r1, arc=240, thick=0.022, steps=8, ky=1.12, mat=None):
    """Faceted flared open shell along local +X; arc centred on local +Z (opening faces -Z)."""
    bm = bmesh.new()
    a0, a1 = math.radians(90 - arc / 2), math.radians(90 + arc / 2)
    rows = [[bm.verts.new((x, ky * r * math.cos(a0 + (a1 - a0) * i / steps), r * math.sin(a0 + (a1 - a0) * i / steps)))
             for i in range(steps + 1)] for (x, r) in ((x0, r0), (x1, r1))]
    for i in range(steps):
        bm.faces.new((rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i]))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    m = ob.modifiers.new("Sol", "SOLIDIFY"); m.thickness = thick; m.offset = -1
    bc.add_bevel(ob, 0.004, 2); bc.assign(ob, mat); bc.shade_smooth(ob, 25)
    return ob
# pivot = empty at (0.200, 0, 1.440), rotation_euler = (0, radians(50), 0); parent the lames to it.
# strip = lame("VAR_PauldronStrip", 0.025, 0.037, 0.1185, 0.123, arc=96, thick=0.004, steps=4, mat=amber);
#         strip.rotation_euler = (radians(42), 0, 0); parent to the pivot.
```
