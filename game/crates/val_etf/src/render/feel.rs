//! `game/assets/data/feel.ron`: the numbers behind the screen and gun feel (camera bob and shot shake, the
//! gun's sway and kick, tracers, hit markers and halo cracks). Visual only: none of it reaches the simulation,
//! so it is not part of the gameplay data the host and clients must share.

use bevy::prelude::*;
use serde::Deserialize;
use std::collections::HashMap;
use std::f32::consts::{E, TAU};
use std::sync::OnceLock;

#[derive(Resource, Debug, Clone, PartialEq, Deserialize)]
pub struct FeelData {
    pub camera: CameraFeel,
    /// Per weapon id (weapons.ron).
    pub shots: HashMap<String, ShotFeel>,
    pub default_shot: ShotFeel,
    pub gun: GunFeel,
    pub tracers: TracerFeel,
    pub laser: LaserFeel,
    pub hits: HitFeel,
    pub halo: HaloFeel,
}

/// The head's bob at one gait.
#[derive(Debug, Clone, Copy, PartialEq, Default, Deserialize)]
pub struct Gait {
    pub step_hz: f32,
    pub up_m: f32,
    pub side_m: f32,
    pub pitch_deg: f32,
    pub yaw_deg: f32,
    pub roll_deg: f32,
}

impl Gait {
    /// Field by field from `a` (t = 0) to `b` (t = 1).
    pub fn lerp(a: Gait, b: Gait, t: f32) -> Gait {
        let l = |x: f32, y: f32| x + (y - x) * t;
        Gait {
            step_hz: l(a.step_hz, b.step_hz),
            up_m: l(a.up_m, b.up_m),
            side_m: l(a.side_m, b.side_m),
            pitch_deg: l(a.pitch_deg, b.pitch_deg),
            yaw_deg: l(a.yaw_deg, b.yaw_deg),
            roll_deg: l(a.roll_deg, b.roll_deg),
        }
    }

    /// The same rhythm with the swing scaled by `k`.
    pub fn scaled(self, k: f32) -> Gait {
        Gait {
            up_m: self.up_m * k,
            side_m: self.side_m * k,
            pitch_deg: self.pitch_deg * k,
            yaw_deg: self.yaw_deg * k,
            roll_deg: self.roll_deg * k,
            ..self
        }
    }
}

/// The gun's bob at one gait.
#[derive(Debug, Clone, Copy, PartialEq, Default, Deserialize)]
pub struct GunGait {
    pub side_m: f32,
    pub up_m: f32,
    pub roll_deg: f32,
    pub pitch_deg: f32,
}

