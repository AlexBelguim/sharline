//! Weapon state machine: fire rate, fire modes, reloads, mag checks, ADS, spread and bloom.
//!
//! Timers are counted in fixed ticks so predicted and authoritative copies compare exactly.
//! Hard rule: the player never sees an exact round count. The HUD only gets a [`MagEstimate`] from a
//! mag check, and the round counts here stay internal.

use crate::data::{
    AttachmentCategory, FireMode, GameData, ModifierTotals, RecoilSpec, WeaponClass, WeaponSpec, Zoom,
};
use crate::input::{Buttons, InputFrame, view_dir};
use crate::movement::MoveMode;
use crate::rng::SplitMix;
use glam::Vec3;
use serde::{Deserialize, Serialize};

pub fn secs_to_ticks(s: f32, tick_hz: u32) -> u16 {
    (s * tick_hz as f32).round().max(0.0) as u16
}

/// Ticks between shots: 720 RPM at 60 Hz = 5 ticks; bolt guns use the bolt cycle.
pub fn fire_interval_ticks(w: &WeaponSpec, tick_hz: u32) -> u16 {
    let s = w.bolt_cycle_s.unwrap_or(60.0 / w.rpm);
    secs_to_ticks(s, tick_hz).max(1)
}

// ---------------------------------------------------------------------------------------------- loadout

/// A weapon with its attachments resolved: fixed for one life.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WeaponLoadout {
    pub weapon: u8,
    pub attachments: Vec<String>,
    pub mag_capacity: u16,
    pub spare_mags: u8,
    pub zoom: f32,
    pub mods: ModTotals,
}

/// Serializable copy of [`ModifierTotals`].
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ModTotals {
    pub ads_time: f32,
    pub move_mult: f32,
    pub ads_move: f32,
    pub sway: f32,
    pub recoil_v: f32,
    pub recoil_h: f32,
    pub hip_spread: f32,
    pub reload: f32,
    pub sprint_to_fire: f32,
}

impl From<ModifierTotals> for ModTotals {
    fn from(m: ModifierTotals) -> Self {
        Self {
            ads_time: m.ads_time,
            move_mult: m.move_mult,
            ads_move: m.ads_move,
            sway: m.sway,
            recoil_v: m.recoil_v,
            recoil_h: m.recoil_h,
            hip_spread: m.hip_spread,
            reload: m.reload,
            sprint_to_fire: m.sprint_to_fire,
        }
    }
}

impl WeaponLoadout {
    /// Resolve a weapon id plus attachment ids. Attachments that do not fit are ignored; missing
    /// categories fall back to the weapon's defaults (so every gun always has a magazine).
    pub fn resolve(data: &GameData, weapon_id: &str, attachments: &[String], spare_mags: u8) -> Option<Self> {
        let weapon = data.weapon_index(weapon_id)?;
        let spec = &data.weapons.weapons[weapon];
        let fits = |id: &str| data.attachment(id).filter(|a| a.fits.iter().any(|f| f == weapon_id));
        let mut chosen: Vec<&crate::data::AttachmentSpec> = Vec::new();
        for id in attachments {
            if let Some(a) = fits(id) {
                if !chosen.iter().any(|c| c.cat == a.cat) {
                    chosen.push(a);
                }
            }
        }
        for a in &data.attachments.attachments {
            if a.default_for.iter().any(|w| w == weapon_id) && !chosen.iter().any(|c| c.cat == a.cat) {
                chosen.push(a);
            }
        }
        let mag_capacity = chosen
            .iter()
            .find(|a| a.cat == AttachmentCategory::Mag)
            .and_then(|a| a.capacity)
            .or_else(|| data.attachment(&spec.mag_default).and_then(|a| a.capacity))?;
        let zoom = chosen
            .iter()
            .find(|a| a.cat == AttachmentCategory::Optic)
            .and_then(|a| a.zoom.as_ref())
            .map(|z| match z {
                Zoom::Fixed(v) => *v,
                Zoom::Levels(v) => v.first().copied().unwrap_or(1.0),
            })
            .unwrap_or(1.0);
        Some(Self {
            weapon: weapon as u8,
            attachments: chosen.iter().map(|a| a.id.clone()).collect(),
            mag_capacity,
            spare_mags,
            zoom,
            mods: ModifierTotals::combine(chosen.iter().copied()).into(),
        })
    }

