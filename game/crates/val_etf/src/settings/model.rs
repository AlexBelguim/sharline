//! The [`Settings`] resource (what the player chose, saved as `settings.ron` in the user's config folder),
//! [`SettingsData`] (defaults and ranges from `game/assets/data/settings.ron`), and the maths the screen
//! shows: cm/360, other games' sensitivities, field of view, the crosshair code.

use super::bindings::{Action, Binding, Keybinds};
use bevy::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::sync::OnceLock;

/// The user file in the config folder (see `user_config`).
pub const FILE: &str = "settings.ron";

/// The settings file format this build writes (`version` in the file). A file from before versions reads as 0.
/// Each version that moves a default has a step in [`Settings::migrate`].
pub const SETTINGS_VERSION: u32 = 1;

macro_rules! choice {
    ($(#[$m:meta])* $name:ident { $($var:ident = $label:literal),+ $(,)? }) => {
        $(#[$m])*
        #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
        pub enum $name {
            $($var),+
        }
        impl $name {
            pub const ALL: &'static [$name] = &[$($name::$var),+];
            /// Segment copy, exactly as the mockup writes it.
            pub const LABELS: &'static [&'static str] = &[$($label),+];
            pub fn index(self) -> usize {
                Self::ALL.iter().position(|v| *v == self).unwrap_or(0)
            }
            pub fn from_index(i: usize) -> Self {
                Self::ALL[i.min(Self::ALL.len() - 1)]
            }
            pub fn label(self) -> &'static str {
                Self::LABELS[self.index()]
            }
        }
        impl Default for $name {
            fn default() -> Self {
                Self::ALL[0]
            }
        }
    };
}

choice!(Jetpack { HoldJumpInAir = "HOLD JUMP IN AIR", SeparateKey = "SEPARATE KEY" });
// A slide starts from a forward run as well as a sprint (the variant keeps its saved name).
choice!(Slide { CrouchWhileSprinting = "CROUCH WHILE RUNNING", Off = "OFF" });
choice!(MagCard { ThreeSeconds = "3 S", WhileHeld = "WHILE HELD" });
choice!(RadialPick { Release = "RELEASE", Click = "CLICK" });
choice!(ImportGame { Valorant = "VALORANT", Cs2 = "CS2", Apex = "APEX", Overwatch2 = "OVERWATCH 2" });
choice!(AdsScaling { MatchFocal = "MATCH FOCAL LENGTH", SameCm = "SAME CM/360", Custom = "CUSTOM" });
choice!(HoldToggle { Hold = "HOLD", Toggle = "TOGGLE" });
choice!(HitMarkers { ShieldFlesh = "SHIELD + FLESH", FleshOnly = "FLESH ONLY", Off = "OFF" });
choice!(
    /// Crosshair preview background (preview only, never saved).
    PreviewBg { Street = "STREET", WhiteWall = "WHITE WALL", Sky = "SKY" }
);
choice!(WindowModeChoice { Fullscreen = "FULLSCREEN", Borderless = "BORDERLESS", Windowed = "WINDOWED" });
choice!(Overlay { Off = "OFF", Fps = "FPS + FRAME TIME", Network = "+ NETWORK" });
choice!(Preset { Low = "LOW", Medium = "MEDIUM", High = "HIGH", Ultra = "ULTRA" });
choice!(Aa { Off = "OFF", Fxaa = "FXAA", Smaa = "SMAA", Taa = "TAA", Msaa4 = "MSAA 4×" });
choice!(Shadows { Low = "LOW", Medium = "MEDIUM", High = "HIGH" });
choice!(Bloom { Off = "OFF", Low = "LOW", High = "HIGH" });
choice!(Particles { Low = "LOW", High = "HIGH" });
choice!(Mix { Headphones = "HEADPHONES", Speakers = "SPEAKERS", Night = "NIGHT (compressed)" });
choice!(Ultrawide { Centre = "16:9 CENTRE", Full = "FULL WIDTH" });
choice!(HealthNumbers { Show = "SHOW", BarsOnly = "BARS ONLY" });
choice!(Minimap { Rotate = "ROTATE", NorthUp = "NORTH UP" });
choice!(KillFeed { Three = "3", Five = "5", Seven = "7" });
choice!(EnemyNames { OnScanAim = "ON SCAN / AIM", Never = "NEVER" });
choice!(TeamColours { Default = "DEFAULT", Deutan = "DEUTAN", Protan = "PROTAN", Tritan = "TRITAN" });
choice!(
    /// 'OFF' is left out on purpose: settings may never hide enemy outlines (Video tab rule).
    EnemyOutline { On = "ON", Thick = "THICK" }
);
choice!(DamageFlash { Off = "OFF", Soft = "SOFT", Full = "FULL" });
choice!(TextSize { S = "S", M = "M", L = "L" });

impl KillFeed {
    pub fn lines(self) -> usize {
        match self {
            KillFeed::Three => 3,
            KillFeed::Five => 5,
            KillFeed::Seven => 7,
        }
    }
}

/// Frame-rate cap. `Monitor` follows the display's refresh rate (none when it is unknown).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub enum FrameLimit {
    #[default]
    Off,
    Monitor,
    Fps(u32),
}

impl FrameLimit {
    /// The cap in frames per second, if any.
    pub fn fps(self, monitor_hz: Option<u32>) -> Option<u32> {
        match self {
            FrameLimit::Off => None,
            FrameLimit::Monitor => monitor_hz,
            FrameLimit::Fps(n) => Some(n),
        }
    }
}

/// The frame-limit segment options: the data's fixed caps plus the monitor's refresh rate (if not already
/// listed), in ascending order, then OFF.
pub fn frame_limit_options(fixed: &[u32], monitor_hz: Option<u32>) -> Vec<FrameLimit> {
    let mut caps: Vec<u32> = fixed.to_vec();
    if let Some(hz) = monitor_hz
        && !caps.contains(&hz)
    {
        caps.push(hz);
    }
    caps.sort_unstable();
    caps.into_iter().map(FrameLimit::Fps).chain([FrameLimit::Off]).collect()
}

/// Which option a frame limit shows as (Monitor maps to the monitor's own rate).
pub fn frame_limit_index(options: &[FrameLimit], value: FrameLimit, monitor_hz: Option<u32>) -> usize {
    let want = match value.fps(monitor_hz) {
        Some(n) => FrameLimit::Fps(n),
        None => FrameLimit::Off,
    };
    options.iter().position(|o| *o == want).unwrap_or(options.len().saturating_sub(1))
}

