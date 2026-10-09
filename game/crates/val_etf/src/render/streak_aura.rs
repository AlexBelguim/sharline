//! The kill streak bounty aura (item 9c2): a player on a streak of `rules.ron` `streaks.aura_min` or more has a
//! few small warm-gold embers spiralling up around their body, from the feet to just over the halo, so everyone
//! can see who is on a run. It is a marker on the player, not a body outline: a teammate's ally glow
//! (`friend_foe`) is a rim drawn on the body, and the embers never tint the body at all, so the two read apart
//! (and a teammate on a streak shows both).
//!
//! Cheap by design: a handful of tiny unlit, additive spheres per streaker (one shared mesh and material, no
//! shadows), moved on the CPU. The look lives in `rules.ron` `streaks.aura`. The streak comes from the
//! replicated [`Score::streak`], so a player who joins mid-match sees the aura too.
//!
//! Our own body is never drawn (first person), so the streaker sees a faint aura of their own instead (user
//! direction 2026-10-09): a few dim embers rising around the gun hand and lightly at the screen's left and right
//! edges, under the view camera and never within `own_aura.clear_deg` of the crosshair, so it never blocks aim.

use super::{PlayerVisual, ViewCamera, vfov_of};
use crate::AppState;
use crate::config::Data;
use bevy::light::NotShadowCaster;
use bevy::prelude::*;
use bevy::window::PrimaryWindow;
use lightyear::prelude::*;
use std::f32::consts::{PI, TAU};
use vetf_net::*;
use vetf_sim::streak::{AuraLook, OwnAuraLook, StreakRules};

pub struct StreakAuraPlugin;

