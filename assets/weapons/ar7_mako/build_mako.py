"""AR-7 "MAKO" - modular M4-style assault rifle. Re-runnable build: creates everything from scratch.

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python-exit-code 1 \
      -P build_mako.py -- [flags]
Flags:
  --no-render      build + export only
  --no-export      skip glb/fbx/blend output
  --quick          low-res / low-sample renders (16 samples, 60 % size)
  --out=<dir>      stage generated outputs in this directory (defaults to this asset folder)
  --renders=a,b    only these render groups: main, closeups, stocks, mags, fixes, compare (default: all six);
                   side, iterc = iteration-only views written to _work/iter/
Outputs: mako.blend, mako_base.glb/.fbx, MAKO_<part>.glb/.fbx, mako_default.glb, sockets.json, tri_counts.json,
textures/ (baked tinted detail maps), renders/ (+ contact sheets via make_sheets.py). check_glb.py validates the
GLBs after export (names, sockets vs sockets.json, materials, embedded textures, no emissive, engine extras,
zero-area triangles) and the build exits 1 if it fails.
Helpers: mako_lib.py (geometry, per-edge bevels, glTF-safe materials), render_mako.py, make_sheets.py, check_glb.py.
Debug switches (environment, default off; never needed for a delivery build): MAKO_LOCAL_OFFSETS=0 (uniform bevel
weights, i.e. the old globally clamped bevels), MAKO_NO_SPIKEFIX=1, MAKO_NO_POSTCLEAN=1, MAKO_MICRO_EDGE=<m>,
MAKO_SPIKE_DEBUG=<object name>, MAKO_RD=<dir> (iteration renders elsewhere).

Master reference: art/concepts/mako/v09.png (DIRECTION_LOG item 2): no iron sights, no ammo counter, long
squared free-float handguard with 3 rows of rounded slots + full-length top rail, slotted birdcage flash hider,
graphite receiver, bone stock/grip/mag (mag with a long window and visible cartridges).
Axes: muzzle -Y, Z up, origin = pistol-grip hand position, bore Z = 0.050.
Handedness: shooter's RIGHT = -X (ejection port, dust cover, forward assist, CH latch, mag release),
            shooter's LEFT = +X (bolt catch, selector).
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(PROJECT, "tools"))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import blender_common as bc  # noqa: E402
import mako_lib as L  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FLAG = {a.split("=")[0]: (a.split("=")[1] if "=" in a else True) for a in ARGS}
bc.PROJECT = PROJECT
bc.TEXTURES = os.path.join(PROJECT, "art", "textures")
T0 = time.time()


def log(*a):
    print(f"[mako {time.time() - T0:6.1f}s]", *a, flush=True)


# --------------------------------------------------------------------------------------------- constants
BORE_Z = 0.050
RAIL_BASE = 0.0745
RAIL_TOP = RAIL_BASE + L.RAIL_H          # 0.084
MUZZLE_Y = -0.565
HG_FRONT, HG_REAR = -0.495, -0.168
STOCK_SOCKET = (0.0, 0.215, BORE_Z)
MAG_SOCKET = (0.0, -0.152, 0.012)
# Rear-of-receiver clearances (review fix): the charging handle rides above the castle nut / buffer tube for its
# whole stroke, the forward-assist cap sits in its own bore and ends before the tube starts.
TUBE_Y0 = 0.0295                        # buffer tube front (hidden inside the receiver bosses)
TUBE_R = 0.0160
NUT_Y = (0.0360, 0.0465)                # castle nut
NUT_R = 0.0194                          # top of nut z 0.0694
CH_Z0, CH_Z1 = 0.0702, 0.0741           # charging-handle shaft (inside the upper's channel)
CH_WING_Z1 = 0.0792                     # T-wing top (still below the rail top 0.084)
CH_STROKE = 0.050                       # clean pull with the stock extended (stock front y 0.098)
FA_AXIS = (-0.0172, 0.0585)             # forward-assist axis (x, z), along Y
FA_HOUSING_REAR = 0.024
FA_CAP_R = 0.0060
FA_CAP_Y = (0.0130, 0.0285)             # plunger cap at rest; pushes -Y by FA_PUSH
FA_PUSH = 0.004
UP_PANEL = (-0.132, -0.036, 0.0510, 0.0630)   # +X upper panel-line frame: y0, y1, z0, z1 (behind the shoulder pad)
UP_PAD_Y = (-0.165, -0.140)             # raised shoulder pads at the front of both upper flanks (r2 review, v09)
REAR_SWEEP_C, REAR_SWEEP_R = (0.002, 0.036), 0.012   # upper/lower parting line sweeps up into the tube tower
STOCK_TRAVEL = (0.0, 0.0145, 0.0290, 0.0435)  # stock_standard positions toward -Y (r3: limited by the tube end in
                                              # the stock's blind channel, y 0.2595; the front stays behind the nut)
STD_CHANNEL_END = 0.2595                      # stock_standard: blind end of the tube channel (rear wall 2.5 mm)

OUT = os.path.abspath(FLAG.get("--out", HERE))
os.environ["MAKO_OUT"] = OUT
RENDERS = os.path.join(OUT, "renders")

# --------------------------------------------------------------------------------------------- scene
bc.reset_scene()
SC = bpy.context.scene
COL = {}
for cname in ("MAKO_Base", "MAKO_stock_standard", "MAKO_stock_precision", "MAKO_stock_light",
              "MAKO_mag_30", "MAKO_mag_45", "MAKO_mag_drum60"):
    COL[cname] = bc.collection(cname)

TEX = bc.TEXTURES
TEXOUT = os.path.join(OUT, "textures")   # baked, tinted copies of the shared detail textures (embedded in GLBs)
# glTF-safe materials (mako_lib.gl_material): palette colour x detail texture baked into one sRGB map, wired
# straight into Base Color, so the engine sees exactly what Blender renders. Repeats come from the UVs (REPS).
M = {
    "graphite": L.gl_material("M_MAKO_Graphite", (0.030, 0.033, 0.040), rough=0.55, metal=0.20,
                              tex=os.path.join(TEX, "worn_paint.png"), tex_mix=0.55, bake_dir=TEXOUT),
    "gunmetal": L.gl_material("M_MAKO_Gunmetal", (0.11, 0.115, 0.12), rough=0.35, metal=0.85,
                              tex=os.path.join(TEX, "brushed_metal.png"), tex_mix=0.30, bake_dir=TEXOUT),
    "bone": L.gl_material("M_MAKO_Bone", (0.55, 0.52, 0.46), rough=0.60, metal=0.0,
                          tex=os.path.join(TEX, "worn_paint.png"), tex_mix=0.22, bake_dir=TEXOUT),
    # grip panels: same bone hue (mean ~0.85 of bone), stipple levelled so the pattern reads (review fix)
    "stipple": L.gl_material("M_MAKO_BoneStipple", (0.55, 0.52, 0.46), rough=0.85, metal=0.0,
                             tex=os.path.join(TEX, "polymer_stipple.png"), tex_mix=0.34, bake_dir=TEXOUT,
                             stretch=True),
    "rubber": L.gl_material("M_MAKO_Rubber", (0.030, 0.033, 0.040), rough=0.85, metal=0.0),
    "dark": L.gl_material("M_MAKO_Dark", (0.035, 0.037, 0.045), rough=0.70, metal=0.0),
    "brass": L.gl_material("M_MAKO_Brass", (0.36, 0.28, 0.18), rough=0.35, metal=0.85),
}
REPS = {"M_MAKO_Graphite": 5.0, "M_MAKO_Gunmetal": 8.0, "M_MAKO_Bone": 6.0, "M_MAKO_BoneStipple": 6.0}
BASE = COL["MAKO_Base"]


def P(name, pts, x0, x1, mat=None, col=BASE):
    """Side-profile prism: pts (y, z), extruded x0..x1."""
    return L.prism(name, pts, "X", x0, x1, col, mat)


def S(name, pts, y0, y1, mat=None, col=BASE):
    """Section prism: pts (x, z), extruded along Y y0..y1."""
    return L.prism(name, pts, "Y", y0, y1, col, mat)


def T(name, pts, z0, z1, mat=None, col=BASE):
    """Plan prism: pts (x, y), extruded along Z z0..z1."""
    return L.prism(name, pts, "Z", z0, z1, col, mat)


def sym(pts_half):
    """Mirror a half outline given for +x (top to bottom) into a closed symmetric (x, z) polygon."""
    return [(x, z) for (x, z) in pts_half] + [(-x, z) for (x, z) in reversed(pts_half)]


def convex_edge(e):
    if len(e.link_faces) != 2:
        return False
    f0, f1 = e.link_faces
    d = f1.calc_center_median() - f0.calc_center_median()
    return d.dot(f0.normal) < -1e-7


def convex_sharp(angle=30):
    def fn(e):
        return L.edge_angle_deg(e) > angle and convex_edge(e)
    return fn


# ===================================================================================================== BASE
def rear_sweep(n=6):
    """Parting-line arc shared by the upper and the lower (r2 review: a swept AR contour instead of the angular
    chamfer). Runs from the tower front (0.014, 0.036) down to the horizontal parting line (0.002, 0.024): a
    convex quarter-round on the upper, a matching cove in the lower's buffer-tube tower."""
    (cy, cz), r = REAR_SWEEP_C, REAR_SWEEP_R
    return [(cy + r * math.cos(-math.pi / 2 * k / n), cz + r * math.sin(-math.pi / 2 * k / n)) for k in range(n + 1)]


def build_shoulder_pads():
    """Raised 2 mm pads at the front of both upper flanks (v09's block behind the handguard). Finished on their
    own with a small crisp bevel and joined into MAKO_Upper (the 1.6 mm receiver bevel would round a 2 mm step
    into a pillow). Their inner faces sit inside the upper."""
    sec = [(0.0140, 0.0500), (0.0172, 0.0500), (0.0172, 0.0658), (0.0149, 0.0702), (0.0118, 0.0702)]
    pads = []
    for sgn in (1, -1):
        pts = [(sgn * x, z) for (x, z) in sec]
        if sgn < 0:
            pts = list(reversed(pts))
        pd = S("_pad", pts, UP_PAD_Y[0], UP_PAD_Y[1], M["graphite"])
        # chamfered front/back ends (plan view), so the pad reads as a machined boss, not a sticker
        L.intersect(pd, T("_padp", [(0.0, UP_PAD_Y[0]), (sgn * 0.0145, UP_PAD_Y[0]),
                                    (sgn * 0.0180, UP_PAD_Y[0] + 0.0035), (sgn * 0.0180, UP_PAD_Y[1] - 0.0035),
                                    (sgn * 0.0145, UP_PAD_Y[1]), (0.0, UP_PAD_Y[1])], 0.04, 0.08))
        L.clean(pd)
        L.finish(pd, bevel=0.0005, segs=1, angle=30)
        pads.append(pd)
    return pads


