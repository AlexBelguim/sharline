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
    /// `--name`, else `$USER`. The name saved from the main menu wins unless [`Cli::name_given`].
    pub name: String,
    /// `--name` was given: it overrides the saved profile name for this run.
    pub name_given: bool,
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
    /// Open a menu for screenshots: `reload` (the magazine radial), `heal` / `heal-region` (the heal ring),
    /// `hud` (wounds and a mag check), `board` (the Tab board with the invite's state), `loadout` (the
    /// Loadout screen), `loadout-ammo` (its ammo picker on
    /// MAG 1), `loadout-attach` (its attachment list on the optic slot). The heal and hud ones also hurt
    /// the host's own player. On the main menu: `menu-join` (JOIN GAME, code tab), `menu-join-ip` (direct
    /// IP tab), `menu-host` (HOST GAME).
    pub demo_ui: Option<String>,
    /// `--esc-at 4,5.5`: press Esc at these seconds after start-up (automated tests of the Esc routing).
    pub esc_at: Vec<f32>,
    /// `--allow-input`: a screenshot or demo run still takes the desktop's mouse and keys (for driving it
    /// by hand or with injected input); see [`Cli::ignores_desktop_input`].
    pub allow_input: bool,
    /// Loadout overrides (weapon id, ammo like `rip3`, armor preset id, comma-separated attachment ids).
    /// Without any of them the Loadout screen's active preset is used; with some, anything missing uses
    /// `rules.ron`'s default loadout.
    pub weapon: Option<String>,
    pub ammo: Option<String>,
    /// Magazines in slot order, e.g. `std,std,ap2,ap2`.
    pub mags: Option<String>,
    pub armor: Option<String>,
    pub attach: Option<String>,
    /// `--monitor N`: open the window on monitor N (0-based, left to right). Automated runs (see
    /// [`Cli::automated`]) default to the first monitor that is not the primary one, so tests stay off
    /// the user's main screen.
    pub monitor: Option<usize>,
    /// `--camera x,y,z,tx,ty,tz`: a fixed view camera at (x, y, z) looking at (tx, ty, tz), Bevy world
    /// coordinates, for map screenshots.
    pub camera: Option<(Vec3, Vec3)>,
}

/// No options: what a plain `val_etf` run gets (tests build on it with `Cli { .., ..Cli::default() }`, so a
/// new option never breaks them).
impl Default for Cli {
    fn default() -> Self {
        Cli {
            host: None,
            join: None,
            name: default_name(),
            name_given: false,
            port: None,
            width: 1600,
            height: 900,
            screenshot: None,
            screenshot_after: 3.0,
            exit_after: None,
            bot: false,
            yaw: None,
            demo_ui: None,
            esc_at: Vec::new(),
            allow_input: false,
            weapon: None,
            ammo: None,
            mags: None,
            armor: None,
            attach: None,
            monitor: None,
            camera: None,
        }
    }
}

