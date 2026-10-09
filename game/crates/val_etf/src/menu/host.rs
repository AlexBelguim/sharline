//! PLAY > HOST GAME (mockup 04b): lobby name, mode (team deathmatch or free-for-all), who can join, max
//! players, tick rate and snapshot rate (with the upload they cost), port and password, then CREATE LOBBY, which
//! opens the lobby on Showhome. The values live in [`HostSettings`] (kept across menu visits; the gun range hosts
//! with them too, always as the range).

use super::field::{self, Field, FieldEditor, FieldId, FieldSpec};
use super::{Click, Ctx, Focus, FocusRing, FocusTarget, HostItem, MenuAction, MenuState, Sub, copy, ring};
use crate::AppState;
use crate::net::{
    HostSettings, JoinAccess, NetRequest, Session, default_lobby_name, max_players_cap_for, parse_host_port,
};
use crate::screens::Screens;
use crate::ui_kit::*;
use bevy::prelude::*;
use bevy::text::EditableText;
use vetf_net::MatchMode;

pub(super) fn plugin(app: &mut App) {
    app.add_systems(
        Update,
        (follow_default_port, settings_from_widgets, follow_mode, follow_rates, visuals)
            .chain()
            .run_if(in_state(AppState::MainMenu)),
    );
}

/// SETTINGS > GAMEPLAY > DEFAULT HOST PORT is HOST GAME's port (and the gun range's), unless `--port` set one
/// for this run: at start-up and whenever the setting changes.
fn follow_default_port(
    settings: Res<crate::settings::Settings>,
    cli: Res<crate::config::Cli>,
    mut host: ResMut<HostSettings>,
    mut editors: Query<(&FieldEditor, &mut EditableText)>,
    mut seen: Local<Option<u16>>,
) {
    let port = settings.network.host_port;
    if cli.port.is_some() || *seen == Some(port) {
        return;
    }
    *seen = Some(port);
    if host.port != port {
        host.port = port;
    }
    for (id, mut ed) in &mut editors {
        if id.0 == FieldId::Port && ed.value().to_string() != port.to_string() {
            field::set_value(&mut ed, &port.to_string());
        }
    }
}

/// WHO CAN JOIN's segments, in order: an internet invite (Iroh), LAN only and direct IP (both plain UDP
/// at ip:port, no Iroh). LAN ONLY has no discovery list yet; friends type the LAN address.
const ACCESS: [(JoinAccess, &str); 3] =
    [(JoinAccess::JoinCode, "Join code"), (JoinAccess::LanOnly, "LAN only"), (JoinAccess::DirectIp, "Direct IP")];

fn access_enabled(_: JoinAccess) -> bool {
    true
}

/// MODE's segments, in order.
const MODES: [(MatchMode, &str); 2] = [(MatchMode::Tdm, "Team deathmatch"), (MatchMode::Ffa, "Free-for-all")];

fn mode_index(mode: MatchMode) -> usize {
    MODES.iter().position(|(m, _)| *m == mode).unwrap_or(0)
}

/// Keyboard order (the disabled password is skipped).
pub(super) const ORDER: [HostItem; 8] = [
    HostItem::Name,
    HostItem::Mode,
    HostItem::Access,
    HostItem::MaxPlayers,
    HostItem::TickRate,
    HostItem::Snapshots,
    HostItem::Port,
    HostItem::Create,
];

pub(super) fn step(item: HostItem, delta: i32) -> HostItem {
    let i = ORDER.iter().position(|h| *h == item).unwrap_or(0) as i32;
    ORDER[(i + delta).rem_euclid(ORDER.len() as i32) as usize]
}

/// The next enabled WHO CAN JOIN option from `current` (no wrap).
pub(super) fn step_access(current: usize, delta: i32) -> usize {
    let enabled: Vec<usize> = (0..ACCESS.len()).filter(|i| access_enabled(ACCESS[*i].0)).collect();
    let pos = enabled.iter().position(|i| *i == current).unwrap_or(0) as i32;
    enabled[(pos + delta).clamp(0, enabled.len() as i32 - 1) as usize]
}

#[derive(Component)]
pub(super) struct AccessToggle;

/// MODE: team deathmatch or free-for-all.
#[derive(Component)]
pub(super) struct ModeToggle;

/// MAX PLAYERS' help (follows the mode).
#[derive(Component)]
pub(super) struct MaxHelp;

/// CREATE LOBBY's help (follows the mode).
#[derive(Component)]
pub(super) struct CreateHelp;

#[derive(Component)]
pub(super) struct MaxStepper;

#[derive(Component)]
pub(super) struct CreateBtn;

#[derive(Component)]
pub(super) struct PortHelp;

/// WHO CAN JOIN's explanation (follows the selected option).
#[derive(Component)]
pub(super) struct AccessHelp;

