use super::collision::{Brush, BrushKind};
use super::*;
use crate::level::{Level, Zipline};
use std::f32::consts::PI;

const DT: f32 = 1.0 / 60.0;

fn flat_level() -> Level {
    let mut level = Level { name: "test".into(), kill_y: -50.0, ..Default::default() };
    level.world.push(Brush::cuboid(Vec3::new(-200.0, -1.0, -200.0), Vec3::new(200.0, 0.0, 200.0), BrushKind::Solid));
    level
}

fn mods(d: &GameData, wc: WeightClass) -> MoveModifiers {
    MoveModifiers { weight: wc, fx: d.armor.effects(wc), speed_mult: 1.0, gear_mult: 1.0, legs_broken: false }
}

fn input(mv: Vec2, bits: u16) -> InputFrame {
    InputFrame { movement: mv, yaw: 0.0, pitch: 0.0, buttons: Buttons(bits), ..Default::default() }
}

fn run(
    d: &GameData,
    level: &Level,
    st: &mut MoveState,
    inp: InputFrame,
    m: &MoveModifiers,
    ticks: usize,
) -> MoveEvents {
    let mut all = MoveEvents::default();
    for _ in 0..ticks {
        let ev = step(d, level, st, &inp, m, DT);
        all.jumped |= ev.jumped;
        all.landed |= ev.landed;
        all.slide_started |= ev.slide_started;
        all.jet_started |= ev.jet_started;
        all.mantle_started |= ev.mantle_started;
        all.zip_attached |= ev.zip_attached;
        all.zip_detached |= ev.zip_detached;
        all.fall_damage += ev.fall_damage;
    }
    all
}

fn spawn(d: &GameData, pos: Vec3) -> MoveState {
    MoveState::spawn(pos, d.movement.jetpack.fuel_s)
}

#[test]
fn reaches_jog_and_sprint_speed() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, 0), &m, 30);
    assert!((st.horizontal_speed() - 4.8).abs() < 1e-3, "{}", st.horizontal_speed());
    assert!(st.vel.z < 0.0, "forward is -Z");
    run(&d, &level, &mut st, input(Vec2::Y, Buttons::SPRINT), &m, 30);
    assert!((st.horizontal_speed() - 7.0).abs() < 1e-3);
    assert!(st.sprinting);
    assert_eq!(st.mode, MoveMode::Ground);
    assert!(st.pos.y.abs() < 0.01, "{}", st.pos);
}

#[test]
fn heavy_halo_is_slower() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::Heavy);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, Buttons::SPRINT), &m, 60);
    assert!((st.horizontal_speed() - 7.0 * 0.88).abs() < 1e-3);
}

#[test]
fn no_sprint_sideways_or_backwards() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::X, Buttons::SPRINT), &m, 30);
    assert!(!st.sprinting);
    run(&d, &level, &mut st, input(Vec2::NEG_Y, Buttons::SPRINT), &m, 30);
    assert!(!st.sprinting);
    run(&d, &level, &mut st, input(Vec2::new(1.0, 1.0), Buttons::SPRINT), &m, 30);
    assert!(st.sprinting, "a forward diagonal (45 deg) sprints");
}

/// The run a player is in when they press crouch: (input, buttons held besides crouch).
fn slide_from(d: &GameData, mv: Vec2, bits: u16, wc: WeightClass) -> (bool, f32) {
    let level = flat_level();
    let m = mods(d, wc);
    let mut st = spawn(d, Vec3::ZERO);
    run(d, &level, &mut st, input(mv, bits), &m, 60);
    let speed = st.horizontal_speed();
    let ev = step(d, &level, &mut st, &input(mv, bits | Buttons::CROUCH), &m, DT);
    assert_eq!(ev.slide_started, st.mode == MoveMode::Slide);
    (ev.slide_started, speed)
}

