"""Pure-Python data shared by the Blender build (halo_lib.py) and make_catalog.py (no bpy needed).

Gameplay numbers are NOT copied here: they are read from the game's data file at import time
(game/assets/data/armor.ron, the source of truth) and cross-checked against the design data
(design/systems/data/armors.slice.json).  Any disagreement raises GameDataMismatch, so the art kit can never
silently drift from the game.  Set HALO_ALLOW_DATA_DRIFT=1 to turn the mismatch into a warning.
Only art-side values (colours, halo scale, orbit geometry) live in this file.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
GAME_ARMOR = os.path.join(ROOT, "game", "assets", "data", "armor.ron")
DESIGN_ARMOR = os.path.join(ROOT, "design", "systems", "data", "armors.slice.json")

ZONES_LC = ("head", "torso", "arms", "legs")
TIERS = {
    1: (0.85, 0.88, 0.92),   # white
    2: (0.10, 0.45, 1.00),   # blue
    3: (0.55, 0.15, 1.00),   # violet
    4: (1.00, 0.62, 0.08),   # gold
}

# Art-side weight-class visuals.  cells must equal the game's weight_effects cells (checked below).
# orbit_z puts the power cells above the ring top so the true count shows at eye level
# (qa/qa_cell_visibility.py: >= 90 % of the orbit at -2 and -5 deg).
WEIGHT_VISUALS = {
    "Light": dict(scale=0.85, band=None, cells=1, orbit_r=0.215, orbit_z=0.058, orbit_period_s=2.6),
    "Medium": dict(scale=1.00, band="Medium", cells=2, orbit_r=0.245, orbit_z=0.058, orbit_period_s=3.4),
    "Heavy": dict(scale=1.20, band="Heavy", cells=3, orbit_r=0.275, orbit_z=0.058, orbit_period_s=4.6),
}


class GameDataMismatch(RuntimeError):
    pass


def _strip_comments(text):
    return "\n".join(line.split("//", 1)[0] for line in text.splitlines())


def _block(text, key, open_ch, close_ch):
    """Return the text inside `key: <open_ch> ... <close_ch>` (balanced)."""
    m = re.search(r"\b" + re.escape(key) + r"\s*:\s*" + re.escape(open_ch), text)
    if not m:
        raise GameDataMismatch(f"armor.ron: '{key}' not found")
    i, depth = m.end(), 1
    while depth:
        c = text[i]
        depth += c == open_ch
        depth -= c == close_ch
        i += 1
    return text[m.end():i - 1]


def _num(s):
    return float(s) if "." in s else int(s)


def load_game_armor(path=GAME_ARMOR):
    text = _strip_comments(open(path, encoding="utf-8").read())
    out = {}
    out["capacity"] = {k: [float(x) for x in v.split(",") if x.strip()]
                       for k, v in re.findall(r"(\w+)\s*:\s*\[([^\]]*)\]", _block(text, "capacity", "{", "}"))}
    out["zone_capacity_share"] = {k: float(v) for k, v in
                                  re.findall(r"(\w+)\s*:\s*([\d.]+)", _block(text, "zone_capacity_share", "(", ")"))}
    out["regen"] = {}
    for core, body in re.findall(r"(\w+)\s*:\s*\(([^)]*)\)", _block(text, "regen", "{", "}")):
        out["regen"][core] = {k: float(v) for k, v in re.findall(r"(\w+)\s*:\s*([\d.]+)", body)}
    out["weight_bands"] = [(n, int(lo), int(hi)) for n, lo, hi in
                           re.findall(r"\((\w+)\s*,\s*(\d+)\s*,\s*(\d+)\)", _block(text, "weight_bands", "[", "]"))]
    out["weight_effects"] = {}
    for wc, body in re.findall(r"(\w+)\s*:\s*\(([^)]*)\)", _block(text, "weight_effects", "{", "}")):
        out["weight_effects"][wc] = {k: _num(v) for k, v in re.findall(r"(\w+)\s*:\s*([\d.]+)", body)}
    out["loadout_tier_caps"] = {k: int(v) for k, v in
                                re.findall(r"(\w+)\s*:\s*(\d+)", _block(text, "loadout_tier_caps", "(", ")"))}
    out["status_effects"] = dict(re.findall(r'(\w+)\s*:\s*"([^"]*)"', _block(text, "status_effects", "{", "}")))
    out["presets"] = []
    for pid, name, core, tiers in re.findall(
            r'\(\s*id\s*:\s*"(\w+)"\s*,\s*name\s*:\s*"([^"]*)"\s*,\s*core\s*:\s*(?:Some\((\w+)\)|None)\s*,'
            r'\s*tiers\s*:\s*\(([^)]*)\)\s*,?\s*\)', _block(text, "presets", "[", "]")):
        t = {k: int(v) for k, v in re.findall(r"(\w+)\s*:\s*(\d+)", tiers)}
        out["presets"].append({"id": pid, "name": name, "core": core or None, "tiers": t})
    for k in ("capacity", "zone_capacity_share", "regen", "weight_bands", "weight_effects", "presets"):
        if not out[k]:
            raise GameDataMismatch(f"armor.ron: could not parse '{k}'")
    return out


def _check(problems, what, game, design):
    if game != design:
        problems.append(f"{what}: game={game!r} design={design!r}")


def cross_check(game, path=DESIGN_ARMOR):
    """Compare the game's armor.ron with the design JSON; raise (or warn) on any difference."""
    if not os.path.exists(path):
        print("WARNING: design armor data not found, skipping cross-check:", path)
        return []
    d = json.load(open(path, encoding="utf-8"))
    problems = []
    for core, caps in d.get("capacity", {}).items():
        _check(problems, f"capacity[{core}]", game["capacity"].get(core), [float(x) for x in caps])
    for core, r in d.get("regen", {}).items():
        _check(problems, f"regen[{core}]", game["regen"].get(core), {k: float(v) for k, v in r.items()})
    _check(problems, "weight_bands", game["weight_bands"], [tuple(x) for x in d.get("weight_bands", [])])
    for wc, e in d.get("weight_effects", {}).items():
        g = game["weight_effects"].get(wc, {})
        for k in ("move", "cells", "energy_per_min"):
            _check(problems, f"weight_effects[{wc}].{k}", g.get(k), e.get(k))
    for wc, v in WEIGHT_VISUALS.items():
        _check(problems, f"power cells for {wc} (art kit vs game)", v["cells"],
               game["weight_effects"].get(wc, {}).get("cells"))
    if problems:
        msg = "game/assets/data/armor.ron and the design / art data disagree:\n  " + "\n  ".join(problems)
        if os.environ.get("HALO_ALLOW_DATA_DRIFT") == "1":
            print("WARNING:", msg)
        else:
            raise GameDataMismatch(msg)
    return problems


GAME = load_game_armor()
cross_check(GAME)
WEIGHT_BANDS = tuple(GAME["weight_bands"])
PRESETS = {p["id"]: p for p in GAME["presets"]}


def weight_of(arc_tiers):
    """Weight class from the sum of the arc tiers (game rule, DIRECTION_LOG 9). Accepts any zone-name case."""
    s = sum(arc_tiers.values())
    for name, lo, hi in WEIGHT_BANDS:
        if lo <= s <= hi:
            return name
    raise ValueError(f"no weight class for protection score {s}")


def preset_tiers(pid):
    """{Head, Torso, Arms, Legs: tier} of a game preset (capitalised zone names, as the Blender kit uses)."""
    t = PRESETS[pid]["tiers"]
    return {z.capitalize(): int(t.get(z, 0)) for z in ZONES_LC}
