//! The scoreboard (hold the Scoreboard key, Tab by default, in a match; hub spec 06, mockup 07): mode, map,
//! score target, time left and host; the team score; one row per player (your team on top) with halo,
//! kills, deaths and ping; and the server card. Free-for-all has one list sorted by kills (your row
//! highlighted, everyone else an enemy) and your kills against the leader's. It is pinned while a finished
//! match waits to restart, and then names the winner. No ammo information, ever.

use crate::AppState;
use crate::client::BindDevices;
use crate::config::{Cli, Data};
use crate::invite::JoinInfo;
use crate::net::{Role, Session};
use crate::screens::Screens;
use crate::settings::{Action, Settings};
use crate::ui_kit::*;
use bevy::prelude::*;
use lightyear::prelude::Controlled;
use vetf_net::*;
use vetf_sim::level::Team;

pub struct ScoreboardPlugin;

impl Plugin for ScoreboardPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(AppState::InGame), spawn)
            .add_systems(Update, (show, rebuild).chain().run_if(in_state(AppState::InGame)));
    }
}

#[derive(Component)]
struct BoardRoot;

/// Everything under the dim; rebuilt a few times a second while shown.
#[derive(Component)]
struct BoardBody;

/// The table's columns (one grid per row, so the header and every row line up): badge, player, halo, K, D,
/// ping.
fn columns() -> Vec<RepeatedGridTrack> {
    vec![
        GridTrack::px(56.0),
        GridTrack::flex(1.0),
        GridTrack::px(170.0),
        GridTrack::px(90.0),
        GridTrack::px(90.0),
        GridTrack::px(110.0),
    ]
}

const WIDTH: f32 = 1240.0;

fn spawn(mut commands: Commands) {
    commands.spawn((
        BoardRoot,
        DespawnOnExit(AppState::InGame),
        Node {
            position_type: PositionType::Absolute,
            width: percent(100),
            height: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            ..default()
        },
        BackgroundColor(SCOREBOARD_DIM),
        // Over the HUD, under the hub screens (100+).
        GlobalZIndex(50),
        Visibility::Hidden,
        children![(
            BoardBody,
            Node { width: px(WIDTH), margin: UiRect::top(px(120)), flex_direction: FlexDirection::Column, ..default() }
        )],
    ));
}

/// Shown while the Scoreboard key is held (not under a hub screen), and pinned when the match has ended.
fn show(
    mut devices: BindDevices,
    settings: Res<Settings>,
    cli: Res<Cli>,
    screens: Res<Screens>,
    matches: Query<&MatchState>,
    mut root: Query<&mut Visibility, With<BoardRoot>>,
) {
    let ended = matches.iter().next().is_some_and(|m| matches!(m.phase, MatchPhase::Ended { .. }));
    let held =
        settings.keybinds.pressed(Action::Scoreboard, &devices.read()) || cli.demo_ui.as_deref() == Some("board");
    let on = screens.is_empty() && (held || ended);
    for mut vis in &mut root {
        vis.set_if_neq(if on { Visibility::Inherited } else { Visibility::Hidden });
    }
}

/// One player's row data.
struct Row {
    id: u64,
    name: String,
    me: bool,
    host: bool,
    dead: bool,
    respawn_s: f32,
    team: Option<Team>,
    tiers: vetf_sim::ZoneTable<u8>,
    weight: vetf_sim::data::WeightClass,
    kills: u16,
    deaths: u16,
    ping_ms: u16,
}

