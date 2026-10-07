//! Healing items: data, the per-player kit, using one (predicted, like the weapon) and its effect (host).
//!
//! Whole-body items treat every region or every arc at once; region items treat one region, picked on a
//! second ring. Using an item lowers the gun for `use_s`; firing, aiming, reloading or sprinting cancels
//! it and keeps the item. The effect lands on the host when the use finishes.

use crate::combat::{HaloSpec, HaloState, Health};
use crate::data::Mode;
use crate::input::{Buttons, InputFrame};
use crate::weapon::secs_to_ticks;
use crate::zone::Zone;
use serde::{Deserialize, Serialize};

/// Most items a kit holds (the heal ring has room for this many).
pub const MAX_KIT: usize = 8;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ItemScope {
    /// Every region (HP) or every arc (shield) at once.
    Body,
    /// One region, picked on a second ring.
    Region,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ItemSpec {
    pub id: String,
    /// Short name for the heal ring.
    pub label: String,
    pub scope: ItemScope,
    pub use_s: f32,
    #[serde(default)]
    pub heal_hp: f32,
    #[serde(default)]
    pub stop_bleed: bool,
    #[serde(default)]
    pub shield_frac: f32,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct KitEntry {
    pub item: String,
    pub count: u8,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Kits {
    pub tdm: Vec<KitEntry>,
    pub range: Vec<KitEntry>,
}

impl Kits {
    pub fn get(&self, mode: Mode) -> &[KitEntry] {
        match mode {
            Mode::Tdm => &self.tdm,
            Mode::Range => &self.range,
        }
    }
}

/// `items.ron`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ItemsFile {
    pub use_move_mult: f32,
    pub items: Vec<ItemSpec>,
    pub kits: Kits,
}

impl ItemsFile {
    pub fn index(&self, id: &str) -> Option<usize> {
        self.items.iter().position(|i| i.id == id)
    }

    /// The kit a mode hands out, resolved to item indices (unknown ids are skipped; validation refuses
    /// them for the shipped data).
    pub fn kit(&self, mode: Mode) -> Vec<KitSlot> {
        self.kits
            .get(mode)
            .iter()
            .filter_map(|e| Some(KitSlot { item: self.index(&e.item)? as u8, count: e.count }))
            .take(MAX_KIT)
            .collect()
    }

    pub fn spec(&self, slot: &KitSlot) -> &ItemSpec {
        &self.items[slot.item as usize]
    }
}

/// One kit slot as carried: which item and how many at spawn.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct KitSlot {
    pub item: u8,
    pub count: u8,
}

// ---------------------------------------------------------------------------------------------- using

/// An item being applied.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ItemUse {
    /// Kit slot (0-based).
    pub slot: u8,
    /// The region, for region items.
    pub zone: Option<Zone>,
    pub left: u16,
    pub total: u16,
}

/// Item counts and the item in use. Predicted by the owner, authoritative on the host.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub struct ItemState {
    /// Items left per kit slot.
    pub counts: Vec<u8>,
    pub using: Option<ItemUse>,
}

/// What happened this tick.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct ItemEvents {
    pub started: Option<ItemUse>,
    pub cancelled: bool,
    /// (kit slot, region): the host applies the item's effect.
    pub finished: Option<(u8, Option<Zone>)>,
}

/// An item pick from the heal ring: kit slot 1..=8 (0 = none) and region 1..=4 in `Zone::ALL` order
/// (0 = none, for whole-body items).
pub fn decode_pick(item: u8, zone: u8) -> Option<(u8, Option<Zone>)> {
    let slot = item.checked_sub(1)?;
    let zone = match zone {
        0 => None,
        z => Some(*Zone::ALL.get(z as usize - 1)?),
    };
    Some((slot, zone))
}

/// The inverse of [`decode_pick`].
pub fn encode_pick(slot: u8, zone: Option<Zone>) -> (u8, u8) {
    (slot + 1, zone.map_or(0, |z| z.index() as u8 + 1))
}

impl ItemState {
    pub fn new(kit: &[KitSlot]) -> Self {
        Self { counts: kit.iter().map(|k| k.count).collect(), using: None }
    }

    pub fn count(&self, slot: u8) -> u8 {
        self.counts.get(slot as usize).copied().unwrap_or(0)
    }

