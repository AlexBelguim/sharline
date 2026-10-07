"""Detailed diagram of the AIM LAB ("Reflex Hall"): plan to scale + per-mode front/side views.

Run:  python draw_aimlab.py      -> aimlab_layout.png
"""
import os
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.patches import FancyBboxPatch

import layout_data as L
from draw_common import C, rect, circle, metric_grid, scale_bar, save

HERE = os.path.dirname(os.path.abspath(__file__))
PAD_Y = L.AIM_PAD_Y


def dim(ax, x0, y0, x1, y1, text, fs=6, off=(0, 0), color=None, rot=0):
    color = color or C["ink"]
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="<->", lw=0.6, color=color, shrinkA=0, shrinkB=0), zorder=15)
    ax.text((x0 + x1) / 2 + off[0], (y0 + y1) / 2 + off[1], text, fontsize=fs, ha="center", va="center",
            color=color, rotation=rot, zorder=16, bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none",
                                                            alpha=0.85))


def plan(ax):
    rect(ax, L.AIM_HALL, fc=C["aim"], lw=1.4)
    rect(ax, L.AIM_CONCOURSE, fc="#EEF3F7", lw=0.5)
    rect(ax, L.AIM_CORRIDOR, fc=C["aim"], lw=0.8, label="to READY ROOM\n(W door)", fs=6)
    ax.text(-48, -18.3, "CONCOURSE (6 m) - spectators walk here; bay boards hang above each bay entrance",
            fontsize=7, ha="center", va="center")
    for xp in L.AIM_PARTITIONS_X:
        rect(ax, (xp - 0.15, -14.0, xp + 0.15, 18.0), fc=C["ink"], lw=0.2)
    rect(ax, (-72.0, 17.7, -24.0, 18.0), fc=C["ink"], lw=0.2)
    for b in L.AIM_BAYS:
        x0 = b["x0"]
        m = b["mode"]
        ax.text(x0 + 6, 16.6, f"{m} BAY", fontsize=8, ha="center", va="center", weight="bold", zorder=12,
                bbox=dict(boxstyle="square,pad=0.2", fc=C["aim"], ec="none"))
        # glass divider between booths
        rect(ax, (x0 + 5.95, -12.0, x0 + 6.05, 18.0), fc=C["glass"], ec=C["glass"], lw=0.6)
        # board above the entrance
        bx = (x0 + L.AIM_BOARD[0], L.AIM_BOARD[1], x0 + L.AIM_BOARD[2], L.AIM_BOARD[3])
        rect(ax, bx, fc=C["ink"], lw=0.2)
        ax.text(x0 + 6, -14.7, "BAY BOARD 8 x 2.2 m, double-sided, z 3.0-5.2", fontsize=5, ha="center",
                va="center")
        # spectator rail with gaps
        for seg in [(x0 + 0.3, x0 + 2.0), (x0 + 4.0, x0 + 8.0), (x0 + 10.0, x0 + 11.7)]:
            ax.plot(seg, [L.AIM_RAIL_Y] * 2, color=C["ink"], lw=1.4, zorder=6)
        for bid, xb in b["booths"].items():
            s = L.AIM_PAD_SIZE / 2
            rect(ax, (xb - s, PAD_Y - s, xb + s, PAD_Y + s), fc=C["teal"], alpha=0.5, ec=C["teal"], lw=1.0)
            ax.text(xb, PAD_Y, f"PAD\n{m[0]}{bid}", fontsize=5.5, ha="center", va="center", zorder=9)
            cx, cy = xb + L.AIM_PAD_CONSOLE[0], PAD_Y + L.AIM_PAD_CONSOLE[1]
            rect(ax, (cx - 0.25, cy - 0.2, cx + 0.25, cy + 0.2), fc=C["ice"], lw=0.4)
            if m == "GRIDSHOT":
                g = L.GRID
                rect(ax, (xb + g["backing"][0], g["backing"][1], xb + g["backing"][2], g["backing"][3]),
                     fc=C["graphite"], lw=0.2)
                for dx in g["cols_dx"]:
                    circle(ax, xb + dx, g["plane_y"], g["target_d"] / 2, fc=C["coral"], ec=C["coral"], lw=0.3)
                dim(ax, xb - 2.2, PAD_Y, xb - 2.2, g["plane_y"], "10 m", rot=90)
            elif m == "TRACKING":
                t = L.TRACK
                ax.plot([xb - t["half_range"], xb + t["half_range"]], [t["band_y"]] * 2, color=C["coral"], lw=3,
                        alpha=0.4, zorder=6, solid_capstyle="butt")
                circle(ax, xb + 0.8, t["band_y"], t["bot_d"] / 2, fc=C["coral"], ec=C["ink"], lw=0.4)
                dim(ax, xb - 2.2, PAD_Y, xb - 2.2, t["band_y"], "14 m", rot=90)
                dim(ax, xb - t["half_range"], t["band_y"] + 1.2, xb + t["half_range"], t["band_y"] + 1.2,
                    "4.8 m strafe band")
            elif m == "REACTION":
                r_ = L.REACT
                rect(ax, (xb - r_["half_w"], r_["panel_y"] - 0.15, xb + r_["half_w"], r_["panel_y"] + 0.15),
                     fc=C["coral"], lw=0.3)
                dim(ax, xb - 2.4, PAD_Y, xb - 2.4, r_["panel_y"], "8 m", rot=90)
            elif m == "PRECISION":
                p = L.PRECISION
                for ry in p["rails_y"]:
                    rect(ax, (xb - p["rail_half_w"], ry - 0.15, xb + p["rail_half_w"], ry + 0.15),
                         fc=C["graphite"], lw=0.2)
                    ax.text(xb, ry + 0.55, f"{ry - PAD_Y:.0f} m from pad", fontsize=5.5, ha="center", va="bottom",
                            bbox=dict(boxstyle="square,pad=0.1", fc=C["aim"], ec="none"))
                for (hx, hy) in [(xb - 1.0, 10.0), (xb + 0.6, 15.0)]:
                    circle(ax, hx, hy + 0.35, 0.11, fc=C["coral"], ec=C["coral"])
    # entrance arrow
    ax.annotate("", xy=(-26, -17.5), xytext=(-20.5, -17.5), arrowprops=dict(arrowstyle="->", lw=1.2), zorder=20)
    ax.set_xlim(-73, -17)
    ax.set_ylim(-21, 19)
    ax.set_aspect("equal")
    metric_grid(ax, 1, 5, fs=7)
    scale_bar(ax, -71.5, -20.6, 5, fs=6, h=0.3)
    ax.set_title("A. AIM LAB plan, to scale (grid 1 m, labels every 5 m). Shooting direction = north (+Y). "
                 "Pads at y = -10; pad 1.6 x 1.6 m; pad console (ice) 1.3 m right of the pad.", fontsize=9,
                 loc="left")


