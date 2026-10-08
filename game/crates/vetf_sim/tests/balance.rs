//! Balance pins from the ammo balance pass (v2; see game/DESIGN_DELTAS.md section 1). These fail when a
//! number in `assets/data` moves a breakpoint the design relies on: the SMG and RIP leg spraying, AP and the
//! gear budget, the Warden's one-shot margins, and Shrapnel bleed timing. All at 10 m and hip fire unless
//! stated. The gun tuning of playtest round 1 (DESIGN_DELTAS.md section 9) adds time-to-kill, range-role and
//! recoil-control pins at the end.

use glam::Vec3;
use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::ZoneTable;
use vetf_sim::combat::{HaloSpec, HaloState, Health, falloff, resolve_hit};
use vetf_sim::data::{AmmoChoice, AmmoKind, AmmoSpec, ArmorStats, RecoilSpec, WeaponClass};
use vetf_sim::hitbox::{self, Pose};
use vetf_sim::movement::{MoveMode, Stance};
use vetf_sim::weapon::{
    ADS_AIMED, WeaponAction, WeaponEnv, WeaponLoadout, WeaponState, fire_interval_ticks, shot_direction, shot_seed,
};

const NEVER: f32 = 1.0;
const SKINK: &str = "sk9_skink";
const MAKO: &str = "ar7_mako";
const WARDEN: &str = "vk50_warden";

fn ammo(d: &GameData, class: WeaponClass, kind: AmmoKind, tier: u8) -> AmmoSpec {
    d.ammo.resolve(class, AmmoChoice { kind, tier }).unwrap()
}

fn std(d: &GameData, class: WeaponClass) -> AmmoSpec {
    ammo(d, class, AmmoKind::Standard, 1)
}

/// An armor preset with the loadout tier caps applied (what a player can actually wear).
fn capped(d: &GameData, armor: &str) -> ArmorStats {
    let mut p = d.armor.preset(armor).unwrap().clone();
    let caps = d.armor.loadout_tier_caps;
    p.tiers = p.tiers.map(|z, t| (*t).min(caps[z]));
    d.armor.resolve(&p)
}

fn shots(d: &GameData, weapon: &str, a: &AmmoSpec, armor: &ArmorStats, zone: Zone, range: f32) -> u32 {
    let w = d.weapon(weapon).unwrap();
    let spec = HaloSpec::from_armor(armor);
    let mut halo = HaloState::full(&spec);
    let mut hp = Health::new(d.armor.zone_hp);
    for n in 1..400 {
        if resolve_hit(w, a, range, zone, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp, NEVER).killed {
            return n;
        }
    }
    panic!("{weapon} never killed through {zone:?}");
}

/// (torso, legs) shots.
fn torso_legs(d: &GameData, weapon: &str, a: &AmmoSpec, armor: &ArmorStats) -> (u32, u32) {
    (shots(d, weapon, a, armor, Zone::Torso, 10.0), shots(d, weapon, a, armor, Zone::Legs, 10.0))
}

#[test]
fn skink_fires_fast_and_slower_aimed() {
    let d = GameData::embedded();
    let s = d.weapon(SKINK).unwrap();
    assert_eq!(s.cls, WeaponClass::Smg);
    assert_eq!(fire_interval_ticks(s, 60, false), 3, "1200 rpm");
    assert_eq!(fire_interval_ticks(s, 60, true), 4, "900 rpm aimed");
}

