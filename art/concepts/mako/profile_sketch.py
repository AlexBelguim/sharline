"""AR-7 MAKO - side-profile coordinate sketch (authoritative numbers for BRIEF.md).

Plots the side (Y,Z) profiles of every major part in metres, using the style-guide axes:
origin (0,0,0) = pistol-grip hand position, muzzle toward -Y, bore along Y at Z = BORE_Z.
The plot is drawn with -Y on the LEFT (muzzle left), i.e. the view from +X = the gun's LEFT side,
which is the same view as the concept images and blender_common's "right" render view.

Run:  python profile_sketch.py [--overlay concept.png]   -> writes profile_sketch.png (and _overlay.png)
"""
import math
import os
import sys

try:  # plotting only; the point lists below import fine without matplotlib (e.g. inside Blender)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon
except ImportError:
    plt = None

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------- key constants (metres)
BORE_Z = 0.050          # bore axis height above the grip origin
RAIL_BASE = 0.0745      # top of upper / handguard bodies = rail base
RAIL_TOP = 0.084        # top of the continuous Picatinny rail (0.0095 tall, 0.021 wide)
MUZZLE_Y = -0.565       # front face of compensator
BUTT_Y = 0.278          # rear face of butt pad

# ----------------------------------------------------------------------------- part profiles (y, z)
# upper: rear-bottom corner is stepped up to z 0.046 where the lower's buffer tower rises behind the grip
UPPER = [(-0.168, 0.024), (-0.168, 0.068), (-0.162, RAIL_BASE), (0.022, RAIL_BASE), (0.030, 0.066),
         (0.030, 0.046), (0.014, 0.046), (0.008, 0.024)]
HANDGUARD = [(-0.168, 0.026), (-0.490, 0.026), (-0.500, 0.036), (-0.500, RAIL_BASE), (-0.168, RAIL_BASE)]
RAIL = [(-0.498, RAIL_BASE), (-0.498, RAIL_TOP), (0.022, RAIL_TOP), (0.022, RAIL_BASE)]
# lower: front sits 0.008 behind the upper's front (AR step), magwell flares at the lip, buffer tower at rear
LOWER = [(-0.160, 0.024), (-0.162, -0.026), (-0.168, -0.032), (-0.168, -0.038), (-0.080, -0.038),
         (-0.078, -0.030), (-0.080, -0.006), (-0.072, 0.000), (0.018, 0.000), (0.030, 0.008),
         (0.036, 0.020), (0.036, 0.046), (0.014, 0.046), (0.008, 0.024)]
TRIGGER_GUARD = [(-0.082, 0.000), (-0.082, -0.030), (-0.074, -0.037), (-0.022, -0.037), (-0.012, -0.026),
                 (-0.012, 0.000)]
TRIGGER_GUARD_HOLE = [(-0.074, 0.001), (-0.074, -0.029), (-0.024, -0.029), (-0.018, -0.022),
                      (-0.018, 0.001)]
TRIGGER = [(-0.036, 0.004), (-0.044, 0.004), (-0.047, -0.010), (-0.050, -0.022), (-0.045, -0.024),
           (-0.042, -0.012), (-0.038, -0.002)]
GRIP = [(-0.020, 0.002), (0.022, 0.002), (0.030, 0.008), (0.035, 0.000), (0.044, -0.030), (0.054, -0.062),
        (0.066, -0.100), (0.064, -0.108), (0.026, -0.111), (0.021, -0.104), (0.008, -0.064),
        (-0.004, -0.034), (-0.020, -0.006)]
# magazine: straight to z=-0.020, then forward arc about centre (-0.520,-0.020): radius 0.368 front edge,
# 0.432 rear edge, sweeping 0.32 rad (18.3 deg) -> floorplate tilted 18 deg, rear corner lowest.
MAG = [(-0.152, 0.012), (-0.152, -0.020), (-0.1532, -0.0494), (-0.1567, -0.0786), (-0.1626, -0.1075),
       (-0.1707, -0.1358), (-0.1745, -0.1345), (-0.1783, -0.1459), (-0.1099, -0.1686), (-0.1061, -0.1572),
       (-0.1099, -0.1559), (-0.1004, -0.1227), (-0.0935, -0.0888), (-0.0894, -0.0545), (-0.088, -0.020),
       (-0.088, 0.012)]