def front_axes(ax, title, xlim=(-3.1, 3.1), zlim=(0, 3.6)):
    ax.set_xlim(*xlim)
    ax.set_ylim(*zlim)
    ax.set_aspect("equal")
    metric_grid(ax, 0.25, 0.5, fs=6)
    ax.axhline(0, color=C["ink"], lw=1.0)
    ax.axhline(L.EYE_HEIGHT, color=C["teal"], lw=0.6, ls=(0, (4, 3)))
    ax.text(xlim[0] + 0.05, L.EYE_HEIGHT + 0.05, "eye 1.60 m", fontsize=5.5, color=C["teal"], va="bottom")
    ax.set_title(title, fontsize=8, loc="left")
    ax.set_xlabel("x from booth centre (m)", fontsize=6)
    ax.set_ylabel("height z (m)", fontsize=6)


def gridshot_front(ax):
    g = L.GRID
    front_axes(ax, "B. GRIDSHOT front view at 10 m\n5 x 3 cells, pitch 1.0 m (5.7 deg), target 40 cm (2.3 deg)")
    rect(ax, (g["backing"][0], g["backing_z"][0], g["backing"][2], g["backing_z"][1]), fc=C["graphite"], lw=0.4)
    live = {(0, 2), (2, 1), (4, 0)}
    for i, dx in enumerate(g["cols_dx"]):
        for j, z in enumerate(g["rows_z"]):
            on = (i, j) in live
            circle(ax, dx, z, g["target_d"] / 2, fc=C["coral"] if on else "none",
                   ec=C["coral"] if on else "#8A9099", lw=0.8, ls="-" if on else (0, (2, 2)), z=5)
    dim(ax, -2.0, 3.25, 2.0, 3.25, "4.0 m (+/-11.3 deg)", fs=5.5)
    ax.text(0, 0.08, "3 live targets (filled); dashed = free cells", fontsize=5.5, ha="center", va="bottom",
            color="white")


def tracking_front(ax):
    t = L.TRACK
    front_axes(ax, "C. TRACKING front view at 14 m\nbot 50 cm wide (2.0 deg), head 25 cm (1.0 deg), band +/-2.4 m")
    x = 0.8
    rect(ax, (x - t["bot_d"] / 2, 0.0, x + t["bot_d"] / 2, 1.45), fc=C["coral"], lw=0.5, z=5)
    circle(ax, x, 1.60, t["head_d"] / 2, fc="#FFB0A6", ec=C["ink"], lw=0.5, z=6)
    ax.plot([-2.4, 2.4], [0.02, 0.02], color=C["coral"], lw=4, alpha=0.4)
    ax.annotate("", xy=(2.2, 0.9), xytext=(1.2, 0.9), arrowprops=dict(arrowstyle="->", lw=1.0))
    ax.annotate("", xy=(-0.6, 0.9), xytext=(0.4, 0.9), arrowprops=dict(arrowstyle="->", lw=1.0))
    ax.text(0.8, 2.15, "speed 3.0-6.0 m/s\nreverse every 0.25-1.0 s\nhop 0.6 m every 3-6 s", fontsize=5.5,
            ha="center", va="bottom")
    dim(ax, -2.4, 3.25, 2.4, 3.25, "4.8 m (+/-9.7 deg)", fs=5.5)