/// A video mode picked in the resolution list.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Resolution {
    pub width: u32,
    pub height: u32,
    pub refresh_mhz: u32,
}

impl Resolution {
    /// '2560 × 1440 · 165 Hz'.
    pub fn label(self) -> String {
        format!("{} × {} · {} Hz", self.width, self.height, (self.refresh_mhz as f32 / 1000.0).round() as u32)
    }
}

/// The settings tabs (mirrors `screens::SettingsTab`, which has no serde).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub enum Tab {
    Gameplay,
    #[default]
    MouseAim,
    Keybinds,
    Video,
    Audio,
    Hud,
}

impl Tab {
    pub const ALL: [Tab; 6] = [Tab::Gameplay, Tab::MouseAim, Tab::Keybinds, Tab::Video, Tab::Audio, Tab::Hud];

    pub fn label(self) -> &'static str {
        match self {
            Tab::Gameplay => "GAMEPLAY",
            Tab::MouseAim => "MOUSE & AIM",
            Tab::Keybinds => "KEYBINDS",
            Tab::Video => "VIDEO",
            Tab::Audio => "AUDIO",
            Tab::Hud => "HUD & ACCESSIBILITY",
        }
    }

    pub fn screen(self) -> crate::screens::SettingsTab {
        use crate::screens::SettingsTab as S;
        match self {
            Tab::Gameplay => S::Gameplay,
            Tab::MouseAim => S::MouseAim,
            Tab::Keybinds => S::Keybinds,
            Tab::Video => S::Video,
            Tab::Audio => S::Audio,
            Tab::Hud => S::Hud,
        }
    }

    pub fn from_screen(t: crate::screens::SettingsTab) -> Tab {
        Tab::ALL.into_iter().find(|x| x.screen() == t).unwrap_or(Tab::MouseAim)
    }

    /// The next (or previous) tab, wrapping around.
    pub fn step(self, by: i32) -> Tab {
        let i = Tab::ALL.iter().position(|t| *t == self).unwrap_or(0) as i32;
        Tab::ALL[(i + by).rem_euclid(Tab::ALL.len() as i32) as usize]
    }
}