MAG_WINDOW = [(-0.102, -0.046), (-0.096, -0.046), (-0.098, -0.080), (-0.104, -0.080)]
BUFFER_TUBE = [(0.030, BORE_Z - 0.016), (0.030, BORE_Z + 0.016), (0.215, BORE_Z + 0.016),
               (0.215, BORE_Z - 0.016)]
CASTLE_NUT = [(0.036, BORE_Z - 0.0195), (0.036, BORE_Z + 0.0195), (0.046, BORE_Z + 0.0195),
              (0.046, BORE_Z - 0.0195)]
STOCK = [(0.098, 0.034), (0.098, 0.064), (0.110, 0.074), (0.136, 0.078), (0.262, 0.078), (0.262, -0.056),
         (0.240, -0.056), (0.164, 0.020), (0.150, 0.025), (0.106, 0.026)]
STOCK_PANEL = [(0.198, 0.014), (0.246, 0.014), (0.246, -0.034)]    # 0.003 RECESS each side (not a through-cut)
BUTT_PAD = [(0.262, 0.082), (0.270, 0.082), (0.277, 0.072), (BUTT_Y, -0.046), (0.274, -0.058),
            (0.262, -0.060)]
BARREL = [(-0.520, BORE_Z - 0.0095), (-0.520, BORE_Z + 0.0095), (-0.500, BORE_Z + 0.0095),
          (-0.500, BORE_Z - 0.0095)]
COMP = [(MUZZLE_Y, BORE_Z - 0.009), (MUZZLE_Y, BORE_Z + 0.009), (-0.561, BORE_Z + 0.013),
        (-0.521, BORE_Z + 0.013), (-0.517, BORE_Z + 0.010), (-0.517, BORE_Z - 0.010),
        (-0.521, BORE_Z - 0.013), (-0.561, BORE_Z - 0.013)]
COMP_PORTS = [(-0.556, -0.547), (-0.540, -0.531)]          # y ranges of the 2 side ports, z = bore +-0.0065
CHARGING_HANDLE = [(0.022, 0.064), (0.022, RAIL_BASE), (0.034, RAIL_BASE), (0.042, 0.068), (0.040, 0.062)]
OPTIC_Y = -0.085                                            # optic clamp centre (socket) on rail top
OPTIC = [(OPTIC_Y - 0.040, RAIL_TOP), (OPTIC_Y + 0.036, RAIL_TOP), (OPTIC_Y + 0.036, RAIL_TOP + 0.016),
         (OPTIC_Y + 0.032, RAIL_TOP + 0.052), (OPTIC_Y + 0.000, RAIL_TOP + 0.054),
         (OPTIC_Y - 0.032, RAIL_TOP + 0.046), (OPTIC_Y - 0.040, RAIL_TOP + 0.022)]
OPTIC_WINDOW = [(OPTIC_Y - 0.036, RAIL_TOP + 0.020), (OPTIC_Y + 0.032, RAIL_TOP + 0.020),
                (OPTIC_Y + 0.032, RAIL_TOP + 0.044), (OPTIC_Y - 0.036, RAIL_TOP + 0.044)]
SIGHT_Z = RAIL_TOP + 0.032                                  # 0.116, 0.066 above bore
AMMO_BEZEL = [(-0.030, 0.040), (0.006, 0.040), (0.006, 0.064), (-0.030, 0.064)]
AMMO_SCREEN = [(-0.026, 0.044), (0.002, 0.044), (0.002, 0.060), (-0.026, 0.060)]
REAR_SIGHT = [(0.004, RAIL_TOP), (0.020, RAIL_TOP), (0.020, RAIL_TOP + 0.008), (0.008, RAIL_TOP + 0.008)]
BOTTOM_RAIL = [(-0.430, 0.026), (-0.430, 0.0165), (-0.290, 0.0165), (-0.290, 0.026)]
SIDE_RAIL = [(-0.470, BORE_Z - 0.0105), (-0.410, BORE_Z - 0.0105), (-0.410, BORE_Z + 0.0105),
             (-0.470, BORE_Z + 0.0105)]
