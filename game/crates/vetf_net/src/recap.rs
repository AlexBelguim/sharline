//! The death screen's damage recap of one life (user direction 2026-10-09: "it show how much dm you take
//! where and how much dm you gave and where").
//!
//! The host is the authority: every hit it accepts goes into the victim's [`LifeLog`] (taken) and the
//! shooter's (dealt). When a player dies the host sends them a [`LifeRecap`] of their log; the log starts
//! afresh when they respawn. It is a recap, not a log of every shot: one [`DamageLine`] per other player and
//! direction, with hits per zone, the damage to the halo and to health, and the gun and distance of the last
//! hit.

use bevy::prelude::*;
use serde::{Deserialize, Serialize};
use vetf_sim::{Zone, ZoneTable};

/// One life's damage between this player and one other, in one direction (taken from them, or dealt to them).
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct DamageLine {
    /// The other player's [`crate::PlayerId`].
    pub player: u64,
    /// The gun of the last hit (a `weapons.ron` id).
    pub weapon: String,
    /// Hits per zone.
    pub hits: ZoneTable<u16>,
    /// Damage the halo took.
    pub shield: f32,
    /// Damage that reached health.
    pub health: f32,
    /// How far the shot of the last hit flew (m).
    pub range_m: f32,
    /// Where the shooter's eye was for the last hit (the death cam turns toward it).
    pub from: Vec3,
}

impl DamageLine {
    pub fn total(&self) -> f32 {
        self.shield + self.health
    }

    pub fn hit_count(&self) -> u32 {
        self.hits.iter().map(|(_, n)| *n as u32).sum()
    }
}

/// One accepted hit, as the host records it.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Hit<'a> {
    pub shooter: u64,
    pub victim: u64,
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
}

/// What one player took and dealt in their current life (host only, never sent as it is).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct LifeLog {
    pub taken: Vec<DamageLine>,
    pub dealt: Vec<DamageLine>,
}

impl LifeLog {
    /// `hit` landed on this player.
    pub fn took(&mut self, hit: &Hit) {
        add(&mut self.taken, hit.shooter, hit);
    }

    /// This player's `hit` landed on someone.
    pub fn dealt(&mut self, hit: &Hit) {
        add(&mut self.dealt, hit.victim, hit);
    }

    /// A new life.
    pub fn clear(&mut self) {
        self.taken.clear();
        self.dealt.clear();
    }

    /// The recap of this life for its owner, who was killed by `killer` (`None`: a fall, the level) with a hit
    /// in `zone`. The killer's line comes first among the damage taken, then the most damage; the damage dealt
    /// is ordered by the most damage.
    pub fn recap(&self, killer: Option<u64>, zone: Option<Zone>) -> LifeRecap {
        let mut taken = self.taken.clone();
        let mut dealt = self.dealt.clone();
        let most = |a: &DamageLine, b: &DamageLine| b.total().total_cmp(&a.total()).then(a.player.cmp(&b.player));
        taken.sort_by(|a, b| (Some(b.player) == killer).cmp(&(Some(a.player) == killer)).then(most(a, b)));
        dealt.sort_by(most);
        LifeRecap { killer, zone, taken, dealt }
    }
}

fn add(lines: &mut Vec<DamageLine>, other: u64, hit: &Hit) {
    let i = match lines.iter().position(|l| l.player == other) {
        Some(i) => i,
        None => {
            lines.push(DamageLine {
                player: other,
                weapon: String::new(),
                hits: ZoneTable::default(),
                shield: 0.0,
                health: 0.0,
                range_m: 0.0,
                from: Vec3::ZERO,
            });
            lines.len() - 1
        }
    };
    let line = &mut lines[i];
    line.hits[hit.zone] = line.hits[hit.zone].saturating_add(1);
    line.shield += hit.shield.max(0.0);
    line.health += hit.health.max(0.0);
    line.range_m = hit.range_m;
    line.from = hit.from;
    if line.weapon != hit.weapon {
        line.weapon = hit.weapon.to_string();
    }
}

