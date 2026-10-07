//! In-match HUD: a compact, stylized readout instead of info panels (user direction).
//!
//! - **Vitals** (bottom left): one row per region, like a boss bar. A thin strip of halo-arc shield in the
//!   arc's tier colour sits over a segmented HP bar (one segment per 10 points, so a region's size is its
//!   HP). Recent damage trails in orange. Bleeding and broken limbs show as chips on the row, only where
//!   the mode's rules have them.
//! - **No weapon panel.** A mag check leaves a small card (estimate + which magazine and ammo); reloads,
//!   item use and fire-mode changes show briefly under the crosshair.
//! - Score (top centre, ally/enemy colours), kill feed (top right), crosshair, hit marker and damage
//!   direction stay.
//!
//! Hard rule: no exact ammo count anywhere. Rounds are only ever reported as a mag-check estimate.

use crate::AppState;
use crate::client::{Feedback, LocalControl};
use crate::config::Data;
use crate::net::{NetRequest, Session};
use crate::render::ViewCamera;
use crate::ui_kit::{self as kit, Face, UiFonts, abs, panel};
use bevy::prelude::*;
use lightyear::prelude::*;
use vetf_net::*;
use vetf_sim::Zone;
use vetf_sim::data::FireMode;
use vetf_sim::level::Team;
use vetf_sim::weapon::{ReloadKind, WeaponAction, secs_to_ticks};

pub struct HudPlugin;

