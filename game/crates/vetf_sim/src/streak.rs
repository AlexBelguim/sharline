//! Kill streaks in team deathmatch and free-for-all (user direction, item 9c2).
//!
//! A streak counts a player's kills in a row within one life: every kill that scores (an enemy, in a live
//! match) adds one, dying sets it back to 0, and assists do not count. Some streak lengths are tiers
//! (`rules.ron` `streaks.tiers`): reaching one puts a line in the kill feed, may announce it to the whole map
//! (a banner and a stinger) and gives its rewards, which the host applies. A long enough streak lights a bounty
//! aura everyone sees, and ending one of `ended_min` or more is in the feed too.
//!
//! Every number lives in `rules.ron`; this module is the rules on them.

use crate::combat::{HaloSpec, HaloState, Health};
use crate::weapon::WeaponState;
use serde::{Deserialize, Serialize};

/// `rules.ron` `streaks`: shared by team deathmatch and free-for-all.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StreakRules {
    /// The HUD counter (left of the health block) shows from this streak on.
    pub hud_min: u16,
    /// Ending a streak at least this long is in the kill feed ("WREN ended ORCA's 5 STREAK").
    pub ended_min: u16,
    /// The bounty aura (embers rising around the body) from this streak on.
    pub aura_min: u16,
    /// How long the map-wide banner stays.
    pub banner_s: f32,
    /// How long the streaker's own reward toast stays.
    pub toast_s: f32,
    /// The streak lengths that do something, in rising order.
    pub tiers: Vec<StreakTier>,
    /// What the bounty aura looks like (visual only).
    pub aura: AuraLook,
}

/// One streak length that does something.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StreakTier {
    /// Kills in a row that reach it.
    pub kills: u16,
    /// Map-wide: a big centre banner for everyone and the stinger. Off: a kill feed line only.
    #[serde(default)]
    pub announce: bool,
    /// The banner's caption (announced tiers).
    #[serde(default)]
    pub title: String,
    /// The `sounds.ron` id everyone hears when it is announced (a placeholder stinger).
    #[serde(default)]
    pub stinger: Option<String>,
    /// The announcer's voice line, a `sounds.ron` id played after the stinger: the hook for a recorded line
    /// (there is no voice model yet, so none is set).
    #[serde(default)]
    pub voice: Option<String>,
    /// What the streaker gets on reaching it.
    #[serde(default)]
    pub rewards: Vec<StreakReward>,
}

/// A reward for reaching a tier. The host applies it ([`apply_rewards`]).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum StreakReward {
    /// Every region back to its maximum HP.
    FullHealth,
    /// Every halo arc back to its capacity.
    FullShield,
    /// Every magazine full again, the one in the gun too (the user's "mag reset").
    RefillMags,
    /// A throwable. A stub until throwables (smoke, molotov) exist: it gives nothing, and the data check
    /// rejects it in a tier.
    Grenade,
}

impl StreakReward {
    /// The reward toast's words.
    pub fn label(self) -> &'static str {
        match self {
            StreakReward::FullHealth => "FULL HEALTH",
            StreakReward::FullShield => "FULL SHIELD",
            StreakReward::RefillMags => "MAGAZINES REFILLED",
            StreakReward::Grenade => "GRENADE",
        }
    }

    /// Can it be given yet? (Not a grenade: there are no throwables.)
    pub fn available(self) -> bool {
        self != StreakReward::Grenade
    }
}

/// The bounty aura: a few small warm embers rising around a streaker's body, looping. It reads as a marker on
/// the player, unlike a teammate's rim glow (`render::friend_foe`), which is an outline drawn on the body.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AuraLook {
    /// Embers per player.
    pub embers: u8,
    /// How far from the body's axis they rise.
    pub radius_m: f32,
    /// From the feet up to this height (just over the halo), then they start again.
    pub height_m: f32,
    /// Seconds for one ember to rise the whole way.
    pub rise_s: f32,
    /// Turns around the body over one rise.
    pub swirl_turns: f32,
    /// An ember's size at its biggest (they shrink away near the top).
    pub size_m: f32,
    /// Colour (sRGB 0..1) and how bright it glows (emissive multiplier).
    pub color: [f32; 3],
    pub glow: f32,
}

impl StreakRules {
    /// The tier a streak of exactly `kills` reaches, if any.
    pub fn tier(&self, kills: u16) -> Option<&StreakTier> {
        self.tiers.iter().find(|t| t.kills == kills)
    }

    /// The HUD counter shows (hidden at 0 and 1 with the shipped numbers).
    pub fn shows_counter(&self, streak: u16) -> bool {
        streak >= self.hud_min.max(1)
    }

    /// The bounty aura shows.
    pub fn has_aura(&self, streak: u16) -> bool {
        streak >= self.aura_min.max(1)
    }

    /// Ending this streak is in the kill feed.
    pub fn announces_end(&self, streak: u16) -> bool {
        streak >= self.ended_min.max(1)
    }

