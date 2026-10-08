//! Command line, gameplay data and the current level as resources.

use bevy::prelude::*;
use std::path::{Path, PathBuf};
use std::sync::{Arc, OnceLock};
use vetf_sim::GameData;
use vetf_sim::level::Level;

/// All gameplay numbers (shared, read-only).
#[derive(Resource, Clone, Deref)]
pub struct Data(pub Arc<GameData>);

/// The level being played (host picks it; clients load it by name from the match state).
#[derive(Resource, Clone, Deref)]
pub struct CurrentLevel(pub Arc<Level>);

/// The game's asset folder (`game/assets`), found once at start-up; every file the game reads at run time
/// (textures, images, data) comes from here. See [`pick_assets_root`] for the search order.
pub fn assets_root() -> &'static Path {
    static ROOT: OnceLock<PathBuf> = OnceLock::new();
    ROOT.get_or_init(|| {
        let exe_dir = std::env::current_exe().ok().and_then(|e| e.parent().map(Path::to_path_buf));
        let source = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../assets");
        let env = std::env::var_os("VETF_ASSETS").filter(|v| !v.is_empty()).map(PathBuf::from);
        let root = pick_assets_root(env.clone(), exe_dir.as_deref(), &source);
        // Before logging starts (the asset plugin needs the folder first), so on stderr.
        if let Some(env) = env.filter(|e| std::path::absolute(e).ok().as_deref() != Some(root.as_path())) {
            eprintln!("VETF_ASSETS={} has no data/rules.ron; using {}", env.display(), root.display());
        }
        root
    })
}

/// Where the asset folder is, in this order: `VETF_ASSETS` if set; an `assets` folder next to the exe (a
/// copied build) or in the nearest folder above it (`target/debug`, `target/release` and
/// `target/<triple>/release` all sit under `game/`); else the source tree the binary was built from. Only a
/// folder with `data/rules.ron` counts, so the repository's art `assets/` folder never matches.
///
/// The result is absolute: Bevy joins a relative asset path to the exe's folder (or `CARGO_MANIFEST_DIR`),
/// not to the current directory the data files were checked against (a relative `VETF_ASSETS`).
pub fn pick_assets_root(env: Option<PathBuf>, exe_dir: Option<&Path>, source: &Path) -> PathBuf {
    let is_root = |d: &Path| d.join("data").join("rules.ron").is_file();
    let mut candidates: Vec<PathBuf> = env.into_iter().collect();
    if let Some(dir) = exe_dir {
        candidates.extend(dir.ancestors().map(|a| a.join("assets")));
    }
    candidates.push(source.to_path_buf());
    let root = candidates.into_iter().find(|d| is_root(d)).unwrap_or_else(|| source.to_path_buf());
    // `absolute` (not `canonicalize`): no verbatim prefix on Windows, which would break `ui/icons/x.png`.
    std::path::absolute(&root).unwrap_or(root)
}

