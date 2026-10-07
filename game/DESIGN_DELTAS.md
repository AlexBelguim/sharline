# Design deltas: where the game deliberately differs from `design/`

`design/systems/data/*.json` is the source of truth for gameplay numbers, and
`crates/vetf_sim/tests/design_sync.rs` fails when `game/assets/data/*.ron` drifts from it. The user has since given
direction that changes some of those numbers and systems. Cloud sessions cannot edit `design/` (it belongs to the
local session), so each change is listed here and skipped by the sync test (`superseded()` in `design_sync.rs`).
Once the design docs and JSON are updated, delete the entry here and in `superseded()`.

## 1. Shields are a buffer; pen is a shield-damage multiplier (ammo = class × type × tier)
- **Design:** a flat `shield_pierce` fraction per weapon bled through the shield to HP (Mako 0.0, Warden 0.3).
- **Now (user direction):**
  - **The shield is a buffer.** While a halo arc holds, it takes the whole bullet, and zone HP takes nothing.
    The bullet that breaks the arc carries its leftover on to HP.
  - **`pen` multiplies shield damage, per halo tier.** pen 2 means the shield takes twice the bullet's damage;
    below 1 means that tier resists the round. Leftover is converted back as `(shield damage − absorbed) / pen`.
- **Ammo** is a **type and a tier** (e.g. AP II) in `assets/data/ammo.ron`, picked **per magazine** (see 5).
  Nothing to sort per round.
  - **Weapon class** sets the baseline pen per halo tier. SMG Standard only slightly beats T1 and nothing above.
  - **Type and tier** scale pen, damage, flesh damage and limb spill:
    - Standard.
    - **AP I-III:** arcs take x1.2 / x1.5 / x1.8 and the round hits 2 / 4 / 6 % harder (kept under the Mako's
      3-shot bare torso).
    - **RIP I-III:** SMG only. Arcs take only 35 %, flesh takes +10 / 15 / 20 %, and a broken limb passes more
      on to the torso (legs 0.84 / 0.95 / 1.0). Spray bare legs, never shields.
    - **Slug I-II:** shotgun only; one heavy projectile (x1.8 / x2.1 damage), shields resist it (x0.8).
    - **Shrapnel:** NPC-only, for bots and bosses later. Low damage, low pen, a seeded chance to slip past
      the shield, and fragments that bleed until treated, after which a 0.1 HP/s trickle per stack stays
      until respawn.
  - **Gear budget:** in team deathmatch, AP is paid for with a loadout gear budget of 13 (`rules.ron`). Halo arc
    tiers plus the gear cost of **every magazine** must fit (AP 2 / 4 / 6, RIP 1 / 2 / 3 per magazine). A Heavy
    halo never carries AP III; the capped Bulwark Juggernaut (13) just fits with Standard rounds. In the
    extraction mode, AP will be expensive or craftable instead.
- **Mako:** Standard has pen 1.0 everywhere, so it still matches the design's numbers exactly (tested against the
  design's Python model).
- **Warden:** loses the 30% bleed-through. Its pen is a flat 1.0: 160 damage already breaks any arc up to 160 in
  one shot, so every design kill breakpoint holds (a torso hit at 30 m on a Volt Line still leaves 60 HP).
  With AP it one-shots light halos (AP II a T2 Mender torso, AP III a T3 one); the gear budget is the brake.
- **SK-9 Skink (new SMG, no design entry yet):** 1200 rpm (900 aimed), 24 damage to 10 m falling to 13 at 30 m,
  40-round magazine, recoil = the Mako's pattern x0.6. It beats the Mako up close against most halos and loses
  clearly past 15 m. The design sync test skips weapons the design does not have.
  - Pinned by `crates/vetf_sim/tests/balance.rs`: RIP leg spraying beats any SMG round to the torso on
    bare-legged Medium / Heavy halos, a T2 leg arc blunts it, Standard and AP stay torso-first.
  - Needs a model with optic and side-rail sockets (art, local session).
- **Pending:** the shotgun's pellets and the light / heavy assault guns.

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
  target takes about as many rifle shots as going through the torso (10 vs 8). The global spill stays as
  designed (user direction); only RIP rounds in the SMG raise it, which makes leg spraying the faster answer to
  bare-legged Medium / Heavy halos (section 1).
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

## 5. Ordered magazines, each with its own ammo
- **Design:** one magazine type per loadout, and the HUD shows spare magazines in the pouch.
- **Now (user direction):**
  - A loadout carries **up to six magazines in slot order**, each loaded with its own ammo (`mags` in
    `rules.ron`'s default loadout, `LoadoutChoice.mags` on the wire). Slot 1 starts in the gun.
  - A magazine always goes back to **its own slot**, so players learn where their good rounds sit.
  - **Tap R:** the next slot in order (wrapping) that still holds rounds. A full magazine ignores a tap.
  - **Hold R:** the magazine radial opens. Release over a slot (or press 1-6) to load it, even from a full
    magazine. Spent magazines are dimmed; nothing shows how many rounds the others hold.
  - The mag check card names the magazine in the gun and its ammo next to the estimate.
  - The HUD no longer shows a spare-magazine count.
  - Each shot remembers its magazine slot, so damage uses that magazine's ammo.

## 6. Rulesets per mode
- **Now (user direction):** `rulesets` in `rules.ron`, replicated in `MatchState.rules`.
  - **Team deathmatch** (gunplay and netcode test bed): per-region shields and health, but **no status
    effects**. There is no bleeding, and a limb at 0 HP carries no broken-limb penalty; it still spills damage
    into the torso. Healing uses only what will be high-end items in the extraction mode: items that heal
    every region or restore every arc at once.
  - **Gun range:** the full extraction rules (bleeding, broken limbs, regional items).
- **Visual impact (UI):** the HUD shows status icons only when the ruleset has them.

## 7. Healing items and the heal ring
- **Design:** no item numbers yet (the HUD mockups show heal states only).
- **Now (user direction):** `assets/data/items.ron`. Every number there is a placeholder.
  - **Whole-body items** treat every region or every arc at once: the trauma kit (HP + bleeding) and the halo
    cell (all arcs). They are high-end in the extraction mode and are **the only items in team deathmatch**.
  - **Region items** treat one region: gauze (bleeding), field dressing (HP + bleeding), arc patch (one arc).
  - **Each mode hands out a kit** (`kits` in `items.ron`). Validation refuses a region item in a mode whose
    rules forbid them.
  - **Heal ring (H):** click an item. A whole-body item is used at once. A region item opens a second ring of
    regions around it (head up, torso right, legs down, arms left); click the region. Right click steps
    back. Options that would do nothing are dimmed.
  - **Using an item:**
    - It lowers the gun for `use_s` and slows you (`use_move_mult`).
    - Firing, aiming, reloading or sprinting cancels it and keeps the item.
    - The gun then takes as long to come up as after a sprint.
    - The use is predicted like the weapon; the host applies the effect when it finishes.

## 8. Small things that are not changes, but worth knowing
- **Port:** the host-game mockup (`design/ui/mockups/png/04b_main_menu_host.png`) shows UDP port 7777, while the
  network diagram uses 47820. The game uses **47820** (`assets/data/net.ron`). The mockup should be updated.
- **Placeholders:** the TDM time limit and spawn protection length have no design value yet. Both are marked as
  placeholders in `assets/data/rules.ron`.
