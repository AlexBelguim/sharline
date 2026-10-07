"""Lane / target diagram for the shooting range: whole 0-320 m strip, close-lane detail,
target catalogue (front view, to scale) and an angular-size table.

Run:  python draw_range_lanes.py      -> range_lanes_targets.png
"""
import os
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Ellipse, Rectangle, Circle

import layout_data as L
from draw_common import C, TIER_COLORS, rect, circle, metric_grid, scale_bar, save

HERE = os.path.dirname(os.path.abspath(__file__))


def tier_color(label):
    t = L.tier_of(label)
    return TIER_COLORS[t - 1] if t else "white"


# ------------------------------------------------------------------ A: whole range, rotated
def R(r):
    """rotate a plan rect 90 deg clockwise: horizontal = y (downrange), vertical = -x (west up)."""
    x0, y0, x1, y1 = r
    return (y0, -x1, y1, -x0)


def strip(ax):
    rect(ax, R(L.FIELD), fc=C["field"], lw=0.8)
    rect(ax, R(L.BERM_W), fc=C["berm"], lw=0.5)
    rect(ax, R(L.BERM_E), fc=C["berm"], lw=0.5)
    rect(ax, R(L.BACKSTOP), fc=C["backstop"], lw=0.8, label="BACKSTOP\n10 m", fs=6)
    rect(ax, R(L.DECK), fc=C["deck"], lw=0.8, label="DECK", fs=6)
    rect(ax, R((22.0, 0.0, 30.0, 28.0)), fc=C["recoil"], lw=0.5, label="RECOIL", fs=5)
    ax.text(150, 19, "WEST SIDE BERM 4 m", fontsize=6, ha="center", va="center")
    ax.text(150, -19, "EAST SIDE BERM 4 m", fontsize=6, ha="center", va="center")
    for d in L.DISTANCE_LINES:
        ax.plot([d, d], [-16, 16], color=C["ink"], lw=0.5, ls="--")
        ax.text(d, 16.6, f"{d} m", fontsize=6.5, ha="center", va="bottom", weight="bold")
        for mx in L.MARKER_POST_X:
            ax.plot(d, -mx, "s", ms=2.5, color=C["ink"])
    for b in L.BAYS:
        tx = b["xc"] + L.LANE_TRACK_OFFSET
        ax.plot(list(L.LANE_TRACK_Y), [-tx, -tx], color=C["teal"], lw=0.7)
        for d in L.LANE_PLATES:
            ax.plot(d, -(b["xc"] + L.PLATE_STAND_OFFSET), "s", ms=1.8, color=C["steel"])
    ax.plot([60, 60], [14, -14], color=C["coral"], lw=1.4)
    ax.text(62, -14, "RUNNER 60 m", fontsize=6, color=C["coral"], va="center")
    for kind, x, y, lab in L.LONG_TARGETS:
        if kind == "dummy":
            ax.plot(y, -x, "o", ms=4, color=tier_color(lab), mec=C["ink"], mew=0.4, zorder=8)
        else:
            ax.plot(y, -x, "s", ms=3.4, color=C["steel"], zorder=8)
            ax.text(y + 1.5, -x, lab, fontsize=5, va="center", ha="left", zorder=9,
                    bbox=dict(boxstyle="square,pad=0.05", fc=C["field"], ec="none"))
    ax.text(100, -19.5, "HALO GALLERY (11 dummies: none, L T1-T4, M T2-T4, H T3-T4)", fontsize=6, ha="center", va="center")
    ax.text(200, -19.5, "CORE LINE (4 cores, all M T3)", fontsize=6, ha="center", va="center")
    ax.text(300, -19.5, "H T4 + L T1 dummies", fontsize=6, ha="center", va="center")
    ax.set_xlim(-12, 322)
    ax.set_ylim(-24, 24)
    ax.set_aspect("equal")
    metric_grid(ax, 5, 25, fs=6)
    ax.set_xlabel("distance downrange y (m)", fontsize=7)
    ax.set_ylabel("-x (m), west up", fontsize=7)
    ax.set_title("A. Whole range 0-320 m, to scale, rotated 90 deg (downrange to the right). Grid 5 m.",
                 fontsize=9, loc="left")


