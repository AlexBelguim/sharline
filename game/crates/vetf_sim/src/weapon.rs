//! Weapon state machine: fire rate, fire modes, reloads, mag checks, ADS, spread and bloom.
//!
//! Timers are counted in fixed ticks so predicted and authoritative copies compare exactly.
//! Hard rule: the player never sees an exact round count. The HUD only gets a [`MagEstimate`] from a
//! mag check, and the round counts here stay internal.

use crate::data::{
    AmmoChoice, AmmoSpec, AttachmentCategory, FireMode, GameData, ModifierTotals, RecoilSpec, WeaponClass, WeaponSpec,
    Zoom,
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
/// Aiming down sights slows automatic fire by `ads_rpm_mult` (720 -> 612 RPM rounds to 6 ticks).
pub fn fire_interval_ticks(w: &WeaponSpec, tick_hz: u32, aimed: bool) -> u16 {
    let rpm = if aimed { w.rpm * w.ads_rpm_mult } else { w.rpm };
    let s = w.bolt_cycle_s.unwrap_or(60.0 / rpm);
    secs_to_ticks(s, tick_hz).max(1)
}

/// The gun counts as aimed for fire rate and first-shot accuracy past this ADS progress.
pub const ADS_AIMED: f32 = 0.9;

// ---------------------------------------------------------------------------------------------- loadout

/// Most magazines a loadout can carry. Each has a fixed slot (1..=6) the player learns.
pub const MAX_MAGS: usize = 6;

/// A weapon with its attachments resolved: fixed for one life.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WeaponLoadout {
    pub weapon: u8,
    /// Magazines in slot order, each with its own ammo. Slot 1 (index 0) starts in the gun, and a
    /// magazine always goes back to its own slot, so players learn where their good rounds sit.
    pub mags: Vec<AmmoSpec>,
    pub attachments: Vec<String>,
    pub mag_capacity: u16,
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
    /// Resolve a weapon id, its magazines (in slot order) and attachment ids. Attachments that do not
    /// fit are ignored; missing categories fall back to the weapon's defaults (so every gun always has a
    /// magazine). Ammo the gun cannot load falls back to standard; past [`MAX_MAGS`] are dropped, and
    /// no magazines at all means one standard magazine.
    pub fn resolve(data: &GameData, weapon_id: &str, mags: &[AmmoChoice], attachments: &[String]) -> Option<Self> {
        let weapon = data.weapon_index(weapon_id)?;
        let spec = &data.weapons.weapons[weapon];
        let standard = data.ammo_for(spec, AmmoChoice::STANDARD)?;
        let mut mags: Vec<AmmoSpec> =
            mags.iter().take(MAX_MAGS).map(|c| data.ammo_for(spec, *c).unwrap_or_else(|| standard.clone())).collect();
        if mags.is_empty() {
            mags.push(standard);
        }
        let fits = |id: &str| data.attachment(id).filter(|a| a.fits.iter().any(|f| f == weapon_id));
        let mut chosen: Vec<&crate::data::AttachmentSpec> = Vec::new();
        for id in attachments {
            if let Some(a) = fits(id)
                && !chosen.iter().any(|c| c.cat == a.cat)
            {
                chosen.push(a);
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
            mags,
            attachments: chosen.iter().map(|a| a.id.clone()).collect(),
            mag_capacity,
            zoom,
            mods: ModifierTotals::combine(chosen.iter().copied()).into(),
        })
    }

    pub fn spec<'a>(&self, data: &'a GameData) -> &'a WeaponSpec {
        &data.weapons.weapons[self.weapon as usize]
    }

    /// Resolve the default loadout from rules.ron.
    pub fn default_for(data: &GameData) -> Self {
        let l = &data.rules.default_loadout;
        Self::resolve(data, &l.primary, &l.mags, &l.attachments).expect("valid default loadout")
    }

    /// The ammo in magazine slot `slot` (0-based).
    pub fn ammo(&self, slot: u8) -> &AmmoSpec {
        &self.mags[(slot as usize).min(self.mags.len() - 1)]
    }

    /// Gear-budget points for the ammo: each magazine is priced on its own.
    pub fn ammo_gear_cost(&self) -> u32 {
        self.mags.iter().map(|m| m.gear_cost).sum()
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
    Equipping {
        left: u16,
    },
    /// Swapping to the magazine in `slot` (0-based).
    Reloading {
        left: u16,
        kind: ReloadKind,
        slot: u8,
    },
    MagChecking {
        left: u16,
    },
}