/// N5: on bare-legged Medium / Heavy halos, RIP to the legs beats every SMG round to the torso, and the
/// SMG's other rounds stay torso-first.
#[test]
fn rip_makes_leg_spraying_the_answer_to_bare_legs() {
    let d = GameData::embedded();
    let smg = WeaponClass::Smg;
    let rounds = [
        ("RIP I", ammo(&d, smg, AmmoKind::Rip, 1)),
        ("RIP II", ammo(&d, smg, AmmoKind::Rip, 2)),
        ("RIP III", ammo(&d, smg, AmmoKind::Rip, 3)),
        ("STD", std(&d, smg)),
        ("AP I", ammo(&d, smg, AmmoKind::ArmorPiercing, 1)),
        ("AP II", ammo(&d, smg, AmmoKind::ArmorPiercing, 2)),
        ("AP III", ammo(&d, smg, AmmoKind::ArmorPiercing, 3)),
    ];
    // (torso, legs) per round, for bulwark_assault, volt_line, bulwark_vanguard, mender_medic. Gun tuning
    // (playtest round 1) raised the Skink's close damage 24 -> 36: every count dropped, the order stayed.
    #[rustfmt::skip]
    let want: [[(u32, u32); 4]; 7] = [
        [(14, 7), (11, 7), (17, 11), (10, 9)],
        [(14, 7), (11, 7), (16, 10), (10, 9)],
        [(14, 6), (11, 6), (16, 9), (10, 8)],
        [(7, 9), (7, 9), (8, 10), (6, 10)],
        [(7, 9), (6, 9), (8, 10), (6, 9)],
        [(6, 9), (5, 9), (7, 9), (5, 9)],
        [(6, 8), (5, 8), (6, 9), (5, 9)],
    ];
    let presets = ["arm_bulwark_assault", "arm_volt_line", "arm_bulwark_vanguard", "arm_mender_medic"];
    for ((name, a), want) in rounds.iter().zip(want) {
        for (armor, want) in presets.iter().zip(want) {
            let got = torso_legs(&d, SKINK, a, &capped(&d, armor));
            assert_eq!(got, want, "{name} vs {armor}");
            let rip = name.starts_with("RIP");
            assert_eq!(got.1 < got.0, rip, "{name} vs {armor}: only RIP is leg-first");
        }
    }
}

/// N6: a T2 leg arc (the loadout cap) is a real counter to RIP leg spraying.
#[test]
fn leg_arcs_blunt_rip() {
    let d = GameData::embedded();
    let assault = capped(&d, "arm_bulwark_assault");
    let jugg = capped(&d, "arm_bulwark_jugg");
    assert_eq!(jugg.tiers.legs, d.armor.loadout_tier_caps.legs);
    let want = [((14, 7), (17, 13)), ((14, 7), (16, 12)), ((14, 6), (16, 12))];
    for (tier, (wa, wj)) in (1..=3).zip(want) {
        let rip = ammo(&d, WeaponClass::Smg, AmmoKind::Rip, tier);
        let (a, j) = (torso_legs(&d, SKINK, &rip, &assault), torso_legs(&d, SKINK, &rip, &jugg));
        assert_eq!((a, j), (wa, wj), "RIP {tier}");
        let (adv_a, adv_j) = (a.0 as i32 - a.1 as i32, j.0 as i32 - j.1 as i32);
        assert!(adv_j * 3 <= adv_a * 2 && adv_a - adv_j >= 3, "RIP {tier}: {adv_a} -> {adv_j}");
    }
}

#[test]
fn skink_breakpoints() {
    let d = GameData::embedded();
    let smg = WeaponClass::Smg;
    let none = capped(&d, "arm_none");
    let (s, rip3) = (std(&d, smg), ammo(&d, smg, AmmoKind::Rip, 3));
    assert_eq!(shots(&d, SKINK, &s, &none, Zone::Torso, 10.0), 4, "36 x 3 = 108 < 120");
    assert_eq!(shots(&d, SKINK, &rip3, &none, Zone::Torso, 10.0), 3, "43.2 x 3 = 129.6");
    assert_eq!(shots(&d, SKINK, &s, &capped(&d, "arm_mender_scout"), Zone::Torso, 10.0), 5, "36 x 5 = 180");
    assert_eq!(shots(&d, MAKO, &std(&d, WeaponClass::AssaultRifle), &none, Zone::Torso, 10.0), 3);
    // N10: the SMG falls off hard; the Mako owns range.
    let volt = capped(&d, "arm_volt_line");
    let mako = std(&d, WeaponClass::AssaultRifle);
    for (range, armor, want_std, want_rip, want_mako) in
        [(30.0, &none, 9, 8, 3), (30.0, &volt, 16, 28, 5), (50.0, &volt, 22, 39, 6)]
    {
        assert_eq!(shots(&d, SKINK, &s, armor, Zone::Torso, range), want_std, "STD at {range}");
        assert_eq!(shots(&d, SKINK, &rip3, armor, Zone::Torso, range), want_rip, "RIP III at {range}");
        assert_eq!(shots(&d, MAKO, &mako, armor, Zone::Torso, range), want_mako, "Mako at {range}");
    }
    // No Skink round one-taps a bare head.
    let w = d.weapon(SKINK).unwrap();
    let best = w.damage * w.zone_mult.head * rip3.flesh_mult * rip3.damage_mult;
    assert!(best < d.armor.zone_hp.head, "{best}");
}

