# SOLACE — modeler build brief (field medic / healer support)

Authoritative spec for the procedural Blender build. **Where a concept image and this brief disagree, the brief
wins** (and `art/DIRECTION_LOG.md` wins over both). Units are metres, Blender Z-up, character **faces −Y**, feet on
Z = 0, centred on X = Y = 0, A-pose (see `art/STYLE_GUIDE.md`). Object prefix `SOL_`, materials `M_SOL_<Surface>`.
She is built **on top of the parametric female base body** (`tools/female_base.py`). Every number below was
measured on that body at the settings in section 3.

> **Handedness: read twice.** Facing −Y, **her RIGHT is −X** (screen-LEFT in Blender's Front view) and **her LEFT
> is +X** (screen-right). Blender's *Right* view (camera at +X) shows **her left** side.
> Mnemonic: **"the right hand heals."** Her RIGHT (−X) carries the ponytail, the injector bracer and the medic
> pouch. Her LEFT (+X) carries the shoulder emblem and the docked heal drone.

No armour plates, no tier pips. Protection is the shared halo shield (`art/HALO_SHIELD_SPEC.md`). She only needs the
`SOL_SOCKET_Halo` empty (section 4l). **No red cross anywhere** (it is a protected emblem). Her medic mark is the
original three-petal "Bloom mark" (section 4e).

Files in this folder:

| File | Use it for |
|---|---|
| `concept_main.png` (= `v09.png`) | Overall look, A-pose, colour blocking, all sides correct, bud-vane tips peeking over both shoulders. |
| `concept_turnaround.png` (= `v08.png`) | Jacket cut: wrap front, hip-length front hem curving down into the split back tail; sleeve and tail lengths; front/side/back consistency. **Has no Bloom module**, so use `v04` for that. |
| `concept_face.png` (= `v05.png`) | Face, skin, hair parting, ponytail drape over her right shoulder, coral studs, collar + piping. |
| `v04.png` (turnaround, **back view only**) | The Bloom module from behind: closed three-vane bud, coral seams, charcoal yoke with two coral LEDs, hub at the base. |
| `v03.png` | Painterly finish and value pattern closest to Kestrel's concepts; alternative jacket cut. |
| `proportions_overlay.png` | **Dimensions only**: the base-body silhouette at Solace's settings with this brief's gear drawn on top (front + her left side; grid 0.1 m). |
| `sol_proportion_overlay.py` | Script that made the overlay (pure numpy/matplotlib; it holds the gear coordinates as data). |
| `_rejected/v07_red_cross.png` | **Never use** (it shows a red cross and rear-focused framing). |

---

## 1. Identity and silhouette

Solace is the team's anchor: a calm, warm field medic in her late 20s, 1.68 m, slender and athletic, with deep
skin, defined cheekbones and soft features. She reads as graceful and approachable, never armoured or bulky. Her
outfit is a **fitted ivory field jacket** with a **soft high wrap collar**, an asymmetric wrap closure with coral
piping, and a waist cinched by a slim charcoal belt. The jacket is hip-length in front and sweeps down into a **split
tail at the back that reaches mid-thigh**. Under it she wears sand utility pants, slim ivory knee pads and light
charcoal ankle boots. Her tech is clean and medical: a slim **"Bloom" regen module** on her back (a spine with three
ivory vanes folded shut like a flower bud, glowing coral at the seams), an **injector bracer with a glowing coral
vial** on her right forearm, and a **palm-sized white heal drone** docked on her left hip.

In black silhouette she reads as a slim upright figure with:
- two small pointed **vane tips rising behind both shoulders**;
- a **long ponytail** bulging over her right shoulder onto the chest;
- a **coat-tail flare** below the belt, wider than the hips and split at the back;
- a small **knob on the right forearm** (the bracer) and a **ball on the left hip** (the drone).

She must contrast clearly with Kestrel, who is dark charcoal + teal with a short asymmetric bob, a cropped
jacket and a jet pack. Solace is light ivory + coral, with long hair, a long-tailed jacket and the bud.

## 2. The 5 things that MUST read

1. **The Bloom bud on her back.** Three closed ivory vanes form a teardrop bud between her shoulder blades, and
   the **coral glow shows through the two seams** between the vanes. From the front, the two side-vane tips
   peek **above both shoulders** (Z 1.47–1.535). From the side, the bud is a slim teardrop about 0.13 m off her
   back. It must never look like wings: the vanes stay closed and compact.
2. **Long dark hair, low ponytail over her RIGHT shoulder (−X).** It is tied with a coral band behind her right
   ear, drapes over the shoulder and falls onto her upper chest to Z ≈ 1.16. It has soft waves and two
   face-framing strands. This is her head silhouette (Kestrel has a bob).
3. **Light ivory body with the coat-tail.** Ivory jacket (the brightest large mass) with a soft high collar,
   a coral wrap edge and coral-edged hems. The split back tail flares below the belt to mid-thigh. Value read top
   to bottom: dark hair → ivory jacket → **charcoal belt (waist)** → ivory tail around **sand pants** → ivory
   knee pads → charcoal boots.
4. **Injector bracer on her RIGHT forearm (−X).** An ivory housing on a charcoal gauntlet, with a **glowing coral
   vial** in a channel on top. It is her "weapon" read and must be visible in first person (on top of the
   forearm).
5. **Her LEFT side kit (+X):** the white **heal drone** docked on the left hip, its **coral eye** facing
   forward-out, and the coral **Bloom mark** patch on the left upper arm. No cross shapes anywhere.

---

## 3. Base body and proportions

Build the body first:

```python
import sys; sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc, female_base as fb
res = fb.build_female_base(
    prefix="SOL", height=1.68, build=0.2,
    skin=(0.26, 0.14, 0.085), eye_color=(0.10, 0.055, 0.030), brow_color=(0.018, 0.011, 0.008),
    face=dict(cheek=1.15, lip_full=1.15, nose_w=1.10, nose_len=0.97, jaw_w=0.98, chin_w=0.96,
              eye_open=1.06, eye_tilt=0.05, brow=0.95))
body = res["body"]          # SOL_Body; also res["eyes"], res["brows"], res["lashes"], res["joints"], res["dims"]
```

`build=0.2` sits on the lean side of the 0.15–0.3 range: slender but athletic. The numbers below come from the
recipe at these settings. **At build time read `res["joints"]` / `res["dims"]`, and use those values if they differ
from the brief by more than 3 mm.**

Height 1.68 m to the skull crown (Z 1.686 measured). Hair adds about +0.02. Head (chin→crown) = 0.224 m (1/7.5).
The legs are long (crotch at 46.5 % of height).

| Landmark | Z (m) | Measurements |
|---|---|---|
| Skull crown | 1.686 | hair top ≈ 1.71 (part lift) |
| Forehead hairline (centre) | 1.635 | |
| Eye centres | 1.566 | (±0.031, −0.045), eyeball r 0.0136 |
| Ear centre / ear top / lobe | 1.555 / 1.579 / 1.532 | ear centre (±0.069, 0.027); lobe centre (±0.068, 0.022), lobe outer face X ±0.077 |
| Mouth corners | 1.502 | (±0.023, −0.065) |
| Chin (menton) | 1.456 | front Y ≈ −0.075. Gonion (jaw angle) ≈ (±0.05, 0.012, 1.489) |
| Neck | 1.43–1.47 | half-width 0.044; front Y −0.010; back Y +0.083 |
| Neck root (jacket neck line) | front 1.400 / side 1.420 / back 1.445 | |
| Shoulder ridge (trapezius top at X ±0.11–0.13) | ≈ 1.415 | ridge at Y ≈ +0.02 |
| Shoulder joint | 1.367 | (±0.170, 0.012); biacromial 0.34 |
| Bust (apex) | 1.218 | half-width 0.146; front Y −0.095 (apex X ±0.04); back Y +0.093 |
| Underbust | 1.156 | front Y −0.074 |
| Natural waist (narrowest) | 0.990 | half-width 0.111; front Y −0.085; back Y +0.082 |
| Belt band | 0.970–1.000 | over the jacket |
| Hip widest | 0.875 | half-width 0.173; front Y −0.075; back Y +0.10 (glutes +0.109 at X ±0.056) |
| Crotch | 0.781 | |
| Mid-thigh | 0.625 | leg centre (±0.093, −0.002), radius 0.062–0.072 |
| Knee | 0.470 | centre (±0.097, −0.004), radius 0.063 |
| Calf | 0.350 | radius side 0.046, back 0.060 |
| Ankle | 0.073 | (±0.104, 0.022), radius 0.034 |
| Foot | 0 | heel back Y +0.082, toe tip Y −0.154 (length 0.235) |

**A-pose joints** (left side shown; mirror X for the right). Arms are 42° below horizontal with an 8° forward
elbow bend:

| Joint | Left (+X) position |
|---|---|
| Shoulder (glenohumeral) | (0.170, 0.012, 1.367) |
| Elbow | (0.370, 0.012, 1.187); upper arm 0.269, dir (0.743, 0, −0.669) |
| Wrist | (0.544, −0.021, 1.030); forearm 0.237, dir f = (0.736, −0.139, −0.663) |
| Middle fingertip | (0.703, −0.054, 0.938); hand 0.186 |
| Thumb tip | (0.550, −0.120, 0.957) |
| Hip joint | (0.086, 0.000, 0.863) |
| Knee | (0.097, −0.004, 0.470) |
| Ankle | (0.104, 0.022, 0.073) |

Hand frame (left): X_h = f (toward the fingers); T = (−0.103, −0.990, 0.093) (thumb side); D = (0.669, 0, 0.743)
(back of the hand). Mirror X for the right hand.

**Torso polar sections** (body surface). Each value is the distance from the axis point (0, cy, z) to the skin
along the direction at angle a, where a = 0 is front (−Y), 90 is her left side (+X) and 180 is the back (+Y). The
body is mirror-symmetric. Use these for the belt and skirt rings, and add the clothing offsets on top.

| z | cy | 0° | 30° | 60° | 90° | 120° | 150° | 180° |
|---|---|---|---|---|---|---|---|---|
| 0.860 | 0.012 | 0.082 | 0.105 | 0.157 | 0.173 | 0.149 | 0.112 | 0.087 |
| 0.900 | 0.012 | 0.092 | 0.106 | 0.150 | 0.167 | 0.143 | 0.107 | 0.092 |
| 0.940 | 0.008 | 0.091 | 0.097 | 0.123 | 0.142 | 0.123 | 0.097 | 0.090 |
| 0.970 | 0.004 | 0.088 | 0.093 | 0.104 | 0.116 | 0.105 | 0.091 | 0.082 |
| 0.990 | 0.002 | 0.087 | 0.092 | 0.103 | 0.111 | 0.103 | 0.088 | 0.081 |
| 1.060 | 0.004 | 0.080 | 0.091 | 0.106 | 0.126 | 0.115 | 0.091 | 0.082 |
| 1.140 | 0.010 | 0.076 | 0.087 | 0.107 | 0.144 | 0.145 | 0.092 | 0.080 |
| 1.220 | 0.000 | 0.094 | 0.111 | 0.122 | 0.143 | 0.159 | 0.120 | 0.093 |

Back surface on the midline (Bloom mount): Y +0.088 (Z 1.10), +0.093 (1.20), +0.090 (1.30), +0.100 (1.40). At
X ±0.06 the scapulae reach Y +0.105 (Z 1.20–1.25).

---

## 4. Part list

Columns: object, size, position, material, procedural method. All hard parts get `bc.add_bevel` (1–3 segments) and
`bc.shade_smooth`.

**SHELL recipe** (used for every garment copied from the body). Duplicate `SOL_Body`, delete the faces outside the
region (test each face centre), and apply. Move every vertex along its vertex normal by the **offset**. Add a Corrective
Smooth (factor 0.5, 6 repeats) and apply it, then push back out any vertex now closer than 0.8 × offset to the body
(BVH nearest point). Reduce with QuadriFlow or Decimate to the face count in section 8. **Do not Solidify large
shells.** Instead, give every open boundary a **hem return**: extrude the boundary loop 0.004 inward (along
−normal) so edges show thickness. Then `bc.smart_uv`, `bc.shade_smooth(obj, 50)`.

### 4a. Head and face (from the base body)

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_Body` (head, neck top, hands) | from `fb` | — | Skin (+ Lips region, Glove region) | Base body. After all clothing exists, **delete hidden faces**: everything below Z 1.44 except the hands (the hands become gloves, section 4h). Delete by region or by a ray test (a face is hidden when a clothing shell lies within 0.02 along its normal). |
| `SOL_Eye_L/R`, `SOL_Brows`, `SOL_Lashes` | from `fb` | from `fb` | from `fb` | Keep as generated. Iris colour: dark brown. |
| Lips region | ellipsoid (0.017, 0.010, 0.009) | around (0, −0.067, 1.501) | Lips | Assign `M_SOL_Lips` to body faces whose centre is inside the ellipsoid and has Y < −0.060. |
| Smile | — | mouth corners (±0.023, −0.065, 1.502) | — | Move verts within 0.009 of each corner +0.0012 in Z and +0.0006 outward in X (smooth falloff): a calm, closed-mouth half smile. |
| `SOL_Earrings` | sphere r 0.0035, scaled X 0.6 | on each lobe at (±0.0790, 0.020, 1.530) | Coral | Small studs on the outer lobe face. Join both. |

### 4b. Hair (clump table in section 5)

| Object | Material | Method |
|---|---|---|
| `SOL_HairCap` | Hair | SHELL of the head faces where (Z > 1.632) OR (Y > 0.030 and Z > 1.480) OR (\|X\| > 0.050 and Y > −0.040 and Z > 1.588), **excluding the ears** (\|X\| > 0.060, 1.520 < Z < 1.585, −0.015 < Y < 0.055). Offset +0.007; reduce to ≈ 600 faces; hem return 0.003. It must not cover the brows. The nape edge (Z 1.48) tucks inside the collar. |
| `SOL_Hair` | Hair | Scalp clumps H1–H10, joined. |
| `SOL_Ponytail` | Hair | 3 braided wavy clumps PT1–PT3 along the ponytail path. |
| `SOL_HairTie` | Coral | Torus, major 0.017, minor 0.0055. Centre (−0.050, 0.100, 1.535), axis (−0.867, −0.417, −0.273) (the ponytail direction). |

### 4c. Jacket, collar, mock-neck

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_MockNeck` | rings (z, rx, ry, cy): (1.400 front / 1.420 back, 0.056, 0.058, 0.036) → (1.440, 0.051, 0.054, 0.038) → (1.455 front / 1.495 back, 0.049, 0.052, 0.036) | around the neck | Charcoal | Loft of 3 sheared rings (z at angle a = z_front + (z_back − z_front)·(1 − cos a)/2), 20 sides, open. It shows in the collar notch. Must clear the throat by ≥ 0.004. |
| `SOL_Jacket` | SHELL; torso + sleeves | torso faces with Z ≥ 0.900 up to the neck line (front 1.400 → back 1.445, sheared as above). Arm faces up to the **sleeve end plane** at elbow + 0.147 along f (= wrist − 0.090), plane normal f | Ivory | Offset **0.010** on the torso, **0.008** on the sleeves (blend over the deltoid). Then: **bust drape:** for verts with 1.10 ≤ Z ≤ 1.22 and \|X\| ≤ 0.11, clamp Y ≤ y_d(Z) = −0.106 + 0.016·(1.22 − Z)/0.12, faded by w = cos²(π·X/0.22). The cloth falls straight from the bust to the waist with **no under-bust tuck and no cleavage**. Corrective Smooth again in that zone. **Armpits:** smooth until no pinching. Hem returns on the neck line, the front hem (Z 0.900) and the sleeve ends. |
| `SOL_Collar` | rings (z_front/z_back, rx, ry, cy): root (1.405 / 1.450, 0.090, 0.086, 0.030) → mid (1.432 / 1.478, 0.078, 0.075, 0.032) → top (1.455 / 1.505, 0.082, 0.079, 0.030) | sits on the jacket's neck line | Ivory outside and inside; **Coral top rim** | Loft of 3 sheared rings, 24 sides. Solidify 0.008 (offset +1, outward), bevel 0.004 (3 seg) on the top edge for a **soft rolled lip**. **Front notch:** boolean out a V whose top spans X −0.042 … +0.028 at Z 1.47 and whose apex is at (−0.020, 1.410). The charcoal mock-neck shows inside it. The top rim faces and the notch edges are `M_SOL_Coral`. **Check: ≥ 0.006 from the jaw everywhere** (the chin is at Z 1.456). Lower the front or push the top ring outward if not. |
| `SOL_WrapFlap` | ribbon 0.035 wide, 0.004 thick | along the **wrap edge**, lying on the jacket on the edge's −X side (her right panel overlaps onto her left) | Ivory | Edge polyline (X, Z), projected along +Y onto the jacket: (−0.042, 1.455) → (−0.020, 1.405) → (0.012, 1.345) → (0.022, 1.300) → (0.022, 0.900). Sweep a flat ribbon 0.002 off the jacket, with a hem return on its free edge. The diagonal finishes **above** the bust; the vertical runs between the bust apices (X +0.022) over the drape. |
| `SOL_SleeveCuff_L/R` | last 0.012 of the sleeve | at the sleeve end (wrist − 0.090) | Coral rim | Flare the final edge ring by 1.08 about the arm axis (a soft bell). Assign `M_SOL_Coral` to the faces within 0.010 of the end plus the hem return. |

### 4d. Back tail (the coat-tail)

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_JacketTail` | ring loft rows (z, rx, ry, cy, p) of the **outer** surface: (0.900, 0.177, 0.102, 0.012, 2.2) (0.860, 0.186, 0.112, 0.014, 2.3) (0.800, 0.192, 0.116, 0.016, 2.3) (0.740, 0.198, 0.118, 0.020, 2.3) (0.680, 0.204, 0.120, 0.024, 2.3) (0.640, 0.208, 0.121, 0.026, 2.3) | Z 0.900 → 0.640, continuing the jacket's hem ring | Ivory, **Coral edges** | `body_loft`, 32 sides. **Hem cut**: delete faces below hem_z(a), where a is the angle from the front (mirror for −X) with keys a 0°→0.900, 35°→0.900, 60°→0.840, 90°→0.760, 120°→0.700, 150°→0.660, 172°→0.645 (linear between keys; bisect for a clean edge). The front (a < 35°) is fully removed, so there the jacket's own hem at Z 0.900 is the front edge. **Back split**: delete the wedge \|a − 180°\| < 8° from Z 0.840 down, widening to ±10° at the hem. Join with `SOL_Jacket` and merge the Z 0.900 seam (0.002). Hem return 0.004. `M_SOL_Coral` on faces within **0.012** of the hem and split edges, plus their returns, and **0.008** along the front hem. Clearance: ≥ 0.025 from the thighs in A-pose (mid-thigh outer X 0.162, back Y +0.073). |

### 4e. Bloom mark (shoulder emblem)

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_EmblemPatch` | flat-top hexagon 0.052 across corners, 0.0025 thick, corners rounded 0.004 | centre (0.272, −0.030, 1.331) on **her LEFT upper arm**; face normal (0.473, −0.708, 0.526); patch "up" = toward the shoulder along the arm, (−0.743, 0, 0.669) | Sand | Build flat (`profile_extrude`), align, then Shrinkwrap (nearest surface point, offset 0.0012) onto `SOL_Jacket` and apply. |
| `SOL_EmblemMark` | 3 almond petals, 0.0015 proud. Centre petal 0.026 long × 0.011 wide; two side petals 0.021 × 0.009 rotated ±42° about the common base point. The base sits 0.012 below the patch centre | on the patch | **Coral** | Petal outline = a lens (x = ±w/2·sin(πt), z = L·t, t 0→1, 10 steps), `profile_extrude`, Shrinkwrap like the patch. **Three petals, never four: it must not read as a cross or an X** (v06's four-petal mark is rejected). |

### 4f. Belt, buckle, pouch, drone dock

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_Belt` | 0.030 tall, 0.006 thick. Outer rings (z, rx, ry, cy, p): (0.970, 0.134, 0.103, 0.001, 2.1) (0.985, 0.130, 0.102, 0.000, 2.1) (1.000, 0.132, 0.102, −0.001, 2.1) | Z 0.970–1.000, **over the jacket** (it cinches the waist) | Charcoal | `body_loft` of 3 rings, Solidify 0.006 inward. Its inner face sits 0.002 off the jacket. |
| `SOL_BeltBuckle` | 0.044 W × 0.010 D × 0.030 H, raised rim | (0, −0.108, 0.985) | Gunmetal | Box + bevel 0.003. Optional shallow three-petal relief. |
| `SOL_Pouch` | body 0.050 W × 0.026 D × 0.070 H; flap 0.052 × 0.030, 0.004 proud, rounded front corners; coral pull tab 0.010 × 0.003 × 0.014 | **her RIGHT front hip**: centre (−0.086, −0.103, 0.960), rot Z −40°, bottom kicked out 6° (rot about local X). Top at the belt (Z ≈ 0.995) via a 0.020 W belt loop | Sand body + flap, Coral tab | Box + bevel 0.006 (2 seg). The back face stays 0.003 off the belt and jacket (push it further out if the hip flare intersects). |
| `SOL_DroneDock` | spherical cap shell, r_in 0.041 / r_out 0.046, half-angle 55°, plus a tab 0.020 W × 0.005 | cap centred on the drone centre (0.203, −0.044, 0.935), cap axis pointing at the hip (−0.966, 0.259, 0). Tab from the belt face (0.123, −0.033, 0.990) down to the cap top (0.170, −0.035, 0.965) | Graphite | Cap = a `lathe` of an arc profile; tab = a short box sweep. The drone itself is section 4k. |

### 4g. Pants, knee pads, boots

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_Pants` | SHELL | body faces 0.165 < Z < 0.930 (legs + pelvis, no feet) | Sand | Offset **0.010** below Z 0.86, blending to **0.003** at the top edge Z 0.93 (hidden under the jacket). Slim fit. Add a hem return at the ankle (tucked into the boot). Optional: 2 shallow seam grooves down the outer leg. |
| `SOL_KneePad_L/R` | 0.084 W × 0.110 H × 0.014 | centre (±0.097, −0.088, 0.478) | **IvoryHard** | Front outline (half): `(0,.055) (.030,.055) (.042,.030) (.042,-.028) (.026,-.055) (0,-.055)`. Pass the points as (y, z) to `bc.profile_extrude`, which extrudes along X, then rotate 90° about Z. Wrap `y += 4.5·x²`. Horizontal ridge 0.004 proud at the centre line. Bevel 0.003. |
| `SOL_KneeStraps` | band 0.018 tall, 0.004 thick | behind each knee at Z 0.478, ring r 0.075 | Charcoal | Partial ring (back 240°) ending under the pad sides. |
| `SOL_Boot_L/R` | ankle boots, shaft top Z 0.165 | feet | Boot (charcoal) | SHELL of the body foot faces with Z < 0.170, offset **0.012** (0.015 where Y < −0.10, toe room). Then clamp every vertex to Z ≥ 0 (flat sole underside). |
| `SOL_BootCuff_L/R` | torus major ≈ shaft radius 0.049, minor 0.008 | at Z 0.165 around each ankle axis (±0.103, 0.017) | Boot | Padded top roll, flared 0.003. |
| `SOL_BootSole_L/R` | 0.020 tall | Z 0.000–0.020 | Graphite | Footprint = the boot's outline at Z 0.004, grown 0.003 outward; extrude 0.020; bevel 0.003. |
| `SOL_BootTab_L/R` | 0.010 W × 0.022 H × 0.003 | heel of each cuff, back centre | Coral | Pull tab (a small accent seen from behind). |

### 4h. Gloves

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_Glove_L/R` | full-finger gloves | body hand faces beyond the plane wrist − 0.012 along f | Glove | SHELL of the hand faces, offset **0.0025** (thin, keeps the fingers readable). Or simply assign `M_SOL_Glove` to those faces of `SOL_Body`. |
| `SOL_Gauntlet_L/R` | tube from wrist − 0.110 to wrist + 0.012 along f; radius = forearm + 0.004 (≈ 0.039 → 0.028); top edge flared +0.002 | both forearms | Glove | `tube`, 16 sides, ellipse radii from the forearm table (section 4j). The sleeve end (wrist − 0.090) overlaps its top by 0.02. |

### 4i. Bloom regen module (her back): the main silhouette hook

All parts are centred on X = 0 (vanes L/R are mirror pairs). **Bud axis** from (0, 0.178, 1.150) to
(0, 0.190, 1.565). The bud cross-section is an ellipse with Y-depth = 0.62 × X-width.

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_Bloom_Mount` | 0.085 W × 0.340 H × 0.012, corners r 0.020 | Z 1.080–1.420, centre (0, 0.118, 1.250) | Graphite | `profile_extrude` of a rounded rectangle. Shrinkwrap its front face onto the jacket back + 0.003. |
| `SOL_Bloom_Spine` | 7 vertebra blocks, each 0.040 W × 0.022 D × 0.032 H | centres Z 1.090 + 0.052·i (i = 0…6), Y 0.136 | Graphite | Box + bevel 0.006 (2 seg). The upper five are inside the bud. The lower ones show beneath it as the "spine". |
| `SOL_Bloom_Yoke` | 2 arms, section 0.022 × 0.014; 2 clamps 0.040 (X) × 0.045 (Y) × 0.014 (Z) | left arm (0.000, 0.136, 1.400) → (0.045, 0.126, 1.406) → (0.085, 0.090, 1.407) → clamp at (0.108, 0.080, 1.405), tilted to the back slope of the shoulder (≈ −25° about X); mirror | Graphite | `tube` (rectangular radii) + boxes with bevel 0.004. Keep the arms **0.006 off the jacket** (they hug the trapezius and pass behind the collar root). |
| `SOL_Bloom_LEDs` | 2 spheres r 0.0035 | on each clamp's back-top face: clamp + (0, 0.020, 0.008) | **Glow** | v04's two coral status lights. |
| `SOL_Harness` | 2 straps 0.030 W × 0.005 | left: (0.108, 0.075, 1.408) → (0.114, 0.040, 1.428) → (0.114, 0.015, 1.436) [over the ridge] → (0.114, −0.015, 1.415) → (0.112, −0.035, 1.385) → (0.110, −0.046, 1.360); mirror | Charcoal | Flat ribbon swept along each polyline, wide face tangent to the jacket and **0.004 off it** (project the points). The ponytail lies **over** the right strap. Straps end at the collarbone, **not** down over the bust. |
| `SOL_HarnessClips` | 0.026 W × 0.012 D × 0.032 H | strap ends (±0.110, −0.050, 1.355) | Gunmetal | Box + bevel 0.003. |
| `SOL_Bloom_Hub` | collar r 0.030 → 0.022, 0.030 tall; glow ring torus major 0.026, minor 0.0035 | base (0, 0.180, 1.140), along the bud axis; ring at Z 1.155 | Graphite + **Glow** ring | `lathe`. |
| `SOL_Bloom_Core` | spindle: radius 0.80 × bud_r(z), Y scaled 0.62 | inside the bud along its axis | **Glow** | `lathe` of the profile below, scaled Y 0.62. **This is what glows through the vane seams.** It may touch the vanes' inner faces (hidden), but must never show through their outer faces. |
| `SOL_Bloom_Vane_C` | apex meridian (0, 0.170, 1.150) → (0, 0.215, 1.250) → (0, 0.236, 1.330) → (0, 0.225, 1.420) → (0, 0.205, 1.500) → (0, 0.185, 1.565); chord widths 0.030, 0.090, 0.110, 0.085, 0.045, 0.000 | back centre | **IvoryHard**, **Coral rim** | **Petal shell:** resample the meridian (Catmull-Rom, 14 rings). Each ring is a circular arc of the given chord with sagitta 0.22 × chord, 7 verts, its **apex on the meridian**, bulging along n_C = (0, 1, 0); chord direction = normalize(tangent × n). Loft; the tip collapses to a point. Solidify 0.007 toward the axis with `material_offset_rim` → `M_SOL_Coral` (a thin coral outline on every petal edge); bevel 0.0015; Subsurf 1, applied. |
| `SOL_Bloom_Vane_L` / `_R` | apex meridian (+X shown; mirror for R): (0.015, 0.165, 1.150) → (0.060, 0.175, 1.230) → (0.084, 0.180, 1.320) → (0.090, 0.172, 1.410) → (0.104, 0.160, 1.480) → **tip (0.125, 0.150, 1.535)**; chords 0.030, 0.085, 0.105, 0.080, 0.040, 0.000 | her left / right side of the bud | IvoryHard, Coral rim | Same petal shell, bulging along **n_L = (1, 0, 0)** (pure sideways; mirror for R), so the chord runs along ±Y and the edges sit at X = apex − sagitta. Tilting n_L backward moves the back edge inward over vane C and **closes the seam**. The upper third **curls outward** so the tips clear the shoulder ridge (Z ≈ 1.43) in the front view. |

**Bud radius table** `bud_r(z)` (also the core profile ×0.80): (1.150, 0.018) (1.190, 0.050) (1.250, 0.075)
(1.320, 0.082) (1.400, 0.072) (1.470, 0.050) (1.530, 0.025) (1.565, 0.000).

**Seam rule:** from straight behind, adjacent vane edges leave a **0.006–0.012 gap** along Z 1.20–1.45 (vane C's
edges sit at X ±0.055, vane L/R inner edges at X ±0.061). The glowing core must show through both seams. Adjust
the vane widths or the L/R meridian X, never the core brightness. Vane origins go at their hinge pivots
(section 4l) so the bud can **open** in-engine (healing burst): about 30° outward each, then close again. Closed is
the default and the silhouette.

### 4j. Injector bracer (her RIGHT forearm, −X)

Build it in a **right-forearm frame**: origin W = wrist_R (−0.5443, −0.0211, 1.0297); f = (−0.7359, −0.1392,
−0.6626) (toward the hand); m = (−0.581, −0.373, 0.724) (the mount normal: the top of the forearm, turned 15°
toward the front so it shows in the front view and in first person); b = f × m = (−0.348, 0.918, 0.194).
The **forearm radius** along f (body, before the gauntlet) is 0.035 at W−0.12, 0.028 at W−0.08, 0.026 at W−0.06,
0.025 at W−0.04 and 0.024 at the wrist.

| Object | Size | Frame position | Material | Method |
|---|---|---|---|---|
| `SOL_Bracer_Band` | open ring, radii (m 0.036, b 0.033), 0.005 thick, 0.070 long | W − 0.085 → W − 0.015 along f | Graphite | `tube` + Solidify, over the gauntlet. |
| `SOL_Bracer_Housing` | lozenge 0.090 long × 0.034 wide (b) × 0.016 tall (m), chamfered ends | f −0.090 → 0.000; bottom at m +0.034, top at m +0.050. World centre ≈ (−0.536, −0.031, 1.090) | **IvoryHard** | `profile_extrude` of the side profile (f, m), width along b, bevel 0.003. **Vial channel**: boolean a slot 0.018 wide × 0.012 deep, from f −0.078 to −0.016, along the top. |
| `SOL_Bracer_Vial` | cylinder r 0.0085, 0.058 long, axis f | centre f −0.047, m +0.047 (top half proud of the channel). World ≈ (−0.537, −0.032, 1.095) | **Glow** | `cylinder`, 16 sides. **The brightest coral point on her front.** |
| `SOL_Bracer_VialCaps` | 2 × cylinder r 0.0095, 0.006 long | both vial ends | Gunmetal | `cylinder`. |
| `SOL_Bracer_Nozzle` | lathe r 0.009 → 0.006, 0.022 long, with a dark bore r 0.003 | f 0.000 → +0.022 at m +0.042 (above the back of the hand) | Gunmetal | `lathe`; the bore is a small boolean or a Graphite disc. |

### 4k. Heal drone (docked on her LEFT hip, +X)

| Object | Size | Position | Material | Method |
|---|---|---|---|---|
| `SOL_Drone` (joined; **origin at its centre**) | shell sphere r 0.040, scaled Z 0.92 | centre (0.203, −0.044, 0.935) | IvoryHard | UV sphere 24×12. |
| — ring thruster band | torus major 0.041, minor 0.007, horizontal | around the equator | Graphite | Part of `SOL_Drone`. Add 4 small vent notches (optional). |
| — eye | bezel cylinder r 0.017, 0.008 deep; lens disc r 0.011, recessed 0.002 | facing **e = (0.707, −0.707, 0)** (forward-out); lens centre ≈ (0.230, −0.071, 0.935) | Graphite bezel, **Glow** lens | Readable in both front and side views. A single eye. **No cross, no hexagon body** (do not echo Apex's D.O.C.). |
| — vent | disc r 0.014 | underside, local Z −0.036 | **Glow** | Dim, seen from below. |
| — antenna | r 0.002, 0.018 long, tilted 15° back | top | Graphite | v09's small stub. |

The drone must not touch the tail (the tail's top ring at Z 0.900 is at X ≈ 0.177; the drone surface curves away
there).

### 4l. Sockets and pivots (empties)

| Empty | Position | Notes |
|---|---|---|
| `SOL_SOCKET_Halo` | (0, 0.020, 1.906) | 0.22 m above the skull crown (1.686), centred over the skull. Not parented to head rotation (halo spec). |
| `SOL_SOCKET_Hand_R` | (−0.558, −0.049, 1.003) | Weapon grip point (web of the right hand). Axes: gun −Y (muzzle) = right-hand X_h (finger direction), gun +Z (top) = T_R (thumb side), gun +X = −D_R. The engine re-offsets after rigging. |
| `SOL_SOCKET_Hand_L` | (0.558, −0.049, 1.003) | Support hand (mirror). |
| `SOL_SOCKET_Injector` | (−0.586, −0.040, 1.044) | Bracer muzzle; local −Y along f (heal vials fire along the forearm). |
| `SOL_SOCKET_Drone` | (0.203, −0.044, 0.935) | Drone dock / launch point. Parent `SOL_Drone` to it. |
| `SOL_SOCKET_Bloom` | (0, 0.185, 1.330) | Heal-aura VFX origin (bud core centre). |
| `SOL_PIVOT_Vane_C / _L / _R` | (0, 0.172, 1.150) / (0.015, 0.167, 1.150) / (−0.015, 0.167, 1.150) | Vane origins. Open pose: C −30° about X (tip swings back), L +32° about Y, R −32° about Y. |

---

## 5. Face recipe and hair clumps

**Face.** The `face=` overrides in section 3 do most of the work. They give defined cheekbones (cheek 1.15,
around (±0.055, −0.033, 1.550)), soft full lips (lip_full 1.15), a softer, slightly broader nose
(nose_w 1.10, nose_len 0.97), a gently tapered soft jaw and chin (0.98 / 0.96), and open, warm eyes with a slight
lift (eye_open 1.06, eye_tilt 0.05). The expression is **calm, kind and confident**: relaxed brows (no frown; you may
raise the inner brow ends 0.001), a closed-mouth half smile (section 4a), and the gaze straight ahead. Keep the
detail as modelled shapes, with no painted pores or makeup. **Do not copy Kestrel's determined lowered brows.**
Optional: a subtle cheekbone plane (verts within 0.018 of (±0.055, −0.033, 1.550) move 0.0015 outward along their
normal).

**Hair.** Make each clump as a Blender curve: `bevel_mode='ROUND'`, `bevel_depth` = half the width,
`use_fill_caps`. Use the per-point `radius` for the taper and **flatten** each clump to width:thickness ≈ 2.5:1 (a
lens-shaped bevel object, or scale the converted mesh along the clump normal). Tilt the points so the flat face
lies on the scalp. Resolution 4, 8 bevel verts. Convert to mesh and join. Keep ≥ 0.004 between clumps and the cap.
Add a **soft wave**: a lateral sine offset of amplitude 0.004 and period ≈ 0.09 m along each long clump. The
coordinates are design guides, root → tip:

| Clump | Points (x, y, z) | Root W × T | Taper (radius root → tip) |
|---|---|---|---|
| H1 front sweep (from the part across the forehead to **her left**, over the left ear, back to the tie) | (−0.035,−0.078,1.650) → (0.005,−0.092,1.662) → (0.050,−0.082,1.646) → (0.085,−0.040,1.615) → (0.090,0.015,1.598) → (0.068,0.072,1.552) → (0.015,0.100,1.540) → (−0.040,0.101,1.535) | 0.075 × 0.026 | 1.0 → 0.45 |
| H2 left face-framing strand (outside the left ear, to jaw level) | (0.040,−0.082,1.645) → (0.072,−0.066,1.612) → (0.088,−0.040,1.572) → (0.093,−0.028,1.535) → (0.087,−0.030,1.500) → (0.091,−0.022,1.468) | 0.032 × 0.012 | 1.0 → 0.25, S-wave |
| H3 right face-framing strand (shorter, to the cheek) | (−0.040,−0.080,1.645) → (−0.068,−0.070,1.615) → (−0.085,−0.046,1.576) → (−0.089,−0.033,1.538) → (−0.084,−0.030,1.505) | 0.026 × 0.011 | 1.0 → 0.25 |
| H4 right side sweep (over the right ear to the tie) | (−0.042,−0.070,1.662) → (−0.076,−0.045,1.642) → (−0.091,0.005,1.600) → (−0.083,0.055,1.560) → (−0.058,0.092,1.540) | 0.062 × 0.022 | 1.0 → 0.5 |
| H5 crown, left-back | (0.020,−0.020,1.702) → (0.056,0.040,1.682) → (0.071,0.085,1.612) → (0.040,0.106,1.560) → (−0.030,0.104,1.538) | 0.066 × 0.022 | 1.0 → 0.5 |
| H6 crown, centre-back | (−0.015,−0.030,1.704) → (−0.005,0.050,1.697) → (0.000,0.106,1.632) → (−0.015,0.111,1.575) → (−0.042,0.104,1.540) | 0.066 × 0.022 | 1.0 → 0.5 |
| H7 crown, right-back | (−0.035,−0.040,1.692) → (−0.060,0.030,1.677) → (−0.075,0.080,1.612) → (−0.066,0.100,1.560) → (−0.052,0.101,1.540) | 0.060 × 0.022 | 1.0 → 0.5 |
| H8 part lift (volume, sweeps left; tucks under H5) | (−0.036,−0.062,1.684) → (0.000,−0.052,1.706) → (0.045,−0.022,1.702) → (0.076,0.020,1.662) | 0.072 × 0.028 | 1.0 → 0.7 |
| H9 nape fill, left | (0.058,0.062,1.545) → (0.030,0.088,1.530) → (−0.030,0.097,1.532) | 0.040 × 0.014 | 1.0 → 0.6 |
| H10 nape fill, right | (−0.070,0.058,1.545) → (−0.054,0.092,1.534) | 0.036 × 0.014 | 1.0 → 0.6 |

**Ponytail** (`SOL_Ponytail`). The bundle centreline and bundle radius:

| Point | (x, y, z) | Bundle r |
|---|---|---|
| P0 tie (coral band) | (−0.050, 0.100, 1.535) | 0.020 |
| P1 behind the neck, above the collar | (−0.104, 0.074, 1.518) | 0.024 |
| P2 over the right shoulder ridge | (−0.128, 0.022, 1.470) | 0.026 |
| P3 front of the shoulder | (−0.120, −0.060, 1.408) | 0.026 |
| P4 upper chest | (−0.106, −0.088, 1.340) | 0.024 |
| P5 | (−0.096, −0.112, 1.270) | 0.020 |
| P6 | (−0.091, −0.118, 1.210) | 0.014 |
| P7 tip (soft outward curl) | (−0.099, −0.108, 1.160) | 0.005 |

Build 3 clumps PT1–PT3, each about 0.6 × the bundle radius. Offset them ±0.010 around the centreline (at 0°, 120°
and 240° in the section plane) and twist the offsets 180° along the length, so they braid loosely. Give each its own
wave phase (0, 2.1, 4.2 rad). Add 2–3 thin wisps (0.010 W) peeling off the tip. **Clearances:** ≥ 0.005 from the
collar (its outer wall is at X ≈ −0.077 near P1), the strap, the jacket chest and the right side-vane. The ponytail
lies **over** the strap and jacket.

**Snapping.** Points at Z ≥ 1.52 on H1–H10 are *attached*. Slide each along the ray from the cap centre
C = (0, 0.020, 1.572) so it sits half a clump thickness + 0.002 above the cap ellipsoid (radii 0.084, 0.098, 0.122).
With `k = √((dx/0.084)² + (dy/0.098)² + (dz/0.122)²)`, scale (p − C) by `k_t / k`, where
`k_t ≈ 1 + (t/2 + 0.002)/0.10`. The remaining points (strand tips, nape ends, ponytail) hang *free*: keep them as
given, but never within 0.004 of the body, collar or jacket (push them out along the surface normal).

**Layout checks:** the **side part** is on her right at X ≈ −0.036, from the front hairline (Y −0.075) to the
crown. H1 and H4 clear the ear tops (Z 1.579) by ≥ 0.006. **Both lobes and the coral studs stay visible** in the
front view (H2 hangs outside the lobe at X ≈ 0.09). No clump covers an eye (eye outer corners at X ±0.045). Hair
top ≈ Z 1.71, far below the halo (1.906 − 0.03).

---

## 6. Materials (linear RGB, `bc.material`)

| Material | Palette token | Base colour (linear) | Rough | Metal | Extra / texture (subtle multiply) | Used on |
|---|---|---|---|---|---|---|
| `M_SOL_Skin` | skin deep | (0.26, 0.14, 0.085) | (fb) | 0 | made by `build_female_base(skin=…)`; `skin_soft.png` optional | head, ears, neck top |
| `M_SOL_Lips` | skin deep, deepened | (0.15, 0.065, 0.048) | 0.45 | 0 | — | lips region |
| `M_SOL_Eye*`, `M_SOL_Brow`, `M_SOL_Lash` | — | iris (0.10, 0.055, 0.030), brow (0.018, 0.011, 0.008) | (fb) | 0 | made by `fb` | eyes, brows, lashes |
| `M_SOL_Hair` | dark warm brown-black (**not** Kestrel's blue-black) | (0.022, 0.012, 0.009) | 0.45 | 0 | `hair_strands.png` mix 0.35, coat 0.15 | hair cap, clumps, ponytail |
| `M_SOL_Ivory` | ivory | (0.70, 0.67, 0.60) | 0.65 | 0 | `fabric_soft.png` mix 0.25 | jacket, tail, collar, wrap flap |
| `M_SOL_IvoryHard` | ivory (polymer) | (0.70, 0.67, 0.60) | 0.40 | 0 | `polymer_stipple.png` mix 0.2 | Bloom vanes, bracer housing, drone shell, knee pads |
| `M_SOL_Sand` | sand | (0.36, 0.28, 0.18) | 0.75 | 0 | `fabric_ripstop.png` mix 0.35 | pants, pouch, emblem patch |
| `M_SOL_Charcoal` | charcoal-cloth | (0.035, 0.037, 0.045) | 0.70 | 0 | `fabric_soft.png` mix 0.3 | mock-neck, belt, harness straps, knee straps |
| `M_SOL_Glove` | charcoal-cloth (leather) | (0.035, 0.037, 0.045) | 0.55 | 0 | `leather_soft.png` mix 0.35 | gloves, gauntlets |
| `M_SOL_Boot` | charcoal-cloth (leather) | (0.035, 0.037, 0.045) | 0.60 | 0 | `leather_soft.png` mix 0.35 | boot shells, cuffs |
| `M_SOL_Graphite` | graphite | (0.030, 0.033, 0.040) | 0.55 | 0 | `polymer_stipple.png` mix 0.3 | Bloom mount/spine/yoke/hub, bracer band, drone band/bezel/antenna, drone dock, boot soles |
| `M_SOL_Gunmetal` | gunmetal | (0.11, 0.115, 0.12) | 0.35 | 0.85 | `brushed_metal.png` mix 0.3 | buckle, harness clips, vial caps, injector nozzle |
| `M_SOL_Coral` | coral (Solace), **not emissive** | (1.0, 0.36, 0.30) | 0.50 | 0 | coat 0.3 on the earrings only if split out | collar rim + notch edges, wrap piping, cuff rims, hem/tail/split edges, vane rims, emblem mark, hair tie, earrings, pouch tab, boot tabs |
| `M_SOL_Glow` | coral, **emissive** | (1.0, 0.36, 0.30), emission (1.0, 0.36, 0.30), strength 4 | 0.40 | 0 | — | **Bloom core (seams), hub ring, 2 yoke LEDs, bracer vial, drone eye lens, drone vent** |

**The coral rule:** `M_SOL_Glow` is the **only emissive material**, used only on her tech: the Bloom (core seen
through the seams, hub ring, LEDs), the **vial** and the **drone eye** (the brightest small points), and the drone
vent (dim, underneath). Everything on the cloth (piping, edges, emblem, hair tie, earrings) is painted coral and
does **not** glow. There is **no other accent colour** (no teal, no red, no pink/lilac).

Textures live in `art/textures/`. They are optional, and the flat colour must carry the look without them.

---

## 7. Layering (inside → out) and offsets

1. `SOL_Body` skin (head, neck); eyes, brows, lashes.
2. `SOL_MockNeck` around the neck (≥ 0.004 off the throat).
3. `SOL_Pants`: body + 0.010, thinning to +0.003 at the top edge (Z 0.93), which is hidden under the jacket.
4. `SOL_Gauntlet`s over the wrists (+0.004); gloves on the hands (+0.0025).
5. `SOL_Jacket` (+0.010 torso / +0.008 sleeves) over the pants top and the gauntlet tops (the sleeve end overlaps the
   gauntlet by 0.02). `SOL_Collar` sits on the jacket's neck line, with the mock-neck inside it.
6. `SOL_JacketTail` hangs free from the jacket hem ring (Z 0.900), ≥ 0.025 off the legs.
7. `SOL_WrapFlap` +0.002 on the jacket front; piping/coral bands are face assignments (no extra offset).
8. `SOL_Belt` over the jacket at the waist (inner face +0.002). Buckle, pouch and drone dock hang from it, with
   their back faces 0.003 off the belt/jacket.
9. `SOL_EmblemPatch` +0.0012 on the left sleeve; the mark +0.0015 on the patch.
10. `SOL_Bloom_Mount` +0.003 on the jacket back. Yoke arms and harness straps 0.004–0.006 over the jacket;
    straps pass over the shoulder ridge. Clips on the strap ends.
11. Bloom spine on the mount; hub, core and vanes outside it (the bud's front face clears the mount by ≥ 0.008).
12. `SOL_Bracer` parts over the right gauntlet.
13. Knee pads +0.003 over the pants; knee straps; boots over the pant hems (the pant ankle sits inside the
    boot shaft).
14. `SOL_HairCap` +0.007 over the skull (its nape edge tucks inside the collar). Clumps over the cap.
    **Ponytail over** the collar top, the right strap and the jacket chest. The coral tie sits on the bundle.
15. Earrings on the lobes.

Intersections hidden inside other meshes are fine. Visible z-fighting is not. **Delete hidden body faces** at the
end (section 4a).

## 8. Triangle budget (target ≈ 46k, hard max 70k)

| Group | Tris |
|---|---|
| Head, face, ears, eyes, brows, lashes, neck top (body after culling) | 7k |
| Hands (gloves) + gauntlets | 3.5k |
| Hair cap + 10 clumps | 7k |
| Ponytail (3 clumps + wisps) + tie | 3k |
| Jacket shell (≈ 1.6k faces) + wrap flap + cuffs | 4k |
| Tail | 2k |
| Collar + mock-neck | 1.2k |
| Pants (≈ 1.4k faces) | 3k |
| Knee pads + straps | 0.8k |
| Boots + cuffs + soles + tabs | 3k |
| Belt, buckle, pouch, dock | 1.5k |
| Emblem | 0.4k |
| Bloom (mount, spine, yoke, LEDs, harness, clips, hub, core, 3 vanes) | 6k |
| Bracer | 1.3k |
| Drone | 1.3k |

## 9. Silhouette hooks

- **Bud**: from the front, two pointed vane tips above the shoulders. From the side and back, a slim closed
  teardrop on the back with two glowing seams.
- **Ponytail**: a dark mass over the right shoulder falling onto the chest. Front silhouette: an asymmetric bulge
  at the right shoulder.
- **Coat-tail**: below the belt the outline widens past the hips and splits at the back. From the side, the hem
  sweeps from hip height at the front down to mid-thigh at the back.
- Secondary: the bracer knob on the right forearm, the drone ball on the left hip, the cinched waist, ivory knee
  pads.

Test it: render front/side/back as flat black silhouettes at 64 px tall. You must still be able to point to the vane
tips, the ponytail and the tail flare. Then render with colour at 64 px: the ivory torso and the dark ponytail
must separate clearly.

## 10. Concept images: what to trust

| Image | Trust it for | Deviations (the brief wins) |
|---|---|---|
| **v09 → `concept_main.png`** (front, A-pose) | Whole look and colour blocking; **all sides correct** (ponytail and bracer on her right, emblem and drone on her left); **vane tips with coral edges peeking above both shoulders**; shoulder straps; coral hair tie; wrap closure with coral piping; sand pants with ivory knee pads; charcoal ankle boots; full gloves. | The wrap front hangs to mid-thigh on her left side: the **front ends at Z 0.900** and only the back/side tail is long. The straps run down to the waist: **stop them at the collarbone clips**. The pouch is black: make it **sand**. The emblem drifts toward a 4-petal X: use the **three-petal Bloom mark**. Skin is slightly light: use **skin deep**. The sleeve/gauntlet split is vague: sleeve end at wrist − 0.090. |
| **v08 → `concept_turnaround.png`** (front / side / back) | Jacket cut: asymmetric wrap, front hem curving down into the **split back tail at mid-thigh with coral edging**; long ivory sleeves; collar height; consistent sides in all three views; A-pose. | **No Bloom module at all**: add it from v04 and section 4i. The side view is broken (a black disc instead of the arm), as in Kestrel's turnaround, so ignore it. Knee pads are grey: make them **ivory**. Ignore the right-thigh strap/holster (she has none). The back-view hair hangs loose: the ponytail goes **over her right shoulder**. |
| **v05 → `concept_face.png`** (portrait) | Face shape, skin tone, cheekbones, soft full lips, warm eyes, coral studs, side part, face-framing strands, ponytail draped over her right shoulder, collar with coral piping, charcoal mock-neck. | The emblem is a **heart**: use the three-petal Bloom mark. The smile reads a little sly: make it a **calm, warm closed-mouth smile**. The collar is a notched stand collar: build the soft rolled wrap collar (section 4c). |
| **v04** (turnaround) — **back view only** | **Bloom module**: closed teardrop bud of 3 vanes with coral seams, charcoal yoke with two coral LEDs, hub at the base, mounted between the shoulder blades; split back tail with coral edges. | Short sleeves with charcoal arms (wrong: long ivory sleeves). The front view puts the bracer on her **left** (wrong) and adds a thigh holster (drop it). The tail reaches the knee (make it **mid-thigh**). The hair hangs down the back. The side view is broken. |
| **v03** (front, slight 3/4) | Painterly finish and value pattern closest to Kestrel's concept art; sides correct; jacket front cut away above the hips with coral-edged tails; ivory knee pads. | The bud barely shows (one vane over the left shoulder). The legs are crossed: use the A-pose. |
| v01 (front) | Early drone read (white sphere, coral eye) and the shoulder-emblem placement. | Bracer on her **left** (wrong); holster; a single wing-like vane; skin too light. |
| v02 (front) | Clean symmetric A-pose. | **Everything is mirrored** (ponytail, emblem, bracer, drone on the wrong sides); front-open lab coat; no Bloom. |
| v06 (front) | Sides correct; bracer proportions. | **Four-petal emblem reads like a cross: never use it.** Long front apron and a sand skirt panel. |
| `_rejected/v07_red_cross.png` | Nothing. | Red cross on the shoulder; rear-focused framing. |
| `proportions_overlay.png` | Every dimension and position in this brief, drawn over the real base-body silhouette. | The gear shapes are schematic lines and dots, not design. |

## 11. Build order and checks

1. `build_female_base` (section 3), then read `res["joints"]`/`res["dims"]`, then the SHELL garments (jacket, pants,
   boots, gloves), collar, mock-neck, tail. Render front/side and compare against `proportions_overlay.png`.
2. Face tweaks (lips, smile) → hair cap → clumps → ponytail + tie → earrings. Check from the front: **ponytail at
   screen-left** in the Front view; both studs visible; eyes clear.
3. Belt, buckle, pouch (screen-left), emblem (screen-right), knee pads, boots.
4. Bloom: mount, spine, yoke, harness, hub, core, vanes. Check the **front-view vane tips above both shoulders**, the
   two glowing seams from behind, and no wing read.
5. Bracer (right-forearm frame), drone + dock (screen-right hip), sockets/pivots.
6. Delete hidden body faces → materials → `bc.uv_all()` → `bc.stats()` (≤ 50k) → renders (front, right, back,
   three_quarter + sheet) → export.

**Final self-check:**

- Ponytail, bracer and pouch on **−X**; emblem and drone on **+X**.
- **No cross or X shape anywhere**; the emblem has three petals.
- No armour plates, shoulder pads or tier pips; `SOL_SOCKET_Halo` at (0, 0.020, 1.906).
- Exactly one emissive material (`M_SOL_Glow`), only on the Bloom, vial and drone.
- The jacket front ends at the hip (Z 0.900); the tail reaches mid-thigh (Z 0.645) at the back and is split.
- No cleavage and no shrink-wrapped bust (the drape rule); straps stop at the collarbone.
- The collar does not intersect the jaw; the ponytail does not intersect the collar or the strap.
- Feet at Z = 0; skull crown 1.686 (+ hair ≈ 1.71).
