//! Smoke grenades and molotovs in a match (item 10b; the rules are `vetf_sim::throwable`, the look
//! `render::throw_fx`).
//!
//! - **The host** ([`host_step`], in the host's resolve chain): flies every grenade the players throw (each
//!   [`ThrowLaunched`] from the authoritative simulation), pops the smokes, lights the fires, lets smoke put them
//!   out, and burns whoever stands in a fire: a pulse every `pulse_s` through the halo and health rules (the
//!   thrower and teammates too), with the usual damage indicator; a burn kill is the thrower's kill when the
//!   victim is their enemy (cause FIRE), else nobody's. It tells every client what happens ([`ThrowNews`]). Its
//!   [`HostThrows`] is what the test bots see smoke with.
//! - **Every client** (the host's own too): [`ThrowView`], the grenades in flight (the local player's own from the
//!   moment it leaves the hand, predicted along the same deterministic arc, then confirmed by the host), the smoke
//!   clouds and fires on their own clocks, and the bullet tunnels cut through the clouds by every shot this
//!   client sees. [`ThrowView::veiled`] is the smoke sight test for markers. Sounds: the throw, bounces, the pop,
//!   the burst, the fire's loop and the hiss of a fire put out.

use crate::AppState;
use crate::config::{CurrentLevel, Data};
use crate::server::{ClientLinks, PlayerDied, ServerPlayer, hostile, send_to_every_client, takes_damage};
use crate::shared::LocalPlayerEvents;
use crate::sound::{Play, Sfx, cue};
use bevy::prelude::*;
use lightyear::prelude::*;
use std::collections::HashMap;
use vetf_net::*;
use vetf_sim::data::Ruleset;
use vetf_sim::level::{Level, Team};
use vetf_sim::throwable::{
    Fire, Flight, Launch, Projectile, Smoke, ThrowId, ThrowKind, ThrowWorld, ThrowablesFile, Tunnels, WorldEvent, burn,
    pulse_due, sight_blocked,
};

pub struct ThrowablesPlugin;

impl Plugin for ThrowablesPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<ThrowView>()
            .add_systems(OnEnter(AppState::InGame), reset_view)
            .add_systems(OnExit(AppState::InGame), reset_view)
            .add_systems(
                Update,
                (own_throws, receive_news, advance_view, cut_tunnels, play_sounds)
                    .chain()
                    .in_set(ThrowViewSystems)
                    .run_if(in_state(AppState::InGame)),
            );
    }
}

/// The view's update each frame (`render::throw_fx` draws it after).
#[derive(SystemSet, Debug, Clone, PartialEq, Eq, Hash)]
pub struct ThrowViewSystems;

/// The recap's word for burn damage (no gun: the death screen prints it as it is).
pub const MOLOTOV: &str = "molotov";

// ---------------------------------------------------------------------------------------------- the host

/// A grenade left a player's hand on the host this tick (`server::simulate_authoritative`).
#[derive(Message, Debug, Clone, Copy)]
pub struct ThrowLaunched {
    pub owner: u64,
    pub launch: Launch,
}

/// The host's grenades, clouds and fires, and each player's burn clock.
#[derive(Resource, Default)]
pub struct HostThrows {
    pub world: ThrowWorld,
    /// Team captured by the host at launch, retained even if the thrower disconnects.
    teams: HashMap<ThrowId, Option<Team>>,
    burn: HashMap<Entity, f32>,
    /// The level and match phase the world belongs to: a new map or phase (the lobby, a match starting or
    /// ending) clears it.
    key: Option<(String, Option<MatchPhase>)>,
}

impl HostThrows {
    /// Whether smoke hides `b` from `a` (the bots' sight).
    pub fn sight_blocked(&self, data: &ThrowablesFile, dt: f32, a: Vec3, b: Vec3) -> bool {
        self.world.sight_blocked(data, dt, a, b)
    }
}

