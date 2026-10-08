//! The lobby (hub spec 05, mockup 06): the room before a deathmatch. Team deathmatch shows both teams with
//! halo, ping and READY; free-for-all shows one player list with its seats (no teams, no SWITCH TEAM). Then
//! how friends join, with COPY; the match settings, where the host picks the mode; and LEAVE, LOADOUT,
//! SWITCH TEAM (teams only), READY and (host only) START MATCH. It is a screen over the match while the
//! match is in `MatchPhase::Lobby`, so the match underneath takes no input; START MATCH, or the end of a
//! match (back here), moves everyone on.
//!
//! Not yet: chat, the host editing the other match settings, moving or kicking players.

use crate::AppState;
use crate::config::{Cli, Data};
use crate::invite::{CopyInvite, InviteCopied, JoinInfo};
use crate::net::{NetRequest, Role, Session};
use crate::screens::{EscPress, EscSystems, Screen, ScreenRoot, Screens, screen_on_top};
use crate::ui_kit::*;
use bevy::prelude::*;
use lightyear::prelude::client::Client;
use lightyear::prelude::{Controlled, MessageSender};
use vetf_net::*;
use vetf_sim::level::Team;

pub struct LobbyPlugin;

impl Plugin for LobbyPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(
            Update,
            (
                follow_phase,
                spawn_root,
                // Esc does nothing here: LEAVE leaves (the screens over the lobby close with Esc as usual).
                keep_esc.in_set(EscSystems::Top).run_if(screen_on_top(Screen::Lobby)),
                buttons,
                mode_toggle,
                demo,
                refresh,
            )
                .chain()
                .run_if(in_state(AppState::InGame)),
        );
    }
}

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
enum LobbyBtn {
    Leave,
    Loadout,
    SwitchTeam,
    Ready,
    Start,
    Copy,
}

/// The lobby name and the status line under it.
#[derive(Component)]
struct LobbyName;
#[derive(Component)]
struct LobbyStatus;
/// A team's column (rebuilt).
#[derive(Component)]
struct TeamCol(Team);
/// How friends join (rebuilt), and the COPY button's row.
#[derive(Component)]
struct JoinBox;
/// The match settings (rebuilt: they come from the replicated match).
#[derive(Component)]
struct SettingsBox;
/// "2/3 READY" next to START MATCH.
#[derive(Component)]
struct ReadyCount;
/// Shown to non-hosts where START MATCH is.
#[derive(Component)]
struct WaitingForHost;
/// The host's MODE control in the match settings (team deathmatch or free-for-all).
#[derive(Component)]
struct ModeToggle;

/// The modes the host can switch the lobby between, in the toggle's order.
const MODES: [(MatchMode, &str); 2] = [(MatchMode::Tdm, "Team deathmatch"), (MatchMode::Ffa, "Free-for-all")];

/// The mode's name in the lobby and on the scoreboard.
pub fn mode_title(mode: MatchMode) -> &'static str {
    match mode {
        MatchMode::Tdm => "TEAM DEATHMATCH",
        MatchMode::Ffa => "FREE-FOR-ALL",
        MatchMode::Range => "GUN RANGE",
    }
}

/// The lobby is open exactly while the match is in its lobby phase.
fn follow_phase(matches: Query<&MatchState>, mut screens: ResMut<Screens>) {
    let lobby = matches.iter().next().is_some_and(|m| m.phase == MatchPhase::Lobby);
    if lobby && !screens.contains(Screen::Lobby) {
        // Back from a finished match: whatever was open (the ESC menu, a loadout) makes way.
        screens.clear();
        screens.push(Screen::Lobby);
    } else if !lobby && screens.contains(Screen::Lobby) {
        screens.close(Screen::Lobby);
    }
}

fn keep_esc(mut esc: ResMut<EscPress>) {
    esc.take();
}

