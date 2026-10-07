"""VK-50 WARDEN - coarse PROPORTION PROXY built only from the numbers in art/concepts/warden/BRIEF.md.
Reference / coordinate cheat sheet for the modeler. NOT the deliverable: no detailing, no sockets, no module split.
Run: blender -b --factory-startup -P warden_proportion_proxy.py
Purpose: verify that the brief's coordinates give the intended silhouette. Not the final asset.
Renders to art/concepts/warden/proxy_*.png
"""
import math
import sys

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402
from mathutils import Vector  # noqa: E402

OUT = r"F:/git/val etf/art/concepts/warden"
BZ = 0.075          # bore height
SZ = 0.178          # scope axis height

bc.reset_scene()
G = bc.material("M_Warden_Graphite", (0.030, 0.033, 0.040), rough=0.55, metal=0.15)
GM = bc.material("M_Warden_Gunmetal", (0.11, 0.115, 0.12), rough=0.35, metal=0.85)
S = bc.material("M_Warden_Sand", (0.36, 0.28, 0.18), rough=0.70)
R = bc.material("M_Warden_Rubber", (0.035, 0.037, 0.045), rough=0.9)
GLOW = bc.material("M_Warden_CounterGlow", (0.45, 0.85, 1.0), rough=0.4, emission=(0.45, 0.85, 1.0),
                   emission_strength=1.0)
ICE = bc.material("M_Warden_IcePaint", (0.45, 0.85, 1.0), rough=0.4)
LENS = bc.material("M_Warden_Lens", (0.010, 0.030, 0.080), rough=0.05, coat=1.0)


def cut(obj, cutter):
    bc.boolean(obj, cutter)


# ---------------------------------------------------------------- receiver + chassis + rail
rec = bc.profile_extrude("WARDEN_Receiver", [(0.080, 0.035), (0.080, 0.112), (0.064, 0.128), (-0.292, 0.128),
                                              (-0.300, 0.120), (-0.300, 0.033), (-0.292, 0.025), (0.072, 0.025)],
                         0.078, mat=G)
# ejection port (shooter's RIGHT = -X) and bolt-handle notch
cut(rec, bc.box("_c1", (0.03, 0.135, 0.042), loc=(-0.039 - 0.003, -0.1075, 0.083)))
cut(rec, bc.box("_c2", (0.03, 0.040, 0.026), loc=(-0.039 - 0.003, 0.062, 0.092)))
# counter bezel recess (LEFT = +X)
cut(rec, bc.box("_c3", (0.008, 0.060, 0.028), loc=(0.039, -0.050, 0.084)))
bc.add_bevel(rec, 0.004, 1)
bc.box("WARDEN_CounterScreen", (0.003, 0.052, 0.020), loc=(0.0365, -0.050, 0.084), mat=GLOW)
bc.box("_EjectBolt", (0.010, 0.135, 0.040), loc=(-0.032, -0.1075, 0.083), mat=GM)

cha = bc.profile_extrude("WARDEN_Chassis", [(0.080, 0.025), (-0.340, 0.025), (-0.296, -0.040),
                                             (-0.290, -0.058), (-0.282, -0.068), (-0.112, -0.068), (-0.104, -0.060),
                                             (-0.104, -0.010), (-0.030, 0.000), (0.040, 0.000), (0.080, -0.010)],
                         0.070, mat=G, bevel=0.004, segments=1)

# stylized picatinny: crenellated side profile extruded across X (rail top width 0.021, height 0.0095)
pts = [(0.078, 0.128)]
y = 0.078
top, slot = 0.1375, 0.1345
while y - 0.010 > -0.690:
    pts += [(y, top), (y - 0.0055, top), (y - 0.0055, slot), (y - 0.010, slot)]
    y -= 0.010
pts += [(y, top), (-0.690, top), (-0.690, 0.128)]
rail = bc.profile_extrude("WARDEN_RailTop", pts, 0.021, mat=G)

