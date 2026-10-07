//! Rebindable controls: the actions, what can be bound to them (keys, mouse buttons, the wheel), their
//! display names, the conflict rule, and the input helper the match reads them through.

use bevy::prelude::*;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Everything a player can bind. Order is the Keybinds table order.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Action {
    MoveForward,
    MoveLeft,
    MoveBack,
    MoveRight,
    Jump,
    Sprint,
    Walk,
    Crouch,
    Interact,
    Fire,
    Ads,
    Reload,
    MagCheck,
    FireMode,
    Underbarrel,
    Laser,
    Melee,
    HoldBreath,
    Ability1,
    Signature,
    Ultimate,
    Heal,
    Scoreboard,
    Ping,
    Chat,
    ChangeLoadout,
}

impl Action {
    pub const ALL: [Action; 26] = [
        Action::MoveForward,
        Action::MoveLeft,
        Action::MoveBack,
        Action::MoveRight,
        Action::Jump,
        Action::Sprint,
        Action::Walk,
        Action::Crouch,
        Action::Interact,
        Action::Fire,
        Action::Ads,
        Action::Reload,
        Action::MagCheck,
        Action::FireMode,
        Action::Underbarrel,
        Action::Laser,
        Action::Melee,
        Action::HoldBreath,
        Action::Ability1,
        Action::Signature,
        Action::Ultimate,
        Action::Heal,
        Action::Scoreboard,
        Action::Ping,
        Action::Chat,
        Action::ChangeLoadout,
    ];

    pub const MOVE: [Action; 4] = [Action::MoveForward, Action::MoveLeft, Action::MoveBack, Action::MoveRight];

    /// The short name a conflict note uses ("V is also Laser").
    pub fn short(self) -> &'static str {
        use Action::*;
        match self {
            MoveForward | MoveLeft | MoveBack | MoveRight => "Move",
            Jump => "Jump",
            Sprint => "Sprint",
            Walk => "Walk",
            Crouch => "Crouch",
            Interact => "Interact",
            Fire => "Fire",
            Ads => "Aim down sights",
            Reload => "Reload",
            MagCheck => "Mag check",
            FireMode => "Fire mode",
            Underbarrel => "Underbarrel",
            Laser => "Laser",
            Melee => "Melee",
            HoldBreath => "Hold breath",
            Ability1 => "Ability 1",
            Signature => "Signature",
            Ultimate => "Ultimate",
            Heal => "Heal",
            Scoreboard => "Scoreboard",
            Ping => "Ping",
            Chat => "Chat",
            ChangeLoadout => "Change loadout",
        }
    }

    /// Bindable, but the feature is not in the prototype yet (the row shows LATER).
    pub fn later(self) -> bool {
        use Action::*;
        matches!(
            self,
            Underbarrel | Laser | Melee | HoldBreath | Ability1 | Signature | Ultimate | Ping | Chat | ChangeLoadout
        )
    }
}

/// Pairs that may share an input because they never run at once (you cannot sprint while aiming, and hold
/// breath only works while aiming).
pub const ALLOWED_SHARES: [(Action, Action); 1] = [(Action::Sprint, Action::HoldBreath)];

/// One input: a key, a mouse button or a wheel direction.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub enum Binding {
    Key(KeyCode),
    Mouse(MouseButton),
    WheelUp,
    WheelDown,
}

