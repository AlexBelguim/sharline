# VK-50 "WARDEN" — build brief (authoritative modeler spec)

Heavy-calibre (12.7 mm class) bolt-action anti-materiel sniper rifle. Prefix **`WARDEN`**, folder
`assets/weapons/vk50_warden/` (see `art/WEAPON_MODULAR_SPEC.md`). Budget: heavy sniper **12k–25k tris** (hard max 35k)
for base gun + default stock + mag_5 + optic_sniper + bipod together.

**Order of authority:** `art/STYLE_GUIDE.md` > `art/WEAPON_MODULAR_SPEC.md` (part split, sockets) > **this brief**
(shapes, numbers, colours) > the concept images. Where an image disagrees with this file, this file wins.

Reference files in this folder:
| File | Use it for |
|---|---|
| `profile_sketch.png` | **The proportions.** Exact 1 px = 1 mm orthographic side + top render of a coarse proxy built from the numbers below, with a metric grid, origin, bore line, rail top and scope axis. |
| `proxy_right.png`, `proxy_left.png`, `proxy_three_quarter.png` | The same proxy in the `bc.render_views` "right" (= gun's LEFT side, counter visible), "left" (= gun's RIGHT side, bolt + ejection port) and three-quarter views. Your final renders should match these silhouettes. |
| `warden_proportion_proxy.py` | The proxy build script (headless Blender, uses `blender_common`). Every number in this brief is in it. Use it as a coordinate cheat sheet / starting point — it is NOT the finished asset (no detailing, no sockets, no module split). |
| `concept_main.png` (= `v02.png`) | Style, colour blocking, overall mood, side silhouette. |
| `concept_34.png` (= `v04.png`) | Volumes in perspective: brake, handguard, scope bell, bipod, stock. |
| `v01`–`v08.png` | All generations, see section 7 for which ones to trust for what. |

---

## 1. Identity and silhouette

The Warden is the "big gun" of the prototype: a long, heavy, horizontal rifle that reads as *sniper* from any
distance. Read from the muzzle backwards: a **big blocky see-through muzzle brake**, a **gunmetal fluted barrel**,
a **long slotted graphite handguard** with a **bipod deployed forward like an A-frame**. Then a **monolithic
graphite receiver** with a full-length top rail, a small **ice-blue ammo counter** on its left side and an
**oversized bolt knob** sticking out on the right. Under it, a **chunky box magazine** with a sand base plate.
Behind it, the **sand pistol grip** and an angular **sand skeleton stock** with a big triangular window, a
cheek riser floating on two posts, a thick black recoil pad and a short **monopod spike**. On top, a **large
5–25x scope** with a sunshade and a thin ice ring at the objective. Near-future (2060s) and clean, chunky and
chamfered, but a real-world archetype (think AX50 / MRAD class chassis rifle): no glow strips, no floating parts,
no energy coils.

Overall bounds (default config, bipod deployed): **Y −1.100 … +0.320 (1.42 m)**, Z −0.20 … +0.23, X −0.12 … +0.07.

## 2. Axes, origin, handedness (read twice)

- Metres, Z up, **muzzle toward −Y**, bore axis parallel to Y at **x = 0, z = 0.075**.
- **Origin (0,0,0) = top centre of the pistol grip** (where the web of the hand sits). The chassis underside is at
  z = 0 there; the grip polygon starts at z = +0.004 (sinks 4 mm into the chassis).
- **Handedness: with the muzzle at −Y and Z up, the shooter's RIGHT side is −X and LEFT side is +X** (same as Blender
  character convention: `.L` = +X).
  - **Bolt handle, bolt knob, ejection port, windage turret → −X (right).**
  - **Ammo counter, side-focus knob → +X (left).**
  - `bc.render_views` view "right" (camera at +X) therefore shows the gun's LEFT side (counter, muzzle pointing
    left — matches the concept). View "left" shows the bolt side.
  - Note: `WEAPON_MODULAR_SPEC.md` calls the +X side rail socket `_SOCKET_Side_R`. Keep the spec's socket *names*
    (engine binding) but do **not** move the bolt to +X because of it.
