//! The Settings hub screen (mockups 08-08e): a tab rail (gameplay, mouse & aim, keybinds, video, audio,
//! HUD & accessibility) over one shared frame. Opens over the main menu or the match
//! (`Screen::Settings(tab)`); values persist in the user's config folder.

use bevy::prelude::*;

pub struct SettingsScreenPlugin;

impl Plugin for SettingsScreenPlugin {
    fn build(&self, _app: &mut App) {}
}
