//! Screen and gun feel: the camera's step bob, landing dip and shot shake, and the gun's sway (breathing, drag
//! behind the view, step bob, landing dip), kick and sprint pose. Data in `feel.ron` ([`FeelData`]).
//!
//! All of it is a render-only offset in view space, applied on top of the view by `render::update_camera`
//! (like the visual punch): the simulation's view angles (`LocalControl` yaw / pitch, sent with each input) stay
//! the aim, so it never moves where bullets go. The camera's part follows the SCREEN SHAKE setting (0 % turns it
//! off); the gun's does not. Aiming quiets both, so the sight stays on the aim point.

use super::feel::{FeelData, Gait, GunGait, ShotFeel, Spring};
use crate::client::LocalControl;
use crate::config::Data;
use crate::settings::Settings;
use crate::shared::LocalShot;
use bevy::prelude::*;
use lightyear::prelude::*;
use std::f32::consts::{PI, TAU};
use vetf_net::*;
use vetf_sim::movement::{MoveMode, Stance};

/// A view-space offset: a shift (metres, +X right, +Y up, +Z back toward the eye) and a turn (degrees: pitch
/// up, yaw left, roll counter-clockwise).
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Offset {
    pub shift: Vec3,
    /// (pitch, yaw, roll) in degrees.
    pub turn: Vec3,
}

impl Offset {
    pub fn rotation(&self) -> Quat {
        Quat::from_euler(EulerRot::YXZ, self.turn.y.to_radians(), self.turn.x.to_radians(), self.turn.z.to_radians())
    }

    fn scaled(self, k: f32) -> Offset {
        Offset { shift: self.shift * k, turn: self.turn * k }
    }

    fn add(self, o: Offset) -> Offset {
        Offset { shift: self.shift + o.shift, turn: self.turn + o.turn }
    }

    /// The gun's pose (view space) moved by this offset: it turns about the eye by the pitch and yaw (trailing
    /// the view), rolls by the roll, then shifts. The roll cants the gun about its own barrel, or with
    /// `roll_about_eye` (the ADS blend) about the view axis instead: aimed, a cant about the barrel would swing the
    /// sight's reticle, which sits above the barrel, off the aim point.
    pub fn move_gun(&self, pose: Transform, roll_about_eye: f32) -> Transform {
        let swing = Quat::from_euler(EulerRot::YXZ, self.turn.y.to_radians(), self.turn.x.to_radians(), 0.0);
        let k = roll_about_eye.clamp(0.0, 1.0);
        let barrel = pose.rotation * Vec3::Z;
        let cant = Quat::from_axis_angle(barrel, (self.turn.z * (1.0 - k)).to_radians());
        let roll = Quat::from_rotation_z((self.turn.z * k).to_radians());
        Transform {
            translation: swing * (roll * pose.translation) + self.shift,
            rotation: swing * roll * cant * pose.rotation,
            scale: pose.scale,
        }
    }
}

/// What the feel needs from this frame.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FeelInput {
    pub dt: f32,
    /// Seconds since start-up (the breathing's clock).
    pub time: f32,
    /// Horizontal speed (m/s).
    pub speed: f32,
    /// On the ground on foot (not in the air, sliding, on the jetpack, a zipline or a mantle).
    pub grounded: bool,
    pub crouched: bool,
    pub vel_y: f32,
    /// How far down the gun should be (0..1): 1 while a sprint (an item, a mantle) lowers it, then the share of
    /// the simulation's bring-up still to go (`sprint_pose`), 0 once it can fire or while it is aimed.
    pub sprint: f32,
    /// ADS blend, 0 hip .. 1 aimed.
    pub ads: f32,
    /// The view (radians), for the gun's drag.
    pub yaw: f32,
    pub pitch: f32,
    /// movement.ron's walk, jog and sprint speeds.
    pub gaits: [f32; 3],
    /// SCREEN SHAKE, 0..1.
    pub shake: f32,
}

/// The feel's moving parts.
#[derive(Debug, Clone, Default)]
pub struct FeelState {
    /// Step phase: a footfall every half turn.
    phase: f32,
    bob: Gait,
    gun_bob: GunGait,
    started: bool,
    grounded: bool,
    last_vy: f32,
    last_look: Option<(f32, f32)>,
    land: [Spring; 2],
    gun_land: [Spring; 2],
    /// Camera: pitch, yaw, roll, back; the gun's settle speed of the last shot.
    shot: [Spring; 4],
    shot_hz: f32,
    /// Gun: back, pitch.
    kick: [Spring; 2],
    kick_hz: f32,
    /// Gun drag: pitch, yaw (degrees the gun trails the view by).
    drag: [Spring; 2],
    sprint: f32,
}

