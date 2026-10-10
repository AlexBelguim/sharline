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
  - **Points:** in team deathmatch and free-for-all, AP and RIP are paid for with loadout points (section 13):
    the ammo type's `gear_cost` (AP and RIP I / II / III: 1 / 2 / 4) is paid **once**, next to the armor tier
    and the magazine type, against a total of 8. T4 armor never carries a tier III round. In the extraction
    mode, AP will be expensive or craftable instead.
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
  and the small base spread. **Superseded by section 12:** standing still there is no base spread either.

## 5. Ordered magazines, each with its own ammo
- **Design:** one magazine type per loadout, and the HUD shows spare magazines in the pouch.
- **Since 2026-10-08** this is the gun range's: in team deathmatch and free-for-all everyone carries six
  magazines of one picked type, all with one ammo type (see 12).
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

## 10. Aim on the move: auto-sprint, aiming never slows you, slides from a run
- **Design:** aiming slows you (`move_mult_ads`: Mako 0.6, Warden 0.45) and ends a sprint; aimed spread still grows
  with movement (`spread_deg.move_full_ads`), the Warden's scope is unsettled while moving (`ads_unsettled` 3.0), the
  jetpack forbids aiming (`jetpack.ads_allowed` false), and a slide needs 5.5 m/s (`slide.min_entry_speed`, a full
  sprint).