fn spawn_root(
    screens: Res<Screens>,
    roots: Query<&ScreenRoot>,
    session: Res<Session>,
    fonts: Res<UiFonts>,
    mut commands: Commands,
) {
    if !screens.contains(Screen::Lobby) || roots.iter().any(|r| r.0 == Screen::Lobby) {
        return;
    }
    let depth = screens.iter().position(|s| s.same_kind(Screen::Lobby)).unwrap_or(0) as i32;
    let host = session.role == Role::Host;
    let fonts = &*fonts;
    commands
        .spawn((
            ScreenRoot(Screen::Lobby),
            GlobalZIndex(100 + depth * 10),
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
            BackgroundColor(BG0),
        ))
        .with_children(|r| {
            r.spawn(page_background(40.0, 20.0, [(0x151C26, 0.0), (0x090C11, 60.0), (0x06080B, 100.0)]));
            top_bar(r, fonts);
            // Teams: two columns, your team's colour is ALLY wherever it sits.
            r.spawn(Node {
                display: Display::Grid,
                grid_template_columns: vec![GridTrack::flex(1.0), GridTrack::flex(1.0)],
                column_gap: px(20),
                width: px(1180),
                ..abs(Some(48.0), None, Some(124.0), None)
            })
            .with_children(|t| {
                t.spawn((TeamCol(Team::A), Node { flex_direction: FlexDirection::Column, ..default() }));
                t.spawn((TeamCol(Team::B), Node { flex_direction: FlexDirection::Column, ..default() }));
            });
            r.spawn(panel_of(
                PanelKind::Base,
                Node {
                    width: px(600),
                    flex_direction: FlexDirection::Column,
                    padding: UiRect::axes(px(20), px(18)),
                    row_gap: px(10),
                    ..abs(None, Some(48.0), Some(124.0), None)
                },
            ))
            .with_children(|p| {
                p.spawn(fonts.role(TextRole::Subtitle, "Match settings"));
                if host {
                    // Only the host changes the mode; everyone sees it in the rows below.
                    p.spawn((
                        ModeToggle,
                        SegValue(0),
                        Node {
                            height: px(36),
                            border: UiRect::all(px(1)),
                            align_self: AlignSelf::Start,
                            margin: UiRect::vertical(px(4)),
                            ..default()
                        },
                        BorderColor::all(STROKE_HI),
                    ))
                    .with_children(|t| {
                        for (i, (_, label)) in MODES.iter().enumerate() {
                            t.spawn((segment(fonts, label, TOGGLE, 34.0, false), SegOption(i)));
                        }
                    });
                }
                p.spawn((SettingsBox, Node { flex_direction: FlexDirection::Column, row_gap: px(8), ..default() }));
            });
            r.spawn(panel_of(
                PanelKind::Base,
                Node {
                    width: px(1180),
                    flex_direction: FlexDirection::Column,
                    padding: UiRect::axes(px(16), px(14)),
                    row_gap: px(8),
                    ..abs(Some(48.0), None, None, Some(112.0))
                },
            ))
            .with_children(|p| {
                p.spawn(fonts.role(TextRole::Subtitle, "Connection"));
                p.spawn((JoinBox, Node { flex_direction: FlexDirection::Column, row_gap: px(6), ..default() }));
                p.spawn(Node { margin: UiRect::top(px(4)), ..default() }).with_children(|b| {
                    b.spawn((LobbyBtn::Copy, button(fonts, "Copy invite", BtnKind::Normal, BtnSize::S)));
                });
            });
            bottom_bar(r, fonts, host);
        });
}

fn top_bar(r: &mut ChildSpawnerCommands, fonts: &UiFonts) {
    r.spawn((
        Node {
            height: px(96),
            align_items: AlignItems::Center,
            padding: UiRect::horizontal(px(48)),
            column_gap: px(32),
            border: UiRect::bottom(px(1)),
            ..abs(Some(0.0), Some(0.0), Some(0.0), None)
        },
        BorderColor::all(STROKE),
    ))
    .with_children(|t| {
        t.spawn(fonts.role(TextRole::ScreenTitle, "Lobby"));
        t.spawn(Node { flex_direction: FlexDirection::Column, row_gap: px(4), ..default() }).with_children(|c| {
            c.spawn((LobbyName, fonts.role(TextRole::LobbyName, "")));
            c.spawn((LobbyStatus, fonts.role(TextRole::Micro, "")));
        });
    });
}

