//! Builder chrome only. Buttons send EditorAction; the controller owns documents and world changes.
use crate::build_editor::{EditorAction, EditorActive, EditorState, PlaceTool};
use crate::ui_kit::{self as kit, BtnKind, BtnSize, Face, UiFonts};
use bevy::prelude::*;
use vetf_sim::build_mode::{EditableItem, PropDescriptor};

pub(crate) const PAGE_SIZE: usize = 8;

/// Controller ray-picks should ignore the pointer while any of these panels is hovered/pressed.
#[derive(Component)]
pub(crate) struct EditorPanel;
#[derive(Component)]
pub(crate) struct EditorUiRoot;

#[derive(SystemSet, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub(crate) enum EditorUiSystems {
    Input,
    Refresh,
}

#[derive(Clone, Copy)]
enum PaletteTool {
    Select,
    Hedge,
    Bush,
    SpawnA,
    SpawnB,
    SpawnFfa,
    Clip,
    Extract,
    Loot,
}

#[derive(Component)]
struct EditorButton(UiAction);
enum UiAction {
    Prop(String),
    Tool(PaletteTool),
    Save,
    Reload,
    Undo,
    Redo,
    Play,
    Delete,
    Duplicate,
    Drop,
    Lock,
    Loot,
    Move(usize, f64),
    Rotate(f64),
    Scale(bool),
    Resize(usize, f64),
    Snap,
    Grid,
    Angle,
    SearchFocus(bool),
    ClearSearch,
    Page(i32),
}

pub fn plugin(app: &mut App) {
    app.add_systems(Update, dispatch.in_set(EditorUiSystems::Input))
        .add_systems(Update, refresh.in_set(EditorUiSystems::Refresh).after(EditorUiSystems::Input));
}

fn tool(choice: PaletteTool) -> PlaceTool {
    match choice {
        PaletteTool::Select => PlaceTool::Select,
        PaletteTool::Hedge => PlaceTool::Hedge,
        PaletteTool::Bush => PlaceTool::Bush,
        PaletteTool::SpawnA => PlaceTool::SpawnA,
        PaletteTool::SpawnB => PlaceTool::SpawnB,
        PaletteTool::SpawnFfa => PlaceTool::SpawnFfa,
        PaletteTool::Clip => PlaceTool::Clip,
        PaletteTool::Extract => PlaceTool::Extract,
        PaletteTool::Loot => PlaceTool::Loot,
    }
}

fn action(choice: &UiAction, state: Option<&EditorState>) -> EditorAction {
    match choice {
        UiAction::Prop(id) => EditorAction::Tool(PlaceTool::Prop(id.clone())),
        UiAction::Tool(t) => EditorAction::Tool(tool(*t)),
        UiAction::Save => EditorAction::Save,
        UiAction::Reload => EditorAction::Reload,
        UiAction::Undo => EditorAction::Undo,
        UiAction::Redo => EditorAction::Redo,
        UiAction::Play => EditorAction::Play,
        UiAction::Delete => EditorAction::Delete,
        UiAction::Duplicate => EditorAction::Duplicate,
        UiAction::Drop => EditorAction::Drop,
        UiAction::Lock => EditorAction::ToggleLock,
        UiAction::Loot => EditorAction::ToggleLoot,
        UiAction::Move(axis, delta) => {
            let mut v = [0.; 3];
            v[*axis] = *delta;
            EditorAction::Move(v)
        }
        UiAction::Rotate(delta) => EditorAction::Rotate(*delta),
        UiAction::Scale(up) => {
            let prop = state
                .and_then(|s| s.selected.as_ref().and_then(|id| s.document()?.item(id)))
                .is_some_and(|i| matches!(i, EditableItem::Prop(_)));
            EditorAction::Scale(if prop {
                if *up { 0.05 } else { -0.05 }
            } else if *up {
                1.05
            } else {
                0.95
            })
        }
        UiAction::Resize(axis, delta) => EditorAction::Resize(*axis, *delta),
        UiAction::Snap => EditorAction::ToggleSnap,
        UiAction::Grid => EditorAction::NextGrid,
        UiAction::Angle => EditorAction::NextAngle,
        UiAction::SearchFocus(on) => EditorAction::SearchFocus(*on),
        UiAction::ClearSearch => EditorAction::Search(String::new()),
        UiAction::Page(delta) => EditorAction::Page(*delta),
    }
}

