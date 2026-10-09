//! The kill streak bounty aura (item 9c2): a player on a streak of `rules.ron` `streaks.aura_min` or more has a
//! few small warm-gold embers spiralling up around their body, from the feet to just over the halo, so everyone
//! can see who is on a run. It is a marker on the player, not a body outline: a teammate's ally glow
//! (`friend_foe`) is a rim drawn on the body, and the embers never tint the body at all, so the two read apart
//! (and a teammate on a streak shows both).
//!
//! Cheap by design: a handful of tiny unlit, additive spheres per streaker (one shared mesh and material, no
//! shadows), moved on the CPU. The look lives in `rules.ron` `streaks.aura`. The streak comes from the
//! replicated [`Score::streak`], so a player who joins mid-match sees the aura too. Our own body is never drawn
//! (first person), so the local player has no aura of their own; the HUD counter tells them instead.

use super::PlayerVisual;
use crate::AppState;
use crate::config::Data;
use bevy::light::NotShadowCaster;
use bevy::prelude::*;
use lightyear::prelude::*;
use std::f32::consts::{PI, TAU};
use vetf_net::*;
use vetf_sim::streak::AuraLook;

pub struct StreakAuraPlugin;

impl Plugin for StreakAuraPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<EmberAssets>().add_systems(
            Update,
            (place_auras, animate_embers)
                .chain()
                .after(super::update_player_visuals)
                .run_if(in_state(AppState::InGame)),
        );
    }
}

/// The aura's root, under a player's visual root (so it follows them and hides with them).
#[derive(Component)]
struct Aura;

/// One ember of an aura: its place in the loop.
#[derive(Component)]
struct Ember(u8);

/// The embers' shared mesh and material.
#[derive(Resource, Default)]
struct EmberAssets {
    mesh: Option<Handle<Mesh>>,
    material: Option<Handle<StandardMaterial>>,
}

/// Light the aura on a streak from its tier on, and put it out when the streak ends.
fn place_auras(
    mut commands: Commands,
    data: Res<Data>,
    players: Query<(Entity, &Score, Option<&Children>), (With<PlayerVisual>, Without<Controlled>)>,
    auras: Query<(), With<Aura>>,
    mut assets: ResMut<EmberAssets>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let rules = &data.rules.streaks;
    for (e, score, children) in &players {
        let lit = children.into_iter().flatten().copied().find(|c| auras.contains(*c));
        match (rules.has_aura(score.streak), lit) {
            (true, None) => {
                let look = &rules.aura;
                let mesh = assets
                    .mesh
                    .get_or_insert_with(|| meshes.add(Sphere::new(0.5).mesh().ico(1).expect("a small ico sphere")))
                    .clone();
                let material = assets.material.get_or_insert_with(|| materials.add(ember_material(look))).clone();
                commands.entity(e).with_children(|p| {
                    p.spawn((Aura, Transform::default(), Visibility::default())).with_children(|a| {
                        for i in 0..look.embers {
                            a.spawn((
                                Ember(i),
                                Mesh3d(mesh.clone()),
                                MeshMaterial3d(material.clone()),
                                Transform::from_scale(Vec3::ZERO),
                                NotShadowCaster,
                            ));
                        }
                    });
                });
            }
            (false, Some(aura)) => commands.entity(aura).despawn(),
            _ => {}
        }
    }
}

/// Unlit and additive: a small hot point of light that never darkens what is behind it.
fn ember_material(look: &AuraLook) -> StandardMaterial {
    let [r, g, b] = look.color;
    let color = Color::srgb(r, g, b);
    StandardMaterial {
        base_color: color,
        emissive: color.to_linear() * look.glow,
        unlit: true,
        alpha_mode: AlphaMode::Add,
        ..default()
    }
}

fn animate_embers(time: Res<Time>, data: Res<Data>, mut embers: Query<(&Ember, &mut Transform)>) {
    let look = &data.rules.streaks.aura;
    let t = time.elapsed_secs();
    for (ember, mut tf) in &mut embers {
        *tf = ember_at(look, ember.0, t);
    }
}

/// Where ember `i` is at `t` seconds (player space, feet at the origin): each rises from the feet to
/// `height_m` in `rise_s`, turning `swirl_turns` around the body and drawing in a little as it climbs, then
/// starts again; the embers are spread evenly through the loop. It swells in and shrinks away to nothing at
/// both ends, so the loop never pops.
pub fn ember_at(look: &AuraLook, i: u8, t: f32) -> Transform {
    let n = look.embers.max(1) as f32;
    let phase = (t / look.rise_s + i as f32 / n).fract();
    // The golden angle spreads the embers around the body without a pattern.
    let angle = i as f32 * 2.399_963 + phase * look.swirl_turns * TAU;
    let r = look.radius_m * (1.0 - 0.3 * phase);
    let size = look.size_m * (phase * PI).sin();
    Transform::from_xyz(angle.cos() * r, phase * look.height_m, angle.sin() * r).with_scale(Vec3::splat(size))
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::GameData;

    fn look() -> AuraLook {
        GameData::embedded().rules.streaks.aura
    }

    /// The embers stay around the body: within the radius of its axis, from the feet to the top of the loop,
    /// never bigger than their size.
    #[test]
    fn embers_rise_around_the_body() {
        let l = look();
        for i in 0..l.embers {
            for k in 0..200 {
                let tf = ember_at(&l, i, k as f32 * 0.037);
                let p = tf.translation;
                assert!(p.xz().length() <= l.radius_m + 1e-4, "{p}");
                assert!(p.xz().length() >= l.radius_m * 0.7 - 1e-4, "never inside the body: {p}");
                assert!((0.0..=l.height_m).contains(&p.y), "{p}");
                assert!(tf.scale.x >= 0.0 && tf.scale.x <= l.size_m + 1e-6);
            }
        }
    }

    /// An ember climbs, then starts again at the feet, swelling in and shrinking away so the loop never pops.
    #[test]
    fn an_ember_loops_without_popping() {
        let l = look();
        let start = ember_at(&l, 0, 0.0);
        assert_eq!((start.translation.y, start.scale.x), (0.0, 0.0));
        let mid = ember_at(&l, 0, l.rise_s * 0.5);
        assert!((mid.translation.y - l.height_m * 0.5).abs() < 1e-3);
        assert!((mid.scale.x - l.size_m).abs() < 1e-4, "biggest halfway up");
        let near_top = ember_at(&l, 0, l.rise_s * 0.999);
        assert!(near_top.scale.x < l.size_m * 0.01, "gone before it wraps");
        // Spread through the loop: at any moment they are at different heights.
        let mut ys: Vec<f32> = (0..l.embers).map(|i| ember_at(&l, i, 0.3).translation.y).collect();
        ys.sort_by(f32::total_cmp);
        assert!(ys.windows(2).all(|w| w[1] - w[0] > 0.05), "{ys:?}");
    }

    /// It is subtle and cheap: a few small embers.
    #[test]
    fn the_aura_is_small_and_cheap() {
        let l = look();
        assert!((4..=16).contains(&l.embers), "a handful");
        assert!(l.size_m <= 0.08, "small points, no body outline");
    }

    /// The ember material is unlit and additive (a light, not a coat of paint on the body).
    #[test]
    fn embers_glow_additively() {
        let m = ember_material(&look());
        assert!(m.unlit);
        assert!(matches!(m.alpha_mode, AlphaMode::Add));
        assert!(m.emissive.red > 1.0, "bright enough to read at range");
    }
}
