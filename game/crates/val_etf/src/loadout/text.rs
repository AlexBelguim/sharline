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
    /// Relative size, for ordering (and picking the ammo picker's two biggest).
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

fn zoom_number(v: f32) -> String {
    if (v - v.round()).abs() < 1e-3 { format!("{v:.0}") } else { format!("{v:.2}") }
}

fn zoom_text(z: &Option<Zoom>) -> Option<String> {
    match z {
        Some(Zoom::Fixed(v)) => Some(format!("{}×", zoom_number(*v))),
        Some(Zoom::Variable([lo, hi])) => Some(format!("{}–{}×", zoom_number(*lo), zoom_number(*hi))),
        None => None,
    }
}

fn zoom_first(z: &Option<Zoom>) -> f32 {
    z.map_or(1.0, |z| z.range().0)
}

/// A stat an attachment can change, as the attachment list names it. Every multiplier field of an attachment
/// (`attachments.ron`) has one.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StatLine {
    RecoilV,
    RecoilH,
    AdsTime,
    Sway,
    Mobility,
    SprintToFire,
    /// `hip_spread`: it widens or narrows the hip cone on the move only (standing still is exact, aimed fire is
    /// not touched), so it reads MOVING SPREAD.
    MovingSpread,
    Reload,
}

impl StatLine {
    pub const ALL: [StatLine; 8] = [
        StatLine::RecoilV,
        StatLine::RecoilH,
        StatLine::AdsTime,
        StatLine::Sway,
        StatLine::Mobility,
        StatLine::SprintToFire,
        StatLine::MovingSpread,
        StatLine::Reload,
    ];

    pub fn label(self) -> &'static str {
        match self {
            StatLine::RecoilV => "RECOIL V",
            StatLine::RecoilH => "RECOIL H",
            StatLine::AdsTime => "ADS TIME",
            StatLine::Sway => "SWAY",
            StatLine::Mobility => "MOBILITY",
            StatLine::SprintToFire => "SPRINT-TO-FIRE",
            StatLine::MovingSpread => "MOVING SPREAD",
            StatLine::Reload => "RELOAD",
        }
    }

    /// The attachment field it shows (its key in `attachments.ron`); the data test holds every field to a line.
    #[cfg(test)]
    pub fn field(self) -> &'static str {
        match self {
            StatLine::RecoilV => "recoil_v",
            StatLine::RecoilH => "recoil_h",
            StatLine::AdsTime => "ads_time",
            StatLine::Sway => "sway",
            StatLine::Mobility => "move",
            StatLine::SprintToFire => "sprint_to_fire",
            StatLine::MovingSpread => "hip_spread",
            StatLine::Reload => "reload",
        }
    }

    fn value(self, s: &WeaponStats) -> f32 {
        match self {
            StatLine::RecoilV => s.recoil_v,
            StatLine::RecoilH => s.recoil_h,
            StatLine::AdsTime => s.ads_s,
            StatLine::Sway => s.sway,
            StatLine::Mobility => s.mobility,
            StatLine::SprintToFire => s.sprint_to_fire_s,
            StatLine::MovingSpread => s.hip_spread,
            StatLine::Reload => s.reload_s,
        }
    }

    fn lower_is_better(self) -> bool {
        self != StatLine::Mobility
    }
}

/// Good first, then neutral, then bad; bigger first within each.
fn good_first(v: &mut [Delta]) {
    let rank = |t: Tone| match t {
        Tone::Good => 0,
        Tone::Neutral => 1,
        Tone::Bad => 2,
    };
    v.sort_by(|a, b| rank(a.tone).cmp(&rank(b.tone)).then(b.size.total_cmp(&a.size)));
}

