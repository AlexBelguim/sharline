//! Host authority: player spawns, the authoritative simulation, shot-claim validation, damage, deaths,
//! respawns and the match rules (team deathmatch and free-for-all). Runs only while hosting.

use crate::config::{Cli, CurrentLevel, Data};
use crate::net::{Role, Session};
use crate::shared::{LocalPlayerEvents, LocalShot, SimSystems};
use bevy::prelude::*;
use lightyear::prelude::input::native::ActionState;
use lightyear::prelude::server::*;
use lightyear::prelude::*;
use std::collections::VecDeque;
use std::sync::Arc;
use std::sync::atomic::{AtomicU32, Ordering};
use vetf_net::*;
use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::combat::{HaloState, Health, resolve_hit};
use vetf_sim::data::{Core, Ruleset};
use vetf_sim::gear::{gear_budget, loadout_cost};
use vetf_sim::hitbox::{FiredShot, Pose, PoseHistory, Verdict, validate_claim};
use vetf_sim::input::view_dir;
use vetf_sim::items::{self, ItemState};
use vetf_sim::level::{Level, SpawnPoint, Team};
use vetf_sim::movement::MoveState;
use vetf_sim::player::{self, Loadout, Wounds};
use vetf_sim::weapon::{MAX_MAGS, WeaponLoadout, WeaponState, shot_direction, shot_seed};

pub struct ServerPlugin;

impl Plugin for ServerPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PendingClaims>()
            .add_message::<PlayerDied>()
            .add_observer(on_new_link)
            .add_observer(on_link_connected)
            .add_observer(on_link_lost)
            .add_systems(
                Update,
                (
                    receive_hellos,
                    receive_loadout_updates,
                    receive_lobby_actions,
                    receive_claims,
                    demo_wounds,
                    demo_kill,
                    measure_ping,
                    count_seats,
                )
                    .run_if(is_hosting),
            )
            .add_systems(FixedUpdate, simulate_authoritative.in_set(SimSystems::Simulate).run_if(is_hosting))
            .add_systems(
                FixedUpdate,
                (resolve_claims, handle_deaths, sync_teams, respawn_players, run_match, deal_agents)
                    .chain()
                    .in_set(SimSystems::Resolve)
                    .run_if(is_hosting),
            );
    }
}

/// Each player's ping, from their link's round-trip time, twice a second (the host's own player has none).
fn measure_ping(
    time: Res<Time>,
    mut next: Local<f32>,
    links: Query<&lightyear::prelude::Link>,
    mut players: Query<(&ServerPlayer, &mut PlayerNet)>,
) {
    if time.elapsed_secs() < *next {
        return;
    }
    *next = time.elapsed_secs() + 0.5;
    for (p, mut net) in &mut players {
        let ms = if p.peer.is_local() { 0 } else { links.get(p.link).map_or(0, |l| l.stats.rtt.as_millis()) };
        net.set_if_neq(PlayerNet { ping_ms: ms.min(u16::MAX as u128) as u16, ..*net });
    }
}

pub fn is_hosting(session: Res<Session>) -> bool {
    session.role == Role::Host
}

/// Host-only bookkeeping on each player entity (never replicated).
#[derive(Component)]
pub struct ServerPlayer {
    pub link: Entity,
    pub peer: PeerId,
    pub history: PoseHistory,
    pub shots: VecDeque<FiredShot>,
    pub choice: Option<LoadoutChoice>,
    /// Who last damaged this player (kill credit for bleeding out).
    pub last_attacker: Option<Entity>,
    /// When this player reached their kill count (a host-wide kill number; lower is earlier): breaks a
    /// free-for-all tie on kills and deaths. Meaningless while they have no kills.
    pub kill_seq: u64,
}

/// What the host set up in HOST GAME: the mode before the match entity exists (the host's own player
/// connects first: `net::handle_requests` inserts this before it), kept in step with the lobby's mode, and
/// the player slots the netcode was opened with (MAX PLAYERS), so a mode change in the lobby never promises
/// more seats than that. Removed when the session ends.
#[derive(Resource, Debug, Clone, Copy, PartialEq)]
pub struct HostedMatch {
    pub mode: MatchMode,
    pub slots: u32,
}

/// Seats left for players joining over the network, shared with the netcode server's connection-request
/// handler ([`SeatCheck`]): the match's MAX PLAYERS (which a lobby mode change can lower) minus the players
/// in it, recounted every frame by [`count_seats`]. A full lobby denies new joiners with "server full".
#[derive(Resource, Debug, Clone, Default)]
pub struct Seats(pub Arc<AtomicU32>);

impl Seats {
    pub fn new(free: u32) -> Self {
        Self(Arc::new(AtomicU32::new(free)))
    }

    pub fn free(&self) -> u32 {
        self.0.load(Ordering::Relaxed)
    }

    /// The handler to give the netcode server.
    pub fn check(&self) -> Arc<SeatCheck> {
        Arc::new(SeatCheck(self.0.clone()))
    }
}

/// Free seats in a match of `max_players` with `players` in it (the host included).
pub fn free_seats(max_players: u32, players: usize) -> u32 {
    max_players.saturating_sub(players as u32)
}

/// The netcode server's gate: a connection request finds the lobby full, or not.
#[derive(Debug)]
pub struct SeatCheck(Arc<AtomicU32>);

impl lightyear::connection::shared::ConnectionRequestHandler for SeatCheck {
    fn handle_request(&self, _client: PeerId) -> Option<lightyear::connection::shared::DeniedReason> {
        (self.0.load(Ordering::Relaxed) == 0).then_some(lightyear::connection::shared::DeniedReason::ServerFull)
    }
}

/// Keep [`Seats`] in step with the match (its seats follow the lobby's mode) and the players in it.
fn count_seats(seats: Option<Res<Seats>>, matches: Query<&MatchState>, players: Query<(), With<ServerPlayer>>) {
    let (Some(seats), Some(m)) = (seats, matches.iter().next()) else { return };
    let free = free_seats(m.max_players, players.iter().count());
    if seats.free() != free {
        seats.0.store(free, Ordering::Relaxed);
    }
}

/// Can a player of team `a` hurt one of team `b`? Players without a team (free-for-all, the gun range)
/// are everyone's enemy.
pub fn hostile(a: Option<Team>, b: Option<Team>) -> bool {
    a.is_none() || b.is_none() || a != b
}

#[derive(Message, Debug, Clone, Copy)]
pub struct PlayerDied {
    pub victim: Entity,
    pub killer: Option<Entity>,
    pub zone: Option<Zone>,
}

struct PendingClaim {
    link: Entity,
    claim: ShotClaim,
    age: u32,
}

#[derive(Resource, Default)]
struct PendingClaims(Vec<PendingClaim>);

/// Claims wait at most this many ticks for the host to simulate the matching shot.
const CLAIM_WAIT_TICKS: u32 = 30;
/// Seconds between the end of a match and the next one.
const INTERMISSION_S: f32 = 8.0;

/// The mode a game on `map` plays: the gun range is always the range, whatever HOST GAME's mode says.
pub fn mode_for_map(map: &str, mode: MatchMode) -> MatchMode {
    if map.eq_ignore_ascii_case("range") { MatchMode::Range } else { mode }
}

/// The match entity. A deathmatch (team or free-for-all) starts in the lobby unless `lobby` is false
/// (`--live`); the range is always live, whatever `mode` asks for. [`HostedMatch`] is the caller's (it must
/// exist before the host's own client connects).
pub fn spawn_match(
    commands: &mut Commands,
    data: &GameData,
    map: &str,
    mode: MatchMode,
    lobby_name: String,
    max_players: u32,
    lobby: bool,
) {
    let mode = mode_for_map(map, mode);
    let rules = data.rules.deathmatch(mode);
    commands.spawn((
        Name::new("Match"),
        MatchState {
            mode,
            map: map.to_lowercase(),
            score_a: 0,
            score_b: 0,
            score_limit: rules.score_limit,
            time_left_s: rules.time_limit_s,
            phase: if lobby && mode.is_deathmatch() { MatchPhase::Lobby } else { MatchPhase::Live },
            lobby_name,
            max_players: mode_max_players(data, mode, max_players),
            rules: data.rules.rulesets.get(mode),
        },
        Replicate::to_clients(NetworkTarget::All),
        // A session that ends must not leave its mode and rules to the next one.
        DespawnOnEnter(crate::AppState::MainMenu),
    ));
}

/// A mode's seats for a game hosted with `slots` players: the mode's limit (`rules.ron`) and the slots,
/// even in team deathmatch (teams of equal size), at least 2.
pub fn mode_max_players(data: &GameData, mode: MatchMode, slots: u32) -> u32 {
    let n = slots.min(data.rules.deathmatch(mode).max_players);
    let n = if mode.has_teams() { n - n % 2 } else { n };
    n.max(2)
}

/// A joiner finds no seat: the match already holds `max_players` (the host's own client always gets one).
pub fn lobby_full(max_players: u32, players: usize, local: bool) -> bool {
    !local && free_seats(max_players, players) == 0
}

/// Every new link (remote clients and the host's own) needs a replication sender.
fn on_new_link(trigger: On<Add, LinkOf>, mut commands: Commands) {
    commands.entity(trigger.entity).insert(ReplicationSender);
}

/// A client left (or timed out): remove their player, or it stays in the match as a ghost replaying its
/// last input.
fn on_link_lost(trigger: On<Remove, Connected>, players: Query<(Entity, &ServerPlayer)>, mut commands: Commands) {
    for (e, p) in &players {
        if p.link == trigger.entity {
            info!("removing player {e} (link {} disconnected)", trigger.entity);
            commands.entity(e).try_despawn();
        }
    }
}

/// A client finished connecting: give them a player.
#[allow(clippy::too_many_arguments)]
fn on_link_connected(
    trigger: On<Add, Connected>,
    links: Query<&RemoteId, With<ClientOf>>,
    players: Query<(&PlayerInfo, &PlayerMove, &Vitals)>,
    matches: Query<&MatchState>,
    hosted: Option<Res<HostedMatch>>,
    session: Res<Session>,
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    mut commands: Commands,
) {
    if session.role != Role::Host {
        return;
    }
    let (Ok(remote), Some(level)) = (links.get(trigger.entity), level) else { return };
    let peer = remote.0;
    // Backstop to the netcode seat check (`Seats`): two joiners racing for the last seat. Never the host.
    if let Some(m) = matches.iter().next()
        && lobby_full(m.max_players, players.iter().count(), peer.is_local())
    {
        warn!("{peer:?} connected to a full lobby ({} seats): no player for them", m.max_players);
        return;
    }
    // The match entity may not exist yet when the host's own client connects: HOST GAME's mode decides.
    let mode = matches
        .iter()
        .next()
        .map(|m| m.mode)
        .or(hosted.map(|h| h.mode))
        .unwrap_or(if level.name.eq_ignore_ascii_case("range") { MatchMode::Range } else { MatchMode::Tdm });
    let team = mode.has_teams().then(|| {
        let a = players.iter().filter(|(i, _, _)| i.team == Some(Team::A)).count();
        let b = players.iter().filter(|(i, _, _)| i.team == Some(Team::B)).count();
        if a <= b { Team::A } else { Team::B }
    });
    let enemies: Vec<Vec3> = players
        .iter()
        .filter(|(i, _, _)| hostile(team, i.team))
        .filter(|(_, _, v)| !v.health.dead)
        .map(|(_, m, _)| m.0.pos)
        .collect();
    let id = peer.to_bits();
    let spawn = spawn_for(&data, &level, mode, team, &enemies, spawn_roll(id, players.iter().count() as u64, 0));
    let loadout = default_loadout(&data, mode);
    let player = commands
        .spawn((
            Name::new(format!("Player {id:x}")),
            PlayerId(id),
            PlayerInfo { name: if peer.is_local() { session.local_name.clone() } else { "AGENT".into() }, team },
            PlayerMove(MoveState::spawn(spawn.pos, loadout_fuel(&data, &loadout))),
            PlayerLook { yaw: spawn.yaw, pitch: 0.0 },
            PlayerWeapon(WeaponState::new(&data, &loadout.weapon)),
            PlayerItems(ItemState::new(&loadout.kit)),
            fresh_vitals(&data, &loadout, mode),
            PlayerLoadout(loadout),
            Score::default(),
            PlayerNet::default(),
            // Dealt when the match starts (`deal_agents`); none in the lobby and the range.
            PlayerAgent::default(),
            ServerPlayer {
                link: trigger.entity,
                peer,
                history: PoseHistory::default(),
                shots: VecDeque::new(),
                choice: None,
                last_attacker: None,
                kill_seq: 0,
            },
        ))
        .insert((
            Replicate::to_clients(NetworkTarget::All),
            PredictionTarget::to_clients(NetworkTarget::Single(peer)),
            InterpolationTarget::to_clients(NetworkTarget::AllExceptSingle(peer)),
            ControlledBy { owner: trigger.entity, lifetime: Default::default() },
            // Visual children added on the host must not be replicated.
            DisableReplicateHierarchy,
        ))
        .id();
    info!("spawned player {player} for {peer:?} on team {team:?}");
}