/// One host tick of throwables, after the shot claims and before the deaths are handled.
#[allow(clippy::type_complexity)]
pub(crate) fn host_step(
    editor: Option<Res<crate::build_editor::EditorActive>>,
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    time: Res<Time>,
    mut host: ResMut<HostThrows>,
    mut launched: MessageReader<ThrowLaunched>,
    mut players: Query<(Entity, &PlayerId, &PlayerInfo, &PlayerLoadout, &mut Vitals, &PlayerMove, &mut ServerPlayer)>,
    matches: Query<&MatchState>,
    mut news: ClientLinks<ThrowNews>,
    mut damage: Query<&mut MessageSender<DamageTaken>>,
    mut deaths: MessageWriter<PlayerDied>,
) {
    if editor.is_some_and(|e|e.0) {launched.clear();return;}
    let Some(level) = level else {
        launched.clear();
        return;
    };
    let m = matches.iter().next();
    let key = (level.name.clone(), m.map(|m| m.phase));
    if host.key.as_ref() != Some(&key) {
        if host.key.is_some() {
            send_to_every_client(&mut news, ThrowNews::Clear);
        }
        host.world.clear();
        host.teams.clear();
        host.burn.clear();
        host.key = Some(key);
    }
    let t = &data.throwables;
    let dt = data.tick_dt();
    for l in launched.read() {
        // This internal event came from the authoritative player tick, which captured its team.
        let launch = l.launch;
        let id = host.world.throw(l.owner, &launch);
        host.teams.insert(id, launch.team);
        send_to_every_client(&mut news, ThrowNews::Thrown { id, launch });
    }
    for e in host.world.step(t, &level, dt) {
        match e {
            WorldEvent::Burst { id, kind, at } => {
                let team = host.teams.remove(&id).flatten();
                send_to_every_client(&mut news, ThrowNews::Burst { id, kind, at, team });
            }
            WorldEvent::Doused { id, .. } => send_to_every_client(&mut news, ThrowNews::Doused { id }),
            WorldEvent::Lost { id } => {
                host.teams.remove(&id);
            }
            WorldEvent::Bounced { .. } => {}
        }
    }

    // Burning: only while shots hurt (not in the lobby, nor once the match is over).
    let hurts = m.is_none_or(|m| takes_damage(m.phase));
    let rules = m.map_or(Ruleset::FULL, |m| m.rules);
    let owners: HashMap<u64, (Entity, Option<Team>)> =
        players.iter().map(|(e, id, info, ..)| (id.0, (e, info.team))).collect();
    let fd = t.molotov.damage;
    let now = time.elapsed_secs_f64();
    let HostThrows { world, burn: clocks, .. } = &mut *host;
    let mut dealt = Vec::new();
    for (e, id, info, lo, mut v, mv, mut sp) in &mut players {
        let fire = (hurts && !v.health.dead && v.protected_s <= 0.0)
            .then(|| world.fire_under(t, dt, mv.0.pos).copied())
            .flatten();
        // Out of the fire the clock resets, so stepping back in burns at once.
        let due = pulse_due(clocks.entry(e).or_insert(0.0), fire.is_some(), fd.pulse_s, dt);
        let Some(fire) = fire.filter(|_| due) else { continue };
        let spec = lo.0.halo;
        let Vitals { health, halo, wounds, .. } = &mut *v;
        let b = burn(&fd, &data.weapons.spill_to_torso, &spec, halo, health);
        wounds.sync(health, &rules);
        // The thrower's enemies burn on the thrower's account (the kill, an assist); their own side and
        // themselves on nobody's.
        let thrower = owners.get(&fire.id.owner).map(|o| o.0);
        let enemy_thrower =
            owners.get(&fire.id.owner).filter(|(te, team)| *te != e && hostile(*team, info.team)).map(|o| o.0);
        if let Some(te) = enemy_thrower {
            sp.last_attacker = Some(te);
        }
        let hit = Hit {
            shooter: fire.id.owner,
            victim: id.0,
            victim_life: sp.life.number,
            weapon: MOLOTOV,
            zone: fd.zone,
            shield: b.absorbed,
            health: b.to_hp,
            range_m: 0.0,
            from: fire.at,
            at_s: now,
        };
        if thrower.is_some() {
            sp.life.took(&hit);
        }
        if let Some(te) = enemy_thrower {
            dealt.push((te, hit));
        }
        if let Ok(mut s) = damage.get_mut(sp.link) {
            s.send::<ReliableChannel>(DamageTaken { from: fire.at, zone: fd.zone, shield: b.absorbed > 0.0 });
        }
        if b.died {
            deaths.write(PlayerDied { victim: e, killer: enemy_thrower, zone: Some(fd.zone), cause: DeathCause::Fire });
        }
    }
    for (te, hit) in dealt {
        if let Ok((.., v, _, mut tsp)) = players.get_mut(te) {
            tsp.life.dealt(&hit);
            tsp.recap_due |= v.health.dead;
        }
    }
    clocks.retain(|e, _| players.contains(*e));
}

