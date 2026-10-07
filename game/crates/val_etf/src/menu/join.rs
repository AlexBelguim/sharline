//! PLAY > JOIN GAME (mockup 04): JOIN CODE / DIRECT IP / ON YOUR NETWORK tabs, the field with PASTE, JOIN
//! LOBBY, and the RECENT list. A join code is only the host's address and port (no relay), so both tabs
//! take the same input. LAN discovery is not built, so ON YOUR NETWORK says so (adaptation J3).

use super::field::{self, Field, FieldEditor, FieldId, FieldSpec};
use super::{Click, Ctx, Focus, FocusRing, FocusTarget, JoinItem, JoinTab, MenuAction, MenuState, Sub, copy, ring};
use crate::AppState;
use crate::config::Data;
use crate::net::{NetRequest, Session, is_lan_ip};
use crate::screens::Screens;
use crate::ui_kit::*;
use crate::user_config::{RecentServer, RecentServers};
use bevy::clipboard::Clipboard;
use bevy::prelude::*;
use bevy::text::EditableText;
use vetf_net::JoinCode;

pub(super) fn plugin(app: &mut App) {
    app.add_systems(Update, visuals.run_if(in_state(AppState::MainMenu)));
}

/// RECENT shows this many games.
pub(super) const RECENT_ROWS: usize = 3;

pub(super) fn visible_rows(recent: &RecentServers) -> usize {
    recent.servers.len().min(RECENT_ROWS)
}

/// Keyboard order on a tab: tabs, field, PASTE, JOIN LOBBY, rows (only the tabs on ON YOUR NETWORK).
pub(super) fn order(tab: JoinTab, rows: usize) -> Vec<JoinItem> {
    if tab == JoinTab::Lan {
        return vec![JoinItem::Tabs];
    }
    let mut v = vec![JoinItem::Tabs, JoinItem::Input, JoinItem::Paste, JoinItem::Join];
    v.extend((0..rows).map(JoinItem::Row));
    v
}

pub(super) fn step(item: JoinItem, delta: i32, tab: JoinTab, rows: usize) -> JoinItem {
    let o = order(tab, rows);
    let i = o.iter().position(|j| *j == item).unwrap_or(0) as i32;
    o[(i + delta).rem_euclid(o.len() as i32) as usize]
}

/// Characters a code or an address may use.
fn join_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || matches!(c, '-' | '.' | ':' | ' ')
}

/// How the field draws a value: a whole SL1 invite short ("SL1-3A38…DC49"), anything else as typed.
pub(super) fn invite_display(value: &str) -> Option<String> {
    crate::iroh_transport::parse_invite(value).map(|_| crate::invite::short_invite(value))
}

/// What PASTE puts in the field: trimmed, upper case on the code tab.
pub(super) fn pasted(text: &str, tab: JoinTab) -> String {
    let t = text.trim();
    if tab == JoinTab::Code { t.to_uppercase() } else { t.to_string() }
}

#[derive(Component, Debug, Clone, Copy)]
pub(super) struct TabBtn(JoinTab);

/// A tab's body.
#[derive(Component, Debug, Clone, Copy)]
pub(super) struct Block(JoinTab);

/// A tab's help line (replaced by the error while there is one).
#[derive(Component, Debug, Clone, Copy)]
pub(super) struct BlockHelp(JoinTab);

#[derive(Component)]
pub(super) struct JoinBtn;

#[derive(Component)]
pub(super) struct RecentBlock;

#[derive(Component, Debug, Clone, Copy)]
pub(super) struct RecentRow(usize);

