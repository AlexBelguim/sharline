//! The Loadout hub screen (mockups 05 / 05b): agent, weapon, attachments, the six ordered magazines with
//! their ammo, the custom halo (a core and a tier per arc) and the gear-budget result. Opens over the main
//! menu or the match (`Screen::Loadout`); in a match, CONFIRM sends a `LoadoutUpdate` that the host
//! applies at the next spawn.
//!
//! Contract with the other screens:
//! - [`ActiveLoadout`] is what this player asks the host for (sent in `Hello`, applied at each spawn).
//!   CONFIRM updates it and saves it into the active preset (`loadouts.ron`).
//! - [`summary`] formats it for the main menu's player card and the ESC menu.
//! - Open the screen with `Screens::push(Screen::Loadout)`; Esc or BACK pops it.

mod focus;
mod halo;
mod model;
mod popover;
mod presets;
mod text;
mod ui_data;
mod view;

pub use model::Draft;
pub use presets::LoadoutsFile;
#[allow(unused_imports)] // for the other hub screens
pub use text::{ammo_short, halo_name, tier_label};

use crate::AppState;
use crate::config::{Cli, Data};
use crate::net::Session;
use crate::screens::{Screen, ScreenRoot, Screens, screen_on_top};
use crate::ui_kit::*;
use bevy::input_focus::{FocusCause, InputFocus};
use bevy::prelude::*;
use bevy::text::{EditableText, TextEdit};
use bevy::ui::RelativeCursorPosition;
use bevy::window::{CursorGrabMode, CursorOptions, PrimaryWindow};
use halo::HaloImages;
use lightyear::prelude::*;
use std::hash::{Hash, Hasher};
use ui_data::LoadoutUiData;
use vetf_net::{LoadoutChoice, LoadoutUpdate, MatchMode, MatchState, ReliableChannel};
use vetf_sim::GameData;
use vetf_sim::ZoneTable;
use vetf_sim::data::{AmmoKind, AttachmentCategory, Core, WeightClass};
use vetf_sim::gear::gear_budget;
use vetf_sim::{Zone, gear};

pub struct LoadoutScreenPlugin;

impl Plugin for LoadoutScreenPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(LoadoutUiData::load())
            .init_resource::<LoadoutUi>()
            .add_systems(Startup, (init_active_loadout, load_halo_images))
            .add_systems(Update, (demo_open, open_screen, free_cursor_in_match).chain())
            .add_systems(
                Update,
                (
                    focus::keyboard_focus,
                    presses,
                    mag_release,
                    right_click,
                    keys,
                    save_as_field,
                    hover_rows,
                    tick_flash,
                    view::refresh,
                    view::move_ghost,
                    view::focus_rows,
                    view::hotspot_hover,
                    focus::place_ring,
                )
                    .chain()
                    .after(open_screen)
                    .run_if(screen_on_top(Screen::Loadout).and_then(resource_exists::<LoadoutEdit>)),
            )
            .add_systems(Update, halo::orbit_cells);
    }
}

// ---------------------------------------------------------------------------------------------- contract

/// The loadout this player asks for (the active preset, or the command line's overrides).
#[derive(Resource, Debug, Clone, PartialEq)]
pub struct ActiveLoadout(pub LoadoutChoice);

fn init_active_loadout(mut commands: Commands, cli: Res<Cli>, data: Res<Data>) {
    let choice = if cli.has_loadout_overrides() {
        crate::config::loadout_choice(&cli, &data)
    } else {
        preset_choice(&LoadoutsFile::load(&data, crate::config::DEFAULT_AGENT), &data, &cli)
    };
    commands.insert_resource(ActiveLoadout(choice));
}

/// The active preset, cleaned up like the screen would (unknown parts dropped, caps applied); a preset the
/// host would refuse in team deathmatch (saved over budget with + SAVE AS) gives the default loadout.
fn preset_choice(file: &LoadoutsFile, data: &GameData, cli: &Cli) -> LoadoutChoice {
    let preset = &file.presets[file.active.min(file.presets.len().saturating_sub(1))].loadout;
    let draft = Draft::from_choice(preset, &file.attachments, data);
    if draft.problems(data, gear_budget(data, MatchMode::Tdm)).is_empty() {
        draft.choice()
    } else {
        warn!(
            "loadout preset {} cannot be used in team deathmatch; using the default loadout",
            file.label(file.active)
        );
        crate::config::loadout_choice(
            &Cli { weapon: None, ammo: None, mags: None, armor: None, attach: None, ..cli.clone() },
            data,
        )
    }
}

