//! Keyboard and gamepad-style focus on the Loadout page: Q / E switch column (the gun range: agent, weapon,
//! halo; the deathmatch layout: the gun with its parts and magazine type, then armor tier and ammo), the
//! arrow keys move inside a column (Left / Right within a row of items, Up / Down between rows), Enter
//! activates. The focused item gets the teal focus ring (2 px, offset 2), drawn only while the keyboard is in
//! use.

use super::model::{Draft, parts_for};
use super::ui_data::LoadoutUiData;
use super::{Act, LoadoutEdit, LoadoutUi};
use crate::config::Data;
use crate::ui_kit::*;
use bevy::input::mouse::AccumulatedMouseMotion;
use bevy::prelude::*;
use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::data::{AttachmentCategory, Core};
use vetf_sim::weapon::MAX_MAGS;

/// The canonical element of an action (the card, not its hotspot): the focus ring frames it.
#[derive(Component)]
pub struct Focusable;

/// The focus ring overlay.
#[derive(Component)]
pub struct FocusRing;

/// The focusable items of the page: columns of rows of items, and the column focus starts in (the gun's).
#[derive(Debug, Clone, PartialEq)]
pub struct Columns {
    pub cols: Vec<Vec<Vec<Act>>>,
    pub start: usize,
}

/// The focusable items of each column, as rows of items, in the order the page shows them.
pub fn columns(draft: &Draft, data: &GameData, ui: &LoadoutUiData, arc: Zone) -> Columns {
    let tabs: Vec<Act> = (0..data.weapons.weapons.len()).map(Act::Weapon).collect();
    let slots: Vec<Act> = AttachmentCategory::ALL
        .iter()
        .filter(|c| !parts_for(data, &draft.weapon, **c).is_empty())
        .map(|c| Act::Slot(*c))
        .collect();
    if let Some(kit) = &draft.fixed {
        // Deathmatch: the gun, its parts and its magazine type; then the armor tiers and the ammo row.
        let mags = draft
            .mag_options(data)
            .iter()
            .filter_map(|m| data.attachments.attachments.iter().position(|a| a.id == m.id))
            .map(Act::MagType)
            .collect();
        let armor = (1..=kit.armor.len() as u8).map(Act::Armor).collect();
        let ammo = draft.ammo_options(data).into_iter().map(Act::Ammo).collect();
        return Columns { cols: vec![vec![tabs, slots, mags], vec![armor, ammo]], start: 0 };
    }
    let agents = (0..ui.agents.len()).map(|i| vec![Act::Agent(i)]).collect();
    let mags = (0..=draft.mags.len().min(MAX_MAGS - 1)).map(Act::Mag).collect();
    let cores = [Core::Bulwark, Core::Mender, Core::Volt, Core::Phase].map(Act::Core).to_vec();
    let tiers = (1..=data.armor.loadout_tier_caps[arc].max(1)).map(Act::Tier).collect();
    let zones = Zone::ALL.map(Act::Zone).to_vec();
    Columns { cols: vec![agents, vec![tabs, slots, mags], vec![cores, tiers, zones]], start: 1 }
}

/// A focus move.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Move {
    PrevColumn,
    NextColumn,
    Left,
    Right,
    Up,
    Down,
}

/// Where focus goes from `current` (None = the first item of the weapon column).
pub fn step(columns: &Columns, current: Option<Act>, m: Move) -> Option<Act> {
    let cols = &columns.cols;
    let find = |a: Act| {
        cols.iter().enumerate().find_map(|(c, rows)| {
            rows.iter().enumerate().find_map(|(r, items)| items.iter().position(|x| *x == a).map(|i| (c, r, i)))
        })
    };
    let Some((c, r, i)) = current.and_then(find) else {
        return cols.get(columns.start)?.first().and_then(|row| row.first()).copied();
    };
    let at = |c: usize, r: usize, i: usize| {
        let rows = cols.get(c)?;
        let row = rows.get(r.min(rows.len().saturating_sub(1)))?;
        row.get(i.min(row.len().saturating_sub(1))).copied()
    };
    match m {
        Move::PrevColumn => at(c.saturating_sub(1), 0, 0),
        Move::NextColumn => at((c + 1).min(cols.len().saturating_sub(1)), 0, 0),
        Move::Left => at(c, r, i.saturating_sub(1)),
        Move::Right => at(c, r, i + 1),
        Move::Up => at(c, r.saturating_sub(1), i),
        Move::Down => at(c, r + 1, i),
    }
}