    pub fn spec<'a>(&self, data: &'a GameData) -> &'a WeaponSpec {
        &data.weapons.weapons[self.weapon as usize]
    }
}

// ---------------------------------------------------------------------------------------------- mag estimate

/// What a mag check tells the player: an estimate read through the magazine window, never a count.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MagEstimate {
    Empty,
    AlmostEmpty,
    LessThanHalf,
    AboutHalf,
    MoreThanHalf,
    NearlyFull,
    Full,
}

impl MagEstimate {
    pub fn from_rounds(rounds: u16, capacity: u16) -> Self {
        if rounds == 0 || capacity == 0 {
            return Self::Empty;
        }
        if rounds >= capacity {
            return Self::Full;
        }
        match rounds as f32 / capacity as f32 {
            f if f < 0.15 => Self::AlmostEmpty,
            f if f < 0.4 => Self::LessThanHalf,
            f if f < 0.6 => Self::AboutHalf,
            f if f < 0.85 => Self::MoreThanHalf,
            _ => Self::NearlyFull,
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Empty => "EMPTY",
            Self::AlmostEmpty => "ALMOST EMPTY",
            Self::LessThanHalf => "LESS THAN HALF",
            Self::AboutHalf => "ABOUT HALF",
            Self::MoreThanHalf => "MORE THAN HALF",
            Self::NearlyFull => "NEARLY FULL",
            Self::Full => "FULL",
        }
    }

    /// Which of the six HUD bar segments (0 = empty end .. 5 = full end) lights up.
    pub fn segment(self) -> u8 {
        match self {
            Self::Empty | Self::AlmostEmpty => 0,
            Self::LessThanHalf => 1,
            Self::AboutHalf => 2,
            Self::MoreThanHalf => 3,
            Self::NearlyFull => 4,
            Self::Full => 5,
        }
    }
}

// ---------------------------------------------------------------------------------------------- state

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ReloadKind {
    /// Rounds left in the mag: the partial mag goes back into the pouch.
    Tactical,
    /// Mag ran dry: longer, the bolt has to be released.
    Empty,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum WeaponAction {
    Ready,
    Equipping { left: u16 },
    Reloading { left: u16, kind: ReloadKind },
    MagChecking { left: u16 },
}

/// The result card a mag check leaves on the HUD for a few seconds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct MagCard {
    pub estimate: MagEstimate,
    pub left: u16,
}

/// Seconds the mag check card stays up (design/ui mockup 02: "card stays 3 s").
pub const MAG_CARD_S: f32 = 3.0;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WeaponState {
    pub fire_mode: FireMode,
    /// Rounds in the inserted magazine. Internal only: never shown.
    pub mag: u16,
    /// Rounds in each spare magazine in the pouch.
    pub spares: Vec<u16>,
    pub action: WeaponAction,
    /// Ticks until the next shot is allowed (fire interval / bolt cycle).
    pub cooldown: u16,
    /// Ticks until the gun is up after sprinting.
    pub sprint_lock: u16,
    /// Shots in the current burst (drives the recoil pattern).
    pub burst: u16,
    /// Ticks since the last shot (saturating).
    pub since_shot: u16,
    /// Total shots fired this life: seeds spread and identifies shot claims.
    pub shot_seq: u32,
    pub prev_buttons: Buttons,
    pub bloom_deg: f32,
    /// 0 = hip, 1 = fully aimed down sights.
    pub ads: f32,
    pub card: Option<MagCard>,
}

/// Movement facts the weapon needs this tick.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct WeaponEnv {
    pub mode: MoveMode,
    pub sprinting: bool,
    pub crouched: bool,
    /// Horizontal speed / jog speed.
    pub speed_frac: f32,
    pub broken_arms: bool,
}