fn load_halo_images(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(HaloImages::load(&assets));
}

/// A loadout as the hub screens show it.
#[allow(dead_code)] // for the main menu's player card and the ESC menu
#[derive(Debug, Clone, PartialEq)]
pub struct LoadoutSummary {
    pub weapon_name: String,
    pub attachments: Vec<String>,
    /// (slot 1-based, short ammo label, ammo type) in slot order. Never round counts.
    pub mags: Vec<(usize, String, AmmoKind)>,
    /// The halo in a few words: `T2 MENDER`, `T1–T3 BULWARK`, `NO HALO`.
    pub armor_name: String,
    pub core: Option<Core>,
    /// Tier per halo arc (loadout caps applied).
    pub tiers: ZoneTable<u8>,
    pub weight: WeightClass,
    /// Team-deathmatch gear cost (halo + every magazine) against the budget.
    pub gear_cost: u32,
    pub gear_budget: u32,
    /// The agent's display name (cosmetic for now).
    pub agent_name: String,
}

/// Summarise a loadout choice (unknown ids fall back to what the host would use).
#[allow(dead_code)] // for the main menu's player card and the ESC menu
pub fn summary(choice: &LoadoutChoice, data: &GameData) -> LoadoutSummary {
    let weapon = data.weapon(&choice.weapon).or_else(|| data.weapon(&data.rules.default_loadout.primary));
    let mags: Vec<(usize, String, AmmoKind)> = choice
        .mags
        .iter()
        .enumerate()
        .filter_map(|(i, m)| {
            let a = data.ammo_for(weapon?, *m)?;
            Some((i + 1, a.label, m.kind))
        })
        .collect();
    let halo = choice.halo.capped(data.armor.loadout_tier_caps);
    let armor = data.armor.resolve_halo(&halo);
    let cost = weapon.map_or(0, |w| gear::gear_cost(data, w, &halo, &choice.mags).total());
    static AGENTS: std::sync::OnceLock<LoadoutUiData> = std::sync::OnceLock::new();
    let agents = AGENTS.get_or_init(LoadoutUiData::load);
    LoadoutSummary {
        weapon_name: weapon.map_or("?".into(), |w| w.name.clone()),
        attachments: choice
            .attachments
            .iter()
            .map(|a| data.attachment(a).map_or(a.clone(), |s| s.display_name().to_string()))
            .collect(),
        mags,
        armor_name: halo_name(&halo),
        core: armor.core,
        tiers: armor.tiers,
        weight: armor.weight_class,
        gear_cost: cost,
        gear_budget: data.rules.tdm.gear_budget,
        agent_name: agents.agent(&choice.agent).map_or(choice.agent.to_uppercase(), |(_, a)| a.name.clone()),
    }
}

// ---------------------------------------------------------------------------------------------- state

/// The edit in progress while the screen is open (dropped when it closes: BACK discards it).
#[derive(Resource, Debug, Clone)]
pub struct LoadoutEdit {
    pub draft: Draft,
    pub file: LoadoutsFile,
}

/// What the attachment popover shows.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Pop {
    Slot(AttachmentCategory),
    /// The ammo picker of magazine slot n (0-based; the first empty slot adds a magazine).
    Mag(usize),
}

/// A magazine card being dragged onto another.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Drag {
    pub from: usize,
    /// Cursor at the press (UI px) and the card's offset under it.
    pub start: Vec2,
    pub grab: Vec2,
    pub active: bool,
    pub over: Option<usize>,
    /// The press was on the card whose picker was open (a click then closes it).
    pub was_open: bool,
}

