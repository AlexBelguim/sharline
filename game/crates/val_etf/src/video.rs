//! The VIDEO settings put to work (hub spec 10): window mode and resolution, V-sync, a frame limiter,
//! brightness, anti-aliasing, shadows, bloom, the cheap screen effects (contact shadows, motion blur,
//! vignette), the map's parallax surface depth (by quality preset) and the performance overlay. Every change
//! applies at once.
//!
//! Not applied: render scale (it needs a render-to-texture 3D camera), stylized outlines and particles (the
//! blockout renderer has neither) and SSR (Bevy's only works with deferred rendering).
//!
//! Scripted runs (screenshots, demos, `--exit-after` tests) keep their window as the command line made it,
//! 1920x1080 windowed for screenshots, whatever the saved settings say; they also hide the overlay (except
//! `--demo-ui overlay`), so screenshots compare cleanly with the mockups.

use crate::config::Cli;
use crate::map_materials::SurfaceDepthLevel;
use crate::render::ViewCamera;
use crate::settings::{Aa, Bloom as BloomLevel, Overlay, Preset, Resolution, Settings, SettingsData, VideoSettings};
use crate::settings::{Shadows, WindowModeChoice};
use crate::ui_kit::{self as kit, Face, UiFonts, abs};
use bevy::anti_alias::{fxaa::Fxaa, smaa::Smaa, taa::TemporalAntiAliasing};
use bevy::core_pipeline::prepass::{DepthPrepass, MotionVectorPrepass};
use bevy::diagnostic::{DiagnosticsStore, FrameTimeDiagnosticsPlugin};
use bevy::light::{CascadeShadowConfigBuilder, DirectionalLightShadowMap};
use bevy::pbr::ContactShadows;
use bevy::post_process::bloom::Bloom;
use bevy::post_process::effect_stack::Vignette;
use bevy::post_process::motion_blur::MotionBlur;
use bevy::prelude::*;
use bevy::render::camera::{MipBias, TemporalJitter};
use bevy::render::view::{ColorGrading, Msaa};
use bevy::window::{
    Monitor, MonitorSelection, PresentMode, PrimaryMonitor, PrimaryWindow, VideoMode, VideoModeSelection, WindowMode,
};
use lightyear::prelude::Controlled;
use std::time::{Duration, Instant};
use vetf_net::PlayerNet;

pub struct VideoPlugin;

impl Plugin for VideoPlugin {
    fn build(&self, app: &mut App) {
        if !app.is_plugin_added::<FrameTimeDiagnosticsPlugin>() {
            app.add_plugins(FrameTimeDiagnosticsPlugin::default());
        }
        app.insert_resource(FrameClock(Instant::now()))
            .init_resource::<SurfaceDepthLevel>()
            .add_systems(Startup, spawn_overlay)
            .add_systems(Update, (apply_window, apply_camera, apply_shadows, apply_surface_depth, update_overlay))
            .add_systems(Last, limit_frame_rate);
    }
}

/// Bloom intensity per BLOOM level (Bevy's natural preset is 0.15).
const BLOOM_LOW: f32 = 0.05;
const BLOOM_HIGH: f32 = 0.15;
/// A light vignette: the corners darken by this much at most.
const VIGNETTE_INTENSITY: f32 = 0.35;
/// The overlay refreshes this often, so its numbers stay readable.
const OVERLAY_EVERY_S: f32 = 0.25;
/// The limiter sleeps until this close to the deadline, then spins (a sleep can overshoot by a millisecond).
const SPIN_MARGIN: Duration = Duration::from_micros(800);

// ---------------------------------------------------------------------------------------------- window

/// The video mode a resolution names on the monitor: the exact mode, else the same size at its best refresh
/// rate (the saved refresh rate may be gone on another monitor).
pub fn matching_mode(res: Resolution, modes: &[VideoMode]) -> Option<VideoMode> {
    let size = |m: &&VideoMode| m.physical_size == UVec2::new(res.width, res.height);
    modes
        .iter()
        .filter(size)
        .find(|m| m.refresh_rate_millihertz == res.refresh_mhz)
        .or_else(|| modes.iter().filter(size).max_by_key(|m| m.refresh_rate_millihertz))
        .copied()
}

