//! When the Loadout screen's edits take effect (user direction 2026-10-09, item 8c):
//! - Alive (the menu, the lobby, a match where it applies at the next spawn): CONFIRM applies, and so does
//!   leaving with Esc (or BACK) when the picks are within the points. Over the points, the first Esc only
//!   shows a notice and a second Esc discards the edits.
//! - Dead (over the death screen): there is no CONFIRM. Each valid edit is applied as it is made, so the
//!   host's fallback respawn takes it too, and CONFIRM's place is the death screen's RESPAWN with its timer.
//!   Over the points RESPAWN is blocked until the picks are fixed (it says so); spawning with something
//!   other than what is on screen would be the more confusing choice. The host still checks every loadout.

use super::{LoadoutEdit, LoadoutUi, hash_of};
use vetf_net::LoadoutChoice;
use vetf_sim::GameData;

/// What Esc (or BACK) does to the edit.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EscOutcome {
    /// Nothing changed: just close.
    Close,
    /// Within the points: apply the edits, then close.
    Apply,
    /// Over the points: stay open and say so (a second Esc discards).
    Warn,
    /// Over the points, after the notice: close without applying.
    Discard,
}

/// Esc's rule: `changed` (the picks differ from what was last applied), `valid` (within the points and the
/// caps), `warned` (the notice is showing for these very picks).
pub fn esc_outcome(changed: bool, valid: bool, warned: bool) -> EscOutcome {
    match (changed, valid, warned) {
        (false, ..) => EscOutcome::Close,
        (true, true, _) => EscOutcome::Apply,
        (true, false, false) => EscOutcome::Warn,
        (true, false, true) => EscOutcome::Discard,
    }
}

/// One Esc on the screen: the outcome, keeping the over-the-points notice in `ui` (it holds for the picks it
/// was shown for; any further edit needs a new first Esc).
pub fn esc_step(edit: &LoadoutEdit, ui: &mut LoadoutUi, data: &GameData, budget: Option<u32>) -> EscOutcome {
    let key = hash_of(&edit.draft);
    let out = esc_outcome(edit.changed(), edit.valid(data, budget), ui.esc_warned == Some(key));
    ui.esc_warned = (out == EscOutcome::Warn).then_some(key);
    out
}

/// The notice is showing (for the picks on screen).
pub fn warned(edit: &LoadoutEdit, ui: &LoadoutUi) -> bool {
    ui.esc_warned.is_some_and(|k| k == hash_of(&edit.draft))
}

/// While dead, a valid edit is applied as soon as it is made.
pub fn apply_now(dead: bool, valid: bool, choice: &LoadoutChoice, base: &LoadoutChoice) -> bool {
    dead && valid && choice != base
}

/// CONFIRM's place over the death screen: RESPAWN with its timer.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum RespawnBtn {
    /// The timer runs: whole seconds left.
    Wait(u32),
    Ready,
    /// The picks are over the points: fix them first.
    OverPoints,
    /// RESPAWN was sent.
    Respawning,
}

impl RespawnBtn {
    /// `left`: seconds until RESPAWN may be pressed.
    pub fn new(left: f32, valid: bool, asked: bool) -> Self {
        if asked {
            Self::Respawning
        } else if !valid {
            Self::OverPoints
        } else if left > 0.0 {
            Self::Wait(left.ceil() as u32)
        } else {
            Self::Ready
        }
    }

    pub fn label(self) -> String {
        match self {
            Self::Wait(s) => format!("RESPAWN IN {s}"),
            Self::Ready => "RESPAWN".into(),
            Self::OverPoints => "OVER THE POINTS".into(),
            Self::Respawning => "RESPAWNING".into(),
        }
    }

    pub fn enabled(self) -> bool {
        self == Self::Ready
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::loadout::{Draft, LoadoutsFile};
    use vetf_net::MatchMode;
    use vetf_sim::data::{AmmoChoice, AmmoKind};

    fn edit(d: &GameData) -> LoadoutEdit {
        let kit = d.rules.fixed_loadout(MatchMode::Tdm).cloned();
        let choice = crate::server::default_choice(d);
        let mut file = LoadoutsFile::default();
        file.repair(d, "kestrel");
        let draft = Draft::from_choice(&choice, &file.attachments, d, kit);
        LoadoutEdit { base: draft.choice(), draft, file }
    }

    /// T4 armor and AP III: over team deathmatch's points.
    fn go_over(e: &mut LoadoutEdit, d: &GameData) {
        e.draft.set_armor_tier(4);
        e.draft.set_ammo(AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 }, d);
    }

