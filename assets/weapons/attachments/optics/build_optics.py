"""build_optics.py - shared OPTICS attachment set (prefix ATT) for the val etf prototype.

Re-runnable from scratch (headless Blender 5.2; the system `python` with PIL must be on PATH, it makes the projector
reticle texture and the contact sheets):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/weapons/attachments/optics/build_optics.py" -- [--render none|quick|full|iter]
      [--only optic_holo,optic_3x] [--res 800] [--samples 48] [--no-export] [--debug] [--out <staging-folder>]

Every optic is modeled in MOUNT SPACE (art/WEAPON_MODULAR_SPEC.md):
  origin = centre of the clamp contact on the rail TOP surface, forward = -Y, up = +Z,
  shooter's RIGHT = -X, LEFT = +X.
Each optic lives in its own collection `ATT_<optic>` with a root empty `ATT_<optic>` at the origin, its meshes
as one child node per role (`_Body` opaque multi-material; `_Glass` reflex window; `_Objective` / `_Ocular`
lenses; `_Display` thermal screen; `_Reticle` ADS reticle facing the eye; `_Glint` third-person glint facing
forward; `_StatusLight` thermal LED; optic_projector: `_Flap_L` / `_Flap_R` hinged emitter flaps with their origin
on the hinge axis and `_Hologram`, the projected reticle plane) and the empty `ATT_<optic>_SOCKET_ADS` on the sight
line at the rear of the reticle / eyepiece (camera eye point = socket + Y * eye_relief_m).

1x sights (DIRECTION_LOG item 12) are looked THROUGH: their window walls and hood flanks lie on the eye's view cone,
and measure_ads() checks the 1920 x 1080 eye view on the Mako at the game's effective ADS FOV (settings.ron fov_h 103
through each optic's zoom) against the targets (WINDOW_TARGET, FRAME_EDGE_MAX).

Outputs (all in this folder): ATT_<optic>.glb/.fbx per optic, ATT_optic_projector_Hologram.png, optics.blend,
catalog.json, fitcheck.json, textures/*.png, renders/*.png (contact sheets, measured ADS overlays, before / after and
concept comparisons are made by make_sheets.py with the system python).
"""
import json
import math
import os
import subprocess
import sys

SOURCE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(SOURCE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(PROJECT, "tools"))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import blender_common as bc  # noqa: E402

bc.PROJECT = PROJECT
bc.TEXTURES = os.path.join(PROJECT, "art", "textures")

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
OUT = os.path.abspath(_arg("--out", SOURCE))  # optional staged rebuild; defaults to this asset folder
REN = os.path.join(OUT, "renders")

# ------------------------------------------------------------------------------------------ rail standard
RAIL_W = 0.021          # rail top (overall) width
RAIL_H = 0.0095         # rail height above its base
RAIL_PITCH = 0.010      # cross slot pitch
RAIL_SLOT = 0.005       # slot length along Y
RAIL_SLOT_D = 0.003     # slot depth from the top
JAW_IN = 0.0106         # clamp jaw inner face |x| (0.1 mm clearance to the 0.021 flank)
JAW_BOT = -0.0062       # jaws stop 3.3 mm above the rail base (clear of the dovetail undercut)
CONTACT = 0.0001        # clamp underside sits 0.1 mm above the rail top (no coplanar faces)

OPTIC_IDS = ["optic_reddot", "optic_holo", "optic_projector", "optic_3x", "optic_sniper", "optic_thermal"]
# which guns accept each optic (mirrors game/assets/data/attachments.ron "fits"; optic_projector is new, DIRECTION_LOG
# item 12, and has no attachments.ron entry yet: NOTES.md suggests one)
COMPAT = {"optic_reddot": ["MAKO", "WARDEN"], "optic_holo": ["MAKO", "WARDEN"], "optic_projector": ["MAKO", "WARDEN"],
          "optic_3x": ["MAKO", "WARDEN"], "optic_sniper": ["WARDEN"], "optic_thermal": ["WARDEN"]}
GUNS = {"WARDEN": (os.path.join(PROJECT, "assets", "weapons", "vk50_warden"), "WARDEN_SOCKET_Optic"),
        "MAKO": (os.path.join(PROJECT, "assets", "weapons", "ar7_mako"), "MAKO_SOCKET_Optic")}
# ADS zoom (mirrors game/assets/data/attachments.ron "zoom"; sniper = its low power; DIRECTION_LOG item 12: the 1x
# sights keep a slight zoom, red dot 1.15, holo 1.25, projector ~1.2 (suggested, not in attachments.ron yet))
ZOOM = {"optic_reddot": 1.15, "optic_holo": 1.25, "optic_projector": 1.2, "optic_3x": 3.0, "optic_sniper": 6.0,
        "optic_thermal": 4.0}
# Game FOV. The player's default is game/assets/data/settings.ron defaults.mouse.fov_h = 103 deg, measured at 16:9;
# game/crates/val_etf/src/settings/model.rs turns it into a vertical FOV (vertical_fov) and an optic's zoom makes the
# focal length `zoom` times longer (zoomed_fov). Every ADS check / render here uses exactly those formulas. The
# view camera in render.rs is still hard-coded to 78 deg vertical (not wired to the setting yet), so the ADS
# measurement also reports that case (RENDER_RS_VFOV).
GAME_FOV_H = 103.0
RENDER_RS_VFOV = 78.0


def vertical_fov(h_deg):
    """settings/model.rs vertical_fov(): vertical FOV (deg) for a horizontal FOV measured at 16:9."""
    return 2.0 * math.degrees(math.atan(math.tan(math.radians(h_deg) / 2.0) * 9.0 / 16.0))


def zoomed_fov(v_deg, zoom):
    """settings/model.rs zoomed_fov(): vertical FOV through an optic (focal length `zoom` times longer)."""
    return 2.0 * math.degrees(math.atan(math.tan(math.radians(v_deg) / 2.0) / max(zoom, 1.0)))


GAME_VFOV = vertical_fov(GAME_FOV_H)       # 70.53 deg


def ads_vfov(oid, base=None):
    """Effective vertical ADS FOV (deg) of an optic: the default game FOV through its zoom."""
    return zoomed_fov(GAME_VFOV if base is None else base, ZOOM[oid])
# camera eye point = _SOCKET_ADS + Y * eye_relief_m. The game camera's near plane is 0.03 m
# (game/crates/val_etf/src/render.rs), so nothing of the optic inside the ADS view frustum may come closer to the
# eye than that (depth along the view axis): the 1x sights derive their eye relief from this rule (rearmost body
# point in view + their design distance, >= NEAR_MIN), the magnified ones keep a fixed relief that satisfies it.
# near_check() verifies it on the finished meshes.
NEAR_PLANE = 0.030
NEAR_MIN = 0.0325                          # 2.5 mm margin for ADS sway / recoil push
EYE_RELIEF = {"optic_3x": 0.065, "optic_sniper": 0.085, "optic_thermal": 0.040}
# DIRECTION_LOG item 12: 1x sights are looked THROUGH, so their clear window must be large. Targets at the effective
# ADS FOV, measured on a 1920 x 1080 eye view on the Mako (measure_ads()): holo clear window >= 30 % of the screen
# width and >= 24 % of its height, red dot >= 24 % of the width, the frame / hood edge round the window <= ~2.5 % of
# the screen width (48 px at 1920), nothing over the centre. The window walls and the hood's outer walls lie on the
# eye's view cone, so the front window looks exactly as big as the rear one from the eye and no tunnel wall shows.
WINDOW_TARGET = {"optic_holo": (0.30, 0.24), "optic_reddot": (0.24, 0.0)}      # (width, height) fractions
FRAME_EDGE_MAX = 0.025
# optic_projector (DIRECTION_LOG item 12): hologram plane distance from the eye (task: 0.10 - 0.18 m)
PROJ_HOLO_DIST = 0.130
PROJ_FRAME = (0.24, 0.32)                  # projected frame size as a fraction of the screen (width, height)
# 1x reticles are sized for the SCREEN, not for real MOA (real holo dots are 1-2 MOA and vanish on screen): at the
# effective ADS FOV the dot is >= 5 px and the ring line >= 2 px at 1080p. Diameters in MOA.
HOLO_DOT_MOA = 22
HOLO_RING_MOA = 68                         # ring centre-line diameter (EOTech class)
HOLO_LINE_MOA = 9                          # ring line width
REDDOT_DOT_MOA = 24
OUTLINE_MOA = 4                            # thin dark outline around every reticle element (contrast on sky / snow)
# ice glow: a deeper ice than the palette token (0.45, 0.85, 1.0) so the emissive core stays ice-blue after
# tonemapping instead of clipping to white (review round 2)
ICE_GLOW = (0.15, 0.75, 1.0)


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


def rrect_off(cx, cy, hw, hh, r, off, seg=3, corners=(1, 1, 1, 1)):
    """rrect() offset outward by `off` (negative = inward) with concentric corners (same point count)."""
    rr = max(r + off, 1e-5)
    return rrect(cx, cy, hw + off, hh + off, rr, seg, corners=[max(r * m + off, 1e-5) / rr for m in corners])


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


def moa_m(moa, dist):
    """Linear size (m) of an angle given in MOA, seen from `dist` metres."""
    return dist * math.tan(moa * MOA)


def px_per_moa(vfov_deg, height_px=1080):
    """Screen pixels per MOA at the centre of a perspective view with this vertical FOV."""
    return (height_px / 2.0) / math.tan(math.radians(vfov_deg) / 2.0) * MOA


def decal_quad(name, center, half, facing, mat=None, col=None, mirror_u=False):
    """One-sided textured square (UV 0..1) in the XZ plane at y = center.y, normal = facing * +Y. Used for the 1x
    reticles (facing the eye, +Y) and the third-person glints (facing forward, -Y); the shape lives in an RGBA
    texture with its anti-aliasing baked in, so it filters on screen instead of stair-stepping like tiny geometry."""
    cx, cy, cz = center
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    vs = [bm.verts.new((cx + u * half, cy, cz + v * half)) for u, v in corners]
    f = bm.faces.new(vs)
    bm.normal_update()
    if f.normal.y * facing < 0:
        bmesh.ops.reverse_faces(bm, faces=[f])
    for loop in f.loops:
        co = loop.vert.co
        u = (co.x - cx) / (2 * half)
        loop[uvl].uv = ((0.5 - u) if mirror_u else (u + 0.5), (co.z - cz) / (2 * half) + 0.5)
    ob = _new_obj(name, bm, mat, col)
    ob.data.polygons[0].use_smooth = False
    return ob


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
    """EXACT boolean, applied. transfer_mat: the new faces made by the cutter get this material (default: the
    object's first material, so a cutter without materials never leaves an empty slot behind)."""
    if transfer_mat is None and not any(cutter.data.materials) and any(obj.data.materials):
        transfer_mat = next(m for m in obj.data.materials if m is not None)
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


def _save_rgba(name, rgba):
    """Write a float RGBA array (sRGB-encoded colour, straight alpha, row 0 = bottom) to textures/<name>.png and
    load it back as an sRGB image datablock."""
    import numpy as np
    os.makedirs(TEXDIR, exist_ok=True)
    n = rgba.shape[0]
    path = os.path.join(TEXDIR, name + ".png")
    img = bpy.data.images.new("_" + name, n, n, alpha=True)
    img.pixels = np.clip(rgba, 0.0, 1.0).astype(np.float32).ravel()
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    im = bpy.data.images.load(path, check_existing=True)
    im.name = name
    im.colorspace_settings.name = "sRGB"
    im.alpha_mode = "STRAIGHT"
    return im


def reticle_texture(name, half_moa, shapes, soft_moa, size=128, outline_moa=OUTLINE_MOA, outline_alpha=0.8):
    """RGBA reticle for one decal quad, designed in MOA (the quad spans +-half_moa). shapes: ('disc', r) or
    ('ring', r_centre, half_width), radii in MOA. Ice core (ICE_GLOW) + a thin dark outline for contrast; the edges are
    a signed-distance ramp ~1 screen pixel wide (soft_moa) at the game ADS FOV, so the texture filters cleanly at its
    on-screen size even without mipmaps. Transparent texels carry the dark colour (no bright fringes)."""
    import numpy as np
    c = ((np.arange(size) + 0.5) / size * 2.0 - 1.0) * half_moa
    X, Z = np.meshgrid(c, c)
    R = np.sqrt(X * X + Z * Z)
    d = np.full(R.shape, 1e9)
    for s in shapes:
        d = np.minimum(d, R - s[1] if s[0] == "disc" else np.abs(R - s[1]) - s[2])
    a_core = np.clip(0.5 - d / soft_moa, 0.0, 1.0)
    a_out = np.clip(0.5 - (d - outline_moa) / soft_moa, 0.0, 1.0) * outline_alpha
    alpha = a_core + (1.0 - a_core) * a_out
    ice = _lin_to_srgb(np.asarray(ICE_GLOW, np.float32))
    dark = _lin_to_srgb(np.asarray((0.006, 0.009, 0.013), np.float32))
    w = np.where(alpha > 1e-6, a_core / np.maximum(alpha, 1e-6), 0.0)[..., None]
    rgba = np.ones((size, size, 4), np.float32)
    rgba[..., :3] = ice * w + dark * (1.0 - w)
    rgba[..., 3] = alpha
    return _save_rgba(name, rgba)


