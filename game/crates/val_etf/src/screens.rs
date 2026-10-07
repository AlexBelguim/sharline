//! Overlay screens (Loadout, Settings, the ESC menu, confirm modals) as a stack, so a screen opened from
//! another returns to it ("return to opener"). The main menu and the match are the base (`AppState`);
//! overlays open over either.
//!
//! Each screen module watches the stack: it spawns its root when its screen becomes the top and despawns it
//! when its screen leaves the stack (see [`Screens::top`] and [`ScreenRoot`]).
//!
//! **Esc** means "back one level" and goes to exactly one place per press, in the order of [`EscSystems`]:
//! the top screen's innermost layer (a listening key cap, an edited field, a popover, a dropdown), then that
//! screen's BACK (by default [`back_on_esc`] pops it), and only with no screen open the base under the stack
//! (the main menu's flyout or name edit, the match's ring menus, then its pause / ESC menu). Handlers never
//! read `KeyCode::Escape`; they call [`EscPress::take`] from a system in their set.
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
            .init_resource::<EscPress>()
            .configure_sets(
                Update,
                (EscSystems::Read, EscSystems::Top, EscSystems::Back, EscSystems::Base).chain(),
            )
            .add_systems(Update, (read_esc.in_set(EscSystems::Read), back_on_esc.in_set(EscSystems::Back)))
            .add_systems(Update, scripted_esc.after(read_esc).in_set(EscSystems::Read).run_if(resource_exists::<Cli>))
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

// ---------------------------------------------------------------------------------------------- Esc

/// Who gets Esc, in this order, every frame (all in `Update`; the sets are chained). Exactly one handler
/// acts on a press: it calls [`EscPress::take`] and acts only when that returns true.
#[derive(SystemSet, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum EscSystems {
    /// [`read_esc`]: this frame's Esc press goes into [`EscPress`].
    Read,
    /// The top screen's own handlers, gated with [`screen_on_top`]: its innermost open layer first (a
    /// listening key cap, an edited text field, a popover, a dropdown), then its BACK when leaving needs
    /// work (saving, a confirm). A screen with nothing to close leaves Esc for [`EscSystems::Back`].
    Top,
    /// [`back_on_esc`]: an Esc the top screen left pops it, so nothing under the stack ever sees it.
    Back,
    /// The base under the stack, which only gets Esc while no screen is open: the main menu (name edit,
    /// flyout back to the nav) and the match (a ring menu first, then the pause / ESC menu).
    Base,
}

/// This frame's Esc press, until a handler takes it (see [`EscSystems`]).
#[derive(Resource, Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct EscPress {
    pending: bool,
}

impl EscPress {
    /// True once per press: the caller handles this Esc and nobody after it sees it.
    pub fn take(&mut self) -> bool {
        std::mem::take(&mut self.pending)
    }

    /// An Esc press is waiting (look without taking it).
    pub fn pending(&self) -> bool {
        self.pending
    }

    /// Press Esc from code (demos, tests).
    pub fn press(&mut self) {
        self.pending = true;
    }
}

/// The key, once per frame (a press nobody took does not carry over to the next frame).
fn read_esc(keys: Res<ButtonInput<KeyCode>>, mut esc: ResMut<EscPress>) {
    esc.set_if_neq(EscPress { pending: keys.just_pressed(KeyCode::Escape) });
}

/// `--esc-at S,S,..`: press Esc at those seconds after start-up, for automated tests of this routing.
fn scripted_esc(cli: Res<Cli>, time: Res<Time>, mut esc: ResMut<EscPress>, mut next: Local<usize>) {
    if cli.esc_at.get(*next).is_some_and(|t| time.elapsed_secs() >= *t) {
        *next += 1;
        info!("--esc-at: Esc at {:.1} s", time.elapsed_secs());
        esc.press();
    }
}

/// The default BACK: an Esc the top screen did not take closes it, returning to the screen below (or the
/// base). Screens that must do something on the way out take Esc in [`EscSystems::Top`] instead.
pub fn back_on_esc(mut esc: ResMut<EscPress>, mut screens: ResMut<Screens>) {
    if !screens.is_empty() && esc.take() {
        screens.pop();
    }
}