def build_upper():
    side = [(-0.168, 0.024), (-0.168, RAIL_BASE), (0.022, RAIL_BASE), (0.030, 0.066), (0.030, 0.046),
            (0.014, 0.046)] + rear_sweep()
    sec = sym([(0.0092, 0.077), (0.0152, 0.066), (0.0152, 0.0480), (0.0168, 0.0464), (0.0168, 0.020)])
    up = P("MAKO_Upper", side, -0.0168, 0.0168, M["graphite"])
    L.intersect(up, S("_us", sec, -0.175, 0.040))
    # brass deflector (shooter's right, -X) behind the ejection port
    defl = P("_defl", [(-0.027, 0.0535), (-0.010, 0.0535), (-0.008, 0.0700), (-0.017, 0.0720)], -0.0215, -0.012)
    L.intersect(defl, S("_dfs", [(-0.030, 0.050), (-0.012, 0.050), (-0.012, 0.075), (-0.0175, 0.075),
                                 (-0.030, 0.062)], -0.04, 0.0))
    # forward-assist housing (-X), teardrop boss; flat rear face at y FA_HOUSING_REAR
    fa = L.lathe_y("_fah", [(0, 0), (0.003, 0), (0.0085, 0.011), (0.0085, 0.0345), (0.0079, 0.036), (0, 0.036)],
                   FA_HOUSING_REAR - 0.036, 1, c=FA_AXIS, steps=16)
    ring = L.cyl("_ring", 0.0192, "Y", 0.012, 0.030, c=(0, BORE_Z), segs=24)
    L.intersect(ring, L.box("_rb", -0.03, 0.03, 0.0, 0.05, 0.046, 0.0745))
    L.boolean(up, [defl, fa, ring], op="UNION", transfer=False)
    cut = []
    # ejection port (bolt carrier face shows gunmetal when the dust cover opens)
    port = L.round_poly([(-0.091, 0.0395), (-0.029, 0.0395), (-0.029, 0.0635), (-0.091, 0.0635)], 0.002, 2)
    cut.append(P("_port", port, -0.030, -0.0125, M["gunmetal"]))
    # charging-handle channel under the rail (the handle rides high enough to clear the tube and castle nut); it
    # runs far forward so the shaft stays inside it over the whole CH_STROKE pull
    cut.append(L.box("_chn", -0.0068, 0.0068, -0.052, 0.040, CH_Z0 - 0.0012, 0.080, mat=M["dark"]))
    # forward-assist bore: 0.8 mm clearance around the plunger cap, deep enough for a 4 mm push
    cut.append(L.cyl("_fab", FA_CAP_R + 0.0008, "Y", FA_CAP_Y[0] - 0.0060, 0.040, c=FA_AXIS, segs=16,
                     mat=M["dark"]))
    # shooter's-left (+X) panel line: one 0.9 mm groove framing the upper's flat (brief, optional detail; v09)
    o = L.round_poly([(UP_PANEL[0], UP_PANEL[2]), (UP_PANEL[1], UP_PANEL[2]), (UP_PANEL[1], UP_PANEL[3]),
                      (UP_PANEL[0], UP_PANEL[3])], 0.0025, 3)
    i = L.round_poly([(UP_PANEL[0] + 0.0009, UP_PANEL[2] + 0.0009), (UP_PANEL[1] - 0.0009, UP_PANEL[2] + 0.0009),
                      (UP_PANEL[1] - 0.0009, UP_PANEL[3] - 0.0009), (UP_PANEL[0] + 0.0009, UP_PANEL[3] - 0.0009)],
                     0.0016, 3)
    cut.append(L.tube("_upl", o, i, "X", 0.0152 - 0.0006, 0.03, mat=M["graphite"]))
    L.boolean(up, cut)
    L.clean(up)

    def bevel_edge(e):
        if L.edge_angle_deg(e) < 30:
            return False
        m = (e.verts[0].co + e.verts[1].co) / 2
        if m.x > 0.0140 and UP_PANEL[0] - 0.001 < m.y < UP_PANEL[1] + 0.001 and \
                UP_PANEL[2] - 0.001 < m.z < UP_PANEL[3] + 0.001:
            return False  # keep the panel-line groove crisp (the 1.6 mm bevel would eat a 0.9 mm groove)
        return True
    # r2 round 2: one-segment 1.6 mm chamfers like the lower (the 2-segment round only existed on paper: Blender's
    # global clamp squashed it to 0.01 mm; now that the bevel is real, a crisp chamfer keeps the receiver planar
    # and the default loadout inside 22k)
    L.finish(up, bevel=0.0016, segs=1, weight_fn=bevel_edge)
    up = L.join([up] + build_shoulder_pads(), "MAKO_Upper")
    L.finish(up, bevel=0)   # keeps the joined parts' own custom normals / sharp edges
    return up


def well_front(z):
    """Magwell front face y at height z: AR-style, raked forward about 10 deg toward the flared lip."""
    return -0.1590 - (0.012 - z) * 0.175


def build_lower():
    body_pts = [(-0.158, 0.024), (well_front(-0.026) + 0.003, -0.028), (-0.080, -0.028), (-0.080, -0.006),
                (-0.072, 0.000), (0.018, 0.000), (0.030, 0.008), (0.036, 0.020), (0.036, 0.046),
                (0.014, 0.046)] + rear_sweep()
    low = P("MAKO_Lower", body_pts, -0.0152, 0.0152, M["graphite"])
    well = P("_well", [(well_front(0.012), 0.012), (well_front(-0.030), -0.030), (-0.0790, -0.030),
                       (-0.0790, 0.004), (-0.0840, 0.010)], -0.0170, 0.0170)
    # flared lip (r2 review): 2.8 mm per side and 4 mm forward over the bottom 15 mm, a lip, not a bucket
    lf = well_front(-0.0250)
    lip = P("_lip", [(lf - 0.0040, -0.0405), (-0.0765, -0.0405), (-0.0765, -0.0335), (-0.0790, -0.0250),
                     (lf, -0.0250), (lf - 0.0040, -0.0345)], -0.0198, 0.0198)
    L.intersect(lip, S("_lps", sym([(0.0170, -0.020), (0.0170, -0.0250), (0.0198, -0.0340), (0.0198, -0.050)]),
                       -0.18, -0.07))
    guard = P("_guard", [(-0.0815, 0.002), (-0.0815, -0.031), (-0.0745, -0.0375), (-0.0225, -0.0375),
                         (-0.0120, -0.0270), (-0.0120, 0.002)], -0.0065, 0.0065)
    # round boss around the buffer-tube entry (lower half; the upper carries the top half)
    ring = L.cyl("_ring", 0.0192, "Y", 0.014, 0.036, c=(0, BORE_Z), segs=24)
    L.intersect(ring, L.box("_rb", -0.03, 0.03, 0.0, 0.05, 0.020, 0.046))
    # bolt-catch boss with two ears (+X, shooter's left), sized for the larger r2 paddle
    boss = P("_bkboss", L.round_poly([(-0.0830, 0.0010), (-0.0570, 0.0010), (-0.0570, 0.0235), (-0.0830, 0.0235)],
                                     0.003, 2), 0.0140, 0.0166)
    # raised rib along the magwell front edge (both sides), raked with the front face
    ribs = [P("_wrib", [(well_front(-0.027) + 0.0040, -0.0270), (well_front(-0.027) + 0.0100, -0.0270),
                        (well_front(0.006) + 0.0100, 0.0060), (well_front(0.006) + 0.0060, 0.0100)], -0.0184,
              0.0184)]
    # pivot-pin and takedown-pin bosses (both sides): the pin heads sit in raised rings (v09)
    for (y, z, r) in ((-0.1525, 0.0170, 0.0058), (0.0255, 0.0330, 0.0060)):
        ribs.append(L.cyl("_pboss", r, "X", -0.0160, 0.0160, c=(y, z), segs=16))
    L.boolean(low, [well, lip, guard, ring, boss] + ribs, op="UNION", transfer=False)
    cut = []
    cut.append(P("_ghole", L.round_poly([(-0.0760, -0.0002), (-0.0760, -0.0320), (-0.0240, -0.0320),
                                          (-0.0170, -0.0245), (-0.0170, -0.0002)], 0.004, 2), -0.02, 0.02))
    cut.append(L.box("_trs", -0.0045, 0.0045, -0.0535, -0.0310, -0.004, 0.009, mat=M["dark"]))
    cut.append(L.box("_cav", -0.0135, 0.0135, -0.1535, -0.0865, -0.060, 0.016, mat=M["dark"]))
    cut.append(L.loft("_fun", [(-0.0430, [(-0.0172, -0.1572), (0.0172, -0.1572), (0.0172, -0.0828),
                                          (-0.0172, -0.0828)]),
                               (-0.0355, [(-0.0135, -0.1535), (0.0135, -0.1535), (0.0135, -0.0865),
                                          (-0.0135, -0.0865)])], "Z", mat=M["dark"]))
    # bolt-catch channel between the ears
    cut.append(L.box("_bkch", 0.0153, 0.03, -0.0778, -0.0642, -0.002, 0.03))
    # mag-release well (shooter's right, -X)
    cut.append(L.cyl("_mrf", 0.0068, "X", -0.03, -0.0140, c=(-0.0720, 0.0090), segs=16, mat=M["graphite"]))
    # grip grooves on the magwell front
    for z in (-0.006, -0.012, -0.018):
        yf = well_front(z)
        cut.append(L.box("_wg", -0.012, 0.012, yf - 0.004, yf + 0.0006, z - 0.0009, z + 0.0009))
    # recessed side panels on the magwell (both sides) - the classic AR lower read
    pan = L.round_poly([(-0.1470, -0.0215), (-0.0960, -0.0215), (-0.0960, 0.0050), (-0.1470, 0.0050)], 0.003, 2)
    cut.append(P("_wp", pan, 0.0160, 0.03, M["graphite"]))
    cut.append(P("_wp", pan, -0.03, -0.0160, M["graphite"]))
    L.boolean(low, cut)
    L.clean(low)

    def visible_edge(e):
        if L.edge_angle_deg(e) < 30:
            return False
        m = (e.verts[0].co + e.verts[1].co) / 2
        if abs(m.x) < 0.0138 and -0.1540 < m.y < -0.0860 and -0.0345 < m.z < 0.0170:
            return False  # inside the magwell
        if abs(m.x) < 0.0047 and -0.0540 < m.y < -0.0305 and -0.0005 < m.z < 0.0095:
            return False  # inside the trigger slot
        return True
    # one-segment 1.5 mm chamfers (r2: the 2-segment round doubled the lower to 4.2k tris; a crisp chamfer keeps
    # the planar stylised read and the default loadout inside the 22k budget)
    L.finish(low, bevel=0.0015, segs=1, weight_fn=visible_edge)
    return low


def rrect_yx(yf, yb, hw, rf, rb, segs=3):
    """Rounded rectangle in (y, x): front edge y = yf (toward -Y), back edge y = yb, half width hw.
    Front corners radius rf, back corners rb. CCW seen from +Z. Returns [(y, x), ...]."""
    pts = []

    def arc(cy, cx, r, a0, a1):
        for k in range(segs + 1):
            a = a0 + (a1 - a0) * k / segs
            pts.append((cy + r * math.cos(a), cx + r * math.sin(a)))
    arc(yb - rb, -hw + rb, rb, -math.pi / 2, 0.0)          # back-right (-X)
    arc(yb - rb, hw - rb, rb, 0.0, math.pi / 2)            # back-left (+X)
    arc(yf + rf, hw - rf, rf, math.pi / 2, math.pi)        # front-left
    arc(yf + rf, -hw + rf, rf, math.pi, 1.5 * math.pi)     # front-right
    return pts


def catmull(keys, n_between):
    """Catmull-Rom resample of a list of equal-length tuples (keys); n_between extra samples per span (an int, or
    one int per span)."""
    out = []
    m = len(keys)
    for i in range(m - 1):
        p0 = keys[max(i - 1, 0)]
        p1, p2 = keys[i], keys[i + 1]
        p3 = keys[min(i + 2, m - 1)]
        nb = n_between[i] if isinstance(n_between, (list, tuple)) else n_between
        for s in range(nb + 1):
            t = s / (nb + 1)
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 +
                                    (-a + 3 * b - 3 * c + d) * t3) for a, b, c, d in zip(p0, p1, p2, p3)))
    out.append(keys[-1])
    return out