/// Q / E / arrows / Enter (the popover and the name field have their own keys).
pub fn keyboard_focus(
    keys: Res<ButtonInput<KeyCode>>,
    motion: Res<AccumulatedMouseMotion>,
    mouse: Res<ButtonInput<MouseButton>>,
    edit: Res<LoadoutEdit>,
    mut ui: ResMut<LoadoutUi>,
    data: Res<Data>,
    ui_data: Res<LoadoutUiData>,
) {
    if motion.delta != Vec2::ZERO || mouse.get_just_pressed().next().is_some() {
        if ui.keyboard {
            ui.keyboard = false;
        }
        return;
    }
    if ui.pop.is_some() || ui.save_as {
        return;
    }
    let shift = keys.pressed(KeyCode::ShiftLeft) || keys.pressed(KeyCode::ShiftRight);
    let moves = [
        (KeyCode::KeyQ, Move::PrevColumn),
        (KeyCode::KeyE, Move::NextColumn),
        (KeyCode::ArrowLeft, Move::Left),
        (KeyCode::ArrowRight, Move::Right),
        (KeyCode::ArrowUp, Move::Up),
        (KeyCode::ArrowDown, Move::Down),
    ];
    for (k, m) in moves {
        // Shift + Left / Right moves a magazine instead.
        if keys.just_pressed(k) && !(shift && matches!(m, Move::Left | Move::Right)) {
            let cols = columns(&edit.draft, &data, &ui_data, ui.arc);
            let next = if ui.keyboard { step(&cols, ui.focus, m) } else { ui.focus.or_else(|| step(&cols, None, m)) };
            ui.focus = next;
            ui.keyboard = true;
        }
    }
    if keys.just_pressed(KeyCode::Enter)
        && ui.keyboard
        && let Some(a) = ui.focus
    {
        ui.activate = Some(a);
    }
}

/// Keep the ring on the focused element (rebuilt sections replace their entities, so it is looked up each
/// frame).
pub fn place_ring(
    ui: Res<LoadoutUi>,
    targets: Query<(&Act, &ComputedNode, &UiGlobalTransform), With<Focusable>>,
    mut ring: Query<(&mut Node, &mut Visibility), With<FocusRing>>,
) {
    let Ok((mut node, mut vis)) = ring.single_mut() else { return };
    let target = ui.focus.filter(|_| ui.keyboard).and_then(|f| targets.iter().find(|(a, ..)| **a == f));
    let Some((_, n, t)) = target else {
        if *vis != Visibility::Hidden {
            *vis = Visibility::Hidden;
        }
        return;
    };
    let size = n.size() * n.inverse_scale_factor;
    let top_left = (t.translation - n.size() / 2.0) * n.inverse_scale_factor;
    // Outline width 2, offset 2.
    node.left = px(top_left.x - 4.0);
    node.top = px(top_left.y - 4.0);
    node.width = px(size.x + 8.0);
    node.height = px(size.y + 8.0);
    if *vis != Visibility::Inherited {
        *vis = Visibility::Inherited;
    }
}