- Part names `WARDEN_<Part>`, helpers start with `_`. Materials `M_Warden_<Surface>`.
- `bc.profile_extrude(points=[(y, z), ...], width)` builds a slab centred on X = 0 → all side profiles below are
  given directly in (y, z) gun coordinates and can be pasted in.
- `bc.lathe(profile=[(r, h), ...], rot=(90, 0, 0), loc=(0, 0, z_axis))` lays the lathe along Y with
  **h = −y** (positive h runs toward the muzzle). Profiles below are given as (r, y) — negate y for h.
- `bc.cylinder(..., rot=(90, 0, 0))` = axis along Y; `rot=(0, 90, 0)` = axis along X.

## 3. Side-profile coordinate sketch (y, z) in metres

Key stations along Y (muzzle → butt):

| y | What happens there |
|---|---|
| −1.100 | front face of muzzle brake (`_SOCKET_Muzzle`) |
| −0.950 | rear of brake (collar), barrel visible behind it |
| −0.925 … −0.700 | 6 barrel flutes (visible front half of barrel) |
| −0.761 | bipod feet (deployed) |
| −0.690 | front of handguard and end of top rail |
| −0.645 | side rail segments (centre) |
| −0.650 … −0.540 | bottom rail (bipod clamp at −0.600) |
| −0.340 | handguard / receiver joint, chassis "chin" starts |
| −0.300 | receiver front face |
| −0.290 … −0.104 | magazine well (mag body −0.276 … −0.118) |
| −0.240 | barrel breech (hidden in receiver), barrel length 0.72 → muzzle at −0.965 inside the brake |
| −0.104 … −0.012 | trigger guard, trigger at −0.055 |
| −0.020, −0.140 | scope rings (rail clamp centre −0.080 = `_SOCKET_Optic`) |
| 0.000 | **origin** — top centre of grip |
| +0.065 | scope eyepiece rear |
| +0.080 | receiver rear / stock joint (`_SOCKET_Stock` at z 0.075) |
| +0.112 | rear of bolt shroud |
| +0.205 | monopod |
| +0.292 / +0.320 | stock rear post / recoil pad rear |

Key heights:

| z | What |
|---|---|
| +0.228 | top of elevation turret (highest point) |
| +0.178 | scope axis |
| +0.136 | top of cheek riser |
| +0.1375 | rail top surface (rail base on receiver/handguard top at 0.128) |
| +0.128 | receiver and handguard top |
| +0.075 | **bore axis** |
| +0.025 / +0.030 | receiver bottom / handguard bottom |
| 0.000 | chassis underside at the grip = origin |
| −0.068 | magwell bottom lip |
| −0.132 | grip bottom |
| −0.168 | mag_5 base plate bottom |
| −0.197 / −0.198 | bipod feet / monopod tip (rifle rests level on them) |

Side profiles (closed polygons, (y, z), paste into `profile_extrude`):

```
RECEIVER   (w 0.078)  (0.080,0.035) (0.080,0.112) (0.064,0.128) (-0.292,0.128) (-0.300,0.120)
                      (-0.300,0.033) (-0.292,0.025) (0.072,0.025)
CHASSIS    (w 0.070)  (0.080,0.025) (-0.340,0.025) (-0.296,-0.040) (-0.290,-0.058) (-0.282,-0.068)
                      (-0.112,-0.068) (-0.104,-0.060) (-0.104,-0.010) (-0.030,0.000) (0.040,0.000) (0.080,-0.010)
GRIP       (w 0.034)  (-0.026,0.004) (0.030,0.004) (0.042,-0.018) (0.064,-0.110) (0.062,-0.124) (0.052,-0.132)
                      (0.020,-0.132) (0.010,-0.124) (-0.004,-0.072) (-0.010,-0.054) (-0.020,-0.036) (-0.026,-0.012)
TRIG GUARD (w 0.020)  outer (-0.104,-0.005) (-0.104,-0.062) (-0.094,-0.072) (-0.026,-0.072) (-0.012,-0.058) (-0.014,-0.005)
                      hole  (-0.092,-0.004) (-0.092,-0.058) (-0.086,-0.062) (-0.030,-0.062) (-0.024,-0.054) (-0.026,-0.004)
TRIGGER    (w 0.008)  (-0.058,0.000) (-0.050,0.000) (-0.052,-0.030) (-0.060,-0.048) (-0.066,-0.046) (-0.060,-0.028)
MAG_5 body (w 0.052)  (-0.270,0.000) (-0.120,0.000) (-0.118,-0.150) (-0.276,-0.150)
STOCK      (w 0.046)  (0.080,0.045) (0.122,0.045) (0.140,0.080) (0.150,0.088) (0.282,0.092) (0.292,0.100)
                      (0.292,-0.118) (0.282,-0.126) (0.240,-0.126) (0.100,-0.032) (0.080,-0.012)
  window (cut through) (0.150,0.054) (0.266,0.070) (0.266,-0.094)
CHEEK RISER (w 0.040) (0.150,0.100) (0.158,0.128) (0.172,0.136) (0.276,0.136) (0.284,0.128) (0.284,0.100)
RECOIL PAD (w 0.050)  (0.292,0.104) (0.312,0.100) (0.320,0.082) (0.320,-0.110) (0.312,-0.126) (0.292,-0.130)
```

