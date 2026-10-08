//! The main menu (mockups 04 and 04b, `design/ui/mockups/_src/pages/main_menu.html`): the agent backdrop, the
//! SHARD/LINE wordmark, the left nav (PLAY with HOST GAME / JOIN GAME, GUN RANGE, SETTINGS, QUIT; no LOADOUT for
//! now, DIRECTION_LOG 17: players pick their loadout in the lobby and from the ESC menu),
//! the PLAY flyout on the right of the nav (`host.rs`, `join.rs`), the player card, the agent tag, the key
//! hints and the version / network line.
//!
//! HOST GAME and JOIN GAME open as a modal over the dimmed menu, only when picked (a click, or Enter / Right
//! on the row); Esc, the CLOSE key cap or a click on the backdrop closes it. Focus has two zones, the nav
//! and the open modal: Up / Down move in the nav, Tab / Up / Down move inside the modal. Text fields get the keyboard through Bevy's `InputFocus` (see `field.rs`).

mod copy;
mod field;
mod host;
mod join;

use crate::AppState;
use crate::config::{Cli, Data};
use crate::loadout::{ActiveLoadout, summary};
use crate::net::{HostSettings, NetRequest, Session};
use crate::screens::{EscPress, EscSystems, Screen, Screens, SettingsTab};
use crate::ui_kit::*;
use crate::user_config::{PlayerProfile, RecentServers};
use bevy::input_focus::{FocusCause, InputFocus};
use bevy::prelude::*;
use bevy::text::{EditableText, FontFeatureTag, LetterSpacing};
use bevy::ui::{ColorStop, InterpolationColorSpace, LinearGradient};
use field::{FieldEditor, FieldId, FieldSpec};
use vetf_net::LoadoutChoice;

pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<MenuState>()
            .add_message::<MenuAction>()
            .add_systems(OnEnter(AppState::MainMenu), enter_menu)
            // The menu's fields go with it: do not leave the keyboard focused on a despawned field.
            .add_systems(OnExit(AppState::MainMenu), |mut input: ResMut<InputFocus>| input.clear())
            .add_systems(
                Update,
                (
                    // Not at OnEnter: the first OnEnter runs before Startup, which loads the images and
                    // the active loadout.
                    spawn_menu
                        .run_if(not(any_with_component::<MenuRoot>))
                        .run_if(resource_exists::<UiImages>)
                        .run_if(resource_exists::<ActiveLoadout>),
                    demo_ui,
                    follow_status,
                    follow_clicked_field,
                    clicks,
                    // The base under the screen stack: it only gets Esc while no screen is open.
                    keyboard.in_set(EscSystems::Base),
                    (nav_actions, host::actions, join::actions),
                    (host::keys, join::keys),
                    sync_input_focus,
                    (nav_visuals, ring_visuals, hints, refresh_bound, name_visuals, net_line),
                )
                    .chain()
                    .run_if(in_state(AppState::MainMenu)),
            );
        field::plugin(app);
        host::plugin(app);
        join::plugin(app);
    }
}

// ---------------------------------------------------------------------------------------------- state

/// The two PLAY flyouts.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub(crate) enum Sub {
    Host,
    #[default]
    Join,
}

/// JOIN GAME's tabs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub(crate) enum JoinTab {
    #[default]
    Code,
    Ip,
    Lan,
}

impl JoinTab {
    pub const ALL: [JoinTab; 3] = [JoinTab::Code, JoinTab::Ip, JoinTab::Lan];

    /// The tab's text field (none on ON YOUR NETWORK).
    pub fn field(self) -> Option<FieldId> {
        match self {
            JoinTab::Code => Some(FieldId::JoinCode),
            JoinTab::Ip => Some(FieldId::JoinIp),
            JoinTab::Lan => None,
        }
    }
}

/// The nav's rows, in keyboard order.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum NavItem {
    Play,
    Host,
    Join,
    GunRange,
    Settings,
    Quit,
}

impl NavItem {
    pub const ORDER: [NavItem; 6] =
        [NavItem::Play, NavItem::Host, NavItem::Join, NavItem::GunRange, NavItem::Settings, NavItem::Quit];

    /// The next (or previous) row, wrapping.
    pub fn step(self, delta: i32) -> NavItem {
        let i = Self::ORDER.iter().position(|n| *n == self).unwrap_or(0) as i32;
        Self::ORDER[(i + delta).rem_euclid(Self::ORDER.len() as i32) as usize]
    }

    /// The top-level row that shows the active bar while this row has focus (sub-items light PLAY).
    pub fn top(self) -> NavItem {
        match self {
            NavItem::Host | NavItem::Join => NavItem::Play,
            other => other,
        }
    }

    fn sub(sub: Sub) -> NavItem {
        match sub {
            Sub::Host => NavItem::Host,
            Sub::Join => NavItem::Join,
        }
    }
}

/// HOST GAME's focus order (the password is disabled, so it is skipped).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum HostItem {
    Name,
    Mode,
    Access,
    MaxPlayers,
    Port,
    Create,
}

/// JOIN GAME's focus order: tabs, field, PASTE, JOIN LOBBY, then the recent rows.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum JoinItem {
    Tabs,
    Input,
    Paste,
    Join,
    Row(usize),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Focus {
    Nav(NavItem),
    Host(HostItem),
    Join(JoinItem),
    EditName,
}

/// Where the main menu is (kept across visits, so the flyout and tab picked last stay open).
#[derive(Resource, Debug, Clone, PartialEq)]
pub(crate) struct MenuState {
    pub sub: Sub,
    pub tab: JoinTab,
    pub focus: Focus,
    /// Draw the focus ring: the last move was by keyboard.
    pub focus_visible: bool,
    pub selected_recent: Option<usize>,
    /// The HOST GAME / JOIN GAME modal (`sub`) is open.
    pub open: bool,
    /// Where focus goes back to after editing the name.
    pub before_edit: Focus,
}