# grip key sections (horizontal slices): z, y_front, y_back, half width, r_front, r_back, tilt dz/dy
# Review fix (v09): beavertail lip tucked under the buffer tower, backstrap palm swell (+5 mm at z -0.055),
# flared base (~2.5 mm front/back, +1.5 mm per side).
# r2 review, round 2: v09's A2-style front strap -> one finger knuckle at z -0.045 standing ~3.5 mm proud of the
# front line, with a shallow finger valley above (middle finger) and below (ring finger).
GRIP_KEYS = [(0.0050, -0.0172, 0.0270, 0.0128, 0.0045, 0.0060, 0.00),   # top, inside the lower (r2: the old
             #                                                               top poked out behind the lower)
             (-0.0020, -0.0150, 0.0415, 0.0136, 0.0055, 0.0080, 0.00),  # beavertail tang
             (-0.0110, -0.0118, 0.0405, 0.0146, 0.0062, 0.0095, 0.00),  # web of the hand
             (-0.0240, -0.0080, 0.0418, 0.0152, 0.0065, 0.0105, 0.00),
             (-0.0330, -0.0040, 0.0464, 0.0155, 0.0066, 0.0108, 0.00),  # middle-finger valley
             (-0.0450, -0.0062, 0.0518, 0.0158, 0.0072, 0.0111, 0.007),  # finger knuckle + palm swell
             (-0.0570, 0.0022, 0.0558, 0.0160, 0.0066, 0.0112, 0.022),   # ring-finger valley, palm swell max
             (-0.0700, 0.0040, 0.0580, 0.0158, 0.0068, 0.0110, 0.04),
             (-0.0850, 0.0105, 0.0596, 0.0154, 0.0066, 0.0108, 0.07),
             (-0.0970, 0.0140, 0.0620, 0.0160, 0.0066, 0.0106, 0.10),   # base flare
             (-0.1050, 0.0145, 0.0665, 0.0172, 0.0064, 0.0102, 0.13),
             (-0.1095, 0.0160, 0.0668, 0.0170, 0.0060, 0.0096, 0.14)]


def build_grip():
    """Lofted polymer grip (v09): raked ~20 deg, finger swell on the front, palm swell, flared base, beavertail,
    stippled side panels (recessed 0.9 mm)."""
    rake = 0.06  # extra shear (dy per -dz): about +3.4 deg of rake over the key table
    keys = [(z, yf - rake * z, yb - rake * z, hw, rf, rb, t) for (z, yf, yb, hw, rf, rb, t) in GRIP_KEYS]
    # r2: two in-between rings over the beavertail and the finger knuckle (one shaded lumpy there), one elsewhere
    secs_d = catmull(keys, [2, 2, 1, 2, 2, 2, 2, 1, 1, 1, 1])
    # bottom chamfer ring
    z, yf, yb, hw, rf, rb, tilt = secs_d[-1]
    secs_d.append((z - 0.0025, yf + 0.0025, yb - 0.0025, hw - 0.0025, rf - 0.0015, rb - 0.0025, tilt))
    secs = []
    for (z, yf, yb, hw, rf, rb, tilt) in secs_d:
        ym = (yf + yb) / 2
        ring = rrect_yx(yf, yb, hw, rf, rb, 3)
        secs.append([(x, y, z + tilt * (y - ym)) for (y, x) in ring])
    bm = bmesh.new()
    rings = [[bm.verts.new(co) for co in r] for r in secs]
    n = len(rings[0])
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    g = L.new_obj("MAKO_Grip", bm, BASE, M["bone"])
    # stippled side panel: follows the flat part of the sides between z -0.020 and -0.092
    fr, bk = [], []
    for (z, yf, yb, hw, rf, rb, tilt) in secs_d:
        if -0.093 <= z <= -0.019:
            ym = (yf + yb) / 2
            yf2, yb2 = yf + rf + 0.0030, yb - rb - 0.0030
            fr.append((yf2, z + tilt * (yf2 - ym)))
            bk.append((yb2, z + tilt * (yb2 - ym)))
    # r2 round 2: pull the panel's top and bottom edges 1.2 mm off the loft rings they were sampled on (an outline
    # edge lying exactly on a ring line left collinear vertices -> zero-area triangles after the boolean)
    for lst in (fr, bk):
        lst[0] = (lst[0][0], lst[0][1] - 0.0012)
        lst[-1] = (lst[-1][0], lst[-1][1] + 0.0012)
    panel = L.round_poly(fr + list(reversed(bk)), 0, 2,
                         radii=[0.004] + [0.0] * (len(fr) - 2) + [0.004, 0.004] + [0.0] * (len(bk) - 2) + [0.004])
    cut = [P("_gp", panel, 0.0141, 0.03, M["stipple"]), P("_gp", panel, -0.03, -0.0141, M["stipple"])]
    L.boolean(g, cut)
    L.clean(g)
    L.finish(g, bevel=0.0005, segs=1, angle=50, smooth_angle=40)
    return g


def build_trigger():
    pts = [(-0.0355, 0.010), (-0.0440, 0.010), (-0.0440, 0.004), (-0.0470, -0.010), (-0.0500, -0.0215),
           (-0.0455, -0.0240), (-0.0420, -0.0120), (-0.0380, -0.0020), (-0.0355, 0.004)]
    pts = L.round_poly(pts, 0, 2, radii=[0, 0, 0, 0.004, 0.002, 0.002, 0.004, 0.003, 0])
    t = P("MAKO_Trigger", pts, -0.0032, 0.0032, M["gunmetal"])
    L.finish(t, bevel=0.0008, segs=1, angle=30)
    L.set_origin(t, (0.0, -0.040, 0.012))
    return t


# Handguard section (review fix): deeper and squarer than the brief's octagon, closer to v09. The rail base
# (0.0745), bore (0.050) and side-rail faces (x +-0.023 at z 0.050) stay where the shared attachments expect them;
# only the bottom drops (0.025 -> HG_BOT) and the corner chamfers shrink (10 mm -> 5 mm top, 7.5 mm bottom).
HG_BOT = 0.017
HG_OUTER = [(0.018, 0.0745), (-0.018, 0.0745), (-0.023, 0.0695), (-0.023, 0.0245), (-0.0155, HG_BOT),
            (0.0155, HG_BOT), (0.023, 0.0245), (0.023, 0.0695)]
HG_WALL = 0.0028
SLOT_Y = [-0.462 + 0.032 * k for k in range(9)]
SLOT_ROWS_Z = (0.0570, 0.0385)          # two rows of pill slots on each side face
SLOT_SIDE = (0.0245, 0.0080)            # side-face slot length x height
SLOT_CHAMFER = (0.0230, 0.0064)         # third row, on the lower chamfers
SLOT_CAP_SEGS = 8                       # end-cap segments: round pills (r2 review: 2-4 read as hexagons / octagons;
                                        # 22.5 deg steps stay under the 30 deg bevel/sharp limit, so the caps shade round)
SIDE_RAIL_Y = (-0.474, -0.424)


def point_in(poly, p):
    x, y = p
    ins = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xi:
                ins = not ins
    return ins


def build_handguard():
    inner = L.offset_poly(HG_OUTER, HG_WALL)
    hg = L.tube("MAKO_Handguard", HG_OUTER, inner, "Y", HG_FRONT, HG_REAR, BASE, M["graphite"])
    # r3: rear bulkhead (barrel-nut plate). The handguard is wider than the upper, so from the first-person angle
    # its open rear end showed the hollow inside (and daylight through the slots) at the receiver joint.
    cap = S("_hgcap", L.offset_poly(HG_OUTER, HG_WALL * 0.5), HG_REAR - 0.0045, HG_REAR, M["graphite"])
    L.boolean(hg, cap, op="UNION", transfer=False)
    L.clean(hg)
    cut = []
    # lower chamfer: 45 deg face from (0.023, 0.0245) to (0.0155, HG_BOT); third slot row sits on its midline
    ch_x, ch_z = (0.023 + 0.0155) / 2, (0.0245 + HG_BOT) / 2
    for k, yc in enumerate(SLOT_Y):
        under_side_rail = SIDE_RAIL_Y[0] - 0.002 < yc < SIDE_RAIL_Y[1] + 0.008
        if not under_side_rail:
            for zc in SLOT_ROWS_Z:
                cut.append(P("_s", L.stadium_pts(SLOT_SIDE[0], SLOT_SIDE[1], SLOT_CAP_SEGS, yc, zc), -0.03, 0.03,
                             M["dark"]))
        for sgn in (1, -1):  # third row on the bottom chamfers
            c = P("_c", L.stadium_pts(SLOT_CHAMFER[0], SLOT_CHAMFER[1], SLOT_CAP_SEGS, yc, 0.0), -0.006, 0.006,
                  M["dark"])
            L.rotate(c, "Y", 45 if sgn > 0 else 135)
            L.move(c, (sgn * ch_x, 0, ch_z))
            cut.append(c)
    # bottom-front chamfer
    cut.append(P("_fc", [(-0.510, 0.002), (-0.476, 0.002), (-0.510, 0.036)], -0.03, 0.03))
    # QD sling cups near the rear, both sides (between the two slot rows)
    for sgn in (1, -1):
        x0, x1 = (0.0215, 0.03) if sgn > 0 else (-0.03, -0.0215)
        cut.append(L.cyl("_qd", 0.0062, "X", x0, x1, c=(-0.1835, 0.0478), segs=16, mat=M["graphite"]))
        h0, h1 = (0.016, 0.03) if sgn > 0 else (-0.03, -0.016)
        cut.append(L.cyl("_qh", 0.0033, "X", h0, h1, c=(-0.1835, 0.0478), segs=12, mat=M["dark"]))
    L.boolean(hg, cut)
    L.clean(hg)
    inner_test = L.offset_poly(HG_OUTER, HG_WALL * 0.5)

    def outer_edge(e):
        if L.edge_angle_deg(e) < 30:
            return False
        for f in e.link_faces:
            c = f.calc_center_median()
            if point_in(inner_test, (c.x, c.z)) and HG_FRONT + 0.001 < c.y < HG_REAR - 0.001:
                return False
        return True
    L.finish(hg, bevel=0.0009, segs=1, weight_fn=outer_edge, smooth_angle=50)
    return hg


def build_rails():
    top, top_c = L.rail("MAKO_Rail", -0.493, 0.022, M["graphite"], BASE)
    L.place_rail(top, (0, 0, RAIL_BASE), "+Z")
    bot, bot_c = L.rail("MAKO_RailBottom", -0.400, -0.270, M["graphite"], BASE)
    L.place_rail(bot, (0, 0, HG_BOT), "-Z")
    side_r, side_c = L.rail("MAKO_RailSide_R", SIDE_RAIL_Y[0], SIDE_RAIL_Y[1], M["graphite"], BASE)
    L.place_rail(side_r, (-0.023, 0, BORE_Z), "-X")
    side_l, _ = L.rail("MAKO_RailSide_L", SIDE_RAIL_Y[0], SIDE_RAIL_Y[1], M["graphite"], BASE)
    L.place_rail(side_l, (0.023, 0, BORE_Z), "+X")
    for r in (top, bot, side_r, side_l):  # convex-only bevels keep the rail cheap
        me = r.data
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.edges.ensure_lookup_table()
        fl = [convex_sharp(40)(e) for e in bm.edges]
        w = r.modifiers["Bevel"].width
        off = L.local_bevel_offsets(bm, fl, w)   # per-edge, non-overlapping (see L.finish)
        bm.free()
        at = me.attributes.get("bevel_weight_edge") or me.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
        for i in range(len(me.edges)):
            at.data[i].value = off.get(i, 0.0) / w
    return (top, bot, side_r, side_l), top_c, bot_c, side_c