/// A shot fired this tick.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Shot {
    pub seq: u32,
    /// Spread cone half-angle at the moment of firing (degrees).
    pub spread_deg: f32,
    /// Recoil kick to apply to the view after this shot (degrees, pitch up +, yaw right +).
    pub kick_pitch: f32,
    pub kick_yaw: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct WeaponEvents {
    pub shot: Option<Shot>,
    pub dry_fire: bool,
    pub reload_started: Option<ReloadKind>,
    pub reload_finished: bool,
    pub mag_check_started: bool,
    pub mag_checked: Option<MagEstimate>,
    pub fire_mode_changed: bool,
}

impl WeaponState {
    pub fn new(data: &GameData, loadout: &WeaponLoadout) -> Self {
        let spec = loadout.spec(data);
        let hz = data.net.tick_hz;
        Self {
            fire_mode: spec.fire_modes.first().copied().unwrap_or(FireMode::Semi),
            mag: loadout.mag_capacity,
            spares: vec![loadout.mag_capacity; loadout.spare_mags as usize],
            action: WeaponAction::Equipping { left: secs_to_ticks(spec.equip_s, hz) },
            cooldown: 0,
            sprint_lock: 0,
            burst: 0,
            since_shot: u16::MAX,
            shot_seq: 0,
            prev_buttons: Buttons::default(),
            bloom_deg: 0.0,
            ads: 0.0,
            card: None,
        }
    }

    pub fn is_ready(&self) -> bool {
        self.action == WeaponAction::Ready
    }

    /// How many spare magazines still hold rounds (the HUD may show pouch slots, not round counts).
    pub fn loaded_spares(&self) -> usize {
        self.spares.iter().filter(|&&r| r > 0).count()
    }

