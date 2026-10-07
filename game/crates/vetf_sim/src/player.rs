//! One player's full fixed-tick step (movement + weapon), shared by the host and predicting clients.

use crate::combat::{Bleeding, HaloSpec, Health};
use crate::data::{ArmorStats, GameData, Mode, Ruleset, WeightClass};
use crate::input::InputFrame;
use crate::items::{ItemEvents, ItemState, KitSlot};
use crate::level::Level;
use crate::movement::{self, MoveEvents, MoveMode, MoveModifiers, MoveState, Stance};
use crate::weapon::{ADS_AIMED, WeaponAction, WeaponEnv, WeaponEvents, WeaponLoadout, WeaponState};
use crate::zone::ZoneSet;
use serde::{Deserialize, Serialize};

/// Everything fixed for one life: gun, magazines, attachments, halo and the mode's healing kit.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Loadout {
    pub weapon: WeaponLoadout,
    pub armor_id: String,
    pub halo: HaloSpec,
    pub weight: WeightClass,
    /// Healing items in heal-ring order.
    pub kit: Vec<KitSlot>,
}

impl Loadout {
    pub fn new(weapon: WeaponLoadout, armor: &ArmorStats, kit: Vec<KitSlot>) -> Self {
        Self { weapon, armor_id: armor.id.clone(), halo: HaloSpec::from_armor(armor), weight: armor.weight_class, kit }
    }

    pub fn default_for(data: &GameData, mode: Mode) -> Self {
        let armor = data.armor.resolve_id(&data.rules.default_loadout.armor).expect("valid default armor");
        Self::new(WeaponLoadout::default_for(data), &armor, data.items.kit(mode))
    }
}

/// Conditions from the host's damage model that change how a player moves and shoots.
#[derive(Debug, Clone, Copy, PartialEq, Default, Serialize, Deserialize)]
pub struct Wounds {
    pub broken: ZoneSet,
    /// Seconds of "tagging" slow left (after taking HP damage).
    pub tag_slow_s: f32,
    /// Seconds of Volt-pulse slow left.
    pub volt_slow_s: f32,
}

