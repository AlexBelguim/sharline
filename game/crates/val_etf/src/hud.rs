//! In-match HUD: a compact, stylized readout instead of info panels (user direction).
//!
//! - **Vitals** (bottom left): one row per region, like a boss bar. A thin strip of halo-arc shield in the
//!   arc's tier colour sits over a segmented HP bar (one segment per 10 points, so a region's size is its
//!   HP). Recent damage trails in orange. Bleeding and broken limbs show as chips on the row, only where
//!   the mode's rules have them.
//! - **No weapon panel.** A mag check leaves a small card (estimate + which magazine and ammo); reloads,
//!   item use and fire-mode changes show briefly under the crosshair. With MAG CHECK on EXACT (an option, see
//!   below) a round counter sits in the bottom right corner too.
//! - Score (top centre, ally/enemy colours: your team and theirs, or in free-for-all your kills and the
//!   leader's), kill feed (top right), crosshair and damage direction stay. Hit markers are drawn on the player
//!   hit, not here (`render::hit_fx`).
//!
//! The settings shape it as they change: HUD scale, safe area and the 16:9 width scale and place the HUD
//! (the crosshair keeps its own size), the crosshair and hit markers follow MOUSE & AIM, and the kill feed
//! lines, team colours, damage flash and reduce flashing follow HUD & ACCESSIBILITY.
//!
//! The genre rule: no exact ammo count. Rounds are reported as a mag-check estimate. The one exception is the
//! MAG CHECK option (user direction 2026-10-09), off by default: on EXACT ([`mag_check_mode`]: the host's match
//! setting in team deathmatch and free-for-all, the player's own in the gun range) the HUD keeps a permanent
//! counter of the rounds in the gun's magazine, and the mag check card gives the exact count.

use crate::AppState;
use crate::client::{ASSIST_POPUP_S, FeedEntry, Feedback};
use crate::config::{Cli, Data};
use crate::net::Session;
use crate::render::ViewCamera;
use crate::settings::{DamageFlash, Settings, Ultrawide, crosshair_rects, rgb_color};
use crate::streaks::StreakLine;
use crate::ui_kit::{self as kit, Face, UiFonts, abs, panel};
use bevy::prelude::*;
use bevy::ui::{ColorStop, RadialGradient, RadialGradientShape, UiPosition};
use bevy::window::PrimaryWindow;
use lightyear::prelude::*;
use vetf_net::*;
use vetf_sim::Zone;
use vetf_sim::data::FireMode;
use vetf_sim::level::Team;
use vetf_sim::weapon::{MagCheckMode, MagEstimate, ReloadKind, WeaponAction, secs_to_ticks};

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
                    update_ammo_counter,
                    update_action,
                    update_score,
                    update_crosshair,
                    update_feed,
                    update_assist_popup,
                    update_streak_hud,
                    update_overlays,
                    update_damage_indicators,
                    update_connecting.run_if(in_state(AppState::Connecting)),
                )
                    .run_if(in_state(AppState::InGame).or_else(in_state(AppState::Connecting))),
            )
            .add_systems(
                Update,
                (fit_hud, update_damage_flash, demo_hud_fx, hide_under_screens).run_if(in_state(AppState::InGame)),
            );
    }
}

/// The HUD's centre layer (outside the scaled canvas): crosshair, damage direction and flash.
#[derive(Component)]
struct HudCenter;

