//! Per-user files (settings, loadout presets, recent servers, the player name), as RON in the user's config
//! folder:
//! - Linux: `$XDG_CONFIG_HOME/shardline` or `~/.config/shardline`
//! - Windows: `%APPDATA%\shardline`
//! - macOS: `~/Library/Application Support/shardline`
//!
//! `VETF_CONFIG_DIR` overrides the folder (tests, portable installs). Each screen keeps its own file, so
//! screens never fight over one struct: `load_or_default::<T>("x.ron")` / `save("x.ron", &t)`.

// The screen modules fill this in; until then parts of the API are unused.
#![allow(dead_code)]

use bevy::prelude::*;
use serde::Serialize;
use serde::de::DeserializeOwned;
use std::path::PathBuf;

/// The folder the per-user files live in (created on first save).
pub fn config_dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("VETF_CONFIG_DIR") {
        return PathBuf::from(dir);
    }
    let home = || std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("."));
    let base = if cfg!(windows) {
        std::env::var_os("APPDATA").map(PathBuf::from).unwrap_or_else(home)
    } else if cfg!(target_os = "macos") {
        home().join("Library").join("Application Support")
    } else {
        std::env::var_os("XDG_CONFIG_HOME").map(PathBuf::from).unwrap_or_else(|| home().join(".config"))
    };
    base.join("shardline")
}

/// Load `name` from the config folder; a missing or unreadable file gives the default (and a warning if
/// it existed but did not parse).
pub fn load_or_default<T: DeserializeOwned + Default>(name: &str) -> T {
    let path = config_dir().join(name);
    match std::fs::read_to_string(&path) {
        Ok(text) => ron::from_str(&text).unwrap_or_else(|e| {
            warn!("{}: {e}; using defaults", path.display());
            T::default()
        }),
        Err(_) => T::default(),
    }
}

/// Save `value` as `name` in the config folder.
pub fn save<T: Serialize>(name: &str, value: &T) -> Result<(), String> {
    let dir = config_dir();
    std::fs::create_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    let text = ron::ser::to_string_pretty(value, ron::ser::PrettyConfig::default()).map_err(|e| e.to_string())?;
    let path = dir.join(name);
    std::fs::write(&path, text).map_err(|e| format!("{}: {e}", path.display()))
}

/// Who the player is: the name shown to others. `profile.ron`.
#[derive(Resource, Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct PlayerProfile {
    pub name: String,
}

impl Default for PlayerProfile {
    fn default() -> Self {
        Self { name: crate::config::default_name() }
    }
}

impl PlayerProfile {
    pub const FILE: &'static str = "profile.ron";
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug, Default, PartialEq, serde::Serialize, serde::Deserialize)]
    struct Probe {
        a: u32,
        b: Vec<String>,
    }

    #[test]
    fn files_round_trip_and_missing_files_give_defaults() {
        let dir = std::env::temp_dir().join(format!("vetf_cfg_{}", std::process::id()));
        // SAFETY: tests in this crate that touch VETF_CONFIG_DIR run in this one test only.
        unsafe { std::env::set_var("VETF_CONFIG_DIR", &dir) };
        assert_eq!(load_or_default::<Probe>("probe.ron"), Probe::default());
        let p = Probe { a: 7, b: vec!["x".into()] };
        save("probe.ron", &p).unwrap();
        assert_eq!(load_or_default::<Probe>("probe.ron"), p);
        std::fs::write(dir.join("probe.ron"), "not ron").unwrap();
        assert_eq!(load_or_default::<Probe>("probe.ron"), Probe::default(), "a broken file gives defaults");
        let _ = std::fs::remove_dir_all(&dir);
        unsafe { std::env::remove_var("VETF_CONFIG_DIR") };
    }
}
