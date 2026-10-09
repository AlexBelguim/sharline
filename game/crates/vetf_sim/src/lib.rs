//! Engine-free gameplay simulation for val etf.
//!
//! Everything here is plain Rust (no Bevy) so it can be unit-tested quickly and run identically on the
//! host and on predicting clients. Numbers come from `game/assets/data/*.ron` via [`data::GameData`].

pub mod bot;
pub mod combat;
pub mod data;
pub mod gear;
pub mod hitbox;
pub mod input;
pub mod items;
pub mod level;
pub mod maps;
pub mod movement;
pub mod player;
pub mod recoil;
pub mod rng;
pub mod streak;
pub mod weapon;
pub mod zone;

pub use data::GameData;
pub use zone::{Zone, ZoneSet, ZoneTable};