def glint_texture(name, size=64, core=0.36, halo_alpha=0.5):
    """Third-person reticle glint (v09): a solid ice core (radius `core` of the quad half size) inside a faint ice halo
    that fades out to the quad edge, so it reads as a saturated cyan oval instead of a white speck."""
    import numpy as np
    c = (np.arange(size) + 0.5) / size * 2.0 - 1.0
    X, Z = np.meshgrid(c, c)
    R = np.sqrt(X * X + Z * Z)
    px = 2.0 / size
    a_core = np.clip(0.5 - (R - core) / (1.5 * px), 0.0, 1.0)
    t = np.clip((R - core) / (1.0 - core), 0.0, 1.0)
    a_halo = halo_alpha * (1.0 - t) ** 2
    alpha = np.maximum(a_core, a_halo)
    rgba = np.ones((size, size, 4), np.float32)
    rgba[..., :3] = _lin_to_srgb(np.asarray(ICE_GLOW, np.float32))
    rgba[..., 3] = alpha
    return _save_rgba(name, rgba)


def decal_mat(name, img, strength, rough=0.45):
    """Alpha-blended emissive decal material: the RGBA texture drives base colour, alpha AND emission (glTF:
    baseColorTexture + emissiveTexture of the same image, alphaMode BLEND, doubleSided false). Clamp-to-edge."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    ti = nt.nodes.new("ShaderNodeTexImage")
    ti.image = img
    ti.interpolation = "Linear"
    ti.extension = "EXTEND"
    ti.location = (-400, 200)
    nt.links.new(ti.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(ti.outputs["Alpha"], p.inputs["Alpha"])
    nt.links.new(ti.outputs["Color"], p.inputs["Emission Color"])
    bc._set_input(p, "Emission Strength", strength)
    bc._set_input(p, "Roughness", rough)
    try:
        mat.surface_render_method = "BLENDED"
    except Exception:  # noqa: BLE001
        pass
    mat.use_backface_culling = True
    mat.diffuse_color = (*ICE_GLOW, 1.0)
    return mat


def hologram_mat(name, png, tint, strength):
    """optic_projector hologram: white-on-transparent texture x tint. Nodes: Image -> Mix(MULTIPLY, factor 1, tint) ->
    Base Color + Emission Color, Image alpha -> Alpha, alpha blended, double-sided. glTF: baseColorTexture +
    baseColorFactor = tint, emissiveTexture + emissiveFactor = tint x strength (KHR_materials_emissive_strength),
    alphaMode BLEND, doubleSided true; the engine re-tints by changing those two factors and fades the hologram in
    through baseColorFactor alpha / emissive. The FBX gets the PNG through the Alpha link (transparency map)."""
    img = bpy.data.images.load(png, check_existing=True)
    img.name = os.path.splitext(os.path.basename(png))[0]
    img.colorspace_settings.name = "sRGB"
    img.alpha_mode = "STRAIGHT"
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    ti = nt.nodes.new("ShaderNodeTexImage")
    ti.image = img
    ti.interpolation = "Linear"
    ti.extension = "EXTEND"
    ti.location = (-700, 200)
    mx = nt.nodes.new("ShaderNodeMix")
    mx.data_type = "RGBA"
    mx.blend_type = "MULTIPLY"
    mx.location = (-400, 250)
    fac = next(s for s in mx.inputs if s.identifier == "Factor_Float")
    fac.default_value = 1.0
    a_in = next(s for s in mx.inputs if s.identifier == "A_Color")
    b_in = next(s for s in mx.inputs if s.identifier == "B_Color")
    out = next(s for s in mx.outputs if s.identifier == "Result_Color")
    b_in.default_value = (*tint[:3], 1.0)
    nt.links.new(ti.outputs["Color"], a_in)
    nt.links.new(out, p.inputs["Base Color"])
    nt.links.new(out, p.inputs["Emission Color"])
    nt.links.new(ti.outputs["Alpha"], p.inputs["Alpha"])
    bc._set_input(p, "Emission Strength", strength)
    bc._set_input(p, "Roughness", 0.5)
    try:
        mat.surface_render_method = "BLENDED"
    except Exception:  # noqa: BLE001
        pass
    mat.use_backface_culling = False
    mat.diffuse_color = (*tint[:3], 1.0)
    return mat


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
    # (review r2) pushed to a saturated blue so it shows as a blue disc at 3/4 like Warden concept_34
    M["lensdeep"] = gmat("M_ATT_LensObjectiveDeep", (0.030, 0.100, 0.320), 0.08, 0.0, coat=1.0)
    # sunshade / bell lining of the sniper: a dark slate that still catches light (M_ATT_Dark made a black hole)
    M["shade"] = gmat("M_ATT_ShadeLining", (0.060, 0.066, 0.078), 0.55, 0.15)
    M["display"] = gmat("M_ATT_Display", (0.004, 0.005, 0.007), 0.05, 0.2, coat=1.0)
    # anti-reflection coated window: a weak coat so the eye-side reflection (stock, cheek) does not ghost the view
    M["reflex"] = gmat("M_ATT_ReflexGlass", (0.03, 0.07, 0.09), 0.03, 0.0, coat=0.35, alpha=0.30)
    # ADS reticles (one textured quad each, faces the eye) and third-person glints (textured quad, faces forward).
    # Edge softness = 1 px at 1080p at each sight's effective ADS FOV.
    soft = {k: 1.0 / px_per_moa(ads_vfov(k)) for k in ("optic_holo", "optic_reddot")}
    rh = HOLO_RING_MOA / 2 + HOLO_LINE_MOA / 2 + OUTLINE_MOA + soft["optic_holo"]
    M["ret_holo_half_moa"] = rh
    M["ret_holo"] = decal_mat("M_ATT_ReticleHolo", reticle_texture(
        "T_ATT_ReticleHolo", rh, [("disc", HOLO_DOT_MOA / 2), ("ring", HOLO_RING_MOA / 2, HOLO_LINE_MOA / 2)],
        soft["optic_holo"]), 1.0)
    rr = REDDOT_DOT_MOA / 2 + OUTLINE_MOA + 1.5 * soft["optic_reddot"]
    M["ret_reddot_half_moa"] = rr
    M["ret_reddot"] = decal_mat("M_ATT_ReticleDot", reticle_texture(
        "T_ATT_ReticleDot", rr, [("disc", REDDOT_DOT_MOA / 2)], soft["optic_reddot"]), 1.0)
    M["glint"] = decal_mat("M_ATT_IceGlint", glint_texture("T_ATT_IceGlint"), 1.2)
    # the 3x's tiny illuminated reticle centre (flat emissive geometry on the ocular)
    M["ice"] = gmat("M_ATT_IceDot", ICE_GLOW, 0.30, emission=ICE_GLOW, strength=1.0)
    # optic_projector: the emitter slits on the inner faces of its flaps (only visible when the flaps are open) and
    # the hologram: a WHITE-on-transparent PIL texture (make_projector_reticle.py) tinted ice by the material factors
    M["emitter"] = gmat("M_ATT_IceEmitter", (0.05, 0.25, 0.33), 0.20, emission=ICE_GLOW, strength=0.9)
    M["holo_png"] = os.path.join(TEXDIR, "T_ATT_ProjectorHologram.png")
    lay = os.path.join(OUT, "_work", "projector_reticle_layout.json")
    os.makedirs(os.path.dirname(lay), exist_ok=True)
    subprocess.run(["python", os.path.join(SOURCE, "make_projector_reticle.py"), "--out", M["holo_png"], "--json", lay],
                   check=True, timeout=120)
    with open(lay) as f:
        M["holo_layout"] = json.load(f)
    M["hologram"] = hologram_mat("M_ATT_ProjectorHologram", M["holo_png"], ICE_GLOW, 1.3)
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
def hood_section(k, hw, top, bottom, r_top, cz, seg=4, chamfer=False):
    """Front-view (x, z) outline of a hood / shroud that flares along the eye's view cone: at cone scale k (distance
    from the eye / reference distance) the half width is hw * k and the top is cz + (top - cz) * k (scaled about the
    sight line height cz), the bottom stays flat at `bottom`. Top corners: radius r_top * k (or a 45 deg chamfer)."""
    t = cz + (top - cz) * k
    return rrect(0.0, (t + bottom) / 2, hw * k, (t - bottom) / 2, r_top * k, 1 if chamfer else seg, corners=(1, 1, 0, 0))


def window_cutters(name, win, s_of, y_rear, y_front, c_rear, c_front, e=0.0010):
    """Cutters for a see-through window on the view cone: the tunnel (scale s_of(y), extended e past both faces) and
    45 deg chamfers round the window on the rear face (c_rear) and the front face (c_front). win(s, off) -> outline."""
    tun = loft_y(name, win(s_of(y_rear + e), 0.0), y_rear + e, win(s_of(y_front - e), 0.0), y_front - e)
    cr = loft_y(name, win(s_of(y_rear - c_rear - 0.0001), -0.0001), y_rear - c_rear - 0.0001,
                win(s_of(y_rear), c_rear + e), y_rear + e)
    if not c_front:
        return tun, cr
    cf = loft_y(name, win(s_of(y_front + c_front + 0.0001), -0.0001), y_front + c_front + 0.0001,
                win(s_of(y_front), c_front + e), y_front - e)
    return tun, cr, cf


def rotate_z(obj, deg, pivot):
    """Rotate mesh data about a Z-parallel axis through pivot (x, y)."""
    px, py = pivot
    obj.data.transform(Matrix.Translation((px, py, 0)) @ Matrix.Rotation(math.radians(deg), 4, "Z") @
                       Matrix.Translation((-px, -py, 0)))
    return obj


def build_reddot(col, M):
    """Mini open reflex sight on a skeletonised Picatinny riser. DIRECTION_LOG item 12 (1x sights are looked THROUGH):
    a big 33 x 26 mm window in a thin 10 mm deep shroud. The shroud's window walls AND its outer walls lie on the eye's
    view cone (the front window is the rear one scaled by the cone, 1.25x), so from the eye both windows look the same
    size, no wall shows and the visible frame is just the 2.1 mm rear face. Only a low, short deck sits behind the
    ring (emitter + adjusters), so the eye comes to NEAR_MIN behind the deck's rear end."""
    P = "ATT_optic_reddot"
    g, gm, rb, dk, ln = M["graphite"], M["gunmetal"], M["rubber"], M["dark"], M["lining"]
    SL = 0.0490                       # sight line above the rail top
    RW, RH, RR = 0.0165, 0.0130, 0.0040   # rear (eye-side) clear window half width / half height / corner radius
    WT = 0.0021                       # frame round the window on the rear face (sides and top), seen from the eye
    D_S = 0.0440                      # eye -> shroud rear face
    LS = 0.0100                       # shroud depth
    YS1 = -0.0055                     # shroud rear face
    YS0 = YS1 - LS                    # shroud front face
    eye_y = YS1 + D_S
    YDK = round(eye_y - NEAR_MIN - 0.0002, 4)   # rear end of the deck = the body point nearest to the eye
    kS = (eye_y - YS0) / D_S          # cone scale at the front face
    TUN = 1.02                        # window walls 2 % outside the cone: they face away from the eye
    ZB = 0.0236                       # housing bottom (on the riser)
    ZDK = SL - RH - 0.0015            # deck top, under the window
    HXD = RW + WT                     # deck half width = the shroud's rear outer half width
    body = []

    def s_t(y):                       # tunnel scale at y (1 at the rear face)
        return 1.0 + (kS * TUN - 1.0) * (YS1 - y) / LS

    def win(s, off=0.0):
        return rrect_off(0.0, SL, RW * s, RH * s, RR * s, off, 4)

    body.append(rail_clamp(P + "_Clamp", -0.0170, 0.0170, W=0.028, top=0.0050, mat=g, col=col))
    # skeletonised riser: flared pedestal in side view (lifts the sight line into the 0.04-0.075 band), widening
    # toward the housing in front view, one big lightening window through it
    riser = prism(P + "_Riser", [(-0.0170, 0.0045), (0.0170, 0.0045), (0.0170, 0.0085), (YDK - 0.0005, 0.0172),
                                 (YDK - 0.0005, 0.0242), (YS0 + 0.0005, 0.0242), (YS0 + 0.0005, 0.0172),
                                 (-0.0170, 0.0085)], "X", -0.0170, 0.0170, g, col)
    cut(riser, prism("_c", [(-0.0142, 0.0030), (0.0142, 0.0030), (0.0168, 0.0260), (-0.0168, 0.0260)], "Y",
                     -0.04, 0.04), op="INTERSECT")
    cut(riser, prism("_c", rrect(-0.0015, 0.0158, 0.0062, 0.0036, 0.0030, 4), "X", -0.03, 0.03), transfer_mat=dk)
    bevel(riser, 0.0010, 2)
    body.append(riser)

    # shroud ring: flares along the view cone (front = rear x kS), flat bottom on the riser
    hs = loft_y(P + "_Housing", hood_section(1.0, HXD, SL + RH + WT, ZB, RR + WT, SL), YS1,
                hood_section(kS, HXD, SL + RH + WT, ZB, RR + WT, SL), YS0, g, col)
    # low deck behind the ring (emitter + adjusters), merged into the ring
    deck = prism("_c", [(YS1 - 0.0020, ZB), (YDK, ZB), (YDK, ZDK - 0.0020), (YDK - 0.0020, ZDK), (YS1 - 0.0020, ZDK)],
                 "X", -HXD, HXD, g)
    cut(hs, deck, op="UNION")
    for c in window_cutters("_c", win, s_t, YS1, YS0, 0.0005, 0.0009):
        cut(hs, c, transfer_mat=ln)
    bevel(hs, 0.0007, 2)
    body.append(hs)

    # emitter hood at the rear of the deck (its LED window faces the glass)
    ye0, ye1 = YDK - 0.0062, YDK - 0.0016
    em = prism(P + "_Emitter", [(ye0, ZDK - 0.0004), (ye1, ZDK - 0.0004), (ye1, ZDK + 0.0018), (ye1 - 0.0014, ZDK + 0.0030),
                                (ye0, ZDK + 0.0030)], "X", -0.0042, 0.0042, g, col)
    bevel(em, 0.0005, 2)
    body.append(em)
    body.append(box(P + "_EmitterWin", -0.0022, 0.0022, ye0 - 0.0004, ye0 + 0.0003, ZDK + 0.0006, ZDK + 0.0023, dk,
                    col))
    # adjusters (gunmetal): elevation on the deck top (+X of the emitter), windage on the right (-X) deck flank
    ym = (YS1 + YDK) / 2
    body.append(screw_head(P + "_ScrewElev", (0.0112, ym, ZDK), "Z", 1, 0.0021, 0.0011, gm, col))
    body.append(screw_head(P + "_ScrewWind", (-HXD, ym, 0.0291), "X", -1, 0.0022, 0.0012, gm, col))
    # brightness up / down buttons on the left (+X) deck flank
    for zb in (0.0270, 0.0314):
        b = prism(P + "_Btn", rrect(ym, zb, 0.0030, 0.0014, 0.0010, 2), "X", HXD - 0.0002, HXD + 0.0013, rb, col)
        bevel(b, 0.0004, 1)
        body.append(b)
    # cross-bolt: knurled nut on the left (+X), screw head on the right (-X)
    body.append(knob_x(P + "_ClampKnob", 0.0140, 0.0040, -0.0002, 1, 0.0045, 0.0035, gm, col, steps=14))
    body.append(hex_nut(P + "_ClampBolt", -0.0140, 0.0040, -0.0002, -1, gm, col, r=0.0036, t=0.0020))

    # glass: in the ring, tilted 4 deg (top toward the shooter), edges buried 0.4 mm in the window walls
    YG = YS1 - 0.0030
    TILT = -4
    glass = prism(P + "_Lens", win(s_t(YG), 0.0004), "Y", YG - 0.0006, YG + 0.0006, M["reflex"], col)
    rotate_x(glass, TILT, (YG, SL))
    smooth(glass, 30)
    ads = (0.0, YG + 0.0007, SL)
    ER = round(eye_y - ads[1], 4)
    # ADS reticle: one textured quad facing the eye (REDDOT_DOT_MOA dot + dark outline, sized for that eye relief);
    # third-person glint: soft ice core + halo quad facing forward
    ret = decal_quad(P + "_Reticle", (0.0, YG + 0.00065, SL), moa_m(M["ret_reddot_half_moa"], ER), +1,
                     mat=M["ret_reddot"], col=col)
    glint = decal_quad(P + "_GlintDot", (0.0, YG - 0.00065, SL), 0.0021, -1, mat=M["glint"], col=col)
    for o in (ret, glint):
        rotate_x(o, TILT, (YG, SL))
    return dict(body=body, glass=[glass], reticle=[ret], glint=[glint], ads=ads, clamps=[(-0.0170, 0.0170)],
                eye_relief=ER, rear_y=YDK, magnification=1.0, recommended_for=["MAKO"], default_for=[],
                kind="mini reflex", keep_uv=("Reticle", "Glint"),
                window_mm=[round(2000 * RW, 1), round(2000 * RH, 1)],
                front_window_mm=[round(2000 * RW * kS * TUN, 1), round(2000 * RH * kS * TUN, 1)],
                frame_mm=round(1000 * WT, 1), eye_to_rear_face_m=D_S,
                reticle_moa={"dot": REDDOT_DOT_MOA, "outline": OUTLINE_MOA},
                reticle_desc="%d MOA ice dot with a %d MOA dark outline (one alpha-blended textured quad)" % (
                    REDDOT_DOT_MOA, OUTLINE_MOA))


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


