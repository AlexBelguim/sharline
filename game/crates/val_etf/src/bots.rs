//! Test bots for solo testing (user direction 2026-10-09: "a simple and quick bot so i can solo test, maybe add
//! bot button in the lobby screen, just a stationary that aims at my head when in sight is fine").
//!
//! A bot is a player the host simulates like its own: no client, no network link, no separate process (the
//! `--bot` option, which drives a joining client, is something else). It takes a seat (in team deathmatch on
//! the team with fewer players), plays `rules.ron`'s default loadout, spawns, dies and respawns like anyone
//! (it presses RESPAWN as soon as it may), and shows in the lobby, the kill feed, the scoreboard and the death
//! screen. Its brain (`vetf_sim::bot`) stands it still and shoots at an enemy's head it can see; its shots go
//! through `server::simulate_authoritative` and, as a claim the host makes for it, through the same shot check
//! and damage as everyone's (`server::resolve_claims`). Numbers: `game/assets/data/bots.ron`.
//!
//! The host adds and removes bots with ADD BOT / REMOVE BOT in the lobby, or `--bots N` on the command line.

use crate::config::{Cli, CurrentLevel, Data};
use crate::server::{
    ServerPlayer, free_seats, hostile, is_hosting, new_player, simulate_authoritative, spawn_for, spawn_roll,
    takes_damage,
};
use crate::shared::SimSystems;
use bevy::prelude::*;
use lightyear::prelude::*;
use vetf_net::*;
use vetf_sim::Zone;
use vetf_sim::bot::{BotBrain, BotTuning, pick_target};
use vetf_sim::hitbox::{Pose, zone_center};
use vetf_sim::input::InputFrame;
use vetf_sim::level::Team;
use vetf_sim::weapon::Shot;

pub struct BotsPlugin;

impl Plugin for BotsPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<BotRequests>()
            .insert_resource(Tuning(load_tuning()))
            .add_systems(Update, (cli_bots, apply_bot_requests).chain().run_if(is_hosting))
            .add_systems(
                FixedUpdate,
                drive_bots.in_set(SimSystems::Simulate).before(simulate_authoritative).run_if(is_hosting),
            );
    }
}

/// `bots.ron`.
#[derive(Resource, Debug, Clone)]
pub struct Tuning(pub BotTuning);

/// From the data folder (so it can be tuned without a rebuild), else the built-in copy.
fn load_tuning() -> BotTuning {
    let path = crate::config::assets_root().join("data").join("bots.ron");
    match std::fs::read_to_string(&path).map(|text| BotTuning::parse(&text)) {
        Ok(Ok(t)) => t,
        Ok(Err(e)) => {
            error!("{e}; using the built-in copy");
            BotTuning::embedded()
        }
        Err(_) => BotTuning::embedded(),
    }
}

/// The host asks for a bot more or less (ADD BOT / REMOVE BOT, `--bots N`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BotRequest {
    Add,
    Remove,
}

/// Requests waiting for [`apply_bot_requests`].
#[derive(Resource, Debug, Default)]
pub struct BotRequests(pub Vec<BotRequest>);

/// A test bot: its number (BOT 1, BOT 2, ...) and its brain.
#[derive(Component, Debug, Clone)]
pub struct Bot {
    pub n: u32,
    pub brain: BotBrain,
    /// Just (re)spawned: the brain starts over from its spawn view on the next tick.
    pub fresh: bool,
}

/// What the brain sends this tick, in place of a client's input, and the shot it fired last tick (its recoil).
#[derive(Component, Debug, Clone, Default)]
pub struct BotControl {
    pub frame: InputFrame,
    pub last_shot: Option<Shot>,
}

/// Bot `n`'s player id: far from the host's 0 and from any netcode client id in practice.
pub fn bot_id(n: u32) -> u64 {
    0xB070_0000_0000_0000 | n as u64
}

/// The lowest bot number not in use.
pub fn next_bot_number(taken: &[u32]) -> u32 {
    (1..).find(|n| !taken.contains(n)).unwrap_or(1)
}

/// The team a new bot joins: the one with fewer players (team A on a tie, as for joiners); none without teams.
pub fn bot_team(teams: bool, a: usize, b: usize) -> Option<Team> {
    teams.then_some(if a <= b { Team::A } else { Team::B })
}

