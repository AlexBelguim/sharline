//! The death screen's recap of one life (user direction 2026-10-09: first "it show how much dm you take where
//! and how much dm you gave and where", then "damage you dealt should not be across lives? should show total
//! kills ... the guy you dm in the last 5sec ... total dm and shield dm not remaining health, and leave out the
//! per body part one").
//!
//! The host is the authority: every hit it accepts goes into the victim's [`LifeLog`] (taken) and the
//! shooter's (dealt), and every kill into the killer's. When a player dies the host sends them a
//! [`LifeRecap`] of their log; the log starts afresh when they respawn. Everything in it is about the life
//! that just ended:
//! - damage taken: one [`DamageLine`] per attacker (their gun, the total, the part the halo took, the
//!   distance of their last hit);
//! - damage dealt: one [`Encounter`] per opponent LIFE, so an opponent who died and came back during your
//!   life is a new encounter, never summed into the old one as if it were one fight;
//! - the kills, each with the zone of the killing hit (the headshot icon).
//!
//! The victim's log also keeps each hit's time, for the host's assist credit ([`LifeLog::assisters`]).

use bevy::prelude::*;
use serde::{Deserialize, Serialize};
use vetf_sim::{Zone, ZoneTable};

/// One attacker's damage to you this life.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct DamageLine {
    /// The attacker's [`crate::PlayerId`].
    pub player: u64,
    /// The gun of their last hit (a `weapons.ron` id).
    pub weapon: String,
    /// Damage your halo took.
    pub shield: f32,
    /// Damage that reached your health.
    pub health: f32,
    /// How far the shot of their last hit flew (m).
    pub range_m: f32,
    /// Where their eye was for the last hit (the death cam turns toward it).
    pub from: Vec3,
}

impl DamageLine {
    pub fn total(&self) -> f32 {
        self.shield + self.health
    }
}

/// Your damage to one opponent during ONE of their lives.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct Encounter {
    /// The opponent's [`crate::PlayerId`].
    pub player: u64,
    /// Which of their lives (the host's per-player count, see [`LifeLog::number`]).
    pub life: u32,
    /// Your gun for the last hit.
    pub weapon: String,
    /// Your hits per zone (the death screen lights the silhouette where you hit, it shows no numbers).
    pub hits: ZoneTable<u16>,
    /// Damage their halo took.
    pub shield: f32,
    /// Damage that reached their health.
    pub health: f32,
    /// The host's clock (s) at your last hit on them.
    pub at_s: f64,
    /// You killed them (this life of theirs).
    pub killed: bool,
}

impl Encounter {
    pub fn total(&self) -> f32 {
        self.shield + self.health
    }

    /// Did any of your hits land on `zone`?
    pub fn hit(&self, zone: Zone) -> bool {
        self.hits[zone] > 0
    }
}

/// One of your kills this life.
#[derive(Serialize, Deserialize, Clone, Copy, Debug, PartialEq, Eq)]
pub struct KillMark {
    pub victim: u64,
    /// The zone of the killing hit (`None`: they bled out from your hits).
    pub zone: Option<Zone>,
}

impl KillMark {
    pub fn headshot(&self) -> bool {
        self.zone == Some(Zone::Head)
    }
}

/// One accepted hit, as the host records it.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Hit<'a> {
    pub shooter: u64,
    pub victim: u64,
    /// The victim's life number ([`LifeLog::number`] of their log).
    pub victim_life: u32,
    /// The shooter's gun (a `weapons.ron` id).
    pub weapon: &'a str,
    pub zone: Zone,
    /// Damage the victim's halo absorbed.
    pub shield: f32,
    /// Damage that reached the victim's health.
    pub health: f32,
    pub range_m: f32,
    /// The shot's origin (the shooter's eye).
    pub from: Vec3,
    /// The host's clock (s).
    pub at_s: f64,
}

/// A hit this life took, for the assist credit.
#[derive(Clone, Copy, Debug, PartialEq)]
struct Taken {
    shooter: u64,
    damage: f32,
    at_s: f64,
}

/// What one player took, dealt and killed in their current life (host only, never sent as it is).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct LifeLog {
    /// This life's number: counts up at each respawn, so hits on an opponent's next life are a new encounter.
    pub number: u32,
    pub taken: Vec<DamageLine>,
    pub dealt: Vec<Encounter>,
    pub kills: Vec<KillMark>,
    /// When this life ended (the host's clock), once it has.
    pub died_at_s: Option<f64>,
    /// Every hit taken, with its time (assists).
    hits_taken: Vec<Taken>,
}

