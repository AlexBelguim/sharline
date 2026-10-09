//! Reusable widgets of the hub mockups (the spec's "components" section). Each returns a bundle (with its
//! children) to spawn; interaction colours come from [`Looks`](super::Looks). Geometry is in 1080p px.

use super::icons::*;
use super::look::*;
use super::text::*;
use super::tokens::*;
use bevy::prelude::*;
use bevy::text::{EditableText, TextCursorStyle};
use bevy::ui::{BoxShadow, ShadowStyle};

pub(super) fn plugin(app: &mut App) {
    app.add_systems(Update, (pulse, kit_controls, kit_segments, sync_segments));
}

// ---------------------------------------------------------------------------------------------- panels

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PanelKind {
    /// `.panel`: PANEL fill.
    Base,
    /// `.panel.hi`: PANEL_HI fill.
    Hi,
    /// Main-menu flyout over the art: PANEL_HI and a 2 px TEAL top border (over-art colours).
    Flyout,
    /// Popover: opaque POPOVER_SURFACE (PANEL_HI's colour), 2 px TEAL top, a deep shadow.
    Popover,
    /// Loadout RESULT: PANEL with a 2 px TEXT_HI top border.
    Result,
    /// Death-recap killer card: PANEL_HI with a 3 px ENEMY left border.
    Killer,
    /// Context menu: MENU_SURFACE, shadow.
    Menu,
    /// Confirm modal: MODAL_SURFACE with a 3 px top border (ENEMY; WARN for restart).
    Modal,
}

/// A panel around `node` (its border, radius and colours are set here).
pub fn panel_of(kind: PanelKind, node: Node) -> impl Bundle {
    let (bg, border) = panel_colors(kind);
    let (top, left) = match kind {
        PanelKind::Flyout | PanelKind::Popover | PanelKind::Result => (2.0, 1.0),
        PanelKind::Killer => (1.0, 3.0),
        PanelKind::Modal => (3.0, 1.0),
        PanelKind::Base | PanelKind::Hi | PanelKind::Menu => (1.0, 1.0),
    };
    let shadow = match kind {
        PanelKind::Popover => BoxShadow(vec![ShadowStyle {
            color: K60,
            x_offset: px(0),
            y_offset: px(20),
            spread_radius: px(0),
            blur_radius: px(60),
        }]),
        PanelKind::Menu => BoxShadow(vec![ShadowStyle {
            color: K60,
            x_offset: px(0),
            y_offset: px(12),
            spread_radius: px(0),
            blur_radius: px(40),
        }]),
        _ => BoxShadow(vec![]),
    };
    let radius = if kind == PanelKind::Modal { 0.0 } else { 2.0 };
    (
        Node {
            border: UiRect { left: px(left), right: px(1), top: px(top), bottom: px(1) },
            border_radius: BorderRadius::all(px(radius)),
            ..node
        },
        BackgroundColor(bg),
        border,
        shadow,
    )
}

/// A panel kind's fill and border colours.
pub fn panel_colors(kind: PanelKind) -> (Color, BorderColor) {
    match kind {
        PanelKind::Base => (PANEL, BorderColor::all(STROKE)),
        PanelKind::Hi => (PANEL_HI, BorderColor::all(STROKE)),
        PanelKind::Flyout => {
            (PANEL_HI_OVER_ART, BorderColor { top: TEAL, ..BorderColor::all(PANEL_HI_OVER_ART_STROKE) })
        }
        PanelKind::Popover => (POPOVER_SURFACE, BorderColor { top: TEAL, ..BorderColor::all(POPOVER_STROKE) }),
        PanelKind::Result => (PANEL, BorderColor { top: TEXT_HI, ..BorderColor::all(STROKE) }),
        PanelKind::Killer => (PANEL_HI, BorderColor { left: ENEMY, ..BorderColor::all(STROKE) }),
        // Over other UI: opaque fills, and their strokes mixed onto them (opaque too).
        PanelKind::Menu => (MENU_SURFACE, BorderColor::all(stroke_on_fill(0xFFFFFF, 0.09, 0x141A22, 1.0, DARK_REF))),
        PanelKind::Modal => (
            MODAL_SURFACE,
            BorderColor { top: ENEMY, ..BorderColor::all(stroke_on_fill(0xFFFFFF, 0.09, 0x11161D, 1.0, DARK_REF)) },
        ),
    }
}