/// This frame's offsets.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Feel {
    pub camera: Offset,
    pub gun: Offset,
    /// How far the gun is in its sprint pose (0..1).
    pub sprint: f32,
    /// The ADS blend the gun's offset was made for: aimed, its roll turns about the view axis
    /// ([`Offset::move_gun`]).
    pub ads: f32,
}

/// Which two gaits a speed lies between and how far, and how much of the slowest gait shows below its speed.
fn gait_mix(gaits: [f32; 3], speed: f32) -> (usize, f32, f32) {
    let [walk, jog, sprint] = gaits;
    if speed < walk {
        (0, 0.0, (speed / walk.max(0.01)).clamp(0.0, 1.0))
    } else if speed < jog {
        (0, (speed - walk) / (jog - walk).max(0.01), 1.0)
    } else if speed < sprint {
        (1, (speed - jog) / (sprint - jog).max(0.01), 1.0)
    } else {
        (1, 1.0, 1.0)
    }
}

/// The head's bob at `speed` (amplitudes fade out below walking speed; the rhythm stays the walk's).
pub fn camera_gait(feel: &FeelData, gaits: [f32; 3], speed: f32) -> Gait {
    let c = &feel.camera;
    let g = [c.walk, c.jog, c.sprint];
    let (i, t, k) = gait_mix(gaits, speed);
    Gait::lerp(g[i], g[i + 1], t).scaled(k)
}

fn gun_gait(feel: &FeelData, gaits: [f32; 3], speed: f32) -> GunGait {
    let f = &feel.gun;
    let g = [f.walk, f.jog, f.sprint];
    let (i, t, k) = gait_mix(gaits, speed);
    let b = GunGait::lerp(g[i], g[i + 1], t);
    GunGait { side_m: b.side_m * k, up_m: b.up_m * k, roll_deg: b.roll_deg * k, pitch_deg: b.pitch_deg * k }
}

/// A repeatable 0..1 value per shot (seq) and purpose (salt): the shake's random yaw and roll.
fn noise(seq: u32, salt: u32) -> f32 {
    let mut x = seq.wrapping_mul(0x9E37_79B9) ^ salt.wrapping_mul(0x85EB_CA6B);
    x ^= x >> 15;
    x = x.wrapping_mul(0x2C1B_3C6D);
    x ^= x >> 12;
    (x & 0xFFFF) as f32 / 65535.0
}

/// A signed share of an amplitude: half to all of it, either way.
fn signed(seq: u32, salt: u32) -> f32 {
    let n = noise(seq, salt);
    let mag = 0.5 + 0.5 * noise(seq, salt ^ 0x51ED);
    if n < 0.5 { -mag } else { mag }
}

fn ease(dt: f32, tau: f32) -> f32 {
    if tau <= 0.0 { 1.0 } else { 1.0 - (-dt / tau).exp() }
}

impl FeelState {
    /// Forget everything (dead, respawned): the next frame starts from rest.
    pub fn reset(&mut self) {
        *self = FeelState::default();
    }

