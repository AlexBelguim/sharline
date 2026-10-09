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
use vetf_sim::throwable::{Launch, ThrowId, ThrowKind};
use vetf_sim::weapon::WeaponState;

/// Bumped whenever the protocol changes; part of the netcode protocol id, so old builds cannot connect.
pub const PROTOCOL_VERSION: u64 = 16;

/// netcode.io protocol id shared by host and clients.
pub fn protocol_id() -> u64 {
    0x5641_4c5f_4554_4600 ^ PROTOCOL_VERSION
}

/// netcode.io private key. Prototype only: a fixed key means anyone with the build can mint tokens.
pub const PRIVATE_KEY: [u8; 32] = [0; 32];

// ---------------------------------------------------------------------------------------------- tick rate

/// A joining client's netcode id: a random number with the client's tick rate in its low byte. The id is the one
/// thing a client tells the host in the netcode handshake, so the host knows the rate before it seats anyone: a
/// client at another rate gets no player, only [`TickRate`], and reconnects at the host's rate (a 60 and a 120 Hz
/// player never share a match). Never 0 (the host's own id).
pub fn client_id(tick_hz: u32, random: u64) -> u64 {
    (random << 8) | u64::from(tick_hz.clamp(1, 255) as u8)
}

/// The tick rate a joining client runs at, from its netcode id ([`client_id`]).
pub fn client_tick_hz(id: u64) -> u32 {
    (id & 0xFF) as u32
}

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
    /// Kills this player helped with (the host's assist rule, `rules.ron` `assist_min_damage` within
    /// `assist_window_s`).
    pub assists: u16,
    /// Kills in a row this life (`rules.ron` `streaks`; dying resets it, assists do not count). Everyone sees it:
    /// the HUD counter for its owner, the bounty aura on the streaker for the rest.
    pub streak: u16,
}

impl Score {
    /// (kills + assists) / deaths, deaths counted as at least 1.
    pub fn kda(&self) -> f32 {
        (self.kills as f32 + self.assists as f32) / self.deaths.max(1) as f32
    }
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
pub use vetf_sim::data::{MatchSetting, MatchSettings};
pub use vetf_sim::weapon::MagCheckMode;

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
    /// MAG CHECK, a match rule the host picks in the lobby (team deathmatch, free-for-all): the estimate (the
    /// default) or exact rounds, with a HUD counter. Everyone in the match plays with it. The gun range ignores
    /// it: there each player picks their own (Settings > Gameplay).
    pub mag_check: MagCheckMode,
    /// The host's simulation rate (HOST GAME's TICK RATE; every player in the match runs at it).
    pub tick_hz: u16,
    /// How many snapshots a second the host sends (its SNAPSHOT RATE, which it may change in the lobby).
    /// Clients draw other players [`vetf_sim::data::NetSpec::interpolation_delay_s`] behind them.
    pub snapshot_hz: u16,
    /// The host's lobby settings beside the score limit and MAX PLAYERS: the clock, the respawn timer, the
    /// kill refill and the loadout points (the mode's `rules.ron` values until the host changes them).
    pub settings: MatchSettings,
}

impl MatchState {
    /// Players are split into two teams (team deathmatch).
    pub fn has_teams(&self) -> bool {
        self.mode.has_teams()
    }

    /// The loadout points this match allows (none in the gun range): the Loadout screen and the host's check.
    pub fn gear_budget(&self) -> Option<u32> {
        self.mode.is_deathmatch().then_some(self.settings.gear_budget)
    }