/// `.panel` around `node`.
pub fn panel(node: Node) -> impl Bundle {
    panel_of(PanelKind::Base, node)
}

/// A `.panel` with another background.
pub fn panel_bg(node: Node, bg: Color) -> impl Bundle {
    (
        Node { border: UiRect::all(px(1)), border_radius: BorderRadius::all(px(2)), ..node },
        BackgroundColor(bg),
        BorderColor::all(STROKE),
    )
}

// ---------------------------------------------------------------------------------------------- chrome

/// Screen top bar (Loadout / Settings 84 tall, Lobby 96): full width, 1 px bottom rule, padding 0 48.
pub fn top_bar(height: f32, gap: f32) -> impl Bundle {
    (
        Node {
            position_type: PositionType::Absolute,
            left: px(0),
            right: px(0),
            top: px(0),
            height: px(height),
            padding: UiRect::horizontal(px(48)),
            column_gap: px(gap),
            align_items: AlignItems::Center,
            border: UiRect::bottom(px(1)),
            ..default()
        },
        BorderColor::all(STROKE),
    )
}

/// Screen bottom bar (Settings 80, Lobby 88): 1 px top rule, #05070A at .60.
pub fn bottom_bar(height: f32) -> impl Bundle {
    (
        Node {
            position_type: PositionType::Absolute,
            left: px(0),
            right: px(0),
            bottom: px(0),
            height: px(height),
            padding: UiRect::horizontal(px(48)),
            column_gap: px(12),
            align_items: AlignItems::Center,
            border: UiRect::top(px(1)),
            ..default()
        },
        BorderColor::all(STROKE),
        BackgroundColor(BOTTOM_BAR),
    )
}

/// A flexible spacer (pushes what follows to the end of a row).
pub fn spacer() -> impl Bundle {
    Node { flex_grow: 1.0, ..default() }
}

/// A radial-gradient page background (Loadout, Lobby, Settings), centred at `x`%, `y`%.
pub fn page_background(x: f32, y: f32, stops: [(u32, f32); 3]) -> impl Bundle {
    use bevy::ui::{ColorStop, InterpolationColorSpace, RadialGradient, RadialGradientShape, UiPosition};
    let stops = stops.iter().map(|(c, at)| ColorStop::new(hex(*c), percent(*at))).collect();
    (
        Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
        BackgroundGradient::from(
            RadialGradient::new(UiPosition::TOP_LEFT.at_percent(x, y), RadialGradientShape::FarthestCorner, stops)
                .in_color_space(InterpolationColorSpace::Srgba),
        ),
    )
}

