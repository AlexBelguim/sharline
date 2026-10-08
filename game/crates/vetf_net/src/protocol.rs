//! Replicated components, inputs, messages and channels.

use bevy::ecs::entity::MapEntities;
use bevy::prelude::*;
use lightyear::prelude::input::InputConfig;
use lightyear::prelude::input::native::InputPlugin;
use lightyear::prelude::*;
use serde::{Deserialize, Serialize};
use vetf_sim::Zone;
use vetf_sim::combat::{HaloState, Health};
use vetf_sim::data::{AmmoChoice, DeathmatchLoadout, Ruleset};
use vetf_sim::gear::HaloChoice;
use vetf_sim::hitbox::HitClaim;
use vetf_sim::input::{Buttons, InputFrame};
use vetf_sim::items::ItemState;
use vetf_sim::level::Team;
use vetf_sim::movement::MoveState;
use vetf_sim::player::{Loadout, Wounds};
use vetf_sim::weapon::WeaponState;

/// Bumped whenever the protocol changes; part of the netcode protocol id, so old builds cannot connect.
pub const PROTOCOL_VERSION: u64 = 9;

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
    /// A test bot the host runs (no client behind it): the lobby and the scoreboard mark it.
    pub bot: bool,
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
    /// Dead from a death in a live match (not a reset): the player respawns when they ask
    /// ([`RespawnRequest`]) once `respawn_s` is out, or on their own `rules.ron` `auto_respawn_s` later. The
    /// death screen shows while it is set.
    pub awaiting_respawn: bool,
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

/// The agent this player plays, as the host says (an `agents.ron` id; cosmetic for now). Team deathmatch and
/// free-for-all have no agent pick (DIRECTION_LOG 17): the host deals one at random when the match starts and
/// it is kept until the match ends; `None` in the lobby. The gun range: the one picked on the Loadout screen.
#[derive(Component, Serialize, Deserialize, Clone, Debug, PartialEq, Eq, Default)]
pub struct PlayerAgent(pub Option<String>);

pub use vetf_sim::data::Mode as MatchMode;

#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum MatchPhase {
    /// Before a match: players pick loadouts, switch teams and ready up; the host starts it.
    Lobby,
    Live,
    Ended {
        /// Team deathmatch: the winning team (`None`: a draw, or a mode without teams).
        winner: Option<Team>,
        /// Free-for-all: the winning player's [`PlayerId`] (`None`: a draw, or a team mode).
        player: Option<u64>,
    },
}

/// One replicated entity per match.
#[derive(Component, Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct MatchState {
    /// Team deathmatch, free-for-all or the gun range. The host can change it in the lobby.
    pub mode: MatchMode,
    pub map: String,
    pub score_a: u32,
    pub score_b: u32,
    pub score_limit: u32,
    pub time_left_s: f32,
    pub phase: MatchPhase,
    /// The host's lobby name (HOST GAME), shown in the lobby.
    pub lobby_name: String,
    /// Players including the host (HOST GAME's MAX PLAYERS): half of it per team in team deathmatch.
    pub max_players: u32,
    /// What this mode switches on (status effects, regional items). Clients use it for the HUD and menus.
    pub rules: Ruleset,
}

impl MatchState {
    /// Players are split into two teams (team deathmatch).
    pub fn has_teams(&self) -> bool {
        self.mode.has_teams()
    }
}