impl Default for MenuState {
    fn default() -> Self {
        Self {
            sub: Sub::Join,
            tab: JoinTab::Code,
            focus: Focus::Nav(NavItem::Play),
            focus_visible: false,
            selected_recent: None,
            open: false,
            before_edit: Focus::Nav(NavItem::Play),
        }
    }
}

impl MenuState {
    /// The text field that has the keyboard, if focus is on one.
    /// Close the modal, back to its nav row.
    fn close_modal(&mut self) {
        self.open = false;
        self.focus = Focus::Nav(NavItem::sub(self.sub));
    }

    pub fn focused_field(&self) -> Option<FieldId> {
        match self.focus {
            Focus::Host(HostItem::Name) => Some(FieldId::LobbyName),
            Focus::Host(HostItem::Port) => Some(FieldId::Port),
            Focus::Join(JoinItem::Input) => self.tab.field(),
            Focus::EditName => Some(FieldId::PlayerName),
            _ => None,
        }
    }

    /// Open the modal on its first stop.
    fn enter_flyout(&mut self) {
        self.open = true;
        self.focus = match self.sub {
            Sub::Host => Focus::Host(HostItem::Name),
            Sub::Join if self.tab == JoinTab::Lan => Focus::Join(JoinItem::Tabs),
            Sub::Join => Focus::Join(JoinItem::Input),
        };
    }
}

/// What a click or a key asks for.
#[derive(Message, Debug, Clone, Copy, PartialEq)]
pub(crate) enum MenuAction {
    Nav(NavItem),
    CreateLobby,
    JoinLobby,
    Paste,
    Tab(JoinTab),
    PickRecent(usize),
    JoinRecent(usize),
    EditName,
    SaveName,
    CancelName,
    CloseModal,
}

// ---------------------------------------------------------------------------------------------- markers

#[derive(Component)]
struct MenuRoot;

/// A clickable element and what it does.
#[derive(Component, Debug, Clone, Copy)]
pub(crate) struct Click(pub MenuAction);

/// Clicking this element moves focus here.
#[derive(Component, Debug, Clone, Copy)]
pub(crate) struct FocusTarget(pub Focus);

/// This element draws the teal focus ring while `Focus` has keyboard focus.
#[derive(Component, Debug, Clone, Copy)]
pub(crate) struct FocusRing(pub Focus);

#[derive(Component, Debug, Clone, Copy)]
struct NavRow(NavItem);

#[derive(Component, Debug, Clone, Copy)]
struct SubDiamond(Sub);

/// The dimmed layer the HOST GAME / JOIN GAME modal sits on.
#[derive(Component)]
struct ModalLayer;

/// A PLAY flyout panel.
#[derive(Component, Debug, Clone, Copy)]
pub(crate) struct Flyout(pub Sub);

#[derive(Component)]
struct NameText;

#[derive(Component)]
struct NameEdit;

#[derive(Component)]
struct HintRow(Option<HintMode>);

/// The mockups keep ↑↓ SELECT · ENTER CONFIRM · ESC BACK while a flyout field is focused; only editing the
/// name (no mockup) shows its own keys.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum HintMode {
    Nav,
    Name,
}

#[derive(Component)]
struct NetLine(u16);

/// Content drawn from the active loadout (in HOST GAME's mode); rebuilt when either changes.
#[derive(Component)]
struct LoadoutBound(Option<(LoadoutChoice, vetf_net::MatchMode)>, Bound);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Bound {
    Gear,
    Lines,
    Halo,
}

/// ESC CLOSE in the modal's top-right corner (clickable, like the backdrop).
pub(crate) fn close_button(p: &mut ChildSpawnerCommands, fonts: &UiFonts) {
    p.spawn((
        Button,
        Click(MenuAction::CloseModal),
        Node { column_gap: px(7), align_items: AlignItems::Center, ..abs(None, Some(24.0), Some(26.0), None) },
    ))
    .with_children(|b| {
        b.spawn(keycap(fonts, "Esc", KeyStyle::Ghost, 20.0));
        b.spawn(fonts.role(TextRole::Hint, "Close"));
    });
}

/// The keyboard focus ring (teal, 2 px, 2 px out).
pub(crate) fn ring() -> Outline {
    Outline::new(px(2), px(2), Color::NONE)
}

// ---------------------------------------------------------------------------------------------- spawn

fn enter_menu(mut state: ResMut<MenuState>, session: Res<Session>) {
    state.focus = Focus::Nav(NavItem::Play);
    state.focus_visible = false;
    state.selected_recent = None;
    state.open = false;
    if session.host_error {
        state.sub = Sub::Host;
        state.enter_flyout();
    } else if session.status.is_some() {
        // Show why we are back (disconnected, timed out) where the player rejoins.
        state.sub = Sub::Join;
        if state.tab == JoinTab::Lan {
            state.tab = JoinTab::Code;
        }
        state.enter_flyout();
    }
}

