//! The deathmatch layout (team deathmatch and free-for-all, DIRECTION_LOG 17). The gun and its attachments
//! use the shared cards; the MAG slot is the magazine type (everyone carries six of the one they pick, all
//! with the one ammo type; no separate magazine row). On the right, the ARMOR row (ONE tier, T1-T4, each a fixed combination of arc tiers on the one halo, with
//! its weight class), the AMMO row (ONE type for all six magazines, priced once) and the RESULT: the weight
//! class, the halo's figures and the points used against the mode's total. Every card shows its points, in
//! red when picking it would go over the total.

use super::Act;
use super::focus::Focusable;
use super::halo::{Centre, HaloLook, spawn_halo};
use super::model::{Draft, pushes_over};
use super::text::{self, Tone};
use super::view::{Section, View, col_header, price_color, section, tier_looks};
use crate::ui_kit::*;
use bevy::prelude::*;
use vetf_sim::data::AmmoKind;

/// The right column's sections, from `left` to the page's right margin.
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

/// A pick card: a flex cell of a row of picks, framed in `accent` when on.
fn pick_card(act: Act, on: bool, accent: Color, border: Color) -> impl Bundle {
    let looks = Looks::new(
        Look::new(W03, white_on(0.16, 0.03), TEXT_MID),
        Look::new(W06, white_on(0.32, 0.06), TEXT_MID),
        Look::new(translucent(accent, 0.08), border, TEXT_HI),
    );
    (
        Button,
        act,
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
    )
}

impl View<'_> {
    /// Would this change take the loadout over the points total (or further over it)? A cheaper pick that
    /// still leaves it over is not marked: it is not what pushes the loadout over.
    fn over_with(&self, f: impl FnOnce(&mut Draft)) -> bool {
        let d = &self.edit.draft;
        pushes_over(self.ctx.budget, d.gear(self.data).total(), d.gear_with(self.data, f).total())
    }

    /// A card's points, always on show: `FREE` (muted), `2 PTS`; red when picking it would go over the total.
    fn price(&self, b: &mut ChildSpawnerCommands, pts: u32, over: bool) {
        b.spawn((
            self.fonts.role_color(TextRole::Micro, text::points(pts), price_color(pts, over)),
            TextLayout::no_wrap(),
        ));
    }

    /// ARMOR: the halo as others see it, and ONE row of tiers (each a fixed combination of arc tiers).
    pub(super) fn armor(&self, p: &mut ChildSpawnerCommands) {
        let f = self.fonts;
        let d = &self.edit.draft;
        let Some(kit) = &d.fixed else { return };
        let current = d.armor_tier();
        let halo = d.halo;
        let armor = self.data.armor.resolve_halo(&halo);
        let top = current.unwrap_or(1);
        // NO HALO (tier 0) has no tier colour of its own: a quiet grey that still reads on the dark panel
        let pick_color = |t: u8| if t == 0 { TEXT_MID } else { tier_color(t) };
        p.spawn(col_header(f, "ARMOR", "NO HALO OR ONE TIER · ONE HALO FOR EVERYONE", TextRole::H2, 10.0));
        p.spawn(Node { height: px(132), column_gap: px(16), align_items: AlignItems::Center, ..default() })
            .with_children(|row| {
                row.spawn(Node {
                    width: px(132),
                    flex_shrink: 0.0,
                    justify_content: JustifyContent::Center,
                    ..default()
                })
                .with_children(|w| {
                    let look = HaloLook {
                        core: halo.core,
                        tiers: halo.tiers,
                        colors: halo.tiers.map(|_, t| tier_color(*t)),
                        weight: armor.weight_class,
                        cells: armor.power_cells,
                        accent: tier_color(top),
                        centre: if top == 0 {
                            Centre::Value { value: 0, sub: "NO HALO".into(), sub_color: TEXT_LOW }
                        } else {
                            Centre::Value {
                                value: armor.capacity.round() as u32,
                                sub: armor.weight_class.label().to_string(),
                                sub_color: tier_color(top),
                            }
                        },
                        letters: false,
                        selected: None,
                    };
                    spawn_halo(w, self.halo, f, &look, 128.0);
                });
                row.spawn(Node { flex_grow: 1.0, height: percent(100), column_gap: px(6), ..default() }).with_children(
                    |cards| {
                        for (t, spec) in kit.armor_picks() {
                            let on = current == Some(t);
                            let c = pick_color(t);
                            let weight = self.data.armor.weight_class(spec.tiers.iter().map(|(_, x)| *x as u32).sum());
                            let over = !on && self.over_with(|x| _ = x.set_armor_tier(t));
                            let mut card = cards.spawn(pick_card(Act::Armor(t), on, c, c));
                            card.insert(tier_looks(c)).insert(BackgroundColor(if on {
                                tier_looks(c).on.bg
                            } else {
                                Color::NONE
                            }));
                            card.with_children(|b| {
                                b.spawn(Node { column_gap: px(8), align_items: AlignItems::Center, ..default() })
                                    .with_children(|l| {
                                        l.spawn((
                                            Node { width: px(12), height: px(12), ..default() },
                                            BackgroundColor(c),
                                            UiTransform::from_rotation(Rot2::degrees(45.0)),
                                        ));
                                        l.spawn(f.role_color(TextRole::TierBox, text::armor_pick(t), c));
                                        l.spawn(spacer());
                                        self.price(l, spec.points, over);
                                    });
                                b.spawn((
                                    f.role_color(TextRole::Chip, weight.label(), if on { TEXT_HI } else { TEXT_MID }),
                                    Node { margin: UiRect::top(px(10)), ..default() },
                                ));
                                b.spawn((
                                    f.role(TextRole::Micro, text::armor_pick_arcs(&spec.tiers)),
                                    TextLayout::no_wrap(),
                                    Node { margin: UiRect::top(px(4)), ..default() },
                                ));
                            });
                        }
                    },
                );
            });
    }

    /// AMMO: every round this gun loads, one pick for all six magazines (priced once); then what it does.
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
                let over = !on && self.over_with(|x| _ = x.set_ammo(c, self.data));
                let border = if on && flashing { WARN } else { accent };
                row.spawn(pick_card(Act::Ammo(c), on, accent, border)).with_children(|b| {
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
                    b.spawn(Node { margin: UiRect::top(px(4)), ..default() })
                        .with_children(|l| self.price(l, cost, over));
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

    /// RESULT: the weight class, the halo's figures and the points used against the mode's total.
    pub(super) fn kit_result(&self, p: &mut ChildSpawnerCommands) {
        let halo = self.edit.draft.halo;
        let armor = self.data.armor.resolve_halo(&halo);
        self.result(p, &halo, &armor);
    }
}
