# Shared optics

Six top-rail optics for the Mako and Warden. `build_optics.py` is the source;
`optics.blend`, the per-optic GLB/FBX exports, `catalog.json`, and `fitcheck.json`
are generated deliverables. Read [NOTES.md](NOTES.md) for design measurements and
node/material contracts; the earlier critiques in `review/` are historical evidence.
See [the shared attachments README](../README.md) for the combined catalog workflow.

## What changed in this cleanup

- Triangulate before removing bevel/boolean slivers. Checking only Blender polygon
  area missed about 90 degenerate triangles introduced when exporting four optics.
- Rebuild the six exports and Blender scene from that cleaned topology, while
  preserving the existing wide sight windows, sockets, materials and projector animation.
- Resolve project paths from the build script, and support `--out` for an isolated
  rebuild before replacing deliverables.
- Add `review/verify_cleanup.py` and a fresh `review/cleanup_checks.json`, covering
  source solid closure/normals, imported GLB geometry, UV/material assignments,
  catalog triangle counts, and every frame of the projector flap motion.

The earlier reticle size, holo tunnel, thermal eye relief, 3x silhouette and holo
detail fixes were already present and are retained. The old round-2 critique
describes the earlier five-optic set and must be read together with this current status.

## What still needs to change

- Load these exports in the game renderer. The current weapon view uses procedural
  placeholder meshes, so passing asset checks alone does not validate the game view.
- Register `optic_projector` in `game/assets/data/attachments.ron` and add it to the
  1x optics row in `game/assets/data/settings.ron`; suggested zoom is 1.2.
- Bind the ADS camera to `_SOCKET_ADS + Y * eye_relief_m`, preserving mount-space
  axes. Re-check sight visibility with the actual game FOV/tonemapper; `render.rs`
  currently uses 78 degrees vertical while the asset checks also cover settings
  `fov_h: 103` through each optic's zoom.
- Play projector `ADS_Open` forward on ADS and reverse on release (0.12 seconds).
  Hide its hologram at hip fire, reveal it above 80% ADS, and fade it in over
  0.08 seconds. Bind magnified scope/thermal rendering to the separate lens/display nodes.
- Judge any warmer bone colour together with the Mako and shared palette. Keep
  the current shared bone token until that coordinated change is made.

These are engine integration and shared-palette follow-ups; this cleanup changes
only the optics asset folder.

## Rebuild and verify

From the repository root in PowerShell, with Blender 5.2 and Python/Pillow installed:

```powershell
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --factory-startup --python-exit-code 1 --python 'assets/weapons/attachments/optics/build_optics.py' -- --render none
python assets/weapons/attachments/optics/validate_exports.py
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --factory-startup --python-exit-code 1 --python 'assets/weapons/attachments/optics/review/verify_cleanup.py'
python assets/weapons/attachments/build_catalog.py
```

Use `--render full` to regenerate the current render set, or `--render iter
--only optic_holo --views three_quarter,ads --tag check` for focused visual review.
Add `--out <absolute-directory>` to stage a build; pass the same path to both
validators. The Blender QA accepts it after `-- --out <absolute-directory>`.
The build leaves historical `review/` and `_ref/` evidence intact.

## Verification status

Current technical evidence is in `review/cleanup_checks.json`; delivered triangle
counts are authoritative in `catalog.json`. Budget is 1,500–5,000 triangles per
optic. Flat reticle/glint/hologram decals intentionally have open edges. Closed
solids are checked in the Blender source, because GLB export splits vertices at
UV, normal and material seams.

Representative images are in `renders/sheets/ATT_optics_overview.png`,
`renders/sheets/ATT_optics_ads_sheet.png`, and the projector pose sheet. See
`review/cleanup_visuals/` for the representative views rendered after this cleanup.