fn bottom_bar(r: &mut ChildSpawnerCommands, fonts: &UiFonts, host: bool) {
    r.spawn((
        Node {
            height: px(88),
            align_items: AlignItems::Center,
            column_gap: px(12),
            padding: UiRect::horizontal(px(48)),
            border: UiRect::top(px(1)),
            ..abs(Some(0.0), Some(0.0), None, Some(0.0))
        },
        BorderColor::all(STROKE),
        BackgroundColor(BOTTOM_BAR),
    ))
    .with_children(|b| {
        b.spawn((LobbyBtn::Leave, button(fonts, "Leave", BtnKind::Danger, BtnSize::M)));
        b.spawn(Node { flex_grow: 1.0, ..default() });
        b.spawn((LobbyBtn::Loadout, button(fonts, "Loadout", BtnKind::Normal, BtnSize::M)));
        b.spawn((LobbyBtn::SwitchTeam, button(fonts, "Switch team", BtnKind::Normal, BtnSize::M)));
        b.spawn((LobbyBtn::Ready, button(fonts, "Ready", BtnKind::Ally, BtnSize::M)));
        b.spawn((ReadyCount, fonts.role(TextRole::Hint, ""), Node { margin: UiRect::horizontal(px(6)), ..default() }));
        if host {
            b.spawn((LobbyBtn::Start, button(fonts, "Start match", BtnKind::Primary, BtnSize::M)));
        } else {
            b.spawn((WaitingForHost, fonts.role(TextRole::Hint, "Waiting for the host to start")));
        }
    });
}

fn buttons(
    q: Query<(&Interaction, &LobbyBtn), Changed<Interaction>>,
    me: Query<&PlayerNet, With<Controlled>>,
    mut screens: ResMut<Screens>,
    mut requests: MessageWriter<NetRequest>,
    mut copy: MessageWriter<CopyInvite>,
    mut senders: Query<&mut MessageSender<LobbyAction>, With<Client>>,
) {
    if screens.top() != Some(Screen::Lobby) {
        return;
    }
    for (i, b) in &q {
        if *i != Interaction::Pressed {
            continue;
        }
        let send = match b {
            LobbyBtn::Leave => {
                requests.write(NetRequest::Leave { reason: None });
                None
            }
            LobbyBtn::Loadout => {
                screens.push(Screen::Loadout);
                None
            }
            LobbyBtn::Copy => {
                copy.write(CopyInvite);
                None
            }
            LobbyBtn::SwitchTeam => Some(LobbyAction::SwitchTeam),
            LobbyBtn::Ready => Some(LobbyAction::Ready(!me.iter().next().is_some_and(|n| n.ready))),
            LobbyBtn::Start => Some(LobbyAction::Start),
        };
        if let Some(action) = send {
            for mut s in &mut senders {
                s.send::<ReliableChannel>(action);
            }
        }
    }
}

/// The host's MODE toggle: a click asks the host to switch the lobby (the toggle then follows the match's
/// mode, so a refused switch, e.g. too many players for free-for-all, springs back).
fn mode_toggle(
    presses: Query<(&Interaction, &SegOption, &ChildOf), Changed<Interaction>>,
    toggles: Query<(), With<ModeToggle>>,
    screens: Res<Screens>,
    time: Res<Time>,
    mut asked: Local<f32>,
    mut groups: Query<&mut SegValue, With<ModeToggle>>,
    matches: Query<&MatchState>,
    mut senders: Query<&mut MessageSender<LobbyAction>, With<Client>>,
) {
    if screens.top() == Some(Screen::Lobby) {
        for (i, opt, parent) in &presses {
            if *i != Interaction::Pressed || !toggles.contains(parent.parent()) {
                continue;
            }
            let Some((mode, _)) = MODES.get(opt.0) else { continue };
            *asked = time.elapsed_secs();
            for mut s in &mut senders {
                s.send::<ReliableChannel>(LobbyAction::SetMode(*mode));
            }
        }
    }
    // Follow the match (not while a click is on its way).
    let Some(m) = matches.iter().next() else { return };
    if time.elapsed_secs() - *asked < 1.0 {
        return;
    }
    let want = MODES.iter().position(|(mode, _)| *mode == m.mode).unwrap_or(0);
    for mut v in &mut groups {
        if v.0 != want {
            v.0 = want;
        }
    }
}

