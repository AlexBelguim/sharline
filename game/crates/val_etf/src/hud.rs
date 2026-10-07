//! In-match HUD (layout after design/ui/mockups/png/01_hud.png and 02_hud_magcheck.png).
//!
//! Hard rule: no exact ammo count anywhere. The weapon panel shows the gun, fire mode, and which magazine
//! slot (and so which ammo) is in the gun; rounds are only ever reported as a mag-check estimate.

use crate::AppState;
use crate::client::{Feedback, LocalControl};
use crate::config::Data;
use crate::net::{NetRequest, Session};
use crate::render::{ViewCamera, team_color, tier_color};
use bevy::prelude::*;
use lightyear::prelude::*;
use vetf_net::*;
use vetf_sim::Zone;
use vetf_sim::data::FireMode;
use vetf_sim::level::Team;
use vetf_sim::weapon::WeaponAction;

pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(AppState::InGame), spawn_hud)
            .add_systems(OnEnter(AppState::Connecting), spawn_connecting)
            .add_systems(
                Update,
                (
                    update_vitals_panel,
                    update_weapon_panel,
                    update_score,
                    update_crosshair,
                    update_feed,
                    update_overlays,
                    update_damage_indicators,
                    pause_buttons,
                    update_connecting.run_if(in_state(AppState::Connecting)),
                )
                    .run_if(in_state(AppState::InGame).or_else(in_state(AppState::Connecting))),
            );
    }
}

const PANEL: Color = Color::srgba(0.06, 0.07, 0.09, 0.82);
const INK: Color = Color::srgb(0.93, 0.94, 0.95);
const MUTED: Color = Color::srgb(0.58, 0.62, 0.68);
const TEAL: Color = Color::srgb(0.0, 0.70, 0.62);
const CORAL: Color = Color::srgb(1.0, 0.36, 0.30);

#[derive(Component)]
struct ZoneBar(Zone);
#[derive(Component)]
struct ZoneValue(Zone);
#[derive(Component)]
struct ArcBar(Zone);
#[derive(Component)]
struct ShieldText;
#[derive(Component)]
struct HaloLabel;
#[derive(Component)]
struct StatusText;
#[derive(Component)]
struct WeaponName;
#[derive(Component)]
struct WeaponDetail;
#[derive(Component)]
struct FireModeText;
#[derive(Component)]
struct MagCardRoot;
#[derive(Component)]
struct MagCardText;
#[derive(Component)]
struct MagCardSegment(u8);
#[derive(Component)]
struct ScoreA;
#[derive(Component)]
struct ScoreB;
#[derive(Component)]
struct MatchClock;
#[derive(Component)]
struct CrosshairArm(u8);
#[derive(Component)]
struct HitMarker;
#[derive(Component)]
struct FeedText;
#[derive(Component)]
struct CenterBanner;
#[derive(Component)]
struct PauseRoot;
#[derive(Component)]
struct ScoreboardText;
#[derive(Component)]
struct DamageChevron(usize);
#[derive(Component)]
struct ConnectingText;
#[derive(Component, Clone, Copy)]
enum PauseButton {
    Resume,
    Leave,
}

fn text(s: impl Into<String>, size: f32, color: Color) -> (Text, TextFont, TextColor) {
    (Text::new(s), TextFont::from_font_size(size), TextColor(color))
}

fn abs_node(left: Option<f32>, right: Option<f32>, top: Option<f32>, bottom: Option<f32>) -> Node {
    Node {
        position_type: PositionType::Absolute,
        left: left.map_or(Val::Auto, Val::Px),
        right: right.map_or(Val::Auto, Val::Px),
        top: top.map_or(Val::Auto, Val::Px),
        bottom: bottom.map_or(Val::Auto, Val::Px),
        ..default()
    }
}

fn spawn_connecting(mut commands: Commands) {
    commands.spawn((
        Node {
            width: percent(100),
            height: percent(100),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            ..default()
        },
        BackgroundColor(Color::srgb(0.04, 0.05, 0.07)),
        DespawnOnExit(AppState::Connecting),
        children![(ConnectingText, text("CONNECTING...", 28.0, INK))],
    ));
}