/// The slide threshold sits below a normal run (user direction 2026-10-08): crouching while running or
/// sprinting forward slides; walking, strafing or backpedalling just crouches.
#[test]
fn a_slide_starts_from_a_forward_run() {
    let d = GameData::embedded();
    let s = &d.movement.slide;
    assert!(s.min_entry_speed < d.movement.speed.jog, "a jog is fast enough");
    assert!(s.min_entry_speed > d.movement.speed.walk.max(d.movement.speed.crouch), "a walk is not");
    let none = WeightClass::None;
    let diag = Vec2::new(1.0, 1.0).normalize();
    for (mv, bits, want, why) in [
        (Vec2::Y, 0, true, "jog forward"),
        (Vec2::Y, Buttons::SPRINT, true, "sprint forward"),
        (diag, Buttons::SPRINT, true, "sprint on a forward diagonal"),
        (diag, 0, true, "jog on a forward diagonal"),
        (Vec2::Y, Buttons::WALK, false, "walk"),
        (Vec2::X, 0, false, "strafe at jog speed"),
        (Vec2::NEG_Y, 0, false, "backpedal at jog speed"),
        (Vec2::ZERO, 0, false, "standing"),
    ] {
        let (slid, speed) = slide_from(&d, mv, bits, none);
        assert_eq!(slid, want, "{why} at {speed} m/s");
    }
    // a Medium halo still slides from a jog
    assert!(slide_from(&d, Vec2::Y, 0, WeightClass::Medium).0);
    // releasing forward a moment before the crouch still slides on the momentum
    let level = flat_level();
    let m = mods(&d, none);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, Buttons::SPRINT), &m, 60);
    step(&d, &level, &mut st, &input(Vec2::ZERO, 0), &m, DT);
    assert!(step(&d, &level, &mut st, &input(Vec2::ZERO, Buttons::CROUCH), &m, DT).slide_started);
}

#[test]
fn landing_with_crouch_held_slides_only_forward() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    for (mv, want) in [(Vec2::Y, true), (Vec2::NEG_Y, false)] {
        let mut st = spawn(&d, Vec3::ZERO);
        run(&d, &level, &mut st, input(mv, 0), &m, 60);
        step(&d, &level, &mut st, &input(mv, Buttons::JUMP), &m, DT);
        assert_eq!(st.mode, MoveMode::Air);
        let mut slid = false;
        for _ in 0..90 {
            slid |= step(&d, &level, &mut st, &input(mv, Buttons::CROUCH), &m, DT).slide_started;
        }
        assert_eq!(slid, want, "{mv}");
    }
}

#[test]
fn jump_apex_is_one_metre() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    step(&d, &level, &mut st, &input(Vec2::ZERO, Buttons::JUMP), &m, DT);
    assert_eq!(st.mode, MoveMode::Air);
    let mut peak: f32 = 0.0;
    for _ in 0..120 {
        step(&d, &level, &mut st, &input(Vec2::ZERO, Buttons::JUMP), &m, DT);
        peak = peak.max(st.pos.y);
    }
    assert!((peak - 1.0).abs() < 0.06, "{peak}");
    assert_eq!(st.mode, MoveMode::Ground, "landed");
}

/// The design's check values: highest feet rise from a standing start with jump + full jetpack.
#[test]
fn jetpack_max_rise_matches_design() {
    let d = GameData::embedded();
    let level = flat_level();
    for wc in [WeightClass::Light, WeightClass::Medium, WeightClass::Heavy] {
        let m = mods(&d, wc);
        let mut best: f32 = 0.0;
        for press_at in 2..30 {
            let mut st = spawn(&d, Vec3::ZERO);
            st.fuel = m.max_fuel(&d.movement);
            let mut peak: f32 = 0.0;
            for t in 0..240 {
                let held = t == 0 || t >= press_at;
                step(&d, &level, &mut st, &input(Vec2::ZERO, if held { Buttons::JUMP } else { 0 }), &m, DT);
                peak = peak.max(st.pos.y);
            }
            best = best.max(peak);
        }
        let want = d.movement.jetpack.max_rise_m[&wc];
        assert!((best - want).abs() < 0.1, "{wc:?}: rise {best} vs design {want}");
    }
}

#[test]
fn jetpack_needs_a_fresh_press_and_fuel() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    // Holding jump from the ground never lights the jetpack.
    let ev = run(&d, &level, &mut st, input(Vec2::ZERO, Buttons::JUMP), &m, 20);
    assert!(!ev.jet_started);
    let mut st = spawn(&d, Vec3::ZERO);
    st.fuel = 0.0;
    step(&d, &level, &mut st, &input(Vec2::ZERO, Buttons::JUMP), &m, DT);
    step(&d, &level, &mut st, &input(Vec2::ZERO, 0), &m, DT);
    let ev = run(&d, &level, &mut st, input(Vec2::ZERO, Buttons::JUMP), &m, 5);
    assert!(!ev.jet_started, "no fuel");
}

#[test]
fn fuel_regenerates_after_delay() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    st.fuel = 0.0;
    st.fuel_regen_wait = d.movement.jetpack.regen_delay_s;
    run(&d, &level, &mut st, input(Vec2::ZERO, 0), &m, 55);
    assert_eq!(st.fuel, 0.0);
    run(&d, &level, &mut st, input(Vec2::ZERO, 0), &m, (60.0 * 3.3) as usize);
    assert!((st.fuel - d.movement.jetpack.fuel_s).abs() < 1e-4);
}

