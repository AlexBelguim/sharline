"""Movement course ("Kinetic Yard"): plan to scale + elevation profile along the racing line.

Run:  python draw_course.py      -> movement_course.png
"""
import math
import os
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

import layout_data as L
from draw_common import C, rect, metric_grid, scale_bar, save

HERE = os.path.dirname(os.path.abspath(__file__))

# racing line (2D polyline): start -> north up S1/S2 -> east along S3/S4 -> onto the tower -> zipline south
# -> west along S6 to the finish. s(x, y) maps a point on the line to the distance along it.
ZIP_START, ZIP_END = L.ZIPLINE
LINE = [(42.0, -48.5), (42.0, 16.0), (91.0, 16.0), (91.0, 12.0), (91.0, -44.0), (52.0, -44.0)]


def s_of(x, y):
    """distance along the racing line of the line point closest to (x, y)."""
    acc, best = 0.0, (1e9, 0.0)
    for (ax_, ay), (bx, by) in zip(LINE, LINE[1:]):
        seg = math.dist((ax_, ay), (bx, by))
        t = max(0.0, min(1.0, ((x - ax_) * (bx - ax_) + (y - ay) * (by - ay)) / (seg * seg)))
        px, py = ax_ + t * (bx - ax_), ay + t * (by - ay)
        d = math.dist((x, y), (px, py))
        if d < best[0]:
            best = (d, acc + t * seg)
        acc += seg
    return best[1]


def cable_z(y):
    (x0, y0, z0), (x1, y1, z1) = L.ZIPLINE
    return z0 + (z1 - z0) * (y0 - y) / (y0 - y1)


def plan(ax):
    rect(ax, L.COURSE_AREA, fc="#F3FAF8", ec=C["teal"], lw=1.0, ls=(0, (6, 3)))
    for p in L.COURSE_PATH:
        rect(ax, p, fc=C["path"], lw=0.5)
    ax.text(34, -32, "WALKWAY from READY ROOM east door", rotation=90, fontsize=6, ha="center", va="center")
    for name, r, z0, z1, note in L.COURSE:
        fc = C["course"]
        if "WALL" in name or "TOWER" in name:
            fc = "#8FD2C4"
        if "pit" in name:
            fc = "#FBEDEA"
        rect(ax, r, fc=fc, lw=0.6)
        if name in ("START GATE", "CORNER"):
            continue
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        rot = 90 if (r[3] - r[1]) > (r[2] - r[0]) * 1.4 else 0
        txt = name + (f"\n{note}" if note else "")
        if z0 != z1:
            txt += f"\nz {z0} -> {z1} m"
        if name == "S3 MANTLE LANE":
            cy = 13.2
        if name == "S6 FINAL LANE":
            cy = -46.6
        ax.text(cx, cy, txt, fontsize=6, ha="center", va="center", rotation=rot, zorder=9)
    rect(ax, (37.0, 4.0, 47.0, 12.0), fc="#000000", alpha=0.10, lw=0.0)   # tunnel roof shading
    for name, r, h in L.MANTLE_WALLS + [L.SLIDE_GATE, L.FINAL_BOX]:
        rect(ax, r, fc=C["teal"], lw=0.4)
        ax.text((r[0] + r[2]) / 2, r[3] + 0.5, name, fontsize=6, ha="center", va="bottom", zorder=9,
                bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.8))
    rect(ax, L.START_GRID, fc=C["teal"], alpha=0.35, ec=C["teal"], lw=0.8)
    for sx, sy in L.START_SPOTS:
        ax.plot(sx, sy, marker="^", ms=6, color=C["teal"], zorder=8)
    ax.text(42, -51.2, "START GRID 8 x 3 m, 4 spots 2 m apart", fontsize=6, ha="center")
    ax.plot([37, 47], [-46, -46], color=C["teal"], lw=3, zorder=8)
    ax.text(47.5, -46, "START GATE", fontsize=6, va="center", color=C["teal"], weight="bold")
    (x0, y0, z0), (x1, y1, z1) = L.ZIPLINE
    ax.plot([x0, x1], [y0, y1], color=C["coral"], lw=2.0, zorder=9)
    ax.text(x0 + 1.0, -14, f"S5 ZIPLINE  {L.zipline_length():.1f} m\nanchor z {z0} -> {z1} m (6.1 deg), ~11 m/s",
            fontsize=6.5, rotation=90, ha="left", va="center", color=C["coral"])
    for name, (a, b, c, d) in L.CHECKPOINTS.items():
        ax.plot([a, c], [b, d], color=C["coral"], lw=2.5, zorder=10)
        ax.text(max(a, c) + 0.5, max(b, d) + 0.5, name, fontsize=7, color=C["coral"], weight="bold", zorder=10)
    ax.plot(*L.PIT_RESPAWN, marker="x", ms=7, color=C["coral"], mew=1.5, zorder=11)
    ax.text(L.PIT_RESPAWN[0] - 0.5, L.PIT_RESPAWN[1] - 1.6, "pit respawn", fontsize=5.5, ha="right",
            color=C["coral"])
    ax.plot([p[0] for p in LINE], [p[1] for p in LINE], color=C["ink"], lw=0.8, ls=(0, (1, 1.5)), zorder=12)
    ax.set_xlim(30, 98)
    ax.set_ylim(-54, 27)
    ax.set_aspect("equal")
    metric_grid(ax, 1, 5, label_every=10, fs=7)
    scale_bar(ax, 50, 23.0, 10, fs=6, h=0.5)
    ax.set_title("A. Plan, to scale (grid 1 m). Dotted = racing line. Lanes 10 m wide (S1/S2), 8 m (S3/S4/S6).",
                 fontsize=9, loc="left")