// ---------------------------------------------------------------------------------------------- the view

/// A grenade in flight as this client sees it.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Flying {
    pub p: Projectile,
    /// How it was thrown (ours: as we predicted it).
    pub launch: Launch,
    /// Where it was one step back (it is drawn between the two).
    pub prev: Vec3,
    /// Our own throw, flown before the host's word.
    pub predicted: bool,
    /// The host has said it was thrown.
    pub confirmed: bool,
    /// It went off on our clock: it waits there for the host's burst.
    pub landed: bool,
    /// Steps it has waited (for the host's confirmation, or for its burst).
    pub waited: u32,
}

/// A smoke cloud and the bullet lines through it.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SmokeView {
    pub smoke: Smoke,
    pub tunnels: Tunnels,
    pub team: Option<Team>,
}

/// A fire, and its sound.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FireView {
    pub fire: Fire,
    /// Seconds since smoke put it out (the flames die away), `None` while it burns.
    pub doused_s: Option<f32>,
    pub voice: Option<Entity>,
}

/// Something to hear.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ThrowSound {
    Bounce(Vec3),
    Burst(ThrowId, ThrowKind, Vec3),
    Doused(Vec3),
}

/// Unconfirmed own throws and grenades that went off on our clock wait this long for the host (s).
const WAIT_S: f32 = 2.0;
/// A predicted throw this far off the host's (launch point plus velocity, m and m/s) is put on the host's arc.
const CORRECT_M: f32 = 0.05;

/// Every grenade, cloud and fire this client knows of.
#[derive(Resource, Default)]
pub struct ThrowView {
    pub flying: Vec<Flying>,
    pub smokes: Vec<SmokeView>,
    pub fires: Vec<FireView>,
    /// The view's clock (s): bullet tunnels age on it.
    pub now_s: f32,
    /// Frame time not yet stepped.
    acc: f32,
    /// Sounds to start, and fire loops to stop.
    pub sounds: Vec<ThrowSound>,
    pub stop: Vec<Entity>,
}

impl ThrowView {
    /// How far between its last two steps a grenade is drawn (0..1).
    pub fn blend(&self, dt: f32) -> f32 {
        (self.acc / dt.max(1e-6)).clamp(0.0, 1.0)
    }

    /// Whether smoke hides `b` from `a` (markers). Bullet tunnels do not count.
    pub fn veiled(&self, data: &ThrowablesFile, dt: f32, a: Vec3, b: Vec3) -> bool {
        self.smokes.iter().any(|s| sight_blocked(std::slice::from_ref(&s.smoke), data, dt, a, b))
    }

    /// Our own throw left the hand: it flies at once (`owner`: our player id).
    pub fn own_launch(&mut self, owner: u64, l: &Launch) {
        let id = ThrowId { owner, seq: l.seq };
        if self.flying.iter().any(|f| f.p.id == id) {
            return;
        }
        let p = Projectile::new(id, l);
        self.flying.push(Flying {
            p,
            launch: *l,
            prev: p.pos,
            predicted: true,
            confirmed: false,
            landed: false,
            waited: 0,
        });
    }

