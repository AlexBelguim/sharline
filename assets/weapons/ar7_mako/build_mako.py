"""AR-7 "MAKO" - modular M4-style assault rifle. Re-runnable build: creates everything from scratch.

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P build_mako.py -- [flags]
Flags:
  --no-render      build + export only
  --no-export      skip glb/fbx/blend output
  --quick          low-res / low-sample preview renders of the main views only
  --renders=a,b    only these render groups (main, closeups, stocks, mags, compare)

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

HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
sys.path.insert(0, HERE)
sys.path.insert(0, r"F:/git/val etf/tools")

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import blender_common as bc  # noqa: E402
import mako_lib as L  # noqa: E402

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FLAG = {a.split("=")[0]: (a.split("=")[1] if "=" in a else True) for a in ARGS}
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

OUT = HERE
RENDERS = os.path.join(HERE, "renders")

# --------------------------------------------------------------------------------------------- scene
bc.reset_scene()
SC = bpy.context.scene
COL = {}
for cname in ("MAKO_Base", "MAKO_stock_standard", "MAKO_stock_precision", "MAKO_stock_light",
              "MAKO_mag_30", "MAKO_mag_45", "MAKO_mag_drum60"):
    COL[cname] = bc.collection(cname)

TEX = bc.TEXTURES
M = {
    "graphite": bc.material("M_MAKO_Graphite", (0.030, 0.033, 0.040), rough=0.58, metal=0.18,
                            tex=os.path.join(TEX, "worn_paint.png"), tex_mix=0.45, tex_scale=1.5),
    "gunmetal": bc.material("M_MAKO_Gunmetal", (0.11, 0.115, 0.12), rough=0.35, metal=0.85,
                            tex=os.path.join(TEX, "brushed_metal.png"), tex_mix=0.30, tex_scale=2.5),
    "bone": bc.material("M_MAKO_Bone", (0.55, 0.52, 0.46), rough=0.60, metal=0.0,
                        tex=os.path.join(TEX, "worn_paint.png"), tex_mix=0.35, tex_scale=1.5),
    "stipple": bc.material("M_MAKO_BoneStipple", (0.52, 0.49, 0.43), rough=0.78, metal=0.0,
                           tex=os.path.join(TEX, "polymer_stipple.png"), tex_mix=0.45, tex_scale=4),
    "rubber": bc.material("M_MAKO_Rubber", (0.030, 0.033, 0.040), rough=0.85, metal=0.0),
    "dark": bc.material("M_MAKO_Dark", (0.035, 0.037, 0.045), rough=0.70, metal=0.0),
    "brass": bc.material("M_MAKO_Brass", (0.36, 0.28, 0.18), rough=0.35, metal=0.85),
}
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
def build_upper():
    side = [(-0.168, 0.024), (-0.168, RAIL_BASE), (0.022, RAIL_BASE), (0.030, 0.066), (0.030, 0.046),
            (0.014, 0.046), (0.008, 0.024)]
    sec = sym([(0.0092, 0.077), (0.0152, 0.066), (0.0152, 0.0480), (0.0168, 0.0464), (0.0168, 0.020)])
    up = P("MAKO_Upper", side, -0.0168, 0.0168, M["graphite"])
    L.intersect(up, S("_us", sec, -0.175, 0.040))
    # brass deflector (shooter's right, -X) behind the ejection port
    defl = P("_defl", [(-0.027, 0.0535), (-0.010, 0.0535), (-0.008, 0.0700), (-0.017, 0.0720)], -0.0215, -0.012)
    L.intersect(defl, S("_dfs", [(-0.030, 0.050), (-0.012, 0.050), (-0.012, 0.075), (-0.0175, 0.075),
                                 (-0.030, 0.062)], -0.04, 0.0))
    # forward-assist housing (-X), teardrop boss
    fa = L.lathe_y("_fah", [(0, 0), (0.003, 0), (0.0080, 0.011), (0.0080, 0.031), (0.0072, 0.032), (0, 0.032)],
                   -0.010, 1, c=(-0.0172, 0.0585), steps=16)
    ring = L.cyl("_ring", 0.0192, "Y", 0.012, 0.030, c=(0, BORE_Z), segs=24)
    L.intersect(ring, L.box("_rb", -0.03, 0.03, 0.0, 0.05, 0.046, 0.0745))
    L.boolean(up, [defl, fa, ring], op="UNION", transfer=False)
    cut = []
    # ejection port (bolt carrier face shows gunmetal when the dust cover opens)
    port = L.round_poly([(-0.091, 0.0395), (-0.029, 0.0395), (-0.029, 0.0635), (-0.091, 0.0635)], 0.002, 2)
    cut.append(P("_port", port, -0.030, -0.0125, M["gunmetal"]))
    # charging-handle channel at the rear top
    cut.append(L.box("_chn", -0.0068, 0.0068, 0.004, 0.040, 0.0612, 0.080, mat=M["dark"]))
    # forward assist bore (cap sits in it)
    cut.append(L.cyl("_fab", 0.0050, "Y", 0.018, 0.040, c=(-0.0172, 0.0585), segs=16, mat=M["dark"]))
    L.boolean(up, cut)
    L.clean(up)
    L.finish(up, bevel=0.0016, segs=2, angle=30)
    return up


def build_lower():
    body_pts = [(-0.158, 0.024), (-0.1605, -0.028), (-0.080, -0.028), (-0.080, -0.006), (-0.072, 0.000),
                (0.018, 0.000), (0.030, 0.008), (0.036, 0.020), (0.036, 0.046), (0.014, 0.046), (0.008, 0.024)]
    low = P("MAKO_Lower", body_pts, -0.0152, 0.0152, M["graphite"])
    well = P("_well", [(-0.1600, 0.010), (-0.1620, -0.030), (-0.0790, -0.030), (-0.0790, 0.004), (-0.0840, 0.010)],
             -0.0172, 0.0172)
    lip = P("_lip", [(-0.1665, -0.0415), (-0.0765, -0.0415), (-0.0755, -0.0355), (-0.0790, -0.0275),
                     (-0.1620, -0.0275), (-0.1665, -0.0345)], -0.0205, 0.0205)
    L.intersect(lip, S("_lps", sym([(0.0172, -0.020), (0.0172, -0.0275), (0.0205, -0.0350), (0.0205, -0.050)]),
                       -0.18, -0.07))
    guard = P("_guard", [(-0.0815, 0.002), (-0.0815, -0.031), (-0.0745, -0.0375), (-0.0225, -0.0375),
                         (-0.0120, -0.0270), (-0.0120, 0.002)], -0.0065, 0.0065)
    # round boss around the buffer-tube entry (lower half; the upper carries the top half)
    ring = L.cyl("_ring", 0.0192, "Y", 0.012, 0.036, c=(0, BORE_Z), segs=24)
    L.intersect(ring, L.box("_rb", -0.03, 0.03, 0.0, 0.05, 0.020, 0.046))
    # bolt-catch boss with two ears (+X, shooter's left)
    boss = P("_bkboss", L.round_poly([(-0.0800, 0.0010), (-0.0590, 0.0010), (-0.0590, 0.0235), (-0.0800, 0.0235)],
                                     0.003, 2), 0.0140, 0.0166)
    ribs = [P("_wrib", [(-0.1560, -0.0270), (-0.1500, -0.0270), (-0.1500, 0.0060), (-0.1540, 0.0100)], -0.0184,
              0.0184)]
    L.boolean(low, [well, lip, guard, ring, boss] + ribs, op="UNION", transfer=False)
    cut = []
    cut.append(P("_ghole", L.round_poly([(-0.0760, -0.0002), (-0.0760, -0.0320), (-0.0240, -0.0320),
                                          (-0.0170, -0.0245), (-0.0170, -0.0002)], 0.004, 2), -0.02, 0.02))
    cut.append(L.box("_trs", -0.0045, 0.0045, -0.0535, -0.0310, -0.004, 0.009, mat=M["dark"]))
    cut.append(L.box("_cav", -0.0135, 0.0135, -0.1535, -0.0865, -0.060, 0.016, mat=M["dark"]))
    cut.append(L.loft("_fun", [(-0.0425, [(-0.0168, -0.1568), (0.0168, -0.1568), (0.0168, -0.0832),
                                          (-0.0168, -0.0832)]),
                               (-0.0355, [(-0.0135, -0.1535), (0.0135, -0.1535), (0.0135, -0.0865),
                                          (-0.0135, -0.0865)])], "Z", mat=M["dark"]))
    # bolt-catch channel between the ears
    cut.append(L.box("_bkch", 0.0153, 0.03, -0.0745, -0.0655, -0.002, 0.03))
    # mag-release well (shooter's right, -X)
    cut.append(L.cyl("_mrf", 0.0068, "X", -0.03, -0.0140, c=(-0.0720, 0.0090), segs=16, mat=M["graphite"]))
    # grip grooves on the magwell front
    for z in (-0.006, -0.012, -0.018):
        cut.append(L.box("_wg", -0.012, 0.012, -0.166, -0.1610, z - 0.0009, z + 0.0009))
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
    L.finish(low, bevel=0.0015, segs=2, weight_fn=visible_edge)
    return low


def build_grip():
    pts = [(-0.018, 0.004), (0.020, 0.004), (0.030, 0.009), (0.039, 0.004), (0.037, -0.004), (0.032, -0.012),
           (0.036, -0.030), (0.046, -0.060), (0.055, -0.088), (0.059, -0.100), (0.057, -0.107), (0.026, -0.110),
           (0.021, -0.105), (0.016, -0.090), (0.009, -0.072), (0.004, -0.058), (-0.002, -0.050), (-0.007, -0.042),
           (-0.0085, -0.035), (-0.008, -0.026), (-0.012, -0.016)]
    radii = [0, 0, 0.002, 0.002, 0.002, 0.004, 0.008, 0.02, 0.012, 0.004, 0.003, 0.003, 0.004, 0.012, 0.010,
             0.006, 0.006, 0.005, 0.005, 0.004, 0.004]
    pts = L.round_poly(pts, 0, 2, radii=radii)
    g = P("MAKO_Grip", pts, -0.0148, 0.0148, M["bone"])
    panel = L.round_poly([(0.004, -0.022), (0.027, -0.022), (0.041, -0.064), (0.048, -0.092), (0.028, -0.096),
                          (0.018, -0.078), (0.010, -0.060), (0.004, -0.044)], 0.004, 2)
    cut = [P("_gp1", panel, 0.0136, 0.03, M["stipple"]), P("_gp2", panel, -0.03, -0.0136, M["stipple"])]
    L.boolean(g, cut)
    L.clean(g)
    L.finish(g, bevel=0.0042, segs=2, angle=30, smooth_angle=45)
    return g


def build_trigger():
    pts = [(-0.0355, 0.010), (-0.0440, 0.010), (-0.0440, 0.004), (-0.0470, -0.010), (-0.0500, -0.0215),
           (-0.0455, -0.0240), (-0.0420, -0.0120), (-0.0380, -0.0020), (-0.0355, 0.004)]
    pts = L.round_poly(pts, 0, 2, radii=[0, 0, 0, 0.004, 0.002, 0.002, 0.004, 0.003, 0])
    t = P("MAKO_Trigger", pts, -0.0032, 0.0032, M["gunmetal"])
    L.finish(t, bevel=0.0008, segs=1, angle=30)
    L.set_origin(t, (0.0, -0.040, 0.012))
    return t


HG_OUTER = [(0.013, 0.0745), (-0.013, 0.0745), (-0.023, 0.0655), (-0.023, 0.0345), (-0.0135, 0.025),
            (0.0135, 0.025), (0.023, 0.0345), (0.023, 0.0655)]
HG_WALL = 0.0028
SLOT_Y = [-0.462 + 0.032 * k for k in range(9)]
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
    cut = []
    for k, yc in enumerate(SLOT_Y):
        under_side_rail = SIDE_RAIL_Y[0] - 0.002 < yc < SIDE_RAIL_Y[1] + 0.008
        if not under_side_rail:
            for zc in (0.0572, 0.0428):
                cut.append(P("_s", L.stadium_pts(0.024, 0.0066, 4, yc, zc), -0.03, 0.03, M["dark"]))
        for sgn in (1, -1):  # third row on the bottom chamfers
            c = P("_c", L.stadium_pts(0.024, 0.0062, 3, yc, 0.0), -0.006, 0.006, M["dark"])
            L.rotate(c, "Y", 45 if sgn > 0 else 135)
            L.move(c, (sgn * 0.01825, 0, 0.02975))
            cut.append(c)
    # bottom-front chamfer
    cut.append(P("_fc", [(-0.510, 0.010), (-0.478, 0.010), (-0.510, 0.042)], -0.03, 0.03))
    # QD sling cups near the rear, both sides
    for sgn in (1, -1):
        x0, x1 = (0.0215, 0.03) if sgn > 0 else (-0.03, -0.0215)
        cut.append(L.cyl("_qd", 0.0062, "X", x0, x1, c=(-0.187, 0.050), segs=12))
        h0, h1 = (0.016, 0.03) if sgn > 0 else (-0.03, -0.016)
        cut.append(L.cyl("_qh", 0.0033, "X", h0, h1, c=(-0.187, 0.050), segs=8, mat=M["dark"]))
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
    L.place_rail(bot, (0, 0, 0.025), "-Z")
    side_r, side_c = L.rail("MAKO_RailSide_R", SIDE_RAIL_Y[0], SIDE_RAIL_Y[1], M["graphite"], BASE)
    L.place_rail(side_r, (-0.023, 0, BORE_Z), "-X")
    side_l, _ = L.rail("MAKO_RailSide_L", SIDE_RAIL_Y[0], SIDE_RAIL_Y[1], M["graphite"], BASE)
    L.place_rail(side_l, (0.023, 0, BORE_Z), "+X")
    for r in (top, bot, side_r, side_l):  # convex-only bevels keep the rail cheap
        r.modifiers["Bevel"].limit_method = "WEIGHT"
        me = r.data
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.edges.ensure_lookup_table()
        fl = [convex_sharp(40)(e) for e in bm.edges]
        bm.free()
        at = me.attributes.get("bevel_weight_edge") or me.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
        for i, f in enumerate(fl):
            at.data[i].value = 1.0 if f else 0.0
        try:
            r.modifiers["Bevel"].edge_weight = "bevel_weight_edge"
        except Exception:
            pass
    return (top, bot, side_r, side_l), top_c, bot_c, side_c


def build_barrel():
    br = L.cyl("MAKO_Barrel", 0.0095, "Y", -0.513, -0.150, c=(0, BORE_Z), segs=20, col=BASE, mat=M["gunmetal"])
    gb = L.box("_gb", -0.0105, 0.0105, -0.407, -0.389, 0.0395, 0.0668, mat=M["gunmetal"])
    gt = L.cyl("_gt", 0.0022, "Y", -0.392, -0.168, c=(0, 0.0628), segs=8, mat=M["gunmetal"])
    L.finish(gb, bevel=0.0012, segs=1, uv=False)
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
        c = L.prism("_fs", L.stadium_pts(0.025, 0.0036, 3, 0.0, 0.0), "X", 0.005, 0.016, mat=M["dark"])
        # pill lies in the (y, z) plane, extruded radially along +X -> rotate about Y to the slot angle
        L.rotate(c, "Y", -ang)
        L.move(c, (0, MUZZLE_Y + 0.0195, BORE_Z))
        cut.append(c)
    L.boolean(fh, cut)
    L.clean(fh)
    L.finish(fh, bevel=0.0005, segs=1, angle=60, smooth_angle=40)
    return fh


def build_buffer_tube():
    prof = [(0, 0), (0.0160, 0), (0.0160, 0.183), (0.0150, 0.189), (0.0, 0.189)]
    tb = L.lathe_y("MAKO_BufferTube", prof, 0.026, 1, c=(0, BORE_Z), steps=20, col=BASE, mat=M["graphite"])
    key = L.box("_key", -0.0035, 0.0035, 0.050, 0.212, BORE_Z - 0.0186, BORE_Z - 0.0140)
    L.boolean(tb, key, op="UNION", transfer=False)
    ring_o = L.circle_pts(0.0196, 18)
    ring_i = L.circle_pts(0.0158, 18)
    nut = L.tube("_nut", [(x, z + BORE_Z) for (x, z) in ring_o], [(x, z + BORE_Z) for (x, z) in ring_i], "Y",
                 0.036, 0.0465, mat=M["gunmetal"])
    notches = []
    for k in range(6):
        a = math.radians(30 + 60 * k)
        c = L.box("_nn", -0.0022, 0.0022, 0.0430, 0.050, 0.0170, 0.026)
        L.rotate(c, "Y", math.degrees(a))
        L.move(c, (0, 0, BORE_Z))
        notches.append(c)
    L.boolean(nut, notches)
    L.finish(nut, bevel=0.0006, segs=1, angle=40, uv=False)
    L.finish(tb, bevel=0.0008, segs=1, angle=40, smooth_angle=40, uv=False)
    tb = L.join([tb, nut], "MAKO_BufferTube")
    L.finish(tb, bevel=0, smooth_angle=40)
    return tb


def build_charging_handle():
    plan = [(-0.0055, 0.000), (0.0055, 0.000), (0.0055, 0.0305), (0.0170, 0.0335), (0.0210, 0.0355),
            (0.0210, 0.0400), (0.0185, 0.0425), (-0.0200, 0.0425), (-0.0232, 0.0400), (-0.0232, 0.0345),
            (-0.0190, 0.0320), (-0.0055, 0.0305)]
    ch = T("MAKO_ChargingHandle", plan, 0.0624, 0.0731, M["graphite"])
    # latch (shooter's right, -X): raised grip ridges on the wing
    rid = [L.box("_lr", -0.0228 + 0.0042 * i, -0.0208 + 0.0042 * i, 0.0338, 0.0415, 0.0725, 0.0745)
           for i in range(3)]
    L.boolean(ch, rid, op="UNION", transfer=False)
    L.clean(ch)
    L.finish(ch, bevel=0.0009, segs=1, angle=30)
    L.set_origin(ch, (0.0, 0.030, 0.068))
    return ch


def build_forward_assist():
    prof = [(0, 0), (0.0049, 0), (0.0049, 0.004), (0.0062, 0.0045), (0.0062, 0.0105), (0.0054, 0.0118),
            (0.0030, 0.0118), (0.0030, 0.0113), (0, 0.0113)]
    fa = L.lathe_y("MAKO_ForwardAssist", prof, 0.0195, 1, c=(-0.0172, 0.0585), steps=12, col=BASE,
                   mat=M["gunmetal"])
    grooves = [L.box("_fg", -0.0172 - 0.0007, -0.0172 + 0.0007, 0.0300, 0.0330, 0.0585 - 0.008, 0.0585 + 0.008)]
    L.boolean(fa, grooves)
    L.finish(fa, bevel=0.0005, segs=1, angle=50, smooth_angle=40)
    L.set_origin(fa, (-0.0172, 0.0195, 0.0585))
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
    pts = L.round_poly([(-0.0742, 0.0020), (-0.0658, 0.0020), (-0.0658, 0.0150), (-0.0640, 0.0215),
                        (-0.0690, 0.0262), (-0.0742, 0.0240)], 0.0012, 1)
    bk = P("MAKO_BoltCatch", pts, 0.0153, 0.0192, M["graphite"])
    ribs = [P("_bkr", [(-0.0712, 0.0165 + 0.0024 * i), (-0.0662, 0.0165 + 0.0024 * i),
                       (-0.0662, 0.0176 + 0.0024 * i), (-0.0712, 0.0176 + 0.0024 * i)], 0.0186, 0.0198)
            for i in range(3)]
    L.boolean(bk, ribs, op="UNION", transfer=False)
    L.clean(bk)
    L.finish(bk, bevel=0.0005, segs=1)
    L.set_origin(bk, (0.0170, -0.0700, 0.0060))
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
def build_stock_standard():
    col = COL["MAKO_stock_standard"]
    side = [(0.098, 0.030), (0.098, 0.068), (0.108, 0.078), (0.262, 0.081), (0.262, -0.054), (0.244, -0.054),
            (0.168, 0.012), (0.156, 0.012), (0.146, 0.005), (0.126, 0.005), (0.116, 0.016), (0.108, 0.028)]
    side = L.round_poly(side, 0, 2, radii=[0.003, 0.004, 0.008, 0.003, 0.003, 0.004, 0.008, 0.003, 0.003, 0.003,
                                          0.004, 0.003])
    sec = sym([(0.0125, 0.090), (0.0205, 0.064), (0.0205, 0.030), (0.0145, 0.022), (0.0145, -0.080)])
    st = P("MAKO_stock_standard", side, -0.026, 0.026, M["bone"], col)
    L.intersect(st, S("_ss", sec, 0.09, 0.27, col=col))
    cut = []
    tri = L.round_poly([(0.1685, 0.0280), (0.2465, 0.0280), (0.2465, -0.0397)], 0.005, 3)
    cut.append(P("_sto", tri, -0.03, 0.03, M["bone"], col))
    cut.append(L.cyl("_stc", 0.0166, "Y", 0.090, 0.228, c=(0, BORE_Z), segs=24, mat=M["dark"]))
    L.boolean(st, cut)
    L.clean(st)
    L.finish(st, bevel=0.0028, segs=2, angle=30, smooth_angle=35)
    pad_pts = L.round_poly([(0.2615, 0.0845), (0.2710, 0.0845), (0.2775, 0.0760), (0.2790, -0.0480),
                            (0.2750, -0.0595), (0.2615, -0.0600)], 0.002, 2)
    pad = P("MAKO_stock_standard_ButtPad", pad_pts, -0.0225, 0.0225, M["rubber"], col)
    L.intersect(pad, S("_ps", sym([(0.016, 0.095), (0.0225, 0.080), (0.0225, -0.060), (0.018, -0.070)]), 0.25,
                       0.29, col=col))
    grooves = [L.box("_pg", -0.03, 0.03, 0.2765, 0.29, z - 0.0011, z + 0.0011) for z in (0.045, 0.015, -0.015)]
    L.boolean(pad, grooves, transfer=False)
    L.clean(pad)
    L.finish(pad, bevel=0.0025, segs=2, angle=30)
    lever = L.box("MAKO_stock_standard_Lever", -0.0065, 0.0065, 0.186, 0.226, 0.0240, 0.0290, col=col,
                  mat=M["graphite"])
    lv2 = L.box("_lv2", -0.0055, 0.0055, 0.127, 0.148, 0.0015, 0.0065, mat=M["graphite"])
    lever = L.join([lever, lv2], "MAKO_stock_standard_Lever")
    L.finish(lever, bevel=0.0010, segs=1)
    # sling loop under the leg (v09)
    loop_o = L.round_poly([(0.1900, -0.0200), (0.2080, -0.0200), (0.2080, -0.0380), (0.1900, -0.0380)], 0.007, 3)
    loop_i = L.round_poly([(0.1925, -0.0225), (0.2055, -0.0225), (0.2055, -0.0355), (0.1925, -0.0355)], 0.0050, 3)
    loop = L.tube("_loop", [(y, z) for (y, z) in loop_o], [(y, z) for (y, z) in loop_i], "X", -0.0015, 0.0015,
                  mat=M["gunmetal"])
    L.rotate(loop, "Z", 0)
    boss = L.cyl("_lboss", 0.0042, "Z", -0.0230, -0.0050, c=(0.0, 0.1990), segs=12, mat=M["gunmetal"])
    L.finish(loop, bevel=0.0005, segs=1, uv=False)
    sling = L.join([loop, boss], "MAKO_stock_standard_Sling")
    L.finish(sling, bevel=0, smooth_angle=40)
    return st, [pad, lever, sling]


def build_stock_precision():
    col = COL["MAKO_stock_precision"]
    side = [(0.048, 0.028), (0.048, 0.066), (0.058, 0.0745), (0.252, 0.0745), (0.252, -0.066), (0.226, -0.066),
            (0.214, -0.052), (0.196, -0.050), (0.184, -0.040), (0.172, -0.028), (0.140, -0.004), (0.100, 0.016),
            (0.062, 0.026)]
    side = L.round_poly(side, 0, 2, radii=[0.003, 0.004, 0.008, 0.003, 0.003, 0.006, 0.006, 0.006, 0.010, 0.010,
                                          0.020, 0.020, 0.006])
    sec = sym([(0.0130, 0.090), (0.0220, 0.062), (0.0220, -0.090)])
    st = P("MAKO_stock_precision", side, -0.026, 0.026, M["bone"], col)
    L.intersect(st, S("_ps", sec, 0.04, 0.26, col=col))
    cut = [L.cyl("_ptc", 0.0166, "Y", 0.040, 0.228, c=(0, BORE_Z), segs=24, mat=M["dark"])]
    pan = L.round_poly([(0.105, 0.020), (0.236, 0.020), (0.236, -0.050), (0.212, -0.038), (0.178, -0.016)],
                       0.005, 2)
    cut.append(P("_pp1", pan, 0.0200, 0.03, M["bone"], col))
    cut.append(P("_pp2", pan, -0.03, -0.0200, M["bone"], col))
    # riser post holes
    for y in (0.140, 0.212):
        cut.append(L.cyl("_ph", 0.0042, "Z", 0.066, 0.080, c=(0.0, y), segs=12, mat=M["dark"]))
    L.boolean(st, cut)
    L.clean(st)
    L.finish(st, bevel=0.0030, segs=2, angle=30, smooth_angle=35)
    cheek_side = L.round_poly([(0.112, 0.0790), (0.238, 0.0790), (0.238, 0.0945), (0.228, 0.0975),
                               (0.132, 0.0975), (0.116, 0.0905)], 0.002, 2)
    cheek = P("MAKO_stock_precision_Cheek", cheek_side, -0.0185, 0.0185, M["bone"], col)
    L.intersect(cheek, S("_cs", sym([(0.011, 0.100), (0.0185, 0.090), (0.0185, 0.075)]), 0.10, 0.25, col=col))
    L.clean(cheek)
    L.finish(cheek, bevel=0.0025, segs=2, angle=30)
    posts = [L.cyl("_pst", 0.0032, "Z", 0.068, 0.0805, c=(0.0, y), segs=12, mat=M["gunmetal"]) for y in
             (0.140, 0.212)]
    posts = L.join(posts, "MAKO_stock_precision_Posts")
    L.finish(posts, bevel=0.0004, segs=1, angle=50, smooth_angle=40)
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
    return st, [cheek, posts, pad]


def build_stock_light():
    col = COL["MAKO_stock_light"]
    collar_sec = L.round_poly([(-0.0195, 0.0300), (0.0195, 0.0300), (0.0195, 0.0700), (0.0110, 0.0760),
                               (-0.0110, 0.0760), (-0.0195, 0.0700)], 0.004, 2)
    st = S("MAKO_stock_light", collar_sec, 0.128, 0.214, M["bone"], col)
    L.intersect(st, P("_cp", [(0.128, 0.024), (0.128, 0.068), (0.136, 0.080), (0.214, 0.080), (0.214, 0.024)],
                      -0.03, 0.03, col=col))
    frame_out = [(0.140, 0.034), (0.214, 0.060), (0.2615, 0.070), (0.2615, -0.050), (0.2530, -0.056),
                 (0.2370, -0.056)]
    frame_out = L.round_poly(frame_out, 0, 2, radii=[0.004, 0.010, 0.003, 0.003, 0.003, 0.006])
    frame = P("_frame", frame_out, -0.0095, 0.0095, M["bone"], col)
    opening = L.round_poly([(0.1615, 0.0305), (0.2135, 0.0305), (0.2135, 0.0490), (0.2490, 0.0565),
                            (0.2490, -0.0400), (0.2374, -0.0400)], 0.004, 2)
    L.boolean(frame, P("_fo", opening, -0.03, 0.03, col=col))
    L.boolean(st, frame, op="UNION", transfer=False)
    L.boolean(st, L.cyl("_ltc", 0.0166, "Y", 0.120, 0.226, c=(0, BORE_Z), segs=24, mat=M["dark"]))
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
    spine from the top (m). Straight down to z_straight, then a forward arc."""

    def __init__(self, r_front, sweep_deg, depth=0.064, y_front=-0.152, z_top=0.012, z_straight=-0.020):
        self.rf = r_front
        self.depth = depth
        self.yf = y_front
        self.zt = z_top
        self.zs = z_straight
        self.cy = y_front - r_front
        self.L0 = z_top - z_straight
        self.rmid = r_front + depth / 2
        self.U = self.L0 + self.rmid * math.radians(sweep_deg)

    def theta(self, u):
        return 0.0 if u <= self.L0 else (u - self.L0) / self.rmid

    def F(self, dm, u):
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
        return us


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


