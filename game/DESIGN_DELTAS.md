# Design deltas: where the game deliberately differs from `design/`

`design/systems/data/*.json` is the source of truth for gameplay numbers, and
`crates/vetf_sim/tests/design_sync.rs` fails when `game/assets/data/*.ron` drifts from it. The user has since given
direction that changes some of those numbers and systems. Cloud sessions cannot edit `design/` (it belongs to the
local session), so each change is listed here and skipped by the sync test (`superseded()` in `design_sync.rs`).
Once the design docs and JSON are updated, delete the entry here and in `superseded()`.

## 1. Ammo decides halo penetration (class × type × tier)
- **Design:** one flat `shield_pierce` per weapon (Mako 0.0, Warden 0.3).
- **Now:** `assets/data/ammo.ron`. A loadout loads one ammo for its gun, picked as a **type and a tier** (e.g. AP II).
  Nothing to sort per round or per magazine, so it stays lighter than Tarkov.
  - **Weapon class** (SMG, light assault, assault rifle, heavy assault, shotgun, bolt sniper) sets the baseline
    penetration per halo tier. Example from the direction: SMG rounds slightly pierce T1 and do nothing to T2+.
  - **Type** changes the halo-vs-HP split:
    - Standard.
    - AP: pierces, slightly less damage.
    - Shrapnel: shreds shields, no pen.
    - RIP: big HP damage, weak on shields.
    - Slug: shotgun only.
  - **Tier I-III** scales the type's speciality.
- The Warden's standard round keeps the design's 0.30 pierce against T3.
- **Pending:** the shotgun's pellets and slugs, and the SMG / light / heavy assault guns themselves. The data hooks
  exist already.

## 2. Armor tier per halo section
- **Design:** one halo has one tier, a list of covered zones and one shared shield pool.
- **Now:** `assets/data/armor.ron`. Every arc has its own tier and its own shield pool, so a torso arc can break
  while the head or leg arc holds.
  - **Arc capacity** = core capacity for that tier × `zone_capacity_share` (head 0.6, torso 1.0, arms 0.6, legs 0.6).
  - **Weight class** comes from the sum of the arc tiers. With uniform tiers this equals the design's
    tier × zones, so the design presets keep their weight class, cells, move and energy numbers (still tested).
  - **Loadout caps** (`loadout_tier_caps`) keep leg arcs at T2 or below. Higher leg protection is meant to be rare
    loot, so spraying legs stays a real option.
- **Balance note:** with the design's spill factors (legs ×0.85, 70% spill to torso), spraying the legs of a T4-torso
  target takes about as many rifle shots as going through the torso (10 vs 8). To make leg spraying a stronger
  counter, raise `spill_to_torso.legs` in `weapons.ron`; that is a design call.
- **Visual impact (art):** each halo arc should show its own tier colour, not one colour for the whole ring.
  `art/HALO_SHIELD_SPEC.md` needs an update by the local session.

## 3. Aiming: slower fire, lighter recoil, accurate first shot
- `ads_rpm_mult` (Mako 0.85): automatic fire is slower while aimed (720 → 600 RPM at the 60 Hz tick).
- Mako `recoil.ads_mult` is 0.7 (design: 0.85).
- `ads_first_shot` (Mako on, Warden off): an aimed first shot ignores the airborne penalty, and on the ground it
  ignores movement up to 35% of jog speed. A shot counts as "first" when the recoil pattern has reset.

## 4. Learnable recoil when still, bloom when moving
- The per-shot bloom values are the design's, but bloom now scales with movement: 0 below the movement threshold,
  full at full speed or in the air. Standing still, the only things moving your aim are the fixed recoil pattern
  and the small base spread.

## 5. Small things that are not changes, but worth knowing
- **Port:** the host-game mockup (`design/ui/mockups/png/04b_main_menu_host.png`) shows UDP port 7777, while the
  network diagram uses 47820. The game uses **47820** (`assets/data/net.ron`). The mockup should be updated.
- **Placeholders:** the TDM time limit and spawn protection length have no design value yet. Both are marked as
  placeholders in `assets/data/rules.ron`.