/// Keys a player can bind: (key, id in settings.ron, cap label). Esc is the match menu and never bindable.
const KEYS: &[(KeyCode, &str, &str)] = &[
    (KeyCode::KeyA, "KeyA", "A"),
    (KeyCode::KeyB, "KeyB", "B"),
    (KeyCode::KeyC, "KeyC", "C"),
    (KeyCode::KeyD, "KeyD", "D"),
    (KeyCode::KeyE, "KeyE", "E"),
    (KeyCode::KeyF, "KeyF", "F"),
    (KeyCode::KeyG, "KeyG", "G"),
    (KeyCode::KeyH, "KeyH", "H"),
    (KeyCode::KeyI, "KeyI", "I"),
    (KeyCode::KeyJ, "KeyJ", "J"),
    (KeyCode::KeyK, "KeyK", "K"),
    (KeyCode::KeyL, "KeyL", "L"),
    (KeyCode::KeyM, "KeyM", "M"),
    (KeyCode::KeyN, "KeyN", "N"),
    (KeyCode::KeyO, "KeyO", "O"),
    (KeyCode::KeyP, "KeyP", "P"),
    (KeyCode::KeyQ, "KeyQ", "Q"),
    (KeyCode::KeyR, "KeyR", "R"),
    (KeyCode::KeyS, "KeyS", "S"),
    (KeyCode::KeyT, "KeyT", "T"),
    (KeyCode::KeyU, "KeyU", "U"),
    (KeyCode::KeyV, "KeyV", "V"),
    (KeyCode::KeyW, "KeyW", "W"),
    (KeyCode::KeyX, "KeyX", "X"),
    (KeyCode::KeyY, "KeyY", "Y"),
    (KeyCode::KeyZ, "KeyZ", "Z"),
    (KeyCode::Digit0, "Digit0", "0"),
    (KeyCode::Digit1, "Digit1", "1"),
    (KeyCode::Digit2, "Digit2", "2"),
    (KeyCode::Digit3, "Digit3", "3"),
    (KeyCode::Digit4, "Digit4", "4"),
    (KeyCode::Digit5, "Digit5", "5"),
    (KeyCode::Digit6, "Digit6", "6"),
    (KeyCode::Digit7, "Digit7", "7"),
    (KeyCode::Digit8, "Digit8", "8"),
    (KeyCode::Digit9, "Digit9", "9"),
    (KeyCode::F1, "F1", "F1"),
    (KeyCode::F2, "F2", "F2"),
    (KeyCode::F3, "F3", "F3"),
    (KeyCode::F4, "F4", "F4"),
    (KeyCode::F5, "F5", "F5"),
    (KeyCode::F6, "F6", "F6"),
    (KeyCode::F7, "F7", "F7"),
    (KeyCode::F8, "F8", "F8"),
    (KeyCode::F9, "F9", "F9"),
    (KeyCode::F10, "F10", "F10"),
    (KeyCode::F11, "F11", "F11"),
    (KeyCode::F12, "F12", "F12"),
    (KeyCode::Space, "Space", "SPACE"),
    (KeyCode::Tab, "Tab", "TAB"),
    (KeyCode::Enter, "Enter", "ENTER"),
    (KeyCode::ShiftLeft, "ShiftLeft", "L-SHIFT"),
    (KeyCode::ShiftRight, "ShiftRight", "R-SHIFT"),
    (KeyCode::ControlLeft, "ControlLeft", "L-CTRL"),
    (KeyCode::ControlRight, "ControlRight", "R-CTRL"),
    (KeyCode::AltLeft, "AltLeft", "L-ALT"),
    (KeyCode::AltRight, "AltRight", "R-ALT"),
    (KeyCode::CapsLock, "CapsLock", "CAPS"),
    (KeyCode::ArrowUp, "ArrowUp", "UP"),
    (KeyCode::ArrowDown, "ArrowDown", "DOWN"),
    (KeyCode::ArrowLeft, "ArrowLeft", "LEFT"),
    (KeyCode::ArrowRight, "ArrowRight", "RIGHT"),
    (KeyCode::Insert, "Insert", "INS"),
    (KeyCode::Delete, "Delete", "DEL"),
    (KeyCode::Home, "Home", "HOME"),
    (KeyCode::End, "End", "END"),
    (KeyCode::PageUp, "PageUp", "PGUP"),
    (KeyCode::PageDown, "PageDown", "PGDN"),
    (KeyCode::Minus, "Minus", "-"),
    (KeyCode::Equal, "Equal", "="),
    (KeyCode::BracketLeft, "BracketLeft", "["),
    (KeyCode::BracketRight, "BracketRight", "]"),
    (KeyCode::Semicolon, "Semicolon", ";"),
    (KeyCode::Quote, "Quote", "'"),
    (KeyCode::Comma, "Comma", ","),
    (KeyCode::Period, "Period", "."),
    (KeyCode::Slash, "Slash", "/"),
    (KeyCode::Backslash, "Backslash", "\\"),
    (KeyCode::Backquote, "Backquote", "`"),
    (KeyCode::Numpad0, "Numpad0", "NUM 0"),
    (KeyCode::Numpad1, "Numpad1", "NUM 1"),
    (KeyCode::Numpad2, "Numpad2", "NUM 2"),
    (KeyCode::Numpad3, "Numpad3", "NUM 3"),
    (KeyCode::Numpad4, "Numpad4", "NUM 4"),
    (KeyCode::Numpad5, "Numpad5", "NUM 5"),
    (KeyCode::Numpad6, "Numpad6", "NUM 6"),
    (KeyCode::Numpad7, "Numpad7", "NUM 7"),
    (KeyCode::Numpad8, "Numpad8", "NUM 8"),
    (KeyCode::Numpad9, "Numpad9", "NUM 9"),
];