/// The window mode for WINDOW MODE and RESOLUTION. Borderless always covers the monitor at its own mode;
/// windowed takes the resolution as its size (see [`windowed_size`]).
pub fn window_mode_for(choice: WindowModeChoice, res: Option<Resolution>, modes: &[VideoMode]) -> WindowMode {
    match choice {
        WindowModeChoice::Windowed => WindowMode::Windowed,
        WindowModeChoice::Borderless => WindowMode::BorderlessFullscreen(MonitorSelection::Current),
        WindowModeChoice::Fullscreen => {
            let mode = res.and_then(|r| matching_mode(r, modes));
            WindowMode::Fullscreen(
                MonitorSelection::Current,
                mode.map_or(VideoModeSelection::Current, VideoModeSelection::Specific),
            )
        }
    }
}

/// A windowed window's size in physical pixels: the picked resolution, or none (keep the size it has).
pub fn windowed_size(choice: WindowModeChoice, res: Option<Resolution>) -> Option<UVec2> {
    res.filter(|_| choice == WindowModeChoice::Windowed).map(|r| UVec2::new(r.width, r.height))
}

pub fn present_mode(vsync: bool) -> PresentMode {
    if vsync { PresentMode::AutoVsync } else { PresentMode::AutoNoVsync }
}

/// The primary monitor's refresh rate in Hz (FRAME LIMIT's MONITOR option), like the settings screen reads it.
fn monitor_hz(monitors: &Query<(&Monitor, Has<PrimaryMonitor>)>) -> Option<u32> {
    let m = monitors.iter().find(|(_, p)| *p).or_else(|| monitors.iter().next())?.0;
    m.refresh_rate_millihertz.map(|mhz| (mhz + 500) / 1000)
}

/// V-sync always; window mode and resolution only for a player's run, once the window is shown (scripted
/// and `--monitor` runs start hidden until `main::place_window` has moved them).
fn apply_window(
    cli: Res<Cli>,
    settings: Res<Settings>,
    mut windows: Query<&mut Window, With<PrimaryWindow>>,
    monitors: Query<(&Monitor, Has<PrimaryMonitor>)>,
    mut applied: Local<Option<(WindowModeChoice, Option<Resolution>)>>,
) {
    let Ok(mut window) = windows.single_mut() else { return };
    let v = &settings.video;
    let present = present_mode(v.vsync);
    if window.present_mode != present {
        window.present_mode = present;
    }
    let want = (v.window_mode, v.resolution);
    if cli.automated() || !window.visible || *applied == Some(want) {
        return;
    }
    let modes: Vec<VideoMode> = monitors
        .iter()
        .find(|(_, p)| *p)
        .or_else(|| monitors.iter().next())
        .map(|(m, _)| m.video_modes.clone())
        .unwrap_or_default();
    // A fullscreen resolution waits for the monitor's modes (winit lists them in the first frames).
    if v.window_mode == WindowModeChoice::Fullscreen && v.resolution.is_some() && modes.is_empty() {
        return;
    }
    *applied = Some(want);
    let mode = window_mode_for(v.window_mode, v.resolution, &modes);
    if window.mode != mode {
        window.mode = mode;
    }
    if let Some(size) = windowed_size(v.window_mode, v.resolution)
        && window.physical_size() != size
    {
        window.resolution.set_physical_resolution(size.x, size.y);
    }
}

// ---------------------------------------------------------------------------------------------- frame limit

/// When the last frame ended (the frame limiter's clock).
#[derive(Resource)]
struct FrameClock(Instant);

/// How long to wait so a frame that took `took` lasts `budget`.
pub fn frame_wait(took: Duration, budget: Duration) -> Duration {
    budget.saturating_sub(took)
}

/// FRAME LIMIT: sleep away what is left of the frame budget, at the very end of the frame.
fn limit_frame_rate(
    settings: Res<Settings>,
    monitors: Query<(&Monitor, Has<PrimaryMonitor>)>,
    mut clock: ResMut<FrameClock>,
) {
    if let Some(fps) = settings.video.frame_limit.fps(monitor_hz(&monitors)).filter(|f| *f > 0) {
        let budget = Duration::from_secs_f64(1.0 / fps as f64);
        let deadline = clock.0 + budget;
        let wait = frame_wait(clock.0.elapsed(), budget);
        if wait > SPIN_MARGIN {
            std::thread::sleep(wait - SPIN_MARGIN);
        }
        while Instant::now() < deadline {
            std::hint::spin_loop();
        }
    }
    clock.0 = Instant::now();
}

