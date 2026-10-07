"""Geometry + material library for the HALO shield kit (imported by build_halo.py).

Conventions (art/STYLE_GUIDE.md + art/HALO_SHIELD_SPEC.md):
  metres, Z up, the wearer faces -Y.  Halo lies in the XY plane, origin = halo centre.
  Arc zones (seen from above): Head = front (-Y, 270 deg), Arms = +X (0 deg), Torso = back (+Y, 90 deg),
  Legs = -X (180 deg).  Angles below are measured counter-clockwise from +X.
"""
import math

import bmesh
import bpy
from mathutils import Vector

D = math.radians

ZONES = {"Arms": 0.0, "Torso": 90.0, "Legs": 180.0, "Head": 270.0}
CORES = ("Bulwark", "Mender", "Volt", "Phase")
TIERS = {
    1: (0.85, 0.88, 0.92),   # white
    2: (0.10, 0.45, 1.00),   # blue
    3: (0.55, 0.15, 1.00),   # violet
    4: (1.00, 0.62, 0.08),   # gold
}
GRAPHITE = (0.030, 0.033, 0.040)
GUNMETAL = (0.11, 0.115, 0.12)
BONE = (0.55, 0.52, 0.46)
SMOKE = (0.02, 0.02, 0.025)

# Weight classes (engine data, also used by the showcase renders)
WEIGHT = {
    "Light": dict(scale=0.85, band=None, cells=1, orbit_r=0.215, orbit_z=0.004, orbit_period_s=2.6),
    "Medium": dict(scale=1.00, band="Medium", cells=2, orbit_r=0.245, orbit_z=0.004, orbit_period_s=3.4),
    "Heavy": dict(scale=1.20, band="Heavy", cells=3, orbit_r=0.275, orbit_z=0.004, orbit_period_s=4.6),
}

# Fixed tier-pip positions (halo-local, unscaled); PIP_1 is on the viewer's left when facing the wearer.
PIP_SPACING = 0.0160
PIP_Z = 0.0245
PIP_Y = -0.150
PIP_POS = [(-1.5 * PIP_SPACING + i * PIP_SPACING, PIP_Y, PIP_Z) for i in range(4)]


# ------------------------------------------------------------------------------------------ shapes
def circ(a, r):
    return (r * math.cos(a), r * math.sin(a))


HEX_NORMALS = [D(30 + 60 * k) for k in range(6)]   # flat edge facing the front (270 deg)
HEX_CORNERS = [60.0 * k for k in range(6)]          # degrees


def hexs(a, d):
    """Point on a hexagon with apothem d (flat edge at the front) in direction a (radians)."""
    k = round((math.degrees(a) - 30.0) / 60.0)
    n = D(30.0 + 60.0 * k)
    r = d / math.cos(a - n)
    return (r * math.cos(a), r * math.sin(a))


