//! Host authority: player spawns, the authoritative simulation, shot-claim validation, damage, deaths,
//! respawns and team-deathmatch rules. Runs only while hosting.

use crate::config::{CurrentLevel, Data};
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
use vetf_sim::data::Core;
use vetf_sim::hitbox::{FiredShot, Pose, PoseHistory, Verdict, validate_claim};
use vetf_sim::input::view_dir;
use vetf_sim::level::{Level, SpawnPoint, Team};
use vetf_sim::movement::MoveState;
use vetf_sim::player::{self, Loadout, Wounds};
use vetf_sim::weapon::{WeaponLoadout, WeaponState, shot_direction, shot_seed};

pub struct ServerPlugin;

impl Plugin for ServerPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<PendingClaims>()
            .add_message::<PlayerDied>()
            .add_observer(on_new_link)
            .add_observer(on_link_connected)
            .add_systems(Update, (receive_hellos, receive_claims).run_if(is_hosting))
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

pub fn spawn_match(commands: &mut Commands, data: &GameData, map: &str) {
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
            phase: MatchPhase::Live,
        },
        Replicate::to_clients(NetworkTarget::All),
    ));
}

/// Every new link (remote clients and the host's own) needs a replication sender.
fn on_new_link(trigger: On<Add, LinkOf>, mut commands: Commands) {
    commands.entity(trigger.entity).insert(ReplicationSender);
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
    let loadout = Loadout::default_for(&data);
    let id = peer.to_bits();
    let player = commands
        .spawn((
            Name::new(format!("Player {id:x}")),
            PlayerId(id),
            PlayerInfo { name: if peer.is_local() { session.local_name.clone() } else { "AGENT".into() }, team },
            PlayerMove(MoveState::spawn(spawn.pos, loadout_fuel(&data, &loadout))),
            PlayerLook { yaw: spawn.yaw, pitch: 0.0 },
            PlayerWeapon(WeaponState::new(&data, &loadout.weapon)),
            fresh_vitals(&data, &loadout),
            PlayerLoadout(loadout),
            Score::default(),
            ServerPlayer {
                link: trigger.entity,
                peer,
                history: PoseHistory::default(),
                shots: VecDeque::new(),
                choice: None,
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

/// Build a loadout from a client's choice, with the loadout tier caps applied to the halo arcs.
fn loadout_from_choice(data: &GameData, choice: &LoadoutChoice) -> Option<Loadout> {
    let weapon = WeaponLoadout::resolve(
        data,
        &choice.weapon,
        choice.ammo,
        &choice.attachments,
        data.rules.default_loadout.spare_mags,
    )?;
    let mut preset = data.armor.preset(&choice.armor)?.clone();
    let caps = data.armor.loadout_tier_caps;
    preset.tiers = preset.tiers.map(|z, t| (*t).min(caps[z]));
    Some(Loadout::new(weapon, &data.armor.resolve(&preset)))
}

fn receive_hellos(
    mut links: Query<(Entity, &mut MessageReceiver<Hello>), With<ClientOf>>,
    mut players: Query<(
        &mut PlayerInfo,
        &mut ServerPlayer,
        &mut PlayerLoadout,
        &mut PlayerWeapon,
        &mut Vitals,
        &mut PlayerMove,
    )>,
    data: Res<Data>,
) {
    for (link, mut rx) in &mut links {
        for hello in rx.receive() {
            if hello.data_fingerprint != data.fingerprint {
                warn!("{} runs different gameplay data: prediction will drift", hello.name);
            }
            for (mut info, mut sp, mut lo, mut w, mut v, mut mv) in &mut players {
                if sp.link != link {
                    continue;
                }
                info.name = hello.name.chars().filter(|c| !c.is_control()).take(16).collect();
                let chosen = loadout_from_choice(&data, &hello.loadout);
                if chosen.is_none() {
                    warn!("{}: loadout {:?} is invalid; keeping the default", hello.name, hello.loadout);
                }
                if let Some(l) = chosen {
                    *w = PlayerWeapon(WeaponState::new(&data, &l.weapon));
                    *v = fresh_vitals(&data, &l);
                    mv.0.fuel = loadout_fuel(&data, &l);
                    *lo = PlayerLoadout(l);
                }
                sp.choice = Some(hello.loadout.clone());
            }
        }
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
            &PlayerLoadout,
            &mut Vitals,
            &mut PlayerLook,
            &mut ServerPlayer,
            Has<Controlled>,
        ),
        With<Replicate>,
    >,
    server: Query<&Server>,
    mut fx: ServerMultiMessageSender,
    mut local_shots: MessageWriter<LocalShot>,
    mut deaths: MessageWriter<PlayerDied>,
) {
    let Some(level) = level else { return };
    let tick = timeline.tick().0;
    let dt = data.tick_dt();
    let keep = (data.combat.shot_validation.history_s * data.net.tick_hz as f32).ceil() as u32;
    let server = server.iter().next();
    for (entity, id, input, mut mv, mut weapon, loadout, mut vitals, mut look, mut sp, local) in &mut players {
        if vitals.health.dead {
            continue;
        }
        let frame = input.map(|a| a.0.frame().sanitized()).unwrap_or_default();
        look.yaw = frame.yaw;
        look.pitch = frame.pitch;
        let mut wounds = vitals.wounds;
        let ev = player::step(&data, &level, &loadout.0, &mut mv.0, &mut weapon.0, &mut wounds, &frame);
        vitals.wounds = wounds;
        vitals.protected_s = (vitals.protected_s - dt).max(0.0);
        let spec = loadout.0.halo;
        vitals.halo.tick(&spec, dt);

        if ev.movement.fall_damage > 0.0 {
            let hp = vitals.health.apply(Zone::Legs, ev.movement.fall_damage, &data.weapons.spill_to_torso);
            vitals.wounds.broken = vitals.health.broken();
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
            });
            while sp.shots.len() > 64 {
                sp.shots.pop_front();
            }
            let dir = shot_direction(frame.yaw, frame.pitch, shot.spread_deg, shot_seed(id.0, shot.seq));
            let range = loadout.0.weapon.spec(&data).max_range_m;
            let end = origin + dir * level.world.raycast(origin, dir, range).map_or(range, |(d, _)| d);
            if let Some(server) = server {
                let msg = ShotFx { shooter: id.0, origin, end };
                if let Err(e) = fx.send::<_, FxChannel>(&msg, server, &NetworkTarget::AllExceptSingle(sp.peer)) {
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
    mut players: Query<(Entity, &PlayerId, &PlayerInfo, &PlayerLoadout, &mut Vitals, &PlayerMove, &ServerPlayer)>,
    mut confirms: Query<&mut MessageSender<HitConfirm>>,
    mut damage: Query<&mut MessageSender<DamageTaken>>,
    mut deaths: MessageWriter<PlayerDied>,
) {
    let Some(level) = level else { return };
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
        let Ok((_, _, vinfo, vloadout, mut vitals, vmove, vsp)) = players.get_mut(victim_e) else { continue };
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
            &shooter.loadout.weapon.ammo,
            range,
            zone,
            &data.weapons.spill_to_torso,
            &halo_spec,
            &mut halo,
            &mut health,
        );
        vitals.halo = halo;
        vitals.health = health;
        vitals.wounds.broken = health.broken();
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
    mut matches: Query<&mut MatchState>,
    server: Query<&Server>,
    mut feed: ServerMultiMessageSender,
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
            }
        }
        if let Some(server) = server.iter().next() {
            let msg = KillFeed { killer: killer_id, victim: victim_id, zone: d.zone };
            if let Err(e) = feed.send::<_, ReliableChannel>(&msg, server, &NetworkTarget::All) {
                warn!("kill feed not sent: {e:?}");
            }
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
        &mut PlayerLoadout,
        &mut ServerPlayer,
    )>,
) {
    let Some(level) = level else { return };
    let dt = data.tick_dt();
    let living: Vec<(Option<Team>, Vec3)> =
        players.iter().filter(|(_, v, ..)| !v.health.dead).map(|(i, _, m, ..)| (i.team, m.0.pos)).collect();
    for (info, mut v, mut mv, mut look, mut w, mut lo, mut sp) in &mut players {
        if !v.health.dead {
            continue;
        }
        v.respawn_s -= dt;
        if v.respawn_s > 0.0 {
            continue;
        }
        if let Some(l) = sp.choice.as_ref().and_then(|c| loadout_from_choice(&data, c)) {
            lo.0 = l;
        }
        let enemies: Vec<Vec3> =
            living.iter().filter(|(t, _)| t.is_none() || *t != info.team).map(|(_, p)| *p).collect();
        let spawn = pick_spawn(&level, info.team, &enemies);
        *v = fresh_vitals(&data, &lo.0);
        mv.0 = MoveState::spawn(spawn.pos, loadout_fuel(&data, &lo.0));
        *look = PlayerLook { yaw: spawn.yaw, pitch: 0.0 };
        w.0 = WeaponState::new(&data, &lo.0.weapon);
        sp.history.clear();
        sp.shots.clear();
    }
}

fn run_match(
    data: Res<Data>,
    mut matches: Query<&mut MatchState>,
    mut players: Query<(&mut Vitals, &mut Score)>,
    mut intermission: Local<f32>,
) {
    let Some(mut m) = matches.iter_mut().next() else { return };
    if m.mode != MatchMode::Tdm {
        return;
    }
    let dt = data.tick_dt();
    match m.phase {
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
                m.score_a = 0;
                m.score_b = 0;
                m.time_left_s = data.rules.tdm.time_limit_s;
                m.phase = MatchPhase::Live;
                for (mut v, mut s) in &mut players {
                    *s = Score::default();
                    v.health.dead = true;
                    v.respawn_s = 0.0;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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

    #[test]
    fn loadout_choice_caps_leg_tier() {
        let d = GameData::embedded();
        let choice = LoadoutChoice {
            weapon: "ar7_mako".into(),
            ammo: vetf_sim::data::AmmoChoice::STANDARD,
            attachments: vec![],
            armor: "arm_bulwark_jugg".into(),
        };
        let l = loadout_from_choice(&d, &choice).unwrap();
        assert_eq!(l.halo.tiers.legs, d.armor.loadout_tier_caps.legs);
        assert_eq!(l.halo.tiers.torso, 4);
    }
}