# ------------------------------------------------------------------ B: close lanes detail
def close_detail(ax):
    rect(ax, (-16.0, 0.0, 16.0, 62.0), fc=C["field"], lw=0.6)
    rect(ax, (-22.0, 0.0, -16.0, 62.0), fc=C["berm"], lw=0.4, hatch="////")
    rect(ax, (16.0, 0.0, 22.0, 62.0), fc=C["berm"], lw=0.4, hatch="////")
    rect(ax, L.DECK, fc=C["deck"], lw=0.8)
    rect(ax, L.DECK_ROOF, fc="none", lw=0.6, ls=(0, (4, 3)))
    rect(ax, L.RANGE_CONTROL, fc="#C9CCD3", lw=0.5, label="RANGE\nCONTROL", fs=6)
    rect(ax, L.RANGE_BOARD, fc=C["ink"], lw=0.2)
    ax.text(-19.3, -5, "RANGE BOARD (8 x 3 m)", rotation=90, fontsize=5.5, ha="left", va="center")
    ax.text(5, -7.5, "WALKWAY  y -10..-4   (roof to y +2 = dashed)", fontsize=6.5, ha="center")
    for xp in L.BAY_PARTITIONS_X:
        rect(ax, (xp - 0.1, -4.0, xp + 0.1, 0.0), fc=C["ink"], lw=0.2)
    for b in L.BAYS:
        xc = b["xc"]
        fb = L.FIRING_BENCH
        rect(ax, (xc + fb[0], fb[1], xc + fb[2], fb[3]), fc=C["bone"], lw=0.4)
        rect(ax, (xc + L.BAY_MONITOR[0] - 0.2, L.BAY_MONITOR[1] - 0.12, xc + L.BAY_MONITOR[0] + 0.2,
                  L.BAY_MONITOR[1] + 0.12), fc=C["ice"], lw=0.3)
        rect(ax, (xc + L.BAY_RACK[0] - 0.4, L.BAY_RACK[1] - 0.25, xc + L.BAY_RACK[0] + 0.4,
                  L.BAY_RACK[1] + 0.25), fc=C["graphite"], lw=0.3)
        ax.plot(xc, -1.6, marker="^", ms=4, color=C["teal"])
        ax.text(xc, -2.6, b["id"], fontsize=7, ha="center", weight="bold")
        tx = xc + L.LANE_TRACK_OFFSET
        rect(ax, (tx - 0.1, L.LANE_TRACK_Y[0], tx + 0.1, L.LANE_TRACK_Y[1]), fc=C["teal"], ec=C["teal"], lw=0.2)
        for d in L.LANE_PRESETS:
            ax.plot([tx - 0.35, tx + 0.35], [d, d], color=C["teal"], lw=1.2)
        circle(ax, tx, 25.0, 0.3, fc=C["T2"], ec=C["ink"], lw=0.4, z=8)
        rx = xc + L.LANE_READOUT[0]
        rect(ax, (rx - 0.6, L.LANE_READOUT[1] - 0.15, rx + 0.6, L.LANE_READOUT[1] + 0.15), fc=C["ice"], lw=0.3)
        px = xc + L.PLATE_STAND_OFFSET
        for d in L.LANE_PLATES:
            rect(ax, (px - 0.25, d - 0.1, px + 0.25, d + 0.1), fc=C["steel"], lw=0.3)
        ax.plot([b["x0"], b["x0"]], [0, 50], color="#00000025", lw=0.6)
    ax.plot([16, 16], [0, 50], color="#00000025", lw=0.6)
    for d in (10, 25, 50):
        ax.plot([-16, 16], [d, d], color=C["ink"], lw=0.4, ls="--")
        ax.text(-16.3, d, f"{d} m", fontsize=6, ha="right", va="center")
    ax.plot([-14, 14], [60, 60], color=C["coral"], lw=2.0)
    circle(ax, 3.0, 60.0, 0.3, fc=C["T2"], ec=C["ink"], lw=0.4, z=8)
    ax.text(0, 61.0, "RUNNER track y = 60 (shared, 28 m, default M T3 Volt)", fontsize=6, ha="center",
            color=C["coral"])
    # recoil lab
    for w in L.RECOIL_WALLS:
        rect(ax, w, fc=C["ink"], lw=0.2)
    rect(ax, (22.3, 0.0, 29.7, 28.0), fc=C["recoil"], lw=0.0)
    for rb in L.RECOIL_BAYS:
        xc = rb["xc"]
        rect(ax, (xc - 0.4, -0.8, xc + 0.4, 0.0), fc=C["bone"], lw=0.3)
        ax.text(xc, -2.6, rb["id"], fontsize=7, ha="center", weight="bold")
        ax.plot(xc, -1.6, marker="^", ms=4, color=C["teal"])
        ax.plot([xc, xc], [8, 27], color=C["coral"], lw=0.6, ls=(0, (2, 2)))
        rect(ax, (xc - 1.5, 14.85, xc + 1.5, 15.15), fc=C["ink"], lw=0.2)
        for s in L.RECOIL_BOARD_STOPS:
            ax.plot([xc - 0.4, xc + 0.4], [s, s], color=C["coral"], lw=1.0)
            ax.text(xc + 0.5, s, f"{s:.0f}", fontsize=5, va="center")
    ax.text(26, 22, "RECOIL LAB\npattern board\n3.0 x 3.4 m\n(default 15 m)", fontsize=6, ha="center", va="center")
    ax.set_xlim(-23, 31)
    ax.set_ylim(-10.5, 63)
    ax.set_aspect("equal")
    metric_grid(ax, 1, 5, fs=6)
    scale_bar(ax, 18.5, 40, 10, fs=5.5, h=0.5)
    ax.set_title("B. Close lanes + Recoil Lab, plan (north up, grid 1 m).\n"
                 "Bay 3.5 m; bench 2.4 x 0.8 m; monitor (ice) at bench right; rack at back right;\n"
                 "lane dummy track 0.4 m left of lane centre (8-50 m, presets 10/25/50);\n"
                 "plate tree 1.2 m right of centre at 10/25/50 m; lane readout at 5 m.", fontsize=8, loc="left")


