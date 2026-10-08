//! Replicated components, inputs, messages and channels.

use bevy::ecs::entity::MapEntities;
use bevy::prelude::*;
use lightyear::prelude::input::InputConfig;
use lightyear::prelude::input::native::InputPlugin;
use lightyear::prelude::*;
use serde::{Deserialize, Serialize};
use vetf_sim::Zone;
use vetf_sim::combat::{HaloState, Health};
use vetf_sim::data::{AmmoChoice, Ruleset};
use vetf_sim::gear::HaloChoice;
use vetf_sim::hitbox::HitClaim;
use vetf_sim::input::{Buttons, InputFrame};
use vetf_sim::items::ItemState;
use vetf_sim::level::Team;
use vetf_sim::movement::MoveState;
use vetf_sim::player::{Loadout, Wounds};
use vetf_sim::weapon::WeaponState;

/// Bumped whenever the protocol changes; part of the netcode protocol id, so old builds cannot connect.
pub const PROTOCOL_VERSION: u64 = 4;

/// netcode.io protocol id shared by host and clients.
pub fn protocol_id() -> u64 {
    0x5641_4c5f_4554_4600 ^ PROTOCOL_VERSION
}

/// netcode.io private key. Prototype only: a fixed key means anyone with the build can mint tokens.
pub const PRIVATE_KEY: [u8; 32] = [0; 32];

// ---------------------------------------------------------------------------------------------- components

/// Stable player id: the netcode client id (0 for the host).
#[derive(Component, Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct PlayerId(pub u64);

#[derive(Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct PlayerInfo {
    pub name: String,
    pub team: Option<Team>,
}

/// Movement state. Predicted by the owner, interpolated for everyone else.
#[derive(Component, Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct PlayerMove(pub MoveState);

/// Where the player looks (from their inputs). Drives remote bodies and the host's shot checks.
#[derive(Component, Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Default)]
pub struct PlayerLook {
    pub yaw: f32,
    pub pitch: f32,
}

/// Weapon state. Predicted by the owner.
#[derive(Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct PlayerWeapon(pub WeaponState);

/// Healing items left and the item in use. Predicted by the owner.
#[derive(Component, Serialize, Deserialize, Clone, Debug, PartialEq, Default)]
pub struct PlayerItems(pub ItemState);

/// Gun, ammo, attachments and halo for the current life.
#[derive(Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct PlayerLoadout(pub Loadout);

/// Host-authoritative health, halo shields and wounds.
#[derive(Component, Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct Vitals {
    pub health: Health,
    pub halo: HaloState,
    pub wounds: Wounds,
    /// Seconds until respawn while dead.
    pub respawn_s: f32,
    /// Seconds of spawn protection left.
    pub protected_s: f32,
}

#[derive(Component, Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Default)]
pub struct Score {
    pub kills: u16,
    pub deaths: u16,
}

/// The player's connection as the host measures it, and their lobby state.
#[derive(Component, Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct PlayerNet {
    /// Round-trip time to the host, in milliseconds (the host's own player: 0).
    pub ping_ms: u16,
    /// READY in the lobby (cleared when the match starts or the player switches team).
    pub ready: bool,
}

pub use vetf_sim::data::Mode as MatchMode;

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum MatchPhase {
    /// Before a match: players pick loadouts, switch teams and ready up; the host starts it.
    Lobby,
    Live,
    Ended {
        winner: Option<Team>,
    },
}

/// One replicated entity per match.
#[derive(Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct MatchState {
    pub mode: MatchMode,
    pub map: String,
    pub score_a: u32,
    pub score_b: u32,
    pub score_limit: u32,
    pub time_left_s: f32,
    pub phase: MatchPhase,
    /// The host's lobby name (HOST GAME), shown in the lobby.
    pub lobby_name: String,
    /// Players including the host (HOST GAME's MAX PLAYERS): half of it per team.
    pub max_players: u32,
    /// What this mode switches on (status effects, regional items). Clients use it for the HUD and menus.
    pub rules: Ruleset,
}

/// What a player does in the lobby. The host checks each one: only in the lobby, a team switch only to a
/// team with a free slot, and only the host's own player can start the match.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum LobbyAction {
    Ready(bool),
    SwitchTeam,
    Start,
}

// ---------------------------------------------------------------------------------------------- input