/// `rules.ron`'s default loadout as a choice (the command line without overrides asks for the same).
pub fn default_choice(data: &GameData) -> LoadoutChoice {
    let d = &data.rules.default_loadout;
    LoadoutChoice {
        weapon: d.primary.clone(),
        mags: d.mags.clone(),
        attachments: d.attachments.clone(),
        halo: crate::config::halo_from_armor(&d.armor, data),
        agent: crate::config::DEFAULT_AGENT.into(),
    }
}

/// What a player wears before their hello: the default loadout, shaped to the mode (its one halo).
fn default_loadout(data: &GameData, mode: MatchMode) -> Loadout {
    loadout_from_choice(data, &default_choice(data), mode).unwrap_or_else(|e| {
        warn!("the default loadout does not fit {mode:?} ({e:?})");
        Loadout::default_for(data, mode)
    })
}

fn loadout_fuel(data: &GameData, l: &Loadout) -> f32 {
    data.movement.jetpack.fuel_s * data.armor.effects(l.weight).fuel
}

fn fresh_vitals(data: &GameData, l: &Loadout, mode: MatchMode) -> Vitals {
    Vitals {
        health: Health::new(data.armor.zone_hp),
        halo: HaloState::full(&l.halo),
        wounds: Wounds::default(),
        respawn_s: 0.0,
        protected_s: data.rules.deathmatch(mode).spawn_protection_s,
    }
}

/// A spawn pick's random number in [0, 1), from the player, their deaths and the tick (deterministic, so a
/// test run is repeatable).
fn spawn_roll(player: u64, deaths: u64, tick: u64) -> f32 {
    vetf_sim::rng::SplitMix::from_parts(&[player, deaths, tick, 0x0053_5041_574e]).next_f32()
}

/// Where a player (re)spawns: free-for-all picks from every spawn (see [`pick_ffa_spawn`]); otherwise the
/// team's spawn farthest from living enemies.
fn spawn_for(
    data: &GameData,
    level: &Level,
    mode: MatchMode,
    team: Option<Team>,
    enemies: &[Vec3],
    roll: f32,
) -> SpawnPoint {
    match mode {
        MatchMode::Ffa => pick_ffa_spawn(level, enemies, data.rules.ffa.spawn_slack_m, roll),
        MatchMode::Tdm | MatchMode::Range => pick_spawn(level, team, enemies),
    }
}

/// Free-for-all: any spawn of either side. The ones within `slack_m` of the farthest from every living
/// enemy are candidates, and `roll` (in [0, 1)) picks one, so players do not always appear at the same
/// point. With no living enemies every spawn is a candidate.
pub fn pick_ffa_spawn(level: &Level, enemies: &[Vec3], slack_m: f32, roll: f32) -> SpawnPoint {
    let nearest = |s: &SpawnPoint| enemies.iter().map(|e| e.distance(s.pos)).fold(f32::INFINITY, f32::min);
    let best = level.spawns.iter().map(nearest).fold(f32::NEG_INFINITY, f32::max);
    let candidates: Vec<&SpawnPoint> =
        level.spawns.iter().filter(|s| enemies.is_empty() || nearest(s) >= best - slack_m.max(0.0)).collect();
    if candidates.is_empty() {
        return SpawnPoint { pos: Vec3::new(0.0, 0.5, 0.0), yaw: 0.0, team: None };
    }
    let i = ((roll.clamp(0.0, 1.0) * candidates.len() as f32) as usize).min(candidates.len() - 1);
    *candidates[i]
}

/// The spawn (of our team) farthest from any living enemy.
fn pick_spawn(level: &Level, team: Option<Team>, enemies: &[Vec3]) -> SpawnPoint {
    let mut best = None;
    let mut best_d = f32::MIN;
    for s in level.spawns_for(team) {
        let d = enemies.iter().map(|e| e.distance(s.pos)).fold(f32::MAX, f32::min);
        let d = if d == f32::MAX { 0.0 } else { d };
        if best.is_none() || d > best_d {
            best = Some(*s);
            best_d = d;
        }
    }
    best.unwrap_or(SpawnPoint { pos: Vec3::new(0.0, 0.5, 0.0), yaw: 0.0, team })
}

/// Why the host refused a requested loadout.
#[derive(Debug, Clone, PartialEq)]
pub enum LoadoutError {
    UnknownWeapon,
    /// An attachment that does not exist or does not fit the gun, or two in one category.
    Attachment,
    /// A halo arc above its loadout tier cap (more armor than any loadout may wear).
    TierCap,
    /// A magazine's ammo cannot be loaded by that gun, or it is NPC-only.
    Ammo,
    /// No magazines, or more than six.
    MagCount,
    /// The picks cost more points than the mode's budget.
    OverBudget {
        cost: u32,
        budget: u32,
    },
}

/// Build a loadout from a client's choice (the Loadout screen checks the same rules before CONFIRM).
///
/// First what no loadout may ask for: an unknown gun, no magazine or more than six, a halo arc above its
/// loadout cap. Then team deathmatch and free-for-all shape the choice to the picks they sell
/// ([`LoadoutChoice::for_mode`]): the armor tier the halo makes, on the one halo core, and six magazines of
/// slot 1's ammo (a loadout saved by an older build opens as its nearest picks). Then: players' ammo only,
/// attachments that fit the gun (one per category), and the points (armor tier + ammo type once + magazine
/// type, `vetf_sim::gear::loadout_cost`) within the mode's budget; the gun range has none. The healing kit
/// comes from the mode, not the client.
pub fn loadout_from_choice(data: &GameData, choice: &LoadoutChoice, mode: MatchMode) -> Result<Loadout, LoadoutError> {
    let spec = data.weapon(&choice.weapon).ok_or(LoadoutError::UnknownWeapon)?;
    if choice.mags.is_empty() || choice.mags.len() > MAX_MAGS {
        return Err(LoadoutError::MagCount);
    }
    if !choice.halo.within_caps(data.armor.loadout_tier_caps) {
        return Err(LoadoutError::TierCap);
    }
    let choice = &choice.for_mode(data, mode);
    for m in &choice.mags {
        data.ammo_for(spec, *m).filter(|a| a.player_loadout).ok_or(LoadoutError::Ammo)?;
    }
    let mut cats = Vec::new();
    for id in &choice.attachments {
        let a = data.attachment(id).filter(|a| a.fits.contains(&choice.weapon)).ok_or(LoadoutError::Attachment)?;
        if cats.contains(&a.cat) {
            return Err(LoadoutError::Attachment);
        }
        cats.push(a.cat);
    }
    let weapon = WeaponLoadout::resolve(data, &choice.weapon, &choice.mags, &choice.attachments)
        .ok_or(LoadoutError::UnknownWeapon)?;
    let cost = loadout_cost(data, mode, spec, &choice.halo, &choice.mags, &choice.attachments).total();
    if let Some(budget) = gear_budget(data, mode)
        && cost > budget
    {
        return Err(LoadoutError::OverBudget { cost, budget });
    }
    let armor = data.armor.resolve_halo(&choice.halo);
    Ok(Loadout::new(weapon, &armor, data.items.kit(mode)))
}

/// The running match's rules (full rules before the match entity exists).
fn match_rules(matches: &Query<&MatchState>) -> Ruleset {
    matches.iter().next().map_or(Ruleset::FULL, |m| m.rules)
}

/// The running match's mode.
fn match_mode(matches: &Query<&MatchState>) -> MatchMode {
    matches.iter().next().map_or(MatchMode::Tdm, |m| m.mode)
}

/// Deterministic shield-bypass roll for one hit (shooter, shot number, victim).
fn bypass_roll(shooter: u64, seq: u32, victim: u64) -> f32 {
    vetf_sim::rng::SplitMix::from_parts(&[shooter, seq as u64, victim, 0x4259_5041_5353]).next_f32()
}

