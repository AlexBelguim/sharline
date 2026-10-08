//! Loadout gear: the custom halo a player builds (one core, a tier per arc) and the points a whole loadout
//! costs. The host (validation) and the Loadout screen (RESULT panel, cost chips) use the same functions, so
//! they always agree. Team deathmatch and free-for-all price their picks ([`kit_cost`], `rules.ron`
//! `deathmatch_loadout`: the armor tier, the one ammo type once, the magazine type) against a budget; the gun
//! range shows the arc tiers and every magazine's ammo ([`gear_cost`]) with no limit.

use crate::data::{
    AmmoChoice, ArmorFile, ArmorPreset, ArmorStats, AttachmentCategory, Core, DeathmatchLoadout, GameData, Mode,
    WeaponSpec,
};
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

    /// The halo of a deathmatch armor tier (1-based; 0 is NO HALO): the mode's one core with that tier's arcs. Out of range:
    /// no halo.
    pub fn of_tier(kit: &DeathmatchLoadout, tier: u8) -> Self {
        Self { core: kit.halo_core, tiers: kit.armor_tier(tier).map_or(ZoneTable::splat(0), |a| a.tiers) }
    }
}

impl ArmorFile {
    /// Resolve a custom halo (no caps applied: check [`HaloChoice::within_caps`] first).
    pub fn resolve_halo(&self, halo: &HaloChoice) -> ArmorStats {
        self.resolve(&halo.preset())
    }
}

/// The points of a loadout, split as the RESULT panel shows them.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct GearCost {
    /// The halo: the armor tier's points (team deathmatch, free-for-all), or the sum of the arc tiers (the gun
    /// range).
    pub halo: u32,
    /// The ammo: the one type's points, paid once (team deathmatch, free-for-all), or every magazine's (the
    /// gun range).
    pub ammo: u32,
    /// The magazine type (team deathmatch, free-for-all; nothing in the gun range).
    pub mags: u32,
}

impl GearCost {
    pub fn total(&self) -> u32 {
        self.halo + self.ammo + self.mags
    }
}

/// The gear cost of a loadout with ammo picked per magazine (the gun range): halo arc tiers + each
/// magazine's ammo `gear_cost`. Ammo the gun cannot load costs nothing here (the host refuses it separately).
pub fn gear_cost(data: &GameData, weapon: &WeaponSpec, halo: &HaloChoice, mags: &[AmmoChoice]) -> GearCost {
    GearCost {
        halo: halo.score(),
        ammo: mags.iter().filter_map(|m| data.ammo_for(weapon, *m)).map(|a| a.gear_cost).sum(),
        mags: 0,
    }
}

/// The magazine type of a gun with these attachments: the first magazine part that fits it, else its
/// default magazine.
pub fn mag_type<'a>(data: &GameData, weapon: &'a WeaponSpec, attachments: &'a [String]) -> &'a str {
    attachments
        .iter()
        .find(|id| data.attachment(id).is_some_and(|a| a.cat == AttachmentCategory::Mag && a.fits.contains(&weapon.id)))
        .map_or(weapon.mag_default.as_str(), |id| id.as_str())
}

/// The points of a deathmatch loadout's picks: armor tier `armor` (1-based, 0 NO HALO; out of range: none), the one
/// ammo type (paid once: every magazine carries it; ammo the gun cannot load costs nothing here, the host
/// refuses it separately) and the magazine type.
pub fn kit_cost(
    data: &GameData,
    kit: &DeathmatchLoadout,
    weapon: &WeaponSpec,
    armor: u8,
    ammo: AmmoChoice,
    mag: &str,
) -> GearCost {
    GearCost {
        halo: kit.armor_tier(armor).map_or(0, |a| a.points),
        ammo: data.ammo_for(weapon, ammo).map_or(0, |a| a.gear_cost),
        mags: kit.mag_points(mag),
    }
}

