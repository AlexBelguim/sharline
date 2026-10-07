"""Top-down site layout of the Range / HQ training map, to scale, with a metric grid.

Run:  python draw_site_layout.py      -> site_layout.png (next to this script)
"""
import os
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D

import layout_data as L
from draw_common import C, TIER_COLORS, rect, circle, metric_grid, scale_bar, north_arrow, save

HERE = os.path.dirname(os.path.abspath(__file__))


def draw_sections(ax, detail):
    """Draw every section. detail=True adds interior items (used for the core-area panel)."""
    fs_sec = 9 if detail else 7
    # terrain / range field
    rect(ax, L.FIELD, fc=C["field"], lw=0.8)
    rect(ax, L.BERM_W, fc=C["berm"], hatch="////" if detail else None, lw=0.6)
    rect(ax, L.BERM_E, fc=C["berm"], hatch="////" if detail else None, lw=0.6)
    rect(ax, L.BACKSTOP, fc=C["backstop"], lw=0.8, label=None if detail else "BACKSTOP BERM 10 m", fs=6)
    if not detail:
        ax.text(-19, 150, "SIDE BERM 4 m", rotation=90, fontsize=6, ha="center", va="center")
        ax.text(19, 150, "SIDE BERM 4 m", rotation=90, fontsize=6, ha="center", va="center")
        ax.text(0, 160, "RANGE FIELD\n32 m wide", fontsize=7, ha="center", va="center", weight="bold")
    # distance lines
    for d in L.DISTANCE_LINES:
        if detail and d > 32:
            continue
        ax.plot([-16, 16], [d, d], color=C["ink"], lw=0.5, ls="--", zorder=3)
        ax.text(-16.5, d, f"{d} m", fontsize=6 if detail else 6, ha="right", va="center", zorder=6)
    # deck + roof
    rect(ax, L.DECK, fc=C["deck"], lw=1.0)
    rect(ax, L.DECK_ROOF, fc="none", ec=C["ink"], lw=0.6, ls=(0, (4, 3)))
    rect(ax, L.RANGE_CONTROL, fc="#C9CCD3", lw=0.6, label="RANGE\nCONTROL" if detail else None, fs=6)
    # ready room
    rect(ax, L.READY_ROOM, fc=C["ready"], lw=1.2,
         label=None if detail else "READY\nROOM", fs=fs_sec, weight="bold")
    # aim lab
    rect(ax, L.AIM_HALL, fc=C["aim"], lw=1.2,
         label=None if detail else "AIM LAB", fs=fs_sec, weight="bold")
    rect(ax, L.AIM_CORRIDOR, fc=C["aim"], lw=0.8)
    # recoil lab lanes
    rect(ax, (22.0, 0.0, 30.0, 28.0), fc=C["recoil"], lw=0.6)
    for w in L.RECOIL_WALLS:
        rect(ax, w, fc=C["ink"], lw=0.3)
    # course
    rect(ax, L.COURSE_AREA, fc="#EEF7F5", ec=C["teal"], lw=0.8, ls=(0, (6, 3)))
    for p in L.COURSE_PATH:
        rect(ax, p, fc=C["path"], lw=0.5)
    for name, r, z0, z1, note in L.COURSE:
        fc = C["course"]
        if "WALL" in name or "TOWER" in name:
            fc = "#9FD8CC"
        if "pit" in name:
            fc = "#F3F3F3"
        rect(ax, r, fc=fc, lw=0.6)
    if not detail:
        ax.text(65, -4, "MOVEMENT\nCOURSE", fontsize=fs_sec, ha="center", va="center", weight="bold")
        ax.text(26, 33, "RECOIL\nLAB", fontsize=6, ha="center", va="bottom")
        ax.text(5, -8.5, "RANGE DECK", fontsize=6, ha="center", va="center")
    # long-range targets
    for kind, x, y, lab in L.LONG_TARGETS:
        if detail and y > 32:
            continue
        if kind == "dummy":
            t = L.tier_of(lab)
            col = TIER_COLORS[t - 1] if t else "white"
            ax.plot(x, y, "o", ms=2.6, color=col, mec=C["ink"], mew=0.3, zorder=7)
        else:
            ax.plot(x, y, "s", ms=2.2, color=C["steel"], zorder=7)
    if not detail:
        ax.text(0, 107, "100 m  HALO GALLERY (11 dummies) + plates", fontsize=5.5, ha="center", va="bottom")
        ax.text(0, 207, "200 m  CORE LINE (4 dummies) + plates", fontsize=5.5, ha="center", va="bottom")
        ax.text(0, 288, "300 m  2 dummies + 3 plates", fontsize=5.5, ha="center", va="top")
        ax.plot([-14, 14], [60, 60], color=C["coral"], lw=1.0, zorder=6)
        ax.text(0, 63, "60 m RUNNER track", fontsize=5.5, ha="center", va="bottom", color=C["coral"])