const MOUSE: &[(MouseButton, &str, &str)] = &[
    (MouseButton::Left, "MouseLeft", "LMB"),
    (MouseButton::Right, "MouseRight", "RMB"),
    (MouseButton::Middle, "MouseMiddle", "MMB"),
    (MouseButton::Back, "MouseBack", "M4"),
    (MouseButton::Forward, "MouseForward", "M5"),
];

impl Binding {
    /// The bindable keys (Esc is not one: it always opens the match menu).
    pub fn keys() -> impl Iterator<Item = KeyCode> {
        KEYS.iter().map(|(k, ..)| *k)
    }

    pub fn mouse_buttons() -> impl Iterator<Item = MouseButton> {
        MOUSE.iter().map(|(m, ..)| *m)
    }

    pub fn is_bindable_key(k: KeyCode) -> bool {
        KEYS.iter().any(|(c, ..)| *c == k)
    }

    /// The id written to settings.ron.
    pub fn id(self) -> String {
        match self {
            Binding::Key(k) => KEYS.iter().find(|(c, ..)| *c == k).map_or_else(|| format!("{k:?}"), |e| e.1.into()),
            Binding::Mouse(m) => match MOUSE.iter().find(|(b, ..)| *b == m) {
                Some(e) => e.1.into(),
                None => match m {
                    MouseButton::Other(n) => format!("MouseOther{n}"),
                    _ => format!("{m:?}"),
                },
            },
            Binding::WheelUp => "WheelUp".into(),
            Binding::WheelDown => "WheelDown".into(),
        }
    }

    pub fn from_id(id: &str) -> Option<Binding> {
        if let Some(e) = KEYS.iter().find(|e| e.1 == id) {
            return Some(Binding::Key(e.0));
        }
        if let Some(e) = MOUSE.iter().find(|e| e.1 == id) {
            return Some(Binding::Mouse(e.0));
        }
        match id {
            "WheelUp" => Some(Binding::WheelUp),
            "WheelDown" => Some(Binding::WheelDown),
            _ => id.strip_prefix("MouseOther").and_then(|n| n.parse().ok()).map(|n| Binding::Mouse(MouseButton::Other(n))),
        }
    }

    /// What the key cap shows ('L-SHIFT', 'LMB', 'WHEEL ↓').
    pub fn label(self) -> String {
        match self {
            Binding::Key(k) => KEYS.iter().find(|(c, ..)| *c == k).map_or_else(|| format!("{k:?}"), |e| e.2.into()),
            Binding::Mouse(m) => match MOUSE.iter().find(|(b, ..)| *b == m) {
                Some(e) => e.2.into(),
                None => match m {
                    MouseButton::Other(n) => format!("M{n}"),
                    _ => format!("{m:?}"),
                },
            },
            Binding::WheelUp => "WHEEL ↑".into(),
            Binding::WheelDown => "WHEEL ↓".into(),
        }
    }
}