SLOT_Y = [-0.200, -0.245, -0.290, -0.335, -0.380]          # M-LOK slot centres (0.032 x 0.007, side faces)

SOCKETS = {
    "Optic": (0, OPTIC_Y, RAIL_TOP), "Stock": (0, 0.215, BORE_Z), "Mag": (0, -0.152, 0.012),
    "Under": (0, -0.360, 0.0165), "Side_R/L": (0.0315, -0.440, BORE_Z), "Shield": (0, -0.480, RAIL_TOP),
    "Muzzle": (0, MUZZLE_Y, BORE_Z), "LeftHand": (0, -0.330, 0.020),
}

GRAPHITE = "#2f3238"
GUNMETAL = "#5d6066"
BONE = "#c4bdb1"
ICE = "#b3eeff"
RUBBER = "#1d1f23"


def poly(ax, pts, fc, ec="#111", lw=1.0, alpha=1.0, z=1, hatch=None):
    ax.add_patch(Polygon(pts, closed=True, fc=fc, ec=ec, lw=lw, alpha=alpha, zorder=z, hatch=hatch))


def draw(ax, alpha=1.0, outline_only=False):
    def P(pts, fc, z, **kw):
        poly(ax, pts, "none" if outline_only else fc, ec=("#ff2a6d" if outline_only else "#111"),
             lw=(1.4 if outline_only else 0.9), alpha=alpha, z=z, **kw)
    P(BUFFER_TUBE, GRAPHITE, 1)
    P(CASTLE_NUT, GUNMETAL, 2)
    P(STOCK, BONE, 3)
    P(STOCK_PANEL, "#a9a296", 4)
    P(BUTT_PAD, RUBBER, 3)
    P(BARREL, GUNMETAL, 1)
    P(COMP, GUNMETAL, 2)
    for y0, y1 in COMP_PORTS:
        P([(y0, BORE_Z - 0.0065), (y1, BORE_Z - 0.0065), (y1, BORE_Z + 0.0065), (y0, BORE_Z + 0.0065)], "#111", 3)
    P(MAG, BONE, 1)
    P(MAG_WINDOW, "#222", 2)
    P(LOWER, GRAPHITE, 2)
    P(TRIGGER_GUARD, GRAPHITE, 2)
    if not outline_only:
        P(TRIGGER_GUARD_HOLE, "white", 3)
    P(TRIGGER, GUNMETAL, 4)
    P(GRIP, BONE, 3)
    P(UPPER, GRAPHITE, 3)
    P(HANDGUARD, GRAPHITE, 3)
    P(BOTTOM_RAIL, GRAPHITE, 2)
    P(SIDE_RAIL, "#3a3e45", 4)
    for yc in SLOT_Y:
        P([(yc - 0.016, BORE_Z - 0.0035), (yc + 0.016, BORE_Z - 0.0035), (yc + 0.016, BORE_Z + 0.0035),
           (yc - 0.016, BORE_Z + 0.0035)], "#0d0e10", 4)
        for dz in (0.0185, -0.0185):
            P([(yc - 0.012, BORE_Z + dz - 0.0025), (yc + 0.012, BORE_Z + dz - 0.0025),
               (yc + 0.012, BORE_Z + dz + 0.0025), (yc - 0.012, BORE_Z + dz + 0.0025)], "#0d0e10", 4)
    P(RAIL, "#3a3e45", 4)
    P(CHARGING_HANDLE, GRAPHITE, 4)
    P(REAR_SIGHT, GRAPHITE, 4)
    P(OPTIC, GRAPHITE, 5)
    if not outline_only:
        P(OPTIC_WINDOW, "#cfeefa", 6)
        ax.add_patch(Circle((OPTIC_Y - 0.030, SIGHT_Z), 0.002, fc=ICE, ec="#3aa0c8", zorder=7))
    P(AMMO_BEZEL, "#24272c", 5)
    P(AMMO_SCREEN, ICE, 6)


