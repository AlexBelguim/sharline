//! The in-match ESC menu (hub spec 14-16, mockups 09 / 09b): `Screen::Esc` over the running match. On the
//! left RESUME, LOADOUT (next spawn), SETTINGS and CONTROLS (the keybinds tab); for the host a group with
//! PLAYERS, RESTART MATCH and BACK TO LOBBY; then STOP HOSTING, or LEAVE MATCH for a client. On the right a
//! card with the match: mode and map, score and clock, how friends join, players, server, ping and your
//! loadout.
//!
//! - The match does not pause (a listen server). The menu only takes the player's input away
//!   (`client::gather_input` reads nothing while a screen is open), and the cursor follows the stack.
//! - Esc is RESUME, and Esc on a confirm modal is CANCEL: both are the stack's default BACK
//!   (`screens::back_on_esc`), so this module never reads Esc.
//! - STOP HOSTING, LEAVE MATCH and RESTART MATCH (RESET RANGE in the gun range) ask first, in one confirm
//!   modal (`Screen::Confirm`) with their own copy and accent.
//!
//! Not yet: PLAYERS (needs kick and move on the host) and BACK TO LOBBY in the gun range (it has no lobby)
//! are shown dimmed. Clients are not told why the host left (a `HostClosing` message): they read "The host
//! closed the connection."

use crate::AppState;
use crate::config::{Cli, Data};
use crate::invite::{CopyInvite, InviteCopied, JoinInfo};
use crate::loadout::{ActiveLoadout, LoadoutSummary, summary};
use crate::net::{NetRequest, Role, Session};
use crate::screens::{ConfirmKind, Screen, ScreenRoot, Screens, SettingsTab};
use crate::server::{ServerPlayer, is_hosting};
use crate::ui_kit::*;
use bevy::prelude::*;
use bevy::ui::{ColorStop, InterpolationColorSpace, LinearGradient};
use lightyear::prelude::Controlled;
use std::collections::VecDeque;
use std::time::Instant;
use vetf_net::*;
use vetf_sim::GameData;
use vetf_sim::data::WeightClass;
use vetf_sim::level::Team;

pub struct EscMenuPlugin;

