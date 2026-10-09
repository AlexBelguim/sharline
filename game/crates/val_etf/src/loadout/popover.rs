//! The attachment list popover (mockup 05b) and the ammo picker that reuses it for a magazine card: every
//! part that fits the slot (or every round the gun loads) with a blurb and, for ammo, its two biggest effects
//! and its gear cost against the budget.
//!
//! A part's row shows what the part does ON ITS OWN, against no part in that slot (user, item B): every stat
//! it changes (good first, green / red), its zoom and its other effects as tags (with what is not in the game
//! yet saying so), and under that a quieter "vs equipped" line with what changes if you swap to it. The panel
//! is opaque, so the cards under it never show through; a long list spreads over two or three columns.

use super::model::{Draft, WeaponStats, parts_for, parts_with, pushes_over, weapon_stats};
use super::text::{self, Delta, Tag, Tone};
use super::ui_data::LoadoutUiData;
use super::view::View;
use super::{Act, Pop, PopPanel};
use crate::ui_kit::*;
use bevy::prelude::*;
use bevy::ui::{FocusPolicy, RelativeCursorPosition};
use vetf_sim::GameData;
use vetf_sim::data::{AmmoChoice, AmmoKind, AttachmentCategory, AttachmentSpec};

/// What a row picks.
#[derive(Debug, Clone, PartialEq)]
pub enum RowKind {
    /// A part, or NONE for an optional slot.
    Part(Option<String>),
    Ammo(AmmoChoice),
    /// Remove this (last) magazine.
    NoMag,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Row {
    pub kind: RowKind,
    pub equipped: bool,
}

/// The rows of a popover, top to bottom.
pub fn rows(draft: &Draft, pop: Pop, data: &GameData, _ui: &LoadoutUiData) -> Vec<Row> {
    match pop {
        Pop::Slot(cat) => {
            let equipped = draft.equipped(cat, data).map(|a| a.id.clone());
            let mut v = Vec::new();
            if data.attachments.is_optional(cat) {
                v.push(Row { kind: RowKind::Part(None), equipped: equipped.is_none() });
            }
            for a in parts_for(data, &draft.weapon, cat) {
                v.push(Row { kind: RowKind::Part(Some(a.id.clone())), equipped: equipped.as_deref() == Some(&a.id) });
            }
            v
        }
        Pop::Mag(i) => {
            let current = draft.mags.get(i).copied();
            let mut v = Vec::new();
            if i > 0 && i + 1 == draft.mags.len() {
                v.push(Row { kind: RowKind::NoMag, equipped: false });
            }
            for c in draft.ammo_options(data) {
                v.push(Row { kind: RowKind::Ammo(c), equipped: current == Some(c) });
            }
            v
        }
    }
}

/// Apply row `r` of a popover.
pub fn pick(draft: &mut Draft, pop: Pop, r: usize, data: &GameData, ui: &LoadoutUiData) {
    let Some(row) = rows(draft, pop, data, ui).into_iter().nth(r) else { return };
    match (pop, row.kind) {
        (Pop::Slot(cat), RowKind::Part(p)) => draft.set_part(cat, p.as_deref(), data),
        (Pop::Mag(i), RowKind::Ammo(c)) => {
            draft.set_mag(i, c);
        }
        (Pop::Mag(_), RowKind::NoMag) => {
            draft.remove_last_mag();
        }
        _ => {}
    }
}

/// The part a hovered (or arrow-key) attachment row would put in its slot, for the stats and hotspot
/// preview: `Some((slot, part))`, part `None` = NONE.
pub fn preview_part<'a>(
    draft: &Draft,
    pop: Option<Pop>,
    row: Option<usize>,
    data: &'a GameData,
    ui: &LoadoutUiData,
) -> Option<(AttachmentCategory, Option<&'a AttachmentSpec>)> {
    let (Some(Pop::Slot(cat)), Some(r)) = (pop, row) else { return None };
    match rows(draft, Pop::Slot(cat), data, ui).into_iter().nth(r)?.kind {
        RowKind::Part(p) => Some((cat, p.and_then(|id| data.attachment(&id)))),
        _ => None,
    }
}

