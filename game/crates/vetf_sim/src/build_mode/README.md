# Engine-free building-mode foundation

The public entry point is `vetf_sim::build_mode::inspect_map(assets_root, map_id) -> Result<MapInspection, BuildError>`. It reads the actual user placements, the current proposal, the catalog, fixed collision and prop collision. Its JSON-compatible report contains counts, warnings and SHA256 hashes. Inspection never accepts proposals or writes a placement file.

`Placements::from_ron`, `load` and `to_ron` support the supplied `[x,y,z]` lists as well as RON tuples. `IMPLICIT_SOME` accepts hand-authored `color_variant: "blue"`. Typed props, clips, spawns, extracts, loot, foliage volumes and suggested regions retain the world frame and origin. Unknown editable fields are rejected instead of silently discarded. The optional prop tilt is local X/Y degrees, followed by yaw; omitted mode means `all`. Old RONs load with an empty foliage list; saving an empty list omits that field.

`EditSession::apply` accepts add, delete, move, rotate, uniform scale, resize, duplicate, lock and loot-flag commands. `transaction` commits a command batch as one snapshot; failure leaves the entire state unchanged. Locked items can be unlocked explicitly but cannot otherwise be edited or duplicated. Undo/redo restores exact document and proposal state, and a new branch clears redo. Props use absolute scale; clip and extract dimensions use a validated uniform scale factor. Props remain limited to 0.8–1.25.

Editable hedges use `FoliageVolume` in `Placements::foliage_volumes`. Kinds are `hedge`, `bush`, `tree` and `climber`. Position is the ground-centre pivot in design XYZ; its Z coordinate is the envelope bottom. Dimensions are local X width, Y depth and Z height. `Resize { id, dimensions_m }` sets those three axes independently; `Scale` applies any positive finite uniform factor to foliage dimensions. Foliage stays upright and supports yaw rotation, move, duplicate, delete, lock, undo/redo and proposals. Nonpositive/nonfinite dimensions or scale, negative/nonfinite density and an empty tint are rejected transactionally. Density and the existing tint token are preserved. Example editable entry:

```ron
foliage_volumes: [
    (id: "user_hedge_1", kind: "hedge", position: [338, 640, 0],
     dimensions_m: [12, 1.2, 3], yaw_deg: 45,
     density: 1, tint: "sage_hedge", mode: "all"),
],
```

`foliage::export_foliage(document, active_mode)` (also `collision::instantiate_foliage`) returns stable-id-sorted volume exports and matching closed oriented convex collision. The renderer can build the existing envelope geometry inside `local_bounds_bevy` and apply the column-major `transform_bevy`; `world_bounds_bevy` is only a broad-phase AABB. Hedge/bush envelopes use `foliage_dense`, tree/climber envelopes use `foliage_thin`. These are foliage envelopes and do not generate trunks or leaf cards. The adapter preserves density, tint, mode and locking, and applies the same yaw/origin conversion to the visual envelope and collider.

`foliage::import_authoring_foliage(json, id_prefix)` is an explicit caller-controlled conversion from fixed authoring AABBs, supporting both the core's legacy JSON list and the extension's schema-1 document. It does not alter the fixed kit, automatically duplicate foliage into user placements or save any file. `inspect_map` also reports editable foliage and its collision count.

`set_proposal`, `proposals`, `accept` and `reject` compare every editable item by its stable id. Each item is added, changed or removed explicitly. Loading a proposal preserves current user edits. Rejections are saved in `proposal_resolutions`; their digest applies only to that proposed item, so a changed proposal becomes pending again. Acceptance of a changed locked item requires unlocking it first. The kit, frame and origin are outside per-item proposal acceptance.

`EditorOptions::load` reads numerical settings from `assets/data/build_mode.ron`, or uses defaults when the file is absent. Position and angle snapping are independent. The default autosave interval is 120 seconds; this module does not start a timer.

`save_atomic` writes a same-directory temporary file, syncs it, creates a timestamped backup of the previous user file, then replaces the target and keeps the last ten backups. An optional expected SHA256 detects a stale editor. Tests use temporary directories; no test saves an actual supplied placement file.

`collision::CollisionDocument::load` retains full convex planes, vertices, physical material, walkability, parent links and extra data. `in_bevy(origin)` transforms fixed world collision to `(x,z,-y)` with the origin offset. `instantiate_props` applies uniform scale, local tilt, positive yaw and translation to the entire convex geometry, in stable instance-id/source-volume-name order. Positive design Z yaw becomes positive Bevy Y rotation. AABBs are rebuilt after transformation and remain broad-phase metadata.

For non-lootable props in `category=containers`, the collision adapter closes moving leaves using the actual OPEN parent's world matrix from the prop GLB JSON chunk. Source COLL vertices already contain the authored ajar pose. Hinge pivots come from that matrix; drawer closed locations come from metadata. The exact delta is applied to planes and vertices. Structural garden gates and worksite doors retain their authored pose. No pivot is inferred from a collider centre or its AABB thickness.

`kit_placements_hash` sorts normalized relative paths and hashes length-delimited path names and bytes. Map inspection includes the fixed kit, current catalog, referenced prop GLBs/LODs/collision, local image dependencies, sampled ground-contract files and user placements. Pending proposal bytes are excluded. This provides a deterministic version fingerprint; it is not yet connected to a network handshake.

The tested foundation leaves client camera/browser/gizmos, rendered scene loading, editable marker collision integration, full placement/doorway/reachability checks, autosave scheduling and Play from here for the next implementation stage. The existing game is not launched by these tests.

Validation: `cargo test -p vetf_sim build_mode --offline`. Seventeen tests cover actual core/extension RONs and the current prop catalog, markers and foliage data, independent hedge dimensions, scale/rotation/history/locking, transactional invalid edits, proposals, snapping/prop scale bounds, atomic saves/backups/conflicts, sorted hashes, exact oriented convex transforms, explicit fixed-foliage import, OPEN pivot closure and read-only map inspection. The game offers a separate read-only Showhome v3 TDM preview; the interactive client editor and editable foliage scene-loader wiring remain deferred.