impl Cli {
    pub fn parse() -> Self {
        let mut cli =
            Cli { monitor: std::env::var("VETF_TEST_MONITOR").ok().and_then(|v| v.parse().ok()), ..Cli::default() };
        let mut args = std::env::args().skip(1);
        while let Some(a) = args.next() {
            let mut val = || args.next().unwrap_or_default();
            match a.as_str() {
                "--host" => cli.host = Some(val()),
                "--join" => cli.join = Some(val()),
                "--name" => {
                    cli.name = val();
                    cli.name_given = true;
                }
                "--port" => cli.port = val().parse().ok(),
                "--width" => cli.width = val().parse().unwrap_or(cli.width),
                "--height" => cli.height = val().parse().unwrap_or(cli.height),
                "--screenshot" => cli.screenshot = Some(PathBuf::from(val())),
                "--screenshot-after" => cli.screenshot_after = val().parse().unwrap_or(3.0),
                "--exit-after" => cli.exit_after = val().parse().ok(),
                "--bot" => cli.bot = true,
                "--yaw" => cli.yaw = val().parse().ok(),
                "--demo-ui" => cli.demo_ui = Some(val()),
                "--esc-at" => cli.esc_at = val().split(',').filter_map(|t| t.trim().parse().ok()).collect(),
                "--allow-input" => cli.allow_input = true,
                "--weapon" => cli.weapon = Some(val()),
                "--ammo" => cli.ammo = Some(val()),
                "--mags" => cli.mags = Some(val()),
                "--armor" => cli.armor = Some(val()),
                "--attach" => cli.attach = Some(val()),
                "--monitor" => cli.monitor = val().parse().ok(),
                "--camera" => {
                    let n: Vec<f32> = val().split(',').filter_map(|x| x.trim().parse().ok()).collect();
                    if n.len() == 6 {
                        cli.camera = Some((Vec3::new(n[0], n[1], n[2]), Vec3::new(n[3], n[4], n[5])));
                    }
                }
                "--help" | "-h" => {
                    println!(
                        "val_etf [--host showhome|range] [--join CODE|IP[:PORT]] [--name NAME] [--port PORT]\n\
                         \x20       [--width W --height H] [--screenshot PATH [--screenshot-after S]] [--exit-after S] [--bot] [--yaw DEG]\n\
                         \x20       [--weapon ID] [--ammo std|ap1..3|rip1..3|slug1..2] [--mags std,ap2,..]\n\
                         \x20       [--armor PRESET] [--attach A,B]\n\
                         \x20       [--demo-ui reload|heal|heal-region|hud|board|menu-join|menu-join-ip|menu-host|\n\
                         \x20                  loadout|loadout-ammo|loadout-attach] [--esc-at S,S,..] [--allow-input]\n\
                         \n\
                         --name overrides the name saved from the main menu (EDIT NAME) for this run.\n\
                         --port sets the HOST GAME port (default: net.ron, 47820).\n\
                         --monitor N opens the window on monitor N (0 = leftmost). Automated runs (--exit-after,\n\
                         \x20 --screenshot, --demo-ui) open on the first non-primary monitor by default\n\
                         \x20 (override with VETF_TEST_MONITOR=N).\n\
                         --screenshot and --demo-ui runs render at scale factor 1 (exactly W x H pixels, also on\n\
                         \x20 a HiDPI screen), never grab the mouse, do not take the keyboard focus and ignore the\n\
                         \x20 desktop's mouse and keys (--allow-input keeps them); --bot runs do not grab the mouse.\n\
                         --esc-at presses Esc at those seconds after start-up (tests of the Esc routing).
                         --camera x,y,z,tx,ty,tz fixes the view camera (world coordinates) for map screenshots."
                    );
                    std::process::exit(0);
                }
                other => eprintln!("ignoring unknown argument {other}"),
            }
        }
        cli
    }

    /// A scripted run (tests, screenshots, demos) rather than someone playing: it opens on a secondary
    /// monitor (see `main::place_window`).
    pub fn automated(&self) -> bool {
        self.exit_after.is_some() || self.screenshot.is_some() || self.demo_ui.is_some()
    }

    /// A screenshot or demo run (`--screenshot`, `--demo-ui`): the window renders at scale factor 1, so
    /// `--width 1920 --height 1080` gives a 1920x1080 image on a HiDPI screen too, and the mouse neither
    /// turns the view nor fires in the match (see also [`Cli::hands_off`]).
    pub fn demo_mode(&self) -> bool {
        self.screenshot.is_some() || self.demo_ui.is_some()
    }

    /// A demo run that ignores the desktop's mouse and keys (unless `--allow-input`): the window opens
    /// without taking the keyboard focus, and a click or key press of the user, or the pointer resting over
    /// the window, changes nothing (no button press, no hover look in the screenshot, no turning or firing).
    pub fn ignores_desktop_input(&self) -> bool {
        self.demo_mode() && !self.allow_input
    }

    /// Automated runs leave the desktop's mouse alone: the cursor is never grabbed or hidden (demo mode and
    /// `--bot`).
    pub fn hands_off(&self) -> bool {
        self.demo_mode() || self.bot
    }

