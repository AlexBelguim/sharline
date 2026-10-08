//! Per-zone hitboxes posed on a player, and the host's lag-compensated check of a client's shot claim
//! (design/systems/diagrams/damage_flow.png, steps 2-3).

use crate::data::{GameData, MovementSpec};
use crate::movement::Stance;
use crate::movement::collision::CollisionWorld;
use crate::zone::Zone;
use glam::{Quat, Vec3};
use serde::{Deserialize, Serialize};
use std::collections::VecDeque;

/// Where a player's body is at one tick: enough to place the hitboxes.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Pose {
    /// Feet position.
    pub pos: Vec3,
    /// Body yaw (radians, same convention as the view yaw).
    pub yaw: f32,
    pub stance: Stance,
}

impl Pose {
    fn height_scale(&self, m: &MovementSpec) -> f32 {
        let h = match self.stance {
            Stance::Stand => m.capsule.height_stand,
            Stance::Crouch => m.capsule.height_crouch,
            Stance::Slide => m.capsule.height_slide,
        };
        h / m.capsule.height_stand
    }

    fn lerp(&self, other: &Pose, t: f32) -> Pose {
        let d = (other.yaw - self.yaw + std::f32::consts::PI).rem_euclid(std::f32::consts::TAU) - std::f32::consts::PI;
        Pose {
            pos: self.pos.lerp(other.pos, t),
            yaw: self.yaw + d * t,
            stance: if t < 0.5 { self.stance } else { other.stance },
        }
    }
}

/// An oriented hitbox in world space (rotated about +Y only).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ZoneBox {
    pub zone: Zone,
    pub center: Vec3,
    pub half: Vec3,
    pub yaw: f32,
}

impl ZoneBox {
    fn local(&self, p: Vec3) -> Vec3 {
        Quat::from_rotation_y(-self.yaw) * (p - self.center)
    }

    pub fn contains(&self, p: Vec3, inflate: f32) -> bool {
        let l = self.local(p).abs();
        let h = self.half + Vec3::splat(inflate);
        l.x <= h.x && l.y <= h.y && l.z <= h.z
    }

    /// Ray entry distance, if the ray hits the box.
    pub fn ray(&self, origin: Vec3, dir: Vec3) -> Option<f32> {
        let rot = Quat::from_rotation_y(-self.yaw);
        let o = rot * (origin - self.center);
        let d = rot * dir;
        let (mut tmin, mut tmax) = (0.0_f32, f32::MAX);
        for i in 0..3 {
            let (oi, di, hi) = (o[i], d[i], self.half[i]);
            if di.abs() < 1e-9 {
                if oi.abs() > hi {
                    return None;
                }
            } else {
                let (a, b) = ((-hi - oi) / di, (hi - oi) / di);
                tmin = tmin.max(a.min(b));
                tmax = tmax.min(a.max(b));
                if tmin > tmax {
                    return None;
                }
            }
        }
        Some(tmin)
    }
}

/// The zone hitboxes for a pose.
pub fn zone_boxes<'a>(data: &'a GameData, pose: &Pose) -> impl Iterator<Item = ZoneBox> + 'a {
    let s = pose.height_scale(&data.movement);
    let rot = Quat::from_rotation_y(pose.yaw);
    let pose = *pose;
    data.hitboxes.boxes.iter().map(move |b| {
        let c = Vec3::new(b.center.0, b.center.1 * s, b.center.2);
        ZoneBox {
            zone: b.zone,
            center: pose.pos + rot * c,
            half: Vec3::new(b.half.0, b.half.1 * s, b.half.2),
            yaw: pose.yaw,
        }
    })
}

/// First zone a ray hits on this pose: (zone, distance).
pub fn raycast(data: &GameData, pose: &Pose, origin: Vec3, dir: Vec3, max_dist: f32) -> Option<(Zone, f32)> {
    zone_boxes(data, pose)
        .filter_map(|b| b.ray(origin, dir).map(|t| (b.zone, t)))
        .filter(|(_, t)| *t <= max_dist)
        .min_by(|a, b| a.1.total_cmp(&b.1))
}