    /// The host's word.
    pub fn apply(&mut self, news: ThrowNews, data: &ThrowablesFile, level: &Level, dt: f32) {
        match news {
            ThrowNews::Thrown { id, launch } => {
                if let Some(f) = self.flying.iter_mut().find(|f| f.p.id == id) {
                    f.confirmed = true;
                    // Our prediction left from elsewhere or otherwise (a correction): fly the host's throw to the
                    // same age.
                    let off = launch.origin.distance(f.launch.origin) + launch.vel.distance(f.launch.vel);
                    if off > CORRECT_M || launch.charge != f.launch.charge || launch.style != f.launch.style {
                        let age = f.p.age;
                        let mut p = Projectile::new(id, &launch);
                        let mut landed = false;
                        for _ in 0..age {
                            if !matches!(p.step(data, level, dt), Flight::Flying | Flight::Bounced { .. }) {
                                landed = true;
                                break;
                            }
                        }
                        f.p = p;
                        f.prev = p.pos;
                        f.launch = launch;
                        f.landed = landed;
                        f.waited = 0;
                    }
                    f.launch.team = launch.team;
                } else {
                    let p = Projectile::new(id, &launch);
                    self.flying.push(Flying {
                        p,
                        launch,
                        prev: p.pos,
                        predicted: false,
                        confirmed: true,
                        landed: false,
                        waited: 0,
                    });
                }
            }
            ThrowNews::Burst { id, kind, at, team } => {
                self.flying.retain(|f| f.p.id != id);
                match kind {
                    ThrowKind::Smoke => {
                        if !self.smokes.iter().any(|s| s.smoke.id == id) {
                            self.smokes.push(SmokeView {
                                smoke: Smoke::new(id, at),
                                tunnels: Tunnels::default(),
                                team,
                            });
                        }
                    }
                    ThrowKind::Molotov => {
                        if !self.fires.iter().any(|f| f.fire.id == id) {
                            self.fires.push(FireView { fire: Fire::new(id, at), doused_s: None, voice: None });
                        }
                    }
                }
                self.sounds.push(ThrowSound::Burst(id, kind, at));
            }
            ThrowNews::Doused { id } => {
                if let Some(f) = self.fires.iter_mut().find(|f| f.fire.id == id && f.doused_s.is_none()) {
                    f.doused_s = Some(0.0);
                    self.stop.extend(f.voice.take());
                    self.sounds.push(ThrowSound::Doused(f.fire.at));
                }
            }
            ThrowNews::Clear => self.clear(),
        }
    }

    /// Forget everything (stopping the fire loops).
    pub fn clear(&mut self) {
        self.stop.extend(self.fires.iter().filter_map(|f| f.voice));
        self.flying.clear();
        self.smokes.clear();
        self.fires.clear();
        self.sounds.clear();
    }

    /// Step the grenades and age the areas by `elapsed_s` of frame time, in whole ticks of `dt`.
    pub fn advance(&mut self, data: &ThrowablesFile, level: &Level, dt: f32, fade_s: f32, elapsed_s: f32) {
        self.now_s += elapsed_s;
        self.acc = (self.acc + elapsed_s).min(dt * 8.0);
        while self.acc >= dt {
            self.acc -= dt;
            self.step(data, level, dt, fade_s);
        }
    }

    fn step(&mut self, data: &ThrowablesFile, level: &Level, dt: f32, fade_s: f32) {
        let wait = (WAIT_S / dt) as u32;
        let mut sounds = Vec::new();
        self.flying.retain_mut(|f| {
            f.prev = f.p.pos;
            if f.landed || (f.predicted && !f.confirmed) {
                f.waited += 1;
                if f.waited > wait {
                    return false;
                }
            }
            if f.landed {
                return true;
            }
            match f.p.step(data, level, dt) {
                Flight::Flying => true,
                Flight::Bounced { at, .. } => {
                    sounds.push(ThrowSound::Bounce(at));
                    true
                }
                Flight::Burst { .. } => {
                    // The host's burst brings the cloud or the fire; until then it lies where it went off.
                    f.landed = true;
                    f.waited = 0;
                    true
                }
                Flight::Lost => false,
            }
        });
        self.sounds.extend(sounds);
        for s in &mut self.smokes {
            s.smoke.age += 1;
        }
        self.smokes.retain(|s| !s.smoke.done(&data.smoke, dt));
        let mut stop = Vec::new();
        self.fires.retain_mut(|f| {
            f.fire.age += 1;
            if let Some(d) = &mut f.doused_s {
                *d += dt;
            }
            let over = f.fire.done(&data.molotov, dt) || f.doused_s.is_some_and(|d| d >= fade_s);
            if over {
                stop.extend(f.voice.take());
            }
            !over
        });
        self.stop.extend(stop);
    }

