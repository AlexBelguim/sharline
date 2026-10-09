//! Throwables: smoke grenades and molotovs (item 10b), the base the underbarrel launcher's grenades will reuse.
//!
//! - **The hand** ([`ThrowHand`], in the predicted [`crate::items::ItemState`]): a throw key starts a short wind-up
//!   (the gun goes down), the grenade leaves the hand at its end ([`launch`]: from the right hand, along the aim
//!   lifted a little, plus some of the thrower's own velocity), and the gun comes back up after a recovery. How
//!   many each life carries is the loadout's [`ThrowKit`] (`rules.ron` `throwables`).
//! - **The flight** ([`Projectile`]): a small ball under gravity that bounces off the level (data-driven
//!   restitution and friction) and comes to rest on a floor. A smoke pops after its fuse or once it lies still; a
//!   molotov bursts on its first impact (on a wall, the fire takes the ground below).
//! - **The areas** ([`Smoke`], [`Fire`]): a smoke cloud grows, holds and thins out, and while dense it hides what is
//!   behind it ([`ThrowWorld::sight_blocked`]: bots, markers). Fire spreads over the ground and burns anyone whose
//!   feet are in it ([`burn`], through the halo and health rules). Smoke puts out fire ([`douses`]).
//! - **Bullet tunnels** ([`Tunnels`]): a bullet through smoke clears a see-through path for a moment, which then
//!   refills. Visual and local to each client (the host's sight test ignores them); the ring of recent segments
//!   lives here so its ageing is tested with the rest.
//!
//! Everything is deterministic (fixed ticks, no randomness): the host runs the [`ThrowWorld`], and a client flies
//! the same arcs from the host's launch messages (its own throw at once, predicted). Numbers:
//! `game/assets/data/throwables.ron`.

use crate::combat::{HaloSpec, HaloState, Health};
use crate::data::SpillToTorso;
use crate::input::{Buttons, MAX_PITCH, view_dir, view_rotation};
use crate::level::Level;
use crate::movement::collision::CollisionWorld;
use crate::weapon::secs_to_ticks;
use crate::zone::Zone;
use glam::Vec3;
use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------------------------- kinds and kits

/// What can be thrown.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ThrowKind {
    Smoke,
    Molotov,
}

impl ThrowKind {
    pub const ALL: [ThrowKind; 2] = [ThrowKind::Smoke, ThrowKind::Molotov];

    /// Its throw key's bit in [`Buttons`].
    pub fn button(self) -> u16 {
        match self {
            ThrowKind::Smoke => Buttons::THROW_SMOKE,
            ThrowKind::Molotov => Buttons::THROW_MOLOTOV,
        }
    }

    /// The HUD's word for it.
    pub fn label(self) -> &'static str {
        match self {
            ThrowKind::Smoke => "SMOKE",
            ThrowKind::Molotov => "MOLOTOV",
        }
    }
}

/// Throwables carried: how many of each (a life's share, `rules.ron` `throwables`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub struct ThrowKit {
    pub smoke: u8,
    pub molotov: u8,
}

impl ThrowKit {
    pub fn get(&self, kind: ThrowKind) -> u8 {
        match kind {
            ThrowKind::Smoke => self.smoke,
            ThrowKind::Molotov => self.molotov,
        }
    }

    fn slot(&mut self, kind: ThrowKind) -> &mut u8 {
        match kind {
            ThrowKind::Smoke => &mut self.smoke,
            ThrowKind::Molotov => &mut self.molotov,
        }
    }

    /// Take one, if any is left.
    pub fn take(&mut self, kind: ThrowKind) -> bool {
        let n = self.slot(kind);
        if *n == 0 {
            return false;
        }
        *n -= 1;
        true
    }

    pub fn total(&self) -> u32 {
        self.smoke as u32 + self.molotov as u32
    }
}

// ---------------------------------------------------------------------------------------------- data