#[derive(Component)]
pub(super) struct HostError;

/// TICK RATE: `net.ron`'s `tick_rates`, in order.
#[derive(Component)]
pub(super) struct TickToggle;

/// SNAPSHOT RATE: `net.ron`'s `snapshot_rates`, in order (those above the tick rate disabled).
#[derive(Component)]
pub(super) struct SnapshotToggle;

/// SNAPSHOT RATE's help: the upload it costs (follows the rates and MAX PLAYERS).
#[derive(Component)]
pub(super) struct SnapshotHelp;

/// The segment index of `hz` among `rates` (the first if it is not there).
fn rate_index(rates: &[u32], hz: u32) -> usize {
    rates.iter().position(|r| *r == hz).unwrap_or(0)
}

/// The host's upload at the snapshot rate in play, with MAX PLAYERS all playing over the network but the host,
/// and whether it is high.
fn upload(data: &vetf_sim::GameData, host: &HostSettings) -> (f32, bool) {
    let players = hosted_players_for(data, host);
    let mbit = data.net.host_upload_mbit(host.snapshot_hz_in_play(data), players, players.saturating_sub(1));
    (mbit, data.net.upload_is_high(mbit))
}

/// The players CREATE LOBBY opens for (MAX PLAYERS within the mode's cap).
fn hosted_players_for(data: &vetf_sim::GameData, host: &HostSettings) -> u32 {
    crate::net::hosted_players(data, host.mode, host.max_players)
}

fn snapshot_help_text(data: &vetf_sim::GameData, host: &HostSettings) -> (String, Color) {
    let (mbit, high) = upload(data, host);
    (copy::snapshot_help(mbit, hosted_players_for(data, host), high), if high { BAD } else { TEXT_MID })
}

fn lobby_char(c: char) -> bool {
    !c.is_control()
}

fn port_char(c: char) -> bool {
    c.is_ascii_digit()
}

/// `.input.sm`: 44 tall, K45 fill, STROKE_HI border, 8 px below its grid row's top (as in the CSS).
fn input_box(width: Option<f32>) -> impl Bundle {
    (
        Node {
            width: width.map_or(Val::Auto, px),
            flex_shrink: 0.0,
            height: px(44),
            margin: UiRect::top(px(8)),
            padding: UiRect::horizontal(px(16)),
            border: UiRect::all(px(1)),
            align_items: AlignItems::Center,
            overflow: Overflow::clip(),
            ..default()
        },
        BackgroundColor(K45),
        // The visuals system keeps this border (red when invalid).
        BorderColor::all(STROKE_HI),
    )
}

