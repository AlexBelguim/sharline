//! The loadout being edited on the Loadout screen, its rules and its derived numbers. Engine-free, so it
//! is tested on its own: attachments per slot, the contiguous magazine list (1..=6, slot 1 in the gun,
//! slot index = reload-wheel position), the custom halo, the gear budget and the weapon stats.

use std::collections::BTreeMap;
use vetf_net::LoadoutChoice;
use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::ZoneTable;
use vetf_sim::data::{AmmoChoice, AmmoKind, AttachmentCategory, AttachmentSpec, Core, WeaponSpec, Zoom};
use vetf_sim::gear::{GearCost, HaloChoice, gear_cost};
use vetf_sim::weapon::MAX_MAGS;

/// The edit in progress.
#[derive(Debug, Clone, PartialEq)]
pub struct Draft {
    pub agent: String,
    pub weapon: String,
    /// Chosen attachment ids per weapon id: the current weapon's set is the loadout's, the others are what
    /// each gun had last (a weapon tab brings its set back).
    pub parts: BTreeMap<String, Vec<String>>,
    /// Magazines in slot order: 1..=6, no gaps.
    pub mags: Vec<AmmoChoice>,
    pub halo: HaloChoice,
    /// Each arc's last tier above 0 (a re-checked arc gets it back).
    pub last_tiers: ZoneTable<u8>,
}

/// Why CONFIRM is off.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Problem {
    OverBudget {
        used: u32,
        budget: u32,
    },
    /// An arc above its loadout cap.
    TierCap,
    /// A magazine the gun cannot load (or NPC-only ammo).
    Ammo,
    /// No magazine at all (slot 1 must hold one).
    NoMag,
}

impl Draft {
    /// Open a loadout for editing (unknown or misfit ids are cleaned up; `remembered` = other guns' sets).
    pub fn from_choice(c: &LoadoutChoice, remembered: &BTreeMap<String, Vec<String>>, data: &GameData) -> Self {
        let weapon = if data.weapon(&c.weapon).is_some() {
            c.weapon.clone()
        } else {
            data.rules.default_loadout.primary.clone()
        };
        let mut parts = BTreeMap::new();
        for w in &data.weapons.weapons {
            let wanted = if w.id == weapon { Some(c.attachments.clone()) } else { remembered.get(&w.id).cloned() };
            parts.insert(w.id.clone(), normalize_parts(data, &w.id, wanted.as_deref()));
        }
        let spec = data.weapon(&weapon).expect("checked above");
        let mut mags: Vec<AmmoChoice> = c.mags.iter().take(MAX_MAGS).copied().collect();
        for m in &mut mags {
            if !ammo_ok(data, spec, *m) {
                *m = AmmoChoice::STANDARD;
            }
        }
        if mags.is_empty() {
            mags.push(AmmoChoice::STANDARD);
        }
        let halo = c.halo.capped(data.armor.loadout_tier_caps);
        let last_tiers = halo.tiers.map(|_, t| (*t).max(1));
        Self { agent: c.agent.clone(), weapon, parts, mags, halo, last_tiers }
    }

    /// The loadout to send to the host.
    pub fn choice(&self) -> LoadoutChoice {
        LoadoutChoice {
            weapon: self.weapon.clone(),
            mags: self.mags.clone(),
            attachments: self.parts.get(&self.weapon).cloned().unwrap_or_default(),
            halo: self.halo,
            agent: self.agent.clone(),
        }
    }

