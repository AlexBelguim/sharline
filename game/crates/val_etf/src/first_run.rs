//! First launch on a machine: ask for a callsign (the player name) before anything else.
//!
//! When no profile has been saved yet (`profile.ron` is missing from the config folder), the main menu opens
//! with a modal over it: CHOOSE YOUR CALLSIGN, a text field with live validation, CONFIRM (Enter does the
//! same) and a one-click `USE AGENT-nnnn` (a generated callsign, never the OS user name). Esc does not
//! close it. Confirming saves the profile, so the prompt never shows again; the name can be changed later
//! with EDIT NAME on the main menu's player card. Until a name is chosen the player shows as `UNKNOWN`.
//!
//! Unattended runs never see it: `--name` (used for that run, not saved), `--host`, `--join`, `--bot`,
//! `--screenshot` and `--demo-ui` skip it, except `--demo-ui first-run | first-run-invalid |
//! first-run-valid`, which open it (empty, with a too-short name, with a valid name) for screenshots.
//!
//! The name rules live here ([`validate_name`]); the player card and Settings use the same ones through
//! [`PlayerProfile::name_char_ok`] and [`PlayerProfile::clean_name`].
//!
//! The modal is the confirm modal of the hub spec (`16_*.md`: MODAL_SURFACE, 620 wide, padding 28 / 30,
//! a 3 px top accent, right-aligned actions) with the TEAL focus accent, since nothing here is destructive.
//! Its field draws like the main menu's fields: an invisible `EditableText` edits, a mirror shows the value
//! in the role's letter spacing and case with the teal 2x30 caret.

use crate::AppState;
use crate::config::Cli;
use crate::net::Session;
use crate::screens::{Screen, ScreenRoot, Screens};
use crate::ui_kit::*;
use crate::user_config::PlayerProfile;
use bevy::input_focus::{FocusCause, InputFocus};
use bevy::prelude::*;
use bevy::text::{EditableText, EditableTextFilter, LetterSpacing, TextCursorStyle};
use bevy::ui::FocusPolicy;

// ---------------------------------------------------------------------------------------------- name rules

/// Shortest callsign, in characters.
pub const NAME_MIN: usize = 3;
/// Longest callsign (the host keeps 16 characters of a name).
pub const NAME_MAX: usize = PlayerProfile::MAX_NAME;

/// Characters a callsign may use: ASCII letters and digits, space, `-`, `_` and `.`.
pub fn name_char_ok(c: char) -> bool {
    c.is_ascii_alphanumeric() || matches!(c, ' ' | '-' | '_' | '.')
}

/// Why a typed callsign cannot be used.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NameError {
    /// Nothing typed (or only spaces).
    Empty,
    TooShort,
    TooLong,
    /// A character outside [`name_char_ok`].
    BadChar(char),
}

impl NameError {
    /// The help line under a name field.
    pub fn message(self) -> String {
        match self {
            NameError::Empty => format!("{NAME_MIN}–{NAME_MAX} characters: letters, digits, spaces and - _ ."),
            NameError::TooShort => format!("Too short: use at least {NAME_MIN} characters."),
            NameError::TooLong => format!("Too long: use at most {NAME_MAX} characters."),
            NameError::BadChar(c) if c.is_whitespace() || c.is_control() => {
                "Use only letters, digits, plain spaces and - _ .".into()
            }
            NameError::BadChar(c) => format!("“{c}” is not allowed: use letters, digits, spaces and - _ ."),
        }
    }
}

/// Trim, fold runs of spaces into one and upper-case (the kit shows names in upper case).
fn tidy(raw: &str) -> String {
    raw.split(' ').filter(|w| !w.is_empty()).collect::<Vec<_>>().join(" ").to_uppercase()
}

/// A typed callsign as the game keeps it (trimmed, single spaces, upper case), or why it cannot be used:
/// 3-16 characters of letters, digits, space, `-`, `_` and `.`.
pub fn validate_name(raw: &str) -> Result<String, NameError> {
    if let Some(c) = raw.chars().find(|c| !name_char_ok(*c)) {
        return Err(NameError::BadChar(c));
    }
    let name = tidy(raw);
    match name.chars().count() {
        0 => Err(NameError::Empty),
        n if n < NAME_MIN => Err(NameError::TooShort),
        n if n > NAME_MAX => Err(NameError::TooLong),
        _ => Ok(name),
    }
}

