//! Kill streaks on the client (item 9c2): the host's [`StreakNews`] turned into kill feed lines, the map-wide
//! banner and stinger of an announced tier, and the streaker's own reward toast. The HUD draws them
//! (`hud.rs`: the feed, the banner, the toast and the streak counter left of the health block); the bounty
//! aura is `render::streak_aura`. The rules and numbers are `vetf_sim::streak` and `rules.ron` `streaks`.

use crate::client::{FEED_LINE_S, FeedEntry, Feedback};
use crate::config::Data;
use bevy::prelude::*;
use lightyear::prelude::*;
use vetf_net::*;
use vetf_sim::streak::{StreakReward, StreakRules};

/// A kill feed line about a streak (on a [`FeedEntry`]; `hud::feed_text` writes it).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreakLine {
    /// "WREN: 3 STREAK", or for an announced tier "WREN is on a 5 STREAK". The player is the entry's killer.
    Reached { kills: u16, announced: bool },
    /// "ORCA ended WREN's 5 STREAK" (the ender is the killer, the streaker the victim), or with no player to
    /// name "FALL ended WREN's 5 STREAK".
    Ended { kills: u16 },
}

/// The map-wide banner of an announced tier: a caption over a headline.
#[derive(Debug, Clone, PartialEq)]
pub struct Banner {
    /// The tier's title ("BOUNTY").
    pub caption: String,
    /// "WREN IS ON A 5 STREAK", or for your own "YOU ARE ON A 5 STREAK".
    pub headline: String,
    /// Seconds left on screen.
    pub left_s: f32,
}

/// The streaker's own reward toast: "3 STREAK: FULL HEALTH + FULL SHIELD".
#[derive(Debug, Clone, PartialEq)]
pub struct Toast {
    pub text: String,
    pub left_s: f32,
}

/// The kill feed line for a piece of streak news.
pub fn feed_entry(news: &StreakNews, rules: &StreakRules, name: impl Fn(u64) -> String) -> FeedEntry {
    let blank = |streak, killer: Option<String>, victim: String, cause| FeedEntry {
        killer,
        helpers: Vec::new(),
        cause,
        victim,
        headshot: false,
        left_s: FEED_LINE_S,
        streak: Some(streak),
    };
    match *news {
        StreakNews::Reached { player, kills } => {
            let announced = rules.tier(kills).is_some_and(|t| t.announce);
            blank(StreakLine::Reached { kills, announced }, Some(name(player)), String::new(), DeathCause::Shot)
        }
        StreakNews::Ended { player, by, kills, cause } => {
            blank(StreakLine::Ended { kills }, by.map(&name), name(player), cause)
        }
    }
}

/// The banner everyone sees when a player reaches an announced tier.
pub fn banner(news: &StreakNews, rules: &StreakRules, me: Option<u64>, name: impl Fn(u64) -> String) -> Option<Banner> {
    let StreakNews::Reached { player, kills } = *news else { return None };
    let tier = rules.tier(kills).filter(|t| t.announce)?;
    let headline = if me == Some(player) {
        format!("YOU ARE ON A {kills} STREAK")
    } else {
        format!("{} IS ON A {kills} STREAK", name(player))
    };
    Some(Banner { caption: tier.title.clone(), headline, left_s: rules.banner_s })
}

/// The streaker's own toast for the rewards of the tier they reached (only rewards that exist: a grenade stub
/// never shows).
pub fn toast(news: &StreakNews, rules: &StreakRules, me: Option<u64>) -> Option<Toast> {
    let StreakNews::Reached { player, kills } = *news else { return None };
    if me != Some(player) {
        return None;
    }
    let given: Vec<&str> =
        rules.tier(kills)?.rewards.iter().filter(|r| r.available()).map(|r| StreakReward::label(*r)).collect();
    if given.is_empty() {
        return None;
    }
    Some(Toast { text: format!("{kills} STREAK: {}", given.join(" + ")), left_s: rules.toast_s })
}

/// The sounds of a piece of news: an announced tier's stinger, then its voice line if one is set (the hook for
/// a recorded announcer line). Nothing for the rest.
pub fn announce_sounds(news: &StreakNews, rules: &StreakRules) -> Vec<String> {
    let StreakNews::Reached { kills, .. } = *news else { return Vec::new() };
    let Some(tier) = rules.tier(kills).filter(|t| t.announce) else { return Vec::new() };
    tier.stinger.iter().chain(&tier.voice).cloned().collect()
}