Lathe profiles, (r, y) — use h = −y:

```
BARREL  axis z 0.075: (0,-0.240) (0.023,-0.240) (0.023,-0.600) (0.021,-0.680) (0.021,-0.940) (0.016,-0.942)
                      (0.016,-0.965) (0,-0.965)        -> 0.72 m long, 24 steps
SCOPE   axis z 0.178: (0,+0.065) (0.0200,+0.065) (0.0250,+0.060) (0.0250,+0.012) (0.0230,+0.010) (0.0230,-0.002)
                      (0.0185,-0.012) (0.0185,-0.165) (0.0340,-0.212) (0.0340,-0.255) (0.0300,-0.255) (0,-0.255)
ICE RING             : (0.0320,-0.255) (0.0355,-0.255) (0.0355,-0.265) (0.0320,-0.265)
SUNSHADE (open tube) : (0.0300,-0.265) (0.0330,-0.265) (0.0330,-0.315) (0.0300,-0.315)
```

## 4. Part list

Positions are **gun coordinates** (origin at grip). For a separate module whose own origin is its mount point
(modular spec), subtract that module's origin from every coordinate. "→" = suggested procedural method.
Bevel = `bc.add_bevel` width; use 1 segment (chamfer look) unless noted, 2 on hand-held sand parts.

### 4.1 Base gun (one file, children of `WARDEN_Root` at 0,0,0)