#[test]
fn ap_hits_shields_harder_but_keeps_the_mako_at_three_bare_torso_shots() {
    let d = GameData::embedded();
    let none = capped(&d, "arm_none");
    for tier in 1..=3 {
        let ap = ammo(&d, WeaponClass::AssaultRifle, AmmoKind::ArmorPiercing, tier);
        assert_eq!(shots(&d, MAKO, &ap, &none, Zone::Torso, 10.0), 3, "AP {tier}");
    }
}

/// Health left after one Warden torso shot at 30 m (None = dead).
fn warden_torso(d: &GameData, a: &AmmoSpec, armor: &ArmorStats) -> Option<f32> {
    let w = d.weapon(WARDEN).unwrap();
    let spec = HaloSpec::from_armor(armor);
    let mut halo = HaloState::full(&spec);
    let mut hp = Health::new(d.armor.zone_hp);
    let r = resolve_hit(w, a, 30.0, Zone::Torso, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp, NEVER);
    (!r.killed).then_some(hp.hp.torso)
}

#[test]
fn warden_keeps_the_design_breakpoints_and_ap_margins() {
    let d = GameData::embedded();
    let sniper = WeaponClass::BoltSniper;
    // The design's worked example: one torso hit at 30 m on a Volt Line leaves 60 HP and no torso shield.
    let volt = capped(&d, "arm_volt_line");
    let left = warden_torso(&d, &std(&d, sniper), &volt).unwrap();
    assert!((left - 60.0).abs() < 1e-3, "{left}");
    // AP one-shot margins stay at least 5 HP either way.
    let ap = |t| ammo(&d, sniper, AmmoKind::ArmorPiercing, t);
    let near = |got: Option<f32>, want: f32| got.is_some_and(|hp| (hp - want).abs() < 0.05);
    let scout = capped(&d, "arm_mender_scout");
    let medic = capped(&d, "arm_mender_medic");
    assert!(near(warden_torso(&d, &ap(1), &scout), 6.8));
    assert_eq!(warden_torso(&d, &ap(2), &scout), None);
    assert!(near(warden_torso(&d, &ap(2), &medic), 6.9));
    assert_eq!(warden_torso(&d, &ap(3), &medic), None);
    assert!(near(warden_torso(&d, &ap(3), &volt), 6.0));
}

/// The design's single-pool Warden numbers (every arc at full core capacity, uncapped presets).
#[test]
fn warden_matches_the_design_model() {
    let mut d = GameData::embedded();
    d.armor.zone_capacity_share = ZoneTable::splat(1.0);
    let s = std(&d, WeaponClass::BoltSniper);
    #[rustfmt::skip]
    let table: [(&str, [u32; 4]); 7] = [
        ("arm_none", [1, 1, 3, 2]), ("arm_phase_runner", [1, 1, 3, 2]), ("arm_phase_ghost", [1, 1, 3, 2]),
        ("arm_mender_scout", [1, 2, 3, 2]), ("arm_volt_line", [1, 2, 3, 2]),
        ("arm_bulwark_assault", [1, 2, 4, 2]), ("arm_bulwark_jugg", [1, 2, 4, 4]),
    ];
    for (armor, want) in table {
        let a = d.armor.resolve_id(armor).unwrap();
        let got = Zone::ALL.map(|z| shots(&d, WARDEN, &s, &a, z, 10.0));
        assert_eq!(got, want, "{armor}");
    }
}

