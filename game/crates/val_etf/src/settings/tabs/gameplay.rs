//! Settings ▸ GAMEPLAY (hub spec 13; built from settings.html, there is no PNG): the player name, movement
//! preferences, the mag-check card and the radial menus in the left card, the network defaults in the right.

use super::super::controls::{Ch, FieldKind, Kit, Num, Tg, card, dimc, field, h2, row, seg, slider, switch};
use crate::ui_kit::{self as kit, TextRole};
use bevy::prelude::*;
use bevy::text::LineHeight;

/// What a row's control column holds.
#[derive(Debug, Clone, Copy)]
enum Ctl {
    /// A text or number field, px wide.
    Field(FieldKind, f32),
    Switch(Tg),
    /// A segmented control; the listed options cannot be picked yet.
    Seg(Ch, &'static [usize]),
    /// A 400 px slider and its 70 px field.
    Slider(Num),
}

/// Label, sub-label, control.
type Row = (&'static str, Option<&'static str>, Ctl);

const GAMEPLAY: &[Row] = &[
    ("PLAYER NAME", None, Ctl::Field(FieldKind::PlayerName, 280.0)),
    ("AUTO-SPRINT", Some("Moving forward sprints · Shift walks"), Ctl::Switch(Tg::AutoSprint)),
    // SEPARATE KEY needs a 'Jetpack (hold)' bind, which Keybinds does not have yet.
    ("JETPACK", None, Ctl::Seg(Ch::Jetpack, &[1])),
    // OFF and WHILE HELD wait for the game to honour them (the sim always slides; the card is timed).
    ("SLIDE", None, Ctl::Seg(Ch::Slide, &[1])),
    ("MAG CHECK CARD", None, Ctl::Seg(Ch::MagCard, &[1])),
];

const RADIAL: &[Row] = &[
    ("RADIAL HOLD TIME", Some("Hold reload or heal this long to open the ring"), Ctl::Slider(Num::RadialHold)),
    ("RADIAL PICK", Some("Mag slot 1 is at the top, then clockwise"), Ctl::Seg(Ch::RadialPick, &[])),
];

const NETWORK: &[Row] = &[
    // The mockup stretches this field across the row; it is 140 wide (shell spec, adaptation 5).
    ("DEFAULT HOST PORT", None, Ctl::Field(FieldKind::Num(Num::HostPort), 140.0)),
    // The same value as Video ▸ Performance overlay '+ NETWORK'.
    ("SHOW NET GRAPH", None, Ctl::Switch(Tg::NetGraph)),
];

/// The proposed range of the radial pointer's dead zone, in mouse counts (spec 13). There is no setting for it
/// yet, so its row is drawn disabled at the game's value (`radial::DEADZONE`).
const POINTER_RANGE: (f32, f32) = (10.0, 30.0);

pub fn build(p: &mut ChildSpawnerCommands, k: &Kit) {
    super::col(p, |c| {
        card(c, 1.0, 14.0, Node::default(), |c| {
            h2(c, k, "GAMEPLAY", None, 0.0);
            rows(c, k, GAMEPLAY, true);
            h2(c, k, "RADIAL MENUS", None, 12.0);
            rows(c, k, RADIAL, true);
            pointer_row(c, k);
        });
    });
    super::col(p, |c| {
        card(c, 1.0, 14.0, Node::default(), |c| {
            h2(c, k, "NETWORK", None, 0.0);
            rows(c, k, NETWORK, false);
        });
    });
}

/// A table's rows. `more` = other rows follow in the card, so the last one keeps its border too.
fn rows(c: &mut ChildSpawnerCommands, k: &Kit, rows: &[Row], more: bool) {
    for (i, (label, sub, ctl)) in rows.iter().enumerate() {
        let border = more || i + 1 < rows.len();
        row(c, k, label, *sub, false, border, 50.0, |r| match *ctl {
            Ctl::Field(kind, width) => {
                field(r, k, kind, width, false, false);
            }
            Ctl::Switch(t) => switch(r, k, t, false),
            Ctl::Seg(ch, off) => {
                seg(r, k, ch, false, off);
            }
            Ctl::Slider(n) => {
                slider(r, k, n, Some(400.0), &[], false);
                field(r, k, FieldKind::Num(n), 70.0, false, false);
            }
        });
    }
}

/// RADIAL POINTER: the ring's dead zone, disabled until it is a setting.
fn pointer_row(c: &mut ChildSpawnerCommands, k: &Kit) {
    let dead = crate::radial::DEADZONE;
    let (lo, hi) = POINTER_RANGE;
    row(c, k, "RADIAL POINTER", Some("Mouse travel before a slot is picked"), true, false, 50.0, |r| {
        fixed_slider(r, ((dead - lo) / (hi - lo)).clamp(0.0, 1.0), 400.0);
        fixed_field(r, k, &format!("{dead:.0}"), 70.0);
    });
}

/// A disabled slider at a fixed position (the kit's slider look, with no value behind it).
fn fixed_slider(p: &mut ChildSpawnerCommands, frac: f32, width: f32) {
    p.spawn(Node { width: px(width), height: px(24), align_items: AlignItems::Center, flex_shrink: 0.0, ..default() })
        .with_children(|h| {
            h.spawn((Node { width: percent(100), height: px(4), ..default() }, BackgroundColor(dimc(kit::W14, true))))
                .with_children(|t| {
                    t.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: px(0),
                            top: px(0),
                            bottom: px(0),
                            width: percent(frac * 100.0),
                            ..default()
                        },
                        BackgroundColor(dimc(kit::TEXT_HI, true)),
                    ));
                    t.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: percent(frac * 100.0),
                            top: px(-6),
                            width: px(16),
                            height: px(16),
                            margin: UiRect::left(px(-8)),
                            ..default()
                        },
                        BackgroundColor(dimc(kit::TEXT_HI, true)),
                        UiTransform::from_rotation(Rot2::degrees(45.0)),
                    ));
                });
        });
}