    /// Advance one tick.
    pub fn step(
        &mut self,
        data: &GameData,
        loadout: &WeaponLoadout,
        input: &InputFrame,
        env: &WeaponEnv,
    ) -> WeaponEvents {
        let spec = loadout.spec(data);
        let hz = data.net.tick_hz;
        let dt = 1.0 / hz as f32;
        let b = input.buttons;
        let prev = self.prev_buttons;
        self.prev_buttons = b;
        let mut ev = WeaponEvents::default();

        self.cooldown = self.cooldown.saturating_sub(1);
        self.since_shot = self.since_shot.saturating_add(1);
        if let Some(card) = &mut self.card {
            card.left = card.left.saturating_sub(1);
            if card.left == 0 && !b.held(Buttons::MAG_CHECK) {
                self.card = None;
            }
        }

        // Sprinting lowers the gun; it takes `sprint_to_fire_s` to bring it back up.
        let lowered = env.sprinting || env.mode == MoveMode::Mantle;
        if lowered {
            self.sprint_lock = secs_to_ticks(spec.sprint_to_fire_s * loadout.mods.sprint_to_fire, hz);
        } else {
            self.sprint_lock = self.sprint_lock.saturating_sub(1);
        }

        // Timed actions.
        match &mut self.action {
            WeaponAction::Ready => {}
            WeaponAction::Equipping { left } => {
                *left = left.saturating_sub(1);
                if *left == 0 {
                    self.action = WeaponAction::Ready;
                }
            }
            WeaponAction::Reloading { left, kind } => {
                *left = left.saturating_sub(1);
                if *left == 0 {
                    let kind = *kind;
                    self.finish_reload(kind);
                    self.action = WeaponAction::Ready;
                    ev.reload_finished = true;
                }
            }
            WeaponAction::MagChecking { left } => {
                // Firing, aiming or sprinting cancels a mag check.
                if b.held(Buttons::FIRE) || b.held(Buttons::ADS) || lowered {
                    self.action = WeaponAction::Ready;
                } else {
                    *left = left.saturating_sub(1);
                    if *left == 0 {
                        let est = MagEstimate::from_rounds(self.mag, loadout.mag_capacity);
                        self.card = Some(MagCard { estimate: est, left: secs_to_ticks(MAG_CARD_S, hz) });
                        self.action = WeaponAction::Ready;
                        ev.mag_checked = Some(est);
                    }
                }
            }
        }

        // ADS.
        let can_ads = self.is_ready() && !lowered && !(env.mode == MoveMode::Jetpack && !data.movement.jetpack.ads_allowed);
        let mut ads_time = spec.ads_s * loadout.mods.ads_time;
        if env.broken_arms {
            ads_time *= data.combat.broken_arms.ads_time_mult;
        }
        let ads_rate = dt / ads_time.max(dt);
        if can_ads && b.held(Buttons::ADS) {
            self.ads = (self.ads + ads_rate).min(1.0);
        } else {
            self.ads = (self.ads - ads_rate).max(0.0);
        }

        // Bloom decays after a short delay.
        let sp = &spec.spread_deg;
        if self.since_shot as f32 * dt >= sp.bloom_decay_delay_s {
            self.bloom_deg = (self.bloom_deg - sp.bloom_decay_deg_per_s * dt).max(0.0);
        }
        // The recoil pattern restarts after a pause.
        if let RecoilSpec::Pattern(p) = &spec.recoil {
            if self.since_shot as f32 * dt >= p.reset_after_s {
                self.burst = 0;
            }
        } else {
            self.burst = 0;
        }

        if !self.is_ready() {
            return ev;
        }

        // Fire mode toggle.
        if b.pressed(prev, Buttons::FIRE_MODE) && spec.fire_modes.len() > 1 {
            let i = spec.fire_modes.iter().position(|m| *m == self.fire_mode).unwrap_or(0);
            self.fire_mode = spec.fire_modes[(i + 1) % spec.fire_modes.len()];
            ev.fire_mode_changed = true;
        }

        // Reload / mag check.
        if b.pressed(prev, Buttons::RELOAD) && self.mag < loadout.mag_capacity && self.loaded_spares() > 0 {
            let kind = if self.mag == 0 { ReloadKind::Empty } else { ReloadKind::Tactical };
            let s = match kind {
                ReloadKind::Tactical => spec.reload_tactical_s,
                ReloadKind::Empty => spec.reload_empty_s,
            } * loadout.mods.reload;
            self.action = WeaponAction::Reloading { left: secs_to_ticks(s, hz).max(1), kind };
            self.ads = 0.0;
            ev.reload_started = Some(kind);
            return ev;
        }
        if b.pressed(prev, Buttons::MAG_CHECK) && !lowered {
            self.action = WeaponAction::MagChecking { left: secs_to_ticks(spec.mag_check_s, hz).max(1) };
            ev.mag_check_started = true;
            return ev;
        }

        // Fire.
        let wants_fire = match self.fire_mode {
            FireMode::Auto => b.held(Buttons::FIRE),
            FireMode::Semi | FireMode::Bolt => b.pressed(prev, Buttons::FIRE),
        };
        if !wants_fire || self.cooldown > 0 || self.sprint_lock > 0 || lowered {
            return ev;
        }
        if self.mag == 0 {
            if b.pressed(prev, Buttons::FIRE) {
                ev.dry_fire = true;
            }
            return ev;
        }
        let spread_deg = self.spread_deg(data, spec, loadout, env);
        self.mag -= 1;
        self.cooldown = fire_interval_ticks(spec, hz);
        self.burst = self.burst.saturating_add(1);
        self.since_shot = 0;
        self.shot_seq = self.shot_seq.wrapping_add(1);
        let (bloom_add, bloom_max) = (
            lerp(sp.bloom_per_shot_hip, sp.bloom_per_shot_ads, self.ads),
            lerp(sp.bloom_max_hip, sp.bloom_max_ads, self.ads),
        );
        self.bloom_deg = (self.bloom_deg + bloom_add).min(bloom_max.max(self.bloom_deg));
        let (kick_pitch, kick_yaw) = self.recoil_kick(data, spec, loadout, env);
        ev.shot = Some(Shot { seq: self.shot_seq, spread_deg, kick_pitch, kick_yaw });
        ev
    }

