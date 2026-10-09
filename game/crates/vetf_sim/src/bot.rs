//! The test bot's brain (user direction 2026-10-09: "a simple and quick bot so i can solo test ... just a
//! stationary that aims at my head when in sight"). A bot stands where it spawned. Once an enemy's head has been
//! in its line of sight (within range) for its reaction time, it turns toward the head at its turn speed, with a
//! small aim error, and pulls the trigger when its view is on the aim point, in bursts. Its gun is an ordinary
//! [`WeaponState`] stepped by [`crate::player::step`], so fire rate, recoil, magazines and reloads are the normal
//! rules; it reloads when the magazine in the gun is empty. The host drives one brain per bot
//! (`val_etf/src/bots.rs`) and turns its inputs into shots like anyone's. Numbers: `game/assets/data/bots.ron`.

use crate::data::FireMode;
use crate::input::{Buttons, InputFrame, MAX_PITCH, view_dir};
use crate::movement::collision::CollisionWorld;
use crate::rng::SplitMix;
use crate::weapon::{Shot, WeaponState};
use glam::Vec3;
use serde::Deserialize;
use std::f32::consts::{PI, TAU};

/// `bots.ron`: everything a bot does, in numbers.
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct BotTuning {
    /// Callsign before the number ("BOT" makes "BOT 1").
    pub name: String,
    /// How far it sees an enemy's head (m).
    pub range_m: f32,
    /// Seconds a head must be in sight before it turns and shoots.
    pub reaction_s: f32,
    /// A target out of sight longer than this is forgotten (the next sighting waits for the reaction again).
    pub forget_s: f32,
    /// How fast the view turns (degrees per second).
    pub turn_deg_per_s: f32,
    /// The aim point's largest offset from the head's centre (degrees), rolled anew for every burst.
    pub aim_error_deg: f32,
    /// It pulls the trigger once the view is this close to the aim point (degrees).
    pub fire_cone_deg: f32,
    /// Rounds per burst (0: no bursts), then a pause of `burst_pause_s`.
    pub burst_shots: u32,
    pub burst_pause_s: f32,
    /// Aim down sights while shooting.
    pub ads: bool,
}

const EMBEDDED: &str = include_str!("../../../assets/data/bots.ron");

impl BotTuning {
    /// The copy compiled into the binary (checked by tests).
    pub fn embedded() -> Self {
        Self::parse(EMBEDDED).expect("game/assets/data/bots.ron is valid")
    }

    /// Parse and check `bots.ron`'s text.
    pub fn parse(text: &str) -> Result<Self, String> {
        let t: BotTuning = ron::from_str(text).map_err(|e| format!("bots.ron: {e}"))?;
        t.validate()?;
        Ok(t)
    }

    pub fn validate(&self) -> Result<(), String> {
        let finite = [
            self.range_m,
            self.reaction_s,
            self.forget_s,
            self.turn_deg_per_s,
            self.aim_error_deg,
            self.fire_cone_deg,
            self.burst_pause_s,
        ];
        if finite.iter().any(|x| !x.is_finite() || *x < 0.0) {
            return Err("bots.ron: every number must be finite and 0 or more".into());
        }
        if self.range_m <= 0.0 || self.turn_deg_per_s <= 0.0 || self.fire_cone_deg <= 0.0 {
            return Err("bots.ron: range_m, turn_deg_per_s and fire_cone_deg must be above 0".into());
        }
        if self.name.trim().is_empty() {
            return Err("bots.ron: name must not be empty".into());
        }
        Ok(())
    }

    /// The callsign of bot number `n` (1-based): "BOT 1".
    pub fn callsign(&self, n: u32) -> String {
        format!("{} {n}", self.name.trim())
    }
}

/// An enemy head the bot can see.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Seen {
    pub id: u64,
    pub head: Vec3,
}

