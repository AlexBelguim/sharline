# Tactical attachments

Start here for the current asset status and rebuild workflow. [NOTES.md](NOTES.md) holds the detailed design,
materials, dimensions and previous fix history. The constraints are in
[WEAPON_MODULAR_SPEC.md](../../../../art/WEAPON_MODULAR_SPEC.md).

## Current status

The latest critique in `review/critique_latest.json` describes older exports. Its required geometry and material
fixes are already in the current assets: dark shield glass, clean laser/launcher seams, separate bipod splay pivots,
smoother launcher muzzle, correct compatibility and clamps that clear both real gun rails. Do not reapply that
critique without checking the current model. Historical review files and before-images are retained.

The cleanup verified the delivered exports against a fresh Blender 5.2 build. All ten rebuilt GLBs match the delivered
GLBs byte for byte, and all fourteen supported Mako/Warden fits have **0.00 mm penetration** using socket nodes from
the current gun exports. Both gun exports agree with their `sockets.json` positions. The launcher remains 5,822 triangles,
the bipod 3,792, and every attachment is within its budget.

## What changed in this cleanup

- Added this README to distinguish current work from historical critique.
- Active scripts now find the repository and asset folder from their own location.
- `build_tactical.py --out DIR` supports a review build without overwriting delivered assets.
- `render_tactical.py --blend FILE --out DIR` supports previewing that review build.
- `validate_tactical.py` independently imports all GLB and FBX exports, checks triangle counts, topology, winding,
  UVs, materials and catalog bounds/nodes, and checks the bipod fold and launcher muzzle hierarchy.
- `check_fit.py` writes fresh evidence under `_work/validation/` and fails when a fit penetrates a gun by more than
  0.02 mm. It no longer overwrites the historical `_work/rev4/fit_check.json` by default.

Fresh local evidence lives in `_work/validation/exports.json`, `fit_check.json` and `renders/`.
`rebuild_comparison.json` records the delivered/rebuilt GLB hashes. The topology check welds export seam vertices
on a temporary copy; two enclosed launcher housing/receiver contact edges are recorded separately from defects.

The Warden loadout images and `renders/sheet_loadouts.png` were refreshed from the current slender Warden export,
with the current sniper optic on its Optic socket. The older bulky Warden rows and sheet are preserved in
`_work/validation/warden_loadout_before/`. `renders/loadouts/sources.json` records the exact gun, optic and tactical
source hashes used for refreshed loadouts. The catalog and saved TestFit rig were also refreshed from the current
gun sockets; the attachment GLBs were verified unchanged.

## Remaining work

| Item | What needs to change |
|---|---|
| Engine integration | Consume the [shared catalog](../../attachments.json); use `compatible_weapon_ids` and the matching gun socket node. Verify materials and moving poses in the game. |
| Skink fit | Laser and flashlight compatibility includes `sk9_skink`, but no Skink art export exists to verify its rail geometry. Re-run fit checks when that export is available. |
| Shield sight balance | The specified glass span remains z +0.030 to +0.100 m. The aim point is low in this window. Recentring the window is a design option, not a required repair; agree a new span before editing `build_shield()`. |
| Future gun or attachment exports | Rebuild and re-check the fits whenever socket positions or rail geometry change. The flashlight clears the shield port by only 2.4 mm, so a wider light head needs a new clearance check. |

## Rebuild and verify

Run these commands from this folder in PowerShell. Blender 5.2 and Python with Pillow are required.
`--python-exit-code 1` makes Blender script failures visible to automation.

```powershell
$blender = 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe'
& $blender -b --factory-startup --python-exit-code 1 -P build_tactical.py
& $blender -b --factory-startup --python-exit-code 1 -P validate_tactical.py
& $blender -b --factory-startup --python-exit-code 1 -P check_fit.py
& $blender -b --factory-startup --python-exit-code 1 -P render_tactical.py -- --sets alone,detail,fit,open,loadout,sight,closeup
& $blender -b --factory-startup --python-exit-code 1 -P render_railfit.py
python make_sheets.py all
python ../build_catalog.py
```

For a review build first:

```powershell
& $blender -b --factory-startup --python-exit-code 1 -P build_tactical.py -- --out _work/validation/rebuild
& $blender -b --factory-startup --python-exit-code 1 -P validate_tactical.py -- --source _work/validation/rebuild --out _work/validation/rebuild_exports.json
& $blender -b --factory-startup --python-exit-code 1 -P render_tactical.py -- --blend _work/validation/rebuild/tactical.blend --out _work/validation/renders
```

To refresh only the Warden loadout rows and the loadout sheet after a gun export:

```powershell
& $blender -b --factory-startup --python-exit-code 1 -P render_tactical.py -- --sets loadout --loadout-guns warden
python make_sheets.py loadouts
```

Edit the builder and `att_lib.py`, then regenerate both export formats, `catalog.json`, renders and sheets together.
Models use metres, Z up and muzzle toward -Y; the shooter's right is -X. Origins are in mount space, and moving meshes
and sockets must remain in their existing hierarchy. Compare the updated GLBs with the catalog and game data before
refreshing the shared catalog with `python ../build_catalog.py`.
