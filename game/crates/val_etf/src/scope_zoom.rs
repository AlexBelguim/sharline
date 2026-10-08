//! Variable scopes (item 8d): aimed through an optic whose zoom is a range (attachments.ron `zoom: [min, max]`:
//! the Warden's 6-12x scope and the 1-3x), Zoom in / Zoom out (the wheel by default) move the wanted zoom and the
//! view eases toward it, never in steps. Aimed through such a scope the zoom binds take their inputs, so the wheel
//! zooms instead of jumping.
//!
//! Each optic's last zoom is kept in the player's settings (`Settings::optic_zoom`, saved with them half a second
//! after the last change) and comes back the next time they aim with it, also after a restart.
//!
//! The zoom is the aiming player's own: it narrows their camera (`render::camera_fov`, still blended by the ADS)
//! and their sensitivity follows it (`client::look_per_count`: MATCH FOCAL scales with it, the per-optic ADS
//! multiplier still applies). Shots, the simulation and what other players see never change.

use crate::client::LocalControl;
use crate::config::{Cli, Data};
use crate::screens::Screens;
use crate::settings::{Action, BindInput, Binding, Keybinds, ScopeZoomTuning, Settings, SettingsData};
use bevy::input::mouse::{AccumulatedMouseScroll, MouseScrollUnit};
use bevy::prelude::*;
use lightyear::prelude::*;
use std::collections::BTreeMap;
use vetf_net::*;
use vetf_sim::data::{AttachmentCategory, AttachmentSpec, GameData};
use vetf_sim::input::Buttons;
use vetf_sim::weapon::WeaponLoadout;

/// The variable scope in hand and its zoom (kept in [`LocalControl`]).
#[derive(Debug, Clone, Default, PartialEq)]
pub struct ScopeZoom {
    /// The variable optic's id (None: the gun has no variable optic).
    pub optic: Option<String>,
    /// Its zoom range (min, max).
    pub range: (f32, f32),
    /// The zoom the player scrolled to.
    pub target: f32,
    /// The zoom the view shows, easing toward `target`.
    pub live: f32,
    /// Aimed through it: the zoom binds take their inputs from the other actions.
    pub active: bool,
}

impl ScopeZoom {
    /// The zoom of a weapon as the view shows it: the live zoom of the variable optic in hand, else the loadout's
    /// (a fixed optic's zoom, 1 without one).
    pub fn of(&self, weapon: &WeaponLoadout) -> f32 {
        match &self.optic {
            Some(o) if weapon.attachments.iter().any(|a| a == o) => self.live,
            _ => weapon.zoom,
        }
    }

    /// Follow the optic in hand. A variable optic newly in hand starts at the player's remembered zoom for it
    /// (`memory`, the settings' `optic_zoom`), else at its data default; the same one keeps its zoom.
    pub fn follow(&mut self, spec: Option<&AttachmentSpec>, memory: &BTreeMap<String, f32>) {
        let Some((spec, range)) = spec.and_then(|s| Some((s, s.zoom_range()?))) else {
            *self = ScopeZoom::default();
            return;
        };
        if self.optic.as_deref() == Some(spec.id.as_str()) {
            return;
        }
        let z = remembered(spec, memory);
        *self = ScopeZoom { optic: Some(spec.id.clone()), range, target: z, live: z, active: false };
    }

    /// Move the wanted zoom by `notches` (+ in, − out). The zoom to remember when it changed.
    pub fn scroll(&mut self, notches: f32, tuning: &ScopeZoomTuning) -> Option<f32> {
        self.optic.as_ref()?;
        let before = self.target;
        self.target = step_zoom(self.target, self.range, notches, tuning.notches_per_range);
        (self.target != before).then_some(self.target)
    }

    /// Ease the view's zoom toward the wanted one over `dt` seconds.
    pub fn ease(&mut self, dt: f32, tuning: &ScopeZoomTuning) {
        if self.optic.is_some() {
            self.live = ease_zoom(self.live, self.target, tuning.ease_per_s, dt);
        }
    }
}

/// A variable optic's starting zoom for this player: their remembered one (held inside its range), else its
/// data default.
pub fn remembered(spec: &AttachmentSpec, memory: &BTreeMap<String, f32>) -> f32 {
    match (spec.zoom, memory.get(&spec.id)) {
        (Some(z), Some(m)) => z.clamp(*m),
        _ => spec.start_zoom(),
    }
}