/// A name from elsewhere (a saved file, the OS user name) made usable: disallowed characters dropped,
/// tidied and cut to 16 characters. `None` if nothing is left. Unlike [`validate_name`] it keeps names
/// shorter than 3, so a name saved under older rules survives.
pub fn sanitize_name(raw: &str) -> Option<String> {
    let kept: String =
        raw.chars().map(|c| if c.is_whitespace() { ' ' } else { c }).filter(|c| name_char_ok(*c)).collect();
    let name: String = tidy(&kept).chars().take(NAME_MAX).collect();
    let name = name.trim_end();
    (!name.is_empty()).then(|| name.to_string())
}

/// The quick option: a generated callsign, `AGENT-` and four digits of `seed`. Never the OS user name:
/// friends would see it.
pub fn suggest_name(seed: u32) -> String {
    format!("AGENT-{:04}", seed % 10_000)
}

/// The name this run starts with: `--name` for this run, else the saved profile's (which is
/// [`crate::config::UNNAMED`] until one is chosen).
pub fn starting_name(cli: &Cli, profile: &PlayerProfile) -> String {
    if cli.name_given { cli.name.clone() } else { profile.name.clone() }
}

/// A few varying digits for a generated callsign (no RNG crate needed for this).
fn seed() -> u32 {
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.subsec_nanos());
    nanos ^ std::process::id().rotate_left(16)
}

// ---------------------------------------------------------------------------------------------- when

/// `--demo-ui` values that open the prompt, and what each types into the field.
pub const DEMOS: [(&str, &str); 3] = [("first-run", ""), ("first-run-invalid", "K7"), ("first-run-valid", "Kestrel 7")];

/// What a `--demo-ui` value types into the field, if it is one of this screen's demos.
pub fn demo_text(demo: &str) -> Option<&'static str> {
    DEMOS.iter().find(|(d, _)| *d == demo).map(|(_, text)| *text)
}

/// Does this run ask for a callsign? Only on the first interactive launch (no saved profile and no
/// `--name`); never in a run that hosts, joins, plays a bot, takes a screenshot or shows a demo, except this
/// screen's own demos.
pub fn should_prompt(cli: &Cli, profile_saved: bool) -> bool {
    let unattended = cli.host.is_some() || cli.join.is_some() || cli.bot;
    if let Some(demo) = cli.demo_ui.as_deref() {
        return demo_text(demo).is_some() && !unattended;
    }
    !profile_saved && !cli.name_given && !unattended && !cli.demo_mode()
}

// ---------------------------------------------------------------------------------------------- plugin

/// The prompt's state for this run (decided at start-up).
#[derive(Resource, Debug, Clone, Default, PartialEq, Eq)]
pub struct FirstRun {
    /// The prompt still has to be answered.
    pub pending: bool,
    /// What the field starts with (the demos fill it).
    pub initial: String,
    /// The `USE <name>` quick option.
    pub suggested: String,
}

pub struct FirstRunPlugin;

impl Plugin for FirstRunPlugin {
    fn build(&self, app: &mut App) {
        app.init_resource::<FirstRun>()
            .add_systems(Startup, decide)
            .add_systems(
                Update,
                (open, spawn_prompt, keep_focus, act, mirror, validation)
                    .chain()
                    .run_if(in_state(AppState::MainMenu))
                    .run_if(resource_exists::<UiFonts>),
            )
            .add_systems(
                Update,
                keep_esc
                    .in_set(crate::screens::EscSystems::Top)
                    .run_if(crate::screens::screen_on_top(Screen::NamePrompt)),
            );
    }
}

fn decide(cli: Res<Cli>, mut first: ResMut<FirstRun>) {
    *first = FirstRun {
        pending: should_prompt(&cli, PlayerProfile::saved()),
        initial: cli.demo_ui.as_deref().and_then(demo_text).unwrap_or_default().to_string(),
        suggested: suggest_name(seed()),
    };
}

/// Over everything else the hub puts on screen (the Loadout uses 100+, popovers 130).
const PROMPT_Z: i32 = 200;