/// The enemy head the bot shoots at: of the `heads` (enemies' ids and head centres) within range, with nothing
/// that stops bullets between `eye` and the head and no smoke hiding it (`veiled(eye, head)`, see
/// [`crate::throwable::ThrowWorld::sight_blocked`]), the one it is already on (`current`), else the nearest.
pub fn pick_target(
    t: &BotTuning,
    world: &CollisionWorld,
    veiled: impl Fn(Vec3, Vec3) -> bool,
    eye: Vec3,
    heads: impl IntoIterator<Item = (u64, Vec3)>,
    current: Option<u64>,
) -> Option<Seen> {
    let visible: Vec<Seen> = heads
        .into_iter()
        .filter(|(_, h)| h.distance(eye) <= t.range_m && world.line_of_sight(eye, *h) && !veiled(eye, *h))
        .map(|(id, head)| Seen { id, head })
        .collect();
    visible
        .iter()
        .find(|s| Some(s.id) == current)
        .or_else(|| visible.iter().min_by(|a, b| a.head.distance(eye).total_cmp(&b.head.distance(eye))))
        .copied()
}

/// The view angles (yaw, pitch, radians) that look from `eye` at `at`: the inverse of [`view_dir`].
pub fn aim_angles(eye: Vec3, at: Vec3) -> (f32, f32) {
    let d = (at - eye).normalize_or_zero();
    if d == Vec3::ZERO {
        return (0.0, 0.0);
    }
    let yaw = (-d.x).atan2(-d.z).rem_euclid(TAU);
    let pitch = d.y.clamp(-1.0, 1.0).asin().clamp(-MAX_PITCH, MAX_PITCH);
    (yaw, pitch)
}

/// The angle (radians) between two views.
pub fn view_gap(a: (f32, f32), b: (f32, f32)) -> f32 {
    view_dir(a.0, a.1).angle_between(view_dir(b.0, b.1))
}

/// `a - b` for angles, in (-PI, PI].
fn wrap(a: f32) -> f32 {
    let w = (a + PI).rem_euclid(TAU) - PI;
    if w <= -PI { w + TAU } else { w }
}

/// One bot's state between ticks.
#[derive(Debug, Clone)]
pub struct BotBrain {
    /// Its view (radians), what it sends as input.
    pub yaw: f32,
    pub pitch: f32,
    /// The enemy it is on.
    pub target: Option<u64>,
    /// Seconds the target has been in sight (the reaction).
    pub seen_s: f32,
    /// Seconds since the target was last in sight.
    pub lost_s: f32,
    /// The aim point's offset from the head's centre (yaw, pitch; radians).
    pub error: (f32, f32),
    /// Rounds fired in this burst, and the pause left after one.
    pub burst_fired: u32,
    pub pause_s: f32,
    /// Last tick's buttons (a semi-automatic or bolt gun needs the trigger released between shots).
    pub prev: Buttons,
    rng: SplitMix,
}

impl BotBrain {
    /// A brain looking along (`yaw`, `pitch`), its aim error drawn from `seed` (the bot's id).
    pub fn new(yaw: f32, pitch: f32, seed: u64) -> Self {
        Self {
            yaw,
            pitch,
            target: None,
            seen_s: 0.0,
            lost_s: 0.0,
            error: (0.0, 0.0),
            burst_fired: 0,
            pause_s: 0.0,
            prev: Buttons::default(),
            rng: SplitMix::from_parts(&[seed, 0x424f_5442_5241_494e]),
        }
    }

    /// A new aim error: up to `aim_error_deg` off the head's centre, in any direction.
    fn roll_error(&mut self, t: &BotTuning) {
        let r = t.aim_error_deg.to_radians() * self.rng.next_f32().sqrt();
        let a = self.rng.next_f32() * TAU;
        self.error = (r * a.cos(), r * a.sin());
    }

    /// The shot it fired last tick: the recoil kicks its view (as it kicks a player's camera: pitch up, yaw
    /// right is negative yaw), and the burst counts it.
    pub fn on_shot(&mut self, t: &BotTuning, shot: &Shot) {
        self.pitch = (self.pitch + shot.kick_pitch.to_radians()).clamp(-MAX_PITCH, MAX_PITCH);
        self.yaw = (self.yaw - shot.kick_yaw.to_radians()).rem_euclid(TAU);
        self.burst_fired += 1;
        if t.burst_shots > 0 && self.burst_fired >= t.burst_shots {
            self.burst_fired = 0;
            self.pause_s = t.burst_pause_s;
            self.roll_error(t);
        }
    }

