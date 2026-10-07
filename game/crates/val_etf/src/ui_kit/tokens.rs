//! Colour tokens from `design/ui/mockups/_src/common.css` (`:root`) and the literals the pages repeat.
//! Alphas are the CSS floats, never rounded to a hex byte.

use bevy::prelude::*;

pub const fn hex(rgb: u32) -> Color {
    Color::srgb(((rgb >> 16) & 0xff) as f32 / 255.0, ((rgb >> 8) & 0xff) as f32 / 255.0, (rgb & 0xff) as f32 / 255.0)
}

/// A translucent colour at a CSS alpha (blend-corrected, see [`css_alpha`]).
pub const fn hexa(rgb: u32, a: f32) -> Color {
    let (r, g, b) =
        (((rgb >> 16) & 0xff) as f32 / 255.0, ((rgb >> 8) & 0xff) as f32 / 255.0, (rgb & 0xff) as f32 / 255.0);
    Color::srgba(r, g, b, css_alpha(luma(r, g, b), a))
}

/// White at an alpha (the mockups' `rgba(255,255,255,a)` ladder, blend-corrected, see [`css_alpha`]).
pub const fn white(a: f32) -> Color {
    Color::srgba(1.0, 1.0, 1.0, css_alpha(1.0, a))
}

/// Any colour at a CSS alpha, blend-corrected like [`hexa`] (use it instead of `with_alpha` for fills,
/// borders and glows that copy a CSS `rgba(...)`).
pub fn translucent(c: Color, a: f32) -> Color {
    let s = c.to_srgba();
    c.with_alpha(css_alpha(luma(s.red, s.green, s.blue), a))
}

// --- Blending
// The mockups are CSS: a translucent colour mixes with what is under it in sRGB values. Bevy blends UI in
// linear light, which makes faint fills over the hub's dark surfaces far brighter (white at .03 comes out like
// CSS white at .18). Translucent tokens therefore carry the alpha that gives the CSS result over a reference
// dark surface: sRGB grey 0.05, the hub's pages and panels. Opaque colours and dark-on-dark scrims are
// unchanged.
const BLEND_REF: f64 = 0.05;

const fn fifth_root(v: f64) -> f64 {
    let mut y = 1.0;
    let mut i = 0;
    while i < 64 {
        let y4 = y * y * y * y;
        y = (4.0 * y + v / y4) / 5.0;
        i += 1;
    }
    y
}

/// sRGB -> linear light (const: x^2.4 as the fifth root of x^12).
const fn to_linear(x: f64) -> f64 {
    if x <= 0.04045 {
        x / 12.92
    } else {
        let b = (x + 0.055) / 1.055;
        let b4 = b * b * b * b;
        fifth_root(b4 * b4 * b4)
    }
}

const fn luma(r: f32, g: f32, b: f32) -> f32 {
    0.2126 * r + 0.7152 * g + 0.0722 * b
}

/// The alpha that makes a colour of sRGB luma `lum` at CSS alpha `a` look like the mockup once Bevy blends
/// it in linear light over the hub's dark surfaces.
pub const fn css_alpha(lum: f32, a: f32) -> f32 {
    let (c, a) = (lum as f64, a as f64);
    let d = c - BLEND_REF;
    if (d < 0.02 && d > -0.02) || a <= 0.0 || a >= 1.0 {
        return a as f32;
    }
    let (lb, lc) = (to_linear(BLEND_REF), to_linear(c));
    let out = (to_linear(BLEND_REF + a * d) - lb) / (lc - lb);
    (if out < 0.0 {
        0.0
    } else if out > 1.0 {
        1.0
    } else {
        out
    }) as f32
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

/// Multiply a colour's alpha (the disabled look uses .35). An opaque colour gets the CSS-opacity look
/// (blend-corrected like [`translucent`]).
pub fn fade(c: Color, a: f32) -> Color {
    let alpha = c.alpha();
    if alpha >= 0.999 { translucent(c, a) } else { c.with_alpha(alpha * a) }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Linear-light blending with the corrected alpha lands where CSS (sRGB) blending lands.
    #[test]
    fn translucent_tokens_blend_like_the_css() {
        let enc = |l: f64| if l <= 0.0031308 { l * 12.92 } else { 1.055 * l.powf(1.0 / 2.4) - 0.055 };
        let dec = |s: f64| if s <= 0.04045 { s / 12.92 } else { ((s + 0.055) / 1.055).powf(2.4) };
        assert!((to_linear(0.5) - dec(0.5)).abs() < 1e-9);
        for a in [0.03_f32, 0.06, 0.12, 0.16, 0.32] {
            let css = BLEND_REF + a as f64 * (1.0 - BLEND_REF);
            let bevy = enc(dec(BLEND_REF) + white(a).alpha() as f64 * (1.0 - dec(BLEND_REF)));
            assert!((css - bevy).abs() < 1e-3, "white {a}: css {css} bevy {bevy}");
        }
        assert!(W03.alpha() < 0.005, "white .03 is a very faint fill in linear light");
        assert_eq!(white(1.0).alpha(), 1.0);
        assert_eq!(translucent(Color::WHITE, 0.12).alpha(), W12.alpha());
    }

    #[test]
    fn hex_tokens_match_the_css() {
        let c = TEAL.to_srgba();
        assert!(c.red.abs() < 1e-6 && (c.green - 218.0 / 255.0).abs() < 1e-6 && (c.blue - 206.0 / 255.0).abs() < 1e-6);
        let p = PANEL.to_srgba();
        assert!((p.alpha - 0.70).abs() < 1e-6 && (p.red - 9.0 / 255.0).abs() < 1e-6, "dark on dark is unchanged");
        assert_eq!(tier_color(9), TIERS[4]);
        assert_eq!(tier_color(0), UNLIT);
        assert!((fade(STROKE_HI, 0.35).alpha() - STROKE_HI.alpha() * 0.35).abs() < 1e-6);
    }
}