| Object | Size (m) / position | Mat | How |
|---|---|---|---|
| `WARDEN_Receiver` | monolithic upper, y +0.080 … −0.300, z 0.025 … 0.128, **w 0.078** | graphite | → `profile_extrude` RECEIVER, bevel 0.004. Booleans: **ejection port** on −X: box y −0.175…−0.040, z 0.062…0.104, 0.015 deep; **bolt-handle notch** on −X: y +0.042…+0.082, z 0.079…0.105, 0.015 deep; **counter recess** on +X: y −0.080…−0.020, z 0.070…0.098, 0.004 deep. Optional: 2–3 shallow panel-line grooves (0.003 wide, 0.002 deep), e.g. a line at z 0.060 from y −0.300 to −0.190 then rising 30° — keep them few. |
| `WARDEN_Counter` | screen 0.052 × 0.020, face at x +0.038 (1 mm inside receiver skin), centre y −0.050, z 0.084, tilted 0° | **ice emissive** | → thin box (0.003 × 0.052 × 0.020). The ONLY emissive part of the gun. Optional: 2 tiny dark boxes on it suggesting a "05" digit readout. |
| `WARDEN_Chassis` | lower bed + magwell, y +0.080 … −0.340, z −0.068 … 0.025, w 0.070 | graphite | → `profile_extrude` CHASSIS, bevel 0.004. The sloped "chin" from (−0.340, 0.025) to (−0.296, −0.040) is a silhouette feature (matches concepts). Magwell opening: boolean a 0.054 × 0.154 box up into it from below so the mag visibly enters a hole. |
| `WARDEN_RailTop` | stylised Picatinny, y +0.078 … −0.690, z 0.128 … 0.1375, **top width 0.021** | graphite | → `profile_extrude` of a crenellated side profile (teeth 0.0055 long, slots 0.0045 long × 0.003 deep, pitch 0.010) with width 0.021 across X, bevel 0.001. Cheap and exact (no booleans). |
| `WARDEN_Handguard` | free-float, y −0.300 … −0.690, x ±0.036 (w 0.072), z 0.030 … 0.128 | graphite | → box (0.072, 0.390, 0.098) at (0, −0.495, 0.079), bevel **0.012, 1 seg** (octagonal section). Booleans: **bore tunnel** cylinder r 0.030 along Y through the whole length (makes it a shell so the gunmetal barrel shows through the slots); **4 side slots** through X, each 0.055 (Y) × 0.020 (Z), z centre 0.084, y centres −0.370, −0.445, −0.520, −0.595 (round the cutter ends: bevel the cutter 0.008/2 seg); **2 bottom slots** 0.024 × 0.055, cutter 0.04 tall at z 0.030 (opens the bottom wall only), y −0.400, −0.475. Front end: barrel hole r 0.025 + 0.006 chamfer. |
| `WARDEN_RailSide` ×2 | 0.0095 (X) × 0.060 (Y) × 0.021 (Z), outer face x ±0.0455, centre y −0.645, z 0.079 | graphite | → crenellated profile like the top rail (rotated) or plain box with 3 boolean slots. |
| `WARDEN_RailBottom` | 0.021 × 0.110 × 0.0095, y −0.650 … −0.540, z 0.0205 … 0.030 | graphite | → same crenellated extrude, flipped. Bottom surface z 0.0205 = bipod mount. |
| `WARDEN_Barrel` | **0.72 m**, y −0.240 … −0.965, r 0.023 → 0.021 (step at −0.600 … −0.680), muzzle thread r 0.016 | gunmetal | → `lathe` BARREL, 24 steps, `rot=(90,0,0)`, `loc=(0,0,0.075)`. **6 flutes** y −0.700 … −0.925: six box cutters 0.006 × 0.225 × 0.006 centred at radius 0.022, angles 30° + 60°·i around the bore, EXACT boolean (or lathe with 24 steps and push every other pair of vertices in by 0.003 in that range). Slab-sided is acceptable if flutes fail, but flutes read better. |
| `WARDEN_Brake` | **big blocky**: box 0.070 (X) × 0.150 (Y) × 0.062 (Z), y −0.950 … −1.100, centred on bore | gunmetal | → box, booleans **before** bevel: **2 large through-ports** (cut through both sides along X so you can see through): A y −1.022 … −0.985, B y −1.074 … −1.035, both z 0.053 … 0.097; **1 small relief port** y −0.975 … −0.962, z 0.062 … 0.088; front bore hole r 0.010. Then bevel 0.006 (1 seg). Front face gets a bigger 0.010 chamfer if you can. Collar: cylinder r 0.025 × 0.012 at y −0.956. |
| `WARDEN_Grip` | y −0.026 … +0.064, z +0.004 … −0.132, w 0.034, rake ≈18° | sand | → `profile_extrude` GRIP, bevel 0.005 / 2 seg. Optional recessed stipple panel per side (0.0015 deep). No finger grooves. |
| `WARDEN_TriggerGuard` | y −0.104 … −0.012, bottom z −0.072, w 0.020 | graphite | → `profile_extrude` outer, boolean out the hole polygon (extrude cutter 0.06 wide), bevel 0.003. |
| `WARDEN_Trigger` | blade y −0.066 … −0.050, z 0 … −0.048, w 0.008; origin at pivot (0, −0.054, 0) | gunmetal | → `profile_extrude` TRIGGER. Separate object (moving part). |
| `WARDEN_Bolt` | **separate object, origin at bolt-axis rear (0, +0.112, 0.075)**. Shroud: cylinder r 0.024, y +0.080 … +0.112, rear chamfer 0.004. Handle arm 0.018 × 0.016 from root (−0.032, +0.060, 0.092) to (−0.082, +0.074, 0.048). **Knob: r 0.024 (Ø 48 mm, deliberately oversized) at (−0.092, +0.078, 0.042)**. Bolt body strip visible in the ejection port: box 0.010 × 0.135 × 0.040 at (−0.032, −0.1075, 0.083) | gunmetal | → cylinder + rotated box (`Vector.to_track_quat`) + knob as a **faceted** sphere (`bc.sphere(..., segments=8, rings=6, smooth=None)`) or a 6-sided cylinder along X with 0.004 bevel (hex knob). The knob is on **−X**; its centre sits 0.053 outside the receiver side so it breaks the top and front silhouettes. |