impl Plugin for HudPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(AppState::InGame), spawn_hud)
            .add_systems(OnEnter(AppState::Connecting), spawn_connecting)
            .add_systems(
                Update,
                (
                    update_vitals,
                    update_mag_card,
                    update_action,
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

/// HUD bars: px per point of HP or shield, points per segment, and the gap between segments.
const PX_PER_POINT: f32 = 2.0;
const SEG_POINTS: f32 = 10.0;
const SEG_GAP: f32 = 3.0;
const HP_H: f32 = 14.0;
const SHIELD_H: f32 = 6.0;
/// Recent damage stays visible this long, then drains at this rate (points per second).
const GHOST_HOLD_S: f32 = 0.45;
const GHOST_DRAIN: f32 = 90.0;
/// A fire-mode change shows under the crosshair this long.
const TOAST_S: f32 = 1.2;
const FEED_ROWS: usize = 5;

#[derive(Component)]
struct RowLabel(Zone);
#[derive(Component)]
struct HpSeg;
#[derive(Component)]
struct HpFill(Zone, usize);
#[derive(Component)]
struct GhostFill(Zone, usize);
#[derive(Component)]
struct ShieldSeg(Zone, usize);
#[derive(Component)]
struct ShieldFill(Zone, usize);
#[derive(Component, Clone, Copy, PartialEq, Eq)]
enum Chip {
    Bleed,
    Broken,
    Heal,
}
#[derive(Component)]
struct ZoneChip(Zone, Chip);
#[derive(Component)]
struct VitalsHeader;
#[derive(Component)]
struct VitalsStatus;
#[derive(Component)]
struct MagCardRoot;
#[derive(Component)]
struct MagCardEstimate;
#[derive(Component)]
struct MagCardMag;
#[derive(Component)]
struct MagCardSegment(u8);
#[derive(Component)]
struct ActionRoot;
#[derive(Component)]
struct ActionText;
#[derive(Component)]
struct ActionTrack;
#[derive(Component)]
struct ActionFill;
#[derive(Component)]
struct ScoreRoot;
#[derive(Component)]
struct ScoreAlly;
#[derive(Component)]
struct ScoreEnemy;
#[derive(Component)]
struct ScoreBox;
#[derive(Component)]
struct MatchClock;
#[derive(Component)]
struct MatchSub;
#[derive(Component)]
struct CrosshairArm(u8);
#[derive(Component)]
struct HitMarker;
#[derive(Component)]
struct FeedRow(usize);
#[derive(Component)]
struct FeedKiller(usize);
#[derive(Component)]
struct FeedVictim(usize);
#[derive(Component)]
struct FeedTag(usize);
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

fn spawn_connecting(mut commands: Commands, fonts: Res<UiFonts>) {
    commands.spawn((
        Node {
            width: percent(100),
            height: percent(100),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            ..default()
        },
        BackgroundColor(kit::BG0),
        DespawnOnExit(AppState::Connecting),
        children![(ConnectingText, fonts.text("CONNECTING...", Face::Display, 700, 28.0, kit::TEXT_HI, 0.08))],
    ));
}

fn update_connecting(session: Res<Session>, mut q: Query<&mut Text, With<ConnectingText>>) {
    for mut t in &mut q {
        t.0 = session.status.clone().unwrap_or_else(|| "STARTING MATCH...".into()).to_uppercase();
    }
}

/// Segment widths (px) for a bar of `max` points.
fn segments(max: f32) -> Vec<f32> {
    let n = (max / SEG_POINTS).ceil().max(0.0) as usize;
    (0..n).map(|i| (max - i as f32 * SEG_POINTS).min(SEG_POINTS) * PX_PER_POINT - SEG_GAP).collect()
}

/// How full segment `i` of a bar of `max` points is at `value` points (the last segment may be short).
fn seg_fill(value: f32, max: f32, i: usize) -> f32 {
    let start = i as f32 * SEG_POINTS;
    let size = (max - start).min(SEG_POINTS);
    if size <= 0.0 { 0.0 } else { ((value - start) / size).clamp(0.0, 1.0) }
}

fn spawn_hud(mut commands: Commands, data: Res<Data>, fonts: Res<UiFonts>) {
    let root = commands
        .spawn((
            Node { width: percent(100), height: percent(100), ..default() },
            DespawnOnExit(AppState::InGame),
            Pickable::IGNORE,
        ))
        .id();

    // --- vitals (bottom left)
    let vitals = commands
        .spawn((
            kit::panel_bg(
                Node {
                    flex_direction: FlexDirection::Column,
                    padding: UiRect::axes(px(14), px(12)),
                    row_gap: px(7),
                    ..abs(Some(32.0), None, None, Some(32.0))
                },
                kit::PANEL.with_alpha(0.45),
            ),
            ChildOf(root),
        ))
        .id();
    commands.spawn((
        Node { column_gap: px(10), align_items: AlignItems::Center, margin: UiRect::bottom(px(2)), ..default() },
        ChildOf(vitals),
        children![
            (VitalsHeader, fonts.text("", Face::Display, 700, 14.0, kit::TEXT_MID, 0.14)),
            (VitalsStatus, fonts.text("", Face::Display, 700, 14.0, kit::WARN, 0.14)),
        ],
    ));
    // The largest arc any halo can have, so every loadout fits the shield strip.
    let share = data.armor.zone_capacity_share.iter().fold(0.0f32, |m, (_, s)| m.max(*s));
    let max_arc = data.armor.capacity.values().filter_map(|c| c.last()).fold(0.0f32, |m, c| m.max(*c * share));
    for zone in Zone::ALL {
        let row = commands
            .spawn((Node { align_items: AlignItems::Center, column_gap: px(8), ..default() }, ChildOf(vitals)))
            .id();
        commands.spawn((
            RowLabel(zone),
            fonts.text(zone.label(), Face::Display, 700, 14.0, kit::TEXT_MID, 0.16),
            Node { width: px(54), ..default() },
            ChildOf(row),
        ));
        let bars = commands
            .spawn((Node { flex_direction: FlexDirection::Column, row_gap: px(2), ..default() }, ChildOf(row)))
            .id();
        let shield = commands.spawn((Node { height: px(SHIELD_H), ..default() }, ChildOf(bars))).id();
        for (i, w) in segments(max_arc).into_iter().enumerate() {
            commands.spawn((
                ShieldSeg(zone, i),
                Node { width: px(w), height: percent(100), margin: UiRect::right(px(SEG_GAP)), ..default() },
                BackgroundColor(kit::UNLIT),
                ChildOf(shield),
                children![(
                    ShieldFill(zone, i),
                    Node { width: percent(100), height: percent(100), ..default() },
                    BackgroundColor(kit::TIERS[1])
                )],
            ));
        }
        let hp = commands.spawn((Node { height: px(HP_H), ..default() }, ChildOf(bars))).id();
        for (i, w) in segments(data.armor.zone_hp[zone]).into_iter().enumerate() {
            commands.spawn((
                HpSeg,
                Node { width: px(w), height: percent(100), margin: UiRect::right(px(SEG_GAP)), ..default() },
                BackgroundColor(kit::UNLIT),
                ChildOf(hp),
                children![
                    (
                        GhostFill(zone, i),
                        Node { position_type: PositionType::Absolute, height: percent(100), ..default() },
                        BackgroundColor(kit::HP_DMG)
                    ),
                    (
                        HpFill(zone, i),
                        Node { position_type: PositionType::Absolute, height: percent(100), ..default() },
                        BackgroundColor(kit::HP_OK)
                    ),
                ],
            ));
        }
        for (chip, label, bg, ink) in [
            (Chip::Bleed, "BLEED", kit::BLEED, kit::TEXT_HI),
            (Chip::Broken, "BROKEN", kit::HP_DMG, kit::BG0),
            (Chip::Heal, "+ HEAL", kit::HEAL, kit::BG0),
        ] {
            commands.spawn((
                ZoneChip(zone, chip),
                Node {
                    padding: UiRect::axes(px(6), px(1)),
                    border_radius: BorderRadius::all(px(2)),
                    display: Display::None,
                    ..default()
                },
                BackgroundColor(bg),
                ChildOf(row),
                children![fonts.text(label, Face::Display, 700, 13.0, ink, 0.12)],
            ));
        }
    }

    // --- mag check card (bottom right): an estimate, never a count
    let card = commands
        .spawn((
            MagCardRoot,
            panel(Node {
                flex_direction: FlexDirection::Column,
                padding: UiRect::all(px(12)),
                row_gap: px(6),
                width: px(240),
                ..abs(None, Some(32.0), None, Some(32.0))
            }),
            Visibility::Hidden,
            ChildOf(root),
        ))
        .id();
    commands.spawn((
        Node { justify_content: JustifyContent::SpaceBetween, ..default() },
        ChildOf(card),
        children![(fonts.lbl("MAG CHECK")), (MagCardMag, fonts.text("", Face::Display, 700, 13.0, kit::TEXT, 0.12))],
    ));
    commands.spawn((MagCardEstimate, fonts.text("", Face::Display, 700, 26.0, kit::TEXT_HI, 0.04), ChildOf(card)));
    let segs = commands.spawn((Node { column_gap: px(3), height: px(6), ..default() }, ChildOf(card))).id();
    for i in 0..6 {
        commands.spawn((
            MagCardSegment(i),
            Node { flex_grow: 1.0, height: percent(100), ..default() },
            BackgroundColor(kit::UNLIT),
            ChildOf(segs),
        ));
    }
    commands.spawn((fonts.micro("AN ESTIMATE, NOT A COUNT"), ChildOf(card)));

    // --- action readout (under the crosshair): reload, item use, mag check, fire mode
    commands.spawn((
        ActionRoot,
        Node {
            width: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            row_gap: px(5),
            // A little under the screen centre (the UI is laid out at 1080p and scaled to the window).
            ..abs(Some(0.0), None, Some(kit::REF_HEIGHT * 0.5 + 64.0), None)
        },
        Visibility::Hidden,
        ChildOf(root),
        children![
            (ActionText, fonts.text("", Face::Display, 700, 14.0, kit::TEXT_HI, 0.14)),
            (
                ActionTrack,
                Node { width: px(180), height: px(3), ..default() },
                BackgroundColor(kit::STROKE_MID),
                children![(
                    ActionFill,
                    Node { width: percent(0), height: percent(100), ..default() },
                    BackgroundColor(kit::TEXT_HI)
                )]
            ),
        ],
    ));

    // --- score (top centre)
    commands.spawn((
        ScoreRoot,
        Node { width: percent(100), justify_content: JustifyContent::Center, ..abs(None, None, Some(24.0), None) },
        ChildOf(root),
        children![(
            Node { column_gap: px(3), align_items: AlignItems::Stretch, ..default() },
            children![
                (
                    ScoreBox,
                    Node {
                        width: px(64),
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        ..default()
                    },
                    BackgroundColor(kit::ALLY.with_alpha(0.92)),
                    children![(ScoreAlly, fonts.text("0", Face::Display, 700, 30.0, kit::BG0, 0.0))]
                ),
                (
                    panel(Node {
                        padding: UiRect::axes(px(18), px(4)),
                        flex_direction: FlexDirection::Column,
                        align_items: AlignItems::Center,
                        min_width: px(128),
                        ..default()
                    }),
                    children![
                        (MatchClock, fonts.text("", Face::Display, 700, 24.0, kit::TEXT_HI, 0.04)),
                        (MatchSub, fonts.micro("")),
                    ]
                ),
                (
                    ScoreBox,
                    Node {
                        width: px(64),
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        ..default()
                    },
                    BackgroundColor(kit::ENEMY.with_alpha(0.92)),
                    children![(ScoreEnemy, fonts.text("0", Face::Display, 700, 30.0, kit::BG0, 0.0))]
                ),
            ]
        )],
    ));

    // --- kill feed (top right)
    let feed = commands
        .spawn((
            Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::FlexEnd,
                row_gap: px(4),
                ..abs(None, Some(32.0), Some(24.0), None)
            },
            ChildOf(root),
        ))
        .id();
    for i in 0..FEED_ROWS {
        commands.spawn((
            FeedRow(i),
            panel(Node {
                padding: UiRect::axes(px(10), px(4)),
                column_gap: px(8),
                align_items: AlignItems::Center,
                display: Display::None,
                ..default()
            }),
            ChildOf(feed),
            children![
                (FeedKiller(i), fonts.text("", Face::Display, 700, 15.0, kit::TEXT, 0.04)),
                (fonts.text(">", Face::Display, 700, 15.0, kit::TEXT_LOW, 0.0)),
                (FeedVictim(i), fonts.text("", Face::Display, 700, 15.0, kit::TEXT, 0.04)),
                (FeedTag(i), fonts.text("", Face::Display, 700, 11.0, kit::WARN, 0.16)),
            ],
        ));
    }

    // --- crosshair + hit marker + damage direction (centre)
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
        fonts.text("X", Face::Display, 700, 26.0, Color::WHITE, 0.0),
        Visibility::Hidden,
        ChildOf(center),
    ));
    for i in 0..4 {
        commands.spawn((
            DamageChevron(i),
            Node { position_type: PositionType::Absolute, width: px(18), height: px(18), ..default() },
            BackgroundColor(kit::ENEMY.with_alpha(0.85)),
            Visibility::Hidden,
            ChildOf(center),
        ));
    }

    // --- centre banner (death / match end) and pause menu
    commands.spawn((
        CenterBanner,
        Node { width: percent(100), justify_content: JustifyContent::Center, ..abs(None, None, Some(200.0), None) },
        ChildOf(root),
        children![(fonts.text("", Face::Display, 700, 34.0, kit::TEXT_HI, 0.06), TextLayout::justify(Justify::Center))],
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
        BackgroundColor(kit::BG0.with_alpha(0.78)),
        Visibility::Hidden,
        ChildOf(root),
        children![
            (fonts.text("PAUSED", Face::Display, 700, 34.0, kit::TEXT_HI, 0.08)),
            (
                ScoreboardText,
                fonts.text("", Face::Display, 600, 16.0, kit::TEXT, 0.04),
                TextLayout::justify(Justify::Center)
            ),
            menu_button(&fonts, "RESUME", PauseButton::Resume),
            menu_button(&fonts, "LEAVE MATCH", PauseButton::Leave),
        ],
    ));
}

