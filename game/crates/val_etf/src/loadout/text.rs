//! Copy the Loadout screen generates from data: ammo names and effect lines, stat values and deltas, the
//! RESULT header, weight-band labels and the WHAT OTHERS SEE lines. Minus signs are U+2212, as in the
//! mockups. Pure functions, tested below.

use super::model::WeaponStats;
use super::ui_data::LoadoutUiData;
use vetf_sim::GameData;
use vetf_sim::Zone;
use vetf_sim::data::{AmmoChoice, AmmoKind, ArmorStats, AttachmentSpec, WeaponSpec, WeightClass, Zoom};
use vetf_sim::gear::HaloChoice;

pub const MINUS: char = '\u{2212}';

/// `+3` / `−3` with `decimals` decimals (no sign for zero).
pub fn signed(v: f32, decimals: usize) -> String {
    let s = format!("{:.*}", decimals, v.abs());
    let zero = s.chars().all(|c| c == '0' || c == '.');
    if zero {
        s
    } else if v < 0.0 {
        format!("{MINUS}{s}")
    } else {
        format!("+{s}")
    }
}

/// Better, worse or neither (the colour of a delta).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tone {
    Good,
    Bad,
    Neutral,
}

/// One line of the attachment list's or ammo picker's delta column.
#[derive(Debug, Clone, PartialEq)]
pub struct Delta {
    pub text: String,
    pub tone: Tone,
    /// Relative size, for picking the two biggest.
    pub size: f32,
}

fn tone(change: f32, lower_is_better: bool) -> Tone {
    if change.abs() < 1e-6 {
        Tone::Neutral
    } else if (change < 0.0) == lower_is_better {
        Tone::Good
    } else {
        Tone::Bad
    }
}

/// The two biggest deltas, or a neutral "NO CHANGE".
fn top_two(mut v: Vec<Delta>) -> Vec<Delta> {
    v.retain(|d| d.size > 1e-4);
    v.sort_by(|a, b| b.size.total_cmp(&a.size));
    v.truncate(2);
    if v.is_empty() {
        v.push(Delta { text: "NO CHANGE".into(), tone: Tone::Neutral, size: 0.0 });
    }
    v
}

fn zoom_text(z: &Option<Zoom>) -> Option<String> {
    let fmt = |v: f32| if (v - v.round()).abs() < 1e-3 { format!("{v:.0}") } else { format!("{v:.2}") };
    match z {
        Some(Zoom::Fixed(v)) => Some(format!("{}×", fmt(*v))),
        Some(Zoom::Levels(l)) => Some(format!("{}×", l.iter().map(|v| fmt(*v)).collect::<Vec<_>>().join("/"))),
        None => None,
    }
}

fn zoom_first(z: &Option<Zoom>) -> f32 {
    match z {
        Some(Zoom::Fixed(v)) => *v,
        Some(Zoom::Levels(l)) => l.first().copied().unwrap_or(1.0),
        None => 1.0,
    }
}