    /// What is wrong with the numbers, if anything.
    pub fn problem(&self) -> Option<String> {
        if self.tiers.windows(2).any(|w| w[1].kills <= w[0].kills) {
            return Some("streaks: tiers must be in rising order of kills".into());
        }
        if self.tiers.iter().any(|t| t.kills < 2) {
            return Some("streaks: a tier needs at least 2 kills (one kill is no streak)".into());
        }
        if let Some(t) = self.tiers.iter().find(|t| t.rewards.iter().any(|r| !r.available())) {
            return Some(format!("streaks: the {}-kill tier gives a reward that does not exist yet", t.kills));
        }
        if let Some(t) = self.tiers.iter().find(|t| t.announce && t.title.is_empty()) {
            return Some(format!("streaks: the announced {}-kill tier needs a banner title", t.kills));
        }
        if self.hud_min < 1 || self.ended_min < 2 || self.aura_min < 2 {
            return Some("streaks: hud_min must be 1 or more, ended_min and aura_min 2 or more".into());
        }
        let a = &self.aura;
        let aura_ok = a.radius_m > 0.0 && a.height_m > 0.0 && a.rise_s > 0.0 && a.size_m > 0.0 && a.glow >= 0.0;
        if !aura_ok || !(self.banner_s > 0.0 && self.toast_s > 0.0) {
            return Some("streaks: the aura's sizes and times, banner_s and toast_s must be positive".into());
        }
        None
    }
}

/// A player's streak after a kill that scores: one more.
pub fn after_kill(streak: u16) -> u16 {
    streak.saturating_add(1)
}

/// A player's streak after they die: none. (Every death, a fall or a teamkill too.)
pub fn after_death(_streak: u16) -> u16 {
    0
}

/// The player whose gear a reward touches.
pub struct RewardTarget<'a> {
    pub health: &'a mut Health,
    pub halo: &'a mut HaloState,
    pub halo_spec: &'a HaloSpec,
    pub weapon: &'a mut WeaponState,
    /// The magazine capacity of the gun they carry.
    pub mag_capacity: u16,
}