/// A disabled number field showing `text` (the kit's `.inp` look).
fn fixed_field(p: &mut ChildSpawnerCommands, k: &Kit, text: &str, width: f32) {
    let pad_v = (36.0 - 2.0 - 18.0 * 1.2) / 2.0;
    p.spawn((
        Node {
            width: px(width),
            height: px(36),
            padding: UiRect::axes(px(10), px(pad_v)),
            border: UiRect::all(px(1)),
            flex_shrink: 0.0,
            overflow: Overflow::clip(),
            ..default()
        },
        BackgroundColor(dimc(kit::K35, true)),
        BorderColor::all(dimc(kit::STROKE_HI, true)),
        children![(
            Text::new(text),
            k.fonts.role_font(TextRole::Field),
            TextColor(dimc(kit::TEXT_HI, true)),
            LineHeight::RelativeToFont(1.2)
        )],
    ));
}

#[cfg(test)]
mod tests {
    use super::super::super::controls::*;
    use super::super::super::model::{Settings, SettingsData, embedded};
    use super::*;
    use crate::user_config::PlayerProfile;

    fn all_rows() -> impl Iterator<Item = &'static Row> {
        GAMEPLAY.iter().chain(RADIAL).chain(NETWORK)
    }

    /// What a row's control shows for these settings.
    fn shown(ctl: Ctl, s: &Settings, ui: &UiState, d: &SettingsData) -> String {
        match ctl {
            Ctl::Field(kind, _) => field_text(kind, s, ui, d, &PlayerProfile { name: "KESTREL_YOU".into() }),
            Ctl::Switch(t) => if get_toggle(s, t) { "ON" } else { "OFF" }.into(),
            Ctl::Seg(c, _) => choice_labels(ui, d, c, s)[get_choice(s, ui, d, c)].clone(),
            Ctl::Slider(n) => num_text(n, get_num(s, ui, d, n)),
        }
    }

    #[test]
    fn every_row_starts_at_the_specs_default() {
        let d = embedded();
        let ui = UiState::default();
        let want = [
            ("PLAYER NAME", "KESTREL_YOU"),
            // user direction 2026-10-08: sprint by default, slide from a run
            ("AUTO-SPRINT", "ON"),
            ("JETPACK", "HOLD JUMP IN AIR"),
            ("SLIDE", "CROUCH WHILE RUNNING"),
            ("MAG CHECK CARD", "3 S"),
            ("RADIAL HOLD TIME", "0.20 s"),
            ("RADIAL PICK", "RELEASE"),
            // the game's port (net.ron), not the mockup's 7777
            ("DEFAULT HOST PORT", "47820"),
            ("SHOW NET GRAPH", "OFF"),
        ];
        let rows: Vec<_> = all_rows().map(|(l, _, c)| (*l, shown(*c, &d.defaults, &ui, d))).collect();
        let want: Vec<_> = want.iter().map(|(l, v)| (*l, v.to_string())).collect();
        assert_eq!(rows, want, "the spec's rows, in order, at their defaults");
    }

    #[test]
    fn every_control_on_the_tab_writes_its_value() {
        let d = embedded();
        let mut s = d.defaults.clone();
        let mut ui = UiState::default();
        for (label, _, ctl) in all_rows() {
            match *ctl {
                Ctl::Seg(c, off) => {
                    let n = choice_labels(&ui, d, c, &s).len();
                    assert!(off.iter().all(|i| *i < n), "{label}");
                    for i in (0..n).filter(|i| !off.contains(i)) {
                        set_choice(&mut s, &mut ui, d, c, i);
                        assert_eq!(get_choice(&s, &ui, d, c), i, "{label} {i}");
                    }
                }
                Ctl::Switch(t) => {
                    for on in [true, false] {
                        set_toggle(&mut s, t, on);
                        assert_eq!(get_toggle(&s, t), on, "{label}");
                    }
                }
                Ctl::Slider(n) | Ctl::Field(FieldKind::Num(n), _) => {
                    let r = range(d, n);
                    for v in [r.min, r.max] {
                        set_num(&mut s, &mut ui, d, n, v);
                        assert!((get_num(&s, &ui, d, n) - v).abs() < 1e-4, "{label} {v}");
                    }
                }
                Ctl::Field(..) => {}
            }
        }
        assert_eq!(choice_labels(&ui, d, Ch::Jetpack, &s)[1], "SEPARATE KEY", "the option that waits for a bind");
        // the port field: 1024-65535, hold time snaps to 0.05 s
        assert!(!field_valid(FieldKind::Num(Num::HostPort), "1023", d));
        assert!(field_valid(FieldKind::Num(Num::HostPort), "65535", d));
        set_num(&mut s, &mut ui, d, Num::RadialHold, 0.37);
        assert_eq!(num_text(Num::RadialHold, s.gameplay.radial_hold_s), "0.35 s");
    }

    #[test]
    fn the_pointer_row_shows_the_games_dead_zone_on_its_track() {
        let (lo, hi) = POINTER_RANGE;
        assert!((lo..=hi).contains(&crate::radial::DEADZONE));
    }
}