/// What changes going from `from` to `to` (an attachment list row against the equipped part).
pub fn stat_deltas(from: &WeaponStats, to: &WeaponStats) -> Vec<Delta> {
    let mut v = Vec::new();
    let rel = |a: f32, b: f32| if a.abs() < 1e-6 { 0.0 } else { (b / a - 1.0).abs() };
    let secs = |name: &str, a: f32, b: f32, v: &mut Vec<Delta>| {
        let d = b - a;
        if d.abs() >= 0.005 {
            v.push(Delta { text: format!("{name} {} S", signed(d, 2)), tone: tone(d, true), size: rel(a, b) });
        }
    };
    let pct = |name: &str, a: f32, b: f32, lower_better: bool, v: &mut Vec<Delta>| {
        let p = if a.abs() < 1e-6 { 0.0 } else { (b / a - 1.0) * 100.0 };
        if p.abs() >= 0.5 {
            v.push(Delta { text: format!("{name} {} %", signed(p, 0)), tone: tone(p, lower_better), size: rel(a, b) });
        }
    };
    secs("ADS", from.ads_s, to.ads_s, &mut v);
    pct("RECOIL V", from.recoil_v, to.recoil_v, true, &mut v);
    pct("RECOIL H", from.recoil_h, to.recoil_h, true, &mut v);
    pct("SWAY", from.sway, to.sway, true, &mut v);
    pct("HIP SPREAD", from.hip_spread, to.hip_spread, true, &mut v);
    secs("SPRINT-FIRE", from.sprint_to_fire_s, to.sprint_to_fire_s, &mut v);
    secs("RELOAD", from.reload_s, to.reload_s, &mut v);
    pct("MOBILITY", from.mobility, to.mobility, false, &mut v);
    if from.mag != to.mag {
        let d = to.mag as f32 - from.mag as f32;
        v.push(Delta {
            text: format!("{} RND", signed(d, 0)),
            tone: tone(d, false),
            size: rel(from.mag as f32, to.mag as f32),
        });
    }
    if from.zoom != to.zoom
        && let Some(z) = zoom_text(&to.zoom)
    {
        v.push(Delta {
            text: format!("ZOOM {z}"),
            tone: Tone::Neutral,
            size: rel(zoom_first(&from.zoom), zoom_first(&to.zoom)),
        });
    }
    top_two(v)
}

/// The long ammo name: STANDARD, AP II, RIP III, SLUG I.
pub fn ammo_name(data: &GameData, c: AmmoChoice) -> String {
    data.ammo.long_name(c).unwrap_or_else(|| format!("{:?}", c.kind).to_uppercase())
}

/// The short ammo label for chips: STD, AP II.
#[allow(dead_code)] // for the other hub screens' magazine chips
pub fn ammo_short(data: &GameData, spec: &WeaponSpec, c: AmmoChoice) -> String {
    data.ammo_for(spec, c).map_or_else(|| ammo_name(data, c), |a| a.label)
}

/// A magazine card's effect line: what its type does, from the data.
pub fn ammo_effect(data: &GameData, c: AmmoChoice) -> String {
    let Some(t) = data.ammo.types.get(&c.kind).and_then(|t| t.tiers.get(c.tier.max(1) as usize - 1)) else {
        return String::new();
    };
    match c.kind {
        AmmoKind::Standard => "BASELINE".into(),
        AmmoKind::ArmorPiercing => format!("SHIELD ×{:.2}", t.pen_mult),
        AmmoKind::Rip => format!("FLESH {} %", signed((t.flesh_mult - 1.0) * 100.0, 0)),
        AmmoKind::Slug => format!("DAMAGE ×{:.2}", t.damage_mult),
        AmmoKind::Shrapnel => "BLEED".into(),
    }
}

/// The ammo picker's delta column: the two biggest effects of a round.
pub fn ammo_deltas(data: &GameData, c: AmmoChoice) -> Vec<Delta> {
    let Some(t) = data.ammo.types.get(&c.kind).and_then(|t| t.tiers.get(c.tier.max(1) as usize - 1)) else {
        return Vec::new();
    };
    if c.kind == AmmoKind::Standard {
        return vec![Delta { text: "BASELINE".into(), tone: Tone::Neutral, size: 0.0 }];
    }
    let mut v = Vec::new();
    let mult = |name: &str, m: f32, v: &mut Vec<Delta>| {
        if (m - 1.0).abs() > 1e-4 {
            v.push(Delta { text: format!("{name} ×{m:.2}"), tone: tone(m - 1.0, false), size: (m - 1.0).abs() });
        }
    };
    let pct = |name: &str, m: f32, v: &mut Vec<Delta>| {
        if (m - 1.0).abs() > 1e-4 {
            v.push(Delta {
                text: format!("{name} {} %", signed((m - 1.0) * 100.0, 0)),
                tone: tone(m - 1.0, false),
                size: (m - 1.0).abs(),
            });
        }
    };
    mult("SHIELD", t.pen_mult, &mut v);
    if c.kind == AmmoKind::Slug {
        mult("DAMAGE", t.damage_mult, &mut v);
    } else {
        pct("DAMAGE", t.damage_mult, &mut v);
    }
    pct("FLESH", t.flesh_mult, &mut v);
    pct("SPILL", t.spill_mult, &mut v);
    if t.bypass_chance > 0.0 {
        v.push(Delta {
            text: format!("BYPASS {:.0} %", t.bypass_chance * 100.0),
            tone: Tone::Good,
            size: t.bypass_chance,
        });
    }
    top_two(v)
}