impl LifeLog {
    /// `hit` landed on this player.
    pub fn took(&mut self, hit: &Hit) {
        let line = match self.taken.iter().position(|l| l.player == hit.shooter) {
            Some(i) => &mut self.taken[i],
            None => {
                self.taken.push(DamageLine {
                    player: hit.shooter,
                    weapon: String::new(),
                    shield: 0.0,
                    health: 0.0,
                    range_m: 0.0,
                    from: Vec3::ZERO,
                });
                self.taken.last_mut().expect("just pushed")
            }
        };
        line.shield += hit.shield.max(0.0);
        line.health += hit.health.max(0.0);
        line.range_m = hit.range_m;
        line.from = hit.from;
        if line.weapon != hit.weapon {
            line.weapon = hit.weapon.to_string();
        }
        let damage = hit.shield.max(0.0) + hit.health.max(0.0);
        self.hits_taken.push(Taken { shooter: hit.shooter, damage, at_s: hit.at_s });
    }

    /// This player's `hit` landed on someone: it adds to the encounter with that life of theirs.
    pub fn dealt(&mut self, hit: &Hit) {
        let e = self.encounter(hit.victim, hit.victim_life);
        e.hits[hit.zone] = e.hits[hit.zone].saturating_add(1);
        e.shield += hit.shield.max(0.0);
        e.health += hit.health.max(0.0);
        e.at_s = e.at_s.max(hit.at_s);
        if e.weapon != hit.weapon {
            e.weapon = hit.weapon.to_string();
        }
    }

    /// This player killed `victim` (in their life `victim_life`) with a hit in `zone` (`None`: a bleed-out).
    pub fn killed(&mut self, victim: u64, victim_life: u32, zone: Option<Zone>) {
        self.encounter(victim, victim_life).killed = true;
        self.kills.push(KillMark { victim, zone });
    }

    /// This life ended at `at_s`.
    pub fn died(&mut self, at_s: f64) {
        self.died_at_s = Some(at_s);
    }

    /// A respawn: an empty log for the next life.
    pub fn new_life(&mut self) {
        *self = LifeLog { number: self.number.wrapping_add(1), ..default() };
    }

    /// Nothing taken, dealt or killed yet.
    pub fn is_empty(&self) -> bool {
        self.taken.is_empty() && self.dealt.is_empty() && self.kills.is_empty() && self.hits_taken.is_empty()
    }

    fn encounter(&mut self, player: u64, life: u32) -> &mut Encounter {
        match self.dealt.iter().position(|e| e.player == player && e.life == life) {
            Some(i) => &mut self.dealt[i],
            None => {
                self.dealt.push(Encounter {
                    player,
                    life,
                    weapon: String::new(),
                    hits: ZoneTable::default(),
                    shield: 0.0,
                    health: 0.0,
                    at_s: f64::NEG_INFINITY,
                    killed: false,
                });
                self.dealt.last_mut().expect("just pushed")
            }
        }
    }

    /// Who earns an assist for this player's death at `now_s`: everyone but the killer (and this player) who
    /// dealt at least `min_damage` (halo and health) to this life within `window_s` before it. Team rules are
    /// the host's to apply. Ordered by player id.
    pub fn assisters(&self, killer: Option<u64>, now_s: f64, min_damage: f32, window_s: f32) -> Vec<u64> {
        let mut sums: Vec<(u64, f32)> = Vec::new();
        for t in &self.hits_taken {
            if Some(t.shooter) == killer || now_s - t.at_s > window_s as f64 || t.at_s > now_s {
                continue;
            }
            match sums.iter_mut().find(|(p, _)| *p == t.shooter) {
                Some((_, d)) => *d += t.damage,
                None => sums.push((t.shooter, t.damage)),
            }
        }
        let mut out: Vec<u64> = sums.into_iter().filter(|(_, d)| *d >= min_damage.max(0.0)).map(|(p, _)| p).collect();
        out.sort_unstable();
        out
    }

