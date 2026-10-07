"""build_optics.py - shared OPTICS attachment set (prefix ATT) for the val etf prototype.

Re-runnable from scratch (headless Blender 5.2):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/weapons/attachments/optics/build_optics.py" -- [--render none|quick|full]
      [--only optic_holo,optic_3x] [--res 800] [--samples 48] [--no-export]

Every optic is modeled in MOUNT SPACE (art/WEAPON_MODULAR_SPEC.md):
  origin = centre of the clamp contact on the rail TOP surface, forward = -Y, up = +Z,
  shooter's RIGHT = -X, LEFT = +X.
Each optic lives in its own collection `ATT_<optic>` with a root empty `ATT_<optic>` at the origin, its meshes
(`_Body` opaque multi-material, `_Glass` lenses, `_Glow` the single emissive) and the empty
`ATT_<optic>_SOCKET_ADS` on the sight line at the rear of the reticle / eyepiece.

Outputs (all in this folder): ATT_<optic>.glb/.fbx per optic, optics.blend, catalog.json, fitcheck.json,
renders/*.png (contact sheets + concept comparisons are made by make_sheets.py with the system python).
"""
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, r"F:/git/val etf/tools")
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import blender_common as bc  # noqa: E402

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
REN = OUT + "/renders"
TEX_PAINT = os.path.join(bc.TEXTURES, "worn_paint.png")

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        return ARGS[i + 1] if i + 1 < len(ARGS) else True
    return default


RENDER = _arg("--render", "full")          # none | quick | full
ONLY = _arg("--only", None)
RES = int(_arg("--res", 800))
SAMPLES = int(_arg("--samples", 48))
DO_EXPORT = "--no-export" not in ARGS

# ------------------------------------------------------------------------------------------ rail standard
RAIL_W = 0.021          # rail top (overall) width
RAIL_H = 0.0095         # rail height above its base
RAIL_PITCH = 0.010      # cross slot pitch
RAIL_SLOT = 0.005       # slot length along Y
RAIL_SLOT_D = 0.003     # slot depth from the top
JAW_IN = 0.0106         # clamp jaw inner face |x| (0.1 mm clearance to the 0.021 flank)
JAW_BOT = -0.0062       # jaws stop 3.3 mm above the rail base (clear of the dovetail undercut)
CONTACT = 0.0001        # clamp underside sits 0.1 mm above the rail top (no coplanar faces)

OPTIC_IDS = ["optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"]


