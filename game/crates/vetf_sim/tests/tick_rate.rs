//! The simulation rate is a host setting (60 or 120 Hz, `net.ron`). Behaviour must not depend on it: these run
//! the same moves, jumps, slides, guns and throws at every offered rate and check they land within a small
//! tolerance of each other, and that fire rates are exactly the same.
//!
//! The tolerances are the integration error of a 60 Hz step: movement and grenades use semi-implicit Euler
//! (velocity first, then the move), which is off by about half a tick of speed change, `dv * dt / 2`: 2-5 cm on a
//! jump or a stop, under 1.5 % of a slide. 120 Hz is the more exact of the two.

use glam::{Vec2, Vec3};
use vetf_sim::GameData;
use vetf_sim::data::AmmoChoice;
use vetf_sim::input::{Buttons, InputFrame};
use vetf_sim::level::Level;
use vetf_sim::movement::collision::{Brush, BrushKind};
use vetf_sim::movement::{MoveMode, MoveModifiers, MoveState, step};
use vetf_sim::throwable::{Flight, Launch, Projectile, ThrowId, ThrowKind};
use vetf_sim::weapon::{WeaponAction, WeaponEnv, WeaponLoadout, WeaponState, fire_interval_ticks, secs_to_ticks};

/// The data at each rate a host may pick (the slowest first).
fn rates() -> Vec<GameData> {
    let d = GameData::embedded();
    let mut hz = d.net.tick_rates.clone();
    hz.sort_unstable();
    assert!(hz.contains(&60) && hz.contains(&120), "60 and 120 Hz are offered: {hz:?}");
    hz.iter().map(|r| d.with_tick_hz(*r)).collect()
}

fn flat() -> Level {
    let mut level = Level { kill_y: -50.0, ..Default::default() };
    level.world.push(Brush::cuboid(Vec3::new(-400.0, -1.0, -400.0), Vec3::new(400.0, 0.0, 400.0), BrushKind::Solid));
    level
}

fn frame(movement: Vec2, buttons: u16) -> InputFrame {
    InputFrame { movement, buttons: Buttons(buttons), ..Default::default() }
}

/// Run `secs` of `input(t)` (t in seconds) from a standstill; returns the state every tick with its time.
fn run(d: &GameData, secs: f32, input: impl Fn(f32) -> InputFrame) -> Vec<(f32, MoveState)> {
    let level = flat();
    let mods = MoveModifiers::unarmored(d);
    let mut st = MoveState::spawn(Vec3::ZERO, mods.max_fuel(&d.movement));
    let dt = d.tick_dt();
    let mut out = vec![];
    for k in 0..secs_to_ticks(secs, d.net.tick_hz) {
        let t = k as f32 * dt;
        step(d, &level, &mut st, &input(t), &mods, dt);
        out.push((t + dt, st));
    }
    out
}

fn close(what: &str, values: &[f32], tol: f32) {
    let (lo, hi) = values.iter().fold((f32::MAX, f32::MIN), |(lo, hi), v| (lo.min(*v), hi.max(*v)));
    assert!(hi - lo <= tol, "{what} differs by {} across tick rates (tolerance {tol}): {values:?}", hi - lo);
}

/// A second of running from a standstill reaches the same speed and covers the same ground; a sprint too.
#[test]
fn running_is_the_same_at_every_tick_rate() {
    for buttons in [0, Buttons::SPRINT] {
        let ends: Vec<MoveState> =
            rates().iter().map(|d| run(d, 1.0, |_| frame(Vec2::Y, buttons)).last().unwrap().1).collect();
        close("run distance (m)", &ends.iter().map(|s| -s.pos.z).collect::<Vec<_>>(), 0.05);
        close("run speed (m/s)", &ends.iter().map(|s| s.horizontal_speed()).collect::<Vec<_>>(), 0.01);
        // and stopping takes as long: half a second after letting go
        let stops: Vec<f32> = rates()
            .iter()
            .map(|d| {
                let r = run(d, 1.5, |t| frame(if t < 1.0 { Vec2::Y } else { Vec2::ZERO }, buttons));
                -r.last().unwrap().1.pos.z
            })
            .collect();
        // about 1 % of the ground covered
        close("run and stop distance (m)", &stops, 0.07);
    }
}

/// A jump from a standstill reaches the same apex, lands at the same time, and the time in the air matches.
#[test]
fn a_jump_peaks_and_lands_the_same_at_every_tick_rate() {
    let (mut apex, mut air) = (vec![], vec![]);
    for d in rates() {
        let r = run(&d, 1.5, |t| frame(Vec2::ZERO, if t < 0.05 { Buttons::JUMP } else { 0 }));
        apex.push(r.iter().map(|(_, s)| s.pos.y).fold(0.0, f32::max));
        let up: Vec<f32> = r.iter().filter(|(_, s)| s.mode == MoveMode::Air).map(|(t, _)| *t).collect();
        air.push(up.last().unwrap() - up.first().unwrap());
    }
    // 1.05 m at 60 Hz, 1.02 at 120 (the analytic apex of jump_v0 under gravity is 1.00 m)
    close("jump apex (m)", &apex, 0.03);
    close("time in the air (s)", &air, 0.02);
}

