//! Settings ▸ MOUSE & AIM (mockup 08, the default tab): sensitivity as cm/360 with the DPI, the import box
//! and the ruler, ADS multipliers, field of view, and the crosshair editor with its code and a live preview.
//! The rows follow the game, not the mockup: one ADS row per optic group of settings.ron (THERMAL 4×
//! included), and VIEWMODEL FOV is dimmed until the gun has a camera of its own.

use crate::settings::controls::{
    Ch, Field, FieldKind, Kit, Live, Num, Tg, UiState, card, ctl, dropdown, field, get_num, h2, range, row, seg,
    set_num, slider, switch, text_as, unit,
};
use crate::settings::{
    CrosshairSettings, PreviewBg, SWATCHES, Settings, SettingsData, cm_from_sens, crosshair_rects, fmt_num, hex_string,
    parse_crosshair_code, rgb_color, ruler_px, sens_for,
};
use crate::ui_kit::{self as kit, Art, BtnKind, BtnSize, TextRole};
use bevy::clipboard::Clipboard;
use bevy::ecs::hierarchy::ChildSpawnerCommands;
use bevy::ecs::system::EntityCommands;
use bevy::input_focus::InputFocus;
use bevy::prelude::*;
use bevy::ui::widget::NodeImageMode;
use bevy::ui::{ColorStop, InterpolationColorSpace, LinearGradient, UiSystems};

/// The turn distance field's border shows TEXT_HI this long after APPLY.
const APPLY_FLASH_S: f32 = 0.3;
/// The crosshair code shows TEAL this long after it was copied or pasted.
const CODE_FLASH_S: f32 = 1.0;
/// The part of `hud_street.jpg` (1920x1080) the preview shows: the mockup's cover fit, centred at 55 %.
const STREET_CROP: Rect = Rect { min: Vec2::new(0.0, 223.0), max: Vec2::new(1920.0, 897.0) };
/// Turn distance marks between the track's ends (cm).
const CM_MARKS: [f32; 3] = [30.0, 50.0, 65.0];

/// APPLY in the import box.
#[derive(Component)]
struct ApplyImport;

/// The crosshair code in the CROSSHAIR title: a click copies it, Ctrl+V pastes one.
#[derive(Component)]
struct CodeTag;

/// A colour swatch.
#[derive(Component, Clone, Copy)]
struct Swatch([u8; 3]);

/// The hex field after the swatches.
#[derive(Component)]
struct HexField;

/// The crosshair preview box (its fill and gradient are the WHITE WALL and SKY backgrounds).
#[derive(Component)]
struct Preview;

/// The STREET background.
#[derive(Component)]
struct StreetImage;

/// The preview's centre: the crosshair's rectangles are its children.
#[derive(Component)]
struct CrosshairOrigin;

pub fn build(p: &mut ChildSpawnerCommands, k: &Kit) {
    p.commands().queue(install_systems);
    super::col(p, |c| {
        sensitivity(c, k);
        aim_down_sights(c, k);
    });
    super::col(p, |c| {
        field_of_view(c, k);
        crosshair(c, k);
    });
}

// ---------------------------------------------------------------------------------------------- cards

fn sensitivity(p: &mut ChildSpawnerCommands, k: &Kit) {
    card(p, 0.0, 0.0, Node::default(), |c| {
        h2(c, k, "SENSITIVITY", Some(("RAW INPUT, NO ACCELERATION, NO SMOOTHING", None)), 0.0);
        row(c, k, "Mouse DPI", Some("Read it from your mouse software"), false, true, 50.0, |r| {
            field(r, k, FieldKind::Num(Num::Dpi), 90.0, false, false);
            unit(r, k, "counts per inch", kit::TEXT_MID, None);
        });
        row(c, k, "Turn distance", Some("Mouse travel for one full 360° turn"), false, true, 96.0, |r| {
            let (lo, hi) = range(k.data, Num::Cm).track();
            let mut ticks = vec![(lo, fmt_num(lo, 0))];
            ticks.extend(CM_MARKS.iter().filter(|m| **m > lo && **m < hi).map(|m| (*m, fmt_num(*m, 0))));
            ticks.push((hi, format!("{} cm", fmt_num(hi, 0))));
            big_value(r, k, Num::Cm, &ticks, |u| {
                unit(u, k, "cm / 360°", kit::TEXT_MID, None);
                u.spawn((
                    text_as(k.fonts, TextRole::Unit, "", kit::TEXT_MID),
                    Live::TurnUnits,
                    Node { margin: UiRect::left(px(14)), ..default() },
                ));
            });
        });
        import_box(c, k);
        formula(c, k);
        ruler(c, k);
    });
}