# =========================================================================================== geometry helpers
def _new_obj(name, bm, mat=None, col=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    if mat is not None:
        if isinstance(mat, (list, tuple)):
            for m in mat:
                ob.data.materials.append(m)
        else:
            ob.data.materials.append(mat)
    return ob


def _axis_map(axis):
    """(u, v, w) -> (x, y, z): (u, v) is the 2D profile, w runs along `axis`."""
    if axis == "X":
        return lambda u, v, w: (w, u, v)      # profile in (y, z)
    if axis == "Y":
        return lambda u, v, w: (u, w, v)      # profile in (x, z)
    return lambda u, v, w: (u, v, w)          # profile in (x, y)


def prism(name, pts, axis, w0, w1, mat=None, col=None):
    """Extrude a closed 2D polygon between w0..w1 along axis (X: pts=(y,z), Y: pts=(x,z), Z: pts=(x,y))."""
    P = _axis_map(axis)
    bm = bmesh.new()
    a = [bm.verts.new(P(u, v, w0)) for u, v in pts]
    b = [bm.verts.new(P(u, v, w1)) for u, v in pts]
    n = len(pts)
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _new_obj(name, bm, mat, col)


def box(name, x0, x1, y0, y1, z0, z1, mat=None, col=None):
    return prism(name, [(x0, z0), (x1, z0), (x1, z1), (x0, z1)], "Y", y0, y1, mat, col)


def rrect(cx, cy, hw, hh, r, seg=3, corners=(1, 1, 1, 1)):
    """Rounded / chamfered rectangle (CCW). corners = radius multipliers for (+u+v, -u+v, -u-v, +u-v)."""
    out = []
    spec = [((cx + hw, cy + hh), (-1, -1), 0), ((cx - hw, cy + hh), (1, -1), 90),
            ((cx - hw, cy - hh), (1, 1), 180), ((cx + hw, cy - hh), (-1, 1), 270)]
    for k, ((px, py), (sx, sy), a0) in enumerate(spec):
        rr = r * corners[k]
        if rr <= 1e-9:
            out.append((px, py))
            continue
        ccx, ccy = px + sx * rr, py + sy * rr
        for i in range(seg + 1):
            a = math.radians(a0 + 90.0 * i / seg)
            out.append((ccx + rr * math.cos(a), ccy + rr * math.sin(a)))
    return out


def circle(cx, cy, r, n=24, phase=0.0):
    return [(cx + r * math.cos(phase + 2 * math.pi * i / n), cy + r * math.sin(phase + 2 * math.pi * i / n))
            for i in range(n)]


def lathe(name, prof, axis="Y", c=(0.0, 0.0, 0.0), steps=32, mats=None, seg_mat=None, knurl=0.0,
          closed=True, phase=0.0, col=None):
    """Revolve a profile [(r, h[, tag])] around an axis through c. h is the coordinate along the axis.
    Entries with r == 0 become a single pole vertex. Tag 'k' = knurled ring: every other vertex pulled in by
    `knurl`. seg_mat = material index per profile segment (closing segment included when closed)."""
    bm = bmesh.new()
    cx, cy, cz = c

    def pos(r, h, a):
        ca, sa = math.cos(a), math.sin(a)
        if axis == "Y":
            return (cx + r * ca, h, cz + r * sa)
        if axis == "Z":
            return (cx + r * ca, cy + r * sa, h)
        return (h, cy + r * ca, cz + r * sa)

    rings = []
    for e in prof:
        r, h = e[0], e[1]
        tag = e[2] if len(e) > 2 else ""
        if r <= 1e-9:
            v = bm.verts.new(pos(0.0, h, 0.0))
            rings.append([v] * steps)
            continue
        ring = []
        for i in range(steps):
            a = phase + 2 * math.pi * i / steps
            rr = r - knurl if ("k" in tag and i % 2 == 1) else r
            ring.append(bm.verts.new(pos(rr, h, a)))
        rings.append(ring)
    nseg = len(prof) if closed else len(prof) - 1
    for j in range(nseg):
        A, B = rings[j], rings[(j + 1) % len(prof)]
        for i in range(steps):
            i2 = (i + 1) % steps
            vs = []
            for v in (A[i], A[i2], B[i2], B[i]):
                if v not in vs:
                    vs.append(v)
            if len(vs) < 3:
                continue
            try:
                f = bm.faces.new(vs)
            except ValueError:
                continue
            if seg_mat:
                f.material_index = seg_mat[j] if j < len(seg_mat) else 0
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _new_obj(name, bm, mats, col)


def disc(name, center, r, normal_axis="Y", n=12, t=0.0002, mat=None, col=None):
    """Thin disc (cylinder) used for reticle dots."""
    h0 = center[{"X": 0, "Y": 1, "Z": 2}[normal_axis]]
    return lathe(name, [(0.0, h0 - t / 2), (r, h0 - t / 2), (r, h0 + t / 2), (0.0, h0 + t / 2)],
                 axis=normal_axis, c=center, steps=n, mats=mat, col=col)


def ring_flat(name, center, r0, r1, normal_axis="Y", n=32, t=0.0002, mat=None, col=None):
    h0 = center[{"X": 0, "Y": 1, "Z": 2}[normal_axis]]
    return lathe(name, [(r0, h0 - t / 2), (r1, h0 - t / 2), (r1, h0 + t / 2), (r0, h0 + t / 2)],
                 axis=normal_axis, c=center, steps=n, mats=mat, col=col)


def rotate_x(obj, deg, pivot):
    """Rotate mesh data about an X-parallel axis through pivot (y, z)."""
    py, pz = pivot
    M = Matrix.Translation((0, py, pz)) @ Matrix.Rotation(math.radians(deg), 4, "X") @ \
        Matrix.Translation((0, -py, -pz))
    obj.data.transform(M)
    return obj


def translate(obj, v):
    obj.data.transform(Matrix.Translation(v))
    return obj


def apply_xform(obj):
    obj.data.transform(obj.matrix_basis)
    obj.matrix_basis = Matrix.Identity(4)
    return obj


def cut(obj, cutter, op="DIFFERENCE", transfer_mat=None):
    """EXACT boolean, applied. transfer_mat: the new faces made by the cutter get this material."""
    if transfer_mat is not None:
        cutter.data.materials.clear()
        cutter.data.materials.append(transfer_mat)
    m = obj.modifiers.new("Bool", "BOOLEAN")
    m.object = cutter
    m.operation = op
    m.solver = "EXACT"
    if transfer_mat is not None:
        m.material_mode = "TRANSFER"
    bc.apply_modifiers(obj, only=[m.name])
    bpy.data.objects.remove(cutter, do_unlink=True)
    return obj


def merge(objs, name):
    """Join helper meshes (cutters) without modifiers into one object."""
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    return o


def bevel(obj, width, seg=2, angle=30, harden=True, exclude=None, smooth_angle=30):
    """Smooth shading with angle-based sharp edges + an angle-limited bevel (hardened normals).
    exclude(midpoint) -> True keeps that sharp edge un-bevelled (used for the clamp's rail channel)."""
    bc.shade_smooth(obj, smooth_angle)
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = seg
    m.use_clamp_overlap = True
    if exclude is None:
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(angle)
    else:
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        lay = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
        lim = math.radians(angle)
        for e in bm.edges:
            w = 0.0
            if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim:
                mid = (e.verts[0].co + e.verts[1].co) / 2
                w = 0.0 if exclude(mid) else 1.0
            e[lay] = w
        bm.to_mesh(obj.data)
        bm.free()
        m.limit_method = "WEIGHT"
    m.harden_normals = harden
    return m


def smooth(obj, angle=30):
    bc.shade_smooth(obj, angle)
    return obj


def empty(name, loc, col, parent=None, size=0.01, kind="PLAIN_AXES"):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = kind
    e.empty_display_size = size
    e.location = loc
    col.objects.link(e)
    if parent is not None:
        e.parent = parent
    return e


# =========================================================================================== materials
def make_materials():
    M = {}
    M["graphite"] = bc.material("M_ATT_Graphite", (0.030, 0.033, 0.040), rough=0.50, metal=0.25,
                                tex=TEX_PAINT, tex_scale=0.8, tex_mix=0.30)
    M["bone"] = bc.material("M_ATT_Bone", (0.55, 0.52, 0.46), rough=0.60, metal=0.0,
                            tex=TEX_PAINT, tex_scale=0.8, tex_mix=0.25)
    M["gunmetal"] = bc.material("M_ATT_Gunmetal", (0.11, 0.115, 0.12), rough=0.35, metal=0.85)
    M["rubber"] = bc.material("M_ATT_Rubber", (0.035, 0.037, 0.045), rough=0.85, metal=0.0)
    M["dark"] = bc.material("M_ATT_Dark", (0.016, 0.017, 0.020), rough=0.75, metal=0.0)
    M["lens"] = bc.material("M_ATT_Lens", (0.006, 0.018, 0.055), rough=0.04, metal=0.0, coat=1.0)
    M["reflex"] = bc.material("M_ATT_ReflexGlass", (0.03, 0.07, 0.09), rough=0.03, metal=0.0, coat=1.0,
                              alpha=0.30)
    M["ice"] = bc.material("M_ATT_IceGlow", (0.45, 0.85, 1.0), rough=0.30, metal=0.0,
                           emission=(0.45, 0.85, 1.0), emission_strength=1.6)
    M["icepaint"] = bc.material("M_ATT_IcePaint", (0.45, 0.85, 1.0), rough=0.40, metal=0.0)
    M["germanium"] = bc.material("M_ATT_Germanium", (0.045, 0.024, 0.006), rough=0.06, metal=0.55, coat=1.0)
    M["amber"] = bc.material("M_ATT_AmberGlow", (1.0, 0.50, 0.08), rough=0.30, metal=0.0,
                             emission=(1.0, 0.42, 0.05), emission_strength=3.0)
    M["testrail"] = bc.material("_M_TestRail", (0.16, 0.17, 0.19), rough=0.45, metal=0.5)
    M["testbase"] = bc.material("_M_TestBase", (0.06, 0.065, 0.075), rough=0.55, metal=0.2)
    return M


# =========================================================================================== shared parts
def _channel_edge(mid):
    """The two inner top corners of the clamp channel (kept square so the clamp fits a square OR dovetail rail)."""
    return abs(abs(mid.x) - JAW_IN) < 2e-4 and abs(mid.z - CONTACT) < 2e-4


def rail_clamp(name, y0, y1, W, top, mat, col, bev=0.0009, seg=1):
    """Picatinny clamp block: flat underside on the rail top (z = +0.1 mm), jaws hugging both flanks
    (inner faces at |x| = 0.0106) down to z = -0.0062. Built in mount space."""
    hw = W / 2
    c = 0.0012
    pts = [(-hw, top), (-hw, JAW_BOT + c), (-hw + c, JAW_BOT), (-JAW_IN, JAW_BOT), (-JAW_IN, CONTACT),
           (JAW_IN, CONTACT), (JAW_IN, JAW_BOT), (hw - c, JAW_BOT), (hw, JAW_BOT + c), (hw, top)]
    ob = prism(name, pts, "Y", y0, y1, mat, col)
    bevel(ob, bev, seg, exclude=_channel_edge)
    return ob


def hex_nut(name, x_face, y, z, side, mat, col, r=0.0045, t=0.0030):
    """Hex nut / bolt head on a clamp side, axis X, starting at the jaw face x_face, sticking out to `side`."""
    e = 0.0002  # embed
    h0, h1 = x_face - side * e, x_face + side * t
    prof = [(0.0, h0), (r, h0), (r, h1 - side * 0.0006), (r - 0.0007, h1), (0.0, h1)]
    ob = lathe(name, prof, "X", (0, y, z), steps=6, mats=mat, col=col, phase=math.radians(30))
    smooth(ob, 30)
    return ob


def knob_x(name, x_face, y, z, side, r, t, mat, col, steps=16, knurl=0.0007):
    e = 0.0002
    h0, h1 = x_face - side * e, x_face + side * t
    prof = [(0.0, h0), (r, h0, "k"), (r, h1 - side * 0.0012, "k"), (r - 0.0012, h1), (0.0, h1)]
    ob = lathe(name, prof, "X", (0, y, z), steps=steps, mats=mat, col=col, knurl=knurl)
    smooth(ob, 30)
    return ob


def screw_head(name, center, axis, sign, r, t, mat, col, steps=12, slot=True):
    """Small domed screw head with a driver slot. axis X/Y/Z, sign = direction it faces."""
    ai = {"X": 0, "Y": 1, "Z": 2}[axis]
    h0 = center[ai] - sign * 0.0002
    h1 = center[ai] + sign * t
    prof = [(0.0, h0), (r, h0), (r, h0 + sign * t * 0.55), (r * 0.7, h1), (0.0, h1)]
    ob = lathe(name, prof, axis, center, steps=steps, mats=mat, col=col)
    if slot:
        rng = [None, None, None]
        rng[ai] = tuple(sorted((h1 - sign * 0.0005, h1 + sign * 0.0010)))
        o1, o2 = [i for i in range(3) if i != ai]
        rng[o1] = (center[o1] - r * 1.3, center[o1] + r * 1.3)
        rng[o2] = (center[o2] - 0.0003, center[o2] + 0.0003)
        cut(ob, box("_slot", rng[0][0], rng[0][1], rng[1][0], rng[1][1], rng[2][0], rng[2][1]))
    smooth(ob, 30)
    return ob


# =========================================================================================== optics
def build_reddot(col, M):
    """Mini open reflex sight on a skeletonised Picatinny riser."""
    P = "ATT_optic_reddot"
    g, gm, rb, dk = M["graphite"], M["gunmetal"], M["rubber"], M["dark"]
    SL = 0.0490                       # sight line above the rail top
    body = []

    body.append(rail_clamp(P + "_Clamp", -0.0170, 0.0170, W=0.028, top=0.0050, mat=g, col=col))
    # skeletonised riser
    riser = prism(P + "_Riser", [(-0.0190, 0.0045), (0.0190, 0.0045), (0.0190, 0.0205), (0.0160, 0.0242),
                                 (-0.0160, 0.0242), (-0.0190, 0.0205)], "X", -0.0120, 0.0120, g, col)
    cut(riser, prism("_c", rrect(0.0, 0.0142, 0.0105, 0.0040, 0.0035, 4), "X", -0.02, 0.02), transfer_mat=dk)
    bevel(riser, 0.0010, 2)
    body.append(riser)

    # sight housing: low rear deck + forward lens shroud, side profile x front-view rounded top
    side = [(-0.0240, 0.0236), (0.0215, 0.0236), (0.0215, 0.0335), (0.0185, 0.0365), (-0.0010, 0.0365),
            (-0.0040, 0.0400), (-0.0060, 0.0635), (-0.0090, 0.0665), (-0.0165, 0.0665), (-0.0195, 0.0640),
            (-0.0250, 0.0385), (-0.0250, 0.0290)]
    hs = prism(P + "_Housing", side, "X", -0.0130, 0.0130, g, col)
    cut(hs, prism("_c", rrect(0.0, 0.0440, 0.0130, 0.0230, 0.0070, 5, corners=(1, 1, 0, 0)), "Y", -0.05, 0.05),
        op="INTERSECT")
    win = rrect(0.0, SL, 0.0095, 0.0105, 0.0035, 4)
    cut(hs, prism("_c", win, "Y", -0.05, 0.003), transfer_mat=dk)
    # battery-door seam on the deck top
    seam = prism("_c", rrect(0.0, 0.0090, 0.0080, 0.0060, 0.0020, 2), "Z", 0.0358, 0.040)
    inner = prism("_c2", rrect(0.0, 0.0090, 0.0072, 0.0052, 0.0016, 2), "Z", 0.030, 0.045)
    cut(seam, inner)
    cut(hs, seam, transfer_mat=dk)
    bevel(hs, 0.0010, 2)
    body.append(hs)

    # emitter hood on the deck (LED window faces the lens)
    em = prism(P + "_Emitter", [(0.0005, 0.0360), (0.0105, 0.0360), (0.0105, 0.0380), (0.0080, 0.0395),
                                (0.0005, 0.0395)], "X", -0.0045, 0.0045, g, col)
    bevel(em, 0.0006, 2)
    body.append(em)
    body.append(box(P + "_EmitterWin", -0.0025, 0.0025, 0.0000, 0.0008, 0.0366, 0.0388, dk, col))

    # adjustment screws (gunmetal): elevation on top of the deck, windage on the right (-X)
    body.append(screw_head(P + "_ScrewElev", (0.0, 0.0165, 0.0365), "Z", 1, 0.0026, 0.0014, gm, col))
    body.append(screw_head(P + "_ScrewWind", (-0.0130, 0.0120, 0.0300), "X", -1, 0.0024, 0.0013, gm, col))
    # brightness buttons, both sides of the shroud base
    for s in (1, -1):
        b = prism(P + "_Btn", rrect(-0.0150, 0.0298, 0.0042, 0.0026, 0.0014, 2), "X",
                  s * 0.0128, s * 0.0146, rb, col)
        bevel(b, 0.0005, 1)
        body.append(b)
    # cross-bolt: knurled nut on the left (+X), screw head on the right (-X)
    body.append(knob_x(P + "_ClampKnob", 0.0140, 0.0040, -0.0002, 1, 0.0045, 0.0035, gm, col, steps=14))
    body.append(hex_nut(P + "_ClampBolt", -0.0140, 0.0040, -0.0002, -1, gm, col, r=0.0036, t=0.0020))

    # lens: tilted 10 deg (top toward the shooter), embedded in the shroud walls
    yc = -0.0142
    glass = prism(P + "_Lens", rrect(0.0, SL, 0.0101, 0.0111, 0.0039, 4), "Y", yc - 0.0006, yc + 0.0006,
                  M["reflex"], col)
    rotate_x(glass, -10, (yc, SL))
    smooth(glass, 30)
    dot = disc(P + "_Dot", (0.0, yc + 0.0008, SL), 0.0011, "Y", n=12, mat=M["ice"], col=col)
    rotate_x(dot, -10, (yc, SL))
    ads = (0.0, yc + 0.0010, SL)
    return dict(body=body, glass=[glass], glow=[dot], ads=ads, clamps=[(-0.0170, 0.0170)],
                eye_relief=0.12, magnification=1.0, recommended_for=["MAKO"], default_for=[],
                kind="mini reflex")


def build_holo(col, M):
    """Bone box holographic sight (Mako default, DIRECTION_LOG item 2 / mako v09)."""
    P = "ATT_optic_holo"
    g, gm, rb, dk, bo = M["graphite"], M["gunmetal"], M["rubber"], M["dark"], M["bone"]
    SL = 0.0450                       # sight line (window centre) above the rail top
    HW = 0.0230                       # half width of the bone shell
    YF = -0.0240                      # hood front face
    ZB = 0.0080                       # bottom of the bone shell (dark base plate below it)
    body = []
    # rail clamp + dark base plate under the whole shell (v09: dark band under the bone body)
    body.append(rail_clamp(P + "_Clamp", -0.0440, 0.0270, W=0.034, top=0.0045, mat=g, col=col, seg=2))
    plate = prism(P + "_BasePlate", [(-0.0520, 0.0015), (0.0290, 0.0015), (0.0290, ZB + 0.0005),
                                     (-0.0520, ZB + 0.0005)], "X", -HW - 0.0005, HW + 0.0005, g, col)
    bevel(plate, 0.0012, 2)
    body.append(plate)

    # bone shell: low front deck (button tray) + wide hood with the big window and a chamfered brow (v09)
    side = [(-0.0540, ZB), (0.0300, ZB), (0.0300, 0.0610), (0.0280, 0.0660), (0.0240, 0.0680),
            (-0.0150, 0.0680), (YF, 0.0572), (YF, 0.0290), (YF - 0.0022, 0.0265), (-0.0490, 0.0265),
            (-0.0540, 0.0215)]
    sh = prism(P + "_Shell", side, "X", -HW, HW, bo, col)
    cut(sh, prism("_c", rrect(0.0, 0.0345, HW, 0.0345, 0.0105, 5, corners=(1, 1, 0, 0)), "Y", -0.08, 0.08),
        op="INTERSECT")
    # chamfer the hood's two front vertical edges (above the deck)
    c = 0.0060
    for s in (1, -1):
        cut(sh, prism("_c", [(s * (HW + 0.001), YF - 0.001), (s * (HW + 0.001), YF + c), (s * (HW - c), YF - 0.001)],
                      "Z", 0.0266, 0.09))
    # big window tunnel through the hood (dark lining)
    cut(sh, prism("_c", rrect(0.0, SL, 0.0163, 0.0145, 0.0045, 4), "Y", -0.08, 0.08), transfer_mat=dk)
    # deck: recessed button tray between two side walls, open into the hood face
    cut(sh, prism("_c", rrect(0.0, -0.03525, 0.0185, 0.01175, 0.0030, 3, corners=(0, 0, 1, 1)), "Z", 0.0235, 0.040))
    # rear battery-door recess under the window
    cut(sh, prism("_c", rrect(0.0, 0.0200, 0.0120, 0.0045, 0.0022, 3), "Y", 0.0292, 0.040))
    bevel(sh, 0.0015, 2)
    body.append(sh)
    # thick dark inner frames at both ends of the window (v09's dark window bezel)
    for (y0, y1) in ((YF + 0.0015, YF + 0.0055), (0.0240, 0.0280)):
        fr = prism(P + "_WinFrame", rrect(0.0, SL, 0.0165, 0.0147, 0.0046, 4), "Y", y0, y1, rb, col)
        cut(fr, prism("_c", rrect(0.0, SL, 0.0138, 0.0120, 0.0034, 4), "Y", y0 - 0.01, y1 + 0.01))
        bevel(fr, 0.0007, 1)
        body.append(fr)

    # deck buttons in the tray: one big round main button + a small one (v09)
    for (bx, by, br) in ((0.0070, -0.0385, 0.0052), (-0.0090, -0.0320, 0.0038)):
        b = lathe(P + "_BtnTop", [(0.0, 0.0231), (br, 0.0231), (br, 0.0262), (br - 0.0013, 0.0276), (0.0, 0.0276)],
                  "Z", (bx, by, 0), steps=16, mats=rb, col=col)
        smooth(b, 35)
        body.append(b)
    # side buttons / sensor windows on the deck sides
    for s in (1, -1):
        sb = prism(P + "_BtnSide", rrect(-0.0400, 0.0185, 0.0068, 0.0048, 0.0020, 2), "X",
                   s * (HW - 0.0005), s * (HW + 0.0026), rb, col)
        bevel(sb, 0.0007, 1)
        body.append(sb)
        body.append(screw_head(P + "_BtnBoss", (s * (HW + 0.0026), -0.0400, 0.0185), "X", s, 0.0020, 0.0008,
                               dk, col, steps=10, slot=False))
    # cross-bolt on the base plate: knurled knob with a thumb bar on the left (+X, the side v09 shows),
    # bolt head on the right (-X)
    kx = HW + 0.0005
    body.append(knob_x(P + "_ClampKnob", kx, 0.0150, 0.0045, 1, 0.0060, 0.0040, gm, col, steps=16))
    bar = box(P + "_ClampBar", kx + 0.0028, kx + 0.0056, 0.0150 - 0.0022, 0.0150 + 0.0022, -0.0040, 0.0130, gm, col)
    bevel(bar, 0.0008, 2)
    body.append(bar)
    body.append(hex_nut(P + "_ClampBolt", -kx, 0.0150, 0.0045, -1, gm, col, r=0.0042, t=0.0024))

    yc = -0.0060
    glass = prism(P + "_Glass", rrect(0.0, SL, 0.0169, 0.0151, 0.0047, 4), "Y", yc - 0.00075, yc + 0.00075,
                  M["reflex"], col)
    rotate_x(glass, -8, (yc, SL))
    smooth(glass, 30)
    dot = disc(P + "_RetDot", (0.0, yc + 0.0009, SL), 0.0013, "Y", n=12, mat=M["ice"], col=col)
    ring = ring_flat(P + "_RetRing", (0.0, yc + 0.0009, SL), 0.0050, 0.0055, "Y", n=24, mat=M["ice"], col=col)
    for o in (dot, ring):
        rotate_x(o, -8, (yc, SL))
    ads = (0.0, yc + 0.0011, SL)
    return dict(body=body, glass=[glass], glow=[dot, ring], ads=ads, clamps=[(-0.0440, 0.0270)],
                eye_relief=0.12, magnification=1.0, recommended_for=["MAKO"], default_for=["MAKO"],
                kind="box holographic")


def build_3x(col, M):
    """Compact 3x prism sight with integral QD mount."""
    P = "ATT_optic_3x"
    g, gm, rb, dk = M["graphite"], M["gunmetal"], M["rubber"], M["dark"]
    AX = 0.0500
    body = []
    body.append(rail_clamp(P + "_Clamp", -0.0280, 0.0280, W=0.032, top=0.0060, mat=g, col=col))
    neck = prism(P + "_Neck", [(-0.0260, 0.0055), (0.0260, 0.0055), (0.0260, 0.0170), (0.0220, 0.0215),
                               (-0.0220, 0.0215), (-0.0260, 0.0170)], "X", -0.0130, 0.0130, g, col)
    cut(neck, prism("_c", rrect(0.0, 0.0138, 0.0125, 0.0033, 0.0030, 4), "X", -0.02, 0.02), transfer_mat=dk)
    bevel(neck, 0.0010, 2)
    body.append(neck)

    # prism housing
    hs = prism(P + "_Housing", rrect(0.0, 0.0480, 0.0215, 0.0290, 0.0090, 1, corners=(1, 1, 0.45, 0.45)),
               "Y", -0.0260, 0.0240, g, col)
    cut(hs, prism("_c", [(-0.0260, 0.0150), (0.0240, 0.0150), (0.0240, 0.0730), (0.0200, 0.0770),
                         (-0.0165, 0.0770), (-0.0260, 0.0675)], "X", -0.03, 0.03), op="INTERSECT")
    # side panel recesses (both sides)
    for s in (1, -1):
        cut(hs, prism("_c", rrect(0.0035, 0.0335, 0.0170, 0.0060, 0.0025, 3), "X",
                      s * 0.0207, s * 0.030))
    bevel(hs, 0.0016, 2)
    body.append(hs)

    # turrets: elevation (top), windage (right, -X), illumination dial (left, +X)
    t = lathe(P + "_TurretElev", [(0.0, 0.0740), (0.0090, 0.0740, "k"), (0.0090, 0.0818, "k"),
                                  (0.0078, 0.0830), (0.0, 0.0830)], "Z", (0.0, 0.0010, 0), steps=20,
              mats=g, knurl=0.0007, col=col)
    smooth(t, 30)
    body.append(t)
    t = lathe(P + "_TurretWind", [(0.0, -0.0205), (0.0090, -0.0205, "k"), (0.0090, -0.0283, "k"),
                                  (0.0078, -0.0295), (0.0, -0.0295)], "X", (0, 0.0010, AX), steps=20,
              mats=g, knurl=0.0007, col=col)
    smooth(t, 30)
    body.append(t)
    t = lathe(P + "_IllumDial", [(0.0, 0.0205), (0.0102, 0.0205, "k"), (0.0102, 0.0268, "k"),
                                 (0.0090, 0.0280), (0.0, 0.0280)], "X", (0, 0.0010, AX), steps=24,
              mats=g, knurl=0.0008, col=col)
    smooth(t, 30)
    body.append(t)
    t = lathe(P + "_IllumHub", [(0.0, 0.0276), (0.0048, 0.0276), (0.0048, 0.0287), (0.0040, 0.0292),
                                (0.0, 0.0292)], "X", (0, 0.0010, AX), steps=16, mats=gm, col=col)
    smooth(t, 30)
    body.append(t)

    # objective (front) and eyepiece (rear): mat 0 graphite, 1 rubber, 2 dark
    obj = lathe(P + "_Objective", [(0.0, -0.0220), (0.0150, -0.0220), (0.0150, -0.0440), (0.0170, -0.0500),
                                   (0.0175, -0.0515, "k"), (0.0175, -0.0660, "k"), (0.0163, -0.0700),
                                   (0.0145, -0.0700), (0.0145, -0.0645), (0.0, -0.0645)],
                "Y", (0, 0, AX), steps=32, mats=[g, rb, dk], seg_mat=[0, 0, 0, 0, 0, 0, 0, 2, 2, 0],
                knurl=0.0006, col=col)
    smooth(obj, 30)
    body.append(obj)
    eye = lathe(P + "_Eyepiece", [(0.0, 0.0200), (0.0135, 0.0200), (0.0135, 0.0300), (0.0155, 0.0312),
                                  (0.0160, 0.0325, "k"), (0.0160, 0.0435, "k"), (0.0150, 0.0450),
                                  (0.0150, 0.0470), (0.0170, 0.0490), (0.0176, 0.0600), (0.0167, 0.0625),
                                  (0.0127, 0.0625), (0.0127, 0.0585), (0.0, 0.0585)],
                "Y", (0, 0, AX), steps=32, mats=[g, rb, dk],
                seg_mat=[0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 0], knurl=0.0006, col=col)
    smooth(eye, 30)
    body.append(eye)

    # QD throw lever on the right (-X), knurled cross-bolt nut on the left
    lev = prism(P + "_Lever", [(-0.0170, -0.0030), (0.0180, -0.0038), (0.0215, 0.0), (0.0180, 0.0038),
                               (-0.0170, 0.0030), (-0.0185, 0.0)], "X", -0.0193, -0.0158, gm, col)
    bevel(lev, 0.0007, 2)
    body.append(lev)
    body.append(knob_x(P + "_LeverPivot", -0.0193, 0.0180, 0.0, -1, 0.0040, 0.0012, gm, col, steps=12,
                       knurl=0.0))
    body.append(hex_nut(P + "_ClampNut", 0.0160, 0.0180, -0.0001, 1, gm, col, r=0.0042, t=0.0026))

    lens_o = lathe(P + "_LensObj", [(0.0, -0.0662), (0.0080, -0.0659), (0.0146, -0.0651), (0.0146, -0.0642),
                                    (0.0, -0.0642)], "Y", (0, 0, AX), steps=32, mats=M["lens"], col=col)
    lens_e = lathe(P + "_LensEye", [(0.0, 0.0597), (0.0080, 0.0594), (0.0128, 0.0588), (0.0128, 0.0580),
                                    (0.0, 0.0580)], "Y", (0, 0, AX), steps=32, mats=M["lens"], col=col)
    for o in (lens_o, lens_e):
        smooth(o, 40)
    dot = disc(P + "_RetDot", (0.0, 0.05985, AX), 0.0008, "Y", n=12, mat=M["ice"], col=col)
    ads = (0.0, 0.0625, AX)
    return dict(body=body, glass=[lens_o, lens_e], glow=[dot], ads=ads, clamps=[(-0.0280, 0.0280)],
                eye_relief=0.065, magnification=3.0, recommended_for=["MAKO"], default_for=[],
                kind="compact prism 3x")


def build_sniper(col, M):
    """5-25x long-range scope (Warden default): 0.38 m, 50 mm objective bell, turrets, sunshade, ice ring."""
    P = "ATT_optic_sniper"
    g, gm, rb, dk = M["graphite"], M["gunmetal"], M["rubber"], M["dark"]
    AX = 0.0440                      # scope axis above the rail top
    RY = 0.0520                      # ring centres at +-RY
    body = []

    # main body: eyepiece -> power ring seat -> 30 mm-class tube -> long taper -> objective bell
    # (mat 0 graphite, 2 dark inner walls)
    prof = [(0.0, 0.1400), (0.0200, 0.1400), (0.0200, 0.1450), (0.0240, 0.1450), (0.0250, 0.1438),
            (0.0250, 0.1110), (0.0258, 0.1100, "k"), (0.0258, 0.0975, "k"), (0.0215, 0.0940),
            (0.0215, 0.0760), (0.0185, 0.0680), (0.0185, -0.0850), (0.0340, -0.1420), (0.0340, -0.2010),
            (0.0300, -0.2010), (0.0300, -0.1970), (0.0, -0.1970)]
    seg = [2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 2, 0]
    tube = lathe(P + "_Tube", prof, "Y", (0, 0, AX), steps=32, mats=[g, rb, dk], seg_mat=seg, knurl=0.0008,
                 col=col)
    smooth(tube, 30)
    body.append(tube)
    # magnification ring (knurled) with a throw-lever fin on the right (-X)
    pr = lathe(P + "_PowerRing", [(0.0213, 0.0905), (0.0240, 0.0905, "k"), (0.0240, 0.0780, "k"),
                                  (0.0213, 0.0780)], "Y", (0, 0, AX), steps=32, mats=g, knurl=0.0009, col=col)
    smooth(pr, 30)
    body.append(pr)
    fin = box(P + "_PowerFin", -0.0340, -0.0225, 0.0805, 0.0880, AX - 0.0028, AX + 0.0028, g, col)
    bevel(fin, 0.0008, 1)
    body.append(fin)
    # thin ice-painted ring at the objective (paint, not emissive) + short sunshade (inner walls dark)
    ice = lathe(P + "_IceRing", [(0.0300, -0.2008), (0.0356, -0.2008), (0.0356, -0.2066), (0.0300, -0.2066)],
                "Y", (0, 0, AX), steps=32, mats=[M["icepaint"], dk], seg_mat=[0, 0, 0, 1], col=col)
    smooth(ice, 30)
    shade = lathe(P + "_Sunshade", [(0.0300, -0.2064), (0.0330, -0.2064), (0.0330, -0.2332), (0.0315, -0.2350),
                                    (0.0300, -0.2350)], "Y", (0, 0, AX), steps=32, mats=[g, dk],
                  seg_mat=[0, 0, 0, 0, 1], col=col)
    smooth(shade, 30)
    body += [ice, shade]

    # turret saddle + turrets: elevation (top), windage (right, -X), side focus / parallax (left, +X)
    sad = box(P + "_Saddle", -0.0220, 0.0220, -0.0310, 0.0310, AX - 0.0220, AX + 0.0220, g, col)
    bevel(sad, 0.0080, 3, harden=True)
    body.append(sad)
    tur = lathe(P + "_TurretElev", [(0.0, AX + 0.0190), (0.0150, AX + 0.0190), (0.0150, AX + 0.0270),
                                    (0.0192, AX + 0.0275, "k"), (0.0192, AX + 0.0480, "k"), (0.0170, AX + 0.0505),
                                    (0.0, AX + 0.0505)], "Z", (0, 0, 0), steps=24, mats=g, knurl=0.0012,
                col=col)
    smooth(tur, 30)
    body.append(tur)
    tw = lathe(P + "_TurretWind", [(0.0, -0.0190), (0.0150, -0.0190), (0.0150, -0.0270),
                                   (0.0188, -0.0275, "k"), (0.0188, -0.0455, "k"), (0.0168, -0.0478),
                                   (0.0, -0.0478)], "X", (0, 0, AX), steps=20, mats=g, knurl=0.0012, col=col)
    smooth(tw, 30)
    body.append(tw)
    sf = lathe(P + "_SideFocus", [(0.0, 0.0190), (0.0172, 0.0190, "k"), (0.0172, 0.0372, "k"),
                                  (0.0156, 0.0392), (0.0082, 0.0392), (0.0082, 0.0422), (0.0, 0.0422)],
               "X", (0, 0, AX), steps=20, mats=g, knurl=0.0010, col=col)
    smooth(sf, 30)
    body.append(sf)

    # two chunky rings, each with its own rail clamp (origin = midpoint of the two clamp contacts)
    for k, ry in enumerate((-RY, RY)):
        ring = prism(P + "_Ring%d" % k, rrect(0.0, AX, 0.0255, 0.0260, 0.0095, 3), "Y", ry - 0.0110,
                     ry + 0.0110, g, col)
        cut(ring, lathe("_c", [(0.0, ry - 0.02), (0.0186, ry - 0.02), (0.0186, ry + 0.02), (0.0, ry + 0.02)],
                        "Y", (0, 0, AX), steps=24))
        for s in (1, -1):        # cap split line on both sides
            cut(ring, box("_c", s * 0.0215, s * 0.0300, ry - 0.0120, ry + 0.0120, AX - 0.0006, AX + 0.0006),
                transfer_mat=dk)
        bevel(ring, 0.0013, 1)
        body.append(ring)
        neck = prism(P + "_RingNeck%d" % k, [(-0.0150, 0.0055), (0.0150, 0.0055), (0.0150, 0.0105),
                                             (0.0195, AX - 0.0200), (-0.0195, AX - 0.0200), (-0.0150, 0.0105)],
                     "Y", ry - 0.0100, ry + 0.0100, g, col)
        bevel(neck, 0.0010, 1)
        body.append(neck)
        body.append(rail_clamp(P + "_Clamp%d" % k, ry - 0.0135, ry + 0.0135, W=0.032, top=0.0062, mat=g,
                               col=col))
        body.append(hex_nut(P + "_ClampNut%d" % k, 0.0160, ry, -0.0001, 1, gm, col, r=0.0045, t=0.0030))
        body.append(hex_nut(P + "_ClampBolt%d" % k, -0.0160, ry, -0.0001, -1, gm, col, r=0.0040, t=0.0022))
        for s in (1, -1):        # cap screws (one per side, above the split)
            body.append(screw_head(P + "_CapScrew", (s * 0.0255, ry, AX + 0.0120), "X", s, 0.0024,
                                   0.0011, gm, col, steps=10, slot=False))

    lens_o = lathe(P + "_LensObj", [(0.0, -0.1988), (0.0160, -0.1984), (0.0302, -0.1975), (0.0302, -0.1966),
                                    (0.0, -0.1966)], "Y", (0, 0, AX), steps=32, mats=M["lens"], col=col)
    lens_e = lathe(P + "_LensEye", [(0.0, 0.1414), (0.0202, 0.1404), (0.0202, 0.1396), (0.0, 0.1396)],
                   "Y", (0, 0, AX), steps=32, mats=M["lens"], col=col)
    for o in (lens_o, lens_e):
        smooth(o, 40)
    ads = (0.0, 0.1450, AX)
    return dict(body=body, glass=[lens_o, lens_e], glow=[], ads=ads,
                clamps=[(-RY - 0.0135, -RY + 0.0135), (RY - 0.0135, RY + 0.0135)],
                eye_relief=0.085, magnification="5-25", recommended_for=["WARDEN"], default_for=["WARDEN"],
                kind="5-25x long-range scope")


def build_thermal(col, M):
    """Bulky boxy thermal scope: germanium objective, side battery housing, rear eyecup, amber status light."""
    P = "ATT_optic_thermal"
    g, gm, rb, dk = M["graphite"], M["gunmetal"], M["rubber"], M["dark"]
    AX = 0.0520
    body = []
    body.append(rail_clamp(P + "_Clamp", -0.0340, 0.0340, W=0.034, top=0.0062, mat=g, col=col))
    neck = prism(P + "_Neck", [(-0.0200, 0.0055), (0.0200, 0.0055), (0.0200, 0.0165), (0.0170, 0.0200),
                               (-0.0170, 0.0200), (-0.0200, 0.0165)], "Y", -0.0300, 0.0300, g, col)
    bevel(neck, 0.0010, 1)
    body.append(neck)

    hs = prism(P + "_Housing", rrect(0.0, 0.0540, 0.0290, 0.0360, 0.0100, 1, corners=(1, 1, 0.6, 0.6)),
               "Y", -0.0500, 0.0620, g, col)
    cut(hs, prism("_c", [(-0.0500, 0.0100), (0.0620, 0.0100), (0.0620, 0.0840), (0.0560, 0.0900),
                         (-0.0400, 0.0900), (-0.0500, 0.0800)], "X", -0.04, 0.04), op="INTERSECT")
    # shell split line
    fo = box("_c", -0.040, 0.040, 0.0194, 0.0206, 0.0, 0.10)
    fi = prism("_c2", rrect(0.0, 0.0540, 0.0278, 0.0348, 0.0095, 1, corners=(1, 1, 0.6, 0.6)), "Y", 0.018, 0.022)
    cut(fo, fi)
    cut(hs, fo, transfer_mat=dk)
    # heat-sink grooves on the right side (-X)
    gs = [box("_g%d" % i, -0.040, -0.0275, -0.0380, 0.0080, z - 0.0016, z + 0.0016)
          for i, z in enumerate((0.040, 0.048, 0.056, 0.064))]
    cut(hs, merge(gs, "_c"), transfer_mat=dk)

    def _groove(m):
        return (m.x < -0.0270 and m.y < 0.0085 and 0.036 < m.z < 0.068) or abs(m.y - 0.020) < 0.0009
    bevel(hs, 0.0018, 2, exclude=_groove)
    body.append(hs)

    # short accessory rail on top, behind the buttons
    tr = prism(P + "_TopRail", [(-0.0105, 0.0895), (0.0105, 0.0895), (0.0105, 0.0965), (0.0090, 0.0980),
                                (-0.0090, 0.0980), (-0.0105, 0.0965)], "Y", 0.0215, 0.0535, g, col)
    cut(tr, merge([box("_s%d" % i, -0.02, 0.02, y - 0.0025, y + 0.0025, 0.0950, 0.11)
                   for i, y in enumerate((0.0275, 0.0375, 0.0475))], "_c"))
    bevel(tr, 0.0005, 1)
    body.append(tr)
    # top control buttons
    for i, y in enumerate((-0.0200, -0.0060, 0.0080)):
        b = prism(P + "_Btn%d" % i, rrect(0.0, y, 0.0075, 0.0048, 0.0022, 2), "Z", 0.0895, 0.0925, rb, col)
        bevel(b, 0.0008, 1)
        body.append(b)

    # focus ring (knurled) + square lens hood with round bore
    fr = lathe(P + "_FocusRing", [(0.0200, -0.0490), (0.0262, -0.0490, "k"), (0.0262, -0.0640, "k"),
                                  (0.0200, -0.0640)], "Y", (0, 0, AX), steps=36, mats=g, knurl=0.0012, col=col)
    smooth(fr, 30)
    body.append(fr)
    hood = prism(P + "_Hood", rrect(0.0, AX, 0.0275, 0.0275, 0.0090, 3), "Y", -0.1000, -0.0635, g, col)
    cut(hood, prism("_c", [(-0.0600, 0.0), (-0.0840, 0.0), (-0.0950, 0.1), (-0.0600, 0.1)], "X", -0.04, 0.04),
        op="INTERSECT")     # forward-leaning sun visor
    cut(hood, lathe("_c", [(0.0, -0.10), (0.0215, -0.10), (0.0215, -0.05), (0.0, -0.05)], "Y", (0, 0, AX),
                    steps=32), transfer_mat=dk)
    bevel(hood, 0.0016, 2)
    body.append(hood)
    # lens retaining ring (dark) at the bottom of the hood bore
    rr_ = lathe(P + "_LensRing", [(0.0180, -0.0700), (0.0216, -0.0700), (0.0216, -0.0745), (0.0180, -0.0745)],
                "Y", (0, 0, AX), steps=24, mats=dk, col=col)
    smooth(rr_, 30)
    body.append(rr_)

    # side battery housing on the left (+X): D-section box fused to the housing, knurled cap at the rear
    bh = prism(P + "_Battery", rrect(0.0310, 0.0420, 0.0100, 0.0130, 0.0085, 3, corners=(1, 0, 0, 1)), "Y",
               -0.0400, 0.0285, g, col)
    fo = prism("_c", rrect(0.0310, 0.0420, 0.0130, 0.0160, 0.0100, 3, corners=(1, 0, 0, 1)), "Y",
               -0.0300, -0.0288)
    fi = prism("_c2", rrect(0.0310, 0.0420, 0.0090, 0.0120, 0.0075, 3, corners=(1, 0, 0, 1)), "Y",
               -0.0310, -0.0278)
    cut(fo, fi)
    cut(bh, fo, transfer_mat=dk)   # battery-door seam
    bevel(bh, 0.0016, 1)
    body.append(bh)
    bc_ = lathe(P + "_BatteryCap", [(0.0, 0.0275), (0.0102, 0.0275, "k"), (0.0102, 0.0390, "k"),
                                    (0.0088, 0.0408), (0.0, 0.0408)], "Y", (0.0320, 0, 0.0420), steps=24,
                mats=gm, knurl=0.0008, col=col)
    smooth(bc_, 30)
    body.append(bc_)

    # rear bezel + rubber eyecup (inner wall dark)
    bz = lathe(P + "_Bezel", [(0.0130, 0.0600), (0.0212, 0.0600), (0.0212, 0.0660), (0.0130, 0.0660)],
               "Y", (0, 0, AX), steps=32, mats=g, col=col)
    smooth(bz, 30)
    body.append(bz)
    cup = lathe(P + "_Eyecup", [(0.0132, 0.0655), (0.0174, 0.0655), (0.0178, 0.0760), (0.0202, 0.0900),
                                (0.0186, 0.0918), (0.0152, 0.0850), (0.0136, 0.0720)], "Y", (0, 0, AX),
                steps=32, mats=[rb, dk], seg_mat=[0, 0, 0, 0, 1, 1, 1], col=col)
    smooth(cup, 30)
    body.append(cup)
    # QD levers on the right (-X), cross-bolt nut on the left
    for k, (y0, y1, ang) in enumerate(((-0.0300, -0.0040, 6), (0.0040, 0.0300, -6))):
        yc = (y0 + y1) / 2
        lev = prism(P + "_Lever%d" % k, rrect(yc, -0.0002, (y1 - y0) / 2, 0.0036, 0.0016, 2), "X",
                    -0.0204, -0.0168, gm, col)
        rotate_x(lev, ang, (yc, 0.0))
        bevel(lev, 0.0006, 1)
        body.append(lev)
    body.append(hex_nut(P + "_ClampNut", 0.0170, 0.0, -0.0001, 1, gm, col, r=0.0045, t=0.0028))
    # status light bezel (graphite) on the rear face, upper left (+X)
    lb = lathe(P + "_LedBezel", [(0.0016, 0.0614), (0.0030, 0.0614), (0.0030, 0.0632), (0.0016, 0.0632)],
               "Y", (0.0185, 0, 0.0790), steps=12, mats=g, col=col)
    smooth(lb, 30)
    body.append(lb)

    lens_o = lathe(P + "_Germanium", [(0.0, -0.0735), (0.0110, -0.0732), (0.0216, -0.0724), (0.0216, -0.0712),
                                      (0.0, -0.0712)], "Y", (0, 0, AX), steps=32, mats=M["germanium"], col=col)
    lens_e = lathe(P + "_Display", [(0.0, 0.0728), (0.0137, 0.0726), (0.0137, 0.0715), (0.0, 0.0715)],
                   "Y", (0, 0, AX), steps=32, mats=M["lens"], col=col)
    for o in (lens_o, lens_e):
        smooth(o, 40)
    led = lathe(P + "_StatusLED", [(0.0, 0.0612), (0.0017, 0.0612), (0.0017, 0.0628), (0.0011, 0.0638),
                                   (0.0, 0.0641)], "Y", (0.0185, 0, 0.0790), steps=12, mats=M["amber"], col=col)
    smooth(led, 60)
    ads = (0.0, 0.0918, AX)
    return dict(body=body, glass=[lens_o, lens_e], glow=[led], ads=ads, clamps=[(-0.0340, 0.0340)],
                eye_relief=0.025, magnification="2-8 thermal", recommended_for=["WARDEN"], default_for=[],
                kind="thermal scope")


BUILDERS = {"optic_reddot": build_reddot, "optic_holo": build_holo, "optic_3x": build_3x,
            "optic_sniper": build_sniper, "optic_thermal": build_thermal}


# =========================================================================================== assembly
def finalize(oid, col, d):
    P = "ATT_" + oid
    root = empty(P, (0, 0, 0), col, size=0.03, kind="ARROWS")
    out = {}
    for key, objs in (("Body", d["body"]), ("Glass", d["glass"]), ("Glow", d["glow"])):
        if not objs:
            continue
        if "--debug" in ARGS:
            rows = sorted(((tri_count([o]), o.name) for o in objs), reverse=True)
            print("  parts of %s_%s:" % (P, key), ", ".join("%s=%d" % (n.replace(P + "_", ""), t)
                                                            for t, n in rows))
        for o in objs:
            apply_xform(o)
        j = bc.join(list(objs), P + "_" + key)
        bc.smart_uv(j)
        j.parent = root
        out[key] = j
    ads = empty(P + "_SOCKET_ADS", d["ads"], col, parent=root, size=0.01)
    ads["eye_relief_m"] = d["eye_relief"]
    ads["note"] = "sight line at the rear of the reticle/eyepiece; camera eye point = +Y by eye_relief_m"
    meshes = list(out.values())
    mn, mx = bc.world_bounds(meshes)
    root["optic_id"] = oid
    root["category"] = "optic"
    root["mount"] = "picatinny top rail; origin = clamp contact centre on rail top"
    root["ads_height_m"] = round(d["ads"][2], 4)
    root["length_m"] = round(mx.y - mn.y, 4)
    root["magnification"] = str(d["magnification"])
    return root, out, ads, (mn, mx)


def make_rail(name, y0, y1, col, M):
    """Dummy stylised Picatinny segment in mount space: top at z 0, base at z -0.0095 (Mako dovetail profile,
    0.021 wide, cross slots 0.005 long x 0.003 deep every 0.010; teeth centred on multiples of 0.010)."""
    prof = [(-0.0075, -RAIL_H), (0.0075, -RAIL_H), (0.0105, -RAIL_H + 0.0030), (0.0105, -0.0015),
            (0.0090, 0.0), (-0.0090, 0.0), (-0.0105, -0.0015), (-0.0105, -RAIL_H + 0.0030)]
    rail = prism(name, prof, "Y", y0, y1, M["testrail"], col)
    cs = []
    k0 = math.ceil((y0 + 0.006) / RAIL_PITCH)
    k1 = math.floor((y1 - 0.006) / RAIL_PITCH)
    for k in range(k0, k1):
        yc = k * RAIL_PITCH + RAIL_PITCH / 2
        cs.append(box("_s%d" % k, -0.02, 0.02, yc - RAIL_SLOT / 2, yc + RAIL_SLOT / 2, -RAIL_SLOT_D, 0.01))
    if cs:
        cut(rail, merge(cs, "_slots"))
    bevel(rail, 0.0005, 1)
    base = prism(name + "Base", rrect(0.0, -RAIL_H - 0.0150, 0.0170, 0.0153, 0.0040, 2, corners=(1, 1, 0, 0)),
                 "Y", y0 - 0.01, y1 + 0.01, M["testbase"], col)
    bevel(base, 0.0010, 2)
    return [rail, base]


def fit_check(oid, body, glass, clamps, rail):
    """BVH test: no triangle of the optic may intersect the dummy rail, and every clamp must touch the rail
    top + both flanks (nearest optic surface within 0.3 mm of sample points on the rail)."""
    dg = bpy.context.evaluated_depsgraph_get()
    rb = BVHTree.FromObject(rail, dg)
    res = {"intersections": 0, "samples": []}
    for o in [body] + glass:
        ob = BVHTree.FromObject(o, dg)
        res["intersections"] += len(ob.overlap(rb))
    bb = BVHTree.FromObject(body, dg)
    worst = 0.0
    for (y0, y1) in clamps:
        yc = round(((y0 + y1) / 2) / RAIL_PITCH) * RAIL_PITCH   # a tooth centre under the clamp
        for name, p in (("top", (0.0, yc, 0.0)), ("top_l", (0.006, yc, 0.0)), ("top_r", (-0.006, yc, 0.0)),
                        ("flank_l", (0.0105, yc, -0.0040)), ("flank_r", (-0.0105, yc, -0.0040))):
            hit = bb.find_nearest(Vector(p))
            dist = hit[3] if hit[0] is not None else 1.0
            worst = max(worst, dist)
            res["samples"].append({"clamp_y": round(yc, 4), "where": name, "gap_m": round(dist, 5)})
    res["max_gap_m"] = round(worst, 5)
    res["ok"] = res["intersections"] == 0 and worst < 0.0003
    print("FITCHECK %s: intersections=%d max_gap=%.5f m -> %s" % (oid, res["intersections"], worst,
                                                                    "OK" if res["ok"] else "FAIL"))
    return res


def tri_count(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    t = 0
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        t += sum(len(p.vertices) - 2 for p in me.polygons)
        ev.to_mesh_clear()
    return t


def export_optic(oid, root):
    objs = [root] + [c for c in root.children_recursive]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = root
    base = os.path.join(OUT, "ATT_" + oid)
    bpy.ops.export_scene.gltf(filepath=base + ".glb", export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_extras=True)
    bpy.ops.export_scene.fbx(filepath=base + ".fbx", use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             use_mesh_modifiers=True, add_leaf_bones=False, path_mode="COPY",
                             embed_textures=True, use_custom_props=True)
    print("exported", base + ".glb / .fbx")


# =========================================================================================== rendering
def set_visible(objs):
    vis = set(o.name for o in objs)
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.hide_render = o.name not in vis


def eye_view(path, ads, dist, lens=50, res=None):
    sc = bpy.context.scene
    cam = bpy.data.objects.get("_PreviewCam")
    cam.data.type = "PERSP"
    cam.data.lens = lens
    cam.location = Vector(ads) + Vector((0, dist, 0.0))
    cam.rotation_euler = (Vector(ads) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)
    return path


def render_optic(oid, meshes, rail_objs, ads, eye_relief, mode, closeups):
    paths = []
    pre = "ATT_" + oid
    if mode == "quick":
        views_alone = ("three_quarter", "right", "back")
        views_rail = ()
    else:
        views_alone = ("right", "left", "three_quarter", "three_quarter_back", "front", "back", "top")
        views_rail = ("right", "three_quarter", "front", "back")
    set_visible(meshes)
    paths += bc.render_views(REN, pre, objs=meshes, views=views_alone, res=(RES, RES), engine="CYCLES",
                             samples=SAMPLES, lens=85)
    if views_rail:
        set_visible(meshes + rail_objs)
        paths += bc.render_views(REN, pre + "_onrail", objs=meshes, views=views_rail, res=(RES, RES),
                                 engine="CYCLES", samples=SAMPLES, lens=85, margin=1.25)
    if mode != "quick":
        set_visible(meshes + rail_objs)
        paths.append(eye_view(os.path.join(REN, pre + "_eye.png"), ads, max(eye_relief, 0.06) + 0.05, lens=50))
        set_visible(meshes)
        for cname, (center, radius, vdir) in closeups.items():
            paths += bc.render_views(REN, pre + "_close_" + cname, objs=meshes, views=(vdir,), res=(RES, RES),
                                     engine="CYCLES", samples=SAMPLES, lens=85, focus=(center, radius))
    return paths


CLOSEUPS = {
    "optic_reddot": {"lens": ((0, -0.012, 0.045), 0.026, (0.6, 1.0, 0.45))},
    "optic_holo": {"window": ((0, 0.000, 0.045), 0.034, (0.55, 1.0, 0.35)),
                   "buttons": ((0, -0.035, 0.022), 0.030, (0.9, -0.8, 0.6))},
    "optic_3x": {"turrets": ((0, 0.000, 0.060), 0.040, (-0.9, -0.6, 0.5))},
    "optic_sniper": {"turrets": ((0, 0.000, 0.060), 0.060, (-0.8, -0.7, 0.55)),
                     "objective": ((0, -0.200, 0.044), 0.055, (0.45, -1.0, 0.25))},
    "optic_thermal": {"rear": ((0, 0.070, 0.055), 0.050, (0.6, 1.0, 0.35)),
                      "front": ((0, -0.070, 0.050), 0.050, (0.55, -1.0, 0.25))},
}


# =========================================================================================== main
def main():
    bc.reset_scene()
    sc = bpy.context.scene
    M = make_materials()
    ids = OPTIC_IDS if not ONLY else [i for i in OPTIC_IDS if i in ONLY.split(",")]
    test_col = bc.collection("_TestFit")
    results = {}
    for oid in ids:
        col = bc.collection("ATT_" + oid)
        d = BUILDERS[oid](col, M)
        root, parts, ads, (mn, mx) = finalize(oid, col, d)
        rail = make_rail("_Rail_" + oid, mn.y - 0.025, mx.y + 0.025, test_col, M)
        fit = fit_check(oid, parts["Body"], [parts[k] for k in ("Glass",) if k in parts], d["clamps"], rail[0])
        meshes = list(parts.values())
        tris = tri_count(meshes)
        results[oid] = dict(root=root, parts=parts, ads=ads, d=d, bounds=(mn, mx), rail=rail, fit=fit, tris=tris)
        print("OPTIC %s tris=%d  size=(%.4f, %.4f, %.4f)  ads=%s" % (
            oid, tris, mx.x - mn.x, mx.y - mn.y, mx.z - mn.z, tuple(round(v, 4) for v in d["ads"])))
        for o in meshes:
            print("    %-34s %6d tris" % (o.name, tri_count([o])))

    if DO_EXPORT and not ONLY:
        for oid, r in results.items():
            export_optic(oid, r["root"])
        catalog = []
        fits = {}
        for oid, r in results.items():
            mn, mx = r["bounds"]
            d = r["d"]
            catalog.append({
                "id": oid,
                "category": "optic",
                "file": "ATT_%s.glb" % oid,
                "file_fbx": "ATT_%s.fbx" % oid,
                "root_node": "ATT_" + oid,
                "ads_socket": "ATT_%s_SOCKET_ADS" % oid,
                "ads_height_m": round(d["ads"][2], 4),
                "ads_location_m": [round(v, 4) for v in d["ads"]],
                "eye_relief_m": d["eye_relief"],
                "length_m": round(mx.y - mn.y, 4),
                "width_m": round(mx.x - mn.x, 4),
                "height_m": round(mx.z - mn.z, 4),
                "magnification": str(d["magnification"]),
                "kind": d["kind"],
                "sockets_accepted": ["_SOCKET_Optic"],
                "recommended_for": d["recommended_for"],
                "default_for": d["default_for"],
                "tris": r["tris"],
                "rail_fit_ok": r["fit"]["ok"],
            })
            fits[oid] = r["fit"]
        with open(os.path.join(OUT, "catalog.json"), "w") as f:
            json.dump({"prefix": "ATT", "rail_standard": {"top_width_m": RAIL_W, "height_m": RAIL_H,
                                                         "slot_pitch_m": RAIL_PITCH},
                       "mount_space": "origin = clamp contact centre on rail top, forward -Y, up +Z, "
                                      "shooter right = -X",
                       "optics": catalog}, f, indent=2)
        with open(os.path.join(OUT, "fitcheck.json"), "w") as f:
            json.dump(fits, f, indent=2)
        print("wrote catalog.json / fitcheck.json")

    if RENDER != "none":
        bc.setup_studio(sc)
        all_paths = {}
        for oid, r in results.items():
            meshes = list(r["parts"].values())
            all_paths[oid] = render_optic(oid, meshes, r["rail"], r["d"]["ads"], r["d"]["eye_relief"], RENDER,
                                          CLOSEUPS.get(oid, {}))
        if RENDER == "full" and not ONLY:
            # line-up: every optic on its own rail, side by side
            offs = {}
            x = 0.0
            for oid, r in results.items():
                offs[oid] = Vector((x, 0, 0))
                x += 0.085
            vis = []
            for oid, r in results.items():
                r["root"].location = offs[oid]
                for o in r["rail"]:
                    o.location = offs[oid]
                vis += list(r["parts"].values()) + r["rail"]
            set_visible(vis)
            bpy.context.view_layer.update()
            bc.render_views(REN, "ATT_optics_lineup", objs=vis, views=("three_quarter", "right", "top"),
                            res=(1400, 1000), engine="CYCLES", samples=SAMPLES, lens=85, margin=1.05)
            for oid, r in results.items():
                r["root"].location = (0, 0, 0)
                for o in r["rail"]:
                    o.location = (0, 0, 0)
            bpy.context.view_layer.update()
        with open(os.path.join(REN, "_render_index.json"), "w") as f:
            json.dump(all_paths, f, indent=2)
        # labelled contact sheets + concept comparisons (system python + PIL)
        try:
            subprocess.run(["python", os.path.join(OUT, "make_sheets.py")], check=False, timeout=300)
        except Exception as e:  # noqa: BLE001
            print("make_sheets failed:", e)

    if DO_EXPORT and not ONLY:
        for o in bpy.context.scene.objects:
            if o.type == "MESH":
                o.hide_render = o.name.startswith("_")
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "optics.blend"), compress=True)
        print("saved", os.path.join(OUT, "optics.blend"))


main()