/// What a player's gear is made of on the host, to equip a new loadout at once.
type Gear<'a> =
    (Mut<'a, PlayerLoadout>, Mut<'a, PlayerWeapon>, Mut<'a, PlayerItems>, Mut<'a, Vitals>, Mut<'a, PlayerMove>);

/// Put a loadout on a living player now: a fresh gun, kit, halo and fuel (a hello, or a change in the lobby).
fn equip(data: &GameData, l: Loadout, mode: MatchMode, gear: Gear) {
    let (mut lo, mut w, mut it, mut v, mut mv) = gear;
    *w = PlayerWeapon(WeaponState::new(data, &l.weapon));
    *it = PlayerItems(ItemState::new(&l.kit));
    *v = fresh_vitals(data, &l, mode);
    mv.0.fuel = loadout_fuel(data, &l);
    *lo = PlayerLoadout(l);
}

/// A loadout in a few words for the log: `sk9_skink skink_mag_60 · T3 MENDER (H3 T3 A1 L1) · AP II x6`, or
/// `... · H2 T3 A1 L0 MENDER · ...` for a halo that is no deathmatch armor tier (the gun range).
fn loadout_words(data: &GameData, l: &Loadout) -> String {
    let t = l.halo.tiers;
    let core = l.halo.core.map_or("NO HALO", |c| c.label());
    let arcs = format!("H{} T{} A{} L{}", t.head, t.torso, t.arms, t.legs);
    let halo = match data.rules.deathmatch_loadout.tier_of(t) {
        Some(tier) => format!("T{tier} {core} ({arcs})"),
        None => format!("{arcs} {core}"),
    };
    let ammo: Vec<String> =
        l.weapon.mags.iter().map(|m| data.ammo.long_name(m.choice).unwrap_or_else(|| "?".into())).collect();
    let ammo = match ammo.first() {
        Some(first) if ammo.iter().all(|a| a == first) => format!("{first} x{}", ammo.len()),
        _ => ammo.join(", "),
    };
    let spec = l.weapon.spec(data);
    let mag = vetf_sim::gear::mag_type(data, spec, &l.weapon.attachments);
    format!("{} {mag} · {halo} · {ammo}", spec.id)
}

fn receive_hellos(
    mut links: Query<(Entity, &mut MessageReceiver<Hello>), With<ClientOf>>,
    mut players: Query<(
        &mut PlayerInfo,
        &mut ServerPlayer,
        &mut PlayerLoadout,
        &mut PlayerWeapon,
        &mut PlayerItems,
        &mut Vitals,
        &mut PlayerMove,
    )>,
    matches: Query<&MatchState>,
    data: Res<Data>,
) {
    let mode = match_mode(&matches);
    for (link, mut rx) in &mut links {
        for hello in rx.receive() {
            if hello.data_fingerprint != data.fingerprint {
                warn!("{} runs different gameplay data: prediction will drift", hello.name);
            }
            for (mut info, mut sp, lo, w, it, v, mv) in &mut players {
                if sp.link != link {
                    continue;
                }
                info.name = hello.name.chars().filter(|c| !c.is_control()).take(16).collect();
                match loadout_from_choice(&data, &hello.loadout, mode) {
                    Ok(l) => {
                        info!("{}: loadout {}", info.name, loadout_words(&data, &l));
                        equip(&data, l, mode, (lo, w, it, v, mv));
                        // Kept for every respawn (a LoadoutUpdate replaces it).
                        sp.choice = Some(hello.loadout.clone());
                    }
                    Err(e) => {
                        warn!("{}: loadout {:?} refused ({e:?}); keeping the default", hello.name, hello.loadout)
                    }
                }
            }
        }
    }
}

/// A player changed their loadout on the Loadout screen: check it now and apply it at their next spawn (a
/// live match keeps this life's gear). In the lobby, where nobody fights yet, it is put on at once, so the
/// lobby's rows show the new halo.
#[allow(clippy::type_complexity)]
fn receive_loadout_updates(
    mut links: Query<(Entity, &mut MessageReceiver<LoadoutUpdate>), With<ClientOf>>,
    mut players: Query<(
        &PlayerInfo,
        &mut ServerPlayer,
        &mut PlayerLoadout,
        &mut PlayerWeapon,
        &mut PlayerItems,
        &mut Vitals,
        &mut PlayerMove,
    )>,
    matches: Query<&MatchState>,
    data: Res<Data>,
) {
    let mode = match_mode(&matches);
    let lobby = matches.iter().next().is_some_and(|m| m.phase == MatchPhase::Lobby);
    for (link, mut rx) in &mut links {
        for update in rx.receive() {
            for (info, mut sp, lo, w, it, v, mv) in &mut players {
                if sp.link != link {
                    continue;
                }
                match loadout_from_choice(&data, &update.loadout, mode) {
                    Ok(l) => {
                        sp.choice = Some(update.loadout.clone());
                        if lobby && !v.health.dead {
                            info!("{}: new loadout {}, on now (lobby)", info.name, loadout_words(&data, &l));
                            equip(&data, l, mode, (lo, w, it, v, mv));
                        } else {
                            info!("{}: new loadout {} for the next spawn", info.name, loadout_words(&data, &l));
                        }
                    }
                    Err(e) => warn!("{}: loadout update {:?} refused ({e:?})", info.name, update.loadout),
                }
            }
        }
    }
}

/// Lobby actions (see [`LobbyAction`]); anything outside the lobby is ignored.
fn receive_lobby_actions(
    mut links: Query<(Entity, &mut MessageReceiver<LobbyAction>), With<ClientOf>>,
    mut players: Query<(&mut PlayerInfo, &mut PlayerNet, &mut Vitals, &mut Score, &ServerPlayer)>,
    mut matches: Query<&mut MatchState>,
    mut hosted: Option<ResMut<HostedMatch>>,
    data: Res<Data>,
) {
    let Some(mut m) = matches.iter_mut().next() else { return };
    for (link, mut rx) in &mut links {
        let actions: Vec<LobbyAction> = rx.receive().collect();
        for action in actions {
            if m.phase != MatchPhase::Lobby {
                continue;
            }
            let Some(team) = players.iter().find(|p| p.4.link == link).map(|p| p.0.team) else { continue };
            let from_host = players.iter().any(|p| p.4.link == link && p.4.peer.is_local());
            let free = |to: Team, players: &Query<(&mut PlayerInfo, &mut PlayerNet, &mut Vitals, &mut Score, &ServerPlayer)>| {
                (players.iter().filter(|p| p.0.team == Some(to)).count() as u32) < (m.max_players / 2).max(1)
            };
            match action {
                LobbyAction::Ready(ready) => {
                    for (_, mut net, .., p) in &mut players {
                        if p.link == link {
                            net.ready = ready;
                        }
                    }
                }
                LobbyAction::SetMode(mode) => {
                    let slots = hosted.as_ref().map_or(m.max_players, |h| h.slots);
                    let Some(max) = lobby_mode_change(&data, &m, mode, slots, players.iter().count() as u32, from_host)
                    else {
                        continue;
                    };
                    info!("the host switches the lobby to {mode:?} ({max} players)");
                    let rules = data.rules.deathmatch(mode);
                    if let Some(h) = hosted.as_mut() {
                        h.mode = mode;
                    }
                    m.mode = mode;
                    m.max_players = max;
                    m.score_limit = rules.score_limit;
                    m.rules = data.rules.rulesets.get(mode);
                    // Teams follow on the next tick (`sync_teams`); everyone respawns for the new mode.
                    reset_match(&mut m, &data, None, players.iter_mut().map(|(_, n, v, s, _)| (n, v, s)));
                }
                LobbyAction::SwitchTeam => {
                    if !m.has_teams() {
                        continue;
                    }
                    let Some(to) = team.map(Team::other).filter(|t| free(*t, &players)) else { continue };
                    for (mut info, mut net, mut v, _, p) in &mut players {
                        if p.link == link {
                            info!("{} switches to team {to:?}", info.name);
                            info.team = Some(to);
                            net.ready = false;
                            // Respawn on the new side.
                            v.health.dead = true;
                            v.respawn_s = 0.0;
                        }
                    }
                }
                LobbyAction::Start => {
                    if from_host {
                        info!("the host starts the match");
                        reset_match(
                            &mut m,
                            &data,
                            Some(MatchPhase::Live),
                            players.iter_mut().map(|(_, n, v, s, _)| (n, v, s)),
                        );
                    }
                }
            }
        }
    }
}

/// The lobby's seats after the host asks to change its mode to `mode`, or `None` when the change is refused:
/// only the host, only in the lobby, only between the deathmatch modes (the range stays the range), and
/// never to fewer seats than players already in the lobby. `slots` is what HOST GAME opened.
fn lobby_mode_change(
    data: &GameData,
    m: &MatchState,
    mode: MatchMode,
    slots: u32,
    players: u32,
    from_host: bool,
) -> Option<u32> {
    if !from_host || m.phase != MatchPhase::Lobby || !m.mode.is_deathmatch() || !mode.is_deathmatch() {
        return None;
    }
    if m.mode == mode {
        return None;
    }
    let max = mode_max_players(data, mode, slots);
    if players > max {
        warn!("{mode:?} seats {max}, but {players} players are in the lobby: mode not changed");
        return None;
    }
    Some(max)
}

/// Teams follow the mode: none in free-for-all and the range; in team deathmatch a player without one
/// (after a switch from free-for-all, or one who joined before the match existed) joins the smaller team.
fn sync_teams(matches: Query<&MatchState>, mut players: Query<(&PlayerId, &mut PlayerInfo)>) {
    let Some(m) = matches.iter().next() else { return };
    if !m.has_teams() {
        for (_, mut info) in &mut players {
            if info.team.is_some() {
                info.team = None;
            }
        }
        return;
    }
    let count = |t: Team, players: &Query<(&PlayerId, &mut PlayerInfo)>| {
        players.iter().filter(|(_, i)| i.team == Some(t)).count()
    };
    let (mut a, mut b) = (count(Team::A, &players), count(Team::B, &players));
    let mut free: Vec<u64> = players.iter().filter(|(_, i)| i.team.is_none()).map(|(id, _)| id.0).collect();
    // By id (the host is 0), so the host lands on team A.
    free.sort_unstable();
    for id in free {
        let team = if a <= b { Team::A } else { Team::B };
        if team == Team::A {
            a += 1;
        } else {
            b += 1;
        }
        if let Some((_, mut info)) = players.iter_mut().find(|(p, _)| p.0 == id) {
            info!("{} joins team {team:?}", info.name);
            info.team = Some(team);
        }
    }
}

/// A fresh match (in `phase`, if given): scores, the mode's clock, everyone's score and READY, and
/// everyone respawns on the next tick. Also the host's RESTART MATCH / BACK TO LOBBY (`esc_menu.rs`).
pub(crate) fn reset_match<'a>(
    m: &mut MatchState,
    data: &GameData,
    phase: Option<MatchPhase>,
    players: impl Iterator<Item = (Mut<'a, PlayerNet>, Mut<'a, Vitals>, Mut<'a, Score>)>,
) {
    m.score_a = 0;
    m.score_b = 0;
    if m.mode.is_deathmatch() {
        m.time_left_s = data.rules.deathmatch(m.mode).time_limit_s;
    }
    if let Some(phase) = phase {
        m.phase = phase;
    }
    for (mut net, mut v, mut s) in players {
        *s = Score::default();
        net.ready = false;
        v.health.dead = true;
        v.respawn_s = 0.0;
    }
}

/// `--demo-ui heal*|hud`: hurt the host's own player once, so the HUD and the heal ring have something
/// to show in screenshots.
fn demo_wounds(
    cli: Res<Cli>,
    data: Res<Data>,
    mut done: Local<bool>,
    mut me: Query<(&mut Vitals, &ServerPlayer), With<Controlled>>,
) {
    if *done || !cli.demo_ui.as_deref().is_some_and(|d| d.starts_with("heal") || d == "hud") {
        return;
    }
    // After the hello (which resets vitals for the chosen loadout).
    for (mut v, _) in me.iter_mut().filter(|(_, sp)| sp.choice.is_some()) {
        *done = true;
        let spill = &data.weapons.spill_to_torso;
        v.health.apply(Zone::Legs, 60.0, spill);
        v.health.apply(Zone::Head, 12.0, spill);
        v.halo.shield.torso = 0.0;
        v.halo.regen_wait_s = 600.0;
        if let Some(bleed) = data
            .ammo
            .resolve(
                vetf_sim::data::WeaponClass::AssaultRifle,
                vetf_sim::data::AmmoChoice { kind: vetf_sim::data::AmmoKind::Shrapnel, tier: 1 },
            )
            .and_then(|a| a.bleed)
        {
            v.health.bleeding.add_stack(Zone::Arms, &bleed);
        }
    }
}

/// `--demo-ui kill` on the host: two seconds after the first joined player is in, the host's player kills them
/// with a head shot, so a host + `--bot` run shows the kill feed on both ends.
fn demo_kill(
    cli: Res<Cli>,
    time: Res<Time>,
    mut since: Local<Option<f32>>,
    mut done: Local<bool>,
    players: Query<(Entity, &ServerPlayer, Has<Controlled>)>,
    mut deaths: MessageWriter<PlayerDied>,
) {
    if *done || cli.demo_ui.as_deref() != Some("kill") {
        return;
    }
    let host = players.iter().find(|(.., own)| *own).map(|(e, ..)| e);
    let joined = players.iter().find(|(_, sp, own)| !*own && sp.choice.is_some()).map(|(e, ..)| e);
    let (Some(host), Some(joined)) = (host, joined) else { return };
    let t = time.elapsed_secs();
    if t - *since.get_or_insert(t) >= 2.0 {
        *done = true;
        deaths.write(PlayerDied { victim: joined, killer: Some(host), zone: Some(Zone::Head) });
    }
}

fn receive_claims(
    mut links: Query<(Entity, &mut MessageReceiver<ShotClaim>), With<ClientOf>>,
    mut pending: ResMut<PendingClaims>,
) {
    for (link, mut rx) in &mut links {
        for claim in rx.receive() {
            pending.0.push(PendingClaim { link, claim, age: 0 });
        }
    }
}

#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn simulate_authoritative(
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    timeline: Res<LocalTimeline>,
    mut players: Query<
        (
            Entity,
            &PlayerId,
            Option<&ActionState<PlayerInput>>,
            &mut PlayerMove,
            &mut PlayerWeapon,
            &mut PlayerItems,
            &PlayerLoadout,
            &mut Vitals,
            &mut PlayerLook,
            &mut ServerPlayer,
            Has<Controlled>,
        ),
        With<Replicate>,
    >,
    server: Query<&Server>,
    matches: Query<&MatchState>,
    mut fx: ServerMultiMessageSender,
    mut local_shots: MessageWriter<LocalShot>,
    mut local_events: MessageWriter<LocalPlayerEvents>,
    mut deaths: MessageWriter<PlayerDied>,
    mut feedback: ResMut<crate::client::Feedback>,
) {
    let Some(level) = level else { return };
    let rules = match_rules(&matches);
    let tick = timeline.tick().0;
    let dt = data.tick_dt();
    let keep = (data.combat.shot_validation.history_s * data.net.tick_hz as f32).ceil() as u32;
    let server = server.iter().next();
    for (entity, id, input, mut mv, mut weapon, mut items, loadout, mut vitals, mut look, mut sp, local) in &mut players
    {
        if vitals.health.dead {
            continue;
        }
        let frame = input.map(|a| a.0.frame().sanitized()).unwrap_or_default();
        look.yaw = frame.yaw;
        look.pitch = frame.pitch;
        let mut wounds = vitals.wounds;
        let ev = player::step(&data, &level, &loadout.0, &mut mv.0, &mut weapon.0, &mut items.0, &mut wounds, &frame);
        vitals.wounds = wounds;
        if local {
            let trigger = crate::sound::TriggerTick::of(&weapon.0);
            local_events.write(LocalPlayerEvents { player: id.0, events: ev, trigger });
        }
        if let Some((slot, zone)) = ev.items.finished
            && let Some(k) = loadout.0.kit.get(slot as usize)
        {
            let Vitals { health, halo, wounds, .. } = &mut *vitals;
            items::apply(data.items.spec(k), zone, health, halo, &loadout.0.halo);
            wounds.sync(health, &rules);
        }
        vitals.protected_s = (vitals.protected_s - dt).max(0.0);
        let spec = loadout.0.halo;
        vitals.halo.tick(&spec, dt);
        if vitals.health.bleeding.is_bleeding() {
            let out = vitals.health.tick_bleeding(&data.weapons.spill_to_torso, dt);
            let Vitals { health, wounds, .. } = &mut *vitals;
            wounds.sync(health, &rules);
            if out.died {
                deaths.write(PlayerDied { victim: entity, killer: sp.last_attacker, zone: None });
            }
        }

        if ev.movement.fall_damage > 0.0 {
            let hp = vitals.health.apply(Zone::Legs, ev.movement.fall_damage, &data.weapons.spill_to_torso);
            let Vitals { health, wounds, .. } = &mut *vitals;
            wounds.sync(health, &rules);
            if hp.died {
                deaths.write(PlayerDied { victim: entity, killer: None, zone: Some(Zone::Legs) });
            }
        }
        if mv.0.pos.y < level.kill_y {
            vitals.health.dead = true;
            deaths.write(PlayerDied { victim: entity, killer: None, zone: None });
        }

        sp.history.push(tick, Pose { pos: mv.0.pos, yaw: look.yaw, stance: mv.0.stance }, keep);

        if let Some(shot) = ev.weapon.shot {
            debug!("{:x} fired shot {} at tick {tick}", id.0, shot.seq);
            vitals.protected_s = 0.0;
            let origin = mv.0.eye_pos();
            sp.shots.push_back(FiredShot {
                seq: shot.seq,
                tick,
                origin,
                aim: view_dir(frame.yaw, frame.pitch),
                spread_deg: shot.spread_deg,
                ammo_slot: shot.ammo_slot,
            });
            while sp.shots.len() > 64 {
                sp.shots.pop_front();
            }
            let dir = shot_direction(frame.yaw, frame.pitch, shot.spread_deg, shot_seed(id.0, shot.seq));
            let range = loadout.0.weapon.spec(&data).max_range_m;
            let hit = level.world.raycast(origin, dir, range);
            let end = origin + dir * hit.map_or(range, |(d, _)| d);
            // Our own client never receives the shot fx sent to the clients, so the host draws other players'
            // tracers and bullet holes here (its own shots go through `LocalShot` like everyone's).
            if !local {
                feedback.tracers.push((origin, end, 0.0, false));
                if let Some((_, normal)) = hit {
                    feedback.impacts.push((end, normal));
                }
            }
            if let Some(server) = server {
                let msg = ShotFx { shooter: id.0, origin, end };
                if let Err(e) = fx.send::<_, FxChannel>(&msg, server, &joined_except(sp.peer)) {
                    warn!("shot fx not sent: {e:?}");
                }
            }
            if local {
                local_shots.write(LocalShot { shot, player: id.0, origin, yaw: frame.yaw, pitch: frame.pitch });
            }
        }
    }
}