def build_barrel():
    br = L.cyl("MAKO_Barrel", 0.0095, "Y", -0.513, -0.150, c=(0, BORE_Z), segs=20, col=BASE, mat=M["gunmetal"])
    gb = L.box("_gb", -0.0105, 0.0105, -0.407, -0.389, 0.0395, 0.0668, mat=M["gunmetal"])
    gt = L.cyl("_gt", 0.0022, "Y", -0.392, -0.168, c=(0, 0.0628), segs=8, mat=M["gunmetal"])
    L.finish(gb, bevel=0.0012, segs=1, uv=False)
    for o in (br, gt):   # sharp edges must exist before the join (the joined mesh keeps them, see L.finish)
        L.finish(o, bevel=0, smooth_angle=40, uv=False)
    br = L.join([br, gb, gt], "MAKO_Barrel")
    L.finish(br, bevel=0, smooth_angle=40)
    return br


def build_flash_hider():
    prof = [(0, 0.039), (0.0068, 0.039), (0.0068, 0.0), (0.0094, 0.0), (0.0114, 0.0018), (0.0114, 0.0365),
            (0.0102, 0.0395), (0.0102, 0.0420), (0.0118, 0.0420), (0.0126, 0.0428), (0.0126, 0.0466),
            (0.0118, 0.0474), (0.0101, 0.0474), (0.0101, 0.0490), (0.0118, 0.0490), (0.0126, 0.0498),
            (0.0126, 0.0536), (0.0118, 0.0544), (0.0097, 0.0544), (0.0097, 0.0560), (0, 0.0560)]
    fh = L.lathe_y("MAKO_FlashHider", prof, MUZZLE_Y, 1, c=(0, BORE_Z), steps=16, col=BASE, mat=M["gunmetal"])
    fh.data.materials.append(M["dark"])
    for p in fh.data.polygons:  # bore interior dark
        c = p.center
        if math.hypot(c.x, c.z - BORE_Z) < 0.0075:
            p.material_index = 1
    cut = []
    for ang in (90, 150, 210, 330, 30):  # A2-style: closed bottom
        c = L.prism("_fs", L.stadium_pts(0.025, 0.0036, 4, 0.0, 0.0), "X", 0.005, 0.016, mat=M["dark"])
        # pill lies in the (y, z) plane, extruded radially along +X -> rotate about Y to the slot angle
        L.rotate(c, "Y", -ang)
        L.move(c, (0, MUZZLE_Y + 0.0195, BORE_Z))
        cut.append(c)
    L.boolean(fh, cut)
    L.clean(fh)
    L.finish(fh, bevel=0.0005, segs=1, angle=60, smooth_angle=40)
    return fh


def build_buffer_tube():
    L_t = STOCK_SOCKET[1] - TUBE_Y0
    prof = [(0, 0), (TUBE_R, 0), (TUBE_R, L_t - 0.006), (TUBE_R - 0.001, L_t), (0.0, L_t)]
    tb = L.lathe_y("MAKO_BufferTube", prof, TUBE_Y0, 1, c=(0, BORE_Z), steps=24, col=BASE, mat=M["graphite"])
    # anti-rotation key under the tube, 1.2 mm proud (r3: was 2.6 mm, which put the stocks' key-slot floor on their
    # own bottom faces)
    key = L.box("_key", -0.0035, 0.0035, 0.050, 0.212, BORE_Z - 0.0172, BORE_Z - 0.0140)
    L.boolean(tb, key, op="UNION", transfer=False)
    L.finish(tb, bevel=0.0008, segs=1, angle=40, smooth_angle=40, uv=False)
    tb = L.join([tb, build_castle_nut()], "MAKO_BufferTube")
    L.finish(tb, bevel=0, smooth_angle=30)
    return tb


def build_castle_nut():
    """Castle nut as a hollow ring (outer notched outline, inner circle on the tube): every face is a planar quad,
    lug faces are split from the notch walls by sharp edges, so no pinched / wavy highlights (review fix).
    Graphite like the tube (the gunmetal nut mirrored the studio into speckles right in the first-person view)."""
    outer, inner = [], []
    r_in = TUBE_R - 0.0015
    for k in range(6):
        c = 90 + 60 * k            # a notch on top, under the charging-handle path
        for (a, r) in [(c - 8, NUT_R), (c - 8, NUT_R - 0.0026), (c + 8, NUT_R - 0.0026), (c + 8, NUT_R)] + \
                [(c + 8 + 44 * j / 6, NUT_R) for j in range(1, 6)]:
            outer.append((r * math.cos(math.radians(a)), BORE_Z + r * math.sin(math.radians(a))))
            # inner ring vertex at the same angle (notch-wall pairs share an angle -> radial quads)
            inner.append((r_in * math.cos(math.radians(a)), BORE_Z + r_in * math.sin(math.radians(a))))
    nut = L.tube("_nut", outer, inner, "Y", NUT_Y[0], NUT_Y[1], mat=M["graphite"])
    # paired notch-wall vertices sit at the same angle: merge the duplicated inner verts
    L.clean(nut, dist=1e-7, dissolve_angle=0)
    # sharp at 25 deg, 0.5 mm chamfers on edges over 40 deg with per-edge safe offsets (L.finish)
    L.finish(nut, bevel=0.0005, segs=1, angle=40, smooth_angle=25, uv=False)
    bc.apply_modifiers(nut)
    return nut


def build_charging_handle():
    """T-handle on top of the upper's rear. Review fix: the whole part rides at z >= CH_Z0 (0.0702), above the
    buffer tube (top 0.066) and the castle nut (top 0.0694), so the CH_STROKE pull (+Y) is clean; the shaft sits in
    the upper's channel, under the rail base, and the T-wings stand 4.7 mm proud behind the rail end."""
    # the shaft reaches forward to y -0.046, so at full stroke it still runs inside the upper's channel
    shaft = T("MAKO_ChargingHandle", [(-0.0055, -0.046), (0.0055, -0.046), (0.0055, 0.0320), (-0.0055, 0.0320)],
              CH_Z0, CH_Z1, M["graphite"])
    plan = [(-0.0055, 0.0290), (0.0055, 0.0290), (0.0055, 0.0305), (0.0170, 0.0335), (0.0210, 0.0355),
            (0.0210, 0.0400), (0.0185, 0.0425), (-0.0200, 0.0425), (-0.0232, 0.0400), (-0.0232, 0.0345),
            (-0.0190, 0.0320), (-0.0055, 0.0305)]
    wings = T("_chw", plan, CH_Z0, CH_WING_Z1, M["graphite"])
    # latch (shooter's right, -X): raised grip ridges on top of the wing
    rid = [L.box("_lr", -0.0228 + 0.0042 * i, -0.0208 + 0.0042 * i, 0.0338, 0.0415, CH_WING_Z1 - 0.0004,
                 CH_WING_Z1 + 0.0012) for i in range(3)]
    L.boolean(shaft, [wings] + rid, op="UNION", transfer=False)
    L.clean(shaft)
    L.finish(shaft, bevel=0.0008, segs=1, angle=30)
    L.set_origin(shaft, (0.0, 0.030, RAIL_BASE))
    shaft["stroke_m"] = CH_STROKE
    shaft["motion"] = "translate +Y (rearward) by stroke_m"
    return shaft


def build_forward_assist():
    """Plunger cap in its own bore at the rear of the -X housing (review fix: it no longer pokes out of the upper's
    rear face into the tube / castle nut, and a FA_PUSH press toward -Y stays inside the bore)."""
    y0, y1 = FA_CAP_Y
    # plain cylinder with n-gon end caps (r2: a lathe's pole fan + the end grooves left a hole in the end face)
    fa = L.cyl("MAKO_ForwardAssist", FA_CAP_R, "Y", y0, y1, c=FA_AXIS, segs=16, col=BASE, mat=M["gunmetal"])
    # three shallow grip grooves across the end face
    grooves = [L.box("_fg", FA_AXIS[0] - 0.0050, FA_AXIS[0] + 0.0050, y1 - 0.0006, y1 + 0.002,
                     FA_AXIS[1] + dz - 0.00045, FA_AXIS[1] + dz + 0.00045) for dz in (-0.0026, 0.0, 0.0026)]
    L.boolean(fa, grooves)
    L.clean(fa)
    L.finish(fa, bevel=0.0006, segs=1, angle=40, smooth_angle=40)
    L.set_origin(fa, (FA_AXIS[0], y1, FA_AXIS[1]))
    fa["push_m"] = FA_PUSH
    fa["motion"] = "translate -Y (forward) by push_m"
    return fa


def build_dust_cover():
    plate = L.round_poly([(-0.0896, 0.0412), (-0.0304, 0.0412), (-0.0304, 0.0624), (-0.0896, 0.0624)], 0.0016, 2)
    dc = P("MAKO_DustCover", plate, -0.0170, -0.0151, M["graphite"])
    rib = P("_rib", [(-0.0860, 0.0545), (-0.0360, 0.0545), (-0.0360, 0.0565), (-0.0860, 0.0565)], -0.0179,
            -0.0160)
    bump = P("_bump", [(-0.0370, 0.0585), (-0.0320, 0.0585), (-0.0320, 0.0612), (-0.0370, 0.0612)], -0.0181,
             -0.0160)
    rod = L.cyl("_rod", 0.0017, "Y", -0.0925, -0.0275, c=(-0.0160, 0.0410), segs=10)
    L.boolean(dc, [rib, bump, rod], op="UNION", transfer=False)
    L.clean(dc)
    L.finish(dc, bevel=0.0005, segs=1, angle=30)
    L.set_origin(dc, (-0.0160, -0.060, 0.0410))
    return dc


def build_bolt_catch():
    """r2 review: a readable ~12 x 22 mm paddle (v09) with a lower lever standing 1.5 mm prouder than the paddle,
    three grip ribs on the upper (press) half. Pivots about X on its roll pin (origin)."""
    pts = L.round_poly([(-0.0772, 0.0030), (-0.0648, 0.0030), (-0.0648, 0.0175), (-0.0636, 0.0228),
                        (-0.0690, 0.0262), (-0.0772, 0.0240)], 0.0015, 2)
    bk = P("MAKO_BoltCatch", pts, 0.0153, 0.0192, M["graphite"])
    lever = P("_bkl", L.round_poly([(-0.0766, 0.0034), (-0.0654, 0.0034), (-0.0654, 0.0102), (-0.0766, 0.0102)],
                                   0.0014, 2), 0.0180, 0.0207)
    ribs = [P("_bkr", [(-0.0742, 0.0150 + 0.0026 * i), (-0.0662, 0.0150 + 0.0026 * i),
                       (-0.0662, 0.0162 + 0.0026 * i), (-0.0742, 0.0162 + 0.0026 * i)], 0.0186, 0.0199)
            for i in range(3)]
    L.boolean(bk, [lever] + ribs, op="UNION", transfer=False)
    L.clean(bk)
    L.finish(bk, bevel=0.0005, segs=1)
    L.set_origin(bk, (0.0170, -0.0710, 0.0060))
    return bk


