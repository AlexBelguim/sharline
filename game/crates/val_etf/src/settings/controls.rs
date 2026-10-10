//! The Settings control kit (mockup `settings.html`): cards, rows, segmented controls, sliders, number and
//! text fields, switches and dropdowns, each bound to one value of [`Settings`]. Controls write the value as
//! they are used; the `sync_*` systems redraw every control from the value, so resets and presets show at once.

use super::model::*;
use crate::ui_kit::{
    self as kit, Active, Disabled, Face, Ink, Looks, SegOption, SegValue, Switch, SwitchKnob, TextRole, UiFonts,
    UiImages,
};
use crate::user_config::PlayerProfile;
use bevy::ecs::hierarchy::ChildSpawnerCommands;
use bevy::input::mouse::AccumulatedMouseScroll;
use bevy::input_focus::InputFocus;
use bevy::prelude::*;
use bevy::text::{EditableText, EditableTextFilter, LetterSpacing, LineHeight, TextCursorStyle};
use bevy::ui::RelativeCursorPosition;
use bevy::ui_widgets::SelectAllOnFocus;

pub const DIM: f32 = kit::DISABLED_ALPHA;

/// A number the screen edits.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Num {
    Dpi,
    Cm,
    ImportSens,
    /// An ADS row (index into the data's optic rows).
    Optic(u8),
    FovH,
    ViewmodelFov,
    XhLength,
    XhGap,
    XhWidth,
    RenderScale,
    Brightness,
    /// Master, weapons, movement, abilities, hits, interface, music.
    Vol(u8),
    HudScale,
    SafeArea,
    ScreenShake,
    RadialHold,
    HostPort,
}

/// A choice the screen edits (segments and dropdowns).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Ch {
    Jetpack,
    Slide,
    MagCard,
    RangeMagCheck,
    RadialPick,
    ImportGame,
    AdsScaling,
    AdsInput,
    XhOutline,
    XhDot,
    HitMarkers,
    PreviewBg,
    WindowMode,
    Resolution,
    FrameLimit,
    Vsync,
    Overlay,
    Preset,
    Aa,
    Shadows,
    Bloom,
    Particles,
    OutputDevice,
    Mix,
    LowMag,
    Ultrawide,
    HealthNumbers,
    Minimap,
    DamageNumbers,
    KillFeed,
    EnemyNames,
    TeamColours,
    EnemyOutline,
    DamageFlash,
    TextSize,
    HoldToggle,
}

/// An on/off value (switches).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Tg {
    AutoSprint,
    ThrowLine,
    NetGraph,
    InvertY,
    Outlines,
    ContactShadows,
    Ssr,
    MotionBlur,
    Vignette,
    ShieldHit,
    Headshot,
    PlayInBg,
    ReduceFlashing,
}

/// What a text field edits.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum FieldKind {
    Num(Num),
    PlayerName,
    CrosshairHex,
}

/// The monitor, as far as the window system tells us.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct DisplayInfo {
    /// Distinct modes, largest first.
    pub modes: Vec<Resolution>,
    /// The monitor's current mode.
    pub native: Option<Resolution>,
    pub refresh_hz: Option<u32>,
}

/// Screen state that is not saved.
#[derive(Resource, Debug, Default)]
pub struct UiState {
    pub preview_bg: PreviewBg,
    /// A sensitivity staged for the import box's APPLY; otherwise (and once committed) it shows the current
    /// equivalent.
    pub import_sens: Option<f32>,
    pub display: DisplayInfo,
    /// The open dropdown and its list entity.
    pub dropdown: Option<(Entity, Entity)>,
    /// The RESET ALL confirm is open.
    pub confirm: Option<Entity>,
    /// Shown instead of the top-bar hint when saving failed.
    pub save_error: Option<String>,
    /// Seconds left of the import field's flash after APPLY.
    pub flash: f32,
    /// The field being edited (see [`Editing`]).
    pub editing: Option<Editing>,
}

// ---------------------------------------------------------------------------------------------- values

pub fn range(d: &SettingsData, k: Num) -> Range {
    let r = &d.ranges;
    match k {
        Num::Dpi => r.dpi,
        Num::Cm => r.cm_per_360,
        Num::ImportSens => r.import_sens,
        Num::Optic(_) => r.optic_mult,
        Num::FovH => r.fov_h,
        Num::ViewmodelFov => r.viewmodel_fov,
        Num::XhLength => r.xh_length,
        Num::XhGap => r.xh_gap,
        Num::XhWidth => r.xh_width,
        Num::RenderScale => r.render_scale,
        Num::Brightness => r.brightness,
        Num::Vol(_) => r.volume,
        Num::HudScale => r.hud_scale,
        Num::SafeArea => r.safe_area,
        Num::ScreenShake => r.screen_shake,
        Num::RadialHold => r.radial_hold_s,
        Num::HostPort => r.host_port,
    }
}

/// Decimals and unit suffix a field shows.
pub fn format(k: Num) -> (usize, &'static str) {
    match k {
        Num::Cm => (1, ""),
        Num::ImportSens => (3, ""),
        Num::Optic(_) => (2, ""),
        Num::FovH | Num::ViewmodelFov => (0, "°"),
        Num::RenderScale | Num::HudScale | Num::ScreenShake => (0, " %"),
        Num::SafeArea => (0, " px"),
        Num::RadialHold => (2, " s"),
        _ => (0, ""),
    }
}

pub fn num_text(k: Num, v: f32) -> String {
    let (d, unit) = format(k);
    format!("{}{unit}", fmt_num(v, d))
}

fn optic_ids(d: &SettingsData, row: u8) -> &[String] {
    d.optic_rows.get(row as usize).map_or(&[], |r| r.optics.as_slice())
}

pub fn get_num(s: &Settings, ui: &UiState, d: &SettingsData, k: Num) -> f32 {
    match k {
        Num::Dpi => s.mouse.dpi as f32,
        Num::Cm => s.mouse.cm_per_360,
        Num::ImportSens => ui
            .import_sens
            .unwrap_or_else(|| sens_for(s.mouse.cm_per_360, s.mouse.dpi, d.import_yaw.of(s.mouse.import_game))),
        Num::Optic(i) => optic_ids(d, i).first().map_or(1.0, |o| s.optic_mult(o)),
        Num::FovH => s.mouse.fov_h,
        Num::ViewmodelFov => s.mouse.viewmodel_fov,
        Num::XhLength => s.crosshair.length,
        Num::XhGap => s.crosshair.gap,
        Num::XhWidth => s.crosshair.width,
        Num::RenderScale => s.video.render_scale,
        Num::Brightness => s.video.brightness,
        Num::Vol(i) => *volume(&s.audio, i),
        Num::HudScale => s.hud.scale,
        Num::SafeArea => s.hud.safe_area,
        Num::ScreenShake => s.hud.screen_shake,
        Num::RadialHold => s.gameplay.radial_hold_s,
        Num::HostPort => s.network.host_port as f32,
    }
}

fn volume(a: &AudioSettings, i: u8) -> &f32 {
    match i {
        0 => &a.master,
        1 => &a.weapons,
        2 => &a.movement,
        3 => &a.abilities,
        4 => &a.hits,
        5 => &a.interface,
        _ => &a.music,
    }
}

fn volume_mut(a: &mut AudioSettings, i: u8) -> &mut f32 {
    match i {
        0 => &mut a.master,
        1 => &mut a.weapons,
        2 => &mut a.movement,
        3 => &mut a.abilities,
        4 => &mut a.hits,
        5 => &mut a.interface,
        _ => &mut a.music,
    }
}