/// The modal backdrop (CSS black .60). Browsers dim in sRGB, Bevy in linear light, where the same alpha
/// dims far less: `1 - (1 - a)^2.2` gives the browser's result over any backdrop (as the main menu's shade).
fn backdrop() -> Color {
    black(1.0 - (1.0 - 0.60f32).powf(2.2))
}

const TITLE: &str = "Choose your callsign";
const BODY: &str = "Friends see it in lobbies, on the scoreboard and in the kill feed. You can change it later with \
                    EDIT NAME on the main menu.";
const PLACEHOLDER: &str = "TYPE A CALLSIGN";

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
enum PromptButton {
    Suggest,
    Confirm,
}

/// The editing entity (invisible; the mirror draws its value).
#[derive(Component)]
struct NameEditor;

/// The field's box and its mirror's parts.
#[derive(Component)]
struct Mirror {
    before: Entity,
    after: Entity,
    caret: Entity,
    caret_holder: Entity,
    placeholder: Entity,
    shown: Option<(String, String)>,
    value: String,
    since: f32,
}

#[derive(Component)]
struct HelpLine;

#[derive(Component)]
struct Counter;

/// Keep the prompt on the overlay stack while it is pending (the main menu ignores input while a screen is
/// open, so nothing behind it reacts to typing, Enter or clicks).
fn open(first: Res<FirstRun>, mut screens: ResMut<Screens>) {
    if first.pending && !screens.contains(Screen::NamePrompt) {
        screens.push(Screen::NamePrompt);
    }
}

fn spawn_prompt(
    mut commands: Commands,
    fonts: Res<UiFonts>,
    first: Res<FirstRun>,
    screens: Res<Screens>,
    roots: Query<&ScreenRoot>,
) {
    if screens.top() != Some(Screen::NamePrompt) || roots.iter().any(|r| r.0 == Screen::NamePrompt) {
        return;
    }
    let pad = UiRect { left: px(30), right: px(30), top: px(28), bottom: px(28) };
    commands
        .spawn((
            ScreenRoot(Screen::NamePrompt),
            DespawnOnExit(AppState::MainMenu),
            GlobalZIndex(PROMPT_Z),
            Node {
                position_type: PositionType::Absolute,
                width: percent(100),
                height: percent(100),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..default()
            },
            BackgroundColor(backdrop()),
            // A backdrop click does nothing, and nothing under it lights up.
            FocusPolicy::Block,
            Interaction::default(),
        ))
        .with_children(|root| {
            let mut modal = root.spawn(panel_of(
                PanelKind::Modal,
                Node { width: px(620), flex_direction: FlexDirection::Column, padding: pad, ..default() },
            ));
            // Not a destructive confirm: the focus accent instead of red.
            modal.insert(BorderColor { top: TEAL, ..BorderColor::all(STROKE) });
            modal.with_children(|m| {
                m.spawn(fonts.role(TextRole::ModalTitle, TITLE));
                m.spawn((fonts.role(TextRole::ModalBody, BODY), Node { margin: UiRect::top(px(10)), ..default() }));
                m.spawn(Node {
                    margin: UiRect { top: px(22), bottom: px(8), ..default() },
                    justify_content: JustifyContent::SpaceBetween,
                    align_items: AlignItems::Center,
                    ..default()
                })
                .with_children(|l| {
                    l.spawn(fonts.lbl("Callsign"));
                    let mut font = fonts.role_font(TextRole::Lbl);
                    font.font_features = [bevy::text::FontFeatureTag::TABULAR_FIGURES].into();
                    l.spawn((
                        Counter,
                        Text::new(counter_text(&first.initial)),
                        font,
                        TextColor(TEXT_LOW),
                        LetterSpacing::Px(TextRole::Lbl.spacing_px()),
                    ));
                });
                spawn_field(m, &fonts, &first.initial);
                m.spawn((
                    HelpLine,
                    fonts.role(TextRole::Help, NameError::Empty.message()),
                    Node { margin: UiRect::top(px(8)), ..default() },
                ));
                m.spawn(Node {
                    margin: UiRect::top(px(22)),
                    justify_content: JustifyContent::FlexEnd,
                    column_gap: px(12),
                    ..default()
                })
                .with_children(|a| {
                    let use_label = format!("Use {}", first.suggested);
                    a.spawn((button(&fonts, &use_label, BtnKind::Normal, BtnSize::M), PromptButton::Suggest));
                    a.spawn((confirm_button(&fonts), PromptButton::Confirm, Disabled));
                });
            });
        });
}

