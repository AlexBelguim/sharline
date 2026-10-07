//! Settings ▸ HUD & ACCESSIBILITY (mockup 08e): HUD scale and placement, the HUD element options, colour-blind
//! team colours and comfort. Rows for HUD features the prototype lacks (health numbers in the new HUD, the
//! minimap, damage numbers, enemy names, enemy outlines, the damage flash) show dimmed at their values until
//! the redesigned HUD has them.

use super::super::controls::{
    Ch, FieldKind, Kit, Live, Num, Tg, card, field, h2, num_text, range, row, seg, slider, switch,
};
use super::super::model::{TeamColours, team_pair};
use crate::ui_kit::Face;
use bevy::prelude::*;

/// A row for a feature the prototype does not have yet (drawn at .35, no input).
const LATER: bool = true;

pub fn build(p: &mut ChildSpawnerCommands, k: &Kit) {
    super::col(p, |c| {
        card(c, 1.0, 14.0, Node::default(), |c| {
            h2(c, k, "HUD", None, 0.0);
            // tick labels at the ends of the track ('80 %', '120 %')
            let (lo, hi) = range(k.data, Num::HudScale).track();
            let ticks = [(lo, num_text(Num::HudScale, lo)), (hi, num_text(Num::HudScale, hi))];
            let ticks = ticks.iter().map(|(v, s)| (*v, s.as_str())).collect::<Vec<_>>();
            slider_row(c, k, "HUD SCALE", None, Num::HudScale, &ticks);
            slider_row(c, k, "SAFE AREA MARGIN", Some("Pushes HUD in from the screen edge"), Num::SafeArea, &[]);
            seg_row(c, k, "ULTRAWIDE HUD WIDTH", None, Ch::Ultrawide, false, true);
            seg_row(c, k, "HEALTH NUMBERS", None, Ch::HealthNumbers, LATER, true);
            seg_row(c, k, "MINIMAP", None, Ch::Minimap, LATER, true);
            seg_row(c, k, "DAMAGE NUMBERS", None, Ch::DamageNumbers, LATER, true);
            seg_row(c, k, "KILL FEED LINES", None, Ch::KillFeed, false, true);
            seg_row(c, k, "SHOW ENEMY NAMES", None, Ch::EnemyNames, LATER, false);
        });
    });
    super::col(p, |c| {
        card(c, 1.0, 14.0, Node::default(), |c| {
            h2(c, k, "COLOUR & COMFORT", None, 0.0);
            let sub = "Halo tier colours never change; tiers also show as I–IV pips";
            row(c, k, "TEAM COLOURS", Some(sub), false, true, 76.0, |r| {
                r.spawn(Node {
                    flex_direction: FlexDirection::Column,
                    align_items: AlignItems::FlexStart,
                    ..default()
                })
                .with_children(|b| {
                    seg(b, k, Ch::TeamColours, false, &[]);
                    team_preview(b, k);
                });
            });
            // ON | THICK only: settings may never hide enemy outlines (the mockup's OFF is left out).
            seg_row(c, k, "ENEMY OUTLINE", None, Ch::EnemyOutline, LATER, true);
            slider_row(c, k, "SCREEN SHAKE", None, Num::ScreenShake, &[]);
            seg_row(c, k, "DAMAGE FLASH", Some("Red / hex edge flash when hit"), Ch::DamageFlash, false, true);
            row(c, k, "REDUCE FLASHING", None, false, true, 50.0, |r| switch(r, k, Tg::ReduceFlashing, false));
            seg_row(c, k, "TEXT SIZE", None, Ch::TextSize, LATER, true);
            // ADS has its own HOLD / TOGGLE on the Mouse & Aim tab.
            seg_row(c, k, "HOLD / TOGGLE", Some("Sprint, crouch, health panel"), Ch::HoldToggle, false, false);
        });
    });
}

fn seg_row(p: &mut ChildSpawnerCommands, k: &Kit, label: &str, sub: Option<&str>, c: Ch, dim: bool, border: bool) {
    row(p, k, label, sub, dim, border, 50.0, |r| {
        seg(r, k, c, dim, &[]);
    });
}