/// `throwables.ron`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ThrowablesFile {
    pub throw: ThrowSpec,
    pub projectile: ProjectileSpec,
    pub smoke: SmokeSpec,
    pub molotov: MolotovSpec,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ThrowSpec {
    pub windup_s: f32,
    pub recover_s: f32,
    pub speed_mps: f32,
    pub lift_deg: f32,
    pub inherit: f32,
    /// From the eye in view space: right, up, forward (m).
    pub hand: (f32, f32, f32),
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ProjectileSpec {
    pub radius_m: f32,
    pub gravity: f32,
    pub restitution: f32,
    pub friction: f32,
    pub rest_speed_mps: f32,
    pub max_flight_s: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SmokeSpec {
    pub fuse_s: f32,
    pub radius_m: f32,
    pub height_m: f32,
    pub lift_m: f32,
    pub grow_s: f32,
    pub hold_s: f32,
    pub fade_s: f32,
    pub sight_min_density: f32,
    pub sight_chord_m: f32,
    pub douse_overlap_m: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct MolotovSpec {
    pub ground_drop_m: f32,
    pub radius_m: f32,
    pub spread_s: f32,
    pub burn_s: f32,
    pub height_m: f32,
    pub damage: FireDamage,
}

/// Burn damage, through the usual halo and health rules.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct FireDamage {
    pub dps: f32,
    pub pulse_s: f32,
    pub zone: Zone,
    /// The share of each pulse the zone's halo arc soaks while it holds (0..1).
    pub shield_soak: f32,
}

impl ThrowablesFile {
    /// Every number finite and in range.
    pub fn validate(&self) -> Result<(), String> {
        let (t, p, s, m) = (&self.throw, &self.projectile, &self.smoke, &self.molotov);
        let all = [
            t.windup_s,
            t.recover_s,
            t.speed_mps,
            t.lift_deg,
            t.inherit,
            t.hand.0,
            t.hand.1,
            t.hand.2,
            p.radius_m,
            p.gravity,
            p.restitution,
            p.friction,
            p.rest_speed_mps,
            p.max_flight_s,
            s.fuse_s,
            s.radius_m,
            s.height_m,
            s.lift_m,
            s.grow_s,
            s.hold_s,
            s.fade_s,
            s.sight_min_density,
            s.sight_chord_m,
            s.douse_overlap_m,
            m.ground_drop_m,
            m.radius_m,
            m.spread_s,
            m.burn_s,
            m.height_m,
            m.damage.dps,
            m.damage.pulse_s,
            m.damage.shield_soak,
        ];
        if all.iter().any(|x| !x.is_finite()) {
            return Err("throwables.ron: every number must be finite".into());
        }
        let positive = [
            t.speed_mps,
            p.radius_m,
            p.gravity,
            p.max_flight_s,
            s.fuse_s,
            s.radius_m,
            s.height_m,
            s.grow_s,
            m.radius_m,
            m.burn_s,
            m.height_m,
            m.damage.pulse_s,
        ];
        if positive.iter().any(|x| *x <= 0.0) {
            return Err("throwables.ron: speeds, sizes, gravity, fuse, growth, burn and pulse must be above 0".into());
        }
        let shares = [p.restitution, p.friction, t.inherit, s.sight_min_density, m.damage.shield_soak];
        if shares.iter().any(|x| !(0.0..=1.0).contains(x)) {
            return Err(
                "throwables.ron: restitution, friction, inherit, sight_min_density, shield_soak within 0..1".into()
            );
        }
        if t.windup_s < 0.0 || t.recover_s < 0.0 || s.hold_s < 0.0 || s.fade_s < 0.0 || m.spread_s < 0.0 {
            return Err("throwables.ron: times must not be negative".into());
        }
        if m.damage.dps < 0.0 || m.ground_drop_m < 0.0 || s.douse_overlap_m < 0.0 || s.sight_chord_m < 0.0 {
            return Err(
                "throwables.ron: dps, ground_drop_m, douse_overlap_m and sight_chord_m must be 0 or more".into()
            );
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------------------------- the hand

/// A throw winding up: what, and the ticks until it leaves the hand.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Windup {
    pub kind: ThrowKind,
    pub left: u16,
}

/// Throwables in hand: how many are left this life, a throw in progress, and the throw counter. Predicted by
/// the owner like the rest of [`crate::items::ItemState`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub struct ThrowHand {
    pub left: ThrowKit,
    pub windup: Option<Windup>,
    /// Ticks until the gun comes back up after a throw.
    pub recover: u16,
    /// Throws so far this life: a throw's number (with its thrower) names its grenade on the host and every
    /// client.
    pub seq: u16,
    /// Last tick's throw keys (a press starts a throw; a held key does not throw again).
    pub keys: u16,
}

/// What the hand did this tick.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct HandEvents {
    pub started: Option<ThrowKind>,
    /// A grenade left the hand: its kind and number.
    pub released: Option<(ThrowKind, u16)>,
}

impl ThrowHand {
    pub fn new(kit: ThrowKit) -> Self {
        Self { left: kit, ..Default::default() }
    }

    /// Winding up or recovering: the gun is down.
    pub fn busy(&self) -> bool {
        self.windup.is_some() || self.recover > 0
    }

    /// Advance one tick. `can_start`: the hands are free (the gun idle, no item in use, not mantling).
    pub fn step(&mut self, spec: &ThrowSpec, buttons: Buttons, can_start: bool, tick_hz: u32) -> HandEvents {
        let mut ev = HandEvents::default();
        let keys = buttons.0 & (Buttons::THROW_SMOKE | Buttons::THROW_MOLOTOV);
        let pressed = keys & !self.keys;
        self.keys = keys;
        if let Some(w) = &mut self.windup {
            w.left = w.left.saturating_sub(1);
            if w.left == 0 {
                let kind = w.kind;
                self.windup = None;
                self.recover = secs_to_ticks(spec.recover_s, tick_hz);
                self.seq = self.seq.wrapping_add(1);
                ev.released = Some((kind, self.seq));
            }
            return ev;
        }
        if self.recover > 0 {
            self.recover -= 1;
            return ev;
        }
        if !can_start {
            return ev;
        }
        if let Some(kind) = ThrowKind::ALL.into_iter().find(|k| pressed & k.button() != 0 && self.left.get(*k) > 0) {
            self.left.take(kind);
            self.windup = Some(Windup { kind, left: secs_to_ticks(spec.windup_s, tick_hz).max(1) });
            ev.started = Some(kind);
        }
        ev
    }
}

/// A grenade leaving the hand.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Launch {
    pub kind: ThrowKind,
    pub seq: u16,
    pub origin: Vec3,
    pub vel: Vec3,
}

/// Where a throw leaves from and how fast: from the hand (in view space from the `eye`; from the eye itself when
/// the hand is inside a wall), along the view lifted by `lift_deg`, plus `inherit` of the thrower's velocity.
pub fn launch(
    spec: &ThrowSpec,
    world: &CollisionWorld,
    eye: Vec3,
    body_vel: Vec3,
    yaw: f32,
    pitch: f32,
) -> (Vec3, Vec3) {
    let (r, u, f) = spec.hand;
    let hand = eye + view_rotation(yaw, pitch) * Vec3::new(r, u, -f);
    let origin = if world.trace_solid(eye, hand, Vec3::ZERO).hit() { eye } else { hand };
    let aim = view_dir(yaw, (pitch + spec.lift_deg.to_radians()).clamp(-MAX_PITCH, MAX_PITCH));
    (origin, aim * spec.speed_mps + body_vel * spec.inherit)
}

// ---------------------------------------------------------------------------------------------- the flight

/// Names a grenade (and the area it makes) on the host and on every client: the thrower and their throw number.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ThrowId {
    pub owner: u64,
    pub seq: u16,
}

/// A grenade in the air (or lying on the ground, a smoke waiting for its fuse).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Projectile {
    pub id: ThrowId,
    pub kind: ThrowKind,
    pub pos: Vec3,
    pub vel: Vec3,
    /// Ticks since the throw.
    pub age: u32,
    pub resting: bool,
}

/// What a grenade did this tick.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Flight {
    Flying,
    /// It bounced off something, hitting it at `speed` (m/s into the surface).
    Bounced {
        at: Vec3,
        speed: f32,
    },
    /// It went off: a smoke pops, a molotov bursts. `at` is the ground point the area grows from.
    Burst {
        at: Vec3,
    },
    /// It fell out of the map.
    Lost,
}

/// A bounce this soft makes no sound.
const QUIET_BOUNCE_MPS: f32 = 1.0;

impl Projectile {
    pub fn new(id: ThrowId, l: &Launch) -> Self {
        Self { id, kind: l.kind, pos: l.origin, vel: l.vel, age: 0, resting: false }
    }