    fn finish_reload(&mut self, kind: ReloadKind) {
        // Take the fullest spare; a tactical reload puts the old mag back in the pouch.
        let Some((i, _)) = self.spares.iter().enumerate().max_by_key(|(_, r)| **r) else { return };
        let fresh = self.spares.remove(i);
        if kind == ReloadKind::Tactical && self.mag > 0 {
            self.spares.push(self.mag);
        }
        self.mag = fresh;
    }

    /// Current spread cone half-angle in degrees.
    pub fn spread_deg(&self, _data: &GameData, spec: &WeaponSpec, loadout: &WeaponLoadout, env: &WeaponEnv) -> f32 {
        let sp = &spec.spread_deg;
        let hip = loadout.mods.hip_spread;
        let ads_still = match sp.ads_unsettled {
            Some(u) if self.ads < 1.0 => u,
            _ => sp.ads_still,
        };
        let still = lerp(sp.hip_still * hip, ads_still, self.ads);
        let moving = lerp(sp.move_full_hip * hip, sp.move_full_ads, self.ads);
        let t = ((env.speed_frac - sp.move_threshold_frac) / (1.0 - sp.move_threshold_frac)).clamp(0.0, 1.0);
        let mut s = lerp(still, moving, t);
        if env.crouched {
            s *= sp.crouch_mult;
        }
        s = match env.mode {
            MoveMode::Air => s.max(sp.air),
            MoveMode::Slide => s.max(sp.slide),
            MoveMode::Zipline => s.max(sp.zipline),
            MoveMode::Jetpack => s.max(sp.jetpack),
            _ => s,
        };
        s + self.bloom_deg
    }

    fn recoil_kick(&self, data: &GameData, spec: &WeaponSpec, loadout: &WeaponLoadout, env: &WeaponEnv) -> (f32, f32) {
        let arms = if env.broken_arms { data.combat.broken_arms.recoil_mult } else { 1.0 };
        match &spec.recoil {
            RecoilSpec::Pattern(p) => {
                let Some(pattern) = data.recoil_pattern(spec) else { return (0.0, 0.0) };
                let (kp, ky) = pattern.kick(self.burst as u32);
                let mut m = lerp(p.hip_mult, p.ads_mult, self.ads) * arms;
                if env.crouched {
                    m *= p.crouch_mult;
                }
                (kp * m * loadout.mods.recoil_v, ky * m * loadout.mods.recoil_h)
            }
            RecoilSpec::Kick(k) => {
                let mut rng = SplitMix::from_parts(&[self.shot_seq as u64, 0x4b49_434b]);
                (
                    k.kick_pitch_deg * arms * loadout.mods.recoil_v,
                    k.kick_yaw_rand_deg * rng.next_signed() * arms * loadout.mods.recoil_h,
                )
            }
        }
    }
}

fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// The direction a shot actually travels: the view direction, deflected inside the spread cone by a
/// deterministic random offset (same seed on client and host).
pub fn shot_direction(yaw: f32, pitch: f32, spread_deg: f32, seed: u64) -> Vec3 {
    let forward = view_dir(yaw, pitch);
    if spread_deg <= 0.0 {
        return forward;
    }
    let mut rng = SplitMix::new(seed);
    let r = spread_deg.to_radians() * rng.next_f32().sqrt();
    let theta = rng.next_f32() * std::f32::consts::TAU;
    let right = view_dir(yaw - std::f32::consts::FRAC_PI_2, 0.0);
    let up = right.cross(forward).normalize();
    let tan = r.tan();
    (forward + right * (theta.cos() * tan) + up * (theta.sin() * tan)).normalize()
}

/// Seed for a player's shot (player id and shot number).
pub fn shot_seed(player: u64, seq: u32) -> u64 {
    SplitMix::from_parts(&[player, seq as u64, 0x5348_4f54]).next_u64()
}

