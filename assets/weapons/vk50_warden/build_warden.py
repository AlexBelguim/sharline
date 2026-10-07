"""VK-50 "WARDEN" heavy-calibre bolt-action sniper -- modular build (base + stocks + magazines).

Re-runnable from scratch. Builds everything procedurally, saves warden.blend and exports
  warden_base.glb/.fbx                       base gun (WARDEN_Root + meshes + socket empties)
  warden_stock_standard.glb/.fbx             default stock      (origin = stock mount point)
  warden_stock_folding.glb/.fbx              folding stock      (origin = stock mount point)
  warden_mag_5.glb/.fbx, warden_mag_8.glb/.fbx  magazines        (origin = mag socket point)
  warden_default.glb                          base + stock_standard + mag_5 assembled on their sockets
  sockets.json

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P build_warden.py -- [--render none|quick|full]

Conventions (art/STYLE_GUIDE.md, art/WEAPON_MODULAR_SPEC.md, art/DIRECTION_LOG.md):
  metres, Z up, muzzle -Y, origin = top centre of the pistol grip, bore axis x=0 z=0.075.
  Shooter's RIGHT = -X (bolt handle, ejection port), LEFT = +X.
  No ammo counter, no emissive anywhere on the gun. Scope and bipod are separate attachments (other agents).
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

OUT = r"F:/git/val etf/assets/weapons/vk50_warden"
REN = os.path.join(OUT, "renders")
P = "WARDEN"
BZ = 0.075            # bore axis height
RAIL_TOP_Z = 0.1375   # top rail top surface
T0 = time.time()

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--render", default="none", help="none | quick | full | compare")
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--no-export", action="store_true")
ARGS = ap.parse_args(argv)


def log(*a):
    print(f"[warden {time.time() - T0:6.1f}s]", *a, flush=True)


# =============================================================================================== helpers
def _new_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def prism(name, pts, axis, a0, a1, mat=None):
    """Extrude a closed 2D polygon along an axis.
    axis 'X': pts are (y, z); 'Y': pts are (x, z); 'Z': pts are (x, y). The prism spans a0..a1 on that axis."""
    def p3(u, v, a):
        return {"X": (a, u, v), "Y": (u, a, v), "Z": (u, v, a)}[axis]
    bm = bmesh.new()
    vs = [bm.verts.new(p3(u, v, a0)) for (u, v) in pts]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    d = {"X": (a1 - a0, 0, 0), "Y": (0, a1 - a0, 0), "Z": (0, 0, a1 - a0)}[axis]
    bmesh.ops.translate(bm, vec=Vector(d), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _new_obj(name, bm)
    if mat:
        bc.assign(obj, mat)
    return obj


def hull(name, points, mat=None):
    bm = bmesh.new()
    for p in points:
        bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _new_obj(name, bm)
    if mat:
        bc.assign(obj, mat)
    return obj


def rounded_rect(cu, cv, w, h, r, n=4):
    """Closed polygon (u, v) of a w x h rectangle centred at (cu, cv) with corner radius r."""
    r = min(r, w / 2 * 0.999, h / 2 * 0.999)
    pts = []
    for (ccx, ccy, a0) in [(cu + w / 2 - r, cv + h / 2 - r, 0), (cu - w / 2 + r, cv + h / 2 - r, 90),
                           (cu - w / 2 + r, cv - h / 2 + r, 180), (cu + w / 2 - r, cv - h / 2 + r, 270)]:
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def stadium(cu, cv, w, h, n=5):
    return rounded_rect(cu, cv, w, h, min(w, h) / 2, n)


def band(pts, w):
    """Polygon outlining a polyline with width w (mitred joins) -- for panel-line groove cutters."""
    def nrm(a, b):
        d = Vector((b[0] - a[0], b[1] - a[1])).normalized()
        return Vector((-d.y, d.x))
    left, right = [], []
    for i, p in enumerate(pts):
        pv = Vector(p)
        if i == 0:
            n = nrm(pts[0], pts[1])
        elif i == len(pts) - 1:
            n = nrm(pts[-2], pts[-1])
        else:
            n1, n2 = nrm(pts[i - 1], p), nrm(p, pts[i + 1])
            n = (n1 + n2).normalized()
            n = n / max(0.3, n.dot(n1))
        left.append(tuple(pv + n * w / 2))
        right.append(tuple(pv - n * w / 2))
    return left + right[::-1]


def bake(obj):
    """Apply the object transform into the mesh (object ends at identity, origin = world 0)."""
    obj.data.transform(obj.matrix_basis)
    obj.matrix_basis = Matrix.Identity(4)
    return obj


def set_origin(obj, point):
    """Move the object origin to world `point` without moving the geometry (object must be un-parented)."""
    point = Vector(point)
    mw = obj.matrix_world.copy()
    local = mw.inverted() @ point
    obj.data.transform(Matrix.Translation(-local))
    obj.matrix_world = mw @ Matrix.Translation(local)
    return obj


def cut(obj, *cutters):
    for c in cutters:
        bc.boolean(obj, c, "DIFFERENCE")
    return obj


def union(obj, *others):
    for c in others:
        bc.boolean(obj, c, "UNION")
    return obj


def intersect(obj, other):
    return bc.boolean(obj, other, "INTERSECT")


def finish(obj, width, segs=1, angle=30, harden=True):
    """Hard-surface finish: smooth shading + angle-based sharp edges + bevel (harden normals), applied."""
    for p in obj.data.polygons:
        p.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(angle))
    if width > 0:
        m = obj.modifiers.new("Bevel", "BEVEL")
        m.width = width
        m.segments = segs
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(angle)
        m.harden_normals = harden
        m.miter_outer = "MITER_ARC"
        m.use_clamp_overlap = True
        bc.apply_modifiers(obj)
    return obj


def smooth(obj, angle=35):
    for p in obj.data.polygons:
        p.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(angle))
    return obj


def lathe_y(name, prof_ry, x=0.0, z=BZ, steps=24, mat=None, angle=40):
    """Lathe around an axis parallel to Y through (x, z). prof_ry = [(r, y), ...] (open or closed at r=0)."""
    obj = bc.lathe(name, [(r, -y) for (r, y) in prof_ry], rot=(90, 0, 0), loc=(x, 0, z), steps=steps, mat=mat,
                   smooth=None)
    bake(obj)
    smooth(obj, angle)
    return obj


def lathe_dir(name, prof_rt, center, direction, steps=16, mat=None, angle=40):
    """Lathe around an arbitrary axis through `center` pointing along `direction`; prof = [(r, t), ...]."""
    obj = bc.lathe(name, prof_rt, steps=steps, mat=mat, smooth=None)
    q = Vector(direction).normalized().to_track_quat("Z", "Y")
    obj.matrix_basis = Matrix.Translation(Vector(center)) @ q.to_matrix().to_4x4()
    bake(obj)
    smooth(obj, angle)
    return obj


def box(name, size, loc, mat=None, rot=None):
    o = bc.box(name, size, loc=loc, mat=mat, smooth=None)
    if rot is not None:
        o.rotation_euler = rot
    return bake(o)


def cyl(name, r, depth, loc, axis="Y", verts=16, mat=None, r2=None):
    rot = {"X": (0, 90, 0), "Y": (90, 0, 0), "Z": (0, 0, 0)}[axis]
    o = bc.cylinder(name, r, depth, loc=loc, rot=rot, verts=verts, mat=mat, smooth=None, radius2=r2)
    return bake(o)


def knurl_cyl(name, r, depth, loc, axis="Z", verts=16, dent=0.001, mat=None):
    """Cylinder whose every other rim vertex is pushed in by `dent` (cheap knurl / grip ridges)."""
    o = cyl(name, r, depth, loc, axis, verts, mat)
    c = Vector(loc)
    ax = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[axis]
    rings = {}
    for v in o.data.vertices:
        d = v.co - c
        radial = d - ax * d.dot(ax)
        if radial.length < 1e-6:
            continue
        u = radial.normalized()
        ref = Vector((0, 1, 0)) if axis != "Y" else Vector((1, 0, 0))
        ref = (ref - ax * ref.dot(ax)).normalized()
        ang = math.atan2(ax.cross(ref).dot(u), ref.dot(u)) % (2 * math.pi)
        rings.setdefault(round(d.dot(ax), 5), []).append((ang, v, u))
    for ring in rings.values():
        for i, (_, v, u) in enumerate(sorted(ring, key=lambda t: t[0])):
            if i % 2:
                v.co -= u * dent
    return o


def mat_slots(obj, *mats):
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)


def join(objs, name):
    out = bc.join(objs, name)
    return out


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ============================================================================================== materials
def mats():
    T = bc.TEXTURES
    return dict(
        G=bc.material("M_Warden_Graphite", (0.030, 0.033, 0.040), rough=0.55, metal=0.15,
                      tex=os.path.join(T, "worn_paint.png"), tex_mix=0.5, tex_scale=1.5),
        GM=bc.material("M_Warden_Gunmetal", (0.11, 0.115, 0.12), rough=0.35, metal=0.85,
                       tex=os.path.join(T, "brushed_metal.png"), tex_mix=0.3, tex_scale=2.5),
        S=bc.material("M_Warden_Sand", (0.36, 0.28, 0.18), rough=0.70,
                      tex=os.path.join(T, "worn_paint.png"), tex_mix=0.3, tex_scale=1.5),
        SS=bc.material("M_Warden_SandStipple", (0.36, 0.28, 0.18), rough=0.78,
                       tex=os.path.join(T, "polymer_stipple.png"), tex_mix=0.45, tex_scale=4.0),
        R=bc.material("M_Warden_Rubber", (0.035, 0.037, 0.045), rough=0.90),
        # steel-cased 12.7 mm rounds: a lighter, less metallic gunmetal so they read through the mag window
        C=bc.material("M_Warden_Cartridge", (0.36, 0.34, 0.30), rough=0.38, metal=0.35,
                      tex=os.path.join(T, "brushed_metal.png"), tex_mix=0.25, tex_scale=2.5),
    )


# ================================================================================================= rails
RAIL_SEC = [(-0.0075, -0.0012), (0.0075, -0.0012), (0.0075, 0.0030), (0.0105, 0.0060), (0.0105, 0.0095),
            (-0.0105, 0.0095), (-0.0105, 0.0060), (-0.0075, 0.0030)]


def rail(name, length, mat, bevel=0.0):
    """Stylised Picatinny along local Y, centred at y=0, base z=0, top z=0.0095, top width 0.021,
    cross slots 0.0045 long x 0.003 deep every 0.010 m (centred so both ends keep a full tooth)."""
    obj = prism(name, RAIL_SEC, "Y", -length / 2, length / 2, mat)
    n = int((length - 0.008) / 0.010) + 1
    first = -(n - 1) * 0.010 / 2
    cs = [box("_slot", (0.03, 0.0045, 0.006), (0, first + i * 0.010, 0.0095 - 0.003 + 0.003)) for i in range(n)]
    cutter = join(cs, "_slots")
    cut(obj, cutter)
    finish(obj, bevel, 1)
    return obj


def place(obj, rot_y_deg=0.0, loc=(0, 0, 0)):
    obj.matrix_basis = Matrix.Translation(Vector(loc)) @ Matrix.Rotation(math.radians(rot_y_deg), 4, "Y")
    return bake(obj)


# =========================================================================================== BASE GUN
def build_base(M, col):
    G, GM, S, SS = M["G"], M["GM"], M["S"], M["SS"]
    parts = []

    # ------------------------------------------------------------------ receiver (monolithic upper)
    side = prism("WARDEN_Receiver", [(0.080, 0.035), (0.080, 0.112), (0.064, 0.128), (-0.292, 0.128),
                                     (-0.300, 0.120), (-0.300, 0.033), (-0.292, 0.025), (0.072, 0.025)],
                 "X", -0.045, 0.045, G)
    sec = prism("_rsec", [(-0.020, 0.010), (0.020, 0.010), (0.039, 0.029), (0.039, 0.117), (0.016, 0.140),
                          (-0.016, 0.140), (-0.039, 0.117), (-0.039, 0.029)], "Y", -0.32, 0.10)
    rec = intersect(side, sec)
    # bolt raceway (internal, shows through the port and at the rear face)
    cut(rec, cyl("_race", 0.0205, 0.27, (0, -0.050, BZ), "Y", 24))
    # ejection port, shooter's RIGHT (-X)
    cut(rec, prism("_eport", rounded_rect(-0.1075, 0.081, 0.135, 0.040, 0.006), "X", -0.06, -0.010))
    # bolt-handle notch (-X), open to the rear
    cut(rec, prism("_notch", [(0.040, 0.078), (0.090, 0.078), (0.090, 0.106), (0.046, 0.106)], "X", -0.06, -0.012))
    # panel-line grooves, LEFT (+X): stepped line running from the chin up to the rear
    gl = [(-0.305, 0.050), (-0.226, 0.050), (-0.204, 0.068), (0.085, 0.068)]
    cut(rec, prism("_gL", band(gl, 0.0028), "X", 0.0365, 0.05))
    gl2 = [(-0.305, 0.108), (-0.045, 0.108), (-0.029, 0.097), (0.085, 0.097)]
    cut(rec, prism("_gL2", band(gl2, 0.0028), "X", 0.0365, 0.05))
    # RIGHT (-X): line under the ejection port
    gr = [(-0.305, 0.050), (0.006, 0.050), (0.020, 0.042), (0.085, 0.042)]
    cut(rec, prism("_gR", band(gr, 0.0028), "X", -0.05, -0.0365))
    finish(rec, 0.0035, 2)
    parts.append(rec)

    # bolt-release button (LEFT, +X)
    btn = cyl("WARDEN_BoltRelease", 0.0055, 0.006, (0.0395, 0.040, 0.0825), "X", 12, GM)
    finish(btn, 0.0012, 1)
    parts.append(btn)

    # ------------------------------------------------------------------ chassis (lower bed + magwell + chin)
    cha = prism("WARDEN_Chassis", [(0.080, 0.025), (-0.300, 0.025), (-0.300, 0.034), (-0.340, 0.034),
                                   (-0.296, -0.040), (-0.290, -0.058), (-0.282, -0.068), (-0.112, -0.068),
                                   (-0.104, -0.060), (-0.104, -0.010), (-0.030, 0.000), (0.040, 0.000),
                                   (0.080, -0.010)], "X", -0.035, 0.035, G)
    # magwell opening + flared entrance
    cut(cha, box("_mw", (0.054, 0.1575, 0.090), (0, -0.19575, -0.041)))
    fl = hull("_mwfl", [(sx * 0.031, y, -0.0705) for sx in (1, -1) for y in (-0.2785, -0.1130)] +
              [(sx * 0.027, y, -0.0625) for sx in (1, -1) for y in (-0.2745, -0.1170)])
    cut(cha, fl)
    # trigger slot
    cut(cha, box("_tslot", (0.011, 0.030, 0.030), (0, -0.057, -0.004)))
    # rear stock-adapter lug: the interface every stock clamps over (sits inside the stocks' hinge block)
    lug = prism("_lug", [(0.076, 0.038), (0.090, 0.038), (0.094, 0.034), (0.094, -0.004), (0.090, -0.008),
                         (0.076, -0.008)], "X", -0.019, 0.019)
    cut(lug, cyl("_lugh", 0.0045, 0.05, (0, 0.086, 0.015), "X", 12))
    union(cha, lug)
    # side lightening pockets on the magwell block
    for sx in (1, -1):
        cut(cha, prism("_pk", [(-0.262, -0.012), (-0.140, -0.012), (-0.140, -0.052), (-0.250, -0.052),
                               (-0.262, -0.040)], "X", sx * 0.033, sx * 0.050))
    finish(cha, 0.003, 2)
    parts.append(cha)

    # ------------------------------------------------------------------ handguard (free-float, slotted shell)
    hsec = [(-0.024, 0.030), (0.024, 0.030), (0.036, 0.042), (0.036, 0.116), (0.024, 0.128), (-0.024, 0.128),
            (-0.036, 0.116), (-0.036, 0.042)]
    hg = prism("WARDEN_Handguard", hsec, "Y", -0.700, -0.300, G)
    # front profile: vertical upper front face, chamfered lower front
    k = (0.692 - 0.656) / (0.068 - 0.030)
    hside = prism("_hside", [(-0.290, 0.010), (-0.290, 0.150), (-0.690, 0.150), (-0.690, 0.068),
                             (-0.690 + k * (0.068 - 0.010), 0.010)], "X", -0.05, 0.05)
    intersect(hg, hside)
    # inner cavity (wall 5 mm), open at the rear where the receiver closes it
    isec = [(-0.021, 0.035), (0.021, 0.035), (0.031, 0.045), (0.031, 0.113), (0.021, 0.123), (-0.021, 0.123),
            (-0.031, 0.113), (-0.031, 0.045)]
    cav = prism("_cav", isec, "Y", -0.681, -0.296)
    cav_side = prism("_cavs", [(-0.280, 0.020), (-0.280, 0.140), (-0.681, 0.140), (-0.681, 0.075),
                               (-0.681 + k * (0.075 - 0.020), 0.020)], "X", -0.05, 0.05)
    intersect(cav, cav_side)
    cut(hg, cav)
    # barrel exit hole in the front cap
    cut(hg, cyl("_bh", 0.0265, 0.05, (0, -0.690, BZ), "Y", 24))
    # side slots: 2 rows x 4, rounded
    for yc in (-0.372, -0.437, -0.502, -0.567):
        cut(hg, prism("_s", stadium(yc, 0.1035, 0.050, 0.0145, 3), "X", -0.06, 0.06))
        cut(hg, prism("_s", stadium(yc, 0.0640, 0.050, 0.0145, 3), "X", -0.06, 0.06))
    # bottom slots
    for yc in (-0.405, -0.480):
        cut(hg, prism("_sb", stadium(0.0, yc, 0.022, 0.055, 3), "Z", 0.020, 0.040))
    # top vent slots either side of the rail
    for yc in (-0.405, -0.470, -0.535):
        for sx in (1, -1):
            cut(hg, prism("_st", stadium(sx * 0.0175, yc, 0.007, 0.040, 2), "Z", 0.118, 0.140))
    finish(hg, 0.0025, 1)
    parts.append(hg)

    # handguard clamp screws at the receiver joint (hex heads, both sides)
    for sx in (1, -1):
        for zc in (0.052, 0.104):
            s = cyl("_scr", 0.0042, 0.004, (sx * 0.0365, -0.316, zc), "X", 6, GM)
            finish(s, 0.0008, 1)
            parts.append(s)

    # ------------------------------------------------------------------ rails
    rt = rail("WARDEN_RailTop", 0.752, G)
    place(rt, 0, (0, (0.062 - 0.690) / 2, 0.128))
    parts.append(rt)
    rb = rail("WARDEN_RailBottom", 0.110, G)
    place(rb, 180, (0, -0.595, 0.030))
    parts.append(rb)
    for sx, nm in ((-1, "WARDEN_RailSide_R"), (1, "WARDEN_RailSide_L")):
        rs = rail(nm, 0.060, G)
        place(rs, 90 * sx, (sx * 0.036, -0.645, 0.079))
        parts.append(rs)

    # ------------------------------------------------------------------ barrel (fluted, step-down) + brake
    bar = lathe_y("WARDEN_Barrel", [(0, -0.240), (0.023, -0.240), (0.023, -0.600), (0.021, -0.680),
                                    (0.021, -0.940), (0.016, -0.942), (0.016, -0.965), (0.009, -0.965),
                                    (0.009, -0.955), (0, -0.955)], steps=24, mat=GM)
    for i in range(6):
        a = math.radians(30 + 60 * i)
        c = prism("_fl", stadium(0.0, -0.8125, 0.0078, 0.225, 4), "Z", 0.0, 0.012)  # local: tangential x, y
        # local x -> tangent t, local y -> Y, local z -> radial r (right-handed: t x Y = r);
        # radial direction r=(cos a, sin a) in the XZ plane; cutter spans radius 0.018..0.030
        rmat = Matrix(((math.sin(a), 0, math.cos(a), 0),
                       (0, 1, 0, 0),
                       (-math.cos(a), 0, math.sin(a), 0),
                       (0, 0, 0, 1)))
        c.matrix_basis = Matrix.Translation(Vector((0.018 * math.cos(a), 0, BZ + 0.018 * math.sin(a)))) @ rmat
        cut(bar, c)
    smooth(bar, 40)
    parts.append(bar)

    # muzzle brake: big blocky dual-chamber, see-through ports
    bs = prism("WARDEN_Brake", [(-0.950, BZ - 0.025), (-0.950, BZ + 0.025), (-0.956, BZ + 0.031),
                                (-1.090, BZ + 0.031), (-1.100, BZ + 0.021), (-1.100, BZ - 0.021),
                                (-1.090, BZ - 0.031), (-0.956, BZ - 0.031)], "X", -0.035, 0.035, GM)
    bt = prism("_btop", [(-0.035, -0.950), (0.035, -0.950), (0.035, -1.090), (0.025, -1.100), (-0.025, -1.100),
                         (-0.035, -1.090)], "Z", BZ - 0.05, BZ + 0.05)
    intersect(bs, bt)
    # long-edge chamfers (front section octagon)
    bsec = prism("_bsec", [(-0.029, BZ - 0.031), (0.029, BZ - 0.031), (0.035, BZ - 0.025), (0.035, BZ + 0.025),
                           (0.029, BZ + 0.031), (-0.029, BZ + 0.031), (-0.035, BZ + 0.025), (-0.035, BZ - 0.025)],
                 "Y", -1.11, -0.94)
    intersect(bs, bsec)
    cut(bs, prism("_pA", rounded_rect(-1.0035, BZ, 0.037, 0.044, 0.005, 2), "X", -0.06, 0.06))
    cut(bs, prism("_pB", rounded_rect(-1.0545, BZ, 0.039, 0.044, 0.005, 2), "X", -0.06, 0.06))
    cut(bs, prism("_pC", rounded_rect(-0.9685, BZ, 0.013, 0.026, 0.004, 2), "X", -0.06, 0.06))
    # top compensator vents (into the chambers)
    for yc in (-1.0035, -1.0545):
        for sx in (1, -1):
            cut(bs, prism("_pv", stadium(sx * 0.0125, yc, 0.008, 0.026, 2), "Z", BZ, BZ + 0.05))
    cut(bs, cyl("_bore", 0.0105, 0.2, (0, -1.02, BZ), "Y", 20))
    finish(bs, 0.0022, 1)
    parts.append(bs)
    collar = lathe_y("WARDEN_BrakeCollar", [(0, -0.937), (0.021, -0.937), (0.0245, -0.940), (0.0245, -0.949),
                                            (0.022, -0.952), (0, -0.952)], steps=8, mat=GM, angle=30)
    finish(collar, 0.0008, 1)
    parts.append(collar)

    # ------------------------------------------------------------------ pistol grip (sand) + stipple panels
    gp = [(-0.026, 0.004), (0.030, 0.004), (0.042, -0.018), (0.064, -0.110), (0.062, -0.124), (0.052, -0.132),
          (0.020, -0.132), (0.010, -0.124), (-0.004, -0.072), (-0.010, -0.054), (-0.020, -0.036), (-0.026, -0.012)]
    grip = prism("WARDEN_Grip", gp, "X", -0.018, 0.018, S)
    # gentle palm-swell: narrow the front strap with an intersect section (top view)
    finish(grip, 0.0065, 3)
    parts.append(grip)
    pad_pts = [(0.006, -0.026), (0.030, -0.026), (0.050, -0.104), (0.046, -0.114), (0.024, -0.114),
               (0.014, -0.100), (0.002, -0.056)]
    for sx in (1, -1):
        pad = prism("_gpad", pad_pts, "X", sx * 0.0165, sx * 0.0195, SS)
        finish(pad, 0.0012, 1)
        parts.append(pad)

    # ------------------------------------------------------------------ trigger guard + trigger
    tg = prism("WARDEN_TriggerGuard", [(-0.106, -0.004), (-0.106, -0.062), (-0.094, -0.072), (-0.026, -0.072),
                                       (-0.004, -0.064), (-0.010, -0.030), (-0.014, -0.004)], "X", -0.010, 0.010, G)
    cut(tg, prism("_tgh", [(-0.092, 0.010), (-0.092, -0.056), (-0.086, -0.062), (-0.030, -0.062),
                           (-0.022, -0.054), (-0.024, 0.010)], "X", -0.05, 0.05))
    finish(tg, 0.0025, 2)
    parts.append(tg)

    # mag release paddle (ahead of the trigger guard, under the magwell rear)
    mr = prism("WARDEN_MagRelease", [(-0.116, -0.064), (-0.107, -0.064), (-0.104, -0.084), (-0.112, -0.086)],
               "X", -0.011, 0.011, GM)
    finish(mr, 0.0012, 1)
    parts.append(mr)

    trig = prism("WARDEN_Trigger", [(-0.058, 0.004), (-0.049, 0.004), (-0.051, -0.030), (-0.059, -0.048),
                                    (-0.066, -0.046), (-0.060, -0.028)], "X", -0.004, 0.004, GM)
    finish(trig, 0.0012, 1)

    # ------------------------------------------------------------------ bolt (separate, origin = bolt-axis rear)
    bolt = lathe_y("WARDEN_Bolt", [(0, 0.112), (0.0170, 0.112), (0.0205, 0.1105),
                                   (0.024, 0.1070), (0.024, 0.0855), (0.0225, 0.0820), (0.0185, 0.0820),
                                   (0.0185, -0.171), (0.0160, -0.175), (0, -0.175)], steps=24, mat=GM, angle=35)
    # shroud ring groove + bolt-body flutes visible in the port (facing -X / up)
    for ang in (150, 180, 210):   # angle around the bore in the XZ plane, 180 = straight toward -X
        a = math.radians(ang)
        c = box("_bfl", (0.0042, 0.105, 0.006), (0, 0, 0))
        # rotation about Y by (90 - a) maps local Z onto the radial direction (cos a, 0, sin a)
        c.matrix_basis = (Matrix.Translation(Vector((0.0185 * math.cos(a), -0.105, BZ + 0.0185 * math.sin(a)))) @
                          Matrix.Rotation(math.radians(90) - a, 4, "Y"))
        bake(c)
        cut(bolt, c)
    gpro = [(0.030, 0.094), (0.0225, 0.094), (0.0225, 0.0975), (0.030, 0.0975)]
    cut(bolt, lathe_y("_bg", gpro + [gpro[0]], steps=24))
    smooth(bolt, 35)
    # handle root block (sits in the notch)
    root = box("_broot", (0.030, 0.024, 0.022), (-0.020, 0.062, 0.0915), GM)
    finish(root, 0.003, 1)
    # oversized handle arm, angled down/out to the shooter's right
    p0, p1 = Vector((-0.030, 0.060, 0.092)), Vector((-0.082, 0.074, 0.048))
    d = p1 - p0
    arm = bc.box("_barm", (0.017, 0.015, d.length + 0.010), loc=(0, 0, 0), smooth=None, mat=GM)
    arm.matrix_basis = Matrix.Translation((p0 + p1) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bake(arm)
    finish(arm, 0.004, 1)
    # big knob, lathed along the arm direction
    dn = d.normalized()
    kc = p1 + dn * 0.016
    R = 0.024
    kprof = [(0, -0.030), (0.0065, -0.030), (0.0065, -0.020)]
    for deg in (-58, -40, -20, 0, 20, 38, 52):
        a = math.radians(deg)
        kprof.append((R * math.cos(a), R * math.sin(a)))
    kprof += [(0.0125, R * math.sin(math.radians(56))), (0.0080, 0.0205), (0, 0.0205)]
    knob = lathe_dir("_bknob", kprof, kc, dn, steps=16, mat=GM, angle=32)
    bolt = join([bolt, root, arm, knob], "WARDEN_Bolt")
    set_origin(bolt, (0, 0.112, BZ))

    # merge small static detail bits into their host objects to keep the hierarchy clean
    screws = [o for o in parts if o.name.startswith("_scr")]
    pads = [o for o in parts if o.name.startswith("_gpad")]
    others = [o for o in parts if not o.name.startswith(("_scr", "_gpad")) and o not in (hg, grip)]
    hg = join([hg] + screws, "WARDEN_Handguard")
    grip = join([grip] + pads, "WARDEN_Grip")
    statics = others + [hg, grip]
    set_origin(trig, (0, -0.054, 0.0))
    return statics, trig, bolt


# ================================================================================================ STOCKS
STOCK_MOUNT = Vector((0, 0.080, BZ))


def hinge_block(M, name, fold_knuckle=False):
    G, GM = M["G"], M["GM"]
    hb = prism(name, [(0.078, 0.045), (0.110, 0.045), (0.114, 0.041), (0.114, -0.011), (0.110, -0.015),
                      (0.078, -0.015)], "X", -0.026, 0.026, G)
    for sx in (1, -1):
        cut(hb, prism("_hbg", band([(0.074, 0.016), (0.118, 0.016)], 0.0025), "X", sx * 0.0238, sx * 0.03))
    finish(hb, 0.003, 2)
    bits = [hb]
    for sx in (1, -1):
        for (yy, zz) in ((0.087, 0.032), (0.087, 0.000)):
            s = cyl("_hs", 0.0038, 0.004, (sx * 0.0255, yy, zz), "X", 6, GM)
            finish(s, 0.0007, 1)
            bits.append(s)
    if fold_knuckle:
        kn = cyl("_kn", 0.0085, 0.066, (0.030, 0.111, 0.015), "Z", 16, GM)
        finish(kn, 0.0015, 1)
        bits.append(kn)
        for zz in (0.044, -0.014):
            cap = cyl("_kc", 0.0095, 0.004, (0.030, 0.111, zz), "Z", 16, GM)
            finish(cap, 0.001, 1)
            bits.append(cap)
    return bits


def build_stock_standard(M, col):
    G, GM, S, R = M["G"], M["GM"], M["S"], M["R"]
    bits = hinge_block(M, "_hinge")
    st = prism("_frame", [(0.090, 0.045), (0.122, 0.045), (0.140, 0.080), (0.150, 0.088), (0.282, 0.092),
                          (0.292, 0.100), (0.292, -0.118), (0.282, -0.126), (0.240, -0.126), (0.100, -0.032),
                          (0.090, -0.020)], "X", -0.023, 0.023, S)
    # triangular window with rounded corners
    tri = [(0.150, 0.054), (0.266, 0.070), (0.266, -0.094)]
    chamfered_window(st, round_poly(tri, 0.008, 3), 0.023, 0.0045)
    # lightening pockets on the rear post and the front web (both sides)
    for sx in (1, -1):
        cut(st, prism("_pp", rounded_rect(0.2805, -0.020, 0.010, 0.120, 0.004, 2), "X", sx * 0.0205, sx * 0.04))
        cut(st, prism("_pf", round_poly([(0.122, 0.028), (0.138, 0.040), (0.172, 0.000), (0.160, -0.034),
                                         (0.122, -0.010)], 0.004, 2), "X", sx * 0.0205, sx * 0.04))
    finish(st, 0.005, 2)
    bits.append(st)
    # riser-height knob (+X) and QD sling cups
    kb = knurl_cyl("_rk", 0.0085, 0.008, (0.027, 0.215, 0.078), "X", 16, 0.0008, GM)
    finish(kb, 0.001, 1)
    bits.append(kb)
    for sx in (1, -1):
        qd = cyl("_qd", 0.0065, 0.004, (sx * 0.0235, 0.2805, -0.090), "X", 12, GM)
        cut(qd, cyl("_qdh", 0.0035, 0.01, (sx * 0.0255, 0.2805, -0.090), "X", 12))
        finish(qd, 0.0008, 1)
        bits.append(qd)
    # recoil pad
    pad = prism("_pad", [(0.290, 0.104), (0.312, 0.100), (0.320, 0.082), (0.320, -0.110), (0.312, -0.126),
                         (0.290, -0.130)], "X", -0.025, 0.025, R)
    for zc in (-0.080, -0.040, 0.000, 0.040):
        cut(pad, box("_pg", (0.06, 0.006, 0.0035), (0, 0.3205, zc)))
    finish(pad, 0.004, 2)
    bits.append(pad)
    # monopod housing (fixed)
    mh = box("_mh", (0.034, 0.030, 0.024), (0, 0.205, -0.105), G)
    finish(mh, 0.003, 2)
    bits.append(mh)
    stock = join(bits, "WARDEN_StockStandard")
    set_origin(stock, STOCK_MOUNT)

    # cheek riser (child, slides on its posts) -- origin at the comb top centre between the posts
    cr = prism("WARDEN_StockStandard_CheekRiser", [(0.150, 0.100), (0.158, 0.128), (0.172, 0.136),
                                                   (0.276, 0.136), (0.284, 0.128), (0.284, 0.100)],
               "X", -0.020, 0.020, S)
    finish(cr, 0.005, 3)
    posts = []
    for yp in (0.180, 0.250):
        p = cyl("_post", 0.005, 0.034, (0, yp, 0.087), "Z", 12, GM)
        finish(p, 0.0008, 1)
        posts.append(p)
    cr = join([cr] + posts, "WARDEN_StockStandard_CheekRiser")
    set_origin(cr, (0, 0.215, 0.092))
    cr["slide_axis"] = "Z"
    cr["travel_m"] = [0.0, 0.030]

    # monopod (child, extends along -Z) -- origin at the housing bottom
    col_ = cyl("_mcol", 0.0095, 0.070, (0, 0.205, -0.150), "Z", 14, GM)
    smooth(col_, 40)
    knurl = knurl_cyl("_mknurl", 0.0135, 0.014, (0, 0.205, -0.140), "Z", 16, 0.0012, GM)
    finish(knurl, 0.0012, 1)
    spike = cyl("_mspike", 0.0105, 0.020, (0, 0.205, -0.189), "Z", 14, GM, r2=0.0012)
    spike.data.transform(Matrix.Translation(Vector((0, 0.205, -0.189))) @ Matrix.Rotation(math.pi, 4, "X") @
                         Matrix.Translation(-Vector((0, 0.205, -0.189))))
    smooth(spike, 40)
    mono = join([col_, knurl, spike], "WARDEN_StockStandard_Monopod")
    set_origin(mono, (0, 0.205, -0.117))
    mono["slide_axis"] = "Z"
    mono["travel_m"] = [-0.045, 0.0]

    for o in (stock, cr, mono):
        bc.link(o, col)
    bc.parent_keep(cr, stock)
    bc.parent_keep(mono, stock)
    stock["part"] = "stock_standard"
    stock["socket"] = "WARDEN_SOCKET_Stock"
    return stock


def round_poly(pts, r, n=4):
    """Round the corners of a convex/concave polygon by radius r (fillet arcs inside each corner)."""
    out = []
    N = len(pts)
    for i in range(N):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % N])
        a, b = (p0 - p1).normalized(), (p2 - p1).normalized()
        ang = math.acos(max(-1.0, min(1.0, a.dot(b))))
        t = r / math.tan(ang / 2)
        t = min(t, (p0 - p1).length * 0.45, (p2 - p1).length * 0.45)
        rr = t * math.tan(ang / 2)
        s, e = p1 + a * t, p1 + b * t
        bis = (a + b).normalized()
        c = p1 + bis * (rr / math.sin(ang / 2))
        a0 = math.atan2(s.y - c.y, s.x - c.x)
        a1 = math.atan2(e.y - c.y, e.x - c.x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n + 1):
            aa = a0 + da * k / n
            out.append((c.x + rr * math.cos(aa), c.y + rr * math.sin(aa)))
    return out


def offset_poly(pts, d):
    """Offset a convex polygon outward by d (vertex-normal offset with miter compensation)."""
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        e1, e2 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n1, n2 = Vector((e1.y, -e1.x)), Vector((e2.y, -e2.x))
        if n1.dot(p1 - Vector((cx, cy))) < 0:
            n1, n2 = -n1, -n2
        nb = (n1 + n2).normalized()
        out.append(tuple(p1 + nb * d / max(0.3, nb.dot(n1))))
    return out


def chamfered_window(obj, poly, half_w, depth):
    """Cut a through-window (side profile polygon, axis X) and a 45-degree chamfer `depth` deep on both faces."""
    cut(obj, prism("_win", poly, "X", -0.06, 0.06))
    big = offset_poly(poly, depth + 0.004)
    for sx in (1, -1):
        pts = ([(sx * (half_w - depth), y, z) for (y, z) in poly] +
               [(sx * (half_w + 0.004), y, z) for (y, z) in big])
        cut(obj, hull("_wch", pts))
    return obj


def build_stock_folding(M, col):
    G, GM, S, R = M["G"], M["GM"], M["S"], M["R"]
    fixed = join(hinge_block(M, "_hingeF", fold_knuckle=True), "WARDEN_StockFolding")
    set_origin(fixed, STOCK_MOUNT)
    # folding arm: lighter Z-frame skeleton (w 0.036), no riser, no monopod
    outer = [(0.116, 0.044), (0.128, 0.062), (0.276, 0.066), (0.288, 0.076), (0.288, -0.104), (0.278, -0.114),
             (0.246, -0.114), (0.128, -0.026), (0.116, -0.016)]
    fr = prism("_ffr", outer, "X", -0.018, 0.018, S)
    winA = round_poly([(0.134, 0.046), (0.236, 0.050), (0.134, -0.004)], 0.006)
    winB = round_poly([(0.272, 0.046), (0.272, -0.094), (0.160, -0.020)], 0.006)
    chamfered_window(fr, winA, 0.018, 0.0035)
    chamfered_window(fr, winB, 0.018, 0.0035)
    finish(fr, 0.0045, 2)
    pad = prism("_fpad", [(0.286, 0.084), (0.304, 0.080), (0.310, 0.066), (0.310, -0.104), (0.302, -0.118),
                          (0.286, -0.120)], "X", -0.022, 0.022, R)
    for zc in (-0.070, -0.030, 0.010, 0.050):
        cut(pad, box("_pg", (0.06, 0.006, 0.0035), (0, 0.3105, zc)))
    finish(pad, 0.004, 3)
    # hinge leaf (graphite) joining the arm to the knuckle on the LEFT (+X)
    leaf = prism("_leaf", [(0.104, 0.040), (0.132, 0.040), (0.132, -0.012), (0.104, -0.012)], "X", 0.016, 0.0345, G)
    finish(leaf, 0.002, 2)
    core = prism("_fcore", [(0.1155, 0.044), (0.132, 0.044), (0.132, -0.016), (0.1155, -0.016)], "X", -0.017,
                 0.017, G)
    finish(core, 0.002, 2)
    arm = join([fr, pad, leaf, core], "WARDEN_StockFolding_Arm")
    set_origin(arm, (0.030, 0.111, 0.015))
    arm["fold_axis"] = "Z"
    arm["fold_angle_deg"] = -180.0
    arm["note"] = "rotate about local Z by fold_angle_deg: stock swings out to +X and lies along the LEFT side"
    for o in (fixed, arm):
        bc.link(o, col)
    bc.parent_keep(arm, fixed)
    fixed["part"] = "stock_folding"
    fixed["socket"] = "WARDEN_SOCKET_Stock"
    return fixed


# ============================================================================================= MAGAZINES
MAG_MOUNT = Vector((0, -0.270, 0.0))


def cartridge(name, tip_y, z, steps, mat):
    """12.7 mm-class cartridge lying along Y, bullet tip toward -Y at tip_y, axis at height z (gun coords)."""
    prof = [(0, 0.0), (0.0022, 0.003), (0.0046, 0.012), (0.0062, 0.026), (0.0066, 0.039), (0.0076, 0.039),
            (0.0078, 0.056), (0.0099, 0.066), (0.0105, 0.128), (0.0090, 0.130), (0.0090, 0.1335),
            (0.0104, 0.1345), (0.0104, 0.138), (0, 0.138)]
    o = lathe_y(name, [(r, tip_y + s) for (r, s) in prof], x=0.0, z=z, steps=steps, mat=mat, angle=40)
    return o


def build_mag(M, col, cap, body_bottom):
    """mag_5 (cap 5, body bottom -0.150) or mag_8 (cap 8, body bottom -0.200). Single-stack 12.7 mm column
    seen through a vertical window slot on each side; top round at the feed lips. The upper 0.072 m (inside the
    magwell) is 0.052 wide; below the well the body steps out to 0.056 (seats against the magwell lip)."""
    G, GM, S = M["G"], M["GM"], M["S"]
    zb = body_bottom
    fr = 0.006 * (abs(zb) / 0.150)          # front face rakes forward toward the bottom
    body = prism("_mbody", [(-0.270, 0.000), (-0.120, 0.000), (-0.118, zb), (-0.270 - fr, zb)], "X", -0.035,
                 0.035, G)
    msec = prism("_msec", [(-0.026, 0.010), (0.026, 0.010), (0.026, -0.0725), (0.028, -0.0745), (0.028, zb - 0.01),
                           (-0.028, zb - 0.01), (-0.028, -0.0745), (-0.026, -0.0725)], "Y", -0.30, -0.10)
    intersect(body, msec)
    # internal channel for the cartridge column (narrow so the rounds sit right behind the window)
    cut(body, box("_mch", (0.025, 0.141, abs(zb) - 0.008 - 0.004), (0, -0.196, (-0.004 + zb + 0.008) / 2)))
    # feed-lip opening on top
    cut(body, prism("_mfl", stadium(0.0, -0.196, 0.0155, 0.128, 4), "Z", -0.006, 0.01))
    # window slots both sides (physical mag-check window)
    wz0, wz1 = -0.018, zb + 0.020
    cut(body, prism("_mw", stadium(-0.181, (wz0 + wz1) / 2, 0.023, wz0 - wz1, 4), "X", -0.04, 0.04))
    # rear catch notch
    cut(body, box("_mcn", (0.020, 0.008, 0.010), (0, -0.120, -0.030)))
    finish(body, 0.003, 1)
    # raised ribs flanking the window on the lower (wider) section
    ribs = []
    for sx in (1, -1):
        for yc in (-0.232, -0.132):
            h = abs(zb) - 0.084
            rb = box("_mrib", (0.006, 0.010, h), (sx * 0.0285, yc, -0.080 - h / 2), G)
            finish(rb, 0.0018, 1)
            ribs.append(rb)
    base = box("_mbase", (0.060, 0.172, 0.018), (0, -0.197 - fr / 2, zb - 0.009), S)
    cut(base, prism("_mbg", band([(-0.30, zb - 0.009), (-0.09, zb - 0.009)], 0.003), "X", 0.028, 0.04))
    cut(base, prism("_mbg2", band([(-0.30, zb - 0.009), (-0.09, zb - 0.009)], 0.003), "X", -0.04, -0.028))
    finish(base, 0.004, 2)
    follower_z = -0.011 - 0.021 * (cap - 1) - 0.0105 - 0.0075
    fol = box("_mfol", (0.023, 0.136, 0.012), (0, -0.197, follower_z), G)
    finish(fol, 0.0015, 1)
    mag = join([body] + ribs + [base, fol], f"WARDEN_Mag{cap}")
    set_origin(mag, MAG_MOUNT)
    bc.link(mag, col)
    mag["part"] = f"mag_{cap}"
    mag["capacity"] = cap
    mag["socket"] = "WARDEN_SOCKET_Mag"
    rounds = []
    for i in range(cap):
        nm = f"WARDEN_Mag{cap}_Round" if i == 0 else f"WARDEN_Mag{cap}_Round_{i + 1:02d}"
        r = cartridge(nm, -0.2655, -0.011 - 0.021 * i, 12 if i == 0 else 8, M["C"])
        set_origin(r, (0, -0.1965, -0.011 - 0.021 * i))
        r["round_index"] = i + 1
        bc.link(r, col)
        bc.parent_keep(r, mag)
        rounds.append(r)
    return mag


# ================================================================================================ SOCKETS
SOCKETS = {
    "Optic": (0, -0.080, RAIL_TOP_Z),
    "Stock": (0, 0.080, BZ),
    "Mag": (0, -0.270, 0.0),
    "Under": (0, -0.600, 0.0205),
    "Side_R": (-0.0455, -0.645, 0.079),   # shooter's RIGHT = -X (modular spec handedness)
    "Side_L": (0.0455, -0.645, 0.079),
    "Muzzle": (0, -1.100, BZ),
    "LeftHand": (0, -0.380, 0.030),
}


def build_all():
    bc.reset_scene()
    M = mats()
    c_base = bc.collection("WARDEN_Base")
    c_ss = bc.collection("WARDEN_Stock_Standard")
    c_sf = bc.collection("WARDEN_Stock_Folding")
    c_m5 = bc.collection("WARDEN_Mag_5")
    c_m8 = bc.collection("WARDEN_Mag_8")

    root = bpy.data.objects.new("WARDEN_Root", None)
    root.empty_display_type = "ARROWS"
    root.empty_display_size = 0.05
    c_base.objects.link(root)
    root["weapon"] = "VK-50 WARDEN"
    root["default_stock"] = "stock_standard"
    root["default_mag"] = "mag_5"
    root["default_optic"] = "optic_sniper"
    root["default_under"] = "bipod"

    log("building base")
    statics, trig, bolt = build_base(M, c_base)
    for o in statics + [trig, bolt]:
        bc.link(o, c_base)
        bc.parent_keep(o, root)
    trig["pivot_axis"] = "X"
    trig["pull_deg"] = 12.0
    bolt["note"] = "origin = bolt-axis rear; open = rotate about local Y ~ -60 deg (handle up), then slide +Y 0.13"
    bolt["lift_deg"] = 60.0
    bolt["travel_m"] = 0.130
    sockets = {}
    for nm, loc in SOCKETS.items():
        e = bpy.data.objects.new(f"WARDEN_SOCKET_{nm}", None)
        e.empty_display_type = "PLAIN_AXES"
        e.empty_display_size = 0.02
        e.location = loc
        c_base.objects.link(e)
        e.parent = root
        sockets[nm] = e

    log("building stocks")
    ss = build_stock_standard(M, c_ss)
    sf = build_stock_folding(M, c_sf)
    log("building mags")
    m5 = build_mag(M, c_m5, 5, -0.150)
    m8 = build_mag(M, c_m8, 8, -0.200)

    bc.uv_all()
    return dict(root=root, statics=statics, trig=trig, bolt=bolt, sockets=sockets, ss=ss, sf=sf, m5=m5, m8=m8,
                cols=dict(base=c_base, ss=c_ss, sf=c_sf, m5=c_m5, m8=c_m8))


def tree(o):
    out = [o]
    for c in o.children:
        out += tree(c)
    return out


def base_objs(B):
    return list(B["cols"]["base"].objects)


def tri_count(objs):
    return sum(tris(o) for o in objs if o.type == "MESH")


# ================================================================================================= EXPORT
def export_part(root_obj, path_noext):
    """Export a part whose root object's origin is its mount point: temporarily put it at world origin."""
    mw = root_obj.matrix_world.copy()
    root_obj.matrix_world = Matrix.Identity(4)
    bc.export_all(path_noext, objs=tree(root_obj), blend=False)
    root_obj.matrix_world = mw