    /// One frame: this frame's shots (their feel and shot number), then the offsets.
    pub fn step(&mut self, feel: &FeelData, input: &FeelInput, shots: &[(ShotFeel, u32)]) -> Feel {
        let dt = input.dt.max(0.0);
        let (c, g) = (&feel.camera, &feel.gun);
        let ads = input.ads.clamp(0.0, 1.0);

        // Landing: the fall speed of the last frame in the air.
        if !self.started {
            self.started = true;
            self.grounded = input.grounded;
        }
        if input.grounded && !self.grounded {
            let fall = (-self.last_vy).max(0.0);
            if let Some((dip, nod)) = c.land.kick(fall) {
                self.land[0].kick(-dip, c.land.spring.hz, c.land.spring.damping);
                self.land[1].kick(-nod, c.land.spring.hz, c.land.spring.damping);
            }
            if let Some((dip, nod)) = g.land.kick(fall) {
                self.gun_land[0].kick(-dip, g.land.spring.hz, g.land.spring.damping);
                self.gun_land[1].kick(-nod, g.land.spring.hz, g.land.spring.damping);
            }
        }
        self.grounded = input.grounded;
        if !input.grounded {
            self.last_vy = input.vel_y;
        }

        // Shots.
        for (s, seq) in shots {
            self.shot_hz = s.settle_hz;
            let z = c.shot_damping;
            self.shot[0].kick(s.pitch_deg, s.settle_hz, z);
            self.shot[1].kick(s.yaw_deg * signed(*seq, 1), s.settle_hz, z);
            self.shot[2].kick(s.roll_deg * signed(*seq, 2), s.settle_hz, z);
            self.shot[3].kick(s.back_m, s.settle_hz, z);
            self.kick_hz = s.gun_settle_hz;
            self.kick[0].kick(s.gun_back_m, s.gun_settle_hz, g.kick_damping);
            self.kick[1].kick(s.gun_pitch_deg, s.gun_settle_hz, g.kick_damping);
        }

        // The gun trails the view: it keeps `lag` of each turn, then springs back. A jump (a respawn) is no turn.
        if let Some((yaw, pitch)) = self.last_look {
            let d_yaw = ((input.yaw - yaw + PI).rem_euclid(TAU) - PI).to_degrees();
            let d_pitch = (input.pitch - pitch).to_degrees();
            if d_yaw.abs() < 45.0 && d_pitch.abs() < 45.0 {
                let max = g.drag.max_deg;
                self.drag[0].x = (self.drag[0].x - d_pitch * g.drag.lag).clamp(-max, max);
                self.drag[1].x = (self.drag[1].x - d_yaw * g.drag.lag).clamp(-max, max);
            }
        }
        self.last_look = Some((input.yaw, input.pitch));

        // Springs settle.
        for s in &mut self.land {
            s.step(c.land.spring.hz, c.land.spring.damping, dt);
        }
        for s in &mut self.gun_land {
            s.step(g.land.spring.hz, g.land.spring.damping, dt);
        }
        for s in &mut self.shot {
            s.step(self.shot_hz.max(0.1), c.shot_damping, dt);
        }
        for s in &mut self.kick {
            s.step(self.kick_hz.max(0.1), g.kick_damping, dt);
        }
        for s in &mut self.drag {
            s.step(g.drag.spring.hz, g.drag.spring.damping, dt);
        }

        // Step bob: eased toward this gait, on the ground only.
        let on_foot = if input.grounded { if input.crouched { c.crouch_mult } else { 1.0 } } else { 0.0 };
        let target = camera_gait(feel, input.gaits, input.speed);
        let target = Gait { step_hz: target.step_hz, ..target.scaled(on_foot) };
        let gun_target = gun_gait(feel, input.gaits, input.speed);
        let k = ease(dt, c.ease_s);
        self.bob = Gait::lerp(self.bob, target, k);
        let gun_target = GunGait {
            side_m: gun_target.side_m * on_foot,
            up_m: gun_target.up_m * on_foot,
            roll_deg: gun_target.roll_deg * on_foot,
            pitch_deg: gun_target.pitch_deg * on_foot,
        };
        self.gun_bob = GunGait::lerp(self.gun_bob, gun_target, k);
        self.phase = (self.phase + PI * self.bob.step_hz * dt).rem_euclid(TAU);
        let (side, step) = (self.phase.sin(), (2.0 * self.phase).cos());
        // Down: eased. Up: with the simulation's bring-up, so the gun is up on the tick it can fire (eased, it
        // came up only after the first shots had left it).
        let target = input.sprint.clamp(0.0, 1.0);
        if target > self.sprint {
            self.sprint += (target - self.sprint) * ease(dt, g.sprint_pose.ease_s);
        } else {
            self.sprint = target;
        }

        // The camera.
        let b = self.bob;
        let bob = Offset {
            shift: Vec3::new(b.side_m * side, b.up_m * step, 0.0),
            turn: Vec3::new(b.pitch_deg * step, b.yaw_deg * side, b.roll_deg * side),
        };
        let land = Offset { shift: Vec3::Y * self.land[0].x, turn: Vec3::X * self.land[1].x };
        let calm = |a: f32| 1.0 + (a - 1.0) * ads;
        let (turn_k, shift_k) = (calm(c.ads_turn_mult), calm(c.ads_shift_mult));
        let walk = bob.add(land);
        let shot =
            Offset { shift: Vec3::Z * self.shot[3].x, turn: Vec3::new(self.shot[0].x, self.shot[1].x, self.shot[2].x) }
                .scaled(calm(c.ads_shot_mult));
        let shake = input.shake.clamp(0.0, 1.0);
        let camera = Offset { shift: walk.shift * shift_k, turn: walk.turn * turn_k }.add(shot).scaled(shake);

        // The gun.
        let w = TAU / g.breath.period_s.max(0.1);
        let t = input.time;
        let breath = Offset {
            shift: Vec3::new((w * t).sin(), 0.5 * (2.0 * w * t).sin(), 0.0) * g.breath.shift_m,
            turn: Vec3::new(0.5 * (2.0 * w * t).sin(), 0.5 * (w * t).sin(), 0.0) * g.breath.turn_deg,
        };
        let (dp, dy) = (self.drag[0].x, self.drag[1].x);
        let drag = Offset {
            shift: Vec3::new(-dy, dp, 0.0) * g.drag.shift_m_per_deg,
            turn: Vec3::new(dp, dy, -dy * g.drag.roll_per_deg),
        };
        let gb = self.gun_bob;
        let gun_bob = Offset {
            shift: Vec3::new(-gb.side_m * side, gb.up_m * step, 0.0),
            turn: Vec3::new(gb.pitch_deg * step, 0.0, gb.roll_deg * side),
        };
        let gun_land = Offset { shift: Vec3::Y * self.gun_land[0].x, turn: Vec3::X * self.gun_land[1].x };
        let kick = Offset { shift: Vec3::Z * self.kick[0].x, turn: Vec3::X * self.kick[1].x };
        // Aimed, the sway turns the gun a little but does not slide it across the view (that carried the reticle
        // a degree or more off the aim point).
        let sway = breath.add(drag).add(gun_bob).add(gun_land);
        let (turn_k, across_k) = (calm(g.ads_mult), calm(g.ads_shift_mult));
        let sway = Offset {
            shift: Vec3::new(sway.shift.x * across_k, sway.shift.y * across_k, sway.shift.z * turn_k),
            turn: sway.turn * turn_k,
        };
        let gun = sway.add(kick.scaled(calm(g.ads_kick_mult)));

        Feel { camera, gun, sprint: self.sprint, ads }
    }
}