    /// The recap of this life for its owner, who was killed by `killer` (`None`: a fall, the level) with a hit
    /// in `zone`. The killer's line comes first among the damage taken, then the most damage; the encounters
    /// are ordered by the most damage.
    pub fn recap(&self, killer: Option<u64>, zone: Option<Zone>) -> LifeRecap {
        let mut taken = self.taken.clone();
        let mut dealt = self.dealt.clone();
        taken.sort_by(|a, b| {
            (Some(b.player) == killer)
                .cmp(&(Some(a.player) == killer))
                .then(b.total().total_cmp(&a.total()))
                .then(a.player.cmp(&b.player))
        });
        dealt.sort_by(|a, b| b.total().total_cmp(&a.total()).then(a.player.cmp(&b.player)).then(a.life.cmp(&b.life)));
        let last_hit = self.dealt.iter().map(|e| e.at_s).fold(0.0, f64::max);
        LifeRecap {
            killer,
            zone,
            taken,
            dealt,
            kills: self.kills.clone(),
            died_at_s: self.died_at_s.unwrap_or(last_hit),
        }
    }
}

/// Host -> a player who died: their life's damage taken, encounters and kills (see [`LifeLog::recap`]). Sent
/// again, updated, if a shot they fired before dying lands (or kills) while they are still dead.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct LifeRecap {
    /// `None` for falls and the level.
    pub killer: Option<u64>,
    /// The zone of the killing hit.
    pub zone: Option<Zone>,
    /// Per attacker, the killer first.
    pub taken: Vec<DamageLine>,
    /// Per opponent life, the most damage first.
    pub dealt: Vec<Encounter>,
    /// Your kills, in order.
    pub kills: Vec<KillMark>,
    /// When the life ended (the host's clock, as [`Encounter::at_s`]).
    pub died_at_s: f64,
}

impl LifeRecap {
    /// The killer's line among the damage taken.
    pub fn killer_line(&self) -> Option<&DamageLine> {
        let k = self.killer?;
        self.taken.iter().find(|l| l.player == k)
    }

    /// Where the killing shot came from (the killer's last hit).
    pub fn shot_from(&self) -> Option<Vec3> {
        self.killer_line().map(|l| l.from)
    }

    /// (halo, total) damage you took.
    pub fn taken_totals(&self) -> (f32, f32) {
        self.taken.iter().fold((0.0, 0.0), |(s, t), l| (s + l.shield, t + l.total()))
    }

    /// All the damage you dealt this life.
    pub fn dealt_total(&self) -> f32 {
        self.dealt.iter().map(Encounter::total).sum()
    }

    /// How many of your kills were headshots.
    pub fn headshot_kills(&self) -> usize {
        self.kills.iter().filter(|k| k.headshot()).count()
    }

    /// Your last fight: the opponents you hit within `window_s` before you died and did not kill (that life of
    /// theirs), the most damage first. A shot that landed after you died (a trade) counts as at the death.
    pub fn last_fight(&self, window_s: f32) -> Vec<&Encounter> {
        self.dealt
            .iter()
            .filter(|e| !e.killed && e.total() > 0.0 && self.died_at_s - e.at_s <= window_s.max(0.0) as f64)
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[allow(clippy::too_many_arguments)]
    fn hit(shooter: u64, victim: u64, life: u32, zone: Zone, shield: f32, health: f32, at_s: f64) -> Hit<'static> {
        Hit {
            shooter,
            victim,
            victim_life: life,
            weapon: "ar7_mako",
            zone,
            shield,
            health,
            range_m: 20.0,
            from: Vec3::new(shooter as f32, 1.6, 0.0),
            at_s,
        }
    }

    /// Damage taken adds up per attacker, the halo's part apart; the last hit sets the gun, distance and
    /// origin; nothing negative creeps in.
    #[test]
    fn damage_taken_adds_up_per_attacker() {
        let mut log = LifeLog::default();
        log.took(&hit(7, 1, 0, Zone::Torso, 30.0, 0.0, 1.0));
        log.took(&hit(7, 1, 0, Zone::Torso, 12.0, 18.0, 1.2));
        log.took(&Hit { weapon: "vk50_warden", range_m: 18.0, ..hit(7, 1, 0, Zone::Head, 0.0, 41.5, 1.4) });
        assert_eq!(log.taken.len(), 1, "one line per attacker");
        let l = &log.taken[0];
        assert_eq!((l.shield, l.health, l.total()), (42.0, 59.5, 101.5));
        assert_eq!((l.weapon.as_str(), l.range_m, l.from), ("vk50_warden", 18.0, Vec3::new(7.0, 1.6, 0.0)));
        assert!(log.dealt.is_empty() && log.kills.is_empty(), "taking is not dealing");
        log.took(&hit(7, 1, 0, Zone::Arms, -5.0, -1.0, 1.5));
        assert_eq!((log.taken[0].shield, log.taken[0].health), (42.0, 59.5));
    }