/// The primary CONFIRM button with an ENTER cap drawn in the button's ink (the kit's ghost cap is light-on-
/// dark and would vanish on the light primary fill).
fn confirm_button(fonts: &UiFonts) -> impl Bundle {
    let looks = BtnKind::Primary.looks();
    (
        Button,
        button_node(BtnSize::M),
        BackgroundColor(looks.idle.bg),
        BorderColor::all(looks.idle.border),
        looks,
        children![
            (fonts.role_color(TextRole::Btn, "Confirm", looks.idle.ink), Ink),
            (
                Node {
                    min_width: px(20),
                    height: px(20),
                    padding: UiRect::horizontal(px(6)),
                    align_items: AlignItems::Center,
                    justify_content: JustifyContent::Center,
                    border: UiRect::all(px(1)),
                    border_radius: BorderRadius::all(px(2)),
                    ..default()
                },
                BorderColor::all(translucent(BG0, 0.45)),
                children![(fonts.text("ENTER", Face::Display, 700, 13.0, looks.idle.ink, 0.04), Ink)],
            ),
        ],
    )
}

/// The `.input` box (56 tall, K45 fill, STROKE_HI border) with the name in the player card's type.
fn spawn_field(parent: &mut ChildSpawnerCommands, fonts: &UiFonts, initial: &str) {
    let role = TextRole::PlayerName;
    let r = role.spec();
    let font = fonts.role_font(role);
    let text = |s: &str, color: Color| {
        (
            Text::new(s),
            font.clone(),
            TextColor(color),
            LetterSpacing::Px(role.spacing_px()),
            r.line,
            TextLayout::no_wrap(),
            Node { flex_shrink: 0.0, ..default() },
            Pickable::IGNORE,
        )
    };
    let (mut before, mut after, mut caret, mut caret_holder, mut placeholder) =
        (Entity::PLACEHOLDER, Entity::PLACEHOLDER, Entity::PLACEHOLDER, Entity::PLACEHOLDER, Entity::PLACEHOLDER);
    let mut boxed = parent.spawn((
        Node {
            height: px(56),
            padding: UiRect::horizontal(px(16)),
            align_items: AlignItems::Center,
            border: UiRect::all(px(1)),
            overflow: Overflow::clip(),
            ..default()
        },
        BackgroundColor(K45),
        BorderColor::all(STROKE_HI),
    ));
    boxed.with_children(|b| {
        let mut ed = EditableText::new(initial);
        ed.allow_newlines = false;
        ed.max_characters = Some(NAME_MAX);
        b.spawn((
            NameEditor,
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
            EditableTextFilter::new(name_char_ok),
        ));
        b.spawn((Node { align_items: AlignItems::Center, ..default() }, Pickable::IGNORE)).with_children(|row| {
            before = row.spawn(text("", r.color)).id();
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
                            Pickable::IGNORE,
                        ))
                        .id();
                })
                .id();
            after = row.spawn(text("", r.color)).id();
            placeholder = row.spawn(text(PLACEHOLDER, TEXT_LOW)).id();
        });
    });
    boxed.insert(Mirror {
        before,
        after,
        caret,
        caret_holder,
        placeholder,
        shown: None,
        value: initial.to_string(),
        since: 0.0,
    });
}

/// The field keeps the keyboard while the prompt is open.
fn keep_focus(editors: Query<Entity, With<NameEditor>>, mut input: ResMut<InputFocus>) {
    if let Some(e) = editors.iter().next()
        && input.get() != Some(e)
    {
        input.set(e, FocusCause::Navigated);
    }
}

/// Esc does nothing while the prompt is open: it needs a name.
fn keep_esc(mut esc: ResMut<crate::screens::EscPress>) {
    esc.take();
}

