# KESTREL — modeler build brief (Tier-2 recon / mobility agent)

Authoritative spec for the procedural Blender build. **Where a concept image and this brief disagree, the brief
wins.** Units are metres, Blender Z-up, character **faces −Y**, feet on Z = 0, centred on X = Y = 0, A-pose
(see `art/STYLE_GUIDE.md`). Object prefix `KES_`, materials `M_KES_<Surface>`.

> **Handedness — read twice.** Facing −Y, **her LEFT is +X** (screen-right in Blender's Front view) and **her
> RIGHT is −X**. Blender's *Right* view (camera at +X) therefore shows **her left** side.
> Mnemonic: **her LEFT = the tech side** (monocle, ear-piece, undercut, grapple launcher, belt pouches, cargo
> pocket). **Her RIGHT = the hair side** (long bob sweep, thigh holster).

Files in this folder:

| File | Use it for |
|---|---|
| `concept_main.png` (= `v01.png`) | Overall look, colour blocking, value pattern, gear placement on the front. |
| `concept_turnaround.png` (= `v03.png`) | Front/back layout, back plate + jet-pack placement, collar height, cropped-jacket length. |
| `v06.png` | Face, hair shapes, monocle (octagonal lens) and collar close-up. |
| `v04.png` | Chest-plate shape and the "II" pips, ribbed jacket hem and sleeve cuffs. |
| `v07.png` | Back three-quarter: back plate **with "II"**, jet pods under it, leg/knee straps, boot caps. |
| `v08.png` | True side profile of **her left** (tech) side: undercut, ear-piece, monocle arm, collar rake, chest-plate wrap, grapple, cargo pocket. |
| `proportions_blockout.png` | **Dimensions only**: an ortho render (1 m = 500 px) of the numbers below, labelled at landmark heights. The shapes are crude. |
| `kes_proportion_blockout.py` | The script that made it. Copy its helpers `ring`, `loft`, `body_loft` and `tube` instead of reinventing them. |

---

## 1. Identity and silhouette

Kestrel is a lean, athletic woman in her mid-20s and the game's recon / mobility specialist. She is the person
who is already on the zipline before anyone else has looked up. The design is light and quick: a **cropped**
charcoal jacket with a **tall chin-high collar**, a dark navy under-suit showing at the midriff, fitted charcoal
cargo pants, and only the **Tier-2** amount of armour: one bone chest plate with a raised "II", plus a small
back plate. Her tech is compact and sits on **her left**: a glowing teal octagonal monocle with an ear-piece,
and a zipline grapple launcher on her forearm. The jump-jet pack rides low on her back, and its two bone
thruster pods angle **down, back and slightly out**, so from the front two small teal-lit flares peek out
beside her waist. In black silhouette she reads as a tall narrow figure with long legs, a collar column and an
asymmetric hair wedge on top (long on her right, tight on her left), two small nozzle flares at the waist, a
knob on the left forearm and a holster block on the right thigh. Nothing is bulky. If a part makes her look
heavier, it is wrong.

## 2. The 5 things that MUST read

1. **Asymmetric hair.** A blue-black bob sweeps across her forehead to **her right** and hangs past the right
   cheek to chin level, with **teal-dyed tips**. Her left side is tight to the skull, with a buzzed undercut
   above the ear that exposes the ear-piece. In the front silhouette the hair is a lopsided wedge.
2. **Tall high collar.** A funnel collar rises from the shoulders to the chin (front top Z 1.50, back top
   Z 1.535). It has a front V-opening and a **teal lining / teal edge**. The neck is never visible except in the
   V.
3. **Jet-pack nozzles.** Two bone thruster pods with gunmetal bells and **glowing teal cores**, angled
   down/back/out. They are visible beside the waist from the front, dominant from the side and back, and
   their glow can be seen from behind and below.
4. **Tier-2 armour, nothing more.** The bone chest plate carries two raised graphite **"II" pips**, and the
   small bone back plate carries "II" as well. **No** side plates, shoulder pads/pauldrons or neck guard: those
   mean Tier 3/4 (v05 drew shoulder pads, so ignore that). The bone pieces should be the brightest large
   shapes on the torso.
5. **Teal monocle over her LEFT eye.** This is the brightest point on the character (emissive). It sits with
   the ear-piece on the undercut side. The value read should be: dark charcoal jacket → navy midriff band →
   graphite belt → charcoal pants → bone knee pads → bone toe caps.

---

## 3. Body proportions (outer clothed surface unless noted)

Height 1.70 m to the skull crown; the hair adds about +0.02. Head (chin→crown) = 0.225 m = 1/7.55 of the
height. The legs are stylized long (crotch at 47 % of height).

| Landmark | Z (m) | Width X (full) | Depth Y (full) | Notes |
|---|---|---|---|---|
| Crown (skull) | 1.700 | — | — | hair top ≈ 1.72 |
| Hairline (forehead) | 1.665 | | | |
| Brow | 1.612 | | | |
| Eye line | 1.590 | head 0.148 | head 0.188 | eye centres X ±0.031 |
| Nose tip | 1.540 | | | 0.018 proud of face |
| Mouth | 1.508 | mouth 0.040 | | |
| Chin | 1.475 | jaw 0.100 at Z 1.50 | | narrow, slightly pointed |
| Collar top | 1.500 front / 1.535 back | 0.166 | 0.156 | funnel, flared slightly |
| Neck base / collar root | 1.405 | 0.176 | 0.164 | neck itself r 0.050 (hidden) |
| Shoulder top (acromion) | 1.395 | 0.40 over deltoids | | glenohumeral joint at (±0.165, 0, 1.360) |
| Chest / bust | 1.270 | 0.312 (jacket) | 0.236 | centre Y shifted −0.008 |
| Underbust / jacket hem | 1.140 | 0.264 | 0.196 | cropped jacket ends here |
| Waist (narrowest, under-suit) | 1.070 | 0.240 | 0.176 | |
| Belt centre | 0.975 | 0.33 | 0.23 | belt band Z 0.958–0.993 |
| Hip widest | 0.885 | 0.340 | 0.230 | seat centre Y +0.010 |
| Crotch | 0.800 | | | inseam 0.80 |
| Mid-thigh | 0.740 | thigh Ø 0.160 | | thigh centre X ±0.095 |
| Knee centre | 0.470 | knee Ø 0.112 | | knee centre X ±0.110 |
| Calf widest | 0.360 | calf Ø 0.112 | 0.120 | |
| Ankle | 0.085 | Ø 0.070 | | ankle centre (±0.118, +0.010) |
| Boot top | 0.150 | | | boot length 0.28, toe at Y −0.195 |

**A-pose joints** (left side shown; mirror X for the right). The arms are 45° from vertical with a 10° forward
elbow bend:

| Joint | Left (+X) position |
|---|---|
| Shoulder (glenohumeral) | (0.165, 0.000, 1.360) |
| Elbow | (0.370, 0.000, 1.155), upper arm 0.290 |
| Wrist | (0.559, −0.042, 0.997), forearm 0.250, forearm dir ≈ (0.755, −0.168, −0.634) |
| Fingertip (middle) | ≈ (0.695, −0.072, 0.882), hand 0.180 |
| Hip joint | (0.085, 0.005, 0.860) |
| Knee | (0.110, −0.008, 0.470) |
| Ankle | (0.118, 0.006, 0.085) |

The palms face the thighs, the fingers are relaxed (12° curl per joint) and the feet are toed out 8°.

**Torso ring table** for `body_loft` (rows are `z, rx, ry, cy, p`, superellipse exponent p):

```
KES_Jacket     (1.140,0.132,0.098,0.000,2.4) (1.170,0.136,0.102,0.000,2.4) (1.220,0.148,0.110,-0.004,2.4)
               (1.270,0.156,0.118,-0.008,2.4) (1.320,0.160,0.112,-0.004,2.5) (1.370,0.163,0.100,0.000,2.6)
               (1.405,0.150,0.086,0.004,2.8)  (1.425,0.110,0.074,0.008,2.4)  (1.437,0.072,0.066,0.008,2.0)
KES_UnderSuit  (0.990,0.150,0.105,0.006,2.2) (1.020,0.136,0.098,0.004,2.2) (1.070,0.120,0.088,0.000,2.2)
               (1.100,0.122,0.090,0.000,2.2) (1.160,0.126,0.094,0.000,2.2)
KES_Pants pelvis (0.800,0.120,0.090,0.010,2.2) (0.830,0.165,0.112,0.008,2.3) (0.885,0.170,0.115,0.010,2.3)
               (0.960,0.160,0.110,0.008,2.2) (1.000,0.152,0.106,0.006,2.2)
```

**Leg tube** (`tube`, 16 sides; left leg, mirror X): points → radii (side, front-back)

```
(0.085,0.005,0.86)->(0.088,0.092)  (0.095,0.000,0.74)->(0.080,0.082)  (0.104,-0.005,0.60)->(0.066,0.068)
(0.110,-0.008,0.47)->(0.056,0.058) (0.114,0.002,0.36)->(0.056,0.060)  (0.117,0.006,0.24)->(0.048,0.050)
(0.118,0.006,0.13)->(0.050,0.054)   # slight flare over the boot top
```

**Sleeve tube** (16 sides): torso entry (±0.125, 0.004, 1.355) r 0.055 → shoulder cap (joint + (±0.014, 0, 0.004))
r 0.058 → +0.08 along the upper arm r 0.050 → +0.18 r 0.046 → elbow r 0.044 → +0.06 along the forearm r 0.045
→ **cuff end at elbow + 0.11 along the forearm** r 0.048. Forearm skin runs from (cuff − 0.02) to the wrist,
r 0.036 → 0.028.

Only model **visible** skin: head, ears, the neck inside the collar V, forearms and the exposed fingers. Build
no nude body under the clothes. The clothing shells *are* the body.

---

## 4. Part list

Columns: object, size (W × D × H or radii), centre position (left-side parts; "mirror" means also make the
−X copy), material, and procedural method. All hard parts get `bc.add_bevel` (1–3 segments) and
`bc.shade_smooth`.

### 4a. Head and face

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `KES_Head` | radii 0.074 × 0.094 × 0.112 | (0, 0.004, 1.588) | Skin | UV sphere 24×16 scaled, then the vertex recipe in section 5. |
| `KES_Ears` | each 0.030 (Y) × 0.012 (X) × 0.055 (Z) | (±0.074, 0.010, 1.575) | Skin | Flattened half-disc (`profile_extrude` of a D shape), tilted back 10°. |
| `KES_Nose` | 0.022 W at tip, 0.045 long | bridge (0, −0.084, 1.585) → tip (0, −0.100, 1.540) | Skin | Triangular prism wedge, bevel 0.003, joined to the head. |
| `KES_Eyes` | 0.026 W × 0.011 H almond | (±0.031, −0.080, 1.590) | EyeWhite + Iris | Flattened sphere (0.013, 0.006, 0.0055) with a dark iris disc (r 0.0055) on the front. Recess the face 0.004 around the eye. |
| `KES_Brows` | 0.030 × 0.003 × 0.006→0.003 | (±0.032, −0.087, 1.612) | Hair | Thin wedges. The **inner end sits 0.006 lower** than the outer end (determined look). |
| `KES_Lips` | upper r (0.020, 0.006, 0.004), lower r (0.018, 0.007, 0.005) | (0, −0.086, 1.512) / (0, −0.085, 1.504) | Lips | Two flattened ellipsoids, pressed into the face. |
| `KES_Neck` | r 0.050 → 0.047 | (0, 0.008, 1.395 → 1.505) | Skin | `tube`, 12 sides. |

### 4b. Hair (see section 5 for the clump table)

| Object | Material | Method |
|---|---|---|
| `KES_HairCap` | Hair | Head ellipsoid +0.010 (radii 0.084 × 0.104 × 0.122). Delete the verts below the hairline: front Z 1.665, **her left side Z 1.630** (the undercut starts below), her right side Z 1.55 (hidden under clumps), nape Z 1.505. Solidify 0.006. |
| `KES_HairBuzz` | HairBuzz | Undercut patch on **her left (+X)**: a shell 0.0015 off the skull, Z 1.530–1.630, Y −0.045 → +0.090, cut out around the ear. |
| `KES_Hair` | Hair | 9 clumps (H1–H9), joined. |
| `KES_HairTips` | Teal | The tip segments of H1–H8, split from the clumps (see section 5). |

### 4c. Monocle (her LEFT eye, +X)

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `KES_Earpiece` | 0.020 (X) × 0.032 (Y) × 0.042 (Z) | (0.092, 0.006, 1.580) | Graphite | Box with bevel 0.006 (3 seg), sitting on the outside of the left ear. |
| `KES_MonocleFrame` | octagon outer 0.056 W × 0.040 H, rim 0.003, depth 0.007 | (0.034, −0.100, 1.592), rot Z +15° (outer edge swings back) | Graphite | Elongated octagon (v06): `profile_extrude` of the outer octagon, boolean out the inner octagon. |
| `KES_MonocleLens` | 0.050 × 0.034, 0.003 thick | in the frame, 0.015–0.02 in front of the eye | **Glow** | Same octagon inset, faces bulged 0.002 forward. |
| `KES_MonocleArm` | 0.006 × 0.006 section | upper arm (0.062, −0.090, 1.600) → (0.068, −0.050, 1.602) → (0.080, −0.012, 1.598) → ear-piece; lower arm (0.062, −0.092, 1.580) → (0.070, −0.050, 1.576) → (0.084, −0.010, 1.570) | Graphite | Two thin `tube`s (6 sides) running 0.004 off the temple surface. |

### 4d. Jacket, collar and under-suit

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `KES_Jacket` | see the ring table (section 3) | Z 1.140–1.437 | Jacket | `body_loft`, 24 sides. Neck ring left open. The sleeves overlap into it. |
| `KES_JacketHem` | ring 0.030 tall, +0.004 proud | Z 1.140–1.170 | Graphite | Ribbed band: loft 2 rings, add 3 shallow horizontal grooves (inset loops) or rely on texture. |
| `KES_Collar` | rings: Z 1.405 (0.088, 0.082) → Z 1.455 (0.080, 0.075) → top (0.083, 0.078); top ring sheared so the front is Z 1.500 and the back Z 1.535; centre Y 0.008 | — | Jacket outside, **Teal inside** | Loft 3 open rings, Solidify 0.010 inward. Boolean a **front V-notch** (0.055 wide at the top, apex Z 1.445) so the chin sits in it. Assign faces whose normals point at the collar axis, plus the top lip, to `M_KES_Teal`. **It must not intersect the jaw.** Push the top ring forward (cy −0.004) if needed. |
| `KES_Zip` | 0.006 W, 0.003 proud | collar V apex (0.006, −0.090, 1.445) up to the top; pull tab 0.008 × 0.004 × 0.016 | Gunmetal | Thin box strip plus a tab. |
| `KES_Sleeve_L/R` | see the sleeve tube (section 3) | shoulder → mid-forearm | Jacket | `tube`, 16 sides. |
| `KES_SleeveCuff_L/R` | 2 bunched folds (torus major 0.047, minor 0.010) at forearm +0.085 / +0.100, plus a ribbed band 0.025 long r 0.042 at the cuff end | at the sleeve end | Jacket folds, Graphite band | Rotate each torus ±6° about a different axis so the bunch looks pushed-up, not machined. |
| `KES_Piping` | tube r 0.0035, 6 sides, 0.003 off the surface | (a) each sleeve: collar root (±0.06, 0.0, 1.425) → shoulder top (±0.17, 0.0, 1.418) → down the outer/top line of the sleeve to the cuff. (b) each front side seam: (±0.150, −0.060, 1.350) → (±0.132, −0.060, 1.170). | Teal | `tube` along polylines that follow the surfaces. Joined into one object. |
| `KES_UnderSuit` | see the ring table | Z 0.990–1.160 (runs under the jacket and belt) | UnderSuit | `body_loft`. Optional: two raised seam strips (0.006 W) forming a shallow V down to the navel (v01). |
| `KES_Forearm_L/R` | r 0.036 → 0.028 | from the cuff to the wrist | Skin | `tube`, 12 sides. |

### 4e. Armour (Tier 2) and harness

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `KES_ChestPlate` | 0.250 W × 0.200 H, 0.016 thick + 0.006 raised upper panel | centre (0, −0.136, 1.265) | Bone | `profile_extrude` of the **front outline** (X, Z offsets from the centre, mirrored half): `(0,.100) (.055,.100) (.068,.088) (.095,.088) (.125,.045) (.128,-.010) (.100,-.065) (.050,-.075) (.040,-.100) (0,-.100)`. To extrude along Y with `bc.profile_extrude` (which extrudes along X), pass the (X, Z) points as its (y, z), use width 0.016, then rotate the object 90° about Z and apply (the outline is symmetric). **Wrap in both directions** so it sits on the convex chest: `y += 1.6·x² + 2.2·(z − 1.265)²`. The side edges go 0.025 back and the top/bottom edges 0.022 back. The jacket front is Y −0.126 at the bust but only about −0.102 at the plate's top and bottom edges, so a flat plate would float there. Inset the front face above Z −0.040 by 0.012 and extrude it +0.006 (the upper facet, v04). Bevel 0.004, 2 seg. |
| `KES_ChestPips` | 2 bars, each 0.010 W × 0.044 H × 0.005 proud | X ±0.013, Z 1.300, on the plate surface (Y ≈ −0.153) | Graphite | Box + bevel 0.0015. Upright "II" (the concepts slant them about 8°, which is optional). |
| `KES_BackPlate` | 0.210 W × 0.170 H × 0.018 | (0, +0.124, 1.310) — its bottom 0.02 tucks **behind/under the jet-pack body top** (the pack overlaps it, as in v03/v07) | Bone | Rectangle, top corners chamfered 0.035, small bottom-centre notch 0.06 W × 0.02 for the jet-pack spine. Wrap `y −= 1.6·x²` (mirror of the chest). Bevel as for the chest plate. |
| `KES_BackPips` | as `KES_ChestPips` | X ±0.013, Z 1.355, Y ≈ +0.136 | Graphite | Same as the chest pips. The tier must read from behind too. |
| `KES_Straps` | webbing 0.035 W × 0.006 | **Shoulder** (each side): chest-plate top corner (±0.085, −0.140, 1.360) → (±0.105, −0.095, 1.405) → over the shoulder (±0.110, 0.000, 1.432) → (±0.100, 0.090, 1.410) → back-plate corner (±0.080, 0.132, 1.390). **Side** (each side, 0.028 tall): from the plate side (±0.122, −0.115, 1.205) around the ribs to (±0.110, 0.118, 1.215). | Webbing | Flat ribbon swept along each polyline, wide face tangent to the jacket, 0.004 off it (a `tube` with radii (0.0175, 0.003), or a chain of thin boxes). |
| `KES_StrapBuckles` | 0.022 × 0.010 × 0.030 | 4 buckles where the straps meet the plate corners/sides | Gunmetal | Box + bevel. |

### 4f. Belt, pouches, holster

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `KES_Belt` | 0.035 tall, 0.008 thick | rings (0.958, 0.164, 0.117, 0.006, 2.2) → (0.993, 0.158, 0.113, 0.006, 2.2) | Graphite | `body_loft`, open, Solidify. |
| `KES_BeltBuckle` | 0.045 W × 0.012 D × 0.030 H, with a raised downward chevron | (0, −0.122, 0.975) | Gunmetal | Box + bevel, plus a chevron `profile_extrude`. |
| `KES_Pouches` | two rigid pouches, each 0.045 W × 0.030 D × 0.060 H, flap overhang +0.004, snap stud r 0.004 | **her left front hip**: (0.075, −0.117, 0.950) rot Z +20°; (0.133, −0.080, 0.950) rot Z +40° (back face 0.004 off the belt) | Webbing | Box + bevel 0.008, flap box, stud cylinder. |
| `KES_Holster` | 0.045 (X) × 0.130 (Y) × 0.200 (Z) | **her right thigh (−X)**, outer face, sitting on the leg straps: (−0.205, −0.005, 0.735) | Webbing | `profile_extrude` of the side profile: a rounded-bottom rectangle with a hood at the back-top over the grip. Bevel 0.008. |
| `KES_HolsterGrip` | 0.028 × 0.040 × 0.075, tilted back 12° | (−0.205, 0.035, 0.875) | Graphite | Box + bevel (pistol grip sticking out of the holster). |
| `KES_LegStraps` | 2 bands 0.028 tall, 0.006 thick, plus gunmetal buckles at the front | around the **right** thigh at Z 0.700 and 0.630 (ring = leg radius +0.006) | Webbing | Short `tube` rings or solidified loft rings. Add a drop strap 0.03 W from the belt (−0.160, −0.005, 0.960) to the holster top (−0.195, −0.005, 0.845). |

### 4g. Legs and feet

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `KES_Pants` | pelvis loft + 2 leg tubes (section 3) | Z 0.13–1.00 | Pants | Overlap the legs 0.06 into the pelvis; join. |
| `KES_CargoPocket` | 0.030 (X) × 0.100 (Y) × 0.130 (Z), flap 0.035 | **her left** outer thigh (0.188, −0.005, 0.680) | Pants | Box + bevel 0.006, flap box +0.004. |
| `KES_KneePad_L/R` | 0.095 W × 0.125 H × 0.022 | (±0.110, −0.080, 0.475) | Bone | Front outline (half): `(0,.0625) (.035,.0625) (.0475,.035) (.0475,-.030) (.030,-.0625) (0,-.0625)`. Extrude, wrap `y += 4·x²`. Add a horizontal ridge (raised 0.004) at the centre line. Bevel 0.004. |
| `KES_KneeStraps` | band 0.022 tall | behind each knee at Z 0.47, r ≈ 0.062 | Webbing | Partial ring (back 240°) ending at the pad sides. |
| `KES_Boot_L/R` | width 0.098 (toe tapered to 0.080), length 0.280 | ankle (±0.118, 0.010, 0), toed out 8° | Jacket upper / Graphite sole | `profile_extrude` of the side profile (Y, Z) relative to the ankle: `(.070,0) (-.190,0) (-.205,.012) (-.200,.035) (-.150,.060) (-.070,.085) (-.045,.150) (.055,.150) (.062,.090) (.075,.030)`. Bevel 0.012, 3 seg. Separate sole slab 0.022 thick, footprint +0.004, **Graphite**. |
| `KES_BootCaps_L/R` | toe cap from Y −0.205 to −0.130, up to Z 0.055; heel counter 0.06 tall | on each boot, offset 0.003 | Bone | Duplicate the boot faces in the region and solidify 0.004 (v01's bone toe caps). |

### 4h. Hands

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `KES_Glove_L/R` | palm block 0.082 W × 0.028 T × 0.090 L; wrist cuff 0.030 long r 0.031 | from the wrist along the hand axis | Graphite | Box + bevel 0.010 for the palm; `tube` cuff. |
| `KES_GloveArmor_L/R` | back-of-hand plate 0.045 × 0.040 × 0.006, plus 3 knuckle studs r 0.006 | on the back of each glove | Bone | Box + bevel; spheres (v01). |
| `KES_Fingers_L/R` | 4 fingers r 0.0085 → 0.007, lengths index 0.070 / middle 0.078 / ring 0.073 / pinky 0.058; thumb 0.055 r 0.010 at 35° | coming out of the glove (it covers the first ~40 % of each finger) | Skin | 2-segment `tube`s, 8 sides, 12° curl per joint, 4° spread. |

### 4i. Jump-jet pack (on her lower back)

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `KES_JetPack_Body` | trapezoid, top 0.180 W, bottom 0.220 W, 0.150 H, 0.085 deep | (0, 0.168, 1.170) | Graphite | `profile_extrude` of the XZ outline (rotate it), corners chamfered 0.020, bevel 0.012. Boolean a centre vertical groove (0.012 W, 0.008 deep) on the back face and 2 small vent slots on top. |
| `KES_JetPack_Spine` | 0.060 W × 0.015 D × 0.080 H | (0, 0.142, 1.250), into the back-plate notch | Graphite | Box + bevel. |
| `KES_Thruster_L/R` | cylindrical pod r 0.046, 0.09 long | base (±0.090, 0.200, 1.120), axis **d = normalize(±0.30, 0.55, −0.78)** | Bone | `lathe` (rounded top lip) aligned to d. |
| `KES_Nozzle_L/R` | bell: r 0.030 at the throat → 0.042 at the exit, 0.055 long, wall 0.004, open | from base + d·0.060 to base + d·0.115 (exit centre ≈ (±0.125, 0.263, 1.030)) | Gunmetal | `lathe` of a closed thin-wall profile. |
| `KES_JetGlow_L/R` | cone/disc r 0.032 | recessed inside each nozzle at base + d·0.095 | **Glow** | `lathe` of a shallow cone pointing into the nozzle. |

Check: from the front view, each nozzle exit must stick out 0.03–0.04 beyond the waist outline at Z ≈ 1.03.
This is the silhouette hook (see `proportions_blockout.png`).

### 4j. Zipline grapple launcher (her LEFT forearm, +X)

Build it in a **forearm frame**: origin at the left wrist (0.559, −0.042, 0.997); axis `f` = forearm direction
(0.755, −0.168, −0.634) pointing toward the hand; `up` = world +Z made orthogonal to `f` (the face that points
up/out in A-pose). Mount everything on the `up` face.

| Object | Size | Frame position | Material | Method |
|---|---|---|---|---|
| `KES_Grapple_Bracer` | ring 0.100 long, radii (0.040, 0.034), 0.008 thick, plus 2 strap bands 0.015 wide | from wrist −0.12 to wrist +0.01 along f | Graphite | Open `tube`, Solidify. |
| `KES_Grapple_Housing` | faceted slab 0.140 long × 0.045 wide × 0.022 tall, nose tapered | centre at wrist −0.06 along f, +0.030 along up | Bone | `profile_extrude` of a long hexagon (v01 grapple crop), bevel 0.004. Add a 0.004 Teal stripe along its outer side. |
| `KES_Grapple_Barrel` | rectangular rail 0.024 × 0.022, 0.170 long, with a slot | from wrist −0.13 to wrist +0.04 along f, +0.050 along up | Graphite | Box + bevel 0.004, slot boolean. |
| `KES_Grapple_Hook` | cone r 0.012 → 0.005, 0.025 long, plus 3 folded claw prongs 0.004 × 0.008 × 0.030 at 120° | at the barrel muzzle (wrist +0.04) | Gunmetal | Lathe cone + 3 wedges. |
| `KES_Grapple_Spool` | drum r 0.022, 0.018 wide, axis ⟂ f | on the housing's outer side at wrist −0.07 | Gunmetal | `cylinder`. |

---

## 5. Face recipe and hair clumps

**Head shaping** (applied to the scaled UV sphere, in world coordinates):

1. Jaw taper: for each vert with z < 1.590, `t = (1.590 − z) / 0.113`; `x *= 1 − 0.38·t²`. For verts with
   y > 0.004 (back of the skull/nape), `y = 0.004 + (y − 0.004)·(1 − 0.25·t)`.
2. Chin: verts with z < 1.50 and y < −0.04 move `y −= 0.006` (a small pointed chin at (0, −0.072, 1.478)).
3. Face plane: verts with y < −0.075 get `y = −0.075 + (y + 0.075)·0.6` (a flatter stylized face).
4. **Sharp cheekbones**: verts within 0.022 of (±0.060, −0.058, 1.565) move 0.006 outward along their
   normal. Verts within 0.020 of (±0.055, −0.062, 1.530) move 0.004 inward. This makes a planar, hollowed
   cheek.
5. Eye sockets: verts within 0.016 of (±0.031, −0.082, 1.590) move +0.004 in Y (recess). Brow ridge
   (±0.032, −0.084, 1.608) moves −0.002 in Y.

The expression is neutral-determined: lowered inner brows, mouth closed and level, no smile. The eyes are
almond-shaped and slightly narrowed, with dark brown irises. Keep facial detail as **modelled shapes**: no
painted pores and no realism.

**Hair clumps.** Make each clump with a Blender curve: `bevel_mode='ROUND'`, `bevel_depth` = half the width,
`use_fill_caps`. Use per-point `radius` for the taper (1.0 → 0.25) and **flatten** it with a lens-shaped bevel
object (width:thickness ≈ 2.5 : 1) or by scaling the converted mesh along the clump's normal. Tilt the points
so the flat face lies on the scalp. Resolution 4, 8 bevel verts. Convert to mesh, then join. Keep at least
0.004 between a clump and the cap. **Split each curve** at the tip fraction and give the tip part
`M_KES_Teal` (`KES_HairTips`). Coordinates are root → tip:

| Clump | Points (x, y, z) | Root width × thick | Teal tip |
|---|---|---|---|
| H1 hero fringe (sweeps to **her right**, past the right cheek) | (0.030,−0.088,1.668) → (−0.020,−0.100,1.650) → (−0.068,−0.088,1.605) → (−0.080,−0.070,1.535) → (−0.074,−0.060,1.468) | 0.060 × 0.022 | last 30 % |
| H2 right side, mid | (0.020,−0.040,1.712) → (−0.050,−0.050,1.690) → (−0.092,−0.045,1.620) → (−0.094,−0.030,1.540) → (−0.086,−0.035,1.480) | 0.065 × 0.024 | last 30 % |
| H3 right side, back (covers the right ear) | (0.010,0.030,1.715) → (−0.060,0.040,1.690) → (−0.094,0.040,1.610) → (−0.092,0.045,1.540) → (−0.082,0.040,1.488) | 0.065 × 0.024 | last 30 % |
| H4 back right | (0.000,0.080,1.700) → (−0.050,0.105,1.650) → (−0.065,0.110,1.570) → (−0.058,0.100,1.500) | 0.060 × 0.024 | last 30 % |
| H5 back centre | (0.020,0.090,1.700) → (0.000,0.115,1.640) → (−0.005,0.112,1.560) → (0.000,0.098,1.505) | 0.060 × 0.022 | last 30 % |
| H6 back left (shorter, graduating up) | (0.040,0.085,1.695) → (0.055,0.105,1.640) → (0.060,0.100,1.580) → (0.055,0.090,1.540) | 0.055 × 0.020 | last 30 % |
| H7 top-left flick (above the temple) | (0.030,−0.075,1.670) → (0.070,−0.065,1.650) → (0.090,−0.050,1.625) | 0.045 × 0.018 | last 25 % |
| H8 top-left back flick | (0.030,0.000,1.708) → (0.075,0.010,1.675) → (0.093,0.030,1.630) | 0.050 × 0.018 | last 25 % |
| H9 crown volume (lifts the top, sweeps right) | (0.030,−0.060,1.700) → (−0.010,−0.020,1.725) → (−0.060,0.020,1.700) → (−0.085,0.050,1.650) | 0.070 × 0.030 | none |

**Snapping the points:** the coordinates are design guides. Points at Z ≥ 1.56 are *attached*: slide each
one along the ray from the head centre C = (0, 0.004, 1.588) so it sits half a clump thickness plus 0.002 above
the cap. With `k = √((dx/0.084)² + (dy/0.104)² + (dz/0.122)²)`, scale (p − C) by `k_t / k`, where
`k_t ≈ 1 + (t/2 + 0.002)/0.10` (about 1.13 for t = 0.022). Points below Z 1.56 hang *free* (the bob ends): keep
them as given, but never inside k = 1.12. The tips are the last point of each list.

The **side part** sits on her left at X ≈ +0.030 and runs from the front hairline (Y −0.08) to the crown. The
right side must clear the right ear (clump centres at |x| ≥ 0.092 between Z 1.55 and 1.62). The H1 fringe must
**not** cover the right eye: its inner edge passes the eye's outer corner (X −0.046). The left side stays
within 0.012 of the skull above the undercut, so the ear and ear-piece show.

---

## 6. Materials (linear RGB, `bc.material`)

| Material | Palette token | Base colour (linear) | Rough | Metal | Extra / texture (subtle multiply) | Used on |
|---|---|---|---|---|---|---|
| `M_KES_Skin` | skin light | (0.62, 0.42, 0.33) | 0.60 | 0 | — | head, ears, nose, neck, forearms, fingers |
| `M_KES_Lips` | skin light, deepened | (0.42, 0.22, 0.19) | 0.50 | 0 | — | lips |
| `M_KES_EyeWhite` | bone, dimmed | (0.50, 0.47, 0.42) | 0.40 | 0 | — | eyes |
| `M_KES_Iris` | — | (0.05, 0.03, 0.02) | 0.30 | 0 | — | iris discs |
| `M_KES_Hair` | blue-black (graphite shifted blue) | (0.010, 0.016, 0.035) | 0.45 | 0 | coat 0.2 optional | hair, cap, brows |
| `M_KES_HairBuzz` | hair over skin | (0.06, 0.05, 0.06) | 0.80 | 0 | — | undercut |
| `M_KES_Jacket` | charcoal-cloth | (0.035, 0.037, 0.045) | 0.70 | 0 | `fabric_ripstop.png` mix 0.35 | jacket, collar outside, sleeves, boot uppers |
| `M_KES_UnderSuit` | charcoal-cloth, navy shift | (0.020, 0.025, 0.050) | 0.50 | 0 | `fabric_soft.png` mix 0.3 | midriff under-suit |
| `M_KES_Pants` | charcoal-cloth, 20 % darker | (0.028, 0.030, 0.036) | 0.75 | 0 | `fabric_ripstop.png` mix 0.35 | pants, cargo pocket |
| `M_KES_Bone` | bone | (0.55, 0.52, 0.46) | 0.50 | 0 | `worn_paint.png` mix 0.3 | chest/back plate, knee pads, thruster pods, grapple housing, glove plates, boot caps |
| `M_KES_Graphite` | graphite | (0.030, 0.033, 0.040) | 0.55 | 0 | `polymer_stipple.png` mix 0.3 | pips, belt, jet-pack body, earpiece, monocle frame, gloves, grapple barrel/bracer, hem/cuff ribbing, boot soles |
| `M_KES_Gunmetal` | gunmetal | (0.11, 0.115, 0.12) | 0.35 | 0.85 | `brushed_metal.png` mix 0.3 | nozzles, buckles, zip, grapple hook and spool |
| `M_KES_Webbing` | olive | (0.12, 0.13, 0.08) | 0.80 | 0 | `fabric_ripstop.png` mix 0.4 | plate straps, pouches, holster, leg/knee straps |
| `M_KES_Teal` | teal (Kestrel), **not emissive** | (0.0, 0.70, 0.62) | 0.50 | 0 | — | piping, collar lining, hair tips, grapple stripe |
| `M_KES_Glow` | teal, **emissive** | (0.0, 0.70, 0.62), emission (0.0, 0.70, 0.62), strength 5 | 0.40 | 0 | — | **monocle lens + the 2 nozzle cores only** |

**The single emissive accent:** `M_KES_Glow` is the only emissive material on Kestrel. It goes on exactly two
zones: the **monocle lens** (primary, the brightest point) and the **recessed cores inside the two jet
nozzles** (secondary, hidden from the front). Piping, collar lining, hair tips and the grapple stripe are
painted teal and do **not** glow. If the art director later wants one zone only, switch the nozzle cores to
`M_KES_Teal`.

Textures live in `art/textures/` (`fabric_ripstop.png`, `fabric_soft.png`, `worn_paint.png`,
`polymer_stipple.png`, `brushed_metal.png`) and are optional. The flat colour must carry the look without
them.

---

## 7. Layering (inside → out) and offsets

1. Skin pieces (head, neck, forearms, fingers).
2. `KES_UnderSuit`: runs 0.02 up inside the jacket and 0.01 down inside the pants.
3. `KES_Pants`: the pelvis top hides under the belt.
4. `KES_Jacket` + sleeves; `KES_Collar` over the jacket's neck ring; hem band +0.004.
5. Piping +0.003 on the jacket.
6. Plates: the chest-plate back face sits **0.004** off the jacket front (jacket front Y −0.126 at Z 1.27; plate centre
   Y −0.136). The back plate sits 0.006 off the jacket back (jacket back Y +0.109 at Z 1.31).
7. Straps +0.004 over the jacket. They pass **under** the plate edges at the plate corners and over the
   shoulders.
8. Belt +0.004 over the under-suit/pants seam; pouches on the belt; holster on the leg straps, which are
   +0.006 over the pants.
9. Knee pads +0.004 over the pants; boots over the pant hems (the pants flare 0.004 over the boot top).
10. Gloves over the wrists; grapple bracer over the left forearm skin, behind the sleeve cuff.
11. Jet pack over the jacket/under-suit back (body front face at Y ≈ 0.126; the jacket back at Z 1.17 is at
    Y ≈ 0.102). The spine plate tucks into the back-plate notch.
12. Hair cap +0.010 over the skull; clumps over the cap; the buzz shell +0.0015.

Intersections hidden inside other meshes are fine. Visible z-fighting is not.

## 8. Triangle budget (target ≈ 45k, hard max 70k)

| Group | Tris |
|---|---|
| Head, face, ears, eyes, brows, lips, neck | 3.7k |
| Hair (cap, buzz, 9 clumps, tips) | 8k |
| Monocle + ear-piece | 0.6k |
| Jacket, hem, collar, zip | 3.5k |
| Sleeves, cuffs, piping | 3.5k |
| Forearms, fingers | 3k |
| Gloves + glove armour | 1.5k |
| Under-suit | 0.8k |
| Chest/back plates, pips, straps, buckles | 3k |
| Belt, buckle, pouches | 1.5k |
| Holster, grip, leg straps | 1.5k |
| Pants + pocket | 3.5k |
| Knee pads + straps | 1k |
| Boots + caps | 3k |
| Jet pack | 4k |
| Grapple launcher | 2.5k |

## 9. Silhouette hooks

- **Hair wedge**: from the front, a lopsided cap (right side long down to Z 1.47, left side tight).
- **Collar column**: from the side, the collar rakes back-higher, and the head sits inside it like a funnel.
- **Jet nozzles**: two short flares at waist height on both sides from the front; from the side and back,
  two pods angled down and back.
- Secondary hooks: the grapple knob on the left forearm, the holster block on the right thigh, bone knee pads.

Test it: render front/side/back as a flat black silhouette at 64 px tall. You must still be able to point to
the hair asymmetry, the collar and the nozzles.

## 10. Concept images: what to trust

| Image | Trust it for | Deviations (the brief wins) |
|---|---|---|
| **v01 → `concept_main.png`** (front, A-pose-ish) | The whole look: palette blocking, cropped jacket + navy midriff, chest-plate placement, olive webbing, belt pouches on her left, holster on her right thigh, bone knee pads and toe caps, grapple on her left forearm, nozzles peeking beside the waist, monocle on her left eye. All sides are correct. | The plate marks look like "!!": use two plain upright bars. The jet "fins" there are flat bone wedges: build pods + nozzles per section 4i. Arms are less than 45° from the body: use the A-pose. The undercut is not visible: model it. |
| **v03 → `concept_turnaround.png`** (front / side / back) | Collar height and rake, jacket length (hem at the underbust), back plate between the shoulder blades with the jet pack below it, sleeve piping running over the shoulders, the A-pose, side-correct holster and grapple. | **The side view is broken**: the arm is missing and a black disc stands in for it. Ignore that disc and use **v08** for the side. The monocle is drawn as goggles in the side view, and the jet nozzles point straight back. Use the angle in section 4i (down/back/out). Pouches are black there: use olive. |
| **v06** (head study) | Face shape, the **octagonal monocle lens** with 2 thin arms to the ear-piece, the teal collar edge, hair length on her right with teal tips. | Her left side shows longer hair tucked behind the ear. Use a **buzzed undercut** instead. |
| **v04** (3/4 view) | Chest-plate outline and facet step, the "II" pips, ribbed hem and black ribbed sleeve cuffs, grapple proportions. | Hair is mirrored (long on her left): wrong. Belt pouches and holster are bone: use olive. |
| **v02** (front) | Alternative front, good glove and grapple read. | Hair mirrored (long on her left). No proper jet nozzles. Pips slanted. |
| **v05** (turnaround) | Back-view jet-pack layout (second opinion). | **Bone shoulder pads (Tier-4 read): do not build.** Four bars on the plate: wrong, it is "II". The side view is broken like v03's. |
| **v07** (back 3/4) | Back plate shape **with the "II" pips**, twin thruster pods directly under the back plate, olive leg straps and drop strap, knee-pad straps, bone toe caps/heels, black ribbed sleeve cuffs. Grapple and holster are on the correct sides. | Thrusters point straight back: angle them down/back/out (section 4i). Belt pouches are bone and at the back: use olive pouches on the front-left hip. |
| **v08** (side profile, her LEFT) | **Best side reference**: the buzzed undercut with the ear-piece, the monocle arm running to the ear, the collar rake and teal lining, how the chest plate wraps the ribs, the cropped hem line, the grapple on the forearm, the cargo pocket on her left thigh, knee pad and strap, low boots. | The jet pod sits at shoulder-blade height: the brief puts it on the **lower back** (body Z 1.095–1.245) so the nozzles flare at the waist. Bone strap bumpers on the shoulder: leave them out (they would read as pauldrons). |
| `proportions_blockout.png` | Every dimension and position in this brief, rendered at true scale. | The shapes are primitive stand-ins, not design. |

## 11. Build order and checks

1. Body shells (sections 3 and 4d/4g) → render front/side and compare against `proportions_blockout.png`
   at the same ortho scale (1 m = 500 px, centre Z 0.88).
2. Head and face recipe → hair clumps → monocle. Check from the front that the hair wedge and monocle side are
   correct (**monocle at screen-right in the Front view**).
3. Armour, harness, belt, holster, knee pads, boots.
4. Jet pack (check the front-view nozzle peek) and the grapple (forearm frame).
5. Materials → `bc.uv_all()` → `bc.stats()` (≤ 50k) → renders (front, right, back, three_quarter + sheet) →
   export.

**Final self-check:**

- Monocle and ear-piece on **+X**, holster on **−X**.
- Long hair on **−X**.
- "II" on both plates.
- Exactly one emissive material.
- No bone on the shoulders.
- Collar not intersecting the jaw.
- Feet at Z = 0.
- Height 1.70 (+hair).
