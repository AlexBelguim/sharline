//! Network protocol for val etf (lightyear 0.30, listen server).
//!
//! Model (design/systems/diagrams/net_architecture.png): the host runs server and player in one app
//! ("HostClient"). Each remote client predicts its own player and interpolates everyone else. Clients
//! send inputs every tick; shots are resolved on the shooter's client and sent as claims, which the host
//! verifies with lag compensation before applying damage.
//!
//! Register [`ProtocolPlugin`] after lightyear's client/server plugin groups and before spawning any
//! client or server entity, in the same order on every build (lightyear checks a protocol hash).

pub mod join_code;
pub mod protocol;
pub mod recap;

pub use join_code::JoinCode;
pub use protocol::*;
pub use recap::{DamageLine, Hit, LifeLog, LifeRecap};
