//! The mag check's inspect: the gun turns its magazine window toward the eye while the simulation checks the
//! magazine, so the cartridges behind the window (`weapon_models::MagWindow`, a coarse level) can be seen, and the
//! estimate card shows as the check ends. Visual only, like the rest of the feel (`feel.ron` gun.mag_inspect): the
//! check itself, its time and what cancels it are the simulation's (`vetf_sim::weapon`).
//!
//! A tap turns the gun in and back so it is back as the check ends; held, the gun stays turned (and the card stays
//! up) until the key comes up. Aiming, firing or a reload turns it back at once. Others see the gun in that
//! player's hand turn too, from their replicated weapon state.

use super::feel::{FeelData, HeldInspect, MagInspectFeel};
use crate::client::LocalControl;
use crate::config::Data;
use bevy::prelude::*;
use lightyear::prelude::*;
use vetf_net::*;
use vetf_sim::input::Buttons;
use vetf_sim::weapon::{WeaponAction, WeaponState};

/// How a mag check press is being used.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PressKind {
    /// Let go before the gun would turn back: a quick look, and the card.
    Tap,
    /// Still down (or let go later) when the tap would turn back: the gun stays turned while it is down.
    Hold,
}

impl PressKind {
    /// A press let go at `release_s` (seconds after the check started; `None` while it is down), for a tap that
    /// turns back at `turn_back_s`.
    pub fn of(release_s: Option<f32>, turn_back_s: f32) -> PressKind {
        match release_s {
            Some(r) if r <= turn_back_s => PressKind::Tap,
            _ => PressKind::Hold,
        }
    }
}

/// The turn-in and turn-back times (seconds) for a check of `check_s`: the data's, shortened in proportion when
/// both would not fit in the check.
pub fn timings(f: &MagInspectFeel, check_s: f32) -> (f32, f32) {
    let (i, o) = (f.in_s.max(0.0), f.out_s.max(0.0));
    let check = check_s.max(0.0);
    if i + o <= check || i + o <= 0.0 {
        (i, o)
    } else {
        let k = check / (i + o);
        (i * k, o * k)
    }
}

/// When a tap turns the gun back (seconds after the check started): so it is back as the check ends, but never
/// before it is all the way in.
pub fn turn_back_s(f: &MagInspectFeel, check_s: f32) -> f32 {
    let (i, o) = timings(f, check_s);
    (check_s - o).max(i)
}

fn smooth(x: f32) -> f32 {
    let s = x.clamp(0.0, 1.0);
    s * s * (3.0 - 2.0 * s)
}

/// What the inspect needs from this frame.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct InspectInput {
    pub dt: f32,
    /// The simulation started a check this frame.
    pub started: bool,
    /// The gun's check time (weapons.ron `mag_check_s`).
    pub check_s: f32,
    /// The mag check key is down.
    pub held: bool,
    /// Aiming, firing, a reload, or the simulation dropped the check: turn back now.
    pub cancel: bool,
}

/// The first-person inspect's timeline.
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct MagInspect {
    /// Seconds since the check started; `None` while the gun is not turned.
    t: Option<f32>,
    check_s: f32,
    /// When the key came up.
    release: Option<f32>,
    /// When the gun started to turn back, and over how long.
    back: Option<(f32, f32)>,
    /// How far the gun is turned, 0 (hip) .. 1 (window to the eye).
    pub weight: f32,
}

impl MagInspect {
    /// The press so far (`None` while idle).
    #[cfg(test)]
    pub fn kind(&self, f: &MagInspectFeel) -> Option<PressKind> {
        self.t.map(|_| PressKind::of(self.release, turn_back_s(f, self.check_s)))
    }

    /// One frame; returns the weight.
    pub fn step(&mut self, f: &MagInspectFeel, i: &InspectInput) -> f32 {
        if i.started {
            // A new check while the last one is still turning back carries on from where the gun is.
            let (in_s, _) = timings(f, i.check_s);
            *self = MagInspect { t: Some(in_s * self.weight), check_s: i.check_s, ..MagInspect::default() };
        }
        let Some(mut t) = self.t else {
            self.weight = 0.0;
            return 0.0;
        };
        t += i.dt.max(0.0);
        if !i.held && self.release.is_none() {
            self.release = Some(t);
        }
        let (in_s, out_s) = timings(f, self.check_s);
        if self.back.is_none() {
            if i.cancel {
                self.back = Some((t, f.cancel_s.max(0.0)));
            } else if let Some(r) = self.release {
                let turn = turn_back_s(f, self.check_s);
                let at = match PressKind::of(Some(r), turn) {
                    PressKind::Tap => turn,
                    PressKind::Hold => r,
                };
                if t >= at {
                    self.back = Some((at, out_s));
                }
            }
        }
        let rise = if in_s > 0.0 { smooth(t / in_s) } else { 1.0 };
        let fall = self.back.map_or(0.0, |(s, d)| if d > 0.0 { smooth((t - s) / d) } else { 1.0 });
        if fall >= 1.0 {
            *self = MagInspect::default();
            return 0.0;
        }
        self.t = Some(t);
        self.weight = rise * (1.0 - fall);
        self.weight
    }
}