    /// Turn the view toward (`yaw`, `pitch`) by at most `step` radians.
    fn turn_toward(&mut self, yaw: f32, pitch: f32, step: f32) {
        let (dy, dp) = (wrap(yaw - self.yaw), pitch - self.pitch);
        let gap = (dy * dy + dp * dp).sqrt();
        let k = if gap <= step || gap <= 0.0 { 1.0 } else { step / gap };
        self.yaw = (self.yaw + dy * k).rem_euclid(TAU);
        self.pitch = (self.pitch + dp * k).clamp(-MAX_PITCH, MAX_PITCH);
    }

    /// This tick's input: standing still, its view, and the trigger, aim and reload buttons. `seen` is the head
    /// it can see now ([`pick_target`]), `weapon` its gun, `dt` the tick.
    pub fn think(&mut self, t: &BotTuning, eye: Vec3, seen: Option<Seen>, weapon: &WeaponState, dt: f32) -> InputFrame {
        self.pause_s = (self.pause_s - dt).max(0.0);
        match seen {
            Some(s) => {
                if self.target != Some(s.id) || self.lost_s > t.forget_s {
                    // A new sighting: the reaction starts over, and so does the burst.
                    self.target = Some(s.id);
                    self.seen_s = 0.0;
                    self.burst_fired = 0;
                    self.roll_error(t);
                }
                self.lost_s = 0.0;
                self.seen_s += dt;
            }
            None => {
                self.lost_s += dt;
                if self.lost_s > t.forget_s {
                    self.target = None;
                    self.seen_s = 0.0;
                }
            }
        }
        let mut b = Buttons::default();
        if let Some(s) = seen.filter(|_| self.seen_s >= t.reaction_s) {
            let (yaw, pitch) = aim_angles(eye, s.head);
            let aim = ((yaw + self.error.0).rem_euclid(TAU), (pitch + self.error.1).clamp(-MAX_PITCH, MAX_PITCH));
            self.turn_toward(aim.0, aim.1, t.turn_deg_per_s.to_radians() * dt);
            b.set(Buttons::ADS, t.ads);
            let on_target = view_gap((self.yaw, self.pitch), aim) <= t.fire_cone_deg.to_radians();
            if on_target && self.pause_s <= 0.0 && weapon.is_ready() && weapon.mag() > 0 {
                let pull = match weapon.fire_mode {
                    FireMode::Auto => true,
                    // A fresh pull every other tick.
                    FireMode::Semi | FireMode::Bolt => !self.prev.held(Buttons::FIRE),
                };
                b.set(Buttons::FIRE, pull);
            }
        }
        // Reload when the magazine in the gun is empty and another one holds rounds (a tap: press, release).
        if weapon.is_ready() && weapon.mag() == 0 && weapon.next_slot().is_some() {
            b.set(Buttons::RELOAD, !self.prev.held(Buttons::RELOAD));
        }
        self.prev = b;
        InputFrame { yaw: self.yaw, pitch: self.pitch, buttons: b, ..Default::default() }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::GameData;
    use crate::movement::collision::{Brush, BrushKind};
    use crate::weapon::{WeaponAction, WeaponLoadout};

    fn tuning() -> BotTuning {
        BotTuning { aim_error_deg: 0.0, ..BotTuning::embedded() }
    }

    fn gun(d: &GameData) -> WeaponState {
        let mut w = WeaponState::new(d, &WeaponLoadout::default_for(d));
        w.action = WeaponAction::Ready;
        w
    }

    const DT: f32 = 1.0 / 60.0;

    /// The data file loads, and its numbers make sense.
    #[test]
    fn bots_ron_loads_and_validates() {
        let t = BotTuning::embedded();
        assert_eq!(t.callsign(1), "BOT 1");
        assert!(t.reaction_s > 0.0 && t.range_m > 10.0);
        let bad = BotTuning { turn_deg_per_s: 0.0, ..t.clone() };
        assert!(bad.validate().is_err());
        let bad = BotTuning { reaction_s: f32::NAN, ..t.clone() };
        assert!(bad.validate().is_err());
        let bad = BotTuning { name: " ".into(), ..t };
        assert!(bad.validate().is_err());
    }

    #[test]
    fn aim_angles_look_at_the_point() {
        let eye = Vec3::new(1.0, 1.6, 2.0);
        for at in [Vec3::new(1.0, 1.6, -8.0), Vec3::new(-5.0, 3.0, 7.0), Vec3::new(9.0, 0.2, 2.5)] {
            let (yaw, pitch) = aim_angles(eye, at);
            let d = view_dir(yaw, pitch);
            assert!((d - (at - eye).normalize()).length() < 1e-5, "{at}: {d}");
        }
        assert_eq!(aim_angles(eye, Vec3::new(1.0, 1.6, -8.0)), (0.0, 0.0), "north is yaw 0");
    }

    /// In sight within range: a target; behind a wall or beyond the range: none. It keeps the one it is on,
    /// else takes the nearest.
    #[test]
    fn it_sees_heads_in_range_and_in_the_open_only() {
        let t = tuning();
        let mut world = CollisionWorld::default();
        // A wall across x = 10, z in -1..1.
        world.push(Brush::cuboid(Vec3::new(9.5, 0.0, -1.0), Vec3::new(10.5, 3.0, 1.0), BrushKind::Solid));
        let eye = Vec3::new(0.0, 1.6, 0.0);
        let open = (1, Vec3::new(0.0, 1.6, -20.0));
        let walled = (2, Vec3::new(20.0, 1.6, 0.0));
        let far = (3, Vec3::new(0.0, 1.6, t.range_m + 5.0));
        let near = (4, Vec3::new(-8.0, 1.6, 0.0));
        let pick = |heads: &[(u64, Vec3)], cur| pick_target(&t, &world, |_, _| false, eye, heads.iter().copied(), cur);
        assert_eq!(pick(&[open], None).map(|s| s.id), Some(1), "in sight");
        assert_eq!(pick(&[walled], None), None, "out of sight");
        assert_eq!(pick(&[far], None), None, "out of range");
        assert_eq!(pick(&[open, walled, far, near], None).map(|s| s.id), Some(4), "the nearest");
        assert_eq!(pick(&[open, near], Some(1)).map(|s| s.id), Some(1), "the one it is on");
        assert_eq!(pick(&[open, near], Some(2)).map(|s| s.id), Some(4), "its old one is gone");
    }

    /// Smoke hides a head from the bot like a wall does: a cloud between them and it sees nothing (and keeps to
    /// a head it can still see); once the cloud thins out it sees again.
    #[test]
    fn smoke_hides_heads_from_the_bot() {
        use crate::throwable::{Smoke, ThrowId, ThrowWorld};
        let d = GameData::embedded();
        let t = tuning();
        let world = CollisionWorld::default();
        let eye = Vec3::new(0.0, 1.6, 0.0);
        let s = &d.throwables.smoke;
        let grown = (s.grow_s / DT) as u32 + 1;
        let mut smoke = ThrowWorld::default();
        smoke.smokes.push(Smoke { id: ThrowId { owner: 1, seq: 1 }, at: Vec3::new(0.0, 0.0, -10.0), age: grown });
        let behind = (1, Vec3::new(0.0, 1.6, -20.0));
        let beside = (2, Vec3::new(-20.0, 1.6, 0.0));
        let pick = |w: &ThrowWorld, heads: &[(u64, Vec3)], cur| {
            let veiled = |a, b| w.sight_blocked(&d.throwables, DT, a, b);
            pick_target(&t, &world, veiled, eye, heads.iter().copied(), cur).map(|s| s.id)
        };
        assert_eq!(pick(&smoke, &[behind], None), None, "behind the smoke");
        assert_eq!(pick(&smoke, &[behind, beside], Some(1)), Some(2), "it turns to the one it can see");
        smoke.smokes[0].age = ((s.grow_s + s.hold_s + s.fade_s * 0.95) / DT) as u32;
        assert_eq!(pick(&smoke, &[behind], None), Some(1), "the smoke has thinned out");
        // And the brain does not fire on a head it cannot see: no target, no trigger.
        let mut brain = BotBrain::new(0.0, 0.0, 1);
        let w = gun(&d);
        for _ in 0..240 {
            let f = brain.think(&t, eye, None, &w, DT);
            assert!(!f.buttons.held(Buttons::FIRE));
        }
    }

    /// Nothing before the reaction time; then it turns at its turn speed (never faster), and fires once on target.
    #[test]
    fn it_reacts_then_turns_then_fires() {
        let d = GameData::embedded();
        let t = tuning();
        let w = gun(&d);
        let eye = Vec3::new(0.0, 1.6, 0.0);
        // The head straight west (yaw 90 degrees); the bot looks north.
        let seen = Some(Seen { id: 7, head: Vec3::new(-15.0, 1.6, 0.0) });
        let mut brain = BotBrain::new(0.0, 0.0, 1);
        // Just short of the reaction time.
        let react = ((t.reaction_s / DT) as usize).saturating_sub(1);
        for _ in 0..react {
            let f = brain.think(&t, eye, seen, &w, DT);
            assert_eq!((f.yaw, f.buttons.held(Buttons::FIRE)), (0.0, false), "reacting");
        }
        let step = t.turn_deg_per_s.to_radians() * DT;
        let mut last = brain.yaw;
        let mut fired_at = None;
        for i in 0..120 {
            let f = brain.think(&t, eye, seen, &w, DT);
            assert!(wrap(f.yaw - last).abs() <= step + 1e-4, "turn speed");
            last = f.yaw;
            if f.buttons.held(Buttons::FIRE) {
                fired_at = Some(i);
                assert!(view_gap((f.yaw, f.pitch), (PI / 2.0, 0.0)) <= t.fire_cone_deg.to_radians() + 1e-4);
                break;
            }
            if brain.seen_s >= t.reaction_s {
                assert_eq!(f.buttons.held(Buttons::ADS), t.ads, "aims while shooting");
            }
        }
        let turn_ticks = (90.0 / t.turn_deg_per_s / DT) as usize;
        assert!(fired_at.is_some_and(|i| i + 2 >= turn_ticks), "fired after turning 90 degrees: {fired_at:?}");
        assert_eq!(brain.target, Some(7));
    }

    /// Out of sight it holds still and never fires; a short break keeps the target, a long one makes it react
    /// again.
    #[test]
    fn out_of_sight_it_holds_fire_and_forgets() {
        let d = GameData::embedded();
        let t = tuning();
        let w = gun(&d);
        let eye = Vec3::new(0.0, 1.6, 0.0);
        let seen = Some(Seen { id: 7, head: Vec3::new(0.0, 1.6, -15.0) });
        let mut brain = BotBrain::new(0.0, 0.0, 1);
        for _ in 0..200 {
            let f = brain.think(&t, eye, None, &w, DT);
            assert!(!f.buttons.held(Buttons::FIRE) && f.yaw == 0.0 && f.movement == glam::Vec2::ZERO);
        }
        let react = (t.reaction_s / DT).ceil() as usize + 1;
        let fires =
            |brain: &mut BotBrain, n| (0..n).any(|_| brain.think(&t, eye, seen, &w, DT).buttons.held(Buttons::FIRE));
        assert!(fires(&mut brain, react + 2), "on target after the reaction");
        // A blink (shorter than forget_s): back on it at once.
        let blink = ((t.forget_s * 0.5) / DT) as usize;
        for _ in 0..blink {
            assert!(!brain.think(&t, eye, None, &w, DT).buttons.held(Buttons::FIRE), "no shots out of sight");
        }
        brain.pause_s = 0.0;
        assert!(fires(&mut brain, 3), "a blink keeps the target");
        // Gone for longer: the reaction again.
        for _ in 0..((t.forget_s / DT) as usize + 2) {
            brain.think(&t, eye, None, &w, DT);
        }
        assert_eq!(brain.target, None);
        brain.pause_s = 0.0;
        assert!(!fires(&mut brain, react - 3), "reacts anew");
    }

    /// Bursts of `burst_shots`, then a pause; recoil kicks the view and the bot pulls it back.
    #[test]
    fn it_fires_in_bursts_and_fights_the_recoil() {
        let d = GameData::embedded();
        let t = tuning();
        let w = gun(&d);
        let eye = Vec3::new(0.0, 1.6, 0.0);
        let seen = Some(Seen { id: 7, head: Vec3::new(0.0, 1.6, -15.0) });
        let mut brain = BotBrain::new(0.0, 0.0, 1);
        brain.target = Some(7);
        brain.seen_s = t.reaction_s;
        let shot = Shot { seq: 1, ammo_slot: 0, spread_deg: 0.0, kick_pitch: 1.0, kick_yaw: 0.0 };
        for _ in 0..t.burst_shots {
            brain.on_shot(&t, &shot);
        }
        assert!(brain.pitch > 0.0, "the kick");
        assert_eq!(brain.pause_s, t.burst_pause_s, "a pause after the burst");
        let f = brain.think(&t, eye, seen, &w, DT);
        assert!(!f.buttons.held(Buttons::FIRE), "pausing");
        assert!(f.pitch < t.burst_shots as f32 * 1f32.to_radians(), "pulling down");
        let pause = (t.burst_pause_s / DT).ceil() as usize + 30;
        assert!((0..pause).any(|_| brain.think(&t, eye, seen, &w, DT).buttons.held(Buttons::FIRE)), "then again");
    }

    /// A semi-automatic gun gets a fresh pull every other tick; an empty magazine is reloaded (a tap), and a gun
    /// that is not ready does not fire.
    #[test]
    fn it_pulls_semi_triggers_and_reloads_when_empty() {
        let d = GameData::embedded();
        let t = BotTuning { burst_shots: 0, ..tuning() };
        let eye = Vec3::new(0.0, 1.6, 0.0);
        let seen = Some(Seen { id: 7, head: Vec3::new(0.0, 1.6, -15.0) });
        let mut brain = BotBrain::new(0.0, 0.0, 1);
        brain.target = Some(7);
        brain.seen_s = t.reaction_s;
        let mut w = gun(&d);
        w.fire_mode = FireMode::Semi;
        let pulls: Vec<bool> = (0..6).map(|_| brain.think(&t, eye, seen, &w, DT).buttons.held(Buttons::FIRE)).collect();
        assert_eq!(pulls, [true, false, true, false, true, false]);
        w.fire_mode = FireMode::Auto;
        assert!((0..4).all(|_| brain.think(&t, eye, seen, &w, DT).buttons.held(Buttons::FIRE)), "auto: held");
        // Empty: no trigger, a reload tap (also out of sight).
        let loaded = w.loaded as usize;
        w.rounds[loaded] = 0;
        let f = brain.think(&t, eye, None, &w, DT);
        assert!(f.buttons.held(Buttons::RELOAD) && !f.buttons.held(Buttons::FIRE));
        assert!(!brain.think(&t, eye, None, &w, DT).buttons.held(Buttons::RELOAD), "released");
        assert!(brain.think(&t, eye, None, &w, DT).buttons.held(Buttons::RELOAD), "and tapped again");
        // Nothing left anywhere: no reload.
        w.rounds.iter_mut().for_each(|r| *r = 0);
        assert!((0..3).all(|_| !brain.think(&t, eye, seen, &w, DT).buttons.held(Buttons::RELOAD)));
        // Reloading: hands off the trigger.
        let mut w = gun(&d);
        w.action = WeaponAction::Equipping { left: 5 };
        assert!((0..4).all(|_| !brain.think(&t, eye, seen, &w, DT).buttons.held(Buttons::FIRE)));
    }

    /// The aim error stays within `aim_error_deg` and differs from burst to burst.
    #[test]
    fn the_aim_error_is_small_and_rolled_per_burst() {
        let t = BotTuning::embedded();
        let mut brain = BotBrain::new(0.0, 0.0, 3);
        let shot = Shot { seq: 1, ammo_slot: 0, spread_deg: 0.0, kick_pitch: 0.0, kick_yaw: 0.0 };
        let mut errors = Vec::new();
        for _ in 0..20 {
            for _ in 0..t.burst_shots.max(1) {
                brain.on_shot(&t, &shot);
            }
            let (y, p) = brain.error;
            assert!((y * y + p * p).sqrt() <= t.aim_error_deg.to_radians() + 1e-6);
            errors.push(brain.error);
        }
        errors.dedup();
        assert!(errors.len() > 10, "a new offset per burst");
    }
}