def loft_y(name, ptsA, yA, ptsB, yB, mat=None, col=None, axis="Y"):
    """Closed solid between two outlines with the same point count at yA and yB along `axis` (a frustum cutter);
    outlines are (x, z) for Y, (y, z) for X, (x, y) for Z."""
    P = _axis_map(axis)
    bm = bmesh.new()
    a = [bm.verts.new(P(u, v, yA)) for u, v in ptsA]
    b = [bm.verts.new(P(u, v, yB)) for u, v in ptsB]
    n = len(ptsA)
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(n):
        bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return _new_obj(name, bm, mat, col)


def offset_convex(pts, d):
    """Offset a convex 2D polygon (CCW or CW) outward by d (negative = inward): each edge moves along its normal,
    consecutive edges are intersected."""
    n = len(pts)
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    sgn = 1.0 if area > 0 else -1.0
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        ln_ = math.hypot(ex, ey)
        nx, ny = sgn * ey / ln_, -sgn * ex / ln_          # outward normal
        lines.append(((x0 + nx * d, y0 + ny * d), (ex, ey)))
    out = []
    for i in range(n):
        (p0, e0), (p1, e1) = lines[i - 1], lines[i]
        den = e0[0] * e1[1] - e0[1] * e1[0]
        t = ((p1[0] - p0[0]) * e1[1] - (p1[1] - p0[1]) * e1[0]) / den
        out.append((p0[0] + e0[0] * t, p0[1] + e0[1] * t))
    return out