pub(super) fn spawn_flyout(
    r: &mut ChildSpawnerCommands,
    ctx: &Ctx,
    host: &HostSettings,
    session: &Session,
    state: &MenuState,
) {
    let fonts = ctx.fonts;
    let data = ctx.data;
    let cap = max_players_cap_for(data, host.mode);
    let access = ACCESS.iter().position(|(a, _)| *a == host.access).unwrap_or(0);
    r.spawn((
        super::Flyout(Sub::Host),
        panel_of(
            PanelKind::Flyout,
            Node {
                display: if state.sub == Sub::Host { Display::Flex } else { Display::None },
                width: px(620),
                flex_direction: FlexDirection::Column,
                padding: UiRect { left: px(28), right: px(28), top: px(26), bottom: px(24) },
                ..default()
            },
        ),
        // Clicks inside the modal stay in it (the backdrop around it closes it).
        bevy::ui::FocusPolicy::Block,
    ))
    .with_children(|p| {
        p.spawn(fonts.role(TextRole::FlyoutTitle, "Host game"));
        super::close_button(p, fonts);
        p.spawn((fonts.role(TextRole::Help, copy::HOST_INTRO), Node { margin: UiRect::top(px(6)), ..default() }));
        p.spawn(Node {
            display: Display::Grid,
            grid_template_columns: vec![GridTrack::px(170.0), GridTrack::flex(1.0)],
            row_gap: px(14),
            align_items: AlignItems::Center,
            margin: UiRect::top(px(18)),
            ..default()
        })
        .with_children(|g| {
            g.spawn(fonts.lbl("Lobby name"));
            let default_name = default_lobby_name(&session.local_name);
            field::spawn_field(
                g,
                fonts,
                FieldSpec {
                    id: FieldId::LobbyName,
                    role: TextRole::InputM,
                    em: None,
                    tnum: false,
                    placeholder: default_name.clone(),
                    max_chars: HostSettings::LOBBY_NAME_MAX,
                    filter: Some(lobby_char),
                    initial: if host.lobby_name.is_empty() { default_name } else { host.lobby_name.clone() },
                    display: None,
                },
                input_box(None),
                |_| {},
            );

            g.spawn(fonts.lbl("Mode"));
            g.spawn((
                ModeToggle,
                SegValue(mode_index(host.mode)),
                FocusRing(Focus::Host(HostItem::Mode)),
                ring(),
                Node { height: px(36), border: UiRect::all(px(1)), align_self: AlignSelf::Start, ..default() },
                BorderColor::all(STROKE_HI),
            ))
            .with_children(|t| {
                for (i, (m, label)) in MODES.iter().enumerate() {
                    let mut seg = t.spawn((
                        segment(fonts, label, TOGGLE, 34.0, false),
                        SegOption(i),
                        FocusTarget(Focus::Host(HostItem::Mode)),
                    ));
                    if *m == host.mode {
                        seg.insert(Active(true));
                    }
                }
            });

            // The label stays centred on the toggle (as in the mockup); the explanation hangs below it.
            g.spawn((
                fonts.lbl("Who can join"),
                Node { align_self: AlignSelf::Start, margin: UiRect::top(px(10)), ..default() },
            ));
            g.spawn(Node { flex_direction: FlexDirection::Column, ..default() }).with_children(|col| {
                col.spawn((
                    AccessToggle,
                    SegValue(access),
                    FocusRing(Focus::Host(HostItem::Access)),
                    ring(),
                    Node { height: px(36), border: UiRect::all(px(1)), ..default() },
                    BorderColor::all(STROKE_HI),
                ))
                .with_children(|t| {
                    for (i, (a, label)) in ACCESS.iter().enumerate() {
                        let mut seg = t.spawn((
                            segment(fonts, label, TOGGLE, 34.0, false),
                            SegOption(i),
                            FocusTarget(Focus::Host(HostItem::Access)),
                        ));
                        if i == access {
                            seg.insert(Active(true));
                        }
                        if !access_enabled(*a) {
                            seg.insert(Disabled);
                        }
                    }
                });
                // Two lines tall for every option, so switching never moves the rows below.
                col.spawn((
                    AccessHelp,
                    fonts.role(TextRole::Help, copy::access_help(host.access, host.port)),
                    Node { margin: UiRect::top(px(6)), min_height: px(37.7), ..default() },
                ));
            });

            g.spawn(fonts.lbl("Max players"));
            g.spawn(Node { column_gap: px(10), align_items: AlignItems::Center, ..default() }).with_children(|row| {
                let (value, step) = max_stepper(host.mode, host.max_players, cap);
                row.spawn((
                    stepper(fonts, value as i32, 2, cap as i32, step),
                    MaxStepper,
                    FocusRing(Focus::Host(HostItem::MaxPlayers)),
                    ring(),
                ));
                row.spawn((MaxHelp, fonts.role(TextRole::Help, max_help(data, host.mode))));
            });

            // TICK RATE and SNAPSHOT RATE, each with what it means; SNAPSHOT RATE's help is the upload it costs.
            let rates = [
                (HostItem::TickRate, "Tick rate", &data.net.tick_rates, host.tick_hz),
                (HostItem::Snapshots, "Snapshots", &data.net.snapshot_rates, host.snapshot_hz_in_play(data)),
            ];
            for (item, label, options, value) in rates {
                g.spawn((
                    fonts.lbl(label),
                    Node { align_self: AlignSelf::Start, margin: UiRect::top(px(10)), ..default() },
                ));
                g.spawn(Node { flex_direction: FlexDirection::Column, ..default() }).with_children(|col| {
                    let mut toggle = col.spawn((
                        SegValue(rate_index(options, value)),
                        FocusRing(Focus::Host(item)),
                        ring(),
                        Node { height: px(36), border: UiRect::all(px(1)), align_self: AlignSelf::Start, ..default() },
                        BorderColor::all(STROKE_HI),
                    ));
                    if item == HostItem::TickRate {
                        toggle.insert(TickToggle);
                    } else {
                        toggle.insert(SnapshotToggle);
                    }
                    toggle.with_children(|t| {
                        for (i, hz) in options.iter().enumerate() {
                            let mut seg = t.spawn((
                                segment(fonts, &copy::hz_label(*hz), TOGGLE, 34.0, false),
                                SegOption(i),
                                FocusTarget(Focus::Host(item)),
                            ));
                            if *hz == value {
                                seg.insert(Active(true));
                            }
                            if item == HostItem::Snapshots && *hz > host.tick_hz {
                                seg.insert(Disabled);
                            }
                        }
                    });
                    let below = Node { margin: UiRect::top(px(6)), ..default() };
                    if item == HostItem::TickRate {
                        col.spawn((fonts.role(TextRole::Help, copy::TICK_RATE_HELP), below));
                    } else {
                        let (text, color) = snapshot_help_text(data, host);
                        col.spawn((SnapshotHelp, fonts.role_color(TextRole::Help, text, color), below));
                    }
                });
            }

            g.spawn(fonts.lbl("Port"));
            g.spawn(Node { column_gap: px(10), align_items: AlignItems::Center, ..default() }).with_children(|row| {
                field::spawn_field(
                    row,
                    fonts,
                    FieldSpec {
                        id: FieldId::Port,
                        role: TextRole::InputM,
                        em: None,
                        tnum: true,
                        placeholder: data.net.port.to_string(),
                        max_chars: 5,
                        filter: Some(port_char),
                        initial: host.port.to_string(),
                        display: None,
                    },
                    input_box(Some(136.0)),
                    |_| {},
                );
                row.spawn((PortHelp, fonts.role(TextRole::Help, copy::PORT_HELP)));
            });

            // Not in the protocol yet: shown, disabled.
            g.spawn(fonts.lbl("Password"));
            g.spawn((
                Node {
                    height: px(44),
                    margin: UiRect::top(px(8)),
                    padding: UiRect::horizontal(px(16)),
                    border: UiRect::all(px(1)),
                    align_items: AlignItems::Center,
                    ..default()
                },
                BackgroundColor(fade(K45, DISABLED_ALPHA)),
                BorderColor::all(fade(STROKE_HI, DISABLED_ALPHA)),
                children![fonts.role_color(
                    TextRole::InputM,
                    copy::PASSWORD_PLACEHOLDER,
                    fade(TEXT_LOW, DISABLED_ALPHA)
                )],
            ));
        });
        p.spawn(Node { column_gap: px(12), align_items: AlignItems::Center, margin: UiRect::top(px(22)), ..default() })
            .with_children(|a| {
                a.spawn((
                    button(fonts, "Create lobby", BtnKind::Primary, BtnSize::L),
                    CreateBtn,
                    Click(MenuAction::CreateLobby),
                    FocusTarget(Focus::Host(HostItem::Create)),
                    FocusRing(Focus::Host(HostItem::Create)),
                    ring(),
                ));
                a.spawn((CreateHelp, fonts.role(TextRole::Help, create_help(data, host.mode))));
            });
        p.spawn((
            HostError,
            fonts.role_color(TextRole::Help, "", BAD),
            Node { display: Display::None, margin: UiRect::top(px(12)), ..default() },
        ));
    });
}

