//! A kill streak's bounty seen through walls (user direction 2026-10-09). In free-for-all (`rules.ron`
//! `streaks.bounty.reveal_modes`) a player on a streak of `bounty.min` or more is shown to everyone else
//! wherever they are, walls or not: by default a name marker with a small bounty icon above the head, like a
//! teammate's marker but in the bounty colour (`reveal: Name`); or a faint outline of the body (`Silhouette`).
//! The streaker never sees their own. It is a deliberate exception to "no enemy tells" (DIRECTION_LOG 17, see
//! game/DESIGN_DELTAS.md).
//!
//! The rule is [`StreakRules::reveal_for`](vetf_sim::streak::StreakRules::reveal_for); the look is
//! `friend_foe.ron` `bounty`. Like the teammate markers it is UI drawn over the 3D view, so no wall hides it.

use super::friend_foe::{FriendFoeData, sight_points};
use super::hit_fx::on_screen;
use super::{PlayerVisual, ViewCamera, vfov_of};
use crate::AppState;
use crate::config::Data;
use crate::screens::Screens;
use crate::ui_kit::{Face, UiFonts};
use bevy::prelude::*;
use bevy::window::PrimaryWindow;
use lightyear::prelude::*;
use serde::Deserialize;
use std::collections::HashMap;
use vetf_net::*;
use vetf_sim::streak::Reveal;

/// Just under the teammate markers (`friend_foe`), above the world.
const REVEAL_Z: i32 = -7;

pub struct BountyRevealPlugin;

impl Plugin for BountyRevealPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(AppState::InGame), spawn_reveal_layer).add_systems(
            Update,
            place_reveals
                .after(super::update_camera)
                .after(super::update_player_visuals)
                .run_if(in_state(AppState::InGame)),
        );
    }
}

/// `friend_foe.ron` `bounty`: how a bounty looks through walls.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct BountyLook {
    /// The bounty colour (sRGB 0..1).
    pub color: [f32; 3],
    pub above_head_m: f32,
    pub font_px: f32,
    /// The icon under the name: a ring this wide around a dot.
    pub icon_px: f32,
    pub icon_ring_px: f32,
    /// Full strength up to `near_m`, fading to `far_alpha` at `far_m` and staying there.
    pub near_m: f32,
    pub far_m: f32,
    pub far_alpha: f32,
    /// The silhouette's outline: the body's width, the line's width and its strength.
    pub body_width_m: f32,
    pub outline_px: f32,
    pub outline_alpha: f32,
}

impl BountyLook {
    fn color(&self) -> Color {
        Color::srgb(self.color[0], self.color[1], self.color[2])
    }
}

/// How strongly a bounty shows `distance_m` away: full up to `near_m`, fading to `far_alpha` at `far_m`, and
/// never less (a bounty is never hidden by distance either).
pub fn bounty_alpha(look: &BountyLook, distance_m: f32) -> f32 {
    let t = ((distance_m - look.near_m) / (look.far_m - look.near_m).max(1e-3)).clamp(0.0, 1.0);
    let t = t * t * (3.0 - 2.0 * t);
    1.0 + (look.far_alpha - 1.0) * t
}

/// The silhouette's box on screen (fractions of the screen, top-left origin: min and max corners) for a body
/// from `feet` up to `top`, `width_m` wide; `None` when it is behind the camera.
pub fn outline_box(cam: &Transform, vfov: f32, aspect: f32, feet: Vec3, top: Vec3, width_m: f32) -> Option<Rect> {
    let low = on_screen(cam, vfov, aspect, feet)?;
    let high = on_screen(cam, vfov, aspect, top)?;
    let mid = (feet + top) * 0.5;
    let dist = (cam.rotation.inverse() * (mid - cam.translation)).z.abs().max(0.05);
    // The body's half-width as a share of the screen's width at that distance.
    let half_w = width_m * 0.5 / (dist * (vfov * 0.5).tan() * aspect) * 0.5;
    let cx = (low.x + high.x) * 0.5;
    Some(Rect::new(cx - half_w, high.y.min(low.y), cx + half_w, high.y.max(low.y)))
}