fn menu_button(fonts: &UiFonts, label: &str, action: PauseButton) -> impl Bundle {
    (
        Button,
        action,
        Node {
            width: px(260),
            height: px(44),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            border_radius: BorderRadius::all(px(2)),
            ..default()
        },
        BackgroundColor(kit::TEXT_HI),
        children![fonts.text(label, Face::Display, 700, 16.0, kit::BG0, 0.12)],
    )
}

/// Recent-damage trail per region: the value shown, the last HP seen, and seconds before it drains.
#[derive(Default)]
struct Ghost {
    shown: [f32; 4],
    last: [f32; 4],
    hold: [f32; 4],
}

impl Ghost {
    fn step(&mut self, i: usize, hp: f32, dt: f32) {
        if hp < self.last[i] {
            self.hold[i] = GHOST_HOLD_S;
        }
        self.hold[i] -= dt;
        if self.hold[i] <= 0.0 {
            self.shown[i] -= GHOST_DRAIN * dt;
        }
        self.shown[i] = self.shown[i].max(hp);
        self.last[i] = hp;
    }
}

#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn update_vitals(
    me: Query<(&Vitals, &PlayerLoadout, Option<&PlayerItems>), With<Controlled>>,
    matches: Query<&MatchState>,
    data: Res<Data>,
    time: Res<Time>,
    mut ghost: Local<Ghost>,
    mut hp_fill: Query<(&HpFill, &mut Node, &mut BackgroundColor), (Without<GhostFill>, Without<ShieldFill>)>,
    mut ghost_fill: Query<(&GhostFill, &mut Node), (Without<HpFill>, Without<ShieldFill>)>,
    mut shield_seg: Query<(&ShieldSeg, &mut Node), (Without<HpFill>, Without<GhostFill>, Without<ShieldFill>)>,
    mut shield_fill: Query<(&ShieldFill, &mut Node, &mut BackgroundColor), (Without<HpFill>, Without<ShieldSeg>)>,
    mut labels: Query<(&RowLabel, &mut TextColor)>,
    mut chips: Query<
        (&ZoneChip, &mut Node),
        (Without<HpFill>, Without<GhostFill>, Without<ShieldSeg>, Without<ShieldFill>),
    >,
    mut header: Query<&mut Text, (With<VitalsHeader>, Without<VitalsStatus>)>,
    mut status: Query<&mut Text, (With<VitalsStatus>, Without<VitalsHeader>)>,
) {
    let Some((v, lo, items)) = me.iter().next() else { return };
    let rules = matches.iter().next().map_or(vetf_sim::data::Ruleset::FULL, |m| m.rules);
    let halo = lo.0.halo;
    let dt = time.delta_secs();
    for z in Zone::ALL {
        ghost.step(z.index(), v.health.hp[z].max(0.0), dt);
    }
    for (f, mut node, mut bg) in &mut hp_fill {
        let (hp, max) = (v.health.hp[f.0].max(0.0), v.health.max[f.0]);
        node.width = percent(seg_fill(hp, max, f.1) * 100.0);
        bg.0 = if hp / max.max(1.0) < 0.35 { kit::HP_CRIT } else { kit::HP_OK };
    }
    for (g, mut node) in &mut ghost_fill {
        node.width = percent(seg_fill(ghost.shown[g.0.index()], v.health.max[g.0], g.1) * 100.0);
    }
    for (s, mut node) in &mut shield_seg {
        let n = segments(halo.capacity[s.0]).len();
        node.display = if s.1 < n { Display::Flex } else { Display::None };
        if let Some(w) = segments(halo.capacity[s.0]).get(s.1) {
            node.width = px(*w);
        }
    }
    for (f, mut node, mut bg) in &mut shield_fill {
        node.width = percent(seg_fill(v.halo.shield[f.0], halo.capacity[f.0], f.1) * 100.0);
        bg.0 = kit::tier_color(halo.tiers[f.0]);
    }
    let healing = items
        .filter(|_| !v.health.dead)
        .and_then(|i| i.0.using)
        .and_then(|u| Some((u.zone, data.items.spec(lo.0.kit.get(u.slot as usize)?).scope)));
    for (label, mut c) in &mut labels {
        c.0 = if v.health.hp[label.0] <= 0.0 { kit::HP_CRIT } else { kit::TEXT_MID };
    }
    for (chip, mut node) in &mut chips {
        let z = chip.0;
        let on = match chip.1 {
            Chip::Bleed => rules.bleeding && v.health.bleeding.active[z] > 0.0,
            Chip::Broken => v.wounds.broken.contains(z),
            Chip::Heal => match healing {
                Some((Some(hz), _)) => hz == z,
                Some((None, _)) => true,
                None => false,
            },
        };
        node.display = if on { Display::Flex } else { Display::None };
    }
    for mut t in &mut header {
        t.0 = match halo.core {
            Some(core) => format!("{} CORE  /  {}", core.label(), lo.0.weight.label()).to_uppercase(),
            None => "NO HALO".into(),
        };
    }
    for mut t in &mut status {
        let mut parts = vec![];
        if v.halo.regen_wait_s > 0.0 && halo.core.is_some() {
            parts.push(format!("REGEN {:.0}", v.halo.regen_wait_s.ceil()));
        }
        if v.protected_s > 0.0 {
            parts.push("PROTECTED".into());
        }
        t.0 = parts.join("  ");
    }
}

