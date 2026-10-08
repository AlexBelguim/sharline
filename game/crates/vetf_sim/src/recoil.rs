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

/// The purely visual camera punch (degrees) a shot starts. It never moves the aim, and the screen-shake setting
/// scales it.
pub fn view_punch(spec: &WeaponSpec) -> f32 {
    match &spec.recoil {
        RecoilSpec::Pattern(p) => p.view_punch_visual_deg,
        RecoilSpec::Kick(_) => 0.0,
    }
}

/// The visual punch `punch_deg` after `dt` more seconds: it settles linearly over `view_punch_return_s`.
pub fn settle_punch(spec: &WeaponSpec, punch_deg: f32, dt: f32) -> f32 {
    match &spec.recoil {
        RecoilSpec::Pattern(p) => {
            let rate = p.view_punch_visual_deg / p.view_punch_return_s.max(1e-3);
            (punch_deg - rate * dt).max(0.0)
        }
        RecoilSpec::Kick(_) => 0.0,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::data::{FireMode, GameData};
    use crate::weapon::fire_interval_ticks;

    #[test]
    fn recovers_part_of_uncompensated_climb() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let RecoilSpec::Pattern(p) = &mako.recoil else { panic!("the Mako has a pattern") };
        let mut r = ViewRecoil::default();
        let mut pitch = 0.0;
        for k in [1.0, 1.1, 1.15] {
            r.on_shot(mako, pitch, k);
            pitch += k;
        }
        let climbed = pitch;
        let mut t = 0.0;
        while t < 2.0 {
            pitch -= r.tick(mako, pitch, 1.0 / 60.0);
            t += 1.0 / 60.0;
        }
        // `recover_frac` (half) of the climb comes back down
        assert_eq!(p.recover_frac, 0.5);
        assert!((pitch - climbed * (1.0 - p.recover_frac)).abs() < 1e-4, "{pitch}");
    }

    /// Playtest round 1: the pattern must be the same every spray, so nothing recovers between the shots of an
    /// automatic spray, even aimed (the slowest automatic fire) and with uneven frame times.
    #[test]
    fn a_spray_never_recovers_between_shots() {
        let d = GameData::embedded();
        let hz = d.net.tick_hz;
        for w in d.weapons.weapons.iter().filter(|w| w.fire_modes.contains(&FireMode::Auto)) {
            let RecoilSpec::Pattern(p) = &w.recoil else { continue };
            let interval = fire_interval_ticks(w, hz, true) as f32 / hz as f32;
            assert!(
                p.recover_delay_s >= interval + 2.0 / hz as f32,
                "{}: {} s vs {interval} s",
                w.id,
                p.recover_delay_s
            );
            let mut r = ViewRecoil::default();
            let (mut t, mut next, mut pitch, mut shots, mut recovered) = (0.0_f32, 0.0_f32, 0.0_f32, 0, 0.0_f32);
            let frames = [1.0 / 144.0, 1.0 / 40.0, 1.0 / 90.0, 1.0 / 30.0];
            let mut i = 0;
            while shots < 20 {
                if t >= next {
                    r.on_shot(w, pitch, 0.5);
                    pitch += 0.5;
                    shots += 1;
                    next += interval;
                }
                let dt = frames[i % frames.len()];
                i += 1;
                recovered += r.tick(w, pitch, dt);
                t += dt;
            }
            assert_eq!(recovered, 0.0, "{}: recovered mid-spray", w.id);
            for _ in 0..120 {
                recovered += r.tick(w, pitch - recovered, 1.0 / 60.0);
            }
            assert!(recovered > 0.0, "{}: recovers once the spray stops", w.id);
        }
    }

    /// Every shot's visual punch is back before the next shot, so it reads as a kick and never as an aim offset.
    #[test]
    fn the_view_punch_is_back_before_the_next_shot() {
        let d = GameData::embedded();
        let hz = d.net.tick_hz;
        for w in &d.weapons.weapons {
            let RecoilSpec::Pattern(p) = &w.recoil else {
                assert_eq!(view_punch(w), 0.0, "{}: kick guns have no visual punch", w.id);
                continue;
            };
            let punch = view_punch(w);
            assert!(punch >= 0.3, "{}: a visible punch: {punch}", w.id);
            let interval = fire_interval_ticks(w, hz, false) as f32 / hz as f32;
            assert!(p.view_punch_return_s < interval, "{}: {} s vs {interval} s", w.id, p.view_punch_return_s);
            let half = settle_punch(w, punch, p.view_punch_return_s * 0.5);
            assert!((half - punch * 0.5).abs() < 1e-5, "{}: {half}", w.id);
            assert_eq!(settle_punch(w, punch, p.view_punch_return_s + 1e-4), 0.0, "{}", w.id);
        }
    }

    /// The Skink's pattern is the Mako's x0.6: the same shape to learn, lighter on every shot.
    #[test]
    fn the_skink_pattern_is_the_makos_lighter() {
        let d = GameData::embedded();
        let (mako, skink) = (&d.recoil_patterns["mako_recoil_pattern"], &d.recoil_patterns["skink_recoil_pattern"]);
        assert_eq!(mako.kicks.len(), skink.kicks.len());
        assert_eq!(mako.loop_from_index, skink.loop_from_index);
        for (m, s) in mako.kicks.iter().zip(&skink.kicks) {
            assert_eq!(m.after_shot, s.after_shot);
            assert!(
                (s.pitch - m.pitch * 0.6).abs() < 1e-4 && (s.yaw - m.yaw * 0.6).abs() < 1e-4,
                "shot {}",
                m.after_shot
            );
        }
    }

    #[test]
    fn compensated_climb_is_not_recovered() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let mut r = ViewRecoil::default();
        r.on_shot(mako, 0.0, 1.0);
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
