//! One player's full fixed-tick step (movement + weapon), shared by the host and predicting clients.

use crate::combat::{Bleeding, HaloSpec, Health};
use crate::data::{ArmorStats, GameData, Ruleset, WeightClass};
use crate::input::InputFrame;
use crate::level::Level;
use crate::movement::{self, MoveEvents, MoveMode, MoveModifiers, MoveState, Stance};
use crate::weapon::{ADS_AIMED, WeaponEnv, WeaponEvents, WeaponLoadout, WeaponState};
use crate::zone::ZoneSet;
use serde::{Deserialize, Serialize};

/// Everything fixed for one life: gun, ammo, attachments and halo.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Loadout {
    pub weapon: WeaponLoadout,
    pub armor_id: String,
    pub halo: HaloSpec,
    pub weight: WeightClass,
}

impl Loadout {
    pub fn new(weapon: WeaponLoadout, armor: &ArmorStats) -> Self {
        Self { weapon, armor_id: armor.id.clone(), halo: HaloSpec::from_armor(armor), weight: armor.weight_class }
    }

    pub fn default_for(data: &GameData) -> Self {
        let armor = data.armor.resolve_id(&data.rules.default_loadout.armor).expect("valid default armor");
        Self::new(WeaponLoadout::default_for(data), &armor)
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
}

pub fn move_modifiers(data: &GameData, loadout: &Loadout, weapon: &WeaponState, wounds: &Wounds) -> MoveModifiers {
    let spec = loadout.weapon.spec(data);
    let mods = &loadout.weapon.mods;
    let aimed = weapon.ads >= ADS_AIMED;
    let mut speed = spec.move_mult_held * mods.move_mult;
    if aimed {
        speed *= spec.move_mult_ads * mods.ads_move;
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
    }
}

/// Advance one player by one tick: movement first, then the weapon (which sees the new movement state).
pub fn step(
    data: &GameData,
    level: &Level,
    loadout: &Loadout,
    ms: &mut MoveState,
    ws: &mut WeaponState,
    wounds: &mut Wounds,
    input: &InputFrame,
) -> PlayerEvents {
    let dt = data.tick_dt();
    let input = input.sanitized();
    let mods = move_modifiers(data, loadout, ws, wounds);
    let movement = movement::step(data, level, ms, &input, &mods, dt);
    let env = weapon_env(data, ms, wounds);
    let weapon = ws.step(data, &loadout.weapon, &input, &env);
    wounds.tag_slow_s = (wounds.tag_slow_s - dt).max(0.0);
    wounds.volt_slow_s = (wounds.volt_slow_s - dt).max(0.0);
    PlayerEvents { movement, weapon }
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
        let l = Loadout::default_for(&d);
        let mut ms = MoveState::spawn(Vec3::ZERO, 1.6);
        let mut ws = WeaponState::new(&d, &l.weapon);
        let mut wounds = Wounds::default();
        let run =
            InputFrame { movement: Vec2::Y, yaw: 0.0, pitch: 0.0, buttons: Buttons(Buttons::ADS), reload_slot: 0 };
        for _ in 0..90 {
            step(&d, &level, &l, &mut ms, &mut ws, &mut wounds, &run);
        }
        let mako = d.weapon("ar7_mako").unwrap();
        let want = d.movement.speed.jog * mako.move_mult_ads * d.armor.effects(l.weight).move_mult;
        assert!((ms.horizontal_speed() - want).abs() < 0.05, "{} vs {want}", ms.horizontal_speed());
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