fn update_connecting(session: Res<Session>, mut q: Query<&mut Text, With<ConnectingText>>) {
    for mut t in &mut q {
        t.0 = session.status.clone().unwrap_or_else(|| "STARTING MATCH...".into()).to_uppercase();
    }
}

fn spawn_hud(mut commands: Commands) {
    let root = commands
        .spawn((
            Node { width: percent(100), height: percent(100), ..default() },
            DespawnOnExit(AppState::InGame),
            Pickable::IGNORE,
        ))
        .id();

    // --- health panel (bottom left)
    let health = commands
        .spawn((
            Node {
                flex_direction: FlexDirection::Column,
                padding: UiRect::all(px(14)),
                row_gap: px(6),
                width: px(380),
                ..abs_node(Some(24.0), None, None, Some(24.0))
            },
            BackgroundColor(PANEL),
            ChildOf(root),
        ))
        .id();
    commands.spawn((StatusText, text("", 14.0, CORAL), ChildOf(health)));
    commands.spawn((
        Node { justify_content: JustifyContent::SpaceBetween, ..default() },
        ChildOf(health),
        children![(text("SHIELD", 13.0, MUTED)), (HaloLabel, text("", 13.0, Color::srgb(0.4, 0.65, 1.0)))],
    ));
    commands.spawn((ShieldText, text("", 30.0, INK), ChildOf(health)));
    // one bar per halo arc
    let arcs = commands
        .spawn((Node { column_gap: px(4), height: px(8), margin: UiRect::bottom(px(6)), ..default() }, ChildOf(health)))
        .id();
    for zone in Zone::ALL {
        commands.spawn((
            Node { flex_grow: 1.0, height: percent(100), ..default() },
            BackgroundColor(Color::srgb(0.15, 0.16, 0.19)),
            ChildOf(arcs),
            children![(
                ArcBar(zone),
                Node { width: percent(100), height: percent(100), ..default() },
                BackgroundColor(Color::NONE)
            )],
        ));
    }
    for zone in Zone::ALL {
        let row = commands
            .spawn((Node { align_items: AlignItems::Center, column_gap: px(10), ..default() }, ChildOf(health)))
            .id();
        commands.spawn((text(zone.label(), 13.0, MUTED), Node { width: px(56), ..default() }, ChildOf(row)));
        commands.spawn((
            Node { width: px(220), height: px(6), ..default() },
            BackgroundColor(Color::srgb(0.15, 0.16, 0.19)),
            ChildOf(row),
            children![(
                ZoneBar(zone),
                Node { width: percent(100), height: percent(100), ..default() },
                BackgroundColor(INK)
            )],
        ));
        commands.spawn((ZoneValue(zone), text("", 15.0, INK), ChildOf(row)));
    }

    // --- weapon panel (bottom right)
    let weapon = commands
        .spawn((
            Node {
                flex_direction: FlexDirection::Column,
                padding: UiRect::all(px(14)),
                row_gap: px(6),
                width: px(400),
                ..abs_node(None, Some(24.0), None, Some(24.0))
            },
            BackgroundColor(PANEL),
            ChildOf(root),
        ))
        .id();
    commands.spawn((
        Node { justify_content: JustifyContent::SpaceBetween, ..default() },
        ChildOf(weapon),
        children![(WeaponName, text("", 24.0, INK)), (FireModeText, text("", 16.0, INK))],
    ));
    commands.spawn((WeaponDetail, text("", 14.0, MUTED), ChildOf(weapon)));

    // --- mag check card (above the weapon panel)
    let card = commands
        .spawn((
            MagCardRoot,
            Node {
                flex_direction: FlexDirection::Column,
                padding: UiRect::all(px(14)),
                row_gap: px(6),
                width: px(400),
                ..abs_node(None, Some(24.0), None, Some(150.0))
            },
            BackgroundColor(PANEL),
            Visibility::Hidden,
            ChildOf(root),
        ))
        .id();
    commands.spawn((text("MAG CHECK", 13.0, MUTED), ChildOf(card)));
    commands.spawn((MagCardText, text("", 30.0, INK), ChildOf(card)));
    let segs = commands.spawn((Node { column_gap: px(4), height: px(6), ..default() }, ChildOf(card))).id();
    for i in 0..6 {
        commands.spawn((
            MagCardSegment(i),
            Node { flex_grow: 1.0, height: percent(100), ..default() },
            BackgroundColor(Color::srgb(0.2, 0.21, 0.24)),
            ChildOf(segs),
        ));
    }
    commands.spawn((
        Node { justify_content: JustifyContent::SpaceBetween, ..default() },
        ChildOf(card),
        children![(text("EMPTY", 11.0, MUTED)), (text("FULL", 11.0, MUTED))],
    ));
    commands.spawn((text("Estimate from the mag window, not a count.", 12.0, MUTED), ChildOf(card)));

    // --- score (top centre)
    commands.spawn((
        Node {
            width: percent(100),
            justify_content: JustifyContent::Center,
            column_gap: px(4),
            ..abs_node(None, None, Some(18.0), None)
        },
        ChildOf(root),
        children![
            (
                Node { padding: UiRect::axes(px(18), px(6)), ..default() },
                BackgroundColor(TEAL),
                children![(ScoreA, text("0", 30.0, Color::BLACK))]
            ),
            (
                Node {
                    padding: UiRect::axes(px(18), px(6)),
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    ..default()
                },
                BackgroundColor(PANEL),
                children![(MatchClock, text("", 22.0, INK))]
            ),
            (
                Node { padding: UiRect::axes(px(18), px(6)), ..default() },
                BackgroundColor(CORAL),
                children![(ScoreB, text("0", 30.0, Color::BLACK))]
            ),
        ],
    ));

    // --- kill feed (top right)
    commands.spawn((
        FeedText,
        abs_node(None, Some(24.0), Some(24.0), None),
        text("", 15.0, INK),
        TextLayout::justify(Justify::Right),
        ChildOf(root),
    ));

    // --- crosshair + hit marker (centre)
    let center = commands
        .spawn((
            Node {
                position_type: PositionType::Absolute,
                width: percent(100),
                height: percent(100),
                align_items: AlignItems::Center,
                justify_content: JustifyContent::Center,
                ..default()
            },
            ChildOf(root),
        ))
        .id();
    for i in 0..4u8 {
        commands.spawn((
            CrosshairArm(i),
            Node {
                position_type: PositionType::Absolute,
                width: px(if i < 2 { 10 } else { 2 }),
                height: px(if i < 2 { 2 } else { 10 }),
                ..default()
            },
            BackgroundColor(Color::srgba(1.0, 1.0, 1.0, 0.9)),
            ChildOf(center),
        ));
    }
    commands.spawn((
        HitMarker,
        Node { position_type: PositionType::Absolute, ..default() },
        text("X", 26.0, Color::WHITE),
        Visibility::Hidden,
        ChildOf(center),
    ));
    for i in 0..4 {
        commands.spawn((
            DamageChevron(i),
            Node { position_type: PositionType::Absolute, width: px(18), height: px(18), ..default() },
            BackgroundColor(Color::srgba(1.0, 0.25, 0.2, 0.85)),
            Visibility::Hidden,
            ChildOf(center),
        ));
    }

    // --- centre banner (death / match end) and pause menu
    commands.spawn((
        CenterBanner,
        Node {
            width: percent(100),
            justify_content: JustifyContent::Center,
            ..abs_node(None, None, Some(200.0), None)
        },
        ChildOf(root),
        children![(text("", 30.0, INK), TextLayout::justify(Justify::Center))],
    ));
    commands.spawn((
        PauseRoot,
        Node {
            position_type: PositionType::Absolute,
            width: percent(100),
            height: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            row_gap: px(12),
            ..default()
        },
        BackgroundColor(Color::srgba(0.02, 0.03, 0.05, 0.75)),
        Visibility::Hidden,
        ChildOf(root),
        children![
            (text("PAUSED", 34.0, INK)),
            (ScoreboardText, text("", 16.0, INK), TextLayout::justify(Justify::Center)),
            menu_button("RESUME", PauseButton::Resume),
            menu_button("LEAVE MATCH", PauseButton::Leave),
        ],
    ));
}