/// Screen-local UI state.
#[derive(Resource, Debug, Clone, PartialEq)]
pub struct LoadoutUi {
    pub pop: Option<Pop>,
    /// The arc the TIER row edits.
    pub arc: Zone,
    /// Popover row under the mouse / picked with the arrow keys.
    pub hover_row: Option<usize>,
    pub focus_row: Option<usize>,
    pub drag: Option<Drag>,
    /// Seconds left of each magazine's warning flash.
    pub flash: [f32; 6],
    /// The + SAVE AS chip is a text field.
    pub save_as: bool,
    /// Keyboard focus (Q / E / arrows), shown with the focus ring while `keyboard` is on.
    pub focus: Option<Act>,
    pub keyboard: bool,
    /// Enter on the focused item: handled like a click on the next pass.
    pub activate: Option<Act>,
}

impl Default for LoadoutUi {
    fn default() -> Self {
        Self {
            pop: None,
            arc: Zone::Torso,
            hover_row: None,
            focus_row: None,
            drag: None,
            flash: [0.0; 6],
            save_as: false,
            focus: None,
            keyboard: false,
            activate: None,
        }
    }
}

impl LoadoutUi {
    fn close_pop(&mut self) {
        self.pop = None;
        self.hover_row = None;
        self.focus_row = None;
    }

    fn open_pop(&mut self, p: Pop) {
        self.pop = Some(p);
        self.hover_row = None;
        self.focus_row = None;
    }
}

/// Where the screen is shown: from the menu (TDM budget as a default) or over a match (its mode decides).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ScreenCtx {
    pub in_match: bool,
    pub budget: Option<u32>,
    /// The micro after the budget: HOST OPTION, TDM DEFAULT, GUN RANGE.
    pub note: &'static str,
}

impl ScreenCtx {
    fn new(data: &GameData, state: &AppState, matches: &Query<&MatchState>) -> Self {
        let in_match = matches!(state, AppState::InGame | AppState::Connecting);
        let mode = matches.iter().next().map(|m| m.mode);
        match (in_match, mode) {
            (true, Some(MatchMode::Range)) => {
                Self { in_match, budget: gear_budget(data, MatchMode::Range), note: "GUN RANGE" }
            }
            (true, _) => Self { in_match, budget: gear_budget(data, MatchMode::Tdm), note: "HOST OPTION" },
            (false, _) => Self { in_match, budget: gear_budget(data, MatchMode::Tdm), note: "TDM DEFAULT" },
        }
    }
}

/// Clickable things on the screen.
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Act {
    Preset(usize),
    SaveAs,
    Back,
    Confirm,
    Agent(usize),
    Weapon(usize),
    Slot(AttachmentCategory),
    Mag(usize),
    Core(Core),
    Tier(u8),
    Zone(Zone),
    ZoneCheck(Zone),
    Row(usize),
}

/// The popover panel (clicks inside it never close it).
#[derive(Component)]
pub struct PopPanel;

/// The + SAVE AS text field.
#[derive(Component)]
pub struct SaveAsField;

fn hash_of(v: &impl std::fmt::Debug) -> u64 {
    let mut h = std::collections::hash_map::DefaultHasher::new();
    format!("{v:?}").hash(&mut h);
    h.finish()
}

// ---------------------------------------------------------------------------------------------- lifecycle

/// `--demo-ui loadout | loadout-ammo | loadout-attach`: open the screen over the main menu (and a popover).
fn demo_open(
    cli: Res<Cli>,
    state: Res<State<AppState>>,
    mut screens: ResMut<Screens>,
    mut ui: ResMut<LoadoutUi>,
    edit: Option<Res<LoadoutEdit>>,
    mut step: Local<u8>,
) {
    let Some(demo) = cli.demo_ui.as_deref() else { return };
    // On the main menu, or over the match with --host.
    let base = if cli.host.is_some() { AppState::InGame } else { AppState::MainMenu };
    if !demo.starts_with("loadout") || *state.get() != base {
        return;
    }
    match *step {
        0 => {
            screens.push(Screen::Loadout);
            *step = 1;
        }
        1 if edit.is_some() => {
            match demo {
                "loadout-ammo" => ui.open_pop(Pop::Mag(0)),
                "loadout-attach" => ui.open_pop(Pop::Slot(AttachmentCategory::Optic)),
                _ => {}
            }
            *step = 2;
        }
        _ => {}
    }
}

