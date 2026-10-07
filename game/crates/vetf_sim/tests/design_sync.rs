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
    path.ends_with(".units") || path.ends_with(".note") || path.ends_with(".other") || path.ends_with(".recoil.pattern")
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

#[test]
fn weapons_match_design() {
    let d = GameData::embedded();
    check("weapons.slice.json", to_value(&d.weapons));
}

#[test]
fn recoil_pattern_matches_design() {
    let d = GameData::embedded();
    check("mako_recoil_pattern.json", to_value(&d.recoil_patterns["mako_recoil_pattern"]));
}

#[test]
fn armor_matches_design() {
    let d = GameData::embedded();
    let presets: Vec<_> = d.armor.presets.iter().map(|p| d.armor.resolve(p)).collect();
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
    check("attachments_stats.slice.json", to_value(&d.attachments));
}