#[derive(Component)]
struct RevealLayer;

/// One player's reveal: its root (under the layer), how it shows, and the parts to tint.
#[derive(Component)]
struct BountyReveal {
    player: Entity,
    kind: Reveal,
    text: Option<Entity>,
    tinted: Vec<Entity>,
}

fn spawn_reveal_layer(mut commands: Commands) {
    commands.spawn((
        RevealLayer,
        Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
        GlobalZIndex(REVEAL_Z),
        Visibility::Inherited,
        Pickable::IGNORE,
        DespawnOnExit(AppState::InGame),
    ));
}

/// Where a revealed player shows this frame.
#[derive(Debug, Clone, PartialEq)]
struct Shown {
    kind: Reveal,
    /// Name: the point above the head. Silhouette: the box's top-left corner.
    at: Vec2,
    /// Silhouette: the box's size (screen fractions).
    size: Vec2,
    alpha: f32,
    name: String,
}

/// Each bounty, seen by everyone else through walls (after the camera and the players have moved this frame).
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn place_reveals(
    mut commands: Commands,
    data: Res<Data>,
    ff: Res<FriendFoeData>,
    fonts: Res<UiFonts>,
    screens: Res<Screens>,
    matches: Query<&MatchState>,
    windows: Query<&Window, With<PrimaryWindow>>,
    camera: Query<(&Transform, &Projection), With<ViewCamera>>,
    players: Query<(Entity, &PlayerInfo, &PlayerMove, &Vitals, &Score), (With<PlayerVisual>, Without<Controlled>)>,
    mut layer: Query<(Entity, &mut Visibility), With<RevealLayer>>,
    mut reveals: Query<(Entity, &BountyReveal, &mut Node, &mut Visibility), Without<RevealLayer>>,
    mut texts: Query<(&mut Text, &mut TextColor, &mut TextShadow)>,
    mut tints: Query<(Option<&mut BorderColor>, Option<&mut BackgroundColor>), Without<BountyReveal>>,
) {
    let Some((layer, mut layer_vis)) = layer.iter_mut().next() else { return };
    // Hidden with the HUD while a hub screen is open over the match.
    layer_vis.set_if_neq(if screens.is_empty() { Visibility::Inherited } else { Visibility::Hidden });
    let look = &ff.bounty;
    let rules = &data.rules.streaks;
    let mode = matches.iter().next().map(|m| m.mode);
    let mut shown: HashMap<Entity, Shown> = HashMap::new();
    if let (Some(mode), Some((cam, projection))) = (mode, camera.iter().next()) {
        let aspect = windows.iter().next().map_or(16.0 / 9.0, |w| w.width() / w.height().max(1.0));
        let vfov = vfov_of(projection);
        // Everyone here is someone else (`Without<Controlled>`): the streaker never sees their own.
        for (e, info, mv, vitals, score) in &players {
            let Some(kind) = rules.reveal_for(mode, score.streak, false).filter(|_| !vitals.health.dead) else {
                continue;
            };
            let points = sight_points(mv.0.pos, mv.0.stance, &ff.marker.sight_heights_m);
            let top_y = points.iter().map(|p| p.y).fold(mv.0.pos.y, f32::max);
            let top = Vec3::new(mv.0.pos.x, top_y, mv.0.pos.z);
            let alpha = bounty_alpha(look, top.distance(cam.translation));
            let name = info.name.to_uppercase();
            let s = match kind {
                Reveal::Off => continue,
                Reveal::Name => {
                    let Some(at) = on_screen(cam, vfov, aspect, top + Vec3::Y * look.above_head_m) else { continue };
                    Shown { kind, at, size: Vec2::ZERO, alpha, name }
                }
                Reveal::Silhouette => {
                    let Some(r) = outline_box(cam, vfov, aspect, mv.0.pos, top, look.body_width_m) else { continue };
                    Shown { kind, at: r.min, size: r.size(), alpha: alpha * look.outline_alpha, name }
                }
            };
            let off = |v: f32| !(-0.2..=1.2).contains(&v);
            if off(s.at.x) || off(s.at.y) {
                continue;
            }
            shown.insert(e, s);
        }
    }

    let color = look.color();
    let mut have: HashMap<Entity, Entity> = HashMap::new();
    for (root, r, mut node, mut vis) in &mut reveals {
        let current = shown.get(&r.player).filter(|s| s.kind == r.kind);
        if players.get(r.player).is_err() || (shown.contains_key(&r.player) && current.is_none()) {
            // Gone, or shown another way now: built again below.
            commands.entity(root).despawn();
            continue;
        }
        have.insert(r.player, root);
        let Some(s) = current else {
            vis.set_if_neq(Visibility::Hidden);
            continue;
        };
        vis.set_if_neq(Visibility::Inherited);
        (node.left, node.top) = (percent(s.at.x * 100.0), percent(s.at.y * 100.0));
        if s.kind == Reveal::Silhouette {
            (node.width, node.height) = (percent(s.size.x * 100.0), percent(s.size.y * 100.0));
        }
        if let Some(Ok((mut text, mut c, mut shadow))) = r.text.map(|t| texts.get_mut(t)) {
            if text.0 != s.name {
                text.0 = s.name.clone();
            }
            c.0 = color.with_alpha(s.alpha);
            shadow.color = Color::BLACK.with_alpha(0.7 * s.alpha);
        }
        for part in &r.tinted {
            if let Ok((border, bg)) = tints.get_mut(*part) {
                if let Some(mut b) = border {
                    *b = BorderColor::all(color.with_alpha(s.alpha));
                }
                if let Some(mut b) = bg {
                    b.0 = color.with_alpha(s.alpha);
                }
            }
        }
    }
    for (player, s) in shown.iter().filter(|(p, _)| !have.contains_key(*p)) {
        spawn_reveal(&mut commands, &fonts, look, layer, *player, s);
    }
}