#[allow(clippy::too_many_arguments)]
fn rebuild(
    root: Query<&Visibility, With<BoardRoot>>,
    body: Query<Entity, With<BoardBody>>,
    players: Query<(&PlayerId, &PlayerInfo, &Score, &Vitals, &PlayerLoadout, Option<&PlayerNet>, Has<Controlled>)>,
    matches: Query<&MatchState>,
    session: Res<Session>,
    data: Res<Data>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    time: Res<Time>,
    mut next: Local<f32>,
    mut was_shown: Local<bool>,
    mut commands: Commands,
) {
    let shown = root.iter().next().is_some_and(|v| *v != Visibility::Hidden);
    let just_shown = shown && !*was_shown;
    *was_shown = shown;
    if !shown || (!just_shown && time.elapsed_secs() < *next) {
        return;
    }
    *next = time.elapsed_secs() + 0.25;
    let Some(body) = body.iter().next() else { return };
    let rows: Vec<Row> = players
        .iter()
        .map(|(id, info, score, v, loadout, net, me)| Row {
            id: id.0,
            name: info.name.to_uppercase(),
            me,
            host: id.0 == 0,
            dead: v.health.dead,
            respawn_s: v.respawn_s,
            team: info.team,
            tiers: loadout.0.halo.tiers,
            weight: loadout.0.weight,
            kills: score.kills,
            deaths: score.deaths,
            ping_ms: net.map_or(0, |n| n.ping_ms),
        })
        .collect();
    let my_team = rows.iter().find(|r| r.me).and_then(|r| r.team);
    let my_ping = rows.iter().find(|r| r.me).map_or(0, |r| r.ping_ms);
    let host_name = rows.iter().find(|r| r.host).map(|r| r.name.clone()).unwrap_or_default();
    let m = matches.iter().next();
    let join = JoinInfo::of(&session, data.net.port);
    let tick_hz = data.net.tick_hz;
    let hosting = session.role == Role::Host;
    let fonts = &*fonts;
    let images = &*images;
    let teams = m.is_none_or(|m| m.mode != MatchMode::Ffa);
    commands.entity(body).despawn_children().with_children(|b| {
        if teams {
            head(b, fonts, m, my_team, &host_name);
        } else {
            ffa_head(b, fonts, m, &rows, &host_name);
        }
        table(b, fonts, images, rows, my_team, teams);
        footer(b, fonts, tick_hz, hosting, my_ping, &join);
    });
}

fn head(b: &mut ChildSpawnerCommands, fonts: &UiFonts, m: Option<&MatchState>, my_team: Option<Team>, host: &str) {
    let tdm = m.is_some_and(|m| m.mode == MatchMode::Tdm);
    let map = m.map_or(String::new(), |m| m.map.to_uppercase());
    let (title, title_color) = match m.map(|m| m.phase) {
        Some(MatchPhase::Ended { winner: Some(w), .. }) if Some(w) == my_team => ("VICTORY", ALLY),
        Some(MatchPhase::Ended { winner: Some(_), .. }) => ("DEFEAT", ENEMY),
        Some(MatchPhase::Ended { winner: None, .. }) => ("DRAW", TEXT_HI),
        _ if tdm => ("TEAM DEATHMATCH", TEXT_HI),
        _ => ("GUN RANGE", TEXT_HI),
    };
    let mut parts = vec![map];
    if let Some(m) = m.filter(|_| tdm) {
        parts.push(format!("FIRST TO {}", m.score_limit));
        let s = m.time_left_s.max(0.0).ceil() as u32;
        parts.push(format!("{:02}:{:02} LEFT", s / 60, s % 60));
    } else {
        parts.push("FREE PRACTICE".into());
    }
    if !host.is_empty() {
        parts.push(format!("HOST: {host}"));
    }
    b.spawn((
        Node {
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::FlexEnd,
            padding: UiRect::bottom(px(12)),
            border: UiRect::bottom(px(1)),
            ..default()
        },
        BorderColor::all(STROKE_MID),
    ))
    .with_children(|h| {
        h.spawn(Node { flex_direction: FlexDirection::Column, row_gap: px(4), ..default() }).with_children(|t| {
            t.spawn(fonts.role_color(TextRole::SbTitle, title, title_color));
            t.spawn(fonts.text(parts.join(" · "), Face::Display, 600, 13.0, TEXT_MID, 0.2));
        });
        if let Some(m) = m.filter(|_| tdm) {
            let (ours, theirs) = match my_team {
                Some(Team::B) => (m.score_b, m.score_a),
                _ => (m.score_a, m.score_b),
            };
            h.spawn(Node { column_gap: px(16), align_items: AlignItems::Center, ..default() }).with_children(|s| {
                s.spawn(fonts.text(ours.to_string(), Face::Display, 700, 48.0, ALLY, 0.0));
                s.spawn(fonts.text("VS", Face::Display, 700, 16.0, TEXT_MID, 0.2));
                s.spawn(fonts.text(theirs.to_string(), Face::Display, 700, 48.0, ENEMY, 0.0));
            });
        }
    });
}