def build_mag_release():
    prof = [(0, 0), (0.0048, 0), (0.0048, 0.0040), (0.0040, 0.0050), (0, 0.0050)]
    mr = L.lathe_y("MAKO_MagRelease", prof, 0.0, 1, steps=16, col=BASE, mat=M["gunmetal"])
    # lathe_y revolves around Y; turn it to point along -X
    L.rotate(mr, "Z", 90)
    L.move(mr, (-0.0140, -0.0720, 0.0090))
    L.finish(mr, bevel=0.0004, segs=1, angle=50, smooth_angle=40)
    L.set_origin(mr, (-0.0152, -0.0720, 0.0090))
    return mr


def build_selector():
    hub = L.cyl("MAKO_Selector", 0.0056, "X", 0.0150, 0.0178, c=(0.0060, 0.0125), segs=16, col=BASE,
                mat=M["gunmetal"])
    lever = P("_lev", L.round_poly([(0.0080, 0.0100), (-0.0120, 0.0108), (-0.0150, 0.0125), (-0.0120, 0.0145),
                                    (0.0080, 0.0150)], 0.001, 1), 0.0170, 0.0200)
    L.boolean(hub, lever, op="UNION", transfer=False)
    L.clean(hub)
    L.finish(hub, bevel=0.0005, segs=1, angle=40)
    L.set_origin(hub, (0.0164, 0.0060, 0.0125))  # rotates about the hub axis (X)
    return hub


def build_pins():
    pins = []
    for (y, z, r) in ((-0.1530, 0.0170, 0.0037), (0.0255, 0.0330, 0.0037), (-0.0400, 0.0120, 0.0027),
                      (-0.0200, 0.0165, 0.0027)):
        pins.append(L.cyl("_pin", r, "X", -0.0163, 0.0163, c=(y, z), segs=12, mat=M["gunmetal"]))
    p = L.join(pins, "MAKO_Pins")
    L.finish(p, bevel=0.0004, segs=1, angle=50, smooth_angle=40)
    return p


# ===================================================================================================== STOCKS
STD_SLEEVE_TOP = 0.0694      # stock_standard: top of the front sleeve (CH wings ride at z >= 0.0702)
STD_BORE_R = 0.0164          # stock_standard: tube channel (tube r 0.016), leaves a 3 mm sleeve wall on top
PREC_TOP = 0.0745            # stock_precision's flat top
PREC_CHEEK = (0.116, 0.238)  # cheek comb footprint, y front/back (r2: seated on the stock, no gap, no posts)
PREC_CHEEK_HW = 0.0150       # comb half width at its base (the stock's flat top is +-0.018 wide)
PREC_LINE = 0.0006           # panel-line groove around the comb base (width = depth)


def cheek_plan(grow):
    """Plan outline (x, y) of the precision cheek comb's footprint, grown outward by `grow`."""
    return L.round_poly([(-PREC_CHEEK_HW - grow, PREC_CHEEK[0] - grow), (PREC_CHEEK_HW + grow, PREC_CHEEK[0] - grow),
                         (PREC_CHEEK_HW + grow, PREC_CHEEK[1] + grow), (-PREC_CHEEK_HW - grow, PREC_CHEEK[1] + grow)],
                        0.004 + grow, 3)


def key_slot(y0, y1):
    """Channel for the buffer tube's bottom key, so every stock slides on the tube without clipping it."""
    return L.box("_kslot", -0.0043, 0.0043, y0, y1, BORE_Z - 0.0182, BORE_Z - 0.0100, mat=M["dark"])


def build_stock_standard():
    col = COL["MAKO_stock_standard"]
    # review fix: toe 4 mm lower and 2.5 mm longer, leg and butt post ~10 % thicker (v09 reads chunkier).
    # r2: the top line rises from a low front sleeve (just over the tube, like v09/v04) to the butt, which also
    # keeps the charging handle's pull clear over more of the collapse range (see STOCK_CH_STROKE).
    # r3: the front 48 mm stay at z <= STD_SLEEVE_TOP (under the charging handle's wings, z 0.0702), so the full
    # CH_STROKE pull is clean at every collapse position (the engine needs no per-position clamp any more).
    side = [(0.098, 0.030), (0.098, 0.0635), (0.1035, STD_SLEEVE_TOP), (0.146, STD_SLEEVE_TOP), (0.262, 0.0835),
            (0.262, -0.058), (0.2415, -0.058), (0.1665, 0.0105), (0.156, 0.0105), (0.146, 0.005), (0.126, 0.005),
            (0.116, 0.016), (0.108, 0.028)]
    side = L.round_poly(side, 0, 2, radii=[0.003, 0.003, 0.004, 0.030, 0.003, 0.003, 0.004, 0.008, 0.003, 0.003,
                                          0.003, 0.004, 0.003])
    sec = sym([(0.0125, 0.090), (0.0205, 0.064), (0.0205, 0.030), (0.0160, 0.022), (0.0160, -0.080)])
    st = P("MAKO_stock_standard", side, -0.026, 0.026, M["bone"], col)
    L.intersect(st, S("_ss", sec, 0.09, 0.27, col=col))
    cut = []
    tri = L.round_poly([(0.1690, 0.0280), (0.2445, 0.0280), (0.2445, -0.0380)], 0.005, 3)
    cut.append(P("_sto", tri, -0.03, 0.03, M["bone"], col))
    cut.append(L.cyl("_stc", STD_BORE_R, "Y", 0.090, STD_CHANNEL_END, c=(0, BORE_Z), segs=24, mat=M["dark"]))
    cut.append(key_slot(0.090, STD_CHANNEL_END))
    L.boolean(st, cut)
    L.clean(st)
    L.finish(st, bevel=0.0028, segs=2, angle=30, smooth_angle=35)
    pad_pts = L.round_poly([(0.2615, 0.0845), (0.2710, 0.0845), (0.2775, 0.0760), (0.2792, -0.0520),
                            (0.2752, -0.0635), (0.2615, -0.0640)], 0.002, 2)
    pad = P("MAKO_stock_standard_ButtPad", pad_pts, -0.0235, 0.0235, M["rubber"], col)
    L.intersect(pad, S("_ps", sym([(0.0165, 0.095), (0.0235, 0.080), (0.0235, -0.064), (0.0185, -0.074)]), 0.25,
                       0.29, col=col))
    grooves = [L.box("_pg", -0.03, 0.03, 0.2765, 0.29, z - 0.0011, z + 0.0011) for z in (0.045, 0.015, -0.015,
                                                                                         -0.040)]
    L.boolean(pad, grooves, transfer=False)
    L.clean(pad)
    L.finish(pad, bevel=0.0025, segs=1, angle=30)
    lever = L.box("MAKO_stock_standard_Lever", -0.0065, 0.0065, 0.186, 0.226, 0.0240, 0.0290, col=col,
                  mat=M["graphite"])
    lv2 = L.box("_lv2", -0.0055, 0.0055, 0.127, 0.148, 0.0015, 0.0065, mat=M["graphite"])
    lever = L.join([lever, lv2], "MAKO_stock_standard_Lever")
    L.finish(lever, bevel=0.0010, segs=1)
    # sling loop under the leg (v09). r2 review: the 2.5 mm wire ring vanished at gameplay distance and was the only
    # "noodly" part -> a chunky swivel: 4 mm ring section, 4.4 mm thick, on a 5 mm swivel post.
    yc, zc = 0.1990, -0.0345
    loop_o = L.round_poly([(yc - 0.0105, zc + 0.0105), (yc + 0.0105, zc + 0.0105), (yc + 0.0105, zc - 0.0105),
                           (yc - 0.0105, zc - 0.0105)], 0.0085, 4)
    loop_i = L.round_poly([(yc - 0.0065, zc + 0.0065), (yc + 0.0065, zc + 0.0065), (yc + 0.0065, zc - 0.0065),
                           (yc - 0.0065, zc - 0.0065)], 0.0050, 4)
    loop = L.tube("_loop", loop_o, loop_i, "X", -0.0022, 0.0022, mat=M["gunmetal"])
    boss = L.cyl("_lboss", 0.0050, "Z", zc + 0.0080, -0.0100, c=(0.0, yc), segs=16, mat=M["gunmetal"])
    L.finish(loop, bevel=0.0009, segs=1, angle=40, smooth_angle=40, uv=False)
    L.finish(boss, bevel=0, smooth_angle=40, uv=False)
    sling = L.join([loop, boss], "MAKO_stock_standard_Sling")
    L.finish(sling, bevel=0, smooth_angle=40)
    return st, [pad, lever, sling]


def build_stock_precision():
    col = COL["MAKO_stock_precision"]
    # r2: the front 50 mm is a low sleeve over the tube (top z 0.0695, under the charging handle's wings), ramping up
    # to the flat top behind it, so the CH_STROKE pull is clear with this fixed stock too (it hit the old top).
    side = [(0.048, 0.028), (0.048, 0.0640), (0.054, 0.0695), (0.098, 0.0695), (0.114, PREC_TOP), (0.252, PREC_TOP),
            (0.252, -0.066), (0.226, -0.066), (0.214, -0.052), (0.196, -0.050), (0.184, -0.040), (0.172, -0.028),
            (0.140, -0.004), (0.100, 0.016), (0.062, 0.026)]
    side = L.round_poly(side, 0, 2, radii=[0.003, 0.003, 0.004, 0.008, 0.008, 0.003, 0.003, 0.006, 0.006, 0.006,
                                          0.010, 0.010, 0.020, 0.020, 0.006])
    sec = sym([(0.0130, 0.090), (0.0220, 0.062), (0.0220, -0.090)])
    st = P("MAKO_stock_precision", side, -0.026, 0.026, M["bone"], col)
    L.intersect(st, S("_ps", sec, 0.04, 0.26, col=col))
    cut = [L.cyl("_ptc", 0.0166, "Y", 0.040, 0.228, c=(0, BORE_Z), segs=24, mat=M["dark"]), key_slot(0.040, 0.228)]
    pan = L.round_poly([(0.105, 0.020), (0.236, 0.020), (0.236, -0.050), (0.212, -0.038), (0.178, -0.016)],
                       0.005, 2)
    cut.append(P("_pp1", pan, 0.0200, 0.03, M["bone"], col))
    cut.append(P("_pp2", pan, -0.03, -0.0200, M["bone"], col))
    # panel line around the cheek comb's footprint: a 0.6 mm groove sunk into the stock's flat top
    fo = cheek_plan(PREC_LINE)
    fi = cheek_plan(-0.0002)   # 0.2 mm under the comb's wall: no coplanar faces at the bottom of the groove
    cut.append(L.tube("_pl", fo, fi, "Z", PREC_TOP - PREC_LINE, PREC_TOP + 0.01, mat=M["dark"]))
    L.boolean(st, cut)
    L.clean(st)

    def stock_edge(e):
        if L.edge_angle_deg(e) < 30:
            return False
        m = (e.verts[0].co + e.verts[1].co) / 2
        if m.z > PREC_TOP - PREC_LINE - 0.0002 and abs(m.x) < PREC_CHEEK_HW + PREC_LINE + 0.0003 and                 PREC_CHEEK[0] - PREC_LINE - 0.0003 < m.y < PREC_CHEEK[1] + PREC_LINE + 0.0003:
            return False  # keep the panel-line groove crisp (a 3 mm bevel would swallow it)
        return True
    L.finish(st, bevel=0.0030, segs=2, weight_fn=stock_edge, smooth_angle=35)
    # fixed cheek comb seated on the stock (r2 review: the riser on hidden posts read as a hovering slab). Its
    # base sits 1.5 mm down inside the stock, so the panel line is the only seam; narrower than the stock top.
    z0 = PREC_TOP - 0.0015
    cheek_side = L.round_poly([(PREC_CHEEK[0], z0), (PREC_CHEEK[1], z0), (PREC_CHEEK[1], 0.0905),
                               (0.229, 0.0935), (0.140, 0.0935), (0.124, 0.0870), (PREC_CHEEK[0], 0.0790)],
                              0, 2, radii=[0, 0, 0.002, 0.004, 0.010, 0.006, 0.002])
    cheek = P("MAKO_stock_precision_Cheek", cheek_side, -PREC_CHEEK_HW, PREC_CHEEK_HW, M["bone"], col)
    L.intersect(cheek, S("_cs", sym([(0.0105, 0.0960), (0.0150, 0.0880), (0.0150, z0 - 0.001)]), 0.10, 0.25,
                         col=col))
    L.intersect(cheek, T("_cp", cheek_plan(0.0), z0 - 0.002, 0.11))
    L.clean(cheek)

    def comb_edge(e):   # only the visible edges (above the stock top) get the 1.8 mm round
        m = (e.verts[0].co + e.verts[1].co) / 2
        return L.edge_angle_deg(e) > 31 and m.z > PREC_TOP + 0.0004
    L.finish(cheek, bevel=0.0018, segs=2, weight_fn=comb_edge, smooth_angle=35)
    pad_pts = L.round_poly([(0.2515, 0.0790), (0.2760, 0.0790), (0.2830, 0.0700), (0.2850, -0.0600),
                            (0.2790, -0.0710), (0.2515, -0.0710)], 0.003, 2)
    pad = P("MAKO_stock_precision_ButtPad", pad_pts, -0.0235, 0.0235, M["rubber"], col)
    L.intersect(pad, S("_pps", sym([(0.017, 0.095), (0.0235, 0.075), (0.0235, -0.068), (0.017, -0.080)]), 0.24,
                       0.30, col=col))
    grooves = [L.box("_pg", -0.03, 0.03, 0.2820, 0.30, z - 0.0012, z + 0.0012) for z in
               (0.048, 0.024, 0.0, -0.024, -0.048)]
    L.boolean(pad, grooves, transfer=False)
    L.clean(pad)
    L.finish(pad, bevel=0.0028, segs=2, angle=30)
    return st, [cheek, pad]