#[allow(clippy::type_complexity)]
fn update_mag_card(
    me: Query<(&PlayerWeapon, &PlayerLoadout), With<Controlled>>,
    mut root: Query<&mut Visibility, With<MagCardRoot>>,
    mut est: Query<&mut Text, (With<MagCardEstimate>, Without<MagCardMag>)>,
    mut mag: Query<&mut Text, (With<MagCardMag>, Without<MagCardEstimate>)>,
    mut segs: Query<(&MagCardSegment, &mut BackgroundColor)>,
) {
    let card = me.iter().next().and_then(|(w, lo)| Some((w.0.card?, lo)));
    for mut v in &mut root {
        *v = if card.is_some() { Visibility::Inherited } else { Visibility::Hidden };
    }
    let Some((card, lo)) = card else { return };
    for mut t in &mut est {
        t.0 = card.estimate.label().into();
    }
    for mut t in &mut mag {
        t.0 = format!("MAG {}  {}", card.slot + 1, lo.0.weapon.ammo(card.slot).label);
    }
    for (s, mut bg) in &mut segs {
        bg.0 = if s.0 == card.estimate.segment() { kit::TEXT_HI } else { kit::UNLIT };
    }
}

/// What is happening to the gun or in your hands, under the crosshair: reloading (which magazine), using an
/// item, checking the mag, or a fire-mode change.
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn update_action(
    me: Query<(&PlayerWeapon, &PlayerLoadout, Option<&PlayerItems>, &Vitals), With<Controlled>>,
    data: Res<Data>,
    time: Res<Time>,
    mut last_mode: Local<Option<FireMode>>,
    mut toast: Local<f32>,
    mut root: Query<&mut Visibility, With<ActionRoot>>,
    mut text: Query<&mut Text, With<ActionText>>,
    mut track: Query<&mut Visibility, (With<ActionTrack>, Without<ActionRoot>)>,
    mut fill: Query<(&mut Node, &mut BackgroundColor), (With<ActionFill>, Without<ActionRoot>)>,
) {
    let Some((w, lo, items, v)) = me.iter().next() else { return };
    let spec = lo.0.weapon.spec(&data);
    let hz = data.net.tick_hz;
    // The dead are not simulated: their last action would stay frozen on screen.
    let items = items.filter(|_| !v.health.dead);
    if last_mode.is_some_and(|m| m != w.0.fire_mode) {
        *toast = TOAST_S;
    }
    *last_mode = Some(w.0.fire_mode);
    *toast = (*toast - time.delta_secs()).max(0.0);
    let progress = |left: u16, total: u16| 1.0 - left as f32 / total.max(1) as f32;
    let shown: Option<(String, Option<f32>, Color)> = if let Some(u) = items.and_then(|i| i.0.using) {
        let item = data.items.spec(&lo.0.kit[u.slot as usize]);
        let zone = u.zone.map_or(String::new(), |z| format!("  /  {}", z.label()));
        Some((format!("{}{zone}", item.label), Some(progress(u.left, u.total)), kit::HEAL))
    } else {
        match w.0.action {
            WeaponAction::Reloading { left, kind, slot } if !v.health.dead => {
                let s = match kind {
                    ReloadKind::Tactical => spec.reload_tactical_s,
                    ReloadKind::Empty => spec.reload_empty_s,
                } * lo.0.weapon.mods.reload;
                let total = secs_to_ticks(s, hz).max(1);
                let label = format!("RELOADING  /  MAG {}  {}", slot + 1, lo.0.weapon.ammo(slot).label);
                Some((label, Some(progress(left, total)), kit::TEXT_HI))
            }
            WeaponAction::MagChecking { left } if !v.health.dead => {
                let total = secs_to_ticks(spec.mag_check_s, hz).max(1);
                Some(("CHECKING MAG".into(), Some(progress(left, total)), kit::TEXT_HI))
            }
            _ if v.health.dead => None,
            _ if *toast > 0.0 => {
                let mode = match w.0.fire_mode {
                    FireMode::Auto => "AUTO",
                    FireMode::Semi => "SEMI",
                    FireMode::Bolt => "BOLT",
                };
                Some((mode.into(), None, kit::TEXT_HI))
            }
            _ => None,
        }
    };
    for mut vis in &mut root {
        *vis = if shown.is_some() { Visibility::Inherited } else { Visibility::Hidden };
    }
    let Some((label, bar, color)) = shown else { return };
    for mut t in &mut text {
        t.0 = label.clone();
    }
    for mut v in &mut track {
        *v = if bar.is_some() { Visibility::Inherited } else { Visibility::Hidden };
    }
    for (mut node, mut bg) in &mut fill {
        node.width = percent(bar.unwrap_or(0.0) * 100.0);
        bg.0 = color;
    }
}