#[allow(clippy::type_complexity)]
fn dispatch(
    active: Option<Res<EditorActive>>,
    state: Option<Res<EditorState>>,
    mouse: Option<Res<ButtonInput<MouseButton>>>,
    buttons: Query<(&Interaction, &EditorButton), (Changed<Interaction>, Without<kit::Disabled>)>,
    mut messages: MessageWriter<EditorAction>,
) {
    if !active.is_some_and(|a| a.0) || mouse.is_some_and(|m| !m.just_pressed(MouseButton::Left)) {
        return;
    }
    for (interaction, button) in &buttons {
        if *interaction == Interaction::Pressed {
            messages.write(action(&button.0, state.as_deref()));
        }
    }
}

fn text(commands: &mut Commands, fonts: &UiFonts, parent: Entity, value: impl Into<String>, size: f32, color: Color) {
    commands.spawn((
        fonts.text(value, Face::Body, 500, size, color, 0.0),
        EditorPanel,
        Interaction::None,
        ChildOf(parent),
    ));
}
fn row(commands: &mut Commands, parent: Entity) -> Entity {
    commands
        .spawn((
            Node { width: percent(100), column_gap: px(6), align_items: AlignItems::Center, ..default() },
            ChildOf(parent),
        ))
        .id()
}
fn button(
    commands: &mut Commands,
    fonts: &UiFonts,
    parent: Entity,
    label: &str,
    choice: UiAction,
    kind: BtnKind,
    enabled: bool,
) {
    let entity = commands
        .spawn((kit::button(fonts, label, kind, BtnSize::Xs), EditorButton(choice), EditorPanel, ChildOf(parent)))
        .id();
    if !enabled {
        commands.entity(entity).insert(kit::Disabled);
    }
}
fn panel(commands: &mut Commands, parent: Entity, mut node: Node) -> Entity {
    if node.padding == UiRect::default() {
        node.padding = UiRect::all(px(14));
    }
    if node.row_gap == px(0) {
        node.row_gap = px(8);
    }
    commands.spawn((kit::panel_bg(node, kit::PANEL_SOLID), EditorPanel, Interaction::None, ChildOf(parent))).id()
}

fn filtered<'a>(props: &'a [PropDescriptor], search: &str) -> Vec<&'a PropDescriptor> {
    let words: Vec<String> = search.split_whitespace().map(str::to_lowercase).collect();
    let mut rows: Vec<_> = props
        .iter()
        .filter(|p| {
            let hay = format!("{} {} {}", p.id, p.category, p.tags.join(" ")).to_lowercase();
            words.iter().all(|word| hay.contains(word))
        })
        .collect();
    rows.sort_by(|a, b| a.id.cmp(&b.id));
    rows
}

fn selected_tool(state: &EditorState, wanted: PaletteTool) -> bool {
    match state.placement.as_ref() {
        None => matches!(wanted, PaletteTool::Select),
        Some(current) => std::mem::discriminant(current) == std::mem::discriminant(&tool(wanted)),
    }
}