    /// A bullet line from `a` to `b`: a tunnel through every cloud it crosses (`reach`: the clouds' size the
    /// line is tested against, a little past the sim's own so the puffs at the rim open too), kept `life_s`.
    pub fn cut(&mut self, data: &ThrowablesFile, dt: f32, a: Vec3, b: Vec3, reach: f32, life_s: f32) {
        let now = self.now_s;
        for s in &mut self.smokes {
            s.tunnels.prune(now, life_s);
            let Some((s0, s1)) = s.smoke.clip(&data.smoke, dt, a, b, reach) else { continue };
            s.tunnels.push(a.lerp(b, s0), a.lerp(b, s1), now);
        }
    }
}

fn reset_view(mut view: ResMut<ThrowView>, mut sfx: Sfx) {
    view.clear();
    for e in std::mem::take(&mut view.stop) {
        sfx.stop(Some(e));
    }
    *view = ThrowView::default();
}

/// Our own grenades fly the moment they leave the hand (the simulation's tick events, outside rollback).
fn own_throws(
    mut events: MessageReader<LocalPlayerEvents>,
    mut view: ResMut<ThrowView>,
    mut sfx: Sfx,
    me: Query<(&PlayerId, &PlayerInfo), With<Controlled>>,
) {
    for e in events.read() {
        if let Some(mut l) = e.events.throw.launched {
            l.team = me.iter().find(|(id, _)| id.0 == e.player).and_then(|(_, info)| info.team);
            view.own_launch(e.player, &l);
            sfx.play(Play::new(cue::THROW));
        }
    }
}

fn receive_news(
    data: Res<Data>,
    level: Option<Res<CurrentLevel>>,
    mut rx: Query<&mut MessageReceiver<ThrowNews>, With<Client>>,
    mut view: ResMut<ThrowView>,
) {
    let Some(level) = level else { return };
    let dt = data.tick_dt();
    for mut r in &mut rx {
        for news in r.receive() {
            view.apply(news, &data.throwables, &level, dt);
        }
    }
}

fn advance_view(
    data: Res<Data>,
    fx: Res<crate::render::throw_fx::ThrowFxData>,
    level: Option<Res<CurrentLevel>>,
    time: Res<Time>,
    mut view: ResMut<ThrowView>,
) {
    let Some(level) = level else { return };
    view.advance(&data.throwables, &level, data.tick_dt(), fx.fire.fade_s, time.delta_secs());
}

/// Every shot this client saw cuts a tunnel through the clouds it crossed.
fn cut_tunnels(
    data: Res<Data>,
    fx: Res<crate::render::throw_fx::ThrowFxData>,
    mut feedback: ResMut<crate::client::Feedback>,
    mut view: ResMut<ThrowView>,
) {
    let paths = std::mem::take(&mut feedback.bullet_paths);
    if view.smokes.is_empty() {
        return;
    }
    let tn = &fx.smoke.tunnel;
    for (a, b) in paths {
        view.cut(&data.throwables, data.tick_dt(), a, b, tn.reach, tn.life_s);
    }
}

