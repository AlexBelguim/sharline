//! Quick ring menus: the magazine radial (hold R) and the heal ring (H). While one is open, mouse movement
//! steers a pointer instead of the view; the sector the pointer is in is the selection. Option 1 sits at
//! the top and the rest follow clockwise, so the same slot is always in the same direction.

use crate::AppState;
use crate::client::LocalControl;
use crate::config::Data;
use crate::ui_kit::{self as kit, Face, UiFonts};
use bevy::prelude::*;
use lightyear::prelude::Controlled;
use vetf_net::{PlayerItems, PlayerLoadout, PlayerWeapon, Vitals};
use vetf_sim::Zone;
use vetf_sim::items::{ItemScope, would_help};

/// Seconds reload must be held before the magazine radial opens (a shorter tap reloads the next slot).
pub const RELOAD_HOLD_S: f32 = 0.2;
/// How far (in mouse counts) the pointer must move off the centre to select anything.
pub const DEADZONE: f32 = 18.0;
/// The pointer is clamped to this radius, so turning back towards another slot is quick.
pub const POINTER_RADIUS: f32 = 60.0;

/// An open ring menu.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct Radial {
    /// Pointer offset from the centre, in mouse counts (+x right, +y down, like mouse motion).
    pub pointer: Vec2,
    /// How many options the ring has.
    pub options: usize,
}

impl Radial {
    pub fn new(options: usize) -> Self {
        Self { pointer: Vec2::ZERO, options }
    }

    /// Move the pointer by a mouse delta.
    pub fn steer(&mut self, delta: Vec2) {
        self.pointer = (self.pointer + delta).clamp_length_max(POINTER_RADIUS);
    }

    /// The option under the pointer (0-based), or `None` in the dead zone.
    pub fn selected(&self) -> Option<usize> {
        sector(self.pointer, self.options, DEADZONE)
    }
}

/// Which of `n` equal sectors `pointer` points into: sector 0 is centred straight up, and the index grows
/// clockwise. `None` inside the dead zone or for an empty ring.
pub fn sector(pointer: Vec2, n: usize, deadzone: f32) -> Option<usize> {
    if n == 0 || pointer.length() < deadzone {
        return None;
    }
    // Screen space has +y down: "up" is -y. Angle measured clockwise from up.
    let angle = pointer.x.atan2(-pointer.y).rem_euclid(std::f32::consts::TAU);
    let width = std::f32::consts::TAU / n as f32;
    Some(((angle + width / 2.0) / width) as usize % n)
}

/// The heal ring: items first; a region item opens a second ring of regions around it.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
pub struct HealMenu {
    pub ring: Radial,
    /// The region item picked on the first ring (kit slot), while its region ring is open.
    pub item: Option<usize>,
    pub regions: Radial,
}

impl HealMenu {
    pub fn new(items: usize) -> Self {
        Self { ring: Radial::new(items), item: None, regions: Radial::new(REGION_ORDER.len()) }
    }
}

/// Regions on the second ring, clockwise from the top: head up, legs down.
pub const REGION_ORDER: [Zone; 4] = [Zone::Head, Zone::Torso, Zone::Legs, Zone::Arms];

/// Where option `i` of `n` sits on a ring of radius `r` (screen space, +y down), for drawing.
pub fn option_offset(i: usize, n: usize, r: f32) -> Vec2 {
    let angle = std::f32::consts::TAU * i as f32 / n.max(1) as f32;
    Vec2::new(angle.sin() * r, -angle.cos() * r)
}

// ---------------------------------------------------------------------------------------------- drawing

/// One option on a ring as drawn.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct RingOption {
    /// Main text: a slot number, item or region.
    pub key: String,
    /// Small text under it: e.g. the ammo, how many are left, or the region's state.
    pub label: String,
    /// False draws it dimmed (a spent magazine, an item that would do nothing).
    pub enabled: bool,
    /// Outlined as current (the magazine in the gun).
    pub current: bool,
}

/// One ring on screen.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct RingLayer {
    pub title: String,
    pub options: Vec<RingOption>,
    pub selected: Option<usize>,
    pub pointer: Vec2,
    /// Centre, as an offset from the screen centre (px).
    pub centre: Vec2,
    pub radius: f32,
    pub chip: Vec2,
    pub key_size: f32,
    /// Only this option is drawn (the item whose region ring is open).
    pub focus: Option<usize>,
}