/// MAX PLAYERS' value and step for a mode: even and by twos for teams, by ones in free-for-all.
fn max_stepper(mode: MatchMode, wanted: u32, cap: u32) -> (u32, i32) {
    let v = wanted.clamp(2, cap.max(2));
    if mode.has_teams() { ((v - v % 2).max(2), 2) } else { (v, 1) }
}

/// The MAX PLAYERS the player wants, after the stepper shows `shown`. The stepper showing the wanted value as
/// the mode allows it (a MODE switch clamped it) keeps the wanted value, so a look at free-for-all does not
/// shrink a 5 v 5; any other value was stepped to and becomes the wanted one.
fn wanted_players(mode: MatchMode, wanted: u32, shown: u32, cap: u32) -> u32 {
    if shown == max_stepper(mode, wanted, cap).0 { wanted } else { shown }
}

fn max_help(data: &vetf_sim::GameData, mode: MatchMode) -> String {
    let cap = max_players_cap_for(data, mode);
    match mode {
        MatchMode::Ffa => copy::ffa_max_players_help(cap),
        _ => copy::max_players_help(cap, data.rules.tdm.max_players),
    }
}

fn create_help(data: &vetf_sim::GameData, mode: MatchMode) -> String {
    match mode {
        MatchMode::Ffa => copy::ffa_create_help(data.rules.ffa.score_limit),
        _ => copy::create_help(data.rules.tdm.score_limit),
    }
}

/// A new MODE re-limits MAX PLAYERS (free-for-all seats fewer, by ones) and rewrites the help lines.
#[allow(clippy::type_complexity)]
fn follow_mode(
    host: Res<HostSettings>,
    data: Res<crate::config::Data>,
    mut last: Local<Option<MatchMode>>,
    mut steppers: Query<&mut StepperValue, With<MaxStepper>>,
    mut toggles: Query<&mut SegValue, With<ModeToggle>>,
    mut texts: ParamSet<(Query<&mut Text, With<MaxHelp>>, Query<&mut Text, With<CreateHelp>>)>,
) {
    if *last == Some(host.mode) {
        return;
    }
    let first = last.is_none();
    *last = Some(host.mode);
    let cap = max_players_cap_for(&data, host.mode);
    for mut s in &mut steppers {
        // From the wanted value, not the one shown: TDM 10 -> FFA 8 -> TDM shows 10 again.
        let (value, step) = max_stepper(host.mode, host.max_players, cap);
        let want = StepperValue { value: value as i32, min: 2, max: cap as i32, step };
        if *s != want {
            *s = want;
        }
    }
    for mut t in &mut toggles {
        let i = mode_index(host.mode);
        if t.0 != i {
            t.0 = i;
        }
    }
    if first {
        return;
    }
    let (max, create) = (max_help(&data, host.mode), create_help(&data, host.mode));
    for mut t in &mut texts.p0() {
        if t.0 != max {
            t.0.clone_from(&max);
        }
    }
    for mut t in &mut texts.p1() {
        if t.0 != create {
            t.0.clone_from(&create);
        }
    }
}