    #[test]
    fn esc_applies_within_the_points_and_warns_then_discards_over_them() {
        assert_eq!(esc_outcome(false, false, false), EscOutcome::Close, "no edits: nothing to warn about");
        assert_eq!(esc_outcome(true, true, false), EscOutcome::Apply);
        assert_eq!(esc_outcome(true, true, true), EscOutcome::Apply);
        assert_eq!(esc_outcome(true, false, false), EscOutcome::Warn);
        assert_eq!(esc_outcome(true, false, true), EscOutcome::Discard);
    }

    #[test]
    fn esc_on_the_screen_follows_the_points() {
        let d = GameData::embedded();
        let budget = Some(d.rules.tdm.gear_budget);
        let mut ui = LoadoutUi::default();
        let mut e = edit(&d);
        assert_eq!(esc_step(&e, &mut ui, &d, budget), EscOutcome::Close, "untouched");
        // within the points: applied on Esc
        e.draft.set_armor_tier(1);
        assert!(e.changed() && e.valid(&d, budget));
        assert_eq!(esc_step(&e, &mut ui, &d, budget), EscOutcome::Apply);
        // over the points: a notice first, then a second Esc discards
        go_over(&mut e, &d);
        assert!(!e.valid(&d, budget));
        assert_eq!(esc_step(&e, &mut ui, &d, budget), EscOutcome::Warn);
        assert!(warned(&e, &ui), "the notice shows");
        assert_eq!(esc_step(&e, &mut ui, &d, budget), EscOutcome::Discard);
        assert!(!warned(&e, &ui));
        // an edit after the notice needs a new first Esc
        assert_eq!(esc_step(&e, &mut ui, &d, budget), EscOutcome::Warn);
        e.draft.set_armor_tier(3);
        assert!(!warned(&e, &ui), "the notice was for other picks");
        if !e.valid(&d, budget) {
            assert_eq!(esc_step(&e, &mut ui, &d, budget), EscOutcome::Warn);
        }
        // fixed: Esc applies again
        e.draft.set_ammo(AmmoChoice::STANDARD, &d);
        e.draft.set_armor_tier(1);
        assert_eq!(esc_step(&e, &mut ui, &d, budget), EscOutcome::Apply);
        // the gun range has no points: Esc always applies
        go_over(&mut e, &d);
        assert_eq!(esc_step(&e, &mut ui, &d, None), EscOutcome::Apply);
    }

    #[test]
    fn dead_edits_apply_as_they_are_made_when_valid() {
        let d = GameData::embedded();
        let budget = Some(d.rules.tdm.gear_budget);
        let mut e = edit(&d);
        let base = e.base.clone();
        assert!(!apply_now(true, e.valid(&d, budget), &e.draft.choice(), &base), "nothing changed");
        e.draft.set_armor_tier(1);
        let valid = e.valid(&d, budget);
        assert!(apply_now(true, valid, &e.draft.choice(), &base), "dead: sent at once");
        assert!(!apply_now(false, valid, &e.draft.choice(), &base), "alive: CONFIRM or Esc");
        go_over(&mut e, &d);
        assert!(!apply_now(true, e.valid(&d, budget), &e.draft.choice(), &base), "over the points: never sent");
    }

    #[test]
    fn respawn_replaces_confirm_on_the_death_screen() {
        assert_eq!(RespawnBtn::new(3.2, true, false), RespawnBtn::Wait(4));
        assert_eq!(RespawnBtn::new(3.2, true, false).label(), "RESPAWN IN 4");
        assert_eq!(RespawnBtn::new(0.0, true, false), RespawnBtn::Ready);
        assert!(RespawnBtn::new(0.0, true, false).enabled());
        // over the points: blocked until fixed, whatever the timer says
        for left in [0.0, 2.0] {
            let b = RespawnBtn::new(left, false, false);
            assert_eq!((b, b.enabled()), (RespawnBtn::OverPoints, false));
        }
        assert!(!RespawnBtn::new(1.0, true, false).enabled(), "the timer still runs");
        assert_eq!(RespawnBtn::new(0.0, true, true), RespawnBtn::Respawning);
        assert!(!RespawnBtn::Respawning.enabled());
    }
}