/// Weapon tab subtitle: class, then the fire modes when there is more than one.
pub fn weapon_subtitle(ui: &LoadoutUiData, spec: &WeaponSpec) -> String {
    let class = ui.ui.class_labels.get(&spec.cls).cloned().unwrap_or_default();
    if spec.fire_modes.len() > 1 {
        let modes: Vec<String> =
            spec.fire_modes.iter().map(|m| ui.ui.fire_mode_labels.get(m).cloned().unwrap_or_default()).collect();
        format!("{class} · {}", modes.join(" / "))
    } else {
        class
    }
}

#[allow(dead_code)] // for the other hub screens' halo summaries
/// The halo's tier label: `T2` when every covered arc shares it, `T1–T3` when mixed, None without a halo.
/// The second value is the highest tier (the label's colour).
pub fn tier_label(halo: &HaloChoice) -> Option<(String, u8)> {
    let (lo, hi) = halo.tier_range()?;
    Some((if lo == hi { format!("T{hi}") } else { format!("T{lo}–T{hi}") }, hi))
}

/// A halo in a few words: `T2 MENDER`, `T1–T3 BULWARK`, `NO HALO`.
pub fn halo_name(halo: &HaloChoice) -> String {
    match tier_label(halo) {
        Some((t, _)) => format!("{t} {}", halo.core.label()),
        None => "NO HALO".into(),
    }
}

/// A halo's arcs in one line: `H3 T3 A1 L1`.
pub fn arcs_line(tiers: &vetf_sim::ZoneTable<u8>) -> String {
    Zone::ALL.iter().map(|z| format!("{}{}", &z.label()[..1], tiers[*z])).collect::<Vec<_>>().join(" ")
}

/// A number of points: `0 PTS`, `1 PT`, `4 PTS`.
pub fn pts(n: u32) -> String {
    if n == 1 { "1 PT".into() } else { format!("{n} PTS") }
}

/// A pick's points on its card: `FREE`, `1 PT`, `4 PTS`.
pub fn points(n: u32) -> String {
    if n == 0 { "FREE".into() } else { pts(n) }
}

/// RESULT header: `T2 × 3 ZONES = 6 PTS`, `H2 · T3 · A1 · L0 = 6 PTS`, `NO HALO · 0 PTS`.
pub fn result_header(halo: &HaloChoice) -> String {
    let score = halo.score();
    let Some((lo, hi)) = halo.tier_range() else { return "NO HALO · 0 PTS".into() };
    if lo == hi {
        let n = halo.tiers.iter().filter(|(_, t)| **t > 0).count();
        format!("T{hi} × {n} {} = {score} PTS", if n == 1 { "ZONE" } else { "ZONES" })
    } else {
        let parts: Vec<String> = Zone::ALL.iter().map(|z| format!("{}{}", &z.label()[..1], halo.tiers[*z])).collect();
        format!("{} = {score} PTS", parts.join(" · "))
    }
}

/// Weight class boxes from the data's bands: `LIGHT ≤ 4`, `MEDIUM 5–8`, `HEAVY ≥ 9`.
pub fn weight_band_labels(data: &GameData) -> Vec<(WeightClass, String)> {
    let bands = &data.armor.weight_bands;
    bands
        .iter()
        .enumerate()
        .map(|(i, (wc, lo, hi))| {
            let label = if i == 0 {
                format!("{} ≤ {hi}", wc.label())
            } else if i + 1 == bands.len() {
                format!("{} ≥ {lo}", wc.label())
            } else {
                format!("{} {lo}–{hi}", wc.label())
            };
            (*wc, label)
        })
        .collect()
}

fn title_case(s: &str) -> String {
    let mut c = s.chars();
    match c.next() {
        Some(f) => f.to_uppercase().collect::<String>() + &c.as_str().to_lowercase(),
        None => String::new(),
    }
}