impl Plugin for EscMenuPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<EscUi>()
            .init_resource::<ModalUi>()
            .init_resource::<TickCpu>()
            .add_systems(FixedFirst, tick_start.run_if(is_hosting))
            .add_systems(FixedLast, tick_end.run_if(is_hosting))
            .add_systems(
                Update,
                (demo, spawn_menu, spawn_modal, menu_input, modal_input, row_looks, modal_looks, refresh_card)
                    .chain()
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

// ---------------------------------------------------------------------------------------------- rows

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum Item {
    Resume,
    Loadout,
    Settings,
    Controls,
    Players,
    Restart,
    Lobby,
    /// STOP HOSTING for the host, LEAVE MATCH for a client.
    Danger,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Group {
    /// 60 px rows, 36 px labels.
    Main,
    /// The host's group: 46 px rows, 24 px labels, under a separator and a micro label.
    Host,
    /// The red row at the bottom.
    Danger,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct RowSpec {
    item: Item,
    label: &'static str,
    /// The right-hand hint (RESUME shows an ESC key cap instead).
    hint: &'static str,
    group: Group,
    enabled: bool,
}

/// The rows for the host or a client, in team deathmatch or the gun range. A feature the prototype lacks
/// is a dimmed row with the hint NOT YET, never a hidden one.
fn rows(host: bool, range: bool) -> Vec<RowSpec> {
    let row = |item, label, hint, group| RowSpec { item, label, hint, group, enabled: true };
    let not_yet = |item, label, group| RowSpec { item, label, hint: "NOT YET", group, enabled: false };
    let mut v = vec![
        row(Item::Resume, "Resume", "", Group::Main),
        row(Item::Loadout, "Loadout", "NEXT SPAWN", Group::Main),
        row(Item::Settings, "Settings", "", Group::Main),
        row(Item::Controls, "Controls", "KEY REFERENCE", Group::Main),
    ];
    if host {
        v.push(not_yet(Item::Players, "Players", Group::Host));
        v.push(row(Item::Restart, if range { "Reset range" } else { "Restart match" }, "", Group::Host));
        v.push(if range {
            not_yet(Item::Lobby, "Back to lobby", Group::Host)
        } else {
            row(Item::Lobby, "Back to lobby", "KEEPS EVERYONE", Group::Host)
        });
        v.push(row(Item::Danger, "Stop hosting", "ENDS MATCH FOR ALL", Group::Danger));
    } else {
        v.push(row(Item::Danger, "Leave match", "BACK TO MAIN MENU", Group::Danger));
    }
    v
}

/// The next enabled row after `from` (`delta` +1 down, -1 up), wrapping.
fn step(rows: &[RowSpec], from: Item, delta: i32) -> Item {
    let n = rows.len() as i32;
    let at = rows.iter().position(|r| r.item == from).unwrap_or(0) as i32;
    for k in 1..=n {
        let r = &rows[(at + delta * k).rem_euclid(n) as usize];
        if r.enabled {
            return r.item;
        }
    }
    from
}

/// The menu's state: the rows it was built with and the selected one.
#[derive(Resource, Debug, Clone)]
struct EscUi {
    rows: Vec<RowSpec>,
    sel: Item,
}

impl Default for EscUi {
    fn default() -> Self {
        Self { rows: rows(false, false), sel: Item::Resume }
    }
}

#[derive(Component, Debug, Clone, Copy)]
struct EscRow(Item);

// ---------------------------------------------------------------------------------------------- card text

/// The card's texts that follow the match (set every frame, only written when they change).
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
enum CardText {
    Title,
    Ally,
    Enemy,
    Limit,
    Clock,
    ClockUnit,
    Join,
    JoinKind,
    CopyLabel,
    Players,
    Server,
    Ping,
    Loadout,
    Gear,
    GearSplit,
}

/// The JOIN CODE row's COPY (writes [`CopyInvite`], like F6).
#[derive(Component)]
struct CopyBtn;

/// The magazine chips (rebuilt when the loadout changes).
#[derive(Component)]
struct MagsBox;

/// The card's title: mode and map.
fn title(m: Option<&MatchState>) -> String {
    match m {
        Some(m) if m.mode == MatchMode::Tdm => format!("TEAM DEATHMATCH · {}", m.map.to_uppercase()),
        Some(m) if m.mode == MatchMode::Ffa => format!("FREE-FOR-ALL · {}", m.map.to_uppercase()),
        _ => "GUN RANGE · FREE PRACTICE".into(),
    }
}

/// Your team's score and the other team's.
fn scores(m: &MatchState, my_team: Option<Team>) -> (u32, u32) {
    match my_team {
        Some(Team::B) => (m.score_b, m.score_a),
        _ => (m.score_a, m.score_b),
    }
}

/// The clock (mm:ss of the whole seconds left), or MATCH OVER once the match has ended.
fn clock(m: &MatchState) -> (String, bool) {
    if matches!(m.phase, MatchPhase::Ended { .. }) {
        return ("MATCH OVER".into(), true);
    }
    let s = m.time_left_s.max(0.0).ceil() as u32;
    (format!("{:02}:{:02}", s / 60, s % 60), false)
}

/// `10 / 10 · 5 v 5` (allies first); the gun range has no teams.
fn players_line(connected: usize, max: u32, allies: usize, enemies: usize, tdm: bool) -> String {
    if tdm { format!("{connected} / {max} · {allies} v {enemies}") } else { format!("{connected} / {max}") }
}

/// The host runs a listen server (with the CPU time per tick once it is measured); a client names its host.
fn server_line(host: bool, tick_hz: u32, cpu_ms: Option<f32>, host_name: &str) -> String {
    match (host, cpu_ms) {
        (true, Some(ms)) => format!("Listen server (you) · {tick_hz} Hz · CPU {ms:.1} ms / tick"),
        (true, None) => format!("Listen server (you) · {tick_hz} Hz"),
        (false, _) => format!("{host_name} hosts · {tick_hz} Hz"),
    }
}

/// The host sees the remote player with the highest ping (WORST PING); a client sees its own (YOUR PING).
fn ping_line(host: bool, worst: Option<(&str, u16)>, own: Option<u16>) -> String {
    if host {
        worst.map_or("No one else connected".into(), |(name, ms)| format!("{name} {ms} ms"))
    } else {
        own.map_or("—".into(), |ms| format!("{ms} ms"))
    }
}

/// `Kestrel` from `KESTREL`.
fn title_case(s: &str) -> String {
    let lower = s.to_lowercase();
    let mut c = lower.chars();
    c.next().map_or(String::new(), |f| f.to_uppercase().chain(c).collect())
}

/// The halo in a few words: `T2 Mender (Medium)`, `T1-T3 Bulwark (Heavy)`, `No halo`; `T2 halo (Light)` where
/// everyone wears the same one (team deathmatch, free-for-all).
fn halo_words(s: &LoadoutSummary) -> String {
    let covered: Vec<u8> = vetf_sim::Zone::ALL.iter().map(|z| s.tiers[*z]).filter(|t| *t > 0).collect();
    let (Some(lo), Some(hi)) = (covered.iter().min(), covered.iter().max()) else { return "No halo".into() };
    let tier = if lo == hi { format!("T{hi}") } else { format!("T{lo}-T{hi}") };
    let core = match s.core {
        Some(_) if s.one_halo => " halo".to_string(),
        Some(c) => format!(" {}", title_case(c.label())),
        None => String::new(),
    };
    let weight =
        if s.weight == WeightClass::None { String::new() } else { format!(" ({})", title_case(s.weight.label())) };
    format!("{tier}{core}{weight}")
}

/// `Kestrel · AR-7 Mako · T2 Mender (Medium)` in the gun range; `AR-7 Mako · T2 halo (Medium) · AP II` in team
/// deathmatch and free-for-all (no agent pick, one halo, one ammo type).
fn loadout_line(s: &LoadoutSummary) -> String {
    match s.one_ammo().filter(|_| s.one_halo) {
        Some((ammo, ..)) => format!("{} · {} · {ammo}", s.weapon_name, halo_words(s)),
        None => format!("{} · {} · {}", title_case(&s.agent_name), s.weapon_name, halo_words(s)),
    }
}

/// The gear readout: `9 / 13` against the mode's budget, `9 PTS` without one (the gun range).
fn gear_line(s: &LoadoutSummary) -> String {
    match s.gear_budget {
        Some(budget) => format!("{} / {budget}", s.gear_cost),
        None => format!("{} PTS", s.gear_cost),
    }
}

/// What the gear is spent on: `HALO 6 + AMMO 2` (paid once, one ammo type) or `HALO 6 + MAGS 4`.
fn gear_split(s: &LoadoutSummary) -> String {
    let halo = s.gear_cost.saturating_sub(s.ammo_cost);
    format!("HALO {halo} + {} {}", if s.one_halo { "AMMO" } else { "MAGS" }, s.ammo_cost)
}

/// How friends join, for the JOIN CODE row: the code (or address) in big letters, and what it is.
fn join_lines(join: &JoinInfo) -> (String, String) {
    match join {
        JoinInfo::None => ("—".into(), String::new()),
        JoinInfo::Preparing { .. } => ("PREPARING…".into(), "INTERNET INVITE · READY IN A FEW SECONDS".into()),
        JoinInfo::Ready { .. } => (join.headline(), "INTERNET INVITE".into()),
        JoinInfo::Unavailable { lan: Some(lan), .. } => (lan.to_string(), "INVITE UNAVAILABLE · LAN".into()),
        JoinInfo::Unavailable { lan: None, .. } => ("—".into(), "INTERNET INVITE UNAVAILABLE".into()),
        JoinInfo::Address { addr, .. } => (addr.to_string(), join.label().into()),
    }
}

// ---------------------------------------------------------------------------------------------- CPU per tick

/// The host's simulation time per fixed tick over the last second (SERVER row).
#[derive(Resource, Default)]
struct TickCpu {
    start: Option<Instant>,
    /// (seconds since start-up, milliseconds) per tick.
    samples: VecDeque<(f32, f32)>,
}

impl TickCpu {
    fn add(&mut self, now: f32, ms: f32) {
        self.samples.push_back((now, ms));
        while self.samples.front().is_some_and(|(t, _)| *t < now - 1.0) {
            self.samples.pop_front();
        }
    }

    fn average_ms(&self) -> Option<f32> {
        let n = self.samples.len();
        (n > 0).then(|| self.samples.iter().map(|(_, ms)| ms).sum::<f32>() / n as f32)
    }
}

fn tick_start(mut cpu: ResMut<TickCpu>) {
    cpu.start = Some(Instant::now());
}

fn tick_end(mut cpu: ResMut<TickCpu>, time: Res<Time<Real>>) {
    if let Some(start) = cpu.start.take() {
        cpu.add(time.elapsed_secs(), start.elapsed().as_secs_f32() * 1000.0);
    }
}

// ---------------------------------------------------------------------------------------------- menu

/// Open the menu when it becomes the top screen (it stays under the screens it opens).
#[allow(clippy::too_many_arguments)]
fn spawn_menu(
    screens: Res<Screens>,
    roots: Query<&ScreenRoot>,
    session: Res<Session>,
    matches: Query<&MatchState>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    mut ui: ResMut<EscUi>,
    mut commands: Commands,
) {
    if screens.top() != Some(Screen::Esc) || roots.iter().any(|r| r.0 == Screen::Esc) {
        return;
    }
    let host = session.role == Role::Host;
    let range = matches.iter().next().is_none_or(|m| m.mode == MatchMode::Range);
    *ui = EscUi { rows: rows(host, range), sel: Item::Resume };
    let depth = screens.iter().position(|s| *s == Screen::Esc).unwrap_or(0) as i32;
    let fonts = &*fonts;
    // The live match shows through: darkest on the left, under the menu.
    let stops = scrim_stops(&[(0.0, 0.94), (36.0, 0.86), (100.0, 0.55)], 2.0)
        .into_iter()
        .map(|(t, a)| ColorStop::new(hexa_exact(INK, a), percent(t)))
        .collect();
    commands
        .spawn((
            ScreenRoot(Screen::Esc),
            DespawnOnExit(AppState::InGame),
            GlobalZIndex(100 + depth * 10),
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
            BackgroundGradient::from(LinearGradient::to_right(stops).in_color_space(InterpolationColorSpace::Srgba)),
        ))
        .with_children(|r| {
            r.spawn(Node {
                column_gap: px(10),
                align_items: AlignItems::Center,
                ..abs(Some(96.0), None, Some(72.0), None)
            })
            .with_children(|l| {
                l.spawn((
                    Node { width: px(10), height: px(10), border_radius: BorderRadius::MAX, ..default() },
                    BackgroundColor(ENEMY),
                    Pulse { period: 1.2, base: ENEMY },
                ));
                l.spawn(fonts.role_color(TextRole::Lbl, "Match still running · the game does not pause", TEXT_HI));
            });
            r.spawn(Node {
                width: px(460),
                flex_direction: FlexDirection::Column,
                ..abs(Some(96.0), None, Some(150.0), None)
            })
            .with_children(|c| menu_column(c, fonts, &ui.rows));
            info_card(r, fonts, host, !range);
            key_hints(r, fonts, &images);
        });
}

fn menu_column(c: &mut ChildSpawnerCommands, fonts: &UiFonts, rows: &[RowSpec]) {
    for r in rows.iter().filter(|r| r.group == Group::Main) {
        menu_row(c, fonts, r);
    }
    for group in [Group::Host, Group::Danger] {
        let members: Vec<&RowSpec> = rows.iter().filter(|r| r.group == group).collect();
        if members.is_empty() {
            continue;
        }
        c.spawn((
            Node {
                flex_direction: FlexDirection::Column,
                margin: UiRect::top(px(22)),
                padding: UiRect::top(px(14)),
                border: UiRect::top(px(1)),
                ..default()
            },
            BorderColor::all(STROKE),
        ))
        .with_children(|g| {
            if group == Group::Host {
                g.spawn((
                    fonts.micro("Host · only you see this"),
                    Node { margin: UiRect { left: px(22), bottom: px(4), ..default() }, ..default() },
                ));
            }
            for r in members {
                menu_row(g, fonts, r);
            }
        });
    }
}

/// One row: the label 22 px in, a hint (or RESUME's ESC key cap) at the right edge, and a 4 px bar on the
/// left while it is selected. Hover selects, so the rows have no hover look of their own.
fn menu_row(c: &mut ChildSpawnerCommands, fonts: &UiFonts, r: &RowSpec) {
    let (height, role) = if r.group == Group::Main { (60.0, TextRole::NavL) } else { (46.0, TextRole::NavM) };
    let danger = r.group == Group::Danger;
    let looks = if danger { NAV_DANGER } else { Looks::ink(TEXT_MID, TEXT_MID, TEXT_HI) };
    let hint_color = if danger { fade(ENEMY, 0.7) } else { TEXT_LOW };
    let mut row = c.spawn((
        EscRow(r.item),
        Button,
        Node {
            height: px(height),
            padding: UiRect::left(px(22)),
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::Center,
            ..default()
        },
        looks,
        Active(false),
    ));
    if !r.enabled {
        row.insert(Disabled);
    }
    row.with_children(|row| {
        row.spawn((
            OnBar,
            Node { width: px(4), ..abs(Some(0.0), None, Some(14.0), Some(14.0)) },
            BackgroundColor(if danger { ENEMY } else { TEXT_HI }),
            Visibility::Hidden,
        ));
        row.spawn((fonts.role_color(role, r.label, looks.idle.ink), Ink));
        if r.item == Item::Resume {
            row.spawn(keycap(fonts, "Esc", KeyStyle::Ghost, 20.0));
        } else {
            let color = if r.enabled { hint_color } else { fade(hint_color, DISABLED_ALPHA) };
            row.spawn(fonts.text(r.hint, Face::Display, 600, 13.0, color, 0.16));
        }
    });
}

/// The match card (top right): title, score and clock, then a key / value grid.
fn info_card(r: &mut ChildSpawnerCommands, fonts: &UiFonts, host: bool, tdm: bool) {
    r.spawn((
        Node {
            width: px(560),
            flex_direction: FlexDirection::Column,
            padding: UiRect::axes(px(24), px(22)),
            border: UiRect::all(px(1)),
            border_radius: BorderRadius::all(px(2)),
            ..abs(None, Some(96.0), Some(150.0), None)
        },
        BackgroundColor(PANEL_HI_OVER_ART),
        BorderColor::all(PANEL_HI_OVER_ART_STROKE),
    ))
    .with_children(|card| {
        card.spawn((CardText::Title, fonts.role(TextRole::H2, "")));
        if tdm {
            score_row(card, fonts);
        }
        card.spawn(Node {
            display: Display::Grid,
            grid_template_columns: vec![GridTrack::px(150.0), GridTrack::flex(1.0)],
            row_gap: px(10),
            margin: UiRect::top(px(16)),
            ..default()
        })
        .with_children(|g| {
            let key = |g: &mut ChildSpawnerCommands, k: &str| {
                g.spawn((fonts.lbl(k), Node { padding: UiRect::top(px(2)), ..default() }));
            };
            let num = |s: CardText| (s, fonts.role_color(TextRole::Num, "", TEXT));
            key(g, "Join code");
            g.spawn(Node { flex_direction: FlexDirection::Column, row_gap: px(4), ..default() }).with_children(|v| {
                v.spawn((CardText::Join, fonts.role(TextRole::CodeM, "")));
                v.spawn(Node { column_gap: px(10), align_items: AlignItems::Center, ..default() }).with_children(|s| {
                    s.spawn((CardText::JoinKind, fonts.micro("")));
                    s.spawn((
                        CopyBtn,
                        Button,
                        Node { column_gap: px(6), align_items: AlignItems::Center, ..default() },
                        Looks::ink(TEXT_LOW, TEXT_HI, TEXT_HI),
                    ))
                    .with_children(|b| {
                        b.spawn(keycap(fonts, "F6", KeyStyle::Ghost, 16.0));
                        b.spawn((CardText::CopyLabel, fonts.micro(""), Ink));
                    });
                });
            });
            key(g, "Players");
            g.spawn(num(CardText::Players));
            key(g, "Server");
            g.spawn(num(CardText::Server));
            key(g, if host { "Worst ping" } else { "Your ping" });
            g.spawn(num(CardText::Ping));
            key(g, "Your loadout");
            g.spawn((CardText::Loadout, fonts.role(TextRole::KvValue, "")));
            key(g, "Magazines");
            g.spawn((MagsBox, Node { column_gap: px(4), align_items: AlignItems::Center, ..default() }));
            if tdm {
                key(g, "Gear");
                g.spawn(Node { column_gap: px(8), align_items: AlignItems::Baseline, ..default() }).with_children(
                    |v| {
                        v.spawn((CardText::Gear, fonts.text("", Face::Display, 700, 15.0, TEXT_HI, 0.0)));
                        v.spawn((CardText::GearSplit, fonts.micro("")));
                    },
                );
            }
        });
    });
}

/// `32 VS 28` in the team colours, and on the right the score limit over the clock.
fn score_row(card: &mut ChildSpawnerCommands, fonts: &UiFonts) {
    card.spawn(Node {
        height: px(56),
        column_gap: px(18),
        align_items: AlignItems::Center,
        margin: UiRect::top(px(10)),
        ..default()
    })
    .with_children(|s| {
        s.spawn((CardText::Ally, fonts.role_color(TextRole::ScoreXl, "", ALLY)));
        s.spawn(fonts.lbl("VS"));
        s.spawn((CardText::Enemy, fonts.role_color(TextRole::ScoreXl, "", ENEMY)));
        s.spawn(Node {
            margin: UiRect::left(Val::Auto),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::FlexEnd,
            ..default()
        })
        .with_children(|c| {
            c.spawn((CardText::Limit, fonts.micro("")));
            c.spawn(Node { align_items: AlignItems::Baseline, column_gap: px(4), ..default() }).with_children(|t| {
                t.spawn((CardText::Clock, fonts.role(TextRole::Stepper, "")))
                    .insert(bevy::text::LetterSpacing::Px(1.76));
                t.spawn((CardText::ClockUnit, fonts.micro("Left")));
            });
        });
    });
}

/// ↑↓ SELECT · ENTER CONFIRM · ESC RESUME (bottom left).
fn key_hints(r: &mut ChildSpawnerCommands, fonts: &UiFonts, images: &UiImages) {
    r.spawn(Node { column_gap: px(22), align_items: AlignItems::Center, ..abs(Some(96.0), None, None, Some(40.0)) })
        .with_children(|h| {
            for (key, label) in [("↑↓", "Select"), ("Enter", "Confirm"), ("Esc", "Resume")] {
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
                        i.spawn(keycap(fonts, key, KeyStyle::Ghost, 22.0));
                    }
                    i.spawn(fonts.role(TextRole::Hint, label));
                });
            }
        });
}