fn spawn_reveal(commands: &mut Commands, fonts: &UiFonts, look: &BountyLook, layer: Entity, player: Entity, s: &Shown) {
    let color = look.color().with_alpha(s.alpha);
    match s.kind {
        Reveal::Off => {}
        Reveal::Silhouette => {
            let root = commands
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: percent(s.at.x * 100.0),
                        top: percent(s.at.y * 100.0),
                        width: percent(s.size.x * 100.0),
                        height: percent(s.size.y * 100.0),
                        border: UiRect::all(px(look.outline_px)),
                        border_radius: BorderRadius::MAX,
                        ..default()
                    },
                    BorderColor::all(color),
                    Pickable::IGNORE,
                    ChildOf(layer),
                ))
                .id();
            commands.entity(root).insert(BountyReveal { player, kind: s.kind, text: None, tinted: vec![root] });
        }
        Reveal::Name => {
            let anchor = commands
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: percent(s.at.x * 100.0),
                        top: percent(s.at.y * 100.0),
                        width: px(0),
                        height: px(0),
                        ..default()
                    },
                    Pickable::IGNORE,
                    ChildOf(layer),
                ))
                .id();
            // The name and the bounty icon under it stand centred on the anchor, the icon's foot on it.
            let column = commands
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(-120),
                        width: px(240),
                        bottom: px(0),
                        flex_direction: FlexDirection::Column,
                        align_items: AlignItems::Center,
                        row_gap: px(2),
                        ..default()
                    },
                    Pickable::IGNORE,
                    ChildOf(anchor),
                ))
                .id();
            let text = commands
                .spawn((
                    fonts.text(s.name.clone(), Face::Display, 700, look.font_px, color, 0.06),
                    TextShadow { offset: Vec2::splat(1.0), color: Color::BLACK.with_alpha(0.7 * s.alpha) },
                    TextLayout::no_wrap(),
                    Pickable::IGNORE,
                    ChildOf(column),
                ))
                .id();
            // The bounty icon: a ring around a dot (a target), unlike a teammate's plain dot.
            let ring = commands
                .spawn((
                    Node {
                        width: px(look.icon_px),
                        height: px(look.icon_px),
                        border: UiRect::all(px(look.icon_ring_px)),
                        border_radius: BorderRadius::MAX,
                        justify_content: JustifyContent::Center,
                        align_items: AlignItems::Center,
                        ..default()
                    },
                    BorderColor::all(color),
                    Pickable::IGNORE,
                    ChildOf(column),
                ))
                .id();
            let dot_px = (look.icon_px - 4.0 * look.icon_ring_px).max(2.0);
            let dot = commands
                .spawn((
                    Node { width: px(dot_px), height: px(dot_px), border_radius: BorderRadius::MAX, ..default() },
                    BackgroundColor(color),
                    Pickable::IGNORE,
                    ChildOf(ring),
                ))
                .id();
            commands.entity(anchor).insert(BountyReveal {
                player,
                kind: s.kind,
                text: Some(text),
                tinted: vec![ring, dot],
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::GameData;

    fn look() -> BountyLook {
        FriendFoeData::embedded().bounty.clone()
    }

    /// The bounty colour is the streak gold, never the ally colour (it must not read as a teammate).
    #[test]
    fn the_bounty_is_in_its_own_colour() {
        let l = look();
        let gold = l.color();
        use crate::settings::TeamColours;
        for preset in [TeamColours::Default, TeamColours::Deutan, TeamColours::Protan, TeamColours::Tritan] {
            let ally = crate::settings::team_pair(preset).0;
            let d = gold.to_srgba().to_vec3() - ally.to_srgba().to_vec3();
            assert!(d.length() > 0.2, "{preset:?}: the bounty must not look like an ally");
        }
    }

    /// A bounty never fades away with distance: full up close, down to `far_alpha` far out, never less.
    #[test]
    fn a_bounty_shows_at_any_range() {
        let l = look();
        assert_eq!(bounty_alpha(&l, 0.0), 1.0);
        assert_eq!(bounty_alpha(&l, l.near_m), 1.0);
        assert!((bounty_alpha(&l, l.far_m) - l.far_alpha).abs() < 1e-5);
        assert!((bounty_alpha(&l, 10_000.0) - l.far_alpha).abs() < 1e-5);
        assert!(l.far_alpha > 0.2, "still readable far out");
        let mut last = 1.0;
        for d in 0..200 {
            let a = bounty_alpha(&l, d as f32);
            assert!(a <= last + 1e-6);
            last = a;
        }
    }

    /// The silhouette's box: a body straight ahead stands around the middle of the screen, from the head down to
    /// the feet, narrower than it is tall; nothing for a body behind the camera.
    #[test]
    fn the_silhouette_box_frames_the_body() {
        let cam = Transform::from_xyz(0.0, 1.6, 0.0);
        let vfov = 70f32.to_radians();
        let (feet, top) = (Vec3::new(0.0, 0.0, -10.0), Vec3::new(0.0, 1.75, -10.0));
        let r = outline_box(&cam, vfov, 16.0 / 9.0, feet, top, 0.7).unwrap();
        assert!((r.center().x - 0.5).abs() < 1e-4, "{r:?}");
        assert!(r.min.y < 0.5 && r.max.y > 0.5, "spans the eye line: {r:?}");
        assert!(r.width() > 0.0 && r.width() < r.height(), "{r:?}");
        let far = outline_box(&cam, vfov, 16.0 / 9.0, feet * 2.0, top.with_z(-20.0), 0.7).unwrap();
        assert!(far.height() < r.height() * 0.6, "smaller further away");
        let behind = outline_box(&cam, vfov, 16.0 / 9.0, -feet, top.with_z(10.0), 0.7);
        assert!(behind.is_none());
    }

    /// The default reveal is the name marker, in free-for-all only.
    #[test]
    fn the_shipped_reveal_is_a_name_in_free_for_all() {
        let r = GameData::embedded().rules.streaks;
        assert_eq!(r.reveal_for(MatchMode::Ffa, r.bounty.min, false), Some(Reveal::Name));
        assert_eq!(r.reveal_for(MatchMode::Tdm, r.bounty.min, false), None);
        assert_eq!(r.reveal_for(MatchMode::Ffa, r.bounty.min, true), None, "never your own");
    }
}
