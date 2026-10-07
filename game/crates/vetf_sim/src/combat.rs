//! Damage pipeline (design/systems/diagrams/damage_flow.png): raw damage -> halo -> zone HP -> result.
//!
//! Runs on the host only. The model is checked against `design/systems/tools/slice_data.py` in the tests.

use crate::data::{ArmorStats, Core, RegenSpec, SpillToTorso, WeaponSpec};
use crate::zone::{Zone, ZoneSet, ZoneTable};
use serde::{Deserialize, Serialize};

/// Damage after range falloff, before zone multipliers. Linear between falloff points; past the last
/// point the weapon does `min_damage`.
pub fn falloff(weapon: &WeaponSpec, range_m: f32) -> f32 {
    let pts = &weapon.falloff;
    let Some(&(r0, d0)) = pts.first() else {
        return weapon.damage;
    };
    if range_m <= r0 {
        return d0;
    }
    for w in pts.windows(2) {
        let ((ra, da), (rb, db)) = (w[0], w[1]);
        if range_m <= rb {
            return da + (db - da) * (range_m - ra) / (rb - ra);
        }
    }
    weapon.min_damage
}

pub fn raw_damage(weapon: &WeaponSpec, range_m: f32, zone: Zone) -> f32 {
    falloff(weapon, range_m) * weapon.zone_mult[zone]
}

// ---------------------------------------------------------------------------------------------- health

/// Per-zone HP. Head or torso at 0 kills; arms or legs at 0 break and pass further damage to the torso.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Health {
    pub hp: ZoneTable<f32>,
    pub max: ZoneTable<f32>,
    pub dead: bool,
}

/// What a call to [`Health::apply`] did.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct HpOutcome {
    /// HP removed per zone (spill included), clamped to what the zone had left.
    pub removed: ZoneTable<f32>,
    pub newly_broken: ZoneSet,
    pub died: bool,
}

impl Health {
    pub fn new(max: ZoneTable<f32>) -> Self {
        Self { hp: max, max, dead: false }
    }

    pub fn is_broken(&self, zone: Zone) -> bool {
        !zone.is_vital() && self.hp[zone] <= 0.0
    }

    pub fn broken(&self) -> ZoneSet {
        let mut s = ZoneSet::EMPTY;
        for z in [Zone::Arms, Zone::Legs] {
            if self.is_broken(z) {
                s.insert(z);
            }
        }
        s
    }

    /// Apply `dmg` to `zone`, spilling to the torso for broken limbs.
    pub fn apply(&mut self, zone: Zone, dmg: f32, spill: &SpillToTorso) -> HpOutcome {
        let mut out = HpOutcome::default();
        self.apply_inner(zone, dmg, spill, &mut out);
        out
    }

    fn apply_inner(&mut self, zone: Zone, dmg: f32, spill: &SpillToTorso, out: &mut HpOutcome) {
        if dmg <= 0.0 || self.dead {
            return;
        }
        if let Some(f) = spill.factor(zone) {
            if self.hp[zone] <= 0.0 {
                self.apply_inner(Zone::Torso, dmg * f, spill, out);
                return;
            }
        }
        let before = self.hp[zone];
        self.hp[zone] = before - dmg;
        out.removed[zone] += dmg.min(before.max(0.0));
        if self.hp[zone] <= 0.0 {
            if zone.is_vital() {
                self.dead = true;
                out.died = true;
            } else {
                let over = -self.hp[zone];
                self.hp[zone] = 0.0;
                out.newly_broken.insert(zone);
                if let Some(f) = spill.factor(zone) {
                    self.apply_inner(Zone::Torso, over * f, spill, out);
                }
            }
        }
    }

    /// Heal a zone (items, Solace). Does nothing to the dead.
    pub fn heal(&mut self, zone: Zone, amount: f32) {
        if !self.dead {
            self.hp[zone] = (self.hp[zone].max(0.0) + amount).min(self.max[zone]);
        }
    }
}

// ---------------------------------------------------------------------------------------------- halo

/// Static description of the halo a player wears (resolved from an armor preset).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct HaloSpec {
    pub core: Option<Core>,
    pub tier: u8,
    pub coverage: ZoneSet,
    pub capacity: f32,
    pub regen: Option<RegenSpec>,
}

impl HaloSpec {
    pub const NONE: HaloSpec =
        HaloSpec { core: None, tier: 0, coverage: ZoneSet::EMPTY, capacity: 0.0, regen: None };

    pub fn from_armor(a: &ArmorStats) -> Self {
        Self { core: a.core, tier: a.tier, coverage: a.coverage_set(), capacity: a.capacity, regen: a.regen() }
    }
}

/// Live shield state.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct HaloState {
    pub shield: f32,
    /// Seconds until regen starts again.
    pub regen_wait_s: f32,
}

/// What the halo did with one hit.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Absorb {
    /// Damage that goes on to zone HP (pierce + overflow, or everything if the zone is not covered).
    pub to_hp: f32,
    pub absorbed: f32,
    pub broke: bool,
}

