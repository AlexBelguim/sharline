//! The main menu's text fields. An invisible [`EditableText`] does the editing (keys, selection, clipboard,
//! IME); a mirror draws the value the way the mockups do: the role's letter spacing (Bevy's editable text has
//! none), upper case where the role says so, the placeholder, and the 2x30 teal caret that blinks between
//! full and .35 opacity once a second (CSS `pulse 1s steps(1)`).

use crate::screens::Screens;
use crate::ui_kit::*;
use bevy::input_focus::InputFocus;
use bevy::prelude::*;
use bevy::text::{EditableText, EditableTextFilter, FontFeatureTag, LetterSpacing, TextCursorStyle, TextEdit};

pub(super) fn plugin(app: &mut App) {
    app.add_systems(Update, mirror_fields);
}

/// Which field (the screen finds its fields by this).
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum FieldId {
    JoinCode,
    JoinIp,
    LobbyName,
    Port,
    PlayerName,
}

/// How a field looks and what it accepts.
pub(crate) struct FieldSpec {
    pub id: FieldId,
    pub role: TextRole,
    /// Letter spacing in em (the role's unless overridden).
    pub em: Option<f32>,
    pub tnum: bool,
    pub placeholder: String,
    pub max_chars: usize,
    pub filter: Option<fn(char) -> bool>,
    pub initial: String,
}

/// On the field's box: the entities of its parts and the last value seen.
#[derive(Component, Debug)]
pub(crate) struct Field {
    pub id: FieldId,
    pub editable: Entity,
    upper: bool,
    spacing: f32,
    before: Entity,
    after: Entity,
    caret_holder: Entity,
    caret: Entity,
    placeholder: Entity,
    shown: (String, String),
    pub value: String,
    /// The value changed this frame (typed, pasted or set).
    pub edited: bool,
    focused_since: f32,
    was_focused: bool,
}

/// The editable entity of a field.
#[derive(Component, Debug, Clone, Copy)]
pub(crate) struct FieldEditor(pub FieldId);

/// Spawn a field's contents into `node` (the box: size, fill, border; it gets [`Field`]). `extra` spawns
/// more children after the text (the PASTE button).
pub(crate) fn spawn_field(
    parent: &mut ChildSpawnerCommands,
    fonts: &UiFonts,
    spec: FieldSpec,
    node: impl Bundle,
    extra: impl FnOnce(&mut ChildSpawnerCommands),
) -> Entity {
    let r = spec.role.spec();
    let em = spec.em.unwrap_or(r.em);
    let spacing = r.size * em;
    let mut font = fonts.role_font(spec.role);
    if spec.tnum {
        font.font_features = [FontFeatureTag::TABULAR_FIGURES].into();
    }
    // One line: a long value runs on under the box's clip rather than wrapping.
    let text = |s: String, color: Color| {
        (
            Text::new(s),
            font.clone(),
            TextColor(color),
            LetterSpacing::Px(spacing),
            r.line,
            TextLayout::no_wrap(),
            Node { flex_shrink: 0.0, ..default() },
            Pickable::IGNORE,
        )
    };
    let (mut editable, mut before, mut after, mut caret_holder, mut caret, mut placeholder) = (
        Entity::PLACEHOLDER,
        Entity::PLACEHOLDER,
        Entity::PLACEHOLDER,
        Entity::PLACEHOLDER,
        Entity::PLACEHOLDER,
        Entity::PLACEHOLDER,
    );
    let mut boxed = parent.spawn(node);
    boxed.with_children(|b| {
        let mut ed = EditableText::new(&spec.initial);
        ed.allow_newlines = false;
        ed.max_characters = Some(spec.max_chars);
        // The mirror draws everything; the editor only edits.
        editable = b
            .spawn((
                FieldEditor(spec.id),
                ed,
                Node {
                    position_type: PositionType::Absolute,
                    left: px(0),
                    right: px(0),
                    top: px(0),
                    bottom: px(0),
                    ..default()
                },
                font.clone(),
                TextColor(Color::NONE),
                TextCursorStyle {
                    color: Color::NONE,
                    selection_color: Color::NONE,
                    unfocused_selection_color: Color::NONE,
                    selected_text_color: None,
                },
                spec.filter.map(EditableTextFilter::new).unwrap_or_default(),
            ))
            .id();
        // No clip here: the caret hangs past the text (the box clips).
        b.spawn((Node { align_items: AlignItems::Center, ..default() }, Pickable::IGNORE)).with_children(|row| {
            before = row.spawn(text(String::new(), r.color)).id();
            caret_holder = row
                .spawn((Node { width: px(0), height: px(30), ..default() }, Pickable::IGNORE))
                .with_children(|h| {
                    caret = h
                        .spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                left: px(4),
                                top: px(0),
                                width: px(2),
                                height: px(30),
                                ..default()
                            },
                            BackgroundColor(TEAL),
                            Visibility::Hidden,
                            Pickable::IGNORE,
                        ))
                        .id();
                })
                .id();
            after = row.spawn(text(String::new(), r.color)).id();
            placeholder = row.spawn(text(spec.placeholder.clone(), TEXT_LOW)).id();
        });
        extra(b);
    });
    boxed.insert(Field {
        id: spec.id,
        editable,
        upper: r.upper,
        spacing,
        before,
        after,
        caret_holder,
        caret,
        placeholder,
        shown: (String::from("\u{0}"), String::new()),
        value: spec.initial.clone(),
        edited: false,
        focused_since: 0.0,
        was_focused: false,
    });
    boxed.id()
}

