"""KESTREL proportion blockout — validates the numbers in BRIEF.md (body rings, limb paths, gear placement).

NOT the final model. It is a reference the modeler can run, render and copy helpers from:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P kes_proportion_blockout.py -- <out_dir>
Writes bo_front/bo_her_left/bo_her_right/bo_back.png (ortho, 1 m = 500 px, image centre = (x 0, z 0.88)).
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "_blockout")
os.makedirs(OUT, exist_ok=True)


# ----------------------------------------------------------------------------- helpers (copy these)
def ring(c, rx, ry, n=24, p=2.0, frame=None):
    """Superellipse ring (p=2 ellipse, p>2 boxier) centred at c, in the plane spanned by frame=(u, v)."""
    u, v = frame or (Vector((1, 0, 0)), Vector((0, 1, 0)))
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        x = rx * math.copysign(abs(ca) ** (2 / p), ca)
        y = ry * math.copysign(abs(sa) ** (2 / p), sa)
        pts.append(Vector(c) + u * x + v * y)
    return pts


def loft(name, rings, cap_start=True, cap_end=True, mat=None, smooth=50):
    """Skin consecutive rings (equal vertex counts) with quads; optional n-gon caps."""
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in r] for r in rings]
    n = len(rings[0])
    for a, b in zip(vr, vr[1:]):
        for i in range(n):
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    if cap_start:
        bm.faces.new(list(reversed(vr[0])))
    if cap_end:
        bm.faces.new(vr[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if mat:
        bc.assign(ob, mat)
    bc.shade_smooth(ob, smooth)
    return ob


def body_loft(name, table, n=24, **kw):
    """table rows (z, rx, ry, cy, p): horizontal superellipse rings stacked along Z (torso, pelvis)."""
    return loft(name, [ring((0, cy, z), rx, ry, n, p) for (z, rx, ry, cy, p) in table], **kw)


def tube(name, path, radii, n=12, **kw):
    """Sweep rings along a polyline; radii[i] = r or (r_side, r_frontback). Limbs, sleeves, straps."""
    rings = []
    for i, p in enumerate(path):
        p = Vector(p)
        t = (Vector(path[min(i + 1, len(path) - 1)]) - Vector(path[max(i - 1, 0)])).normalized()
        ref = Vector((0, -1, 0)) if abs(t.y) < 0.9 else Vector((0, 0, 1))
        v = (ref - t * ref.dot(t)).normalized()       # points to the front (-Y) where possible
        u = v.cross(t).normalized()
        r = radii[i] if isinstance(radii[i], (tuple, list)) else (radii[i], radii[i])
        rings.append(ring(p, r[0], r[1], n, 2.0, (u, v)))
    return loft(name, rings, **kw)


def ell(name, loc, radii, mat):
    return bc.sphere(name, 1.0, loc=loc, scale=radii, segments=24, rings=12, mat=mat)


# ----------------------------------------------------------------------------- materials (brief §6)
bc.reset_scene()
sc = bpy.context.scene
M = dict(
    skin=bc.material("M_KES_Skin", (0.62, 0.42, 0.33), 0.6),
    jacket=bc.material("M_KES_Jacket", (0.035, 0.037, 0.045), 0.7),
    suit=bc.material("M_KES_UnderSuit", (0.020, 0.025, 0.050), 0.5),
    pants=bc.material("M_KES_Pants", (0.028, 0.030, 0.036), 0.75),
    bone=bc.material("M_KES_Bone", (0.55, 0.52, 0.46), 0.5),
    graph=bc.material("M_KES_Graphite", (0.030, 0.033, 0.040), 0.55),
    gun=bc.material("M_KES_Gunmetal", (0.11, 0.115, 0.12), 0.35, 0.85),
    web=bc.material("M_KES_Webbing", (0.12, 0.13, 0.08), 0.8),
    teal=bc.material("M_KES_Teal", (0.0, 0.70, 0.62), 0.5),
    glow=bc.material("M_KES_Glow", (0.0, 0.70, 0.62), 0.4, emission=(0.0, 0.70, 0.62), emission_strength=5),
    hair=bc.material("M_KES_Hair", (0.010, 0.016, 0.035), 0.45),
)

# ----------------------------------------------------------------------------- body (brief §3/§4)
# head: ellipsoid + jaw taper (brief §5 face recipe, simplified)
head = ell("KES_Head", (0, 0.004, 1.588), (0.074, 0.094, 0.112), M["skin"])
bc.apply_modifiers(head)
for v in head.data.vertices:
    w = head.matrix_world @ v.co
    t = max(0.0, (1.590 - w.z) / 0.113)
    w.x *= 1 - 0.38 * t * t
    if w.y > 0:
        w.y = 0.004 + (w.y - 0.004) * (1 - 0.25 * t)
    v.co = head.matrix_world.inverted() @ w
tube("KES_Neck", [(0, 0.008, 1.395), (0, 0.006, 1.50)], [0.050, 0.047], mat=M["skin"])

# jacket torso shell: (z, rx, ry, cy, p)
body_loft("KES_Jacket", [
    (1.140, 0.132, 0.098, 0.000, 2.4),
    (1.170, 0.136, 0.102, 0.000, 2.4),
    (1.220, 0.148, 0.110, -0.004, 2.4),
    (1.270, 0.156, 0.118, -0.008, 2.4),
    (1.320, 0.160, 0.112, -0.004, 2.5),
    (1.370, 0.163, 0.100, 0.000, 2.6),
    (1.405, 0.150, 0.086, 0.004, 2.8),
    (1.425, 0.110, 0.074, 0.008, 2.4),
    (1.437, 0.072, 0.066, 0.008, 2.0),
], mat=M["jacket"])
# collar: tall funnel, back higher than front
bm_rings = []
for z0, r in [(1.405, (0.088, 0.082)), (1.455, (0.080, 0.075)), (1.50, (0.083, 0.078))]:
    pts = ring((0, 0.008, z0), r[0], r[1], 24)
    bm_rings.append([Vector((p.x, p.y, p.z + (0.035 * (p.y + 0.07) / 0.15 if z0 > 1.41 else 0))) for p in pts])
loft("KES_Collar", bm_rings, cap_start=False, cap_end=False, mat=M["jacket"])
# under-suit midriff band
body_loft("KES_UnderSuit", [
    (0.990, 0.150, 0.105, 0.006, 2.2),
    (1.020, 0.136, 0.098, 0.004, 2.2),
    (1.070, 0.120, 0.088, 0.000, 2.2),
    (1.100, 0.122, 0.090, 0.000, 2.2),
    (1.160, 0.126, 0.094, 0.000, 2.2),
], mat=M["suit"])
# pants: pelvis + two legs
body_loft("KES_PantsPelvis", [
    (0.800, 0.120, 0.090, 0.010, 2.2),
    (0.830, 0.165, 0.112, 0.008, 2.3),
    (0.885, 0.170, 0.115, 0.010, 2.3),
    (0.960, 0.160, 0.110, 0.008, 2.2),
    (1.000, 0.152, 0.106, 0.006, 2.2),
], mat=M["pants"])
LEG = [((0.085, 0.005, 0.86), (0.088, 0.092)), ((0.095, 0.000, 0.74), (0.080, 0.082)),
       ((0.104, -0.005, 0.60), (0.066, 0.068)), ((0.110, -0.008, 0.47), (0.056, 0.058)),
       ((0.114, 0.002, 0.36), (0.056, 0.060)), ((0.117, 0.006, 0.24), (0.048, 0.050)),
       ((0.118, 0.006, 0.13), (0.050, 0.054))]
for s, side in ((1, "L"), (-1, "R")):
    tube(f"KES_PantsLeg_{side}", [(s * p[0], p[1], p[2]) for p, _ in LEG], [r for _, r in LEG], n=16,
         mat=M["pants"])

# arms (A-pose): shoulder joint, elbow, wrist, fingertip
def arm_points(s):
    sh = Vector((s * 0.165, 0.0, 1.360))  # glenohumeral joint (acromion top = 1.395)
    a = math.radians(45)
    el = sh + Vector((s * math.sin(a), 0, -math.cos(a))) * 0.290
    fd = Vector((s * math.sin(math.radians(50)), -0.17, -math.cos(math.radians(50)))).normalized()
    wr = el + fd * 0.250
    return sh, el, wr, fd


for s, side in ((1, "L"), (-1, "R")):
    sh, el, wr, fd = arm_points(s)
    ad = (el - sh).normalized()
    print(f"arm {side}: shoulder {tuple(round(c, 3) for c in sh)} elbow {tuple(round(c, 3) for c in el)} "
          f"wrist {tuple(round(c, 3) for c in wr)}")
    cuff = el + fd * 0.11
    tube(f"KES_Sleeve_{side}",
         [Vector((s * 0.125, 0.004, 1.355)), sh + Vector((s * 0.014, 0, 0.004)), sh + ad * 0.08, sh + ad * 0.18,
          el, el + fd * 0.06, cuff],
         [0.055, 0.058, 0.050, 0.046, 0.044, 0.045, 0.048], n=16, mat=M["jacket"])
    tube(f"KES_Forearm_{side}", [cuff - fd * 0.02, wr], [0.036, 0.028], n=12, mat=M["skin"])
    hand_end = wr + fd * 0.18
    tube(f"KES_Hand_{side}", [wr, wr + fd * 0.09, hand_end], [(0.042, 0.017), (0.044, 0.016), (0.030, 0.011)],
         n=12, mat=M["graph"])
    if s == 1:  # grapple on LEFT forearm, along the top/outer face
        up = Vector((0, 0, 1)) - fd * fd.z
        up.normalize()
        g0, g1 = cuff + fd * 0.01 + up * 0.04, wr + fd * 0.035 + up * 0.04
        tube("KES_Grapple_Barrel", [g0, g1], [0.017, 0.017], n=12, mat=M["graph"])
        tube("KES_Grapple_Housing", [cuff + fd * 0.015 + up * 0.018, wr - fd * 0.01 + up * 0.018],
             [(0.030, 0.022), (0.028, 0.020)], n=12, mat=M["bone"])

# ----------------------------------------------------------------------------- armor + gear (brief §4)
bc.box("KES_ChestPlate", (0.25, 0.022, 0.20), loc=(0, -0.136, 1.265), mat=M["bone"], bevel=0.015)
for x in (-0.012, 0.012):
    bc.box(f"KES_Pip{x}", (0.010, 0.008, 0.042), loc=(x, -0.150, 1.295), mat=M["graph"])
bc.box("KES_BackPlate", (0.21, 0.018, 0.17), loc=(0, 0.124, 1.310), mat=M["bone"], bevel=0.012)
bc.box("KES_JetPack", (0.22, 0.085, 0.15), loc=(0, 0.168, 1.170), mat=M["graph"], bevel=0.02)
for s in (-1, 1):
    base = Vector((s * 0.090, 0.200, 1.120))
    d = Vector((s * 0.30, 0.55, -0.78)).normalized()
    tube(f"KES_Thruster{s}", [base - d * 0.02, base + d * 0.07], [0.046, 0.046], n=16, mat=M["bone"])
    tube(f"KES_Nozzle{s}", [base + d * 0.06, base + d * 0.115], [0.036, 0.042], n=16, mat=M["gun"],
         cap_end=False)
    ell(f"KES_Glow{s}", base + d * 0.10, (0.033, 0.033, 0.012), M["glow"])
body_loft("KES_Belt", [(0.958, 0.164, 0.117, 0.006, 2.2), (0.993, 0.158, 0.113, 0.006, 2.2)], mat=M["graph"])
bc.box("KES_Pouch1", (0.045, 0.03, 0.06), loc=(0.075, -0.117, 0.950), rot=(0, 0, 20), mat=M["web"], bevel=0.008)
bc.box("KES_Pouch2", (0.045, 0.03, 0.06), loc=(0.133, -0.080, 0.950), rot=(0, 0, 40), mat=M["web"], bevel=0.008)
bc.box("KES_CargoPocket", (0.030, 0.10, 0.13), loc=(0.188, -0.005, 0.680), mat=M["pants"], bevel=0.006)
for x in (-0.013, 0.013):
    bc.box(f"KES_BackPip{x}", (0.010, 0.008, 0.044), loc=(x, 0.136, 1.355), mat=M["graph"])
bc.box("KES_Holster", (0.045, 0.13, 0.20), loc=(-0.205, -0.005, 0.735), mat=M["web"], bevel=0.012)
for s in (-1, 1):
    bc.box(f"KES_KneePad{s}", (0.095, 0.024, 0.125), loc=(s * 0.110, -0.080, 0.475), mat=M["bone"], bevel=0.012)
    pts = [(-0.045, 0.0), (0.21, 0.0), (0.22, 0.03), (0.13, 0.06), (0.03, 0.10), (0.03, 0.15),
           (-0.06, 0.15), (-0.065, 0.03)]
    boot = bc.profile_extrude(f"KES_Boot{s}", [(-y, z) for (y, z) in pts], 0.098, mat=M["graph"], bevel=0.012)
    boot.location = (s * 0.120, 0.015, 0.0)
    boot.rotation_euler = (0, 0, math.radians(-s * 8))
# hair: cap + long right side + teal tips; monocle on LEFT eye (+X)
ell("KES_HairCap", (-0.006, 0.006, 1.625), (0.083, 0.104, 0.088), M["hair"])
tube("KES_HairR", [(-0.050, -0.090, 1.665), (-0.085, -0.080, 1.600), (-0.083, -0.062, 1.530)],
     [(0.030, 0.012), (0.026, 0.012), (0.020, 0.010)], n=10, mat=M["hair"])
tube("KES_HairTipR", [(-0.083, -0.062, 1.532), (-0.078, -0.060, 1.470)], [(0.020, 0.010), (0.006, 0.004)], n=10,
     mat=M["teal"])
bc.box("KES_MonocleLens", (0.050, 0.006, 0.034), loc=(0.034, -0.100, 1.592), rot=(0, 0, 15), mat=M["glow"])
bc.box("KES_Earpiece", (0.020, 0.032, 0.042), loc=(0.092, 0.006, 1.580), mat=M["graph"], bevel=0.006)

bc.stats()

# ----------------------------------------------------------------------------- render
bc.setup_studio(sc, bg=(0.55, 0.56, 0.58))
bc._set_engine(sc)
try:
    sc.view_settings.view_transform = "Standard"
except Exception:
    pass
sc.render.resolution_x = sc.render.resolution_y = 1000
cam_d = bpy.data.cameras.new("_cam")
cam_d.type = "ORTHO"
cam_d.ortho_scale = 2.0
cam = bpy.data.objects.new("_cam", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
C = Vector((0, 0, 0.88))
for name, d in [("front", (0, -1, 0)), ("her_left", (1, 0, 0)), ("her_right", (-1, 0, 0)), ("back", (0, 1, 0))]:
    cam.location = C + Vector(d) * 5
    cam.rotation_euler = (C - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, f"bo_{name}.png")
    bpy.ops.render.render(write_still=True)
print("BLOCKOUT DONE")
