//! The Settings hub screen (hub spec 07-13, mockups 08-08e): a tab rail (gameplay, mouse & aim, keybinds,
//! video, audio, HUD & accessibility) over one shared frame. It opens over the main menu or the match
//! (`Screen::Settings(tab)`) on the last tab used. Every control writes [`Settings`] at once; the screen
//! saves `settings.ron` in the user's config folder half a second after the last change, and on DONE / BACK.
//!
//! The frame lives here; each tab's columns are built by `tabs::build` from the control kit in `controls.rs`
//! (`keybinds.rs` for the key map).

// Parts of the control kit wait for their tabs.
#![allow(dead_code)]

mod bindings;
mod controls;
mod keybinds;
mod model;
mod tabs;

// The tabs and the game read these (sensitivity, field of view, key map, crosshair).
#[allow(unused_imports)]
pub use bindings::*;
#[allow(unused_imports)]
pub use model::*;

use crate::AppState;
use crate::config::Cli;
use crate::screens::{EscPress, EscSystems, Screen, ScreenRoot, Screens, SettingsTab, screen_on_top};
use crate::ui_kit::{self as kit, *};
use crate::user_config::{self, PlayerProfile};
use bevy::input_focus::InputFocus;
use bevy::prelude::*;
use bevy::ui::{ColorStop, InterpolationColorSpace, LinearGradient};
use controls::{Field, Kit, Live, UiState};
use keybinds::Listening;

/// Glyphs Barlow lacks (arrows, pad buttons): DejaVu Sans Bold, subset.
#[derive(Resource, Clone)]
pub struct SymbolFont(pub Handle<Font>);

pub struct SettingsScreenPlugin;

impl Plugin for SettingsScreenPlugin {
    fn build(&self, app: &mut App) {
        let data = load_data();
        let mut settings: Settings = user_config::load_or_default(FILE);
        settings.complete(&data);
        // An older file moves to today's defaults where it still holds the old ones, once: save it at the new
        // version straight away.
        if settings.migrate(&data.defaults) {
            info!("settings: migrated {FILE} to version {SETTINGS_VERSION}");
            if let Err(e) = user_config::save(FILE, &settings) {
                warn!("cannot save migrated settings: {e}");
            }
        }
        let on_top = || screen_on_top(Screen::Settings(SettingsTab::Gameplay));
        app.insert_resource(data)
            .insert_resource(settings)
            .init_resource::<UiState>()
            .init_resource::<Listening>()
            .init_resource::<SaveTimer>()
            .add_systems(Startup, load_symbols)
            .add_plugins(tabs::plugin)
            .add_systems(
                Update,
                (
                    demo_open,
                    read_display,
                    spawn_screen.run_if(resource_exists::<SymbolFont>),
                    // A listening key cap, then an edited field or an open list, take Esc before BACK.
                    (keybinds::capture, esc).chain().in_set(EscSystems::Top).run_if(on_top()),
                    (controls::commit_left_edit, rail_clicks, hotkeys, footer_clicks, rebuild_pane)
                        .chain()
                        .run_if(on_top()),
                    (
                        controls::seg_input,
                        controls::switch_input,
                        controls::slider_input,
                        controls::field_input,
                        controls::dropdown_input,
                        controls::scroll_dropdown,
                        keybinds::cap_clicks,
                    )
                        .run_if(on_top()),
                    (
                        controls::sync_controls,
                        controls::seg_z,
                        controls::sync_dropdowns,
                        controls::sync_live,
                        keybinds::sync_caps,
                        rail_visuals,
                    )
                        .run_if(on_top()),
                    save_soon,
                )
                    .chain(),
            );
    }
}

fn load_symbols(server: Res<AssetServer>, mut commands: Commands) {
    commands.insert_resource(SymbolFont(server.load("fonts/DejaVuSans-Bold-Symbols.ttf")));
}

// ---------------------------------------------------------------------------------------------- frame

/// The pane the current tab fills (rebuilt when the tab changes).
#[derive(Component)]
struct Pane;

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
struct RailTab(Tab);

#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
enum SettingsBtn {
    Back,
    ResetAll,
    Done,
    ConfirmCancel,
    ConfirmReset,
}

/// The tab a screen push names, or the last one used when it names the default (the main menu's SETTINGS).
fn opening_tab(pushed: SettingsTab, last: Tab) -> Tab {
    if pushed == SettingsTab::default() { last } else { Tab::from_screen(pushed) }
}

