//! Dumps the levels the game actually builds (`vetf_sim::maps::{showhome, range}`) as JSON, so the Blender
//! map kit can be aligned to the real collision brushes.
//!
//! Usage:
//!   level_dump                      print the Showhome level JSON to stdout
//!   level_dump --level range        print the range level JSON to stdout
//!   level_dump --out <dir>          write <dir>/showhome_level.json and <dir>/range_level.json
//!
//! Every brush is written in BOTH frames:
//!   * "bevy":   the sim's own numbers (Y-up, metres; north = -Z). This is the ground truth.
//!   * "design": Blender / layout frame (x = east, y = north, z = up): design = (bevy.x, -bevy.z, bevy.y).
//!     That frame is a proper rotation of the Bevy one, so plane distances carry over unchanged.
//! Values are rounded to 1e-5 m (0.01 mm).

use std::{env, fs, path::PathBuf};

use glam::Vec3;
use serde_json::{Value, json};
use vetf_sim::level::{Level, Team};
use vetf_sim::maps::{self, RangeTargetKind};
use vetf_sim::movement::collision::{Brush, BrushKind};

/// The sim sources the dump depends on, fingerprinted so a stale JSON can be detected.
const SOURCES: [(&str, &str); 5] = [
    ("maps/showhome.rs", include_str!("../../../game/crates/vetf_sim/src/maps/showhome.rs")),
    ("maps/range.rs", include_str!("../../../game/crates/vetf_sim/src/maps/range.rs")),
    ("maps/mod.rs", include_str!("../../../game/crates/vetf_sim/src/maps/mod.rs")),
    ("movement/collision.rs", include_str!("../../../game/crates/vetf_sim/src/movement/collision.rs")),
    ("level.rs", include_str!("../../../game/crates/vetf_sim/src/level.rs")),
];

fn fnv1a64(s: &str) -> String {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for b in s.bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x0000_0100_0000_01b3);
    }
    format!("{h:016x}")
}

fn r(v: f32) -> f64 {
    // `+ 0.0` turns -0.0 into 0.0.
    ((v as f64) * 1e5).round() / 1e5 + 0.0
}

fn v3(v: Vec3) -> Value {
    json!([r(v.x), r(v.y), r(v.z)])
}

/// Bevy (Y-up, north = -Z) to design (Z-up, north = +Y).
fn to_design(v: Vec3) -> Vec3 {
    Vec3::new(v.x, -v.z, v.y)
}

fn compass(d: Vec3) -> &'static str {
    // `d` is a design-frame horizontal unit vector.
    if d.x > 0.5 {
        "E"
    } else if d.x < -0.5 {
        "W"
    } else if d.y > 0.5 {
        "N"
    } else {
        "S"
    }
}

fn kind_str(k: BrushKind) -> &'static str {
    match k {
        BrushKind::Solid => "Solid",
        BrushKind::PlayerClip => "PlayerClip",
        BrushKind::BulletOnly => "BulletOnly",
    }
}

fn brush_json(i: usize, b: &Brush) -> Value {
    let (dmin, dmax) = (to_design(Vec3::new(b.min.x, b.min.y, b.max.z)), to_design(Vec3::new(b.max.x, b.max.y, b.min.z)));
    let size = dmax - dmin;
    let mut design = json!({
        "min": v3(dmin),
        "max": v3(dmax),
        "size": v3(size),
        "center": v3((dmin + dmax) * 0.5),
    });
    let mut bevy = json!({ "min": v3(b.min), "max": v3(b.max), "ramp": Value::Null });
    let shape = if let Some(rise) = b.ramp {
        let d = to_design(rise);
        let run = if d.x.abs() > 0.5 { size.x } else { size.y };
        design["ramp"] = json!({
            "rise_toward": compass(d),
            "rise_dir": v3(d),
            "z_low": r(dmin.z),
            "z_high": r(dmax.z),
            "run": r(run),
            "slope_deg": r((size.z / run).atan().to_degrees()),
            "note": "wedge inside min..max: top surface goes from z_low at the edge opposite rise_toward to z_high at the rise_toward edge",
        });
        bevy["ramp"] = v3(rise);
        // The extra (sloped) plane is the last one the builder pushes.
        if let Some(p) = b.planes.last() {
            let nd = to_design(p.normal);
            bevy["slope_plane"] = json!({ "normal": v3(p.normal), "dist": r(p.dist) });
            design["slope_plane"] = json!({ "normal": v3(nd), "dist": r(p.dist),
                "note": "solid side: dot(normal, p) < dist" });
        }
        "ramp"
    } else {
        "box"
    };
    json!({
        "i": i,
        "kind": kind_str(b.kind),
        "look": format!("{:?}", b.look),
        "shape": shape,
        "blocks_players": b.blocks_players(),
        "blocks_bullets": b.blocks_bullets(),
        "design": design,
        "bevy": bevy,
        "plane_count": b.planes.len(),
    })
}

fn team_str(t: Option<Team>) -> Value {
    match t {
        Some(Team::A) => json!("A"),
        Some(Team::B) => json!("B"),
        None => Value::Null,
    }
}

fn aabb<'a>(it: impl Iterator<Item = &'a Brush>) -> Value {
    let (mut lo, mut hi) = (Vec3::splat(f32::INFINITY), Vec3::splat(f32::NEG_INFINITY));
    let mut n = 0;
    for b in it {
        let (a, c) = (to_design(Vec3::new(b.min.x, b.min.y, b.max.z)), to_design(Vec3::new(b.max.x, b.max.y, b.min.z)));
        lo = lo.min(a);
        hi = hi.max(c);
        n += 1;
    }
    if n == 0 { Value::Null } else { json!({ "min": v3(lo), "max": v3(hi) }) }
}

