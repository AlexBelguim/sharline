//! Overlay screens (Loadout, Settings, the ESC menu, confirm modals) as a stack, so a screen opened from
//! another returns to it ("return to opener"). The main menu and the match are the base (`AppState`);
//! overlays open over either.
//!
//! Each screen module watches the stack: it spawns its root when its screen becomes the top and despawns it
//! when its screen leaves the stack (see [`Screens::top`] and [`ScreenRoot`]). Esc pops the top screen.
//!
//! **Cursor and match input** are derived, never set by a screen: [`apply_cursor`] frees the pointer on the
//! menus, over any open screen and while the match is paused, and locks it in play (see [`cursor_free`]);
//! the match takes no look / move / fire input while a screen is open. Closing a screen therefore gives
//! back exactly what the screen below it (or the match) needs.

// The screen modules fill this in; until then parts of the API are unused.
#![allow(dead_code)]

use crate::AppState;
use crate::client::LocalControl;
use crate::config::Cli;
use bevy::prelude::*;
use bevy::window::{CursorGrabMode, CursorOptions, PrimaryWindow};

/// Settings tabs (the rail on the left of the Settings screen).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default)]
pub enum SettingsTab {
    #[default]
    Gameplay,
    MouseAim,
    Keybinds,
    Video,
    Audio,
    Hud,
}

/// What a confirm modal asks.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ConfirmKind {
    StopHosting,
    LeaveMatch,
    RestartMatch,
    QuitGame,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Screen {
    Loadout,
    Settings(SettingsTab),
    Esc,
    Confirm(ConfirmKind),
}

impl Screen {
    /// Same screen, ignoring parameters (a Settings screen on another tab is still Settings).
    pub fn same_kind(self, other: Screen) -> bool {
        std::mem::discriminant(&self) == std::mem::discriminant(&other)
    }
}

/// The overlay stack (empty = only the base screen).
#[derive(Resource, Debug, Default, Clone, PartialEq, Eq)]
pub struct Screens(Vec<Screen>);

impl Screens {
    pub fn top(&self) -> Option<Screen> {
        self.0.last().copied()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn contains(&self, s: Screen) -> bool {
        self.0.iter().any(|x| x.same_kind(s))
    }

    /// Open `s` over the current top (a screen of the same kind already open is brought back to the top).
    pub fn push(&mut self, s: Screen) {
        self.0.retain(|x| !x.same_kind(s));
        self.0.push(s);
    }

    pub fn pop(&mut self) -> Option<Screen> {
        self.0.pop()
    }

    /// Replace the top (e.g. switching Settings tabs).
    pub fn replace_top(&mut self, s: Screen) {
        self.0.pop();
        self.0.push(s);
    }

    pub fn clear(&mut self) {
        self.0.clear();
    }

    pub fn iter(&self) -> impl Iterator<Item = &Screen> {
        self.0.iter()
    }
}

/// On the root entity of an overlay screen.
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub struct ScreenRoot(pub Screen);

pub struct ScreensPlugin;

impl Plugin for ScreensPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<Screens>()
            .add_systems(Update, despawn_closed)
            .add_systems(PostUpdate, apply_cursor.run_if(resource_exists::<Cli>))
            .add_systems(OnEnter(crate::AppState::MainMenu), clear_stack)
            .add_systems(OnEnter(crate::AppState::InGame), clear_stack);
    }
}

fn clear_stack(mut screens: ResMut<Screens>) {
    screens.clear();
}

/// Roots whose screen left the stack go away (screens spawn their own roots when they become the top).
fn despawn_closed(screens: Res<Screens>, roots: Query<(Entity, &ScreenRoot)>, mut commands: Commands) {
    if !screens.is_changed() {
        return;
    }
    for (e, root) in &roots {
        if !screens.contains(root.0) {
            commands.entity(e).despawn();
        }
    }
}

/// The pointer is free (shown, not grabbed) on the menus, over any open screen and while the match is
/// paused, and locked while playing. Hands-off runs (screenshots, demos, the bot) never grab it.
pub fn cursor_free(in_match: bool, screen_open: bool, paused: bool, hands_off: bool) -> bool {
    hands_off || !in_match || screen_open || paused
}

/// The one system that sets [`CursorOptions`]: screens and the match never touch the cursor themselves, so
/// whatever closes, the state below it comes back on its own.
fn apply_cursor(
    state: Res<State<AppState>>,
    screens: Res<Screens>,
    control: Option<Res<LocalControl>>,
    cli: Res<Cli>,
    mut cursor: Query<&mut CursorOptions, With<PrimaryWindow>>,
) {
    let free = cursor_free(
        *state.get() == AppState::InGame,
        !screens.is_empty(),
        control.is_some_and(|c| c.paused),
        cli.hands_off(),
    );
    let (visible, grab) = if free { (true, CursorGrabMode::None) } else { (false, CursorGrabMode::Locked) };
    for mut c in &mut cursor {
        if c.visible != visible || c.grab_mode != grab {
            c.visible = visible;
            c.grab_mode = grab;
        }
    }
}

/// Run condition: `s` (of its kind) is the top screen.
pub fn screen_on_top(s: Screen) -> impl Fn(Res<Screens>) -> bool + Clone {
    move |screens: Res<Screens>| screens.top().is_some_and(|t| t.same_kind(s))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_cursor_is_only_locked_in_play() {
        assert!(!cursor_free(true, false, false, false), "playing: locked");
        assert!(cursor_free(true, true, false, false), "a screen over the match frees it");
        assert!(cursor_free(true, false, true, false), "paused");
        assert!(cursor_free(false, false, false, false), "menus");
        assert!(cursor_free(true, false, false, true), "screenshot, demo and bot runs never grab it");
    }

    #[test]
    fn the_stack_returns_to_the_opener() {
        let mut s = Screens::default();
        s.push(Screen::Esc);
        s.push(Screen::Settings(SettingsTab::Keybinds));
        assert_eq!(s.top(), Some(Screen::Settings(SettingsTab::Keybinds)));
        s.replace_top(Screen::Settings(SettingsTab::Video));
        assert!(s.contains(Screen::Settings(SettingsTab::Gameplay)), "any tab counts as Settings");
        assert_eq!(s.pop(), Some(Screen::Settings(SettingsTab::Video)));
        assert_eq!(s.top(), Some(Screen::Esc));
        s.push(Screen::Loadout);
        s.push(Screen::Esc);
        assert_eq!(s.iter().copied().collect::<Vec<_>>(), vec![Screen::Loadout, Screen::Esc], "one of each kind");
    }
}
