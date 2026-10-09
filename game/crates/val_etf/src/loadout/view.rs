//! Layout of the Loadout page (mockup 05, with the adapted weapon column for the magazine strip). The page
//! is a fixed frame of section containers; each section rebuilds its children when the inputs it shows
//! change (a hash of them), so hover and drag states elsewhere are left alone.

use super::apply::RespawnBtn;
use super::focus::Focusable;
use super::gun_preview::{GunPreview, HotspotAt, PreviewViewport};
use super::halo::{Centre, HaloImages, HaloLook, spawn_halo};
use super::model::{WeaponStats, parts_with, weapon_stats};
use super::popover::{self, preview_part, view_icon};
use super::text::{self, Tone};
use super::ui_data::{Accent, LoadoutUiData, TagSide, bar_frac};
use super::{Act, LoadoutEdit, LoadoutUi, Pop, SaveAsField, ScreenCtx, hash_of};
use crate::AppState;
use crate::config::Data;
use crate::death::DeathState;
use crate::screens::{Screen, ScreenRoot};
use crate::ui_kit::*;
use bevy::prelude::*;
use bevy::text::{EditableText, LetterSpacing, TextCursorStyle};
use bevy::ui::{
    BoxShadow, ColorStop, FocusPolicy, InterpolationColorSpace, LinearGradient, RelativeCursorPosition, ShadowStyle,
    VisualBox,
};
use bevy::window::PrimaryWindow;
use lightyear::prelude::Controlled;
use vetf_net::{MatchState, Vitals};
use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::data::{AmmoChoice, AmmoKind, AttachmentCategory, Core, WeightClass};
use vetf_sim::weapon::MAX_MAGS;

/// Sections of the page; each rebuilds on its own.
#[derive(Component, Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Section {
    TopBar,
    Agents,
    Tabs,
    Preview,
    Slots,
    Mags,
    Stats,
    Halo,
    Popover,
    Ghost,
    /// The deathmatch layout: the armor tier of the one halo.
    Armor,
    /// The deathmatch layout: one ammo type for every magazine.
    Ammo,
    /// The deathmatch layout: weight class, figures and the points used against the total.
    Result,
}

/// Left edge of the weapon column: next to the agents (gun range) or at the page's margin (deathmatch).
/// The gun preview's key hints. Nothing shows the gun on the agent from here, so there is no F hint (user, item B:
/// "remove the hint").
pub const PREVIEW_HINTS: [(&str, &str); 2] = [("LMB", "DRAG TO ROTATE"), ("WHEEL", "ZOOM")];

pub fn weapon_left(simple: bool) -> f32 {
    if simple { 48.0 } else { 432.0 }
}

#[derive(Component, Default)]
pub struct SectionKey(Option<u64>);

/// The dragged magazine card.
#[derive(Component)]
pub struct Ghost;

/// Everything a section needs to draw itself.
pub struct View<'a> {
    pub fonts: &'a UiFonts,
    pub images: &'a UiImages,
    pub halo: &'a HaloImages,
    pub data: &'a GameData,
    pub ui: &'a LoadoutUiData,
    pub edit: &'a LoadoutEdit,
    pub st: &'a LoadoutUi,
    pub ctx: ScreenCtx,
    /// Over the death screen: RESPAWN in CONFIRM's place, with its timer.
    pub respawn: Option<RespawnBtn>,
    /// The first Esc over the points showed its notice.
    pub warned: bool,
    /// The 3D preview, while it shows the gun's model.
    pub model: Option<&'a GunPreview>,
    /// The gun has a model (shown or being built): the 2D picture is not drawn.
    pub has_model: bool,
}

impl View<'_> {
    /// Would loading `ammo` into the popover's magazine slot go over the budget?
    pub fn over_with_mag(&self, pop: Pop, ammo: AmmoChoice) -> bool {
        let Pop::Mag(i) = pop else { return false };
        let Some(budget) = self.ctx.budget else { return false };
        let mut d = self.edit.draft.clone();
        if !d.set_mag(i, ammo) {
            return false;
        }
        d.gear(self.data).total() > budget
    }

    fn hover_row(&self) -> Option<usize> {
        self.st.hover_row.or(self.st.focus_row)
    }

    fn key(&self, s: Section) -> u64 {
        let d = &self.edit.draft;
        let parts = d.parts.get(&d.weapon);
        let preview =
            preview_part(d, self.st.pop, self.hover_row(), self.data, self.ui).map(|(c, p)| (c, p.map(|a| &a.id)));
        match s {
            Section::TopBar => hash_of(&(
                self.edit.file.presets.iter().map(|p| &p.name).collect::<Vec<_>>(),
                self.edit.file.active,
                self.st.save_as,
                self.ctx,
                self.respawn,
                self.warned,
                d.problems(self.data, self.ctx.budget),
                d.gear(self.data).total(),
            )),
            Section::Agents => hash_of(&d.agent),
            Section::Tabs => hash_of(&d.weapon),
            Section::Preview => {
                hash_of(&(&d.weapon, parts, self.st.pop, preview, self.model.is_some(), self.has_model))
            }
            Section::Slots => hash_of(&(&d.weapon, parts, self.st.pop, self.ctx)),
            Section::Mags => hash_of(&(
                &d.mags,
                &d.weapon,
                self.st.pop,
                self.st.drag.map(|g| (g.from, g.active, g.over)),
                self.st.flash.map(|f| f > 0.0),
            )),
            Section::Stats => hash_of(&(&d.weapon, parts, self.st.pop, preview)),
            Section::Halo => hash_of(&(d.halo, self.st.arc, &d.mags, &d.weapon, self.ctx)),
            Section::Popover => hash_of(&(self.st.pop, &d.weapon, parts, &d.mags, d.halo, self.ctx)),
            Section::Ghost => hash_of(&self.st.drag.filter(|g| g.active).map(|g| (g.from, d.mags.get(g.from)))),
            // Every pick card turns red when it would go over the total: each depends on the other picks.
            Section::Armor => hash_of(&(d.halo, &d.mags, &d.weapon, parts, self.ctx)),
            Section::Ammo => hash_of(&(&d.mags, &d.weapon, d.halo, parts, self.ctx, self.st.flash[0] > 0.0)),
            Section::Result => hash_of(&(d.halo, &d.mags, &d.weapon, parts, self.ctx)),
        }
    }

    fn build(&self, s: Section, p: &mut ChildSpawnerCommands) {
        match s {
            Section::TopBar => self.top_bar(p),
            Section::Agents => self.agents(p),
            Section::Tabs => self.tabs(p),
            Section::Preview => self.preview(p),
            Section::Slots => self.slots(p),
            Section::Mags => self.mags(p),
            Section::Stats => self.stats(p),
            Section::Halo => self.halo_column(p),
            Section::Popover => popover::build(self, p),
            Section::Ghost => self.ghost(p),
            Section::Armor => self.armor(p),
            Section::Ammo => self.ammo(p),
            Section::Result => self.kit_result(p),
        }
    }
}

/// Text in a role without its upper-casing (mixed-case copy such as the in-match warning).
fn raw(fonts: &UiFonts, role: TextRole, s: impl Into<String>, color: Color) -> impl Bundle {
    let r = role.spec();
    (Text::new(s), fonts.role_font(role), TextColor(color), LetterSpacing::Px(r.size * r.em), r.line)
}

pub(super) fn section(s: Section) -> impl Bundle {
    (s, SectionKey::default())
}

/// A dashed 1 px border (9-slice), tinted.
fn dashed(images: &UiImages, color: Color) -> impl Bundle {
    use bevy::sprite::{BorderRect, SliceScaleMode, TextureSlicer};
    (ImageNode {
        visual_box: VisualBox::BorderBox,
        ..ImageNode::new(images.shape(Shape::Dash9Slice)).with_color(color).with_mode(NodeImageMode::Sliced(
            TextureSlicer {
                border: BorderRect::all(2.0),
                center_scale_mode: SliceScaleMode::Stretch,
                sides_scale_mode: SliceScaleMode::Tile { stretch_value: 0.5 },
                max_corner_scale: 0.5,
            },
        ))
    },)
}

