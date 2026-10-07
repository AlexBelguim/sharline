# Modular weapon spec (attachments & swappable parts)

Both base guns are built as a **receiver/base mesh + swappable parts that snap onto named sockets**, so the
game can mix and match. Overrides anything in the per-weapon concept BRIEFs that shows integrated scope /
bipod / stock: those become separate attachments.

## User direction decisions (override the concept BRIEFs)
- **Mako: NO iron sights and NO ammo counter.** The master reference is `art/concepts/mako/v09.png`.
  See `art/DIRECTION_LOG.md` item 2 for the full list. Aiming relies on the optic attachments.

## Socket convention
- Each weapon file has a root empty `<P>_Root` at the weapon origin (pistol-grip hand position; muzzle → −Y,
  Z up). All weapon meshes and sockets are children of it.
- Sockets are **empties** named `<P>_SOCKET_<Slot>` (children of the root). glTF/FBX keep them as nodes.
- **Every attachment / swappable part is modeled so its own origin is its mount point**, with the same axes
  as the gun (forward = −Y, up = +Z). Snapping = put the part's origin on the socket, no rotation
  (except side mounts, see below). Moving parts inside an attachment (bipod legs, flip caps, GL breech)
  are separate child objects with their origin at the hinge.
- Rail standard (stylized Picatinny): rail top width **0.021 m**, rail height above its base 0.0095 m,
  cross slots every 0.010 m. Top-mounted attachments' origin = **centre of the clamp's contact on the rail
  top surface**; under-mounted = centre of clamp contact on the rail bottom surface (part hangs down −Z);
  side-mounted = centre of contact on the rail's outer face, sticking out sideways. Side attachments are
  modeled for the shooter's RIGHT side and **exported twice**: `<name>_R` and `<name>_L` (mirrored across X,
  normals recalculated). All sockets, including `_Side_L`, have zero rotation.
- **Handedness (important):** the shooter stands behind the gun looking toward −Y, so the **shooter's RIGHT
  is −X and LEFT is +X**. Ejection port, bolt handle, charging-handle latch and forward assist go on −X;
  `_SOCKET_Side_R` is at −X, `_SOCKET_Side_L` at +X.

| Socket | Where | Accepts |
|---|---|---|
| `_SOCKET_Optic` | top rail, the default optic clamp centre (over the receiver) | optics |
| `_SOCKET_Stock` | rear attachment point on the bore axis (buffer tube end / chassis hinge) | stocks |
| `_SOCKET_Mag` | top-front of the magazine well opening (where the mag's top-front lip seats) | magazines |
| `_SOCKET_Under` | handguard bottom rail, comfortable foregrip position | foregrips, grenade launcher (Mako), bipod (Warden) |
| `_SOCKET_Side_R` / `_SOCKET_Side_L` | handguard side rails near the front | laser, flashlight |
| `_SOCKET_Shield` | front end of the handguard top, on the centreline (Mako only) | front shield |
| `_SOCKET_Muzzle` | barrel end on the bore axis (for VFX; muzzle devices stay integrated) | — |
| `_SOCKET_ADS` | on every OPTIC (not the gun): the eye-line point behind the reticle | camera aim |
| `_SOCKET_LeftHand` | on the gun and on each foregrip/GL: where the support hand grips | IK target |

Socket positions are also written to `assets/weapons/<gun>/sockets.json`
(`{socket: {"location": [x,y,z], "rotation_deg": [x,y,z]}}`, metres, Blender axes).

## Parts list
### AR-7 Mako (prefix `MAKO`) — folder `assets/weapons/ar7_mako/`
- Base: upper + lower + barrel + compensator + handguard (with top/bottom/side rails) + pistol grip +
  trigger + charging handle + dust cover + forward assist + buffer tube. Moving parts separate: trigger,
  charging handle, dust cover, bolt-catch, mag release (optional).
- Stocks: `stock_standard` (angular collapsible, default), `stock_precision` (fixed, cheek riser, thicker pad),
  `stock_light` (minimal skeleton).
- Magazines: `mag_30` (curved STANAG-style, default), `mag_45` (extended, longer curve), `mag_drum60`
  (compact drum). Each mag has a separate `round` mesh (one visible top cartridge) as a child.

### VK-50 Warden (prefix `WARDEN`) — folder `assets/weapons/vk50_warden/`
- Base: receiver + chassis + barrel + muzzle brake + handguard (top rail, bottom rail for bipod, side rails) +
  pistol grip + trigger guard + bolt (separate object, origin at bolt axis rear) + trigger.
- Stocks: `stock_standard` (skeletonised chassis stock with cheek riser + monopod spike, default),
  `stock_folding` (lighter folding skeleton stock).
- Magazines: `mag_5` (default), `mag_8` (extended).

### Shared attachments — folder `assets/weapons/attachments/` (prefix `ATT`)
- **Optics** (top rail): `optic_reddot` (mini open reflex), `optic_holo` (box holographic, Mako default),
  `optic_3x` (compact prism mid-range), `optic_sniper` (5–25x long scope with rings + sunshade, Warden default),
  `optic_thermal` (bulky boxy thermal scope: front germanium lens dark with amber tint, side battery
  housing, rear eyecup/display, small amber status light). Each optic has `_SOCKET_ADS` child.
- **Foregrips** (under rail): `grip_vertical`, `grip_angled`, `grip_stub` (hand stop). `_SOCKET_LeftHand` child.
- **Underbarrel**: `ugl_launcher` — 40 mm-class single-shot grenade launcher (angular near-future housing,
  barrel tube ~0.045 m bore, own trigger + grip/guard, breech that swings open as a child object).
  `bipod` — sniper front bipod: clamp + 2 angular telescoping legs, legs separate objects with hinge origin,
  delivered DEPLOYED (legs angled down/forward ~ 50° from the rail) with a `folded` pose stored as
  custom properties (`fold_angle_deg`) for the engine.
- **Side rail**: `laser` (compact box, emitter lens red emissive dot + IR window), `flashlight` (cylindrical
  light with knurled bezel, lens slightly emissive). Exported as `_R` and `_L` variants.
- **Shield**: `shield_front` (Mako) — compact ballistic gun shield: angular graphite plate ~0.32 m wide × 0.26 m
  tall perpendicular to the bore, slightly wrapped, with a blue-tinted ballistic glass viewport aligned with
  the optic sight line, mounted by an arm clamp to the shield socket. Must not block the sight line.

Visual rules for attachments: same art bible (stylized, chamfered, graphite/bone/sand, single tiny ice/amber
accent max). Budget: optics 1.5k–5k tris, grips 0.5k–1.5k, GL 3k–6k, shield 1.5k–4k, laser/light ≤1.5k.

## Exports
Each part → its own `.glb` + `.fbx` named `<prefix>_<part>.glb` (origin = mount point) inside its folder,
plus each base gun `.glb` with its socket empties, plus `assets/weapons/attachments.json` catalog
(`id, category, file, sockets_accepted, compatible_weapons`). The `.blend` of each gun contains the base +
all its own parts in separate collections. `assets/weapons/loadouts/` holds assembled showcase renders.
