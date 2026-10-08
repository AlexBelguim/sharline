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

## 9. Gun tuning after playtest round 1 (recoil, time to kill, ADS speed, SMG range)
User direction (2026-10-08): recoil is much stronger, the AR's most of all, and recoil control is the skill check;
the AR kills faster; the SMG is weak at range; aiming down sights is much faster. Skipped in the sync test by
`gun_tuning_round_1()` in `design_sync.rs`; pinned in `tests/balance.rs`, `recoil.rs` and `weapon.rs`.

- **Mako damage** 37 → **46** (falloff kept in shape: 46 to 25 m, 38.5 at 50 m, 33.5 from 80 m), **head x1.3 → x1.5**.
  - Lever: the base damage. Death is per zone (head or torso at 0), and limb hits only reach the torso once the
    limb breaks (spill stays as designed), so a body spray kills when enough torso hits land. Through the default
    halo (Mender Scout, 60 shield + 120 HP) that is 5 hits at 37 and 4 from 45 up. Nothing below 45 changes a
    body spray, and the zone, spill and halo rules stay untouched.
  - Bare torso: 4 → 3 hits (AP still never makes it 2; the AP note in section 1 now reads "3-shot").
  - Head x1.5: two head hits through any loadout head arc up to T3 Bulwark within 25 m (was 3), one on a bare
    head at any range (was not past 70 m).
- **Mako time to kill, through the default halo** (10 m, the same out to 25 m; aimed fire is 600 rpm, hip 720):

  | Hit mix | Before: hits, hip / aimed s | After: hits, hip / aimed s | Faster |
  | --- | --- | --- | --- |
  | All torso | 5, 0.33 / 0.40 | 4, 0.25 / 0.30 | 25 % |
  | Body spray (60 % torso, 20 % arms, 20 % legs) | 8, 0.58 / 0.70 | 6, 0.42 / 0.50 | 29 % |
  | Head and torso (every third hit on the head) | 6, 0.42 / 0.50 | 5, 0.33 / 0.40 | 20 % |
  | All head | 2, 0.08 / 0.10 | 2, 0.08 / 0.10 | – |
  | All torso, no halo | 4, 0.25 / 0.30 | 3, 0.17 / 0.20 | 33 % |
  | All torso / body spray at 40 m | 6 / 10 hits | 5 / 8 hits | 20-22 % |

- **Skink (SMG)**: close damage 24 → **36** to 10 m, then a steep drop to **16 at 25 m** and **10 from 40 m** (was
  24 → 13 from 30 m), **head x1.3 → x1.0**.
  - Why the close buff: the harder Mako would otherwise out-kill it up close (it already tied it before). It now
    kills a Scout's torso in 5 hits (0.20 s hip, 0.27 s aimed against the Mako's 0.25 / 0.30) and a body spray in
    8 (0.35 / 0.47 against 0.42 / 0.50) out to 10 m; the Mako wins from 15 m (Skink 0.30 / 0.40 s torso), and from
    25 m the Skink takes at least 1.5x as long, about twice as long through a halo (Scout torso at 25 m: 12 hits,
    0.55 s).
  - Head x1.0 keeps the balance-pass rule that no Skink round one-taps a bare head (RIP III: 36 x 1.2 = 43.2 < 45).
    The SMG sprays bodies; the AR rewards heads.
  - RIP leg-spraying keeps its shape (only RIP is leg-first on bare-legged Medium / Heavy halos, a T2 leg arc still
    blunts it); every count in those pins dropped.
  - Aimed fire stays at 900 rpm.
- **Damage per second by range** (hip fire rate; before → after):

  | Range | Mako | Skink | Warden | Skink / Mako |
  | --- | --- | --- | --- | --- |
  | 5 m | 444 → 552 | 480 → 720 | 128 | 108 % → 130 % |
  | 15 m | 444 → 552 | 425 → 587 | 128 | 96 % → 106 % |
  | 25 m | 444 → 552 | 315 → 320 | 128 | 71 % → 58 % |
  | 40 m | 401 → 498 | 260 → 200 | 128 | 65 % → 40 % |
  | 60 m | 356 → 442 | 260 → 200 | 128 | 73 % → 45 % |

  The Warden is unchanged and stays the long-range pick: two torso hits or one head hit kill through anything up
  to T3, at any range.
- **Recoil** (`recoil_patterns.ron`; the Skink's stays the Mako's x0.6):
  - Mako climb after 10 rounds 4.37 → **8.87°**, after 20 rounds 4.89 → **12.64°** (aimed x0.7: 6.21° / 8.85°). The
    design's pattern went flat after round 10; the new one keeps climbing 0.35° a round, drifts right over the
    first 10, swings left over the next 10, and its loop sways with zero net yaw.
  - Still controllable: pulling down hard to round 8 and gently to round 15, with no sideways correction, keeps
    a 15-round aimed spray on a torso at 15 m (tested with the real hitboxes). Without pulling down the spray
    leaves the torso by round 3.
  - **No recovery mid-spray**: `recover_delay_s` 0.1 → 0.15 (longer than aimed 600 rpm's 0.1 s plus frame
    jitter, so the pattern is the same every time), `recover_frac` 0.6 → 0.5, `recover_deg_per_s` 15 → 20.
  - **Visible view punch**: `view_punch_visual_deg` 0.15 → 0.5 (Skink 0.12 → 0.3), settling over the new
    `view_punch_return_s` (0.07 s; Skink 0.045 s) instead of a hard-coded 2°/s, so every shot reads as its own kick
    and the screen centre is back on the aim before the next shot. Still scaled by the screen-shake setting.
  - The Warden's kick is unchanged (3.5° up, 70 % back in 0.35 s): about a quarter of the 6x scope picture.
- **ADS time** (`ads_s`): Mako 0.22 → **0.13**, Skink 0.18 → **0.11**, Warden 0.38 → **0.22** (8 / 7 / 14 ticks with
  the default optics). Everything on screen follows the sim's ADS blend: camera zoom, viewmodel pose, scope picture,
  crosshair. The projector sight had its own clock: flaps 0.12 → 0.08 s, hologram fade 0.08 → 0.03 s
  (`weapon_models.ron`; it still shows from 80 % ADS), tested to keep up with the fastest build of each gun.
