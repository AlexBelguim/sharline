//! Interaction styling shared by every clickable element: idle, hover and "on" (selected / active)
//! looks, plus the disabled look (every colour at .35, no hover). State changes are instant, as in the
//! mockups.
//!
//! An element carries [`Looks`] and optionally [`Active`] / [`Disabled`]. Its background and border follow
//! the look; descendants marked [`Ink`] take the look's text colour, and descendants marked [`OnBar`] are
//! shown only while the element is on (the nav rows' active bar).

use super::tokens::*;
use bevy::prelude::*;
use bevy::ui::InteractionDisabled;

/// Colours of one state.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Look {
    pub bg: Color,
    pub border: Color,
    pub ink: Color,
}

impl Look {
    pub const fn new(bg: Color, border: Color, ink: Color) -> Self {
        Self { bg, border, ink }
    }
}

/// The three looks of an element.
#[derive(Component, Debug, Clone, Copy, PartialEq)]
pub struct Looks {
    pub idle: Look,
    pub hover: Look,
    pub on: Look,
}

impl Looks {
    pub const fn new(idle: Look, hover: Look, on: Look) -> Self {
        Self { idle, hover, on }
    }

    /// Text-only element (nav rows, tabs): transparent box, ink changes.
    pub const fn ink(idle: Color, hover: Color, on: Color) -> Self {
        Self {
            idle: Look::new(Color::NONE, Color::NONE, idle),
            hover: Look::new(Color::NONE, Color::NONE, hover),
            on: Look::new(Color::NONE, Color::NONE, on),
        }
    }
}

/// Selected / active / checked.
#[derive(Component, Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct Active(pub bool);

/// Not usable: drawn at .35, no hover, skipped by keyboard navigation.
#[derive(Component, Debug, Default, Clone, Copy)]
pub struct Disabled;

/// Text (or icon) that takes its element's ink colour.
#[derive(Component, Debug, Default, Clone, Copy)]
pub struct Ink;

/// Shown only while its element is on.
#[derive(Component, Debug, Default, Clone, Copy)]
pub struct OnBar;

pub const DISABLED_ALPHA: f32 = 0.35;

pub(super) fn plugin(app: &mut App) {
    app.add_systems(PostUpdate, (sync_disabled, apply_looks).chain().before(bevy::ui::UiSystems::Prepare));
}

/// Keep bevy's InteractionDisabled marker in step with ours (no hover or press while disabled).
fn sync_disabled(
    mut commands: Commands,
    added: Query<Entity, (Added<Disabled>, Without<InteractionDisabled>)>,
    mut removed: RemovedComponents<Disabled>,
) {
    for e in &added {
        commands.entity(e).insert(InteractionDisabled);
    }
    for e in removed.read() {
        if let Ok(mut ec) = commands.get_entity(e) {
            ec.remove::<InteractionDisabled>();
        }
    }
}

#[allow(clippy::type_complexity)]
fn apply_looks(
    elements: Query<
        (Entity, &Looks, Option<&Interaction>, Option<&Active>, Has<Disabled>),
        Or<(Changed<Looks>, Changed<Interaction>, Changed<Active>, Added<Disabled>)>,
    >,
    mut removed: RemovedComponents<Disabled>,
    all: Query<(Entity, &Looks, Option<&Interaction>, Option<&Active>, Has<Disabled>)>,
    mut boxes: Query<(Option<&mut BackgroundColor>, Option<&mut BorderColor>)>,
    children: Query<&Children>,
    mut inks: Query<(&mut TextColor, Option<&LookOwner>), With<Ink>>,
    mut icon_inks: Query<&mut ImageNode, (With<Ink>, Without<TextColor>)>,
    mut bars: Query<&mut Visibility, With<OnBar>>,
    owners: Query<(), With<Looks>>,
) {
    let mut todo: Vec<_> = elements.iter().collect();
    for e in removed.read() {
        if let Ok(item) = all.get(e) {
            todo.push(item);
        }
    }
    for (entity, looks, interaction, on, disabled) in todo {
        let on = on.is_some_and(|o| o.0);
        let hovered = matches!(interaction, Some(Interaction::Hovered | Interaction::Pressed));
        let mut look = if on {
            looks.on
        } else if hovered && !disabled {
            looks.hover
        } else {
            looks.idle
        };
        if disabled {
            look = Look::new(
                fade(look.bg, DISABLED_ALPHA),
                fade(look.border, DISABLED_ALPHA),
                fade(look.ink, DISABLED_ALPHA),
            );
        }
        if let Ok((bg, border)) = boxes.get_mut(entity) {
            if let Some(mut bg) = bg {
                bg.0 = look.bg;
            }
            if let Some(mut border) = border {
                *border = BorderColor::all(look.border);
            }
        }
        // Ink and bars in the subtree, stopping at nested elements that have their own looks.
        let mut stack: Vec<Entity> = children.get(entity).map(|c| c.iter().collect()).unwrap_or_default();
        while let Some(e) = stack.pop() {
            if owners.contains(e) {
                continue;
            }
            if let Ok((mut c, owner)) = inks.get_mut(e)
                && owner.is_none_or(|o| o.0 == entity)
            {
                c.0 = look.ink;
            }
            if let Ok(mut img) = icon_inks.get_mut(e) {
                img.color = look.ink;
            }
            if let Ok(mut vis) = bars.get_mut(e) {
                *vis = if on { Visibility::Inherited } else { Visibility::Hidden };
            }
            if let Ok(c) = children.get(e) {
                stack.extend(c.iter());
            }
        }
    }
}