    /// The user's screenshot: one row read "BOT 1 ... 1230 health", several of the bot's lives summed. Now each
    /// life of an opponent is its own encounter, and a kill closes only the life it ended.
    #[test]
    fn damage_dealt_is_per_opponent_life() {
        let mut log = LifeLog::default();
        log.dealt(&hit(1, 9, 4, Zone::Head, 50.0, 40.0, 10.0));
        log.dealt(&hit(1, 9, 4, Zone::Torso, 0.0, 60.0, 10.5));
        log.killed(9, 4, Some(Zone::Torso));
        // Bot 9 respawns (life 5) and takes more hits from the same life of ours.
        log.dealt(&hit(1, 9, 5, Zone::Legs, 20.0, 0.0, 30.0));
        log.dealt(&hit(1, 9, 5, Zone::Legs, 15.0, 5.0, 31.0));
        // Someone else, once.
        log.dealt(&hit(1, 3, 0, Zone::Arms, 0.0, 12.0, 31.5));
        assert_eq!(log.dealt.len(), 3, "two lives of bot 9 and one of player 3");
        let first = &log.dealt[0];
        assert_eq!((first.player, first.life, first.total(), first.killed), (9, 4, 150.0, true));
        assert!(first.hit(Zone::Head) && first.hit(Zone::Torso) && !first.hit(Zone::Legs));
        let second = &log.dealt[1];
        assert_eq!(
            (second.player, second.life, second.total(), second.shield, second.killed),
            (9, 5, 40.0, 35.0, false)
        );
        assert_eq!(second.hits.legs, 2);
        assert!(!second.hit(Zone::Head) && !second.hit(Zone::Torso));
        let recap = log.recap(None, None);
        assert_eq!(recap.dealt_total(), 202.0, "the life's total still counts everything");
        assert_eq!(recap.dealt.iter().map(|e| (e.player, e.life)).collect::<Vec<_>>(), [(9, 4), (9, 5), (3, 0)]);
        // A kill on a life we never hit (a bleed-out credit) still marks a kill.
        log.killed(5, 2, None);
        assert_eq!(log.kills.len(), 2);
        assert!(log.dealt.iter().any(|e| e.player == 5 && e.killed && e.total() == 0.0));
    }

    /// The kills keep the killing zone: a headshot icon or a body icon.
    #[test]
    fn kills_know_headshots() {
        let mut log = LifeLog::default();
        log.killed(3, 0, Some(Zone::Head));
        log.killed(4, 0, Some(Zone::Torso));
        log.killed(5, 1, None);
        log.killed(3, 1, Some(Zone::Head));
        let r = log.recap(None, None);
        assert_eq!(r.kills.iter().map(KillMark::headshot).collect::<Vec<_>>(), [true, false, false, true]);
        assert_eq!((r.kills.len(), r.headshot_kills()), (4, 2));
    }

    /// Your last fight: who you hit in the last few seconds before you died and did not kill. Older hits, kills
    /// and a trade shot landing after the death are sorted out.
    #[test]
    fn the_last_fight_is_the_window_before_the_death() {
        let mut log = LifeLog::default();
        log.dealt(&hit(1, 3, 0, Zone::Torso, 30.0, 10.0, 90.0)); // 10 s before: an older fight
        log.dealt(&hit(1, 4, 0, Zone::Head, 25.0, 40.0, 96.0)); // 4 s before
        log.dealt(&hit(1, 5, 2, Zone::Legs, 0.0, 20.0, 95.0)); // exactly 5 s before
        log.dealt(&hit(1, 6, 0, Zone::Torso, 0.0, 70.0, 98.0));
        log.killed(6, 0, Some(Zone::Torso)); // killed: a kill icon, not a last-fight card
        log.dealt(&hit(1, 7, 0, Zone::Arms, 10.0, 0.0, 99.0));
        log.died(100.0);
        log.dealt(&hit(1, 8, 0, Zone::Torso, 0.0, 33.0, 100.1)); // a trade: landed after the death
        let r = log.recap(Some(4), Some(Zone::Head));
        let window = 5.0;
        let fight: Vec<(u64, f32)> = r.last_fight(window).iter().map(|e| (e.player, e.total())).collect();
        assert_eq!(fight, [(4, 65.0), (8, 33.0), (5, 20.0), (7, 10.0)], "most damage first");
        assert_eq!(r.last_fight(3.0).iter().map(|e| e.player).collect::<Vec<_>>(), [8, 7]);
        assert_eq!(r.last_fight(20.0).len(), 5, "a wider window reaches the older fight, never the kill");
        assert_eq!(r.died_at_s, 100.0);
    }

