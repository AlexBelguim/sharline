"""Showhome architecture kit: the two show homes, Sage House (west, team A) and Clay House (east, team B).

Run (headless Blender 5.2, re-runnable from scratch):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/maps/showhome/build_houses.py" -- [--no-render] [--views a,b,...] [--quick]

Everything is generated from the game's collision layout (layout/showhome_annotated.json via layout_lib), so the
walls, floors, stair, openings, parapets and terrace sit exactly on the brushes the game collides with:
  * every exposed face of every house brush is emitted exactly on the brush plane (exposure is computed by
    subtracting all neighbouring brushes), so openings, reveals, sills and lintels come out of the data;
  * decoration (cladding panels, bands, frames, sills, printed-concrete ridges, coping) stays <= 2 cm proud;
  * window and door openings stay open holes (no glass: bullets fly through every opening in the game);
  * the roof sits on the 45 deg gable planes; chimneys stand on the ridge above z 10, which is above the map's hard
    ceiling, so they can never block a line of sight between two players.
The west house is built from the W_* brushes; the east house is its exact mirror about x = 36 (the layout is
mirror-symmetric, which the script asserts), recoloured to the Clay colourway.

Frames: design / Blender = metres, x east, y north, z up (origin = SW map corner). The glTF is exported +Y up,
which is exactly the game's frame: bevy = (x, z, -y). Load kit/houses.glb at Transform::IDENTITY.

Writes
  kit/houses.glb, kit/houses.blend         the kit (objects SH_<SAGE|CLAY>_<part>)
  kit/textures/*.png                        textures derived from ../textures (plaster, oak floor)
  kit/renders/houses_*.png                  4 sides + aerial per house, cutaways, concept comparisons
"""
import json
import math
import os
import random
import subprocess
import sys
import time

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ROOT = r"F:/git/val etf"
SH = ROOT + "/assets/maps/showhome"
LAYOUT = SH + "/layout"
TEX = SH + "/textures"
V2 = TEX + "/v2"
KIT = SH + "/kit"
KTEX = KIT + "/textures"
RENDERS = KIT + "/renders"
CONCEPTS = ROOT + "/design/maps/tdm/concepts/_candidates"
sys.path.insert(0, LAYOUT)
sys.path.insert(0, ROOT + "/tools")
import layout_lib as LL  # noqa: E402
import blender_common as bc  # noqa: E402

V = Vector
EPS = 1e-4
WHITE = (1.0, 1.0, 1.0, 1.0)
T0 = time.time()


def log(*a):
    print(f"[houses {time.time() - T0:6.1f}s]", *a, flush=True)


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    views = None
    if "--views" in a:
        views = a[a.index("--views") + 1].split(",")
    return dict(render="--no-render" not in a, views=views, quick="--quick" in a)


