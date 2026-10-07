//! Main menu (after design/ui/mockups/png/04_main_menu.png): host, gun range, join by code, quit.

use crate::AppState;
use crate::config::Data;
use crate::net::{NetRequest, Session};
use bevy::input_focus::{FocusCause, InputFocus};
use bevy::prelude::*;
use bevy::text::{EditableText, TextCursorStyle};

pub struct MenuPlugin;

impl Plugin for MenuPlugin {
    fn build(&self, app: &mut App) {
        app.add_systems(OnEnter(AppState::MainMenu), spawn_menu)
            .add_systems(Update, (menu_buttons, update_status, button_hover).run_if(in_state(AppState::MainMenu)));
    }
}

#[derive(Component, Clone, Copy)]
enum MenuAction {
    HostTdm,
    GunRange,
    Join,
    Quit,
}

#[derive(Component)]
struct JoinField;

#[derive(Component)]
struct StatusLine;

const INK: Color = Color::srgb(0.93, 0.94, 0.95);
const MUTED: Color = Color::srgb(0.55, 0.59, 0.66);
const TEAL: Color = Color::srgb(0.0, 0.70, 0.62);
const BUTTON: Color = Color::srgba(1.0, 1.0, 1.0, 0.0);
const BUTTON_HOVER: Color = Color::srgba(1.0, 1.0, 1.0, 0.08);

fn text(s: impl Into<String>, size: f32, color: Color) -> (Text, TextFont, TextColor) {
    (Text::new(s), TextFont::from_font_size(size), TextColor(color))
}

fn big_button(label: &str, hint: &str, action: MenuAction) -> impl Bundle {
    (
        Button,
        action,
        Node {
            width: px(520),
            padding: UiRect::axes(px(14), px(8)),
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::Center,
            border: UiRect::left(px(3)),
            ..default()
        },
        BorderColor::all(Color::NONE),
        BackgroundColor(BUTTON),
        children![(text(label, 40.0, INK)), (text(hint, 13.0, MUTED))],
    )
}

fn spawn_menu(mut commands: Commands, data: Res<Data>, session: Res<Session>) {
    commands
        .spawn((
            DespawnOnExit(AppState::MainMenu),
            Node {
                width: percent(100),
                height: percent(100),
                flex_direction: FlexDirection::Column,
                padding: UiRect::axes(px(96), px(72)),
                row_gap: px(14),
                ..default()
            },
            BackgroundColor(Color::srgb(0.035, 0.043, 0.06)),
        ))
        .with_children(|root| {
            root.spawn(text("SHARD/LINE", 72.0, INK));
            root.spawn((
                text("WORKING TITLE - PROTOTYPE 0.1", 14.0, TEAL),
                Node { margin: UiRect::bottom(px(48)), ..default() },
            ));
            root.spawn(big_button("HOST GAME", "SHOWHOME - TEAM DEATHMATCH", MenuAction::HostTdm));
            root.spawn(big_button("GUN RANGE", "THE YARD - FRIENDS CAN JOIN", MenuAction::GunRange));
            root.spawn((
                Node {
                    column_gap: px(12),
                    align_items: AlignItems::Center,
                    margin: UiRect::vertical(px(8)),
                    ..default()
                },
                children![
                    (
                        JoinField,
                        Node { width: px(330), padding: UiRect::all(px(8)), border: UiRect::all(px(2)), ..default() },
                        BorderColor::all(MUTED),
                        BackgroundColor(Color::srgb(0.07, 0.08, 0.1)),
                        EditableText { allow_newlines: false, max_characters: Some(40), ..default() },
                        TextFont::from_font_size(22.0),
                        TextColor(INK),
                        TextCursorStyle::default(),
                    ),
                    (
                        Button,
                        MenuAction::Join,
                        Node { padding: UiRect::axes(px(22), px(10)), ..default() },
                        BackgroundColor(Color::srgb(0.92, 0.91, 0.88)),
                        children![(text("JOIN GAME", 20.0, Color::BLACK))],
                    ),
                ],
            ));
            root.spawn(text("Enter a join code (XXXX-XXXX-XX) or an IP address, e.g. 192.168.1.20", 13.0, MUTED));
            root.spawn(big_button("QUIT", "", MenuAction::Quit));
            root.spawn((
                StatusLine,
                text(session.status.clone().unwrap_or_default(), 16.0, Color::srgb(1.0, 0.45, 0.4)),
            ));
            root.spawn((
                Node { position_type: PositionType::Absolute, right: px(32), bottom: px(24), ..default() },
                children![
                    (text(
                        format!(
                            "v0.1-proto  |  bevy 0.19  |  lightyear 0.30  |  udp {}  |  playing as {}",
                            data.net.port, session.local_name
                        ),
                        13.0,
                        MUTED
                    ))
                ],
            ));
        });
}

#[allow(clippy::too_many_arguments)]
fn menu_buttons(
    q: Query<(&Interaction, &MenuAction), Changed<Interaction>>,
    keys: Res<ButtonInput<KeyCode>>,
    focus: Res<InputFocus>,
    fields: Query<(Entity, &EditableText), With<JoinField>>,
    mut requests: MessageWriter<NetRequest>,
    mut exit: MessageWriter<AppExit>,
    mut session: ResMut<Session>,
) {
    let join_text = || fields.iter().next().map(|(_, f)| f.value().to_string()).unwrap_or_default();
    let join = |requests: &mut MessageWriter<NetRequest>, session: &mut Session| {
        let address = join_text();
        if address.trim().is_empty() {
            session.status = Some("type a join code or address first".into());
        } else {
            requests.write(NetRequest::Join { address });
        }
    };
    // Enter in the join field joins.
    if keys.just_pressed(KeyCode::Enter) && fields.iter().any(|(e, _)| focus.get() == Some(e)) {
        join(&mut requests, &mut session);
    }
    for (i, action) in &q {
        if *i != Interaction::Pressed {
            continue;
        }
        match action {
            MenuAction::HostTdm => {
                requests.write(NetRequest::Host { map: "showhome".into() });
            }
            MenuAction::GunRange => {
                requests.write(NetRequest::Host { map: "range".into() });
            }
            MenuAction::Join => join(&mut requests, &mut session),
            MenuAction::Quit => {
                exit.write(AppExit::Success);
            }
        }
    }
    let _ = FocusCause::Navigated;
}

fn update_status(session: Res<Session>, mut q: Query<&mut Text, With<StatusLine>>) {
    if session.is_changed() {
        for mut t in &mut q {
            t.0 = session.status.clone().unwrap_or_default();
        }
    }
}

fn button_hover(
    mut q: Query<
        (&Interaction, &mut BackgroundColor, Option<&mut BorderColor>),
        (Changed<Interaction>, With<Button>, With<MenuAction>),
    >,
) {
    for (i, mut bg, border) in &mut q {
        // Only the big transparent buttons get a hover band; the solid join button keeps its colour.
        if bg.0.alpha() >= 0.99 {
            continue;
        }
        let hovered = matches!(i, Interaction::Hovered | Interaction::Pressed);
        bg.0 = if hovered { BUTTON_HOVER } else { BUTTON };
        if let Some(mut b) = border {
            *b = BorderColor::all(if hovered { TEAL } else { Color::NONE });
        }
    }
}