fn menu_button(label: &str, action: PauseButton) -> impl Bundle {
    (
        Button,
        action,
        Node {
            width: px(260),
            height: px(46),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            ..default()
        },
        BackgroundColor(Color::srgb(0.92, 0.91, 0.88)),
        children![(text(label, 18.0, Color::BLACK))],
    )
}

#[allow(clippy::type_complexity)]
fn update_vitals_panel(
    me: Query<(&Vitals, &PlayerLoadout, Option<&PlayerItems>), With<Controlled>>,
    data: Res<Data>,
    mut zone_bars: Query<(&ZoneBar, &mut Node, &mut BackgroundColor), Without<ArcBar>>,
    mut zone_vals: Query<
        (&ZoneValue, &mut Text, &mut TextColor),
        (Without<ShieldText>, Without<HaloLabel>, Without<StatusText>),
    >,
    mut arc_bars: Query<(&ArcBar, &mut Node, &mut BackgroundColor), Without<ZoneBar>>,
    mut shield: Query<&mut Text, (With<ShieldText>, Without<ZoneValue>, Without<HaloLabel>, Without<StatusText>)>,
    mut label: Query<&mut Text, (With<HaloLabel>, Without<ZoneValue>, Without<ShieldText>, Without<StatusText>)>,
    mut status: Query<&mut Text, (With<StatusText>, Without<ZoneValue>, Without<ShieldText>, Without<HaloLabel>)>,
) {
    let Some((v, lo, items)) = me.iter().next() else { return };
    let halo = lo.0.halo;
    for (z, mut node, mut bg) in &mut zone_bars {
        let frac = (v.health.hp[z.0] / v.health.max[z.0]).clamp(0.0, 1.0);
        node.width = percent(frac * 100.0);
        bg.0 = if frac < 0.35 { CORAL } else { INK };
    }
    for (z, mut t, mut c) in &mut zone_vals {
        t.0 = format!("{:.0}", v.health.hp[z.0].max(0.0));
        c.0 = if v.wounds.broken.contains(z.0) || v.health.hp[z.0] <= 0.0 { CORAL } else { INK };
    }
    for (a, mut node, mut bg) in &mut arc_bars {
        let cap = halo.capacity[a.0];
        let frac = if cap > 0.0 { v.halo.shield[a.0] / cap } else { 0.0 };
        node.width = percent(frac * 100.0);
        bg.0 = Color::from(tier_color(halo.tiers[a.0]));
    }
    for mut t in &mut shield {
        t.0 = format!("{:.0} / {:.0}", v.halo.total(), halo.total_capacity());
    }
    for mut t in &mut label {
        let tiers: Vec<String> = Zone::ALL
            .iter()
            .filter(|z| halo.tiers[**z] > 0)
            .map(|z| format!("{} T{}", z.label(), halo.tiers[*z]))
            .collect();
        t.0 = match halo.core {
            Some(core) => format!("{}  {}  |  {}", core.label(), tiers.join(" "), lo.0.weight.label()),
            None => "NO HALO".into(),
        };
    }
    for mut t in &mut status {
        let mut parts = vec![];
        // The item in hand, with a progress bar.
        if let Some((u, k)) = items.and_then(|i| i.0.using).and_then(|u| Some((u, lo.0.kit.get(u.slot as usize)?))) {
            let done = 1.0 - u.left as f32 / u.total.max(1) as f32;
            let bar: String = (0..10).map(|i| if (i as f32) < done * 10.0 { '#' } else { '.' }).collect();
            let zone = u.zone.map_or(String::new(), |z| format!(" ON {}", z.label()));
            parts.push(format!("USING {}{zone} [{bar}]", data.items.spec(k).label));
        }
        let bleeding = v.health.bleeding.zones();
        if !bleeding.is_empty() {
            let zones: Vec<&str> = bleeding.iter().map(Zone::label).collect();
            parts.push(format!("BLEEDING - {}", zones.join(" ")));
        }
        // Broken limbs only exist where the mode's rules have injuries (wounds are synced on the host).
        if v.wounds.broken.contains(Zone::Arms) {
            parts.push("ARMS BROKEN".to_string());
        }
        if v.wounds.broken.contains(Zone::Legs) {
            parts.push("LEGS BROKEN".to_string());
        }
        if v.halo.regen_wait_s > 0.0 && halo.core.is_some() {
            parts.push(format!("REGEN IN {:.0} S", v.halo.regen_wait_s.ceil()));
        }
        if v.protected_s > 0.0 {
            parts.push("SPAWN PROTECTED".into());
        }
        t.0 = parts.join("  |  ");
    }
}