impl From<Binding> for String {
    fn from(b: Binding) -> String {
        b.id()
    }
}

impl TryFrom<String> for Binding {
    type Error = String;
    fn try_from(s: String) -> Result<Self, String> {
        Binding::from_id(&s).ok_or_else(|| format!("unknown input '{s}'"))
    }
}

/// Primary and secondary input per action.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(transparent)]
pub struct Keybinds(pub BTreeMap<Action, [Option<Binding>; 2]>);

impl Keybinds {
    pub fn get(&self, a: Action) -> [Option<Binding>; 2] {
        self.0.get(&a).copied().unwrap_or([None, None])
    }

    pub fn slot(&self, a: Action, slot: usize) -> Option<Binding> {
        self.get(a)[slot.min(1)]
    }

    pub fn set(&mut self, a: Action, slot: usize, b: Option<Binding>) {
        let mut v = self.get(a);
        v[slot.min(1)] = b;
        self.0.insert(a, v);
    }

    /// Actions a newer build added keep their defaults in an older settings file.
    pub fn fill_missing(&mut self, defaults: &Keybinds) {
        for (a, v) in &defaults.0 {
            self.0.entry(*a).or_insert(*v);
        }
    }

    pub fn pressed(&self, a: Action, input: &BindInput) -> bool {
        self.get(a).iter().flatten().any(|b| input.pressed(*b))
    }

    pub fn just_pressed(&self, a: Action, input: &BindInput) -> bool {
        self.get(a).iter().flatten().any(|b| input.just_pressed(*b))
    }

    pub fn just_released(&self, a: Action, input: &BindInput) -> bool {
        self.get(a).iter().flatten().any(|b| input.just_released(*b)) && !self.pressed(a, input)
    }

    /// Clashing inputs: every (action, slot) whose input another action also uses, with that other action.
    /// Shares in [`ALLOWED_SHARES`] are not clashes.
    pub fn conflicts(&self) -> Vec<((Action, usize), Action)> {
        let mut out = Vec::new();
        for a in Action::ALL {
            for slot in 0..2 {
                let Some(b) = self.slot(a, slot) else { continue };
                let other = Action::ALL.into_iter().find(|o| {
                    *o != a
                        && !ALLOWED_SHARES.iter().any(|(x, y)| (*x == a && y == o) || (*y == a && x == o))
                        && self.get(*o).contains(&Some(b))
                });
                if let Some(o) = other {
                    out.push(((a, slot), o));
                }
            }
        }
        out
    }
}

/// What the input devices did this frame, for [`Keybinds`]. The wheel has no button state: a scroll counts
/// as pressed for the frame it happens in.
pub struct BindInput<'a> {
    pub keys: &'a ButtonInput<KeyCode>,
    pub mouse: &'a ButtonInput<MouseButton>,
    /// Wheel movement this frame and last frame (+ = up).
    pub wheel: f32,
    pub wheel_prev: f32,
}

