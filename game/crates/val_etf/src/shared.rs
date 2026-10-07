//! Pieces used by both the host and clients: input marking, the predicted simulation, local shot events.

use crate::config::{CurrentLevel, Data};
use bevy::prelude::*;
use lightyear::prelude::input::native::{ActionState, InputMarker};
use lightyear::prelude::*;
use vetf_net::{PlayerId, PlayerInput, PlayerItems, PlayerLoadout, PlayerMove, PlayerWeapon, Vitals};
use vetf_sim::player;
use vetf_sim::weapon::Shot;

pub struct SharedPlugin;

impl Plugin for SharedPlugin {
    fn build(&self, app: &mut App) {
        app.add_message::<LocalShot>()
            .add_observer(mark_controlled)
            .add_systems(FixedUpdate, simulate_predicted.in_set(SimSystems::Simulate))
            .configure_sets(FixedUpdate, (SimSystems::Simulate, SimSystems::Resolve).chain());
    }
}

#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub enum SimSystems {
    /// Advance players by one tick.
    Simulate,
    /// Host: validate shot claims and apply damage.
    Resolve,
}

/// A shot fired by the local player (outside rollback): drives hit detection, tracer and recoil.
#[derive(Message, Debug, Clone, Copy)]
pub struct LocalShot {
    pub shot: Shot,
    pub player: u64,
    pub origin: Vec3,
    pub yaw: f32,
    pub pitch: f32,
}

/// The local player's entity gets the input marker, so lightyear sends its inputs.
/// In host mode this is the host's authoritative player entity itself.
fn mark_controlled(trigger: On<Add, Controlled>, players: Query<(), With<PlayerId>>, mut commands: Commands) {
    if players.contains(trigger.entity) {
        commands.entity(trigger.entity).insert(InputMarker::<PlayerInput>::default());
    }
}

/// Remote client: predict our own player. (The host simulates authoritative players in `server.rs`;
/// `Without<Replicate>` keeps this from running a second time on the host's own entity.)
#[allow(clippy::type_complexity)]
fn simulate_predicted(
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    rollback: Option<Res<Rollback>>,
    mut players: Query<
        (
            &PlayerId,
            Option<&ActionState<PlayerInput>>,
            &mut PlayerMove,
            &mut PlayerWeapon,
            &mut PlayerItems,
            &PlayerLoadout,
            Option<&Vitals>,
        ),
        (With<Predicted>, Without<Replicate>),
    >,
    mut shots: MessageWriter<LocalShot>,
) {
    let Some(level) = level else { return };
    for (id, input, mut mv, mut weapon, mut items, loadout, vitals) in &mut players {
        if vitals.is_some_and(|v| v.health.dead) {
            continue;
        }
        let frame = input.map(|a| a.0.frame()).unwrap_or_default();
        let mut wounds = vitals.map(|v| v.wounds).unwrap_or_default();
        let ev = player::step(&data, &level, &loadout.0, &mut mv.0, &mut weapon.0, &mut items.0, &mut wounds, &frame);
        if let (Some(shot), None) = (ev.weapon.shot, &rollback) {
            shots.write(LocalShot { shot, player: id.0, origin: mv.0.eye_pos(), yaw: frame.yaw, pitch: frame.pitch });
        }
    }
}