def attach(part, socket):
    part.parent = socket
    part.matrix_parent_inverse = Matrix.Identity(4)
    part.matrix_basis = Matrix.Identity(4)


def detach(part):
    mw = part.matrix_world.copy()
    part.parent = None
    part.matrix_world = mw


def do_exports(B):
    s = B["sockets"]
    # parts sit on their sockets in the .blend (variants hidden)
    for p, sk in ((B["ss"], "Stock"), (B["sf"], "Stock"), (B["m5"], "Mag"), (B["m8"], "Mag")):
        p.matrix_world = Matrix.Translation(Vector(SOCKETS[sk]))
    bpy.context.view_layer.update()
    bc.export_all(os.path.join(OUT, "warden_base"), objs=base_objs(B), blend=False)
    for p, nm in ((B["ss"], "stock_standard"), (B["sf"], "stock_folding"), (B["m5"], "mag_5"), (B["m8"], "mag_8")):
        export_part(p, os.path.join(OUT, f"warden_{nm}"))
    # assembled default: parts parented to their sockets
    attach(B["ss"], s["Stock"])
    attach(B["m5"], s["Mag"])
    bpy.context.view_layer.update()
    objs = base_objs(B)
    bc.export_all(os.path.join(OUT, "warden_default"), objs=objs, fbx=False, blend=False)
    # keep the default assembled in the .blend; variants placed on the sockets but hidden
    for p in (B["sf"], B["m8"]):
        for o in tree(p):
            o.hide_render = False
    data = {f"WARDEN_SOCKET_{k}": {"location": [round(v, 5) for v in loc], "rotation_deg": [0, 0, 0]}
            for k, loc in SOCKETS.items()}
    with open(os.path.join(OUT, "sockets.json"), "w") as f:
        json.dump(data, f, indent=2)
    vl = bpy.context.view_layer.layer_collection
    for cname in ("WARDEN_Stock_Folding", "WARDEN_Mag_8"):
        vl.children[cname].exclude = True
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "warden.blend"), compress=True)
    vl.children["WARDEN_Stock_Folding"].exclude = False
    vl.children["WARDEN_Mag_8"].exclude = False
    log("saved blend + exports")