def build_holo(col, M):
    """Bone box holographic sight (Mako default, DIRECTION_LOG item 2 / mako v09), rebuilt for DIRECTION_LOG item 12
    (1x sights are looked THROUGH: large clear aperture, front and rear windows the same size from the eye, thin
    frames, no tunnel, nothing over the centre).
      - The eye sits D_R = 50 mm behind the hood's rear face. Everything above the window's lower edge (window walls,
        hood flanks, top) lies inside the eye's view cone through the 2.4 mm rear frame: the hood flares
        forward along that cone (the window walls 2 % outside it, so they face away from the eye). From the eye the
        sight picture is: window -> 2.4 mm bone frame -> the world.
      - The window is taller above the sight line than below it (like most holo sights the dot sits low in the
        window). That raises the lowest sight ray through the window, so the deck in front can be tall (its top slopes
        down along that ray) and the body keeps v09's proportions: a bone hood with a chamfered brow over a deep-set
        window, on a chunky deck that runs up to the window's lower edge.
      - v09 details: dark window bezel (the lining walls seen from the front), 45 deg chamfered upper corners and brow,
        sloped deck with a shallow inset panel, a proud round main button + small nub, a wrap-around rubber guard on
        the +X front corner, dark base plate + mount bars on both sides (butterfly QD lever on the shooter's LEFT,
        +X; cross-bolt head + windage / elevation adjusters on the RIGHT, -X), a hood / base split line and a graphite
        battery door on the rear face under the window.
    The clamp is centred on the origin (spec)."""
    P = "ATT_optic_holo"
    g, gm, rb, bo, ln, dk = M["graphite"], M["gunmetal"], M["rubber"], M["bone"], M["lining"], M["dark"]
    SL = 0.0450                       # sight line above the rail top
    AW = 0.0175                       # rear (eye-side) clear window half width: 35 mm
    AUP, ADN = 0.0150, 0.0095         # window extent above / below the sight line at the rear face: 24.5 mm tall
    WR, WC = 0.0045, (1.35, 1.35, 1.0, 1.0)   # window corner radius (top corners x1.35)
    T = 0.0024                        # frame round the window on the rear face (sides + top), seen from the eye
    D_R = 0.0500                      # eye -> hood rear face
    L = 0.0150                        # hood depth (rear face -> front face)
    LD = 0.0520                       # deck length
    YR = (L + LD) / 2                 # hood rear face (body centred on the origin)
    YF = YR - L                       # window front face
    YD = YF - LD                      # deck front
    eye_y = YR + D_R
    ZB = 0.0075                       # bottom of the bone shell (dark base plate below it)
    ZSEAM = 0.0128                    # hood / base split line
    TUN = 1.02                        # window walls 2 % outside the view cone

    def ray_z(y):                     # lowest sight ray through the window (rear lower edge) at y
        return SL - ADN * (eye_y - y) / D_R
    ZDR = ray_z(YF) - 0.0030          # deck top at the hood / at the front: 3 mm under that ray
    ZDF = ray_z(YD) - 0.0030
    SLOPE = math.degrees(math.atan2(ZDR - ZDF, YF - YD))

    def deck_top(y):
        return ZDF + (ZDR - ZDF) * (y - YD) / (YF - YD)
    kF = (eye_y - YF) / D_R           # cone scale at the window front face
    HWR = AW + T                      # hood half width at the rear face
    HWF = HWR * kF                    # ... at the window front face = the deck half width
    TOP = SL + AUP + T                # hood top at the rear face
    RT = 0.586 * (WR * WC[0] + T)     # 45 deg chamfer leg of the hood's upper corners (the frame stays T thick)
    body = []

    def s_t(y):                       # window tunnel scale at y (1 at the rear face)
        return 1.0 + (kF * TUN - 1.0) * (YR - y) / L

    def win(s, off=0.0):              # window outline at scale s, scaled about the sight line
        return rrect_off(0.0, SL + (AUP - ADN) / 2 * s, AW * s, (AUP + ADN) / 2 * s, WR * s, off, 4, WC)

    def sec(k):
        return hood_section(k, HWR, TOP, ZB, RT, SL, chamfer=True)

    # rail clamp (centred on the origin) + dark base plate under the whole shell (v09: dark band under the bone body)
    body.append(rail_clamp(P + "_Clamp", -0.0240, 0.0240, W=0.036, top=0.0045, mat=g, col=col, seg=2))
    plan = [(-HWF, YD), (HWF, YD), (HWF, YF), (HWR, YR), (-HWR, YR), (-HWF, YF)]   # top view of the shell
    plate = prism(P + "_BasePlate", offset_convex(plan, 0.0006), "Z", 0.0015, ZB + 0.0003, g, col)
    bevel(plate, 0.0012, 2)
    body.append(plate)

    # bone shell: the hood, ONE loft from the rear face to the front face flaring along the view cone (flat bottom),
    # with v09's brow as a 45 deg chamfer on its top front edge (the top rises along the cone toward the front)
    sh = loft_y(P + "_Shell", sec(1.0), YR, sec(kF), YF, bo, col)
    zf_top = SL + (TOP - SL) * kF
    BRW = 0.0024                                                     # brow chamfer (the top bar is ~3 mm here)
    cut(sh, prism("_c", [(YF - 0.001, zf_top - BRW), (YF + BRW, zf_top + 0.001), (YF - 0.001, zf_top + 0.001)], "X",
                  -0.06, 0.06))
    # deck in front of the hood: plan with straight sides at the hood's front width (+ a tapered tail inside the
    # hood) x side profile with the top sloping down along the lowest sight ray and a chamfered front top edge
    deck = prism("_c", [(-HWF, YD), (HWF, YD), (HWF, YF), (HWF - 0.0012, YF + 0.0025), (-HWF + 0.0012, YF + 0.0025),
                        (-HWF, YF)], "Z", ZB, 0.06, bo)
    cut(deck, prism("_c2", [(YD - 0.001, ZB - 0.001), (YF + 0.003, ZB - 0.001), (YF + 0.003, deck_top(YF + 0.003)),
                            (YD + 0.0030, deck_top(YD + 0.0030)), (YD - 0.001, deck_top(YD + 0.0030) - 0.0040)],
                    "X", -0.06, 0.06), op="INTERSECT")
    cut(sh, deck, op="UNION")
    # window: tunnel along the view cone through the hood (lining = v09's dark inner bezel seen from the front) + a
    # 0.5 mm 45 deg chamfer round it on the rear face; the bevel rounds the front edges
    for c in window_cutters("_c", win, s_t, YR, YF, 0.0005, None):
        cut(sh, c, transfer_mat=ln)
    # shallow 0.9 mm inset panel in the sloped deck top (v09)
    py0, py1 = YD + 0.0050, YF - 0.0035
    pan = prism("_c", rrect(0.0, (py0 + py1) / 2, HWF - 0.0050, (py1 - py0) / 2, 0.0025, 3), "Z", 0.0, 0.08)
    cut(pan, prism("_c2", [(YD - 0.01, deck_top(YD - 0.01) - 0.0009), (YF + 0.01, deck_top(YF + 0.01) - 0.0009),
                           (YF + 0.01, 0.09), (YD - 0.01, 0.09)], "X", -0.06, 0.06), op="INTERSECT")
    cut(sh, pan)
    # hood / base split line: 0.6 mm groove, 0.5 mm deep, all round the shell (dark lining faces)
    ring = prism("_c", offset_convex(plan, 0.0020), "Z", ZSEAM - 0.0003, ZSEAM + 0.0003)
    cut(ring, prism("_c2", offset_convex(plan, -0.0005), "Z", ZSEAM - 0.002, ZSEAM + 0.002))
    cut(sh, ring, transfer_mat=ln)
    bevel(sh, 0.0009, 2, exclude=lambda m: abs(m.z - ZSEAM) < 0.00035)
    body.append(sh)

    # rear battery door: a bone panel standing 0.6 mm proud of the rear face under the window (three engraved grip
    # lines; a dark door read as a dead screen, review round 1), rubber thumb latch
    zt_door = SL - ADN - 0.0030
    zdc = (ZSEAM + 0.0018 + zt_door) / 2
    door = prism(P + "_BatteryDoor", rrect(0.0, zdc, 0.0128, (zt_door - ZSEAM - 0.0018) / 2, 0.0018, 3),
                 "Y", YR - 0.0004, YR + 0.0006, bo, col)
    for k in range(3):
        zg = zt_door - 0.0040 - 0.0022 * k
        cut(door, box("_c", -0.0060, 0.0060, YR + 0.0002, YR + 0.0012, zg - 0.0003, zg + 0.0003), transfer_mat=ln)
    bevel(door, 0.0003, 1)
    body.append(door)
    latch = prism(P + "_DoorLatch", rrect(0.0, ZSEAM + 0.0030, 0.0036, 0.0009, 0.0007, 2), "Y", YR + 0.0002,
                  YR + 0.0012, rb, col)
    bevel(latch, 0.0003, 1)
    body.append(latch)

    # deck buttons (in the inset panel, normal to the sloped deck): one big round main button standing proud + a small
    # nub at the +X front (v09)
    for (bx, by, br, h) in ((-0.0070, YF - 0.0190, 0.0060, 0.0020), (0.0100, YD + 0.0130, 0.0032, 0.0011)):
        z0 = deck_top(by) - 0.0009
        b = lathe(P + "_BtnTop", [(0.0, z0 - 0.0012), (br, z0 - 0.0012), (br, z0 + h - 0.0010), (br - 0.0010, z0 + h),
                                  (0.0, z0 + h)], "Z", (bx, by, 0), steps=18, mats=rb, col=col)
        rotate_x(b, SLOPE, (by, z0))
        smooth(b, 35)
        body.append(b)
    # +X front corner: angular wrap-around rubber guard (v09) with a round button recess on its side face
    gz0 = 0.0095
    gd = prism(P + "_CornerGuard", [(HWF - 0.0095, YD - 0.0020), (HWF - 0.0006, YD - 0.0020), (HWF + 0.0020, YD + 0.0006),
                                    (HWF + 0.0020, YD + 0.0140), (HWF - 0.0010, YD + 0.0140), (HWF - 0.0010, YD + 0.0010),
                                    (HWF - 0.0095, YD + 0.0010)], "Z", gz0, 0.05, rb, col)
    cut(gd, prism("_c", [(YD - 0.01, deck_top(YD - 0.01) + 0.0008), (YD + 0.03, deck_top(YD + 0.03) + 0.0008),
                         (YD + 0.03, 0.08), (YD - 0.01, 0.08)], "X", -0.06, 0.06))     # top follows the deck slope
    cut(gd, lathe("_c", [(0.0, HWF + 0.0009), (0.0024, HWF + 0.0009), (0.0024, HWF + 0.01), (0.0, HWF + 0.01)], "X",
                  (0, YD + 0.0078, (gz0 + deck_top(YD + 0.0078)) / 2), steps=14), transfer_mat=dk)
    bevel(gd, 0.0008, 2)
    body.append(gd)
    # mount bars along both deck flanks (v09 shows the +X one): cross-bolt boss (+X) / bolt head (-X) at the front,
    # butterfly QD lever on +X at the rear end next to the hood
    mx0, mx1 = HWF - 0.0004, HWF + 0.0032
    bar = [(YD + 0.0155, 0.0022), (YF - 0.0006, 0.0022), (YF - 0.0006, 0.0090), (YF - 0.0036, 0.0116),
           (YD + 0.0195, 0.0116), (YD + 0.0155, 0.0076)]
    for s in (1, -1):
        mb = prism(P + "_MountBar", bar, "X", s * mx0, s * mx1, g, col)
        bevel(mb, 0.0008, 2)
        body.append(mb)
    yb = YD + 0.0240
    boss = lathe(P + "_BoltBoss", [(0.0022, mx1 - 0.0002), (0.0042, mx1 - 0.0002), (0.0042, mx1 + 0.0014),
                                   (0.0035, mx1 + 0.0021), (0.0022, mx1 + 0.0021), (0.0022, mx1 + 0.0009)],
                 "X", (0, yb, 0.0070), steps=16, mats=M["dark"], col=col)
    smooth(boss, 30)
    body.append(boss)
    body.append(hex_nut(P + "_BoltHead", -mx1, yb, 0.0070, -1, gm, col, r=0.0034, t=0.0018))
    yq = YF - 0.0095
    lv = prism(P + "_QDLever", lobes_profile(yq, 0.0070, 0.0036, 0.0052, n=10), "X", mx1 - 0.0003, mx1 + 0.0034, g,
               col)
    bevel(lv, 0.0009, 2)
    body.append(lv)
    body.append(screw_head(P + "_QDHub", (mx1 + 0.0034, yq, 0.0070), "X", 1, 0.0022, 0.0010, gm, col, steps=12,
                           slot=False))
    # windage / elevation adjusters on the shooter's right (-X) deck flank next to the hood, above the split line
    for (ya, za) in ((YF - 0.0085, 0.0175), (YF - 0.0085, 0.0245)):
        body.append(screw_head(P + "_Adjuster", (-HWF, ya, za), "X", -1, 0.0028, 0.0013, gm, col, steps=14))
    # cross-bolt nut on the right (-X) on the clamp jaw, small nut on the left jaw
    body.append(hex_nut(P + "_ClampBolt", -0.0180, -0.0100, -0.0020, -1, gm, col, r=0.0032, t=0.0022))
    body.append(hex_nut(P + "_ClampNut", 0.0180, -0.0100, -0.0020, 1, gm, col, r=0.0032, t=0.0022))

    # glass 5 mm in front of the rear face, tilted 4 deg (top toward the eye), edges buried in the window walls
    YG = YR - 0.0050
    TILT = -4
    glass = prism(P + "_Glass", win(s_t(YG), 0.0004), "Y", YG - 0.00075, YG + 0.00075, M["reflex"], col)
    rotate_x(glass, TILT, (YG, SL))
    smooth(glass, 30)
    ads = (0.0, YG + 0.0009, SL)
    ER = round(eye_y - ads[1], 4)
    assert eye_y - (YR + 0.0012) >= NEAR_MIN       # latch face = rearmost body point
    # ADS reticle: one textured quad on the glass rear (faces the eye): dot + ring + dark outline, sized for ER;
    # third-person glint: soft ice core + halo quad on the glass front (faces forward), like v09
    ret = decal_quad(P + "_Reticle", (0.0, YG + 0.0008, SL), moa_m(M["ret_holo_half_moa"], ER), +1,
                     mat=M["ret_holo"], col=col)
    glint = decal_quad(P + "_GlintDot", (0.0, YG - 0.0008, SL), 0.0026, -1, mat=M["glint"], col=col)
    for o in (ret, glint):
        rotate_x(o, TILT, (YG, SL))
    return dict(body=body, glass=[glass], reticle=[ret], glint=[glint], ads=ads, clamps=[(-0.0240, 0.0240)],
                eye_relief=ER, rear_y=YR + 0.0012, magnification=1.0, recommended_for=["MAKO"], default_for=["MAKO"],
                kind="box holographic", keep_uv=("Reticle", "Glint"),
                window_mm=[round(2000 * AW, 1), round(1000 * (AUP + ADN), 1)],
                window_above_below_sight_line_mm=[round(1000 * AUP, 1), round(1000 * ADN, 1)],
                front_window_mm=[round(2000 * AW * kF * TUN, 1), round(1000 * (AUP + ADN) * kF * TUN, 1)],
                frame_mm=round(1000 * T, 1), eye_to_rear_face_m=D_R,
                reticle_moa={"dot": HOLO_DOT_MOA, "ring": HOLO_RING_MOA, "ring_line": HOLO_LINE_MOA,
                             "outline": OUTLINE_MOA},
                reticle_desc="%d MOA ice dot + %d MOA ring (%d MOA line), %d MOA dark outline (one alpha-blended "
                             "textured quad)" % (HOLO_DOT_MOA, HOLO_RING_MOA, HOLO_LINE_MOA, OUTLINE_MOA))