/// What a player does in the lobby. The host checks each one: only in the lobby, a team switch only to a
/// team with a free slot (and only in a mode with teams), and only the host's own player can start the
/// match or change its mode.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum LobbyAction {
    Ready(bool),
    SwitchTeam,
    Start,
    /// The host's match settings: team deathmatch or free-for-all (the gun range stays the range).
    SetMode(MatchMode),
    /// The host adds a test bot (if a seat is free; in team deathmatch to the team with fewer players), or
    /// removes the last one added.
    AddBot,
    RemoveBot,
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
    /// a slot's index is its position on the reload wheel. Team deathmatch and free-for-all load the mode's
    /// count of them with slot 1's ammo ([`LoadoutChoice::shaped`]).
    pub mags: Vec<AmmoChoice>,
    /// Attachment ids, at most one per category (the magazine type among them); categories left out use the
    /// weapon's defaults.
    pub attachments: Vec<String>,
    /// The halo: one core and a tier per arc, within the armor data's loadout tier caps. Team deathmatch and
    /// free-for-all wear one of their armor tiers on their one core instead ([`LoadoutChoice::shaped`]).
    pub halo: HaloChoice,
    /// Agent id, picked in the gun range (cosmetic for now: agents have no abilities in this build). Team
    /// deathmatch and free-for-all have no agent pick: the host deals agents ([`PlayerAgent`]).
    pub agent: String,
}

impl LoadoutChoice {
    /// The ammo of slot 1 (the magazine that starts in the gun): a deathmatch loadout's one ammo type.
    pub fn ammo(&self) -> AmmoChoice {
        self.mags.first().copied().unwrap_or(AmmoChoice::STANDARD)
    }

    /// This loadout as team deathmatch and free-for-all take it (`rules.ron` `deathmatch_loadout`, see
    /// [`vetf_sim::data::RulesFile::fixed_loadout`]): the armor tier its halo makes
    /// ([`DeathmatchLoadout::tier_for`]) on the one halo core, and the mode's count of magazines, all with
    /// slot 1's ammo. Without such rules (the gun range) it is taken as it is. The host and the Loadout screen
    /// both shape a loadout this way, so a loadout saved by an older build still opens (as its nearest picks),
    /// and a client never gets more than the picks it pays for (another core, a mix of ammo, extra
    /// magazines).
    pub fn shaped(&self, fixed: Option<&DeathmatchLoadout>) -> LoadoutChoice {
        let Some(kit) = fixed else { return self.clone() };
        LoadoutChoice {
            mags: vec![self.ammo(); kit.mags as usize],
            halo: HaloChoice::of_tier(kit, kit.tier_for(self.halo.tiers)),
            ..self.clone()
        }
    }