/// A slider (flex 1, so 400 px at 1080p) and its 70 px field.
fn slider_row(p: &mut ChildSpawnerCommands, k: &Kit, label: &str, sub: Option<&str>, n: Num, ticks: &[(f32, &str)]) {
    row(p, k, label, sub, false, true, 50.0, |r| {
        slider(r, k, n, None, ticks, false);
        field(r, k, FieldKind::Num(n), 70.0, false, false);
    });
}

/// The colour line under the team colour segments: the chosen preset's ally and enemy colours, then the
/// Deutan / Protan pair for reference.
fn team_preview(p: &mut ChildSpawnerCommands, k: &Kit) {
    let (ally, enemy) = k.s.team_colors();
    let (cb_ally, cb_enemy) = team_pair(TeamColours::Deutan);
    let mid = crate::ui_kit::TEXT_MID;
    p.spawn(Node { align_items: AlignItems::Center, column_gap: px(10), margin: UiRect::top(px(10)), ..default() })
        .with_children(|l| {
            chip(l, |c| {
                square(c, ally, Some(Live::TeamAllySquare));
                c.spawn((preview_text(k, "ALLY", ally), Live::TeamAlly));
            });
            chip(l, |c| {
                square(c, enemy, Some(Live::TeamEnemySquare));
                c.spawn((preview_text(k, "ENEMY", enemy), Live::TeamEnemy));
            });
            chip(l, |c| {
                c.spawn(preview_text(k, "· Deutan/Protan: ally", mid));
                square(c, cb_ally, None);
                c.spawn(preview_text(k, "enemy", mid));
                square(c, cb_enemy, None);
            });
        });
}

/// `.cb-prev span`: a flex row, gap 6.
fn chip(p: &mut ChildSpawnerCommands, f: impl FnOnce(&mut ChildSpawnerCommands)) {
    p.spawn(Node { align_items: AlignItems::Center, column_gap: px(6), ..default() }).with_children(f);
}

fn square(p: &mut ChildSpawnerCommands, color: Color, live: Option<Live>) {
    let mut e =
        p.spawn((Node { width: px(14), height: px(14), flex_shrink: 0.0, ..default() }, BackgroundColor(color)));
    if let Some(l) = live {
        e.insert(l);
    }
}

/// Barlow Condensed 700, 14 px, 0.1 em, in the copy's own case.
fn preview_text(k: &Kit, s: &str, color: Color) -> impl Bundle {
    k.fonts.text(s, Face::Display, 700, 14.0, color, 0.10)
}

#[cfg(test)]
mod tests {
    use super::super::super::controls::{
        Field, SegBind, SliderBind, SwitchBind, UiState, choice_labels, get_choice, get_num, get_toggle, set_choice,
        set_num, set_toggle, sync_live,
    };
    use super::super::super::model::{Settings, embedded};
    use super::*;
    use crate::ui_kit::{Disabled, UiFonts, UiImages, UiKitPlugin};
    use crate::user_config::PlayerProfile;
    use bevy::ecs::system::RunSystemOnce;

    #[derive(Debug, Clone, Copy, PartialEq)]
    enum Bound {
        /// The choice, and whether its row is dimmed.
        Seg(Ch, bool),
        Slider(Num),
        Field(FieldKind),
        Switch(Tg),
    }

    /// The tab built with the default settings into a bare world, under the returned root.
    fn built() -> (World, Entity) {
        let mut app = App::new();
        app.insert_resource(Assets::<Font>::default());
        UiKitPlugin.finish(&mut app);
        let fonts = app.world().resource::<UiFonts>().clone();
        let d = embedded();
        let (ui, images, profile) = (UiState::default(), UiImages::default(), PlayerProfile::default());
        let k = Kit {
            fonts: &fonts,
            images: &images,
            symbols: Handle::default(),
            s: &d.defaults,
            ui: &ui,
            data: d,
            profile: &profile,
        };
        let mut world = World::new();
        let root = world.spawn(Node::default()).id();
        world.commands().entity(root).with_children(|p| build(p, &k));
        world.flush();
        (world, root)
    }

    /// The tab's controls in order (column A, then B).
    fn controls() -> Vec<Bound> {
        let (world, root) = built();
        let mut out = Vec::new();
        walk(&world, root, &mut out);
        out
    }

