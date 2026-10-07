# Art Bible — "val etf" prototype assets

Extraction shooter (Tarkov-style loop) with **stylized, readable Valorant-like visuals**, Apex-like movement
(jetpacks, ziplines), simplified guns/ammo and **simple, readable shield tiers** (equipment any agent can wear).

## Visual pillars
1. **Readable silhouette first.** Every asset must read instantly as a black silhouette at 64 px.
   Chunky, slightly exaggerated proportions; no noodly thin parts.
2. **Stylized, not realistic.** Clean planar hard-surface shapes, generous chamfers/bevels, big simple forms
   with a few crisp details. Painted, slightly flat material response (roughness 0.45–0.75, little
   metalness except bare metal), no photoreal grime. Think "Valorant / Overwatch 2 meets near-future
   tactical gear", **not** Tarkov realism and **not** neon cyberpunk.
3. **Near-future (≈2060s), grounded.** Base guns are recognisable real-world archetypes, modernised: smoother
   monolithic receivers, panel lines. **No ammo counters on any weapon** (genre rule: players check mags
   themselves). No floating parts, no sci-fi energy coils. Base guns have no emissive; optics may have one small
   reticle/status glow. Characters may carry more tech.
4. **One accent colour per asset** over neutral bases.

## Palette (linear RGB for Blender's Base Color)
| Token | Use | Linear RGB |
|---|---|---|
| graphite | metal receivers, hard armor | (0.030, 0.033, 0.040) |
| gunmetal | barrels, bolts, bare steel (metal 0.85, rough 0.35) | (0.11, 0.115, 0.12) |
| bone | polymer furniture, light panels | (0.55, 0.52, 0.46) |
| sand | furniture, pouches, cloth | (0.36, 0.28, 0.18) |
| olive | cloth / pants | (0.12, 0.13, 0.08) |
| charcoal-cloth | jackets, under-suits | (0.035, 0.037, 0.045) |
| teal (Kestrel) | accent / emissive | (0.0, 0.70, 0.62) |
| coral (Solace) | accent / emissive | (1.0, 0.36, 0.30) |
| ivory | Solace outfit main colour | (0.70, 0.67, 0.60) |
| ice (optic glow) | reticles, optic status lights | (0.45, 0.85, 1.0) |
| skin light | Kestrel skin | (0.62, 0.42, 0.33) |
| skin deep | Solace skin | (0.26, 0.14, 0.085) |

## Units, axes, origins (both engines + glTF depend on this)
- Metres. Blender Z-up. **Asset front faces −Y** (Blender "Front" view looks at its face/muzzle).
  Export: glTF Y-up (exporter handles it), FBX forward −Z / up Y.
- Characters: feet on Z = 0, centred on X = Y = 0, **A-pose** (arms ~45° down), symmetric where possible.
  Heights: Kestrel 1.70 m, Solace 1.68 m (without hair volume).
  Handedness: a character facing −Y has her **RIGHT at −X and LEFT at +X** (same for a shooter behind a gun).
- Weapons: muzzle toward −Y, **origin (0,0,0) at the pistol-grip hand position** (top-centre of the grip where
  the web of the hand sits), bore axis along Y. Real-world scale.
- Object names: `PREFIX_Part` (e.g. `KES_Jacket`, `MAKO_Upper`). Helper/temp objects start with `_`.

## Poly budgets (triangles, evaluated, after modifiers)
| Asset | Target | Hard max |
|---|---|---|
| Character (incl. hair, gear) | 30k–50k | 70k |
| Heavy sniper | 12k–25k | 35k |
| Assault rifle | 10k–22k | 30k |
Use bevel modifiers with 1–3 segments and auto-smooth (`bc.shade_smooth`) rather than subdividing everything.

## Materials
- Use `bc.material(name, color, rough, metal, emission=…, tex=…)`. Material names: `M_<Asset>_<Surface>`.
- Shared tileable detail textures live in `art/textures/` (made with the local Krea2 model). Use them as a
  **subtle multiply** (`tex_mix` 0.25–0.6) for painted wear / fabric weave — flat colour must still carry the look.
- Every mesh must have UVs before export (`bc.uv_all()`).

## Halo shields instead of armor plates (user decision)
Protection is **equipment any agent can wear**, never part of a character's design. Each armor projects an
energy shield, shown as a **tech halo floating above the head**. The halo's colour shows the tier, its lit arcs
show coverage (head / torso / arms / legs), its ring shape shows the core type, and orbiting cells show the
power level. Hits throw hex shards in the tier colour. Full spec: `art/HALO_SHIELD_SPEC.md`.
- Every character gets a `<P>_SOCKET_Halo` empty about 0.22 m above the top of the head.
- Characters therefore wear **no tier pips or heavy armor plates**. A light chest rig or outfit plate is fine as
  pure styling (e.g. Kestrel's bone chest piece from her concept v06).

## Tools
- Headless Blender: `"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P script.py`
- Helpers: `tools/blender_common.py` (`import blender_common as bc`) — primitives (`box`, `cylinder`, `sphere`,
  `profile_extrude`, `lathe`), `add_bevel`, `boolean`, `mirror_x`, `join`, `material`, `uv_all`, `stats`,
  `setup_studio`, `render_views`, `contact_sheet`, `export_all`. Read the file for exact signatures.
- Images: `python tools/comfy_gen.py --prompt "…" --out file.png [--w --h --seed] [--tileable]`
  (ComfyUI must be running on 127.0.0.1:8188; ~15–60 s per image; jobs queue, so several agents can call it).
  Prompt tips: do NOT write "tile"/"tileable" in texture prompts (it draws literal tiles) — describe the
  surface ("uniform close-up surface of …, evenly lit, no borders, no objects") and pass `--tileable`.
  Characters must be described as fully clothed in tactical gear.
- **Image references** (Krea2 identity edit, which keeps a character/design consistent): add `--ref image.png`
  (once for the subject, or twice for scene + subject) and write the prompt as a plain-English instruction, e.g.
  "Show this exact same character from the side, full body, plain grey background. Preserve the exact identity."
  `--ref-boost` sets likeness (default 4). Use it for turnarounds, close-ups and detail views of a chosen design.
  ~60–110 s per image.

- **Image → 3D (characters only):** `python tools/trellis_gen.py --image apose.png --out model.glb --seed N --faces 80000`
  runs TRELLIS.2 locally (about 75 s; it removes the background itself; best input is a clean full-body A-pose
  front view). Results vary a lot by seed, so try several. `blender -b --factory-startup -P tools/inspect_glb.py --
  <in.glb> <ABS out_dir> <prefix> <height_m>` normalises it and renders a turnaround and a head close-up.
  Weapons stay procedural, because modular parts need clean separate meshes.
- Always pass **absolute** output paths to renders and exports.

## Deliverables per asset
`assets/<kind>/<name>/` containing `build_<name>.py` (re-runnable from scratch), `<name>.blend`, `<name>.glb`,
`<name>.fbx`, `renders/` (front, right, back, three_quarter + a contact sheet), and `NOTES.md` (design notes,
tri count, materials, known limitations).