def build_projector(col, M):
    """optic_projector (DIRECTION_LOG item 12, original design): the high-end 1x sight, no glass. A low graphite
    housing (31 mm from jaw to hinge top when folded) with a raised bone spine down the middle and two emitter flaps
    lying flush either side of it. On ADS the flaps flip up about their outer hinges (OPEN deg, leaning slightly
    outward) and the emitter slits on their inner faces project the HOLOGRAM: one alpha-textured, emissive plane
    (white-on-transparent PIL texture, tinted ice by the material) floating PROJ_HOLO_DIST in front of the eye at
    sight height, sized so its corner-bracket frame covers PROJ_FRAME of the screen at the ADS FOV. Nothing sits
    round the frame, so the sight picture is wide open.
    Nodes: _Body; _Flap_L (+X, shooter's left) / _Flap_R (-X) with their origin ON the hinge axis (rest pose =
    FOLDED, identity rotation; custom properties fold_angle_deg / open_angle_deg); _Hologram (origin at the frame
    centre, double-sided); _SOCKET_ADS on the sight line at the housing's rear face."""
    P = "ATT_optic_projector"
    g, gm, rb, dk, bo = M["graphite"], M["gunmetal"], M["rubber"], M["dark"], M["bone"]
    SL = 0.0470                       # sight line (hologram centre) above the rail top
    PH = 0.0170                       # housing half width (34 mm)
    YPF, YPR = -0.0330, 0.0300        # housing front / rear
    ZH = 0.0235                       # housing top (the folded flaps lie flush with it)
    BAY = 0.0028                      # flap bay depth
    HX = 0.0135                       # hinge axis |x| (at z = ZH)
    XIN = 0.0037                      # flap free edge |x| when folded (the bone spine runs between the flaps)
    FT = 0.0022                       # flap thickness
    YW0, YW1 = -0.0190, 0.0165        # flap span along Y (hinge edge)
    OPEN = 100.0                      # open angle about the hinge (deg): 10 deg past vertical, leaning outward
    ER = 0.0450                       # eye relief behind the socket (socket = housing rear face on the sight line)
    ads = (0.0, YPR, SL)
    eye_y = YPR + ER
    YH = eye_y - PROJ_HOLO_DIST       # hologram plane (in front of the housing nose)
    body = []

    body.append(rail_clamp(P + "_Clamp", -0.0240, 0.0240, W=0.032, top=0.0050, mat=g, col=col))
    # housing: side profile (long sloped nose, chamfered rear) x plan (chamfered nose corners) x front section
    # (1.2 mm chamfers on the top side edges)
    side = [(YPF, 0.0045), (YPR, 0.0045), (YPR, ZH - 0.0045), (YPR - 0.0045, ZH), (YPF + 0.0115, ZH),
            (YPF, ZH - 0.0085)]
    hs = prism(P + "_Housing", side, "X", -PH, PH, g, col)
    cut(hs, prism("_c", [(-PH, YPR + 0.01), (PH, YPR + 0.01), (PH, YPF + 0.0070), (PH - 0.0070, YPF - 0.0001),
                         (-PH + 0.0070, YPF - 0.0001), (-PH, YPF + 0.0070)], "Z", -0.01, 0.05), op="INTERSECT")
    cut(hs, prism("_c", [(-PH + 0.0032, 0.0040), (PH - 0.0032, 0.0040), (PH, 0.0080), (PH, ZH - 0.0010),
                         (PH - 0.0010, ZH + 0.0001), (-PH + 0.0010, ZH + 0.0001), (-PH, ZH - 0.0010), (-PH, 0.0080)],
                  "Y", -0.06, 0.06), op="INTERSECT")
    # flap bays either side of the spine (dark floors: the emitters face down into them when folded) + a hinge
    # channel round each flap knuckle (0.2 mm clearance) so nothing rubs while the flap swings
    for s in (1, -1):
        x0, x1 = sorted((s * (XIN - 0.0004), s * (HX + 0.0004)))
        cut(hs, box("_c", x0, x1, YW0 - 0.0004, YW1 + 0.0004, ZH - BAY, ZH + 0.01), transfer_mat=dk)
        cut(hs, lathe("_c", [(0.0, YW0 - 0.0002), (0.0021, YW0 - 0.0002), (0.0021, YW1 + 0.0002), (0.0, YW1 + 0.0002)],
                      "Y", (s * HX, 0, ZH), steps=12), transfer_mat=dk)
    # side seam line, three short vent grooves on each flank (rear half), sensor window on the nose
    for s in (1, -1):
        cut(hs, box("_c", s * (PH - 0.0005), s * (PH + 0.002), YPF - 0.01, YPR + 0.01, 0.0118, 0.0124), transfer_mat=dk)
        for zv in (0.0155, 0.0172, 0.0189):
            cut(hs, box("_c", s * (PH - 0.0006), s * (PH + 0.002), 0.0060, 0.0230, zv - 0.0003, zv + 0.0003),
                transfer_mat=dk)
    cut(hs, prism("_c", rrect(0.0, 0.0095, 0.0075, 0.0024, 0.0012, 2), "Y", YPF - 0.002, YPF + 0.0006), transfer_mat=dk)
    bevel(hs, 0.0008, 2, exclude=lambda m: abs(m.z - 0.0121) < 0.0005 or (abs(abs(m.x) - PH) < 0.0008 and
                                                                         0.015 < m.z < 0.0195 and m.y > 0.005) or
          (XIN - 0.0010 < abs(m.x) < HX + 0.0025 and m.z > ZH - BAY - 0.0005 and YW0 - 0.001 < m.y < YW1 + 0.001))
    body.append(hs)
    # a raised spine down the middle of the top (between the flaps), sloping down over the nose
    sp = prism(P + "_Spine", [(YPF + 0.0025, ZH - 0.0070), (YPF + 0.0120, ZH + 0.0010), (YPR - 0.0050, ZH + 0.0010),
                              (YPR - 0.0035, ZH - 0.0006), (YPR - 0.0035, ZH - 0.0040), (YPF + 0.0040, ZH - 0.0090)],
               "X", -0.0029, 0.0029, g, col)
    cut(sp, prism("_c", [(-0.0040, ZH - 0.02), (0.0040, ZH - 0.02), (0.0040, ZH - 0.0002), (0.0021, ZH + 0.0012),
                         (-0.0021, ZH + 0.0012), (-0.0040, ZH - 0.0002)], "Y", -0.06, 0.06), op="INTERSECT")
    cut(sp, box("_c", -0.01, 0.01, -0.0035, -0.0025, ZH + 0.0004, ZH + 0.01), transfer_mat=dk)   # notch line
    bevel(sp, 0.0004, 1)
    body.append(sp)
    # housing hinge knuckles at both ends of each flap (gunmetal)
    for s in (1, -1):
        for (y0, y1) in ((YW0 - 0.0050, YW0 - 0.0003), (YW1 + 0.0003, YW1 + 0.0050)):
            k = lathe(P + "_Knuckle", [(0.0, y0), (0.0016, y0), (0.0016, y1), (0.0, y1)], "Y", (s * HX, 0, ZH),
                      steps=12, mats=gm, col=col)
            smooth(k, 35)
            body.append(k)
    # rear: rubber power button; +X: rubber brightness rocker; cross-bolt knob +X, bolt head -X
    pb = prism(P + "_PowerBtn", rrect(0.0, 0.0120, 0.0045, 0.0022, 0.0012, 2), "Y", YPR - 0.0004, YPR + 0.0012, rb,
               col)
    bevel(pb, 0.0004, 1)
    body.append(pb)
    rk = prism(P + "_Rocker", rrect(-0.0120, 0.0168, 0.0060, 0.0022, 0.0012, 2), "X", PH - 0.0003, PH + 0.0012, rb,
               col)
    bevel(rk, 0.0004, 1)
    body.append(rk)
    body.append(knob_x(P + "_ClampKnob", 0.0160, -0.0100, -0.0002, 1, 0.0045, 0.0035, gm, col, steps=14))
    body.append(hex_nut(P + "_ClampBolt", -0.0160, -0.0100, -0.0002, -1, gm, col, r=0.0036, t=0.0020))

    def flap(sx, name):
        """One emitter flap, modeled FOLDED in mount space: a fin (plan: a trapezoid with a raked front edge) lying in
        its bay, hinge edge on the axis, top flush with the housing."""
        x_h, x_i = sx * HX, sx * XIN
        z0, z1 = ZH - FT, ZH
        plan = [(x_h, YW0), (x_h, YW1), (x_i, YW1 - 0.0025), (x_i, YW0 + 0.0065)]
        f = prism(name, plan, "Z", z0, z1, g, col)
        # outer face (top when folded): inset panel + three grip notches at the free edge
        lo, hi = sorted((x_h, x_i))
        pc = ((lo + hi) / 2 + sx * 0.0008, (YW0 + YW1) / 2 + 0.0005)
        cut(f, prism("_c", rrect(pc[0], pc[1], (hi - lo) / 2 - 0.0020, (YW1 - YW0) / 2 - 0.0060, 0.0016, 3), "Z",
                     z1 - 0.0006, z1 + 0.01))
        for yn in (YW1 - 0.0055, YW1 - 0.0080, YW1 - 0.0105):
            cut(f, box("_c", x_i - sx * 0.002, x_i + sx * 0.0012, yn - 0.0006, yn + 0.0006, z1 - 0.0005, z1 + 0.01))
        bevel(f, 0.0004, 1)
        parts = [f]
        # bone accent: an insert in the outer-face recess, 0.15 mm under the flap top
        ins = prism(name + "Insert", rrect(pc[0], pc[1], (hi - lo) / 2 - 0.0024, (YW1 - YW0) / 2 - 0.0064, 0.0012, 3),
                    "Z", z1 - 0.0007, z1 - 0.00015, bo, col)
        bevel(ins, 0.0002, 1)
        parts.append(ins)
        # flap knuckle along the hinge between the housing knuckles (gunmetal)
        k = lathe(name + "Knuckle", [(0.0, YW0), (0.0016, YW0), (0.0016, YW1), (0.0, YW1)], "Y", (x_h, 0, ZH),
                  steps=12, mats=gm, col=col)
        smooth(k, 35)
        parts.append(k)
        # emitter slit on the inner face (underside when folded): dark lens strip + ice emitter line
        xa, xb = sorted((x_i + sx * 0.0024, x_i + sx * 0.0068))
        parts.append(box(name + "EmWin", xa, xb, YW0 + 0.0080, YW1 - 0.0040, z0 - 0.0002, z0 + 0.0002, dk, col))
        xa, xb = sorted((x_i + sx * 0.0036, x_i + sx * 0.0056))
        parts.append(box(name + "Em", xa, xb, YW0 + 0.0090, YW1 - 0.0050, z0 - 0.00035, z0 - 0.0001, M["emitter"],
                         col))
        return parts

    flap_l = flap(1, P + "_FlapLPlate")
    flap_r = flap(-1, P + "_FlapRPlate")

    # the hologram: one square quad, frame sized from the PIL texture layout so the corner-bracket frame covers
    # PROJ_FRAME of the screen at the effective ADS FOV, PROJ_HOLO_DIST from the eye
    lay = M["holo_layout"]
    tv = math.tan(math.radians(ads_vfov("optic_projector")) / 2)
    th = tv * 16 / 9
    fw_half = PROJ_FRAME[0] * th * PROJ_HOLO_DIST
    fh_half = PROJ_FRAME[1] * tv * PROJ_HOLO_DIST
    QH = fw_half * lay["size"] / lay["frame_px"][0]
    holo = decal_quad(P + "_HologramQuad", (0.0, YH, SL), QH, +1, mat=M["hologram"], col=col, mirror_u=True)
    return dict(body=body, flap_l=flap_l, flap_r=flap_r, hologram=[holo], ads=ads,
                clamps=[(-0.0240, 0.0240)], eye_relief=ER, rear_y=YPR + 0.0012, magnification=1.0,
                recommended_for=["MAKO"], default_for=[], kind="flip-up projected holographic (no glass)",
                keep_uv=("Reticle", "Glint", "Hologram"),
                pivots={"Flap_L": ((HX, 0.0, ZH), OPEN), "Flap_R": ((-HX, 0.0, ZH), -OPEN)},
                origins={"Hologram": (0.0, YH, SL)}, anim=True,
                holo_info={"distance_from_eye_m": PROJ_HOLO_DIST, "plane_y_m": round(YH, 4),
                          "quad_m": round(2 * QH, 4),
                          "frame_mm": [round(2000 * fw_half, 1), round(2000 * fh_half, 1)],
                          "frame_frac_screen": list(PROJ_FRAME), "texture_px": lay["size"],
                          "frame_px_in_texture": lay["frame_px"]},
                folded_height_m=round(ZH + 0.0016 - JAW_BOT, 4), folded_height_above_rail_m=round(ZH + 0.0016, 4),
                reticle_desc="projected hologram, no glass: corner-bracket frame %d x %d mm at %.2f m from the eye "
                             "(%d %% x %d %% of the screen), centre dot in a gapped ring, three range ticks "
                             "(white-on-transparent texture tinted ice)" % (
                                 round(2000 * fw_half), round(2000 * fh_half), PROJ_HOLO_DIST,
                                 round(100 * PROJ_FRAME[0]), round(100 * PROJ_FRAME[1])))


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
    # r2: the top is tall at the front and slopes down toward the eye, so the sight tapers toward the shooter (the
    # old brow sloped the other way and the side silhouette read the same from both ends)
    cut(hs, prism("_c", [(-0.0250, 0.0150), (0.0240, 0.0150), (0.0240, 0.0625), (0.0200, 0.0655),
                         (-0.0040, 0.0750), (-0.0215, 0.0750), (-0.0250, 0.0715)], "X", -0.03, 0.03),
        op="INTERSECT")
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
    body.append(cap_turret(P + "_TurretElev", "Z", 1, 0.0742, 0.0092, 0.0090, 0.0064, (0.0, -0.0128, 0), steps=24,
                           knurl=0.0))
    body.append(cap_turret(P + "_TurretWind", "X", -1, -0.0206, 0.0090, 0.0088, 0.0062, (0, 0.0040, AX), steps=24,
                           knurl=0.0))
    body.append(cap_turret(P + "_IllumDial", "X", 1, 0.0206, 0.0108, 0.0070, 0.0050, (0, 0.0040, AX),
                           steps=28, knurl=0.0007))

    # objective bell (front) and eyepiece (rear): mats 0 graphite, 1 rubber, 2 dark
    # r2: longer (+8 mm) and wider (+2 mm) flared objective bell, stubby rubber eyecup (-6 mm): front / back read
    obj = lathe(P + "_Objective", [(0.0, -0.0676), (0.0181, -0.0676), (0.0181, -0.0748), (0.0203, -0.0748),
                                   (0.0216, -0.0735), (0.0216, -0.0718, "k"), (0.0216, -0.0560, "k"),
                                   (0.0209, -0.0535), (0.0160, -0.0360), (0.0160, -0.0220), (0.0, -0.0220)],
                "Y", (0, 0, AX), steps=32, mats=[g, rb, dk], seg_mat=[2, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                knurl=0.0007, col=col)
    smooth(obj, 25)
    body.append(obj)
    eye = lathe(P + "_Eyepiece", [(0.0, 0.0200), (0.0136, 0.0200), (0.0136, 0.0262), (0.0150, 0.0276),
                                  (0.0150, 0.0352), (0.0158, 0.0366), (0.0166, 0.0488), (0.0158, 0.0508),
                                  (0.0124, 0.0508), (0.0124, 0.0480), (0.0, 0.0480)],
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
    lens_o = lathe(P + "_LensObj", [(0.0, -0.0694), (0.0090, -0.0691), (0.0179, -0.0683), (0.0179, -0.0678),
                                    (0.0, -0.0678)], "Y", (0, 0, AX), steps=32, mats=M["objective"], col=col)
    lens_e = lathe(P + "_LensEye", [(0.0, 0.0493), (0.0080, 0.0490), (0.0123, 0.0485), (0.0123, 0.0482),
                                    (0.0, 0.0482)], "Y", (0, 0, AX), steps=32, mats=M["ocular"], col=col)
    for o in (lens_o, lens_e):
        smooth(o, 40)
    # illuminated reticle centre on the ocular (faces the eye): reads from behind in third person / hip; the game
    # hides it when it draws its scope overlay on the Ocular node
    dot = decal(P + "_RetDot", (0.0, 0.04935, AX), 0.0, 0.0005, +1, n=12, mat=M["ice"], col=col)
    ads = (0.0, 0.0508, AX)
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
    # r2: the sunshade's inner wall is lined in a light-catching dark slate (4) instead of graphite / near-black, so
    # the front no longer reads as an empty black tube (with the saturated blue M_ATT_LensObjectiveDeep)
    seg = [2, 2, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 3, 3, 0, 0, 0, 4, 2, 2]
    tube = lathe(P + "_Tube", prof, "Y", (0, 0, AX), steps=32, mats=[g, rb, dk, ic, M["shade"]], seg_mat=seg,
                 knurl=0.0009, col=col)
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


BUILDERS = {"optic_reddot": build_reddot, "optic_holo": build_holo, "optic_projector": build_projector,
            "optic_3x": build_3x,
            "optic_sniper": build_sniper, "optic_thermal": build_thermal}


# =========================================================================================== assembly
# builder dict key -> (node suffix, catalog role). Every role is its own child node so the engine can treat it on
# its own: Glass = reflex window pane, Objective / Ocular = lenses of magnified optics (glint shader / scope view),
# Display = the thermal's rear screen, Reticle = ADS reticle (faces the eye), Glint = third-person reticle glint
# (faces forward), StatusLight = the thermal's LED.
PART_KEYS = (("body", "Body", "body"), ("glass", "Glass", "window_glass"), ("objective", "Objective", "objective"),
             ("ocular", "Ocular", "ocular"), ("display", "Display", "display"), ("reticle", "Reticle", "reticle"),
             ("glint", "Glint", "glint"), ("status", "StatusLight", "status_light"), ("flap_l", "Flap_L", "flap_l"),
             ("flap_r", "Flap_R", "flap_r"), ("hologram", "Hologram", "hologram"))
# parts that never block the view (ADS aperture / near-plane checks ignore them)
SEE_THROUGH = ("Glass", "Objective", "Ocular", "Display", "Reticle", "Glint", "StatusLight", "Hologram")
# optic_projector flap clip: ADS_Open, folded -> open in FLAP_OPEN_S (engine note: ~0.12 s), sampled at ANIM_FPS
ANIM_FPS = 100
FLAP_OPEN_S = 0.12
ANIM_END = int(round(FLAP_OPEN_S * ANIM_FPS))       # frame of the open pose (frame 0 = folded = rest pose)
HOLO_SHOW_FROM_ADS = 0.80
HOLO_FADE_S = 0.08


def clean_degenerate(obj, dist=2e-6):
    """Triangulate before collapsing bevel/boolean slivers, so export adds no zero-area triangles.

    Testing only polygon area misses collinear corners inside healthy n-gons. The
    exporter triangulates those corners into degenerate faces; clean the same
    triangle topology that will be delivered instead.
    """
    mod = obj.modifiers.new("_CleanupTriangulate", "TRIANGULATE")
    mod.quad_method = "FIXED"
    mod.ngon_method = "BEAUTY"
    mod.keep_custom_normals = True
    bc.apply_modifiers(obj, only=[mod.name])
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    # Store hardened corner normals in a regular loop layer so BMesh topology
    # operations carry them along instead of discarding Mesh custom normals.
    layer_name = "_cleanup_corner_normal"
    normals = bm.loops.layers.float_vector.new(layer_name) if obj.data.has_custom_normals else None
    if normals is not None:
        for face in bm.faces:
            for loop, index in zip(face.loops, obj.data.polygons[face.index].loop_indices):
                loop[normals] = obj.data.corner_normals[index].vector
    # Float32 export/import arithmetic can disagree at the 1e-11 QA boundary.
    min_area = 2e-11
    before = sum(f.calc_area() < min_area for f in bm.faces)
    if not before:
        bm.free()
        return obj
    for _pass in range(4):
        for d2 in (dist, 1e-5, 3e-5):
            bad = [f for f in bm.faces if f.calc_area() < min_area]
            if not bad:
                break
            es = list({e for f in bad for e in f.edges})
            bmesh.ops.dissolve_degenerate(bm, dist=d2, edges=es)
        # Dissolving can create n-gons; retest their actual export triangles.
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3],
                              quad_method="FIXED", ngon_method="BEAUTY")
        bad = [f for f in bm.faces if f.calc_area() < min_area]
        if bad:
            # Some bevel/boolean corner slivers resist edge dissolve despite
            # being only a few microns across. Weld only their own vertices.
            bmesh.ops.remove_doubles(bm, verts=list({v for f in bad for v in f.verts}), dist=3e-5)
        if not any(f.calc_area() < min_area for f in bm.faces):
            break
    after = sum(f.calc_area() < min_area for f in bm.faces)
    print("  %s: degenerate faces %d -> %d" % (obj.name, before, after))
    if after:
        bm.free()
        raise RuntimeError("%s still has %d degenerate triangles" % (obj.name, after))
    if normals is not None:
        bm.normal_update()
        repaired_normals = 0
        for face in bm.faces:
            average = sum((loop[normals] for loop in face.loops), Vector())
            # A collapsed sliver can inherit the old, ill-defined face's
            # opposing corner normals. Correct only those repaired faces.
            if average.length and average.normalized().dot(face.normal) < -0.5:
                for loop in face.loops:
                    loop[normals] = face.normal
                repaired_normals += 1
        if repaired_normals:
            print("  %s: corrected corner normals on %d repaired faces" % (obj.name, repaired_normals))
    bm.to_mesh(obj.data)
    bm.free()
    if normals is not None:
        attr = obj.data.attributes[layer_name]
        obj.data.normals_split_custom_set([tuple(item.vector) for item in attr.data])
        obj.data.attributes.remove(attr)
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
        j = bc.join(list(objs), P + "_" + key) if len(objs) > 1 else objs[0]
        j.name = j.data.name = P + "_" + key
        clean_degenerate(j)
        if key not in d.get("keep_uv", ()):         # textured decal quads keep their own 0..1 UVs
            bc.smart_uv(j)
            uv_density(j)
        pv = d.get("pivots", {}).get(key)
        org = pv[0] if pv else d.get("origins", {}).get(key)
        if org is not None:                          # node origin on the hinge axis / at the hologram centre
            j.data.transform(Matrix.Translation(-Vector(org)))
            j.location = org
        if pv:                                       # modeled FOLDED = the rest pose (identity rotation)
            j.rotation_mode = "QUATERNION"
            j.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            q_open = Quaternion((0.0, 1.0, 0.0), math.radians(pv[1]))
            j["fold_angle_deg"] = 0.0
            j["open_angle_deg"] = pv[1]
            j["hinge_axis_blender"] = [0.0, 1.0, 0.0]
            j["hinge_axis_gltf"] = [0.0, 0.0, -1.0]
            j["hinge_note"] = ("node origin is ON the hinge axis; rotation = axis-angle(hinge_axis, angle), angle from "
                               "fold_angle_deg (rest, hip fire) to open_angle_deg (ADS) in ~%.2f s" % FLAP_OPEN_S)
            j["open_rotation_gltf_xyzw"] = [round(v, 6) for v in _gltf_quat(q_open)]
            j["open_time_s"] = FLAP_OPEN_S
        if key == "Hologram":
            j["show_from_ads"] = HOLO_SHOW_FROM_ADS
            j["fade_in_s"] = HOLO_FADE_S
            j["tint_note"] = "white-on-transparent texture; tint = baseColorFactor / emissiveFactor (ice by default)"
        j.parent = root
        out[key] = j
    ads = empty(P + "_SOCKET_ADS", d["ads"], col, parent=root, size=0.01)
    ads["eye_relief_m"] = d["eye_relief"]
    ads["ads_zoom"] = ZOOM[oid]
    ads["note"] = "sight line at the rear of the reticle/eyepiece; camera eye point = +Y by eye_relief_m"
    ads["reticle"] = d.get("reticle_desc", "")
    meshes = [o for k, o in out.items() if k != "Hologram"]     # sizes = the optic, not the floating hologram
    bpy.context.view_layer.update()
    mn, mx = bc.world_bounds(meshes)
    root["optic_id"] = oid
    root["category"] = "optic"
    root["mount"] = "picatinny top rail; origin = clamp contact centre on rail top"
    root["ads_height_m"] = round(d["ads"][2], 4)
    root["length_m"] = round(mx.y - mn.y, 4)
    root["magnification"] = str(d["magnification"])
    root["eye_relief_m"] = d["eye_relief"]
    root["ads_zoom"] = ZOOM[oid]
    for _dkey, key, role in PART_KEYS:          # node names per role (glTF extras), e.g. ocular_node
        if key in out:
            root[role + "_node"] = out[key].name
    if d.get("anim"):
        root["ads_animation"] = "ADS_Open"
        root["ads_animation_note"] = ("flaps folded (rest, t = 0) -> open (t = %.2f s); play forward on ADS, reverse on "
                                      "release. The hologram is not in the clip: show it from %d %% ADS and fade it "
                                      "in over ~%.2f s" % (FLAP_OPEN_S, round(100 * HOLO_SHOW_FROM_ADS), HOLO_FADE_S))
        root["hologram_show_from_ads"] = HOLO_SHOW_FROM_ADS
        root["flap_open_time_s"] = FLAP_OPEN_S
        root["hologram_fade_in_s"] = HOLO_FADE_S
        root["suggested_zoom"] = ZOOM[oid]
    return root, out, ads, (mn, mx)