/// The first-person gun's pose (view space) turned `weight` of the way to the inspect: shifted, then turned about
/// the grip (its origin) by the yaw, pitch and roll in view axes.
pub fn inspect_gun(f: &MagInspectFeel, pose: Transform, weight: f32) -> Transform {
    let w = weight.clamp(0.0, 1.0);
    if w <= 0.0 {
        return pose;
    }
    let turn = Quat::from_euler(
        EulerRot::YXZ,
        (f.yaw_deg * w).to_radians(),
        (f.pitch_deg * w).to_radians(),
        (f.roll_deg * w).to_radians(),
    );
    Transform {
        translation: pose.translation + Vec3::from(f.shift) * w,
        rotation: turn * pose.rotation,
        scale: pose.scale,
    }
}

/// The turn (in the gun's own axes, about the grip) of a third-person gun `weight` of the way into the inspect.
pub fn held_turn(h: &HeldInspect, weight: f32) -> Quat {
    let w = weight.clamp(0.0, 1.0);
    Quat::from_euler(
        EulerRot::YXZ,
        (h.yaw_deg * w).to_radians(),
        (h.pitch_deg * w).to_radians(),
        (h.roll_deg * w).to_radians(),
    )
}

/// Whether a player's gun (as everyone has it, replicated) should be turned to its window: while the check runs,
/// and while the key stays down after it with the card up; never while aiming or firing.
pub fn held_inspecting(w: &WeaponState) -> bool {
    let b = w.prev_buttons;
    if b.held(Buttons::FIRE) || b.held(Buttons::ADS) {
        return false;
    }
    match w.action {
        WeaponAction::MagChecking { .. } => true,
        WeaponAction::Ready => b.held(Buttons::MAG_CHECK) && w.card.is_some(),
        _ => false,
    }
}

/// A third-person gun's weight eased toward its target over `ease_s` (a time constant).
pub fn ease_held(weight: f32, inspecting: bool, h: &HeldInspect, dt: f32) -> f32 {
    let target = if inspecting { 1.0 } else { 0.0 };
    let k = if h.ease_s <= 0.0 { 1.0 } else { 1.0 - (-dt.max(0.0) / h.ease_s).exp() };
    weight + (target - weight) * k
}

/// This frame's first-person inspect, for `render::update_camera`.
#[derive(Resource, Debug, Clone, Default)]
pub struct ViewInspect {
    pub state: MagInspect,
    /// The simulation was checking last frame.
    checking: bool,
}