/// Set a number (snapped to its range) in a copy of the settings.
pub fn set_num(s: &mut Settings, ui: &mut UiState, d: &SettingsData, k: Num, v: f32) {
    let v = range(d, k).snap(v);
    match k {
        Num::Dpi => s.mouse.dpi = v.round() as u32,
        Num::Cm => s.mouse.cm_per_360 = v,
        // A sensitivity committed in the import box (Enter, or a click away such as DONE) sets the turn at
        // once: typed and left, it used to wait for APPLY and was lost when the screen closed.
        Num::ImportSens => {
            let cm = cm_from_sens(v, s.mouse.dpi, d.import_yaw.of(s.mouse.import_game));
            s.mouse.cm_per_360 = range(d, Num::Cm).snap(cm);
            ui.import_sens = None;
        }
        Num::Optic(i) => {
            for o in optic_ids(d, i) {
                s.mouse.optic_mult.insert(o.clone(), v);
            }
        }
        Num::FovH => s.mouse.fov_h = v,
        Num::ViewmodelFov => s.mouse.viewmodel_fov = v,
        Num::XhLength => s.crosshair.length = v,
        Num::XhGap => s.crosshair.gap = v,
        Num::XhWidth => s.crosshair.width = v,
        Num::RenderScale => s.video.render_scale = v,
        Num::Brightness => s.video.brightness = v,
        Num::Vol(i) => *volume_mut(&mut s.audio, i) = v,
        Num::HudScale => s.hud.scale = v,
        Num::SafeArea => s.hud.safe_area = v,
        Num::ScreenShake => s.hud.screen_shake = v,
        Num::RadialHold => s.gameplay.radial_hold_s = v,
        Num::HostPort => s.network.host_port = v.round() as u16,
    }
}

fn b2i(on: bool, first_is_on: bool) -> usize {
    if on == first_is_on { 0 } else { 1 }
}

pub fn get_choice(s: &Settings, ui: &UiState, d: &SettingsData, c: Ch) -> usize {
    let v = &s.video;
    let h = &s.hud;
    match c {
        Ch::Jetpack => s.gameplay.jetpack.index(),
        Ch::Slide => s.gameplay.slide.index(),
        Ch::MagCard => s.gameplay.mag_card.index(),
        Ch::RangeMagCheck => s.gameplay.range_mag_check.index(),
        Ch::RadialPick => s.gameplay.radial_pick.index(),
        Ch::ImportGame => s.mouse.import_game.index(),
        Ch::AdsScaling => s.mouse.ads_scaling.index(),
        Ch::AdsInput => s.mouse.ads_input.index(),
        Ch::XhOutline => b2i(s.crosshair.outline, true),
        Ch::XhDot => b2i(s.crosshair.dot, true),
        Ch::HitMarkers => s.crosshair.hit_markers.index(),
        Ch::PreviewBg => ui.preview_bg.index(),
        Ch::WindowMode => v.window_mode.index(),
        Ch::Resolution => match v.resolution {
            Some(r) => ui.display.modes.iter().position(|m| *m == r).map_or(0, |i| i + 1),
            None => 0,
        },
        Ch::FrameLimit => {
            let opts = frame_limit_options(&d.frame_limits, ui.display.refresh_hz);
            frame_limit_index(&opts, v.frame_limit, ui.display.refresh_hz)
        }
        Ch::Vsync => b2i(v.vsync, false),
        Ch::Overlay => v.overlay.index(),
        Ch::Preset => v.preset.index(),
        Ch::Aa => v.aa.index(),
        Ch::Shadows => v.shadows.index(),
        Ch::Bloom => v.bloom.index(),
        Ch::Particles => v.particles.index(),
        Ch::OutputDevice => 0,
        Ch::Mix => s.audio.mix.index(),
        Ch::LowMag => b2i(s.audio.low_mag_cue, false),
        Ch::Ultrawide => h.ultrawide.index(),
        Ch::HealthNumbers => h.health_numbers.index(),
        Ch::Minimap => h.minimap.index(),
        Ch::DamageNumbers => b2i(h.damage_numbers, false),
        Ch::KillFeed => h.kill_feed.index(),
        Ch::EnemyNames => h.enemy_names.index(),
        Ch::TeamColours => h.team_colours.index(),
        Ch::EnemyOutline => h.enemy_outline.index(),
        Ch::DamageFlash => h.damage_flash.index(),
        Ch::TextSize => h.text_size.index(),
        Ch::HoldToggle => h.hold_toggle.index(),
    }
}

pub fn set_choice(s: &mut Settings, ui: &mut UiState, d: &SettingsData, c: Ch, i: usize) {
    let v = &mut s.video;
    let h = &mut s.hud;
    match c {
        Ch::Jetpack => s.gameplay.jetpack = Jetpack::from_index(i),
        Ch::Slide => s.gameplay.slide = Slide::from_index(i),
        Ch::MagCard => s.gameplay.mag_card = MagCard::from_index(i),
        Ch::RangeMagCheck => s.gameplay.range_mag_check = RangeMagCheck::from_index(i),
        Ch::RadialPick => s.gameplay.radial_pick = RadialPick::from_index(i),
        Ch::ImportGame => {
            s.mouse.import_game = ImportGame::from_index(i);
            ui.import_sens = None;
        }
        Ch::AdsScaling => s.mouse.ads_scaling = AdsScaling::from_index(i),
        Ch::AdsInput => s.mouse.ads_input = HoldToggle::from_index(i),
        Ch::XhOutline => s.crosshair.outline = i == 0,
        Ch::XhDot => s.crosshair.dot = i == 0,
        Ch::HitMarkers => s.crosshair.hit_markers = HitMarkers::from_index(i),
        Ch::PreviewBg => ui.preview_bg = PreviewBg::from_index(i),
        Ch::WindowMode => v.window_mode = WindowModeChoice::from_index(i),
        Ch::Resolution => v.resolution = if i == 0 { None } else { ui.display.modes.get(i - 1).copied() },
        Ch::FrameLimit => {
            let opts = frame_limit_options(&d.frame_limits, ui.display.refresh_hz);
            if let Some(o) = opts.get(i) {
                v.frame_limit = match (*o, ui.display.refresh_hz) {
                    (FrameLimit::Fps(n), Some(hz)) if n == hz => FrameLimit::Monitor,
                    (o, _) => o,
                };
            }
        }
        Ch::Vsync => v.vsync = i == 1,
        Ch::Overlay => v.overlay = Overlay::from_index(i),
        Ch::Preset => s.apply_preset(Preset::from_index(i), &d.presets),
        Ch::Aa => v.aa = Aa::from_index(i),
        Ch::Shadows => v.shadows = Shadows::from_index(i),
        Ch::Bloom => v.bloom = Bloom::from_index(i),
        Ch::Particles => v.particles = Particles::from_index(i),
        Ch::OutputDevice => {}
        Ch::Mix => s.audio.mix = super::model::Mix::from_index(i),
        Ch::LowMag => s.audio.low_mag_cue = i == 1,
        Ch::Ultrawide => h.ultrawide = Ultrawide::from_index(i),
        Ch::HealthNumbers => h.health_numbers = HealthNumbers::from_index(i),
        Ch::Minimap => h.minimap = Minimap::from_index(i),
        Ch::DamageNumbers => h.damage_numbers = i == 1,
        Ch::KillFeed => h.kill_feed = KillFeed::from_index(i),
        Ch::EnemyNames => h.enemy_names = EnemyNames::from_index(i),
        Ch::TeamColours => h.team_colours = TeamColours::from_index(i),
        Ch::EnemyOutline => h.enemy_outline = EnemyOutline::from_index(i),
        Ch::DamageFlash => h.damage_flash = DamageFlash::from_index(i),
        Ch::TextSize => h.text_size = TextSize::from_index(i),
        Ch::HoldToggle => h.hold_toggle = HoldToggle::from_index(i),
    }
}