/// Stats of the current gun with one slot replaced.
fn stats_with(v: &View, cat: AttachmentCategory, part: Option<&AttachmentSpec>) -> WeaponStats {
    let draft = &v.edit.draft;
    let parts = parts_with(&draft.equipped_all(v.data), cat, part);
    weapon_stats(v.data, draft.spec(v.data), &parts)
}

/// Rows above six use compact padding (the SMG's ammo picker has eight).
const COMPACT_ABOVE: usize = 6;

/// One column of part rows, and the gap between columns.
const PART_COL_W: f32 = 440.0;
const COL_GAP: f32 = 8.0;
/// The ammo picker's width (one column).
const AMMO_W: f32 = 420.0;

/// Columns of a part list: up to three rows in one, up to six in two, more in three (the Warden's seven
/// optics), so the list never grows past the top of the screen. The ammo picker stays one column.
pub fn columns(pop: Pop, rows: usize) -> usize {
    match pop {
        Pop::Slot(_) => rows.div_ceil(3).clamp(1, 3),
        Pop::Mag(_) => 1,
    }
}

/// The panel's outer width for `cols` columns (12 px padding and a 1 px border each side).
pub fn panel_width(pop: Pop, cols: usize) -> f32 {
    let inner = match pop {
        Pop::Slot(_) => cols as f32 * PART_COL_W + (cols.saturating_sub(1)) as f32 * COL_GAP,
        Pop::Mag(_) => AMMO_W - 26.0,
    };
    inner + 26.0
}

/// Build the popover panel (absolute; anchored so its bottom edge sits 1 px over the row that opened it).
pub fn build(v: &View, p: &mut ChildSpawnerCommands) {
    let Some(pop) = v.st.pop else { return };
    let draft = &v.edit.draft;
    let rows = rows(draft, pop, v.data, v.ui);
    let compact = rows.len() > COMPACT_ABOVE;
    // Page y of the bottom edge: 621 over the attachment slots, 731 over the magazines.
    let bottom_edge = match pop {
        Pop::Slot(_) => 621.0,
        Pop::Mag(_) => 731.0,
    };
    let (title, micro) = match (pop, &draft.fixed) {
        // Team deathmatch and free-for-all: the magazine type picked here is the one carried, six of it.
        (Pop::Slot(AttachmentCategory::Mag), Some(kit)) => {
            (format!("MAG · {} TYPES", rows.len()), text::mag_carry(kit.mags))
        }
        (Pop::Slot(cat), _) => {
            (format!("{} · {} PARTS", cat.label(), rows.len()), "OWN EFFECT · HOVER = PREVIEW".into())
        }
        (Pop::Mag(i), _) => (format!("MAG {} · AMMO", i + 1), "HOVER = STAT DELTA · COST".into()),
    };
    let f = v.fonts;
    let cols = columns(pop, rows.len());
    let mut panel = p.spawn((
        PopPanel,
        RelativeCursorPosition::default(),
        FocusPolicy::Block,
        panel_of(
            PanelKind::Popover,
            Node {
                position_type: PositionType::Absolute,
                // Over the weapon column, 14 px in.
                left: px(super::view::weapon_left(v.ctx.simple()) + 14.0),
                top: px(bottom_edge),
                width: px(panel_width(pop, cols)),
                padding: UiRect::all(px(12)),
                flex_direction: FlexDirection::Column,
                ..default()
            },
        ),
        // Grow upwards from the anchor.
        UiTransform::from_translation(Val2::percent(0.0, -100.0)),
    ));
    // The kit's popover is opaque (user, item B: the cards under it showed through the old .82 fill).
    panel.with_children(|panel| {
        panel.spawn((
            Node {
                justify_content: JustifyContent::SpaceBetween,
                align_items: AlignItems::Baseline,
                margin: UiRect { left: px(4), right: px(4), top: px(2), bottom: px(6) },
                ..default()
            },
            children![f.role(TextRole::H2Small, title), f.role(TextRole::Micro, micro)],
        ));
        let equipped_stats = match pop {
            Pop::Slot(cat) => Some(stats_with(v, cat, draft.equipped(cat, v.data))),
            Pop::Mag(_) => None,
        };
        // Rows fill the columns top to bottom, then left to right (reading order stays the row order).
        let per_col = rows.len().div_ceil(cols);
        panel.spawn(Node { column_gap: px(COL_GAP), align_items: AlignItems::Start, ..default() }).with_children(
            |grid| {
                for c in 0..cols {
                    grid.spawn(Node {
                        width: px(match pop {
                            Pop::Slot(_) => PART_COL_W,
                            Pop::Mag(_) => AMMO_W - 26.0,
                        }),
                        flex_direction: FlexDirection::Column,
                        ..default()
                    })
                    .with_children(|col| {
                        for (i, row) in rows.iter().enumerate().skip(c * per_col).take(per_col) {
                            spawn_row(v, col, pop, i, row, compact, equipped_stats.as_ref());
                        }
                    });
                }
            },
        );
    });
}