/// The wanted zoom after `notches` (+ in, − out): `per_range` notches cross the whole range, evenly in
/// magnification ratio, held inside it.
pub fn step_zoom(target: f32, (lo, hi): (f32, f32), notches: f32, per_range: f32) -> f32 {
    let held = |z: f32| if z.is_finite() { z.clamp(lo, hi) } else { lo };
    if hi <= lo || lo <= 0.0 || notches == 0.0 || !notches.is_finite() {
        return held(target);
    }
    let per_notch = (hi / lo).ln() / per_range.max(1e-3);
    held((held(target).ln() + notches * per_notch).exp())
}

/// The view's zoom after `dt` seconds easing from `live` toward `target`: it closes 1 − e^(−rate·dt) of the gap,
/// the same at any frame rate, and lands on the target once within a hair of it.
pub fn ease_zoom(live: f32, target: f32, rate_per_s: f32, dt: f32) -> f32 {
    if !live.is_finite() {
        return target;
    }
    let z = live + (target - live) * (1.0 - (-rate_per_s.max(0.0) * dt.max(0.0)).exp());
    if (z - target).abs() < 1e-3 { target } else { z }
}

/// Wheel notches this frame (+ up): a mouse wheel's lines, or a touchpad's pixels over `pixels_per_notch`.
pub fn wheel_notches(scroll: &AccumulatedMouseScroll, tuning: &ScopeZoomTuning) -> f32 {
    match scroll.unit {
        MouseScrollUnit::Line => scroll.delta.y,
        MouseScrollUnit::Pixel => scroll.delta.y / tuning.pixels_per_notch.max(1.0),
    }
}

/// Zoom notches this frame from the Zoom in / Zoom out binds (+ in): a wheel bind counts the wheel's notches in
/// its direction, a held key or button `key_notches_per_s` notches a second.
pub fn zoom_notches(kb: &Keybinds, input: &BindInput, wheel: f32, dt: f32, tuning: &ScopeZoomTuning) -> f32 {
    let mut n = 0.0;
    for (action, sign) in [(Action::ZoomIn, 1.0), (Action::ZoomOut, -1.0)] {
        for b in kb.get(action).into_iter().flatten() {
            n += sign
                * match b {
                    Binding::WheelUp => wheel.max(0.0),
                    Binding::WheelDown => (-wheel).max(0.0),
                    _ if input.held(b) => tuning.key_notches_per_s * dt,
                    _ => 0.0,
                };
        }
    }
    n
}

/// The variable optic of a weapon, if it has one.
pub fn variable_optic<'a>(data: &'a GameData, weapon: &WeaponLoadout) -> Option<&'a AttachmentSpec> {
    weapon
        .attachments
        .iter()
        .filter_map(|a| data.attachment(a))
        .find(|a| a.cat == AttachmentCategory::Optic && a.zoom_range().is_some())
}

