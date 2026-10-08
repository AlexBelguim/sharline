//! The attachment list popover (mockup 05b) and the ammo picker that reuses it for a magazine card: every
//! part that fits the slot (or every round the gun loads) with a one-line blurb, the two biggest changes and,
//! for ammo, its gear cost against the budget.

use super::model::{Draft, WeaponStats, parts_for, parts_with, pushes_over, weapon_stats};
use super::text::{self, Delta, Tone};
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
            (format!("{} · {} PARTS", cat.label(), rows.len()), "HOVER = PREVIEW + STAT DELTA".into())
        }
        (Pop::Mag(i), _) => (format!("MAG {} · AMMO", i + 1), "HOVER = STAT DELTA · COST".into()),
    };
    let f = v.fonts;
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
                width: px(420),
                padding: UiRect::all(px(12)),
                flex_direction: FlexDirection::Column,
                ..default()
            },
        ),
        // Grow upwards from the anchor.
        UiTransform::from_translation(Val2::percent(0.0, -100.0)),
    ));
    // PANEL_HI is dark on dark elsewhere; here it lies on the bright preview, where linear-light blending
    // would let the gun show through far more than the mockup's .82 does: the kit's PANEL_HI over art.
    panel.insert(BackgroundColor(PANEL_HI_OVER_ART));
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
        for (i, row) in rows.iter().enumerate() {
            spawn_row(v, panel, pop, i, row, compact, equipped_stats.as_ref());
        }
    });
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
                let row_stats = stats_with(v, cat, spec);
                deltas = if row.equipped {
                    // The equipped row shows its own effect against NONE or the gun's default part.
                    let base_part = if v.data.attachments.is_optional(cat) {
                        None
                    } else {
                        super::model::default_part(v.data, &draft.weapon, cat)
                    };
                    text::stat_deltas(&stats_with(v, cat, base_part), eq)
                } else {
                    text::stat_deltas(eq, &row_stats)
                };
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
        });
}

/// A blurb with optional inline key caps (`{G}`).
fn spawn_blurb(v: &View, parent: &mut ChildSpawnerCommands, blurb: &str) {
    let f = v.fonts;
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
        dr.switch_weapon("sk9_skink", &d);
        assert_eq!(rows(&dr, Pop::Mag(0), &d, &ui).len(), 7, "the SMG adds RIP I-III");
    }
}
