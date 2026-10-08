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
    use crate::data::{FireMode, GameData, RecoilPattern};
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

    /// Where each round of a spray goes (pitch up, yaw right; degrees) when nobody pulls: round 1 at the origin,
    /// round n after the kicks of rounds 1..n-1.
    fn rounds(p: &RecoilPattern, n: u32) -> Vec<(f32, f32)> {
        let mut at = vec![(0.0_f32, 0.0_f32)];
        for shot in 1..n {
            let (kp, ky) = p.kick(shot);
            let last = at[at.len() - 1];
            at.push((last.0 + kp, last.1 + ky));
        }
        at
    }

    /// Playtest round 3 (DIRECTION_LOG 18): the Mako's pattern is a T, for every magazine (30, 45, the 60 drum).
    /// The stem: rounds 1-10 climb straight up, hard. The bar: the climb flattens and the gun sweeps right, then
    /// left across, then right again, each sweep wide enough that it needs real sideways control, the bar centred
    /// on the stem and roughly level.
    #[test]
    fn the_mako_pattern_is_a_t() {
        const STEM: usize = 10;
        let d = GameData::embedded();
        let p = &d.recoil_patterns["mako_recoil_pattern"];
        for mag in [30, 45, 60] {
            let at = rounds(p, mag);
            // The stem: no sideways drift at all, and a strong climb (hip degrees; aimed x0.7).
            let stem_climb = at[STEM - 1].0;
            assert!(at[..STEM].iter().all(|r| r.1 == 0.0), "{mag}: the stem is straight up");
            assert!((7.0..=11.0).contains(&stem_climb), "{mag}: stem climb {stem_climb}");
            // The bar: mostly sideways. Even over a drum its climb is a small part of the stem's, its sideways travel many times that.
            let bar = &at[STEM - 1..];
            let rise = bar[bar.len() - 1].0 - bar[0].0;
            let travel: f32 = bar.windows(2).map(|w| (w[1].1 - w[0].1).abs()).sum();
            assert!(rise >= 0.0 && rise < 0.4 * stem_climb, "{mag}: the bar rises {rise}");
            assert!(travel > 4.0 * rise, "{mag}: {travel} sideways against {rise} up");
            // Sweeps: runs of kicks the same way, alternating right / left / right ...
            let mut sweeps: Vec<(f32, usize)> = vec![];
            for shot in STEM as u32..mag {
                let yaw = p.kick(shot).1;
                assert_ne!(yaw, 0.0, "{mag}: every bar kick moves sideways (shot {shot})");
                match sweeps.last_mut() {
                    Some((dir, len)) if dir.signum() == yaw.signum() => {
                        *dir += yaw;
                        *len += 1;
                    }
                    _ => sweeps.push((yaw, 1)),
                }
            }
            assert!(sweeps.len() >= 3, "{mag}: at least right, left and right again: {sweeps:?}");
            assert!(sweeps[0].0 > 0.0, "{mag}: the first sweep goes right");
            assert!(sweeps.windows(2).all(|w| w[0].0.signum() != w[1].0.signum()), "{mag}: alternating");
            assert!((5..=6).contains(&sweeps[0].1), "{mag}: first sweep over 5-6 rounds: {sweeps:?}");
            // Every full sweep crosses the bar: 2-4x the first, in 6-10 rounds (the last one may be cut off by the mag).
            for (i, (yaw, len)) in sweeps[1..sweeps.len() - 1].iter().enumerate() {
                assert!((6..=10).contains(len), "{mag}: sweep {} over {len} rounds", i + 2);
                assert!(yaw.abs() > 1.5 * sweeps[0].0, "{mag}: sweep {} crosses the bar: {yaw}", i + 2);
            }
            // The bar's width is data-sane: 3-8 deg hip (2.1-5.6 aimed), and centred on the stem within half a degree.
            let (lo, hi) = bar.iter().fold((f32::MAX, f32::MIN), |(lo, hi), r| (lo.min(r.1), hi.max(r.1)));
            assert!((3.0..=8.0).contains(&(hi - lo)), "{mag}: bar width {}", hi - lo);
            assert!((hi + lo).abs() < 0.5, "{mag}: the bar is centred on the stem: {lo} .. {hi}");
        }
    }

    /// The Skink keeps its round-2 pattern, the old Mako column x0.6 (the T is the AR's alone): a tall climb with a
    /// gentle sway, lighter on every shot.
    #[test]
    fn the_skink_keeps_its_column() {
        let d = GameData::embedded();
        let p = &d.recoil_patterns["skink_recoil_pattern"];
        assert_eq!((p.kicks.len(), p.loop_from_index), (29, 20));
        let at = rounds(p, 40);
        let (lo, hi) = at.iter().fold((f32::MAX, f32::MIN), |(lo, hi), r| (lo.min(r.1), hi.max(r.1)));
        assert!(hi - lo < 1.0, "a gentle sway: {lo} .. {hi}");
        assert!((at[20].0 - 7.584).abs() < 1e-3, "{:?}", at[20]);
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