/// IMPORT FROM ANOTHER GAME: the game, its sensitivity (the current equivalent until one is typed), APPLY.
fn import_box(p: &mut ChildSpawnerCommands, k: &Kit) {
    let y = &k.data.import_yaw;
    let games =
        if y.cs2 == y.apex { format!("CS2 / Apex {}°", y.cs2) } else { format!("CS2 {}°, Apex {}°", y.cs2, y.apex) };
    let copy = format!("Same DPI. Valorant yaw {}°, {games}, Overwatch 2 {}° per count.", y.valorant, y.overwatch2);
    p.spawn((
        Node {
            display: Display::Grid,
            grid_template_columns: vec![GridTrack::flex(1.0), GridTrack::auto(), GridTrack::auto(), GridTrack::auto()],
            column_gap: px(10),
            align_items: AlignItems::Center,
            margin: UiRect::top(px(10)),
            padding: UiRect::all(px(12)),
            border: UiRect::all(px(1)),
            flex_shrink: 0.0,
            ..default()
        },
        BackgroundColor(kit::W04),
        BorderColor::all(kit::STROKE),
    ))
    .with_children(|g| {
        g.spawn(Node { flex_direction: FlexDirection::Column, min_width: px(0), ..default() }).with_children(|l| {
            l.spawn(k.fonts.role_color(TextRole::Lbl, "Import from another game", kit::TEXT));
            note(l, k, Node::default(), |t| {
                span(t, k, copy, false);
            });
        });
        dropdown(g, k, Ch::ImportGame, 150.0, false);
        field(g, k, FieldKind::Num(Num::ImportSens), 80.0, false, false);
        g.spawn((ApplyImport, kit::button(k.fonts, "Apply", BtnKind::Primary, BtnSize::Apply)));
    });
}

/// 'cm/360 = …', the example for the current turn, and the turn's sensitivity in other games.
fn formula(p: &mut ChildSpawnerCommands, k: &Kit) {
    let y = &k.data.import_yaw;
    note(p, k, Node { margin: UiRect::top(px(8)), ..default() }, |t| {
        span(t, k, "cm/360 = 914.4 ÷ (DPI × sens × yaw). ", false);
        span(t, k, example(Example::Sens, k.s, k.data), false).insert(Example::Sens);
        let mut arrow = TextFont::from_font_size(12.0).with_font(k.symbols.clone());
        arrow.font_size = FontSize::Px(12.0);
        t.spawn((TextSpan::new("→"), arrow, TextColor(kit::TEXT_MID), TextRole::Note.spec().line));
        span(t, k, example(Example::Cm, k.s, k.data), false).insert(Example::Cm);
        span(t, k, "Your value in other games: Valorant ", false);
        span(t, k, " ", true).insert(Live::OtherGame(0));
        span(t, k, if y.cs2 == y.apex { " · CS2/Apex " } else { " · CS2 " }, false);
        span(t, k, " ", true).insert(Live::OtherGame(1));
        span(t, k, " · OW2 ", false);
        span(t, k, " ", true).insert(Live::OtherGame(2));
    });
}

/// The two halves of the formula's example around its arrow. (The kit's `Live::FormulaExample` is one span,
/// and Barlow has no arrow.)
#[derive(Component, Clone, Copy, PartialEq, Eq)]
enum Example {
    /// 'Valorant 0.400 at 800 DPI '
    Sens,
    /// ' 40.8 cm. '
    Cm,
}

