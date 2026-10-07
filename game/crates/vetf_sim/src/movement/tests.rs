use super::collision::{Brush, BrushKind};
use super::*;
use crate::level::{Level, Zipline};

const DT: f32 = 1.0 / 60.0;

fn flat_level() -> Level {
    let mut level = Level { name: "test".into(), kill_y: -50.0, ..Default::default() };
    level.world.push(Brush::cuboid(Vec3::new(-200.0, -1.0, -200.0), Vec3::new(200.0, 0.0, 200.0), BrushKind::Solid));
    level
}

fn mods(d: &GameData, wc: WeightClass) -> MoveModifiers {
    MoveModifiers { weight: wc, fx: d.armor.effects(wc), speed_mult: 1.0, legs_broken: false, ads: false }
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
fn no_sprint_sideways_or_aiming() {
    let d = GameData::embedded();
    let level = flat_level();
    let mut m = mods(&d, WeightClass::None);
    let mut st = spawn(&d, Vec3::ZERO);
    run(&d, &level, &mut st, input(Vec2::X, Buttons::SPRINT), &m, 30);
    assert!(!st.sprinting);
    m.ads = true;
    run(&d, &level, &mut st, input(Vec2::Y, Buttons::SPRINT), &m, 30);
    assert!(!st.sprinting);
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
    assert!(st.horizontal_speed() > 8.8, "boosted: {}", st.horizontal_speed());
    // (9.0 - 3.6) / 4.5 = 1.2 s of sliding on flat ground
    let mut ticks = 0;
    while st.mode == MoveMode::Slide && ticks < 300 {
        step(&d, &level, &mut st, &input(Vec2::Y, Buttons::CROUCH), &m, DT);
        ticks += 1;
    }
    assert!((60..=80).contains(&ticks), "{ticks}");
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