// ---------------------------------------------------------------------------------------------- buttons

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BtnKind {
    Normal,
    Primary,
    Danger,
    DangerSolid,
    Ally,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BtnSize {
    /// 52 tall, padding 0 34, 20 px text.
    L,
    /// 44 tall, padding 0 22, 18 px text.
    M,
    /// 36 tall, padding 0 12, 14 px text.
    S,
    /// 34 tall, padding 0 12, 13 px text.
    Xs,
    /// 36 tall, padding 0 16, 15 px text (settings APPLY, always primary).
    Apply,
}

impl BtnKind {
    pub fn looks(self) -> Looks {
        match self {
            BtnKind::Normal => BTN,
            BtnKind::Primary => BTN_PRIMARY,
            BtnKind::Danger => BTN_DANGER,
            BtnKind::DangerSolid => BTN_DANGER_SOLID,
            BtnKind::Ally => BTN_ALLY,
        }
    }
}

impl BtnSize {
    fn geometry(self) -> (f32, f32, TextRole) {
        match self {
            BtnSize::L => (52.0, 34.0, TextRole::BtnL),
            BtnSize::M => (44.0, 22.0, TextRole::Btn),
            BtnSize::S => (36.0, 12.0, TextRole::BtnS),
            BtnSize::Xs => (34.0, 12.0, TextRole::BtnXs),
            BtnSize::Apply => (36.0, 16.0, TextRole::Apply),
        }
    }
}

/// The node of a `.btn` (use with [`button`] or to build one with custom children).
pub fn button_node(size: BtnSize) -> Node {
    let (h, pad, _) = size.geometry();
    Node {
        height: px(h),
        padding: UiRect::horizontal(px(pad)),
        column_gap: px(10),
        align_items: AlignItems::Center,
        justify_content: JustifyContent::Center,
        border: UiRect::all(px(1)),
        ..default()
    }
}

/// A `.btn` with a label. Add a marker component to it to react to presses.
pub fn button(fonts: &UiFonts, label: &str, kind: BtnKind, size: BtnSize) -> impl Bundle {
    let (_, _, role) = size.geometry();
    let looks = kind.looks();
    (
        Button,
        button_node(size),
        BackgroundColor(looks.idle.bg),
        BorderColor::all(looks.idle.border),
        looks,
        children![(fonts.role_color(role, label, looks.idle.ink), Ink)],
    )
}

/// A `.btn` with a trailing ghost key cap, like `BACK [ESC]`.
pub fn button_with_key(fonts: &UiFonts, label: &str, key: &str, kind: BtnKind, size: BtnSize) -> impl Bundle {
    let (_, _, role) = size.geometry();
    let looks = kind.looks();
    (
        Button,
        button_node(size),
        BackgroundColor(looks.idle.bg),
        BorderColor::all(looks.idle.border),
        looks,
        children![(fonts.role_color(role, label, looks.idle.ink), Ink), keycap(fonts, key, KeyStyle::Ghost, 20.0)],
    )
}

// ---------------------------------------------------------------------------------------------- key caps

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum KeyStyle {
    /// TEXT_HI fill, BG0 text.
    Solid,
    /// Transparent, 1 px STROKE_HI border, TEXT_HI text.
    Ghost,
}

/// A key cap (hints only; never clickable). Heights: 22 default, 20 in buttons, 18 / 16 inline.
pub fn keycap(fonts: &UiFonts, key: &str, style: KeyStyle, height: f32) -> impl Bundle {
    let size = if height >= 20.0 {
        13.0
    } else if height >= 18.0 {
        12.0
    } else {
        11.0
    };
    let (bg, border, ink) = match style {
        KeyStyle::Solid => (TEXT_HI, Color::NONE, BG0),
        KeyStyle::Ghost => (Color::NONE, STROKE_HI, TEXT_HI),
    };
    (
        Node {
            min_width: px(height),
            height: px(height),
            padding: UiRect::horizontal(px(6)),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            border: UiRect::all(px(if style == KeyStyle::Ghost { 1.0 } else { 0.0 })),
            border_radius: BorderRadius::all(px(2)),
            ..default()
        },
        BackgroundColor(bg),
        BorderColor::all(border),
        children![fonts.text(key.to_uppercase(), Face::Display, 700, size, ink, 0.04)],
    )
}

/// One footer hint: key caps 7 px apart, then a HINT label 7 px after them.
pub fn hint(fonts: &UiFonts, keys: &[&str], label: &str) -> impl Bundle {
    let caps: Vec<_> = keys.iter().map(|k| keycap(fonts, k, KeyStyle::Solid, 22.0)).collect();
    (
        Node { column_gap: px(7), align_items: AlignItems::Center, ..default() },
        Children::spawn((SpawnIter(caps.into_iter()), Spawn(fonts.role(TextRole::Hint, label)))),
    )
}

/// A row of hints, 22 px apart.
pub fn hint_row(node: Node, fonts: &UiFonts, hints: &[(&[&str], &str)]) -> impl Bundle {
    let items: Vec<_> = hints.iter().map(|(keys, label)| hint(fonts, keys, label)).collect();
    (
        Node { column_gap: px(22), align_items: AlignItems::Center, ..node },
        Children::spawn(SpawnIter(items.into_iter())),
    )
}

// ---------------------------------------------------------------------------------------------- nav rows

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NavSize {
    /// 66 tall, 44 px (main menu).
    Xl,
    /// 56 tall, 32 px (main menu QUIT).
    Quit,
    /// 60 tall, 36 px (ESC menu).
    L,
    /// 46 tall, 24 px (ESC host / danger rows).
    M,
}

/// A nav row: label 22 px in, an optional right-hand micro label, and a 4 px active bar on the left while
/// it is [`Active`]. `bar` is TEAL on the main menu, TEXT_HI in the ESC menu, ENEMY on danger rows.
pub fn nav_row(fonts: &UiFonts, label: &str, right: &str, size: NavSize, looks: Looks, bar: Color) -> impl Bundle {
    let (h, role) = match size {
        NavSize::Xl => (66.0, TextRole::NavXl),
        NavSize::Quit => (56.0, TextRole::NavQuit),
        NavSize::L => (66.0 - 6.0, TextRole::NavL),
        NavSize::M => (46.0, TextRole::NavM),
    };
    (
        Button,
        Node {
            height: px(h),
            padding: UiRect::left(px(22)),
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::Center,
            ..default()
        },
        looks,
        Active(false),
        children![
            (
                OnBar,
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0),
                    top: px(14),
                    bottom: px(14),
                    width: px(4),
                    ..default()
                },
                BackgroundColor(bar),
                Visibility::Hidden,
            ),
            (fonts.role_color(role, label, looks.idle.ink), Ink),
            fonts.role_color(
                TextRole::NavSmall,
                right,
                if looks.idle.ink == ENEMY { fade(ENEMY, 0.7) } else { TEXT_LOW }
            ),
        ],
    )
}