impl GunGait {
    pub fn lerp(a: GunGait, b: GunGait, t: f32) -> GunGait {
        let l = |x: f32, y: f32| x + (y - x) * t;
        GunGait {
            side_m: l(a.side_m, b.side_m),
            up_m: l(a.up_m, b.up_m),
            roll_deg: l(a.roll_deg, b.roll_deg),
            pitch_deg: l(a.pitch_deg, b.pitch_deg),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct SpringSpec {
    pub hz: f32,
    pub damping: f32,
}

/// A landing's dip and nod, by the fall speed.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Landing {
    pub min_speed_mps: f32,
    pub dip_m_per_mps: f32,
    pub max_dip_m: f32,
    pub pitch_deg_per_mps: f32,
    pub max_pitch_deg: f32,
    pub spring: SpringSpec,
}

impl Landing {
    /// (dip in metres, nod down in degrees) for landing at `fall_mps`; none below the threshold.
    pub fn kick(&self, fall_mps: f32) -> Option<(f32, f32)> {
        (fall_mps >= self.min_speed_mps).then(|| {
            (
                (fall_mps * self.dip_m_per_mps).min(self.max_dip_m),
                (fall_mps * self.pitch_deg_per_mps).min(self.max_pitch_deg),
            )
        })
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct CameraFeel {
    pub walk: Gait,
    pub jog: Gait,
    pub sprint: Gait,
    pub crouch_mult: f32,
    pub ads_turn_mult: f32,
    pub ads_shift_mult: f32,
    pub ease_s: f32,
    pub land: Landing,
    pub shot_damping: f32,
    pub ads_shot_mult: f32,
    /// The view follows a step up or down on flat ground over this time constant.
    pub step_smooth_s: f32,
}

/// One gun's shot: the camera's jolt and the gun's kick.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct ShotFeel {
    pub pitch_deg: f32,
    pub yaw_deg: f32,
    pub roll_deg: f32,
    pub back_m: f32,
    pub settle_hz: f32,
    pub gun_back_m: f32,
    pub gun_pitch_deg: f32,
    pub gun_settle_hz: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Breath {
    pub period_s: f32,
    pub shift_m: f32,
    pub turn_deg: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Drag {
    pub lag: f32,
    pub max_deg: f32,
    pub shift_m_per_deg: f32,
    pub roll_per_deg: f32,
    pub spring: SpringSpec,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct SprintPose {
    pub shift: [f32; 3],
    pub yaw_deg: f32,
    pub ease_s: f32,
}

/// The gun put away while a grenade is in hand (`render::holster`): shifted (view axes, metres) and pitched muzzle
/// down (degrees, negative), down over `down_s`, back up over `up_s`, hidden once `hide_at` of the way down.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct HolsterPose {
    pub shift: [f32; 3],
    pub pitch_deg: f32,
    pub down_s: f32,
    pub up_s: f32,
    pub hide_at: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct GunFeel {
    pub breath: Breath,
    pub drag: Drag,
    pub walk: GunGait,
    pub jog: GunGait,
    pub sprint: GunGait,
    pub land: Landing,
    pub kick_damping: f32,
    pub ads_mult: f32,
    /// Aimed, the share of the sway's shift across the view (x, y) that stays.
    pub ads_shift_mult: f32,
    pub ads_kick_mult: f32,
    pub sprint_pose: SprintPose,
    pub holster_pose: HolsterPose,
    pub mag_inspect: MagInspectFeel,
    pub dry_fire: DryFireFeel,
}

/// The empty gun's twitch on each dry pull, and the frustrated shake after a few in a row (`render::dry_fire`).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct DryFireFeel {
    pub twitch_pitch_deg: f32,
    pub twitch_down_m: f32,
    pub twitch: SpringSpec,
    pub shake_after_pulls: u32,
    pub reset_after_s: f32,
    pub shake_s: f32,
    pub smack_down_m: f32,
    pub smack_pitch_deg: f32,
    pub smack_s: f32,
    pub shake_hz: f32,
    pub shake_roll_deg: f32,
    pub shake_yaw_deg: f32,
    pub cancel_s: f32,
    pub third_person_mult: f32,
}

/// A mag check's turn of the gun toward the eye (`render::inspect`): its timing, the first-person pose (a shift
/// in view space, then a turn about the grip) and the third-person turn.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct MagInspectFeel {
    pub in_s: f32,
    pub out_s: f32,
    pub cancel_s: f32,
    pub shift: [f32; 3],
    pub yaw_deg: f32,
    pub pitch_deg: f32,
    pub roll_deg: f32,
    pub third_person: HeldInspect,
}

/// The third-person gun's turn about the grip during a mag check, eased in and out over `ease_s`.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct HeldInspect {
    pub yaw_deg: f32,
    pub pitch_deg: f32,
    pub roll_deg: f32,
    pub ease_s: f32,
}

/// A camera-facing ribbon: its width and its colours (linear RGBA, above 1 glows) for own and others' shots.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Ribbon {
    pub width_m: f32,
    pub min_px: f32,
    pub max_px: f32,
    pub own: [f32; 4],
    pub other: [f32; 4],
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Smoke {
    pub life_s: f32,
    pub width_m: f32,
    pub grow_m: f32,
    pub min_px: f32,
    pub max_px: f32,
    pub color: [f32; 4],
    pub skip_own_m: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct TracerFeel {
    pub speed_mps: f32,
    pub streak_m: f32,
    pub core: Ribbon,
    pub glow: Ribbon,
    pub smoke: Smoke,
}

/// The LASER's beam and dot (`render::laser_fx`).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct LaserFeel {
    /// How far from the emitter the beam shows (it fades out toward here).
    pub beam_m: f32,
    /// How far from the eye the dot still shows on what the aim meets.
    pub dot_max_m: f32,
    /// The beam follows the barrel instead of the aim once the barrel turns this far (degrees) from the aim: none
    /// at the first, all of it from the second (the gun lowered, folded or busy).
    pub follow_barrel_deg: (f32, f32),
    pub beam: Ribbon,
    pub dot: Ribbon,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct HitFeel {
    pub life_s: f32,
    pub pop_s: f32,
    pub pop_scale: f32,
    pub size_px: f32,
    pub thickness_px: f32,
    pub gap_px: f32,
    pub head_scale: f32,
    pub kill_scale: f32,
    pub ring_px: f32,
    pub ring_border_px: f32,
    pub remember_s: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct Shards {
    pub count: u32,
    pub size_m: f32,
    pub speed_mps: f32,
    pub life_s: f32,
}

/// How shards fly off a cracked or broken arc.
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct ShardFlight {
    pub scatter: f32,
    pub lift: f32,
    pub speed_jitter: f32,
    pub size_jitter: f32,
    pub spread: f32,
    pub drag_per_s: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
pub struct HaloFeel {
    pub min_drop: f32,
    pub flash_s: f32,
    pub flash_gain: f32,
    pub pulse_scale: f32,
    pub crack: Shards,
    pub shatter: Shards,
    pub shards: ShardFlight,
    pub gravity_mps2: f32,
    pub spin_rps: f32,
    pub ring_s: f32,
    pub ring_grow: f32,
    pub max_shards: usize,
}

const EMBEDDED: &str = include_str!("../../../../assets/data/feel.ron");

impl FeelData {
    /// The copy compiled into the binary.
    pub fn embedded() -> &'static FeelData {
        static DATA: OnceLock<FeelData> = OnceLock::new();
        DATA.get_or_init(|| ron::from_str(EMBEDDED).expect("game/assets/data/feel.ron is valid"))
    }

    /// From the data folder (so it can be tuned without a rebuild), else the built-in copy.
    pub fn load() -> FeelData {
        let path = crate::config::assets_root().join("data").join("feel.ron");
        match std::fs::read_to_string(&path).map(|text| ron::from_str(&text)) {
            Ok(Ok(d)) => d,
            Ok(Err(e)) => {
                error!("{} is invalid ({e}); using the built-in copy", path.display());
                Self::embedded().clone()
            }
            Err(_) => Self::embedded().clone(),
        }
    }

    /// A gun's shot feel, or the default for a gun without a row.
    pub fn shot(&self, weapon: &str) -> &ShotFeel {
        self.shots.get(weapon).unwrap_or(&self.default_shot)
    }
}

impl ShotFeel {
    /// The shake as the build's recoil multipliers shape it (attachments.ron `recoil_v` / `recoil_h`): a stock
    /// calms the vertical parts (the camera's pitch and push-back, the gun's kick up and back), a front grip the
    /// sideways ones (yaw and roll), so a steadier build also looks steadier. The settle speeds stay.
    pub fn scaled(self, recoil_v: f32, recoil_h: f32) -> ShotFeel {
        ShotFeel {
            pitch_deg: self.pitch_deg * recoil_v,
            back_m: self.back_m * recoil_v,
            gun_back_m: self.gun_back_m * recoil_v,
            gun_pitch_deg: self.gun_pitch_deg * recoil_v,
            yaw_deg: self.yaw_deg * recoil_h,
            roll_deg: self.roll_deg * recoil_h,
            ..self
        }
    }
}

// ---------------------------------------------------------------------------------------------- springs

/// A damped spring pulled back to 0: kicks move it, and it settles at its own speed.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Spring {
    pub x: f32,
    pub v: f32,
}

impl Spring {
    /// Advance by `dt` seconds at `hz` with damping ratio `damping` (0..1; above 1 counts as 1). Stepped by the
    /// exact solution, so it moves the same at any frame rate.
    pub fn step(&mut self, hz: f32, damping: f32, dt: f32) {
        if dt <= 0.0 {
            return;
        }
        let w = TAU * hz.max(0.01);
        let z = damping.clamp(0.0, 1.0);
        let (x0, v0) = (self.x, self.v);
        let decay = (-z * w * dt).exp();
        if z >= 0.999 {
            let c = v0 + w * x0;
            self.x = (x0 + c * dt) * decay;
            self.v = (v0 - c * w * dt) * decay;
        } else {
            let wd = w * (1.0 - z * z).sqrt();
            let (sin, cos) = (wd * dt).sin_cos();
            let (a, b) = (x0, (v0 + z * w * x0) / wd);
            self.x = decay * (a * cos + b * sin);
            self.v = decay * ((b * wd - z * w * a) * cos - (a * wd + z * w * b) * sin);
        }
    }

    /// A kick that swings the spring out to about `amp` (its peak, when it starts at rest).
    pub fn kick(&mut self, amp: f32, hz: f32, damping: f32) {
        let w = TAU * hz.max(0.01);
        self.v += amp * w / peak_per_unit_velocity(damping);
    }
}

/// How far a spring at rest swings when kicked with a velocity of one (angular frequency units): the peak of
/// x(t) for x(0) = 0, x'(0) = w, in units of 1.
pub fn peak_per_unit_velocity(damping: f32) -> f32 {
    let z = damping.clamp(0.0, 1.0);
    if z >= 0.999 {
        return 1.0 / E;
    }
    let s = (1.0 - z * z).sqrt();
    (-z / s * (s / z.max(1e-6)).atan()).exp()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_data_parses_and_every_gun_has_a_shot() {
        let f = FeelData::embedded();
        assert_eq!(&FeelData::load(), f, "disk copy matches the built-in one");
        let d = vetf_sim::GameData::embedded();
        for w in &d.weapons.weapons {
            assert!(f.shots.contains_key(&w.id), "{} has no shot feel", w.id);
        }
        for id in f.shots.keys() {
            assert!(d.weapon_index(id).is_some(), "{id} is not in weapons.ron");
        }
        // SMG light, Mako medium, Warden one bigger jolt.
        let (smg, ar, sniper) = (f.shot("sk9_skink"), f.shot("ar7_mako"), f.shot("vk50_warden"));
        assert!(smg.pitch_deg < ar.pitch_deg && ar.pitch_deg < sniper.pitch_deg);
        assert!(smg.settle_hz > ar.settle_hz && ar.settle_hz > sniper.settle_hz, "the SMG's settles fastest");
        assert_eq!(f.shot("no_such_gun"), &f.default_shot);
        // Sprinting wobbles more than jogging, jogging more than walking.
        let c = &f.camera;
        assert!(c.walk.pitch_deg < c.jog.pitch_deg && c.jog.pitch_deg < c.sprint.pitch_deg);
        assert!(c.walk.roll_deg < c.sprint.roll_deg && c.walk.up_m < c.sprint.up_m);
        assert!(f.gun.ads_mult < 0.2, "aimed, the gun barely sways");
    }

    #[test]
    fn a_kick_peaks_at_its_amplitude_and_settles_at_any_frame_rate() {
        for damping in [0.5, 0.6, 1.0] {
            for fps in [30.0, 60.0, 144.0, 500.0] {
                let mut s = Spring::default();
                s.kick(2.0, 6.0, damping);
                let (mut peak, dt) = (0.0f32, 1.0 / fps);
                for _ in 0..(fps as usize) {
                    s.step(6.0, damping, dt);
                    peak = peak.max(s.x);
                }
                assert!((peak - 2.0).abs() < 0.1, "damping {damping} at {fps} fps: peak {peak}");
                assert!(s.x.abs() < 0.05, "settled after a second: {}", s.x);
            }
        }
    }

    #[test]
    fn a_landing_dips_more_when_harder_up_to_a_cap() {
        let l = FeelData::embedded().camera.land;
        assert_eq!(l.kick(l.min_speed_mps * 0.5), None, "a step down is no landing");
        let (soft, hard) = (l.kick(4.0).unwrap(), l.kick(9.0).unwrap());
        assert!(hard.0 > soft.0 && hard.1 > soft.1);
        assert_eq!(l.kick(100.0).unwrap(), (l.max_dip_m, l.max_pitch_deg));
    }

    /// A stock calms the vertical shake and a grip the sideways shake, by the build's own multipliers; the plain
    /// build (1, 1) is the data's shake, and the settle speeds never change.
    #[test]
    fn the_shot_shake_follows_the_recoil_multipliers() {
        let f = FeelData::embedded();
        let base = *f.shot("ar7_mako");
        assert_eq!(base.scaled(1.0, 1.0), base);
        let s = base.scaled(0.6, 0.55);
        assert!((s.pitch_deg - base.pitch_deg * 0.6).abs() < 1e-6 && (s.gun_pitch_deg - base.gun_pitch_deg * 0.6).abs() < 1e-6);
        assert!((s.back_m - base.back_m * 0.6).abs() < 1e-6 && (s.gun_back_m - base.gun_back_m * 0.6).abs() < 1e-6);
        assert!((s.yaw_deg - base.yaw_deg * 0.55).abs() < 1e-6 && (s.roll_deg - base.roll_deg * 0.55).abs() < 1e-6);
        assert_eq!((s.settle_hz, s.gun_settle_hz), (base.settle_hz, base.gun_settle_hz));
    }
}
