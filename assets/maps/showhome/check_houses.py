"""Summarise an alignment report (layout/check_alignment.py) for the house kit only.

    blender -b --factory-startup -P layout/check_alignment.py -- --art kit/houses.glb --out kit/alignment_houses.json
    python check_houses.py [kit/alignment_houses.json] [--list N]

The checker scans the whole map, so every structure the house kit does not draw shows up as INVISIBLE; this keeps
the house structures (SAGE/CLAY_HOUSE, *_HOUSE_PROPS) plus the house floors, and GHOSTs from any structure (art of
the houses poking into open space next to other brushes).
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
HOUSES = ("SAGE_HOUSE", "CLAY_HOUSE", "SAGE_HOUSE_PROPS", "CLAY_HOUSE_PROPS")


def house_floor(m):
    x, y = m["hit"][0], m["hit"][1]
    return m["structure"] == "GROUND" and (8.9 < x < 21.1 or 50.9 < x < 63.1) and 15.9 < y < 32.1 and \
        abs(m["hit"][2]) < 0.05


def main():
    a = [x for x in sys.argv[1:] if x.endswith(".json")]
    path = a[0] if a else os.path.join(HERE, "kit", "alignment_houses.json")
    n_list = int(sys.argv[sys.argv.index("--list") + 1]) if "--list" in sys.argv else 25
    rep = json.load(open(path))
    keep = [m for m in rep["items"] if m["structure"] in HOUSES or house_floor(m) or m["kind"] == "GHOST"]
    c = Counter((m["structure"], m["tag"], m.get("part"), m["kind"]) for m in keep)
    g = sum(1 for m in keep if m["kind"] == "GHOST")
    i = sum(1 for m in keep if m["kind"] == "INVISIBLE")
    print(f"house kit: {len(keep)} mismatches (GHOST {g}, INVISIBLE {i}) of {rep['rays']} rays; tol {rep['tol']}")
    for k, n in c.most_common(40):
        print("  ", n, *k)
    print("examples:")
    for m in sorted(keep, key=lambda m: (m["kind"], m["tag"]))[:n_list]:
        print("  ", m["kind"], m["tag"], m.get("part"), "origin", m["origin"], "dir", m["dir"], "hit", m["hit"],
              "d_col", m["d_col"], "d_art", m["d_art"])


if __name__ == "__main__":
    main()
