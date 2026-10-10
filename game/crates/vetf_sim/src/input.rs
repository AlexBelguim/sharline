//! One tick of player input. This is what clients send to the host every fixed tick.

use glam::{Quat, Vec2, Vec3};
use serde::{Deserialize, Serialize};

/// Held buttons as a bitmask. Presses are detected by comparing with the previous tick's buttons,
/// which the simulation keeps in its own state (so prediction rollback replays them correctly).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub struct Buttons(pub u16);

impl Buttons {
    pub const JUMP: u16 = 1 << 0;
    pub const CROUCH: u16 = 1 << 1;
    pub const SPRINT: u16 = 1 << 2;
    pub const WALK: u16 = 1 << 3;
    pub const FIRE: u16 = 1 << 4;
    pub const ADS: u16 = 1 << 5;
    pub const RELOAD: u16 = 1 << 6;
    pub const MAG_CHECK: u16 = 1 << 7;
    pub const FIRE_MODE: u16 = 1 << 8;
    pub const INTERACT: u16 = 1 << 9;
    /// Equip a smoke grenade / molotov. Pressing its selected key again cancels.
    pub const THROW_SMOKE: u16 = 1 << 10;
    pub const THROW_MOLOTOV: u16 = 1 << 11;
    /// Turn the laser on or off (a press toggles it, see `weapon::WeaponState::laser_on`).
    pub const LASER: u16 = 1 << 12;
    /// Put away a selected grenade without consuming it (also used by editor/pause guards).
    pub const THROW_CANCEL: u16 = 1 << 13;

    pub fn held(self, bit: u16) -> bool {
        self.0 & bit != 0
    }

    /// Held now and not on the previous tick.
    pub fn pressed(self, prev: Buttons, bit: u16) -> bool {
        self.held(bit) && !prev.held(bit)
    }

    pub fn set(&mut self, bit: u16, on: bool) {
        if on {
            self.0 |= bit;
        } else {
            self.0 &= !bit;
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
pub struct InputFrame {
    /// x = strafe right, y = forward; each in [-1, 1].
    pub movement: Vec2,
    /// View angles in radians. Yaw turns around +Y (0 looks down -Z), pitch > 0 looks up.
    pub yaw: f32,
    pub pitch: f32,
    pub buttons: Buttons,
    /// A magazine picked on the reload radial: 1..=6 for that slot, 0 for none. Sent for one tick.
    pub reload_slot: u8,
    /// An item picked on the heal ring: kit slot 1..=8, 0 for none. Sent for one tick.
    pub use_item: u8,
    /// The region for a region item: 1..=4 in `Zone::ALL` order, 0 for none.
    pub use_zone: u8,
}

impl InputFrame {
    pub fn view_rotation(&self) -> Quat {
        view_rotation(self.yaw, self.pitch)
    }

    pub fn view_dir(&self) -> Vec3 {
        view_dir(self.yaw, self.pitch)
    }

    /// Clamp values a client could send out of range.
    pub fn sanitized(mut self) -> Self {
        let m = self.movement;
        self.movement = if m.is_finite() { m.clamp(Vec2::splat(-1.0), Vec2::splat(1.0)) } else { Vec2::ZERO };
        if !self.yaw.is_finite() {
            self.yaw = 0.0;
        }
        self.yaw = self.yaw.rem_euclid(std::f32::consts::TAU);
        self.pitch = if self.pitch.is_finite() { self.pitch.clamp(-MAX_PITCH, MAX_PITCH) } else { 0.0 };
        if self.reload_slot as usize > crate::weapon::MAX_MAGS {
            self.reload_slot = 0;
        }
        if self.use_item as usize > crate::items::MAX_KIT || self.use_zone as usize > crate::Zone::ALL.len() {
            self.use_item = 0;
            self.use_zone = 0;
        }
        self
    }
}

/// Look up/down limit (radians), just short of vertical.
pub const MAX_PITCH: f32 = 1.54;

pub fn view_rotation(yaw: f32, pitch: f32) -> Quat {
    Quat::from_rotation_y(yaw) * Quat::from_rotation_x(pitch)
}

pub fn view_dir(yaw: f32, pitch: f32) -> Vec3 {
    let (sy, cy) = yaw.sin_cos();
    let (sp, cp) = pitch.sin_cos();
    Vec3::new(-sy * cp, sp, -cy * cp)
}

/// Horizontal facing (yaw only) as a forward / right pair on the XZ plane.
pub fn yaw_basis(yaw: f32) -> (Vec3, Vec3) {
    let (s, c) = yaw.sin_cos();
    (Vec3::new(-s, 0.0, -c), Vec3::new(c, 0.0, -s))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn view_dir_matches_rotation() {
        for (y, p) in [(0.0, 0.0), (1.0, 0.3), (-2.0, -0.7), (3.0, 1.2)] {
            let a = view_dir(y, p);
            let b = view_rotation(y, p) * Vec3::NEG_Z;
            assert!((a - b).length() < 1e-5, "{a} vs {b}");
        }
        let (f, r) = yaw_basis(0.3);
        assert!((f - view_dir(0.3, 0.0)).length() < 1e-6);
        assert!((r - view_rotation(0.3, 0.0) * Vec3::X).length() < 1e-6);
    }

    #[test]
    fn edges() {
        let prev = Buttons(Buttons::FIRE);
        let now = Buttons(Buttons::FIRE | Buttons::RELOAD);
        assert!(now.pressed(prev, Buttons::RELOAD));
        assert!(!now.pressed(prev, Buttons::FIRE));
    }

    #[test]
    fn sanitize_clamps() {
        let f = InputFrame {
            movement: Vec2::new(5.0, f32::NAN),
            yaw: -0.5,
            pitch: 9.0,
            buttons: Buttons(0),
            reload_slot: 7,
            use_item: 9,
            use_zone: 1,
        }
        .sanitized();
        assert_eq!(f.movement, Vec2::ZERO);
        assert_eq!((f.reload_slot, f.use_item, f.use_zone), (0, 0, 0));
        assert!(f.yaw >= 0.0 && f.pitch == MAX_PITCH);
    }
}