/// What a part row shows: its own effect lines, its tags and the "vs equipped" line (None on the equipped
/// row). `empty` is the gun with the slot empty, `equipped` with the equipped part, `with` with this row's.
pub fn part_copy(
    part: Option<&AttachmentSpec>,
    empty: &WeaponStats,
    equipped: &WeaponStats,
    with: &WeaponStats,
    is_equipped: bool,
) -> (Vec<Delta>, Vec<Tag>, Option<Vec<Delta>>) {
    let lines = text::own_lines(empty, with, part);
    let tags = part.map(text::part_tags).unwrap_or_default();
    let vs = (!is_equipped).then(|| text::stat_lines(equipped, with));
    (lines, tags, vs)
}

fn row_looks(equipped: bool) -> Looks {
    let hover = Look::new(W08, TEXT_HI, TEXT_HI);
    let idle =
        if equipped { Look::new(W04, STROKE_MID, TEXT_HI) } else { Look::new(Color::NONE, Color::NONE, TEXT_HI) };
    Looks::new(idle, hover, hover)
}

fn spawn_row(
    v: &View,
    panel: &mut ChildSpawnerCommands,
    pop: Pop,
    i: usize,
    row: &Row,
    compact: bool,
    equipped_stats: Option<&WeaponStats>,
) {
    let f = v.fonts;
    let draft = &v.edit.draft;
    let looks = row_looks(row.equipped);
    // Icon, name, blurb and deltas of the row.
    let name: String;
    let mut blurb: String;
    let mut deltas: Vec<Delta> = Vec::new();
    let mut tags: Vec<Tag> = Vec::new();
    let mut vs: Option<Vec<Delta>> = None;
    let mut ammo: Option<AmmoChoice> = None;
    let mut icon: Option<(Icon, f32, f32, Color)> = None;
    match &row.kind {
        RowKind::Part(part) => {
            let Pop::Slot(cat) = pop else { return };
            let spec = part.as_deref().and_then(|id| v.data.attachment(id));
            name = text::part_name(spec);
            blurb = match spec {
                Some(a) => a.blurb.clone(),
                None => v.ui.ui.none_blurbs.get(&cat).cloned().unwrap_or_default(),
            };
            if row.equipped && !blurb.is_empty() {
                blurb.insert_str(0, "Equipped. ");
            }
            if let Some(eq) = equipped_stats {
                (deltas, tags, vs) =
                    part_copy(spec, &stats_with(v, cat, None), eq, &stats_with(v, cat, spec), row.equipped);
            }
            icon = spec.map(|a| {
                if a.id == "ugl_launcher" {
                    (Icon::Gl, 34.0, 17.0, TEXT_HI)
                } else {
                    (view_icon(cat), 28.0, 28.0, TEXT_HI)
                }
            });
        }
        RowKind::Ammo(c) => {
            name = text::ammo_name(v.data, *c);
            blurb = v.data.ammo.types.get(&c.kind).map(|t| t.blurb.clone()).unwrap_or_default();
            deltas = text::ammo_deltas(v.data, *c);
            ammo = Some(*c);
            icon = Some((Icon::Mag, 16.0, 28.0, ammo_color(c.kind)));
        }
        RowKind::NoMag => {
            name = "NO MAG".into();
            blurb = v.ui.ui.no_mag_blurb.clone();
        }
    }
    let pad = if compact { 6.0 } else { 10.0 };
    panel
        .spawn((
            Button,
            Act::Row(i),
            Node {
                display: Display::Grid,
                grid_template_columns: vec![
                    RepeatedGridTrack::px(1, 44.0),
                    RepeatedGridTrack::flex(1, 1.0),
                    RepeatedGridTrack::auto(1),
                ],
                column_gap: px(12),
                align_items: AlignItems::Center,
                padding: UiRect::all(px(pad)),
                border: UiRect::all(px(1)),
                margin: UiRect::top(px(4)),
                ..default()
            },
            BackgroundColor(looks.idle.bg),
            BorderColor::all(looks.idle.border),
            looks,
            Active(false),
        ))
        .with_children(|r| {
            // icon box
            r.spawn((
                Node {
                    width: px(44),
                    height: px(44),
                    align_items: AlignItems::Center,
                    justify_content: JustifyContent::Center,
                    ..default()
                },
                BackgroundColor(W05),
            ))
            .with_children(|b| match icon {
                Some((ic, w, h, c)) => {
                    b.spawn((
                        ImageNode::new(v.images.icon(ic)).with_color(c),
                        Node { width: px(w), height: px(h), ..default() },
                    ));
                }
                None => {
                    b.spawn(f.text("—", Face::Display, 700, 17.0, TEXT_LOW, 0.0));
                }
            });
            // name, pips, cost, blurb
            r.spawn(Node { flex_direction: FlexDirection::Column, min_width: px(0), ..default() }).with_children(|c| {
                c.spawn(Node { align_items: AlignItems::Center, column_gap: px(6), ..default() }).with_children(|n| {
                    n.spawn(f.role(TextRole::ListName, name.clone()));
                    if let Some(a) = ammo {
                        let tiers = v.data.ammo.types.get(&a.kind).map_or(1, |t| t.tiers.len() as u8);
                        if a.kind != AmmoKind::Standard {
                            n.spawn(ammo_pips(v.images, a.kind, a.tier, tiers));
                        }
                        let cost = v.data.ammo_for(draft.spec(v.data), a).map_or(0, |s| s.gear_cost);
                        let over = v.over_with_mag(pop, a);
                        if cost > 0 || over {
                            n.spawn(f.role_color(
                                TextRole::Micro,
                                cost_text(cost, over),
                                if over { BAD } else { TEXT_MID },
                            ));
                        }
                    }
                    // Team deathmatch and free-for-all: every part's points (FREE muted; a magazine type has
                    // its price), red when picking it would go over the total.
                    if let (RowKind::Part(id), Pop::Slot(cat)) = (&row.kind, pop)
                        && let Some(pts) = draft.part_points(cat, id.as_deref())
                    {
                        let with = draft.gear_with(v.data, |x| x.set_part(cat, id.as_deref(), v.data));
                        let over = !row.equipped && pushes_over(v.ctx.budget, draft.gear(v.data).total(), with.total());
                        n.spawn((
                            f.role_color(TextRole::Micro, text::points(pts), super::view::price_color(pts, over)),
                            TextLayout::no_wrap(),
                        ));
                    }
                    if row.equipped {
                        n.spawn((
                            ImageNode::new(v.images.icon(Icon::Check)).with_color(TEAL),
                            Node {
                                width: px(14),
                                height: px(14),
                                margin: UiRect { left: px(-2), top: px(2), ..default() },
                                ..default()
                            },
                        ));
                    }
                });
                if !blurb.is_empty() {
                    spawn_blurb(v, c, &blurb);
                }
            });
            // deltas
            r.spawn(Node { flex_direction: FlexDirection::Column, align_items: AlignItems::End, ..default() })
                .with_children(|d| {
                    for delta in &deltas {
                        let color = match delta.tone {
                            Tone::Good => GOOD,
                            Tone::Bad => BAD,
                            Tone::Neutral => TEXT_MID,
                        };
                        d.spawn((
                            f.text_line(
                                delta.text.to_uppercase(),
                                Face::Display,
                                600,
                                13.0,
                                color,
                                0.06,
                                bevy::text::LineHeight::Px(17.0),
                            ),
                            TextLayout::justify(Justify::Right).with_no_wrap(),
                        ));
                    }
                });
            // Tags (zoom, beam, deploy...) and the "vs equipped" line, under the name and the lines.
            let under = || Node {
                grid_column: GridPlacement::start_span(2, 2),
                flex_wrap: FlexWrap::Wrap,
                align_items: AlignItems::Center,
                column_gap: px(5),
                row_gap: px(3),
                margin: UiRect::top(px(5)),
                ..default()
            };
            if !tags.is_empty() {
                r.spawn(under()).with_children(|t| {
                    for tag in &tags {
                        spawn_tag(v, t, tag);
                    }
                });
            }
            if let Some(vs) = &vs {
                r.spawn(under()).with_children(|t| {
                    t.spawn((f.text("VS EQUIPPED", Face::Display, 600, 11.0, TEXT_LOW, 0.1), TextLayout::no_wrap()));
                    if vs.is_empty() {
                        t.spawn((f.text("NO CHANGE", Face::Display, 600, 11.0, TEXT_LOW, 0.06), TextLayout::no_wrap()));
                    }
                    for d in vs {
                        let color = match d.tone {
                            Tone::Good => fade(GOOD, 0.7),
                            Tone::Bad => fade(BAD, 0.7),
                            Tone::Neutral => TEXT_LOW,
                        };
                        t.spawn((f.text(d.text.clone(), Face::Display, 600, 11.0, color, 0.06), TextLayout::no_wrap()));
                    }
                });
            }
        });
}

