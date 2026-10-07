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
    /// The host keeps at most 16 characters of a name.
    pub const MAX_NAME: usize = 16;

    /// Characters a player name may use: letters, digits, space, `-`, `_` and `.` (the rules live in
    /// [`crate::first_run`]).
    pub fn name_char_ok(c: char) -> bool {
        crate::first_run::name_char_ok(c)
    }

    /// A typed name as the game keeps it (trimmed, upper case, 3-16 characters), or None if it breaks the
    /// rules ([`crate::first_run::validate_name`] says why).
    pub fn clean_name(s: &str) -> Option<String> {
        crate::first_run::validate_name(s).ok()
    }

    /// A profile has been saved on this machine (the first-launch name prompt has been answered).
    pub fn saved() -> bool {
        config_dir().join(Self::FILE).is_file()
    }

    /// The saved profile, with its name sanitised (a broken or empty name falls back to the default).
    pub fn load() -> Self {
        let mut p: Self = load_or_default(Self::FILE);
        p.name = crate::first_run::sanitize_name(&p.name).unwrap_or_else(|| Self::default().name);
        p
    }
}

/// Games this player joined, newest first (`recent.ron`). The main menu's JOIN GAME panel lists them.
#[derive(Resource, Debug, Clone, Default, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct RecentServers {
    pub servers: Vec<RecentServer>,
}

#[derive(Debug, Clone, Default, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct RecentServer {
    /// The lobby name, or "<HOST>'S GAME" until lobby names replicate.
    pub name: String,
    /// Map id: "showhome", "range".
    pub map: String,
    /// What to dial again: a canonical join code ("6000-105E-PC") or "ip:port".
    pub address: String,
    /// Joined by address (DIRECT IP) rather than by code.
    pub by_ip: bool,
    /// Unix time in seconds.
    pub last_joined: u64,
}

impl RecentServers {
    pub const FILE: &'static str = "recent.ron";
    /// Entries kept in the file (the menu shows the first three).
    pub const KEEP: usize = 10;

    /// Put `entry` first, replacing an older entry for the same address.
    pub fn record(&mut self, entry: RecentServer) {
        self.servers.retain(|s| !s.address.eq_ignore_ascii_case(&entry.address));
        self.servers.insert(0, entry);
        self.servers.truncate(Self::KEEP);
    }
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

        // The player profile: absent on a fresh machine (the first-launch prompt shows), then saved and loaded.
        assert!(!PlayerProfile::saved(), "no profile yet");
        let os = PlayerProfile::default().name;
        let fallback = crate::first_run::sanitize_name(&os).unwrap_or(os);
        assert_eq!(PlayerProfile::load().name, fallback, "the OS user name until one is saved");
        let p = PlayerProfile { name: PlayerProfile::clean_name(" kestrel  7 ").unwrap() };
        save(PlayerProfile::FILE, &p).unwrap();
        assert!(PlayerProfile::saved());
        assert_eq!(PlayerProfile::load(), p);
        assert_eq!(PlayerProfile::load().name, "KESTREL 7");
        // Hand-edited or older files are sanitised, not thrown away.
        std::fs::write(dir.join(PlayerProfile::FILE), "(name: \"  odd  name!! \")").unwrap();
        assert_eq!(PlayerProfile::load().name, "ODD NAME");
        std::fs::write(dir.join(PlayerProfile::FILE), "(name: \"ab\")").unwrap();
        assert_eq!(PlayerProfile::load().name, "AB", "a short name saved under the old rules survives");
        std::fs::write(dir.join(PlayerProfile::FILE), "(name: \"!!\")").unwrap();
        assert_eq!(PlayerProfile::load().name, fallback, "nothing usable: the default name");
        assert!(PlayerProfile::saved(), "but it was saved: no prompt");
        let _ = std::fs::remove_dir_all(&dir);
        unsafe { std::env::remove_var("VETF_CONFIG_DIR") };
    }

    #[test]
    fn player_names_are_cleaned_like_the_host_keeps_them() {
        assert_eq!(PlayerProfile::clean_name("kestrel_you"), Some("KESTREL_YOU".into()));
        assert_eq!(PlayerProfile::clean_name(" a.b  c-d "), Some("A.B C-D".into()));
        assert_eq!(PlayerProfile::clean_name("ABCDEFGHIJKLMNOPQRST"), None, "over 16");
        assert_eq!(PlayerProfile::clean_name(" .. "), None, "under 3");
        assert_eq!(PlayerProfile::clean_name("ash!"), None, "not allowed");
    }

    #[test]
    fn recent_servers_keep_one_entry_per_address_newest_first() {
        let mut r = RecentServers::default();
        let e = |name: &str, address: &str| RecentServer {
            name: name.into(),
            map: "showhome".into(),
            address: address.into(),
            ..Default::default()
        };
        r.record(e("A", "6000-105E-PC"));
        r.record(e("B", "192.168.1.40:47820"));
        r.record(e("A2", "6000-105e-pc"));
        assert_eq!(r.servers.iter().map(|s| s.name.as_str()).collect::<Vec<_>>(), ["A2", "B"]);
        for i in 0..20 {
            r.record(e("X", &format!("10.0.0.{i}:47820")));
        }
        assert_eq!(r.servers.len(), RecentServers::KEEP);
        let text = ron::ser::to_string(&r).unwrap();
        assert_eq!(ron::from_str::<RecentServers>(&text).unwrap(), r, "recent.ron round-trips");
    }
}
