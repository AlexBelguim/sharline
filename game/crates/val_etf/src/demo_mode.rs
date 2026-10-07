//! Screenshot and demo runs (`--screenshot`, `--demo-ui`; see [`Cli::demo_mode`]) are for agents and tests on
//! the user's own desktop, while the user keeps working:
//!
//! - The window renders at scale factor 1 (`main.rs`), so `--width 1920 --height 1080` is a 1920x1080 image
//!   on a HiDPI screen too, and [`keep_resolution`] puts that size back if the window is resized or moved to
//!   a monitor with another scale while the run lasts.
//! - The cursor is never grabbed or hidden (`screens::apply_cursor`).
//! - Unless `--allow-input` is given ([`Cli::ignores_desktop_input`]), the window opens without the keyboard
//!   focus and the desktop's mouse and keys are ignored: a click or key press of the user (the window may
//!   open under their pointer) presses nothing, and the pointer resting over the window lights no hover
//!   look in the screenshot. Scripted input (`--demo-ui`, `--esc-at`) does not go through them.

use crate::config::Cli;
use bevy::prelude::*;
use bevy::window::PrimaryWindow;

pub struct DemoModePlugin;

impl Plugin for DemoModePlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Startup, no_desktop_picking.run_if(ignores_desktop_input))
            .add_systems(
                PreUpdate,
                ignore_desktop_input
                    .after(bevy::input::InputSystems)
                    .before(bevy::ui::UiSystems::Focus)
                    .run_if(ignores_desktop_input),
            )
            .add_systems(Update, keep_resolution.run_if(|cli: Option<Res<Cli>>| cli.is_some_and(|c| c.demo_mode())));
    }
}

/// Run condition: a screenshot or demo run without `--allow-input`.
fn ignores_desktop_input(cli: Option<Res<Cli>>) -> bool {
    cli.is_some_and(|c| c.ignores_desktop_input())
}

/// No pointer events from the desktop's mouse (text fields and other picking users never see it).
fn no_desktop_picking(settings: Option<ResMut<bevy::picking::PickingSettings>>) {
    if let Some(mut s) = settings {
        s.is_input_enabled = false;
    }
}

/// Every frame, before the UI computes hover and press: no mouse buttons, no keys, no cursor position.
fn ignore_desktop_input(
    mut mouse: ResMut<ButtonInput<MouseButton>>,
    mut keys: ResMut<ButtonInput<KeyCode>>,
    mut windows: Query<&mut Window>,
) {
    mouse.reset_all();
    keys.reset_all();
    for mut w in &mut windows {
        if w.physical_cursor_position().is_some() {
            w.set_physical_cursor_position(None);
        }
    }
}

/// The requested size in physical pixels, whatever happens to the window during the run (not while it is
/// minimised).
fn keep_resolution(cli: Res<Cli>, mut windows: Query<&mut Window, With<PrimaryWindow>>) {
    for mut w in &mut windows {
        let (pw, ph) = (w.resolution.physical_width(), w.resolution.physical_height());
        if pw > 0 && ph > 0 && (pw, ph) != (cli.width, cli.height) {
            warn!("demo run: the window became {pw}x{ph}; back to {}x{}", cli.width, cli.height);
            w.resolution.set_scale_factor_override(Some(1.0));
            w.resolution.set_physical_resolution(cli.width, cli.height);
        }
    }
}