#[allow(clippy::too_many_arguments)]
fn spawn_menu(
    mut commands: Commands,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    data: Res<Data>,
    session: Res<Session>,
    host: Res<HostSettings>,
    recent: Res<RecentServers>,
    state: Res<MenuState>,
) {
    let ctx = Ctx { fonts: &fonts, images: &images, data: &data };
    commands
        .spawn((
            MenuRoot,
            DespawnOnExit(AppState::MainMenu),
            Node { width: percent(100), height: percent(100), overflow: Overflow::clip(), ..default() },
            BackgroundColor(BG0),
        ))
        .with_children(|r| {
            backdrop(r, &images);
            r.spawn(shade());
            logo(r, &fonts);
            nav(r, &fonts);
            player_card(r, &ctx, &session);
            agent_tag(r, &ctx);
            version(r, &fonts);
            // HOST GAME / JOIN GAME: a modal over the dimmed menu; a click on the backdrop closes it.
            r.spawn((
                ModalLayer,
                Button,
                Click(MenuAction::CloseModal),
                ZIndex(10),
                Node {
                    display: if state.open { Display::Flex } else { Display::None },
                    width: percent(100),
                    height: percent(100),
                    justify_content: JustifyContent::Center,
                    align_items: AlignItems::Center,
                    ..abs(Some(0.0), None, Some(0.0), None)
                },
                BackgroundColor(MODAL_BACKDROP),
            ))
            .with_children(|m| {
                host::spawn_flyout(m, &ctx, &host, &session, &state);
                join::spawn_flyout(m, &ctx, &recent, &state);
            });
            // The key hints stay readable over the backdrop.
            r.spawn((
                HintRow(None),
                ZIndex(20),
                Node {
                    justify_content: JustifyContent::Center,
                    align_items: AlignItems::Center,
                    column_gap: px(22),
                    ..abs(Some(0.0), Some(0.0), None, Some(28.0))
                },
            ));
        });
}

/// What the spawn helpers share.
pub(crate) struct Ctx<'a> {
    pub fonts: &'a UiFonts,
    pub images: &'a UiImages,
    pub data: &'a Data,
}

/// The agent art, full-bleed and centred like CSS `cover` at any aspect ratio.
fn backdrop(r: &mut ChildSpawnerCommands, images: &UiImages) {
    r.spawn((
        ImageNode::new(images.art(Art::MenuKestrel)),
        Node {
            position_type: PositionType::Absolute,
            left: percent(50),
            top: percent(50),
            width: Val::Vw(100.0),
            min_width: Val::Vh(100.0 * 16.0 / 9.0),
            min_height: Val::Vh(100.0),
            aspect_ratio: Some(16.0 / 9.0),
            ..default()
        },
        UiTransform::from_translation(Val2::percent(-50.0, -50.0)),
    ));
}

/// The shade stops of the mockup's CSS (position %, alpha of rgb(5,7,10)): left to right, bottom to top.
const SHADE_X: [(f32, f32); 4] = [(0.0, 0.96), (30.0, 0.88), (56.0, 0.35), (72.0, 0.0)];
const SHADE_Y: [(f32, f32); 2] = [(0.0, 0.85), (26.0, 0.0)];

/// The two shades over the art: dark on the left for the nav and flyout, dark at the bottom for the card
/// and hints.
fn shade() -> impl Bundle {
    // A dark shade over the art: the kit converts the CSS alphas (resampled, so the curve holds between stops).
    let stops = |s: &[(f32, f32)]| {
        scrim_stops(s, 2.0).into_iter().map(|(t, a)| ColorStop::new(hexa_exact(INK, a), percent(t))).collect()
    };
    let horizontal = LinearGradient::to_right(stops(&SHADE_X)).in_color_space(InterpolationColorSpace::Srgba);
    let bottom = LinearGradient::to_top(stops(&SHADE_Y)).in_color_space(InterpolationColorSpace::Srgba);
    (
        Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
        BackgroundGradient(vec![horizontal.into(), bottom.into()]),
    )
}

fn logo(r: &mut ChildSpawnerCommands, fonts: &UiFonts) {
    let role = TextRole::Wordmark;
    let span = |s: &str, color: Color| {
        (
            TextSpan::new(s),
            fonts.role_font(role),
            TextColor(color),
            LetterSpacing::Px(role.spacing_px()),
            role.spec().line,
        )
    };
    r.spawn(Node { flex_direction: FlexDirection::Column, ..abs(Some(96.0), None, Some(72.0), None) }).with_children(
        |l| {
            l.spawn(fonts.role(role, "SHARD")).with_children(|w| {
                w.spawn(span("/", TEAL));
                w.spawn(span("LINE", TEXT_HI));
            });
            l.spawn(Node {
                margin: UiRect::top(px(6)),
                column_gap: px(10),
                align_items: AlignItems::Center,
                ..default()
            })
            .with_children(|t| {
                t.spawn((Node { width: px(40), height: px(2), ..default() }, BackgroundColor(TEAL)));
                t.spawn(fonts.lbl(copy::tagline()));
            });
        },
    );
}