def report(B):
    base = [o for o in base_objs(B) if o.type == "MESH"]
    ss, sf, m5, m8 = (tree(B[k]) for k in ("ss", "sf", "m5", "m8"))
    rows = {
        "base": tri_count(base), "stock_standard": tri_count(ss), "stock_folding": tri_count(sf),
        "mag_5": tri_count(m5), "mag_8": tri_count(m8),
    }
    rows["default (base+stock_standard+mag_5)"] = rows["base"] + rows["stock_standard"] + rows["mag_5"]
    for o in sorted(base + ss + m5, key=lambda o: -tris(o) if o.type == "MESH" else 0):
        if o.type == "MESH":
            print(f"    {tris(o):>6}  {o.name}")
    for k, v in rows.items():
        print(f"  TRIS {k:<40} {v}")
    with open(os.path.join(OUT, "_wip", "tris.json"), "w") as f:
        json.dump(rows, f, indent=2)
    return rows


# ================================================================================================= RENDER
def render_world():
    bc.setup_studio(bg=(0.24, 0.25, 0.27))
    w = bpy.context.scene.world
    nt = w.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    if not any(n.type == "LIGHT_PATH" for n in nt.nodes):
        bg2 = nt.nodes.new("ShaderNodeBackground")
        bg2.inputs[0].default_value = (1.9, 1.92, 1.96, 1)
        bg2.inputs[1].default_value = 1.0
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(bg.outputs[0], mix.inputs[1])
        nt.links.new(bg2.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs[0])
    vs = bpy.context.scene.view_settings
    vs.exposure = -0.35
    try:
        vs.look = "AgX - Punchy"
    except TypeError:
        pass


