//! Settings ▸ AUDIO (mockup 08d): the volume mix as seven meters, the output device and mix, and the gameplay
//! cues. `sound.rs` applies them as they change: MASTER, the category sliders (a slider coming to rest plays a
//! sample of its category), SHIELD-HIT SOUND, HEADSHOT SOUND, LOW-MAG CUE and PLAY IN BACKGROUND. The output
//! device and the mix are dimmed, because Bevy plays on the system default device only and there is no
//! compressor yet. The low-mag cue is approximate by design: it never gives away an exact count.

use super::super::controls::{
    Ch, FieldKind, Kit, Num, Tg, card, dropdown, field, glyph_text, h2, note, row, seg, slider, switch,
};
use crate::ui_kit::{self as kit, TextRole};
use bevy::prelude::*;

/// The volume rows in `Num::Vol` order: label and sub-label.
const VOLUMES: [(&str, Option<&str>); 7] = [
    ("MASTER", None),
    ("WEAPONS", None),
    ("FOOTSTEPS & MOVEMENT", Some("Jetpack, slide, zipline")),
    ("ABILITIES & HALOS", None),
    ("HIT AND KILL SOUNDS", None),
    ("INTERFACE", None),
    ("MUSIC", Some("Menus and match end only")),
];

pub fn build(p: &mut ChildSpawnerCommands, k: &Kit) {
    super::col(p, |c| {
        card(c, 1.0, 14.0, Node::default(), |c| {
            h2(c, k, "VOLUME", None, 0.0);
            for (i, (label, sub)) in VOLUMES.iter().enumerate() {
                let last = i + 1 == VOLUMES.len();
                row(c, k, label, *sub, false, !last, 50.0, |r| meter(r, k, Num::Vol(i as u8)));
            }
        });
    });
    super::col(p, |c| {
        card(c, 1.0, 14.0, Node::default(), |c| {
            h2(c, k, "OUTPUT & CUES", None, 0.0);
            row(c, k, "OUTPUT DEVICE", None, true, true, 50.0, |r| dropdown(r, k, Ch::OutputDevice, 300.0, true));
            row(c, k, "MIX", None, true, true, 50.0, |r| {
                seg(r, k, Ch::Mix, true, &[]);
            });
            glyph_row(c, k, "SHIELD-HIT SOUND", "Glassy \"tink\" per tier, pitch rises T1 → T4", |r| {
                switch(r, k, Tg::ShieldHit, false)
            });
            row(c, k, "HEADSHOT SOUND", None, false, true, 50.0, |r| switch(r, k, Tg::Headshot, false));
            row(
                c,
                k,
                "LOW-MAG CUE",
                Some("Lighter trigger click in roughly the last 15\u{a0}% (open question)"),
                false,
                true,
                50.0,
                |r| {
                    seg(r, k, Ch::LowMag, false, &[]);
                },
            );
            row(c, k, "PLAY IN BACKGROUND", None, false, true, 50.0, |r| switch(r, k, Tg::PlayInBg, false));
            note(
                c,
                k,
                &[(
                    "No voice chat in the prototype. Friends use Discord or similar. Text chat is in the lobby and in \
                     match.",
                    false,
                    None,
                )],
                Node { margin: UiRect::top(px(10)), ..default() },
            );
        });
    });
}

/// `.meter`: a 340 px slider and its 64 px number field, gap 10.
fn meter(p: &mut ChildSpawnerCommands, k: &Kit, n: Num) {
    p.spawn(Node { align_items: AlignItems::Center, column_gap: px(10), ..default() }).with_children(|m| {
        slider(m, k, n, Some(340.0), &[], false);
        field(m, k, FieldKind::Num(n), 64.0, false, false);
    });
}

/// A bordered `row` whose sub-label takes its arrows from the symbol font (Barlow has no '→').
fn glyph_row(p: &mut ChildSpawnerCommands, k: &Kit, label: &str, sub: &str, f: impl FnOnce(&mut ChildSpawnerCommands)) {
    p.spawn((
        Node {
            display: Display::Grid,
            grid_template_columns: vec![GridTrack::px(230.0), GridTrack::flex(1.0)],
            align_items: AlignItems::Center,
            min_height: px(50),
            border: UiRect::bottom(px(1)),
            flex_shrink: 0.0,
            ..default()
        },
        BorderColor::all(kit::STROKE),
    ))
    .with_children(|r| {
        r.spawn(Node { flex_direction: FlexDirection::Column, padding: UiRect::right(px(12)), ..default() })
            .with_children(|l| {
                l.spawn(k.fonts.role_color(TextRole::RowLabel, label, kit::TEXT));
                glyph_text(l, k, TextRole::Sub, sub, kit::TEXT_MID, Node { margin: UiRect::top(px(1)), ..default() });
            });
        r.spawn(Node { align_items: AlignItems::Center, column_gap: px(12), min_width: px(0), ..default() })
            .with_children(f);
    });
}

#[cfg(test)]
mod tests {
    use super::super::super::controls::{UiState, get_choice, get_num, get_toggle, set_choice, set_num, set_toggle};
    use super::super::super::model::embedded;
    use super::*;

    #[test]
    fn every_row_edits_the_value_it_names() {
        let d = embedded();
        let mut s = d.defaults.clone();
        let mut ui = UiState::default();
        // the defaults the mockup shows, in row order
        let shown: Vec<f32> = (0..VOLUMES.len()).map(|i| get_num(&s, &ui, d, Num::Vol(i as u8))).collect();
        assert_eq!(shown, [80.0, 90.0, 100.0, 85.0, 70.0, 60.0, 40.0]);
        for i in 0..VOLUMES.len() {
            set_num(&mut s, &mut ui, d, Num::Vol(i as u8), 10.0 + i as f32);
        }
        let a = &s.audio;
        assert_eq!(
            [a.master, a.weapons, a.movement, a.abilities, a.hits, a.interface, a.music],
            [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0]
        );
        // volumes are whole numbers in 0..=100
        set_num(&mut s, &mut ui, d, Num::Vol(0), 33.4);
        assert_eq!(s.audio.master, 33.0);
        set_num(&mut s, &mut ui, d, Num::Vol(0), 140.0);
        assert_eq!(s.audio.master, 100.0);
        // the low-mag cue is OFF | ON and off by default
        assert_eq!(get_choice(&d.defaults, &ui, d, Ch::LowMag), 0);
        set_choice(&mut s, &mut ui, d, Ch::LowMag, 1);
        assert!(s.audio.low_mag_cue);
        for (t, on) in [(Tg::ShieldHit, true), (Tg::Headshot, true), (Tg::PlayInBg, false)] {
            assert_eq!(get_toggle(&d.defaults, t), on, "{t:?}");
            set_toggle(&mut s, t, !on);
            assert_eq!(get_toggle(&s, t), !on, "{t:?}");
        }
        assert!(!s.audio.shield_hit && !s.audio.headshot && s.audio.play_in_background);
    }
}
