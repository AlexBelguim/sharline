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
    /// Speed multiplier for carrying the gun. Aiming and firing never slow you (user direction 2026-10-08).
    pub move_mult_held: f32,
    pub spread_deg: SpreadSpec,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sway: Option<SwaySpec>,
    pub recoil: RecoilSpec,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scope: Option<ScopeSpec>,
    /// Out of the game for now (DIRECTION_LOG: the SMG is removed for now): no loadout screen, preset, bot or
    /// default offers it and the host refuses it, but its tuning stays so it can come back by clearing this.
    #[serde(default, skip_serializing_if = "is_false")]
    pub hidden: bool,
}

fn is_false(b: &bool) -> bool {
    !*b
}

fn one() -> f32 {
    1.0
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
    /// Short label (chips, the reload wheel): `STD`, `AP`; the tier numeral is added for multi-tier types.
    pub label: String,
    /// Long name for the Loadout screen (`STANDARD`, `AP`); empty = the label.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub name: String,
    /// One line for the Loadout screen's ammo picker.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub blurb: String,
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
    /// Points against the deathmatch loadout budget, paid once for the loadout's one ammo type.
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

/// A tier as a roman numeral (1 = I).
pub fn roman(tier: u8) -> &'static str {
    ROMAN[(tier.clamp(1, 4) - 1) as usize]
}

impl AmmoFile {
    /// The long name of an ammo choice: `STANDARD`, `AP II`, `SLUG I` (the numeral only for types with more
    /// than one tier).
    pub fn long_name(&self, choice: AmmoChoice) -> Option<String> {
        let ty = self.types.get(&choice.kind)?;
        let base = if ty.name.is_empty() { &ty.label } else { &ty.name };
        Some(if ty.tiers.len() > 1 { format!("{base} {}", roman(choice.tier)) } else { base.clone() })
    }

    pub fn resolve(&self, class: WeaponClass, choice: AmmoChoice) -> Option<AmmoSpec> {
        let base = self.classes.get(&class)?;
        let ty = self.types.get(&choice.kind)?;
        if !ty.only.is_empty() && !ty.only.contains(&class) {
            return None;
        }
        let tier = ty.tiers.get((choice.tier as usize).checked_sub(1)?)?;
        let pen = base.pen.map(|p| (p * tier.pen_mult).max(0.0));
        let label = if ty.tiers.len() > 1 { format!("{} {}", ty.label, roman(choice.tier)) } else { ty.label.clone() };
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

/// Random spread (cone half-angles, degrees) while moving: the bloom on top of the fixed recoil pattern (user
/// direction 2026-10-08, DIRECTION_LOG 17). Standing still (on the ground, under `move_threshold_frac` of jog
/// speed, any stance) a gun has no random spread at all, hip or aimed: the pattern is the whole story. Moving, hip
/// fire opens with speed and state (walk < jog < sprint, and the slide, air, zipline and jetpack floors) and with
/// sustained fire; aimed, the same cone is scaled down to `ads_move_mult`, so aimed shots stay accurate.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpreadSpec {
    /// On the ground below this fraction of jog speed counts as standing still: no random spread.
    pub move_threshold_frac: f32,
    /// Crouched (on the ground), the moving cone and its bloom are this much tighter.
    pub crouch_mult: f32,
    /// Hip-fire cone at walking speed, at jog speed (`move_full_hip`) and at sprint speed or faster; linear in
    /// between (from 0 at `move_threshold_frac`).
    pub walk_hip: f32,
    pub move_full_hip: f32,
    pub sprint_hip: f32,
    /// Hip-fire floors in the air, in a slide, on a zipline and on the jetpack.
    pub air: f32,
    pub slide: f32,
    pub zipline: f32,
    pub jetpack: f32,
    /// Aimed (from [`crate::weapon::ADS_AIMED`]), the movement cone is the hip cone (before hip attachments) times
    /// this.
    pub ads_move_mult: f32,
    /// Sustained fire while moving: each shot adds `bloom_per_shot_hip` (times how much the player moves) up to
    /// `bloom_max_hip`. Aimed, the same bloom counts at `bloom_max_ads / bloom_max_hip`.
    #[serde(default)]
    pub bloom_max_ads: f32,
    #[serde(default)]
    pub bloom_per_shot_hip: f32,
    #[serde(default)]
    pub bloom_max_hip: f32,
    /// The bloom settles at `bloom_decay_deg_per_s` (hip degrees) once no shot came for `bloom_decay_delay_s`.
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
    /// The pattern rewinds gradually during a pause and is back at bullet 1 this long after the last shot
    /// (`WeaponState::pattern_pos`): taps this far apart always fire bullet 1. Longer than the aimed fire interval.
    pub reset_after_s: f32,
    /// Fraction of the un-compensated climb that recovers on its own.
    pub recover_frac: f32,
    pub recover_delay_s: f32,
    pub recover_deg_per_s: f32,
    /// Purely visual camera punch per shot (does not move the aim).
    pub view_punch_visual_deg: f32,
    /// Seconds the visual punch takes to settle back (linearly). Shorter than the fire interval, so every shot
    /// reads as its own kick and the screen centre is back on the aim before the next one.
    pub view_punch_return_s: f32,
}

/// One fixed kick per shot (no randomness: the same every shot, so it can be learned).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct KickRecoilSpec {
    pub kick_pitch_deg: f32,
    /// Yaw right (+) per shot.
    pub kick_yaw_deg: f32,
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
    /// One line per core for the Loadout screen's core cards.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub core_blurbs: BTreeMap<Core, String>,
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AttachmentCategory {
    Optic,
    Stock,
    Mag,
    Under,
    Side,
    Shield,
}

impl AttachmentCategory {
    /// Slot order on the Loadout screen.
    pub const ALL: [AttachmentCategory; 6] = [
        AttachmentCategory::Optic,
        AttachmentCategory::Stock,
        AttachmentCategory::Mag,
        AttachmentCategory::Under,
        AttachmentCategory::Side,
        AttachmentCategory::Shield,
    ];