/// Every frame before the input is gathered: follow the optic in hand, zoom while aimed through a variable one
/// (its binds then take their inputs, see `client::gather_input`), remember the zoom in the settings, and ease
/// the view toward it.
#[allow(clippy::too_many_arguments)]
pub fn update(
    time: Res<Time>,
    keys: Res<ButtonInput<KeyCode>>,
    mouse: Res<ButtonInput<MouseButton>>,
    scroll: Res<AccumulatedMouseScroll>,
    cli: Res<Cli>,
    data: Res<Data>,
    tables: Res<SettingsData>,
    screens: Res<Screens>,
    me: Query<(&PlayerLoadout, Option<&Vitals>), With<Controlled>>,
    mut settings: ResMut<Settings>,
    mut control: ResMut<LocalControl>,
) {
    let tuning = tables.scope_zoom;
    let me = me.iter().next();
    let spec = me.and_then(|(l, _)| variable_optic(&data, &l.0.weapon));
    let control = &mut *control;
    control.scope.follow(spec, &settings.optic_zoom);
    let dead = me.is_some_and(|(_, v)| v.is_some_and(|v| v.health.dead));
    let free = !control.paused && screens.is_empty() && control.heal.is_none() && control.reload_radial.is_none();
    let scope = &mut control.scope;
    scope.active = scope.optic.is_some() && free && !dead && !cli.bot && control.held & Buttons::ADS != 0;
    if scope.active {
        let wheel = if cli.ignores_desktop_input() { 0.0 } else { wheel_notches(&scroll, &tuning) };
        let input = BindInput { keys: &keys, mouse: &mouse, wheel, wheel_prev: 0.0, taken: Vec::new() };
        let notches = zoom_notches(&settings.keybinds, &input, wheel, time.delta_secs(), &tuning);
        if let (Some(z), Some(id)) = (scope.scroll(notches, &tuning), scope.optic.clone()) {
            // Saved with the settings (half a second after the last change), to two decimals.
            settings.optic_zoom.insert(id, (z * 100.0).round() / 100.0);
        }
    }
    scope.ease(time.delta_secs(), &tuning);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::render::camera_fov;

    fn tuning() -> ScopeZoomTuning {
        crate::settings::embedded().scope_zoom
    }

    fn near(a: f32, b: f32) -> bool {
        (a - b).abs() < 1e-3
    }

    /// The zoom data: the sniper scope scrolls 6x-12x, the 1-3x 1x-3x, and the scroll rates are sane.
    #[test]
    fn the_scroll_tuning_is_in_the_data() {
        let t = tuning();
        assert!(t.notches_per_range >= 2.0 && t.notches_per_range <= 30.0, "{t:?}");
        assert!(t.ease_per_s > 2.0 && t.key_notches_per_s > 0.0 && t.pixels_per_notch > 0.0, "{t:?}");
        let d = GameData::embedded();
        assert_eq!(d.attachment("optic_sniper").and_then(|a| a.zoom_range()), Some((6.0, 12.0)));
        assert_eq!(d.attachment("optic_1_3x").and_then(|a| a.zoom_range()), Some((1.0, 3.0)));
    }

    /// Scrolling moves the wanted zoom evenly in ratio and never past the range; a whole range takes the data's
    /// notches for both scopes.
    #[test]
    fn the_zoom_steps_and_clamps() {
        let n = tuning().notches_per_range;
        for range in [(6.0, 12.0), (1.0, 3.0)] {
            let (lo, hi) = range;
            assert!(near(step_zoom(lo, range, n, n), hi), "{range:?}: a whole range of notches");
            assert!(near(step_zoom(hi, range, -n, n), lo));
            assert_eq!(step_zoom(lo, range, -3.0, n), lo, "never under the range");
            assert_eq!(step_zoom(hi, range, 50.0, n), hi, "never over it");
            assert_eq!(step_zoom(f32::NAN, range, 1.0, n), step_zoom(lo, range, 1.0, n), "broken: from the min");
            let one = step_zoom(lo, range, 1.0, n);
            assert!(one > lo && one < hi);
            // even in ratio: every notch multiplies the zoom by the same factor
            assert!(near(step_zoom(one, range, 1.0, n) / one, one / lo));
            // half a range of notches lands on the geometric middle (6x: about 8.49x)
            assert!(near(step_zoom(lo, range, n * 0.5, n), (lo * hi).sqrt()));
        }
        assert_eq!(step_zoom(20.0, (6.0, 12.0), 0.0, n), 12.0, "a stray value comes back inside");
    }

    /// The view eases toward the wanted zoom: gradual (no jump on the first frame), the same at any frame rate,
    /// and it lands.
    #[test]
    fn the_view_eases_toward_the_zoom() {
        let rate = tuning().ease_per_s;
        let first = ease_zoom(6.0, 12.0, rate, 1.0 / 60.0);
        assert!(first > 6.0 && first < 7.5, "a gradual start: {first}");
        // 60 fps and 240 fps reach the same zoom after the same time
        let run = |fps: u32, secs: f32| {
            let mut z = 6.0;
            for _ in 0..(fps as f32 * secs) as u32 {
                z = ease_zoom(z, 12.0, rate, 1.0 / fps as f32);
            }
            z
        };
        assert!((run(60, 0.1) - run(240, 0.1)).abs() < 0.05, "{} vs {}", run(60, 0.1), run(240, 0.1));
        assert_eq!(run(60, 2.0), 12.0, "it lands on the target");
        let mut prev = 6.0;
        for _ in 0..30 {
            let z = ease_zoom(prev, 12.0, rate, 1.0 / 60.0);
            assert!(z >= prev && z <= 12.0, "monotonic, never past");
            prev = z;
        }
        assert_eq!(ease_zoom(f32::NAN, 3.0, rate, 0.016), 3.0);
        assert_eq!(ease_zoom(4.0, 3.0, rate, 0.0), 4.0, "no time, no change");
    }

    /// A held zoom key zooms over time; a wheel bind counts the wheel's notches in its own direction; nothing
    /// pressed, nothing moves.
    #[test]
    fn the_zoom_binds_read_the_wheel_and_keys() {
        let t = tuning();
        let kb = crate::settings::embedded().defaults.keybinds.clone();
        assert_eq!(kb.get(Action::ZoomIn)[0], Some(Binding::WheelUp));
        assert_eq!(kb.get(Action::ZoomOut)[0], Some(Binding::WheelDown));
        let (mut keys, mouse) = (ButtonInput::<KeyCode>::default(), ButtonInput::<MouseButton>::default());
        fn input<'a>(keys: &'a ButtonInput<KeyCode>, mouse: &'a ButtonInput<MouseButton>, wheel: f32) -> BindInput<'a> {
            BindInput { keys, mouse, wheel, wheel_prev: 0.0, taken: Vec::new() }
        }
        assert_eq!(zoom_notches(&kb, &input(&keys, &mouse, 2.0), 2.0, 0.016, &t), 2.0, "two notches up: in");
        assert_eq!(zoom_notches(&kb, &input(&keys, &mouse, -1.0), -1.0, 0.016, &t), -1.0, "one down: out");
        assert_eq!(zoom_notches(&kb, &input(&keys, &mouse, 0.0), 0.0, 0.016, &t), 0.0);
        let mut kb = kb;
        kb.set(Action::ZoomIn, 1, Some(Binding::Key(KeyCode::Equal)));
        keys.press(KeyCode::Equal);
        assert!(near(zoom_notches(&kb, &input(&keys, &mouse, 0.0), 0.0, 0.5, &t), t.key_notches_per_s * 0.5));
        // a touchpad's pixels
        let pad = AccumulatedMouseScroll { unit: MouseScrollUnit::Pixel, delta: Vec2::new(0.0, t.pixels_per_notch) };
        assert!(near(wheel_notches(&pad, &t), 1.0));
        let wheel = AccumulatedMouseScroll { unit: MouseScrollUnit::Line, delta: Vec2::new(0.0, -3.0) };
        assert_eq!(wheel_notches(&wheel, &t), -3.0);
    }

    /// Aimed through a variable scope the zoom binds take the wheel: wheel down zooms out and no longer jumps.
    /// Jump and the zoom binds may share the wheel (no clash note).
    #[test]
    fn the_zoom_takes_the_wheel_from_jump() {
        let kb = crate::settings::embedded().defaults.keybinds.clone();
        assert!(kb.get(Action::Jump).contains(&Some(Binding::WheelDown)), "the wheel jumps by default");
        let (keys, mouse) = (ButtonInput::<KeyCode>::default(), ButtonInput::<MouseButton>::default());
        let mut input = BindInput { keys: &keys, mouse: &mouse, wheel: -1.0, wheel_prev: 0.0, taken: Vec::new() };
        assert!(kb.just_pressed(Action::Jump, &input) && kb.pressed(Action::Jump, &input));
        input.take(&kb, &crate::settings::ZOOM);
        assert!(!kb.just_pressed(Action::Jump, &input) && !kb.pressed(Action::Jump, &input), "scoped: no jump");
        assert!(input.held(Binding::WheelDown), "the zoom still reads it");
        assert!(kb.conflicts().is_empty(), "{:?}", kb.conflicts());
    }

    /// Each optic's zoom is remembered on its own and comes back from the saved settings file (as it is written
    /// and read on a restart); a remembered zoom outside the range comes back inside it, and an optic never
    /// scrolled starts at its data default.
    #[test]
    fn the_zoom_is_remembered_per_optic_through_the_settings_file() {
        let d = GameData::embedded();
        let t = tuning();
        let mut settings = Settings::default();
        let warden = |optic: &str| WeaponLoadout::resolve(&d, "vk50_warden", &[], &[optic.into()]).unwrap();
        let (sniper, var) = (warden("optic_sniper"), warden("optic_1_3x"));
        let mut s = ScopeZoom::default();
        s.follow(variable_optic(&d, &sniper), &settings.optic_zoom);
        assert_eq!((s.target, s.live), (6.0, 6.0), "never scrolled: the data default");
        for _ in 0..3 {
            if let Some(z) = s.scroll(1.0, &t) {
                settings.optic_zoom.insert("optic_sniper".into(), z);
            }
        }
        let sniper_zoom = s.target;
        assert!(sniper_zoom > 6.0 && sniper_zoom < 12.0);
        s.follow(variable_optic(&d, &var), &settings.optic_zoom);
        assert_eq!(s.target, 1.0, "the 1-3x keeps its own zoom");
        let z = s.scroll(-1.0, &t);
        assert_eq!(z, None, "already at 1x: nothing changes, nothing to save");
        s.scroll(100.0, &t).map(|z| settings.optic_zoom.insert("optic_1_3x".into(), z));
        assert_eq!(s.target, 3.0);
        // through the file, as user_config saves and loads it
        let text = ron::ser::to_string_pretty(&settings, ron::ser::PrettyConfig::default()).unwrap();
        let mut back: Settings = ron::from_str(&text).unwrap();
        back.complete(crate::settings::embedded());
        assert_eq!(back.optic_zoom, settings.optic_zoom);
        let mut s = ScopeZoom::default();
        s.follow(variable_optic(&d, &sniper), &back.optic_zoom);
        assert!(near(s.target, sniper_zoom) && near(s.live, sniper_zoom), "the sniper scope comes back");
        assert!(near(s.of(&sniper), sniper_zoom), "and the view shows it");
        s.follow(variable_optic(&d, &var), &back.optic_zoom);
        assert_eq!(s.target, 3.0, "the 1-3x comes back at 3x");
        // the same optic keeps its live zoom when followed again
        s.scroll(-100.0, &t);
        s.follow(variable_optic(&d, &var), &back.optic_zoom);
        assert_eq!(s.target, 1.0);
        // a hand-edited file out of range, an older file with none
        let odd: Settings = ron::from_str(r#"(optic_zoom: {"optic_sniper": 40.0})"#).unwrap();
        s.follow(variable_optic(&d, &sniper), &odd.optic_zoom);
        assert_eq!(s.target, 12.0);
        let old: Settings = ron::from_str("(version: 1)").unwrap();
        assert!(old.optic_zoom.is_empty());
        // Reset all keeps the remembered zooms
        let mut reset = back.clone();
        reset.reset_all(&crate::settings::embedded().defaults);
        assert_eq!(reset.optic_zoom, back.optic_zoom);
        // a fixed optic has no live zoom
        s.follow(None, &back.optic_zoom);
        assert_eq!(s, ScopeZoom::default());
        assert_eq!(s.of(&warden("optic_3x")), 3.0);
        assert_eq!(s.scroll(1.0, &t), None);
    }

    /// Sensitivity follows the live zoom: in MATCH FOCAL the 12x turns half as far per count as the 6x, the
    /// per-optic ADS multiplier still applies, and from the hip the zoom changes nothing.
    #[test]
    fn sensitivity_follows_the_live_zoom() {
        use crate::client::look_per_count;
        let mut st = Settings::default();
        st.mouse.ads_scaling = crate::settings::AdsScaling::MatchFocal;
        let at = |s: &Settings, zoom: f32, ads: f32| look_per_count(s, Some("optic_sniper"), zoom, ads);
        assert!(near(at(&st, 12.0, 1.0) / at(&st, 6.0, 1.0), 0.5), "{}", at(&st, 12.0, 1.0) / at(&st, 6.0, 1.0));
        assert!(near(at(&st, 6.0, 0.0), at(&st, 12.0, 0.0)), "hip fire ignores the zoom");
        let between = at(&st, 9.0, 1.0);
        assert!(between < at(&st, 6.0, 1.0) && between > at(&st, 12.0, 1.0), "a zoom between, a sensitivity between");
        let base6 = at(&st, 6.0, 1.0);
        st.mouse.optic_mult.insert("optic_sniper".into(), 0.8);
        assert!(near(at(&st, 6.0, 1.0) / base6, 0.8), "the optic's ADS multiplier");
        assert!(near(at(&st, 12.0, 1.0) / at(&st, 6.0, 1.0), 0.5), "still half at 12x");
        // the 1-3x at 1x: hip-fire feel times its multiplier
        let one = look_per_count(&st, Some("optic_1_3x"), 1.0, 1.0);
        assert!(near(one, look_per_count(&st, Some("optic_1_3x"), 1.0, 0.0)));
    }

    /// The 1-3x at 1x gives the 1x view (the hip FOV, no magnification); at 3x it matches the fixed 3x.
    #[test]
    fn one_x_on_the_variable_optic_is_the_one_x_view() {
        let d = GameData::embedded();
        let mouse = Settings::default().mouse;
        let gun = WeaponLoadout::resolve(&d, "ar7_mako", &[], &["optic_1_3x".into()]).unwrap();
        let mut s = ScopeZoom::default();
        s.follow(variable_optic(&d, &gun), &BTreeMap::new());
        assert_eq!(s.of(&gun), 1.0);
        assert!(near(camera_fov(&mouse, s.of(&gun), 1.0), camera_fov(&mouse, 1.0, 0.0)), "1x: the hip FOV");
        s.scroll(100.0, &tuning());
        for _ in 0..240 {
            s.ease(1.0 / 60.0, &tuning());
        }
        assert!(near(camera_fov(&mouse, s.of(&gun), 1.0), camera_fov(&mouse, 3.0, 1.0)), "3x: the 3x view");
        // and halfway up the ADS the zoom is halfway in, as with any optic
        assert!(near(camera_fov(&mouse, s.of(&gun), 0.5), camera_fov(&mouse, 3.0, 0.5)));
    }
}