/// Steps the first-person inspect from our predicted weapon and the mag check key.
pub(crate) fn step_inspect(
    time: Res<Time>,
    feel: Res<FeelData>,
    data: Res<Data>,
    control: Res<LocalControl>,
    me: Query<(&PlayerWeapon, &PlayerLoadout, &Vitals), With<Controlled>>,
    mut view: ResMut<ViewInspect>,
) {
    let Some((weapon, loadout, vitals)) = me.iter().next() else { return };
    if vitals.health.dead {
        *view = ViewInspect::default();
        return;
    }
    let w = &weapon.0;
    let checking = matches!(w.action, WeaponAction::MagChecking { .. });
    let held = Buttons(control.held);
    let dropped = view.checking && !checking && w.card.is_none();
    let input = InspectInput {
        dt: time.delta_secs(),
        started: checking && !view.checking,
        check_s: loadout.0.weapon.spec(&data).mag_check_s,
        held: held.held(Buttons::MAG_CHECK),
        cancel: held.held(Buttons::FIRE)
            || held.held(Buttons::ADS)
            || matches!(w.action, WeaponAction::Reloading { .. } | WeaponAction::Equipping { .. })
            || dropped,
    };
    view.checking = checking;
    view.state.step(&feel.gun.mag_inspect, &input);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn feel() -> MagInspectFeel {
        FeelData::embedded().gun.mag_inspect
    }

    /// Runs a check of `check_s` at 120 fps with the key down for `hold_s`, cancelled at `cancel_at` if given;
    /// returns (time, weight) per frame until the gun is back (or 5 s).
    fn run(check_s: f32, hold_s: f32, cancel_at: Option<f32>) -> (Vec<(f32, f32)>, MagInspect) {
        let f = feel();
        let dt = 1.0 / 120.0;
        let mut s = MagInspect::default();
        let mut out = vec![];
        let mut kind = s;
        for frame in 0..600 {
            let t = (frame + 1) as f32 * dt;
            let i = InspectInput {
                dt,
                started: frame == 0,
                check_s,
                held: t <= hold_s,
                cancel: cancel_at.is_some_and(|c| t >= c),
            };
            let w = s.step(&f, &i);
            out.push((t, w));
            if s.kind(&f).is_some() {
                kind = s;
            }
            if frame > 0 && w == 0.0 {
                break;
            }
        }
        (out, kind)
    }

    #[test]
    fn the_data_is_a_quick_turn_that_fits_every_gun_check() {
        let f = feel();
        assert!(f.in_s > 0.0 && f.out_s > 0.0 && f.cancel_s > 0.0);
        assert!(f.cancel_s <= f.out_s, "a cancel turns back faster than a tap");
        assert!(f.third_person.ease_s > 0.0);
        let data = vetf_sim::GameData::embedded();
        for w in &data.weapons.weapons {
            let (i, o) = timings(&f, w.mag_check_s);
            assert_eq!((i, o), (f.in_s, f.out_s), "{}: the turn fits its {} s check", w.id, w.mag_check_s);
            // The gun is fully turned for a moment before it turns back.
            assert!(turn_back_s(&f, w.mag_check_s) - i >= 0.25, "{}: the window shows long enough", w.id);
        }
    }

    #[test]
    fn a_tap_turns_in_and_is_back_as_the_check_ends() {
        let check = 1.0;
        let (frames, kind) = run(check, 0.1, None);
        assert_eq!(kind.kind(&feel()), Some(PressKind::Tap));
        let peak = frames.iter().map(|f| f.1).fold(0.0, f32::max);
        assert!((peak - 1.0).abs() < 1e-3, "all the way in: {peak}");
        let end = frames.last().unwrap().0;
        assert!((end - check).abs() < 0.02, "back as the check ends: {end}");
        // Fully turned in the middle, where the card's estimate is being read.
        let mid = frames.iter().find(|f| (f.0 - 0.5).abs() < 0.005).unwrap().1;
        assert_eq!(mid, 1.0);
    }

    #[test]
    fn a_hold_keeps_the_gun_turned_until_released() {
        let f = feel();
        let (frames, kind) = run(1.0, 2.5, None);
        assert_eq!(kind.kind(&f), Some(PressKind::Hold));
        let at = |t: f32| frames.iter().find(|x| (x.0 - t).abs() < 0.005).map_or(0.0, |x| x.1);
        assert_eq!(at(1.5), 1.0, "still turned after the check");
        assert_eq!(at(2.45), 1.0, "still turned just before release");
        let end = frames.last().unwrap().0;
        assert!((end - (2.5 + f.out_s)).abs() < 0.02, "back out_s after release: {end}");
    }

    #[test]
    fn tap_or_hold_is_decided_by_when_the_key_comes_up() {
        let f = feel();
        let back = turn_back_s(&f, 1.0);
        assert_eq!(PressKind::of(Some(0.05), back), PressKind::Tap);
        assert_eq!(PressKind::of(Some(back), back), PressKind::Tap);
        assert_eq!(PressKind::of(Some(back + 0.1), back), PressKind::Hold);
        assert_eq!(PressKind::of(None, back), PressKind::Hold);
        // A press just past the tap's turn-back is a (short) hold: the gun turns back on release.
        let (frames, kind) = run(1.0, back + 0.2, None);
        assert_eq!(kind.kind(&f), Some(PressKind::Hold));
        assert!((frames.last().unwrap().0 - (back + 0.2 + f.out_s)).abs() < 0.02);
    }

    #[test]
    fn aiming_or_firing_cancels_it_quickly() {
        let f = feel();
        for (hold, cancel) in [(0.1, 0.4), (3.0, 1.6)] {
            let (frames, _) = run(1.0, hold, Some(cancel));
            let end = frames.last().unwrap().0;
            assert!(
                (end - (cancel + f.cancel_s)).abs() < 0.02,
                "hold {hold}: back {} s after the cancel",
                end - cancel
            );
        }
    }

    #[test]
    fn a_short_check_squeezes_the_turn_to_fit() {
        let f = MagInspectFeel { in_s: 0.4, out_s: 0.4, ..feel() };
        let (i, o) = timings(&f, 0.4);
        assert!((i + o - 0.4).abs() < 1e-6 && (i - o).abs() < 1e-6);
        assert_eq!(turn_back_s(&f, 0.4), i);
    }

    /// A gun's hip pose from its real socket places (the base GLBs) and the middle of its magazine window, in gun
    /// space (glTF axes: muzzle +Z, the window faces +-X).
    fn gun_at_hip(weapon: &str) -> (Transform, Vec3) {
        use crate::weapon_models::{Layout, ModelData, RawNode, first_person_rig};
        let node = |name: &str, t: Vec3| RawNode {
            name: name.into(),
            transform: Transform::from_translation(t),
            children: Vec::new(),
            extras: None,
        };
        let (prefix, optic, muzzle, window) = match weapon {
            "ar7_mako" => {
                ("MAKO", Vec3::new(0.0, 0.084, 0.0855), Vec3::new(0.0, 0.05, 0.565), Vec3::new(0.0, -0.09, 0.122))
            }
            _ => ("WARDEN", Vec3::new(0.0, 0.117, 0.19), Vec3::new(0.0, 0.075, 1.1), Vec3::new(0.0, -0.015, 0.227)),
        };
        let base = Layout::from_nodes(&[
            node(&format!("{prefix}_SOCKET_Optic"), optic),
            node(&format!("{prefix}_SOCKET_Muzzle"), muzzle),
        ]);
        let row = ModelData::embedded().guns.iter().find(|g| g.weapon == weapon).unwrap();
        (first_person_rig(row, &base, None).unwrap().hip, window)
    }

    #[test]
    fn the_inspect_pose_turns_the_magazine_window_to_the_eye() {
        // At the hip the magazine's side is seen nearly edge-on; turned, one of its window faces (gun +-X) looks
        // toward the eye, and the window stays on screen.
        let f = feel();
        for weapon in ["ar7_mako", "vk50_warden"] {
            let (hip, window) = gun_at_hip(weapon);
            let facing = |pose: Transform| {
                let to_eye = (-pose.transform_point(window)).normalize();
                [Vec3::X, Vec3::NEG_X].map(|n| (pose.rotation * n).dot(to_eye)).into_iter().fold(-1.0, f32::max)
            };
            let turned = inspect_gun(&f, hip, 1.0);
            let (before, after) = (facing(hip), facing(turned));
            assert!(after > before + 0.25, "{weapon}: the window turns toward the eye: {before:.2} -> {after:.2}");
            assert!(after > 0.6, "{weapon}: the window faces the eye (cos {after:.2})");
            let at = turned.transform_point(window);
            assert!(at.z < -0.1, "{weapon}: in front of the eye: {at}");
            let half = 30.0f32.to_radians().tan();
            assert!(at.x.abs() < -at.z * half && at.y.abs() < -at.z * half, "{weapon}: on screen: {at}");
            assert_eq!(inspect_gun(&f, hip, 0.0), hip);
        }
    }

    #[test]
    fn others_see_the_gun_turn_while_checking_but_not_while_aiming() {
        let data = vetf_sim::GameData::embedded();
        let lo = vetf_sim::weapon::WeaponLoadout::resolve(&data, "ar7_mako", &[], &[]).unwrap();
        let mut w = WeaponState::new(&data, &lo);
        w.action = WeaponAction::Ready;
        assert!(!held_inspecting(&w));
        w.action = WeaponAction::MagChecking { left: 10 };
        assert!(held_inspecting(&w));
        w.prev_buttons = Buttons(Buttons::ADS);
        assert!(!held_inspecting(&w), "aiming");
        w.action = WeaponAction::Ready;
        w.prev_buttons = Buttons(Buttons::MAG_CHECK);
        assert!(!held_inspecting(&w), "the key alone, no check done");
        w.card = Some(vetf_sim::weapon::MagCard { estimate: vetf_sim::weapon::MagEstimate::Full, slot: 0, left: 10 });
        assert!(held_inspecting(&w), "held after the check");
        let h = feel().third_person;
        let mut x = 0.0;
        for _ in 0..60 {
            x = ease_held(x, true, &h, 1.0 / 60.0);
        }
        assert!(x > 0.99);
        assert_eq!(held_turn(&h, 0.0), Quat::IDENTITY);
    }
}