#[allow(clippy::type_complexity)]
fn update_weapon_panel(
    me: Query<(&PlayerWeapon, &PlayerLoadout), With<Controlled>>,
    data: Res<Data>,
    mut name: Query<&mut Text, (With<WeaponName>, Without<WeaponDetail>, Without<FireModeText>, Without<MagCardText>)>,
    mut detail: Query<
        &mut Text,
        (With<WeaponDetail>, Without<WeaponName>, Without<FireModeText>, Without<MagCardText>),
    >,
    mut mode: Query<&mut Text, (With<FireModeText>, Without<WeaponName>, Without<WeaponDetail>, Without<MagCardText>)>,
    mut card_root: Query<&mut Visibility, With<MagCardRoot>>,
    mut card_text: Query<
        &mut Text,
        (With<MagCardText>, Without<WeaponName>, Without<WeaponDetail>, Without<FireModeText>),
    >,
    mut segs: Query<(&MagCardSegment, &mut BackgroundColor)>,
) {
    let Some((w, lo)) = me.iter().next() else { return };
    let spec = lo.0.weapon.spec(&data);
    for mut t in &mut name {
        t.0 = spec.name.to_uppercase();
    }
    for mut t in &mut mode {
        t.0 = match w.0.fire_mode {
            FireMode::Auto => "AUTO",
            FireMode::Semi => "SEMI",
            FireMode::Bolt => "BOLT",
        }
        .into();
    }
    for mut t in &mut detail {
        // Which magazine slot is in the gun and its ammo: never how many rounds or magazines are left.
        let slot = w.0.loaded;
        let action = match w.0.action {
            WeaponAction::Reloading { .. } => "  RELOADING",
            WeaponAction::MagChecking { .. } => "  CHECKING MAG",
            WeaponAction::Equipping { .. } => "  EQUIPPING",
            WeaponAction::Ready => "",
        };
        let atts: Vec<String> = lo.0.weapon.attachments.iter().map(|a| a.replace('_', " ").to_uppercase()).collect();
        t.0 = format!(
            "MAG {}  {}{action}\n{}\n[T] CHECK MAG  [R] RELOAD (HOLD: PICK MAG)  [B] FIRE MODE",
            slot + 1,
            lo.0.weapon.ammo(slot).label,
            atts.join(" / ")
        );
    }
    let card = w.0.card;
    for mut v in &mut card_root {
        *v = if card.is_some() { Visibility::Inherited } else { Visibility::Hidden };
    }
    if let Some(card) = card {
        for mut t in &mut card_text {
            t.0 = format!("{}  ·  MAG {} {}", card.estimate.label(), card.slot + 1, lo.0.weapon.ammo(card.slot).label);
        }
        for (s, mut bg) in &mut segs {
            bg.0 = if s.0 == card.estimate.segment() { INK } else { Color::srgb(0.2, 0.21, 0.24) };
        }
    }
}