// ---------------------------------------------------------------------------------------------- camera

/// What the VIDEO settings ask of the view camera.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CameraFx {
    pub msaa: Msaa,
    pub fxaa: bool,
    pub smaa: bool,
    pub taa: bool,
    /// Bloom intensity, none when BLOOM is off.
    pub bloom: Option<f32>,
    pub contact_shadows: bool,
    pub motion_blur: bool,
    pub vignette: bool,
    /// BRIGHTNESS as an exposure offset in stops.
    pub exposure: f32,
}

impl CameraFx {
    /// TAA and contact shadows read the depth prepass.
    pub fn depth_prepass(&self) -> bool {
        self.taa || self.contact_shadows
    }

    /// TAA and motion blur read motion vectors.
    pub fn motion_prepass(&self) -> bool {
        self.taa || self.motion_blur
    }
}

/// BRIGHTNESS (−50..+50) as stops of exposure: ±50 is ± `brightness_ev` (settings.ron).
pub fn brightness_stops(brightness: f32, brightness_ev: f32) -> f32 {
    brightness.clamp(-50.0, 50.0) / 50.0 * brightness_ev
}

pub fn camera_fx(v: &VideoSettings, brightness_ev: f32) -> CameraFx {
    CameraFx {
        // The post-process AAs need MSAA off.
        msaa: if v.aa == Aa::Msaa4 { Msaa::Sample4 } else { Msaa::Off },
        fxaa: v.aa == Aa::Fxaa,
        smaa: v.aa == Aa::Smaa,
        taa: v.aa == Aa::Taa,
        bloom: match v.bloom {
            BloomLevel::Off => None,
            BloomLevel::Low => Some(BLOOM_LOW),
            BloomLevel::High => Some(BLOOM_HIGH),
        },
        contact_shadows: v.contact_shadows,
        motion_blur: v.motion_blur,
        vignette: v.vignette,
        exposure: brightness_stops(v.brightness, brightness_ev),
    }
}

/// Put [`CameraFx`] on the view camera: when it spawns, and when the settings change it.
fn apply_camera(
    settings: Res<Settings>,
    data: Res<SettingsData>,
    mut cameras: Query<(Entity, Option<&mut ColorGrading>), With<ViewCamera>>,
    added: Query<(), Added<ViewCamera>>,
    mut applied: Local<Option<CameraFx>>,
    mut commands: Commands,
) {
    let fx = camera_fx(&settings.video, data.brightness_ev);
    if *applied == Some(fx) && added.is_empty() {
        return;
    }
    // Prepasses are only taken away when these settings stop needing them (the camera may want them anyway).
    let before = applied.replace(fx);
    let drop_depth = before.is_some_and(|b| b.depth_prepass()) && !fx.depth_prepass();
    let drop_motion = before.is_some_and(|b| b.motion_prepass()) && !fx.motion_prepass();
    for (e, grading) in &mut cameras {
        match grading {
            Some(mut g) => g.global.exposure = fx.exposure,
            None => {
                let mut g = ColorGrading::default();
                g.global.exposure = fx.exposure;
                commands.entity(e).insert(g);
            }
        }
        let mut c = commands.entity(e);
        c.insert(fx.msaa);
        if fx.fxaa {
            c.insert(Fxaa::default());
        } else {
            c.remove::<Fxaa>();
        }
        if fx.smaa {
            c.insert(Smaa::default());
        } else {
            c.remove::<Smaa>();
        }
        if fx.taa {
            c.insert(TemporalAntiAliasing::default());
        } else {
            // The jitter TAA brought would otherwise keep shaking the view.
            c.remove::<(TemporalAntiAliasing, TemporalJitter, MipBias)>();
        }
        match fx.bloom {
            Some(intensity) => c.insert(Bloom { intensity, ..Bloom::NATURAL }),
            None => c.remove::<Bloom>(),
        };
        if fx.contact_shadows {
            c.insert(ContactShadows::default());
        } else {
            c.remove::<ContactShadows>();
        }
        if fx.motion_blur {
            c.insert(MotionBlur::default());
        } else {
            c.remove::<MotionBlur>();
        }
        if fx.vignette {
            c.insert(Vignette { intensity: VIGNETTE_INTENSITY, ..default() });
        } else {
            c.remove::<Vignette>();
        }
        if fx.depth_prepass() {
            c.insert(DepthPrepass);
        } else if drop_depth {
            c.remove::<DepthPrepass>();
        }
        if fx.motion_prepass() {
            c.insert(MotionVectorPrepass);
        } else if drop_motion {
            c.remove::<MotionVectorPrepass>();
        }
    }
}