fn nav(r: &mut ChildSpawnerCommands, fonts: &UiFonts) {
    let top = |label: &'static str, right: &'static str, item: NavItem| {
        let (size, looks) = if item == NavItem::Quit { (NavSize::Quit, NAV_QUIT) } else { (NavSize::Xl, NAV) };
        (nav_row(fonts, label, right, size, looks, TEAL), NavRow(item), Click(MenuAction::Nav(item)))
    };
    let sub = |label: &'static str, which: Sub| {
        let item = NavItem::sub(which);
        (
            Button,
            Node { height: px(44), column_gap: px(12), align_items: AlignItems::Center, ..default() },
            Looks::ink(TEXT_MID, TEXT_HI, TEXT_HI),
            Active(false),
            NavRow(item),
            Click(MenuAction::Nav(item)),
            children![
                (
                    SubDiamond(which),
                    Node { width: px(10), height: px(10), border: UiRect::all(px(1)), ..default() },
                    BackgroundColor(Color::NONE),
                    BorderColor::all(TEXT_LOW),
                    UiTransform::from_rotation(Rot2::degrees(45.0)),
                ),
                (fonts.role(TextRole::NavSub, label), Ink),
            ],
        )
    };
    r.spawn(Node { width: px(400), flex_direction: FlexDirection::Column, ..abs(Some(96.0), None, Some(300.0), None) })
        .with_children(|n| {
            n.spawn(top("Play", "Host · Join", NavItem::Play));
            n.spawn(Node {
                flex_direction: FlexDirection::Column,
                padding: UiRect { left: px(44), top: px(2), bottom: px(12), right: px(0) },
                ..default()
            })
            .with_children(|s| {
                s.spawn(sub("Host game", Sub::Host));
                s.spawn(sub("Join game", Sub::Join));
            });
            // The range is a listen server too: friends can join it (the mockup's OFFLINE is wrong here).
            n.spawn(top("Gun range", "Friends can join", NavItem::GunRange));
            // No LOADOUT for now (DIRECTION_LOG 17): the lobby's LOADOUT and the ESC menu open it.
            n.spawn(top("Settings", "", NavItem::Settings));
            n.spawn(Node { height: px(18), ..default() });
            n.spawn(top("Quit", "", NavItem::Quit));
        });
}

fn player_card(r: &mut ChildSpawnerCommands, ctx: &Ctx, session: &Session) {
    let fonts = ctx.fonts;
    r.spawn(panel(Node {
        column_gap: px(16),
        align_items: AlignItems::Center,
        padding: UiRect { left: px(12), right: px(18), top: px(12), bottom: px(12) },
        max_width: px(700),
        ..abs(Some(96.0), None, None, Some(60.0))
    }))
    .with_children(|c| {
        c.spawn((
            ImageNode::new(ctx.images.shape(Shape::KestrelHex)),
            Node { width: px(64), height: px(64), flex_shrink: 0.0, ..default() },
        ));
        c.spawn(Node {
            flex_direction: FlexDirection::Column,
            min_width: px(0),
            overflow: Overflow::clip(),
            ..default()
        })
        .with_children(|col| {
            // Name, EDIT NAME and the gear budget share a baseline (Bevy has no text baselines in flex,
            // so the small texts sit on the name's baseline by margin).
            col.spawn(Node { align_items: AlignItems::FlexEnd, ..default() }).with_children(|line| {
                line.spawn((
                    Button,
                    Node::default(),
                    Click(MenuAction::EditName),
                    children![(NameText, fonts.role(TextRole::PlayerName, session.local_name.clone()))],
                ));
                let spec = FieldSpec {
                    id: FieldId::PlayerName,
                    role: TextRole::PlayerName,
                    em: None,
                    tnum: false,
                    placeholder: String::new(),
                    max_chars: PlayerProfile::MAX_NAME,
                    filter: Some(PlayerProfile::name_char_ok),
                    initial: session.local_name.clone(),
                    display: None,
                };
                let edit = field::spawn_field(
                    line,
                    fonts,
                    spec,
                    (
                        Node {
                            display: Display::None,
                            width: px(270),
                            height: px(29),
                            align_items: AlignItems::Center,
                            border: UiRect::bottom(px(1)),
                            ..default()
                        },
                        BorderColor::all(STROKE_HI),
                    ),
                    |_| {},
                );
                line.commands().entity(edit).insert(NameEdit);
                line.spawn((
                    Button,
                    Node { margin: UiRect { left: px(7), bottom: px(2.6), ..default() }, ..default() },
                    Looks::ink(TEXT_LOW, TEXT_MID, TEXT_MID),
                    Click(MenuAction::EditName),
                    children![(fonts.micro("Edit name"), Ink)],
                ));
                line.spawn((
                    LoadoutBound(None, Bound::Gear),
                    Node {
                        margin: UiRect { left: px(14), bottom: px(2.2), ..default() },
                        column_gap: px(5),
                        align_items: AlignItems::FlexEnd,
                        ..default()
                    },
                ));
            });
            col.spawn((LoadoutBound(None, Bound::Lines), Node { flex_direction: FlexDirection::Column, ..default() }));
        });
    });
}

fn agent_tag(r: &mut ChildSpawnerCommands, ctx: &Ctx) {
    let fonts = ctx.fonts;
    r.spawn(Node {
        flex_direction: FlexDirection::Column,
        align_items: AlignItems::FlexEnd,
        ..abs(None, Some(120.0), None, Some(120.0))
    })
    .with_children(|a| {
        // Static until agents exist: the backdrop shows Kestrel.
        a.spawn(fonts.role(TextRole::RoleLine, "Recon · Mobility"));
        a.spawn(fonts.role(TextRole::AgentXl, "Kestrel"));
        a.spawn((
            LoadoutBound(None, Bound::Halo),
            Node {
                margin: UiRect::top(px(10)),
                column_gap: px(10),
                align_items: AlignItems::Center,
                justify_content: JustifyContent::FlexEnd,
                ..default()
            },
        ));
    });
}

fn version(r: &mut ChildSpawnerCommands, fonts: &UiFonts) {
    r.spawn(Node {
        flex_direction: FlexDirection::Column,
        align_items: AlignItems::FlexEnd,
        ..abs(None, Some(40.0), None, Some(28.0))
    })
    .with_children(|v| {
        v.spawn(fonts.micro(copy::version_line()));
        v.spawn((NetLine(0), fonts.micro(""), Node { margin: UiRect::top(px(3)), ..default() })).with_children(|l| {
            l.spawn((
                TextSpan::new(""),
                fonts.role_font(TextRole::Micro),
                TextColor(TEXT_LOW),
                LetterSpacing::Px(TextRole::Micro.spacing_px()),
            ));
        });
    });
}

