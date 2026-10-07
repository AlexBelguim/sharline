//! Shared UI style, after `design/ui/mockups/_src/common.css`: colour tokens, the Barlow fonts, text
//! helpers, and the 1080p reference scale. Mockup pixel values map 1:1 to `Val::Px`, because `UiScale` is
//! window height / 1080.

// The whole palette of common.css is here, used or not yet.
#![allow(dead_code)]

use bevy::prelude::*;
use bevy::text::LetterSpacing;
use bevy::window::PrimaryWindow;

// ---------------------------------------------------------------------------------------------- tokens

const fn hex(rgb: u32) -> Color {
    Color::srgb(((rgb >> 16) & 0xff) as f32 / 255.0, ((rgb >> 8) & 0xff) as f32 / 255.0, (rgb & 0xff) as f32 / 255.0)
}

const fn hexa(rgb: u32, a: f32) -> Color {
    Color::srgba(
        ((rgb >> 16) & 0xff) as f32 / 255.0,
        ((rgb >> 8) & 0xff) as f32 / 255.0,
        (rgb & 0xff) as f32 / 255.0,
        a,
    )
}

// surfaces
pub const BG0: Color = hex(0x07090D);
pub const BG1: Color = hex(0x0C1016);
pub const BG2: Color = hex(0x121821);
pub const PANEL: Color = hexa(0x090C11, 0.70);
pub const PANEL_HI: Color = hexa(0x10151D, 0.82);
pub const PANEL_SOLID: Color = hex(0x10151C);
pub const STROKE: Color = Color::srgba(1.0, 1.0, 1.0, 0.09);
pub const STROKE_MID: Color = Color::srgba(1.0, 1.0, 1.0, 0.16);
pub const STROKE_HI: Color = Color::srgba(1.0, 1.0, 1.0, 0.32);
// text
pub const TEXT_HI: Color = hex(0xF3F0E9);
pub const TEXT: Color = hex(0xD7D4CD);
pub const TEXT_MID: Color = hex(0x9CA2AB);
pub const TEXT_LOW: Color = hex(0x646B75);
// art-bible palette
pub const BONE: Color = hex(0xC4BFB5);
pub const TEAL: Color = hex(0x00DACE);
pub const CORAL: Color = hex(0xFF8C7A);
pub const ICE: Color = hex(0xB3EDFF);
// halo tiers (0 = unlit)
pub const TIERS: [Color; 5] = [hex(0x27272C), hex(0xEDF1F6), hex(0x59B3FF), hex(0xC46CFF), hex(0xFFCE50)];
pub const UNLIT: Color = hex(0x27272C);
// teams are relative: ally is always you and your team
pub const ALLY: Color = hex(0x52E5A5);
pub const ENEMY: Color = hex(0xFF4D5A);
// health states
pub const HP_OK: Color = hex(0xE6E2D8);
pub const HP_DMG: Color = hex(0xFFA23A);
pub const HP_CRIT: Color = hex(0xFF3B4E);
pub const HP_DEAD: Color = hex(0x15171B);
pub const BLEED: Color = hex(0xE0162E);
pub const HEAL: Color = hex(0x9CF7C8);
pub const WARN: Color = hex(0xFFA23A);
pub const GOOD: Color = hex(0x52E5A5);
pub const BAD: Color = hex(0xFF4D5A);

pub fn tier_color(tier: u8) -> Color {
    TIERS[tier.min(4) as usize]
}

// ---------------------------------------------------------------------------------------------- fonts

/// Barlow (body) and Barlow Condensed (display, labels, numbers), compiled into the binary. OFL; see
/// `game/assets/fonts/OFL.txt`.
#[derive(Resource, Clone)]
pub struct UiFonts {
    /// Barlow 400, 500, 600, 700.
    body: [Handle<Font>; 4],
    /// Barlow Condensed 500, 600, 700.
    display: [Handle<Font>; 3],
}

macro_rules! font_bytes {
    ($name:literal) => {
        include_bytes!(concat!("../../../assets/fonts/", $name))
    };
}

/// The two families of the mockups.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Face {
    /// Barlow: body copy.
    Body,
    /// Barlow Condensed: titles, labels, numbers, buttons (`--fd`).
    Display,
}

