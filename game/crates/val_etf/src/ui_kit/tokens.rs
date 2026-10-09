//! Colour tokens from `design/ui/mockups/_src/common.css` (`:root`) and the literals the pages repeat.
//! Alphas are the CSS floats, never rounded to a hex byte.

use bevy::prelude::*;

pub const fn hex(rgb: u32) -> Color {
    let (r, g, b) = rgb_f(rgb);
    Color::srgb(r, g, b)
}

const fn rgb_f(rgb: u32) -> (f32, f32, f32) {
    (((rgb >> 16) & 0xff) as f32 / 255.0, ((rgb >> 8) & 0xff) as f32 / 255.0, (rgb & 0xff) as f32 / 255.0)
}

/// A translucent colour at a CSS alpha, as the mockup shows it over the hub's dark pages and panels
/// (blend-corrected, see "Colour" below).
pub const fn hexa(rgb: u32, a: f32) -> Color {
    hexa_over(rgb, a, DARK_REF)
}

/// A translucent colour at a CSS alpha, as the mockup shows it over a backdrop of sRGB grey `bg` (0..1):
/// [`ART_REF`] for panels over the main-menu art or the live match.
pub const fn hexa_over(rgb: u32, a: f32, bg: f32) -> Color {
    let (r, g, b) = rgb_f(rgb);
    Color::srgba(r, g, b, css_alpha_over(luma(r, g, b), a, bg))
}

/// A colour with exactly this alpha, uncorrected: only for alphas that are already corrected (e.g. from
/// [`scrim_stops`]).
pub const fn hexa_exact(rgb: u32, a: f32) -> Color {
    let (r, g, b) = rgb_f(rgb);
    Color::srgba(r, g, b, a)
}

/// White at an alpha (the mockups' `rgba(255,255,255,a)` ladder, blend-corrected).
pub const fn white(a: f32) -> Color {
    Color::srgba(1.0, 1.0, 1.0, css_alpha(1.0, a))
}

/// Any colour at a CSS alpha, blend-corrected like [`hexa`] (use it instead of `with_alpha` for fills,
/// borders and glows that copy a CSS `rgba(...)`).
pub fn translucent(c: Color, a: f32) -> Color {
    let s = c.to_srgba();
    c.with_alpha(css_alpha(luma(s.red, s.green, s.blue), a))
}

/// A border (`stroke_rgb` at CSS alpha `stroke_a`) on an element whose own fill is `fill_rgb` at `fill_a`, as
/// CSS draws it: CSS paints the fill under the border, Bevy does not (a node's background stops inside its
/// border), so a border on a filled element came out too dark. The result is the CSS composite of stroke
/// over fill as one colour, blend-corrected over a backdrop of sRGB grey `bg`.
pub const fn stroke_on_fill(stroke_rgb: u32, stroke_a: f32, fill_rgb: u32, fill_a: f32, bg: f32) -> Color {
    let (sr, sg, sb) = rgb_f(stroke_rgb);
    let (fr, fg, fb) = rgb_f(fill_rgb);
    let a = 1.0 - (1.0 - stroke_a) * (1.0 - fill_a);
    let k = (1.0 - stroke_a) * fill_a;
    let (r, g, b) = ((stroke_a * sr + k * fr) / a, (stroke_a * sg + k * fg) / a, (stroke_a * sb + k * fb) / a);
    Color::srgba(r, g, b, css_alpha_over(luma(r, g, b), a, bg))
}

/// A white stroke at `stroke_a` on the element's own white fill at `fill_a` (buttons, tiles, list rows):
/// [`stroke_on_fill`] for the white ladders, i.e. white at the combined alpha.
pub const fn white_on(stroke_a: f32, fill_a: f32) -> Color {
    white(1.0 - (1.0 - stroke_a) * (1.0 - fill_a))
}

/// A dark shade (a scrim, a modal backdrop, the menu's shade over the art) at a CSS alpha, over anything:
/// see [`scrim_alpha`].
pub const fn scrim(rgb: u32, a: f32) -> Color {
    hexa_exact(rgb, scrim_alpha(a))
}