def arc_angles(a0, a1, step=2.5, corners=()):
    """Sample angles (degrees in, radians out) from a0 to a1 incl. any corner angles in between."""
    n = max(1, int(math.ceil(abs(a1 - a0) / step)))
    angs = [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    for c in corners:
        for cc in (c - 360, c, c + 360):
            if min(a0, a1) + 1e-4 < cc < max(a0, a1) - 1e-4:
                angs.append(cc)
    angs = sorted(set(round(x, 6) for x in angs), reverse=a1 < a0)
    return [D(x) for x in angs]


def hex_angles(a0, a1):
    """Hexagon edges are straight: only the ends + corners are needed (plus one mid point per edge)."""
    return arc_angles(a0, a1, step=15.0, corners=HEX_CORNERS)


def rounded_rect(w0, w1, z0, z1, c, n=2):
    """Closed (d, z) profile: rectangle d in [w0,w1], z in [z0,z1] with chamfer c (n=1) or rounded (n>1)."""
    pts = []
    corners = [((w1 - c, z1 - c), 0), ((w0 + c, z1 - c), 90), ((w0 + c, z0 + c), 180), ((w1 - c, z0 + c), 270)]
    # counter-clockwise starting at the outer-top corner
    for (cx, cz), start in corners:
        for i in range(n + 1):
            t = D(start + 90.0 * i / n)
            pts.append((cx + c * math.cos(t), cz + c * math.sin(t)))
    out = []
    for p in pts:
        if not out or (abs(out[-1][0] - p[0]) > 1e-7 or abs(out[-1][1] - p[1]) > 1e-7):
            out.append(p)
    return out


def ellipse(cd, cz, hw, hh, n=16):
    return [(cd + hw * math.cos(2 * math.pi * i / n), cz + hh * math.sin(2 * math.pi * i / n)) for i in range(n)]


# ------------------------------------------------------------------------------------------ builder
class MB:
    """bmesh mesh builder with per-face material indices."""

    def __init__(self):
        self.bm = bmesh.new()

    # sweep a closed (d, z) profile along a polar shape over the given angles (radians)
    def sweep(self, shape, profile, angles, mat=0, cap=True, scale_fn=None, pivot=None, loop=False,
              open_profile=False, zoff_fn=None):
        bm = self.bm
        if pivot is None:
            pivot = (sum(p[0] for p in profile) / len(profile), sum(p[1] for p in profile) / len(profile))
        rings = []
        for a in angles:
            s = scale_fn(a) if scale_fn else 1.0
            zo = zoff_fn(a) if zoff_fn else 0.0
            ring = []
            for d, z in profile:
                d2 = pivot[0] + (d - pivot[0]) * s
                z2 = pivot[1] + (z - pivot[1]) * s + zo
                x, y = shape(a, d2)
                ring.append(bm.verts.new((x, y, z2)))
            rings.append(ring)
        m = len(profile)
        faces = []
        nring = len(rings)
        jmax = m - 1 if open_profile else m
        for i in range(nring if loop else nring - 1):
            r0, r1 = rings[i], rings[(i + 1) % nring]
            for j in range(jmax):
                try:
                    faces.append(bm.faces.new((r0[j], r0[(j + 1) % m], r1[(j + 1) % m], r1[j])))
                except ValueError:
                    pass
        if cap and not loop and not open_profile:
            faces.append(bm.faces.new(rings[0]))
            faces.append(bm.faces.new(list(reversed(rings[-1]))))
        for f in faces:
            f.material_index = mat
        return faces

    def lathe(self, shape, profile, steps=48, mat=0, corners=()):
        """Revolve an OPEN (d, z) profile 360 deg (profile should start/end on the axis, d=0)."""
        if corners:
            angs = [D(c) for c in corners]
            extra = []
            for c in corners:
                extra += [D(c + 30.0)]
            angs = sorted(set(angs + extra))
        else:
            angs = [2 * math.pi * i / steps for i in range(steps)]
        faces = self.sweep(shape, profile, angs, mat=mat, cap=False, loop=True, open_profile=True)
        return faces

    def prism(self, poly, origin, au, av, aw, w0, w1, mat=0):
        """Extrude a 2D polygon [(u, v)] lying in the plane (au, av) through `origin` from w0 to w1 along aw."""
        bm = self.bm
        o, au, av, aw = Vector(origin), Vector(au), Vector(av), Vector(aw)
        b = [bm.verts.new(o + au * u + av * v + aw * w0) for u, v in poly]
        t = [bm.verts.new(o + au * u + av * v + aw * w1) for u, v in poly]
        faces = [bm.faces.new(list(reversed(b))), bm.faces.new(t)]
        n = len(poly)
        for i in range(n):
            faces.append(bm.faces.new((b[i], b[(i + 1) % n], t[(i + 1) % n], t[i])))
        for f in faces:
            f.material_index = mat
        return faces

    def box(self, center, au, av, aw, su, sv, sw, mat=0, chamfer=0.0):
        """Oriented box (optionally chamfered on its u/v edges) centred at `center`."""
        c = chamfer
        hu, hv = su / 2, sv / 2
        if c > 0:
            poly = [(-hu + c, -hv), (hu - c, -hv), (hu, -hv + c), (hu, hv - c), (hu - c, hv), (-hu + c, hv),
                    (-hu, hv - c), (-hu, -hv + c)]
        else:
            poly = [(-hu, -hv), (hu, -hv), (hu, hv), (-hu, hv)]
        return self.prism(poly, center, au, av, aw, -sw / 2, sw / 2, mat)

    def raw(self, verts, faces_idx, mat=0):
        bm = self.bm
        vs = [bm.verts.new(v) for v in verts]
        out = []
        for f in faces_idx:
            ff = bm.faces.new([vs[i] for i in f])
            ff.material_index = mat
            out.append(ff)
        return out

    def finish(self, name, mats, smooth_angle=32, col=None, recalc=True):
        bm = self.bm
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        if recalc:
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        obj = bpy.data.objects.new(name, me)
        for m in mats:
            me.materials.append(m)
        for p in me.polygons:
            p.use_smooth = True
        try:
            me.set_sharp_from_angle(angle=D(smooth_angle))
        except Exception:
            pass
        (col or bpy.context.scene.collection).objects.link(obj)
        return obj


def frame_at(shape, a, d, z=0.0, eps=1e-4):
    """Local frame on a polar shape: origin, tangent (ccw), outward normal (in plane), up."""
    p0 = Vector((*shape(a - eps, d), 0))
    p1 = Vector((*shape(a + eps, d), 0))
    t = (p1 - p0).normalized()
    n = Vector((t.y, -t.x, 0))  # outward for ccw travel
    o = Vector((*shape(a, d), z))
    return o, t, n, Vector((0, 0, 1))


# ------------------------------------------------------------------------------------------ glyphs
def _ring_poly(r_out, r_in, n=12):
    """Annulus as a list of quads (u, v)."""
    quads = []
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        quads.append([(r_in * math.cos(a0), r_in * math.sin(a0)), (r_out * math.cos(a0), r_out * math.sin(a0)),
                      (r_out * math.cos(a1), r_out * math.sin(a1)), (r_in * math.cos(a1), r_in * math.sin(a1))])
    return quads


def glyph_polys(zone, s=1.0):
    """Tiny pictogram per zone, (u = along the ring, v = outward).  ~10 mm.
    Head = ring (a head), Torso = chamfered block, Arms = twin bars, Legs = inverted V."""
    if zone == "Head":
        return _ring_poly(0.0050 * s, 0.0027 * s)
    if zone == "Torso":
        h, w, c = 0.0058 * s, 0.0042 * s, 0.0016 * s
        return [[(-w + c, -h), (w - c, -h), (w, -h + c), (w, h - c), (w - c, h), (-w + c, h), (-w, h - c),
                 (-w, -h + c)]]
    if zone == "Arms":
        bw, h, g = 0.0018 * s, 0.0060 * s, 0.0030 * s
        return [[(-g - bw, -h), (-g + bw, -h), (-g + bw, h), (-g - bw, h)],
                [(g - bw, -h), (g + bw, -h), (g + bw, h), (g - bw, h)]]
    if zone == "Legs":  # inverted V pointing outward (v+)
        t, h, sp = 0.0019 * s, 0.0060 * s, 0.0050 * s
        return [[(-sp - t, -h), (-sp + t, -h), (t * 0.9, h), (-t * 0.9, h)],
                [(sp - t, -h), (sp + t, -h), (t * 0.9, h), (-t * 0.9, h)]]
    raise ValueError(zone)


def add_glyph(mb, shape, a, d, z, zone, mat, h=0.0016, s=1.0):
    o, t, n, up = frame_at(shape, a, d, z)
    for poly in glyph_polys(zone, s):
        mb.prism(poly, o, t, n, up, 0.0, h, mat)


# ------------------------------------------------------------------------------------------ materials
def _mat(name, color, rough=0.5, metal=0.0, emission=None, strength=0.0, alpha=1.0, coat=0.0, spec=0.5):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    p = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")

    def si(names, v):
        for nm in names if isinstance(names, (list, tuple)) else [names]:
            if nm in p.inputs:
                p.inputs[nm].default_value = v
                return

    si("Base Color", (*color, 1))
    si("Roughness", rough)
    si("Metallic", metal)
    si(["Specular IOR Level", "Specular"], spec)
    if coat:
        si(["Coat Weight", "Clearcoat"], coat)
        si(["Coat Roughness"], 0.08)
    if emission is not None:
        si(["Emission Color", "Emission"], (*emission, 1))
        si("Emission Strength", strength)
    if alpha < 1.0:
        si("Alpha", alpha)
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:
            pass
        mat.use_backface_culling = False
    mat.diffuse_color = (*(emission if emission else color), 1)
    return mat


def make_materials():
    M = {}
    M["graphite"] = _mat("M_HALO_Graphite", GRAPHITE, rough=0.55, metal=0.15, spec=0.35)
    M["gunmetal"] = _mat("M_HALO_Gunmetal", GUNMETAL, rough=0.35, metal=0.85)
    M["bone"] = _mat("M_HALO_Bone", BONE, rough=0.6, metal=0.0)
    M["off"] = _mat("M_HALO_Glass_Off", SMOKE, rough=0.08, metal=0.0, alpha=0.55, coat=1.0, spec=0.8)
    for t, c in TIERS.items():
        base = tuple(0.12 * v for v in c)
        M[f"T{t}"] = _mat(f"M_HALO_Glass_T{t}", base, rough=0.25, emission=c, strength=2.4, coat=0.4, spec=0.5)
    return M


def set_strength(mat, s):
    p = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Emission Strength"].default_value = s