    pub fn spec<'a>(&self, data: &'a GameData) -> &'a WeaponSpec {
        data.weapon(&self.weapon).unwrap_or(&data.weapons.weapons[0])
    }

    // ------------------------------------------------------------------------------------------ attachments

    /// The part in a slot of the current gun (None = empty, or no part fits).
    pub fn equipped<'a>(&self, cat: AttachmentCategory, data: &'a GameData) -> Option<&'a AttachmentSpec> {
        self.parts.get(&self.weapon)?.iter().filter_map(|id| data.attachment(id)).find(|a| a.cat == cat)
    }

    /// Every equipped part of the current gun.
    pub fn equipped_all<'a>(&self, data: &'a GameData) -> Vec<&'a AttachmentSpec> {
        AttachmentCategory::ALL.iter().filter_map(|c| self.equipped(*c, data)).collect()
    }

    /// Equip `id` in its slot, or empty the slot (`None`; only optional slots can be empty).
    pub fn set_part(&mut self, cat: AttachmentCategory, id: Option<&str>, data: &GameData) {
        let list = self.parts.entry(self.weapon.clone()).or_default();
        list.retain(|p| data.attachment(p).is_none_or(|a| a.cat != cat));
        if let Some(id) = id
            && data.attachment(id).is_some_and(|a| a.cat == cat && a.fits.contains(&self.weapon))
        {
            list.push(id.to_string());
        }
        let normalized = normalize_parts(data, &self.weapon, Some(list));
        *list = normalized;
    }

    /// R on a slot: back to the gun's default part (or empty for an optional slot without one).
    pub fn reset_part(&mut self, cat: AttachmentCategory, data: &GameData) {
        let def = default_part(data, &self.weapon, cat).map(|a| a.id.clone());
        self.set_part(cat, def.as_deref(), data);
    }

    /// Switch the gun. Its attachments come back as it had them last (or its defaults); magazines it
    /// cannot load turn to STANDARD. Returns the slots (0-based) that changed, for the warning flash.
    pub fn switch_weapon(&mut self, id: &str, data: &GameData) -> Vec<usize> {
        let Some(spec) = data.weapon(id) else { return Vec::new() };
        self.weapon = id.to_string();
        if !self.parts.contains_key(id) {
            self.parts.insert(id.to_string(), normalize_parts(data, id, None));
        }
        let mut changed = Vec::new();
        for (i, m) in self.mags.iter_mut().enumerate() {
            if !ammo_ok(data, spec, *m) {
                *m = AmmoChoice::STANDARD;
                changed.push(i);
            }
        }
        changed
    }

    // ------------------------------------------------------------------------------------------ magazines

    /// Load `slot` (0-based) with `ammo`. The first empty slot adds a magazine; slots past it do nothing.
    pub fn set_mag(&mut self, slot: usize, ammo: AmmoChoice) -> bool {
        if slot < self.mags.len() {
            self.mags[slot] = ammo;
            true
        } else if slot == self.mags.len() && slot < MAX_MAGS {
            self.mags.push(ammo);
            true
        } else {
            false
        }
    }

    /// Remove the last magazine (only the last can go, so the list never has a gap; slot 1 always stays).
    pub fn remove_last_mag(&mut self) -> bool {
        if self.mags.len() > 1 {
            self.mags.pop();
            true
        } else {
            false
        }
    }

    /// Swap two loaded magazines' ammo (the slot numbers stay with the positions).
    pub fn swap_mags(&mut self, a: usize, b: usize) -> bool {
        if a != b && a < self.mags.len() && b < self.mags.len() {
            self.mags.swap(a, b);
            true
        } else {
            false
        }
    }

    /// The slot that shows "+ ADD MAG" (None with six magazines).
    pub fn add_slot(&self) -> Option<usize> {
        (self.mags.len() < MAX_MAGS).then_some(self.mags.len())
    }

    /// Ammo rows of the picker for this gun: type x tier, players' ammo only, in data order.
    pub fn ammo_options(&self, data: &GameData) -> Vec<AmmoChoice> {
        let spec = self.spec(data);
        let mut out = Vec::new();
        for (kind, ty) in &data.ammo.types {
            for tier in 1..=ty.tiers.len() as u8 {
                let c = AmmoChoice { kind: *kind, tier };
                if ammo_ok(data, spec, c) {
                    out.push(c);
                }
            }
        }
        // Standard first, then the rest in data order (BTreeMap order puts Standard first already).
        out.sort_by_key(|c| (c.kind != AmmoKind::Standard, kind_order(c.kind), c.tier));
        out
    }

    // ------------------------------------------------------------------------------------------ halo

    pub fn set_core(&mut self, core: Core) {
        self.halo.core = core;
    }

    /// Check or uncheck an arc: off sets it to 0, on brings back its last tier (T1 the first time).
    pub fn toggle_arc(&mut self, z: Zone, caps: ZoneTable<u8>) {
        if self.halo.tiers[z] > 0 {
            self.last_tiers[z] = self.halo.tiers[z];
            self.halo.tiers[z] = 0;
        } else {
            self.halo.tiers[z] = self.last_tiers[z].clamp(1, caps[z].max(1)).min(caps[z]);
        }
    }

    /// Set one arc's tier (clamped to its cap); returns false when the tier is above the cap.
    pub fn set_tier(&mut self, z: Zone, tier: u8, caps: ZoneTable<u8>) -> bool {
        if tier > caps[z] {
            return false;
        }
        self.halo.tiers[z] = tier;
        if tier > 0 {
            self.last_tiers[z] = tier;
        }
        true
    }

    /// Shift+click: every covered arc to `tier`, each clamped to its cap.
    pub fn set_tier_all(&mut self, tier: u8, caps: ZoneTable<u8>) {
        for z in Zone::ALL {
            if self.halo.tiers[z] > 0 {
                let t = tier.min(caps[z]).max(1);
                self.halo.tiers[z] = t;
                self.last_tiers[z] = t;
            }
        }
    }

    // ------------------------------------------------------------------------------------------ budget

    pub fn gear(&self, data: &GameData) -> GearCost {
        gear_cost(data, self.spec(data), &self.halo, &self.mags)
    }

    /// What keeps CONFIRM off (empty = the build is valid). `budget` None = no limit.
    pub fn problems(&self, data: &GameData, budget: Option<u32>) -> Vec<Problem> {
        let mut out = Vec::new();
        let spec = self.spec(data);
        if self.mags.is_empty() {
            out.push(Problem::NoMag);
        }
        if self.mags.iter().any(|m| !ammo_ok(data, spec, *m)) {
            out.push(Problem::Ammo);
        }
        if !self.halo.within_caps(data.armor.loadout_tier_caps) {
            out.push(Problem::TierCap);
        }
        let used = self.gear(data).total();
        if let Some(budget) = budget
            && used > budget
        {
            out.push(Problem::OverBudget { used, budget });
        }
        out
    }
}