/// Replace a field's value (caret at the end).
pub(crate) fn set_value(editable: &mut EditableText, value: &str) {
    editable.clear();
    editable.editor_mut().set_text(value);
    editable.queue_edit(TextEdit::TextEnd(false));
}

/// Split `display` at the caret: `cursor` is a byte index into `value`, and `display` has the same
/// characters (maybe upper-cased).
pub(crate) fn split_at_cursor(value: &str, display: &str, cursor: usize) -> (String, String) {
    let chars_before = value.get(..cursor.min(value.len())).map_or(value.chars().count(), |s| s.chars().count());
    let before: String = display.chars().take(chars_before).collect();
    let after: String = display.chars().skip(chars_before).collect();
    (before, after)
}

/// Caret opacity at `t` seconds after focus: 1 for half a second, then .35 (CSS `steps(1)`).
pub(crate) fn caret_alpha(t: f32) -> f32 {
    if t.rem_euclid(1.0) < 0.5 { 1.0 } else { 0.35 }
}

fn mirror_fields(
    mut fields: Query<&mut Field>,
    editors: Query<&EditableText>,
    focus: Res<InputFocus>,
    screens: Res<Screens>,
    time: Res<Time>,
    mut texts: Query<&mut Text>,
    mut nodes: Query<&mut Node>,
    mut vis: Query<&mut Visibility>,
    mut colors: Query<&mut BackgroundColor>,
) {
    let now = time.elapsed_secs();
    for mut f in &mut fields {
        let Ok(ed) = editors.get(f.editable) else { continue };
        let value = ed.value().to_string();
        f.edited = value != f.value;
        if f.edited {
            f.value = value.clone();
            f.focused_since = now;
        }
        let display = if f.upper { value.to_uppercase() } else { value.clone() };
        let cursor = ed.editor().raw_selection().focus().index();
        let parts = split_at_cursor(&value, &display, cursor);
        if parts != f.shown {
            if let Ok(mut t) = texts.get_mut(f.before) {
                t.0.clone_from(&parts.0);
            }
            if let Ok(mut t) = texts.get_mut(f.after) {
                t.0.clone_from(&parts.1);
            }
            if let Ok(mut n) = nodes.get_mut(f.placeholder) {
                n.display = if value.is_empty() { Display::Flex } else { Display::None };
            }
            // At the end the caret sits 4 px after the text; inside it, in the gap before the next glyph.
            if let Ok(mut n) = nodes.get_mut(f.caret) {
                n.left = px(if parts.1.is_empty() && !value.is_empty() { 4.0 } else { -(f.spacing / 2.0) - 1.0 });
            }
            if let Ok(mut n) = nodes.get_mut(f.caret_holder) {
                // Keep the placeholder clear of the caret.
                n.margin.right = px(if value.is_empty() { 6.0 } else { 0.0 });
            }
            f.shown = parts;
        }
        let focused = screens.is_empty() && focus.get() == Some(f.editable);
        if focused && !f.was_focused {
            f.focused_since = now;
        }
        f.was_focused = focused;
        if let Ok(mut v) = vis.get_mut(f.caret) {
            let want = if focused { Visibility::Inherited } else { Visibility::Hidden };
            if *v != want {
                *v = want;
            }
        }
        if focused && let Ok(mut c) = colors.get_mut(f.caret) {
            let want = fade(TEAL, caret_alpha(now - f.focused_since));
            if c.0 != want {
                c.0 = want;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_mirror_splits_at_the_caret() {
        assert_eq!(split_at_cursor("abc", "ABC", 1), ("A".into(), "BC".into()));
        assert_eq!(split_at_cursor("abc", "ABC", 3), ("ABC".into(), String::new()));
        assert_eq!(split_at_cursor("", "", 0), (String::new(), String::new()));
        // Multi-byte characters: the byte index maps to characters.
        assert_eq!(split_at_cursor("aé b", "AÉ B", 3), ("AÉ".into(), " B".into()));
    }

    #[test]
    fn the_caret_blinks_in_steps() {
        assert_eq!(caret_alpha(0.0), 1.0);
        assert_eq!(caret_alpha(0.49), 1.0);
        assert_eq!(caret_alpha(0.5), 0.35);
        assert_eq!(caret_alpha(1.2), 1.0);
    }
}
