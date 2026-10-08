//! The deathmatch layout's right column (team deathmatch and free-for-all, DIRECTION_LOG 17): ARMOR (the one
//! halo: a tier per body part, NONE up to each part's cap), AMMO (one type for every magazine, paid once) and
//! the RESULT (weight class, shield, move speed, power drain and the gear budget). The gun and its
//! attachments are the left column, as in the gun range's layout.

use super::Act;
use super::focus::Focusable;
use super::halo::{Centre, HaloLook, spawn_halo};
use super::text::{self, Tone};
use super::view::{Section, View, col_header, section, tier_looks};
use crate::ui_kit::*;
use bevy::prelude::*;
use vetf_sim::Zone;
use vetf_sim::data::{AmmoChoice, AmmoKind};

/// The column's sections, from `left` to the page's right margin.
pub fn spawn_column(root: &mut ChildSpawnerCommands, left: f32) {
    root.spawn(Node {
        position_type: PositionType::Absolute,
        left: px(left),
        right: px(48),
        top: px(108),
        flex_direction: FlexDirection::Column,
        ..default()
    })
    .with_children(|c| {
        c.spawn((section(Section::Armor), Node { flex_direction: FlexDirection::Column, ..default() }));
        c.spawn((
            section(Section::Ammo),
            Node { flex_direction: FlexDirection::Column, margin: UiRect::top(px(24)), ..default() },
        ));
        c.spawn((section(Section::Result), Node { flex_direction: FlexDirection::Column, ..default() }));
    });
}

