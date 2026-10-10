//! The gun put away while a grenade is in hand: from the moment a smoke or a molotov is equipped, through the
//! wind-up and the recovery after the throw, the gun drops out of the view and hides, and the held grenade
//! (`throw_fx`) is all you hold. It comes back up when the hand is free again (user, 2026-10-10: "when switching
//! to nade the guns still stays active"; before, it only tilted into the sprint pose and stayed on screen).
//!
//! The simulation already stops the gun while the hand is busy (`ThrowHand::busy`: no fire, no aim). This is the
//! picture of it, visual only (`feel.ron` gun.holster_pose).

use super::feel::{FeelData, HolsterPose};
use bevy::prelude::*;
use lightyear::prelude::*;
use vetf_net::*;

/// How far our own gun is put away (0 in the hands, 1 out of view), eased.
#[derive(Resource, Debug, Default, Clone, Copy, PartialEq)]
pub struct ViewHolster {
    /// Linear progress toward the wanted state; [`ViewHolster::amount`] eases it.
    pub t: f32,
}

impl ViewHolster {
    /// The eased share of the holster pose (0..1).
    pub fn amount(&self) -> f32 {
        let x = self.t.clamp(0.0, 1.0);
        x * x * (3.0 - 2.0 * x)
    }

    /// Hidden once it is this far down (the gun is out of view by then; hiding also hides its laser).
    pub fn hidden(&self, pose: &HolsterPose) -> bool {
        self.amount() >= pose.hide_at
    }
}

/// One frame toward away (`busy`) or back in the hands: down over `down_s`, up over `up_s`.
pub fn step(t: f32, busy: bool, pose: &HolsterPose, dt: f32) -> f32 {
    if busy { (t + dt / pose.down_s.max(1e-3)).min(1.0) } else { (t - dt / pose.up_s.max(1e-3)).max(0.0) }
}

/// The gun's view pose with `amount` of the holster on top: shifted (view axes, metres) and pitched muzzle down.
pub fn holster_gun(pose: &HolsterPose, gun: Transform, amount: f32) -> Transform {
    if amount <= 0.0 {
        return gun;
    }
    let mut out = gun;
    out.translation += Vec3::from(pose.shift) * amount;
    out.rotation = Quat::from_rotation_x(pose.pitch_deg.to_radians() * amount) * out.rotation;
    out
}

/// Eases our gun away while our grenade hand is busy, and back once it is free (dead: straight back).
pub(crate) fn step_view_holster(
    time: Res<Time>,
    feel: Res<FeelData>,
    me: Query<(&PlayerItems, &Vitals), With<Controlled>>,
    mut holster: ResMut<ViewHolster>,
) {
    let Some((items, vitals)) = me.iter().next() else { return };
    if vitals.health.dead {
        *holster = ViewHolster::default();
        return;
    }
    holster.t = step(holster.t, items.0.throw.busy(), &feel.gun.holster_pose, time.delta_secs());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_gun_goes_away_while_a_grenade_is_out_and_comes_back_after() {
        let pose = FeelData::embedded().gun.holster_pose;
        assert!(pose.shift[1] < -0.1, "it drops out of view");
        let dt = 1.0 / 120.0;
        let mut h = ViewHolster::default();
        assert!(!h.hidden(&pose));
        // Equipped: down within `down_s`, hidden by then.
        let mut frames = 0;
        while h.t < 1.0 {
            h.t = step(h.t, true, &pose, dt);
            frames += 1;
        }
        assert!(frames as f32 * dt <= pose.down_s + dt * 1.5);
        assert!(h.hidden(&pose) && (h.amount() - 1.0).abs() < 1e-6);
        // Free again: shown again early on the way up (within a quarter of `up_s`), fully up within `up_s`.
        let mut frames = 0;
        while h.t > 0.0 {
            h.t = step(h.t, false, &pose, dt);
            frames += 1;
            if frames as f32 * dt >= pose.up_s * 0.25 {
                assert!(!h.hidden(&pose), "shown by a quarter of the way back up");
            }
        }
        assert!(frames as f32 * dt <= pose.up_s + dt * 1.5);
        assert_eq!(h.amount(), 0.0);
    }

    #[test]
    fn the_pose_moves_the_gun_down_and_tips_it_only_while_put_away() {
        let pose = FeelData::embedded().gun.holster_pose;
        let gun = Transform::from_xyz(0.2, -0.2, -0.4);
        assert_eq!(holster_gun(&pose, gun, 0.0), gun);
        let away = holster_gun(&pose, gun, 1.0);
        assert!(away.translation.y < gun.translation.y - 0.1);
        let muzzle = away.rotation * Vec3::NEG_Z;
        assert!(muzzle.y < -0.2, "muzzle tipped down: {muzzle}");
    }
}