fn catalog(commands: &mut Commands, fonts: &UiFonts, parent: Entity, state: &EditorState) {
    text(commands, fonts, parent, "CATALOG", 21., kit::TEAL);
    let search = row(commands, parent);
    let short_search: String = state.search.chars().take(24).collect();
    let label = if state.search.is_empty() {
        "Search props…".to_owned()
    } else {
        format!("{}{}", short_search, if state.search_focus { " |" } else { "" })
    };
    button(
        commands,
        fonts,
        search,
        &label,
        UiAction::SearchFocus(true),
        if state.search_focus { BtnKind::Primary } else { BtnKind::Normal },
        true,
    );
    button(commands, fonts, search, "CLEAR", UiAction::ClearSearch, BtnKind::Normal, !state.search.is_empty());
    if state.search_focus {
        button(commands, fonts, parent, "DONE TYPING", UiAction::SearchFocus(false), BtnKind::Normal, true);
    }
    let choices = [
        (PaletteTool::Select, "SELECT"),
        (PaletteTool::Hedge, "HEDGE"),
        (PaletteTool::Bush, "BUSH"),
        (PaletteTool::SpawnA, "SPAWN A"),
        (PaletteTool::SpawnB, "SPAWN B"),
        (PaletteTool::SpawnFfa, "SPAWN FFA"),
        (PaletteTool::Clip, "PLAYER CLIP"),
        (PaletteTool::Extract, "EXTRACT"),
        (PaletteTool::Loot, "LOOT SPOT"),
    ];
    for pair in choices.chunks(2) {
        let line = row(commands, parent);
        for (choice, label) in pair {
            button(
                commands,
                fonts,
                line,
                label,
                UiAction::Tool(*choice),
                if selected_tool(state, *choice) { BtnKind::Primary } else { BtnKind::Normal },
                true,
            );
        }
    }
    let Some(cat) = state.catalog.as_ref() else {
        text(commands, fonts, parent, "Loading reusable props…", 14., kit::TEXT_MID);
        return;
    };
    let matches = filtered(&cat.props, &state.search);
    let pages = matches.len().div_ceil(PAGE_SIZE).max(1);
    let page = state.page.min(pages - 1);
    text(
        commands,
        fonts,
        parent,
        format!("{} props  /  PAGE {} OF {}", matches.len(), page + 1, pages),
        13.,
        kit::TEXT_MID,
    );
    let paging = row(commands, parent);
    button(commands, fonts, paging, "PREV", UiAction::Page(-1), BtnKind::Normal, page > 0);
    button(commands, fonts, paging, "NEXT", UiAction::Page(1), BtnKind::Normal, page + 1 < pages);
    for prop in matches.into_iter().skip(page * PAGE_SIZE).take(PAGE_SIZE) {
        let active = matches!(&state.placement,Some(PlaceTool::Prop(id)) if id==&prop.id);
        button(
            commands,
            fonts,
            parent,
            &prop.id.replace('_', " "),
            UiAction::Prop(prop.id.clone()),
            if active { BtnKind::Primary } else { BtnKind::Normal },
            true,
        );
    }
    if cat.props.is_empty() {
        text(commands, fonts, parent, "The catalog is empty.", 14., kit::TEXT_MID);
    }
    text(
        commands,
        fonts,
        parent,
        "Select a tool, then click the world to place.\nRMB + WASD flies the camera.",
        13.,
        kit::TEXT_LOW,
    );
}

