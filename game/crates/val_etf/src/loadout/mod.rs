//! The Loadout hub screen (mockups 05 / 05b): agent, weapon, attachments, the six ordered magazines with
//! their ammo, halo armor per arc, and the gear-budget result. Opens over the main menu or the match
//! (`Screen::Loadout`); changes apply at the next spawn.
//!
//! Contract with the other screens:
//! - [`ActiveLoadout`] is what this player asks the host for (sent in `Hello`, applied at each spawn).
//! - [`summary`] formats it for the main menu's player card and the ESC menu.

// The main menu and ESC menu use `summary` once they are built.
#![allow(dead_code)]

use crate::config::{Cli, Data};
use bevy::prelude::*;
use vetf_net::LoadoutChoice;
use vetf_sim::GameData;
use vetf_sim::ZoneTable;
use vetf_sim::data::{AmmoKind, Core, WeightClass};

pub struct LoadoutScreenPlugin;

impl Plugin for LoadoutScreenPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, init_active_loadout);
    }
}

/// The loadout this player asks for (the active preset, or the command line's overrides).
#[derive(Resource, Debug, Clone, PartialEq)]
pub struct ActiveLoadout(pub LoadoutChoice);

fn init_active_loadout(mut commands: Commands, cli: Res<Cli>, data: Res<Data>) {
    commands.insert_resource(ActiveLoadout(crate::config::loadout_choice(&cli, &data)));
}

/// A loadout as the hub screens show it.
#[derive(Debug, Clone, PartialEq)]
pub struct LoadoutSummary {
    pub weapon_name: String,
    pub attachments: Vec<String>,
    /// (slot 1-based, short ammo label, ammo type) in slot order. Never round counts.
    pub mags: Vec<(usize, String, AmmoKind)>,
    pub armor_name: String,
    pub core: Option<Core>,
    /// Tier per halo arc (loadout caps applied).
    pub tiers: ZoneTable<u8>,
    pub weight: WeightClass,
    /// Team-deathmatch gear cost (halo + every magazine) against the budget.
    pub gear_cost: u32,
    pub gear_budget: u32,
}

/// Summarise a loadout choice (unknown ids fall back to what the host would use).
pub fn summary(choice: &LoadoutChoice, data: &GameData) -> LoadoutSummary {
    let weapon = data.weapon(&choice.weapon).or_else(|| data.weapon(&data.rules.default_loadout.primary));
    let mags: Vec<(usize, String, AmmoKind)> = choice
        .mags
        .iter()
        .enumerate()
        .filter_map(|(i, m)| {
            let a = data.ammo_for(weapon?, *m)?;
            Some((i + 1, a.label, m.kind))
        })
        .collect();
    let ammo_cost: u32 = choice.mags.iter().filter_map(|m| data.ammo_for(weapon?, *m)).map(|a| a.gear_cost).sum();
    let preset = data.armor.preset(&choice.armor).or_else(|| data.armor.preset(&data.rules.default_loadout.armor));
    let (armor_name, core, tiers, weight, armor_cost) = match preset {
        Some(p) => {
            let mut p = p.clone();
            let caps = data.armor.loadout_tier_caps;
            p.tiers = p.tiers.map(|z, t| (*t).min(caps[z]));
            let a = data.armor.resolve(&p);
            (p.name.clone(), a.core, a.tiers, a.weight_class, a.gear_cost)
        }
        None => ("NONE".into(), None, ZoneTable::splat(0), WeightClass::None, 0),
    };
    LoadoutSummary {
        weapon_name: weapon.map_or("?".into(), |w| w.name.clone()),
        attachments: choice
            .attachments
            .iter()
            .map(|a| data.attachment(a).map_or(a.clone(), |s| s.id.replace('_', " ")))
            .collect(),
        mags,
        armor_name,
        core,
        tiers,
        weight,
        gear_cost: armor_cost + ammo_cost,
        gear_budget: data.rules.tdm.gear_budget,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::data::AmmoChoice;

    #[test]
    fn the_default_loadout_summarises_within_budget() {
        let d = GameData::embedded();
        let l = &d.rules.default_loadout;
        let c = LoadoutChoice {
            weapon: l.primary.clone(),
            mags: l.mags.clone(),
            attachments: l.attachments.clone(),
            armor: l.armor.clone(),
        };
        let s = summary(&c, &d);
        assert_eq!(s.weapon_name, "AR-7 Mako");
        assert_eq!(s.mags.len(), l.mags.len());
        assert_eq!(s.mags[0], (1, "STD".into(), AmmoKind::Standard));
        assert!(s.gear_cost <= s.gear_budget);
        let ap = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 };
        let c = LoadoutChoice { mags: vec![ap; 6], ..c };
        assert!(summary(&c, &d).gear_cost > s.gear_budget, "six AP III magazines are over budget");
    }
}