/// The host's RESTART MATCH / BACK TO LOBBY: `server::reset_match` on the match.
fn reset_match(
    data: &GameData,
    matches: &mut Query<&mut MatchState>,
    players: &mut Query<(&mut PlayerNet, &mut Vitals, &mut Score), With<ServerPlayer>>,
    phase: Option<MatchPhase>,
) {
    let Some(mut m) = matches.iter_mut().next() else { return };
    crate::server::reset_match(&mut m, data, phase, players.iter_mut());
}

/// Rows: hover selects, ↑↓ move the selection over the enabled rows (wrapping), Enter or a click acts.
/// Keys count only when the menu was on top the frame before too, so the Enter that closed a screen over it
/// does not act here as well.
#[allow(clippy::too_many_arguments)]
fn menu_input(
    keys: Res<ButtonInput<KeyCode>>,
    session: Res<Session>,
    data: Res<Data>,
    rows: Query<(&Interaction, &EscRow), (Changed<Interaction>, Without<Disabled>)>,
    copy_btn: Query<&Interaction, (Changed<Interaction>, With<CopyBtn>)>,
    mut ui: ResMut<EscUi>,
    mut screens: ResMut<Screens>,
    mut matches: Query<&mut MatchState>,
    mut players: Query<(&mut PlayerNet, &mut Vitals, &mut Score), With<ServerPlayer>>,
    mut copy: MessageWriter<CopyInvite>,
    mut was_top: Local<bool>,
) {
    let top = screens.top() == Some(Screen::Esc);
    let live = top && *was_top;
    *was_top = top;
    if !live {
        return;
    }
    let mut act = None;
    for (i, r) in &rows {
        match i {
            Interaction::Hovered => ui.sel = r.0,
            Interaction::Pressed => {
                ui.sel = r.0;
                act = Some(r.0);
            }
            Interaction::None => {}
        }
    }
    if copy_btn.iter().any(|i| *i == Interaction::Pressed) {
        copy.write(CopyInvite);
    }
    if keys.just_pressed(KeyCode::ArrowDown) {
        ui.sel = step(&ui.rows, ui.sel, 1);
    } else if keys.just_pressed(KeyCode::ArrowUp) {
        ui.sel = step(&ui.rows, ui.sel, -1);
    } else if keys.any_just_pressed([KeyCode::Enter, KeyCode::NumpadEnter]) {
        act = Some(ui.sel);
    }
    let Some(item) = act.filter(|a| ui.rows.iter().any(|r| r.item == *a && r.enabled)) else { return };
    let host = session.role == Role::Host;
    match item {
        Item::Resume => {
            screens.pop();
        }
        Item::Loadout => screens.push(Screen::Loadout),
        // The default tab opens Settings on the last tab used.
        Item::Settings => screens.push(Screen::Settings(SettingsTab::Gameplay)),
        Item::Controls => screens.push(Screen::Settings(SettingsTab::Keybinds)),
        Item::Restart => screens.push(Screen::Confirm(ConfirmKind::RestartMatch)),
        // Everyone goes back to the lobby (the lobby screen takes over the stack), connections kept.
        Item::Lobby if host => {
            info!("the host sends everyone back to the lobby");
            reset_match(&data, &mut matches, &mut players, Some(MatchPhase::Lobby));
        }
        Item::Danger if host => screens.push(Screen::Confirm(ConfirmKind::StopHosting)),
        Item::Danger => screens.push(Screen::Confirm(ConfirmKind::LeaveMatch)),
        Item::Players | Item::Lobby => {}
    }
}