/// A bot fits while the match has a free seat (bots take seats like players, so they also keep joiners out).
pub fn can_add_bot(max_players: u32, players: usize) -> bool {
    free_seats(max_players, players) > 0
}

/// The bot REMOVE BOT takes out: the last one added (the highest number).
pub fn bot_to_remove(bots: &[(Entity, u32)]) -> Option<Entity> {
    bots.iter().max_by_key(|(_, n)| *n).map(|(e, _)| *e)
}

/// `--bots N`: once the match and the host's own player are there, ask for N bots.
fn cli_bots(
    cli: Res<Cli>,
    mut done: Local<bool>,
    matches: Query<(), With<MatchState>>,
    players: Query<&ServerPlayer>,
    mut requests: ResMut<BotRequests>,
) {
    if *done || matches.is_empty() || !players.iter().any(|p| p.peer.is_local()) {
        return;
    }
    *done = true;
    if cli.bots > 0 {
        info!("--bots: adding {} bot(s)", cli.bots);
        requests.0.extend(std::iter::repeat_n(BotRequest::Add, cli.bots as usize));
    }
}

/// Add and remove bots as asked: a new bot gets a free seat (else the request is dropped), the lowest free
/// number, in team deathmatch the team with fewer players, and spawns like a joining player.
pub(crate) fn apply_bot_requests(
    mut requests: ResMut<BotRequests>,
    data: Res<Data>,
    tuning: Res<Tuning>,
    level: Option<Res<CurrentLevel>>,
    matches: Query<&MatchState>,
    players: Query<(Entity, &PlayerInfo, &PlayerMove, &Vitals), With<ServerPlayer>>,
    bots: Query<(Entity, &Bot)>,
    mut commands: Commands,
) {
    if requests.0.is_empty() {
        return;
    }
    let (Some(m), Some(level)) = (matches.iter().next(), level) else {
        requests.0.clear();
        return;
    };
    // Who holds a seat, and on which team (bots added or removed in this batch included).
    let mut seats: Vec<(Entity, Option<Team>)> = players.iter().map(|(e, i, ..)| (e, i.team)).collect();
    let mut taken: Vec<(Entity, u32)> = bots.iter().map(|(e, b)| (e, b.n)).collect();
    for request in std::mem::take(&mut requests.0) {
        match request {
            BotRequest::Add => {
                if !can_add_bot(m.max_players, seats.len()) {
                    warn!("no free seat for a bot ({} of {})", seats.len(), m.max_players);
                    continue;
                }
                let count = |t: Team| seats.iter().filter(|(_, x)| *x == Some(t)).count();
                let team = bot_team(m.has_teams(), count(Team::A), count(Team::B));
                let numbers: Vec<u32> = taken.iter().map(|(_, n)| *n).collect();
                let n = next_bot_number(&numbers);
                let enemies: Vec<Vec3> = players
                    .iter()
                    .filter(|(_, i, _, v)| hostile(team, i.team) && !v.health.dead)
                    .map(|(_, _, mv, _)| mv.0.pos)
                    .collect();
                let id = bot_id(n);
                let spawn = spawn_for(&data, &level, m.mode, team, &enemies, spawn_roll(id, seats.len() as u64, 0));
                let name = tuning.0.callsign(n);
                info!("adding {name} on team {team:?}");
                let e = commands.spawn_empty().id();
                // Its own entity stands in for the link it does not have: claims are filed under it, and the
                // messages a player's link would get (hit confirms, its death recap) find no sender and are
                // dropped.
                let sp = ServerPlayer::new(e, PeerId::Entity(id));
                commands.entity(e).insert((
                    new_player(&data, m.mode, id, PlayerInfo { name, team, bot: true }, spawn, sp),
                    Bot { n, brain: BotBrain::new(spawn.yaw, 0.0, id), fresh: true },
                    BotControl::default(),
                    Replicate::to_clients(NetworkTarget::All),
                    // Nobody predicts a bot: everyone sees it like another player.
                    InterpolationTarget::to_clients(NetworkTarget::All),
                    DisableReplicateHierarchy,
                ));
                seats.push((e, team));
                taken.push((e, n));
            }
            BotRequest::Remove => {
                let Some(e) = bot_to_remove(&taken) else { continue };
                info!("removing a bot");
                commands.entity(e).despawn();
                // Its seat frees up for the next request in this batch too.
                taken.retain(|(x, _)| *x != e);
                seats.retain(|(x, _)| *x != e);
            }
        }
    }
}

