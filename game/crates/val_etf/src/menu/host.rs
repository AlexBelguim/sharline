//! PLAY > HOST GAME (mockup 04b): lobby name, who can join, max players, port and password, then CREATE
//! LOBBY. Until the lobby screen exists, CREATE LOBBY starts team deathmatch on Showhome directly. The
//! values live in [`HostSettings`] (kept across menu visits; the gun range hosts with them too).

use super::field::{self, Field, FieldEditor, FieldId, FieldSpec};
use super::{Click, Ctx, Focus, FocusRing, FocusTarget, HostItem, MenuAction, MenuState, Sub, copy, ring};
use crate::AppState;
use crate::net::{HostSettings, JoinAccess, NetRequest, Session, default_lobby_name, max_players_cap, parse_host_port};
use crate::screens::Screens;
use crate::ui_kit::*;
use bevy::prelude::*;
use bevy::text::EditableText;

pub(super) fn plugin(app: &mut App) {
    app.add_systems(Update, (settings_from_widgets, visuals).chain().run_if(in_state(AppState::MainMenu)));
}

/// WHO CAN JOIN's segments, in order. LAN ONLY waits for the LAN beacon.
const ACCESS: [(JoinAccess, &str); 3] =
    [(JoinAccess::JoinCode, "Join code"), (JoinAccess::LanOnly, "LAN only"), (JoinAccess::DirectIp, "Direct IP")];

fn access_enabled(a: JoinAccess) -> bool {
    a != JoinAccess::LanOnly
}

/// Keyboard order (the disabled password is skipped).
pub(super) const ORDER: [HostItem; 5] =
    [HostItem::Name, HostItem::Access, HostItem::MaxPlayers, HostItem::Port, HostItem::Create];

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

#[derive(Component)]
pub(super) struct MaxStepper;

#[derive(Component)]
pub(super) struct CreateBtn;

#[derive(Component)]
pub(super) struct PortHelp;

#[derive(Component)]
pub(super) struct HostError;

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
        // The visuals system keeps this border (browser-matched, red when invalid).
        BorderColor::all(super::browser(STROKE_HI)),
        super::BrowserBlended,
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
    let cap = max_players_cap(data);
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
                ..abs(Some(540.0), None, Some(300.0), None)
            },
        ),
    ))
    // The panel sits over the art: blend like the browser does.
    .insert(BackgroundColor(super::browser_fill_over_art(PANEL_HI)))
    .with_children(|p| {
        p.spawn(fonts.role(TextRole::FlyoutTitle, "Host game"));
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
                },
                input_box(None),
                |_| {},
            );

            g.spawn(fonts.lbl("Who can join"));
            g.spawn((
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

            g.spawn(fonts.lbl("Max players"));
            g.spawn(Node { column_gap: px(10), align_items: AlignItems::Center, ..default() }).with_children(|row| {
                row.spawn((
                    stepper(fonts, host.max_players.clamp(2, cap) as i32, 2, cap as i32, 2),
                    MaxStepper,
                    FocusRing(Focus::Host(HostItem::MaxPlayers)),
                    ring(),
                ));
                row.spawn(fonts.role(TextRole::Help, copy::max_players_help(cap, data.rules.tdm.max_players)));
            });

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
                a.spawn(fonts.role(TextRole::Help, copy::create_help(data.rules.tdm.score_limit)));
            });
        p.spawn((
            HostError,
            fonts.role_color(TextRole::Help, "", BAD),
            Node { display: Display::None, margin: UiRect::top(px(12)), ..default() },
        ));
    });
}

/// CREATE LOBBY: host team deathmatch on Showhome (phase 1: the lobby screen comes later).
pub(super) fn actions(
    mut actions: MessageReader<MenuAction>,
    create: Query<Has<Disabled>, With<CreateBtn>>,
    mut requests: MessageWriter<NetRequest>,
) {
    for action in actions.read() {
        if *action == MenuAction::CreateLobby && !create.iter().any(|disabled| disabled) {
            requests.write(NetRequest::Host { map: "showhome".into() });
        }
    }
}

/// ←/→ on WHO CAN JOIN; ←/→ and -/+ on MAX PLAYERS.
pub(super) fn keys(
    keys: Res<ButtonInput<KeyCode>>,
    mut state: ResMut<MenuState>,
    screens: Res<Screens>,
    mut toggles: Query<&mut SegValue, With<AccessToggle>>,
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
        _ => {}
    }
}

/// Copy the panel's widgets into [`HostSettings`].
fn settings_from_widgets(
    mut host: ResMut<HostSettings>,
    mut session: ResMut<Session>,
    fields: Query<&Field>,
    toggles: Query<&SegValue, (With<AccessToggle>, Changed<SegValue>)>,
    steppers: Query<&StepperValue, (With<MaxStepper>, Changed<StepperValue>)>,
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
    for s in &steppers {
        let n = s.value.max(2) as u32;
        if host.max_players != n {
            host.max_players = n;
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
    mut fields: Query<(&Field, &mut BorderColor)>,
    steppers: Query<(&StepperValue, &Children), (With<MaxStepper>, Changed<StepperValue>)>,
    cells: Query<&Children>,
    step_buttons: Query<(Entity, &StepperButton, Has<Disabled>)>,
    create: Query<(Entity, Has<Disabled>), With<CreateBtn>>,
    mut texts: ParamSet<(
        Query<&mut Text, With<StepperText>>,
        Query<(&mut Text, &mut TextColor), With<PortHelp>>,
        Query<(&mut Text, &mut Node), With<HostError>>,
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
        let want = BorderColor::all(if port_ok { super::browser(STROKE_HI) } else { BAD });
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
        assert_eq!(step(HostItem::Name, 1), HostItem::Access);
        assert_eq!(step(HostItem::Name, -1), HostItem::Create);
        assert_eq!(step(HostItem::Create, 1), HostItem::Name);
        assert_eq!(step_access(0, 1), 2, "LAN ONLY is disabled until the LAN beacon exists");
        assert_eq!(step_access(2, -1), 0);
        assert_eq!(step_access(2, 1), 2);
    }
}