fn play_sounds(mut view: ResMut<ThrowView>, mut sfx: Sfx) {
    for e in std::mem::take(&mut view.stop) {
        sfx.stop(Some(e));
    }
    for s in std::mem::take(&mut view.sounds) {
        match s {
            ThrowSound::Bounce(at) => {
                sfx.play(Play::new(cue::THROW_BOUNCE).at(Some(at)));
            }
            ThrowSound::Burst(_, ThrowKind::Smoke, at) => {
                sfx.play(Play::new(cue::SMOKE_POP).at(Some(at)));
            }
            ThrowSound::Burst(id, ThrowKind::Molotov, at) => {
                sfx.play(Play::new(cue::MOLOTOV_BURST).at(Some(at)));
                let voice = sfx.play(Play::new(cue::FIRE_LOOP).at(Some(at)));
                match view.fires.iter_mut().find(|f| f.fire.id == id && f.doused_s.is_none()) {
                    Some(f) => f.voice = voice,
                    // Put out before its loop started.
                    None => sfx.stop(voice),
                }
            }
            ThrowSound::Doused(at) => {
                sfx.play(Play::new(cue::DOUSE).at(Some(at)));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use vetf_sim::GameData;
    use vetf_sim::movement::collision::{Brush, BrushKind};

    const DT: f32 = 1.0 / 60.0;

    fn yard() -> Level {
        let mut level = Level { kill_y: -20.0, ..Default::default() };
        level.world.push(Brush::cuboid(
            Vec3::new(-100.0, -1.0, -100.0),
            Vec3::new(100.0, 0.0, 100.0),
            BrushKind::Solid,
        ));
        level
    }

    fn lob(seq: u16) -> Launch {
        Launch {
            kind: ThrowKind::Smoke,
            seq,
            origin: Vec3::new(0.0, 1.5, 0.0),
            vel: Vec3::new(0.0, 4.0, -8.0),
            ..Default::default()
        }
    }

    #[test]
    fn authoritative_style_charge_and_team_replace_prediction_and_survive_missing_owner() {
        let d = GameData::embedded();
        let level = yard();
        let mut view = ThrowView::default();
        let id = ThrowId { owner: 9, seq: 1 };
        view.own_launch(9, &Launch { charge: u16::MAX, ..lob(1) });
        view.advance(&d.throwables, &level, DT, 0.5, DT * 10.0);
        let host =
            Launch { style: vetf_sim::throwable::ThrowStyle::Underhand, charge: 0, team: Some(Team::B), ..lob(1) };
        view.apply(ThrowNews::Thrown { id, launch: host }, &d.throwables, &level, DT);
        assert_eq!(view.flying[0].launch, host);
        assert_eq!(view.flying[0].p.charge, 0);
        view.apply(
            ThrowNews::Burst { id, kind: ThrowKind::Smoke, at: Vec3::ZERO, team: Some(Team::B) },
            &d.throwables,
            &level,
            DT,
        );
        assert_eq!(view.smokes[0].team, Some(Team::B));
        let absent = ThrowId { owner: 999, seq: 1 };
        view.apply(
            ThrowNews::Burst { id: absent, kind: ThrowKind::Smoke, at: Vec3::X, team: Some(Team::A) },
            &d.throwables,
            &level,
            DT,
        );
        assert_eq!(view.smokes[1].team, Some(Team::A));
    }

    /// Our own throw flies at once and keeps flying when the host confirms it (no jump); a throw the host never
    /// confirms is dropped after a while; someone else's starts from the host's word.
    #[test]
    fn own_throws_are_predicted_then_confirmed() {
        let d = GameData::embedded();
        let level = yard();
        let mut v = ThrowView::default();
        v.own_launch(9, &lob(1));
        v.advance(&d.throwables, &level, DT, 0.5, DT * 5.0);
        let before = v.flying[0].p.pos;
        v.apply(ThrowNews::Thrown { id: ThrowId { owner: 9, seq: 1 }, launch: lob(1) }, &d.throwables, &level, DT);
        assert!(v.flying[0].confirmed);
        assert_eq!(v.flying[0].p.pos, before, "the same arc: no correction");
        // A refused throw (never confirmed) goes after WAIT_S.
        v.own_launch(9, &Launch { seq: 2, ..lob(2) });
        // (It pops on its fuse and waits there for the host's burst too.)
        for _ in 0..((d.throwables.smoke.fuse_s + WAIT_S * 2.0 + 0.2) / 0.05) as u32 {
            v.advance(&d.throwables, &level, DT, 0.5, 0.05);
        }
        assert!(!v.flying.iter().any(|f| f.p.id.seq == 2), "dropped");
        // Another player's throw.
        v.apply(ThrowNews::Thrown { id: ThrowId { owner: 4, seq: 1 }, launch: lob(1) }, &d.throwables, &level, DT);
        assert!(v.flying.iter().any(|f| f.p.id.owner == 4 && !f.predicted));
        // A correction: the host's throw left from elsewhere; ours jumps onto its arc at the same age.
        let mut v = ThrowView::default();
        v.own_launch(9, &lob(3));
        v.advance(&d.throwables, &level, DT, 0.5, DT * 4.0);
        let host = Launch { origin: Vec3::new(2.0, 1.5, 0.0), ..lob(3) };
        v.apply(ThrowNews::Thrown { id: ThrowId { owner: 9, seq: 3 }, launch: host }, &d.throwables, &level, DT);
        assert!((v.flying[0].p.pos.x - 2.0).abs() < 1e-4 && v.flying[0].p.age == 4, "{:?}", v.flying[0].p);
    }

    /// The host's burst replaces the grenade with its cloud or fire; the cloud ages out on the view's clock; a
    /// doused fire dies away; Clear empties everything and stops the loops.
    #[test]
    fn bursts_make_areas_that_end_on_their_own() {
        let d = GameData::embedded();
        let t = &d.throwables;
        let level = yard();
        let mut v = ThrowView::default();
        let id = ThrowId { owner: 4, seq: 1 };
        v.apply(ThrowNews::Thrown { id, launch: lob(1) }, t, &level, DT);
        v.apply(ThrowNews::Burst { id, kind: ThrowKind::Smoke, at: Vec3::ZERO, team: None }, t, &level, DT);
        assert!(v.flying.is_empty() && v.smokes.len() == 1);
        assert!(matches!(v.sounds.last(), Some(ThrowSound::Burst(_, ThrowKind::Smoke, _))));
        let fire = ThrowId { owner: 4, seq: 2 };
        v.apply(
            ThrowNews::Burst { id: fire, kind: ThrowKind::Molotov, at: Vec3::new(9.0, 0.0, 0.0), team: None },
            t,
            &level,
            DT,
        );
        v.fires[0].voice = Some(Entity::from_raw_u32(77).unwrap());
        v.apply(ThrowNews::Doused { id: fire }, t, &level, DT);
        assert_eq!(v.stop.len(), 1, "the fire loop stops");
        for _ in 0..12 {
            v.advance(t, &level, DT, 0.5, 0.05);
        }
        assert!(v.fires.is_empty(), "the doused flames died away");
        let life = t.smoke.grow_s + t.smoke.hold_s + t.smoke.fade_s;
        for _ in 0..((life + 0.5) / 0.1) as u32 {
            v.advance(t, &level, DT, 0.5, 0.1);
        }
        assert!(v.smokes.is_empty(), "the cloud thinned out");
        v.apply(ThrowNews::Burst { id, kind: ThrowKind::Smoke, at: Vec3::ZERO, team: None }, t, &level, DT);
        v.apply(ThrowNews::Clear, t, &level, DT);
        assert!(v.smokes.is_empty() && v.flying.is_empty());
    }

    /// Markers see smoke as the bots do; a shot through a cloud cuts a tunnel (only through the clouds it
    /// crosses), which refills and ages out.
    #[test]
    fn markers_respect_smoke_and_shots_cut_tunnels() {
        let d = GameData::embedded();
        let t = &d.throwables;
        let level = yard();
        let mut v = ThrowView::default();
        let grown = Smoke { id: ThrowId { owner: 1, seq: 1 }, at: Vec3::new(0.0, 0.0, -10.0), age: 200 };
        let far = Smoke { id: ThrowId { owner: 1, seq: 2 }, at: Vec3::new(40.0, 0.0, 0.0), age: 200 };
        v.smokes.push(SmokeView { smoke: grown, tunnels: Tunnels::default(), team: None });
        v.smokes.push(SmokeView { smoke: far, tunnels: Tunnels::default(), team: None });
        let eye = Vec3::new(0.0, 1.6, 0.0);
        assert!(v.veiled(t, DT, eye, Vec3::new(0.0, 1.6, -20.0)));
        assert!(!v.veiled(t, DT, eye, Vec3::new(-20.0, 1.6, 0.0)));
        v.cut(t, DT, eye, Vec3::new(0.0, 1.6, -30.0), 1.15, 2.5);
        assert_eq!(v.smokes[0].tunnels.live(v.now_s, 2.5, 1.0).count(), 1);
        assert_eq!(v.smokes[1].tunnels.live(v.now_s, 2.5, 1.0).count(), 0, "the other cloud is untouched");
        let (tunnel, open) = v.smokes[0].tunnels.live(v.now_s, 2.5, 1.0).next().unwrap();
        assert_eq!(open, 1.0);
        assert!(tunnel.a.z < -4.0 && tunnel.b.z > -16.5, "clipped to the cloud: {tunnel:?}");
        for _ in 0..30 {
            v.advance(t, &level, DT, 0.5, 0.1);
        }
        assert_eq!(v.smokes[0].tunnels.live(v.now_s, 2.5, 1.0).count(), 0, "refilled");
    }
}