#[test]
fn slide_boosts_then_slows_to_a_crouch() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, Buttons::SPRINT), &m, 30);
    let ev = step(&d, &level, &mut st, &input(Vec2::Y, Buttons::SPRINT | Buttons::CROUCH), &m, DT);
    assert!(ev.slide_started);
    assert_eq!(st.mode, MoveMode::Slide);
    assert!(st.horizontal_speed() > 9.8, "boosted: {}", st.horizontal_speed());
    // Playtest round 4 ("slide feels a little slow and short"): (10 - 3.6) / 3.75 = 1.7 s and about 11.6 m of
    // sliding on flat ground, inside the 1.6-1.8 s and 11-13 m asked for.
    let start = st.pos;
    let mut ticks = 0;
    while st.mode == MoveMode::Slide && ticks < 300 {
        step(&d, &level, &mut st, &input(Vec2::Y, Buttons::CROUCH), &m, DT);
        ticks += 1;
    }
    let secs = ticks as f32 * DT;
    let dist = horizontal(st.pos - start).length();
    assert!((1.6..=1.8).contains(&secs), "{secs} s");
    assert!((11.0..=13.0).contains(&dist), "{dist} m");
    assert_eq!(st.stance, Stance::Crouch);
}

#[test]
fn slide_boost_has_cooldown() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, Buttons::SPRINT), &m, 30);
    step(&d, &level, &mut st, &input(Vec2::Y, Buttons::CROUCH), &m, DT);
    // stand up and immediately slide again: no second boost
    step(&d, &level, &mut st, &input(Vec2::Y, Buttons::SPRINT), &m, DT);
    let before = st.horizontal_speed();
    step(&d, &level, &mut st, &input(Vec2::Y, Buttons::SPRINT | Buttons::CROUCH), &m, DT);
    assert!(st.horizontal_speed() <= before + 1e-3);
}

#[test]
fn steps_up_stairs_but_not_walls() {
    let d = GameData::embedded();
    let mut level = flat_level();
    level.world.push(Brush::cuboid(Vec3::new(-5.0, 0.0, -3.0), Vec3::new(5.0, 0.3, -2.0), BrushKind::Solid));
    level.world.push(Brush::cuboid(Vec3::new(-5.0, 0.0, -8.0), Vec3::new(5.0, 0.6, -7.0), BrushKind::Solid));
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, 0), &m, 40);
    assert!((st.pos.y - 0.3).abs() < 0.02 || st.pos.z < -3.0, "stepped onto/over the 0.3 m step: {}", st.pos);
    run(&d, &level, &mut st, input(Vec2::Y, 0), &m, 120);
    assert!(st.pos.z > -7.0, "0.6 m wall blocks walking: {}", st.pos);
}

#[test]
fn walks_up_a_ramp() {
    let d = GameData::embedded();
    let mut level = flat_level();
    // 2 m over 6 m (18 deg), like the course ramp
    level.world.push(Brush::ramp(Vec3::new(-5.0, 0.0, -8.0), Vec3::new(5.0, 2.0, -2.0), Vec3::NEG_Z, BrushKind::Solid));
    level.world.push(Brush::cuboid(Vec3::new(-5.0, 0.0, -20.0), Vec3::new(5.0, 2.0, -8.0), BrushKind::Solid));
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, 0), &m, 150);
    assert!((st.pos.y - 2.0).abs() < 0.05, "{}", st.pos);
    assert!(st.pos.z < -9.0);
    assert_eq!(st.mode, MoveMode::Ground);
}

#[test]
fn mantles_onto_a_box() {
    let d = GameData::embedded();
    let mut level = flat_level();
    level.world.push(Brush::cuboid(Vec3::new(-5.0, 0.0, -6.0), Vec3::new(5.0, 1.5, -1.0), BrushKind::Solid));
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    let mut started = false;
    for _ in 0..120 {
        started |= step(&d, &level, &mut st, &input(Vec2::Y, Buttons::JUMP), &m, DT).mantle_started;
        if started {
            break;
        }
    }
    assert!(started);
    run(&d, &level, &mut st, input(Vec2::ZERO, 0), &m, 60);
    assert!((st.pos.y - 1.5).abs() < 0.05, "{}", st.pos);
    assert!(st.pos.z < -1.0, "on top of the box: {}", st.pos);
    assert_eq!(st.mode, MoveMode::Ground);
}

#[test]
fn zipline_ride_and_jump_off() {
    let d = GameData::embedded();
    let mut level = flat_level();
    level.ziplines.push(Zipline { a: Vec3::new(0.0, 2.9, 0.0), b: Vec3::new(0.0, 2.9, -40.0) });
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    let ev = step(&d, &level, &mut st, &input(Vec2::ZERO, Buttons::INTERACT), &m, DT);
    assert!(ev.zip_attached);
    run(&d, &level, &mut st, input(Vec2::ZERO, 0), &m, 60);
    assert_eq!(st.mode, MoveMode::Zipline);
    assert!(st.vel.z < -10.0, "riding at ~11 m/s: {}", st.vel);
    let ev = step(&d, &level, &mut st, &input(Vec2::ZERO, Buttons::JUMP), &m, DT);
    assert!(ev.zip_detached);
    assert_eq!(st.mode, MoveMode::Air);
    assert!(st.vel.y > 4.0);
}

