"""Solace proportion overlay: female_base SDF silhouette (h=1.68, build=0.2) + planned gear, ortho front/side.
Writes sol_proportions.png (1 m = 500 px). Pure numpy/matplotlib (bpy stubbed)."""
import sys, types, math
import numpy as np
for name in ("bpy", "bmesh", "mathutils", "blender_common"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["mathutils"].Vector = object
sys.modules["mathutils"].kdtree = types.SimpleNamespace()
sys.path.insert(0, r"F:/git/val etf/tools")
import female_base as fb  # noqa
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Circle, Polygon

OUT = sys.argv[1] if len(sys.argv) > 1 else r"F:/git/val etf/art/concepts/solace/proportions_overlay.png"
H, B = 1.68, 0.2
s = H / fb.REF_H
ops, J, info = fb.make_recipe(B, dict(cheek=1.15, lip_full=1.15, nose_w=1.10, nose_len=0.97, jaw_w=0.98,
                                      chin_w=0.96, eye_open=1.06, eye_tilt=0.05, brow=0.95))
F = fb.Field(ops, s)

# ---------------------------------------------------------------- silhouettes (min over the depth axis)
h = 0.005
xs = np.arange(-0.78, 0.78 + h, h)
ys = np.arange(-0.22, 0.24 + h, h)
zs = np.arange(-0.01, 1.76 + h, h)
front = np.zeros((len(zs), len(xs)), bool)
side = np.zeros((len(zs), len(ys)), bool)
for i, z in enumerate(zs):
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    P = np.stack([X.ravel(), Y.ravel(), np.full(X.size, z)], 1)
    inside = (F(P) < 0).reshape(X.shape)
    front[i] = inside.any(1)
    side[i] = inside.any(0)

# ---------------------------------------------------------------- planned gear (world coords, metres)
def bud_r(z):
    t = [(1.150, 0.018), (1.190, 0.050), (1.250, 0.075), (1.320, 0.082), (1.400, 0.072), (1.470, 0.050),
         (1.530, 0.025), (1.565, 0.0)]
    zz, rr = zip(*t)
    return np.interp(z, zz, rr)

BUD_CY = 0.185
VANE_C = [(0.000, 0.170, 1.150), (0.000, 0.215, 1.250), (0.000, 0.236, 1.330), (0.000, 0.225, 1.420),
          (0.000, 0.205, 1.500), (0.000, 0.185, 1.565)]
VANE_L = [(0.015, 0.165, 1.150), (0.060, 0.175, 1.230), (0.084, 0.180, 1.320), (0.090, 0.172, 1.410),
          (0.104, 0.160, 1.480), (0.125, 0.150, 1.535)]
VANE_W = [0.030, 0.085, 0.105, 0.080, 0.040, 0.0]
PONY = [(-0.050, 0.100, 1.535), (-0.104, 0.074, 1.518), (-0.128, 0.022, 1.470), (-0.120, -0.060, 1.408),
        (-0.106, -0.088, 1.340), (-0.096, -0.112, 1.270), (-0.091, -0.118, 1.210), (-0.099, -0.108, 1.160)]
PONY_R = [0.020, 0.024, 0.026, 0.026, 0.024, 0.020, 0.014, 0.005]
DRONE_C, DRONE_R = (0.203, -0.044, 0.935), 0.040
POUCH = dict(c=(-0.086, -0.103, 0.960), size=(0.050, 0.026, 0.070), rotz=-40)
BELT = (0.970, 1.000)
HALO = (0.0, 0.020, 1.906)
EMBLEM = (0.272, -0.030, 1.331)
KNEE = (0.097, -0.088, 0.478)
HEM = [(0, 0.900), (35, 0.900), (60, 0.840), (90, 0.760), (120, 0.700), (150, 0.660), (172, 0.645)]
SKIRT = [(0.900, 0.177, 0.102, 0.012), (0.860, 0.186, 0.112, 0.014), (0.800, 0.192, 0.116, 0.016),
         (0.740, 0.198, 0.118, 0.020), (0.680, 0.204, 0.120, 0.024), (0.640, 0.208, 0.121, 0.026)]
COLLAR = [(1.405, 0.090, 0.086, 0.030), (1.432, 0.078, 0.075, 0.032)]  # front z; top ring 1.455 front .. 1.505 back
W_R = np.array([-0.5443, -0.0211, 1.0297])
f_R = np.array([-0.7359, -0.1392, -0.6626])
m_R = np.array([-0.581, -0.373, 0.724])
YOKE = [(0.0, 0.136, 1.400), (0.045, 0.126, 1.406), (0.085, 0.090, 1.407), (0.108, 0.080, 1.405)]
STRAP = [(0.108, 0.075, 1.408), (0.114, 0.040, 1.428), (0.114, 0.015, 1.436), (0.114, -0.015, 1.415),
         (0.112, -0.035, 1.385), (0.110, -0.046, 1.360)]


def skirt_ring(z):
    zz = [r[0] for r in SKIRT][::-1]
    return [np.interp(z, zz, [r[k] for r in SKIRT][::-1]) for k in (1, 2, 3)]


def hem_z(a):
    aa, zz = zip(*HEM)
    return np.interp(a, aa, zz)


fig, axs = plt.subplots(1, 2, figsize=(16, 9.5), dpi=100, gridspec_kw=dict(width_ratios=[1.56, 0.62]))
for ax in axs:
    ax.set_aspect("equal")
    ax.set_facecolor("#e9e9e9")
    ax.grid(True, color="#cccccc", lw=0.5)
    for z in np.arange(0, 1.8, 0.1):
        ax.axhline(z, color="#bbbbbb", lw=0.4)

ax = axs[0]
ax.set_title("FRONT (looking at her face; her RIGHT = -X = screen-left)")
ax.contourf(xs, zs, front.astype(float), levels=[0.5, 1.5], colors=["#9a7a66"])
# skirt/tail outline (front view: outer x of the skirt at each z, below hem)
zz = np.linspace(0.64, 0.90, 30)
ax.plot([skirt_ring(z)[0] for z in zz], zz, color="#c9c2b0", lw=2)
ax.plot([-skirt_ring(z)[0] for z in zz], zz, color="#c9c2b0", lw=2)
ax.fill_between([-0.15, 0.15], BELT[0], BELT[1], color="#222", alpha=0.8)
# collar
for z, rx, ry, cy in COLLAR:
    ax.plot([-rx, rx], [z, z], color="#f0ead8", lw=3)
ax.plot([-0.082, -0.040], [1.457, 1.462], color="#f0ead8", lw=3)
ax.plot([0.028, 0.082], [1.462, 1.480], color="#f0ead8", lw=3)
# bud vanes (front view) - side vane tips
for sgn in (1, -1):
    pts = np.array(VANE_L) * [sgn, 1, 1]
    ax.plot(pts[:, 0], pts[:, 2], color="#f7f3e8", lw=2.5)
    ax.plot(pts[-1, 0], pts[-1, 2], "^", color="#ff6a5a", ms=8)
pts = np.array(VANE_C)
ax.plot(pts[:, 0], pts[:, 2], color="#f7f3e8", lw=2, ls=":")
# yoke/strap
for sgn in (1, -1):
    p = np.array(STRAP) * [sgn, 1, 1]
    ax.plot(p[:, 0], p[:, 2], color="#333", lw=3)
# ponytail
p = np.array(PONY)
ax.plot(p[:, 0], p[:, 2], color="#2a1a14", lw=1)
for q, r in zip(PONY, PONY_R):
    ax.add_patch(Circle((q[0], q[2]), r, color="#2a1a14", alpha=0.6))
ax.add_patch(Circle((DRONE_C[0], DRONE_C[2]), DRONE_R, color="#f2efe6", ec="#333"))
ax.add_patch(Circle((DRONE_C[0] + 0.028, DRONE_C[2]), 0.011, color="#ff5c4d"))
ax.add_patch(Polygon([(POUCH["c"][0] - 0.022, 0.925), (POUCH["c"][0] + 0.022, 0.925),
                      (POUCH["c"][0] + 0.022, 0.995), (POUCH["c"][0] - 0.022, 0.995)], color="#7d6a4f"))
ax.plot(*EMBLEM[0:1], EMBLEM[2], "h", color="#ff5c4d", ms=9)
# bracer (right forearm)
for t0, t1, mm, col in ((-0.090, 0.000, 0.042, "#f2efe6"), (-0.078, -0.016, 0.047, "#ff5c4d")):
    a = W_R + t0 * f_R + mm * m_R
    b = W_R + t1 * f_R + mm * m_R
    ax.plot([a[0], b[0]], [a[2], b[2]], color=col, lw=6 if col != "#ff5c4d" else 3)
nz = W_R + 0.024 * f_R + 0.042 * m_R
ax.plot(nz[0], nz[2], "o", color="#555", ms=5)
for sgn in (1, -1):
    ax.add_patch(Ellipse((sgn * KNEE[0], KNEE[2]), 0.084, 0.110, color="#f2efe6", ec="#333"))
ax.add_patch(Ellipse((HALO[0], HALO[2]), 0.32, 0.05, fill=False, ec="#4d7cff", lw=2))
ax.plot(HALO[0], HALO[2], "+", color="#4d7cff", ms=12)
ax.set_xlim(-0.78, 0.78)
ax.set_ylim(-0.02, 2.0)

ax = axs[1]
ax.set_title("SIDE (her LEFT side; front = -Y = screen-left)")
ax.contourf(ys, zs, side.astype(float), levels=[0.5, 1.5], colors=["#9a7a66"])
# skirt: back outline & hem
zz = np.linspace(0.64, 0.90, 30)
ax.plot([skirt_ring(z)[2] + skirt_ring(z)[1] for z in zz], zz, color="#c9c2b0", lw=2)
# hem profile seen from the side: (y at angle a, hem_z)
aa = np.linspace(0, 180, 60)
hy, hz = [], []
for a in aa:
    z = hem_z(a)
    rx, ry, cy = skirt_ring(z) if z <= 0.9 else skirt_ring(0.9)
    hy.append(cy - ry * math.cos(math.radians(a)))
    hz.append(z)
ax.plot(hy, hz, color="#ff5c4d", lw=2)
# bud profile (side): depth extent of vanes
zz = np.linspace(1.15, 1.565, 40)
pc = np.array(VANE_C)
ax.plot(pc[:, 1], pc[:, 2], color="#f7f3e8", lw=3)
ax.plot(np.array(VANE_L)[:, 1], np.array(VANE_L)[:, 2], color="#f0ead8", lw=2, ls="--")
ax.fill_betweenx(zz, BUD_CY - 0.62 * bud_r(zz), BUD_CY + 0.62 * bud_r(zz), color="#ff5c4d", alpha=0.25)
ax.add_patch(Polygon([(0.112, 1.08), (0.124, 1.08), (0.124, 1.42), (0.112, 1.42)], color="#333"))
p = np.array(PONY)
for q, r in zip(PONY, PONY_R):
    ax.add_patch(Circle((q[1], q[2]), r, color="#2a1a14", alpha=0.6))
ax.add_patch(Circle((DRONE_C[1], DRONE_C[2]), DRONE_R, color="#f2efe6", ec="#333"))
p = np.array(STRAP)
ax.plot(p[:, 1], p[:, 2], color="#333", lw=3)
p = np.array(YOKE)
ax.plot(p[:, 1], p[:, 2], color="#333", lw=3)
ax.add_patch(Ellipse((KNEE[1], KNEE[2]), 0.016, 0.110, color="#f2efe6", ec="#333"))
ax.add_patch(Ellipse((HALO[1], HALO[2]), 0.32, 0.05, fill=False, ec="#4d7cff", lw=2))
ax.plot(HALO[1], HALO[2], "+", color="#4d7cff", ms=12)
ax.set_xlim(-0.26, 0.30)
ax.set_ylim(-0.02, 2.0)
fig.suptitle("SOLACE proportions overlay - female_base(height=1.68, build=0.2) silhouette (brown) + planned gear from BRIEF.md. "
             "DIMENSIONS ONLY (grid 0.1 m). White = ivory parts, red = coral, dark = charcoal/hair, blue = halo socket.", fontsize=10)
plt.tight_layout()
plt.savefig(OUT)
print("saved", OUT)
