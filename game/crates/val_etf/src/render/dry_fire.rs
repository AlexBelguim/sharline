//! The empty gun, seen: with the loud dry click (`sound`'s [`crate::sound::DryFire`]) each empty trigger pull
//! twitches the gun in the hands (the trigger finger's jolt, no recoil), and a few empty pulls in a row get a short
//! frustrated shake of the gun, so the player sees at once that the magazine is out. No HUD text (user direction:
//! "maybe make it do an animation so players see fast that their ammo is up", "maybe a gun shake out of
//! frustration maybe after 3 or 4 tries?"). Visual only (`feel.ron` gun.dry_fire), like the rest of the feel.
//!
//! The pulls come from the dry click itself ([`DryPull`], sent by `sound` when it plays one), so the twitch and
//! the click always go together. Others see the shake on the gun in that player's hand.

use super::feel::{DryFireFeel, FeelData, Spring};
use crate::client::LocalControl;
use bevy::prelude::*;
use lightyear::prelude::*;
use std::f32::consts::TAU;
use vetf_net::*;
use vetf_sim::input::Buttons;
use vetf_sim::weapon::{WeaponAction, WeaponState};

/// A trigger pull on an empty gun that clicked: the player whose gun it is (`sound` sends one per dry click).
#[derive(Message, Debug, Clone, Copy, PartialEq, Eq)]
pub struct DryPull {
    pub player: Entity,
}

/// What the gun is doing that stops the frustrated shake.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Stop {
    /// Aiming (or the gun still coming down from the sights): the shake stops; the count stays.
    Aim,
    /// A reload or a swap (the gun coming up): the shake stops and the count starts again.
    Reset,
}

/// What stops the shake now: a reload or a swap, else aiming (`ads_held`: the aim key is down).
pub fn stop_of(w: &WeaponState, ads_held: bool) -> Option<Stop> {
    match w.action {
        WeaponAction::Reloading { .. } | WeaponAction::Equipping { .. } => Some(Stop::Reset),
        _ if ads_held || w.ads > 0.0 => Some(Stop::Aim),
        _ => None,
    }
}

/// One gun's twitch and frustration: the empty pulls in a row, the twitch's spring and the shake's clock.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct DryFx {
    /// Empty pulls in a row since the count last started.
    pulls: u32,
    /// Seconds since the last empty pull.
    since_pull: f32,
    twitch: Spring,
    /// Seconds into the frustrated shake, while it runs.
    shake: Option<f32>,
    /// Seconds since the shake was stopped, while it fades out.
    fading: Option<f32>,
}

impl DryFx {
    /// An empty pull clicked: the gun twitches, and the count goes up (starting again after a pause of
    /// `reset_after_s`). The pull that brings it to `shake_after_pulls` starts the shake, unless the player is
    /// aiming; then the next pull without aiming does. Returns whether the shake started.
    pub fn pull(&mut self, f: &DryFireFeel, aiming: bool) -> bool {
        self.twitch.kick(1.0, f.twitch.hz, f.twitch.damping);
        if self.since_pull > f.reset_after_s {
            self.pulls = 0;
        }
        self.since_pull = 0.0;
        self.pulls += 1;
        if self.pulls >= f.shake_after_pulls.max(1) && !aiming && !self.shaking() {
            self.pulls = 0;
            self.shake = Some(0.0);
            self.fading = None;
            return true;
        }
        false
    }

    /// Stops the shake (it fades out over `cancel_s`); a reset also starts the count again.
    pub fn stop(&mut self, why: Stop) {
        if why == Stop::Reset {
            self.pulls = 0;
        }
        if self.shake.is_some() && self.fading.is_none() {
            self.fading = Some(0.0);
        }
    }

    /// The shake is running (and not fading out).
    pub fn shaking(&self) -> bool {
        self.shake.is_some() && self.fading.is_none()
    }

    /// Empty pulls counted toward the shake.
    #[cfg(test)]
    pub fn pulls(&self) -> u32 {
        self.pulls
    }