def build_stock_light():
    col = COL["MAKO_stock_light"]
    # r3: bottom at 0.0275 (was 0.030 = the key-slot floor -> a paper-thin bottom and a bad front-face fill)
    collar_sec = L.round_poly([(-0.0195, 0.0275), (0.0195, 0.0275), (0.0195, 0.0700), (0.0110, 0.0760),
                               (-0.0110, 0.0760), (-0.0195, 0.0700)], 0.004, 2)
    st = S("MAKO_stock_light", collar_sec, 0.128, 0.218, M["bone"], col)
    L.intersect(st, P("_cp", [(0.128, 0.024), (0.128, 0.068), (0.136, 0.080), (0.218, 0.080), (0.218, 0.024)],
                      -0.03, 0.03, col=col))
    # skeleton frame: starts INSIDE the collar (y 0.150) so the union overlaps; top strut, rear post and a
    # diagonal leg to the toe stay connected around one triangular opening
    frame_out = [(0.150, 0.030), (0.150, 0.066), (0.214, 0.066), (0.2615, 0.0725), (0.2615, -0.0500),
                 (0.2530, -0.0560), (0.2370, -0.0560)]
    frame_out = L.round_poly(frame_out, 0, 2, radii=[0.0, 0.0, 0.010, 0.003, 0.003, 0.003, 0.006])
    frame = P("_frame", frame_out, -0.0095, 0.0095, M["bone"], col)
    opening = L.round_poly([(0.1880, 0.0280), (0.2205, 0.0280), (0.2205, 0.0545), (0.2485, 0.0575),
                            (0.2485, -0.0400), (0.2392, -0.0400)], 0.0035, 2)
    L.boolean(frame, P("_fo", opening, -0.03, 0.03, col=col))
    L.boolean(st, frame, op="UNION", transfer=False)
    # tube channel stops inside the collar (the buffer tube ends at y 0.215), so the top strut stays whole
    L.boolean(st, [L.cyl("_ltc", 0.0166, "Y", 0.120, 0.2165, c=(0, BORE_Z), segs=24, mat=M["dark"]),
                   key_slot(0.120, 0.2165)])
    L.clean(st)
    L.finish(st, bevel=0.0022, segs=2, angle=30, smooth_angle=35)
    pad_pts = L.round_poly([(0.2610, 0.0740), (0.2700, 0.0740), (0.2730, 0.0680), (0.2735, -0.0520),
                            (0.2690, -0.0590), (0.2610, -0.0590)], 0.0015, 2)
    pad = P("MAKO_stock_light_ButtPad", pad_pts, -0.0170, 0.0170, M["rubber"], col)
    L.finish(pad, bevel=0.0020, segs=2, angle=30)
    lever = L.box("MAKO_stock_light_Lever", -0.0045, 0.0045, 0.150, 0.172, 0.0240, 0.0310, col=col,
                  mat=M["graphite"])
    L.finish(lever, bevel=0.0009, segs=1)
    return st, [pad, lever]


# ===================================================================================================== MAGS
class MagFrame:
    """Curved-magazine coordinate frame. dm = depth offset from the front edge (m), u = distance down the
    spine from the top (m). Straight down to z_straight, then a forward arc.
    Review fix: below the magwell lip the body flares (front -flare_f, rear +flare_r over u_flare), so the visible
    magazine is deeper like v09 while the part inside the well keeps the 0.064 that fits the cavity. r2 round 2:
    0.0735 (was 0.070): v09's magazine still read a size chunkier in the silhouette overlay."""

    def __init__(self, r_front, sweep_deg, depth=0.064, y_front=-0.152, z_top=0.012, z_straight=-0.020,
                 flare_f=0.0055, flare_r=0.0040, u_flare=(0.056, 0.086)):
        self.rf = r_front
        self.depth = depth
        self.yf = y_front
        self.zt = z_top
        self.zs = z_straight
        self.cy = y_front - r_front
        self.L0 = z_top - z_straight
        self.rmid = r_front + depth / 2
        self.U = self.L0 + self.rmid * math.radians(sweep_deg)
        self.ff, self.fr, self.uf = flare_f, flare_r, u_flare

    def theta(self, u):
        return 0.0 if u <= self.L0 else (u - self.L0) / self.rmid

    def flare(self, u):
        t = min(max((u - self.uf[0]) / (self.uf[1] - self.uf[0]), 0.0), 1.0)
        s = t * t * (3 - 2 * t)
        return self.ff * s, self.fr * s

    def F(self, dm, u):
        ef, er = self.flare(u)
        dm = -ef + dm * (self.depth + ef + er) / self.depth
        if u <= self.L0:
            return (self.yf + dm, self.zt - u)
        th = self.theta(u)
        r = self.rf + dm
        return (self.cy + r * math.cos(th), self.zs - r * math.sin(th))

    def map_pts(self, pts):
        """pts given as (dm, u) -> world (y, z)."""
        return [self.F(d, u) for (d, u) in pts]

    def spine(self, steps=10):
        us = [0.0, self.L0] + [self.L0 + (self.U - self.L0) * k / steps for k in range(1, steps + 1)]
        us += [self.uf[0] + (self.uf[1] - self.uf[0]) * k / 8 for k in range(9)]   # smooth flare (r2: 4 kinked)
        return sorted(set(round(u, 6) for u in us))


def round_lathe(name, mat_case, mat_tip, steps=10, col=None):
    """Cartridge along -Y from y=0 (case head) to y=-0.057 (tip)."""
    prof = [(0, 0), (0.0045, 0), (0.0048, 0.0010), (0.0048, 0.0355), (0.0040, 0.0395), (0.0029, 0.0405),
            (0.0029, 0.0445), (0.0026, 0.0480), (0.0018, 0.0530), (0.0007, 0.0565), (0, 0.0570)]
    r = L.lathe_y(name, prof, 0.0, -1, c=(0, 0), steps=steps, col=col, mat=mat_case)
    r.data.materials.append(mat_tip)
    for p in r.data.polygons:
        if p.center.y < -0.0446:
            p.material_index = 1
    return r


MAG_CAPACITY = {"mag_30": 30, "mag_45": 45, "mag_drum60": 60}
STACK_RULE = ("Each child <mag>_Stack_NN is one cartridge seen through the window (NN = 00 nearest the feed lips). "
              "Show it while rounds_in_mag >= its min_rounds custom property, hide it otherwise.")


def stack_empty(key, col, n):
    e = L.empty(f"MAKO_{key}_Stack", MAG_SOCKET, col, 0.01, "PLAIN_AXES")
    e["capacity"] = MAG_CAPACITY[key]
    e["visible_rounds"] = n
    e["rule"] = STACK_RULE
    return e


def build_box_mag(key, r_front, sweep, win_u, col):
    """STANAG-style curved box magazine with a window slot and visible cartridges."""
    fr = MagFrame(r_front, sweep)
    D = fr.depth
    us = fr.spine(8)
    outline = [fr.F(0.0, u) for u in us] + [fr.F(D, u) for u in reversed(us)]
    body = P(f"MAKO_{key}", outline, -0.0125, 0.0125, M["bone"], col)
    U = fr.U
    # floorplate (graphite polymer), flared
    fp = fr.map_pts([(0.0010, U - 0.0010), (D - 0.0010, U - 0.0010), (D + 0.0030, U + 0.0035),
                     (D + 0.0030, U + 0.0085), (D + 0.0010, U + 0.0110), (-0.0010, U + 0.0110),
                     (-0.0030, U + 0.0085), (-0.0030, U + 0.0035)])
    plate = P("_fp", fp, -0.0146, 0.0146, M["graphite"], col)
    L.intersect(plate, S("_fps", sym([(0.0120, 0.30), (0.0146, 0.30), (0.0146, -0.40), (0.0120, -0.40)]), -0.30,
                         0.10, col=col))
    # ribs along the curve (front and rear), both sides
    ribs = []
    for d0 in (0.0070, D - 0.0100):
        us_r = [0.060 + (U - 0.004 - 0.060) * k / 7 for k in range(8)]
        rp = fr.map_pts([(d0, u) for u in us_r] + [(d0 + 0.0030, u) for u in reversed(us_r)])
        ribs.append(P("_rib", rp, 0.0120, 0.0137, M["bone"], col))
        ribs.append(P("_rib", rp, -0.0137, -0.0120, M["bone"], col))
    L.boolean(body, [plate] + ribs, op="UNION")
    cut = []
    # feed lips: channel for the top round + lip in-curl chamfers
    cut.append(L.box("_ch", -0.0068, 0.0068, -0.1490, -0.0905, 0.0055, 0.030, mat=M["dark"]))
    for sgn in (1, -1):
        c = S("_lipc", [(0.0, 0.0165), (0.012, 0.0165), (0.012, 0.006)] if sgn > 0 else
              [(0.0, 0.0165), (-0.012, 0.006), (-0.012, 0.0165)], -0.160, -0.080)
        L.move(c, (sgn * 0.0040, 0, 0))
        cut.append(c)
    # window slot (both sides), follows the curve; 8-segment round ends (review: 4 read as a pointed top)
    dmc = D * 0.56
    u0, u1 = win_u
    win_half = 0.0044   # 8.8 mm window (r2 review: 8-9 mm so the cartridges read in a mag check)
    n = 8
    cs = 8      # 22.5 deg cap steps: under the 30 deg bevel limit, so no stray bevelled cap edges
    left = [(dmc - win_half, u0 + (u1 - u0) * k / n) for k in range(n + 1)]
    right = [(dmc + win_half, u1 - (u1 - u0) * k / n) for k in range(n + 1)]
    end1 = [(dmc - win_half * math.cos(math.pi * k / cs), u1 + win_half * math.sin(math.pi * k / cs))
            for k in range(1, cs)]
    end0 = [(dmc + win_half * math.cos(math.pi * k / cs), u0 - win_half * math.sin(math.pi * k / cs))
            for k in range(1, cs)]
    wy = fr.map_pts(left + end1 + right + end0)
    cut.append(P("_win", wy, 0.0082, 0.03, M["dark"], col))
    cut.append(P("_win", wy, -0.03, -0.0082, M["dark"], col))
    L.boolean(body, cut)
    L.clean(body)
    L.finish(body, bevel=0.0020, segs=1, angle=30, smooth_angle=35)
    # top round, lying in the channel, tip forward (-Y)
    rnd = round_lathe(f"MAKO_{key}_Round", M["brass"], M["gunmetal"], steps=12, col=col)
    L.move(rnd, (0.0018, -0.0915, 0.0055 + 0.0048))
    L.finish(rnd, bevel=0, smooth_angle=40)
    rnd["min_rounds"] = 1
    # Visible cartridges behind the window (review fix): one node per round so a mag check can show roughly how
    # full the mag is. Round i (0 = top, in the feed lips) sits at spine u_i; the double stack alternates sides.
    # Only rounds that can be seen through the window are modelled.
    cap = MAG_CAPACITY[key]
    u_top = 0.0017
    step = (U - 0.010 - u_top) / (cap - 1)
    nodes = []
    for i in range(1, cap):
        u = u_top + i * step
        if not (u0 - 0.0035 <= u <= u1 + 0.0035):
            continue
        sgn = 1 if i % 2 == 0 else -1
        th = fr.theta(u)
        y, z = fr.F(dmc, u)
        c = L.cyl(f"MAKO_{key}_Stack_{len(nodes):02d}", 0.0048, "Y", -0.008, 0.008, c=(0, 0), segs=8,
                  mat=M["brass"], col=col)
        L.rotate(c, "X", -math.degrees(th))
        L.move(c, (sgn * 0.0052, y, z))
        L.finish(c, bevel=0, smooth_angle=50)
        L.set_origin(c, (sgn * 0.0052, y, z))
        c["min_rounds"] = i + 1
        c["round_index"] = i
        nodes.append(c)
    stack = stack_empty(key, col, len(nodes))
    for c in nodes:
        L.parent(c, stack)
    for o in (body, rnd, stack):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    return body, [rnd, stack]


