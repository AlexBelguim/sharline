//! The design data (`design/systems/data/*.json`) is the source of truth for gameplay numbers.
//! These tests walk every value in the design JSON and check the game's RON data has the same value at
//! the same path, so a design change that is not ported to `game/assets/data/` fails `cargo test`.

use serde_json::Value;
use std::path::PathBuf;
use vetf_sim::GameData;

fn design_dir() -> Option<PathBuf> {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../design/systems/data");
    dir.is_dir().then_some(dir)
}

fn load_design(name: &str) -> Option<Value> {
    let path = design_dir()?.join(name);
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{}: {e}", path.display()));
    Some(serde_json::from_str(&text).unwrap())
}

/// Paths whose design value is free text, or a file reference the game resolves differently.
fn ignored(path: &str) -> bool {
    path.ends_with(".units")
        || path.ends_with(".note")
        || path.ends_with(".other")
        || path.ends_with(".recoil.pattern")
        || superseded(path)
}

/// Design values the user has since changed on purpose. Each one is listed, with the reason, in
/// game/DESIGN_DELTAS.md until the design docs catch up.
fn superseded(path: &str) -> bool {
    // Halo penetration comes from the ammo (weapon class x type x tier), not a flat per-weapon value.
    path.ends_with(".shield_pierce")
        // Aiming reduces recoil more than the design's 0.85.
        || path == "weapons.slice.json.weapons[0].recoil.ads_mult"
        // Each halo arc has its own shield pool, so a preset's total capacity differs.
        || (path.starts_with("armors.slice.json.presets[") && path.ends_with(".capacity"))
        // Aiming never slows you, and aimed shots are accurate in every movement state
        // (DESIGN_DELTAS.md, 'Aim on the move').
        || (path.starts_with("weapons.slice.json.weapons[")
            && (path.ends_with(".move_mult_ads")
                || path.ends_with(".spread_deg.move_full_ads")
                || path.ends_with(".spread_deg.ads_unsettled")))
        || path == "movement.slice.json.movement.jetpack.ads_allowed"
        // A slide starts from a normal run, not only a full sprint (DESIGN_DELTAS.md, 'Aim on the move').
        || path == "movement.slice.json.movement.slide.min_entry_speed"
        // Aiming never slows you, so the 3x scope's `ads_move` is gone.
        || (path.starts_with("attachments_stats.slice.json.attachments[") && path.ends_with(".ads_move"))
        // The sniper scope zooms smoothly from 6x to 12x instead of toggling (item 8d, DESIGN_DELTAS.md).
        || path == "attachments_stats.slice.json.attachments[3].other"
        || gun_tuning_round_1(path)
        || recoil_and_bloom_round_2(path)
        || recoil_roles_round_3(path)
        // The recoil pattern rewinds gradually and is back at bullet 1 sooner (item 9c, DESIGN_DELTAS.md section 15).
        || (path.starts_with("weapons.slice.json.weapons[") && path.ends_with(".recoil.reset_after_s"))
        // Playtest round 3: more steering in the air, without strafe-jump speed gains (DESIGN_DELTAS.md section 15).
        || path == "movement.slice.json.movement.air.air_wish_speed"
        // The tick rate is a host setting, 60 or 120 Hz, default 120 (net.ron; DESIGN_DELTAS.md, '120 Hz').
        || path == "weapons.slice.json.tick_hz"
        || path == "movement.slice.json.tick_hz"
        // Playtest round 4: a faster, longer slide (DESIGN_DELTAS.md section 41).
        || path == "movement.slice.json.movement.slide.boost"
        || path == "movement.slice.json.movement.slide.friction"
        || path.ends_with("slide_boost") && path.contains(".weight_effects.")
}

/// Playtest round 3 (DESIGN_DELTAS.md section 15): the Mako's pattern is a T, looping its two full sweeps, and
/// stocks lower only the vertical recoil, front grips only the horizontal, each by its own amount.
fn recoil_roles_round_3(path: &str) -> bool {
    path == "mako_recoil_pattern.json.loop_from_index"
        || (path.starts_with("attachments_stats.slice.json.attachments[")
            && (path.ends_with(".recoil_v") || path.ends_with(".recoil_h")))
}

/// Playtest round 2 recoil and bloom (DESIGN_DELTAS.md section 12): no random spread standing still (no
/// `hip_still` / `ads_still`), a fixed Warden kick, Apex-style bloom on the move that is small aimed, and a raise from
/// the sprint pose about as fast as the ADS.
fn recoil_and_bloom_round_2(path: &str) -> bool {
    let Some(rest) = path.strip_prefix("weapons.slice.json.weapons[") else { return false };
    let Some((gun, key)) = rest.split_once("].") else { return false };
    let spread = ["ads_still", "hip_still", "move_threshold_frac", "bloom_per_shot_ads"];
    let per_gun: &[&str] = match gun {
        // Mako
        "0" => &["slide", "zipline", "bloom_max_ads", "bloom_decay_delay_s"],
        // Warden
        "1" => &["air", "slide", "zipline"],
        _ => &[],
    };
    key.strip_prefix("spread_deg.").is_some_and(|k| spread.contains(&k) || per_gun.contains(&k))
        || key == "sprint_to_fire_s"
        || key == "recoil.kick_yaw_rand_deg"
}