/// Spawn the page when the screen comes to the top; drop the edit when it leaves the stack.
fn open_screen(
    mut commands: Commands,
    screens: Res<Screens>,
    roots: Query<(Entity, &ScreenRoot)>,
    edit: Option<Res<LoadoutEdit>>,
    active: Res<ActiveLoadout>,
    data: Res<Data>,
    mut ui: ResMut<LoadoutUi>,
) {
    let open = screens.contains(Screen::Loadout);
    let root = roots.iter().find(|(_, r)| r.0.same_kind(Screen::Loadout)).map(|(e, _)| e);
    if !open {
        if edit.is_some() {
            commands.remove_resource::<LoadoutEdit>();
            *ui = LoadoutUi::default();
        }
        return;
    }
    if root.is_some() || !screens.top().is_some_and(|t| t.same_kind(Screen::Loadout)) {
        return;
    }
    let mut file = LoadoutsFile::load(&data, crate::config::DEFAULT_AGENT);
    let draft = Draft::from_choice(&active.0, &file.attachments, &data);
    // The edit starts from what the player spawns with; it belongs to the preset it equals (else the last one).
    if let Some(i) = file.presets.iter().position(|p| p.loadout == draft.choice()) {
        file.active = i;
    }
    commands.insert_resource(LoadoutEdit { draft, file });
    *ui = LoadoutUi::default();
    let depth = screens.iter().position(|s| s.same_kind(Screen::Loadout)).unwrap_or(0) as i32;
    view::spawn_root(&mut commands, 100 + depth * 10);
}

/// Over a running match the cursor is free and the player's input is off while the screen is open. When the
/// screen paused the game itself and closes with nothing under it, play resumes (a screen under it, such as
/// the ESC menu, keeps its own pause).
fn free_cursor_in_match(
    screens: Res<Screens>,
    state: Res<State<AppState>>,
    mut cursor: Query<&mut CursorOptions, With<PrimaryWindow>>,
    mut control: Option<ResMut<crate::client::LocalControl>>,
    mut paused_here: Local<bool>,
) {
    let on_top = screens.top().is_some_and(|t| t.same_kind(Screen::Loadout));
    if *state.get() != AppState::InGame {
        *paused_here = false;
        return;
    }
    let Some(control) = control.as_mut() else { return };
    if !on_top {
        if *paused_here && !screens.contains(Screen::Loadout) {
            *paused_here = false;
            if screens.is_empty() && control.paused {
                control.paused = false;
                for mut c in &mut cursor {
                    c.visible = false;
                    c.grab_mode = CursorGrabMode::Locked;
                }
            }
        }
        return;
    }
    for mut c in &mut cursor {
        if !c.visible || c.grab_mode != CursorGrabMode::None {
            c.visible = true;
            c.grab_mode = CursorGrabMode::None;
        }
    }
    if !control.paused {
        control.paused = true;
        *paused_here = true;
    }
}

// ---------------------------------------------------------------------------------------------- actions

fn load_preset(edit: &mut LoadoutEdit, ui: &mut LoadoutUi, i: usize, data: &GameData) {
    let Some(p) = edit.file.presets.get(i) else { return };
    edit.draft = Draft::from_choice(&p.loadout, &edit.file.attachments, data);
    edit.file.active = i;
    ui.close_pop();
    ui.flash = [0.0; 6];
}

#[allow(clippy::too_many_arguments)]
fn confirm(
    edit: &mut LoadoutEdit,
    ctx: &ScreenCtx,
    data: &GameData,
    active: &mut ActiveLoadout,
    screens: &mut Screens,
    session: &Session,
    senders: &mut Query<&mut MessageSender<LoadoutUpdate>, With<Client>>,
) {
    if !edit.draft.problems(data, ctx.budget).is_empty() {
        return;
    }
    let choice = edit.draft.choice();
    let i = edit.file.active;
    edit.file.presets[i].loadout = choice.clone();
    edit.file.attachments = edit.draft.parts.clone();
    if let Err(e) = edit.file.save() {
        warn!("loadout presets not saved: {e}");
    }
    active.0 = choice.clone();
    if ctx.in_match
        && let Some(client) = session.client
        && let Ok(mut sender) = senders.get_mut(client)
    {
        sender.send::<ReliableChannel>(LoadoutUpdate { loadout: choice });
        info!("loadout sent; it applies at the next spawn");
    }
    screens.pop();
}