/// (armor tier, gun class, ammo (type, tier), magazine type, expected points)
type GearRow<'a> = (u8, WeaponClass, (AmmoKind, u8), &'a str, u32);

/// Team deathmatch and free-for-all points (DIRECTION_LOG 17, `rules.ron` `deathmatch_loadout`): the armor
/// tier, the one ammo type paid once and the magazine type, against `gear_budget`. T4 and the best ammo
/// never fit together; the middles do.
#[test]
fn deathmatch_points() {
    let d = GameData::embedded();
    let kit = &d.rules.deathmatch_loadout;
    let budget = d.rules.tdm.gear_budget;
    assert_eq!((budget, d.rules.ffa.gear_budget), (8, 8));
    assert_eq!(kit.armor.iter().map(|a| a.points).collect::<Vec<_>>(), [1, 2, 3, 5]);
    let ar = WeaponClass::AssaultRifle;
    let cost = |armor: u8, class: WeaponClass, (k, t): (AmmoKind, u8), mag: &str| {
        kit.armor_tier(armor).unwrap().points + ammo(&d, class, k, t).gear_cost + kit.mag_points(mag)
    };
    use AmmoKind::{ArmorPiercing as Ap, Rip, Standard as Std};
    #[rustfmt::skip]
    let table: &[GearRow] = &[
        (1, ar, (Std, 1), "mag_30", 1),
        (2, ar, (Std, 1), "mag_30", 2),
        (4, ar, (Std, 1), "mag_drum60", 7),
        (4, ar, (Ap, 1), "mag_drum60", 8),
        (4, ar, (Ap, 2), "mag_45", 8),
        (4, ar, (Ap, 2), "mag_drum60", 9),
        (4, ar, (Ap, 3), "mag_30", 9),
        (3, ar, (Ap, 3), "mag_45", 8),
        (3, ar, (Ap, 3), "mag_drum60", 9),
        (2, ar, (Ap, 3), "mag_drum60", 8),
        (1, ar, (Ap, 3), "mag_drum60", 7),
        (4, WeaponClass::Smg, (Rip, 3), "skink_mag_40", 9),
        (3, WeaponClass::Smg, (Rip, 3), "skink_mag_60", 8),
        (4, WeaponClass::BoltSniper, (Ap, 3), "mag_5", 9),
        (3, WeaponClass::BoltSniper, (Ap, 3), "mag_8", 8),
    ];
    for (armor, class, round, mag, want) in table {
        assert_eq!(cost(*armor, *class, *round, mag), *want, "T{armor} {round:?} {mag}");
    }
    // T4 with any tier III round never fits; every tier fits with standard ammo and any magazine.
    for class in [ar, WeaponClass::Smg, WeaponClass::BoltSniper] {
        assert!(cost(4, class, (Ap, 3), "") > budget, "{class:?}");
        for armor in 1..=4 {
            assert!(cost(armor, class, (Std, 1), "mag_drum60") <= budget, "{class:?} T{armor}");
        }
    }
}

/// N9: Shrapnel bleed at max stacks is slow enough to treat; the treated residual is a 0.1 HP/s trickle.
#[test]
fn shrapnel_bleed_timing() {
    let d = GameData::embedded();
    let spill = &d.weapons.spill_to_torso;
    for (tier, lo, hi) in [(1, 26.6, 26.7), (2, 19.95, 20.05), (3, 15.95, 16.05)] {
        let b = ammo(&d, WeaponClass::AssaultRifle, AmmoKind::Shrapnel, tier).bleed.unwrap();
        assert_eq!(b.residual_hp_per_s, 0.1, "SHR {tier}");
        let mut hp = Health::new(d.armor.zone_hp);
        for _ in 0..b.max_stacks {
            hp.bleeding.add_stack(Zone::Torso, &b);
        }
        let mut ticks = 0;
        while !hp.dead && ticks < 60 * 1000 {
            if hp.tick_bleeding(spill, 1.0 / 60.0).died {
                hp.dead = true;
            }
            ticks += 1;
        }
        let s = ticks as f32 / 60.0;
        assert!((lo..=hi).contains(&s) && s >= 10.0, "SHR {tier}: {s} s");
        // Treated: only the residual keeps ticking.
        let mut hp = Health::new(d.armor.zone_hp);
        for _ in 0..b.max_stacks {
            hp.bleeding.add_stack(Zone::Torso, &b);
        }
        hp.bleeding.treat(Zone::Torso);
        assert!((hp.bleeding.active.torso - 0.1 * b.max_stacks as f32).abs() < 1e-5);
    }
}

