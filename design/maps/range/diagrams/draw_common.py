"""Shared matplotlib helpers for the range-map diagrams (top-down, metric, to scale)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.patches import Rectangle, Circle, FancyArrow, Polygon  # noqa: E402,F401
from matplotlib.ticker import MultipleLocator       # noqa: E402

C = {
    "ready": "#E9E2D3", "deck": "#D5D8DE", "field": "#F4E9D8", "berm": "#D9B48F", "backstop": "#C4936A",
    "aim": "#DDE7EF", "course": "#D3EEE8", "recoil": "#F8DCD6", "path": "#E4E4E4", "ink": "#22262C",
    "grid_minor": "#0000000D", "grid_major": "#00000038", "teal": "#00A08F", "coral": "#EE5A4A",
    "graphite": "#2B2F36", "bone": "#BDB3A0", "steel": "#6E7782", "ice": "#5BC8F5",
    "T1": "#AEB8C4", "T2": "#2F7BFF", "T3": "#8C3CFF", "T4": "#E39A1E", "glass": "#9CC9E0",
}
TIER_COLORS = [C["T1"], C["T2"], C["T3"], C["T4"]]


def rect(ax, r, fc="none", ec=None, lw=0.8, label=None, fs=7, alpha=1.0, hatch=None, z=2,
         color="#22262C", weight="normal", rot=0, va="center", ha="center", ls="-", label_xy=None):
    x0, y0, x1, y1 = r
    ec = C["ink"] if ec is None else ec
    p = Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=fc, edgecolor=ec, lw=lw, alpha=alpha,
                  hatch=hatch, zorder=z, linestyle=ls)
    ax.add_patch(p)
    if label:
        lx, ly = label_xy if label_xy else ((x0 + x1) / 2, (y0 + y1) / 2)
        ax.text(lx, ly, label, fontsize=fs, ha=ha, va=va, color=color, zorder=z + 5,
                rotation=rot, weight=weight, clip_on=True)
    return p


def circle(ax, x, y, r, fc="none", ec=None, lw=0.8, z=3, alpha=1.0, ls="-"):
    ec = C["ink"] if ec is None else ec
    p = Circle((x, y), r, facecolor=fc, edgecolor=ec, lw=lw, zorder=z, alpha=alpha, linestyle=ls)
    ax.add_patch(p)
    return p


def metric_grid(ax, minor, major, label_every=None, fs=7):
    ax.xaxis.set_minor_locator(MultipleLocator(minor))
    ax.yaxis.set_minor_locator(MultipleLocator(minor))
    ax.xaxis.set_major_locator(MultipleLocator(label_every or major))
    ax.yaxis.set_major_locator(MultipleLocator(label_every or major))
    ax.grid(which="minor", color=C["grid_minor"], lw=0.3, zorder=0)
    ax.grid(which="major", color=C["grid_major"], lw=0.7, zorder=0)
    ax.tick_params(labelsize=fs, which="both", length=2)
    ax.set_axisbelow(True)


def scale_bar(ax, x, y, length, label=None, fs=7, h=None):
    h = h if h is not None else length * 0.04
    n = 4
    for i in range(n):
        ax.add_patch(Rectangle((x + i * length / n, y), length / n, h,
                               facecolor=C["ink"] if i % 2 == 0 else "white", edgecolor=C["ink"], lw=0.6,
                               zorder=20))
    ax.text(x, y + h * 1.6, "0", fontsize=fs, ha="center", va="bottom", zorder=21)
    ax.text(x + length, y + h * 1.6, f"{length:g} m", fontsize=fs, ha="center", va="bottom", zorder=21)
    if label:
        ax.text(x + length / 2, y - h * 0.8, label, fontsize=fs, ha="center", va="top", zorder=21)


def north_arrow(ax, x, y, size, fs=8):
    ax.add_patch(FancyArrow(x, y, 0, size, width=size * 0.12, head_width=size * 0.35,
                            head_length=size * 0.35, length_includes_head=True, color=C["ink"], zorder=20))
    ax.text(x, y + size * 1.12, "N (+Y)\nshooting direction", fontsize=fs, ha="center", va="bottom", zorder=20)


def save(fig, path, dpi=150):
    fig.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)