    /// Advance one tick. `hands_free`: the gun is up and idle (not reloading, equipping or lowered).
    /// `lowered`: sprinting or mantling, which cancels a use.
    pub fn step(
        &mut self,
        items: &ItemsFile,
        kit: &[KitSlot],
        input: &InputFrame,
        hands_free: bool,
        lowered: bool,
        tick_hz: u32,
    ) -> ItemEvents {
        let mut ev = ItemEvents::default();
        let b = input.buttons;
        if let Some(u) = &mut self.using {
            let reload = b.held(Buttons::RELOAD) || input.reload_slot != 0;
            if b.held(Buttons::FIRE) || b.held(Buttons::ADS) || reload || lowered {
                self.using = None;
                ev.cancelled = true;
                return ev;
            }
            u.left = u.left.saturating_sub(1);
            if u.left == 0 {
                let (slot, zone) = (u.slot, u.zone);
                self.using = None;
                if let Some(c) = self.counts.get_mut(slot as usize) {
                    *c = c.saturating_sub(1);
                }
                ev.finished = Some((slot, zone));
            }
            return ev;
        }
        let Some((slot, zone)) = decode_pick(input.use_item, input.use_zone) else { return ev };
        let Some(k) = kit.get(slot as usize) else { return ev };
        let spec = items.spec(k);
        // A whole-body item takes no region; a region item needs one.
        let fits = (spec.scope == ItemScope::Body) == zone.is_none();
        if !fits || self.count(slot) == 0 || !hands_free || lowered {
            return ev;
        }
        let total = secs_to_ticks(spec.use_s, tick_hz).max(1);
        let u = ItemUse { slot, zone, left: total, total };
        self.using = Some(u);
        ev.started = Some(u);
        ev
    }
}

// ---------------------------------------------------------------------------------------------- effect

fn zones(spec: &ItemSpec, zone: Option<Zone>) -> Vec<Zone> {
    match (spec.scope, zone) {
        (ItemScope::Body, _) => Zone::ALL.to_vec(),
        (ItemScope::Region, Some(z)) => vec![z],
        (ItemScope::Region, None) => Vec::new(),
    }
}

/// Whether using `spec` on `zone` would change anything right now (the heal ring dims useless options).
pub fn would_help(
    spec: &ItemSpec,
    zone: Option<Zone>,
    health: &Health,
    halo: &HaloState,
    halo_spec: &HaloSpec,
) -> bool {
    if health.dead {
        return false;
    }
    zones(spec, zone).into_iter().any(|z| {
        (spec.heal_hp > 0.0 && health.hp[z] < health.max[z])
            || (spec.stop_bleed && health.bleeding.active[z] > health.bleeding.residual[z])
            || (spec.shield_frac > 0.0 && halo.shield[z] < halo_spec.capacity[z])
    })
}