// --- Colour
// The mockups are CSS: a translucent colour mixes with what is under it in sRGB values. Bevy blends UI in
// linear light, which makes faint light fills far brighter (white at .03 comes out like CSS white at .18,
// a .09 stroke at 85/255 instead of 35/255) and dark shades lighter. THE KIT IS THE ONLY PLACE THAT CORRECTS
// THIS: every translucent token and helper here already carries the corrected alpha, so screens use them
// as they are and never correct them again.
// - Light or tinted fills and strokes ([`white`], [`hexa`], [`translucent`], [`fade`]): the alpha that gives
//   the CSS result over the hub's dark surfaces ([`DARK_REF`]). Over the menu art or the match use
//   [`hexa_over`] with [`ART_REF`] (a panel over the art: [`PANEL_HI_OVER_ART`]).
// - Dark shades over anything ([`scrim`], [`scrim_stops`]): a dark overlay scales what is under it, so one
//   correction fits every backdrop.
// - Opaque colours, and dark fills within .02 of the reference grey (PANEL), are unchanged.

/// The dark pages and panels of the hub (sRGB grey 0.05): the reference backdrop of [`hexa`] and [`white`].
pub const DARK_REF: f32 = 0.05;
/// A mid grey: the reference backdrop for panels over the main-menu art (and the live match view).
pub const ART_REF: f32 = 120.0 / 255.0;

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

const fn clamp01(v: f64) -> f32 {
    (if v < 0.0 {
        0.0
    } else if v > 1.0 {
        1.0
    } else {
        v
    }) as f32
}

/// The alpha that makes a colour of sRGB luma `lum` at CSS alpha `a` look like the mockup once Bevy blends
/// it in linear light over the hub's dark surfaces ([`DARK_REF`]).
pub const fn css_alpha(lum: f32, a: f32) -> f32 {
    css_alpha_over(lum, a, DARK_REF)
}

/// [`css_alpha`] over a backdrop of sRGB grey `bg`. A colour within .02 of the backdrop is left alone.
pub const fn css_alpha_over(lum: f32, a: f32, bg: f32) -> f32 {
    let (c, a, bg) = (lum as f64, a as f64, bg as f64);
    let d = c - bg;
    if (d < 0.02 && d > -0.02) || a <= 0.0 || a >= 1.0 {
        return a as f32;
    }
    let (lb, lc) = (to_linear(bg), to_linear(c));
    clamp01((to_linear(bg + a * d) - lb) / (lc - lb))
}

/// The alpha for a dark shade at CSS alpha `a`: CSS keeps `1 - a` of the backdrop's sRGB value, which is
/// `to_linear(1 - a)` of its linear value (exact over white, close over darker backdrops).
pub const fn scrim_alpha(a: f32) -> f32 {
    if a <= 0.0 || a >= 1.0 {
        return a;
    }
    clamp01(1.0 - to_linear(1.0 - a as f64))
}