/// Host -> a player who died: what their life took and dealt (see [`LifeLog::recap`]). Sent again, updated,
/// if a shot they fired before dying lands while they are still dead.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub struct LifeRecap {
    /// `None` for falls and the level.
    pub killer: Option<u64>,
    /// The zone of the killing hit.
    pub zone: Option<Zone>,
    /// Per attacker, the killer first.
    pub taken: Vec<DamageLine>,
    /// Per victim.
    pub dealt: Vec<DamageLine>,
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

    /// (halo, health) damage over `lines`.
    pub fn totals(lines: &[DamageLine]) -> (f32, f32) {
        lines.iter().fold((0.0, 0.0), |(s, h), l| (s + l.shield, h + l.health))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn hit(shooter: u64, victim: u64, weapon: &str, zone: Zone, shield: f32, health: f32, range_m: f32) -> Hit<'_> {
        Hit { shooter, victim, weapon, zone, shield, health, range_m, from: Vec3::new(shooter as f32, 1.6, 0.0) }
    }

    /// Hits add up per zone, the halo and health apart; the last hit sets the gun, distance and origin.
    #[test]
    fn hits_add_up_per_zone_with_shield_and_health_apart() {
        let mut log = LifeLog::default();
        log.took(&hit(7, 1, "ar7_mako", Zone::Torso, 30.0, 0.0, 22.0));
        log.took(&hit(7, 1, "ar7_mako", Zone::Torso, 12.0, 18.0, 20.0));
        log.took(&hit(7, 1, "ar7_mako", Zone::Head, 0.0, 41.5, 18.5));
        log.took(&hit(7, 1, "ar7_mako", Zone::Legs, 0.0, 9.0, 18.0));
        assert_eq!(log.taken.len(), 1, "one line per attacker");
        let l = &log.taken[0];
        assert_eq!(l.hits, ZoneTable { head: 1, torso: 2, arms: 0, legs: 1 });
        assert_eq!(l.hit_count(), 4);
        assert_eq!((l.shield, l.health), (42.0, 68.5));
        assert_eq!(l.total(), 110.5);
        assert_eq!((l.weapon.as_str(), l.range_m, l.from), ("ar7_mako", 18.0, Vec3::new(7.0, 1.6, 0.0)));
        assert!(log.dealt.is_empty(), "taking is not dealing");
        // Nothing negative creeps in.
        log.took(&hit(7, 1, "ar7_mako", Zone::Arms, -5.0, -1.0, 18.0));
        assert_eq!((log.taken[0].shield, log.taken[0].health, log.taken[0].hits.arms), (42.0, 68.5, 1));
    }

    /// Several attackers each get their own line; the killer leads the recap, then the most damage; a weapon
    /// switch shows the last gun.
    #[test]
    fn several_attackers_and_victims_each_get_a_line() {
        let mut log = LifeLog::default();
        log.took(&hit(3, 1, "sk9_skink", Zone::Arms, 0.0, 50.0, 9.0));
        log.took(&hit(3, 1, "sk9_skink", Zone::Arms, 0.0, 40.0, 9.0));
        log.took(&hit(8, 1, "vk50_warden", Zone::Head, 30.0, 35.0, 41.0));
        log.took(&hit(5, 1, "ar7_mako", Zone::Legs, 0.0, 5.0, 30.0));
        log.dealt(&hit(1, 3, "ar7_mako", Zone::Torso, 20.0, 0.0, 9.0));
        log.dealt(&hit(1, 8, "ar7_mako", Zone::Head, 25.0, 30.0, 41.0));
        log.dealt(&hit(1, 3, "ar7_mako", Zone::Torso, 10.0, 0.0, 9.0));
        let r = log.recap(Some(8), Some(Zone::Head));
        assert_eq!(r.taken.iter().map(|l| l.player).collect::<Vec<_>>(), vec![8, 3, 5], "killer, then most damage");
        assert_eq!(r.dealt.iter().map(|l| l.player).collect::<Vec<_>>(), vec![8, 3]);
        assert_eq!(r.dealt[1].hits.torso, 2);
        assert_eq!(r.killer_line().map(|l| l.weapon.as_str()), Some("vk50_warden"));
        assert_eq!(r.shot_from(), Some(Vec3::new(8.0, 1.6, 0.0)));
        assert_eq!(LifeRecap::totals(&r.taken), (30.0, 130.0));
        assert_eq!(LifeRecap::totals(&r.dealt), (55.0, 30.0));
        // A fall: no killer, no shot to turn toward.
        let fall = log.recap(None, None);
        assert_eq!(fall.taken[0].player, 3, "most damage first");
        assert_eq!(fall.shot_from(), None);
        // The same attacker switching guns.
        log.took(&hit(3, 1, "ar7_mako", Zone::Torso, 0.0, 1.0, 12.0));
        assert_eq!(log.recap(None, None).taken[0].weapon, "ar7_mako");
    }

    /// A respawn starts an empty log.
    #[test]
    fn a_new_life_starts_empty() {
        let mut log = LifeLog::default();
        log.took(&hit(3, 1, "sk9_skink", Zone::Arms, 0.0, 50.0, 9.0));
        log.dealt(&hit(1, 3, "sk9_skink", Zone::Arms, 0.0, 50.0, 9.0));
        log.clear();
        assert_eq!(log, LifeLog::default());
        let r = log.recap(None, None);
        assert!(r.taken.is_empty() && r.dealt.is_empty());
    }
}