// ---------------------------------------------------------------------------------------------- gun tuning
// Playtest round 1 (DESIGN_DELTAS.md section 9): "time to kill seems pretty high with the AR", "the SMG does the
// same damage at long range?", "the recoil is way too low on the AR".

/// Hit mixes: where a spray's rounds land, in turn.
const ALL_TORSO: &[Zone] = &[Zone::Torso];
/// A body spray: 60 % torso, 20 % arms, 20 % legs.
const BODY_SPRAY: &[Zone] = &[Zone::Torso, Zone::Arms, Zone::Torso, Zone::Legs, Zone::Torso];
/// A spray that climbs into the head: every third round.
const HEAD_AND_TORSO: &[Zone] = &[Zone::Torso, Zone::Torso, Zone::Head];
const ALL_HEAD: &[Zone] = &[Zone::Head];

/// The halo every player spawns with (rules.ron default loadout), loadout-capped.
fn default_halo(d: &GameData) -> ArmorStats {
    capped(d, &d.rules.default_loadout.armor)
}

/// Rounds and seconds to kill with Standard rounds landing on `mix` in turn at `range`, hip fire or aimed (the
/// aimed fire rate). The seconds run from the first round to the killing one.
fn ttk(d: &GameData, weapon: &str, armor: &ArmorStats, mix: &[Zone], range: f32, aimed: bool) -> (u32, f32) {
    let w = d.weapon(weapon).unwrap();
    let a = std(d, w.cls);
    let spec = HaloSpec::from_armor(armor);
    let mut halo = HaloState::full(&spec);
    let mut hp = Health::new(d.armor.zone_hp);
    let hz = d.net.tick_hz;
    for (n, zone) in mix.iter().cycle().take(400).enumerate() {
        if resolve_hit(w, &a, range, *zone, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp, NEVER).killed {
            let interval = fire_interval_ticks(w, hz, aimed) as f32 / hz as f32;
            return (n as u32 + 1, n as f32 * interval);
        }
    }
    panic!("{weapon} never killed");
}

/// The Mako with the design's damage numbers (what the slice shipped with before playtest round 1).
fn with_design_mako(d: &GameData) -> GameData {
    let mut old = d.clone();
    let w = old.weapons.weapons.iter_mut().find(|w| w.id == MAKO).unwrap();
    w.damage = 37.0;
    w.falloff = vec![(0.0, 37.0), (25.0, 37.0), (50.0, 31.0), (80.0, 27.0)];
    w.min_damage = 27.0;
    w.zone_mult = ZoneTable { head: 1.3, torso: 1.0, arms: 0.8, legs: 0.85 };
    old
}