/// What the ring menus show this frame (no layers = closed). Filled by the menus that use a ring.
#[derive(Resource, Debug, Clone, Default)]
pub struct RingView {
    pub layers: Vec<RingLayer>,
}

pub struct RadialPlugin;

impl Plugin for RadialPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<RingView>()
            .add_systems(OnEnter(AppState::InGame), spawn_ring)
            .add_systems(Update, (fill_rings, draw_ring).chain().run_if(in_state(AppState::InGame)));
    }
}

/// Ring sizes on screen (px).
const RING_R: f32 = 165.0;
const CHIP: Vec2 = Vec2::new(132.0, 66.0);
const REGION_R: f32 = 128.0;
const REGION_CHIP: Vec2 = Vec2::new(112.0, 52.0);
const MAX_OPTIONS: usize = 8;
const MAX_LAYERS: usize = 2;

const INK: Color = kit::TEXT_HI;
const MUTED: Color = kit::TEXT_MID;
const TEAL: Color = kit::TEAL;
const CHIP_BG: Color = kit::PANEL_HI;
const CHIP_SELECTED: Color = Color::srgba(0.0, 0.45, 0.42, 0.95);

#[derive(Component)]
struct RingRoot;
#[derive(Component)]
struct RingChip(usize, usize);
#[derive(Component)]
struct RingKey(usize, usize);
#[derive(Component)]
struct RingLabel(usize, usize);
#[derive(Component)]
struct RingTitle(usize);
#[derive(Component)]
struct RingPointer(usize);

fn spawn_ring(mut commands: Commands, fonts: Res<UiFonts>) {
    // A zero-size anchor at the screen centre; chips are placed around it.
    let root = commands
        .spawn((
            RingRoot,
            Node {
                position_type: PositionType::Absolute,
                left: percent(50),
                top: percent(50),
                width: px(0),
                height: px(0),
                ..default()
            },
            Visibility::Hidden,
            GlobalZIndex(20),
            DespawnOnExit(AppState::InGame),
        ))
        .id();
    for layer in 0..MAX_LAYERS {
        commands.spawn((
            RingTitle(layer),
            Text::new(""),
            fonts.font(Face::Display, 700, 14.0),
            TextColor(MUTED),
            TextLayout::justify(Justify::Center),
            Node { position_type: PositionType::Absolute, width: px(160), ..default() },
            ChildOf(root),
        ));
        commands.spawn((
            RingPointer(layer),
            Node {
                position_type: PositionType::Absolute,
                width: px(10),
                height: px(10),
                border_radius: BorderRadius::MAX,
                ..default()
            },
            BackgroundColor(TEAL),
            ChildOf(root),
        ));
        for i in 0..MAX_OPTIONS {
            let chip = commands
                .spawn((
                    RingChip(layer, i),
                    Node {
                        position_type: PositionType::Absolute,
                        flex_direction: FlexDirection::Column,
                        align_items: AlignItems::Center,
                        justify_content: JustifyContent::Center,
                        border: UiRect::all(px(2)),
                        border_radius: BorderRadius::all(px(6)),
                        display: Display::None,
                        ..default()
                    },
                    BackgroundColor(CHIP_BG),
                    BorderColor::all(Color::NONE),
                    ChildOf(root),
                ))
                .id();
            commands.spawn((
                RingKey(layer, i),
                Text::new(""),
                fonts.font(Face::Display, 700, 24.0),
                TextColor(INK),
                ChildOf(chip),
            ));
            commands.spawn((
                RingLabel(layer, i),
                Text::new(""),
                fonts.font(Face::Display, 600, 14.0),
                TextColor(MUTED),
                ChildOf(chip),
            ));
        }
    }
}

