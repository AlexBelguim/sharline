# ATT optics set (shared top-rail attachments)

Folder: `assets/weapons/attachments/optics/`. Prefix `ATT`. Specs followed: `art/WEAPON_MODULAR_SPEC.md`
("Optics", rail standard, handedness), `art/DIRECTION_LOG.md` item 2 (bone `optic_holo` like Mako v09), item 12
(1x sights are looked through; new `optic_projector`), `art/concepts/warden/BRIEF.md` 4.4 (`optic_sniper` numbers).

## Rebuild

```
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup ^
    -P "F:/git/val etf/assets/weapons/attachments/optics/build_optics.py" -- --render full
python "F:/git/val etf/assets/weapons/attachments/optics/validate_exports.py"
```

`build_optics.py` rebuilds everything from an empty scene: the six optics, the baked albedo textures and the
projector hologram texture (`textures/`), the rail fit-check, the flap clearance check, the near-plane check, the
ADS measurement on the Mako, `ATT_<optic>.glb/.fbx`, `ATT_optic_projector_Hologram.png`, `optics.blend`,
`catalog.json`, `fitcheck.json` and every render. It calls the **system python with PIL** twice:
`make_projector_reticle.py` (the hologram texture) and `make_sheets.py` (labelled sheets, measured ADS overlays,
before/after and concept comparisons). Options: `--render none|quick|full|iter`, `--only optic_holo,optic_projector`
(no export), `--no-export`, `--res 800`, `--samples 48`, `--debug`, and for iteration renders
`--render iter --views three_quarter,right,ads,folded_three_quarter,half_right,v0.55_1.0_0.35,close0,gun --tag x`
(writes `_work/iter/sheet_<tag>.png`). `validate_exports.py` re-reads every `.glb` / `.fbx` (no Blender needed):
nodes against the catalog roles, root `<role>_node` extras, ADS socket + `eye_relief_m`, a material on every
primitive, own materials on lens / display nodes, emissive only on reticle / glint / status / hologram / flap nodes,
single-sided reticle / glint, embedded textures, no `KHR_texture_transform`, the 1.5k-5k budget, PNGs in the `.fbx`,
and for the projector: flap `fold_angle_deg` / `open_angle_deg` extras, identity (folded) rest rotation, an
alpha-blended hologram material with base + emissive textures, and the `ADS_Open` clip on both flaps.

## Aperture revision (DIRECTION_LOG item 12, 2026-10-07)

User: the 1x sights are looked THROUGH in 3D, so the part you see through must be big. The old holo had a small
front window inside a big rear hood (a tunnel, `_ref/before_revision/ATT_optic_holo_ads_onmako.png`).

**FOV the checks use.** The player's default is `game/assets/data/settings.ron` `fov_h: 103` (16:9), which
`settings/model.rs` turns into 70.5 deg vertical; an optic's zoom makes the focal length `zoom` times longer
(`zoomed_fov`). Effective vertical ADS FOV: red dot (1.15) 63.2 deg, projector (1.2) 61.0 deg, holo (1.25) 59.0 deg.
`render.rs` still hard-codes a 78 deg vertical camera (not wired to the setting yet); the build measures that case too
(`at_render_rs_78deg` in the catalog).

**How it is measured.** `measure_ads()` casts one ray per pixel centre along the centre row and column of a
1920 x 1080 eye view (eye = `_SOCKET_ADS` + Y * `eye_relief_m`), with the optic snapped onto `MAKO_SOCKET_Optic` of
the real Mako export, against every opaque mesh (glass, reticle, glint, hologram are see-through). It reports the
clear window, the frame / hood run on the left, right and top, and the clear share of the whole screen (240 x 135
ray grid). `renders/ATT_<optic>_ads_onmako_measured.png` draws the result on the 1920 x 1080 render.

| optic | clear window on the Mako (W x H) | optic's own window | frame edge L / R / top | at render.rs 78 deg | target |
|---|---|---|---|---|---|
| `optic_holo` | 668 x 375 px = **34.8 % x 34.7 %** | 34.8 % x 43.4 % | 46 / 46 / 45 px = **2.4 %** of W | 30.4 % x 30.2 %, frame 2.1 % | >= 30 % W, >= 24 % H, frame <= 2.5 % |
| `optic_reddot` | 660 x 357 px = **34.4 % x 33.1 %** | 34.4 % x 48.1 % | 41 / 41 / 41 px = **2.1 %** | 30.0 % x 28.8 %, frame 1.9 % | >= 24 % W, frame <= 2.5 % |
| `optic_projector` | full width, 58 % H (no glass, no frame) | 100 % x 70 % | none | 100 % x 57 % | hologram frame 461 x 345 px = 24 % x 32 % |