/// This frame's feel, for `render::update_camera`.
#[derive(Resource, Debug, Clone, Default)]
pub struct ViewFeel {
    pub now: Feel,
    state: FeelState,
}

/// How far down the gun should be (0..1) from the simulation's weapon: lowered while `sprint_lock` is full
/// (the sim sets it full every tick a sprint lowers the gun), then the share of the bring-up (`full` ticks) still
/// to go, counted down smoothly between ticks (`overstep`, 0..1 of a tick), and 0 while aimed.
pub fn sprint_target(sprint_lock: u16, full: u16, ads: f32, overstep: f32) -> f32 {
    if ads > 0.0 || sprint_lock == 0 {
        return 0.0;
    }
    let full = full.max(1) as f32;
    let left = sprint_lock as f32;
    if left >= full { 1.0 } else { ((left - overstep.clamp(0.0, 1.0)) / full).clamp(0.0, 1.0) }
}

/// Steps the feel from our player and this frame's shots (`LocalShot`, the same shots that kick the view).
#[allow(clippy::too_many_arguments)]
pub(crate) fn step_feel(
    time: Res<Time>,
    fixed: Res<Time<Fixed>>,
    feel: Res<FeelData>,
    data: Res<Data>,
    settings: Res<Settings>,
    control: Res<LocalControl>,
    ads: Res<super::SmoothedAds>,
    mut shots: MessageReader<LocalShot>,
    me: Query<(&PlayerMove, &PlayerWeapon, &PlayerLoadout, &Vitals), With<Controlled>>,
    mut view: ResMut<ViewFeel>,
) {
    let fired: Vec<u32> = shots.read().map(|s| s.shot.seq).collect();
    let Some((mv, weapon, loadout, vitals)) = me.iter().next() else { return };
    if vitals.health.dead {
        view.state.reset();
        view.now = Feel::default();
        return;
    }
    let spec = loadout.0.weapon.spec(&data);
    let shot = *feel.shot(&spec.id);
    let shots: Vec<(ShotFeel, u32)> = fired.into_iter().map(|seq| (shot, seq)).collect();
    let m = &mv.0;
    let speeds = &data.movement.speed;
    let w = &weapon.0;
    let bring_up =
        vetf_sim::weapon::secs_to_ticks(spec.sprint_to_fire_s * loadout.0.weapon.mods.sprint_to_fire, data.net.tick_hz);
    let input = FeelInput {
        dt: time.delta_secs(),
        time: time.elapsed_secs(),
        speed: m.horizontal_speed(),
        grounded: m.mode == MoveMode::Ground,
        crouched: m.stance != Stance::Stand,
        vel_y: m.vel.y,
        sprint: sprint_target(w.sprint_lock, bring_up, w.ads, fixed.overstep_fraction()),
        ads: ads.at(fixed.overstep_fraction()),
        yaw: control.yaw,
        pitch: control.pitch,
        gaits: [speeds.walk, speeds.jog, speeds.sprint],
        shake: settings.hud.screen_shake / 100.0,
    };
    let ViewFeel { now, state } = &mut *view;
    *now = state.step(&feel, &input, &shots);
}