/// Each tick before the players move: every bot's input from its brain. A living bot looks for an enemy head
/// in sight (only while shots hurt: not in the lobby or once the match is over) and turns and fires at it; a
/// dead one presses RESPAWN (the host still waits for the timer). Bots are always READY.
pub(crate) fn drive_bots(
    data: Res<Data>,
    tuning: Res<Tuning>,
    level: Option<Res<CurrentLevel>>,
    matches: Query<&MatchState>,
    mut bots: Query<(
        &PlayerId,
        &PlayerInfo,
        &PlayerMove,
        &PlayerLook,
        &PlayerWeapon,
        &Vitals,
        &mut Bot,
        &mut BotControl,
        &mut ServerPlayer,
        &mut PlayerNet,
    )>,
    others: Query<(&PlayerId, &PlayerInfo, &PlayerMove, &PlayerLook, &Vitals)>,
) {
    let Some(level) = level else { return };
    let t = &tuning.0;
    let armed = matches.iter().next().is_none_or(|m| takes_damage(m.phase));
    let heads: Vec<(u64, Option<Team>, Vec3)> = others
        .iter()
        .filter(|(.., v)| !v.health.dead)
        .filter_map(|(id, info, mv, look, _)| {
            let pose = Pose { pos: mv.0.pos, yaw: look.yaw, stance: mv.0.stance };
            zone_center(&data, &pose, Zone::Head).map(|h| (id.0, info.team, h))
        })
        .collect();
    let dt = data.tick_dt();
    for (id, info, mv, look, weapon, v, mut bot, mut ctl, mut sp, mut net) in &mut bots {
        if !net.ready {
            net.ready = true;
        }
        if v.health.dead {
            sp.respawn_asked = true;
            bot.fresh = true;
            *ctl = BotControl::default();
            continue;
        }
        if bot.fresh {
            bot.fresh = false;
            bot.brain = BotBrain::new(look.yaw, look.pitch, id.0);
            ctl.last_shot = None;
        }
        if let Some(shot) = ctl.last_shot.take() {
            bot.brain.on_shot(t, &shot);
        }
        let eye = mv.0.eye_pos();
        let enemies =
            heads.iter().filter(|(e, team, _)| *e != id.0 && hostile(info.team, *team)).map(|(e, _, h)| (*e, *h));
        let seen = if armed { pick_target(t, &level.world, eye, enemies, bot.brain.target) } else { None };
        ctl.frame = bot.brain.think(t, eye, seen, &weapon.0, dt);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The lobby's seat rules for bots: a free seat, the lowest free number, the smaller team, the last one
    /// out first.
    #[test]
    fn bots_take_free_seats_on_the_smaller_team() {
        assert!(can_add_bot(10, 1));
        assert!(can_add_bot(10, 9));
        assert!(!can_add_bot(10, 10), "the lobby is full");
        assert!(!can_add_bot(6, 8), "a lobby that shrank");
        assert_eq!(next_bot_number(&[]), 1);
        assert_eq!(next_bot_number(&[1, 2, 4]), 3, "a removed bot's number is reused");
        assert_eq!(bot_team(true, 1, 0), Some(Team::B), "the host alone on A: the bot faces them");
        assert_eq!(bot_team(true, 1, 1), Some(Team::A));
        assert_eq!(bot_team(true, 2, 3), Some(Team::A));
        assert_eq!(bot_team(false, 1, 0), None, "free-for-all");
        let mut w = World::new();
        let [a, b, c] = [(); 3].map(|_| w.spawn_empty().id());
        assert_eq!(bot_to_remove(&[(a, 1), (b, 3), (c, 2)]), Some(b), "the last added");
        assert_eq!(bot_to_remove(&[]), None);
        assert_ne!(bot_id(1), 0, "never the host");
        assert_ne!(bot_id(1), bot_id(2));
    }
}
