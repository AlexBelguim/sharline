//! A playable level as the simulation sees it: collision brushes, ziplines, spawns and the kill plane.
//! Visual meshes are built from the same data by the game crate.

use crate::movement::collision::CollisionWorld;
use glam::Vec3;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Zipline {
    pub a: Vec3,
    pub b: Vec3,
}

impl Zipline {
    /// Closest point parameter (0..1) and distance from `p`.
    pub fn closest(&self, p: Vec3) -> (f32, f32) {
        let ab = self.b - self.a;
        let s = ((p - self.a).dot(ab) / ab.length_squared().max(1e-6)).clamp(0.0, 1.0);
        (s, p.distance(self.a + ab * s))
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Team {
    /// Teal (west side on Showhome).
    A,
    /// Coral (east side).
    B,
}

impl Team {
    pub fn other(self) -> Team {
        match self {
            Team::A => Team::B,
            Team::B => Team::A,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SpawnPoint {
    pub pos: Vec3,
    pub yaw: f32,
    /// `None` = any team (free-for-all / range).
    pub team: Option<Team>,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Level {
    pub name: String,
    pub world: CollisionWorld,
    pub ziplines: Vec<Zipline>,
    pub spawns: Vec<SpawnPoint>,
    /// Falling below this height kills / resets the player.
    pub kill_y: f32,
}

impl Level {
    pub fn nearest_zipline(&self, p: Vec3, radius: f32) -> Option<(usize, f32)> {
        self.ziplines
            .iter()
            .enumerate()
            .map(|(i, z)| {
                let (s, d) = z.closest(p);
                (i, s, d)
            })
            .filter(|(_, _, d)| *d <= radius)
            .min_by(|a, b| a.2.total_cmp(&b.2))
            .map(|(i, s, _)| (i, s))
    }

    pub fn spawns_for(&self, team: Option<Team>) -> impl Iterator<Item = &SpawnPoint> {
        self.spawns
            .iter()
            .filter(move |s| s.team.is_none() || team.is_none() || s.team == team)
    }
}
