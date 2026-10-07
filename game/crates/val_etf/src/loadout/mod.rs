//! The Loadout hub screen (mockups 05 / 05b): agent, weapon, attachments, the six ordered magazines with
//! their ammo, halo armor per arc, and the gear-budget result. Opens over the main menu or the match
//! (`Screen::Loadout`); changes apply at the next spawn.

use bevy::prelude::*;

pub struct LoadoutScreenPlugin;

impl Plugin for LoadoutScreenPlugin {
    fn build(&self, _app: &mut App) {}
}
