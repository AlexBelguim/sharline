//! Weapon state machine: fire rate, fire modes, reloads, mag checks, ADS, spread and bloom.
//!
//! Timers are counted in fixed ticks so predicted and authoritative copies compare exactly.
//! The player normally never sees an exact round count: the HUD only gets a [`MagEstimate`] from a mag check.
//! The one exception is the [`MagCheckMode::Exact`] option (user direction 2026-10-09): a match setting the host
//! picks in the lobby (team deathmatch, free-for-all) or a personal one in the gun range. Off by default.

use crate::data::{
    AmmoChoice, AmmoSpec, AttachmentCategory, FireMode, GameData, ModifierTotals, RecoilSpec, WeaponClass, WeaponSpec,
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

/// The gun counts as aimed for fire rate and accuracy from this ADS progress on.
pub const ADS_AIMED: f32 = 0.9;

/// The player is using the gun: fire or aim held, or a mag check started or under way. Sprinting lowers the
/// gun only while it is not in use (see [`WeaponState::step`]), so a sprinting player can fire, aim and check
/// the magazine without slowing down; the gun comes up from the sprint pose in `sprint_to_fire_s` (user
/// direction 2026-10-08).
pub fn gun_in_use(b: Buttons, action: WeaponAction) -> bool {
    b.held(Buttons::FIRE)
        || b.held(Buttons::ADS)
        || b.held(Buttons::MAG_CHECK)
        || matches!(action, WeaponAction::MagChecking { .. })
}

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
    /// The optic's zoom as it starts (a variable optic's default; 1 without an optic). A variable optic's live
    /// zoom is the aiming player's own (the client's `scope_zoom`) and never goes over the wire.
    pub zoom: f32,
    pub mods: ModTotals,
}