/// TICK RATE limits SNAPSHOT RATE (no more snapshots than ticks: the faster ones are disabled and the toggle shows
/// the rate in play, keeping the wanted one for a switch back), and the upload help follows the rates and MAX
/// PLAYERS.
#[allow(clippy::type_complexity)]
fn follow_rates(
    host: Res<HostSettings>,
    data: Res<crate::config::Data>,
    mut last: Local<Option<(u32, u32, u32, MatchMode)>>,
    mut toggles: Query<(&mut SegValue, &Children), (With<SnapshotToggle>, Without<TickToggle>)>,
    mut ticks: Query<&mut SegValue, (With<TickToggle>, Without<SnapshotToggle>)>,
    segs: Query<(&SegOption, Has<Disabled>)>,
    mut help: Query<(&mut Text, &mut TextColor), With<SnapshotHelp>>,
    mut commands: Commands,
) {
    let now = (host.tick_hz, host.snapshot_hz, host.max_players, host.mode);
    if *last == Some(now) {
        return;
    }
    *last = Some(now);
    let rates = &data.net.snapshot_rates;
    for mut v in &mut ticks {
        let want = rate_index(&data.net.tick_rates, host.tick_hz);
        if v.0 != want {
            v.0 = want;
        }
    }
    for (mut v, kids) in &mut toggles {
        let want = rate_index(rates, host.snapshot_hz_in_play(&data));
        if v.0 != want {
            v.0 = want;
        }
        for kid in kids.iter() {
            let Ok((opt, disabled)) = segs.get(kid) else { continue };
            let off = rates.get(opt.0).is_some_and(|hz| *hz > host.tick_hz);
            if off && !disabled {
                commands.entity(kid).insert(Disabled);
            } else if !off && disabled {
                commands.entity(kid).remove::<Disabled>();
            }
        }
    }
    let (text, color) = snapshot_help_text(&data, &host);
    for (mut t, mut c) in &mut help {
        if t.0 != text {
            t.0.clone_from(&text);
        }
        if c.0 != color {
            c.0 = color;
        }
    }
}

/// The SNAPSHOT RATE the player wants after the toggle shows `shown`: like MAX PLAYERS, the toggle showing the
/// wanted rate as the tick rate allows it keeps the wanted one (a look at 60 Hz does not lose 120 snapshots).
fn wanted_snapshots(data: &vetf_sim::GameData, tick_hz: u32, wanted: u32, shown: u32) -> u32 {
    if shown == data.net.snapshot_hz_for(tick_hz, wanted) { wanted } else { shown }
}

/// CREATE LOBBY: host the chosen mode on Showhome; it opens in the lobby.
pub(super) fn actions(
    mut actions: MessageReader<MenuAction>,
    create: Query<Has<Disabled>, With<CreateBtn>>,
    mut requests: MessageWriter<NetRequest>,
) {
    for action in actions.read() {
        if *action == MenuAction::CreateLobby && !create.iter().any(|disabled| disabled) {
            requests.write(NetRequest::Host { map: "showhome".into(), lobby: true });
        }
    }
}