impl BindInput<'_> {
    pub fn pressed(&self, b: Binding) -> bool {
        match b {
            Binding::Key(k) => self.keys.pressed(k),
            Binding::Mouse(m) => self.mouse.pressed(m),
            Binding::WheelUp => self.wheel > 0.0,
            Binding::WheelDown => self.wheel < 0.0,
        }
    }

    pub fn just_pressed(&self, b: Binding) -> bool {
        match b {
            Binding::Key(k) => self.keys.just_pressed(k),
            Binding::Mouse(m) => self.mouse.just_pressed(m),
            Binding::WheelUp => self.wheel > 0.0 && self.wheel_prev <= 0.0,
            Binding::WheelDown => self.wheel < 0.0 && self.wheel_prev >= 0.0,
        }
    }

    pub fn just_released(&self, b: Binding) -> bool {
        match b {
            Binding::Key(k) => self.keys.just_released(k),
            Binding::Mouse(m) => self.mouse.just_released(m),
            Binding::WheelUp => self.wheel <= 0.0 && self.wheel_prev > 0.0,
            Binding::WheelDown => self.wheel >= 0.0 && self.wheel_prev < 0.0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn kb(pairs: &[(Action, Option<Binding>, Option<Binding>)]) -> Keybinds {
        Keybinds(pairs.iter().map(|(a, p, s)| (*a, [*p, *s])).collect())
    }

    #[test]
    fn bindings_round_trip_through_their_ids() {
        for k in Binding::keys() {
            assert_eq!(Binding::from_id(&Binding::Key(k).id()), Some(Binding::Key(k)));
        }
        for m in Binding::mouse_buttons().chain([MouseButton::Other(7)]) {
            assert_eq!(Binding::from_id(&Binding::Mouse(m).id()), Some(Binding::Mouse(m)));
        }
        for b in [Binding::WheelUp, Binding::WheelDown] {
            assert_eq!(Binding::from_id(&b.id()), Some(b));
        }
        assert_eq!(Binding::from_id("Nonsense"), None);
        assert!(!Binding::is_bindable_key(KeyCode::Escape), "Esc always opens the match menu");
        let k = kb(&[(Action::Jump, Some(Binding::Key(KeyCode::Space)), Some(Binding::WheelDown))]);
        let text = ron::to_string(&k).unwrap();
        assert!(text.contains("\"Space\"") && text.contains("\"WheelDown\""), "{text}");
        assert_eq!(ron::from_str::<Keybinds>(&text).unwrap(), k);
    }

    #[test]
    fn cap_labels_match_the_mockup() {
        assert_eq!(Binding::Key(KeyCode::ShiftLeft).label(), "L-SHIFT");
        assert_eq!(Binding::Key(KeyCode::ControlLeft).label(), "L-CTRL");
        assert_eq!(Binding::Key(KeyCode::KeyW).label(), "W");
        assert_eq!(Binding::Key(KeyCode::Digit3).label(), "3");
        assert_eq!(Binding::Mouse(MouseButton::Middle).label(), "MMB");
        assert_eq!(Binding::Mouse(MouseButton::Back).label(), "M4");
        assert_eq!(Binding::WheelDown.label(), "WHEEL ↓");
    }

    #[test]
    fn clashes_name_the_other_action_and_allowed_shares_pass() {
        let v = Some(Binding::Key(KeyCode::KeyV));
        let shift = Some(Binding::Key(KeyCode::ShiftLeft));
        let k = kb(&[
            (Action::Laser, v, None),
            (Action::Melee, v, Some(Binding::Key(KeyCode::Digit3))),
            (Action::Sprint, shift, None),
            (Action::HoldBreath, shift, None),
        ]);
        let c = k.conflicts();
        assert!(c.contains(&((Action::Melee, 0), Action::Laser)));
        assert!(c.contains(&((Action::Laser, 0), Action::Melee)));
        assert_eq!(c.len(), 2, "sprint and hold breath may share shift: {c:?}");
    }

    #[test]
    fn missing_actions_keep_their_defaults() {
        let defaults = kb(&[(Action::Jump, Some(Binding::Key(KeyCode::Space)), None)]);
        let mut user = Keybinds::default();
        user.fill_missing(&defaults);
        assert_eq!(user.slot(Action::Jump, 0), Some(Binding::Key(KeyCode::Space)));
        user.set(Action::Jump, 0, None);
        user.fill_missing(&defaults);
        assert_eq!(user.slot(Action::Jump, 0), None, "a cleared binding stays cleared");
    }
}