#[cfg(test)]
mod tests {
    use super::*;

    const GAITS: [f32; 3] = [2.6, 4.8, 7.0];

    fn input(speed: f32) -> FeelInput {
        FeelInput {
            dt: 1.0 / 120.0,
            time: 0.0,
            speed,
            grounded: true,
            crouched: false,
            vel_y: 0.0,
            sprint: if speed >= GAITS[2] { 1.0 } else { 0.0 },
            ads: 0.0,
            yaw: 0.0,
            pitch: 0.0,
            gaits: GAITS,
            shake: 1.0,
        }
    }

    /// Runs `secs` at 120 fps (shots at `shots`' times) and returns the largest camera and gun offsets seen
    /// (shift length, turn length) in the second half, so easing in is over.
    fn run(feel: &FeelData, base: FeelInput, secs: f32, shots: &[(f32, ShotFeel)]) -> (Vec2, Vec2, FeelState) {
        let mut s = FeelState::default();
        let (mut cam, mut gun) = (Vec2::ZERO, Vec2::ZERO);
        let frames = (secs / base.dt) as usize;
        for f in 0..frames {
            let t = f as f32 * base.dt;
            let now: Vec<(ShotFeel, u32)> =
                shots.iter().filter(|(at, _)| (*at - t).abs() < base.dt * 0.5).map(|(_, s)| (*s, f as u32)).collect();
            let out = s.step(feel, &FeelInput { time: t, ..base }, &now);
            if f >= frames / 2 || !shots.is_empty() {
                cam = cam.max(Vec2::new(out.camera.shift.length(), out.camera.turn.length()));
                gun = gun.max(Vec2::new(out.gun.shift.length(), out.gun.turn.length()));
            }
        }
        (cam, gun, s)
    }

    #[test]
    fn sprinting_wobbles_more_than_jogging_and_walking_and_standing_is_still() {
        let feel = FeelData::embedded();
        let (still, ..) = run(feel, input(0.0), 2.0, &[]);
        assert!(still.length() < 1e-5, "standing still: no camera bob {still}");
        let (walk, ..) = run(feel, input(GAITS[0]), 2.0, &[]);
        let (jog, ..) = run(feel, input(GAITS[1]), 2.0, &[]);
        let (sprint, gun_sprint, _) = run(feel, input(GAITS[2]), 2.0, &[]);
        assert!(walk.y > 0.0 && walk.y < jog.y && jog.y < sprint.y, "{walk} {jog} {sprint}");
        assert!(sprint.y < 1.0 && sprint.x < 0.03, "subtle: {sprint}");
        // In the air there is no step bob.
        let (air, ..) = run(feel, FeelInput { grounded: false, ..input(GAITS[2]) }, 2.0, &[]);
        assert!(air.length() < 1e-4, "{air}");
        let (crouch, ..) = run(feel, FeelInput { crouched: true, ..input(GAITS[1]) }, 2.0, &[]);
        assert!(crouch.y < jog.y);
        assert!(gun_sprint.y > 0.5, "the gun bobs too: {gun_sprint}");
    }

