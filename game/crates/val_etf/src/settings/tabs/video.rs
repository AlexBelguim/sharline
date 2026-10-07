//! Settings ▸ Video (mockup 08c): DISPLAY and the performance overlay on the left, QUALITY (a preset and
//! the values it sets, under the competitive rule) on the right. Rows the blockout renderer cannot honour
//! yet (render scale, the frame limiter, outlines, bloom, particles, contact shadows, SSR, motion blur,
//! vignette) are drawn dimmed at their values, never hidden.

use super::super::controls::{self as c, Ch, FieldKind, Kit, Live, Num, Tg};
use bevy::prelude::*;

/// What a row's control column holds.
#[derive(Debug, Clone, Copy)]
enum Ctl {
    Seg(Ch),
    /// A dropdown this wide.
    Drop(Ch, f32),
    /// A 400 px slider and its 70 px field.
    Slider(Num),
    /// Switches side by side (gap 12).
    Switches(&'static [Tg]),
}

enum Item {
    /// A card title, or a sub-heading with its top margin, and the micro tag that follows the settings.
    Head(&'static str, f32, Option<Live>),
    /// Label, sub-label, control, and whether the game cannot honour it yet (drawn dimmed).
    Row(&'static str, Option<&'static str>, Ctl, bool),
    Note(&'static str),
}

const DISPLAY: &[Item] = &[
    Item::Head("DISPLAY", 0.0, None),
    Item::Row("WINDOW MODE", None, Ctl::Seg(Ch::WindowMode), false),
    Item::Row("RESOLUTION", None, Ctl::Drop(Ch::Resolution, 240.0), false),
    Item::Row("RENDER SCALE", Some("3D only. UI always renders at native"), Ctl::Slider(Num::RenderScale), true),
    Item::Row("FRAME LIMIT", None, Ctl::Seg(Ch::FrameLimit), true),
    Item::Row("V-SYNC", Some("Bevy PresentMode"), Ctl::Seg(Ch::Vsync), false),
    Item::Row("BRIGHTNESS", None, Ctl::Slider(Num::Brightness), false),
    Item::Head("PERFORMANCE OVERLAY", 12.0, None),
    Item::Row("SHOW", None, Ctl::Seg(Ch::Overlay), false),
];

const QUALITY: &[Item] = &[
    Item::Head("QUALITY", 0.0, Some(Live::PresetMicro)),
    Item::Row("PRESET", None, Ctl::Seg(Ch::Preset), false),
    Item::Row("ANTI-ALIASING", None, Ctl::Seg(Ch::Aa), false),
    Item::Row("SHADOWS", None, Ctl::Seg(Ch::Shadows), false),
    Item::Row("STYLIZED OUTLINES", Some("Ink edges on characters and props"), Ctl::Switches(&[Tg::Outlines]), true),
    Item::Row("BLOOM", Some("Halos, optics, jet cores"), Ctl::Seg(Ch::Bloom), true),
    Item::Row("PARTICLES (BEVY_HANABI)", None, Ctl::Seg(Ch::Particles), true),
    Item::Row("CONTACT SHADOWS · SSR", None, Ctl::Switches(&[Tg::ContactShadows, Tg::Ssr]), true),
    Item::Row("MOTION BLUR · VIGNETTE", None, Ctl::Switches(&[Tg::MotionBlur, Tg::Vignette]), true),
    Item::Note(
        "Competitive rule: settings may never hide halos, hex shards or enemy outlines. \"Low\" only drops their \
         particle count, not their visibility.",
    ),
];

/// Build the tab's two column cards into the pane.
pub fn build(p: &mut ChildSpawnerCommands, k: &Kit) {
    for items in [DISPLAY, QUALITY] {
        super::col(p, |col| c::card(col, 1.0, 14.0, Node::default(), |card| items_into(card, k, items)));
    }
}

fn items_into(card: &mut ChildSpawnerCommands, k: &Kit, items: &[Item]) {
    for (i, item) in items.iter().enumerate() {
        match item {
            // (sync_live writes the micro tag's text)
            Item::Head(title, top, live) => c::h2(card, k, title, live.map(|l| ("", Some(l))), *top),
            // The card's last row has no rule under it.
            Item::Row(label, sub, ctl, dim) => {
                let ruled = i + 1 < items.len();
                c::row(card, k, label, *sub, *dim, ruled, row_min_h(ruled), |r| control(r, k, *ctl, *dim))
            }
            Item::Note(text) => {
                c::note(card, k, &[(*text, false, None)], Node { margin: UiRect::top(px(10)), ..default() })
            }
        }
    }
}

/// Rows are 50 px tall with their rule (a 64 px pitch with the card's 14 px gap). The kit's `row` lays its
/// 1 px rule out below `min_h` (51 px rows), so a ruled row asks for 49.
fn row_min_h(ruled: bool) -> f32 {
    if ruled { 49.0 } else { 50.0 }
}

fn control(r: &mut ChildSpawnerCommands, k: &Kit, ctl: Ctl, dim: bool) {
    match ctl {
        Ctl::Seg(ch) => {
            c::seg(r, k, ch, dim, &[]);
        }
        // A list with nothing else to pick (no monitor data: 'Native' alone) is disabled.
        Ctl::Drop(ch, width) => {
            let single = c::choice_labels(k.ui, k.data, ch, k.s).len() < 2;
            c::dropdown(r, k, ch, width, dim || single);
        }
        Ctl::Slider(n) => c::ctl(r, Node::default(), |x| {
            c::slider(x, k, n, Some(400.0), &[], dim);
            c::field(x, k, FieldKind::Num(n), 70.0, false, dim);
        }),
        Ctl::Switches(ts) => c::ctl(r, Node::default(), |x| {
            for t in ts {
                c::switch(x, k, *t, dim);
            }
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::super::super::controls::{
        DisplayInfo, UiState, choice_labels, get_choice, get_num, get_toggle, range, set_choice, set_num, set_toggle,
    };
    use super::super::super::model::{Resolution, embedded};
    use super::*;

    #[test]
    fn every_video_value_has_one_working_control() {
        let d = embedded();
        let mut s = d.defaults.clone();
        let mut ui = UiState::default();
        let mode = |width, height, hz: u32| Resolution { width, height, refresh_mhz: hz * 1000 };
        ui.display = DisplayInfo {
            modes: vec![mode(2560, 1440, 165), mode(1920, 1080, 144)],
            native: Some(mode(2560, 1440, 165)),
            refresh_hz: Some(165),
        };
        assert_eq!(choice_labels(&ui, d, Ch::FrameLimit, &s), ["60", "144", "165", "240", "OFF"], "as drawn");
        let mut values = 0;
        for item in DISPLAY.iter().chain(QUALITY) {
            let Item::Row(label, _, ctl, _) = item else { continue };
            match *ctl {
                Ctl::Seg(ch) | Ctl::Drop(ch, _) => {
                    for i in 0..choice_labels(&ui, d, ch, &s).len() {
                        set_choice(&mut s, &mut ui, d, ch, i);
                        assert_eq!(get_choice(&s, &ui, d, ch), i, "{label} {i}");
                    }
                    values += 1;
                }
                Ctl::Slider(n) => {
                    let r = range(d, n);
                    for v in [r.min, r.max] {
                        set_num(&mut s, &mut ui, d, n, v);
                        assert!((get_num(&s, &ui, d, n) - v).abs() < 1e-4, "{label}");
                    }
                    values += 1;
                }
                Ctl::Switches(ts) => {
                    for t in ts {
                        for on in [true, false] {
                            set_toggle(&mut s, *t, on);
                            assert_eq!(get_toggle(&s, *t), on, "{label} {t:?}");
                        }
                    }
                    values += ts.len();
                }
            }
        }
        assert_eq!(values, 17, "one control per VideoSettings value");
    }
}