/// The options of a choice, as the control shows them.
pub fn choice_labels(ui: &UiState, d: &SettingsData, c: Ch, s: &Settings) -> Vec<String> {
    fn l(x: &[&str]) -> Vec<String> {
        x.iter().map(|s| s.to_string()).collect()
    }
    match c {
        Ch::Jetpack => l(Jetpack::LABELS),
        Ch::Slide => l(Slide::LABELS),
        Ch::MagCard => l(MagCard::LABELS),
        Ch::RangeMagCheck => l(RangeMagCheck::LABELS),
        Ch::RadialPick => l(RadialPick::LABELS),
        Ch::ImportGame => l(ImportGame::LABELS),
        Ch::AdsScaling => l(AdsScaling::LABELS),
        Ch::AdsInput | Ch::HoldToggle => l(HoldToggle::LABELS),
        Ch::XhOutline => l(&["OUTLINE 1 PX", "OFF"]),
        Ch::XhDot => l(&["DOT", "NO DOT"]),
        Ch::HitMarkers => l(HitMarkers::LABELS),
        Ch::PreviewBg => l(PreviewBg::LABELS),
        Ch::WindowMode => l(WindowModeChoice::LABELS),
        Ch::Resolution => {
            let native = ui.display.native.map_or("Native".to_string(), |n| n.label());
            std::iter::once(native).chain(ui.display.modes.iter().map(|m| m.label())).collect()
        }
        Ch::FrameLimit => frame_limit_options(&d.frame_limits, ui.display.refresh_hz)
            .into_iter()
            .map(|o| match o {
                FrameLimit::Fps(n) => n.to_string(),
                _ => "OFF".into(),
            })
            .collect(),
        Ch::Vsync => l(&["OFF (AutoNoVsync)", "ON (AutoVsync)"]),
        Ch::Overlay => l(Overlay::LABELS),
        Ch::Preset => l(Preset::LABELS),
        Ch::Aa => l(Aa::LABELS),
        Ch::Shadows => l(Shadows::LABELS),
        Ch::Bloom => l(Bloom::LABELS),
        Ch::Particles => l(Particles::LABELS),
        Ch::OutputDevice => vec![s.audio.output_device.clone()],
        Ch::Mix => l(super::model::Mix::LABELS),
        Ch::LowMag | Ch::DamageNumbers => l(&["OFF", "ON"]),
        Ch::Ultrawide => l(Ultrawide::LABELS),
        Ch::HealthNumbers => l(HealthNumbers::LABELS),
        Ch::Minimap => l(Minimap::LABELS),
        Ch::KillFeed => l(KillFeed::LABELS),
        Ch::EnemyNames => l(EnemyNames::LABELS),
        Ch::TeamColours => l(TeamColours::LABELS),
        Ch::EnemyOutline => l(EnemyOutline::LABELS),
        Ch::DamageFlash => l(DamageFlash::LABELS),
        Ch::TextSize => l(TextSize::LABELS),
    }
}

pub fn get_toggle(s: &Settings, t: Tg) -> bool {
    let v = &s.video;
    match t {
        Tg::AutoSprint => s.gameplay.auto_sprint,
        Tg::ThrowLine => s.gameplay.throw_line,
        Tg::NetGraph => v.overlay == Overlay::Network,
        Tg::InvertY => s.mouse.invert_y,
        Tg::Outlines => v.outlines,
        Tg::ContactShadows => v.contact_shadows,
        Tg::Ssr => v.ssr,
        Tg::MotionBlur => v.motion_blur,
        Tg::Vignette => v.vignette,
        Tg::ShieldHit => s.audio.shield_hit,
        Tg::Headshot => s.audio.headshot,
        Tg::PlayInBg => s.audio.play_in_background,
        Tg::ReduceFlashing => s.hud.reduce_flashing,
    }
}

pub fn set_toggle(s: &mut Settings, t: Tg, on: bool) {
    let v = &mut s.video;
    match t {
        Tg::AutoSprint => s.gameplay.auto_sprint = on,
        Tg::ThrowLine => s.gameplay.throw_line = on,
        // The same value as Video ▸ Performance overlay '+ NETWORK'.
        Tg::NetGraph => {
            v.overlay = match (on, v.overlay) {
                (true, _) => Overlay::Network,
                (false, Overlay::Network) => Overlay::Fps,
                (false, o) => o,
            }
        }
        Tg::InvertY => s.mouse.invert_y = on,
        Tg::Outlines => v.outlines = on,
        Tg::ContactShadows => v.contact_shadows = on,
        Tg::Ssr => v.ssr = on,
        Tg::MotionBlur => v.motion_blur = on,
        Tg::Vignette => v.vignette = on,
        Tg::ShieldHit => s.audio.shield_hit = on,
        Tg::Headshot => s.audio.headshot = on,
        Tg::PlayInBg => s.audio.play_in_background = on,
        Tg::ReduceFlashing => s.hud.reduce_flashing = on,
    }
}

/// Change the settings through a copy, so change detection fires only for real changes.
pub fn edit(settings: &mut ResMut<Settings>, f: impl FnOnce(&mut Settings)) {
    let mut next = (**settings).clone();
    f(&mut next);
    if next != **settings {
        **settings = next;
    }
}

// ---------------------------------------------------------------------------------------------- components

#[derive(Component, Debug, Clone, Copy)]
pub struct SegBind(pub Ch);

#[derive(Component, Debug, Clone, Copy)]
pub struct SwitchBind(pub Tg);

/// A slider's hit area (taller than the 4 px track); its fill and thumb.
#[derive(Component, Debug, Clone, Copy)]
pub struct SliderBind {
    pub num: Num,
    pub fill: Entity,
    pub thumb: Entity,
}

#[derive(Component, Debug, Clone, Copy)]
pub struct Field {
    pub kind: FieldKind,
    pub invalid: bool,
    pub big: bool,
}

/// A dropdown button; `label` is its text entity.
#[derive(Component, Debug, Clone, Copy)]
pub struct Dropdown {
    pub choice: Ch,
    pub label: Entity,
}

/// A row of an open dropdown list.
#[derive(Component, Debug, Clone, Copy)]
pub struct DropRow {
    pub choice: Ch,
    pub index: usize,
}

/// Text recomputed from the settings (unit lines, notes, micro tags).
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq)]
pub enum Live {
    TurnUnits,
    RulerLabel,
    Ruler,
    FormulaExample,
    OtherGame(u8),
    FovUnits,
    CrosshairCode,
    PresetMicro,
    TeamAlly,
    TeamEnemy,
    TeamAllySquare,
    TeamEnemySquare,
    TopHint,
}

/// The settings that should be drawn faded (a disabled row) carry this.
#[derive(Component, Debug, Clone, Copy)]
pub struct Dim;

// ---------------------------------------------------------------------------------------------- builders

/// What the builders need.
pub struct Kit<'a> {
    pub fonts: &'a UiFonts,
    pub images: &'a UiImages,
    pub symbols: Handle<Font>,
    pub s: &'a Settings,
    pub ui: &'a UiState,
    pub data: &'a SettingsData,
    pub profile: &'a PlayerProfile,
}

pub fn dimc(c: Color, dim: bool) -> Color {
    if dim { kit::fade(c, DIM) } else { c }
}

/// Text in a role and colour, keeping its case (mixed-case copy and units).
pub fn text_as(fonts: &UiFonts, role: TextRole, s: impl Into<String>, color: Color) -> impl Bundle {
    let r = role.spec();
    (Text::new(s), fonts.role_font(role), TextColor(color), LetterSpacing::Px(r.size * r.em), r.line)
}

/// Text where the glyphs Barlow lacks (arrows, pad symbols) come from the symbol font, as spans.
pub fn glyph_text(
    p: &mut ChildSpawnerCommands,
    k: &Kit,
    role: TextRole,
    s: &str,
    color: Color,
    extra: impl Bundle,
) -> Entity {
    let r = role.spec();
    let font = k.fonts.role_font(role);
    let mut sym = TextFont::from_font_size(r.size * 0.92).with_font(k.symbols.clone());
    sym.font_size = FontSize::Px(r.size * 0.92);
    let runs = glyph_runs(s);
    let mut e =
        p.spawn((Text::new(""), font.clone(), TextColor(color), LetterSpacing::Px(r.size * r.em), r.line, extra));
    e.with_children(|c| {
        for (txt, is_sym) in runs {
            if is_sym {
                c.spawn((TextSpan::new(txt), sym.clone(), TextColor(color)));
            } else {
                c.spawn((TextSpan::new(txt), font.clone(), TextColor(color)));
            }
        }
    });
    e.id()
}