    /// Advance one tick of `dt` seconds.
    pub fn step(&mut self, data: &ThrowablesFile, level: &Level, dt: f32) -> Flight {
        let p = &data.projectile;
        self.age += 1;
        if self.pos.y < level.kill_y {
            return Flight::Lost;
        }
        let flight_s = self.age as f32 * dt;
        let mut out = Flight::Flying;
        if !self.resting {
            let half = Vec3::splat(p.radius_m);
            self.vel.y -= p.gravity * dt;
            let mut left = 1.0f32;
            for _ in 0..4 {
                let end = self.pos + self.vel * dt * left;
                let tr = level.world.trace_solid(self.pos, end, half);
                if !tr.hit() {
                    self.pos = end;
                    break;
                }
                self.pos = tr.end;
                left *= 1.0 - tr.fraction;
                let n = tr.normal;
                if self.kind == ThrowKind::Molotov || n == Vec3::ZERO {
                    // A molotov bursts on its first impact; a grenade stuck inside a wall goes off there.
                    return Flight::Burst { at: self.ground_point(data, level, n) };
                }
                let into = self.vel.dot(n);
                if into < 0.0 {
                    let along = self.vel - n * into;
                    self.vel = along * p.friction - n * into * p.restitution;
                    if -into >= QUIET_BOUNCE_MPS {
                        out = Flight::Bounced { at: self.pos, speed: -into };
                    }
                }
                if n.y > 0.7 && self.vel.length() < p.rest_speed_mps {
                    self.vel = Vec3::ZERO;
                    self.resting = true;
                    break;
                }
                if left <= 1e-4 {
                    break;
                }
            }
        }
        let fused = self.kind == ThrowKind::Smoke && (self.resting || flight_s >= data.smoke.fuse_s);
        if fused || flight_s >= p.max_flight_s {
            return Flight::Burst { at: self.ground_point(data, level, Vec3::ZERO) };
        }
        out
    }

    /// The ground point an area grows from, where the grenade is now (`hit`: the normal it just met). On a floor:
    /// the floor under it. Else the ground below, up to the molotov's `ground_drop_m` (a smoke: its `lift_m`, so a
    /// smoke popping higher keeps its centre where it popped); with none there, the point itself.
    fn ground_point(&self, data: &ThrowablesFile, level: &Level, hit: Vec3) -> Vec3 {
        let r = data.projectile.radius_m;
        let below = self.pos - Vec3::Y * r;
        if hit.y > 0.7 || self.resting {
            return below;
        }
        let drop = match self.kind {
            ThrowKind::Molotov => data.molotov.ground_drop_m,
            ThrowKind::Smoke => data.smoke.lift_m,
        };
        let start = self.pos + hit * 0.02;
        let tr = level.world.trace_solid(start, start - Vec3::Y * drop, Vec3::splat(r));
        if tr.hit() && tr.normal.y > 0.5 {
            tr.end - Vec3::Y * r
        } else if self.kind == ThrowKind::Smoke {
            self.pos - Vec3::Y * data.smoke.lift_m
        } else {
            below
        }
    }
}

// ---------------------------------------------------------------------------------------------- the areas

fn ease_out(x: f32) -> f32 {
    let x = x.clamp(0.0, 1.0);
    1.0 - (1.0 - x) * (1.0 - x)
}

/// A smoke cloud: it grows over the place it popped, holds, and thins out.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Smoke {
    pub id: ThrowId,
    /// The ground point it popped over.
    pub at: Vec3,
    /// Ticks since it popped.
    pub age: u32,
}

impl Smoke {
    pub fn new(id: ThrowId, at: Vec3) -> Self {
        Self { id, at, age: 0 }
    }

    pub fn centre(&self, s: &SmokeSpec) -> Vec3 {
        self.at + Vec3::Y * s.lift_m
    }

    /// Its size now (0..1 of `radius_m` and `height_m`): it grows, easing out, over `grow_s`.
    pub fn growth(&self, s: &SmokeSpec, dt: f32) -> f32 {
        ease_out(self.age as f32 * dt / s.grow_s)
    }

    /// The radius across (m).
    pub fn radius(&self, s: &SmokeSpec, dt: f32) -> f32 {
        s.radius_m * self.growth(s, dt)
    }

    /// How thick it is (0..1): full while it grows and holds, then thinning out to nothing over `fade_s`.
    pub fn density(&self, s: &SmokeSpec, dt: f32) -> f32 {
        let t = self.age as f32 * dt - s.grow_s - s.hold_s;
        if t <= 0.0 { 1.0 } else { (1.0 - t / s.fade_s.max(1e-3)).max(0.0) }
    }

    pub fn done(&self, s: &SmokeSpec, dt: f32) -> bool {
        self.age as f32 * dt >= s.grow_s + s.hold_s + s.fade_s
    }

    /// The (s0, s1) stretch of the segment `a..b` (as shares of it) inside the cloud at full size `scale` (1 = its
    /// size now), if any.
    pub fn clip(&self, s: &SmokeSpec, dt: f32, a: Vec3, b: Vec3, scale: f32) -> Option<(f32, f32)> {
        let g = self.growth(s, dt) * scale;
        let radii = Vec3::new(s.radius_m, s.height_m, s.radius_m) * g;
        if radii.min_element() <= 1e-4 {
            return None;
        }
        segment_in_ellipsoid(a, b, self.centre(s), radii)
    }

    /// Whether it hides `b` from `a`: dense enough, with the line running at least `sight_chord_m` through it.
    pub fn hides(&self, s: &SmokeSpec, dt: f32, a: Vec3, b: Vec3) -> bool {
        if self.density(s, dt) < s.sight_min_density.max(1e-3) {
            return false;
        }
        self.clip(s, dt, a, b, 1.0).is_some_and(|(s0, s1)| (s1 - s0) * a.distance(b) >= s.sight_chord_m)
    }
}

/// The stretch (s0, s1), as shares of `a..b`, inside the axis-aligned ellipsoid at `c` with `radii`.
pub fn segment_in_ellipsoid(a: Vec3, b: Vec3, c: Vec3, radii: Vec3) -> Option<(f32, f32)> {
    let p = (a - c) / radii;
    let d = (b - a) / radii;
    let qa = d.dot(d);
    let qb = 2.0 * p.dot(d);
    let qc = p.dot(p) - 1.0;
    if qa <= 1e-12 {
        return (qc <= 0.0).then_some((0.0, 1.0));
    }
    let disc = qb * qb - 4.0 * qa * qc;
    if disc <= 0.0 {
        return None;
    }
    let root = disc.sqrt();
    let s0 = ((-qb - root) / (2.0 * qa)).max(0.0);
    let s1 = ((-qb + root) / (2.0 * qa)).min(1.0);
    (s1 > s0).then_some((s0, s1))
}

/// A burning area: fire spreading over the ground where a molotov burst.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Fire {
    pub id: ThrowId,
    /// The ground point it burst on.
    pub at: Vec3,
    pub age: u32,
}

impl Fire {
    pub fn new(id: ThrowId, at: Vec3) -> Self {
        Self { id, at, age: 0 }
    }

    /// Its radius now: it spreads, easing out, over `spread_s`.
    pub fn radius(&self, m: &MolotovSpec, dt: f32) -> f32 {
        if m.spread_s <= 0.0 {
            return m.radius_m;
        }
        m.radius_m * ease_out(self.age as f32 * dt / m.spread_s)
    }

    pub fn done(&self, m: &MolotovSpec, dt: f32) -> bool {
        self.age as f32 * dt >= m.burn_s
    }