/// Defines a settings section: the struct, and a `Default` that reads the built-in data defaults (so a user
/// file that lacks a field gets the data's value). serde builds a container's default eagerly, even while it
/// parses the built-in file itself; a plain zero value stands in then, since that file sets every field.
macro_rules! section {
    ($(#[$m:meta])* $name:ident from $($path:ident).+ { $($(#[$fm:meta])* $f:ident : $t:ty),* $(,)? }) => {
        $(#[$m])*
        #[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
        #[serde(default)]
        pub struct $name {
            $($(#[$fm])* pub $f: $t),*
        }
        impl Default for $name {
            fn default() -> Self {
                if PARSING_EMBEDDED.with(|p| p.get()) {
                    Self { $($f: Default::default()),* }
                } else {
                    embedded().$($path).+.clone()
                }
            }
        }
    };
}

thread_local! {
    static PARSING_EMBEDDED: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

section!(GameplaySettings from defaults.gameplay {
    auto_sprint: bool,
    jetpack: Jetpack,
    slide: Slide,
    mag_card: MagCard,
    /// Seconds reload (or heal) must be held to open the ring.
    radial_hold_s: f32,
    radial_pick: RadialPick,
});

section!(NetworkSettings from defaults.network {
    host_port: u16,
});

section!(MouseSettings from defaults.mouse {
    dpi: u32,
    /// Mouse travel for one full turn, in cm.
    cm_per_360: f32,
    import_game: ImportGame,
    ads_scaling: AdsScaling,
    /// ADS multiplier per optic id (missing = 1.0).
    optic_mult: BTreeMap<String, f32>,
    ads_input: HoldToggle,
    invert_y: bool,
    /// Horizontal field of view at 16:9, degrees.
    fov_h: f32,
    viewmodel_fov: f32,
});

section!(CrosshairSettings from defaults.crosshair {
    /// '#RRGGBB'.
    color: String,
    outline: bool,
    dot: bool,
    /// Px at 1080p.
    length: f32,
    /// The minimum gap; the gun's live random spread adds to it (none standing still, so every gun at rest shows
    /// this gap).
    gap: f32,
    width: f32,
    hit_markers: HitMarkers,
});

section!(VideoSettings from defaults.video {
    window_mode: WindowModeChoice,
    /// `None` = the monitor's native mode.
    resolution: Option<Resolution>,
    render_scale: f32,
    frame_limit: FrameLimit,
    vsync: bool,
    /// −50..+50; ±50 is ±1 EV (see `brightness_ev`).
    brightness: f32,
    overlay: Overlay,
    preset: Preset,
    aa: Aa,
    shadows: Shadows,
    outlines: bool,
    bloom: Bloom,
    particles: Particles,
    contact_shadows: bool,
    ssr: bool,
    motion_blur: bool,
    vignette: bool,
});

section!(AudioSettings from defaults.audio {
    /// 0..100 each.
    master: f32,
    weapons: f32,
    movement: f32,
    abilities: f32,
    hits: f32,
    interface: f32,
    music: f32,
    output_device: String,
    mix: Mix,
    shield_hit: bool,
    headshot: bool,
    /// Approximate by design: never an exact count.
    low_mag_cue: bool,
    play_in_background: bool,
});

section!(HudSettings from defaults.hud {
    /// Percent.
    scale: f32,
    /// Px at 1080p from the screen edge.
    safe_area: f32,
    ultrawide: Ultrawide,
    health_numbers: HealthNumbers,
    minimap: Minimap,
    damage_numbers: bool,
    kill_feed: KillFeed,
    enemy_names: EnemyNames,
    team_colours: TeamColours,
    enemy_outline: EnemyOutline,
    /// Percent of the visual camera punch (never the recoil pattern).
    screen_shake: f32,
    damage_flash: DamageFlash,
    reduce_flashing: bool,
    text_size: TextSize,
    /// Sprint and crouch.
    hold_toggle: HoldToggle,
});

section!(
    /// Everything the Settings screen edits. Changes apply at once; the screen saves them to `settings.ron`.
    #[derive(Resource)]
    Settings from defaults {
        /// The file format ([`SETTINGS_VERSION`]); a file without one is from before versions (0).
        #[serde(default)]
        version: u32,
        last_tab: Tab,
        gameplay: GameplaySettings,
        network: NetworkSettings,
        mouse: MouseSettings,
        crosshair: CrosshairSettings,
        keybinds: Keybinds,
        video: VideoSettings,
        audio: AudioSettings,
        hud: HudSettings,
    }
);

// ---------------------------------------------------------------------------------------------- data file

/// A number's range: typed values clamp to min..max; sliders draw `track` (min..max if none).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Range {
    pub min: f32,
    pub max: f32,
    pub step: f32,
    #[serde(default)]
    pub track: Option<(f32, f32)>,
}

impl Range {
    pub fn track(&self) -> (f32, f32) {
        self.track.unwrap_or((self.min, self.max))
    }

    /// Clamp to the range and snap to the step.
    pub fn snap(&self, v: f32) -> f32 {
        let v = v.clamp(self.min, self.max);
        if self.step > 0.0 {
            let s = ((v - self.min) / self.step).round() * self.step + self.min;
            // Clean float noise (0.30000001 → 0.3) at the step's precision.
            let k = 10f32.powi(decimals_of(self.step) as i32 + 1);
            ((s * k).round() / k).clamp(self.min, self.max)
        } else {
            v
        }
    }

    /// Where `v` sits on the slider track, 0..1.
    pub fn frac(&self, v: f32) -> f32 {
        let (a, b) = self.track();
        if b > a { ((v - a) / (b - a)).clamp(0.0, 1.0) } else { 0.0 }
    }

    /// The value at a track position (0..1), snapped.
    pub fn at(&self, frac: f32) -> f32 {
        let (a, b) = self.track();
        self.snap(a + (b - a) * frac.clamp(0.0, 1.0))
    }
}

fn decimals_of(step: f32) -> u32 {
    let mut d = 0;
    let mut s = step;
    while d < 4 && (s - s.round()).abs() > 1e-4 {
        s *= 10.0;
        d += 1;
    }
    d
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Ranges {
    pub dpi: Range,
    pub cm_per_360: Range,
    pub import_sens: Range,
    pub optic_mult: Range,
    pub fov_h: Range,
    pub viewmodel_fov: Range,
    pub xh_length: Range,
    pub xh_gap: Range,
    pub xh_width: Range,
    pub render_scale: Range,
    pub brightness: Range,
    pub volume: Range,
    pub hud_scale: Range,
    pub safe_area: Range,
    pub screen_shake: Range,
    pub radial_hold_s: Range,
    pub host_port: Range,
}

/// Yaw per mouse count (degrees) of the games the import box converts from.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ImportYaw {
    pub valorant: f32,
    pub cs2: f32,
    pub apex: f32,
    pub overwatch2: f32,
}

impl ImportYaw {
    pub fn of(&self, g: ImportGame) -> f32 {
        match g {
            ImportGame::Valorant => self.valorant,
            ImportGame::Cs2 => self.cs2,
            ImportGame::Apex => self.apex,
            ImportGame::Overwatch2 => self.overwatch2,
        }
    }
}

/// One ADS row of the Mouse & Aim tab: the optics it covers (multipliers are saved per optic id).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct OpticRow {
    pub label: String,
    #[serde(default)]
    pub sub: Option<String>,
    pub optics: Vec<String>,
}

/// What a quality preset writes.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct QualityPreset {
    pub aa: Aa,
    pub shadows: Shadows,
    pub bloom: Bloom,
    pub particles: Particles,
    pub contact_shadows: bool,
    pub ssr: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Presets {
    pub low: QualityPreset,
    pub medium: QualityPreset,
    pub high: QualityPreset,
    pub ultra: QualityPreset,
}

impl Presets {
    pub fn of(&self, p: Preset) -> QualityPreset {
        match p {
            Preset::Low => self.low,
            Preset::Medium => self.medium,
            Preset::High => self.high,
            Preset::Ultra => self.ultra,
        }
    }
}

/// Shadow-map size and cascade count per shadow level.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ShadowLevels {
    pub map_size: [usize; 3],
    pub cascades: [usize; 3],
}

/// `game/assets/data/settings.ron`: defaults for a new player and every range and table the screen uses.
#[derive(Resource, Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SettingsData {
    pub ranges: Ranges,
    pub import_yaw: ImportYaw,
    pub optic_rows: Vec<OpticRow>,
    /// Brightness ±50 maps to ± this many EV.
    pub brightness_ev: f32,
    /// Text size S / M / L as a factor on HUD text.
    pub text_size_scale: [f32; 3],
    pub shadows: ShadowLevels,
    pub presets: Presets,
    /// Frame caps offered besides the monitor's refresh rate.
    pub frame_limits: Vec<u32>,
    pub defaults: Settings,
}

const EMBEDDED: &str = include_str!("../../../../assets/data/settings.ron");

/// The copy of settings.ron compiled into the binary.
pub fn embedded() -> &'static SettingsData {
    static DATA: OnceLock<SettingsData> = OnceLock::new();
    DATA.get_or_init(|| {
        PARSING_EMBEDDED.with(|p| p.set(true));
        let data = ron::from_str(EMBEDDED);
        PARSING_EMBEDDED.with(|p| p.set(false));
        data.expect("game/assets/data/settings.ron is valid")
    })
}

/// settings.ron from the data folder (so it can be tuned without a rebuild), else the built-in copy.
pub fn load_data() -> SettingsData {
    for dir in [crate::config::assets_root().join("data")] {
        let Ok(text) = std::fs::read_to_string(dir.join("settings.ron")) else { continue };
        match ron::from_str(&text) {
            Ok(d) => return d,
            Err(e) => error!("{}/settings.ron is invalid ({e}); using the built-in copy", dir.display()),
        }
    }
    embedded().clone()
}

// ---------------------------------------------------------------------------------------------- maths

/// cm/360 = 914.4 / (DPI × sens × yaw): 360° over (inches per turn × 2.54).
pub const CM_TURN: f32 = 360.0 * 2.54;

/// View rotation per mouse count (radians) for a turn distance and DPI.
pub fn rad_per_count(cm_per_360: f32, dpi: u32) -> f32 {
    std::f32::consts::TAU * 2.54 / (cm_per_360.max(0.01) * dpi.max(1) as f32)
}

pub fn deg_per_count(cm_per_360: f32, dpi: u32) -> f32 {
    rad_per_count(cm_per_360, dpi).to_degrees()
}

/// Another game's sensitivity for the same turn distance.
pub fn sens_for(cm_per_360: f32, dpi: u32, yaw: f32) -> f32 {
    CM_TURN / (dpi.max(1) as f32 * yaw * cm_per_360.max(0.01))
}