/// A CSS shade gradient's stops `(position %, alpha)` for Bevy: resampled every `step` % (so the curve
/// holds between the CSS stops too) and converted with [`scrim_alpha`]. Build the colours with
/// [`hexa_exact`].
pub fn scrim_stops(stops: &[(f32, f32)], step: f32) -> Vec<(f32, f32)> {
    let css = |t: f32| {
        let i = stops.iter().rposition(|(p, _)| *p <= t).unwrap_or(0);
        match (stops.get(i), stops.get(i + 1)) {
            (Some((p0, a0)), Some((p1, a1))) => a0 + (a1 - a0) * ((t - p0) / (p1 - p0)).clamp(0.0, 1.0),
            (Some((_, a)), None) => *a,
            _ => 0.0,
        }
    };
    let end = stops.last().map_or(0.0, |s| s.0);
    let n = (end / step).ceil() as usize;
    (0..=n).map(|k| (k as f32 * step).min(end)).map(|t| (t, scrim_alpha(css(t)))).collect()
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
/// PANEL_HI over the main-menu art (the PLAY flyouts).
pub const PANEL_HI_OVER_ART: Color = hexa_over(0x10151D, 0.82, ART_REF);
/// The STROKE border of a PANEL_HI panel over the shaded menu art (the PLAY flyouts), see
/// [`stroke_on_fill`].
pub const PANEL_HI_OVER_ART_STROKE: Color = stroke_on_fill(0xFFFFFF, 0.09, 0x10151D, 0.82, DARK_REF);
pub const PANEL_SOLID: Color = hex(0x10151C);
/// Popovers, panels and tooltips that sit over other UI are opaque (user, item B: the cards under the attachment
/// list showed through PANEL_HI's .82): PANEL_HI's colour at full alpha.
pub const POPOVER_SURFACE: Color = hex(0x10151D);
/// A popover's STROKE border, mixed onto its opaque fill (opaque too).
pub const POPOVER_STROKE: Color = stroke_on_fill(0xFFFFFF, 0.09, 0x10151D, 1.0, DARK_REF);
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
/// Over the live match.
pub const SCOREBOARD_DIM: Color = scrim(0x040609, 0.62);
/// Over whatever screen opened the modal.
pub const MODAL_BACKDROP: Color = scrim(0x000000, 0.60);

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
        let r = DARK_REF as f64;
        for a in [0.03_f32, 0.06, 0.12, 0.16, 0.32] {
            let css = r + a as f64 * (1.0 - r);
            let bevy = enc(dec(r) + white(a).alpha() as f64 * (1.0 - dec(r)));
            assert!((css - bevy).abs() < 1e-3, "white {a}: css {css} bevy {bevy}");
        }
        assert!(W03.alpha() < 0.005, "white .03 is a very faint fill in linear light");
        assert_eq!(white(1.0).alpha(), 1.0);
        assert_eq!(translucent(Color::WHITE, 0.12).alpha(), W12.alpha());
    }

    #[test]
    fn panels_over_the_art_blend_like_the_css() {
        let enc = |l: f64| if l <= 0.0031308 { l * 12.92 } else { 1.055 * l.powf(1.0 / 2.4) - 0.055 };
        let dec = |s: f64| if s <= 0.04045 { s / 12.92 } else { ((s + 0.055) / 1.055).powf(2.4) };
        let a = PANEL_HI_OVER_ART.alpha() as f64;
        assert!(a > 0.82 && a < 0.97, "a dark fill must be more opaque over bright art: {a}");
        let p = PANEL_HI_OVER_ART.to_srgba();
        let c = (0.2126 * p.red + 0.7152 * p.green + 0.0722 * p.blue) as f64;
        let bg = ART_REF as f64;
        let css = 0.82 * c + 0.18 * bg;
        let bevy = enc(a * dec(c) + (1.0 - a) * dec(bg));
        assert!((css - bevy).abs() < 1e-3, "{css} vs {bevy}");
        assert_eq!(hexa_over(0x10151D, 1.0, ART_REF).alpha(), 1.0, "opaque stays opaque");
    }

    #[test]
    fn borders_include_the_fill_css_draws_under_them() {
        let c = PANEL_HI_OVER_ART_STROKE.to_srgba();
        // .09 white over rgba(16,21,29,.82): mostly opaque, a little lighter than the fill.
        assert!(c.alpha > 0.7 && c.alpha < 0.9, "{}", c.alpha);
        assert!(c.red > 16.0 / 255.0 && c.red < 0.25, "{}", c.red);
        let plain = stroke_on_fill(0xFFFFFF, 0.09, 0x10151D, 0.0, DARK_REF);
        assert!((plain.alpha() - STROKE.alpha()).abs() < 1e-6, "no fill: a plain stroke");
        // A .16 stroke on a .06 fill is white at 1 - .84 x .94.
        assert!((white_on(0.16, 0.06).alpha() - white(0.2104).alpha()).abs() < 1e-6);
        assert!(white_on(0.16, 0.06).alpha() > STROKE_MID.alpha());
    }

    #[test]
    fn scrims_darken_like_the_css() {
        let dec = |s: f64| if s <= 0.04045 { s / 12.92 } else { ((s + 0.055) / 1.055).powf(2.4) };
        // Over white, CSS keeps (1 - a) of the sRGB value; Bevy keeps (1 - a') of the linear value.
        for a in [0.35_f32, 0.6, 0.85, 0.96] {
            let kept = 1.0 - scrim_alpha(a) as f64;
            assert!((kept - dec(1.0 - a as f64)).abs() < 1e-6, "{a}");
            assert!(scrim_alpha(a) > a, "a dark shade needs more alpha in linear light");
        }
        assert_eq!(scrim_alpha(0.0), 0.0);
        assert_eq!(scrim_alpha(1.0), 1.0);
        assert_eq!(MODAL_BACKDROP.alpha(), scrim_alpha(0.60));
        let s = scrim_stops(&[(0.0, 0.96), (30.0, 0.88), (56.0, 0.35), (72.0, 0.0)], 2.0);
        assert_eq!(s.first().map(|x| x.0), Some(0.0));
        assert_eq!(s.last(), Some(&(72.0, 0.0)), "clear from 72 %");
        assert!(s.windows(2).all(|w| w[1].1 <= w[0].1 + 1e-6), "never darker to the right");
        let at56 = s.iter().find(|x| x.0 == 56.0).unwrap().1;
        assert!((at56 - scrim_alpha(0.35)).abs() < 1e-6);
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