/// A cable 2.9 m up from the middle of one pylon to the middle of another 30 m away (as on Showhome), over a floor.
fn pylon_level() -> Level {
    let mut level = flat_level();
    for z in [0.0, -30.0] {
        let (min, max) = (Vec3::new(-0.25, 0.0, z - 0.25), Vec3::new(0.25, 4.0, z + 0.25));
        level.world.push(Brush::cuboid(min, max, BrushKind::Solid));
    }
    level.ziplines.push(Zipline { a: Vec3::new(0.0, 2.9, 0.0), b: Vec3::new(0.0, 2.9, -30.0) });
    level
}

/// Grab the cable from `from` facing `yaw` and ride for `ticks` with no input but `jump_at`; returns every tick's
/// state, asserting none of them is inside anything.
fn ride(d: &GameData, level: &Level, from: Vec3, yaw: f32, jump_at: Option<usize>, ticks: usize) -> Vec<MoveState> {
    let m = mods(d, WeightClass::None);
    let mut st = spawn(d, from);
    (0..ticks)
        .map(|i| {
            let bits = match i {
                0 => Buttons::INTERACT,
                i if Some(i) == jump_at => Buttons::JUMP,
                _ => 0,
            };
            step(d, level, &mut st, &InputFrame { yaw, ..input(Vec2::ZERO, bits) }, &m, DT);
            assert!(fits(&level.world, &d.movement, st.pos, st.stance), "tick {i}: inside something at {}", st.pos);
            st
        })
        .collect()
}

#[test]
fn zipline_ride_ends_short_of_the_pylon() {
    let d = GameData::embedded();
    let level = pylon_level();
    let keep_off = d.movement.capsule.radius + d.movement.zipline.end_clearance;
    let ticks = ride(&d, &level, Vec3::new(0.0, 0.0, -1.0), 0.0, None, 240);
    assert_eq!(ticks[0].mode, MoveMode::Zipline);
    let off = ticks.iter().position(|s| s.mode != MoveMode::Zipline).expect("the ride ends");
    assert!((ticks[off].pos.z + 30.0 - keep_off).abs() < 1e-3, "ended at {}", ticks[off].pos);
    // It hops off, drops to the floor in front of the pylon and can walk away (back along the line).
    let mut st = *ticks.last().unwrap();
    assert_eq!(st.mode, MoveMode::Ground);
    assert!(st.pos.y.abs() < 0.01 && st.pos.z > -30.0 + 0.25 + 0.32, "{}", st.pos);
    let from = st.pos;
    run(&d, &level, &mut st, InputFrame { yaw: PI, ..input(Vec2::Y, 0) }, &mods(&d, WeightClass::None), 60);
    assert!(st.pos.z - from.z > 2.0, "walked away: {} -> {}", from, st.pos);
}

#[test]
fn zipline_grabbed_at_a_pylon_hangs_clear_of_it() {
    let d = GameData::embedded();
    let level = pylon_level();
    // Facing the near pylon: the grab hangs clear of it and the ride ends on the same tick, still clear.
    let ticks = ride(&d, &level, Vec3::new(0.0, 0.0, -0.6), PI, None, 60);
    assert_eq!(ticks[0].mode, MoveMode::Air);
    assert!(ticks[0].pos.y > 0.8 && ticks[0].pos.z <= -0.25 - 0.32, "{}", ticks[0].pos);
    assert_eq!(ticks.last().unwrap().mode, MoveMode::Ground);
}

#[test]
fn zipline_ride_stops_short_of_a_wall_on_the_line() {
    let d = GameData::embedded();
    let mut level = pylon_level();
    // A beam across the line, above head height on the floor but in the way of a hanging rider.
    level.world.push(Brush::cuboid(Vec3::new(-2.0, 2.2, -15.2), Vec3::new(2.0, 2.6, -14.8), BrushKind::Solid));
    let ticks = ride(&d, &level, Vec3::new(0.0, 0.0, -1.0), 0.0, None, 240);
    let off = ticks.iter().position(|s| s.mode != MoveMode::Zipline).expect("the ride ends");
    assert!(ticks[off].pos.z > -14.8 + 0.31 && ticks[off].pos.z < -14.0, "{}", ticks[off].pos);
}

