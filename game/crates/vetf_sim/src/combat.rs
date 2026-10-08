//! Damage pipeline (design/systems/diagrams/damage_flow.png): raw damage -> halo -> zone HP -> result.
//!
//! Shield rule (user direction): an arc with shield left takes the whole bullet, scaled by the ammo's
//! shield-damage multiplier (`pen`) for that arc's tier; zone HP takes nothing until the arc is down, and
//! the bullet that breaks it carries its leftover on to HP. Runs on the host only. The Mako (pen 1.0) is
//! checked against `design/systems/tools/slice_data.py` in the tests.

use crate::data::{AmmoSpec, ArmorStats, BleedSpec, Core, RegenSpec, SpillToTorso, WeaponSpec};
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
    pub bleeding: Bleeding,
}

/// Fragment bleeding per zone (Shrapnel). Each fragment adds a stack; untreated zones lose `active` HP/s.
/// Treatment (a future medkit) drops a zone to its `residual`, which stays until respawn: fragments
/// "cannot be removed fully".
#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
pub struct Bleeding {
    pub stacks: ZoneTable<u8>,
    /// HP per second the zone is losing now.
    pub active: ZoneTable<f32>,
    /// What treatment cannot remove (HP per second).
    pub residual: ZoneTable<f32>,
}

impl Bleeding {
    /// A fragment lodged in `zone`. Stacks past the round's maximum do nothing.
    pub fn add_stack(&mut self, zone: Zone, spec: &BleedSpec) -> bool {
        if self.stacks[zone] >= spec.max_stacks {
            return false;
        }
        self.stacks[zone] += 1;
        self.active[zone] += spec.hp_per_s;
        self.residual[zone] += spec.residual_hp_per_s;
        true
    }

    /// Stop what can be stopped in `zone`.
    pub fn treat(&mut self, zone: Zone) {
        self.active[zone] = self.residual[zone];
    }

    pub fn is_bleeding(&self) -> bool {
        self.active.iter().any(|(_, r)| *r > 0.0)
    }

    pub fn zones(&self) -> ZoneSet {
        let mut s = ZoneSet::EMPTY;
        for (z, r) in self.active.iter() {
            if *r > 0.0 {
                s.insert(z);
            }
        }
        s
    }
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
        Self { hp: max, max, dead: false, bleeding: Bleeding::default() }
    }

    /// Lose this tick's bleeding (broken limbs keep spilling into the torso).
    pub fn tick_bleeding(&mut self, spill: &SpillToTorso, dt: f32) -> HpOutcome {
        let mut out = HpOutcome::default();
        for zone in Zone::ALL {
            let rate = self.bleeding.active[zone];
            if rate > 0.0 {
                self.apply_inner(zone, rate * dt, spill, &mut out);
            }
        }
        out
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
    /// Damage that goes on to zone HP: the leftover of an arc-breaking bullet, or everything when the
    /// zone is uncovered, its arc is down, or the round slipped past the shield.
    pub to_hp: f32,
    pub absorbed: f32,
    pub broke: bool,
    pub bypassed: bool,
}

impl HaloState {
    pub fn full(spec: &HaloSpec) -> Self {
        Self { shield: spec.capacity, regen_wait_s: 0.0 }
    }

    pub fn total(&self) -> f32 {
        self.shield.iter().map(|(_, s)| *s).sum()
    }

