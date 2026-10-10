//! The loadout being edited on the Loadout screen, its rules and its derived numbers. Engine-free, so it
//! is tested on its own: attachments per slot, the contiguous magazine list (1..=6, slot 1 in the gun,
//! slot index = reload-wheel position), the custom halo, the points and the weapon stats.
//!
//! Team deathmatch and free-for-all sell picks instead ([`Draft::fixed`], `rules.ron` `deathmatch_loadout`):
//! the gun and its parts (the magazine type among them), ONE armor tier and ONE ammo type for all six
//! magazines. The draft is shaped to them when it opens, exactly as the host shapes what it receives, so a
//! loadout saved by an older build opens as its nearest picks.

use std::collections::BTreeMap;
use vetf_net::LoadoutChoice;
use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::ZoneTable;
use vetf_sim::data::{
    AmmoChoice, AmmoKind, AttachmentCategory, AttachmentSpec, Core, DeathmatchLoadout, WeaponSpec, Zoom,
};
use vetf_sim::gear::{GearCost, HaloChoice, gear_cost, kit_cost};
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
    /// The picks and points of team deathmatch and free-for-all: one armor tier on the one halo core, and
    /// six magazines with one ammo type. None in the gun range (any core, a tier per arc, ammo per magazine).
    pub fixed: Option<DeathmatchLoadout>,
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
    /// Open a loadout for editing (unknown, hidden or misfit ids are cleaned up; `remembered` = other guns' sets),
    /// shaped to the picks of team deathmatch and free-for-all when `fixed` ([`LoadoutChoice::shaped`]).
    pub fn from_choice(
        c: &LoadoutChoice,
        remembered: &BTreeMap<String, Vec<String>>,
        data: &GameData,
        fixed: Option<DeathmatchLoadout>,
    ) -> Self {
        let c = &c.shaped(fixed.as_ref());
        // An unknown or hidden gun (the SK-9 Skink, out for now) opens as the default gun.
        let weapon = data.offered_weapon_or_default(&c.weapon).to_string();
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
        Self { agent: c.agent.clone(), weapon, parts, mags, halo, last_tiers, fixed }
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

    /// Switch the gun (not to a hidden one). Its attachments come back as it had them last (or its defaults); magazines it
    /// cannot load turn to STANDARD. Returns the slots (0-based) that changed, for the warning flash.
    pub fn switch_weapon(&mut self, id: &str, data: &GameData) -> Vec<usize> {
        let Some(spec) = data.offered_weapon(id) else { return Vec::new() };
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

    /// The one ammo type of a team deathmatch or free-for-all draft (every magazine's; slot 1's in the gun
    /// range).
    pub fn ammo(&self) -> AmmoChoice {
        self.mags.first().copied().unwrap_or(AmmoChoice::STANDARD)
    }

    /// Load every magazine with `ammo` (the one ammo type of team deathmatch and free-for-all). False when the
    /// gun cannot load it.
    pub fn set_ammo(&mut self, ammo: AmmoChoice, data: &GameData) -> bool {
        if !ammo_ok(data, self.spec(data), ammo) {
            return false;
        }
        self.mags.iter_mut().for_each(|m| *m = ammo);
        true
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

    // ------------------------------------------------------------------------------------------ picks

    /// The armor tier (1-based) of a team deathmatch or free-for-all draft: the tier its halo is (a draft
    /// always holds one), else the one it makes. None in the gun range.
    pub fn armor_tier(&self) -> Option<u8> {
        let kit = self.fixed.as_ref()?;
        Some(kit.tier_of(self.halo.tiers).unwrap_or_else(|| kit.tier_for(self.halo.tiers)))
    }

    /// Wear armor tier `tier` (team deathmatch, free-for-all). False in the gun range or for a tier that
    /// does not exist.
    pub fn set_armor_tier(&mut self, tier: u8) -> bool {
        let Some(kit) = &self.fixed else { return false };
        if kit.armor_tier(tier).is_none() {
            return false;
        }
        self.halo = HaloChoice::of_tier(kit, tier);
        true
    }

    /// The magazine type: the gun's part in its magazine slot.
    pub fn mag_type<'a>(&self, data: &'a GameData) -> Option<&'a AttachmentSpec> {
        self.equipped(AttachmentCategory::Mag, data)
    }

    /// The magazine types this gun takes, in data order (the standard one first): the MAG slot's popover.
    #[cfg(test)]
    pub fn mag_options<'a>(&self, data: &'a GameData) -> Vec<&'a AttachmentSpec> {
        parts_for(data, &self.weapon, AttachmentCategory::Mag)
    }

    /// Team deathmatch and free-for-all: the points of part `id` (None: an empty slot) in slot `cat`. A
    /// magazine type (`mag_points`) and an optic (`optic_points`: the variable 1-3x) may have a price; every
    /// other part, and an empty slot, is free. None in the gun range (parts are not priced there).
    pub fn part_points(&self, cat: AttachmentCategory, id: Option<&str>) -> Option<u32> {
        let kit = self.fixed.as_ref()?;
        Some(id.map_or(0, |id| kit.part_points(cat, id)))
    }

    /// The points of what slot `cat` holds now (what its card shows; None in the gun range).
    pub fn slot_points(&self, cat: AttachmentCategory, data: &GameData) -> Option<u32> {
        self.part_points(cat, self.equipped(cat, data).map(|a| a.id.as_str()))
    }

    // ------------------------------------------------------------------------------------------ budget

    /// The points. Team deathmatch and free-for-all: the armor tier, the one ammo type once, the magazine type
    /// and the optic; the gun range: the arc tiers and every magazine's ammo.
    pub fn gear(&self, data: &GameData) -> GearCost {
        let spec = self.spec(data);
        match (&self.fixed, self.armor_tier()) {
            (Some(kit), Some(tier)) => {
                let mag = self.mag_type(data).map_or(spec.mag_default.as_str(), |m| m.id.as_str());
                let optic = self.equipped(AttachmentCategory::Optic, data).map(|o| o.id.as_str());
                kit_cost(data, kit, spec, tier, self.ammo(), mag, optic)
            }
            _ => gear_cost(data, spec, &self.halo, &self.mags),
        }
    }

    /// The points with one pick changed (`f` changes a copy): what a card shows before it is picked.
    pub fn gear_with(&self, data: &GameData, f: impl FnOnce(&mut Draft)) -> GearCost {
        let mut d = self.clone();
        f(&mut d);
        d.gear(data)
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

/// Does a pick push the loadout over the points total (`budget`; None: no limit): `with` its points instead of
/// `now`? Over, or further over: a cheaper pick that still leaves the loadout over is not what pushes it over.
pub fn pushes_over(budget: Option<u32>, now: u32, with: u32) -> bool {
    budget.is_some_and(|b| with > b && with > now)
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
        zoom: parts.iter().find(|a| a.cat == AttachmentCategory::Optic).and_then(|a| a.zoom),
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

    /// The default loadout as the gun range edits it (ammo per magazine, any core).
    fn draft() -> (GameData, Draft) {
        let d = GameData::embedded();
        let c = crate::config::loadout_choice(&crate::loadout::tests::plain_cli(), &d);
        let draft = Draft::from_choice(&c, &BTreeMap::new(), &d, None);
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
        assert_eq!(Draft::from_choice(&c, &dr.parts, &d, None), dr);
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

    /// The SK-9 Skink is out for now: a saved loadout with it opens on the Mako (its parts, ammo it loads),
    /// and the screen cannot switch to it.
    #[test]
    fn a_hidden_gun_opens_as_the_mako_and_cannot_be_picked() {
        let d = GameData::embedded();
        let rip3 = AmmoChoice { kind: AmmoKind::Rip, tier: 3 };
        let old = LoadoutChoice {
            weapon: "sk9_skink".into(),
            mags: vec![AP2, rip3],
            attachments: vec!["optic_reddot".into(), "skink_mag_60".into()],
            halo: crate::config::halo_from_armor("arm_mender_scout", &d),
            agent: "kestrel".into(),
        };
        for fixed in [None, d.rules.fixed_loadout(vetf_net::MatchMode::Tdm).cloned()] {
            let dr = Draft::from_choice(&old, &BTreeMap::new(), &d, fixed.clone());
            assert_eq!(dr.weapon, "ar7_mako", "{fixed:?}");
            assert!(dr.equipped_all(&d).iter().all(|a| a.fits.contains(&dr.weapon)), "{fixed:?}: Mako parts");
            assert!(dr.mags.iter().all(|m| *m != rip3), "{fixed:?}: no RIP in a rifle");
            assert_eq!(dr.mag_type(&d).map(|m| m.id.as_str()), Some("mag_30"), "{fixed:?}");
            assert_eq!(dr.choice().weapon, "ar7_mako", "{fixed:?}: what goes to the host");
        }
        let (d, mut dr) = draft();
        assert_eq!(dr.switch_weapon("sk9_skink", &d), Vec::<usize>::new());
        assert_eq!(dr.weapon, "ar7_mako", "no switch to a hidden gun");
    }

    #[test]
    fn switching_guns_keeps_parts_per_gun_and_falls_back_on_ammo() {
        let (_, mut dr) = draft();
        let d = crate::loadout::tests::data_with_skink();
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

    /// The fold-out projector is offered in the optic slot of both modelled guns and can be equipped.
    #[test]
    fn the_projector_is_a_pickable_optic() {
        let (d, mut dr) = draft();
        for gun in ["ar7_mako", "vk50_warden"] {
            let optics: Vec<&str> =
                parts_for(&d, gun, AttachmentCategory::Optic).iter().map(|a| a.id.as_str()).collect();
            assert!(optics.contains(&"optic_projector"), "{gun}: {optics:?}");
        }
        dr.set_part(AttachmentCategory::Optic, Some("optic_projector"), &d);
        assert_eq!(dr.equipped(AttachmentCategory::Optic, &d).map(|a| a.id.as_str()), Some("optic_projector"));
    }

    #[test]
    fn ammo_rows_are_what_the_gun_can_load() {
        let (_, mut dr) = draft();
        let d = crate::loadout::tests::data_with_skink();
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
        let budget = Some(10);
        assert!(dr.problems(&d, budget).is_empty(), "10 points fit a budget of 10");
        dr.set_mag(0, AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 3 });
        assert!(matches!(dr.problems(&d, budget).as_slice(), [Problem::OverBudget { used: 14, .. }]));
        assert!(dr.problems(&d, None).is_empty(), "the gun range has no limit");
        dr.halo.tiers.legs = 4;
        assert!(dr.problems(&d, None).contains(&Problem::TierCap));
    }

    /// Team deathmatch and free-for-all: whatever the preset held (a Volt core, a halo that is no armor tier,
    /// mixed ammo, fewer magazines), the draft opens as the picks the mode sells: an armor tier, six
    /// magazines of one ammo type, the gun's magazine type. Each pick has its points.
    #[test]
    fn a_deathmatch_draft_is_an_armor_tier_a_magazine_type_and_one_ammo_type() {
        let d = crate::loadout::tests::data_with_skink();
        let ap = |tier| AmmoChoice { kind: AmmoKind::ArmorPiercing, tier };
        let old = LoadoutChoice {
            weapon: "ar7_mako".into(),
            mags: vec![AmmoChoice::STANDARD, ap(3), ap(3), ap(1)],
            attachments: vec!["mag_45".into()],
            halo: HaloChoice { core: Core::Volt, tiers: ZoneTable { head: 2, torso: 3, arms: 1, legs: 0 } },
            agent: "solace".into(),
        };
        for mode in [vetf_net::MatchMode::Tdm, vetf_net::MatchMode::Ffa] {
            let kit = d.rules.fixed_loadout(mode).cloned();
            let budget = Some(d.rules.deathmatch(mode).gear_budget);
            let mut dr = Draft::from_choice(&old, &BTreeMap::new(), &d, kit.clone());
            let kit = kit.unwrap();
            assert_eq!(dr.mags, vec![AmmoChoice::STANDARD; 6], "slot 1's ammo in six magazines");
            assert_eq!(dr.armor_tier(), Some(3), "torso 3 makes T3");
            assert_eq!(dr.halo, HaloChoice::of_tier(&kit, 3), "on the one halo core");
            assert_eq!(dr.mag_type(&d).map(|m| m.id.as_str()), Some("mag_45"));
            assert_eq!(dr.gear(&d), GearCost { halo: 3, ammo: 0, mags: 1, optic: 0 });
            // the picks
            assert!(dr.set_armor_tier(4));
            assert_eq!(dr.halo.tiers, d.armor.loadout_tier_caps);
            assert!(!dr.set_armor_tier(5));
            // NO HALO (DIRECTION_LOG 18): the first pick, free, and it stays no halo through the host's shaping
            assert!(dr.set_armor_tier(0));
            assert_eq!((dr.armor_tier(), dr.halo.tiers, dr.gear(&d).halo), (Some(0), ZoneTable::splat(0), 0));
            assert!(!dr.halo.is_lit());
            assert_eq!(dr.choice().for_mode(&d, mode).halo.tiers, ZoneTable::splat(0));
            let again = Draft::from_choice(&dr.choice(), &BTreeMap::new(), &d, Some(kit.clone()));
            assert_eq!(again.armor_tier(), Some(0), "a saved NO HALO opens as NO HALO");
            assert!(dr.set_armor_tier(4));
            assert!(dr.set_ammo(ap(2), &d));
            assert!(dr.mags.iter().all(|m| *m == ap(2)) && dr.ammo() == ap(2));
            assert!(!dr.set_ammo(AmmoChoice { kind: AmmoKind::Rip, tier: 1 }, &d), "a rifle cannot load RIP");
            dr.set_part(AttachmentCategory::Mag, Some("mag_drum60"), &d);
            let opts: Vec<&str> = dr.mag_options(&d).iter().map(|m| m.id.as_str()).collect();
            assert_eq!(opts, ["mag_30", "mag_45", "mag_drum60"]);
            assert_eq!(dr.gear(&d), GearCost { halo: 5, ammo: 2, mags: 2, optic: 0 }, "AP II paid once");
            assert!(matches!(dr.problems(&d, budget).as_slice(), [Problem::OverBudget { used: 9, budget: 8 }]));
            let with_ext = dr.gear_with(&d, |x| x.set_part(AttachmentCategory::Mag, Some("mag_45"), &d));
            assert_eq!(with_ext.total(), 8, "an extended magazine instead fits");
            assert_eq!(dr.gear(&d).total(), 9, "gear_with leaves the draft alone");
            dr.set_part(AttachmentCategory::Mag, Some("mag_45"), &d);
            assert!(dr.problems(&d, budget).is_empty());
            // the choice it confirms is what the host builds from it
            assert_eq!(dr.choice(), dr.choice().for_mode(&d, mode));
            // a gun that cannot load the ammo falls back to standard in every magazine
            dr.set_ammo(ap(3), &d);
            dr.switch_weapon("sk9_skink", &d);
            assert!(dr.mags.iter().all(|m| *m == ap(3)), "the SMG loads AP too");
            assert_eq!(dr.mag_type(&d).map(|m| m.id.as_str()), Some("skink_mag_40"), "the SMG's own magazine");
            dr.set_ammo(AmmoChoice { kind: AmmoKind::Rip, tier: 2 }, &d);
            let changed = dr.switch_weapon("ar7_mako", &d);
            assert_eq!(changed.len(), 6);
            assert!(dr.mags.iter().all(|m| *m == AmmoChoice::STANDARD));
            assert_eq!(dr.mag_type(&d).map(|m| m.id.as_str()), Some("mag_45"), "the Mako's magazine comes back");
        }
        // the gun range has no armor tier
        let mut range = Draft::from_choice(&old, &BTreeMap::new(), &d, None);
        assert_eq!(range.armor_tier(), None);
        assert!(!range.set_armor_tier(2));
        assert_eq!(range.gear(&d).mags, 0);
    }

    /// Every attachment card shows the points of what it holds, all the time (DIRECTION_LOG: "points should
    /// show here for whatever options selected"): the magazine type has its price, every other part and an
    /// empty slot are free, and the gun range prices no parts.
    #[test]
    fn every_slot_shows_its_points_in_a_deathmatch() {
        let d = GameData::embedded();
        let c = LoadoutChoice {
            weapon: "ar7_mako".into(),
            mags: vec![AmmoChoice::STANDARD],
            attachments: vec!["optic_holo".into(), "mag_drum60".into()],
            halo: HaloChoice { core: Core::Mender, tiers: ZoneTable::splat(1) },
            agent: "kestrel".into(),
        };
        let kit = d.rules.fixed_loadout(vetf_net::MatchMode::Tdm).cloned().unwrap();
        let mut dr = Draft::from_choice(&c, &BTreeMap::new(), &d, Some(kit.clone()));
        assert_eq!(dr.slot_points(AttachmentCategory::Mag, &d), Some(2), "the drum");
        assert_eq!(dr.slot_points(AttachmentCategory::Mag, &d), Some(dr.gear(&d).mags), "what the total counts");
        assert_eq!(dr.slot_points(AttachmentCategory::Optic, &d), Some(0), "an optic is free");
        assert_eq!(dr.slot_points(AttachmentCategory::Side, &d), Some(0), "an empty slot is free");
        // the popover's options: each magazine type at its own price
        let prices: Vec<u32> =
            dr.mag_options(&d).iter().map(|m| dr.part_points(AttachmentCategory::Mag, Some(&m.id)).unwrap()).collect();
        assert_eq!(prices, [0, 1, 2], "standard, extended, drum");
        assert_eq!(dr.part_points(AttachmentCategory::Optic, Some("optic_holo")), Some(0));
        assert_eq!(dr.part_points(AttachmentCategory::Under, None), Some(0));
        dr.set_part(AttachmentCategory::Mag, Some("mag_45"), &d);
        assert_eq!(dr.slot_points(AttachmentCategory::Mag, &d), Some(1), "follows the pick");
        // the gun range: no prices on parts
        let range = Draft::from_choice(&c, &BTreeMap::new(), &d, None);
        assert_eq!(range.slot_points(AttachmentCategory::Mag, &d), None);
        assert_eq!(range.part_points(AttachmentCategory::Mag, Some("mag_drum60")), None);
    }

    /// Item 8d: the variable 1-3x is offered in the optic slot of both guns the 3x fits, at a point where the 3x is
    /// free; the card, the popover row and the total agree, and the summary splits it out.
    #[test]
    fn the_variable_optic_is_a_priced_pick() {
        let d = GameData::embedded();
        let kit = d.rules.fixed_loadout(vetf_net::MatchMode::Tdm).cloned().unwrap();
        for gun in ["ar7_mako", "vk50_warden"] {
            let c = LoadoutChoice {
                weapon: gun.into(),
                mags: vec![AmmoChoice::STANDARD],
                attachments: vec![],
                halo: HaloChoice { core: Core::Mender, tiers: ZoneTable::splat(1) },
                agent: "kestrel".into(),
            };
            let mut dr = Draft::from_choice(&c, &BTreeMap::new(), &d, Some(kit.clone()));
            let optics: Vec<&str> =
                parts_for(&d, gun, AttachmentCategory::Optic).iter().map(|a| a.id.as_str()).collect();
            assert!(optics.contains(&"optic_1_3x") && optics.contains(&"optic_3x"), "{gun}: {optics:?}");
            assert_eq!(dr.part_points(AttachmentCategory::Optic, Some("optic_1_3x")), Some(1));
            assert_eq!(dr.part_points(AttachmentCategory::Optic, Some("optic_3x")), Some(0));
            let before = dr.gear(&d).total();
            let with = dr.gear_with(&d, |x| x.set_part(AttachmentCategory::Optic, Some("optic_1_3x"), &d));
            assert_eq!((with.total(), with.optic), (before + 1, 1), "{gun}: what picking it would cost");
            dr.set_part(AttachmentCategory::Optic, Some("optic_1_3x"), &d);
            assert_eq!(dr.equipped(AttachmentCategory::Optic, &d).map(|a| a.id.as_str()), Some("optic_1_3x"));
            assert_eq!(dr.slot_points(AttachmentCategory::Optic, &d), Some(1), "{gun}: the card");
            assert_eq!(dr.gear(&d).optic, 1);
            dr.set_part(AttachmentCategory::Optic, Some("optic_3x"), &d);
            assert_eq!((dr.slot_points(AttachmentCategory::Optic, &d), dr.gear(&d).total()), (Some(0), before));
        }
        assert!(!parts_for(&d, "sk9_skink", AttachmentCategory::Optic).iter().any(|a| a.id == "optic_1_3x"));
        // the summary (the match menu's points line) and the host agree with the screen
        let c = LoadoutChoice {
            weapon: "vk50_warden".into(),
            mags: vec![AmmoChoice::STANDARD],
            attachments: vec!["optic_1_3x".into()],
            halo: HaloChoice { core: Core::Mender, tiers: ZoneTable::splat(1) },
            agent: "kestrel".into(),
        };
        let s = super::super::summary(&c, &d, vetf_net::MatchMode::Tdm);
        assert_eq!((s.optic_cost, s.halo_cost(), s.gear_cost), (1, 1, 2));
    }

    #[test]
    fn a_pick_pushes_over_only_when_it_adds_to_an_overrun() {
        assert!(pushes_over(Some(8), 6, 9), "over");
        assert!(!pushes_over(Some(8), 6, 8), "exactly the total fits");
        assert!(pushes_over(Some(8), 9, 10), "further over");
        assert!(!pushes_over(Some(8), 11, 9), "cheaper, still over: not the culprit");
        assert!(!pushes_over(None, 0, 99), "no limit");
    }

    #[test]
    fn stats_follow_the_data() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let def: Vec<_> =
            ["optic_holo", "mako_stock_standard", "mag_30"].iter().map(|i| d.attachment(i).unwrap()).collect();
        let s = weapon_stats(&d, mako, &def);
        assert!((s.ads_s - 0.13).abs() < 1e-5);
        assert_eq!((s.rpm, s.range_m, s.mag), (720.0, 35.0, 30));
        assert!((s.recoil_v - 100.0).abs() < 1e-4 && (s.mobility - 100.0).abs() < 1e-4);
        assert!((s.reload_s - 2.1).abs() < 1e-5);
        let grip = parts_with(&def, AttachmentCategory::Under, d.attachment("grip_angled"));
        let g = weapon_stats(&d, mako, &grip);
        assert!((g.ads_s - 0.13 * 0.92).abs() < 1e-5);
        let drum = parts_with(&def, AttachmentCategory::Mag, d.attachment("mag_drum60"));
        assert_eq!(weapon_stats(&d, mako, &drum).mag, 60);
        assert_eq!(weapon_stats(&d, d.weapon("vk50_warden").unwrap(), &[]).range_m, 60.0);
        assert_eq!(weapon_stats(&d, d.weapon("sk9_skink").unwrap(), &[]).range_m, 10.0);
    }
}