/// The HUD hides while a hub screen is open over the match (the ESC menu, Settings, the lobby).
fn hide_under_screens(
    screens: Res<crate::screens::Screens>,
    mut root: Query<&mut Visibility, Or<(With<HudRoot>, With<HudCenter>)>>,
) {
    let want = if screens.is_empty() { Visibility::Inherited } else { Visibility::Hidden };
    for mut v in &mut root {
        v.set_if_neq(want);
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
/// Kill streaks: the feed's streak tag, the banner, the toast and the counter (a warm gold, like the aura).
const STREAK_GOLD: Color = Color::srgb(1.0, 0.76, 0.33);
/// The most KILL FEED LINES offers; the setting shows 3, 5 or 7 of them.
const FEED_ROWS: usize = 7;
/// The camera's vertical field of view when there is no perspective view camera (render.rs's default).
const FALLBACK_VFOV_DEG: f32 = 78.0;
/// The crosshair outline (1 px, drawn around each line).
const CROSSHAIR_OUTLINE: Color = Color::srgba(0.0, 0.0, 0.0, 0.6);
/// The red edge flash when hit: its peak alpha at SOFT and FULL, the cap REDUCE FLASHING puts on it, and how
/// long it fades.
const FLASH_SOFT: f32 = 0.12;
const FLASH_FULL: f32 = 0.25;
const FLASH_REDUCED: f32 = 0.08;
const FLASH_S: f32 = 0.45;

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
/// The mag check card's footnote (estimate or exact count).
#[derive(Component)]
struct MagCardNote;
/// The permanent round counter (MAG CHECK on EXACT only).
#[derive(Component)]
struct AmmoCounterRoot;
#[derive(Component)]
struct AmmoCounterRounds;
#[derive(Component)]
struct AmmoCounterMag;
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
/// A team score box: yours (ally colour) or theirs (enemy colour).
#[derive(Component)]
struct ScoreBox {
    enemy: bool,
}
#[derive(Component)]
struct MatchClock;
#[derive(Component)]
struct MatchSub;
/// The HUD canvas, scaled and narrowed by the settings (`fit_hud`).
#[derive(Component)]
struct HudRoot;
/// The corner and edge groups' frame: the canvas less the safe-area margin.
#[derive(Component)]
struct HudSafeArea;
/// One rectangle of the crosshair (`settings::crosshair_rects`: four lines, then the dot).
#[derive(Component)]
struct CrosshairPart(usize);
/// The red screen-edge flash when hit.
#[derive(Component)]
struct DamageFlashEdge;
#[derive(Component)]
struct FeedRow(usize);
/// One text of a kill feed row (`feed_text`): row index and which part.
#[derive(Component)]
struct FeedPart(usize, Part);
#[derive(Clone, Copy, PartialEq, Eq)]
enum Part {
    Lead,
    Helper,
    Cause,
    Mid,
    Victim,
    Tag,
}
/// The ASSIST popup under the crosshair.
#[derive(Component)]
struct AssistPopup;
/// The kill streak counter, left of the vitals, and its number.
#[derive(Component)]
struct StreakCounter;
#[derive(Component)]
struct StreakCount;
/// Your kill streak reward toast.
#[derive(Component)]
struct StreakToastText;
/// The map-wide kill streak banner, its caption and headline.
#[derive(Component)]
struct StreakBannerRoot;
#[derive(Component)]
struct StreakBannerCaption;
#[derive(Component)]
struct StreakBannerHeadline;
#[derive(Component)]
struct CenterBanner;
#[derive(Component)]
struct DamageChevron(usize);
#[derive(Component)]
struct ConnectingText;

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
    // The canvas: HUD SCALE scales it about the screen centre, and on ultrawide screens it can keep 16:9.
    let root = commands
        .spawn((
            HudRoot,
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
            UiTransform::IDENTITY,
            Visibility::Inherited,
            DespawnOnExit(AppState::InGame),
            Pickable::IGNORE,
        ))
        .id();
    // The corner and edge groups sit inside the safe-area margin.
    let edges = commands
        .spawn((HudSafeArea, abs(Some(32.0), Some(32.0), Some(32.0), Some(32.0)), Pickable::IGNORE, ChildOf(root)))
        .id();

    // --- bottom left: the kill streak counter, then the vitals
    let bottom_left = commands
        .spawn((
            Node { align_items: AlignItems::FlexEnd, column_gap: px(10), ..abs(Some(0.0), None, None, Some(0.0)) },
            Pickable::IGNORE,
            ChildOf(edges),
        ))
        .id();
    // The streak counter, just left of the health block: its slot is kept in team deathmatch and free-for-all
    // (so the vitals never jump when it appears) and gone in the gun range.
    commands.spawn((
        StreakCounter,
        kit::panel_bg(
            Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::Center,
                padding: UiRect::axes(px(8), px(8)),
                row_gap: px(2),
                width: px(68),
                display: Display::None,
                ..default()
            },
            kit::PANEL.with_alpha(0.45),
        ),
        Visibility::Hidden,
        ChildOf(bottom_left),
        children![
            (StreakCount, fonts.text("", Face::Display, 700, 30.0, STREAK_GOLD, 0.0)),
            fonts.text("STREAK", Face::Display, 700, 11.0, kit::TEXT_MID, 0.16),
        ],
    ));
    let vitals = commands
        .spawn((
            kit::panel_bg(
                Node {
                    flex_direction: FlexDirection::Column,
                    padding: UiRect::axes(px(14), px(12)),
                    row_gap: px(7),
                    ..default()
                },
                kit::PANEL.with_alpha(0.45),
            ),
            ChildOf(bottom_left),
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

    // --- bottom right: the mag check card, over the round counter (MAG CHECK on EXACT only)
    let corner = commands
        .spawn((
            Node {
                flex_direction: FlexDirection::Column,
                align_items: AlignItems::FlexEnd,
                row_gap: px(8),
                ..abs(None, Some(0.0), None, Some(0.0))
            },
            Pickable::IGNORE,
            ChildOf(edges),
        ))
        .id();
    let card = commands
        .spawn((
            MagCardRoot,
            panel(Node {
                flex_direction: FlexDirection::Column,
                padding: UiRect::all(px(12)),
                row_gap: px(6),
                width: px(240),
                ..default()
            }),
            Visibility::Hidden,
            ChildOf(corner),
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
    commands.spawn((MagCardNote, fonts.micro(ESTIMATE_NOTE), ChildOf(card)));
    // The round counter: which magazine, and its rounds out of the capacity.
    let counter = commands
        .spawn((
            AmmoCounterRoot,
            panel(Node {
                flex_direction: FlexDirection::Column,
                padding: UiRect::axes(px(12), px(10)),
                row_gap: px(4),
                width: px(240),
                display: Display::None,
                ..default()
            }),
            ChildOf(corner),
        ))
        .id();
    commands.spawn((
        Node { justify_content: JustifyContent::SpaceBetween, ..default() },
        ChildOf(counter),
        children![(fonts.lbl("ROUNDS")), (AmmoCounterMag, fonts.text("", Face::Display, 700, 13.0, kit::TEXT, 0.12))],
    ));
    commands.spawn((AmmoCounterRounds, fonts.text("", Face::Display, 700, 30.0, kit::TEXT_HI, 0.04), ChildOf(counter)));

    // --- action readout (under the crosshair): reload, item use, mag check, fire mode
    commands.spawn((
        ActionRoot,
        Node {
            width: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            row_gap: px(5),
            // A little under the screen centre.
            top: percent(50),
            margin: UiRect::top(px(64)),
            ..abs(Some(0.0), None, None, None)
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

    // --- ASSIST popup (just under the crosshair, above the action readout): short, like a kill confirm
    commands.spawn((
        Node {
            width: percent(100),
            justify_content: JustifyContent::Center,
            top: percent(50),
            margin: UiRect::top(px(36)),
            ..abs(Some(0.0), None, None, None)
        },
        ChildOf(root),
        children![(
            AssistPopup,
            fonts.text("ASSIST", Face::Display, 700, 15.0, kit::TEXT_HI, 0.24),
            Visibility::Hidden
        )],
    ));

    // --- kill streak reward toast (yours), under the action readout
    commands.spawn((
        Node {
            width: percent(100),
            justify_content: JustifyContent::Center,
            top: percent(50),
            margin: UiRect::top(px(100)),
            ..abs(Some(0.0), None, None, None)
        },
        ChildOf(root),
        children![(StreakToastText, fonts.text("", Face::Display, 700, 14.0, STREAK_GOLD, 0.14), Visibility::Hidden)],
    ));

    // --- kill streak banner (map-wide, an announced tier): a caption over a headline, above the death banner
    commands.spawn((
        StreakBannerRoot,
        Node {
            width: percent(100),
            flex_direction: FlexDirection::Column,
            align_items: AlignItems::Center,
            row_gap: px(2),
            ..abs(None, None, Some(118.0), None)
        },
        Visibility::Hidden,
        ChildOf(root),
        children![
            (StreakBannerCaption, fonts.text("", Face::Display, 700, 15.0, STREAK_GOLD, 0.3)),
            (StreakBannerHeadline, fonts.text("", Face::Display, 700, 30.0, kit::TEXT_HI, 0.06)),
        ],
    ));

    // --- score (top centre)
    // Hidden until the match state says which mode this is: the range has no teams (no team boxes).
    commands.spawn((
        ScoreRoot,
        Node {
            width: percent(100),
            justify_content: JustifyContent::Center,
            display: Display::None,
            ..abs(None, None, Some(0.0), None)
        },
        ChildOf(edges),
        children![(
            Node { column_gap: px(3), align_items: AlignItems::Stretch, ..default() },
            children![
                (
                    ScoreBox { enemy: false },
                    Node {
                        width: px(64),
                        display: Display::None,
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
                    ScoreBox { enemy: true },
                    Node {
                        width: px(64),
                        display: Display::None,
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
                ..abs(None, Some(0.0), Some(0.0), None)
            },
            ChildOf(edges),
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
                (FeedPart(i, Part::Lead), fonts.text("", Face::Display, 700, 15.0, kit::TEXT, 0.04)),
                (FeedPart(i, Part::Helper), fonts.text("", Face::Display, 700, 13.0, kit::TEXT, 0.04)),
                (FeedPart(i, Part::Cause), fonts.text("", Face::Display, 700, 13.0, kit::TEXT_MID, 0.08)),
                (FeedPart(i, Part::Mid), fonts.text(">", Face::Display, 700, 15.0, kit::TEXT_LOW, 0.0)),
                (FeedPart(i, Part::Victim), fonts.text("", Face::Display, 700, 15.0, kit::TEXT, 0.04)),
                (FeedPart(i, Part::Tag), fonts.text("", Face::Display, 700, 11.0, kit::WARN, 0.16)),
            ],
        ));
    }

    // --- damage flash, crosshair and damage direction (centre): full screen and never scaled
    // with the HUD (the crosshair has its own sizes), under the canvas so the banner draws over it.
    let center = commands
        .spawn((
            HudCenter,
            Node {
                position_type: PositionType::Absolute,
                width: percent(100),
                height: percent(100),
                align_items: AlignItems::Center,
                justify_content: JustifyContent::Center,
                ..default()
            },
            Visibility::Inherited,
            ZIndex(-1),
            DespawnOnExit(AppState::InGame),
            Pickable::IGNORE,
        ))
        .id();
    commands.spawn((
        DamageFlashEdge,
        abs(Some(0.0), Some(0.0), Some(0.0), Some(0.0)),
        BackgroundGradient::default(),
        Visibility::Hidden,
        ChildOf(center),
    ));
    // The crosshair's rectangles are placed from the screen centre.
    let anchor = commands
        .spawn((
            Node { position_type: PositionType::Absolute, left: percent(50), top: percent(50), ..default() },
            ChildOf(center),
        ))
        .id();
    for i in 0..5 {
        commands.spawn((
            CrosshairPart(i),
            Node { position_type: PositionType::Absolute, ..default() },
            BackgroundColor(Color::WHITE),
            Outline::new(px(1), px(0), Color::NONE),
            Visibility::Hidden,
            ChildOf(anchor),
        ));
    }
    for i in 0..4 {
        commands.spawn((
            DamageChevron(i),
            Node { position_type: PositionType::Absolute, width: px(18), height: px(18), ..default() },
            BackgroundColor(kit::ENEMY.with_alpha(0.85)),
            Visibility::Hidden,
            ChildOf(center),
        ));
    }

    // --- centre banner (death / match end)
    commands.spawn((
        CenterBanner,
        Node { width: percent(100), justify_content: JustifyContent::Center, ..abs(None, None, Some(200.0), None) },
        ChildOf(root),
        children![(fonts.text("", Face::Display, 700, 34.0, kit::TEXT_HI, 0.06), TextLayout::justify(Justify::Center))],
    ));
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
    let one_halo = matches.iter().next().is_some_and(|m| data.rules.fixed_loadout(m.mode).is_some());
    for mut t in &mut header {
        t.0 = halo_header(halo.core, lo.0.weight, one_halo);
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

/// The vitals panel's header: the halo and its weight class. `MENDER CORE  /  MEDIUM` in the gun range (cores
/// differ there); `HALO  /  MEDIUM` where everyone wears the same one (team deathmatch, free-for-all); the
/// weight class is what tells halos apart there.
fn halo_header(core: Option<vetf_sim::data::Core>, weight: vetf_sim::data::WeightClass, one_halo: bool) -> String {
    match core {
        Some(_) if one_halo => format!("HALO  /  {}", weight.label()),
        Some(core) => format!("{} CORE  /  {}", core.label(), weight.label()),
        None => "NO HALO".into(),
    }
}

/// The mag check card's footnote with the estimate, and with the exact count.
const ESTIMATE_NOTE: &str = "AN ESTIMATE, NOT A COUNT";
const EXACT_NOTE: &str = "EXACT COUNT · MAG CHECK: EXACT";

/// How this player reads their rounds: in team deathmatch and free-for-all the host's MAG CHECK match setting
/// (everyone plays with the same); in the gun range (or with no match yet) the player's own, from Settings >
/// Gameplay.
pub(crate) fn mag_check_mode(m: Option<&MatchState>, range: MagCheckMode) -> MagCheckMode {
    match m {
        Some(m) if m.mode.is_deathmatch() => m.mag_check,
        _ => range,
    }
}

/// The player's MAG CHECK from the replicated match and their settings.
pub(crate) fn current_mag_check(matches: &Query<&MatchState>, settings: &Settings) -> MagCheckMode {
    mag_check_mode(matches.iter().next(), settings.gameplay.range_mag_check.mode())
}

/// Rounds out of a magazine's capacity, as the counter and the exact card write them: `23 / 30`.
pub(crate) fn rounds_text(rounds: u16, capacity: u16) -> String {
    format!("{rounds} / {capacity}")
}

/// The round counter's text, or `None`: there is a counter only with MAG CHECK on EXACT.
fn ammo_counter_text(mode: MagCheckMode, rounds: u16, capacity: u16) -> Option<String> {
    mode.is_exact().then(|| rounds_text(rounds, capacity))
}

/// The mag check card's headline and footnote: the estimate, or with MAG CHECK on EXACT the exact rounds.
fn mag_card_lines(mode: MagCheckMode, estimate: MagEstimate, rounds: u16, capacity: u16) -> (String, &'static str) {
    match mode {
        MagCheckMode::Estimate => (estimate.label().to_string(), ESTIMATE_NOTE),
        MagCheckMode::Exact => (rounds_text(rounds, capacity), EXACT_NOTE),
    }
}

#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn update_mag_card(
    me: Query<(&PlayerWeapon, &PlayerLoadout), With<Controlled>>,
    matches: Query<&MatchState>,
    settings: Res<Settings>,
    mut root: Query<&mut Visibility, With<MagCardRoot>>,
    mut est: Query<&mut Text, (With<MagCardEstimate>, Without<MagCardMag>, Without<MagCardNote>)>,
    mut mag: Query<&mut Text, (With<MagCardMag>, Without<MagCardEstimate>, Without<MagCardNote>)>,
    mut note: Query<&mut Text, (With<MagCardNote>, Without<MagCardEstimate>, Without<MagCardMag>)>,
    mut segs: Query<(&MagCardSegment, &mut BackgroundColor)>,
) {
    let card = me.iter().next().and_then(|(w, lo)| Some((w.0.card?, &w.0, lo)));
    for mut v in &mut root {
        *v = if card.is_some() { Visibility::Inherited } else { Visibility::Hidden };
    }
    let Some((card, w, lo)) = card else { return };
    let rounds = w.rounds.get(card.slot as usize).copied().unwrap_or(0);
    let (headline, footnote) =
        mag_card_lines(current_mag_check(&matches, &settings), card.estimate, rounds, lo.0.weapon.mag_capacity);
    for mut t in &mut est {
        t.0.clone_from(&headline);
    }
    for mut t in &mut note {
        if t.0 != footnote {
            t.0 = footnote.into();
        }
    }
    for mut t in &mut mag {
        t.0 = format!("MAG {}  {}", card.slot + 1, lo.0.weapon.ammo(card.slot).label);
    }
    for (s, mut bg) in &mut segs {
        bg.0 = if s.0 == card.estimate.segment() { kit::TEXT_HI } else { kit::UNLIT };
    }
}

/// The permanent round counter: shown only with MAG CHECK on EXACT, while alive; the rounds in the gun's
/// magazine out of its capacity, and which magazine (its slot and ammo).
#[allow(clippy::type_complexity)]
fn update_ammo_counter(
    me: Query<(&PlayerWeapon, &PlayerLoadout, &Vitals), With<Controlled>>,
    matches: Query<&MatchState>,
    settings: Res<Settings>,
    mut root: Query<&mut Node, With<AmmoCounterRoot>>,
    mut rounds: Query<&mut Text, (With<AmmoCounterRounds>, Without<AmmoCounterMag>)>,
    mut mag: Query<&mut Text, (With<AmmoCounterMag>, Without<AmmoCounterRounds>)>,
) {
    let mode = current_mag_check(&matches, &settings);
    let shown = me.iter().next().filter(|(.., v)| !v.health.dead).and_then(|(w, lo, _)| {
        let text = ammo_counter_text(mode, w.0.mag(), lo.0.weapon.mag_capacity)?;
        Some((text, format!("MAG {}  {}", w.0.loaded + 1, lo.0.weapon.ammo(w.0.loaded).label)))
    });
    let display = if shown.is_some() { Display::Flex } else { Display::None };
    for mut n in &mut root {
        if n.display != display {
            n.display = display;
        }
    }
    let Some((text, which)) = shown else { return };
    for mut t in &mut rounds {
        if t.0 != text {
            t.0.clone_from(&text);
        }
    }
    for mut t in &mut mag {
        if t.0 != which {
            t.0.clone_from(&which);
        }
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

/// The top-centre header for a mode: (score boxes shown, title, subline). The range has no teams, so it
/// shows only what the place is; the deathmatches show the clock and the score limit between the scores
/// (team deathmatch: the two teams'; free-for-all: your kills and the leader's).
fn score_header(mode: MatchMode, time_left_s: f32, score_limit: u32) -> (bool, String, String) {
    let clock = || {
        let s = time_left_s.max(0.0) as u32;
        format!("{:02}:{:02}", s / 60, s % 60)
    };
    match mode {
        MatchMode::Range => (false, "GUN RANGE".into(), "FREE PRACTICE".into()),
        MatchMode::Tdm => (true, clock(), format!("TDM  /  FIRST TO {score_limit}")),
        MatchMode::Ffa => (true, clock(), format!("FFA  /  FIRST TO {score_limit}")),
    }
}

/// Free-for-all's score boxes: your kills, and the leader's (the best of everyone else, so while you lead it
/// is whoever is chasing you).
fn ffa_scores(scores: &[(u16, bool)]) -> (u32, u32) {
    let mine = scores.iter().find(|(_, me)| *me).map_or(0, |(k, _)| *k);
    let best = scores.iter().filter(|(_, me)| !*me).map(|(k, _)| *k).max().unwrap_or(0);
    (mine as u32, best as u32)
}

/// The end-of-match banner in free-for-all: VICTORY when you won, else who did, with the top two scores.
fn ffa_banner(winner: Option<u64>, me: u64, players: &[(u64, String, u16)]) -> String {
    let kills = |id: u64| players.iter().find(|p| p.0 == id).map_or(0, |p| p.2);
    let mine = kills(me);
    let best_other = players.iter().filter(|p| p.0 != me).map(|p| p.2).max().unwrap_or(0);
    match winner {
        Some(w) if w == me => format!("VICTORY  {mine} - {best_other}"),
        Some(w) => {
            let name = players.iter().find(|p| p.0 == w).map_or("A PLAYER".into(), |p| p.1.to_uppercase());
            format!("{name} WINS  {} - {mine}", kills(w))
        }
        None => format!("DRAW  {mine} - {best_other}"),
    }
}

#[allow(clippy::type_complexity)]
fn update_score(
    matches: Query<&MatchState>,
    me: Query<&PlayerInfo, With<Controlled>>,
    scores: Query<(&Score, Has<Controlled>), With<PlayerId>>,
    mut ally: Query<&mut Text, (With<ScoreAlly>, Without<ScoreEnemy>, Without<MatchClock>, Without<MatchSub>)>,
    mut enemy: Query<&mut Text, (With<ScoreEnemy>, Without<ScoreAlly>, Without<MatchClock>, Without<MatchSub>)>,
    mut clock: Query<&mut Text, (With<MatchClock>, Without<ScoreAlly>, Without<ScoreEnemy>, Without<MatchSub>)>,
    mut sub: Query<&mut Text, (With<MatchSub>, Without<ScoreAlly>, Without<ScoreEnemy>, Without<MatchClock>)>,
    mut boxes: Query<(&ScoreBox, &mut Node, &mut BackgroundColor), Without<ScoreRoot>>,
    mut root: Query<&mut Node, (With<ScoreRoot>, Without<ScoreBox>)>,
    settings: Res<Settings>,
) {
    let Some(m) = matches.iter().next() else { return };
    // Scores are relative: your team on the left in the ally colour.
    let mine = me.iter().next().and_then(|i| i.team);
    let (a, b) = if m.mode == MatchMode::Ffa {
        ffa_scores(&scores.iter().map(|(s, me)| (s.kills, me)).collect::<Vec<_>>())
    } else if mine == Some(Team::B) {
        (m.score_b, m.score_a)
    } else {
        (m.score_a, m.score_b)
    };
    for mut t in &mut ally {
        t.0 = a.to_string();
    }
    for mut t in &mut enemy {
        t.0 = b.to_string();
    }
    let (teams, title, subline) = score_header(m.mode, m.time_left_s, m.score_limit);
    let show = |on: bool| if on { Display::Flex } else { Display::None };
    for mut node in &mut root {
        node.display = Display::Flex;
    }
    let (ally_color, enemy_color) = settings.team_colors();
    for (b, mut node, mut bg) in &mut boxes {
        node.display = show(teams);
        let c = if b.enemy { enemy_color } else { ally_color }.with_alpha(0.92);
        if bg.0 != c {
            bg.0 = c;
        }
    }
    for mut t in &mut clock {
        t.0.clone_from(&title);
    }
    for mut t in &mut sub {
        t.0.clone_from(&subline);
    }
}

/// Px at 1080p that a spread angle opens the crosshair by, for a camera's vertical field of view (radians):
/// the UI is laid out at 1080p and scaled to the window, so project with the reference height.
fn spread_px(spread_deg: f32, vfov: f32) -> f32 {
    let focal = kit::REF_HEIGHT * 0.5 / (vfov * 0.5).tan();
    spread_deg.max(0.0).to_radians().tan() * focal
}

/// The crosshair from MOUSE & AIM (colour, outline, lines, dot), opened by the gun's live random spread (standing
/// still there is none, so every gun at rest shows the plain small cross, and it opens by the real cone on the
/// move). Hit markers are not drawn on it: they show on the player hit (`render::hit_fx`, which follows HIT MARKERS).
#[allow(clippy::type_complexity)]
fn update_crosshair(
    me: Query<(&PlayerWeapon, &PlayerLoadout, &PlayerMove, &Vitals), With<Controlled>>,
    camera: Query<&Projection, With<ViewCamera>>,
    data: Res<Data>,
    settings: Res<Settings>,
    mut parts: Query<(&CrosshairPart, &mut Node, &mut BackgroundColor, &mut Outline, &mut Visibility)>,
) {
    let Some((w, lo, mv, v)) = me.iter().next() else { return };
    let spec = lo.0.weapon.spec(&data);
    let env = vetf_sim::player::weapon_env(&data, &mv.0, &v.wounds);
    let spread = w.0.spread_deg(&data, spec, &lo.0.weapon, &env);
    let vfov = match camera.iter().next() {
        Some(Projection::Perspective(p)) => p.fov,
        _ => FALLBACK_VFOV_DEG.to_radians(),
    };
    let c = &settings.crosshair;
    let rects = crosshair_rects(c, spread_px(spread, vfov));
    let color = rgb_color(settings.crosshair_rgb());
    let outline = if c.outline { CROSSHAIR_OUTLINE } else { Color::NONE };
    let hide = w.0.ads > 0.7 || v.health.dead;
    for (part, mut node, mut bg, mut line, mut vis) in &mut parts {
        let Some(&(x, y, width, height)) = rects.get(part.0).filter(|_| !hide) else {
            vis.set_if_neq(Visibility::Hidden);
            continue;
        };
        vis.set_if_neq(Visibility::Inherited);
        let place = (px(x), px(y), px(width), px(height));
        if (node.left, node.top, node.width, node.height) != place {
            (node.left, node.top, node.width, node.height) = place;
        }
        if bg.0 != color {
            bg.0 = color;
        }
        if line.color != outline {
            line.color = outline;
        }
    }
}

/// The HUD canvas in percent of the screen before it is scaled about the screen centre, and the safe-area
/// inset in canvas px. Scaled by `scale`, it covers the screen (or the centred 16:9 part of an ultrawide one)
/// exactly, with the corner groups `safe_area` px at 1080p from its edges.
#[derive(Debug, Clone, Copy, PartialEq)]
struct HudFit {
    scale: f32,
    width: f32,
    height: f32,
    left: f32,
    top: f32,
    inset: f32,
}

/// [`HudFit`] for HUD SCALE `scale` (1 = 100 %) on a window `aspect` (width / height) wide; `centre_16_9` keeps
/// an ultrawide HUD 16:9 wide.
fn hud_fit(scale: f32, aspect: f32, centre_16_9: bool, safe_area: f32) -> HudFit {
    let s = scale.max(0.1);
    let wide = if centre_16_9 && aspect > 0.0 { (16.0 / 9.0 / aspect).min(1.0) } else { 1.0 };
    let (width, height) = (100.0 * wide / s, 100.0 / s);
    let (left, top) = ((100.0 - width) / 2.0, (100.0 - height) / 2.0);
    HudFit { scale: s, width, height, left, top, inset: safe_area.max(0.0) / s }
}

/// HUD SCALE, SAFE AREA MARGIN and ULTRAWIDE HUD WIDTH, live (also while Settings is open over the match).
fn fit_hud(
    settings: Res<Settings>,
    windows: Query<&Window, With<PrimaryWindow>>,
    mut canvas: Query<(&mut Node, &mut UiTransform), With<HudRoot>>,
    mut safe: Query<&mut Node, (With<HudSafeArea>, Without<HudRoot>)>,
) {
    let aspect = windows.iter().next().map_or(16.0 / 9.0, |w| w.width() / w.height().max(1.0));
    let h = &settings.hud;
    let fit = hud_fit(h.scale / 100.0, aspect, h.ultrawide == Ultrawide::Centre, h.safe_area);
    for (mut node, mut t) in &mut canvas {
        let want = (percent(fit.left), percent(fit.top), percent(fit.width), percent(fit.height));
        if (node.left, node.top, node.width, node.height) != want {
            (node.left, node.top, node.width, node.height) = want;
        }
        let scale = Vec2::splat(fit.scale);
        if t.scale != scale {
            t.scale = scale;
        }
    }
    let inset = px(fit.inset);
    for mut node in &mut safe {
        if (node.left, node.right, node.top, node.bottom) != (inset, inset, inset, inset) {
            (node.left, node.right, node.top, node.bottom) = (inset, inset, inset, inset);
        }
    }
}

/// The edge flash's alpha `since` seconds after a hit, for DAMAGE FLASH and REDUCE FLASHING (which caps it).
fn flash_alpha(setting: DamageFlash, reduce: bool, since: f32) -> f32 {
    let peak = match setting {
        DamageFlash::Off => 0.0,
        DamageFlash::Soft => FLASH_SOFT,
        DamageFlash::Full => FLASH_FULL,
    };
    let peak = if reduce { peak.min(FLASH_REDUCED) } else { peak };
    if since >= FLASH_S { 0.0 } else { peak * (1.0 - since.max(0.0) / FLASH_S) }
}

/// Red from the screen edges in, at `alpha`.
fn edge_gradient(alpha: f32) -> BackgroundGradient {
    let red = kit::HP_CRIT;
    BackgroundGradient::from(RadialGradient::new(
        UiPosition::CENTER,
        RadialGradientShape::ClosestCorner,
        vec![ColorStop::new(red.with_alpha(0.0), percent(70)), ColorStop::new(red.with_alpha(alpha), percent(100))],
    ))
}

/// Seconds since the last hit, and the freshest damage entry seen (each counts down from when it arrived, so
/// a fresher one is a new hit).
struct FlashClock {
    since: f32,
    freshest: f32,
}

impl Default for FlashClock {
    fn default() -> Self {
        FlashClock { since: FLASH_S, freshest: 0.0 }
    }
}

fn update_damage_flash(
    feedback: Res<Feedback>,
    settings: Res<Settings>,
    time: Res<Time>,
    mut clock: Local<FlashClock>,
    mut shown: Local<f32>,
    mut edge: Query<(&mut BackgroundGradient, &mut Visibility), With<DamageFlashEdge>>,
) {
    let freshest = feedback.damage.iter().map(|d| d.1).fold(0.0, f32::max);
    clock.since = if freshest > clock.freshest + 1e-4 { 0.0 } else { clock.since + time.delta_secs() };
    clock.freshest = freshest;
    let alpha = flash_alpha(settings.hud.damage_flash, settings.hud.reduce_flashing, clock.since);
    if (alpha - *shown).abs() < 0.004 && (alpha > 0.0) == (*shown > 0.0) {
        return;
    }
    *shown = alpha;
    for (mut gradient, mut vis) in &mut edge {
        vis.set_if_neq(if alpha > 0.0 { Visibility::Inherited } else { Visibility::Hidden });
        if alpha > 0.0 {
            *gradient = edge_gradient(alpha);
        }
    }
}

/// `--demo-ui hud-fx`: keep a stream of hits from the right and a kill feed on screen (you in the ally colour, the
/// rest as enemies), for screenshots of the crosshair, team colours and flash (`--demo-ui hit-fx` shows the hit
/// markers, on the nearest other player).
fn demo_hud_fx(
    cli: Res<Cli>,
    time: Res<Time>,
    me: Query<(&PlayerInfo, &PlayerMove), With<Controlled>>,
    mut feedback: ResMut<Feedback>,
    mut since: Local<Option<f32>>,
) {
    if cli.demo_ui.as_deref() != Some("hud-fx") {
        return;
    }
    let Some((info, mv)) = me.iter().next() else { return };
    let t = time.elapsed_secs();
    if t - *since.get_or_insert(t) < 1.0 {
        return;
    }
    if feedback.damage.iter().all(|d| d.1 < 1.0) {
        feedback.damage.push((mv.0.pos + Vec3::new(8.0, 0.0, 0.0), 1.2));
    }
    if feedback.kills.is_empty() {
        let you = info.name.as_str();
        for (killer, victim) in [("WREN", "ORCA"), ("VESPER", "MOTH"), (you, "VESPER"), ("ORCA", "LARK"), (you, "WREN")]
        {
            feedback.kills.push(FeedEntry::kill(killer, victim, killer == "ORCA"));
        }
        // An assist line and a fall right after a fight.
        let mut helped = FeedEntry::kill("WREN", "LARK", false);
        helped.helpers = vec![you.into(), "ORCA".into()];
        let mut fall = FeedEntry::kill("", "MOTH", false);
        (fall.killer, fall.helpers, fall.cause) = (None, vec!["VESPER".into()], DeathCause::Fall);
        feedback.kills.extend([helped, fall]);
        feedback.assist_s = ASSIST_POPUP_S;
        // Kill streak lines, the map-wide banner and the reward toast.
        let mut run = FeedEntry::kill("ORCA", "", false);
        run.streak = Some(StreakLine::Reached { kills: 5, announced: true });
        let mut ended = FeedEntry::kill(you, "ORCA", false);
        ended.streak = Some(StreakLine::Ended { kills: 5 });
        feedback.kills.extend([run, ended]);
        let headline = "ORCA IS ON A 5 STREAK".into();
        feedback.streak_banner = Some(crate::streaks::Banner { caption: "BOUNTY".into(), headline, left_s: 30.0 });
        let text = "3 STREAK: FULL HEALTH + FULL SHIELD".into();
        feedback.streak_toast = Some(crate::streaks::Toast { text, left_s: 30.0 });
    }
}

/// A kill feed line's texts, left to right: the lead name, the helper part and the cause, the middle word,
/// the victim and the tag. Empty parts take no room.
/// - a kill: "KILLER", "+ HELPER +N" (the top helper by damage, and how many more), "" (or "+ BLEED"), ">",
///   "VICTIM", "HEADSHOT" (or "")
/// - a death no player caused, after a fight: "HELPER", "+N", "+ FALL" (the top helper leads)
/// - with nobody to credit: "FALL" (or "--" for a suicide), "", ""
/// - a kill streak ([`StreakLine`]): "WREN:" "3 STREAK", "WREN" "is on a" "5 STREAK", "ORCA" "ended" "WREN's"
///   "5 STREAK"
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FeedText {
    pub lead: String,
    /// The player the lead names (its colour), if any.
    pub lead_name: Option<String>,
    pub helper: String,
    /// The player the helper part names (its colour), if any.
    pub helper_name: Option<String>,
    pub cause: String,
    /// ">" for a kill, a word for a streak line ("is on a", "ended").
    pub mid: String,
    pub victim: String,
    /// The player the victim part names (its colour), if any.
    pub victim_name: Option<String>,
    pub tag: String,
    /// The tag is a streak ("5 STREAK", in the streak colour) rather than HEADSHOT.
    pub tag_streak: bool,
}

impl FeedText {
    /// The whole line, as a player reads it: "KILLER + HELPER +1 > VICTIM".
    pub fn line(&self) -> String {
        let parts = [&self.lead, &self.helper, &self.cause, &self.mid, &self.victim, &self.tag];
        parts.into_iter().map(String::as_str).filter(|s| !s.is_empty()).collect::<Vec<_>>().join(" ")
    }

    fn plain(lead: String, lead_name: Option<String>) -> FeedText {
        FeedText {
            lead,
            lead_name,
            helper: String::new(),
            helper_name: None,
            cause: String::new(),
            mid: String::new(),
            victim: String::new(),
            victim_name: None,
            tag: String::new(),
            tag_streak: false,
        }
    }
}

pub fn feed_text(e: &FeedEntry) -> FeedText {
    if let Some(s) = e.streak {
        return streak_text(e, s);
    }
    let more = |n: usize| if n > 0 { format!("+{n}") } else { String::new() };
    let cause = if e.cause.is_environmental() { e.cause.label() } else { "" };
    let plus_cause = if cause.is_empty() { String::new() } else { format!("+ {cause}") };
    let mut t = match (&e.killer, e.helpers.split_first()) {
        (Some(k), top) => FeedText {
            helper: top.map_or(String::new(), |(h, rest)| match rest.len() {
                0 => format!("+ {h}"),
                n => format!("+ {h} +{n}"),
            }),
            helper_name: top.map(|(h, _)| h.clone()),
            cause: plus_cause,
            ..FeedText::plain(k.clone(), Some(k.clone()))
        },
        (None, Some((h, rest))) => {
            FeedText { helper: more(rest.len()), cause: plus_cause, ..FeedText::plain(h.clone(), Some(h.clone())) }
        }
        (None, None) => FeedText::plain(if cause.is_empty() { "--".into() } else { cause.into() }, None),
    };
    t.mid = ">".into();
    t.victim = e.victim.clone();
    t.victim_name = Some(e.victim.clone());
    if e.headshot {
        t.tag = "HEADSHOT".into();
    }
    t
}

/// A kill streak line: "WREN: 3 STREAK", "WREN is on a 5 STREAK", "ORCA ended WREN's 5 STREAK" (with no
/// player to name, the cause: "FALL ended WREN's 5 STREAK", else "WREN's 5 STREAK ended").
fn streak_text(e: &FeedEntry, s: StreakLine) -> FeedText {
    let who = e.killer.clone().unwrap_or_default();
    let mut t = match s {
        StreakLine::Reached { kills, announced: false } => {
            FeedText { tag: format!("{kills} STREAK"), ..FeedText::plain(format!("{who}:"), Some(who)) }
        }
        StreakLine::Reached { kills, announced: true } => FeedText {
            mid: "is on a".into(),
            tag: format!("{kills} STREAK"),
            ..FeedText::plain(who.clone(), Some(who))
        },
        StreakLine::Ended { kills } => {
            let cause = e.cause.is_environmental().then_some(e.cause.label());
            let (lead, lead_name, mid, tag) = match (&e.killer, cause) {
                (Some(k), _) => (k.clone(), Some(k.clone()), "ended", format!("{kills} STREAK")),
                (None, Some(c)) => (c.to_string(), None, "ended", format!("{kills} STREAK")),
                (None, None) => (String::new(), None, "", format!("{kills} STREAK ended")),
            };
            FeedText {
                mid: mid.into(),
                victim: format!("{}'s", e.victim),
                victim_name: Some(e.victim.clone()),
                tag,
                ..FeedText::plain(lead, lead_name)
            }
        }
    };
    t.tag_streak = true;
    t
}

/// The ASSIST popup: on for a moment after an assist of yours, fading out over its last third.
fn update_assist_popup(
    feedback: Res<Feedback>,
    mut popup: Query<(&mut Visibility, &mut TextColor), With<AssistPopup>>,
) {
    let t = feedback.assist_s;
    for (mut vis, mut color) in &mut popup {
        *vis = if t > 0.0 { Visibility::Inherited } else { Visibility::Hidden };
        color.0 = kit::TEXT_HI.with_alpha(assist_popup_alpha(t));
    }
}

/// The kill streak HUD: the counter left of the vitals (team deathmatch and free-for-all; shown from
/// `streaks.hud_min`), the map-wide banner and your reward toast, each fading out over its last moments.
#[allow(clippy::type_complexity)]
fn update_streak_hud(
    data: Res<Data>,
    feedback: Res<Feedback>,
    me: Query<&Score, With<Controlled>>,
    matches: Query<&MatchState>,
    mut counter: Query<(&mut Node, &mut Visibility), With<StreakCounter>>,
    mut count: Query<&mut Text, (With<StreakCount>, Without<StreakBannerCaption>, Without<StreakBannerHeadline>)>,
    mut banner: Query<&mut Visibility, (With<StreakBannerRoot>, Without<StreakCounter>, Without<StreakToastText>)>,
    mut lines: Query<
        (&mut Text, &mut TextColor, Has<StreakBannerCaption>),
        (Or<(With<StreakBannerCaption>, With<StreakBannerHeadline>)>, Without<StreakCount>),
    >,
    mut toast: Query<
        (&mut Text, &mut TextColor, &mut Visibility),
        (
            With<StreakToastText>,
            Without<StreakCount>,
            Without<StreakBannerCaption>,
            Without<StreakBannerHeadline>,
            Without<StreakCounter>,
            Without<StreakBannerRoot>,
        ),
    >,
) {
    let rules = &data.rules.streaks;
    let deathmatch = matches.iter().next().is_some_and(|m| m.mode.is_deathmatch());
    let streak = me.iter().next().map_or(0, |s| s.streak);
    for (mut node, mut vis) in &mut counter {
        node.display = if deathmatch { Display::Flex } else { Display::None };
        vis.set_if_neq(if rules.shows_counter(streak) { Visibility::Inherited } else { Visibility::Hidden });
    }
    for mut t in &mut count {
        let text = streak.to_string();
        if t.0 != text {
            t.0 = text;
        }
    }
    let b = feedback.streak_banner.as_ref();
    for mut vis in &mut banner {
        vis.set_if_neq(if b.is_some() { Visibility::Inherited } else { Visibility::Hidden });
    }
    if let Some(b) = b {
        let alpha = fade_out(b.left_s);
        for (mut t, mut c, caption) in &mut lines {
            let (text, col) = if caption { (&b.caption, STREAK_GOLD) } else { (&b.headline, kit::TEXT_HI) };
            if &t.0 != text {
                t.0 = text.clone();
            }
            c.0 = col.with_alpha(alpha);
        }
    }
    for (mut t, mut c, mut vis) in &mut toast {
        match &feedback.streak_toast {
            Some(toast) => {
                if t.0 != toast.text {
                    t.0 = toast.text.clone();
                }
                c.0 = STREAK_GOLD.with_alpha(fade_out(toast.left_s));
                vis.set_if_neq(Visibility::Inherited);
            }
            None => {
                vis.set_if_neq(Visibility::Hidden);
            }
        }
    }
}

/// A banner's or toast's opacity with `left_s` seconds to go: full, then fading out over its last half second.
pub fn fade_out(left_s: f32) -> f32 {
    (left_s / 0.5).clamp(0.0, 1.0)
}

/// The popup's opacity with `left_s` seconds to go: full, then fading out over the last third.
pub fn assist_popup_alpha(left_s: f32) -> f32 {
    (left_s / (ASSIST_POPUP_S / 3.0)).clamp(0.0, 1.0)
}

#[allow(clippy::type_complexity)]
fn update_feed(
    feedback: Res<Feedback>,
    me: Query<&PlayerInfo, With<Controlled>>,
    players: Query<&PlayerInfo>,
    mut rows: Query<(&FeedRow, &mut Node), Without<FeedPart>>,
    mut parts: Query<(&FeedPart, &mut Text, &mut TextColor, &mut Node), Without<FeedRow>>,
    settings: Res<Settings>,
) {
    let mine = me.iter().next().map(|i| (i.name.clone(), i.team));
    let (ally, enemy) = settings.team_colors();
    // Ally is you and your team; in free-for-all modes everyone else is an enemy.
    let color = |name: &str| {
        let Some((my_name, my_team)) = &mine else { return kit::TEXT };
        let team = players.iter().find(|p| p.name == name).and_then(|p| p.team);
        if name == my_name || (my_team.is_some() && team == *my_team) { ally } else { enemy }
    };
    let lines = settings.hud.kill_feed.lines().min(FEED_ROWS);
    let entries: Vec<_> = feedback.kills.iter().rev().take(lines).collect();
    for (row, mut node) in &mut rows {
        node.display = if row.0 < entries.len() { Display::Flex } else { Display::None };
    }
    let texts: Vec<FeedText> = entries.iter().map(|e| feed_text(e)).collect();
    for (part, mut t, mut c, mut node) in &mut parts {
        let (Some(e), Some(ft)) = (entries.get(part.0), texts.get(part.0)) else { continue };
        let named = |name: &Option<String>| name.as_deref().map_or(kit::TEXT_MID, color);
        let (text, col) = match part.1 {
            Part::Lead => (ft.lead.clone(), named(&ft.lead_name)),
            Part::Helper => (ft.helper.clone(), named(&ft.helper_name)),
            Part::Cause => (ft.cause.clone(), kit::TEXT_MID),
            // A kill's ">" is quiet; a streak line's words ("is on a", "ended") read a little brighter.
            Part::Mid => (ft.mid.clone(), if e.streak.is_some() { kit::TEXT_MID } else { kit::TEXT_LOW }),
            Part::Victim => (ft.victim.clone(), named(&ft.victim_name)),
            Part::Tag => (ft.tag.clone(), if ft.tag_streak { STREAK_GOLD } else { kit::WARN }),
        };
        // An empty part takes no room (the row's gap would leave a hole).
        let display = if text.is_empty() { Display::None } else { Display::Flex };
        if node.display != display {
            node.display = display;
        }
        if t.0 != text {
            t.0 = text;
        }
        c.0 = col;
    }
}

fn update_overlays(
    me: Query<(&Vitals, &PlayerInfo, &PlayerId), With<Controlled>>,
    players: Query<(&PlayerId, &PlayerInfo, &Score)>,
    matches: Query<&MatchState>,
    banner: Query<&Children, With<CenterBanner>>,
    mut texts: Query<&mut Text>,
) {
    let Some((v, info, my_id)) = me.iter().next() else { return };
    let m = matches.iter().next();
    let mut msg = String::new();
    if let Some(MatchPhase::Ended { player, .. }) = m.filter(|m| m.mode == MatchMode::Ffa).map(|m| m.phase) {
        let all: Vec<(u64, String, u16)> = players.iter().map(|(id, i, s)| (id.0, i.name.clone(), s.kills)).collect();
        msg = ffa_banner(player, my_id.0, &all);
    } else if let Some(MatchPhase::Ended { winner, .. }) = m.map(|m| m.phase) {
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
}

/// The direction of recent damage, in the enemy colour. The chevrons always show: they are information, not
/// a flash (DAMAGE FLASH drives the edge flash).
fn update_damage_indicators(
    feedback: Res<Feedback>,
    settings: Res<Settings>,
    camera: Query<&GlobalTransform, With<ViewCamera>>,
    mut chevrons: Query<(&DamageChevron, &mut Node, &mut BackgroundColor, &mut Visibility)>,
) {
    let Some(cam) = camera.iter().next() else { return };
    let fwd = cam.forward().with_y(0.0).normalize_or_zero();
    let right = cam.right().with_y(0.0).normalize_or_zero();
    let tint = settings.team_colors().1.with_alpha(0.85);
    for (c, mut node, mut bg, mut vis) in &mut chevrons {
        match feedback.damage.get(c.0) {
            Some((from, _)) => {
                let d = (*from - cam.translation()).with_y(0.0).normalize_or_zero();
                let (x, y) = (d.dot(right), -d.dot(fwd));
                let r = 130.0;
                node.margin = UiRect { left: px(x * r * 2.0), top: px(y * r * 2.0), ..default() };
                if bg.0 != tint {
                    bg.0 = tint;
                }
                *vis = Visibility::Inherited;
            }
            None => *vis = Visibility::Hidden,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entry(killer: Option<&str>, helpers: &[&str], cause: DeathCause) -> FeedEntry {
        FeedEntry {
            killer: killer.map(Into::into),
            helpers: helpers.iter().map(|h| h.to_string()).collect(),
            cause,
            victim: "MOTH".into(),
            headshot: false,
            left_s: 1.0,
            streak: None,
        }
    }

    fn line(killer: Option<&str>, helpers: &[&str], cause: DeathCause) -> String {
        feed_text(&entry(killer, helpers, cause)).line()
    }

    /// The kill feed: "KILLER + HELPER > VICTIM", with several helpers the top one (most damage) and "+N".
    #[test]
    fn the_feed_line_names_the_killer_and_the_top_helper() {
        assert_eq!(line(Some("WREN"), &[], DeathCause::Shot), "WREN > MOTH");
        assert_eq!(line(Some("WREN"), &["ORCA"], DeathCause::Shot), "WREN + ORCA > MOTH");
        assert_eq!(line(Some("WREN"), &["ORCA", "LARK", "VESPER"], DeathCause::Shot), "WREN + ORCA +2 > MOTH");
        let t = feed_text(&entry(Some("WREN"), &["ORCA", "LARK"], DeathCause::Shot));
        assert_eq!((t.lead_name.as_deref(), t.helper_name.as_deref()), (Some("WREN"), Some("ORCA")), "each its colour");
        // Bled out: the last attacker kept the kill; the cause shows too.
        assert_eq!(line(Some("WREN"), &["ORCA"], DeathCause::Bleed), "WREN + ORCA + BLEED > MOTH");
    }

    /// A death no player caused, right after a fight: "HELPER + FALL > VICTIM"; with nobody to credit, the
    /// cause alone.
    #[test]
    fn environmental_deaths_name_the_helper_and_the_cause() {
        assert_eq!(line(None, &["ORCA"], DeathCause::Fall), "ORCA + FALL > MOTH");
        assert_eq!(line(None, &["ORCA", "LARK"], DeathCause::Fire), "ORCA +1 + FIRE > MOTH");
        assert_eq!(line(None, &["ORCA"], DeathCause::OutOfBounds), "ORCA + OUT OF BOUNDS > MOTH");
        assert_eq!(line(None, &[], DeathCause::Fall), "FALL > MOTH");
        assert_eq!(line(None, &[], DeathCause::Shot), "-- > MOTH", "a suicide, as before");
        let t = feed_text(&entry(None, &["ORCA", "LARK"], DeathCause::Fall));
        assert_eq!((t.lead_name.as_deref(), t.helper_name), (Some("ORCA"), None), "the top helper leads");
        assert_eq!(feed_text(&entry(None, &[], DeathCause::Fall)).lead_name, None, "a cause is no player");
    }

    /// The ASSIST popup: full for the first two thirds, then fading out; gone at zero.
    #[test]
    fn the_assist_popup_fades_out_at_the_end() {
        assert_eq!(assist_popup_alpha(ASSIST_POPUP_S), 1.0);
        assert_eq!(assist_popup_alpha(ASSIST_POPUP_S * 0.5), 1.0);
        let late = assist_popup_alpha(ASSIST_POPUP_S / 6.0);
        assert!((late - 0.5).abs() < 1e-4, "{late}");
        assert_eq!(assist_popup_alpha(0.0), 0.0);
        const { assert!(ASSIST_POPUP_S > 0.5 && ASSIST_POPUP_S < 2.0, "short, like a kill confirm") };
    }

    #[test]
    fn the_range_header_has_no_team_scores() {
        let (teams, title, sub) = score_header(MatchMode::Range, 0.0, 50);
        assert!(!teams, "the range has no teams");
        assert_eq!((title.as_str(), sub.as_str()), ("GUN RANGE", "FREE PRACTICE"));
        let (teams, title, sub) = score_header(MatchMode::Tdm, 125.4, 50);
        assert!(teams);
        assert_eq!((title.as_str(), sub.as_str()), ("02:05", "TDM  /  FIRST TO 50"));
        let (boxes, title, sub) = score_header(MatchMode::Ffa, 59.9, 25);
        assert!(boxes, "free-for-all shows your kills and the leader's");
        assert_eq!((title.as_str(), sub.as_str()), ("00:59", "FFA  /  FIRST TO 25"));
    }

    /// One halo for everyone (team deathmatch, free-for-all): the header names the weight class, not a core.
    #[test]
    fn the_vitals_header_names_the_core_only_where_cores_differ() {
        use vetf_sim::data::{Core, WeightClass};
        assert_eq!(halo_header(Some(Core::Mender), WeightClass::Medium, false), "MENDER CORE  /  MEDIUM");
        assert_eq!(halo_header(Some(Core::Mender), WeightClass::Medium, true), "HALO  /  MEDIUM");
        assert_eq!(halo_header(None, WeightClass::None, true), "NO HALO");
        let d = vetf_sim::GameData::embedded();
        assert!(d.rules.fixed_loadout(MatchMode::Tdm).is_some() && d.rules.fixed_loadout(MatchMode::Ffa).is_some());
        assert!(d.rules.fixed_loadout(MatchMode::Range).is_none(), "the range keeps its cores");
    }

    #[test]
    fn free_for_all_score_is_your_kills_against_the_leaders() {
        assert_eq!(ffa_scores(&[(3, true), (7, false), (5, false)]), (3, 7));
        assert_eq!(ffa_scores(&[(9, true), (7, false)]), (9, 7), "leading: the best of the rest");
        assert_eq!(ffa_scores(&[(2, true)]), (2, 0), "alone");
        assert_eq!(ffa_scores(&[]), (0, 0));
    }

    #[test]
    fn the_free_for_all_banner_names_the_winner() {
        let players = vec![(0, "ash".to_string(), 18), (5, "Lark".to_string(), 25), (7, "wren".to_string(), 3)];
        assert_eq!(ffa_banner(Some(5), 0, &players), "LARK WINS  25 - 18");
        assert_eq!(ffa_banner(Some(5), 5, &players), "VICTORY  25 - 18");
        assert_eq!(ffa_banner(None, 7, &players), "DRAW  3 - 25");
    }

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

    #[test]
    fn the_crosshair_opens_with_spread() {
        let vfov = 78f32.to_radians();
        assert_eq!(spread_px(0.0, vfov), 0.0);
        // Half the field of view reaches the top of the 1080p canvas.
        assert!((spread_px(39.0, vfov) - 540.0).abs() < 0.01);
        assert!(spread_px(1.0, vfov) > spread_px(0.5, vfov));
        assert!(spread_px(1.0, 60f32.to_radians()) > spread_px(1.0, vfov), "a narrower view opens it more");
    }

    #[test]
    fn the_hud_canvas_scales_about_the_centre_and_keeps_the_margin() {
        let at = |f: HudFit| (f.left, f.top, f.width, f.height, f.inset);
        let same = |a: (f32, f32, f32, f32, f32), b: (f32, f32, f32, f32, f32)| {
            [a.0 - b.0, a.1 - b.1, a.2 - b.2, a.3 - b.3, a.4 - b.4].iter().all(|d| d.abs() < 1e-3)
        };
        // 100 % on 16:9: the whole screen, the corner groups 32 px in.
        assert!(same(at(hud_fit(1.0, 16.0 / 9.0, true, 32.0)), (0.0, 0.0, 100.0, 100.0, 32.0)));
        // 120 %: a smaller canvas scaled up to the screen; the margin stays 32 px on screen.
        let f = hud_fit(1.2, 16.0 / 9.0, true, 32.0);
        assert!((f.width * f.scale - 100.0).abs() < 1e-3 && (f.left + f.width / 2.0 - 50.0).abs() < 1e-3);
        assert!((f.inset * f.scale - 32.0).abs() < 1e-3);
        // 21:9 keeps a centred 16:9 HUD, or the full width when asked.
        let f = hud_fit(1.0, 21.0 / 9.0, true, 0.0);
        assert!(same(at(f), (50.0 - 100.0 * 16.0 / 21.0 / 2.0, 0.0, 100.0 * 16.0 / 21.0, 100.0, 0.0)));
        assert!(same(at(hud_fit(1.0, 21.0 / 9.0, false, 0.0)), (0.0, 0.0, 100.0, 100.0, 0.0)));
        // 4:3 is narrower than 16:9 already.
        assert!(same(at(hud_fit(1.0, 4.0 / 3.0, true, 0.0)), (0.0, 0.0, 100.0, 100.0, 0.0)));
    }

    #[test]
    fn the_damage_flash_follows_the_comfort_settings() {
        assert_eq!(flash_alpha(DamageFlash::Off, false, 0.0), 0.0);
        assert_eq!(flash_alpha(DamageFlash::Soft, false, 0.0), FLASH_SOFT);
        assert_eq!(flash_alpha(DamageFlash::Full, false, 0.0), FLASH_FULL);
        assert!(flash_alpha(DamageFlash::Full, false, FLASH_S * 0.5) < FLASH_FULL, "it fades");
        assert_eq!(flash_alpha(DamageFlash::Full, false, FLASH_S), 0.0);
        assert_eq!(flash_alpha(DamageFlash::Full, true, 0.0), FLASH_REDUCED, "reduce flashing caps it");
        let soft = flash_alpha(DamageFlash::Soft, true, 0.0);
        assert!(soft <= FLASH_REDUCED && soft < flash_alpha(DamageFlash::Soft, false, 0.0), "SOFT is capped too");
    }

    #[test]
    fn the_feed_has_a_row_for_every_kill_feed_choice() {
        let most = crate::settings::KillFeed::ALL.iter().map(|k| k.lines()).max();
        assert_eq!(most, Some(FEED_ROWS));
    }
    /// MAG CHECK: the host's match setting in team deathmatch and free-for-all (whatever a player picked for the
    /// range), the player's own in the gun range; the estimate when nobody picked anything.
    #[test]
    fn mag_check_follows_the_match_in_deathmatch_and_the_player_in_the_range() {
        let d = vetf_sim::GameData::embedded();
        let m = |mode, mag_check| MatchState {
            mode,
            map: "showhome".into(),
            score_a: 0,
            score_b: 0,
            score_limit: 50,
            time_left_s: 600.0,
            phase: MatchPhase::Live,
            lobby_name: String::new(),
            max_players: 10,
            rules: d.rules.rulesets.get(mode),
            mag_check,
        };
        use MagCheckMode::{Estimate, Exact};
        let defaults = crate::settings::Settings::default().gameplay.range_mag_check.mode();
        assert_eq!(defaults, Estimate, "the range's default is the estimate");
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            assert_eq!(mag_check_mode(Some(&m(mode, Exact)), Estimate), Exact, "{mode:?}: the host's EXACT");
            assert_eq!(mag_check_mode(Some(&m(mode, Estimate)), Exact), Estimate, "{mode:?}: not the player's");
            assert_eq!(mag_check_mode(Some(&m(mode, MagCheckMode::default())), defaults), Estimate);
        }
        assert_eq!(mag_check_mode(Some(&m(MatchMode::Range, Estimate)), Exact), Exact, "the range: the player's");
        assert_eq!(mag_check_mode(Some(&m(MatchMode::Range, Exact)), Estimate), Estimate);
        assert_eq!(mag_check_mode(None, defaults), Estimate);
    }

    /// The counter exists only with EXACT; the card says the estimate, or with EXACT the rounds.
    #[test]
    fn the_counter_and_the_card_text_in_both_modes() {
        assert_eq!(ammo_counter_text(MagCheckMode::Estimate, 23, 30), None, "no counter with the estimate");
        assert_eq!(ammo_counter_text(MagCheckMode::Exact, 23, 30).as_deref(), Some("23 / 30"));
        assert_eq!(ammo_counter_text(MagCheckMode::Exact, 0, 60).as_deref(), Some("0 / 60"));
        let est = MagEstimate::from_rounds(23, 30);
        assert_eq!(mag_card_lines(MagCheckMode::Estimate, est, 23, 30), ("MORE THAN HALF".into(), ESTIMATE_NOTE));
        assert_eq!(mag_card_lines(MagCheckMode::Exact, est, 23, 30), ("23 / 30".into(), EXACT_NOTE));
        assert!(!mag_card_lines(MagCheckMode::Estimate, est, 23, 30).0.contains("23"), "no number in the estimate");
    }

    /// The HUD's round counter, as the system draws it: hidden with the estimate, `rounds / capacity` with EXACT
    /// (the match's in a deathmatch, the player's own setting in the range), hidden again while dead.
    #[test]
    fn the_round_counter_shows_only_with_exact() {
        use bevy::ecs::system::RunSystemOnce;
        let d = vetf_sim::GameData::embedded();
        let lo = vetf_sim::player::Loadout::default_for(&d, MatchMode::Tdm);
        let cap = lo.weapon.mag_capacity;
        let mut w = vetf_sim::weapon::WeaponState::new(&d, &lo.weapon);
        w.rounds[0] = cap - 7;
        let vitals = Vitals {
            health: vetf_sim::combat::Health::new(d.armor.zone_hp),
            halo: vetf_sim::combat::HaloState::full(&lo.halo),
            wounds: Default::default(),
            respawn_s: 0.0,
            protected_s: 0.0,
            awaiting_respawn: false,
        };
        let mut app = App::new();
        app.insert_resource(crate::settings::Settings::default());
        let me = app.world_mut().spawn((PlayerWeapon(w), PlayerLoadout(lo), vitals, Controlled)).id();
        let m = app
            .world_mut()
            .spawn(MatchState {
                mode: MatchMode::Tdm,
                map: "showhome".into(),
                score_a: 0,
                score_b: 0,
                score_limit: 50,
                time_left_s: 600.0,
                phase: MatchPhase::Live,
                lobby_name: String::new(),
                max_players: 10,
                rules: d.rules.rulesets.tdm,
                mag_check: MagCheckMode::default(),
            })
            .id();
        let root = app.world_mut().spawn((AmmoCounterRoot, Node { display: Display::None, ..default() })).id();
        let rounds = app.world_mut().spawn((AmmoCounterRounds, Text::new(""))).id();
        app.world_mut().spawn((AmmoCounterMag, Text::new("")));
        let shown = |app: &mut App| {
            app.world_mut().run_system_once(update_ammo_counter).unwrap();
            let on = app.world().get::<Node>(root).unwrap().display != Display::None;
            (on, app.world().get::<Text>(rounds).unwrap().0.clone())
        };
        assert!(!shown(&mut app).0, "the estimate (the default): no counter");
        app.world_mut().get_mut::<MatchState>(m).unwrap().mag_check = MagCheckMode::Exact;
        assert_eq!(shown(&mut app), (true, format!("{} / {cap}", cap - 7)), "the host's EXACT");
        app.world_mut().get_mut::<Vitals>(me).unwrap().health.dead = true;
        assert!(!shown(&mut app).0, "not while dead");
        app.world_mut().get_mut::<Vitals>(me).unwrap().health.dead = false;
        // The range ignores the match setting: the player's own decides.
        app.world_mut().get_mut::<MatchState>(m).unwrap().mode = MatchMode::Range;
        assert!(!shown(&mut app).0, "the range: the player's ESTIMATE");
        app.world_mut().resource_mut::<crate::settings::Settings>().gameplay.range_mag_check =
            crate::settings::RangeMagCheck::Exact;
        assert!(shown(&mut app).0, "the range: the player's EXACT");
    }
}