On the Mako the lower edge of every window is the gun's own top rail / handguard running to the muzzle (it sits
5 deg under the sight line), not the optic. Before the revision the holo window was ~17 % of the width with a tunnel
round it; old vs new: `renders/sheets/before_after_optic_holo_ads_onmako.png`, `..._reddot_...`.

**How the windows stay big without a tunnel.** A hood seen from 5 cm shows its inner walls unless they point
at the eye. Both 1x sights now put the window walls *and* the hood / shroud flanks on the eye's view cone through the
rear frame (window walls 2 % outside it, so they face away from the eye). The front window is the rear one scaled by
the cone (holo 1.33x, red dot 1.25x), so from the eye both windows line up exactly, no wall shows, and the visible
frame is only the thin rear face (holo 2.4 mm at 50 mm, red dot 2.1 mm at 44 mm). Nothing sits over the centre: the
deck, buttons and emitter stay under the lowest sight ray through the window (the holo deck top is built 3 mm
under that ray).

## The optics

| id | what | ADS (x, y, z) m | eye relief m | L x W x H m | tris | for |
|---|---|---|---|---|---|---|
| `optic_reddot` | open reflex: 10 mm deep shroud on the view cone round a 33 x 26 mm window (2.1 mm frame), glass tilted 4 deg, short deck behind it (emitter hood, elevation screw on top, windage screw -X, two brightness buttons +X), skeletonised riser, cross-bolt knob +X / hex bolt -X. 24 MOA ice dot facing the eye, ice glint facing forward | (0, -0.0078, 0.049) | 0.0463 | 0.034 x 0.046 x 0.074 | 2044 | Mako (fits both) |
| `optic_holo` | **Mako default.** Bone box holo after v09, rebuilt round a 35 x 24.5 mm window (15 mm above / 9.5 mm below the sight line, as on most holos the dot sits low): 15 mm hood flaring forward along the view cone with 45 deg chamfered upper corners and a chamfered brow, dark window bezel (lining walls seen from the front), deck sloping down along the lowest sight ray with a 0.9 mm inset panel, proud main button + nub, wrap-around rubber guard on the +X front corner, dark base plate, mount bars both sides (+X bolt boss + butterfly QD lever, -X hex bolt), windage / elevation adjusters on the -X deck flank, hood / base seam, bone rear battery door with three grip lines and a rubber latch. Reticle 22 MOA dot + 68 MOA ring; v09 ice glint forward | (0, 0.0294, 0.045) | 0.0541 | 0.070 x 0.064 x 0.074 | 3300 | Mako |
| `optic_projector` | **new, high-end 1x** (see below) | (0, 0.030, 0.047) | 0.045 | 0.064 x 0.038 x 0.031 (folded) | 2624 | Mako (fits both) |
| `optic_3x` | compact 3x prism (unchanged this pass) | (0, 0.0508, 0.050) | 0.065 | 0.126 x 0.059 x 0.090 | 4542 | Mako + Warden |
| `optic_sniper` | **Warden default.** 5-25x after Warden BRIEF 4.4 (unchanged) | (0, 0.145, 0.0405) | 0.085 | 0.380 x 0.088 x 0.097 | 4696 | Warden |
| `optic_thermal` | boxy thermal (unchanged) | (0, 0.0918, 0.052) | 0.040 | 0.184 x 0.071 x 0.104 | 4276 | Warden |

The magnified optics (3x, sniper, thermal) switch to a scope view in code, so their lenses were left alone.

## optic_projector (new)

Valorant-style flip-up sight, original design, no glass. A low graphite housing (34 mm wide, 31 mm from the clamp
jaws to the hinge tops when folded, 25 mm above the rail top) with a chamfered hexagonal section, a long sloped nose
with a dark sensor window, vent grooves and a seam on both flanks, a raised spine between the flaps, a rubber power
button (rear) and brightness rocker (+X), cross-bolt knob +X / hex bolt -X. Two emitter flaps lie flush in dark bays
either side of the spine, on gunmetal hinge rods (each flap knuckle turns in a channel with 0.5 mm clearance). Bone
accent: an insert in each flap's outer face, so it reads folded and in third person but never shows in the ADS
picture. On ADS the flaps flip up 100 deg about their outer hinges (10 deg past vertical, leaning out) and the ice
emitter slits on their inner faces project the hologram.