/// Apply a finished item (host). Returns whether it changed anything.
pub fn apply(
    spec: &ItemSpec,
    zone: Option<Zone>,
    health: &mut Health,
    halo: &mut HaloState,
    halo_spec: &HaloSpec,
) -> bool {
    let helped = would_help(spec, zone, health, halo, halo_spec);
    if health.dead {
        return false;
    }
    for z in zones(spec, zone) {
        if spec.heal_hp > 0.0 {
            health.heal(z, spec.heal_hp);
        }
        if spec.stop_bleed {
            health.bleeding.treat(z);
        }
        if spec.shield_frac > 0.0 {
            let cap = halo_spec.capacity[z];
            halo.shield[z] = (halo.shield[z] + cap * spec.shield_frac).min(cap);
        }
    }
    helped
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::GameData;
    use crate::data::Ruleset;

    fn frame(bits: u16, item: u8, zone: u8) -> InputFrame {
        InputFrame { buttons: Buttons(bits), use_item: item, use_zone: zone, ..Default::default() }
    }

    fn slot_of(d: &GameData, mode: Mode, id: &str) -> u8 {
        d.items.kit(mode).iter().position(|k| d.items.items[k.item as usize].id == id).unwrap() as u8
    }

    #[test]
    fn team_deathmatch_only_hands_out_whole_body_items() {
        let d = GameData::embedded();
        let tdm = d.items.kit(Mode::Tdm);
        assert!(!tdm.is_empty());
        assert!(tdm.iter().all(|k| d.items.spec(k).scope == ItemScope::Body));
        assert!(!d.rules.rulesets.get(Mode::Tdm).regional_items);
        let range = d.items.kit(Mode::Range);
        assert!(range.iter().any(|k| d.items.spec(k).scope == ItemScope::Region));
        assert_eq!(d.rules.rulesets.get(Mode::Range), Ruleset::FULL);
    }

    #[test]
    fn picks_roundtrip() {
        for slot in 0..MAX_KIT as u8 {
            for zone in [None, Some(Zone::Head), Some(Zone::Legs)] {
                let (i, z) = encode_pick(slot, zone);
                assert_eq!(decode_pick(i, z), Some((slot, zone)));
            }
        }
        assert_eq!(decode_pick(0, 0), None);
        assert_eq!(decode_pick(1, 9), None);
    }

    #[test]
    fn using_takes_use_time_then_spends_one() {
        let d = GameData::embedded();
        let kit = d.items.kit(Mode::Tdm);
        let mut s = ItemState::new(&kit);
        let slot = slot_of(&d, Mode::Tdm, "trauma_kit");
        let (i, z) = encode_pick(slot, None);
        let before = s.count(slot);
        let ev = s.step(&d.items, &kit, &frame(0, i, z), true, false, 60);
        let total = ev.started.unwrap().total;
        assert_eq!(total, secs_to_ticks(4.5, 60));
        let mut done = 0;
        for t in 1..=total {
            if let Some(f) = s.step(&d.items, &kit, &frame(0, 0, 0), true, false, 60).finished {
                assert_eq!(f, (slot, None));
                done = t;
            }
        }
        assert_eq!(done, total);
        assert_eq!(s.count(slot), before - 1);
        assert!(s.using.is_none());
    }

    #[test]
    fn firing_or_sprinting_cancels_and_keeps_the_item() {
        let d = GameData::embedded();
        let kit = d.items.kit(Mode::Tdm);
        let slot = slot_of(&d, Mode::Tdm, "halo_cell");
        let (i, z) = encode_pick(slot, None);
        for (bits, lowered) in [(Buttons::FIRE, false), (Buttons::ADS, false), (Buttons::RELOAD, false), (0, true)] {
            let mut s = ItemState::new(&kit);
            let before = s.count(slot);
            s.step(&d.items, &kit, &frame(0, i, z), true, false, 60);
            for _ in 0..10 {
                s.step(&d.items, &kit, &frame(0, 0, 0), true, false, 60);
            }
            let ev = s.step(&d.items, &kit, &frame(bits, 0, 0), true, lowered, 60);
            assert!(ev.cancelled && s.using.is_none());
            assert_eq!(s.count(slot), before);
        }
    }

    #[test]
    fn region_items_need_a_region_and_body_items_refuse_one() {
        let d = GameData::embedded();
        let kit = d.items.kit(Mode::Range);
        let gauze = slot_of(&d, Mode::Range, "gauze");
        let trauma = slot_of(&d, Mode::Range, "trauma_kit");
        let mut s = ItemState::new(&kit);
        let (i, _) = encode_pick(gauze, None);
        assert!(s.step(&d.items, &kit, &frame(0, i, 0), true, false, 60).started.is_none());
        let (i, z) = encode_pick(trauma, Some(Zone::Head));
        assert!(s.step(&d.items, &kit, &frame(0, i, z), true, false, 60).started.is_none());
        let (i, z) = encode_pick(gauze, Some(Zone::Legs));
        assert!(s.step(&d.items, &kit, &frame(0, i, z), false, false, 60).started.is_none(), "hands busy");
        assert_eq!(s.step(&d.items, &kit, &frame(0, i, z), true, false, 60).started.unwrap().zone, Some(Zone::Legs));
        // nothing left: nothing starts
        let mut s = ItemState::new(&kit);
        s.counts[gauze as usize] = 0;
        assert!(s.step(&d.items, &kit, &frame(0, i, z), true, false, 60).started.is_none());
    }

    #[test]
    fn whole_body_items_treat_every_region_or_arc() {
        let d = GameData::embedded();
        let armor = d.armor.resolve_id("arm_bulwark_vanguard").unwrap();
        let spec = HaloSpec::from_armor(&armor);
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        let trauma = &d.items.items[d.items.index("trauma_kit").unwrap()];
        let cell = &d.items.items[d.items.index("halo_cell").unwrap()];
        assert!(!would_help(trauma, None, &hp, &halo, &spec), "full health");
        hp.apply(Zone::Legs, 200.0, &d.weapons.spill_to_torso);
        hp.apply(Zone::Head, 20.0, &d.weapons.spill_to_torso);
        assert!(hp.is_broken(Zone::Legs));
        assert!(apply(trauma, None, &mut hp, &mut halo, &spec));
        assert!(!hp.is_broken(Zone::Legs), "a healed limb is no longer broken");
        assert_eq!(hp.hp[Zone::Head], hp.max[Zone::Head]);
        for z in Zone::ALL {
            halo.shield[z] = 0.0;
        }
        apply(cell, None, &mut hp, &mut halo, &spec);
        assert_eq!(halo.shield, spec.capacity, "a halo cell refills every arc");
    }

    #[test]
    fn region_items_treat_one_region() {
        let d = GameData::embedded();
        let armor = d.armor.resolve_id("arm_bulwark_vanguard").unwrap();
        let spec = HaloSpec::from_armor(&armor);
        let mut halo = HaloState::full(&spec);
        let mut hp = Health::new(d.armor.zone_hp);
        let shr = d
            .ammo
            .resolve(
                crate::data::WeaponClass::AssaultRifle,
                crate::data::AmmoChoice { kind: crate::data::AmmoKind::Shrapnel, tier: 1 },
            )
            .unwrap();
        let bleed = shr.bleed.unwrap();
        hp.bleeding.add_stack(Zone::Arms, &bleed);
        hp.bleeding.add_stack(Zone::Legs, &bleed);
        let gauze = &d.items.items[d.items.index("gauze").unwrap()];
        assert!(!would_help(gauze, Some(Zone::Head), &hp, &halo, &spec));
        apply(gauze, Some(Zone::Arms), &mut hp, &mut halo, &spec);
        assert_eq!(hp.bleeding.active[Zone::Arms], bleed.residual_hp_per_s, "only the residual stays");
        assert_eq!(hp.bleeding.active[Zone::Legs], bleed.hp_per_s, "other regions untouched");
        let patch = &d.items.items[d.items.index("arc_patch").unwrap()];
        halo.shield[Zone::Torso] = 0.0;
        apply(patch, Some(Zone::Torso), &mut hp, &mut halo, &spec);
        assert!((halo.shield[Zone::Torso] - spec.capacity[Zone::Torso] * patch.shield_frac).abs() < 1e-4);
    }
}