/// Free-for-all's title: the mode, or once it is over, who won (VICTORY when it is you).
fn ffa_title(phase: Option<MatchPhase>, me: Option<u64>, name_of: impl Fn(u64) -> Option<String>) -> (String, Color) {
    match phase {
        Some(MatchPhase::Ended { player: Some(w), .. }) if Some(w) == me => ("VICTORY".into(), ALLY),
        Some(MatchPhase::Ended { player: Some(w), .. }) => {
            (format!("{} WINS", name_of(w).unwrap_or_else(|| "A PLAYER".into())), ENEMY)
        }
        Some(MatchPhase::Ended { .. }) => ("DRAW".into(), TEXT_HI),
        _ => ("FREE-FOR-ALL".into(), TEXT_HI),
    }
}

/// Your kills and the best of everyone else's (the leader to catch, or the one chasing you).
fn kills_vs_best_other(rows: &[Row]) -> (u16, u16) {
    let mine = rows.iter().find(|r| r.me).map_or(0, |r| r.kills);
    let best = rows.iter().filter(|r| !r.me).map(|r| r.kills).max().unwrap_or(0);
    (mine, best)
}

fn ffa_head(b: &mut ChildSpawnerCommands, fonts: &UiFonts, m: Option<&MatchState>, rows: &[Row], host: &str) {
    let me = rows.iter().find(|r| r.me).map(|r| r.id);
    let name_of = |id: u64| rows.iter().find(|r| r.id == id).map(|r| r.name.clone());
    let (title, title_color) = ffa_title(m.map(|m| m.phase), me, name_of);
    let mut parts = vec![m.map_or(String::new(), |m| m.map.to_uppercase())];
    if let Some(m) = m {
        parts.push(format!("FIRST TO {} KILLS", m.score_limit));
        let s = m.time_left_s.max(0.0).ceil() as u32;
        parts.push(format!("{:02}:{:02} LEFT", s / 60, s % 60));
    }
    if !host.is_empty() {
        parts.push(format!("HOST: {host}"));
    }
    let (mine, best) = kills_vs_best_other(rows);
    b.spawn((
        Node {
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::FlexEnd,
            padding: UiRect::bottom(px(12)),
            border: UiRect::bottom(px(1)),
            ..default()
        },
        BorderColor::all(STROKE_MID),
    ))
    .with_children(|h| {
        h.spawn(Node { flex_direction: FlexDirection::Column, row_gap: px(4), ..default() }).with_children(|t| {
            t.spawn(fonts.role_color(TextRole::SbTitle, title, title_color));
            t.spawn(fonts.text(parts.join(" · "), Face::Display, 600, 13.0, TEXT_MID, 0.2));
        });
        // Your kills against the best of the rest.
        h.spawn(Node { column_gap: px(16), align_items: AlignItems::Center, ..default() }).with_children(|s| {
            s.spawn(fonts.text("YOU", Face::Display, 700, 14.0, TEXT_MID, 0.2));
            s.spawn(fonts.text(mine.to_string(), Face::Display, 700, 48.0, ALLY, 0.0));
            s.spawn(fonts.text("VS", Face::Display, 700, 16.0, TEXT_MID, 0.2));
            s.spawn(fonts.text(best.to_string(), Face::Display, 700, 48.0, ENEMY, 0.0));
            s.spawn(fonts.text(if mine > best { "NEXT" } else { "LEADER" }, Face::Display, 700, 14.0, TEXT_MID, 0.2));
        });
    });
}

/// A right-aligned cell (12 px padding, like the mockup's table).
fn cell(right: bool) -> Node {
    Node {
        padding: UiRect::horizontal(px(12)),
        justify_content: if right { JustifyContent::FlexEnd } else { JustifyContent::FlexStart },
        align_items: AlignItems::Center,
        column_gap: px(8),
        height: percent(100),
        ..default()
    }
}