fn example(e: Example, s: &Settings, d: &SettingsData) -> String {
    let m = &s.mouse;
    match e {
        Example::Sens => {
            format!("Valorant {} at {} DPI ", fmt_num(sens_for(m.cm_per_360, m.dpi, d.import_yaw.valorant), 3), m.dpi)
        }
        Example::Cm => format!(" {} cm. ", fmt_num(m.cm_per_360, 1)),
    }
}

/// `.note` text. Unlike the kit's `note`, every span carries the note's line height: a span's `LineHeight` is
/// its own, so the kit's spans fall back to 1.2 and a two-line note comes out 6 px short.
fn note(p: &mut ChildSpawnerCommands, k: &Kit, extra: Node, f: impl FnOnce(&mut ChildSpawnerCommands)) {
    let r = TextRole::Note.spec();
    p.spawn((Text::new(""), k.fonts.role_font(TextRole::Note), TextColor(r.color), r.line, extra)).with_children(f);
}

/// A span of a note: TEXT_MID, or Barlow 700 in TEXT_HI when bold.
fn span<'a>(t: &'a mut ChildSpawnerCommands, k: &Kit, s: impl Into<String>, bold: bool) -> EntityCommands<'a> {
    let role = if bold { TextRole::NoteBold } else { TextRole::Note };
    let r = role.spec();
    t.spawn((TextSpan::new(s), k.fonts.role_font(role), TextColor(r.color), r.line))
}

/// One full turn drawn at cm × 10 px (clamped), with quarter ticks and the distance after its end.
fn ruler(p: &mut ChildSpawnerCommands, k: &Kit) {
    p.spawn(Node { flex_direction: FlexDirection::Column, margin: UiRect::top(px(12)), flex_shrink: 0.0, ..default() })
        .with_children(|b| {
            // The mockup's micro is an inline span on a 19 px line.
            b.spawn(Node { height: px(19), padding: UiRect::top(px(5)), ..default() }).with_children(|l| {
                l.spawn(k.fonts.micro("One full turn at your setting (not to scale)"));
            });
            b.spawn((
                Live::Ruler,
                Node {
                    width: px(ruler_px(k.s.mouse.cm_per_360)),
                    height: px(42),
                    margin: UiRect::top(px(10)),
                    border: UiRect::top(px(2)),
                    ..default()
                },
                BorderColor::all(kit::TEXT_HI),
            ))
            .with_children(|r| {
                for (at, h) in [(0.0, 14.0), (25.0, 8.0), (50.0, 12.0), (75.0, 8.0), (100.0, 14.0)] {
                    r.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: percent(at),
                            top: px(0),
                            width: px(1),
                            height: px(h),
                            ..default()
                        },
                        BackgroundColor(kit::TEXT_MID),
                    ));
                }
                r.spawn((
                    text_as(k.fonts, TextRole::Unit, "", kit::TEXT_HI),
                    Live::RulerLabel,
                    TextLayout::no_wrap(),
                    Node { position_type: PositionType::Absolute, right: px(-70), top: px(-12), ..default() },
                ));
            });
        });
}

fn aim_down_sights(p: &mut ChildSpawnerCommands, k: &Kit) {
    card(p, 0.0, 0.0, Node::default(), |c| {
        h2(c, k, "AIM DOWN SIGHTS", None, 0.0);
        row(c, k, "ADS scaling", Some("How zoomed sensitivity is derived"), false, true, 50.0, |r| {
            seg(r, k, Ch::AdsScaling, false, &[]);
        });
        for (i, optic) in k.data.optic_rows.iter().enumerate() {
            let n = Num::Optic(i as u8);
            row(c, k, &optic.label, optic.sub.as_deref(), false, true, 50.0, |r| {
                slider(r, k, n, Some(400.0), &[], false);
                field(r, k, FieldKind::Num(n), 70.0, false, false);
            });
        }
        row(c, k, "ADS input", None, false, true, 50.0, |r| {
            seg(r, k, Ch::AdsInput, false, &[]);
        });
        row(c, k, "Invert Y", None, false, false, 50.0, |r| switch(r, k, Tg::InvertY, false));
    });
}

