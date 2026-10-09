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
//! A bot gives up its seat on its own when a player joins a full lobby or match (user direction 2026-10-09:
//! "make bot give up automatically"): see [`seat_joiner`].

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
    /// The order bots were added in (higher: later). Numbers are reused, so they do not tell.
    pub added: u64,
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

/// A bot fits while the match has a free seat (it takes a seat like a player, and gives it up to a joiner).
pub fn can_add_bot(max_players: u32, players: usize) -> bool {
    free_seats(max_players, players) > 0
}

/// The bot REMOVE BOT takes out: the last one added (`bots` holds each bot's [`Bot::added`]).
pub fn bot_to_remove(bots: &[(Entity, u64)]) -> Option<Entity> {
    bots.iter().max_by_key(|(_, added)| *added).map(|(e, _)| *e)
}

/// A taken seat as the join rules see it: its team, and for a bot the order it was added in ([`Bot::added`]).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Seat {
    pub team: Option<Team>,
    pub bot: Option<u64>,
}

/// Where a player joining over the network sits: their team, and the seat (an index into the seats) of the
/// bot that leaves to make room for them, if any.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct JoinSeat {
    pub team: Option<Team>,
    pub evict: Option<usize>,
}

/// The seat for a player joining a match of `max_players` (lobby or in progress) that holds `seats`. A free
/// seat is theirs; with none, a bot gives up its seat: in team deathmatch one from the team the joiner goes
/// to (the smaller one, team A on a tie), else from the team with more bots; in free-for-all any bot; the
/// most recently added first. The joiner then takes the smaller team. `None` only when every seat holds a
/// player: joining is never refused while a bot holds a seat.
pub fn seat_joiner(max_players: u32, teams: bool, seats: &[Seat]) -> Option<JoinSeat> {
    let count = |t: Team, skip: Option<usize>| {
        seats.iter().enumerate().filter(|(i, s)| Some(*i) != skip && s.team == Some(t)).count()
    };
    let team_without = |skip: Option<usize>| bot_team(teams, count(Team::A, skip), count(Team::B, skip));
    if free_seats(max_players, seats.len()) > 0 {
        return Some(JoinSeat { team: team_without(None), evict: None });
    }
    // The latest bot on `team` (any team for `None`).
    let latest = |team: Option<Team>| {
        seats
            .iter()
            .enumerate()
            .filter(|(_, s)| team.is_none() || s.team == team)
            .filter_map(|(i, s)| s.bot.map(|added| (i, added)))
            .max_by_key(|(_, added)| *added)
            .map(|(i, _)| i)
    };
    let evict = if teams {
        let bots_on = |t: Team| seats.iter().filter(|s| s.bot.is_some() && s.team == Some(t)).count();
        let more = if bots_on(Team::A) >= bots_on(Team::B) { Team::A } else { Team::B };
        team_without(None).and_then(|t| latest(Some(t))).or_else(|| latest(Some(more))).or_else(|| latest(None))
    } else {
        latest(None)
    }?;
    Some(JoinSeat { team: team_without(Some(evict)), evict: Some(evict) })
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
    // (entity, number, order added)
    let mut taken: Vec<(Entity, u32, u64)> = bots.iter().map(|(e, b)| (e, b.n, b.added)).collect();
    for request in std::mem::take(&mut requests.0) {
        match request {
            BotRequest::Add => {
                if !can_add_bot(m.max_players, seats.len()) {
                    warn!("no free seat for a bot ({} of {})", seats.len(), m.max_players);
                    continue;
                }
                let count = |t: Team| seats.iter().filter(|(_, x)| *x == Some(t)).count();
                let team = bot_team(m.has_teams(), count(Team::A), count(Team::B));
                let numbers: Vec<u32> = taken.iter().map(|(_, n, _)| *n).collect();
                let n = next_bot_number(&numbers);
                let added = taken.iter().map(|(.., a)| a + 1).max().unwrap_or(0);
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
                    Bot { n, added, brain: BotBrain::new(spawn.yaw, 0.0, id), fresh: true },
                    BotControl::default(),
                    Replicate::to_clients(NetworkTarget::All),
                    // Nobody predicts a bot: everyone sees it like another player.
                    InterpolationTarget::to_clients(NetworkTarget::All),
                    DisableReplicateHierarchy,
                ));
                seats.push((e, team));
                taken.push((e, n, added));
            }
            BotRequest::Remove => {
                let order: Vec<(Entity, u64)> = taken.iter().map(|(e, _, a)| (*e, *a)).collect();
                let Some(e) = bot_to_remove(&order) else { continue };
                info!("removing a bot");
                commands.entity(e).despawn();
                // Its seat frees up for the next request in this batch too.
                taken.retain(|(x, ..)| *x != e);
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
    throws: Option<Res<crate::throwables::HostThrows>>,
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
        // Smoke hides heads from bots as walls do.
        let veiled = |a, b| throws.as_ref().is_some_and(|w| w.sight_blocked(&data.throwables, dt, a, b));
        let seen = if armed { pick_target(t, &level.world, veiled, eye, enemies, bot.brain.target) } else { None };
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

    fn human(team: Option<Team>) -> Seat {
        Seat { team, bot: None }
    }

    fn bot(team: Option<Team>, added: u64) -> Seat {
        Seat { team, bot: Some(added) }
    }

    /// A free seat is the joiner's, and no bot leaves for it.
    #[test]
    fn a_free_seat_needs_no_bot_to_leave() {
        let (a, b) = (Some(Team::A), Some(Team::B));
        let seats = [human(a), bot(b, 0), bot(a, 1)];
        assert_eq!(seat_joiner(4, true, &seats), Some(JoinSeat { team: b, evict: None }), "the smaller team");
        assert_eq!(seat_joiner(4, false, &[human(None), bot(None, 0)]), Some(JoinSeat { team: None, evict: None }));
    }

    /// Free-for-all, every seat taken: the most recently added bot leaves (not the highest number: numbers are
    /// reused); with only players in the seats the joiner is turned away.
    #[test]
    fn a_full_ffa_lobby_drops_its_latest_bot() {
        // BOT 1 (added 0), BOT 3 (added 2), BOT 2 re-added after a removal (added 5)
        let seats = [human(None), bot(None, 0), bot(None, 2), bot(None, 5)];
        assert_eq!(seat_joiner(4, false, &seats), Some(JoinSeat { team: None, evict: Some(3) }));
        assert_eq!(seat_joiner(2, false, &[human(None), human(None)]), None, "players only: full");
        assert_eq!(seat_joiner(2, false, &[human(None), bot(None, 0)]), Some(JoinSeat { team: None, evict: Some(1) }));
        // a lobby that shrank below its players still lets one bot go per joiner
        let over = [human(None), human(None), bot(None, 0), bot(None, 1)];
        assert_eq!(seat_joiner(3, false, &over).and_then(|j| j.evict), Some(3));
    }

    /// Team deathmatch, every seat taken: a bot from the team the joiner goes to (the smaller one, A on a tie),
    /// else from the team with more bots, and the joiner takes the seat it left, so the teams stay even.
    #[test]
    fn a_full_tdm_lobby_drops_a_bot_from_the_joiners_team() {
        let (a, b) = (Some(Team::A), Some(Team::B));
        // 2 v 2, a bot on each side: the joiner goes to A (tie), so A's bot leaves
        let seats = [human(a), bot(b, 0), bot(a, 1), human(b)];
        assert_eq!(seat_joiner(4, true, &seats), Some(JoinSeat { team: a, evict: Some(2) }));
        // two bots on A: the latest of them
        let seats = [human(a), bot(a, 0), bot(a, 3), human(b), human(b), bot(b, 4)];
        assert_eq!(seat_joiner(6, true, &seats), Some(JoinSeat { team: a, evict: Some(2) }));
        // 3 v 3, A has only players: the joiner would go to A, so B (the team with bots) gives its latest and
        // the joiner takes B's seat
        let seats = [human(a), human(a), human(b), bot(b, 0), bot(b, 1), human(a)];
        assert_eq!(seat_joiner(6, true, &seats), Some(JoinSeat { team: b, evict: Some(4) }));
        // uneven teams (a host swap): the smaller team B; its bot leaves
        let seats = [human(a), human(a), bot(a, 0), human(b), bot(b, 1), human(a)];
        assert_eq!(seat_joiner(6, true, &seats), Some(JoinSeat { team: b, evict: Some(4) }));
        // players only: full
        assert_eq!(seat_joiner(4, true, &[human(a), human(b), human(a), human(b)]), None);
        // a bot not yet on a team (before the teams sync) still gives way
        assert_eq!(
            seat_joiner(2, true, &[human(a), bot(None, 0)]),
            Some(JoinSeat { team: b, evict: Some(1) }),
            "the joiner faces the host"
        );
    }
}