def show_only(objs):
    keep = set(o.name for o in objs)
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.hide_render = o.name not in keep


def rv(prefix, objs, views, res=(1600, 800), focus=None, margin=1.10, samples=None, lens=85, rename=None,
       ortho=False):
    show_only(objs)
    paths = bc.render_views(REN, prefix, objs=[o for o in objs if o.type == "MESH"], views=views, res=res,
                            engine="CYCLES", samples=samples or ARGS.samples, lens=lens, margin=margin, focus=focus,
                            ortho=ortho)
    if rename:
        out = []
        for p, nm in zip(paths, rename):
            q = os.path.join(REN, f"{prefix}_{nm}.png")
            if os.path.normcase(os.path.abspath(p)) != os.path.normcase(os.path.abspath(q)):
                os.replace(p, q)
            out.append(q)
        return out
    return paths


TOP = (0.001, 0.0, 1.0)  # camera above; screen-up = -X (shooter's right), muzzle to the left


def exact_side(objs, name, side="+X"):
    """1 px = 1 mm orthographic side render matching art/concepts/warden/profile_sketch.png (top panel)."""
    show_only(objs)
    sc = bpy.context.scene
    bc.setup_cycles_gpu(sc, ARGS.samples)
    cam_data = bpy.data.cameras.get("_PreviewCam") or bpy.data.cameras.new("_PreviewCam")
    cam = bpy.data.objects.get("_PreviewCam") or bpy.data.objects.new("_PreviewCam", cam_data)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 1.6
    sc.render.resolution_x, sc.render.resolution_y = 1600, 640
    sc.render.resolution_percentage = 100
    if side == "+X":
        cam.location = (2.0, -0.39, 0.015)
        cam.rotation_euler = (math.radians(90), 0, math.radians(90))
    sc.render.filepath = os.path.join(REN, name)
    sc.render.film_transparent = True
    sc.render.image_settings.color_mode = "RGBA"
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError:
        sc.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    cam_data.type = "PERSP"
    sc.render.film_transparent = False
    sc.render.image_settings.color_mode = "RGB"
    return sc.render.filepath