/// Every multiplier stat that changes from `from` to `to`, in per cent (a change under half a per cent is none,
/// one under a whole per cent shows as 1 so nothing a part does rounds away).
fn pct_lines(from: &WeaponStats, to: &WeaponStats) -> Vec<Delta> {
    let mut v = Vec::new();
    for stat in StatLine::ALL {
        let (a, b) = (stat.value(from), stat.value(to));
        let p = if a.abs() < 1e-6 { 0.0 } else { (b / a - 1.0) * 100.0 };
        if p.abs() < 0.5 {
            continue;
        }
        let shown = if p.abs() < 1.0 { p.signum() } else { p };
        v.push(Delta {
            text: format!("{} {} %", stat.label(), signed(shown, 0)),
            tone: tone(p, stat.lower_is_better()),
            size: p.abs() / 100.0,
        });
    }
    v
}

/// Everything that changes going from `from` to `to`, good first: every multiplier stat in per cent, the rounds
/// in the magazine and the zoom. The attachment list's "vs equipped" line (from = the equipped part).
pub fn stat_lines(from: &WeaponStats, to: &WeaponStats) -> Vec<Delta> {
    let rel = |a: f32, b: f32| if a.abs() < 1e-6 { 0.0 } else { (b / a - 1.0).abs() };
    let mut v = pct_lines(from, to);
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
    good_first(&mut v);
    v
}

/// What a part does on its own, against no part in its slot (`empty`: the gun with that slot empty, which for a
/// magazine is the gun's standard capacity): every stat it changes, good first, and a magazine's CAPACITY.
/// BASELINE when it changes nothing (NONE, a default stock). Its zoom and other effects are [`part_tags`].
pub fn own_lines(empty: &WeaponStats, with: &WeaponStats, part: Option<&AttachmentSpec>) -> Vec<Delta> {
    let mut v = pct_lines(empty, with);
    if let Some(cap) = part.and_then(|a| a.capacity) {
        let d = cap as f32 - empty.mag as f32;
        v.push(Delta {
            text: format!("CAPACITY {cap}"),
            tone: tone(d, false),
            size: if empty.mag == 0 { 0.0 } else { d.abs() / empty.mag as f32 },
        });
    }
    good_first(&mut v);
    if v.is_empty() {
        v.push(Delta { text: "BASELINE".into(), tone: Tone::Neutral, size: 0.0 });
    }
    v
}

/// A tag under a part's blurb: something it does that is not a stat.
#[derive(Debug, Clone, PartialEq)]
pub struct Tag {
    pub text: String,
    /// Promised but not in the game yet.
    pub not_yet: bool,
}

/// What a part does besides its stats: its zoom (`3× ZOOM`, `6–12× ZOOM · SCROLL`), then the data's effects.
pub fn part_tags(a: &AttachmentSpec) -> Vec<Tag> {
    let mut v = Vec::new();
    if let Some(z) = zoom_text(&a.zoom) {
        let scroll = if a.zoom.is_some_and(|z| z.is_variable()) { " · SCROLL" } else { "" };
        v.push(Tag { text: format!("{z} ZOOM{scroll}"), not_yet: false });
    }
    v.extend(a.effects.iter().map(|e| Tag { text: e.text.to_uppercase(), not_yet: e.not_yet }));
    v
}

/// The note a tag for something not in the game yet carries.
pub const NOT_YET: &str = "NOT IN THE GAME YET";

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

/// A deathmatch armor pick's name: `NO HALO` (tier 0), `T1`, `T2`, ...
pub fn armor_pick(tier: u8) -> String {
    if tier == 0 { "NO HALO".into() } else { format!("T{tier}") }
}

/// The arcs of a deathmatch armor pick: `H3 T3 A1 L1`, or `no shield` for no halo (not a row of zeros).
pub fn armor_pick_arcs(tiers: &vetf_sim::ZoneTable<u8>) -> String {
    if tiers.iter().all(|(_, t)| *t == 0) { "no shield".into() } else { arcs_line(tiers) }
}

/// A number of points: `0 PTS`, `1 PT`, `4 PTS`.
pub fn pts(n: u32) -> String {
    if n == 1 { "1 PT".into() } else { format!("{n} PTS") }
}

