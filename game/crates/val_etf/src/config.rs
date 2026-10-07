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
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("assets/data"));
            candidates.push(dir.join("../../assets/data"));
        }
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
    /// Save a screenshot of the window after `screenshot_after` seconds.
    pub screenshot: Option<PathBuf>,
    pub screenshot_after: f32,
    /// Quit after this many seconds (for automated runs).
    pub exit_after: Option<f32>,
    /// Drive the local player with a simple bot (smoke tests).
    pub bot: bool,
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
                "--help" | "-h" => {
                    println!(
                        "val_etf [--host showhome|range] [--join CODE|IP[:PORT]] [--name NAME] [--port PORT]\n\
                         \x20       [--width W --height H] [--screenshot PATH [--screenshot-after S]] [--exit-after S] [--bot]"
                    );
                    std::process::exit(0);
                }
                other => eprintln!("ignoring unknown argument {other}"),
            }
        }
        cli
    }
}

fn default_name() -> String {
    std::env::var("USER").or_else(|_| std::env::var("USERNAME")).map(|u| u.to_uppercase()).unwrap_or("AGENT".into())
}