/// A slide out of a sprint goes as far and lasts as long.
#[test]
fn a_slide_goes_as_far_at_every_tick_rate() {
    let (mut far, mut long) = (vec![], vec![]);
    for d in rates() {
        // sprint 1.5 s, then crouch (held) into a slide until it ends
        let r = run(&d, 4.0, |t| frame(Vec2::Y, if t < 1.5 { Buttons::SPRINT } else { Buttons::CROUCH }));
        let sliding: Vec<&(f32, MoveState)> = r.iter().filter(|(_, s)| s.mode == MoveMode::Slide).collect();
        let (first, last) = (sliding.first().unwrap(), sliding.last().unwrap());
        far.push(first.1.pos.distance(last.1.pos));
        long.push(last.0 - first.0);
    }
    close("slide distance (m)", &far, 0.12);
    close("slide time (s)", &long, 0.02);
}

/// Every gun fires at exactly the same rate, hip and aimed, and a bolt cycles in the same time: the intervals land
/// on whole ticks at 60 Hz, so at 120 Hz too (Mako 720 RPM: 5 and 10 ticks, Warden 48 RPM: 75 and 150).
#[test]
fn fire_intervals_are_the_same_at_every_tick_rate() {
    let ds = rates();
    for w in &ds[0].weapons.weapons {
        for aimed in [false, true] {
            let secs: Vec<f32> =
                ds.iter().map(|d| fire_interval_ticks(w, d.net.tick_hz, aimed) as f32 / d.net.tick_hz as f32).collect();
            close(&format!("{} fire interval (aimed {aimed}, s)", w.id), &secs, 1e-6);
        }
    }
    let mako = ds[0].weapon("ar7_mako").unwrap();
    let warden = ds[0].weapon("vk50_warden").unwrap();
    assert_eq!([60, 120].map(|hz| fire_interval_ticks(mako, hz, false)), [5, 10]);
    assert_eq!([60, 120].map(|hz| fire_interval_ticks(mako, hz, true)), [6, 12]);
    assert_eq!([60, 120].map(|hz| fire_interval_ticks(warden, hz, false)), [75, 150]);
    // The other timed actions land within half a 60 Hz tick of each other.
    for w in &ds[0].weapons.weapons {
        for s in [w.reload_tactical_s, w.reload_empty_s, w.mag_check_s, w.equip_s, w.ads_s, w.sprint_to_fire_s] {
            let secs: Vec<f32> =
                ds.iter().map(|d| secs_to_ticks(s, d.net.tick_hz) as f32 / d.net.tick_hz as f32).collect();
            close(&format!("{} {s} s action", w.id), &secs, 0.5 / 60.0 + 1e-6);
        }
    }
}

/// Holding the trigger empties a magazine on the same schedule: every shot at the same time, at every rate.
#[test]
fn a_held_spray_fires_on_the_same_schedule_at_every_tick_rate() {
    let still = WeaponEnv {
        mode: MoveMode::Ground,
        sprinting: false,
        crouched: false,
        speed_frac: 0.0,
        broken_arms: false,
        hands_busy: false,
    };
    for gun in ["ar7_mako", "vk50_warden", "sk9_skink"] {
        let times: Vec<Vec<f32>> = rates()
            .iter()
            .map(|d| {
                let l = WeaponLoadout::resolve(d, gun, &[AmmoChoice::STANDARD], &[]).unwrap();
                let mut s = WeaponState::new(d, &l);
                s.action = WeaponAction::Ready;
                let mut at = vec![];
                for k in 0..secs_to_ticks(6.0, d.net.tick_hz) {
                    // pressed every 1/30 s (a fresh pull for the bolt gun), held between
                    let t = k as f32 * d.tick_dt();
                    let fire = if (t * 30.0).fract() < 0.5 { Buttons::FIRE } else { 0 };
                    if s.step(d, &l, &frame(Vec2::ZERO, fire), &still).shot.is_some() {
                        at.push(t);
                    }
                }
                at
            })
            .collect();
        assert_eq!(times[0].len(), times[1].len(), "{gun}: as many shots");
        for (k, (a, b)) in times[0].iter().zip(&times[1]).enumerate() {
            assert!((a - b).abs() <= 1.0 / 60.0 + 1e-4, "{gun}: shot {k} at {a} s vs {b} s");
        }
    }
}

/// A grenade's arc: where it is half a second in, and where it lands, match at every rate.
#[test]
fn throwable_arcs_are_the_same_at_every_tick_rate() {
    let level = flat();
    let launch =
        Launch { kind: ThrowKind::Molotov, seq: 1, origin: Vec3::new(0.0, 1.6, 0.0), vel: Vec3::new(0.0, 6.0, -14.0) };
    let (mut mid, mut burst, mut flight) = (vec![], vec![], vec![]);
    for d in rates() {
        let dt = d.tick_dt();
        let mut p = Projectile::new(ThrowId { owner: 1, seq: 1 }, &launch);
        let half = secs_to_ticks(0.5, d.net.tick_hz) as u32;
        let mut at = None;
        for _ in 0..secs_to_ticks(10.0, d.net.tick_hz) {
            let f = p.step(&d.throwables, &level, dt);
            if p.age == half {
                mid.push(p.pos);
            }
            if let Flight::Burst { at: a } = f {
                at = Some(a);
                break;
            }
        }
        burst.push(at.expect("it lands"));
        flight.push(p.age as f32 * dt);
    }
    close("half-second height (m)", &mid.iter().map(|p| p.y).collect::<Vec<_>>(), 0.04);
    close("half-second range (m)", &mid.iter().map(|p| p.z).collect::<Vec<_>>(), 0.01);
    close("landing range (m)", &burst.iter().map(|p| p.z).collect::<Vec<_>>(), 0.15);
    close("flight time (s)", &flight, 0.02);
}