def case_head(name, mat, x_face, sgn, y, z, steps=14, primer=None):
    """Short cartridge stub seen end-on in the drum windows: case head (rim + extractor groove) facing sgn*X,
    its face at x_face, 8 mm of case behind it (the rest of the round is hidden inside the drum). r2: a primer
    disc (r 2.2 mm, `primer` material) so the heads read as cartridges, not as plain brass coins."""
    prof = [(0, 0), (0.0022, 0), (0.0048, 0), (0.0048, 0.0014), (0.0040, 0.0020), (0.0040, 0.0030),
            (0.0048, 0.0036), (0.0048, 0.0080), (0, 0.0080)]
    c = L.lathe_y(name, prof, 0.0, 1, c=(0, 0), steps=steps, mat=mat)
    if primer is not None:
        c.data.materials.append(primer)
        for p in c.data.polygons:
            if abs(p.center.y) < 1e-6 and math.hypot(p.center.x, p.center.z) < 0.0022:
                p.material_index = 1
    # the lathe runs +Y from the head face; turn it so the head faces sgn*X
    L.rotate(c, "Z", 90 if sgn > 0 else -90)
    L.move(c, (x_face, y, z))
    return c


def build_drum():
    key = "mag_drum60"
    col = COL["MAKO_mag_drum60"]
    neck = P(f"MAKO_{key}", [(-0.152, 0.012), (-0.152, -0.052), (-0.088, -0.052), (-0.088, 0.012)], -0.0125,
             0.0125, M["bone"], col)
    dc = (-0.121, -0.093)  # drum centre (y, z)
    R = 0.052
    W = 0.031
    prof = [(0, -W), (R - 0.006, -W), (R, -W + 0.006), (R, -0.0045), (R + 0.0015, -0.0030), (R + 0.0015, 0.0030),
            (R, 0.0045), (R, W - 0.006), (R - 0.006, W), (0, W)]
    drum = L.lathe_y("_drum", prof, 0.0, 1, c=(0, 0), steps=40, mat=M["bone"])
    L.rotate(drum, "Z", -90)          # axis Y -> X
    L.move(drum, (0, dc[0], dc[1]))
    # neck-to-drum fairing
    fair = P("_fair", [(-0.156, -0.040), (-0.084, -0.040), (-0.090, -0.060), (-0.150, -0.060)], -0.0150,
             0.0150, M["bone"], col)
    L.boolean(neck, [drum, fair], op="UNION", transfer=False)
    cut = [L.box("_ch", -0.0068, 0.0068, -0.1490, -0.0905, 0.0055, 0.030, mat=M["dark"])]
    for sgn in (1, -1):
        c = S("_lipc", [(0.0, 0.0165), (0.012, 0.0165), (0.012, 0.006)] if sgn > 0 else
              [(0.0, 0.0165), (-0.012, 0.006), (-0.012, 0.0165)], -0.160, -0.080)
        L.move(c, (sgn * 0.0040, 0, 0))
        cut.append(c)
    # Arc window on both drum faces, wrapped around the REAR-lower quadrant (review: a symmetric lower arc under
    # the round hub read as a smiling face). Angle 0 points to +Y (rear), negative angles are below the centre.
    rw, hw = 0.0335, 0.0052
    a0, a1 = math.radians(-118), math.radians(28)
    n = 16

    def at(r, a):
        return (dc[0] + r * math.cos(a), dc[1] + r * math.sin(a))
    outer = [at(rw + hw, a0 + (a1 - a0) * k / n) for k in range(n + 1)]
    inner = [at(rw - hw, a1 - (a1 - a0) * k / n) for k in range(n + 1)]
    c1, c0 = at(rw, a1), at(rw, a0)
    # 8-step end caps (22.5 deg): with 30 deg steps some cap edges sat right on the 30 deg bevel limit and got a
    # stray bevel -> small spikes where the cap met the arc (r2 review)
    cs = 8
    cap1 = [(c1[0] + hw * math.cos(a1 + math.pi * k / cs), c1[1] + hw * math.sin(a1 + math.pi * k / cs))
            for k in range(1, cs)]
    cap0 = [(c0[0] + hw * math.cos(a0 + math.pi + math.pi * k / cs),
             c0[1] + hw * math.sin(a0 + math.pi + math.pi * k / cs)) for k in range(1, cs)]
    wpts = outer + cap1 + inner + cap0
    cut.append(P("_dw", wpts, W - 0.0045, W + 0.01, M["dark"], col))
    cut.append(P("_dw", wpts, -W - 0.01, -W + 0.0045, M["dark"], col))
    L.boolean(neck, cut)
    # hub caps (graphite) + winding key (+X)
    hubs = []
    for sgn in (1, -1):
        x0, x1 = (W - 0.001, W + 0.0035) if sgn > 0 else (-W - 0.0035, -W + 0.001)
        hubs.append(L.cyl("_hub", 0.0165, "X", x0, x1, c=dc, segs=24, mat=M["graphite"]))
    key_t = L.box("_key", W + 0.0030, W + 0.0090, dc[0] - 0.0140, dc[0] + 0.0140, dc[1] - 0.0030,
                  dc[1] + 0.0030, mat=M["gunmetal"])
    L.boolean(neck, hubs + [key_t], op="UNION")
    L.clean(neck)
    L.finish(neck, bevel=0.0018, segs=2, angle=30, smooth_angle=35)
    rnd = round_lathe(f"MAKO_{key}_Round", M["brass"], M["gunmetal"], steps=12, col=col)
    L.move(rnd, (0.0018, -0.0915, 0.0055 + 0.0048))
    L.finish(rnd, bevel=0, smooth_angle=40)
    rnd["min_rounds"] = 1
    # cartridges in the window, case heads seen on BOTH faces (review fix: the -X face showed only bullet tips).
    # One node per window position; 00 = the end nearest the neck (the last to empty).
    N = 8
    cap = MAG_CAPACITY[key]
    nodes = []
    for k in range(N):
        a = a1 - (a1 - a0) * (k + 0.5) / N
        y, z = at(rw, a)
        pair = [case_head("_dch", M["brass"], W - 0.0022, 1, y, z, primer=M["gunmetal"]),
                case_head("_dch", M["brass"], -W + 0.0022, -1, y, z, primer=M["gunmetal"])]
        for c in pair:
            L.finish(c, bevel=0, smooth_angle=40, uv=False)
        node = L.join(pair, f"MAKO_{key}_Stack_{k:02d}")
        to_col(node, col)
        L.finish(node, bevel=0, smooth_angle=40)
        L.set_origin(node, (0.0, y, z))
        node["min_rounds"] = int(math.ceil(1 + (k + 1) * (cap - 1) / N))
        nodes.append(node)
    stack = stack_empty(key, col, len(nodes))
    for c in nodes:
        L.parent(c, stack)
    for o in (neck, rnd, stack):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    return neck, [rnd, stack]


# ===================================================================================================== CHECKS
def bvh_of(objs, offset=(0.0, 0.0, 0.0)):
    """World-space BVH of the evaluated meshes, shifted by offset."""
    from mathutils.bvhtree import BVHTree
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    off = Vector(offset)
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        b = len(verts)
        verts += [mw @ v.co + off for v in me.vertices]
        # the real triangulation (a naive fan over a ring-shaped n-gon would bridge its hole -> false hits)
        me.calc_loop_triangles()
        polys += [[b + i for i in t.vertices] for t in me.loop_triangles]
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys, epsilon=0.0)


def ch_sweep(ch, fixed, stock_objs, travels, stroke, step=0.001):
    """Largest clean charging-handle pull (+Y) for each stock collapse position (stock moved -Y by t), checked
    against the fixed base parts and the stock. Returns ([max clear stroke per travel], {s: [fixed parts hit]})."""
    fixed_t = {o.name: bvh_of([o]) for o in fixed}
    hits = {}
    n = int(round(stroke / step))
    for k in range(n + 1):
        s = k * step
        b = bvh_of([ch], (0, s, 0))
        hit = [nm for nm, t in fixed_t.items() if b.overlap(t)]
        if hit:
            hits[round(s, 4)] = hit
    out = []
    for t in travels:
        st = bvh_of(stock_objs, (0, -t, 0))
        best = 0.0
        for k in range(n + 1):
            s = k * step
            if bvh_of([ch], (0, s, 0)).overlap(st):
                break
            best = s
        out.append(round(best, 4))
    return out, hits


# ===================================================================================================== ASSEMBLY
def to_col(o, col):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    col.objects.link(o)
    return o