#[test]
fn zipline_jump_off_near_the_end() {
    let d = GameData::embedded();
    let level = pylon_level();
    let off = ride(&d, &level, Vec3::new(0.0, 0.0, -1.0), 0.0, None, 240)
        .iter()
        .position(|s| s.mode != MoveMode::Zipline)
        .unwrap();
    let ticks = ride(&d, &level, Vec3::new(0.0, 0.0, -1.0), 0.0, Some(off - 2), 240);
    let jumped = ticks[off - 2];
    assert_eq!(jumped.mode, MoveMode::Air);
    assert!(jumped.vel.y > d.movement.zipline.detach_up * 0.9, "{jumped:?}");
    assert_eq!(ticks.last().unwrap().mode, MoveMode::Ground);
}

#[test]
fn long_fall_hurts_legs() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::new(0.0, 10.0, 0.0));
    st.mode = MoveMode::Air;
    st.peak_y = 10.0;
    let ev = run(&d, &level, &mut st, input(Vec2::ZERO, 0), &m, 120);
    assert!(ev.landed);
    assert!((ev.fall_damage - 36.0).abs() < 0.5, "{}", ev.fall_damage);
}

#[test]
fn broken_legs_block_sprint_and_jet() {
    let d = GameData::embedded();
    let level = flat_level();
    let mut m = mods(&d, WeightClass::None);
    m.legs_broken = true;
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, Buttons::SPRINT), &m, 30);
    assert!(!st.sprinting);
}

/// Flat floor with a lintel across the way north: 1.1 m of clearance under it, 0.25 m deep (z -3.25..-3.0), so a
/// slide fits under it and a crouch does not.
fn lintel_level() -> Level {
    let mut level = flat_level();
    level.world.push(Brush::cuboid(Vec3::new(-5.0, 1.1, -3.25), Vec3::new(5.0, 3.0, -3.0), BrushKind::Solid));
    level
}

/// A slide stopped under the lintel, moving north at `speed`.
fn sliding_under_lintel(d: &GameData, speed: f32) -> MoveState {
    let mut st = spawn(d, Vec3::new(0.0, SKIN, -3.1));
    st.mode = MoveMode::Slide;
    st.stance = Stance::Slide;
    st.eye = d.movement.eye_height.slide;
    st.vel = Vec3::new(0.0, 0.0, -speed);
    st.prev_buttons = Buttons(Buttons::CROUCH);
    st
}

/// User report (round 3, item 7): a slide stopped midway under a low gap left the player stuck in the wall,
/// rising up through it. The slide stance stays until there is room to crouch or stand.
#[test]
fn slide_stopped_under_a_low_gap_stays_low() {
    let d = GameData::embedded();
    let level = lintel_level();
    let m = mods(&d, WeightClass::None);
    assert!(d.movement.capsule.height_slide < 1.1 && d.movement.capsule.height_crouch > 1.1, "the test gap");

    // Crouch released mid-gap: the slide ends, but there is no room to stand or crouch.
    let mut st = sliding_under_lintel(&d, 1.0);
    step(&d, &level, &mut st, &input(Vec2::ZERO, 0), &m, DT);
    assert_eq!(st.mode, MoveMode::Ground);
    assert_eq!(st.stance, Stance::Slide);
    for (bits, what) in [(0, "released"), (Buttons::CROUCH, "crouch held"), (Buttons::JUMP, "jump")] {
        for _ in 0..90 {
            step(&d, &level, &mut st, &input(Vec2::ZERO, bits), &m, DT);
            assert_eq!(st.stance, Stance::Slide, "{what}");
            assert_eq!(st.mode, MoveMode::Ground, "{what}");
            assert!((st.pos.y - SKIN).abs() < 1e-3, "{what}: rose to {}", st.pos.y);
            assert_clear(&d, &level, &st);
            assert!((-3.25 - 0.32..-3.0 + 0.32).contains(&st.pos.z), "{what}: left the gap: {}", st.pos);
        }
    }

    // Still low, it moves at crouch speed, and stands up once clear of the lintel.
    let mut stood = None;
    for t in 0..120 {
        step(&d, &level, &mut st, &input(Vec2::Y, 0), &m, DT);
        assert!((st.pos.y - SKIN).abs() < 1e-3, "rose to {}", st.pos.y);
        assert_clear(&d, &level, &st);
        if st.stance != Stance::Stand {
            assert!(st.horizontal_speed() <= d.movement.speed.crouch + 1e-3, "{}", st.horizontal_speed());
        } else if stood.is_none() {
            stood = Some(t);
            // Standing needs the whole box clear of the lintel (its north face, minus the radius).
            assert!(st.pos.z <= -3.25 - d.movement.capsule.radius + 0.01, "{}", st.pos.z);
        }
    }
    assert!(stood.is_some(), "never stood up: {st:?}");
}