- **Now (user direction 2026-10-08):**
  - **Auto-sprint is the default:** moving forward sprints, Shift held walks (Sprint moved to Alt, for players who
    turn auto-sprint off). Walk and Hold breath share Shift.
  - **Aiming and firing never slow you or end a sprint.** `move_mult_ads` is gone (attachments' `ads_move` no longer
    applies either). A sprinting player can fire, aim and mag-check: the gun comes up from the sprint pose in the
    gun's `sprint_to_fire_s` and the player keeps their speed. A trigger pull while it comes up fires once it is
    up, and after a shot the gun stays up `speed.sprint_gun_hold_s` (0.6 s) before a sprint lowers it again.
  - **Aimed shots are accurate in every movement state:** fully aimed (from 90 % ADS progress), every gun has its
    `ads_still` spread running, sprinting, sliding, in the air, on a zipline or a jetpack. `move_full_ads` and
    `ads_unsettled` are gone; the movement, air, slide, zipline and jetpack spreads are hip-fire penalties only.
    This replaces the `ads_first_shot` rule of section 3. ADS bloom while moving stays. **Section 12** refines
    this: aimed and standing still there is no spread at all, and on the move a small aimed bloom (at most 0.2° on
    the Mako and Skink, 0.1° on the Warden) keeps every aimed shot on a head at 25 m (Warden: 50 m).
  - **ADS works in every movement state** but a mantle (the hands are on the ledge): `jetpack.ads_allowed` is true.
  - **Slides start from a normal run:** `slide.min_entry_speed` 4.0 (jog 4.8, walk 2.6), moving within
    `slide.entry_max_angle_deg` (60°) of the facing, so a crouch while strafing or backpedalling only crouches.
    Section 12 scales the 4.0 with the halo weight and the gear, so every loadout slides from its own run.
  - **Keys:** Heal is B and Fire mode H (section 7's "Heal ring (H)" is now B). The default crosshair is a small plus
    (2 × 4 px arms, 2 px gap). Saved settings files move to the new defaults once, where they still hold the old
    ones (`settings.ron` version 1).
- **Design follow-up (local session):** `weapons.slice.json` (drop `move_mult_ads`, `move_full_ads`,
  `ads_unsettled`) and `movement.slice.json` (`min_entry_speed` 4.0, `ads_allowed` true), then delete the
  matching lines in `superseded()`.

## 11. Free-for-all deathmatch (2026-10-08)
- **Design:** the slice has team deathmatch only.
- **Now (user direction: "i want a free for all deathmatch"):** a second match mode on Showhome, through the same
  host / lobby flow (HOST GAME's MODE, the lobby's match settings, `--mode ffa`).
  - Everyone against everyone: no teams, damage between all players, every other player drawn as an enemy.
  - `ffa` in `rules.ron`: first to **25 kills**, 10 min, **3 s respawn**, 1.5 s spawn protection, **8 players**,
    one magazine refilled per kill, the TDM gear budget. All placeholders, like the TDM ones. Its ruleset has the
    same switches as team deathmatch (no bleeding, no broken limbs, whole-body items only), and it hands out the
    deathmatch healing kit.
  - Spawns: any spawn of either side; among those within `spawn_slack_m` (6 m) of the farthest from living
    enemies, one at random.
  - The winner has the most kills; a tie goes to fewer deaths, then to whoever reached that score first.
- No design JSON covers match rules, so the sync test has nothing to skip.

## 12. Recoil and bloom after playtest round 2 (2026-10-08)
User direction (DIRECTION_LOG 17, with 16's "aimed shots are accurate in every state"): a fixed pattern with no
randomness standing still, Apex-style random bloom on the move, and moving never better than standing still.
Skipped in the sync test by `recoil_and_bloom_round_2()`; pinned by the tests in `weapon.rs` and `tests/balance.rs`.

- **Standing still** (on the ground under `spread_deg.move_threshold_frac` 0.1 of jog speed = 0.48 m/s, any stance):
  **no random spread, hip or aimed.** Every shot goes where the view points, and only the gun's fixed recoil moves
  the aim, so two sprays are identical for every player, seed and time. The first aimed shot is exact.
  - Gone: `hip_still` (Mako 0.7°, Warden 6°), `ads_still` (0.08°, 0°), `bloom_per_shot_ads`, the design's 0.3 / 0.2
    threshold. The Warden's kick is fixed: `kick_yaw_rand_deg` 0.4 (random) → `kick_yaw_deg` 0.2 (always right).
  - The Mako and Skink patterns are unchanged (section 9). A crouch lightens the pattern (x0.9) only standing still.
- **Moving** adds a random cone on top of the same pattern, seeded by player and shot number (client and host agree).

  | Hip cone (°) | walk | jog | sprint | slide | zipline | jetpack | air | sustained fire |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | Mako | 1.2 | 2.6 | 3.0 | 3.0 | 3.0 | 3.0 | 4.0 | +0.12 a shot, up to +1.6 |
  | Skink | 1.0 | 2.6 | 3.0 | 3.0 | 3.0 | 3.0 | 4.0 | +0.072 a shot, up to +1.6 |
  | Warden | 4.0 | 8.0 | 9.0 | 9.0 | 9.0 | 10.0 | 9.0 | – |

  - Linear in speed between `walk_hip` (new), `move_full_hip` and `sprint_hip` (new); the slide, air, zipline and
    jetpack values are floors, at least a sprint's (design: Mako slide 1.8, zipline 2.0; Warden air 8, slide 6,
    zipline 6). Crouched x0.85. Sustained fire adds `bloom_per_shot_hip` x how much you move; it settles at 3°/s after
    `bloom_decay_delay_s` 0.15 s (design 0.08, shorter than the Mako's fire interval, so it barely built).
  - Aimed: the cone x `ads_move_mult` (new: 0.04, Warden 0.01) plus the bloom x `bloom_max_ads / bloom_max_hip`
    (`bloom_max_ads` 0.8 → 0.04). At most 0.2° (8.7 cm at 25 m) on the Mako and Skink, 0.1° (8.7 cm at 50 m) on the
    Warden: aimed shots on the move stay on a head.
  - The data check rejects any tuning where moving could beat standing still or a faster state is tighter: hip cones
    0 < walk ≤ jog ≤ sprint ≤ every floor, `ads_move_mult` in [0, 1], `bloom_max_ads` ≤ `bloom_max_hip`.
- **Crosshair:** opens by the live random cone: the plain cross for every gun standing still (they are exact there),
  the real cone on the move (the Warden's hip cone widest). This replaces "over the resting hip spread".
- **Raise from a sprint:** with aim held the raise takes no longer than the ADS, so an aimed shot never waits once
  aimed. `sprint_to_fire_s` Mako 0.2 → 0.12, Skink 0.15 → 0.10, Warden 0.32 → 0.20. A raise shortened by aim stays
  short if aim is let go (at most 1-2 ticks sooner for a hip shot with the fastest-aiming parts; accepted).
- **Trigger on the run:** an empty gun clicks on the pull itself; a pull during a bolt cycle is dropped, as standing
  still. **Slides:** `slide.min_entry_speed` 4.0 scales with the halo weight and the gear (not items or wounds), so
  every loadout slides from its own jog. **ADS MOVE** (`ads_move`) is gone from attachments and the loadout;
  protocol 7, together with section 13's agent.
- **Balance tests:** the aimed Mako spray at 15 m used the 0.08° `ads_still` cone; it is now exact standing still.
  New: `aimed_shots_on_the_move_hit_a_head` (real hitboxes, 512 seeds, every moving state, full bloom).
- **Design follow-up (local session):** in `weapons.slice.json` drop `hip_still`, `ads_still`, `bloom_per_shot_ads`,
  `kick_yaw_rand_deg`; add `walk_hip`, `sprint_hip`, `ads_move_mult`, `kick_yaw_deg`; take the new threshold, floors,
  bloom and `sprint_to_fire_s` values. In `attachments_stats.slice.json` drop `ads_move`. Then delete
  `recoil_and_bloom_round_2()` and the `ads_move` line in `superseded()`.

## 13. Deathmatch loadout: picks and points, a random agent (2026-10-08)
- **Design:** the Loadout screen (mockups 05 / 05b) picks an agent, a halo core and a tier per arc, and ammo per
  magazine for up to six magazines, priced magazine by magazine against the budget.
- **Now (user direction, DIRECTION_LOG 17):** team deathmatch and free-for-all share one loadout rule,
  `deathmatch_loadout` in `rules.ron`. A player picks the gun, its attachments and its **magazine type**, then
  **one armor tier** and **one ammo type**, and pays points for the three against the mode's `gear_budget`.
  - **One armor tier (T1-T4)** for the whole halo. A tier is a fixed combination of the existing arc tiers (no
    new armor, no new art; the halo shows the arcs as before):

    | Tier | Head / torso / arms / legs | Tier points | Weight class | Points |
    |------|----------------------------|-------------|--------------|--------|
    | T1   | 1 / 1 / 1 / 1              | 4           | Light        | 1      |
    | T2   | 2 / 2 / 2 / 2              | 8           | Medium       | 2      |
    | T3   | 3 / 3 / 1 / 1              | 8           | Medium       | 3      |
    | T4   | 4 / 4 / 3 / 2              | 13          | Heavy        | 5      |

    T4 is every arc at its `loadout_tier_caps`, the best combination a loadout allows. Validation keeps every
    tier within the caps, a new combination, and no cheaper than the tier below.
  - **One halo for everyone:** `halo_core: Mender`, no core pick. Of the four cores its special is only numbers (its
    regen table); Volt's break pulse slows, Phase is immune to slows and Bulwark cuts flinch, ability-like effects
    these modes leave out. It is also the default loadout's core, so time-to-kill stays where playtest round 1
    tuned it.
  - **Six magazines of the picked type** (`mags: 6`), all loaded with the **one ammo type**. The magazine type is
    the gun's `mag` attachment: Mako `mag_30` / `mag_45` / `mag_drum60`, Warden `mag_5` / `mag_8`, Skink
    `skink_mag_40` / `skink_mag_60`.
  - **No agent pick:** these modes have no abilities (everyone keeps the jetpack). The host deals every player a
    random agent from `agents.ron` when the match goes live: one roll per player from the match's seed (the tick
    it went live) and the player id, kept for the whole match, dealt to late joiners on arrival, dealt again on
    RESTART MATCH and taken back in the lobby. `PlayerAgent` is replicated (`PROTOCOL_VERSION` 7, together with
    section 12's ADS MOVE removal). The agent is cosmetic today: it shows on the scoreboard's and the lobby's badge
    (`?` until dealt) and on the ESC card (`Random agent` before the start). The gun range keeps the agent pick.
- **The point table** (all in data: armor in `deathmatch_loadout.armor`, magazines in `mag_points`, ammo is
  `gear_cost` in `ammo.ron`, the total is `gear_budget`):
  - Total **8** in both modes.
  - Armor T1 / T2 / T3 / T4: **1 / 2 / 3 / 5**.
  - Ammo, paid **once** for all six magazines: Standard **0**, AP I / II / III **1 / 2 / 4**, RIP I / II / III
    **1 / 2 / 4** (Skink only).
  - Magazine: each gun's standard magazine **0**, extended (`mag_45`, `mag_8`, `skink_mag_60`) **1**, drum
    (`mag_drum60`) **2**.
  - What it buys: T1 and T2 fit any ammo with any magazine (T2 + AP III + drum is exactly 8). T3 fits any ammo
    with a standard or extended magazine, and the drum up to a tier II round. T4 never fits a tier III round
    (5 + 4 = 9); it fits a tier II round with a standard or extended magazine, and the drum with Standard or a
    tier I round. Every gun fits every tier with Standard ammo and any magazine. The best gun does not change
    this: guns cost nothing, so no gun, T4 and the best ammo fit together.
  - Why these numbers: the notes started from a total of 9 with armor 1 / 2 / 4 / 6. T3 is 3 / 3 / 1 / 1, the
    same tier points and weight class as T2, so its price sits one point above T2 rather than two. Taking one
    point off T3, T4 and the total keeps exactly the same set of loadouts that fit, with smaller numbers.
  - Pinned by tests: `vetf_sim::gear` (every gun, magazine and round), `tests/balance.rs` (`deathmatch_points`)
    and the host's checks in `server.rs`.
- **The host** shapes every loadout it receives (`LoadoutChoice::shaped`): its halo becomes an armor tier on the
  one core (its own tier, else the highest tier whose torso is no higher than its best head or torso arc), and
  it gets six magazines of slot 1's ammo. It refuses an unknown gun, no magazine or more than six, a halo arc
  above its cap, ammo the gun cannot load, misfit or doubled attachments, and anything over the points. The
  `LoadoutChoice` message keeps its fields.
- **The screen:** the gun and its attachments, where the MAG card is the magazine pick (it reads `MAG ×6`; its
  popover says "YOU CARRY 6 · ALL WITH YOUR AMMO"; no separate MAGAZINE row, user: "the one you select is just
  what you get"); then ONE ARMOR row (NO HALO, T1-T4 with weight class, arcs and points), ONE AMMO row, and the
  points used / total split into armor, ammo and magazine. Every pick shows its points all the time: each
  attachment card shows what it holds (`2 PTS`; a muted `FREE` for anything that costs nothing), every option in
  the popovers, every armor and ammo card; the top bar always shows `POINTS n / 8` (red when over, CONFIRM off).
  A card's points turn red when picking it would push the loadout over the total. Q / E and the arrows walk gun
  -> attachments (MAG among them) -> armor -> ammo -> BACK / CONFIRM. The main menu has no LOADOUT entry for now; the
  lobby's LOADOUT and the ESC menu open the screen. A loadout confirmed in the lobby is worn at once.
- The HUD's vitals header reads `HALO / MEDIUM` (the weight class tells halos apart); the lobby's match settings
  list the mode's loadout rule and that agents are random.
- **The gun range** keeps the full screen (agent, core, a tier per arc, ammo per magazine, no budget).
- Presets saved before (`loadouts.ron`) load unchanged and open in these modes as their nearest picks (an armor
  tier, slot 1's ammo in six magazines, the gun's magazine type); a preset this build cannot read is replaced by
  the built-in one in its letter.

## 14. Low gaps: a slide that stops under one stays low (2026-10-08)

- The design has three stances (stand, crouch, slide) and a slide that ends drops to a crouch. Some gaps are
  lower than a crouch (1.25 m): the jammed garage rollers and the office shutters are 1.1 m. A slide that stopped
  under one put the player in a crouch that did not fit, and the controller pushed them up through the lintel.
- Now every stance change picks the tallest stance, up to the wanted one, that fits: stand, then crouch, then
  the slide's low stance (1.0 m). A slide that stops under a low gap leaves the player low on the floor there,
  moving at crouch speed, until there is room to crouch or stand. No new numbers.
- The step-up for small ledges tries its full `step_height` first, then halves of it. Under the roller's lintel
  the full lift ran the head into the lintel and stopped the slide dead on the 2.8 cm doorway threshold; a
  smaller lift clears the threshold and the slide carries on.
- Pinned by `vetf_sim::movement` tests (a lintel, crouch released or held, a slide off a ledge under a low
  ceiling) and `maps::showhome` (`slide_stopped_under_the_garage_roller_stays_low`: slides into both rollers that
  stop at every point along the way).

## 15. The AR's recoil is a T; stocks take the climb, grips the sweep (2026-10-08)
User direction (DIRECTION_LOG 18): "recoil of ar should be more like a T with no special stocks", and "stocks and
front grips will then each lower the vertical or horizontal recoil". Skipped in the sync test by
`recoil_roles_round_3()`; pinned by `recoil.rs` (`the_mako_pattern_is_a_t`), `weapon.rs`
(`mako_attachments_scale_the_t_per_axis`, `the_mako_climb_is_pinned`) and `data.rs`
(`stocks_lower_the_climb_and_grips_the_sweep`).

- **The user's tune after testing it (2026-10-09, standard stock, no grip):**
  - a 15-round stem: kicks 1-14 go straight up, 15.65° in all;
  - about 70 % more total climb: 17.6° over a 30-round mag, against 10.3° before;
  - a 60 % wider bar: right +4.16° over kicks 15-20, then sweeps of ±8.32° looping from kick 21.

  The first version below is kept for the record.
- **Tapping: the pattern rewinds gradually (item 9c, 2026-10-09).** It used to jump back to the first bullet after
  0.3 s without a shot, all or nothing. The user asked for a shorter reset that does not make macro tapping a laser,
  and chose a gradual one. Now, after a shot:
  - within the gun's aimed fire interval (Mako 0.1 s, Skink 0.067 s) nothing rewinds, so a held spray, or taps as
    fast as one, follows the pattern exactly;
  - after that the pattern rewinds in proportion to the pause and is back at bullet 1 `reset_after_s` after the
    last shot (weapons.ron: Mako 0.25 s, Skink 0.22 s, was 0.3 s for both). Half the rewind takes the place about
    halfway back, rounded up: a 15-round Mako stem paused 0.15 s continues at bullet 11, 0.2 s at bullet 6;
  - so taps `reset_after_s` or more apart (about 4 a second on the Mako) always fire the first bullet, which is
    exact standing still; faster taps settle near the start (Mako tapped 0.2 s apart: bullet 2, 0.15 s: bullet 3,
    0.12 s: bullet 9) and never get further than a held spray of as many shots;
  - it is counted in whole ticks and integers (`WeaponState::pattern_pos`), so the predicting client and the host
    agree exactly. The Warden has no pattern; its bolt (1.25 s) is slower than any rewind anyway.

  Pinned by `weapon.rs` (`the_pattern_rewinds_by_elapsed_time`, `slow_taps_are_always_bullet_1`,
  `fast_taps_never_get_further_than_a_held_spray`, `a_pause_mid_spray_rewinds_part_of_the_pattern`,
  `the_rewind_is_deterministic`); the data check wants `reset_after_s` longer than the aimed fire interval.
  Skipped in the sync test (`reset_after_s`); design follow-up: port the 0.25 / 0.22 s and the rule.
- **Mako pattern, first version** (`recoil_patterns.ron`, standard stock, no grip; hip degrees, aimed x0.7):
  - The stem: kicks 1-9 go straight up (no yaw), 8.8° in all, so rounds 1-10 stack in one column. After 10 rounds
    the climb is 9.1° (round 2: 8.87° with a small wiggle).
  - The bar: the climb flattens (0.3° a round falling to 0.05°) and the gun sweeps right over rounds 11-16
    (+2.6°), left across over 17-24 (−5.2°), right again over 25-32 (+5.2°). Past kick 31 it loops the two full
    sweeps (`loop_from_index` 20 → 15), so a 45 or the 60 drum keeps sweeping the same ±2.6° bar, centred on the
    stem. The bar rises 1.5° over a 30 and 3° over a drum (round 2 kept climbing 0.35° a round: 15.8° at 30
    rounds, now 10.3°). The total climb is lower; the skill check moves to the sideways control.
  - The Skink keeps the round-2 column x0.6 (the T is the AR's alone), so it is no longer "the Mako's x0.6".
- **Recoil roles** (`attachments.ron`): a stock only sets `recoil_v`, an under-rail part only `recoil_h`; the data
  check rejects anything else. Every stock and grip lowers its axis by its own amount and pays elsewhere:

  | Part | design | now |
  | --- | --- | --- |
  | Mako PRECISION stock | V 0.9, H 0.9 | V 0.6 (ADS x1.1, sway 0.8, move 0.98) |
  | Mako LIGHT stock | V 1.12, H 1.12 | V 0.78 (ADS x0.88, sway 1.15, sprint-to-fire 0.85) |
  | Warden FOLDING stock | V 1.1 | V 0.85 (ADS x0.9, sway 1.25, move 1.03) |
  | VERTICAL GRIP, now **BRACE GRIP** | V 0.88 | H 0.55 (ADS x1.03, new sway 0.95) |
  | ANGLED GRIP | H 0.94 | H 0.7 (ADS x0.92) |
  | STUB GRIP | H 0.95 | H 0.82 (hip spread 0.88, sprint-to-fire 0.9) |

  The "now" column is the 2026-10-10 strength (section 39); round 3 shipped V 0.8 / 0.92 / 0.95 and H 0.78 / 0.88 / 0.94.
  `grip_vertical` keeps its id (its model and saved loadouts); only its name and blurb changed. The front shield
  keeps its H 0.95 (it is not a grip). The Skink has no stocks or grips. The bipod's deployed bonus is unchanged.
- **Balance tests:** the learned-pull test now runs 20 aimed rounds at 15 m and pulls against the sweep too (in
  straight lines between the turning points); pulling down only, the sweep leaves the torso, so the bar needs real
  sideways control. The stat text test reads RECOIL H for the grips and RECOIL V for the stocks.
- **Design follow-up (local session):** port the T pattern and `loop_from_index` 15 into
  `mako_recoil_pattern.json`, the recoil roles into `attachments_stats.slice.json` (and the Skink's note in the
  weapons doc), then delete `recoil_roles_round_3()`.

## 16. A NO HALO armor pick in team deathmatch and free-for-all (2026-10-08)
User direction (DIRECTION_LOG 18): "A NO HALO armor option for 0 points." Section 13's armor pick gains a first
option before T1.
- **Data** (`rules.ron` `deathmatch_loadout.no_halo_points: 0`): NO HALO is armor tier 0. Every arc is 0, so the
  weight class is None and movement uses armor.ron's fastest `weight_effects` row (move 1.0, slide boost 2.0, no
  power drain). The data check rejects a NO HALO that costs more than T1.
- **Host:** a halo with every arc 0 stays NO HALO when it is shaped (`tier_for`). Before this change it became T1.
  A halo with arcs but no head or torso arc still becomes T1. Older saved loadouts that had no halo now open as
  NO HALO.
- **Look:** no arcs are drawn over the head (the gun range's `arm_none` also no longer draws four dark arcs). The
  HUD's shield strip is empty and its header reads NO HALO. The Loadout card reads NO HALO / FREE / NONE / no
  shield. The ESC card and player tag read "No halo".

- **Impacts: no bullet marks on lawns.** Shots into the mown lawn (`M_GND_Grass`, listed in `no_mark` in
  `impacts.ron`) throw their soil debris but leave no mark: the grass hid marks up close and they popped in
  beyond its fade distance. The user: "no bullet marks on lawns is fine".

## 17. Walls while sliding: the eye and a stuck body stay out of them (2026-10-08)

- The eye eased down toward a slide's height (0.85 m) over `eye_height.transition_s`, slower than a slide carries
  the head under a garage roller (1.1 m), so the view (and the shots, which leave from the eye) came from inside
  the lintel for a moment. The eye now stays `eye_height.clearance` (new, 0.08 m) from walls and ceilings: under a
  low gap it is held down to the open space there. Data validation checks every stance's eye sits that far inside
  its box.
- A body that was somehow inside something used to be nudged up 1 cm a tick, which carried a player stuck under a
  lintel up through it. Now it first goes lower (crouch, then the slide's low stance), else it steps out the
  shortest way, rising or dropping at most a `step_height` (out of a floor, never through a lintel or a floor).
- A mantle's move over the ledge starts while the body is still rising; it is now traced, so it no longer cuts
  through the ledge's edge (it catches up as the body rises; the mantle's time and end point are unchanged).
- The camera's render-only offsets (the step ease, bob, landing dip, a shot's push back, between ticks) only move
  the view as far as the eye's clearance box fits. The near plane is 2 cm (was 3 cm), so its corners stay inside
  that box at the widest FOV on a 32:9 screen.
- Pinned by `vetf_sim::movement` tests (slides into a wall head-on, at shallow angles, along it and into a corner;
  the eye under a lintel; a body inside a ceiling), `collision::push_out_*`, and `render` tests (the camera on
  Showhome's garage rollers with exaggerated offsets; the near plane's reach).

## 18. Ziplines end clear of the pylons (2026-10-08)
The user: "you no clip in the pillar of the zip if you don't jump off". Showhome's cable is anchored in the middle
of each pylon mast, and a ride to the end used to stop with the rider hanging inside the mast.
- A ride now ends `capsule.radius + zipline.end_clearance` (new, 0.35 m: 0.67 m in all) short of each anchor. The
  hanging body is also swept along the cable each tick, so a ride ends just short of anything solid on the line
  (a wider pylon, a wall). The rider then hops off as before, onto the pylon's pad on Showhome.
- A grab hangs the rider at the nearest clear point within that span (up to 2 m away). With no clear point, the
  grab fails.
- Pinned by `vetf_sim::movement` tests (a cable between two pylons, a beam across the line, jumping off near the
  end) and map tests that ride Showhome's cable to both pylons and the range's S5 line both ways.

## 19. The sensitivity import box applies when committed (2026-10-08)
The user asked whether the sensitivity setting works. The whole path checks out (cm/360 and DPI to the in-match
look, every frame with no smoothing or frame-time scaling; per-optic ADS multipliers; invert Y; saved to
`settings.ron`; a change from the match's Esc menu applies on resume). One trap: a sensitivity typed into
MOUSE & AIM's "Import from another game" box only took effect after APPLY, and was dropped when the screen closed.
- Enter, or a click away from the box (DONE, BACK, another control), now converts it to cm/360 at once. APPLY
  still works the same.
- Pinned by `settings::controls` test `a_typed_import_sensitivity_sets_the_turn_without_apply`.

## 20. A death screen, and RESPAWN instead of an automatic respawn (2026-10-09)
The user: "a death screen you can see where you get shot from (death cam but dont replay your death) a loadout
button and an respawn button with the timer and it show how much dm you take where and how much dm you gave and
where". After `design/ui/mockups/death.html` (mockup 10), with these differences:
- **Respawn rule:** the host used to respawn a dead player as soon as `respawn_s` ran out. In a live match it now
  waits for the death screen's RESPAWN (active once the timer is out); a player who never presses it is
  respawned anyway `auto_respawn_s` later (new in `rules.ron`, 10 s in team deathmatch and free-for-all; the
  gun range follows team deathmatch). Resets (RESTART MATCH, back to the lobby, a team switch), deaths in the
  lobby and the end of a match still respawn on the timer alone.
- **Death cam, no replay:** the view stays at your eye where you died and turns smoothly to your killer's live
  position while you can see them, else the last spot you saw them at, else where the killing shot came from,
  and zooms in to frame them (`death_screen.ron`).
- **Killer card:** name, gun, the killing shot's distance, and their health and halo as pips and a word
  (Healthy / Hurt / Critical; Full / Cracked / Low / Broken) plus the halo's tier and weight class. The mockup's
  exact shield and HP numbers are left out on purpose.
- **Recap:** one row per player and direction (damage you took, damage you dealt) for the life that ended:
  hits per zone, damage to the halo and to health, the distance of the last hit. The mockup's per-hit timeline
  is folded into these rows (a recap, not a log). The host records every accepted hit and sends the recap to the
  player who died (`LifeRecap`, protocol 8; again if a shot they fired before dying lands while they are dead). Replaced by section 24.
- Pinned by `vetf_net::recap` tests (per zone, shield apart from health, several attackers, a new life), the
  server's `respawn_waits_for_the_player_then_falls_back`,
  `a_death_waits_for_respawn_with_a_recap_then_starts_a_new_life` and
  `a_life_recap_reaches_the_host_and_only_the_dead_player`, and `death` tests (the death cam's target, turn and
  zoom, line of sight, the rough reads, the layout).

## 21. Loadout edits apply without CONFIRM (2026-10-09)
The user: "after loadout changes you should not have to press confirm, this can be replaced with the respawn
button with timer if dead, just confirm when still alive is fine but just esc should also work if not above
point limit".
- **Alive** (menu, lobby, a match where it applies at the next spawn): CONFIRM still applies; Esc and BACK now
  apply too when the picks are within the points (they used to discard). Over the points the first Esc shows
  "Over the points: fix it, or press Esc again to discard" and a second Esc on the same picks discards them.
- **Dead** (the Loadout screen over the death screen): no CONFIRM. Each valid edit is saved and sent to the host
  as it is made, so the host's fallback respawn takes it too; CONFIRM's place is RESPAWN with its timer, which
  also respawns. Over the points RESPAWN reads OVER THE POINTS and is blocked until fixed (rather than spawning
  you with the last valid loadout, which would not be what the screen shows); the fallback respawn still comes
  with the last valid one. The host's check of every loadout is unchanged.
- Pinned by `loadout::apply` tests (Esc within / over the points, the double-Esc discard, edits applied as made
  while dead, the RESPAWN button's states).

## 22. Test bots for solo testing (2026-10-09)
The user: "after death screen could you add a simple and quick bot so i can solo test, maybe add bot button in the
lobby screen, just a stationary that aims at my head when in sight is fine". Not in the design docs (they plan no
AI players in the slice); a testing aid:
- **What a bot is:** a player the host simulates like its own, with no client, link or process (`src/bots.rs`; the
  `--bot` client mode is unchanged). It takes a seat (bots count against MAX PLAYERS; ADD BOT needs a free one),
  but gives it up to a joiner (see "Bots give up their seat" below), joins the team with fewer players in team deathmatch, is named BOT 1, BOT 2,
  ..., plays `rules.ron`'s default loadout, is always READY, and presses RESPAWN as soon as the timer allows.
  The lobby, the scoreboard and the replicated `PlayerInfo` mark it as a bot (protocol 9).
- **What it does:** stands still where it spawned; once an enemy's head has been in its line of sight within
  `range_m` for `reaction_s`, it turns toward the head at `turn_deg_per_s` with an aim error of up to
  `aim_error_deg` (rolled per burst) and fires in bursts when its view is on the aim point, with the normal fire
  rate, recoil (the kick turns its view, it pulls back at its turn speed), magazines and reloads (when the
  magazine in the gun is empty). Never in the lobby or after the match has ended. Numbers: `assets/data/bots.ron`.
- **Its hits:** it has no client to claim them, so the host claims for it (the first enemy body on the shot's
  line, as the host sees everyone now) and the claim goes through the normal check and damage, so halos, kill
  credit, the kill feed and the death screen's killer and recap all work. Its hit confirms and its own recap have
  nowhere to go and are dropped.
- **Lobby:** the host gets ADD BOT (while a seat is free) and REMOVE BOT (the last one added, while there is a
  bot); `--bots N` adds N when the game is up.
- Pinned by `vetf_sim::bot` tests (in sight / out of sight / out of range, reaction, turn speed, bursts, recoil,
  semi-automatic pulls, reloads, the aim error), the server's
  `a_bot_shoots_through_the_normal_path_scores_the_kill_and_respawns` and
  `bots_take_seats_on_the_smaller_team_and_hold_fire_in_the_lobby`, and `bots::tests`.
- **Bots give up their seat (2026-10-09, the user: "make bot give up automatically"):** a player joining a full
  lobby or match in progress is never turned away while a bot holds a seat: the host removes a bot and the joiner
  takes its seat. In team deathmatch the bot comes from the team the joiner goes to (the smaller one, team A on a
  tie), else from the team with more bots, and the joiner then takes the smaller team, so the sides stay even; in
  free-for-all any bot. The most recently added bot goes first (a new `Bot::added` order; REMOVE BOT uses it too,
  since numbers are reused). The netcode's seat check counts players only, so it lets the joiner through; the
  removed bot leaves everyone's lobby list and scoreboard as a leaving player does. Only players in every seat
  still mean "server full". Rules: `bots::seat_joiner`; pinned by its tests and the server's
  `a_full_tdm_lobby_makes_room_by_dropping_a_bot` and `a_full_match_in_progress_drops_its_latest_bot`.

## 23. Variable scopes and a 1-3x optic (2026-10-09)
The user: "i would like the 6x 12x be for min 6 to 12 and scroll should be gradual from 6x to 12x and the scope
should remember per player and per different scope setting, lets also add 1x 3x and both should be a thin line
cross". The design's sniper scope toggles 6x / 12x (`attachments_stats.slice.json` optic_sniper `other`):
- **Variable zoom:** an optic's `zoom` in `attachments.ron` is a number (fixed) or `[min, max]` (variable). Aimed
  through a variable one, Zoom in / Zoom out (new binds, the wheel by default) move the wanted zoom evenly in
  ratio (`notches_per_range` wheel notches cross the range; a held key `key_notches_per_s`), and the view eases
  toward it (`ease_per_s`, frame-rate independent): gradual, never stepped. Tuning: `settings.ron` `scope_zoom`.
  The Warden's scope is now 6-12x (`6–12× SCOPE`), starting at `zoom_default` 6x.
- **New optic `optic_1_3x` (1–3× VARIABLE):** an extra pick on the guns the 3x fits; the fixed 3x stays. At 1x it is
  a 1x sight seen through its scope picture. In team deathmatch and free-for-all it costs 1 point
  (`rules.ron` `optic_points`, a new price list next to `mag_points`; the 3x and every other optic stay free). It
  wears the 3x's model with a brass body tint (`weapon_models.ron` `tint`) until the art side models a
  low-profile 1-3x (`assets/weapons/attachments/optics/build_optics.py`). Its ADS multiplier shares the 3x's row.
- **Memory:** each player's last zoom per variable optic is saved in their own `settings.ron` (`optic_zoom`) and
  restored when they aim with it again, also after a restart. RESET ALL keeps it.
- **Reticle:** both variable scopes draw a thin line cross (a 1 px dark line on a 3 px pale halo, screen pixels, so
  the same at every zoom); the posts and mil dots are gone.
- **Local only:** the live zoom narrows the aiming player's own camera (still blended by the ADS) and their
  sensitivity follows it (MATCH FOCAL; the per-optic ADS multiplier still applies). Shots, the simulation, the wire
  (no protocol change) and what others see are unchanged. Aimed through a variable scope the zoom binds take their
  inputs, so wheel down zooms out instead of jumping (Jump and the zoom binds may share the wheel).
- Pinned by `scope_zoom` tests (steps, clamps, easing, binds, the file round trip, sensitivity at 6x vs 12x, 1x
  view), `client::aimed_through_a_variable_scope_the_wheel_zooms`, `data::variable_optics_have_a_zoom_range`,
  `gear::the_variable_optic_costs_more_than_the_fixed_3x`, `loadout::model::the_variable_optic_is_a_priced_pick`
  and the `weapon_models` reticle and tint tests.

## 24. The death recap per opponent life, and assists and KDA (2026-10-09)
The user, on the first death screen: "so damage you dealt should not be across lives? should show total kills and
can we make it more visual like the kill per headshot or other, and then if you die the guy you dm in the last 5sec
... with a silhouette or something, total dm and shield dm not remaining health, and leave out the per body part
one, can the tab show assist and kda". The recap of section 20 changes:
- **Per opponent life:** the host numbers each player's lives; your damage to an opponent is one encounter per life
  of theirs, so an opponent who died and came back during your life is never summed into one row (the "BOT 1 ...
  1230 health" row).
- **No per-zone columns.** The recap now shows, for the life that ended: KILLS / HEADSHOT KILLS / DAMAGE DEALT
  tiles; KILLS THIS LIFE as one icon per kill (the headshot mark, or a body for any other kill, bleed-outs
  included) with the victim's name; YOUR LAST FIGHT, a card for each opponent you hit in the last `last_fight_s`
  (5 s, `death_screen.ron` `recap`) before you died and did not kill, with a silhouette lit where you hit them
  (brighter for more hits, no numbers), their name and gun, your total damage and the part of it their halo took
  (never what they have left); DAMAGE YOU TOOK per attacker as a bar (your halo's part first) with their gun,
  the total, the shield part and the distance. A shot or kill that lands after you died (a trade) re-sends it.
- **Assists (new rule):** when a player dies, every other player who dealt at least `assist_min_damage` (40,
  halo + health) to that life within `assist_window_s` (10 s) before the death gets an assist (`rules.ron`,
  placeholders). The killer never does; in team deathmatch only the victim's enemies; in free-for-all anyone. A
  fall right after a fight credits whoever hurt them. Only a live match counts, like kills. Assists reach every
  client in `Score` (replicated) and in the kill feed message (`KillFeed::assists`, sent to every client, the
  host's own included); the HUD kill feed itself is unchanged.
- **Tab scoreboard:** new A and KDA columns in team deathmatch and free-for-all; KDA = (K + A) / max(D, 1), one
  decimal. The sort is unchanged (kills, then deaths).
- Protocol 10 (`Score::assists`, `KillFeed::assists`, the new `LifeRecap`).
- Pinned by `vetf_net::recap` tests (per-life encounters, the last-fight window, headshot kills, the assist rule,
  a new life), `protocol` round trips and `kda_counts_assists_and_never_divides_by_zero`, the server's
  `assists_go_to_the_victims_enemies_who_hurt_them_enough`, `a_death_waits_for_respawn_with_a_recap_then_starts_a_new_life`
  (the killer's kill icon, the next life number), `a_life_recap_reaches_the_host_and_only_the_dead_player` and
  `every_kill_reaches_the_host_and_each_joined_player_once` (with assists), `death` tests (kill icons, the last
  fight, the silhouette, the bars, the layout) and `scoreboard::the_board_shows_assists_and_kda`.

## 25. The mag check turns the gun to its magazine window (2026-10-09)
The user: "can you add that the check magazine does an inspect magazine animation so the gun its magazine gets
turned to you slightly, so you can see how many bullets, and holding the button does the check with that popup".
- **Inspect (visual only, `feel.ron` gun.mag_inspect):** when the simulation starts a mag check the first-person gun
  turns its magazine window toward the eye (up and in, muzzle across, canted) over `in_s` 0.22 s. A tap turns it
  back over `out_s` 0.26 s so it is back as the check ends (`mag_check_s`, 0.9-1.2 s, unchanged): that is when the
  estimate card shows. Held past that point, the gun stays turned (and the card stays, as before) until the key
  comes up. Aiming, firing, a reload or a dropped check turns it back over `cancel_s` 0.12 s. Others see the gun in
  that player's hand turn too (from the replicated weapon state; no protocol change).
- **The magazine window shows a level, not a count:** the Mako's `<mag>_Stack_NN` cartridges and top round and the
  Warden's rounds and follower now follow the magazine in your own gun, but read as the mag check's estimate: the
  window shows a fixed share of a full magazine per estimate (`weapon_models.ron` `mag_window`, kept within the
  estimate's own range), so it changes only on an estimate step and never counts down. Only the first-person gun's
  window is driven; third-person magazines keep the export (full) look.
- The sim's mag check (its time, what cancels it, the card) is unchanged.
- Pinned by `render::inspect` tests (tap vs hold, cancel, the turn fits every gun's check, the pose faces the Mako's
  and Warden's windows to the eye, others' turn) and `weapon_models` tests (`the_mag_window_shows_a_level_never_a_count`,
  `magazine_windows_are_read_from_the_exports`).

## 26. MAG CHECK: EXACT, an optional round counter (2026-10-09)

The user's exception to the genre rule "no exact ammo counters". It is an option, off by default: the estimate stays
the default everywhere.
- **Team deathmatch and free-for-all:** a host match setting in the lobby, MAG CHECK: ESTIMATE / EXACT
  (`MatchState::mag_check`, set with `LobbyAction::SetMagCheck`). Only the host can change it, and only in the lobby.
  It goes to every player with the match state, so everyone in the match plays with the same setting. A newly hosted
  match starts on ESTIMATE, and a mode change keeps the setting. Protocol version 11.
- **Gun range:** the player's own setting, Settings > Gameplay > RANGE MAG CHECK (`range_mag_check` in
  `settings.ron`, default ESTIMATE). The range ignores the match setting.
- **With EXACT:** the HUD keeps a permanent counter in the bottom right, "23 / 30" with the magazine's slot and ammo
  (hidden while dead), under the mag check card. The card's headline is the exact rounds instead of the estimate
  (footnote "EXACT COUNT"), and the reload radial shows each magazine's rounds ("AP II  23/30").
- **Unchanged:** the gun model's magazine window keeps its coarse level, the sim's mag check is the same, and with
  ESTIMATE nothing new shows. The client has always held its own exact round counts (predicted weapon state), so
  the setting changes only what the HUD shows. The host does not hide the counts from clients.

## 27. Assists shown: kill feed, ASSIST popup, environmental deaths (2026-10-09)

Assists (item 9-pre: `assist_min_damage` within `assist_window_s` in `rules.ron`) now show, and every death has a cause.
- **Kill feed:** "KILLER + HELPER > VICTIM". With several helpers the one who dealt the most damage is named, then
  "+N" (`LifeLog::assisters` now orders by damage, ties by id). Every client gets the line, the host's own included.
- **Environmental deaths:** `KillFeed::cause` (`DeathCause`: Shot, Fall, Bleed, OutOfBounds, Fire) is new on the wire
  (protocol version 12). Any cause but a shot is a non-player source: those who hurt the victim within the window
  still get their assists (one rule, keyed on the cause, so molotov fire needs no new rule). The feed names the
  cause: "HELPER + FALL > VICTIM", "HELPER +1 + FIRE > VICTIM", or "FALL > VICTIM" with nobody to credit. Kill credit
  is unchanged: a bleed-out still gives the kill to the last attacker ("KILLER + HELPER + BLEED > VICTIM").
- **ASSIST popup:** only the helpers (never the killer, the victim or a bystander) see a short "ASSIST" under the
  crosshair (1.1 s, fading out over its last third) and hear `combat/assist` plus the announcer hook
  `announcer/assist`. The announcer line is a placeholder stinger: a recorded voice line drops in by listing its file
  under that id in `sounds.ron` (no code change).

## 28. Kill streaks in team deathmatch and free-for-all (2026-10-09)

New (item 9c2, user direction; the design docs have no streaks). All numbers in `rules.ron` `streaks`, rules in
`vetf_sim::streak`.
- **The count:** kills in a row within one life. A kill adds one only when it scores (an enemy, in a live match: a
  teamkill or a kill in the lobby or the intermission does not) and the killer is alive (a trade on the same tick
  ends that life). Any death resets it. Assists do not count. It is `Score::streak`, replicated to everyone
  (protocol version 13), so a late joiner sees the aura too.
- **Tiers** (placeholders): 3 = a feed line ("WREN: 3 STREAK") and full health on every region plus every halo arc
  full; 5 = announced map-wide ("WREN is on a 5 STREAK" in the feed, a centre banner "BOUNTY" / "WREN IS ON A 5
  STREAK" for 3 s for everyone, the `announcer/streak_5` stinger) and every magazine refilled, the one in the gun
  too (the "mag reset"); 10 = announced ("MOST WANTED"), no reward. Ending a streak of 3 or more is in the feed:
  "ORCA ended WREN's 5 STREAK", "FALL ended WREN's 4 STREAK". The host applies the rewards; the streaker sees a
  toast under the crosshair ("3 STREAK: FULL HEALTH + FULL SHIELD"). The news is a new host-to-everyone message
  (`StreakNews`), sent like the kill feed so the host's own client gets it.
- **Rewards** are data: `FullHealth`, `FullShield`, `RefillMags`, and `Grenade`, a stub for when throwables exist
  (it gives nothing, and the data check rejects it in a tier until then).
- **Announcer:** no voice model, so each announced tier plays a placeholder stinger. A tier's `voice` field (a
  `sounds.ron` id, none set) is the hook for a recorded line, played with the stinger.
- **Bounty aura** from a 5 streak: ten small warm-gold embers spiral up around the body from the feet to just over
  the halo (unlit, additive, no shadows; look in `streaks.aura`). It is a marker on the player, not an outline, so it
  reads apart from the teammate rim glow. The local player has no aura of their own (first person).
- **HUD:** a streak counter just left of the health block (team deathmatch and free-for-all; shown from 2). Its
  slot is kept in those modes, so the vitals block sits about 80 px further right there than in the gun range.

## 29. The Loadout preview shows the real gun in 3D (2026-10-09)
- **Design:** mockups 05 / 05b show a fixed render of the gun in the preview box, with hotspots at fixed places.
- **Now (user direction, item 9d):** the preview box shows the draft's gun built from its glTF model with the parts
  it carries, the same assembly the match uses (a gun always shows a stock and a magazine: its defaults when the
  slot names none). Hovering a popover row puts that part on at once. LMB drag turns the gun (all the way round, the
  tilt limited), the wheel zooms; it opens on a three-quarter view of the gun's right side, muzzle to the right,
  under three studio lights. The slot hotspots sit on the gun's sockets and follow it as it turns. The view, the
  controls and the lights are UI data (`loadout_ui.ron` `gun_preview`; each hotspot's `model_side`). It is drawn by
  its own camera into an image on its own render layer, and exists only while the screen is open. A gun without a
  model (the Skink) keeps its 2D picture. The same screen serves the deathmatch layout, the death screen's loadout
  and the gun range's.

## 30. The SK-9 Skink SMG is out for now (2026-10-09)
- **Before:** three guns, the Mako, the Warden and the Skink SMG (the only gun that loads RIP).
- **Now (user direction, item 9e: "lets remove the smg for now"):** players pick from the Mako and the Warden. The
  Skink keeps all its data (`weapons.ron`, attachments, recoil pattern, sounds, feel, UI preview) with a new flag,
  `hidden: true`, so it can come back by deleting that one line. A hidden gun has no tab on the Loadout screen (any
  mode), cannot be switched to, cannot be the default loadout's gun (the data check refuses it) and no scripted pick
  clicks it. A saved loadout or preset with the Skink opens on the Mako with its default parts (RIP magazines turn
  STANDARD, the halo stays); `--weapon sk9_skink` asks for the Mako. The host refuses a client that still sends the
  Skink (`LoadoutError::HiddenWeapon`) and keeps them on their current loadout. Bots already play the default Mako.
  RIP ammo stays in the data, but no offered gun loads it now. Weapon indices are unchanged (no wire change).

## 31. The laser draws its beam; the UGL says it is not in yet (2026-10-09)
- **Before:** the LASER only changed stats (`hip_spread` 0.8, `ads_time` 1.02) and drew nothing; the UGL-40 was a
  model and stats with a blurb promising grenades and a key to switch to them.
- **Now (item 10):** the laser shows a thin red beam from its emitter (the model's `ATT_laser_R_SOCKET_Beam` node)
  to where its holder aims, with a dot where that aim meets the level or a player: our own from the first-person
  gun (hip and aimed), everyone else's from their held gun along their replicated look. The beam shows for 25 m
  from the gun and fades out there; the dot shows up to 120 m (`feel.ron` `laser`, visual only, no wire change). It
  was always on then (V toggles it since section 38). Since standing still is exact (section 12), the laser's
  `hip_spread` only narrows the moving hip cone (not the bloom, not aimed fire); its blurb now says "Tighter hip
  fire on the move". The UGL's blurb says grenades are not in yet (no `{G}` key hint) until the grenade-launcher
  mode lands; its stats (slower ADS, sway, move) still apply.

## 32. Smoke grenades and molotovs (2026-10-09)
- **Design:** throwables were not in the slice yet (the UGL's grenades were promised for later).
- **Now (user direction, item 10b):** every life in team deathmatch and free-for-all starts with one smoke grenade
  and one molotov (`rules.ron` `throwables`; three of each in the gun range, `range_throwables`). Keys **4** smoke and
  **5** molotov (Settings > Keybinds; a settings file from before keeps its own keys, and a new action never takes a
  key already in use). The HUD lists them bottom right with their counts (grenades are counted; the no-counter rule
  is about rounds). The numbers are in `throwables.ron`, the look in `throwable_fx.ron`:
  - **Throw:** a 0.3 s wind-up (the gun goes down), then the grenade leaves the right hand along the aim lifted 8°,
    at 16 m/s plus 60 % of your own velocity; the gun comes back up 0.35 s later. Not while reloading, using an
    item or mantling; a sprint is fine. It ends spawn protection. Deterministic and host-authoritative: the host
    flies every grenade; the thrower sees their own at once on the same arc, everyone else from the host's message.
  - **Flight:** a small ball under 14 m/s² of gravity that bounces off walls, glass and the map's bounds (keeps 35 %
    of its speed into a surface, 65 % along it) and comes to rest on a floor. Grenades pass through players.
  - **Smoke** pops 2 s after the throw or as soon as it lies still. The cloud grows to 4.5 m across (2.6 m half
    height) over 1.5 s, holds 15 s and thins out over 3 s. While dense it hides what is behind it: the test bots
    do not see (or shoot at) a head behind it, and a teammate in or behind it gets their marker as behind a wall.
    Bullets still go through smoke. A shot through it leaves a see-through tunnel along its path for about
    2.6 s on every client that saw the shot (visual only; the host's sight test ignores tunnels).
  - **Molotov** bursts on its first impact (on a wall, on the ground below it). Fire spreads to 3 m over 0.6 s and
    burns 7 s. Anyone whose feet are in it burns, the thrower and teammates too: 40 dps in 0.25 s pulses on the
    legs, the legs' halo arc soaking half of each pulse while it holds, the rest to health (broken legs spill into
    the torso). A burn kill is the thrower's kill when the victim is their enemy (kill feed "THROWER + FIRE"),
    otherwise nobody's; burning counts for assists like any damage. No damage in the lobby or after a match.
  - **Smoke puts out fire:** a fire goes out once a cloud reaches 0.5 m past its edge (a smoke landing in fire, or
    a molotov bursting under smoke).
  - Grenades, clouds and fires are cleared when the map or the match phase changes. A player who joins mid-match
    does not see clouds or fires already burning (they last seconds).
  - Wire: `ThrowNews` (thrown, burst, doused, clear), the throw keys in the buttons, the hand in the predicted
    items, the loadout's share per life: protocol 14.


## 33. Sound round 2 and the empty gun (2026-10-09)
- **Sounds (user playtest):** the concrete, gravel and wood steps, the landing, the Warden's shot and its bolt are now
  MiniMax H3 picks (`assets/audio/h3_round2/listen.html` lists every candidate and the pick, to override by ear);
  the grass steps stay. Volumes keep the placeholders' balance (A-weighted, grass as the reference); the Warden's
  shot sits about 5 dB(A) over the Mako's.
- **Bolt timing:** the bolt sound ends exactly as the Warden can fire again: `bolt_delay_s` (0.35 s) + its length
  (0.90 s) = `bolt_cycle_s` (1.25 s), its lock click in the last 0.07 s, no pitch jitter (tested). A change to the
  cycle or the delay needs the sound re-cut.
- **Empty gun (no HUD text):** the dry click is loud and crisp (about 14 dB over the old placeholder; the low-mag
  cue, which borrows its file, stays as quiet as before). Each empty pull twitches the gun in the hands (no recoil,
  no camera kick); the third empty pull in a row (within 1.5 s of each other; a reload starts the count again)
  gives a 0.5 s frustrated shake of the gun, stopped by aiming, a reload or a swap (`feel.ron` gun.dry_fire). Others
  see the shake on the gun in that player's hand. The gun models' moving nodes now move: the trigger comes back
  while FIRE is held, and an empty gun shows its bolt held open (the Warden's bolt lifted and drawn back; the Mako
  has no bolt-carrier node, so its charging handle comes back instead) until the reload closes it
  (`weapon_models.ron` guns.moving). Visual only: nothing on the wire changed.


## 34. 120 Hz, and the tick and snapshot rates as host settings (2026-10-09)
- **Tick rate (HOST GAME):** 60 or 120 Hz, **120 by default** (the design's `tick_hz: 60` is superseded; `net.ron`
  `tick_hz` is only the default and `tick_rates` what HOST GAME offers). Everyone in a match runs at the host's
  rate: a joining client's netcode id carries its rate, the host gives a player only to a client at its own rate
  (no bot gives up its seat for the others) and tells every joiner its rate (`TickRate`); a client at the other
  rate reconnects at once at the host's ("The host plays at 60 Hz: joining at 60 Hz..." on the connecting
  screen). A host rate the build does not offer sends the client back to the menu with a message (last resort).
  The rate is set between sessions only (lightyear's tick, Bevy's fixed step and the session's data).
- **Snapshot rate (HOST GAME and the lobby's MATCH SETTINGS):** 30, 60 or 120 snapshots a second, **60 by default**
  (was 30), 120 only at 120 Hz. The lobby shows it with the host's upload for the players in it, in the warning
  colour past `net.ron` `upload.warn_mbit` (5 Mbit/s). The estimate, every player moving (about 120 bytes of state
  each per snapshot plus 64 of headers, sent to every player on the network):

  | players | 30/s | 60/s | 120/s |
  |---|---|---|---|
  | 2 | 0.07 | 0.15 | 0.29 Mbit/s |
  | 4 | 0.39 | 0.78 | 1.57 Mbit/s |
  | 6 | 0.94 | 1.88 | 3.76 Mbit/s |
  | 8 | 1.72 | 3.44 | 6.88 Mbit/s |
  | 10 | 2.73 | 5.46 | 10.92 Mbit/s |

  The host sends at most one snapshot per rendered frame (lightyear), so 120 a second needs the host above 120 fps.
  No per-client cap yet (lightyear has one replication timer for every client).
- **Interpolation delay:** other players are drawn `interpolation_snapshots` (2) snapshot intervals behind the newest
  snapshot, at least 25 ms, plus lightyear's jitter margin (4 x jitter + 1 tick): about 33 ms + margin at 60 a
  second, 67 at 30, 25 at 120. Before, lightyear drew them 1.2 intervals behind at 30 a second (40 ms + margin; the
  100 ms in `net.ron` was never used).
- **Seconds, not ticks:** `net.ron` `input_redundancy_s` (1/6 s: 10 ticks at 60 Hz, 20 at 120) and `max_rollback_s`
  (1/3 s: 20 and 40; now passed to lightyear, which used its own default of 20). The host's claim wait and the grace
  for a dead shooter's last shots moved from code (30 and 2 ticks) to `combat.ron` (`claim_wait_s` 0.5,
  `dead_shooter_grace_s` 0.034). `weapons.ron` loses its unused `tick_hz`.
- **The same game at both rates (tested, `vetf_sim/tests/tick_rate.rs`):** every fire interval is the same time
  (Mako 720 RPM: 5 or 10 ticks, 612 aimed: 6 or 12; Warden 48 RPM: 75 or 150, so the bolt sound still ends as it can
  fire), reloads and other actions within half a 60 Hz tick. Movement and grenades keep their semi-implicit step,
  whose error halves at 120 Hz: a jump peaks at 1.05 m at 60 Hz and 1.02 m at 120 (1.00 m exact), a sprint and stop
  goes 6 cm (0.8 %) further, a slide 10 cm (1.3 %), a 15 m molotov lands 10 cm further.
- **Projector sight:** its hologram fades in over 0.02 s (was 0.03), so at 120 Hz it is still in when the gun is up.
- **Cost:** the host simulates twice the ticks: a throwaway probe of 10 players' movement and weapons (no game run)
  took about 6 ms of CPU a second at 60 Hz and 8 ms at 120 (70-100 us a tick); the ESC menu shows the host's whole
  tick live. Clients send as many input packets as before (one a frame) with twice the ticks in each, and a rollback
  replays twice the ticks.
- Wire: `TickRate`, the rates on `MatchState`, `LobbyAction::SetSnapshotHz`, the rate in the client id: protocol 15.


## 35. The attachment list shows what each part does; the laser and the thermal add recoil (2026-10-09)
- **Before:** each row of the Loadout screen's attachment popover showed only the two biggest stat changes
  against the EQUIPPED part (so with the stub grip on, NONE read "HIP SPREAD +14 %" and the angled grip hid its
  own benefits), and the panel was PANEL_HI at .82, so the cards under it showed through.
- **Now (user, item B):**
  - Each row lists the part's OWN effect, against no part in that slot: EVERY stat it changes, in per cent
    (RECOIL V / H, ADS TIME, SWAY, MOBILITY, SPRINT-TO-FIRE, MOVING SPREAD, RELOAD; a magazine's CAPACITY), good
    first, green / red. NONE and a default stock read BASELINE. Under it a quieter "VS EQUIPPED" line lists what
    changes if you swap to it (rounds and zoom too); the equipped row has none. A test holds every stat field an
    attachment sets to a line.
  - Tags list what a part does that is not a stat: its zoom (`3× ZOOM`, `6–12× ZOOM · SCROLL`) and the data's new
    `effects` (`attachments.ron`). What a part promises but the game does not do yet is a warning-coloured tag
    saying NOT IN THE GAME YET: the bipod's deploy (and its blurb says so: there is no deploy yet), the UGL's
    grenades, the flashlight's light and glare, the front shield's bullet blocking, the scopes' glint and the
    thermal's heat view. The bipod, flashlight, shield and thermal blurbs stopped promising those effects.
  - `hip_spread` reads MOVING SPREAD (standing still is exact, aimed fire is not touched; section 12).
  - Popovers, context menus and modals are opaque, borders included (`POPOVER_SURFACE`); so is the dragged
    magazine card. A long list spreads over two or three columns (the Warden's seven optics take three).
  - The gun preview's "F: SHOW ON AGENT + HALO" hint is gone (nothing did that).
- **Recoil penalties (user: "some stuff can increase it again like laser or thermal"):** the LASER `recoil_h` 1.05
  (+5 % sweep), the THERMAL optic `recoil_v` 1.08 (+8 % climb). The rule stays: every non-default stock lowers only
  the climb, every grip only the sweep; other parts may raise either (tested: no stock or grip raises recoil).
  The 60-round drum and the UGL stay recoil-neutral: they already pay in reload, aim speed and move speed, and
  every magazine sprays the same T (section 15). No wire change.


## 36. The host edits the match settings in the lobby; bots make room on a mode switch (2026-10-09)
- **Before:** the lobby only showed the score limit, time limit, players, respawn, kill refill and points; they
  came from `rules.ron` per mode. A switch to a mode with fewer seats (team deathmatch 10 to free-for-all 8) was
  refused whenever the lobby held more than 8, bots included.
- **Now (user, item C):**
  - The host steps SCORE LIMIT, TIME (whole minutes), MAX PLAYERS, RESPAWN (whole seconds), KILL REFILL (0, 1 or
    2 magazines) and POINTS in the match settings; everyone else reads the values live in the rows below. Ranges
    and steps live in `rules.ron` `lobby_settings` (placeholders: score 5-200 by 5, time 2-30 min, respawn 1-15 s,
    refill 0-2, points 2-20; points never under 2 so the default loadout always fits). MAX PLAYERS goes from 2 to
    the mode's seats and HOST GAME's slots, by 2 in team deathmatch. The host clamps whatever it is sent.
  - A lobby opens with its mode's `rules.ron` values, and a mode switch goes back to the new mode's (the host's
    edits do not carry over; MAG CHECK and the snapshot rate stay).
  - The settings drive the match: the clock a match starts with, the respawn timer a death starts (and the death
    screen's bar), the magazines a kill refills, and the points budget of the host's loadout check and of the
    Loadout screen (and the ESC menu's points). Auto-respawn, spawn protection and assists stay per mode in data.
  - Bots on a switch to fewer seats, or a lower MAX PLAYERS (user: "remove automatically"): bots leave, the most
    recently added first (in team deathmatch first from a team over its half), until everyone fits. Only real
    players alone over the new limit refuse the change.
- **Not yet:** a player whose loadout no longer fits lower POINTS is not told in the lobby: the host refuses the
  loadout and they spawn with the default one until they pick a cheaper loadout.
- Wire: `MatchState::settings`, `LobbyAction::SetSetting`: protocol 16.

## 37. Your own streak aura, repeat announcements, and the free-for-all bounty (2026-10-09)
- **Before (section 28):** the bounty aura was for others only, 10 was the last announced streak, and a streak gave
  only its tier rewards, the same in team deathmatch and free-for-all.
- **Now (user, item D):**
  - **Your own aura:** from the aura's tier (5) the streaker sees a faint version in first person: a few dim gold
    embers rising around the gun hand and lightly at the left and right screen edges, never within 15 degrees of
    the crosshair (tested at every FOV and screen shape), gone when the streak resets. Look in `rules.ron`
    `streaks.own_aura` (counts, places, `intensity`, `glow`, `clear_deg`).
  - **Repeat announcements:** after the last tier (10, "MOST WANTED"), every `streaks.repeat_every` (5) kills more
    are announced again with that tier's banner and stinger, no rewards: 15, 20, 25 ... and nothing in between.
  - **The bounty (free-for-all only; team deathmatch keeps its streaks as they were):** `streaks.bounty`, with the
    modes listed per effect (`speed_modes`, `reveal_modes`: `[Ffa]`).
    - Speed: from a 5 streak every kill adds 5 % movement speed (5 kills +5 %, 6 +10 % ...), at most +25 %; it goes
      with the streak on death. The host sets it on the player's `Wounds::bounty_speed`, which goes into the
      movement speed multiplier, so the host and the owner's prediction move alike (protocol 17).
    - Reveal: from a 5 streak everyone else sees the streaker through walls (`reveal: Name`, the default: their
      name and a small bounty icon, a ring around a dot, above the head, in the bounty gold, never the ally
      colour; fades to 55 % far out but never hides). `reveal: Silhouette` draws a faint rounded outline around
      the body instead; `Off` turns it off. The streaker never sees their own. Look in `friend_foe.ron` `bounty`.
      **This is a deliberate exception to DIRECTION_LOG 17's "no enemy tells"** (the user's ask for a bounty), so
      it is limited to free-for-all and to a streak of 5 or more.

## 38. The laser switches on and off; the beam follows the barrel; the dot shows in the scope (2026-10-09)
- **Before:** the laser was always on and V did nothing; its beam always ran to the crosshair, even with the gun
  lowered in the sprint pose; fully scoped through a magnified optic the gun and its laser were hidden.
- **Now (item D2, user answers):**
  - **V toggles the laser** (`Buttons::LASER`, `WeaponState::laser_on`, on at spawn, a small click). The state is
    replicated, so other players see a beam only while it is on (protocol 18). It toggles at any time, gun up or not.
  - **The laser's `hip_spread` (0.8) counts only while it is on.** Its `ads_time` and `recoil_h` are the part's
    weight and always count (attachments.ron `laser: true`). Turning it off trades tighter moving hip fire for not
    being seen.
  - **The beam follows the barrel:** once the barrel points more than `feel.ron` `laser.follow_barrel_deg` (6 to 16
    degrees, eased) away from the aim (sprint pose, mag check, reload, an item, any pose with the gun down or busy),
    the beam leaves along the barrel and the dot lands where the barrel ray hits. This is measured from the gun as
    drawn, for our own viewmodel and for other players' third-person guns. With the gun up it is as before.
  - **Scoped:** fully aimed through a magnified optic, our own dot still shows in the scope view where the aim
    lands. There is no beam.

## 39. Stocks and grips bite harder; the visual kick follows them (2026-10-10)
User: "currently stocks and grips have too little impact on the spray".
- **Stronger multipliers** (`attachments.ron`, table in section 15): the Mako PRECISION stock takes the climb to 0.6
  (was 0.8), LIGHT 0.78 (0.92), the Warden FOLDING 0.85 (0.95); the BRACE grip takes the sweep to 0.55 (0.78),
  ANGLED 0.7 (0.88), STUB 0.82 (0.94). Their costs are unchanged. PRECISION + BRACE now sprays 60 % of the climb and
  55 % of the bar.
- **The visual kick follows them** (render only): the camera punch scales with `recoil_v`, and the per-shot shake
  (`feel.ron` shots) scales per axis, pitch / push-back / gun kick by `recoil_v`, yaw / roll by `recoil_h`
  (`ShotFeel::scaled`). Before, the screen shook the same with any stock or grip, so the change was hard to feel.
- Pinned by `data.rs` (`attachment_modifiers_multiply`, `stocks_lower_the_climb_and_grips_the_sweep`) and
  `render/feel.rs` (`the_shot_shake_follows_the_recoil_multipliers`).
