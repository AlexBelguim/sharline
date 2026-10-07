//! Engine-free gameplay simulation for val etf.
//!
//! Everything here is plain Rust (no Bevy) so it can be unit-tested quickly and run identically on the
//! host and on predicting clients. Numbers come from `game/assets/data/*.ron` via [`data::GameData`].

pub mod combat;
pub mod data;
pub mod input;
pub mod level;
pub mod movement;
pub mod recoil;
pub mod rng;
pub mod weapon;
pub mod zone;

pub use data::GameData;
pub use zone::{Zone, ZoneSet, ZoneTable};