/// Playtest round 1 gun tuning (DESIGN_DELTAS.md section 9): a harder-hitting Mako with a stronger, learnable
/// recoil pattern that never recovers mid-spray, and much faster ADS on every gun.
fn gun_tuning_round_1(path: &str) -> bool {
    const MAKO: &str = "weapons.slice.json.weapons[0].";
    const WARDEN: &str = "weapons.slice.json.weapons[1].";
    let mako = ["damage", "falloff", "min_damage", "zone_mult.head", "ads_s"];
    let mako_recoil = ["recover_frac", "recover_delay_s", "recover_deg_per_s", "view_punch_visual_deg"];
    path.strip_prefix(MAKO).is_some_and(|k| mako.contains(&k))
        || path.strip_prefix(MAKO).and_then(|k| k.strip_prefix("recoil.")).is_some_and(|k| mako_recoil.contains(&k))
        || path == format!("{WARDEN}ads_s")
        || path == "mako_recoil_pattern.json.kicks"
}

/// Check that every leaf in `design` exists in `game` with the same value. Extra game keys are allowed.
fn compare(path: &str, design: &Value, game: &Value, errors: &mut Vec<String>) {
    if ignored(path) {
        return;
    }
    match (design, game) {
        (Value::Number(a), Value::Number(b)) => {
            let (a, b) = (a.as_f64().unwrap(), b.as_f64().unwrap());
            if (a - b).abs() > 1e-5 * a.abs().max(1.0) {
                errors.push(format!("{path}: design {a} != game {b}"));
            }
        }
        (Value::Object(a), Value::Object(b)) => {
            for (k, v) in a {
                match b.get(k) {
                    Some(g) => compare(&format!("{path}.{k}"), v, g, errors),
                    None if ignored(&format!("{path}.{k}")) => {}
                    None => errors.push(format!("{path}.{k}: missing in game data")),
                }
            }
        }
        // Fit lists: the game may add its own weapons; every design entry must still be there.
        (Value::Array(a), Value::Array(b)) if path.ends_with(".fits") => {
            for v in a {
                if !b.contains(v) {
                    errors.push(format!("{path}: design entry {v} missing in game"));
                }
            }
        }
        (Value::Array(a), Value::Array(b)) => {
            if a.len() != b.len() {
                errors.push(format!("{path}: design has {} items, game has {}", a.len(), b.len()));
                return;
            }
            for (i, (x, y)) in a.iter().zip(b).enumerate() {
                compare(&format!("{path}[{i}]"), x, y, errors);
            }
        }
        (a, b) if a == b => {}
        (a, b) => errors.push(format!("{path}: design {a} != game {b}")),
    }
}

fn check(file: &str, game: Value) {
    let Some(design) = load_design(file) else {
        eprintln!("design/ not found next to game/: skipping {file}");
        return;
    };
    let mut errors = Vec::new();
    compare(file, &design, &game, &mut errors);
    assert!(errors.is_empty(), "game/assets/data drifted from design/systems/data:\n  {}", errors.join("\n  "));
}

fn to_value<T: serde::Serialize>(v: &T) -> Value {
    serde_json::to_value(v).unwrap()
}

/// Pick the game records with the same ids as the design's `key` array, in design order, so the game may
/// add records (new weapons, presets, attachments) without hiding drift in the design's own ones.
fn by_design_ids(design: &Value, key: &str, game: Value) -> Value {
    let game_items = game.as_array().cloned().unwrap_or_default();
    let picked: Vec<Value> = design[key]
        .as_array()
        .unwrap()
        .iter()
        .map(|d| {
            let id = &d["id"];
            game_items
                .iter()
                .find(|g| &g["id"] == id)
                .cloned()
                .unwrap_or_else(|| panic!("design {key} {id} missing in game data"))
        })
        .collect();
    Value::Array(picked)
}

#[test]
fn weapons_match_design() {
    let d = GameData::embedded();
    let Some(design) = load_design("weapons.slice.json") else { return };
    let mut game = to_value(&d.weapons);
    game["weapons"] = by_design_ids(&design, "weapons", game["weapons"].clone());
    check("weapons.slice.json", game);
}

#[test]
fn recoil_pattern_matches_design() {
    let d = GameData::embedded();
    check("mako_recoil_pattern.json", to_value(&d.recoil_patterns["mako_recoil_pattern"]));
}

#[test]
fn armor_matches_design() {
    let d = GameData::embedded();
    // The game has extra mixed-tier presets; compare the design's presets, by id, in design order.
    let Some(design) = load_design("armors.slice.json") else {
        return;
    };
    let presets: Vec<_> = design["presets"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| {
            let id = p["id"].as_str().unwrap();
            d.armor.resolve_id(id).unwrap_or_else(|| panic!("design preset {id} missing from armor.ron"))
        })
        .collect();
    let mut game = to_value(&d.armor);
    game["presets"] = to_value(&presets);
    // The design stores regen as a map of objects and weight bands as [name, lo, hi] arrays, same as us.
    check("armors.slice.json", game);
}

#[test]
fn movement_matches_design() {
    let d = GameData::embedded();
    let game = serde_json::json!({
        "tick_hz": d.net.tick_hz,
        "weight_effects": to_value(&d.armor.weight_effects),
        "movement": to_value(&d.movement),
    });
    check("movement.slice.json", game);
}

#[test]
fn attachments_match_design() {
    let d = GameData::embedded();
    let Some(design) = load_design("attachments_stats.slice.json") else { return };
    let mut game = to_value(&d.attachments);
    game["attachments"] = by_design_ids(&design, "attachments", game["attachments"].clone());
    check("attachments_stats.slice.json", game);
}

#[test]
fn throwable_charge_matches_design() {
    check("throwables.slice.json", to_value(&GameData::embedded().throwables));
}