#[allow(clippy::type_complexity)]
fn update_score(
    matches: Query<&MatchState>,
    mut a: Query<&mut Text, (With<ScoreA>, Without<ScoreB>, Without<MatchClock>)>,
    mut b: Query<&mut Text, (With<ScoreB>, Without<ScoreA>, Without<MatchClock>)>,
    mut clock: Query<&mut Text, (With<MatchClock>, Without<ScoreA>, Without<ScoreB>)>,
) {
    let Some(m) = matches.iter().next() else { return };
    for mut t in &mut a {
        t.0 = m.score_a.to_string();
    }
    for mut t in &mut b {
        t.0 = m.score_b.to_string();
    }
    for mut t in &mut clock {
        t.0 = match m.mode {
            MatchMode::Range => "GUN RANGE".into(),
            MatchMode::Tdm => {
                let s = m.time_left_s.max(0.0) as u32;
                format!("{:02}:{:02}  TDM - FIRST TO {}", s / 60, s % 60, m.score_limit)
            }
        };
    }
}

#[allow(clippy::type_complexity)]
fn update_crosshair(
    me: Query<(&PlayerWeapon, &PlayerLoadout, &PlayerMove, &Vitals), With<Controlled>>,
    data: Res<Data>,
    windows: Query<&Window>,
    feedback: Res<Feedback>,
    mut arms: Query<(&CrosshairArm, &mut Node, &mut Visibility), Without<HitMarker>>,
    mut marker: Query<(&mut Visibility, &mut TextColor), With<HitMarker>>,
) {
    let Some((w, lo, mv, v)) = me.iter().next() else { return };
    let spec = lo.0.weapon.spec(&data);
    let wounds = v.wounds;
    let env = vetf_sim::player::weapon_env(&data, &mv.0, &wounds);
    let spread = w.0.spread_deg(&data, spec, &lo.0.weapon, &env);
    let h = windows.iter().next().map_or(900.0, |w| w.height());
    let focal = h * 0.5 / (78f32.to_radians() * 0.5).tan();
    let gap = 4.0 + spread.to_radians().tan() * focal;
    let hide = w.0.ads > 0.7 || v.health.dead;
    for (arm, mut node, mut vis) in &mut arms {
        let (dx, dy) = match arm.0 {
            0 => (-gap - 10.0, -1.0),
            1 => (gap, -1.0),
            2 => (-1.0, -gap - 10.0),
            _ => (-1.0, gap),
        };
        node.margin = UiRect {
            left: px(dx * 2.0 + if arm.0 < 2 { 10.0 } else { 2.0 }),
            top: px(dy * 2.0 + if arm.0 < 2 { 2.0 } else { 10.0 }),
            ..default()
        };
        *vis = if hide { Visibility::Hidden } else { Visibility::Inherited };
    }
    for (mut vis, mut color) in &mut marker {
        match feedback.hit_marker {
            Some((kind, _)) => {
                *vis = Visibility::Inherited;
                color.0 = match kind {
                    HitKind::Shield => Color::srgb(0.45, 0.7, 1.0),
                    HitKind::Health => Color::WHITE,
                    HitKind::Kill => CORAL,
                };
            }
            None => *vis = Visibility::Hidden,
        }
    }
}

