//! Settings ▸ Keybinds (mockup 08b): the input map as two tables, rebinding by clicking a key cap, and the
//! conflict check. The rows follow the game, not the mockup: tap / hold reload with the magazine radial,
//! the static 1–6 magazine pick, the heal ring on H, and LATER rows for features the prototype lacks.

use super::bindings::{Action, Binding};
use super::controls::{Kit, glyph_runs, text_as};
use super::model::{Settings, move_label};
use crate::ui_kit::{self as kit, Face, NodeImageMode, Shape, TextRole};
use bevy::ecs::hierarchy::ChildSpawnerCommands;
use bevy::input::mouse::AccumulatedMouseScroll;
use bevy::prelude::*;
use bevy::text::LetterSpacing;
use bevy::ui::widget::NodeImageMode as _;

/// What a key cap rebinds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CapTarget {
    /// The four movement keys, entered in sequence (forward, left, back, right).
    Move(usize),
    Action(Action, usize),
}

#[derive(Component, Debug, Clone, Copy)]
pub struct KeyCap {
    pub target: CapTarget,
    pub text: Entity,
}

/// The conflict note after an action's name ('· V is also Laser').
#[derive(Component, Debug, Clone, Copy)]
pub struct ConflictNote(pub Action);

/// The cap waiting for an input.
#[derive(Resource, Debug, Default, Clone, PartialEq)]
pub struct Listening {
    pub target: Option<CapTarget>,
    /// For Move: which of the four keys is next, and the ones entered so far.
    pub step: usize,
    pub keys: [Option<Binding>; 4],
}

const MOVE_STEPS: [&str; 4] = ["FORWARD…", "LEFT…", "BACK…", "RIGHT…"];