/// The page frame: background, sections and footer. Sections fill themselves in [`refresh`]. `simple`: the
/// deathmatch layout (the gun and its parts, the MAG slot being the magazine type, on the left; armor tier, ammo and points on the
/// right; no agents, no magazine strip); else the gun range's (agents, gun with its magazines, halo).
pub fn spawn_root(commands: &mut Commands, z: i32, simple: bool) {
    let bg = page_background(50.0, 35.0, [(0x18202B, 0.0), (0x0A0D12, 55.0), (0x06080B, 100.0)]);
    commands
        .spawn((
            ScreenRoot(Screen::Loadout),
            GlobalZIndex(z),
            Node { position_type: PositionType::Absolute, width: percent(100), height: percent(100), ..default() },
            BackgroundColor(BG0),
            // Block clicks to whatever is under the page.
            FocusPolicy::Block,
            Interaction::default(),
        ))
        .with_children(|root| {
            root.spawn(bg);
            root.spawn((section(Section::TopBar), top_bar(84.0, 28.0)));
            if !simple {
                root.spawn((
                    section(Section::Agents),
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(48),
                        top: px(108),
                        width: px(360),
                        flex_direction: FlexDirection::Column,
                        ..default()
                    },
                ));
            }
            root.spawn(Node {
                position_type: PositionType::Absolute,
                left: px(weapon_left(simple)),
                top: px(108),
                width: px(872),
                flex_direction: FlexDirection::Column,
                ..default()
            })
            .with_children(|w| {
                w.spawn((section(Section::Tabs), Node { height: px(62), column_gap: px(6), ..default() }));
                // The preview box: the 3D gun (its camera's picture, `gun_preview`), and over it the section
                // with the hotspots and hints (or the 2D picture of a gun without a model).
                let fill = || Node {
                    position_type: PositionType::Absolute,
                    left: px(0),
                    top: px(0),
                    width: percent(100),
                    height: percent(100),
                    ..default()
                };
                w.spawn((
                    Node {
                        height: px(430),
                        margin: UiRect::top(px(10)),
                        border: UiRect::all(px(1)),
                        overflow: Overflow::clip(),
                        ..default()
                    },
                    BorderColor::all(STROKE),
                    BackgroundColor(PREVIEW_BG),
                ))
                .with_children(|b| {
                    b.spawn((PreviewViewport, RelativeCursorPosition::default(), FocusPolicy::Pass, fill()));
                    b.spawn((section(Section::Preview), fill()));
                });
                w.spawn((
                    section(Section::Slots),
                    Node { height: px(76), margin: UiRect::top(px(10)), column_gap: px(6), ..default() },
                ));
                // The gun range's six ordered magazines. The deathmatch layout has no magazine row: the MAG
                // slot's pick is the magazine type, and everyone carries six of it.
                if !simple {
                    w.spawn((
                        section(Section::Mags),
                        Node { margin: UiRect::top(px(10)), flex_direction: FlexDirection::Column, ..default() },
                    ));
                }
                w.spawn((section(Section::Stats), Node { margin: UiRect::top(px(10)), ..default() }));
            });
            if simple {
                super::kit_view::spawn_column(root, weapon_left(true) + 872.0 + 48.0);
            } else {
                root.spawn((
                    section(Section::Halo),
                    Node {
                        position_type: PositionType::Absolute,
                        right: px(48),
                        top: px(108),
                        width: px(544),
                        flex_direction: FlexDirection::Column,
                        ..default()
                    },
                ));
            }
            root.spawn(footer_marker());
            root.spawn((
                section(Section::Popover),
                GlobalZIndex(z + 5),
                Node { position_type: PositionType::Absolute, left: px(0), top: px(0), ..default() },
            ));
            root.spawn((super::focus::ring(), GlobalZIndex(z + 4)));
            root.spawn((
                section(Section::Ghost),
                GlobalZIndex(z + 6),
                Node { position_type: PositionType::Absolute, left: px(0), top: px(0), ..default() },
            ));
        });
}

#[derive(Component)]
pub struct Footer;

fn footer_marker() -> impl Bundle {
    (
        Footer,
        Node {
            position_type: PositionType::Absolute,
            left: px(48),
            right: px(48),
            bottom: px(24),
            column_gap: px(22),
            align_items: AlignItems::Center,
            ..default()
        },
    )
}

/// One footer hint with ghost key caps (Loadout uses the ghost style).
fn ghost_hint(fonts: &UiFonts, keys: &[&str], label: &str) -> impl Bundle {
    let caps: Vec<_> = keys.iter().map(|k| keycap(fonts, k, KeyStyle::Ghost, 22.0)).collect();
    (
        Node { column_gap: px(7), align_items: AlignItems::Center, ..default() },
        Children::spawn((SpawnIter(caps.into_iter()), Spawn(fonts.role(TextRole::Hint, label)))),
    )
}

/// Rebuild the sections whose inputs changed (and fill the footer once).
#[allow(clippy::too_many_arguments)]
pub fn refresh(
    mut commands: Commands,
    mut sections: Query<(Entity, &Section, &mut SectionKey)>,
    footers: Query<(Entity, Option<&Children>), With<Footer>>,
    fonts: Res<UiFonts>,
    images: Res<UiImages>,
    halo: Option<Res<HaloImages>>,
    data: Res<Data>,
    ui_data: Res<LoadoutUiData>,
    edit: Res<LoadoutEdit>,
    st: Res<LoadoutUi>,
    state: Res<State<AppState>>,
    matches: Query<&MatchState>,
    (death, me, gun): (Option<Res<DeathState>>, Query<&Vitals, With<Controlled>>, Option<Res<GunPreview>>),
) {
    let Some(halo) = halo else { return };
    let ctx = ScreenCtx::new(&data, state.get(), &matches, death.as_deref());
    let respawn = death.filter(|_| ctx.dead).map(|d| {
        let left = me.iter().next().map_or(f32::MAX, crate::death::respawn_left);
        RespawnBtn::new(left, edit.valid(&data, ctx.budget), d.asked)
    });
    let warned = super::apply::warned(&edit, &st);
    let v = View {
        fonts: &fonts,
        images: &images,
        halo: &halo,
        data: &data,
        ui: &ui_data,
        edit: &edit,
        st: &st,
        ctx,
        respawn,
        warned,
        model: gun.as_deref().filter(|g| g.live()),
        has_model: gun.as_deref().is_some_and(|g| g.has_model),
    };
    for (e, s, mut key) in &mut sections {
        let k = v.key(*s);
        if key.0 == Some(k) {
            continue;
        }
        key.0 = Some(k);
        commands.entity(e).despawn_related::<Children>();
        commands.entity(e).with_children(|p| v.build(*s, p));
    }
    for (e, kids) in &footers {
        if kids.is_none_or(|k| k.is_empty()) {
            let simple = edit.draft.fixed.is_some();
            commands.entity(e).with_children(|f| {
                f.spawn(ghost_hint(&fonts, &["Q", "E"], "SWITCH COLUMN"));
                f.spawn(ghost_hint(&fonts, &["1", "2", "3"], "PRESET"));
                f.spawn(ghost_hint(&fonts, &["R"], "RESET SLOT"));
                if simple {
                    f.spawn(ghost_hint(&fonts, &["ENTER"], "PICK"));
                } else {
                    f.spawn(ghost_hint(&fonts, &["LMB"], "DRAG TO REORDER MAGS"));
                }
            });
        }
    }
}

/// Keep the dragged card under the cursor.
pub fn move_ghost(
    st: Res<LoadoutUi>,
    windows: Query<&Window, With<PrimaryWindow>>,
    scale: Res<UiScale>,
    mut ghosts: Query<&mut Node, With<Ghost>>,
) {
    let Some(drag) = st.drag.filter(|d| d.active) else { return };
    let Some(cursor) = windows.iter().next().and_then(|w| w.cursor_position()) else { return };
    let at = cursor / scale.0 - drag.grab;
    for mut n in &mut ghosts {
        n.left = px(at.x);
        n.top = px(at.y);
    }
}

/// The preview box's inner size (its 1 px border inside the 872 x 430 box).
const INNER: (f32, f32) = (870.0, 428.0);

/// Place a hotspot: its dot centred on `xy` (UI px in the preview box), its tag on `side`.
pub fn place_hotspot(node: &mut Node, side: TagSide, xy: Vec2) {
    let (x, y) = (xy.x, xy.y);
    *node = Node { position_type: PositionType::Absolute, align_items: AlignItems::Center, ..default() };
    match side {
        TagSide::Right => {
            node.left = px(x - 7.0);
            node.top = px(y - 12.0);
            node.height = px(24);
            node.column_gap = px(8);
        }
        TagSide::Left => {
            node.right = px(INNER.0 - x - 7.0);
            node.top = px(y - 12.0);
            node.height = px(24);
            node.column_gap = px(8);
            node.flex_direction = FlexDirection::RowReverse;
        }
        TagSide::Below => {
            node.left = px(x - 7.0);
            node.top = px(y - 7.0);
            node.flex_direction = FlexDirection::Column;
            node.align_items = AlignItems::FlexStart;
            node.row_gap = px(6);
        }
        TagSide::Above => {
            node.left = px(x - 7.0);
            node.bottom = px(INNER.1 - y - 7.0);
            node.flex_direction = FlexDirection::ColumnReverse;
            node.align_items = AlignItems::FlexStart;
            node.row_gap = px(6);
        }
    }
}