fn top_tab(screens: &Screens) -> Option<SettingsTab> {
    match screens.top() {
        Some(Screen::Settings(t)) => Some(t),
        _ => None,
    }
}

#[allow(clippy::too_many_arguments)]
fn spawn_screen(
    mut screens: ResMut<Screens>,
    roots: Query<&ScreenRoot>,
    mut settings: ResMut<Settings>,
    mut ui: ResMut<UiState>,
    mut listening: ResMut<Listening>,
    fonts: Res<UiFonts>,
    mut commands: Commands,
) {
    let Some(pushed) = top_tab(&screens) else { return };
    if roots.iter().any(|r| matches!(r.0, Screen::Settings(_))) {
        return;
    }
    // A fresh screen: nothing left over from one that was closed from outside (match end, a disconnect).
    *listening = Listening::default();
    ui.confirm = None;
    ui.dropdown = None;
    ui.editing = None;
    let tab = opening_tab(pushed, settings.last_tab);
    screens.replace_top(Screen::Settings(tab.screen()));
    if settings.last_tab != tab {
        settings.last_tab = tab;
    }
    let depth = screens.iter().position(|s| matches!(s, Screen::Settings(_))).unwrap_or(0) as i32;
    let fonts = &*fonts;
    commands
        .spawn((
            ScreenRoot(Screen::Settings(tab.screen())),
            GlobalZIndex(100 + depth * 10),
            Node {
                position_type: PositionType::Absolute,
                width: percent(100),
                height: percent(100),
                overflow: Overflow::clip(),
                ..default()
            },
            BackgroundColor(BG0),
        ))
        .with_children(|r| {
            r.spawn(page_background(60.0, 30.0, [(0x141B25, 0.0), (0x090C11, 60.0), (0x06080B, 100.0)]));
            // Top bar: title, the save hint, BACK [ESC].
            r.spawn((
                Node {
                    height: px(84),
                    align_items: AlignItems::Center,
                    padding: UiRect::horizontal(px(48)),
                    column_gap: px(24),
                    border: UiRect::bottom(px(1)),
                    ..abs(Some(0.0), Some(0.0), Some(0.0), None)
                },
                BorderColor::all(STROKE),
            ))
            .with_children(|t| {
                t.spawn(fonts.role(TextRole::ScreenTitle, "Settings"));
                t.spawn(Node { flex_grow: 1.0, ..default() });
                t.spawn((Live::TopHint, fonts.text("", Face::Display, 600, 14.0, TEXT_MID, 0.14)));
                t.spawn((SettingsBtn::Back, button_with_key(fonts, "Back", "Esc", BtnKind::Normal, BtnSize::M)));
            });
            // Tab rail.
            r.spawn(Node {
                width: px(260),
                flex_direction: FlexDirection::Column,
                ..abs(Some(48.0), None, Some(112.0), None)
            })
            .with_children(|rail| {
                for t in Tab::ALL {
                    rail.spawn((
                        RailTab(t),
                        Button,
                        Node {
                            height: px(52),
                            align_items: AlignItems::Center,
                            padding: UiRect::left(px(18)),
                            border: UiRect::left(px(3)),
                            ..default()
                        },
                        BorderColor::all(Color::NONE),
                        BackgroundColor(Color::NONE),
                        children![fonts.role_color(TextRole::RailTab, t.label(), TEXT_MID)],
                    ));
                }
            });
            // The tab's columns.
            r.spawn((Pane, Node { column_gap: px(24), ..abs(Some(340.0), Some(48.0), Some(112.0), Some(104.0)) }));
            // Bottom bar: Q E TABS · R RESET TAB, RESET ALL, DONE.
            r.spawn((
                Node {
                    height: px(80),
                    align_items: AlignItems::Center,
                    padding: UiRect::horizontal(px(48)),
                    column_gap: px(12),
                    border: UiRect::top(px(1)),
                    ..abs(Some(0.0), Some(0.0), None, Some(0.0))
                },
                BorderColor::all(STROKE),
                BackgroundColor(BOTTOM_BAR),
            ))
            .with_children(|b| {
                b.spawn(Node { column_gap: px(7), align_items: AlignItems::Center, ..default() }).with_children(|h| {
                    h.spawn(keycap(fonts, "Q", KeyStyle::Ghost, 22.0));
                    h.spawn(keycap(fonts, "E", KeyStyle::Ghost, 22.0));
                    h.spawn(fonts.role(TextRole::Hint, "Tabs"));
                });
                b.spawn(Node {
                    column_gap: px(7),
                    align_items: AlignItems::Center,
                    margin: UiRect::left(px(18)),
                    ..default()
                })
                .with_children(|h| {
                    h.spawn(keycap(fonts, "R", KeyStyle::Ghost, 22.0));
                    h.spawn(fonts.role(TextRole::Hint, "Reset tab"));
                });
                b.spawn(Node { flex_grow: 1.0, ..default() });
                b.spawn((SettingsBtn::ResetAll, button(fonts, "Reset all", BtnKind::Normal, BtnSize::M)));
                b.spawn((SettingsBtn::Done, button(fonts, "Done", BtnKind::Primary, BtnSize::M)));
            });
        });
}