fn inspector(commands: &mut Commands, fonts: &UiFonts, parent: Entity, state: &EditorState) {
    text(commands, fonts, parent, "SELECTED OBJECT", 21., kit::TEAL);
    let selected = state.selected.as_deref().and_then(|id| state.document()?.item(id));
    let Some(item) = selected else {
        text(commands, fonts, parent, "Choose SELECT, then click an object in the world.", 15., kit::TEXT_MID);
        return;
    };
    let locked = item.locked();
    let pos = item.position();
    text(commands, fonts, parent, item.id(), 16., kit::TEXT_HI);
    let (details, yaw, scale, dimensions, can_scale, can_loot) = match &item {
        EditableItem::Prop(p) => (
            format!("PROP / {}\nMODE {}  /  LOOT {}", p.prop_id, p.mode, if p.lootable { "ON" } else { "OFF" }),
            Some(p.yaw_deg),
            Some(p.scale),
            None,
            true,
            true,
        ),
        EditableItem::Foliage(p) => (
            format!("FOLIAGE / {}\n{} / density {:.2}\nMODE {}", p.kind.as_str(), p.tint, p.density, p.mode),
            Some(p.yaw_deg),
            None,
            Some(p.dimensions_m),
            true,
            false,
        ),
        EditableItem::Clip(p) => (
            format!("PLAYER CLIP / {}\nPHYS {} / MODE {}", p.kind, p.phys, p.mode),
            None,
            None,
            Some(std::array::from_fn(|i| p.max[i] - p.min[i])),
            true,
            false,
        ),
        EditableItem::Spawn(p) => (
            format!("SPAWN / {}\nMODE {}", p.team.as_deref().unwrap_or("FFA"), p.mode),
            Some(p.yaw_deg),
            None,
            None,
            false,
            false,
        ),
        EditableItem::Extract(p) => (
            format!("EXTRACT / {}\n{} / radius {:.2} m\nMODE {}", p.name, p.shape, p.radius_m, p.mode),
            Some(p.yaw_deg),
            None,
            p.size_m,
            true,
            false,
        ),
        EditableItem::Loot(p) => (
            format!(
                "LOOT / {}\nCHANCE {:.0}% / MAX {}\nMODE {}",
                p.loot_table,
                p.spawn_chance * 100.,
                p.max_count,
                p.mode
            ),
            None,
            None,
            None,
            false,
            false,
        ),
    };
    text(commands, fonts, parent, details, 14., kit::TEXT_MID);
    text(
        commands,
        fonts,
        parent,
        format!("{}  /  design metres", if locked { "LOCKED" } else { "EDITABLE" }),
        13.,
        if locked { kit::CORAL } else { kit::TEXT_LOW },
    );
    text(commands, fonts, parent, "POSITION", 14., kit::TEXT_HI);
    let step = state.options.position_snap_m;
    for axis in 0..3 {
        let line = row(commands, parent);
        text(commands, fonts, line, format!("{}  {:9.2}", ["X", "Y", "Z"][axis], pos[axis]), 15., kit::TEXT);
        button(commands, fonts, line, "−", UiAction::Move(axis, -step), BtnKind::Normal, !locked);
        button(commands, fonts, line, "+", UiAction::Move(axis, step), BtnKind::Normal, !locked);
    }
    if let Some(yaw) = yaw {
        let line = row(commands, parent);
        text(commands, fonts, line, format!("YAW {:.1}°", yaw), 15., kit::TEXT);
        button(commands, fonts, line, "−", UiAction::Rotate(-state.options.yaw_snap_deg), BtnKind::Normal, !locked);
        button(commands, fonts, line, "+", UiAction::Rotate(state.options.yaw_snap_deg), BtnKind::Normal, !locked);
    }
    if can_scale {
        let line = row(commands, parent);
        text(commands, fonts, line, scale.map_or("SCALE".into(), |s| format!("SCALE {s:.2}")), 15., kit::TEXT);
        button(commands, fonts, line, "−", UiAction::Scale(false), BtnKind::Normal, !locked);
        button(commands, fonts, line, "+", UiAction::Scale(true), BtnKind::Normal, !locked);
    }
    if let Some(size) = dimensions {
        text(commands, fonts, parent, "DIMENSIONS / METRES", 14., kit::TEXT_HI);
        for axis in 0..3 {
            let line = row(commands, parent);
            text(commands, fonts, line, format!("{}  {:.2}", ["X", "Y", "Z"][axis], size[axis]), 15., kit::TEXT);
            button(commands, fonts, line, "−", UiAction::Resize(axis, -step), BtnKind::Normal, !locked);
            button(commands, fonts, line, "+", UiAction::Resize(axis, step), BtnKind::Normal, !locked);
        }
    }
    let line = row(commands, parent);
    button(commands, fonts, line, "DROP TO GROUND", UiAction::Drop, BtnKind::Normal, !locked);
    button(commands, fonts, line, if locked { "UNLOCK" } else { "LOCK" }, UiAction::Lock, BtnKind::Normal, true);
    let line = row(commands, parent);
    button(commands, fonts, line, "DUPLICATE", UiAction::Duplicate, BtnKind::Normal, !locked);
    button(commands, fonts, line, "DELETE", UiAction::Delete, BtnKind::Danger, !locked);
    if can_loot {
        button(commands, fonts, parent, "TOGGLE LOOTABLE", UiAction::Loot, BtnKind::Normal, !locked);
    }
}

