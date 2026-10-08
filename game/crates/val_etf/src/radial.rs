//! Quick ring menus: the magazine radial (hold Reload for the Gameplay tab's radial hold time) and the heal
//! ring (Heal); `client` reads their keys from the key map. While one is open, mouse movement steers a cursor
//! instead of the view; the sector the cursor is in is the selection. Option 1 sits at the top and the rest
//! follow clockwise, so the same slot is always in the same direction.
//!
//! The cursor is drawn exactly where it is, in screen pixels, and reaches out as far as the option chips: push
//! toward an option and the cursor lands on it. Each ring is wide enough that every chip lies wholly inside its
//! own sector ([`ring_radius`]), so whatever chip the cursor is over is the one that lights up.

use crate::AppState;
use crate::client::LocalControl;
use crate::config::Data;
use crate::settings::RadialTuning;
use crate::ui_kit::{self as kit, Face, UiFonts};
use bevy::prelude::*;
use lightyear::prelude::Controlled;
use vetf_net::{PlayerItems, PlayerLoadout, PlayerWeapon, Vitals};
use vetf_sim::Zone;
use vetf_sim::items::{ItemScope, would_help};

/// Ring cursor pixels per mouse count at the player's DPI (the Mouse & Aim tab), so the hand travels the same
/// distance on any mouse: settings.ron `radial.px_per_inch` per inch of travel.
pub fn px_per_count(dpi: u32, tuning: &RadialTuning) -> f32 {
    tuning.px_per_inch / dpi.max(1) as f32
}

/// An open ring menu.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Radial {
    /// Cursor offset from the ring's centre, in screen px (+x right, +y down, like mouse motion).
    pub pointer: Vec2,
    /// How many options the ring has.
    pub options: usize,
    /// How far out the options sit (px); the cursor is held within it, so it can rest on a chip and turning
    /// back toward another one stays quick.
    pub reach: f32,
    /// How far (px) the cursor must move off the centre to select anything (settings.ron
    /// `radial.dead_zone_px`; the Gameplay tab shows it on its RADIAL POINTER row).
    pub dead_zone: f32,
}

impl Radial {
    /// The main ring (magazines, heal items).
    pub fn new(options: usize, tuning: &RadialTuning) -> Self {
        let dead_zone = tuning.dead_zone_px;
        Self { pointer: Vec2::ZERO, options, reach: ring_radius(options, CHIP, RING_R, dead_zone), dead_zone }
    }

    /// The heal ring's second ring, of body regions around the picked item.
    pub fn regions(tuning: &RadialTuning) -> Self {
        let (n, dead_zone) = (REGION_ORDER.len(), tuning.dead_zone_px);
        Self { pointer: Vec2::ZERO, options: n, reach: ring_radius(n, REGION_CHIP, REGION_R, dead_zone), dead_zone }
    }

    /// Move the cursor by a mouse delta, already in screen px (see [`px_per_count`]).
    pub fn steer(&mut self, delta: Vec2) {
        self.pointer = (self.pointer + delta).clamp_length_max(self.reach);
    }

