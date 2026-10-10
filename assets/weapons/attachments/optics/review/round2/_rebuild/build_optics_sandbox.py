"""build_optics.py - shared OPTICS attachment set (prefix ATT) for the val etf prototype.

Re-runnable from scratch (headless Blender 5.2):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/weapons/attachments/optics/build_optics.py" -- [--render none|quick|full]
      [--only optic_holo,optic_3x] [--res 800] [--samples 48] [--no-export]

Every optic is modeled in MOUNT SPACE (art/WEAPON_MODULAR_SPEC.md):
  origin = centre of the clamp contact on the rail TOP surface, forward = -Y, up = +Z,
  shooter's RIGHT = -X, LEFT = +X.
Each optic lives in its own collection `ATT_<optic>` with a root empty `ATT_<optic>` at the origin, its meshes
as one child node per role (`_Body` opaque multi-material; `_Glass` reflex window; `_Objective` / `_Ocular`
lenses; `_Display` thermal screen; `_Reticle` ADS reticle facing the eye; `_Glint` third-person glint facing
forward; `_StatusLight` thermal LED) and the empty `ATT_<optic>_SOCKET_ADS` on the sight line at the rear of the
reticle / eyepiece (camera eye point = socket + Y * eye_relief_m).

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

OUT = r"F:/git/val etf/assets/weapons/attachments/optics/review/round2/_rebuild"
REN = OUT + "/renders"

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _arg(name, default=None):
    if name in ARGS:
        i = ARGS.index(name)
        return ARGS[i + 1] if i + 1 < len(ARGS) else True
    return default


RENDER = _arg("--render", "full")          # none | quick | full | iter
ONLY = _arg("--only", None)
RES = int(_arg("--res", 800))
SAMPLES = int(_arg("--samples", 48))
DO_EXPORT = "--no-export" not in ARGS
VIEWS = _arg("--views", None)               # comma list of bc view names / "x_y_z" directions (iteration renders)
TAG = _arg("--tag", "")                     # suffix for iteration renders (written to _work/iter)

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
# which guns accept each optic (mirrors game/assets/data/attachments.ron "fits")
COMPAT = {"optic_reddot": ["MAKO", "WARDEN"], "optic_holo": ["MAKO", "WARDEN"], "optic_3x": ["MAKO", "WARDEN"],
          "optic_sniper": ["WARDEN"], "optic_thermal": ["WARDEN"]}
GUNS = {"WARDEN": (r"F:/git/val etf/assets/weapons/vk50_warden", "WARDEN_SOCKET_Optic"),
        "MAKO": (r"F:/git/val etf/assets/weapons/ar7_mako", "MAKO_SOCKET_Optic")}
# ADS zoom (mirrors game/assets/data/attachments.ron "zoom"; sniper = its low power): the ADS check renders at the
# game's vertical FOV 78 deg / zoom
ZOOM = {"optic_reddot": 1.15, "optic_holo": 1.25, "optic_3x": 3.0, "optic_sniper": 6.0, "optic_thermal": 4.0}
GAME_VFOV = 78.0
# camera eye point = _SOCKET_ADS + Y * eye_relief_m. The 1x sights are tuned so the clear window is >= 25 % of the
# screen height at the game's ADS FOV (the 0.12 used before gave a 10 x 15 % tunnel on the holo).
EYE_RELIEF = {"optic_reddot": 0.065, "optic_holo": 0.080, "optic_3x": 0.065, "optic_sniper": 0.085,
              "optic_thermal": 0.025}
# 1x reticles are real geometry sized for that eye relief (angular size, diameter): a game-readable centre dot
# (~2 px at 720p, real holo dots are 1-2 MOA) and an EOTech-class 68 MOA ring with a 4 MOA line
DOT_MOA = 10
RING_MOA = 68
RING_LINE_MOA = 4


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


MOA = math.radians(1.0 / 60.0)


def decal(name, center, r0, r1, facing, n=12, mat=None, col=None):
    """One-sided flat decal in the XZ plane at y = center.y, normal = facing * +Y: a disc (r0 == 0, triangle fan)
    or a ring (r0 < r1). Used for ADS reticles (facing the eye, +Y) and third-person glints (facing forward, -Y):
    with backface culling (glTF doubleSided false) the eye never sees the glint and the front never sees the
    reticle."""
    cx, cy, cz = center
    bm = bmesh.new()
    outer = [bm.verts.new((cx + r1 * math.cos(2 * math.pi * i / n), cy, cz + r1 * math.sin(2 * math.pi * i / n)))
             for i in range(n)]
    if r0 <= 1e-9:
        c = bm.verts.new((cx, cy, cz))
        for i in range(n):
            bm.faces.new((c, outer[i], outer[(i + 1) % n]))
    else:
        inner = [bm.verts.new((cx + r0 * math.cos(2 * math.pi * i / n), cy, cz + r0 * math.sin(2 * math.pi * i / n)))
                 for i in range(n)]
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((inner[i], outer[i], outer[j], inner[j]))
    bm.normal_update()
    flip = [f for f in bm.faces if f.normal.y * facing < 0]
    if flip:
        bmesh.ops.reverse_faces(bm, faces=flip)
    ob = _new_obj(name, bm, mat, col)
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


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
TEXDIR = os.path.join(OUT, "textures")
TILE_M = 1.0 / 6.0       # metres of surface per detail-texture repeat (= the Mako's bone density, 6 per metre)


def _srgb_to_lin(c):
    import numpy as np
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(c):
    import numpy as np
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def bake_albedo(mat_name, src_name, color, mix, normalize=True, size=512):
    """Bake palette colour x subtle detail multiply into one sRGB PNG (textures/<mat>.png) that is wired straight
    into Base Color. glTF then carries it as baseColorTexture with factor 1 and the FBX exporter finds and embeds
    it (it ignores textures behind a Mix node), so Blender, the .glb and the .fbx all show the same colour.
      normalize=True : linear = colour * (1 - mix * (1 - src / src_p99.5))   (optics' graphite / gunmetal)
      normalize=False: linear = colour * ((1 - mix) + mix * src)             (= mako_lib.bake_tint, used for bone
                       so the holo's bone is bit-identical to the Mako furniture, M_MAKO_Bone mix 0.22)."""
    import numpy as np
    os.makedirs(TEXDIR, exist_ok=True)
    path = os.path.join(TEXDIR, mat_name + ".png")
    src = bpy.data.images.load(os.path.join(bc.TEXTURES, src_name + ".png"), check_existing=False)
    if src.size[0] != size:
        src.scale(size, size)
    px = np.array(src.pixels[:], dtype=np.float32).reshape(size, size, 4)[..., :3]
    bpy.data.images.remove(src)
    lin = _srgb_to_lin(px)
    if normalize:
        n = np.clip(lin.mean(axis=2) / np.percentile(lin.mean(axis=2), 99.5), 0.0, 1.0)[..., None]
        t = 1.0 - mix * (1.0 - n)
    else:
        t = (1.0 - mix) + mix * lin
    out = np.ones((size, size, 4), np.float32)
    out[..., :3] = _lin_to_srgb(np.asarray(color[:3], np.float32) * t)
    img = bpy.data.images.new("_" + mat_name, size, size, alpha=False)
    img.pixels = out.ravel()
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    im = bpy.data.images.load(path, check_existing=True)
    im.name = mat_name
    im.colorspace_settings.name = "sRGB"
    return im


def gmat(name, color, rough, metal=0.0, tex=None, mix=0.0, coat=0.0, alpha=1.0, emission=None, strength=0.0,
         normalize=True):
    """Principled material that maps 1:1 to glTF: flat palette colour (baseColorFactor), or a baked albedo texture
    (palette x detail) wired straight into Base Color (baseColorTexture, factor 1, no Mapping node so no
    KHR_texture_transform). Clearcoat / emissive_strength / alpha BLEND extensions where used."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    col4 = (*color[:3], 1.0)
    bc._set_input(p, "Base Color", col4)
    bc._set_input(p, "Roughness", rough)
    bc._set_input(p, "Metallic", metal)
    if coat:
        bc._set_input(p, ["Coat Weight", "Clearcoat"], coat)
    if emission is not None:
        bc._set_input(p, ["Emission Color", "Emission"], (*emission[:3], 1.0))
        bc._set_input(p, "Emission Strength", strength)
    if alpha < 1.0:
        bc._set_input(p, "Alpha", alpha)
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:  # noqa: BLE001
            pass
    if tex:
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = bake_albedo(name, tex, color, mix, normalize)
        ti.location = (-400, 200)
        nt.links.new(ti.outputs["Color"], p.inputs["Base Color"])
    # closed solids + one-sided decals (reticle faces the eye, glint faces forward) -> glTF doubleSided false
    mat.use_backface_culling = True
    mat.diffuse_color = col4
    return mat


def make_materials():
    import glob
    for f in glob.glob(os.path.join(TEXDIR, "*.png")):       # no stale bakes from older material layouts
        os.remove(f)
    M = {}
    M["graphite"] = gmat("M_ATT_Graphite", (0.030, 0.033, 0.040), 0.50, 0.25, "worn_paint", 0.30)
    # bone: the palette token baked exactly like M_MAKO_Bone (mako_lib.bake_tint, worn_paint mix 0.22, 6 repeats/m)
    M["bone"] = gmat("M_ATT_Bone", (0.55, 0.52, 0.46), 0.60, 0.0, "worn_paint", 0.22, normalize=False)
    M["gunmetal"] = gmat("M_ATT_Gunmetal", (0.11, 0.115, 0.12), 0.35, 0.85, "brushed_metal", 0.25)
    M["rubber"] = gmat("M_ATT_Rubber", (0.035, 0.037, 0.045), 0.85)
    M["dark"] = gmat("M_ATT_Dark", (0.016, 0.017, 0.020), 0.75)
    # hood / tunnel lining: a dark graphite with a little sheen (pure M_ATT_Dark made the holo window a black tunnel)
    M["lining"] = gmat("M_ATT_Lining", (0.045, 0.049, 0.058), 0.50, 0.15)
    # coated lens glass, one material per lens ROLE so the engine can bind a scope view / glint shader per node:
    # ocular (eyepiece, faces the eye) and objective (front). Dark blue: brighter values read as a toy blue.
    M["ocular"] = gmat("M_ATT_LensOcular", (0.0050, 0.0150, 0.0480), 0.10, 0.0, coat=1.0)
    M["objective"] = gmat("M_ATT_LensObjective", (0.0050, 0.0150, 0.0480), 0.10, 0.0, coat=1.0)
    # objective lenses deep in a sunshade/hood get almost no key light: a brighter coated blue keeps the glass
    # (and the sniper glint) readable from the front instead of a black hole
    M["lensdeep"] = gmat("M_ATT_LensObjectiveDeep", (0.020, 0.060, 0.170), 0.12, 0.0, coat=1.0)
    M["display"] = gmat("M_ATT_Display", (0.004, 0.005, 0.007), 0.05, 0.2, coat=1.0)
    # anti-reflection coated window: a weak coat so the eye-side reflection (stock, cheek) does not ghost the view
    M["reflex"] = gmat("M_ATT_ReflexGlass", (0.03, 0.07, 0.09), 0.03, 0.0, coat=0.35, alpha=0.30)
    # ADS reticles (one-sided, face the eye) and third-person glints (one-sided, face forward): same ice token
    M["ice"] = gmat("M_ATT_IceReticle", (0.45, 0.85, 1.0), 0.30, emission=(0.45, 0.85, 1.0), strength=1.6)
    M["glint"] = gmat("M_ATT_IceGlint", (0.45, 0.85, 1.0), 0.30, emission=(0.45, 0.85, 1.0), strength=2.2)
    # ice paint (not emissive): a deeper ice than the glow token so the thin ring stays ice-blue, not white
    M["icepaint"] = gmat("M_ATT_IcePaint", (0.12, 0.50, 0.72), 0.40)
    M["germanium"] = gmat("M_ATT_Germanium", (0.045, 0.024, 0.006), 0.06, 0.55, coat=1.0)
    M["amber"] = gmat("M_ATT_AmberGlow", (1.0, 0.50, 0.08), 0.30, emission=(1.0, 0.42, 0.05), strength=3.0)
    M["testrail"] = gmat("_M_TestRail", (0.16, 0.17, 0.19), 0.45, 0.5)
    M["testbase"] = gmat("_M_TestBase", (0.06, 0.065, 0.075), 0.55, 0.2)
    return M


def uv_density(obj, tile_m=TILE_M):
    """Rescale the (smart-projected) UVs so one texture repeat = tile_m metres of surface on every optic."""
    me = obj.data
    uv = me.uv_layers.active.data
    a3 = a2 = 0.0
    for p in me.polygons:
        a3 += p.area
        pts = [uv[li].uv for li in p.loop_indices]
        s = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            s += x0 * y1 - x1 * y0
        a2 += abs(s) / 2
    if a2 <= 0:
        return
    k = math.sqrt(a3 / a2) / tile_m
    for d in uv:
        d.uv = d.uv * k


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
    # skeletonised riser: flared pedestal in side view (lifts the sight line into the 0.04-0.075 band),
    # slightly tapered in front view, one big lightening window through it
    riser = prism(P + "_Riser", [(-0.0170, 0.0045), (0.0170, 0.0045), (0.0170, 0.0085), (0.0205, 0.0172),
                                 (0.0205, 0.0242), (-0.0230, 0.0242), (-0.0230, 0.0172), (-0.0170, 0.0085)],
                  "X", -0.0145, 0.0145, g, col)
    cut(riser, prism("_c", [(-0.0145, 0.0030), (0.0145, 0.0030), (0.0124, 0.0260), (-0.0124, 0.0260)], "Y",
                     -0.04, 0.04), op="INTERSECT")
    cut(riser, prism("_c", rrect(-0.0010, 0.0158, 0.0118, 0.0040, 0.0036, 4), "X", -0.02, 0.02), transfer_mat=dk)
    bevel(riser, 0.0010, 2)
    body.append(riser)

    # sight housing: low rear deck + forward lens shroud, side profile x front-view rounded top
    # (the front corner sits 2 mm under the window floor z 0.0385: a coincident corner left a z-fighting sliver)
    side = [(-0.0240, 0.0236), (0.0215, 0.0236), (0.0215, 0.0335), (0.0185, 0.0365), (-0.0010, 0.0365),
            (-0.0040, 0.0400), (-0.0060, 0.0635), (-0.0090, 0.0665), (-0.0165, 0.0665), (-0.0195, 0.0640),
            (-0.0250, 0.0365), (-0.0250, 0.0290)]
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
    # ADS reticle (faces the eye) sized for the eye relief: a DOT_MOA dot; third-person glint (faces forward)
    ER = EYE_RELIEF["optic_reddot"]
    dot = decal(P + "_RetDot", (0.0, yc + 0.00065, SL), 0.0, ER * math.tan(DOT_MOA / 2 * MOA), +1, n=12,
                mat=M["ice"], col=col)
    glint = decal(P + "_GlintDot", (0.0, yc - 0.00065, SL), 0.0, 0.0009, -1, n=12, mat=M["glint"], col=col)
    for o in (dot, glint):
        rotate_x(o, -10, (yc, SL))
    ads = (0.0, yc + 0.0007, SL)
    return dict(body=body, glass=[glass], reticle=[dot], glint=[glint], ads=ads, clamps=[(-0.0170, 0.0170)],
                eye_relief=ER, magnification=1.0, recommended_for=["MAKO"], default_for=[],
                kind="mini reflex", reticle_desc="%d MOA dot" % DOT_MOA)


def lobes_profile(cy, cz, d, r, n=10):
    """Outline (y, z) of two overlapping circles (centres cy -/+ d) = a 'butterfly' thumb lever, CCW."""
    h = math.sqrt(max(r * r - d * d, 1e-12))
    t0 = math.atan2(h, d)
    pts = []
    for i in range(n + 1):                 # circle A (rear lobe, -d) from the top intersection, round the far side
        a = t0 + (2 * math.pi - 2 * t0) * i / n
        pts.append((cy - d + r * math.cos(a), cz + r * math.sin(a)))
    for i in range(1, n):                  # circle B (+d) from the bottom intersection round to the top
        a = -(math.pi - t0) + (2 * math.pi - 2 * t0) * i / n
        pts.append((cy + d + r * math.cos(a), cz + r * math.sin(a)))
    return pts


def loft_y(name, ptsA, yA, ptsB, yB, mat=None, col=None):
    """Closed solid between two (x, z) outlines with the same point count at yA and yB (a frustum cutter)."""
    bm = bmesh.new()
    a = [bm.verts.new((u, yA, v)) for u, v in ptsA]
    b = [bm.verts.new((u, yB, v)) for u, v in ptsB]
    n = len(ptsA)
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _new_obj(name, bm, mat, col)


def build_holo(col, M):
    """Bone box holographic sight (Mako default, DIRECTION_LOG item 2 / mako v09): a tall faceted hood with a
    heavy chamfered brow over the window, slanted upper flanks, a dark window bezel, a low button deck with a
    recessed tray in front of the window, rubber side buttons, dark mount bars on both sides (butterfly QD lever on
    the shooter's LEFT, +X, the side v09 shows; cross-bolt head + windage / elevation adjusters on the RIGHT, -X)
    and a bone battery door with a thumb latch on the rear face."""
    P = "ATT_optic_holo"
    g, gm, rb, bo, ln = M["graphite"], M["gunmetal"], M["rubber"], M["bone"], M["lining"]
    SL = 0.0450                       # sight line (window centre) above the rail top
    HW = 0.0235                       # half width of the bone shell at its base
    HWT = 0.0138                      # half width where the slanted flanks meet the top
    ZS = 0.0410                       # flanks start to slant inward above this height
    YF = -0.0230                      # hood front face
    YR = 0.0310                       # hood rear face (54 mm hood, v09 proportions)
    YD = -0.0560                      # deck front
    ZB = 0.0080                       # bottom of the bone shell (dark base plate below it)
    ZT = 0.0710                       # hood top (2 mm taller than before: room for a solid brow over the window)
    ZD = 0.0270                       # deck top
    WHW, WHH = 0.0172, 0.01575        # window tunnel half width / half height (= bezel outer)
    WZ = 0.04425                      # window centre (z 0.0285-0.060): the sight line sits 0.75 mm above it
    FIN = 0.0012                      # front bezel inner lip (clear aperture 32 x 29.1 mm; was a 3.4 mm inset)
    BRH, BRW = 0.0070, 0.0095         # brow chamfer: drop at the front face / run back over the top
    # bone over the window at the front face = (ZT - BRH) - (WZ + WHH + 0.0002) = 3.8 mm (the review asked >= 3)
    assert (ZT - BRH) - (WZ + WHH + 0.0002) >= 0.0030
    body = []
    # rail clamp + dark base plate under the whole shell (v09: dark band under the bone body)
    body.append(rail_clamp(P + "_Clamp", -0.0450, 0.0270, W=0.036, top=0.0045, mat=g, col=col, seg=2))
    plate = prism(P + "_BasePlate", [(YD + 0.0015, 0.0015), (YR - 0.0010, 0.0015), (YR - 0.0010, ZB + 0.0006),
                                     (YD + 0.0015, ZB + 0.0006)], "X", -HW - 0.0006, HW + 0.0006, g, col)
    bevel(plate, 0.0012, 2)
    body.append(plate)

    # bone shell: side profile (deck + hood with heavy brow chamfer) x front section (slanted upper flanks)
    side = [(YD, ZB), (YR, ZB), (YR, ZT - 0.0065), (YR - 0.0050, ZT), (YF + BRW, ZT), (YF, ZT - BRH),
            (YF, ZD), (YD + 0.0070, ZD), (YD, ZD - 0.0070)]
    sh = prism(P + "_Shell", side, "X", -HW, HW, bo, col)
    sec = [(-HW, ZB - 0.002), (HW, ZB - 0.002), (HW, ZS), (HWT, ZT + 0.0015), (-HWT, ZT + 0.0015), (-HW, ZS)]
    cut(sh, prism("_c", sec, "Y", -0.08, 0.08), op="INTERSECT")
    # chamfer the hood's front vertical edges (above the deck) and the rear vertical edges
    for s in (1, -1):
        c = 0.0068
        cut(sh, prism("_c", [(s * (HW + 0.001), YF - 0.001), (s * (HW + 0.001), YF + c), (s * (HW - c), YF - 0.001)],
                      "Z", ZD + 0.0004, 0.09))
        c = 0.0025
        cut(sh, prism("_c", [(s * (HW + 0.001), YR + 0.001), (s * (HW - c), YR + 0.001), (s * (HW + 0.001), YR - c)],
                      "Z", 0.0, 0.09))
    # window tunnel through the hood (dark graphite lining), with a 45 deg bone flare at the rear opening so the
    # eye-side frame reads as a bevel instead of a second thick dark frame
    WC = (1.5, 1.5, 1, 1)             # window corner radii: rounder at the top (follows the slanted flanks)
    cut(sh, prism("_c", rrect(0.0, WZ, WHW, WHH, 0.0050, 4, corners=WC), "Y", -0.08, 0.08), transfer_mat=ln)
    FL = 0.0025
    cut(sh, loft_y("_c", rrect(0.0, WZ, WHW - 0.0001, WHH - 0.0001, 0.0050, 4, corners=WC), YR - FL - 0.0001,
                   rrect(0.0, WZ, WHW + FL + 0.001, WHH + FL + 0.001, 0.0050 + FL, 4, corners=WC), YR + 0.001))
    # deck: recessed button tray between two side walls, running back to the hood face
    cut(sh, prism("_c", rrect(0.0, (YD + 0.0085 + YF) / 2, HW - 0.0062, (YF - YD - 0.0085) / 2, 0.0030, 3,
                              corners=(0, 0, 1, 1)), "Z", ZD - 0.0045, ZD + 0.010))
    bevel(sh, 0.0014, 2)
    body.append(sh)
    # front bezel: thick-looking dark frame (v09) with a thin 2 mm inner lip so the clear aperture stays big
    y0, y1 = YF + 0.0012, YF + 0.0062
    fr = prism(P + "_WinFrame", rrect(0.0, WZ, WHW + 0.0002, WHH + 0.0002, 0.0051, 4, corners=WC), "Y", y0, y1,
               rb, col)
    cut(fr, prism("_c", rrect(0.0, WZ, WHW - FIN, WHH - FIN, 0.0035, 4, corners=WC), "Y", y0 - 0.01, y1 + 0.01))
    bevel(fr, 0.0007, 1)
    body.append(fr)
    # rear: only a thin rubber gasket lip (1 mm) at the bottom of the flare
    y0, y1 = YR - FL - 0.0032, YR - FL - 0.0004
    fr = prism(P + "_WinGasket", rrect(0.0, WZ, WHW + 0.0002, WHH + 0.0002, 0.0051, 4, corners=WC), "Y", y0, y1,
               rb, col)
    cut(fr, prism("_c", rrect(0.0, WZ, WHW - 0.0010, WHH - 0.0010, 0.0042, 4, corners=WC), "Y", y0 - 0.01,
                  y1 + 0.01))
    bevel(fr, 0.0004, 1)
    body.append(fr)
    # rear battery door: a bone panel standing 0.6 mm proud of the rear face (its edge reads as the door seam) with
    # a small rubber thumb latch (was a flat black rectangle that read as a dead screen in ADS)
    door = prism(P + "_BatteryDoor", rrect(0.0, 0.0160, 0.0122, 0.0050, 0.0022, 3), "Y", YR - 0.0004, YR + 0.0006,
                 bo, col)
    bevel(door, 0.0003, 1)
    body.append(door)
    latch = prism(P + "_DoorLatch", rrect(0.0, 0.0118, 0.0036, 0.0011, 0.0008, 2), "Y", YR + 0.0002, YR + 0.0019,
                  rb, col)
    bevel(latch, 0.0004, 1)
    body.append(latch)

    # deck buttons in the tray: one big flat main button + a small one (v09)
    for (bx, by, br) in ((-0.0068, YD + 0.0160, 0.0055), (0.0085, YD + 0.0135, 0.0036)):
        b = lathe(P + "_BtnTop", [(0.0, ZD - 0.0047), (br, ZD - 0.0047), (br, ZD - 0.0018), (br - 0.0015, ZD - 0.0004),
                                  (0.0, ZD - 0.0004)], "Z", (bx, by, 0), steps=16, mats=rb, col=col)
        smooth(b, 35)
        body.append(b)
    # rubber side buttons with a round recess on the deck flanks (both sides)
    for s in (1, -1):
        sb = prism(P + "_BtnSide", rrect(YD + 0.0135, 0.0175, 0.0070, 0.0052, 0.0022, 2), "X",
                   s * (HW - 0.0005), s * (HW + 0.0028), rb, col)
        cut(sb, lathe("_c", [(0.0, s * (HW + 0.0016)), (0.0021, s * (HW + 0.0016)), (0.0021, s * (HW + 0.01)),
                             (0.0, s * (HW + 0.01))], "X", (0, YD + 0.0135, 0.0175), steps=12), transfer_mat=M["dark"])
        bevel(sb, 0.0007, 1)
        body.append(sb)
    # mount bars on both sides under the hood (v09 shows the +X one): cross-bolt boss (+X) / bolt head (-X) at the
    # front, butterfly QD lever on +X at the rear
    mx0, mx1 = HW - 0.0004, HW + 0.0032
    bar = [(YF - 0.0040, 0.0022), (YR - 0.0035, 0.0022), (YR - 0.0035, 0.0125), (YR - 0.0075, 0.0160),
           (YF + 0.0000, 0.0160), (YF - 0.0040, 0.0120)]
    for s in (1, -1):
        mb = prism(P + "_MountBar", bar, "X", s * mx0, s * mx1, g, col)
        bevel(mb, 0.0009, 2)
        body.append(mb)
    boss = lathe(P + "_BoltBoss", [(0.0024, mx1 - 0.0002), (0.0048, mx1 - 0.0002), (0.0048, mx1 + 0.0016),
                                   (0.0040, mx1 + 0.0024), (0.0024, mx1 + 0.0024), (0.0024, mx1 + 0.0010)],
                 "X", (0, YF + 0.0060, 0.0085), steps=16, mats=M["dark"], col=col)
    smooth(boss, 30)
    body.append(boss)
    body.append(hex_nut(P + "_BoltHead", -mx1, YF + 0.0060, 0.0085, -1, gm, col, r=0.0038, t=0.0020))
    lv = prism(P + "_QDLever", lobes_profile(YR - 0.0135, 0.0175, 0.0040, 0.0058, n=10), "X", HW - 0.0003,
               mx1 + 0.0042, g, col)
    bevel(lv, 0.0010, 2)
    body.append(lv)
    body.append(screw_head(P + "_QDHub", (mx1 + 0.0042, YR - 0.0135, 0.0175), "X", 1, 0.0026, 0.0012, gm, col,
                           steps=12, slot=False))
    # windage / elevation adjusters on the shooter's right (-X) hood flank (breaks up the bone slab)
    for ya in (-0.0050, 0.0110):
        body.append(screw_head(P + "_Adjuster", (-HW, ya, 0.0285), "X", -1, 0.0036, 0.0015, gm, col, steps=14))
    # cross-bolt nut on the right (-X) on the clamp jaw, small nut on the left jaw
    body.append(hex_nut(P + "_ClampBolt", -0.0180, -0.0090, -0.0020, -1, gm, col, r=0.0032, t=0.0022))
    body.append(hex_nut(P + "_ClampNut", 0.0180, -0.0090, -0.0020, 1, gm, col, r=0.0032, t=0.0022))

    yc = YF + 0.0095                  # glass just behind the front bezel so the glint reads at oblique angles (v09)
    glass = prism(P + "_Glass", rrect(0.0, WZ, WHW + 0.0004, WHH + 0.0004, 0.0052, 4, corners=WC), "Y", yc - 0.00075,
                  yc + 0.00075, M["reflex"], col)
    rotate_x(glass, -8, (yc, SL))
    smooth(glass, 30)
    # ADS reticle on the glass rear (faces the eye), sized for the eye relief: DOT_MOA dot + RING_MOA ring
    ER = EYE_RELIEF["optic_holo"]
    yr = yc + 0.00080
    rd = ER * math.tan(DOT_MOA / 2 * MOA)
    rr = ER * math.tan(RING_MOA / 2 * MOA)
    rw = ER * math.tan(RING_LINE_MOA / 2 * MOA)
    dot = decal(P + "_RetDot", (0.0, yr, SL), 0.0, rd, +1, n=12, mat=M["ice"], col=col)
    ring = decal(P + "_RetRing", (0.0, yr, SL), rr - rw, rr + rw, +1, n=40, mat=M["ice"], col=col)
    # third-person glint: one soft ice dot on the glass front (faces forward), like v09
    glint = decal(P + "_GlintDot", (0.0, yc - 0.00080, SL), 0.0, 0.0011, -1, n=12, mat=M["glint"], col=col)
    for o in (dot, ring, glint):
        rotate_x(o, -8, (yc, SL))
    ads = (0.0, yr + 0.0001, SL)
    return dict(body=body, glass=[glass], reticle=[dot, ring], glint=[glint], ads=ads, clamps=[(-0.0450, 0.0270)],
                eye_relief=ER, magnification=1.0, recommended_for=["MAKO"], default_for=["MAKO"],
                kind="box holographic", reticle_desc="%d MOA dot + %d MOA ring" % (DOT_MOA, RING_MOA))


def build_3x(col, M):
    """Compact 3x prism sight: squat prism housing with a sloped brow, flared knurled objective bell, short
    rubber-ringed eyepiece, capped elevation / windage turrets + illumination dial, integral QD mount."""
    P = "ATT_optic_3x"
    g, gm, rb, dk = M["graphite"], M["gunmetal"], M["rubber"], M["dark"]
    AX = 0.0500
    body = []
    body.append(rail_clamp(P + "_Clamp", -0.0280, 0.0280, W=0.034, top=0.0060, mat=g, col=col))
    neck = prism(P + "_Neck", [(-0.0265, 0.0055), (0.0265, 0.0055), (0.0265, 0.0165), (0.0225, 0.0215),
                               (-0.0225, 0.0215), (-0.0265, 0.0165)], "X", -0.0140, 0.0140, g, col)
    cut(neck, prism("_c", rrect(0.0, 0.0135, 0.0130, 0.0032, 0.0030, 4), "X", -0.02, 0.02), transfer_mat=dk)
    bevel(neck, 0.0010, 2)
    body.append(neck)

    # prism housing: rounded front section x side profile with a sloped brow toward the objective
    hs = prism(P + "_Housing", rrect(0.0, 0.0475, 0.0215, 0.0275, 0.0090, 1, corners=(1, 1, 0.45, 0.45)),
               "Y", -0.0250, 0.0240, g, col)
    cut(hs, prism("_c", [(-0.0250, 0.0150), (0.0240, 0.0150), (0.0240, 0.0705), (0.0195, 0.0750),
                         (-0.0110, 0.0750), (-0.0250, 0.0625)], "X", -0.03, 0.03), op="INTERSECT")
    for s in (1, -1):             # side panel recesses (both sides), graphite: a dark fill read as a small LCD
        cut(hs, prism("_c", rrect(0.0040, 0.0325, 0.0165, 0.0058, 0.0024, 3), "X", s * 0.0208, s * 0.030))
    bevel(hs, 0.0016, 2)
    body.append(hs)
    for s in (1, -1):             # two grip ribs in each recess
        for zr in (0.0302, 0.0348):
            rib = prism(P + "_Rib", rrect(0.0040, zr, 0.0138, 0.0007, 0.0005, 1), "X", s * 0.0204, s * 0.0214, g, col)
            bevel(rib, 0.0003, 1)
            body.append(rib)

    def cap_turret(name, axis, sign, base, r1, length, cap_r, c, steps=28, knurl=0.0007):
        h = lambda d: base + sign * d  # noqa: E731
        # starts with a pole at the base: the turret is a closed solid (its floor is buried in the housing)
        pr = [(0.0, h(0.0)), (r1 - 0.0015, h(0.0)), (r1 - 0.0015, h(0.0018)), (r1, h(0.0022), "k"),
              (r1, h(length - 0.0030), "k"), (r1 - 0.0012, h(length - 0.0018)), (cap_r, h(length - 0.0018)),
              (cap_r - 0.0005, h(length + 0.0008)), (0.0, h(length + 0.0008))]
        ob = lathe(name, pr, axis, c, steps=steps, mats=g, knurl=knurl, closed=False, col=col)
        smooth(ob, 22)
        return ob

    # smooth capped turrets (a prism sight has caps, not exposed target knobs) + knurled illumination dial
    body.append(cap_turret(P + "_TurretElev", "Z", 1, 0.0742, 0.0092, 0.0090, 0.0064, (0.0, 0.0060, 0), steps=24,
                           knurl=0.0))
    body.append(cap_turret(P + "_TurretWind", "X", -1, -0.0206, 0.0090, 0.0088, 0.0062, (0, 0.0040, AX), steps=24,
                           knurl=0.0))
    body.append(cap_turret(P + "_IllumDial", "X", 1, 0.0206, 0.0108, 0.0070, 0.0050, (0, 0.0040, AX),
                           steps=28, knurl=0.0007))

    # objective bell (front) and eyepiece (rear): mats 0 graphite, 1 rubber, 2 dark
    obj = lathe(P + "_Objective", [(0.0, -0.0596), (0.0161, -0.0596), (0.0161, -0.0668), (0.0183, -0.0668),
                                   (0.0196, -0.0655), (0.0196, -0.0640, "k"), (0.0196, -0.0480, "k"),
                                   (0.0190, -0.0458), (0.0160, -0.0335), (0.0160, -0.0220), (0.0, -0.0220)],
                "Y", (0, 0, AX), steps=32, mats=[g, rb, dk], seg_mat=[2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                knurl=0.0007, col=col)
    smooth(obj, 25)
    body.append(obj)
    eye = lathe(P + "_Eyepiece", [(0.0, 0.0200), (0.0138, 0.0200), (0.0138, 0.0280), (0.0158, 0.0298),
                                  (0.0158, 0.0392), (0.0166, 0.0410), (0.0180, 0.0545), (0.0172, 0.0568),
                                  (0.0130, 0.0568), (0.0130, 0.0538), (0.0, 0.0538)],
                "Y", (0, 0, AX), steps=32, mats=[g, rb, dk], seg_mat=[0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 0],
                col=col)
    smooth(eye, 30)
    body.append(eye)

    # QD throw lever on the right (-X), cross-bolt nut on the left
    lev = prism(P + "_Lever", [(-0.0170, -0.0030), (0.0180, -0.0038), (0.0215, 0.0), (0.0180, 0.0038),
                               (-0.0170, 0.0030), (-0.0185, 0.0)], "X", -0.0203, -0.0168, gm, col)
    bevel(lev, 0.0007, 2)
    body.append(lev)
    body.append(knob_x(P + "_LeverPivot", -0.0203, 0.0180, 0.0, -1, 0.0040, 0.0012, gm, col, steps=12,
                       knurl=0.0))
    body.append(hex_nut(P + "_ClampNut", 0.0170, 0.0180, -0.0001, 1, gm, col, r=0.0042, t=0.0026))

    # objective / ocular lenses are separate nodes with their own materials (scope view + glint shader binding)
    lens_o = lathe(P + "_LensObj", [(0.0, -0.0614), (0.0080, -0.0611), (0.0159, -0.0604), (0.0159, -0.0598),
                                    (0.0, -0.0598)], "Y", (0, 0, AX), steps=32, mats=M["objective"], col=col)
    lens_e = lathe(P + "_LensEye", [(0.0, 0.0551), (0.0080, 0.0548), (0.0129, 0.0543), (0.0129, 0.0540),
                                    (0.0, 0.0540)], "Y", (0, 0, AX), steps=32, mats=M["ocular"], col=col)
    for o in (lens_o, lens_e):
        smooth(o, 40)
    # illuminated reticle centre on the ocular (faces the eye): reads from behind in third person / hip; the game
    # hides it when it draws its scope overlay on the Ocular node
    dot = decal(P + "_RetDot", (0.0, 0.05520, AX), 0.0, 0.0005, +1, n=12, mat=M["ice"], col=col)
    ads = (0.0, 0.0568, AX)
    return dict(body=body, objective=[lens_o], ocular=[lens_e], reticle=[dot], ads=ads, clamps=[(-0.0280, 0.0280)],
                eye_relief=EYE_RELIEF["optic_3x"], magnification=3.0, recommended_for=["MAKO", "WARDEN"],
                default_for=[], kind="compact prism 3x",
                reticle_desc="engine scope overlay on the Ocular node; the Reticle node is the illuminated centre "
                             "for third-person views")


def build_sniper(col, M):
    """5-25x long-range scope (Warden default, art/concepts/warden/BRIEF.md 4.4): 0.38 m long, 68 mm objective
    bell (stylised 50 mm objective), 30 mm-class tube, knurled power ring, chunky turret saddle with elevation
    (top) / windage (shooter's right, -X) / side-focus (+X) turrets, thin ice-PAINTED ring + sunshade at the
    front, two chunky rings with their own rail clamps. Axis 0.0405 above the rail top (Warden z 0.178)."""
    P = "ATT_optic_sniper"
    g, gm, rb, dk, ic = M["graphite"], M["gunmetal"], M["rubber"], M["dark"], M["icepaint"]
    AX = 0.0405                      # scope axis above the rail top
    RY = 0.0600                      # ring centres at +-RY (Warden y -0.020 / -0.140)
    body = []

    # one lathe for the whole body: eyecup -> eyepiece -> knurled power ring -> tube -> bell -> ice ring ->
    # sunshade (hollow, dark inside) -> objective seat. mats: 0 graphite, 1 rubber, 2 dark, 3 ice paint
    prof = [(0.0, 0.1395), (0.0198, 0.1395), (0.0198, 0.1450), (0.0236, 0.1450), (0.0252, 0.1434),
            (0.0252, 0.1300), (0.0247, 0.1288), (0.0247, 0.1125), (0.0262, 0.1112, "k"), (0.0262, 0.0962, "k"),
            (0.0232, 0.0935), (0.0232, 0.0790), (0.0185, 0.0700), (0.0185, -0.0850), (0.0340, -0.1320),
            (0.0340, -0.1755), (0.0355, -0.1768), (0.0355, -0.1825), (0.0330, -0.1838), (0.0330, -0.2335),
            (0.0316, -0.2350), (0.0298, -0.2350), (0.0298, -0.1758), (0.0, -0.1758)]
    seg = [2, 2, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 0, 2, 2]
    tube = lathe(P + "_Tube", prof, "Y", (0, 0, AX), steps=32, mats=[g, rb, dk, ic], seg_mat=seg, knurl=0.0009,
                 col=col)
    smooth(tube, 25)
    body.append(tube)
    # magnification throw-lever fin on the power ring, shooter's right (-X)
    fin = prism(P + "_PowerFin", [(0.0975, -0.0030), (0.1100, -0.0030), (0.1100, 0.0030), (0.0975, 0.0030)], "X",
                -0.0335, -0.0240, g, col)
    translate(fin, (0, 0, AX))
    bevel(fin, 0.0009, 1)
    body.append(fin)

    # turret saddle (brief: 0.044 x 0.062 x 0.044, bevel 0.008)
    sad = box(P + "_Saddle", -0.0220, 0.0220, -0.0310, 0.0310, AX - 0.0220, AX + 0.0220, g, col)
    bevel(sad, 0.0080, 3, harden=True)
    body.append(sad)

    def turret(name, axis, sign, base, r0, r1, length, cap_r, steps):
        """Knurled turret: collar r0, knurled cap r1, small stepped top cap. Closed solid (floor inside the saddle)."""
        h = lambda d: base + sign * d  # noqa: E731
        pr = [(0.0, h(0.0)), (r0, h(0.0)), (r0, h(0.0055)), (r1, h(0.0062), "k"), (r1, h(length - 0.0045), "k"),
              (r1 - 0.0016, h(length - 0.0028)), (cap_r, h(length - 0.0028)), (cap_r - 0.0006, h(length + 0.0008)),
              (0.0, h(length + 0.0008))]
        c = (0, 0, AX) if axis == "X" else (0, 0, 0)
        ob = lathe(name, pr, axis, c, steps=steps, mats=g, knurl=0.0009, closed=False, col=col)
        smooth(ob, 22)
        return ob

    body.append(turret(P + "_TurretElev", "Z", 1, AX + 0.0200, 0.0150, 0.0190, 0.0292, 0.0118, 28))
    body.append(turret(P + "_TurretWind", "X", -1, -0.0200, 0.0150, 0.0186, 0.0270, 0.0112, 28))
    # side focus / parallax knob on the left (+X): wide flat knurled wheel + hub (no ice on it)
    sf = lathe(P + "_SideFocus", [(0.0, 0.0200), (0.0140, 0.0200), (0.0140, 0.0225), (0.0172, 0.0232, "k"), (0.0172, 0.0352, "k"),
                                  (0.0158, 0.0368), (0.0085, 0.0368), (0.0079, 0.0400),
                                  (0.0, 0.0400)], "X", (0, 0, AX), steps=28, mats=g, knurl=0.0008, closed=False,
               col=col)
    smooth(sf, 22)
    body.append(sf)

    # two chunky rings (cap + waisted base, brief: ring r 0.027 x 0.018 + base 0.034 wide), each on its own clamp
    for k, ry in enumerate((-RY, RY)):
        R = 0.0262
        out = [(R * math.cos(math.radians(a)), AX + R * math.sin(math.radians(a))) for a in range(0, 181, 15)]
        out += [(-R, AX - 0.0075), (-0.0170, AX - 0.0215), (-0.0170, 0.0055), (0.0170, 0.0055),
                (0.0170, AX - 0.0215), (R, AX - 0.0075)]
        # solid ring: the tube runs through it (the intersection line reads as the bore, saves ~250 tris a ring)
        ring = prism(P + "_Ring%d" % k, out, "Y", ry - 0.0095, ry + 0.0095, g, col)
        for s in (1, -1):        # cap split line on both flanks
            cut(ring, box("_c", s * 0.0240, s * 0.0300, ry - 0.0120, ry + 0.0120, AX - 0.0007, AX + 0.0007),
                transfer_mat=dk)
        bevel(ring, 0.0014, 2)
        body.append(ring)
        body.append(rail_clamp(P + "_Clamp%d" % k, ry - 0.0150, ry + 0.0150, W=0.036, top=0.0062, mat=g, col=col))
        # cross-bolt: big nut on the left (+X, brief), bolt head on the right
        body.append(hex_nut(P + "_ClampNut%d" % k, 0.0180, ry, -0.0012, 1, gm, col, r=0.0050, t=0.0034))
        body.append(hex_nut(P + "_ClampBolt%d" % k, -0.0180, ry, -0.0012, -1, gm, col, r=0.0042, t=0.0024))
        for s in (1, -1):        # cap screw heads above the split, both flanks
            body.append(screw_head(P + "_CapScrew", (s * 0.0257, ry, AX + 0.0040), "X", s, 0.0022, 0.0010, gm,
                                   col, steps=8, slot=False))

    lens_o = lathe(P + "_LensObj", [(0.0, -0.1792), (0.0160, -0.1788), (0.0297, -0.1779), (0.0297, -0.1762),
                                    (0.0, -0.1762)], "Y", (0, 0, AX), steps=32, mats=M["lensdeep"], col=col)
    lens_e = lathe(P + "_LensEye", [(0.0, 0.1407), (0.0197, 0.1400), (0.0197, 0.1397), (0.0, 0.1397)],
                   "Y", (0, 0, AX), steps=32, mats=M["ocular"], col=col)
    for o in (lens_o, lens_e):
        smooth(o, 40)
    ads = (0.0, 0.1450, AX)
    return dict(body=body, objective=[lens_o], ocular=[lens_e], ads=ads,
                clamps=[(-RY - 0.0150, -RY + 0.0150), (RY - 0.0150, RY + 0.0150)],
                eye_relief=EYE_RELIEF["optic_sniper"], magnification="5-25", recommended_for=["WARDEN"],
                default_for=["WARDEN"], kind="5-25x long-range scope",
                reticle_desc="engine scope overlay on the Ocular node (no emissive: the ice ring is paint)")


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
    # lens retaining lip (dark) at the bottom of the hood bore, in FRONT of the lens and inside the 21.5 mm bore
    # (the old ring was wider than the bore and overlapped the lens: z-fighting)
    rr_ = lathe(P + "_LensRing", [(0.0168, -0.0729), (0.0213, -0.0729), (0.0213, -0.0745), (0.0168, -0.0745)],
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

    # germanium objective (behind the lip, inside the bore) and the rear display (inside the eyecup wall)
    lens_o = lathe(P + "_Germanium", [(0.0, -0.0732), (0.0110, -0.0729), (0.0205, -0.0723), (0.0205, -0.0710),
                                      (0.0, -0.0710)], "Y", (0, 0, AX), steps=32, mats=M["germanium"], col=col)
    lens_e = lathe(P + "_Display", [(0.0, 0.0728), (0.0133, 0.0726), (0.0133, 0.0715), (0.0, 0.0715)],
                   "Y", (0, 0, AX), steps=32, mats=M["display"], col=col)
    for o in (lens_o, lens_e):
        smooth(o, 40)
    led = lathe(P + "_StatusLED", [(0.0, 0.0612), (0.0015, 0.0612), (0.0015, 0.0628), (0.0010, 0.0638),
                                   (0.0, 0.0641)], "Y", (0.0185, 0, 0.0790), steps=12, mats=M["amber"], col=col)
    smooth(led, 60)
    ads = (0.0, 0.0918, AX)
    return dict(body=body, objective=[lens_o], display=[lens_e], status=[led], ads=ads, clamps=[(-0.0340, 0.0340)],
                eye_relief=EYE_RELIEF["optic_thermal"], magnification="2-8 thermal", recommended_for=["WARDEN"],
                default_for=[], kind="thermal scope",
                reticle_desc="engine thermal view + reticle on the Display node")


BUILDERS = {"optic_reddot": build_reddot, "optic_holo": build_holo, "optic_3x": build_3x,
            "optic_sniper": build_sniper, "optic_thermal": build_thermal}


# =========================================================================================== assembly
# builder dict key -> (node suffix, catalog role). Every role is its own child node so the engine can treat it on
# its own: Glass = reflex window pane, Objective / Ocular = lenses of magnified optics (glint shader / scope view),
# Display = the thermal's rear screen, Reticle = ADS reticle (faces the eye), Glint = third-person reticle glint
# (faces forward), StatusLight = the thermal's LED.
PART_KEYS = (("body", "Body", "body"), ("glass", "Glass", "window_glass"), ("objective", "Objective", "objective"),
             ("ocular", "Ocular", "ocular"), ("display", "Display", "display"), ("reticle", "Reticle", "reticle"),
             ("glint", "Glint", "glint"), ("status", "StatusLight", "status_light"))


def clean_degenerate(obj, dist=2e-6):
    """Collapse the zero-area slivers that bevel-after-boolean leaves behind (edges < 2 microns); the custom
    (hardened) normals of the surviving corners are kept."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    before = sum(1 for f in bm.faces if f.calc_area() < 1e-11)
    if before:
        bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges[:])
        after = sum(1 for f in bm.faces if f.calc_area() < 1e-11)
        bm.to_mesh(obj.data)
        print("  %s: degenerate faces %d -> %d" % (obj.name, before, after))
    bm.free()
    return obj


def finalize(oid, col, d):
    P = "ATT_" + oid
    root = empty(P, (0, 0, 0), col, size=0.03, kind="ARROWS")
    out = {}
    for dkey, key, _role in PART_KEYS:
        objs = d.get(dkey) or []
        if not objs:
            continue
        if "--debug" in ARGS:
            rows = sorted(((tri_count([o]), o.name) for o in objs), reverse=True)
            print("  parts of %s_%s:" % (P, key), ", ".join("%s=%d" % (n.replace(P + "_", ""), t)
                                                            for t, n in rows))
        for o in objs:
            apply_xform(o)
        j = bc.join(list(objs), P + "_" + key)
        clean_degenerate(j)
        bc.smart_uv(j)
        uv_density(j)
        j.parent = root
        out[key] = j
    ads = empty(P + "_SOCKET_ADS", d["ads"], col, parent=root, size=0.01)
    ads["eye_relief_m"] = d["eye_relief"]
    ads["note"] = "sight line at the rear of the reticle/eyepiece; camera eye point = +Y by eye_relief_m"
    ads["reticle"] = d.get("reticle_desc", "")
    meshes = list(out.values())
    mn, mx = bc.world_bounds(meshes)
    root["optic_id"] = oid
    root["category"] = "optic"
    root["mount"] = "picatinny top rail; origin = clamp contact centre on rail top"
    root["ads_height_m"] = round(d["ads"][2], 4)
    root["length_m"] = round(mx.y - mn.y, 4)
    root["magnification"] = str(d["magnification"])
    root["eye_relief_m"] = d["eye_relief"]
    for _dkey, key, role in PART_KEYS:          # node names per role (glTF extras), e.g. ocular_node
        if key in out:
            root[role + "_node"] = out[key].name
    return root, out, ads, (mn, mx)


def node_roles(oid, parts):
    """{role: node name or None} for the catalog."""
    return {role: (parts[key].name if key in parts else None) for _d, key, role in PART_KEYS}


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


CULL_MATS = ("M_ATT_IceReticle", "M_ATT_IceGlint")


def cycles_backface_cull(enable):
    """Cycles ignores material backface culling; the engine does not (glTF doubleSided false). For renders, the
    one-sided reticle / glint decals get a Backfacing -> Transparent mix so every render shows what the game shows
    (the eye never sees the glint, the front never sees the ADS reticle). Removed again before the .blend is saved
    (the exports are written before any render)."""
    for nm in CULL_MATS:
        m = bpy.data.materials.get(nm)
        if m is None:
            continue
        nt = m.node_tree
        out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        mix = nt.nodes.get("_cull_mix")
        if enable and mix is None:
            geo = nt.nodes.new("ShaderNodeNewGeometry")
            geo.name = "_cull_geo"
            tr = nt.nodes.new("ShaderNodeBsdfTransparent")
            tr.name = "_cull_tr"
            mix = nt.nodes.new("ShaderNodeMixShader")
            mix.name = "_cull_mix"
            nt.links.new(geo.outputs["Backfacing"], mix.inputs[0])
            nt.links.new(p.outputs[0], mix.inputs[1])
            nt.links.new(tr.outputs[0], mix.inputs[2])
            nt.links.new(mix.outputs[0], out.inputs["Surface"])
        elif not enable and mix is not None:
            nt.links.new(p.outputs[0], out.inputs["Surface"])
            for k in ("_cull_mix", "_cull_tr", "_cull_geo"):
                nt.nodes.remove(nt.nodes[k])


def ads_aperture(oid, r):
    """Clear sight picture of a 1x optic at the game's ADS FOV, measured by ray casts from the eye point against the
    optic body (mount space): the contiguous clear window around the sight line (up / down / left / right angles)
    as a fraction of the screen height / width (16:9), plus the clear fraction of the whole screen."""
    d = r["d"]
    body = r["parts"]["Body"]
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(body, dg)
    eye = Vector(d["ads"]) + Vector((0, d["eye_relief"], 0))
    vf = math.radians(GAME_VFOV / ZOOM[oid])
    tv = math.tan(vf / 2)
    th = tv * 16 / 9

    def clear(dx, dz):
        v = Vector((dx, -1.0, dz)).normalized()
        return bvh.ray_cast(eye, v, 2.0)[0] is None

    def edge(axis, sign):
        t = 0.0
        while t < 1.2:
            t += 0.002
            if not (clear(sign * t, 0.0) if axis == "x" else clear(0.0, sign * t)):
                return t
        return t
    up, down, left, right = edge("z", 1), edge("z", -1), edge("x", 1), edge("x", -1)
    n, ok = 0, 0
    for i in range(48):
        for j in range(27):
            n += 1
            ok += clear(th * (2 * (i + 0.5) / 48 - 1), tv * (2 * (j + 0.5) / 27 - 1))
    res = {"eye_m": [round(v, 4) for v in eye], "vfov_deg": round(GAME_VFOV / ZOOM[oid], 2),
           "window_deg": {"up": round(math.degrees(math.atan(up)), 2), "down": round(math.degrees(math.atan(down)), 2),
                          "left": round(math.degrees(math.atan(left)), 2),
                          "right": round(math.degrees(math.atan(right)), 2)},
           "window_frac_screen_h": round((up + down) / (2 * tv), 3),
           "window_frac_screen_w": round((left + right) / (2 * th), 3),
           "screen_clear_frac": round(ok / n, 3)}
    print("ADS APERTURE %s: window %.0f%% of screen height x %.0f%% of width, %.0f%% of the screen clear" % (
        oid, 100 * res["window_frac_screen_h"], 100 * res["window_frac_screen_w"], 100 * res["screen_clear_frac"]))
    return res


def ads_render(path, oid, r, extra_meshes=(), res=(1280, 720), samples=32):
    """First-person ADS render at the game's FOV (78 deg vertical / zoom) from the eye point (_SOCKET_ADS +
    Y * eye_relief), on a temporary range: sky world, sun, ground, man-sized targets at 25 m (head on the sight line)
    and 10 m (1.2 m to the side), so the window size and the reticle scale can be judged."""
    sc = bpy.context.scene
    d = r["d"]
    root = r["root"]
    bpy.context.view_layer.update()
    ads_w = root.matrix_world @ Vector(d["ads"])
    eye = ads_w + Vector((0, d["eye_relief"], 0))
    old_world = sc.world
    w = bpy.data.worlds.new("_Range")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.40, 0.52, 0.70, 1)
    bg.inputs[1].default_value = 1.0
    sc.world = w
    tmp = []
    sun = bpy.data.lights.new("_RangeSun", "SUN")
    sun.energy = 3.0
    so = bpy.data.objects.new("_RangeSun", sun)
    so.rotation_euler = (math.radians(50), 0, math.radians(30))
    sc.collection.objects.link(so)
    tmp.append(so)
    gm = bpy.data.materials.get("_M_Ground") or gmat("_M_Ground", (0.18, 0.17, 0.15), 0.9)
    tm = bpy.data.materials.get("_M_Target") or gmat("_M_Target", (0.55, 0.12, 0.08), 0.6)
    tmp.append(box("_RangeGround", -200, 200, -400, 5, eye.z - 1.52, eye.z - 1.50, gm))
    for dist, x in ((25.0, 0.0), (10.0, 1.2)):
        tmp.append(box("_RangeTorso", x - 0.225, x + 0.225, eye.y - dist - 0.125, eye.y - dist + 0.125,
                       eye.z - 1.50, eye.z - 0.13, tm))
        tmp.append(lathe("_RangeHead", [(0.0, eye.z - 0.11)] + [(0.11 * math.sin(math.radians(a)), eye.z - 0.11 * math.cos(
            math.radians(a))) for a in range(15, 180, 15)] + [(0.0, eye.z + 0.11)], "Z", (x, eye.y - dist, eye.z),
            steps=24, mats=tm, closed=False))
    cd = bpy.data.cameras.new("_ADSCam")
    cd.sensor_fit = "VERTICAL"
    cd.angle_y = math.radians(GAME_VFOV / ZOOM[oid])
    cd.clip_start = 0.004
    cd.clip_end = 1000
    cam = bpy.data.objects.new("_ADSCam", cd)
    sc.collection.objects.link(cam)
    cam.location = eye
    cam.rotation_euler = Vector((0, -1, 0)).to_track_quat("-Z", "Y").to_euler()
    old_cam = sc.camera
    sc.camera = cam
    set_visible(list(r["parts"].values()) + list(extra_meshes) + [o for o in tmp if o.type == "MESH"])
    bc.setup_cycles_gpu(sc, samples)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.filepath = path
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:  # GPU busy: CPU fallback like bc.render_views
        print("ADS render failed, retrying on CPU:", e)
        sc.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("rendered", path)
    sc.camera = old_cam
    sc.world = old_world
    for o in tmp + [cam]:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.worlds.remove(w)
    return path


def render_optic(oid, meshes, rail_objs, ads, eye_relief, mode, closeups):
    paths = []
    pre = "ATT_" + oid
    if mode == "quick":
        views_alone = ("three_quarter", "right", "back")
        views_rail = ()
    else:
        views_alone = ("right", "left", "three_quarter", "three_quarter_back", "front", "back", "top",
                       (0.85, -0.75, 0.5))            # the last one matches the concept camera (v09 / warden 3/4)
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


def load_gun(key):
    """Import a finished gun export (read-only reference, never modified) and return (objects, meshes, socket)."""
    import glob
    folder, sock_name = GUNS[key]
    files = sorted(glob.glob(os.path.join(folder, "*.glb")))
    pick = [f for f in files if "default" in os.path.basename(f).lower()] or            [f for f in files if "base" in os.path.basename(f).lower()]
    if not pick:
        print("no %s glb found for the on-gun test fit (skipped)" % key)
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=pick[0])
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    sock = next((o for o in new if o.name.startswith(sock_name)), None)
    node_loc = sock.matrix_world.translation.copy() if sock is not None else None
    loc = node_loc
    sj = os.path.join(folder, "sockets.json")
    if os.path.exists(sj):                      # sockets.json is the documented source of truth for socket positions
        with open(sj) as f:
            loc = Vector(json.load(f)[sock_name]["location"])
        if node_loc is not None and (node_loc - loc).length > 1e-4:
            print("WARNING: %s node in %s is at %s but sockets.json says %s (using sockets.json)" % (
                sock_name, os.path.basename(pick[0]), tuple(round(v, 4) for v in node_loc),
                tuple(round(v, 4) for v in loc)))
    print("on-gun reference %s: %s, optic socket at %s" % (key, pick[0], tuple(round(v, 4) for v in loc)))
    return new, [o for o in new if o.type == "MESH"], loc


def render_on_guns(results, out_dir, views=("right", "three_quarter"), ads=True):
    """Snap every optic onto the real gun exports at <GUN>_SOCKET_Optic (origin on socket, no rotation) and render
    a close side view + a full three-quarter (+ the first-person ADS view on the optic's main gun). Proves the
    mount-space convention end to end."""
    paths = []
    for key in GUNS:
        g = load_gun(key)
        if not g:
            continue
        objs, gun_meshes, loc = g
        for oid, r in results.items():
            if key not in COMPAT[oid]:
                continue
            meshes = list(r["parts"].values())
            r["root"].location = loc
            bpy.context.view_layer.update()
            set_visible(gun_meshes + meshes)
            mn, mx = bc.world_bounds(meshes)
            c = (mn + mx) / 2
            pre = "ATT_%s_on%s" % (oid, key.lower())
            for v in views:
                if v == "right":     # close side view: the optic + the rail / receiver under it
                    paths += bc.render_views(out_dir, pre, objs=meshes, views=(v,), res=(RES, int(RES * 0.6)),
                                             engine="CYCLES", samples=SAMPLES, lens=85,
                                             focus=(c, max(0.10, (mx.y - mn.y) * 0.62, (mx.z - mn.z) * 1.15)))
                else:
                    paths += bc.render_views(out_dir, pre, objs=gun_meshes + meshes, views=(v,),
                                             res=(RES, int(RES * 0.6)), engine="CYCLES", samples=SAMPLES, lens=85,
                                             margin=0.75)
            if ads and key == r["d"]["recommended_for"][0]:   # first-person ADS view on its main gun
                paths.append(ads_render(os.path.join(out_dir, "ATT_%s_ads_on%s.png" % (oid, key.lower())), oid, r,
                                        gun_meshes))
            r["root"].location = (0, 0, 0)
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.context.view_layer.update()
    return paths


CLOSEUPS = {
    "optic_reddot": {"lens": ((0, -0.012, 0.045), 0.026, (0.6, 1.0, 0.45))},
    "optic_holo": {"window": ((0, 0.000, 0.045), 0.034, (0.55, 1.0, 0.35)),
                   "buttons": ((0, -0.035, 0.022), 0.030, (0.9, -0.8, 0.6)),
                   "brow": ((0, -0.020, 0.058), 0.024, (0.25, -0.55, 1.0)),
                   "rightside": ((-0.022, -0.004, 0.026), 0.034, (-1.0, -0.35, 0.25)),
                   "rear": ((0, 0.031, 0.035), 0.036, (-0.3, 1.0, 0.25))},
    "optic_3x": {"turrets": ((0, 0.000, 0.060), 0.040, (-0.9, -0.6, 0.5)),
                 "objective": ((0, -0.045, 0.050), 0.040, (0.5, -1.0, 0.3))},
    "optic_sniper": {"turrets": ((0, 0.000, 0.060), 0.060, (-0.8, -0.7, 0.55)),
                     "objective": ((0, -0.200, 0.0405), 0.055, (0.45, -1.0, 0.25))},
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
        fit = fit_check(oid, parts["Body"], [o for k, o in parts.items() if k != "Body"], d["clamps"], rail[0])
        meshes = list(parts.values())
        tris = tri_count(meshes)
        results[oid] = dict(root=root, parts=parts, ads=ads, d=d, bounds=(mn, mx), rail=rail, fit=fit, tris=tris)
        if d["magnification"] == 1.0:          # 1x sights: measure the clear ADS window at the game FOV
            fit["ads_aperture"] = ads_aperture(oid, results[oid])
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
                "ads_zoom_game": ZOOM[oid],
                "nodes": node_roles(oid, r["parts"]),
                "ocular_node": r["parts"]["Ocular"].name if "Ocular" in r["parts"] else (
                    r["parts"]["Display"].name if "Display" in r["parts"] else None),
                "objective_node": r["parts"]["Objective"].name if "Objective" in r["parts"] else None,
                "reticle_node": r["parts"]["Reticle"].name if "Reticle" in r["parts"] else None,
                "glint_node": r["parts"]["Glint"].name if "Glint" in r["parts"] else None,
                "reticle": d.get("reticle_desc", ""),
                "length_m": round(mx.y - mn.y, 4),
                "width_m": round(mx.x - mn.x, 4),
                "height_m": round(mx.z - mn.z, 4),
                "magnification": str(d["magnification"]),
                "kind": d["kind"],
                "sockets_accepted": ["_SOCKET_Optic"],
                "compatible_weapons": COMPAT[oid],
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
        cycles_backface_cull(True)
    if RENDER == "iter":
        bc.setup_studio(sc)
        itd = os.path.join(OUT, "_work", "iter")
        os.makedirs(itd, exist_ok=True)
        made = []
        for oid, r in results.items():
            meshes = list(r["parts"].values())
            for v in (VIEWS or "three_quarter,right,front").split(","):
                rail = v.startswith("rail_")
                vv = v[5:] if rail else v
                set_visible(meshes + (r["rail"] if rail else []))
                pre = "%s_%s%s" % (oid, TAG + "_" if TAG else "", "rail" if rail else "x")
                if vv == "gun":
                    continue
                if vv == "ads":                      # first-person ADS at the game FOV (dummy rail, no gun)
                    made.append(ads_render(os.path.join(itd, pre + "_ads.png"), oid, r, r["rail"]))
                    continue
                if vv == "eye":
                    made.append(eye_view(os.path.join(itd, pre + "_eye.png"), r["d"]["ads"],
                                         max(r["d"]["eye_relief"], 0.06) + 0.05, lens=50))
                    continue
                if vv.startswith("close"):           # close<i>: the i-th close-up of CLOSEUPS
                    cu = list(CLOSEUPS.get(oid, {}).items())[int(vv[5:] or 0)]
                    made += bc.render_views(itd, pre + "_" + cu[0], objs=meshes, views=(cu[1][2],), res=(RES, RES),
                                            engine="CYCLES", samples=SAMPLES, lens=85, focus=(cu[1][0], cu[1][1]))
                    continue
                vd = vv if vv in bc.VIEW_DIRS else tuple(float(x) for x in vv.split("_"))
                made += bc.render_views(itd, pre, objs=meshes, views=(vd,), res=(RES, RES), engine="CYCLES",
                                        samples=SAMPLES, lens=85, margin=1.2 if rail else 1.12)
        if VIEWS and "gun" in VIEWS.split(","):
            made += render_on_guns(results, itd)
        with open(os.path.join(itd, "_last.json"), "w") as f:
            json.dump(made, f, indent=1)
        subprocess.run(["python", os.path.join(OUT, "make_sheets.py"), "--iter", os.path.join(itd, "_last.json"),
                        os.path.join(itd, "sheet_%s.png" % (TAG or "x"))], check=False, timeout=300)

    if RENDER not in ("none", "iter"):
        bc.setup_studio(sc)
        if RENDER == "full" and not ONLY:          # start clean so no stale render survives a rename
            import glob
            for f in glob.glob(os.path.join(REN, "*.png")) + glob.glob(os.path.join(REN, "sheets", "*.png")):
                os.remove(f)
        all_paths = {}
        for oid, r in results.items():
            meshes = list(r["parts"].values())
            all_paths[oid] = render_optic(oid, meshes, r["rail"], r["d"]["ads"], r["d"]["eye_relief"], RENDER,
                                          CLOSEUPS.get(oid, {}))
        if RENDER == "full" and not ONLY:
            # line-up: every optic on its own rail segment, in a row along Y (a side view compares their sizes)
            offs = {}
            y = 0.0
            for oid, r in results.items():
                mn, mx = r["bounds"]
                offs[oid] = Vector((0, y - mn.y, 0))
                y += (mx.y - mn.y) + 0.07
            vis = []
            for oid, r in results.items():
                r["root"].location = offs[oid]
                for o in r["rail"]:
                    o.location = offs[oid]
                vis += list(r["parts"].values()) + r["rail"]
            set_visible(vis)
            bpy.context.view_layer.update()
            all_paths["lineup"] = bc.render_views(REN, "ATT_optics_lineup", objs=vis,
                                                  views=("three_quarter", "right"), res=(1600, 900),
                                                  engine="CYCLES", samples=SAMPLES, lens=85, margin=1.0)
            for oid, r in results.items():
                r["root"].location = (0, 0, 0)
                for o in r["rail"]:
                    o.location = (0, 0, 0)
            bpy.context.view_layer.update()
            # snap test on the real gun exports (read-only references)
            all_paths["on_gun"] = render_on_guns(results, REN)
        with open(os.path.join(REN, "_render_index.json"), "w") as f:
            json.dump(all_paths, f, indent=2)
        # labelled contact sheets + concept comparisons (system python + PIL)
        try:
            subprocess.run(["python", os.path.join(OUT, "make_sheets.py")], check=False, timeout=300)
        except Exception as e:  # noqa: BLE001
            print("make_sheets failed:", e)

    cycles_backface_cull(False)
    if DO_EXPORT and not ONLY:
        for o in bpy.context.scene.objects:
            if o.type == "MESH":
                o.hide_render = o.name.startswith("_")
        # drop everything the on-gun snap tests imported (gun meshes, M_MAKO_* / M_Warden_* materials, their
        # packed images) and render temporaries, so optics.blend only holds the optics + the test-fit rails
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "optics.blend"), compress=True)
        print("saved", os.path.join(OUT, "optics.blend"))


main()
