//! Balance pins from the ammo balance pass (v2; see game/DESIGN_DELTAS.md section 1). These fail when a
//! number in `assets/data` moves a breakpoint the design relies on: the SMG and RIP leg spraying, AP and the
//! gear budget, the Warden's one-shot margins, and Shrapnel bleed timing. All at 10 m and hip fire unless
//! stated.

use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::ZoneTable;
use vetf_sim::combat::{HaloSpec, HaloState, Health, resolve_hit};
use vetf_sim::data::{AmmoChoice, AmmoKind, AmmoSpec, ArmorStats, WeaponClass};
use vetf_sim::weapon::fire_interval_ticks;

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
    // (torso, legs) per round, for bulwark_assault, volt_line, bulwark_vanguard, mender_medic.
    #[rustfmt::skip]
    let want: [[(u32, u32); 4]; 7] = [
        [(21, 11), (17, 11), (25, 16), (15, 14)],
        [(20, 10), (17, 10), (24, 15), (14, 13)],
        [(20, 9), (17, 9), (24, 14), (14, 12)],
        [(11, 13), (10, 13), (12, 15), (9, 14)],
        [(10, 13), (9, 13), (11, 14), (8, 14)],
        [(9, 13), (8, 13), (10, 14), (7, 13)],
        [(8, 12), (7, 12), (9, 13), (7, 13)],
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
    let want = [((21, 11), (25, 19)), ((20, 10), (24, 18)), ((20, 9), (24, 17))];
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
    assert_eq!(shots(&d, SKINK, &s, &none, Zone::Torso, 10.0), 5, "24 x 5 = 120 exactly");
    assert_eq!(shots(&d, SKINK, &rip3, &none, Zone::Torso, 10.0), 5, "28.8 x 4 = 115.2 < 120");
    assert_eq!(shots(&d, SKINK, &s, &capped(&d, "arm_mender_scout"), Zone::Torso, 10.0), 8);
    assert_eq!(shots(&d, MAKO, &std(&d, WeaponClass::AssaultRifle), &none, Zone::Torso, 10.0), 4);
    // N10: the SMG falls off hard; the Mako owns range.
    let volt = capped(&d, "arm_volt_line");
    let mako = std(&d, WeaponClass::AssaultRifle);
    for (range, armor, want_std, want_rip, want_mako) in
        [(30.0, &none, 10, 8, 4), (30.0, &volt, 17, 30, 7), (50.0, &volt, 17, 30, 8)]
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
fn ap_hits_shields_harder_but_keeps_the_mako_at_four_bare_torso_shots() {
    let d = GameData::embedded();
    let none = capped(&d, "arm_none");
    for tier in 1..=3 {
        let ap = ammo(&d, WeaponClass::AssaultRifle, AmmoKind::ArmorPiercing, tier);
        assert_eq!(shots(&d, MAKO, &ap, &none, Zone::Torso, 10.0), 4, "AP {tier}");
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

/// (armor preset, gun class, magazines as (type, tier), expected gear cost)
type GearRow<'a> = (&'a str, WeaponClass, &'a [(AmmoKind, u8)], u32);

/// Team-deathmatch gear: capped halo tiers plus every magazine's gear cost, against `tdm.gear_budget`.
#[test]
fn gear_budget_per_magazine() {
    let d = GameData::embedded();
    let budget = d.rules.tdm.gear_budget;
    assert_eq!(budget, 13);
    let ar = WeaponClass::AssaultRifle;
    let cost = |armor: &str, class: WeaponClass, mags: &[(AmmoKind, u8)]| {
        capped(&d, armor).gear_cost + mags.iter().map(|(k, t)| ammo(&d, class, *k, *t).gear_cost).sum::<u32>()
    };
    use AmmoKind::{ArmorPiercing as Ap, Rip, Standard as Std};
    #[rustfmt::skip]
    let table: &[GearRow] = &[
        ("arm_mender_scout", ar, &[(Std, 1); 4], 4),
        ("arm_bulwark_jugg", ar, &[(Std, 1)], 13),
        ("arm_bulwark_jugg", ar, &[(Ap, 1)], 15),
        ("arm_bulwark_assault", ar, &[(Ap, 1); 2], 13),
        ("arm_bulwark_assault", ar, &[(Ap, 1); 3], 15),
        ("arm_bulwark_assault", ar, &[(Ap, 2)], 13),
        ("arm_bulwark_assault", ar, &[(Ap, 3)], 15),
        ("arm_bulwark_vanguard", ar, &[(Ap, 3)], 15),
        ("arm_mender_scout", ar, &[(Ap, 3)], 10),
        ("arm_mender_scout", ar, &[(Ap, 3); 2], 16),
        ("arm_phase_runner", ar, &[(Ap, 3); 2], 13),
        ("arm_volt_line", ar, &[(Ap, 3)], 12),
        ("arm_none", ar, &[(Ap, 3); 6], 36),
        ("arm_bulwark_assault", WeaponClass::Smg, &[(Rip, 3)], 12),
        ("arm_bulwark_assault", WeaponClass::Smg, &[(Rip, 3); 2], 15),
        ("arm_mender_scout", WeaponClass::Smg, &[(Rip, 3); 3], 13),
        ("arm_mender_scout", WeaponClass::Smg, &[(Rip, 3); 4], 16),
    ];
    for (armor, class, mags, want) in table {
        assert_eq!(cost(armor, *class, mags), *want, "{armor} {mags:?}");
    }
    // A Heavy halo never carries AP III; a Light one always can.
    for p in &d.armor.presets {
        let a = capped(&d, &p.id);
        let fits = a.gear_cost + ammo(&d, ar, Ap, 3).gear_cost <= budget;
        match a.weight_class {
            vetf_sim::data::WeightClass::Heavy => assert!(!fits, "{}", p.id),
            vetf_sim::data::WeightClass::Light | vetf_sim::data::WeightClass::None => assert!(fits, "{}", p.id),
            _ => {}
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