    /// Whether feet at `feet` stand in it.
    pub fn burns(&self, m: &MolotovSpec, dt: f32, feet: Vec3) -> bool {
        let d = Vec3::new(feet.x - self.at.x, 0.0, feet.z - self.at.z).length();
        d <= self.radius(m, dt) && feet.y >= self.at.y - 0.5 && feet.y <= self.at.y + m.height_m
    }
}

/// Whether `smoke` puts out `fire`: the cloud reaches `douse_overlap_m` past the fire's edge, at its height.
pub fn douses(data: &ThrowablesFile, dt: f32, smoke: &Smoke, fire: &Fire) -> bool {
    let s = &data.smoke;
    if smoke.density(s, dt) <= 0.0 {
        return false;
    }
    let c = smoke.centre(s);
    let height = s.height_m * smoke.growth(s, dt);
    if fire.at.y < c.y - height - 0.5 || fire.at.y > c.y + height {
        return false;
    }
    let d = Vec3::new(c.x - fire.at.x, 0.0, c.z - fire.at.z).length();
    d <= smoke.radius(s, dt) + fire.radius(&data.molotov, dt) - s.douse_overlap_m
}

// ---------------------------------------------------------------------------------------------- the world

/// What happened to the throwables this tick.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum WorldEvent {
    Bounced {
        id: ThrowId,
        kind: ThrowKind,
        at: Vec3,
        speed: f32,
    },
    /// A grenade went off: its smoke cloud or fire is now in the world.
    Burst {
        id: ThrowId,
        kind: ThrowKind,
        at: Vec3,
    },
    /// Smoke put this fire out.
    Doused {
        id: ThrowId,
        at: Vec3,
    },
    Lost {
        id: ThrowId,
    },
}

/// Every grenade, smoke cloud and fire in a match.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct ThrowWorld {
    pub projectiles: Vec<Projectile>,
    pub smokes: Vec<Smoke>,
    pub fires: Vec<Fire>,
}

impl ThrowWorld {
    pub fn throw(&mut self, owner: u64, l: &Launch) -> ThrowId {
        let id = ThrowId { owner, seq: l.seq };
        self.projectiles.push(Projectile::new(id, l));
        id
    }

    pub fn clear(&mut self) {
        *self = Self::default();
    }

    /// Advance one tick: areas age (and end), grenades fly and go off, smoke puts out fire.
    pub fn step(&mut self, data: &ThrowablesFile, level: &Level, dt: f32) -> Vec<WorldEvent> {
        let mut out = Vec::new();
        for s in &mut self.smokes {
            s.age += 1;
        }
        for f in &mut self.fires {
            f.age += 1;
        }
        self.smokes.retain(|s| !s.done(&data.smoke, dt));
        self.fires.retain(|f| !f.done(&data.molotov, dt));
        let mut i = 0;
        while i < self.projectiles.len() {
            let p = &mut self.projectiles[i];
            let (id, kind) = (p.id, p.kind);
            match p.step(data, level, dt) {
                Flight::Flying => i += 1,
                Flight::Bounced { at, speed } => {
                    out.push(WorldEvent::Bounced { id, kind, at, speed });
                    i += 1;
                }
                Flight::Burst { at } => {
                    self.projectiles.remove(i);
                    match kind {
                        ThrowKind::Smoke => self.smokes.push(Smoke::new(id, at)),
                        ThrowKind::Molotov => self.fires.push(Fire::new(id, at)),
                    }
                    out.push(WorldEvent::Burst { id, kind, at });
                }
                Flight::Lost => {
                    self.projectiles.remove(i);
                    out.push(WorldEvent::Lost { id });
                }
            }
        }
        let smokes = &self.smokes;
        self.fires.retain(|f| {
            let out_now = smokes.iter().any(|s| douses(data, dt, s, f));
            if out_now {
                out.push(WorldEvent::Doused { id: f.id, at: f.at });
            }
            !out_now
        });
        out
    }

    /// Whether smoke hides `b` from `a` (bullet tunnels are not counted: they are each client's own).
    pub fn sight_blocked(&self, data: &ThrowablesFile, dt: f32, a: Vec3, b: Vec3) -> bool {
        sight_blocked(&self.smokes, data, dt, a, b)
    }

    /// The fire burning feet at `feet`, if any (the first one: standing in two burns no faster).
    pub fn fire_under(&self, data: &ThrowablesFile, dt: f32, feet: Vec3) -> Option<&Fire> {
        self.fires.iter().find(|f| f.burns(&data.molotov, dt, feet))
    }
}

/// Whether any of `smokes` hides `b` from `a`.
pub fn sight_blocked(smokes: &[Smoke], data: &ThrowablesFile, dt: f32, a: Vec3, b: Vec3) -> bool {
    smokes.iter().any(|s| s.hides(&data.smoke, dt, a, b))
}

// ---------------------------------------------------------------------------------------------- burning

/// What one burn pulse did.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Burn {
    /// Damage the halo arc soaked.
    pub absorbed: f32,
    /// Damage that went on to health.
    pub to_hp: f32,
    pub shield_broke: bool,
    pub died: bool,
}

/// One burn pulse (`dps x pulse_s`) on the data's zone: its halo arc soaks `shield_soak` of it while it holds,
/// the rest goes to health (a broken limb spills into the torso as usual). Any of it delays the halo's regen.
pub fn burn(
    d: &FireDamage,
    spill: &SpillToTorso,
    halo_spec: &HaloSpec,
    halo: &mut HaloState,
    health: &mut Health,
) -> Burn {
    let dmg = d.dps * d.pulse_s;
    if dmg <= 0.0 || health.dead {
        return Burn::default();
    }
    let z = d.zone;
    let mut out = Burn::default();
    if halo_spec.tiers[z] > 0 && halo.shield[z] > 0.0 {
        out.absorbed = (dmg * d.shield_soak).min(halo.shield[z]);
        halo.shield[z] -= out.absorbed;
        if halo.shield[z] <= 1e-6 {
            halo.shield[z] = 0.0;
            out.shield_broke = true;
        }
    }
    out.to_hp = dmg - out.absorbed;
    halo.on_damaged(halo_spec, out.shield_broke);
    out.died = health.apply(z, out.to_hp, spill).died;
    out
}

/// A player's burn clock (seconds to the next pulse): whether a pulse is due this tick. Stepping into fire burns at
/// once, then every `pulse_s`; out of it the clock resets, so the next step in burns at once again.
pub fn pulse_due(clock: &mut f32, in_fire: bool, pulse_s: f32, dt: f32) -> bool {
    if !in_fire {
        *clock = 0.0;
        return false;
    }
    let due = *clock <= 1e-5;
    if due {
        *clock += pulse_s;
    }
    *clock -= dt;
    due
}