/// The Mako's time to kill through the default halo (Mender Scout: 60 shield + 120 torso HP, 36 + 45 head) at
/// 10 m: (rounds, hip seconds, aimed seconds) per mix. Before, with the design's 37 damage: torso 5 (0.33 / 0.40 s),
/// body spray 8 (0.58 / 0.70 s), head and torso 6 (0.42 / 0.50 s), head 2.
#[test]
fn the_mako_kills_faster_through_the_default_halo() {
    let d = GameData::embedded();
    let old = with_design_mako(&d);
    let halo = default_halo(&d);
    assert_eq!(halo.id, "arm_mender_scout");
    #[rustfmt::skip]
    let want: [(&[Zone], u32, f32, f32); 4] = [
        (ALL_TORSO, 4, 0.25, 0.3),
        (BODY_SPRAY, 6, 5.0 / 12.0, 0.5),
        (HEAD_AND_TORSO, 5, 4.0 / 12.0, 0.4),
        (ALL_HEAD, 2, 1.0 / 12.0, 0.1),
    ];
    for range in [10.0, 25.0] {
        for (mix, rounds, hip, aimed) in want {
            let (n, h) = ttk(&d, MAKO, &halo, mix, range, false);
            let (_, a) = ttk(&d, MAKO, &halo, mix, range, true);
            assert_eq!(n, rounds, "{mix:?} at {range} m");
            assert!((h - hip).abs() < 1e-4 && (a - aimed).abs() < 1e-4, "{mix:?} at {range} m: {h} / {a}");
        }
    }
    // The aim of the change: a body spray kills 25-35 % faster, hip and aimed, out to 25 m.
    for range in [10.0, 25.0] {
        for aimed in [false, true] {
            let before = ttk(&old, MAKO, &halo, BODY_SPRAY, range, aimed).1;
            let after = ttk(&d, MAKO, &halo, BODY_SPRAY, range, aimed).1;
            let faster = 1.0 - after / before;
            assert!((0.25..=0.35).contains(&faster), "{range} m aimed {aimed}: {before} -> {after} s");
        }
    }
    // Headshots pay: two kill within 25 m through the biggest T3 head arc (Bulwark; three before) and a T4 Phase
    // one, and one kills a bare head at any range (before: not past 70 m).
    for armor in ["arm_mender_scout", "arm_bulwark_assault", "arm_phase_ghost"] {
        assert_eq!(ttk(&d, MAKO, &capped(&d, armor), ALL_HEAD, 25.0, false).0, 2, "{armor}");
    }
    assert_eq!(ttk(&old, MAKO, &capped(&d, "arm_bulwark_assault"), ALL_HEAD, 25.0, false).0, 3);
    assert_eq!(ttk(&d, MAKO, &capped(&d, "arm_none"), ALL_HEAD, 300.0, false).0, 1);
}

/// SMG wins close, the AR owns mid range: the Skink kills faster at 5-10 m (strictly through the default halo), the
/// Mako from 15 m, and past 25 m the Skink takes at least half as long again, hip or aimed, sprayed or all torso.
#[test]
fn the_skink_wins_close_and_the_mako_owns_mid_range() {
    let d = GameData::embedded();
    let halos = [default_halo(&d), capped(&d, "arm_none")];
    for (i, halo) in halos.iter().enumerate() {
        for mix in [ALL_TORSO, BODY_SPRAY] {
            for aimed in [false, true] {
                let t = |w: &str, r: f32| ttk(&d, w, halo, mix, r, aimed).1;
                let at = |r: f32| format!("{} {mix:?} aimed {aimed} at {r} m", halo.id);
                for r in [5.0, 10.0] {
                    let (s, m) = (t(SKINK, r), t(MAKO, r));
                    assert!(if i == 0 { s < m } else { s <= m + 1e-6 }, "{}: skink {s} mako {m}", at(r));
                }
                for r in [15.0, 25.0, 40.0] {
                    let (s, m) = (t(SKINK, r), t(MAKO, r));
                    assert!(m < s, "{}: skink {s} mako {m}", at(r));
                    if r >= 25.0 {
                        assert!(s >= 1.5 * m, "{}: skink {s} mako {m}", at(r));
                    }
                }
            }
        }
    }
}