/// A rotated square (nav diamonds 10, tier boxes 14, slider thumbs 16).
pub fn diamond(size: f32, fill: Color, border: Color) -> impl Bundle {
    (
        Node {
            width: px(size),
            height: px(size),
            border: UiRect::all(px(if border == Color::NONE { 0.0 } else { 1.0 })),
            ..default()
        },
        BackgroundColor(fill),
        BorderColor::all(border),
        UiTransform::from_rotation(Rot2::degrees(45.0)),
    )
}

// ---------------------------------------------------------------------------------------------- tabs, segments

/// An underline tab (join flyout): TAB text; on = TEXT_HI with a 2 px bar at the bottom.
pub fn underline_tab(fonts: &UiFonts, label: &str) -> impl Bundle {
    (
        Button,
        Node { padding: UiRect::axes(px(18), px(10)), ..default() },
        NAV,
        Active(false),
        children![
            (fonts.role(TextRole::Tab, label), Ink),
            (
                OnBar,
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0),
                    right: px(0),
                    bottom: px(0),
                    height: px(2),
                    ..default()
                },
                BackgroundColor(TEXT_HI),
                Visibility::Hidden,
            ),
        ],
    )
}

/// One segment of a segmented control. `fill`: lobby cells share the width evenly.
pub fn segment(fonts: &UiFonts, label: &str, looks: Looks, height: f32, fill: bool) -> impl Bundle {
    (
        Button,
        Node {
            height: px(height),
            padding: UiRect::horizontal(px(14)),
            flex_grow: if fill { 1.0 } else { 0.0 },
            margin: UiRect::left(px(if looks == TOGGLE { 0.0 } else { -1.0 })),
            border: UiRect::all(px(if looks == TOGGLE { 0.0 } else { 1.0 })),
            align_items: AlignItems::Center,
            justify_content: JustifyContent::Center,
            ..default()
        },
        BackgroundColor(looks.idle.bg),
        BorderColor::all(looks.idle.border),
        looks,
        Active(false),
        children![(fonts.role(if looks == TOGGLE { TextRole::Toggle } else { TextRole::Seg }, label), Ink)],
    )
}

/// The value of a segmented control: which option (by index) is on. Put it on the container; give each
/// segment a [`SegOption`].
#[derive(Component, Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct SegValue(pub usize);

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub struct SegOption(pub usize);

// ---------------------------------------------------------------------------------------------- inputs

/// A text field: `.input` (main menu, 56 tall, K45 fill, CODE_XL) or `.inp` (settings, 36 tall, K35).
pub fn text_input(fonts: &UiFonts, role: TextRole, height: f32, fill: Color, max_chars: usize) -> impl Bundle {
    (
        Node {
            height: px(height),
            padding: UiRect::horizontal(px(if height >= 44.0 { 16.0 } else { 10.0 })),
            align_items: AlignItems::Center,
            border: UiRect::all(px(1)),
            ..default()
        },
        BackgroundColor(fill),
        BorderColor::all(STROKE_HI),
        EditableText { allow_newlines: false, max_characters: Some(max_chars), ..default() },
        fonts.role_font(role),
        TextColor(role.spec().color),
        TextCursorStyle { color: TEAL, ..default() },
    )
}

