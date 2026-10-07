//! Damage pipeline (design/systems/diagrams/damage_flow.png): raw damage -> halo -> zone HP -> result.
//!
//! Runs on the host only. The model is checked against `design/systems/tools/slice_data.py` in the tests.

use crate::data::{AmmoSpec, ArmorStats, Core, RegenSpec, SpillToTorso, WeaponSpec};
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

/// Bullet damage at a range on a zone, before the halo and the ammo's shield / flesh multipliers.
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
        if let Some(f) = spill.factor(zone)
            && self.hp[zone] <= 0.0
        {
            self.apply_inner(Zone::Torso, dmg * f, spill, out);
            return;
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

/// Static description of the halo a player wears (resolved from an armor preset): one core type and
/// one arc per zone, each with its own tier and shield capacity.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct HaloSpec {
    pub core: Option<Core>,
    pub tiers: ZoneTable<u8>,
    pub capacity: ZoneTable<f32>,
    pub regen: Option<RegenSpec>,
}

impl HaloSpec {
    pub const NONE: HaloSpec = HaloSpec {
        core: None,
        tiers: ZoneTable { head: 0, torso: 0, arms: 0, legs: 0 },
        capacity: ZoneTable { head: 0.0, torso: 0.0, arms: 0.0, legs: 0.0 },
        regen: None,
    };

    pub fn from_armor(a: &ArmorStats) -> Self {
        Self { core: a.core, tiers: a.tiers, capacity: a.arc_capacity, regen: a.regen() }
    }

    pub fn coverage(&self) -> ZoneSet {
        let mut s = ZoneSet::EMPTY;
        for (z, t) in self.tiers.iter() {
            if *t > 0 {
                s.insert(z);
            }
        }
        s
    }

    pub fn total_capacity(&self) -> f32 {
        self.capacity.iter().map(|(_, c)| *c).sum()
    }
}