#[allow(clippy::type_complexity)]
fn update_score(
    matches: Query<&MatchState>,
    me: Query<&PlayerInfo, With<Controlled>>,
    mut ally: Query<&mut Text, (With<ScoreAlly>, Without<ScoreEnemy>, Without<MatchClock>, Without<MatchSub>)>,
    mut enemy: Query<&mut Text, (With<ScoreEnemy>, Without<ScoreAlly>, Without<MatchClock>, Without<MatchSub>)>,
    mut clock: Query<&mut Text, (With<MatchClock>, Without<ScoreAlly>, Without<ScoreEnemy>, Without<MatchSub>)>,
    mut sub: Query<&mut Text, (With<MatchSub>, Without<ScoreAlly>, Without<ScoreEnemy>, Without<MatchClock>)>,
    mut boxes: Query<&mut Node, With<ScoreBox>>,
) {
    let Some(m) = matches.iter().next() else { return };
    // Scores are relative: your team on the left in the ally colour.
    let mine = me.iter().next().and_then(|i| i.team);
    let (a, b) = if mine == Some(Team::B) { (m.score_b, m.score_a) } else { (m.score_a, m.score_b) };
    for mut t in &mut ally {
        t.0 = a.to_string();
    }
    for mut t in &mut enemy {
        t.0 = b.to_string();
    }
    let range = m.mode == MatchMode::Range;
    for mut node in &mut boxes {
        node.display = if range { Display::None } else { Display::Flex };
    }
    for mut t in &mut clock {
        t.0 = if range {
            "GUN RANGE".into()
        } else {
            let s = m.time_left_s.max(0.0) as u32;
            format!("{:02}:{:02}", s / 60, s % 60)
        };
    }
    for mut t in &mut sub {
        t.0 = if range { "FREE PRACTICE".into() } else { format!("TDM  /  FIRST TO {}", m.score_limit) };
    }
}

