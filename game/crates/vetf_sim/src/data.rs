//! Gameplay data loaded from `game/assets/data/*.ron`.
//!
//! The structs mirror the design data in `design/systems/data/*.json` (field names and nesting), so the
//! sync test in `tests/design_sync.rs` can compare every design number against what the game loads.

use crate::zone::{Zone, ZoneSet, ZoneTable};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

// ---------------------------------------------------------------------------------------------- errors

#[derive(Debug, thiserror::Error)]
pub enum DataError {
    #[error("cannot read {path}: {source}")]
    Io { path: PathBuf, source: std::io::Error },
    #[error("cannot parse {file}: {source}")]
    Parse { file: String, source: Box<ron::error::SpannedError> },
    #[error("invalid data: {0}")]
    Invalid(String),
}

// ---------------------------------------------------------------------------------------------- weapons

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WeaponsFile {
    pub tick_hz: u32,
    pub weapons: Vec<WeaponSpec>,
    pub spill_to_torso: SpillToTorso,
}

/// Damage hitting an already-broken limb flows on to the torso, scaled by these factors.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct SpillToTorso {
    pub arms: f32,
    pub legs: f32,
}

impl SpillToTorso {
    pub fn factor(&self, zone: Zone) -> Option<f32> {
        match zone {
            Zone::Arms => Some(self.arms),
            Zone::Legs => Some(self.legs),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum WeaponClass {
    Smg,
    LightAssault,
    AssaultRifle,
    HeavyAssault,
    Shotgun,
    BoltSniper,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Ballistics {
    Hitscan,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FireMode {
    Auto,
    Semi,
    Bolt,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WeaponSpec {
    pub id: String,
    pub name: String,
    pub cls: WeaponClass,
    pub ballistics: Ballistics,
    pub damage: f32,
    /// (range m, damage) points, linearly interpolated; beyond the last point damage is `min_damage`.
    pub falloff: Vec<(f32, f32)>,
    pub min_damage: f32,
    pub max_range_m: f32,
    pub zone_mult: ZoneTable<f32>,
    pub rpm: f32,
    /// Fire rate multiplier while aiming down sights.
    #[serde(default = "one")]
    pub ads_rpm_mult: f32,
    /// Aimed first shots stay accurate in the air and while moving slightly.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ads_first_shot: Option<AdsFirstShot>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bolt_cycle_s: Option<f32>,
    pub fire_modes: Vec<FireMode>,
    pub mag_default: String,
    pub reload_tactical_s: f32,
    pub reload_empty_s: f32,
    pub reload_fast_drop_s: f32,
    pub mag_check_s: f32,
    pub equip_s: f32,
    pub holster_s: f32,
    pub ads_s: f32,
    pub sprint_to_fire_s: f32,
    pub move_mult_held: f32,
    pub move_mult_ads: f32,
    pub spread_deg: SpreadSpec,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sway: Option<SwaySpec>,
    pub recoil: RecoilSpec,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scope: Option<ScopeSpec>,
}

fn one() -> f32 {
    1.0
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct AdsFirstShot {
    /// The airborne / jetpack spread penalty does not apply.
    pub air_accurate: bool,
    /// Moving up to this fraction of jog speed still counts as standing still.
    pub move_tolerance_frac: f32,
}

/// Ammo is picked per loadout as a type and a tier; the weapon class sets the baseline.
///
/// `pen` is a shield-damage multiplier per halo tier (user direction): a covered arc takes
/// `damage x pen[tier]`, zone HP takes nothing until the arc is down, and the bullet that breaks an arc
/// carries its leftover (converted back by `/ pen`) on to HP.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AmmoFile {
    /// Upper limit on the broken-limb -> torso spill factor after `spill_mult`.
    pub spill_cap: f32,
    pub classes: BTreeMap<WeaponClass, AmmoClassSpec>,
    pub types: BTreeMap<AmmoKind, AmmoTypeSpec>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AmmoClassSpec {
    /// Baseline shield-damage multiplier against a halo arc of tier 1..4 (1.0 = normal).
    pub pen: [f32; 4],
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum AmmoKind {
    Standard,
    ArmorPiercing,
    Shrapnel,
    Rip,
    Slug,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AmmoTypeSpec {
    pub label: String,
    /// Weapon classes that can load this type (empty = all).
    #[serde(default)]
    pub only: Vec<WeaponClass>,
    /// False for NPC-only rounds (Shrapnel is meant for bots and bosses in the extraction mode).
    #[serde(default = "yes")]
    pub player_loadout: bool,
    /// Ammo tiers I, II, III (some types have fewer).
    pub tiers: Vec<AmmoTierSpec>,
}

fn yes() -> bool {
    true
}

/// Bleeding from fragments: per stack on the hit zone, until treated; treatment leaves a residual
/// trickle that lasts until respawn ("cannot be removed fully").
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct BleedSpec {
    pub hp_per_s: f32,
    pub max_stacks: u8,
    pub residual_hp_per_s: f32,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AmmoTierSpec {
    /// Multiplies the class shield-damage multiplier.
    pub pen_mult: f32,
    /// Multiplies the bullet's damage (shield and HP).
    pub damage_mult: f32,
    /// Multiplies damage that reaches zone HP.
    pub flesh_mult: f32,
    /// Multiplies the broken-limb -> torso spill factors (capped by `spill_cap`).
    pub spill_mult: f32,
    /// Chance that a hit on a covered arc ignores the shield entirely.
    pub bypass_chance: f32,
    pub bleed: Option<BleedSpec>,
    /// Points against the team-deathmatch loadout gear budget.
    pub gear_cost: u32,
}

impl Default for AmmoTierSpec {
    fn default() -> Self {
        Self {
            pen_mult: 1.0,
            damage_mult: 1.0,
            flesh_mult: 1.0,
            spill_mult: 1.0,
            bypass_chance: 0.0,
            bleed: None,
            gear_cost: 0,
        }
    }
}

/// What a loadout loads: e.g. `AmmoChoice { kind: ArmorPiercing, tier: 2 }` = AP II.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AmmoChoice {
    pub kind: AmmoKind,
    pub tier: u8,
}

impl AmmoChoice {
    pub const STANDARD: AmmoChoice = AmmoChoice { kind: AmmoKind::Standard, tier: 1 };
}

/// A resolved round for one weapon class.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AmmoSpec {
    pub choice: AmmoChoice,
    pub label: String,
    /// Shield-damage multiplier against a halo arc of tier 1..4.
    pub pen: [f32; 4],
    pub damage_mult: f32,
    pub flesh_mult: f32,
    /// Broken-limb -> torso spill multiplier, and the cap on the result.
    pub spill_mult: f32,
    pub spill_cap: f32,
    pub bypass_chance: f32,
    pub bleed: Option<BleedSpec>,
    pub gear_cost: u32,
    pub player_loadout: bool,
}

impl AmmoSpec {
    /// Shield-damage multiplier against an arc of `tier` (tier 0 = no arc).
    pub fn pen_for_tier(&self, tier: u8) -> f32 {
        match tier {
            0 => 1.0,
            t => self.pen[(t.min(4) - 1) as usize],
        }
    }

    /// The spill factors this round uses for broken limbs.
    pub fn spill(&self, base: &SpillToTorso) -> SpillToTorso {
        SpillToTorso {
            arms: (base.arms * self.spill_mult).min(self.spill_cap),
            legs: (base.legs * self.spill_mult).min(self.spill_cap),
        }
    }
}

const ROMAN: [&str; 4] = ["I", "II", "III", "IV"];

impl AmmoFile {
    pub fn resolve(&self, class: WeaponClass, choice: AmmoChoice) -> Option<AmmoSpec> {
        let base = self.classes.get(&class)?;
        let ty = self.types.get(&choice.kind)?;
        if !ty.only.is_empty() && !ty.only.contains(&class) {
            return None;
        }
        let tier = ty.tiers.get((choice.tier as usize).checked_sub(1)?)?;
        let pen = base.pen.map(|p| (p * tier.pen_mult).max(0.0));
        let label = if ty.tiers.len() > 1 {
            format!("{} {}", ty.label, ROMAN[(choice.tier as usize - 1).min(3)])
        } else {
            ty.label.clone()
        };
        Some(AmmoSpec {
            choice,
            label,
            pen,
            damage_mult: tier.damage_mult,
            flesh_mult: tier.flesh_mult,
            spill_mult: tier.spill_mult,
            spill_cap: self.spill_cap,
            bypass_chance: tier.bypass_chance,
            bleed: tier.bleed,
            gear_cost: tier.gear_cost,
            player_loadout: ty.player_loadout,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpreadSpec {
    pub ads_still: f32,
    /// Bolt sniper: spread while the scope has not settled after ADS / movement.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ads_unsettled: Option<f32>,
    pub hip_still: f32,
    pub crouch_mult: f32,
    pub move_full_ads: f32,
    pub move_full_hip: f32,
    /// Movement below this fraction of jog speed counts as standing still.
    pub move_threshold_frac: f32,
    pub air: f32,
    pub slide: f32,
    pub zipline: f32,
    pub jetpack: f32,
    #[serde(default)]
    pub bloom_per_shot_ads: f32,
    #[serde(default)]
    pub bloom_max_ads: f32,
    #[serde(default)]
    pub bloom_per_shot_hip: f32,
    #[serde(default)]
    pub bloom_max_hip: f32,
    #[serde(default)]
    pub bloom_decay_delay_s: f32,
    #[serde(default)]
    pub bloom_decay_deg_per_s: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SwaySpec {
    pub idle_amp_deg: f32,
    pub period_s: f32,
    pub hold_breath_s: f32,
    pub exhausted_mult: f32,
    pub exhausted_s: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScopeSpec {
    pub zoom_levels: Vec<f32>,
    pub glint_min_range_m: f32,
    pub glint_cone_deg: f32,
}

/// Automatic weapons follow a learnable pattern; bolt guns get one big kick per shot.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum RecoilSpec {
    Pattern(PatternRecoilSpec),
    Kick(KickRecoilSpec),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PatternRecoilSpec {
    /// Key into `recoil_patterns.ron`.
    pub pattern: String,
    pub ads_mult: f32,
    pub hip_mult: f32,
    pub crouch_mult: f32,
    /// The pattern restarts after this long without firing.
    pub reset_after_s: f32,
    /// Fraction of the un-compensated climb that recovers on its own.
    pub recover_frac: f32,
    pub recover_delay_s: f32,
    pub recover_deg_per_s: f32,
    /// Purely visual camera punch per shot (does not move the aim).
    pub view_punch_visual_deg: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct KickRecoilSpec {
    pub kick_pitch_deg: f32,
    pub kick_yaw_rand_deg: f32,
    pub recover_frac: f32,
    pub recover_s: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RecoilPattern {
    pub loop_from_index: usize,
    pub kicks: Vec<PatternKick>,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct PatternKick {
    pub after_shot: u32,
    pub pitch: f32,
    pub yaw: f32,
}

impl RecoilPattern {
    /// Kick applied after the `shot`-th shot of a burst (1-based). Loops for long magazines.
    pub fn kick(&self, shot: u32) -> (f32, f32) {
        let n = self.kicks.len();
        if n == 0 || shot == 0 {
            return (0.0, 0.0);
        }
        let i = (shot - 1) as usize;
        let idx = if i < n {
            i
        } else {
            let lf = self.loop_from_index.min(n - 1);
            lf + (i - n) % (n - lf)
        };
        let k = self.kicks[idx];
        (k.pitch, k.yaw)
    }
}

// ---------------------------------------------------------------------------------------------- armor

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum WeightClass {
    None,
    Light,
    Medium,
    Heavy,
}

impl WeightClass {
    pub fn label(self) -> &'static str {
        match self {
            WeightClass::None => "NONE",
            WeightClass::Light => "LIGHT",
            WeightClass::Medium => "MEDIUM",
            WeightClass::Heavy => "HEAVY",
        }
    }
}

/// Halo core type: decides capacity, regen and the status effect.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Core {
    Bulwark,
    Volt,
    Mender,
    Phase,
}

impl Core {
    pub const ALL: [Core; 4] = [Core::Bulwark, Core::Volt, Core::Mender, Core::Phase];

    pub fn label(self) -> &'static str {
        match self {
            Core::Bulwark => "BULWARK",
            Core::Volt => "VOLT",
            Core::Mender => "MENDER",
            Core::Phase => "PHASE",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct WeightEffects {
    #[serde(rename = "move")]
    pub move_mult: f32,
    pub accel: f32,
    pub fuel: f32,
    pub slide_boost: f32,
    pub mantle: f32,
    pub energy_per_min: f32,
    pub cells: u8,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct RegenSpec {
    pub delay_s: f32,
    pub delay_after_break_s: f32,
    pub rate_per_s: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ArmorFile {
    pub zone_hp: ZoneTable<f32>,
    pub weight_effects: BTreeMap<WeightClass, WeightEffects>,
    /// Capacity of one arc per core, indexed by tier 1..4.
    pub capacity: BTreeMap<Core, Vec<f32>>,
    /// Each arc's share of the core capacity.
    pub zone_capacity_share: ZoneTable<f32>,
    pub regen: BTreeMap<Core, RegenSpec>,
    pub weight_bands: Vec<(WeightClass, u32, u32)>,
    /// Highest tier a loadout may put on each arc.
    pub loadout_tier_caps: ZoneTable<u8>,
    pub status_effects: BTreeMap<Core, String>,
    pub presets: Vec<ArmorPreset>,
}

/// An armor: one core type, and a tier (0 = uncovered) per halo arc.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ArmorPreset {
    pub id: String,
    pub name: String,
    pub core: Option<Core>,
    pub tiers: ZoneTable<u8>,
}

/// A fully resolved armor (halo). The first fields serialise like a design `presets` record
/// (`tier` = highest arc tier, `coverage` = arcs with a tier, `capacity` = all arcs together).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ArmorStats {
    pub id: String,
    pub name: String,
    pub core: Option<Core>,
    pub tier: u8,
    pub coverage: Vec<Zone>,
    pub tiers: ZoneTable<u8>,
    pub arc_capacity: ZoneTable<f32>,
    pub weight_class: WeightClass,
    pub power_cells: u8,
    pub move_speed_mult: f32,
    pub energy_drain_per_min: f32,
    pub gear_cost: u32,
    pub capacity: f32,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub regen_delay_s: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub regen_delay_after_break_s: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub regen_per_s: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status_effect: Option<String>,
}

impl ArmorStats {
    pub fn coverage_set(&self) -> ZoneSet {
        ZoneSet::from_zones(&self.coverage)
    }

    pub fn regen(&self) -> Option<RegenSpec> {
        Some(RegenSpec {
            delay_s: self.regen_delay_s?,
            delay_after_break_s: self.regen_delay_after_break_s?,
            rate_per_s: self.regen_per_s?,
        })
    }
}

impl ArmorFile {
    /// Protection score (sum of arc tiers) mapped through the weight bands.
    pub fn weight_class(&self, score: u32) -> WeightClass {
        if score == 0 {
            return WeightClass::None;
        }
        self.weight_bands
            .iter()
            .find(|(_, lo, hi)| (*lo..=*hi).contains(&score))
            .map(|(wc, _, _)| *wc)
            .unwrap_or(WeightClass::Heavy)
    }

    pub fn effects(&self, wc: WeightClass) -> WeightEffects {
        self.weight_effects[&wc]
    }

    pub fn preset(&self, id: &str) -> Option<&ArmorPreset> {
        self.presets.iter().find(|p| p.id == id)
    }

    pub fn arc_capacity(&self, core: Core, tier: u8, zone: Zone) -> f32 {
        if tier == 0 {
            return 0.0;
        }
        let table = &self.capacity[&core];
        table[(tier.min(4) as usize - 1).min(table.len() - 1)] * self.zone_capacity_share[zone]
    }

    pub fn resolve(&self, preset: &ArmorPreset) -> ArmorStats {
        let tiers = if preset.core.is_some() { preset.tiers } else { ZoneTable::default() };
        let score: u32 = tiers.iter().map(|(_, t)| *t as u32).sum();
        let wc = self.weight_class(score);
        let fx = self.effects(wc);
        let arc_capacity = tiers.map(|z, t| preset.core.map_or(0.0, |c| self.arc_capacity(c, *t, z)));
        let mut stats = ArmorStats {
            id: preset.id.clone(),
            name: preset.name.clone(),
            core: preset.core,
            tier: tiers.iter().map(|(_, t)| *t).max().unwrap_or(0),
            coverage: tiers.iter().filter(|(_, t)| **t > 0).map(|(z, _)| z).collect(),
            tiers,
            arc_capacity,
            weight_class: wc,
            power_cells: fx.cells,
            move_speed_mult: fx.move_mult,
            energy_drain_per_min: fx.energy_per_min,
            gear_cost: score,
            capacity: arc_capacity.iter().map(|(_, c)| *c).sum(),
            regen_delay_s: None,
            regen_delay_after_break_s: None,
            regen_per_s: None,
            status_effect: None,
        };
        if let Some(core) = preset.core {
            let regen = self.regen[&core];
            stats.regen_delay_s = Some(regen.delay_s);
            stats.regen_delay_after_break_s = Some(regen.delay_after_break_s);
            stats.regen_per_s = Some(regen.rate_per_s);
            stats.status_effect = self.status_effects.get(&core).cloned();
        }
        stats
    }

    pub fn resolve_id(&self, id: &str) -> Option<ArmorStats> {
        self.preset(id).map(|p| self.resolve(p))
    }
}

// ---------------------------------------------------------------------------------------------- attachments

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttachmentCategory {
    Optic,
    Stock,
    Mag,
    Under,
    Side,
    Shield,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Zoom {
    Fixed(f32),
    Levels(Vec<f32>),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AttachmentsFile {
    pub attachments: Vec<AttachmentSpec>,
}

/// Every modifier is a multiplier on the base weapon stat; `None` means 1.0.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Modifiers {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ads_time: Option<f32>,
    #[serde(rename = "move", skip_serializing_if = "Option::is_none")]
    pub move_mult: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ads_move: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sway: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recoil_v: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub recoil_h: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hip_spread: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reload: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sprint_to_fire: Option<f32>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AttachmentSpec {
    pub id: String,
    pub cat: AttachmentCategory,
    pub fits: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub zoom: Option<Zoom>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub capacity: Option<u16>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub default_for: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub other: Option<String>,
    // Not `#[serde(flatten)]`: RON cannot deserialise flattened structs reliably.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ads_time: Option<f32>,
    #[serde(default, rename = "move", skip_serializing_if = "Option::is_none")]
    pub move_mult: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ads_move: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sway: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recoil_v: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub recoil_h: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hip_spread: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reload: Option<f32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sprint_to_fire: Option<f32>,
}

impl AttachmentSpec {
    pub fn modifiers(&self) -> Modifiers {
        Modifiers {
            ads_time: self.ads_time,
            move_mult: self.move_mult,
            ads_move: self.ads_move,
            sway: self.sway,
            recoil_v: self.recoil_v,
            recoil_h: self.recoil_h,
            hip_spread: self.hip_spread,
            reload: self.reload,
            sprint_to_fire: self.sprint_to_fire,
        }
    }
}

/// Product of all attachment multipliers on one weapon (1.0 = unchanged).
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ModifierTotals {
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

impl Default for ModifierTotals {
    fn default() -> Self {
        Self {
            ads_time: 1.0,
            move_mult: 1.0,
            ads_move: 1.0,
            sway: 1.0,
            recoil_v: 1.0,
            recoil_h: 1.0,
            hip_spread: 1.0,
            reload: 1.0,
            sprint_to_fire: 1.0,
        }
    }
}

impl ModifierTotals {
    pub fn combine<'a>(mods: impl IntoIterator<Item = &'a AttachmentSpec>) -> Self {
        let mut t = Self::default();
        for a in mods {
            let m = a.modifiers();
            t.ads_time *= m.ads_time.unwrap_or(1.0);
            t.move_mult *= m.move_mult.unwrap_or(1.0);
            t.ads_move *= m.ads_move.unwrap_or(1.0);
            t.sway *= m.sway.unwrap_or(1.0);
            t.recoil_v *= m.recoil_v.unwrap_or(1.0);
            t.recoil_h *= m.recoil_h.unwrap_or(1.0);
            t.hip_spread *= m.hip_spread.unwrap_or(1.0);
            t.reload *= m.reload.unwrap_or(1.0);
            t.sprint_to_fire *= m.sprint_to_fire.unwrap_or(1.0);
        }
        t
    }
}

// ---------------------------------------------------------------------------------------------- movement

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MovementSpec {
    pub capsule: CapsuleSpec,
    pub eye_height: EyeHeightSpec,
    pub speed: SpeedSpec,
    pub ground: GroundSpec,
    pub air: AirSpec,
    pub fall_damage: FallDamageSpec,
    pub slide: SlideSpec,
    pub mantle: MantleSpec,
    pub jetpack: JetpackSpec,
    pub zipline: ZiplineSpec,
    pub noise_radius_m: NoiseSpec,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CapsuleSpec {
    pub radius: f32,
    pub height_stand: f32,
    pub height_crouch: f32,
    pub height_slide: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EyeHeightSpec {
    pub stand: f32,
    pub crouch: f32,
    pub slide: f32,
    pub transition_s: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpeedSpec {
    pub walk: f32,
    pub jog: f32,
    pub sprint: f32,
    pub crouch: f32,
    pub backpedal_mult: f32,
    pub sprint_max_angle_deg: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GroundSpec {
    pub accel: f32,
    pub decel: f32,
    pub counter_strafe_extra_decel: f32,
    pub step_height: f32,
    pub max_slope_deg: f32,
    pub ground_snap: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AirSpec {
    pub gravity: f32,
    pub jump_height: f32,
    pub jump_v0: f32,
    pub coyote_s: f32,
    pub jump_buffer_s: f32,
    pub air_accel: f32,
    pub air_wish_speed: f32,
    pub terminal_speed: f32,
    pub max_horizontal_speed: f32,
    pub max_horizontal_speed_boosted: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FallDamageSpec {
    pub free_drop_m: f32,
    pub legs_hp_per_m: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SlideSpec {
    pub min_entry_speed: f32,
    pub boost: f32,
    pub boost_cooldown_s: f32,
    pub friction: f32,
    pub end_speed: f32,
    pub downhill_min_deg: f32,
    pub max_speed: f32,
    pub jump_keep_frac: f32,
    pub steer_deg_per_s: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MantleSpec {
    pub min_ledge: f32,
    pub max_ledge: f32,
    pub low_max: f32,
    pub time_low_s: f32,
    pub time_high_s: f32,
    pub probe_forward: f32,
    pub min_ledge_depth: f32,
    pub min_headroom: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct JetpackSpec {
    pub fuel_s: f32,
    pub kick_up_mps: f32,
    pub kick_cost_s: f32,
    pub min_fuel_frac: f32,
    pub thrust: f32,
    pub climb_cap: f32,
    pub air_accel: f32,
    pub horizontal_cap: f32,
    pub regen_delay_s: f32,
    pub regen_full_s: f32,
    pub fade_band_m: BTreeMap<WeightClass, (f32, f32)>,
    pub max_rise_m: BTreeMap<WeightClass, f32>,
    pub fire_spread_add_deg: f32,
    pub ads_allowed: bool,
}

impl JetpackSpec {
    /// Fade band for a weight class (no halo uses the Light band).
    pub fn fade_band(&self, wc: WeightClass) -> (f32, f32) {
        let wc = if wc == WeightClass::None { WeightClass::Light } else { wc };
        self.fade_band_m.get(&wc).copied().unwrap_or((4.0, 5.0))
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ZiplineSpec {
    pub attach_radius: f32,
    pub snap_s: f32,
    pub speed_flat: f32,
    pub speed_min: f32,
    pub speed_max: f32,
    pub accel_s: f32,
    pub detach_keep_frac: f32,
    pub detach_up: f32,
    pub end_hop_up: f32,
    pub reattach_block_s: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NoiseSpec {
    pub walk: f32,
    pub crouch: f32,
    pub jog: f32,
    pub sprint: f32,
    pub slide: f32,
    pub land: f32,
    pub jet_start: f32,
    pub jet_loop: f32,
    pub zipline: f32,
    pub mantle: f32,
    pub reload: f32,
    pub mag_check: f32,
    pub heavy_mult: f32,
    pub kestrel_mult: f32,
}

// ---------------------------------------------------------------------------------------------- combat, hitboxes, rules, net

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CombatSpec {
    pub wounded: WoundedSpec,
    pub bulwark_flinch_mult: f32,
    pub volt_pulse: VoltPulseSpec,
    pub broken_arms: BrokenArmsSpec,
    pub broken_legs: BrokenLegsSpec,
    pub shot_validation: ShotValidationSpec,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WoundedSpec {
    pub tag_slow_frac: f32,
    pub tag_slow_s: f32,
    pub aim_punch_hp_deg: f32,
    pub aim_punch_shield_deg: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct VoltPulseSpec {
    pub radius_m: f32,
    pub slow_frac: f32,
    pub duration_s: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BrokenArmsSpec {
    pub sway_mult: f32,
    pub ads_time_mult: f32,
    pub recoil_mult: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BrokenLegsSpec {
    pub move_mult: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ShotValidationSpec {
    pub history_s: f32,
    pub max_rewind_s: f32,
    pub hitbox_inflate_m: f32,
    pub hitbox_inflate_per_speed_s: f32,
    pub aim_tolerance_deg: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct HitboxFile {
    pub boxes: Vec<HitboxSpec>,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct HitboxSpec {
    pub zone: Zone,
    pub center: (f32, f32, f32),
    pub half: (f32, f32, f32),
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RulesFile {
    pub tdm: TdmRules,
    pub rulesets: Rulesets,
    pub default_loadout: LoadoutSpec,
}

/// What a mode switches on. Team deathmatch is the gunplay and netcode test bed: per-region shields and
/// health, but no status effects, and only the high-end items that heal every region or every arc at once.
/// The gun range runs the full extraction rules.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Ruleset {
    /// Bleeds (from Shrapnel) tick until treated.
    pub bleeding: bool,
    /// A limb at 0 HP is broken: broken legs slow you, broken arms hurt aim and recoil. Off, a limb at 0 HP
    /// still spills damage into the torso; it just carries no penalty.
    pub injuries: bool,
    /// Items that treat one region can be used. Off, only whole-body items.
    pub regional_items: bool,
}

impl Ruleset {
    /// The full rules (extraction mode).
    pub const FULL: Ruleset = Ruleset { bleeding: true, injuries: true, regional_items: true };
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Rulesets {
    pub tdm: Ruleset,
    pub range: Ruleset,
}

impl Rulesets {
    pub fn get(&self, mode: Mode) -> Ruleset {
        match mode {
            Mode::Tdm => self.tdm,
            Mode::Range => self.range,
        }
    }
}

/// The game modes of the slice.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Mode {
    /// Team deathmatch on Showhome.
    Tdm,
    /// Gun range: free practice, no score, full rules.
    Range,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TdmRules {
    /// Halo arc tiers plus ammo gear cost must fit this (AP's price in team deathmatch).
    pub gear_budget: u32,
    pub score_limit: u32,
    pub time_limit_s: f32,
    pub respawn_s: f32,
    pub spawn_protection_s: f32,
    pub max_players: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LoadoutSpec {
    pub primary: String,
    /// Magazines in slot order (at most six), each with its own ammo. Slot 1 starts in the gun.
    pub mags: Vec<AmmoChoice>,
    pub attachments: Vec<String>,
    pub armor: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NetSpec {
    pub tick_hz: u32,
    pub port: u16,
    pub lan_beacon_port: u16,
    pub snapshot_hz: u32,
    pub max_remote_clients: u32,
    pub input_redundancy: u32,
    pub interpolation_delay_ms: u32,
    pub max_rollback_ticks: u32,
    pub upnp_lease_s: u32,
}

// ---------------------------------------------------------------------------------------------- all data

/// Every gameplay number the simulation uses.
#[derive(Debug, Clone, PartialEq)]
pub struct GameData {
    pub weapons: WeaponsFile,
    pub ammo: AmmoFile,
    pub recoil_patterns: BTreeMap<String, RecoilPattern>,
    pub armor: ArmorFile,
    pub attachments: AttachmentsFile,
    pub movement: MovementSpec,
    pub combat: CombatSpec,
    pub hitboxes: HitboxFile,
    pub rules: RulesFile,
    pub net: NetSpec,
    pub items: crate::items::ItemsFile,
    /// FNV-1a hash of the source text, so host and clients can check they run the same numbers.
    pub fingerprint: u64,
}

const FILES: [&str; 11] = [
    "weapons.ron",
    "ammo.ron",
    "recoil_patterns.ron",
    "armor.ron",
    "attachments.ron",
    "movement.ron",
    "combat.ron",
    "hitboxes.ron",
    "rules.ron",
    "net.ron",
    "items.ron",
];

macro_rules! embedded {
    ($name:literal) => {
        ($name, include_str!(concat!("../../../assets/data/", $name)))
    };
}

const EMBEDDED: [(&str, &str); 11] = [
    embedded!("weapons.ron"),
    embedded!("ammo.ron"),
    embedded!("recoil_patterns.ron"),
    embedded!("armor.ron"),
    embedded!("attachments.ron"),
    embedded!("movement.ron"),
    embedded!("combat.ron"),
    embedded!("hitboxes.ron"),
    embedded!("rules.ron"),
    embedded!("net.ron"),
    embedded!("items.ron"),
];

fn parse<T: serde::de::DeserializeOwned>(file: &str, text: &str) -> Result<T, DataError> {
    ron::from_str(text).map_err(|source| DataError::Parse { file: file.to_owned(), source: Box::new(source) })
}

fn fnv1a(hash: u64, bytes: &[u8]) -> u64 {
    bytes.iter().fold(hash, |h, b| (h ^ *b as u64).wrapping_mul(0x100_0000_01b3))
}

impl GameData {
    /// The data compiled into the binary (always valid; checked by tests).
    pub fn embedded() -> Self {
        Self::from_sources(|name| {
            Ok(EMBEDDED.iter().find(|(n, _)| *n == name).map(|(_, t)| t.to_string()).unwrap_or_default())
        })
        .expect("embedded game data is valid")
    }

    /// Load the `.ron` files from a directory (for tuning without a rebuild).
    pub fn load_dir(dir: &Path) -> Result<Self, DataError> {
        Self::from_sources(|name| {
            let path = dir.join(name);
            std::fs::read_to_string(&path).map_err(|source| DataError::Io { path, source })
        })
    }

    pub fn from_sources(mut read: impl FnMut(&str) -> Result<String, DataError>) -> Result<Self, DataError> {
        let mut texts = Vec::with_capacity(FILES.len());
        let mut fingerprint = 0xcbf2_9ce4_8422_2325_u64;
        for name in FILES {
            let text = read(name)?;
            fingerprint = fnv1a(fingerprint, text.as_bytes());
            texts.push(text);
        }
        let data = GameData {
            weapons: parse(FILES[0], &texts[0])?,
            ammo: parse(FILES[1], &texts[1])?,
            recoil_patterns: parse(FILES[2], &texts[2])?,
            armor: parse(FILES[3], &texts[3])?,
            attachments: parse(FILES[4], &texts[4])?,
            movement: parse(FILES[5], &texts[5])?,
            combat: parse(FILES[6], &texts[6])?,
            hitboxes: parse(FILES[7], &texts[7])?,
            rules: parse(FILES[8], &texts[8])?,
            net: parse(FILES[9], &texts[9])?,
            items: parse(FILES[10], &texts[10])?,
            fingerprint,
        };
        data.validate()?;
        Ok(data)
    }

    /// Cross-reference checks the type system cannot express.
    pub fn validate(&self) -> Result<(), DataError> {
        let bad = |m: String| Err(DataError::Invalid(m));
        for w in &self.weapons.weapons {
            if w.falloff.is_empty() || w.falloff.windows(2).any(|p| p[1].0 <= p[0].0) {
                return bad(format!("{}: falloff ranges must be strictly increasing", w.id));
            }
            if w.rpm <= 0.0 {
                return bad(format!("{}: rpm must be positive", w.id));
            }
            if let RecoilSpec::Pattern(p) = &w.recoil
                && !self.recoil_patterns.contains_key(&p.pattern)
            {
                return bad(format!("{}: unknown recoil pattern {}", w.id, p.pattern));
            }
            if self.ammo.resolve(w.cls, AmmoChoice::STANDARD).is_none() {
                return bad(format!("{}: no ammo class entry for {:?}", w.id, w.cls));
            }
            match self.attachment(&w.mag_default) {
                Some(m) if m.cat == AttachmentCategory::Mag && m.capacity.is_some() => {}
                _ => {
                    return bad(format!("{}: mag_default {} is not a magazine", w.id, w.mag_default));
                }
            }
        }
        for p in self.recoil_patterns.values() {
            if p.kicks.is_empty() || p.loop_from_index >= p.kicks.len() {
                return bad("recoil pattern loop_from_index out of range".into());
            }
        }
        for wc in [WeightClass::None, WeightClass::Light, WeightClass::Medium, WeightClass::Heavy] {
            if !self.armor.weight_effects.contains_key(&wc) {
                return bad(format!("armor: missing weight_effects for {wc:?}"));
            }
        }
        for core in Core::ALL {
            let cap_ok = self.armor.capacity.get(&core).is_some_and(|c| c.len() == 4);
            if !cap_ok || !self.armor.regen.contains_key(&core) {
                return bad(format!("armor: need 4 capacities and a regen entry for {core:?}"));
            }
        }
        for p in &self.armor.presets {
            let any = p.tiers.iter().any(|(_, t)| *t > 0);
            if p.core.is_some() != any || p.tiers.iter().any(|(_, t)| *t > 4) {
                return bad(format!("{}: arc tiers must be 0-4, with a core exactly when any arc is covered", p.id));
            }
        }
        for (class, c) in &self.ammo.classes {
            if c.pen.iter().any(|p| !(0.05..=5.0).contains(p)) {
                return bad(format!("ammo class {class:?}: shield multiplier (pen) must be within 0.05..5"));
            }
        }
        for (kind, t) in &self.ammo.types {
            if t.tiers.is_empty() || t.tiers.len() > 3 {
                return bad(format!("ammo type {kind:?}: needs 1 to 3 tiers"));
            }
            for tier in &t.tiers {
                let ok = tier.pen_mult > 0.0
                    && tier.damage_mult > 0.0
                    && tier.flesh_mult > 0.0
                    && tier.spill_mult > 0.0
                    && (0.0..=1.0).contains(&tier.bypass_chance)
                    && tier.bleed.is_none_or(|b| b.hp_per_s >= 0.0 && b.residual_hp_per_s <= b.hp_per_s);
                if !ok {
                    return bad(format!("ammo type {kind:?}: invalid tier {tier:?}"));
                }
            }
        }
        if !(0.0..=1.0).contains(&self.ammo.spill_cap) {
            return bad("ammo spill_cap must be within 0..1".into());
        }
        let l = &self.rules.default_loadout;
        let Some(w) = self.weapon(&l.primary) else {
            return bad(format!("default loadout: unknown weapon {}", l.primary));
        };
        if l.mags.is_empty() || l.mags.len() > crate::weapon::MAX_MAGS {
            return bad(format!("default loadout: 1..={} magazines", crate::weapon::MAX_MAGS));
        }
        for m in &l.mags {
            if self.ammo.resolve(w.cls, *m).is_none_or(|a| !a.player_loadout) {
                return bad(format!("default loadout: {} cannot load {m:?}", l.primary));
            }
        }
        for a in &l.attachments {
            match self.attachment(a) {
                Some(spec) if spec.fits.iter().any(|f| f == &l.primary) => {}
                _ => return bad(format!("default loadout: {a} does not fit {}", l.primary)),
            }
        }
        if self.armor.preset(&l.armor).is_none() {
            return bad(format!("default loadout: unknown armor {}", l.armor));
        }
        for mode in [Mode::Tdm, Mode::Range] {
            let kit = self.items.kits.get(mode);
            if kit.len() > crate::items::MAX_KIT {
                return bad(format!("{mode:?} kit: at most {} items", crate::items::MAX_KIT));
            }
            let rules = self.rules.rulesets.get(mode);
            for e in kit {
                let Some(i) = self.items.index(&e.item) else {
                    return bad(format!("{mode:?} kit: unknown item {}", e.item));
                };
                if e.count == 0 {
                    return bad(format!("{mode:?} kit: {} has a count of 0", e.item));
                }
                if self.items.items[i].scope == crate::items::ItemScope::Region && !rules.regional_items {
                    return bad(format!("{mode:?} kit: {} treats one region, which this mode's rules forbid", e.item));
                }
            }
        }
        for i in &self.items.items {
            if i.use_s <= 0.0 || !(0.0..=1.0).contains(&i.shield_frac) || i.heal_hp < 0.0 {
                return bad(format!("item {}: use_s > 0, heal_hp >= 0, shield_frac within 0..1", i.id));
            }
        }
        Ok(())
    }

    pub fn tick_dt(&self) -> f32 {
        1.0 / self.net.tick_hz as f32
    }

    pub fn weapon(&self, id: &str) -> Option<&WeaponSpec> {
        self.weapons.weapons.iter().find(|w| w.id == id)
    }

    pub fn weapon_index(&self, id: &str) -> Option<usize> {
        self.weapons.weapons.iter().position(|w| w.id == id)
    }

    /// Resolve an ammo choice for a weapon (None if that gun cannot load it).
    pub fn ammo_for(&self, weapon: &WeaponSpec, choice: AmmoChoice) -> Option<AmmoSpec> {
        self.ammo.resolve(weapon.cls, choice)
    }

    pub fn attachment(&self, id: &str) -> Option<&AttachmentSpec> {
        self.attachments.attachments.iter().find(|a| a.id == id)
    }

    pub fn recoil_pattern(&self, weapon: &WeaponSpec) -> Option<&RecoilPattern> {
        match &weapon.recoil {
            RecoilSpec::Pattern(p) => self.recoil_patterns.get(&p.pattern),
            RecoilSpec::Kick(_) => None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_data_loads_and_validates() {
        let d = GameData::embedded();
        assert_eq!(d.weapons.weapons.len(), 2);
        assert_eq!(d.net.tick_hz, d.weapons.tick_hz);
        assert!(d.weapon("ar7_mako").is_some());
        assert_ne!(d.fingerprint, 0);
    }

    #[test]
    fn disk_data_matches_embedded() {
        let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../assets/data");
        let disk = GameData::load_dir(&dir).expect("load assets/data");
        assert_eq!(disk, GameData::embedded());
    }

    #[test]
    fn recoil_pattern_loops_for_long_mags() {
        let d = GameData::embedded();
        let p = &d.recoil_patterns["mako_recoil_pattern"];
        assert_eq!(p.kick(1), (0.55, 0.0));
        assert_eq!(p.kick(29), (0.02, -0.1));
        // shot 30 continues from index 20 (shot 21), and the loop has period 9
        assert_eq!(p.kick(30), p.kick(21));
        assert_eq!(p.kick(38), p.kick(29));
        assert_eq!(p.kick(39), p.kick(21));
    }

    #[test]
    fn weight_class_bands() {
        let a = &GameData::embedded().armor;
        assert_eq!(a.weight_class(0), WeightClass::None);
        assert_eq!(a.weight_class(4), WeightClass::Light);
        assert_eq!(a.weight_class(6), WeightClass::Medium);
        assert_eq!(a.weight_class(9), WeightClass::Heavy);
        assert_eq!(a.weight_class(16), WeightClass::Heavy);
    }

    #[test]
    fn attachment_modifiers_multiply() {
        let d = GameData::embedded();
        let t = ModifierTotals::combine([
            d.attachment("mako_stock_precision").unwrap(),
            d.attachment("grip_vertical").unwrap(),
        ]);
        assert!((t.recoil_v - 0.9 * 0.88).abs() < 1e-6);
        assert!((t.ads_time - 1.1 * 1.03).abs() < 1e-6);
        assert_eq!(t.hip_spread, 1.0);
    }

    #[test]
    fn per_section_armor_resolves() {
        let d = GameData::embedded();
        let v = d.armor.resolve_id("arm_bulwark_vanguard").unwrap();
        assert_eq!(v.tiers.torso, 4);
        assert_eq!(v.arc_capacity.torso, 165.0);
        assert!((v.arc_capacity.head - 100.0 * 0.6).abs() < 1e-4);
        assert!((v.arc_capacity.legs - 65.0 * 0.6).abs() < 1e-4);
        assert_eq!(v.gear_cost, 2 + 4 + 2 + 1);
        assert_eq!(v.weight_class, WeightClass::Heavy);
        assert_eq!(v.coverage, vec![Zone::Head, Zone::Torso, Zone::Arms, Zone::Legs]);
        let none = d.armor.resolve_id("arm_none").unwrap();
        assert_eq!(none.weight_class, WeightClass::None);
        assert_eq!(none.capacity, 0.0);
    }

    #[test]
    fn smg_standard_only_slightly_beats_t1() {
        let d = GameData::embedded();
        let smg = d.ammo.resolve(WeaponClass::Smg, AmmoChoice::STANDARD).unwrap();
        assert!(smg.pen_for_tier(1) >= 1.0 && smg.pen_for_tier(1) <= 1.2);
        assert!(smg.pen[1..].iter().all(|p| *p <= 1.0));
        assert_eq!(smg.pen_for_tier(0), 1.0);
        assert_eq!(smg.label, "STD");
        assert!(smg.player_loadout);
    }

    #[test]
    fn ap_tiers_shred_more() {
        let d = GameData::embedded();
        let ap = |t| {
            d.ammo.resolve(WeaponClass::AssaultRifle, AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: t }).unwrap()
        };
        assert!(ap(1).pen[2] < ap(2).pen[2] && ap(2).pen[2] < ap(3).pen[2]);
        assert!(ap(1).pen.iter().all(|p| *p > 1.0) && ap(1).damage_mult > 1.0);
        assert!(ap(1).gear_cost > 0 && ap(1).gear_cost < ap(3).gear_cost);
        assert_eq!(ap(2).label, "AP II");
        assert!(
            d.ammo.resolve(WeaponClass::AssaultRifle, AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 4 }).is_none()
        );
    }

    #[test]
    fn rip_is_smg_only_and_slugs_shotgun_only() {
        let d = GameData::embedded();
        let rip = AmmoChoice { kind: AmmoKind::Rip, tier: 2 };
        assert!(d.ammo.resolve(WeaponClass::Smg, rip).is_some());
        assert!(d.ammo.resolve(WeaponClass::AssaultRifle, rip).is_none());
        let slug = AmmoChoice { kind: AmmoKind::Slug, tier: 1 };
        assert!(d.ammo.resolve(WeaponClass::Shotgun, slug).is_some());
        assert!(d.ammo.resolve(WeaponClass::AssaultRifle, slug).is_none());
    }

    #[test]
    fn shrapnel_is_npc_only() {
        let d = GameData::embedded();
        let shr = d.ammo.resolve(WeaponClass::AssaultRifle, AmmoChoice { kind: AmmoKind::Shrapnel, tier: 1 }).unwrap();
        assert!(!shr.player_loadout);
        assert!(shr.bypass_chance > 0.0 && shr.bleed.is_some());
    }

    #[test]
    fn mako_standard_is_neutral_against_every_tier() {
        // Keeps the Mako on the design's numbers: nothing pierced in the design, nothing is multiplied here.
        let d = GameData::embedded();
        let a = d.ammo_for(d.weapon("ar7_mako").unwrap(), AmmoChoice::STANDARD).unwrap();
        assert_eq!(a.pen, [1.0; 4]);
        assert_eq!((a.damage_mult, a.flesh_mult, a.spill_mult), (1.0, 1.0, 1.0));
    }

    #[test]
    fn broken_data_is_rejected() {
        let mut d = GameData::embedded();
        d.weapons.weapons[0].mag_default = "optic_holo".into();
        assert!(d.validate().is_err());
    }
}