pub fn is_sniper(spec: &WeaponSpec) -> bool {
    spec.cls == WeaponClass::BoltSniper
}

#[cfg(test)]
mod tests {
    use super::*;
    use glam::Vec2;

    fn setup(weapon: &str) -> (GameData, WeaponLoadout, WeaponState) {
        let d = GameData::embedded();
        let l = WeaponLoadout::resolve(&d, weapon, &[], 3).unwrap();
        let mut s = WeaponState::new(&d, &l);
        s.action = WeaponAction::Ready;
        (d, l, s)
    }

    fn still() -> WeaponEnv {
        WeaponEnv { mode: MoveMode::Ground, sprinting: false, crouched: false, speed_frac: 0.0, broken_arms: false }
    }

    fn input(bits: u16) -> InputFrame {
        InputFrame { movement: Vec2::ZERO, yaw: 0.0, pitch: 0.0, buttons: Buttons(bits) }
    }

    #[test]
    fn fire_interval_from_rpm() {
        let d = GameData::embedded();
        assert_eq!(fire_interval_ticks(d.weapon("ar7_mako").unwrap(), 60), 5);
        assert_eq!(fire_interval_ticks(d.weapon("vk50_warden").unwrap(), 60), 75);
    }

    #[test]
    fn default_loadout_fills_categories() {
        let d = GameData::embedded();
        let l = WeaponLoadout::resolve(&d, "ar7_mako", &["mag_45".into(), "optic_3x".into()], 2).unwrap();
        assert_eq!(l.mag_capacity, 45);
        assert_eq!(l.zoom, 3.0);
        assert!(l.attachments.contains(&"mako_stock_standard".to_string()));
        assert!(!l.attachments.contains(&"mag_30".to_string()));
        // optics that do not fit are ignored
        let l = WeaponLoadout::resolve(&d, "ar7_mako", &["optic_sniper".into()], 2).unwrap();
        assert_eq!(l.zoom, 1.25);
    }

    #[test]
    fn auto_fire_rate_and_mag() {
        let (d, l, mut s) = setup("ar7_mako");
        let mut shots = 0;
        let mut first = None;
        for t in 0..300 {
            let ev = s.step(&d, &l, &input(Buttons::FIRE), &still());
            if ev.shot.is_some() {
                shots += 1;
                first.get_or_insert(t);
            }
        }
        assert_eq!(shots, 30, "one magazine, then dry");
        assert_eq!(s.mag, 0);
        // 30 shots at 5 ticks each take 145 ticks after the first
        assert_eq!(first, Some(0));
    }

    #[test]
    fn semi_needs_trigger_release() {
        let (d, l, mut s) = setup("ar7_mako");
        s.fire_mode = FireMode::Semi;
        let shots = (0..60).filter(|_| s.step(&d, &l, &input(Buttons::FIRE), &still()).shot.is_some()).count();
        assert_eq!(shots, 1);
    }

    #[test]
    fn tactical_reload_keeps_partial_mag() {
        let (d, l, mut s) = setup("ar7_mako");
        for _ in 0..50 {
            s.step(&d, &l, &input(Buttons::FIRE), &still());
        }
        let left = s.mag;
        assert!(left > 0 && left < 30);
        s.step(&d, &l, &input(0), &still());
        let ev = s.step(&d, &l, &input(Buttons::RELOAD), &still());
        assert_eq!(ev.reload_started, Some(ReloadKind::Tactical));
        let ticks = secs_to_ticks(2.1, 60);
        let mut done = 0;
        for t in 1..=ticks {
            if s.step(&d, &l, &input(0), &still()).reload_finished {
                done = t;
            }
        }
        assert_eq!(done, ticks);
        assert_eq!(s.mag, 30);
        assert_eq!(s.spares.len(), 3);
        assert!(s.spares.contains(&left));
    }