/// Mouse presses on everything but the magazine cards (those act on release, so they can be dragged).
#[allow(clippy::too_many_arguments)]
fn presses(
    q: Query<(&Interaction, &Act, Has<Disabled>), Changed<Interaction>>,
    mouse: Res<ButtonInput<MouseButton>>,
    keys: Res<ButtonInput<KeyCode>>,
    panels: Query<&RelativeCursorPosition, With<PopPanel>>,
    mut edit: ResMut<LoadoutEdit>,
    mut ui: ResMut<LoadoutUi>,
    (data, ui_data, state, matches): (Res<Data>, Res<LoadoutUiData>, Res<State<AppState>>, Query<&MatchState>),
    (mut active, mut screens, session, mut senders): (
        ResMut<ActiveLoadout>,
        ResMut<Screens>,
        Res<Session>,
        Query<&mut MessageSender<LoadoutUpdate>, With<Client>>,
    ),
    (windows, scale, cards): (
        Query<&Window, With<PrimaryWindow>>,
        Res<UiScale>,
        Query<(&Act, &ComputedNode, &UiGlobalTransform)>,
    ),
) {
    let ctx = ScreenCtx::new(&data, state.get(), &matches);
    let pressed: Option<(Act, bool)> = q.iter().find(|(i, ..)| **i == Interaction::Pressed).map(|(_, a, d)| (*a, d));
    // Enter on the keyboard focus acts like a click (magazines open their picker: no drag).
    let from_keys = ui.activate.take();
    if let Some(Act::Mag(i)) = from_keys {
        if ui.pop == Some(Pop::Mag(i)) {
            ui.close_pop();
        } else if i <= edit.draft.mags.len() {
            ui.open_pop(Pop::Mag(i));
        }
        return;
    }
    let pressed = pressed.or(from_keys.map(|a| (a, false)));
    // A press outside the popover closes it (the cards that open popovers decide for themselves).
    if mouse.just_pressed(MouseButton::Left) && ui.pop.is_some() {
        let inside = panels.iter().any(|p| p.cursor_over());
        let opener = matches!(pressed, Some((Act::Slot(_) | Act::Mag(_) | Act::Row(_), _)));
        if !inside && !opener {
            ui.close_pop();
        }
    }
    if mouse.just_pressed(MouseButton::Left) && ui.save_as && !matches!(pressed, Some((Act::SaveAs, _))) {
        ui.save_as = false;
    }
    let Some((act, disabled)) = pressed else { return };
    if disabled {
        return;
    }
    let caps = data.armor.loadout_tier_caps;
    let shift = keys.pressed(KeyCode::ShiftLeft) || keys.pressed(KeyCode::ShiftRight);
    let edit = &mut *edit;
    match act {
        Act::Preset(i) => load_preset(edit, &mut ui, i, &data),
        Act::SaveAs => ui.save_as = true,
        Act::Back => {
            screens.pop();
        }
        Act::Confirm => confirm(edit, &ctx, &data, &mut active, &mut screens, &session, &mut senders),
        Act::Agent(i) => {
            if let Some(a) = ui_data.agents.get(i) {
                edit.draft.agent = a.id.clone();
            }
        }
        Act::Weapon(i) => {
            if let Some(w) = data.weapons.weapons.get(i)
                && w.id != edit.draft.weapon
            {
                for slot in edit.draft.switch_weapon(&w.id.clone(), &data) {
                    ui.flash[slot] = 1.0;
                }
                ui.close_pop();
            }
        }
        Act::Slot(cat) => {
            if ui.pop == Some(Pop::Slot(cat)) {
                ui.close_pop();
            } else {
                ui.open_pop(Pop::Slot(cat));
            }
        }
        Act::Mag(i) => {
            // Acts on release (click = picker, drag = swap).
            let Some(cursor) = windows.iter().next().and_then(|w| w.cursor_position()) else { return };
            let cursor = cursor / scale.0;
            // Physical px -> UI px: the card's top-left under the cursor.
            let grab = cards
                .iter()
                .find(|(a, ..)| **a == Act::Mag(i))
                .map(|(_, n, t)| cursor - (t.translation - n.size() / 2.0) * n.inverse_scale_factor)
                .unwrap_or(Vec2::new(70.0, 38.0));
            ui.drag = Some(Drag {
                from: i,
                start: cursor,
                grab,
                active: false,
                over: None,
                was_open: ui.pop == Some(Pop::Mag(i)),
            });
        }
        Act::Core(c) => edit.draft.set_core(c),
        Act::Tier(t) => {
            if shift {
                edit.draft.set_tier_all(t, caps);
            } else {
                edit.draft.set_tier(ui.arc, t, caps);
            }
        }
        Act::Zone(z) => ui.arc = z,
        Act::ZoneCheck(z) => {
            edit.draft.toggle_arc(z, caps);
            ui.arc = z;
        }
        Act::Row(r) => {
            if let Some(pop) = ui.pop {
                popover::pick(&mut edit.draft, pop, r, &data, &ui_data);
                ui.close_pop();
            }
        }
    }
}