/// ←/→ on MODE, WHO CAN JOIN, TICK RATE and SNAPSHOTS; ←/→ and -/+ on MAX PLAYERS.
#[allow(clippy::type_complexity)]
pub(super) fn keys(
    keys: Res<ButtonInput<KeyCode>>,
    mut state: ResMut<MenuState>,
    screens: Res<Screens>,
    host: Res<HostSettings>,
    data: Res<crate::config::Data>,
    mut toggles: Query<&mut SegValue, (With<AccessToggle>, Without<ModeToggle>)>,
    mut modes: Query<&mut SegValue, (With<ModeToggle>, Without<AccessToggle>)>,
    mut rates: ParamSet<(
        Query<&mut SegValue, (With<TickToggle>, Without<ModeToggle>, Without<AccessToggle>)>,
        Query<&mut SegValue, (With<SnapshotToggle>, Without<ModeToggle>, Without<AccessToggle>)>,
    )>,
    mut steppers: Query<(Entity, &mut StepperValue), With<MaxStepper>>,
    step_buttons: Query<(&Interaction, &ChildOf), (Changed<Interaction>, With<StepperButton>)>,
) {
    // A click on the stepper's − / + also moves focus to it.
    for (i, parent) in &step_buttons {
        if *i == Interaction::Pressed && steppers.contains(parent.parent()) {
            state.focus = Focus::Host(HostItem::MaxPlayers);
            state.focus_visible = false;
        }
    }
    if !screens.is_empty() {
        return;
    }
    let less = keys.any_just_pressed([KeyCode::ArrowLeft, KeyCode::Minus, KeyCode::NumpadSubtract]);
    let more = keys.any_just_pressed([KeyCode::ArrowRight, KeyCode::Equal, KeyCode::NumpadAdd]);
    if !(less || more) {
        return;
    }
    let delta = if more { 1 } else { -1 };
    match state.focus {
        Focus::Host(HostItem::Mode) if !keys.any_just_pressed([KeyCode::Minus, KeyCode::Equal]) => {
            for mut v in &mut modes {
                let next = (v.0 as i32 + delta).clamp(0, MODES.len() as i32 - 1) as usize;
                if v.0 != next {
                    v.0 = next;
                }
            }
            state.focus_visible = true;
        }
        Focus::Host(HostItem::Access) if !keys.any_just_pressed([KeyCode::Minus, KeyCode::Equal]) => {
            for mut v in &mut toggles {
                let next = step_access(v.0, delta);
                if v.0 != next {
                    v.0 = next;
                }
            }
            state.focus_visible = true;
        }
        Focus::Host(HostItem::MaxPlayers) => {
            for (_, mut s) in &mut steppers {
                let next = (s.value + delta * s.step).clamp(s.min, s.max);
                if s.value != next {
                    s.value = next;
                }
            }
            state.focus_visible = true;
        }
        Focus::Host(HostItem::TickRate) if !keys.any_just_pressed([KeyCode::Minus, KeyCode::Equal]) => {
            for mut v in &mut rates.p0() {
                let next = (v.0 as i32 + delta).clamp(0, data.net.tick_rates.len() as i32 - 1) as usize;
                if v.0 != next {
                    v.0 = next;
                }
            }
            state.focus_visible = true;
        }
        Focus::Host(HostItem::Snapshots) if !keys.any_just_pressed([KeyCode::Minus, KeyCode::Equal]) => {
            // Only the rates the tick rate allows.
            let allowed = data.net.snapshot_rates.iter().filter(|hz| **hz <= host.tick_hz).count().max(1);
            for mut v in &mut rates.p1() {
                let next = (v.0 as i32 + delta).clamp(0, allowed as i32 - 1) as usize;
                if v.0 != next {
                    v.0 = next;
                }
            }
            state.focus_visible = true;
        }
        _ => {}
    }
}

/// Copy the panel's widgets into [`HostSettings`].
#[allow(clippy::too_many_arguments)]
fn settings_from_widgets(
    mut host: ResMut<HostSettings>,
    data: Res<crate::config::Data>,
    mut session: ResMut<Session>,
    fields: Query<&Field>,
    toggles: Query<&SegValue, (With<AccessToggle>, Changed<SegValue>)>,
    modes: Query<&SegValue, (With<ModeToggle>, Changed<SegValue>)>,
    steppers: Query<&StepperValue, (With<MaxStepper>, Changed<StepperValue>)>,
    ticks: Query<&SegValue, (With<TickToggle>, Changed<SegValue>)>,
    snapshots: Query<&SegValue, (With<SnapshotToggle>, Changed<SegValue>)>,
    mut editors: Query<(&FieldEditor, &mut EditableText)>,
    mut last_name: Local<String>,
) {
    let mut edited = false;
    for f in &fields {
        if !f.edited {
            continue;
        }
        match f.id {
            FieldId::LobbyName => {
                edited = true;
                let typed = if f.value.trim() == default_lobby_name(&session.local_name) { "" } else { f.value.trim() };
                if host.lobby_name != typed {
                    host.lobby_name = typed.to_string();
                }
            }
            FieldId::Port => {
                edited = true;
                if let Some(p) = parse_host_port(&f.value)
                    && host.port != p
                {
                    host.port = p;
                }
            }
            _ => {}
        }
    }
    // Typing clears a hosting error.
    if edited && session.host_error {
        session.status = None;
        session.host_error = false;
    }
    for v in &toggles {
        let access = ACCESS.get(v.0).map_or(JoinAccess::JoinCode, |(a, _)| *a);
        if host.access != access {
            host.access = access;
        }
    }
    for v in &modes {
        let mode = MODES.get(v.0).map_or(MatchMode::Tdm, |(m, _)| *m);
        if host.mode != mode {
            host.mode = mode;
        }
    }
    for s in &steppers {
        let cap = max_players_cap_for(&data, host.mode);
        let n = wanted_players(host.mode, host.max_players, s.value.max(2) as u32, cap);
        if host.max_players != n {
            host.max_players = n;
        }
    }
    for v in &ticks {
        let hz = data.net.tick_rates.get(v.0).copied().unwrap_or(data.net.tick_hz);
        if host.tick_hz != hz {
            host.tick_hz = hz;
        }
    }
    for v in &snapshots {
        let shown = data.net.snapshot_rates.get(v.0).copied().unwrap_or(data.net.snapshot_hz);
        let hz = wanted_snapshots(&data, host.tick_hz, host.snapshot_hz, shown);
        if host.snapshot_hz != hz {
            host.snapshot_hz = hz;
        }
    }
    // A new player name renames a lobby that still has the default name.
    if *last_name != session.local_name {
        let first = last_name.is_empty();
        last_name.clone_from(&session.local_name);
        if !first && host.lobby_name.is_empty() {
            for (id, mut ed) in &mut editors {
                if id.0 == FieldId::LobbyName {
                    field::set_value(&mut ed, &default_lobby_name(&session.local_name));
                }
            }
        }
    }
}