/// Enter or CONFIRM saves a valid name, USE <name> saves the suggestion. Esc does nothing: the prompt
/// needs a name.
fn act(
    mut keys: ResMut<ButtonInput<KeyCode>>,
    buttons: Query<(&Interaction, &PromptButton, Has<Disabled>), Changed<Interaction>>,
    editors: Query<&EditableText, With<NameEditor>>,
    mut first: ResMut<FirstRun>,
    mut screens: ResMut<Screens>,
    mut session: ResMut<Session>,
    mut profile: ResMut<PlayerProfile>,
    mut input: ResMut<InputFocus>,
) {
    let Some(editor) = editors.iter().next() else { return };
    let typed = validate_name(&editor.value().to_string()).ok();
    let enter = keys.any_just_pressed([KeyCode::Enter, KeyCode::NumpadEnter]) && !editor.is_composing();
    let mut chosen = if enter { typed.clone() } else { None };
    for (i, b, disabled) in &buttons {
        if *i != Interaction::Pressed || disabled {
            continue;
        }
        chosen = match b {
            PromptButton::Confirm => typed.clone(),
            PromptButton::Suggest => Some(first.suggested.clone()),
        };
    }
    let Some(name) = chosen else { return };
    // Hello carries the name, so it is set before anything can connect.
    session.local_name.clone_from(&name);
    profile.name = name;
    if let Err(e) = crate::user_config::save(PlayerProfile::FILE, &*profile) {
        warn!("cannot save the player profile: {e}");
    }
    first.pending = false;
    if screens.top() == Some(Screen::NamePrompt) {
        screens.pop();
    }
    input.clear();
    // The Enter that confirmed must not also press the menu's focused row.
    keys.clear_just_pressed(KeyCode::Enter);
    keys.clear_just_pressed(KeyCode::NumpadEnter);
}

/// Draw the value (upper case, letter-spaced), the placeholder and the blinking caret.
fn mirror(
    mut fields: Query<&mut Mirror>,
    editors: Query<&EditableText, With<NameEditor>>,
    time: Res<Time>,
    mut texts: Query<&mut Text>,
    mut nodes: Query<&mut Node>,
    mut colors: Query<&mut BackgroundColor>,
) {
    let now = time.elapsed_secs();
    let Some(ed) = editors.iter().next() else { return };
    for mut f in &mut fields {
        let value = ed.value().to_string();
        if value != f.value {
            f.value.clone_from(&value);
            f.since = now;
        }
        let cursor = ed.editor().raw_selection().focus().index();
        let parts = split_at_cursor(&value.to_uppercase(), cursor);
        if f.shown.as_ref() != Some(&parts) {
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
                let spacing = TextRole::PlayerName.spacing_px();
                n.left = px(if parts.1.is_empty() && !value.is_empty() { 4.0 } else { -(spacing / 2.0) - 1.0 });
            }
            if let Ok(mut n) = nodes.get_mut(f.caret_holder) {
                n.margin.right = px(if value.is_empty() { 6.0 } else { 0.0 });
            }
            f.shown = Some(parts);
        }
        if let Ok(mut c) = colors.get_mut(f.caret) {
            let want = fade(TEAL, caret_alpha(now - f.since));
            if c.0 != want {
                c.0 = want;
            }
        }
    }
}

/// Split `display` (ASCII: the filter only lets ASCII in) at the caret's byte index.
fn split_at_cursor(display: &str, cursor: usize) -> (String, String) {
    let at = cursor.min(display.len());
    match (display.get(..at), display.get(at..)) {
        (Some(a), Some(b)) => (a.to_string(), b.to_string()),
        _ => (display.to_string(), String::new()),
    }
}

/// The CSS caret blink, `steps(1)` over 1 s: full for half a second, then .35.
fn caret_alpha(t: f32) -> f32 {
    if t.rem_euclid(1.0) < 0.5 { 1.0 } else { 0.35 }
}

fn counter_text(value: &str) -> String {
    format!("{} / {NAME_MAX}", value.chars().count())
}

/// How the field reads for a typed value: help text, its colour and the box's border.
fn field_state(value: &str) -> (String, Color, Color) {
    match validate_name(value) {
        Ok(name) => (format!("Others will see you as {name}."), GOOD, STROKE_HI),
        Err(NameError::Empty) => (NameError::Empty.message(), TEXT_MID, STROKE_HI),
        // Not wrong yet, just not done: the kit's "invalid but editable" warn look.
        Err(e @ NameError::TooShort) => (e.message(), WARN, WARN),
        Err(e) => (e.message(), BAD, BAD),
    }
}