// ---------------------------------------------------------------------------------------------- input

/// `--demo-ui menu-join | menu-join-ip | menu-host`: open a flyout with a field focused, for screenshots.
fn demo_ui(
    cli: Res<Cli>,
    mut state: ResMut<MenuState>,
    mut editors: Query<(&FieldEditor, &mut EditableText)>,
    roots: Query<(), With<MenuRoot>>,
    mut done: Local<bool>,
) {
    let Some(demo) = cli.demo_ui.as_deref() else { return };
    if *done || roots.is_empty() || cli.host.is_some() || cli.join.is_some() {
        return;
    }
    *done = true;
    match demo {
        "menu-join" => {
            state.sub = Sub::Join;
            state.tab = JoinTab::Code;
            state.open = true;
            state.focus = Focus::Join(JoinItem::Input);
            // A real-format SL1 internet invite (the field shows it short); the mockup's sample is an old
            // 8-character code.
            let code = crate::iroh_transport::invite(iroh::SecretKey::from_bytes(&[0x3A; 32]).public());
            for (id, mut ed) in &mut editors {
                if id.0 == FieldId::JoinCode {
                    field::set_value(&mut ed, &code);
                }
            }
        }
        "menu-join-ip" => {
            state.sub = Sub::Join;
            state.tab = JoinTab::Ip;
            state.open = true;
            state.focus = Focus::Join(JoinItem::Input);
        }
        "menu-host" => {
            state.sub = Sub::Host;
            state.open = true;
            state.focus = Focus::Host(HostItem::Name);
        }
        _ => {}
    }
}

/// A new error opens the flyout that shows it: HOST GAME for a hosting failure (a busy port, also from
/// `--host`), JOIN GAME for anything else.
fn follow_status(session: Res<Session>, mut state: ResMut<MenuState>, mut last: Local<Option<String>>) {
    if session.status == *last {
        return;
    }
    last.clone_from(&session.status);
    if session.status.is_none() {
        return;
    }
    let sub = if session.host_error { Sub::Host } else { Sub::Join };
    if sub == Sub::Join && state.tab == JoinTab::Lan {
        state.tab = JoinTab::Code;
    }
    if state.sub != sub || !state.open {
        state.sub = sub;
        state.enter_flyout();
    }
}

/// A click into a text field (Bevy focuses it) moves the menu's focus there.
fn follow_clicked_field(
    input: Res<InputFocus>,
    editors: Query<&FieldEditor>,
    mut state: ResMut<MenuState>,
    screens: Res<Screens>,
) {
    if !input.is_changed() || !screens.is_empty() {
        return;
    }
    let Some(id) = input.get().and_then(|e| editors.get(e).ok()) else { return };
    let focus = match id.0 {
        FieldId::JoinCode | FieldId::JoinIp => Focus::Join(JoinItem::Input),
        FieldId::LobbyName => Focus::Host(HostItem::Name),
        FieldId::Port => Focus::Host(HostItem::Port),
        FieldId::PlayerName => Focus::EditName,
    };
    if state.focus != focus {
        state.focus = focus;
        state.focus_visible = false;
    }
}

/// The text field the menu's focus is on gets the keyboard; no field has it while an overlay is open.
fn sync_input_focus(
    state: Res<MenuState>,
    screens: Res<Screens>,
    editors: Query<(Entity, &FieldEditor)>,
    mut input: ResMut<InputFocus>,
) {
    let want_id = if screens.is_empty() { state.focused_field() } else { None };
    let want = want_id.and_then(|id| editors.iter().find(|(_, f)| f.0 == id).map(|(e, _)| e));
    let current = input.get();
    match want {
        Some(e) if current != Some(e) => input.set(e, FocusCause::Navigated),
        None if current.is_some_and(|c| editors.contains(c)) => input.clear(),
        _ => {}
    }
}

/// Mouse clicks: run the element's action and move focus to it.
fn clicks(
    q: Query<
        (&Interaction, Option<&Click>, Option<&FocusTarget>, Has<Disabled>),
        (Changed<Interaction>, Or<(With<Click>, With<FocusTarget>)>),
    >,
    mut state: ResMut<MenuState>,
    mut actions: MessageWriter<MenuAction>,
    screens: Res<Screens>,
    time: Res<Time>,
    mut last_pick: Local<Option<(usize, f32)>>,
) {
    if !screens.is_empty() {
        return;
    }
    let now = time.elapsed_secs();
    for (interaction, click, target, disabled) in &q {
        if *interaction != Interaction::Pressed || disabled {
            continue;
        }
        if let Some(FocusTarget(f)) = target {
            state.focus = *f;
            state.focus_visible = false;
        }
        let Some(Click(action)) = click else { continue };
        // A second click on the same recent row joins it.
        let action = match *action {
            MenuAction::PickRecent(i) => {
                let double = last_pick.is_some_and(|(j, t)| j == i && now - t < 0.45);
                *last_pick = Some((i, now));
                if double { MenuAction::JoinRecent(i) } else { MenuAction::PickRecent(i) }
            }
            other => other,
        };
        actions.write(action);
    }
}