### 4.2 `stock_standard` (default stock) — origin = `_SOCKET_Stock` (0, +0.080, 0.075)

| Object | Size / position (gun coords) | Mat | How |
|---|---|---|---|
| `WARDEN_StockHinge` | box 0.052 × 0.034 × 0.060 at (0, +0.097, +0.015) | graphite | → box bevel 0.004. Dark block between receiver and sand stock (graphite→sand colour break like the concepts). |
| `WARDEN_Stock` | y +0.080 … +0.292, z −0.126 … +0.100, **w 0.046** | sand | → `profile_extrude` STOCK, boolean the triangular **window** through X (bevel the cutter or the result 0.005 so the window corners are rounded), bevel 0.005. Top beam stays **below z 0.048 for y < 0.122** so the bolt shroud sits over it. |
| `WARDEN_CheekRiser` | y +0.150 … +0.284, z 0.100 … 0.136, w 0.040 | sand | → `profile_extrude` CHEEK RISER, bevel 0.005 / 2 seg. **Visible 8 mm gap** to the comb (comb top 0.092). |
| `WARDEN_RiserPost` ×2 | cylinder r 0.005, z 0.090 … 0.102, at y +0.180 and +0.250 | gunmetal | → cylinder. Optional riser lock knob r 0.009 on +X at (0.024, 0.215, 0.080). |
| `WARDEN_RecoilPad` | y +0.292 … +0.320, z −0.130 … +0.104, w 0.050 | rubber | → `profile_extrude` RECOIL PAD, bevel 0.004 / 2 seg. Optional 3 horizontal grooves on each side (0.002 deep). |
| `WARDEN_Monopod` | housing box 0.034 × 0.030 × 0.022 at (0, +0.205, −0.106) graphite; column cyl r 0.010, z −0.115 … −0.180; knurled collar cyl r 0.0135 × 0.014 at z −0.140 (12 verts); spike cone r 0.010 → 0.001, z −0.180 … −0.198 | graphite + gunmetal | → boxes/cylinders (`radius2` for the cone, `rot=(180,0,0)` so the tip points down). Join into one object. |

`stock_folding` (secondary, per modular spec): same hinge block and recoil pad, but a thinner (w 0.036) open
"Z" frame without riser and without monopod. Low priority.

### 4.3 `mag_5` (default) and `mag_8` — origin = `_SOCKET_Mag` (0, −0.270, 0.000)

| Object | Size / position | Mat | How |
|---|---|---|---|
| `WARDEN_Mag5` body | y −0.276 … −0.118, z 0.000 … −0.150, w 0.052 (front face rakes forward 6 mm at the bottom) | graphite | → `profile_extrude` MAG_5, bevel 0.004. Two raised vertical ribs per side (0.003 × 0.010 × 0.080, at y −0.235 and −0.160, z centre −0.105). |
| `WARDEN_Mag5Base` | base plate 0.058 × 0.170 × 0.018, y −0.282 … −0.112, z −0.150 … −0.168 | **sand** | → box bevel 0.004 / 2 seg. Sand base = the mag reads as a separate, lootable item. |
| `round` child | one visible top cartridge (12.7 mm: case r 0.0105, ~0.138 long incl. bullet), y −0.268 … −0.130, top at z −0.002 (mostly hidden in the well) | gunmetal/brass-free (use gunmetal) | → lathe. |
| `mag_8` | same section, body bottom at z −0.200, base plate z −0.200 … −0.218, front bottom at y −0.282 | — | copy of mag_5 with longer profile. |

Visible mag below the well (z −0.068 … −0.168) must stay ≥ 0.10 tall: chunky, not a sliver.

### 4.4 `optic_sniper` (shared attachment, Warden default) — origin = `_SOCKET_Optic` (0, −0.080, 0.1375)

Total length **0.380** (eyepiece y +0.065 → sunshade y −0.315), axis **z 0.178** (0.0405 above rail top).
Objective bell outer **Ø 0.068** (stylised 50 mm objective), tube Ø 0.037, eyepiece Ø 0.050.