#[allow(clippy::type_complexity)]
fn visuals(
    session: Res<Session>,
    host: Res<HostSettings>,
    mut fields: Query<(&Field, &mut BorderColor)>,
    steppers: Query<(&StepperValue, &Children), (With<MaxStepper>, Changed<StepperValue>)>,
    cells: Query<&Children>,
    step_buttons: Query<(Entity, &StepperButton, Has<Disabled>)>,
    create: Query<(Entity, Has<Disabled>), With<CreateBtn>>,
    mut texts: ParamSet<(
        Query<&mut Text, With<StepperText>>,
        Query<(&mut Text, &mut TextColor), With<PortHelp>>,
        Query<(&mut Text, &mut Node), With<HostError>>,
        Query<&mut Text, With<AccessHelp>>,
    )>,
    mut commands: Commands,
) {
    // Port: digits, 1024-65535; anything else turns the field red and disables CREATE LOBBY.
    let mut port_ok = true;
    for (f, mut border) in &mut fields {
        if f.id != FieldId::Port {
            continue;
        }
        port_ok = parse_host_port(&f.value).is_some();
        let want = BorderColor::all(if port_ok { STROKE_HI } else { BAD });
        if *border != want {
            *border = want;
        }
    }
    for (e, disabled) in &create {
        if disabled == port_ok {
            if port_ok {
                commands.entity(e).remove::<Disabled>();
            } else {
                commands.entity(e).insert(Disabled);
            }
        }
    }
    for (mut t, mut c) in &mut texts.p1() {
        let (copy, color) = if port_ok { (copy::PORT_HELP, TEXT_MID) } else { (copy::PORT_ERROR, BAD) };
        if t.0 != copy {
            t.0 = copy.to_string();
            c.0 = color;
        }
    }
    // The stepper's value, and its − / + at the limits.
    for (v, kids) in &steppers {
        for cell in kids.iter() {
            for t in cells.get(cell).map(|c| c.iter().collect::<Vec<_>>()).unwrap_or_default() {
                if let Ok(mut text) = texts.p0().get_mut(t) {
                    text.0 = v.value.to_string();
                }
            }
            if let Ok((e, b, disabled)) = step_buttons.get(cell) {
                let at_limit = (b.0 < 0 && v.value <= v.min) || (b.0 > 0 && v.value >= v.max);
                if at_limit && !disabled {
                    commands.entity(e).insert(Disabled);
                } else if !at_limit && disabled {
                    commands.entity(e).remove::<Disabled>();
                }
            }
        }
    }
    if host.is_changed() {
        let help = copy::access_help(host.access, host.port);
        for mut t in &mut texts.p3() {
            if t.0 != help {
                t.0.clone_from(&help);
            }
        }
    }
    // A hosting error (port in use) shows under the action row.
    let msg = session.status.as_deref().filter(|_| session.host_error).unwrap_or_default();
    for (mut t, mut n) in &mut texts.p2() {
        if t.0 != msg {
            t.0 = msg.to_string();
        }
        let display = if msg.is_empty() { Display::None } else { Display::Flex };
        if n.display != display {
            n.display = display;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn host_focus_wraps_and_lan_only_is_skipped() {
        assert_eq!(step(HostItem::Name, 1), HostItem::Mode);
        assert_eq!(step(HostItem::Mode, 1), HostItem::Access);
        assert_eq!(step(HostItem::Name, -1), HostItem::Create);
        assert_eq!(step(HostItem::Create, 1), HostItem::Name);
        assert_eq!(step_access(0, 1), 1, "LAN ONLY hosts without an internet invite");
        assert_eq!(step_access(2, -1), 1);
        assert_eq!(step_access(2, 1), 2, "no wrap");
        assert_eq!(step_access(0, -1), 0);
    }

    /// TICK RATE and SNAPSHOTS: 120 Hz and 60 snapshots by default; at 60 Hz the 120-snapshot option is shown as
    /// 60 (no more snapshots than ticks) but stays wanted for a switch back; a rate stepped to sticks. The help
    /// warns past `net.ron`'s upload line.
    #[test]
    fn the_rates_default_to_120_hz_and_60_snapshots() {
        let d = vetf_sim::GameData::embedded();
        let mut h = HostSettings::new(&d, None);
        assert_eq!((h.tick_hz, h.snapshot_hz_in_play(&d)), (120, 60));
        assert_eq!(rate_index(&d.net.tick_rates, h.tick_hz), 1);
        assert_eq!(rate_index(&d.net.snapshot_rates, 60), 1);
        h.snapshot_hz = 120;
        h.tick_hz = 60;
        assert_eq!(h.snapshot_hz_in_play(&d), 60, "no more snapshots than ticks");
        assert_eq!(wanted_snapshots(&d, 60, 120, 60), 120, "only shown clamped");
        h.tick_hz = 120;
        assert_eq!(h.snapshot_hz_in_play(&d), 120, "back at 120 Hz: the wanted rate");
        assert_eq!(wanted_snapshots(&d, 120, 120, 30), 30, "a rate stepped to sticks");
        // 10 players at 120 snapshots: high; 30 snapshots: fine.
        assert!(upload(&d, &h).1, "{:?}", upload(&d, &h));
        h.snapshot_hz = 30;
        assert!(!upload(&d, &h).1);
        let (text, color) = snapshot_help_text(&d, &h);
        assert!(text.starts_with("≈ 2.") && text.contains("with 10 players"), "{text}");
        assert_eq!(color, TEXT_MID);
        h.max_players = 2;
        assert!(upload(&d, &h).0 < 0.2, "one friend: next to nothing");
    }

    #[test]
    fn max_players_follow_the_mode() {
        let d = vetf_sim::GameData::embedded();
        let (tdm, ffa) = (max_players_cap_for(&d, MatchMode::Tdm), max_players_cap_for(&d, MatchMode::Ffa));
        assert_eq!((tdm, ffa), (10, 8));
        assert_eq!(max_stepper(MatchMode::Tdm, 10, tdm), (10, 2));
        assert_eq!(max_stepper(MatchMode::Ffa, 10, ffa), (8, 1), "free-for-all seats 8");
        assert_eq!(max_stepper(MatchMode::Ffa, 5, ffa), (5, 1), "odd is fine without teams");
        assert_eq!(max_stepper(MatchMode::Tdm, 5, tdm), (4, 2), "teams of equal size");
        assert_eq!(max_stepper(MatchMode::Tdm, 0, tdm), (2, 2));
        assert_eq!(mode_index(MatchMode::Ffa), 1);
        assert!(create_help(&d, MatchMode::Ffa).contains("first to 25 kills"));
        assert!(max_help(&d, MatchMode::Ffa).starts_with("2–8"));
    }

    /// A look at free-for-all does not shrink a 5 v 5: MODE's clamp is only shown, the wanted 10 stays and
    /// team deathmatch shows it again. A value stepped to is kept, in either mode.
    #[test]
    fn max_players_survive_a_mode_round_trip() {
        let d = vetf_sim::GameData::embedded();
        let (tdm, ffa) = (max_players_cap_for(&d, MatchMode::Tdm), max_players_cap_for(&d, MatchMode::Ffa));
        let mut wanted = 10;
        // TDM -> FFA: the stepper shows 8 (follow_mode), which settings_from_widgets reads back next frame.
        let shown = max_stepper(MatchMode::Ffa, wanted, ffa).0;
        assert_eq!(shown, 8);
        wanted = wanted_players(MatchMode::Ffa, wanted, shown, ffa);
        assert_eq!(wanted, 10, "only shown clamped");
        // FFA -> TDM: back to 10.
        assert_eq!(max_stepper(MatchMode::Tdm, wanted, tdm).0, 10);
        assert_eq!(wanted_players(MatchMode::Tdm, wanted, 10, tdm), 10);
        // The player steps FFA down to 7: that sticks, and TDM shows 6 (even) but keeps wanting 7.
        wanted = wanted_players(MatchMode::Ffa, wanted, 7, ffa);
        assert_eq!(wanted, 7);
        assert_eq!(max_stepper(MatchMode::Tdm, wanted, tdm).0, 6);
        assert_eq!(wanted_players(MatchMode::Tdm, wanted, 6, tdm), 7);
        // ... and the lobby that CREATE LOBBY opens from it.
        assert_eq!(crate::net::hosted_players(&d, MatchMode::Tdm, 10), 10);
        assert_eq!(crate::net::hosted_players(&d, MatchMode::Ffa, 10), 8);
    }
}