/// Load `game/assets/data/*.ron` so numbers can be tuned without rebuilding; fall back to the copy compiled
/// into the binary.
pub fn load_game_data() -> GameData {
    for dir in [assets_root().join("data")].into_iter().filter(|d| d.is_dir()) {
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
    /// `--live`: `--host showhome` skips the lobby and starts the match at once (tests, screenshots).
    pub live: bool,
    /// `--mode tdm|ffa`: the mode HOST GAME (and `--host showhome`) starts: team deathmatch or free-for-all.
    pub mode: Option<vetf_net::MatchMode>,
    /// Join straight away (join code, ip:port or ip).
    pub join: Option<String>,
    /// `--name`, else [`UNNAMED`]. The name saved from the main menu wins unless [`Cli::name_given`].
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
    /// IP tab), `menu-host` (HOST GAME). `first-run`, `first-run-invalid`, `first-run-valid`: the
    /// first-launch callsign prompt (`first_run.rs`). In a match: `ads` (held aim down sights), `inspect` /
    /// `inspect-left` (the gun across the view, a side to the camera).
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
            live: false,
            mode: None,
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
                "--live" => cli.live = true,
                "--mode" => {
                    let v = val();
                    cli.mode = parse_mode(&v);
                    if cli.mode.is_none() {
                        eprintln!("unknown --mode {v} (tdm or ffa); using team deathmatch");
                    }
                }
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
                        "val_etf [--host showhome|range [--live] [--mode tdm|ffa]] [--join CODE|IP[:PORT]] [--name NAME]\n\
                         \x20       [--port PORT]\n\
                         \x20       [--width W --height H] [--screenshot PATH [--screenshot-after S]] [--exit-after S] [--bot] [--yaw DEG]\n\
                         \x20       [--weapon ID] [--ammo std|ap1..3|rip1..3|slug1..2] [--mags std,ap2,..]\n\
                         \x20       [--armor PRESET] [--attach A,B]\n\
                         \x20       [--demo-ui reload|heal|heal-region|hud|board|menu-join|menu-join-ip|menu-host|\n\
                         \x20                  loadout|loadout-ammo|loadout-attach|ads|inspect|inspect-left]\n\
                         \x20       [--esc-at S,S,..] [--allow-input]\n\
                         \n\
                         --name overrides the name saved from the main menu (EDIT NAME) for this run.\n\
                         --port sets the HOST GAME port (default: net.ron, 47820).\n\
                         --monitor N opens the window on monitor N (0 = leftmost). Automated runs (--exit-after,\n\
                         \x20 --screenshot, --demo-ui) open on the first non-primary monitor by default\n\
                         \x20 (override with VETF_TEST_MONITOR=N).\n\
                         --screenshot and --demo-ui runs render at scale factor 1 (exactly W x H pixels, also on\n\
                         \x20 a HiDPI screen), never grab the mouse, do not take the keyboard focus and ignore the\n\
                         \x20 desktop's mouse and keys (--allow-input keeps them); --bot runs do not grab the mouse.\n\
                         --esc-at presses Esc at those seconds after start-up (tests of the Esc routing).\n\
                         --host showhome opens the lobby; --live starts the match at once. --mode ffa hosts a\n\
                         \x20 free-for-all deathmatch instead of team deathmatch (also preselects HOST GAME's MODE).\n\
                         --demo-ui settings-gameplay|-mouse|-keybinds|-video|-audio|-hud opens that Settings tab from the\n\
                         \x20 main menu; esc | esc-stop | esc-restart opens the ESC menu (or its confirm) over a hosted\n\
                         \x20 match; ads holds aim down sights; hud-fx shows the damage flash; overlay keeps the\n\
                         \x20 performance overlay in a scripted run.\n\
                         --demo-ui lobby-ready | lobby-switch | lobby-start presses READY, SWITCH TEAM then READY, or\n\
                         \x20 READY then START MATCH in the lobby (tests of the lobby over the network); lobby-ffa (host)\n\
                         \x20 switches the lobby to free-for-all, then READY and START MATCH.\n\
                         --demo-ui first-run | first-run-invalid | first-run-valid opens the first-launch callsign\n\
                         \x20 prompt (empty, too short, valid); without a saved profile it opens on its own.\n\
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

/// Parse `--mode`: `tdm` (team deathmatch) or `ffa` (free-for-all).
pub fn parse_mode(s: &str) -> Option<vetf_net::MatchMode> {
    match s.trim().to_ascii_lowercase().replace(['-', '_', ' '], "").as_str() {
        "tdm" | "team" | "teamdeathmatch" => Some(vetf_net::MatchMode::Tdm),
        "ffa" | "freeforall" | "dm" | "deathmatch" => Some(vetf_net::MatchMode::Ffa),
        _ => None,
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

/// The name shown until the player picks one (the first-launch prompt, EDIT NAME, `--name`). Never the OS
/// user name: friends would see it in lobbies and the kill feed.
pub const UNNAMED: &str = "UNKNOWN";

pub fn default_name() -> String {
    UNNAMED.into()
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

    #[test]
    fn mode_option() {
        use vetf_net::MatchMode;
        assert_eq!(parse_mode("ffa"), Some(MatchMode::Ffa));
        assert_eq!(parse_mode("Free-for-all"), Some(MatchMode::Ffa));
        assert_eq!(parse_mode("TDM"), Some(MatchMode::Tdm));
        assert_eq!(parse_mode("range"), None, "the range is a map (--host range), not a mode");
        assert_eq!(parse_mode("ctf"), None);
        assert_eq!(Cli::default().mode, None);
    }

    fn cli() -> Cli {
        Cli { name: "T".into(), ..Cli::default() }
    }

    /// The asset folder is found from wherever the exe sits: `--target <triple>` builds sit one folder
    /// deeper than `target/release`, which broke the old fixed `../../assets` (the walls did not draw).
    #[test]
    fn the_asset_folder_is_found_from_any_build_folder() {
        let tmp = std::env::temp_dir().join(format!("vetf_assets_root_{}", std::process::id()));
        let mk = |d: &Path, marker: bool| {
            std::fs::create_dir_all(d.join("data")).unwrap();
            if marker {
                std::fs::write(d.join("data").join("rules.ron"), "()").unwrap();
            }
        };
        let game = tmp.join("repo").join("game");
        let release = game.join("target").join("x86_64-pc-windows-msvc").join("release");
        std::fs::create_dir_all(&release).unwrap();
        mk(&game.join("assets"), true);
        // The repository's art folder (no data/rules.ron) is never taken.
        mk(&tmp.join("repo").join("assets"), false);
        let source = tmp.join("nowhere");
        assert_eq!(pick_assets_root(None, Some(&release), &source), game.join("assets"));
        assert_eq!(pick_assets_root(None, Some(&game.join("target").join("debug")), &source), game.join("assets"));
        // A copied build with its own assets folder uses that one.
        let shipped = tmp.join("shipped");
        mk(&shipped.join("assets"), true);
        assert_eq!(pick_assets_root(None, Some(&shipped), &source), shipped.join("assets"));
        // VETF_ASSETS wins; nothing found falls back to the source tree.
        assert_eq!(pick_assets_root(Some(shipped.join("assets")), Some(&release), &source), shipped.join("assets"));
        assert_eq!(pick_assets_root(None, Some(&tmp.join("empty")), &source), source);
        // A relative VETF_ASSETS is made absolute against the current directory (Bevy would otherwise join it
        // to the exe's folder, while the data files were read from here).
        let rel = PathBuf::from(format!("vetf_rel_assets_{}", std::process::id()));
        mk(&rel, true);
        let got = pick_assets_root(Some(rel.clone()), Some(&release), &source);
        std::fs::remove_dir_all(&rel).ok();
        assert!(got.is_absolute() && got.ends_with(&rel), "{}", got.display());
        assert_eq!(got, std::env::current_dir().unwrap().join(&rel));
        std::fs::remove_dir_all(&tmp).ok();
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
