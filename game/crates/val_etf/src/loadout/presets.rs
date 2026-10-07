//! Loadout presets A, B and C, plus each gun's last attachments, saved as `loadouts.ron` in the user's
//! config folder. Client-side only: the host only ever sees the loadout a player confirms.

use crate::user_config;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use vetf_net::LoadoutChoice;
use vetf_sim::GameData;
use vetf_sim::gear::HaloChoice;

/// Presets on the top bar (A, B, C).
pub const PRESET_COUNT: usize = 3;
pub const PRESET_LETTERS: [char; PRESET_COUNT] = ['A', 'B', 'C'];
/// Longest preset name.
pub const NAME_MAX: usize = 8;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Preset {
    /// Upper case, at most [`NAME_MAX`] characters.
    pub name: String,
    pub loadout: LoadoutChoice,
}

/// `loadouts.ron`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct LoadoutsFile {
    /// The preset the current loadout was loaded from (0 = A).
    pub active: usize,
    pub presets: Vec<Preset>,
    /// The attachments each gun had last (weapon id -> attachment ids), so a weapon tab brings them back.
    pub attachments: BTreeMap<String, Vec<String>>,
}

impl LoadoutsFile {
    pub const FILE: &'static str = "loadouts.ron";

    /// Load the file, filling in missing or broken presets with the built-in ones.
    pub fn load(data: &GameData, agent: &str) -> Self {
        let mut f: Self = user_config::load_or_default(Self::FILE);
        f.repair(data, agent);
        f
    }

    pub fn save(&self) -> Result<(), String> {
        user_config::save(Self::FILE, self)
    }

    /// Exactly three presets, each naming a gun that exists; `active` in range.
    pub fn repair(&mut self, data: &GameData, agent: &str) {
        let defaults = default_presets(data, agent);
        self.presets.truncate(PRESET_COUNT);
        for (i, def) in defaults.into_iter().enumerate() {
            match self.presets.get_mut(i) {
                Some(p) if data.weapon(&p.loadout.weapon).is_some() && !p.loadout.mags.is_empty() => {
                    p.name = clean_name(&p.name);
                    if p.name.is_empty() {
                        p.name = def.name;
                    }
                }
                Some(p) => *p = def,
                None => self.presets.push(def),
            }
        }
        self.active = self.active.min(PRESET_COUNT - 1);
    }

    /// Chip label: `A · RIFLE`.
    pub fn label(&self, i: usize) -> String {
        format!("{} · {}", PRESET_LETTERS[i], self.presets.get(i).map_or("", |p| p.name.as_str()))
    }
}

/// Preset names: upper case letters, digits, space and `-`, at most [`NAME_MAX`].
pub fn clean_name(s: &str) -> String {
    s.trim_start()
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == ' ' || *c == '-')
        .map(|c| c.to_ascii_uppercase())
        .take(NAME_MAX)
        .collect::<String>()
        .trim_end()
        .to_string()
}

/// The presets a new player starts with: A · RIFLE (rules.ron's default loadout), B · LONG (the Warden with
/// its default parts) and C · MEDIC (the Mako with the Mender Medic halo).
pub fn default_presets(data: &GameData, agent: &str) -> Vec<Preset> {
    let d = &data.rules.default_loadout;
    let caps = data.armor.loadout_tier_caps;
    let halo_of = |id: &str| data.armor.preset(id).map(HaloChoice::from_preset).unwrap_or_default().capped(caps);
    let rifle = LoadoutChoice {
        weapon: d.primary.clone(),
        mags: d.mags.clone(),
        attachments: d.attachments.clone(),
        halo: halo_of(&d.armor),
        agent: agent.into(),
    };
    let long_gun = data
        .weapons
        .weapons
        .iter()
        .find(|w| w.cls == vetf_sim::data::WeaponClass::BoltSniper)
        .map_or(d.primary.clone(), |w| w.id.clone());
    let long = LoadoutChoice {
        weapon: long_gun.clone(),
        attachments: super::model::normalize_parts(data, &long_gun, None),
        ..rifle.clone()
    };
    let medic = LoadoutChoice { halo: halo_of("arm_mender_medic"), ..rifle.clone() };
    vec![
        Preset { name: "RIFLE".into(), loadout: rifle },
        Preset { name: "LONG".into(), loadout: long },
        Preset { name: "MEDIC".into(), loadout: medic },
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_three_valid_presets() {
        let d = GameData::embedded();
        let p = default_presets(&d, "kestrel");
        assert_eq!(p.iter().map(|p| p.name.as_str()).collect::<Vec<_>>(), ["RIFLE", "LONG", "MEDIC"]);
        assert_eq!(p[1].loadout.weapon, "vk50_warden");
        assert!(p[1].loadout.attachments.contains(&"optic_sniper".to_string()));
        assert_eq!(p[2].loadout.halo.score(), 6, "Mender Medic: H1 T3 A1 L1");
        for preset in &p {
            let c = &preset.loadout;
            let cost = vetf_sim::gear::gear_cost(&d, d.weapon(&c.weapon).unwrap(), &c.halo, &c.mags);
            assert!(cost.total() <= d.rules.tdm.gear_budget, "{}", preset.name);
            assert!(c.halo.within_caps(d.armor.loadout_tier_caps));
        }
        let f = LoadoutsFile { presets: p, ..Default::default() };
        assert_eq!(f.label(0), "A · RIFLE");
        assert_eq!(f.label(2), "C · MEDIC");
    }

    #[test]
    fn broken_files_are_repaired() {
        let d = GameData::embedded();
        let mut f = LoadoutsFile { active: 9, ..Default::default() };
        f.repair(&d, "kestrel");
        assert_eq!(f.presets.len(), 3);
        assert_eq!(f.active, 2);
        f.presets[0].loadout.weapon = "gone".into();
        f.presets[1].name = "long range!!".into();
        f.presets.push(f.presets[2].clone());
        f.repair(&d, "kestrel");
        assert_eq!(f.presets.len(), 3);
        assert_eq!(f.presets[0].loadout.weapon, d.rules.default_loadout.primary);
        assert_eq!(f.presets[1].name, "LONG RAN");
        assert_eq!(clean_name("  sn1per-x  "), "SN1PER-X");
        assert_eq!(clean_name("é#"), "");
    }

    #[test]
    fn the_file_round_trips_through_ron() {
        let d = GameData::embedded();
        let mut f = LoadoutsFile::default();
        f.repair(&d, "solace");
        f.active = 1;
        f.attachments.insert("ar7_mako".into(), vec!["optic_3x".into(), "grip_vertical".into()]);
        f.presets[0]
            .loadout
            .mags
            .push(vetf_sim::data::AmmoChoice { kind: vetf_sim::data::AmmoKind::ArmorPiercing, tier: 2 });
        let text = ron::ser::to_string_pretty(&f, ron::ser::PrettyConfig::default()).unwrap();
        let back: LoadoutsFile = ron::from_str(&text).unwrap();
        assert_eq!(back, f);
        // and through the config folder
        let dir = std::env::temp_dir().join(format!("vetf_loadouts_{}", std::process::id()));
        let path = dir.join(LoadoutsFile::FILE);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(&path, &text).unwrap();
        let read: LoadoutsFile = ron::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
        assert_eq!(read.presets[0].loadout.mags.len(), 5);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