    pub fn label(self) -> &'static str {
        match self {
            AttachmentCategory::Optic => "OPTIC",
            AttachmentCategory::Stock => "STOCK",
            AttachmentCategory::Mag => "MAG",
            AttachmentCategory::Under => "UNDER",
            AttachmentCategory::Side => "SIDE",
            AttachmentCategory::Shield => "SHIELD",
        }
    }
}

/// An optic's magnification: one fixed zoom (`3.0`), or a variable optic's range (`[6.0, 12.0]`, min and
/// max) that the player scrolls through smoothly while aiming (the client's `scope_zoom`; the zoom is local
/// only, so it never reaches the wire or the simulation).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Zoom {
    Fixed(f32),
    Variable([f32; 2]),
}

impl Zoom {
    /// The lowest and highest zoom (the same for a fixed optic).
    pub fn range(self) -> (f32, f32) {
        match self {
            Zoom::Fixed(v) => (v, v),
            Zoom::Variable([lo, hi]) => (lo, hi),
        }
    }

    /// A scroll-to-zoom optic.
    pub fn is_variable(self) -> bool {
        matches!(self, Zoom::Variable(_))
    }

    /// `z` held inside the optic's range.
    pub fn clamp(self, z: f32) -> f32 {
        let (lo, hi) = self.range();
        if z.is_finite() { z.clamp(lo, hi) } else { lo }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AttachmentsFile {
    pub attachments: Vec<AttachmentSpec>,
    /// Categories a loadout may leave empty (the Loadout screen offers NONE); the others always hold a part.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub optional: Vec<AttachmentCategory>,
}

impl AttachmentsFile {
    pub fn is_optional(&self, cat: AttachmentCategory) -> bool {
        self.optional.contains(&cat)
    }
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
    /// Display name (`ANGLED GRIP`, `30-RND STANAG`); empty = the id.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub name: String,
    /// Short name for tight spots (the preview hotspot tags); empty = the name.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub short: String,
    /// One line for the Loadout screen's attachment list.
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub blurb: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub zoom: Option<Zoom>,
    /// A variable optic's zoom for a player who has never scrolled it (none: its lowest). Each player's own
    /// last zoom per optic is kept in their settings file.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub zoom_default: Option<f32>,
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
    /// The display name (the id when the data has none).
    pub fn display_name(&self) -> &str {
        if self.name.is_empty() { &self.id } else { &self.name }
    }

    /// The short display name.
    pub fn short_name(&self) -> &str {
        if self.short.is_empty() { self.display_name() } else { &self.short }
    }

    /// The zoom the optic starts at: a fixed optic's zoom, a variable one's `zoom_default` (inside its range)
    /// or its lowest; 1 for a part with no zoom.
    pub fn start_zoom(&self) -> f32 {
        match self.zoom {
            Some(z) => z.clamp(self.zoom_default.unwrap_or(z.range().0)),
            None => 1.0,
        }
    }

    /// A scroll-to-zoom optic's range (min, max).
    pub fn zoom_range(&self) -> Option<(f32, f32)> {
        self.zoom.filter(|z| z.is_variable()).map(Zoom::range)
    }

    pub fn modifiers(&self) -> Modifiers {
        Modifiers {
            ads_time: self.ads_time,
            move_mult: self.move_mult,
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
    /// How far (metres) the eye stays from any wall, ceiling or floor: the eye's height is held down under a
    /// low ceiling (a slide under a garage roller eases the eye down slower than the head goes under), so the
    /// view and the shots never start inside a wall. At least the camera's near-plane corner distance.
    pub clearance: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpeedSpec {
    pub walk: f32,
    pub jog: f32,
    pub sprint: f32,
    pub crouch: f32,
    pub backpedal_mult: f32,
    pub sprint_max_angle_deg: f32,
    /// A sprint lowers the gun only once it has been idle this long after its last shot (fire, aim and mag checks
    /// keep it up while they last), so semi-auto taps on the run do not bounce it up and down.
    pub sprint_gun_hold_s: f32,
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
    /// Strafe jumping builds speed up to this (m/s); past it, air control only turns the speed.
    pub air_strafe_max_speed: f32,
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
    /// A slide starts only while moving within this angle of where the player faces (no backward or
    /// sideways slides from a crouch-strafe).
    pub entry_max_angle_deg: f32,
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
    /// A ride ends this far plus the capsule radius short of each anchor (and short of anything solid on the line).
    pub end_clearance: f32,
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
    /// Free-for-all deathmatch on Showhome: everyone against everyone (user direction 2026-10-08).
    pub ffa: FfaRules,
    /// The loadout of team deathmatch and free-for-all (see [`RulesFile::fixed_loadout`]).
    pub deathmatch_loadout: DeathmatchLoadout,
    /// Kill streaks in team deathmatch and free-for-all (item 9c2, see [`crate::streak`]).
    pub streaks: crate::streak::StreakRules,
    pub rulesets: Rulesets,
    pub default_loadout: LoadoutSpec,
    /// Throwables every life starts with in the gun range (practice).
    #[serde(default)]
    pub range_throwables: crate::throwable::ThrowKit,
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
    pub ffa: Ruleset,
    pub range: Ruleset,
}

impl Rulesets {
    pub fn get(&self, mode: Mode) -> Ruleset {
        match mode {
            Mode::Tdm => self.tdm,
            Mode::Ffa => self.ffa,
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
    /// Free-for-all deathmatch on Showhome: no teams, every other player is an enemy, most kills wins.
    Ffa,
}

impl Mode {
    pub const ALL: [Mode; 3] = [Mode::Tdm, Mode::Ffa, Mode::Range];

    /// Players are split into two teams (team deathmatch only).
    pub fn has_teams(self) -> bool {
        self == Mode::Tdm
    }

    /// A scored match with a clock, a score limit and a lobby (team deathmatch and free-for-all).
    pub fn is_deathmatch(self) -> bool {
        matches!(self, Mode::Tdm | Mode::Ffa)
    }
}

impl RulesFile {
    /// A mode's match rules (limits, respawn, spawn protection, kill refill). The gun range respawns and
    /// protects like team deathmatch.
    pub fn deathmatch(&self, mode: Mode) -> &TdmRules {
        match mode {
            Mode::Ffa => &self.ffa,
            Mode::Tdm | Mode::Range => &self.tdm,
        }
    }

    /// The throwables each life starts with in `mode` (team deathmatch and free-for-all: their `throwables`).
    pub fn throw_kit(&self, mode: Mode) -> crate::throwable::ThrowKit {
        match mode {
            Mode::Tdm => self.tdm.throwables,
            Mode::Ffa => self.ffa.throwables,
            Mode::Range => self.range_throwables,
        }
    }

    /// The loadout rules of a mode with picks and points: team deathmatch and free-for-all share one
    /// ([`DeathmatchLoadout`]); the gun range has none (any halo core, a tier per arc, ammo per magazine).
    pub fn fixed_loadout(&self, mode: Mode) -> Option<&DeathmatchLoadout> {
        match mode {
            Mode::Tdm | Mode::Ffa => Some(&self.deathmatch_loadout),
            Mode::Range => None,
        }
    }
}

/// The team deathmatch and free-for-all loadout (user direction 2026-10-08, DIRECTION_LOG 17). A player
/// picks a gun and its parts (the magazine type among them), ONE armor tier and ONE ammo type; everything
/// else is fixed: no agent pick (the host deals agents at random), one halo core for everyone, and
/// [`DeathmatchLoadout::mags`] magazines of the picked type, all loaded with the picked ammo. The armor tier,
/// the ammo type (its `gear_cost`, paid once) and the magazine type cost points against the mode's
/// `gear_budget`.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct DeathmatchLoadout {
    /// The one halo: every player's halo has this core.
    pub halo_core: Core,
    /// Magazines every loadout carries, all of the picked type and ammo (slot 1 starts in the gun).
    pub mags: u8,
    /// Armor tiers T1, T2, ... in order: each a fixed combination of per-arc tiers (no new armor), and its
    /// points.
    pub armor: Vec<ArmorTierSpec>,
    /// Points of the NO HALO pick (tier 0: every arc 0, weight class None, so the fastest movement; user
    /// direction 2026-10-08, DIRECTION_LOG 18).
    pub no_halo_points: u32,
    /// Points of a magazine type (an attachment id of category `mag`); a type left out costs nothing (each
    /// gun's standard magazine).
    #[serde(default)]
    pub mag_points: BTreeMap<String, u32>,
    /// Points of an optic (an attachment id of category `optic`); one left out costs nothing.
    #[serde(default)]
    pub optic_points: BTreeMap<String, u32>,
}

/// One armor tier of the deathmatch loadout.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ArmorTierSpec {
    /// The halo's tier on each arc.
    pub tiers: ZoneTable<u8>,
    pub points: u32,
}

impl DeathmatchLoadout {
    /// Armor tier `t` (1-based: T1 is 1; 0 is NO HALO, every arc 0 for [`DeathmatchLoadout::no_halo_points`]).
    pub fn armor_tier(&self, t: u8) -> Option<ArmorTierSpec> {
        match t {
            0 => Some(ArmorTierSpec { tiers: ZoneTable::splat(0), points: self.no_halo_points }),
            _ => self.armor.get(t as usize - 1).copied(),
        }
    }

    /// Every armor pick in the order the Loadout screen lists them: NO HALO (0) first, then T1, T2, ...
    pub fn armor_picks(&self) -> impl Iterator<Item = (u8, ArmorTierSpec)> + '_ {
        (0..=self.armor.len() as u8).filter_map(|t| self.armor_tier(t).map(|a| (t, a)))
    }

    /// The tier whose combination these arcs are exactly (1-based; 0 for no halo), if any.
    pub fn tier_of(&self, tiers: ZoneTable<u8>) -> Option<u8> {
        if tiers == ZoneTable::splat(0) {
            return Some(0);
        }
        self.armor.iter().position(|a| a.tiers == tiers).map(|i| i as u8 + 1)
    }

    /// The armor tier a halo becomes (an older loadout, or any halo a client sends): its own tier when it is
    /// one, else the highest tier whose torso does not exceed the halo's best head-or-torso tier (head and
    /// torso are what set the tiers apart), T1 at least. Mender Scout's H2 T2 becomes T2, Mender Medic's
    /// H1 T3 A1 L1 T3; no halo stays no halo (0).
    pub fn tier_for(&self, tiers: ZoneTable<u8>) -> u8 {
        if let Some(t) = self.tier_of(tiers) {
            return t;
        }
        let best = tiers.head.max(tiers.torso);
        self.armor.iter().rposition(|a| a.tiers.torso <= best).map_or(1, |i| i as u8 + 1)
    }

    /// Points of a magazine type.
    pub fn mag_points(&self, mag: &str) -> u32 {
        self.mag_points.get(mag).copied().unwrap_or(0)
    }

    /// Points of an optic.
    pub fn optic_points(&self, optic: &str) -> u32 {
        self.optic_points.get(optic).copied().unwrap_or(0)
    }

    /// Points of part `id` in slot `cat`: a magazine type or an optic may have a price, every other part is
    /// free.
    pub fn part_points(&self, cat: AttachmentCategory, id: &str) -> u32 {
        match cat {
            AttachmentCategory::Mag => self.mag_points(id),
            AttachmentCategory::Optic => self.optic_points(id),
            _ => 0,
        }
    }
}

/// Free-for-all has the same match rules as team deathmatch (`max_players` need not be even, and
/// `spawn_slack_m` adds a little randomness to the spawn pick).
pub type FfaRules = TdmRules;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TdmRules {
    /// The loadout's points (armor tier + ammo type + magazine type, see [`DeathmatchLoadout`]) must fit this.
    pub gear_budget: u32,
    pub score_limit: u32,
    pub time_limit_s: f32,
    /// Seconds after a death before the death screen's RESPAWN can be pressed.
    pub respawn_s: f32,
    /// A player who has not pressed RESPAWN is respawned anyway this many seconds after `respawn_s` ran out
    /// (0: at once, as before the death screen).
    #[serde(default)]
    pub auto_respawn_s: f32,
    pub spawn_protection_s: f32,
    pub max_players: u32,
    /// Magazines a kill tops back up (the killer's emptiest spare first, see `WeaponState::refill_mags`).
    #[serde(default)]
    pub kill_refill_mags: u8,
    /// Spawn pick: any spawn within this many metres of the farthest one from living enemies may be picked
    /// at random (0: always the farthest).
    #[serde(default)]
    pub spawn_slack_m: f32,
    /// An assist: a player other than the killer who dealt at least this much damage (halo and health) to the
    /// victim within `assist_window_s` before the kill (team deathmatch: enemies of the victim only).
    pub assist_min_damage: f32,
    pub assist_window_s: f32,
    /// Throwables every life starts with (item 10b: smoke grenades and molotovs).
    #[serde(default)]
    pub throwables: crate::throwable::ThrowKit,
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
    /// Smoke grenades and molotovs (`throwables.ron`, see [`crate::throwable`]).
    pub throwables: crate::throwable::ThrowablesFile,
    /// FNV-1a hash of the source text, so host and clients can check they run the same numbers.
    pub fingerprint: u64,
}

const FILES: [&str; 12] = [
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
    "throwables.ron",
];

macro_rules! embedded {
    ($name:literal) => {
        ($name, include_str!(concat!("../../../assets/data/", $name)))
    };
}

const EMBEDDED: [(&str, &str); 12] = [
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
    embedded!("throwables.ron"),
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
            throwables: parse(FILES[11], &texts[11])?,
            fingerprint,
        };
        data.validate()?;
        Ok(data)
    }

    /// Cross-reference checks the type system cannot express.
    pub fn validate(&self) -> Result<(), DataError> {
        let bad = |m: String| Err(DataError::Invalid(m));
        // Every stance's eye sits inside its own box, `clearance` from its top and sides: a settled view never
        // starts inside a wall or a ceiling the body fits under.
        let (cap, eye) = (&self.movement.capsule, &self.movement.eye_height);
        let eye_ok = [(eye.stand, cap.height_stand), (eye.crouch, cap.height_crouch), (eye.slide, cap.height_slide)]
            .iter()
            .all(|(e, h)| *e >= eye.clearance && *e + eye.clearance <= *h)
            && eye.clearance > 0.0
            && eye.clearance < cap.radius;
        if !eye_ok {
            return bad("movement: each eye height must sit `clearance` inside its stance's box".into());
        }
        if !(self.movement.zipline.end_clearance >= 0.0 && self.movement.zipline.end_clearance.is_finite()) {
            return bad("movement: zipline.end_clearance must be a finite distance of 0 or more".into());
        }
        for w in &self.weapons.weapons {
            if w.falloff.is_empty() || w.falloff.windows(2).any(|p| p[1].0 <= p[0].0) {
                return bad(format!("{}: falloff ranges must be strictly increasing", w.id));
            }
            if w.rpm <= 0.0 {
                return bad(format!("{}: rpm must be positive", w.id));
            }
            // Moving is never more accurate than standing still (no random spread there), and faster is never
            // tighter (DIRECTION_LOG 17): hip cones 0 < walk <= jog <= sprint <= every air / slide / zipline / jetpack
            // floor, aimed fire no wider than hip, and the still threshold under the slowest gait, so a crouch walk
            // counts as moving.
            let (sp, speed) = (&w.spread_deg, &self.movement.speed);
            let floors = [sp.air, sp.slide, sp.zipline, sp.jetpack];
            let blooms = [sp.bloom_max_ads, sp.bloom_per_shot_hip, sp.bloom_max_hip];
            let cones_ok = sp.walk_hip > 0.0
                && sp.walk_hip <= sp.move_full_hip
                && sp.move_full_hip <= sp.sprint_hip
                && floors.iter().all(|f| *f >= sp.sprint_hip)
                && (0.0..=1.0).contains(&sp.ads_move_mult)
                && blooms.iter().all(|b| *b >= 0.0)
                && sp.bloom_max_ads <= sp.bloom_max_hip;
            let threshold_ok =
                sp.move_threshold_frac > 0.0 && sp.move_threshold_frac * speed.jog < speed.walk.min(speed.crouch);
            let gaits_ok = speed.walk < speed.jog && speed.jog < speed.sprint;
            if !cones_ok || !(sp.crouch_mult > 0.0 && sp.crouch_mult <= 1.0) || !threshold_ok || !gaits_ok {
                return bad(format!(
                    "{}: hip cones must rise 0 < walk <= jog <= sprint <= air / slide / zipline / jetpack, aimed \
                     (ads_move_mult in [0, 1], bloom_max_ads <= bloom_max_hip) no wider than hip, crouch_mult in \
                     (0, 1], and the still threshold under walk and crouch speed",
                    w.id
                ));
            }
            if let RecoilSpec::Pattern(p) = &w.recoil
                && !self.recoil_patterns.contains_key(&p.pattern)
            {
                return bad(format!("{}: unknown recoil pattern {}", w.id, p.pattern));
            }
            // The gradual rewind (item 9c) starts after the aimed fire interval, so a held spray never rewinds: the
            // full rewind must be longer than that.
            if let RecoilSpec::Pattern(p) = &w.recoil {
                let hz = self.net.tick_hz;
                let hold = crate::weapon::fire_interval_ticks(w, hz, true);
                if crate::weapon::secs_to_ticks(p.reset_after_s, hz) <= hold {
                    return bad(format!("{}: recoil.reset_after_s must be longer than the aimed fire interval", w.id));
                }
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
        // Recoil roles (DESIGN_DELTAS.md section 15): a stock scales only the climb, an under-rail part (the front
        // grips) only the sideways sweep, so neither changes the shape of a pattern on the other axis.
        for a in &self.attachments.attachments {
            let wrong_axis = match a.cat {
                AttachmentCategory::Stock => a.recoil_h.is_some(),
                AttachmentCategory::Under => a.recoil_v.is_some(),
                _ => false,
            };
            if wrong_axis {
                return bad(format!("{}: stocks may only set recoil_v and under-rail parts only recoil_h", a.id));
            }
            // Zoom: only optics have one, at least 1x; a variable range rises, and its default sits inside it.
            if let Some(z) = a.zoom {
                let (lo, hi) = z.range();
                let rising = !z.is_variable() || hi > lo;
                if a.cat != AttachmentCategory::Optic || !(lo >= 1.0 && rising && hi.is_finite()) {
                    return bad(format!("{}: an optic's zoom is >= 1 and a variable range rises", a.id));
                }
            }
            if let Some(d) = a.zoom_default
                && a.zoom_range().is_none_or(|(lo, hi)| !(lo..=hi).contains(&d))
            {
                return bad(format!("{}: zoom_default needs a variable zoom range around it", a.id));
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
        if w.hidden {
            return bad(format!("default loadout: {} is hidden (out of the game for now)", l.primary));
        }
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
        if let Some(p) = self.rules.streaks.problem() {
            return bad(p);
        }
        let kit = &self.rules.deathmatch_loadout;
        if !(1..=crate::weapon::MAX_MAGS).contains(&(kit.mags as usize)) {
            return bad(format!("deathmatch loadout: 1..={} magazines", crate::weapon::MAX_MAGS));
        }
        if kit.armor.is_empty() {
            return bad("deathmatch loadout: at least one armor tier".into());
        }
        if kit.no_halo_points > kit.armor[0].points {
            return bad("deathmatch loadout: NO HALO at no more points than T1".into());
        }
        for (i, a) in kit.armor.iter().enumerate() {
            let caps = self.armor.loadout_tier_caps;
            if Zone::ALL.iter().any(|z| a.tiers[*z] == 0 || a.tiers[*z] > caps[*z]) {
                return bad(format!("deathmatch armor T{}: every arc 1 up to its loadout cap", i + 1));
            }
            if kit.armor[..i].iter().any(|b| b.tiers == a.tiers || b.points > a.points) {
                return bad(format!("deathmatch armor T{}: a new combination, at no fewer points than T{i}", i + 1));
            }
        }
        for id in kit.mag_points.keys() {
            if self.attachment(id).is_none_or(|a| a.cat != AttachmentCategory::Mag) {
                return bad(format!("deathmatch mag_points: {id} is not a magazine"));
            }
        }
        for id in kit.optic_points.keys() {
            let Some(a) = self.attachment(id).filter(|a| a.cat == AttachmentCategory::Optic) else {
                return bad(format!("deathmatch optic_points: {id} is not an optic"));
            };
            // A gun's own optic is always affordable: every loadout starts with it.
            if !a.default_for.is_empty() {
                return bad(format!("deathmatch optic_points: {id} is a gun's default optic and stays free"));
            }
        }
        for mode in Mode::ALL {
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
        if !(self.items.use_move_mult > 0.0 && self.items.use_move_mult <= 1.0) {
            return bad("items use_move_mult must be within (0, 1]".into());
        }
        for (n, i) in self.items.items.iter().enumerate() {
            if self.items.items[..n].iter().any(|o| o.id == i.id) {
                return bad(format!("item {}: duplicate id", i.id));
            }
            if i.use_s <= 0.0 || !(0.0..=1.0).contains(&i.shield_frac) || i.heal_hp < 0.0 {
                return bad(format!("item {}: use_s > 0, heal_hp >= 0, shield_frac within 0..1", i.id));
            }
        }
        self.throwables.validate().map_err(DataError::Invalid)?;
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

    /// A gun players may pick: it exists and is not hidden (see [`WeaponSpec::hidden`]).
    pub fn offered_weapon(&self, id: &str) -> Option<&WeaponSpec> {
        self.weapon(id).filter(|w| !w.hidden)
    }

    /// The guns players may pick, with their index in `weapons.ron` (indices stay those of the full list).
    pub fn offered_weapons(&self) -> impl Iterator<Item = (usize, &WeaponSpec)> {
        self.weapons.weapons.iter().enumerate().filter(|(_, w)| !w.hidden)
    }

    /// `id` if players may pick it, else the default loadout's gun (an old save or preset with a hidden gun).
    pub fn offered_weapon_or_default<'a>(&'a self, id: &'a str) -> &'a str {
        if self.offered_weapon(id).is_some() { id } else { &self.rules.default_loadout.primary }
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
        assert_eq!(d.weapons.weapons.len(), 3);
        assert_eq!(d.net.tick_hz, d.weapons.tick_hz);
        assert!(d.weapon("ar7_mako").is_some());
        assert_eq!(d.weapon("sk9_skink").map(|w| w.cls), Some(WeaponClass::Smg));
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
        assert_eq!(p.kick(1), (0.95, 0.0));
        assert_eq!(p.kick(36), (0.08, 0.56));
        // shot 37 continues from index 20 (shot 21): the two full sweeps of the T's bar, period 16
        assert_eq!(p.kick(37), p.kick(21));
        assert_eq!(p.kick(52), p.kick(36));
        assert_eq!(p.kick(53), p.kick(21));
        assert_eq!(p.kick(59), p.kick(27));
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
        assert!((t.recoil_v - 0.8).abs() < 1e-6);
        assert!((t.recoil_h - 0.78).abs() < 1e-6);
        assert!((t.ads_time - 1.1 * 1.03).abs() < 1e-6);
        assert!((t.sway - 0.8 * 0.95).abs() < 1e-6);
        assert_eq!(t.hip_spread, 1.0);
    }

    /// Playtest round 3 (DIRECTION_LOG 18): stocks lower only the vertical recoil (the climb), front grips only the
    /// horizontal (the sweep), each by its own amount. A gun's default stock is its plain pattern.
    #[test]
    fn stocks_lower_the_climb_and_grips_the_sweep() {
        let d = GameData::embedded();
        let (mut stocks, mut grips) = (0, 0);
        for w in &d.weapons.weapons {
            let fits = |cat| d.attachments.attachments.iter().filter(move |a| a.cat == cat && a.fits.contains(&w.id));
            let mut amounts = vec![];
            for a in fits(AttachmentCategory::Stock) {
                assert_eq!(a.recoil_h, None, "{}: a stock never touches the sweep", a.id);
                if a.default_for.contains(&w.id) {
                    assert_eq!(a.recoil_v, None, "{}: the default stock is the plain pattern", a.id);
                } else {
                    let v = a.recoil_v.unwrap_or_else(|| panic!("{}: a stock lowers the climb", a.id));
                    assert!(v > 0.5 && v < 1.0, "{}: {v}", a.id);
                    amounts.push(v);
                    stocks += 1;
                }
            }
            for a in fits(AttachmentCategory::Under) {
                assert_eq!(a.recoil_v, None, "{}: an under-rail part never touches the climb", a.id);
                if a.id.starts_with("grip_") {
                    let h = a.recoil_h.unwrap_or_else(|| panic!("{}: a front grip lowers the sweep", a.id));
                    assert!(h > 0.5 && h < 1.0, "{}: {h}", a.id);
                    assert!(!a.display_name().contains("VERTICAL"), "{}: its name promised vertical recoil", a.id);
                    amounts.push(10.0 + h);
                    grips += 1;
                }
            }
            let n = amounts.len();
            amounts.sort_by(f32::total_cmp);
            amounts.dedup();
            assert_eq!(amounts.len(), n, "{}: every stock and every grip has its own amount", w.id);
        }
        assert_eq!((stocks, grips), (3, 3), "the Mako's precision and light stocks, the Warden's folding, three grips");
        // The data check holds the roles.
        let mut bad = GameData::embedded();
        bad.attachments.attachments.iter_mut().find(|a| a.id == "mako_stock_light").unwrap().recoil_h = Some(0.9);
        assert!(bad.validate().is_err(), "a stock on the sweep");
        let mut bad = GameData::embedded();
        bad.attachments.attachments.iter_mut().find(|a| a.id == "grip_angled").unwrap().recoil_v = Some(0.9);
        assert!(bad.validate().is_err(), "a grip on the climb");
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

    /// Free-for-all: its own limits in rules.ron, team deathmatch's switches, no teams.
    #[test]
    fn free_for_all_rules() {
        let d = GameData::embedded();
        let ffa = d.rules.deathmatch(Mode::Ffa);
        assert_eq!(ffa, &d.rules.ffa);
        assert_eq!(d.rules.deathmatch(Mode::Tdm), &d.rules.tdm);
        assert_eq!(d.rules.deathmatch(Mode::Range), &d.rules.tdm, "the range respawns like team deathmatch");
        assert_eq!(ffa.score_limit, 25);
        assert_eq!(ffa.max_players, 8);
        assert_eq!(ffa.kill_refill_mags, d.rules.tdm.kill_refill_mags);
        assert!(ffa.spawn_slack_m > 0.0 && d.rules.tdm.spawn_slack_m == 0.0);
        assert_eq!(d.rules.rulesets.get(Mode::Ffa), d.rules.rulesets.tdm, "same switches as team deathmatch");
        assert_eq!(d.items.kits.get(Mode::Ffa), d.items.kits.get(Mode::Tdm), "the deathmatch kit");
        assert!(Mode::Tdm.has_teams() && !Mode::Ffa.has_teams() && !Mode::Range.has_teams());
        assert!(Mode::Tdm.is_deathmatch() && Mode::Ffa.is_deathmatch() && !Mode::Range.is_deathmatch());
        // The death screen: RESPAWN after the timer, and a fallback respawn for players who never press it.
        for mode in Mode::ALL {
            let r = d.rules.deathmatch(mode);
            assert!(r.respawn_s > 0.0, "{mode:?}: a respawn timer");
            assert!(r.auto_respawn_s > 0.0, "{mode:?}: time to read the death screen before the fallback");
            // Assists: some real damage, recently (not a single graze, not a fight long over).
            assert!(r.assist_min_damage > 0.0 && r.assist_window_s > 0.0, "{mode:?}: an assist rule");
        }
        assert_eq!((d.rules.tdm.assist_min_damage, d.rules.tdm.assist_window_s), (40.0, 10.0));
    }

    /// The SMG is out for now (DIRECTION_LOG: "remove the smg for now"): its data stays, hidden, so the
    /// players' guns are the Mako and the Warden, and a hidden gun falls back to the default loadout's.
    #[test]
    fn the_skink_is_hidden_but_kept() {
        let d = GameData::embedded();
        let skink = d.weapon("sk9_skink").expect("its tuning stays in weapons.ron");
        assert!(skink.hidden);
        assert!(d.offered_weapon("sk9_skink").is_none());
        let offered: Vec<(usize, &str)> = d.offered_weapons().map(|(i, w)| (i, w.id.as_str())).collect();
        assert_eq!(offered, [(0, "ar7_mako"), (1, "vk50_warden")], "indices of the full list");
        assert_eq!(d.offered_weapon_or_default("sk9_skink"), "ar7_mako");
        assert_eq!(d.offered_weapon_or_default("nope"), "ar7_mako");
        assert_eq!(d.offered_weapon_or_default("vk50_warden"), "vk50_warden");
        // A hidden gun cannot be the default loadout's.
        let mut bad = d.clone();
        bad.rules.default_loadout.primary = "sk9_skink".into();
        bad.rules.default_loadout.attachments.clear();
        assert!(bad.validate().is_err());
    }

    #[test]
    fn broken_data_is_rejected() {
        let mut d = GameData::embedded();
        d.weapons.weapons[0].mag_default = "optic_holo".into();
        assert!(d.validate().is_err());
        // the deathmatch armor tiers: within the caps, every arc covered, new combinations, rising points
        let broken = |f: &dyn Fn(&mut DeathmatchLoadout)| {
            let mut d = GameData::embedded();
            f(&mut d.rules.deathmatch_loadout);
            d.validate().is_err()
        };
        assert!(broken(&|k| k.armor[3].tiers.legs = 4), "legs above their cap");
        assert!(broken(&|k| k.armor[0].tiers.arms = 0), "an uncovered arc");
        assert!(broken(&|k| k.armor[2] = k.armor[1]), "the same combination twice");
        assert!(broken(&|k| k.armor[0].points = 9), "T1 dearer than T2");
        assert!(broken(&|k| k.armor.clear()));
        assert!(broken(&|k| k.no_halo_points = 2), "no halo dearer than T1");
        assert!(broken(&|k| k.mags = 7));
        assert!(broken(&|k| _ = k.mag_points.insert("optic_holo".into(), 1)), "not a magazine");
        assert!(broken(&|k| _ = k.optic_points.insert("mag_45".into(), 1)), "not an optic");
        assert!(broken(&|k| _ = k.optic_points.insert("optic_holo".into(), 1)), "a gun's default optic");
    }

    /// Item 8d: the Warden's sniper scope zooms 6x-12x and the new 1-3x variable optic (an extra, dearer choice
    /// next to the fixed 3x, which stays) zooms 1x-3x, on the same guns as the 3x. Zoom ranges live in the data
    /// and the data check holds them.
    #[test]
    fn variable_optics_have_a_zoom_range() {
        let d = GameData::embedded();
        let a = |id: &str| d.attachment(id).unwrap_or_else(|| panic!("{id}"));
        let (sniper, var, fixed) = (a("optic_sniper"), a("optic_1_3x"), a("optic_3x"));
        assert_eq!(sniper.zoom, Some(Zoom::Variable([6.0, 12.0])));
        assert_eq!((sniper.zoom_range(), sniper.start_zoom()), (Some((6.0, 12.0)), 6.0));
        assert_eq!(var.cat, AttachmentCategory::Optic);
        assert_eq!((var.zoom_range(), var.start_zoom()), (Some((1.0, 3.0)), 1.0));
        assert_eq!(var.fits, fixed.fits, "the 1-3x fits the same guns as the 3x");
        assert!(var.default_for.is_empty(), "an extra pick, never a gun's default");
        assert!(!var.display_name().is_empty() && !var.blurb.is_empty());
        assert_eq!(fixed.zoom, Some(Zoom::Fixed(3.0)), "the fixed 3x stays");
        assert_eq!(fixed.zoom_range(), None);
        let k = &d.rules.deathmatch_loadout;
        assert_eq!((k.optic_points("optic_1_3x"), k.optic_points("optic_3x")), (1, 0), "dearer than the 3x");
        assert_eq!(k.part_points(AttachmentCategory::Optic, "optic_1_3x"), 1);
        assert_eq!(k.part_points(AttachmentCategory::Mag, "mag_drum60"), 2);
        assert_eq!(k.part_points(AttachmentCategory::Stock, "optic_1_3x"), 0);
        // clamping
        assert_eq!(Zoom::Variable([6.0, 12.0]).clamp(20.0), 12.0);
        assert_eq!(Zoom::Variable([6.0, 12.0]).clamp(2.0), 6.0);
        assert_eq!(Zoom::Variable([6.0, 12.0]).clamp(f32::NAN), 6.0);
        assert_eq!(Zoom::Fixed(3.0).clamp(9.0), 3.0);
        // the data check
        let broken = |f: &dyn Fn(&mut AttachmentSpec)| {
            let mut d = GameData::embedded();
            f(d.attachments.attachments.iter_mut().find(|a| a.id == "optic_1_3x").unwrap());
            d.validate().is_err()
        };
        assert!(!broken(&|_| ()));
        assert!(broken(&|a| a.zoom = Some(Zoom::Variable([3.0, 1.0]))), "a falling range");
        assert!(broken(&|a| a.zoom = Some(Zoom::Variable([0.5, 3.0]))), "below 1x");
        assert!(broken(&|a| a.zoom_default = Some(4.0)), "a default outside the range");
        assert!(broken(&|a| a.cat = AttachmentCategory::Side), "a zoom on a non-optic");
        let mut d3 = GameData::embedded();
        d3.attachments.attachments.iter_mut().find(|a| a.id == "optic_3x").unwrap().zoom_default = Some(3.0);
        assert!(d3.validate().is_err(), "a default needs a variable range");
        // RON: a fixed zoom is a number, a variable one a [min, max] pair
        let z: Option<Zoom> = ron::from_str("Some([1.0, 3.0])").unwrap();
        assert_eq!(z, Some(Zoom::Variable([1.0, 3.0])));
        assert_eq!(ron::from_str::<Option<Zoom>>("Some(3.0)").unwrap(), Some(Zoom::Fixed(3.0)));
    }

    /// The deathmatch armor tiers are the user's combinations (DIRECTION_LOG 17), and an older halo becomes
    /// the tier of its best head or torso arc.
    #[test]
    fn deathmatch_armor_tiers() {
        let d = GameData::embedded();
        let k = &d.rules.deathmatch_loadout;
        let t = |h, t, a, l| ZoneTable { head: h, torso: t, arms: a, legs: l };
        let combos: Vec<ZoneTable<u8>> = k.armor.iter().map(|a| a.tiers).collect();
        assert_eq!(combos, [t(1, 1, 1, 1), t(2, 2, 2, 2), t(3, 3, 1, 1), t(4, 4, 3, 2)]);
        assert_eq!(k.armor[3].tiers, d.armor.loadout_tier_caps, "T4 is the best combination a loadout allows");
        let weight = |i: usize| d.armor.weight_class(k.armor[i].tiers.iter().map(|(_, t)| *t as u32).sum());
        assert_eq!(
            [weight(0), weight(1), weight(2), weight(3)],
            [WeightClass::Light, WeightClass::Medium, WeightClass::Medium, WeightClass::Heavy]
        );
        assert_eq!(k.halo_core, Core::Mender);
        assert_eq!(k.mags, 6, "everyone carries six magazines");
        for (i, c) in combos.iter().enumerate() {
            assert_eq!(k.tier_of(*c), Some(i as u8 + 1));
            assert_eq!(k.tier_for(*c), i as u8 + 1);
            assert_eq!(k.armor_tier(i as u8 + 1).map(|a| a.tiers), Some(*c));
        }
        assert_eq!(k.armor_tier(5), None);
        // NO HALO (DIRECTION_LOG 18): the first pick, 0 points, every arc 0, weight class None
        let none = k.armor_tier(0).unwrap();
        assert_eq!((none.tiers, none.points), (t(0, 0, 0, 0), 0));
        assert_eq!(d.armor.weight_class(0), WeightClass::None);
        assert_eq!((k.tier_of(none.tiers), k.tier_for(none.tiers)), (Some(0), 0));
        let picks: Vec<(u8, u32)> = k.armor_picks().map(|(t, a)| (t, a.points)).collect();
        assert_eq!(picks, [(0, 0), (1, 1), (2, 2), (3, 3), (4, 5)]);
        let fx = |w| d.armor.effects(w).move_mult;
        assert!(fx(WeightClass::None) >= fx(WeightClass::Light), "no halo moves fastest");
        assert_eq!(k.tier_for(t(2, 2, 0, 0)), 2, "Mender Scout");
        assert_eq!(k.tier_for(t(1, 3, 1, 1)), 3, "Mender Medic");
        assert_eq!(k.tier_for(t(4, 4, 4, 4)), 4, "the uncapped Juggernaut");
        assert_eq!(k.tier_for(t(0, 0, 3, 2)), 1, "no head or torso arc");
        assert_eq!(k.mag_points("mag_30"), 0);
        assert_eq!(k.mag_points("mag_drum60"), 2);
    }

    /// Spread tuning can never make moving as accurate as standing still, a faster state tighter than a slower one,
    /// or aimed fire wider than hip fire (DIRECTION_LOG 17).
    #[test]
    fn spread_that_rewards_moving_is_rejected() {
        let ok = GameData::embedded();
        assert!(ok.validate().is_ok());
        type Break = fn(&mut SpreadSpec);
        let broken: [(&str, Break); 9] = [
            ("no cone at a walk", |s| s.walk_hip = 0.0),
            ("a jog tighter than a walk", |s| s.move_full_hip = s.walk_hip * 0.5),
            ("a sprint tighter than a jog", |s| s.sprint_hip = s.move_full_hip * 0.5),
            ("a slide tighter than a sprint", |s| s.slide = s.sprint_hip * 0.5),
            ("the air tighter than a sprint", |s| s.air = s.sprint_hip * 0.5),
            ("aimed wider than hip", |s| s.ads_move_mult = 1.5),
            ("aimed bloom past hip bloom", |s| s.bloom_max_ads = s.bloom_max_hip + 1.0),
            ("no still threshold", |s| s.move_threshold_frac = 0.0),
            ("a NaN cone", |s| s.zipline = f32::NAN),
        ];
        for (why, f) in broken {
            let mut d = ok.clone();
            f(&mut d.weapons.weapons[0].spread_deg);
            assert!(d.validate().is_err(), "{why}");
        }
    }
}