/// Give `rewards` to a living player. Returns the ones given (a grenade, a stub, never is).
pub fn apply_rewards(rewards: &[StreakReward], t: RewardTarget) -> Vec<StreakReward> {
    let mut given = Vec::new();
    if t.health.dead {
        return given;
    }
    for &r in rewards {
        match r {
            StreakReward::FullHealth => t.health.hp = t.health.max,
            StreakReward::FullShield => *t.halo = HaloState::full(t.halo_spec),
            StreakReward::RefillMags => {
                t.weapon.refill_mags(u8::MAX, t.mag_capacity);
            }
            StreakReward::Grenade => continue,
        }
        given.push(r);
    }
    given
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::GameData;
    use crate::Zone;
    use crate::player::Loadout;

    fn rules() -> StreakRules {
        GameData::embedded().rules.streaks
    }

    /// Kills in a row add up; a death sets the streak back to nothing.
    #[test]
    fn a_streak_counts_kills_in_a_row_and_a_death_resets_it() {
        let mut s = 0;
        for want in 1..=6 {
            s = after_kill(s);
            assert_eq!(s, want);
        }
        assert_eq!(after_death(s), 0);
        assert_eq!(after_kill(after_death(s)), 1, "a new life starts again at one");
        assert_eq!(after_kill(u16::MAX), u16::MAX, "never wraps");
    }

    /// The shipped tiers (the user's ask): 3 gives full health and shield in the feed, 5 is announced to the
    /// map and refills the magazines, 10 is announced again; the aura from 5, the counter from 2.
    #[test]
    fn the_shipped_tiers() {
        let r = rules();
        assert_eq!(r.problem(), None);
        let three = r.tier(3).expect("a 3 tier");
        assert!(!three.announce, "3 is a feed line");
        assert_eq!(three.rewards, [StreakReward::FullHealth, StreakReward::FullShield]);
        let five = r.tier(5).expect("a 5 tier");
        assert!(five.announce && five.stinger.is_some() && !five.title.is_empty());
        assert_eq!(five.rewards, [StreakReward::RefillMags]);
        assert!(r.tier(10).is_some_and(|t| t.announce));
        assert!(r.tier(1).is_none() && r.tier(2).is_none() && r.tier(4).is_none());
        assert!(!r.shows_counter(0) && !r.shows_counter(1) && r.shows_counter(2));
        assert!(!r.has_aura(4) && r.has_aura(5) && r.has_aura(12));
        assert!(!r.announces_end(2) && r.announces_end(3));
        // No voice line yet (no voice model): the hook is empty.
        assert!(r.tiers.iter().all(|t| t.voice.is_none()));
    }

    /// The aura is only from its tier on: never for a short streak.
    #[test]
    fn the_aura_is_only_from_its_tier() {
        let r = rules();
        for s in 0..r.aura_min {
            assert!(!r.has_aura(s), "{s}");
        }
        for s in r.aura_min..r.aura_min + 20 {
            assert!(r.has_aura(s), "{s}");
        }
    }

    fn hurt_player(d: &GameData) -> (Loadout, Health, HaloState, WeaponState) {
        let l = Loadout::default_for(d, crate::data::Mode::Tdm);
        let mut h = Health::new(d.armor.zone_hp);
        h.hp.torso = 12.0;
        h.hp.head = 3.0;
        h.hp.legs = 0.0;
        let mut halo = HaloState::full(&l.halo);
        halo.shield = crate::ZoneTable { head: 0.0, torso: 0.0, arms: 0.0, legs: 0.0 };
        halo.regen_wait_s = 4.0;
        let mut w = WeaponState::new(d, &l.weapon);
        w.rounds.fill(1);
        (l, h, halo, w)
    }

    /// The 3 tier: every region at its maximum and every arc at its capacity again.
    #[test]
    fn full_health_and_shield_fill_every_region_and_arc() {
        let d = GameData::embedded();
        let (l, mut h, mut halo, mut w) = hurt_player(&d);
        let before = w.rounds.clone();
        let r = rules();
        let rewards = &r.tier(3).unwrap().rewards;
        let target = RewardTarget {
            health: &mut h,
            halo: &mut halo,
            halo_spec: &l.halo,
            weapon: &mut w,
            mag_capacity: l.weapon.mag_capacity,
        };
        assert_eq!(apply_rewards(rewards, target), *rewards);
        assert_eq!(h.hp, h.max);
        for z in Zone::ALL {
            assert_eq!(halo.shield[z], l.halo.capacity[z], "{z:?}");
        }
        assert!(l.halo.total_capacity() > 0.0, "the default deathmatch halo has arcs");
        assert_eq!(w.rounds, before, "health and shield leave the magazines alone");
    }

    /// The 5 tier: every magazine full, the one in the gun too; health and shield untouched.
    #[test]
    fn refill_mags_fills_every_magazine() {
        let d = GameData::embedded();
        let (l, mut h, mut halo, mut w) = hurt_player(&d);
        let (hp, shield) = (h.hp, halo.shield);
        let cap = l.weapon.mag_capacity;
        let target =
            RewardTarget { health: &mut h, halo: &mut halo, halo_spec: &l.halo, weapon: &mut w, mag_capacity: cap };
        assert_eq!(apply_rewards(&[StreakReward::RefillMags], target), [StreakReward::RefillMags]);
        assert!(w.rounds.len() > 1);
        assert!(w.rounds.iter().all(|r| *r == cap), "{:?}", w.rounds);
        assert_eq!((h.hp, halo.shield), (hp, shield));
    }

    /// A grenade is a stub (no throwables yet): it gives nothing, and a tier that lists it is rejected.
    #[test]
    fn the_grenade_reward_is_a_stub() {
        let d = GameData::embedded();
        let (l, mut h, mut halo, mut w) = hurt_player(&d);
        let (hp, rounds) = (h.hp, w.rounds.clone());
        let cap = l.weapon.mag_capacity;
        let target =
            RewardTarget { health: &mut h, halo: &mut halo, halo_spec: &l.halo, weapon: &mut w, mag_capacity: cap };
        assert!(apply_rewards(&[StreakReward::Grenade], target).is_empty());
        assert_eq!((h.hp, w.rounds), (hp, rounds));
        assert!(!StreakReward::Grenade.available());
        let mut r = rules();
        r.tiers[0].rewards.push(StreakReward::Grenade);
        assert!(r.problem().is_some());
    }

    /// The dead get nothing (a trade: the killer died on the same tick).
    #[test]
    fn the_dead_get_no_rewards() {
        let d = GameData::embedded();
        let (l, mut h, mut halo, mut w) = hurt_player(&d);
        h.dead = true;
        let cap = l.weapon.mag_capacity;
        let target =
            RewardTarget { health: &mut h, halo: &mut halo, halo_spec: &l.halo, weapon: &mut w, mag_capacity: cap };
        assert!(apply_rewards(&[StreakReward::FullHealth, StreakReward::RefillMags], target).is_empty());
        assert_eq!(h.hp.torso, 12.0);
    }

    #[test]
    fn broken_streak_rules_are_rejected() {
        let mut r = rules();
        r.tiers.swap(0, 1);
        assert!(r.problem().is_some(), "out of order");
        let mut r = rules();
        r.tiers[0].kills = 1;
        assert!(r.problem().is_some(), "one kill is no streak");
        let mut r = rules();
        r.tiers[1].title.clear();
        assert!(r.problem().is_some(), "an announced tier without a title");
        let mut r = rules();
        r.aura.rise_s = 0.0;
        assert!(r.problem().is_some());
    }
}