fn row_looks(ui: Res<EscUi>, mut rows: Query<(&EscRow, &mut Active)>) {
    for (r, mut on) in &mut rows {
        let want = r.0 == ui.sel;
        if on.0 != want {
            on.0 = want;
        }
    }
}

/// The card follows the match, the session and your loadout.
#[allow(clippy::too_many_arguments)]
fn refresh_card(
    screens: Res<Screens>,
    session: Res<Session>,
    data: Res<Data>,
    active: Res<ActiveLoadout>,
    copied: Res<InviteCopied>,
    cpu: Res<TickCpu>,
    time: Res<Time>,
    fonts: Res<UiFonts>,
    matches: Query<&MatchState>,
    players: Query<(&PlayerId, &PlayerInfo, Option<&PlayerNet>, Has<Controlled>, Option<&Score>)>,
    mut texts: Query<(&CardText, &mut Text)>,
    mut copy_btn: Query<&mut Node, With<CopyBtn>>,
    mags: Query<Entity, With<MagsBox>>,
    mut shown_loadout: Local<Option<(Entity, LoadoutChoice)>>,
    mut commands: Commands,
) {
    if !screens.contains(Screen::Esc) || texts.is_empty() {
        return;
    }
    let host = session.role == Role::Host;
    let m = matches.iter().next();
    let tdm = m.is_some_and(|m| m.mode == MatchMode::Tdm);
    let my_team = players.iter().find(|p| p.3).and_then(|p| p.1.team);
    let allies = players.iter().filter(|p| p.1.team == my_team).count();
    let host_name = players.iter().find(|p| p.0.0 == 0).map_or("The host".into(), |p| p.1.name.clone());
    let worst = players
        .iter()
        .filter(|p| !p.3)
        .filter_map(|p| p.2.map(|n| (p.1.name.as_str(), n.ping_ms)))
        .max_by_key(|(_, ms)| *ms);
    let own_ping = players.iter().find(|p| p.3).and_then(|p| p.2).map(|n| n.ping_ms);
    let join = JoinInfo::of(&session, data.net.port);
    let (code, kind) = join_lines(&join);
    // As this match's mode takes the loadout (team deathmatch over the menu).
    let s = summary(&active.0, &data, m.map_or(MatchMode::Tdm, |m| m.mode));
    // Free-for-all: your kills and the best of everyone else's (the HUD's score boxes).
    let ffa_kills = |me: bool| players.iter().filter(|p| p.3 == me).filter_map(|p| p.4.map(|s| s.kills as u32)).max();
    let (ally, enemy) = match m {
        Some(m) if m.mode == MatchMode::Ffa => (ffa_kills(true).unwrap_or(0), ffa_kills(false).unwrap_or(0)),
        Some(m) => scores(m, my_team),
        None => (0, 0),
    };
    let (clock_text, ended) = m.map_or((String::new(), false), clock);
    let copy_label = if copied.recent(time.elapsed_secs()) { "COPIED" } else { join.copy_label() };
    for (which, mut t) in &mut texts {
        let want = match which {
            CardText::Title => title(m),
            CardText::Ally => ally.to_string(),
            CardText::Enemy => enemy.to_string(),
            CardText::Limit => m.map_or(String::new(), |m| format!("FIRST TO {}", m.score_limit)),
            CardText::Clock => clock_text.clone(),
            CardText::ClockUnit => if ended { "" } else { "LEFT" }.into(),
            CardText::Join => code.clone(),
            CardText::JoinKind => kind.clone(),
            CardText::CopyLabel => copy_label.into(),
            CardText::Players => players_line(
                players.iter().count(),
                m.map_or(0, |m| m.max_players),
                allies,
                players.iter().count() - allies,
                tdm,
            ),
            CardText::Server => server_line(host, data.net.tick_hz, cpu.average_ms(), &host_name),
            CardText::Ping => ping_line(host, worst, own_ping),
            CardText::Loadout => loadout_line(&s),
            CardText::Gear => gear_line(&s),
            CardText::GearSplit => gear_split(&s),
        };
        if t.0 != want {
            t.0 = want;
        }
    }
    let display = if join.copy_text().is_some() { Display::Flex } else { Display::None };
    for mut n in &mut copy_btn {
        if n.display != display {
            n.display = display;
        }
    }
    // The magazine chips, in slot order (never a fill state or a round count).
    let Some(mags_box) = mags.iter().next() else { return };
    if shown_loadout.as_ref().is_some_and(|(e, l)| *e == mags_box && *l == active.0) {
        return;
    }
    *shown_loadout = Some((mags_box, active.0.clone()));
    let fonts = &*fonts;
    commands.entity(mags_box).despawn_children().with_children(|b| {
        for (slot, label, kind) in s.mags.iter().take(6) {
            b.spawn(mag_chip(fonts, *slot, label, *kind, false));
        }
    });
}