fn update_feed(feedback: Res<Feedback>, mut q: Query<&mut Text, With<FeedText>>) {
    for mut t in &mut q {
        t.0 = feedback
            .kills
            .iter()
            .map(|(k, v, hs, _)| {
                let k = if k.is_empty() { "--".to_string() } else { k.clone() };
                format!("{k}  >  {v}{}", if *hs { "  [HEADSHOT]" } else { "" })
            })
            .collect::<Vec<_>>()
            .join("\n");
    }
}

#[allow(clippy::type_complexity)]
fn update_overlays(
    me: Query<(&Vitals, &PlayerInfo), With<Controlled>>,
    matches: Query<&MatchState>,
    players: Query<(&PlayerInfo, &Score)>,
    control: Res<LocalControl>,
    session: Res<Session>,
    keys: Res<ButtonInput<KeyCode>>,
    banner: Query<&Children, With<CenterBanner>>,
    mut texts: Query<&mut Text, Without<ScoreboardText>>,
    mut pause: Query<&mut Visibility, With<PauseRoot>>,
    mut board: Query<&mut Text, With<ScoreboardText>>,
) {
    let Some((v, info)) = me.iter().next() else { return };
    let m = matches.iter().next();
    let mut msg = String::new();
    if let Some(MatchPhase::Ended { winner }) = m.map(|m| m.phase) {
        let (a, b) = m.map_or((0, 0), |m| (m.score_a, m.score_b));
        msg = match winner {
            Some(t) if Some(t) == info.team => format!("VICTORY  {a} - {b}"),
            Some(_) => format!("DEFEAT  {a} - {b}"),
            None => format!("DRAW  {a} - {b}"),
        };
    } else if v.health.dead {
        msg = format!("ELIMINATED\nRESPAWN IN {:.1}", v.respawn_s.max(0.0));
    }
    for children in &banner {
        for c in children.iter() {
            if let Ok(mut t) = texts.get_mut(c) {
                t.0 = msg.clone();
            }
        }
    }
    let show_board = control.paused || keys.pressed(KeyCode::Tab);
    for mut vis in &mut pause {
        *vis = if control.paused { Visibility::Inherited } else { Visibility::Hidden };
    }
    if show_board {
        let mut lines = vec![];
        if let Some(code) = &session.join_code {
            lines.push(format!("JOIN CODE  {code}"));
            if let Some(addr) = session.lan_addr {
                lines.push(format!("(LAN {addr})"));
            }
            lines.push(String::new());
        }
        for team in [Some(Team::A), Some(Team::B), None] {
            let mut rows: Vec<_> = players.iter().filter(|(i, _)| i.team == team).collect();
            if rows.is_empty() {
                continue;
            }
            rows.sort_by_key(|(_, s)| std::cmp::Reverse(s.kills));
            lines.push(match team {
                Some(Team::A) => "TEAM TEAL".into(),
                Some(Team::B) => "TEAM CORAL".into(),
                None => "PLAYERS".into(),
            });
            for (i, s) in rows {
                lines.push(format!("{:<16} {:>3} / {:<3}", i.name, s.kills, s.deaths));
            }
            lines.push(String::new());
        }
        for mut t in &mut board {
            t.0 = lines.join("\n");
        }
    }
    let _ = team_color;
}