/// One tag chip: what a part does besides its stats; in the warning colour, saying so, when it is not in the
/// game yet.
fn spawn_tag(v: &View, parent: &mut ChildSpawnerCommands, tag: &Tag) {
    let (label, color, border) = if tag.not_yet {
        (format!("{} · {}", tag.text, text::NOT_YET), WARN, fade(WARN, 0.45))
    } else {
        (tag.text.clone(), TEXT_MID, STROKE_MID)
    };
    parent.spawn((
        Node { padding: UiRect::axes(px(6), px(1)), border: UiRect::all(px(1)), max_width: percent(100), ..default() },
        BorderColor::all(border),
        children![v.fonts.text(label, Face::Display, 600, 11.0, color, 0.06)],
    ));
}

/// A blurb with optional inline key caps (`{G}`); one without wraps.
fn spawn_blurb(v: &View, parent: &mut ChildSpawnerCommands, blurb: &str) {
    let f = v.fonts;
    if !blurb.contains('{') {
        parent.spawn((f.role(TextRole::Desc, blurb), Node { margin: UiRect::top(px(1)), ..default() }));
        return;
    }
    parent
        .spawn(Node { align_items: AlignItems::Center, column_gap: px(4), margin: UiRect::top(px(1)), ..default() })
        .with_children(|b| {
            let mut rest = blurb;
            while let Some(open) = rest.find('{') {
                let Some(close) = rest[open..].find('}').map(|c| open + c) else { break };
                let before = rest[..open].trim_end();
                if !before.is_empty() {
                    b.spawn((f.role(TextRole::Desc, before), TextLayout::no_wrap()));
                }
                b.spawn(keycap(f, &rest[open + 1..close], KeyStyle::Ghost, 16.0));
                rest = rest[close + 1..].trim_start();
            }
            if !rest.is_empty() {
                b.spawn((f.role(TextRole::Desc, rest), TextLayout::no_wrap()));
            }
        });
}