/// Snapshot of what a claim needs from the shooter.
struct Shooter {
    entity: Entity,
    id: u64,
    team: Option<Team>,
    shot: FiredShot,
    loadout: Loadout,
}

#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn resolve_claims(
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    timeline: Res<LocalTimeline>,
    mut pending: ResMut<PendingClaims>,
    mut players: Query<(Entity, &PlayerId, &PlayerInfo, &PlayerLoadout, &mut Vitals, &PlayerMove, &mut ServerPlayer)>,
    mut confirms: Query<&mut MessageSender<HitConfirm>>,
    mut damage: Query<&mut MessageSender<DamageTaken>>,
    matches: Query<&MatchState>,
    mut deaths: MessageWriter<PlayerDied>,
) {
    let Some(level) = level else { return };
    // No damage in the lobby (bots, a held trigger) nor in the intermission after a match (the winner is
    // decided): claims are dropped.
    if matches.iter().next().is_some_and(|m| !takes_damage(m.phase)) {
        pending.0.clear();
        return;
    }
    let rules = match_rules(&matches);
    let tick = timeline.tick().0;
    let mut keep = Vec::new();
    for mut p in std::mem::take(&mut pending.0) {
        p.age += 1;
        let shooter = players.iter().find(|(.., sp)| sp.link == p.link).and_then(|(e, id, info, lo, v, _, sp)| {
            let shot = sp.shots.iter().find(|s| s.seq == p.claim.seq)?;
            (!v.health.dead || shot.tick + 2 >= tick).then(|| Shooter {
                entity: e,
                id: id.0,
                team: info.team,
                shot: *shot,
                loadout: lo.0.clone(),
            })
        });
        let Some(shooter) = shooter else {
            if p.age == CLAIM_WAIT_TICKS {
                debug!("claim {} expired: no matching shot", p.claim.seq);
            }
            if p.age < CLAIM_WAIT_TICKS {
                keep.push(p);
            }
            continue;
        };
        let Some((victim_e, ..)) = players.iter().find(|(_, id, ..)| id.0 == p.claim.victim) else { continue };
        let Ok((_, _, vinfo, vloadout, mut vitals, vmove, mut vsp)) = players.get_mut(victim_e) else { continue };
        if victim_e == shooter.entity
            || vitals.health.dead
            || vitals.protected_s > 0.0
            || !hostile(shooter.team, vinfo.team)
        {
            continue;
        }
        let weapon = shooter.loadout.weapon.spec(&data);
        let verdict =
            validate_claim(&data, &level.world, &shooter.shot, &p.claim.hit, &vsp.history, tick, weapon.max_range_m);
        let (zone, range) = match verdict {
            Verdict::Hit { zone, range_m } => (zone, range_m),
            Verdict::Rejected(why) => {
                debug!("claim {} from {:x} rejected: {why:?}", p.claim.seq, shooter.id);
                continue;
            }
        };
        info!("hit: {:x} -> {:x} {zone:?} at {range:.1} m", shooter.id, p.claim.victim);
        let halo_spec = vloadout.0.halo;
        let (mut halo, mut health) = (vitals.halo, vitals.health);
        let report = resolve_hit(
            weapon,
            shooter.loadout.weapon.ammo(shooter.shot.ammo_slot),
            range,
            zone,
            &data.weapons.spill_to_torso,
            &halo_spec,
            &mut halo,
            &mut health,
            bypass_roll(shooter.id, p.claim.seq, p.claim.victim),
        );
        vsp.last_attacker = Some(shooter.entity);
        vitals.wounds.sync(&mut health, &rules);
        vitals.halo = halo;
        vitals.health = health;
        if report.to_hp > 0.0 && halo_spec.core != Some(Core::Phase) {
            vitals.wounds.tag_slow_s = data.combat.wounded.tag_slow_s;
        }
        let victim_pos = vmove.0.pos;
        let victim_link = vsp.link;
        let kind = if report.killed {
            HitKind::Kill
        } else if report.absorbed > 0.0 && report.to_hp <= 0.0 {
            HitKind::Shield
        } else {
            HitKind::Health
        };
        if let Ok(mut s) = confirms.get_mut(p.link) {
            s.send::<ReliableChannel>(HitConfirm {
                victim: p.claim.victim,
                zone,
                kind,
                shield_broke: report.shield_broke,
                seq: p.claim.seq,
                point: p.claim.hit.point,
            });
        }
        if let Ok(mut s) = damage.get_mut(victim_link) {
            s.send::<ReliableChannel>(DamageTaken { from: shooter.shot.origin, zone, shield: report.hit_shield() });
        }
        if report.killed {
            deaths.write(PlayerDied { victim: victim_e, killer: Some(shooter.entity), zone: Some(zone) });
        }
        // Volt core: a breaking arc shocks the victim's enemies nearby (in free-for-all: everyone else).
        if report.shield_broke && halo_spec.core == Some(Core::Volt) {
            let pulse = &data.combat.volt_pulse;
            let victim_team = vinfo.team;
            for (e, _, info, _, mut v, m, _) in &mut players {
                if e != victim_e && hostile(info.team, victim_team) && m.0.pos.distance(victim_pos) <= pulse.radius_m {
                    v.wounds.volt_slow_s = pulse.duration_s;
                }
            }
        }
    }
    pending.0 = keep;
}

/// Shots hurt only while the match is live: not in the lobby, nor in the intermission once it has ended.
pub fn takes_damage(phase: MatchPhase) -> bool {
    phase == MatchPhase::Live
}

/// A kill's mark on the match: whether it counts (a live deathmatch, an enemy killed), and in team deathmatch
/// a point for the killer's team. Free-for-all reads each player's kills instead, so nothing is added here.
fn score_kill(m: &mut MatchState, killer: Option<Team>, victim: Option<Team>) -> bool {
    if !m.mode.is_deathmatch() || m.phase != MatchPhase::Live || !hostile(killer, victim) {
        return false;
    }
    match killer.filter(|_| m.has_teams()) {
        Some(Team::A) => m.score_a += 1,
        Some(Team::B) => m.score_b += 1,
        None => {}
    }
    true
}

#[allow(clippy::too_many_arguments, clippy::type_complexity)]
fn handle_deaths(
    data: Res<Data>,
    mut died: MessageReader<PlayerDied>,
    mut players: Query<(&PlayerId, &PlayerInfo, &mut Vitals, &mut Score, &mut PlayerMove, &mut ServerPlayer)>,
    mut weapons: Query<(&mut PlayerWeapon, &PlayerLoadout)>,
    mut matches: Query<&mut MatchState>,
    mut feed: ClientLinks<KillFeed>,
    mut kills: Local<u64>,
) {
    let mode = matches.iter().next().map_or(MatchMode::Tdm, |m| m.mode);
    // Kills and deaths count only in a live match (the range is always live): a fall or a bleed-out in the
    // lobby or in the intermission after the winner is decided leaves the standings alone.
    let counts = matches.iter().next().is_none_or(|m| m.phase == MatchPhase::Live);
    for d in died.read() {
        let Ok((vid, vinfo, mut v, mut score, mut mv, _)) = players.get_mut(d.victim) else { continue };
        v.health.dead = true;
        v.respawn_s = data.rules.deathmatch(mode).respawn_s;
        if counts {
            score.deaths += 1;
        }
        mv.0.vel = Vec3::ZERO;
        let (victim_id, victim_team) = (vid.0, vinfo.team);
        let killer = d.killer.filter(|k| *k != d.victim);
        let killer_id = killer.and_then(|k| players.get(k).ok()).map(|p| p.0.0);
        if let Some(k) = killer.filter(|_| counts)
            && let Ok((_, kinfo, _, mut kscore, _, mut ksp)) = players.get_mut(k)
        {
            kscore.kills += 1;
            // When they reached this kill count: the free-for-all tie-break.
            *kills += 1;
            ksp.kill_seq = *kills;
            if let Some(mut m) = matches.iter_mut().next()
                && score_kill(&mut m, kinfo.team, victim_team)
            {
                // Every kill tops up a magazine (user direction), so a good run keeps going.
                if let Ok((mut w, l)) = weapons.get_mut(k) {
                    w.0.refill_mags(data.rules.deathmatch(m.mode).kill_refill_mags, l.0.weapon.mag_capacity);
                }
            }
        }
        send_to_every_client(&mut feed, KillFeed { killer: killer_id, victim: victim_id, zone: d.zone });
    }
}

/// The message senders of every connected client: the joined players' links and the host's own client.
pub(crate) type ClientLinks<'w, 's, M> =
    Query<'w, 's, &'static mut MessageSender<M>, (With<ClientOf>, With<Connected>)>;

/// Queues `msg` once for every connected player, the host included. lightyear's `ServerMultiMessageSender`
/// writes into each link's transport, but the host's in-process client never reads a transport (it only gets
/// what is queued on its own `MessageSender`), so the kill feed sent that way reached every joined player and
/// never the host.
pub(crate) fn send_to_every_client<M: lightyear::prelude::Message + Clone>(links: &mut ClientLinks<M>, msg: M) {
    for mut link in links.iter_mut() {
        link.send::<ReliableChannel>(msg.clone());
    }
}

/// The host's own client: lightyear gives it this peer id.
const HOST_PEER: PeerId = PeerId::Local(0);

/// Every joined player but `peer`, for the multi-sender. The host's own client is left out: it never reads what
/// the multi-sender queues for it (see [`send_to_every_client`]), so those copies only piled up in memory; the
/// host draws other players' shots itself.
fn joined_except(peer: PeerId) -> NetworkTarget {
    NetworkTarget::AllExcept(vec![peer, HOST_PEER].into())
}

#[cfg(test)]
mod routing_tests {
    use super::*;
    use bevy::ecs::system::RunSystemOnce;
    use lightyear::connection::host::HostClient;
    use lightyear::prelude::client::ClientPlugins;
    use std::any::TypeId;

