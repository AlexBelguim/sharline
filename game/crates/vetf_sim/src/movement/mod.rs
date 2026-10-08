//! Character controller (design/systems/diagrams/movement_state_machine.png), stepped at the fixed tick.
//!
//! States: GROUND, AIR, SLIDE, JETPACK, MANTLE, ZIPLINE. The same code runs on the host and inside client
//! prediction, so it only depends on the previous state, the input and the static level.

pub mod collision;

use crate::data::{GameData, MovementSpec, WeightClass, WeightEffects};
use crate::input::{Buttons, InputFrame, yaw_basis};
use crate::level::Level;
use collision::{CollisionWorld, SKIN};
use glam::{Vec2, Vec3};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub enum MoveMode {
    #[default]
    Ground,
    Air,
    Slide,
    Jetpack,
    Mantle,
    Zipline,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub enum Stance {
    #[default]
    Stand,
    Crouch,
    Slide,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct MantleMove {
    pub from: Vec3,
    pub to: Vec3,
    pub t: f32,
    pub duration: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ZipRide {
    pub line: u8,
    /// Position along the line, 0 at `a`, 1 at `b`.
    pub s: f32,
    /// +1 rides toward `b`, -1 toward `a`.
    pub dir: f32,
    pub speed: f32,
}

/// Predicted movement state of one player.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct MoveState {
    /// Feet position.
    pub pos: Vec3,
    pub vel: Vec3,
    pub mode: MoveMode,
    pub stance: Stance,
    /// Camera height above the feet (eases between stances).
    pub eye: f32,
    /// Seconds since the feet last touched walkable ground.
    pub since_ground: f32,
    /// Seconds since jump was last pressed (for the jump buffer).
    pub since_jump_press: f32,
    pub fuel: f32,
    pub fuel_regen_wait: f32,
    /// Ground height at take-off: the jetpack fade band is measured from here.
    pub takeoff_y: f32,
    /// Highest feet height since leaving the ground (fall damage).
    pub peak_y: f32,
    pub slide_cooldown: f32,
    pub zip_block: f32,
    pub mantle: Option<MantleMove>,
    pub zip: Option<ZipRide>,
    /// A fresh jump press is needed to light the jetpack (holding jump from the ground does not).
    pub jump_released_in_air: bool,
    pub sprinting: bool,
    pub prev_buttons: Buttons,
}

impl MoveState {
    pub fn spawn(pos: Vec3, fuel: f32) -> Self {
        Self {
            pos,
            vel: Vec3::ZERO,
            mode: MoveMode::Ground,
            stance: Stance::Stand,
            eye: 1.6,
            since_ground: 0.0,
            since_jump_press: f32::MAX,
            fuel,
            fuel_regen_wait: 0.0,
            takeoff_y: pos.y,
            peak_y: pos.y,
            slide_cooldown: 0.0,
            zip_block: 0.0,
            mantle: None,
            zip: None,
            jump_released_in_air: false,
            sprinting: false,
            prev_buttons: Buttons::default(),
        }
    }

    pub fn horizontal_speed(&self) -> f32 {
        Vec2::new(self.vel.x, self.vel.z).length()
    }

    pub fn eye_pos(&self) -> Vec3 {
        self.pos + Vec3::Y * self.eye
    }

    /// Close enough to count as the same state when comparing prediction with the host.
    pub fn approx_eq(&self, o: &Self) -> bool {
        self.mode == o.mode
            && self.stance == o.stance
            && self.pos.distance_squared(o.pos) < 0.01 * 0.01
            && self.vel.distance_squared(o.vel) < 0.05 * 0.05
            && (self.fuel - o.fuel).abs() < 0.02
    }
}

/// Per-player multipliers on top of the movement data (armor weight, held weapon, wounds). Aiming and firing
/// are not among them: they never slow a player or end a sprint (user direction 2026-10-08).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MoveModifiers {
    pub weight: WeightClass,
    pub fx: WeightEffects,
    /// Held weapon x attachments x item in use x wounds, applied to every ground speed.
    pub speed_mult: f32,
    /// The part of `speed_mult` the loadout sets (held weapon x attachments): it scales the slide threshold with
    /// the halo weight, so every loadout slides from its own run, while items and wounds do not lower it.
    pub gear_mult: f32,
    pub legs_broken: bool,
}

impl MoveModifiers {
    pub fn unarmored(data: &GameData) -> Self {
        Self {
            weight: WeightClass::None,
            fx: data.armor.effects(WeightClass::None),
            speed_mult: 1.0,
            gear_mult: 1.0,
            legs_broken: false,
        }
    }

    pub fn max_fuel(&self, m: &MovementSpec) -> f32 {
        m.jetpack.fuel_s * self.fx.fuel
    }
}

/// Things that happened this tick (for sounds, VFX and host-side damage).
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct MoveEvents {
    pub jumped: bool,
    pub landed: bool,
    /// Leg damage from a long fall (host applies it).
    pub fall_damage: f32,
    pub slide_started: bool,
    pub jet_started: bool,
    pub mantle_started: bool,
    pub zip_attached: bool,
    pub zip_detached: bool,
}

const MAX_BUMPS: usize = 4;

fn stance_height(m: &MovementSpec, s: Stance) -> f32 {
    match s {
        Stance::Stand => m.capsule.height_stand,
        Stance::Crouch => m.capsule.height_crouch,
        Stance::Slide => m.capsule.height_slide,
    }
}

fn stance_eye(m: &MovementSpec, s: Stance) -> f32 {
    match s {
        Stance::Stand => m.eye_height.stand,
        Stance::Crouch => m.eye_height.crouch,
        Stance::Slide => m.eye_height.slide,
    }
}

fn half_extents(m: &MovementSpec, s: Stance) -> Vec3 {
    let r = m.capsule.radius;
    Vec3::new(r, stance_height(m, s) * 0.5, r)
}

fn center(pos: Vec3, half: Vec3) -> Vec3 {
    pos + Vec3::Y * half.y
}

fn horizontal(v: Vec3) -> Vec3 {
    Vec3::new(v.x, 0.0, v.z)
}

fn walkable(m: &MovementSpec, n: Vec3) -> bool {
    n.y >= m.ground.max_slope_deg.to_radians().cos()
}

/// Ground under the feet within `reach`: (feet height, normal).
fn probe_ground(
    world: &CollisionWorld,
    m: &MovementSpec,
    pos: Vec3,
    stance: Stance,
    reach: f32,
) -> Option<(f32, Vec3)> {
    let half = half_extents(m, stance);
    let c = center(pos, half);
    let tr = world.trace_box(c, c - Vec3::Y * reach, half);
    (tr.hit() && !tr.start_solid && walkable(m, tr.normal)).then_some((tr.end.y - half.y, tr.normal))
}

fn fits(world: &CollisionWorld, m: &MovementSpec, pos: Vec3, stance: Stance) -> bool {
    let half = half_extents(m, stance);
    let c = center(pos, half) + Vec3::Y * SKIN;
    let tr = world.trace_box(c, c + Vec3::Y * 0.001, half);
    !tr.start_solid
}

/// The tallest stance, up to `want`, that fits at `pos`: standing, then crouching, then the low slide stance.
/// A slide that stops under a gap lower than a crouch (the jammed garage roller, the office shutters) stays low
/// until there is room again, instead of rising into the lintel.
fn settle_stance(world: &CollisionWorld, m: &MovementSpec, pos: Vec3, want: Stance) -> Stance {
    let tallest_first = [Stance::Stand, Stance::Crouch];
    let from = tallest_first.iter().position(|s| *s == want).unwrap_or(tallest_first.len());
    tallest_first[from..].iter().copied().find(|s| fits(world, m, pos, *s)).unwrap_or(Stance::Slide)
}

/// A player whose box is inside something (a stance that did not fit, a state from elsewhere) gets out before it
/// moves: first by going lower (crouch, then the slide's low stance), else the slide box steps out the shortest
/// way, rising or dropping at most a step. Never up through a lintel or a ceiling, nor down through a floor.
fn unstick(world: &CollisionWorld, m: &MovementSpec, st: &mut MoveState) {
    if fits(world, m, st.pos, st.stance) {
        return;
    }
    let lower = match st.stance {
        Stance::Stand => &[Stance::Crouch, Stance::Slide][..],
        Stance::Crouch => &[Stance::Slide][..],
        Stance::Slide => &[][..],
    };
    if let Some(s) = lower.iter().copied().find(|s| fits(world, m, st.pos, *s)) {
        st.stance = s;
        return;
    }
    let half = half_extents(m, Stance::Slide);
    if let Some(push) = world.push_out(center(st.pos, half) + Vec3::Y * SKIN, half, m.ground.step_height) {
        st.pos += push;
        st.stance = Stance::Slide;
        // Whatever it was moving into, it no longer moves into it.
        if st.vel.dot(push) < 0.0 {
            st.vel -= push.normalize_or_zero() * st.vel.dot(push.normalize_or_zero());
        }
    }
}

/// The eye's height above the feet at `pos`, held down so the eye (a box `eye_height.clearance` around it) is
/// never inside anything: above the body's box (the eye easing down toward a slide's height while the head
/// is already under a garage roller) it goes no higher than the open space over the box allows.
fn clear_eye(world: &CollisionWorld, m: &MovementSpec, pos: Vec3, stance: Stance, eye: f32) -> f32 {
    let r = m.eye_height.clearance;
    let top = stance_height(m, stance) - r;
    if eye <= top {
        return eye;
    }
    let half = Vec3::splat(r);
    let tr = world.trace_box(pos + Vec3::Y * top, pos + Vec3::Y * eye, half);
    if tr.start_solid { top } else { tr.end.y - pos.y }
}

/// Quake-style collide-and-slide. Returns the new feet position and velocity. A box that starts inside something
/// steps out the shortest way, rising or dropping at most `max_y` (out of a floor, never up through a lintel).
fn slide_move(world: &CollisionWorld, pos: Vec3, vel: Vec3, half: Vec3, max_y: f32, dt: f32) -> (Vec3, Vec3, bool) {
    let mut p = center(pos, half);
    let mut v = vel;
    let mut left = dt;
    let mut planes: Vec<Vec3> = Vec::with_capacity(MAX_BUMPS);
    let mut blocked = false;
    for _ in 0..MAX_BUMPS {
        if v.length_squared() < 1e-8 || left <= 0.0 {
            break;
        }
        let tr = world.trace_box(p, p + v * left, half);
        if tr.start_solid && tr.fraction == 0.0 {
            // Stuck inside geometry: step out the shortest way and stop this tick. (It used to nudge up 1 cm a
            // tick, which carried a player stuck under a lintel up through it.)
            if let Some(push) = world.push_out(p, half, max_y) {
                p += push;
            }
            v = Vec3::ZERO;
            break;
        }
        p = tr.end;
        if !tr.hit() {
            break;
        }
        blocked = true;
        left *= 1.0 - tr.fraction;
        planes.push(tr.normal);
        v = clip(v, tr.normal);
        // Moving into a crease between two planes: slide along their intersection.
        if planes.len() >= 2 {
            let (a, b) = (planes[planes.len() - 2], planes[planes.len() - 1]);
            if v.dot(a) < 0.0 || v.dot(b) < 0.0 {
                let dir = a.cross(b).normalize_or_zero();
                v = dir * dir.dot(v);
            }
        }
    }
    (p - Vec3::Y * half.y, v, blocked)
}

fn clip(v: Vec3, n: Vec3) -> Vec3 {
    let back = v.dot(n);
    if back < 0.0 { v - n * back * 1.001 } else { v }
}

/// Step-up lifts tried in turn: the full `step_height`, then halves of it. Under a low lintel (the garage roller,
/// the office shutters) the full lift runs the head into the lintel and stops the slide dead, while a smaller
/// one clears the low threshold step in the doorway and keeps going.
const STEP_TRIES: usize = 4;

/// Move with step-up for stairs and small ledges (step height from the data).
fn step_slide_move(
    world: &CollisionWorld,
    m: &MovementSpec,
    pos: Vec3,
    vel: Vec3,
    stance: Stance,
    dt: f32,
) -> (Vec3, Vec3) {
    let half = half_extents(m, stance);
    let max_y = m.ground.step_height;
    let (p1, v1, blocked) = slide_move(world, pos, vel, half, max_y, dt);
    if !blocked || vel.y > 0.1 {
        return (p1, v1);
    }
    // Try again from higher up, then settle back down. A lift whose move is not blocked again wins at once;
    // otherwise the one that gets farthest, if it beats the plain move.
    let c0 = center(pos, half);
    let progress = |p: Vec3| horizontal(p - pos).length_squared();
    let mut best = (p1, v1);
    let mut best_progress = progress(p1) + 1e-6;
    let mut lift = m.ground.step_height;
    for _ in 0..STEP_TRIES {
        let up = world.trace_box(c0, c0 + Vec3::Y * lift, half);
        let raised = up.end - Vec3::Y * half.y;
        let (p2, v2, blocked2) = slide_move(world, raised, Vec3::new(vel.x, 0.0, vel.z), half, max_y, dt);
        let c2 = center(p2, half);
        let down = world.trace_box(c2, c2 - Vec3::Y * (lift + SKIN * 2.0), half);
        if !(down.hit() && !walkable(m, down.normal)) {
            let p2 = down.end - Vec3::Y * half.y;
            if progress(p2) > best_progress {
                best = (p2, Vec3::new(v2.x, v1.y, v2.z));
                best_progress = progress(p2);
                if !blocked2 {
                    break;
                }
            }
        }
        lift *= 0.5;
    }
    best
}

/// Accelerate the horizontal velocity toward `target` (ground model with counter-strafe braking).
fn ground_accel(v: Vec3, target: Vec3, m: &MovementSpec, accel_mult: f32, dt: f32) -> Vec3 {
    let vh = horizontal(v);
    let dv = target - vh;
    if dv.length_squared() < 1e-8 {
        return Vec3::new(target.x, v.y, target.z);
    }
    let rate = if target.length_squared() > 1e-6 && vh.dot(target) < 0.0 {
        m.ground.decel + m.ground.counter_strafe_extra_decel
    } else if target.length() < vh.length() {
        m.ground.decel
    } else {
        m.ground.accel * accel_mult
    };
    let nv = vh + dv.clamp_length_max(rate * dt);
    Vec3::new(nv.x, v.y, nv.z)
}

fn air_accel(v: Vec3, wish_dir: Vec3, wish_speed: f32, accel: f32, cap: f32, dt: f32) -> Vec3 {
    let mut vh = horizontal(v);
    if wish_dir.length_squared() > 0.0 {
        let add = wish_speed - vh.dot(wish_dir);
        if add > 0.0 {
            vh += wish_dir * add.min(accel * dt);
        }
    }
    vh = vh.clamp_length_max(cap.max(0.0));
    Vec3::new(vh.x, v.y, vh.z)
}

/// Advance one player by one fixed tick.
pub fn step(
    data: &GameData,
    level: &Level,
    st: &mut MoveState,
    input: &InputFrame,
    mods: &MoveModifiers,
    dt: f32,
) -> MoveEvents {
    let m = &data.movement;
    let world = &level.world;
    let b = input.buttons;
    let prev = st.prev_buttons;
    st.prev_buttons = b;
    let mut ev = MoveEvents::default();

    let (fwd, right) = yaw_basis(input.yaw);
    let mv = input.movement.clamp_length_max(1.0);
    let wish = (fwd * mv.y + right * mv.x).normalize_or_zero();

    if b.pressed(prev, Buttons::JUMP) {
        st.since_jump_press = 0.0;
    } else {
        st.since_jump_press = (st.since_jump_press + dt).min(10.0);
    }
    if !b.held(Buttons::JUMP) && st.mode != MoveMode::Ground {
        st.jump_released_in_air = true;
    }
    st.slide_cooldown = (st.slide_cooldown - dt).max(0.0);
    st.zip_block = (st.zip_block - dt).max(0.0);

    // Fuel regen (not while thrusting).
    let max_fuel = mods.max_fuel(m);
    if st.mode != MoveMode::Jetpack {
        if st.fuel_regen_wait > 0.0 {
            st.fuel_regen_wait = (st.fuel_regen_wait - dt).max(0.0);
        } else {
            st.fuel = (st.fuel + max_fuel / m.jetpack.regen_full_s * dt).min(max_fuel);
        }
    }

    // Zipline attach (interact near a line, from ground, air or jetpack).
    if b.pressed(prev, Buttons::INTERACT)
        && st.zip_block <= 0.0
        && !mods.legs_broken
        && matches!(st.mode, MoveMode::Ground | MoveMode::Air | MoveMode::Jetpack | MoveMode::Slide)
    {
        let hands = st.pos + Vec3::Y * m.capsule.height_stand;
        if let Some((i, s)) = level.nearest_zipline(hands, m.zipline.attach_radius) {
            let line = &level.ziplines[i];
            let dir = if input.view_dir().dot(line.b - line.a) >= 0.0 { 1.0 } else { -1.0 };
            st.zip = Some(ZipRide { line: i as u8, s, dir, speed: st.horizontal_speed().min(m.zipline.speed_flat) });
            st.mode = MoveMode::Zipline;
            st.stance = Stance::Stand;
            ev.zip_attached = true;
        }
    }

    if matches!(st.mode, MoveMode::Ground | MoveMode::Slide | MoveMode::Air | MoveMode::Jetpack) {
        unstick(world, m, st);
    }

    match st.mode {
        MoveMode::Ground => step_ground(data, world, st, b, prev, fwd, wish, mv, mods, dt, &mut ev),
        MoveMode::Slide => step_slide(data, world, st, b, wish, mods, dt, &mut ev),
        MoveMode::Air | MoveMode::Jetpack => step_air(data, level, st, b, prev, input, wish, mods, dt, &mut ev),
        MoveMode::Mantle => step_mantle(data, world, st, dt),
        MoveMode::Zipline => step_zipline(data, level, st, b, prev, mods, dt, &mut ev),
    }

    // Eye height eases toward the stance height.
    let target_eye = stance_eye(m, st.stance);
    let rate = (m.eye_height.stand - m.eye_height.slide) / m.eye_height.transition_s.max(1e-3);
    st.eye += (target_eye - st.eye).clamp(-rate * dt, rate * dt);
    st.eye = clear_eye(world, m, st.pos, st.stance, st.eye);

    // Fell out of the map: the host respawns the player; keep the state sane meanwhile.
    if st.pos.y < level.kill_y {
        st.vel = Vec3::ZERO;
    }
    ev
}

#[allow(clippy::too_many_arguments)]
fn step_ground(
    data: &GameData,
    world: &CollisionWorld,
    st: &mut MoveState,
    b: Buttons,
    prev: Buttons,
    fwd: Vec3,
    wish: Vec3,
    mv: Vec2,
    mods: &MoveModifiers,
    dt: f32,
    ev: &mut MoveEvents,
) {
    let m = &data.movement;
    st.since_ground = 0.0;
    st.jump_released_in_air = false;

    // Crouch / slide entry.
    let crouch = b.held(Buttons::CROUCH);
    if crouch && b.pressed(prev, Buttons::CROUCH) && can_slide(m, st, fwd, mods) {
        start_slide(m, st, mods, ev);
        return step_slide(data, world, st, b, wish, mods, dt, ev);
    }
    let want = if crouch { Stance::Crouch } else { Stance::Stand };
    if st.stance != want {
        st.stance = settle_stance(world, m, st.pos, want);
    }

    // Target speed. Aiming or firing never stops a sprint.
    let sprint_ok = b.held(Buttons::SPRINT)
        && !mods.legs_broken
        && st.stance == Stance::Stand
        && mv.y > 0.0
        && mv.x.atan2(mv.y).abs() <= m.speed.sprint_max_angle_deg.to_radians() + 1e-4;
    st.sprinting = sprint_ok;
    // Crouched, or still low after a slide that stopped under a gap: crouch speed.
    let mut target_speed = if st.stance != Stance::Stand {
        m.speed.crouch
    } else if sprint_ok {
        m.speed.sprint
    } else if b.held(Buttons::WALK) {
        m.speed.walk
    } else {
        m.speed.jog
    };
    if mv.y < 0.0 {
        target_speed *= m.speed.backpedal_mult;
    }
    target_speed *= mods.fx.move_mult * mods.speed_mult;
    let target = wish * target_speed * mv.length().min(1.0);
    st.vel = ground_accel(st.vel, target, m, mods.fx.accel, dt);
    st.vel.y = 0.0;

    // Jump (buffered).
    if st.since_jump_press <= m.air.jump_buffer_s && b.held(Buttons::JUMP) && fits(world, m, st.pos, Stance::Stand) {
        st.stance = Stance::Stand;
        st.vel.y = m.air.jump_v0;
        st.since_jump_press = f32::MAX;
        enter_air(st);
        ev.jumped = true;
        let (p, v) = step_slide_move(world, m, st.pos, st.vel, st.stance, dt);
        st.pos = p;
        st.vel = v;
        return;
    }

    let (p, v) = step_slide_move(world, m, st.pos, st.vel, st.stance, dt);
    st.pos = p;
    st.vel = Vec3::new(v.x, 0.0, v.z);

    // Stick to the ground (down slopes and stairs), or start falling.
    match probe_ground(world, m, st.pos, st.stance, m.ground.ground_snap + m.ground.step_height) {
        Some((y, _)) => st.pos.y = y,
        None => enter_air(st),
    }
}

/// Crouch starts a slide (from the ground, or on landing) when moving at least `slide.min_entry_speed` (scaled by
/// the halo weight and the gear, like the run itself, so a Heavy halo with a slow gun still slides from its run),
/// within `slide.entry_max_angle_deg` of where the player faces: a run or a sprint forward slides, a crouch while
/// strafing or backpedalling does not.
fn can_slide(m: &MovementSpec, st: &MoveState, fwd: Vec3, mods: &MoveModifiers) -> bool {
    let vh = horizontal(st.vel);
    let speed = vh.length();
    let cone = m.slide.entry_max_angle_deg.to_radians().cos();
    let min = slide_entry_speed(m, mods);
    !mods.legs_broken && speed >= min && vh.dot(fwd) >= speed * cone - 1e-4
}

/// The speed a slide needs for this player: `slide.min_entry_speed` scaled by the halo weight and the gear.
pub fn slide_entry_speed(m: &MovementSpec, mods: &MoveModifiers) -> f32 {
    m.slide.min_entry_speed * mods.fx.move_mult * mods.gear_mult
}

fn enter_air(st: &mut MoveState) {
    st.mode = MoveMode::Air;
    st.takeoff_y = st.pos.y;
    st.peak_y = st.pos.y;
    st.sprinting = false;
}

fn start_slide(m: &MovementSpec, st: &mut MoveState, mods: &MoveModifiers, ev: &mut MoveEvents) {
    st.mode = MoveMode::Slide;
    st.stance = Stance::Slide;
    st.sprinting = false;
    if st.slide_cooldown <= 0.0 {
        let vh = horizontal(st.vel);
        let boosted = vh.normalize_or_zero() * (vh.length() + mods.fx.slide_boost).min(m.slide.max_speed);
        st.vel = Vec3::new(boosted.x, st.vel.y, boosted.z);
        st.slide_cooldown = m.slide.boost_cooldown_s;
    }
    ev.slide_started = true;
}

#[allow(clippy::too_many_arguments)]
fn step_slide(
    data: &GameData,
    world: &CollisionWorld,
    st: &mut MoveState,
    b: Buttons,
    wish: Vec3,
    mods: &MoveModifiers,
    dt: f32,
    ev: &mut MoveEvents,
) {
    let m = &data.movement;
    st.since_ground = 0.0;
    let ground = probe_ground(world, m, st.pos, Stance::Slide, m.ground.ground_snap + m.ground.step_height);
    let Some((gy, normal)) = ground else {
        enter_air(st);
        st.stance = settle_stance(world, m, st.pos, Stance::Crouch);
        return;
    };
    st.pos.y = gy;

    // Jump out of a slide keeps most of the speed.
    if b.held(Buttons::JUMP) && st.since_jump_press <= m.air.jump_buffer_s && fits(world, m, st.pos, Stance::Stand) {
        let vh = horizontal(st.vel) * m.slide.jump_keep_frac;
        st.vel = Vec3::new(vh.x, m.air.jump_v0, vh.z);
        st.stance = Stance::Stand;
        st.since_jump_press = f32::MAX;
        enter_air(st);
        ev.jumped = true;
        return;
    }

    // Friction, plus gravity along the slope when going downhill.
    let mut vh = horizontal(st.vel);
    let speed = vh.length();
    let dir = vh.normalize_or_zero();
    let downhill = horizontal(normal).normalize_or_zero();
    let slope = normal.y.clamp(-1.0, 1.0).acos();
    let mut accel = -m.slide.friction;
    if slope >= m.slide.downhill_min_deg.to_radians() {
        accel += m.air.gravity * slope.sin() * dir.dot(downhill);
    }
    let mut new_speed = (speed + accel * dt).clamp(0.0, m.slide.max_speed);
    // Steering toward the input direction.
    if wish.length_squared() > 0.0 && dir.length_squared() > 0.0 {
        let max_turn = m.slide.steer_deg_per_s.to_radians() * dt;
        let ang = dir.x.atan2(dir.z);
        let target = wish.x.atan2(wish.z);
        let mut delta = (target - ang + std::f32::consts::PI).rem_euclid(std::f32::consts::TAU) - std::f32::consts::PI;
        delta = delta.clamp(-max_turn, max_turn);
        let a = ang + delta;
        vh = Vec3::new(a.sin(), 0.0, a.cos()) * new_speed;
    } else {
        vh = dir * new_speed;
    }
    if speed <= 1e-4 {
        new_speed = 0.0;
        vh = Vec3::ZERO;
    }
    st.vel = Vec3::new(vh.x, 0.0, vh.z);

    let (p, v) = step_slide_move(world, m, st.pos, st.vel, Stance::Slide, dt);
    st.pos = p;
    st.vel = Vec3::new(v.x, 0.0, v.z);
    if let Some((y, _)) = probe_ground(world, m, st.pos, Stance::Slide, m.ground.ground_snap + m.ground.step_height) {
        st.pos.y = y;
    }

    // End of the slide.
    if new_speed < m.slide.end_speed || !b.held(Buttons::CROUCH) || mods.legs_broken {
        st.mode = MoveMode::Ground;
        let want = if b.held(Buttons::CROUCH) { Stance::Crouch } else { Stance::Stand };
        st.stance = settle_stance(world, m, st.pos, want);
    }
}

#[allow(clippy::too_many_arguments)]
fn step_air(
    data: &GameData,
    level: &Level,
    st: &mut MoveState,
    b: Buttons,
    prev: Buttons,
    input: &InputFrame,
    wish: Vec3,
    mods: &MoveModifiers,
    dt: f32,
    ev: &mut MoveEvents,
) {
    let m = &data.movement;
    let world = &level.world;
    st.since_ground += dt;
    st.sprinting = false;
    // Crouch does not lower a standing player in the air, but releasing it stands up when there is room.
    let want = if b.held(Buttons::CROUCH) { Stance::Crouch } else { Stance::Stand };
    if st.stance == Stance::Slide || (st.stance == Stance::Crouch && want == Stance::Stand) {
        st.stance = settle_stance(world, m, st.pos, want);
    }

    // Coyote jump: walked off a ledge a moment ago.
    if st.mode == MoveMode::Air
        && st.since_ground <= m.air.coyote_s
        && st.vel.y <= 0.0
        && b.pressed(prev, Buttons::JUMP)
    {
        st.vel.y = m.air.jump_v0;
        st.since_ground = f32::MAX / 2.0;
        st.since_jump_press = f32::MAX;
        ev.jumped = true;
    }

    // Mantle: a ledge in reach ahead while jump is held and moving forward.
    if b.held(Buttons::JUMP)
        && input.movement.y > 0.1
        && let Some(mantle) = find_mantle(m, world, st, input.yaw, mods)
    {
        st.mode = MoveMode::Mantle;
        st.mantle = Some(mantle);
        st.vel = Vec3::ZERO;
        ev.mantle_started = true;
        return;
    }

    // Jetpack: a fresh jump press in the air lights it; releasing or running dry ends it.
    let min_fuel = mods.max_fuel(m) * m.jetpack.min_fuel_frac;
    if st.mode == MoveMode::Air
        && b.pressed(prev, Buttons::JUMP)
        && st.jump_released_in_air
        && !ev.jumped
        && st.fuel >= min_fuel
        && !mods.legs_broken
    {
        st.mode = MoveMode::Jetpack;
        st.vel.y = st.vel.y.max(0.0) + m.jetpack.kick_up_mps;
        st.fuel = (st.fuel - m.jetpack.kick_cost_s).max(0.0);
        ev.jet_started = true;
    } else if st.mode == MoveMode::Jetpack && (!b.held(Buttons::JUMP) || st.fuel <= 0.0 || mods.legs_broken) {
        st.mode = MoveMode::Air;
    }

    if st.mode == MoveMode::Jetpack {
        st.fuel = (st.fuel - dt).max(0.0);
        st.fuel_regen_wait = m.jetpack.regen_delay_s;
        let (lo, hi) = m.jetpack.fade_band(mods.weight);
        let rise = st.pos.y - st.takeoff_y;
        let fade = 1.0 - ((rise - lo) / (hi - lo).max(1e-3)).clamp(0.0, 1.0);
        let net = m.jetpack.thrust * fade - m.air.gravity;
        let cap = m.jetpack.climb_cap;
        st.vel.y = if st.vel.y >= cap {
            // Above the climb cap (after the kick): thrust holds, gravity slows it back to the cap.
            (st.vel.y - m.air.gravity * dt).max(cap.min(st.vel.y + net * dt))
        } else if net > 0.0 {
            (st.vel.y + net * dt).min(cap)
        } else {
            st.vel.y + net * dt
        };
        let cap_h = m.jetpack.horizontal_cap * mods.fx.move_mult;
        st.vel = air_accel(st.vel, wish, cap_h, m.jetpack.air_accel, horizontal(st.vel).length().max(cap_h), dt);
    } else {
        st.vel.y = (st.vel.y - m.air.gravity * dt).max(-m.air.terminal_speed);
        st.vel = air_accel(st.vel, wish, m.air.air_wish_speed, m.air.air_accel, m.air.max_horizontal_speed, dt);
    }

    let falling = st.vel.y <= 0.0;
    let (p, v) = step_slide_move(world, m, st.pos, st.vel, st.stance, dt);
    st.pos = p;
    st.vel = v;
    st.peak_y = st.peak_y.max(st.pos.y);

    // Landing (the slide move's overclip can leave a tiny upward velocity, so use the pre-move sign).
    if (falling || st.vel.y <= 0.0)
        && let Some((y, _)) = probe_ground(world, m, st.pos, st.stance, 0.05)
    {
        st.pos.y = y;
        let drop = st.peak_y - y;
        if drop > m.fall_damage.free_drop_m {
            ev.fall_damage = (drop - m.fall_damage.free_drop_m) * m.fall_damage.legs_hp_per_m;
        }
        ev.landed = true;
        st.vel.y = 0.0;
        st.since_ground = 0.0;
        if b.held(Buttons::CROUCH) && can_slide(m, st, yaw_basis(input.yaw).0, mods) {
            start_slide(m, st, mods, ev);
        } else {
            st.mode = MoveMode::Ground;
        }
    }
}

/// Look for a ledge ahead that can be mantled.
fn find_mantle(
    m: &MovementSpec,
    world: &CollisionWorld,
    st: &MoveState,
    yaw: f32,
    mods: &MoveModifiers,
) -> Option<MantleMove> {
    let mt = &m.mantle;
    let (fwd, _) = yaw_basis(yaw);
    let r = m.capsule.radius;
    // Something solid must be right in front of the body.
    let half = half_extents(m, st.stance);
    let c = center(st.pos, half);
    let wall = world.trace_box(c, c + fwd * mt.probe_forward, half);
    if !wall.hit() || wall.normal.y.abs() > 0.3 {
        return None;
    }
    // Probe down onto the ledge, one body-width past the wall face.
    let reach = horizontal(wall.end - c).length() + r + mt.min_ledge_depth * 0.5;
    let top = st.pos.y + mt.max_ledge + 0.05;
    let probe = Vec3::new(c.x, top, c.z) + fwd * reach;
    let down =
        world.trace_box(probe, probe - Vec3::Y * (mt.max_ledge - mt.min_ledge + 0.05), Vec3::new(0.05, 0.0, 0.05));
    if !down.hit() || down.start_solid || !walkable(m, down.normal) {
        return None;
    }
    let ledge = down.end.y;
    let height = ledge - st.pos.y;
    if !(mt.min_ledge..=mt.max_ledge).contains(&height) {
        return None;
    }
    // Room to crouch on top, and the ledge is deep enough.
    let target = Vec3::new(probe.x, ledge, probe.z);
    let deep = target + fwd * (mt.min_ledge_depth * 0.5);
    let deep_tr = world.trace_box(deep + Vec3::Y * 0.3, deep - Vec3::Y * 0.1, Vec3::new(0.05, 0.0, 0.05));
    if !deep_tr.hit() || (deep_tr.end.y - ledge).abs() > 0.15 {
        return None;
    }
    let crouch_half = Vec3::new(r, mt.min_headroom * 0.5, r);
    let room = world.trace_box(
        center(target, crouch_half) + Vec3::Y * SKIN,
        center(target, crouch_half) + Vec3::Y * 0.002,
        crouch_half,
    );
    if room.start_solid {
        return None;
    }
    let base = if height <= mt.low_max { mt.time_low_s } else { mt.time_high_s };
    Some(MantleMove { from: st.pos, to: target, t: 0.0, duration: base * mods.fx.mantle })
}

fn step_mantle(data: &GameData, world: &CollisionWorld, st: &mut MoveState, dt: f32) {
    let m = &data.movement;
    st.sprinting = false;
    let Some(mut mm) = st.mantle else {
        st.mode = MoveMode::Air;
        return;
    };
    mm.t = (mm.t + dt / mm.duration.max(1e-3)).min(1.0);
    // Rise first (70% of the time), then move over the ledge.
    let k = mm.t;
    let rise = (k / 0.7).min(1.0);
    let over = ((k - 0.5) / 0.5).clamp(0.0, 1.0);
    let y = mm.from.y + (mm.to.y - mm.from.y) * rise;
    let xz = horizontal(mm.from).lerp(horizontal(mm.to), over);
    // Up, then over, each traced: the move over starts while the body is still rising, and untraced it cut
    // through the ledge's edge (the view inside the wall for a moment). Held back, it catches up as it rises.
    st.stance = Stance::Crouch;
    let half = half_extents(m, Stance::Crouch);
    let c0 = center(st.pos, half);
    let up = world.trace_box(c0, Vec3::new(c0.x, y + half.y, c0.z), half);
    let over = world.trace_box(up.end, Vec3::new(xz.x, up.end.y, xz.z), half);
    st.pos = over.end - Vec3::Y * half.y;
    if mm.t >= 1.0 {
        st.mantle = None;
        st.mode = MoveMode::Ground;
        st.pos = mm.to;
        if fits(world, m, st.pos, Stance::Stand) {
            st.stance = Stance::Stand;
        }
    } else {
        st.mantle = Some(mm);
    }
}

#[allow(clippy::too_many_arguments)]
fn step_zipline(
    data: &GameData,
    level: &Level,
    st: &mut MoveState,
    b: Buttons,
    prev: Buttons,
    mods: &MoveModifiers,
    dt: f32,
    ev: &mut MoveEvents,
) {
    let m = &data.movement;
    let z = &m.zipline;
    st.sprinting = false;
    let Some(mut ride) = st.zip else {
        enter_air(st);
        return;
    };
    let Some(line) = level.ziplines.get(ride.line as usize) else {
        st.zip = None;
        enter_air(st);
        return;
    };
    let along = (line.b - line.a) * ride.dir;
    let len = along.length().max(1e-3);
    let dir = along / len;
    // Downhill is faster, uphill slower.
    let target = (z.speed_flat - dir.y * 15.0).clamp(z.speed_min, z.speed_max);
    let accel = z.speed_flat / z.accel_s.max(1e-3);
    ride.speed += (target - ride.speed).clamp(-accel * dt, accel * dt);
    ride.s += ride.dir * ride.speed * dt / len;
    let hang = m.capsule.height_stand + 0.2;
    let at_end = !(0.0..=1.0).contains(&ride.s);
    ride.s = ride.s.clamp(0.0, 1.0);
    st.pos = line.a.lerp(line.b, ride.s) - Vec3::Y * hang;
    st.vel = dir * ride.speed;
    st.stance = Stance::Stand;

    let detach = |st: &mut MoveState, vel: Vec3, ev: &mut MoveEvents| {
        st.zip = None;
        st.vel = vel;
        st.zip_block = z.reattach_block_s;
        enter_air(st);
        st.jump_released_in_air = false;
        ev.zip_detached = true;
    };
    if b.pressed(prev, Buttons::JUMP) {
        detach(st, st.vel * z.detach_keep_frac + Vec3::Y * z.detach_up, ev);
    } else if b.pressed(prev, Buttons::CROUCH) || mods.legs_broken {
        detach(st, st.vel * z.detach_keep_frac, ev);
    } else if at_end {
        detach(st, st.vel * z.detach_keep_frac + Vec3::Y * z.end_hop_up, ev);
    } else {
        st.zip = Some(ride);
    }
}

#[cfg(test)]
mod tests;