| Object | Size / position | Mat | How |
|---|---|---|---|
| `ATT_OpticSniper_Body` | SCOPE lathe profile | graphite | → `lathe` 32 steps, `rot=(90,0,0)`, axis z 0.178. |
| `ATT_OpticSniper_IceRing` | ICE RING lathe, r 0.032–0.0355, y −0.255 … −0.265 (10 mm wide, 1.5 mm proud of the bell) | **ice paint (not emissive)** | → lathe. |
| `ATT_OpticSniper_Sunshade` | SUNSHADE lathe, open tube r 0.030–0.033, y −0.265 … −0.315 | graphite | → lathe (hollow). |
| `ATT_OpticSniper_Lens` ×2 | objective disc r 0.030 at y −0.258 (recessed in bell); ocular disc r 0.020 at y +0.063 | lens | → thin cylinders. |
| `ATT_OpticSniper_Saddle` | box 0.044 × 0.062 × 0.044 centred (0, −0.080, 0.178), bevel 0.008 | graphite | → box. |
| `ATT_OpticSniper_TurretElev` | cylinder r 0.019, z 0.200 … 0.228, at y −0.080; 16 verts with alternate verts pushed in 1 mm (knurl), chamfered cap | graphite | → cylinder. |
| `ATT_OpticSniper_TurretWind` | same, axis X, on **−X** (x −0.022 … −0.048) | graphite | → cylinder `rot=(0,90,0)`. |
| `ATT_OpticSniper_SideFocus` | flat knob r 0.017, axis X, on **+X** (x +0.022 … +0.040) | graphite | → cylinder. NO ice ring on it. |
| `ATT_OpticSniper_Ring` ×2 | at y −0.020 and −0.140: ring cylinder r 0.027 × 0.018 (Y) around the tube + base block 0.034 × 0.024 from rail top z 0.1375 up to 0.178, clamp screw cyl r 0.006 on +X | graphite | → cylinder + box, join. |
| `ATT_OpticSniper_PowerLever` (opt.) | small fin 0.006 × 0.010 × 0.016 on the magnification ring at (−0.026, +0.005, 0.178) | graphite | → box. |
| `_SOCKET_ADS` (child) | eye point (0, +0.150, 0.178) gun coords = local (0, +0.230, +0.0405) | — | empty. |

No flip-up lens caps (they appear in the concepts; leave them out of the default).

### 4.5 `bipod` (shared attachment, Warden default) — origin = `_SOCKET_Under` (0, −0.600, 0.0205)

| Object | Size / position | Mat | How |
|---|---|---|---|
| `ATT_Bipod_Clamp` | box 0.044 × 0.050 × 0.018 at (0, −0.600, 0.0115) + throw lever 0.006 × 0.030 × 0.008 on +X | graphite / gunmetal lever | → boxes, bevel 0.004. |
| `ATT_Bipod_Hinge` | box 0.060 × 0.030 × 0.020 at (0, −0.600, −0.0075) | graphite | → box, bevel 0.004. |
| `ATT_Bipod_Leg_L` / `_R` (separate objects, **origin at hinge** (±0.024, −0.600, −0.008)) | **Deployed:** unit direction (±0.133, −0.643, −0.754) = **50° below the rail, pointing forward, 10° splay**. Upper leg 0.022 × 0.016 × 0.140 (graphite, centred 0.070 along the leg), lower telescoping leg 0.015 × 0.012 × 0.130 (gunmetal, centred 0.185 along), angular foot/claw 0.026 × 0.030 × 0.016 (rubber) at 0.250 → feet at (±0.057, −0.761, −0.197). | graphite / gunmetal / rubber | → boxes aligned with `dir.to_track_quat('Z','Y')`, bevel 0.003. Rectangular sections (angular, not round tubes). Store custom props `fold_angle_deg = -50` (rotation about local X that lays the legs forward along −Y under the handguard) and `splay_deg = 10`. |

### 4.6 Sockets (empties, zero rotation, children of `WARDEN_Root`)