/// Damage per second by range (hip fire rate): the Skink leads up close and falls under 60 % of the Mako's from
/// 25 m; the Warden's is low on paper, it is the one-shot pick.
#[test]
fn damage_per_second_by_range() {
    let d = GameData::embedded();
    let dps = |w: &str, r: f32| {
        let w = d.weapon(w).unwrap();
        falloff(w, r) / w.bolt_cycle_s.unwrap_or(60.0 / w.rpm)
    };
    #[rustfmt::skip]
    let want = [
        (5.0, 552.0, 720.0), (15.0, 552.0, 586.7), (25.0, 552.0, 320.0), (40.0, 498.0, 200.0), (60.0, 442.0, 200.0),
    ];
    for (r, mako, skink) in want {
        assert!((dps(MAKO, r) - mako).abs() < 0.5, "mako at {r} m: {}", dps(MAKO, r));
        assert!((dps(SKINK, r) - skink).abs() < 0.5, "skink at {r} m: {}", dps(SKINK, r));
        assert!((dps(WARDEN, r) - 128.0).abs() < 0.5, "warden at {r} m");
        if r >= 25.0 {
            assert!(dps(SKINK, r) < 0.6 * dps(MAKO, r), "{r} m");
        }
    }
}

/// Recoil is the skill check now, and it must stay learnable. A player who learned the Mako's pattern (pull down
/// hard to the 8th round, then gently on to the 15th, no sideways correction) keeps a 15-round aimed spray on the
/// torso of a target 15 m away. Without pulling down, the climb leaves the torso within four rounds.
#[test]
fn a_learned_pull_keeps_an_aimed_mako_spray_on_a_torso_at_15_m() {
    let d = GameData::embedded();
    let w = d.weapon(MAKO).unwrap();
    let RecoilSpec::Pattern(p) = &w.recoil else { panic!("the Mako has a pattern") };
    let pattern = d.recoil_pattern(w).unwrap();
    const ROUNDS: usize = 15;
    const KNEE: usize = 8;
    // The view climb (pitch, yaw right; degrees) each round leaves with: the aimed kicks of the rounds before it.
    let mut climb = vec![(0.0_f32, 0.0_f32)];
    for n in 1..ROUNDS as u32 {
        let (kp, ky) = pattern.kick(n);
        let last = climb[climb.len() - 1];
        climb.push((last.0 + kp * p.ads_mult, last.1 + ky * p.ads_mult));
    }
    // The learned pull: straight down to where round KNEE would go, then on to round ROUNDS.
    let (k, e) = (KNEE - 1, ROUNDS - 1);
    let pull = |i: usize| {
        if i <= k {
            climb[k].0 * i as f32 / k as f32
        } else {
            climb[k].0 + (climb[e].0 - climb[k].0) * (i - k) as f32 / (e - k) as f32
        }
    };
    let eye = Vec3::Y * d.movement.eye_height.stand;
    let target = Pose { pos: Vec3::new(0.0, 0.0, -15.0), yaw: 0.0, stance: Stance::Stand };
    let torso = d.hitboxes.boxes.iter().find(|b| b.zone == Zone::Torso).unwrap();
    let aim = (target.pos + Vec3::new(torso.center.0, torso.center.1, torso.center.2) - eye).normalize();
    let (yaw0, pitch0) = ((-aim.x).atan2(-aim.z), aim.y.asin());
    // Standing still and aimed there is no random spread at all now (DESIGN_DELTAS.md section 12; this pin used the
    // old 0.08 deg `ads_still` cone), so the learned pull puts every round exactly where it aims.
    let spread = cone(&d, MAKO, &still(), 1.0, 0.0);
    assert_eq!(spread, 0.0);
    let zones = |pulled: bool| -> Vec<Option<Zone>> {
        (0..ROUNDS)
            .map(|i| {
                let down = if pulled { pull(i) } else { 0.0 };
                let pitch = pitch0 + (climb[i].0 - down).to_radians();
                // Yaw right turns the view to negative yaw (as the client applies the kick).
                let yaw = yaw0 - climb[i].1.to_radians();
                let dir = shot_direction(yaw, pitch, spread, shot_seed(7, i as u32 + 1));
                hitbox::raycast(&d, &target, eye, dir, 100.0).map(|(z, _)| z)
            })
            .collect()
    };
    let pulled = zones(true);
    assert!(pulled.iter().all(|z| *z == Some(Zone::Torso)), "pulled: {pulled:?}");
    let free = zones(false);
    let left = free.iter().position(|z| *z != Some(Zone::Torso)).expect("the climb leaves the torso");
    assert!(left < 4, "without pulling down the spray leaves the torso at round {}: {free:?}", left + 1);
}