fn kind_order(k: AmmoKind) -> u8 {
    match k {
        AmmoKind::Standard => 0,
        AmmoKind::ArmorPiercing => 1,
        AmmoKind::Rip => 2,
        AmmoKind::Slug => 3,
        AmmoKind::Shrapnel => 4,
    }
}

/// A player may load this ammo in this gun.
pub fn ammo_ok(data: &GameData, spec: &WeaponSpec, c: AmmoChoice) -> bool {
    data.ammo_for(spec, c).is_some_and(|a| a.player_loadout)
}

/// Parts of a category that fit a gun, in data order.
pub fn parts_for<'a>(data: &'a GameData, weapon: &str, cat: AttachmentCategory) -> Vec<&'a AttachmentSpec> {
    data.attachments.attachments.iter().filter(|a| a.cat == cat && a.fits.iter().any(|f| f == weapon)).collect()
}

/// The part a slot resets to: the gun's default, else (required slots) the first part that fits.
pub fn default_part<'a>(data: &'a GameData, weapon: &str, cat: AttachmentCategory) -> Option<&'a AttachmentSpec> {
    let parts = parts_for(data, weapon, cat);
    parts
        .iter()
        .find(|a| a.default_for.iter().any(|w| w == weapon))
        .copied()
        .or_else(|| if data.attachments.is_optional(cat) { None } else { parts.first().copied() })
}

