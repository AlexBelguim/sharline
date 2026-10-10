# Building mode implementation

The user authorized this work after the Showhome v3 core and residential/worksite extension exports were completed. Those assets are staged in game/assets/maps/showhome_v3. The existing Showhome is preserved.

The first implementation provides the engine-free data foundation in vetf_sim::build_mode: editable placements, catalog/collision parsing, snapping, edit history, proposals, safe persistence and map inspection. It follows art/briefs/showhome_rebuild/02_BUILD_MODE.md. The interactive editor UI is still pending.

Showhome v3 now has a read-only TDM preview selected in PLAY > HOST GAME > MAP before CREATE LOBBY, alongside original Showhome. `val_etf --host showhome_v3 --live` launches the same preview directly. It reads the current `placements.reference.json` at runtime (proposal/user files are fallbacks only), loads houses and ground with the design-to-Bevy origin offset, and renders reusable catalog instances. Exact convex collision includes real OPEN node pivots when closing decorative containers. Existing foliage, grass, surface-depth, decals and audio remain active. Team spawns are temporary collision-checked points in the suggested regions; no user markers or placements are written. The construction extension is excluded.

Next work: free-fly editor camera/browser and editing controls; marker inspector/check overlays; then Play from here and map-hash enforcement in the multiplayer handshake. Per-material penetration tuning beyond the existing gameplay surface classes remains separate work.

User-owned placements.ron is preserved. Newly authored layout changes are proposals until explicitly accepted in the editor. Mode=tdm barriers must be excluded from extraction; the extension remains independently loadable. Exact physical thickness, OPEN parent pivots and the world-to-TDM offset must remain common to visuals and collision.

## Verified

Current TDM preview checks: `cargo check -p val_etf --offline` and `cargo build --release -p val_etf --offline` passed. Full simulation tests passed 244 unit + 25 integration tests. Full game tests passed 512, with the opt-in public-network test ignored. Preview tests cover actual reference data, safe temporary spawns, nonwalkable collision, independently assembled closed hull geometry, all instance render/collision transforms, staged height paths, supplied glTF normal strengths, private normal-image cache reuse, the full foliage culling bounds and headless lobby selection. Runtime GPU captures are checked separately by the asset integration task.

- `cargo test -p vetf_sim build_mode`: 17 tests passed.
- `cargo test -p vetf_sim`: 241 unit and 25 integration tests passed (266 total).
- `cargo run -p vetf_sim --example build_mode_check -- showhome_v3`: valid authored data; 47 catalog props, 1675 fixed and 3515 instantiated prop volumes.
- Actual core/extension RON round-trips, snapshot transactions and locking, proposal accept/reject, snapping, backups/stale save detection, sorted SHA256 hashing, exact affine convex planes and closed hinge/drawer/lid collision are covered.
- Inspection never writes user placements. It reports 100 pending changes and no spawn markers, which remain user editing decisions.

The inspection example runs without Bevy or a window. It checks authoring data; the separate game preview launch above is playable, while the interactive editor remains unimplemented.

Editable foliage volumes now support hedge placement, independent width/depth/height, move/yaw, duplication, locks and undo/redo. Their collider and renderer-volume exports stay aligned. Fixed kit foliage is imported only through an explicit API call. Prop uniform scale remains 0.8-1.25; hedge dimensions can be resized independently. This data foundation is tested, while the in-game editor UI still needs implementation.