fn field_of_view(p: &mut ChildSpawnerCommands, k: &Kit) {
    card(p, 0.0, 0.0, Node::default(), |c| {
        h2(c, k, "FIELD OF VIEW", None, 0.0);
        let sub = "Measured at 16:9. Ultrawide adds width (Hor+)";
        row(c, k, "Horizontal FOV", Some(sub), false, true, 90.0, |r| {
            let (lo, hi) = range(k.data, Num::FovH).track();
            let ticks = [(lo, format!("{}°", fmt_num(lo, 0))), (hi, format!("{}°", fmt_num(hi, 0)))];
            big_value(r, k, Num::FovH, &ticks, |u| {
                u.spawn((text_as(k.fonts, TextRole::Unit, "", kit::TEXT_MID), Live::FovUnits));
            });
        });
        // The gun and hands have no camera of their own yet (there is one Camera3d).
        row(c, k, "Viewmodel FOV", Some("Gun and hands only"), true, false, 50.0, |r| {
            slider(r, k, Num::ViewmodelFov, Some(400.0), &[], true);
            field(r, k, FieldKind::Num(Num::ViewmodelFov), 70.0, false, true);
        });
    });
}

/// A big field and its units, over a full-width slider (TURN DISTANCE, HORIZONTAL FOV).
fn big_value(
    p: &mut ChildSpawnerCommands,
    k: &Kit,
    n: Num,
    ticks: &[(f32, String)],
    units: impl FnOnce(&mut ChildSpawnerCommands),
) {
    let ticks: Vec<(f32, &str)> = ticks.iter().map(|(v, s)| (*v, s.as_str())).collect();
    p.spawn(Node { flex_direction: FlexDirection::Column, flex_grow: 1.0, min_width: px(0), ..default() })
        .with_children(|col| {
            ctl(col, Node::default(), |u| {
                field(u, k, FieldKind::Num(n), 140.0, true, false);
                units(u);
            });
            // The slider's hit area is 24 tall around its 4 px track; the mockup's 14 px gap and the row's
            // height count the track only.
            ctl(col, Node { margin: UiRect { top: px(4), bottom: px(-10), ..default() }, ..default() }, |s| {
                slider(s, k, n, None, &ticks, false);
            });
        });
}

fn crosshair(p: &mut ChildSpawnerCommands, k: &Kit) {
    card(p, 1.0, 0.0, Node::default(), |c| {
        // The h2 of the kit, with the code as a button.
        c.spawn(Node {
            height: px(22),
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::Baseline,
            flex_shrink: 0.0,
            ..default()
        })
        .with_children(|h| {
            h.spawn(k.fonts.role(TextRole::H2Card, "CROSSHAIR"));
            h.spawn((
                Button,
                CodeTag,
                Live::CrosshairCode,
                k.fonts.micro(format!("COPY / PASTE CODE: {}", k.s.crosshair_code())),
            ));
        });
        preview(c, k);
        row(c, k, "Colour", None, false, true, 50.0, |r| {
            r.spawn(Node { column_gap: px(8), align_items: AlignItems::Center, ..default() }).with_children(|s| {
                for (_, rgb) in SWATCHES {
                    s.spawn((
                        Button,
                        Swatch(rgb),
                        Node { width: px(30), height: px(30), flex_shrink: 0.0, ..default() },
                        BackgroundColor(rgb_color(rgb)),
                        BorderColor::all(Color::NONE),
                        Outline::new(px(2), px(0), Color::NONE),
                    ));
                }
                hex_field(s, k);
            });
        });
        row(c, k, "Outline · centre dot", None, false, true, 50.0, |r| {
            seg(r, k, Ch::XhOutline, false, &[]);
            seg(r, k, Ch::XhDot, false, &[]);
        });
        row(c, k, "Lines · length / gap / width", None, false, true, 50.0, |r| {
            for n in [Num::XhLength, Num::XhGap, Num::XhWidth] {
                field(r, k, FieldKind::Num(n), 56.0, false, false);
            }
            unit(r, k, "px at 1080p", kit::TEXT_MID, None);
        });
        row(c, k, "Hit markers", None, false, false, 50.0, |r| {
            seg(r, k, Ch::HitMarkers, false, &[]);
        });
    });
}