/// `--demo-ui lobby-ready | lobby-switch | lobby-start | lobby-ffa`: press READY; SWITCH TEAM then READY; READY
/// then START MATCH; or (the host) switch to free-for-all, READY and START MATCH, a few seconds in (demo runs
/// ignore the desktop's mouse), to test the lobby over the network.
fn demo(
    cli: Res<Cli>,
    time: Res<Time>,
    screens: Res<Screens>,
    mut step: Local<usize>,
    mut senders: Query<&mut MessageSender<LobbyAction>, With<Client>>,
) {
    let plan: &[(f32, LobbyAction)] = match cli.demo_ui.as_deref() {
        Some("lobby-ready") => &[(4.0, LobbyAction::Ready(true))],
        Some("lobby-switch") => &[(4.0, LobbyAction::SwitchTeam), (5.0, LobbyAction::Ready(true))],
        Some("lobby-start") => &[(4.0, LobbyAction::Ready(true)), (7.0, LobbyAction::Start)],
        // The host switches a team deathmatch lobby to free-for-all, readies and starts it.
        Some("lobby-ffa") => {
            &[(4.0, LobbyAction::SetMode(MatchMode::Ffa)), (5.0, LobbyAction::Ready(true)), (12.0, LobbyAction::Start)]
        }
        _ => return,
    };
    let Some((at, action)) = plan.get(*step) else { return };
    if screens.contains(Screen::Lobby) && time.elapsed_secs() >= *at {
        *step += 1;
        info!("--demo-ui: {action:?}");
        for mut s in &mut senders {
            s.send::<ReliableChannel>(*action);
        }
    }
}

/// One player's row.
struct Seat {
    id: u64,
    name: String,
    me: bool,
    host: bool,
    team: Option<Team>,
    tiers: vetf_sim::ZoneTable<u8>,
    weight: vetf_sim::data::WeightClass,
    ping_ms: u16,
    ready: bool,
}