// ---------------------------------------------------------------------------------------------- bullet tunnels

/// Bullet lines kept per smoke cloud.
pub const TUNNELS: usize = 8;

/// A bullet's path through a cloud, and when it was fired (the client's clock, s).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Tunnel {
    pub a: Vec3,
    pub b: Vec3,
    pub at_s: f32,
}

/// The recent bullet lines through one cloud: a small ring, the oldest overwritten first.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Tunnels {
    pub slots: [Option<Tunnel>; TUNNELS],
    next: usize,
}

impl Tunnels {
    pub fn push(&mut self, a: Vec3, b: Vec3, now_s: f32) {
        self.slots[self.next] = Some(Tunnel { a, b, at_s: now_s });
        self.next = (self.next + 1) % TUNNELS;
    }

    /// Drop the lines that have refilled (older than `life_s`).
    pub fn prune(&mut self, now_s: f32, life_s: f32) {
        for s in &mut self.slots {
            if s.is_some_and(|t| now_s - t.at_s >= life_s) {
                *s = None;
            }
        }
    }

    /// Every live line and how open it is (1 = clear, 0 = refilled).
    pub fn live(&self, now_s: f32, life_s: f32, refill_s: f32) -> impl Iterator<Item = (Tunnel, f32)> + '_ {
        self.slots.iter().flatten().filter_map(move |t| {
            let open = tunnel_open(now_s - t.at_s, life_s, refill_s);
            (open > 0.0).then_some((*t, open))
        })
    }
}