/// A slide that runs out of speed under a low gap with crouch held stays low too (not a crouch that does not fit).
#[test]
fn slide_ending_under_a_low_gap_with_crouch_held_stays_low() {
    let d = GameData::embedded();
    let level = lintel_level();
    let m = mods(&d, WeightClass::None);
    let mut st = sliding_under_lintel(&d, d.movement.slide.end_speed * 0.5);
    run(&d, &level, &mut st, input(Vec2::ZERO, Buttons::CROUCH), &m, 120);
    assert_eq!(st.mode, MoveMode::Ground);
    assert_eq!(st.stance, Stance::Slide);
    assert!((st.pos.y - SKIN).abs() < 1e-3, "rose to {}", st.pos.y);
    // Backing out south: a crouch first (crouch is held), with the feet still on the floor.
    run(&d, &level, &mut st, input(Vec2::NEG_Y, Buttons::CROUCH), &m, 60);
    assert_eq!(st.stance, Stance::Crouch);
    assert!(st.pos.z > -3.0 + d.movement.capsule.radius - 0.01, "{}", st.pos.z);
    assert!((st.pos.y - SKIN).abs() < 1e-3);
}

/// The player's box for its current stance is not inside anything.
fn assert_clear(d: &GameData, level: &Level, st: &MoveState) {
    let half = half_extents(&d.movement, st.stance);
    let c = center(st.pos, half) + Vec3::Y * SKIN;
    assert!(!level.world.trace_box(c, c + Vec3::Y * 0.001, half).start_solid, "inside the level: {st:?}");
}

/// Sliding off a ledge under a low ceiling keeps the slide stance in the air until a crouch fits.
#[test]
fn slide_off_a_ledge_under_a_low_ceiling_stays_low() {
    let d = GameData::embedded();
    let mut level = Level { name: "test".into(), kill_y: -50.0, ..Default::default() };
    // A floor that ends at z = -3, a lower floor 2 m down, and a 1.1 m ceiling that runs on past the edge.
    level.world.push(Brush::cuboid(Vec3::new(-5.0, -1.0, -3.0), Vec3::new(5.0, 0.0, 5.0), BrushKind::Solid));
    level.world.push(Brush::cuboid(Vec3::new(-5.0, -3.0, -20.0), Vec3::new(5.0, -2.0, 5.0), BrushKind::Solid));
    level.world.push(Brush::cuboid(Vec3::new(-5.0, 1.1, -6.0), Vec3::new(5.0, 3.0, 0.0), BrushKind::Solid));
    let m = mods(&d, WeightClass::None);
    let mut st = sliding_under_lintel(&d, 6.0);
    st.pos = Vec3::new(0.0, SKIN, -2.5);
    let mut left_ground = false;
    for _ in 0..90 {
        step(&d, &level, &mut st, &input(Vec2::Y, Buttons::CROUCH), &m, DT);
        assert_clear(&d, &level, &st);
        left_ground |= st.mode == MoveMode::Air;
    }
    assert!(left_ground);
    assert!((st.pos.y + 2.0).abs() < 0.01, "landed on the lower floor: {st:?}");
}

/// The eye (a box `eye_height.clearance` around it, where the camera's near plane reaches) is not inside anything.
fn assert_eye_clear(d: &GameData, level: &Level, st: &MoveState, what: &str) {
    let r = d.movement.eye_height.clearance;
    assert!(level.world.box_free(st.eye_pos(), Vec3::splat(r)), "{what}: the eye is inside the level: {st:?}");
}

/// A floor, a wall across the way north (its face at z -6) and one across the way east (its face at x 4):
/// a corner at (4, -6).
fn walls_level() -> Level {
    let mut level = flat_level();
    level.world.push(Brush::cuboid(Vec3::new(-20.0, 0.0, -6.5), Vec3::new(20.0, 3.0, -6.0), BrushKind::Solid));
    level.world.push(Brush::cuboid(Vec3::new(4.0, 0.0, -20.0), Vec3::new(4.5, 3.0, 20.0), BrushKind::Solid));
    level
}