    /// Assists: everyone but the killer who dealt at least the threshold within the window before the death.
    #[test]
    fn assists_need_enough_damage_recently() {
        let mut log = LifeLog::default();
        log.took(&hit(2, 1, 0, Zone::Torso, 20.0, 25.0, 50.0)); // 45 at 10 s before
        log.took(&hit(3, 1, 0, Zone::Torso, 0.0, 30.0, 52.0)); // 30 ...
        log.took(&hit(3, 1, 0, Zone::Legs, 0.0, 15.0, 58.0)); // ... + 15 = 45
        log.took(&hit(4, 1, 0, Zone::Head, 0.0, 39.0, 59.0)); // 39: under the bar
        log.took(&hit(5, 1, 0, Zone::Torso, 0.0, 80.0, 40.0)); // a lot, but 20 s ago
        log.took(&hit(6, 1, 0, Zone::Head, 30.0, 70.0, 59.5)); // the killer
        let (min, window) = (40.0, 10.0);
        assert_eq!(log.assisters(Some(6), 60.0, min, window), [2, 3]);
        assert_eq!(log.assisters(Some(6), 60.5, min, window), [3], "player 2's damage just left the window");
        assert_eq!(log.assisters(None, 60.0, min, window), [2, 3, 6], "a fall: everyone who hurt them recently");
        assert_eq!(log.assisters(Some(6), 60.0, 39.0, window), [2, 3, 4]);
        assert_eq!(log.assisters(Some(6), 60.0, min, 30.0), [2, 3, 5]);
    }

    /// A respawn starts an empty log with the next life number.
    #[test]
    fn a_new_life_starts_empty() {
        let mut log = LifeLog::default();
        log.took(&hit(3, 1, 0, Zone::Arms, 0.0, 50.0, 1.0));
        log.dealt(&hit(1, 3, 0, Zone::Arms, 0.0, 50.0, 1.0));
        log.killed(3, 0, Some(Zone::Arms));
        log.died(2.0);
        log.new_life();
        assert!(log.is_empty() && log.died_at_s.is_none());
        assert_eq!(log.number, 1);
        assert!(log.assisters(None, 2.0, 0.0, 10.0).is_empty(), "the last life's hits are gone");
        let r = log.recap(None, None);
        assert!(r.taken.is_empty() && r.dealt.is_empty() && r.kills.is_empty());
    }

    /// The killer leads the damage taken, then the most damage.
    #[test]
    fn the_killer_leads_the_damage_taken() {
        let mut log = LifeLog::default();
        log.took(&Hit { weapon: "sk9_skink", ..hit(3, 1, 0, Zone::Arms, 0.0, 90.0, 1.0) });
        log.took(&Hit { weapon: "vk50_warden", ..hit(8, 1, 0, Zone::Head, 30.0, 35.0, 2.0) });
        log.took(&hit(5, 1, 0, Zone::Legs, 0.0, 5.0, 3.0));
        let r = log.recap(Some(8), Some(Zone::Head));
        assert_eq!(r.taken.iter().map(|l| l.player).collect::<Vec<_>>(), [8, 3, 5]);
        assert_eq!(r.killer_line().map(|l| l.weapon.as_str()), Some("vk50_warden"));
        assert_eq!(r.shot_from(), Some(Vec3::new(8.0, 1.6, 0.0)));
        assert_eq!(r.taken_totals(), (30.0, 160.0));
        let fall = log.recap(None, None);
        assert_eq!(fall.taken[0].player, 3, "most damage first");
        assert_eq!(fall.shot_from(), None);
    }
}