fn table(
    b: &mut ChildSpawnerCommands,
    fonts: &UiFonts,
    images: &UiImages,
    mut rows: Vec<Row>,
    my_team: Option<Team>,
    teams: bool,
) {
    b.spawn(Node {
        display: Display::Grid,
        grid_template_columns: columns(),
        margin: UiRect::top(px(14)),
        padding: UiRect::bottom(px(6)),
        ..default()
    })
    .with_children(|h| {
        for (i, label) in ["", "Player", "Halo", "K", "D", "Ping"].iter().enumerate() {
            h.spawn(cell(i != 1)).with_children(|c| {
                c.spawn(fonts.role(TextRole::TableHead, *label));
            });
        }
    });
    sort_rows(&mut rows);
    // Your team on top, then the other team after a 14 px gap; the range has one neutral block, and
    // free-for-all one block where everyone but you is an enemy.
    let blocks: Vec<(Option<Team>, Option<bool>)> = match my_team {
        Some(t) => vec![(Some(t), Some(true)), (Some(t.other()), Some(false))],
        None if !teams => vec![(None, Some(false))],
        None => vec![(None, None)],
    };
    for (bi, (team, ally)) in blocks.into_iter().enumerate() {
        let block: Vec<&Row> = rows.iter().filter(|r| team.is_none() || r.team == team).collect();
        if block.is_empty() {
            continue;
        }
        b.spawn(Node {
            flex_direction: FlexDirection::Column,
            margin: UiRect::top(px(if bi > 0 { 14 } else { 0 })),
            ..default()
        })
        .with_children(|blk| {
            for r in block {
                player_row(blk, fonts, images, r, ally);
            }
        });
    }
}

/// Most kills first, then fewest deaths, then by name (a steady order while the scores tie).
fn sort_rows(rows: &mut [Row]) {
    rows.sort_by(|a, b| b.kills.cmp(&a.kills).then(a.deaths.cmp(&b.deaths)).then_with(|| a.name.cmp(&b.name)));
}

fn player_row(blk: &mut ChildSpawnerCommands, fonts: &UiFonts, images: &UiImages, r: &Row, ally: Option<bool>) {
    // You are never your own enemy (free-for-all's single block).
    let ally = ally.map(|a| a || r.me);
    let bg = match (r.me, ally) {
        (true, _) => hexa(0x52E5A5, 0.26),
        (false, Some(true)) => hexa(0x52E5A5, 0.12),
        (false, Some(false)) => hexa(0xFF4D5A, 0.11),
        (false, None) => white(0.035),
    };
    let ink = if r.dead { TEXT_MID } else { TEXT_HI };
    blk.spawn((
        Node {
            display: Display::Grid,
            grid_template_columns: columns(),
            height: px(44),
            border: UiRect::top(px(2)),
            align_items: AlignItems::Center,
            ..default()
        },
        BackgroundColor(bg),
        BorderColor::all(scrim(0x040609, 0.60)),
    ))
    .with_children(|row| {
        if let Some(ally) = ally {
            row.spawn((
                Node { width: px(3), height: percent(100), ..abs(Some(0.0), None, Some(0.0), None) },
                BackgroundColor(if ally { ALLY } else { ENEMY }),
            ));
        }
        // Agent badge: every agent is Kestrel until the loadout carries one.
        row.spawn(cell(false)).with_children(|c| {
            c.spawn((
                Node {
                    width: px(28),
                    height: px(28),
                    justify_content: JustifyContent::Center,
                    align_items: AlignItems::Center,
                    border_radius: BorderRadius::all(px(3)),
                    ..default()
                },
                BackgroundColor(if r.dead { fade(AGENT_KESTREL, 0.45) } else { AGENT_KESTREL }),
                children![fonts.text("K", Face::Display, 700, 14.0, ICON_CUT, 0.0)],
            ));
        });
        row.spawn(cell(false)).with_children(|c| {
            c.spawn(fonts.text(r.name.clone(), Face::Display, 600, 19.0, ink, 0.0));
            let tag = |s: &str| fonts.text(s.to_string(), Face::Display, 600, 12.0, TEXT_MID, 0.14);
            if r.me {
                c.spawn(tag("· YOU"));
            }
            if r.host {
                c.spawn(icon(images, Icon::Crown, 14.0, hex(0xFFCE50)));
                c.spawn(tag("HOST"));
            }
            if r.dead {
                c.spawn(tag(&format!("· RESPAWN {} S", r.respawn_s.max(0.0).ceil() as u32)));
            }
        });
        row.spawn(cell(true)).with_children(|c| {
            c.spawn(arc_chip(images, r.tiers));
            c.spawn(weight_squares(weight_lit(r.weight)));
        });
        for v in [r.kills, r.deaths] {
            row.spawn(cell(true)).with_children(|c| {
                c.spawn(fonts.text(v.to_string(), Face::Display, 600, 19.0, ink, 0.0));
            });
        }
        row.spawn(cell(true)).with_children(|c| {
            c.spawn(fonts.text(r.ping_ms.to_string(), Face::Display, 600, 16.0, TEXT_MID, 0.0));
        });
    });
}