/// SHADOWS: the shadow-map size and cascade count from settings.ron, per level LOW / MEDIUM / HIGH.
pub fn shadow_setup(level: Shadows, data: &SettingsData) -> (usize, usize) {
    let i = level.index();
    let size = data.shadows.map_size.get(i).copied().unwrap_or(2048).clamp(256, 8192).next_power_of_two();
    let cascades = data.shadows.cascades.get(i).copied().unwrap_or(1).clamp(1, 4);
    (size, cascades)
}

/// SHADOWS and the light half of CONTACT SHADOWS, on every directional light (the level's sun).
fn apply_shadows(
    settings: Res<Settings>,
    data: Res<SettingsData>,
    map: Option<Res<DirectionalLightShadowMap>>,
    mut lights: Query<(Entity, &mut DirectionalLight)>,
    mut applied: Local<Option<(Shadows, bool)>>,
    mut commands: Commands,
) {
    let want = (settings.video.shadows, settings.video.contact_shadows);
    let new_light = lights.iter_mut().any(|(_, l)| l.is_added());
    if *applied == Some(want) && !new_light {
        return;
    }
    *applied = Some(want);
    let (size, cascades) = shadow_setup(want.0, &data);
    if map.is_none_or(|m| m.size != size) {
        commands.insert_resource(DirectionalLightShadowMap { size });
    }
    for (e, mut light) in &mut lights {
        if light.contact_shadows_enabled != want.1 {
            light.contact_shadows_enabled = want.1;
        }
        commands.entity(e).insert(CascadeShadowConfigBuilder { num_cascades: cascades, ..default() }.build());
    }
}

// ---------------------------------------------------------------------------------------------- surface depth

/// The map's parallax depth (`map_materials`, `surface_depth.ron`) follows the quality PRESET: off on LOW, more
/// layers on HIGH / ULTRA. `VETF_SURFACE_DEPTH=off|low|medium|high|ultra` overrides it (before / after shots).
pub fn surface_depth_preset(preset: Preset, env: Option<&str>) -> Preset {
    match env.map(|s| s.trim().to_ascii_lowercase()).as_deref() {
        Some("off" | "low") => Preset::Low,
        Some("medium") => Preset::Medium,
        Some("high") => Preset::High,
        Some("ultra") => Preset::Ultra,
        _ => preset,
    }
}

fn apply_surface_depth(
    settings: Res<Settings>,
    mut level: ResMut<SurfaceDepthLevel>,
    mut env: Local<Option<Option<String>>>,
) {
    let env = env.get_or_insert_with(|| std::env::var("VETF_SURFACE_DEPTH").ok());
    level.set_if_neq(SurfaceDepthLevel(surface_depth_preset(settings.video.preset, env.as_deref())));
}

// ---------------------------------------------------------------------------------------------- overlay

#[derive(Component)]
struct OverlayRoot;
#[derive(Component)]
struct OverlayText;

/// The performance overlay's line: frames per second and frame time, plus the ping with '+ NETWORK' (the
/// host's own player has none: it plays on the host).
pub fn overlay_line(overlay: Overlay, fps: Option<f64>, frame_ms: Option<f64>, ping: Option<(u16, bool)>) -> String {
    if overlay == Overlay::Off {
        return String::new();
    }
    let mut parts = vec![
        fps.map_or("— FPS".into(), |f| format!("{f:.0} FPS")),
        frame_ms.map_or("— MS".into(), |ms| format!("{ms:.1} MS")),
    ];
    if overlay == Overlay::Network {
        parts.push(match ping {
            Some((_, true)) => "HOST".into(),
            Some((ms, false)) => format!("PING {ms} MS"),
            None => "OFFLINE".into(),
        });
    }
    parts.join("  ·  ")
}