/// A stepper (152x40): − value +. Put [`StepperValue`] on it; the kit handles the buttons.
pub fn stepper(fonts: &UiFonts, value: i32, min: i32, max: i32, step: i32) -> impl Bundle {
    (
        Node { width: px(152), height: px(40), border: UiRect::all(px(1)), ..default() },
        BorderColor::all(STROKE_HI),
        StepperValue { value, min, max, step },
        children![
            (
                Button,
                StepperButton(-1),
                step_cell(40.0),
                children![(fonts.role_color(TextRole::Stepper, "−", TEXT_MID), Ink)],
                NAV
            ),
            (step_cell(72.0), children![(StepperText, fonts.role(TextRole::Stepper, value.to_string()))]),
            (
                Button,
                StepperButton(1),
                step_cell(40.0),
                children![(fonts.role_color(TextRole::Stepper, "+", TEXT_MID), Ink)],
                NAV
            ),
        ],
    )
}

fn step_cell(w: f32) -> Node {
    Node {
        width: px(w),
        height: percent(100),
        align_items: AlignItems::Center,
        justify_content: JustifyContent::Center,
        ..default()
    }
}

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub struct StepperValue {
    pub value: i32,
    pub min: i32,
    pub max: i32,
    pub step: i32,
}

#[derive(Component, Debug, Clone, Copy)]
pub struct StepperButton(pub i32);

#[derive(Component, Debug, Clone, Copy)]
pub struct StepperText;

/// A switch (46x24, radius 12): off W14 with a TEXT_MID knob, on ALLY with a READY_INK knob.
pub fn switch(on: bool) -> impl Bundle {
    (
        Button,
        Switch(on),
        Node { width: px(46), height: px(24), border_radius: BorderRadius::all(px(12)), ..default() },
        BackgroundColor(if on { ALLY } else { W14 }),
        children![(
            SwitchKnob,
            Node {
                position_type: PositionType::Absolute,
                left: px(if on { 25.0 } else { 3.0 }),
                top: px(3),
                width: px(18),
                height: px(18),
                border_radius: BorderRadius::MAX,
                ..default()
            },
            BackgroundColor(if on { READY_INK } else { TEXT_MID }),
        )],
    )
}

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub struct Switch(pub bool);

#[derive(Component, Debug, Clone, Copy)]
pub struct SwitchKnob;

// ---------------------------------------------------------------------------------------------- chips, pips

/// A tag on a card (`SELECTED`: BG0 on TEAL; `IN GUN`: BG0 on TEXT_HI).
pub fn tag(fonts: &UiFonts, label: &str, bg: Color, xs: bool) -> impl Bundle {
    (
        Node { padding: if xs { UiRect::axes(px(5), px(1)) } else { UiRect::axes(px(7), px(2)) }, ..default() },
        BackgroundColor(bg),
        children![fonts.role(if xs { TextRole::TagXs } else { TextRole::Tag }, label)],
    )
}

/// A magazine chip: slot number and short ammo label in the ammo colour. Never a round count.
pub fn mag_chip(
    fonts: &UiFonts,
    slot: usize,
    label: &str,
    kind: vetf_sim::data::AmmoKind,
    in_gun: bool,
) -> impl Bundle {
    (
        Node {
            height: px(22),
            padding: UiRect::horizontal(px(6)),
            column_gap: px(4),
            align_items: AlignItems::Center,
            border: UiRect::all(px(1)),
            border_radius: BorderRadius::all(px(2)),
            ..default()
        },
        BackgroundColor(if in_gun { translucent(TEXT_HI, 0.10) } else { W04 }),
        BorderColor::all(if in_gun { TEXT_HI } else { STROKE_MID }),
        children![
            fonts.text(slot.to_string(), Face::Display, 600, 11.0, TEXT_LOW, 0.0),
            fonts.text(label.to_uppercase(), Face::Display, 700, 13.0, ammo_color(kind), 0.06),
        ],
    )
}

/// A gear-cost chip: "n PTS", or "n PTS · OVER" in BAD.
pub fn cost_text(cost: u32, over: bool) -> String {
    if over { format!("{cost} PTS · OVER") } else { format!("{cost} PTS") }
}