fn footer(b: &mut ChildSpawnerCommands, fonts: &UiFonts, tick_hz: u32, hosting: bool, ping: u16, join: &JoinInfo) {
    let value = if hosting { format!("{tick_hz} Hz · HOST") } else { format!("{tick_hz} Hz · {ping} ms") };
    let micro = match join {
        JoinInfo::None => "LISTEN SERVER".to_string(),
        j => format!("LISTEN SERVER · {} {}", j.label(), j.headline()),
    };
    b.spawn(Node { margin: UiRect::top(px(18)), column_gap: px(12), ..default() }).with_children(|f| {
        f.spawn(panel_of(
            PanelKind::Base,
            Node {
                width: px(301),
                flex_direction: FlexDirection::Column,
                padding: UiRect::axes(px(14), px(12)),
                ..default()
            },
        ))
        .with_children(|p| {
            p.spawn(fonts.lbl("Server"));
            p.spawn((
                fonts.text(value, Face::Display, 700, 22.0, TEXT_HI, 0.0),
                Node { margin: UiRect::vertical(px(4)), ..default() },
            ));
            p.spawn(fonts.micro(micro));
        });
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(id: u64, name: &str, kills: u16, deaths: u16, me: bool) -> Row {
        Row {
            id,
            name: name.into(),
            me,
            host: id == 0,
            dead: false,
            respawn_s: 0.0,
            team: None,
            tiers: vetf_sim::ZoneTable::splat(0),
            weight: vetf_sim::data::WeightClass::None,
            kills,
            deaths,
            ping_ms: 0,
        }
    }

    #[test]
    fn free_for_all_rows_sort_by_kills_then_deaths() {
        let mut rows = vec![
            row(1, "WREN", 4, 2, false),
            row(2, "ORCA", 9, 5, true),
            row(3, "LARK", 9, 3, false),
            row(4, "MOTH", 0, 0, false),
        ];
        sort_rows(&mut rows);
        let order: Vec<&str> = rows.iter().map(|r| r.name.as_str()).collect();
        assert_eq!(order, ["LARK", "ORCA", "WREN", "MOTH"]);
        assert_eq!(kills_vs_best_other(&rows), (9, 9), "your 9 against LARK's 9");
        rows[0].kills = 3;
        assert_eq!(kills_vs_best_other(&rows), (9, 4), "you lead: the best of the rest is 4");
    }

    #[test]
    fn free_for_all_names_the_winner() {
        let name = |id: u64| (id == 3).then(|| "LARK".to_string());
        let end = |p| Some(MatchPhase::Ended { winner: None, player: p });
        assert_eq!(ffa_title(end(Some(3)), Some(3), name), ("VICTORY".into(), ALLY));
        assert_eq!(ffa_title(end(Some(3)), Some(2), name), ("LARK WINS".into(), ENEMY));
        assert_eq!(ffa_title(end(None), Some(2), name).0, "DRAW");
        assert_eq!(ffa_title(Some(MatchPhase::Live), Some(2), name).0, "FREE-FOR-ALL");
    }
}
