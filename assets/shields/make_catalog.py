"""Generate armor_catalog.example.json (plain Python, no dependencies; build_halo.py calls it too).

  python "F:/git/val etf/assets/shields/make_catalog.py"

No gameplay number is copied into this script.  halo_data.py parses game/assets/data/armor.ron (the source of
truth: per-arc tiers and per-arc shield pools, user direction in game/DESIGN_DELTAS.md #2) and cross-checks it
against design/systems/data/armors.slice.json; any disagreement stops the build (GameDataMismatch).
Examples whose id exists in the game presets take their arc tiers from the game.
Food / energy drain multipliers are art-side placeholders (the design only has energy_per_min); they scale
with the weight class so heavier = more protection but more drain and slower.
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from halo_data import GAME, PRESETS, TIERS, WEIGHT_VISUALS, ZONES_LC, weight_of  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "armor_catalog.example.json")

CAPACITY = GAME["capacity"]
ZONE_SHARE = GAME["zone_capacity_share"]
REGEN = GAME["regen"]
WEIGHT_BANDS = [list(b) for b in GAME["weight_bands"]]
EFFECTS = GAME["weight_effects"]
# art-side placeholders (not in the game data yet)
DRAIN = {"Light": dict(food=1.00, energy=1.10), "Medium": dict(food=1.05, energy=1.20),
         "Heavy": dict(food=1.15, energy=1.40)}
CORE_DRAIN_ADJUST = {"Phase": -0.05, "Bulwark": 0.05}   # added to energy_drain_mult (Phase = low drain)
STATUS = {
    "Bulwark": {"id": "steady", "params": {"flinch_taken_mult": 0.5}},
    "Mender": {"id": "fast_regen", "params": {}},
    "Volt": {"id": "break_shock", "params": {"radius_m": 4.0, "slow": 0.30, "duration_s": 1.5}},
    "Phase": {"id": "slow_immune", "params": {}},
}
STATUS_VFX = {   # engine VFX hints: cell trail / pulse and hit-particle behaviour per status effect
    "steady": "cells: slow, heavy orbit, steady glow; hit: shards fall short and drop (heavy glass)",
    "fast_regen": "cells: soft breathing pulse; regen: arcs refill from both ends with a bright moving edge",
    "break_shock": "cells: flickering spark trail; break: flat ring of shards + a ground ring flash, r = radius_m",
    "slow_immune": "cells: long ghost trail (2x fin streak); hit: shards dissolve quickly instead of falling",
}

# (id, display name, core, {zone: tier}).  Game preset ids take name/core/tiers from armor.ron (None here).
EXAMPLES = [
    ("arm_phase_runner", None, None, None),
    ("arm_phase_ghost", None, None, None),
    ("arm_mender_scout", None, None, None),
    ("arm_volt_line", None, None, None),
    ("arm_volt_sentry", "Volt Sentry", "Volt", {"head": 2, "torso": 2, "legs": 2}),   # art-side example
    ("arm_mender_medic", None, None, None),
    ("arm_bulwark_assault", None, None, None),
    ("arm_bulwark_vanguard", None, None, None),
    ("arm_bulwark_jugg", None, None, None),
]


def entry(aid, name, core, tiers):
    source = "art example"
    if aid in PRESETS:
        p = PRESETS[aid]
        name, core, tiers, source = p["name"], p["core"], p["tiers"], "game/assets/data/armor.ron preset"
    arc_tiers = {z: int(tiers.get(z, 0)) for z in ZONES_LC}
    coverage = [z for z in ZONES_LC if arc_tiers[z] > 0]
    score = sum(arc_tiers.values())
    wc = weight_of(arc_tiers)
    eff = EFFECTS[wc]
    arc_cap = {z: round(CAPACITY[core][t - 1] * ZONE_SHARE[z], 1) for z, t in arc_tiers.items() if t}
    rg = REGEN[core]
    return {
        "id": aid,
        "name": name,
        "source": source,
        "core": core,
        "tier": max(arc_tiers.values()),
        "coverage": coverage,
        "arc_tiers": arc_tiers,
        "weight_class": wc,
        "protection_score": score,
        "capacity": round(sum(arc_cap.values()), 1),
        "arc_capacity": arc_cap,
        "regen_per_s": rg["rate_per_s"],
        "regen_delay_s": rg["delay_s"],
        "regen_delay_after_break_s": rg["delay_after_break_s"],
        "power_cells": int(eff["cells"]),
        "food_drain_mult": DRAIN[wc]["food"],
        "energy_drain_mult": round(DRAIN[wc]["energy"] + CORE_DRAIN_ADJUST.get(core, 0.0), 2),
        "energy_drain_per_min": eff["energy_per_min"],
        "move_speed_mult": eff["move"],
        "status_effect": {"id": STATUS[core]["id"], "description": GAME["status_effects"].get(core, ""),
                          "params": STATUS[core]["params"]},
    }


SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "HaloArmor",
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "name", "core", "tier", "coverage", "weight_class", "capacity", "regen_per_s",
                 "power_cells", "food_drain_mult", "energy_drain_mult", "move_speed_mult", "status_effect"],
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z0-9_]+$", "description": "Stable item id (loot tables, saves)."},
        "name": {"type": "string", "description": "Display name (placeholder)."},
        "source": {"type": "string", "description": "Where the arc tiers come from (game preset or art example)."},
        "core": {"enum": ["Bulwark", "Mender", "Volt", "Phase"],
                 "description": "Ring silhouette: HALO_<core>_Arc_* + HALO_<core>_Band_* meshes, HALO_Core_<core> pickup."},
        "tier": {"type": "integer", "minimum": 1, "maximum": 4,
                 "description": "Headline tier = highest arc tier. Number of tier pips shown (HALO_<core>_PIP_1..tier) and the pip/cell/band-lip colour."},
        "coverage": {"type": "array", "minItems": 1, "maxItems": 4, "uniqueItems": True,
                     "items": {"enum": ["head", "torso", "arms", "legs"]},
                     "description": "Covered zones = arcs with tier > 0 (head = front arc, arms = +X, torso = back, legs = -X)."},
        "arc_tiers": {"type": "object", "additionalProperties": False,
                      "properties": {z: {"type": "integer", "minimum": 0, "maximum": 4} for z in ZONES_LC},
                      "description": "Per-arc tier (game/DESIGN_DELTAS.md #2). 0 = uncovered (dark arc). Each arc glows in its own tier colour."},
        "weight_class": {"enum": ["Light", "Medium", "Heavy"],
                         "description": "From protection_score via rules.weight_bands. Drives halo scale, weight band mesh, cell count, orbit."},
        "protection_score": {"type": "integer", "minimum": 1, "maximum": 16,
                             "description": "Sum of the arc tiers (= tier x zones when uniform)."},
        "capacity": {"type": "number", "exclusiveMinimum": 0, "description": "Total shield HP = sum of arc_capacity."},
        "arc_capacity": {"type": "object", "additionalProperties": {"type": "number"},
                         "description": "Shield pool per covered arc = rules.capacity[core][arc tier] x rules.zone_capacity_share[zone]."},
        "regen_per_s": {"type": "number", "minimum": 0, "description": "Shield HP regenerated per second per arc after the delay."},
        "regen_delay_s": {"type": "number", "minimum": 0, "description": "Seconds without damage before regen starts."},
        "regen_delay_after_break_s": {"type": "number", "minimum": 0, "description": "Longer delay after an arc broke."},
        "power_cells": {"type": "integer", "minimum": 1, "maximum": 3, "description": "Orbiting HALO_PowerCell count (1 Light, 2 Medium, 3 Heavy)."},
        "food_drain_mult": {"type": "number", "minimum": 0.5, "maximum": 2.0, "description": "Multiplier on the hunger drain rate while worn (art-side placeholder)."},
        "energy_drain_mult": {"type": "number", "minimum": 0.5, "maximum": 2.0, "description": "Multiplier on the energy drain rate while worn (art-side placeholder)."},
        "energy_drain_per_min": {"type": "number", "minimum": 0, "description": "Game value (absolute extra energy drain per minute)."},
        "move_speed_mult": {"type": "number", "minimum": 0.7, "maximum": 1.0, "description": "Multiplier on base movement speed."},
        "status_effect": {"type": "object", "required": ["id", "description"],
                          "properties": {"id": {"enum": ["steady", "fast_regen", "break_shock", "slow_immune"]},
                                         "description": {"type": "string"},
                                         "params": {"type": "object", "additionalProperties": {"type": "number"}}},
                          "description": "Core effect; also selects the cell trail / pulse look and hit-particle behaviour (rules.status_vfx)."},
    },
}


def main():
    cat = {
        "schema_version": 3,
        "notes": ("Example halo-shield armor catalog for the HALO kit (assets/shields/, see NOTES.md). Generated by "
                  "make_catalog.py: every gameplay number is read from game/assets/data/armor.ron at build time "
                  "and cross-checked against design/systems/data/armors.slice.json (the build fails if they "
                  "disagree). The game's data files stay the source of truth. Food/energy drain multipliers are "
                  "art-side placeholders."),
        "schema": SCHEMA,
        "rules": {
            "zones_to_arcs": {"head": "HALO_<core>_Arc_Head", "torso": "HALO_<core>_Arc_Torso",
                              "arms": "HALO_<core>_Arc_Arms", "legs": "HALO_<core>_Arc_Legs"},
            "tier_colors_linear_rgb": {str(k): list(v) for k, v in TIERS.items()},
            "protection_score": "sum(arc_tiers)",
            "weight_bands": {n: [lo, hi] for n, lo, hi in WEIGHT_BANDS},
            "loadout_tier_caps": GAME["loadout_tier_caps"],
            "weight_class_effects": {k: {"move_speed_mult": EFFECTS[k]["move"], "power_cells": int(EFFECTS[k]["cells"]),
                                         "energy_drain_per_min": EFFECTS[k]["energy_per_min"],
                                         "food_drain_mult": DRAIN[k]["food"], "energy_drain_mult": DRAIN[k]["energy"]}
                                     for k in ("Light", "Medium", "Heavy")},
            "energy_drain_core_adjust": CORE_DRAIN_ADJUST,
            "weight_class_visuals_note": ("halo_scale scales the whole halo root; orbit_radius_local and "
                                          "orbit_height_local are in the root's local space (world metres = value x "
                                          "halo_scale). orbit_height_local is above the ring plane (Blender +Z, "
                                          "glTF +Y) so the cells clear the ring top at eye level."),
            "weight_class_visuals": {k: {"halo_scale": v["scale"], "band_mesh": v["band"],
                                         "power_cells": v["cells"], "orbit_radius_local": v["orbit_r"],
                                         "orbit_height_local": v["orbit_z"], "orbit_period_s": v["orbit_period_s"]}
                                     for k, v in WEIGHT_VISUALS.items()},
            "capacity": CAPACITY,
            "zone_capacity_share": ZONE_SHARE,
            "regen": REGEN,
            "status_vfx": STATUS_VFX,
        },
        "armors": [entry(*e) for e in EXAMPLES],
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(cat, f, indent=2)
        f.write("\n")
    for a in cat["armors"]:
        print(f"  {a['id']:<22} {a['core']:<8} T{a['tier']} {a['weight_class']:<6} score={a['protection_score']:>2} "
              f"cap={a['capacity']:>6} cells={a['power_cells']} move={a['move_speed_mult']} "
              f"food={a['food_drain_mult']} energy={a['energy_drain_mult']}  ({a['source']})")
    print("wrote", OUT)
    return OUT


if __name__ == "__main__":
    main()