/// The centre of a pose's hitbox for `zone` (the head: where a bot aims).
pub fn zone_center(data: &GameData, pose: &Pose, zone: Zone) -> Option<Vec3> {
    zone_boxes(data, pose).find(|b| b.zone == zone).map(|b| b.center)
}

// ---------------------------------------------------------------------------------------------- history

/// Recent poses of one player, one per tick, for rewinding.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct PoseHistory {
    entries: VecDeque<(u32, Pose)>,
}

impl PoseHistory {
    pub fn push(&mut self, tick: u32, pose: Pose, keep_ticks: u32) {
        // Re-recording a tick (should not happen on the host) replaces the newer entries.
        while self.entries.back().is_some_and(|(t, _)| *t >= tick) {
            self.entries.pop_back();
        }
        self.entries.push_back((tick, pose));
        while self.entries.front().is_some_and(|(t, _)| tick.saturating_sub(*t) > keep_ticks) {
            self.entries.pop_front();
        }
    }

    pub fn clear(&mut self) {
        self.entries.clear();
    }

    pub fn latest(&self) -> Option<(u32, Pose)> {
        self.entries.back().copied()
    }

    /// Pose at a fractional tick, interpolated between recorded ticks and clamped to the recorded span.
    pub fn sample(&self, tick: f32) -> Option<Pose> {
        let (first_t, first) = *self.entries.front()?;
        if tick <= first_t as f32 {
            return Some(first);
        }
        for w in self.entries.iter().zip(self.entries.iter().skip(1)) {
            let ((ta, a), (tb, b)) = (*w.0, *w.1);
            if tick <= tb as f32 {
                let t = (tick - ta as f32) / (tb - ta).max(1) as f32;
                return Some(a.lerp(&b, t));
            }
        }
        self.latest().map(|(_, p)| p)
    }

    /// Average horizontal+vertical speed around a tick (m/s), for the hitbox inflation.
    pub fn speed_at(&self, tick: f32, tick_hz: u32) -> f32 {
        match (self.sample(tick - 1.0), self.sample(tick + 1.0)) {
            (Some(a), Some(b)) => a.pos.distance(b.pos) * tick_hz as f32 / 2.0,
            _ => 0.0,
        }
    }
}

// ---------------------------------------------------------------------------------------------- claims

/// A shot as the host simulated it from the shooter's inputs.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct FiredShot {
    pub seq: u32,
    pub tick: u32,
    /// Shooter eye position at the shot.
    pub origin: Vec3,
    /// Aim direction from the shooter's input at that tick.
    pub aim: Vec3,
    pub spread_deg: f32,
    /// The magazine slot it came from: its ammo decides the damage.
    pub ammo_slot: u8,
}