/// One tick of input, as sent on the wire (see [`vetf_sim::input::InputFrame`]).
#[derive(Serialize, Deserialize, Debug, Default, PartialEq, Clone, Copy, Reflect)]
pub struct PlayerInput {
    pub move_x: f32,
    pub move_y: f32,
    pub yaw: f32,
    pub pitch: f32,
    pub buttons: u16,
    /// Reload radial pick: 1..=6, or 0.
    pub reload_slot: u8,
    /// Heal ring pick: kit slot 1..=8 and region 1..=4 (0 = none / whole body).
    pub use_item: u8,
    pub use_zone: u8,
}

impl MapEntities for PlayerInput {
    fn map_entities<M: EntityMapper>(&mut self, _mapper: &mut M) {}
}

impl PlayerInput {
    pub fn frame(&self) -> InputFrame {
        InputFrame {
            movement: Vec2::new(self.move_x, self.move_y),
            yaw: self.yaw,
            pitch: self.pitch,
            buttons: Buttons(self.buttons),
            reload_slot: self.reload_slot,
            use_item: self.use_item,
            use_zone: self.use_zone,
        }
    }

    pub fn from_frame(f: &InputFrame) -> Self {
        Self {
            move_x: f.movement.x,
            move_y: f.movement.y,
            yaw: f.yaw,
            pitch: f.pitch,
            buttons: f.buttons.0,
            reload_slot: f.reload_slot,
            use_item: f.use_item,
            use_zone: f.use_zone,
        }
    }
}

// ---------------------------------------------------------------------------------------------- messages

/// What a player wants to spawn with (applied at the next spawn).
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct LoadoutChoice {
    pub weapon: String,
    /// Magazines in slot order: one to six, no gaps, each with its own ammo. Slot 1 starts in the gun, and
    /// a slot's index is its position on the reload wheel.
    pub mags: Vec<AmmoChoice>,
    /// Attachment ids, at most one per category; categories left out use the weapon's defaults.
    pub attachments: Vec<String>,
    /// The halo: one core and a tier per arc, within the armor data's loadout tier caps.
    pub halo: HaloChoice,
    /// Agent id (cosmetic for now: agents have no abilities in this build).
    pub agent: String,
}

/// Client -> host: a new loadout from the Loadout screen during a match, applied at the next spawn.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct LoadoutUpdate {
    pub loadout: LoadoutChoice,
}

/// Client -> host, after connecting.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Hello {
    pub name: String,
    pub loadout: LoadoutChoice,
    /// [`vetf_sim::GameData::fingerprint`]: host and client must run the same gameplay numbers.
    pub data_fingerprint: u64,
}

/// Client -> host: one of my shots hit a player.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct ShotClaim {
    /// The shooter's shot number (`WeaponState::shot_seq`).
    pub seq: u32,
    pub victim: u64,
    pub hit: HitClaim,
}

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum HitKind {
    Shield,
    Health,
    Kill,
}

/// Host -> shooter: a claim was accepted (hit marker).
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct HitConfirm {
    pub victim: u64,
    pub zone: Zone,
    pub kind: HitKind,
    pub shield_broke: bool,
}

/// Host -> victim: you were hit (damage direction indicator).
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct DamageTaken {
    pub from: Vec3,
    pub zone: Zone,
    pub shield: bool,
}

/// Host -> everyone.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct KillFeed {
    /// `None` for suicides and falls.
    pub killer: Option<u64>,
    pub victim: u64,
    pub zone: Option<Zone>,
}

/// Host -> everyone but the shooter: draw a tracer.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct ShotFx {
    pub shooter: u64,
    pub origin: Vec3,
    pub end: Vec3,
}

// ---------------------------------------------------------------------------------------------- channels

/// Reliable, ordered: hello, kill feed, hit confirms.
pub struct ReliableChannel;
/// Reliable, unordered: shot claims (each one matters, order does not).
pub struct ClaimChannel;
/// Unreliable: cosmetic effects.
pub struct FxChannel;

// ---------------------------------------------------------------------------------------------- rollback / interpolation

fn move_should_rollback(confirmed: &PlayerMove, predicted: &PlayerMove) -> bool {
    !confirmed.0.approx_eq(&predicted.0)
}

fn weapon_should_rollback(confirmed: &PlayerWeapon, predicted: &PlayerWeapon) -> bool {
    let (a, b) = (&confirmed.0, &predicted.0);
    a.rounds != b.rounds
        || a.loaded != b.loaded
        || a.action != b.action
        || a.fire_mode != b.fire_mode
        || a.shot_seq != b.shot_seq
        || a.cooldown != b.cooldown
        || (a.ads - b.ads).abs() > 0.05
}