// ---------------------------------------------------------------------------------------------- confirm

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
enum ModalBtn {
    Cancel,
    Confirm,
}

/// A modal button's own looks (the focused one wears its hover look).
#[derive(Component, Debug, Clone, Copy)]
struct BaseLooks(Looks);

/// The open modal: which button has the keyboard focus, and whether to show it (after the first key).
#[derive(Resource, Debug, Clone, Copy)]
struct ModalUi {
    focus: ModalBtn,
    visible: bool,
}

impl Default for ModalUi {
    fn default() -> Self {
        Self { focus: ModalBtn::Cancel, visible: false }
    }
}

/// What a confirm modal says: title, body, the confirm button's label, and whether it is the restart one
/// (WARN accent and a primary button instead of red).
struct ModalCopy {
    title: &'static str,
    body: String,
    confirm: &'static str,
    restart: bool,
}

fn modal_copy(kind: ConfirmKind, range: bool, others: usize) -> Option<ModalCopy> {
    let red = |title, body: String, confirm| ModalCopy { title, body, confirm, restart: false };
    Some(match kind {
        ConfirmKind::StopHosting => {
            let body = match others {
                0 => "No one else is connected. The match ends and you return to the main menu.".into(),
                1 => "The match ends for the 1 other player and everyone returns to the main menu. Scores are not \
                      saved."
                    .into(),
                n => format!(
                    "The match ends for all {n} other players and everyone returns to the main menu. Scores are \
                     not saved."
                ),
            };
            red("Stop hosting?", body, "Stop hosting")
        }
        ConfirmKind::LeaveMatch => red(
            "Leave match?",
            "You return to the main menu. The match keeps running for everyone else, and you can rejoin with the \
             join code."
                .into(),
            "Leave match",
        ),
        ConfirmKind::RestartMatch if range => ModalCopy {
            title: "Reset range?",
            body: "Everyone respawns with a fresh loadout. No one is disconnected.".into(),
            confirm: "Reset",
            restart: true,
        },
        ConfirmKind::RestartMatch => ModalCopy {
            title: "Restart match?",
            body: "Scores reset to 0 - 0, the clock restarts and everyone respawns. No one is disconnected.".into(),
            confirm: "Restart",
            restart: true,
        },
        // The main menu's own confirm.
        ConfirmKind::QuitGame => return None,
    })
}