/// Fill the ring layers from whichever menu is open.
#[allow(clippy::type_complexity)]
fn fill_rings(
    control: Res<LocalControl>,
    data: Res<Data>,
    me: Query<(&PlayerWeapon, &PlayerItems, &PlayerLoadout, Option<&Vitals>), With<Controlled>>,
    mut view: ResMut<RingView>,
) {
    view.layers.clear();
    let Some((w, items, lo, vitals)) = me.iter().next() else { return };
    if let Some(radial) = control.reload_radial {
        // The magazine radial: one option per slot, its ammo under the number, spent magazines dimmed (you
        // emptied them yourself; nothing says how many rounds the others hold).
        let options =
            lo.0.weapon
                .mags
                .iter()
                .enumerate()
                .map(|(i, ammo)| RingOption {
                    key: (i + 1).to_string(),
                    label: ammo.label.clone(),
                    enabled: w.0.slot_has_rounds(i as u8),
                    current: w.0.loaded as usize == i,
                })
                .collect();
        view.layers.push(RingLayer {
            title: "MAGAZINE".into(),
            options,
            selected: radial.selected(),
            pointer: radial.pointer,
            radius: RING_R,
            chip: CHIP,
            key_size: 24.0,
            ..default()
        });
        return;
    }
    let Some(menu) = control.heal else { return };
    let helps = |slot: usize, zone: Option<Zone>| {
        let spec = data.items.spec(&lo.0.kit[slot]);
        vitals.is_none_or(|v| would_help(spec, zone, &v.health, &v.halo, &lo.0.halo))
    };
    let options =
        lo.0.kit
            .iter()
            .enumerate()
            .map(|(i, k)| {
                let spec = data.items.spec(k);
                let left = items.0.count(i as u8);
                // A region item is worth opening if it helps any region.
                let useful = match spec.scope {
                    ItemScope::Body => helps(i, None),
                    ItemScope::Region => REGION_ORDER.iter().any(|z| helps(i, Some(*z))),
                };
                let scope = if spec.scope == ItemScope::Body { "ALL" } else { "REGION" };
                RingOption {
                    key: spec.label.clone(),
                    label: format!("x{left}  {scope}"),
                    enabled: left > 0 && useful,
                    current: false,
                }
            })
            .collect();
    view.layers.push(RingLayer {
        title: "HEAL".into(),
        options,
        selected: if menu.item.is_some() { menu.item } else { menu.ring.selected() },
        pointer: menu.ring.pointer,
        radius: RING_R,
        chip: CHIP,
        key_size: 17.0,
        focus: menu.item,
        ..default()
    });
    let Some(item) = menu.item else { return };
    let spec = data.items.spec(&lo.0.kit[item]);
    let options = REGION_ORDER
        .iter()
        .map(|z| {
            let label = match vitals {
                Some(v) if spec.shield_frac > 0.0 && spec.heal_hp <= 0.0 => {
                    if lo.0.halo.tiers[*z] == 0 {
                        "NO ARC".to_string()
                    } else {
                        format!("ARC {:.0}/{:.0}", v.halo.shield[*z], lo.0.halo.capacity[*z])
                    }
                }
                Some(v) if v.health.bleeding.active[*z] > v.health.bleeding.residual[*z] => "BLEEDING".into(),
                Some(v) => format!("{:.0}/{:.0}", v.health.hp[*z].max(0.0), v.health.max[*z]),
                None => String::new(),
            };
            RingOption { key: z.label().into(), label, enabled: helps(item, Some(*z)), current: false }
        })
        .collect();
    view.layers.push(RingLayer {
        title: String::new(),
        options,
        selected: menu.regions.selected(),
        pointer: menu.regions.pointer,
        centre: option_offset(item, lo.0.kit.len(), RING_R),
        radius: REGION_R,
        chip: REGION_CHIP,
        key_size: 18.0,
        ..default()
    });
}