// ---------------------------------------------------------------------------------------------- cursor

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

    /// A test app with the stack, a top-screen handler that closes a popover, and a base handler.
    #[derive(Resource, Default)]
    struct Probe {
        popover_open: bool,
        base_esc: u32,
    }

    fn esc_app() -> App {
        let mut app = App::new();
        app.add_plugins(bevy::state::app::StatesPlugin)
            .init_state::<AppState>()
            .init_resource::<ButtonInput<KeyCode>>()
            .init_resource::<Probe>()
            .add_plugins(ScreensPlugin)
            .add_systems(
                Update,
                (|mut esc: ResMut<EscPress>, mut probe: ResMut<Probe>| {
                    if probe.popover_open && esc.take() {
                        probe.popover_open = false;
                    }
                })
                .in_set(EscSystems::Top)
                .run_if(screen_on_top(Screen::Loadout)),
            )
            .add_systems(
                Update,
                (|mut esc: ResMut<EscPress>, mut probe: ResMut<Probe>| {
                    if esc.take() {
                        probe.base_esc += 1;
                    }
                })
                .in_set(EscSystems::Base),
            );
        // The first update enters MainMenu, which clears the stack.
        app.update();
        app
    }

    fn press_esc(app: &mut App) {
        app.world_mut().resource_mut::<ButtonInput<KeyCode>>().press(KeyCode::Escape);
        app.update();
        let mut keys = app.world_mut().resource_mut::<ButtonInput<KeyCode>>();
        keys.release(KeyCode::Escape);
        keys.clear();
    }

    #[test]
    fn esc_goes_to_the_top_screen_only_then_back_down_the_stack() {
        let mut app = esc_app();
        app.world_mut().resource_mut::<Probe>().popover_open = true;
        app.world_mut().resource_mut::<Screens>().push(Screen::Esc);
        app.world_mut().resource_mut::<Screens>().push(Screen::Loadout);
        let stack = |app: &App| app.world().resource::<Screens>().iter().copied().collect::<Vec<_>>();
        let base = |app: &App| app.world().resource::<Probe>().base_esc;

        press_esc(&mut app);
        assert!(!app.world().resource::<Probe>().popover_open, "the top screen's popover closes first");
        assert_eq!(stack(&app), vec![Screen::Esc, Screen::Loadout], "and only the popover");
        press_esc(&mut app);
        assert_eq!(stack(&app), vec![Screen::Esc], "then BACK returns to the opener");
        press_esc(&mut app);
        assert!(stack(&app).is_empty(), "the ESC menu's Esc is RESUME");
        assert_eq!(base(&app), 0, "the base never saw an Esc while a screen was open");
        press_esc(&mut app);
        assert_eq!(base(&app), 1, "with no screen open the base gets it");
        app.update();
        assert_eq!(base(&app), 1, "a press is used once");
    }

    /// Every Esc goes through [`EscPress`]: a module reading the key itself would run in no defined order
    /// with the screens (the bug this routing fixes).
    #[test]
    fn nothing_reads_the_esc_key_directly() {
        fn walk(dir: &std::path::Path, out: &mut Vec<std::path::PathBuf>) {
            for e in std::fs::read_dir(dir).unwrap().flatten() {
                let p = e.path();
                if p.is_dir() {
                    walk(&p, out);
                } else if p.extension().is_some_and(|x| x == "rs") {
                    out.push(p);
                }
            }
        }
        let src = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
        let mut files = vec![];
        walk(&src, &mut files);
        // screens.rs reads the key; bindings.rs only checks in a test that Esc cannot be bound.
        let allowed = ["screens.rs", "bindings.rs"];
        let key = ["KeyCode::", "Escape"].concat();
        let offenders: Vec<_> = files
            .iter()
            .filter(|p| !allowed.iter().any(|a| p.ends_with(a)))
            .filter(|p| std::fs::read_to_string(p).unwrap().contains(&key))
            .collect();
        assert!(offenders.is_empty(), "use screens::EscPress instead of the Esc key: {offenders:?}");
    }

    #[test]
    fn esc_press_is_taken_once() {
        let mut esc = EscPress::default();
        assert!(!esc.take());
        esc.press();
        assert!(esc.pending());
        assert!(esc.take());
        assert!(!esc.take());
    }

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