/// The ring node (spawned once with the page).
pub fn ring() -> impl Bundle {
    (
        FocusRing,
        Node { position_type: PositionType::Absolute, border: UiRect::all(px(2)), ..default() },
        BorderColor::all(ACCENT_FOCUS),
        Visibility::Hidden,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    #[test]
    fn focus_moves_through_columns_and_rows() {
        let d = GameData::embedded();
        let ui = LoadoutUiData::embedded();
        let c = crate::config::loadout_choice(&crate::loadout::tests::plain_cli(), &d);
        let draft = Draft::from_choice(&c, &BTreeMap::new(), &d, None);
        let cols = columns(&draft, &d, &ui, Zone::Legs);
        assert_eq!(cols.cols[2][1], vec![Act::Tier(1), Act::Tier(2)], "legs cap at T2");
        assert_eq!(cols.cols[1][2].len(), 5, "four mags and the + ADD MAG slot");
        let start = step(&cols, None, Move::Right);
        assert_eq!(start, Some(Act::Weapon(0)));
        assert_eq!(step(&cols, start, Move::Right), Some(Act::Weapon(1)));
        assert_eq!(step(&cols, start, Move::Down), Some(Act::Slot(AttachmentCategory::Optic)));
        assert_eq!(step(&cols, Some(Act::Weapon(2)), Move::Down), Some(Act::Slot(AttachmentCategory::Mag)));
        assert_eq!(step(&cols, Some(Act::Mag(4)), Move::Down), Some(Act::Mag(4)), "the last row stays");
        assert_eq!(step(&cols, start, Move::NextColumn), Some(Act::Core(Core::Bulwark)));
        assert_eq!(step(&cols, start, Move::PrevColumn), Some(Act::Agent(0)));
        assert_eq!(step(&cols, Some(Act::Agent(0)), Move::Down), Some(Act::Agent(1)));
        assert_eq!(step(&cols, Some(Act::Core(Core::Phase)), Move::Down), Some(Act::Tier(2)), "clamped to the row");
    }

    /// The deathmatch layout: Q / E between the gun column (weapon tabs, attachment slots, magazine types) and
    /// the picks column (the armor tiers T1-T4, then the ammo row).
    #[test]
    fn the_deathmatch_layout_focuses_gun_and_magazine_then_armor_then_ammo() {
        use vetf_sim::data::{AmmoChoice, AmmoKind};
        let d = GameData::embedded();
        let ui = LoadoutUiData::embedded();
        let c = crate::config::loadout_choice(&crate::loadout::tests::plain_cli(), &d);
        let kit = d.rules.fixed_loadout(vetf_net::MatchMode::Ffa).cloned();
        let draft = Draft::from_choice(&c, &BTreeMap::new(), &d, kit);
        let cols = columns(&draft, &d, &ui, Zone::Torso);
        assert_eq!(cols.cols.len(), 2, "no agent column");
        assert_eq!(cols.start, 0);
        let mag = |id: &str| Act::MagType(d.attachments.attachments.iter().position(|a| a.id == id).unwrap());
        assert_eq!(cols.cols[0][2], [mag("mag_30"), mag("mag_45"), mag("mag_drum60")], "the Mako's magazines");
        let rows = &cols.cols[1];
        assert_eq!(rows.len(), 2, "armor, ammo");
        assert_eq!(rows[0], (1..=4).map(Act::Armor).collect::<Vec<_>>());
        assert_eq!(rows[1][0], Act::Ammo(AmmoChoice::STANDARD));
        let start = step(&cols, None, Move::Down);
        assert_eq!(start, Some(Act::Weapon(0)), "focus starts on the gun");
        assert_eq!(step(&cols, Some(Act::Slot(AttachmentCategory::Optic)), Move::Down), Some(mag("mag_30")));
        let right = step(&cols, start, Move::NextColumn);
        assert_eq!(right, Some(Act::Armor(1)));
        assert_eq!(step(&cols, right, Move::NextColumn), right, "the last column");
        assert_eq!(step(&cols, Some(Act::Armor(4)), Move::Right), Some(Act::Armor(4)), "the row's end");
        let ammo = step(&cols, Some(Act::Armor(2)), Move::Down);
        assert_eq!(ammo, Some(Act::Ammo(AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 1 })), "same position");
        assert_eq!(step(&cols, ammo, Move::Up), Some(Act::Armor(2)));
        assert_eq!(step(&cols, ammo, Move::PrevColumn), Some(Act::Weapon(0)));
    }
}