/// A preview hotspot (dot and tag) and its dot.
#[derive(Component)]
pub struct Hotspot;

#[derive(Component)]
pub struct HotspotDot {
    selected: bool,
}

/// Hovering a hotspot fills its dot (the selected one stays teal).
pub fn hotspot_hover(
    spots: Query<(&Interaction, &Children), (Changed<Interaction>, With<Hotspot>)>,
    mut dots: Query<(&HotspotDot, &mut BackgroundColor)>,
) {
    for (i, kids) in &spots {
        for k in kids.iter() {
            if let Ok((dot, mut bg)) = dots.get_mut(k)
                && !dot.selected
            {
                bg.0 = if matches!(i, Interaction::Hovered | Interaction::Pressed) { TEXT_HI } else { K40 };
            }
        }
    }
}

/// Arrow-key focus in the popover (the row looks "on").
pub fn focus_rows(st: Res<LoadoutUi>, mut rows: Query<(&Act, &mut Active)>) {
    for (a, mut on) in &mut rows {
        if let Act::Row(r) = a {
            let want = st.focus_row == Some(*r);
            if on.0 != want {
                on.0 = want;
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------- looks

/// Slot and magazine cards: header ink TEXT_MID, open = TEAL. (Borders on fills: `white_on`, see the kit.)
const CARD: Looks = Looks::new(
    Look::new(W03, white_on(0.16, 0.03), TEXT_MID),
    Look::new(W06, white_on(0.32, 0.06), TEXT_MID),
    Look::new(hexa(0x00DACE, 0.08), TEAL, TEAL),
);

/// Weapon tabs.
const TAB: Looks = Looks::new(
    Look::new(W03, white_on(0.16, 0.03), TEXT_MID),
    Look::new(W06, white_on(0.32, 0.06), TEXT_MID),
    Look::new(W07, TEXT_HI, TEXT_HI),
);

pub(super) fn tier_looks(c: Color) -> Looks {
    Looks::new(
        Look::new(Color::NONE, STROKE_MID, c),
        Look::new(W06, white_on(0.32, 0.06), c),
        Look::new(translucent(c, 0.08), c, c),
    )
}

// ---------------------------------------------------------------------------------------------- sections

impl View<'_> {
    fn top_bar(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        p.spawn(f.role(TextRole::ScreenTitle, "LOADOUT"));
        p.spawn(Node { column_gap: px(6), align_items: AlignItems::Center, ..default() }).with_children(|chips| {
            for i in 0..super::presets::PRESET_COUNT {
                // The preset the edit was loaded from (CONFIRM saves into it).
                let on = i == self.edit.file.active;
                chips.spawn((
                    Button,
                    Act::Preset(i),
                    chip_node(),
                    BackgroundColor(Color::NONE),
                    BorderColor::all(STROKE_MID),
                    CHIP,
                    Active(on),
                    children![(f.role(TextRole::Chip, self.edit.file.label(i)), Ink)],
                ));
            }
            if self.st.save_as {
                chips.spawn((
                    SaveAsField,
                    Node { width: px(106), ..chip_node() },
                    BorderColor::all(TEAL),
                    BackgroundColor(K45),
                    EditableText { allow_newlines: false, max_characters: Some(super::presets::NAME_MAX), ..default() },
                    f.role_font(TextRole::Chip),
                    TextColor(TEXT_HI),
                    LetterSpacing::Px(TextRole::Chip.spacing_px()),
                    TextCursorStyle { color: TEAL, ..default() },
                ));
            } else {
                chips.spawn((
                    Button,
                    Act::SaveAs,
                    Node { border: UiRect::all(px(0)), ..chip_node() },
                    BackgroundColor(Color::NONE),
                    Looks::new(
                        Look::new(Color::NONE, Color::NONE, TEXT_MID),
                        Look::new(W12, Color::NONE, TEXT_HI),
                        Look::new(W12, Color::NONE, TEXT_HI),
                    ),
                    dashed(self.images, STROKE_MID),
                    children![(f.role(TextRole::Chip, "+ SAVE AS"), Ink)],
                ));
            }
        });
        p.spawn(spacer());
        let problems = d.problems(self.data, self.ctx.budget);
        let over = problems.iter().find_map(|pr| match pr {
            super::model::Problem::OverBudget { used, budget } => Some((*used, *budget)),
            _ => None,
        });
        // Team deathmatch and free-for-all: the points used against the total, always on show (red when over).
        if self.ctx.simple()
            && let Some(budget) = self.ctx.budget
        {
            let used = d.gear(self.data).total();
            let color = if used > budget { BAD } else { TEXT_HI };
            p.spawn((
                f.text(text::points_total(used, budget), Face::Display, 700, 16.0, color, 0.0),
                TextLayout::no_wrap(),
            ));
        }
        if self.warned {
            p.spawn(raw(f, TextRole::Hint, "Over the points: fix it, or press Esc again to discard", BAD));
        } else if let Some((used, budget)) = over {
            let hint = if self.ctx.simple() {
                format!("Over by {}: lower the armor, the ammo or the magazine", used - budget)
            } else {
                format!("Over gear budget: {used} / {budget} pts")
            };
            p.spawn(raw(f, TextRole::Hint, hint, BAD));
        } else if self.ctx.dead {
            p.spawn(raw(f, TextRole::Hint, "Dead: your picks go into your next life", TEXT_MID));
        } else if self.ctx.lobby {
            p.spawn(raw(f, TextRole::Hint, "Lobby: you wear it as soon as you confirm", TEXT_MID));
        } else if self.ctx.in_match {
            p.spawn(raw(f, TextRole::Hint, "In match: changes apply on your next spawn", WARN));
        }
        // Both are the last row of the keyboard focus (focus::columns), so the keyboard can finish the edit.
        p.spawn((Act::Back, Focusable, button_with_key(f, "BACK", "ESC", BtnKind::Normal, BtnSize::M)));
        // Over the death screen CONFIRM's place is RESPAWN with its timer (the edits are already applied).
        let (label, enabled) = match self.respawn {
            Some(r) => (r.label(), r.enabled()),
            None => ("CONFIRM".to_string(), problems.is_empty()),
        };
        let mut confirm = p.spawn((Act::Confirm, Focusable, button(f, &label, BtnKind::Primary, BtnSize::M)));
        if !enabled {
            confirm.insert(Disabled);
        }
    }

    fn agents(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let agents = &self.ui.agents;
        let sel = self.ui.agent(&self.edit.draft.agent).map_or(0, |(i, _)| i);
        p.spawn((
            Node {
                justify_content: JustifyContent::SpaceBetween,
                align_items: AlignItems::Baseline,
                margin: UiRect::bottom(px(10)),
                ..default()
            },
            children![
                f.role(TextRole::H2, "AGENT"),
                f.role(TextRole::Micro, format!("{} OF {} · ABILITIES NOT IN THIS BUILD", sel + 1, agents.len())),
            ],
        ));
        for (i, a) in agents.iter().enumerate() {
            let on = i == sel;
            let accent = match a.accent {
                Accent::Teal => AGENT_KESTREL,
                Accent::Coral => AGENT_SOLACE,
            };
            let looks = Looks::new(
                Look::new(BG1, STROKE_MID, TEXT_HI),
                Look::new(BG1, STROKE_HI, TEXT_HI),
                Look::new(BG1, TEAL, TEXT_HI),
            );
            let portrait = match a.portrait.as_str() {
                "solace_portrait.jpg" => self.images.art(Art::SolacePortrait),
                _ => self.images.art(Art::KestrelPortrait),
            };
            let shadow = if on {
                BoxShadow(vec![ShadowStyle {
                    color: hexa(0x00DACE, 0.18),
                    x_offset: px(0),
                    y_offset: px(0),
                    spread_radius: px(0),
                    // Bevy's blur reads about twice as wide as CSS's for the same radius.
                    blur_radius: px(12),
                }])
            } else {
                BoxShadow(vec![])
            };
            p.spawn((
                Button,
                Act::Agent(i),
                Focusable,
                Node {
                    height: px(150),
                    margin: UiRect::bottom(px(10)),
                    border: UiRect::all(px(if on { 2.0 } else { 1.0 })),
                    overflow: Overflow::clip(),
                    ..default()
                },
                BackgroundColor(BG1),
                BorderColor::all(if on { TEAL } else { STROKE_MID }),
                looks,
                Active(on),
                shadow,
            ))
            .with_children(|c| {
                c.spawn((
                    ImageNode::new(portrait),
                    Node {
                        position_type: PositionType::Absolute,
                        right: px(-20),
                        top: px(-10),
                        width: px(200),
                        height: px(200),
                        ..default()
                    },
                ));
                c.spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(0),
                        right: px(0),
                        top: px(0),
                        bottom: px(0),
                        ..default()
                    },
                    BackgroundGradient::from(
                        LinearGradient::to_right(vec![
                            ColorStop::new(BG1, percent(38)),
                            ColorStop::new(BG1.with_alpha(0.0), percent(75)),
                        ])
                        .in_color_space(InterpolationColorSpace::Srgba),
                    ),
                ));
                c.spawn((
                    Node {
                        position_type: PositionType::Absolute,
                        left: px(18),
                        top: px(18),
                        flex_direction: FlexDirection::Column,
                        ..default()
                    },
                    children![
                        f.role_color(TextRole::AgentL, &a.name, if on { TEXT_HI } else { TEXT_MID }),
                        (
                            f.role_color(TextRole::Subtitle, &a.role, accent),
                            Node { margin: UiRect::top(px(2)), ..default() }
                        ),
                    ],
                ));
                c.spawn(Node {
                    position_type: PositionType::Absolute,
                    left: px(18),
                    bottom: px(16),
                    column_gap: px(6),
                    ..default()
                })
                .with_children(|strip| {
                    for ab in &a.abilities {
                        strip.spawn((
                            Node {
                                width: px(34),
                                height: px(34),
                                align_items: AlignItems::Center,
                                justify_content: JustifyContent::Center,
                                border: UiRect::all(px(1)),
                                ..default()
                            },
                            BackgroundColor(K50),
                            BorderColor::all(STROKE_MID),
                            children![icon(self.images, ability_icon(&ab.icon), 22.0, TEXT_HI)],
                        ));
                    }
                });
                if on {
                    c.spawn((
                        Node { position_type: PositionType::Absolute, right: px(10), top: px(10), ..default() },
                        children![tag(f, "SELECTED", TEAL, false)],
                    ));
                }
            });
        }
        // Abilities of the selected agent.
        let Some(a) = agents.get(sel) else { return };
        p.spawn(panel(Node {
            padding: UiRect::axes(px(16), px(14)),
            flex_direction: FlexDirection::Column,
            ..default()
        }))
        .with_children(|list| {
            let n = a.abilities.len();
            for (i, ab) in a.abilities.iter().enumerate() {
                list.spawn((
                    Node {
                        column_gap: px(10),
                        padding: UiRect::vertical(px(8)),
                        border: UiRect::bottom(px(if i + 1 < n { 1.0 } else { 0.0 })),
                        ..default()
                    },
                    BorderColor::all(STROKE),
                ))
                .with_children(|row| {
                    row.spawn((
                        Node {
                            width: px(40),
                            height: px(40),
                            flex_shrink: 0.0,
                            align_items: AlignItems::Center,
                            justify_content: JustifyContent::Center,
                            border: UiRect::all(px(1)),
                            ..default()
                        },
                        BorderColor::all(STROKE_MID),
                        children![icon(self.images, ability_icon(&ab.icon), 26.0, TEXT_HI)],
                    ));
                    row.spawn(Node { flex_direction: FlexDirection::Column, flex_grow: 1.0, ..default() })
                        .with_children(|t| {
                            t.spawn((
                                Node { align_items: AlignItems::Baseline, column_gap: px(5), ..default() },
                                children![
                                    f.role(TextRole::AbilityTitle, format!("{} · {}", ab.key, ab.name)),
                                    f.role(TextRole::Micro, &ab.meta),
                                ],
                            ));
                            t.spawn((
                                f.role(TextRole::Desc, &ab.text),
                                Node { margin: UiRect::top(px(1)), ..default() },
                            ));
                        });
                });
            }
        });
    }

    fn tabs(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let n = self.data.offered_weapons().count().max(1);
        // Two tabs use the mockup's sizes; three need the smaller ones (spec A6).
        let (name_px, name_em, sub_px, sub_em, sil): (f32, f32, f32, f32, Option<(f32, f32)>) =
            if n <= 2 { (22.0, 0.08, 12.0, 0.18, None) } else { (20.0, 0.08, 11.0, 0.18, Some((96.0, 26.0))) };
        for (i, w) in self.data.offered_weapons() {
            let on = w.id == self.edit.draft.weapon;
            p.spawn((
                Button,
                Act::Weapon(i),
                Focusable,
                Node {
                    flex_grow: 1.0,
                    flex_basis: px(0),
                    height: px(62),
                    padding: UiRect::horizontal(px(16)),
                    column_gap: px(14),
                    align_items: AlignItems::Center,
                    border: UiRect::all(px(1)),
                    ..default()
                },
                BackgroundColor(if on { W07 } else { W03 }),
                BorderColor::all(if on { TEXT_HI } else { STROKE_MID }),
                TAB,
                Active(on),
            ))
            .with_children(|t| {
                if let Some(icon_id) = silhouette(&w.id) {
                    let (iw, ih) = if icon_id == Icon::Warden { (560.0, 128.0) } else { (480.0, 128.0) };
                    let (w_px, h_px) = match sil {
                        Some((bw, bh)) => {
                            let k = (bw / iw).min(bh / ih);
                            (iw * k, ih * k)
                        }
                        None => (if icon_id == Icon::Warden { 150.0 } else { 130.0 }, 35.0),
                    };
                    t.spawn((
                        ImageNode::new(self.images.icon(icon_id)).with_color(if on {
                            BONE
                        } else {
                            translucent(BONE, 0.6)
                        }),
                        Node { width: px(w_px), height: px(h_px), flex_shrink: 0.0, ..default() },
                    ));
                }
                t.spawn(Node { flex_direction: FlexDirection::Column, ..default() }).with_children(|c| {
                    c.spawn((
                        f.text(w.name.to_uppercase(), Face::Display, 700, name_px, TEXT_MID, name_em),
                        Ink,
                        TextLayout::no_wrap(),
                    ));
                    c.spawn((
                        f.text(text::weapon_subtitle(self.ui, w), Face::Display, 600, sub_px, TEXT_LOW, sub_em),
                        TextLayout::no_wrap(),
                    ));
                });
            });
        }
    }

    fn preview(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let Some(spec) = self.ui.ui.previews.get(&d.weapon) else { return };
        let (l, t, w, h) = spec.rect;
        let img = if self.has_model {
            None
        } else if !spec.image.is_empty() {
            Some((self.images.art(Art::MakoDark), Color::WHITE))
        } else if !spec.icon.is_empty() {
            Some((self.images.icon(icon_by_name(&spec.icon)), translucent(BONE, spec.alpha)))
        } else {
            None
        };
        if let Some((handle, tint)) = img {
            p.spawn((
                ImageNode::new(handle).with_color(tint),
                Node {
                    position_type: PositionType::Absolute,
                    left: px(l),
                    top: px(t),
                    width: px(w),
                    height: px(h),
                    ..default()
                },
            ));
        }
        p.spawn((
            Node {
                position_type: PositionType::Absolute,
                left: px(0),
                right: px(0),
                bottom: px(0),
                height: px(120),
                ..default()
            },
            BackgroundGradient::from(
                LinearGradient::to_top(vec![
                    ColorStop::new(hexa(0x090B0E, 0.9), percent(0)),
                    ColorStop::new(hexa(0x090B0E, 0.0), percent(100)),
                ])
                .in_color_space(InterpolationColorSpace::Srgba),
            ),
        ));
        // Hotspots: one per slot that has parts for this gun.
        let preview = preview_part(d, self.st.pop, self.hover_row(), self.data, self.ui);
        for hs in &spec.hotspots {
            if super::model::parts_for(self.data, &d.weapon, hs.slot).is_empty() {
                continue;
            }
            let selected = self.st.pop == Some(Pop::Slot(hs.slot));
            let part = match preview {
                Some((c, part)) if c == hs.slot => part,
                _ => d.equipped(hs.slot, self.data),
            };
            let value = part.map_or("NONE".to_string(), |a| a.short_name().to_uppercase());
            let mut node = Node::default();
            // On the 3D gun the dot sits on its slot's socket and follows it (`gun_preview::place_hotspots`).
            let at = HotspotAt { slot: hs.slot, side: hs.model_side.unwrap_or(hs.side) };
            let model = self.model.map(|m| m.spot(hs.slot));
            match model {
                Some(Some(xy)) => place_hotspot(&mut node, at.side, xy),
                // A slot the model has no socket for.
                Some(None) => continue,
                None => place_hotspot(&mut node, hs.side, Vec2::new(hs.x, hs.y)),
            }
            let mut spot = p.spawn((Button, Act::Slot(hs.slot), Hotspot, node));
            if model.is_some() {
                spot.insert(at);
            }
            spot.with_children(|g| {
                let (dot_bg, dot_border) = if selected { (TEAL, TEAL) } else { (K40, TEXT_HI) };
                g.spawn((
                    HotspotDot { selected },
                    Node {
                        width: px(14),
                        height: px(14),
                        flex_shrink: 0.0,
                        border: UiRect::all(px(2)),
                        border_radius: BorderRadius::MAX,
                        ..default()
                    },
                    BackgroundColor(dot_bg),
                    BorderColor::all(dot_border),
                    Outline::new(px(if selected { 5.0 } else { 0.0 }), px(0), hexa(0x00DACE, 0.25)),
                ));
                g.spawn((
                    Node {
                        padding: UiRect::axes(px(8), px(3)),
                        border: UiRect::all(px(1)),
                        align_items: AlignItems::Baseline,
                        ..default()
                    },
                    BackgroundColor(hexa(0x07090D, 0.85)),
                    BorderColor::all(if selected { TEAL } else { STROKE_MID }),
                    children![
                        (
                            f.text(hs.slot.label(), Face::Display, 600, 13.0, TEXT_MID, 0.12),
                            Node { margin: UiRect::right(px(6)), ..default() },
                            TextLayout::no_wrap(),
                        ),
                        (f.role(TextRole::HotspotValue, value), TextLayout::no_wrap()),
                    ],
                ));
            });
        }
        p.spawn(Node {
            position_type: PositionType::Absolute,
            left: px(14),
            bottom: px(12),
            column_gap: px(16),
            ..default()
        })
        .with_children(|h| {
            for (key, label) in PREVIEW_HINTS {
                h.spawn((
                    Node { column_gap: px(6), align_items: AlignItems::Center, ..default() },
                    children![keycap(f, key, KeyStyle::Ghost, 22.0), f.role(TextRole::StatKey, label)],
                ));
            }
        });
    }

    fn slots(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        for cat in AttachmentCategory::ALL {
            let fits = !super::model::parts_for(self.data, &d.weapon, cat).is_empty();
            let part = d.equipped(cat, self.data);
            let on = self.st.pop == Some(Pop::Slot(cat));
            let (value, color) = if !fits {
                ("—".to_string(), TEXT_LOW)
            } else {
                match part {
                    Some(a) => (a.display_name().to_uppercase(), TEXT_HI),
                    None => ("NONE".to_string(), TEXT_LOW),
                }
            };
            let mut card = p.spawn((
                Button,
                Act::Slot(cat),
                Focusable,
                card_node(),
                BackgroundColor(if on { CARD.on.bg } else { CARD.idle.bg }),
                BorderColor::all(if on { CARD.on.border } else { CARD.idle.border }),
                CARD,
                Active(on),
            ));
            // Team deathmatch and free-for-all: the MAG slot is the magazine type, carried six times, and every
            // card shows the points of what it holds (FREE muted).
            let label = match (&d.fixed, cat) {
                (Some(kit), AttachmentCategory::Mag) => text::mag_slot_label(kit.mags),
                _ => cat.label().to_string(),
            };
            let pts = d.slot_points(cat, self.data).filter(|_| fits);
            card.with_children(|c| {
                c.spawn(Node { column_gap: px(6), align_items: AlignItems::Center, ..default() }).with_children(|h| {
                    h.spawn((icon(self.images, view_icon(cat), 16.0, if on { TEAL } else { TEXT_MID }), Ink));
                    h.spawn((f.role(TextRole::TableHead, label), Ink));
                    if let Some(pts) = pts {
                        h.spawn(spacer());
                        h.spawn((
                            f.role_color(TextRole::Micro, text::points(pts), price_color(pts, false)),
                            TextLayout::no_wrap(),
                        ));
                    }
                });
                c.spawn((
                    f.role_color(TextRole::SlotValue, value, color),
                    Node { margin: UiRect::top(px(6)), overflow: Overflow::clip(), ..default() },
                    TextLayout::no_wrap(),
                ));
            });
            if !fits {
                card.insert(Disabled);
            }
        }
    }

    fn mags(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let ammo_pts = d.gear(self.data).ammo;
        p.spawn(Node {
            height: px(16),
            justify_content: JustifyContent::SpaceBetween,
            align_items: AlignItems::Baseline,
            ..default()
        })
        .with_children(|l| {
            l.spawn(f.role(TextRole::Lbl, "MAGAZINES · LOAD ORDER"));
            l.spawn((
                Node { align_items: AlignItems::Baseline, ..default() },
                children![
                    f.role(TextRole::Micro, "SLOT = RELOAD WHEEL POSITION · AMMO\u{a0}"),
                    f.role_color(
                        TextRole::Micro,
                        format!("{ammo_pts} PTS"),
                        if ammo_pts > 0 { TEXT_HI } else { TEXT_LOW }
                    ),
                ],
            ));
        });
        p.spawn(Node { height: px(76), margin: UiRect::top(px(8)), column_gap: px(6), ..default() }).with_children(
            |row| {
                for i in 0..MAX_MAGS {
                    self.mag_card(row, i, true);
                }
            },
        );
    }

    /// One magazine card (`live` = clickable; the drag ghost is a copy).
    fn mag_card(&self, row: &mut ChildSpawnerCommands, i: usize, live: bool) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let len = d.mags.len();
        let on = live && self.st.pop == Some(Pop::Mag(i));
        let drag = self.st.drag.filter(|g| g.active);
        let target = live && drag.is_some_and(|g| g.over == Some(i) && g.from != i);
        let flashing = live && self.st.flash.get(i).is_some_and(|t| *t > 0.0);
        let mut node = card_node();
        if !live {
            node.width = px(140.33);
            node.flex_grow = 0.0;
            node.flex_basis = Val::Auto;
        }
        if i < len {
            let ammo = d.mags[i];
            if target {
                node.border = UiRect::all(px(2));
                node.padding = UiRect::axes(px(9), px(8));
            }
            let border = if target {
                TEAL
            } else if flashing {
                WARN
            } else if on {
                TEAL
            } else {
                STROKE_MID
            };
            let mut card = row.spawn((
                node,
                BackgroundColor(if on { CARD.on.bg } else { CARD.idle.bg }),
                BorderColor::all(border),
            ));
            if live {
                let mut looks = CARD;
                if flashing || target {
                    looks.idle.border = border;
                    looks.hover.border = border;
                    looks.on.border = border;
                }
                card.insert((Button, Act::Mag(i), Focusable, RelativeCursorPosition::default(), looks, Active(on)));
            } else {
                // The dragged copy: an opaque card over the strip, so it stays readable (Bevy has no group
                // opacity; the CSS card's .03 fill would let the card under it show through).
                card.insert((
                    BackgroundColor(POPOVER_SURFACE),
                    BorderColor::all(STROKE_HI),
                    BoxShadow(vec![ShadowStyle {
                        color: K50,
                        x_offset: px(0),
                        y_offset: px(8),
                        spread_radius: px(0),
                        blur_radius: px(12),
                    }]),
                ));
            }
            card.with_children(|c| {
                c.spawn(Node { column_gap: px(6), align_items: AlignItems::Center, ..default() }).with_children(|h| {
                    wheel_glyph(h, self.images, i, if on { TEAL } else { TEXT_HI });
                    h.spawn((
                        f.role_color(TextRole::TableHead, format!("MAG {}", i + 1), if on { TEAL } else { TEXT_MID }),
                        Ink,
                    ));
                    if i == 0 {
                        h.spawn((
                            Node { margin: UiRect::left(Val::Auto), ..default() },
                            children![tag(f, "IN GUN", TEXT_HI, true)],
                        ));
                    }
                });
                c.spawn(Node {
                    margin: UiRect::top(px(6)),
                    height: px(18),
                    column_gap: px(6),
                    align_items: AlignItems::Center,
                    ..default()
                })
                .with_children(|v| {
                    v.spawn((
                        f.role_color(TextRole::SlotValue, text::ammo_name(self.data, ammo), ammo_color(ammo.kind)),
                        TextLayout::no_wrap(),
                    ));
                    if ammo.kind != AmmoKind::Standard {
                        let tiers = self.data.ammo.types.get(&ammo.kind).map_or(1, |t| t.tiers.len() as u8);
                        v.spawn(ammo_pips(self.images, ammo.kind, ammo.tier, tiers));
                    }
                    let cost = self.data.ammo_for(d.spec(self.data), ammo).map_or(0, |a| a.gear_cost);
                    if cost > 0 {
                        v.spawn((
                            f.role_color(TextRole::Micro, format!("{cost} PTS"), TEXT_MID),
                            Node { margin: UiRect::left(Val::Auto), ..default() },
                        ));
                    }
                });
                c.spawn((
                    f.role_color(TextRole::Micro, text::ammo_effect(self.data, ammo), TEXT_MID),
                    Node { margin: UiRect::top(px(4)), ..default() },
                ));
            });
        } else {
            // Empty: dashed. Only the first empty slot can add a magazine (no gaps).
            let add = d.add_slot() == Some(i);
            let mut card = row.spawn((
                node,
                BackgroundColor(Color::NONE),
                BorderColor::all(Color::NONE),
                dashed(self.images, STROKE_MID),
            ));
            if add && live {
                card.insert((
                    Button,
                    Act::Mag(i),
                    Focusable,
                    RelativeCursorPosition::default(),
                    Looks::new(
                        Look::new(Color::NONE, Color::NONE, TEXT_LOW),
                        Look::new(W06, Color::NONE, TEXT_LOW),
                        Look::new(hexa(0x00DACE, 0.08), Color::NONE, TEAL),
                    ),
                    Active(on),
                ));
            }
            card.with_children(|c| {
                c.spawn(Node { column_gap: px(6), align_items: AlignItems::Center, ..default() }).with_children(|h| {
                    wheel_glyph(h, self.images, i, if on { TEAL } else { W18 });
                    h.spawn((
                        f.role_color(TextRole::TableHead, format!("MAG {}", i + 1), if on { TEAL } else { TEXT_LOW }),
                        Ink,
                    ));
                });
                if add {
                    c.spawn((
                        f.text("+ ADD MAG", Face::Display, 700, 17.0, TEXT_LOW, 0.04),
                        Node { margin: UiRect::top(px(6)), ..default() },
                    ));
                }
            });
        }
    }

    fn ghost(&self, p: &mut ChildSpawnerCommands) {
        let Some(drag) = self.st.drag.filter(|g| g.active) else { return };
        p.spawn((Ghost, Node { position_type: PositionType::Absolute, ..default() }))
            .with_children(|g| self.mag_card(g, drag.from, false));
    }

    fn stats(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let spec = d.spec(self.data);
        let equipped = d.equipped_all(self.data);
        let current = weapon_stats(self.data, spec, &equipped);
        // Deltas: a hovered list row against the equipped part; with a slot open, the equipped part against
        // NONE or the default; otherwise none.
        let (base, new): (WeaponStats, WeaponStats) =
            match (self.st.pop, preview_part(d, self.st.pop, self.hover_row(), self.data, self.ui)) {
                (_, Some((cat, part))) => {
                    (current.clone(), weapon_stats(self.data, spec, &parts_with(&equipped, cat, part)))
                }
                (Some(Pop::Slot(cat)), None) => {
                    let base_part = if self.data.attachments.is_optional(cat) {
                        None
                    } else {
                        super::model::default_part(self.data, &d.weapon, cat)
                    };
                    (weapon_stats(self.data, spec, &parts_with(&equipped, cat, base_part)), current)
                }
                _ => (current.clone(), current),
            };
        let bars = &self.ui.ui.stat_bars;
        let range = |row: usize| match row {
            0 => bars.ads_s,
            1 => bars.rpm,
            2 | 3 => bars.recoil,
            4 => bars.mobility,
            5 => bars.reload_s,
            6 => bars.range_m,
            _ => bars.mag,
        };
        p.spawn(panel(Node {
            width: percent(100),
            padding: UiRect::axes(px(16), px(14)),
            display: Display::Grid,
            grid_template_columns: RepeatedGridTrack::flex(2, 1.0),
            column_gap: px(28),
            row_gap: px(9),
            ..default()
        }))
        .with_children(|g| {
            for (row, key) in text::STAT_KEYS.iter().enumerate() {
                let fb = bar_frac(text::stat_number(row, &base), range(row));
                let fnew = bar_frac(text::stat_number(row, &new), range(row));
                let delta = text::stat_inline_delta(row, &base, &new);
                g.spawn(Node {
                    display: Display::Grid,
                    grid_template_columns: vec![
                        RepeatedGridTrack::px(1, 96.0),
                        RepeatedGridTrack::flex(1, 1.0),
                        RepeatedGridTrack::px(1, 64.0),
                    ],
                    column_gap: px(10),
                    align_items: AlignItems::Center,
                    ..default()
                })
                .with_children(|r| {
                    r.spawn(f.role(TextRole::StatKey, *key));
                    r.spawn((Node { height: px(6), ..default() }, BackgroundColor(W10))).with_children(|b| {
                        let lo = fb.min(fnew);
                        b.spawn((
                            Node {
                                position_type: PositionType::Absolute,
                                left: px(0),
                                top: px(0),
                                bottom: px(0),
                                width: percent(lo * 100.0),
                                ..default()
                            },
                            BackgroundColor(TEXT_HI),
                        ));
                        if (fnew - fb).abs() > 1e-4 {
                            b.spawn((
                                Node {
                                    position_type: PositionType::Absolute,
                                    left: percent(lo * 100.0),
                                    top: px(0),
                                    bottom: px(0),
                                    width: percent((fnew - fb).abs() * 100.0),
                                    ..default()
                                },
                                BackgroundColor(if fnew > fb { GOOD } else { BAD }),
                            ));
                        }
                    });
                    let value_font = f.role_font(TextRole::Num).with_font(f.handle(Face::Display, 700));
                    r.spawn((
                        Text::new(text::stat_value(row, &new)),
                        value_font.clone(),
                        TextColor(TEXT_HI),
                        TextLayout::justify(Justify::Right),
                        Node { width: px(64), justify_content: JustifyContent::End, ..default() },
                    ))
                    .with_children(|t| {
                        if let Some((txt, tone)) = delta {
                            t.spawn((
                                TextSpan::new(format!(" {txt}")),
                                value_font.clone(),
                                TextColor(match tone {
                                    Tone::Good => GOOD,
                                    Tone::Bad => BAD,
                                    Tone::Neutral => TEXT_MID,
                                }),
                            ));
                        }
                    });
                });
            }
        });
    }

    fn halo_column(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let caps = self.data.armor.loadout_tier_caps;
        let halo = d.halo;
        let armor = self.data.armor.resolve_halo(&halo);
        let top_tier = halo.tier_range().map_or(2, |(_, hi)| hi);
        let accent = tier_color(top_tier);
        // header
        p.spawn(col_header(f, "HALO ARMOR", "ANY AGENT CAN WEAR IT", TextRole::H2, 10.0));
        // cores
        p.spawn(Node { column_gap: px(6), ..default() }).with_children(|row| {
            for core in [Core::Bulwark, Core::Mender, Core::Volt, Core::Phase] {
                let on = core == halo.core;
                let looks = Looks::new(
                    Look::new(W03, white_on(0.16, 0.03), TEXT_MID),
                    Look::new(W03, white_on(0.32, 0.03), TEXT_MID),
                    Look::new(translucent(accent, 0.08), accent, TEXT_HI),
                );
                row.spawn((
                    Button,
                    Act::Core(core),
                    Focusable,
                    Node {
                        flex_grow: 1.0,
                        flex_basis: px(0),
                        height: px(128),
                        flex_direction: FlexDirection::Column,
                        align_items: AlignItems::Center,
                        justify_content: JustifyContent::Center,
                        row_gap: px(2),
                        border: UiRect::all(px(1)),
                        ..default()
                    },
                    BackgroundColor(if on { looks.on.bg } else { looks.idle.bg }),
                    BorderColor::all(if on { looks.on.border } else { looks.idle.border }),
                    looks,
                    Active(on),
                ))
                .with_children(|c| {
                    let look = HaloLook {
                        core,
                        tiers: vetf_sim::ZoneTable::splat(top_tier),
                        colors: vetf_sim::ZoneTable::splat(accent),
                        weight: WeightClass::Light,
                        cells: 1,
                        accent,
                        centre: Centre::Nothing,
                        letters: true,
                        selected: None,
                    };
                    spawn_halo(c, self.halo, f, &look, 62.0);
                    c.spawn((f.role(TextRole::CoreName, core.label()), Ink));
                    let blurb = self.data.armor.core_blurbs.get(&core).cloned().unwrap_or_default();
                    c.spawn((
                        f.role(TextRole::CoreDesc, blurb),
                        TextLayout::justify(Justify::Center),
                        Node { padding: UiRect::horizontal(px(6)), ..default() },
                    ));
                });
            }
        });
        // tier row
        let arc = self.st.arc;
        let arc_cap = caps[arc];
        let cap_note = if arc_cap < 4 {
            format!("{} CAP T{arc_cap} · HIGHER IS RARE LOOT", arc.label())
        } else {
            "SHIFT+CLICK: ALL ARCS".to_string()
        };
        p.spawn((
            Node { margin: UiRect::top(px(14)), ..col_header_node(0.0) },
            children![f.role(TextRole::Lbl, format!("TIER · {}", arc.label())), f.role(TextRole::Micro, cap_note)],
        ));
        p.spawn(Node { margin: UiRect::top(px(8)), column_gap: px(6), ..default() }).with_children(|row| {
            for t in 1..=4u8 {
                let c = tier_color(t);
                let on = halo.tiers[arc] == t;
                let looks = tier_looks(c);
                let mut b = row.spawn((
                    Button,
                    Act::Tier(t),
                    Focusable,
                    Node {
                        flex_grow: 1.0,
                        flex_basis: px(0),
                        height: px(46),
                        column_gap: px(8),
                        align_items: AlignItems::Center,
                        justify_content: JustifyContent::Center,
                        border: UiRect::all(px(if on { 2.0 } else { 1.0 })),
                        ..default()
                    },
                    BackgroundColor(if on { looks.on.bg } else { Color::NONE }),
                    BorderColor::all(if on { c } else { STROKE_MID }),
                    looks,
                    Active(on),
                ));
                b.with_children(|b| {
                    b.spawn((
                        Node { width: px(14), height: px(14), ..default() },
                        BackgroundColor(c),
                        UiTransform::from_rotation(Rot2::degrees(45.0)),
                        BoxShadow(vec![ShadowStyle {
                            color: translucent(c, 0.55),
                            x_offset: px(0),
                            y_offset: px(0),
                            spread_radius: px(0),
                            blur_radius: px(5),
                        }]),
                    ));
                    b.spawn(f.role_color(TextRole::TierBox, format!("T{t}"), c));
                });
                if t > arc_cap {
                    b.insert(Disabled);
                }
            }
        });
        // coverage
        p.spawn((f.role(TextRole::Lbl, "COVERAGE · CLICK A ZONE"), Node { margin: UiRect::top(px(14)), ..default() }));
        p.spawn(Node {
            margin: UiRect::top(px(8)),
            display: Display::Grid,
            grid_template_columns: vec![RepeatedGridTrack::px(1, 150.0), RepeatedGridTrack::flex(1, 1.0)],
            column_gap: px(16),
            align_items: AlignItems::Center,
            ..default()
        })
        .with_children(|cov| {
            cov.spawn(Node { justify_content: JustifyContent::Center, ..default() }).with_children(|w| {
                let (sub, sub_tier) = match halo.tier_range() {
                    Some((lo, hi)) if lo == hi => (format!("T{hi} {}", halo.core.label()), hi),
                    Some((_, hi)) => (halo.core.label().to_string(), hi),
                    None => ("NO HALO".into(), 0),
                };
                let look = HaloLook {
                    core: halo.core,
                    tiers: halo.tiers,
                    colors: halo.tiers.map(|_, t| tier_color(*t)),
                    weight: armor.weight_class,
                    cells: armor.power_cells,
                    accent,
                    centre: Centre::Value {
                        value: armor.capacity.round() as u32,
                        sub,
                        sub_color: if sub_tier == 0 { TEXT_LOW } else { tier_color(sub_tier) },
                    },
                    letters: false,
                    selected: Some(arc),
                };
                spawn_halo(w, self.halo, f, &look, 140.0);
            });
            cov.spawn(Node {
                display: Display::Grid,
                grid_template_columns: RepeatedGridTrack::flex(2, 1.0),
                column_gap: px(6),
                row_gap: px(6),
                ..default()
            })
            .with_children(|tiles| {
                for z in Zone::ALL {
                    let t = halo.tiers[z];
                    let c = tier_color(t);
                    let covered = t > 0;
                    let selected = z == arc;
                    tiles
                        .spawn((
                            Button,
                            Act::Zone(z),
                            Focusable,
                            Node {
                                height: px(46),
                                padding: UiRect::horizontal(px(12)),
                                column_gap: px(10),
                                align_items: AlignItems::Center,
                                border: UiRect::all(px(1)),
                                ..default()
                            },
                            BackgroundColor(if covered { translucent(c, 0.08) } else { Color::NONE }),
                            BorderColor::all(if covered { translucent(c, 0.6) } else { STROKE_MID }),
                            Looks::new(
                                Look::new(
                                    if covered { translucent(c, 0.08) } else { Color::NONE },
                                    if covered { translucent(c, 0.6) } else { STROKE_MID },
                                    TEXT_HI,
                                ),
                                Look::new(
                                    if covered { translucent(c, 0.08) } else { W06 },
                                    if covered { STROKE_HI } else { white_on(0.32, 0.06) },
                                    TEXT_HI,
                                ),
                                Look::new(translucent(c, 0.08), c, TEXT_HI),
                            ),
                            Outline::new(px(if selected { 2.0 } else { 0.0 }), px(0), TEAL),
                        ))
                        .with_children(|tile| {
                            tile.spawn(icon(
                                self.images,
                                Icon::zone(z),
                                18.0,
                                if covered { TEXT_HI } else { TEXT_MID },
                            ));
                            tile.spawn(f.role_color(
                                TextRole::Chip,
                                z.label(),
                                if covered { TEXT_HI } else { TEXT_MID },
                            ));
                            if covered {
                                tile.spawn((
                                    f.role_color(TextRole::TierText, format!("T{t}"), c),
                                    Node { margin: UiRect::left(Val::Auto), ..default() },
                                ));
                            }
                            tile.spawn((
                                Button,
                                Act::ZoneCheck(z),
                                Node {
                                    width: px(18),
                                    height: px(18),
                                    flex_shrink: 0.0,
                                    margin: UiRect::left(if covered { px(0) } else { Val::Auto }),
                                    border: UiRect::all(px(2)),
                                    ..default()
                                },
                                BackgroundColor(if covered { c } else { Color::NONE }),
                                BorderColor::all(if covered { c } else { STROKE_HI }),
                            ));
                        });
                }
            });
        });
        self.result(p, &halo, &armor);
        // what others see
        let see = text::what_others_see(self.ui, &halo, &armor);
        p.spawn(panel(Node {
            margin: UiRect::top(px(12)),
            padding: UiRect::axes(px(18), px(14)),
            flex_direction: FlexDirection::Column,
            ..default()
        }))
        .with_children(|w| {
            w.spawn(col_header(f, "WHAT OTHERS SEE", "READABILITY LAYERS", TextRole::H2Small, 6.0));
            w.spawn(Node { flex_direction: FlexDirection::Column, row_gap: px(7), ..default() }).with_children(|g| {
                for (k, line) in ["ALWAYS", "ON HIT", "ON SCAN"].iter().zip(see) {
                    // One 16 px line per row (fixed, so text measuring cannot stretch it); the 12 px label sits
                    // 1 px lower so it shares the 13 px line's baseline.
                    g.spawn((
                        Node { height: px(16), ..default() },
                        children![
                            (
                                f.text(*k, Face::Display, 600, 12.0, TEXT_MID, 0.14),
                                Node { width: px(86), flex_shrink: 0.0, margin: UiRect::top(px(1)), ..default() },
                            ),
                            (f.text(line, Face::Body, 400, 13.0, TEXT, 0.0), TextLayout::no_wrap()),
                        ],
                    ));
                }
            });
        });
    }

    pub(super) fn result(
        &self,
        p: &mut ChildSpawnerCommands,
        halo: &vetf_sim::gear::HaloChoice,
        armor: &vetf_sim::data::ArmorStats,
    ) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let gear = d.gear(self.data);
        p.spawn(panel_of(
            PanelKind::Result,
            Node {
                margin: UiRect::top(px(14)),
                padding: UiRect::axes(px(18), px(16)),
                flex_direction: FlexDirection::Column,
                ..default()
            },
        ))
        .with_children(|r| {
            // The deathmatch layout names the armor tier: `T3 · H3 T3 A1 L1`.
            let header = match d.armor_tier() {
                Some(t) => format!("{} · {}", text::armor_pick(t), text::armor_pick_arcs(&halo.tiers)),
                None => text::result_header(halo),
            };
            r.spawn(col_header(f, "RESULT", &header, TextRole::H2Small, 0.0));
            r.spawn(Node { margin: UiRect::top(px(8)), column_gap: px(4), ..default() }).with_children(|w| {
                for (wc, label) in text::weight_band_labels(self.data) {
                    let on = wc == armor.weight_class;
                    w.spawn((
                        Node {
                            flex_grow: 1.0,
                            flex_basis: px(0),
                            height: px(36),
                            align_items: AlignItems::Center,
                            justify_content: JustifyContent::Center,
                            ..default()
                        },
                        BackgroundColor(if on { TEXT_HI } else { W05 }),
                        children![f.role_color(TextRole::Wclass, label, if on { BG0 } else { TEXT_LOW })],
                    ));
                }
            });
            // figures
            let fx = self.data.armor.effects(armor.weight_class);
            let sprint = self.data.movement.speed.sprint;
            let (shield_sub, move_pct) = match armor.regen() {
                Some(rg) => (format!("regen {}/s after {} s", rg.rate_per_s, rg.delay_s), (fx.move_mult - 1.0) * 100.0),
                None => ("no shield".to_string(), (fx.move_mult - 1.0) * 100.0),
            };
            let drain = if fx.energy_per_min > 0.0 {
                format!("energy {}{:.1}/min", text::MINUS, fx.energy_per_min)
            } else {
                "no power drain".to_string()
            };
            let figures = [
                ("SHIELD", format!("{}", armor.capacity.round()), "", shield_sub),
                (
                    "MOVE SPEED",
                    format!("{} %", text::signed(move_pct, 0)),
                    "",
                    format!("sprint {:.1} m/s (base {sprint:.1})", sprint * fx.move_mult),
                ),
                (
                    "POWER DRAIN",
                    format!("{}", armor.power_cells),
                    if armor.power_cells == 1 { "cell" } else { "cells" },
                    drain,
                ),
            ];
            r.spawn(Node {
                margin: UiRect::top(px(14)),
                display: Display::Grid,
                grid_template_columns: RepeatedGridTrack::flex(3, 1.0),
                column_gap: px(10),
                ..default()
            })
            .with_children(|g| {
                for (k, value, unit, sub) in figures {
                    g.spawn(Node { flex_direction: FlexDirection::Column, ..default() }).with_children(|c| {
                        c.spawn(f.role(TextRole::Lbl, k));
                        c.spawn(Node { align_items: AlignItems::Baseline, column_gap: px(4), ..default() })
                            .with_children(|v| {
                                v.spawn(f.role(TextRole::ValueL, value));
                                if !unit.is_empty() {
                                    v.spawn(f.text(unit, Face::Display, 600, 14.0, TEXT_MID, 0.0));
                                }
                            });
                        c.spawn(f.role(TextRole::Sub, sub));
                    });
                }
            });
            // The points (the gun range: the gear it would cost, with no limit): a bar in parts, used / total.
            let used = gear.total();
            let over = self.ctx.budget.is_some_and(|b| used > b);
            let simple = self.ctx.simple();
            let parts: Vec<(&str, u32, f32)> = if simple {
                let mut v = vec![("ARMOR", gear.halo, 1.0), ("AMMO (ONCE)", gear.ammo, 0.55), ("MAG", gear.mags, 0.3)];
                // Only a priced optic (the variable 1-3x) shows its part of the points.
                if gear.optic > 0 {
                    v.push(("OPTIC", gear.optic, 0.75));
                }
                v
            } else {
                vec![("HALO", gear.halo, 1.0), ("AMMO", gear.ammo, 0.55)]
            };
            r.spawn(Node {
                margin: UiRect::top(px(14)),
                column_gap: px(10),
                align_items: AlignItems::Center,
                ..default()
            })
            .with_children(|b| {
                b.spawn(f.role(TextRole::Lbl, if simple { "POINTS" } else { "GEAR BUDGET" }));
                match self.ctx.budget {
                    Some(budget) => {
                        let scale = budget.max(used).max(1) as f32;
                        let fill = if over { BAD } else { TEXT_HI };
                        b.spawn((
                            Node { flex_grow: 1.0, height: px(8), column_gap: px(2), ..default() },
                            BackgroundColor(W10),
                        ))
                        .with_children(|bar| {
                            for (_, pts, alpha) in parts.iter().filter(|p| p.1 > 0) {
                                bar.spawn((
                                    Node {
                                        width: percent(*pts as f32 / scale * 100.0),
                                        height: percent(100),
                                        ..default()
                                    },
                                    BackgroundColor(translucent(fill, *alpha)),
                                ));
                            }
                        });
                        b.spawn(f.text(
                            format!("{used} / {budget}"),
                            Face::Display,
                            700,
                            16.0,
                            if over { BAD } else { TEXT_HI },
                            0.0,
                        ));
                    }
                    None => {
                        b.spawn(spacer());
                        b.spawn(f.text("NO LIMIT", Face::Display, 700, 16.0, TEXT_MID, 0.0));
                    }
                }
                b.spawn(f.role(TextRole::Micro, self.ctx.note));
            });
            // legend
            r.spawn(Node {
                margin: UiRect::top(px(6)),
                column_gap: px(14),
                align_items: AlignItems::Center,
                ..default()
            })
            .with_children(|l| match self.ctx.budget {
                Some(budget) if over => {
                    let fix =
                        if simple { "THE ARMOR, THE AMMO OR THE MAGAZINE" } else { "AN ARC TIER OR A MAG'S AMMO" };
                    l.spawn(f.role_color(TextRole::Micro, format!("OVER BY {} PTS: LOWER {fix}", used - budget), BAD));
                }
                _ => {
                    for (label, pts, alpha) in &parts {
                        l.spawn((
                            Node { column_gap: px(6), align_items: AlignItems::Center, ..default() },
                            children![
                                (
                                    Node { width: px(8), height: px(8), ..default() },
                                    BackgroundColor(translucent(TEXT_HI, *alpha))
                                ),
                                f.role(TextRole::Micro, format!("{label} {}", text::pts(*pts))),
                            ],
                        ));
                    }
                }
            });
        });
    }
}

