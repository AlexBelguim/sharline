//! Loadout presets A, B and C, plus each gun's last attachments, saved as `loadouts.ron` in the user's
//! config folder. Client-side only: the host only ever sees the loadout a player confirms.
//!
//! A preset is saved as the player built it. Team deathmatch and free-for-all shape it into their picks when
//! they use it (an armor tier on the one halo, six magazines of one ammo type: `LoadoutChoice::shaped`), so
//! presets from older builds (a Volt core, a halo per arc, mixed magazines) still load, and open in those
//! modes as their nearest picks.

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

impl Preset {
    /// A preset that did not read: no gun, no magazines, so [`LoadoutsFile::repair`] replaces it.
    fn unreadable() -> Self {
        Preset {
            name: String::new(),
            loadout: LoadoutChoice {
                weapon: String::new(),
                mags: Vec::new(),
                attachments: Vec::new(),
                halo: HaloChoice::default(),
                agent: String::new(),
            },
        }
    }
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
        let path = user_config::config_dir().join(Self::FILE);
        let mut f = std::fs::read_to_string(&path).map(|text| Self::parse(&text)).unwrap_or_default();
        f.repair(data, agent);
        f
    }

    /// Read the file's text; never fails. A file this build cannot read whole (another build's format, a hand
    /// edit) keeps every preset that still reads, in its letter; [`LoadoutsFile::repair`] then puts the
    /// built-in preset in the others.
    pub fn parse(text: &str) -> Self {
        let err = match ron::from_str::<Self>(text) {
            Ok(f) => return f,
            Err(e) => e,
        };
        bevy::log::warn!("{}: {err}; keeping the presets that still read", Self::FILE);
        #[derive(Deserialize, Default)]
        #[serde(default)]
        struct Loose {
            active: usize,
            presets: Vec<Box<ron::value::RawValue>>,
            attachments: BTreeMap<String, Vec<String>>,
        }
        let loose: Loose = ron::from_str(text).unwrap_or_default();
        let presets =
            loose.presets.iter().map(|raw| raw.into_rust::<Preset>().unwrap_or_else(|_| Preset::unreadable()));
        Self { active: loose.active, presets: presets.collect(), attachments: loose.attachments }
    }

    pub fn save(&self) -> Result<(), String> {
        user_config::save(Self::FILE, self)
    }

    /// Exactly three presets, each naming a gun players may pick; `active` in range.
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
                    // A hidden gun (the SK-9 Skink, out for now) becomes the default gun with its default parts;
                    // the halo and magazines stay (ammo the gun cannot load opens as STANDARD).
                    if data.offered_weapon(&p.loadout.weapon).is_none() {
                        p.loadout.weapon = data.rules.default_loadout.primary.clone();
                        p.loadout.attachments = data.rules.default_loadout.attachments.clone();
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
            assert!(c.halo.within_caps(d.armor.loadout_tier_caps));
            // each is a valid pick in team deathmatch and free-for-all: RIFLE and LONG T2, MEDIC T3
            for mode in [vetf_net::MatchMode::Tdm, vetf_net::MatchMode::Ffa] {
                let s = crate::loadout::summary(c, &d, mode);
                assert!(s.gear_cost <= s.gear_budget.unwrap(), "{} {mode:?}", preset.name);
            }
        }
        let tier = |c: &LoadoutChoice| crate::loadout::summary(c, &d, vetf_net::MatchMode::Tdm).armor_tier;
        assert_eq!(p.iter().map(|p| tier(&p.loadout)).collect::<Vec<_>>(), [Some(2), Some(2), Some(3)]);
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

    /// `loadouts.ron` as builds before the deathmatch picks wrote it (DIRECTION_LOG 17): per-magazine
    /// ammo, a Volt core, halos that are no armor tier, an agent. It still loads as saved; team deathmatch and
    /// free-for-all open it as their picks (an armor tier, six magazines of one ammo type), the range as it is.
    const OLD_FILE: &str = r#"(
    active: 1,
    presets: [
        (name: "RIFLE", loadout: (weapon: "ar7_mako", mags: [(kind: Standard, tier: 1), (kind: Standard, tier: 1)],
            attachments: ["optic_holo", "mako_stock_standard", "mag_30"],
            halo: (core: Mender, tiers: (head: 2, torso: 2, arms: 0, legs: 0)), agent: "kestrel")),
        (name: "VOLT AP", loadout: (weapon: "sk9_skink",
            mags: [(kind: ArmorPiercing, tier: 2), (kind: Rip, tier: 3), (kind: Standard, tier: 1),
                (kind: ArmorPiercing, tier: 1), (kind: Rip, tier: 1), (kind: Standard, tier: 1)],
            attachments: ["optic_reddot"],
            halo: (core: Volt, tiers: (head: 1, torso: 3, arms: 1, legs: 1)), agent: "solace")),
        (name: "MEDIC", loadout: (weapon: "ar7_mako", mags: [(kind: Standard, tier: 1)], attachments: [],
            halo: (core: Mender, tiers: (head: 1, torso: 3, arms: 1, legs: 1)), agent: "kestrel")),
    ],
    attachments: {"ar7_mako": ["optic_3x", "grip_vertical"]},
)"#;

    #[test]
    fn an_older_file_still_loads_and_opens_as_the_new_picks() {
        use crate::loadout::model::Draft;
        use vetf_sim::data::{AmmoChoice, AmmoKind, Core};
        let d = GameData::embedded();
        let mut f = LoadoutsFile::parse(OLD_FILE);
        f.repair(&d, "kestrel");
        assert_eq!(f.presets.iter().map(|p| p.name.as_str()).collect::<Vec<_>>(), ["RIFLE", "VOLT AP", "MEDIC"]);
        assert_eq!(f.active, 1);
        let volt = &f.presets[1].loadout;
        assert_eq!((volt.mags.len(), volt.halo.core), (6, Core::Volt), "saved as built");
        // ...but on the Mako with its default parts: the SK-9 Skink is out for now.
        assert_eq!(volt.weapon, "ar7_mako");
        assert_eq!(volt.attachments, d.rules.default_loadout.attachments);
        assert_eq!(f.attachments["ar7_mako"], ["optic_3x", "grip_vertical"]);
        let ap2 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 };
        for mode in [vetf_net::MatchMode::Tdm, vetf_net::MatchMode::Ffa] {
            let kit = d.rules.fixed_loadout(mode).cloned();
            let budget = Some(d.rules.deathmatch(mode).gear_budget);
            let dr = Draft::from_choice(volt, &f.attachments, &d, kit.clone());
            assert_eq!(dr.mags, vec![ap2; 6], "{mode:?}: slot 1's AP II in all six");
            assert_eq!(dr.halo.core, kit.unwrap().halo_core, "{mode:?}: the one halo");
            assert_eq!(dr.armor_tier(), Some(3), "{mode:?}: H1 T3 A1 L1 is T3");
            assert_eq!(dr.mag_type(&d).map(|m| m.id.as_str()), Some("mag_30"), "the Mako's standard magazine");
            assert_eq!(dr.weapon, "ar7_mako");
            // every old preset opens as picks within the points
            let tiers: Vec<Option<u8>> = f
                .presets
                .iter()
                .map(|p| Draft::from_choice(&p.loadout, &f.attachments, &d, d.rules.fixed_loadout(mode).cloned()))
                .inspect(|dr| assert!(dr.problems(&d, budget).is_empty(), "{mode:?}: {dr:?}"))
                .map(|dr| dr.armor_tier())
                .collect();
            assert_eq!(tiers, [Some(2), Some(3), Some(3)], "RIFLE H2 T2, VOLT AP and MEDIC H1 T3");
        }
        let range = Draft::from_choice(volt, &f.attachments, &d, None);
        let rifle_mags: Vec<AmmoChoice> =
            volt.mags.iter().map(|m| if m.kind == AmmoKind::Rip { AmmoChoice::STANDARD } else { *m }).collect();
        assert_eq!(
            range.mags, rifle_mags,
            "the range keeps its magazines (RIP, which a rifle cannot load, as STANDARD)"
        );
        assert_eq!(range.halo, volt.halo, "and its halo");
    }

    /// A preset saved with NO HALO (DIRECTION_LOG 18) reads back, and opens, as NO HALO in team deathmatch and
    /// free-for-all, and its loadout line says so.
    #[test]
    fn a_no_halo_preset_round_trips() {
        use crate::loadout::model::Draft;
        let d = GameData::embedded();
        let mut f = LoadoutsFile { presets: default_presets(&d, "kestrel"), ..Default::default() };
        for mode in [vetf_net::MatchMode::Tdm, vetf_net::MatchMode::Ffa] {
            let kit = d.rules.fixed_loadout(mode).cloned();
            let mut dr = Draft::from_choice(&f.presets[0].loadout, &f.attachments, &d, kit.clone());
            assert!(dr.set_armor_tier(0));
            f.presets[0].loadout = dr.choice();
            let text = ron::to_string(&f).unwrap();
            let back = LoadoutsFile::parse(&text);
            assert_eq!(back, f, "{mode:?}: the file reads back as saved");
            let again = Draft::from_choice(&back.presets[0].loadout, &back.attachments, &d, kit);
            assert_eq!(again.armor_tier(), Some(0), "{mode:?}");
            let s = crate::loadout::summary(&back.presets[0].loadout, &d, mode);
            assert_eq!((s.armor_tier, s.armor_name.as_str()), (Some(0), "NO HALO"), "{mode:?}");
            assert_eq!(s.weight, vetf_sim::data::WeightClass::None);
        }
    }

    /// A file this build cannot read whole never crashes the game: what still reads stays, in its letter.
    #[test]
    fn an_unreadable_preset_falls_back_in_its_own_letter() {
        let d = GameData::embedded();
        // B's ammo type does not exist (a newer build's), C's gun is no gun id at all.
        let text = OLD_FILE
            .replace("(kind: Rip, tier: 3)", "(kind: Plasma, tier: 3)")
            .replace(r#"(name: "MEDIC", loadout: (weapon: "ar7_mako","#, r#"(name: "MEDIC", loadout: (weapon: 7,"#);
        assert!(ron::from_str::<LoadoutsFile>(&text).is_err(), "the strict read fails");
        let mut f = LoadoutsFile::parse(&text);
        f.repair(&d, "kestrel");
        let defaults = default_presets(&d, "kestrel");
        assert_eq!(f.presets[0].name, "RIFLE", "A still reads");
        assert_eq!(f.presets[1], defaults[1], "B: the built-in preset");
        assert_eq!(f.presets[2], defaults[2], "C: the built-in preset");
        assert_eq!((f.active, f.attachments.len()), (1, 1));
        // nothing readable at all: the built-in presets
        let mut junk = LoadoutsFile::parse("not a loadouts file {");
        junk.repair(&d, "kestrel");
        assert_eq!(junk.presets, defaults);
    }
}