/// Glyphs the symbol font supplies.
pub fn is_symbol(c: char) -> bool {
    matches!(c, '←' | '↑' | '→' | '↓' | '✕' | '◯' | '▢' | '△')
}

/// Split a string into runs of (text, uses the symbol font).
pub fn glyph_runs(s: &str) -> Vec<(String, bool)> {
    let mut out: Vec<(String, bool)> = Vec::new();
    for ch in s.chars() {
        let sym = is_symbol(ch);
        match out.last_mut() {
            Some((t, k)) if *k == sym => t.push(ch),
            _ => out.push((ch.to_string(), sym)),
        }
    }
    out
}

/// A card (`.card.panel`): padding 18 / 20. `gap` 14 for column cards (pattern a), 0 for stacked ones.
pub fn card(p: &mut ChildSpawnerCommands, grow: f32, gap: f32, extra: Node, f: impl FnOnce(&mut ChildSpawnerCommands)) {
    p.spawn(kit::panel(Node {
        flex_direction: FlexDirection::Column,
        padding: UiRect::axes(px(20), px(18)),
        row_gap: px(gap),
        flex_grow: grow,
        flex_basis: if grow > 0.0 { px(0) } else { Val::Auto },
        min_width: px(0),
        ..extra
    }))
    .with_children(f);
}

/// A card title (h2) with an optional right-hand micro tag.
pub fn h2(p: &mut ChildSpawnerCommands, k: &Kit, title: &str, micro: Option<(&str, Option<Live>)>, top: f32) {
    p.spawn(Node {
        height: px(22),
        justify_content: JustifyContent::SpaceBetween,
        align_items: AlignItems::Baseline,
        margin: UiRect::top(px(top)),
        flex_shrink: 0.0,
        ..default()
    })
    .with_children(|r| {
        r.spawn(k.fonts.role(TextRole::H2Card, title));
        if let Some((m, live)) = micro {
            let mut e = r.spawn(k.fonts.micro(m));
            if let Some(l) = live {
                e.insert(l);
            }
        }
    });
}

/// A settings row: label (and sub-label) in a 230 px column, controls after it.
pub fn row(
    p: &mut ChildSpawnerCommands,
    k: &Kit,
    label: &str,
    sub: Option<&str>,
    dim: bool,
    border: bool,
    min_h: f32,
    f: impl FnOnce(&mut ChildSpawnerCommands),
) {
    let mut e = p.spawn((
        Node {
            display: Display::Grid,
            grid_template_columns: vec![GridTrack::px(230.0), GridTrack::flex(1.0)],
            align_items: AlignItems::Center,
            // Taffy adds the bottom rule on top of the grid's stretched track; CSS counts it inside.
            min_height: px(if border { min_h - 1.0 } else { min_h }),
            border: UiRect::bottom(px(if border { 1.0 } else { 0.0 })),
            flex_shrink: 0.0,
            ..default()
        },
        BorderColor::all(kit::STROKE),
    ));
    if dim {
        e.insert(Dim);
    }
    e.with_children(|r| {
        r.spawn(Node { flex_direction: FlexDirection::Column, padding: UiRect::right(px(12)), ..default() })
            .with_children(|l| {
                l.spawn(k.fonts.role_color(TextRole::RowLabel, label, dimc(kit::TEXT, dim)));
                if let Some(sub) = sub {
                    l.spawn((
                        text_as(k.fonts, TextRole::Sub, sub, dimc(kit::TEXT_MID, dim)),
                        Node { margin: UiRect::top(px(1)), ..default() },
                    ));
                }
            });
        r.spawn(Node { align_items: AlignItems::Center, column_gap: px(12), min_width: px(0), ..default() })
            .with_children(f);
    });
}

/// `.ctl`: a flex row of controls, gap 12.
pub fn ctl(p: &mut ChildSpawnerCommands, extra: Node, f: impl FnOnce(&mut ChildSpawnerCommands)) {
    p.spawn(Node { align_items: AlignItems::Center, column_gap: px(12), ..extra }).with_children(f);
}

/// A unit label ('counts per inch', 'cm / 360°').
pub fn unit(p: &mut ChildSpawnerCommands, k: &Kit, s: &str, color: Color, live: Option<Live>) {
    let mut e = p.spawn(text_as(k.fonts, TextRole::Unit, s, color));
    if let Some(l) = live {
        e.insert(l);
    }
}

/// A segmented control. `off` lists options that cannot be picked yet (drawn at .35).
pub fn seg(p: &mut ChildSpawnerCommands, k: &Kit, c: Ch, dim: bool, off: &[usize]) -> Entity {
    let labels = choice_labels(k.ui, k.data, c, k.s);
    let value = get_choice(k.s, k.ui, k.data, c);
    let mut e = p.spawn((Node { flex_shrink: 0.0, ..default() }, SegBind(c), SegValue(value)));
    e.with_children(|g| {
        for (i, label) in labels.iter().enumerate() {
            let mut o = g.spawn((kit::segment(k.fonts, label, kit::SEG, 34.0, false), SegOption(i), ZIndex(0)));
            // Seg copy keeps its case ('NIGHT (compressed)'); the kit's Seg role already does.
            o.insert(Active(i == value));
            if dim || off.contains(&i) {
                o.insert(Disabled);
            }
        }
    });
    e.id()
}

/// A slider bound to a number: `width` px (or flex 1), tick labels at values.
pub fn slider(p: &mut ChildSpawnerCommands, k: &Kit, n: Num, width: Option<f32>, ticks: &[(f32, &str)], dim: bool) {
    let r = range(k.data, n);
    let frac = r.frac(get_num(k.s, k.ui, k.data, n));
    let mut hit = p.spawn((
        Node {
            width: width.map_or(Val::Auto, px),
            flex_grow: if width.is_none() { 1.0 } else { 0.0 },
            flex_shrink: if width.is_none() { 1.0 } else { 0.0 },
            height: px(24),
            align_items: AlignItems::Center,
            ..default()
        },
        Interaction::default(),
        RelativeCursorPosition::default(),
    ));
    if dim {
        hit.insert(Disabled);
    }
    let hit_id = hit.id();
    let mut fill = Entity::PLACEHOLDER;
    let mut thumb = Entity::PLACEHOLDER;
    hit.with_children(|h| {
        h.spawn((Node { width: percent(100), height: px(4), ..default() }, BackgroundColor(dimc(kit::W14, dim))))
            .with_children(|t| {
                fill = t
                    .spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: px(0),
                            top: px(0),
                            bottom: px(0),
                            width: percent(frac * 100.0),
                            ..default()
                        },
                        BackgroundColor(dimc(kit::TEXT_HI, dim)),
                    ))
                    .id();
                thumb = t
                    .spawn((
                        Node {
                            position_type: PositionType::Absolute,
                            left: percent(frac * 100.0),
                            top: px(-6),
                            width: px(16),
                            height: px(16),
                            margin: UiRect::left(px(-8)),
                            ..default()
                        },
                        BackgroundColor(dimc(kit::TEXT_HI, dim)),
                        UiTransform::from_rotation(Rot2::degrees(45.0)),
                    ))
                    .id();
                for (v, label) in ticks {
                    t.spawn((
                        text_as(k.fonts, TextRole::Tick, *label, dimc(kit::TEXT_LOW, dim)),
                        TextLayout::no_wrap(),
                        Node {
                            position_type: PositionType::Absolute,
                            top: px(10),
                            left: percent(r.frac(*v) * 100.0),
                            ..default()
                        },
                        UiTransform::from_translation(Val2::percent(-50.0, 0.0)),
                    ));
                }
            });
    });
    p.commands().entity(hit_id).insert(SliderBind { num: n, fill, thumb });
}