fn still() -> WeaponEnv {
    WeaponEnv {
        mode: MoveMode::Ground,
        sprinting: false,
        crouched: false,
        speed_frac: 0.0,
        broken_arms: false,
        hands_busy: false,
    }
}

/// The random cone (degrees) of `weapon`'s next shot in `env` (default parts), `ads` of the way aimed, with `bloom`
/// (hip degrees) of sustained-fire bloom built up.
fn cone(d: &GameData, weapon: &str, env: &WeaponEnv, ads: f32, bloom: f32) -> f32 {
    let l = WeaponLoadout::resolve(d, weapon, &[AmmoChoice::STANDARD], &[]).unwrap();
    let mut s = WeaponState::new(d, &l);
    s.action = WeaponAction::Ready;
    (s.ads, s.bloom_deg) = (ads, bloom);
    s.spread_deg(d, l.spec(d), &l, env)
}

/// Playtest round 2 (DIRECTION_LOG 16 and 17): aimed shots stay accurate on the move. Aimed at the head of a target
/// 25 m away (the Warden: 50 m), with the most sustained-fire bloom built up, every shot hits the head (real
/// hitboxes, 512 shooters each) whatever the shooter does: walking, crouch walking, jogging, sprinting, sliding, in
/// the air, on a zipline or the jetpack. From the hip the same shots miss the head most of the time: hip fire keeps
/// its movement penalty.
#[test]
fn aimed_shots_on_the_move_hit_a_head() {
    let d = GameData::embedded();
    let speed = &d.movement.speed;
    let sprint = speed.sprint / speed.jog;
    let ground =
        |speed_frac: f32, crouched: bool| WeaponEnv { speed_frac, crouched, sprinting: speed_frac > 1.0, ..still() };
    let states = [
        ("walk", ground(speed.walk / speed.jog, false)),
        ("crouch walk", ground(speed.crouch / speed.jog, true)),
        ("jog", ground(1.0, false)),
        ("sprint", ground(sprint, false)),
        ("slide", WeaponEnv { mode: MoveMode::Slide, speed_frac: 2.0, ..still() }),
        ("air", WeaponEnv { mode: MoveMode::Air, speed_frac: sprint, ..still() }),
        ("zipline", WeaponEnv { mode: MoveMode::Zipline, speed_frac: 11.0 / speed.jog, ..still() }),
        ("jetpack", WeaponEnv { mode: MoveMode::Jetpack, speed_frac: 1.0, ..still() }),
    ];
    let head = d.hitboxes.boxes.iter().find(|b| b.zone == Zone::Head).unwrap();
    let eye = Vec3::Y * d.movement.eye_height.stand;
    for (weapon, range) in [(MAKO, 25.0), (SKINK, 25.0), (WARDEN, 50.0)] {
        let target = Pose { pos: Vec3::new(0.0, 0.0, -range), yaw: 0.0, stance: Stance::Stand };
        let aim = (target.pos + Vec3::new(head.center.0, head.center.1, head.center.2) - eye).normalize();
        let (yaw, pitch) = ((-aim.x).atan2(-aim.z), aim.y.asin());
        let heads = |spread: f32| {
            (0..512)
                .filter(|i| {
                    let dir = shot_direction(yaw, pitch, spread, shot_seed(3, *i));
                    hitbox::raycast(&d, &target, eye, dir, 200.0).map(|(z, _)| z) == Some(Zone::Head)
                })
                .count()
        };
        let bloom = d.weapon(weapon).unwrap().spread_deg.bloom_max_hip;
        let mut hip_heads = 0;
        for (name, env) in states {
            let aimed = cone(&d, weapon, &env, ADS_AIMED, bloom);
            assert_eq!(heads(aimed), 512, "{weapon} {name}: aimed cone {aimed} deg");
            hip_heads += heads(cone(&d, weapon, &env, 0.0, bloom));
        }
        assert!(hip_heads < 512 * states.len() / 4, "{weapon}: hip fire on the move hits the head {hip_heads} times");
    }
}
