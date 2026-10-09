//! The Loadout hub screen, in two layouts:
//! - Team deathmatch and free-for-all (DIRECTION_LOG 17): the gun, its attachments and its magazine type (six
//!   of it), then ONE armor tier (T1-T4), ONE ammo type for all six magazines, and the points used against
//!   the mode's total (`rules.ron` `deathmatch_loadout`). No agent pick (the host deals agents at random) and
//!   no halo core (everyone wears the mode's one halo).
//! - The gun range (mockups 05 / 05b): agent, weapon, attachments, the six ordered magazines with their own
//!   ammo, the custom halo (a core and a tier per arc) and the result.
//!
//! It opens over the lobby or the match (`Screen::Loadout`: the lobby's LOADOUT, the ESC menu's LOADOUT);
//! the main menu has no LOADOUT entry for now. In a match, CONFIRM (or Esc within the points) sends a
//! `LoadoutUpdate` that the host applies at the next spawn (at once in the lobby). Over the death screen
//! there is no CONFIRM: valid edits go out as they are made and RESPAWN takes them into the next life
//! (see [`apply`]).
//!
//! Contract with the other screens:
//! - [`ActiveLoadout`] is what this player asks the host for (sent in `Hello`, applied at each spawn).
//!   Applying (CONFIRM, Esc, or each edit while dead) updates it and saves it into the active preset
//!   (`loadouts.ron`).
//! - [`summary`] formats it for the main menu's player card and the ESC menu.
//! - Open the screen with `Screens::push(Screen::Loadout)`; Esc (after the popover) or BACK leaves it,
//!   applying the edits within the points (a second Esc discards them over the points).

mod apply;
mod focus;
mod gun_preview;
mod halo;
mod kit_view;
mod model;
mod popover;
mod presets;
pub(crate) mod text;
mod ui_data;
mod view;

pub use gun_preview::StudioLight;
pub use model::Draft;
pub use presets::LoadoutsFile;
#[allow(unused_imports)] // for the other hub screens
pub use text::{ammo_short, halo_name, tier_label};

use crate::AppState;
use crate::config::{Cli, Data};
use crate::death::DeathState;
use crate::net::Session;
use crate::screens::{EscPress, EscSystems, Screen, ScreenRoot, Screens, screen_on_top};
use crate::ui_kit::*;
use apply::{EscOutcome, RespawnBtn};
use bevy::app::{HierarchyPropagatePlugin, PropagateSet};
use bevy::camera::visibility::{RenderLayers, VisibilitySystems};
use bevy::ecs::system::SystemParam;
use bevy::input_focus::{FocusCause, InputFocus};
use bevy::prelude::*;
use bevy::text::{EditableText, TextEdit};
use bevy::ui::RelativeCursorPosition;
use bevy::window::PrimaryWindow;
use halo::HaloImages;
use lightyear::prelude::*;
use std::hash::{Hash, Hasher};
use ui_data::LoadoutUiData;
use vetf_net::{LoadoutChoice, LoadoutUpdate, MatchMode, MatchState, ReliableChannel, RespawnRequest, Vitals};
use vetf_sim::GameData;
use vetf_sim::ZoneTable;
use vetf_sim::data::{AmmoChoice, AmmoKind, AttachmentCategory, Core, WeightClass};
use vetf_sim::gear::gear_budget;
use vetf_sim::{Zone, gear};

pub struct LoadoutScreenPlugin;