pub(super) fn spawn_flyout(r: &mut ChildSpawnerCommands, ctx: &Ctx, recent: &RecentServers, state: &MenuState) {
    let fonts = ctx.fonts;
    let port = ctx.data.net.port;
    r.spawn((
        super::Flyout(Sub::Join),
        panel_of(
            PanelKind::Flyout,
            Node {
                display: if state.sub == Sub::Join { Display::Flex } else { Display::None },
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
        p.spawn(fonts.role(TextRole::FlyoutTitle, "Join game"));
        super::close_button(p, fonts);
        p.spawn((
            FocusRing(Focus::Join(JoinItem::Tabs)),
            ring(),
            Node { margin: UiRect::top(px(18)), border: UiRect::bottom(px(1)), ..default() },
            BorderColor::all(STROKE_MID),
        ))
        .with_children(|t| {
            // No count until the LAN beacon exists.
            for (tab, label) in
                [(JoinTab::Code, "Join code"), (JoinTab::Ip, "Direct IP"), (JoinTab::Lan, "On your network")]
            {
                t.spawn((
                    underline_tab(fonts, label),
                    TabBtn(tab),
                    Click(MenuAction::Tab(tab)),
                    FocusTarget(Focus::Join(JoinItem::Tabs)),
                ));
            }
        });
        for tab in [JoinTab::Code, JoinTab::Ip] {
            let (label, placeholder, help, id, em) = match tab {
                JoinTab::Code => {
                    (copy::CODE_LABEL, copy::CODE_PLACEHOLDER, copy::CODE_HELP.to_string(), FieldId::JoinCode, None)
                }
                _ => (copy::IP_LABEL, copy::IP_PLACEHOLDER, copy::ip_help(port), FieldId::JoinIp, Some(0.08)),
            };
            p.spawn((
                Block(tab),
                Node {
                    display: if state.tab == tab { Display::Flex } else { Display::None },
                    flex_direction: FlexDirection::Column,
                    margin: UiRect::top(px(18)),
                    ..default()
                },
            ))
            .with_children(|b| {
                b.spawn(fonts.lbl(label));
                field::spawn_field(
                    b,
                    fonts,
                    FieldSpec {
                        id,
                        role: TextRole::CodeXl,
                        em,
                        tnum: true,
                        placeholder: placeholder.to_string(),
                        // "255.255.255.255:65535"
                        max_chars: 80,
                        filter: Some(join_char),
                        initial: String::new(),
                        // A pasted invite is 68 characters: show it short (it is never typed by hand).
                        display: Some(invite_display),
                    },
                    (
                        Node {
                            height: px(56),
                            margin: UiRect::top(px(8)),
                            padding: UiRect::horizontal(px(16)),
                            border: UiRect::all(px(1)),
                            align_items: AlignItems::Center,
                            overflow: Overflow::clip(),
                            ..default()
                        },
                        BackgroundColor(K45),
                        BorderColor::all(STROKE_HI),
                    ),
                    |f| {
                        f.spawn((
                            Button,
                            Node { margin: UiRect::left(Val::Auto), ..button_node(BtnSize::S) },
                            BackgroundColor(BTN.idle.bg),
                            BorderColor::all(BTN.idle.border),
                            BTN,
                            Click(MenuAction::Paste),
                            FocusTarget(Focus::Join(JoinItem::Paste)),
                            FocusRing(Focus::Join(JoinItem::Paste)),
                            ring(),
                            children![
                                (icon(ctx.images, Icon::Copy, 16.0, TEXT_HI), Ink),
                                (fonts.role(TextRole::BtnS, "Paste"), Ink),
                            ],
                        ));
                    },
                );
                b.spawn((
                    BlockHelp(tab),
                    fonts.role(TextRole::Help, help),
                    Node { margin: UiRect::top(px(8)), ..default() },
                ));
            });
        }
        // ON YOUR NETWORK: one row saying discovery is not built yet.
        p.spawn((
            Block(JoinTab::Lan),
            Node {
                display: if state.tab == JoinTab::Lan { Display::Flex } else { Display::None },
                height: px(46),
                margin: UiRect::top(px(18)),
                padding: UiRect::horizontal(px(10)),
                align_items: AlignItems::Center,
                border: UiRect::vertical(px(1)),
                ..default()
            },
            BorderColor::all(STROKE),
            children![fonts.role(TextRole::Help, copy::LAN_NOT_BUILT)],
        ));
        p.spawn(Node { column_gap: px(12), align_items: AlignItems::Center, margin: UiRect::top(px(18)), ..default() })
            .with_children(|a| {
                a.spawn((
                    button(fonts, "Join lobby", BtnKind::Primary, BtnSize::L),
                    JoinBtn,
                    Click(MenuAction::JoinLobby),
                    FocusTarget(Focus::Join(JoinItem::Join)),
                    FocusRing(Focus::Join(JoinItem::Join)),
                    ring(),
                ));
                a.spawn(keycap(fonts, "Enter", KeyStyle::Solid, 22.0));
            });
        p.spawn((
            RecentBlock,
            Node {
                display: if state.tab == JoinTab::Lan { Display::None } else { Display::Flex },
                flex_direction: FlexDirection::Column,
                margin: UiRect::top(px(26)),
                ..default()
            },
        ))
        .with_children(|b| {
            b.spawn(Node {
                justify_content: JustifyContent::SpaceBetween,
                align_items: AlignItems::Center,
                ..default()
            })
            .with_children(|h| {
                h.spawn(fonts.lbl("Recent"));
                h.spawn(fonts.micro("Ping · players"));
            });
            b.spawn((
                Node {
                    flex_direction: FlexDirection::Column,
                    margin: UiRect::top(px(8)),
                    border: UiRect::top(px(1)),
                    ..default()
                },
                BorderColor::all(STROKE),
            ))
            .with_children(|list| {
                let now = unix_now();
                for (i, s) in recent.servers.iter().take(RECENT_ROWS).enumerate() {
                    recent_row(list, fonts, i, s, now, ctx.data);
                }
                if recent.servers.is_empty() {
                    list.spawn((
                        Node {
                            height: px(46),
                            padding: UiRect::horizontal(px(10)),
                            align_items: AlignItems::Center,
                            border: UiRect::bottom(px(1)),
                            ..default()
                        },
                        BorderColor::all(STROKE),
                        children![fonts.role(TextRole::Help, copy::RECENT_EMPTY)],
                    ));
                }
            });
        });
    });
}

pub(super) fn unix_now() -> u64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or_default()
}

fn recent_row(list: &mut ChildSpawnerCommands, fonts: &UiFonts, i: usize, s: &RecentServer, now: u64, data: &Data) {
    // Ping and players need a status query to the host (not built): '—'. Private addresses read LAN.
    let lan = JoinCode::parse(&s.address, data.net.port).is_some_and(|a| is_lan_ip(a.ip()));
    let cell = |text: &'static str, color: Color| {
        (fonts.role_color(TextRole::NumCell, text, color), Node { justify_self: JustifySelf::End, ..default() })
    };
    list.spawn((
        Button,
        Node {
            display: Display::Grid,
            grid_template_columns: vec![
                GridTrack::flex(1.0),
                GridTrack::px(110.0),
                GridTrack::px(70.0),
                GridTrack::px(60.0),
            ],
            height: px(46),
            padding: UiRect::horizontal(px(10)),
            border: UiRect::bottom(px(1)),
            align_items: AlignItems::Center,
            ..default()
        },
        BackgroundColor(Color::NONE),
        BorderColor::all(STROKE),
        LIST_ROW,
        Active(false),
        RecentRow(i),
        Click(MenuAction::PickRecent(i)),
        FocusTarget(Focus::Join(JoinItem::Row(i))),
    ))
    .with_children(|row| {
        row.spawn(Node { flex_direction: FlexDirection::Column, overflow: Overflow::clip(), ..default() })
            .with_children(|n| {
                n.spawn((fonts.role(TextRole::ListName, s.name.to_uppercase()), TextLayout::no_wrap()));
                n.spawn((
                    fonts.role(TextRole::Sub, copy::recent_subline(&s.map, &s.address, s.by_ip, s.last_joined, now)),
                    TextLayout::no_wrap(),
                ));
            });
        row.spawn(cell("—", TEXT_MID));
        row.spawn(cell("—", TEXT_MID));
        if lan {
            row.spawn(cell("LAN", ALLY));
        } else {
            row.spawn(cell("—", TEXT_LOW));
        }
    });
}