def annotate(ax):
    ax.axhline(BORE_Z, color="#d33", lw=0.7, ls="--", zorder=0)
    ax.text(-0.60, BORE_Z + 0.003, "bore Z=0.050", color="#d33", fontsize=7)
    ax.axhline(SIGHT_Z, color="#39c", lw=0.6, ls=":", zorder=0)
    ax.text(-0.60, SIGHT_Z + 0.003, "sight line Z=0.116", color="#39c", fontsize=7)
    ax.plot([0], [0], "k+", ms=14, mew=1.5, zorder=20)
    ax.text(0.004, -0.010, "ORIGIN (0,0,0)\ngrip hand pos.", fontsize=7, zorder=20)
    for name, (x, y, z) in SOCKETS.items():
        ax.plot([y], [z], marker="o", ms=4, mfc="#ffcc00", mec="k", zorder=21)
        ax.text(y + 0.003, z + 0.004, "S_" + name, fontsize=6, color="#7a5c00", zorder=21)
    stations = [(MUZZLE_Y, "muzzle -0.565"), (-0.517, "comp/barrel -0.517"), (-0.500, "HG front -0.500"),
                (-0.168, "HG/upper -0.168"), (0.030, "rcvr rear 0.030"), (0.098, "stock front 0.098"),
                (0.215, "tube end 0.215"), (BUTT_Y, "butt 0.278")]
    for y, lab in stations:
        ax.axvline(y, color="#888", lw=0.5, ls=":", zorder=0)
        ax.text(y, -0.205, lab, rotation=90, fontsize=6, va="bottom", ha="right", color="#555")
    for z, lab in [(RAIL_TOP, "rail top 0.084"), (0.024, "parting line 0.024"), (-0.038, "magwell lip -0.038"),
                   (-0.169, "mag bottom -0.169"), (0.138, "optic top 0.138"), (-0.111, "grip bottom -0.111")]:
        ax.axhline(z, color="#aaa", lw=0.4, ls=":", zorder=0)
        ax.text(0.30, z, lab, fontsize=6, va="center", color="#555")


def main():
    fig, ax = plt.subplots(figsize=(16, 6.4), dpi=110)
    draw(ax)
    annotate(ax)
    ax.set_xlim(-0.62, 0.37)
    ax.set_ylim(-0.215, 0.165)
    ax.set_aspect("equal")
    ax.set_xticks([x / 100 for x in range(-60, 31, 5)])
    ax.set_yticks([z / 100 for z in range(-20, 17, 2)])
    ax.tick_params(labelsize=7)
    ax.grid(True, lw=0.3, color="#ddd")
    ax.set_xlabel("Y (m)   <- muzzle (-Y)                       stock (+Y) ->", fontsize=8)
    ax.set_ylabel("Z (m)", fontsize=8)
    ax.set_title('AR-7 "MAKO" side profile, viewed from +X (gun\'s LEFT side), metres. Yellow = sockets.',
                 fontsize=10)
    out = os.path.join(HERE, "profile_sketch.png")
    fig.tight_layout()
    fig.savefig(out)
    print("wrote", out)

    if "--overlay" in sys.argv:
        # overlay the profile outline on a concept image, scaled by the user-given pixel extents
        # args: --overlay img.png x_muzzle_px x_butt_px y_bore_px
        i = sys.argv.index("--overlay")
        img_path = sys.argv[i + 1]
        xm, xb, yb = (float(v) for v in sys.argv[i + 2:i + 5])
        img = plt.imread(img_path)
        h, w = img.shape[:2]
        s = (xb - xm) / (BUTT_Y - MUZZLE_Y)                     # px per metre
        # image extent in metres so that muzzle/butt/bore line up
        left = MUZZLE_Y - xm / s
        right = left + w / s
        top = BORE_Z + yb / s
        bottom = top - h / s
        fig2, ax2 = plt.subplots(figsize=(16, 16 * h / w), dpi=110)
        ax2.imshow(img, extent=(left, right, bottom, top), zorder=0)
        draw(ax2, alpha=0.95, outline_only=True)
        ax2.plot([0], [0], "+", color="#ff2a6d", ms=14, mew=1.5, zorder=20)
        ax2.set_xlim(left, right)
        ax2.set_ylim(bottom, top)
        ax2.set_aspect("equal")
        ax2.axis("off")
        out2 = os.path.join(HERE, "profile_overlay.png")
        fig2.tight_layout(pad=0)
        fig2.savefig(out2)
        print("wrote", out2)


if __name__ == "__main__":
    main()