def build_box_mag(key, r_front, sweep, win_u, col):
    """STANAG-style curved box magazine with a window slot and visible cartridges."""
    fr = MagFrame(r_front, sweep)
    D = fr.depth
    us = fr.spine(6)
    outline = [fr.F(0.0, u) for u in us] + [fr.F(D, u) for u in reversed(us)]
    body = P(f"MAKO_{key}", outline, -0.0125, 0.0125, M["bone"], col)
    U = fr.U
    # floorplate (dark polymer), flared
    fp = fr.map_pts([(0.0010, U - 0.0010), (D - 0.0010, U - 0.0010), (D + 0.0030, U + 0.0035),
                     (D + 0.0030, U + 0.0085), (D + 0.0010, U + 0.0110), (-0.0010, U + 0.0110),
                     (-0.0030, U + 0.0085), (-0.0030, U + 0.0035)])
    plate = P("_fp", fp, -0.0146, 0.0146, M["graphite"], col)
    L.intersect(plate, S("_fps", sym([(0.0120, 0.30), (0.0146, 0.30), (0.0146, -0.40), (0.0120, -0.40)]), -0.30,
                         0.10, col=col))
    # ribs along the curve (front and rear), both sides
    ribs = []
    for d0 in (0.0070, D - 0.0100):
        us_r = [0.060 + (U - 0.004 - 0.060) * k / 5 for k in range(6)]
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
    # window slot (both sides), follows the curve
    dmc = D * 0.56
    u0, u1 = win_u
    win_half = 0.0040
    n = 6
    left = [(dmc - win_half, u0 + (u1 - u0) * k / n) for k in range(n + 1)]
    right = [(dmc + win_half, u1 - (u1 - u0) * k / n) for k in range(n + 1)]
    wpts = left + [(dmc - win_half * math.cos(math.pi * k / 4), u1 + win_half * math.sin(math.pi * k / 4))
                   for k in range(1, 4)] + right + \
        [(dmc + win_half * math.cos(math.pi * k / 4), u0 - win_half * math.sin(math.pi * k / 4)) for k in range(1, 4)]
    wy = fr.map_pts(wpts)
    cut.append(P("_win", wy, 0.0082, 0.03, M["dark"], col))
    cut.append(P("_win", wy, -0.03, -0.0082, M["dark"], col))
    L.boolean(body, cut)
    L.clean(body)
    L.finish(body, bevel=0.0020, segs=1, angle=30, smooth_angle=35)
    # top round, lying in the channel, tip forward (-Y)
    rnd = round_lathe(f"MAKO_{key}_Round", M["brass"], M["gunmetal"], steps=12, col=col)
    L.move(rnd, (0.0018, -0.0915, 0.0055 + 0.0048))
    L.finish(rnd, bevel=0, smooth_angle=40)
    # visible cartridges behind the window: one column per side (double stack, staggered)
    parts = []
    pitch = 0.0105
    u = u0 - 0.004
    i = 0
    while u < u1 + 0.006:
        for sgn in (1, -1):
            uu = u + (pitch / 2 if sgn < 0 else 0.0)
            th = fr.theta(uu)
            y, z = fr.F(dmc, uu)
            c = L.cyl("_cart", 0.0048, "Y", -0.008, 0.008, c=(0, 0), segs=8, mat=M["brass"])
            L.rotate(c, "X", -math.degrees(th))
            L.move(c, (sgn * 0.0052, y, z))
            parts.append(c)
        u += pitch
        i += 1
    stack = L.join(parts, f"MAKO_{key}_Stack")
    L.finish(stack, bevel=0, smooth_angle=50)
    for o in (body, rnd, stack):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    return body, [rnd, stack]


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
    drum = L.lathe_y("_drum", prof, 0.0, 1, c=(0, 0), steps=28, mat=M["bone"])
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
    # arc window on both drum faces (lower half), showing the cartridges
    rw, hw = 0.0335, 0.0050
    a0, a1 = math.radians(-160), math.radians(-20)
    n = 12
    outer = [(dc[0] + (rw + hw) * math.cos(a0 + (a1 - a0) * k / n), dc[1] + (rw + hw) * math.sin(a0 + (a1 - a0) * k / n))
             for k in range(n + 1)]
    inner = [(dc[0] + (rw - hw) * math.cos(a1 - (a1 - a0) * k / n), dc[1] + (rw - hw) * math.sin(a1 - (a1 - a0) * k / n))
             for k in range(n + 1)]
    wpts = outer + inner
    cut.append(P("_dw", wpts, W - 0.0045, W + 0.01, M["dark"], col))
    cut.append(P("_dw", wpts, -W - 0.01, -W + 0.0045, M["dark"], col))
    L.boolean(neck, cut)
    # hub caps (graphite) + winding key (+X)
    hubs = []
    for sgn in (1, -1):
        x0, x1 = (W - 0.001, W + 0.0035) if sgn > 0 else (-W - 0.0035, -W + 0.001)
        hubs.append(L.cyl("_hub", 0.0175, "X", x0, x1, c=dc, segs=20, mat=M["graphite"]))
    key_t = L.box("_key", W + 0.0030, W + 0.0090, dc[0] - 0.0140, dc[0] + 0.0140, dc[1] - 0.0030,
                  dc[1] + 0.0030, mat=M["gunmetal"])
    L.boolean(neck, hubs + [key_t], op="UNION")
    L.clean(neck)
    L.finish(neck, bevel=0.0018, segs=2, angle=30, smooth_angle=35)
    rnd = round_lathe(f"MAKO_{key}_Round", M["brass"], M["gunmetal"], steps=12, col=col)
    L.move(rnd, (0.0018, -0.0915, 0.0055 + 0.0048))
    L.finish(rnd, bevel=0, smooth_angle=40)
    carts = []
    for k in range(8):
        a = a0 + (a1 - a0) * (k + 0.5) / 8
        y = dc[0] + rw * math.cos(a)
        z = dc[1] + rw * math.sin(a)
        c = round_lathe("_dc", M["brass"], M["gunmetal"], steps=10)
        L.rotate(c, "Z", -90)  # case head at +X, tip toward -X
        L.move(c, (W - 0.0025, y, z))
        carts.append(c)
    stack = L.join(carts, f"MAKO_{key}_Stack")
    L.finish(stack, bevel=0, smooth_angle=50)
    for o in (neck, rnd, stack):
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    return neck, [rnd, stack]