/// Optional: pin an [`Ink`] to a specific element when nesting is ambiguous.
#[derive(Component, Debug, Clone, Copy)]
pub struct LookOwner(pub Entity);

// ---------------------------------------------------------------------------------------------- presets

/// `.btn`: W06 fill, STROKE_MID border; hover W12 / STROKE_HI.
pub const BTN: Looks = Looks::new(
    Look::new(W06, STROKE_MID, TEXT_HI),
    Look::new(W12, STROKE_HI, TEXT_HI),
    Look::new(W12, STROKE_HI, TEXT_HI),
);
/// `.btn.primary`: TEXT_HI fill and border, BG0 text; hover white.
pub const BTN_PRIMARY: Looks = Looks::new(
    Look::new(TEXT_HI, TEXT_HI, BG0),
    Look::new(Color::WHITE, Color::WHITE, BG0),
    Look::new(PRIMARY_PRESSED, PRIMARY_PRESSED, BG0),
);
/// `.btn.danger`: ENEMY text and a .45 ENEMY border.
pub const BTN_DANGER: Looks = Looks::new(
    Look::new(W06, hexa(0xFF4D5A, 0.45), ENEMY),
    Look::new(W12, hexa(0xFF4D5A, 0.70), ENEMY),
    Look::new(W12, hexa(0xFF4D5A, 0.70), ENEMY),
);
/// `.btn.danger-solid`.
pub const BTN_DANGER_SOLID: Looks = Looks::new(
    Look::new(ENEMY, ENEMY, DANGER_INK),
    Look::new(DANGER_SOLID_HOVER, DANGER_SOLID_HOVER, DANGER_INK),
    Look::new(DANGER_SOLID_HOVER, DANGER_SOLID_HOVER, DANGER_INK),
);
/// `.btn.ally` (READY).
pub const BTN_ALLY: Looks = Looks::new(
    Look::new(ALLY, ALLY, ALLY_BTN_INK),
    Look::new(ALLY, ALLY, ALLY_BTN_INK),
    Look::new(ALLY, ALLY, ALLY_BTN_INK),
);
/// Selectable tiles (slot, mag, core cards): STROKE_MID / W03, hover STROKE_HI / W06, on TEAL / TEAL .08.
pub const TILE: Looks = Looks::new(
    Look::new(W03, STROKE_MID, TEXT_HI),
    Look::new(W06, STROKE_HI, TEXT_HI),
    Look::new(hexa(0x00DACE, 0.08), TEAL, TEAL),
);
/// Segments (settings / lobby): STROKE_MID border; on TEXT_HI fill, BG0 ink.
pub const SEG: Looks = Looks::new(
    Look::new(Color::NONE, STROKE_MID, TEXT_MID),
    Look::new(Color::NONE, STROKE_HI, TEXT_HI),
    Look::new(TEXT_HI, TEXT_HI, BG0),
);
/// The main-menu toggle's segments (no borders).
pub const TOGGLE: Looks = Looks::new(
    Look::new(Color::NONE, Color::NONE, TEXT_MID),
    Look::new(Color::NONE, Color::NONE, TEXT_HI),
    Look::new(TEXT_HI, TEXT_HI, BG0),
);
/// Preset chips (Loadout A/B/C).
pub const CHIP: Looks = Looks::new(
    Look::new(Color::NONE, STROKE_MID, TEXT_MID),
    Look::new(W12, STROKE_HI, TEXT_HI),
    Look::new(TEXT_HI, TEXT_HI, BG0),
);
/// List rows: hover W05, selected W08.
pub const LIST_ROW: Looks = Looks::new(
    Look::new(Color::NONE, STROKE, TEXT_HI),
    Look::new(W05, STROKE, TEXT_HI),
    Look::new(W08, STROKE, TEXT_HI),
);
/// Nav rows and text tabs: TEXT_MID, hover / on TEXT_HI.
pub const NAV: Looks = Looks::ink(TEXT_MID, TEXT_HI, TEXT_HI);
/// The main menu's QUIT row.
pub const NAV_QUIT: Looks = Looks::ink(TEXT_LOW, TEXT_HI, TEXT_HI);
/// The ESC menu's danger rows.
pub const NAV_DANGER: Looks = Looks::ink(ENEMY, ENEMY, ENEMY);