fn items_should_rollback(confirmed: &PlayerItems, predicted: &PlayerItems) -> bool {
    confirmed != predicted
}

fn lerp_move(start: PlayerMove, end: PlayerMove, t: f32) -> PlayerMove {
    let mut m = if t < 0.5 { start.0 } else { end.0 };
    m.pos = start.0.pos.lerp(end.0.pos, t);
    m.vel = start.0.vel.lerp(end.0.vel, t);
    m.eye = start.0.eye + (end.0.eye - start.0.eye) * t;
    PlayerMove(m)
}

fn lerp_look(start: PlayerLook, end: PlayerLook, t: f32) -> PlayerLook {
    use std::f32::consts::{PI, TAU};
    let d = (end.yaw - start.yaw + PI).rem_euclid(TAU) - PI;
    PlayerLook { yaw: start.yaw + d * t, pitch: start.pitch + (end.pitch - start.pitch) * t }
}

// ---------------------------------------------------------------------------------------------- plugin

/// The shared protocol. Add after lightyear's `ClientPlugins` / `ServerPlugins`.
pub struct ProtocolPlugin {
    pub input_redundancy: u16,
}

impl Plugin for ProtocolPlugin {
    fn build(&self, app: &mut App) {
        app.add_plugins(InputPlugin::<PlayerInput> {
            config: InputConfig { lag_compensation: true, packet_redundancy: self.input_redundancy, ..default() },
        });

        app.component::<PlayerId>().replicate();
        app.component::<PlayerInfo>().replicate();
        app.component::<PlayerMove>()
            .replicate()
            .predict()
            .with_rollback_condition(move_should_rollback)
            .add_interpolation_with(lerp_move);
        app.component::<PlayerLook>().replicate().add_interpolation_with(lerp_look);
        app.component::<PlayerWeapon>().replicate().predict().with_rollback_condition(weapon_should_rollback);
        app.component::<PlayerItems>().replicate().predict().with_rollback_condition(items_should_rollback);
        app.component::<PlayerLoadout>().replicate();
        app.component::<Vitals>().replicate();
        app.component::<Score>().replicate();
        app.component::<PlayerNet>().replicate();
        app.component::<MatchState>().replicate();

        app.add_channel::<ReliableChannel>(ChannelSettings {
            mode: ChannelMode::OrderedReliable(ReliableSettings::default()),
            ..default()
        })
        .add_direction(NetworkDirection::Bidirectional);
        app.add_channel::<ClaimChannel>(ChannelSettings {
            mode: ChannelMode::UnorderedReliable(ReliableSettings::default()),
            ..default()
        })
        .add_direction(NetworkDirection::ClientToServer);
        app.add_channel::<FxChannel>(ChannelSettings { mode: ChannelMode::UnorderedUnreliable, ..default() })
            .add_direction(NetworkDirection::ServerToClient);

        // One direction per message type (in host mode both ends share one receiver per type).
        app.register_message::<Hello>().add_direction(NetworkDirection::ClientToServer);
        app.register_message::<LoadoutUpdate>().add_direction(NetworkDirection::ClientToServer);
        app.register_message::<LobbyAction>().add_direction(NetworkDirection::ClientToServer);
        app.register_message::<ShotClaim>().add_direction(NetworkDirection::ClientToServer);
        app.register_message::<HitConfirm>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<DamageTaken>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<KillFeed>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<ShotFx>().add_direction(NetworkDirection::ServerToClient);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::GameData;

    /// Wire types must survive a serde round trip (lightyear serialises them with bincode-style serde).
    fn roundtrip<T: Serialize + for<'de> Deserialize<'de> + PartialEq + std::fmt::Debug>(v: &T) {
        let bytes = ron::to_string(v).unwrap();
        let back: T = ron::from_str(&bytes).unwrap();
        assert_eq!(&back, v);
    }

    #[test]
    fn components_and_messages_roundtrip() {
        let d = GameData::embedded();
        let loadout = Loadout::default_for(&d, MatchMode::Range);
        let ws = WeaponState::new(&d, &loadout.weapon);
        let ms = MoveState::spawn(Vec3::new(1.0, 2.0, 3.0), 1.6);
        roundtrip(&PlayerMove(ms));
        // a gun coming up from a sprint with a trigger pull waiting
        roundtrip(&PlayerWeapon(WeaponState { sprint_lock: 9, fire_queued: true, ..ws.clone() }));
        roundtrip(&PlayerWeapon(ws));
        roundtrip(&PlayerItems(ItemState::new(&loadout.kit)));
        roundtrip(&PlayerLoadout(loadout.clone()));
        roundtrip(&Vitals {
            health: Health::new(d.armor.zone_hp),
            halo: HaloState::full(&loadout.halo),
            wounds: Wounds::default(),
            respawn_s: 0.0,
            protected_s: 1.5,
        });
        roundtrip(&ShotClaim {
            seq: 7,
            victim: 42,
            hit: HitClaim {
                origin: Vec3::ONE,
                dir: Vec3::NEG_Z,
                view_tick: 120.5,
                zone: Zone::Head,
                point: Vec3::new(0.0, 1.6, -10.0),
            },
        });
        let choice = LoadoutChoice {
            weapon: "ar7_mako".into(),
            mags: vec![AmmoChoice::STANDARD, AmmoChoice { kind: vetf_sim::data::AmmoKind::ArmorPiercing, tier: 2 }],
            attachments: vec!["optic_holo".into()],
            halo: HaloChoice::from_preset(d.armor.preset("arm_mender_scout").unwrap()),
            agent: "kestrel".into(),
        };
        roundtrip(&Hello { name: "KESTREL_YOU".into(), loadout: choice.clone(), data_fingerprint: d.fingerprint });
        roundtrip(&LoadoutUpdate { loadout: choice });
        roundtrip(&KillFeed { killer: Some(1), victim: 2, zone: Some(Zone::Head) });
        roundtrip(&MatchState {
            mode: MatchMode::Tdm,
            map: "showhome".into(),
            score_a: 3,
            score_b: 4,
            score_limit: 50,
            time_left_s: 12.5,
            phase: MatchPhase::Ended { winner: None },
            lobby_name: "ASH'S GAME".into(),
            max_players: 10,
            rules: d.rules.rulesets.tdm,
        });
        // The lobby: its phase, READY and the actions players send.
        roundtrip(&MatchPhase::Lobby);
        roundtrip(&PlayerNet { ping_ms: 48, ready: true });
        for action in [LobbyAction::Ready(true), LobbyAction::Ready(false), LobbyAction::SwitchTeam, LobbyAction::Start]
        {
            roundtrip(&action);
        }
    }

    /// The Loadout screen's output: six ordered magazines with mixed ammo, a mixed-tier custom halo and
    /// the agent survive the wire (ron here; lightyear's binary serde uses the same derive).
    #[test]
    fn loadout_choice_with_six_mags_and_a_custom_halo_roundtrips() {
        use vetf_sim::ZoneTable;
        use vetf_sim::data::{AmmoKind, Core};
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let choice = LoadoutChoice {
            weapon: "sk9_skink".into(),
            mags: vec![ap(2), AmmoChoice::STANDARD, AmmoChoice { kind: AmmoKind::Rip, tier: 3 }, ap(1), ap(3), ap(2)],
            attachments: vec!["optic_reddot".into(), "skink_mag_60".into(), "laser".into()],
            halo: HaloChoice { core: Core::Phase, tiers: ZoneTable { head: 3, torso: 1, arms: 0, legs: 2 } },
            agent: "solace".into(),
        };
        roundtrip(&LoadoutUpdate { loadout: choice.clone() });
        let text = ron::to_string(&choice).unwrap();
        let back: LoadoutChoice = ron::from_str(&text).unwrap();
        assert_eq!(back.mags.len(), 6);
        assert_eq!(back.mags[2], AmmoChoice { kind: AmmoKind::Rip, tier: 3 }, "slot order is kept");
        assert_eq!(back.halo.tiers.legs, 2);
        assert_eq!(protocol_id() ^ 0x5641_4c5f_4554_4600, PROTOCOL_VERSION);
    }

    #[test]
    fn input_frame_roundtrip() {
        let f = InputFrame {
            movement: Vec2::new(0.5, -1.0),
            yaw: 1.0,
            pitch: -0.2,
            buttons: Buttons(0b1011),
            reload_slot: 3,
            use_item: 2,
            use_zone: 4,
        };
        assert_eq!(PlayerInput::from_frame(&f).frame(), f);
    }

    #[test]
    fn interpolation_takes_the_short_way_round() {
        let a = PlayerLook { yaw: 6.2, pitch: 0.0 };
        let b = PlayerLook { yaw: 0.1, pitch: 0.2 };
        let m = lerp_look(a, b, 0.5);
        let half = (0.1 + std::f32::consts::TAU - 6.2) / 2.0;
        assert!((m.yaw - (6.2 + half)).abs() < 1e-4, "{}", m.yaw);
    }
}