/// Keyboard: ↑↓ select, Enter confirm, Esc back, Tab / Shift+Tab inside a flyout.
fn keyboard(
    keys: Res<ButtonInput<KeyCode>>,
    mut esc_press: ResMut<EscPress>,
    mut state: ResMut<MenuState>,
    mut actions: MessageWriter<MenuAction>,
    recent: Res<RecentServers>,
    screens: Res<Screens>,
    mut live: Local<bool>,
) {
    // Not while an overlay is open, nor on the frame it closes (the Enter or click that closed it must
    // not act on the menu too; Esc cannot, the screen stack used it).
    let open = screens.is_empty();
    let was_open = std::mem::replace(&mut *live, open);
    if !open || !was_open {
        return;
    }
    let shift = keys.any_pressed([KeyCode::ShiftLeft, KeyCode::ShiftRight]);
    let tab = keys.just_pressed(KeyCode::Tab);
    let next = keys.just_pressed(KeyCode::ArrowDown) || (tab && !shift);
    let prev = keys.just_pressed(KeyCode::ArrowUp) || (tab && shift);
    let enter = keys.any_just_pressed([KeyCode::Enter, KeyCode::NumpadEnter]);
    // The menu is the last stop for Esc (name edit: cancel; flyout: back to the nav; nav: nothing).
    let esc = esc_press.take();
    let right = keys.just_pressed(KeyCode::ArrowRight);
    if !(next || prev || enter || esc || right) {
        return;
    }
    let delta = if next { 1 } else { -1 };
    match state.focus {
        Focus::EditName => {
            if enter {
                actions.write(MenuAction::SaveName);
            } else if esc {
                actions.write(MenuAction::CancelName);
            }
            return;
        }
        Focus::Nav(item) => {
            if next || prev {
                let item = item.step(delta);
                state.focus = Focus::Nav(item);
                // Moving onto a sub-item picks it (its diamond); Enter opens it.
                match item {
                    NavItem::Host => state.sub = Sub::Host,
                    NavItem::Join => state.sub = Sub::Join,
                    _ => {}
                }
            } else if enter || (right && matches!(item, NavItem::Host | NavItem::Join | NavItem::Play)) {
                actions.write(MenuAction::Nav(item));
            }
        }
        Focus::Host(item) => {
            if esc {
                state.close_modal();
            } else if next || prev {
                state.focus = Focus::Host(host::step(item, delta));
            } else if enter {
                actions.write(MenuAction::CreateLobby);
            }
        }
        Focus::Join(item) => {
            let rows = join::visible_rows(&recent);
            if esc {
                state.close_modal();
            } else if next || prev {
                state.focus = Focus::Join(join::step(item, delta, state.tab, rows));
            } else if enter {
                match item {
                    JoinItem::Tabs if state.tab != JoinTab::Lan => state.focus = Focus::Join(JoinItem::Input),
                    JoinItem::Tabs => {}
                    JoinItem::Input | JoinItem::Join => {
                        actions.write(MenuAction::JoinLobby);
                    }
                    JoinItem::Paste => {
                        actions.write(MenuAction::Paste);
                    }
                    JoinItem::Row(i) => {
                        actions.write(MenuAction::JoinRecent(i));
                    }
                }
            }
        }
    }
    if next || prev || esc || right {
        state.focus_visible = true;
    }
}

/// The nav rows' and the name's actions.
#[allow(clippy::too_many_arguments)]
fn nav_actions(
    mut actions: MessageReader<MenuAction>,
    mut state: ResMut<MenuState>,
    mut requests: MessageWriter<NetRequest>,
    mut screens: ResMut<Screens>,
    mut exit: MessageWriter<AppExit>,
    mut session: ResMut<Session>,
    mut profile: ResMut<PlayerProfile>,
    mut editors: Query<(&FieldEditor, &mut EditableText)>,
) {
    for action in actions.read() {
        match *action {
            MenuAction::Nav(NavItem::Play) => state.focus = Focus::Nav(NavItem::sub(state.sub)),
            MenuAction::Nav(NavItem::Host) => {
                state.sub = Sub::Host;
                state.enter_flyout();
            }
            MenuAction::Nav(NavItem::Join) => {
                state.sub = Sub::Join;
                state.enter_flyout();
            }
            MenuAction::Nav(NavItem::GunRange) => {
                state.focus = Focus::Nav(NavItem::GunRange);
                requests.write(NetRequest::Host { map: "range".into(), lobby: false });
            }
            MenuAction::Nav(NavItem::Settings) => {
                state.focus = Focus::Nav(NavItem::Settings);
                screens.push(Screen::Settings(SettingsTab::Gameplay));
            }
            MenuAction::Nav(NavItem::Quit) => {
                exit.write(AppExit::Success);
            }
            MenuAction::EditName if state.focus != Focus::EditName => {
                state.before_edit = state.focus;
                state.focus = Focus::EditName;
                for (id, mut ed) in &mut editors {
                    if id.0 == FieldId::PlayerName {
                        field::set_value(&mut ed, &session.local_name);
                    }
                }
            }
            MenuAction::SaveName => {
                let typed =
                    editors.iter().find(|(id, _)| id.0 == FieldId::PlayerName).map(|(_, e)| e.value().to_string());
                if let Some(name) = typed.as_deref().and_then(PlayerProfile::clean_name) {
                    // Hello carries the name, so it must be set before connecting.
                    session.local_name.clone_from(&name);
                    profile.name = name;
                    if let Err(e) = crate::user_config::save(PlayerProfile::FILE, &*profile) {
                        warn!("cannot save the player name: {e}");
                    }
                }
                state.focus = state.before_edit;
            }
            MenuAction::CancelName => state.focus = state.before_edit,
            MenuAction::CloseModal => state.close_modal(),
            _ => {}
        }
    }
}

// ---------------------------------------------------------------------------------------------- visuals