    /// Advance by `dt` seconds.
    pub fn step(&mut self, f: &DryFireFeel, dt: f32) {
        let dt = dt.max(0.0);
        self.since_pull += dt;
        self.twitch.step(f.twitch.hz, f.twitch.damping, dt);
        if let Some(t) = self.shake.as_mut() {
            *t += dt;
            if *t >= f.shake_s {
                self.shake = None;
                self.fading = None;
            }
        }
        if let Some(t) = self.fading.as_mut() {
            *t += dt;
            if *t >= f.cancel_s {
                self.shake = None;
                self.fading = None;
            }
        }
    }

    /// The gun's offset now: a shift (view axes, metres) and a turn about the grip (pitch, yaw, roll in degrees;
    /// pitch up, yaw left, roll counter-clockwise are positive).
    pub fn offset(&self, f: &DryFireFeel) -> (Vec3, Vec3) {
        let tw = self.twitch.x;
        let mut shift = Vec3::new(0.0, -f.twitch_down_m * tw, 0.0);
        let mut turn = Vec3::new(-f.twitch_pitch_deg * tw, 0.0, 0.0);
        if let Some(t) = self.shake {
            let k = match self.fading {
                Some(s) if f.cancel_s > 0.0 => (1.0 - s / f.cancel_s).clamp(0.0, 1.0),
                Some(_) => 0.0,
                None => 1.0,
            };
            let u = if f.shake_s > 0.0 { (t / f.shake_s).clamp(0.0, 1.0) } else { 1.0 };
            let tail = (1.0 - u) * (1.0 - u);
            // The smack: down to its deepest `smack_s` in, then back.
            let x = if f.smack_s > 0.0 { t / f.smack_s } else { 0.0 };
            let smack = x * (1.0 - x).exp() * (1.0 - u) * k;
            // The rattle: comes in over the smack, dies away to nothing at the end.
            let rise = if f.smack_s > 0.0 { smooth(t / (2.0 * f.smack_s)) } else { 1.0 };
            let env = rise * tail * k;
            let phase = TAU * f.shake_hz * t;
            shift.y -= f.smack_down_m * smack;
            turn.x -= f.smack_pitch_deg * smack;
            turn.y += f.shake_yaw_deg * phase.cos() * env;
            turn.z += f.shake_roll_deg * phase.sin() * env;
        }
        (shift, turn)
    }
}

fn smooth(x: f32) -> f32 {
    let s = x.clamp(0.0, 1.0);
    s * s * (3.0 - 2.0 * s)
}

fn turn_quat(turn_deg: Vec3) -> Quat {
    Quat::from_euler(EulerRot::YXZ, turn_deg.y.to_radians(), turn_deg.x.to_radians(), turn_deg.z.to_radians())
}

/// The first-person gun's pose (view space) with the twitch and shake: shifted, then turned about the grip.
pub fn view_gun(f: &DryFireFeel, pose: Transform, fx: &DryFx) -> Transform {
    let (shift, turn) = fx.offset(f);
    if shift == Vec3::ZERO && turn == Vec3::ZERO {
        return pose;
    }
    Transform { translation: pose.translation + shift, rotation: turn_quat(turn) * pose.rotation, scale: pose.scale }
}

/// The turn of a gun in another player's hand (its own axes, about the grip), `third_person_mult` of the view's.
pub fn held_turn(f: &DryFireFeel, fx: &DryFx) -> Quat {
    let (_, turn) = fx.offset(f);
    turn_quat(turn * f.third_person_mult)
}

/// Our own gun's twitch and shake, for `render::update_camera`.
#[derive(Resource, Debug, Clone, Default)]
pub struct ViewDryFire {
    pub fx: DryFx,
}

/// Another player's gun's twitch and shake (on their player entity), for `render::update_player_visuals`.
#[derive(Component, Debug, Clone, Copy, Default)]
pub struct HeldDryFire(pub DryFx);

/// Steps our own gun's twitch and shake from our dry clicks, the aim key and our predicted weapon.
pub(crate) fn step_view_dry_fire(
    time: Res<Time>,
    feel: Res<FeelData>,
    control: Res<LocalControl>,
    mut pulls: MessageReader<DryPull>,
    me: Query<(Entity, &PlayerWeapon, &Vitals), With<Controlled>>,
    mut view: ResMut<ViewDryFire>,
) {
    let f = &feel.gun.dry_fire;
    let Some((entity, weapon, vitals)) = me.iter().next() else {
        pulls.clear();
        return;
    };
    if vitals.health.dead {
        pulls.clear();
        view.fx = DryFx::default();
        return;
    }
    let stop = stop_of(&weapon.0, Buttons(control.held).held(Buttons::ADS));
    for _ in pulls.read().filter(|p| p.player == entity) {
        view.fx.pull(f, stop.is_some());
    }
    if let Some(why) = stop {
        view.fx.stop(why);
    }
    view.fx.step(f, time.delta_secs());
}