/// The turn distance another game's sensitivity gives.
pub fn cm_from_sens(sens: f32, dpi: u32, yaw: f32) -> f32 {
    CM_TURN / (dpi.max(1) as f32 * sens.max(1e-6) * yaw)
}

/// Vertical FOV (degrees) for a horizontal FOV measured at 16:9.
pub fn vertical_fov(h_deg: f32) -> f32 {
    2.0 * ((h_deg.to_radians() * 0.5).tan() * 9.0 / 16.0).atan().to_degrees()
}

/// Vertical FOV through an optic: the focal length is `zoom` times longer.
pub fn zoomed_fov(v_deg: f32, zoom: f32) -> f32 {
    2.0 * ((v_deg.to_radians() * 0.5).tan() / zoom.max(1.0)).atan().to_degrees()
}

impl Settings {
    /// The ADS sensitivity factor for an optic (1 = hip-fire feel).
    pub fn ads_factor(&self, optic: Option<&str>, zoom: f32) -> f32 {
        let base = match self.mouse.ads_scaling {
            AdsScaling::MatchFocal => {
                let hip = vertical_fov(self.mouse.fov_h);
                (zoomed_fov(hip, zoom).to_radians() * 0.5).tan() / (hip.to_radians() * 0.5).tan()
            }
            AdsScaling::SameCm | AdsScaling::Custom => 1.0,
        };
        base * optic.map_or(1.0, |o| self.optic_mult(o))
    }

    pub fn optic_mult(&self, optic: &str) -> f32 {
        self.mouse.optic_mult.get(optic).copied().unwrap_or(1.0)
    }

    /// Crosshair colour as RGB bytes (the default white if the hex is broken).
    pub fn crosshair_rgb(&self) -> [u8; 3] {
        parse_hex(&self.crosshair.color).unwrap_or([0xF3, 0xF0, 0xE9])
    }

    /// The crosshair code: `XH1-<colour>-O<outline px>-I<length>.<width>.<gap>[-D]`.
    pub fn crosshair_code(&self) -> String {
        let c = &self.crosshair;
        let rgb = self.crosshair_rgb();
        let colour = SWATCHES
            .iter()
            .find(|(_, s)| *s == rgb)
            .map_or_else(|| format!("{:02X}{:02X}{:02X}", rgb[0], rgb[1], rgb[2]), |(l, _)| l.to_string());
        let dot = if c.dot { "-D" } else { "" };
        format!(
            "XH1-{colour}-O{}-I{}.{}.{}{dot}",
            c.outline as u8,
            c.length.round() as i32,
            c.width.round() as i32,
            c.gap.round() as i32
        )
    }

    /// Ally and enemy colours for the chosen colour-blind preset. Halo tier colours never change.
    pub fn team_colors(&self) -> (Color, Color) {
        team_pair(self.hud.team_colours)
    }

    /// The quality preset whose values all match the current ones, or `None` when customised.
    pub fn quality_custom(&self, presets: &Presets) -> bool {
        let p = presets.of(self.video.preset);
        let v = &self.video;
        !(v.aa == p.aa
            && v.shadows == p.shadows
            && v.bloom == p.bloom
            && v.particles == p.particles
            && v.contact_shadows == p.contact_shadows
            && v.ssr == p.ssr)
    }

    /// Write a quality preset into the quality values.
    pub fn apply_preset(&mut self, preset: Preset, presets: &Presets) {
        let p = presets.of(preset);
        let v = &mut self.video;
        v.preset = preset;
        v.aa = p.aa;
        v.shadows = p.shadows;
        v.bloom = p.bloom;
        v.particles = p.particles;
        v.contact_shadows = p.contact_shadows;
        v.ssr = p.ssr;
    }

    /// Reset one tab's values to the defaults (the player name and last tab are kept).
    pub fn reset_tab(&mut self, tab: Tab, defaults: &Settings) {
        match tab {
            Tab::Gameplay => {
                self.gameplay = defaults.gameplay.clone();
                self.network = defaults.network.clone();
                // SHOW NET GRAPH sits on this tab; it is VIDEO's '+ NETWORK' overlay.
                if (self.video.overlay == Overlay::Network) != (defaults.video.overlay == Overlay::Network) {
                    self.video.overlay = defaults.video.overlay;
                }
            }
            Tab::MouseAim => {
                self.mouse = defaults.mouse.clone();
                self.crosshair = defaults.crosshair.clone();
            }
            Tab::Keybinds => self.keybinds = defaults.keybinds.clone(),
            Tab::Video => self.video = defaults.video.clone(),
            Tab::Audio => self.audio = defaults.audio.clone(),
            Tab::Hud => self.hud = defaults.hud.clone(),
        }
    }

    pub fn reset_all(&mut self, defaults: &Settings) {
        let tab = self.last_tab;
        *self = defaults.clone();
        self.last_tab = tab;
    }

    /// Fill what an older settings file lacks: actions added to the key map since, and the ADS multiplier of an
    /// optic added to an ADS row since (it takes the value the row shows, saved for the row's other optics).
    pub fn complete(&mut self, data: &SettingsData) {
        self.keybinds.fill_missing(&data.defaults.keybinds);
        for row in &data.optic_rows {
            let Some(v) = row.optics.iter().find_map(|o| self.mouse.optic_mult.get(o).copied()) else { continue };
            for o in &row.optics {
                self.mouse.optic_mult.entry(o.clone()).or_insert(v);
            }
        }
    }
}

/// Version 1 (2026-10-08, user direction: sprint by default with Shift to walk, B heals, a small plus crosshair):
/// the key bindings whose default moved, with the old default. Each moves to today's default (the data's) only
/// while a file still holds the old one.
const V1_KEYS: [(Action, KeyCode); 4] = [
    (Action::Sprint, KeyCode::ShiftLeft),
    (Action::Walk, KeyCode::AltLeft),
    (Action::FireMode, KeyCode::KeyB),
    (Action::Heal, KeyCode::KeyH),
];

/// The crosshair lines before version 1, (length, gap, width) px. They move as one shape.
const V1_CROSSHAIR: (f32, f32, f32) = (7.0, 5.0, 2.0);

impl Settings {
    /// Bring a file of an older version up to [`SETTINGS_VERSION`]. A value moves to its new default only while
    /// it still holds the old default, so a choice the player made is kept; a moved key binding that would clash
    /// with one of the player's own bindings stays where it was. Returns whether anything ran (the file should
    /// then be saved, with the new version).
    pub fn migrate(&mut self, defaults: &Settings) -> bool {
        if self.version >= SETTINGS_VERSION {
            return false;
        }
        if self.version < 1 {
            self.migrate_v1(defaults);
        }
        self.version = SETTINGS_VERSION;
        true
    }

