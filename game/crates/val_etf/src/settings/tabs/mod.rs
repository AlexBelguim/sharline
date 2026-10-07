//! Each Settings tab's columns, built into the pane (a flex row, gap 24) from the control kit
//! (`super::controls`). Every tab but KEYBINDS has two columns of equal width (`col`); KEYBINDS is
//! `super::keybinds::build`.

mod audio;
mod gameplay;
mod hud;
mod mouse_aim;
mod video;

use super::controls::Kit;
use super::model::Tab;
use bevy::prelude::*;

pub fn build(p: &mut ChildSpawnerCommands, k: &Kit, tab: Tab) {
    match tab {
        Tab::Gameplay => gameplay::build(p, k),
        Tab::MouseAim => mouse_aim::build(p, k),
        Tab::Keybinds => super::keybinds::build(p, k),
        Tab::Video => video::build(p, k),
        Tab::Audio => audio::build(p, k),
        Tab::Hud => hud::build(p, k),
    }
}

/// One of a tab's two columns (flex 1, a column with a 14 px gap, min width 0).
pub fn col(p: &mut ChildSpawnerCommands, f: impl FnOnce(&mut ChildSpawnerCommands)) {
    p.spawn(Node {
        flex_grow: 1.0,
        flex_basis: px(0),
        min_width: px(0),
        flex_direction: FlexDirection::Column,
        row_gap: px(14),
        ..default()
    })
    .with_children(f);
}

/// A placeholder for a tab that is not built yet.
pub fn todo(p: &mut ChildSpawnerCommands, k: &Kit, title: &str) {
    col(p, |c| {
        super::controls::card(c, 1.0, 14.0, Node::default(), |card| {
            super::controls::h2(card, k, title, Some(("being built", None)), 0.0);
        });
    });
    col(p, |_| {});
}
