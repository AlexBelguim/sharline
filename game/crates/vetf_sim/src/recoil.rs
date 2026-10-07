//! View recoil on the shooter's camera.
//!
//! Each shot rotates the view by the kick from [`crate::weapon::Shot`]; the player pulls down to
//! compensate. After a short pause the gun recovers part of the climb the player did *not* compensate.
//! This runs only on the shooter's own client (the view angles it produces go into its inputs), so it is
//! never re-simulated during rollback.

use crate::data::{RecoilSpec, WeaponSpec};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
pub struct ViewRecoil {
    /// Seconds since the last shot.
    since_shot: f32,
    /// View pitch (degrees) when the current burst started.
    burst_start_pitch: f32,
    /// Total upward kick applied during this burst (degrees).
    burst_kick: f32,
    /// Degrees still to recover (set when recovery starts).
    to_recover: f32,
    recovering: bool,
    in_burst: bool,
}

impl ViewRecoil {
    /// Register a shot fired at `pitch_deg` (before the kick) with an upward kick of `kick_pitch`.
    pub fn on_shot(&mut self, spec: &WeaponSpec, pitch_deg: f32, kick_pitch: f32) {
        let reset = match &spec.recoil {
            RecoilSpec::Pattern(p) => p.reset_after_s,
            RecoilSpec::Kick(_) => 0.0,
        };
        if !self.in_burst || self.since_shot >= reset {
            self.burst_start_pitch = pitch_deg;
            self.burst_kick = 0.0;
        }
        self.in_burst = true;
        self.recovering = false;
        self.to_recover = 0.0;
        self.burst_kick += kick_pitch;
        self.since_shot = 0.0;
    }

    /// Advance by `dt` and return how many degrees to lower the view pitch this frame.
    pub fn tick(&mut self, spec: &WeaponSpec, pitch_deg: f32, dt: f32) -> f32 {
        if !self.in_burst {
            return 0.0;
        }
        self.since_shot += dt;
        let (frac, delay, rate) = match &spec.recoil {
            RecoilSpec::Pattern(p) => (p.recover_frac, p.recover_delay_s, p.recover_deg_per_s),
            RecoilSpec::Kick(k) => (k.recover_frac, 0.0, k.kick_pitch_deg * k.recover_frac / k.recover_s.max(1e-3)),
        };
        if self.since_shot < delay {
            return 0.0;
        }
        if !self.recovering {
            // Only the climb the player did not pull down themselves is recovered.
            let climb = (pitch_deg - self.burst_start_pitch).clamp(0.0, self.burst_kick);
            self.to_recover = climb * frac;
            self.recovering = true;
        }
        let step = (rate * dt).min(self.to_recover);
        self.to_recover -= step;
        if self.to_recover <= 0.0 {
            self.in_burst = false;
        }
        step
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::GameData;

    #[test]
    fn recovers_part_of_uncompensated_climb() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let mut r = ViewRecoil::default();
        let mut pitch = 0.0;
        for k in [0.55, 0.6, 0.62] {
            r.on_shot(mako, pitch, k);
            pitch += k;
        }
        let climbed = pitch;
        let mut t = 0.0;
        while t < 2.0 {
            pitch -= r.tick(mako, pitch, 1.0 / 60.0);
            t += 1.0 / 60.0;
        }
        // 60% of the climb comes back down
        assert!((pitch - climbed * 0.4).abs() < 1e-4, "{pitch}");
    }

    #[test]
    fn compensated_climb_is_not_recovered() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let mut r = ViewRecoil::default();
        r.on_shot(mako, 0.0, 0.55);
        // the player pulled the view back down below where the burst started
        let mut pitch = -0.2;
        for _ in 0..120 {
            pitch -= r.tick(mako, pitch, 1.0 / 60.0);
        }
        assert_eq!(pitch, -0.2);
    }

    #[test]
    fn warden_recovers_70_percent_quickly() {
        let d = GameData::embedded();
        let w = d.weapon("vk50_warden").unwrap();
        let mut r = ViewRecoil::default();
        r.on_shot(w, 0.0, 3.5);
        let mut pitch = 3.5;
        for _ in 0..22 {
            pitch -= r.tick(w, pitch, 1.0 / 60.0);
        }
        assert!((pitch - 3.5 * 0.3).abs() < 1e-3, "{pitch}");
    }
}