impl HaloState {
    pub fn full(spec: &HaloSpec) -> Self {
        Self { shield: spec.capacity, regen_wait_s: 0.0 }
    }

    pub fn absorb(&mut self, spec: &HaloSpec, zone: Zone, raw: f32, pierce_frac: f32) -> Absorb {
        if !spec.coverage.contains(zone) || self.shield <= 0.0 {
            return Absorb { to_hp: raw, ..Default::default() };
        }
        let pierce = raw * pierce_frac;
        let to_shield = raw - pierce;
        let absorbed = self.shield.min(to_shield);
        self.shield -= absorbed;
        let broke = self.shield <= 0.0;
        if broke {
            self.shield = 0.0;
        }
        Absorb { to_hp: pierce + (to_shield - absorbed), absorbed, broke }
    }

    /// Any damage taken (shield or HP) delays regen; a break delays it longer.
    pub fn on_damaged(&mut self, spec: &HaloSpec, broke: bool) {
        if let Some(r) = spec.regen {
            let wait = if broke { r.delay_after_break_s } else { r.delay_s };
            self.regen_wait_s = self.regen_wait_s.max(wait);
        }
    }

    pub fn tick(&mut self, spec: &HaloSpec, dt: f32) {
        let Some(r) = spec.regen else { return };
        if self.regen_wait_s > 0.0 {
            self.regen_wait_s = (self.regen_wait_s - dt).max(0.0);
            return;
        }
        self.shield = (self.shield + r.rate_per_s * dt).min(spec.capacity);
    }
}

// ---------------------------------------------------------------------------------------------- one hit

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct HitReport {
    pub zone: Option<Zone>,
    pub raw: f32,
    pub absorbed: f32,
    /// Damage that reached zone HP before spill (pierce + overflow).
    pub to_hp: f32,
    pub shield_broke: bool,
    pub newly_broken: ZoneSet,
    pub killed: bool,
}

impl HitReport {
    pub fn hit_shield(&self) -> bool {
        self.absorbed > 0.0
    }
}