/// JOIN LOBBY, PASTE, tabs and recent rows.
#[allow(clippy::too_many_arguments)]
pub(super) fn actions(
    mut actions: MessageReader<MenuAction>,
    mut state: ResMut<MenuState>,
    mut session: ResMut<Session>,
    mut requests: MessageWriter<NetRequest>,
    mut editors: Query<(&FieldEditor, &mut EditableText)>,
    recent: Res<RecentServers>,
    clipboard: Option<ResMut<Clipboard>>,
) {
    let mut clipboard = clipboard;
    for action in actions.read() {
        match *action {
            MenuAction::Tab(tab) => {
                state.tab = tab;
                state.focus =
                    if tab == JoinTab::Lan { Focus::Join(JoinItem::Tabs) } else { Focus::Join(JoinItem::Input) };
            }
            MenuAction::JoinLobby => {
                let Some(id) = state.tab.field() else { continue };
                let text =
                    editors.iter().find(|(f, _)| f.0 == id).map(|(_, e)| e.value().to_string()).unwrap_or_default();
                if text.trim().is_empty() {
                    session.status = Some(copy::EMPTY_JOIN.into());
                    session.host_error = false;
                } else {
                    requests.write(NetRequest::Join { address: text.trim().to_string() });
                }
            }
            MenuAction::Paste => {
                if state.tab.field().is_none() {
                    continue;
                }
                let Some(cb) = clipboard.as_deref_mut() else { continue };
                let Some(Ok(text)) = cb.fetch_text().poll_result() else { continue };
                if text.trim().is_empty() {
                    continue;
                }
                // An invite pasted on DIRECT IP belongs on the invite tab.
                if crate::iroh_transport::parse_invite(&text).is_some() {
                    state.tab = JoinTab::Code;
                }
                let Some(id) = state.tab.field() else { continue };
                let text = pasted(&text, state.tab);
                for (f, mut ed) in &mut editors {
                    if f.0 == id {
                        field::set_value(&mut ed, &text);
                    }
                }
                state.focus = Focus::Join(JoinItem::Input);
            }
            MenuAction::PickRecent(i) => {
                let Some(s) = recent.servers.get(i) else { continue };
                state.tab = if s.by_ip { JoinTab::Ip } else { JoinTab::Code };
                let id = if s.by_ip { FieldId::JoinIp } else { FieldId::JoinCode };
                for (f, mut ed) in &mut editors {
                    if f.0 == id {
                        field::set_value(&mut ed, &s.address);
                    }
                }
                state.selected_recent = Some(i);
                state.focus = Focus::Join(JoinItem::Join);
            }
            MenuAction::JoinRecent(i) => {
                if let Some(s) = recent.servers.get(i) {
                    requests.write(NetRequest::Join { address: s.address.clone() });
                }
            }
            _ => {}
        }
    }
}