impl Plugin for LoadoutScreenPlugin {
    fn build(&self, app: &mut App) {
        app.insert_resource(LoadoutUiData::load())
            .init_resource::<LoadoutUi>()
            .add_systems(Startup, (init_active_loadout, load_halo_images))
            .add_systems(Update, (demo_open, open_screen).chain())
            .add_systems(
                Update,
                (
                    focus::keyboard_focus,
                    presses,
                    mag_release,
                    apply_while_dead,
                    right_click,
                    esc.in_set(EscSystems::Top),
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
            .add_systems(Update, halo::orbit_cells)
            // The 3D gun preview: its camera and stage live while the screen's preview box does.
            .add_plugins(HierarchyPropagatePlugin::<RenderLayers>::new(PostUpdate))
            .configure_sets(
                PostUpdate,
                PropagateSet::<RenderLayers>::default().before(VisibilitySystems::CheckVisibility),
            )
            .add_systems(
                Update,
                (
                    gun_preview::teardown,
                    gun_preview::setup,
                    gun_preview::drag_and_zoom
                        .run_if(screen_on_top(Screen::Loadout).and_then(resource_exists::<gun_preview::GunPreview>)),
                    (gun_preview::sync_gun, gun_preview::pose)
                        .chain()
                        .run_if(resource_exists::<gun_preview::GunPreview>.and_then(resource_exists::<LoadoutEdit>)),
                )
                    .chain()
                    .after(open_screen)
                    .before(view::refresh),
            )
            .add_systems(Update, gun_preview::place_hotspots.after(view::refresh));
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
/// host would refuse in the mode this player hosts (`--mode`, else team deathmatch; e.g. saved over budget
/// with + SAVE AS) gives the default loadout.
fn preset_choice(file: &LoadoutsFile, data: &GameData, cli: &Cli) -> LoadoutChoice {
    let preset = &file.presets[file.active.min(file.presets.len().saturating_sub(1))].loadout;
    let mode = cli.mode.unwrap_or(MatchMode::Tdm);
    let shaped = Draft::from_choice(preset, &file.attachments, data, data.rules.fixed_loadout(mode).cloned());
    if shaped.problems(data, gear_budget(data, mode)).is_empty() {
        // As saved (the gun range keeps its mixed magazines); each mode shapes it its own way.
        Draft::from_choice(preset, &file.attachments, data, None).choice()
    } else {
        warn!("loadout preset {} cannot be used in {mode:?}; using the default loadout", file.label(file.active));
        crate::config::loadout_choice(
            &Cli { weapon: None, ammo: None, mags: None, armor: None, attach: None, ..cli.clone() },
            data,
        )
    }
}

fn load_halo_images(mut commands: Commands, assets: Res<AssetServer>) {
    commands.insert_resource(HaloImages::load(&assets));
}

/// A loadout as the hub screens show it, in one mode.
#[derive(Debug, Clone, PartialEq)]
pub struct LoadoutSummary {
    pub weapon_name: String,
    pub attachments: Vec<String>,
    /// (slot 1-based, short ammo label, ammo type) in slot order. Never round counts.
    pub mags: Vec<(usize, String, AmmoKind)>,
    /// Team deathmatch and free-for-all: one halo, one armor tier and one ammo type for everyone's six
    /// magazines; the core is not worth naming, and the ammo is one label.
    pub one_halo: bool,
    /// The deathmatch armor tier (1-based, 0 for NO HALO; None in the gun range).
    pub armor_tier: Option<u8>,
    /// The halo in a few words: `T2 MENDER`, `T1–T3 BULWARK`, `NO HALO`; `T3 HALO` for an armor tier.
    pub armor_name: String,
    pub core: Option<Core>,
    /// Tier per halo arc (loadout caps applied).
    pub tiers: ZoneTable<u8>,
    pub weight: WeightClass,
    /// The mode's points and their parts (halo or armor tier, ammo, magazine type), against the mode's
    /// budget (None: the gun range has no limit).
    pub gear_cost: u32,
    pub ammo_cost: u32,
    pub mag_cost: u32,
    /// The optic's points (the variable 1-3x; 0 for every other optic).
    pub optic_cost: u32,
    pub gear_budget: Option<u32>,
    /// The agent's display name (cosmetic for now): the pick in the gun range.
    pub agent_name: String,
}

impl LoadoutSummary {
    /// The ammo of a one-ammo-type loadout: (short label, type, magazines). None with mixed magazines.
    pub fn one_ammo(&self) -> Option<(String, AmmoKind, usize)> {
        let (_, label, kind) = self.mags.first()?;
        self.mags.iter().all(|(_, l, _)| l == label).then(|| (label.clone(), *kind, self.mags.len()))
    }

    /// The halo's (or armor tier's) part of the points.
    pub fn halo_cost(&self) -> u32 {
        self.gear_cost.saturating_sub(self.ammo_cost + self.mag_cost + self.optic_cost)
    }
}

/// `agents.ron`, read once (the agent names the hub screens show, and the agents the host deals).
fn agents_data() -> &'static LoadoutUiData {
    static AGENTS: std::sync::OnceLock<LoadoutUiData> = std::sync::OnceLock::new();
    AGENTS.get_or_init(LoadoutUiData::load)
}

/// Every agent's id, in `agents.ron` order: what team deathmatch and free-for-all deal from.
pub fn agent_ids() -> Vec<String> {
    agents_data().agents.iter().map(|a| a.id.clone()).collect()
}

/// An agent's display name (`KESTREL`), or the id in capitals for one this build does not know.
pub fn agent_name(id: &str) -> String {
    agents_data().agent(id).map_or(id.to_uppercase(), |(_, a)| a.name.clone())
}

/// An agent's badge on the scoreboard and in the lobby: its initial and its accent colour.
pub fn agent_badge(id: &str) -> (String, Color) {
    let accent = agents_data().agent(id).map(|(_, a)| a.accent);
    let initial = agent_name(id).chars().next().map_or("?".into(), |c| c.to_string());
    let color = match accent {
        Some(ui_data::Accent::Teal) => AGENT_KESTREL,
        Some(ui_data::Accent::Coral) => AGENT_SOLACE,
        None => TEXT_MID,
    };
    (initial, color)
}

/// Summarise a loadout choice as `mode` takes it (unknown ids fall back to what the host would use).
pub fn summary(choice: &LoadoutChoice, data: &GameData, mode: MatchMode) -> LoadoutSummary {
    let choice = &choice.for_mode(data, mode);
    let weapon = data.offered_weapon(&choice.weapon).or_else(|| data.weapon(&data.rules.default_loadout.primary));
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
    let cost =
        weapon.map(|w| gear::loadout_cost(data, mode, w, &halo, &choice.mags, &choice.attachments)).unwrap_or_default();
    let kit = data.rules.fixed_loadout(mode);
    let armor_tier = kit.and_then(|k| k.tier_of(halo.tiers));
    LoadoutSummary {
        weapon_name: weapon.map_or("?".into(), |w| w.name.clone()),
        attachments: choice
            .attachments
            .iter()
            .map(|a| data.attachment(a).map_or(a.clone(), |s| s.display_name().to_string()))
            .collect(),
        mags,
        one_halo: kit.is_some(),
        armor_tier,
        armor_name: match armor_tier {
            Some(0) => "NO HALO".into(),
            Some(t) => format!("T{t} HALO"),
            None => halo_name(&halo),
        },
        core: armor.core,
        tiers: armor.tiers,
        weight: armor.weight_class,
        gear_cost: cost.total(),
        ammo_cost: cost.ammo,
        mag_cost: cost.mags,
        optic_cost: cost.optic,
        gear_budget: gear_budget(data, mode),
        agent_name: agent_name(&choice.agent),
    }
}

// ---------------------------------------------------------------------------------------------- state

/// The edit in progress while the screen is open (dropped when it closes).
#[derive(Resource, Debug, Clone)]
pub struct LoadoutEdit {
    pub draft: Draft,
    pub file: LoadoutsFile,
    /// The picks as last applied (or as opened): what Esc compares the draft with.
    pub base: LoadoutChoice,
}

impl LoadoutEdit {
    /// The picks differ from the last applied ones.
    pub fn changed(&self) -> bool {
        self.draft.choice() != self.base
    }

    /// Within the points and the caps: the host would take it.
    pub fn valid(&self, data: &GameData, budget: Option<u32>) -> bool {
        self.draft.problems(data, budget).is_empty()
    }
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
    /// The first Esc over the points showed the notice, for the draft with this hash (a second Esc on the
    /// same picks discards them).
    pub esc_warned: Option<u64>,
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
            esc_warned: None,
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

/// Where the screen is shown: over a match (its mode decides the layout, the picks and the budget) or over
/// the menu (team deathmatch's, as a default).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct ScreenCtx {
    pub in_match: bool,
    /// Over the lobby: the host puts a confirmed loadout on at once (no fighting yet).
    pub lobby: bool,
    /// Over the death screen: no CONFIRM, valid edits apply as they are made and RESPAWN takes its place.
    pub dead: bool,
    pub mode: MatchMode,
    pub budget: Option<u32>,
    /// The mode sells picks (team deathmatch, free-for-all: `rules.ron` `deathmatch_loadout`): the
    /// deathmatch layout. False: the gun range's.
    pub simple: bool,
    /// The micro after the budget: TEAM DEATHMATCH, FREE-FOR-ALL, GUN RANGE, TDM DEFAULT.
    pub note: &'static str,
}

impl ScreenCtx {
    fn new(data: &GameData, state: &AppState, matches: &Query<&MatchState>, death: Option<&DeathState>) -> Self {
        let in_match = matches!(state, AppState::InGame | AppState::Connecting);
        let m = matches.iter().next().filter(|_| in_match);
        let lobby = m.is_some_and(|m| m.phase == vetf_net::MatchPhase::Lobby);
        let dead = in_match && death.is_some_and(|d| d.dead);
        let ctx = Self::for_mode(data, in_match, m.map(|m| m.mode));
        // The points this match allows: the host's lobby setting (`rules.ron`'s over the menu).
        let budget = m.map_or(ctx.budget, |m| m.gear_budget());
        Self { lobby, dead, budget, ..ctx }
    }

    /// `mode`: the match's, None over the menu (or before the match state arrives).
    fn for_mode(data: &GameData, in_match: bool, mode: Option<MatchMode>) -> Self {
        let note = match mode {
            None => "TDM DEFAULT",
            Some(m) => crate::lobby::mode_title(m),
        };
        let mode = mode.unwrap_or(MatchMode::Tdm);
        let simple = data.rules.fixed_loadout(mode).is_some();
        Self { in_match, lobby: false, dead: false, mode, budget: gear_budget(data, mode), simple, note }
    }

    /// The deathmatch layout: the gun with its parts and magazine type, an armor tier, one ammo type, points.
    pub fn simple(&self) -> bool {
        self.simple
    }

    /// The picks this mode sells, for a draft (None: the gun range).
    pub fn kit(&self, data: &GameData) -> Option<vetf_sim::data::DeathmatchLoadout> {
        data.rules.fixed_loadout(self.mode).cloned()
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
    /// The deathmatch layout: a magazine type (its index in the attachment data). No card shows it (the MAG
    /// slot's popover picks the type); the scripted demo picks (`demo_picks`) click it.
    MagType(usize),
    /// The deathmatch layout: an armor tier (1-based).
    Armor(u8),
    /// The deathmatch layout: the one ammo type.
    Ammo(AmmoChoice),
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

/// A scripted pick on the deathmatch layout (`--demo-ui loadout-set:TIER,AMMO[,MAG][,WEAPON]`, e.g.
/// `loadout-set:3,ap3,mag_45`, or `loadout-pick:...` which then confirms): the clicks it makes, in order (the
/// gun first, so its magazine type can be picked).
pub fn demo_picks(spec: &str, data: &GameData) -> Option<Vec<Act>> {
    let parts: Vec<&str> = spec.split(',').map(str::trim).collect();
    let [tier, ammo, rest @ ..] = parts.as_slice() else { return None };
    let tier: u8 = tier.trim_start_matches(['t', 'T']).parse().ok()?;
    let mut gun = Vec::new();
    let mut mag = Vec::new();
    for id in rest {
        match data.weapon_index(id) {
            Some(w) if data.weapons.weapons[w].hidden => return None,
            Some(w) => gun.push(Act::Weapon(w)),
            None => {
                let i = data.attachments.attachments.iter().position(|a| a.id == *id)?;
                if data.attachments.attachments[i].cat != AttachmentCategory::Mag {
                    return None;
                }
                mag.push(Act::MagType(i));
            }
        }
    }
    let mut acts = gun;
    acts.extend(mag);
    acts.push(Act::Armor(tier));
    acts.push(Act::Ammo(crate::config::parse_ammo(ammo)?));
    Some(acts)
}

/// `--demo-ui loadout | loadout-ammo | loadout-attach`: open the screen over the main menu, or over the
/// lobby or match with `--host` / `--join` (and a popover). `loadout-set:TIER,AMMO[,MAG][,WEAPON]` also picks
/// that armor tier, ammo (`ap2`), magazine type and gun through the screen's own clicks; `loadout-pick:...`
/// then presses CONFIRM (the lobby then readies, and the host starts: see `lobby::demo`).
#[allow(clippy::too_many_arguments)]
fn demo_open(
    cli: Res<Cli>,
    state: Res<State<AppState>>,
    time: Res<Time>,
    data: Res<Data>,
    mut screens: ResMut<Screens>,
    mut ui: ResMut<LoadoutUi>,
    edit: Option<Res<LoadoutEdit>>,
    mut step: Local<u8>,
    mut since: Local<Option<f32>>,
    mut queue: Local<Vec<Act>>,
) {
    let Some(demo) = cli.demo_ui.as_deref() else { return };
    // On the main menu, or over the lobby / match with --host or --join.
    let base = if cli.host.is_some() || cli.join.is_some() { AppState::InGame } else { AppState::MainMenu };
    if !demo.starts_with("loadout") || *state.get() != base {
        return;
    }
    // Let the match state and the hello settle first (a joiner needs a moment).
    let t = time.elapsed_secs();
    if base == AppState::InGame && t - *since.get_or_insert(t) < 3.0 {
        return;
    }
    let script = demo.split_once(':').filter(|(k, _)| matches!(*k, "loadout-set" | "loadout-pick"));
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
            if let Some((kind, spec)) = script {
                match demo_picks(spec, &data) {
                    Some(mut acts) => {
                        if kind == "loadout-pick" {
                            acts.push(Act::Confirm);
                        }
                        info!("--demo-ui {kind}: {acts:?}");
                        acts.reverse();
                        *queue = acts;
                    }
                    None => warn!("--demo-ui {demo}: expected TIER,AMMO[,MAG][,WEAPON]"),
                }
            }
            *step = 2;
        }
        // One click a frame, through `presses` (as Enter on a focused item).
        2 if ui.activate.is_none() => {
            if let Some(act) = queue.pop() {
                ui.activate = Some(act);
            } else {
                *step = 3;
            }
        }
        _ => {}
    }
}

/// Spawn the page when the screen comes to the top; drop the edit when it leaves the stack.
#[allow(clippy::too_many_arguments)]
fn open_screen(
    mut commands: Commands,
    screens: Res<Screens>,
    roots: Query<(Entity, &ScreenRoot)>,
    edit: Option<ResMut<LoadoutEdit>>,
    active: Res<ActiveLoadout>,
    data: Res<Data>,
    mut ui: ResMut<LoadoutUi>,
    (state, matches): (Res<State<AppState>>, Query<&MatchState>),
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
    let ctx = ScreenCtx::new(&data, state.get(), &matches, None);
    let kit = ctx.kit(&data);
    // The host switched the lobby between the deathmatch modes: same layout, the new mode's picks (today
    // both modes sell the same ones, so this only matters once they differ).
    if let Some(mut edit) = edit
        && root.is_some()
        && edit.draft.fixed.is_some()
        && kit.is_some()
        && edit.draft.fixed != kit
    {
        let parts = edit.draft.parts.clone();
        edit.draft = Draft::from_choice(&edit.draft.choice(), &parts, &data, kit.clone());
    }
    if root.is_some() || !screens.top().is_some_and(|t| t.same_kind(Screen::Loadout)) {
        return;
    }
    let mut file = LoadoutsFile::load(&data, crate::config::DEFAULT_AGENT);
    let draft = Draft::from_choice(&active.0, &file.attachments, &data, kit.clone());
    // The edit starts from what the player spawns with; it belongs to the preset it equals as this mode
    // takes it (else the last one).
    let shaped = |p: &presets::Preset| Draft::from_choice(&p.loadout, &file.attachments, &data, kit.clone()).choice();
    if let Some(i) = file.presets.iter().position(|p| shaped(p) == draft.choice()) {
        file.active = i;
    }
    commands.insert_resource(LoadoutEdit { base: draft.choice(), draft, file });
    *ui = LoadoutUi::default();
    let depth = screens.iter().position(|s| s.same_kind(Screen::Loadout)).unwrap_or(0) as i32;
    view::spawn_root(&mut commands, 100 + depth * 10, ctx.simple());
}

// ---------------------------------------------------------------------------------------------- actions

fn load_preset(edit: &mut LoadoutEdit, ui: &mut LoadoutUi, i: usize, data: &GameData) {
    let Some(p) = edit.file.presets.get(i) else { return };
    edit.draft = Draft::from_choice(&p.loadout, &edit.file.attachments, data, edit.draft.fixed.clone());
    edit.file.active = i;
    ui.close_pop();
    ui.flash = [0.0; 6];
}

/// What applying a loadout needs: the active loadout and the link to the host.
#[derive(SystemParam)]
pub struct Applier<'w, 's> {
    active: ResMut<'w, ActiveLoadout>,
    session: Res<'w, Session>,
    senders: Query<'w, 's, &'static mut MessageSender<LoadoutUpdate>, With<Client>>,
}

impl Applier<'_, '_> {
    /// Apply the edit if the host would take it: save it into the active preset, make it the active
    /// loadout and send it to the host in a match (the next spawn takes it; the lobby puts it on at once).
    /// False (nothing done) over the points.
    fn apply(&mut self, edit: &mut LoadoutEdit, ctx: &ScreenCtx, data: &GameData) -> bool {
        if !edit.valid(data, ctx.budget) {
            return false;
        }
        let choice = edit.draft.choice();
        let i = edit.file.active;
        edit.file.presets[i].loadout = choice.clone();
        edit.file.attachments = edit.draft.parts.clone();
        if let Err(e) = edit.file.save() {
            warn!("loadout presets not saved: {e}");
        }
        edit.base = choice.clone();
        self.active.0 = choice.clone();
        if ctx.in_match
            && let Some(client) = self.session.client
            && let Ok(mut sender) = self.senders.get_mut(client)
        {
            sender.send::<ReliableChannel>(LoadoutUpdate { loadout: choice });
            info!("loadout sent; it applies at the next spawn");
        }
        true
    }
}

/// Esc or BACK: apply within the points and close; over them, a notice first and a second press discards.
fn leave(
    edit: &mut LoadoutEdit,
    ui: &mut LoadoutUi,
    ctx: &ScreenCtx,
    data: &GameData,
    applier: &mut Applier,
    screens: &mut Screens,
) {
    match apply::esc_step(edit, ui, data, ctx.budget) {
        EscOutcome::Warn => {}
        EscOutcome::Apply => {
            applier.apply(edit, ctx, data);
            screens.pop();
        }
        EscOutcome::Close | EscOutcome::Discard => {
            screens.pop();
        }
    }
}

/// The death screen's RESPAWN, from this screen: the edits (already applied as they were made) go into the
/// next life. Blocked over the points or while the timer runs.
fn respawn_from_here(
    edit: &mut LoadoutEdit,
    ctx: &ScreenCtx,
    data: &GameData,
    applier: &mut Applier,
    screens: &mut Screens,
    (death, left, senders): (
        Option<&mut DeathState>,
        f32,
        &mut Query<&mut MessageSender<RespawnRequest>, With<Client>>,
    ),
) {
    let Some(death) = death else { return };
    if !RespawnBtn::new(left, edit.valid(data, ctx.budget), death.asked).enabled() || !applier.apply(edit, ctx, data) {
        return;
    }
    crate::death::ask_respawn(death, senders);
    screens.pop();
}

/// While dead, a valid edit is applied as soon as it is made (so the host's fallback respawn takes it too).
fn apply_while_dead(
    mut edit: ResMut<LoadoutEdit>,
    mut applier: Applier,
    data: Res<Data>,
    (state, matches, death): (Res<State<AppState>>, Query<&MatchState>, Option<Res<DeathState>>),
) {
    if !edit.is_changed() {
        return;
    }
    let ctx = ScreenCtx::new(&data, state.get(), &matches, death.as_deref());
    let valid = edit.valid(&data, ctx.budget);
    if apply::apply_now(ctx.dead, valid, &edit.draft.choice(), &edit.base) {
        applier.apply(&mut edit, &ctx, &data);
    }
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
    (mut screens, mut applier): (ResMut<Screens>, Applier),
    (mut death, me, mut respawns): (
        Option<ResMut<DeathState>>,
        Query<&Vitals, With<Controlled>>,
        Query<&mut MessageSender<RespawnRequest>, With<Client>>,
    ),
    (windows, scale, cards): (
        Query<&Window, With<PrimaryWindow>>,
        Res<UiScale>,
        Query<(&Act, &ComputedNode, &UiGlobalTransform)>,
    ),
) {
    let ctx = ScreenCtx::new(&data, state.get(), &matches, death.as_deref());
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
        Act::Back => leave(edit, &mut ui, &ctx, &data, &mut applier, &mut screens),
        Act::Confirm if ctx.dead => {
            let left = me.iter().next().map_or(f32::MAX, crate::death::respawn_left);
            let death = death.as_deref_mut();
            respawn_from_here(edit, &ctx, &data, &mut applier, &mut screens, (death, left, &mut respawns));
        }
        Act::Confirm => {
            if applier.apply(edit, &ctx, &data) {
                screens.pop();
            }
        }
        Act::Agent(i) => {
            if let Some(a) = ui_data.agents.get(i) {
                edit.draft.agent = a.id.clone();
            }
        }
        Act::Weapon(i) => {
            if let Some(w) = data.weapons.weapons.get(i).filter(|w| !w.hidden)
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
        Act::MagType(i) => {
            if let Some(m) = data.attachments.attachments.get(i) {
                let id = m.id.clone();
                edit.draft.set_part(AttachmentCategory::Mag, Some(&id), &data);
                ui.close_pop();
            }
        }
        Act::Armor(t) => {
            edit.draft.set_armor_tier(t);
        }
        Act::Ammo(c) => {
            edit.draft.set_ammo(c, &data);
            ui.flash[0] = 0.0;
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

/// Esc closes the + SAVE AS name field, else the popover, else leaves the screen like BACK ([`leave`]:
/// applied within the points; over them a notice, and a second Esc discards).
#[allow(clippy::too_many_arguments)]
fn esc(
    mut esc: ResMut<EscPress>,
    mut ui: ResMut<LoadoutUi>,
    mut edit: ResMut<LoadoutEdit>,
    mut applier: Applier,
    mut screens: ResMut<Screens>,
    data: Res<Data>,
    (state, matches, death): (Res<State<AppState>>, Query<&MatchState>, Option<Res<DeathState>>),
) {
    if !esc.take() {
        return;
    }
    if ui.save_as {
        ui.save_as = false;
    } else if ui.pop.is_some() {
        ui.close_pop();
    } else {
        let ctx = ScreenCtx::new(&data, state.get(), &matches, death.as_deref());
        leave(&mut edit, &mut ui, &ctx, &data, &mut applier, &mut screens);
    }
}

/// Keyboard: 1-3 presets, R reset, arrows in the popover, Shift+arrows move a magazine (Esc: [`esc`]).
#[allow(clippy::too_many_arguments)]
fn keys(
    keys: Res<ButtonInput<KeyCode>>,
    mut edit: ResMut<LoadoutEdit>,
    mut ui: ResMut<LoadoutUi>,
    data: Res<Data>,
    ui_data: Res<LoadoutUiData>,
    cards: Query<(&Act, &Interaction)>,
) {
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
        // The deathmatch layout: the ammo row back to standard (the MAG slot resets like any slot).
        if ui.pop.is_none() && matches!(hovered, Some(Act::Ammo(_))) {
            edit.draft.set_ammo(AmmoChoice::STANDARD, &data);
        }
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
                edit.draft.set_mag(i, AmmoChoice::STANDARD);
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
    use bevy::ecs::system::RunSystemOnce;

    /// A command line without options.
    pub(crate) fn plain_cli() -> Cli {
        Cli { name: "T".into(), ..Cli::default() }
    }

    /// The game data with the SK-9 Skink back in (hidden for now), for rules that hold for every gun.
    pub(crate) fn data_with_skink() -> GameData {
        let mut d = GameData::embedded();
        d.weapons.weapons.iter_mut().filter(|w| w.id == "sk9_skink").for_each(|w| w.hidden = false);
        d
    }

    fn default_choice(d: &GameData) -> LoadoutChoice {
        crate::server::default_choice(d)
    }

    #[test]
    fn the_default_loadout_summarises_within_budget() {
        let d = GameData::embedded();
        let c = default_choice(&d);
        let s = summary(&c, &d, MatchMode::Tdm);
        assert_eq!(s.weapon_name, "AR-7 Mako");
        assert_eq!(s.mags.len(), 6, "six magazines");
        assert_eq!(s.mags[0], (1, "STD".into(), AmmoKind::Standard));
        assert_eq!(s.one_ammo(), Some(("STD".into(), AmmoKind::Standard, 6)));
        assert!(s.one_halo);
        assert_eq!((s.armor_tier, s.armor_name.as_str()), (Some(2), "T2 HALO"), "Mender Scout's H2 T2: T2");
        assert_eq!(s.agent_name, "KESTREL");
        assert_eq!(s.attachments[0], "HOLO");
        assert_eq!(s.weight, WeightClass::Medium);
        assert_eq!(s.gear_budget, Some(d.rules.tdm.gear_budget));
        assert_eq!((s.gear_cost, s.halo_cost(), s.ammo_cost, s.mag_cost), (2, 2, 0, 0));
        // the gun range names the core and has no budget
        let range = summary(&c, &d, MatchMode::Range);
        assert_eq!((range.armor_name.as_str(), range.gear_budget, range.one_halo), ("T2 MENDER", None, false));
        assert_eq!(range.armor_tier, None);
        // T4 armor, AP II and the drum: over the deathmatch budget, the ammo paid once
        let ap2 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 };
        let rich = LoadoutChoice {
            mags: vec![ap2, AmmoChoice::STANDARD],
            attachments: vec!["mag_drum60".into()],
            halo: gear::HaloChoice { core: Core::Volt, tiers: d.armor.loadout_tier_caps },
            ..c.clone()
        };
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            let s = summary(&rich, &d, mode);
            assert_eq!(s.core, Some(Core::Mender), "{mode:?}: the one halo");
            assert_eq!((s.armor_tier, s.weight), (Some(4), WeightClass::Heavy));
            assert_eq!((s.halo_cost(), s.ammo_cost, s.mag_cost), (5, 2, 2), "AP II once");
            assert_eq!((s.gear_cost, s.gear_budget), (9, Some(8)), "{mode:?}: over");
            assert_eq!(s.one_ammo().map(|a| a.0), Some("AP II".into()));
        }
    }

    #[test]
    fn agents_have_names_and_badges() {
        assert_eq!(agent_ids(), ["kestrel", "solace"]);
        assert_eq!(agent_name("solace"), "SOLACE");
        assert_eq!(agent_name("nobody"), "NOBODY", "an agent this build does not know");
        assert_eq!(agent_badge("kestrel"), ("K".to_string(), AGENT_KESTREL));
        assert_eq!(agent_badge("solace"), ("S".to_string(), AGENT_SOLACE));
        assert_eq!(agent_badge("nobody").1, TEXT_MID);
    }

    #[test]
    fn an_over_budget_preset_is_not_used_at_start_up() {
        let d = GameData::embedded();
        let mut file = LoadoutsFile::default();
        file.repair(&d, "kestrel");
        file.active = 2;
        let cli = plain_cli();
        assert_eq!(preset_choice(&file, &d, &cli), file.presets[2].loadout, "C is valid");
        // mixed magazines fit a deathmatch (slot 1's ammo, paid once) and are kept as saved for the range
        let ap3 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 };
        file.presets[2].loadout.mags = vec![AmmoChoice::STANDARD, ap3, ap3];
        assert_eq!(preset_choice(&file, &d, &cli), file.presets[2].loadout);
        // T4 armor and AP III in slot 1: over budget, so the default loadout
        file.presets[2].loadout.mags = vec![ap3; 4];
        file.presets[2].loadout.halo.tiers = d.armor.loadout_tier_caps;
        let fallback = preset_choice(&file, &d, &cli);
        assert_eq!(fallback, crate::config::loadout_choice(&cli, &d));
    }

    /// The screen prices against the match's mode (free-for-all's own budget, not team deathmatch's) and
    /// picks its layout from it: the deathmatch modes sell picks, the range does not.
    #[test]
    fn the_budget_and_layout_follow_the_match() {
        let mut d = GameData::embedded();
        d.rules.ffa.gear_budget = 10;
        let menu = ScreenCtx::for_mode(&d, false, None);
        assert_eq!((menu.note, menu.budget, menu.mode), ("TDM DEFAULT", Some(d.rules.tdm.gear_budget), MatchMode::Tdm));
        assert!(menu.simple());
        let ffa = ScreenCtx::for_mode(&d, true, Some(MatchMode::Ffa));
        assert_eq!((ffa.note, ffa.budget), ("FREE-FOR-ALL", Some(10)));
        assert_eq!(ffa.kit(&d).as_ref(), d.rules.fixed_loadout(MatchMode::Ffa));
        let range = ScreenCtx::for_mode(&d, true, Some(MatchMode::Range));
        assert_eq!((range.note, range.budget, range.simple()), ("GUN RANGE", None, false));
        assert_eq!(range.kit(&d), None);
        // and from the replicated match
        let mut app = App::new();
        app.world_mut().spawn(MatchState {
            mode: MatchMode::Ffa,
            map: "showhome".into(),
            score_a: 0,
            score_b: 0,
            score_limit: 25,
            time_left_s: 600.0,
            phase: vetf_net::MatchPhase::Lobby,
            lobby_name: String::new(),
            max_players: 8,
            rules: d.rules.rulesets.ffa,
            mag_check: Default::default(),
            tick_hz: 120,
            snapshot_hz: 60,
            // The host set POINTS to 13 in the lobby.
            settings: vetf_net::MatchSettings { gear_budget: 13, ..d.rules.ffa.settings() },
        });
        let data = d.clone();
        let ctx = app
            .world_mut()
            .run_system_once(move |q: Query<&MatchState>| {
                (
                    ScreenCtx::new(&data, &AppState::InGame, &q, None),
                    ScreenCtx::new(&data, &AppState::MainMenu, &q, None),
                )
            })
            .unwrap();
        assert_eq!((ctx.0.mode, ctx.0.budget), (MatchMode::Ffa, Some(13)), "in the match: the host's POINTS");
        assert_eq!(ctx.1.mode, MatchMode::Tdm, "over the menu");
    }

    /// Bevy refuses a system whose queries clash when it is first run (the missing resources only make
    /// these runs return an error).
    #[test]
    fn the_apply_systems_have_no_conflicting_queries() {
        let mut world = World::new();
        let _ = world.run_system_once(presses);
        let _ = world.run_system_once(esc);
        let _ = world.run_system_once(apply_while_dead);
        let _ = world.run_system_once(view::refresh);
    }

    #[test]
    fn demo_picks_click_through_the_deathmatch_layout() {
        let d = data_with_skink();
        let ap2 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 };
        assert_eq!(demo_picks("3,ap2", &d).unwrap(), [Act::Armor(3), Act::Ammo(ap2)]);
        let mag = |id: &str| Act::MagType(d.attachments.attachments.iter().position(|a| a.id == id).unwrap());
        let skink = Act::Weapon(d.weapon_index("sk9_skink").unwrap());
        // the gun first, then its magazine type, whatever order they were given in
        let acts = demo_picks("t1,std,skink_mag_60,sk9_skink", &d).unwrap();
        assert_eq!(acts, [skink, mag("skink_mag_60"), Act::Armor(1), Act::Ammo(AmmoChoice::STANDARD)]);
        assert_eq!(demo_picks("4,std,mag_drum60", &d).unwrap()[0], mag("mag_drum60"));
        assert_eq!(demo_picks("3", &d), None);
        assert_eq!(demo_picks("3,laser", &d), None, "not an ammo");
        assert_eq!(demo_picks("3,std,optic_holo", &d), None, "not a magazine");
        assert_eq!(demo_picks("x,std", &d), None);
        // The Skink is out for now: no scripted pick clicks it.
        assert_eq!(demo_picks("t1,std,sk9_skink", &GameData::embedded()), None);
    }
}