    /// This loadout as `mode` takes it (see [`LoadoutChoice::shaped`]).
    pub fn for_mode(&self, data: &vetf_sim::GameData, mode: MatchMode) -> LoadoutChoice {
        self.shaped(data.rules.fixed_loadout(mode))
    }
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

/// Host -> shooter: a claim was accepted (hit marker, drawn on the victim where the shot hit).
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct HitConfirm {
    pub victim: u64,
    pub zone: Zone,
    pub kind: HitKind,
    pub shield_broke: bool,
    /// The claim's shot number ([`ShotClaim::seq`]): the shooter finds where on the victim its shot landed.
    pub seq: u32,
    /// Where the shot hit, in the world, as the shooter claimed it ([`HitClaim::point`]).
    pub point: Vec3,
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

/// Client -> host: respawn me now (the death screen's RESPAWN, once the respawn timer is out).
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub struct RespawnRequest;

/// Host -> everyone but the shooter: draw a tracer.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub struct ShotFx {
    pub shooter: u64,
    pub origin: Vec3,
    pub end: Vec3,
}

// ---------------------------------------------------------------------------------------------- channels

/// Reliable, ordered: hello, kill feed, hit confirms, respawn requests and life recaps.
pub struct ReliableChannel;
/// Reliable, unordered: shot claims (each one matters, order does not).
pub struct ClaimChannel;
/// Unreliable: cosmetic effects.
pub struct FxChannel;

// ---------------------------------------------------------------------------------------------- rollback / interpolation

fn move_should_rollback(confirmed: &PlayerMove, predicted: &PlayerMove) -> bool {
    !confirmed.0.approx_eq(&predicted.0)
}

/// Every weapon field that decides when the next shot goes off, or where it can go: the raise from a sprint and a
/// trigger pull waiting on it decide whether a shot fires at all, and the bloom sets its random cone. All of them
/// follow from inputs and movement, so they agree unless an input differed.
fn weapon_should_rollback(confirmed: &PlayerWeapon, predicted: &PlayerWeapon) -> bool {
    let (a, b) = (&confirmed.0, &predicted.0);
    a.rounds != b.rounds
        || a.loaded != b.loaded
        || a.action != b.action
        || a.fire_mode != b.fire_mode
        || a.shot_seq != b.shot_seq
        || a.cooldown != b.cooldown
        || a.sprint_lock != b.sprint_lock
        || a.fire_queued != b.fire_queued
        || (a.ads - b.ads).abs() > 0.05
        || (a.bloom_deg - b.bloom_deg).abs() > 0.05
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
        app.component::<PlayerAgent>().replicate();
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
        app.register_message::<RespawnRequest>().add_direction(NetworkDirection::ClientToServer);
        app.register_message::<HitConfirm>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<DamageTaken>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<KillFeed>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<ShotFx>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<crate::recap::LifeRecap>().add_direction(NetworkDirection::ServerToClient);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::GameData;

    /// Wire types must survive lightyear's serializer: postcard (lightyear_serde), which unlike RON is not
    /// self-describing, so a `skip_serializing_if` reachable from a networked type fails here as it would on
    /// the wire. Returns the bytes.
    fn roundtrip<T: Serialize + for<'de> Deserialize<'de> + PartialEq + std::fmt::Debug>(v: &T) -> Vec<u8> {
        let bytes = postcard::to_allocvec(v).unwrap();
        let back: T = postcard::from_bytes(&bytes).unwrap();
        assert_eq!(&back, v);
        bytes
    }

    /// The round trip above catches what RON lets through: an optional field skipped when empty decodes in
    /// RON, but not from postcard's bytes.
    #[test]
    fn the_wire_format_is_not_self_describing() {
        #[derive(Serialize, Deserialize, Debug, PartialEq)]
        struct Skips {
            a: u8,
            #[serde(default, skip_serializing_if = "Option::is_none")]
            b: Option<u8>,
            c: u8,
        }
        let v = Skips { a: 1, b: None, c: 2 };
        assert_eq!(ron::from_str::<Skips>(&ron::to_string(&v).unwrap()).unwrap(), v, "RON hides the hazard");
        let bytes = postcard::to_allocvec(&v).unwrap();
        assert_ne!(postcard::from_bytes::<Skips>(&bytes).ok(), Some(v), "postcard does not");
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
            awaiting_respawn: false,
        });
        roundtrip(&Vitals {
            health: Health::new(d.armor.zone_hp),
            halo: HaloState::full(&loadout.halo),
            wounds: Wounds::default(),
            respawn_s: -2.5,
            protected_s: 0.0,
            awaiting_respawn: true,
        });
        roundtrip(&RespawnRequest);
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
        // A hit confirm carries the shot number and where it hit, for the marker on the victim.
        for kind in [HitKind::Shield, HitKind::Health, HitKind::Kill] {
            roundtrip(&HitConfirm {
                victim: 42,
                zone: Zone::Arms,
                kind,
                shield_broke: kind == HitKind::Shield,
                seq: 7,
                point: Vec3::new(-3.5, 1.42, -18.25),
            });
        }
        roundtrip(&MatchState {
            mode: MatchMode::Tdm,
            map: "showhome".into(),
            score_a: 3,
            score_b: 4,
            score_limit: 50,
            time_left_s: 12.5,
            phase: MatchPhase::Ended { winner: None, player: None },
            lobby_name: "ASH'S GAME".into(),
            max_players: 10,
            rules: d.rules.rulesets.tdm,
        });
        // The lobby: its phase, READY and the actions players send.
        roundtrip(&MatchPhase::Lobby);
        roundtrip(&PlayerNet { ping_ms: 48, ready: true });
        for action in [
            LobbyAction::Ready(true),
            LobbyAction::Ready(false),
            LobbyAction::SwitchTeam,
            LobbyAction::Start,
            LobbyAction::SetMode(MatchMode::Ffa),
            LobbyAction::SetMode(MatchMode::Tdm),
            LobbyAction::AddBot,
            LobbyAction::RemoveBot,
        ] {
            roundtrip(&action);
        }
    }

    /// Free-for-all: the mode, its rules and limits, and a winning player survive the wire.
    #[test]
    fn free_for_all_match_state_roundtrips() {
        let d = GameData::embedded();
        let ffa = MatchState {
            mode: MatchMode::Ffa,
            map: "showhome".into(),
            score_a: 0,
            score_b: 0,
            score_limit: d.rules.ffa.score_limit,
            time_left_s: d.rules.ffa.time_limit_s,
            phase: MatchPhase::Ended { winner: None, player: Some(0x5eed_0001) },
            lobby_name: "ASH'S GAME".into(),
            max_players: d.rules.ffa.max_players,
            rules: d.rules.rulesets.ffa,
        };
        roundtrip(&ffa);
        assert!(!ffa.has_teams());
        for mode in MatchMode::ALL {
            roundtrip(&mode);
            roundtrip(&MatchState { mode, phase: MatchPhase::Live, ..ffa.clone() });
        }
        roundtrip(&MatchPhase::Ended { winner: Some(Team::B), player: None });
        // A player without a team (free-for-all and the range) roundtrips too.
        roundtrip(&PlayerInfo { name: "LARK".into(), team: None, bot: false });
        // A test bot is marked as one.
        roundtrip(&PlayerInfo { name: "BOT 1".into(), team: Some(Team::B), bot: true });
        // The bytes the wire carries: the mode is its own variant, so a free-for-all never decodes as team
        // deathmatch.
        assert_ne!(roundtrip(&MatchMode::Ffa), roundtrip(&MatchMode::Tdm));
    }

    /// The Loadout screen's output: six ordered magazines with mixed ammo, a mixed-tier custom halo and
    /// the agent survive the wire (postcard, as lightyear sends them).
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
        let bytes = roundtrip(&choice);
        let back: LoadoutChoice = postcard::from_bytes(&bytes).unwrap();
        assert_eq!(back.mags.len(), 6);
        assert_eq!(back.mags[2], AmmoChoice { kind: AmmoKind::Rip, tier: 3 }, "slot order is kept");
        assert_eq!(back.halo.tiers.legs, 2);
        assert_eq!(protocol_id() ^ 0x5641_4c5f_4554_4600, PROTOCOL_VERSION);
    }

    /// Team deathmatch and free-for-all: whatever a client asks for (another core, a halo that is no armor
    /// tier, a mix of ammo, fewer magazines) is shaped to the picks it pays for: an armor tier on the one
    /// halo core, and the mode's count of magazines with slot 1's ammo. The gun range takes the loadout as it
    /// is.
    #[test]
    fn deathmatch_loadouts_become_an_armor_tier_and_one_ammo_type() {
        use vetf_sim::ZoneTable;
        use vetf_sim::data::{AmmoKind, Core};
        let d = GameData::embedded();
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let rich = LoadoutChoice {
            weapon: "sk9_skink".into(),
            mags: vec![ap(3), AmmoChoice::STANDARD, AmmoChoice { kind: AmmoKind::Rip, tier: 1 }, ap(1), ap(2), ap(2)],
            attachments: vec!["optic_reddot".into(), "skink_mag_60".into()],
            halo: HaloChoice { core: Core::Volt, tiers: ZoneTable { head: 3, torso: 1, arms: 0, legs: 2 } },
            agent: "solace".into(),
        };
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            let kit = d.rules.fixed_loadout(mode).unwrap();
            let s = rich.for_mode(&d, mode);
            assert_eq!(s.mags, vec![ap(3); kit.mags as usize], "{mode:?}: slot 1's ammo in all six magazines");
            assert_eq!(s.mags.len(), 6);
            assert_eq!(s.halo, HaloChoice::of_tier(kit, 3), "{mode:?}: head 3 makes T3, on the one core");
            assert_eq!(s.halo.core, Core::Mender);
            assert_eq!((&s.weapon, &s.attachments), (&rich.weapon, &rich.attachments), "the gun stays free");
            assert_eq!(s.for_mode(&d, mode), s, "shaping twice changes nothing");
            roundtrip(&LoadoutUpdate { loadout: s });
        }
        assert_eq!(rich.for_mode(&d, MatchMode::Range), rich);
        let none = LoadoutChoice { mags: vec![], ..rich.clone() };
        assert_eq!(none.ammo(), AmmoChoice::STANDARD);
        assert!(none.for_mode(&d, MatchMode::Tdm).mags.iter().all(|m| *m == AmmoChoice::STANDARD));
    }

    /// The host deals agents: an id, or none in the lobby.
    #[test]
    fn the_dealt_agent_roundtrips() {
        roundtrip(&PlayerAgent(Some("solace".into())));
        roundtrip(&PlayerAgent(None));
        assert_eq!(PlayerAgent::default(), PlayerAgent(None));
        assert_eq!(
            PROTOCOL_VERSION, 9,
            "agent + deathmatch picks 6, no ADS MOVE 7, death screen 8, test bots (bot mark, ADD/REMOVE BOT) 9"
        );
    }

    /// The death screen's recap: lines with hits per zone, the killer's zone, or none of it (a fall).
    #[test]
    fn the_life_recap_roundtrips() {
        use crate::recap::{Hit, LifeLog};
        let mut log = LifeLog::default();
        let h = |shooter, victim, zone, shield, health| Hit {
            shooter,
            victim,
            weapon: "ar7_mako",
            zone,
            shield,
            health,
            range_m: 21.5,
            from: Vec3::new(-4.0, 1.6, 12.25),
        };
        log.took(&h(7, 1, Zone::Head, 30.0, 35.0));
        log.took(&h(8, 1, Zone::Legs, 0.0, 22.0));
        log.dealt(&h(1, 7, Zone::Torso, 42.0, 0.0));
        roundtrip(&log.recap(Some(7), Some(Zone::Head)));
        roundtrip(&log.recap(None, None));
        roundtrip(&LifeLog::default().recap(None, None));
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

    /// Which weapon fields send the predicting client back to the host's state: everything that decides when the
    /// next shot fires (a sprint raise or a waiting trigger pull included) or where it can go (the bloom). A client
    /// whose sprint tap the host missed must not fire the queued shot on its own.
    #[test]
    fn weapon_rollback_covers_every_field_that_decides_a_shot() {
        let d = GameData::embedded();
        let loadout = Loadout::default_for(&d, MatchMode::Range);
        let base = WeaponState::new(&d, &loadout.weapon);
        type Change = fn(&mut WeaponState);
        let differs = |f: Change| {
            let mut other = base.clone();
            f(&mut other);
            weapon_should_rollback(&PlayerWeapon(base.clone()), &PlayerWeapon(other))
        };
        assert!(!differs(|_| {}), "the same state");
        let rollback: [(&str, Change); 10] = [
            ("rounds", |w| w.rounds[0] -= 1),
            ("loaded", |w| w.loaded = 1),
            ("action", |w| w.action = vetf_sim::weapon::WeaponAction::Ready),
            ("fire mode", |w| w.fire_mode = vetf_sim::data::FireMode::Semi),
            ("shot seq", |w| w.shot_seq += 1),
            ("cooldown", |w| w.cooldown += 1),
            ("sprint lock", |w| w.sprint_lock += 1),
            ("queued pull", |w| w.fire_queued = true),
            ("ads", |w| w.ads += 0.1),
            ("bloom", |w| w.bloom_deg += 0.1),
        ];
        for (name, f) in rollback {
            assert!(differs(f), "{name} must roll back");
        }
        // Float noise does not.
        assert!(!differs(|w| w.ads += 0.01), "ads noise");
        assert!(!differs(|w| w.bloom_deg += 0.01), "bloom noise");
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