def reaction_front(ax):
    r_ = L.REACT
    front_axes(ax, "D. REACTION front view at 8 m\npanel 4.0 x 2.4 m (28 x 17 deg)")
    rect(ax, (-r_["half_w"], r_["z"][0], r_["half_w"], r_["z"][1]), fc=C["teal"], alpha=0.85, lw=0.6, z=5)
    ax.text(0, 1.6, "WAIT (bone)  ->  GO (teal flash)\nshoot anywhere on the panel", fontsize=6,
            ha="center", va="center", color="white", zorder=8)
    dim(ax, -2.0, 3.1, 2.0, 3.1, "4.0 m", fs=5.5)


def precision_side(ax):
    p = L.PRECISION
    ax.set_xlim(-1, 27)
    ax.set_ylim(0, 3.0)
    ax.set_aspect(3.0)
    metric_grid(ax, 0.5, 5, fs=6)
    ax.yaxis.set_major_locator(__import__("matplotlib").ticker.MultipleLocator(0.5))
    ax.axhline(0, color=C["ink"], lw=1.0)
    ax.set_title("E. PRECISION side view (distance from pad vs height); rails 1.0 m tall at 15/20/25 m,\n"
                 "head 22 cm: 0.84 deg at 15 m, 0.63 deg at 20 m, 0.50 deg at 25 m; stand 1.60 m / crouch 1.20 m (vertical scale x3)",
                 fontsize=8, loc="left")
    ax.set_xlabel("distance from pad (m)", fontsize=6)
    ax.set_ylabel("z (m)", fontsize=6)
    ax.plot(0, L.EYE_HEIGHT, marker=">", ms=6, color=C["teal"])
    ax.text(0.2, L.EYE_HEIGHT + 0.15, "eye 1.60 m", fontsize=5.5, color=C["teal"])
    for ry in p["rails_y"]:
        d = ry - PAD_Y
        rect(ax, (d - 0.15, 0, d + 0.15, p["rail_h"]), fc=C["graphite"], lw=0.3)
        for kind, zh in p["head_z"].items():
            circle(ax, d + 0.35, zh, p["head_d"] / 2, fc=C["coral"] if kind == "stand" else "#FFB0A6",
                   ec=C["ink"], lw=0.3, z=6)
            ax.plot([0, d + 0.35], [L.EYE_HEIGHT, zh], color=C["coral"], lw=0.3, ls=(0, (3, 3)))
    rect(ax, (25.6, 0, 25.9, 3.0), fc=C["ink"], lw=0.2)
    ax.text(24.0, 2.7, "head busts pop up behind the rails;\nbody/shoulder hits = penalty", fontsize=5.5,
            ha="right", va="top")


def main():
    fig = plt.figure(figsize=(18, 17))
    gs = GridSpec(3, 3, height_ratios=[2.25, 1.0, 0.62], hspace=0.28, wspace=0.12, figure=fig)
    plan(fig.add_subplot(gs[0, :]))
    gridshot_front(fig.add_subplot(gs[1, 0]))
    tracking_front(fig.add_subplot(gs[1, 1]))
    reaction_front(fig.add_subplot(gs[1, 2]))
    precision_side(fig.add_subplot(gs[2, :2]))
    axn = fig.add_subplot(gs[2, 2])
    axn.axis("off")
    notes = ("Every booth = 1 start pad. Walk onto the pad, press E to start (3 s countdown,\n"
             "movement locked, look free). Hold E 0.6 s = abort. Hold E on the console = options.\n"
             "Timers: GRIDSHOT 60 s, TRACKING 45 s, REACTION 45 s, PRECISION 45 s.\n"
             "Targets are per player (owner's shots only); friends see them via relayed events.\n"
             "Booth A and B of one bay can start together = head-to-head (shared countdown).\n"
             "All angular sizes are from the pad's eye point (1.60 m).")
    axn.text(0, 1, notes, fontsize=7.5, va="top", ha="left", transform=axn.transAxes,
             bbox=dict(boxstyle="round,pad=0.5", fc="#F6F7F9", ec=C["ink"], lw=0.5))
    fig.canvas.draw()
    fig.text(0.125, 0.905, "AIM LAB (Reflex Hall): 4 mode bays x 2 booths - exact layout and target geometry",
             fontsize=14, weight="bold", ha="left")
    save(fig, os.path.join(HERE, "aimlab_layout.png"))


if __name__ == "__main__":
    main()