/// The hex field is the mockup's small chip (30 tall, 14 px, no border at rest); an outline shows while it is
/// edited or holds a bad colour.
fn hex_field(p: &mut ChildSpawnerCommands, k: &Kit) {
    let e = field(p, k, FieldKind::CrosshairHex, 69.0, false, false);
    let mut font = k.fonts.role_font(TextRole::Field);
    font.font_size = FontSize::Px(14.0);
    let pad_v = (30.0 - 14.0 * 1.2) / 2.0;
    p.commands().entity(e).insert((
        HexField,
        Node {
            width: px(69),
            height: px(30),
            padding: UiRect { left: px(12), right: px(8), top: px(pad_v), bottom: px(pad_v) },
            flex_shrink: 0.0,
            overflow: Overflow::clip(),
            ..default()
        },
        font,
        Outline::new(px(1), px(0), Color::NONE),
    ));
}

/// The preview: the street (or a white wall, or sky), the crosshair at 1:1 in its centre, and the background
/// choice at the top right.
fn preview(p: &mut ChildSpawnerCommands, k: &Kit) {
    p.spawn((
        Preview,
        Node {
            height: px(250),
            margin: UiRect::top(px(12)),
            border: UiRect::all(px(1)),
            overflow: Overflow::clip(),
            flex_shrink: 0.0,
            ..default()
        },
        BorderColor::all(kit::STROKE_MID),
        BackgroundColor(Color::NONE),
        BackgroundGradient::default(),
    ))
    .with_children(|v| {
        let mut street = ImageNode::new(k.images.art(Art::HudStreet)).with_mode(NodeImageMode::Stretch);
        street.rect = Some(STREET_CROP);
        v.spawn((
            StreetImage,
            street,
            Node {
                position_type: PositionType::Absolute,
                left: px(0),
                top: px(0),
                width: percent(100),
                height: percent(100),
                ..default()
            },
        ));
        v.spawn((
            CrosshairOrigin,
            Node { position_type: PositionType::Absolute, left: percent(50), top: percent(50), ..default() },
        ));
        v.spawn((
            Node { position_type: PositionType::Absolute, right: px(10), top: px(10), ..default() },
            BackgroundColor(kit::hexa(0x07090D, 0.85)),
        ))
        .with_children(|s| {
            seg(s, k, Ch::PreviewBg, false, &[]);
        });
    });
}

// ---------------------------------------------------------------------------------------------- behaviour

/// The tab's systems are in the schedule.
#[derive(Resource)]
struct SystemsAdded;

/// The frame's plugin registers the shared kit only, so the tab adds its own systems (swatches, APPLY, the
/// code, the preview) the first time it is built. They run in PostUpdate, after the kit's (Update).
fn install_systems(world: &mut World) {
    if world.contains_resource::<SystemsAdded>() {
        return;
    }
    world.insert_resource(SystemsAdded);
    world
        .resource_mut::<Schedules>()
        .add_systems(PostUpdate, (clicks, crosshair_code, sync_tab).chain().before(UiSystems::Prepare));
}

/// APPLY: the turn distance that gives the import box's sensitivity in its game, at the same DPI. The box
/// then shows the current equivalent again.
fn import(s: &mut Settings, ui: &mut UiState, d: &SettingsData) {
    let sens = get_num(s, ui, d, Num::ImportSens);
    let cm = cm_from_sens(sens, s.mouse.dpi, d.import_yaw.of(s.mouse.import_game));
    set_num(s, ui, d, Num::Cm, cm);
    ui.import_sens = None;
}

/// A pasted crosshair code (lines held to their ranges); `None` when the text is not a code.
fn pasted(s: &Settings, ui: &mut UiState, d: &SettingsData, text: &str) -> Option<Settings> {
    let mut xh: CrosshairSettings = s.crosshair.clone();
    if !parse_crosshair_code(text, &mut xh) {
        return None;
    }
    let mut next = s.clone();
    next.crosshair = xh;
    for n in [Num::XhLength, Num::XhGap, Num::XhWidth] {
        let v = get_num(&next, ui, d, n);
        set_num(&mut next, ui, d, n, v);
    }
    Some(next)
}