/// Serializable copy of [`ModifierTotals`].
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ModTotals {
    pub ads_time: f32,
    pub move_mult: f32,
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
        let zoom = chosen.iter().find(|a| a.cat == AttachmentCategory::Optic).map_or(1.0, |a| a.start_zoom());
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

/// How exactly a player reads their rounds (user direction 2026-10-09). [`MagCheckMode::Estimate`], the
/// default everywhere, is the genre rule: no counter, a mag check gives a [`MagEstimate`]. With
/// [`MagCheckMode::Exact`] the HUD keeps a counter of the rounds in the gun's magazine, the mag check card and
/// the reload radial give exact counts too. The gun model's magazine window keeps its coarse level either way.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
pub enum MagCheckMode {
    #[default]
    Estimate,
    Exact,
}

impl MagCheckMode {
    pub const ALL: [MagCheckMode; 2] = [MagCheckMode::Estimate, MagCheckMode::Exact];

    pub fn label(self) -> &'static str {
        match self {
            Self::Estimate => "ESTIMATE",
            Self::Exact => "EXACT",
        }
    }

    pub fn is_exact(self) -> bool {
        self == Self::Exact
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
    /// Ticks until the gun is up after sprinting (or an item, or a mantle).
    pub sprint_lock: u16,
    /// A trigger pull that came while the gun was still coming up from a sprint: the gun keeps coming up, and
    /// the shot goes off as soon as it is up (so a quick tap on the run is never lost).
    pub fire_queued: bool,
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
    /// An item is in hand (or was put away this tick, unless a reload put it away): the gun is down like
    /// when sprinting, and no reload.
    pub hands_busy: bool,
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
    /// Fill `count` magazines back to `capacity`: the emptiest spare in the pouch first, the one in the gun
    /// last. Full magazines are skipped. Returns how many were topped up.
    pub fn refill_mags(&mut self, count: u8, capacity: u16) -> u8 {
        let mut done = 0;
        while done < count {
            let loaded = self.loaded as usize;
            let pick = (0..self.rounds.len())
                .filter(|&i| self.rounds[i] < capacity)
                .min_by_key(|&i| (i == loaded, self.rounds[i], i));
            let Some(i) = pick else { break };
            self.rounds[i] = capacity;
            done += 1;
        }
        done
    }

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
            fire_queued: false,
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

    /// The gun is down (sprint, mantle or an item in hand) or still coming up: the viewmodel's sprint pose.
    pub fn lowered(&self) -> bool {
        self.sprint_lock > 0
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

        // Sprinting lowers the gun unless it is in use (firing, aiming, a mag check), still coming down from the
        // eye, or fired a moment ago; a mantle or an item in hand always does. It takes `sprint_to_fire_s` to bring
        // it back up, and the sprint goes on meanwhile.
        let up = gun_in_use(b, self.action)
            || self.fire_queued
            || self.ads > 0.0
            || (self.since_shot as f32 * dt) < data.movement.speed.sprint_gun_hold_s;
        let lowered = (env.sprinting && !up) || env.mode == MoveMode::Mantle || env.hands_busy;
        if lowered {
            self.fire_queued = false;
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
                // Firing, aiming, a mantle or using an item cancels a mag check (a sprint does not).
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

        // ADS: in every movement state but a mantle or an item in hand (and the jetpack, if the data says so).
        let can_ads =
            self.is_ready() && !lowered && !(env.mode == MoveMode::Jetpack && !data.movement.jetpack.ads_allowed);
        let mut ads_time = spec.ads_s * loadout.mods.ads_time;
        if env.broken_arms {
            ads_time *= data.combat.broken_arms.ads_time_mult;
        }
        let ads_rate = dt / ads_time.max(dt);
        let aiming = can_ads && b.held(Buttons::ADS);
        if aiming {
            self.ads = (self.ads + ads_rate).min(1.0);
            // Aim held brings the gun up no slower than the sight: an aimed shot never waits on the raise from the
            // sprint pose once the gun is aimed, whatever this build's ADS time.
            let to_aimed = ((ADS_AIMED - self.ads).max(0.0) / ads_rate - 1e-3).ceil().max(0.0) as u16;
            self.sprint_lock = self.sprint_lock.min(to_aimed);
        } else {
            self.ads = (self.ads - ads_rate).max(0.0);
        }

        // Bloom settles after a short delay.
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

        if !self.is_ready() || env.hands_busy {
            self.fire_queued = false;
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
            self.fire_queued = false;
            ev.reload_started = Some(kind);
            return ev;
        }
        if b.pressed(prev, Buttons::MAG_CHECK) && !lowered {
            self.action = WeaponAction::MagChecking { left: secs_to_ticks(spec.mag_check_s, hz).max(1) };
            self.fire_queued = false;
            ev.mag_check_started = true;
            return ev;
        }

        // Fire. A pull while the gun is still coming up from a sprint waits for it, but only when the raise is the
        // last thing in the way: a pull during a bolt cycle is dropped, as it is standing still. An empty gun clicks
        // on the pull itself (a tap is over long before the gun is up).
        let wants_fire = self.fire_queued
            || match self.fire_mode {
                FireMode::Auto => b.held(Buttons::FIRE),
                FireMode::Semi | FireMode::Bolt => b.pressed(prev, Buttons::FIRE),
            };
        if wants_fire && !lowered && self.sprint_lock > 0 && self.cooldown <= self.sprint_lock {
            if self.mag() == 0 {
                ev.dry_fire |= b.pressed(prev, Buttons::FIRE);
            } else {
                self.fire_queued = true;
            }
        }
        if !wants_fire || self.cooldown > 0 || self.sprint_lock > 0 || lowered {
            return ev;
        }
        self.fire_queued = false;
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
        // Sustained fire blooms only while moving, by how much the player moves: standing still, the fixed pattern
        // is the whole story.
        let bloom_add = sp.bloom_per_shot_hip * move_level(spec, env);
        self.bloom_deg = (self.bloom_deg + bloom_add).min(sp.bloom_max_hip.max(self.bloom_deg));
        let (kick_pitch, kick_yaw) = self.recoil_kick(data, spec, loadout, env);
        ev.shot = Some(Shot { seq: self.shot_seq, ammo_slot: self.loaded, spread_deg, kick_pitch, kick_yaw });
        ev
    }

    /// The random spread cone (half-angle, degrees) a shot fired now gets: the bloom on top of the fixed recoil
    /// pattern (user direction 2026-10-08, DIRECTION_LOG 17).
    ///
    /// - Standing still ([`is_still`]: on the ground under `move_threshold_frac` of jog speed, any stance) it is 0,
    ///   hip or aimed, whatever bloom is left over: the shot goes exactly where the view points.
    /// - Moving, hip fire opens with speed and state ([`move_cone_deg`]: walk < jog < sprint, slide, air, zipline,
    ///   jetpack; the gun's hip attachments scale it) plus the sustained-fire bloom.
    /// - Aimed (from [`ADS_AIMED`] on) the same movement cone counts `ads_move_mult` and the bloom
    ///   `bloom_max_ads / bloom_max_hip`, so aimed shots stay accurate on the move (item 16). The spread blends from
    ///   hip to aimed as the gun comes up.
    /// - Crouched, both are `crouch_mult` tighter.
    ///
    /// Moving is never more accurate than standing still: every term is 0 or more, and the recoil pattern is never
    /// lighter on the move ([`Self::recoil_kick`]). This is also what the crosshair opens by, so it shows the plain
    /// cross for every gun at rest and opens by the real cone on the move.
    pub fn spread_deg(&self, data: &GameData, spec: &WeaponSpec, loadout: &WeaponLoadout, env: &WeaponEnv) -> f32 {
        if is_still(spec, env) {
            return 0.0;
        }
        let sp = &spec.spread_deg;
        let crouch = if env.crouched { sp.crouch_mult } else { 1.0 };
        let cone = move_cone_deg(data, spec, env);
        let hip = cone * loadout.mods.hip_spread + self.bloom_deg;
        let ads = cone * sp.ads_move_mult + self.bloom_deg * aimed_bloom_frac(spec);
        let aimed = (self.ads / ADS_AIMED).clamp(0.0, 1.0);
        lerp(hip, ads, aimed).max(0.0) * crouch
    }

    /// The view kick of the shot just fired (degrees, pitch up +, yaw right +). Fixed, with no randomness: pattern
    /// guns follow their pattern (`recoil_patterns.ron`) by the shot's place in the burst, kick guns kick the same
    /// every shot. Aiming lightens it (`ads_mult`), and crouching does too, but only standing still, so a pattern
    /// on the move is never lighter than the one standing still.
    fn recoil_kick(&self, data: &GameData, spec: &WeaponSpec, loadout: &WeaponLoadout, env: &WeaponEnv) -> (f32, f32) {
        let arms = if env.broken_arms { data.combat.broken_arms.recoil_mult } else { 1.0 };
        match &spec.recoil {
            RecoilSpec::Pattern(p) => {
                let Some(pattern) = data.recoil_pattern(spec) else {
                    return (0.0, 0.0);
                };
                let (kp, ky) = pattern.kick(self.burst as u32);
                let mut m = lerp(p.hip_mult, p.ads_mult, self.ads) * arms;
                if env.crouched && is_still(spec, env) {
                    m *= p.crouch_mult;
                }
                (kp * m * loadout.mods.recoil_v, ky * m * loadout.mods.recoil_h)
            }
            RecoilSpec::Kick(k) => {
                (k.kick_pitch_deg * arms * loadout.mods.recoil_v, k.kick_yaw_deg * arms * loadout.mods.recoil_h)
            }
        }
    }
}

fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// Standing still for the gun: on the ground, under `move_threshold_frac` of jog speed, in any stance. No random
/// spread then, only the fixed recoil pattern.
pub fn is_still(spec: &WeaponSpec, env: &WeaponEnv) -> bool {
    env.mode == MoveMode::Ground && env.speed_frac < spec.spread_deg.move_threshold_frac
}

/// The hip-fire movement cone (degrees, before attachments, crouch and bloom): 0 at the still threshold, then
/// linear through `walk_hip` at walking speed, `move_full_hip` at jog speed and `sprint_hip` at sprint speed (and
/// faster), and never under the floor of the air, a slide, a zipline or the jetpack. Speeds are the movement
/// data's, as fractions of jog speed like [`WeaponEnv::speed_frac`]. 0 standing still.
pub fn move_cone_deg(data: &GameData, spec: &WeaponSpec, env: &WeaponEnv) -> f32 {
    if is_still(spec, env) {
        return 0.0;
    }
    let sp = &spec.spread_deg;
    let speed = &data.movement.speed;
    let curve = [
        (sp.move_threshold_frac, 0.0),
        (speed.walk / speed.jog, sp.walk_hip),
        (1.0, sp.move_full_hip),
        (speed.sprint / speed.jog, sp.sprint_hip),
    ];
    let s = env.speed_frac;
    let mut cone = sp.sprint_hip;
    for w in curve.windows(2) {
        let ((x0, y0), (x1, y1)) = (w[0], w[1]);
        if s <= x1 {
            cone = lerp(y0, y1, ((s - x0) / (x1 - x0).max(1e-6)).clamp(0.0, 1.0));
            break;
        }
    }
    match env.mode {
        MoveMode::Air => cone.max(sp.air),
        MoveMode::Slide => cone.max(sp.slide),
        MoveMode::Zipline => cone.max(sp.zipline),
        MoveMode::Jetpack => cone.max(sp.jetpack),
        _ => cone,
    }
}

/// How much the player moves, for the sustained-fire bloom: 0 standing still, 1 at jog speed or faster, and off
/// the ground.
pub fn move_level(spec: &WeaponSpec, env: &WeaponEnv) -> f32 {
    if is_still(spec, env) {
        return 0.0;
    }
    if env.mode != MoveMode::Ground {
        return 1.0;
    }
    let th = spec.spread_deg.move_threshold_frac;
    ((env.speed_frac - th) / (1.0 - th).max(1e-6)).clamp(0.0, 1.0)
}

/// Aimed, the sustained-fire bloom (kept in hip degrees) counts this much: `bloom_max_ads / bloom_max_hip`.
fn aimed_bloom_frac(spec: &WeaponSpec) -> f32 {
    let sp = &spec.spread_deg;
    if sp.bloom_max_hip > 0.0 { sp.bloom_max_ads / sp.bloom_max_hip } else { 0.0 }
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
        WeaponEnv {
            mode: MoveMode::Ground,
            sprinting: false,
            crouched: false,
            speed_frac: 0.0,
            broken_arms: false,
            hands_busy: false,
        }
    }

    fn input(bits: u16) -> InputFrame {
        InputFrame { movement: Vec2::ZERO, yaw: 0.0, pitch: 0.0, buttons: Buttons(bits), ..Default::default() }
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
        // a variable optic starts at its default zoom (the sniper scope at 6x, the 1-3x at 1x)
        let warden = |optic: &str| WeaponLoadout::resolve(&d, "vk50_warden", &[], &[optic.into()]).unwrap().zoom;
        assert_eq!((warden("optic_sniper"), warden("optic_1_3x"), warden("optic_3x")), (6.0, 1.0, 3.0));
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

    /// The exact count is an option: the estimate is the default everywhere (user direction 2026-10-09).
    #[test]
    fn the_estimate_is_the_default_mag_check() {
        assert_eq!(MagCheckMode::default(), MagCheckMode::Estimate);
        assert!(!MagCheckMode::default().is_exact());
        assert!(MagCheckMode::Exact.is_exact());
        assert_eq!(MagCheckMode::ALL.map(MagCheckMode::label), ["ESTIMATE", "EXACT"]);
    }

    /// The gun comes up `sprint_to_fire_s` after it was lowered, and the sprint itself no longer has to end: firing
    /// while sprinting waits for the gun, then shoots (user direction 2026-10-08).
    #[test]
    fn sprint_blocks_fire_until_gun_is_up() {
        let (d, l, mut s) = setup("ar7_mako");
        let wait = secs_to_ticks(l.spec(&d).sprint_to_fire_s * l.mods.sprint_to_fire, 60) as i32;
        assert!(wait > 1);
        let mut sprint = still();
        sprint.sprinting = true;
        for (env, why) in [(still(), "the sprint ends"), (sprint, "still sprinting")] {
            for _ in 0..5 {
                assert!(s.step(&d, &l, &input(0), &sprint).shot.is_none());
            }
            assert!(s.lowered(), "a sprint lowers an idle gun");
            let first = (1..60).find(|_| s.step(&d, &l, &input(Buttons::FIRE), &env).shot.is_some());
            assert_eq!(first, Some(wait), "{why}");
            assert!(!s.lowered());
            for _ in 0..secs_to_ticks(d.movement.speed.sprint_gun_hold_s, 60) + 1 {
                s.step(&d, &l, &input(0), &sprint);
            }
        }
    }

    /// A one-tick trigger pull on the run is not lost: the gun comes up and the shot goes off when it is up, for
    /// every fire mode. A reload in between drops it.
    #[test]
    fn a_tap_on_the_run_fires_once_the_gun_is_up() {
        for (gun, mode) in [("ar7_mako", FireMode::Semi), ("ar7_mako", FireMode::Auto), ("vk50_warden", FireMode::Bolt)]
        {
            let (d, l, mut s) = setup(gun);
            s.fire_mode = mode;
            let mut sprint = still();
            sprint.sprinting = true;
            s.step(&d, &l, &input(0), &sprint);
            let wait = secs_to_ticks(l.spec(&d).sprint_to_fire_s * l.mods.sprint_to_fire, 60) as usize;
            assert!(s.step(&d, &l, &input(Buttons::FIRE), &sprint).shot.is_none());
            let shots: Vec<usize> = (1..60).filter(|_| s.step(&d, &l, &input(0), &sprint).shot.is_some()).collect();
            // the pull's own tick counts: the shot goes off `sprint_to_fire_s` after it
            assert_eq!(shots, vec![wait - 1], "{gun} {mode:?}: one shot, when the gun is up");
        }
        let (d, l, mut s) = setup("ar7_mako");
        s.rounds[0] = 10;
        let mut sprint = still();
        sprint.sprinting = true;
        s.step(&d, &l, &input(0), &sprint);
        s.step(&d, &l, &input(Buttons::FIRE), &sprint);
        assert!(s.fire_queued);
        assert!(s.step(&d, &l, &input(Buttons::RELOAD), &sprint).reload_started.is_some());
        assert!(!s.fire_queued, "a reload drops the queued shot");
    }

    /// Semi-auto taps on the run keep the gun up between shots; it goes down once it has been idle a while.
    #[test]
    fn the_gun_stays_up_between_taps_on_the_run() {
        let (d, l, mut s) = setup("ar7_mako");
        s.fire_mode = FireMode::Semi;
        let mut sprint = still();
        sprint.sprinting = true;
        let hold = secs_to_ticks(d.movement.speed.sprint_gun_hold_s, 60) as usize;
        let mut shots = vec![];
        for t in 0..120 {
            // a tap every 15 ticks (4 per second)
            let bits = if t % 15 == 0 { Buttons::FIRE } else { 0 };
            if s.step(&d, &l, &input(bits), &sprint).shot.is_some() {
                shots.push(t);
            }
        }
        assert_eq!(shots.len(), 8, "every tap fires: {shots:?}");
        assert!(!s.lowered());
        for _ in 0..hold {
            s.step(&d, &l, &input(0), &sprint);
        }
        assert!(s.lowered(), "idle on the run: down again");
    }

    #[test]
    fn aiming_and_mag_checks_work_while_sprinting() {
        let (d, l, mut s) = setup("ar7_mako");
        let mut sprint = still();
        sprint.sprinting = true;
        s.step(&d, &l, &input(0), &sprint);
        // Aiming in (ads_s) can be quicker than bringing the gun up from the sprint pose (sprint_to_fire_s):
        // hold until both are done.
        let spec = l.spec(&d);
        for _ in 0..=secs_to_ticks(spec.ads_s.max(spec.sprint_to_fire_s * l.mods.sprint_to_fire), 60) {
            s.step(&d, &l, &input(Buttons::ADS), &sprint);
        }
        assert_eq!(s.ads, 1.0, "the gun comes up to the eye on the run");
        assert!(!s.lowered(), "and it is up");
        s.step(&d, &l, &input(0), &sprint);
        assert!(s.ads < 1.0 && !s.lowered(), "aim let go: the gun comes down from the eye first");
        // a tap of mag check while sprinting runs to the end
        for _ in 0..30 {
            s.step(&d, &l, &input(0), &sprint);
        }
        s.step(&d, &l, &input(Buttons::MAG_CHECK), &sprint);
        assert!(matches!(s.action, WeaponAction::MagChecking { .. }));
        let checked = (0..120).any(|_| s.step(&d, &l, &input(0), &sprint).mag_checked.is_some());
        assert!(checked, "a sprint does not cancel the mag check");
    }

    #[test]
    fn a_mantle_or_an_item_still_lowers_the_gun() {
        let (d, l, mut s) = setup("ar7_mako");
        let mut env = still();
        env.mode = MoveMode::Mantle;
        for _ in 0..30 {
            assert!(s.step(&d, &l, &input(Buttons::FIRE | Buttons::ADS), &env).shot.is_none());
        }
        assert_eq!(s.ads, 0.0);
        let mut env = still();
        env.hands_busy = true;
        assert!(s.step(&d, &l, &input(Buttons::FIRE), &env).shot.is_none());
    }

    #[test]
    fn the_jetpack_allows_aiming() {
        let (d, l, mut s) = setup("vk50_warden");
        assert!(d.movement.jetpack.ads_allowed);
        let mut env = still();
        env.mode = MoveMode::Jetpack;
        for _ in 0..60 {
            s.step(&d, &l, &input(Buttons::ADS), &env);
        }
        assert_eq!(s.ads, 1.0);
    }

    /// The Mako's hip cone: none standing still, then 1.2 deg walking, 2.6 jogging, 3.0 sprinting and 4.0 in the air
    /// (playtest round 2: no randomness standing still, Apex-style bloom on the move).
    #[test]
    fn spread_grows_with_movement_and_air() {
        let (d, l, s) = setup("ar7_mako");
        let spec = l.spec(&d);
        let speed = &d.movement.speed;
        let at =
            |speed_frac: f32, mode: MoveMode| s.spread_deg(&d, spec, &l, &WeaponEnv { speed_frac, mode, ..still() });
        assert_eq!(at(0.0, MoveMode::Ground), 0.0);
        assert_eq!(at(0.09, MoveMode::Ground), 0.0, "drifting under the threshold is standing still");
        assert!((at(speed.walk / speed.jog, MoveMode::Ground) - 1.2).abs() < 1e-5);
        assert!((at(1.0, MoveMode::Ground) - 2.6).abs() < 1e-5);
        assert!((at(speed.sprint / speed.jog, MoveMode::Ground) - 3.0).abs() < 1e-5);
        assert!((at(3.0, MoveMode::Ground) - 3.0).abs() < 1e-5, "no more past a sprint");
        assert!((at(0.0, MoveMode::Air) - 4.0).abs() < 1e-5, "in the air, even hanging still at the apex");
    }

    /// Aimed and standing still, the first shot goes exactly where the view points; on the move, aimed spread is a
    /// small fraction of the hip cone.
    #[test]
    fn ads_tightens_spread() {
        let (d, l, mut s) = setup("ar7_mako");
        for _ in 0..30 {
            s.step(&d, &l, &input(Buttons::ADS), &still());
        }
        assert_eq!(s.ads, 1.0);
        let spec = l.spec(&d);
        assert_eq!(s.spread_deg(&d, spec, &l, &still()), 0.0);
        let shot = s.step(&d, &l, &input(Buttons::ADS | Buttons::FIRE), &still()).shot.unwrap();
        assert_eq!(shot.spread_deg, 0.0, "the first aimed shot standing still is exact");
        assert_eq!(shot_direction(0.3, -0.1, shot.spread_deg, shot_seed(4, shot.seq)), view_dir(0.3, -0.1));
        let jog = WeaponEnv { speed_frac: 1.0, ..still() };
        s.bloom_deg = 0.0;
        assert!((s.spread_deg(&d, spec, &l, &jog) - 2.6 * spec.spread_deg.ads_move_mult).abs() < 1e-5);
    }

    #[test]
    fn recoil_follows_pattern() {
        let (d, l, mut s) = setup("ar7_mako");
        let mut kicks = vec![];
        while kicks.len() < 16 {
            if let Some(shot) = s.step(&d, &l, &input(Buttons::FIRE), &still()).shot {
                kicks.push((shot.kick_pitch, shot.kick_yaw));
            }
        }
        assert_eq!(kicks[0], (0.95, 0.0));
        assert_eq!(kicks[1], (1.05, 0.0));
        assert_eq!(kicks[13], (0.8, 0.0), "the stem: rounds 1-15 straight up");
        assert_eq!(kicks[14], (0.45, 0.48), "the T's bar starts after round 15");
    }

    /// Fire `shots` rounds from a standstill (hip, or fully aimed) and add up the view kick (pitch, yaw).
    fn spray_kick(weapon: &str, shots: usize, aimed: bool) -> (f32, f32) {
        let (d, l, mut s) = setup(weapon);
        let bits = if aimed {
            s.ads = 1.0;
            Buttons::FIRE | Buttons::ADS
        } else {
            Buttons::FIRE
        };
        let (mut kick, mut n) = ((0.0, 0.0), 0);
        for _ in 0..600 {
            if n == shots {
                break;
            }
            if let Some(shot) = s.step(&d, &l, &input(bits), &still()).shot {
                kick.0 += shot.kick_pitch;
                kick.1 += shot.kick_yaw;
                n += 1;
            }
        }
        assert_eq!(n, shots, "{weapon}");
        kick
    }

    /// Playtest round 1, "the recoil is way too low on the AR": the Mako's climb after 10 rounds is about twice the
    /// design's (4.37 deg). Round 3 made the pattern a T (DESIGN_DELTAS.md section 15) and the user tuned it: a
    /// 15-round stem, about 70 % more climb and a 60 % wider bar. After 10 rounds it has climbed 11.9 deg straight
    /// up; after 20 it has climbed 16.9 deg and swung 4.16 deg right into the bar. Aimed, every kick is x0.7.
    #[test]
    fn the_mako_climb_is_pinned() {
        let near = |a: (f32, f32), b: (f32, f32)| (a.0 - b.0).abs() < 1e-3 && (a.1 - b.1).abs() < 1e-3;
        for (shots, hip) in [(10, (11.9, 0.0)), (20, (16.9, 4.16))] {
            let got = spray_kick("ar7_mako", shots, false);
            assert!(near(got, hip), "hip {shots}: {got:?}");
            let got = spray_kick("ar7_mako", shots, true);
            assert!(near(got, (hip.0 * 0.7, hip.1 * 0.7)), "aimed {shots}: {got:?}");
        }
        // The Skink's first second (20 rounds at 1200 rpm): the round-2 Mako column x0.6, unchanged.
        let got = spray_kick("sk9_skink", 20, false);
        assert!(near(got, (7.584, -0.222)), "skink: {got:?}");
    }

    /// Every kick of a standing Mako spray (pitch, yaw), fully aimed or from the hip, with `parts` fitted.
    fn mako_spray(parts: &[&str], aimed: bool) -> Vec<(f32, f32)> {
        let d = GameData::embedded();
        let parts: Vec<String> = parts.iter().map(|p| p.to_string()).collect();
        let l = WeaponLoadout::resolve(&d, "ar7_mako", &[AmmoChoice::STANDARD; 4], &parts).unwrap();
        let mut s = WeaponState::new(&d, &l);
        s.action = WeaponAction::Ready;
        spray(&d, &l, &mut s, &still(), aimed, l.mag_capacity as usize)
            .iter()
            .map(|s| (s.kick_pitch, s.kick_yaw))
            .collect()
    }

    /// Playtest round 3 (DIRECTION_LOG 18): with the standard stock and no grip the Mako sprays the plain T from
    /// its pattern, the same every time, for every magazine. Attachments change its size per axis, never its shape:
    /// a stock scales every round's climb by its `recoil_v` and leaves the sweep alone, a front grip scales every
    /// round's sweep by its `recoil_h` and leaves the climb alone, and the two stack.
    #[test]
    fn mako_attachments_scale_the_t_per_axis() {
        let d = GameData::embedded();
        let pattern = &d.recoil_patterns["mako_recoil_pattern"];
        let RecoilSpec::Pattern(p) = &d.weapon("ar7_mako").unwrap().recoil else { panic!("the Mako has a pattern") };
        let near = |a: f32, b: f32| (a - b).abs() < 1e-5;
        for mag in ["mag_30", "mag_45", "mag_drum60"] {
            for aimed in [false, true] {
                let plain = mako_spray(&[mag], aimed);
                assert_eq!(
                    plain,
                    mako_spray(&[mag, "mako_stock_standard"], aimed),
                    "{mag}: the standard stock is plain"
                );
                assert_eq!(plain, mako_spray(&[mag], aimed), "{mag}: deterministic");
                let m = if aimed { p.ads_mult } else { p.hip_mult };
                for (n, k) in plain.iter().enumerate() {
                    let (kp, ky) = pattern.kick(n as u32 + 1);
                    assert!(near(k.0, kp * m) && near(k.1, ky * m), "{mag} aimed {aimed} round {}: {k:?}", n + 1);
                }
                for parts in [
                    &["mako_stock_precision"][..],
                    &["mako_stock_light"],
                    &["grip_vertical"],
                    &["grip_angled"],
                    &["grip_stub"],
                    &["mako_stock_precision", "grip_vertical"],
                ] {
                    let (v, h) = parts
                        .iter()
                        .map(|id| d.attachment(id).unwrap())
                        .fold((1.0, 1.0), |(v, h), a| (v * a.recoil_v.unwrap_or(1.0), h * a.recoil_h.unwrap_or(1.0)));
                    assert!(v < 1.0 || h < 1.0, "{parts:?} lowers some recoil");
                    let mut with: Vec<&str> = parts.to_vec();
                    with.push(mag);
                    for (n, (k, b)) in mako_spray(&with, aimed).iter().zip(&plain).enumerate() {
                        assert!(
                            near(k.0, b.0 * v) && near(k.1, b.1 * h),
                            "{parts:?} {mag} round {}: {k:?} vs {b:?}",
                            n + 1
                        );
                    }
                }
            }
        }
    }

    /// Aiming down sights is fast (playtest round 1): the ADS blend is full after `ads_s`, to the tick.
    #[test]
    fn ads_takes_ads_s() {
        for weapon in ["ar7_mako", "sk9_skink", "vk50_warden"] {
            let (d, l, mut s) = setup(weapon);
            let spec = l.spec(&d);
            let want = (spec.ads_s * l.mods.ads_time * d.net.tick_hz as f32).ceil() as u32;
            let mut ticks = 0;
            while s.ads < 1.0 {
                s.step(&d, &l, &input(Buttons::ADS), &still());
                ticks += 1;
                assert!(ticks <= 60, "{weapon}");
            }
            assert_eq!(ticks, want, "{weapon}");
        }
        let (d, l, _) = setup("ar7_mako");
        assert_eq!(l.spec(&d).ads_s, 0.13);
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

    const GUNS: [&str; 3] = ["ar7_mako", "sk9_skink", "vk50_warden"];

    /// Every movement state a player can be in with the gun up that counts as moving for `spec`, crouched walks
    /// included.
    fn moving_envs(d: &GameData, spec: &WeaponSpec) -> Vec<WeaponEnv> {
        let speed = &d.movement.speed;
        let mut out = vec![];
        for mode in [MoveMode::Ground, MoveMode::Air, MoveMode::Slide, MoveMode::Zipline, MoveMode::Jetpack] {
            for speed_frac in [0.0, 0.15, 0.3, speed.walk / speed.jog, 1.0, speed.sprint / speed.jog, 2.5] {
                for crouched in [false, true] {
                    let sprinting = mode == MoveMode::Ground && speed_frac > 1.0 && !crouched;
                    let env = WeaponEnv { mode, sprinting, crouched, speed_frac, ..still() };
                    if (!crouched || mode == MoveMode::Ground) && !is_still(spec, &env) {
                        out.push(env);
                    }
                }
            }
        }
        out
    }

    /// Aimed shots stay accurate on the move (DIRECTION_LOG 16 and 17): aimed (from `ADS_AIMED`), with the most
    /// sustained-fire bloom the gun can build, every moving state keeps the cone inside a head width (0.2 m across)
    /// at 25 m for the Mako and the Skink, and at 50 m for the Warden. Hip fire on the move is far wider.
    #[test]
    fn aimed_moving_shots_stay_inside_a_head_width() {
        for (gun, range) in [("ar7_mako", 25.0_f32), ("sk9_skink", 25.0), ("vk50_warden", 50.0)] {
            let (d, l, mut s) = setup(gun);
            let spec = l.spec(&d);
            let max = (0.1 / range).atan().to_degrees();
            s.bloom_deg = spec.spread_deg.bloom_max_hip;
            for env in moving_envs(&d, spec) {
                s.ads = 0.0;
                let hip = s.spread_deg(&d, spec, &l, &env);
                for ads in [ADS_AIMED, 1.0] {
                    s.ads = ads;
                    let got = s.spread_deg(&d, spec, &l, &env);
                    assert!(got > 0.0 && got <= max, "{gun} ads {ads} {env:?}: {got} deg (at most {max})");
                    assert!(hip > 4.0 * got, "{gun} {env:?}: hip {hip} against aimed {got}");
                }
            }
        }
    }

    /// Hip fire keeps every movement penalty, Apex-style: none standing still, then it opens with speed and state
    /// (walk < jog < sprint, and a slide, the air, a zipline and the jetpack at least as wide as a sprint). The spread
    /// blends from hip to aimed as the gun comes up.
    #[test]
    fn hip_fire_keeps_its_movement_penalties() {
        for gun in GUNS {
            let (d, l, mut s) = setup(gun);
            let spec = l.spec(&d);
            let sp = &spec.spread_deg;
            let speed = &d.movement.speed;
            let at = |s: &WeaponState, env: WeaponEnv| s.spread_deg(&d, spec, &l, &env);
            let k = l.mods.hip_spread;
            let ground = |speed_frac: f32| WeaponEnv { speed_frac, ..still() };
            let walk = at(&s, ground(speed.walk / speed.jog));
            let jog = at(&s, ground(1.0));
            let sprint = at(&s, WeaponEnv { sprinting: true, ..ground(speed.sprint / speed.jog) });
            assert!((walk - sp.walk_hip * k).abs() < 1e-5 && (jog - sp.move_full_hip * k).abs() < 1e-5, "{gun}");
            assert!(0.0 < walk && walk < jog && jog < sprint, "{gun}: walk {walk}, jog {jog}, sprint {sprint}");
            let crouch_walk = at(&s, WeaponEnv { crouched: true, ..ground(speed.crouch / speed.jog) });
            assert!(crouch_walk > 0.0 && crouch_walk < walk, "{gun}: a crouch walk is moving, a bit tighter");
            for mode in [MoveMode::Air, MoveMode::Slide, MoveMode::Zipline, MoveMode::Jetpack] {
                for speed_frac in [0.0, 0.5, 1.0, 2.0] {
                    let got = at(&s, WeaponEnv { mode, speed_frac, ..still() });
                    assert!(got >= sprint - 1e-6, "{gun} {mode:?} at {speed_frac}: {got} against a sprint's {sprint}");
                }
            }
            // half way up: half way between hip and aimed
            s.ads = ADS_AIMED / 2.0;
            let air = WeaponEnv { mode: MoveMode::Air, ..still() };
            let half = at(&s, air);
            let (hip, aimed) = (sp.air * k, sp.air * sp.ads_move_mult);
            assert!((half - (hip + aimed) / 2.0).abs() < 1e-5, "{gun}: {half}");
        }
    }

    /// The crosshair shows the live random cone: the plain cross for every gun standing still, the Warden too (its hip
    /// shot standing still is exact now), whatever bloom is left from a run, and on the move it opens by the real
    /// cone, by far the most for the Warden's hip fire (review: the crosshair hid the Warden's hip spread).
    #[test]
    fn the_crosshair_shows_the_random_cone() {
        let mut jog = vec![];
        for gun in GUNS {
            let (d, l, mut s) = setup(gun);
            let spec = l.spec(&d);
            let at = |s: &WeaponState, env: WeaponEnv| s.spread_deg(&d, spec, &l, &env);
            s.bloom_deg = 1.0;
            assert_eq!(at(&s, still()), 0.0, "{gun}: at rest, the plain cross");
            assert_eq!(at(&s, WeaponEnv { crouched: true, ..still() }), 0.0, "{gun}");
            let run = WeaponEnv { speed_frac: 1.0, ..still() };
            s.bloom_deg = 0.0;
            let open = at(&s, run);
            assert!((open - move_cone_deg(&d, spec, &run) * l.mods.hip_spread).abs() < 1e-5, "{gun}");
            s.bloom_deg = 0.5;
            assert!((at(&s, run) - (open + 0.5)).abs() < 1e-5, "{gun}: bloom opens it more");
            s.ads = 1.0;
            assert!(at(&s, run) < 0.25, "{gun}: aimed, barely");
            jog.push(open);
        }
        assert!(jog[2] > 2.0 * jog[0], "the Warden's hip cone on the move dwarfs the Mako's: {jog:?}");
    }

    /// Sustained fire on the move blooms a little aimed too, never past `bloom_max_ads`.
    #[test]
    fn moving_aimed_shots_still_bloom_a_little() {
        let (d, l, mut s) = setup("ar7_mako");
        let spec = l.spec(&d);
        let sp = &spec.spread_deg;
        s.ads = 1.0;
        let run = WeaponEnv { speed_frac: 1.0, ..still() };
        let first = s.spread_deg(&d, spec, &l, &run);
        let both = input(Buttons::FIRE | Buttons::ADS);
        let shots = (0..90).filter(|_| s.step(&d, &l, &both, &run).shot.is_some()).count();
        assert!(shots >= 14, "{shots}");
        assert!((s.bloom_deg - sp.bloom_max_hip).abs() < 1e-5, "a long spray on the run reaches the cap");
        let spread = s.spread_deg(&d, spec, &l, &run);
        assert!(spread > first, "{spread} vs {first}");
        assert!((spread - (sp.move_full_hip * sp.ads_move_mult + sp.bloom_max_ads)).abs() < 1e-5, "{spread}");
    }

    /// One spray from `s` in `env`: aimed in first if `aimed`, then FIRE held (pressed every other tick for guns that
    /// fire once per pull) until `shots` rounds went off.
    fn spray(
        d: &GameData,
        l: &WeaponLoadout,
        s: &mut WeaponState,
        env: &WeaponEnv,
        aimed: bool,
        shots: usize,
    ) -> Vec<Shot> {
        let ads = if aimed { Buttons::ADS } else { 0 };
        for _ in 0..30 {
            s.step(d, l, &input(ads), env);
        }
        let mut out = vec![];
        for t in 0..3000 {
            if out.len() == shots {
                break;
            }
            let fire = if s.fire_mode == FireMode::Auto || t % 2 == 0 { Buttons::FIRE } else { 0 };
            if let Some(shot) = s.step(d, l, &input(fire | ads), env).shot {
                out.push(shot);
            }
        }
        assert_eq!(out.len(), shots, "{env:?}");
        out
    }

    /// Where the shots of a spray go when nobody pulls down: the view climbs by every kick (as the client applies
    /// it), and each shot leaves inside its cone around the view, seeded for `player`. (shot direction, view
    /// direction) per shot.
    fn spray_dirs(shots: &[Shot], player: u64) -> Vec<(Vec3, Vec3)> {
        let (mut yaw, mut pitch) = (0.0_f32, 0.0_f32);
        shots
            .iter()
            .map(|s| {
                let dir = shot_direction(yaw, pitch, s.spread_deg, shot_seed(player, s.seq));
                let view = view_dir(yaw, pitch);
                pitch += s.kick_pitch.to_radians();
                yaw -= s.kick_yaw.to_radians();
                (dir, view)
            })
            .collect()
    }

    fn kicks(shots: &[Shot]) -> Vec<(f32, f32, f32)> {
        shots.iter().map(|s| (s.spread_deg, s.kick_pitch, s.kick_yaw)).collect()
    }

    /// Standing still, every gun follows its fixed pattern with no randomness at all (DIRECTION_LOG 17): two sprays
    /// give the same shots, hip or aimed, standing or crouched, whoever fires them, whatever their shot numbers, and
    /// whenever they start. Every shot, the first aimed one included, goes exactly where the view points.
    #[test]
    fn standing_sprays_are_identical() {
        for gun in GUNS {
            for aimed in [false, true] {
                for crouched in [false, true] {
                    let env = WeaponEnv { crouched, ..still() };
                    let (d, l, mut s) = setup(gun);
                    let n = l.mag_capacity as usize;
                    let first = spray(&d, &l, &mut s, &env, aimed, n);
                    assert!(first.iter().all(|s| s.spread_deg == 0.0), "{gun}: no random cone standing still");
                    let path = spray_dirs(&first, 1);
                    assert!(path.iter().all(|(dir, view)| dir == view), "{gun}: every shot on the view");
                    // The same player after a refill and a pause, and another player late in a life: same shots.
                    for _ in 0..secs_to_ticks(1.0, d.net.tick_hz) {
                        s.step(&d, &l, &input(0), &env);
                    }
                    let slot = s.loaded as usize;
                    s.rounds[slot] = l.mag_capacity;
                    let again = spray(&d, &l, &mut s, &env, aimed, n);
                    let (_, _, mut other) = setup(gun);
                    other.shot_seq = 977;
                    for _ in 0..37 {
                        other.step(&d, &l, &input(0), &env);
                    }
                    let late = spray(&d, &l, &mut other, &env, aimed, n);
                    assert_eq!(kicks(&again), kicks(&first), "{gun} aimed {aimed} crouched {crouched}");
                    assert_eq!(kicks(&late), kicks(&first), "{gun} aimed {aimed} crouched {crouched}");
                    assert_eq!(spray_dirs(&again, 1), path, "{gun}");
                    assert_eq!(spray_dirs(&late, 4242), path, "{gun}");
                }
            }
        }
    }

    /// Moving adds random bloom on top of the same pattern and is never better than standing still (DIRECTION_LOG
    /// 17). For every gun, hip and aimed, standing and crouched, in every moving state and for many shooters
    /// (seeds): each shot kicks at least as hard as the same shot standing still (the same pattern; only standing
    /// still does a crouch lighten it), and has a random cone where standing still has none. Hip fire on the move
    /// really scatters.
    #[test]
    fn moving_never_beats_standing_still() {
        for gun in GUNS {
            let (d, l, _) = setup(gun);
            let spec = l.spec(&d);
            let n = (l.mag_capacity as usize).min(20);
            for aimed in [false, true] {
                for crouched in [false, true] {
                    let rest = spray(&d, &l, &mut setup(gun).2, &WeaponEnv { crouched, ..still() }, aimed, n);
                    for env in moving_envs(&d, spec).into_iter().filter(|e| e.crouched == crouched) {
                        let moving = spray(&d, &l, &mut setup(gun).2, &env, aimed, n);
                        for (m, r) in moving.iter().zip(&rest) {
                            let same_way = m.kick_pitch * r.kick_pitch >= 0.0 && m.kick_yaw * r.kick_yaw >= 0.0;
                            let harder = m.kick_pitch.abs() >= r.kick_pitch.abs() - 1e-6
                                && m.kick_yaw.abs() >= r.kick_yaw.abs() - 1e-6;
                            assert!(same_way && harder, "{gun} aimed {aimed} {env:?}: {m:?} vs {r:?}");
                            if !crouched {
                                assert_eq!((m.kick_pitch, m.kick_yaw), (r.kick_pitch, r.kick_yaw), "{gun} {env:?}");
                            }
                            assert!(m.spread_deg > r.spread_deg, "{gun} aimed {aimed} {env:?}: moving blooms");
                        }
                        let (mut off, mut cone) = (0.0_f32, f32::MAX);
                        for player in 0..24 {
                            for ((dir, view), s) in spray_dirs(&moving, player).into_iter().zip(&moving) {
                                let a = dir.angle_between(view).to_degrees();
                                // (`angle_between` is coarse for tiny angles in f32)
                                assert!(a <= s.spread_deg + 0.05, "{gun} {env:?}: inside its cone");
                                off = off.max(a);
                                cone = cone.min(s.spread_deg);
                            }
                        }
                        if !aimed {
                            assert!(off > 0.3 * cone, "{gun} {env:?}: hip fire on the move scatters ({off} deg)");
                        }
                    }
                }
            }
        }
    }

    /// Stopping brings the fixed pattern back: hip fire on the run blooms, and from the first tick under the still
    /// threshold every shot is exact again and kicks like the same shot of a spray that stood still all along. The
    /// left-over bloom settles before the next run.
    #[test]
    fn stopping_recovers_the_fixed_pattern() {
        let (d, l, mut s) = setup("ar7_mako");
        let (_, _, mut rest) = setup("ar7_mako");
        let run = WeaponEnv { speed_frac: 1.0, ..still() };
        let (mut ran, mut stood) = (0, 0);
        for t in 0..120 {
            let env = if t < 40 { run } else { still() };
            if t == 40 {
                assert!(s.bloom_deg > 0.5, "the bloom is still there, it just does not count standing still");
            }
            let a = s.step(&d, &l, &input(Buttons::FIRE), &env).shot;
            let b = rest.step(&d, &l, &input(Buttons::FIRE), &still()).shot;
            assert_eq!(a.is_some(), b.is_some(), "the same fire rate");
            let (Some(a), Some(b)) = (a, b) else { continue };
            assert_eq!((a.kick_pitch, a.kick_yaw), (b.kick_pitch, b.kick_yaw), "the same pattern, shot {}", a.seq);
            if t < 40 {
                assert!(a.spread_deg > b.spread_deg, "running: bloom");
                ran += 1;
            } else {
                assert_eq!(a.spread_deg, 0.0, "stopped: exact again");
                stood += 1;
            }
        }
        assert!(ran >= 7 && stood >= 15, "{ran} {stood}");
        for _ in 0..60 {
            s.step(&d, &l, &input(0), &still());
        }
        assert_eq!(s.bloom_deg, 0.0, "a second later it has settled");
        assert!((s.spread_deg(&d, l.spec(&d), &l, &run) - 2.6).abs() < 1e-5, "the next run starts fresh");
    }

    /// On the run, hip fire opens with every shot of a spray (the first one has only the movement cone) and closes
    /// back to the movement cone once the trigger is let go, while still running.
    #[test]
    fn hip_bloom_grows_through_a_spray_and_settles_after() {
        for gun in ["ar7_mako", "sk9_skink"] {
            let (d, l, mut s) = setup(gun);
            let spec = l.spec(&d);
            let run = WeaponEnv { speed_frac: 1.0, ..still() };
            let base = s.spread_deg(&d, spec, &l, &run);
            let cones: Vec<f32> = (0..60)
                .filter_map(|_| s.step(&d, &l, &input(Buttons::FIRE), &run).shot.map(|s| s.spread_deg))
                .collect();
            assert!(cones.len() >= 10, "{gun}");
            assert_eq!(cones[0], base, "{gun}: the first shot has the movement cone alone");
            assert!(cones.windows(2).all(|w| w[1] > w[0]), "{gun}: every shot opens it more: {cones:?}");
            let after: Vec<f32> = (0..60)
                .map(|_| {
                    s.step(&d, &l, &input(0), &run);
                    s.spread_deg(&d, spec, &l, &run)
                })
                .collect();
            assert!(after.windows(2).all(|w| w[1] <= w[0]), "{gun}: it only closes: {after:?}");
            assert!((after[59] - base).abs() < 1e-5, "{gun}: back to the movement cone: {}", after[59]);
        }
    }

    /// From a sprint, aim and trigger held: the shot goes off no later than the first tick the gun is aimed, for
    /// every gun, with its default parts and with its fastest-aiming build (review: the faster ADS of playtest round
    /// 1 waited on the raise from the sprint pose, so a run gained nothing from it).
    #[test]
    fn from_a_sprint_an_aimed_shot_never_waits_on_the_raise() {
        let d = GameData::embedded();
        let fastest: [(&str, &[&str]); 3] = [
            ("ar7_mako", &["optic_reddot", "grip_angled", "mako_stock_light"]),
            ("sk9_skink", &["optic_reddot"]),
            ("vk50_warden", &["optic_reddot", "warden_stock_folding"]),
        ];
        for (gun, fast) in fastest {
            for parts in [&[][..], fast] {
                let parts: Vec<String> = parts.iter().map(|p| p.to_string()).collect();
                let l = WeaponLoadout::resolve(&d, gun, &[AmmoChoice::STANDARD], &parts).unwrap();
                let mut s = WeaponState::new(&d, &l);
                s.action = WeaponAction::Ready;
                let sprint = WeaponEnv { sprinting: true, speed_frac: 7.0 / 4.8, ..still() };
                s.step(&d, &l, &input(0), &sprint);
                assert!(s.lowered(), "{gun}");
                let (mut aimed, mut shot) = (None, None);
                for t in 1..60 {
                    let ev = s.step(&d, &l, &input(Buttons::ADS | Buttons::FIRE), &sprint);
                    if s.ads >= ADS_AIMED {
                        aimed.get_or_insert(t);
                    }
                    if ev.shot.is_some() {
                        shot.get_or_insert(t);
                    }
                }
                let (aimed, shot) = (aimed.unwrap(), shot.expect("it fires"));
                let raise = secs_to_ticks(l.spec(&d).sprint_to_fire_s * l.mods.sprint_to_fire, 60) as i32;
                assert!(shot <= aimed, "{gun} {parts:?}: aimed at tick {aimed}, shot at {shot}");
                assert_eq!(shot, raise.min(aimed), "{gun} {parts:?}: no sooner than the raise or the sight");
            }
        }
    }

    /// An empty gun clicks on the trigger pull itself, on the run too while the gun comes up: a one-tick tap gives
    /// exactly one click, on the tap (the sound plays while FIRE is held), and so does FIRE held through the raise
    /// (review: a tap on the run clicked 0.2-0.3 s later, after it was let go, so it never played).
    #[test]
    fn an_empty_tap_on_the_run_clicks_once_on_the_pull() {
        let modes = [
            ("ar7_mako", FireMode::Semi),
            ("ar7_mako", FireMode::Auto),
            ("sk9_skink", FireMode::Auto),
            ("vk50_warden", FireMode::Bolt),
        ];
        for (gun, mode) in modes {
            for hold in [1, 30] {
                let (d, l, mut s) = setup(gun);
                s.fire_mode = mode;
                s.rounds[0] = 0;
                let sprint = WeaponEnv { sprinting: true, ..still() };
                s.step(&d, &l, &input(0), &sprint);
                assert!(s.lowered());
                let clicks: Vec<usize> = (0..90)
                    .filter(|t| {
                        let fire = if *t < hold { Buttons::FIRE } else { 0 };
                        s.step(&d, &l, &input(fire), &sprint).dry_fire
                    })
                    .collect();
                assert_eq!(clicks, vec![0], "{gun} {mode:?} held {hold}: one click, on the pull");
                assert!(!s.fire_queued, "{gun}: nothing waits on an empty gun");
            }
        }
    }

    /// A trigger pull during a bolt cycle is dropped on the run as it is standing still; only a pull that waits on
    /// nothing but the raise from the sprint pose is kept (review: a Warden tap mid-bolt fired on its own later).
    #[test]
    fn a_tap_mid_bolt_fires_nothing_on_the_run_either() {
        for sprinting in [false, true] {
            let (d, l, mut s) = setup("vk50_warden");
            let env = WeaponEnv { sprinting, ..still() };
            let shots: Vec<i32> = (0..200)
                .filter(|t| {
                    let fire = if *t == 0 || (48..52).contains(t) { Buttons::FIRE } else { 0 };
                    s.step(&d, &l, &input(fire), &env).shot.is_some()
                })
                .collect();
            assert_eq!(shots, vec![0], "sprinting {sprinting}: the mid-bolt tap is dropped");
        }
        // Late in the bolt cycle, only the raise is in the way: that tap fires when the gun is up.
        let (d, l, mut s) = setup("vk50_warden");
        let env = WeaponEnv { sprinting: true, ..still() };
        let raise = secs_to_ticks(l.spec(&d).sprint_to_fire_s * l.mods.sprint_to_fire, 60) as i32;
        let cycle = fire_interval_ticks(l.spec(&d), 60, false) as i32;
        let tap = cycle - raise + 2;
        let shots: Vec<i32> = (0..200)
            .filter(|t| {
                let fire = if *t == 0 || *t == tap { Buttons::FIRE } else { 0 };
                s.step(&d, &l, &input(fire), &env).shot.is_some()
            })
            .collect();
        assert_eq!(shots, vec![0, tap + raise - 1]);
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

    #[test]
    fn a_kill_refills_the_emptiest_spare_first() {
        let (_, l, mut s) = setup("ar7_mako");
        let cap = l.mag_capacity;
        s.rounds = vec![3, 0, cap, 10];
        s.loaded = 0;
        assert_eq!(s.refill_mags(1, cap), 1);
        assert_eq!(s.rounds, vec![3, cap, cap, 10], "the empty spare, not the gun's 3");
        assert_eq!(s.refill_mags(1, cap), 1);
        assert_eq!(s.rounds, vec![3, cap, cap, cap], "then the next emptiest spare");
        assert_eq!(s.refill_mags(1, cap), 1);
        assert_eq!(s.rounds, vec![cap; 4], "the gun's own magazine last");
        assert_eq!(s.refill_mags(1, cap), 0, "nothing to fill");
    }
}