/// How open a tunnel is `age_s` after the bullet: clear at once, clear until `life_s - refill_s`, then filling
/// back in to nothing at `life_s`.
pub fn tunnel_open(age_s: f32, life_s: f32, refill_s: f32) -> f32 {
    if age_s < 0.0 || age_s >= life_s {
        return 0.0;
    }
    let start = (life_s - refill_s).max(0.0);
    if age_s <= start { 1.0 } else { 1.0 - (age_s - start) / (life_s - start).max(1e-4) }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::GameData;
    use crate::movement::collision::{Brush, BrushKind};

    const DT: f32 = 1.0 / 60.0;

    fn data() -> ThrowablesFile {
        GameData::embedded().throwables
    }

    /// A floor at y = 0 and a wall facing -x at x = 10.
    fn yard() -> Level {
        let mut level = Level { kill_y: -20.0, ..Default::default() };
        level.world.push(Brush::cuboid(
            Vec3::new(-100.0, -1.0, -100.0),
            Vec3::new(100.0, 0.0, 100.0),
            BrushKind::Solid,
        ));
        level.world.push(Brush::cuboid(Vec3::new(10.0, 0.0, -20.0), Vec3::new(11.0, 6.0, 20.0), BrushKind::Solid));
        level
    }

    fn id(seq: u16) -> ThrowId {
        ThrowId { owner: 7, seq }
    }

    fn fly(d: &ThrowablesFile, level: &Level, l: Launch, ticks: u32) -> (Projectile, Vec<Flight>) {
        let mut p = Projectile::new(id(l.seq), &l);
        let mut seen = Vec::new();
        for _ in 0..ticks {
            let f = p.step(d, level, DT);
            seen.push(f);
            if matches!(f, Flight::Burst { .. } | Flight::Lost) {
                break;
            }
        }
        (p, seen)
    }

    #[test]
    fn the_data_file_parses_and_validates() {
        let d = data();
        d.validate().unwrap();
        assert!((4.0..=5.0).contains(&d.smoke.radius_m), "about 4.5 m");
        assert!((1.0..=2.0).contains(&d.smoke.grow_s), "about 1.5 s");
        assert!((12.0..=18.0).contains(&d.smoke.hold_s), "about 15 s");
        assert!((2.5..=3.5).contains(&d.molotov.radius_m), "about 3 m");
        assert!((6.0..=8.0).contains(&d.molotov.burn_s), "about 7 s");
        let mut bad = d.clone();
        bad.projectile.restitution = 1.5;
        assert!(bad.validate().is_err());
        bad = d.clone();
        bad.smoke.grow_s = 0.0;
        assert!(bad.validate().is_err());
        bad = d;
        bad.molotov.damage.dps = f32::NAN;
        assert!(bad.validate().is_err());
    }

    /// In the open, a grenade follows the gravity arc; the same throw flies the same path every time.
    #[test]
    fn the_arc_is_ballistic_and_deterministic() {
        let d = data();
        let level = yard();
        let l =
            Launch { kind: ThrowKind::Smoke, seq: 1, origin: Vec3::new(0.0, 1.6, 0.0), vel: Vec3::new(3.0, 8.0, -2.0) };
        let mut p = Projectile::new(id(1), &l);
        for k in 1..=30u32 {
            p.step(&d, &level, DT);
            let t = k as f32 * DT;
            // Semi-implicit Euler: the exact sum of the per-tick moves.
            let fall = d.projectile.gravity * DT * DT * (k * (k + 1)) as f32 / 2.0;
            let want = l.origin + l.vel * t - Vec3::Y * fall;
            assert!((p.pos - want).length() < 1e-3, "tick {k}: {} vs {want}", p.pos);
        }
        let a = fly(&d, &level, l, 600);
        let b = fly(&d, &level, l, 600);
        assert_eq!(a, b, "deterministic");
    }

    /// A smoke bounces off the wall and the floor, loses speed each bounce, comes to rest on the floor and pops
    /// there; the same throw does exactly the same.
    #[test]
    fn a_smoke_bounces_rests_and_pops_where_it_lies() {
        let mut d = data();
        d.smoke.fuse_s = 30.0; // only resting pops it
        d.projectile.max_flight_s = 60.0;
        let level = yard();
        let l =
            Launch { kind: ThrowKind::Smoke, seq: 2, origin: Vec3::new(0.0, 3.0, 0.0), vel: Vec3::new(14.0, 3.0, 0.0) };
        let (p, seen) = fly(&d, &level, l, 3000);
        let bounces: Vec<f32> = seen
            .iter()
            .filter_map(|f| if let Flight::Bounced { speed, .. } = f { Some(*speed) } else { None })
            .collect();
        assert!(bounces.len() >= 2, "off the wall and the floor: {bounces:?}");
        let Some(Flight::Burst { at }) = seen.last() else { panic!("never popped: {:?}", seen.last()) };
        assert!(p.resting);
        assert!(at.y.abs() < 0.01, "on the floor: {at}");
        assert!(at.x < 10.0 - d.projectile.radius_m + 0.01, "came back off the wall: {at}");
        let wall_hit = bounces[0];
        assert!(wall_hit > 10.0, "hit the wall fast: {wall_hit}");
        assert_eq!(fly(&d, &level, l, 3000), (p, seen), "deterministic");
    }

    /// The fuse: a smoke thrown high pops when its fuse runs out, still in the air; resting pops it earlier.
    #[test]
    fn the_smoke_fuse_pops_it_in_flight() {
        let d = data();
        let level = yard();
        let l =
            Launch { kind: ThrowKind::Smoke, seq: 3, origin: Vec3::new(0.0, 1.6, 0.0), vel: Vec3::new(0.0, 30.0, 0.0) };
        let (p, seen) = fly(&d, &level, l, 1000);
        assert!(matches!(seen.last(), Some(Flight::Burst { .. })));
        assert_eq!(p.age, secs_to_ticks(d.smoke.fuse_s, 60) as u32, "on the fuse");
        assert!(!p.resting);
        // High up: the cloud centres where it popped (no ground within reach under it).
        let Some(Flight::Burst { at }) = seen.last() else { unreachable!() };
        assert!((at.y + d.smoke.lift_m - p.pos.y).abs() < 1e-3, "{at} vs {}", p.pos);
    }

    /// A molotov bursts on its first impact: on the floor where it lands; on a wall, the fire takes the ground
    /// under the hit.
    #[test]
    fn a_molotov_bursts_on_impact() {
        let d = data();
        let level = yard();
        let lob = Launch {
            kind: ThrowKind::Molotov,
            seq: 4,
            origin: Vec3::new(0.0, 1.6, 0.0),
            vel: Vec3::new(4.0, 5.0, 0.0),
        };
        let (p, seen) = fly(&d, &level, lob, 600);
        assert!(!seen.iter().any(|f| matches!(f, Flight::Bounced { .. })), "no bounce first");
        let Some(Flight::Burst { at }) = seen.last() else { panic!() };
        assert!(at.y.abs() < 0.01 && (at.x - p.pos.x).abs() < 1e-4, "on the floor: {at}");
        let wall = Launch {
            kind: ThrowKind::Molotov,
            seq: 5,
            origin: Vec3::new(0.0, 2.0, 0.0),
            vel: Vec3::new(20.0, 2.0, 0.0),
        };
        let (p, seen) = fly(&d, &level, wall, 600);
        let Some(Flight::Burst { at }) = seen.last() else { panic!() };
        assert!(p.pos.y > 1.0 && p.pos.x > 9.8, "hit the wall up high: {}", p.pos);
        assert!(at.y.abs() < 0.01 && at.x < 10.0, "fire on the ground under it: {at}");
    }

    /// Out of the map: lost, no burst.
    #[test]
    fn a_grenade_off_the_map_is_lost() {
        let d = data();
        let level = Level { kill_y: -5.0, ..Default::default() };
        let l = Launch { kind: ThrowKind::Molotov, seq: 6, origin: Vec3::ZERO, vel: Vec3::new(1.0, 0.0, 0.0) };
        let (_, seen) = fly(&d, &level, l, 600);
        assert_eq!(seen.last(), Some(&Flight::Lost));
    }

    /// The cloud grows to about 4.5 m over about 1.5 s, holds, thins out, and is gone after grow + hold + fade.
    #[test]
    fn smoke_grows_holds_and_thins_out() {
        let d = data();
        let s = &d.smoke;
        let mut c = Smoke::new(id(1), Vec3::ZERO);
        assert_eq!(c.radius(s, DT), 0.0);
        let ticks = |secs: f32| (secs / DT).round() as u32;
        c.age = ticks(s.grow_s * 0.5);
        let half = c.radius(s, DT);
        assert!(half > s.radius_m * 0.5 && half < s.radius_m, "eases out: {half}");
        c.age = ticks(s.grow_s);
        assert!((c.radius(s, DT) - s.radius_m).abs() < 1e-3);
        assert_eq!(c.density(s, DT), 1.0);
        c.age = ticks(s.grow_s + s.hold_s);
        assert_eq!(c.density(s, DT), 1.0, "holds");
        assert!((c.radius(s, DT) - s.radius_m).abs() < 1e-3);
        c.age = ticks(s.grow_s + s.hold_s + s.fade_s * 0.5);
        assert!((c.density(s, DT) - 0.5).abs() < 0.02, "thinning");
        assert!(!c.done(s, DT));
        c.age = ticks(s.grow_s + s.hold_s + s.fade_s);
        assert!(c.done(s, DT));
        // The world drops it then.
        let mut w = ThrowWorld::default();
        w.smokes.push(Smoke::new(id(1), Vec3::ZERO));
        let level = yard();
        let mut steps = 0;
        while !w.smokes.is_empty() {
            w.step(&d, &level, DT);
            steps += 1;
        }
        assert_eq!(steps, ticks(s.grow_s + s.hold_s + s.fade_s));
    }

    /// Smoke hides what is behind it: a line through the cloud is blocked, one past it or grazing its rim is not,
    /// nor one through a thinned-out cloud.
    #[test]
    fn smoke_blocks_sight() {
        let d = data();
        let s = &d.smoke;
        let mut w = ThrowWorld::default();
        w.smokes.push(Smoke { id: id(1), at: Vec3::new(0.0, 0.0, -10.0), age: (s.grow_s / DT) as u32 + 1 });
        let eye = Vec3::new(0.0, 1.6, 0.0);
        assert!(w.sight_blocked(&d, DT, eye, Vec3::new(0.0, 1.6, -20.0)), "straight through");
        assert!(w.sight_blocked(&d, DT, eye, Vec3::new(0.0, 1.6, -10.0)), "into the middle");
        assert!(!w.sight_blocked(&d, DT, eye, Vec3::new(8.0, 1.6, -10.0)), "beside it");
        assert!(!w.sight_blocked(&d, DT, eye, Vec3::new(0.0, 1.6, -3.0)), "short of it");
        // The rim: a line clipping the edge for less than sight_chord_m.
        let r = s.radius_m;
        let rim = Vec3::new(r - 0.02, s.lift_m, -10.0);
        assert!(!w.sight_blocked(&d, DT, rim + Vec3::Z * 10.0, rim - Vec3::Z * 10.0), "the rim is not enough");
        // Just popped: too small to hide anything yet.
        w.smokes[0].age = 1;
        assert!(!w.sight_blocked(&d, DT, eye, Vec3::new(0.0, 1.6, -20.0)));
        // Thinned out.
        w.smokes[0].age = ((s.grow_s + s.hold_s + s.fade_s * 0.9) / DT) as u32;
        assert!(!w.sight_blocked(&d, DT, eye, Vec3::new(0.0, 1.6, -20.0)));
    }

    /// The ellipsoid clip: through the middle, a miss, and a segment that starts inside.
    #[test]
    fn segments_clip_to_the_cloud() {
        let c = Vec3::ZERO;
        let radii = Vec3::new(2.0, 1.0, 2.0);
        let (s0, s1) = segment_in_ellipsoid(Vec3::new(-4.0, 0.0, 0.0), Vec3::new(4.0, 0.0, 0.0), c, radii).unwrap();
        assert!((s0 - 0.25).abs() < 1e-5 && (s1 - 0.75).abs() < 1e-5);
        assert!(segment_in_ellipsoid(Vec3::new(-4.0, 1.5, 0.0), Vec3::new(4.0, 1.5, 0.0), c, radii).is_none());
        let (s0, s1) = segment_in_ellipsoid(Vec3::ZERO, Vec3::new(0.0, 4.0, 0.0), c, radii).unwrap();
        assert!(s0 == 0.0 && (s1 - 0.25).abs() < 1e-5);
    }

    /// Fire spreads to its radius, burns feet in it (not above it, not beside it) and dies out after burn_s.
    #[test]
    fn fire_spreads_and_burns_out() {
        let d = data();
        let m = &d.molotov;
        let mut f = Fire::new(id(2), Vec3::new(5.0, 0.0, 5.0));
        f.age = (m.spread_s / DT).ceil() as u32;
        assert!((f.radius(m, DT) - m.radius_m).abs() < 1e-3);
        assert!(f.burns(m, DT, Vec3::new(5.0 + m.radius_m - 0.1, 0.0, 5.0)));
        assert!(!f.burns(m, DT, Vec3::new(5.0 + m.radius_m + 0.1, 0.0, 5.0)), "beside it");
        assert!(!f.burns(m, DT, Vec3::new(5.0, 3.0, 5.0)), "on a roof above it");
        f.age = 1;
        assert!(!f.burns(m, DT, Vec3::new(5.0 + m.radius_m - 0.1, 0.0, 5.0)), "not spread that far yet");
        let mut w = ThrowWorld { fires: vec![Fire::new(id(2), Vec3::ZERO)], ..Default::default() };
        let level = yard();
        let mut steps = 0;
        while !w.fires.is_empty() {
            w.step(&d, &level, DT);
            steps += 1;
        }
        assert_eq!(steps, (m.burn_s / DT).round() as u32);
    }

    /// Burn damage over time: dps in pulses, half soaked by a holding arc, the rest to health; an uncovered zone
    /// takes it all; enough of it kills.
    #[test]
    fn fire_damage_over_time_goes_through_shield_and_health() {
        let g = GameData::embedded();
        let d = &g.throwables;
        let fd = d.molotov.damage;
        let armor = g.armor.resolve_id(&g.rules.default_loadout.armor).unwrap();
        let mut spec = HaloSpec::from_armor(&armor);
        // An arc on the burning zone (the deathmatch armor tiers all cover the legs).
        spec.tiers[fd.zone] = spec.tiers[fd.zone].max(1);
        spec.capacity[fd.zone] = spec.capacity[fd.zone].max(30.0);
        let mut halo = HaloState::full(&spec);
        let mut health = Health::new(g.armor.zone_hp);
        let pulse = fd.dps * fd.pulse_s;
        let shield0 = halo.shield[fd.zone];
        assert!(spec.tiers[fd.zone] > 0 && shield0 > 0.0, "the default halo covers {:?}", fd.zone);
        let b = burn(&fd, &g.weapons.spill_to_torso, &spec, &mut halo, &mut health);
        assert!((b.absorbed - pulse * fd.shield_soak).abs() < 1e-4);
        assert!((b.to_hp - pulse * (1.0 - fd.shield_soak)).abs() < 1e-4);
        assert!((health.hp[fd.zone] - (health.max[fd.zone] - b.to_hp)).abs() < 1e-4);
        assert!(halo.regen_wait_s > 0.0, "burning delays the regen");
        // No halo: all of it to health.
        let mut bare = HaloState::full(&HaloSpec::NONE);
        let mut h2 = Health::new(g.armor.zone_hp);
        let b = burn(&fd, &g.weapons.spill_to_torso, &HaloSpec::NONE, &mut bare, &mut h2);
        assert_eq!((b.absorbed, b.to_hp), (0.0, pulse));
        // Standing in it long enough kills (the legs break and spill into the torso).
        let mut clock = 0.0;
        let mut pulses = 0;
        let mut died_at = None;
        for t in 0..60 * 60 {
            if pulse_due(&mut clock, true, fd.pulse_s, DT) {
                pulses += 1;
                if burn(&fd, &g.weapons.spill_to_torso, &spec, &mut halo, &mut health).died {
                    died_at = Some(t as f32 * DT);
                    break;
                }
            }
        }
        let died_at = died_at.expect("burning kills");
        assert!(died_at > 2.0, "not at once: {died_at} s");
        assert!(pulses as f32 * fd.pulse_s >= died_at - fd.pulse_s, "a pulse every {} s", fd.pulse_s);
        assert!(halo.shield[fd.zone] == 0.0, "the arc went first");
    }

    /// The burn clock: the first pulse on stepping in, then one every pulse_s; stepping out resets it.
    #[test]
    fn burn_pulses_come_every_pulse_s() {
        let pulse_s = 0.25;
        let mut clock = 0.0;
        assert!(!pulse_due(&mut clock, false, pulse_s, DT));
        assert!(pulse_due(&mut clock, true, pulse_s, DT), "at once");
        let mut n = 1;
        for _ in 1..60 {
            n += pulse_due(&mut clock, true, pulse_s, DT) as u32;
        }
        assert_eq!(n, 4, "four pulses in a second");
        pulse_due(&mut clock, false, pulse_s, DT);
        assert!(pulse_due(&mut clock, true, pulse_s, DT), "stepping back in burns at once");
    }

    /// Smoke puts out fire: a smoke popping on a fire, and a fire spreading under a cloud. A cloud nearby that
    /// does not reach the flames leaves them burning.
    #[test]
    fn smoke_puts_out_fire() {
        let d = data();
        let level = yard();
        // A smoke landing in a fire.
        let mut w = ThrowWorld { fires: vec![Fire::new(id(1), Vec3::new(0.0, 0.0, 0.0))], ..Default::default() };
        let l =
            Launch { kind: ThrowKind::Smoke, seq: 2, origin: Vec3::new(0.0, 0.3, 0.0), vel: Vec3::new(0.0, -1.0, 0.0) };
        w.throw(7, &l);
        let mut doused = None;
        for t in 0..300 {
            for e in w.step(&d, &level, DT) {
                if let WorldEvent::Doused { id, .. } = e {
                    doused = Some((t, id));
                }
            }
            if doused.is_some() {
                break;
            }
        }
        assert_eq!(doused.map(|d| d.1), Some(id(1)), "the fire went out");
        assert!(w.fires.is_empty() && w.smokes.len() == 1);
        // A fire bursting under a cloud goes out at once.
        let mut w = ThrowWorld {
            smokes: vec![Smoke { id: id(3), at: Vec3::new(0.0, 0.0, -2.0), age: 200 }],
            ..Default::default()
        };
        let m = Launch {
            kind: ThrowKind::Molotov,
            seq: 4,
            origin: Vec3::new(0.0, 0.5, 0.0),
            vel: Vec3::new(0.0, -2.0, 0.0),
        };
        w.throw(7, &m);
        let mut events = Vec::new();
        for _ in 0..60 {
            events.extend(w.step(&d, &level, DT));
        }
        assert!(events.iter().any(|e| matches!(e, WorldEvent::Burst { kind: ThrowKind::Molotov, .. })));
        assert!(events.iter().any(|e| matches!(e, WorldEvent::Doused { .. })));
        assert!(w.fires.is_empty());
        // A cloud 12 m away leaves the fire alone.
        let mut w = ThrowWorld {
            smokes: vec![Smoke { id: id(5), at: Vec3::new(12.0, 0.0, 0.0), age: 200 }],
            fires: vec![Fire { id: id(6), at: Vec3::ZERO, age: 60 }],
            ..Default::default()
        };
        assert!(!w.step(&d, &level, DT).iter().any(|e| matches!(e, WorldEvent::Doused { .. })));
        assert_eq!(w.fires.len(), 1);
        // A thinned-out cloud does not douse either.
        let gone =
            Smoke { id: id(5), at: Vec3::ZERO, age: ((d.smoke.grow_s + d.smoke.hold_s + d.smoke.fade_s) / DT) as u32 };
        assert!(!douses(&d, DT, &gone, &Fire { id: id(6), at: Vec3::ZERO, age: 60 }));
    }

    /// The hand: a press winds up (one taken from the kit), the grenade leaves after windup_s with the next
    /// number, the hands stay busy through the recovery, a held key does not throw again, and an empty kit or busy
    /// hands throw nothing.
    #[test]
    fn the_hand_winds_up_releases_and_counts() {
        let d = data();
        let t = &d.throw;
        let mut h = ThrowHand::new(ThrowKit { smoke: 1, molotov: 2 });
        let smoke = Buttons(Buttons::THROW_SMOKE);
        let none = Buttons(0);
        assert_eq!(h.step(t, smoke, false, 60), HandEvents::default(), "hands not free");
        h.keys = 0;
        let ev = h.step(t, smoke, true, 60);
        assert_eq!(ev.started, Some(ThrowKind::Smoke));
        assert_eq!(h.left, ThrowKit { smoke: 0, molotov: 2 });
        assert!(h.busy());
        let windup = secs_to_ticks(t.windup_s, 60);
        let mut released = None;
        for k in 1..=windup {
            let ev = h.step(t, smoke, true, 60);
            if let Some(r) = ev.released {
                released = Some((k, r));
            }
        }
        assert_eq!(released, Some((windup, (ThrowKind::Smoke, 1))), "after the wind-up, number 1");
        assert!(h.busy(), "recovering");
        for _ in 0..secs_to_ticks(t.recover_s, 60) {
            h.step(t, smoke, true, 60);
        }
        assert!(!h.busy());
        // Held: no second throw (and none left anyway); a fresh press of the other key throws a molotov.
        assert_eq!(h.step(t, smoke, true, 60).started, None);
        h.step(t, none, true, 60);
        assert_eq!(h.step(t, smoke, true, 60).started, None, "no smoke left");
        let ev = h.step(t, Buttons(Buttons::THROW_SMOKE | Buttons::THROW_MOLOTOV), true, 60);
        assert_eq!(ev.started, Some(ThrowKind::Molotov));
        assert_eq!(h.left.molotov, 1);
    }

    /// A throw leaves from the right hand ahead of the eye, along the aim lifted a little, faster when running
    /// forward; with the hand in a wall it leaves from the eye.
    #[test]
    fn a_throw_leaves_the_right_hand_along_the_aim() {
        let d = data();
        let t = &d.throw;
        let w = CollisionWorld::default();
        let eye = Vec3::new(0.0, 1.6, 0.0);
        let (origin, vel) = launch(t, &w, eye, Vec3::ZERO, 0.0, 0.0);
        // Yaw 0 looks down -Z: right is +X.
        assert!(origin.x > 0.0 && origin.z < 0.0 && origin.y < eye.y, "{origin}");
        assert!((vel.length() - t.speed_mps).abs() < 1e-3);
        assert!(vel.z < 0.0 && vel.y > 0.0, "forward and a little up: {vel}");
        let (_, running) = launch(t, &w, eye, Vec3::new(0.0, 0.0, -6.0), 0.0, 0.0);
        assert!(running.length() > vel.length());
        let mut walled = CollisionWorld::default();
        walled.push(Brush::cuboid(Vec3::new(-2.0, 0.0, -0.6), Vec3::new(2.0, 3.0, -0.2), BrushKind::Solid));
        let (origin, _) = launch(t, &walled, eye, Vec3::ZERO, 0.0, 0.0);
        assert_eq!(origin, eye, "the hand is in the wall");
    }

    /// Bullet tunnels: clear at once, refill at the end of their life and age out of the ring; the ring keeps the
    /// newest TUNNELS lines.
    #[test]
    fn tunnels_age_out() {
        let (life, refill) = (2.0, 0.8);
        assert_eq!(tunnel_open(0.0, life, refill), 1.0);
        assert_eq!(tunnel_open(1.0, life, refill), 1.0);
        assert!((tunnel_open(1.6, life, refill) - 0.5).abs() < 1e-5, "refilling");
        assert_eq!(tunnel_open(2.0, life, refill), 0.0);
        let mut r = Tunnels::default();
        r.push(Vec3::ZERO, Vec3::X, 0.0);
        r.push(Vec3::ZERO, Vec3::Y, 1.5);
        assert_eq!(r.live(1.6, life, refill).count(), 2);
        assert_eq!(r.live(2.5, life, refill).count(), 1, "the first refilled");
        r.prune(2.5, life);
        assert_eq!(r.slots.iter().flatten().count(), 1);
        r.prune(4.0, life);
        assert_eq!(r.slots.iter().flatten().count(), 0, "all aged out");
        for k in 0..(TUNNELS + 3) {
            r.push(Vec3::ZERO, Vec3::X * k as f32, 5.0 + k as f32 * 0.01);
        }
        let kept: Vec<f32> = r.slots.iter().flatten().map(|t| t.b.x).collect();
        assert_eq!(kept.len(), TUNNELS);
        assert!(!kept.contains(&0.0) && kept.contains(&((TUNNELS + 2) as f32)), "the oldest overwritten: {kept:?}");
    }
}