    /// Any loadout option on the command line (they override the Loadout screen's preset).
    pub fn has_loadout_overrides(&self) -> bool {
        self.weapon.is_some()
            || self.ammo.is_some()
            || self.mags.is_some()
            || self.armor.is_some()
            || self.attach.is_some()
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

/// The agent a loadout starts with (agents are cosmetic for now).
pub const DEFAULT_AGENT: &str = "kestrel";

/// The halo of an armor preset id, within the loadout tier caps (unknown ids give the default armor).
pub fn halo_from_armor(id: &str, data: &GameData) -> vetf_sim::gear::HaloChoice {
    let preset = data.armor.preset(id).or_else(|| data.armor.preset(&data.rules.default_loadout.armor));
    preset.map(vetf_sim::gear::HaloChoice::from_preset).unwrap_or_default().capped(data.armor.loadout_tier_caps)
}

/// The loadout this player asks the host for: `rules.ron` defaults with any command-line overrides
/// (`--armor` takes a preset id and becomes a custom halo, capped like the Loadout screen caps it).
pub fn loadout_choice(cli: &Cli, data: &GameData) -> vetf_net::LoadoutChoice {
    let d = &data.rules.default_loadout;
    let weapon = cli.weapon.clone().unwrap_or_else(|| d.primary.clone());
    // Another gun's default attachments would not fit: only keep the rules.ron ones for the default gun.
    let attachments = match &cli.attach {
        Some(list) => list.split(',').map(|a| a.trim().to_string()).filter(|a| !a.is_empty()).collect(),
        None if weapon == d.primary => d.attachments.clone(),
        None => Vec::new(),
    };
    // `--mags` lists the slots in order; `--ammo` loads every default magazine with one ammo.
    let mags = match (&cli.mags, cli.ammo.as_deref().and_then(parse_ammo)) {
        (Some(list), _) => parse_mags(list),
        (None, Some(ammo)) => vec![ammo; d.mags.len()],
        (None, None) => d.mags.clone(),
    };
    vetf_net::LoadoutChoice {
        weapon,
        mags,
        attachments,
        halo: halo_from_armor(cli.armor.as_deref().unwrap_or(&d.armor), data),
        agent: DEFAULT_AGENT.into(),
    }
}

/// Parse a magazine list in slot order (`std,ap2,ap2`); unknown entries are skipped, past six dropped.
pub fn parse_mags(s: &str) -> Vec<vetf_sim::data::AmmoChoice> {
    s.split(',').filter_map(parse_ammo).take(vetf_sim::weapon::MAX_MAGS).collect()
}

pub fn default_name() -> String {
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
        let ap2 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 };
        assert_eq!(parse_mags("std, ap2,laser,ap2"), vec![AmmoChoice::STANDARD, ap2, ap2]);
        assert_eq!(parse_mags("std,std,std,std,std,std,std").len(), 6);
    }

    fn cli() -> Cli {
        Cli { name: "T".into(), ..Cli::default() }
    }

    #[test]
    fn demo_runs_leave_the_desktop_alone() {
        let c = cli();
        assert!(!c.demo_mode() && !c.hands_off() && !c.ignores_desktop_input(), "a normal run plays");
        let shot = Cli { screenshot: Some("x.png".into()), ..cli() };
        assert!(shot.demo_mode() && shot.hands_off() && shot.ignores_desktop_input());
        let demo = Cli { demo_ui: Some("menu-host".into()), ..cli() };
        assert!(demo.ignores_desktop_input());
        let driven = Cli { allow_input: true, ..demo };
        assert!(driven.demo_mode() && driven.hands_off(), "1:1 and never grabbed");
        assert!(!driven.ignores_desktop_input(), "--allow-input keeps the mouse and keys");
        let bot = Cli { bot: true, ..cli() };
        assert!(bot.hands_off() && !bot.demo_mode());
    }

    #[test]
    fn the_armor_option_becomes_a_capped_custom_halo() {
        use vetf_sim::data::Core;
        let d = GameData::embedded();
        let plain = loadout_choice(&cli(), &d);
        assert!(!cli().has_loadout_overrides());
        assert_eq!(plain.halo.core, Core::Mender, "rules.ron default armor");
        assert_eq!((plain.halo.tiers.head, plain.halo.tiers.torso), (2, 2));
        assert_eq!(plain.agent, DEFAULT_AGENT);
        let jugg = loadout_choice(&Cli { armor: Some("arm_bulwark_jugg".into()), ..cli() }, &d);
        assert!(jugg.halo.within_caps(d.armor.loadout_tier_caps));
        assert_eq!(jugg.halo.tiers.legs, d.armor.loadout_tier_caps.legs);
        assert_eq!(halo_from_armor("arm_none", &d).score(), 0);
        assert_eq!(halo_from_armor("nope", &d), plain.halo, "unknown ids fall back to the default armor");
        let c = Cli { mags: Some("ap2,std".into()), ..cli() };
        assert!(c.has_loadout_overrides());
        assert_eq!(loadout_choice(&c, &d).mags.len(), 2);
    }
}