/// A number or text field (`.inp`): 36 tall (44 big), K35 fill, STROKE_HI border.
pub fn field(p: &mut ChildSpawnerCommands, k: &Kit, kind: FieldKind, width: f32, big: bool, dim: bool) -> Entity {
    let h = if big { 44.0 } else { 36.0 };
    let size = if big { 24.0 } else { 18.0 };
    let mut font = k.fonts.role_font(TextRole::Field);
    font.font_size = FontSize::Px(size);
    if kind == FieldKind::PlayerName {
        font.font_features = Default::default();
    }
    let text = field_text(kind, k.s, k.ui, k.data, k.profile);
    let pad_v = ((h - 2.0 - size * 1.2) / 2.0).max(0.0);
    let node = Node {
        width: px(width),
        height: px(h),
        padding: UiRect { left: px(10), right: px(10), top: px(pad_v), bottom: px(pad_v) },
        border: UiRect::all(px(1)),
        flex_shrink: 0.0,
        overflow: Overflow::clip(),
        ..default()
    };
    if dim {
        return p
            .spawn((
                node,
                BackgroundColor(dimc(kit::K35, true)),
                BorderColor::all(dimc(kit::STROKE_HI, true)),
                children![(
                    Text::new(text),
                    font,
                    TextColor(dimc(kit::TEXT_HI, true)),
                    LineHeight::RelativeToFont(1.2)
                )],
            ))
            .id();
    }
    let max = match kind {
        FieldKind::PlayerName => 16,
        FieldKind::CrosshairHex => 7,
        FieldKind::Num(_) => 9,
    };
    let filter = match kind {
        FieldKind::PlayerName => EditableTextFilter::new(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-'),
        FieldKind::CrosshairHex => EditableTextFilter::new(|c| c.is_ascii_hexdigit() || c == '#'),
        FieldKind::Num(_) => EditableTextFilter::new(|c| c.is_ascii_digit() || matches!(c, '.' | '-' | ',')),
    };
    let mut editable = EditableText::new(&text);
    editable.max_characters = Some(max);
    editable.cursor_width = 2.0 / size;
    p.spawn((
        node,
        BackgroundColor(kit::K35),
        BorderColor::all(kit::STROKE_HI),
        editable,
        filter,
        font,
        TextColor(kit::TEXT_HI),
        LineHeight::RelativeToFont(1.2),
        TextCursorStyle { color: kit::TEAL, selection_color: kit::TEAL.with_alpha(0.35), ..default() },
        SelectAllOnFocus,
        Interaction::default(),
        Field { kind, invalid: false, big },
    ))
    .id()
}

pub fn field_text(kind: FieldKind, s: &Settings, ui: &UiState, d: &SettingsData, profile: &PlayerProfile) -> String {
    match kind {
        FieldKind::Num(n) => num_text(n, get_num(s, ui, d, n)),
        FieldKind::PlayerName => profile.name.clone(),
        FieldKind::CrosshairHex => hex_string(s.crosshair_rgb()),
    }
}

/// Is a typed value acceptable?
pub fn field_valid(kind: FieldKind, text: &str, d: &SettingsData) -> bool {
    match kind {
        FieldKind::Num(n) => {
            let r = range(d, n);
            parse_num(text).is_some_and(|v| v >= r.min - 1e-6 && v <= r.max + 1e-6)
        }
        // The first-launch prompt's rules (3-16 letters, digits, space, - _ .).
        FieldKind::PlayerName => PlayerProfile::clean_name(text).is_some(),
        FieldKind::CrosshairHex => parse_hex(text).is_some(),
    }
}

/// A switch bound to an on/off value.
pub fn switch(p: &mut ChildSpawnerCommands, k: &Kit, t: Tg, dim: bool) {
    let on = get_toggle(k.s, t);
    let mut e = p.spawn((kit::switch(on), SwitchBind(t)));
    if dim {
        e.insert(Disabled);
    }
}

/// A dropdown (`.dd`): 36 tall, STROKE_HI border, the value and a chevron.
pub fn dropdown(p: &mut ChildSpawnerCommands, k: &Kit, c: Ch, width: f32, dim: bool) {
    let labels = choice_labels(k.ui, k.data, c, k.s);
    let value = labels.get(get_choice(k.s, k.ui, k.data, c)).cloned().unwrap_or_default();
    let looks = Looks::new(
        kit::Look::new(Color::NONE, kit::STROKE_HI, kit::TEXT_HI),
        kit::Look::new(kit::W06, kit::STROKE_HI, kit::TEXT_HI),
        kit::Look::new(kit::W06, kit::TEXT_HI, kit::TEXT_HI),
    );
    let mut label = Entity::PLACEHOLDER;
    let mut e = p.spawn((
        Button,
        Node {
            width: px(width),
            height: px(36),
            padding: UiRect::horizontal(px(10)),
            column_gap: px(16),
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::Center,
            border: UiRect::all(px(1)),
            flex_shrink: 0.0,
            ..default()
        },
        BackgroundColor(Color::NONE),
        BorderColor::all(kit::STROKE_HI),
        looks,
        Active(false),
    ));
    if dim {
        e.insert(Disabled);
    }
    e.with_children(|d| {
        label = d.spawn((text_as(k.fonts, TextRole::Select, value, dimc(kit::TEXT_HI, dim)), Ink)).id();
        d.spawn((kit::icon(k.images, kit::Icon::Chev, 12.0, dimc(kit::TEXT_HI, dim)), Ink));
    });
    let id = e.id();
    p.commands().entity(id).insert(Dropdown { choice: c, label });
}

/// `.note`: Barlow 12.5, line height 1.45, TEXT_MID; bold parts are Barlow 700 TEXT_HI.
pub fn note(p: &mut ChildSpawnerCommands, k: &Kit, parts: &[(&str, bool, Option<Live>)], extra: Node) {
    let base = k.fonts.role_font(TextRole::Note);
    let bold = k.fonts.role_font(TextRole::NoteBold);
    let mut sym = TextFont::from_font_size(12.0).with_font(k.symbols.clone());
    sym.font_size = FontSize::Px(12.0);
    p.spawn((Text::new(""), base.clone(), TextColor(kit::TEXT_MID), LineHeight::RelativeToFont(1.45), extra))
        .with_children(|t| {
            for (s, b, live) in parts {
                for (run, is_sym) in glyph_runs(s) {
                    let (font, color) = match (is_sym, *b) {
                        (true, _) => (sym.clone(), kit::TEXT_MID),
                        (false, true) => (bold.clone(), kit::TEXT_HI),
                        (false, false) => (base.clone(), kit::TEXT_MID),
                    };
                    let mut e = t.spawn((TextSpan::new(run), font, TextColor(color)));
                    if let Some(l) = live {
                        e.insert(*l);
                    }
                }
            }
        });
}

// ---------------------------------------------------------------------------------------------- behaviour

/// Segments write their choice.
pub fn seg_input(
    groups: Query<(&SegBind, &SegValue), Changed<SegValue>>,
    mut settings: ResMut<Settings>,
    mut ui: ResMut<UiState>,
    data: Res<SettingsData>,
) {
    for (b, v) in &groups {
        if get_choice(&settings, &ui, &data, b.0) == v.0 {
            continue;
        }
        // (The preview background lives in `UiState`, so it changes `ui`, not the settings.)
        let mut next = (*settings).clone();
        set_choice(&mut next, &mut ui, &data, b.0, v.0);
        if next != *settings {
            *settings = next;
        }
    }
}

/// Segments, switches and sliders follow the values (after a reset, a preset or another control).
pub fn sync_controls(
    settings: Res<Settings>,
    ui: Res<UiState>,
    data: Res<SettingsData>,
    mut segs: Query<(&SegBind, &mut SegValue)>,
    mut switches: Query<(&SwitchBind, &mut Switch, &mut BackgroundColor, &Children, Has<Disabled>)>,
    mut knobs: Query<(&mut Node, &mut BackgroundColor), (With<SwitchKnob>, Without<Switch>)>,
    sliders: Query<&SliderBind>,
    mut nodes: Query<&mut Node, (Without<SwitchKnob>, Without<SliderBind>)>,
    added: Query<(), Added<SliderBind>>,
) {
    if !settings.is_changed() && !ui.is_changed() && added.is_empty() {
        return;
    }
    for (b, mut v) in &mut segs {
        let want = get_choice(&settings, &ui, &data, b.0);
        if v.0 != want {
            v.0 = want;
        }
    }
    for (b, mut sw, mut bg, kids, dim) in &mut switches {
        let on = get_toggle(&settings, b.0);
        if sw.0 != on || bg.is_added() || dim {
            sw.0 = on;
            bg.0 = dimc(if on { kit::ALLY } else { kit::W14 }, dim);
            for k in kids.iter() {
                if let Ok((mut node, mut kbg)) = knobs.get_mut(k) {
                    node.left = px(if on { 25.0 } else { 3.0 });
                    kbg.0 = dimc(if on { kit::READY_INK } else { kit::TEXT_MID }, dim);
                }
            }
        }
    }
    for s in &sliders {
        let frac = range(&data, s.num).frac(get_num(&settings, &ui, &data, s.num)) * 100.0;
        if let Ok(mut n) = nodes.get_mut(s.fill)
            && n.width != percent(frac)
        {
            n.width = percent(frac);
        }
        if let Ok(mut n) = nodes.get_mut(s.thumb)
            && n.left != percent(frac)
        {
            n.left = percent(frac);
        }
    }
}

/// The active segment draws its border over its neighbours'.
pub fn seg_z(mut q: Query<(&Active, &mut ZIndex), (With<SegOption>, Changed<Active>)>) {
    for (a, mut z) in &mut q {
        z.0 = a.0 as i32;
    }
}

/// Switches write their value (the kit flips them on press).
pub fn switch_input(q: Query<(&SwitchBind, &Switch), Changed<Switch>>, mut settings: ResMut<Settings>) {
    for (b, sw) in &q {
        if get_toggle(&settings, b.0) != sw.0 {
            edit(&mut settings, |s| set_toggle(s, b.0, sw.0));
        }
    }
}

/// Sliders: drag (or click the track) to set, the wheel over a slider moves one step.
pub fn slider_input(
    q: Query<(&SliderBind, &Interaction, &RelativeCursorPosition), Without<Disabled>>,
    scroll: Res<AccumulatedMouseScroll>,
    mut settings: ResMut<Settings>,
    mut ui: ResMut<UiState>,
    data: Res<SettingsData>,
) {
    for (s, i, rel) in &q {
        let r = range(&data, s.num);
        let now = get_num(&settings, &ui, &data, s.num);
        let want = match i {
            Interaction::Pressed => rel.normalized.map(|n| r.at(n.x + 0.5)),
            Interaction::Hovered if scroll.delta.y != 0.0 => Some(r.snap(now + r.step * scroll.delta.y.signum())),
            _ => None,
        };
        let Some(v) = want else { continue };
        if (v - now).abs() > 1e-6 {
            let mut next = (*settings).clone();
            set_num(&mut next, &mut ui, &data, s.num, v);
            if next != *settings {
                *settings = next;
            }
        }
    }
}

/// The field being edited and what it holds this frame, so the edit is kept however focus leaves it: Enter,
/// a click elsewhere, another field, a rail tab, DONE / BACK (only Esc drops it).
#[derive(Debug, Clone, PartialEq)]
pub struct Editing {
    pub entity: Entity,
    pub kind: FieldKind,
    pub text: String,
}

/// Write a typed value (if valid) into the settings or the player profile.
#[allow(clippy::too_many_arguments)]
fn commit_text(
    kind: FieldKind,
    typed: &str,
    settings: &mut ResMut<Settings>,
    ui: &mut UiState,
    data: &SettingsData,
    profile: &mut PlayerProfile,
    session: &mut crate::net::Session,
) {
    if !field_valid(kind, typed, data) {
        return;
    }
    match kind {
        FieldKind::Num(n) => {
            let v = parse_num(typed).unwrap_or_default();
            let mut next = (**settings).clone();
            set_num(&mut next, ui, data, n, v);
            if next != **settings {
                **settings = next;
            }
        }
        FieldKind::PlayerName => {
            let Some(name) = PlayerProfile::clean_name(typed) else { return };
            if profile.name != name {
                profile.name = name.clone();
                session.local_name = name;
                if let Err(err) = crate::user_config::save(PlayerProfile::FILE, &*profile) {
                    warn!("could not save the player name: {err}");
                }
            }
        }
        FieldKind::CrosshairHex => {
            let hex = parse_hex(typed).map(hex_string).unwrap_or_default();
            edit(settings, |s| s.crosshair.color = hex);
        }
    }
}

/// First in the screen's frame: an edit whose field lost the keyboard (to another field), or that a click
/// outside it ends (a rail tab, DONE / BACK, any control), is committed before those clicks act.
#[allow(clippy::too_many_arguments)]
pub fn commit_left_edit(
    fields: Query<&Interaction, With<Field>>,
    mut focus: ResMut<InputFocus>,
    mouse: Res<ButtonInput<MouseButton>>,
    mut settings: ResMut<Settings>,
    mut ui: ResMut<UiState>,
    data: Res<SettingsData>,
    mut profile: ResMut<PlayerProfile>,
    mut session: ResMut<crate::net::Session>,
) {
    let Some(ed) = ui.editing.clone() else { return };
    let moved = focus.get() != Some(ed.entity);
    let clicked_out =
        mouse.just_pressed(MouseButton::Left) && fields.get(ed.entity).is_ok_and(|i| *i == Interaction::None);
    if !(moved || clicked_out) {
        return;
    }
    ui.editing = None;
    commit_text(ed.kind, &ed.text, &mut settings, &mut ui, &data, &mut profile, &mut session);
    if focus.get() == Some(ed.entity) {
        focus.clear();
    }
}

/// Fields: show the value while not being edited; Enter commits (a click elsewhere too, see
/// [`commit_left_edit`]), Esc reverts (the screen's Esc handler); a typed value out of range shows a WARN
/// border.
#[allow(clippy::too_many_arguments)]
pub fn field_input(
    mut fields: Query<(Entity, &mut Field, &mut EditableText, &mut BorderColor)>,
    mut focus: ResMut<InputFocus>,
    keys: Res<ButtonInput<KeyCode>>,
    mut settings: ResMut<Settings>,
    mut ui: ResMut<UiState>,
    data: Res<SettingsData>,
    mut profile: ResMut<PlayerProfile>,
    mut session: ResMut<crate::net::Session>,
    time: Res<Time>,
) {
    ui.flash = (ui.flash - time.delta_secs()).max(0.0);
    let focused = focus.get();
    for (e, mut f, mut text, mut border) in &mut fields {
        if focused == Some(e) {
            let typed = text.value().to_string();
            let enter = keys.just_pressed(KeyCode::Enter) || keys.just_pressed(KeyCode::NumpadEnter);
            f.invalid = !typed.trim().is_empty() && !field_valid(f.kind, &typed, &data);
            if enter {
                ui.editing = None;
                commit_text(f.kind, &typed, &mut settings, &mut ui, &data, &mut profile, &mut session);
                f.invalid = false;
                focus.clear();
            } else {
                let ed = Editing { entity: e, kind: f.kind, text: typed };
                if ui.editing.as_ref() != Some(&ed) {
                    ui.editing = Some(ed);
                }
            }
        }
        let still_editing = focus.get() == Some(e);
        if !still_editing {
            let want = field_text(f.kind, &settings, &ui, &data, &profile);
            if text.value().to_string() != want {
                text.editor_mut().set_text(&want);
            }
            f.invalid = false;
        } else if f.kind == FieldKind::PlayerName {
            // Names are upper case: show them so while typing.
            let typed = text.value().to_string();
            if typed.chars().any(|c| c.is_ascii_lowercase()) {
                text.editor_mut().set_text(&typed.to_ascii_uppercase());
                text.queue_edit(bevy::text::TextEdit::TextEnd(false));
            }
        }
        let flash = f.kind == FieldKind::Num(Num::Cm) && ui.flash > 0.0;
        let color = if f.invalid {
            kit::WARN
        } else if still_editing || flash {
            kit::TEXT_HI
        } else {
            kit::STROKE_HI
        };
        if border.top != color {
            *border = BorderColor::all(color);
        }
    }
}

/// Esc while a field is being edited: put the value back and stop editing.
pub fn cancel_field_edit(focus: &mut InputFocus, fields: &Query<(), With<Field>>, ui: &mut UiState) -> bool {
    match focus.get() {
        Some(e) if fields.contains(e) => {
            // Dropped, not committed (see `commit_left_edit`).
            ui.editing = None;
            focus.clear();
            true
        }
        _ => false,
    }
}

/// Dropdowns: open a list under the button; a row picks; a click elsewhere or Esc closes.
pub fn dropdown_input(
    mut commands: Commands,
    buttons: Query<(Entity, &Interaction, &Dropdown, Has<Disabled>), Changed<Interaction>>,
    rows: Query<(&Interaction, &DropRow)>,
    all_rows: Query<&Interaction, With<DropRow>>,
    mouse: Res<ButtonInput<MouseButton>>,
    mut ui: ResMut<UiState>,
    mut settings: ResMut<Settings>,
    data: Res<SettingsData>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
) {
    // a row was picked
    for (i, r) in &rows {
        if *i == Interaction::Pressed {
            let mut next = (*settings).clone();
            set_choice(&mut next, &mut ui, &data, r.choice, r.index);
            if next != *settings {
                *settings = next;
            }
            close_dropdown(&mut commands, &mut ui);
            return;
        }
    }
    for (e, i, d, disabled) in &buttons {
        if *i != Interaction::Pressed || disabled {
            continue;
        }
        let reopen = ui.dropdown.is_none_or(|(b, _)| b != e);
        close_dropdown(&mut commands, &mut ui);
        if reopen {
            let labels = choice_labels(&ui, &data, d.choice, &settings);
            let current = get_choice(&settings, &ui, &data, d.choice);
            let list = commands
                .spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        top: percent(100),
                        left: px(-1),
                        right: px(-1),
                        flex_direction: FlexDirection::Column,
                        border: UiRect::all(px(1)),
                        margin: UiRect::top(px(2)),
                        // Long lists (a monitor's modes) scroll with the wheel, opened on the current choice.
                        max_height: px(DROP_ROWS as f32 * DROP_ROW_H + 2.0),
                        overflow: Overflow::scroll_y(),
                        ..default()
                    },
                    ScrollPosition(Vec2::new(0.0, current.saturating_sub(DROP_ROWS / 2) as f32 * DROP_ROW_H)),
                    BackgroundColor(kit::PANEL_SOLID),
                    BorderColor::all(kit::STROKE_HI),
                    GlobalZIndex(130),
                    ChildOf(e),
                ))
                .id();
            for (idx, label) in labels.iter().enumerate() {
                let on = idx == current;
                let looks = Looks::new(
                    kit::Look::new(Color::NONE, Color::NONE, if on { kit::TEXT_HI } else { kit::TEXT }),
                    kit::Look::new(kit::W06, Color::NONE, kit::TEXT_HI),
                    kit::Look::new(kit::W06, Color::NONE, kit::TEXT_HI),
                );
                commands.spawn((
                    Button,
                    DropRow { choice: d.choice, index: idx },
                    Node {
                        height: px(DROP_ROW_H),
                        padding: UiRect::horizontal(px(10)),
                        justify_content: JustifyContent::SpaceBetween,
                        align_items: AlignItems::Center,
                        flex_shrink: 0.0,
                        ..default()
                    },
                    BackgroundColor(Color::NONE),
                    looks,
                    ChildOf(list),
                    children![
                        (text_as(&fonts, TextRole::Select, label.clone(), looks.idle.ink), Ink),
                        (kit::icon(&images, kit::Icon::Check, 14.0, if on { kit::TEXT_HI } else { Color::NONE }),),
                    ],
                ));
            }
            ui.dropdown = Some((e, list));
        }
        return;
    }
    // a click outside the open list closes it
    if ui.dropdown.is_some()
        && mouse.just_pressed(MouseButton::Left)
        && all_rows.iter().all(|i| *i == Interaction::None)
        && buttons.is_empty()
    {
        close_dropdown(&mut commands, &mut ui);
    }
}