/// Item 5 (round 3): seeing into walls while sliding. Slides into a wall head-on, at shallow angles, along it
/// (steering into it) and into a corner, from starts at many distances so they reach it at every point of the
/// slide, then the slide ends (crouch let go, or held until it runs out) and the player keeps pushing into it,
/// jumps and stands. The body's box and the eye never go inside the wall, and the feet stay on the floor.
#[test]
fn slides_into_walls_never_go_inside_them() {
    let d = GameData::embedded();
    let level = walls_level();
    let m = mods(&d, WeightClass::None);
    // (what, start, yaw in degrees, steering while sliding)
    let mut cases: Vec<(String, Vec3, f32, Vec2)> = Vec::new();
    for i in 0..8 {
        let back = i as f32 * 0.6;
        cases.push((format!("head-on {back}"), Vec3::new(0.0, 0.0, -2.0 + back), 0.0, Vec2::Y));
        for angle in [5.0, 15.0, 30.0, 60.0, 80.0] {
            // `angle` degrees off the north wall's face (heading north-east, so the east wall comes after).
            let yaw = -(90.0 - angle);
            cases.push((format!("{angle} deg {back}"), Vec3::new(-6.0 - back, 0.0, -3.0), yaw, Vec2::Y));
        }
        // Along the north wall, east into the corner, steering into the wall (left).
        let along = Vec3::new(-4.0 - back, 0.0, -6.0 + 0.33);
        cases.push((format!("along {back}"), along, -90.0, Vec2::new(-0.7, 0.7)));
        cases.push((format!("corner {back}"), Vec3::new(1.0 - back, 0.0, -3.0 + back), -45.0, Vec2::Y));
    }
    for (what, start, yaw_deg, steer) in cases {
        for end in ["release", "hold", "jump"] {
            let at = format!("{what}, {end}");
            let yaw = yaw_deg.to_radians();
            let frame =
                |mv: Vec2, bits: u16| InputFrame { movement: mv, yaw, buttons: Buttons(bits), ..Default::default() };
            let mut st = spawn(&d, start);
            let check = |st: &MoveState, tick: usize| {
                assert_clear(&d, &level, st);
                assert_eye_clear(&d, &level, st, &format!("{at}, tick {tick}"));
                // On the ground: on the floor, or on top of a wall a jump mantled onto (3 m).
                if matches!(st.mode, MoveMode::Ground | MoveMode::Slide) {
                    let on = st.pos.y < 0.01 || (st.pos.y - 3.0).abs() < 0.01;
                    assert!(on, "{at}, tick {tick}: rose to {}", st.pos.y);
                }
            };
            let mut slid = false;
            for t in 0..240 {
                let inp = match t {
                    0..25 => frame(Vec2::Y, Buttons::SPRINT),
                    25..70 => frame(steer, Buttons::CROUCH),
                    _ => match end {
                        "release" => frame(steer, 0),
                        "hold" => frame(steer, Buttons::CROUCH),
                        _ => frame(steer, if t % 20 < 10 { Buttons::JUMP } else { 0 }),
                    },
                };
                step(&d, &level, &mut st, &inp, &m, DT);
                slid |= st.mode == MoveMode::Slide;
                check(&st, t);
            }
            assert!(slid, "{at}: never slid");
        }
    }
}

/// Sliding under a low gap the moment the slide starts: the eye eases down toward a slide's height slower than
/// the head goes under the lintel, so it is held under the lintel instead of looking out of the inside of it.
#[test]
fn the_eye_never_goes_into_a_lintel_the_slide_goes_under() {
    let d = GameData::embedded();
    let level = lintel_level();
    let m = mods(&d, WeightClass::None);
    let mut eye_held = false;
    // The lintel's south face is at z -3, so a standing box reaches z -2.68: slides that start from 5 cm to
    // 2.5 m short of that.
    for i in 0..25 {
        let slide_at = -3.0 + d.movement.capsule.radius + 0.05 + i as f32 * 0.1;
        let mut st = spawn(&d, Vec3::new(0.0, 0.0, 4.0));
        let mut slid = false;
        for t in 0..200 {
            let bits = if st.pos.z > slide_at && !slid { Buttons::SPRINT } else { Buttons::CROUCH };
            step(&d, &level, &mut st, &input(Vec2::Y, bits), &m, DT);
            slid |= st.mode == MoveMode::Slide;
            assert_clear(&d, &level, &st);
            assert_eye_clear(&d, &level, &st, &format!("slide at {slide_at}, tick {t}"));
            assert!(st.pos.y < 0.01, "rose to {}", st.pos.y);
            let under = (-3.25 - 0.4..-3.0 + 0.4).contains(&st.pos.z);
            eye_held |= under && st.eye < d.movement.eye_height.crouch && st.stance == Stance::Slide;
        }
        assert!(slid && st.pos.z < -3.6, "slide at {slide_at}: did not get under: {st:?}");
    }
    assert!(eye_held, "no slide reached the lintel with the eye still easing down");
}