    /// A listen server in one app, as when hosting: lightyear's server and client plugins, the protocol, a
    /// started server, the host's own client connected through it, and two joined players' links (peers 7 and
    /// 8; not linked to a socket, so what is queued for them stays in their transports to be counted).
    fn listen_server() -> (App, Entity, [Entity; 2]) {
        let tick = std::time::Duration::from_secs_f64(1.0 / 60.0);
        let mut app = App::new();
        app.add_plugins((MinimalPlugins, bevy::state::app::StatesPlugin));
        app.add_plugins((ServerPlugins { tick_duration: tick }, ClientPlugins { tick_duration: tick }));
        app.add_plugins(vetf_net::ProtocolPlugin { input_redundancy: 1 });
        // What `App::run` does before the first frame (replication builds its channel maps here).
        app.finish();
        app.cleanup();
        let server = app.world_mut().spawn((Name::new("Server"), Server::default(), Linked, Started)).id();
        let host = app.world_mut().spawn((Client, LinkOf { server })).id();
        app.world_mut().trigger(Connect { entity: host });
        let joined = [7, 8].map(|id| {
            app.world_mut().spawn((LinkOf { server }, ClientOf, Connected, RemoteId(PeerId::Netcode(id)))).id()
        });
        app.update();
        assert!(app.world().entity(host).contains::<HostClient>(), "the host's client is a host client");
        (app, host, joined)
    }

    fn host_feed(app: &mut App, host: Entity) -> Vec<KillFeed> {
        app.world_mut()
            .get_mut::<MessageReceiver<KillFeed>>(host)
            .map(|mut r| r.receive().collect())
            .unwrap_or_default()
    }

    /// Messages on channel `C` queued in a link's transport (and taken out, to count the next ones).
    fn queued<C: 'static>(app: &App, link: Entity) -> usize {
        let transport = app.world().get::<Transport>(link).unwrap();
        transport.recv_channel.try_iter().filter(|(kind, ..)| kind.0 == TypeId::of::<C>()).count()
    }

    /// Every player sees every kill exactly once, the host included (it used to see none: the feed went out
    /// through lightyear's multi-sender, which the host's own client never reads).
    #[test]
    fn every_kill_reaches_the_host_and_each_joined_player_once() {
        let (mut app, host, joined) = listen_server();
        let kills = [
            KillFeed { killer: Some(7), victim: 0, zone: Some(Zone::Head) },
            KillFeed { killer: None, victim: 8, zone: None },
        ];
        for kill in kills {
            app.world_mut()
                .run_system_once(move |mut links: ClientLinks<KillFeed>| send_to_every_client(&mut links, kill))
                .unwrap();
            app.update();
            assert_eq!(host_feed(&mut app, host), vec![kill], "the host's kill feed");
            for link in joined {
                assert_eq!(queued::<ReliableChannel>(&app, link), 1, "a joined player's kill feed");
            }
            app.update();
            assert!(host_feed(&mut app, host).is_empty(), "shown once");
        }
    }

    /// Shot effects go to every joined player but the shooter, and are not queued for the host's own client,
    /// which would never read them.
    #[test]
    fn shot_fx_skip_the_shooter_and_the_hosts_own_client() {
        let (mut app, host, joined) = listen_server();
        for (shooter, want) in [(PeerId::Netcode(7), [0, 1]), (HOST_PEER, [1, 1])] {
            let fx = ShotFx { shooter: 7, origin: Vec3::ZERO, end: Vec3::X };
            app.world_mut()
                .run_system_once(move |mut sender: ServerMultiMessageSender, server: Query<&Server>| {
                    sender.send::<_, FxChannel>(&fx, server.single().unwrap(), &joined_except(shooter)).unwrap();
                })
                .unwrap();
            app.update();
            let got = joined.map(|link| queued::<FxChannel>(&app, link));
            assert_eq!(got, want, "shooter {shooter:?}");
            assert_eq!(queued::<FxChannel>(&app, host), 0, "shooter {shooter:?}: nothing piles up for the host");
        }
    }
}

/// The match systems run on a world of players: deaths and kill credit, teams, seats.
#[cfg(test)]
mod system_tests {
    use super::*;
    use bevy::ecs::system::RunSystemOnce;

    fn world(mode: MatchMode, phase: MatchPhase) -> App {
        let d = GameData::embedded();
        let mut app = App::new();
        app.add_message::<PlayerDied>();
        let rules = d.rules.deathmatch(mode);
        app.world_mut().spawn(MatchState {
            mode,
            map: "showhome".into(),
            score_a: 0,
            score_b: 0,
            score_limit: rules.score_limit,
            time_left_s: rules.time_limit_s,
            phase,
            lobby_name: String::new(),
            max_players: rules.max_players,
            rules: d.rules.rulesets.get(mode),
        });
        app.insert_resource(Data(Arc::new(d)));
        app
    }

    fn player(app: &mut App, id: u64, team: Option<Team>) -> Entity {
        let d = GameData::embedded();
        let l = Loadout::default_for(&d, MatchMode::Ffa);
        app.world_mut()
            .spawn((
                PlayerId(id),
                PlayerInfo { name: format!("P{id}"), team },
                fresh_vitals(&d, &l, MatchMode::Ffa),
                Score::default(),
                PlayerMove(MoveState::spawn(Vec3::ZERO, 1.0)),
                PlayerWeapon(WeaponState::new(&d, &l.weapon)),
                PlayerLoadout(l),
                ServerPlayer {
                    link: Entity::PLACEHOLDER,
                    peer: PeerId::Netcode(id),
                    history: PoseHistory::default(),
                    shots: VecDeque::new(),
                    choice: None,
                    last_attacker: None,
                    kill_seq: 0,
                },
            ))
            .id()
    }

    fn kill(app: &mut App, killer: Entity, victim: Entity) {
        app.world_mut().write_message(PlayerDied { victim, killer: Some(killer), zone: Some(Zone::Head) });
    }

    fn standing(app: &App, e: Entity) -> (u16, u16, u64) {
        let w = app.world();
        let s = w.get::<Score>(e).unwrap();
        (s.kills, s.deaths, w.get::<ServerPlayer>(e).unwrap().kill_seq)
    }

    /// Empty every spare magazine (the one in the gun stays).
    fn spend_spares(app: &mut App, e: Entity) {
        let mut w = app.world_mut().get_mut::<PlayerWeapon>(e).unwrap();
        let loaded = w.0.loaded as usize;
        for (i, r) in w.0.rounds.iter_mut().enumerate() {
            if i != loaded {
                *r = 0;
            }
        }
    }

    fn full_spares(app: &App, e: Entity) -> usize {
        let w = app.world().get::<PlayerWeapon>(e).unwrap();
        w.0.rounds.iter().enumerate().filter(|(i, r)| *i != w.0.loaded as usize && **r > 0).count()
    }

    /// Free-for-all: each kill is the killer's point, numbered in the order they came (the tie-break), and
    /// tops up a magazine.
    #[test]
    fn kills_count_and_refill_while_the_match_is_live() {
        let mut app = world(MatchMode::Ffa, MatchPhase::Live);
        let (a, b, victim) = (player(&mut app, 1, None), player(&mut app, 2, None), player(&mut app, 3, None));
        spend_spares(&mut app, a);
        kill(&mut app, a, victim);
        kill(&mut app, b, victim);
        app.world_mut().run_system_once(handle_deaths).unwrap();
        assert_eq!(standing(&app, a), (1, 0, 1));
        assert_eq!(standing(&app, b), (1, 0, 2), "b got there second");
        assert_eq!(standing(&app, victim), (0, 2, 0));
        assert!(app.world().get::<Vitals>(victim).unwrap().health.dead);
        assert_eq!(full_spares(&app, a), 1, "a kill refills one magazine");
    }

    /// Once the match has ended (the 8 s intermission) nothing changes the standings any more: a kill, a fall
    /// or a bleed-out still kills, but counts for nobody and refills nothing. The lobby is the same.
    #[test]
    fn a_death_after_the_match_ended_leaves_the_standings_alone() {
        for phase in [MatchPhase::Ended { winner: None, player: Some(1) }, MatchPhase::Lobby] {
            let mut app = world(MatchMode::Ffa, phase);
            let (winner, victim) = (player(&mut app, 1, None), player(&mut app, 2, None));
            spend_spares(&mut app, winner);
            kill(&mut app, winner, victim);
            app.world_mut().write_message(PlayerDied { victim: winner, killer: None, zone: None });
            app.world_mut().run_system_once(handle_deaths).unwrap();
            assert_eq!(standing(&app, winner), (0, 0, 0), "{phase:?}");
            assert_eq!(standing(&app, victim), (0, 0, 0), "{phase:?}");
            assert!(app.world().get::<Vitals>(victim).unwrap().health.dead, "the victim still dies");
            assert_eq!(full_spares(&app, winner), 0, "{phase:?}: no refill");
            assert!(!takes_damage(phase), "shots are dropped too");
        }
        assert!(takes_damage(MatchPhase::Live));
    }

    /// Team deathmatch after free-for-all: everyone without a team joins the smaller one, the host (id 0)
    /// first, so the split is even; free-for-all clears the teams again.
    #[test]
    fn teams_follow_the_mode() {
        let mut app = world(MatchMode::Tdm, MatchPhase::Lobby);
        let ids = [9, 0, 5, 3];
        let es: Vec<Entity> = ids.iter().map(|id| player(&mut app, *id, None)).collect();
        app.world_mut().run_system_once(sync_teams).unwrap();
        let team = |app: &App, e: Entity| app.world().get::<PlayerInfo>(e).unwrap().team;
        assert_eq!(team(&app, es[1]), Some(Team::A), "the host");
        let a = es.iter().filter(|e| team(&app, **e) == Some(Team::A)).count();
        assert_eq!(a, 2, "two a side");
        // by id: 0 A, 3 B, 5 A, 9 B
        assert_eq!(
            es.iter().map(|e| team(&app, *e)).collect::<Vec<_>>(),
            [Some(Team::B), Some(Team::A), Some(Team::A), Some(Team::B)]
        );
        // a late joiner fills the smaller side
        let late = player(&mut app, 11, None);
        app.world_mut().get_mut::<PlayerInfo>(es[0]).unwrap().team = Some(Team::A);
        app.world_mut().run_system_once(sync_teams).unwrap();
        assert_eq!(team(&app, late), Some(Team::B));
        // free-for-all: no teams
        let mut q = app.world_mut().query::<&mut MatchState>();
        q.single_mut(app.world_mut()).unwrap().mode = MatchMode::Ffa;
        app.world_mut().run_system_once(sync_teams).unwrap();
        assert!(es.iter().chain([&late]).all(|e| team(&app, *e).is_none()));
    }

    /// The seats follow the match: a lobby switched to a mode with fewer seats turns joiners away once it
    /// holds that many, the host's own client never.
    #[test]
    fn seats_follow_the_match() {
        use lightyear::connection::shared::{ConnectionRequestHandler, DeniedReason};
        let mut app = world(MatchMode::Ffa, MatchPhase::Lobby);
        let seats = Seats::new(9);
        app.insert_resource(seats.clone());
        let check = seats.check();
        for id in 0..7 {
            player(&mut app, id, None);
        }
        app.world_mut().run_system_once(count_seats).unwrap();
        assert_eq!(seats.free(), 1, "7 of free-for-all's 8");
        assert_eq!(check.handle_request(PeerId::Netcode(42)), None);
        player(&mut app, 7, None);
        app.world_mut().run_system_once(count_seats).unwrap();
        assert_eq!(seats.free(), 0);
        assert_eq!(check.handle_request(PeerId::Netcode(42)), Some(DeniedReason::ServerFull), "netcode says full");
        assert!(lobby_full(8, 8, false), "the backstop agrees");
        assert!(!lobby_full(8, 8, true), "never the host's own client");
        assert!(!lobby_full(8, 7, false));
        assert_eq!(free_seats(6, 7), 0, "more players than seats (a lobby that shrank) is still full");
    }