    #[test]
    fn mag_check_reports_estimate_only() {
        let (d, l, mut s) = setup("ar7_mako");
        s.mag = 14;
        s.step(&d, &l, &input(Buttons::MAG_CHECK), &still());
        let mut est = None;
        for _ in 0..70 {
            if let Some(e) = s.step(&d, &l, &input(0), &still()).mag_checked {
                est = Some(e);
            }
        }
        assert_eq!(est, Some(MagEstimate::AboutHalf));
        assert_eq!(s.card.map(|c| c.estimate), Some(MagEstimate::AboutHalf));
    }

    #[test]
    fn mag_check_is_cancelled_by_fire() {
        let (d, l, mut s) = setup("ar7_mako");
        s.step(&d, &l, &input(Buttons::MAG_CHECK), &still());
        s.step(&d, &l, &input(Buttons::FIRE), &still());
        assert!(s.is_ready());
        assert!(s.card.is_none());
    }

    #[test]
    fn estimates() {
        assert_eq!(MagEstimate::from_rounds(0, 30), MagEstimate::Empty);
        assert_eq!(MagEstimate::from_rounds(3, 30), MagEstimate::AlmostEmpty);
        assert_eq!(MagEstimate::from_rounds(15, 30), MagEstimate::AboutHalf);
        assert_eq!(MagEstimate::from_rounds(29, 30), MagEstimate::NearlyFull);
        assert_eq!(MagEstimate::from_rounds(30, 30), MagEstimate::Full);
        assert_eq!(MagEstimate::from_rounds(1, 5), MagEstimate::LessThanHalf);
    }

    #[test]
    fn sprint_blocks_fire_until_gun_is_up() {
        let (d, l, mut s) = setup("ar7_mako");
        let mut env = still();
        env.sprinting = true;
        assert!(s.step(&d, &l, &input(Buttons::FIRE), &env).shot.is_none());
        env.sprinting = false;
        let wait = secs_to_ticks(0.2, 60);
        let mut first = 0;
        for t in 1..30 {
            if s.step(&d, &l, &input(Buttons::FIRE), &env).shot.is_some() {
                first = t;
                break;
            }
        }
        assert_eq!(first, wait as i32);
    }

    #[test]
    fn spread_grows_with_movement_and_air() {
        let (d, l, s) = setup("ar7_mako");
        let spec = l.spec(&d);
        let mut env = still();
        let base = s.spread_deg(&d, spec, &l, &env);
        assert!((base - 0.7).abs() < 1e-5);
        env.speed_frac = 1.0;
        assert!((s.spread_deg(&d, spec, &l, &env) - 2.6).abs() < 1e-5);
        env.mode = MoveMode::Air;
        assert!((s.spread_deg(&d, spec, &l, &env) - 4.0).abs() < 1e-5);
    }

    #[test]
    fn ads_tightens_spread() {
        let (d, l, mut s) = setup("ar7_mako");
        for _ in 0..30 {
            s.step(&d, &l, &input(Buttons::ADS), &still());
        }
        assert_eq!(s.ads, 1.0);
        let spec = l.spec(&d);
        assert!((s.spread_deg(&d, spec, &l, &still()) - 0.08).abs() < 1e-5);
    }

    #[test]
    fn recoil_follows_pattern() {
        let (d, l, mut s) = setup("ar7_mako");
        let mut kicks = vec![];
        for _ in 0..20 {
            if let Some(shot) = s.step(&d, &l, &input(Buttons::FIRE), &still()).shot {
                kicks.push((shot.kick_pitch, shot.kick_yaw));
            }
        }
        assert_eq!(kicks[0], (0.55, 0.0));
        assert_eq!(kicks[1], (0.6, 0.02));
    }

    #[test]
    fn shot_direction_stays_in_cone() {
        let fwd = view_dir(0.4, 0.1);
        for seq in 0..500 {
            let d = shot_direction(0.4, 0.1, 2.0, shot_seed(9, seq));
            let ang = fwd.angle_between(d).to_degrees();
            assert!(ang <= 2.0 + 1e-3, "{ang}");
        }
        assert_eq!(shot_direction(0.4, 0.1, 1.0, 5), shot_direction(0.4, 0.1, 1.0, 5));
    }
}