def draw_detail_items(ax):
    # ---- Ready Room interior
    rect(ax, L.SPAWN_STRIP, fc="#F7F3EA", lw=0.4, ls=(0, (3, 2)))
    for i, (x, y) in enumerate(L.SPAWNS):
        ax.plot(x, y, marker="^", ms=4.5, color=C["teal"], zorder=8)
    ax.text(0, -39.3, "SPAWN SP1-SP10 (3 m apart, facing N)", fontsize=6, ha="center", va="center")
    x, y, r = L.OPS_TABLE
    circle(ax, x, y, r, fc="#CBC2AE", lw=1.0)
    circle(ax, x, y, L.OPS_INTERACT_RADIUS, ls=(0, (2, 2)), lw=0.5)
    ax.text(x, y, "OPS TABLE\nmatch terminal", fontsize=6, ha="center", va="center", zorder=9)
    for name, r_ in L.TEAM_PADS.items():
        col = C["teal"] if "A" in name.split()[1] else C["coral"]
        rect(ax, r_, fc=col, alpha=0.35, ec=col, lw=1.0, label=name.replace(" (", "\n("), fs=6)
    rect(ax, L.WEAPON_WALL, fc=C["graphite"], lw=0.3)
    ax.text(-16.6, -29, "WEAPON WALL", rotation=90, fontsize=5.5, ha="center", va="center")
    for name, r_ in L.LOADOUT_BENCHES.items():
        rect(ax, r_, fc=C["bone"], lw=0.6, label=f"BENCH\n{name}", fs=5, rot=90)
    for (bx, by) in L.BENCH_SPOTS:
        ax.plot(bx, by, "o", ms=2.0, color=C["teal"], zorder=8)
    rect(ax, L.HALO_WALL, fc=C["graphite"], lw=0.3)
    ax.text(16.6 + 0.3, -29, "HALO WALL", rotation=90, fontsize=5.5, ha="center", va="center")
    for name, (mx, my) in L.MANNEQUINS.items():
        circle(ax, mx, my, 0.6, fc=C["bone"], lw=0.6)
        ax.text(mx - 1.0, my, name[0], fontsize=6, ha="center", va="center")
    rect(ax, L.FITTING_PAD, fc=C["teal"], alpha=0.25, ec=C["teal"], lw=0.8, label="FITTING\nMIRROR", fs=5.5)
    for name, r_ in L.HALL_BOARDS.items():
        rect(ax, r_, fc=C["ink"], lw=0.3)
        ax.text((r_[0] + r_[2]) / 2, r_[1] - 0.8, f"HALL BOARD: {name}", fontsize=5, ha="center", va="top")
    ax.text(0, -33.2, "READY ROOM  36 x 30 m", fontsize=8, ha="center", va="center", weight="bold")
    # doors
    for name, (x0, y0, x1, y1) in L.READY_DOORS.items():
        ax.plot([x0, x1], [y0, y1], color="white", lw=3.0, zorder=9, solid_capstyle="butt")
    # ---- Deck: bays, benches, monitors, racks
    for xp in L.BAY_PARTITIONS_X:
        rect(ax, (xp - 0.1, -4.0, xp + 0.1, 0.0), fc=C["ink"], lw=0.2)
    for b in L.BAYS:
        xc = b["xc"]
        fb = L.FIRING_BENCH
        rect(ax, (xc + fb[0], fb[1], xc + fb[2], fb[3]), fc=C["bone"], lw=0.4)
        ax.plot(xc + L.BAY_MONITOR[0], L.BAY_MONITOR[1], "s", ms=2.2, color=C["ice"], mec=C["ink"], mew=0.3,
                zorder=8)
        ax.plot(xc + L.BAY_RACK[0], L.BAY_RACK[1], "s", ms=2.2, color=C["graphite"], zorder=8)
        ax.text(xc, -2.6, b["id"], fontsize=6, ha="center", va="center", weight="bold")
        # lane track and readout / plates (only near part visible in this panel)
        tx = xc + L.LANE_TRACK_OFFSET
        ax.plot([tx, tx], list(L.LANE_TRACK_Y), color=C["teal"], lw=0.8, zorder=5)
        ax.plot(xc + L.LANE_READOUT[0], L.LANE_READOUT[1], "s", ms=2.0, color=C["ice"], zorder=7)
        for d in L.LANE_PLATES:
            ax.plot(xc + L.PLATE_STAND_OFFSET, d, "s", ms=2.0, color=C["steel"], zorder=7)
        ax.plot(tx, 25, "o", ms=3.0, color=C["T2"], mec=C["ink"], mew=0.3, zorder=8)
    rect(ax, L.RANGE_BOARD, fc=C["ink"], lw=0.3)
    ax.text(-19.2, -5, "RANGE BOARD", rotation=90, fontsize=5, ha="left", va="center")
    ax.text(-1.0, -7.2, "RANGE DECK  (bays B1-B8, 3.5 m each; walkway y -10..-4)", fontsize=6.5, ha="center",
            va="center", weight="bold")
    ax.text(0, 29.0, "CLOSE LANES: per-lane dummy track 8-50 m (teal), plate trees at 10/25/50 m (grey)",
            fontsize=6, ha="center", va="center")
    # recoil lab
    for rb in L.RECOIL_BAYS:
        ax.text(rb["xc"], -2.4, rb["id"], fontsize=6, ha="center", va="center", weight="bold")
        rect(ax, (rb["xc"] - 0.4, -0.8, rb["xc"] + 0.4, 0.0), fc=C["bone"], lw=0.4)
        ax.plot([rb["xc"], rb["xc"]], [8, 27], color=C["coral"], lw=0.6, ls=(0, (2, 2)), zorder=5)
        rect(ax, (rb["xc"] - 1.5, 14.85, rb["xc"] + 1.5, 15.15), fc=C["ink"], lw=0.3)
        for s in L.RECOIL_BOARD_STOPS:
            ax.plot([rb["xc"] - 0.25, rb["xc"] + 0.25], [s, s], color=C["coral"], lw=0.8, zorder=6)
    ax.text(26.0, 20.5, "RECOIL\nLAB\nboard\n10/15/25 m", fontsize=5.5, ha="center", va="center")
    # ---- Aim lab
    for i, b in enumerate(L.AIM_BAYS):
        x0 = b["x0"]
        ax.text(x0 + 6, 16.2, b["mode"], fontsize=7, ha="center", va="center", weight="bold", zorder=12,
                bbox=dict(boxstyle="square,pad=0.2", fc=C["aim"], ec="none"))
        rect(ax, (x0 + L.AIM_BOARD[0], L.AIM_BOARD[1], x0 + L.AIM_BOARD[2], L.AIM_BOARD[3]), fc=C["ink"], lw=0.2)
        ax.plot([x0 + 6, x0 + 6], [-12, 18], color=C["glass"], lw=1.4, zorder=4)
        for bid, xb in b["booths"].items():
            s = L.AIM_PAD_SIZE / 2
            rect(ax, (xb - s, L.AIM_PAD_Y - s, xb + s, L.AIM_PAD_Y + s), fc=C["teal"], alpha=0.45, ec=C["teal"])
            ax.text(xb, L.AIM_PAD_Y - 1.5, bid, fontsize=5.5, ha="center", va="center")
            m = b["mode"]
            if m == "GRIDSHOT":
                g = L.GRID
                rect(ax, (xb + g["backing"][0], g["backing"][1], xb + g["backing"][2], g["backing"][3]),
                     fc=C["graphite"], lw=0.2)
                for dx in g["cols_dx"]:
                    ax.plot(xb + dx, g["plane_y"], "o", ms=2.0, color=C["coral"], zorder=8)
            elif m == "TRACKING":
                t = L.TRACK
                ax.plot([xb - t["half_range"], xb + t["half_range"]], [t["band_y"]] * 2, color=C["coral"],
                        lw=2.0, zorder=6)
            elif m == "REACTION":
                r_ = L.REACT
                rect(ax, (xb - r_["half_w"], r_["panel_y"] - 0.15, xb + r_["half_w"], r_["panel_y"] + 0.15),
                     fc=C["coral"], lw=0.3)
            elif m == "PRECISION":
                p = L.PRECISION
                for ry in p["rails_y"]:
                    rect(ax, (xb - p["rail_half_w"], ry - 0.15, xb + p["rail_half_w"], ry + 0.15),
                         fc=C["graphite"], lw=0.2)
        # rail with gaps
        for seg in [(x0 + 0.3, x0 + 2.0), (x0 + 4.0, x0 + 8.0), (x0 + 10.0, x0 + 11.7)]:
            ax.plot(seg, [L.AIM_RAIL_Y] * 2, color=C["ink"], lw=1.0, zorder=6)
    for xp in L.AIM_PARTITIONS_X:
        rect(ax, (xp - 0.15, -14.0, xp + 0.15, 18.0), fc=C["ink"], lw=0.2)
    rect(ax, L.AIM_CONCOURSE, fc="#EEF3F7", lw=0.4, label="AIM LAB CONCOURSE  (48 x 38 m hall)", fs=7,
         weight="bold")
    # ---- Course details
    for name, r_, h in L.MANTLE_WALLS + [L.SLIDE_GATE, L.FINAL_BOX]:
        rect(ax, r_, fc=C["teal"], lw=0.3)
        ax.text((r_[0] + r_[2]) / 2, r_[3] + 0.4 if r_[3] < 0 else r_[1] - 0.4, name, fontsize=5, ha="center",
                va="bottom" if r_[3] < 0 else "top", rotation=0, zorder=9)
    rect(ax, L.START_GRID, fc=C["teal"], alpha=0.35, ec=C["teal"], lw=0.8)
    for sx, sy in L.START_SPOTS:
        ax.plot(sx, sy, marker="^", ms=3.5, color=C["teal"], zorder=8)
    ax.text(42, -51.2, "START GRID (4 racers)", fontsize=5.5, ha="center", va="center")
    for name, r_, z0, z1, note in L.COURSE:
        if name in ("CORNER",):
            continue
        cx, cy = (r_[0] + r_[2]) / 2, (r_[1] + r_[3]) / 2
        lab = name if not note else f"{name}\n{note}"
        if name.startswith("S2 PLATFORM") or name == "START GATE":
            continue
        rot = 90 if (r_[3] - r_[1]) > (r_[2] - r_[0]) * 1.4 else 0
        if name == "S6 FINAL LANE":
            cy = r_[1] + 1.5
        if name.startswith("S3") or name.startswith("S4"):
            ax.text(cx, 24.5 if name.startswith("S4 JET GAP") else 22.6, f"{name}: {note}" if note else name, fontsize=5,
                    ha="center", va="bottom", rotation=0, zorder=9,
                    bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none", alpha=0.85))
            continue
        ax.text(cx, cy, lab, fontsize=5.3, ha="center", va="center", rotation=rot, zorder=9)
    (x0, y0, z0), (x1, y1, z1) = L.ZIPLINE
    ax.plot([x0, x1], [y0, y1], color=C["coral"], lw=1.4, zorder=9)
    ax.text(x0 + 1.2, (y0 + y1) / 2, f"S5 ZIPLINE {L.zipline_length():.1f} m\nz {z0} -> {z1} m",
            fontsize=5.5, ha="left", va="center", rotation=90, color=C["coral"])
    for name, (a, b_, c, d) in L.CHECKPOINTS.items():
        ax.plot([a, c], [b_, d], color=C["coral"], lw=1.6, zorder=10)
        ax.text(c + 0.6 if a == c else c + 0.4, d + 0.4, name, fontsize=5.5, color=C["coral"], weight="bold",
                zorder=10)
    ax.text(34, -32, "PATH", rotation=90, fontsize=5.5, ha="center", va="center")


def main():
    fig = plt.figure(figsize=(23, 14))
    gs = GridSpec(2, 2, width_ratios=[1.0, 2.35], height_ratios=[1.0, 0.42], wspace=0.06, hspace=0.12, figure=fig)
    # ---- Panel A: whole site
    axA = fig.add_subplot(gs[:, 0])
    draw_sections(axA, detail=False)
    xmin, ymin, xmax, ymax = L.SITE_BOUNDS
    axA.set_xlim(xmin, xmax)
    axA.set_ylim(ymin, ymax)
    axA.set_aspect("equal")
    metric_grid(axA, 10, 50, fs=7)
    axA.set_title("A. Whole site, to scale (grid 10 m, labels every 50 m)", fontsize=10, loc="left")
    rect(axA, (-76, -56, 101, 32), fc="none", ec=C["coral"], lw=1.0, ls=(0, (5, 3)))
    axA.text(-76, 34, "panel B", fontsize=7, color=C["coral"], va="bottom")
    north_arrow(axA, 75, 230, 30, fs=7)
    scale_bar(axA, 40, 120, 50, fs=7, h=3)
    # ---- Panel B: core area
    axB = fig.add_subplot(gs[0, 1])
    draw_sections(axB, detail=True)
    draw_detail_items(axB)
    axB.set_xlim(-76, 101)
    axB.set_ylim(-56, 32)
    axB.set_aspect("equal")
    metric_grid(axB, 2, 10, fs=7)
    axB.set_title("B. Core area: Ready Room, Range Deck, close lanes, Recoil Lab, Aim Lab, Movement Course "
                  "(grid 2 m, labels every 10 m)", fontsize=10, loc="left")
    scale_bar(axB, -70, 24, 20, fs=6, h=0.8)
    # ---- Panel C: legend / key numbers
    axC = fig.add_subplot(gs[1, 1])
    axC.axis("off")
    rows = [
        ("Origin (0,0,0)", "centre of the firing line (front edge of the bay benches), floor level. X east, Y north "
                           "(shooting direction), Z up = Blender axes. Bevy: (x, y, z) = (X, Z, -Y)."),
        ("READY ROOM", "x -18..18, y -40..-10 (36 x 30 m, 6 m high). 10 spawns, Ops Table, 2 team pads, "
                       "2 loadout benches, Fitting Mirror, Weapon/Halo walls, 2 Hall Boards."),
        ("RANGE DECK", "x -20..30, y -10..0, roof to y +2 (underside 4 m). 8 bays x 3.5 m (B1-B8, x -14..14), "
                       "Range Control alcove x 14..22, Recoil bays R1/R2 x 22..30."),
        ("RANGE FIELD", "x -16..16 (32 m), y 0..305, side berms 4 m, backstop y 305..320 (10 m). Lane dummies "
                        "8-50 m, plate trees 10/25/50 m, Runner 60 m, Halo Gallery 100 m, Core Line 200 m, 300 m line."),
        ("RECOIL LAB", "2 enclosed lanes x 22..30, y 0..28, walls 4.0 m. Pattern board 3.0 x 3.4 m on a carriage, "
                       "stops at 10/15/25 m."),
        ("AIM LAB", "x -72..-24, y -20..18 (48 x 38 m). 4 mode bays x 12 m, 2 booths each (A/B, glass divider). "
                    "Pads at y -10. Corridor x -24..-18 to the Ready Room."),
        ("MOVEMENT COURSE", f"x 32..97, y -52..22. ~213 m loop: sprint, slide, 3 mantles, jet wall 5 m, 10 m jet gap, "
                            f"tower 6 m, zipline {L.zipline_length():.0f} m, slide gate, finish. CP1-CP4 + finish."),
        ("Walking times", "spawn -> firing bay ~30 m, spawn -> aim pad 40-65 m, spawn -> course start ~75 m "
                          "(about 4-11 s at sprint). Optional fast travel via the hub map (open question)."),
    ]
    y = 0.98
    for k, v in rows:
        axC.text(0.0, y, k, fontsize=8.5, weight="bold", va="top", transform=axC.transAxes)
        axC.text(0.14, y, v, fontsize=8.5, va="top", transform=axC.transAxes, wrap=True)
        y -= 0.105
    handles = [
        Line2D([0], [0], marker="^", color="w", markerfacecolor=C["teal"], ms=8, label="spawn / start spot"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C["T2"], ms=7, label="halo dummy (colour = tier)"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=C["steel"], ms=7, label="steel plate"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor=C["ice"], ms=7, label="screen / readout"),
        Line2D([0], [0], color=C["teal"], lw=2, label="lane dummy track"),
        Line2D([0], [0], color=C["coral"], lw=2, label="checkpoint / zipline / target zone"),
    ]
    axC.legend(handles=handles, loc="upper right", bbox_to_anchor=(1.0, 0.08), fontsize=8, frameon=True, ncol=6)
    fig.canvas.draw()
    top = max(axA.get_position().y1, axB.get_position().y1)
    fig.text(axA.get_position().x0, top + 0.03, "THE YARD - HQ training range: top-down site layout "
             "(metres, to scale)", fontsize=15, weight="bold", ha="left", va="bottom")
    save(fig, os.path.join(HERE, "site_layout.png"))


if __name__ == "__main__":
    main()