#[allow(clippy::too_many_arguments)]
fn spawn_modal(
    screens: Res<Screens>,
    roots: Query<&ScreenRoot>,
    matches: Query<&MatchState>,
    players: Query<(), With<PlayerInfo>>,
    fonts: Res<UiFonts>,
    mut ui: ResMut<ModalUi>,
    mut commands: Commands,
) {
    let Some(Screen::Confirm(kind)) = screens.top() else { return };
    if roots.iter().any(|r| matches!(r.0, Screen::Confirm(_))) {
        return;
    }
    let range = matches.iter().next().is_none_or(|m| m.mode == MatchMode::Range);
    let Some(copy) = modal_copy(kind, range, players.iter().count().saturating_sub(1)) else { return };
    *ui = ModalUi::default();
    let depth = screens.iter().position(|s| matches!(s, Screen::Confirm(_))).unwrap_or(0) as i32;
    let fonts = &*fonts;
    let confirm_looks = if copy.restart { BTN_PRIMARY } else { BTN_DANGER_SOLID };
    let confirm_kind = if copy.restart { BtnKind::Primary } else { BtnKind::DangerSolid };
    commands
        .spawn((
            ScreenRoot(Screen::Confirm(kind)),
            DespawnOnExit(AppState::InGame),
            GlobalZIndex(100 + depth * 10),
            Node {
                position_type: PositionType::Absolute,
                width: percent(100),
                height: percent(100),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..default()
            },
            BackgroundColor(MODAL_BACKDROP),
            // A click on the backdrop does nothing (and reaches nothing under it).
            Button,
        ))
        .with_children(|r| {
            let mut panel = r.spawn(panel_of(
                PanelKind::Modal,
                Node {
                    width: px(620),
                    flex_direction: FlexDirection::Column,
                    padding: UiRect::axes(px(30), px(28)),
                    ..default()
                },
            ));
            if copy.restart {
                panel.insert(BorderColor { top: WARN, ..BorderColor::all(STROKE) });
            }
            panel.with_children(|p| {
                p.spawn(fonts.role(TextRole::ModalTitle, copy.title));
                p.spawn((
                    fonts.role(TextRole::ModalBody, copy.body),
                    Node { margin: UiRect::top(px(10)), ..default() },
                ));
                p.spawn(Node {
                    column_gap: px(12),
                    justify_content: JustifyContent::FlexEnd,
                    margin: UiRect::top(px(22)),
                    ..default()
                })
                .with_children(|b| {
                    let ring = Outline::new(px(2), px(2), Color::NONE);
                    b.spawn((ModalBtn::Cancel, BaseLooks(BTN), ring, cancel_button(fonts)));
                    b.spawn((
                        ModalBtn::Confirm,
                        BaseLooks(confirm_looks),
                        ring,
                        button(fonts, copy.confirm, confirm_kind, BtnSize::M),
                    ));
                });
            });
        });
}

/// CANCEL [ESC]: the kit's `button_with_key` with a key cap that has no minimum width. With the kit's key cap
/// (`min_width` = its height) Bevy sizes the button 13 px wider than its content (165 instead of the
/// mockup's 152).
fn cancel_button(fonts: &UiFonts) -> impl Bundle {
    (
        Button,
        button_node(BtnSize::M),
        BackgroundColor(BTN.idle.bg),
        BorderColor::all(BTN.idle.border),
        BTN,
        children![
            (fonts.role(TextRole::Btn, "Cancel"), Ink),
            (
                Node {
                    height: px(20),
                    padding: UiRect::horizontal(px(6)),
                    border: UiRect::all(px(1)),
                    border_radius: BorderRadius::all(px(2)),
                    align_items: AlignItems::Center,
                    justify_content: JustifyContent::Center,
                    ..default()
                },
                BorderColor::all(STROKE_HI),
                children![fonts.text("ESC", Face::Display, 700, 13.0, TEXT_HI, 0.04)],
            )
        ],
    )
}

/// ←→ or Tab move the focus between CANCEL and the confirm button, Enter or a click acts. Esc is CANCEL
/// (the stack's BACK), which leaves the ESC menu's selection where it was.
#[allow(clippy::too_many_arguments)]
fn modal_input(
    keys: Res<ButtonInput<KeyCode>>,
    session: Res<Session>,
    data: Res<Data>,
    btns: Query<(&Interaction, &ModalBtn), Changed<Interaction>>,
    mut ui: ResMut<ModalUi>,
    mut screens: ResMut<Screens>,
    mut matches: Query<&mut MatchState>,
    mut players: Query<(&mut PlayerNet, &mut Vitals, &mut Score), With<ServerPlayer>>,
    mut requests: MessageWriter<NetRequest>,
    mut was_top: Local<bool>,
) {
    let kind = match screens.top() {
        Some(Screen::Confirm(k)) if k != ConfirmKind::QuitGame => Some(k),
        _ => None,
    };
    let live = kind.is_some() && *was_top;
    *was_top = kind.is_some();
    let Some(kind) = kind.filter(|_| live) else { return };
    let mut act = btns.iter().find(|(i, _)| **i == Interaction::Pressed).map(|(_, b)| *b);
    if keys.any_just_pressed([KeyCode::ArrowLeft, KeyCode::ArrowRight, KeyCode::Tab]) {
        if ui.visible {
            ui.focus = if ui.focus == ModalBtn::Cancel { ModalBtn::Confirm } else { ModalBtn::Cancel };
        }
        ui.visible = true;
    } else if keys.any_just_pressed([KeyCode::Enter, KeyCode::NumpadEnter]) {
        act = Some(ui.focus);
    }
    match act {
        None => {}
        Some(ModalBtn::Cancel) => {
            screens.pop();
        }
        Some(ModalBtn::Confirm) => match kind {
            ConfirmKind::RestartMatch if session.role == Role::Host => {
                info!("the host restarts the match");
                let range = matches.iter().next().is_none_or(|m| m.mode == MatchMode::Range);
                reset_match(&data, &mut matches, &mut players, (!range).then_some(MatchPhase::Live));
                // Back to the match.
                screens.close(Screen::Esc);
            }
            ConfirmKind::StopHosting | ConfirmKind::LeaveMatch => {
                requests.write(NetRequest::Leave { reason: None });
            }
            _ => {}
        },
    }
}

fn modal_looks(ui: Res<ModalUi>, mut btns: Query<(&ModalBtn, &BaseLooks, &mut Looks, &mut Outline)>) {
    for (b, base, mut looks, mut ring) in &mut btns {
        let focused = ui.visible && *b == ui.focus;
        let want = if focused { Looks::new(base.0.hover, base.0.hover, base.0.on) } else { base.0 };
        if *looks != want {
            *looks = want;
        }
        let color = if focused { TEXT_HI } else { Color::NONE };
        if ring.color != color {
            ring.color = color;
        }
    }
}

// ---------------------------------------------------------------------------------------------- demo

