//! SHARD/LINE (working title, codename "val etf"): a host-and-join extraction-shooter prototype.
//!
//! One binary does everything: the main menu can host (listen server: server + local player in one app)
//! or join a friend's game. See `game/README.md` for controls and command-line options.

// Bevy systems take their dependencies as parameters and filter with tuple types.
#![allow(clippy::too_many_arguments, clippy::type_complexity)]

mod client;
mod config;
mod demo_mode;
mod esc_menu;
mod hud;
mod invite;
mod iroh_transport;
mod loadout;
mod map_materials;
mod menu;
mod net;
mod radial;
mod render;
mod screens;
mod server;
mod settings;
mod shared;
mod ui_kit;
mod user_config;

use bevy::prelude::*;
use bevy::window::{PresentMode, WindowResolution};
use config::Cli;
use std::time::Duration;

#[derive(States, Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum AppState {
    #[default]
    MainMenu,
    /// Waiting for the netcode handshake (joining) or for our player to appear.
    Connecting,
    InGame,
}

fn main() -> AppExit {
    let cli = Cli::parse();
    let data = config::load_game_data();
    let tick = Duration::from_secs_f64(1.0 / data.net.tick_hz as f64);

    // Screenshot and demo runs ignore the desktop's display scale, so W x H is the image size in pixels
    // (on a 200 % Windows display a 1920x1080 request would otherwise make a 3840x2160 window).
    let mut resolution = WindowResolution::new(cli.width, cli.height);
    if cli.demo_mode() {
        resolution = resolution.with_scale_factor_override(1.0);
    }
    let mut app = App::new();
    app.add_plugins(
        DefaultPlugins
            .set(WindowPlugin {
                primary_window: Some(Window {
                    title: "SHARD/LINE (prototype)".into(),
                    resolution,
                    present_mode: PresentMode::AutoNoVsync,
                    // Scripted runs start hidden and are moved off the primary monitor first
                    // (`place_window`), so tests do not flash over the user's main screen.
                    visible: !(cli.automated() || cli.monitor.is_some()),
                    // A test run must not take the keyboard from whatever the user is typing in.
                    focused: !cli.ignores_desktop_input(),
                    ..default()
                }),
                ..default()
            })
            .set(AssetPlugin { file_path: "../../assets".into(), ..default() })
            .set(bevy::log::LogPlugin {
                filter: "info,wgpu=error,naga=warn,lightyear=warn,bevy_replicon=warn".into(),
                ..default()
            }),
    );
    // Both lightyear plugin groups, always: the same binary hosts or joins (same tick on both).
    app.add_plugins((
        lightyear::prelude::server::ServerPlugins { tick_duration: tick },
        lightyear::prelude::client::ClientPlugins { tick_duration: tick },
    ));
    app.add_plugins(vetf_net::ProtocolPlugin { input_redundancy: data.net.input_redundancy as u16 });
    app.insert_resource(config::Data(std::sync::Arc::new(data)));
    // The name saved from the main menu, unless --name overrides it for this run.
    let profile = user_config::PlayerProfile::load();
    let local_name = if cli.name_given { cli.name.clone() } else { profile.name.clone() };
    let mut session = net::Session::default();
    session.local_name = local_name;
    app.insert_resource(session);
    app.insert_resource(profile);
    if cli.ignores_desktop_input() {
        // The window opens without the keyboard focus; it must still run at full speed.
        app.insert_resource(bevy::winit::WinitSettings {
            focused_mode: bevy::winit::UpdateMode::Continuous,
            unfocused_mode: bevy::winit::UpdateMode::Continuous,
        });
    }
    app.insert_resource(cli);
    app.init_state::<AppState>();
    app.add_plugins((
        shared::SharedPlugin,
        net::NetPlugin,
        invite::InvitePlugin,
        server::ServerPlugin,
        client::ClientPlugin,
        render::RenderPlugin,
        hud::HudPlugin,
        radial::RadialPlugin,
        ui_kit::UiKitPlugin,
        menu::MenuPlugin,
        map_materials::MapMaterialsPlugin,
    ));
    // Hub screens over the menu or the match.
    app.add_plugins((
        screens::ScreensPlugin,
        demo_mode::DemoModePlugin,
        loadout::LoadoutScreenPlugin,
        settings::SettingsScreenPlugin,
        esc_menu::EscMenuPlugin,
    ));
    app.add_systems(Update, place_window);
    app.run()
}

/// Scripted runs (and `--monitor N`) start hidden. Once the monitors are known, move the window to the
/// requested monitor, or by default to the first one that is not primary, then show it. With a single
/// monitor it simply appears where the OS puts it.
fn place_window(
    cli: Res<Cli>,
    mut done: Local<bool>,
    mut frames: Local<u32>,
    mut windows: Query<&mut Window, With<bevy::window::PrimaryWindow>>,
    monitors: Query<(Entity, &bevy::window::Monitor, Has<bevy::window::PrimaryMonitor>)>,
) {
    if *done {
        return;
    }
    if !(cli.automated() || cli.monitor.is_some()) {
        *done = true;
        return;
    }
    let Ok(mut window) = windows.single_mut() else { return };
    *frames += 1;
    let mut list: Vec<_> = monitors.iter().map(|(e, m, primary)| (e, m.physical_position.x, primary)).collect();
    if list.is_empty() && *frames < 30 {
        return; // monitors are spawned by winit during the first frames
    }
    list.sort_by_key(|&(_, x, _)| x);
    let target = match cli.monitor {
        Some(n) => list.get(n).map(|&(e, _, _)| e),
        None => list.iter().find(|&&(_, _, primary)| !primary).map(|&(e, _, _)| e),
    };
    if let Some(monitor) = target {
        if let Ok((_, m, primary)) = monitors.get(monitor) {
            info!(
                "window on monitor at {:?} ({}x{}{})",
                m.physical_position,
                m.physical_width,
                m.physical_height,
                if primary { ", primary" } else { "" }
            );
        }
        window.position = bevy::window::WindowPosition::Centered(bevy::window::MonitorSelection::Entity(monitor));
    }
    window.visible = true;
    *done = true;
}