    #[test]
    fn screen_shake_zero_turns_the_camera_feel_off_but_not_the_gun() {
        let feel = FeelData::embedded();
        let shot = *feel.shot("vk50_warden");
        let off = FeelInput { shake: 0.0, ..input(GAITS[2]) };
        let (cam, gun, _) = run(feel, off, 1.0, &[(0.5, shot)]);
        assert_eq!(cam, Vec2::ZERO, "SCREEN SHAKE 0 %: no bob, no shake");
        assert!(gun.y > 0.0, "the gun still sways and kicks");
        let (half, ..) = run(feel, FeelInput { shake: 0.5, ..off }, 1.0, &[(0.5, shot)]);
        let (full, ..) = run(feel, FeelInput { shake: 1.0, ..off }, 1.0, &[(0.5, shot)]);
        assert!((half.y - full.y * 0.5).abs() < 1e-4, "{half} {full}");
    }

    #[test]
    fn each_gun_shakes_by_its_own_numbers() {
        let feel = FeelData::embedded();
        let peak = |id: &str| {
            let (cam, gun, _) = run(feel, input(0.0), 0.6, &[(0.1, *feel.shot(id))]);
            (cam.y, gun.y)
        };
        let (smg, ar, sniper) = (peak("sk9_skink"), peak("ar7_mako"), peak("vk50_warden"));
        assert!(smg.0 < ar.0 && ar.0 < sniper.0, "camera: {smg:?} {ar:?} {sniper:?}");
        assert!(smg.1 < ar.1 && ar.1 < sniper.1, "gun: {smg:?} {ar:?} {sniper:?}");
        // The Warden's jolt is about its data's pitch (plus the random yaw and roll).
        let w = feel.shot("vk50_warden");
        assert!(sniper.0 >= w.pitch_deg * 0.9 && sniper.0 < (w.pitch_deg + w.yaw_deg + w.roll_deg) * 1.2);
        // A shot's shake settles: a second after it, the camera is back.
        let mut s = FeelState::default();
        let shot = [(*w, 1)];
        s.step(feel, &input(0.0), &shot);
        let mut last = Feel::default();
        for _ in 0..240 {
            last = s.step(feel, &input(0.0), &[]);
        }
        assert!(last.camera.turn.length() < 0.02 && last.gun.shift.length() < 0.002, "{last:?}");
        // The SMG's settles faster than the Warden's (the last frame still off by more than 0.01 degrees).
        let settle = |id: &str| {
            let mut s = FeelState::default();
            s.step(feel, &input(0.0), &[(*feel.shot(id), 1)]);
            let mut last = 0;
            for f in 0..600 {
                if s.step(feel, &input(0.0), &[]).camera.turn.length() > 0.01 {
                    last = f;
                }
            }
            last
        };
        assert!(settle("sk9_skink") < settle("ar7_mako") && settle("ar7_mako") < settle("vk50_warden"));
    }

    #[test]
    fn aiming_keeps_the_sight_on_the_aim_point() {
        let feel = FeelData::embedded();
        let aimed = FeelInput { ads: 1.0, sprint: 0.0, ..input(GAITS[1]) };
        let (cam, gun, _) = run(feel, aimed, 2.0, &[]);
        assert!(cam.y < 1e-5, "aimed, the bob does not turn the camera: {cam}");
        let (hip_cam, hip_gun, _) = run(feel, FeelInput { ads: 0.0, ..aimed }, 2.0, &[]);
        assert!(cam.x < hip_cam.x * 0.5);
        assert!(gun.y < hip_gun.y * 0.15 && gun.x < hip_gun.x * 0.15, "aimed {gun} hip {hip_gun}");
    }

    #[test]
    fn the_gun_trails_a_turn_and_settles() {
        let feel = FeelData::embedded();
        let mut s = FeelState::default();
        let mut i = input(0.0);
        s.step(feel, &i, &[]);
        // Turn right (yaw goes down) at 180 deg/s for a quarter second.
        let mut during = Feel::default();
        for _ in 0..30 {
            i.yaw -= PI / 120.0;
            during = s.step(feel, &i, &[]);
        }
        assert!(during.gun.turn.y > 0.5, "the muzzle lags to the left: {:?}", during.gun.turn);
        assert!(during.gun.turn.y <= feel.gun.drag.max_deg + 0.5, "never further than max_deg");
        assert!(during.gun.turn.z < 0.0, "canted into the turn");
        for _ in 0..240 {
            during = s.step(feel, &i, &[]);
        }
        assert!(during.gun.turn.y.abs() < 0.05, "settled: {:?}", during.gun.turn);
        // A respawn's jump in yaw is not a turn.
        i.yaw += 2.0;
        assert!(s.step(feel, &i, &[]).gun.turn.y.abs() < 0.1);
        // The drag never reaches the camera.
        assert_eq!(during.camera.turn.y, 0.0);
    }

