"""Geometry + material library for the HALO shield kit (imported by build_halo.py).

Conventions (art/STYLE_GUIDE.md + art/HALO_SHIELD_SPEC.md):
  metres, Z up, the wearer faces -Y.  Halo lies in the XY plane, origin = halo centre.
  Arc zones (seen from above): Head = front (-Y, 270 deg), Arms = +X (0 deg), Torso = back (+Y, 90 deg),
  Legs = -X (180 deg).  Angles below are measured counter-clockwise from +X.

UVs: every sweep is unwrapped as a straight strip (U = distance along the arc, V = distance around the
profile, both in units of TILE metres), so tileable textures (the broken-arc crack map) run cleanly along
each arc.  Caps and prisms get planar UVs at the same density.
"""
import math

import bmesh
import bpy
from mathutils import Vector

D = math.radians

from halo_data import TIERS, WEIGHT_BANDS, WEIGHT_VISUALS, preset_tiers, weight_of  # noqa: F401

ZONES = {"Arms": 0.0, "Torso": 90.0, "Legs": 180.0, "Head": 270.0}
CORES = ("Bulwark", "Mender", "Volt", "Phase")
GRAPHITE = (0.030, 0.033, 0.040)
GUNMETAL = (0.11, 0.115, 0.12)
BONE = (0.55, 0.52, 0.46)
SMOKE = (0.02, 0.02, 0.025)
EDGE = (0.56, 0.66, 0.80)      # always-on frame light (cool steel), deliberately not a tier colour
EDGE_STRENGTH = 0.30
BROKEN_DESAT = 0.5             # broken arc: tier colour 50 % desaturated ...
BROKEN_STRENGTH = 1.0          # ... crack map 0.18 (dim body) .. 1.0 (glowing fracture lines) x this
TILE = 0.05                    # metres per UV unit

# Weight classes (art-side visuals; gameplay numbers are read from the game data in halo_data.py)
WEIGHT = WEIGHT_VISUALS


# ------------------------------------------------------------------------------------------ shapes
def circ(a, r):
    return (r * math.cos(a), r * math.sin(a))


HEX_CORNERS = [60.0 * k for k in range(6)]          # degrees


def hexs(a, d):
    """Point on a hexagon with apothem d (flat edge at the front) in direction a (radians)."""
    k = round((math.degrees(a) - 30.0) / 60.0)
    n = D(30.0 + 60.0 * k)
    r = d / math.cos(a - n)
    return (r * math.cos(a), r * math.sin(a))


def arc_angles(a0, a1, step=2.5, corners=()):
    """Sample angles (degrees in, radians out) from a0 to a1 incl. any corner angles in between."""
    n = max(1, int(math.ceil(abs(a1 - a0) / step - 1e-6)))
    angs = [a0 + (a1 - a0) * i / n for i in range(n + 1)]
    for c in corners:
        for cc in (c - 360, c, c + 360):
            if min(a0, a1) + 1e-4 < cc < max(a0, a1) - 1e-4:
                angs.append(cc)
    angs = sorted(set(round(x, 6) for x in angs), reverse=a1 < a0)
    return [D(x) for x in angs]


def hex_angles(a0, a1, step=15.0):
    """Hexagon edges are straight: the ends + corners are enough (plus a few points per edge for UVs/ticks)."""
    return arc_angles(a0, a1, step=step, corners=HEX_CORNERS)


def rounded_rect(w0, w1, z0, z1, c, n=1):
    """Closed (d, z) profile: rectangle d in [w0,w1], z in [z0,z1] with chamfer c (n=1) or rounded (n>1)."""
    pts = []
    corners = [((w1 - c, z1 - c), 0), ((w0 + c, z1 - c), 90), ((w0 + c, z0 + c), 180), ((w1 - c, z0 + c), 270)]
    for (cx, cz), start in corners:
        for i in range(n + 1):
            t = D(start + 90.0 * i / n)
            pts.append((cx + c * math.cos(t), cz + c * math.sin(t)))
    out = []
    for p in pts:
        if not out or (abs(out[-1][0] - p[0]) > 1e-7 or abs(out[-1][1] - p[1]) > 1e-7):
            out.append(p)
    if len(out) > 2 and abs(out[0][0] - out[-1][0]) < 1e-7 and abs(out[0][1] - out[-1][1]) < 1e-7:
        out.pop()
    return out