    /// Team deathmatch and free-for-all deal every player an agent when the match goes live, keep it for the
    /// match (a late joiner gets one too), take them back in the lobby and deal afresh on a restart; the
    /// gun range deals none.
    #[test]
    fn agents_are_dealt_for_the_match() {
        let agent = |app: &App, e: Entity| app.world().get::<PlayerAgent>(e).unwrap().0.clone();
        let set_match = |app: &mut App, f: &dyn Fn(&mut MatchState)| {
            let mut q = app.world_mut().query::<&mut MatchState>();
            f(&mut q.single_mut(app.world_mut()).unwrap());
        };
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            let mut app = world(mode, MatchPhase::Lobby);
            app.init_resource::<LocalTimeline>();
            app.add_systems(Update, deal_agents);
            let es: Vec<Entity> = (0..6)
                .map(|id| {
                    let e = player(&mut app, id, None);
                    app.world_mut().entity_mut(e).insert(PlayerAgent::default());
                    e
                })
                .collect();
            app.update();
            assert!(es.iter().all(|e| agent(&app, *e).is_none()), "{mode:?}: no agents in the lobby");
            set_match(&mut app, &|m| m.phase = MatchPhase::Live);
            app.update();
            let pool = crate::loadout::agent_ids();
            let dealt: Vec<String> = es.iter().map(|e| agent(&app, *e).expect("dealt at the start")).collect();
            assert!(dealt.iter().all(|a| pool.contains(a)), "{dealt:?}");
            // the clock runs: the same agents; a late joiner gets one
            set_match(&mut app, &|m| m.time_left_s -= 30.0);
            let late = player(&mut app, 9, None);
            app.world_mut().entity_mut(late).insert(PlayerAgent::default());
            app.update();
            assert_eq!(es.iter().map(|e| agent(&app, *e).unwrap()).collect::<Vec<_>>(), dealt, "{mode:?}: kept");
            assert!(agent(&app, late).is_some());
            set_match(&mut app, &|m| m.phase = MatchPhase::Ended { winner: None, player: None });
            app.update();
            assert_eq!(agent(&app, es[0]), Some(dealt[0].clone()), "kept on the end board");
            // the host's RESTART MATCH: the clock jumps back up, a new deal (from a new seed)
            app.world_mut().resource_mut::<LocalTimeline>().apply_delta(1000);
            set_match(&mut app, &|m| {
                m.phase = MatchPhase::Live;
                m.time_left_s += 30.0;
            });
            app.update();
            assert!(es.iter().all(|e| agent(&app, *e).is_some()), "{mode:?}: dealt again");
            set_match(&mut app, &|m| m.phase = MatchPhase::Lobby);
            app.update();
            assert!(es.iter().all(|e| agent(&app, *e).is_none()), "{mode:?}: back to the lobby");
        }
        // The gun range: the agent each player picked (the default without a pick, or for an unknown one)
        let mut range = world(MatchMode::Range, MatchPhase::Live);
        range.init_resource::<LocalTimeline>();
        range.add_systems(Update, deal_agents);
        let picked = player(&mut range, 0, None);
        let unknown = player(&mut range, 1, None);
        let none = player(&mut range, 2, None);
        for (e, pick) in [(picked, Some("solace")), (unknown, Some("nobody")), (none, None)] {
            let choice = pick.map(|a| LoadoutChoice { agent: a.into(), ..default_choice(&GameData::embedded()) });
            range.world_mut().get_mut::<ServerPlayer>(e).unwrap().choice = choice;
            range.world_mut().entity_mut(e).insert(PlayerAgent::default());
        }
        range.update();
        assert_eq!(agent(&range, picked).as_deref(), Some("solace"), "the range: the pick");
        assert_eq!(agent(&range, unknown).as_deref(), Some("kestrel"));
        assert_eq!(agent(&range, none).as_deref(), Some("kestrel"));
    }
}

#[allow(clippy::type_complexity)]
fn respawn_players(
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    timeline: Res<LocalTimeline>,
    mut players: Query<(
        &PlayerId,
        &PlayerInfo,
        &Score,
        &mut Vitals,
        &mut PlayerMove,
        &mut PlayerLook,
        &mut PlayerWeapon,
        &mut PlayerItems,
        &mut PlayerLoadout,
        &mut ServerPlayer,
    )>,
    matches: Query<&MatchState>,
) {
    let Some(level) = level else { return };
    let mode = match_mode(&matches);
    let dt = data.tick_dt();
    let tick = timeline.tick().0 as u64;
    let mut living: Vec<(Option<Team>, Vec3)> =
        players.iter().filter(|p| !p.3.health.dead).map(|p| (p.1.team, p.4.0.pos)).collect();
    for (id, info, score, mut v, mut mv, mut look, mut w, mut it, mut lo, mut sp) in &mut players {
        if !v.health.dead {
            continue;
        }
        v.respawn_s -= dt;
        if v.respawn_s > 0.0 {
            continue;
        }
        // The player's choice as this mode takes it (a lobby mode change reshapes it), else the default.
        match sp.choice.as_ref().map(|c| loadout_from_choice(&data, c, mode)) {
            Some(Ok(l)) => lo.0 = l,
            Some(Err(_)) => {}
            None => lo.0 = default_loadout(&data, mode),
        }
        let enemies: Vec<Vec3> = living.iter().filter(|(t, _)| hostile(info.team, *t)).map(|(_, p)| *p).collect();
        let spawn = spawn_for(&data, &level, mode, info.team, &enemies, spawn_roll(id.0, score.deaths as u64, tick));
        // Players spawning on the same tick (the start of a match) keep away from each other too.
        if mode == MatchMode::Ffa {
            living.push((info.team, spawn.pos));
        }
        *v = fresh_vitals(&data, &lo.0, mode);
        mv.0 = MoveState::spawn(spawn.pos, loadout_fuel(&data, &lo.0));
        *look = PlayerLook { yaw: spawn.yaw, pitch: 0.0 };
        w.0 = WeaponState::new(&data, &lo.0.weapon);
        it.0 = ItemState::new(&lo.0.kit);
        sp.history.clear();
        sp.shots.clear();
        sp.last_attacker = None;
    }
}

/// One player's standing in a free-for-all.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Standing {
    pub id: u64,
    pub kills: u16,
    pub deaths: u16,
    /// When they reached their kill count (lower is earlier; see [`ServerPlayer::kill_seq`]).
    pub kill_seq: u64,
}

/// The free-for-all winner: the most kills, then the fewest deaths, then whoever reached that kill count
/// first. `None` is a draw (nobody scored and the deaths tie too).
pub fn ffa_winner(standings: &[Standing]) -> Option<u64> {
    // Without kills there is no "first to reach it".
    let key = |s: &Standing| (std::cmp::Reverse(s.kills), s.deaths, if s.kills > 0 { s.kill_seq } else { 0 });
    let mut ranked: Vec<&Standing> = standings.iter().collect();
    ranked.sort_by_key(|s| key(s));
    match ranked.as_slice() {
        [] => None,
        [one] => Some(one.id),
        [first, second, ..] => (key(first) != key(second)).then_some(first.id),
    }
}

/// How a live match ends, if it does now: a team reaches the score limit (team deathmatch), a player does
/// (free-for-all), or the clock runs out.
pub fn match_result(m: &MatchState, standings: &[Standing]) -> Option<MatchPhase> {
    let limit = m.score_limit;
    let out_of_time = m.time_left_s <= 0.0;
    match m.mode {
        MatchMode::Tdm if m.score_a >= limit || m.score_b >= limit || out_of_time => {
            let winner = match m.score_a.cmp(&m.score_b) {
                std::cmp::Ordering::Greater => Some(Team::A),
                std::cmp::Ordering::Less => Some(Team::B),
                std::cmp::Ordering::Equal => None,
            };
            Some(MatchPhase::Ended { winner, player: None })
        }
        MatchMode::Ffa if standings.iter().any(|s| s.kills as u32 >= limit) || out_of_time => {
            Some(MatchPhase::Ended { winner: None, player: ffa_winner(standings) })
        }
        _ => None,
    }
}

#[allow(clippy::type_complexity)]
fn run_match(
    data: Res<Data>,
    mut matches: Query<&mut MatchState>,
    mut players: Query<(&PlayerId, &mut PlayerNet, &mut Vitals, &mut Score, &ServerPlayer)>,
    mut intermission: Local<f32>,
) {
    let Some(mut m) = matches.iter_mut().next() else { return };
    if !m.mode.is_deathmatch() {
        return;
    }
    let dt = data.tick_dt();
    match m.phase {
        // The clock waits for the host's START MATCH.
        MatchPhase::Lobby => {}
        MatchPhase::Live => {
            m.time_left_s = (m.time_left_s - dt).max(0.0);
            let standings: Vec<Standing> = players
                .iter()
                .map(|(id, _, _, s, sp)| Standing { id: id.0, kills: s.kills, deaths: s.deaths, kill_seq: sp.kill_seq })
                .collect();
            if let Some(end) = match_result(&m, &standings) {
                m.phase = end;
                *intermission = INTERMISSION_S;
                info!("match over: {end:?}, {}-{}", m.score_a, m.score_b);
            }
        }
        MatchPhase::Ended { .. } => {
            *intermission -= dt;
            if *intermission <= 0.0 {
                // Back to the lobby: teams, loadouts and READY for the next one.
                reset_match(
                    &mut m,
                    &data,
                    Some(MatchPhase::Lobby),
                    players.iter_mut().map(|(_, n, v, s, _)| (n, v, s)),
                );
            }
        }
    }
}

/// The agent a player is dealt in a match (DIRECTION_LOG 17: team deathmatch and free-for-all have no agent
/// pick): one roll from the match's seed and the player's id, so every match deals afresh, a player keeps
/// theirs for the whole match, and the same seed deals the same agents (tests and replays). `pool` is
/// `agents.ron`'s ids.
pub fn deal_agent(pool: &[String], seed: u64, player: u64) -> Option<&String> {
    let roll = vetf_sim::rng::SplitMix::from_parts(&[seed, player, 0x4147_454e_5453]).next_f32();
    pool.get(((roll * pool.len() as f32) as usize).min(pool.len().saturating_sub(1)))
}

/// What [`deal_agents`] remembers: the running match's seed (the tick it went live) and its clock.
#[derive(Default)]
struct AgentDeal {
    seed: Option<u64>,
    clock: f32,
}