    #[test]
    fn a_hard_landing_dips_the_view_and_the_gun() {
        let feel = FeelData::embedded();
        let mut s = FeelState::default();
        let air = FeelInput { grounded: false, vel_y: -9.0, ..input(0.0) };
        for _ in 0..10 {
            s.step(feel, &air, &[]);
        }
        let mut low = Vec2::ZERO;
        for _ in 0..60 {
            let out = s.step(feel, &input(0.0), &[]);
            low = low.min(Vec2::new(out.camera.shift.y, out.gun.shift.y));
        }
        assert!(low.x < -0.01 && low.y < -0.02, "{low}");
        assert!(low.x >= -feel.camera.land.max_dip_m * 1.1);
    }

    #[test]
    fn the_feel_is_the_same_at_any_frame_rate() {
        let feel = FeelData::embedded();
        let shot = *feel.shot("ar7_mako");
        let at = |fps: f32| {
            let base = FeelInput { dt: 1.0 / fps, ..input(GAITS[2]) };
            let (sprint, sprint_gun, _) = run(feel, base, 2.0, &[]);
            let (kick, kick_gun, _) = run(feel, FeelInput { dt: 1.0 / fps, ..input(0.0) }, 0.6, &[(0.1, shot)]);
            [sprint.y, sprint_gun.x, kick.y, kick_gun.x]
        };
        let (a, b) = (at(60.0), at(240.0));
        for (x, y) in a.iter().zip(b) {
            assert!((x - y).abs() <= 0.08 * y.abs(), "60 fps {a:?} vs 240 fps {b:?}");
        }
    }

    #[test]
    fn the_sprint_pose_eases_in_and_out() {
        let feel = FeelData::embedded();
        let mut s = FeelState::default();
        let sprint = input(GAITS[2]);
        let first = s.step(feel, &sprint, &[]).sprint;
        assert!(first > 0.0 && first < 0.5, "no snap: {first}");
        for _ in 0..60 {
            s.step(feel, &sprint, &[]);
        }
        assert!(s.step(feel, &sprint, &[]).sprint > 0.99);
        // Coming up follows the simulation's bring-up: on its last tick the gun is up.
        let up = FeelInput { sprint: 0.5, ..sprint };
        assert_eq!(s.step(feel, &up, &[]).sprint, 0.5, "half the bring-up left: half down");
        let ready = FeelInput { sprint: 0.0, ..sprint };
        assert_eq!(s.step(feel, &ready, &[]).sprint, 0.0, "the gun can fire: it is up");
    }

    /// Finding sprint-pose-ease-lags-gun-up: sprint with the trigger held, then let the sim bring the gun up. On
    /// the frame of the first shot (the tick `sprint_lock` reaches 0) the pose is 0, never still lowered.
    #[test]
    fn the_gun_is_up_when_the_first_shot_leaves() {
        let feel = FeelData::embedded();
        let mut s = FeelState::default();
        let full = 12; // the Mako: 0.2 s at 60 Hz
        let base = input(GAITS[2]);
        for _ in 0..60 {
            s.step(feel, &FeelInput { sprint: sprint_target(full, full, 0.0, 0.0), ..base }, &[]);
        }
        let mut last = 1.0;
        // 4 frames a tick (240 fps), the lock counting down from full
        for lock in (0..full).rev() {
            for f in 0..4 {
                let t = sprint_target(lock, full, 0.0, f as f32 / 4.0);
                let out = s.step(feel, &FeelInput { sprint: t, ..base }, &[]);
                assert!(out.sprint <= last + 1e-6, "it only comes up");
                last = out.sprint;
            }
        }
        let first_shot = s.step(feel, &FeelInput { sprint: sprint_target(0, full, 0.0, 0.0), ..base }, &[]);
        assert_eq!(first_shot.sprint, 0.0);
        // Aiming takes over at once.
        assert_eq!(sprint_target(full, full, 0.3, 0.0), 0.0);
        assert_eq!(sprint_target(full, full, 0.0, 0.7), 1.0, "lowered: all the way down");
    }