/// The pane shows the top screen's tab: rebuilt when the tab changes (or the screen was just spawned).
#[allow(clippy::too_many_arguments)]
fn rebuild_pane(
    screens: Res<Screens>,
    pane: Query<Entity, With<Pane>>,
    added: Query<(), Added<Pane>>,
    settings: Res<Settings>,
    mut ui: ResMut<UiState>,
    data: Res<SettingsData>,
    profile: Res<PlayerProfile>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    symbols: Res<SymbolFont>,
    mut shown: Local<Option<Tab>>,
    mut commands: Commands,
) {
    let Some(tab) = top_tab(&screens).map(Tab::from_screen) else { return };
    let Some(pane) = pane.iter().next() else { return };
    if *shown == Some(tab) && added.is_empty() {
        return;
    }
    *shown = Some(tab);
    controls::close_dropdown(&mut commands, &mut ui);
    let k = Kit {
        fonts: &fonts,
        images: &images,
        symbols: symbols.0.clone(),
        s: &settings,
        ui: &ui,
        data: &data,
        profile: &profile,
    };
    commands.entity(pane).despawn_children().with_children(|p| tabs::build(p, &k, tab));
}

fn rail_visuals(
    screens: Res<Screens>,
    mut tabs: Query<(&RailTab, &Interaction, &mut BorderColor, &mut BackgroundGradient, &Children)>,
    added: Query<(), Added<RailTab>>,
    mut texts: Query<&mut TextColor>,
    mut missing: Query<(Entity, &RailTab), Without<BackgroundGradient>>,
    mut commands: Commands,
) {
    // The selected tab's fade (90deg, white .07 to 0) is a gradient component, added once.
    for (e, _) in &mut missing {
        commands.entity(e).insert(BackgroundGradient::default());
    }
    let Some(current) = top_tab(&screens).map(Tab::from_screen) else { return };
    let _ = &added;
    for (t, i, mut border, mut grad, kids) in &mut tabs {
        let on = t.0 == current;
        *border = BorderColor { left: if on { TEXT_HI } else { Color::NONE }, ..BorderColor::all(Color::NONE) };
        let want = if on {
            BackgroundGradient::from(LinearGradient {
                angle: LinearGradient::TO_RIGHT,
                stops: vec![
                    ColorStop::new(kit::white(0.07), percent(0)),
                    ColorStop::new(kit::white(0.0), percent(100)),
                ],
                color_space: InterpolationColorSpace::Srgba,
            })
        } else {
            BackgroundGradient::default()
        };
        if *grad != want {
            *grad = want;
        }
        let ink = if on || *i != Interaction::None { TEXT_HI } else { TEXT_MID };
        for c in kids.iter() {
            if let Ok(mut col) = texts.get_mut(c)
                && col.0 != ink
            {
                col.0 = ink;
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------- input

fn switch_tab(screens: &mut Screens, settings: &mut ResMut<Settings>, tab: Tab) {
    screens.replace_top(Screen::Settings(tab.screen()));
    controls::edit(settings, |s| s.last_tab = tab);
}

fn rail_clicks(
    q: Query<(&Interaction, &RailTab), Changed<Interaction>>,
    mut screens: ResMut<Screens>,
    mut settings: ResMut<Settings>,
) {
    for (i, t) in &q {
        if *i == Interaction::Pressed {
            switch_tab(&mut screens, &mut settings, t.0);
        }
    }
}

/// Q / E: previous / next tab, R: reset this tab. Off while a field is edited, a key cap listens, or a list
/// or the RESET ALL confirm is open.
fn hotkeys(
    keys: Res<ButtonInput<KeyCode>>,
    focus: Res<InputFocus>,
    fields: Query<(), With<Field>>,
    listening: Res<Listening>,
    ui: Res<UiState>,
    data: Res<SettingsData>,
    mut screens: ResMut<Screens>,
    mut settings: ResMut<Settings>,
) {
    let busy = focus.get().is_some_and(|e| fields.contains(e))
        || listening.target.is_some()
        || ui.dropdown.is_some()
        || ui.confirm.is_some();
    if busy {
        return;
    }
    let Some(tab) = top_tab(&screens).map(Tab::from_screen) else { return };
    if keys.just_pressed(KeyCode::KeyQ) {
        switch_tab(&mut screens, &mut settings, tab.step(-1));
    } else if keys.just_pressed(KeyCode::KeyE) {
        switch_tab(&mut screens, &mut settings, tab.step(1));
    } else if keys.just_pressed(KeyCode::KeyR) {
        controls::edit(&mut settings, |s| s.reset_tab(tab, &data.defaults));
    }
}

/// Esc: cancel a field edit, close a list or the confirm; otherwise save and let the default BACK close the
/// screen (`screens::back_on_esc`). A listening key cap took its Esc already (`keybinds::capture`).
#[allow(clippy::too_many_arguments)]
fn esc(
    mut esc: ResMut<EscPress>,
    mut focus: ResMut<InputFocus>,
    fields: Query<(), With<Field>>,
    mut ui: ResMut<UiState>,
    settings: Res<Settings>,
    mut timer: ResMut<SaveTimer>,
    mut commands: Commands,
) {
    if !esc.pending() {
        return;
    }
    if controls::cancel_field_edit(&mut focus, &fields, &mut ui) {
        esc.take();
    } else if ui.dropdown.is_some() {
        controls::close_dropdown(&mut commands, &mut ui);
        esc.take();
    } else if let Some(c) = ui.confirm.take() {
        commands.entity(c).despawn();
        esc.take();
    } else {
        save_now(&settings, &mut ui, &mut timer);
    }
}

#[allow(clippy::too_many_arguments)]
fn footer_clicks(
    q: Query<(&Interaction, &SettingsBtn), Changed<Interaction>>,
    mut screens: ResMut<Screens>,
    mut settings: ResMut<Settings>,
    mut ui: ResMut<UiState>,
    mut timer: ResMut<SaveTimer>,
    data: Res<SettingsData>,
    fonts: Res<UiFonts>,
    roots: Query<(Entity, &ScreenRoot)>,
    mut commands: Commands,
) {
    for (i, b) in &q {
        if *i != Interaction::Pressed {
            continue;
        }
        match b {
            SettingsBtn::Back | SettingsBtn::Done => {
                save_now(&settings, &mut ui, &mut timer);
                screens.pop();
            }
            SettingsBtn::ResetAll if ui.confirm.is_none() => {
                let Some((root, _)) = roots.iter().find(|(_, r)| matches!(r.0, Screen::Settings(_))) else { continue };
                let modal = confirm_modal(&mut commands, &fonts);
                commands.entity(root).add_child(modal);
                ui.confirm = Some(modal);
            }
            SettingsBtn::ResetAll => {}
            SettingsBtn::ConfirmCancel => {
                if let Some(c) = ui.confirm.take() {
                    commands.entity(c).despawn();
                }
            }
            SettingsBtn::ConfirmReset => {
                controls::edit(&mut settings, |s| s.reset_all(&data.defaults));
                if let Some(c) = ui.confirm.take() {
                    commands.entity(c).despawn();
                }
            }
        }
    }
}

/// 'Reset all settings to default?' with CANCEL and RESET ALL (danger).
fn confirm_modal(commands: &mut Commands, fonts: &UiFonts) -> Entity {
    commands
        .spawn((
            Node {
                width: percent(100),
                height: percent(100),
                justify_content: JustifyContent::Center,
                align_items: AlignItems::Center,
                ..abs(Some(0.0), None, Some(0.0), None)
            },
            BackgroundColor(MODAL_BACKDROP),
            ZIndex(50),
            // Clicks on the backdrop go nowhere else.
            Button,
        ))
        .with_children(|m| {
            m.spawn(kit::panel_of(
                PanelKind::Popover,
                Node {
                    width: px(520),
                    flex_direction: FlexDirection::Column,
                    row_gap: px(14),
                    padding: UiRect::axes(px(28), px(24)),
                    ..default()
                },
            ))
            .with_children(|p| {
                p.spawn(fonts.role(TextRole::ModalTitle, "Reset all settings?"));
                p.spawn(fonts.role(
                    TextRole::ModalBody,
                    "Every tab goes back to its defaults: mouse, keybinds, video, audio and HUD.",
                ));
                p.spawn(Node {
                    column_gap: px(12),
                    justify_content: JustifyContent::FlexEnd,
                    margin: UiRect::top(px(8)),
                    ..default()
                })
                .with_children(|b| {
                    b.spawn((SettingsBtn::ConfirmCancel, button(fonts, "Cancel", BtnKind::Normal, BtnSize::M)));
                    b.spawn((SettingsBtn::ConfirmReset, button(fonts, "Reset all", BtnKind::Danger, BtnSize::M)));
                });
            });
        })
        .id()
}

// ---------------------------------------------------------------------------------------------- saving

/// Seconds until the next save (none pending).
#[derive(Resource, Default)]
struct SaveTimer(Option<f32>);

const SAVE_DELAY_S: f32 = 0.5;

fn save_now(settings: &Settings, ui: &mut UiState, timer: &mut SaveTimer) {
    timer.0 = None;
    match user_config::save(FILE, settings) {
        Ok(()) => ui.save_error = None,
        Err(e) => {
            warn!("cannot save settings: {e}");
            ui.save_error = Some(e);
        }
    }
}

/// Save half a second after the last change.
fn save_soon(settings: Res<Settings>, mut ui: ResMut<UiState>, mut timer: ResMut<SaveTimer>, time: Res<Time>) {
    if settings.is_changed() && !settings.is_added() {
        timer.0 = Some(SAVE_DELAY_S);
    }
    if let Some(t) = timer.0.as_mut() {
        *t -= time.delta_secs();
        if *t <= 0.0 {
            save_now(&settings, &mut ui, &mut timer);
        }
    }
}

// ---------------------------------------------------------------------------------------------- display, demo

/// The monitor's modes and refresh rate, for VIDEO's resolution and frame-limit lists.
fn read_display(
    monitors: Query<(&bevy::window::Monitor, Has<bevy::window::PrimaryMonitor>)>,
    mut ui: ResMut<UiState>,
    mut done: Local<bool>,
) {
    if *done {
        return;
    }
    let Some((m, _)) = monitors.iter().find(|(_, p)| *p).or_else(|| monitors.iter().next()) else { return };
    *done = true;
    let mut modes: Vec<Resolution> = m
        .video_modes
        .iter()
        .map(|v| Resolution {
            width: v.physical_size.x,
            height: v.physical_size.y,
            refresh_mhz: v.refresh_rate_millihertz,
        })
        .collect();
    modes.sort_by_key(|r| std::cmp::Reverse((r.width, r.height, r.refresh_mhz)));
    modes.dedup();
    ui.display = controls::DisplayInfo {
        modes,
        native: Some(Resolution {
            width: m.physical_width,
            height: m.physical_height,
            refresh_mhz: m.refresh_rate_millihertz.unwrap_or(0),
        }),
        refresh_hz: m.refresh_rate_millihertz.map(|mhz| (mhz + 500) / 1000),
    };
}

/// `--demo-ui settings-gameplay | settings-mouse | settings-keybinds | settings-video | settings-audio |
/// settings-hud`: open Settings on that tab from the main menu, for screenshots.
fn demo_open(
    cli: Res<Cli>,
    state: Res<State<AppState>>,
    mut screens: ResMut<Screens>,
    mut settings: ResMut<Settings>,
    mut done: Local<bool>,
) {
    let Some(demo) = cli.demo_ui.as_deref().and_then(|d| d.strip_prefix("settings-")) else { return };
    if *done || *state.get() != AppState::MainMenu || !screens.is_empty() {
        return;
    }
    let tab = match demo {
        "gameplay" => Tab::Gameplay,
        "mouse" => Tab::MouseAim,
        "keybinds" => Tab::Keybinds,
        "video" => Tab::Video,
        "audio" => Tab::Audio,
        "hud" => Tab::Hud,
        _ => return,
    };
    *done = true;
    // GAMEPLAY is also the "last tab" push (see `opening_tab`), so the last tab is set first.
    settings.last_tab = tab;
    screens.push(Screen::Settings(tab.screen()));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn settings_open_on_the_tab_asked_for_or_the_last_one() {
        assert_eq!(opening_tab(SettingsTab::Keybinds, Tab::Video), Tab::Keybinds, "KEY REFERENCE opens keybinds");
        assert_eq!(opening_tab(SettingsTab::default(), Tab::Video), Tab::Video, "the main menu opens the last tab");
        assert_eq!(Tab::Gameplay.step(-1), Tab::Hud, "Q wraps");
        assert_eq!(Tab::Hud.step(1), Tab::Gameplay, "E wraps");
    }
}