def socket_debug(B, objs):
    """Temporary coloured markers on every socket (not exported) -> renders/warden_sockets_*.png."""
    cols = {"Optic": (0.1, 0.9, 1.0), "Stock": (1.0, 0.8, 0.1), "Mag": (1.0, 0.4, 0.1), "Under": (0.2, 1.0, 0.2),
            "Side_R": (1.0, 0.1, 0.1), "Side_L": (0.2, 0.3, 1.0), "Muzzle": (1.0, 1.0, 1.0),
            "LeftHand": (1.0, 0.2, 1.0)}
    marks = []
    for nm, c in cols.items():
        m = bc.material("_dbg_" + nm, c, rough=0.4, emission=c, emission_strength=4.0)
        o = bc.sphere("_dbg_" + nm, 0.007, loc=B["sockets"][nm].matrix_world.translation, segments=16, rings=8, mat=m)
        marks.append(o)
    paths = rv("warden_sockets", objs + marks, ("left", "right", TOP, (0.7, -1.0, -0.4)), res=(1600, 800),
               margin=1.0, samples=24, rename=["left", "right", "top", "below"])
    for o in marks:
        bpy.data.objects.remove(o, do_unlink=True)
    return paths


def do_renders(B, mode):
    render_world()
    s = B["sockets"]
    for p, sk in ((B["ss"], "Stock"), (B["sf"], "Stock"), (B["m5"], "Mag"), (B["m8"], "Mag")):
        if p.parent is None:
            p.matrix_world = Matrix.Translation(Vector(SOCKETS[sk]))
    bpy.context.view_layer.update()
    base = base_objs(B)
    default = base + tree(B["ss"]) + tree(B["m5"])
    out = []
    if mode in ("quick", "full", "compare"):
        out += rv("warden", default, ("right", "left"), samples=None if mode != "quick" else 24)
        out += rv("warden", default, ("three_quarter",), samples=None if mode != "quick" else 24, margin=0.92)
        out += [exact_side(default, "warden_exact_side.png")]
    if mode == "full":
        out += rv("warden", default, (TOP,), res=(1600, 640), rename=["top"])
        out += rv("warden", default, ("front", "back"), res=(900, 900), focus=((0, -0.39, -0.02), 0.22),
                  ortho=True, margin=1.0)
        out += rv("warden", default, ("three_quarter_back", "low"), margin=0.92)
        # close-ups
        out += rv("warden_cu", default, ((0.9, -0.8, 0.45),), res=(1200, 900), focus=((0, -1.02, BZ), 0.11),
                  rename=["brake"])
        out += rv("warden_cu", default, ((-1.0, 0.55, 0.45),), res=(1200, 900), focus=((-0.04, 0.03, 0.06), 0.13),
                  rename=["bolt"])
        out += rv("warden_cu", default, ((-1.0, -0.25, 0.25),), res=(1400, 900), focus=((0, -0.12, 0.05), 0.20),
                  rename=["receiver_right"])
        out += rv("warden_cu", default, ((1.0, -0.35, 0.3),), res=(1400, 900), focus=((0, -0.12, 0.05), 0.20),
                  rename=["receiver_left"])
        out += rv("warden_cu", default, ((0.8, -0.6, -0.35),), res=(1400, 900), focus=((0, -0.50, 0.06), 0.24),
                  rename=["handguard_under"])
        # variants: stocks + mags alone
        for key, nm in (("ss", "stock_standard"), ("sf", "stock_folding")):
            objs = tree(B[key])
            out += rv(f"warden_{nm}", objs, ("three_quarter", "right", "left", "three_quarter_back"),
                      res=(1200, 900), margin=1.25)
        for key, nm in (("m5", "mag_5"), ("m8", "mag_8")):
            objs = tree(B[key])
            out += rv(f"warden_{nm}", objs, ("three_quarter", "right", (0.6, -0.5, 1.0)), res=(900, 1000),
                      margin=1.25, rename=["three_quarter", "right", "top_feedlips"])
        # base gun alone (no stock / mag): shows the stock-adapter lug and the empty magwell
        out += rv("warden_base_only", base, ("left", "three_quarter_back", (0.4, 0.9, -0.5)), res=(1600, 900),
                  margin=0.95, rename=["left", "three_quarter_back", "rear_low"])
        out += socket_debug(B, default)
        # the alternative loadout on the gun: folding stock + mag_8
        alt = base + tree(B["sf"]) + tree(B["m8"])
        out += rv("warden_alt", alt, ("right", "three_quarter"))
        # folded pose preview
        arm = B["sf"].children[0]
        arm.rotation_euler[2] = math.radians(arm["fold_angle_deg"])
        bpy.context.view_layer.update()
        out += rv("warden_alt_folded", alt, ("three_quarter", TOP), rename=["three_quarter", "top"])
        arm.rotation_euler[2] = 0
        bpy.context.view_layer.update()
    log("rendered", len(out))
    return out


# =================================================================================================== MAIN
B = build_all()
log("built")
rows = report(B)
if not ARGS.no_export:
    do_exports(B)
if ARGS.render != "none":
    do_renders(B, ARGS.render)
log("done")