#[allow(clippy::too_many_arguments)]
fn refresh(
    screens: Res<Screens>,
    players: Query<(&PlayerId, &PlayerInfo, &PlayerLoadout, Option<&PlayerNet>, Has<Controlled>)>,
    matches: Query<&MatchState>,
    session: Res<Session>,
    data: Res<Data>,
    copied: Res<InviteCopied>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    time: Res<Time>,
    cols: Query<(Entity, &TeamCol)>,
    join_box: Query<Entity, With<JoinBox>>,
    settings_box: Query<Entity, With<SettingsBox>>,
    mut btns: Query<(&LobbyBtn, &Children, &mut Node)>,
    mut texts: ParamSet<(
        Query<&mut Text, With<LobbyName>>,
        Query<&mut Text, With<LobbyStatus>>,
        Query<&mut Text, With<ReadyCount>>,
        Query<&mut Text>,
    )>,
    mut next: Local<f32>,
    mut commands: Commands,
) {
    if !screens.contains(Screen::Lobby) || cols.is_empty() || time.elapsed_secs() < *next {
        return;
    }
    *next = time.elapsed_secs() + 0.25;
    let Some(m) = matches.iter().next() else { return };
    let seats: Vec<Seat> = players
        .iter()
        .map(|(id, info, loadout, net, me)| Seat {
            id: id.0,
            name: info.name.to_uppercase(),
            me,
            host: id.0 == 0,
            team: info.team,
            tiers: loadout.0.halo.tiers,
            weight: loadout.0.weight,
            ping_ms: net.map_or(0, |n| n.ping_ms),
            ready: net.is_some_and(|n| n.ready),
        })
        .collect();
    let my_team = seats.iter().find(|s| s.me).and_then(|s| s.team);
    let i_am_ready = seats.iter().any(|s| s.me && s.ready);
    let ready = seats.iter().filter(|s| s.ready).count();
    let per_team = (m.max_players / 2).max(1) as usize;
    let teams = m.has_teams();

    for mut t in &mut texts.p0() {
        t.0 = m.lobby_name.to_uppercase();
    }
    for mut t in &mut texts.p1() {
        let mode = mode_title(m.mode);
        t.0 = format!("{mode} · {} · {}/{} PLAYERS", m.map.to_uppercase(), seats.len(), m.max_players);
    }
    // No teams to switch between in free-for-all.
    for (b, _, mut node) in &mut btns {
        let display = if *b == LobbyBtn::SwitchTeam && !teams { Display::None } else { Display::Flex };
        if node.display != display {
            node.display = display;
        }
    }
    for mut t in &mut texts.p2() {
        t.0 = format!("{ready}/{} READY", seats.len());
    }
    // Button labels that follow the state.
    let join = JoinInfo::of(&session, data.net.port);
    let copy_label = if copied.recent(time.elapsed_secs()) { "Copied" } else { join.copy_label() };
    for (b, children, _) in &btns {
        let label = match b {
            LobbyBtn::Ready if i_am_ready => "Cancel ready",
            LobbyBtn::Ready => "Ready",
            LobbyBtn::Copy => copy_label,
            _ => continue,
        };
        for c in children.iter() {
            if let Ok(mut t) = texts.p3().get_mut(c) {
                let want = TextRole::Btn.case(label);
                if t.0 != want {
                    t.0 = want;
                }
            }
        }
    }

    let fonts = &*fonts;
    let images = &*images;
    if teams {
        for (e, col) in &cols {
            let ally = my_team.is_none_or(|t| t == col.0);
            let members: Vec<&Seat> = seats.iter().filter(|s| s.team == Some(col.0)).collect();
            commands.entity(e).despawn_children().with_children(|c| {
                team_header(c, fonts, col.0, ally, members.len(), per_team);
                for s in &members {
                    seat_row(c, fonts, images, s);
                }
                for _ in members.len()..per_team {
                    open_slot(c, fonts);
                }
            });
        }
    } else {
        // Free-for-all: one list of every seat (the host first, then in join order), down the left column
        // and on down the right one.
        let mut list: Vec<&Seat> = seats.iter().collect();
        list.sort_by_key(|s| (!s.host, s.id));
        let total = (m.max_players as usize).max(list.len());
        let split = total.div_ceil(2);
        for (e, col) in &cols {
            let range = if col.0 == Team::A { 0..split } else { split..total };
            let first = col.0 == Team::A;
            commands.entity(e).despawn_children().with_children(|c| {
                ffa_header(c, fonts, first, list.len(), m.max_players as usize);
                for i in range {
                    match list.get(i) {
                        Some(s) => seat_row(c, fonts, images, s),
                        None => open_slot(c, fonts),
                    }
                }
            });
        }
    }
    for e in &join_box {
        commands.entity(e).despawn_children().with_children(|j| {
            j.spawn(fonts.role(TextRole::Lbl, join.label()));
            j.spawn(fonts.text(join.headline(), Face::Display, 700, 26.0, TEXT_HI, 0.04));
            if let Some(d) = join.detail() {
                j.spawn(fonts.role(TextRole::Help, d));
            }
        });
    }
    let rules = data.rules.deathmatch(m.mode);
    let rows = [
        ("Map", m.map.to_uppercase()),
        ("Mode", mode_title(m.mode).to_string()),
        (
            "Score limit",
            if teams { format!("FIRST TO {}", m.score_limit) } else { format!("FIRST TO {} KILLS", m.score_limit) },
        ),
        ("Time limit", format!("{} MIN", (m.time_left_s / 60.0).round() as u32)),
        (
            "Players",
            if teams {
                format!("{} V {}", per_team, per_team)
            } else {
                format!("{} · EVERYONE FOR THEMSELVES", m.max_players)
            },
        ),
        ("Respawn", format!("{} S", rules.respawn_s)),
        ("Kill refill", format!("{} MAGAZINE", rules.kill_refill_mags)),
    ];
    for e in &settings_box {
        commands.entity(e).despawn_children().with_children(|s| {
            for (k, v) in &rows {
                s.spawn((
                    Node {
                        justify_content: JustifyContent::SpaceBetween,
                        padding: UiRect::vertical(px(6)),
                        border: UiRect::bottom(px(1)),
                        ..default()
                    },
                    BorderColor::all(STROKE),
                ))
                .with_children(|row| {
                    row.spawn(fonts.role(TextRole::RowLabel, *k));
                    row.spawn(fonts.text(v.clone(), Face::Display, 600, 17.0, TEXT_HI, 0.06));
                });
            }
            s.spawn(fonts.role(TextRole::Help, "Only the host can start the match."));
        });
    }
}

fn team_header(c: &mut ChildSpawnerCommands, fonts: &UiFonts, team: Team, ally: bool, n: usize, per_team: usize) {
    let color = if ally { ALLY } else { ENEMY };
    let name = match team {
        Team::A => "Team A",
        Team::B => "Team B",
    };
    c.spawn(Node { flex_direction: FlexDirection::Column, margin: UiRect::bottom(px(6)), ..default() }).with_children(
        |h| {
            h.spawn(Node {
                justify_content: JustifyContent::SpaceBetween,
                align_items: AlignItems::FlexEnd,
                ..default()
            })
            .with_children(|r| {
                r.spawn(fonts.role_color(TextRole::TeamName, name, color));
                r.spawn(fonts.role(TextRole::Hint, format!("{n}/{per_team}")));
            });
            h.spawn((Node { height: px(3), margin: UiRect::top(px(8)), ..default() }, BackgroundColor(color)));
        },
    );
}