# ------------------------------------------------------------------ C: target catalogue
def catalogue(ax):
    x = 0.0
    ground = 0.0
    zone_cols = {"Head": "#F2C14E", "Torso": "#E86A5A", "Arms": "#7BB3E0", "Legs": "#8CC084"}
    # dummy with zones
    for zone, parts in L.DUMMY_ZONES.items():
        for shape, cx, cz, w, h in parts:
            if shape == "ellipse":
                ax.add_patch(Ellipse((x + cx, cz), w, h, fc=zone_cols[zone], ec=C["ink"], lw=0.5, zorder=4))
            else:
                ax.add_patch(Rectangle((x + cx - w / 2, cz - h / 2), w, h, fc=zone_cols[zone], ec=C["ink"],
                                       lw=0.5, zorder=4))
    for k, (cls, sc) in enumerate(L.HALO_SCALE.items()):
        pass
    ax.add_patch(Ellipse((x, L.HALO_Z), 2 * L.HALO_RADIUS, 0.06, fc="none", ec=C["T2"], lw=2.0, zorder=5))
    ax.text(x + 0.5, L.HALO_Z, "halo (M scale 1.0,\nr 16 cm, z 1.95 m)", fontsize=5.5, va="center")
    ax.text(x + 0.5, 1.60, "HEAD  22 x 26 cm", fontsize=5.5, va="center")
    ax.text(x + 0.5, 1.25, "TORSO 44 x 65 cm", fontsize=5.5, va="center")
    ax.text(x + 0.5, 1.00, "ARMS  2 x 12 x 62 cm", fontsize=5.5, va="center")
    ax.text(x + 0.5, 0.40, "LEGS  2 x 15 x 82 cm", fontsize=5.5, va="center")
    ax.text(x, -0.18, "HQ-D1 dummy 1.75 m\n(hover sled base, invulnerable)", fontsize=6, ha="center", va="top",
            weight="bold")
    x = 2.6
    for pid in ["P10", "P20", "P30", "P50", "P75", "P100"]:
        shape, w, h = L.PLATES[pid]
        d = w / 100.0
        zc = 1.2
        ax.add_patch(Circle((x, zc), d / 2, fc=C["bone"], ec=C["graphite"], lw=1.2, zorder=4))
        ax.plot([x, x], [0, zc - d / 2], color=C["graphite"], lw=1.2)
        ax.text(x, zc + d / 2 + 0.06, f"{pid}\nO {w} cm", fontsize=5.5, ha="center", va="bottom")
        x += max(0.55, d + 0.35)
    shape, w, h = L.PLATES["TORSO"]
    ax.add_patch(Rectangle((x - 0.225, 0.8), 0.45, 0.6, fc=C["bone"], ec=C["graphite"], lw=1.2, zorder=4))
    ax.plot([x, x], [0, 0.8], color=C["graphite"], lw=1.2)
    ax.text(x, 1.46, "TORSO\n45 x 60 cm", fontsize=5.5, ha="center", va="bottom")
    x += 0.95
    ax.add_patch(Rectangle((x - 0.275, 0.0), 0.55, 1.45, fc=C["bone"], ec=C["graphite"], lw=1.2, zorder=4))
    ax.add_patch(Circle((x, 1.6), 0.11, fc="#E7DDC9", ec=C["graphite"], lw=1.2, zorder=4))
    ax.text(x, 1.78, "SIL 55 x 175 cm\n+ head plate O 22 cm", fontsize=5.5, ha="center", va="bottom")
    ax.axhline(0, color=C["ink"], lw=1.0)
    ax.axhline(L.EYE_HEIGHT, color=C["teal"], lw=0.5, ls=(0, (4, 3)))
    ax.text(x + 0.45, L.EYE_HEIGHT, "eye 1.60", fontsize=5.5, color=C["teal"], va="center")
    ax.set_xlim(-0.6, x + 1.0)
    ax.set_ylim(-0.45, 2.25)
    ax.set_aspect("equal")
    metric_grid(ax, 0.1, 0.5, fs=6)
    ax.set_title("C. Target catalogue, front view, to scale (grid 10 cm). Steel = bone face, graphite rim. "
                 "Plate centre heights: see table.", fontsize=8.5, loc="left")