/// Live validation: the help line, the counter, the border and CONFIRM follow what is typed.
fn validation(
    mut commands: Commands,
    mut fields: Query<(&Mirror, &mut BorderColor)>,
    mut help: Query<(&mut Text, &mut TextColor), (With<HelpLine>, Without<Counter>)>,
    mut counter: Query<&mut Text, (With<Counter>, Without<HelpLine>)>,
    confirm: Query<(Entity, &PromptButton, Has<Disabled>)>,
    mut last: Local<Option<String>>,
) {
    let Some((f, mut border)) = fields.iter_mut().next() else {
        *last = None;
        return;
    };
    if last.as_deref() == Some(f.value.as_str()) {
        return;
    }
    *last = Some(f.value.clone());
    let (message, color, edge) = field_state(&f.value);
    *border = BorderColor::all(edge);
    for (mut t, mut c) in &mut help {
        t.0.clone_from(&message);
        c.0 = color;
    }
    for mut t in &mut counter {
        t.0 = counter_text(&f.value);
    }
    let valid = validate_name(&f.value).is_ok();
    for (e, b, disabled) in &confirm {
        if *b != PromptButton::Confirm || disabled != valid {
            continue;
        }
        if valid {
            commands.entity(e).remove::<Disabled>();
        } else {
            commands.entity(e).insert(Disabled);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_callsigns_are_trimmed_folded_and_upper_cased() {
        assert_eq!(validate_name("Kestrel 7"), Ok("KESTREL 7".into()));
        assert_eq!(validate_name("  a.b   c-d "), Ok("A.B C-D".into()));
        assert_eq!(validate_name("x_y"), Ok("X_Y".into()));
        assert_eq!(validate_name("abc"), Ok("ABC".into()), "3 is enough");
        assert_eq!(validate_name(&"z".repeat(16)), Ok("Z".repeat(16)), "16 fits");
        assert_eq!(validate_name(" a  b "), Ok("A B".into()), "inner spaces count once");
    }

    #[test]
    fn invalid_callsigns_say_why() {
        assert_eq!(validate_name(""), Err(NameError::Empty));
        assert_eq!(validate_name("    "), Err(NameError::Empty));
        assert_eq!(validate_name("ab"), Err(NameError::TooShort));
        assert_eq!(validate_name(" a b "), Ok("A B".into()));
        assert_eq!(validate_name("  ab  "), Err(NameError::TooShort), "spaces do not count");
        assert_eq!(validate_name(&"z".repeat(17)), Err(NameError::TooLong));
        assert_eq!(validate_name("kés"), Err(NameError::BadChar('é')));
        assert_eq!(validate_name("a\tbc"), Err(NameError::BadChar('\t')));
        assert_eq!(validate_name("ash!"), Err(NameError::BadChar('!')));
        for e in [NameError::Empty, NameError::TooShort, NameError::TooLong, NameError::BadChar('!')] {
            assert!(!e.message().is_empty());
        }
        assert!(NameError::TooShort.message().contains('3'));
        assert!(NameError::TooLong.message().contains("16"));
        assert!(NameError::BadChar('!').message().contains('!'));
    }

    #[test]
    fn the_field_filter_matches_the_rules() {
        for c in ['a', 'Z', '0', ' ', '-', '_', '.'] {
            assert!(name_char_ok(c), "{c:?}");
        }
        for c in ['!', 'é', '\t', '/', '\'', '\u{0}'] {
            assert!(!name_char_ok(c), "{c:?}");
        }
        assert_eq!(PlayerProfile::name_char_ok('.'), name_char_ok('.'));
        assert_eq!(PlayerProfile::clean_name("ok name"), Some("OK NAME".into()));
        assert_eq!(PlayerProfile::clean_name("no"), None);
    }

    #[test]
    fn outside_names_are_sanitised_leniently() {
        assert_eq!(sanitize_name("Juno Vance"), Some("JUNO VANCE".into()));
        assert_eq!(sanitize_name("jörg"), Some("JRG".into()));
        assert_eq!(sanitize_name("ab"), Some("AB".into()), "a short name saved under older rules survives");
        assert_eq!(sanitize_name("@@ !"), None);
        assert_eq!(sanitize_name("abcdefghijklmno pq"), Some("ABCDEFGHIJKLMNO".into()), "cut, no trailing space");
        assert_eq!(sanitize_name("a\tb"), Some("A B".into()));
    }

    #[test]
    fn the_suggestion_is_a_generated_callsign() {
        assert_eq!(suggest_name(42), "AGENT-0042");
        assert_eq!(suggest_name(123_456), "AGENT-3456");
        for seed in [0, 7, 9_999, u32::MAX] {
            assert!(validate_name(&suggest_name(seed)).is_ok(), "{seed}");
        }
    }

    #[test]
    fn until_a_name_is_chosen_the_player_is_unknown() {
        // Never the OS user name: friends would see it behind the prompt, in lobbies and the kill feed.
        assert_eq!(crate::config::default_name(), "UNKNOWN");
        assert_eq!(PlayerProfile::default().name, "UNKNOWN");
        assert!(validate_name(crate::config::UNNAMED).is_ok());
        let unnamed = PlayerProfile::default();
        let saved = PlayerProfile { name: "KESTREL 7".into() };
        assert_eq!(starting_name(&cli(), &unnamed), "UNKNOWN", "no profile, no --name");
        assert_eq!(starting_name(&cli(), &saved), "KESTREL 7", "the saved name wins");
        let named = Cli { name: "ASH".into(), name_given: true, ..cli() };
        assert_eq!(starting_name(&named, &saved), "ASH", "--name overrides it for the run");
        assert_eq!(starting_name(&named, &unnamed), "ASH");
    }

    fn cli() -> Cli {
        Cli { name: "T".into(), ..Cli::default() }
    }

    #[test]
    fn only_the_first_interactive_launch_asks() {
        assert!(should_prompt(&cli(), false), "first launch");
        assert!(!should_prompt(&cli(), true), "a profile was saved");
        assert!(!should_prompt(&Cli { name_given: true, ..cli() }, false), "--name wins for the run");
        assert!(!should_prompt(&Cli { host: Some("range".into()), ..cli() }, false));
        assert!(!should_prompt(&Cli { join: Some("1.2.3.4".into()), ..cli() }, false));
        assert!(!should_prompt(&Cli { bot: true, ..cli() }, false));
        assert!(!should_prompt(&Cli { screenshot: Some("x.png".into()), ..cli() }, false));
        assert!(!should_prompt(&Cli { demo_ui: Some("menu-join".into()), ..cli() }, false), "other demos");
        assert!(should_prompt(&Cli { demo_ui: Some("first-run".into()), ..cli() }, true), "its own demo");
        assert!(should_prompt(
            &Cli { demo_ui: Some("first-run-valid".into()), screenshot: Some("x.png".into()), ..cli() },
            true
        ));
        assert!(!should_prompt(&Cli { demo_ui: Some("first-run".into()), host: Some("range".into()), ..cli() }, false));
        assert_eq!(demo_text("first-run"), Some(""));
        assert!(demo_text("first-run-invalid").is_some_and(|t| validate_name(t).is_err()));
        assert!(demo_text("first-run-valid").is_some_and(|t| validate_name(t).is_ok()));
        assert_eq!(demo_text("loadout"), None);
    }

    #[test]
    fn the_field_reads_as_typed() {
        assert_eq!(field_state("").1, TEXT_MID, "empty: the rules, neutral");
        assert_eq!(field_state("K7").2, WARN, "too short: not done yet");
        assert_eq!(field_state("K7!").2, BAD, "a bad character is an error");
        let (msg, color, _) = field_state("kestrel 7");
        assert_eq!((msg.as_str(), color), ("Others will see you as KESTREL 7.", GOOD));
        assert_eq!(counter_text("abc"), "3 / 16");
        assert_eq!(split_at_cursor("ABC", 1), ("A".into(), "BC".into()));
        assert_eq!(split_at_cursor("ABC", 9), ("ABC".into(), String::new()));
        assert_eq!(caret_alpha(0.2), 1.0);
        assert_eq!(caret_alpha(0.7), 0.35);
    }
}