/// Free-for-all's list header over both columns: the title and seat count on the left, an empty header on
/// the right so the rows line up; the rule in the enemy colour (everyone else is one).
fn ffa_header(c: &mut ChildSpawnerCommands, fonts: &UiFonts, first: bool, n: usize, seats: usize) {
    c.spawn(Node { flex_direction: FlexDirection::Column, margin: UiRect::bottom(px(6)), ..default() }).with_children(
        |h| {
            h.spawn(Node {
                justify_content: JustifyContent::SpaceBetween,
                align_items: AlignItems::FlexEnd,
                ..default()
            })
            .with_children(|r| {
                let (title, count) = if first {
                    ("Free-for-all".to_string(), format!("{n}/{seats}"))
                } else {
                    (" ".into(), String::new())
                };
                r.spawn(fonts.role_color(TextRole::TeamName, title, TEXT_HI));
                r.spawn(fonts.role(TextRole::Hint, count));
            });
            h.spawn((Node { height: px(3), margin: UiRect::top(px(8)), ..default() }, BackgroundColor(ENEMY)));
        },
    );
}

fn seat_row(c: &mut ChildSpawnerCommands, fonts: &UiFonts, images: &UiImages, s: &Seat) {
    let bg = if s.me { hexa(0x52E5A5, 0.16) } else { white(0.035) };
    c.spawn((
        Node {
            height: px(64),
            margin: UiRect::top(px(6)),
            padding: UiRect::horizontal(px(14)),
            column_gap: px(14),
            align_items: AlignItems::Center,
            ..default()
        },
        BackgroundColor(bg),
    ))
    .with_children(|row| {
        row.spawn((
            Node {
                width: px(34),
                height: px(34),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                border_radius: BorderRadius::all(px(3)),
                ..default()
            },
            BackgroundColor(AGENT_KESTREL),
            children![fonts.text("K", Face::Display, 700, 16.0, ICON_CUT, 0.0)],
        ));
        row.spawn(Node { flex_direction: FlexDirection::Column, row_gap: px(4), flex_grow: 1.0, ..default() })
            .with_children(|n| {
                n.spawn(Node { column_gap: px(8), align_items: AlignItems::Center, ..default() }).with_children(|t| {
                    t.spawn(fonts.text(s.name.clone(), Face::Display, 700, 20.0, TEXT_HI, 0.04));
                    let tag = |x: &str| fonts.text(x.to_string(), Face::Display, 600, 12.0, TEXT_MID, 0.14);
                    if s.host {
                        t.spawn(icon(images, Icon::Crown, 14.0, hex(0xFFCE50)));
                        t.spawn(tag("HOST"));
                    }
                    if s.me {
                        t.spawn(tag("· YOU"));
                    }
                });
                n.spawn(Node { column_gap: px(6), align_items: AlignItems::Center, ..default() }).with_children(|h| {
                    h.spawn(arc_chip(images, s.tiers));
                    h.spawn(weight_squares(weight_lit(s.weight)));
                });
            });
        row.spawn(fonts.text(format!("{} MS", s.ping_ms), Face::Display, 600, 15.0, TEXT_MID, 0.06));
        let (label, color) = if s.ready { ("READY", ALLY) } else { ("NOT READY", TEXT_LOW) };
        row.spawn((
            Node {
                width: px(110),
                height: px(28),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                border: UiRect::all(px(1)),
                ..default()
            },
            BorderColor::all(color),
            children![fonts.text(label, Face::Display, 700, 13.0, color, 0.14)],
        ));
    });
}

fn open_slot(c: &mut ChildSpawnerCommands, fonts: &UiFonts) {
    c.spawn((
        Node {
            height: px(64),
            margin: UiRect::top(px(6)),
            padding: UiRect::horizontal(px(14)),
            align_items: AlignItems::Center,
            border: UiRect::all(px(1)),
            ..default()
        },
        BorderColor::all(STROKE),
        children![fonts.role(TextRole::Hint, "Open slot")],
    ));
}