def _gltf_quat(q):
    """Blender (Z-up) quaternion -> glTF (Y-up) [x, y, z, w]: the exporter maps (x, y, z) -> (x, z, -y)."""
    return [q.x, q.z, -q.y, q.w]


def make_ads_anim(oid, parts, d):
    """optic_projector: one action `ADS_Open` on both flaps: frame 0 = folded (identity, the rest pose) -> frame
    ANIM_END = open (open_angle_deg about the hinge axis) at ANIM_FPS, i.e. FLAP_OPEN_S seconds, eased (Bezier).
    The hologram is not animated (the engine shows it from HOLO_SHOW_FROM_ADS and fades it in)."""
    sc = bpy.context.scene
    sc.render.fps = ANIM_FPS
    sc.render.fps_base = 1.0
    sc.frame_start, sc.frame_end = 0, ANIM_END
    act = bpy.data.actions.new("ADS_Open")
    for key in ("Flap_L", "Flap_R"):
        o = parts[key]
        o.animation_data_create()
        o.animation_data.action = act
        o.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        o.keyframe_insert("rotation_quaternion", frame=0)
        o.rotation_quaternion = Quaternion((0.0, 1.0, 0.0), math.radians(d["pivots"][key][1]))
        o.keyframe_insert("rotation_quaternion", frame=ANIM_END)
    sc.frame_set(0)
    print("ADS_Open animation on", oid, "(%d frames at %d fps)" % (ANIM_END, ANIM_FPS))


def set_pose(results, frame):
    """Pose every animated optic (projector flaps): 0 = folded, ANIM_END = open."""
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()


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