    /// A bullet of `damage` (falloff, zone and ammo damage multipliers applied) hits `zone`.
    ///
    /// While the zone's arc holds, the shield takes `damage x pen[tier]` and HP takes nothing; the bullet
    /// that breaks the arc carries its leftover (converted back by `/ pen`) on to HP. `bypass_roll` in
    /// [0, 1) lets a round with a bypass chance slip past the shield entirely.
    pub fn absorb(&mut self, spec: &HaloSpec, zone: Zone, damage: f32, ammo: &AmmoSpec, bypass_roll: f32) -> Absorb {
        let tier = spec.tiers[zone];
        let shield = &mut self.shield[zone];
        if tier == 0 || *shield <= 0.0 {
            return Absorb { to_hp: damage * ammo.flesh_mult, ..Default::default() };
        }
        if bypass_roll < ammo.bypass_chance {
            return Absorb { to_hp: damage * ammo.flesh_mult, bypassed: true, ..Default::default() };
        }
        let pen = ammo.pen_for_tier(tier);
        let shield_dmg = damage * pen;
        let absorbed = shield.min(shield_dmg);
        *shield -= absorbed;
        let broke = *shield <= 0.0;
        if broke {
            *shield = 0.0;
        }
        let leftover = if pen > 0.0 { (shield_dmg - absorbed) / pen } else { 0.0 };
        Absorb { to_hp: leftover * ammo.flesh_mult, absorbed, broke, bypassed: false }
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
    /// Bullet damage after falloff, zone and ammo damage multipliers.
    pub raw: f32,
    pub absorbed: f32,
    /// Damage that reached zone HP before spill.
    pub to_hp: f32,
    pub shield_broke: bool,
    /// The round slipped past a holding shield (Shrapnel).
    pub bypassed: bool,
    /// A fragment started (or deepened) a bleed.
    pub bleed_added: bool,
    pub newly_broken: ZoneSet,
    pub killed: bool,
}

impl HitReport {
    pub fn hit_shield(&self) -> bool {
        self.absorbed > 0.0
    }
}

/// Resolve one bullet against a target's halo and health (steps 4-6 of the damage flow).
/// `spill` is the base limb -> torso spill; the ammo scales it. `bypass_roll` is a deterministic [0, 1)
/// roll for rounds with a bypass chance (pass 1.0 for "never").
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
    bypass_roll: f32,
) -> HitReport {
    let raw = raw_damage(weapon, range_m, zone) * ammo.damage_mult;
    let a = halo.absorb(halo_spec, zone, raw, ammo, bypass_roll);
    let hp = health.apply(zone, a.to_hp, &ammo.spill(spill));
    let bleed_added = match ammo.bleed {
        Some(b) if a.to_hp > 0.0 && !health.dead => health.bleeding.add_stack(zone, &b),
        _ => false,
    };
    halo.on_damaged(halo_spec, a.broke);
    HitReport {
        zone: Some(zone),
        raw,
        absorbed: a.absorbed,
        to_hp: a.to_hp,
        shield_broke: a.broke,
        bypassed: a.bypassed,
        bleed_added,
        newly_broken: hp.newly_broken,
        killed: hp.died,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{AmmoChoice, AmmoKind, GameData, WeaponClass};

    const NEVER: f32 = 1.0;

    fn ammo(d: &GameData, weapon: &str, kind: AmmoKind, tier: u8) -> AmmoSpec {
        d.ammo_for(d.weapon(weapon).unwrap(), AmmoChoice { kind, tier }).unwrap()
    }

    fn class_ammo(d: &GameData, class: WeaponClass, kind: AmmoKind, tier: u8) -> AmmoSpec {
        d.ammo.resolve(class, AmmoChoice { kind, tier }).unwrap()
    }

    fn hit(
        d: &GameData,
        w: &WeaponSpec,
        a: &AmmoSpec,
        z: Zone,
        spec: &HaloSpec,
        halo: &mut HaloState,
        hp: &mut Health,
    ) -> HitReport {
        resolve_hit(w, a, 10.0, z, &d.weapons.spill_to_torso, spec, halo, hp, NEVER)
    }

    /// The Mako with the design's damage numbers (design/systems/data/weapons.slice.json). The live Mako hits harder
    /// since playtest round 1 (game/DESIGN_DELTAS.md section 9; pinned in tests/balance.rs); the damage model is
    /// still checked against the design's Python model with the numbers that model uses.
    fn design_mako(d: &GameData) -> WeaponSpec {
        let mut w = d.weapon("ar7_mako").unwrap().clone();
        w.damage = 37.0;
        w.falloff = vec![(0.0, 37.0), (25.0, 37.0), (50.0, 31.0), (80.0, 27.0)];
        w.min_damage = 27.0;
        w.zone_mult = ZoneTable { head: 1.3, torso: 1.0, arms: 0.8, legs: 0.85 };
        w
    }

    fn shots_to_kill(d: &GameData, weapon: &str, ammo: &AmmoSpec, armor: &str, zone: Zone, range: f32) -> u32 {
        let w = &design_mako(d);
        assert_eq!(weapon, "ar7_mako", "the oracle covers the design's Mako");
        let spec = HaloSpec::from_armor(&d.armor.resolve_id(armor).unwrap());
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        for n in 1..400 {
            if resolve_hit(w, ammo, range, zone, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp, NEVER).killed {
                return n;
            }
        }
        panic!("never died");
    }

    /// The design's model has one shield pool per halo. With every arc at the full core capacity, the
    /// per-arc model must give the design's numbers when all shots hit one zone.
    fn design_equivalent() -> GameData {
        let mut d = GameData::embedded();
        d.armor.zone_capacity_share = ZoneTable::splat(1.0);
        d
    }

    /// Oracle: `shots_to_kill` for the Mako from design/systems/tools/slice_data.py (head, torso, arms,
    /// legs) per armor preset at 10 / 40 / 80 m. The design's Mako pierces nothing and our Mako Standard
    /// has pen 1.0 everywhere, so the two models agree exactly.
    #[test]
    fn mako_shots_to_kill_match_design_model() {
        #[rustfmt::skip]
        let table: &[(f32, &str, [u32; 4])] = &[
            (10.0, "arm_none", [1, 4, 10, 9]), (10.0, "arm_phase_runner", [1, 5, 10, 9]),
            (10.0, "arm_phase_ghost", [3, 4, 10, 9]), (10.0, "arm_mender_scout", [3, 5, 10, 9]),
            (10.0, "arm_volt_line", [1, 6, 13, 9]), (10.0, "arm_bulwark_assault", [4, 7, 14, 9]),
            (10.0, "arm_bulwark_jugg", [5, 8, 15, 14]),
            (40.0, "arm_none", [2, 4, 11, 10]), (40.0, "arm_phase_runner", [2, 5, 11, 10]),
            (40.0, "arm_phase_ghost", [4, 4, 11, 10]), (40.0, "arm_mender_scout", [3, 6, 11, 10]),
            (40.0, "arm_volt_line", [2, 7, 14, 10]), (40.0, "arm_bulwark_assault", [5, 8, 15, 10]),
            (40.0, "arm_bulwark_jugg", [5, 9, 17, 15]),
            (80.0, "arm_none", [2, 5, 13, 12]), (80.0, "arm_phase_runner", [2, 6, 13, 12]),
            (80.0, "arm_phase_ghost", [4, 5, 13, 12]), (80.0, "arm_mender_scout", [3, 7, 13, 12]),
            (80.0, "arm_volt_line", [2, 9, 18, 12]), (80.0, "arm_bulwark_assault", [5, 10, 19, 12]),
            (80.0, "arm_bulwark_jugg", [6, 11, 21, 19]),
        ];
        let d = design_equivalent();
        let std = ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        for (range, armor, expect) in table {
            let got = Zone::ALL.map(|z| shots_to_kill(&d, "ar7_mako", &std, armor, z, *range));
            assert_eq!(&got, expect, "{armor} at {range} m");
        }
    }

    #[test]
    fn falloff_curve() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let warden = d.weapon("vk50_warden").unwrap();
        for (r, want) in
            [(0.0, 46.0), (25.0, 46.0), (30.0, 44.5), (37.5, 42.25), (50.0, 38.5), (80.0, 33.5), (300.0, 33.5)]
        {
            assert!((falloff(mako, r) - want).abs() < 1e-4, "mako {r}");
        }
        let skink = d.weapon("sk9_skink").unwrap();
        for (r, want) in [(5.0, 36.0), (10.0, 36.0), (15.0, 29.333), (25.0, 16.0), (32.5, 13.0), (60.0, 10.0)] {
            assert!((falloff(skink, r) - want).abs() < 1e-3, "skink {r}");
        }
        for (r, want) in [(60.0, 160.0), (90.0, 155.0), (135.0, 145.0), (400.0, 140.0)] {
            assert!((falloff(warden, r) - want).abs() < 1e-4, "warden {r}");
        }
    }

    /// Core rule: HP takes nothing while the arc holds; the arc-breaking bullet carries its leftover.
    #[test]
    fn hp_only_after_the_arc_breaks_and_leftover_carries() {
        let d = GameData::embedded();
        let w = &design_mako(&d);
        let std = ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        // Phase Runner: T1 torso arc, 35 shield.
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_phase_runner").unwrap());
        let (mut halo, mut hp) = (HaloState::full(&spec), Health::new(d.armor.zone_hp));
        let r = hit(&d, w, &std, Zone::Torso, &spec, &mut halo, &mut hp);
        assert!(r.shield_broke && (r.absorbed - 35.0).abs() < 1e-4);
        assert!((hp.hp.torso - (120.0 - 2.0)).abs() < 1e-4, "37 - 35 = 2 carries on: {}", hp.hp.torso);
        // a T2 arc (Mender Scout, 60) holds a whole bullet: no HP damage at all
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_mender_scout").unwrap());
        let (mut halo, mut hp) = (HaloState::full(&spec), Health::new(d.armor.zone_hp));
        let r = hit(&d, w, &std, Zone::Torso, &spec, &mut halo, &mut hp);
        assert_eq!(r.to_hp, 0.0);
        assert_eq!(hp.hp.torso, 120.0);
        assert_eq!(halo.shield.torso, 60.0 - 37.0);
    }

    #[test]
    fn pen_scales_shield_damage_and_converts_leftover_back() {
        let d = GameData::embedded();
        let w = &design_mako(&d);
        let ap = ammo(&d, "ar7_mako", AmmoKind::ArmorPiercing, 3);
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_phase_runner").unwrap());
        let (mut halo, mut hp) = (HaloState::full(&spec), Health::new(d.armor.zone_hp));
        let r = hit(&d, w, &ap, Zone::Torso, &spec, &mut halo, &mut hp);
        let dmg = 37.0 * ap.damage_mult;
        let pen = ap.pen[0];
        let leftover = (dmg * pen - 35.0) / pen;
        assert!((r.to_hp - leftover).abs() < 1e-3, "{} vs {leftover}", r.to_hp);
    }

    #[test]
    fn broken_legs_spill_to_torso() {
        let d = GameData::embedded();
        let w = &design_mako(&d);
        let ammo = &ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        let spec = HaloSpec::NONE;
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        let mut broke = ZoneSet::EMPTY;
        for _ in 0..3 {
            broke.0 |= hit(&d, w, ammo, Zone::Legs, &spec, &mut halo, &mut hp).newly_broken.0;
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
        let std = ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_mender_scout").unwrap());
        let r = spec.regen.unwrap();
        let mut halo = HaloState::full(&spec);
        let a = halo.absorb(&spec, Zone::Head, 30.0, &std, NEVER);
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
    fn uncovered_zone_takes_everything() {
        let d = GameData::embedded();
        let std = ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_phase_runner").unwrap());
        let mut halo = HaloState::full(&spec);
        let a = halo.absorb(&spec, Zone::Head, 50.0, &std, NEVER);
        assert_eq!(a.to_hp, 50.0);
        assert_eq!(halo.shield, spec.capacity);
    }

    /// User direction: SMG Standard only slightly out-damages normal against T1 arcs, nothing above.
    #[test]
    fn smg_standard_vs_arc_tiers() {
        let d = GameData::embedded();
        let smg = class_ammo(&d, WeaponClass::Smg, AmmoKind::Standard, 1);
        let t1 = HaloSpec::from_armor(&d.armor.resolve_id("arm_phase_runner").unwrap());
        let mut h = HaloState::full(&t1);
        let a = h.absorb(&t1, Zone::Torso, 20.0, &smg, NEVER);
        assert!((a.absorbed - 20.0 * smg.pen[0]).abs() < 1e-4 && a.absorbed >= 20.0);
        assert_eq!(a.to_hp, 0.0);
        let t2 = HaloSpec::from_armor(&d.armor.resolve_id("arm_mender_scout").unwrap());
        let mut h = HaloState::full(&t2);
        assert!(h.absorb(&t2, Zone::Torso, 20.0, &smg, NEVER).absorbed <= 20.0);
    }

    /// Each arc is its own pool: breaking the torso arc leaves the head and leg arcs at full strength.
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
            broke |= hit(&d, w, ammo, Zone::Torso, &spec, &mut halo, &mut hp).shield_broke;
        }
        assert!(broke);
        assert_eq!(halo.shield.torso, 0.0);
        assert_eq!(halo.shield.head, spec.capacity.head);
        assert_eq!(halo.shield.legs, spec.capacity.legs);
    }

    /// AP breaks arcs in fewer shots; RIP kills an unshielded target faster than Standard (SMG).
    #[test]
    fn ammo_types_trade_shield_against_flesh() {
        let d = GameData::embedded();
        let spill = &d.weapons.spill_to_torso;
        let shots_to_break = |w: &WeaponSpec, a: &AmmoSpec| {
            let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_bulwark_vanguard").unwrap());
            let (mut halo, mut hp) = (HaloState::full(&spec), Health::new(d.armor.zone_hp));
            (1..50)
                .find(|_| resolve_hit(w, a, 10.0, Zone::Torso, spill, &spec, &mut halo, &mut hp, NEVER).shield_broke)
                .unwrap()
        };
        let mako = d.weapon("ar7_mako").unwrap();
        let std = ammo(&d, "ar7_mako", AmmoKind::Standard, 1);
        assert!(shots_to_break(mako, &ammo(&d, "ar7_mako", AmmoKind::ArmorPiercing, 3)) < shots_to_break(mako, &std));
        // RIP vs flesh, using the Mako's numbers with SMG-class rounds (only the multipliers matter here)
        let kill_bare = |a: &AmmoSpec| {
            let spec = HaloSpec::NONE;
            let (mut halo, mut hp) = (HaloState::full(&spec), Health::new(d.armor.zone_hp));
            (1..50)
                .find(|_| resolve_hit(mako, a, 10.0, Zone::Legs, spill, &spec, &mut halo, &mut hp, NEVER).killed)
                .unwrap()
        };
        let smg_std = class_ammo(&d, WeaponClass::Smg, AmmoKind::Standard, 1);
        let rip3 = class_ammo(&d, WeaponClass::Smg, AmmoKind::Rip, 3);
        assert!(kill_bare(&rip3) < kill_bare(&smg_std));
        assert!(rip3.pen.iter().all(|p| *p < 1.0), "RIP is bad into shields");
    }

    /// Shrapnel (NPC-only): a lucky fragment slips past a holding shield and starts a bleed that
    /// treatment can only reduce to a residual.
    #[test]
    fn shrapnel_bypass_and_bleed() {
        let d = GameData::embedded();
        let w = d.weapon("ar7_mako").unwrap();
        let shr = ammo(&d, "ar7_mako", AmmoKind::Shrapnel, 3);
        let bleed = shr.bleed.unwrap();
        let spec = HaloSpec::from_armor(&d.armor.resolve_id("arm_bulwark_vanguard").unwrap());
        let (mut halo, mut hp) = (HaloState::full(&spec), Health::new(d.armor.zone_hp));
        // a roll above the chance: the shield takes it, no bleed
        let r = resolve_hit(w, &shr, 10.0, Zone::Torso, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp, 0.99);
        assert!(!r.bypassed && !r.bleed_added && r.to_hp == 0.0);
        // a roll under the chance: straight to HP, shield untouched, one stack of bleeding
        let shield_before = halo.shield.torso;
        let r = resolve_hit(w, &shr, 10.0, Zone::Torso, &d.weapons.spill_to_torso, &spec, &mut halo, &mut hp, 0.0);
        assert!(r.bypassed && r.bleed_added && r.to_hp > 0.0);
        assert_eq!(halo.shield.torso, shield_before);
        assert_eq!(hp.bleeding.stacks.torso, 1);
        let before = hp.hp.torso;
        hp.tick_bleeding(&d.weapons.spill_to_torso, 1.0);
        assert!((before - hp.hp.torso - bleed.hp_per_s).abs() < 1e-4);
        // treatment leaves the residual, which never goes away
        hp.bleeding.treat(Zone::Torso);
        let before = hp.hp.torso;
        hp.tick_bleeding(&d.weapons.spill_to_torso, 1.0);
        assert!((before - hp.hp.torso - bleed.residual_hp_per_s).abs() < 1e-4);
        assert!(hp.bleeding.is_bleeding());
        // stacks cap
        for _ in 0..10 {
            hp.bleeding.add_stack(Zone::Torso, &bleed);
        }
        assert_eq!(hp.bleeding.stacks.torso, bleed.max_stacks);
    }
}