# ------------------------------------------------------------------ D: angular table
def table(ax):
    ax.axis("off")
    rows = []

    def add(dist, what, size_m, note=""):
        mrad, deg, moa = L.angular(size_m, dist)
        rows.append([f"{dist} m", what, f"{size_m * 100:.0f} cm", f"{mrad:.1f}", f"{deg:.2f}", f"{moa:.1f}", note])

    add(10, "P20 head plate (z 1.60)", 0.20, "per lane")
    add(10, "P10 micro plate (z 1.10)", 0.10, "per lane")
    add(10, "dummy head", 0.22, "lane dummy preset")
    add(25, "P20 head plate (z 1.60)", 0.20, "per lane")
    add(25, "TORSO plate width (z 1.10)", 0.45, "per lane")
    add(25, "dummy head", 0.22, "lane dummy preset")
    add(50, "P30 plate (z 1.60)", 0.30, "per lane")
    add(50, "TORSO plate width (z 1.10)", 0.45, "per lane")
    add(50, "dummy torso width", 0.44, "lane dummy preset")
    add(60, "Runner torso width", 0.44, "shared, 3.0/5.5 m/s")
    add(100, "Gallery dummy head", 0.22, "11 dummies, shared")
    add(100, "P30 / P50 plate", 0.30, "P50 = 5.0 mrad")
    add(200, "Core Line dummy torso", 0.44, "4 dummies, shared")
    add(200, "SIL height", 1.75, "+ P50")
    add(300, "dummy torso", 0.44, "H T4 / L T1")
    add(300, "P75 / P100 plate", 0.75, "P100 = 3.3 mrad")
    cols = ["dist", "target", "size", "mrad", "deg", "MOA", "note"]
    t = ax.table(cellText=rows, colLabels=cols, loc="upper left", cellLoc="left", colLoc="left",
                 colWidths=[0.07, 0.33, 0.09, 0.08, 0.08, 0.08, 0.27])
    t.auto_set_font_size(False)
    t.set_fontsize(6.8)
    t.scale(1, 1.18)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#BBBBBB")
        if r == 0:
            cell.set_facecolor("#E8EAEE")
            cell.set_text_props(weight="bold")
    ax.set_title("D. Angular size from the firing line (eye 1.60 m). For reference: a 1080p screen at 90 deg "
                 "HFOV is ~21 px per degree unzoomed.", fontsize=8.5, loc="left")