#[allow(clippy::type_complexity)]
fn nav_visuals(
    state: Res<MenuState>,
    mut rows: Query<(&NavRow, &mut Active)>,
    mut diamonds: Query<(&SubDiamond, &mut BackgroundColor, &mut BorderColor, &mut Node), Without<Flyout>>,
    mut flyouts: Query<(&Flyout, &mut Node), Without<ModalLayer>>,
    mut layer: Query<&mut Node, (With<ModalLayer>, Without<Flyout>, Without<SubDiamond>)>,
) {
    if !state.is_changed() {
        return;
    }
    let top = match state.focus {
        Focus::Nav(item) => item.top(),
        _ => NavItem::Play,
    };
    for (row, mut on) in &mut rows {
        let want = match row.0 {
            NavItem::Host => state.sub == Sub::Host,
            NavItem::Join => state.sub == Sub::Join,
            item => item == top,
        };
        if on.0 != want {
            on.0 = want;
        }
    }
    for (d, mut bg, mut border, mut node) in &mut diamonds {
        let on = d.0 == state.sub;
        bg.0 = if on { TEXT_HI } else { Color::NONE };
        *border = BorderColor::all(if on { TEXT_HI } else { TEXT_LOW });
        // The mockup's hollow diamond is a ::before pseudo-element, which the page's `* { box-sizing:
        // border-box }` does not reach: 10 px plus its 1 px border, so it is 12 px and its label sits 2 px
        // further right.
        let size = px(if on { 10 } else { 12 });
        if node.width != size {
            node.width = size;
            node.height = size;
        }
    }
    for (f, mut node) in &mut flyouts {
        node.display = if f.0 == state.sub { Display::Flex } else { Display::None };
    }
    for mut node in &mut layer {
        node.display = if state.open { Display::Flex } else { Display::None };
    }
}

fn ring_visuals(state: Res<MenuState>, mut rings: Query<(&FocusRing, &mut Outline)>) {
    if !state.is_changed() {
        return;
    }
    for (r, mut o) in &mut rings {
        let want = if state.focus_visible && state.focus == r.0 { TEAL } else { Color::NONE };
        if o.color != want {
            o.color = want;
        }
    }
}

/// The footer hints: ↑↓ SELECT · ENTER CONFIRM · ESC BACK (ENTER SAVE · ESC CANCEL while editing the name).
fn hints(
    state: Res<MenuState>,
    mut rows: Query<(Entity, &mut HintRow)>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    mut commands: Commands,
) {
    let mode = if state.focus == Focus::EditName { HintMode::Name } else { HintMode::Nav };
    for (e, mut row) in &mut rows {
        if row.0 == Some(mode) {
            continue;
        }
        row.0 = Some(mode);
        let items: Vec<(&str, &str)> = match mode {
            HintMode::Nav => vec![("↑↓", "Select"), ("Enter", "Confirm"), ("Esc", "Back")],
            HintMode::Name => vec![("Enter", "Save"), ("Esc", "Cancel")],
        };
        commands.entity(e).despawn_children().with_children(|h| {
            for (key, label) in items {
                h.spawn(Node { column_gap: px(7), align_items: AlignItems::Center, ..default() }).with_children(|i| {
                    if key == "↑↓" {
                        // Barlow has no arrows: an icon in a 28-wide ghost cap.
                        i.spawn((
                            Node {
                                width: px(28),
                                height: px(22),
                                border: UiRect::all(px(1)),
                                border_radius: BorderRadius::all(px(2)),
                                align_items: AlignItems::Center,
                                justify_content: JustifyContent::Center,
                                ..default()
                            },
                            BorderColor::all(STROKE_HI),
                            children![(
                                ImageNode::new(images.shape(Shape::KeyUpDown)).with_color(TEXT_HI),
                                Node { width: px(12), height: px(16), ..default() },
                            )],
                        ));
                    } else {
                        i.spawn(keycap(&fonts, key, KeyStyle::Ghost, 22.0));
                    }
                    i.spawn(fonts.role(TextRole::Hint, label));
                });
            }
        });
    }
}