impl UiFonts {
    fn load(fonts: &mut Assets<Font>) -> Self {
        let mut add = |bytes: &[u8]| fonts.add(Font::from_bytes(bytes.to_vec()));
        Self {
            body: [
                add(font_bytes!("Barlow-Regular.ttf")),
                add(font_bytes!("Barlow-Medium.ttf")),
                add(font_bytes!("Barlow-SemiBold.ttf")),
                add(font_bytes!("Barlow-Bold.ttf")),
            ],
            display: [
                add(font_bytes!("BarlowCondensed-Medium.ttf")),
                add(font_bytes!("BarlowCondensed-SemiBold.ttf")),
                add(font_bytes!("BarlowCondensed-Bold.ttf")),
            ],
        }
    }

    /// The file closest to `weight` (400..700) in `face`.
    pub fn handle(&self, face: Face, weight: u16) -> Handle<Font> {
        match face {
            Face::Body => self.body[((weight.clamp(400, 700) - 400) / 100) as usize].clone(),
            Face::Display => self.display[((weight.clamp(500, 700) - 500) / 100) as usize].clone(),
        }
    }

    pub fn font(&self, face: Face, weight: u16, size: f32) -> TextFont {
        TextFont::from_font_size(size).with_font(self.handle(face, weight))
    }

    /// Text in a face, weight, size (px at 1080p), colour and letter spacing (em, like the CSS).
    pub fn text(&self, s: impl Into<String>, face: Face, weight: u16, size: f32, color: Color, em: f32) -> impl Bundle {
        (Text::new(s), self.font(face, weight, size), TextColor(color), LetterSpacing::Px(size * em))
    }

    /// `.lbl`: Barlow Condensed 600, 13 px, 0.14 em, upper case, `--text-mid`.
    pub fn lbl(&self, s: impl Into<String>) -> impl Bundle {
        self.text(s, Face::Display, 600, 13.0, TEXT_MID, 0.14)
    }

    /// `.micro`: Barlow Condensed 600, 11 px, 0.16 em, upper case, `--text-low`.
    pub fn micro(&self, s: impl Into<String>) -> impl Bundle {
        self.text(s, Face::Display, 600, 11.0, TEXT_LOW, 0.16)
    }
}

// ---------------------------------------------------------------------------------------------- layout

/// An absolutely positioned node (px at 1080p; `None` = auto).
pub fn abs(left: Option<f32>, right: Option<f32>, top: Option<f32>, bottom: Option<f32>) -> Node {
    Node {
        position_type: PositionType::Absolute,
        left: left.map_or(Val::Auto, Val::Px),
        right: right.map_or(Val::Auto, Val::Px),
        top: top.map_or(Val::Auto, Val::Px),
        bottom: bottom.map_or(Val::Auto, Val::Px),
        ..default()
    }
}

/// `.panel`: dark translucent, hairline stroke, 2 px radius.
pub fn panel(node: Node) -> impl Bundle {
    panel_bg(node, PANEL)
}

/// A `.panel` with another background.
pub fn panel_bg(node: Node, bg: Color) -> impl Bundle {
    (
        Node { border: UiRect::all(px(1)), border_radius: BorderRadius::all(px(2)), ..node },
        BackgroundColor(bg),
        BorderColor::all(STROKE),
    )
}

/// Reference height of the mockups.
pub const REF_HEIGHT: f32 = 1080.0;

pub struct UiKitPlugin;

impl Plugin for UiKitPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(Update, follow_window_scale);
    }

    fn finish(&self, app: &mut App) {
        let fonts = UiFonts::load(&mut app.world_mut().resource_mut::<Assets<Font>>());
        app.insert_resource(fonts);
    }
}

/// Mockup px are 1080p px: scale the whole UI with the window height.
fn follow_window_scale(windows: Query<&Window, With<PrimaryWindow>>, mut scale: ResMut<UiScale>) {
    let Some(w) = windows.iter().next() else { return };
    let s = (w.height() / REF_HEIGHT).max(0.25);
    if (scale.0 - s).abs() > 1e-3 {
        scale.0 = s;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_tokens_match_the_css() {
        let c = TEAL.to_srgba();
        assert!((c.red - 0.0).abs() < 1e-6 && (c.green - 218.0 / 255.0).abs() < 1e-6);
        assert_eq!(tier_color(9), TIERS[4]);
        assert_eq!(tier_color(0), UNLIT);
    }
}