    /// A lobby setting's value in its stepper's units (whole minutes, whole seconds).
    pub fn setting(&self, s: MatchSetting) -> u32 {
        match s {
            MatchSetting::ScoreLimit => self.score_limit,
            MatchSetting::TimeLimitMin => (self.settings.time_limit_s / 60.0).round() as u32,
            MatchSetting::MaxPlayers => self.max_players,
            MatchSetting::RespawnS => self.settings.respawn_s.round() as u32,
            MatchSetting::KillRefillMags => self.settings.kill_refill_mags as u32,
            MatchSetting::GearBudget => self.settings.gear_budget,
        }
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
    /// The host's MAG CHECK match setting (team deathmatch and free-for-all).
    SetMagCheck(MagCheckMode),
    /// The host's SNAPSHOT RATE (snapshots a second; one `net.ron` offers at the match's tick rate).
    SetSnapshotHz(u16),
    /// The host's lobby stepper: a setting and its new value in the stepper's units. The host clamps it to
    /// `rules.ron` `lobby_settings` (MAX PLAYERS: to the mode's seats and HOST GAME's slots).
    SetSetting(MatchSetting, u32),
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

/// Host -> a joining client, as it connects: the rate the host simulates at. A client running at another rate
/// (it has no player: see [`client_id`]) reconnects at this one.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub struct TickRate {
    pub hz: u16,
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

/// What killed a player: a player's shot, or something that is no player (the level, a wound). Any cause but
/// [`DeathCause::Shot`] is environmental: those who hurt the victim recently still get their assists, and the
/// kill feed names the cause ("HELPER + FALL > VICTIM").
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq, Default)]
pub enum DeathCause {
    /// A player's shot (the killer's, or a suicide).
    #[default]
    Shot,
    /// Fall damage.
    Fall,
    /// Bled out (the last attacker still gets the kill).
    Bleed,
    /// Fell off the map.
    OutOfBounds,
    /// Fire (molotovs, later): burning is a non-player source like the rest.
    Fire,
}

impl DeathCause {
    /// Not a player's shot: the kill feed names it.
    pub fn is_environmental(self) -> bool {
        self != DeathCause::Shot
    }

    /// The kill feed's word for it (empty for a shot).
    pub fn label(self) -> &'static str {
        match self {
            DeathCause::Shot => "",
            DeathCause::Fall => "FALL",
            DeathCause::Bleed => "BLEED",
            DeathCause::OutOfBounds => "OUT OF BOUNDS",
            DeathCause::Fire => "FIRE",
        }
    }
}

/// Host -> everyone.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct KillFeed {
    /// `None` for suicides and environmental deaths without a killer (falls, the level).
    pub killer: Option<u64>,
    pub victim: u64,
    pub zone: Option<Zone>,
    /// The players credited with an assist on this kill (never the killer), the most damage first.
    pub assists: Vec<u64>,
    /// What killed them.
    pub cause: DeathCause,
}

impl KillFeed {
    /// Did `me` help with this kill (an assist, not the kill itself)? Their ASSIST popup and sound.
    pub fn assisted_by(&self, me: u64) -> bool {
        self.killer != Some(me) && self.victim != me && self.assists.contains(&me)
    }
}

/// Host -> everyone: kill streak news for the kill feed, and for an announced tier the map-wide banner and
/// stinger (`rules.ron` `streaks`). Host and clients run the same data (its fingerprint is checked on join), so
/// a client finds the tier (its banner title, sounds and rewards) from the kill count.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub enum StreakNews {
    /// `player` reached a tier of `kills` in a row ("WREN: 3 STREAK", "WREN is on a 5 STREAK").
    Reached { player: u64, kills: u16 },
    /// `player`'s streak of `kills` ended: killed by `by` (`None`: no player, e.g. a fall, see `cause`).
    Ended { player: u64, by: Option<u64>, kills: u16, cause: DeathCause },
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