/// A clean attachment list for a gun: parts that fit, one per slot, and a part in every required slot
/// (`None` = the gun's defaults).
pub fn normalize_parts(data: &GameData, weapon: &str, wanted: Option<&[String]>) -> Vec<String> {
    let mut out: Vec<String> = Vec::new();
    let mut taken: Vec<AttachmentCategory> = Vec::new();
    if let Some(list) = wanted {
        for id in list {
            if let Some(a) = data.attachment(id)
                && a.fits.iter().any(|f| f == weapon)
                && !taken.contains(&a.cat)
            {
                taken.push(a.cat);
                out.push(a.id.clone());
            }
        }
    }
    for cat in AttachmentCategory::ALL {
        if taken.contains(&cat) {
            continue;
        }
        // Optional slots stay empty when a list was given (NONE was picked); defaults otherwise.
        if wanted.is_some() && data.attachments.is_optional(cat) {
            continue;
        }
        if let Some(a) = default_part(data, weapon, cat) {
            out.push(a.id.clone());
        }
    }
    // Slot order, so lists compare and save the same way every time.
    out.sort_by_key(|id| data.attachment(id).map(|a| a.cat));
    out
}

// ---------------------------------------------------------------------------------------------- stats

/// The weapon numbers the stats panel shows.
#[derive(Debug, Clone, PartialEq)]
pub struct WeaponStats {
    pub ads_s: f32,
    pub rpm: f32,
    /// 100 = the stock pattern.
    pub recoil_v: f32,
    pub recoil_h: f32,
    /// Move speed with the gun in hand, % of base.
    pub mobility: f32,
    pub reload_s: f32,
    /// Largest distance that still deals full damage.
    pub range_m: f32,
    pub mag: u16,
    // Not shown as rows, but used for the attachment list's deltas.
    pub sway: f32,
    pub hip_spread: f32,
    pub sprint_to_fire_s: f32,
    pub ads_move: f32,
    pub zoom: Option<Zoom>,
}

/// Stats of a gun with a set of parts.
pub fn weapon_stats(data: &GameData, spec: &WeaponSpec, parts: &[&AttachmentSpec]) -> WeaponStats {
    let m = vetf_sim::data::ModifierTotals::combine(parts.iter().copied());
    let range_m = spec
        .falloff
        .iter()
        .filter(|(_, dmg)| *dmg >= spec.falloff.first().map_or(0.0, |f| f.1))
        .map(|(d, _)| *d)
        .fold(0.0_f32, f32::max);
    let mag = parts
        .iter()
        .find(|a| a.cat == AttachmentCategory::Mag)
        .and_then(|a| a.capacity)
        .or_else(|| data.attachment(&spec.mag_default).and_then(|a| a.capacity))
        .unwrap_or(0);
    WeaponStats {
        ads_s: spec.ads_s * m.ads_time,
        rpm: spec.rpm,
        recoil_v: 100.0 * m.recoil_v,
        recoil_h: 100.0 * m.recoil_h,
        mobility: 100.0 * spec.move_mult_held * m.move_mult,
        reload_s: spec.reload_tactical_s * m.reload,
        range_m,
        mag,
        sway: m.sway,
        hip_spread: m.hip_spread,
        sprint_to_fire_s: spec.sprint_to_fire_s * m.sprint_to_fire,
        ads_move: m.ads_move,
        zoom: parts.iter().find(|a| a.cat == AttachmentCategory::Optic).and_then(|a| a.zoom.clone()),
    }
}

/// The current parts with one slot replaced (`None` = that slot empty).
pub fn parts_with<'a>(
    current: &[&'a AttachmentSpec],
    cat: AttachmentCategory,
    part: Option<&'a AttachmentSpec>,
) -> Vec<&'a AttachmentSpec> {
    let mut v: Vec<&AttachmentSpec> = current.iter().copied().filter(|a| a.cat != cat).collect();
    v.extend(part);
    v
}

#[cfg(test)]
mod tests {
    use super::*;

