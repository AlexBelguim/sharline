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
- **The screen:** the gun, its attachments and a MAGAZINE row (six carried); then ONE ARMOR row (T1-T4 with weight
  class, arcs and points), ONE AMMO row, and the points used / total split into armor, ammo and magazine. A card's
  points turn red when picking it would push the loadout over the total. Q / E and the arrows walk gun ->
  attachments -> magazine -> armor -> ammo -> BACK / CONFIRM. The main menu has no LOADOUT entry for now; the
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

- **Mako pattern** (`recoil_patterns.ron`, standard stock, no grip; hip degrees, aimed x0.7):
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
  | Mako PRECISION stock | V 0.9, H 0.9 | V 0.8 (ADS x1.1, sway 0.8, move 0.98) |
  | Mako LIGHT stock | V 1.12, H 1.12 | V 0.92 (ADS x0.88, sway 1.15, sprint-to-fire 0.85) |
  | Warden FOLDING stock | V 1.1 | V 0.95 (ADS x0.9, sway 1.25, move 1.03) |
  | VERTICAL GRIP, now **BRACE GRIP** | V 0.88 | H 0.78 (ADS x1.03, new sway 0.95) |
  | ANGLED GRIP | H 0.94 | H 0.88 (ADS x0.92) |
  | STUB GRIP | H 0.95 | H 0.94 (hip spread 0.88, sprint-to-fire 0.9) |

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