| Socket | Location (x, y, z) |
|---|---|
| `WARDEN_SOCKET_Optic` | (0, −0.080, 0.1375) |
| `WARDEN_SOCKET_Stock` | (0, +0.080, 0.075) |
| `WARDEN_SOCKET_Mag` | (0, −0.270, 0.000) |
| `WARDEN_SOCKET_Under` | (0, −0.600, 0.0205) |
| `WARDEN_SOCKET_Side_R` / `_Side_L` | (+0.0455, −0.645, 0.079) / (−0.0455, −0.645, 0.079) (names per modular spec) |
| `WARDEN_SOCKET_Muzzle` | (0, −1.100, 0.075) |
| `WARDEN_SOCKET_LeftHand` | (0, −0.380, 0.030) (under the handguard, ahead of the magwell) |

### 4.7 Suggested triangle split (≈ 18k total)

Receiver + counter 1.6k · chassis 0.6k · rails 1.4k · handguard 2.0k · barrel 1.5k · brake 0.8k · grip 0.4k ·
guard + trigger 0.4k · bolt 0.8k · stock module 2.5k · mag_5 0.7k · optic 4k · bipod 1.3k.
Use 24–32 lathe steps, 16 for knobs, 1–2 bevel segments, `bc.shade_smooth(obj, 30)`.

## 5. Materials (linear RGB, `bc.material`)

| Material | Token | Base colour | Rough | Metal | Used on |
|---|---|---|---|---|---|
| `M_Warden_Graphite` | graphite | (0.030, 0.033, 0.040) | 0.55 | 0.15 | receiver, chassis, rails, handguard, trigger guard, stock hinge, monopod housing, mag body, scope body/rings/turrets/sunshade, bipod clamp/upper legs |
| `M_Warden_Gunmetal` | gunmetal | (0.11, 0.115, 0.12) | 0.35 | 0.85 | barrel, brake, bolt (shroud, handle, knob, bolt body), trigger, riser posts, monopod column/spike, bipod lower legs |
| `M_Warden_Sand` | sand | (0.36, 0.28, 0.18) | 0.70 | 0.0 | pistol grip, stock, cheek riser, mag base plate |
| `M_Warden_Rubber` | charcoal-cloth | (0.035, 0.037, 0.045) | 0.90 | 0.0 | recoil pad, bipod feet, eyepiece eyecup (optional) |
| `M_Warden_CounterGlow` | ice (emissive) | (0.45, 0.85, 1.0) | 0.40 | 0.0 | **ammo counter screen only** — emission (0.45, 0.85, 1.0), strength ≈ 1.0–2.0. Check the render: it must read light ice-blue, not white (AgX washes it out above ~2). |
| `M_Warden_IcePaint` | ice (no emission) | (0.45, 0.85, 1.0) | 0.40 | 0.0 | scope objective ring only |
| `M_Warden_Lens` | (special, not in palette) | (0.010, 0.030, 0.080) | 0.05 | 0.0 | scope lenses, `coat=1.0` — dark blue tint |

Optional wear: `art/textures/worn_paint.png` as a subtle multiply on graphite and sand (`tex_mix` 0.25–0.4,
`tex_scale` 2–4). Flat colour must carry the look. **One emissive zone only** (the counter) — style-guide rule for
base guns. The ice scope ring is paint.

Colour blocking rule: everything forward of the grip is dark (graphite/gunmetal) except the mag base plate; the
sand mass is grip + stock + riser. The graphite stock hinge block makes a clean dark→sand break at y ≈ +0.11.

## 6. Silhouette hooks and the 5 things that MUST read

Silhouette hooks: see-through brake ports · fluted barrel step-down · slotted handguard · forward A-frame bipod ·
chin under the receiver · chunky mag with sand foot · triangle window in the stock · riser floating on posts ·
monopod spike · scope bell + sunshade + ice ring · bolt knob sticking out sideways (top/front views).

**Must read correctly (check against `profile_sketch.png` and at 64 px):**
1. **Length and the hammer-head muzzle** — 1.42 m long, low and horizontal; the brake is clearly wider and taller
   than the barrel (0.070 × 0.062 vs Ø 0.046) with daylight through two big ports.
2. **Big scope on top** — 0.38 m long, bell clearly bigger than the tube, sunshade, thin ice ring at the front;
   sits over the receiver, eyepiece just ahead of the stock joint.