/// Live shield state: one pool per arc.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct HaloState {
    pub shield: ZoneTable<f32>,
    /// Seconds until regen starts again (shared by all arcs).
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

    pub fn total(&self) -> f32 {
        self.shield.iter().map(|(_, s)| *s).sum()
    }

    /// A hit on `zone`. The arc's tier and the ammo decide how much pierces straight to HP; the rest
    /// hits the arc's shield (scaled by the ammo's shield multiplier) and any overflow carries on to HP.
    pub fn absorb(&mut self, spec: &HaloSpec, zone: Zone, raw: f32, ammo: &AmmoSpec) -> Absorb {
        let tier = spec.tiers[zone];
        let shield = &mut self.shield[zone];
        if tier == 0 || *shield <= 0.0 {
            return Absorb { to_hp: raw * ammo.flesh_mult, ..Default::default() };
        }
        let pierce = raw * ammo.pen_for_tier(tier);
        let rest = raw - pierce;
        let shield_dmg = rest * ammo.shield_mult;
        let absorbed = shield.min(shield_dmg);
        *shield -= absorbed;
        let broke = *shield <= 0.0;
        if broke {
            *shield = 0.0;
        }
        // Convert the unabsorbed shield damage back into bullet damage before it reaches HP.
        let leftover = if ammo.shield_mult > 0.0 { (shield_dmg - absorbed) / ammo.shield_mult } else { rest };
        Absorb { to_hp: (pierce + leftover) * ammo.flesh_mult, absorbed, broke }
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
        for z in Zone::ALL {
            self.shield[z] = (self.shield[z] + r.rate_per_s * dt).min(spec.capacity[z]);
        }
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
#[allow(clippy::too_many_arguments)]
pub fn resolve_hit(
    weapon: &WeaponSpec,
    ammo: &AmmoSpec,
    range_m: f32,
    zone: Zone,
    spill: &SpillToTorso,
    halo_spec: &HaloSpec,
    halo: &mut HaloState,
    health: &mut Health,
) -> HitReport {
    let raw = raw_damage(weapon, range_m, zone);
    let a = halo.absorb(halo_spec, zone, raw, ammo);
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
    use crate::data::{AmmoChoice, AmmoKind, GameData, WeaponClass};

    fn ammo(d: &GameData, weapon: &str, kind: AmmoKind, tier: u8) -> AmmoSpec {
        d.ammo_for(d.weapon(weapon).unwrap(), AmmoChoice { kind, tier }).unwrap()
    }

    fn shots_to_kill(d: &GameData, weapon: &str, ammo: &AmmoSpec, armor: &str, zone: Zone, range: f32) -> u32 {
        let w = d.weapon(weapon).unwrap();
        let a = d.armor.resolve_id(armor).unwrap();
        let spec = HaloSpec::from_armor(&a);
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        for n in 1..200 {
            if resolve_hit(w, ammo, range, zone, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp).killed {
                return n;
            }
        }
        panic!("never died");
    }

    fn flat_pen(pen: f32) -> AmmoSpec {
        AmmoSpec {
            choice: AmmoChoice::STANDARD,
            label: "flat".into(),
            pen: [pen; 4],
            shield_mult: 1.0,
            flesh_mult: 1.0,
        }
    }

    /// The design's model has one shield pool and a flat pierce per weapon (Mako 0, Warden 0.3).
    /// With every arc at the full core capacity and a flat-pen ammo, our per-arc model must give the
    /// same numbers when all shots hit one zone.
    fn design_equivalent() -> GameData {
        let mut d = GameData::embedded();
        d.armor.zone_capacity_share = ZoneTable::splat(1.0);
        d
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
        let d = design_equivalent();
        for (range, armor, expect) in table {
            let mut got = [0; 8];
            for (i, (w, z)) in
                ["ar7_mako", "vk50_warden"].iter().flat_map(|w| Zone::ALL.iter().map(move |z| (*w, *z))).enumerate()
            {
                let ammo = flat_pen(if w == "ar7_mako" { 0.0 } else { 0.3 });
                got[i] = shots_to_kill(&d, w, &ammo, armor, z, *range);
            }
            assert_eq!(&got, expect, "{armor} at {range} m");
        }
    }

    #[test]
    fn falloff_curve() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let warden = d.weapon("vk50_warden").unwrap();
        for (r, want) in
            [(0.0, 37.0), (25.0, 37.0), (30.0, 35.8), (37.5, 34.0), (50.0, 31.0), (80.0, 27.0), (300.0, 27.0)]
        {
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
        let ammo = &ammo(&d, "vk50_warden", AmmoKind::Standard, 1);
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_volt_line").unwrap());
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        let r = resolve_hit(w, ammo, 30.0, Zone::Torso, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp);
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
        let ammo = &ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        let spec = HaloSpec::NONE;
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        let mut broke = ZoneSet::EMPTY;
        for _ in 0..3 {
            broke.0 |= resolve_hit(w, ammo, 10.0, Zone::Legs, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp)
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
        let a = halo.absorb(&spec, Zone::Head, 30.0, &flat_pen(0.0));
        halo.on_damaged(&spec, a.broke);
        assert_eq!(halo.shield.head, spec.capacity.head - 30.0);
        let dt = 1.0 / 60.0;
        let mut t = 0.0;
        while t < r.delay_s - 0.05 {
            halo.tick(&spec, dt);
            t += dt;
        }
        assert_eq!(halo.shield.head, spec.capacity.head - 30.0, "no regen during the delay");
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
        let a = halo.absorb(&spec, Zone::Head, 50.0, &flat_pen(0.0));
        assert_eq!(a.to_hp, 50.0);
        assert_eq!(halo.shield, spec.capacity);
    }

    /// User direction: SMG ammo slightly pierces T1 and nothing above.
    #[test]
    fn smg_ammo_only_pierces_tier_one() {
        let d = GameData::embedded();
        let smg = &d.ammo.resolve(WeaponClass::Smg, AmmoChoice::STANDARD).unwrap();
        let t1 = HaloSpec::from_armor(&d.armor.resolve_id("arm_phase_runner").unwrap());
        let mut h = HaloState::full(&t1);
        let a = h.absorb(&t1, Zone::Torso, 30.0, smg);
        assert!((a.to_hp - 30.0 * smg.pen[0]).abs() < 1e-4, "slight pen through T1: {}", a.to_hp);
        assert!(a.to_hp > 0.0);
        let t2 = HaloSpec::from_armor(&d.armor.resolve_id("arm_mender_scout").unwrap());
        let mut h = HaloState::full(&t2);
        assert_eq!(h.absorb(&t2, Zone::Torso, 30.0, smg).to_hp, 0.0);
    }

    /// Each arc is its own pool: breaking the torso arc leaves the head arc at full strength,
    /// and a leg arc can be sprayed through separately.
    #[test]
    fn arcs_break_independently() {
        let d = GameData::embedded();
        let w = d.weapon("ar7_mako").unwrap();
        let ammo = &ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_bulwark_vanguard").unwrap());
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        let mut broke = false;
        for _ in 0..10 {
            broke |= resolve_hit(w, ammo, 10.0, Zone::Torso, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp)
                .shield_broke;
        }
        assert!(broke);
        assert_eq!(halo.shield.torso, 0.0);
        assert_eq!(halo.shield.head, spec.capacity.head);
        assert_eq!(halo.shield.legs, spec.capacity.legs);
    }

    /// Shrapnel breaks an arc in fewer shots than standard; RIP kills an unshielded target faster.
    #[test]
    fn ammo_types_trade_shield_against_flesh() {
        let d = GameData::embedded();
        let w = d.weapon("ar7_mako").unwrap();
        let spill = &d.weapons.spill_to_torso;
        let shots_to_break = |a: &AmmoSpec| {
            let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_bulwark_vanguard").unwrap());
            let (mut halo, mut hp) = (HaloState::full(&spec), Health::new(d.armor.zone_hp));
            (1..50)
                .find(|_| resolve_hit(w, a, 10.0, Zone::Torso, spill, &spec, &mut halo, &mut hp).shield_broke)
                .unwrap()
        };
        let std = ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        assert!(shots_to_break(&ammo(&d, "ar7_mako", AmmoKind::Shrapnel, 3)) < shots_to_break(&std));
        let kill_bare = |a: &AmmoSpec| {
            let spec = HaloSpec::NONE;
            let (mut halo, mut hp) = (HaloState::full(&spec), Health::new(d.armor.zone_hp));
            (1..50).find(|_| resolve_hit(w, a, 10.0, Zone::Torso, spill, &spec, &mut halo, &mut hp).killed).unwrap()
        };
        assert!(kill_bare(&ammo(&d, "ar7_mako", AmmoKind::Rip, 3)) < kill_bare(&std));
        // and AP gets more through a T3 arc than standard
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_volt_line").unwrap());
        let ap = ammo(&d, "ar7_mako", AmmoKind::ArmorPiercing, 3);
        let through = |a: &AmmoSpec| HaloState::full(&spec).absorb(&spec, Zone::Torso, 37.0, a).to_hp;
        assert!(through(&ap) > through(&std));
    }
}
