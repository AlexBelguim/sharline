//! THROW LINE (Settings > Gameplay, a testing aid; user, 2026-10-10: "can you give a throw line for testing"):
//! with a grenade in hand, the arc it would fly and where it goes off, drawn every frame from where we stand and
//! look. It is the simulation's own flight ([`vetf_sim::throwable::predict_path`]) of the throw the hand would make
//! now: the overhand throw at the charge held so far (LMB), and fainter, the soft underhand one (RMB). A ring marks
//! the smoke cloud's or the fire's size where it would go off. Bounces show as small rings.

use super::ViewCamera;
use crate::client::{LocalControl, Smoothed};
use crate::config::{CurrentLevel, Data};
use crate::settings::Settings;
use bevy::prelude::*;
use lightyear::prelude::*;
use std::f32::consts::FRAC_PI_2;
use vetf_net::*;
use vetf_sim::throwable::{PredictedPath, ThrowKind, ThrowStyle, launch_charged, predict_path};

/// The overhand line's colour, the underhand line's, and the burst ring's.
const OVERHAND: Color = Color::srgba(0.35, 1.0, 0.85, 0.95);
const UNDERHAND: Color = Color::srgba(0.35, 1.0, 0.85, 0.35);
const BOUNCE: Color = Color::srgba(1.0, 1.0, 1.0, 0.7);

/// The throws to draw for a hand: what is in it, and each style with its charge (normalised, 0..=u16::MAX).
/// Selected: the overhand throw at the charge held so far and the underhand one; winding up: the committed throw.
pub fn throws_to_draw(hand: &vetf_sim::throwable::ThrowHand, charge_now: f32) -> Vec<(ThrowKind, ThrowStyle, u16)> {
    if let Some(w) = hand.windup {
        return vec![(w.kind, w.style, w.charge)];
    }
    let Some(kind) = hand.selected else { return vec![] };
    let charge = (charge_now.clamp(0.0, 1.0) * u16::MAX as f32).round() as u16;
    vec![(kind, ThrowStyle::Overhand, charge), (kind, ThrowStyle::Underhand, 0)]
}

fn ground_ring(gizmos: &mut Gizmos, at: Vec3, radius: f32, color: Color) {
    let flat = Isometry3d::new(at + Vec3::Y * 0.03, Quat::from_rotation_x(FRAC_PI_2));
    gizmos.circle(flat, radius, color).resolution(48);
}

fn draw_path(gizmos: &mut Gizmos, path: &PredictedPath, color: Color, burst_radius: f32, bounces: bool) {
    gizmos.linestrip(path.points.iter().copied(), color);
    if bounces {
        for b in &path.bounces {
            ground_ring(gizmos, *b, 0.12, BOUNCE);
        }
    }
    if let Some(at) = path.burst {
        ground_ring(gizmos, at, 0.25, color);
        ground_ring(gizmos, at, burst_radius, color.with_alpha(color.alpha() * 0.6));
    }
}

/// Draws our grenade's line while one is in hand and THROW LINE is on.
pub(crate) fn draw_throw_line(
    settings: Res<Settings>,
    data: Res<Data>,
    control: Res<LocalControl>,
    fixed: Res<Time<Fixed>>,
    level: Option<Res<CurrentLevel>>,
    editor: Option<Res<crate::build_editor::EditorActive>>,
    me: Query<(&PlayerItems, &PlayerMove, Option<&Smoothed>, &Vitals), With<Controlled>>,
    camera: Query<(), With<ViewCamera>>,
    mut gizmos: Gizmos,
) {
    if !settings.gameplay.throw_line || editor.is_some_and(|e| e.0) || camera.is_empty() {
        return;
    }
    let (Some(level), Some((items, mv, smoothed, vitals))) = (level, me.iter().next()) else { return };
    if vitals.health.dead {
        return;
    }
    let hand = &items.0.throw;
    let spec = &data.throwables.throw;
    let throws = throws_to_draw(hand, hand.charge_fraction(spec, data.net.tick_hz));
    if throws.is_empty() {
        return;
    }
    // From where the view is this frame (the eye blended between ticks, as the camera is).
    let feet = smoothed.map_or(mv.0.pos, |s| s.prev.lerp(s.curr, fixed.overstep_fraction()));
    let eye = feet + Vec3::Y * mv.0.eye;
    let dt = data.tick_dt();
    let max_ticks = (data.throwables.projectile.max_flight_s / dt).ceil() as u32 + 2;
    for (i, (kind, style, charge)) in throws.into_iter().enumerate() {
        let (origin, vel) =
            launch_charged(spec, &level.world, eye, mv.0.vel, control.yaw, control.pitch, kind, style, charge);
        let path = predict_path(&data.throwables, &level, kind, origin, vel, charge, dt, max_ticks);
        let radius = match kind {
            ThrowKind::Smoke => data.throwables.smoke.radius_m,
            ThrowKind::Molotov => data.throwables.molotov.radius_m,
        };
        draw_path(&mut gizmos, &path, if i == 0 { OVERHAND } else { UNDERHAND }, radius, i == 0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::throwable::{ThrowHand, ThrowKit, Windup};

    #[test]
    fn the_line_shows_only_with_a_grenade_in_hand() {
        let mut hand = ThrowHand::new(ThrowKit { smoke: 2, molotov: 1 });
        assert!(throws_to_draw(&hand, 0.0).is_empty(), "nothing in hand: no line");
        hand.selected = Some(ThrowKind::Molotov);
        let both = throws_to_draw(&hand, 0.5);
        assert_eq!(both.len(), 2);
        assert_eq!(both[0].0, ThrowKind::Molotov);
        assert_eq!((both[0].1, both[1].1), (ThrowStyle::Overhand, ThrowStyle::Underhand));
        assert!((both[0].2 as f32 / u16::MAX as f32 - 0.5).abs() < 1e-3, "the charge held so far");
        assert_eq!(throws_to_draw(&hand, 3.0)[0].2, u16::MAX, "clamped");
        hand.selected = None;
        hand.windup = Some(Windup { kind: ThrowKind::Smoke, left: 5, style: ThrowStyle::Overhand, charge: 999 });
        assert_eq!(throws_to_draw(&hand, 0.0), vec![(ThrowKind::Smoke, ThrowStyle::Overhand, 999)]);
    }
}