    /// Finding ads-sway-moves-reticle-off-aim: aimed, the sway may turn the gun a little, but the sight's reticle
    /// (on the view axis a few centimetres ahead) never slides off it by more than that turn: a sprint bob, a full
    /// drag after a flick and a hard landing.
    #[test]
    fn aimed_the_reticle_moves_only_by_the_sways_turn() {
        let feel = FeelData::embedded();
        // the aimed pose: the gun under the eye, the reticle 5 cm ahead on the view axis
        let pose = Transform::from_xyz(0.0, -0.075, -0.3).with_rotation(Quat::from_rotation_y(PI));
        let reticle = pose.compute_affine().inverse().transform_point3(Vec3::NEG_Z * 0.05);
        let off_axis = |out: &Feel| {
            let t = out.gun.move_gun(pose, out.ads);
            let r = t.compute_affine().transform_point3(reticle);
            r.angle_between(Vec3::NEG_Z).to_degrees()
        };
        let turn = |out: &Feel| Vec2::new(out.gun.turn.x, out.gun.turn.y).length();
        let check = |what: &str, out: &Feel| {
            let (off, turn) = (off_axis(out), turn(out));
            assert!(off <= turn + 0.02, "{what}: the reticle is {off:.3} deg off for a {turn:.3} deg turn");
            assert!(off < 0.4, "{what}: {off:.3} deg");
        };
        // a sprint's bob, aimed
        let mut s = FeelState::default();
        let aimed = FeelInput { ads: 1.0, sprint: 0.0, ..input(GAITS[2]) };
        for f in 0..480 {
            let out = s.step(feel, &FeelInput { time: f as f32 / 120.0, ..aimed }, &[]);
            check("sprint bob", &out);
        }
        // a flick: the drag at its cap
        let mut s = FeelState::default();
        let mut i = FeelInput { ads: 1.0, ..input(0.0) };
        for _ in 0..30 {
            i.yaw -= PI / 60.0;
            let out = s.step(feel, &i, &[]);
            check("full drag", &out);
        }
        // a hard landing
        let mut s = FeelState::default();
        for _ in 0..10 {
            s.step(feel, &FeelInput { grounded: false, vel_y: -12.0, ..i }, &[]);
        }
        for _ in 0..90 {
            let out = s.step(feel, &FeelInput { grounded: true, ..i }, &[]);
            check("hard landing", &out);
        }
    }

    /// The gun turns about the eye (trailing the view) and cants about its barrel; a zero offset leaves it be.
    #[test]
    fn an_offset_moves_the_gun_about_the_eye() {
        let pose = Transform::from_xyz(0.16, -0.2, -0.32).with_rotation(Quat::from_rotation_y(PI));
        assert!(Offset::default().move_gun(pose, 0.0).translation.abs_diff_eq(pose.translation, 1e-6));
        let left = Offset { turn: Vec3::new(0.0, 5.0, 0.0), ..default() }.move_gun(pose, 0.0);
        assert!(left.translation.x < pose.translation.x, "yaw left swings it left");
        assert!((left.translation.length() - pose.translation.length()).abs() < 1e-5, "about the eye");
        let cant = Offset { turn: Vec3::new(0.0, 0.0, 10.0), ..default() }.move_gun(pose, 0.0);
        assert!(cant.translation.abs_diff_eq(pose.translation, 1e-6), "a cant turns it in place");
        assert!((cant.rotation * Vec3::Z).abs_diff_eq(pose.rotation * Vec3::Z, 1e-5), "about its barrel");
        // aimed, the roll turns it about the view axis: a point on that axis stays on it
        let aimed = Offset { turn: Vec3::new(0.0, 0.0, 10.0), ..default() }.move_gun(pose, 1.0);
        let on_axis = pose.compute_affine().inverse().transform_point3(Vec3::NEG_Z * 0.05);
        let moved = aimed.compute_affine().transform_point3(on_axis);
        assert!(moved.abs_diff_eq(Vec3::NEG_Z * 0.05, 1e-5), "{moved}");
    }
}
