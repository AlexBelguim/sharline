//! Quick ring menus (reload magazine pick, later healing). While one is open, mouse movement steers a
//! pointer instead of the view; the sector the pointer is in is the selection. Slot 1 sits at the top and
//! the rest follow clockwise, so the same slot is always in the same direction.

use crate::AppState;
use crate::client::LocalControl;
use bevy::prelude::*;
use lightyear::prelude::Controlled;
use vetf_net::{PlayerLoadout, PlayerWeapon};

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

/// Where option `i` of `n` sits on a ring of radius `r` (screen space, +y down), for drawing.
pub fn option_offset(i: usize, n: usize, r: f32) -> Vec2 {
    let angle = std::f32::consts::TAU * i as f32 / n.max(1) as f32;
    Vec2::new(angle.sin() * r, -angle.cos() * r)
}

// ---------------------------------------------------------------------------------------------- drawing

/// One option on a ring as drawn.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct RingOption {
    /// Big text: the slot number.
    pub key: String,
    /// Small text under it: e.g. the ammo.
    pub label: String,
    /// False draws it dimmed (e.g. a spent magazine).
    pub enabled: bool,
    /// Marked as current (e.g. the magazine in the gun).
    pub current: bool,
}

/// What the ring on screen shows this frame. Filled by the menus that use a ring.
#[derive(Resource, Debug, Clone, Default)]
pub struct RingView {
    pub open: bool,
    pub title: String,
    pub options: Vec<RingOption>,
    pub selected: Option<usize>,
    pub pointer: Vec2,
}

pub struct RadialPlugin;

impl Plugin for RadialPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<RingView>()
            .add_systems(OnEnter(AppState::InGame), spawn_ring)
            .add_systems(Update, (reload_ring, draw_ring).chain().run_if(in_state(AppState::InGame)));
    }
}

/// Ring radius on screen (px) and the size of one option chip.
const RING_R: f32 = 120.0;
const CHIP: Vec2 = Vec2::new(96.0, 58.0);
const MAX_OPTIONS: usize = 8;

const INK: Color = Color::srgb(0.93, 0.94, 0.95);
const MUTED: Color = Color::srgb(0.58, 0.62, 0.68);
const TEAL: Color = Color::srgb(0.0, 0.70, 0.62);
const CHIP_BG: Color = Color::srgba(0.06, 0.07, 0.09, 0.86);
const CHIP_SELECTED: Color = Color::srgba(0.0, 0.42, 0.37, 0.95);

#[derive(Component)]
struct RingRoot;
#[derive(Component)]
struct RingChip(usize);
#[derive(Component)]
struct RingKey(usize);
#[derive(Component)]
struct RingLabel(usize);
#[derive(Component)]
struct RingTitle;
#[derive(Component)]
struct RingPointer;

fn spawn_ring(mut commands: Commands) {
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
    commands.spawn((
        RingTitle,
        Text::new(""),
        TextFont::from_font_size(15.0),
        TextColor(MUTED),
        TextLayout::justify(Justify::Center),
        Node { position_type: PositionType::Absolute, left: px(-80), top: px(-10), width: px(160), ..default() },
        ChildOf(root),
    ));
    commands.spawn((
        RingPointer,
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
                RingChip(i),
                Node {
                    position_type: PositionType::Absolute,
                    width: px(CHIP.x),
                    height: px(CHIP.y),
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::Center,
                    justify_content: JustifyContent::Center,
                    border: UiRect::all(px(2)),
                    border_radius: BorderRadius::all(px(6)),
                    ..default()
                },
                BackgroundColor(CHIP_BG),
                BorderColor::all(Color::NONE),
                ChildOf(root),
            ))
            .id();
        commands.spawn((RingKey(i), Text::new(""), TextFont::from_font_size(24.0), TextColor(INK), ChildOf(chip)));
        commands.spawn((RingLabel(i), Text::new(""), TextFont::from_font_size(13.0), TextColor(MUTED), ChildOf(chip)));
    }
}

/// The magazine radial: one option per slot, its ammo under the number, spent magazines dimmed (you
/// emptied them yourself; nothing says how many rounds the others hold).
fn reload_ring(
    control: Res<LocalControl>,
    me: Query<(&PlayerWeapon, &PlayerLoadout), With<Controlled>>,
    mut view: ResMut<RingView>,
) {
    let (Some(radial), Some((w, lo))) = (control.reload_radial, me.iter().next()) else {
        view.open = false;
        return;
    };
    view.open = true;
    view.title = "MAGAZINE".into();
    view.options =
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
    view.selected = radial.selected();
    view.pointer = radial.pointer;
}

#[allow(clippy::type_complexity)]
fn draw_ring(
    view: Res<RingView>,
    mut root: Query<&mut Visibility, With<RingRoot>>,
    mut chips: Query<(&RingChip, &mut Node, &mut BackgroundColor, &mut BorderColor), Without<RingPointer>>,
    mut keys: Query<(&RingKey, &mut Text, &mut TextColor), Without<RingLabel>>,
    mut labels: Query<(&RingLabel, &mut Text, &mut TextColor), (Without<RingKey>, Without<RingTitle>)>,
    mut title: Query<&mut Text, (With<RingTitle>, Without<RingKey>, Without<RingLabel>)>,
    mut pointer: Query<&mut Node, (With<RingPointer>, Without<RingChip>)>,
) {
    for mut v in &mut root {
        *v = if view.open { Visibility::Inherited } else { Visibility::Hidden };
    }
    if !view.open {
        return;
    }
    let n = view.options.len();
    for (chip, mut node, mut bg, mut border) in &mut chips {
        let Some(opt) = view.options.get(chip.0) else {
            node.display = Display::None;
            continue;
        };
        let at = option_offset(chip.0, n, RING_R) - CHIP / 2.0;
        node.display = Display::Flex;
        node.left = px(at.x);
        node.top = px(at.y);
        let selected = view.selected == Some(chip.0) && opt.enabled;
        bg.0 = if selected { CHIP_SELECTED } else { CHIP_BG };
        *border = BorderColor::all(if opt.current { INK } else { Color::NONE });
    }
    for (k, mut t, mut c) in &mut keys {
        if let Some(opt) = view.options.get(k.0) {
            t.0.clone_from(&opt.key);
            c.0 = if opt.enabled { INK } else { MUTED.with_alpha(0.5) };
        }
    }
    for (l, mut t, mut c) in &mut labels {
        if let Some(opt) = view.options.get(l.0) {
            t.0 = if opt.enabled { opt.label.clone() } else { format!("{} · EMPTY", opt.label) };
            c.0 = if opt.enabled { MUTED } else { MUTED.with_alpha(0.5) };
        }
    }
    for mut t in &mut title {
        t.0.clone_from(&view.title);
    }
    for mut node in &mut pointer {
        let p = view.pointer / POINTER_RADIUS * (RING_R * 0.45) - Vec2::splat(5.0);
        node.left = px(p.x);
        node.top = px(p.y);
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
