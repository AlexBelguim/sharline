//! Colour tokens from `design/ui/mockups/_src/common.css` (`:root`) and the literals the pages repeat.
//! Alphas are the CSS floats, never rounded to a hex byte.

use bevy::prelude::*;

pub const fn hex(rgb: u32) -> Color {
    Color::srgb(((rgb >> 16) & 0xff) as f32 / 255.0, ((rgb >> 8) & 0xff) as f32 / 255.0, (rgb & 0xff) as f32 / 255.0)
}

pub const fn hexa(rgb: u32, a: f32) -> Color {
    Color::srgba(
        ((rgb >> 16) & 0xff) as f32 / 255.0,
        ((rgb >> 8) & 0xff) as f32 / 255.0,
        (rgb & 0xff) as f32 / 255.0,
        a,
    )
}

/// White at an alpha (the mockups' `rgba(255,255,255,a)` ladder).
pub const fn white(a: f32) -> Color {
    Color::srgba(1.0, 1.0, 1.0, a)
}

/// Black at an alpha.
pub const fn black(a: f32) -> Color {
    Color::srgba(0.0, 0.0, 0.0, a)
}

// --- A. CSS variables
// surfaces
pub const BG0: Color = hex(0x07090D);
pub const BG1: Color = hex(0x0C1016);
pub const BG2: Color = hex(0x121821);
pub const PANEL: Color = hexa(0x090C11, 0.70);
pub const PANEL_HI: Color = hexa(0x10151D, 0.82);
pub const PANEL_SOLID: Color = hex(0x10151C);
pub const STROKE: Color = white(0.09);
pub const STROKE_MID: Color = white(0.16);
pub const STROKE_HI: Color = white(0.32);
// text
pub const TEXT_HI: Color = hex(0xF3F0E9);
pub const TEXT: Color = hex(0xD7D4CD);
pub const TEXT_MID: Color = hex(0x9CA2AB);
pub const TEXT_LOW: Color = hex(0x646B75);
// art-bible palette
pub const BONE: Color = hex(0xC4BFB5);
pub const SAND: Color = hex(0xA29076);
pub const IVORY: Color = hex(0xDAD6CB);
pub const TEAL: Color = hex(0x00DACE);
pub const CORAL: Color = hex(0xFF8C7A);
pub const ICE: Color = hex(0xB3EDFF);
// halo tiers (index 0 = unlit)
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
// misc
pub const WARN: Color = hex(0xFFA23A);
pub const GOOD: Color = hex(0x52E5A5);
pub const BAD: Color = hex(0xFF4D5A);

// --- B. semantic aliases
pub const ACCENT_FOCUS: Color = TEAL;
pub const SELECT_FILL: Color = TEXT_HI;
pub const SELECT_INK: Color = BG0;
pub const AMMO_STD: Color = BONE;
pub const AMMO_AP: Color = ICE;
pub const AMMO_RIP: Color = CORAL;
pub const AMMO_SLUG: Color = SAND;
pub const AMMO_SHR: Color = WARN;
pub const AGENT_KESTREL: Color = TEAL;
pub const AGENT_SOLACE: Color = CORAL;
pub const FLESH_TEXT: Color = hex(0xFF6170);
pub const DESTROYED_GREY: Color = hex(0x8A8F98);

// --- C. alpha ladders
pub const W03: Color = white(0.03);
pub const W035: Color = white(0.035);
pub const W04: Color = white(0.04);
pub const W05: Color = white(0.05);
pub const W06: Color = white(0.06);
pub const W07: Color = white(0.07);
pub const W08: Color = white(0.08);
pub const W10: Color = white(0.10);
pub const W12: Color = white(0.12);
pub const W13: Color = white(0.13);
pub const W14: Color = white(0.14);
pub const W15: Color = white(0.15);
pub const W18: Color = white(0.18);
pub const W20: Color = white(0.20);
pub const W70: Color = white(0.70);
pub const K35: Color = black(0.35);
pub const K40: Color = black(0.40);
pub const K45: Color = black(0.45);
pub const K50: Color = black(0.50);
pub const K60: Color = black(0.60);
pub const K85: Color = black(0.85);
/// rgb(5,7,10): shades, scrims and bottom bars.
pub const INK: u32 = 0x05070A;
pub const BOTTOM_BAR: Color = hexa(INK, 0.60);
pub const SCOREBOARD_DIM: Color = hexa(0x040609, 0.62);
pub const MODAL_BACKDROP: Color = black(0.60);

// --- D. opaque specials
pub const MENU_SURFACE: Color = hex(0x141A22);
pub const MODAL_SURFACE: Color = hex(0x11161D);
pub const READY_INK: Color = hex(0x06140D);
pub const ALLY_BTN_INK: Color = hex(0x04140C);
pub const DANGER_INK: Color = hex(0x1B0507);
pub const ICON_CUT: Color = hex(0x0B0E13);
pub const PREVIEW_BG: Color = hex(0x090B0E);
pub const PRIMARY_PRESSED: Color = IVORY;
pub const DANGER_SOLID_HOVER: Color = hex(0xFF6170);

pub fn tier_color(tier: u8) -> Color {
    TIERS[tier.min(4) as usize]
}

/// The colour ammo of a type is named in, everywhere.
pub fn ammo_color(kind: vetf_sim::data::AmmoKind) -> Color {
    use vetf_sim::data::AmmoKind::*;
    match kind {
        Standard => AMMO_STD,
        ArmorPiercing => AMMO_AP,
        Rip => AMMO_RIP,
        Slug => AMMO_SLUG,
        Shrapnel => AMMO_SHR,
    }
}

/// Multiply a colour's alpha (the disabled look uses .35).
pub fn fade(c: Color, a: f32) -> Color {
    let alpha = c.alpha();
    c.with_alpha(alpha * a)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_tokens_match_the_css() {
        let c = TEAL.to_srgba();
        assert!(c.red.abs() < 1e-6 && (c.green - 218.0 / 255.0).abs() < 1e-6 && (c.blue - 206.0 / 255.0).abs() < 1e-6);
        let p = PANEL.to_srgba();
        assert!((p.alpha - 0.70).abs() < 1e-6 && (p.red - 9.0 / 255.0).abs() < 1e-6);
        assert_eq!(tier_color(9), TIERS[4]);
        assert_eq!(tier_color(0), UNLIT);
        assert!((fade(STROKE_HI, 0.35).alpha() - 0.32 * 0.35).abs() < 1e-6);
    }
}