# ===================================================================================================== ASSEMBLY
def to_col(o, col):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    col.objects.link(o)
    return o


def main():
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
        "MAKO_SOCKET_Under": (0.0, nearest(bot_c, -0.335), 0.025 - L.RAIL_H),
        "MAKO_SOCKET_Side_R": (-(0.023 + L.RAIL_H), sum(side_c) / len(side_c), BORE_Z),
        "MAKO_SOCKET_Side_L": (0.023 + L.RAIL_H, sum(side_c) / len(side_c), BORE_Z),
        "MAKO_SOCKET_Shield": (0.0, nearest(top_c, -0.476), RAIL_TOP),
        "MAKO_SOCKET_Muzzle": (0.0, MUZZLE_Y, BORE_Z),
        "MAKO_SOCKET_LeftHand": (0.0, -0.330, 0.025 - L.RAIL_H),
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
        parts[key] = (main_o, kids)
    log("mags")
    for key, rf, sw, win in (("mag_30", 0.48, 15.0, (0.072, 0.132)), ("mag_45", 0.46, 24.0, (0.074, 0.196))):
        main_o, kids = build_box_mag(key, rf, sw, win, COL[f"MAKO_{key}"])
        L.set_origin(main_o, MAG_SOCKET)
        for k in kids:
            L.set_origin(k, MAG_SOCKET)
            L.parent(k, main_o)
        parts[key] = (main_o, kids)
    main_o, kids = build_drum()
    L.set_origin(main_o, MAG_SOCKET)
    for k in kids:
        L.set_origin(k, MAG_SOCKET)
        L.parent(k, main_o)
    parts["mag_drum60"] = (main_o, kids)
    log("parts built")

    bc.uv_all()
    base_meshes = [o for o in base if o.type == "MESH"]

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
    bpy.ops.export_scene.gltf(filepath=path_no_ext + ".glb", export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True)
    bpy.ops.export_scene.fbx(filepath=path_no_ext + ".fbx", use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             use_mesh_modifiers=True, add_leaf_bones=False, path_mode="COPY", embed_textures=True)
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
                              use_selection=True, export_apply=True, export_yup=True)
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
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "mako.blend"), compress=True)
    log("saved mako.blend")


main()