/// A pick's points on its card: `FREE`, `1 PT`, `4 PTS`.
pub fn points(n: u32) -> String {
    if n == 0 { "FREE".into() } else { pts(n) }
}

/// The points used against the mode's total, always on show in team deathmatch and free-for-all:
/// `POINTS 7 / 8`.
pub fn points_total(used: u32, budget: u32) -> String {
    format!("POINTS {used} / {budget}")
}

/// The MAG card's label in team deathmatch and free-for-all: the type picked is the one carried, `mags` of
/// it (`MAG ×6`).
pub fn mag_slot_label(mags: u8) -> String {
    format!("MAG ×{mags}")
}

/// The MAG popover's note in team deathmatch and free-for-all: `YOU CARRY 6 · ALL WITH YOUR AMMO`.
pub fn mag_carry(mags: u8) -> String {
    format!("YOU CARRY {mags} · ALL WITH YOUR AMMO")
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
    use crate::loadout::model::{default_part, parts_with, weapon_stats};
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

    fn texts(v: &[Delta]) -> Vec<&str> {
        v.iter().map(|x| x.text.as_str()).collect()
    }

    /// The gun with its default parts, one slot swapped: (slot empty, slot with `id`).
    fn stats_pair(d: &GameData, gun: &str, cat: AttachmentCategory, id: Option<&str>) -> (WeaponStats, WeaponStats) {
        let spec = d.weapon(gun).unwrap();
        let def: Vec<&AttachmentSpec> =
            AttachmentCategory::ALL.iter().filter_map(|c| default_part(d, gun, *c)).collect();
        let empty = weapon_stats(d, spec, &parts_with(&def, cat, None));
        let with = weapon_stats(d, spec, &parts_with(&def, cat, id.and_then(|i| d.attachment(i))));
        (empty, with)
    }

    fn own(d: &GameData, gun: &str, id: &str) -> Vec<Delta> {
        let a = d.attachment(id).unwrap();
        let (empty, with) = stats_pair(d, gun, a.cat, Some(id));
        own_lines(&empty, &with, Some(a))
    }

    /// Item B: a row shows the part's OWN effect against no part in the slot, every stat it changes, good first;
    /// the "vs equipped" line is the change from the equipped part.
    #[test]
    fn a_part_shows_its_own_effect_and_vs_equipped() {
        let d = GameData::embedded();
        let under = AttachmentCategory::Under;
        let angled = own(&d, "ar7_mako", "grip_angled");
        assert_eq!(texts(&angled), ["RECOIL H −30 %", "ADS TIME −8 %"]);
        assert!(angled.iter().all(|x| x.tone == Tone::Good));
        assert_eq!(
            texts(&own(&d, "ar7_mako", "grip_stub")),
            ["RECOIL H −18 %", "MOVING SPREAD −12 %", "SPRINT-TO-FIRE −10 %"]
        );
        let brace = own(&d, "ar7_mako", "grip_vertical");
        assert_eq!(texts(&brace), ["RECOIL H −45 %", "SWAY −5 %", "ADS TIME +3 %"], "good first, then bad");
        assert_eq!(brace[2].tone, Tone::Bad);
        let (empty, none) = stats_pair(&d, "ar7_mako", under, None);
        assert_eq!(texts(&own_lines(&empty, &none, None)), ["BASELINE"], "NONE does nothing");
        // The user's screenshot: the stub grip equipped. NONE's own line is BASELINE now; what it changes against
        // the stub grip is the quiet vs-equipped line.
        let (_, stub) = stats_pair(&d, "ar7_mako", under, Some("grip_stub"));
        let vs_none = stat_lines(&stub, &none);
        assert_eq!(texts(&vs_none), ["RECOIL H +22 %", "MOVING SPREAD +14 %", "SPRINT-TO-FIRE +11 %"]);
        assert!(vs_none.iter().all(|x| x.tone == Tone::Bad));
        let (_, ang) = stats_pair(&d, "ar7_mako", under, Some("grip_angled"));
        assert_eq!(
            texts(&stat_lines(&stub, &ang)),
            ["RECOIL H −15 %", "ADS TIME −8 %", "MOVING SPREAD +14 %", "SPRINT-TO-FIRE +11 %"]
        );
        assert!(stat_lines(&stub, &stub).is_empty(), "nothing changes against itself");
        // The own effect does not depend on what else is fitted (a different stock, say).
        let spec = d.weapon("ar7_mako").unwrap();
        let def: Vec<&AttachmentSpec> =
            AttachmentCategory::ALL.iter().filter_map(|c| default_part(&d, "ar7_mako", *c)).collect();
        let other = parts_with(&def, AttachmentCategory::Stock, d.attachment("mako_stock_precision"));
        let e2 = weapon_stats(&d, spec, &parts_with(&other, under, None));
        let w2 = weapon_stats(&d, spec, &parts_with(&other, under, d.attachment("grip_angled")));
        assert_eq!(texts(&own_lines(&e2, &w2, d.attachment("grip_angled"))), texts(&angled));
        // Required slots: against the slot empty. A default stock is the plain gun; a magazine has its capacity.
        assert_eq!(texts(&own(&d, "ar7_mako", "mako_stock_standard")), ["BASELINE"]);
        assert_eq!(texts(&own(&d, "ar7_mako", "mako_stock_precision"))[0], "RECOIL V −40 %");
        assert_eq!(texts(&own(&d, "ar7_mako", "mag_30")), ["CAPACITY 30"]);
        let m45 = own(&d, "ar7_mako", "mag_45");
        assert_eq!(texts(&m45), ["CAPACITY 45", "RELOAD +12 %", "ADS TIME +5 %", "MOBILITY −1 %"]);
        assert_eq!(m45[0].tone, Tone::Good);
        let mag = |id| stats_pair(&d, "ar7_mako", AttachmentCategory::Mag, Some(id)).1;
        assert!(
            stat_lines(&mag("mag_30"), &mag("mag_drum60")).iter().any(|x| x.text == "+30 RND" && x.tone == Tone::Good)
        );
        let optic = |id| stats_pair(&d, "ar7_mako", AttachmentCategory::Optic, Some(id)).1;
        assert!(stat_lines(&optic("optic_holo"), &optic("optic_3x")).iter().any(|x| x.text == "ZOOM 3×"));
    }

    /// Item B: the laser adds a little sweep and the thermal optic a little climb; both show, in red.
    #[test]
    fn recoil_penalties_show() {
        let d = GameData::embedded();
        let laser = own(&d, "ar7_mako", "laser");
        assert_eq!(texts(&laser), ["MOVING SPREAD −20 %", "RECOIL H +5 %", "ADS TIME +2 %"]);
        assert_eq!(laser[1].tone, Tone::Bad);
        let thermal = own(&d, "vk50_warden", "optic_thermal");
        assert_eq!(texts(&thermal), ["ADS TIME +20 %", "SWAY +10 %", "RECOIL V +8 %", "MOBILITY −1 %"]);
        assert!(thermal.iter().all(|x| x.tone == Tone::Bad));
    }

    /// Item B, "everything that an item does should be shown": every stat field an attachment sets (other than
    /// 1.0) has a line on its row on every gun it fits, its capacity a CAPACITY line and its zoom a tag.
    #[test]
    fn every_stat_an_attachment_sets_has_a_line() {
        let d = GameData::embedded();
        // Every multiplier field has a StatLine (a new field without one fails here).
        let all = vetf_sim::data::Modifiers {
            ads_time: Some(2.0),
            move_mult: Some(2.0),
            sway: Some(2.0),
            recoil_v: Some(2.0),
            recoil_h: Some(2.0),
            hip_spread: Some(2.0),
            reload: Some(2.0),
            sprint_to_fire: Some(2.0),
        };
        let serde_json::Value::Object(keys) = serde_json::to_value(&all).unwrap() else { unreachable!() };
        assert_eq!(keys.len(), StatLine::ALL.len());
        for k in keys.keys() {
            assert!(StatLine::ALL.iter().any(|s| s.field() == k), "no display line for `{k}`");
        }
        let mut checked = 0;
        for a in &d.attachments.attachments {
            let serde_json::Value::Object(m) = serde_json::to_value(a.modifiers()).unwrap() else { unreachable!() };
            for gun in &a.fits {
                let lines = own(&d, gun, &a.id);
                for (k, val) in &m {
                    let val = val.as_f64().unwrap() as f32;
                    if (val - 1.0).abs() < 1e-6 {
                        continue;
                    }
                    let stat = StatLine::ALL.iter().find(|s| s.field() == k).unwrap();
                    let line = lines.iter().find(|l| l.text.starts_with(stat.label()));
                    let line =
                        line.unwrap_or_else(|| panic!("{} on {gun}: no {} line in {lines:?}", a.id, stat.label()));
                    let worse = (val > 1.0) == stat.lower_is_better();
                    assert_eq!(line.tone, if worse { Tone::Bad } else { Tone::Good }, "{} {k}", a.id);
                    checked += 1;
                }
                if let Some(cap) = a.capacity {
                    assert!(lines.iter().any(|l| l.text == format!("CAPACITY {cap}")), "{}", a.id);
                }
                if a.zoom.is_some() {
                    assert!(part_tags(a).first().is_some_and(|t| t.text.contains("ZOOM")), "{}", a.id);
                }
                assert!(lines.iter().all(|l| !l.text.contains("HIP SPREAD")), "renamed: MOVING SPREAD");
            }
        }
        assert!(checked > 40, "{checked}");
    }

    /// Non-numeric effects are tags, and what is not in the game yet says so.
    #[test]
    fn tags_show_zoom_and_effects() {
        let d = GameData::embedded();
        let tags = |id: &str| part_tags(d.attachment(id).unwrap());
        let sniper = tags("optic_sniper");
        assert_eq!(sniper[0], Tag { text: "6–12× ZOOM · SCROLL".into(), not_yet: false });
        assert!(sniper.iter().any(|t| t.text.contains("GLINT") && t.not_yet), "no glint in the game yet");
        assert_eq!(tags("optic_1_3x")[0].text, "1–3× ZOOM · SCROLL");
        assert_eq!(tags("optic_3x")[0].text, "3× ZOOM");
        assert_eq!(tags("optic_reddot")[0].text, "1.15× ZOOM");
        assert!(tags("optic_thermal").iter().any(|t| t.text.starts_with("HEAT VIEW") && t.not_yet));
        let laser = tags("laser");
        assert!(laser.iter().any(|t| t.text == "EVERYONE SEES ITS BEAM WITHIN 25 M" && !t.not_yet), "{laser:?}");
        for id in ["bipod", "ugl_launcher", "flashlight", "shield_front"] {
            let a = d.attachment(id).unwrap();
            assert!(tags(id).iter().any(|t| t.not_yet), "{id}: says what is not in yet");
            assert!(a.blurb.contains("not in yet"), "{id}: the blurb promises nothing: {:?}", a.blurb);
        }
        assert!(tags("bipod").iter().any(|t| t.text.starts_with("DEPLOYS ON COVER")), "the deploy is not built yet");
        assert!(tags("mako_stock_precision").is_empty());
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
        assert_eq!(points_total(7, 8), "POINTS 7 / 8");
        assert_eq!(points_total(9, 8), "POINTS 9 / 8");
        assert_eq!(mag_slot_label(6), "MAG ×6");
        assert_eq!(mag_carry(6), "YOU CARRY 6 · ALL WITH YOUR AMMO");
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