/// An open list shows this many rows at a time, each this tall.
const DROP_ROWS: usize = 12;
const DROP_ROW_H: f32 = 36.0;

/// The mouse wheel scrolls an open dropdown list, kept within its content.
pub fn scroll_dropdown(
    ui: Res<UiState>,
    scroll: Res<AccumulatedMouseScroll>,
    mut lists: Query<(&mut ScrollPosition, &ComputedNode)>,
) {
    let Some((_, list)) = ui.dropdown else { return };
    if scroll.delta.y == 0.0 {
        return;
    }
    if let Ok((mut pos, node)) = lists.get_mut(list) {
        let step = match scroll.unit {
            bevy::input::mouse::MouseScrollUnit::Line => DROP_ROW_H,
            bevy::input::mouse::MouseScrollUnit::Pixel => 1.0,
        };
        let max = ((node.content_size().y - node.size().y) * node.inverse_scale_factor()).max(0.0);
        pos.y = (pos.y - scroll.delta.y * step).clamp(0.0, max);
    }
}

pub fn close_dropdown(commands: &mut Commands, ui: &mut UiState) {
    if let Some((_, list)) = ui.dropdown.take()
        && let Ok(mut e) = commands.get_entity(list)
    {
        e.despawn();
    }
}

/// Dropdown buttons show the current value.
pub fn sync_dropdowns(
    settings: Res<Settings>,
    ui: Res<UiState>,
    data: Res<SettingsData>,
    q: Query<&Dropdown>,
    mut texts: Query<&mut Text>,
) {
    if !settings.is_changed() && !ui.is_changed() {
        return;
    }
    for d in &q {
        let labels = choice_labels(&ui, &data, d.choice, &settings);
        let want = labels.get(get_choice(&settings, &ui, &data, d.choice)).cloned().unwrap_or_default();
        if let Ok(mut t) = texts.get_mut(d.label)
            && t.0 != want
        {
            t.0 = want;
        }
    }
}