impl Plugin for StreakAuraPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<EmberAssets>().add_systems(
            Update,
            (place_auras, animate_embers, place_own_aura, animate_own_embers)
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

/// The embers' shared mesh and materials (the aura others see, and our own fainter one).
#[derive(Resource, Default)]
struct EmberAssets {
    mesh: Option<Handle<Mesh>>,
    material: Option<Handle<StandardMaterial>>,
    own_material: Option<Handle<StandardMaterial>>,
}

impl EmberAssets {
    fn mesh(&mut self, meshes: &mut Assets<Mesh>) -> Handle<Mesh> {
        self.mesh.get_or_insert_with(|| meshes.add(Sphere::new(0.5).mesh().ico(1).expect("a small ico sphere"))).clone()
    }
}

/// Our own aura's root, under the view camera.
#[derive(Component)]
struct OwnAura;

/// One ember of our own aura: its place in the loop.
#[derive(Component)]
struct OwnEmber(u8);

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
                let mesh = assets.mesh(&mut meshes);
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

/// Whether the local player sees their own faint aura: alive, on a streak from the aura's tier (the same one
/// everyone else sees it from). A reset streak or a death puts it out.
pub fn own_aura_shows(rules: &StreakRules, streak: u16, dead: bool) -> bool {
    !dead && rules.has_aura(streak)
}

/// Our own aura's material: the aura's colour dimmed by `intensity` (additive, so dimmer is fainter).
fn own_ember_material(aura: &AuraLook, own: &OwnAuraLook) -> StandardMaterial {
    let [r, g, b] = aura.color;
    let k = own.intensity;
    let color = Color::srgb(r * k, g * k, b * k);
    StandardMaterial {
        base_color: color,
        emissive: color.to_linear() * own.glow,
        unlit: true,
        alpha_mode: AlphaMode::Add,
        ..default()
    }
}

/// Light our own aura under the view camera while it shows, and put it out when it does not.
#[allow(clippy::too_many_arguments)]
fn place_own_aura(
    mut commands: Commands,
    data: Res<Data>,
    me: Query<(&Score, &Vitals), With<Controlled>>,
    camera: Query<Entity, With<ViewCamera>>,
    own: Query<Entity, With<OwnAura>>,
    mut assets: ResMut<EmberAssets>,
    mut meshes: ResMut<Assets<Mesh>>,
    mut materials: ResMut<Assets<StandardMaterial>>,
) {
    let rules = &data.rules.streaks;
    let show = me.iter().next().is_some_and(|(s, v)| own_aura_shows(rules, s.streak, v.health.dead));
    match (show, own.iter().next(), camera.iter().next()) {
        (true, None, Some(cam)) => {
            let look = &rules.own_aura;
            let mesh = assets.mesh(&mut meshes);
            let material =
                assets.own_material.get_or_insert_with(|| materials.add(own_ember_material(&rules.aura, look))).clone();
            commands.entity(cam).with_children(|c| {
                c.spawn((OwnAura, Transform::default(), Visibility::default())).with_children(|a| {
                    for i in 0..look.hand_embers.saturating_add(look.edge_embers) {
                        a.spawn((
                            OwnEmber(i),
                            Mesh3d(mesh.clone()),
                            MeshMaterial3d(material.clone()),
                            Transform::from_scale(Vec3::ZERO),
                            NotShadowCaster,
                        ));
                    }
                });
            });
        }
        (false, Some(aura), _) => commands.entity(aura).despawn(),
        _ => {}
    }
}

fn animate_own_embers(
    time: Res<Time>,
    data: Res<Data>,
    windows: Query<&Window, With<PrimaryWindow>>,
    camera: Query<&Projection, With<ViewCamera>>,
    mut embers: Query<(&OwnEmber, &mut Transform)>,
) {
    let Some(projection) = camera.iter().next() else { return };
    let look = &data.rules.streaks.own_aura;
    let aspect = windows.iter().next().map_or(16.0 / 9.0, |w| w.width() / w.height().max(1.0));
    let half = view_half_extent(vfov_of(projection), aspect, look.depth_m);
    let t = time.elapsed_secs();
    for (ember, mut tf) in &mut embers {
        *tf = own_ember_at(look, ember.0, t, half);
    }
}

/// The view's half-width and half-height (metres) `depth` in front of the eye.
pub fn view_half_extent(vfov: f32, aspect: f32, depth: f32) -> Vec2 {
    let h = depth * (vfov * 0.5).tan();
    Vec2::new(h * aspect, h)
}

/// Where our own ember `i` is at `t` seconds, in view space (camera-local, -Z forward; `half`: the view's
/// half-extent at `depth_m`, [`view_half_extent`]). The first `hand_embers` rise in a column around the gun
/// hand; the rest rise along the left and right edges of the screen, in turn. Each swells in and shrinks away
/// over its loop, so it never pops.
pub fn own_ember_at(look: &OwnAuraLook, i: u8, t: f32, half: Vec2) -> Transform {
    let hand = i < look.hand_embers;
    let (k, n, offset) = if hand { (i, look.hand_embers, 0.0) } else { (i - look.hand_embers, look.edge_embers, 0.37) };
    let phase = (t / look.rise_s + k as f32 / n.max(1) as f32 + offset).fract();
    let fade = (phase * PI).sin();
    // A spread in -1..1 without a pattern (the golden ratio), and a little sway as it rises.
    let spread = (k as f32 * 0.618_034).fract() * 2.0 - 1.0;
    let sway = (phase * TAU + k as f32).sin();
    let (x, y, size) = if hand {
        let [cx, cy] = look.hand_center;
        let x = cx + spread * look.hand_spread_m + sway * look.hand_spread_m * 0.15;
        (x, cy + (phase - 0.5) * look.rise_m, look.size_m)
    } else {
        let side = if k % 2 == 0 { 1.0 } else { -1.0 };
        // Along the edge, swaying a little inward of `edge_frac`.
        let x = side * half.x * (look.edge_frac - 0.04 * (1.0 + sway));
        let y = (phase - 0.5) * 2.0 * look.rise_m + spread * 0.2 * half.y;
        (x, y.clamp(-half.y, half.y), look.size_m * look.edge_scale)
    };
    Transform::from_xyz(x, y, -look.depth_m).with_scale(Vec3::splat(size * fade))
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

    fn own() -> OwnAuraLook {
        GameData::embedded().rules.streaks.own_aura
    }

    /// Our own aura shows only from its tier, and a reset streak or a death puts it out.
    #[test]
    fn our_own_aura_shows_only_from_its_tier() {
        let r = GameData::embedded().rules.streaks;
        for s in 0..r.aura_min {
            assert!(!own_aura_shows(&r, s, false), "{s}");
        }
        for s in r.aura_min..r.aura_min + 20 {
            assert!(own_aura_shows(&r, s, false), "{s}");
            assert!(!own_aura_shows(&r, s, true), "dead: {s}");
        }
        assert!(!own_aura_shows(&r, vetf_sim::streak::after_death(9), false), "gone on reset");
    }

    /// It never blocks aim: no ember of our own ever comes within `clear_deg` of the crosshair, at any FOV and
    /// screen shape; the edge embers stay on screen at an edge; all are small and swell in from nothing.
    #[test]
    fn our_own_embers_keep_clear_of_the_crosshair() {
        let o = own();
        let count = o.hand_embers + o.edge_embers;
        assert!(count > 0 && count <= 16, "a handful");
        let clear = o.clear_deg.to_radians();
        for vfov_deg in [50.0f32, 60.0, 74.0, 90.0] {
            for aspect in [4.0 / 3.0, 16.0 / 9.0, 21.0 / 9.0, 32.0 / 9.0] {
                let half = view_half_extent(vfov_deg.to_radians(), aspect, o.depth_m);
                for i in 0..count {
                    for k in 0..120 {
                        let tf = own_ember_at(&o, i, k as f32 * 0.043, half);
                        let p = tf.translation;
                        assert!(p.z < 0.0, "in front of the eye");
                        let off_axis = p.xy().length().atan2(-p.z);
                        assert!(off_axis >= clear - 1e-4, "{vfov_deg} {aspect} #{i}: {p}");
                        assert!(tf.scale.x >= 0.0 && tf.scale.x <= o.size_m + 1e-6);
                        if i >= o.hand_embers {
                            assert!(p.x.abs() <= half.x && p.y.abs() <= half.y, "on screen: {p} in {half}");
                            assert!(p.x.abs() >= half.x * 0.5, "at an edge: {p}");
                        }
                    }
                }
            }
        }
        assert_eq!(own_ember_at(&o, 0, 0.0, Vec2::ONE).scale.x, 0.0, "swells in from nothing");
    }

    /// Our own aura is fainter and smaller than the one others see.
    #[test]
    fn our_own_aura_is_faint() {
        let (a, o) = (look(), own());
        let m = own_ember_material(&a, &o);
        assert!(m.unlit && matches!(m.alpha_mode, AlphaMode::Add));
        assert!(o.intensity < 1.0 && o.glow < a.glow);
        assert!(m.emissive.red < ember_material(&a).emissive.red * 0.5);
        assert!(o.size_m < a.size_m);
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