/// Magazine cards: a click opens the ammo picker, a drag onto another loaded card swaps their ammo.
fn mag_release(
    mouse: Res<ButtonInput<MouseButton>>,
    windows: Query<&Window, With<PrimaryWindow>>,
    scale: Res<UiScale>,
    cards: Query<(&Act, &RelativeCursorPosition)>,
    mut edit: ResMut<LoadoutEdit>,
    mut ui: ResMut<LoadoutUi>,
) {
    let Some(mut drag) = ui.drag else { return };
    let cursor = windows.iter().next().and_then(|w| w.cursor_position()).map(|c| c / scale.0);
    let loaded = edit.draft.mags.len();
    if mouse.pressed(MouseButton::Left) {
        if let Some(c) = cursor
            && !drag.active
            && drag.from < loaded
            && c.distance(drag.start) > 5.0
        {
            drag.active = true;
            ui.close_pop();
        }
        if drag.active {
            drag.over = cards.iter().find_map(|(a, r)| match a {
                Act::Mag(i) if *i < loaded && r.cursor_over() => Some(*i),
                _ => None,
            });
        }
        if ui.drag != Some(drag) {
            ui.drag = Some(drag);
        }
        return;
    }
    ui.drag = None;
    if drag.active {
        if let Some(to) = drag.over
            && to != drag.from
        {
            edit.draft.swap_mags(drag.from, to);
        }
    } else if drag.was_open {
        ui.close_pop();
    } else if drag.from <= loaded {
        ui.open_pop(Pop::Mag(drag.from));
    }
}

/// Right click: closes the popover, or removes the last magazine (only the last one can go).
fn right_click(
    mouse: Res<ButtonInput<MouseButton>>,
    cards: Query<(&Act, &Interaction)>,
    mut edit: ResMut<LoadoutEdit>,
    mut ui: ResMut<LoadoutUi>,
) {
    if !mouse.just_pressed(MouseButton::Right) {
        return;
    }
    if ui.pop.is_some() {
        ui.close_pop();
        return;
    }
    let hovered = cards.iter().find_map(|(a, i)| match (a, i) {
        (Act::Mag(n), Interaction::Hovered | Interaction::Pressed) => Some(*n),
        _ => None,
    });
    if let Some(n) = hovered {
        let len = edit.draft.mags.len();
        if n + 1 == len && n > 0 {
            edit.draft.remove_last_mag();
        } else if n < len {
            ui.flash[n] = 1.0;
        }
    }
}