# ---------------------------------------------------------------- handguard
hg = bc.box("WARDEN_Handguard", (0.072, 0.390, 0.098), loc=(0, -0.495, 0.079), mat=G, bevel=0.012, segments=1)
cut(hg, bc.cylinder("_tunnel", 0.030, 0.42, loc=(0, -0.495, BZ), rot=(90, 0, 0)))  # hollow it around the barrel
for yc in (-0.370, -0.445, -0.520, -0.595):
    cut(hg, bc.box("_s", (0.2, 0.055, 0.020), loc=(0, yc, 0.084)))
for yc in (-0.400, -0.475):
    cut(hg, bc.box("_s", (0.024, 0.055, 0.04), loc=(0, yc, 0.030)))
for sx in (1, -1):
    bc.box("WARDEN_SideRail", (0.0095, 0.060, 0.021), loc=(sx * (0.036 + 0.00475), -0.645, 0.079), mat=G)
bc.box("WARDEN_RailBottom", (0.021, 0.110, 0.0095), loc=(0, -0.595, 0.030 - 0.00475), mat=G)

# ---------------------------------------------------------------- barrel + brake
bar = bc.lathe("WARDEN_Barrel", [(0, 0.240), (0.023, 0.240), (0.023, 0.600), (0.021, 0.680), (0.021, 0.940),
                                 (0.016, 0.942), (0.016, 0.965), (0, 0.965)], rot=(90, 0, 0), loc=(0, 0, BZ),
               steps=24, mat=GM)
for i in range(6):
    a = math.radians(30 + 60 * i)
    c = bc.box("_f", (0.006, 0.225, 0.006), loc=(0.022 * math.cos(a), -0.8125, BZ + 0.022 * math.sin(a)),
               rot=(0, -math.degrees(a), 0))
    cut(bar, c)
brk = bc.box("WARDEN_Brake", (0.070, 0.150, 0.062), loc=(0, -1.025, BZ), mat=GM, bevel=0.0, smooth=None)
cut(brk, bc.box("_p", (0.2, 0.037, 0.044), loc=(0, -1.0035, BZ)))
cut(brk, bc.box("_p", (0.2, 0.039, 0.044), loc=(0, -1.0545, BZ)))
cut(brk, bc.box("_p", (0.2, 0.013, 0.026), loc=(0, -0.9685, BZ)))
cut(brk, bc.cylinder("_p", 0.010, 0.05, loc=(0, -1.10, BZ), rot=(90, 0, 0)))
bc.add_bevel(brk, 0.006, 1)
bc.cylinder("WARDEN_BrakeCollar", 0.025, 0.012, loc=(0, -0.956, BZ), rot=(90, 0, 0), mat=GM)

# ---------------------------------------------------------------- grip, trigger guard, trigger
bc.profile_extrude("WARDEN_Grip", [(-0.026, 0.004), (0.030, 0.004), (0.042, -0.018), (0.064, -0.110),
                                   (0.062, -0.124), (0.052, -0.132), (0.020, -0.132), (0.010, -0.124),
                                   (-0.004, -0.072), (-0.010, -0.054), (-0.020, -0.036), (-0.026, -0.012)],
                   0.034, mat=S, bevel=0.005)
tg = bc.profile_extrude("WARDEN_TriggerGuard", [(-0.104, -0.005), (-0.104, -0.062), (-0.094, -0.072),
                                                (-0.026, -0.072), (-0.012, -0.058), (-0.014, -0.005)], 0.020, mat=G)
cut(tg, bc.profile_extrude("_h", [(-0.092, -0.004), (-0.092, -0.058), (-0.086, -0.062), (-0.030, -0.062),
                                  (-0.024, -0.054), (-0.026, -0.004)], 0.06))
bc.add_bevel(tg, 0.003, 1)
bc.profile_extrude("WARDEN_Trigger", [(-0.058, 0.000), (-0.050, 0.000), (-0.052, -0.030), (-0.060, -0.048),
                                      (-0.066, -0.046), (-0.060, -0.028)], 0.008, mat=GM)

