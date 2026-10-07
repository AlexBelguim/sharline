//! Display data of the Loadout screen: `game/assets/data/loadout_ui.ron` (labels, stat-bar ranges, the
//! placeholder preview with its hotspots) and `agents.ron`. Loaded from disk so copy can be edited without a
//! rebuild, with the copy compiled into the binary as the fallback.

use bevy::prelude::*;
use serde::Deserialize;
use std::collections::{BTreeMap, HashMap};
use std::path::PathBuf;
use vetf_sim::data::{AttachmentCategory, FireMode, WeaponClass};

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct LoadoutUiFile {
    pub class_labels: BTreeMap<WeaponClass, String>,
    pub fire_mode_labels: HashMap<FireMode, String>,
    pub stat_bars: StatBars,
    pub tier_colour_names: Vec<String>,
    pub none_blurbs: HashMap<AttachmentCategory, String>,
    pub no_mag_blurb: String,
    pub previews: BTreeMap<String, PreviewSpec>,
}

/// (value at an empty bar, value at a full bar) per stat.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct StatBars {
    pub ads_s: (f32, f32),
    pub rpm: (f32, f32),
    pub recoil: (f32, f32),
    pub mobility: (f32, f32),
    pub reload_s: (f32, f32),
    pub range_m: (f32, f32),
    pub mag: (f32, f32),
}

/// Bar fill for `v` on a (worst, best) range, 0..=1.
pub fn bar_frac(v: f32, (worst, best): (f32, f32)) -> f32 {
    if (best - worst).abs() < 1e-6 {
        return 1.0;
    }
    ((v - worst) / (best - worst)).clamp(0.0, 1.0)
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct PreviewSpec {
    /// A render in `game/assets/ui/img` (empty = none).
    pub image: String,
    /// A silhouette icon stem in `game/assets/ui/icons` (empty = none).
    pub icon: String,
    pub alpha: f32,
    /// (left, top, width, height) in the preview's inner box.
    pub rect: (f32, f32, f32, f32),
    pub hotspots: Vec<HotspotSpec>,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct HotspotSpec {
    pub slot: AttachmentCategory,
    pub x: f32,
    pub y: f32,
    pub side: TagSide,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TagSide {
    Right,
    Left,
    Above,
    Below,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct AgentsFile {
    pub agents: Vec<AgentSpec>,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct AgentSpec {
    pub id: String,
    pub name: String,
    pub role: String,
    pub accent: Accent,
    pub portrait: String,
    pub abilities: Vec<AbilitySpec>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Accent {
    Teal,
    Coral,
}

#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct AbilitySpec {
    pub key: String,
    pub name: String,
    pub meta: String,
    pub icon: String,
    pub text: String,
}

/// Both files, as one resource.
#[derive(Resource, Debug, Clone, PartialEq)]
pub struct LoadoutUiData {
    pub ui: LoadoutUiFile,
    pub agents: Vec<AgentSpec>,
}

const UI_RON: &str = include_str!("../../../../assets/data/loadout_ui.ron");
const AGENTS_RON: &str = include_str!("../../../../assets/data/agents.ron");

impl LoadoutUiData {
    /// The copy compiled into the binary.
    pub fn embedded() -> Self {
        Self::parse(UI_RON, AGENTS_RON).expect("embedded loadout UI data is valid")
    }

    fn parse(ui: &str, agents: &str) -> Result<Self, String> {
        let ui: LoadoutUiFile = ron::from_str(ui).map_err(|e| format!("loadout_ui.ron: {e}"))?;
        let agents: AgentsFile = ron::from_str(agents).map_err(|e| format!("agents.ron: {e}"))?;
        if agents.agents.is_empty() {
            return Err("agents.ron: no agents".into());
        }
        Ok(Self { ui, agents: agents.agents })
    }

    /// From `game/assets/data` when it is there and valid, else the built-in copy.
    pub fn load() -> Self {
        let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets/data");
        let read = |name: &str| std::fs::read_to_string(dir.join(name)).ok();
        match (read("loadout_ui.ron"), read("agents.ron")) {
            (Some(ui), Some(agents)) => Self::parse(&ui, &agents).unwrap_or_else(|e| {
                error!("{e}; using the built-in Loadout copy");
                Self::embedded()
            }),
            _ => Self::embedded(),
        }
    }

    pub fn agent(&self, id: &str) -> Option<(usize, &AgentSpec)> {
        self.agents.iter().enumerate().find(|(_, a)| a.id == id)
    }

    pub fn tier_colour_name(&self, tier: u8) -> &str {
        self.ui.tier_colour_names.get((tier.max(1) - 1) as usize).map_or("", |s| s.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::GameData;

    #[test]
    fn loadout_ui_data_parses_and_covers_every_weapon() {
        let u = LoadoutUiData::embedded();
        assert_eq!(LoadoutUiData::load(), u, "disk copy matches the built-in one");
        let d = GameData::embedded();
        for w in &d.weapons.weapons {
            assert!(u.ui.class_labels.contains_key(&w.cls), "{}", w.id);
            assert!(u.ui.previews.contains_key(&w.id), "{}", w.id);
            for m in &w.fire_modes {
                assert!(u.ui.fire_mode_labels.contains_key(m), "{m:?}");
            }
        }
        for cat in &d.attachments.optional {
            assert!(u.ui.none_blurbs.contains_key(cat), "{cat:?}");
        }
        assert_eq!(u.agents.len(), 2);
        assert_eq!(u.agent("solace").map(|(i, _)| i), Some(1));
        assert_eq!(u.tier_colour_name(2), "blue");
        assert!(u.agents.iter().all(|a| a.abilities.len() == 3));
    }

    #[test]
    fn bar_fill_runs_from_worst_to_best() {
        assert_eq!(bar_frac(0.10, (0.60, 0.10)), 1.0);
        assert_eq!(bar_frac(0.70, (0.60, 0.10)), 0.0);
        assert!((bar_frac(0.35, (0.60, 0.10)) - 0.5).abs() < 1e-5);
        assert!((bar_frac(720.0, (0.0, 1000.0)) - 0.72).abs() < 1e-5);
    }
}
