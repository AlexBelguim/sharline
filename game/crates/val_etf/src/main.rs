//! SHARD/LINE (working title, codename "val etf"): a host-and-join extraction-shooter prototype.
//!
//! One binary does everything: the main menu can host (listen server: server + local player in one app)
//! or join a friend's game. See `game/README.md` for controls and command-line options.

// Bevy systems take their dependencies as parameters and filter with tuple types.
#![allow(clippy::too_many_arguments, clippy::type_complexity)]

mod client;
mod config;
mod hud;
mod menu;
mod net;
mod radial;
mod render;
mod server;
mod shared;
mod ui_kit;

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

    let mut app = App::new();
    app.add_plugins(
        DefaultPlugins
            .set(WindowPlugin {
                primary_window: Some(Window {
                    title: "SHARD/LINE (prototype)".into(),
                    resolution: WindowResolution::new(cli.width, cli.height),
                    present_mode: PresentMode::AutoNoVsync,
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
    app.insert_resource(net::Session { local_name: cli.name.clone(), ..Default::default() });
    app.insert_resource(cli);
    app.init_state::<AppState>();
    app.add_plugins((
        shared::SharedPlugin,
        net::NetPlugin,
        server::ServerPlugin,
        client::ClientPlugin,
        render::RenderPlugin,
        hud::HudPlugin,
        radial::RadialPlugin,
        ui_kit::UiKitPlugin,
        menu::MenuPlugin,
    ));
    app.run()
}