# ---------------------------------------------------------------- bolt (shooter's right = -X)
bc.cylinder("WARDEN_BoltShroud", 0.024, 0.032, loc=(0, 0.096, BZ), rot=(90, 0, 0), mat=GM, bevel=0.004)
p0, p1 = Vector((-0.032, 0.060, 0.092)), Vector((-0.082, 0.074, 0.048))
d = p1 - p0
arm = bc.box("WARDEN_BoltHandle", (0.018, 0.016, d.length), loc=(p0 + p1) / 2, mat=GM, bevel=0.003)
arm.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
bc.sphere("WARDEN_BoltKnob", 0.024, loc=(-0.092, 0.078, 0.042), segments=8, rings=6, mat=GM, smooth=None)

# ---------------------------------------------------------------- stock_standard
bc.box("WARDEN_StockHinge", (0.052, 0.034, 0.060), loc=(0, 0.097, 0.015), mat=G, bevel=0.004)
st = bc.profile_extrude("WARDEN_Stock", [(0.080, 0.045), (0.122, 0.045), (0.140, 0.080), (0.150, 0.088),
                                         (0.282, 0.092), (0.292, 0.100), (0.292, -0.118), (0.282, -0.126),
                                         (0.240, -0.126), (0.100, -0.032), (0.080, -0.012)], 0.046, mat=S)
cut(st, bc.profile_extrude("_t", [(0.150, 0.054), (0.266, 0.070), (0.266, -0.094)], 0.1))
bc.add_bevel(st, 0.005, 1)
bc.profile_extrude("WARDEN_CheekRiser", [(0.150, 0.100), (0.158, 0.128), (0.172, 0.136), (0.276, 0.136),
                                         (0.284, 0.128), (0.284, 0.100)], 0.040, mat=S, bevel=0.005)
for yp in (0.180, 0.250):
    bc.cylinder("WARDEN_RiserPost", 0.005, 0.012, loc=(0, yp, 0.096), mat=GM)
bc.profile_extrude("WARDEN_RecoilPad", [(0.292, 0.104), (0.312, 0.100), (0.320, 0.082), (0.320, -0.110),
                                        (0.312, -0.126), (0.292, -0.130)], 0.050, mat=R, bevel=0.004)
bc.box("WARDEN_MonopodHousing", (0.034, 0.030, 0.022), loc=(0, 0.205, -0.106), mat=G, bevel=0.003)
bc.cylinder("WARDEN_MonopodColumn", 0.010, 0.065, loc=(0, 0.205, -0.1475), mat=GM)
bc.cylinder("WARDEN_MonopodCollar", 0.0135, 0.014, loc=(0, 0.205, -0.140), verts=12, mat=GM)
bc.cylinder("WARDEN_MonopodSpike", 0.010, 0.018, loc=(0, 0.205, -0.189), rot=(180, 0, 0), radius2=0.001, mat=GM)

# ---------------------------------------------------------------- mag_5
bc.profile_extrude("WARDEN_Mag5", [(-0.270, 0.000), (-0.120, 0.000), (-0.118, -0.150), (-0.276, -0.150)],
                   0.052, mat=G, bevel=0.004)
bc.box("WARDEN_Mag5Floor", (0.058, 0.170, 0.018), loc=(0, -0.197, -0.159), mat=S, bevel=0.004)

# ---------------------------------------------------------------- optic_sniper (axis z = SZ)
prof = [(0, -0.065), (0.0200, -0.065), (0.0250, -0.060), (0.0250, -0.012), (0.0230, -0.010), (0.0230, 0.002),
        (0.0185, 0.012), (0.0185, 0.165), (0.0340, 0.212), (0.0340, 0.255), (0.0300, 0.255), (0, 0.255)]
bc.lathe("ATT_Scope", prof, rot=(90, 0, 0), loc=(0, 0, SZ), steps=32, mat=G)
bc.lathe("ATT_ScopeIceRing", [(0.0320, 0.255), (0.0355, 0.255), (0.0355, 0.265), (0.0320, 0.265)],
         rot=(90, 0, 0), loc=(0, 0, SZ), steps=32, mat=ICE)
bc.lathe("ATT_Sunshade", [(0.0300, 0.265), (0.0330, 0.265), (0.0330, 0.315), (0.0300, 0.315)],
         rot=(90, 0, 0), loc=(0, 0, SZ), steps=32, mat=G)