/// Swatches pick a colour; APPLY converts the import box.
fn clicks(
    swatches: Query<(&Interaction, &Swatch), Changed<Interaction>>,
    apply: Query<&Interaction, (Changed<Interaction>, With<ApplyImport>)>,
    mut settings: ResMut<Settings>,
    mut ui: ResMut<UiState>,
    data: Res<SettingsData>,
) {
    for (i, sw) in &swatches {
        let hex = hex_string(sw.0);
        if *i == Interaction::Pressed && settings.crosshair.color != hex {
            settings.crosshair.color = hex;
        }
    }
    if apply.iter().any(|i| *i == Interaction::Pressed) {
        let mut next = (*settings).clone();
        import(&mut next, &mut ui, &data);
        if next != *settings {
            *settings = next;
        }
        ui.flash = APPLY_FLASH_S;
    }
}

/// A click on the code copies it; Ctrl+V pastes one (not while a field is edited). The code turns TEAL for a
/// moment after either.
#[allow(clippy::too_many_arguments)]
fn crosshair_code(
    mut tags: Query<(Ref<Interaction>, &mut TextColor), With<CodeTag>>,
    keys: Res<ButtonInput<KeyCode>>,
    focus: Res<InputFocus>,
    fields: Query<(), With<Field>>,
    clipboard: Option<ResMut<Clipboard>>,
    mut settings: ResMut<Settings>,
    mut ui: ResMut<UiState>,
    data: Res<SettingsData>,
    time: Res<Time>,
    mut flashed: Local<Option<f32>>,
) {
    let Ok((interaction, mut color)) = tags.single_mut() else { return };
    let mut clipboard = clipboard;
    let now = time.elapsed_secs();
    if interaction.is_changed()
        && *interaction == Interaction::Pressed
        && let Some(cb) = clipboard.as_deref_mut()
    {
        match cb.set_text(settings.crosshair_code()) {
            Ok(()) => *flashed = Some(now),
            Err(e) => warn!("cannot copy the crosshair code: {e}"),
        }
    }
    let ctrl = keys.any_pressed([KeyCode::ControlLeft, KeyCode::ControlRight]);
    let editing = focus.get().is_some_and(|e| fields.contains(e));
    let busy = editing || ui.dropdown.is_some() || ui.confirm.is_some();
    if ctrl
        && keys.just_pressed(KeyCode::KeyV)
        && !busy
        && let Some(cb) = clipboard.as_deref_mut()
        && let Some(Ok(text)) = cb.fetch_text().poll_result()
        && let Some(next) = pasted(&settings, &mut ui, &data, &text)
    {
        if next != *settings {
            *settings = next;
        }
        *flashed = Some(now);
    }
    let want = if flashed.is_some_and(|t| now - t < CODE_FLASH_S) {
        kit::TEAL
    } else if *interaction != Interaction::None {
        kit::TEXT_HI
    } else {
        kit::TEXT_LOW
    };
    if color.0 != want {
        color.0 = want;
    }
}

