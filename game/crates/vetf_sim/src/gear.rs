//! Loadout gear: the custom halo a player builds (one core, a tier per arc) and the gear-budget price of a
//! whole loadout. The host (validation) and the Loadout screen (RESULT panel, ammo cost chips) use the same
//! functions, so they always agree. The deathmatch modes fix the core and price their one ammo type once
//! ([`kit_cost`], `rules.ron` `loadout`); the gun range prices every magazine ([`gear_cost`]).

use crate::data::{AmmoChoice, ArmorFile, ArmorPreset, ArmorStats, Core, GameData, Mode, WeaponSpec};
use crate::zone::{Zone, ZoneTable};
use serde::{Deserialize, Serialize};

/// A halo as a loadout picks it: one core and a tier per arc (0 = that arc is uncovered). All arcs at 0
/// means no halo; the core is then kept (so the screen remembers it) but does nothing.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct HaloChoice {
    pub core: Core,
    pub tiers: ZoneTable<u8>,
}

impl Default for HaloChoice {
    fn default() -> Self {
        Self { core: Core::Mender, tiers: ZoneTable::splat(0) }
    }
}

impl HaloChoice {
    /// The halo of an armor preset (a preset without a core keeps the default core, with no arcs).
    pub fn from_preset(p: &ArmorPreset) -> Self {
        match p.core {
            Some(core) => Self { core, tiers: p.tiers },
            None => Self::default(),
        }
    }

    /// Every arc limited to the loadout tier caps (rare-loot tiers are not for loadouts).
    pub fn capped(self, caps: ZoneTable<u8>) -> Self {
        Self { core: self.core, tiers: self.tiers.map(|z, t| (*t).min(caps[z])) }
    }

    /// No arc above its loadout cap.
    pub fn within_caps(&self, caps: ZoneTable<u8>) -> bool {
        Zone::ALL.iter().all(|z| self.tiers[*z] <= caps[*z])
    }

    /// Any arc covered.
    pub fn is_lit(&self) -> bool {
        self.tiers.iter().any(|(_, t)| *t > 0)
    }

    /// Protection score: the sum of the arc tiers (the halo's gear cost and its weight band).
    pub fn score(&self) -> u32 {
        self.tiers.iter().map(|(_, t)| *t as u32).sum()
    }

    /// Lowest and highest tier of the covered arcs (None without a halo).
    pub fn tier_range(&self) -> Option<(u8, u8)> {
        let lit: Vec<u8> = self.tiers.iter().map(|(_, t)| *t).filter(|t| *t > 0).collect();
        Some((*lit.iter().min()?, *lit.iter().max()?))
    }

    /// As an armor preset (id `custom`), for [`ArmorFile::resolve`].
    pub fn preset(&self) -> ArmorPreset {
        let lit = self.is_lit();
        ArmorPreset {
            id: "custom".into(),
            name: if lit { self.core.label().to_string() } else { "No halo".into() },
            core: lit.then_some(self.core),
            tiers: if lit { self.tiers } else { ZoneTable::splat(0) },
        }
    }
}

impl ArmorFile {
    /// Resolve a custom halo (no caps applied: check [`HaloChoice::within_caps`] first).
    pub fn resolve_halo(&self, halo: &HaloChoice) -> ArmorStats {
        self.resolve(&halo.preset())
    }
}

/// Gear-budget points of a loadout, split as the RESULT panel shows them.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct GearCost {
    /// The halo: the sum of its arc tiers.
    pub halo: u32,
    /// Every magazine's ammo, each priced on its own.
    pub ammo: u32,
}

impl GearCost {
    pub fn total(&self) -> u32 {
        self.halo + self.ammo
    }
}

/// The gear cost of a loadout with ammo picked per magazine (the gun range): halo arc tiers + each
/// magazine's ammo `gear_cost`. Ammo the gun cannot load costs nothing here (the host refuses it separately).
pub fn gear_cost(data: &GameData, weapon: &WeaponSpec, halo: &HaloChoice, mags: &[AmmoChoice]) -> GearCost {
    GearCost {
        halo: halo.score(),
        ammo: mags.iter().filter_map(|m| data.ammo_for(weapon, *m)).map(|a| a.gear_cost).sum(),
    }
}