bc.cylinder("ATT_LensObj", 0.0301, 0.002, loc=(0, -0.256, SZ), rot=(90, 0, 0), mat=LENS)
bc.cylinder("ATT_LensEye", 0.0201, 0.002, loc=(0, 0.066, SZ), rot=(90, 0, 0), mat=LENS)
bc.box("ATT_Saddle", (0.044, 0.062, 0.044), loc=(0, -0.080, SZ), mat=G, bevel=0.008)
bc.cylinder("ATT_TurretElev", 0.019, 0.028, loc=(0, -0.080, SZ + 0.022 + 0.014), verts=16, mat=G, bevel=0.003)
bc.cylinder("ATT_TurretWind", 0.019, 0.026, loc=(-0.022 - 0.013, -0.080, SZ), rot=(0, 90, 0), verts=16, mat=G,
            bevel=0.003)
bc.cylinder("ATT_SideFocus", 0.017, 0.018, loc=(0.022 + 0.009, -0.080, SZ), rot=(0, 90, 0), verts=16, mat=G,
            bevel=0.003)
for yr in (-0.020, -0.140):
    bc.cylinder("ATT_Ring", 0.027, 0.018, loc=(0, yr, SZ), rot=(90, 0, 0), mat=G)
    bc.box("ATT_RingBase", (0.034, 0.024, SZ - 0.1375), loc=(0, yr, (SZ + 0.1375) / 2), mat=G, bevel=0.003)

# ---------------------------------------------------------------- bipod (deployed, 50 deg from rail)
bc.box("ATT_BipodClamp", (0.044, 0.050, 0.018), loc=(0, -0.600, 0.0115), mat=G, bevel=0.004)
bc.box("ATT_BipodHinge", (0.060, 0.030, 0.020), loc=(0, -0.600, -0.0075), mat=G, bevel=0.004)
for sx in (1, -1):
    hinge = Vector((sx * 0.024, -0.600, -0.008))
    dirv = Vector((sx * 0.133, -0.643, -0.754)).normalized()
    q = dirv.to_track_quat("Z", "Y").to_euler()
    up = bc.box("ATT_BipodLegUpper", (0.022, 0.016, 0.140), loc=hinge + dirv * 0.070, mat=G, bevel=0.003)
    up.rotation_euler = q
    lo = bc.box("ATT_BipodLegLower", (0.015, 0.012, 0.130), loc=hinge + dirv * 0.185, mat=GM, bevel=0.002)
    lo.rotation_euler = q
    ft = bc.box("ATT_BipodFoot", (0.026, 0.030, 0.016), loc=hinge + dirv * 0.250 + Vector((0, 0, 0.004)),
                mat=R, bevel=0.004)

bc.uv_all()
bc.setup_studio(bg=(0.55, 0.56, 0.58))
bc.stats()
paths = bc.render_views(OUT, "proxy", views=("right", "left", "three_quarter"), res=(1536, 768), ortho=True,
                        lens=85, margin=1.05)


# ---------------------------------------------------------------- exact 1 px = 1 mm orthographic sheets
import bpy  # noqa: E402
sc = bpy.context.scene
cam = bpy.data.objects["_PreviewCam"]
cam.data.type = "ORTHO"
sc.render.resolution_percentage = 100


def exact(name, loc, rot, w, h):
    sc.render.resolution_x, sc.render.resolution_y = w, h
    cam.data.ortho_scale = max(w, h) / 1000.0
    cam.location = loc
    cam.rotation_euler = [math.radians(v) for v in rot]
    sc.render.filepath = OUT + "/" + name
    bpy.ops.render.render(write_still=True)


# left side of the gun (camera on +X looking -X): screen right = +Y. Window y -1.19..0.41, z -0.305..0.335
exact("_exact_side.png", (2.0, -0.39, 0.015), (90, 0, 90), 1600, 640)
# top view (camera above looking down, screen right = +Y, screen up = -X). Window y -1.19..0.41, x -0.16..0.16
exact("_exact_top.png", (0.0, -0.39, 2.0), (0, 0, 90), 1600, 320)