def main():
    os.makedirs(os.path.join(OUT, "_work"), exist_ok=True)
    log("building base")
    root = L.empty("MAKO_Root", (0, 0, 0), BASE, 0.05, "ARROWS")
    base = []
    base.append(build_upper()); log("upper")
    base.append(build_lower()); log("lower")
    base.append(build_grip()); log("grip")
    base.append(build_trigger())
    base.append(build_handguard()); log("handguard")
    rails, top_c, bot_c, side_c = build_rails(); log("rails")
    base += list(rails)
    base.append(build_barrel())
    base.append(build_flash_hider()); log("flash hider")
    base.append(build_buffer_tube())
    base.append(build_charging_handle())
    base.append(build_forward_assist())
    base.append(build_dust_cover())
    base.append(build_bolt_catch())
    base.append(build_mag_release())
    base.append(build_selector())
    base.append(build_pins())
    for o in base:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        BASE.objects.link(o)
        L.parent(o, root)
    log("base built")

    # ---------------------------------------------------------------- sockets
    def nearest(cs, y):
        return min(cs, key=lambda c: abs(c - y))
    sockets = {
        "MAKO_SOCKET_Optic": (0.0, nearest(top_c, -0.085), RAIL_TOP),
        "MAKO_SOCKET_Stock": STOCK_SOCKET,
        "MAKO_SOCKET_Mag": MAG_SOCKET,
        "MAKO_SOCKET_Under": (0.0, nearest(bot_c, -0.335), HG_BOT - L.RAIL_H),
        "MAKO_SOCKET_Side_R": (-(0.023 + L.RAIL_H), sum(side_c) / len(side_c), BORE_Z),
        "MAKO_SOCKET_Side_L": (0.023 + L.RAIL_H, sum(side_c) / len(side_c), BORE_Z),
        "MAKO_SOCKET_Shield": (0.0, nearest(top_c, -0.476), RAIL_TOP),
        "MAKO_SOCKET_Muzzle": (0.0, MUZZLE_Y, BORE_Z),
        "MAKO_SOCKET_LeftHand": (0.0, -0.330, HG_BOT - L.RAIL_H),
    }
    sock_objs = []
    for nm, loc in sockets.items():
        e = L.empty(nm, [round(v, 5) for v in loc], BASE, 0.015, "PLAIN_AXES")
        L.parent(e, root)
        sock_objs.append(e)
    with open(os.path.join(OUT, "sockets.json"), "w") as f:
        json.dump({k: {"location": [round(v, 5) for v in loc], "rotation_deg": [0, 0, 0]}
                   for k, loc in sockets.items()}, f, indent=2)

    # ---------------------------------------------------------------- parts
    # parts[key] = (main object, every descendant): direct children are parented to the part's main object; the
    # magazines' per-round stack nodes hang under a MAKO_<mag>_Stack empty.
    parts = {}
    log("stocks")
    for key, fn in (("stock_standard", build_stock_standard), ("stock_precision", build_stock_precision),
                    ("stock_light", build_stock_light)):
        main_o, kids = fn()
        for o in [main_o] + kids:
            to_col(o, COL[f"MAKO_{key}"])
        L.set_origin(main_o, STOCK_SOCKET)
        for k in kids:
            L.parent(k, main_o)
        parts[key] = (main_o, list(main_o.children_recursive))
    st = parts["stock_standard"][0]
    st["travel_positions_m"] = list(STOCK_TRAVEL)
    st["motion"] = "translate -Y (collapse) by one of travel_positions_m; 0 = delivered, fully extended"
    log("mags")
    mags = [("mag_30", lambda: build_box_mag("mag_30", 0.48, 15.0, (0.062, 0.142), COL["MAKO_mag_30"])),
            ("mag_45", lambda: build_box_mag("mag_45", 0.46, 24.0, (0.064, 0.212), COL["MAKO_mag_45"])),
            ("mag_drum60", build_drum)]
    for key, fn in mags:
        main_o, kids = fn()
        L.set_origin(main_o, MAG_SOCKET)
        for k in kids:
            if k.type == "MESH":
                L.set_origin(k, MAG_SOCKET)
            L.parent(k, main_o)
        main_o["capacity"] = MAG_CAPACITY[key]
        parts[key] = (main_o, list(main_o.children_recursive))
    log("parts built")

    for o in bpy.data.objects:
        if o.type == "MESH":
            bad = L.tidy_materials(o)
            if bad:
                log(f"WARN {o.name}: {bad} faces had an empty material slot (reassigned)")
    bc.uv_all()
    for o in bpy.data.objects:
        if o.type == "MESH":
            L.uv_density(o, REPS)
    # apply the bevel stacks, then remove the micro / zero-area faces the clamped bevels leave behind (the corner
    # normals are carried through the cleanup, so the hardened shading is untouched; see L.bake_clean)
    degen = {}
    for o in bpy.data.objects:
        if o.type == "MESH":
            b, a = L.bake_clean(o)
            if b or a:
                degen[o.name] = (b, a)
    log("bevel spike fixes (passes, edges reduced, worst overshoot mm before):",
        {k: v for k, v in L.BEVEL_LOG.items() if v[0]})
    log("micro / zero-area faces (before -> after the cleanup):", degen)
    left = {k: v[1] for k, v in degen.items() if v[1]}
    if left:
        log("WARN micro / zero-area faces left:", left)
    base_meshes = [o for o in base if o.type == "MESH"]

    # ---------------------------------------------------------------- charging handle vs stocks (r2 review)
    ch = bpy.data.objects["MAKO_ChargingHandle"]
    fixed = [o for o in base_meshes if o is not ch]
    report = {}
    for key, travels in (("stock_standard", STOCK_TRAVEL), ("stock_precision", (0.0,)), ("stock_light", (0.0,))):
        m, kids = parts[key]
        clear, hits = ch_sweep(ch, fixed, [m] + list(kids), travels, CH_STROKE)
        report[key] = {"travel_m": list(travels), "ch_stroke_clear_m": clear}
        m["ch_stroke_max_m"] = clear
        log(f"CH sweep {key}: travel {list(travels)} -> clear stroke {clear}")
    report["ch_vs_base_hits"] = hits
    log("CH sweep vs base parts (stroke: parts touched):", hits or "none")
    # the collapsing stock itself must not run into the receiver / castle nut at any travel position
    st = parts["stock_standard"][0]
    base_bvh = {o.name: bvh_of([o]) for o in fixed + [ch]}
    stock_hits = {}
    for key, travels in (("stock_standard", STOCK_TRAVEL), ("stock_precision", (0.0,)), ("stock_light", (0.0,))):
        m, kids = parts[key]
        for t in travels:
            sb = bvh_of([m] + list(kids), (0, -t, 0))
            hit = [nm for nm, tr in base_bvh.items() if sb.overlap(tr)]
            if hit:
                stock_hits[f"{key}@{t}"] = hit
    report["stock_travel_vs_base_hits"] = stock_hits
    log("stocks (every travel position) vs base parts:", stock_hits or "none")
    # seated magazines vs the receiver (r2 round 2: the visible part of the box mags now flares to 0.0735)
    mag_hits = {}
    for key in ("mag_30", "mag_45", "mag_drum60"):
        m, kids = parts[key]
        mb = bvh_of([m] + [k for k in kids if k.type == "MESH"])
        hit = [nm for nm, tr in base_bvh.items() if mb.overlap(tr)]
        if hit:
            mag_hits[key] = hit
    report["mag_seated_vs_base_hits"] = mag_hits
    log("seated magazines vs base parts:", mag_hits or "none")
    if any(c < CH_STROKE for c in report["stock_standard"]["ch_stroke_clear_m"]) or hits or stock_hits or mag_hits:
        log("WARN moving-part clearance problem (see _work/ch_sweep.json)")
    st["ch_rule"] = ("Charging-handle pull for each travel_positions_m entry is limited to the matching "
                     "ch_stroke_max_m entry (r3: all equal stroke_m, the pull is clean at every position).")
    with open(os.path.join(OUT, "_work", "ch_sweep.json"), "w") as f:
        json.dump(report, f, indent=2)

    def part_objs(key):
        m, k = parts[key]
        return [m] + list(k)

    # ---------------------------------------------------------------- stats
    stats = {"base": L.tri_count(base_meshes)}
    for key in parts:
        stats[key] = L.tri_count(part_objs(key))
    stats["default_total"] = stats["base"] + stats["stock_standard"] + stats["mag_30"]
    per_obj = {o.name: L.tri_count([o]) for o in base_meshes}
    for key in parts:
        for o in part_objs(key):
            if o.type == "MESH":
                per_obj[o.name] = L.tri_count([o])
    with open(os.path.join(OUT, "tri_counts.json"), "w") as f:
        json.dump({"groups": stats, "objects": per_obj}, f, indent=2)
    log("TRIS", json.dumps(stats))
    default_objs = base_meshes + part_objs("stock_standard") + part_objs("mag_30")
    mn, mx = bc.world_bounds(default_objs)
    log("DEFAULT BOUNDS", tuple(round(v, 4) for v in mn), tuple(round(v, 4) for v in mx))

    # ---------------------------------------------------------------- renders
    if not FLAG.get("--no-render"):
        import render_mako
        render_mako.run(FLAG, base, parts, sock_objs, root)

    # ---------------------------------------------------------------- exports
    if not FLAG.get("--no-export"):
        export_everything(root, base, sock_objs, parts)
    log("done")


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_set(path_no_ext, objs):
    select_only(objs)
    # custom properties (motion data, min_rounds of the mag-check cartridges) travel as glTF extras / FBX props
    bpy.ops.export_scene.gltf(filepath=path_no_ext + ".glb", export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_extras=True)
    bpy.ops.export_scene.fbx(filepath=path_no_ext + ".fbx", use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             use_mesh_modifiers=True, add_leaf_bones=False, path_mode="COPY", embed_textures=True,
                             use_custom_props=True)
    log("exported", path_no_ext)


def export_everything(root, base, sock_objs, parts):
    for o in bpy.data.objects:
        o.hide_render = False
    base_all = [root] + base + sock_objs
    export_set(os.path.join(OUT, "mako_base"), base_all)
    for key, (m, kids) in parts.items():
        loc = m.location.copy()
        m.location = (0, 0, 0)
        bpy.context.view_layer.update()
        export_set(os.path.join(OUT, f"MAKO_{key}"), [m] + list(kids))
        m.location = loc
        bpy.context.view_layer.update()
    sel = base_all + [parts["stock_standard"][0]] + parts["stock_standard"][1] + [parts["mag_30"][0]] + \
        parts["mag_30"][1]
    select_only(sel)
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "mako_default.glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_yup=True, export_extras=True)
    log("exported mako_default.glb")
    # blend: default loadout visible, other variants hidden
    vl = bpy.context.view_layer
    for cname in ("MAKO_stock_precision", "MAKO_stock_light", "MAKO_mag_45", "MAKO_mag_drum60"):
        lc = vl.layer_collection.children[cname]
        lc.hide_viewport = True
        bpy.data.collections[cname].hide_render = True
    for o in list(bpy.data.objects):
        if o.name.startswith("_PreviewCam"):
            bpy.data.objects.remove(o, do_unlink=True)
    try:
        bpy.ops.file.pack_all()  # baked textures travel inside the .blend
    except Exception as e:  # noqa: BLE001
        log("pack_all failed", e)
    for image in bpy.data.images:
        if image.filepath and os.path.dirname(os.path.abspath(image.filepath)) == TEXOUT:
            image.filepath = "//textures/" + os.path.basename(image.filepath)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "mako.blend"), compress=True)
    log("saved mako.blend")
    import subprocess
    # r2 review: validation is fatal. check_glb.py exits 1 on any error; run Blender with --python-exit-code 1 so
    # the failure also reaches the shell.
    r = subprocess.run(["python", os.path.join(HERE, "check_glb.py"), "--out", OUT])
    if r.returncode != 0:
        log("check_glb.py FAILED")
        raise SystemExit(1)
    log("check_glb.py OK")


main()