impl View<'_> {
    /// Would this body part at `tier` take the loadout over the budget?
    fn over_with_tier(&self, z: Zone, tier: u8) -> bool {
        let Some(budget) = self.ctx.budget else { return false };
        let mut d = self.edit.draft.clone();
        d.halo.tiers[z] = tier;
        d.gear(self.data).total() > budget
    }

    /// Would this ammo type take the loadout over the budget?
    fn over_with_ammo(&self, ammo: AmmoChoice) -> bool {
        let Some(budget) = self.ctx.budget else { return false };
        let mut d = self.edit.draft.clone();
        d.set_ammo(ammo, self.data) && d.gear(self.data).total() > budget
    }

    /// ARMOR: the halo as others see it, and a row of tiers per body part.
    pub(super) fn armor(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let caps = self.data.armor.loadout_tier_caps;
        let halo = d.halo;
        let armor = self.data.armor.resolve_halo(&halo);
        let top = halo.tier_range().map_or(0, |(_, hi)| hi);
        p.spawn(col_header(f, "ARMOR", "ONE HALO FOR EVERYONE · A TIER PER BODY PART", TextRole::H2, 10.0));
        p.spawn(Node { column_gap: px(20), align_items: AlignItems::Center, ..default() }).with_children(|row| {
            row.spawn(Node { width: px(156), flex_shrink: 0.0, justify_content: JustifyContent::Center, ..default() })
                .with_children(|w| {
                    let (sub, sub_color) = match armor.weight_class {
                        vetf_sim::data::WeightClass::None => ("NO HALO".to_string(), TEXT_LOW),
                        wc => (wc.label().to_string(), tier_color(top)),
                    };
                    let look = HaloLook {
                        core: halo.core,
                        tiers: halo.tiers,
                        colors: halo.tiers.map(|_, t| tier_color(*t)),
                        weight: armor.weight_class,
                        cells: armor.power_cells,
                        accent: tier_color(top.max(1)),
                        centre: Centre::Value { value: armor.capacity.round() as u32, sub, sub_color },
                        letters: false,
                        selected: Some(self.st.arc),
                    };
                    spawn_halo(w, self.halo, f, &look, 150.0);
                });
            row.spawn(Node { flex_grow: 1.0, flex_direction: FlexDirection::Column, row_gap: px(6), ..default() })
                .with_children(|rows| {
                    for z in Zone::ALL {
                        self.arc_row(rows, z, halo.tiers[z], caps[z]);
                    }
                });
        });
        let capped: Vec<String> =
            Zone::ALL.iter().filter(|z| caps[**z] < 4).map(|z| format!("{} UP TO T{}", z.label(), caps[*z])).collect();
        if !capped.is_empty() {
            p.spawn((
                f.role(TextRole::Micro, format!("{} · HIGHER TIERS ARE RARE LOOT", capped.join(" · "))),
                Node { margin: UiRect::top(px(8)), align_self: AlignSelf::End, ..default() },
            ));
        }
    }

    /// One body part: its name, then NONE and T1-T4 (above its cap: off).
    fn arc_row(&self, rows: &mut ChildSpawnerCommands, z: Zone, tier: u8, cap: u8) {
        let f = self.fonts;
        rows.spawn(Node { height: px(46), column_gap: px(6), align_items: AlignItems::Center, ..default() })
            .with_children(|r| {
                let covered = tier > 0;
                r.spawn(Node {
                    width: px(112),
                    flex_shrink: 0.0,
                    column_gap: px(10),
                    align_items: AlignItems::Center,
                    ..default()
                })
                .with_children(|l| {
                    l.spawn(icon(self.images, Icon::zone(z), 18.0, if covered { TEXT_HI } else { TEXT_MID }));
                    l.spawn(f.role_color(TextRole::Chip, z.label(), if covered { TEXT_HI } else { TEXT_MID }));
                });
                for t in 0..=4u8 {
                    let on = tier == t;
                    let c = if t == 0 { TEXT_MID } else { tier_color(t) };
                    let looks = tier_looks(c);
                    let over = t > 0 && !on && self.over_with_tier(z, t);
                    let mut b = r.spawn((
                        Button,
                        Act::Arc(z, t),
                        Focusable,
                        Node {
                            flex_grow: 1.0,
                            flex_basis: px(0),
                            height: percent(100),
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
                    // Above the part's cap (rare loot): shown, faded, not pickable.
                    let off = t > cap;
                    let ink = |c: Color| if off { fade(c, DISABLED_ALPHA) } else { c };
                    b.with_children(|b| {
                        if t == 0 {
                            b.spawn(f.role_color(TextRole::Chip, "NONE", if on { TEXT_HI } else { TEXT_MID }));
                            return;
                        }
                        b.spawn((
                            Node { width: px(12), height: px(12), ..default() },
                            BackgroundColor(ink(c)),
                            UiTransform::from_rotation(Rot2::degrees(45.0)),
                        ));
                        // Red: picking it would go over the budget.
                        b.spawn(f.role_color(TextRole::TierBox, format!("T{t}"), ink(if over { BAD } else { c })));
                    });
                    if off {
                        b.insert(Disabled);
                    }
                }
            });
    }

    /// AMMO: every round this gun loads, one pick for all of the mode's magazines; then what it does.
    pub(super) fn ammo(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let spec = d.spec(self.data);
        let current = d.ammo();
        let flashing = self.st.flash[0] > 0.0;
        let micro = format!("ONE TYPE IN ALL {} MAGAZINES · PRICED ONCE", d.mags.len());
        p.spawn(col_header(f, "AMMO", &micro, TextRole::H2, 10.0));
        p.spawn(Node { height: px(64), column_gap: px(6), ..default() }).with_children(|row| {
            for c in d.ammo_options(self.data) {
                let on = c == current;
                let accent = ammo_color(c.kind);
                let cost = self.data.ammo_for(spec, c).map_or(0, |a| a.gear_cost);
                let over = !on && self.over_with_ammo(c);
                let border = if on && flashing { WARN } else { accent };
                let looks = Looks::new(
                    Look::new(W03, white_on(0.16, 0.03), TEXT_MID),
                    Look::new(W06, white_on(0.32, 0.06), TEXT_MID),
                    Look::new(translucent(accent, 0.08), border, TEXT_HI),
                );
                row.spawn((
                    Button,
                    Act::Ammo(c),
                    Focusable,
                    Node {
                        flex_grow: 1.0,
                        flex_basis: px(0),
                        flex_direction: FlexDirection::Column,
                        justify_content: JustifyContent::Center,
                        padding: UiRect::axes(px(12), px(8)),
                        border: UiRect::all(px(if on { 2.0 } else { 1.0 })),
                        overflow: Overflow::clip(),
                        ..default()
                    },
                    BackgroundColor(if on { looks.on.bg } else { looks.idle.bg }),
                    BorderColor::all(if on { border } else { looks.idle.border }),
                    looks,
                    Active(on),
                ))
                .with_children(|b| {
                    b.spawn(Node { column_gap: px(6), align_items: AlignItems::Center, ..default() }).with_children(
                        |n| {
                            n.spawn((
                                f.role_color(TextRole::SlotValue, text::ammo_name(self.data, c), accent),
                                TextLayout::no_wrap(),
                            ));
                            if c.kind != AmmoKind::Standard {
                                let tiers = self.data.ammo.types.get(&c.kind).map_or(1, |t| t.tiers.len() as u8);
                                n.spawn(ammo_pips(self.images, c.kind, c.tier, tiers));
                            }
                        },
                    );
                    let price = if cost == 0 { "FREE".to_string() } else { format!("{cost} PTS") };
                    b.spawn((
                        f.role_color(TextRole::Micro, price, if over { BAD } else { TEXT_MID }),
                        Node { margin: UiRect::top(px(4)), ..default() },
                    ));
                });
            }
        });
        // What the picked round does: its blurb and its two biggest effects.
        let blurb = self.data.ammo.types.get(&current.kind).map(|t| t.blurb.clone()).unwrap_or_default();
        p.spawn(Node { margin: UiRect::top(px(8)), column_gap: px(14), align_items: AlignItems::Center, ..default() })
            .with_children(|l| {
                if flashing {
                    l.spawn(f.role_color(TextRole::Micro, "THIS GUN CANNOT LOAD THE LAST PICK: STANDARD", WARN));
                } else if !blurb.is_empty() {
                    l.spawn(f.role(TextRole::Desc, blurb));
                }
                for delta in text::ammo_deltas(self.data, current) {
                    let color = match delta.tone {
                        Tone::Good => GOOD,
                        Tone::Bad => BAD,
                        Tone::Neutral => TEXT_MID,
                    };
                    l.spawn(f.role_color(TextRole::Micro, delta.text, color));
                }
            });
    }

    /// RESULT: the halo's weight class and figures, and the gear budget (halo tiers + the ammo, once).
    pub(super) fn kit_result(&self, p: &mut ChildSpawnerCommands) {
        let halo = self.edit.draft.halo;
        let armor = self.data.armor.resolve_halo(&halo);
        self.result(p, &halo, &armor);
    }
}