    fn walk(world: &World, e: Entity, out: &mut Vec<Bound>) {
        let r = world.entity(e);
        let kids: Vec<Entity> = r.get::<Children>().map(|c| c.iter().collect()).unwrap_or_default();
        if let Some(b) = r.get::<SegBind>() {
            out.push(Bound::Seg(b.0, kids.iter().all(|o| world.entity(*o).contains::<Disabled>())));
            return;
        }
        if let Some(b) = r.get::<SliderBind>() {
            out.push(Bound::Slider(b.num));
        }
        if let Some(f) = r.get::<Field>() {
            out.push(Bound::Field(f.kind));
        }
        if let Some(b) = r.get::<SwitchBind>() {
            out.push(Bound::Switch(b.0));
        }
        for k in kids {
            walk(world, k, out);
        }
    }

    #[test]
    fn every_row_edits_the_hud_value_the_spec_names() {
        use Bound::*;
        let field = |n| Field(FieldKind::Num(n));
        let got = controls();
        assert_eq!(
            got,
            [
                Slider(Num::HudScale),
                field(Num::HudScale),
                Slider(Num::SafeArea),
                field(Num::SafeArea),
                Seg(Ch::Ultrawide, false),
                Seg(Ch::HealthNumbers, LATER),
                Seg(Ch::Minimap, LATER),
                Seg(Ch::DamageNumbers, LATER),
                Seg(Ch::KillFeed, false),
                Seg(Ch::EnemyNames, LATER),
                Seg(Ch::TeamColours, false),
                Seg(Ch::EnemyOutline, LATER),
                Slider(Num::ScreenShake),
                field(Num::ScreenShake),
                Seg(Ch::DamageFlash, false),
                Switch(Tg::ReduceFlashing),
                Seg(Ch::TextSize, LATER),
                Seg(Ch::HoldToggle, false),
            ]
        );
        // each control round-trips every value and writes the HUD section only
        let d = embedded();
        let mut ui = UiState::default();
        for b in got {
            let mut s = d.defaults.clone();
            let mut changed = false;
            let mut check = |s: &Settings| {
                let mut rest = s.clone();
                rest.hud = d.defaults.hud.clone();
                assert!(rest == d.defaults, "{b:?} writes outside the HUD settings");
                changed |= s.hud != d.defaults.hud;
            };
            match b {
                Seg(c, _) => {
                    for i in 0..choice_labels(&ui, d, c, &s).len() {
                        set_choice(&mut s, &mut ui, d, c, i);
                        assert_eq!(get_choice(&s, &ui, d, c), i, "{c:?}");
                        check(&s);
                    }
                }
                Slider(n) | Field(FieldKind::Num(n)) => {
                    let r = range(d, n);
                    for v in [r.min, r.max] {
                        set_num(&mut s, &mut ui, d, n, v);
                        assert!((get_num(&s, &ui, d, n) - v).abs() < 1e-4, "{n:?}");
                        check(&s);
                    }
                }
                Switch(t) => {
                    let on = get_toggle(&s, t);
                    set_toggle(&mut s, t, !on);
                    check(&s);
                }
                Field(_) => unreachable!("the tab has number fields only"),
            }
            assert!(changed, "{b:?} changes nothing");
        }
    }

    #[test]
    fn the_preview_chips_follow_the_team_colours() {
        let (mut world, _) = built();
        let d = embedded();
        let mut s = d.defaults.clone();
        s.hud.team_colours = TeamColours::Deutan;
        world.insert_resource(s);
        world.insert_resource(UiState::default());
        world.insert_resource(d.clone());
        world.run_system_once(sync_live).unwrap();
        let (ally, enemy) = team_pair(TeamColours::Deutan);
        let mut seen = 0;
        let mut q = world.query::<(&Live, Option<&TextColor>, Option<&BackgroundColor>)>();
        for (live, text, fill) in q.iter(&world) {
            let want = match live {
                Live::TeamAlly | Live::TeamAllySquare => ally,
                Live::TeamEnemy | Live::TeamEnemySquare => enemy,
                _ => continue,
            };
            let got = text.map(|t| t.0).or(fill.map(|f| f.0));
            assert_eq!(got, Some(want), "{live:?}");
            seen += 1;
        }
        assert_eq!(seen, 4, "two words and two squares");
    }
}