/// `--demo-ui esc | esc-stop | esc-restart` (with `--host <map> --live`): a second into the match, open the
/// menu; `esc-stop` then opens the STOP HOSTING confirm (LEAVE MATCH for a client), `esc-restart` the
/// RESTART MATCH one.
fn demo(
    cli: Res<Cli>,
    time: Res<Time>,
    session: Res<Session>,
    mut screens: ResMut<Screens>,
    mut ui: ResMut<EscUi>,
    mut since: Local<Option<f32>>,
    mut step: Local<u8>,
) {
    let Some(demo) = cli.demo_ui.as_deref().filter(|d| *d == "esc" || d.starts_with("esc-")) else { return };
    let t = time.elapsed_secs();
    let since = *since.get_or_insert(t);
    match *step {
        0 if t - since > 1.0 && screens.is_empty() => {
            screens.push(Screen::Esc);
            *step = 1;
        }
        // The frame after: the menu exists (its spawn resets the selection).
        1 => {
            *step = 2;
            let (item, kind) = match demo {
                "esc-stop" if session.role == Role::Host => (Item::Danger, ConfirmKind::StopHosting),
                "esc-stop" => (Item::Danger, ConfirmKind::LeaveMatch),
                "esc-restart" => (Item::Restart, ConfirmKind::RestartMatch),
                _ => return,
            };
            ui.sel = item;
            screens.push(Screen::Confirm(kind));
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::ZoneTable;
    use vetf_sim::data::{AmmoKind, Core};

    fn items(rows: &[RowSpec]) -> Vec<Item> {
        rows.iter().map(|r| r.item).collect()
    }

    #[test]
    fn the_host_gets_its_group_and_a_client_leaves() {
        let host = rows(true, false);
        assert_eq!(
            items(&host),
            vec![
                Item::Resume,
                Item::Loadout,
                Item::Settings,
                Item::Controls,
                Item::Players,
                Item::Restart,
                Item::Lobby,
                Item::Danger
            ]
        );
        assert_eq!(host.last().map(|r| r.label), Some("Stop hosting"));
        let players = host.iter().find(|r| r.item == Item::Players).unwrap();
        assert!(!players.enabled && players.hint == "NOT YET", "not built yet: dimmed, never hidden");
        let client = rows(false, false);
        assert_eq!(items(&client), vec![Item::Resume, Item::Loadout, Item::Settings, Item::Controls, Item::Danger]);
        assert_eq!(client.last().map(|r| (r.label, r.hint)), Some(("Leave match", "BACK TO MAIN MENU")));
        assert!(client.iter().all(|r| r.group != Group::Host));
    }

    #[test]
    fn the_gun_range_resets_instead_of_restarting() {
        let range = rows(true, true);
        assert_eq!(range.iter().find(|r| r.item == Item::Restart).map(|r| r.label), Some("Reset range"));
        assert!(!range.iter().find(|r| r.item == Item::Lobby).unwrap().enabled, "the range has no lobby");
    }

    #[test]
    fn arrows_skip_dimmed_rows_and_wrap() {
        let host = rows(true, false);
        assert_eq!(step(&host, Item::Controls, 1), Item::Restart, "PLAYERS is skipped");
        assert_eq!(step(&host, Item::Restart, -1), Item::Controls);
        assert_eq!(step(&host, Item::Danger, 1), Item::Resume, "wraps at the bottom");
        assert_eq!(step(&host, Item::Resume, -1), Item::Danger, "and at the top");
        let range = rows(true, true);
        assert_eq!(step(&range, Item::Restart, 1), Item::Danger, "BACK TO LOBBY is skipped in the range");
    }

    fn tdm(time_left_s: f32, phase: MatchPhase) -> MatchState {
        MatchState {
            mode: MatchMode::Tdm,
            map: "showhome".into(),
            score_a: 28,
            score_b: 32,
            score_limit: 50,
            time_left_s,
            phase,
            lobby_name: String::new(),
            max_players: 10,
            rules: GameData::embedded().rules.rulesets.tdm,
        }
    }

    #[test]
    fn the_card_reads_the_match() {
        let m = tdm(400.2, MatchPhase::Live);
        assert_eq!(title(Some(&m)), "TEAM DEATHMATCH · SHOWHOME");
        assert_eq!(title(None), "GUN RANGE · FREE PRACTICE");
        assert_eq!(scores(&m, Some(Team::B)), (32, 28), "your team's score comes first");
        assert_eq!(scores(&m, Some(Team::A)), (28, 32));
        assert_eq!(clock(&m), ("06:41".into(), false), "whole seconds, rounded up");
        assert_eq!(clock(&tdm(400.2, MatchPhase::Ended { winner: None, player: None })), ("MATCH OVER".into(), true));
        assert_eq!(players_line(10, 10, 5, 5, true), "10 / 10 · 5 v 5");
        assert_eq!(players_line(3, 10, 3, 0, false), "3 / 10");
    }

    #[test]
    fn server_and_ping_lines_follow_the_role() {
        assert_eq!(server_line(true, 60, Some(2.13), ""), "Listen server (you) · 60 Hz · CPU 2.1 ms / tick");
        assert_eq!(server_line(true, 60, None, ""), "Listen server (you) · 60 Hz", "no CPU part before it is measured");
        assert_eq!(server_line(false, 60, None, "Brann"), "Brann hosts · 60 Hz");
        assert_eq!(ping_line(true, Some(("Brann", 90)), Some(0)), "Brann 90 ms", "the host: the worst remote ping");
        assert_eq!(ping_line(true, None, None), "No one else connected");
        assert_eq!(ping_line(false, Some(("Brann", 90)), Some(42)), "42 ms", "a client: its own");
        assert_eq!(ping_line(false, None, None), "—");
    }

    fn loadout(tiers: ZoneTable<u8>, core: Option<Core>, weight: WeightClass) -> LoadoutSummary {
        LoadoutSummary {
            weapon_name: "AR-7 Mako".into(),
            attachments: vec![],
            mags: vec![(1, "STD".into(), AmmoKind::Standard)],
            one_halo: false,
            armor_name: String::new(),
            core,
            tiers,
            weight,
            gear_cost: 7,
            ammo_cost: 1,
            gear_budget: None,
            agent_name: "KESTREL".into(),
        }
    }

    #[test]
    fn the_loadout_line_names_gun_and_halo() {
        let t = |head, torso, arms, legs| ZoneTable { head, torso, arms, legs };
        let even = loadout(t(2, 2, 2, 0), Some(Core::Mender), WeightClass::Medium);
        assert_eq!(loadout_line(&even), "Kestrel · AR-7 Mako · T2 Mender (Medium)");
        let mixed = loadout(t(1, 3, 2, 0), Some(Core::Bulwark), WeightClass::Heavy);
        assert_eq!(halo_words(&mixed), "T1-T3 Bulwark (Heavy)");
        assert_eq!(halo_words(&loadout(t(0, 0, 0, 0), None, WeightClass::None)), "No halo");
        assert_eq!((gear_line(&even), gear_split(&even)), ("7 PTS".into(), "HALO 6 + MAGS 1".into()), "the range");
    }

    /// Team deathmatch and free-for-all: no agent, one halo (its core goes unnamed), one ammo type.
    #[test]
    fn the_deathmatch_loadout_line_names_gun_tiers_and_ammo() {
        let d = vetf_sim::GameData::embedded();
        let ap2 = vetf_sim::data::AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 };
        let mut c = crate::server::default_choice(&d);
        c.mags = vec![ap2, vetf_sim::data::AmmoChoice::STANDARD];
        c.halo.tiers = ZoneTable { head: 2, torso: 3, arms: 1, legs: 0 };
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            let s = summary(&c, &d, mode);
            assert_eq!(loadout_line(&s), "AR-7 Mako · T1-T3 halo (Medium) · AP II");
            assert_eq!(gear_line(&s), "10 / 13");
            assert_eq!(gear_split(&s), "HALO 6 + AMMO 4", "AP II paid once");
        }
    }

    #[test]
    fn the_join_row_shows_the_invite_state() {
        let lan: std::net::SocketAddr = "192.168.1.20:47820".parse().unwrap();
        assert_eq!(join_lines(&JoinInfo::None).0, "—");
        assert_eq!(join_lines(&JoinInfo::Preparing { lan: Some(lan) }).0, "PREPARING…");
        let invite = format!("SL1-{}", "ab".repeat(32));
        let ready = JoinInfo::Ready { invite: invite.clone(), lan: None };
        assert_eq!(join_lines(&ready), (crate::invite::short_invite(&invite), "INTERNET INVITE".into()));
        let down = JoinInfo::Unavailable { error: "no internet".into(), lan: Some(lan) };
        assert_eq!(join_lines(&down), ("192.168.1.20:47820".into(), "INVITE UNAVAILABLE · LAN".into()));
        let direct = JoinInfo::Address { addr: lan, lan_only: false };
        assert_eq!(join_lines(&direct), ("192.168.1.20:47820".into(), "DIRECT IP".into()));
    }

    #[test]
    fn stop_hosting_counts_the_other_players() {
        let body = |n| modal_copy(ConfirmKind::StopHosting, false, n).unwrap().body;
        assert!(body(9).starts_with("The match ends for all 9 other players"));
        assert!(body(1).starts_with("The match ends for the 1 other player and"));
        assert!(body(0).starts_with("No one else is connected."));
        let restart = modal_copy(ConfirmKind::RestartMatch, false, 0).unwrap();
        assert!(restart.restart && restart.confirm == "Restart");
        assert_eq!(modal_copy(ConfirmKind::RestartMatch, true, 0).unwrap().title, "Reset range?");
        assert!(!modal_copy(ConfirmKind::LeaveMatch, false, 0).unwrap().restart, "leaving is red");
        assert!(modal_copy(ConfirmKind::QuitGame, false, 0).is_none(), "the main menu's confirm is not ours");
    }

    #[test]
    fn cpu_time_is_averaged_over_the_last_second() {
        let mut cpu = TickCpu::default();
        assert_eq!(cpu.average_ms(), None);
        cpu.add(0.0, 10.0);
        cpu.add(0.5, 2.0);
        cpu.add(1.2, 4.0);
        assert_eq!(cpu.average_ms(), Some(3.0), "the sample older than a second is gone");
    }

    /// The input systems alone, for the client variant (no match, no players).
    fn input_app() -> App {
        let mut app = App::new();
        app.init_resource::<ButtonInput<KeyCode>>()
            .init_resource::<Screens>()
            .init_resource::<ModalUi>()
            .insert_resource(EscUi { rows: rows(false, false), sel: Item::Resume })
            .insert_resource(Session::default())
            .insert_resource(Data(std::sync::Arc::new(GameData::embedded())))
            .add_message::<CopyInvite>()
            .add_message::<NetRequest>()
            .add_systems(Update, (menu_input, modal_input).chain());
        app
    }

    fn press(app: &mut App, key: KeyCode) {
        app.world_mut().resource_mut::<ButtonInput<KeyCode>>().press(key);
        app.update();
        let mut keys = app.world_mut().resource_mut::<ButtonInput<KeyCode>>();
        keys.release(key);
        keys.clear();
    }

    fn top(app: &App) -> Option<Screen> {
        app.world().resource::<Screens>().top()
    }

    #[test]
    fn arrows_select_and_enter_opens_the_row() {
        let mut app = input_app();
        app.world_mut().resource_mut::<Screens>().push(Screen::Esc);
        press(&mut app, KeyCode::Enter);
        assert_eq!(top(&app), Some(Screen::Esc), "the Enter of the frame the menu opened is not for it");
        press(&mut app, KeyCode::ArrowUp);
        assert_eq!(app.world().resource::<EscUi>().sel, Item::Danger, "up from RESUME wraps to LEAVE MATCH");
        press(&mut app, KeyCode::ArrowDown);
        press(&mut app, KeyCode::ArrowDown);
        press(&mut app, KeyCode::Enter);
        assert_eq!(top(&app), Some(Screen::Loadout));
        app.world_mut().resource_mut::<Screens>().pop();
        press(&mut app, KeyCode::ArrowDown);
        press(&mut app, KeyCode::ArrowDown);
        press(&mut app, KeyCode::Enter);
        assert_eq!(top(&app), Some(Screen::Settings(SettingsTab::Keybinds)), "CONTROLS opens the keybinds");
    }

    #[test]
    fn leaving_asks_first_and_cancel_is_the_safe_default() {
        let mut app = input_app();
        app.world_mut().resource_mut::<Screens>().push(Screen::Esc);
        app.update();
        press(&mut app, KeyCode::ArrowUp);
        press(&mut app, KeyCode::Enter);
        assert_eq!(top(&app), Some(Screen::Confirm(ConfirmKind::LeaveMatch)));
        press(&mut app, KeyCode::Enter);
        assert_eq!(top(&app), Some(Screen::Esc), "the modal opens on CANCEL");
        assert_eq!(app.world().resource::<EscUi>().sel, Item::Danger, "LEAVE MATCH stays selected");
        app.world_mut().resource_mut::<Screens>().push(Screen::Confirm(ConfirmKind::LeaveMatch));
        app.update();
        press(&mut app, KeyCode::ArrowRight);
        assert_eq!(app.world().resource::<ModalUi>().focus, ModalBtn::Cancel, "the first key only shows the focus");
        press(&mut app, KeyCode::ArrowRight);
        assert!(app.world().resource::<Messages<NetRequest>>().is_empty());
        press(&mut app, KeyCode::Enter);
        let sent = app.world().resource::<Messages<NetRequest>>();
        assert!(sent.iter_current_update_messages().any(|r| matches!(r, NetRequest::Leave { reason: None })));
    }
}