#[allow(clippy::type_complexity)]
pub fn sync_live(
    settings: Res<Settings>,
    ui: Res<UiState>,
    data: Res<SettingsData>,
    mut texts: Query<(&Live, Option<&mut Text>, Option<&mut TextSpan>, Option<&mut TextColor>)>,
    mut boxes: Query<(&Live, &mut Node, Option<&mut BackgroundColor>), Without<Text>>,
    added: Query<(), Added<Live>>,
) {
    if !settings.is_changed() && !ui.is_changed() && added.is_empty() {
        return;
    }
    let m = &settings.mouse;
    let (ally, enemy) = settings.team_colors();
    for (live, text, span, color) in &mut texts {
        let want: Option<String> = match live {
            Live::TurnUnits => Some(format!(
                "= {} in · {}° per count",
                fmt_num(m.cm_per_360 / 2.54, 1),
                fmt_num(deg_per_count(m.cm_per_360, m.dpi), 4)
            )),
            Live::RulerLabel => Some(format!("{} cm", fmt_num(m.cm_per_360, 1))),
            Live::FormulaExample => {
                let y = data.import_yaw.valorant;
                Some(format!(
                    "Valorant {} at {} DPI → {} cm. ",
                    fmt_num(sens_for(m.cm_per_360, m.dpi, y), 3),
                    m.dpi,
                    fmt_num(m.cm_per_360, 1)
                ))
            }
            Live::OtherGame(g) => {
                let yaw = match g {
                    0 => data.import_yaw.valorant,
                    1 => data.import_yaw.cs2,
                    _ => data.import_yaw.overwatch2,
                };
                Some(fmt_num(sens_for(m.cm_per_360, m.dpi, yaw), 3))
            }
            Live::FovUnits => Some(format!("= {}° vertical · Valorant uses 103°", fmt_num(vertical_fov(m.fov_h), 1))),
            Live::CrosshairCode => Some(format!("COPY / PASTE CODE: {}", settings.crosshair_code())),
            Live::PresetMicro => Some(format!(
                "PRESET: {}{}",
                settings.video.preset.label(),
                if settings.quality_custom(&data.presets) { " · CUSTOM" } else { "" }
            )),
            Live::TeamAlly => {
                if let Some(mut c) = color {
                    c.0 = ally;
                }
                None
            }
            Live::TeamEnemy => {
                if let Some(mut c) = color {
                    c.0 = enemy;
                }
                None
            }
            Live::TopHint => {
                let (s, c) = match &ui.save_error {
                    Some(_) => ("Could not save settings.ron", kit::WARN),
                    None => ("Changes apply instantly · saved to settings.ron", kit::TEXT_MID),
                };
                if let Some(mut col) = color {
                    col.0 = c;
                }
                Some(s.to_string())
            }
            _ => None,
        };
        let Some(want) = want else { continue };
        if let Some(mut t) = text {
            if t.0 != want {
                t.0 = want;
            }
        } else if let Some(mut t) = span
            && t.0 != want
        {
            t.0 = want;
        }
    }
    for (live, mut node, bg) in &mut boxes {
        match live {
            Live::Ruler => node.width = px(ruler_px(m.cm_per_360)),
            Live::TeamAllySquare => {
                if let Some(mut bg) = bg {
                    bg.0 = ally;
                }
            }
            Live::TeamEnemySquare => {
                if let Some(mut bg) = bg {
                    bg.0 = enemy;
                }
            }
            _ => {}
        }
    }
}