/// Host -> everyone (the host's own client too): smoke grenades and molotovs (item 10b). Each client flies the
/// grenades itself from the launch (the same deterministic arc as the host's; the thrower's own is in the air
/// already, predicted) and keeps the areas from the bursts, until they end on their own clocks or the host puts
/// one out.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq)]
pub enum ThrowNews {
    /// A grenade left `id.owner`'s hand.
    Thrown { id: ThrowId, launch: Launch },
    /// It went off: a smoke cloud or a fire grows from the ground point `at`.
    Burst { id: ThrowId, kind: ThrowKind, at: Vec3 },
    /// Smoke put this fire out.
    Doused { id: ThrowId },
    /// Every grenade, cloud and fire is gone (a new match).
    Clear,
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
        app.register_message::<TickRate>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<HitConfirm>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<DamageTaken>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<KillFeed>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<StreakNews>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<ShotFx>().add_direction(NetworkDirection::ServerToClient);
        app.register_message::<ThrowNews>().add_direction(NetworkDirection::ServerToClient);
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
        roundtrip(&KillFeed {
            killer: Some(1),
            victim: 2,
            zone: Some(Zone::Head),
            assists: vec![3, 9],
            cause: DeathCause::Shot,
        });
        roundtrip(&KillFeed { killer: None, victim: 2, zone: None, assists: vec![], cause: DeathCause::OutOfBounds });
        roundtrip(&KillFeed {
            killer: None,
            victim: 2,
            zone: Some(Zone::Legs),
            assists: vec![4],
            cause: DeathCause::Fall,
        });
        roundtrip(&KillFeed { killer: Some(5), victim: 2, zone: None, assists: vec![], cause: DeathCause::Bleed });
        roundtrip(&KillFeed { killer: None, victim: 2, zone: None, assists: vec![6], cause: DeathCause::Fire });
        roundtrip(&Score { kills: 7, deaths: 2, assists: 4, streak: 5 });
        roundtrip(&StreakNews::Reached { player: 3, kills: 5 });
        roundtrip(&StreakNews::Ended { player: 3, by: Some(9), kills: 7, cause: DeathCause::Shot });
        roundtrip(&StreakNews::Ended { player: 3, by: None, kills: 4, cause: DeathCause::Fall });
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
            mag_check: Default::default(),
            tick_hz: 120,
            snapshot_hz: 60,
            settings: d.rules.tdm.settings(),
        });
        roundtrip(&TickRate { hz: 120 });
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
            LobbyAction::SetMagCheck(MagCheckMode::Exact),
            LobbyAction::SetMagCheck(MagCheckMode::Estimate),
            LobbyAction::SetSnapshotHz(120),
        ] {
            roundtrip(&action);
        }
    }

    /// Item C: the host's lobby settings ride on the match state to every player, and each stepper's request
    /// survives the wire; a match the host has not touched carries the mode's `rules.ron` values.
    #[test]
    fn the_lobby_match_settings_roundtrip() {
        let d = GameData::embedded();
        let base = MatchState {
            mode: MatchMode::Ffa,
            map: "showhome".into(),
            score_a: 0,
            score_b: 0,
            score_limit: d.rules.ffa.score_limit,
            time_left_s: d.rules.ffa.time_limit_s,
            phase: MatchPhase::Lobby,
            lobby_name: "ASH'S GAME".into(),
            max_players: 8,
            rules: d.rules.rulesets.ffa,
            mag_check: MagCheckMode::default(),
            tick_hz: 120,
            snapshot_hz: 60,
            settings: d.rules.ffa.settings(),
        };
        assert_eq!(
            (base.settings.time_limit_s, base.settings.respawn_s, base.settings.kill_refill_mags),
            (d.rules.ffa.time_limit_s, d.rules.ffa.respawn_s, d.rules.ffa.kill_refill_mags)
        );
        assert_eq!(base.gear_budget(), Some(d.rules.ffa.gear_budget));
        let edited = MatchState {
            score_limit: 40,
            max_players: 6,
            settings: MatchSettings { time_limit_s: 900.0, respawn_s: 7.0, kill_refill_mags: 2, gear_budget: 12 },
            ..base.clone()
        };
        let bytes = roundtrip(&edited);
        let back: MatchState = postcard::from_bytes(&bytes).unwrap();
        let read = MatchSetting::ALL.map(|s| back.setting(s));
        assert_eq!(read, [40, 15, 6, 7, 2, 12], "score, minutes, players, seconds, magazines, points");
        assert_ne!(bytes, roundtrip(&base));
        assert_eq!(MatchState { mode: MatchMode::Range, ..edited }.gear_budget(), None, "the range has no points");
        for s in MatchSetting::ALL {
            roundtrip(&s);
            roundtrip(&LobbyAction::SetSetting(s, 12));
        }
        assert_ne!(
            roundtrip(&LobbyAction::SetSetting(MatchSetting::ScoreLimit, 5)),
            roundtrip(&LobbyAction::SetSetting(MatchSetting::GearBudget, 5))
        );
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
            mag_check: MagCheckMode::Exact,
            tick_hz: 60,
            snapshot_hz: 30,
            settings: d.rules.ffa.settings(),
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

    /// MAG CHECK is a match rule: it rides on the match state to every player, and the host's change survives the
    /// wire. A match the host has not touched plays with the estimate.
    #[test]
    fn the_mag_check_match_setting_roundtrips() {
        let d = GameData::embedded();
        let base = MatchState {
            mode: MatchMode::Tdm,
            map: "showhome".into(),
            score_a: 0,
            score_b: 0,
            score_limit: 50,
            time_left_s: 600.0,
            phase: MatchPhase::Lobby,
            lobby_name: "ASH'S GAME".into(),
            max_players: 10,
            rules: d.rules.rulesets.tdm,
            mag_check: MagCheckMode::default(),
            tick_hz: 120,
            snapshot_hz: 60,
            settings: d.rules.tdm.settings(),
        };
        assert_eq!(base.mag_check, MagCheckMode::Estimate, "the estimate is the default");
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            for mag_check in MagCheckMode::ALL {
                let m = MatchState { mode, mag_check, ..base.clone() };
                let bytes = roundtrip(&m);
                let back: MatchState = postcard::from_bytes(&bytes).unwrap();
                assert_eq!(back.mag_check, mag_check, "{mode:?}");
                roundtrip(&LobbyAction::SetMagCheck(mag_check));
            }
        }
        assert_ne!(
            roundtrip(&MatchState { mag_check: MagCheckMode::Exact, ..base.clone() }),
            roundtrip(&base),
            "EXACT never decodes as ESTIMATE"
        );
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
            PROTOCOL_VERSION, 16,
            "agent + deathmatch picks 6, no ADS MOVE 7, death screen 8, test bots (bot mark, ADD/REMOVE BOT) 9,              recap per opponent life + kills, assists 10, MAG CHECK match setting 11, kill feed cause 12,              kill streaks (Score::streak, StreakNews) 13, smoke and molotovs (ThrowNews, throw keys, the hand) 14,              tick and snapshot rates as host settings (TickRate, MatchState rates, SetSnapshotHz, rate in the id) 15,              lobby match settings (MatchState::settings, SetSetting) 16"
        );
    }

    /// The death screen's recap: damage taken, encounters per opponent life, kills; or none of it (a fall).
    #[test]
    fn the_life_recap_roundtrips() {
        use crate::recap::{Hit, LifeLog};
        let mut log = LifeLog::default();
        let h = |shooter, victim, victim_life, zone, shield, health| Hit {
            shooter,
            victim,
            victim_life,
            weapon: "ar7_mako",
            zone,
            shield,
            health,
            range_m: 21.5,
            from: Vec3::new(-4.0, 1.6, 12.25),
            at_s: 812.25,
        };
        log.took(&h(7, 1, 0, Zone::Head, 30.0, 35.0));
        log.took(&h(8, 1, 0, Zone::Legs, 0.0, 22.0));
        log.dealt(&h(1, 7, 3, Zone::Torso, 42.0, 0.0));
        log.dealt(&h(1, 7, 4, Zone::Head, 10.0, 60.0));
        log.killed(7, 4, Some(Zone::Head));
        log.killed(9, 1, None);
        log.died(813.0);
        roundtrip(&log.recap(Some(7), Some(Zone::Head)));
        roundtrip(&log.recap(None, None));
        roundtrip(&LifeLog::default().recap(None, None));
    }

    /// The ASSIST popup goes to the helpers only: never the killer, the victim or anyone who did not help.
    #[test]
    fn only_helpers_get_the_assist_popup() {
        let k = KillFeed { killer: Some(1), victim: 2, zone: None, assists: vec![3, 4], cause: DeathCause::Shot };
        assert!(k.assisted_by(3) && k.assisted_by(4));
        assert!(!k.assisted_by(1), "the killer gets the kill, not an assist");
        assert!(!k.assisted_by(2), "nor the victim");
        assert!(!k.assisted_by(5), "nothing for a player who did not help");
        let fall = KillFeed { killer: None, victim: 2, zone: None, assists: vec![3], cause: DeathCause::Fall };
        assert!(fall.assisted_by(3) && !fall.assisted_by(5));
    }

    /// Every cause but a shot is environmental and has a feed word.
    #[test]
    fn environmental_causes_have_a_feed_word() {
        assert!(!DeathCause::Shot.is_environmental() && DeathCause::Shot.label().is_empty());
        for c in [DeathCause::Fall, DeathCause::Bleed, DeathCause::OutOfBounds, DeathCause::Fire] {
            assert!(c.is_environmental() && !c.label().is_empty(), "{c:?}");
        }
    }

    /// KDA: (kills + assists) / deaths, with no deaths counted as one.
    #[test]
    fn kda_counts_assists_and_never_divides_by_zero() {
        assert_eq!(Score { kills: 10, deaths: 4, assists: 2, streak: 0 }.kda(), 3.0);
        assert_eq!(Score { kills: 3, deaths: 0, assists: 1, streak: 0 }.kda(), 4.0, "no deaths: as one");
        assert_eq!(Score::default().kda(), 0.0);
        assert_eq!(Score { kills: 0, deaths: 3, assists: 1, streak: 0 }.kda(), 1.0 / 3.0);
    }

    /// Throwables on the wire: the hand in the predicted items (counts, a wind-up, the throw number), the
    /// loadout's per-life share, and every piece of throw news.
    #[test]
    fn throwables_roundtrip() {
        use vetf_sim::throwable::{ThrowHand, ThrowKit, Windup};
        let d = GameData::embedded();
        let loadout = Loadout::default_for(&d, MatchMode::Tdm);
        assert_eq!(loadout.throws, ThrowKit { smoke: 1, molotov: 1 });
        roundtrip(&PlayerLoadout(loadout.clone()));
        let mut items = ItemState::for_loadout(&loadout);
        items.throw = ThrowHand {
            left: ThrowKit { smoke: 0, molotov: 1 },
            windup: Some(Windup { kind: ThrowKind::Smoke, left: 7 }),
            recover: 3,
            seq: 65535,
            keys: Buttons::THROW_SMOKE,
        };
        roundtrip(&PlayerItems(items));
        let id = ThrowId { owner: 0x5eed_0001, seq: 3 };
        let launch = Launch {
            kind: ThrowKind::Molotov,
            seq: 3,
            origin: Vec3::new(1.0, 1.5, -2.0),
            vel: Vec3::new(0.5, 4.0, -14.0),
        };
        for news in [
            ThrowNews::Thrown { id, launch },
            ThrowNews::Burst { id, kind: ThrowKind::Smoke, at: Vec3::new(3.0, 0.0, -9.5) },
            ThrowNews::Doused { id },
            ThrowNews::Clear,
        ] {
            roundtrip(&news);
        }
        let throw =
            InputFrame { buttons: Buttons(Buttons::THROW_SMOKE | Buttons::THROW_MOLOTOV), ..Default::default() };
        assert_eq!(PlayerInput::from_frame(&throw).frame(), throw, "the throw keys ride in the buttons");
    }

    /// A client's netcode id carries its tick rate, so the host knows it before seating them; the random part
    /// keeps ids apart, and no id is the host's 0.
    #[test]
    fn the_client_id_carries_the_tick_rate() {
        for hz in [60, 120] {
            for random in [0, 1, 0x00ab_cdef_1234_5678, u64::MAX >> 8] {
                let id = client_id(hz, random);
                assert_eq!(client_tick_hz(id), hz);
                assert_ne!(id, 0);
                assert_eq!(id >> 8, random, "the random part survives");
            }
        }
        assert_ne!(client_id(60, 7), client_id(120, 7));
        assert_eq!(client_tick_hz(client_id(1000, 3)), 255, "out-of-range rates are clamped, never wrap");
    }

    /// `net.ron`'s upload estimate counts at least what a moving player's snapshot carries: its movement, look
    /// and weapon on the wire (postcard, as lightyear sends them), plus a few bytes of entity and component ids
    /// each.
    #[test]
    fn the_upload_estimate_covers_a_moving_players_state() {
        let d = GameData::embedded();
        let loadout = Loadout::default_for(&d, MatchMode::Tdm);
        let mut ms = MoveState::spawn(Vec3::new(31.25, 2.5, -48.75), 1.6);
        ms.vel = Vec3::new(4.8, -1.25, 3.5);
        let mut ws = WeaponState::new(&d, &loadout.weapon);
        (ws.cooldown, ws.since_shot, ws.shot_seq, ws.bloom_deg, ws.ads) = (7, 3, 41, 1.25, 0.5);
        let state = [
            roundtrip(&PlayerMove(ms)).len(),
            roundtrip(&PlayerLook { yaw: 2.75, pitch: -0.25 }).len(),
            roundtrip(&PlayerWeapon(ws)).len(),
        ];
        let ids = 4 * state.len();
        let carried = state.iter().sum::<usize>() + ids;
        let u = d.net.upload;
        assert!(u.player_bytes as usize >= carried, "player_bytes {} < {carried} ({state:?})", u.player_bytes);
        assert!((u.player_bytes as usize) < 2 * carried, "and not wildly more: {carried}");
        // 10 players (9 over the network) at 60 snapshots a second: about 5 Mbit/s up, the warning line.
        let up = |hz| d.net.host_upload_mbit(hz, 10, 9);
        assert!((4.0..6.0).contains(&up(60)), "{}", up(60));
        assert!((up(120) / up(60) - 2.0).abs() < 1e-4 && (up(60) / up(30) - 2.0).abs() < 1e-4);
        assert!(d.net.upload_is_high(up(120)) && !d.net.upload_is_high(up(30)));
        assert_eq!(d.net.host_upload_mbit(60, 4, 0), 0.0, "alone with bots: nothing goes out");
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
