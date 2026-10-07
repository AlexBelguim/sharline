# AR-7 "MAKO" — build brief (authoritative modeler spec)

Prefix `MAKO`. Folder for the build: `assets/weapons/ar7_mako/` (see `art/WEAPON_MODULAR_SPEC.md`).
Read with: `art/STYLE_GUIDE.md` (palette, axes, budgets) and `art/WEAPON_MODULAR_SPEC.md` (sockets, part split).
**Numbers in this brief win over the concept images.** All coordinates in metres, Blender axes.

Files in this folder:
- `concept_main.png`: main side view (gun's left side, muzzle left). Use it for mood, colour split and detail language.
- `concept_34.png`: three-quarter view. Use it for volumes only (see section 7 for its errors).
- `profile_sketch.png`: **the side profile drawn from the numbers below**, with sockets. Trust this one for proportions.
- `profile_overlay.png`: this brief's profile outline (pink) over concept v04, showing where the art drifts.
- `profile_sketch.py`: the data behind the sketch. You may import or copy its point lists directly. It imports
  without matplotlib, so `sys.path.insert(0, r"F:/git/val etf/art/concepts/mako"); import profile_sketch as P` works inside Blender.
- `blockout/mako_blockout_sheet.png` + `blockout_check.py`: a 10-minute grey-box extruded straight from these
  numbers (5.8k tris, no detail). It shows the proportions read as an AR in 3D. **This is not the asset.**
  Don't copy its shortcuts: its handguard octagon is approximate, its rails have no dovetail, and it has no bevels.
- `v01…v09.png`: all generations. Section 7 lists which ones to keep and which to throw away.

---

## 1. Identity and silhouette

The MAKO is a modernised M4/AR-15. A player has to read it as "an M4" at a glance, with nothing sci-fi
about the base shape. The upper and lower are graphite and the handguard is a long, slim graphite octagon
with one unbroken Picatinny rail across the top, from the compensator to the charging handle. All the furniture
is pale **bone** polymer: the forward-curving 30-round magazine, the pistol grip, and the angular 6-position stock
with a dark butt pad. The near-future touches are restrained. The panels are monolithic and every edge is
chamfered. A small angular two-port compensator sits at the muzzle, a sleek box holo sight sits on the
receiver, and a small **ice-blue LCD ammo counter** is set into the rear of the upper on the gun's left side.
That counter is the gun's single glowing accent.

Silhouette, read left to right (muzzle −Y on the left):
1. A small boxy comp and a short stub of barrel.
2. A long flat-topped bar made of handguard + receiver, one height from end to end with the rail on top.
3. The sight "hump" over the receiver.
4. The grip, raked back about 22°.
5. The magazine in front of the trigger guard, curving forward.
6. The thin buffer tube.
7. A wedge-shaped stock whose bottom edge drops at 45° to a tall butt.

Overall length is **0.843 m** with the stock extended, from comp face Y −0.565 to butt Y +0.278.
Height from rail top to magazine floorplate is **0.253 m** (the "~0.26 m incl. magazine" figure). The default
holo optic raises that to **0.307 m**.

## 2. Axes, handedness, origin

- Muzzle toward **−Y**, bore along Y at **Z = 0.050**, Z up, centred on X = 0 (symmetric unless noted).
- **Origin (0,0,0) = pistol-grip hand position**: the top centre of the grip where it meets the lower.
  The web of the hand sits there.
- **Handedness, stated once.** With the gun facing −Y, the gun's own **LEFT side is +X** and its **RIGHT side
  is −X**. That is the same rule as Blender's `.L = +X` for characters.
  - **Left (+X)** carries the ammo counter, bolt catch and fire selector. A right-handed player sees this
    side in first person. It is also what the side-view concepts show, and what `bc.render_views` "right"
    renders, since its camera sits at +X.
  - **Right (−X)** carries the ejection port with dust cover, the brass deflector, the forward assist and the
    mag release button.
  - `WEAPON_MODULAR_SPEC.md` calls the +X side rail socket `_Side_R`. Keep that socket naming as the spec
    says. It is only a label and has nothing to do with where the parts above go.
- Key heights:

  | Height | Z |
  |---|---|
  | bore | 0.050 |
  | upper/lower parting line | 0.024 |
  | rail base (top of upper and handguard bodies) | 0.0745 |
  | rail top | 0.084 |
  | sight line | 0.116 |
  | optic top | 0.138 |
  | grip bottom | −0.111 |
  | magwell lip | −0.038 |
  | mag floorplate, rear corner | −0.169 |
  | stock toe | −0.056 |

## 3. Side-profile coordinate sketch (y, z) — the silhouette contract

Copy these lists straight into `bc.profile_extrude(points=…)`. That helper takes (y, z) points and extrudes
along X. The same lists are in `profile_sketch.py`.

```
UPPER       (-0.168,0.024) (-0.168,0.068) (-0.162,0.0745) (0.022,0.0745) (0.030,0.066) (0.030,0.046)
            (0.014,0.046) (0.008,0.024)                                                                     width 0.032
HANDGUARD   (-0.168,0.026) (-0.490,0.026) (-0.500,0.036) (-0.500,0.0745) (-0.168,0.0745)               octagon 0.044 x 0.0485 (see part list)
TOP RAIL    y -0.498 .. +0.022, z 0.0745 .. 0.084 (continuous over handguard + upper)
LOWER       (-0.160,0.024) (-0.162,-0.026) (-0.168,-0.032) (-0.168,-0.038) (-0.080,-0.038) (-0.078,-0.030)
            (-0.080,-0.006) (-0.072,0.000) (0.018,0.000) (0.030,0.008) (0.036,0.020) (0.036,0.046)
            (0.014,0.046) (0.008,0.024)                                                                     width 0.030 (magwell 0.034)
            (front sits 0.008 behind the upper's front = the AR step; rear rises into the buffer tower that
             holds the tube, and the upper's rear-bottom corner is notched to sit on it)
TRIG GUARD  outer (-0.082,0.000) (-0.082,-0.030) (-0.074,-0.037) (-0.022,-0.037) (-0.012,-0.026) (-0.012,0.000)
            hole  (-0.074,0.001) (-0.074,-0.029) (-0.024,-0.029) (-0.018,-0.022) (-0.018,0.001)           width 0.014
TRIGGER     (-0.036,0.004) (-0.044,0.004) (-0.047,-0.010) (-0.050,-0.022) (-0.045,-0.024) (-0.042,-0.012) (-0.038,-0.002)  width 0.007
GRIP        (-0.020,0.002) (0.022,0.002) (0.030,0.008) (0.035,0.000) (0.044,-0.030) (0.054,-0.062) (0.066,-0.100)
            (0.064,-0.108) (0.026,-0.111) (0.021,-0.104) (0.008,-0.064) (-0.004,-0.034) (-0.020,-0.006)   width 0.030
MAG_30      (-0.152,0.012) (-0.152,-0.020) (-0.1532,-0.0494) (-0.1567,-0.0786) (-0.1626,-0.1075) (-0.1707,-0.1358)
            (-0.1745,-0.1345) (-0.1783,-0.1459) (-0.1099,-0.1686) (-0.1061,-0.1572) (-0.1099,-0.1559)
            (-0.1004,-0.1227) (-0.0935,-0.0888) (-0.0894,-0.0545) (-0.088,-0.020) (-0.088,0.012)            width 0.025
            (straight to z -0.020, then arc about centre (-0.520,-0.020), R 0.368 front / 0.432 rear, 18 deg sweep;
             the 4 points (-0.1745..-0.1061) are the floorplate, which overhangs 0.004 and is 0.012 thick)
BUFFER TUBE r 0.016 on the bore, y 0.030 .. 0.215 ; castle-nut ring r 0.0195, y 0.036 .. 0.046
STOCK       (0.098,0.034) (0.098,0.064) (0.110,0.074) (0.136,0.078) (0.262,0.078) (0.262,-0.056) (0.240,-0.056)
            (0.164,0.020) (0.150,0.025) (0.106,0.026)                                                        width 0.028 / 0.040 (see part list)
STOCK PANEL  triangle (0.198,0.014) (0.246,0.014) (0.246,-0.034), corners rounded r 0.004, RECESSED 0.003 each side
             (NOT a through-hole; the standard stock is a solid wedge, the skeleton look is reserved for stock_light)
BUTT PAD    (0.262,0.082) (0.270,0.082) (0.277,0.072) (0.278,-0.046) (0.274,-0.058) (0.262,-0.060)           width 0.042
BARREL      r 0.0095 on the bore, y -0.519 .. -0.160 (visible only -0.519 .. -0.500)
COMP        y -0.565 .. -0.517, octagon 0.026 x 0.026 (chamfer 0.006), front/rear chamfer 0.004
OPTIC (world, default position) clamp y -0.125 .. -0.049 on rail top; body top z 0.138; window z 0.104 .. 0.128
```

What these numbers are meant to produce:
- The handguard and upper are **the same height**, so the handguard + receiver read as one straight bar.
- The upper's front overhangs the lower by 0.008 at the parting line, and the lower rises into a buffer tower
  behind the grip. Both are small, but without them the receiver reads as a brick (checked in the blockout).
- The grip front leans back **≈ 22°** from vertical.
- The magazine leans forward **≈ 18°** at the floorplate, and the rear corner of the floorplate is the lowest point.
- The stock's top line sits **0.012 above the tube top**. That is the cheek riser.

## 4. Part list

The split follows `WEAPON_MODULAR_SPEC.md`:
- **Base gun:** `MAKO_Root` plus the parts below.
- **`stock_standard`:** the default stock.
- **`mag_30`:** the default magazine.
- **`ATT optic_holo`:** a shared attachment.

Each swappable part's own origin is its mount point.

"PE" below means `bc.profile_extrude` of the listed profile. "Bevel" means `bc.add_bevel` (1–2 segments,
plus `shade_smooth`). Chamfer every hard edge: use 0.002–0.004 on receivers and 0.003–0.005 on polymer.
Nothing in the gun is a raw sharp box.

### 4a. Base gun (collection `MAKO_Base`, all parented to `MAKO_Root` at the origin)

| Object | Size (m) | Position / extent | Material | How to build |
|---|---|---|---|---|
| `MAKO_Upper` | 0.198 L × 0.032 W × 0.0505 H | y −0.168…+0.030, z 0.024…0.0745 | Graphite | PE of UPPER, width 0.032, bevel 0.003. The rear-bottom notch (y 0.008…0.030, z 0.024…0.046) seats on the lower's buffer tower. Chamfer the top long edges 0.005 down to the 0.024 rail-base width. **Right (−X):** ejection-port recess (boolean box y −0.092…−0.028, z 0.042…0.064, 0.004 deep) and a brass-deflector wedge (PE (−0.024,0.054)(−0.006,0.054)(−0.006,0.0725)(−0.016,0.0725), x −0.016…−0.024, joined). **Left (+X):** one 0.001 panel-line groove framing y −0.160…−0.030, z 0.030…0.068 (optional). Charging-handle slot: notch y +0.014…+0.030, z 0.062…0.0745, x ±0.008. |
| `MAKO_Lower` | 0.204 L × 0.030 W | y −0.168…+0.036, z −0.038…0.046 | Graphite | PE of LOWER, width 0.030. Magwell block y −0.164…−0.080, z −0.038…0.024, width 0.034, flaring to 0.038 over the last 0.006 at the lip (a box with a bevel, or a scaled-out lip loop). **Boolean the mag cavity:** box x ±0.0135, y −0.154…−0.086, z −0.045…0.016, so the mag can come out in reload animations and the opening reads dark. Join the trigger guard in. Add a raised fence ring (r 0.008, 0.0015 proud) around the mag release on −X. Add three 0.0015-deep horizontal grooves on the front of the magwell (optional). |
| (in Lower) trigger guard | width 0.014 | TRIG GUARD outer/hole above | Graphite | PE of the outer profile, then boolean out the hole prism (or build one bmesh face with a hole). Fully closed loop. |
| `MAKO_Trigger` | 0.007 W | blade y −0.036…−0.050, z +0.004…−0.024 | Gunmetal | PE of TRIGGER. Separate object. **Origin at pivot (0, −0.040, 0.012).** |
| `MAKO_Grip` | 0.086 deep × 0.030 W × 0.119 H | GRIP profile | Bone | PE of GRIP, width 0.030, bevel 0.004 with 3 segments (soft polymer). Inset stipple panel on both sides, 0.0015 deep, 0.006 in from the edges, z −0.020…−0.095. The top hides 0.002 inside the lower. |
| `MAKO_Handguard` | 0.332 L, 0.044 W × 0.0485 H | y −0.500…−0.168, z 0.026…0.0745, centred on X | Graphite | **Hollow octagon tube.** The XZ section is (±0.012,0.0745)(±0.022,0.0645)(±0.022,0.0355)(±0.012,0.026) with a 0.003 wall: inner box boolean, or a lathe with `steps=8` scaled. Front end: bottom-front chamfer cut from (−0.490,0.026) to (−0.500,0.036), with a 0.002 bevel on the front rim. **M-LOK slots**, booleaned as ONE joined cutter, at y centres −0.200, −0.245, −0.290, −0.335, −0.380. *Side slots:* 0.032 (Y) × 0.007 (Z) at z 0.050, one through-X box per station so both sides are cut. *Diagonal slots:* 0.024 × 0.005 on the four 45° faces, made by two through-boxes per station rotated ±48.6° about Y through the bore axis. *Bottom slots:* 2 slots, 0.032 × 0.007, at y −0.200 and −0.245 (cut z 0.020…0.032 only). |
| `MAKO_Rail` (top) | 0.520 L | y −0.498…+0.022, base z 0.0745, top 0.084 | Graphite | Extrude this XZ profile along Y: (±0.0075,0.0745)(±0.0105,0.0775)(±0.0105,0.0825)(±0.009,0.084), a stylised dovetail. Overall width 0.021 and height 0.0095, per the modular spec. **Cross slots every 0.010:** 52 slots, 0.005 wide (Y), cut 0.003 deep from the top. Make one cutter, give it an Array modifier (count 52, constant offset 0.010), apply it, then run one boolean. Chamfer both rail ends 0.003. |
| `MAKO_RailBottom` | 0.140 L | y −0.430…−0.290, base z 0.026, outer face z 0.0165 | Graphite | The same rail profile flipped to −Z, 14 slots. Holds `_SOCKET_Under`. |
| `MAKO_RailSide_L` / `MAKO_RailSide_R` | 0.060 L | y −0.470…−0.410, centred z 0.050, base on x ±0.022, outer face x ±0.0315 | Graphite | The same rail profile turned ±90° about Y, 6 slots. |
| `MAKO_Barrel` | r 0.0095 | y −0.519…−0.160 on the bore | Gunmetal | Cylinder with 24 verts along Y. Only 0.019 of it shows. |
| `MAKO_Comp` | 0.048 L × 0.026 × 0.026 | y −0.565…−0.517 on the bore | Gunmetal | Octagonal prism: box with a 0.006 chamfer on its long edges, 0.004 chamfer on the front and rear rims, rear end tapering to r 0.011. **Two side ports per side:** through-X box cuts at y −0.556…−0.547 and −0.540…−0.531, z 0.0435…0.0565. Front face gets a bore hole, r 0.0045 and 0.010 deep, in Dark. Optional: a 0.002 V-notch across the front top. |
| `MAKO_BufferTube` | r 0.016 | y 0.030…0.215 on the bore | Graphite | 24-vert cylinder with the rear rim chamfered. `MAKO_CastleNut` (Gunmetal): ring r 0.0195, y 0.036…0.046, right behind the buffer tower, 6 shallow notches (optional). |
| `MAKO_ChargingHandle` | wings 0.048 W | y +0.014…+0.042, z 0.062…0.0735 | Graphite | Shaft box 0.012 W runs from y −0.020 (hidden) to 0.040. The T-wings sit at y 0.030…0.042, span x ±0.024 and are 0.010 thick. Seen from above they are swept wedges: rear edge straight, front edge angled 30°, tips chamfered. Separate object. **Origin (0, 0.030, 0.068)**; it animates +Y by 0.06. |
| `MAKO_ForwardAssist` | 0.010 × 0.034 × 0.016 | right side (−X): centre (−0.019, 0.013, 0.058), y −0.004…+0.030 | Graphite + Gunmetal cap | Box, bevel 0.003 (stylised housing). Plunger cap: cylinder r 0.0065 along Y, y 0.030…0.038, at x −0.019, z 0.058, with 3 shallow grooves on its end face. |
| `MAKO_DustCover` | 0.068 × 0.025 × 0.002 | right side, x −0.016…−0.018, y −0.094…−0.026, z 0.041…0.066 | Graphite | Thin plate with a 0.0015 raised stiffener rib at z 0.056 and a small latch bump at the rear top. Hinge rod: cylinder r 0.0018 along Y at (x −0.0175, z 0.041). Separate object. **Origin on the hinge axis (−0.0175, −0.060, 0.041).** |
| `MAKO_BoltCatch` | 0.012 × 0.016 × 0.004 | left (+X): y −0.084…−0.072, z 0.006…0.022, x 0.015…0.019 | Graphite | Chamfered paddle. Separate object (moving part). |
| `MAKO_MagRelease` | r 0.005 | right (−X): (−0.016, −0.074, 0.010), 0.003 proud | Gunmetal | Short cylinder inside the fence. Separate object. |
| `MAKO_Selector` | hub r 0.0055 + lever 0.016 | left (+X): hub at (0.016, −0.006, 0.013); lever points −Y (forward = SAFE) | Gunmetal | Hub cylinder plus a chamfered lever, 0.004 × 0.003. |
| `MAKO_Pins` | r 0.0032 | front pivot (y −0.154, z 0.016), rear takedown in the tower (y 0.024, z 0.034); heads 0.001 proud on both sides | Gunmetal | Cylinders along X, joined. |
| `MAKO_AmmoCounter` (bezel) | 0.036 × 0.024, 0.0025 proud | left (+X): y −0.030…+0.006, z 0.040…0.064, x 0.016…0.0185 | Graphite | Box with a 0.0015 bevel and its top-rear edge chamfered more (0.004). Joining it to the upper is fine. |
| `MAKO_AmmoScreen` | 0.028 × 0.016 | inset in the bezel: y −0.026…+0.002, z 0.044…0.060, face at x 0.0183 | **Ice (emissive)** | Flat panel, a separate object so the emissive stays isolated. Draw the digits "**30**" as **dark 7-segment bars** (Dark material, 0.0003 proud): digit height 0.012 (z 0.046…0.058), width 0.0065, stroke 0.0015. The "3" spans y −0.020…−0.0135 and the "0" spans y −0.0105…−0.004, so they read left to right from +X. Glow area is about 4.5 cm². |
| `MAKO_RearSight` (optional) | 0.022 W × 0.016 L × 0.008 H | folded on the rail: y +0.004…+0.020, z 0.084…0.092 | Graphite | Low clamp box plus a flat leaf (0.003 thick) folded forward, with an aperture ring outline. |

Sockets go on `MAKO_Root` as empties with zero rotation. Also write them to `sockets.json`.

| Socket | Location (x, y, z) |
|---|---|
| `MAKO_SOCKET_Optic` | (0, −0.085, 0.084): clamp centre on the rail top |
| `MAKO_SOCKET_Stock` | (0, 0.215, 0.050): buffer-tube end on the bore |
| `MAKO_SOCKET_Mag` | (0, −0.152, 0.012): top-front corner of a seated magazine |
| `MAKO_SOCKET_Under` | (0, −0.360, 0.0165): bottom rail face |
| `MAKO_SOCKET_Side_R` | (+0.0315, −0.440, 0.050) |
| `MAKO_SOCKET_Side_L` | (−0.0315, −0.440, 0.050) |
| `MAKO_SOCKET_Shield` | (0, −0.480, 0.084) |
| `MAKO_SOCKET_Muzzle` | (0, −0.565, 0.050) |
| `MAKO_SOCKET_LeftHand` | (0, −0.330, 0.020) |

### 4b. `stock_standard` (default; part origin = `_SOCKET_Stock` (0, 0.215, 0.050))

| Object | Size | Extent (world, mounted) | Material | How to build |
|---|---|---|---|---|
| `MAKO_Stock` | 0.164 L × 0.134 H | STOCK profile, y 0.098…0.262, z −0.056…0.078 | Bone | Make two PEs and join them. (1) The full STOCK profile at width 0.028: leg and rear post. (2) The housing band y 0.098…0.262, z 0.026…0.078 at width 0.040: tube housing and cheek riser. Round the top of the cheek riser with a 0.006 chamfer. **Side panel:** recess the STOCK PANEL triangle 0.003 deep on both faces (boolean thin prisms; do NOT cut through). **Tube channel:** boolean a cylinder r 0.0165, y 0.098…0.222, so the tube visibly enters the front face. Inset a 0.002 panel on the housing sides. Bevel 0.003. |
| `MAKO_ButtPad` | 0.016 L × 0.142 H × 0.042 W | BUTT PAD profile, y 0.262…0.278 | Rubber | PE plus a 0.004 bevel. Three 0.002 horizontal grooves on the rear face at z 0.040, 0.010 and −0.020. |
| `MAKO_StockLever` | 0.010 × 0.026 × 0.007 | under the housing front, centre (0, 0.116, 0.022) | Graphite | Chamfered box. |

The stock is delivered fully extended. Note for the engine: 6 positions, 0.0165 apart, total travel 0.083 toward −Y.

### 4c. `mag_30` (default; part origin = `_SOCKET_Mag` (0, −0.152, 0.012))

| Object | Size | Extent (world, seated) | Material | How to build |
|---|---|---|---|---|
| `MAKO_Mag30` | 0.064 deep × 0.025 W, 0.181 tall | MAG_30 profile | Bone | PE of MAG_30, width 0.025. The floorplate is wider: 0.029, from a second PE of the 4 floorplate points, joined. Bevel 0.002. **Round-count window on both sides:** a slot y −0.104…−0.096, z −0.046…−0.080 (it follows the rear edge, keep it 0.006 wide). Recess it 0.0015 and fill with Dark. Two raised ribs (0.0015 proud, 0.003 wide) follow the curve on each side at about 1/3 and 2/3 of the depth, from z −0.045 down to the floorplate. Feed lips on top step in to 0.020 W. The top 0.050 is hidden inside the magwell; still model it, because reloads show it. |
| `MAKO_Mag30_Round` (child) | case r 0.0048, 0.057 L | lying on the follower: y −0.148…−0.091, z 0.017 | Brass + Gunmetal tip | Lathe of case + ogive along Y, tip pointing −Y. |

### 4d. `ATT optic_holo` (attachments folder; part origin = clamp contact centre on rail top)

Coordinates below are **local**: y relative to the socket, z above the rail top. The mounted world position is
the socket plus local.

| Object | Size | Local extent | Material | How to build |
|---|---|---|---|---|
| `ATT_OpticHolo` body | 0.076 L × 0.036 W × 0.054 H | profile (−0.040,0)(0.036,0)(0.036,0.016)(0.032,0.052)(0.000,0.054)(−0.032,0.046)(−0.040,0.022) | Graphite | PE, width 0.036, bevel 0.003. **Window:** a through-Y cut, x ±0.013, z 0.020…0.044, corners chamfered 0.004. It leaves a hood frame about 0.005 thick at the sides and about 0.010 thick on top. The top-front edge forms a small brow (0.004 overhang). |
| clamp | 0.026 W | y −0.038…+0.034, z −0.0095…0 | Graphite | Jaws hug the rail flanks. Boolean the rail profile out of a box. Throw lever on −X: 0.004 × 0.020 × 0.008 at (−0.015, +0.010, −0.004). |
| `ATT_OpticHolo_Glass` | 0.026 × 0.024 | plane at y −0.030, z 0.032, tilted 8° (top toward +Y) | HoloGlass | Single plane, or a thin box. |
| `ATT_OpticHolo_Reticle` | r 0.0018 disc + r 0.0025 ring | (0, −0.0295, 0.032), facing +Y | Ice (emissive) | 12-vert disc plus a thin ring. Tiny. |
| buttons | 0.006 × 0.004 | left (+X) face at y −0.012 and +0.004, z 0.008 | Gunmetal | Two small boxes. |
| `ATT_OpticHolo_SOCKET_ADS` | — | (0, +0.036, 0.032), on the sight axis at the rear window plane | — | Empty. |

Sight line = world z 0.116, which is 0.066 above the bore.

### Budget (evaluated tris)

| Group | Tris |
|---|---|
| Base gun | ~13–15k (rails and slots ~4k, upper + lower ~4k) |
| Stock | ~1.5k |
| Mag | ~1k |
| Default loadout total | **~16–18k** (target 10–22k, hard max 30k) |
| Optic | 2–3k |

Keep cylinders at 16–24 verts and bevels at 1–2 segments. Do not subdivide.

## 5. Materials

All materials are made with `bc.material`. The values below are linear RGB.

| Material | Palette token | Base colour | Rough | Metal | Extra | Used on |
|---|---|---|---|---|---|---|
| `M_MAKO_Graphite` | graphite | (0.030, 0.033, 0.040) | 0.50 | 0.25 | tex `art/textures/worn_paint.png`, tex_mix 0.30, tex_scale 3 | upper, lower, handguard, rails, tube, charging handle, FA housing, dust cover, bezel, bolt catch, stock lever, optic body + clamp |
| `M_MAKO_Gunmetal` | gunmetal | (0.11, 0.115, 0.12) | 0.35 | 0.85 | — | barrel, comp, trigger, pins, castle nut, FA cap, selector, mag release, optic buttons, round tip |
| `M_MAKO_Bone` | bone | (0.55, 0.52, 0.46) | 0.60 | 0.0 | worn_paint, tex_mix 0.25 | stock, grip, magazine |
| `M_MAKO_Rubber` | graphite | (0.030, 0.033, 0.040) | 0.85 | 0.0 | — | butt pad |
| `M_MAKO_Dark` | charcoal-cloth | (0.035, 0.037, 0.045) | 0.70 | 0.0 | — | LCD digit bars, mag window, bore hole, inside of ports |
| `M_MAKO_Ice` | **ice** | (0.45, 0.85, 1.0) | 0.30 | 0.0 | emission (0.45, 0.85, 1.0), strength 4 | **ammo screen only** |
| `M_MAKO_Brass` | sand | (0.36, 0.28, 0.18) | 0.35 | 0.85 | — | top round case (hidden when seated) |
| `M_ATT_HoloGlass` | ice | (0.45, 0.85, 1.0) | 0.05 | 0.0 | alpha 0.20 | optic glass |
| `M_ATT_Ice` | ice | (0.45, 0.85, 1.0) | 0.30 | 0.0 | emission strength 5 | reticle (attachment) |

**The single emissive accent zone is the ammo counter** on the left rear of the upper, about 4.5 cm². No
other glow goes on the base gun: no glowing lines, no lit rail, no lit magazine. The reticle belongs to the
optic attachment and is a dot a few millimetres across.

Colour split, by area:

| Colour | Share | Parts |
|---|---|---|
| Graphite | ~65% | everything metal |
| Bone | ~30% | stock, grip, mag (the three hand and furniture parts) |
| Gunmetal | small | small hardware and the muzzle end |

Keep the comp gunmetal so the muzzle catches a highlight.

## 6. Silhouette hooks and the 5 things that MUST read

**Hooks:**
- one straight, flat top line, rail top at z 0.084, from y −0.498 to +0.022
- the sight hump sitting over the magwell / front of the receiver
- the curved bone magazine against the graphite body
- the 22° grip
- the thin tube gap between receiver and stock (0.068 of tube visible)
- the 45° stock leg (solid wedge, triangular recessed panel)
- the blocky comp beyond a short barrel stub

**MUST read correctly:**
1. **"It's an M4."** Flat-top upper with the T-charging handle at the rear, AR lower with the flared magwell,
   enclosed trigger guard, raked grip, and buffer tube into a collapsible stock. Keep every AR proportion in
   section 3. Do not invent new receiver shapes.
2. **Curved bone STANAG magazine** in front of the trigger guard, visibly curving forward to a tilted floorplate.
3. **Long, slim, slotted free-float handguard**, flush with the receiver height, with one continuous top rail.
   **There is no front sight post or A-frame gas block**, even though several images draw one.
4. **Two-tone read:** graphite metal against bone furniture (stock, grip, mag). The optic is graphite too, never bone or olive.
5. **One small ice ammo counter** on the gun's LEFT (+X) rear upper above the grip, reading "30", plus the
   tiny ice reticle in the holo sight. Nothing else glows.

Things to avoid: noodly thin parts (keep the barrel at r ≥ 0.0095 and levers at ≥ 0.003 thick), exposed long
barrel, carry handle, bayonet lug, sci-fi fins or energy coils, realistic grime.

## 7. Concept images — what to trust

Every image was made with Krea2 Turbo, so the details are approximate. **This brief and `profile_sketch.png`
win on every conflict.**

| Image | Status | Trust it for | Ignore or override |
|---|---|---|---|
| **`concept_main.png` (= v04)** | **MAIN** | Overall mood and painted, chamfered style. The graphite/bone split. The long slotted handguard flush with the receiver. The continuous top rail. A glowing "30" counter as the idea for the accent. The bone mag with a dark window. Stock and grip volumes. Its overall length and receiver proportions match this brief well (see `profile_overlay.png`). | **Optic is olive/grey:** it must be graphite. **Ammo counter sits on the lower above the trigger:** it goes on the UPPER rear (section 4a). **Handguard is too short (~0.30) and too much barrel shows (~0.07):** use 0.332 and a 0.017 stub. **Mag is nearly straight and short:** use the 18° curve. **Comp is a birdcage:** use the angular 2-port comp. **Grip has an A2 finger groove:** use a clean modern front. **Stock is stepped and has a slot:** use the solid wedge with a recessed panel. The bent trigger guard is replaced by an integral angular one. |
| **`concept_34.png` (= v08)** | **MAIN 3/4** | 3D volumes: octagonal handguard section and its front end, rail-on-handguard, receiver / magwell / grip thickness, the box-holo hood shape, chamfer language. It is the only 3/4 view **without a front sight post**. | **Optic is bone:** use graphite. **"30" counter sits on the handguard:** move it to the upper rear. **Stock is an open skeleton:** that look belongs to the `stock_light` variant only. Mag window too big and mag too straight. Birdcage muzzle. |
| v02 | keep (alt side) | Same structure as v04: long handguard, flush rail line, glowing counter. Use as a second opinion on side-view proportions. | Furniture is **tan/sand**: use bone. Counter on the lower: wrong. Tall rubber butt. |
| v06 | keep (right side) | The **only right-side (−X) view.** Shows the ejection port with dust cover, forward assist behind it, brass-deflector bump, T-charging handle, and the right side of the magwell. Also the stock and grip volumes from behind. | **Has a front sight post and a short handguard:** wrong. Brownish metal. |
| v09 | keep (alt 3/4) | Same as v08, with the floorplate and front end slightly more visible. | Same errors as v08. |
| v01 | discard | — | Front sight post, short quad-rail handguard, straight mag, no accent glow. Too realistic and plain. |
| v03 | discard | Colour only: the bone tone is about right. | Front sight post, short handguard, long barrel, bone optic. |
| v05 | discard | — | Front sight post, counter drawn on the optic, short handguard, tan furniture. |
| v07 | discard | — | Front sight post, short handguard, no visible counter. |

Recurring model error: Krea keeps drawing an M4 **A-frame front sight post** and a short handguard. The
MAKO has **neither**.

## 8. Acceptance checks for the modeler

**Bounds**, from `bc.stats()` with the default loadout (base + stock_standard + mag_30, optic excluded):

| Axis | Expected range |
|---|---|
| Y | −0.565 … 0.278 (length 0.843) |
| Z | −0.169 … 0.084 (0.253) |
| X | about ±0.032 (charging-handle wings ±0.024, side rails ±0.0315) |
| Z with the optic | up to 0.138 |

**Side render**, the `bc.render_views` "right" view (camera at +X):
- muzzle on the left
- ammo counter visible above the grip, glowing ice and reading "30"
- magazine curving toward the muzzle
- rail top one unbroken straight line
- no front sight anywhere

The "left" view (camera at −X) shows the ejection port, dust cover and forward assist.

**Overlay test.** Render the "right" view orthographic. It should match `profile_sketch.png`. The quickest
check is to put both side by side at the same scale.

**Hierarchy.** Sockets exist, with zero rotation, at the positions in 4a. Moving parts have their origins on
their pivots: trigger, charging handle, dust cover, bolt catch, mag release.

**Glow and budget.** Exactly one emissive material on the base gun (`M_MAKO_Ice`, ammo screen). Tris
10–22k for the default loadout.