impl Wounds {
    /// Bring wounds and bleeding in line with health and the mode's rules. The host calls this after
    /// anything changes health: without injuries no limb counts as broken (spill still applies), and
    /// without bleeding no bleed is kept.
    pub fn sync(&mut self, health: &mut Health, rules: &Ruleset) {
        self.broken = if rules.injuries { health.broken() } else { ZoneSet::EMPTY };
        if !rules.bleeding {
            health.bleeding = Bleeding::default();
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct PlayerEvents {
    pub movement: MoveEvents,
    pub weapon: WeaponEvents,
    pub items: ItemEvents,
}

pub fn move_modifiers(
    data: &GameData,
    loadout: &Loadout,
    weapon: &WeaponState,
    items: &ItemState,
    wounds: &Wounds,
) -> MoveModifiers {
    let spec = loadout.weapon.spec(data);
    let mods = &loadout.weapon.mods;
    let aimed = weapon.ads >= ADS_AIMED;
    let mut speed = spec.move_mult_held * mods.move_mult;
    if aimed {
        speed *= spec.move_mult_ads * mods.ads_move;
    }
    if items.using.is_some() {
        speed *= data.items.use_move_mult;
    }
    let legs_broken = wounds.broken.contains(crate::Zone::Legs);
    if legs_broken {
        speed *= data.combat.broken_legs.move_mult;
    }
    if wounds.tag_slow_s > 0.0 {
        speed *= 1.0 - data.combat.wounded.tag_slow_frac;
    }
    let phase = loadout.halo.core == Some(crate::data::Core::Phase);
    if wounds.volt_slow_s > 0.0 && !phase {
        speed *= 1.0 - data.combat.volt_pulse.slow_frac;
    }
    MoveModifiers {
        weight: loadout.weight,
        fx: data.armor.effects(loadout.weight),
        speed_mult: speed,
        legs_broken,
        ads: weapon.ads > 0.0,
    }
}

pub fn weapon_env(data: &GameData, ms: &MoveState, wounds: &Wounds) -> WeaponEnv {
    WeaponEnv {
        mode: ms.mode,
        sprinting: ms.sprinting,
        crouched: ms.stance != Stance::Stand && ms.mode == MoveMode::Ground,
        speed_frac: ms.horizontal_speed() / data.movement.speed.jog,
        broken_arms: wounds.broken.contains(crate::Zone::Arms),
        hands_busy: false,
    }
}

/// Advance one player by one tick: movement first, then items and the weapon (which see the new movement
/// state). An item in use keeps the gun down.
#[allow(clippy::too_many_arguments)]
pub fn step(
    data: &GameData,
    level: &Level,
    loadout: &Loadout,
    ms: &mut MoveState,
    ws: &mut WeaponState,
    items: &mut ItemState,
    wounds: &mut Wounds,
    input: &InputFrame,
) -> PlayerEvents {
    let dt = data.tick_dt();
    let input = input.sanitized();
    let mods = move_modifiers(data, loadout, ws, items, wounds);
    let movement = movement::step(data, level, ms, &input, &mods, dt);
    let mut env = weapon_env(data, ms, wounds);
    let lowered = env.sprinting || env.mode == MoveMode::Mantle;
    let hands_free = matches!(ws.action, WeaponAction::Ready | WeaponAction::MagChecking { .. });
    let item_ev = items.step(&data.items, &loadout.kit, &input, hands_free, lowered, data.net.tick_hz);
    // The gun stays down while an item is in hand and on the tick it is put away, except when a reload
    // cancelled it: that one-tick request must reach the weapon, or it would be lost.
    let reload_request = input.buttons.held(crate::input::Buttons::RELOAD) || input.reload_slot != 0;
    env.hands_busy = items.using.is_some() || item_ev.finished.is_some() || (item_ev.cancelled && !reload_request);
    let weapon = ws.step(data, &loadout.weapon, &input, &env);
    wounds.tag_slow_s = (wounds.tag_slow_s - dt).max(0.0);
    wounds.volt_slow_s = (wounds.volt_slow_s - dt).max(0.0);
    PlayerEvents { movement, weapon, items: item_ev }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::input::Buttons;
    use crate::movement::collision::{Brush, BrushKind};
    use glam::{Vec2, Vec3};

    #[test]
    fn aiming_slows_movement_and_heavy_halo_too() {
        let d = GameData::embedded();
        let mut level = Level::default();
        level.world.push(Brush::cuboid(
            Vec3::splat(-100.0).with_y(-1.0),
            Vec3::splat(100.0).with_y(0.0),
            BrushKind::Solid,
        ));
        let l = Loadout::default_for(&d, Mode::Tdm);
        let mut ms = MoveState::spawn(Vec3::ZERO, 1.6);
        let mut ws = WeaponState::new(&d, &l.weapon);
        let mut items = ItemState::new(&l.kit);
        let mut wounds = Wounds::default();
        let run = InputFrame {
            movement: Vec2::Y,
            yaw: 0.0,
            pitch: 0.0,
            buttons: Buttons(Buttons::ADS),
            ..Default::default()
        };
        for _ in 0..90 {
            step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &run);
        }
        let mako = d.weapon("ar7_mako").unwrap();
        let want = d.movement.speed.jog * mako.move_mult_ads * d.armor.effects(l.weight).move_mult;
        assert!((ms.horizontal_speed() - want).abs() < 0.05, "{} vs {want}", ms.horizontal_speed());
    }

    #[test]
    fn using_an_item_keeps_the_gun_down_and_slows_you() {
        let d = GameData::embedded();
        let mut level = Level::default();
        level.world.push(Brush::cuboid(
            Vec3::splat(-100.0).with_y(-1.0),
            Vec3::splat(100.0).with_y(0.0),
            BrushKind::Solid,
        ));
        let l = Loadout::default_for(&d, Mode::Tdm);
        let mut ms = MoveState::spawn(Vec3::ZERO, 1.6);
        let mut ws = WeaponState::new(&d, &l.weapon);
        ws.action = WeaponAction::Ready;
        let mut items = ItemState::new(&l.kit);
        let mut wounds = Wounds::default();
        let walk = InputFrame { movement: Vec2::Y, ..Default::default() };
        let (use_item, use_zone) = crate::items::encode_pick(0, None);
        let ev =
            step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &InputFrame { use_item, use_zone, ..walk });
        assert!(ev.items.started.is_some());
        for _ in 0..90 {
            step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &walk);
        }
        assert!(items.using.is_some(), "a trauma kit takes longer than 1.5 s");
        let mako = d.weapon("ar7_mako").unwrap();
        let want =
            d.movement.speed.jog * mako.move_mult_held * d.items.use_move_mult * d.armor.effects(l.weight).move_mult;
        assert!((ms.horizontal_speed() - want).abs() < 0.05, "{} vs {want}", ms.horizontal_speed());
        // pulling the trigger cancels the item (it is kept), and the gun takes as long to come up as after a sprint
        let fire = InputFrame { buttons: Buttons(Buttons::FIRE), ..walk };
        let ev = step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &fire);
        assert!(ev.items.cancelled && ev.weapon.shot.is_none());
        assert_eq!(items.count(0), l.kit[0].count, "a cancelled item is kept");
        let up = crate::weapon::secs_to_ticks(mako.sprint_to_fire_s * l.weapon.mods.sprint_to_fire, d.net.tick_hz);
        let first = (1..60)
            .find(|_| step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &fire).weapon.shot.is_some());
        assert_eq!(first, Some(up as i32));
    }

    #[test]
    fn a_reload_during_an_item_cancels_it_and_reloads() {
        let d = GameData::embedded();
        let mut level = Level::default();
        level.world.push(Brush::cuboid(
            Vec3::splat(-100.0).with_y(-1.0),
            Vec3::splat(100.0).with_y(0.0),
            BrushKind::Solid,
        ));
        let l = Loadout::default_for(&d, Mode::Tdm);
        for (bits, slot, want_slot) in [(0, 3, 2), (Buttons::RELOAD, 0, 1)] {
            let mut ms = MoveState::spawn(Vec3::ZERO, 1.6);
            let mut ws = WeaponState::new(&d, &l.weapon);
            ws.action = WeaponAction::Ready;
            ws.rounds[0] = 10;
            let mut items = ItemState::new(&l.kit);
            let mut wounds = Wounds::default();
            let idle = InputFrame::default();
            let (use_item, use_zone) = crate::items::encode_pick(0, None);
            step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &InputFrame { use_item, use_zone, ..idle });
            for _ in 0..30 {
                step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &idle);
            }
            let reload = InputFrame { buttons: Buttons(bits), reload_slot: slot, ..idle };
            let ev = step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &reload);
            assert!(ev.items.cancelled, "{bits} {slot}");
            assert!(ev.weapon.reload_started.is_some(), "the reload is not lost ({bits} {slot})");
            assert!(matches!(ws.action, WeaponAction::Reloading { slot, .. } if slot == want_slot), "{:?}", ws.action);
        }
    }

    #[test]
    fn team_deathmatch_has_no_injuries_or_bleeding_but_keeps_spill() {
        let d = GameData::embedded();
        let shr = d.ammo.resolve(
            crate::data::WeaponClass::AssaultRifle,
            crate::data::AmmoChoice { kind: crate::data::AmmoKind::Shrapnel, tier: 1 },
        );
        let bleed = shr.unwrap().bleed.unwrap();
        let spill = &d.weapons.spill_to_torso;
        for rules in [d.rules.rulesets.tdm, d.rules.rulesets.range] {
            let mut hp = Health::new(d.armor.zone_hp);
            let mut wounds = Wounds::default();
            hp.bleeding.add_stack(crate::Zone::Arms, &bleed);
            hp.apply(crate::Zone::Legs, 200.0, spill);
            wounds.sync(&mut hp, &rules);
            assert!(hp.hp[crate::Zone::Torso] < hp.max[crate::Zone::Torso], "spill applies in every mode");
            assert_eq!(wounds.broken.contains(crate::Zone::Legs), rules.injuries);
            assert_eq!(hp.bleeding.is_bleeding(), rules.bleeding);
        }
        assert_eq!(d.rules.rulesets.range, Ruleset::FULL, "the range runs the full extraction rules");
        assert!(!d.rules.rulesets.tdm.regional_items);
    }
}