fn update_damage_indicators(
    feedback: Res<Feedback>,
    camera: Query<&GlobalTransform, With<ViewCamera>>,
    mut chevrons: Query<(&DamageChevron, &mut Node, &mut Visibility)>,
) {
    let Some(cam) = camera.iter().next() else { return };
    let fwd = cam.forward().with_y(0.0).normalize_or_zero();
    let right = cam.right().with_y(0.0).normalize_or_zero();
    for (c, mut node, mut vis) in &mut chevrons {
        match feedback.damage.get(c.0) {
            Some((from, _)) => {
                let d = (*from - cam.translation()).with_y(0.0).normalize_or_zero();
                let (x, y) = (d.dot(right), -d.dot(fwd));
                let r = 130.0;
                node.margin = UiRect { left: px(x * r * 2.0), top: px(y * r * 2.0), ..default() };
                *vis = Visibility::Inherited;
            }
            None => *vis = Visibility::Hidden,
        }
    }
}

fn pause_buttons(
    q: Query<(&Interaction, &PauseButton), Changed<Interaction>>,
    mut control: ResMut<LocalControl>,
    mut requests: MessageWriter<NetRequest>,
    mut cursor: Query<&mut bevy::window::CursorOptions, With<bevy::window::PrimaryWindow>>,
) {
    for (i, b) in &q {
        if *i != Interaction::Pressed {
            continue;
        }
        match b {
            PauseButton::Resume => {
                control.paused = false;
                for mut c in &mut cursor {
                    c.visible = false;
                    c.grab_mode = bevy::window::CursorGrabMode::Locked;
                }
            }
            PauseButton::Leave => {
                control.paused = false;
                requests.write(NetRequest::Leave { reason: None });
            }
        }
    }
}