/// WHAT OTHERS SEE: (ALWAYS, ON HIT, ON SCAN).
pub fn what_others_see(ui: &LoadoutUiData, halo: &HaloChoice, armor: &ArmorStats) -> [String; 3] {
    let Some((lo, hi)) = halo.tier_range() else {
        return ["No halo: nothing to read".into(), "Hits go straight to health".into(), "No halo".into()];
    };
    let mixed = lo != hi;
    let colour = ui.tier_colour_name(hi);
    let cells = match armor.power_cells {
        1 => "1 cell".to_string(),
        n => format!("{n} cells"),
    };
    let always = if mixed {
        format!("{} halo (size, band, {cells}) in dimmed tier colours", armor.weight_class.label())
    } else {
        format!("{} halo (size, band, {cells}) in dimmed {colour}", armor.weight_class.label())
    };
    let arcs: Vec<String> = Zone::ALL.iter().filter(|z| halo.tiers[**z] > 0).map(|z| title_case(z.label())).collect();
    let on_hit = if mixed {
        format!("Lit arcs: {} · hex shards in tier colours · cracks", arcs.join(", "))
    } else {
        format!("Lit arcs: {} · {colour} hex shards · cracks", arcs.join(", "))
    };
    let cap = armor.capacity.round();
    let on_scan = format!("Everything: {}, {cap}/{cap}, {cells}, status effect", title_case(halo.core.label()));
    [always, on_hit, on_scan]
}

/// One stat row's value text: (value, inline delta) for the stats panel.
pub fn stat_value(row: usize, s: &WeaponStats) -> String {
    match row {
        0 => format!("{:.2} s", s.ads_s),
        1 => format!("{:.0} rpm", s.rpm),
        2 => format!("{:.0}", s.recoil_v),
        3 => format!("{:.0}", s.recoil_h),
        4 => format!("{:.0} %", s.mobility),
        5 => format!("{:.1} s", s.reload_s),
        6 => format!("{:.0} m", s.range_m),
        _ => format!("{}", s.mag),
    }
}

/// The inline delta of a stat row (None when it does not change).
pub fn stat_inline_delta(row: usize, base: &WeaponStats, new: &WeaponStats) -> Option<(String, Tone)> {
    let pct = |a: f32, b: f32, lower: bool| {
        let p = if a.abs() < 1e-6 { 0.0 } else { (b / a - 1.0) * 100.0 };
        (p.abs() >= 0.5).then(|| (format!("{} %", signed(p, 0)), tone(p, lower)))
    };
    match row {
        0 => {
            let d = new.ads_s - base.ads_s;
            (d.abs() >= 0.005).then(|| (signed(d, 2), tone(d, true)))
        }
        2 => pct(base.recoil_v, new.recoil_v, true),
        3 => pct(base.recoil_h, new.recoil_h, true),
        4 => {
            let d = new.mobility - base.mobility;
            (d.abs() >= 0.5).then(|| (format!("{} %", signed(d, 0)), tone(d, false)))
        }
        5 => {
            let d = new.reload_s - base.reload_s;
            (d.abs() >= 0.05).then(|| (signed(d, 1), tone(d, true)))
        }
        7 => {
            let d = new.mag as f32 - base.mag as f32;
            (d.abs() >= 0.5).then(|| (signed(d, 0), tone(d, false)))
        }
        _ => None,
    }
}

/// Stat row keys, in grid order (left, right, left, right...).
pub const STAT_KEYS: [&str; 8] =
    ["ADS TIME", "FIRE RATE", "RECOIL V", "RECOIL H", "MOBILITY", "RELOAD", "EFF. RANGE", "MAG SIZE"];

/// The value a stat row's bar measures (index into [`STAT_KEYS`]).
pub fn stat_number(row: usize, s: &WeaponStats) -> f32 {
    match row {
        0 => s.ads_s,
        1 => s.rpm,
        2 => s.recoil_v,
        3 => s.recoil_h,
        4 => s.mobility,
        5 => s.reload_s,
        6 => s.range_m,
        _ => s.mag as f32,
    }
}