/// Steps the twitch and shake of everyone else's gun, from their dry clicks and their replicated weapon.
#[allow(clippy::type_complexity)]
pub(crate) fn step_held_dry_fire(
    mut commands: Commands,
    time: Res<Time>,
    feel: Res<FeelData>,
    mut pulls: MessageReader<DryPull>,
    mut players: Query<(Entity, &PlayerWeapon, Option<&Vitals>, Option<&mut HeldDryFire>), Without<Controlled>>,
) {
    let f = &feel.gun.dry_fire;
    let dt = time.delta_secs();
    let pulled: Vec<Entity> = pulls.read().map(|p| p.player).collect();
    for (e, weapon, vitals, fx) in &mut players {
        let n = pulled.iter().filter(|p| **p == e).count();
        let Some(mut fx) = fx else {
            if n > 0 {
                let mut fresh = DryFx::default();
                for _ in 0..n {
                    fresh.pull(f, stop_of(&weapon.0, false).is_some());
                }
                commands.entity(e).insert(HeldDryFire(fresh));
            }
            continue;
        };
        if vitals.is_some_and(|v| v.health.dead) {
            fx.0 = DryFx::default();
            continue;
        }
        let stop = stop_of(&weapon.0, weapon.0.prev_buttons.held(Buttons::ADS));
        for _ in 0..n {
            fx.0.pull(f, stop.is_some());
        }
        if let Some(why) = stop {
            fx.0.stop(why);
        }
        fx.0.step(f, dt);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sound::{DryFire, TriggerTick};
    use vetf_sim::GameData;
    use vetf_sim::data::AmmoChoice;
    use vetf_sim::input::InputFrame;
    use vetf_sim::movement::MoveMode;
    use vetf_sim::weapon::{WeaponEnv, WeaponLoadout};

    fn feel() -> DryFireFeel {
        FeelData::embedded().gun.dry_fire
    }

    const DT: f32 = 1.0 / 120.0;

    /// Steps `fx` for `secs`, returning the largest |turn| per axis (pitch, yaw, roll) and shift seen.
    fn run(fx: &mut DryFx, f: &DryFireFeel, secs: f32) -> (Vec3, f32) {
        let (mut turn, mut shift) = (Vec3::ZERO, 0.0f32);
        for _ in 0..(secs / DT).round() as usize {
            fx.step(f, DT);
            let (s, t) = fx.offset(f);
            turn = turn.max(t.abs());
            shift = shift.max(s.length());
        }
        (turn, shift)
    }

    #[test]
    fn the_data_is_a_short_twitch_and_a_half_second_shake_after_a_few_pulls() {
        let f = feel();
        assert!((3..=4).contains(&f.shake_after_pulls), "the user asked for 3 or 4 tries");
        assert!((0.3..=0.8).contains(&f.shake_s), "about half a second: {}", f.shake_s);
        assert!(f.reset_after_s >= 1.0, "a pause, not the gap between two quick pulls");
        assert!(f.twitch_pitch_deg > 0.0 && f.twitch_pitch_deg < 3.0, "a twitch, not a recoil");
        assert!(f.smack_s > 0.0 && f.smack_s < f.shake_s && f.cancel_s > 0.0 && f.cancel_s < f.shake_s);
        assert!(f.shake_roll_deg > f.twitch_pitch_deg, "the shake reads as more than a twitch");
    }

    /// The twitch trigger: every empty pull kicks the gun (muzzle down, a little lower), and it settles back.
    #[test]
    fn each_empty_pull_twitches_the_gun_and_it_settles() {
        let f = feel();
        let mut fx = DryFx::default();
        assert_eq!(fx.offset(&f), (Vec3::ZERO, Vec3::ZERO), "at rest");
        assert!(!fx.pull(&f, false), "one pull is no shake");
        let mut lowest = 0.0f32;
        let mut deepest = 0.0f32;
        for _ in 0..12 {
            fx.step(&f, DT);
            let (s, t) = fx.offset(&f);
            lowest = lowest.min(t.x);
            deepest = deepest.min(s.y);
            assert_eq!((t.y, t.z), (0.0, 0.0), "a twitch only nods");
        }
        assert!((lowest + f.twitch_pitch_deg).abs() < 0.15 * f.twitch_pitch_deg, "nods by about the data: {lowest}");
        assert!(deepest < 0.0, "dips");
        run(&mut fx, &f, 0.6);
        let (s, t) = fx.offset(&f);
        assert!(t.length() < 0.02 * f.twitch_pitch_deg && s.length() < 1e-4, "settled: {t} {s}");
        // The pose turns about the grip and leaves the scale.
        let pose = Transform::from_xyz(0.16, -0.2, -0.3);
        let mut fx = DryFx::default();
        fx.pull(&f, false);
        fx.step(&f, 0.03);
        let moved = view_gun(&f, pose, &fx);
        assert!(moved.translation.y < pose.translation.y && (moved.rotation * Vec3::NEG_Z).y < 0.0);
        assert_eq!(view_gun(&f, pose, &DryFx::default()), pose);
    }

    #[test]
    fn a_few_empty_pulls_in_a_row_shake_the_gun_for_about_half_a_second() {
        let f = feel();
        let n = f.shake_after_pulls;
        let mut fx = DryFx::default();
        for i in 1..n {
            assert!(!fx.pull(&f, false), "pull {i}");
            assert_eq!(fx.pulls(), i);
            run(&mut fx, &f, 0.2);
        }
        assert!(fx.pull(&f, false), "pull {n} shakes");
        assert!(fx.shaking() && fx.pulls() == 0, "the count starts again");
        // It rattles and smacks, then stops at shake_s.
        let mut t = 0.0;
        let (mut roll, mut nod) = (0.0f32, 0.0f32);
        while fx.shake.is_some() && t < 2.0 {
            fx.step(&f, DT);
            t += DT;
            let (_, turn) = fx.offset(&f);
            roll = roll.max(turn.z.abs());
            nod = nod.min(turn.x);
        }
        assert!((t - f.shake_s).abs() < 0.02, "lasts shake_s: {t}");
        assert!(roll > 0.5 * f.shake_roll_deg, "rattles: {roll}");
        assert!(nod < -0.8 * f.smack_pitch_deg, "smacks down: {nod}");
        let (_, turn) = fx.offset(&f);
        assert!(turn.length() < 0.05, "back at rest when it ends: {turn}");
        // A pull during the shake does not restart it; the next full count does.
        let mut fx = DryFx::default();
        for _ in 0..n {
            fx.pull(&f, false);
        }
        fx.step(&f, 0.1);
        assert!(!fx.pull(&f, false) && fx.shaking());
    }

    #[test]
    fn the_count_starts_again_after_a_pause_or_a_reload() {
        let f = feel();
        let n = f.shake_after_pulls;
        // Pulls further apart than reset_after_s never add up.
        let mut fx = DryFx::default();
        for _ in 0..(n * 3) {
            assert!(!fx.pull(&f, false));
            run(&mut fx, &f, f.reset_after_s + 0.1);
        }
        // A reload in between starts the count again.
        let mut fx = DryFx::default();
        for _ in 1..n {
            fx.pull(&f, false);
        }
        fx.stop(Stop::Reset);
        assert_eq!(fx.pulls(), 0);
        for i in 1..n {
            assert!(!fx.pull(&f, false), "pull {i} after the reload");
        }
        assert!(fx.pull(&f, false));
    }

    #[test]
    fn aiming_reloading_or_swapping_stops_the_shake() {
        let f = feel();
        let n = f.shake_after_pulls;
        for why in [Stop::Aim, Stop::Reset] {
            let mut fx = DryFx::default();
            for _ in 0..n {
                fx.pull(&f, false);
            }
            fx.step(&f, 0.1);
            fx.stop(why);
            assert!(!fx.shaking());
            let (turn, _) = run(&mut fx, &f, f.cancel_s + 0.02);
            assert!(turn.z <= f.shake_roll_deg, "{why:?}: it fades");
            assert!(fx.shake.is_none(), "{why:?}: gone after cancel_s");
        }
        // Aiming when the count comes round: no shake; the next pull without aiming shakes.
        let mut fx = DryFx::default();
        for _ in 1..n {
            fx.pull(&f, false);
        }
        assert!(!fx.pull(&f, true), "aiming");
        assert!(fx.pull(&f, false), "the next pull at the hip");
    }

    #[test]
    fn what_stops_the_shake_comes_from_the_weapon() {
        let data = GameData::embedded();
        let lo = WeaponLoadout::resolve(&data, "ar7_mako", &[], &[]).unwrap();
        let mut w = WeaponState::new(&data, &lo);
        w.action = WeaponAction::Ready;
        w.ads = 0.0;
        assert_eq!(stop_of(&w, false), None);
        assert_eq!(stop_of(&w, true), Some(Stop::Aim));
        w.ads = 0.3;
        assert_eq!(stop_of(&w, false), Some(Stop::Aim), "still coming down from the sights");
        w.action = WeaponAction::Reloading { left: 10, kind: vetf_sim::weapon::ReloadKind::Empty, slot: 1 };
        assert_eq!(stop_of(&w, false), Some(Stop::Reset));
        w.action = WeaponAction::Equipping { left: 10 };
        assert_eq!(stop_of(&w, true), Some(Stop::Reset));
        let h = held_turn(&feel(), &DryFx::default());
        assert!(h.angle_between(Quat::IDENTITY) < 1e-6, "others' guns sit still without pulls");
    }

    /// The dry-click latch and the frustration together, on the real simulation: an empty gun tapped every 0.3 s
    /// clicks on each tap, and the third click in a row shakes the gun; holding FIRE down is one pull.
    #[test]
    fn empty_taps_click_and_the_third_in_a_row_shakes() {
        let d = GameData::embedded();
        let f = feel();
        let env = WeaponEnv {
            mode: MoveMode::Ground,
            sprinting: false,
            crouched: false,
            speed_frac: 0.0,
            broken_arms: false,
            hands_busy: false,
        };
        for gun in ["ar7_mako", "vk50_warden"] {
            let lo = WeaponLoadout::resolve(&d, gun, &[AmmoChoice::STANDARD], &[]).unwrap();
            let mut ws = WeaponState::new(&d, &lo);
            ws.action = WeaponAction::Ready;
            ws.rounds = vec![0];
            let mut dry = DryFire::default();
            let mut fx = DryFx::default();
            let tick = 1.0 / d.net.tick_hz as f32;
            let mut clicks_at_shake = None;
            let mut clicks = 0;
            // Taps: FIRE down 3 ticks, up 15 ticks.
            for t in 0..(18 * 6) {
                let fire = t % 18 < 3;
                let b = Buttons(if fire { Buttons::FIRE } else { 0 });
                let ev = ws.step(&d, &lo, &InputFrame { buttons: b, ..Default::default() }, &env);
                if dry.local(&ev, TriggerTick::of(&ws)) {
                    clicks += 1;
                    if fx.pull(&f, stop_of(&ws, false).is_some()) {
                        clicks_at_shake.get_or_insert(clicks);
                    }
                }
                fx.step(&f, tick);
            }
            assert_eq!(clicks, 6, "{gun}: every tap clicks");
            assert_eq!(clicks_at_shake, Some(f.shake_after_pulls), "{gun}: the count'th click in a row shakes");
            // FIRE held down for two seconds is one pull: one click, no shake.
            let mut ws = WeaponState::new(&d, &lo);
            ws.action = WeaponAction::Ready;
            ws.rounds = vec![0];
            let (mut dry, mut fx, mut clicks) = (DryFire::default(), DryFx::default(), 0);
            for _ in 0..120 {
                let ev = ws.step(&d, &lo, &InputFrame { buttons: Buttons(Buttons::FIRE), ..Default::default() }, &env);
                if dry.local(&ev, TriggerTick::of(&ws)) {
                    clicks += 1;
                    assert!(!fx.pull(&f, false));
                }
            }
            assert_eq!(clicks, 1, "{gun}: held is one pull");
        }
    }
}