fn level_json(l: &Level, extra: Value) -> Value {
    let brushes: Vec<Value> = l.world.brushes.iter().enumerate().map(|(i, b)| brush_json(i, b)).collect();
    let spawns: Vec<Value> = l
        .spawns
        .iter()
        .enumerate()
        .map(|(i, s)| {
            // Sim yaw: 0 = facing north (-Z), increasing to the left; forward = (-sin, 0, -cos).
            let fwd_b = Vec3::new(-s.yaw.sin(), 0.0, -s.yaw.cos());
            let fwd_d = to_design(fwd_b);
            let mut yaw_deg = s.yaw.to_degrees() + 90.0;
            while yaw_deg > 180.0 {
                yaw_deg -= 360.0;
            }
            while yaw_deg <= -180.0 {
                yaw_deg += 360.0;
            }
            json!({
                "i": i,
                "team": team_str(s.team),
                "design": { "pos": v3(to_design(s.pos)), "yaw_deg": r(yaw_deg), "facing": v3(fwd_d) },
                "bevy": { "pos": v3(s.pos), "yaw_rad": r(s.yaw), "facing": v3(fwd_b) },
            })
        })
        .collect();
    let ziplines: Vec<Value> = l
        .ziplines
        .iter()
        .enumerate()
        .map(|(i, z)| {
            json!({
                "i": i,
                "design": { "a": v3(to_design(z.a)), "b": v3(to_design(z.b)), "length": r(z.a.distance(z.b)) },
                "bevy": { "a": v3(z.a), "b": v3(z.b) },
            })
        })
        .collect();
    let mut counts = serde_json::Map::new();
    for b in &l.world.brushes {
        let k = format!("{}/{:?}{}", kind_str(b.kind), b.look, if b.ramp.is_some() { "/ramp" } else { "" });
        let e = counts.entry(k).or_insert(json!(0));
        *e = json!(e.as_u64().unwrap_or(0) + 1);
    }
    let sources: serde_json::Map<String, Value> =
        SOURCES.iter().map(|(n, s)| (n.to_string(), json!(fnv1a64(s)))).collect();
    let mut out = json!({
        "schema": "vetf_level_dump/1",
        "name": l.name,
        "generated_by": "tools/level_dump (cargo run --release -- --out <dir>)",
        "source_fnv1a64": sources,
        "frames": {
            "design": "metres, x = east, y = north, z = up (Blender Z-up). Use this frame in Blender.",
            "bevy": "metres, Y-up, north = -Z: bevy = (design.x, design.z, -design.y). glTF Y-up export of a Blender scene built in the design frame lands exactly here.",
            "yaw": "design yaw_deg: 0 = facing east (+x), 90 = facing north (+y). Sim yaw_rad = radians(yaw_deg - 90).",
        },
        "kill_plane": { "design_z": r(l.kill_y), "bevy_y": r(l.kill_y) },
        "bounds": {
            "all_brushes": aabb(l.world.brushes.iter()),
            "visible_brushes": aabb(l.world.brushes.iter().filter(|b| format!("{:?}", b.look) != "Invisible")),
            "player_clips": aabb(l.world.brushes.iter().filter(|b| b.kind == BrushKind::PlayerClip)),
        },
        "brush_counts": counts,
        "brush_total": l.world.brushes.len(),
        "spawns": spawns,
        "ziplines": ziplines,
        "brushes": brushes,
    });
    if let (Value::Object(o), Value::Object(e)) = (&mut out, extra) {
        for (k, v) in e {
            o.insert(k, v);
        }
    }
    out
}

fn showhome_json() -> Value {
    use maps::showhome::{AXIS_X, MAP_H, MAP_W};
    level_json(
        &maps::showhome(),
        json!({
            "map": {
                "playable_rect_design": { "x0": 0.0, "y0": 0.0, "x1": r(MAP_W), "y1": r(MAP_H) },
                "mirror_axis_x": r(AXIS_X),
                "note": "Mirror-symmetric about x = axis: west = Sage (team A), east = Clay (team B).",
            }
        }),
    )
}

fn range_json() -> Value {
    let targets: Vec<Value> = maps::range_targets()
        .iter()
        .enumerate()
        .map(|(i, t)| {
            json!({
                "i": i,
                "label": t.label,
                "kind": match t.kind { RangeTargetKind::Dummy => "Dummy", RangeTargetKind::Plate => "Plate" },
                "design": { "pos": v3(to_design(t.pos)) },
                "bevy": { "pos": v3(t.pos) },
            })
        })
        .collect();
    level_json(&maps::range(), json!({ "range_targets": targets }))
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let mut out: Option<PathBuf> = None;
    let mut which = "showhome".to_string();
    let mut it = args.iter();
    while let Some(a) = it.next() {
        match a.as_str() {
            "--out" => out = it.next().map(PathBuf::from),
            "--level" => which = it.next().cloned().unwrap_or_default().to_ascii_lowercase(),
            "-h" | "--help" => {
                println!("level_dump [--level showhome|range] [--out DIR]");
                return;
            }
            other => {
                eprintln!("unknown argument {other:?} (try --help)");
                std::process::exit(2);
            }
        }
    }
    match out {
        Some(dir) => {
            fs::create_dir_all(&dir).expect("create output dir");
            for (name, v) in [("showhome_level.json", showhome_json()), ("range_level.json", range_json())] {
                let p = dir.join(name);
                fs::write(&p, serde_json::to_string_pretty(&v).unwrap() + "\n").expect("write json");
                eprintln!("wrote {} ({} brushes)", p.display(), v["brush_total"]);
            }
        }
        None => {
            let v = if which == "range" { range_json() } else { showhome_json() };
            println!("{}", serde_json::to_string_pretty(&v).unwrap());
        }
    }
}