#[allow(clippy::type_complexity)]
fn update_crosshair(
    me: Query<(&PlayerWeapon, &PlayerLoadout, &PlayerMove, &Vitals), With<Controlled>>,
    data: Res<Data>,
    feedback: Res<Feedback>,
    mut arms: Query<(&CrosshairArm, &mut Node, &mut Visibility), Without<HitMarker>>,
    mut marker: Query<(&mut Visibility, &mut TextColor), With<HitMarker>>,
) {
    let Some((w, lo, mv, v)) = me.iter().next() else { return };
    let spec = lo.0.weapon.spec(&data);
    let wounds = v.wounds;
    let env = vetf_sim::player::weapon_env(&data, &mv.0, &wounds);
    let spread = w.0.spread_deg(&data, spec, &lo.0.weapon, &env);
    // The UI is laid out at 1080p and scaled to the window, so project with the reference height.
    let focal = kit::REF_HEIGHT * 0.5 / (78f32.to_radians() * 0.5).tan();
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
                    HitKind::Shield => kit::TIERS[2],
                    HitKind::Health => Color::WHITE,
                    HitKind::Kill => kit::ENEMY,
                };
            }
            None => *vis = Visibility::Hidden,
        }
    }
}

#[allow(clippy::type_complexity)]
fn update_feed(
    feedback: Res<Feedback>,
    me: Query<&PlayerInfo, With<Controlled>>,
    players: Query<&PlayerInfo>,
    mut rows: Query<(&FeedRow, &mut Node)>,
    mut killers: Query<(&FeedKiller, &mut Text, &mut TextColor), (Without<FeedVictim>, Without<FeedTag>)>,
    mut victims: Query<(&FeedVictim, &mut Text, &mut TextColor), (Without<FeedKiller>, Without<FeedTag>)>,
    mut tags: Query<(&FeedTag, &mut Text), (Without<FeedKiller>, Without<FeedVictim>)>,
) {
    let mine = me.iter().next().map(|i| (i.name.clone(), i.team));
    // Ally is you and your team; in free-for-all modes everyone else is an enemy.
    let color = |name: &str| {
        let Some((my_name, my_team)) = &mine else { return kit::TEXT };
        let team = players.iter().find(|p| p.name == name).and_then(|p| p.team);
        if name == my_name || (my_team.is_some() && team == *my_team) { kit::ALLY } else { kit::ENEMY }
    };
    let entries: Vec<_> = feedback.kills.iter().rev().take(FEED_ROWS).collect();
    for (row, mut node) in &mut rows {
        node.display = if row.0 < entries.len() { Display::Flex } else { Display::None };
    }
    for (k, mut t, mut c) in &mut killers {
        if let Some((killer, ..)) = entries.get(k.0) {
            t.0 = if killer.is_empty() { "--".into() } else { killer.clone() };
            c.0 = if killer.is_empty() { kit::TEXT_MID } else { color(killer) };
        }
    }
    for (v, mut t, mut c) in &mut victims {
        if let Some((_, victim, ..)) = entries.get(v.0) {
            t.0 = victim.clone();
            c.0 = color(victim);
        }
    }
    for (tag, mut t) in &mut tags {
        if let Some((_, _, hs, _)) = entries.get(tag.0) {
            t.0 = if *hs { "HEADSHOT".into() } else { String::new() };
        }
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
        let teams = match info.team {
            Some(t) => vec![Some(t), Some(t.other())],
            None => vec![None],
        };
        for team in teams {
            let mut rows: Vec<_> = players.iter().filter(|(i, _)| i.team == team).collect();
            if rows.is_empty() {
                continue;
            }
            rows.sort_by_key(|(_, s)| std::cmp::Reverse(s.kills));
            lines.push(match team {
                Some(t) if Some(t) == info.team => "YOUR TEAM".into(),
                Some(_) => "ENEMY TEAM".into(),
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn segments_are_ten_points_each_with_a_short_last_one() {
        let s = segments(45.0);
        assert_eq!(s.len(), 5);
        assert!((s[0] - (10.0 * PX_PER_POINT - SEG_GAP)).abs() < 1e-4);
        assert!((s[4] - (5.0 * PX_PER_POINT - SEG_GAP)).abs() < 1e-4);
        assert!(segments(0.0).is_empty());
        assert_eq!(seg_fill(45.0, 45.0, 4), 1.0, "a full short segment is full");
        assert_eq!(seg_fill(42.5, 45.0, 4), 0.5);
        assert_eq!(seg_fill(45.0, 45.0, 0), 1.0);
        assert_eq!(seg_fill(3.0, 45.0, 1), 0.0);
        assert_eq!(seg_fill(3.0, 45.0, 9), 0.0, "past the end");
    }
}