/// A player whose box is inside a ceiling (a stance from elsewhere, an edited map) gets out by going low, or
/// out the shortest way sideways; never up through it (the old 1 cm a tick nudge carried it up through a lintel).
#[test]
fn a_player_inside_a_ceiling_never_rises_through_it() {
    let d = GameData::embedded();
    let m = mods(&d, WeightClass::None);
    // Standing under the 1.1 m lintel: the slide stance fits there, so it just goes low.
    let level = lintel_level();
    let mut st = spawn(&d, Vec3::new(0.0, SKIN, -3.1));
    st.stance = Stance::Stand;
    step(&d, &level, &mut st, &input(Vec2::ZERO, 0), &m, DT);
    assert_eq!(st.stance, Stance::Slide);
    assert!((st.pos - Vec3::new(0.0, SKIN, -3.1)).length() < 1e-3, "{st:?}");
    assert_clear(&d, &level, &st);

    // Under a 0.9 m slab (lower than a slide), 0.3 m in from its south face: out south, on the floor.
    let mut level = flat_level();
    level.world.push(Brush::cuboid(Vec3::new(-5.0, 0.9, -4.0), Vec3::new(5.0, 1.2, -3.0), BrushKind::Solid));
    for (stance, mode) in
        [(Stance::Stand, MoveMode::Ground), (Stance::Crouch, MoveMode::Ground), (Stance::Slide, MoveMode::Slide)]
    {
        for bits in [0, Buttons::JUMP, Buttons::CROUCH] {
            let mut st = spawn(&d, Vec3::new(0.0, SKIN, -3.3));
            st.stance = stance;
            st.mode = mode;
            st.prev_buttons = Buttons(Buttons::CROUCH);
            for t in 0..60 {
                step(&d, &level, &mut st, &input(Vec2::ZERO, bits), &m, DT);
                assert!(st.pos.y < 0.01 || st.mode == MoveMode::Air && st.pos.z > -3.0 + 0.3, "tick {t}: {st:?}");
                assert_clear(&d, &level, &st);
                assert_eye_clear(&d, &level, &st, &format!("{stance:?} {bits}, tick {t}"));
            }
            assert!(st.pos.z >= -3.0 + d.movement.capsule.radius, "{stance:?} {bits}: {st:?}");
        }
    }
}

/// Playtest round 3, "you can't move left or right when airborne": from a standing jump, holding a strafe key
/// steers the player sideways at up to `air_wish_speed` (3.2 m/s) before they land.
#[test]
fn a_standing_jump_can_steer_sideways() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    step(&d, &level, &mut st, &input(Vec2::ZERO, Buttons::JUMP), &m, DT);
    assert_eq!(st.mode, MoveMode::Air);
    let mut fastest: f32 = 0.0;
    while st.mode == MoveMode::Air {
        step(&d, &level, &mut st, &input(Vec2::X, 0), &m, DT);
        fastest = fastest.max(st.horizontal_speed());
    }
    assert!(fastest > 3.0, "sideways in the air: {fastest} m/s");
    assert!(st.pos.x.abs() > 0.8, "moved sideways {} m during the jump", st.pos.x);
}

/// "a form of strafe jumping should be allowed": strafing while turning in the air builds speed past a sprint, but
/// never past `air_strafe_max_speed` (9 m/s), and a player already faster than that only turns.
#[test]
fn strafe_jumping_gains_speed_up_to_its_cap() {
    let d = GameData::embedded();
    let level = flat_level();
    let m = mods(&d, WeightClass::None);
    let cap = d.movement.air.air_strafe_max_speed;
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::Y, Buttons::SPRINT), &m, 60);
    let takeoff = st.horizontal_speed();
    assert!((takeoff - 7.0).abs() < 1e-3);
    let mut best: f32 = 0.0;
    for (side, turn) in [(Vec2::X, -0.03_f32), (Vec2::NEG_X, 0.03), (Vec2::X, -0.06), (Vec2::NEG_X, 0.06)] {
        let mut s = st;
        step(&d, &level, &mut s, &input(Vec2::Y, Buttons::JUMP | Buttons::SPRINT), &m, DT);
        let mut yaw = 0.0;
        while s.mode == MoveMode::Air {
            yaw += turn;
            let mut inp = input(side, 0);
            inp.yaw = yaw;
            step(&d, &level, &mut s, &inp, &m, DT);
            assert!(s.horizontal_speed() <= cap + 1e-3, "{side:?}: {} > {cap}", s.horizontal_speed());
            best = best.max(s.horizontal_speed());
        }
    }
    assert!(best > takeoff + 0.3, "a strafe jump gains speed: {best} from {takeoff}");
    // Already faster than the cap (a slide boost): air control turns that speed but never adds to it.
    let mut s = st;
    step(&d, &level, &mut s, &input(Vec2::Y, Buttons::JUMP | Buttons::SPRINT), &m, DT);
    s.vel.z = -11.0;
    let fast = s.horizontal_speed();
    for _ in 0..20 {
        let mut inp = input(Vec2::X, 0);
        inp.yaw -= 0.05;
        step(&d, &level, &mut s, &inp, &m, DT);
        assert!(s.horizontal_speed() <= fast + 1e-3);
    }
}