/// The tab follows the settings: the formula's example, the preview's background, the crosshair (redrawn
/// when it changes), the selected swatch, and the hex field's edit outline.
#[allow(clippy::type_complexity, clippy::too_many_arguments)]
fn sync_tab(
    settings: Res<Settings>,
    ui: Res<UiState>,
    data: Res<SettingsData>,
    focus: Res<InputFocus>,
    mut examples: Query<(&Example, &mut TextSpan)>,
    mut previews: Query<(Ref<Preview>, &mut BackgroundColor, &mut BackgroundGradient)>,
    mut street: Query<&mut Visibility, With<StreetImage>>,
    origins: Query<(Entity, Ref<CrosshairOrigin>)>,
    mut swatches: Query<(&Swatch, &Interaction, &mut Node, &mut BorderColor, &mut Outline), Without<HexField>>,
    mut hex: Query<(Entity, &Field, &mut Outline), With<HexField>>,
    mut drawn: Local<Option<(PreviewBg, CrosshairSettings)>>,
    mut commands: Commands,
) {
    for (e, mut text) in &mut examples {
        let want = example(*e, &settings, &data);
        if text.0 != want {
            text.0 = want;
        }
    }
    let xh = &settings.crosshair;
    let bg = ui.preview_bg;
    let added = previews.iter().any(|(p, ..)| p.is_added()) || origins.iter().any(|(_, o)| o.is_added());
    if added || drawn.as_ref() != Some(&(bg, xh.clone())) {
        *drawn = Some((bg, xh.clone()));
        for (_, mut fill, mut gradient) in &mut previews {
            fill.0 = if bg == PreviewBg::WhiteWall { kit::IVORY } else { Color::NONE };
            *gradient = if bg == PreviewBg::Sky {
                BackgroundGradient::from(LinearGradient {
                    angle: LinearGradient::TO_BOTTOM,
                    stops: vec![
                        ColorStop::new(kit::hex(0x9CC9F0), percent(0)),
                        ColorStop::new(kit::hex(0xDCEEFB), percent(100)),
                    ],
                    color_space: InterpolationColorSpace::Srgba,
                })
            } else {
                BackgroundGradient::default()
            };
        }
        for mut v in &mut street {
            *v = if bg == PreviewBg::Street { Visibility::Inherited } else { Visibility::Hidden };
        }
        let color = rgb_color(settings.crosshair_rgb());
        for (e, _) in &origins {
            commands.entity(e).despawn_children().with_children(|o| {
                for (x, y, w, h) in crosshair_rects(xh, 0.0) {
                    let mut arm = o.spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: px(x),
                            top: px(y),
                            width: px(w),
                            height: px(h),
                            ..default()
                        },
                        BackgroundColor(color),
                    ));
                    if xh.outline {
                        arm.insert(Outline::new(px(1), px(0), kit::K85));
                    }
                }
            });
        }
    }
    // The selected swatch: a white 2 px border and a black outline; hover: a STROKE_HI border.
    let rgb = settings.crosshair_rgb();
    for (sw, i, mut node, mut border, mut outline) in &mut swatches {
        let on = sw.0 == rgb;
        let edge = if on {
            Color::WHITE
        } else if *i != Interaction::None {
            kit::STROKE_HI
        } else {
            Color::NONE
        };
        // Bevy does not paint the fill under a border: the swatch keeps its full 30 px of colour at rest.
        let width = px(if edge == Color::NONE { 0.0 } else { 2.0 });
        if node.border.top != width {
            node.border = UiRect::all(width);
        }
        if border.top != edge {
            *border = BorderColor::all(edge);
        }
        let ring = if on { Color::BLACK } else { Color::NONE };
        if outline.color != ring {
            outline.color = ring;
        }
    }
    for (e, f, mut outline) in &mut hex {
        let want = if f.invalid {
            kit::WARN
        } else if focus.get() == Some(e) {
            kit::TEXT_HI
        } else {
            Color::NONE
        };
        if outline.color != want {
            outline.color = want;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::settings::{ImportGame, embedded};
    use bevy::ecs::system::RunSystemOnce;

    #[test]
    fn apply_converts_another_games_sensitivity() {
        let d = embedded();
        let mut s = d.defaults.clone();
        let mut ui = UiState::default();
        // CS2 1.273 at 800 DPI is the default 40.8 cm
        s.mouse.import_game = ImportGame::Cs2;
        s.mouse.cm_per_360 = 20.0;
        ui.import_sens = Some(1.273);
        import(&mut s, &mut ui, d);
        assert!((s.mouse.cm_per_360 - 40.8).abs() < 0.05, "{}", s.mouse.cm_per_360);
        assert_eq!(ui.import_sens, None, "the box shows the current equivalent again");
        // Valorant 0.2 at 1600 DPI is the same turn
        s.mouse.import_game = ImportGame::Valorant;
        s.mouse.dpi = 1600;
        ui.import_sens = Some(0.2);
        import(&mut s, &mut ui, d);
        assert!((s.mouse.cm_per_360 - 40.8).abs() < 0.05);
        // a tiny sensitivity clamps to the longest turn the field takes
        ui.import_sens = Some(0.001);
        import(&mut s, &mut ui, d);
        assert_eq!(s.mouse.cm_per_360, d.ranges.cm_per_360.max);
    }

    #[test]
    fn pasted_codes_set_the_crosshair_within_its_ranges() {
        let d = embedded();
        let s = d.defaults.clone();
        let mut ui = UiState::default();
        let next = pasted(&s, &mut ui, d, " XH1-G-O0-I40.9.3-D ").expect("a code");
        let xh = &next.crosshair;
        assert_eq!(xh.color, "#52E5A5");
        assert!(!xh.outline && xh.dot);
        assert_eq!((xh.length, xh.width, xh.gap), (d.ranges.xh_length.max, d.ranges.xh_width.max, 3.0));
        assert_eq!(xh.hit_markers, s.crosshair.hit_markers, "a code leaves hit markers alone");
        assert!(pasted(&s, &mut ui, d, "hello").is_none());
        // the default copies and pastes back to itself
        assert_eq!(pasted(&s, &mut ui, d, &s.crosshair_code()).as_ref(), Some(&s));
    }

    fn world() -> World {
        let d = embedded();
        let mut w = World::new();
        w.insert_resource(d.defaults.clone());
        w.insert_resource(d.clone());
        w.init_resource::<UiState>();
        w.init_resource::<InputFocus>();
        w
    }

    #[test]
    fn a_swatch_picks_its_colour_and_apply_imports() {
        let mut w = world();
        w.spawn((Swatch(SWATCHES[3].1), Interaction::Pressed));
        w.spawn((ApplyImport, Interaction::Pressed));
        w.resource_mut::<Settings>().mouse.import_game = ImportGame::Cs2;
        w.resource_mut::<UiState>().import_sens = Some(0.5);
        w.run_system_once(clicks).unwrap();
        let s = w.resource::<Settings>();
        assert_eq!(s.crosshair.color, "#52E5A5");
        assert!((s.mouse.cm_per_360 - 103.9).abs() < 0.05, "CS2 0.5 at 800 DPI: {}", s.mouse.cm_per_360);
        assert_eq!(w.resource::<UiState>().flash, APPLY_FLASH_S, "the turn field flashes");
    }

    #[test]
    fn the_preview_follows_the_settings() {
        let mut w = world();
        let preview = w.spawn((Preview, BackgroundColor(Color::NONE), BackgroundGradient::default())).id();
        let street = w.spawn((StreetImage, Visibility::Inherited)).id();
        let origin = w.spawn((CrosshairOrigin, Node::default())).id();
        let cm = w.spawn((Example::Cm, TextSpan::new(""))).id();
        let arms = |w: &mut World| {
            let kids: Vec<Entity> = w.get::<Children>(origin).map(|c| c.to_vec()).unwrap_or_default();
            kids.iter()
                .map(|e| (w.get::<BackgroundColor>(*e).unwrap().0, w.get::<Outline>(*e).is_some()))
                .collect::<Vec<_>>()
        };
        w.run_system_once(sync_tab).unwrap();
        let white = rgb_color(SWATCHES[0].1);
        assert_eq!(arms(&mut w), vec![(white, true); 4], "four outlined arms in the default white");
        assert_eq!(w.get::<TextSpan>(cm).unwrap().0, " 40.8 cm. ");
        // a magenta crosshair with a dot and no outline, over the sky
        {
            let mut s = w.resource_mut::<Settings>();
            s.crosshair.color = hex_string(SWATCHES[4].1);
            s.crosshair.dot = true;
            s.crosshair.outline = false;
            s.mouse.cm_per_360 = 33.3;
        }
        w.resource_mut::<UiState>().preview_bg = PreviewBg::Sky;
        w.run_system_once(sync_tab).unwrap();
        assert_eq!(arms(&mut w), vec![(rgb_color(SWATCHES[4].1), false); 5]);
        assert_ne!(*w.get::<BackgroundGradient>(preview).unwrap(), BackgroundGradient::default());
        assert_eq!(*w.get::<Visibility>(street).unwrap(), Visibility::Hidden);
        assert_eq!(w.get::<TextSpan>(cm).unwrap().0, " 33.3 cm. ");
    }
}
