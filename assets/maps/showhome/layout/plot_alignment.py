"""Plots an alignment report (from check_alignment.py) over the collision plan.

    python plot_alignment.py [renders/alignment_report.json] [out.png]
GHOST (orange) = art where the collision is open; INVISIBLE (purple) = collision face without art.
Marker size grows with the mismatch distance; hollow markers are near brush edges (bevel tolerance).
"""
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layout_lib as LL  # noqa: E402


def main():
    rp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "renders", "alignment_report.json")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(rp)[0] + ".png"
    rep = json.load(open(rp, encoding="utf-8"))
    L = LL.load()
    fig, ax = plt.subplots(figsize=(19, 13.5), dpi=100)
    for b in L.visible():
        if b["tag"]["id"] == "GROUND":
            continue
        (x0, y0, _), (x1, y1, _) = b["min"], b["max"]
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=(0.4, 0.4, 0.4), lw=0.5))
    for kind, col in (("GHOST", (1.0, 0.5, 0.0)), ("INVISIBLE", (0.5, 0.1, 0.8))):
        pts = [m for m in rep["items"] if m["kind"] == kind]
        for edge in (False, True):
            sel = [m for m in pts if m["near_edge"] == edge]
            if not sel:
                continue
            sz = [8 + 120 * min(1.0, abs((m["d_col"] or 3.0) - (m["d_art"] or 3.0))) for m in sel]
            ax.scatter([m["hit"][0] for m in sel], [m["hit"][1] for m in sel], s=sz,
                       c=[col] if not edge else "none", edgecolors=[col], linewidths=0.8,
                       label=f"{kind}{' (near edge)' if edge else ''}: {len(sel)}")
    ax.set_xlim(-1, 73)
    ax.set_ylim(-1, 49)
    ax.set_aspect("equal")
    ax.grid(True, lw=0.3, alpha=0.5)
    ax.legend(loc="upper right")
    ax.set_title(f"Alignment report {os.path.basename(rp)}: {rep['rays']} rays, {rep['mismatches']} mismatches "
                 f"(tol {rep['tol']} m, edge tol {rep['edge_tol']} m)")
    fig.tight_layout()
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