/// ←/→ switch tabs while the tab row has focus.
pub(super) fn keys(keys: Res<ButtonInput<KeyCode>>, mut state: ResMut<MenuState>, screens: Res<Screens>) {
    if !screens.is_empty() || state.focus != Focus::Join(JoinItem::Tabs) {
        return;
    }
    let delta = if keys.just_pressed(KeyCode::ArrowRight) {
        1
    } else if keys.just_pressed(KeyCode::ArrowLeft) {
        -1
    } else {
        return;
    };
    let i = JoinTab::ALL.iter().position(|t| *t == state.tab).unwrap_or(0) as i32;
    let tab = JoinTab::ALL[(i + delta).clamp(0, JoinTab::ALL.len() as i32 - 1) as usize];
    if state.tab != tab {
        state.tab = tab;
    }
    state.focus_visible = true;
}

#[allow(clippy::type_complexity)]
fn visuals(
    state: Res<MenuState>,
    mut session: ResMut<Session>,
    mut tabs: Query<(&TabBtn, &mut Active), Without<RecentRow>>,
    mut blocks: Query<(&Block, &mut Node), Without<RecentBlock>>,
    mut recent_block: Query<&mut Node, With<RecentBlock>>,
    join: Query<(Entity, Has<Disabled>), With<JoinBtn>>,
    mut rows: Query<(&RecentRow, &mut Active), Without<TabBtn>>,
    mut fields: Query<(&Field, &mut BorderColor)>,
    mut helps: Query<(&BlockHelp, &mut Text, &mut TextColor)>,
    spawned: Query<(), Added<TabBtn>>,
    data: Res<Data>,
    mut commands: Commands,
) {
    // Typing clears a join error and brings the help back.
    if fields.iter().any(|(f, _)| f.edited && matches!(f.id, FieldId::JoinCode | FieldId::JoinIp))
        && session.status.is_some()
        && !session.host_error
    {
        session.status = None;
    }
    let error = session.status.as_deref().filter(|_| !session.host_error);
    let error_field = state.tab.field();
    for (f, mut border) in &mut fields {
        if !matches!(f.id, FieldId::JoinCode | FieldId::JoinIp) {
            continue;
        }
        let bad = error.is_some() && Some(f.id) == error_field;
        let want = BorderColor::all(if bad { BAD } else { STROKE_HI });
        if *border != want {
            *border = want;
        }
    }
    for (h, mut t, mut c) in &mut helps {
        let (copy, color) = match error {
            Some(e) if h.0 == state.tab => (e.to_string(), BAD),
            _ if h.0 == JoinTab::Code => (copy::CODE_HELP.to_string(), TEXT_MID),
            _ => (copy::ip_help(data.net.port), TEXT_MID),
        };
        if t.0 != copy {
            t.0 = copy;
            c.0 = color;
        }
    }
    // On a change of the menu state, and once when the flyout is spawned (the first frame's change of the
    // state lands before the new entities exist, which left the open tab unlit).
    if !state.is_changed() && spawned.is_empty() {
        return;
    }
    for (t, mut on) in &mut tabs {
        let want = t.0 == state.tab;
        if on.0 != want {
            on.0 = want;
        }
    }
    for (b, mut node) in &mut blocks {
        node.display = if b.0 == state.tab { Display::Flex } else { Display::None };
    }
    for mut node in &mut recent_block {
        node.display = if state.tab == JoinTab::Lan { Display::None } else { Display::Flex };
    }
    let lan = state.tab == JoinTab::Lan;
    for (e, disabled) in &join {
        if lan && !disabled {
            commands.entity(e).insert(Disabled);
        } else if !lan && disabled {
            commands.entity(e).remove::<Disabled>();
        }
    }
    for (r, mut on) in &mut rows {
        let want = state.selected_recent == Some(r.0) || state.focus == Focus::Join(JoinItem::Row(r.0));
        if on.0 != want {
            on.0 = want;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn join_focus_order_per_tab() {
        assert_eq!(order(JoinTab::Lan, 3), vec![JoinItem::Tabs]);
        assert_eq!(order(JoinTab::Code, 2).len(), 6);
        assert_eq!(step(JoinItem::Join, 1, JoinTab::Code, 2), JoinItem::Row(0));
        assert_eq!(step(JoinItem::Row(1), 1, JoinTab::Code, 2), JoinItem::Tabs, "wraps");
        assert_eq!(step(JoinItem::Tabs, -1, JoinTab::Ip, 0), JoinItem::Join);
        let r = RecentServers { servers: vec![RecentServer::default(); 5] };
        assert_eq!(visible_rows(&r), RECENT_ROWS);
    }

    #[test]
    fn paste_trims_and_upper_cases_codes() {
        assert_eq!(pasted("  6000-105e-pc\n", JoinTab::Code), "6000-105E-PC");
        assert_eq!(pasted(" 192.168.1.20:47820 ", JoinTab::Ip), "192.168.1.20:47820");
        assert!("6000-105E-PC".chars().all(join_char) && "10.0.0.2:47820".chars().all(join_char));
        assert!(!join_char('/'));
    }

    #[test]
    fn a_pasted_invite_shows_short() {
        let invite = crate::iroh_transport::invite(iroh::SecretKey::from_bytes(&[0x3A; 32]).public());
        assert!(invite.chars().all(join_char), "an invite can be pasted into the field");
        let shown = invite_display(&pasted(&invite.to_lowercase(), JoinTab::Code)).unwrap();
        assert_eq!(shown, crate::invite::short_invite(&invite));
        assert_eq!(invite_display("6000-105E-PC"), None, "codes and addresses show as typed");
        assert_eq!(invite_display(&invite[..20]), None, "half an invite too");
    }
}