/// The gear cost of a deathmatch loadout: halo arc tiers + the gear cost of its one ammo type, paid once
/// (every magazine carries it).
pub fn kit_cost(data: &GameData, weapon: &WeaponSpec, halo: &HaloChoice, ammo: AmmoChoice) -> GearCost {
    GearCost { halo: halo.score(), ammo: data.ammo_for(weapon, ammo).map_or(0, |a| a.gear_cost) }
}

/// The gear cost of a loadout in `mode`: [`kit_cost`] of the first magazine's ammo where the mode fixes the
/// loadout (one ammo type), [`gear_cost`] otherwise.
pub fn loadout_cost(
    data: &GameData,
    mode: Mode,
    weapon: &WeaponSpec,
    halo: &HaloChoice,
    mags: &[AmmoChoice],
) -> GearCost {
    match data.rules.fixed_loadout(mode) {
        Some(_) => kit_cost(data, weapon, halo, mags.first().copied().unwrap_or(AmmoChoice::STANDARD)),
        None => gear_cost(data, weapon, halo, mags),
    }
}

impl HaloChoice {
    /// This halo as a mode with one halo wears it: that halo's core, the same arc tiers.
    pub fn with_core(self, core: Core) -> Self {
        Self { core, ..self }
    }
}

/// The gear budget of a mode: the deathmatches have one, the gun range has no limit.
pub fn gear_budget(data: &GameData, mode: Mode) -> Option<u32> {
    match mode {
        Mode::Tdm => Some(data.rules.tdm.gear_budget),
        Mode::Ffa => Some(data.rules.ffa.gear_budget),
        Mode::Range => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{AmmoKind, WeaponClass, WeightClass};

    fn halo(core: Core, h: u8, t: u8, a: u8, l: u8) -> HaloChoice {
        HaloChoice { core, tiers: ZoneTable { head: h, torso: t, arms: a, legs: l } }
    }

    #[test]
    fn a_custom_halo_resolves_like_the_preset_with_the_same_arcs() {
        let d = GameData::embedded();
        let scout = d.armor.resolve_id("arm_mender_scout").unwrap();
        let custom = d.armor.resolve_halo(&halo(Core::Mender, 2, 2, 0, 0));
        assert_eq!(custom.capacity, scout.capacity);
        assert_eq!(custom.weight_class, scout.weight_class);
        assert_eq!(custom.gear_cost, 4);
        assert_eq!(custom.id, "custom");
        // Mender T2 on head, torso and arms: 36 + 60 + 36 (the Loadout spec's example).
        let three = d.armor.resolve_halo(&halo(Core::Mender, 2, 2, 2, 0));
        assert!((three.capacity - 132.0).abs() < 1e-3, "{}", three.capacity);
        assert_eq!(three.weight_class, WeightClass::Medium);
    }

    #[test]
    fn no_arcs_is_no_halo_but_keeps_the_core() {
        let d = GameData::embedded();
        let h = halo(Core::Volt, 0, 0, 0, 0);
        assert!(!h.is_lit());
        assert_eq!(h.tier_range(), None);
        let a = d.armor.resolve_halo(&h);
        assert_eq!((a.core, a.weight_class, a.capacity, a.gear_cost), (None, WeightClass::None, 0.0, 0));
        assert_eq!(HaloChoice::from_preset(d.armor.preset("arm_none").unwrap()).tiers, ZoneTable::splat(0));
    }

    #[test]
    fn caps_limit_each_arc() {
        let d = GameData::embedded();
        let caps = d.armor.loadout_tier_caps;
        let jugg = HaloChoice::from_preset(d.armor.preset("arm_bulwark_jugg").unwrap());
        assert!(!jugg.within_caps(caps), "T4 legs and arms are rare loot");
        let capped = jugg.capped(caps);
        assert!(capped.within_caps(caps));
        assert_eq!(capped.tiers, ZoneTable { head: 4, torso: 4, arms: 3, legs: 2 });
        assert_eq!(capped.score(), 13);
        assert_eq!(capped.tier_range(), Some((2, 4)));
    }

    #[test]
    fn gear_cost_is_halo_tiers_plus_every_magazine() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let ap2 = d.ammo.resolve(WeaponClass::AssaultRifle, ap(2)).unwrap().gear_cost;
        let h = halo(Core::Mender, 2, 2, 0, 0);
        let c = gear_cost(&d, mako, &h, &[AmmoChoice::STANDARD, ap(2), ap(2)]);
        assert_eq!(c, GearCost { halo: 4, ammo: 2 * ap2 });
        assert_eq!(c.total(), 4 + 2 * ap2);
        // RIP does not fit a rifle: it is not priced (the host refuses the loadout instead)
        let rip = AmmoChoice { kind: AmmoKind::Rip, tier: 3 };
        assert_eq!(gear_cost(&d, mako, &h, &[rip]).ammo, 0);
        assert_eq!(gear_budget(&d, Mode::Tdm), Some(d.rules.tdm.gear_budget));
        assert_eq!(gear_budget(&d, Mode::Range), None);
        assert_eq!(gear_budget(&d, Mode::Ffa), Some(d.rules.ffa.gear_budget));
    }

    /// The deathmatch modes: one halo and one ammo type, paid once whatever the magazine count.
    #[test]
    fn deathmatch_loadouts_pay_for_their_ammo_once() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let h = halo(Core::Mender, 2, 2, 0, 0);
        for mode in [Mode::Tdm, Mode::Ffa] {
            let fixed = d.rules.fixed_loadout(mode).expect("deathmatch modes fix the loadout");
            let mags = vec![ap(2); fixed.mags as usize];
            let ap2 = d.ammo.resolve(WeaponClass::AssaultRifle, ap(2)).unwrap().gear_cost;
            assert_eq!(loadout_cost(&d, mode, mako, &h, &mags), GearCost { halo: 4, ammo: ap2 }, "{mode:?}");
            assert_eq!(kit_cost(&d, mako, &h, ap(2)), GearCost { halo: 4, ammo: ap2 });
        }
        // the range prices every magazine
        let four = [ap(2); 4];
        assert_eq!(loadout_cost(&d, Mode::Range, mako, &h, &four), gear_cost(&d, mako, &h, &four));
        assert!(d.rules.fixed_loadout(Mode::Range).is_none());
        assert_eq!(h.with_core(Core::Bulwark), HaloChoice { core: Core::Bulwark, tiers: h.tiers });
    }

    /// The deathmatch budget is coherent with the caps and the ammo prices: every arc at its cap with
    /// standard ammo fits exactly; the priciest round still leaves armor to buy; AP III never fits a Heavy
    /// halo; and the one halo has no ability-like status effect (no Volt pulse, Phase immunity or Bulwark
    /// flinch cut).
    #[test]
    fn the_deathmatch_budget_fits_the_caps_and_the_ammo() {
        let d = GameData::embedded();
        let caps = d.armor.loadout_tier_caps;
        let full = HaloChoice { core: Core::Mender, tiers: caps };
        for mode in [Mode::Tdm, Mode::Ffa] {
            let budget = gear_budget(&d, mode).unwrap();
            let fixed = d.rules.fixed_loadout(mode).unwrap();
            assert_eq!(fixed.halo_core, Core::Mender, "{mode:?}: the one halo");
            for w in &d.weapons.weapons {
                assert!(kit_cost(&d, w, &full, AmmoChoice::STANDARD).total() <= budget, "{}: capped arcs", w.id);
                let priciest = d
                    .ammo
                    .types
                    .iter()
                    .flat_map(|(k, t)| (1..=t.tiers.len() as u8).map(|tier| AmmoChoice { kind: *k, tier }))
                    .filter_map(|c| d.ammo_for(w, c).filter(|a| a.player_loadout))
                    .map(|a| a.gear_cost)
                    .max()
                    .unwrap();
                assert!(priciest < budget, "{}: the best round leaves room for a halo", w.id);
            }
            let heavy_lo = d.armor.weight_bands.iter().find(|b| b.0 == WeightClass::Heavy).unwrap().1;
            let ap3 = d.ammo.resolve(WeaponClass::AssaultRifle, AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 });
            assert!(heavy_lo + ap3.unwrap().gear_cost > budget, "AP III and a Heavy halo do not fit together");
        }
    }
}