/// The result card a mag check leaves on the HUD for a few seconds: an estimate, and which magazine
/// (slot, so its ammo) is in the gun.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct MagCard {
    pub estimate: MagEstimate,
    pub slot: u8,
    pub left: u16,
}

/// Seconds the mag check card stays up (design/ui mockup 02: "card stays 3 s").
pub const MAG_CARD_S: f32 = 3.0;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WeaponState {
    pub fire_mode: FireMode,
    /// Rounds in each magazine, by slot (see [`WeaponLoadout::mags`]). Internal only: never shown.
    pub rounds: Vec<u16>,
    /// The slot (0-based) of the magazine in the gun. The others sit in the pouch.
    pub loaded: u8,
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
    /// The magazine slot it came from: its ammo decides the damage.
    pub ammo_slot: u8,
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
            rounds: vec![loadout.mag_capacity; loadout.mags.len()],
            loaded: 0,
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

    /// Rounds in the magazine in the gun. Internal only: never shown.
    pub fn mag(&self) -> u16 {
        self.rounds.get(self.loaded as usize).copied().unwrap_or(0)
    }

    fn mag_mut(&mut self) -> &mut u16 {
        let i = self.loaded as usize;
        &mut self.rounds[i]
    }

    /// Whether the magazine in `slot` still holds rounds. The reload radial may dim spent magazines
    /// (you emptied them yourself); it never shows how many rounds are left.
    pub fn slot_has_rounds(&self, slot: u8) -> bool {
        self.rounds.get(slot as usize).is_some_and(|r| *r > 0)
    }

    /// The magazine a tap of reload takes: the next slot after the one in the gun, in slot order
    /// (wrapping), that still holds rounds.
    pub fn next_slot(&self) -> Option<u8> {
        let n = self.rounds.len();
        (1..n).map(|k| ((self.loaded as usize + k) % n) as u8).find(|s| self.slot_has_rounds(*s))
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
            WeaponAction::Reloading { left, slot, .. } => {
                *left = left.saturating_sub(1);
                if *left == 0 {
                    // The old magazine goes back to its own slot, rounds and all.
                    self.loaded = *slot;
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
                        let est = MagEstimate::from_rounds(self.mag(), loadout.mag_capacity);
                        let left = secs_to_ticks(MAG_CARD_S, hz);
                        self.card = Some(MagCard { estimate: est, slot: self.loaded, left });
                        self.action = WeaponAction::Ready;
                        ev.mag_checked = Some(est);
                    }
                }
            }
        }

        // ADS.
        let can_ads =
            self.is_ready() && !lowered && !(env.mode == MoveMode::Jetpack && !data.movement.jetpack.ads_allowed);
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

        // Reload: a picked slot (reload radial) swaps to that magazine even from a full one; a tap of
        // reload takes the next slot in order, unless the magazine in the gun is full.
        let target = match input.reload_slot {
            0 if b.pressed(prev, Buttons::RELOAD) && self.mag() < loadout.mag_capacity => self.next_slot(),
            0 => None,
            k => Some(k - 1).filter(|s| *s != self.loaded && self.slot_has_rounds(*s)),
        };
        if let Some(slot) = target {
            let kind = if self.mag() == 0 { ReloadKind::Empty } else { ReloadKind::Tactical };
            let s = match kind {
                ReloadKind::Tactical => spec.reload_tactical_s,
                ReloadKind::Empty => spec.reload_empty_s,
            } * loadout.mods.reload;
            self.action = WeaponAction::Reloading { left: secs_to_ticks(s, hz).max(1), kind, slot };
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
        if self.mag() == 0 {
            if b.pressed(prev, Buttons::FIRE) {
                ev.dry_fire = true;
            }
            return ev;
        }
        let spread_deg = self.spread_deg(data, spec, loadout, env);
        *self.mag_mut() -= 1;
        self.cooldown = fire_interval_ticks(spec, hz, self.ads >= ADS_AIMED);
        self.burst = self.burst.saturating_add(1);
        self.since_shot = 0;
        self.shot_seq = self.shot_seq.wrapping_add(1);
        // Bloom only builds while moving: standing still, the learnable pattern is the whole story.
        let (bloom_add, bloom_max) = (
            lerp(sp.bloom_per_shot_hip, sp.bloom_per_shot_ads, self.ads) * movement_factor(spec, env),
            lerp(sp.bloom_max_hip, sp.bloom_max_ads, self.ads),
        );
        self.bloom_deg = (self.bloom_deg + bloom_add).min(bloom_max.max(self.bloom_deg));
        let (kick_pitch, kick_yaw) = self.recoil_kick(data, spec, loadout, env);
        ev.shot = Some(Shot { seq: self.shot_seq, ammo_slot: self.loaded, spread_deg, kick_pitch, kick_yaw });
        ev
    }

    /// True when the next shot is the first of a burst (the recoil pattern has reset).
    pub fn first_shot(&self, spec: &WeaponSpec, tick_hz: u32) -> bool {
        let reset = match &spec.recoil {
            RecoilSpec::Pattern(p) => p.reset_after_s,
            RecoilSpec::Kick(_) => 0.0,
        };
        self.burst == 0 || self.since_shot as f32 / tick_hz as f32 >= reset
    }

    /// Current spread cone half-angle in degrees.
    pub fn spread_deg(&self, data: &GameData, spec: &WeaponSpec, loadout: &WeaponLoadout, env: &WeaponEnv) -> f32 {
        let sp = &spec.spread_deg;
        // An aimed first shot is accurate in the air and with slight movement (most guns).
        if let Some(fs) = spec.ads_first_shot
            && self.ads >= ADS_AIMED
            && self.first_shot(spec, data.net.tick_hz)
        {
            let ok = match env.mode {
                MoveMode::Air | MoveMode::Jetpack => fs.air_accurate,
                MoveMode::Ground => env.speed_frac <= fs.move_tolerance_frac,
                _ => false,
            };
            if ok {
                let mut s = sp.ads_still;
                if env.crouched {
                    s *= sp.crouch_mult;
                }
                return s;
            }
        }
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
                let Some(pattern) = data.recoil_pattern(spec) else {
                    return (0.0, 0.0);
                };
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

/// 0 when standing still (below the movement threshold), 1 at full movement speed or airborne.
fn movement_factor(spec: &WeaponSpec, env: &WeaponEnv) -> f32 {
    if !matches!(env.mode, MoveMode::Ground) {
        return 1.0;
    }
    let th = spec.spread_deg.move_threshold_frac;
    ((env.speed_frac - th) / (1.0 - th)).clamp(0.0, 1.0)
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
        let l = WeaponLoadout::resolve(&d, weapon, &[AmmoChoice::STANDARD; 4], &[]).unwrap();
        let mut s = WeaponState::new(&d, &l);
        s.action = WeaponAction::Ready;
        (d, l, s)
    }

    fn still() -> WeaponEnv {
        WeaponEnv { mode: MoveMode::Ground, sprinting: false, crouched: false, speed_frac: 0.0, broken_arms: false }
    }

    fn input(bits: u16) -> InputFrame {
        InputFrame { movement: Vec2::ZERO, yaw: 0.0, pitch: 0.0, buttons: Buttons(bits), reload_slot: 0 }
    }

    fn pick(slot: u8) -> InputFrame {
        InputFrame { reload_slot: slot, ..input(0) }
    }

    fn run_reload(d: &GameData, l: &WeaponLoadout, s: &mut WeaponState) -> u16 {
        let mut done = 0;
        for t in 1..=400 {
            if s.step(d, l, &input(0), &still()).reload_finished {
                done = t;
                break;
            }
        }
        done
    }

    #[test]
    fn fire_interval_from_rpm() {
        let d = GameData::embedded();
        assert_eq!(fire_interval_ticks(d.weapon("ar7_mako").unwrap(), 60, false), 5);
        assert_eq!(fire_interval_ticks(d.weapon("ar7_mako").unwrap(), 60, true), 6);
        assert_eq!(fire_interval_ticks(d.weapon("vk50_warden").unwrap(), 60, false), 75);
        assert_eq!(fire_interval_ticks(d.weapon("vk50_warden").unwrap(), 60, true), 75);
    }

    #[test]
    fn default_loadout_fills_categories() {
        let d = GameData::embedded();
        let l =
            WeaponLoadout::resolve(&d, "ar7_mako", &[AmmoChoice::STANDARD; 2], &["mag_45".into(), "optic_3x".into()])
                .unwrap();
        assert_eq!(l.ammo(0).label, "STD");
        assert_eq!(l.mags.len(), 2);
        assert_eq!(l.mag_capacity, 45);
        assert_eq!(l.zoom, 3.0);
        assert!(l.attachments.contains(&"mako_stock_standard".to_string()));
        assert!(!l.attachments.contains(&"mag_30".to_string()));
        // optics that do not fit are ignored
        let slug = AmmoChoice { kind: crate::data::AmmoKind::Slug, tier: 1 };
        let l = WeaponLoadout::resolve(&d, "ar7_mako", &[slug], &["optic_sniper".into()]).unwrap();
        assert_eq!(l.zoom, 1.25);
        assert_eq!(l.ammo(0).choice, AmmoChoice::STANDARD, "ammo the gun cannot load falls back to standard");
        let l = WeaponLoadout::resolve(&d, "ar7_mako", &[], &[]).unwrap();
        assert_eq!(l.mags.len(), 1, "a gun always has a magazine");
        let l = WeaponLoadout::resolve(&d, "ar7_mako", &[AmmoChoice::STANDARD; 9], &[]).unwrap();
        assert_eq!(l.mags.len(), MAX_MAGS);
        WeaponLoadout::default_for(&d);
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
        assert_eq!(s.mag(), 0);
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
        let left = s.mag();
        assert!(left > 0 && left < 30);
        s.step(&d, &l, &input(0), &still());
        let ev = s.step(&d, &l, &input(Buttons::RELOAD), &still());
        assert_eq!(ev.reload_started, Some(ReloadKind::Tactical));
        assert_eq!(run_reload(&d, &l, &mut s), secs_to_ticks(2.1, 60));
        assert_eq!((s.loaded, s.mag()), (1, 30), "a tap takes the next slot");
        assert_eq!(s.rounds[0], left, "the partial magazine goes back to slot 1");
    }

    #[test]
    fn tap_reload_walks_the_slots_in_order_and_skips_spent_ones() {
        let (d, l, mut s) = setup("ar7_mako");
        s.rounds = vec![5, 0, 30, 30];
        s.step(&d, &l, &input(Buttons::RELOAD), &still());
        run_reload(&d, &l, &mut s);
        assert_eq!(s.loaded, 2, "slot 2 is spent, so slot 3");
        s.rounds[2] = 1;
        s.step(&d, &l, &input(Buttons::RELOAD), &still());
        run_reload(&d, &l, &mut s);
        s.step(&d, &l, &input(0), &still());
        assert_eq!(s.loaded, 3);
        s.rounds[3] = 0;
        let ev = s.step(&d, &l, &input(Buttons::RELOAD), &still());
        assert_eq!(ev.reload_started, Some(ReloadKind::Empty));
        run_reload(&d, &l, &mut s);
        assert_eq!((s.loaded, s.mag()), (0, 5), "wraps round to slot 1 and its partial magazine");
        // a full magazine ignores a tap
        s.rounds[0] = 30;
        s.step(&d, &l, &input(0), &still());
        assert_eq!(s.step(&d, &l, &input(Buttons::RELOAD), &still()).reload_started, None);
    }

    #[test]
    fn picking_a_slot_swaps_even_from_a_full_magazine() {
        let d = GameData::embedded();
        let ap = AmmoChoice { kind: crate::data::AmmoKind::ArmorPiercing, tier: 2 };
        let l = WeaponLoadout::resolve(&d, "ar7_mako", &[AmmoChoice::STANDARD, AmmoChoice::STANDARD, ap], &[]).unwrap();
        let mut s = WeaponState::new(&d, &l);
        s.action = WeaponAction::Ready;
        assert_eq!(s.step(&d, &l, &pick(1), &still()).reload_started, None, "already in the gun");
        assert_eq!(s.step(&d, &l, &pick(9), &still()).reload_started, None, "no such slot");
        assert_eq!(s.step(&d, &l, &pick(3), &still()).reload_started, Some(ReloadKind::Tactical));
        run_reload(&d, &l, &mut s);
        assert_eq!(s.loaded, 2);
        let shot = s.step(&d, &l, &input(Buttons::FIRE), &still()).shot.unwrap();
        assert_eq!(shot.ammo_slot, 2);
        assert_eq!(l.ammo(shot.ammo_slot).label, "AP II");
        assert_eq!(s.rounds, vec![30, 30, 29]);
        s.rounds[0] = 0;
        assert_eq!(s.step(&d, &l, &pick(1), &still()).reload_started, None, "a spent magazine");
    }

    #[test]
    fn mag_check_reports_estimate_only() {
        let (d, l, mut s) = setup("ar7_mako");
        s.rounds[0] = 14;
        s.step(&d, &l, &input(Buttons::MAG_CHECK), &still());
        let mut est = None;
        for _ in 0..70 {
            if let Some(e) = s.step(&d, &l, &input(0), &still()).mag_checked {
                est = Some(e);
            }
        }
        assert_eq!(est, Some(MagEstimate::AboutHalf));
        assert_eq!(s.card.map(|c| (c.estimate, c.slot)), Some((MagEstimate::AboutHalf, 0)));
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
    fn standing_still_has_no_bloom_moving_does() {
        let (d, l, mut s) = setup("ar7_mako");
        for _ in 0..30 {
            s.step(&d, &l, &input(Buttons::FIRE), &still());
        }
        assert_eq!(s.bloom_deg, 0.0, "pattern only when still");
        let (d, l, mut s) = setup("ar7_mako");
        let mut moving = still();
        moving.speed_frac = 1.0;
        for _ in 0..30 {
            s.step(&d, &l, &input(Buttons::FIRE), &moving);
        }
        assert!(s.bloom_deg > 0.3, "{}", s.bloom_deg);
    }

    #[test]
    fn aimed_first_shot_is_accurate_in_air_and_slight_movement() {
        let (d, l, mut s) = setup("ar7_mako");
        s.ads = 1.0;
        let spec = l.spec(&d);
        let mut env = still();
        env.mode = MoveMode::Air;
        assert!((s.spread_deg(&d, spec, &l, &env) - 0.08).abs() < 1e-5);
        env.mode = MoveMode::Ground;
        env.speed_frac = 0.3;
        assert!((s.spread_deg(&d, spec, &l, &env) - 0.08).abs() < 1e-5);
        env.speed_frac = 0.9;
        assert!(s.spread_deg(&d, spec, &l, &env) > 0.5, "running still costs accuracy");
        // follow-up shots in a burst lose the first-shot bonus in the air
        env = still();
        env.mode = MoveMode::Air;
        s.burst = 3;
        s.since_shot = 2;
        assert!(s.spread_deg(&d, spec, &l, &env) >= 4.0);
    }

    #[test]
    fn sniper_has_no_air_first_shot_bonus() {
        let (d, l, mut s) = setup("vk50_warden");
        s.ads = 1.0;
        let mut env = still();
        env.mode = MoveMode::Air;
        assert!(s.spread_deg(&d, l.spec(&d), &l, &env) >= 8.0);
    }

    #[test]
    fn aiming_slows_auto_fire() {
        let (d, l, mut s) = setup("ar7_mako");
        let both = Buttons::FIRE | Buttons::ADS;
        let mut ticks = vec![];
        for t in 0..60 {
            if s.step(&d, &l, &input(both), &still()).shot.is_some() {
                ticks.push(t);
            }
        }
        let gaps: Vec<_> = ticks.windows(2).map(|w| w[1] - w[0]).collect();
        assert!(gaps.iter().skip(3).all(|g| *g == 6), "{gaps:?}");
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