def profile(ax):
    from matplotlib.patches import Polygon, Rectangle
    total = s_of(*LINE[-1])
    g = "#8FD2C4"

    def block(x0, x1, h, label=None, col=g):
        ax.add_patch(Rectangle((x0, 0), x1 - x0, h, fc=col, ec=C["ink"], lw=0.6, zorder=3))
        if label:
            ax.text((x0 + x1) / 2, h + 0.15, label, fontsize=5.5, ha="center", va="bottom", zorder=6)

    ax.plot([0, total], [0, 0], color=C["ink"], lw=1.0)
    # S2 ramp / platform / chute (y -16..-10 up, -10..-8 flat, -8..4 down)
    a, b, c, d = s_of(42, -16), s_of(42, -10), s_of(42, -8), s_of(42, 4)
    ax.add_patch(Polygon([(a, 0), (b, 2.0), (c, 2.0), (d, 0)], closed=True, fc=g, ec=C["ink"], lw=0.6, zorder=3))
    ax.text((b + c) / 2, 2.15, "S2 ramp 2.0 m\n+ slide chute", fontsize=5.5, ha="center", va="bottom")
    t0, t1 = s_of(42, 4), s_of(42, 12)
    ax.add_patch(Rectangle((t0, 1.3), t1 - t0, 0.25, fc=C["ink"], zorder=4))
    ax.text((t0 + t1) / 2, 1.65, "tunnel ceiling 1.3 m", fontsize=5.5, ha="center", va="bottom")
    for name, r, h in L.MANTLE_WALLS:
        block(s_of(r[0], 16), s_of(r[2], 16), h, name)
    block(s_of(72, 16), s_of(78, 16), 5.0, "JET WALL 5.0")
    tw0, tw1 = s_of(88, 16), s_of(91, 12)
    block(tw0, tw1, 6.0, "TOWER 6.0")
    p0, p1 = s_of(78, 16), s_of(88, 16)
    ax.add_patch(Rectangle((p0, -0.6), p1 - p0, 0.6, fc="#FBEDEA", ec=C["ink"], lw=0.4, zorder=2))
    ax.text((p0 + p1) / 2, -0.3, "pit (fall = reset)", fontsize=5.5, ha="center", va="center")
    # jet arcs (racing line, dotted)
    import numpy as np
    u = np.linspace(0, 1, 30)
    j0, j1 = s_of(70.5, 16), s_of(72.5, 16)
    ax.plot(j0 + (j1 - j0) * u, 5.6 * np.sin(u * math.pi / 2) ** 0.6, color=C["coral"], lw=0.8, ls=(0, (2, 2)))
    ax.plot(p0 + (p1 - p0) * u, 5.0 + 1.0 * u + 1.6 * np.sin(u * math.pi), color=C["coral"], lw=0.8,
            ls=(0, (2, 2)))
    ax.text((p0 + p1) / 2, 7.7, "jet across 10 m", fontsize=5.5, ha="center", color=C["coral"])
    # zipline cable + rider feet
    (zx0, zy0, zz0), (zx1, zy1, zz1) = L.ZIPLINE
    c0, c1 = s_of(91, zy0), s_of(91, zy1)
    ax.plot([c0, c1], [zz0, zz1], color=C["coral"], lw=1.8, zorder=5)
    r1 = s_of(91, -38.5)
    ax.plot([c0, r1], [zz0 - 2.2, cable_z(-38.5) - 2.2], color=C["coral"], lw=0.8, ls=(0, (2, 2)))
    ax.text((c0 + c1) / 2, cable_z((zy0 + zy1) / 2) + 1.3, f"ZIPLINE {L.zipline_length():.1f} m, cable 8.5 -> 3.0 m "
            "(dashed = rider feet, 2.2 m below)", fontsize=5.8, ha="center", va="bottom", color=C["coral"],
            rotation=-2)
    # anchor posts
    for cc, zz in ((c0, zz0), (c1, zz1)):
        ax.plot([cc, cc], [0 if cc > tw1 else 6.0, zz], color=C["graphite"], lw=1.5)
    g0, g1 = s_of(80.6, -44), s_of(80.0, -44)
    ax.add_patch(Rectangle((g0, 1.3), g1 - g0, 2.0, fc=C["ink"], zorder=4))
    ax.text(g1 + 0.8, 2.0, "SLIDE GATE\nopening 1.3 m", fontsize=5.5, va="center")
    block(s_of(67.2, -44), s_of(66.0, -44), 1.2, "BOX 1.2")
    marks = [("START", 42, -48.5), ("CP1", 42, 12), ("CP2", 68, 16), ("CP3", 91, 16),
             ("CP4", 91, -42), ("FINISH", 52, -44)]
    for name, x, y in marks:
        sd = s_of(x, y)
        ax.plot([sd, sd], [-1.0, 9.0], color=C["coral"] if name != "START" else C["teal"], lw=0.8,
                ls=(0, (4, 2)), zorder=1)
        ax.text(sd, -1.1, f"{name}\n{sd:.1f} m", fontsize=6, ha="center", va="top", weight="bold",
                color=C["coral"] if name != "START" else C["teal"])
    ax.set_xlim(-2, total + 3)
    ax.set_ylim(-2.4, 9.5)
    metric_grid(ax, 1, 10, fs=7)
    ax.yaxis.set_major_locator(__import__("matplotlib").ticker.MultipleLocator(1))
    ax.set_xlabel("distance along the racing line (m)", fontsize=7)
    ax.set_ylabel("height z (m)", fontsize=7)
    ax.set_title(f"B. Elevation profile along the racing line (total {total:.1f} m; vertical scale x4). "
                 "Solid = structures, dashed coral = player path.", fontsize=9, loc="left")
    ax.set_aspect(4.0)
    return total


def main():
    fig = plt.figure(figsize=(17, 21))
    gs = GridSpec(2, 1, height_ratios=[2.2, 0.75], hspace=0.12, figure=fig)
    plan(fig.add_subplot(gs[0]))
    total = profile(fig.add_subplot(gs[1]))
    fig.canvas.draw()
    fig.text(0.125, 0.9, f"MOVEMENT COURSE (Kinetic Yard): ~{total:.0f} m timed loop - sprint, slide, mantle, "
             "jetpack, zipline", fontsize=14, weight="bold", ha="left")
    save(fig, os.path.join(HERE, "movement_course.png"))
    print("route length", round(total, 1))


if __name__ == "__main__":
    main()