def world_mesh(objs):
    """(vertices, polygons) of the evaluated meshes in world space (hinged parts carry an object transform)."""
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        mw = o.matrix_world
        base = len(verts)
        verts += [mw @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        ev.to_mesh_clear()
    return verts, polys


def world_bvh(objs):
    v, p = world_mesh(objs)
    return BVHTree.FromPolygons(v, p)


def fit_check(oid, body, glass, clamps, rail):
    """BVH test: no triangle of the optic may intersect the dummy rail, and every clamp must touch the rail
    top + both flanks (nearest optic surface within 0.3 mm of sample points on the rail)."""
    dg = bpy.context.evaluated_depsgraph_get()
    rb = BVHTree.FromObject(rail, dg)
    res = {"intersections": 0, "samples": []}
    for o in [body] + glass:
        ob = world_bvh([o])
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
    anim = any(o.animation_data and o.animation_data.action for o in objs)
    bpy.context.scene.frame_set(0)               # rest pose written to the nodes = folded (flip-up optic)
    kw = dict(export_animations=True, export_animation_mode="ACTIONS", export_frame_range=True,
              export_force_sampling=True) if anim else dict(export_animations=False)
    bpy.ops.export_scene.gltf(filepath=base + ".glb", export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_extras=True, **kw)
    bpy.ops.export_scene.fbx(filepath=base + ".fbx", use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             use_mesh_modifiers=True, add_leaf_bones=False, path_mode="COPY",
                             embed_textures=True, use_custom_props=True, bake_anim=anim)
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


CULL_MATS = ("M_ATT_ReticleHolo", "M_ATT_ReticleDot", "M_ATT_IceGlint", "M_ATT_IceDot")


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


def measure_ads(oid, r, extra=(), base_vfov=None, res=(1920, 1080), grid=(240, 135)):
    """Measure the ADS sight picture of a 1x optic exactly as the 1920 x 1080 eye view shows it: one ray per pixel
    centre along the screen's centre row and centre column from the eye point (_SOCKET_ADS + Y * eye_relief), at the
    effective ADS FOV (default game FOV through the optic's zoom), against every opaque mesh of the optic (glass,
    reticle, glint and hologram are see-through) plus `extra` (the gun). Returns, in pixels and as fractions:
      - the clear window round the sight line (its four edges, width, height);
      - the frame / hood edge on the left, right and top: the run of occluded pixels from the window edge outward,
        until the world shows again ("to_screen_edge" if it never does);
      - the clear fraction of the whole screen (grid of rays).
    Screen right = -X (shooter's right)."""
    d = r["d"]
    occ = [o for k, o in r["parts"].items() if k not in SEE_THROUGH] + list(extra)
    bpy.context.view_layer.update()
    bvh = world_bvh(occ)
    eye = r["root"].matrix_world @ Vector(d["ads"]) + Vector((0, d["eye_relief"], 0))
    vf = ads_vfov(oid, base_vfov)
    W, H = res
    tv = math.tan(math.radians(vf) / 2)
    th = tv * W / H

    def occluded(u, v):                       # u, v in screen units [-1, 1], u right, v up
        return bvh.ray_cast(eye, Vector((-u * th, -1.0, v * tv)).normalized(), 10.0)[0] is not None

    row = [occluded(2 * (i + 0.5) / W - 1, 0.0) for i in range(W)]
    colm = [occluded(0.0, 1 - 2 * (j + 0.5) / H) for j in range(H)]

    def scan(arr, start, step):
        i = start
        while 0 <= i < len(arr) and not arr[i]:
            i += step
        edge = i                              # first occluded pixel (or one past the screen edge)
        j = i
        while 0 <= j < len(arr) and arr[j]:
            j += step
        return edge, abs(j - i), not (0 <= j < len(arr))

    le, lt, l_end = scan(row, W // 2 - 1, -1)
    re_, rt, r_end = scan(row, W // 2, +1)
    te, tt, t_end = scan(colm, H // 2 - 1, -1)
    be, bt, b_end = scan(colm, H // 2, +1)
    win_w, win_h = re_ - le - 1, be - te - 1
    gw, gh = grid
    ok = sum(not occluded(2 * (i + 0.5) / gw - 1, 1 - 2 * (j + 0.5) / gh) for i in range(gw) for j in range(gh))
    res_ = {"res_px": [W, H], "vfov_deg": round(vf, 2), "hfov_deg": round(2 * math.degrees(math.atan(th)), 2),
            "eye_m": [round(v, 4) for v in eye],
            "window_px": {"left": le + 1, "right": re_ - 1, "top": te + 1, "bottom": be - 1, "width": win_w,
                          "height": win_h},
            "window_frac_w": round(win_w / W, 3), "window_frac_h": round(win_h / H, 3),
            "frame_px": {"left": lt, "right": rt, "top": tt, "bottom_body": bt},
            "frame_to_screen_edge": {"left": l_end, "right": r_end, "top": t_end},
            "frame_frac_w": {"left": round(lt / W, 4), "right": round(rt / W, 4), "top": round(tt / W, 4)},
            "screen_clear_frac": round(ok / (gw * gh), 3)}
    tgt = WINDOW_TARGET.get(oid)
    if tgt:
        edge_ok = max(lt, rt, tt) <= FRAME_EDGE_MAX * W and not (l_end or r_end or t_end)
        res_["targets"] = {"window_frac_w_min": tgt[0], "window_frac_h_min": tgt[1], "frame_frac_w_max": FRAME_EDGE_MAX,
                           "window_ok": res_["window_frac_w"] >= tgt[0] and res_["window_frac_h"] >= tgt[1],
                           "frame_ok": edge_ok}
    if "holo_info" in d:                     # projector: where the projected frame sits on screen
        hz = d["holo_info"]
        dist = hz["distance_from_eye_m"]
        fw, fh = hz["frame_mm"][0] / 2000.0, hz["frame_mm"][1] / 2000.0
        res_["hologram_frame_px"] = {"width": round(fw / dist / th * W, 1), "height": round(fh / dist / tv * H, 1)}
        res_["hologram_frame_frac"] = [round(fw / dist / th, 3), round(fh / dist / tv, 3)]
    print("ADS %s @ %.1f deg vFOV %dx%d: window %d x %d px [x %d..%d, y %d..%d] (%.0f %% W x %.0f %% H), frame L/R/T %d/%d/%d px "
          "(max %.1f %% W)%s, %.0f %% of the screen clear%s" % (
              oid, vf, W, H, win_w, win_h, le + 1, re_ - 1, te + 1, be - 1, 100 * res_["window_frac_w"], 100 * res_["window_frac_h"], lt, rt, tt,
              100 * max(lt, rt, tt) / W, " TO SCREEN EDGE" if (l_end or r_end or t_end) else "",
              100 * res_["screen_clear_frac"],
              "" if not tgt else ("  -> window %s, frame %s" % ("OK" if res_["targets"]["window_ok"] else "FAIL",
                                                               "OK" if res_["targets"]["frame_ok"] else "FAIL"))))
    return res_


def measure_on_gun(results, key="MAKO"):
    """Snap every 1x optic onto <GUN>_SOCKET_Optic (read-only gun import) and measure its ADS picture with the gun in
    the way (default game FOV and, for reference, render.rs's hard-coded 78 deg). Falls back to the optic alone."""
    g = load_gun(key)
    objs, gun_meshes, loc = g if g else ([], [], Vector((0, 0, 0)))
    set_pose(results, ANIM_END)
    for oid, r in results.items():
        if r["d"]["magnification"] != 1.0:
            continue
        r["root"].location = loc
        bpy.context.view_layer.update()
        am = measure_ads(oid, r, gun_meshes)
        am["on"] = key if g else "optic alone"
        alone = measure_ads(oid, r, ())                # the optic's own window (no gun rail in the lower edge)
        am["optic_window_px"] = alone["window_px"]
        am["optic_window_frac"] = [alone["window_frac_w"], alone["window_frac_h"]]
        r["fit"]["ads_measure"] = am
        r["fit"]["ads_measure_render_rs_78"] = measure_ads(oid, r, gun_meshes, base_vfov=RENDER_RS_VFOV)
        r["root"].location = (0, 0, 0)
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    set_pose(results, 0)


def near_check(oid, r):
    """Nearest optic vertex inside the ADS view frustum (game FOV, 16:9) measured along the view axis from the eye
    point: must be >= NEAR_MIN so the game's 0.03 m near plane never clips the optic while aiming."""
    d = r["d"]
    occ = [o for k, o in r["parts"].items() if k not in ("Reticle", "Glint", "Hologram")]
    verts, _p = world_mesh(occ)
    eye = Vector(d["ads"]) + Vector((0, d["eye_relief"], 0))
    # the wider of the two game FOVs (settings default vs render.rs's 78 deg) sees more of the optic
    tv = math.tan(math.radians(max(ads_vfov(oid), ads_vfov(oid, RENDER_RS_VFOV))) / 2)
    th = tv * 16 / 9
    best = 9.0
    for v in verts:
        rel = v - eye
        depth = -rel.y
        if depth <= 1e-6:
            continue
        if abs(rel.x) <= depth * th and abs(rel.z) <= depth * tv:
            best = min(best, depth)
    ok = best >= NEAR_MIN - 1e-6
    print("NEAR CHECK %s: nearest optic point in the ADS view %.1f mm from the eye (min %.1f) -> %s" % (
        oid, best * 1000, NEAR_MIN * 1000, "OK" if ok else "FAIL"))
    return {"nearest_in_view_m": round(best, 4), "near_plane_m": NEAR_PLANE, "ok": ok}


def ads_render(path, oid, r, extra_meshes=(), res=None, samples=32):
    """First-person ADS render at the effective ADS FOV (default game FOV through the optic's zoom) from the eye point
    (_SOCKET_ADS + Y * eye_relief), 1920 x 1080 for the 1x sights, on a temporary range: sky world, sun, ground,
    man-sized targets at 25 m (head on the sight line) and 10 m (1.2 m to the side), so the window size and the
    reticle scale can be judged. Flip-up optics are posed open with the hologram showing."""
    sc = bpy.context.scene
    d = r["d"]
    if res is None:
        res = (1920, 1080) if d["magnification"] == 1.0 else (1280, 720)
    if d.get("anim"):
        sc.frame_set(ANIM_END)
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
    cd.angle_y = math.radians(ads_vfov(oid))
    cd.clip_start = NEAR_PLANE              # the game camera near plane: the render shows any clipping
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
    if any(o.animation_data for o in meshes):
        bpy.context.scene.frame_set(ANIM_END)     # flip-up optic: the main views show it OPEN, hologram on
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
        if oid == "optic_holo":
            # bone hue check (review r2): the concept-angle view with the Standard view transform, for the v09 sheet
            vs = bpy.context.scene.view_settings
            old = (vs.view_transform, vs.look)
            try:
                vs.view_transform = "Standard"
                vs.look = "None"
                paths += bc.render_views(REN, pre + "_std", objs=meshes, views=((0.85, -0.75, 0.5),),
                                         res=(RES, RES), engine="CYCLES", samples=SAMPLES, lens=85)
            finally:
                vs.view_transform, vs.look = old
    if any(o.animation_data for o in meshes):
        # flip-up optic: FOLDED (hip fire, rest pose, frame 0) and HALF open (ADS ~50 %), hologram hidden (the engine
        # shows it from 80 % ADS); the main views above are the OPEN pose with the hologram
        solid = [o for o in meshes if not o.name.endswith("_Hologram")]
        sc = bpy.context.scene
        sc.frame_set(0)
        views_f = ("three_quarter", "right") if mode == "quick" else ("three_quarter", "right", "left", "front",
                                                                      "back", "three_quarter_back", "top",
                                                                      (0.85, -0.75, 0.5))
        set_visible(solid)
        paths += bc.render_views(REN, pre + "_folded", objs=solid, views=views_f, res=(RES, RES), engine="CYCLES",
                                 samples=SAMPLES, lens=85)
        if mode != "quick":
            set_visible(solid + rail_objs)
            paths += bc.render_views(REN, pre + "_folded_onrail", objs=solid, views=("three_quarter",),
                                     res=(RES, RES), engine="CYCLES", samples=SAMPLES, lens=85, margin=1.25)
            sc.frame_set(ANIM_END // 2)           # opening (half way through the 0.12 s flap motion)
            set_visible(solid)
            paths += bc.render_views(REN, pre + "_half", objs=solid, views=("three_quarter", "right", "front"),
                                     res=(RES, RES), engine="CYCLES", samples=SAMPLES, lens=85)
            sc.frame_set(ANIM_END)                # open, framed on the optic (hologram cropped / behind)
            set_visible(meshes)
            paths += bc.render_views(REN, pre + "_open", objs=solid, views=("three_quarter", "front",
                                                                            (0.55, 1.0, 0.35)),
                                     res=(RES, RES), engine="CYCLES", samples=SAMPLES, lens=85, margin=1.35)
        sc.frame_set(ANIM_END)
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
            if r["d"].get("anim") and key == r["d"]["recommended_for"][0]:   # flip-up optic: also folded (hip)
                sc_ = bpy.context.scene
                sc_.frame_set(0)
                solid = [o for o in meshes if not o.name.endswith("_Hologram")]
                set_visible(gun_meshes + solid)
                mn2, mx2 = bc.world_bounds(solid)
                paths += bc.render_views(out_dir, pre + "_folded", objs=solid, views=("right",),
                                         res=(RES, int(RES * 0.6)), engine="CYCLES", samples=SAMPLES, lens=85,
                                         focus=((mn2 + mx2) / 2, max(0.10, (mx2.y - mn2.y) * 0.62)))
                paths += bc.render_views(out_dir, pre + "_folded", objs=gun_meshes + solid, views=("three_quarter",),
                                         res=(RES, int(RES * 0.6)), engine="CYCLES", samples=SAMPLES, lens=85,
                                         margin=0.75)
                sc_.frame_set(ANIM_END)
                set_visible(gun_meshes + meshes)
            if ads and key == r["d"]["recommended_for"][0]:   # first-person ADS view on its main gun
                paths.append(ads_render(os.path.join(out_dir, "ATT_%s_ads_on%s.png" % (oid, key.lower())), oid, r,
                                        gun_meshes))
            r["root"].location = (0, 0, 0)
        for o in objs:
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.context.view_layer.update()
    return paths


CLOSEUPS = {
    "optic_reddot": {"lens": ((0, -0.006, 0.045), 0.026, (0.6, 1.0, 0.45)),
                     "front": ((0, -0.010, 0.040), 0.028, (0.45, -1.0, 0.30))},
    "optic_holo": {"window": ((0, 0.020, 0.045), 0.036, (0.55, 1.0, 0.35)),
                   "front_bezel": ((0, 0.008, 0.045), 0.036, (0.45, -1.0, 0.30)),
                   "buttons": ((0, -0.010, 0.017), 0.030, (0.9, -0.8, 0.6)),
                   "rightside": ((-0.023, 0.012, 0.020), 0.034, (-1.0, -0.35, 0.25)),
                   "rear": ((0, 0.025, 0.030), 0.040, (-0.3, 1.0, 0.25))},
    "optic_projector": {"hinge": ((0.014, -0.002, 0.026), 0.026, (0.9, -0.55, 0.55)),
                        "emitters": ((0.0, 0.000, 0.030), 0.030, (0.25, 1.0, 0.55)),
                        "spine_nose": ((0.0, -0.022, 0.020), 0.026, (0.55, -0.9, 0.55))},
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
        if d.get("anim"):
            make_ads_anim(oid, parts, d)
            bpy.context.view_layer.update()
            mn, mx = bc.world_bounds([o for k, o in parts.items() if k != "Hologram"])
        rail = make_rail("_Rail_" + oid, mn.y - 0.025, mx.y + 0.025, test_col, M)
        fit = fit_check(oid, parts["Body"], [o for k, o in parts.items() if k != "Body"], d["clamps"], rail[0])
        meshes = list(parts.values())
        tris = tri_count(meshes)
        results[oid] = dict(root=root, parts=parts, ads=ads, d=d, bounds=(mn, mx), rail=rail, fit=fit, tris=tris)
        if d.get("anim"):                      # flaps must swing clear of the housing (folded, half, open)
            fit["flap_clearance"] = {}
            for fr in (0, ANIM_END // 2, ANIM_END):
                sc.frame_set(fr)
                bpy.context.view_layer.update()
                bb = world_bvh([parts["Body"]])
                n = 0
                for k in ("Flap_L", "Flap_R"):
                    pairs = world_bvh([parts[k]]).overlap(bb)
                    n += len(pairs)
                    if pairs and "--debug" in ARGS:
                        fv, fp = world_mesh([parts[k]])
                        bv, bp = world_mesh([parts["Body"]])
                        for (i, j) in pairs[:6]:
                            ci = sum((fv[v] for v in fp[i]), Vector()) / len(fp[i])
                            cj = sum((bv[v] for v in bp[j]), Vector()) / len(bp[j])
                            print("   overlap %s face @ %s  x body face @ %s" % (
                                k, tuple(round(c, 4) for c in ci), tuple(round(c, 4) for c in cj)))
                n += len(world_bvh([parts["Flap_L"]]).overlap(world_bvh([parts["Flap_R"]])))
                fit["flap_clearance"]["frame_%d" % fr] = n
            print("FLAP CLEARANCE %s: intersections per pose %s -> %s" % (
                oid, fit["flap_clearance"], "OK" if not any(fit["flap_clearance"].values()) else "FAIL"))
            sc.frame_set(ANIM_END)
        fit["near_plane"] = near_check(oid, results[oid])
        sc.frame_set(0)
        print("OPTIC %s tris=%d  size=(%.4f, %.4f, %.4f)  ads=%s" % (
            oid, tris, mx.x - mn.x, mx.y - mn.y, mx.z - mn.z, tuple(round(v, 4) for v in d["ads"])))
        for o in meshes:
            print("    %-34s %6d tris" % (o.name, tri_count([o])))
    # 1x sights: measure the ADS sight picture (1920 x 1080, effective ADS FOV) mounted on the Mako
    measure_on_gun(results, "MAKO")

    if DO_EXPORT and not ONLY:
        for oid, r in results.items():
            export_optic(oid, r["root"])
        import shutil                           # the projector's reticle PNG next to its exports
        shutil.copyfile(M["holo_png"], os.path.join(OUT, "ATT_optic_projector_Hologram.png"))
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
                "ads_zoom": ZOOM[oid],
                "ads_zoom_note": "mirrors game/assets/data/attachments.ron zoom (projector: suggested, not in the "
                                 "game data yet)" if oid == "optic_projector" else
                                 "mirrors game/assets/data/attachments.ron zoom",
                "nodes": node_roles(oid, r["parts"]),
                "ocular_node": r["parts"]["Ocular"].name if "Ocular" in r["parts"] else (
                    r["parts"]["Display"].name if "Display" in r["parts"] else None),
                "objective_node": r["parts"]["Objective"].name if "Objective" in r["parts"] else None,
                "reticle_node": r["parts"]["Reticle"].name if "Reticle" in r["parts"] else None,
                "glint_node": r["parts"]["Glint"].name if "Glint" in r["parts"] else None,
                "hologram_node": r["parts"]["Hologram"].name if "Hologram" in r["parts"] else None,
                "reticle": d.get("reticle_desc", ""),
                "length_m": round(mx.y - mn.y, 4),
                "width_m": round(mx.x - mn.x, 4),
                "height_m": round(mx.z - mn.z, 4),
                "size_note": "folded, without the floating hologram" if d.get("anim") else "",
                "magnification": str(d["magnification"]),
                "kind": d["kind"],
                "sockets_accepted": ["_SOCKET_Optic"],
                "compatible_weapons": COMPAT[oid],
                "recommended_for": d["recommended_for"],
                "default_for": d["default_for"],
                "tris": r["tris"],
                "rail_fit_ok": r["fit"]["ok"],
                "near_plane_ok": r["fit"]["near_plane"]["ok"],
                "nearest_in_view_m": r["fit"]["near_plane"]["nearest_in_view_m"],
            })
            if "ads_measure" in r["fit"]:
                am = r["fit"]["ads_measure"]
                a78 = r["fit"]["ads_measure_render_rs_78"]
                ap = {"measured_on": am["on"], "res_px": am["res_px"],
                      "effective_vfov_deg": am["vfov_deg"],
                      "fov_source": "settings.ron fov_h %g (= %.1f deg vertical) through zoom %g (settings/model.rs "
                                    "zoomed_fov)" % (GAME_FOV_H, GAME_VFOV, ZOOM[oid]),
                      "clear_window_px": [am["window_px"]["width"], am["window_px"]["height"]],
                      "clear_window_frac_screen": [am["window_frac_w"], am["window_frac_h"]],
                      "clear_window_note": "on the Mako: the lower edge is the gun's own rail / handguard",
                      "optic_window_px": [am["optic_window_px"]["width"], am["optic_window_px"]["height"]],
                      "optic_window_frac_screen": am["optic_window_frac"],
                      "frame_edge_px": am["frame_px"], "frame_edge_frac_screen_w": am["frame_frac_w"],
                      "screen_clear_frac": am["screen_clear_frac"],
                      "at_render_rs_78deg": {"effective_vfov_deg": a78["vfov_deg"],
                                             "clear_window_frac_screen": [a78["window_frac_w"], a78["window_frac_h"]],
                                             "frame_edge_frac_screen_w": a78["frame_frac_w"]}}
                if "targets" in am:
                    ap["targets"] = am["targets"]
                if "hologram_frame_frac" in am:
                    ap["hologram_frame_frac_screen"] = am["hologram_frame_frac"]
                    ap["hologram_frame_px"] = am["hologram_frame_px"]
                base = ({"rear_window_mm": d.get("window_mm"), "front_window_mm": d.get("front_window_mm"),
                         "window_above_below_sight_line_mm": d.get("window_above_below_sight_line_mm"),
                         "frame_mm": d.get("frame_mm"), "eye_to_rear_face_m": d.get("eye_to_rear_face_m"),
                         "note": "window walls and hood flanks lie on the eye's view cone: the front window looks "
                                 "exactly as big as the rear one from the eye point and no wall shows"}
                        if d.get("window_mm") else
                        {"note": "no glass and no window: the view is open; the reticle frame is projected"})
                base["ads"] = ap
                catalog[-1]["aperture"] = base
            if d.get("anim"):
                hz = d["holo_info"]
                catalog[-1]["projector"] = {
                    "hologram_node": r["parts"]["Hologram"].name,
                    "hologram_texture": "textures/T_ATT_ProjectorHologram.png (copy: ATT_optic_projector_Hologram.png)",
                    "hologram_material": "M_ATT_ProjectorHologram: white texture x tint (baseColorFactor / "
                                         "emissiveFactor = ice), alpha BLEND, double-sided",
                    "hologram_distance_from_eye_m": hz["distance_from_eye_m"],
                    "hologram_quad_m": hz["quad_m"], "hologram_frame_mm": hz["frame_mm"],
                    "hologram_frame_frac_screen": hz["frame_frac_screen"],
                    "hologram_show_from_ads": HOLO_SHOW_FROM_ADS, "hologram_fade_in_s": HOLO_FADE_S,
                    "suggested_zoom": ZOOM[oid], "folded_height_m": d["folded_height_m"],
                    "folded_height_above_rail_m": d["folded_height_above_rail_m"],
                    "animation": {"clip": "ADS_Open", "duration_s": FLAP_OPEN_S, "rest_pose": "folded",
                                  "play": "forward on ADS, reverse on release"},
                    "flaps": [{"node": r["parts"][k].name, "hinge_origin_m": list(d["pivots"][k][0]),
                               "hinge_axis_blender": [0, 1, 0], "hinge_axis_gltf": [0, 0, -1],
                               "fold_angle_deg": 0.0, "open_angle_deg": d["pivots"][k][1],
                               "open_rotation_gltf_xyzw": list(r["parts"][k]["open_rotation_gltf_xyzw"])}
                              for k in ("Flap_L", "Flap_R")]}
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
                pose = ""
                for pz in ("folded_", "half_"):           # flip-up optic: folded (hip) / half-open pose
                    if vv.startswith(pz):
                        pose = pz[:-1]
                        vv = vv[len(pz):]
                anim = any(o.animation_data for o in meshes)
                if pose and not anim:
                    continue
                sc.frame_set({"folded": 0, "half": ANIM_END // 2}.get(pose, ANIM_END))
                vis = [o for o in meshes if not (pose and o.name.endswith("_Hologram"))]
                set_visible(vis + (r["rail"] if rail else []))
                pre = "%s_%s%s%s" % (oid, TAG + "_" if TAG else "", "rail" if rail else "x", "_" + pose if pose else "")
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
                vd = vv if vv in bc.VIEW_DIRS else tuple(float(x) for x in vv.lstrip("v").split("_"))
                made += bc.render_views(itd, pre, objs=vis, views=(vd,), res=(RES, RES), engine="CYCLES",
                                        samples=SAMPLES, lens=85, margin=1.2 if rail else 1.12)
        if VIEWS and "gun" in VIEWS.split(","):
            made += render_on_guns(results, itd)
        with open(os.path.join(itd, "_last.json"), "w") as f:
            json.dump(made, f, indent=1)
        subprocess.run(["python", os.path.join(SOURCE, "make_sheets.py"), "--iter", os.path.join(itd, "_last.json"),
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
            subprocess.run(["python", os.path.join(SOURCE, "make_sheets.py"), "--out", OUT], check=True, timeout=300)
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
        for image in bpy.data.images:
            if image.filepath and os.path.dirname(os.path.abspath(image.filepath)) == TEXDIR:
                image.filepath = "//textures/" + os.path.basename(image.filepath)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "optics.blend"), compress=True)
        print("saved", os.path.join(OUT, "optics.blend"))


main()