    fn migrate_v1(&mut self, d: &Settings) {
        // Auto-sprint was off by default (indistinguishable from turned off: it comes on).
        if !self.gameplay.auto_sprint {
            self.gameplay.auto_sprint = d.gameplay.auto_sprint;
        }
        let c = &mut self.crosshair;
        if (c.length, c.gap, c.width) == V1_CROSSHAIR {
            (c.length, c.gap, c.width) = (d.crosshair.length, d.crosshair.gap, d.crosshair.width);
        }
        let before = self.keybinds.clone();
        let mut moved: Vec<Action> = V1_KEYS
            .iter()
            .filter(|(a, old)| before.get(*a) == [Some(Binding::Key(*old)), None])
            .map(|(a, _)| *a)
            .collect();
        for a in &moved {
            self.keybinds.0.insert(*a, d.keybinds.get(*a));
        }
        // Undo the moves that clash, one at a time (undoing one can make another clash).
        while let Some(i) = {
            let clash = self.keybinds.conflicts();
            moved.iter().position(|a| clash.iter().any(|((x, _), _)| x == a))
        } {
            let a = moved.remove(i);
            self.keybinds.0.insert(a, before.get(a));
        }
    }
}

pub fn team_pair(t: TeamColours) -> (Color, Color) {
    use crate::ui_kit::{ALLY, ENEMY, hex};
    match t {
        TeamColours::Default => (ALLY, ENEMY),
        TeamColours::Deutan | TeamColours::Protan => (hex(0x3FA9F5), hex(0xFFB000)),
        // Not in the mockup: a proposal, flagged for design.
        TeamColours::Tritan => (hex(0x00C2C7), hex(0xFF3D7F)),
    }
}

/// The crosshair colour swatches and their code letters.
pub const SWATCHES: [(&str, [u8; 3]); 5] = [
    ("W", [0xF3, 0xF0, 0xE9]),
    ("I", [0xB3, 0xED, 0xFF]),
    ("Y", [0xF6, 0xFF, 0x52]),
    ("G", [0x52, 0xE5, 0xA5]),
    ("M", [0xFF, 0x4D, 0xF0]),
];

/// '#RRGGBB' (or without '#') to bytes.
pub fn parse_hex(s: &str) -> Option<[u8; 3]> {
    let h = s.trim().trim_start_matches('#');
    if h.len() != 6 || !h.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let b = |i: usize| u8::from_str_radix(&h[i..i + 2], 16).ok();
    Some([b(0)?, b(2)?, b(4)?])
}

pub fn hex_string(rgb: [u8; 3]) -> String {
    format!("#{:02X}{:02X}{:02X}", rgb[0], rgb[1], rgb[2])
}

pub fn rgb_color(rgb: [u8; 3]) -> Color {
    Color::srgb_u8(rgb[0], rgb[1], rgb[2])
}

/// Parse a crosshair code back into crosshair values (the colour, outline, lines and dot).
pub fn parse_crosshair_code(code: &str, into: &mut CrosshairSettings) -> bool {
    let parts: Vec<&str> = code.trim().split('-').collect();
    if parts.len() < 4 || !parts[0].eq_ignore_ascii_case("XH1") {
        return false;
    }
    let rgb = match SWATCHES.iter().find(|(l, _)| l.eq_ignore_ascii_case(parts[1])) {
        Some((_, rgb)) => *rgb,
        None => match parse_hex(parts[1]) {
            Some(rgb) => rgb,
            None => return false,
        },
    };
    let Some(outline) = parts[2].strip_prefix(['O', 'o']).and_then(|n| n.parse::<u8>().ok()) else { return false };
    let Some(lines) = parts[3].strip_prefix(['I', 'i']) else { return false };
    let nums: Vec<f32> = lines.split('.').filter_map(|n| n.parse().ok()).collect();
    let [length, width, gap] = nums[..] else { return false };
    into.color = hex_string(rgb);
    into.outline = outline > 0;
    into.length = length;
    into.width = width;
    into.gap = gap;
    into.dot = parts.get(4).is_some_and(|d| d.eq_ignore_ascii_case("D"));
    true
}

/// The crosshair as rectangles (x, y, w, h) around the centre, in px at 1080p: four arms `gap` px out (the
/// live spread adds to the base gap), plus the centre dot when it is on.
pub fn crosshair_rects(c: &CrosshairSettings, extra_gap: f32) -> Vec<(f32, f32, f32, f32)> {
    let (l, w, g) = (c.length.max(0.0), c.width.max(1.0), c.gap.max(0.0) + extra_gap.max(0.0));
    let mut r = Vec::with_capacity(5);
    if l > 0.0 {
        r.push((-w / 2.0, -g - l, w, l)); // up
        r.push((-w / 2.0, g, w, l)); // down
        r.push((-g - l, -w / 2.0, l, w)); // left
        r.push((g, -w / 2.0, l, w)); // right
    }
    if c.dot {
        r.push((-w / 2.0, -w / 2.0, w, w));
    }
    r
}

/// The ruler under the sensitivity card: one full turn, drawn at cm × 10 px (clamped).
pub fn ruler_px(cm: f32) -> f32 {
    (cm * 10.0).clamp(150.0, 620.0)
}

/// Format a number with fixed decimals (no '-0').
pub fn fmt_num(v: f32, decimals: usize) -> String {
    let s = format!("{v:.decimals$}");
    if s.starts_with('-') && s[1..].chars().all(|c| c == '0' || c == '.') { s[1..].to_string() } else { s }
}

/// Parse a typed number, ignoring a trailing unit ('103°', '100 %', '32 px', '0.20 s').
pub fn parse_num(s: &str) -> Option<f32> {
    let t: String = s.trim().chars().take_while(|c| c.is_ascii_digit() || matches!(c, '.' | '-' | '+' | ',')).collect();
    let t = t.replace(',', ".");
    let v: f32 = t.parse().ok()?;
    v.is_finite().then_some(v)
}