/// Keyboard: Esc (popover, then the name field, then BACK), 1-3 presets, R reset, arrows in the popover,
/// Shift+arrows move a magazine.
#[allow(clippy::too_many_arguments)]
fn keys(
    mut keys: ResMut<ButtonInput<KeyCode>>,
    mut edit: ResMut<LoadoutEdit>,
    mut ui: ResMut<LoadoutUi>,
    mut screens: ResMut<Screens>,
    data: Res<Data>,
    ui_data: Res<LoadoutUiData>,
    cards: Query<(&Act, &Interaction)>,
) {
    if keys.just_pressed(KeyCode::Escape) {
        keys.clear_just_pressed(KeyCode::Escape);
        if ui.save_as {
            ui.save_as = false;
        } else if ui.pop.is_some() {
            ui.close_pop();
        } else {
            screens.pop();
        }
        return;
    }
    if ui.save_as {
        return;
    }
    // The keyboard focus, else what the mouse is over.
    let hovered = ui
        .focus
        .filter(|_| ui.keyboard)
        .or_else(|| cards.iter().find_map(|(a, i)| matches!(i, Interaction::Hovered).then_some(*a)));
    for (k, i) in [(KeyCode::Digit1, 0), (KeyCode::Digit2, 1), (KeyCode::Digit3, 2)] {
        if keys.just_pressed(k) {
            load_preset(&mut edit, &mut ui, i, &data);
        }
    }
    if keys.just_pressed(KeyCode::KeyR) {
        let target = match ui.pop {
            Some(p) => Some(p),
            None => match hovered {
                Some(Act::Slot(c)) => Some(Pop::Slot(c)),
                Some(Act::Mag(i)) => Some(Pop::Mag(i)),
                _ => None,
            },
        };
        match target {
            Some(Pop::Slot(c)) => edit.draft.reset_part(c, &data),
            Some(Pop::Mag(i)) if i < edit.draft.mags.len() => {
                edit.draft.set_mag(i, vetf_sim::data::AmmoChoice::STANDARD);
            }
            _ => {}
        }
        ui.close_pop();
    }
    if let Some(pop) = ui.pop {
        let n = popover::rows(&edit.draft, pop, &data, &ui_data).len();
        if n > 0 {
            let cur = ui.focus_row.or(ui.hover_row);
            if keys.just_pressed(KeyCode::ArrowDown) {
                ui.focus_row = Some(cur.map_or(0, |c| (c + 1) % n));
            }
            if keys.just_pressed(KeyCode::ArrowUp) {
                ui.focus_row = Some(cur.map_or(n - 1, |c| (c + n - 1) % n));
            }
            if keys.just_pressed(KeyCode::Enter)
                && let Some(r) = ui.focus_row.or(ui.hover_row)
            {
                popover::pick(&mut edit.draft, pop, r, &data, &ui_data);
                ui.close_pop();
            }
        }
        return;
    }
    let shift = keys.pressed(KeyCode::ShiftLeft) || keys.pressed(KeyCode::ShiftRight);
    if shift && let Some(Act::Mag(i)) = hovered {
        let len = edit.draft.mags.len();
        if keys.just_pressed(KeyCode::ArrowLeft) && i > 0 && i < len {
            edit.draft.swap_mags(i, i - 1);
            ui.focus = Some(Act::Mag(i - 1));
        }
        if keys.just_pressed(KeyCode::ArrowRight) && i + 1 < len {
            edit.draft.swap_mags(i, i + 1);
            ui.focus = Some(Act::Mag(i + 1));
        }
    }
}

/// The + SAVE AS field: upper case as you type, Enter saves the build under that name into the active
/// letter (all three letters always hold a preset).
fn save_as_field(
    mut fields: Query<(Entity, &mut EditableText), With<SaveAsField>>,
    mut focus: ResMut<InputFocus>,
    keys: Res<ButtonInput<KeyCode>>,
    mut edit: ResMut<LoadoutEdit>,
    mut ui: ResMut<LoadoutUi>,
) {
    let Some((e, mut field)) = fields.iter_mut().next() else { return };
    if focus.get() != Some(e) {
        focus.set(e, FocusCause::Navigated);
    }
    let value = field.value().to_string();
    let upper = presets::clean_name(&value);
    if value != upper && !value.ends_with(' ') {
        field.editor_mut().set_text(&upper);
        field.queue_edit(TextEdit::TextEnd(false));
    }
    if keys.just_pressed(KeyCode::Enter) {
        if !upper.is_empty() {
            let i = edit.file.active;
            let choice = edit.draft.choice();
            edit.file.presets[i] = presets::Preset { name: upper, loadout: choice };
            edit.file.attachments = edit.draft.parts.clone();
            if let Err(err) = edit.file.save() {
                warn!("loadout presets not saved: {err}");
            }
        }
        ui.save_as = false;
        focus.clear();
    }
}