/// Resolve one bullet against a target's halo and health (steps 4-6 of the damage flow).
pub fn resolve_hit(
    weapon: &WeaponSpec,
    range_m: f32,
    zone: Zone,
    spill: &SpillToTorso,
    halo_spec: &HaloSpec,
    halo: &mut HaloState,
    health: &mut Health,
) -> HitReport {
    let raw = raw_damage(weapon, range_m, zone);
    let a = halo.absorb(halo_spec, zone, raw, weapon.shield_pierce);
    let hp = health.apply(zone, a.to_hp, spill);
    halo.on_damaged(halo_spec, a.broke);
    HitReport {
        zone: Some(zone),
        raw,
        absorbed: a.absorbed,
        to_hp: a.to_hp,
        shield_broke: a.broke,
        newly_broken: hp.newly_broken,
        killed: hp.died,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::GameData;

    fn shots_to_kill(d: &GameData, weapon: &str, armor: &str, zone: Zone, range: f32) -> u32 {
        let w = d.weapon(weapon).unwrap();
        let a = d.armor.resolve_id(armor).unwrap();
        let spec = HaloSpec::from_armor(&a);
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        for n in 1..200 {
            if resolve_hit(w, range, zone, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp).killed {
                return n;
            }
        }
        panic!("never died");
    }

    /// Oracle: `shots_to_kill` from design/systems/tools/slice_data.py (head, torso, arms, legs for the
    /// Mako, then the Warden), per armor preset, at 10 / 40 / 80 m.
    #[test]
    fn shots_to_kill_match_design_model() {
        #[rustfmt::skip]
        let table: &[(f32, &str, [u32; 8])] = &[
            (10.0, "arm_none",            [1, 4, 10, 9, 1, 1, 3, 2]),
            (10.0, "arm_phase_runner",    [1, 5, 10, 9, 1, 1, 3, 2]),
            (10.0, "arm_phase_ghost",     [3, 4, 10, 9, 1, 1, 3, 2]),
            (10.0, "arm_mender_scout",    [3, 5, 10, 9, 1, 2, 3, 2]),
            (10.0, "arm_volt_line",       [1, 6, 13, 9, 1, 2, 3, 2]),
            (10.0, "arm_bulwark_assault", [4, 7, 14, 9, 1, 2, 4, 2]),
            (10.0, "arm_bulwark_jugg",    [5, 8, 15, 14, 1, 2, 4, 4]),
            (40.0, "arm_none",            [2, 4, 11, 10, 1, 1, 3, 2]),
            (40.0, "arm_phase_runner",    [2, 5, 11, 10, 1, 1, 3, 2]),
            (40.0, "arm_phase_ghost",     [4, 4, 11, 10, 1, 1, 3, 2]),
            (40.0, "arm_mender_scout",    [3, 6, 11, 10, 1, 2, 3, 2]),
            (40.0, "arm_volt_line",       [2, 7, 14, 10, 1, 2, 3, 2]),
            (40.0, "arm_bulwark_assault", [5, 8, 15, 10, 1, 2, 4, 2]),
            (40.0, "arm_bulwark_jugg",    [5, 9, 17, 15, 1, 2, 4, 4]),
            (80.0, "arm_none",            [2, 5, 13, 12, 1, 1, 3, 2]),
            (80.0, "arm_phase_runner",    [2, 6, 13, 12, 1, 1, 3, 2]),
            (80.0, "arm_phase_ghost",     [4, 5, 13, 12, 1, 1, 3, 2]),
            (80.0, "arm_mender_scout",    [3, 7, 13, 12, 1, 2, 3, 2]),
            (80.0, "arm_volt_line",       [2, 9, 18, 12, 1, 2, 3, 2]),
            (80.0, "arm_bulwark_assault", [5, 10, 19, 12, 1, 2, 4, 2]),
            (80.0, "arm_bulwark_jugg",    [6, 11, 21, 19, 1, 2, 4, 4]),
        ];
        let d = GameData::embedded();
        for (range, armor, expect) in table {
            let mut got = [0; 8];
            for (i, (w, z)) in ["ar7_mako", "vk50_warden"]
                .iter()
                .flat_map(|w| Zone::ALL.iter().map(move |z| (*w, *z)))
                .enumerate()
            {
                got[i] = shots_to_kill(&d, w, armor, z, *range);
            }
            assert_eq!(&got, expect, "{armor} at {range} m");
        }
    }

    #[test]
    fn falloff_curve() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let warden = d.weapon("vk50_warden").unwrap();
        for (r, want) in [(0.0, 37.0), (25.0, 37.0), (30.0, 35.8), (37.5, 34.0), (50.0, 31.0), (80.0, 27.0), (300.0, 27.0)] {
            assert!((falloff(mako, r) - want).abs() < 1e-4, "mako {r}");
        }
        for (r, want) in [(60.0, 160.0), (90.0, 155.0), (135.0, 145.0), (400.0, 140.0)] {
            assert!((falloff(warden, r) - want).abs() < 1e-4, "warden {r}");
        }
    }

    /// Worked example from the damage flow diagram: Warden torso hit at 30 m on a Volt Line.
    #[test]
    fn warden_vs_volt_line_worked_example() {
        let d = GameData::embedded();
        let w = d.weapon("vk50_warden").unwrap();
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_volt_line").unwrap());
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        let r = resolve_hit(w, 30.0, Zone::Torso, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp);
        assert_eq!(r.raw, 160.0);
        assert!(r.shield_broke);
        assert!((r.to_hp - 60.0).abs() < 1e-3); // pierce 48 + overflow 12
        assert!((hp.hp.torso - 60.0).abs() < 1e-3);
        assert!(!r.killed);
        let regen = spec.regen.unwrap();
        assert_eq!(halo.regen_wait_s, regen.delay_after_break_s);
    }

    #[test]
    fn broken_legs_spill_to_torso() {
        let d = GameData::embedded();
        let w = d.weapon("ar7_mako").unwrap();
        let spec = HaloSpec::NONE;
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        let mut broke = ZoneSet::EMPTY;
        for _ in 0..3 {
            broke.0 |= resolve_hit(w, 10.0, Zone::Legs, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp)
                .newly_broken
                .0;
        }
        // 3 x 31.45 = 94.35 on 85 HP legs: 9.35 over, x0.7 into the torso (design oracle: 113.455)
        assert!(broke.contains(Zone::Legs));
        assert_eq!(hp.hp.legs, 0.0);
        assert!((hp.hp.torso - 113.455).abs() < 1e-3);
        assert!(hp.is_broken(Zone::Legs));
    }

    #[test]
    fn shield_regen_waits_then_refills() {
        let d = GameData::embedded();
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_mender_scout").unwrap());
        let r = spec.regen.unwrap();
        let mut halo = HaloState::full(&spec);
        let a = halo.absorb(&spec, Zone::Head, 30.0, 0.0);
        halo.on_damaged(&spec, a.broke);
        assert_eq!(halo.shield, spec.capacity - 30.0);
        let dt = 1.0 / 60.0;
        let mut t = 0.0;
        while t < r.delay_s - 0.05 {
            halo.tick(&spec, dt);
            t += dt;
        }
        assert_eq!(halo.shield, spec.capacity - 30.0, "no regen during the delay");
        for _ in 0..(60.0 * (30.0 / r.rate_per_s + 0.2)) as usize {
            halo.tick(&spec, dt);
        }
        assert_eq!(halo.shield, spec.capacity);
    }

    #[test]
    fn uncovered_zone_bypasses_shield() {
        let d = GameData::embedded();
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_phase_runner").unwrap());
        let mut halo = HaloState::full(&spec);
        let a = halo.absorb(&spec, Zone::Head, 50.0, 0.0);
        assert_eq!(a.to_hp, 50.0);
        assert_eq!(halo.shield, spec.capacity);
    }
}