fn spawn_overlay(mut commands: Commands, fonts: Res<UiFonts>) {
    commands.spawn((
        OverlayRoot,
        kit::panel_bg(
            Node { padding: UiRect::axes(px(8), px(3)), ..abs(Some(8.0), None, Some(8.0), None) },
            kit::BG0.with_alpha(0.6),
        ),
        // Over every screen.
        GlobalZIndex(1000),
        Visibility::Hidden,
        Pickable::IGNORE,
        children![(OverlayText, fonts.text("", Face::Display, 600, 13.0, kit::TEXT_MID, 0.08))],
    ));
}

#[allow(clippy::too_many_arguments)]
fn update_overlay(
    cli: Res<Cli>,
    settings: Res<Settings>,
    diagnostics: Res<DiagnosticsStore>,
    time: Res<Time>,
    me: Query<(&PlayerNet, &vetf_net::PlayerId), With<Controlled>>,
    mut root: Query<&mut Visibility, With<OverlayRoot>>,
    mut text: Query<&mut Text, With<OverlayText>>,
    mut next: Local<f32>,
) {
    let demo_hides = cli.automated() && cli.demo_ui.as_deref() != Some("overlay");
    let on = settings.video.overlay != Overlay::Off && !demo_hides;
    for mut v in &mut root {
        v.set_if_neq(if on { Visibility::Inherited } else { Visibility::Hidden });
    }
    if !on || time.elapsed_secs() < *next {
        return;
    }
    *next = time.elapsed_secs() + OVERLAY_EVERY_S;
    let fps = diagnostics.get(&FrameTimeDiagnosticsPlugin::FPS).and_then(|d| d.smoothed());
    let ms = diagnostics.get(&FrameTimeDiagnosticsPlugin::FRAME_TIME).and_then(|d| d.smoothed());
    // Player id 0 is the host's own player.
    let ping = me.iter().next().map(|(n, id)| (n.ping_ms, id.0 == 0));
    let line = overlay_line(settings.video.overlay, fps, ms, ping);
    for mut t in &mut text {
        if t.0 != line {
            t.0.clone_from(&line);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::{FrameLimit, embedded};

    fn mode(w: u32, h: u32, hz: u32) -> VideoMode {
        VideoMode { physical_size: UVec2::new(w, h), bit_depth: 32, refresh_rate_millihertz: hz * 1000 }
    }

    #[test]
    fn window_modes_follow_the_settings() {
        let modes = [mode(2560, 1440, 165), mode(2560, 1440, 60), mode(1920, 1080, 144)];
        let qhd = Resolution { width: 2560, height: 1440, refresh_mhz: 60_000 };
        assert_eq!(
            window_mode_for(WindowModeChoice::Fullscreen, Some(qhd), &modes),
            WindowMode::Fullscreen(MonitorSelection::Current, VideoModeSelection::Specific(modes[1]))
        );
        // A refresh rate this monitor lacks: the same size at its best rate.
        let odd = Resolution { refresh_mhz: 75_000, ..qhd };
        assert_eq!(matching_mode(odd, &modes), Some(modes[0]));
        // An unknown size, or native: the monitor's current mode.
        let tiny = Resolution { width: 800, height: 600, refresh_mhz: 60_000 };
        assert_eq!(
            window_mode_for(WindowModeChoice::Fullscreen, Some(tiny), &modes),
            WindowMode::Fullscreen(MonitorSelection::Current, VideoModeSelection::Current)
        );
        assert_eq!(
            window_mode_for(WindowModeChoice::Borderless, Some(qhd), &modes),
            WindowMode::BorderlessFullscreen(MonitorSelection::Current)
        );
        assert_eq!(window_mode_for(WindowModeChoice::Windowed, Some(qhd), &modes), WindowMode::Windowed);
        // Only a windowed window takes the resolution as its size; native keeps the size it has.
        assert_eq!(windowed_size(WindowModeChoice::Windowed, Some(qhd)), Some(UVec2::new(2560, 1440)));
        assert_eq!(windowed_size(WindowModeChoice::Windowed, None), None);
        assert_eq!(windowed_size(WindowModeChoice::Borderless, Some(qhd)), None);
        assert_eq!(present_mode(true), PresentMode::AutoVsync);
        assert_eq!(present_mode(false), PresentMode::AutoNoVsync);
    }

    #[test]
    fn the_frame_limiter_waits_out_the_budget() {
        let budget = Duration::from_secs_f64(1.0 / 144.0);
        assert_eq!(frame_wait(Duration::from_millis(2), budget), budget - Duration::from_millis(2));
        assert_eq!(frame_wait(Duration::from_millis(20), budget), Duration::ZERO, "a slow frame never waits");
        assert_eq!(FrameLimit::Fps(144).fps(Some(165)), Some(144));
        assert_eq!(FrameLimit::Monitor.fps(Some(165)), Some(165));
        assert_eq!(FrameLimit::Monitor.fps(None), None, "unknown refresh: no cap");
    }

    #[test]
    fn the_camera_follows_the_quality_values() {
        let d = embedded();
        let mut v = d.defaults.video.clone();
        let fx = camera_fx(&v, d.brightness_ev);
        // The defaults: SMAA, low bloom, contact shadows on, brightness 0.
        assert_eq!(fx.msaa, Msaa::Off);
        assert!(fx.smaa && !fx.fxaa && !fx.taa);
        assert_eq!(fx.bloom, Some(BLOOM_LOW));
        assert!(fx.contact_shadows && fx.depth_prepass() && !fx.motion_prepass());
        assert_eq!(fx.exposure, 0.0);
        v.aa = Aa::Msaa4;
        v.bloom = BloomLevel::Off;
        v.contact_shadows = false;
        let fx = camera_fx(&v, d.brightness_ev);
        assert_eq!(fx.msaa, Msaa::Sample4);
        assert!(!fx.smaa && fx.bloom.is_none() && !fx.depth_prepass());
        v.aa = Aa::Taa;
        let fx = camera_fx(&v, d.brightness_ev);
        assert!(fx.taa && fx.msaa == Msaa::Off && fx.depth_prepass() && fx.motion_prepass());
        v.aa = Aa::Off;
        v.motion_blur = true;
        let fx = camera_fx(&v, d.brightness_ev);
        assert!(fx.motion_prepass() && !fx.depth_prepass());
        // Brightness ±50 is ± brightness_ev stops.
        assert_eq!(brightness_stops(50.0, 1.0), 1.0);
        assert_eq!(brightness_stops(-25.0, 1.0), -0.5);
        assert_eq!(brightness_stops(-80.0, 2.0), -2.0, "clamped to the range");
    }

    #[test]
    fn shadow_levels_come_from_the_data() {
        let d = embedded();
        assert_eq!(shadow_setup(Shadows::Low, d), (1024, 1));
        assert_eq!(shadow_setup(Shadows::Medium, d), (2048, 2));
        assert_eq!(shadow_setup(Shadows::High, d), (4096, 4));
    }

    #[test]
    fn surface_depth_follows_the_preset() {
        assert_eq!(surface_depth_preset(Preset::Medium, None), Preset::Medium);
        assert_eq!(surface_depth_preset(Preset::Ultra, Some("off")), Preset::Low);
        assert_eq!(surface_depth_preset(Preset::Low, Some(" High ")), Preset::High);
        assert_eq!(surface_depth_preset(Preset::High, Some("nonsense")), Preset::High);
    }

    #[test]
    fn the_overlay_reads_fps_frame_time_and_ping() {
        assert_eq!(overlay_line(Overlay::Off, Some(144.0), Some(6.9), None), "");
        assert_eq!(overlay_line(Overlay::Fps, Some(143.6), Some(6.94), Some((40, false))), "144 FPS  ·  6.9 MS");
        assert_eq!(
            overlay_line(Overlay::Network, Some(60.0), Some(16.7), Some((40, false))),
            "60 FPS  ·  16.7 MS  ·  PING 40 MS"
        );
        assert_eq!(overlay_line(Overlay::Network, None, None, Some((0, true))), "— FPS  ·  — MS  ·  HOST");
        assert_eq!(overlay_line(Overlay::Network, Some(60.0), Some(16.7), None), "60 FPS  ·  16.7 MS  ·  OFFLINE");
    }
}