// ---------------------------------------------------------------------------------------------- helpers

/// A pick's points: red when picking it would go over the total, a muted FREE, else the card's ink.
pub(super) fn price_color(pts: u32, over: bool) -> Color {
    if over {
        BAD
    } else if pts == 0 {
        TEXT_LOW
    } else {
        TEXT_MID
    }
}

fn chip_node() -> Node {
    Node {
        height: px(38),
        padding: UiRect::horizontal(px(14)),
        align_items: AlignItems::Center,
        border: UiRect::all(px(1)),
        ..default()
    }
}

fn card_node() -> Node {
    Node {
        flex_grow: 1.0,
        flex_basis: px(0),
        height: px(76),
        padding: UiRect::axes(px(10), px(9)),
        border: UiRect::all(px(1)),
        flex_direction: FlexDirection::Column,
        overflow: Overflow::clip(),
        ..default()
    }
}

pub(super) fn col_header_node(margin_bottom: f32) -> Node {
    Node {
        justify_content: JustifyContent::SpaceBetween,
        align_items: AlignItems::Baseline,
        margin: UiRect::bottom(px(margin_bottom)),
        ..default()
    }
}

/// A column header: a heading on the left, a micro label on the right.
pub(super) fn col_header(f: &UiFonts, title: &str, micro: &str, role: TextRole, margin_bottom: f32) -> impl Bundle {
    (col_header_node(margin_bottom), children![f.role(role, title), f.role(TextRole::Micro, micro)])
}