/// What a client says one of its shots hit.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct HitClaim {
    pub origin: Vec3,
    pub dir: Vec3,
    /// The (fractional) server tick the shooter was seeing other players at.
    pub view_tick: f32,
    pub zone: Zone,
    pub point: Vec3,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Verdict {
    Hit { zone: Zone, range_m: f32 },
    Rejected(Reject),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Reject {
    /// The claimed muzzle is far from where the host had the shooter.
    Origin,
    /// The claimed direction is outside the spread cone around the host's copy of the aim.
    Aim,
    /// The claimed point is not on the claimed ray.
    Ray,
    /// No pose history for the victim at that time.
    NoHistory,
    /// The point is not inside the (inflated) zone hitbox at the rewound time.
    Hitbox,
    /// Static geometry blocks the line from the muzzle to the point.
    Blocked,
    /// Beyond the weapon's range.
    Range,
}

/// Check a claim the way the design describes: rewind the victim (at most `max_rewind_s`), test the
/// claimed point against the inflated zone box, and check line of sight through the static world.
#[allow(clippy::too_many_arguments)]
pub fn validate_claim(
    data: &GameData,
    world: &CollisionWorld,
    shot: &FiredShot,
    claim: &HitClaim,
    victim: &PoseHistory,
    server_tick: u32,
    max_range_m: f32,
) -> Verdict {
    let v = &data.combat.shot_validation;
    let hz = data.net.tick_hz;
    if claim.origin.distance(shot.origin) > 0.75 {
        return Verdict::Rejected(Reject::Origin);
    }
    let dir = claim.dir.normalize_or_zero();
    let max_angle = (shot.spread_deg + v.aim_tolerance_deg).to_radians();
    if dir == Vec3::ZERO || dir.angle_between(shot.aim) > max_angle {
        return Verdict::Rejected(Reject::Aim);
    }
    let along = (claim.point - claim.origin).dot(dir);
    let off_ray = (claim.point - (claim.origin + dir * along)).length();
    if along <= 0.0 || off_ray > 0.1 {
        return Verdict::Rejected(Reject::Ray);
    }
    if along > max_range_m {
        return Verdict::Rejected(Reject::Range);
    }
    let max_rewind = v.max_rewind_s * hz as f32;
    let view = claim.view_tick.clamp(server_tick as f32 - max_rewind, server_tick as f32);
    let Some(pose) = victim.sample(view) else {
        return Verdict::Rejected(Reject::NoHistory);
    };
    let inflate = v.hitbox_inflate_m + v.hitbox_inflate_per_speed_s * victim.speed_at(view, hz);
    if !zone_boxes(data, &pose).any(|b| b.zone == claim.zone && b.contains(claim.point, inflate)) {
        return Verdict::Rejected(Reject::Hitbox);
    }
    if !world.line_of_sight(claim.origin, claim.point) {
        return Verdict::Rejected(Reject::Blocked);
    }
    Verdict::Hit { zone: claim.zone, range_m: along }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::movement::collision::{Brush, BrushKind};

    fn stand(pos: Vec3) -> Pose {
        Pose { pos, yaw: 0.0, stance: Stance::Stand }
    }

    #[test]
    fn ray_hits_head_and_torso() {
        let d = GameData::embedded();
        let p = stand(Vec3::new(0.0, 0.0, -10.0));
        let eye = Vec3::new(0.0, 1.6, 0.0);
        let (zone, t) = raycast(&d, &p, eye, Vec3::NEG_Z, 100.0).unwrap();
        assert_eq!(zone, Zone::Head);
        assert!((t - (10.0 - 0.12)).abs() < 1e-3);
        let (zone, _) = raycast(&d, &p, Vec3::new(0.0, 1.1, 0.0), Vec3::NEG_Z, 100.0).unwrap();
        assert_eq!(zone, Zone::Torso);
        let (zone, _) = raycast(&d, &p, Vec3::new(0.11, 0.4, 0.0), Vec3::NEG_Z, 100.0).unwrap();
        assert_eq!(zone, Zone::Legs);
        assert!(raycast(&d, &p, Vec3::new(1.0, 1.6, 0.0), Vec3::NEG_Z, 100.0).is_none());
    }

    /// A ray through the head's centre hits the head (a bot aims there).
    #[test]
    fn the_head_centre_is_in_the_head() {
        let d = GameData::embedded();
        let p = stand(Vec3::new(3.0, 0.0, -10.0));
        let head = zone_center(&d, &p, Zone::Head).unwrap();
        let eye = Vec3::new(0.0, 1.6, 0.0);
        assert_eq!(raycast(&d, &p, eye, (head - eye).normalize(), 100.0).map(|h| h.0), Some(Zone::Head));
    }

    #[test]
    fn crouching_lowers_the_head() {
        let d = GameData::embedded();
        let mut p = stand(Vec3::new(0.0, 0.0, -10.0));
        p.stance = Stance::Crouch;
        let hit = raycast(&d, &p, Vec3::new(0.0, 1.6, 0.0), Vec3::NEG_Z, 100.0);
        assert!(hit.is_none(), "a standing-head-height ray passes over a crouched player");
    }

    #[test]
    fn rotated_boxes() {
        let d = GameData::embedded();
        let mut p = stand(Vec3::ZERO);
        p.yaw = std::f32::consts::FRAC_PI_2;
        let arm = zone_boxes(&d, &p).find(|b| b.zone == Zone::Arms).unwrap();
        // the arm offset (x = +/-0.29) is now along z
        assert!(arm.center.x.abs() < 1e-4 && (arm.center.z.abs() - 0.29).abs() < 1e-4);
    }

    #[test]
    fn history_interpolates_and_trims() {
        let mut h = PoseHistory::default();
        for t in 0..100 {
            h.push(t, stand(Vec3::new(t as f32, 0.0, 0.0)), 30);
        }
        assert_eq!(h.entries.len(), 31);
        assert!((h.sample(80.5).unwrap().pos.x - 80.5).abs() < 1e-4);
        assert_eq!(h.sample(10.0).unwrap().pos.x, 69.0, "clamped to oldest");
        assert!((h.speed_at(90.0, 60) - 60.0).abs() < 1e-3);
    }

    fn claim_setup() -> (GameData, CollisionWorld, PoseHistory, FiredShot) {
        let d = GameData::embedded();
        let mut h = PoseHistory::default();
        // victim strafes along +x at 6 m/s (0.1 m per tick), 20 m north of the shooter
        for t in 0..=100 {
            h.push(t, stand(Vec3::new(t as f32 * 0.1 - 5.0, 0.0, -20.0)), 30);
        }
        let shot = FiredShot {
            seq: 1,
            tick: 100,
            origin: Vec3::new(0.0, 1.6, 0.0),
            aim: Vec3::NEG_Z,
            spread_deg: 0.5,
            ammo_slot: 0,
        };
        (d, CollisionWorld::default(), h, shot)
    }

    #[test]
    fn rewound_claim_is_accepted() {
        let (d, w, h, shot) = claim_setup();
        // At tick 94 the victim was at x = 4.4: the client saw it there and shot it.
        let target = Vec3::new(4.4, 1.15, -20.0);
        let dir = (target - shot.origin).normalize();
        let mut s = shot;
        s.aim = dir;
        let claim = HitClaim { origin: shot.origin, dir, view_tick: 94.0, zone: Zone::Torso, point: target };
        assert!(matches!(validate_claim(&d, &w, &s, &claim, &h, 100, 300.0), Verdict::Hit { zone: Zone::Torso, .. }));
    }

    #[test]
    fn rewind_is_capped() {
        let (d, w, h, shot) = claim_setup();
        // Claiming where the victim was 0.5 s ago: further back than 200 ms, so it fails.
        let target = Vec3::new(2.0, 1.15, -20.0);
        let dir = (target - shot.origin).normalize();
        let mut s = shot;
        s.aim = dir;
        let claim = HitClaim { origin: shot.origin, dir, view_tick: 70.0, zone: Zone::Torso, point: target };
        assert_eq!(validate_claim(&d, &w, &s, &claim, &h, 100, 300.0), Verdict::Rejected(Reject::Hitbox));
    }

    #[test]
    fn walls_and_aim_are_checked() {
        let (d, mut w, h, shot) = claim_setup();
        let target = Vec3::new(5.0, 1.15, -20.0);
        let dir = (target - shot.origin).normalize();
        let claim = HitClaim { origin: shot.origin, dir, view_tick: 100.0, zone: Zone::Torso, point: target };
        // aim far off the host's copy of the shooter's view
        assert_eq!(validate_claim(&d, &w, &shot, &claim, &h, 100, 300.0), Verdict::Rejected(Reject::Aim));
        let mut s = shot;
        s.aim = dir;
        w.push(Brush::cuboid(Vec3::new(-10.0, 0.0, -11.0), Vec3::new(10.0, 3.0, -10.0), BrushKind::Solid));
        assert_eq!(validate_claim(&d, &w, &s, &claim, &h, 100, 300.0), Verdict::Rejected(Reject::Blocked));
        let mut bad = claim;
        bad.origin.x += 2.0;
        assert_eq!(validate_claim(&d, &w, &s, &bad, &h, 100, 300.0), Verdict::Rejected(Reject::Origin));
    }
}