/// Tier pips: `n` pips in the tier colour (images; Bevy has no skew).
pub fn tier_pips(images: &UiImages, tier: u8) -> impl Bundle {
    let c = tier_color(tier);
    let pips: Vec<_> = (0..tier.max(1))
        .map(|_| {
            (ImageNode::new(images.shape(Shape::Pip)).with_color(c), Node { width: px(9), height: px(10), ..default() })
        })
        .collect();
    (
        Node { column_gap: px(3), align_items: AlignItems::Center, ..default() },
        Children::spawn(SpawnIter(pips.into_iter())),
    )
}

/// The arc chip: four pips (head, torso, arms, legs), each in its own arc's tier colour. Unlit arcs get
/// UNLIT with a faint outline. Use it for every per-arc halo summary.
pub fn arc_chip(images: &UiImages, tiers: vetf_sim::ZoneTable<u8>) -> impl Bundle {
    let pips: Vec<_> = vetf_sim::Zone::ALL
        .iter()
        .map(|z| {
            let t = tiers[*z];
            (
                ImageNode::new(images.shape(Shape::Pip)).with_color(if t == 0 { W13 } else { tier_color(t) }),
                Node { width: px(9), height: px(10), ..default() },
            )
        })
        .collect();
    (
        Node { column_gap: px(0), align_items: AlignItems::Center, ..default() },
        Children::spawn(SpawnIter(pips.into_iter())),
    )
}

/// Ammo-tier pips: up to three 5x10 pips in the ammo colour, the rest W12. Standard shows none.
pub fn ammo_pips(images: &UiImages, kind: vetf_sim::data::AmmoKind, tier: u8, max: u8) -> impl Bundle {
    let shown = if kind == vetf_sim::data::AmmoKind::Standard { 0 } else { max.min(3) };
    let pips: Vec<_> = (0..shown)
        .map(|i| {
            (
                ImageNode::new(images.shape(Shape::PipAmmo)).with_color(if i < tier { ammo_color(kind) } else { W12 }),
                Node { width: px(8), height: px(10), ..default() },
            )
        })
        .collect();
    (
        Node { column_gap: px(3), align_items: AlignItems::Center, ..default() },
        Children::spawn(SpawnIter(pips.into_iter())),
    )
}

/// Weight squares: three 7x7 squares; 0-3 lit = None / Light / Medium / Heavy.
pub fn weight_squares(lit: u8) -> impl Bundle {
    let sq: Vec<_> = (0..3)
        .map(|i| {
            (Node { width: px(7), height: px(7), ..default() }, BackgroundColor(if i < lit { TEXT_HI } else { W20 }))
        })
        .collect();
    (
        Node { column_gap: px(2), align_items: AlignItems::Center, ..default() },
        Children::spawn(SpawnIter(sq.into_iter())),
    )
}

/// How many weight squares a class lights.
pub fn weight_lit(w: vetf_sim::data::WeightClass) -> u8 {
    use vetf_sim::data::WeightClass::*;
    match w {
        None => 0,
        Light => 1,
        Medium => 2,
        Heavy => 3,
    }
}

/// A plain bar (track W10) with a fill fraction.
pub fn bar(height: f32, frac: f32, fill: Color) -> impl Bundle {
    (
        Node { height: px(height), flex_grow: 1.0, ..default() },
        BackgroundColor(W10),
        children![(
            BarFill,
            Node { width: percent(frac.clamp(0.0, 1.0) * 100.0), height: percent(100), ..default() },
            BackgroundColor(fill)
        )],
    )
}

#[derive(Component, Debug, Clone, Copy)]
pub struct BarFill;

/// An icon image tinted `color` at `size` px.
pub fn icon(images: &UiImages, i: Icon, size: f32, color: Color) -> impl Bundle {
    (ImageNode::new(images.icon(i)).with_color(color), Node { width: px(size), height: px(size), ..default() })
}

/// A pulsing element (opacity 1 → .35 → 1 over `period` s): status dots, listening key caps.
#[derive(Component, Debug, Clone, Copy)]
pub struct Pulse {
    pub period: f32,
    pub base: Color,
}

