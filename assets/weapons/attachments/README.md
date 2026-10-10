# Weapon attachments

Start with [optics/README.md](optics/README.md) or [tactical/README.md](tactical/README.md).
Those files explain the current cleanup, verification, and remaining work. Each folder's
`NOTES.md` keeps the detailed design and iteration history.

The two `review/critique_latest.json` files review **older exports**. Subsequent fixes
are described in the NOTES; use the new cleanup checks linked from the READMEs when
assessing the current deliverables.

## Cleanup completed

- Optics: removed degenerate export triangles, preserved hardened surface normals,
  and rebuilt the Blender scene and GLB/FBX files. The six optics pass source closure,
  raw export geometry, metadata, budget, and projector motion checks.
- Tactical: verified the existing geometry fixes with a fresh rebuild, all 20 GLB/FBX
  files, and 14 Mako/Warden fits with zero measured penetration. Active scripts now
  support portable paths and isolated review builds; bad fits fail validation.
- Documentation: added current READMEs and the shared catalog below. Historical reviews
  and earlier model evidence remain available.

## Shared catalog

[`../attachments.json`](../attachments.json) is the combined handoff for all **16 exports**:
six optics and ten tactical parts, including left/right laser and flashlight variants.
It was missing from the modular-weapon deliverables and is now generated from the two
local catalogs rather than maintained by hand.

From the repository root, after rebuilding either set:

```powershell
python assets/weapons/attachments/build_catalog.py
python assets/weapons/attachments/build_catalog.py --check
```

The generator checks that both export files exist, GLB roots and triangle counts agree
with the source catalogs, IDs are unique, and mount/compatibility fields are populated.
It also compares tactical fit socket metadata with the current gun GLBs, so an older
Warden fit catalog cannot silently pass after a proportion revision.
`--check` also fails if the combined catalog needs regeneration. No Blender dependency
is needed for this step.

- `id` retains the source catalog's asset ID; tactical IDs include the `ATT_` prefix.
- `game_attachment_id` is the gameplay data ID; both laser variants share `laser`.
- `file` and `file_fbx` are paths relative to the repository root.
- `compatible_weapon_ids` follows `game/assets/data/attachments.ron` for registered parts.
  The unregistered projector uses the Mako/Warden compatibility from its asset catalog.
- `tested_weapon_prefixes` records the available Mako/Warden asset fits separately.
  Gameplay permits some attachments on the Skink, but there is no Skink model to test.
- `game_data_status` means whether a row exists in gameplay data, not whether the renderer
  loads the model. The source metadata retains ADS sockets, roles, and moving-part settings.

## Remaining work

The current game renderer still constructs placeholder weapon shapes. It needs to load
these exports, snap attachment roots to the gun socket nodes, and use their child roles
for glass, reticles, beams, and moving parts. Adding the catalog alone does not perform
that integration.

The projector also needs a gameplay/settings entry, flap animation on ADS (0.12 s), and
hologram visibility above about 80% ADS with a 0.08 s fade. Its exported `ADS_Open` clip
and node extras are documented in [optics/NOTES.md](optics/NOTES.md).

The sight measurements cover both the settings-based FOV and the renderer's current
78-degree vertical FOV. Recheck them when the renderer starts using the settings FOV.
The tactical shield retains the specified glass span; the optional viewport adjustment
and its tradeoff are documented in [tactical/NOTES.md](tactical/NOTES.md).

Authoritative asset rules: [modular weapon spec](../../../art/WEAPON_MODULAR_SPEC.md),
[direction log](../../../art/DIRECTION_LOG.md), and [style guide](../../../art/STYLE_GUIDE.md).