def lin1(x):
    return ((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92


def srgb(r, g, b):
    """sRGB 0-255 -> linear tuple."""
    return (lin1(r / 255), lin1(g / 255), lin1(b / 255))


def mul(c, k):
    if isinstance(k, (int, float)):
        return tuple(x * k for x in c[:3])
    return tuple(x * y for x, y in zip(c[:3], k[:3]))


def rgba(c):
    c = tuple(c)
    return c if len(c) == 4 else c + (1.0,)


# ============================================================================================ palette
# Linear multipliers carried in the vertex colour attribute "Col" (exported as glTF COLOR_0; Bevy multiplies
# base_color by it). Textured materials use neutral / pre-coloured textures, so these are tints (README tints).
TEAMS = {
    "W": dict(
        name="SAGE",
        clad=(0.212, 0.300, 0.180),          # fibercement_panel tint -> muted sage (concept facade sRGB 130 138 113)
        chimney=(0.331, 0.419, 0.284),
        door=srgb(66, 73, 70),
        accent_gf=(0.96, 0.84, 0.66),        # plaster multipliers: warm interiors read through the windows
        accent_uf=(0.95, 0.72, 0.52),
        fabric=srgb(128, 140, 112),
        cushion=srgb(196, 132, 96),
        rug=srgb(196, 120, 82),               # terracotta rug in the sage house ...
        car=srgb(112, 150, 156),
        cabinet=srgb(122, 138, 118),
        art=[srgb(196, 132, 96), srgb(122, 140, 98), srgb(230, 214, 180)],
    ),
    "E": dict(
        name="CLAY",
        clad=(0.780, 0.205, 0.088),          # terracotta (concept facade median sRGB 199 124 94 in sun)
        chimney=(0.723, 0.270, 0.169),
        door=srgb(84, 52, 53),
        accent_gf=(0.86, 0.90, 0.74),
        accent_uf=(0.74, 0.84, 0.66),
        fabric=srgb(176, 118, 92),
        cushion=srgb(122, 140, 98),
        rug=srgb(112, 136, 110),              # ... sage rug in the clay house
        car=srgb(176, 64, 52),
        cabinet=srgb(176, 120, 100),
        art=[srgb(122, 140, 98), srgb(196, 132, 96), srgb(230, 214, 180)],
    ),
}
C_TRIM = (1.0, 1.0, 1.0)
C_PLASTER = (1.0, 1.0, 1.0)
C_FROST_LO = srgb(150, 174, 184)      # balustrade glass (opaque, stylised): cooler and darker at the shoe ...
C_FROST_HI = srgb(222, 234, 238)      # ... light sky sheen toward the handrail
C_DECK = (1.0, 1.0, 1.0)              # terrace decking (deck_grey.png is already in its final colour)
C_ROOF = (1.0, 1.0, 1.0)             # v2 roof is already matched to the concept palette
C_SOLAR = (0.72, 0.74, 0.80)          # calms the cell blue (the concept's panels read near-black navy)

# 3D-printed concrete: REAL bead geometry. Crests sit exactly on the brush plane, grooves BEAD_IN inside it, so the
# art never pokes out of the collision; custom shading normals make each 2-quad bead read as a rounded extrusion.
PRINT_P = 0.04                  # matches the v2 32-bead sheet exactly
PRINT_REP = 32 * PRINT_P        # printed_concrete_layers.png carries 32 beads per repeat -> texture grooves align
BEAD_IN = 0.009                 # 9 mm groove depth inside the brush face
BEAD_TILT = math.radians(55)    # shading-normal tilt at the grooves
C_JOINT = (0.38, 0.38, 0.38)     # shadow floor at -9 mm; true sun shadow comes from the panel edges
C_INT_WHITE = srgb(236, 232, 224)     # paint for risers, skirting, interior doors (Paint material is white)
C_DARK = srgb(46, 44, 48)
C_STEEL = srgb(150, 152, 156)
C_TYRE = srgb(30, 30, 32)
C_GLASS = srgb(40, 48, 58)
C_WOOD_LIGHT = (1.0, 1.0, 1.0)
C_WORKTOP = srgb(224, 218, 206)
C_HEATPUMP = srgb(226, 224, 218)

# ============================================================================================ layout data
L = LL.load()
PALETTE = json.load(open(TEX + "/_src/palette.json"))["materials"]
for _side, _family in (("W", "sage"), ("E", "clay")):
    # Only the neutral, seam-free face sheet is tinted. Coloured v2 sheets are never double-tinted.
    TEAMS[_side]["clad"] = tuple(c / 0.70 for c in PALETTE["fibercement_" + _family]["albedo_linear"])
TRIMS = json.load(open(TEX + "/trims.json"))
STRIPS = {s["name"]: (s["uv_blender"][1] + 0.002, s["uv_blender"][3] - 0.002) for s in TRIMS["strips"]}


def wall_union(wid):
    bs = L.brushes(tag=wid)
    mn = [min(b["min"][k] for b in bs) for k in range(3)]
    mx = [max(b["max"][k] for b in bs) for k in range(3)]
    return mn, mx


def check_mirror():
    def key(b, mir=False):
        mn, mx = b["min"], b["max"]
        if mir:
            mn, mx = [72 - mx[0], mn[1], mn[2]], [72 - mn[0], mx[1], mx[2]]
        r = b.get("ramp", {}).get("rise_toward", "")
        if mir and r in ("E", "W"):
            r = {"E": "W", "W": "E"}[r]
        return tuple(round(v, 3) for v in mn), tuple(round(v, 3) for v in mx), b["kind"], b["look"], r
    for a, e in (("SAGE_HOUSE", "CLAY_HOUSE"), ("SAGE_HOUSE_PROPS", "CLAY_HOUSE_PROPS")):
        w = {key(b, True) for b in L.brushes(structure=a)}
        ee = {key(b) for b in L.brushes(structure=e)}
        if w != ee:
            raise SystemExit(f"{a} and {e} are no longer mirror images about x = 36: rebuild the east house "
                             f"from its own brushes before exporting ({len(w ^ ee)} differing brushes)")


# key lines of the west house, all read from the brushes
H = L.heights()
_gw = wall_union("W_GF_W")
_ge = wall_union("W_GF_E")
_gs = wall_union("W_GF_S")
_gn = wall_union("W_GF_N")
_us = wall_union("W_UF_S")
_roof_s = L.brushes(tag="W_ROOF_S")[0]
_roof_n = L.brushes(tag="W_ROOF_N")[0]
G = dict(
    xw=_gw[0][0], xe=_ge[1][0], ys=_gs[0][1], yn=_gn[1][1],
    yms=_us[0][1],                       # outer face of the main block's south wall (above the terrace)
    zuf=H["UF"], zslab=H["UF_slab_bottom"], zceil=H["UF_ceiling"], zeave=H["eaves"], zridge=H["ridge"],
    ridge_y=_roof_s["max"][1], eave_ys=_roof_s["min"][1], eave_yn=_roof_n["max"][1],
    rx0=_roof_s["min"][0], rx1=_roof_s["max"][0],
    tw=0.9,                              # printed-concrete corner "tower" strip width
)
G["zpar"] = wall_union("W_TER_PE")[1][2]
G["zscr"] = wall_union("W_TER_SW")[1][2]
# terrace balustrade inside the 1.0 m parapet brush: printed upstand, then frosted (opaque) glass, steel handrail
GLASS_Z0 = G["zuf"] + 0.45
HOUSE_C = ((G["xw"] + G["xe"]) / 2, 24.0)
GARAGE_Y = wall_union("W_GF_P")[0][1]          # garage / main block split (partition face)
TERRACE_BOX = (lambda b: (b["min"][0], b["min"][1], b["max"][0], b["max"][1]))(L.brushes(tag="W_TERRACE")[0])
TERRACE_C = ((G["xw"] + G["xe"]) / 2, (G["ys"] + G["yms"]) / 2)


def wall_info():
    """Per wall id: normal axis of its sides, centre line, thickness, exterior side (+1/-1, 0 = interior)."""
    info = {}
    ids = sorted({b["tag"]["id"] for b in L.brushes(structure="SAGE_HOUSE") if b["look"] in ("Wall", "Trim", "Fence")})
    for wid in ids:
        mn, mx = wall_union(wid)
        ext = (mx[0] - mn[0], mx[1] - mn[1])
        ax = 0 if ext[0] < ext[1] else 1
        t = ext[ax]
        cl = (mn[ax] + mx[ax]) / 2
        kind = L.brushes(tag=wid)[0]["tag"].get("wall_kind")
        if kind == "int":
            es = 0
        elif kind in ("parapet", "screen"):
            es = 1 if cl > TERRACE_C[ax] else -1
        else:
            es = 1 if cl > HOUSE_C[ax] else -1
        info[wid] = dict(ax=ax, cl=cl, t=t, ext=es, kind=kind, zmin=mn[2], zmax=mx[2])
    return info


WALLS = wall_info()
OPENINGS = L.openings(structure="SAGE_HOUSE")
OPEN_BY_WALL = {}
for _o in OPENINGS:
    OPEN_BY_WALL.setdefault(_o["wall"], []).append(_o)

# clad zones (plane key -> rect in plane coords u, v) and the facade planes; see the module doc for the scheme:
# gable ends (street E, yard W) and the upper storey are fibre-cement cladding between printed-concrete corner
# towers; the garage / terrace volume, the ground floor on the N and W and the towers are 3D-printed concrete.
P_E = (0, 1, G["xe"])
P_W = (0, -1, G["xw"])
P_N = (1, 1, G["yn"])
P_SU = (1, -1, G["yms"])
CLAD = {
    P_E: (G["yms"] + G["tw"], G["yn"] - G["tw"], 0.0, G["zeave"]),
    P_W: (G["yms"] + G["tw"], G["yn"] - G["tw"], G["zslab"], G["zeave"]),
    P_N: (G["xw"] + G["tw"], G["xe"] - G["tw"], G["zslab"], G["zeave"]),
    P_SU: (G["xw"] + G["tw"], G["xe"] - G["tw"], G["zuf"], G["zeave"]),
}
FACADE_WALLS = {P_E: ("W_GF_E", "W_UF_E"), P_W: ("W_GF_W", "W_UF_W"), P_N: ("W_GF_N", "W_UF_N"),
                P_SU: ("W_UF_S",)}


def same_plane(a, b):
    return a[0] == b[0] and a[1] == b[1] and abs(a[2] - b[2]) < 0.004


# ============================================================================================ mesh accumulator
def newell(pts):
    n = V((0.0, 0.0, 0.0))
    k = len(pts)
    for i in range(k):
        a, b = pts[i], pts[(i + 1) % k]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


class Acc:
    """Collects polygons (unwelded: every face owns its corners) with material, per-corner UV, colour, normal."""

    def __init__(self):
        self.P = []

    def poly(self, pts, mat, uv, col=WHITE, nrm=None, want=None):
        pts = [V(p) for p in pts]
        n = newell(pts)
        if n.length < 1e-9:
            return
        if want is not None and n.dot(V(want)) < 0:
            pts.reverse()
            n = -n
            if nrm:
                nrm = list(reversed(nrm))
            if isinstance(uv, list):
                uv = list(reversed(uv))
            if isinstance(col, list):
                col = list(reversed(col))
        n.normalize()
        uvs = uv(pts, n) if callable(uv) else list(uv)
        if isinstance(col, list):
            cols = [rgba(c) for c in col]
        elif callable(col):
            cols = [rgba(col(p)) for p in pts]
        else:
            cols = [rgba(col)] * len(pts)
        nrm = [V(x).normalized() for x in nrm] if nrm else None
        if len(pts) > 4:
            # n-gons -> triangles (MikkTSpace tangents for the glTF need tris / quads); handles concave outlines
            for tri in tessellate_polygon([pts]):
                # tessellate_polygon may return clockwise triangles: keep the polygon's winding
                a, b, c = tri
                if newell([pts[a], pts[b], pts[c]]).dot(n) < 0:
                    a, c = c, a
                ix = (a, b, c)
                self.P.append(([pts[i] for i in ix], mat, [uvs[i] for i in ix], [cols[i] for i in ix],
                               [nrm[i] for i in ix] if nrm else None))
            return
        self.P.append((pts, mat, uvs, cols, nrm))

    def extend(self, other):
        self.P.extend(other.P)

    def mirrored(self, cx=36.0):
        out = Acc()
        for pts, mat, uvs, cols, nrm in self.P:
            out.P.append(([V((2 * cx - p.x, p.y, p.z)) for p in reversed(pts)], mat, list(reversed(uvs)),
                          list(reversed(cols)),
                          None if nrm is None else [V((-q.x, q.y, q.z)) for q in reversed(nrm)]))
        return out

    def tris(self):
        return sum(len(p[0]) - 2 for p in self.P)


# ------------------------------------------------------------------------------------------- UV functions
def uv_box(rep, ou=0.0, ov=0.0):
    """World box projection, 1 UV = rep metres; on walls V follows world up."""
    def f(pts, n):
        ax = max(range(3), key=lambda i: abs(n[i]))
        out = []
        for p in pts:
            if ax == 2:
                u, v = p.x, p.y
            elif ax == 0:
                u, v = (p.y if n.x > 0 else -p.y), p.z
            else:
                u, v = (-p.x if n.y > 0 else p.x), p.z
            out.append((u / rep + ou, v / rep + ov))
        return out
    return f


def uv_trim(strip, along, across=None, lo=0.0, span=1.0, vsub=(0.0, 1.0), ulen=4.0):
    v0, v1 = STRIPS[strip]

    def f(pts, n):
        out = []
        for p in pts:
            t = 0.0 if across is None else (p[across] - lo) / span
            t = vsub[0] + max(0.0, min(1.0, t)) * (vsub[1] - vsub[0])
            out.append((p[along] / ulen, v0 + t * (v1 - v0)))
        return out
    return f


def trim_box_uv(strip, along):
    """For box(): faces map U along `along` (world axis) and V across the face's other axis."""
    def make(mn, mx, ax):
        if ax == along:
            o = [i for i in range(3) if i != ax]
            return uv_trim(strip, o[0], o[1], mn[o[1]], max(mx[o[1]] - mn[o[1]], 1e-6), (0.0, 0.25))
        across = [i for i in range(3) if i not in (ax, along)][0]
        return uv_trim(strip, along, across, mn[across], max(mx[across] - mn[across], 1e-6))
    make.boxaware = True
    return make


def uv_unit(u_ax, v_ax, mn, mx):
    """0..1 over a face (e.g. one solar module)."""
    def f(pts, n):
        return [((p[u_ax] - mn[u_ax]) / max(mx[u_ax] - mn[u_ax], 1e-6),
                 (p[v_ax] - mn[v_ax]) / max(mx[v_ax] - mn[v_ax], 1e-6)) for p in pts]
    return f


# ------------------------------------------------------------------------------------------- primitives
def ppt(axis, c, u, v):
    if axis == 0:
        return V((c, u, v))
    if axis == 1:
        return V((u, c, v))
    return V((u, v, c))


def box(acc, mn, mx, mat, col=WHITE, uv=None, skip=()):
    mn, mx = V(mn), V(mx)
    if uv is None:
        uv = uv_box(1.0)
    for ax in range(3):
        a1, a2 = [i for i in range(3) if i != ax]
        for s in (-1, 1):
            if (ax, s) in skip:
                continue
            c = mx[ax] if s > 0 else mn[ax]
            pts = []
            for p1, p2 in ((mn[a1], mn[a2]), (mx[a1], mn[a2]), (mx[a1], mx[a2]), (mn[a1], mx[a2])):
                p = [0.0, 0.0, 0.0]
                p[ax], p[a1], p[a2] = c, p1, p2
                pts.append(p)
            want = [0, 0, 0]
            want[ax] = s
            f = uv(mn, mx, ax) if getattr(uv, "boxaware", False) else uv
            acc.poly(pts, mat, f, col, want=want)


def prism(acc, plane, poly, d0, d1, mat, col, uv, sides=True, back=False):
    """Extrude a convex polygon given in plane coords (u, v) from offset d0 to d1 along the plane normal."""
    axis, sign, c = plane
    nrm = [0, 0, 0]
    nrm[axis] = sign
    acc.poly([ppt(axis, c + sign * d1, u, v) for u, v in poly], mat, uv, col, want=nrm)
    if back:
        acc.poly([ppt(axis, c + sign * d0, u, v) for u, v in poly], mat, uv, col, want=[-x for x in nrm])
    if sides and abs(d1 - d0) > 1e-5:
        cu = sum(p[0] for p in poly) / len(poly)
        cv = sum(p[1] for p in poly) / len(poly)
        for i in range(len(poly)):
            (u1, v1), (u2, v2) = poly[i], poly[(i + 1) % len(poly)]
            if abs(u1 - u2) < 1e-7 and abs(v1 - v2) < 1e-7:
                continue
            q = [ppt(axis, c + sign * d0, u1, v1), ppt(axis, c + sign * d0, u2, v2),
                 ppt(axis, c + sign * d1, u2, v2), ppt(axis, c + sign * d1, u1, v1)]
            want = ppt(axis, 0.0, (u1 + u2) / 2 - cu, (v1 + v2) / 2 - cv)
            acc.poly(q, mat, uv, col, want=want)


def rect_poly(u0, v0, u1, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def inset_convex(poly, distance):
    """Parallel 2D inset, keeping the exact panel polygon and a 1.8 mm edge chamfer."""
    lines = []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        le = math.hypot(dx, dy)
        if le < 1e-8:
            return poly
        nx, ny = -dy / le, dx / le
        lines.append((a[0] + nx * distance, a[1] + ny * distance, dx, dy))
    out = []
    for i, b in enumerate(lines):
        a = lines[i - 1]
        det = a[2] * b[3] - a[3] * b[2]
        if abs(det) < 1e-9:
            out.append((b[0], b[1])); continue
        t = ((b[0] - a[0]) * b[3] - (b[1] - a[1]) * b[2]) / det
        out.append((a[0] + a[2] * t, a[1] + a[3] * t))
    return out


def bevel_panel(acc, plane, poly, mat, col, uv):
    """Panel crests remain on the collision plane; the dark joint floor is 9 mm behind them."""
    axis, sign, c = plane
    want = [0, 0, 0]; want[axis] = sign
    inner = inset_convex(poly, 0.0018)
    acc.poly([ppt(axis, c, u, v) for u, v in inner], mat, uv, col, want=want)
    centre = V((sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)))
    for i in range(len(poly)):
        j = (i + 1) % len(poly)
        a, b = poly[i], poly[j]
        ia, ib = inner[i], inner[j]
        q = [ppt(axis, c - sign * 0.002, *a), ppt(axis, c - sign * 0.002, *b),
             ppt(axis, c, *ib), ppt(axis, c, *ia)]
        acc.poly(q, mat, uv, col, want=want)
        q = [ppt(axis, c - sign * 0.009, *a), ppt(axis, c - sign * 0.009, *b),
             ppt(axis, c - sign * 0.002, *b), ppt(axis, c - sign * 0.002, *a)]
        mid = (V(a) + V(b)) / 2 - centre
        acc.poly(q, mat, uv, mul(col, 0.88), want=ppt(axis, 0, mid.x, mid.y))


def clip_poly(poly, a, b, c):
    """Keep a*u + b*v <= c (Sutherland-Hodgman, one half-plane)."""
    out = []
    k = len(poly)
    for i in range(k):
        p, q = poly[i], poly[(i + 1) % k]
        fp, fq = a * p[0] + b * p[1] - c, a * q[0] + b * q[1] - c
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def sweep(acc, path, profile, mat, col=WHITE, strip=None, rep=None, caps=True, ulen=4.0):
    """Sweep a closed 2D profile [(lat, up)] along a horizontal polyline path (mitred joints).
    lat is to the left of travel (Z x tangent). UV: U = path length / ulen, V = profile perimeter on the strip."""
    path = [V(p) for p in path]
    Z = V((0, 0, 1))
    n = len(path)
    frames = []
    for i in range(n):
        d_in = (path[i] - path[i - 1]).normalized() if i > 0 else None
        d_out = (path[i + 1] - path[i]).normalized() if i < n - 1 else None
        l_in = Z.cross(d_in).normalized() if d_in else None
        l_out = Z.cross(d_out).normalized() if d_out else None
        if l_in and l_out:
            lm = (l_in + l_out).normalized()
            scale = 1.0 / max(lm.dot(l_in), 0.2)
            frames.append((lm * scale))
        else:
            frames.append(l_in or l_out)
    rings = [[path[i] + frames[i] * a + Z * b for a, b in profile] for i in range(n)]
    plen = [0.0]
    for i in range(1, n):
        plen.append(plen[-1] + (path[i] - path[i - 1]).length)
    per = [0.0]
    m = len(profile)
    for j in range(1, m + 1):
        a, b = profile[j - 1], profile[j % m]
        per.append(per[-1] + math.hypot(a[0] - b[0], a[1] - b[1]))
    ca = sum(p[0] for p in profile) / m
    cb = sum(p[1] for p in profile) / m
    for i in range(n - 1):
        for j in range(m):
            j2 = (j + 1) % m
            q = [rings[i][j], rings[i + 1][j], rings[i + 1][j2], rings[i][j2]]
            mid_a = (profile[j][0] + profile[j2][0]) / 2 - ca
            mid_b = (profile[j][1] + profile[j2][1]) / 2 - cb
            seg_l = Z.cross((path[i + 1] - path[i]).normalized()).normalized()
            want = seg_l * mid_a + Z * mid_b
            if strip:
                v0, v1 = STRIPS[strip]
                vv = [v0 + (per[j] / per[-1]) * (v1 - v0), v0 + (per[j + 1] / per[-1]) * (v1 - v0)]
                uv = [(plen[i] / ulen, vv[0]), (plen[i + 1] / ulen, vv[0]), (plen[i + 1] / ulen, vv[1]),
                      (plen[i] / ulen, vv[1])]
            else:
                uv = uv_box(rep or 1.0)
            acc.poly(q, mat, uv, col, want=want)
    if caps:
        d0 = (path[1] - path[0]).normalized()
        d1 = (path[-1] - path[-2]).normalized()
        f = uv_trim(strip, 0, None) if strip else uv_box(rep or 1.0)
        acc.poly(rings[0], mat, f, col, want=-d0)
        acc.poly(rings[-1], mat, f, col, want=d1)


# ------------------------------------------------------------------------------------------- printed beads
def bead_g(z):
    """0 at a bead crest (z = k P), 1 at a groove (z = (k + 1/2) P)."""
    f = (z / PRINT_P) % 1.0
    return 1.0 - abs(1.0 - 2.0 * f)


def bead_levels(z0, z1):
    h = PRINT_P / 2
    lv = [z0]
    k = math.floor(z0 / h + 1e-6) + 1
    while k * h < z1 - 1e-4:
        if k * h > z0 + 1e-4:
            lv.append(k * h)
        k += 1
    lv.append(z1)
    return lv


def print_col(z, g, base=1.0):
    """Vertex colour of the printed concrete: ground AO + painted cavity in the grooves (survives mip-mapping, so
    the layer lines still read at 40 m where the texture has blurred out)."""
    ao = 0.78 + 0.22 * min(1.0, max(z, 0.0) / 0.8)
    k = base * ao * (1.0 - 0.12 * g * g)
    return (k, k, k)


def ccw_t(n):
    """Counter-clockwise (seen from above) tangent of a horizontal outward normal: printed U runs this way on every
    face, so it is continuous around convex corners."""
    return (-n[1], n[0])


def plane_key(axis, sign, c):
    return (axis, int(sign), round(c, 3))


def bead_ribbon(acc, cols, z0, z1, mat="printed", u_start=0.0, base=1.0, us=None):
    """Printed-concrete beads on a vertical ribbon between z0 and z1.
    cols: [((x, y), geometric outward normal (x, y), shading normal (x, y))] along the ribbon. Two quads per bead
    per column; grooves are pushed BEAD_IN along the geometric normal, shading normals tilt up/down by BEAD_TILT."""
    Z = V((0.0, 0.0, 1.0))
    pts = [V((p[0], p[1], 0.0)) for p, _, _ in cols]
    ng = [V((n[0], n[1], 0.0)).normalized() for _, n, _ in cols]
    ns = [V((n[0], n[1], 0.0)).normalized() for _, _, n in cols]
    if us is None:
        us = [u_start]
        for i in range(1, len(pts)):
            us.append(us[-1] + (pts[i] - pts[i - 1]).length)
    lv = bead_levels(z0, z1)
    for a in range(len(lv) - 1):
        za, zb = lv[a], lv[a + 1]
        up = (((za + zb) / 2 / PRINT_P) % 1.0) < 0.5    # crest below, groove above: this half faces up
        sgn = 1.0 if up else -1.0
        ga, gb = bead_g(za), bead_g(zb)
        for i in range(len(pts) - 1):
            q, nr, uv, cl = [], [], [], []
            for (j, z, g) in ((i, za, ga), (i + 1, za, ga), (i + 1, zb, gb), (i, zb, gb)):
                q.append(pts[j] + ng[j] * (-BEAD_IN * g) + Z * z)
                t = sgn * BEAD_TILT * g
                nr.append(ns[j] * math.cos(t) + Z * math.sin(t))
                uv.append((us[j] / PRINT_REP, z / PRINT_REP))
                cl.append(print_col(z, g, base))
            acc.poly(q, mat, uv, cl, nrm=nr, want=ng[i] + ng[i + 1])


# ------------------------------------------------------------------------------------------- rectangles
def rect_grid(R, covers, cut_u=(), cut_v=()):
    """Grid of R cut by cover edges and extra cut lines; returns (us, vs, keep[i][j])."""
    u0, v0, u1, v1 = R

    def lines(lo, hi, vals):
        s = sorted(set([lo, hi] + [x for x in vals if lo + EPS < x < hi - EPS]))
        out = [s[0]]
        for x in s[1:]:
            if x - out[-1] > EPS:
                out.append(x)
        out[-1] = hi
        return out
    us = lines(u0, u1, [c for r in covers for c in (r[0], r[2])] + list(cut_u))
    vs = lines(v0, v1, [c for r in covers for c in (r[1], r[3])] + list(cut_v))
    keep = []
    for i in range(len(us) - 1):
        col = []
        cu = (us[i] + us[i + 1]) / 2
        for j in range(len(vs) - 1):
            cv = (vs[j] + vs[j + 1]) / 2
            col.append(not any(r[0] < cu < r[2] and r[1] < cv < r[3] for r in covers))
        keep.append(col)
    return us, vs, keep


def merge_cells(us, vs, key):
    """key[i][j] -> hashable or None. Greedy merge into rectangles; returns [(u0, v0, u1, v1, key)]."""
    ni, nj = len(us) - 1, len(vs) - 1
    strips = []
    for j in range(nj):
        i = 0
        while i < ni:
            k = key[i][j]
            if k is None:
                i += 1
                continue
            i2 = i
            while i2 + 1 < ni and key[i2 + 1][j] == k:
                i2 += 1
            strips.append([i, i2, j, j, k])
            i = i2 + 1
    # vertical merge of identical strips in consecutive rows
    strips.sort(key=lambda s: (s[0], s[1], str(s[4]), s[2]))
    out = []
    for s in strips:
        if out and out[-1][0] == s[0] and out[-1][1] == s[1] and out[-1][4] == s[4] and out[-1][3] + 1 == s[2]:
            out[-1][3] = s[3]
        else:
            out.append(s)
    return [(us[a], vs[c], us[b + 1], vs[d + 1], k) for a, b, c, d, k in out]


def rect_subtract(R, holes):
    us, vs, keep = rect_grid(R, holes)
    key = [[True if keep[i][j] else None for j in range(len(vs) - 1)] for i in range(len(us) - 1)]
    return [(a, b, c, d) for a, b, c, d, _ in merge_cells(us, vs, key)]


# ============================================================================================ textures + materials
def derive_textures(force=False):
    """Plaster and oak floor textures derived from the library (numpy in Blender; re-runnable)."""
    import numpy as np
    os.makedirs(KTEX, exist_ok=True)
    jobs = {
        # name: (source, target linear mean, contrast keep)
        "plaster_beige.png": ("concrete_smooth.png", srgb(230, 218, 200), 0.35),
        "oak_boards.png": ("wood_boards_stained.png", srgb(184, 146, 108), 0.75),
        "deck_grey.png": ("wood_boards_stained.png", srgb(126, 116, 108), 0.85),
    }
    for name, (src, target, k) in jobs.items():
        out = os.path.join(KTEX, name)
        source = os.path.join(V2 if os.path.exists(os.path.join(V2, src)) else TEX, src)
        if os.path.exists(out) and not force and os.path.getmtime(out) > os.path.getmtime(source):
            continue
        im = bpy.data.images.load(source, check_existing=False)
        w, h = im.size
        px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
        rgb = px[:, :, :3]
        linv = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
        lum = linv.mean(axis=2, keepdims=True)
        mean_l = lum.mean()
        # keep the painterly value variation (scaled), drop the source hue, then colour to the target mean
        val = (mean_l + (lum - mean_l) * k) / mean_l
        out_lin = np.clip(val * np.array(target, dtype=np.float32), 0, 1)
        out_s = np.where(out_lin > 0.0031308, 1.055 * out_lin ** (1 / 2.4) - 0.055, out_lin * 12.92)
        new = bpy.data.images.new("_d_" + name, w, h, alpha=False)
        buf = np.concatenate([out_s, np.ones((h, w, 1), np.float32)], axis=2)
        new.pixels.foreach_set(buf.ravel())
        new.filepath_raw = out
        new.file_format = "PNG"
        new.save()
        bpy.data.images.remove(new)
        bpy.data.images.remove(im)
        log("derived texture", out)


def glass_streaks(force=False):
    """Stylised glass: a light, slightly cool base with two soft diagonal sheen streaks. Tileable (the streaks run
    along x + y). The balustrade is OPAQUE in the game (the parapet brush blocks bullets and sight), so the glass is
    read through these streaks and a vertical tint gradient, never through transparency."""
    import numpy as np
    out = os.path.join(KTEX, "glass_streaks.png")
    if os.path.exists(out) and not force:
        return
    n = 512
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32) / n
    d = (xx + yy) % 1.0

    def band(c, w):
        t = np.minimum(np.abs(d - c), 1.0 - np.abs(d - c)) / w
        return np.clip(1.0 - t, 0.0, 1.0) ** 1.6
    rng = np.random.default_rng(5)
    noise = rng.normal(0.0, 1.0, (n // 16, n // 16)).astype(np.float32)
    noise = np.kron(noise, np.ones((16, 16), np.float32))
    k = np.ones(9, np.float32) / 9
    for ax in (0, 1):
        noise = np.apply_along_axis(lambda r: np.convolve(np.concatenate([r[-8:], r, r[:8]]), k, "same")[8:-8], ax,
                                    noise)
    val = 0.80 + 0.17 * band(0.30, 0.10) + 0.12 * band(0.47, 0.035) + 0.06 * band(0.82, 0.05) + 0.012 * noise
    val = np.clip(val, 0, 1)
    rgb = np.stack([val * 0.97, val, val], axis=2)
    s_ = np.where(rgb > 0.0031308, 1.055 * rgb ** (1 / 2.4) - 0.055, rgb * 12.92)
    im = bpy.data.images.new("_glass_streaks", n, n, alpha=False)
    im.pixels.foreach_set(np.concatenate([s_[::-1], np.ones((n, n, 1), np.float32)], axis=2).ravel())
    im.filepath_raw = out
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    log("derived texture", out)


def _img(path, colour=True):
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return im


def make_mat(name, tex=None, rough=0.7, metal=0.0, normal=None, nstr=1.0, orm=None, emission=None, estr=0.0,
             spec=0.5):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    m.use_backface_culling = True
    nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type not in ("BSDF_PRINCIPLED", "OUTPUT_MATERIAL"):
            nt.nodes.remove(nd)
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    if tex:
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = _img(tex)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        nt.links.new(ti.outputs["Color"], mix.inputs[6])
        nt.links.new(vc.outputs["Color"], mix.inputs[7])
        nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    else:
        nt.links.new(vc.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    try:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    except KeyError:
        pass
    if normal:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = _img(normal, False)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = nstr
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if orm:
        to = nt.nodes.new("ShaderNodeTexImage")
        to.image = _img(orm, False)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(to.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs[1], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs[2], bsdf.inputs["Metallic"])
        # The glTF exporter recognises this conventional output and exports ORM.R as occlusion.
        ng = bpy.data.node_groups.get("glTF Material Output")
        if ng is None:
            from io_scene_gltf2.blender.com.material_helpers import create_settings_group
            ng = create_settings_group("glTF Material Output")
        go = nt.nodes.new("ShaderNodeGroup"); go.node_tree = ng
        nt.links.new(sep.outputs[0], go.inputs["Occlusion"])
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = estr
    m.diffuse_color = (0.8, 0.8, 0.8, 1)
    if tex:
        m["texture_source"] = os.path.relpath(tex, ROOT).replace("\\", "/")
        if os.path.normpath(tex).startswith(os.path.normpath(V2)):
            m["height_map"] = "assets/maps/showhome/textures/v2/" + os.path.splitext(os.path.basename(tex))[0] + "_height.png"
            m["height_is_linear"] = True
    return m


def materials():
    t = lambda n: os.path.join(V2 if os.path.exists(os.path.join(V2, n)) else TEX, n)  # noqa: E731
    k = lambda n: os.path.join(KTEX, n)  # noqa: E731
    def painted(key, name, file, rough=0.7, metal=0.0, nstr=0.65):
        base = file.removesuffix(".png")
        norm, orm = t(base + "_normal.png"), t(base + "_orm.png")
        m = make_mat(name, t(file), rough, metal,
                     normal=norm if os.path.exists(norm) else None, nstr=nstr,
                     orm=orm if os.path.exists(orm) else None)
        m["texture_family"] = base
        m["height_map"] = "assets/maps/showhome/textures/v2/" + base + "_height.png"
        m["height_is_linear"] = True
        return m
    return {
        "printed": painted("printed", "M_SH_PrintedConcrete", "printed_concrete_layers.png", 0.8, nstr=0.25),
        "frost": make_mat("M_SH_GlassFrost", k("glass_streaks.png"), 0.1, spec=0.8),
        "deck": make_mat("M_SH_Decking", k("deck_grey.png"), 0.75),
        "clad": painted("clad", "M_SH_FibreCementPaintedFace", "fibercement_panel.png", 0.65, nstr=0.25),
        "trim": make_mat("M_SH_TrimSheet", t("trim_sheet_house.png"), 0.6, normal=t("trim_sheet_house_normal.png"),
                         orm=t("trim_sheet_house_orm.png")),
        "roof": painted("roof", "M_SH_RoofShingle", "roof_shingle_dark.png", 0.7, nstr=0.4),
        "roof_edge": painted("roof_edge", "M_SH_RidgeVerge", "roof_ridge_verge.png" if os.path.exists(t("roof_ridge_verge.png")) else "roof_shingle_dark.png", 0.68, nstr=0.3),
        "solar": make_mat("M_SH_SolarPanel", t("solar_panel.png"), 0.38, spec=0.45),
        "plaster": make_mat("M_SH_Plaster", k("plaster_beige.png"), 0.85),
        "concrete": painted("concrete", "M_SH_Concrete", "concrete_smooth.png", 0.8),
        "oak": make_mat("M_SH_OakBoards", k("oak_boards.png"), 0.6),
        "paving": painted("paving", "M_SH_Paving", "paving_slabs.png", 0.8),
        "timber": painted("timber", "M_SH_TimberBoards", "wood_boards_stained.png", 0.8),
        "paint": make_mat("M_SH_Paint", None, 0.5),
        "fabric": make_mat("M_SH_Fabric", None, 0.92, spec=0.3),
        "metal": make_mat("M_SH_Metal", None, 0.35, metal=0.8),
        "glass": make_mat("M_SH_GlassDark", None, 0.08, spec=0.8),
        "lamp": make_mat("M_SH_LampWarm", None, 0.4, emission=srgb(255, 214, 160), estr=4.0),
    }


# ============================================================================================ the west house
class House:
    def __init__(self, team):
        self.T = team
        self.acc = {k: Acc() for k in ("shell", "clad", "trim", "roof", "solar", "interior", "props", "doors")}
        self.extra_cover = {}     # plane key -> rects removed from the generic pass (corner pieces fill them)
        self.skirting = []        # (plane, u0, u1, v)
        self.u_off = {}           # printed U offset per plane key, chosen so U is continuous around rounded corners
        self.rng = random.Random(7)

    # ----------------------------------------------------------------------------------- generic exposed faces
    def generic_faces(self):
        house = [b for b in L.brushes(structure="SAGE_HOUSE")
                 if b["kind"] != "PlayerClip" and b["tag"].get("part") not in ("gable", "stair_ramp")]
        floor = [b for b in L.all if b["tag"].get("part") == "building_floor"
                 and b["min"][0] >= G["xw"] - 0.2 and b["max"][0] <= G["xe"] + 0.2
                 and b["min"][1] >= G["ys"] - 0.2 and b["max"][1] <= G["yn"] + 0.2]
        lo = (G["xw"] - 1.0, G["ys"] - 1.0)
        hi = (G["xe"] + 1.0, G["yn"] + 1.0)
        cov = []
        for b in L.visible():
            if b["max"][0] < lo[0] or b["min"][0] > hi[0] or b["max"][1] < lo[1] or b["min"][1] > hi[1]:
                continue
            p = b["tag"].get("part")
            if b["tag"]["structure"] == "SAGE_HOUSE_PROPS" or p == "stair_ramp":
                continue
            if p == "gable":  # wedge: only its base covers what is under it
                cov.append(dict(min=b["min"], max=[b["max"][0], b["max"][1], b["min"][2] + 0.01], i=b["i"]))
                continue
            cov.append(b)
        emitted = {}
        for b in house + floor:
            only_top = b in floor
            for axis in range(3):
                ua, va = [(1, 2), (0, 2), (0, 1)][axis]
                for sign in (-1, 1):
                    if only_top and not (axis == 2 and sign > 0):
                        continue
                    c = b["max"][axis] if sign > 0 else b["min"][axis]
                    R = (b["min"][ua], b["min"][va], b["max"][ua], b["max"][va])
                    covers = []
                    for o in cov:
                        if o is b or o.get("i") == b["i"]:
                            continue
                        if sign > 0:
                            ok = o["min"][axis] <= c + EPS and o["max"][axis] > c + 1e-3
                        else:
                            ok = o["max"][axis] >= c - EPS and o["min"][axis] < c - 1e-3
                        if not ok:
                            continue
                        r = (max(R[0], o["min"][ua]), max(R[1], o["min"][va]), min(R[2], o["max"][ua]),
                             min(R[3], o["max"][va]))
                        if r[2] - r[0] > EPS and r[3] - r[1] > EPS:
                            covers.append(r)
                    plane = (axis, sign, c)
                    for pk, rects in self.extra_cover.items():
                        if same_plane(pk, plane):
                            covers += rects
                    pkey = (axis, sign, round(c, 3))
                    for r in emitted.get(pkey, []):
                        rr = (max(R[0], r[0]), max(R[1], r[1]), min(R[2], r[2]), min(R[3], r[3]))
                        if rr[2] - rr[0] > EPS and rr[3] - rr[1] > EPS:
                            covers.append(rr)
                    emitted.setdefault(pkey, []).append(R)
                    cu, cv = self.zone_cuts(b, plane)
                    us, vs, keep = rect_grid(R, covers, cu, cv)
                    key = [[None] * (len(vs) - 1) for _ in range(len(us) - 1)]
                    for i in range(len(us) - 1):
                        for j in range(len(vs) - 1):
                            if keep[i][j]:
                                key[i][j] = self.classify(b, plane, (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2)
                    for u0, v0, u1, v1, k in merge_cells(us, vs, key):
                        self.emit_face(plane, (u0, v0, u1, v1), k)

    def zone_cuts(self, b, plane):
        axis, sign, c = plane
        cu, cv = [], []
        if axis != 2:
            cv.append(0.7)    # ground AO gradient
        for pk, (u0, u1, v0, v1) in CLAD.items():
            if same_plane(pk, plane):
                cu += [u0, u1]
                cv += [v0, v1]
        if b["tag"]["id"] == "W_GF_S" and b["tag"].get("part") == "lintel":   # roller curtain rows
            cv += [1.1 + 0.25 * k for k in range(1, 7)] + [2.75]
        if WALLS.get(b["tag"]["id"], {}).get("kind") == "parapet":
            cv.append(GLASS_Z0)
        if axis == 2 and b["tag"].get("part") == "building_floor":
            cv.append(GARAGE_Y)
        return cu, cv

    def classify(self, b, plane, u, v):
        """-> key tuple (acc, mat, uvspec, colspec, offset) or None for faces the art leaves out."""
        axis, sign, c = plane
        tag = b["tag"]
        wid, part = tag["id"], tag.get("part")
        p = ppt(axis, c, u, v)
        if part == "building_floor":
            if p.y < GARAGE_Y:
                return ("interior", "concrete", ("box", 2.0), ("flat", (0.92, 0.92, 0.92)), 0.004)
            return ("interior", "oak", ("box", 2.0), ("flat", (1, 1, 1)), 0.004)
        if wid == "W_UF_SLAB":
            if axis == 2:
                return ("interior", "oak", ("box", 2.0), ("flat", (1, 1, 1)), 0.0) if sign > 0 else \
                    ("interior", "plaster", ("box", 2.0), ("flat", (1, 1, 1)), 0.0)
            return ("interior", "oak", ("trim_any",), ("flat", (0.85, 0.85, 0.85)), 0.0)
        if wid == "W_TERRACE":
            if axis == 2 and sign > 0:
                return ("shell", "deck", ("deck",), ("flat", C_DECK), 0.0)
            if axis == 2:
                return ("interior", "concrete", ("box", 2.0), ("flat", (0.95, 0.95, 0.95)), 0.0)
            return None
        if wid == "W_UF_CEILING":
            if axis == 2 and sign < 0:
                return ("interior", "plaster", ("box", 2.0), ("flat", (1, 1, 1)), 0.0)
            return None
        w = WALLS.get(wid)
        if w is None:
            return None
        if axis == w["ax"]:                                   # wall side faces
            if wid == "W_GF_S" and part == "lintel" and v < 2.75:
                row = int((v - 1.1) / 0.25)
                return ("shell", "trim", ("roller", 1.1 + row * 0.25), ("flat", (1, 1, 1)), 0.0)
            if w["kind"] in ("parapet", "screen") or (w["ext"] != 0 and sign == w["ext"]):
                return self.ext_zone(wid, part, plane, u, v, p)
            return self.int_zone(wid, plane, u, v, p)
        if axis == 2:                                         # tops and bottoms
            if sign > 0:
                if part == "sill":
                    return ("shell", "trim", ("reveal", wid, "sill_cream"), ("flat", C_TRIM), 0.0)
                if w["kind"] in ("parapet", "screen"):
                    return None                               # coping / cap covers it
                tb = TERRACE_BOX
                if abs(c - G["zuf"]) < 0.01 and tb[0] < p.x < tb[2] and tb[1] < p.y < tb[3]:
                    return None                               # under the terrace paving (coplanar)
                if abs(c - G["zeave"]) < 0.01:
                    return ("shell", "trim", ("trimflat", "flashing_dark"), ("flat", (1, 1, 1)), 0.0)
                return ("shell", "trim", ("trimflat", "sill_cream"), ("flat", C_TRIM), 0.0)
            if part != "lintel":
                return ("interior", "plaster", ("box", 2.0), ("flat", (1, 1, 1)), 0.0)
            if part == "lintel":
                op = self.opening_of(wid, tag.get("opening"))
                if op and op["kind"] == "roller":
                    return ("shell", "trim", ("trimflat", "plain_dark"), ("flat", (1, 1, 1)), 0.0)
                strip = "door_frame_cream" if op and op["kind"].startswith("door") else "window_surround_cream"
                return ("shell" if w["ext"] else "interior", "trim", ("reveal", wid, strip), ("flat", C_TRIM), 0.0)
            return None
        # end faces (normal along the wall line): opening reveals or free wall ends
        op = self.opening_at(wid, c)
        if op is not None:
            strip = "door_frame_cream" if op["kind"].startswith("door") or op["kind"] == "roller" else \
                "window_surround_cream"
            return ("shell" if w["ext"] else "interior", "trim", ("reveal", wid, strip), ("flat", C_TRIM), 0.0)
        if w["kind"] == "screen":
            return ("shell", "timber", ("box", 2.0), ("flat", (1, 1, 1)), 0.0)
        return ("shell", "printed", ("box", 1.28), ("ao",), 0.0)

    def opening_of(self, wid, oid):
        for o in OPEN_BY_WALL.get(wid, []):
            if o["id"] == oid:
                return o
        return None

    def opening_at(self, wid, c):
        for o in OPEN_BY_WALL.get(wid, []):
            if abs(o["span"][0] - c) < 0.01 or abs(o["span"][1] - c) < 0.01:
                return o
        return None

    def ext_zone(self, wid, part, plane, u, v, p):
        w = WALLS[wid]
        if w["kind"] == "screen":
            return ("shell", "timber", ("box", 2.0), ("flat", (1, 1, 1)), 0.0)
        if w["kind"] == "parapet" and v > GLASS_Z0:
            return ("shell", "frost", ("box", 1.5), ("frost",), 0.0)
        for pk, (u0, u1, v0, v1) in CLAD.items():
            if same_plane(pk, plane) and u0 < u < u1 and v0 < v < v1:
                return ("shell", "clad", ("box", 2.4), ("flat", mul(self.T["clad"], C_JOINT)), -0.009)
        return ("shell", "printed", ("box", 1.28), ("ao",), 0.0)

    def int_zone(self, wid, plane, u, v, p):
        axis, sign, c = plane
        garage = p.y < GARAGE_Y + 0.1 and p.z < G["zslab"]
        if garage:
            return ("interior", "concrete", ("box", 2.0), ("flat", (0.97, 0.96, 0.95)), 0.0)
        col = (1, 1, 1)
        if p.z < G["zslab"] and axis == 0 and sign > 0 and abs(c - (G["xw"] + 0.3)) < 0.01:
            col = self.T["accent_gf"]
        if p.z > G["zuf"] and wid == "W_UF_P" and sign > 0:
            col = self.T["accent_uf"]
        return ("interior", "plaster", ("box", 2.0), ("flat", col), 0.0)

    def emit_face(self, plane, r, k):
        axis, sign, c = plane
        accn, mat, uvs, cols, off = k
        u0, v0, u1, v1 = r
        if mat == "printed" and axis != 2 and u1 - u0 > 0.06:
            n = [0.0, 0.0]
            n[axis] = float(sign)
            t = ccw_t(n)
            off = self.u_off.get(plane_key(axis, sign, c), 0.0)
            a, b = ppt(axis, c, u0, 0.0), ppt(axis, c, u1, 0.0)
            us = [a.x * t[0] + a.y * t[1] + off, b.x * t[0] + b.y * t[1] + off]
            bead_ribbon(self.acc[accn], [((a.x, a.y), n, n), ((b.x, b.y), n, n)], v0, v1, us=us)
            return
        if mat == "printed":
            uvs = ("box", PRINT_REP)
        cc = c + sign * off
        pts = [ppt(axis, cc, u0, v0), ppt(axis, cc, u1, v0), ppt(axis, cc, u1, v1), ppt(axis, cc, u0, v1)]
        want = [0, 0, 0]
        want[axis] = sign
        uv = self.uvspec(uvs, plane)
        if cols[0] == "ao":
            col = lambda q: (0.80 + 0.20 * min(1.0, max(q.z, 0.0) / 0.7),) * 3  # noqa: E731
        elif cols[0] == "frost":
            z0g, z1g = GLASS_Z0, G["zpar"]

            def col(q):
                t = max(0.0, min(1.0, (q.z - z0g) / (z1g - z0g)))
                return tuple(lo + (hi - lo) * t for lo, hi in zip(C_FROST_LO, C_FROST_HI))
        else:
            col = cols[1]
        self.acc[accn].poly(pts, mat, uv, col, want=want)
        if accn == "interior" and mat == "plaster" and axis != 2 and (abs(v0) < 0.01 or abs(v0 - G["zuf"]) < 0.01):
            self.skirting.append((plane, u0, u1, v0))

    def uvspec(self, s, plane):
        kind = s[0]
        axis, sign, c = plane
        if kind == "box":
            return uv_box(s[1])
        if kind == "trimflat":
            return uv_trim(s[1], 0 if axis != 0 else 1, None)
        if kind == "trim_any":
            return uv_box(2.0)
        if kind == "deck":     # decking boards run east-west (the texture's grain runs along V)
            return lambda pts, n: [(p.y / 1.6, p.x / 1.6) for p in pts]
        if kind == "roller":
            z0 = s[1]
            return uv_trim("garage_door_slats", 0, 2, z0, 0.25)
        if kind == "reveal":
            wid, strip = s[1], s[2]
            w = WALLS[wid]
            lo = w["cl"] - w["t"] / 2
            along = 2 if axis != 2 else (1 - w["ax"])
            if axis == 2:
                along = 1 if w["ax"] == 0 else 0
            return uv_trim(strip, along, w["ax"], lo, w["t"])
        raise ValueError(kind)

    # ----------------------------------------------------------------------------------- printed corners
    def corner(self, C, nA, nB, z0, z1, w=0.55, r=0.05, th=40.0):
        """A 3D-printed rounded corner on a SQUARE collision corner. The collision wins, so the silhouette can only
        round by r (<= 5 cm, LAYOUT rule 7); the curve is carried by shading: over a band of width w on each face the
        shading normals turn continuously like a cylinder's (0 -> th deg), the real round carries the rest, and the
        print beads wrap around it. The band rectangles are registered so the generic pass leaves them out."""
        C = V((C[0], C[1], 0.0))
        nA, nB = V((nA[0], nA[1], 0.0)), V((nB[0], nB[1], 0.0))
        tA, tB = -nB, -nA
        for n_, t_ in ((nA, tA), (nB, tB)):
            axis = 0 if abs(n_.x) > 0.5 else 1
            sign = 1 if (n_.x + n_.y) > 0 else -1
            c = C[axis]
            ua = 1 - axis
            a, bb = C[ua], C[ua] + t_[ua] * w
            self.extra_cover.setdefault((axis, sign, c), []).append((min(a, bb), z0, max(a, bb), z1))

        def bent(theta, n1, n2):
            t = math.radians(theta)
            return (n1 * math.cos(t) + n2 * math.sin(t)).normalized()

        sth = math.sin(math.radians(th))

        def alpha(s):   # cylinder-like: normal angle grows fastest near the corner
            return math.degrees(math.asin(min(1.0, (w - s) / (w - r) * sth)))
        svals = [w, r + (w - r) * 0.70, r + (w - r) * 0.45, r + (w - r) * 0.24, r + (w - r) * 0.09, r]
        cols = []
        for s in svals:
            p = C + tA * s
            cols.append(((p.x, p.y), nA, bent(alpha(s), nA, nB)))
        O = C - nA * r - nB * r
        segs = 4
        for j in range(1, segs):
            phi = 90.0 * j / segs
            rad = nA * math.cos(math.radians(phi)) + nB * math.sin(math.radians(phi))
            p = O + rad * r
            cols.append(((p.x, p.y), rad, bent(th + phi * (90.0 - 2 * th) / 90.0, nA, nB)))
        for s in reversed(svals):
            p = C + tB * s
            cols.append(((p.x, p.y), nB, bent(alpha(s), nB, nA)))
        # U: continue face A's CCW world U through the round into face B and remember B's offset (or the reverse)
        keys, tans = [], []
        for n_ in (nA, nB):
            axis = 0 if abs(n_.x) > 0.5 else 1
            sign = 1 if (n_.x + n_.y) > 0 else -1
            keys.append(plane_key(axis, sign, C[axis]))
            tans.append(ccw_t((n_.x, n_.y)))
        P0, P1 = V((*cols[0][0], 0.0)), V((*cols[-1][0], 0.0))
        d0 = V((*cols[1][0], 0.0)) - P0
        dirn = 1.0 if d0.x * tans[0][0] + d0.y * tans[0][1] > 0 else -1.0
        arc = [0.0]
        for i in range(1, len(cols)):
            arc.append(arc[-1] + (V((*cols[i][0], 0.0)) - V((*cols[i - 1][0], 0.0))).length)
        uA = P0.x * tans[0][0] + P0.y * tans[0][1]
        uB = P1.x * tans[1][0] + P1.y * tans[1][1]
        if keys[0] in self.u_off or keys[1] not in self.u_off:
            u0_ = uA + self.u_off.setdefault(keys[0], 0.0)
            us = [u0_ + dirn * a for a in arc]
            self.u_off[keys[1]] = us[-1] - uB
        else:
            u1_ = uB + self.u_off[keys[1]]
            us = [u1_ - dirn * (arc[-1] - a) for a in arc]
            self.u_off[keys[0]] = us[0] - uA
        bead_ribbon(self.acc["shell"], cols, z0, z1, us=us)

    # ----------------------------------------------------------------------------------- cladding
    def clad_region(self, plane, u0, u1, v0, v1, holes, col_w=1.2, rows=(), clip=None, d=0.0, gap=0.014):
        axis, sign, c = plane
        n = max(1, math.ceil((u1 - u0) / col_w))
        cols = [u0 + i * col_w for i in range(n)] + [u1]
        automatic_rows = [v0 + 2.4 * i for i in range(1, math.ceil((v1 - v0) / 2.4))]
        rws = sorted(set([v0, v1] + [x for x in list(rows) + automatic_rows if v0 + 0.05 < x < v1 - 0.05]))
        acc = self.acc["clad"]
        for i in range(len(cols) - 1):
            for j in range(len(rws) - 1):
                cell = (cols[i], rws[j], cols[i + 1], rws[j + 1])
                hl = []
                for h in holes:
                    r = (max(cell[0], h[0]), max(cell[1], h[1]), min(cell[2], h[2]), min(cell[3], h[3]))
                    if r[2] - r[0] > EPS and r[3] - r[1] > EPS:
                        hl.append(r)
                for (a, b, cc, dd) in rect_subtract(cell, hl):
                    if cc - a < 0.12 or dd - b < 0.12:
                        continue
                    poly = rect_poly(a + gap / 2, b + gap / 2, cc - gap / 2, dd - gap / 2)
                    if clip:
                        for hp in clip:
                            poly = clip_poly(poly, *hp)
                            if len(poly) < 3:
                                break
                        if len(poly) < 3:
                            continue
                        area = 0.5 * abs(sum(poly[q][0] * poly[(q + 1) % len(poly)][1] -
                                             poly[(q + 1) % len(poly)][0] * poly[q][1] for q in range(len(poly))))
                        if area < 0.04:
                            continue
                    jit = 1.0 + self.rng.uniform(-0.055, 0.055)
                    hue = (1.0 + self.rng.uniform(-0.022, 0.022), 1.0, 1.0 + self.rng.uniform(-0.025, 0.025))
                    col = tuple(min(1.0, t * jit * hh) for t, hh in zip(self.T["clad"], hue))
                    uv = uv_box(2.4, self.rng.random(), self.rng.random() * 0.3)
                    bevel_panel(acc, plane, poly, "clad", col, uv)

    # ----------------------------------------------------------------------------------- facade overlays
    def band(self, plane, u0, u1, v0, v1, d=0.016, strip="sill_cream", acc="trim", col=C_TRIM):
        axis, sign, c = plane
        along = 2 if (v1 - v0) > (u1 - u0) else (1 if axis == 0 else 0)
        mn = ppt(axis, c, u0, v0)
        mx = ppt(axis, c + sign * d, u1, v1)
        lo = V([min(a, b) for a, b in zip(mn, mx)])
        hi = V([max(a, b) for a, b in zip(mn, mx)])
        box(self.acc[acc], lo, hi, "trim", col, trim_box_uv(strip, along), skip=((axis, -sign),))

    def opening_overlays(self):
        holes = {pk: [] for pk in CLAD}
        for o in OPENINGS:
            w = WALLS[o["wall"]]
            ax = w["ax"]
            u0, u1 = o["span"]
            sill, head = o["sill"], o["head"]
            kind = o["kind"]
            if w["ext"] != 0:
                cout = w["cl"] + w["ext"] * w["t"] / 2
                cin = w["cl"] - w["ext"] * w["t"] / 2
                pout = (ax, w["ext"], cout)
                pin = (ax, -w["ext"], cin)
                clad = any(same_plane(pk, pout) for pk in CLAD) and self.in_clad(pout, (u0 + u1) / 2, (sill + head) / 2)
                if kind in ("window", "clerestory"):
                    fw = 0.22 if clad else 0.14
                    if o["floor"] == "UF" and kind == "window" and clad:
                        fw = 0.27
                    self.band(pout, u0 - fw, u0, sill, head + fw, 0.018, "window_surround_cream")
                    self.band(pout, u1, u1 + fw, sill, head + fw, 0.018, "window_surround_cream")
                    self.band(pout, u0, u1, head, head + fw, 0.018, "window_surround_cream")
                    self.band(pout, u0 - fw - 0.05, u1 + fw + 0.05, sill - 0.09, sill, 0.019, "sill_cream")
                    hole = (u0 - fw - 0.06, sill - 0.10, u1 + fw + 0.06, head + fw + 0.01)
                    self.window_frame(o, w)
                    if kind == "window" and o["id"] != "W_GF_GARWIN":
                        self.curtains(pin, u0, u1, sill, head)
                elif kind in ("door", "door2"):
                    fw = 0.13
                    self.band(pout, u0 - fw, u0, sill, head + fw, 0.018, "door_frame_cream")
                    self.band(pout, u1, u1 + fw, sill, head + fw, 0.018, "door_frame_cream")
                    self.band(pout, u0, u1, head, head + fw, 0.018, "door_frame_cream")
                    hole = (u0 - fw - 0.01, -1.0, u1 + fw + 0.01, head + fw + 0.01)
                    self.threshold(o, w)
                    self.door_leaves(o, w, pin, exterior=True)
                elif kind == "roller":
                    self.roller(o, w, pout, pin)
                    hole = None
                for pk in CLAD:
                    if hole and same_plane(pk, pout):
                        holes[pk].append(hole)
            else:  # partition doors: architraves both sides + leaf
                for es in (1, -1):
                    pl = (ax, es, w["cl"] + es * w["t"] / 2)
                    fw = 0.08
                    self.band(pl, u0 - fw, u0, sill, head + fw, 0.012, "door_frame_cream", acc="interior")
                    self.band(pl, u1, u1 + fw, sill, head + fw, 0.012, "door_frame_cream", acc="interior")
                    self.band(pl, u0, u1, head, head + fw, 0.012, "door_frame_cream", acc="interior")
                self.door_leaves(o, w, None, exterior=False)
                self.threshold(o, w)
        return holes

    def in_clad(self, plane, u, v):
        for pk, (u0, u1, v0, v1) in CLAD.items():
            if same_plane(pk, plane) and u0 < u < u1 and v0 < v < v1:
                return True
        return False

    def window_frame(self, o, w):
        """Slim dark aluminium frame inside the reveal (intrudes <= 1.8 cm into the opening)."""
        ax = w["ax"]
        ua = 1 - ax
        u0, u1 = o["span"]
        z0, z1 = o["sill"], o["head"]
        d0, d1 = w["cl"] - 0.035, w["cl"] + 0.035
        e = 0.018
        acc = self.acc["trim"]
        uvb = trim_box_uv("window_frame_dark", 2)
        for (a, b, za, zb, along) in ((u0, u0 + e, z0, z1, 2), (u1 - e, u1, z0, z1, 2),
                                      (u0, u1, z1 - e, z1, ua), (u0, u1, z0, z0 + e, ua)):
            mn = [0, 0, 0]
            mx = [0, 0, 0]
            mn[ax], mx[ax] = d0, d1
            mn[ua], mx[ua] = a, b
            mn[2], mx[2] = za, zb
            box(acc, mn, mx, "trim", WHITE, trim_box_uv("window_frame_dark", along))
        del uvb

    def curtains(self, pin, u0, u1, sill, head):
        """Light curtains drawn back against the inner wall face beside the window (<= 1.8 cm deep)."""
        axis, sign, c = pin
        acc = self.acc["interior"]
        z0, z1 = max(sill - 0.35, G["zuf"] + 0.02 if sill > G["zuf"] else 0.02), head + 0.22
        col = srgb(236, 228, 210)
        for (a, b) in ((u0 - 0.42, u0 - 0.03), (u1 + 0.03, u1 + 0.42)):
            folds = 6
            pts_u = [a + (b - a) * k / folds for k in range(folds + 1)]
            for k in range(folds):
                da = 0.004 if k % 2 == 0 else 0.017
                db = 0.017 if k % 2 == 0 else 0.004
                q = [ppt(axis, c + sign * da, pts_u[k], z0), ppt(axis, c + sign * db, pts_u[k + 1], z0),
                     ppt(axis, c + sign * db, pts_u[k + 1], z1), ppt(axis, c + sign * da, pts_u[k], z1)]
                want = [0, 0, 0]
                want[axis] = sign
                acc.poly(q, "fabric", uv_box(1.0), col, want=want)
        # rail
        self.band(pin, u0 - 0.45, u1 + 0.45, head + 0.22, head + 0.26, 0.018, "plain_dark", acc="interior",
                  col=WHITE)

    def entrance(self):
        """Front door: proud cream header with dark drip and warm lamp, kept inside the 2 cm relief allowance.
        The original 25 cm canopy produced ghost hits; a deeper canopy needs a matching game brush."""
        o = next(x for x in OPENINGS if x["id"] == "W_GF_FRONT")
        w = WALLS[o["wall"]]
        x0 = w["cl"] + w["ext"] * w["t"] / 2
        u0, u1 = o["span"]
        z0 = o["head"] + 0.22
        acc = self.acc["trim"]
        box(acc, (x0, u0 - 0.35, z0 + 0.012), (x0 + 0.019, u1 + 0.35, z0 + 0.09), "trim", C_TRIM,
            trim_box_uv("coping_cream", 1), skip=((0, -1),))
        box(acc, (x0, u0 - 0.33, z0), (x0 + 0.017, u1 + 0.33, z0 + 0.012), "trim", WHITE,
            trim_box_uv("plain_dark", 1), skip=((0, -1),))
        for yy in (u0 - 0.36, u1 + 0.30):
            box(acc, (x0, yy, 1.86), (x0 + 0.018, yy + 0.06, 2.12), "trim", WHITE, trim_box_uv("plain_dark", 2),
                skip=((0, -1),))
            box(self.acc["props"], (x0 + 0.018, yy + 0.008, 1.90), (x0 + 0.0195, yy + 0.052, 2.08), "lamp", WHITE,
                uv_box(1.0), skip=((0, -1),))

    def threshold(self, o, w):
        ax = w["ax"]
        ua = 1 - ax
        u0, u1 = o["span"]
        z = o["sill"]
        mn, mx = [0, 0, 0], [0, 0, 0]
        mn[ax], mx[ax] = w["cl"] - w["t"] / 2, w["cl"] + w["t"] / 2
        mn[ua], mx[ua] = u0, u1
        mn[2], mx[2] = z, z + 0.012
        box(self.acc["trim"], mn, mx, "trim", C_TRIM, trim_box_uv("sill_cream", ua), skip=((2, -1),))

    DOOR_HINGE = {"W_GF_FRONT": "both", "W_GF_PATIO": "slide_hi", "W_GF_BACK": "hi", "W_GF_GARDOOR": "hi",
                  "W_UF_TERDOOR": "hi", "W_UF_PD1": "hi", "W_UF_PD2": "lo"}
    DOOR_FACE = {"W_GF_GARDOOR": 1, "W_UF_PD1": 1, "W_UF_PD2": 1}   # partitions: side of the wall (+/-)

    def door_leaves(self, o, w, pin, exterior):
        """Door leaves stand open, flat against the inner wall face (1.5 cm), next to the opening."""
        ax = w["ax"]
        u0, u1 = o["span"]
        z0, z1 = o["sill"], o["head"] - 0.01
        hinge = self.DOOR_HINGE.get(o["id"], "hi")
        if pin is None:
            es = self.DOOR_FACE.get(o["id"], 1)
            pin = (ax, es, w["cl"] + es * w["t"] / 2)
        axis, sign, c = pin
        acc = self.acc["doors"]
        width = (u1 - u0) / (2 if o["kind"] == "door2" else 1)
        spans = []
        if hinge in ("hi", "both"):
            spans.append((u1, u1 + width))
        if hinge in ("lo", "both"):
            spans.append((u0 - width, u0))
        col = self.T["door"] if exterior else C_INT_WHITE
        if hinge == "slide_hi":   # sliding patio leaves parked over the wall: dark frame + glass
            a, b = u1 + 0.02, u1 + 0.02 + (u1 - u0) / 2
            self.band(pin, a, b, z0, z1, 0.016, "window_frame_dark", acc="doors", col=WHITE)
            mn = ppt(axis, c + sign * 0.017, a + 0.06, z0 + 0.06)
            mx = ppt(axis, c + sign * 0.017, b - 0.06, z1 - 0.06)
            pts = [mn, ppt(axis, c + sign * 0.017, b - 0.06, z0 + 0.06), mx, ppt(axis, c + sign * 0.017, a + 0.06, z1 - 0.06)]
            want = [0, 0, 0]
            want[axis] = sign
            acc.poly(pts, "glass", uv_box(1.0), C_GLASS, want=want)
            return
        for (a, b) in spans:
            lo = ppt(axis, c, a + 0.01, z0)
            hi = ppt(axis, c + sign * 0.015, b - 0.01, z1)
            box(acc, [min(p, q) for p, q in zip(lo, hi)], [max(p, q) for p, q in zip(lo, hi)], "paint", col,
                uv_box(1.0), skip=((axis, -sign),))
            # a long vertical pull on the free edge
            fe = b - 0.12 if (a + b) / 2 > (u0 + u1) / 2 else a + 0.12
            lo = ppt(axis, c + sign * 0.015, fe - 0.015, z0 + 0.8)
            hi = ppt(axis, c + sign * 0.019, fe + 0.015, z0 + 1.35)
            box(acc, [min(p, q) for p, q in zip(lo, hi)], [max(p, q) for p, q in zip(lo, hi)], "metal", C_STEEL,
                uv_box(1.0), skip=((axis, -sign),))

    def roller(self, o, w, pout, pin):
        """Garage roller door jammed half-open: slats are the lintel faces (generic pass); add guides + rail."""
        ax = w["ax"]
        ua = 1 - ax
        u0, u1 = o["span"]
        acc = self.acc["trim"]
        # bottom rail (inside the lintel volume, flush +-1.2 cm)
        mn, mx = [0, 0, 0], [0, 0, 0]
        mn[ax], mx[ax] = w["cl"] - w["t"] / 2 - 0.012, w["cl"] + w["t"] / 2 + 0.012
        mn[ua], mx[ua] = u0, u1
        mn[2], mx[2] = o["head"], o["head"] + 0.07
        box(acc, mn, mx, "trim", WHITE, trim_box_uv("window_frame_dark", ua))
        for pl in (pout, pin):
            self.band(pl, u0 - 0.07, u0, 0.0, 2.75, 0.016, "window_frame_dark", col=WHITE)
            self.band(pl, u1, u1 + 0.07, 0.0, 2.75, 0.016, "window_frame_dark", col=WHITE)
        self.band(pout, u0 - 0.23, u0 - 0.07, 0.0, 2.91, 0.018, "door_frame_cream")
        self.band(pout, u1 + 0.07, u1 + 0.23, 0.0, 2.91, 0.018, "door_frame_cream")
        self.band(pout, u0 - 0.07, u1 + 0.07, 2.75, 2.91, 0.018, "door_frame_cream")

    # ----------------------------------------------------------------------------------- facades
    def facades(self):
        holes = self.opening_overlays()
        zb0, zb1 = G["zslab"], G["zuf"] + 0.12
        for pk, (u0, u1, v0, v1) in CLAD.items():
            hl = list(holes[pk])
            rows = []
            if pk == P_E:
                self.band(pk, u0, u1, 0.0, 0.12, 0.016, "sill_cream")
                self.band(pk, u0, u1, zb0, zb1, 0.016, "sill_cream")
                hl += [(u0 - 1, -1, u1 + 1, 0.12), (u0 - 1, zb0, u1 + 1, zb1)]
            elif pk == P_SU:
                self.band(pk, u0, u1, G["zuf"], G["zuf"] + 0.12, 0.016, "sill_cream")
                hl += [(u0 - 1, G["zuf"] - 1, u1 + 1, G["zuf"] + 0.12)]
            else:
                self.band(pk, u0, u1, zb0, zb1, 0.016, "sill_cream")
                hl += [(u0 - 1, v0 - 1, u1 + 1, zb1)]
            # fascia under the gutter on the long sides; eave band on the gables
            if pk[0] == 1:
                hl.append((u0 - 1, G["zeave"] - 0.22, u1 + 1, G["zeave"] + 1))
            self.clad_region(pk, u0, u1, v0, v1, hl, rows=rows)
            # cream stop beads where the printed corner towers meet the cladding (clean edge, hides the bead teeth)
            for uu in (u0, u1):
                self.band(pk, uu - 0.035, uu + 0.035, v0, v1, 0.0175, "sill_cream")

    def corners(self):
        xw, xe, ys, yn, yms = G["xw"], G["xe"], G["ys"], G["yn"], G["yms"]
        zu, ze = G["zuf"], G["zeave"]
        par = wall_union("W_TER_PE")
        pe = par[1][0]
        ps = wall_union("W_TER_PS")[0][1]
        gh = 2.8   # greenhouse roof slab top engulfs the NE corner below this
        yard = wall_union("W_YARD_EN")[1][2]
        self.corner((xe, ys), (1, 0), (0, -1), 0.0, zu, w=0.62)         # garage street corner
        self.corner((pe, ps), (1, 0), (0, -1), zu, GLASS_Z0, w=0.5)     # terrace parapet upstand corner
        self.corner((xe, yms), (1, 0), (0, -1), G["zpar"], ze)          # main block SE above the parapet
        self.corner((xe, yn), (1, 0), (0, 1), gh, ze)                   # NE above the greenhouse
        self.corner((xw, yn), (-1, 0), (0, 1), yard, ze)                # NW above the yard wall

    # ----------------------------------------------------------------------------------- parapets, screens
    def parapets(self):
        """Terrace balustrade inside the 1.0 m parapet brushes (concept: printed upstand + glass railing):
        a beaded printed upstand to GLASS_Z0 with a cream ledge, then FROSTED glass (opaque, like every bullet-proof
        surface in the collision) between slim steel posts, under a brushed-steel handrail. Everything stays inside
        the brush within 1.8 cm. Slatted timber privacy screens with a dark cap."""
        acc = self.acc["trim"]
        pe_mn, pe_mx = wall_union("W_TER_PE")
        ps_mn, ps_mx = wall_union("W_TER_PS")
        zt = G["zpar"]
        xc = (pe_mn[0] + pe_mx[0]) / 2
        yc = (ps_mn[1] + ps_mx[1]) / 2
        sw_mn, sw_mx = wall_union("W_TER_SW")
        ss_mn, ss_mx = wall_union("W_TER_SS")
        hw = (pe_mx[0] - pe_mn[0]) / 2
        # handrail: brushed steel, 1.2 cm overhang each side, rounded top edges
        o = 0.012
        prof = [(-hw - o, -0.055), (hw + o, -0.055), (hw + o, -0.012), (hw + o - 0.012, 0.0), (-hw - o + 0.012, 0.0),
                (-hw - o, -0.012)]
        prof = [(a_, b_ + zt - 0.001) for a_, b_ in prof]
        path = [V((ss_mx[0], yc, 0)), V((xc, yc, 0)), V((xc, G["yms"], 0))]
        sweep(acc, path, prof, "trim", WHITE, strip="railing_cap_steel")
        # ledge over the printed upstand + dark glazing shoe (both faces)
        z0 = GLASS_Z0
        runs = [((1, -1, ps_mn[1]), ss_mx[0], pe_mx[0]), ((1, 1, ps_mx[1]), ss_mx[0], pe_mn[0]),
                ((0, 1, pe_mx[0]), ps_mn[1], G["yms"]), ((0, -1, pe_mn[0]), ps_mx[1], G["yms"])]
        for pl, u0, u1 in runs:
            self.band(pl, u0, u1, z0 - 0.06, z0, 0.017, "sill_cream")
            self.band(pl, u0, u1, z0, z0 + 0.045, 0.009, "window_frame_dark", col=WHITE)
            # posts every ~1.5 m (clamped panels), flush steel
            n = max(1, round((u1 - u0) / 1.5))
            for k in range(n + 1):
                u = u0 + (u1 - u0) * k / n
                ua, ub = max(u0, u - 0.025), min(u1, u + 0.025)
                self.band(pl, ua, ub, z0 + 0.045, zt - 0.055, 0.012, "railing_cap_steel", col=WHITE)
        # screens: battens both sides + a dark cap (top kept 3 mm under the brush top)
        for mn, mx in ((sw_mn, sw_mx), (ss_mn, ss_mx)):
            ax = 0 if (mx[0] - mn[0]) < (mx[1] - mn[1]) else 1
            ua = 1 - ax
            L0, L1 = mn[ua], mx[ua]
            ztop = mx[2] - 0.003
            cap_mn, cap_mx = list(mn), list(mx)
            cap_mn[2], cap_mx[2] = ztop - 0.03, ztop
            cap_mn[ax] -= 0.01
            cap_mx[ax] += 0.01
            box(acc, cap_mn, cap_mx, "trim", WHITE, trim_box_uv("flashing_dark", ua))
            n = int((L1 - L0) / 0.11)
            for side in (-1, 1):
                c = mx[ax] if side > 0 else mn[ax]
                for k in range(n):
                    a_ = L0 + 0.03 + k * (L1 - L0 - 0.06) / n
                    b_ = a_ + 0.05
                    lo, hi = [0, 0, 0], [0, 0, 0]
                    lo[ax], hi[ax] = (c, c + 0.014) if side > 0 else (c - 0.014, c)
                    lo[ua], hi[ua] = a_, b_
                    lo[2], hi[2] = mn[2], ztop - 0.03
                    box(self.acc["shell"], lo, hi, "timber", (0.82, 0.78, 0.74), uv_box(2.0, k * 0.37),
                        skip=((ax, -side),))

    # ----------------------------------------------------------------------------------- roof
    def roof(self):
        xw, xe = G["rx0"], G["rx1"]
        ze, zr, yr = G["zeave"], G["zridge"], G["ridge_y"]
        ys0, yn0 = G["eave_ys"], G["eave_yn"]
        acc = self.acc["roof"]
        s2 = math.sqrt(2.0)
        for (ya, sgn) in ((ys0, 1), (yn0, -1)):
            nrm = V((0, -sgn, 1)).normalized()
            slope_length = (yr - ya) * sgn * s2
            def uvf(ps, n, ya=ya, sgn=sgn):
                # Tangential projection ignores the normal relief, so v2 butt/height lines align exactly
                # with the geometric courses even after their tiny tilt and thickness variation.
                return [(p.x / 2.0, (sgn * (p.y - ya) + (p.z - ze)) / s2 / 2.0) for p in ps]
            # One lightweight strip per course, true 10 mm butt thickness. The staggered shingle joints
            # remain in the exact v2 albedo/height/normal sheet, rather than thousands of separate shingles.
            for course in range(math.ceil(slope_length / 0.25)):
                sa, sb = course * 0.25, min(slope_length, (course + 1) * 0.25)
                value = 1.0 + math.sin(course * 1.73) * 0.028
                def P(x, s, h):
                    return V((x, ya + sgn * s / s2, ze + s / s2)) + nrm * h
                # Contiguous quads form one strip. Their boundaries follow the texture's half bond so a
                # tiny deterministic per-shingle tilt/value variation does not require individual objects.
                half_bond = 0.25 if course % 2 else 0.0
                xs = [xw] + [half_bond + k * 0.5 for k in range(math.floor(xw / 0.5), math.ceil(xe / 0.5) + 1)
                              if xw + 1e-5 < half_bond + k * 0.5 < xe - 1e-5] + [xe]
                for tile in range(len(xs) - 1):
                    xa, xb = xs[tile:tile + 2]
                    ha = 0.010 + math.sin(xa * 4.3 + course * 2.399) * 0.0008
                    hb = 0.010 + math.sin(xb * 4.3 + course * 2.399) * 0.0008
                    colour = mul(C_ROOF, value * (1.0 + math.sin(tile * 2.7 + course * 0.67) * 0.020))
                    top = [P(xa, sa, ha), P(xb, sa, hb), P(xb, sb, 0.001), P(xa, sb, 0.001)]
                    base = [P(xa, sa, 0), P(xb, sa, 0), P(xb, sb, 0), P(xa, sb, 0)]
                    acc.poly(top, "roof", uvf, colour, want=nrm)
                    sides = [(0, 1)]
                    if tile == 0: sides.append((3, 0))
                    if tile == len(xs) - 2: sides.append((1, 2))
                    for a, b in sides:
                        edge = [base[a], base[b], top[b], top[a]]
                        want = (top[a] + top[b]) / 2 - sum(top, V()) / 4
                        acc.poly(edge, "roof", uvf, mul(colour, 0.87), want=want)
        # Angled caps sit above the ridge; the visible joints break up the twelve metre run.
        prof = [(-0.17, -0.155), (0.0, 0.018), (0.17, -0.155), (0.17, -0.167), (0.0, 0.006), (-0.17, -0.167)]
        prof = [(a, b + zr) for a, b in prof]
        for k in range(math.ceil((xe - xw) / 0.5)):
            xa, xb = xw + k * 0.5 + 0.0015, min(xe, xw + (k + 1) * 0.5) - 0.0015
            sweep(acc, [V((xa, yr, 0)), V((xb, yr, 0))], prof, "roof_edge", WHITE, rep=2.0, ulen=2.0)
        # eaves: fascia on the wall face + half-round gutter on the wall top
        for (yf, sgn) in ((G["yms"], -1), (G["yn"], 1)):
            pl = (1, sgn, yf)
            self.band(pl, xw, xe, ze - 0.22, ze, 0.016, "fascia_dark", col=WHITE)
            yc = yf + sgn * (0.018 - 0.07)
            R1, R2 = 0.07, 0.058
            prof = []
            for k in range(9):
                a = math.radians(180 + 180 * k / 8)
                prof.append((R1 * math.cos(a), R1 * math.sin(a)))
            for k in range(9):
                a = math.radians(360 - 180 * k / 8)
                prof.append((R2 * math.cos(a), R2 * math.sin(a)))
            prof = [(a * sgn, b + ze - 0.002) for a, b in prof]
            sweep(self.acc["trim"], [V((xw, yc, 0)), V((xe, yc, 0))], prof, "trim", WHITE, strip="gutter_dark")
        # gable ends: clad triangle + cream barge boards + eave band
        bw = 0.3
        for (xg, sg) in ((xe, 1), (xw, -1)):
            pl = (0, sg, xg)
            tri = [(ys0, ze), (yn0, ze), (yr, zr)]
            prism(self.acc["shell"], pl, tri, -0.15, -0.009, "clad", mul(self.T["clad"], C_JOINT), uv_box(2.4),
                  sides=False)
            # half-planes in (u = y, v = z): below the S slope  z <= ze + (y - ys0)  ->  -y + z <= ze - ys0
            off = bw * s2
            inner = [(-1.0, 1.0, ze - ys0 - off), (1.0, 1.0, ze + yn0 - off)]
            # barge boards: a cream band bw wide below each roof edge, rising 5 cm above the roof plane
            # (verge over the roof edge); mitred vertically at the apex
            up = 0.018 * s2
            for sl in ("S", "N"):
                if sl == "S":
                    poly = rect_poly(ys0 - 0.3, ze, yr, zr + 0.3)
                    poly = clip_poly(poly, -1.0, 1.0, ze - ys0 + up)          # below the verge line
                    poly = clip_poly(poly, 1.0, -1.0, -(ze - ys0 - off))      # above the inner line

                    def uvb(ps, n):
                        v0, v1 = STRIPS["sill_cream"]
                        return [((p.y + p.z) / s2 / 4.0, v0 + max(0.0, min(1.0, ((p.z - p.y) - (ze - ys0 - off)) /
                                                                              (off + up))) * (v1 - v0)) for p in ps]
                else:
                    poly = rect_poly(yr, ze, yn0 + 0.3, zr + 0.3)
                    poly = clip_poly(poly, 1.0, 1.0, ze + yn0 + up)
                    poly = clip_poly(poly, -1.0, -1.0, -(ze + yn0 - off))

                    def uvb(ps, n):
                        v0, v1 = STRIPS["sill_cream"]
                        return [((p.z - p.y) / s2 / 4.0, v0 + max(0.0, min(1.0, ((p.z + p.y) - (ze + yn0 - off)) /
                                                                              (off + up))) * (v1 - v0)) for p in ps]
                if len(poly) >= 3:
                    prism(self.acc["trim"], pl, poly, -0.16, 0.02, "trim", C_TRIM, uvb)
            # eave band across the gable base
            poly = clip_poly(clip_poly(rect_poly(G["yms"], ze, G["yn"], ze + 0.26), *inner[0]), *inner[1])
            if len(poly) >= 3:
                prism(self.acc["trim"], pl, poly, -0.16, 0.018, "trim", C_TRIM, uv_trim("sill_cream", 1, 2, ze, 0.26))
            # cladding panels in the triangle
            self.clad_region(pl, ys0, yn0, ze + 0.26, zr, [], col_w=1.2, rows=(ze + 0.26 + 2.4,),
                             clip=inner)
        self.solar()
        self.chimney()

    def solar(self):
        xw, xe = G["rx0"], G["rx1"]
        ze, yr = G["zeave"], G["ridge_y"]
        s2 = math.sqrt(2.0)
        acc = self.acc["solar"]
        for (ya, sgn, rows, ncol, s0) in ((G["eave_ys"], 1, 3, 10, 0.75), (G["eave_yn"], -1, 3, 8, 0.75)):
            mw, ml, g = 1.0, 1.65, 0.03
            tot = ncol * mw + (ncol - 1) * g
            x0 = (xw + xe) / 2 - tot / 2 + 0.3
            n = V((0, -sgn, 1)).normalized()
            for r in range(rows):
                for cidx in range(ncol):
                    xa = x0 + cidx * (mw + g)
                    xb = xa + mw
                    sa = s0 + r * (ml + g)
                    sb = sa + ml

                    def P(x, s, h):
                        y = ya + sgn * s / s2
                        z = ze + s / s2
                        return V((x, y, z)) + n * h
                    # Rails sit under the modules, visibly bridging the gaps between them. All relief stays
                    # within the 20 mm roof budget, including the air gap over the stepped shingle courses.
                    for rs in (sa + 0.16, sb - 0.16):
                        for h0, h1 in ((0.008, 0.012),):
                            for ds in (-0.018, 0.018):
                                q = [P(xa - 0.015, rs + ds, h0), P(xb + 0.015, rs + ds, h0),
                                     P(xb + 0.015, rs + ds, h1), P(xa - 0.015, rs + ds, h1)]
                                acc.poly(q, "trim", uv_trim("solar_frame", 0, None), WHITE,
                                         want=(0, -sgn if ds < 0 else sgn, 0))
                            q = [P(xa - 0.015, rs - 0.018, h1), P(xb + 0.015, rs - 0.018, h1),
                                 P(xb + 0.015, rs + 0.018, h1), P(xa - 0.015, rs + 0.018, h1)]
                            acc.poly(q, "trim", uv_trim("solar_frame", 0, None), WHITE, want=n)
                    h, underside = 0.0195, 0.014
                    top = [P(xa, sa, h), P(xb, sa, h), P(xb, sb, h), P(xa, sb, h)]
                    acc.poly(top, "solar", [(0, 0), (1, 0), (1, 1), (0, 1)], C_SOLAR, want=n)
                    ring = [(P(xa, sa, underside), P(xb, sa, underside)), (P(xb, sa, underside), P(xb, sb, underside)),
                            (P(xb, sb, underside), P(xa, sb, underside)), (P(xa, sb, underside), P(xa, sa, underside))]
                    cen = P((xa + xb) / 2, (sa + sb) / 2, underside)
                    for a, b in ring:
                        q = [a, b, b + n * (h - underside), a + n * (h - underside)]
                        acc.poly(q, "trim", uv_trim("solar_frame", 0, None), WHITE, want=((a + b) / 2 - cen))

    def chimney(self):
        acc = self.acc["roof"]
        yr, zr = G["ridge_y"], G["zridge"]
        xa, xb = G["xe"] - 2.55, G["xe"] - 1.7
        ya, yb = yr - 0.55, yr + 0.55
        ztop = zr + 1.25
        zbot = zr - 0.75
        box(acc, (xa, ya, zbot), (xb, yb, ztop), "clad", self.T["chimney"], uv_box(2.4, 0.3), skip=((2, -1),))
        box(self.acc["trim"], (xa - 0.05, ya - 0.05, ztop), (xb + 0.05, yb + 0.05, ztop + 0.1), "trim", C_TRIM,
            trim_box_uv("coping_cream", 0))
        for k, xc in enumerate(((xa + xb) / 2 - 0.18, (xa + xb) / 2 + 0.18)):
            box(self.acc["trim"], (xc - 0.08, yr - 0.08, ztop + 0.1), (xc + 0.08, yr + 0.08, ztop + 0.38), "trim",
                WHITE, trim_box_uv("plain_dark", 2))
        # flashing collar where it meets the slopes
        box(self.acc["trim"], (xa - 0.02, ya - 0.02, zbot), (xb + 0.02, yb + 0.02, zr - 0.38), "trim", WHITE,
            trim_box_uv("flashing_dark", 0), skip=((2, -1), (2, 1)))

    def downpipes(self):
        acc = self.acc["trim"]
        ze = G["zeave"]
        for (x, yf, sgn, zb) in ((G["xe"] - 0.62, G["yms"], -1, G["zuf"]), (G["xw"] + 0.62, G["yn"], 1, 0.0)):
            y0, y1 = (yf - 0.045, yf + 0.018) if sgn > 0 else (yf - 0.018, yf + 0.045)
            box(acc, (x - 0.045, y0, zb), (x + 0.045, y1, ze + 0.02), "trim", WHITE, trim_box_uv("gutter_dark", 2))

    def flat_roof_finish(self):
        """Real terrace drainage, wall apron and coping drip. Garage roof is the standable deck at z3.2."""
        acc = self.acc["trim"]
        pe_mn, pe_mx = wall_union("W_TER_PE")
        ps_mn, ps_mx = wall_union("W_TER_PS")
        zt = G["zpar"]
        # Thin drip lip below the existing top coping, proud enough to throw a close-range shadow.
        for pl, a, b in (((0, 1, pe_mx[0]), ps_mn[1], G["yms"]),
                         ((1, -1, ps_mn[1]), G["xw"] + 0.3, pe_mx[0])):
            self.band(pl, a, b, zt - 0.070, zt - 0.060, 0.018, "coping_cream")
        # Apron covers the junction between upper house wall and flat garage roof.
        box(acc, (G["xw"] + 0.35, G["yms"] - 0.08, G["zuf"] + 0.004),
            (G["xe"] - 0.35, G["yms"], G["zuf"] + 0.010), "trim", WHITE,
            trim_box_uv("flashing_dark", 0), skip=((2, -1),))
        # A flush painted drain inset and slim scupper on the inner parapet (no phantom obstacle).
        x, y = pe_mn[0] - 0.12, G["ys"] + 0.45
        box(acc, (x - 0.09, y - 0.09, G["zuf"] + 0.004),
            (x + 0.09, y + 0.09, G["zuf"] + 0.012), "trim", WHITE,
            trim_box_uv("plain_dark", 0), skip=((2, -1),))
        for k in range(4):
            box(acc, (x - 0.075 + k * 0.04, y - 0.074, G["zuf"] + 0.012),
                (x - 0.065 + k * 0.04, y + 0.074, G["zuf"] + 0.015), "trim", WHITE,
                trim_box_uv("railing_cap_steel", 1), skip=((2, -1),))

    # ----------------------------------------------------------------------------------- interior
    def stair(self):
        b = L.brushes(tag="W_STAIR")[0]
        (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
        nsteps = 18
        h = (z1 - z0) / nsteps
        g = (y1 - y0) / nsteps
        acc = self.acc["interior"]
        st = 0.04   # stringer thickness
        # treads: nosing on the slope plane (low end at y1, rising toward y0)
        for k in range(1, nsteps):
            ya = y1 - (k + 1) * g
            yb = y1 - k * g
            zt = z0 + k * h
            box(acc, (x0 + st, ya, zt - 0.04), (x1 - st, yb, zt), "oak", (0.95, 0.92, 0.9),
                uv_box(2.0, 0.1 * k), skip=((0, -1), (0, 1)))
            # riser under the nosing, set back 1.5 cm
            box(acc, (x0 + st, yb - 0.015, zt - h), (x1 - st, yb - 0.0149, zt - 0.04), "paint", C_INT_WHITE,
                uv_box(1.0), skip=((0, -1), (0, 1), (1, -1), (2, 1), (2, -1)))
        # closed stringers (the wedge's side faces), white
        for xs, sgn in ((x0, -1), (x1, 1)):
            for xf, s2_ in ((xs, sgn), (xs - sgn * st, -sgn)):
                pts = [V((xf, y1, 0.0)), V((xf, y0, 0.0)), V((xf, y0, z1))]
                acc.poly(pts, "paint", uv_box(1.0), C_INT_WHITE, want=(s2_, 0, 0))
            # top edge of the stringer along the slope
            q = [V((xs - sgn * st, y1, 0.0)), V((xs, y1, 0.0)), V((xs, y0, z1)), V((xs - sgn * st, y0, z1))]
            acc.poly(q, "paint", uv_box(1.0), C_INT_WHITE, want=(0, 0.6, 0.8))
        # the high end face below the landing (closed under the stair)
        acc.poly([V((x0, y0, 0)), V((x1, y0, 0)), V((x1, y0, G["zslab"])), V((x0, y0, G["zslab"]))], "plaster",
                 uv_box(2.0), WHITE, want=(0, -1, 0))

    def skirting_boards(self):
        acc = self.acc["interior"]
        for (plane, u0, u1, v) in self.skirting:
            axis, sign, c = plane
            if u1 - u0 < 0.05:
                continue
            lo = ppt(axis, c, u0, v)
            hi = ppt(axis, c + sign * 0.012, u1, v + 0.09)
            box(acc, [min(a, b) for a, b in zip(lo, hi)], [max(a, b) for a, b in zip(lo, hi)], "paint", C_INT_WHITE,
                uv_box(1.0), skip=((axis, -sign), (2, -1)))

    def decor(self):
        """Flush interior dressing (rugs, pictures, lights, tiles, pegboard): nothing deeper than 2 cm."""
        acc = self.acc["interior"]
        T = self.T
        # rugs (1.2 cm)
        for (x0, y0, x1, y1, z) in ((15.6, 25.9, 19.9, 28.45, 0.004), (16.2, 23.6, 20.2, 30.4, G["zuf"])):
            box(acc, (x0, y0, z), (x1, y1, z + 0.012), "fabric", T["rug"], uv_box(1.0), skip=((2, -1),))
            box(acc, (x0 + 0.12, y0 + 0.12, z + 0.012), (x1 - 0.12, y1 - 0.12, z + 0.0135), "fabric",
                mul(T["rug"], 0.78), uv_box(1.0), skip=((2, -1),))
        # flush bookshelf on the UF front-room partition (book spines 1.8 cm proud), seen from the street window
        self.bookshelf((0, 1, 15.1), 28.15, 29.7, G["zuf"] + 0.1, G["zuf"] + 2.15)   # clear of the PD2 leaf
        # framed pictures (1.6 cm)
        pics = [
            ((0, 1, G["xw"] + 0.3), 26.0, 27.2, 1.75, 2.45),        # GF back wall, above the splashback
            ((1, -1, G["yn"] - 0.3), 19.55, 20.6, 4.3, 5.1),          # UF front room, beside the garden window
            ((0, 1, 15.1), 26.2, 27.8, 4.65, 5.5),                   # above the dresser
            ((1, -1, G["yn"] - 0.3), 13.2, 14.6, 4.3, 5.1),         # UF landing north wall
            ((1, 1, 22.1), 14.2, 15.4, 1.3, 2.0),                    # GF kitchen side of the partition
        ]
        for k, (pl, u0, u1, v0, v1) in enumerate(pics):
            self.band(pl, u0, u1, v0, v1, 0.014, "window_frame_dark", acc="interior", col=WHITE)
            axis, sign, c = pl
            art = T["art"][k % len(T["art"])]
            q = [ppt(axis, c + sign * 0.016, u0 + 0.06, v0 + 0.06), ppt(axis, c + sign * 0.016, u1 - 0.06, v0 + 0.06),
                 ppt(axis, c + sign * 0.016, u1 - 0.06, v1 - 0.06), ppt(axis, c + sign * 0.016, u0 + 0.06, v1 - 0.06)]
            want = [0, 0, 0]
            want[axis] = sign
            acc.poly(q, "paint", uv_box(1.0), art, want=want)
            # an abstract block inside
            um, vm = (u0 + u1) / 2, (v0 + v1) / 2
            q2 = [ppt(axis, c + sign * 0.017, um - 0.18, vm - 0.12), ppt(axis, c + sign * 0.017, um + 0.12, vm - 0.12),
                  ppt(axis, c + sign * 0.017, um + 0.12, vm + 0.16), ppt(axis, c + sign * 0.017, um - 0.18, vm + 0.16)]
            acc.poly(q2, "paint", uv_box(1.0), T["art"][(k + 1) % len(T["art"])], want=want)
        # ceiling lights (flush discs)
        for (x, y, z) in ((12.0, 25.2, G["zslab"]), (18.0, 27.5, G["zslab"]), (18.0, 27.0, G["zceil"]),
                          (11.6, 28.0, G["zceil"]), (15.0, 19.0, G["zslab"]), (11.0, 18.5, G["zslab"])):
            pts = [V((x + 0.22 * math.cos(math.radians(a)), y + 0.22 * math.sin(math.radians(a)), z - 0.012))
                   for a in range(0, 360, 30)]
            acc.poly(pts, "lamp", uv_box(1.0), WHITE, want=(0, 0, -1))
        # kitchen splashback tiles on the back wall (1 cm)
        self.band((0, 1, G["xw"] + 0.3), 23.2, 27.4, 0.9, 1.55, 0.01, "window_surround_cream", acc="interior")
        # garage: pegboard over the workbench, EV charger
        self.band((0, 1, G["xw"] + 0.3), 17.3, 20.7, 1.2, 2.1, 0.012, "vent_louvre", acc="interior", col=WHITE)
        self.band((1, 1, G["ys"] + 0.3), 17.1, 17.5, 1.0, 1.55, 0.018, "plain_dark", acc="interior", col=WHITE)

    def bookshelf(self, pl, u0, u1, v0, v1):
        """A built-in bookcase drawn flush on a wall (<= 1.8 cm): dark carcass, oak shelves, coloured spines."""
        axis, sign, c = pl
        acc = self.acc["interior"]
        rng = random.Random(11)
        self.band(pl, u0, u1, v0, v1, 0.008, "window_frame_dark", acc="interior", col=WHITE)
        nsh = 5
        h = (v1 - v0) / nsh
        spines = [srgb(196, 132, 96), srgb(122, 140, 98), srgb(230, 214, 180), srgb(84, 96, 120), srgb(160, 60, 52),
                  srgb(210, 170, 90), srgb(60, 66, 70)]
        want = [0, 0, 0]
        want[axis] = sign
        for k in range(nsh):
            vb = v0 + k * h
            self.band(pl, u0, u1, vb, vb + 0.03, 0.017, "sill_cream", acc="interior", col=srgb(200, 160, 120))
            u = u0 + 0.05
            while u < u1 - 0.12:
                wdt = rng.uniform(0.025, 0.06)
                if rng.random() < 0.12:
                    u += rng.uniform(0.1, 0.25)
                    continue
                ht = rng.uniform(0.62, 0.88) * (h - 0.05)
                d = rng.uniform(0.012, 0.017)
                q = [ppt(axis, c + sign * d, u, vb + 0.03), ppt(axis, c + sign * d, u + wdt, vb + 0.03),
                     ppt(axis, c + sign * d, u + wdt, vb + 0.03 + ht), ppt(axis, c + sign * d, u, vb + 0.03 + ht)]
                acc.poly(q, "paint", uv_box(1.0), rng.choice(spines), want=want)
                u += wdt + 0.004
        self.band(pl, u0, u1, v1 - 0.03, v1, 0.017, "sill_cream", acc="interior", col=srgb(200, 160, 120))

    # ----------------------------------------------------------------------------------- props
    def props(self):
        acc = self.acc["props"]
        T = self.T
        P = {b["tag"]["id"]: (b["min"], b["max"]) for b in L.brushes(structure="SAGE_HOUSE_PROPS")}
        # kitchen island: cabinet body, worktop, door seams, toe kick
        (x0, y0, z0), (x1, y1, z1) = P["W_ISLAND"]
        box(acc, (x0 + 0.02, y0 + 0.02, z0), (x1 - 0.02, y1 - 0.02, z0 + 0.1), "paint", C_DARK, uv_box(1.0),
            skip=((2, -1),))
        box(acc, (x0, y0, z0 + 0.1), (x1, y1, z1 - 0.045), "paint", T["cabinet"], uv_box(1.0), skip=((2, -1),))
        box(acc, (x0 - 0.01, y0 - 0.01, z1 - 0.045), (x1 + 0.01, y1 + 0.01, z1), "paint", C_WORKTOP, uv_box(1.0))
        for k in range(1, 4):
            y = y0 + k * (y1 - y0) / 4
            for xf, s in ((x0, -1), (x1, 1)):
                box(acc, (xf - (0.006 if s < 0 else 0), y - 0.006, z0 + 0.14), (xf + (0.006 if s > 0 else 0),
                    y + 0.006, z1 - 0.09), "paint", C_DARK, uv_box(1.0))
        # sofa: chunky upholstered block filling its box (seat cushions and bolsters to the collision top)
        (x0, y0, z0), (x1, y1, z1) = P["W_SOFA"]
        fab = T["fabric"]
        box(acc, (x0 + 0.02, y0 + 0.02, 0.0), (x1 - 0.02, y1 - 0.02, 0.1), "paint", C_DARK, uv_box(1.0), skip=((2, -1),))
        box(acc, (x0, y0, 0.1), (x1, y1, 0.55), "fabric", fab, uv_box(1.0), skip=((2, -1),))
        box(acc, (x0, y1 - 0.3, 0.55), (x1, y1, z1), "fabric", mul(fab, 0.95), uv_box(1.0), skip=((2, -1),))
        for xa, xb in ((x0, x0 + 0.22), (x1 - 0.22, x1)):
            box(acc, (xa, y0, 0.55), (xb, y1 - 0.3, z1), "fabric", mul(fab, 0.92), uv_box(1.0), skip=((2, -1),))
        n = 2
        for k in range(n):
            xa = x0 + 0.22 + k * (x1 - x0 - 0.44) / n + 0.01
            xb = xa + (x1 - x0 - 0.44) / n - 0.02
            box(acc, (xa, y0 + 0.005, 0.55), (xb, y1 - 0.305, z1 - 0.015), "fabric", mul(fab, 1.04), uv_box(1.0),
                skip=((2, -1),))
        for k, xc in enumerate((x0 + 0.55, x1 - 0.55)):
            box(acc, (xc - 0.22, y1 - 0.34, z1 - 0.015), (xc + 0.22, y1 - 0.3, z1 - 0.0), "fabric", T["cushion"],
                uv_box(1.0), skip=((2, -1),))
        # dresser (UF)
        (x0, y0, z0), (x1, y1, z1) = P["W_DRESSER"]
        box(acc, (x0, y0, z0), (x1, y1, z1), "oak", (1, 1, 1), uv_box(2.0, 0.3))
        for k in range(4):
            za = z0 + 0.12 + k * (z1 - z0 - 0.16) / 4
            zb = za + (z1 - z0 - 0.16) / 4 - 0.02
            box(acc, (x1, y0 + 0.06, za), (x1 + 0.012, y1 - 0.06, zb), "oak", (0.9, 0.86, 0.82), uv_box(2.0, 0.6),
                skip=((0, -1),))
            box(acc, (x1 + 0.012, (y0 + y1) / 2 - 0.15, (za + zb) / 2 - 0.012), (x1 + 0.02, (y0 + y1) / 2 + 0.15,
                (za + zb) / 2 + 0.012), "metal", C_STEEL, uv_box(1.0), skip=((0, -1),))
        # garage shelving: uprights + shelves with crates flush with the front plane
        (x0, y0, z0), (x1, y1, z1) = P["W_SHELF"]
        box(acc, (x0, y0 + 0.016, z0), (x1, y1, z1), "paint", srgb(120, 116, 112), uv_box(1.0))
        for k in range(5):
            xa = x0 + k * (x1 - x0) / 4 - (0.03 if k == 4 else 0)
            box(acc, (max(x0, xa - 0.0), y0, z0), (min(x1, xa + 0.03), y0 + 0.03, z1), "metal", C_STEEL, uv_box(1.0),
                skip=((1, 1),))
        rng = random.Random(3)
        for lvl in range(4):
            zs = z0 + 0.05 + lvl * 0.54
            box(acc, (x0, y0, zs), (x1, y0 + 0.03, zs + 0.035), "metal", C_STEEL, uv_box(1.0), skip=((1, 1),))
            xa = x0 + 0.05
            while xa < x1 - 0.3:
                wdt = rng.uniform(0.35, 0.7)
                xb = min(x1 - 0.05, xa + wdt)
                hgt = rng.uniform(0.28, 0.46)
                cc = rng.choice([srgb(208, 164, 118), srgb(196, 150, 104), srgb(92, 96, 104), srgb(214, 206, 190),
                                 T["cushion"]])
                box(acc, (xa, y0 + 0.002, zs + 0.035), (xb, y0 + 0.016, zs + 0.035 + hgt), "paint", cc, uv_box(1.0),
                    skip=((1, 1),))
                xa = xb + rng.uniform(0.04, 0.12)
        # workbench: cabinet + worktop
        (x0, y0, z0), (x1, y1, z1) = P["W_WORKBENCH"]
        box(acc, (x0, y0, z0), (x1, y1, z1 - 0.05), "paint", srgb(92, 96, 104), uv_box(1.0), skip=((2, -1),))
        box(acc, (x0, y0, z1 - 0.05), (x1, y1, z1), "oak", (0.9, 0.85, 0.8), uv_box(2.0))
        for k in range(1, 4):
            y = y0 + k * (y1 - y0) / 4
            box(acc, (x1 - 0.0, y - 0.006, z0 + 0.1), (x1 + 0.006, y + 0.006, z1 - 0.1), "paint", C_DARK, uv_box(1.0))
        # heat pump on the terrace
        (x0, y0, z0), (x1, y1, z1) = P["W_HEATPUMP"]
        box(acc, (x0, y0, z0), (x1, y1, z1), "paint", C_HEATPUMP, uv_box(1.0))
        cx, cz = x0 + 0.62, (z0 + z1) / 2
        ring = [V((cx + 0.42 * math.cos(math.radians(a)), y0 - 0.001, cz + 0.42 * math.sin(math.radians(a))))
                for a in range(0, 360, 20)]
        acc.poly(ring, "trim", uv_trim("vent_louvre", 0, 2, cz - 0.42, 0.84), WHITE, want=(0, -1, 0))
        box(acc, (x1 - 0.55, y0 - 0.012, z0 + 0.2), (x1 - 0.12, y0, z1 - 0.2), "trim", WHITE,
            trim_box_uv("vent_louvre", 0), skip=((1, 1),))
        # garage e-car: a boxy city pod filling its 1.5 m box (skirts to the floor, glass flush)
        self.car(acc, P["W_GARAGE_CAR"])

    def car(self, acc, bb):
        (x0, y0, z0), (x1, y1, z1) = bb
        body = self.T["car"]
        zb = 0.82
        r = 0.08
        # lower body (rounded vertical edges via chamfer)
        def chamfer_box(xa, ya, za, xb, yb, zbb, c, mat, col):
            ring = [(xa + c, ya), (xb - c, ya), (xb, ya + c), (xb, yb - c), (xb - c, yb), (xa + c, yb), (xa, yb - c),
                    (xa, ya + c)]
            prism(acc, (2, 1, 0.0), ring, za, zbb, mat, col, uv_box(1.5), sides=True)
        chamfer_box(x0, y0, 0.06, x1, y1, zb, r, "paint", body)
        chamfer_box(x0 + 0.004, y0 + 0.004, 0.0, x1 - 0.004, y1 - 0.004, 0.06, r, "paint", C_TYRE)
        # cabin: glass band + roof (full footprint, top = collision top)
        chamfer_box(x0, y0, zb, x1, y1, z1 - 0.1, r, "glass", C_GLASS)
        chamfer_box(x0, y0, z1 - 0.1, x1, y1, z1, r, "paint", body)
        # pillars over the glass (paint strips flush)
        for yy in (y0 + 0.9, (y0 + y1) / 2, y1 - 0.9):
            for xf, s in ((x0, -1), (x1, 1)):
                box(acc, (xf - (0.006 if s < 0 else 0), yy - 0.06, zb), (xf + (0.006 if s > 0 else 0), yy + 0.06,
                    z1 - 0.1), "paint", body, uv_box(1.0))
        # wheels: dark discs flush with the sides, light hubs
        for yy in (y0 + 0.75, y1 - 0.75):
            for xf, s in ((x0, -1), (x1, 1)):
                for rad, col, dd in ((0.33, C_TYRE, 0.008), (0.17, C_STEEL, 0.012)):
                    pts = [V((xf + s * dd, yy + rad * math.cos(math.radians(a)), 0.34 + rad * math.sin(math.radians(a))))
                           for a in range(0, 360, 20)]
                    acc.poly(pts, "paint", uv_box(1.0), col, want=(s, 0, 0))
        # lights
        for yf, s, col in ((y0, -1, srgb(200, 40, 36)), (y1, 1, srgb(250, 244, 226))):
            for xc in (x0 + 0.28, x1 - 0.28):
                box(acc, (xc - 0.16, yf - (0.008 if s < 0 else 0), 0.62), (xc + 0.16, yf + (0.008 if s > 0 else 0),
                    0.72), "lamp" if s > 0 else "paint", col, uv_box(1.0))

    # ----------------------------------------------------------------------------------- build
    def build(self):
        self.corners()
        self.generic_faces()
        self.facades()
        self.parapets()
        self.flat_roof_finish()
        self.roof()
        self.downpipes()
        self.entrance()
        self.stair()
        self.skirting_boards()
        self.decor()
        self.props()
        return self.acc


# ============================================================================================ objects + export
def make_object(name, acc, mats, coll):
    verts, faces, mi, uvl, cl, nl = [], [], [], [], [], []
    names = sorted({p[1] for p in acc.P})
    for pts, mat, uvs, cols, nrm in acc.P:
        base = len(verts)
        verts += [tuple(p) for p in pts]
        faces.append(tuple(range(base, base + len(pts))))
        mi.append(names.index(mat))
        for u in uvs:
            uvl += [u[0], u[1]]
        for c in cols:
            cl += list(c)
        if nrm:
            for q in nrm:
                nl.append(tuple(q))
        else:
            n = newell(pts).normalized()
            nl += [tuple(n)] * len(pts)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("material_index", mi)
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", uvl)
    ca = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    ca.data.foreach_set("color", cl)
    me.color_attributes.active_color = ca
    me.polygons.foreach_set("use_smooth", [True] * len(faces))
    me.normals_split_custom_set(nl)
    me.update()
    for m in names:
        me.materials.append(mats[m])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


PARTS = {"shell": "Shell", "clad": "Cladding", "trim": "Trim", "roof": "Roof", "solar": "Solar",
         "interior": "Interior", "props": "Props", "doors": "Doors"}


def build_all():
    check_mirror()
    bc.reset_scene()
    derive_textures()
    glass_streaks()
    mats = materials()
    objs = []
    for side in ("W", "E"):
        team = TEAMS[side]
        log("building", team["name"])
        h = House(team)
        accs = h.build()
        col = bc.collection(f"SH_{team['name']}_HOUSE")
        for k, a in accs.items():
            if side == "E":
                a = a.mirrored(36.0)
            if not a.P:
                continue
            # Separate mesh per material is explicit in the source .blend and in glTF, rather than leaving
            # a mixed-material mesh for the engine to split. All vertices stay in design coordinates.
            for mk in sorted({p[1] for p in a.P}):
                aa = Acc(); aa.P = [p for p in a.P if p[1] == mk]
                ob = make_object(f"SH_{team['name']}_{PARTS[k]}_{mk}", aa, mats, col)
                ob["kit"] = "showhome_houses"
                ob["part"] = k
                ob["material_family"] = mk
                ob["team"] = "A" if side == "W" else "B"
                objs.append(ob)
                log(f"  {ob.name}: {aa.tris()} tris")
    counts = {team: sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs
                        if o.name.startswith("SH_" + team + "_")) for team in ("SAGE", "CLAY")}
    json.dump({"triangles": counts, "materials": sorted({m.name for o in objs for m in o.data.materials}),
               "panel": {"width_m": 1.2, "height_m": 2.4, "joint_width_m": 0.014,
                         "joint_depth_m": 0.009, "bevel_m": 0.0018},
               "roof": {"course_m": 0.25, "butt_m": 0.010, "solar_proud_m": 0.0195},
               "frame": "design x east, y north, z up; glTF x,z,-y at identity"},
              open(KIT + "/houses_stats.json", "w"), indent=2)
    return objs, mats


def export(objs):
    os.makedirs(KIT, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    glb = KIT + "/houses.glb"
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_tangents=True, export_vertex_color="ACTIVE",
                              export_normals=True, export_extras=True)
    log("exported", glb)
    blend = KIT + "/houses.blend"
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True, relative_remap=False)
    log("saved", blend)


# ============================================================================================ rendering
def aim(ob, loc, tgt):
    ob.location = loc
    ob.rotation_euler = (V(tgt) - V(loc)).to_track_quat("-Z", "Y").to_euler()


def sun_dir(so, el, az):
    e, a = math.radians(el), math.radians(az)
    d = V((math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def setup_render(quick):
    """Concept-like light: low warm late-afternoon sun, peach horizon -> blue zenith sky gradient, AgX."""
    sc = bpy.context.scene
    w = bpy.data.worlds.new("_Sky")
    w.use_nodes = True
    nt = w.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    zup = nt.nodes.new("ShaderNodeMath"); zup.operation = "MULTIPLY"; zup.inputs[1].default_value = -1.0
    nt.links.new(tc.outputs["Normal"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], zup.inputs[0])
    nt.links.new(zup.outputs[0], ramp.inputs[0])
    nt.links.new(ramp.outputs["Color"], bg.inputs[0])
    el = ramp.color_ramp.elements
    el[0].position, el[0].color = 0.0, (0.86, 0.72, 0.60, 1)
    el[1].position, el[1].color = 0.42, (0.46, 0.56, 0.80, 1)
    e2 = el.new(0.12)
    e2.color = (0.74, 0.70, 0.74, 1)
    bg.inputs[1].default_value = 0.65
    sky_path = SH + "/backdrop/sky/sky_equirect.png"
    if os.path.exists(sky_path):
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = _img(sky_path)
        nt.links.new(env.outputs["Color"], bg.inputs[0])
    sc.world = w
    sd = bpy.data.lights.new("_Sun", "SUN")
    sd.energy = 2.5
    sd.color = (1.0, 0.84, 0.66)
    sd.angle = math.radians(1.5)
    so = bpy.data.objects.new("_Sun", sd)
    sc.collection.objects.link(so)
    bc._set_engine(sc)
    try:
        sc.eevee.taa_render_samples = 16 if quick else 48
    except Exception:
        pass
    for attr, val in (("use_shadows", True), ("use_raytracing", True), ("use_fast_gi", True),
                      ("shadow_ray_count", 2), ("shadow_step_count", 8)):
        try:
            setattr(sc.eevee, attr, val)
        except Exception:
            pass
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium Low Contrast"
    except Exception:
        pass
    sc.render.image_settings.file_format = "PNG"
    cd = bpy.data.cameras.new("_Cam")
    cam = bpy.data.objects.new("_Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cd.clip_start, cd.clip_end = 0.05, 1500
    return cam, so


def ground_plane():
    """A lawn ground for house-only renders (the ground kit is built elsewhere), flush at z 0."""
    me = bpy.data.meshes.new("_Ground")
    me.from_pydata([(-60, -60, -0.002), (132, -60, -0.002), (132, 108, -0.002), (-60, 108, -0.002)], [],
                   [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", [-30, -30, 66, -30, 66, 54, -30, 54])
    ob = bpy.data.objects.new("_Ground", me)
    bpy.context.scene.collection.objects.link(ob)
    m = bc.material("_GroundMat", (1, 1, 1), rough=0.9)
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    ti = nt.nodes.new("ShaderNodeTexImage")
    ti.image = _img(os.path.join(V2 if os.path.exists(os.path.join(V2, "grass_lawn.png")) else TEX, "grass_lawn.png"))
    nt.links.new(ti.outputs["Color"], bsdf.inputs["Base Color"])
    ob.data.materials.append(m)
    return ob


def context_objects():
    """Prefer the real ground and props GLBs. The older collision preview remains an explicit fallback."""
    ground = KIT + "/ground.glb"
    props = KIT + ("/props_placed.glb" if os.path.exists(KIT + "/props_placed.glb") else "/props_placed_partial.glb")
    if os.path.exists(ground) and os.path.exists(props):
        out = []
        for path in (ground, props):
            before = set(bpy.data.objects)
            bpy.ops.import_scene.gltf(filepath=path)
            out.extend(o for o in bpy.data.objects if o not in before and o.type == "MESH")
        log("look-dev context uses real ground and props GLBs")
        return out
    path = LAYOUT + "/showhome_collision_preview.blend"
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("COL_") and "_HOUSE__" not in n
                       and "_HOUSE_PROPS__" not in n]
    out = []
    coll = bc.collection("_Context")
    for ob in dst.objects:
        if ob is None:
            continue
        if ob.get("kind") == "PlayerClip" or ob.get("look") == "Invisible":
            continue
        if ob.get("tag_id") in ("GROUND",) and ob.get("part") == "building_floor":
            continue
        coll.objects.link(ob)
        out.append(ob)
    # soften the placeholder colours toward the concept palette
    tone = {"Ground": srgb(118, 132, 76), "TeamA": srgb(150, 162, 140), "TeamB": srgb(176, 150, 136),
            "Hedge": srgb(86, 104, 48), "Fence": srgb(226, 219, 205), "Vehicle": srgb(231, 223, 218),
            "Wall": srgb(214, 200, 176), "Roof": srgb(80, 76, 78), "Floor": srgb(175, 162, 154),
            "Prop": srgb(190, 150, 110), "Metal": srgb(110, 112, 118), "Trim": srgb(214, 200, 176)}
    for ob in out:
        lk = ob.get("look")
        if lk in tone:
            m = bc.material("_CTX_" + lk, tone[lk], rough=0.85)
            ob.data.materials.clear()
            ob.data.materials.append(m)
    return out


def render_set(objs, quick, views):
    cam, sun = setup_render(quick)
    sc = bpy.context.scene
    os.makedirs(RENDERS, exist_ok=True)
    res = (1280, 720) if quick else (1600, 900)
    out = []

    def shot(name, loc, tgt, lens, el=30, az=None, hide=(), res_=None):
        if views and name not in views:
            return
        aim(cam, loc, tgt)
        cam.data.lens = lens
        if az is None:
            d = V(loc) - V(tgt)
            az = math.degrees(math.atan2(d.y, d.x)) + 55
        sun_dir(sun, 54, 188)
        for o in hide:
            o.hide_render = True
        sc.render.resolution_x, sc.render.resolution_y = res_ or res
        p = f"{RENDERS}/houses_{name}.png"
        sc.render.filepath = p
        try:
            bpy.ops.render.render(write_still=True)
        except RuntimeError as e:
            log("render failed, CPU Cycles fallback:", e)
            bc._set_engine(sc, ("CYCLES",))
            sc.cycles.device = "CPU"
            sc.cycles.samples = 32
            bpy.ops.render.render(write_still=True)
            bc._set_engine(sc)
        for o in hide:
            o.hide_render = False
        out.append(p)
        log("rendered", p)

    gp = ground_plane()
    byname = {o.name: o for o in objs}
    for tn, cx in (("SAGE", 15.0), ("CLAY", 57.0)):
        mine = [o for o in objs if o.name.startswith(f"SH_{tn}_")]
        other = [o for o in objs if o not in mine]
        sgn = 1 if tn == "SAGE" else -1          # street direction (+x for Sage)
        xs = cx + sgn * 6.15                      # street facade plane
        c = (cx, 24.0, 4.2)
        lo = tn.lower()
        for o in other:
            o.hide_render = True
        # sun from the street side / south so the facades the camera sees are lit, like the concept
        saz = -40 if tn == "SAGE" else 220
        shot(f"{lo}_street", (cx + sgn * 24, 14.0, 4.5), c, 24, el=24, az=saz)
        shot(f"{lo}_south", (cx + sgn * 6, -4.0, 7.0), c, 24, el=26, az=-70 if tn == "SAGE" else 250)
        shot(f"{lo}_yard", (cx - sgn * 24, 32.0, 4.0), c, 24, el=26, az=150 if tn == "SAGE" else 30)
        shot(f"{lo}_north", (cx - sgn * 6, 52.0, 6.0), c, 24, el=24, az=110 if tn == "SAGE" else 70)
        shot(f"{lo}_aerial", (cx + sgn * 18, -1.0, 21.0), (cx, 24.0, 3.0), 26, el=26, az=saz)
        cut = [o for o in mine if o.get("part") in ("roof", "solar", "trim")]
        shot(f"{lo}_cutaway", (cx + sgn * 12, 6.0, 20.0), (cx, 24.0, 1.0), 26, hide=cut, el=65, az=saz)
        # close-ups: printed podium corner, terrace + balustrade, street windows, player eye at a window
        shot(f"{lo}_close_corner", (xs + sgn * 3.2, 13.6, 1.7), (xs - sgn * 0.2, 16.6, 1.9), 30, el=22,
             az=-30 if tn == "SAGE" else 210)
        shot(f"{lo}_close_terrace", (cx + sgn * 2.5, 21.2, 5.0), (cx + sgn * 4.0, 16.4, 3.6), 22, el=30,
             az=-60 if tn == "SAGE" else 240)
        shot(f"{lo}_close_windows", (xs + sgn * 6.0, 27.0, 3.0), (xs, 27.0, 3.4), 30, el=24,
             az=-20 if tn == "SAGE" else 200)
        shot(f"{lo}_eye_window", (xs + sgn * 4.0, 29.8, 1.65), (xs - sgn * 3.0, 29.8, 1.5), 24, el=24,
             az=-20 if tn == "SAGE" else 200)
        shot(f"{lo}_eye_inside", (cx + sgn * 1.2, 26.4, 4.85), (xs + sgn * 8.0, 23.8, 4.4), 20, el=24,
             az=-20 if tn == "SAGE" else 200)
        shot(f"{lo}_close_roof", (xs + sgn * 4.5, 18.2, 9.2), (xs - sgn * 1.5, 23.0, 7.6), 26, el=26,
             az=-40 if tn == "SAGE" else 220)
        shot(f"{lo}_wall_1m", (xs + sgn * 1.0, 26.95, 4.65), (xs, 27.55, 4.65), 32,
             res_=(1280, 1280))
        shot(f"{lo}_wall_5m", (xs + sgn * 5.0, 27.55, 4.65), (xs, 27.55, 4.65), 32,
             res_=(1280, 1280))
        shot(f"{lo}_sunlit_wall_1m", (cx - sgn * 0.45, G["yms"] - 1.0, 5.25),
             (cx - sgn * 0.45, G["yms"], 5.3), 32, res_=(1280, 1280))
        shot(f"{lo}_sunlit_wall_5m", (cx - sgn * 0.45, G["yms"] - 5.0, 4.85),
             (cx - sgn * 0.45, G["yms"], 4.9), 32, res_=(1280, 1280))
        shot(f"{lo}_roof_upper_window", (cx + sgn * 3.2, 21.0, 4.85), (cx, 25.0, 9.4), 25)
        shot(f"{lo}_roof_terrace", (cx + sgn * 1.5, 18.0, 4.8), (cx, 24.0, 8.2), 30)
        shot(f"{lo}_interior_uf", (xs - sgn * 0.7, 23.0, 4.85), (cx + sgn * 0.1, 28.6, 4.2), 18, el=24,
             az=-20 if tn == "SAGE" else 200)
        shot(f"{lo}_interior_gf", (xs - sgn * 0.6, 26.0, 1.65), (cx - sgn * 4.0, 27.5, 1.2), 18, el=24,
             az=-20 if tn == "SAGE" else 200)
        for o in other:
            o.hide_render = False
    # concept comparisons with the rest of the map as collision context
    gp.hide_render = True
    ctx = context_objects()
    shot("concept_aerial_s11", (36.0, -26.0, 40.0), (36.0, 25.0, 0.0), 30, el=28, az=235)
    shot("concept_aerial_s12", (4.0, -16.0, 30.0), (40.0, 28.0, 0.0), 28, el=28, az=235)
    shot("concept_ground_street", (36.0, 10.8, 1.75), (36.0, 30.0, 3.4), 15, el=26, az=250)
    shot("concept_ground_sage", (32.2, 19.6, 1.75), (21.0, 26.0, 4.3), 18, el=24, az=-25)
    shot("concept_ground_clay", (39.8, 19.6, 1.75), (51.0, 26.0, 4.3), 18, el=24, az=205)
    del ctx
    return out


def compare_sheets():
    """Concept | render sheets via the system python (PIL)."""
    code = r'''
import os, sys
from PIL import Image, ImageDraw, ImageFont
R, C = sys.argv[1], sys.argv[2]
pairs = [("A_showhome_aerial_s11.png", "houses_concept_aerial_s11.png"),
         ("A_showhome_aerial_s12.png", "houses_concept_aerial_s12.png"),
         ("A_showhome_ground_s11.png", "houses_concept_ground_sage.png"),
         ("A_showhome_ground_s12.png", "houses_concept_ground_clay.png"),
         ("A_showhome_ground_s11.png", "houses_concept_ground_street.png")]
W = 960
try:
    f = ImageFont.truetype("arial.ttf", 20)
except OSError:
    f = ImageFont.load_default()
for name, sel in (("aerial", pairs[:2]), ("ground", pairs[2:4]), ("street", pairs[4:])):
    tiles = []
    for c, r in sel:
        pc, pr = os.path.join(C, c), os.path.join(R, r)
        if not (os.path.exists(pc) and os.path.exists(pr)):
            continue
        a = Image.open(pc).convert("RGB"); b = Image.open(pr).convert("RGB")
        a = a.resize((W, int(a.height * W / a.width))); b = b.resize((W, int(b.height * W / b.width)))
        tiles.append((a, c, b, r))
    if not tiles:
        continue
    h = sum(max(a.height, b.height) + 34 for a, _, b, _ in tiles)
    sheet = Image.new("RGB", (2 * W + 10, h), (24, 24, 28)); d = ImageDraw.Draw(sheet); y = 0
    for a, cn, b, rn in tiles:
        d.text((8, y + 6), "CONCEPT  " + cn, fill=(235, 235, 235), font=f)
        d.text((W + 18, y + 6), "HOUSE KIT (rest = collision)  " + rn, fill=(235, 235, 235), font=f)
        sheet.paste(a, (0, y + 34)); sheet.paste(b, (W + 10, y + 34)); y += max(a.height, b.height) + 34
    p = os.path.join(R, "houses_compare_%s.png" % name); sheet.save(p); print("wrote", p)
'''
    try:
        r = subprocess.run(["python", "-c", code, RENDERS, CONCEPTS], capture_output=True, text=True, timeout=120)
        log(r.stdout.strip(), r.stderr.strip()[-400:])
    except Exception as e:  # noqa: BLE001
        log("compare sheet skipped:", e)


def main():
    a = args()
    objs, mats = build_all()
    tot = 0
    for o in objs:
        tot += sum(len(p.vertices) - 2 for p in o.data.polygons)
    log(f"total {tot} tris in {len(objs)} objects")
    export(objs)
    if a["render"]:
        render_set(objs, a["quick"], a["views"])
        compare_sheets()
        subprocess.run(["python", SH + "/compare_houses_v2.py"], check=True)
    log("done")


main()