/// Team deathmatch and free-for-all: deal every player a random agent ([`deal_agent`]) when the match goes
/// live, keep it until the match is over (a player who joins mid-match is dealt one on arrival), and take
/// them back in the lobby. The host's RESTART MATCH (the clock jumps back up) is a new match and deals
/// again. The gun range: the agent each player picked on the Loadout screen.
fn deal_agents(
    matches: Query<&MatchState>,
    timeline: Res<LocalTimeline>,
    mut players: Query<(&PlayerId, &mut PlayerAgent, Option<&ServerPlayer>)>,
    mut deal: Local<AgentDeal>,
) {
    let running = matches.iter().next().filter(|m| m.mode.is_deathmatch() && m.phase != MatchPhase::Lobby);
    let Some(m) = running else {
        deal.seed = None;
        let range = matches.iter().next().is_some_and(|m| m.mode == MatchMode::Range);
        let pool = crate::loadout::agent_ids();
        for (_, mut agent, sp) in &mut players {
            let picked = sp.and_then(|p| p.choice.as_ref()).map(|c| c.agent.clone()).filter(|a| pool.contains(a));
            let want = range.then(|| picked.unwrap_or_else(|| crate::config::DEFAULT_AGENT.into()));
            if agent.0 != want {
                agent.0 = want;
            }
        }
        return;
    };
    let restarted = m.phase == MatchPhase::Live && m.time_left_s > deal.clock;
    deal.clock = m.time_left_s;
    let seed = match deal.seed {
        Some(seed) if !restarted => seed,
        _ => {
            let seed = timeline.tick().0 as u64;
            deal.seed = Some(seed);
            for (_, mut agent, _) in &mut players {
                agent.0 = None;
            }
            seed
        }
    };
    let pool = crate::loadout::agent_ids();
    for (id, mut agent, _) in &mut players {
        if agent.0.is_none()
            && let Some(dealt) = deal_agent(&pool, seed, id.0)
        {
            info!("player {:x} plays {dealt} this match", id.0);
            agent.0 = Some(dealt.clone());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::ZoneTable;
    use vetf_sim::data::{AmmoChoice, AmmoKind};
    use vetf_sim::gear::HaloChoice;

    fn spawn_ring() -> Level {
        // Team A's spawns on the west, team B's on the east (like Showhome), 10 m apart.
        let mut level = Level::default();
        for x in [0.0, 10.0, 20.0] {
            level.spawns.push(SpawnPoint { pos: Vec3::new(x, 0.0, 0.0), yaw: 0.0, team: Some(Team::A) });
        }
        for x in [80.0, 90.0, 100.0] {
            level.spawns.push(SpawnPoint { pos: Vec3::new(x, 0.0, 0.0), yaw: 0.0, team: Some(Team::B) });
        }
        level
    }

    #[test]
    fn free_for_all_spawns_on_either_side_far_from_enemies() {
        let level = spawn_ring();
        // An enemy on team B's side: the farthest points are team A's, whatever team the spawn was drawn for.
        let enemy = [Vec3::new(95.0, 0.0, 0.0)];
        assert_eq!(pick_ffa_spawn(&level, &enemy, 0.0, 0.99).pos.x, 0.0, "no slack: always the farthest");
        // With 12 m of slack the two westmost spawns (95 and 85 m away) are candidates, never the third (75 m).
        let picks: Vec<f32> = (0..20).map(|i| pick_ffa_spawn(&level, &enemy, 12.0, i as f32 / 20.0).pos.x).collect();
        assert!(picks.iter().all(|x| *x == 0.0 || *x == 10.0), "{picks:?}");
        assert!(picks.contains(&0.0) && picks.contains(&10.0), "a little randomness: {picks:?}");
        // An enemy on team A's side: team B's spawns are just as good for anyone in free-for-all.
        let west = [Vec3::new(5.0, 0.0, 0.0)];
        assert_eq!(pick_ffa_spawn(&level, &west, 0.0, 0.0).pos.x, 100.0);
        // The nearest enemy counts: one at each end leaves the middle spawns.
        let both = [Vec3::new(-10.0, 0.0, 0.0), Vec3::new(110.0, 0.0, 0.0)];
        let mid = pick_ffa_spawn(&level, &both, 0.0, 0.5).pos.x;
        assert!(mid == 20.0 || mid == 80.0, "{mid}");
        // Nobody alive: any spawn of either side, by the roll.
        let all: Vec<f32> = (0..6).map(|i| pick_ffa_spawn(&level, &[], 6.0, i as f32 / 6.0).pos.x).collect();
        assert_eq!(all, vec![0.0, 10.0, 20.0, 80.0, 90.0, 100.0]);
        // A roll of 1.0 (out of range) still picks a spawn; a level without spawns falls back to the origin.
        assert_eq!(pick_ffa_spawn(&level, &[], 0.0, 1.0).pos.x, 100.0);
        assert_eq!(pick_ffa_spawn(&Level::default(), &enemy, 6.0, 0.3).pos, Vec3::new(0.0, 0.5, 0.0));
    }

    #[test]
    fn free_for_all_spawns_come_from_the_rules_and_rolls_repeat() {
        let d = GameData::embedded();
        let level = vetf_sim::maps::showhome();
        let enemy = [level.spawns[0].pos];
        for i in 0..8 {
            let roll = spawn_roll(7, i, 1200);
            assert_eq!(roll, spawn_roll(7, i, 1200), "deterministic");
            assert!((0.0..1.0).contains(&roll));
            let s = spawn_for(&d, &level, MatchMode::Ffa, None, &enemy, roll);
            let far = level.spawns.iter().map(|p| p.pos.distance(enemy[0])).fold(0.0, f32::max);
            assert!(s.pos.distance(enemy[0]) >= far - d.rules.ffa.spawn_slack_m - 1e-3);
        }
        // Team deathmatch keeps to the team's side.
        let s = spawn_for(&d, &level, MatchMode::Tdm, Some(Team::B), &enemy, 0.0);
        assert_eq!(s.team, Some(Team::B));
    }

    #[test]
    fn everyone_is_an_enemy_without_teams() {
        assert!(hostile(None, None), "free-for-all");
        assert!(hostile(Some(Team::A), None) && hostile(None, Some(Team::B)));
        assert!(hostile(Some(Team::A), Some(Team::B)));
        assert!(!hostile(Some(Team::B), Some(Team::B)), "team mates");
    }

    fn standing(id: u64, kills: u16, deaths: u16, kill_seq: u64) -> Standing {
        Standing { id, kills, deaths, kill_seq }
    }

    #[test]
    fn the_free_for_all_winner_has_most_kills_then_fewest_deaths_then_got_there_first() {
        assert_eq!(ffa_winner(&[]), None);
        assert_eq!(ffa_winner(&[standing(3, 0, 0, 0)]), Some(3), "alone wins");
        assert_eq!(ffa_winner(&[standing(1, 9, 2, 40), standing(2, 12, 7, 50), standing(3, 4, 0, 30)]), Some(2));
        // Same kills: fewer deaths.
        assert_eq!(ffa_winner(&[standing(1, 12, 5, 40), standing(2, 12, 3, 50)]), Some(2));
        // Same kills and deaths: the first to reach that score.
        assert_eq!(ffa_winner(&[standing(1, 12, 3, 52), standing(2, 12, 3, 47)]), Some(2));
        // Nobody scored and the deaths tie: a draw (stale kill numbers from an earlier match do not count).
        assert_eq!(ffa_winner(&[standing(1, 0, 1, 90), standing(2, 0, 1, 12)]), None);
        assert_eq!(ffa_winner(&[standing(1, 0, 2, 0), standing(2, 0, 1, 0)]), Some(2));
    }

    fn live(mode: MatchMode) -> MatchState {
        let d = GameData::embedded();
        let rules = d.rules.deathmatch(mode);
        MatchState {
            mode,
            map: "showhome".into(),
            score_a: 0,
            score_b: 0,
            score_limit: rules.score_limit,
            time_left_s: rules.time_limit_s,
            phase: MatchPhase::Live,
            lobby_name: String::new(),
            max_players: rules.max_players,
            rules: d.rules.rulesets.get(mode),
        }
    }

    #[test]
    fn a_free_for_all_ends_at_the_score_limit_or_the_clock() {
        let m = live(MatchMode::Ffa);
        assert_eq!(m.score_limit, 25);
        let close = [standing(1, 24, 3, 80), standing(2, 20, 1, 70)];
        assert_eq!(match_result(&m, &close), None, "nobody at 25 yet");
        let won = [standing(1, 25, 3, 81), standing(2, 20, 1, 70)];
        assert_eq!(match_result(&m, &won), Some(MatchPhase::Ended { winner: None, player: Some(1) }));
        // Team scores mean nothing in free-for-all.
        let mut odd = m.clone();
        odd.score_a = 99;
        assert_eq!(match_result(&odd, &close), None);
        // Time: the leader wins.
        let timed_out = MatchState { time_left_s: 0.0, ..m.clone() };
        assert_eq!(match_result(&timed_out, &close), Some(MatchPhase::Ended { winner: None, player: Some(1) }));
        assert_eq!(
            match_result(&timed_out, &[standing(1, 0, 0, 0), standing(2, 0, 0, 0)]),
            Some(MatchPhase::Ended { winner: None, player: None }),
            "a draw"
        );
    }

    #[test]
    fn kills_count_against_every_enemy_in_free_for_all() {
        let mut ffa = live(MatchMode::Ffa);
        assert!(score_kill(&mut ffa, None, None), "no teams: everyone is an enemy");
        assert_eq!((ffa.score_a, ffa.score_b), (0, 0), "free-for-all reads players' kills, not team scores");
        let mut tdm = live(MatchMode::Tdm);
        assert!(score_kill(&mut tdm, Some(Team::B), Some(Team::A)));
        assert_eq!((tdm.score_a, tdm.score_b), (0, 1));
        assert!(!score_kill(&mut tdm, Some(Team::A), Some(Team::A)), "a team kill does not count");
        assert!(!score_kill(&mut live(MatchMode::Range), None, None), "the range keeps no score");
        let mut lobby = MatchState { phase: MatchPhase::Lobby, ..live(MatchMode::Ffa) };
        assert!(!score_kill(&mut lobby, None, None), "not before START MATCH");
    }

    #[test]
    fn team_deathmatch_still_ends_on_team_scores() {
        let mut m = live(MatchMode::Tdm);
        let ace = [standing(1, 60, 0, 1)];
        assert_eq!(match_result(&m, &ace), None, "a player's kills do not end a team match");
        m.score_b = m.score_limit;
        assert_eq!(match_result(&m, &ace), Some(MatchPhase::Ended { winner: Some(Team::B), player: None }));
        assert_eq!(match_result(&live(MatchMode::Range), &ace), None, "the range never ends");
    }

    #[test]
    fn the_host_switches_the_lobby_between_the_deathmatch_modes() {
        let d = GameData::embedded();
        let lobby = MatchState { phase: MatchPhase::Lobby, max_players: 10, ..live(MatchMode::Tdm) };
        // Free-for-all seats at most 8 (rules.ron), team deathmatch 10 and even.
        assert_eq!(lobby_mode_change(&d, &lobby, MatchMode::Ffa, 10, 3, true), Some(8));
        assert_eq!(lobby_mode_change(&d, &lobby, MatchMode::Ffa, 10, 3, false), None, "only the host");
        assert_eq!(lobby_mode_change(&d, &lobby, MatchMode::Ffa, 10, 9, true), None, "9 players do not fit");
        assert_eq!(lobby_mode_change(&d, &lobby, MatchMode::Tdm, 10, 3, true), None, "already team deathmatch");
        assert_eq!(lobby_mode_change(&d, &lobby, MatchMode::Range, 10, 3, true), None, "the range is a map");
        let ffa = MatchState { mode: MatchMode::Ffa, max_players: 7, ..lobby.clone() };
        assert_eq!(lobby_mode_change(&d, &ffa, MatchMode::Tdm, 7, 2, true), Some(6), "even for teams");
        let live_ffa = MatchState { phase: MatchPhase::Live, ..ffa };
        assert_eq!(lobby_mode_change(&d, &live_ffa, MatchMode::Tdm, 7, 2, true), None, "only in the lobby");
        assert_eq!(mode_max_players(&d, MatchMode::Ffa, 10), 8);
        assert_eq!(mode_max_players(&d, MatchMode::Ffa, 5), 5, "odd is fine without teams");
        assert_eq!(mode_max_players(&d, MatchMode::Tdm, 5), 4);
        assert_eq!(mode_max_players(&d, MatchMode::Tdm, 1), 2);
    }

    #[test]
    fn spawn_picks_far_from_enemies() {
        let mut level = Level::default();
        for x in [0.0, 10.0, 20.0] {
            level.spawns.push(SpawnPoint { pos: Vec3::new(x, 0.0, 0.0), yaw: 0.0, team: Some(Team::A) });
        }
        level.spawns.push(SpawnPoint { pos: Vec3::new(100.0, 0.0, 0.0), yaw: 0.0, team: Some(Team::B) });
        let s = pick_spawn(&level, Some(Team::A), &[Vec3::new(-5.0, 0.0, 0.0)]);
        assert_eq!(s.pos.x, 20.0);
    }

    /// Team deathmatch (the gear budget's mode).
    fn loadout_from_choice(d: &GameData, c: &LoadoutChoice) -> Result<Loadout, LoadoutError> {
        super::loadout_from_choice(d, c, MatchMode::Tdm)
    }

    /// A preset's halo, capped like the Loadout screen and the command line do.
    fn halo(d: &GameData, armor: &str) -> HaloChoice {
        HaloChoice::from_preset(d.armor.preset(armor).unwrap()).capped(d.armor.loadout_tier_caps)
    }

    #[test]
    fn the_mode_decides_the_healing_kit() {
        let d = GameData::embedded();
        let c = choice("ar7_mako", AmmoChoice::STANDARD, "arm_none");
        let tdm = super::loadout_from_choice(&d, &c, MatchMode::Tdm).unwrap();
        let range = super::loadout_from_choice(&d, &c, MatchMode::Range).unwrap();
        assert_eq!(tdm.kit, d.items.kit(MatchMode::Tdm));
        assert_eq!(range.kit, d.items.kit(MatchMode::Range));
        assert_ne!(tdm.kit, range.kit);
    }

    fn choice(weapon: &str, ammo: AmmoChoice, armor: &str) -> LoadoutChoice {
        mags(weapon, &[ammo; 4], armor)
    }

    fn mags(weapon: &str, mags: &[AmmoChoice], armor: &str) -> LoadoutChoice {
        let d = GameData::embedded();
        LoadoutChoice {
            weapon: weapon.into(),
            mags: mags.to_vec(),
            attachments: vec![],
            halo: halo(&d, armor),
            agent: "kestrel".into(),
        }
    }

    /// A deathmatch loadout as the Loadout screen sends it: armor tier `armor`, six magazines of `ammo`, the
    /// gun's parts.
    fn picks(weapon: &str, armor: u8, ammo: AmmoChoice, parts: &[&str]) -> LoadoutChoice {
        let d = GameData::embedded();
        let kit = &d.rules.deathmatch_loadout;
        LoadoutChoice {
            weapon: weapon.into(),
            mags: vec![ammo; kit.mags as usize],
            attachments: parts.iter().map(|p| p.to_string()).collect(),
            halo: HaloChoice::of_tier(kit, armor),
            agent: String::new(),
        }
    }

    #[test]
    fn halo_arcs_must_stay_within_the_tier_caps() {
        let d = GameData::embedded();
        let capped = choice("ar7_mako", AmmoChoice::STANDARD, "arm_bulwark_jugg");
        let l = super::loadout_from_choice(&d, &capped, MatchMode::Range).unwrap();
        assert_eq!(l.halo.tiers.legs, d.armor.loadout_tier_caps.legs);
        assert_eq!(l.halo.tiers.torso, 4);
        // the uncapped rare-loot halo is refused, not silently capped, in every mode
        let raw = LoadoutChoice {
            halo: HaloChoice::from_preset(d.armor.preset("arm_bulwark_jugg").unwrap()),
            ..capped.clone()
        };
        for mode in MatchMode::ALL {
            assert_eq!(super::loadout_from_choice(&d, &raw, mode).err(), Some(LoadoutError::TierCap), "{mode:?}");
        }
    }

    #[test]
    fn the_range_wears_a_custom_mixed_tier_halo_per_arc() {
        let d = GameData::embedded();
        let mut c = choice("ar7_mako", AmmoChoice::STANDARD, "arm_none");
        c.halo = HaloChoice { core: Core::Volt, tiers: ZoneTable { head: 1, torso: 3, arms: 0, legs: 2 } };
        let l = super::loadout_from_choice(&d, &c, MatchMode::Range).unwrap();
        assert_eq!(l.halo.tiers, c.halo.tiers);
        assert_eq!(l.halo.core, Some(Core::Volt));
        assert_eq!(l.weight, d.armor.weight_class(6));
        // no arcs: no halo, whatever the core
        c.halo.tiers = ZoneTable::splat(0);
        let l = super::loadout_from_choice(&d, &c, MatchMode::Range).unwrap();
        assert_eq!((l.halo.core, l.weight), (None, vetf_sim::data::WeightClass::None));
    }

    /// Team deathmatch and free-for-all wear one armor tier on the one halo core: each tier's combination and
    /// weight class (DIRECTION_LOG 17).
    #[test]
    fn deathmatch_players_wear_an_armor_tier() {
        use vetf_sim::data::WeightClass::{Heavy, Light, Medium};
        let d = GameData::embedded();
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            for (tier, arcs, weight) in [
                (1, ZoneTable { head: 1, torso: 1, arms: 1, legs: 1 }, Light),
                (2, ZoneTable { head: 2, torso: 2, arms: 2, legs: 2 }, Medium),
                (3, ZoneTable { head: 3, torso: 3, arms: 1, legs: 1 }, Medium),
                (4, ZoneTable { head: 4, torso: 4, arms: 3, legs: 2 }, Heavy),
            ] {
                let c = picks("ar7_mako", tier, AmmoChoice::STANDARD, &[]);
                let l = super::loadout_from_choice(&d, &c, mode).unwrap();
                assert_eq!((l.halo.tiers, l.weight), (arcs, weight), "{mode:?} T{tier}");
                assert_eq!(l.halo.core, Some(Core::Mender), "{mode:?} T{tier}: the one halo");
                assert_eq!(l.weapon.mags.len(), 6, "six magazines");
            }
        }
    }

    #[test]
    fn attachments_must_fit_the_gun_once_per_category() {
        let d = GameData::embedded();
        let mut c = choice("ar7_mako", AmmoChoice::STANDARD, "arm_none");
        c.attachments = vec!["optic_reddot".into(), "grip_angled".into(), "laser".into()];
        let l = loadout_from_choice(&d, &c).unwrap();
        assert!(l.weapon.attachments.contains(&"grip_angled".to_string()));
        assert!(l.weapon.attachments.contains(&"mako_stock_standard".to_string()), "defaults fill the rest");
        c.attachments = vec!["bipod".into()];
        assert_eq!(loadout_from_choice(&d, &c).err(), Some(LoadoutError::Attachment), "a Warden part");
        c.attachments = vec!["optic_reddot".into(), "optic_holo".into()];
        assert_eq!(loadout_from_choice(&d, &c).err(), Some(LoadoutError::Attachment), "two optics");
        c.attachments = vec!["mag_45".into(), "mag_drum60".into()];
        assert_eq!(loadout_from_choice(&d, &c).err(), Some(LoadoutError::Attachment), "two magazine types");
        c.attachments = vec!["nope".into()];
        assert_eq!(loadout_from_choice(&d, &c).err(), Some(LoadoutError::Attachment));
    }

    #[test]
    fn the_gun_range_has_no_gear_budget() {
        let d = GameData::embedded();
        let ap3 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 };
        let c = picks("ar7_mako", 4, ap3, &["mag_drum60"]);
        assert!(matches!(loadout_from_choice(&d, &c), Err(LoadoutError::OverBudget { .. })));
        assert!(super::loadout_from_choice(&d, &c, MatchMode::Range).is_ok());
    }

    /// The host prices the picks like the Loadout screen and refuses what the budget does not cover: T4
    /// armor with the best ammo, with any gun; the sensible middles and the default loadout go through.
    #[test]
    fn the_host_holds_every_loadout_to_the_points() {
        let d = GameData::embedded();
        let std = AmmoChoice::STANDARD;
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let rip3 = AmmoChoice { kind: AmmoKind::Rip, tier: 3 };
        for mode in MatchMode::ALL {
            assert!(super::loadout_from_choice(&d, &default_choice(&d), mode).is_ok(), "{mode:?}: the default");
        }
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            let budget = gear_budget(&d, mode).unwrap();
            let host = |c: &LoadoutChoice| super::loadout_from_choice(&d, c, mode);
            let over =
                |c: &LoadoutChoice| matches!(host(c), Err(LoadoutError::OverBudget { budget: b, .. }) if b == budget);
            for gun in ["ar7_mako", "vk50_warden", "sk9_skink"] {
                assert!(over(&picks(gun, 4, ap(3), &[])), "{mode:?} {gun}: T4 + AP III");
                for tier in 1..=4 {
                    assert!(host(&picks(gun, tier, std, &[])).is_ok(), "{mode:?} {gun}: T{tier} + STD");
                }
            }
            assert!(over(&picks("sk9_skink", 4, rip3, &[])), "T4 + RIP III");
            assert!(host(&picks("ar7_mako", 4, std, &["mag_drum60"])).is_ok(), "T4 + STD + the drum");
            assert!(host(&picks("ar7_mako", 3, ap(3), &["mag_45"])).is_ok(), "T3 + AP III + extended");
            assert!(host(&picks("ar7_mako", 2, ap(3), &["mag_drum60"])).is_ok(), "T2 + AP III + the drum");
            assert!(over(&picks("ar7_mako", 3, ap(3), &["mag_drum60"])), "T3 + AP III + the drum");
            assert!(over(&picks("ar7_mako", 4, ap(2), &["mag_drum60"])), "T4 + AP II + the drum");
            // the magazine type is the one asked for, six of it, and the points add up to the budget
            let c = picks("ar7_mako", 2, ap(3), &["mag_drum60"]);
            let l = host(&c).unwrap();
            assert_eq!((l.weapon.mag_capacity, l.weapon.mags.len()), (60, 6));
            let spec = l.weapon.spec(&d);
            assert_eq!(loadout_cost(&d, mode, spec, &c.halo, &c.mags, &c.attachments).total(), budget);
        }
    }

    /// A client cannot ask a deathmatch for more than its picks: another halo core, a halo that is no armor
    /// tier, a mix of ammo or fewer magazines are shaped to the picks before the checks (a loadout from an
    /// older build becomes its nearest picks), and what the picks cost is what the budget sees.
    #[test]
    fn deathmatch_loadouts_are_shaped_to_their_picks_before_the_checks() {
        let d = GameData::embedded();
        let ap2 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 };
        let rip3 = AmmoChoice { kind: AmmoKind::Rip, tier: 3 };
        let mut rich = mags("sk9_skink", &[ap2, AmmoChoice::STANDARD, rip3, ap2], "arm_none");
        rich.halo = HaloChoice { core: Core::Phase, tiers: ZoneTable { head: 2, torso: 2, arms: 0, legs: 0 } };
        for mode in [MatchMode::Tdm, MatchMode::Ffa] {
            let kit = d.rules.fixed_loadout(mode).unwrap();
            let l = super::loadout_from_choice(&d, &rich, mode).unwrap();
            assert_eq!(l.weapon.mags.len(), kit.mags as usize, "{mode:?}: six magazines");
            assert!(l.weapon.mags.iter().all(|m| m.choice == ap2), "{mode:?}: slot 1's ammo everywhere");
            assert_eq!(l.halo.core, Some(kit.halo_core), "{mode:?}: no Phase core (immune to slows)");
            assert_eq!(l.halo.tiers, kit.armor[1].tiers, "{mode:?}: H2 T2 is armor T2");
            // no magazine at all, or seven: refused, as everywhere
            for odd in [vec![], vec![AmmoChoice::STANDARD; 7]] {
                let c = mags("ar7_mako", &odd, "arm_none");
                assert_eq!(super::loadout_from_choice(&d, &c, mode).err(), Some(LoadoutError::MagCount));
            }
        }
        // the gun range takes the loadout as asked
        let l = super::loadout_from_choice(&d, &rich, MatchMode::Range).unwrap();
        assert_eq!((l.weapon.mags.len(), l.halo.core), (4, Some(Core::Phase)));
    }

    #[test]
    fn magazine_count_is_one_to_six_in_the_range() {
        let d = GameData::embedded();
        let std = AmmoChoice::STANDARD;
        let range = |m: &[AmmoChoice]| {
            super::loadout_from_choice(&d, &mags("ar7_mako", m, "arm_none"), MatchMode::Range)
                .map(|l| l.weapon.mags.len())
        };
        assert_eq!(range(&[]), Err(LoadoutError::MagCount));
        assert_eq!(range(&[std; 7]), Err(LoadoutError::MagCount));
        assert_eq!(range(&[std; 6]), Ok(6));
    }

    #[test]
    fn npc_and_wrong_class_ammo_are_refused() {
        let d = GameData::embedded();
        let shr = AmmoChoice { kind: AmmoKind::Shrapnel, tier: 1 };
        let rip = AmmoChoice { kind: AmmoKind::Rip, tier: 1 };
        assert_eq!(loadout_from_choice(&d, &choice("ar7_mako", shr, "arm_none")).err(), Some(LoadoutError::Ammo));
        assert_eq!(loadout_from_choice(&d, &choice("ar7_mako", rip, "arm_none")).err(), Some(LoadoutError::Ammo));
        // in the range one bad magazine refuses the whole loadout; a deathmatch only takes slot 1's ammo
        let one_bad = mags("ar7_mako", &[AmmoChoice::STANDARD, shr], "arm_none");
        assert_eq!(super::loadout_from_choice(&d, &one_bad, MatchMode::Range).err(), Some(LoadoutError::Ammo));
        assert!(loadout_from_choice(&d, &one_bad).is_ok());
        let bad_first = mags("ar7_mako", &[shr, AmmoChoice::STANDARD], "arm_none");
        assert_eq!(loadout_from_choice(&d, &bad_first).err(), Some(LoadoutError::Ammo));
        assert_eq!(
            loadout_from_choice(&d, &choice("nope", AmmoChoice::STANDARD, "arm_none")).err(),
            Some(LoadoutError::UnknownWeapon)
        );
    }

    /// Agents are dealt from the pool by the match's seed and the player: the same seed deals the same, and
    /// over many players every agent turns up about as often.
    #[test]
    fn agents_are_dealt_at_random_but_repeatably() {
        let pool: Vec<String> = ["kestrel", "solace"].map(String::from).to_vec();
        assert_eq!(deal_agent(&pool, 7, 3), deal_agent(&pool, 7, 3));
        let kestrels = (0..1000).filter(|p| deal_agent(&pool, 7, *p).map(|a| a.as_str()) == Some("kestrel")).count();
        assert!((420..580).contains(&kestrels), "{kestrels}");
        let seeds = (0..64).filter(|s| deal_agent(&pool, *s, 3) != deal_agent(&pool, 0, 3)).count();
        assert!(seeds > 10, "another match deals again ({seeds})");
        assert_eq!(deal_agent(&[], 7, 3), None);
        assert_eq!(deal_agent(&pool[..1], 7, 3).map(|a| a.as_str()), Some("kestrel"));
    }

    #[test]
    fn bypass_rolls_are_deterministic_and_spread() {
        assert_eq!(bypass_roll(7, 3, 9), bypass_roll(7, 3, 9));
        let under = (0..1000).filter(|i| bypass_roll(7, *i, 9) < 0.2).count();
        assert!((150..250).contains(&under), "{under}");
    }
}