enum Row {
    Group(&'static str),
    Head,
    Move,
    /// Label, the actions whose caps sit in the cell (Fire and ADS share a row), gamepad text.
    Act(&'static str, &'static [Action], &'static str),
    /// A cap that is not rebindable: label, cap, cap ink, gamepad text.
    Fixed(&'static str, &'static str, Color, &'static str),
}

const LEFT: &[Row] = &[
    Row::Head,
    Row::Group("MOVEMENT"),
    Row::Move,
    Row::Act("Jump · in air, press again and hold: jetpack", &[Action::Jump], "A / ✕"),
    Row::Act("Sprint (hold)", &[Action::Sprint], "L3 click"),
    Row::Act("Walk (silent)", &[Action::Walk], "—"),
    Row::Act("Crouch · while sprinting: slide", &[Action::Crouch], "B / ◯"),
    Row::Act("Interact · grab zipline · revive", &[Action::Interact], "X / ▢ hold"),
    Row::Group("COMBAT"),
    Row::Act("Fire · aim down sights", &[Action::Fire, Action::Ads], "RT · LT"),
    Row::Act("Reload · tap: next mag in order · hold: mag radial", &[Action::Reload], "X / ▢"),
    Row::Fixed("Pick mag (radial open)", "1 – 6", kit::TEXT_MID, "—"),
    Row::Act("Mag check", &[Action::MagCheck], "D-pad ↑"),
    Row::Act("Fire mode", &[Action::FireMode], "D-pad ↑ hold"),
    Row::Act("Underbarrel launcher", &[Action::Underbarrel], "D-pad →"),
    Row::Act("Laser / flashlight", &[Action::Laser], "D-pad ↓"),
    Row::Act("Melee", &[Action::Melee], "R3 tap"),
    Row::Act("Hold breath (Warden scope)", &[Action::HoldBreath], "L3 while ADS"),
];

const RIGHT: &[Row] = &[
    Row::Head,
    Row::Group("ABILITIES"),
    Row::Act("Ability 1 (Grapple · Mend Drone)", &[Action::Ability1], "LB / L1"),
    Row::Act("Signature (Scan · Triage Pulse)", &[Action::Signature], "RB / R1"),
    Row::Act("Ultimate", &[Action::Ultimate], "LB + RB"),
    Row::Group("ITEMS & HEALTH"),
    Row::Act("Heal · item radial (toggle)", &[Action::Heal], "D-pad ← hold"),
    Row::Group("INTERFACE"),
    Row::Act("Scoreboard + join code (hold)", &[Action::Scoreboard], "View hold"),
    Row::Act("Ping / mark", &[Action::Ping], "R3 hold"),
    Row::Act("Team chat · all chat", &[Action::Chat], "—"),
    Row::Act("Change loadout (when dead)", &[Action::ChangeLoadout], "Y / △"),
    Row::Fixed("Match menu", "ESC", kit::TEXT_HI, "Menu / Options"),
];

/// Build the tab's two cards into the pane.
pub fn build(p: &mut ChildSpawnerCommands, k: &Kit) {
    super::controls::card(p, 1.05, 14.0, Node::default(), |c| {
        super::controls::h2(c, k, "KEYBOARD & MOUSE", Some(("CLICK A KEY TO REBIND · BACKSPACE CLEARS · ESC CANCELS", None)), 0.0);
        table(c, k, LEFT, [352.0, 158.0, 116.0]);
    });
    super::controls::card(p, 1.0, 0.0, Node::default(), |c| {
        table(c, k, RIGHT, [303.0, 116.0, 125.0]);
        super::controls::note(
            c,
            k,
            &[(
                "Conflicts are allowed only between contexts that never run at once (Sprint and Hold breath share \
                 Shift because you cannot sprint while aiming). Any other clash turns the key amber and names the \
                 other action. Number keys 1–6 pick magazines only while the reload radial is open.",
                false,
                None,
            )],
            Node { margin: UiRect::top(Val::Auto), padding: UiRect::top(px(12)), ..default() },
        );
    });
}

fn grid(cols: [f32; 3]) -> Vec<GridTrack> {
    vec![GridTrack::px(cols[0]), GridTrack::px(cols[1]), GridTrack::px(cols[2]), GridTrack::flex(1.0)]
}

fn table(p: &mut ChildSpawnerCommands, k: &Kit, rows: &[Row], cols: [f32; 3]) {
    p.spawn(Node { flex_direction: FlexDirection::Column, flex_shrink: 0.0, ..default() }).with_children(|t| {
        for row in rows {
            match row {
                Row::Head => {
                    t.spawn(Node { display: Display::Grid, grid_template_columns: grid(cols), ..default() })
                        .with_children(|r| {
                            for h in ["ACTION", "PRIMARY", "SECONDARY", "GAMEPAD"] {
                                r.spawn((
                                    Node { padding: UiRect::axes(px(10), px(6)), ..default() },
                                    children![k.fonts.role(TextRole::TableHead, h)],
                                ));
                            }
                        });
                }
                Row::Group(g) => {
                    t.spawn((
                        Node {
                            height: px(34),
                            padding: UiRect { left: px(10), top: px(12), ..default() },
                            align_items: AlignItems::Center,
                            ..default()
                        },
                        children![k.fonts.role_color(TextRole::GroupRow, *g, kit::TEXT_HI)],
                    ));
                }
                Row::Move => action_row(t, k, cols, "Move", &[], true, "Left stick", None),
                Row::Act(label, actions, pad) => action_row(t, k, cols, label, actions, false, pad, None),
                Row::Fixed(label, cap, ink, pad) => action_row(t, k, cols, label, &[], false, pad, Some((cap, *ink))),
            }
        }
    });
}

#[allow(clippy::too_many_arguments)]
fn action_row(
    t: &mut ChildSpawnerCommands,
    k: &Kit,
    cols: [f32; 3],
    label: &str,
    actions: &[Action],
    is_move: bool,
    pad: &str,
    fixed: Option<(&str, Color)>,
) {
    let later = actions.iter().any(|a| a.later());
    t.spawn((
        Node {
            display: Display::Grid,
            grid_template_columns: grid(cols),
            height: px(38),
            align_items: AlignItems::Center,
            border: UiRect::top(px(1)),
            ..default()
        },
        BorderColor::all(kit::STROKE),
    ))
    .with_children(|r| {
        // action name (+ LATER, + conflict note)
        r.spawn(Node { padding: UiRect::horizontal(px(10)), align_items: AlignItems::Center, column_gap: px(8), ..default() })
            .with_children(|c| {
                let role = TextRole::TableCell;
                let ink = if later { kit::TEXT_MID } else { kit::TEXT };
                let note_font = k.fonts.role_font(TextRole::Note);
                c.spawn(text_as(k.fonts, role, label, ink)).with_children(|s| {
                    for a in actions {
                        s.spawn((TextSpan::new(""), note_font.clone(), TextColor(kit::WARN), ConflictNote(*a)));
                    }
                });
                if later {
                    c.spawn(k.fonts.micro("LATER"));
                }
            });
        // primary and secondary
        for slot in 0..2 {
            r.spawn(Node { padding: UiRect::horizontal(px(10)), column_gap: px(4), align_items: AlignItems::Center, ..default() })
                .with_children(|c| {
                    if let Some((cap, ink)) = fixed {
                        if slot == 0 {
                            static_cap(c, k, cap, ink);
                        }
                    } else if is_move {
                        key_cap(c, k, CapTarget::Move(slot));
                    } else {
                        for a in actions {
                            key_cap(c, k, CapTarget::Action(*a, slot));
                        }
                    }
                });
        }
        // gamepad (a reference only: the game reads no gamepad yet)
        r.spawn(Node { padding: UiRect::horizontal(px(10)), ..default() }).with_children(|c| {
            pad_text(c, k, pad);
        });
    });
}

fn pad_text(c: &mut ChildSpawnerCommands, k: &Kit, s: &str) {
    let font = k.fonts.font(Face::Display, 600, 14.0);
    let mut sym = TextFont::from_font_size(13.0).with_font(k.symbols.clone());
    sym.font_size = FontSize::Px(13.0);
    c.spawn((Text::new(""), font.clone(), TextColor(kit::TEXT_MID))).with_children(|t| {
        for (run, is_sym) in glyph_runs(s) {
            t.spawn((TextSpan::new(run), if is_sym { sym.clone() } else { font.clone() }, TextColor(kit::TEXT_MID)));
        }
    });
}

fn cap_node() -> Node {
    Node {
        min_width: px(44),
        height: px(28),
        padding: UiRect::horizontal(px(10)),
        align_items: AlignItems::Center,
        border: UiRect::all(px(1)),
        flex_shrink: 0.0,
        ..default()
    }
}

fn static_cap(c: &mut ChildSpawnerCommands, k: &Kit, label: &str, ink: Color) {
    c.spawn((
        cap_node(),
        BorderColor::all(if ink == kit::TEXT_HI { kit::STROKE_HI } else { kit::STROKE_MID }),
        children![k.fonts.role_color(TextRole::KeybindCap, label, ink)],
    ));
}

fn key_cap(c: &mut ChildSpawnerCommands, k: &Kit, target: CapTarget) {
    let font = k.fonts.role_font(TextRole::KeybindCap);
    let spacing = TextRole::KeybindCap.spacing_px();
    let mut cap = c.spawn((
        Button,
        cap_node(),
        BorderColor::all(kit::STROKE_HI),
        ImageNode::new(k.images.shape(Shape::Dash9Slice)).with_mode(NodeImageMode::Sliced(TextureSlicer {
            border: BorderRect::all(2.0),
            center_scale_mode: SliceScaleMode::Stretch,
            sides_scale_mode: SliceScaleMode::Tile { stretch_value: 1.0 },
            max_corner_scale: 0.5,
        })),
    ));
    let mut text = Entity::PLACEHOLDER;
    cap.with_children(|t| {
        text = t.spawn((Text::new(""), font, TextColor(kit::TEXT_HI), LetterSpacing::Px(spacing))).id();
    });
    cap.insert(KeyCap { target, text });
}

fn binding(s: &Settings, t: CapTarget) -> Option<String> {
    match t {
        CapTarget::Move(slot) => move_label(&s.keybinds, slot),
        CapTarget::Action(a, slot) => s.keybinds.slot(a, slot).map(|b| b.label()),
    }
}

/// Caps show their binding, '—' when unbound, a teal pulse while listening, amber on a clash.
#[allow(clippy::type_complexity)]
pub fn sync_caps(
    mut commands: Commands,
    settings: Res<Settings>,
    listening: Res<Listening>,
    time: Res<Time>,
    fonts: Res<crate::ui_kit::UiFonts>,
    symbols: Res<super::SymbolFont>,
    mut caps: Query<(&KeyCap, &Interaction, &mut BorderColor, &mut ImageNode)>,
    mut texts: Query<(&mut TextColor, Option<&Children>), With<Text>>,
    mut spans: Query<(&mut TextSpan, &mut TextColor), (Without<Text>, Without<ConflictNote>)>,
    mut notes: Query<(&ConflictNote, &mut TextSpan), (Without<Text>, With<TextColor>)>,
    mut last: Local<Vec<(CapTarget, String)>>,
) {
    let conflicts = settings.keybinds.conflicts();
    let pulse = {
        let phase = time.elapsed_secs().fract();
        0.35 + 0.65 * (0.5 + 0.5 * (phase * std::f32::consts::TAU).cos())
    };
    let font = fonts.role_font(TextRole::KeybindCap);
    let mut sym = TextFont::from_font_size(13.0).with_font(symbols.0.clone());
    sym.font_size = FontSize::Px(13.0);
    for (cap, interaction, mut border, mut image) in &mut caps {
        let listen = listening.target == Some(cap.target);
        let bound = binding(&settings, cap.target);
        let clash = match cap.target {
            CapTarget::Action(a, slot) => conflicts.iter().any(|((x, s), _)| *x == a && *s == slot),
            CapTarget::Move(slot) => conflicts.iter().any(|((x, s), _)| Action::MOVE.contains(x) && *s == slot),
        };
        let label = if listen {
            match cap.target {
                CapTarget::Move(_) => MOVE_STEPS[listening.step.min(3)].to_string(),
                _ => "PRESS A KEY…".to_string(),
            }
        } else {
            bound.clone().unwrap_or_else(|| "—".into())
        };
        let hovered = matches!(interaction, Interaction::Hovered | Interaction::Pressed);
        let (ink, edge, dashed) = if listen {
            (kit::fade(kit::TEAL, pulse), kit::fade(kit::TEAL, pulse), false)
        } else if bound.is_none() {
            (kit::TEXT_LOW, Color::NONE, true)
        } else if clash {
            (kit::WARN, kit::WARN, false)
        } else {
            (kit::TEXT_HI, if hovered { kit::TEXT_HI } else { kit::STROKE_HI }, false)
        };
        if border.top != edge {
            *border = BorderColor::all(edge);
        }
        let dash = if dashed { if hovered { kit::TEXT_HI } else { kit::STROKE_HI } } else { Color::NONE };
        if image.color != dash {
            image.color = dash;
        }
        // Rebuild the label's spans only when the text changes (arrows come from the symbol font).
        let known = last.iter().find(|(t, _)| *t == cap.target).map(|(_, l)| l.clone());
        if known.as_deref() != Some(label.as_str()) {
            last.retain(|(t, _)| *t != cap.target);
            last.push((cap.target, label.clone()));
            commands.entity(cap.text).despawn_related::<Children>();
            for (run, is_sym) in glyph_runs(&label) {
                commands.spawn((
                    TextSpan::new(run),
                    if is_sym { sym.clone() } else { font.clone() },
                    TextColor(ink),
                    ChildOf(cap.text),
                ));
            }
        }
        if let Ok((mut c, kids)) = texts.get_mut(cap.text) {
            c.0 = ink;
            for k in kids.into_iter().flatten() {
                if let Ok((_, mut sc)) = spans.get_mut(*k)
                    && sc.0 != ink
                {
                    sc.0 = ink;
                }
            }
        }
    }
    // '· V is also Laser' on the later row of a clash
    let order = |a: Action| Action::ALL.iter().position(|x| *x == a).unwrap_or(0);
    for (note, mut span) in &mut notes {
        let want = conflicts
            .iter()
            .filter(|((a, _), other)| *a == note.0 && order(*other) < order(*a))
            .find_map(|((a, slot), other)| {
                settings.keybinds.slot(*a, *slot).map(|b| format!("  · {} is also {}", b.label(), other.short()))
            })
            .unwrap_or_default();
        if span.0 != want {
            span.0 = want;
        }
    }
}

/// Clicking a cap starts listening on it (clicking another cap moves the listening).
pub fn cap_clicks(caps: Query<(&KeyCap, &Interaction), Changed<Interaction>>, mut listening: ResMut<Listening>) {
    for (cap, i) in &caps {
        if *i == Interaction::Pressed && listening.target != Some(cap.target) {
            *listening = Listening { target: Some(cap.target), ..default() };
        }
    }
}

/// While a cap listens, the next key, mouse button or wheel turn binds it (runs before the UI sees the
/// input, and swallows it). Backspace clears, Esc cancels.
pub fn capture(
    mut listening: ResMut<Listening>,
    mut keys: ResMut<ButtonInput<KeyCode>>,
    mut mouse: ResMut<ButtonInput<MouseButton>>,
    scroll: Res<AccumulatedMouseScroll>,
    caps: Query<(&KeyCap, &Interaction)>,
    mut settings: ResMut<Settings>,
) {
    let Some(target) = listening.target else { return };
    if keys.just_pressed(KeyCode::Escape) {
        keys.clear_just_pressed(KeyCode::Escape);
        *listening = Listening::default();
        return;
    }
    let mut got: Option<Option<Binding>> = None;
    if keys.just_pressed(KeyCode::Backspace) {
        keys.clear_just_pressed(KeyCode::Backspace);
        got = Some(None);
    }
    if got.is_none()
        && let Some(k) = keys.get_just_pressed().copied().find(|k| Binding::is_bindable_key(*k))
    {
        keys.clear_just_pressed(k);
        got = Some(Some(Binding::Key(k)));
    }
    if got.is_none()
        && let Some(m) = mouse.get_just_pressed().copied().next()
    {
        // A click on another cap moves the listening there (the UI handles it); anything else binds.
        let on_other_cap = caps.iter().any(|(c, i)| c.target != target && *i != Interaction::None);
        if !(m == MouseButton::Left && on_other_cap) {
            mouse.clear_just_pressed(m);
            got = Some(Some(Binding::Mouse(m)));
        }
    }
    if got.is_none() && scroll.delta.y != 0.0 {
        got = Some(Some(if scroll.delta.y > 0.0 { Binding::WheelUp } else { Binding::WheelDown }));
    }
    let Some(b) = got else { return };
    let mut next = (*settings).clone();
    match target {
        CapTarget::Action(a, slot) => {
            next.keybinds.set(a, slot, b);
            *listening = Listening::default();
        }
        CapTarget::Move(slot) => match b {
            None => {
                for a in Action::MOVE {
                    next.keybinds.set(a, slot, None);
                }
                *listening = Listening::default();
            }
            Some(b) => {
                let step = listening.step.min(3);
                listening.keys[step] = Some(b);
                listening.step += 1;
                if listening.step >= 4 {
                    for (a, k) in Action::MOVE.iter().zip(listening.keys) {
                        next.keybinds.set(*a, slot, k);
                    }
                    *listening = Listening::default();
                }
            }
        },
    }
    if next != *settings {
        *settings = next;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_tables_cover_every_action_once() {
        let mut seen: Vec<Action> = Action::MOVE.to_vec();
        for row in LEFT.iter().chain(RIGHT) {
            if let Row::Act(_, actions, _) = row {
                seen.extend(actions.iter().copied());
            }
        }
        for a in Action::ALL {
            assert_eq!(seen.iter().filter(|x| **x == a).count(), 1, "{a:?}");
        }
        // the left table still fits its card: header 26 + groups 34 + rows 38
        let rows = LEFT.iter().filter(|r| matches!(r, Row::Act(..) | Row::Move | Row::Fixed(..))).count() as f32;
        let groups = LEFT.iter().filter(|r| matches!(r, Row::Group(_))).count() as f32;
        assert!(26.0 + groups * 34.0 + rows * 38.0 < 864.0 - 2.0 * 19.0 - 36.0);
    }
}
