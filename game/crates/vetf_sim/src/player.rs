//! One player's full fixed-tick step (movement + weapon), shared by the host and predicting clients.

use crate::combat::{Bleeding, HaloSpec, Health};
use crate::data::{ArmorStats, GameData, Mode, Ruleset, WeightClass};
use crate::input::InputFrame;
use crate::items::{ItemEvents, ItemState, KitSlot};
use crate::level::Level;
use crate::movement::{self, MoveEvents, MoveMode, MoveModifiers, MoveState, Stance};
use crate::throwable::{self, Launch, ThrowKind, ThrowKit};
use crate::weapon::{WeaponAction, WeaponEnv, WeaponEvents, WeaponLoadout, WeaponState};
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
    /// Throwables each life starts with (the mode's, `rules.ron` `throwables`).
    #[serde(default)]
    pub throws: ThrowKit,
}

impl Loadout {
    pub fn new(weapon: WeaponLoadout, armor: &ArmorStats, kit: Vec<KitSlot>) -> Self {
        Self {
            weapon,
            armor_id: armor.id.clone(),
            halo: HaloSpec::from_armor(armor),
            weight: armor.weight_class,
            kit,
            throws: ThrowKit::default(),
        }
    }

    /// The same loadout carrying `throws` each life.
    pub fn with_throws(self, throws: ThrowKit) -> Self {
        Self { throws, ..self }
    }

    pub fn default_for(data: &GameData, mode: Mode) -> Self {
        let armor = data.armor.resolve_id(&data.rules.default_loadout.armor).expect("valid default armor");
        Self::new(WeaponLoadout::default_for(data), &armor, data.items.kit(mode))
            .with_throws(data.rules.throw_kit(mode))
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
    pub throw: ThrowEvents,
}

/// What the throwing hand did this tick.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct ThrowEvents {
    /// A throw key started a wind-up.
    pub started: Option<ThrowKind>,
    /// A grenade left the hand (the host flies it; the thrower's client flies its own at once).
    pub launched: Option<Launch>,
}