    fn draft() -> (GameData, Draft) {
        let d = GameData::embedded();
        let c = crate::config::loadout_choice(&crate::loadout::tests::plain_cli(), &d);
        let draft = Draft::from_choice(&c, &BTreeMap::new(), &d);
        (d, draft)
    }

    const AP2: AmmoChoice = AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 };
    const RIP1: AmmoChoice = AmmoChoice { kind: AmmoKind::Rip, tier: 1 };

    #[test]
    fn the_default_draft_round_trips_to_a_choice() {
        let (d, dr) = draft();
        assert_eq!(dr.weapon, "ar7_mako");
        assert_eq!(dr.mags.len(), 4);
        let c = dr.choice();
        assert_eq!(c.attachments, vec!["optic_holo", "mako_stock_standard", "mag_30"]);
        assert_eq!(Draft::from_choice(&c, &dr.parts, &d), dr);
        assert!(dr.problems(&d, Some(d.rules.tdm.gear_budget)).is_empty());
    }

    #[test]
    fn magazines_stay_contiguous() {
        let (_, mut dr) = draft();
        assert_eq!(dr.add_slot(), Some(4));
        assert!(!dr.set_mag(5, AP2), "slot 6 is not the first empty one");
        assert!(dr.set_mag(4, AP2));
        assert!(dr.set_mag(5, AP2));
        assert_eq!(dr.add_slot(), None, "six is the most");
        assert!(!dr.set_mag(6, AP2));
        assert!(dr.swap_mags(0, 5));
        assert_eq!(dr.mags[0], AP2);
        assert_eq!(dr.mags[5], AmmoChoice::STANDARD);
        assert!(!dr.swap_mags(0, 6));
        for _ in 0..5 {
            assert!(dr.remove_last_mag());
        }
        assert_eq!(dr.mags, vec![AP2]);
        assert!(!dr.remove_last_mag(), "slot 1 always holds a magazine");
    }

    #[test]
    fn switching_guns_keeps_parts_per_gun_and_falls_back_on_ammo() {
        let (d, mut dr) = draft();
        dr.set_part(AttachmentCategory::Under, Some("grip_angled"), &d);
        // The picker only offers what the gun loads; a stale RIP mag from an SMG preset is cleaned on open.
        dr.mags[1] = RIP1;
        assert_eq!(dr.problems(&d, None), vec![Problem::Ammo]);
        let changed = dr.switch_weapon("sk9_skink", &d);
        assert_eq!(changed, Vec::<usize>::new(), "the SMG loads RIP");
        dr.set_mag(2, RIP1);
        let changed = dr.switch_weapon("ar7_mako", &d);
        assert_eq!(changed, vec![1, 2], "a rifle cannot load RIP");
        assert_eq!(dr.mags[1], AmmoChoice::STANDARD);
        assert_eq!(dr.equipped(AttachmentCategory::Under, &d).map(|a| a.id.as_str()), Some("grip_angled"));
        dr.switch_weapon("vk50_warden", &d);
        assert_eq!(dr.equipped(AttachmentCategory::Optic, &d).map(|a| a.id.as_str()), Some("optic_sniper"));
        assert!(dr.equipped(AttachmentCategory::Shield, &d).is_none());
        assert!(parts_for(&d, "vk50_warden", AttachmentCategory::Shield).is_empty(), "the slot is disabled");
    }

    #[test]
    fn slots_reset_to_the_default_and_optional_slots_can_be_empty() {
        let (d, mut dr) = draft();
        dr.set_part(AttachmentCategory::Optic, Some("optic_3x"), &d);
        dr.set_part(AttachmentCategory::Under, Some("ugl_launcher"), &d);
        dr.set_part(AttachmentCategory::Under, None, &d);
        assert!(dr.equipped(AttachmentCategory::Under, &d).is_none());
        dr.set_part(AttachmentCategory::Optic, None, &d);
        assert_eq!(
            dr.equipped(AttachmentCategory::Optic, &d).map(|a| a.id.as_str()),
            Some("optic_holo"),
            "a required slot cannot be emptied: it falls back to the default"
        );
        dr.set_part(AttachmentCategory::Stock, Some("bipod"), &d);
        assert_eq!(dr.equipped(AttachmentCategory::Stock, &d).map(|a| a.id.as_str()), Some("mako_stock_standard"));
        dr.set_part(AttachmentCategory::Optic, Some("optic_3x"), &d);
        dr.reset_part(AttachmentCategory::Optic, &d);
        assert_eq!(dr.equipped(AttachmentCategory::Optic, &d).map(|a| a.id.as_str()), Some("optic_holo"));
    }

    #[test]
    fn ammo_rows_are_what_the_gun_can_load() {
        let (d, mut dr) = draft();
        let names = |dr: &Draft| dr.ammo_options(&d).iter().map(|c| d.ammo.long_name(*c).unwrap()).collect::<Vec<_>>();
        assert_eq!(names(&dr), ["STANDARD", "AP I", "AP II", "AP III"]);
        dr.switch_weapon("sk9_skink", &d);
        assert_eq!(names(&dr), ["STANDARD", "AP I", "AP II", "AP III", "RIP I", "RIP II", "RIP III"]);
    }

    #[test]
    fn arcs_toggle_and_respect_caps() {
        let (d, mut dr) = draft();
        let caps = d.armor.loadout_tier_caps;
        assert_eq!(dr.halo.tiers.head, 2);
        dr.toggle_arc(Zone::Head, caps);
        assert_eq!(dr.halo.tiers.head, 0);
        dr.toggle_arc(Zone::Head, caps);
        assert_eq!(dr.halo.tiers.head, 2, "a re-checked arc gets its last tier back");
        dr.toggle_arc(Zone::Legs, caps);
        assert_eq!(dr.halo.tiers.legs, 1, "T1 the first time");
        assert!(!dr.set_tier(Zone::Legs, 3, caps), "legs cap at T2");
        assert!(dr.set_tier(Zone::Legs, 2, caps));
        dr.set_tier_all(4, caps);
        assert_eq!(dr.halo.tiers, ZoneTable { head: 4, torso: 4, arms: 0, legs: 2 });
        let budget = Some(d.rules.tdm.gear_budget);
        assert!(dr.problems(&d, budget).is_empty(), "10 points fit");
        dr.set_mag(0, AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 });
        assert!(matches!(dr.problems(&d, budget).as_slice(), [Problem::OverBudget { used: 16, .. }]));
        assert!(dr.problems(&d, None).is_empty(), "the gun range has no limit");
        dr.halo.tiers.legs = 4;
        assert!(dr.problems(&d, None).contains(&Problem::TierCap));
    }

    #[test]
    fn stats_follow_the_data() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let def: Vec<_> =
            ["optic_holo", "mako_stock_standard", "mag_30"].iter().map(|i| d.attachment(i).unwrap()).collect();
        let s = weapon_stats(&d, mako, &def);
        assert!((s.ads_s - 0.22).abs() < 1e-5);
        assert_eq!((s.rpm, s.range_m, s.mag), (720.0, 25.0, 30));
        assert!((s.recoil_v - 100.0).abs() < 1e-4 && (s.mobility - 100.0).abs() < 1e-4);
        assert!((s.reload_s - 2.1).abs() < 1e-5);
        let grip = parts_with(&def, AttachmentCategory::Under, d.attachment("grip_angled"));
        let g = weapon_stats(&d, mako, &grip);
        assert!((g.ads_s - 0.22 * 0.92).abs() < 1e-5);
        let drum = parts_with(&def, AttachmentCategory::Mag, d.attachment("mag_drum60"));
        assert_eq!(weapon_stats(&d, mako, &drum).mag, 60);
        assert_eq!(weapon_stats(&d, d.weapon("vk50_warden").unwrap(), &[]).range_m, 60.0);
        assert_eq!(weapon_stats(&d, d.weapon("sk9_skink").unwrap(), &[]).range_m, 10.0);
    }
}
