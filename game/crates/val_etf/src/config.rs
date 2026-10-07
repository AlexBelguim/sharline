//! Command line, gameplay data and the current level as resources.

use bevy::prelude::*;
use std::path::PathBuf;
use std::sync::Arc;
use vetf_sim::GameData;
use vetf_sim::level::Level;

/// All gameplay numbers (shared, read-only).
#[derive(Resource, Clone, Deref)]
pub struct Data(pub Arc<GameData>);

/// The level being played (host picks it; clients load it by name from the match state).
#[derive(Resource, Clone, Deref)]
pub struct CurrentLevel(pub Arc<Level>);

/// Load `game/assets/data/*.ron` so numbers can be tuned without rebuilding; fall back to the copy compiled
/// into the binary.
pub fn load_game_data() -> GameData {
    let mut candidates = vec![PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets/data")];
    if let Ok(exe) = std::env::current_exe()
        && let Some(dir) = exe.parent()
    {
        candidates.push(dir.join("assets/data"));
        candidates.push(dir.join("../../assets/data"));
    }
    for dir in candidates.into_iter().filter(|d| d.is_dir()) {
        match GameData::load_dir(&dir) {
            Ok(d) => {
                info!("game data loaded from {}", dir.display());
                return d;
            }
            Err(e) => error!("game data in {} is invalid ({e}); using the built-in copy", dir.display()),
        }
    }
    GameData::embedded()
}

pub fn level_by_name(name: &str) -> Level {
    vetf_sim::maps::by_name(name).unwrap_or_else(|| {
        warn!("unknown map {name}; using Showhome");
        vetf_sim::maps::showhome()
    })
}

/// Command-line options (all optional; the menu covers the same ground).
#[derive(Resource, Debug, Clone)]
pub struct Cli {
    /// Host straight away on this map.
    pub host: Option<String>,
    /// Join straight away (join code, ip:port or ip).
    pub join: Option<String>,
    pub name: String,
    pub port: Option<u16>,
    pub width: u32,
    pub height: u32,
    /// Save a screenshot after `screenshot_after` seconds (counted from entering the match when
    /// `--host` / `--join` is given, from start-up otherwise).
    pub screenshot: Option<PathBuf>,
    pub screenshot_after: f32,
    /// Quit after this many seconds (for automated runs).
    pub exit_after: Option<f32>,
    /// Drive the local player with a simple bot (smoke tests).
    pub bot: bool,
    /// Start looking this way (degrees, 0 = north / -Z, 90 = west); the bot then holds this heading.
    pub yaw: Option<f32>,
    /// Loadout overrides until there is a loadout screen (weapon id, ammo like `rip3`, armor preset id,
    /// comma-separated attachment ids). Anything missing uses `rules.ron`'s default loadout.
    pub weapon: Option<String>,
    pub ammo: Option<String>,
    pub armor: Option<String>,
    pub attach: Option<String>,
}

impl Cli {
    pub fn parse() -> Self {
        let mut cli = Cli {
            host: None,
            join: None,
            name: default_name(),
            port: None,
            width: 1600,
            height: 900,
            screenshot: None,
            screenshot_after: 3.0,
            exit_after: None,
            bot: false,
            yaw: None,
            weapon: None,
            ammo: None,
            armor: None,
            attach: None,
        };
        let mut args = std::env::args().skip(1);
        while let Some(a) = args.next() {
            let mut val = || args.next().unwrap_or_default();
            match a.as_str() {
                "--host" => cli.host = Some(val()),
                "--join" => cli.join = Some(val()),
                "--name" => cli.name = val(),
                "--port" => cli.port = val().parse().ok(),
                "--width" => cli.width = val().parse().unwrap_or(cli.width),
                "--height" => cli.height = val().parse().unwrap_or(cli.height),
                "--screenshot" => cli.screenshot = Some(PathBuf::from(val())),
                "--screenshot-after" => cli.screenshot_after = val().parse().unwrap_or(3.0),
                "--exit-after" => cli.exit_after = val().parse().ok(),
                "--bot" => cli.bot = true,
                "--yaw" => cli.yaw = val().parse().ok(),
                "--weapon" => cli.weapon = Some(val()),
                "--ammo" => cli.ammo = Some(val()),
                "--armor" => cli.armor = Some(val()),
                "--attach" => cli.attach = Some(val()),
                "--help" | "-h" => {
                    println!(
                        "val_etf [--host showhome|range] [--join CODE|IP[:PORT]] [--name NAME] [--port PORT]\n\
                         \x20       [--width W --height H] [--screenshot PATH [--screenshot-after S]] [--exit-after S] [--bot] [--yaw DEG]\n\
                         \x20       [--weapon ID] [--ammo std|ap1..3|shr1..3|rip1..3|slug1..2] [--armor PRESET] [--attach A,B]"
                    );
                    std::process::exit(0);
                }
                other => eprintln!("ignoring unknown argument {other}"),
            }
        }
        cli
    }
}

/// Parse an ammo shorthand: `std`, `ap2`, `shr3` / `shrapnel3`, `rip1`, `slug2` (tier defaults to 1).
pub fn parse_ammo(s: &str) -> Option<vetf_sim::data::AmmoChoice> {
    use vetf_sim::data::{AmmoChoice, AmmoKind};
    let s = s.trim().to_ascii_lowercase();
    let split = s.find(|c: char| c.is_ascii_digit()).unwrap_or(s.len());
    let (name, tier) = s.split_at(split);
    let tier = if tier.is_empty() { 1 } else { tier.parse().ok()? };
    let kind = match name.trim_end_matches(['-', '_', ' ']) {
        "std" | "standard" => AmmoKind::Standard,
        "ap" | "armorpiercing" | "armor_piercing" => AmmoKind::ArmorPiercing,
        "shr" | "shrapnel" => AmmoKind::Shrapnel,
        "rip" => AmmoKind::Rip,
        "slug" => AmmoKind::Slug,
        _ => return None,
    };
    Some(AmmoChoice { kind, tier })
}

/// The loadout this player asks the host for: `rules.ron` defaults with any command-line overrides.
pub fn loadout_choice(cli: &Cli, data: &GameData) -> vetf_net::LoadoutChoice {
    let d = &data.rules.default_loadout;
    let weapon = cli.weapon.clone().unwrap_or_else(|| d.primary.clone());
    // Another gun's default attachments would not fit: only keep the rules.ron ones for the default gun.
    let attachments = match &cli.attach {
        Some(list) => list.split(',').map(|a| a.trim().to_string()).filter(|a| !a.is_empty()).collect(),
        None if weapon == d.primary => d.attachments.clone(),
        None => Vec::new(),
    };
    let ammo = cli.ammo.as_deref().and_then(parse_ammo).unwrap_or(d.ammo);
    vetf_net::LoadoutChoice { weapon, ammo, attachments, armor: cli.armor.clone().unwrap_or_else(|| d.armor.clone()) }
}

fn default_name() -> String {
    std::env::var("USER").or_else(|_| std::env::var("USERNAME")).map(|u| u.to_uppercase()).unwrap_or("AGENT".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::data::{AmmoChoice, AmmoKind};

    #[test]
    fn ammo_shorthand() {
        assert_eq!(parse_ammo("std"), Some(AmmoChoice::STANDARD));
        assert_eq!(parse_ammo("RIP3"), Some(AmmoChoice { kind: AmmoKind::Rip, tier: 3 }));
        assert_eq!(parse_ammo("ap-2"), Some(AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 }));
        assert_eq!(parse_ammo("shrapnel"), Some(AmmoChoice { kind: AmmoKind::Shrapnel, tier: 1 }));
        assert_eq!(parse_ammo("laser"), None);
    }
}