- **Nodes:** `ATT_optic_projector` (root), `_Body`, `_Flap_L` (+X, shooter's left) / `_Flap_R` (-X), each with its
  origin ON the hinge axis, `_Hologram`, `_SOCKET_ADS` (sight line at the housing's rear face).
- **Flaps:** rest pose = FOLDED (identity rotation). Node extras: `fold_angle_deg` 0, `open_angle_deg` +100 (L) /
  -100 (R), `hinge_axis_gltf` [0, 0, -1] (Blender +Y), `open_rotation_gltf_xyzw`, `open_time_s` 0.12. Animation clip
  `ADS_Open` (0 -> 0.12 s, eased) rotates both flaps folded -> open: play forward on ADS, reverse on release. The
  build checks that no flap touches the housing or the other flap folded, half open and open.
- **Hologram:** one square quad (76 mm), 0.130 m in front of the eye at sight height (the task asked 0.10-0.18 m),
  sized so its corner-bracket frame is 65 x 49 mm = 24 % x 32 % of the screen at the projector's ADS FOV.
  Texture `textures/T_ATT_ProjectorHologram.png` (copy `ATT_optic_projector_Hologram.png`): 512 x 512, made with PIL
  by `make_projector_reticle.py`, WHITE on transparent (RGB 255 everywhere, alpha carries the shapes): four rounded
  corner brackets of a 4:3 frame, small mid-side ticks, a ~7 px centre dot inside a faint gapped ring, three subtle
  range ticks under the dot, a soft glow. Material `M_ATT_ProjectorHologram`: texture x tint in both
  `baseColorFactor` and `emissiveFactor` (ice 0.15, 0.75, 1.0, emissive strength 1.3), alpha BLEND, double-sided.
- **Engine notes (game session):**
  - open the flaps in about **0.12 s** on ADS (the clip, or rotate the flap nodes by `open_angle_deg` about
    `hinge_axis_gltf`), close them on release;
  - show `_Hologram` only above about **80 % ADS** and **fade it in** over ~0.08 s (scale its base colour alpha /
    emissive), hide it below; at hip fire the hologram node must be hidden (glTF has no visibility flag);
  - re-tint by changing the two factors (the texture is white);
  - suggested zoom **1.2**; the hologram is double-sided, so other players see a mirrored frame while someone aims
    (hide it for them if that tell is unwanted);
  - suggested data row (not added, `game/` is read-only here):
    `(id: "optic_projector", cat: optic, fits: ["ar7_mako", "vk50_warden", "sk9_skink"], name: "PROJECTOR",
    blurb: "Fold-out hologram. Nothing in the way.", zoom: Some(1.2), ads_time: Some(1.0))`, and add it to the
    `"Holo / red dot"` row of `settings.ron` `optic_rows`. (Test-fitted on the Mako and Warden; there is no Skink
    asset yet, the clamp is the same rail standard as the red dot / holo that already list it.)

## Conventions (all optics)

- **Mount space**: origin = centre of the clamp contact on the rail TOP surface, forward = -Y, up = +Z,
  shooter's RIGHT = -X, LEFT = +X. Snap = put the root on `<GUN>_SOCKET_Optic`, no rotation.
- **Nodes per file** (one child node per role, so the engine can treat each on its own):

  | node | role | optics |
  |---|---|---|
  | `ATT_<optic>` | root empty; extras `optic_id`, `category`, `mount`, `ads_height_m`, `length_m`, `magnification`, `eye_relief_m`, `ads_zoom`, `<role>_node` (+ projector: `ads_animation`, `hologram_show_from_ads`, `flap_open_time_s`, `hologram_fade_in_s`, `suggested_zoom`) | all |
  | `ATT_<optic>_Body` | opaque, multi-material | all |
  | `ATT_<optic>_Glass` | reflex window pane (alpha blend) | reddot, holo |
  | `ATT_<optic>_Objective` / `_Ocular` / `ATT_optic_thermal_Display` | lens / screen, own material (glint shader / scope view) | 3x, sniper, thermal |
  | `ATT_<optic>_Reticle` | ADS reticle, one-sided, faces the eye (+Y) | reddot, holo, 3x |
  | `ATT_<optic>_Glint` | third-person reticle glint, one-sided, faces forward (-Y) | reddot, holo |
  | `ATT_optic_thermal_StatusLight` | the amber LED | thermal |
  | `ATT_optic_projector_Flap_L` / `_Flap_R` | hinged emitter flaps, origin on the hinge | projector |
  | `ATT_optic_projector_Hologram` | projected reticle plane, alpha blend, emissive, double-sided | projector |
  | `ATT_<optic>_SOCKET_ADS` | empty on the sight line at the rear of the reticle / eyepiece / housing | all |

  `catalog.json` lists the same per optic (`nodes`, `ocular_node`, `objective_node`, `reticle_node`, `glint_node`,
  `hologram_node`, `reticle`), plus `aperture` (rear / front window mm, frame mm, eye distance, the full ADS
  measurement and its targets) for the 1x sights and a `projector` block (hologram, flaps, animation, timings).
- **ADS camera**: eye point = `_SOCKET_ADS + Y * eye_relief_m` (socket extras and catalog). Every optic keeps the
  nearest visible part >= 32.5 mm from the eye (render.rs near plane 0.03 + 2.5 mm), checked at the wider of the two
  game FOVs (`fitcheck.json` `near_plane`).
- **Reticle / glint**: one-sided decals (glTF `doubleSided` false); the eye never sees the glint and the front never
  sees the reticle. Reticles are sized for the screen (>= 5 px dots at 1080p), with a thin dark outline for contrast.
- **Rail clamps** (`rail_clamp()`): flat underside 0.1 mm above the rail top, jaws at |x| 0.0106, down to z -0.0062,
  square inner channel corners. Every optic is test-fitted on a dummy rail built to the standard (0.021 top width,
  0.0095 high, 0.005 x 0.003 cross slots every 0.010): 0 intersections, every clamp within 0.1 mm (`fitcheck.json`).
- On-gun snap test: the build imports the real gun exports (read-only) and puts each compatible optic on
  `<GUN>_SOCKET_Optic` from that gun's `sockets.json`.

## Materials (one per surface; glTF 1:1)

`M_ATT_Graphite` (0.030, 0.033, 0.040) r0.50 m0.25 · `M_ATT_Bone` (0.55, 0.52, 0.46) r0.60, baked exactly like
`M_MAKO_Bone` · `M_ATT_Gunmetal` (0.11, 0.115, 0.12) r0.35 m0.85 · `M_ATT_Rubber` · `M_ATT_Dark` · `M_ATT_Lining`
(window walls, dark slate) · `M_ATT_LensObjective` / `M_ATT_LensOcular` / `M_ATT_LensObjectiveDeep` ·
`M_ATT_ShadeLining` · `M_ATT_ReflexGlass` (alpha 0.30) · `M_ATT_Display` · `M_ATT_Germanium` · `M_ATT_IcePaint` ·
`M_ATT_ReticleDot` / `M_ATT_ReticleHolo` (textured quads, ice core + dark outline) · `M_ATT_IceGlint` (1.2) ·
`M_ATT_IceDot` (3x) · `M_ATT_IceEmitter` (projector flap slits, 0.9) · `M_ATT_ProjectorHologram` (white texture x ice)
· `M_ATT_AmberGlow` (thermal LED). Albedo detail is baked into one PNG per material (`textures/`) wired straight
into Base Color, so the FBX embeds it too. Emissive rule: base guns have none; optics carry only their reticle /
glint / status light, the projector its emitter slits and hologram. Every boolean now gives its new faces a real
material (no empty slots) and zero-area slivers are collapsed after the join (0 left on every optic).

## Renders

`renders/` per optic: `right`, `left`, `three_quarter`, `three_quarter_back`, `front`, `back`, `top`, the concept
camera `v0.85_-0.75_0.5`, `eye`, `onrail_*`, close-ups, on-gun snaps, `ads_on<gun>` and, for the 1x sights,
`ads_onmako_measured`. Projector: the main views are OPEN with the hologram; `folded_*` (hip fire, rest pose),
`half_*` (opening), `open_*` (framed on the optic), `onmako_folded_*`. `renders/sheets/`: a sheet per optic,
`ATT_optic_projector_poses.png` (folded -> half -> open -> ADS), `ATT_optics_ads_sheet.png`, `before_after_*`,
`compare_holo_*_vs_v09.png`, sniper comparisons, overview and line-up. Renders use a Cycles-only Backfacing ->
Transparent mix on the one-sided decals so they show what the engine shows (removed before the `.blend` is saved).

## Current cleanup

See `README.md` for completed changes, remaining engine integration, and repeatable
verification. The cleanup rebuild checks actual exported triangle areas in double
precision, so a healthy Blender n-gon cannot conceal a degenerate glTF triangle.
Fresh evidence: `review/cleanup_checks.json` and `review/cleanup_visuals/`.

## Review round 2 (`review/critique_latest.json`) - historical status

1. 1x reticles too small / white: textured quads, 22-24 MOA dots (>= 5 px at 1080p), 9 MOA ring line, dark
   outline, deeper ice, emissive 1.0 (kept from the previous pass; softness now uses the effective ADS FOV).
2. Holo ADS tunnel: fixed by this revision (table above); no viewmodel-FOV override is needed.
3. Holo face details vs v09: dark bezel (lining walls), chamfered brow, flat-panel deck with a proud button,
   wrap-around +X rubber guard, hood / base seam. The thin-frame rule limits the hood depth (see limitations).
4. Glint clipping to white: soft ice core + halo texture, strength 1.2 (kept).
5. Bone hue: unchanged on purpose (shared token with the Mako); `ATT_optic_holo_std_*` renders use the Standard view
   transform. Open request to the palette / Mako owner as before.
6. Sniper black objective: dark-slate sunshade lining + saturated blue lens (kept).
7. Holo blank hip faces: the hood is now a short frame; the rear face carries the bone battery door with grip lines,
   the rear window chamfer and the seam.
8. Thermal eye relief 0.040 (kept). 9. 3x directional silhouette (kept). 10. Stale hand-off numbers: the numbers
   here and in `catalog.json` come from the final build.

## Known limitations / notes

- **Physics of a no-tunnel hood**: any hood wall that the eye must not see has to lie on the view cone, so a deeper
  hood has to flare more (slope = the window's half angle, ~20 deg). The holo hood is therefore 15 mm deep and flares
  forward (front window 1.33x the rear one physically, identical from the eye). It keeps v09's bone box, brow, dark
  bezel and deck, but not v09's very deep hood.
- The window fractions depend on the FOV the viewmodel is drawn with. At render.rs's current 78 deg the holo window
  is 30.4 % of the width (still on target). If the game later draws the viewmodel with its own `viewmodel_fov`
  (settings default 68), re-check with `measure_ads()` (pass `base_vfov`).
- The Mako's own top rail fills the lower part of each window when aiming (as on a real rifle); the clear window on
  the gun is therefore shorter than the optic's own window.
- The projector hologram floats 2.5 cm in front of the housing and is wider than the optic (76 mm quad); the engine
  must hide it at hip fire (no glTF visibility flag).
- Turret knurling on the magnified optics is geometric (alternate vertices pushed in), faceted in extreme close-ups.

## Iteration log

Earlier sessions (kept): clamp/fit-check system; holo after v09; sniper to Warden BRIEF 4.4; 3x; reddot riser;
materials glTF 1:1; on-gun snaps; review round 1 and 2 fixes (reticle quads, lens nodes, closed turrets, baked
albedo, thermal lens stack, sniper lining, 3x silhouette).

Aperture revision (this pass, renders in `_work/iter/sheet_*.png`): i1-i2 (previous agent: big windows, but holo rear
frame ~12 % of the width and the projector hologram 45 mm from the eye) -> j1 view-cone hood / shroud, pixel ADS
measurement, projector rebuilt (hinge-axis flaps, PIL hologram at 0.13 m, folded rest pose) -> j2 full run, material
slot fix, flap hinge channels (flap clearance 14 -> 0) -> j3 asymmetric holo window + tall sloped deck (v09
proportions), bone inserts on the flaps / graphite spine -> j4 brow corners follow the hood facets -> j5/j6 deeper
red dot shroud, bone battery door with grip lines, larger bone inserts -> j7 full run, glTF checks (hologram material,
flap extras, clip) -> j8 catalog sizes without the hologram -> j9 brow folded into one flared hood (no corner
"horns" in the rear view) -> final: degenerate faces collapsed to 0, full run, validation ALL OK.