/// The key cap labels of a composite Move binding, e.g. 'W A S D'.
pub fn move_label(kb: &Keybinds, slot: usize) -> Option<String> {
    let keys: Vec<String> = Action::MOVE.iter().map(|a| kb.slot(*a, slot).map(|b| b.label())).collect::<Option<_>>()?;
    Some(keys.join(" "))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_data_file_parses_and_has_the_mockup_defaults() {
        let d = embedded();
        let s = &d.defaults;
        assert_eq!(s.mouse.dpi, 800);
        assert!((s.mouse.cm_per_360 - 40.8).abs() < 1e-4);
        assert_eq!(s.mouse.fov_h, 103.0);
        assert_eq!(s.video.window_mode, WindowModeChoice::Borderless);
        assert_eq!(s.video.aa, Aa::Smaa);
        assert_eq!(s.audio.master, 80.0);
        assert_eq!(s.hud.kill_feed, KillFeed::Five);
        assert_eq!(s.crosshair.hit_markers, HitMarkers::ShieldFlesh);
        assert!((s.gameplay.radial_hold_s - 0.2).abs() < 1e-6, "the old RELOAD_HOLD_S");
        let net = vetf_sim::GameData::embedded().net;
        assert_eq!(s.network.host_port, net.port, "the default host port is the game's port (net.ron)");
        // the reload tap/hold, heal and every action has a default
        for a in Action::ALL {
            assert!(s.keybinds.0.contains_key(&a), "{a:?} has a default binding");
        }
        assert!(s.keybinds.conflicts().is_empty(), "no clashing defaults: {:?}", s.keybinds.conflicts());
        assert_eq!(s.version, SETTINGS_VERSION, "a new player's file is current");
        // user direction 2026-10-08: sprint by default, Shift walks, B heals, H switches the fire mode
        assert!(s.gameplay.auto_sprint);
        let key = |a: Action| s.keybinds.slot(a, 0);
        assert_eq!(key(Action::Walk), Some(Binding::Key(KeyCode::ShiftLeft)));
        assert_eq!(key(Action::HoldBreath), Some(Binding::Key(KeyCode::ShiftLeft)), "scoped, Shift does both");
        assert_eq!(key(Action::Sprint), Some(Binding::Key(KeyCode::AltLeft)));
        assert_eq!(key(Action::Heal), Some(Binding::Key(KeyCode::KeyB)));
        assert_eq!(key(Action::FireMode), Some(Binding::Key(KeyCode::KeyH)));
        assert_eq!(move_label(&s.keybinds, 0).as_deref(), Some("W A S D"));
        // every default sits inside its range
        let r = &d.ranges;
        for (v, range) in [
            (s.mouse.cm_per_360, r.cm_per_360),
            (s.mouse.fov_h, r.fov_h),
            (s.mouse.viewmodel_fov, r.viewmodel_fov),
            (s.crosshair.length, r.xh_length),
            (s.crosshair.gap, r.xh_gap),
            (s.crosshair.width, r.xh_width),
            (s.video.render_scale, r.render_scale),
            (s.video.brightness, r.brightness),
            (s.hud.scale, r.hud_scale),
            (s.hud.safe_area, r.safe_area),
            (s.hud.screen_shake, r.screen_shake),
            (s.gameplay.radial_hold_s, r.radial_hold_s),
        ] {
            assert!(v >= range.min && v <= range.max, "{v} in {range:?}");
        }
        // the data's optics exist
        let game = vetf_sim::GameData::embedded();
        for row in &d.optic_rows {
            for o in &row.optics {
                assert!(game.attachment(o).is_some(), "{o} is an attachment");
            }
        }
    }

    #[test]
    fn user_files_round_trip_and_fill_missing_fields() {
        let mut s = Settings::default();
        s.mouse.cm_per_360 = 33.3;
        s.mouse.optic_mult.insert("optic_3x".into(), 0.92);
        s.video.frame_limit = FrameLimit::Fps(144);
        s.video.resolution = Some(Resolution { width: 2560, height: 1440, refresh_mhz: 165_000 });
        s.keybinds.set(Action::Melee, 0, Some(super::super::bindings::Binding::Key(KeyCode::KeyV)));
        let text = ron::ser::to_string_pretty(&s, ron::ser::PrettyConfig::default()).unwrap();
        assert_eq!(ron::from_str::<Settings>(&text).unwrap(), s);
        // an old file with only one section keeps the defaults for the rest
        let partial: Settings = ron::from_str("(mouse: (dpi: 1600))").unwrap();
        assert_eq!(partial.mouse.dpi, 1600);
        assert_eq!(partial.mouse.cm_per_360, Settings::default().mouse.cm_per_360);
        assert_eq!(partial.video, Settings::default().video);
    }

    /// The projector joined the holo / red dot ADS row after players had saved that row: an older file's value
    /// reaches it, as the row shows it (review finding: it stayed at 1.00 while the row read 0.85). Every optic
    /// has a row, and the row's label names the projector.
    #[test]
    fn an_optic_added_to_a_row_takes_the_rows_saved_multiplier() {
        let d = embedded();
        let row = d.optic_rows.iter().find(|r| r.optics.iter().any(|o| o == "optic_projector")).unwrap();
        assert!(row.optics.iter().any(|o| o == "optic_holo") && row.optics.iter().any(|o| o == "optic_reddot"));
        assert!(row.label.to_lowercase().contains("projector"), "{}", row.label);
        let game = vetf_sim::GameData::embedded();
        for a in game.attachments.attachments.iter().filter(|a| a.cat == vetf_sim::data::AttachmentCategory::Optic) {
            assert!(d.optic_rows.iter().any(|r| r.optics.contains(&a.id)), "{} has an ADS row", a.id);
        }

        let old = r#"(mouse: (optic_mult: {"optic_holo": 0.85, "optic_reddot": 0.85, "optic_3x": 0.9}))"#;
        let mut s: Settings = ron::from_str(old).unwrap();
        assert_eq!(s.optic_mult("optic_projector"), 1.0, "the file itself has no projector value");
        s.complete(d);
        assert_eq!(s.optic_mult("optic_projector"), 0.85, "the holo / red dot value");
        assert_eq!((s.optic_mult("optic_holo"), s.optic_mult("optic_3x")), (0.85, 0.9), "saved values stay");
        assert_eq!(s.optic_mult("optic_thermal"), 1.0, "a row never set stays at the default");
        assert!(!s.mouse.optic_mult.contains_key("optic_thermal"));
        // a value saved for the projector itself wins
        let mut s: Settings =
            ron::from_str(r#"(mouse: (optic_mult: {"optic_holo": 0.85, "optic_projector": 1.1}))"#).unwrap();
        s.complete(d);
        assert_eq!((s.optic_mult("optic_projector"), s.optic_mult("optic_reddot")), (1.1, 0.85));
    }

    #[test]
    fn sensitivity_maths_match_the_mockup() {
        // Valorant 0.400 at 800 DPI is 40.8 cm / 360
        assert!((cm_from_sens(0.4, 800, 0.07) - 40.82).abs() < 0.01);
        assert!((sens_for(40.8, 800, 0.07) - 0.400).abs() < 0.001);
        assert!((sens_for(40.8, 800, 0.022) - 1.273).abs() < 0.001);
        // 16.1 in and 0.0280° per count
        assert!((40.8f32 / 2.54 - 16.06).abs() < 0.01);
        assert!((deg_per_count(40.8, 800) - 0.0280).abs() < 0.0001);
        // one turn of the mouse is one full turn of the view
        let counts = 40.8 / 2.54 * 800.0;
        assert!((rad_per_count(40.8, 800) * counts - std::f32::consts::TAU).abs() < 1e-3);
        assert_eq!(ruler_px(40.8), 408.0);
        assert_eq!(ruler_px(5.0), 150.0);
    }

    #[test]
    fn fov_and_ads_scaling() {
        assert!((vertical_fov(103.0) - 70.5).abs() < 0.1);
        assert!((zoomed_fov(70.0, 1.0) - 70.0).abs() < 1e-4);
        let mut s = Settings::default();
        s.mouse.ads_scaling = AdsScaling::MatchFocal;
        // matching the focal length is 1 / zoom
        assert!((s.ads_factor(Some("optic_3x"), 3.0) - 1.0 / 3.0).abs() < 1e-4);
        s.mouse.optic_mult.insert("optic_3x".into(), 0.9);
        assert!((s.ads_factor(Some("optic_3x"), 3.0) - 0.3).abs() < 1e-4);
        s.mouse.ads_scaling = AdsScaling::SameCm;
        assert_eq!(s.ads_factor(Some("optic_3x"), 3.0), 0.9);
        assert_eq!(s.ads_factor(None, 1.0), 1.0);
    }

    #[test]
    fn crosshair_code_round_trips() {
        let s = Settings::default();
        assert_eq!(s.crosshair_code(), "XH1-W-O1-I4.2.2");
        let mut c = s.crosshair.clone();
        c.color = "#123456".into();
        c.dot = true;
        c.outline = false;
        let s2 = Settings { crosshair: c.clone(), ..s.clone() };
        let code = s2.crosshair_code();
        assert_eq!(code, "XH1-123456-O0-I4.2.2-D");
        let mut back = s.crosshair.clone();
        assert!(parse_crosshair_code(&code, &mut back));
        assert_eq!(back, c);
        assert!(!parse_crosshair_code("XH2-W", &mut back));
        // the default is a small plus (user direction 2026-10-08): 2x4 arms from 2 to 6 px off centre
        let r = crosshair_rects(&s.crosshair, 0.0);
        assert_eq!(r[0], (-1.0, -6.0, 2.0, 4.0));
        assert_eq!(r[3], (2.0, -1.0, 4.0, 2.0));
        assert_eq!(r.len(), 4, "no dot by default");
    }

    /// A settings file saved before versions, with the defaults of the time (abridged to the parts that moved;
    /// a real file lists every field, which changes nothing here).
    const OLD_DEFAULTS: &str = r##"(
        last_tab: MouseAim,
        gameplay: (auto_sprint: false, jetpack: HoldJumpInAir, slide: CrouchWhileSprinting, mag_card: ThreeSeconds,
            radial_hold_s: 0.2, radial_pick: Release),
        crosshair: (color: "#F3F0E9", outline: true, dot: false, length: 7.0, gap: 5.0, width: 2.0,
            hit_markers: ShieldFlesh),
        keybinds: {
            MoveForward: (Some("KeyW"), None), MoveLeft: (Some("KeyA"), None), MoveBack: (Some("KeyS"), None),
            MoveRight: (Some("KeyD"), None), Jump: (Some("Space"), Some("WheelDown")),
            Sprint: (Some("ShiftLeft"), None), Walk: (Some("AltLeft"), None),
            Crouch: (Some("ControlLeft"), Some("KeyC")), Interact: (Some("KeyF"), None),
            Fire: (Some("MouseLeft"), None), Ads: (Some("MouseRight"), None), Reload: (Some("KeyR"), None),
            MagCheck: (Some("KeyT"), None), FireMode: (Some("KeyB"), None), Underbarrel: (Some("KeyG"), None),
            Laser: (Some("KeyV"), None), Melee: (Some("Digit3"), None), HoldBreath: (Some("ShiftLeft"), None),
            Ability1: (Some("KeyQ"), None), Signature: (Some("KeyE"), None), Ultimate: (Some("KeyX"), None),
            Heal: (Some("KeyH"), None), Scoreboard: (Some("Tab"), None), Ping: (Some("MouseMiddle"), Some("KeyZ")),
            Chat: (Some("Enter"), Some("KeyY")), ChangeLoadout: (Some("KeyL"), None),
        },
        mouse: (dpi: 1600),
    )"##;

    fn migrated(text: &str) -> (Settings, bool) {
        let d = embedded();
        let mut s: Settings = ron::from_str(text).unwrap();
        s.complete(d);
        let ran = s.migrate(&d.defaults);
        (s, ran)
    }

    /// A file of the old defaults gets every new default (and keeps its other values); the result is current.
    #[test]
    fn an_old_file_with_the_old_defaults_gets_the_new_ones() {
        let d = &embedded().defaults;
        let raw: Settings = ron::from_str(OLD_DEFAULTS).unwrap();
        assert_eq!(raw.version, 0, "a file without a version is from before versions");
        let (s, ran) = migrated(OLD_DEFAULTS);
        assert!(ran && s.version == SETTINGS_VERSION);
        assert_eq!(s.keybinds, d.keybinds, "every binding at today's default");
        assert_eq!(s.gameplay, d.gameplay);
        assert_eq!(s.crosshair, d.crosshair);
        assert_eq!(s.mouse.dpi, 1600, "the player's own values stay");
        assert!(s.keybinds.conflicts().is_empty());
        // saved and loaded again: nothing left to do
        let text = ron::ser::to_string_pretty(&s, ron::ser::PrettyConfig::default()).unwrap();
        let (again, ran) = migrated(&text);
        assert!(!ran);
        assert_eq!(again, s);
    }

    /// A player who changed a value keeps it; only values still at the old default move.
    #[test]
    fn an_old_file_keeps_the_players_own_choices() {
        let d = &embedded().defaults;
        let custom = OLD_DEFAULTS
            .replace(r#"Walk: (Some("AltLeft"), None)"#, r#"Walk: (Some("KeyN"), None)"#)
            .replace(r#"FireMode: (Some("KeyB"), None)"#, r#"FireMode: (Some("KeyB"), Some("MouseBack"))"#)
            .replace("length: 7.0", "length: 10.0")
            .replace(r##"color: "#F3F0E9""##, r##"color: "#52E5A5""##);
        let (s, ran) = migrated(&custom);
        assert!(ran && s.version == SETTINGS_VERSION);
        let key = |a: Action, i: usize| s.keybinds.slot(a, i);
        assert_eq!(key(Action::Walk, 0), Some(Binding::Key(KeyCode::KeyN)), "a rebound walk stays");
        assert_eq!(key(Action::FireMode, 1), Some(Binding::Mouse(MouseButton::Back)), "a changed pair stays");
        assert_eq!(key(Action::FireMode, 0), Some(Binding::Key(KeyCode::KeyB)));
        // Sprint moved to Alt; Heal could not take B from fire mode, so it stays on H
        assert_eq!(key(Action::Sprint, 0), d.keybinds.slot(Action::Sprint, 0));
        assert_eq!(key(Action::Heal, 0), Some(Binding::Key(KeyCode::KeyH)), "no clash is made");
        assert!(s.keybinds.conflicts().is_empty(), "{:?}", s.keybinds.conflicts());
        assert!(s.gameplay.auto_sprint);
        assert_eq!((s.crosshair.length, s.crosshair.gap, s.crosshair.width), (10.0, 5.0, 2.0), "a custom shape stays");
        assert_eq!(s.crosshair.color, "#52E5A5");
        // the player's binding of Alt to something else keeps Sprint on Shift (and Walk on its old key)
        let alt = OLD_DEFAULTS
            .replace(r#"Walk: (Some("AltLeft"), None)"#, r#"Walk: (Some("CapsLock"), None)"#)
            .replace(r#"Melee: (Some("Digit3"), None)"#, r#"Melee: (Some("AltLeft"), None)"#);
        let (s, _) = migrated(&alt);
        assert_eq!(s.keybinds.slot(Action::Sprint, 0), Some(Binding::Key(KeyCode::ShiftLeft)));
        assert_eq!(s.keybinds.slot(Action::Melee, 0), Some(Binding::Key(KeyCode::AltLeft)));
    }

    /// A current file is left alone, even where it holds an old default on purpose.
    #[test]
    fn a_current_file_is_not_migrated() {
        let mut s = embedded().defaults.clone();
        s.gameplay.auto_sprint = false;
        s.keybinds.set(Action::Sprint, 0, Some(Binding::Key(KeyCode::ShiftLeft)));
        s.keybinds.set(Action::Walk, 0, Some(Binding::Key(KeyCode::AltLeft)));
        s.crosshair.length = 7.0;
        s.crosshair.gap = 5.0;
        let text = ron::ser::to_string_pretty(&s, ron::ser::PrettyConfig::default()).unwrap();
        assert!(text.contains("version: 1"), "{text}");
        let (back, ran) = migrated(&text);
        assert!(!ran);
        assert_eq!(back, s);
    }

    #[test]
    fn ranges_snap_and_map_to_the_track() {
        let r = embedded().ranges.cm_per_360;
        assert_eq!(r.snap(40.83), 40.8);
        assert_eq!(r.snap(500.0), 150.0);
        assert!((r.frac(40.8) - (40.8 - 15.0) / 65.0).abs() < 1e-5, "the slider track is 15-80 cm");
        assert_eq!(r.at(1.0), 80.0);
        let h = embedded().ranges.radial_hold_s;
        assert_eq!(h.snap(0.33), 0.35);
        assert_eq!(parse_num("103°"), Some(103.0));
        assert_eq!(parse_num(" 32 px"), Some(32.0));
        assert_eq!(parse_num("0,20 s"), Some(0.2));
        assert_eq!(parse_num("abc"), None);
        assert_eq!(fmt_num(-0.001, 0), "0");
        assert_eq!(fmt_num(0.4, 3), "0.400");
    }

    #[test]
    fn presets_and_custom_detection() {
        let d = embedded();
        let mut s = d.defaults.clone();
        s.apply_preset(Preset::High, &d.presets);
        assert!(!s.quality_custom(&d.presets));
        s.video.shadows = Shadows::Medium;
        assert!(s.quality_custom(&d.presets), "HIGH with medium shadows is custom, like the mockup");
        s.apply_preset(Preset::Low, &d.presets);
        assert_eq!(s.video.aa, Aa::Fxaa);
        assert_eq!(s.video.bloom, Bloom::Off);
    }

    #[test]
    fn frame_limit_options_include_the_monitor() {
        let o = frame_limit_options(&[60, 144, 240], Some(165));
        assert_eq!(
            o,
            vec![
                FrameLimit::Fps(60),
                FrameLimit::Fps(144),
                FrameLimit::Fps(165),
                FrameLimit::Fps(240),
                FrameLimit::Off
            ]
        );
        assert_eq!(frame_limit_index(&o, FrameLimit::Monitor, Some(165)), 2);
        let o = frame_limit_options(&[60, 144, 240], None);
        assert_eq!(o.len(), 4);
        assert_eq!(frame_limit_index(&o, FrameLimit::Monitor, None), 3, "unknown refresh: OFF");
        assert_eq!(frame_limit_options(&[60, 144, 240], Some(60)).len(), 4, "60 Hz is already listed");
    }

    #[test]
    fn names_tabs_and_teams() {
        // The PLAYER NAME field uses the first-launch prompt's rule (spaces and dots allowed).
        assert_eq!(crate::user_config::PlayerProfile::clean_name("kestrel you."), Some("KESTREL YOU.".into()));
        assert_eq!(Tab::Gameplay.step(-1), Tab::Hud);
        assert_eq!(Tab::Hud.step(1), Tab::Gameplay);
        for t in Tab::ALL {
            assert_eq!(Tab::from_screen(t.screen()), t);
        }
        let (ally, enemy) = team_pair(TeamColours::Deutan);
        assert_ne!(ally, crate::ui_kit::ALLY);
        assert_ne!(enemy, crate::ui_kit::ENEMY);
        assert_eq!(Resolution { width: 2560, height: 1440, refresh_mhz: 164_999 }.label(), "2560 × 1440 · 165 Hz");
    }
}