/// The display a field lives in uses Barlow Condensed (kept here so callers need not import Face).
pub fn display_font(fonts: &UiFonts, weight: u16, size: f32) -> TextFont {
    fonts.font(Face::Display, weight, size)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn values_round_trip_through_their_controls() {
        let d = embedded();
        let mut s = d.defaults.clone();
        let mut ui = UiState::default();
        for (k, v) in [
            (Num::Dpi, 1600.0),
            (Num::Cm, 33.3),
            (Num::FovH, 90.0),
            (Num::Vol(3), 55.0),
            (Num::RadialHold, 0.35),
            (Num::HostPort, 50000.0),
            (Num::Optic(0), 0.92),
        ] {
            set_num(&mut s, &mut ui, d, k, v);
            assert!((get_num(&s, &ui, d, k) - v).abs() < 1e-4, "{k:?}");
        }
        assert_eq!(s.optic_mult("optic_reddot"), 0.92, "one ADS row covers holo and red dot");
        set_num(&mut s, &mut ui, d, Num::Dpi, 99999.0);
        assert_eq!(s.mouse.dpi, 32000, "typed values clamp");
        for c in [Ch::Aa, Ch::KillFeed, Ch::XhDot, Ch::Vsync, Ch::TeamColours, Ch::HoldToggle] {
            let n = choice_labels(&ui, d, c, &s).len();
            for i in 0..n {
                set_choice(&mut s, &mut ui, d, c, i);
                assert_eq!(get_choice(&s, &ui, d, c), i, "{c:?} {i}");
            }
        }
        // the net graph switch and the overlay segment are one value
        set_toggle(&mut s, Tg::NetGraph, true);
        assert_eq!(s.video.overlay, Overlay::Network);
        set_toggle(&mut s, Tg::NetGraph, false);
        assert_eq!(s.video.overlay, Overlay::Fps);
        // the import box shows the current equivalent until something is typed
        let mut s = d.defaults.clone();
        assert!((get_num(&s, &ui, d, Num::ImportSens) - 0.4).abs() < 0.001);
        set_choice(&mut s, &mut ui, d, Ch::ImportGame, ImportGame::Cs2.index());
        assert!((get_num(&s, &ui, d, Num::ImportSens) - 1.273).abs() < 0.001);
    }

    /// Typing another game's sensitivity and pressing Enter (or clicking DONE) sets the turn, without APPLY,
    /// and the in-match look follows it.
    #[test]
    fn a_typed_import_sensitivity_sets_the_turn_without_apply() {
        use bevy::ecs::system::RunSystemOnce;
        let d = embedded();
        let mut w = World::new();
        w.insert_resource(d.defaults.clone());
        w.insert_resource(d.clone());
        w.init_resource::<InputFocus>();
        w.init_resource::<ButtonInput<MouseButton>>();
        w.insert_resource(PlayerProfile::default());
        w.init_resource::<crate::net::Session>();
        let hip = crate::client::look_per_count(w.resource::<Settings>(), None, 1.0, 0.0);
        // Valorant 0.2 at the default 800 DPI: twice the default 40.8 cm
        let field = w.spawn_empty().id();
        let editing = Editing { entity: field, kind: FieldKind::Num(Num::ImportSens), text: "0.2".into() };
        w.insert_resource(UiState { editing: Some(editing), ..default() });
        w.run_system_once(commit_left_edit).unwrap();
        let s = w.resource::<Settings>();
        assert!((s.mouse.cm_per_360 - 81.6).abs() < 0.05, "{}", s.mouse.cm_per_360);
        assert_eq!(w.resource::<UiState>().import_sens, None, "the box shows the new turn's equivalent");
        let now = crate::client::look_per_count(s, None, 1.0, 0.0);
        assert!((now / hip - 0.5).abs() < 1e-3, "half as fast: {}", now / hip);
        // CS2 / Apex 1.0 at 1600 DPI = 25.98 cm
        let (mut s, mut ui) = (d.defaults.clone(), UiState::default());
        s.mouse.dpi = 1600;
        s.mouse.import_game = ImportGame::Apex;
        set_num(&mut s, &mut ui, d, Num::ImportSens, 1.0);
        assert!((s.mouse.cm_per_360 - 26.0).abs() < 0.05, "{}", s.mouse.cm_per_360);
    }

    #[test]
    fn number_text_and_validation() {
        let d = embedded();
        assert_eq!(num_text(Num::FovH, 103.0), "103°");
        assert_eq!(num_text(Num::RenderScale, 100.0), "100 %");
        assert_eq!(num_text(Num::SafeArea, 32.0), "32 px");
        assert_eq!(num_text(Num::Cm, 40.8), "40.8");
        assert_eq!(num_text(Num::RadialHold, 0.2), "0.20 s");
        assert!(field_valid(FieldKind::Num(Num::FovH), "95", d));
        assert!(!field_valid(FieldKind::Num(Num::FovH), "200", d), "out of range warns");
        assert!(!field_valid(FieldKind::Num(Num::Dpi), "abc", d));
        assert!(field_valid(FieldKind::CrosshairHex, "#52E5A5", d));
        assert!(!field_valid(FieldKind::CrosshairHex, "#52E5", d));
        assert!(field_valid(FieldKind::PlayerName, "kestrel_you", d));
        assert!(!field_valid(FieldKind::PlayerName, "!!", d));
        assert_eq!(glyph_runs("A / ✕"), vec![("A / ".to_string(), false), ("✕".to_string(), true)]);
    }
}