def bay_side(ax):
    """Side elevation of one bay (y vs z), to scale: eye line over the bench, readout and plate tree."""
    ax.add_patch(Rectangle((-10, 0), 70, -0.3, fc="#CCCCCC", ec="none"))
    ax.add_patch(Rectangle((-10, 4.0), 12, 0.35, fc=C["deck"], ec=C["ink"], lw=0.6))        # roof y -10..2
    ax.text(-4, 4.18, "deck roof (underside 4.0 m)", fontsize=5.5, ha="center", va="center")
    ax.add_patch(Rectangle((-0.8, 0), 0.8, 0.95, fc=C["bone"], ec=C["ink"], lw=0.6))         # bench
    ax.text(-0.4, 0.45, "bench\n0.95", fontsize=5, ha="center", va="center")
    ax.plot(-1.3, L.EYE_HEIGHT, marker=">", ms=6, color=C["teal"])
    ax.text(-1.5, L.EYE_HEIGHT + 0.15, "eye 1.60", fontsize=5.5, color=C["teal"], ha="right")
    ax.add_patch(Rectangle((L.LANE_READOUT[1] - 0.15, 0), 0.3, L.LANE_READOUT_TOP, fc=C["ice"], ec=C["ink"], lw=0.5))             # readout
    ax.text(L.LANE_READOUT[1], 0.6, "lane readout\n5 m, top 0.45", fontsize=5.5, ha="center", va="bottom")
    for d, plates in L.LANE_PLATES.items():
        if d > 30:
            continue
        ax.plot([d + 0.6, d + 0.6], [0, 1.75], color=C["graphite"], lw=1.0)
        for pid, zc in plates:
            sh, w, h = L.PLATES[pid]
            ax.add_patch(Rectangle((d + 0.5, zc - h / 200), 0.08, h / 100, fc=C["steel"], ec=C["ink"], lw=0.4))
    for d in (8, 10, 25):
        ax.add_patch(Rectangle((d - 0.13, 0), 0.26, 1.47, fc=C["T2"], alpha=0.5, ec=C["ink"], lw=0.4))
        ax.add_patch(Ellipse((d, 1.60), 0.24, 0.26, fc=C["T2"], alpha=0.5, ec=C["ink"], lw=0.4))
        ax.add_patch(Ellipse((d, L.HALO_Z), 0.32, 0.05, fc="none", ec=C["T2"], lw=1.5))
        for zt in (0.0, 1.73):
            ax.plot([-1.3, d], [L.EYE_HEIGHT, zt], color=C["coral"], lw=0.4, ls=(0, (3, 2)))
    ax.text(10, 2.2, "lane dummy @10\n(plate tree 1.2 m to the side)", fontsize=5.5, ha="center", va="bottom")
    ax.text(25, 2.2, "lane dummy @25", fontsize=5.5, ha="center", va="bottom")
    ax.set_xlim(-6, 27)
    ax.set_ylim(-0.3, 4.6)
    ax.set_aspect("equal")
    metric_grid(ax, 0.5, 1, label_every=5, fs=6)
    ax.set_xlabel("y (m) downrange", fontsize=6)
    ax.set_title("E. Bay side elevation, to scale: the readout (top 0.45 m) stays under the sightline to the feet of a "
                 "dummy at 8 m (closest stop) and beyond.", fontsize=8.5, loc="left")


def main():
    fig = plt.figure(figsize=(20, 17))
    gs = GridSpec(2, 2, height_ratios=[0.36, 2.4], width_ratios=[0.9, 1.1], hspace=0.12, wspace=0.08,
                  figure=fig)
    strip(fig.add_subplot(gs[0, :]))
    close_detail(fig.add_subplot(gs[1, 0]))
    sub = gs[1, 1].subgridspec(3, 1, height_ratios=[0.85, 0.62, 1.3], hspace=0.3)
    axc = fig.add_subplot(sub[0])
    catalogue(axc)
    axc.set_anchor("N")
    axe = fig.add_subplot(sub[1])
    bay_side(axe)
    axe.set_anchor("N")
    table(fig.add_subplot(sub[2]))
    fig.canvas.draw()
    fig.text(0.125, 0.905, "RANGE: lanes and targets (metres, to scale)", fontsize=15, weight="bold", ha="left")
    save(fig, os.path.join(HERE, "range_lanes_targets.png"))


if __name__ == "__main__":
    main()