/// The name an attachment row shows for a part (or NONE).
pub fn part_name(a: Option<&AttachmentSpec>) -> String {
    a.map_or("NONE".into(), |a| a.display_name().to_uppercase())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::loadout::model::{parts_with, weapon_stats};
    use vetf_sim::ZoneTable;
    use vetf_sim::data::{AttachmentCategory, Core};

    fn halo(core: Core, h: u8, t: u8, a: u8, l: u8) -> HaloChoice {
        HaloChoice { core, tiers: ZoneTable { head: h, torso: t, arms: a, legs: l } }
    }

    #[test]
    fn signs_use_the_minus_sign() {
        assert_eq!(signed(-0.02, 2), "−0.02");
        assert_eq!(signed(0.01, 2), "+0.01");
        assert_eq!(signed(0.0, 0), "0");
        assert_eq!(signed(-0.001, 2), "0.00");
    }

    #[test]
    fn ammo_copy_comes_from_the_data() {
        let d = GameData::embedded();
        let c = |kind, tier| AmmoChoice { kind, tier };
        assert_eq!(ammo_name(&d, AmmoChoice::STANDARD), "STANDARD");
        assert_eq!(ammo_name(&d, c(AmmoKind::ArmorPiercing, 2)), "AP II");
        assert_eq!(ammo_name(&d, c(AmmoKind::Slug, 1)), "SLUG I");
        let mako = d.weapon("ar7_mako").unwrap();
        assert_eq!(ammo_short(&d, mako, c(AmmoKind::ArmorPiercing, 3)), "AP III");
        assert_eq!(ammo_effect(&d, AmmoChoice::STANDARD), "BASELINE");
        assert_eq!(ammo_effect(&d, c(AmmoKind::ArmorPiercing, 2)), "SHIELD ×1.50");
        assert_eq!(ammo_effect(&d, c(AmmoKind::Rip, 1)), "FLESH +10 %");
        assert_eq!(ammo_effect(&d, c(AmmoKind::Slug, 2)), "DAMAGE ×2.10");
        let ap1 = ammo_deltas(&d, c(AmmoKind::ArmorPiercing, 1));
        assert_eq!(ap1.iter().map(|x| x.text.as_str()).collect::<Vec<_>>(), ["SHIELD ×1.20", "DAMAGE +2 %"]);
        assert!(ap1.iter().all(|x| x.tone == Tone::Good));
        let rip = ammo_deltas(&d, c(AmmoKind::Rip, 1));
        assert_eq!(rip[0].text, "SHIELD ×0.35");
        assert_eq!(rip[0].tone, Tone::Bad);
        assert_eq!(ammo_deltas(&d, AmmoChoice::STANDARD)[0].text, "BASELINE");
    }

    #[test]
    fn attachment_deltas_pick_the_two_biggest() {
        let d = GameData::embedded();
        let mako = d.weapon("ar7_mako").unwrap();
        let def: Vec<_> =
            ["optic_holo", "mako_stock_standard", "mag_30"].iter().map(|i| d.attachment(i).unwrap()).collect();
        let base = weapon_stats(&d, mako, &def);
        let with = |id: &str| weapon_stats(&d, mako, &parts_with(&def, AttachmentCategory::Under, d.attachment(id)));
        let angled = stat_deltas(&base, &with("grip_angled"));
        assert_eq!(angled.iter().map(|x| x.text.as_str()).collect::<Vec<_>>(), ["ADS −0.01 S", "RECOIL H −6 %"]);
        let vertical = stat_deltas(&base, &with("grip_vertical"));
        assert_eq!(vertical[0].text, "RECOIL V −12 %");
        assert_eq!(vertical[0].tone, Tone::Good);
        // Since ADS got fast (0.13 s), the vertical grip's +3 % is under 0.005 s; the launcher's +15 % shows.
        let ugl = stat_deltas(&base, &with("ugl_launcher"));
        assert!(ugl.iter().any(|x| x.text == "ADS +0.02 S" && x.tone == Tone::Bad), "{ugl:?}");
        assert_eq!(stat_deltas(&base, &base)[0].text, "NO CHANGE");
        let drum = weapon_stats(&d, mako, &parts_with(&def, AttachmentCategory::Mag, d.attachment("mag_drum60")));
        assert!(stat_deltas(&base, &drum).iter().any(|x| x.text == "+30 RND" && x.tone == Tone::Good));
        let scope = weapon_stats(&d, mako, &parts_with(&def, AttachmentCategory::Optic, d.attachment("optic_3x")));
        assert!(stat_deltas(&base, &scope).iter().any(|x| x.text == "ZOOM 3×"));
        assert_eq!(stat_inline_delta(0, &base, &with("grip_angled")), Some(("−0.01".into(), Tone::Good)));
        assert_eq!(stat_inline_delta(1, &base, &with("grip_angled")), None);
        assert_eq!(stat_value(0, &base), "0.13 s");
        assert_eq!(stat_value(1, &base), "720 rpm");
        assert_eq!(stat_value(4, &base), "100 %");
        assert_eq!(stat_value(6, &base), "25 m");
    }

    #[test]
    fn halo_copy() {
        let d = GameData::embedded();
        let ui = LoadoutUiData::embedded();
        let t2 = halo(Core::Mender, 2, 2, 2, 0);
        assert_eq!(tier_label(&t2), Some(("T2".into(), 2)));
        assert_eq!(result_header(&t2), "T2 × 3 ZONES = 6 PTS");
        assert_eq!(halo_name(&t2), "T2 MENDER");
        assert_eq!(arcs_line(&t2.tiers), "H2 T2 A2 L0");
        assert_eq!((points(0), points(1), points(4)), ("FREE".into(), "1 PT".into(), "4 PTS".into()));
        assert_eq!((pts(0), pts(1)), ("0 PTS".into(), "1 PT".into()));
        let mixed = halo(Core::Bulwark, 2, 3, 1, 0);
        assert_eq!(tier_label(&mixed), Some(("T1–T3".into(), 3)));
        assert_eq!(result_header(&mixed), "H2 · T3 · A1 · L0 = 6 PTS");
        let none = halo(Core::Volt, 0, 0, 0, 0);
        assert_eq!(result_header(&none), "NO HALO · 0 PTS");
        assert_eq!(halo_name(&none), "NO HALO");
        assert_eq!(result_header(&halo(Core::Phase, 0, 1, 0, 0)), "T1 × 1 ZONE = 1 PTS");
        let bands: Vec<String> = weight_band_labels(&d).into_iter().map(|(_, s)| s).collect();
        assert_eq!(bands, ["LIGHT ≤ 4", "MEDIUM 5–8", "HEAVY ≥ 9"]);
        let a = d.armor.resolve_halo(&t2);
        let see = what_others_see(&ui, &t2, &a);
        assert_eq!(see[0], "MEDIUM halo (size, band, 2 cells) in dimmed blue");
        assert_eq!(see[1], "Lit arcs: Head, Torso, Arms · blue hex shards · cracks");
        assert_eq!(see[2], "Everything: Mender, 132/132, 2 cells, status effect");
        let m = what_others_see(&ui, &mixed, &d.armor.resolve_halo(&mixed));
        assert!(m[0].ends_with("in dimmed tier colours") && m[1].contains("hex shards in tier colours"));
        assert_eq!(what_others_see(&ui, &none, &d.armor.resolve_halo(&none))[0], "No halo: nothing to read");
    }

    #[test]
    fn weapon_subtitles() {
        let d = GameData::embedded();
        let ui = LoadoutUiData::embedded();
        assert_eq!(weapon_subtitle(&ui, d.weapon("ar7_mako").unwrap()), "ASSAULT RIFLE · AUTO / SEMI");
        assert_eq!(weapon_subtitle(&ui, d.weapon("vk50_warden").unwrap()), "HEAVY BOLT-ACTION");
        assert_eq!(weapon_subtitle(&ui, d.weapon("sk9_skink").unwrap()), "SMG · AUTO / SEMI");
    }
}