fn pulse(time: Res<Time>, mut q: Query<(&Pulse, &mut BackgroundColor)>) {
    let t = time.elapsed_secs();
    for (p, mut bg) in &mut q {
        let phase = (t / p.period.max(0.01)).fract();
        let k = 0.35 + 0.65 * (0.5 + 0.5 * (phase * std::f32::consts::TAU).cos());
        bg.0 = fade(p.base, k);
    }
}

// ---------------------------------------------------------------------------------------------- behaviour

/// Steppers and switches update themselves; screens read [`StepperValue`] / [`Switch`].
pub fn kit_controls(
    presses: Query<(&Interaction, &ChildOf, &StepperButton), Changed<Interaction>>,
    mut steppers: Query<(&mut StepperValue, &Children)>,
    mut texts: Query<&mut Text, With<StepperText>>,
    children: Query<&Children>,
    mut switches: Query<
        (&Interaction, &mut Switch, &mut BackgroundColor, &Children),
        (Changed<Interaction>, Without<Disabled>),
    >,
    mut knobs: Query<(&mut Node, &mut BackgroundColor), (With<SwitchKnob>, Without<Switch>)>,
) {
    for (i, parent, b) in &presses {
        if *i != Interaction::Pressed {
            continue;
        }
        let Ok((mut v, kids)) = steppers.get_mut(parent.parent()) else { continue };
        v.value = (v.value + b.0 * v.step).clamp(v.min, v.max);
        for c in kids.iter() {
            for t in children.get(c).map(|c| c.iter().collect::<Vec<_>>()).unwrap_or_default() {
                if let Ok(mut text) = texts.get_mut(t) {
                    text.0 = v.value.to_string();
                }
            }
        }
    }
    for (i, mut s, mut bg, kids) in &mut switches {
        if *i != Interaction::Pressed {
            continue;
        }
        s.0 = !s.0;
        bg.0 = if s.0 { ALLY } else { W14 };
        for k in kids.iter() {
            if let Ok((mut node, mut kbg)) = knobs.get_mut(k) {
                node.left = px(if s.0 { 25.0 } else { 3.0 });
                kbg.0 = if s.0 { READY_INK } else { TEXT_MID };
            }
        }
    }
}

/// Segmented controls: a press turns its option on and the others off, and sets the container's
/// [`SegValue`].
pub fn kit_segments(
    presses: Query<(Entity, &Interaction, &SegOption, &ChildOf), (Changed<Interaction>, Without<Disabled>)>,
    mut groups: Query<(&mut SegValue, &Children)>,
    mut options: Query<(&SegOption, &mut Active)>,
) {
    for (_, i, opt, parent) in &presses {
        if *i != Interaction::Pressed {
            continue;
        }
        let Ok((mut v, kids)) = groups.get_mut(parent.parent()) else { continue };
        v.0 = opt.0;
        for k in kids.iter() {
            if let Ok((o, mut on)) = options.get_mut(k) {
                let want = o.0 == v.0;
                if on.0 != want {
                    on.0 = want;
                }
            }
        }
    }
}

/// Make every segment of a group match its [`SegValue`] (call after spawning or changing it in code).
pub fn sync_segments(
    groups: Query<(&SegValue, &Children), Changed<SegValue>>,
    mut options: Query<(&SegOption, &mut Active)>,
) {
    for (v, kids) in &groups {
        for k in kids.iter() {
            if let Ok((o, mut on)) = options.get_mut(k) {
                let want = o.0 == v.0;
                if on.0 != want {
                    on.0 = want;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Popovers, context menus and modals sit over other UI (user, item B): their fill and every border are
    /// opaque, so nothing under them shows through.
    #[test]
    fn panels_over_other_ui_are_opaque() {
        for kind in [PanelKind::Popover, PanelKind::Menu, PanelKind::Modal] {
            let (bg, b) = panel_colors(kind);
            assert_eq!(bg.alpha(), 1.0, "{kind:?} fill");
            for c in [b.top, b.right, b.bottom, b.left] {
                assert_eq!(c.alpha(), 1.0, "{kind:?} border");
            }
        }
        let mut w = World::new();
        let e = w.spawn(panel_of(PanelKind::Popover, Node::default())).id();
        assert_eq!(w.get::<BackgroundColor>(e).map(|c| c.0.alpha()), Some(1.0), "the spawned popover");
        assert_eq!(w.get::<BorderColor>(e).map(|c| c.top), Some(TEAL));
    }
}