fn refresh(
    mut commands: Commands,
    active: Option<Res<EditorActive>>,
    state: Option<Res<EditorState>>,
    fonts: Option<Res<UiFonts>>,
    mut roots: Query<(Entity, &mut Node), With<EditorUiRoot>>,
    mut revision: Local<Option<u64>>,
) {
    let enabled = active.is_some_and(|a| a.0);
    if !enabled {
        for (_, mut node) in &mut roots {
            node.display = Display::None;
        }
        return;
    }
    for (_, mut node) in &mut roots {
        node.display = Display::Flex;
    }
    let (Some(state), Some(fonts)) = (state, fonts) else { return };
    if *revision == Some(state.ui_revision) && !roots.is_empty() {
        return;
    }
    for (entity, _) in &roots {
        commands.entity(entity).despawn();
    }
    *revision = Some(state.ui_revision);
    let root = commands
        .spawn((
            EditorUiRoot,
            Node { width: percent(100), height: percent(100), position_type: PositionType::Absolute, ..default() },
            GlobalZIndex(50),
            DespawnOnExit(crate::AppState::InGame),
        ))
        .id();
    let toolbar = panel(
        &mut commands,
        root,
        Node {
            height: px(62),
            padding: UiRect::horizontal(px(14)),
            flex_direction: FlexDirection::Row,
            align_items: AlignItems::Center,
            column_gap: px(8),
            ..kit::abs(Some(12.), Some(12.), Some(12.), None)
        },
    );
    let map = state.document().map_or("LOADING", |d| d.map_id.as_str());
    text(
        &mut commands,
        &fonts,
        toolbar,
        format!("BUILDER / {map} {}", if state.dirty { "• UNSAVED" } else { "• SAVED" }),
        19.,
        kit::TEAL,
    );
    let have = state.document().is_some();
    for (label, choice, kind) in [
        ("SAVE", UiAction::Save, BtnKind::Primary),
        ("RELOAD", UiAction::Reload, BtnKind::Normal),
        ("UNDO", UiAction::Undo, BtnKind::Normal),
        ("REDO", UiAction::Redo, BtnKind::Normal),
        ("PLAY / F8", UiAction::Play, BtnKind::Normal),
    ] {
        let enabled = have || matches!(choice, UiAction::Play);
        button(&mut commands, &fonts, toolbar, label, choice, kind, enabled);
    }
    let left = panel(
        &mut commands,
        root,
        Node {
            width: px(320),
            flex_direction: FlexDirection::Column,
            ..kit::abs(Some(12.), None, Some(86.), Some(64.))
        },
    );
    catalog(&mut commands, &fonts, left, &state);
    let right = panel(
        &mut commands,
        root,
        Node {
            width: px(354),
            flex_direction: FlexDirection::Column,
            ..kit::abs(None, Some(12.), Some(86.), Some(64.))
        },
    );
    inspector(&mut commands, &fonts, right, &state);
    let footer = panel(
        &mut commands,
        root,
        Node {
            height: px(40),
            flex_direction: FlexDirection::Row,
            align_items: AlignItems::Center,
            column_gap: px(10),
            padding: UiRect::horizontal(px(12)),
            ..kit::abs(Some(12.), Some(12.), None, Some(12.))
        },
    );
    button(
        &mut commands,
        &fonts,
        footer,
        if state.snap { "SNAP ON" } else { "SNAP OFF" },
        UiAction::Snap,
        BtnKind::Normal,
        true,
    );
    button(
        &mut commands,
        &fonts,
        footer,
        &format!("GRID {:.2} m", state.options.position_snap_m),
        UiAction::Grid,
        BtnKind::Normal,
        true,
    );
    button(
        &mut commands,
        &fonts,
        footer,
        &format!("ANGLE {:.0}°", state.options.yaw_snap_deg),
        UiAction::Angle,
        BtnKind::Normal,
        true,
    );
    text(&mut commands, &fonts, footer, &state.status, 13., kit::TEXT_MID);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn editor_ui_buttons_send_actions_only_when_active_and_only_on_press() {
        let mut app = App::new();
        app.add_message::<EditorAction>().insert_resource(EditorActive(false)).add_systems(Update, dispatch);
        let button = app.world_mut().spawn((EditorButton(UiAction::Save), Interaction::Pressed)).id();
        app.update();
        assert!(app.world().resource::<Messages<EditorAction>>().is_empty());
        app.world_mut().resource_mut::<EditorActive>().0 = true;
        *app.world_mut().get_mut::<Interaction>(button).unwrap() = Interaction::Hovered;
        app.update();
        *app.world_mut().get_mut::<Interaction>(button).unwrap() = Interaction::Pressed;
        app.update();
        let sent: Vec<_> = app.world_mut().resource_mut::<Messages<EditorAction>>().drain().collect();
        assert_eq!(sent.len(), 1);
        assert!(matches!(sent[0], EditorAction::Save));
        app.update();
        assert!(app.world().resource::<Messages<EditorAction>>().is_empty());
    }
}