#[allow(clippy::type_complexity)]
fn draw_ring(
    view: Res<RingView>,
    mut root: Query<&mut Visibility, With<RingRoot>>,
    mut chips: Query<(&RingChip, &mut Node, &mut BackgroundColor, &mut BorderColor), Without<RingPointer>>,
    mut keys: Query<(&RingKey, &mut Text, &mut TextColor, &mut TextFont), Without<RingLabel>>,
    mut labels: Query<(&RingLabel, &mut Text, &mut TextColor), (Without<RingKey>, Without<RingTitle>)>,
    mut titles: Query<(&RingTitle, &mut Text, &mut Node), (Without<RingKey>, Without<RingLabel>, Without<RingChip>)>,
    mut pointers: Query<(&RingPointer, &mut Node), (Without<RingChip>, Without<RingTitle>)>,
) {
    let open = !view.layers.is_empty();
    for mut v in &mut root {
        *v = if open { Visibility::Inherited } else { Visibility::Hidden };
    }
    if !open {
        return;
    }
    // Only the innermost open layer steers.
    let active = view.layers.len() - 1;
    for (chip, mut node, mut bg, mut border) in &mut chips {
        let Some(layer) = view.layers.get(chip.0) else {
            node.display = Display::None;
            continue;
        };
        let Some(opt) = layer.options.get(chip.1).filter(|_| layer.focus.is_none_or(|f| f == chip.1)) else {
            node.display = Display::None;
            continue;
        };
        let at = layer.centre + option_offset(chip.1, layer.options.len(), layer.radius) - layer.chip / 2.0;
        node.display = Display::Flex;
        node.left = px(at.x);
        node.top = px(at.y);
        node.width = px(layer.chip.x);
        node.height = px(layer.chip.y);
        let selected = layer.selected == Some(chip.1) && opt.enabled;
        bg.0 = if selected { CHIP_SELECTED } else { CHIP_BG };
        *border = BorderColor::all(if opt.current || layer.focus == Some(chip.1) { INK } else { Color::NONE });
    }
    for (k, mut t, mut c, mut font) in &mut keys {
        let Some(layer) = view.layers.get(k.0) else { continue };
        if let Some(opt) = layer.options.get(k.1) {
            t.0.clone_from(&opt.key);
            c.0 = if opt.enabled { INK } else { MUTED.with_alpha(0.5) };
            font.font_size = FontSize::Px(layer.key_size);
        }
    }
    for (l, mut t, mut c) in &mut labels {
        let Some(layer) = view.layers.get(l.0) else { continue };
        if let Some(opt) = layer.options.get(l.1) {
            t.0.clone_from(&opt.label);
            c.0 = if opt.enabled { MUTED } else { MUTED.with_alpha(0.5) };
        }
    }
    for (title, mut t, mut node) in &mut titles {
        match view.layers.get(title.0) {
            Some(layer) => {
                t.0.clone_from(&layer.title);
                node.left = px(layer.centre.x - 80.0);
                node.top = px(layer.centre.y + 28.0);
            }
            None => t.0.clear(),
        }
    }
    for (p, mut node) in &mut pointers {
        match view.layers.get(p.0).filter(|_| p.0 == active) {
            Some(layer) => {
                let at = layer.centre + layer.pointer / POINTER_RADIUS * (layer.radius * 0.45) - Vec2::splat(5.0);
                node.display = Display::Flex;
                node.left = px(at.x);
                node.top = px(at.y);
            }
            None => node.display = Display::None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sectors_start_at_the_top_and_go_clockwise() {
        assert_eq!(sector(Vec2::new(0.0, -50.0), 6, DEADZONE), Some(0), "up");
        assert_eq!(sector(Vec2::new(50.0, -30.0), 6, DEADZONE), Some(1), "up and right");
        assert_eq!(sector(Vec2::new(0.0, 50.0), 6, DEADZONE), Some(3), "down");
        assert_eq!(sector(Vec2::new(-50.0, -30.0), 6, DEADZONE), Some(5), "up and left");
        assert_eq!(sector(Vec2::new(50.0, 0.0), 4, DEADZONE), Some(1), "right of four");
        assert_eq!(sector(Vec2::new(3.0, 4.0), 6, DEADZONE), None, "dead zone");
        assert_eq!(sector(Vec2::new(0.0, -50.0), 0, DEADZONE), None);
    }

    #[test]
    fn layout_matches_selection() {
        for n in 1..=6 {
            for i in 0..n {
                assert_eq!(sector(option_offset(i, n, 40.0), n, DEADZONE), Some(i), "{i} of {n}");
            }
        }
    }

    #[test]
    fn pointer_is_clamped() {
        let mut r = Radial::new(6);
        r.steer(Vec2::new(0.0, -500.0));
        assert!((r.pointer.length() - POINTER_RADIUS).abs() < 1e-3);
        r.steer(Vec2::new(0.0, 2.0 * POINTER_RADIUS));
        assert_eq!(r.selected(), Some(3), "a short flick reaches the opposite slot");
    }
}