def ellipse(cd, cz, hw, hh, n=16):
    return [(cd + hw * math.cos(2 * math.pi * i / n), cz + hh * math.sin(2 * math.pi * i / n)) for i in range(n)]


class SegProfile:
    """Closed (d, z) profile with one material index per edge.  Build it from [(point, mat_of_next_edge)]."""

    def __init__(self, items):
        self.pts = [p for p, _ in items]
        self.mats = [m for _, m in items]

    def check(self, name=""):
        """Raise if the outline self-intersects (keeps hand-written profiles honest)."""
        P, n = self.pts, len(self.pts)

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]
            for j in range(i + 2, n):
                if (j + 1) % n == i:
                    continue
                c, d = P[j], P[(j + 1) % n]
                if (cross(a, b, c) * cross(a, b, d) < -1e-16) and (cross(c, d, a) * cross(c, d, b) < -1e-16):
                    raise ValueError(f"profile {name} self-intersects at edges {i} and {j}")
        return self


def _perimeter(pts, closed=True):
    acc = [0.0]
    for i in range(1, len(pts)):
        acc.append(acc[-1] + math.dist(pts[i - 1], pts[i]))
    if closed:
        acc.append(acc[-1] + math.dist(pts[-1], pts[0]))
    return acc


# ------------------------------------------------------------------------------------------ builder
class MB:
    """bmesh mesh builder with per-face material indices and strip UVs."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")

    def _uv(self, face, uvs):
        for loop, uv in zip(face.loops, uvs):
            loop[self.uv].uv = (uv[0] / TILE, uv[1] / TILE)

    # sweep a closed (d, z) profile along a polar shape over the given angles (radians)
    def sweep(self, shape, profile, angles, mat=0, cap=True, scale_fn=None, pivot=None, loop=False,
              open_profile=False, zoff_fn=None, cap_mat=None):
        """`mat` is one material index, or a list with one index per profile edge (edge j runs from
        profile[j] to profile[j+1]): one clean shell whose faces carry glass / frame / edge-light stripes."""
        bm = self.bm
        if isinstance(profile, SegProfile):
            mat, profile = profile.mats, profile.pts
        mats = mat if isinstance(mat, (list, tuple)) else None
        if cap_mat is None:
            cap_mat = max(set(mats), key=mats.count) if mats else mat
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
        # strip UVs: U = arc length along the pivot line, V = perimeter of the profile
        cl = [shape(a, pivot[0]) for a in angles]
        su = _perimeter(cl, closed=loop)
        pv = _perimeter(profile, closed=not open_profile)
        m = len(profile)
        faces = []
        nring = len(rings)
        jmax = m - 1 if open_profile else m
        for i in range(nring if loop else nring - 1):
            r0, r1 = rings[i], rings[(i + 1) % nring]
            u0, u1 = su[i], su[i + 1]
            for j in range(jmax):
                j1 = (j + 1) % m
                v0, v1 = pv[j], pv[j + 1]
                try:
                    f = bm.faces.new((r0[j], r0[j1], r1[j1], r1[j]))
                except ValueError:
                    continue
                self._uv(f, ((u0, v0), (u0, v1), (u1, v1), (u1, v0)))
                f.material_index = mats[j] if mats else mat
                faces.append(f)
        if cap and not loop and not open_profile:
            for ring, rev in ((rings[0], False), (rings[-1], True)):
                vs = list(reversed(ring)) if rev else ring
                prof = list(reversed(profile)) if rev else profile
                f = bm.faces.new(vs)
                self._uv(f, prof)
                f.material_index = cap_mat
                faces.append(f)
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
        return self.sweep(shape, profile, angs, mat=mat, cap=False, loop=True, open_profile=True)

    def prism(self, poly, origin, au, av, aw, w0, w1, mat=0):
        """Extrude a 2D polygon [(u, v)] lying in the plane (au, av) through `origin` from w0 to w1 along aw."""
        bm = self.bm
        o, au, av, aw = Vector(origin), Vector(au), Vector(av), Vector(aw)
        b = [bm.verts.new(o + au * u + av * v + aw * w0) for u, v in poly]
        t = [bm.verts.new(o + au * u + av * v + aw * w1) for u, v in poly]
        fb = bm.faces.new(list(reversed(b)))
        self._uv(fb, list(reversed(poly)))
        ft = bm.faces.new(t)
        self._uv(ft, poly)
        faces = [fb, ft]
        per = _perimeter(poly)
        n = len(poly)
        for i in range(n):
            f = bm.faces.new((b[i], b[(i + 1) % n], t[(i + 1) % n], t[i]))
            self._uv(f, ((per[i], w0), (per[i + 1], w0), (per[i + 1], w1), (per[i], w1)))
            faces.append(f)
        for f in faces:
            f.material_index = mat
        return faces

    def annulus(self, origin, au, av, aw, r_out, r_in, n, w0, w1, mat=0):
        """One welded annulus prism (a ring glyph) - no internal faces."""
        bm = self.bm
        o, au, av, aw = Vector(origin), Vector(au), Vector(av), Vector(aw)
        ang = [2 * math.pi * i / n for i in range(n)]
        P = lambda r, a, w: o + au * (r * math.cos(a)) + av * (r * math.sin(a)) + aw * w  # noqa: E731
        ob = [bm.verts.new(P(r_out, a, w0)) for a in ang]
        ot = [bm.verts.new(P(r_out, a, w1)) for a in ang]
        ib = [bm.verts.new(P(r_in, a, w0)) for a in ang]
        it = [bm.verts.new(P(r_in, a, w1)) for a in ang]
        faces = []
        for i in range(n):
            k = (i + 1) % n
            for quad in ((it[i], ot[i], ot[k], it[k]), (ib[k], ob[k], ob[i], ib[i]),
                         (ob[i], ob[k], ot[k], ot[i]), (ib[k], ib[i], it[i], it[k])):
                f = bm.faces.new(quad)
                self._uv(f, [((v.co - o).dot(au), (v.co - o).dot(av)) for v in quad])
                faces.append(f)
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
            self._uv(ff, [(verts[i][0], verts[i][2]) for i in f])
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
def glyph_polys(zone, s=1.0):
    """Tiny pictogram per zone, (u = along the ring, v = outward).  ~10 mm.
    Torso = chamfered block, Arms = twin bars, Legs = one welded chevron.  (Head = ring: see add_glyph.)"""
    if zone == "Torso":
        h, w, c = 0.0058 * s, 0.0042 * s, 0.0016 * s
        return [[(-w + c, -h), (w - c, -h), (w, -h + c), (w, h - c), (w - c, h), (-w + c, h), (-w, h - c),
                 (-w, -h + c)]]
    if zone == "Arms":
        bw, h, g = 0.0018 * s, 0.0060 * s, 0.0030 * s
        return [[(-g - bw, -h), (-g + bw, -h), (-g + bw, h), (-g - bw, h)],
                [(g - bw, -h), (g + bw, -h), (g + bw, h), (g - bw, h)]]
    if zone == "Legs":  # inverted V pointing outward (v+), one polygon (no coincident faces)
        t, h, sp = 0.0019 * s, 0.0060 * s, 0.0050 * s
        return [[(-sp - t, -h), (-sp + t, -h), (0.0, h - 0.0042 * s), (sp - t, -h), (sp + t, -h),
                 (t * 0.9, h), (-t * 0.9, h)]]
    raise ValueError(zone)


def add_glyph(mb, shape, a, d, z, zone, mat, h=0.0016, s=1.0):
    o, t, n, up = frame_at(shape, a, d, z)
    if zone == "Head":
        mb.annulus(o, t, n, up, 0.0050 * s, 0.0027 * s, 10, 0.0, h, mat)
        return
    for poly in glyph_polys(zone, s):
        mb.prism(poly, o, t, n, up, 0.0, h, mat)


# ------------------------------------------------------------------------------------------ materials
def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _si(p, names, v):
    for nm in names if isinstance(names, (list, tuple)) else [names]:
        if nm in p.inputs:
            p.inputs[nm].default_value = v
            return


def _mat(name, color, rough=0.5, metal=0.0, emission=None, strength=0.0, alpha=1.0, coat=0.0, spec=0.5,
         cull=True):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    p = _principled(mat)
    _si(p, "Base Color", (*color, 1))
    _si(p, "Roughness", rough)
    _si(p, "Metallic", metal)
    _si(p, ["Specular IOR Level", "Specular"], spec)
    if coat:
        _si(p, ["Coat Weight", "Clearcoat"], coat)
        _si(p, ["Coat Roughness"], 0.08)
    if emission is not None:
        _si(p, ["Emission Color", "Emission"], (*emission, 1))
        _si(p, "Emission Strength", strength)
    if alpha < 1.0:
        _si(p, "Alpha", alpha)
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:
            pass
    # every kit mesh is a closed, outward-facing shell: single-sided (glTF doubleSided = false)
    mat.use_backface_culling = cull
    mat.diffuse_color = (*(emission if emission else color), 1)
    return mat


def desaturate(c, k=BROKEN_DESAT):
    lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    return tuple(v + (lum - v) * k for v in c)


def _broken_mat(tier, crack_img):
    """Broken arc: dim, 50 % desaturated tier colour; the crack map drives the emission
    (glTF: emissiveTexture = crack_tile.png, emissiveFactor = desaturated tier colour)."""
    name = f"M_HALO_Glass_Broken_T{tier}"
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    c = desaturate(TIERS[tier])
    mat = _mat(name, tuple(0.10 * v for v in c), rough=0.35, emission=c, strength=BROKEN_STRENGTH, coat=0.4)
    if crack_img is not None:
        nt = mat.node_tree
        p = _principled(mat)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = crack_img
        tex.location = (-700, -200)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.location = (-400, -200)
        mix.inputs["Factor"].default_value = 1.0
        mix.inputs[7].default_value = (*c, 1)       # B (colour)
        nt.links.new(tex.outputs["Color"], mix.inputs[6])   # A (colour)
        nt.links.new(mix.outputs[2], p.inputs["Emission Color"])
    return mat


def make_materials(crack_path=None):
    M = {}
    M["graphite"] = _mat("M_HALO_Graphite", GRAPHITE, rough=0.55, metal=0.15, spec=0.35)
    M["gunmetal"] = _mat("M_HALO_Gunmetal", GUNMETAL, rough=0.35, metal=0.85)
    M["bone"] = _mat("M_HALO_Bone", BONE, rough=0.6, metal=0.0)
    # uncovered arc: opaque, very dark smoked glass with a glossy clearcoat (no alpha sorting in the engine)
    M["off"] = _mat("M_HALO_Glass_Off", SMOKE, rough=0.08, metal=0.0, coat=1.0, spec=0.8)
    M["edge"] = _mat("M_HALO_Edge", (0.04, 0.045, 0.05), rough=0.4, emission=EDGE, strength=EDGE_STRENGTH)
    for t, c in TIERS.items():
        base = tuple(0.12 * v for v in c)
        M[f"T{t}"] = _mat(f"M_HALO_Glass_T{t}", base, rough=0.25, emission=c, strength=2.4, coat=0.4, spec=0.5)
    img = None
    if crack_path:
        try:
            img = bpy.data.images.load(crack_path, check_existing=True)
            img.colorspace_settings.name = "sRGB"
        except Exception as e:  # the material still works (flat dim colour) without the map
            print("crack map not loaded:", e)
    for t in TIERS:
        M[f"B{t}"] = _broken_mat(t, img)
    return M


def set_strength(mat, s):
    _principled(mat).inputs["Emission Strength"].default_value = s