/// The points of a loadout in `mode`. Team deathmatch and free-for-all: [`kit_cost`] of the armor tier the
/// halo makes ([`DeathmatchLoadout::tier_for`]), slot 1's ammo and the magazine type. The gun range:
/// [`gear_cost`].
pub fn loadout_cost(
    data: &GameData,
    mode: Mode,
    weapon: &WeaponSpec,
    halo: &HaloChoice,
    mags: &[AmmoChoice],
    attachments: &[String],
) -> GearCost {
    match data.rules.fixed_loadout(mode) {
        Some(kit) => {
            let ammo = mags.first().copied().unwrap_or(AmmoChoice::STANDARD);
            kit_cost(data, kit, weapon, kit.tier_for(halo.tiers), ammo, mag_type(data, weapon, attachments))
        }
        None => gear_cost(data, weapon, halo, mags),
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
    fn the_range_prices_halo_tiers_plus_every_magazine() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let ap2 = d.ammo.resolve(WeaponClass::AssaultRifle, ap(2)).unwrap().gear_cost;
        let h = halo(Core::Mender, 2, 2, 0, 0);
        let c = gear_cost(&d, mako, &h, &[AmmoChoice::STANDARD, ap(2), ap(2)]);
        assert_eq!(c, GearCost { halo: 4, ammo: 2 * ap2, mags: 0 });
        assert_eq!(c.total(), 4 + 2 * ap2);
        // RIP does not fit a rifle: it is not priced (the host refuses the loadout instead)
        let rip = AmmoChoice { kind: AmmoKind::Rip, tier: 3 };
        assert_eq!(gear_cost(&d, mako, &h, &[rip]).ammo, 0);
        let drum = ["mag_drum60".to_string()];
        assert_eq!(loadout_cost(&d, Mode::Range, mako, &h, &[ap(2); 4], &drum), gear_cost(&d, mako, &h, &[ap(2); 4]));
        assert_eq!(gear_budget(&d, Mode::Tdm), Some(d.rules.tdm.gear_budget));
        assert_eq!(gear_budget(&d, Mode::Range), None);
        assert_eq!(gear_budget(&d, Mode::Ffa), Some(d.rules.ffa.gear_budget));
    }

    #[test]
    fn the_magazine_type_is_the_fitting_mag_part_or_the_default() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let ids = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        assert_eq!(mag_type(&d, mako, &ids(&["optic_holo", "mag_45"])), "mag_45");
        assert_eq!(mag_type(&d, mako, &ids(&["optic_holo"])), "mag_30", "the default");
        assert_eq!(mag_type(&d, mako, &ids(&["skink_mag_60"])), "mag_30", "another gun's magazine");
    }

    /// Team deathmatch and free-for-all: the armor tier's points, the one ammo type once (whatever the
    /// magazine count) and the magazine type.
    #[test]
    fn a_deathmatch_loadout_pays_for_its_picks() {
        let d = GameData::embedded();
        let kit = &d.rules.deathmatch_loadout;
        let mako = d.weapon("ar7_mako").unwrap();
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let drum = ["optic_holo".to_string(), "mag_drum60".to_string()];
        for mode in [Mode::Tdm, Mode::Ffa] {
            assert_eq!(d.rules.fixed_loadout(mode), Some(kit), "{mode:?}: one loadout for both");
            let t3 = HaloChoice::of_tier(kit, 3);
            let six = vec![ap(2); kit.mags as usize];
            assert_eq!(loadout_cost(&d, mode, mako, &t3, &six, &drum), GearCost { halo: 3, ammo: 2, mags: 2 });
            assert_eq!(loadout_cost(&d, mode, mako, &t3, &[ap(2)], &[]), GearCost { halo: 3, ammo: 2, mags: 0 });
        }
        assert_eq!(kit_cost(&d, kit, mako, 4, AmmoChoice::STANDARD, "mag_30").total(), 5);
        assert_eq!(kit_cost(&d, kit, mako, 9, AmmoChoice::STANDARD, "mag_30").halo, 0, "no such tier");
        assert_eq!(HaloChoice::of_tier(kit, 4), HaloChoice { core: Core::Mender, tiers: d.armor.loadout_tier_caps });
        assert!(!HaloChoice::of_tier(kit, 0).is_lit());
    }

    /// The deathmatch point table makes a trade-off (DIRECTION_LOG 17): T4 armor and the best ammo never fit
    /// together, with any gun and magazine; the sensible middles do.
    #[test]
    fn the_deathmatch_points_make_a_trade_off() {
        let d = GameData::embedded();
        let kit = &d.rules.deathmatch_loadout;
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let rip = |tier| AmmoChoice { kind: AmmoKind::Rip, tier };
        for mode in [Mode::Tdm, Mode::Ffa] {
            let budget = gear_budget(&d, mode).unwrap();
            assert_eq!(budget, 8, "{mode:?}");
            for w in &d.weapons.weapons {
                let mags: Vec<&str> = d
                    .attachments
                    .attachments
                    .iter()
                    .filter(|a| a.cat == AttachmentCategory::Mag && a.fits.contains(&w.id))
                    .map(|a| a.id.as_str())
                    .collect();
                let rounds: Vec<AmmoChoice> = d
                    .ammo
                    .types
                    .iter()
                    .flat_map(|(k, t)| (1..=t.tiers.len() as u8).map(|tier| AmmoChoice { kind: *k, tier }))
                    .filter(|c| d.ammo_for(w, *c).is_some_and(|a| a.player_loadout))
                    .collect();
                let cost = |armor, ammo, mag| kit_cost(&d, kit, w, armor, ammo, mag).total();
                let best = rounds.iter().map(|c| d.ammo_for(w, *c).unwrap().gear_cost).max().unwrap();
                assert_eq!(best, 4, "{}: tier III is the best round", w.id);
                for mag in &mags {
                    for round in &rounds {
                        let pts = d.ammo_for(w, *round).unwrap().gear_cost;
                        if pts == best {
                            assert!(cost(4, *round, mag) > budget, "{}: T4 + {round:?} + {mag}", w.id);
                        }
                    }
                    // T4 with standard ammo fits any magazine
                    assert!(cost(4, AmmoChoice::STANDARD, mag) <= budget, "{}: T4 + STD + {mag}", w.id);
                }
                // every tier with standard ammo and the standard magazine
                for armor in 1..=kit.armor.len() as u8 {
                    assert!(cost(armor, AmmoChoice::STANDARD, &w.mag_default) <= budget, "{} T{armor}", w.id);
                }
            }
            let mako = d.weapon("ar7_mako").unwrap();
            let skink = d.weapon("sk9_skink").unwrap();
            let warden = d.weapon("vk50_warden").unwrap();
            let fits = |w, armor, ammo, mag| kit_cost(&d, kit, w, armor, ammo, mag).total() <= budget;
            // the middles
            assert!(fits(mako, 3, ap(3), "mag_45"), "T3 + AP III + extended");
            assert!(fits(warden, 3, ap(3), "mag_8"));
            assert!(fits(skink, 3, rip(3), "skink_mag_60"));
            assert!(fits(mako, 2, ap(3), "mag_drum60"), "T2 + the best ammo + the drum");
            assert!(fits(mako, 4, ap(2), "mag_45"), "T4 + AP II + extended");
            assert!(fits(mako, 1, ap(3), "mag_drum60"));
            // the trade-offs
            assert!(!fits(mako, 3, ap(3), "mag_drum60"), "T3 + AP III + the drum");
            assert!(!fits(mako, 4, ap(2), "mag_drum60"), "T4 + AP II + the drum");
            assert!(!fits(skink, 4, rip(3), "skink_mag_40"), "T4 + RIP III");
        }
    }
}