/// What changes a player's speed: the gun they carry, an item in use, wounds and the halo's weight. Aiming and
/// firing never do (user direction 2026-10-08).
pub fn move_modifiers(data: &GameData, loadout: &Loadout, items: &ItemState, wounds: &Wounds) -> MoveModifiers {
    let spec = loadout.weapon.spec(data);
    let gear = spec.move_mult_held * loadout.weapon.mods.move_mult;
    let mut speed = gear;
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
        gear_mult: gear,
        legs_broken,
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
    let mods = move_modifiers(data, loadout, items, wounds);
    let movement = movement::step(data, level, ms, &input, &mods, dt);
    let mut env = weapon_env(data, ms, wounds);
    let lowered = env.sprinting || env.mode == MoveMode::Mantle;
    let hands_free = matches!(ws.action, WeaponAction::Ready | WeaponAction::MagChecking { .. });
    // No item while a throw is in hand.
    let throwing = items.throw.busy();
    let item_ev = items.step(&data.items, &loadout.kit, &input, hands_free && !throwing, lowered, data.net.tick_hz);
    // The gun stays down while an item is in hand and on the tick it is put away, except when a reload
    // cancelled it: that one-tick request must reach the weapon, or it would be lost.
    let reload_request = input.buttons.held(crate::input::Buttons::RELOAD) || input.reload_slot != 0;
    // A throw: with the gun idle (not reloading), no item in hand, and not mantling (a sprint is fine).
    let can_throw = hands_free
        && items.using.is_none()
        && item_ev.finished.is_none()
        && !reload_request
        && ms.mode != MoveMode::Mantle;
    let hand = items.throw.step(&data.throwables.throw, input.buttons, can_throw, data.net.tick_hz);
    let launched = hand.released.map(|(kind, seq)| {
        let (origin, vel) =
            throwable::launch(&data.throwables.throw, &level.world, ms.eye_pos(), ms.vel, input.yaw, input.pitch);
        Launch { kind, seq, origin, vel }
    });
    env.hands_busy = items.using.is_some()
        || item_ev.finished.is_some()
        || (item_ev.cancelled && !reload_request)
        || items.throw.busy();
    let weapon = ws.step(data, &loadout.weapon, &input, &env);
    wounds.tag_slow_s = (wounds.tag_slow_s - dt).max(0.0);
    wounds.volt_slow_s = (wounds.volt_slow_s - dt).max(0.0);
    PlayerEvents { movement, weapon, items: item_ev, throw: ThrowEvents { started: hand.started, launched } }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::input::Buttons;
    use crate::movement::collision::{Brush, BrushKind};
    use glam::{Vec2, Vec3};

    fn flat() -> Level {
        let mut level = Level::default();
        level.world.push(Brush::cuboid(
            Vec3::splat(-100.0).with_y(-1.0),
            Vec3::splat(100.0).with_y(0.0),
            BrushKind::Solid,
        ));
        level
    }

    /// Aiming and firing never slow you or end a sprint (user direction 2026-10-08): a run with the gun up is as
    /// fast as one without, for every gun, and an aimed sprint fires once the gun is up.
    #[test]
    fn aiming_and_firing_never_slow_movement() {
        let d = GameData::embedded();
        let level = flat();
        let l = Loadout::default_for(&d, Mode::Tdm);
        let weight = d.armor.effects(l.weight).move_mult;
        for gun in ["ar7_mako", "vk50_warden", "sk9_skink"] {
            let weapon = WeaponLoadout::resolve(&d, gun, &[crate::data::AmmoChoice::STANDARD], &[]).unwrap();
            let l = Loadout { weapon, ..l.clone() };
            let held = l.weapon.spec(&d).move_mult_held * l.weapon.mods.move_mult * weight;
            for (bits, speed) in [
                (0, d.movement.speed.jog),
                (Buttons::ADS, d.movement.speed.jog),
                (Buttons::ADS | Buttons::FIRE, d.movement.speed.jog),
                (Buttons::SPRINT, d.movement.speed.sprint),
                (Buttons::SPRINT | Buttons::ADS, d.movement.speed.sprint),
                (Buttons::SPRINT | Buttons::FIRE, d.movement.speed.sprint),
                (Buttons::SPRINT | Buttons::ADS | Buttons::FIRE, d.movement.speed.sprint),
            ] {
                let mut ms = MoveState::spawn(Vec3::ZERO, 1.6);
                let mut ws = WeaponState::new(&d, &l.weapon);
                let mut items = ItemState::new(&l.kit);
                let mut wounds = Wounds::default();
                let mut shots = 0;
                for t in 0..120 {
                    // Fire is pressed every other tick, so the bolt gun fires too.
                    let held = if t % 2 == 1 { bits & !Buttons::FIRE } else { bits };
                    let run = InputFrame { movement: Vec2::Y, buttons: Buttons(held), ..Default::default() };
                    let ev = step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &run);
                    shots += ev.weapon.shot.is_some() as u32;
                }
                let want = speed * held;
                assert!(
                    (ms.horizontal_speed() - want).abs() < 0.05,
                    "{gun} {bits:#x}: {} vs {want}",
                    ms.horizontal_speed()
                );
                assert_eq!(ms.sprinting, bits & Buttons::SPRINT != 0, "{gun} {bits:#x}");
                if bits & Buttons::ADS != 0 {
                    assert_eq!(ws.ads, 1.0, "{gun} {bits:#x}: aimed on the move");
                }
                if bits & Buttons::FIRE != 0 {
                    assert!(shots > 0, "{gun} {bits:#x}: fires on the move");
                }
            }
        }
    }

    /// Every loadout slides from its own run (review: a Heavy halo with the Warden jogged at 3.93 m/s, under the old
    /// fixed 4.0 m/s threshold): every weight class with every gun, bare and with its slowest part in each
    /// category, slides from a forward jog without sprint; a walk never slides.
    #[test]
    fn every_loadout_slides_from_its_own_run() {
        let d = GameData::embedded();
        let level = flat();
        let base = Loadout::default_for(&d, Mode::Tdm);
        for gun in &d.weapons.weapons {
            let mut slowest: Vec<&crate::data::AttachmentSpec> = vec![];
            for a in d.attachments.attachments.iter().filter(|a| a.fits.contains(&gun.id)) {
                let slower = |s: &&crate::data::AttachmentSpec| a.move_mult.unwrap_or(1.0) < s.move_mult.unwrap_or(1.0);
                match slowest.iter().position(|s| s.cat == a.cat) {
                    Some(i) if slower(&slowest[i]) => slowest[i] = a,
                    Some(_) => {}
                    None => slowest.push(a),
                }
            }
            let slow: Vec<String> = slowest.iter().map(|a| a.id.clone()).collect();
            for parts in [vec![], slow] {
                let weapon = WeaponLoadout::resolve(&d, &gun.id, &[crate::data::AmmoChoice::STANDARD], &parts).unwrap();
                for weight in [WeightClass::None, WeightClass::Light, WeightClass::Medium, WeightClass::Heavy] {
                    let l = Loadout { weapon: weapon.clone(), weight, ..base.clone() };
                    for (bits, want) in [(0, true), (Buttons::WALK, false)] {
                        let mut ms = MoveState::spawn(Vec3::ZERO, 1.6);
                        let mut ws = WeaponState::new(&d, &l.weapon);
                        let mut items = ItemState::new(&l.kit);
                        let mut wounds = Wounds::default();
                        let run = InputFrame { movement: Vec2::Y, buttons: Buttons(bits), ..Default::default() };
                        for _ in 0..60 {
                            step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &run);
                        }
                        let speed = ms.horizontal_speed();
                        let crouch = InputFrame { buttons: Buttons(bits | Buttons::CROUCH), ..run };
                        let ev = step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &crouch);
                        let why = format!("{} {parts:?} {weight:?} {bits:#x} at {speed} m/s", gun.id);
                        assert_eq!(ev.movement.slide_started, want, "{why}");
                    }
                }
            }
        }
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

    /// Every life in team deathmatch and free-for-all starts with the rules' smokes and molotovs (1 and 1), the gun
    /// range with its practice share; a fresh life's hand holds them.
    #[test]
    fn each_life_starts_with_the_modes_throwables() {
        let d = GameData::embedded();
        for mode in [Mode::Tdm, Mode::Ffa] {
            let l = Loadout::default_for(&d, mode);
            assert_eq!(l.throws, ThrowKit { smoke: 1, molotov: 1 }, "{mode:?}");
            assert_eq!(l.throws, d.rules.throw_kit(mode));
            let items = ItemState::for_loadout(&l);
            assert_eq!(items.throw.left, l.throws);
            assert!(!items.throw.busy());
        }
        let range = Loadout::default_for(&d, Mode::Range);
        assert_eq!(range.throws, d.rules.range_throwables);
        assert!(range.throws.total() > 0);
        // The plain kit constructor carries none (old saves, tests).
        assert_eq!(ItemState::new(&range.kit).throw.left, ThrowKit::default());
    }

    /// A throw through the player step: the key starts the wind-up and takes one, the gun is down (no shot)
    /// until the recovery is over, the grenade leaves after the wind-up from ahead of the eye with the next
    /// number, and with none left the key does nothing.
    #[test]
    fn throwing_lowers_the_gun_and_launches_once() {
        let d = GameData::embedded();
        let level = flat();
        let l = Loadout::default_for(&d, Mode::Tdm);
        let mut ms = MoveState::spawn(Vec3::ZERO, 1.6);
        let mut ws = WeaponState::new(&d, &l.weapon);
        let mut items = ItemState::for_loadout(&l);
        let mut wounds = Wounds::default();
        // Let the gun come up first.
        for _ in 0..120 {
            step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &InputFrame::default());
        }
        let throw_fire = InputFrame { buttons: Buttons(Buttons::THROW_SMOKE | Buttons::FIRE), ..Default::default() };
        let ev = step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &throw_fire);
        assert_eq!(ev.throw.started, Some(ThrowKind::Smoke));
        assert_eq!(items.throw.left.smoke, 0);
        let mut launched = Vec::new();
        let mut shots = 0;
        let fire = InputFrame { buttons: Buttons(Buttons::FIRE), ..Default::default() };
        let busy_ticks = crate::weapon::secs_to_ticks(d.throwables.throw.windup_s + d.throwables.throw.recover_s, 60);
        for _ in 0..busy_ticks {
            let ev = step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &fire);
            shots += ev.weapon.shot.is_some() as u32;
            launched.extend(ev.throw.launched);
        }
        assert_eq!(shots, 0, "no shot while the arm is busy");
        assert_eq!(launched.len(), 1);
        let g = launched[0];
        assert_eq!((g.kind, g.seq), (ThrowKind::Smoke, 1));
        assert!(g.origin.distance(ms.eye_pos()) < 0.6 && g.vel.length() > 10.0, "{g:?}");
        // The smoke key again: none left.
        let none = InputFrame::default();
        step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &none);
        let smoke = InputFrame { buttons: Buttons(Buttons::THROW_SMOKE), ..Default::default() };
        assert_eq!(step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &smoke).throw.started, None);
        // The molotov still throws, numbered 2.
        let molotov = InputFrame { buttons: Buttons(Buttons::THROW_MOLOTOV), ..Default::default() };
        assert_eq!(
            step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &molotov).throw.started,
            Some(ThrowKind::Molotov)
        );
        let mut seq = None;
        for _ in 0..60 {
            if let Some(g) = step(&d, &level, &l, &mut ms, &mut ws, &mut items, &mut wounds, &none).throw.launched {
                seq = Some(g.seq);
            }
        }
        assert_eq!(seq, Some(2));
    }
}