/// The reload-wheel glyph: six sectors, this slot's lit (slot 1 at the top, clockwise).
fn wheel_glyph(p: &mut ChildSpawnerCommands, images: &UiImages, slot: usize, lit: Color) {
    p.spawn(Node { width: px(16), height: px(16), flex_shrink: 0.0, ..default() }).with_children(|w| {
        let full = || Node {
            position_type: PositionType::Absolute,
            left: px(0),
            top: px(0),
            width: px(16),
            height: px(16),
            ..default()
        };
        w.spawn((ImageNode::new(images.shape(Shape::WheelRing)).with_color(W18), full()));
        w.spawn((
            ImageNode::new(images.shape(Shape::WheelSector)).with_color(lit),
            full(),
            UiTransform::from_rotation(Rot2::degrees(slot as f32 * 60.0)),
        ));
    });
}

fn silhouette(weapon: &str) -> Option<Icon> {
    match weapon {
        "ar7_mako" => Some(Icon::Mako),
        "vk50_warden" => Some(Icon::Warden),
        // No SK-9 Skink silhouette yet (art request): its tab is text-only.
        _ => None,
    }
}

fn icon_by_name(name: &str) -> Icon {
    Icon::ALL.iter().copied().find(|i| i.file() == name).unwrap_or(Icon::Mako)
}

fn ability_icon(name: &str) -> Icon {
    icon_by_name(name)
}