/// Which popover row the mouse is over (the stats panel and the hotspot tag preview it).
fn hover_rows(q: Query<(&Act, &Interaction), Changed<Interaction>>, mut ui: ResMut<LoadoutUi>) {
    for (a, i) in &q {
        let Act::Row(r) = a else { continue };
        match i {
            Interaction::Hovered | Interaction::Pressed => {
                if ui.hover_row != Some(*r) {
                    ui.hover_row = Some(*r);
                    ui.focus_row = None;
                }
            }
            Interaction::None => {
                if ui.hover_row == Some(*r) {
                    ui.hover_row = None;
                }
            }
        }
    }
}

/// The warning flash on magazines that changed (1 s).
fn tick_flash(time: Res<Time>, mut ui: ResMut<LoadoutUi>) {
    if ui.flash.iter().all(|f| *f <= 0.0) {
        return;
    }
    let dt = time.delta_secs();
    let mut next = ui.flash;
    for f in &mut next {
        *f = (*f - dt).max(0.0);
    }
    // Only the on/off change matters to the cards.
    let on = |a: &[f32; 6]| a.map(|f| f > 0.0);
    if on(&next) != on(&ui.flash) {
        ui.flash = next;
    } else {
        ui.bypass_change_detection().flash = next;
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use vetf_sim::data::AmmoChoice;

    /// A command line without options.
    pub(crate) fn plain_cli() -> Cli {
        Cli {
            host: None,
            join: None,
            name: "T".into(),
            port: None,
            width: 1,
            height: 1,
            screenshot: None,
            screenshot_after: 0.0,
            exit_after: None,
            bot: false,
            yaw: None,
            demo_ui: None,
            weapon: None,
            ammo: None,
            mags: None,
            armor: None,
            attach: None,
        }
    }

    #[test]
    fn the_default_loadout_summarises_within_budget() {
        let d = GameData::embedded();
        let l = &d.rules.default_loadout;
        let c = LoadoutChoice {
            weapon: l.primary.clone(),
            mags: l.mags.clone(),
            attachments: l.attachments.clone(),
            halo: crate::config::halo_from_armor(&l.armor, &d),
            agent: "kestrel".into(),
        };
        let s = summary(&c, &d);
        assert_eq!(s.weapon_name, "AR-7 Mako");
        assert_eq!(s.mags.len(), l.mags.len());
        assert_eq!(s.mags[0], (1, "STD".into(), AmmoKind::Standard));
        assert_eq!(s.armor_name, "T2 MENDER");
        assert_eq!(s.agent_name, "KESTREL");
        assert_eq!(s.attachments[0], "HOLO");
        assert_eq!(s.weight, WeightClass::Light);
        assert!(s.gear_cost <= s.gear_budget);
        let ap = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 };
        let c = LoadoutChoice { mags: vec![ap; 6], ..c };
        assert!(summary(&c, &d).gear_cost > s.gear_budget, "six AP III magazines are over budget");
    }

    #[test]
    fn an_over_budget_preset_is_not_used_at_start_up() {
        let d = GameData::embedded();
        let mut file = LoadoutsFile::default();
        file.repair(&d, "kestrel");
        file.active = 2;
        let cli = plain_cli();
        assert_eq!(preset_choice(&file, &d, &cli), file.presets[2].loadout, "C · MEDIC is valid");
        let ap3 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 };
        file.presets[2].loadout.mags = vec![ap3; 4];
        let fallback = preset_choice(&file, &d, &cli);
        assert_eq!(fallback, crate::config::loadout_choice(&cli, &d));
    }

    #[test]
    fn the_budget_depends_on_where_the_screen_opens() {
        let d = GameData::embedded();
        let mut app = App::new();
        app.add_systems(Update, |q: Query<&MatchState>, mut out: Local<Vec<ScreenCtx>>| {
            let d = GameData::embedded();
            out.push(ScreenCtx::new(&d, &AppState::MainMenu, &q));
            assert_eq!(out[0].note, "TDM DEFAULT");
            assert_eq!(out[0].budget, Some(d.rules.tdm.gear_budget));
            let in_match = ScreenCtx::new(&d, &AppState::InGame, &q);
            assert!(in_match.in_match);
            assert_eq!(in_match.note, "HOST OPTION");
        });
        app.update();
        assert_eq!(gear_budget(&d, MatchMode::Range), None);
    }
}
