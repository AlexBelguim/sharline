//! The in-match ESC menu (mockups 09 / 09b): resume, loadout, settings, controls, and the host / client
//! variants with their confirm modals (stop hosting, leave, restart). `Screen::Esc` over the match.

use bevy::prelude::*;

pub struct EscMenuPlugin;

impl Plugin for EscMenuPlugin {
    fn build(&self, _app: &mut App) {}
}