3. **Deployed forward bipod** — two angular legs splayed and angled 50° forward/down from the handguard front,
   feet at y ≈ −0.76, level with the monopod tip (the rifle rests level).
4. **Sand skeleton stock** — triangular window, cheek riser with a visible gap, thick black pad, monopod spike;
   the sand grip + stock against a dark gun is the colour read.
5. **Bolt-action identity** — oversized gunmetal bolt knob on the shooter's RIGHT (−X), ejection port on −X,
   chunky 5-round box mag ahead of the trigger guard, small ice counter on the left (+X). No other glow.

## 7. Concept images — what to trust

| Image | Verdict | Trust it for |
|---|---|---|
| **v02 → `concept_main.png`** | best side view | colour blocking, painted style, handguard slot rhythm, chin under the receiver, counter placement on the left side, ice ring at the objective, mag size, overall proportions |
| **v04 → `concept_34.png`** | best 3/4 | brake volume and see-through ports, handguard section, scope bell + blue lens, angular bipod legs, stock depth |
| v03 | good alt side | sloped receiver chin, bolt knob size (but its knob is drawn tan: build it gunmetal), rail teeth, skeleton stock shape |
| v01 | usable side | sand riser on posts + small monopod spike under the stock; overall length ratios match this brief almost exactly. Its round brake ports are wrong. |
| v06 | partial (rear-right 3/4) | the **bolt side**: big round knob on a short angled arm, sand riser on posts, grip rake, recoil pad thickness. Ignore: counter drawn on this side, ice ring on the eyepiece end, 4-port brake. |
| v07 | partial (side) | sand cheek riser on two posts, overall stock read. Ignore: all-sand magazine (only the base plate is sand), vertical bipod. |
| v08 | partial (3/4) | 3-port brake mass, handguard/rail chunkiness. Ignore: all-sand magazine, tan bolt knob, lens caps. |
| v05 | rejected | round cylindrical brake, ice rings everywhere, brownish graphite, no monopod |

`proxy_*.png` / `profile_sketch.png` beat every painted image on **proportions and part placement**; the paintings
are for **style, colour and surface detail**.

**Where ALL concepts deviate from this brief (brief wins):**
- **Bolt handle side:** the images draw the bolt on the visible (left, +X) side. Build it on **−X** (shooter's
  right). In the left-side view only the shroud and maybe the top of the knob show.
- **Cheek riser** is drawn graphite/black in v02–v05 → build it **sand** (v01 is right).
- **Bipod** is drawn near-vertical → build it **50° forward** per 4.5.
- **Monopod spike** is missing or tiny → build per 4.2 (0.09 m drop).
- **Brake** is drawn smaller / with round ports in some images → build the 0.070 × 0.150 × 0.062 block with
  rectangular ports.
- **Flip-up lens caps** → omit.
- **Extra ice accents** (ring around the side-focus knob, chevrons, eyepiece ring) → omit. Ice = counter (emissive)
  + objective ring (paint) only.
- **Barrel** is sometimes painted chrome → gunmetal, rough 0.35.
- **Grip** finger grooves/screws and stock screw dots → skip or keep as tiny optional bevelled bumps.
- **Scope size/position**: concepts draw it larger and further forward — use section 4.4 numbers (eye relief).

## 8. Build notes / pitfalls

- Do booleans (ports, slots, windows, ejection port) **before** adding bevel modifiers, EXACT solver, then bevel.
  Bevel the brake with `limit="ANGLE"` so the port edges also get a small chamfer.
- Keep every part ≥ 0.010 thick (style guide: no noodly parts). Thinnest allowed: trigger 0.008, riser posts
  Ø 0.010, sunshade wall 0.003 (it is a tube, reads as a ring).
- Separate moving parts with origins at their pivots: trigger (0, −0.054, 0), bolt (0, +0.112, 0.075), bipod legs
  at their hinges.
- After building, render `right`, `left`, `three_quarter` and `top` and compare to `proxy_*.png` /
  `profile_sketch.png`; check the 64 px black-silhouette read (brake, scope, bipod, stock window must survive).
- `bc.uv_all()` before export; run `bc.stats()` and log the tri count in NOTES.md.