/// Rebuild what shows the active loadout when it changes, as the mode HOST GAME is set to takes it (team
/// deathmatch and free-for-all: one halo, one ammo type).
fn refresh_bound(
    active: Res<ActiveLoadout>,
    host: Res<HostSettings>,
    mut bound: Query<(Entity, &mut LoadoutBound)>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    data: Res<Data>,
    mut commands: Commands,
) {
    for (e, mut b) in &mut bound {
        let shown = (active.0.clone(), host.mode);
        if b.0.as_ref() == Some(&shown) {
            continue;
        }
        b.0 = Some(shown);
        let s = summary(&active.0, &data, host.mode);
        let mut ec = commands.entity(e);
        ec.despawn_children();
        match b.1 {
            Bound::Gear => {
                let (numbers, over) = copy::gear_text(s.gear_cost, s.gear_budget);
                let mut font = fonts.font(Face::Display, 700, 13.0);
                font.font_features = [FontFeatureTag::TABULAR_FIGURES].into();
                let color = if over { BAD } else { TEXT_HI };
                ec.with_children(|g| {
                    g.spawn((
                        fonts.role_color(TextRole::Micro, "Gear", TEXT_MID),
                        Node { margin: UiRect::bottom(px(0.4)), ..default() },
                    ));
                    g.spawn((Text::new(numbers), font, TextColor(color)));
                    if over {
                        g.spawn((
                            fonts.role_color(TextRole::Micro, "· Over budget", BAD),
                            Node { margin: UiRect::bottom(px(0.4)), ..default() },
                        ));
                    }
                });
            }
            Bound::Lines => {
                let line = copy::loadout_line(&active.0, &s, &data);
                let slots = copy::mag_slots(&s);
                let one_ammo = s.one_ammo().filter(|_| s.one_halo);
                ec.with_children(|l| {
                    l.spawn((
                        fonts.role(TextRole::CardLine, line),
                        TextLayout::no_wrap(),
                        Node { margin: UiRect::top(px(2)), ..default() },
                    ));
                    // One ammo type (team deathmatch, free-for-all): AMMO AP II x 4.
                    if let Some((label, kind, n)) = one_ammo {
                        l.spawn(Node {
                            margin: UiRect::top(px(2)),
                            height: px(15),
                            align_items: AlignItems::Center,
                            column_gap: px(8),
                            ..default()
                        })
                        .with_children(|m| {
                            m.spawn(fonts.micro("Ammo"));
                            m.spawn(fonts.text(label, Face::Display, 700, 12.0, ammo_color(kind), 0.5 / 12.0));
                            m.spawn(fonts.text(copy::mags_count(n), Face::Display, 600, 12.0, TEXT_LOW, 0.0));
                        });
                        return;
                    }
                    // MAGS: the six slots in order, so the player sees where the good magazines sit.
                    l.spawn(Node {
                        margin: UiRect::top(px(2)),
                        height: px(15),
                        align_items: AlignItems::Center,
                        column_gap: px(10),
                        ..default()
                    })
                    .with_children(|m| {
                        m.spawn((fonts.micro("Mags"), Node { margin: UiRect::right(px(-2)), ..default() }));
                        for (i, slot) in slots.iter().enumerate() {
                            m.spawn(Node { column_gap: px(3), align_items: AlignItems::Center, ..default() })
                                .with_children(|e| {
                                    e.spawn(fonts.text((i + 1).to_string(), Face::Display, 600, 12.0, TEXT_LOW, 0.0));
                                    match slot {
                                        Some((label, kind)) => {
                                            e.spawn(fonts.text(
                                                label.clone(),
                                                Face::Display,
                                                700,
                                                12.0,
                                                ammo_color(*kind),
                                                0.5 / 12.0,
                                            ));
                                        }
                                        None => {
                                            e.spawn(fonts.text("—", Face::Display, 700, 12.0, TEXT_LOW, 0.0));
                                        }
                                    }
                                });
                        }
                    });
                });
            }
            Bound::Halo => {
                let micro = copy::agent_micro(&s);
                ec.with_children(|h| {
                    if let Some((label, tier)) = copy::agent_halo(&s) {
                        h.spawn(Node { column_gap: px(4), align_items: AlignItems::Center, ..default() })
                            .with_children(|c| {
                                // Every arc in its own tier colour (the unified halo summary), not the mockup's N pips.
                                c.spawn(arc_chip(&images, s.tiers));
                                c.spawn(fonts.role_color(TextRole::TierText, label, tier_color(tier)));
                            });
                    }
                    h.spawn(fonts.role_color(TextRole::Micro, micro, TEXT_MID));
                });
            }
        }
    }
}

/// The name on the player card, and its editor while editing.
fn name_visuals(
    state: Res<MenuState>,
    session: Res<Session>,
    mut names: Query<(&mut Text, &ChildOf), With<NameText>>,
    mut nodes: Query<&mut Node>,
    edits: Query<Entity, With<NameEdit>>,
) {
    if !state.is_changed() && !session.is_changed() {
        return;
    }
    let editing = state.focus == Focus::EditName;
    for (mut t, parent) in &mut names {
        if t.0 != session.local_name {
            t.0.clone_from(&session.local_name);
        }
        if let Ok(mut n) = nodes.get_mut(parent.parent()) {
            n.display = if editing { Display::None } else { Display::Flex };
        }
    }
    for e in &edits {
        if let Ok(mut n) = nodes.get_mut(e) {
            n.display = if editing { Display::Flex } else { Display::None };
        }
    }
}

/// Version line 2: the port to host on and this machine's LAN address.
fn net_line(
    host: Res<HostSettings>,
    mut lines: Query<(&mut NetLine, &mut Text, &Children)>,
    mut spans: Query<(&mut TextSpan, &mut TextColor)>,
) {
    for (mut line, mut text, kids) in &mut lines {
        if line.0 == host.port {
            continue;
        }
        line.0 = host.port;
        let (head, tail, warn) = copy::network_line(host.port, crate::net::local_ipv4());
        text.0 = head.to_uppercase();
        for k in kids.iter() {
            if let Ok((mut span, mut color)) = spans.get_mut(k) {
                span.0 = tail.to_uppercase();
                color.0 = if warn { WARN } else { TEXT_LOW };
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_nav_wraps_and_sub_items_light_play() {
        assert_eq!(NavItem::Play.step(1), NavItem::Host);
        assert_eq!(NavItem::Play.step(-1), NavItem::Quit);
        assert_eq!(NavItem::Quit.step(1), NavItem::Play);
        assert_eq!(NavItem::Join.top(), NavItem::Play);
        assert_eq!(NavItem::Settings.top(), NavItem::Settings);
    }

    #[test]
    fn focus_names_the_field_with_the_keyboard() {
        let mut s = MenuState::default();
        assert_eq!(s.focused_field(), None);
        s.sub = Sub::Join;
        s.enter_flyout();
        assert_eq!(s.focused_field(), Some(FieldId::JoinCode));
        s.tab = JoinTab::Ip;
        assert_eq!(s.focused_field(), Some(FieldId::JoinIp));
        s.tab = JoinTab::Lan;
        s.enter_flyout();
        assert_eq!(s.focus, Focus::Join(JoinItem::Tabs), "nothing to type on ON YOUR NETWORK");
        s.sub = Sub::Host;
        s.enter_flyout();
        assert_eq!(s.focused_field(), Some(FieldId::LobbyName));
    }
}