/// The host's streak news: into the kill feed (after the kill's own line, which arrives first on the ordered
/// channel), the banner and stinger for an announced tier, and the toast for your own rewards.
pub fn receive_streaks(
    data: Res<Data>,
    mut news: Query<&mut MessageReceiver<StreakNews>, With<Client>>,
    players: Query<(&PlayerId, &PlayerInfo)>,
    me: Query<&PlayerId, With<Controlled>>,
    mut feedback: ResMut<Feedback>,
    mut sounds: MessageWriter<crate::sound::FeedbackSound>,
) {
    let rules = &data.rules.streaks;
    let me = me.iter().next().map(|p| p.0);
    let name = |id: u64| {
        players.iter().find(|(p, _)| p.0 == id).map(|(_, i)| i.name.clone()).unwrap_or_else(|| format!("{id:x}"))
    };
    for mut rx in &mut news {
        for n in rx.receive() {
            let entry = feed_entry(&n, rules, name);
            info!("kill feed: {}", crate::hud::feed_text(&entry).line());
            feedback.kills.push(entry);
            if let Some(b) = banner(&n, rules, me, name) {
                feedback.streak_banner = Some(b);
                if let StreakNews::Reached { kills, .. } = n {
                    sounds.write(crate::sound::FeedbackSound::Streak { kills });
                }
            }
            if let Some(t) = toast(&n, rules, me) {
                feedback.streak_toast = Some(t);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hud::feed_text;
    use vetf_sim::GameData;

    fn rules() -> StreakRules {
        GameData::embedded().rules.streaks
    }

    fn name(id: u64) -> String {
        ["HOST", "WREN", "ORCA"][id as usize].to_string()
    }

    fn line(news: StreakNews) -> String {
        feed_text(&feed_entry(&news, &rules(), name)).line()
    }

    /// The kill feed's streak lines: a feed tier, an announced tier, and the end of a streak of 3 or more.
    #[test]
    fn the_feed_names_the_streaks() {
        assert_eq!(line(StreakNews::Reached { player: 1, kills: 3 }), "WREN: 3 STREAK");
        assert_eq!(line(StreakNews::Reached { player: 1, kills: 5 }), "WREN is on a 5 STREAK");
        assert_eq!(line(StreakNews::Reached { player: 2, kills: 10 }), "ORCA is on a 10 STREAK");
        let ended = StreakNews::Ended { player: 1, by: Some(2), kills: 5, cause: DeathCause::Shot };
        assert_eq!(line(ended), "ORCA ended WREN's 5 STREAK");
        let fell = StreakNews::Ended { player: 1, by: None, kills: 4, cause: DeathCause::Fall };
        assert_eq!(line(fell), "FALL ended WREN's 4 STREAK");
        let gone = StreakNews::Ended { player: 1, by: None, kills: 3, cause: DeathCause::Shot };
        assert_eq!(line(gone), "WREN's 3 STREAK ended");
    }

    /// The banner: only an announced tier, for everyone, the streaker reading "YOU".
    #[test]
    fn the_banner_is_map_wide_for_announced_tiers_only() {
        let r = rules();
        let five = StreakNews::Reached { player: 1, kills: 5 };
        for me in [Some(0), Some(2), None] {
            let b = banner(&five, &r, me, name).expect("everyone sees it");
            assert_eq!((b.caption.as_str(), b.headline.as_str()), ("BOUNTY", "WREN IS ON A 5 STREAK"));
            assert_eq!(b.left_s, r.banner_s);
        }
        assert_eq!(banner(&five, &r, Some(1), name).unwrap().headline, "YOU ARE ON A 5 STREAK");
        assert!(banner(&StreakNews::Reached { player: 1, kills: 3 }, &r, Some(0), name).is_none(), "a feed tier");
        let ended = StreakNews::Ended { player: 1, by: Some(2), kills: 5, cause: DeathCause::Shot };
        assert!(banner(&ended, &r, Some(0), name).is_none());
        assert_eq!(announce_sounds(&five, &r), ["announcer/streak_5"], "the stinger (no voice line yet)");
        assert!(announce_sounds(&StreakNews::Reached { player: 1, kills: 3 }, &r).is_empty());
        // A voice line set in the data plays after the stinger.
        let mut voiced = r.clone();
        voiced.tiers.iter_mut().find(|t| t.kills == 5).unwrap().voice = Some("announcer/streak_5_voice".into());
        assert_eq!(announce_sounds(&five, &voiced), ["announcer/streak_5", "announcer/streak_5_voice"]);
    }

    /// The reward toast: only the streaker, only a tier with rewards.
    #[test]
    fn the_toast_tells_the_streaker_their_rewards() {
        let r = rules();
        let three = StreakNews::Reached { player: 1, kills: 3 };
        assert_eq!(toast(&three, &r, Some(1)).unwrap().text, "3 STREAK: FULL HEALTH + FULL SHIELD");
        assert_eq!(toast(&three, &r, Some(1)).unwrap().left_s, r.toast_s);
        assert!(toast(&three, &r, Some(2)).is_none(), "not for anyone else");
        let five = StreakNews::Reached { player: 1, kills: 5 };
        assert_eq!(toast(&five, &r, Some(1)).unwrap().text, "5 STREAK: MAGAZINES REFILLED");
        assert!(toast(&StreakNews::Reached { player: 1, kills: 10 }, &r, Some(1)).is_none(), "10 gives nothing");
        // A grenade (a stub) never shows.
        let mut g = r.clone();
        g.tiers[0].rewards = vec![StreakReward::Grenade];
        assert!(toast(&three, &g, Some(1)).is_none());
    }
}
