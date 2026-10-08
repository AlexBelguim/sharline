//! Host authority: player spawns, the authoritative simulation, shot-claim validation, damage, deaths,
//! respawns and team-deathmatch rules. Runs only while hosting.

use crate::config::{Cli, CurrentLevel, Data};
use crate::net::{Role, Session};
use crate::shared::{LocalShot, SimSystems};
use bevy::prelude::*;
use lightyear::prelude::input::native::ActionState;
use lightyear::prelude::server::*;
use lightyear::prelude::*;
use std::collections::VecDeque;
use vetf_net::*;
use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::combat::{HaloState, Health, resolve_hit};
use vetf_sim::data::{Core, Ruleset};
use vetf_sim::gear::{gear_budget, gear_cost};
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
                )
                    .run_if(is_hosting),
            )
            .add_systems(FixedUpdate, simulate_authoritative.in_set(SimSystems::Simulate).run_if(is_hosting))
            .add_systems(
                FixedUpdate,
                (resolve_claims, handle_deaths, respawn_players, run_match)
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

/// The match entity. A team deathmatch starts in the lobby unless `lobby` is false (`--live`); the range
/// is always live.
pub fn spawn_match(
    commands: &mut Commands,
    data: &GameData,
    map: &str,
    lobby_name: String,
    max_players: u32,
    lobby: bool,
) {
    let range = map.eq_ignore_ascii_case("range");
    commands.spawn((
        Name::new("Match"),
        MatchState {
            mode: if range { MatchMode::Range } else { MatchMode::Tdm },
            map: map.to_lowercase(),
            score_a: 0,
            score_b: 0,
            score_limit: data.rules.tdm.score_limit,
            time_left_s: data.rules.tdm.time_limit_s,
            phase: if lobby && !range { MatchPhase::Lobby } else { MatchPhase::Live },
            lobby_name,
            max_players,
            rules: if range { data.rules.rulesets.range } else { data.rules.rulesets.tdm },
        },
        Replicate::to_clients(NetworkTarget::All),
        // A session that ends must not leave its mode and rules to the next one.
        DespawnOnEnter(crate::AppState::MainMenu),
    ));
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
    // The match entity may not exist yet when the host's own client connects; the level decides.
    let tdm =
        !level.name.eq_ignore_ascii_case("range") && matches.iter().next().is_none_or(|m| m.mode == MatchMode::Tdm);
    let team = tdm.then(|| {
        let a = players.iter().filter(|(i, _, _)| i.team == Some(Team::A)).count();
        let b = players.iter().filter(|(i, _, _)| i.team == Some(Team::B)).count();
        if a <= b { Team::A } else { Team::B }
    });
    let enemies: Vec<Vec3> = players
        .iter()
        .filter(|(i, _, _)| i.team != team || team.is_none())
        .filter(|(_, _, v)| !v.health.dead)
        .map(|(_, m, _)| m.0.pos)
        .collect();
    let spawn = pick_spawn(&level, team, &enemies);
    let mode = if tdm { MatchMode::Tdm } else { MatchMode::Range };
    let loadout = Loadout::default_for(&data, mode);
    let id = peer.to_bits();
    let player = commands
        .spawn((
            Name::new(format!("Player {id:x}")),
            PlayerId(id),
            PlayerInfo { name: if peer.is_local() { session.local_name.clone() } else { "AGENT".into() }, team },
            PlayerMove(MoveState::spawn(spawn.pos, loadout_fuel(&data, &loadout))),
            PlayerLook { yaw: spawn.yaw, pitch: 0.0 },
            PlayerWeapon(WeaponState::new(&data, &loadout.weapon)),
            PlayerItems(ItemState::new(&loadout.kit)),
            fresh_vitals(&data, &loadout),
            PlayerLoadout(loadout),
            Score::default(),
            PlayerNet::default(),
            ServerPlayer {
                link: trigger.entity,
                peer,
                history: PoseHistory::default(),
                shots: VecDeque::new(),
                choice: None,
                last_attacker: None,
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

fn loadout_fuel(data: &GameData, l: &Loadout) -> f32 {
    data.movement.jetpack.fuel_s * data.armor.effects(l.weight).fuel
}

fn fresh_vitals(data: &GameData, l: &Loadout) -> Vitals {
    Vitals {
        health: Health::new(data.armor.zone_hp),
        halo: HaloState::full(&l.halo),
        wounds: Wounds::default(),
        respawn_s: 0.0,
        protected_s: data.rules.tdm.spawn_protection_s,
    }
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
    /// A halo arc above its loadout tier cap.
    TierCap,
    /// A magazine's ammo cannot be loaded by that gun, or it is NPC-only.
    Ammo,
    /// No magazines, or more than six.
    MagCount,
    /// Halo arc tiers plus the magazines' gear cost exceed the mode's gear budget.
    OverBudget {
        cost: u32,
        budget: u32,
    },
}

/// Build a loadout from a client's choice (the Loadout screen checks the same rules before CONFIRM):
/// attachments that fit the gun (one per category), halo arcs within the loadout tier caps, players' ammo
/// only, one to six magazines, and the mode's gear budget (arc tiers + every magazine's gear cost, see
/// `vetf_sim::gear`; the gun range has none). The healing kit comes from the mode, not the client.
pub fn loadout_from_choice(data: &GameData, choice: &LoadoutChoice, mode: MatchMode) -> Result<Loadout, LoadoutError> {
    let spec = data.weapon(&choice.weapon).ok_or(LoadoutError::UnknownWeapon)?;
    if choice.mags.is_empty() || choice.mags.len() > MAX_MAGS {
        return Err(LoadoutError::MagCount);
    }
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
    if !choice.halo.within_caps(data.armor.loadout_tier_caps) {
        return Err(LoadoutError::TierCap);
    }
    let weapon = WeaponLoadout::resolve(data, &choice.weapon, &choice.mags, &choice.attachments)
        .ok_or(LoadoutError::UnknownWeapon)?;
    let cost = gear_cost(data, spec, &choice.halo, &choice.mags).total();
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
            for (mut info, mut sp, mut lo, mut w, mut it, mut v, mut mv) in &mut players {
                if sp.link != link {
                    continue;
                }
                info.name = hello.name.chars().filter(|c| !c.is_control()).take(16).collect();
                let chosen = loadout_from_choice(&data, &hello.loadout, mode);
                if let Err(e) = &chosen {
                    warn!("{}: loadout {:?} refused ({e:?}); keeping the default", hello.name, hello.loadout);
                }
                if let Ok(l) = chosen {
                    *w = PlayerWeapon(WeaponState::new(&data, &l.weapon));
                    *it = PlayerItems(ItemState::new(&l.kit));
                    *v = fresh_vitals(&data, &l);
                    mv.0.fuel = loadout_fuel(&data, &l);
                    *lo = PlayerLoadout(l);
                    // Kept for every respawn (a LoadoutUpdate replaces it).
                    sp.choice = Some(hello.loadout.clone());
                }
            }
        }
    }
}

/// A player changed their loadout on the Loadout screen during the match: check it now, apply it at their
/// next spawn (the current life keeps its gear).
fn receive_loadout_updates(
    mut links: Query<(Entity, &mut MessageReceiver<LoadoutUpdate>), With<ClientOf>>,
    mut players: Query<(&PlayerInfo, &mut ServerPlayer)>,
    matches: Query<&MatchState>,
    data: Res<Data>,
) {
    let mode = match_mode(&matches);
    for (link, mut rx) in &mut links {
        for update in rx.receive() {
            for (info, mut sp) in &mut players {
                if sp.link != link {
                    continue;
                }
                match loadout_from_choice(&data, &update.loadout, mode) {
                    Ok(_) => {
                        info!("{}: new loadout for the next spawn", info.name);
                        sp.choice = Some(update.loadout.clone());
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
                LobbyAction::SwitchTeam => {
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
                    if players.iter().any(|p| p.4.link == link && p.4.peer.is_local()) {
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

/// A fresh match (in `phase`, if given): scores, the deathmatch clock, everyone's score and READY, and
/// everyone respawns on the next tick. Also the host's RESTART MATCH / BACK TO LOBBY (`esc_menu.rs`).
pub(crate) fn reset_match<'a>(
    m: &mut MatchState,
    data: &GameData,
    phase: Option<MatchPhase>,
    players: impl Iterator<Item = (Mut<'a, PlayerNet>, Mut<'a, Vitals>, Mut<'a, Score>)>,
) {
    m.score_a = 0;
    m.score_b = 0;
    if m.mode == MatchMode::Tdm {
        m.time_left_s = data.rules.tdm.time_limit_s;
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
    // No damage in the lobby (bots, a held trigger): claims are dropped.
    if matches.iter().next().is_some_and(|m| m.phase == MatchPhase::Lobby) {
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
            || (shooter.team.is_some() && shooter.team == vinfo.team)
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
            });
        }
        if let Ok(mut s) = damage.get_mut(victim_link) {
            s.send::<ReliableChannel>(DamageTaken { from: shooter.shot.origin, zone, shield: report.hit_shield() });
        }
        if report.killed {
            deaths.write(PlayerDied { victim: victim_e, killer: Some(shooter.entity), zone: Some(zone) });
        }
        // Volt core: a breaking arc shocks the victim's enemies nearby.
        if report.shield_broke && halo_spec.core == Some(Core::Volt) {
            let pulse = &data.combat.volt_pulse;
            let victim_team = vinfo.team;
            for (_, _, info, _, mut v, m, _) in &mut players {
                if info.team != victim_team && m.0.pos.distance(victim_pos) <= pulse.radius_m {
                    v.wounds.volt_slow_s = pulse.duration_s;
                }
            }
        }
    }
    pending.0 = keep;
}

#[allow(clippy::too_many_arguments)]
fn handle_deaths(
    data: Res<Data>,
    mut died: MessageReader<PlayerDied>,
    mut players: Query<(&PlayerId, &PlayerInfo, &mut Vitals, &mut Score, &mut PlayerMove)>,
    mut weapons: Query<(&mut PlayerWeapon, &PlayerLoadout)>,
    mut matches: Query<&mut MatchState>,
    mut feed: ClientLinks<KillFeed>,
) {
    for d in died.read() {
        let Ok((vid, vinfo, mut v, mut score, mut mv)) = players.get_mut(d.victim) else { continue };
        v.health.dead = true;
        v.respawn_s = data.rules.tdm.respawn_s;
        score.deaths += 1;
        mv.0.vel = Vec3::ZERO;
        let (victim_id, victim_team) = (vid.0, vinfo.team);
        let mut killer_id = None;
        if let Some(k) = d.killer.filter(|k| *k != d.victim)
            && let Ok((kid, kinfo, _, mut kscore, _)) = players.get_mut(k)
        {
            kscore.kills += 1;
            killer_id = Some(kid.0);
            if let Some(mut m) = matches.iter_mut().next()
                && m.mode == MatchMode::Tdm
                && m.phase == MatchPhase::Live
                && kinfo.team != victim_team
            {
                match kinfo.team {
                    Some(Team::A) => m.score_a += 1,
                    Some(Team::B) => m.score_b += 1,
                    None => {}
                }
                // Every kill tops up a magazine (user direction), so a good run keeps going.
                if let Ok((mut w, l)) = weapons.get_mut(k) {
                    w.0.refill_mags(data.rules.tdm.kill_refill_mags, l.0.weapon.mag_capacity);
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

#[allow(clippy::type_complexity)]
fn respawn_players(
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    mut players: Query<(
        &PlayerInfo,
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
    let living: Vec<(Option<Team>, Vec3)> =
        players.iter().filter(|(_, v, ..)| !v.health.dead).map(|(i, _, m, ..)| (i.team, m.0.pos)).collect();
    for (info, mut v, mut mv, mut look, mut w, mut it, mut lo, mut sp) in &mut players {
        if !v.health.dead {
            continue;
        }
        v.respawn_s -= dt;
        if v.respawn_s > 0.0 {
            continue;
        }
        if let Some(l) = sp.choice.as_ref().and_then(|c| loadout_from_choice(&data, c, mode).ok()) {
            lo.0 = l;
        }
        let enemies: Vec<Vec3> =
            living.iter().filter(|(t, _)| t.is_none() || *t != info.team).map(|(_, p)| *p).collect();
        let spawn = pick_spawn(&level, info.team, &enemies);
        *v = fresh_vitals(&data, &lo.0);
        mv.0 = MoveState::spawn(spawn.pos, loadout_fuel(&data, &lo.0));
        *look = PlayerLook { yaw: spawn.yaw, pitch: 0.0 };
        w.0 = WeaponState::new(&data, &lo.0.weapon);
        it.0 = ItemState::new(&lo.0.kit);
        sp.history.clear();
        sp.shots.clear();
        sp.last_attacker = None;
    }
}

fn run_match(
    data: Res<Data>,
    mut matches: Query<&mut MatchState>,
    mut players: Query<(&mut PlayerNet, &mut Vitals, &mut Score)>,
    mut intermission: Local<f32>,
) {
    let Some(mut m) = matches.iter_mut().next() else { return };
    if m.mode != MatchMode::Tdm {
        return;
    }
    let dt = data.tick_dt();
    match m.phase {
        // The clock waits for the host's START MATCH.
        MatchPhase::Lobby => {}
        MatchPhase::Live => {
            m.time_left_s = (m.time_left_s - dt).max(0.0);
            let limit = m.score_limit;
            if m.score_a >= limit || m.score_b >= limit || m.time_left_s <= 0.0 {
                let winner = match m.score_a.cmp(&m.score_b) {
                    std::cmp::Ordering::Greater => Some(Team::A),
                    std::cmp::Ordering::Less => Some(Team::B),
                    std::cmp::Ordering::Equal => None,
                };
                m.phase = MatchPhase::Ended { winner };
                *intermission = INTERMISSION_S;
                info!("match over: {winner:?} wins {}-{}", m.score_a, m.score_b);
            }
        }
        MatchPhase::Ended { .. } => {
            *intermission -= dt;
            if *intermission <= 0.0 {
                // Back to the lobby: teams, loadouts and READY for the next one.
                reset_match(&mut m, &data, Some(MatchPhase::Lobby), players.iter_mut());
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::ZoneTable;
    use vetf_sim::data::{AmmoChoice, AmmoKind};
    use vetf_sim::gear::HaloChoice;

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

    #[test]
    fn halo_arcs_must_stay_within_the_tier_caps() {
        let mut d = GameData::embedded();
        d.rules.tdm.gear_budget = 100; // only the caps matter here
        let capped = choice("ar7_mako", AmmoChoice::STANDARD, "arm_bulwark_jugg");
        let l = loadout_from_choice(&d, &capped).unwrap();
        assert_eq!(l.halo.tiers.legs, d.armor.loadout_tier_caps.legs);
        assert_eq!(l.halo.tiers.torso, 4);
        // the uncapped rare-loot halo is refused, not silently capped
        let raw = LoadoutChoice {
            halo: HaloChoice::from_preset(d.armor.preset("arm_bulwark_jugg").unwrap()),
            ..capped.clone()
        };
        assert_eq!(loadout_from_choice(&d, &raw).err(), Some(LoadoutError::TierCap));
    }

    #[test]
    fn a_custom_mixed_tier_halo_is_resolved_per_arc() {
        let d = GameData::embedded();
        let mut c = choice("ar7_mako", AmmoChoice::STANDARD, "arm_none");
        c.halo = HaloChoice { core: Core::Volt, tiers: ZoneTable { head: 1, torso: 3, arms: 0, legs: 2 } };
        let l = loadout_from_choice(&d, &c).unwrap();
        assert_eq!(l.halo.tiers, c.halo.tiers);
        assert_eq!(l.halo.core, Some(Core::Volt));
        assert_eq!(l.weight, d.armor.weight_class(6));
        // no arcs: no halo, whatever the core
        c.halo.tiers = ZoneTable::splat(0);
        let l = loadout_from_choice(&d, &c).unwrap();
        assert_eq!((l.halo.core, l.weight), (None, vetf_sim::data::WeightClass::None));
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
        c.attachments = vec!["nope".into()];
        assert_eq!(loadout_from_choice(&d, &c).err(), Some(LoadoutError::Attachment));
    }

    #[test]
    fn the_gun_range_has_no_gear_budget() {
        let d = GameData::embedded();
        let ap3 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 };
        let c = mags("ar7_mako", &[ap3; 6], "arm_bulwark_assault");
        assert!(matches!(loadout_from_choice(&d, &c), Err(LoadoutError::OverBudget { .. })));
        assert!(super::loadout_from_choice(&d, &c, MatchMode::Range).is_ok());
    }

    #[test]
    fn gear_budget_prices_armor_and_each_magazine() {
        let d = GameData::embedded();
        let std = AmmoChoice::STANDARD;
        let ap1 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 1 };
        let ap3 = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 };
        let budget = d.rules.tdm.gear_budget;
        // the default loadout fits
        let def = &d.rules.default_loadout;
        assert!(loadout_from_choice(&d, &mags(&def.primary, &def.mags, &def.armor)).is_ok());
        // the host prices a loadout exactly like the Loadout screen's RESULT panel (the shared function)
        let c = mags("ar7_mako", &[ap1, ap3], "arm_mender_scout");
        let shared = gear_cost(&d, d.weapon("ar7_mako").unwrap(), &c.halo, &c.mags).total();
        assert_eq!(shared, 4 + d.ammo.resolve(vetf_sim::data::WeaponClass::AssaultRifle, ap3).unwrap().gear_cost + 2);
        // every magazine is priced: one AP mag costs its tier's price, two cost twice that
        let price = |m: &[AmmoChoice]| match loadout_from_choice(&d, &mags("ar7_mako", m, "arm_none")) {
            Ok(l) => l.weapon.ammo_gear_cost(),
            Err(LoadoutError::OverBudget { cost, .. }) => cost,
            Err(e) => panic!("{e:?}"),
        };
        let one = d.ammo.resolve(vetf_sim::data::WeaponClass::AssaultRifle, ap1).unwrap().gear_cost;
        assert_eq!(price(&[std, std, ap1]), one);
        assert_eq!(price(&[std, ap1, ap1]), 2 * one);
        // a full pouch of AP III is over budget even with no halo; one AP III mag with a light halo fits
        let all_ap3 = loadout_from_choice(&d, &mags("ar7_mako", &[ap3; 6], "arm_none"));
        assert!(matches!(all_ap3, Err(LoadoutError::OverBudget { budget: b, .. }) if b == budget), "{all_ap3:?}");
        assert!(loadout_from_choice(&d, &mags("ar7_mako", &[std, std, std, ap3], "arm_phase_runner")).is_ok());
    }

    #[test]
    fn magazine_count_is_one_to_six() {
        let d = GameData::embedded();
        let std = AmmoChoice::STANDARD;
        assert_eq!(loadout_from_choice(&d, &mags("ar7_mako", &[], "arm_none")).err(), Some(LoadoutError::MagCount));
        assert_eq!(
            loadout_from_choice(&d, &mags("ar7_mako", &[std; 7], "arm_none")).err(),
            Some(LoadoutError::MagCount)
        );
        assert_eq!(loadout_from_choice(&d, &mags("ar7_mako", &[std; 6], "arm_none")).unwrap().weapon.mags.len(), 6);
    }

    #[test]
    fn npc_and_wrong_class_ammo_are_refused() {
        let d = GameData::embedded();
        let shr = AmmoChoice { kind: AmmoKind::Shrapnel, tier: 1 };
        let rip = AmmoChoice { kind: AmmoKind::Rip, tier: 1 };
        assert_eq!(loadout_from_choice(&d, &choice("ar7_mako", shr, "arm_none")).err(), Some(LoadoutError::Ammo));
        assert_eq!(loadout_from_choice(&d, &choice("ar7_mako", rip, "arm_none")).err(), Some(LoadoutError::Ammo));
        // one bad magazine refuses the whole loadout
        let one_bad = mags("ar7_mako", &[AmmoChoice::STANDARD, shr], "arm_none");
        assert_eq!(loadout_from_choice(&d, &one_bad).err(), Some(LoadoutError::Ammo));
        assert_eq!(
            loadout_from_choice(&d, &choice("nope", AmmoChoice::STANDARD, "arm_none")).err(),
            Some(LoadoutError::UnknownWeapon)
        );
    }

    #[test]
    fn bypass_rolls_are_deterministic_and_spread() {
        assert_eq!(bypass_roll(7, 3, 9), bypass_roll(7, 3, 9));
        let under = (0..1000).filter(|i| bypass_roll(7, *i, 9) < 0.2).count();
        assert!((150..250).contains(&under), "{under}");
    }
}