    /// The option under the cursor (0-based), or `None` in the dead zone.
    pub fn selected(&self) -> Option<usize> {
        sector(self.pointer, self.options, self.dead_zone)
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
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct HealMenu {
    pub ring: Radial,
    /// The region item picked on the first ring (kit slot), while its region ring is open.
    pub item: Option<usize>,
    pub regions: Radial,
}

impl HealMenu {
    pub fn new(items: usize, tuning: &RadialTuning) -> Self {
        Self { ring: Radial::new(items, tuning), item: None, regions: Radial::regions(tuning) }
    }
}

/// What each heal-ring option allows right now: the item's scope, whether it can be picked (any left and
/// it would do something), and which regions (in [`REGION_ORDER`]) it would help. The ring dims what is not
/// allowed and a click on a dimmed option does nothing.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct HealOption {
    pub scope: ItemScope,
    pub left: u8,
    pub enabled: bool,
    pub regions: [bool; 4],
}

/// The heal ring's options for a player. Without vitals (not replicated yet) everything counts as useful.
pub fn heal_options(
    data: &vetf_sim::GameData,
    loadout: &vetf_sim::player::Loadout,
    items: &vetf_sim::items::ItemState,
    vitals: Option<&Vitals>,
) -> Vec<HealOption> {
    loadout
        .kit
        .iter()
        .enumerate()
        .map(|(i, k)| {
            let spec = data.items.spec(k);
            let helps =
                |zone: Option<Zone>| vitals.is_none_or(|v| would_help(spec, zone, &v.health, &v.halo, &loadout.halo));
            let regions = REGION_ORDER.map(|z| spec.scope == ItemScope::Region && helps(Some(z)));
            let useful = match spec.scope {
                ItemScope::Body => helps(None),
                ItemScope::Region => regions.iter().any(|r| *r),
            };
            let left = items.count(i as u8);
            HealOption { scope: spec.scope, left, enabled: left > 0 && useful, regions }
        })
        .collect()
}

/// Regions on the second ring, clockwise from the top: head up, legs down.
pub const REGION_ORDER: [Zone; 4] = [Zone::Head, Zone::Torso, Zone::Legs, Zone::Arms];

/// Where option `i` of `n` sits on a ring of radius `r` (screen space, +y down), for drawing.
pub fn option_offset(i: usize, n: usize, r: f32) -> Vec2 {
    let angle = std::f32::consts::TAU * i as f32 / n.max(1) as f32;
    Vec2::new(angle.sin() * r, -angle.cos() * r)
}

/// Gap (px) kept between a chip and the edges of its sector.
const SECTOR_GAP: f32 = 4.0;

/// True when every one of `n` chips of size `chip` on a ring of radius `r` lies wholly inside its own sector
/// (with [`SECTOR_GAP`] to spare) and clear of the dead zone.
fn chips_fit(n: usize, chip: Vec2, r: f32, dead_zone: f32) -> bool {
    let h = chip / 2.0 + SECTOR_GAP;
    (0..n).all(|i| {
        let c = option_offset(i, n, r);
        // Sectors are convex (at most a half plane) for two options or more, so the corners decide.
        let corners = [Vec2::new(-h.x, -h.y), Vec2::new(h.x, -h.y), Vec2::new(h.x, h.y), Vec2::new(-h.x, h.y)];
        let nearest = Vec2::ZERO.clamp(c - h, c + h);
        nearest.length() > dead_zone && (n == 1 || corners.iter().all(|&k| sector(c + k, n, 0.0) == Some(i)))
    })
}

/// The radius for a ring of `n` chips of size `chip`: `base`, or wider when the chips would cross into their
/// neighbours' sectors (seven or eight heal items), so the chip under the cursor is always the selection.
pub fn ring_radius(n: usize, chip: Vec2, base: f32, dead_zone: f32) -> f32 {
    let mut r = base;
    while !chips_fit(n, chip, r, dead_zone) && r < base * 4.0 {
        r += 1.0;
    }
    r
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
/// The cursor dot's size (px).
const CURSOR: f32 = 14.0;
const MAX_OPTIONS: usize = 8;
const MAX_LAYERS: usize = 2;

const INK: Color = kit::TEXT_HI;
const MUTED: Color = kit::TEXT_MID;
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
        // The cursor, drawn over the chips (it rests on them): light with a dark rim, so it shows on the teal
        // of a lit chip as well as on the dark ones.
        commands.spawn((
            RingPointer(layer),
            Node {
                position_type: PositionType::Absolute,
                width: px(CURSOR),
                height: px(CURSOR),
                border: UiRect::all(px(3)),
                border_radius: BorderRadius::MAX,
                ..default()
            },
            BackgroundColor(INK),
            BorderColor::all(Color::srgba(0.0, 0.0, 0.0, 0.75)),
            ZIndex(10),
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
            radius: radial.reach,
            chip: CHIP,
            key_size: 24.0,
            ..default()
        });
        return;
    }
    let Some(menu) = control.heal else { return };
    let heal = heal_options(&data, &lo.0, &items.0, vitals);
    let options =
        lo.0.kit
            .iter()
            .zip(&heal)
            .map(|(k, h)| {
                let scope = if h.scope == ItemScope::Body { "ALL" } else { "REGION" };
                RingOption {
                    key: data.items.spec(k).label.clone(),
                    label: format!("x{}  {scope}", h.left),
                    enabled: h.enabled,
                    current: false,
                }
            })
            .collect();
    view.layers.push(RingLayer {
        title: "HEAL".into(),
        options,
        selected: if menu.item.is_some() { menu.item } else { menu.ring.selected() },
        pointer: menu.ring.pointer,
        radius: menu.ring.reach,
        chip: CHIP,
        key_size: 17.0,
        focus: menu.item,
        ..default()
    });
    let Some(item) = menu.item.filter(|i| *i < heal.len()) else { return };
    let spec = data.items.spec(&lo.0.kit[item]);
    let options = REGION_ORDER
        .iter()
        .enumerate()
        .map(|(r, z)| {
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
            RingOption { key: z.label().into(), label, enabled: heal[item].regions[r], current: false }
        })
        .collect();
    view.layers.push(RingLayer {
        title: String::new(),
        options,
        selected: menu.regions.selected(),
        pointer: menu.regions.pointer,
        centre: option_offset(item, lo.0.kit.len(), menu.ring.reach),
        radius: menu.regions.reach,
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
        // The chip under the cursor lights up; a dimmed one only gets an outline (it cannot be picked).
        let hovered = layer.selected == Some(chip.1);
        bg.0 = if hovered && opt.enabled { CHIP_SELECTED } else { CHIP_BG };
        *border = BorderColor::all(if opt.current || layer.focus == Some(chip.1) {
            INK
        } else if hovered {
            MUTED
        } else {
            Color::NONE
        });
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
                let at = layer.centre + layer.pointer - Vec2::splat(CURSOR / 2.0);
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

    fn tuning() -> RadialTuning {
        crate::settings::embedded().radial
    }

    fn dead() -> f32 {
        tuning().dead_zone_px
    }

    #[test]
    fn sectors_start_at_the_top_and_go_clockwise() {
        assert_eq!(sector(Vec2::new(0.0, -50.0), 6, dead()), Some(0), "up");
        assert_eq!(sector(Vec2::new(50.0, -30.0), 6, dead()), Some(1), "up and right");
        assert_eq!(sector(Vec2::new(0.0, 50.0), 6, dead()), Some(3), "down");
        assert_eq!(sector(Vec2::new(-50.0, -30.0), 6, dead()), Some(5), "up and left");
        assert_eq!(sector(Vec2::new(50.0, 0.0), 4, dead()), Some(1), "right of four");
        assert_eq!(sector(Vec2::new(3.0, 4.0), 6, dead()), None, "dead zone");
        assert_eq!(sector(Vec2::new(0.0, -50.0), 0, dead()), None);
    }

    /// Every pointer direction picks the option drawn in that direction, for every ring size in use (1 to 8
    /// heal items, 1 to 6 magazines, 4 regions): option `i` is centred at `i * 360 / n` degrees clockwise
    /// from straight up, on screen where +y is down.
    #[test]
    fn every_direction_picks_the_option_drawn_there() {
        for n in 1..=MAX_OPTIONS {
            let width = 360.0 / n as f32;
            for tenth in 0..3600 {
                let deg = tenth as f32 / 10.0;
                // Skip the exact borders between two sectors.
                let off_border = ((deg + width / 2.0) % width).min(width - (deg + width / 2.0) % width);
                if n > 1 && off_border < 0.05 {
                    continue;
                }
                let want = ((deg + width / 2.0) / width) as usize % n;
                let a = deg.to_radians();
                // Clockwise from up on a +y-down screen: up is (0, -1), right is (1, 0).
                let dir = Vec2::new(a.sin(), -a.cos());
                for len in [dead() + 1.0, 100.0, 400.0] {
                    assert_eq!(sector(dir * len, n, dead()), Some(want), "{deg} deg of {n}");
                }
                let drawn = option_offset(want, n, 100.0).normalize();
                assert!(drawn.angle_to(dir).abs().to_degrees() <= width / 2.0 + 1e-3, "{deg} deg of {n}");
            }
            assert_eq!(sector(Vec2::new(1.0, -1.0), n, dead()), None, "dead zone");
        }
    }

    /// The cursor is drawn where it is and can rest on any chip; wherever on a chip it rests, that chip is the
    /// selection (a ring grows when its chips would cross into their neighbours' sectors).
    #[test]
    fn the_chip_under_the_cursor_is_the_selection() {
        let rings = (1..=MAX_OPTIONS).map(|n| (n, Radial::new(n, &tuning()), CHIP, RING_R)).chain([(
            REGION_ORDER.len(),
            Radial::regions(&tuning()),
            REGION_CHIP,
            REGION_R,
        )]);
        for (n, ring, chip, base) in rings {
            assert!(ring.reach >= base && ring.reach < base * 1.5, "{n}: radius {}", ring.reach);
            for i in 0..n {
                let c = option_offset(i, n, ring.reach);
                for (u, v) in (0..=10).flat_map(|u| (0..=10).map(move |v| (u as f32 / 10.0, v as f32 / 10.0))) {
                    let p = c - chip / 2.0 + chip * Vec2::new(u, v);
                    assert_eq!(sector(p, n, dead()), Some(i), "{n}: {p} on chip {i}");
                    if p.length() <= ring.reach {
                        let mut r = ring;
                        r.steer(p);
                        assert_eq!((r.pointer, r.selected()), (p, Some(i)), "{n}: cursor on chip {i}");
                    }
                }
                // Pushing on past a chip leaves the cursor resting on its centre.
                let mut r = ring;
                r.steer(c * 0.5);
                r.steer(c * 3.0);
                assert!((r.pointer - c).length() < 1e-3, "{n}: {} rests on {c}", r.pointer);
            }
        }
        assert_eq!(Radial::new(5, &tuning()).reach, RING_R, "five heal items fit the standard ring");
        assert!(Radial::new(8, &tuning()).reach > RING_R, "eight do not");
    }

    #[test]
    fn pointer_is_clamped_and_turns_quickly() {
        let mut r = Radial::new(6, &tuning());
        r.steer(Vec2::new(0.0, -5000.0));
        assert!((r.pointer.length() - r.reach).abs() < 1e-3);
        assert_eq!(r.selected(), Some(0));
        r.steer(Vec2::new(0.0, 2.0 * r.reach));
        assert_eq!(r.selected(), Some(3), "one ring's width of travel reaches the opposite slot");
    }

    #[test]
    fn the_cursor_moves_the_same_hand_distance_at_any_dpi() {
        let t = tuning();
        assert_eq!(t.px_per_inch, 800.0, "at 800 DPI one count is one px, like a desktop cursor");
        assert_eq!(px_per_count(800, &t), 1.0);
        assert_eq!(px_per_count(1600, &t), 0.5);
        assert_eq!(px_per_count(0, &t), 800.0, "a zero DPI cannot divide by zero");
        // the cursor tuning comes from the data: a faster cursor and a wider dead zone apply
        let fast = RadialTuning { px_per_inch: 1200.0, dead_zone_px: 40.0 };
        assert_eq!(px_per_count(800, &fast), 1.5);
        let mut r = Radial::new(6, &fast);
        r.steer(Vec2::new(0.0, -30.0));
        assert_eq!(r.selected(), None, "inside the wider dead zone");
        r.steer(Vec2::new(0.0, -15.0));
        assert_eq!(r.selected(), Some(0));
    }
}