/// The slot glyph of a category (16 px on cards, 28 px in the list).
pub fn view_icon(cat: AttachmentCategory) -> Icon {
    match cat {
        AttachmentCategory::Optic => Icon::Optic,
        AttachmentCategory::Stock => Icon::Stock,
        AttachmentCategory::Mag => Icon::MagSlot,
        AttachmentCategory::Under => Icon::Under,
        AttachmentCategory::Side => Icon::Side,
        AttachmentCategory::Shield => Icon::GunShield,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn draft(d: &GameData) -> Draft {
        let c = vetf_net::LoadoutChoice {
            weapon: "ar7_mako".into(),
            mags: d.rules.default_loadout.mags.clone(),
            attachments: d.rules.default_loadout.attachments.clone(),
            halo: crate::config::halo_from_armor(&d.rules.default_loadout.armor, d),
            agent: "kestrel".into(),
        };
        // The gun range's draft: its magazines have their own ammo.
        Draft::from_choice(&c, &BTreeMap::new(), d, None)
    }

    #[test]
    fn the_under_list_matches_the_mockup() {
        let d = GameData::embedded();
        let ui = LoadoutUiData::embedded();
        let mut dr = draft(&d);
        dr.set_part(AttachmentCategory::Under, Some("grip_angled"), &d);
        let r = rows(&dr, Pop::Slot(AttachmentCategory::Under), &d, &ui);
        let ids: Vec<Option<&str>> = r
            .iter()
            .map(|r| match &r.kind {
                RowKind::Part(p) => p.as_deref(),
                _ => Some("?"),
            })
            .collect();
        assert_eq!(ids, [None, Some("grip_vertical"), Some("grip_angled"), Some("grip_stub"), Some("ugl_launcher")]);
        assert_eq!(r.iter().position(|r| r.equipped), Some(2));
        // the optic list has no NONE row (a required slot)
        assert!(rows(&dr, Pop::Slot(AttachmentCategory::Optic), &d, &ui).iter().all(|r| r.kind != RowKind::Part(None)));
        // picking NONE empties the slot; hovering a row previews it
        assert_eq!(
            preview_part(&dr, Some(Pop::Slot(AttachmentCategory::Under)), Some(4), &d, &ui)
                .map(|(_, p)| p.map(|a| a.id.as_str())),
            Some(Some("ugl_launcher"))
        );
        pick(&mut dr, Pop::Slot(AttachmentCategory::Under), 0, &d, &ui);
        assert!(dr.equipped(AttachmentCategory::Under, &d).is_none());
    }

    #[test]
    fn the_ammo_picker_only_removes_the_last_mag() {
        let d = GameData::embedded();
        let ui = LoadoutUiData::embedded();
        let mut dr = draft(&d);
        let first = rows(&dr, Pop::Mag(0), &d, &ui);
        assert_eq!(first.len(), 4, "STANDARD + AP I-III, no NO MAG on slot 1");
        assert!(first[0].equipped);
        assert!(rows(&dr, Pop::Mag(1), &d, &ui).iter().all(|r| r.kind != RowKind::NoMag), "not the last mag");
        let last = rows(&dr, Pop::Mag(3), &d, &ui);
        assert_eq!(last[0].kind, RowKind::NoMag);
        let add = rows(&dr, Pop::Mag(4), &d, &ui);
        assert!(add.iter().all(|r| !r.equipped && r.kind != RowKind::NoMag), "the + ADD MAG slot");
        pick(&mut dr, Pop::Mag(4), 2, &d, &ui);
        assert_eq!(dr.mags.len(), 5);
        assert_eq!(dr.mags[4], AmmoChoice { kind: AmmoKind::ArmorPiercing, tier: 2 });
        pick(&mut dr, Pop::Mag(4), 0, &d, &ui);
        assert_eq!(dr.mags.len(), 4, "NO MAG removes the last one");
        let d = crate::loadout::tests::data_with_skink();
        dr.switch_weapon("sk9_skink", &d);
        assert_eq!(rows(&dr, Pop::Mag(0), &d, &ui).len(), 7, "the SMG adds RIP I-III (when it is back in)");
    }

    /// Item B: long part lists spread over columns (so the panel never grows off the top of the screen), the
    /// widest still fits the page, and the panel is opaque.
    #[test]
    fn long_lists_spread_over_columns_and_the_panel_is_opaque() {
        let s = Pop::Slot(AttachmentCategory::Optic);
        let cols: Vec<usize> = [2, 3, 4, 5, 6, 7].iter().map(|n| columns(s, *n)).collect();
        assert_eq!(cols, [1, 1, 2, 2, 2, 3]);
        assert_eq!(columns(Pop::Mag(0), 7), 1, "the ammo picker stays one column");
        for simple in [false, true] {
            let right = super::super::view::weapon_left(simple) + 14.0 + panel_width(s, 3);
            assert!(right <= 1920.0 - 16.0, "{right}");
        }
        let (bg, border) = panel_colors(PanelKind::Popover);
        assert_eq!(bg.alpha(), 1.0);
        assert!([border.top, border.right, border.bottom, border.left].iter().all(|c| c.alpha() == 1.0));
        // "remove the hint": nothing shows the gun on the agent from the preview.
        assert!(super::super::view::PREVIEW_HINTS.iter().all(|(k, l)| *k != "F" && !l.contains("AGENT")));
    }

    /// Item B, the Warden's lists checked like the Mako's: every row has its own lines, the equipped one no
    /// "vs equipped" line, the others one; the seven optics take three columns; the bipod and thermal say what
    /// they do and what is not in yet.
    #[test]
    fn the_warden_popovers_show_every_effect() {
        let d = GameData::embedded();
        let ui = LoadoutUiData::embedded();
        let mut dr = draft(&d);
        dr.switch_weapon("vk50_warden", &d);
        let spec = dr.spec(&d);
        let stats =
            |cat, part: Option<&AttachmentSpec>| weapon_stats(&d, spec, &parts_with(&dr.equipped_all(&d), cat, part));
        let mut shown = 0;
        for cat in AttachmentCategory::ALL {
            if parts_for(&d, &dr.weapon, cat).is_empty() {
                continue; // no popover: the card shows a dash (the Warden takes no gun shield)
            }
            let rows = rows(&dr, Pop::Slot(cat), &d, &ui);
            if cat == AttachmentCategory::Optic {
                assert_eq!((rows.len(), columns(Pop::Slot(cat), rows.len())), (7, 3));
            }
            let eq = stats(cat, dr.equipped(cat, &d));
            for row in &rows {
                let RowKind::Part(id) = &row.kind else { panic!("{row:?}") };
                let part = id.as_deref().and_then(|i| d.attachment(i));
                let (lines, tags, vs) = part_copy(part, &stats(cat, None), &eq, &stats(cat, part), row.equipped);
                assert!(!lines.is_empty(), "{id:?}");
                assert_eq!(vs.is_none(), row.equipped, "{id:?}");
                if let Some(a) = part {
                    assert_eq!(tags, text::part_tags(a));
                }
                shown += 1;
            }
        }
        assert_eq!(shown, 7 + 2 + 2 + 2 + 3, "optics, stocks, mags, NONE + bipod, NONE + laser + flashlight");
        let under = AttachmentCategory::Under;
        let bipod = d.attachment("bipod");
        let (lines, tags, vs) = part_copy(bipod, &stats(under, None), &stats(under, None), &stats(under, bipod), false);
        assert_eq!(lines.iter().map(|l| l.text.as_str()).collect::<Vec<_>>(), ["ADS TIME +6 %", "MOBILITY −1 %"]);
        assert!(tags.iter().any(|t| t.not_yet && t.text.starts_with("DEPLOYS ON COVER")), "{tags:?}");
        assert_eq!(vs.map(|v| v.len()), Some(2), "against NONE equipped: the same two lines");
        let thermal = d.attachment("optic_thermal");
        let optic = AttachmentCategory::Optic;
        let (lines, ..) = part_copy(thermal, &stats(optic, None), &stats(optic, None), &stats(optic, thermal), false);
        assert!(lines.iter().any(|l| l.text == "RECOIL V +8 %" && l.tone == Tone::Bad), "{lines:?}");
    }
}
