"""Showhome GROUND + BOUNDARIES kit: every flat or low surface that defines the space, plus the boundary walls,
fences, hedges and the big brush-matched props (Mover truck, kerb pods, picket fences, hedges, arbours, pylons).

Run (headless Blender 5.2, re-runnable from scratch):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/maps/showhome/build_ground.py" -- [--no-render] [--no-check] [--quick]
      [--views top,aerial_s11,...]

Everything is generated from the game's collision layout (layout/showhome_annotated.json via layout_lib):
  * The ground is ONE flat plane in collision (top z 0). The art is a partition of non-overlapping rectangles
    (a priority list of zones -> a cell grid -> merged rects), so no two ground surfaces overlap. Surfaces sit
    0..16 mm above z 0. Real chamfered kerbs rise to 110 mm, dropped kerbs to 16 mm and low edging to 28 mm.
    Every unit over 20 mm is handed off in ground_steps.json; the game's base layout is not modified here.
    Ground COLOR_0 is linear RGBA wear/spill data, interpreted by the documented height blend.
  * Fences, hedges, walls, planters and beds fill their collision boxes; decoration stays inside the box or
    within 2 cm of it.
  * The west half (Sage, team A) is built and mirrored about x = 36 for the east half (Clay, team B); team
    accents swap (teal -> coral, sage cladding -> clay cladding).
  * Outside the playable rect (x 0..72, y 0..48) a ground skirt runs out to x -80..152, y -60..110 (ring roads,
    pavements, finished lots to the south, sand construction plots to the west / north / east), and a flat far
    plane to +-2 km, so no edge of the world is visible from inside (up to the 10 m hard ceiling).
  * The brush-matched props come from build_props.py (executed as a library, its main() is not run), placed with
    its own placements() at their brushes.

Frames: design / Blender = metres, x east, y north, z up (origin = SW map corner). The glTF is exported +Y up,
which is exactly the game's frame: bevy = (x, z, -y). Load kit/ground.glb at Transform::IDENTITY.

Writes
  kit/ground.glb, kit/ground.blend            the kit (objects GND_* and PROP_*__<anchor>)
  kit/ground_placements.json                  the placed props (design + Bevy transforms)
  kit/ground_alignment.json (+ _summary.json) check_alignment.py on ground.glb, filtered to this kit's brushes
  kit/tex/ground/*.png                        decal textures (ground_textures.py)
  kit/renders/ground/*.png                    top / concept aerials / street level / edge checks + compare sheets
"""
import json
import math
import os
import re
import subprocess
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Vector, noise
from mathutils.geometry import tessellate_polygon

ROOT = r"F:/git/val etf"
SH = ROOT + "/assets/maps/showhome"
LAYOUT_DIR = SH + "/layout"
TEX = SH + "/textures"
KIT = SH + "/kit"
GTEX = KIT + "/tex/ground"
RENDERS = KIT + "/renders/ground"
CONCEPTS = ROOT + "/design/maps/tdm/concepts/_candidates"
BLENDER = r"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
for _p in (ROOT + "/tools", LAYOUT_DIR, SH):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import layout_lib as LL  # noqa: E402
import props_lib as PL  # noqa: E402
import blender_common as bc  # noqa: E402
import ground_edges as GE  # noqa: E402

V = Vector
L = LL.load()
T0 = time.time()
AXIS = 36.0          # mirror axis
EPS = 1e-6


def log(*a):
    print(f"[ground {time.time() - T0:6.1f}s]", *a, flush=True)


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    views = None
    if "--views" in a:
        views = a[a.index("--views") + 1].split(",")
    return dict(render="--no-render" not in a, check="--no-check" not in a, quick="--quick" in a, views=views)


# ============================================================================================ materials
SAGE_PAINT = PL.lin((46, 150, 136))       # teal accent paint (team A), muted for a painted surface
CLAY_PAINT = PL.lin((222, 112, 86))       # coral accent paint (team B)
SAGE_TINT = (0.405, 0.454, 0.241)          # README tint for the neutral 0.70 fibre-cement board
CLAY_TINT = (0.892, 0.340, 0.165)


def materials():
    t = lambda n: os.path.join(TEX, 'v2', n) if os.path.exists(os.path.join(TEX,'v2',n)) else os.path.join(TEX,n)
    g = lambda n: os.path.join(GTEX, n)  # noqa: E731
    PL.spec("M_GND_Asphalt", tex=t("asphalt.png"), repeat=4.0, rough=0.85)
    PL.spec("M_GND_AsphaltOld", tex=t("asphalt_cracked.png"), repeat=4.0, rough=0.85)
    PL.spec("M_GND_Paving", tex=t("paving_slabs.png"), normal=t("paving_slabs_normal.png"), repeat=2.4, rough=0.8)
    PL.spec("M_GND_PavingSage", tex=t("paving_slabs.png"), normal=t("paving_slabs_normal.png"), repeat=2.4,
            rough=0.8, tint=(0.86, 0.98, 0.95))
    PL.spec("M_GND_PavingClay", tex=t("paving_slabs.png"), normal=t("paving_slabs_normal.png"), repeat=2.4,
            rough=0.8, tint=(1.0, 0.90, 0.86))
    PL.spec("M_GND_Kerb", tex=t("kerb_concrete.png"), repeat=2.0, rough=0.8)
    PL.spec("M_GND_Edging", tex=t("edging_strip.png"), normal=t("edging_strip_normal.png"),repeat=2,rough=.8,vc=False)
    PL.spec("M_GND_SteelEdging", tex=t("metal_scaffold_tube.png"),repeat=1,rough=.6,metal=.8,vc=False)
    PL.spec("M_GND_Mulch",tex=t("bark_mulch.png"),normal=t("bark_mulch_normal.png"),repeat=1,rough=.96)
    PL.spec("M_GND_Grass", tex=t("grass_lawn.png"), repeat=2.0, rough=0.9)
    PL.spec("M_GND_GrassFar", tex=t("grass_lawn.png"), repeat=5.0, rough=0.92, tint=(0.80, 0.80, 0.70))
    PL.spec("M_GND_Soil", tex=t("garden_soil.png"), repeat=1.0, rough=0.95)
    PL.spec("M_GND_SoilFar", tex=t("garden_soil.png"), repeat=3.0, rough=0.95, tint=(1.15, 1.1, 1.05))
    PL.spec("M_GND_Gravel", tex=t("gravel.png"), repeat=1.0, rough=0.9)
    PL.spec("M_GND_Sand", tex=t("construction_sand.png"), repeat=6.0, rough=0.95)
    PL.spec("M_GND_Concrete", tex=t("concrete_smooth.png"), repeat=2.0, rough=0.8)
    PL.spec("M_GND_LineWhite", color=(0.78, 0.76, 0.72), rough=0.6, vc=True)
    PL.spec("M_GND_LineYellow", color=(0.80, 0.52, 0.10), rough=0.6, vc=True)
    PL.spec("M_GND_PaintSage",tex=t('fibercement_panel.png'),repeat=2.4,tint=tuple(c/.7 for c in SAGE_PAINT),rough=.55,vc=False)
    PL.spec("M_GND_PaintClay",tex=t('fibercement_panel.png'),repeat=2.4,tint=tuple(c/.7 for c in CLAY_PAINT),rough=.55,vc=False)
    PL.spec("M_GND_Manhole", tex=g("manhole.png"), uv="face01", rough=0.55, metal=0.3, ao=False)
    PL.spec("M_GND_Gully", tex=g("gully.png"), uv="face01", rough=0.55, metal=0.3, ao=False)
    PL.spec("M_GND_Inspection", tex=g("inspection.png"), uv="face01", rough=0.5, metal=0.2, ao=False)
    # walls / fences / planters
    PL.spec("M_GND_WallPrinted", tex=t("printed_concrete_layers.png"), normal=t("printed_concrete_layers_normal.png"),
            repeat=1.28, rough=0.8)
    PL.spec("M_GND_Pilaster", tex=t("concrete_smooth.png"), repeat=2.0, rough=0.75, tint=(1.06, 1.04, 0.98))
    PL.spec("M_GND_Plinth", tex=t("concrete_smooth.png"), repeat=2.0, rough=0.85, tint=(0.62, 0.60, 0.58))
    PL.spec("M_GND_Coping", tex=t("concrete_smooth.png"), repeat=2.0, rough=0.6, tint=(1.12, 1.10, 1.04))
    PL.spec("M_GND_CladSage", tex=t("fibercement_sage.png"), repeat=4.8, offset=(0.0604, -1.0), rough=0.65)
    PL.spec("M_GND_CladClay", tex=t("fibercement_clay.png"), repeat=4.8, offset=(0.0604, -1.0), rough=0.65)
    PL.spec("M_GND_TimberDark", tex=t("wood_boards_stained.png"), repeat=2.0, rough=0.8, tint=(0.62, 0.60, 0.58))
    PL.spec("M_GND_FloorPlaceholder", tex=t("concrete_smooth.png"), repeat=2.0, rough=0.7, tint=(0.92, 0.92, 0.92))
    # All v2 tiling materials export ordinary PBR maps; masks are interpreted by the game ground shader.
    for name,spec in PL._SPECS.items():
        path=spec.get('tex')
        if name.startswith('M_GND_') and path and '/v2/' in path.replace('\\','/'):
            stem=os.path.splitext(path)[0]
            if os.path.exists(stem+'_normal.png'):spec['normal']=stem+'_normal.png'
            if os.path.exists(stem+'_orm.png'):spec['orm']=stem+'_orm.png'


# ============================================================================================ surfaces
# kind -> material, top z, uv mapping (mode, metres per repeat), merge bucket (x, y) in metres, colour model
SURF = {
    "road": dict(mat="M_GND_Asphalt", z=0.000, uv=("xy", 4.0), b=(4.0, 4.0), cm="asphalt"),
    "lane": dict(mat="M_GND_AsphaltOld", z=0.000, uv=("xy", 4.0), b=(4.0, 4.0), cm="asphalt"),
    "pave": dict(mat="M_GND_Paving", z=0.010, uv=("pave", 2.4), b=(4.0, 4.0), cm="pave"),
    "pave_A": dict(mat="M_GND_PavingSage", z=0.010, uv=("pave", 2.4), b=(4.0, 4.0), cm="pave"),
    "band_A": dict(mat="M_GND_PaintSage", z=0.010, uv=("xy", 1.0), b=(4.0, 4.0), cm="paint"),
    "kerb_ns": dict(mat="M_GND_Kerb", z=0.014, uv=("along_y", 2.0), b=(4.0, 4.0), cm="kerb"),
    "kerb_ew": dict(mat="M_GND_Kerb", z=0.014, uv=("xy", 2.0), b=(4.0, 4.0), cm="kerb"),
    "edge_ns": dict(mat="M_GND_Kerb", z=0.012, uv=("along_y", 2.0), b=(4.0, 4.0), cm="kerb"),
    "edge_ew": dict(mat="M_GND_Kerb", z=0.012, uv=("xy", 2.0), b=(4.0, 4.0), cm="kerb"),
    "lawn": dict(mat="M_GND_Grass", z=0.006, uv=("xy", 2.0), b=(2.5, 2.5), cm="grass"),
    "lawn_ns": dict(mat="M_GND_Grass", z=0.006, uv=("xy", 2.0), b=(1.25, 2.5), cm="stripes_x"),
    "lawn_ew": dict(mat="M_GND_Grass", z=0.006, uv=("xy", 2.0), b=(2.5, 1.25), cm="stripes_y"),
    "verge": dict(mat="M_GND_Grass", z=0.006, uv=("xy", 2.0), b=(4.0, 4.0), cm="grass"),
    "grass": dict(mat="M_GND_Grass", z=0.006, uv=("xy", 2.0), b=(4.0, 4.0), cm="grass_far"),
    "soil": dict(mat="M_GND_Soil", z=0.003, uv=("xy", 1.0), b=(2.5, 2.5), cm="soil"),
    "mulch": dict(mat="M_GND_Mulch",z=.004,uv=("xy",1.),b=(2.5,2.5),cm="soil"),
    "gravel": dict(mat="M_GND_Gravel", z=0.004, uv=("xy", 1.0), b=(4.0, 4.0), cm="gravel"),
    "conc": dict(mat="M_GND_Concrete", z=0.008, uv=("xy", 2.0), b=(4.0, 4.0), cm="conc"),
    "sand": dict(mat="M_GND_Sand", z=0.000, uv=("xy", 6.0), b=(4.0, 4.0), cm="sand", mound=True),
    "earth": dict(mat="M_GND_SoilFar", z=0.000, uv=("xy", 3.0), b=(4.0, 4.0), cm="sand", mound=True),
    "none": None,
}
KINDS = list(SURF)
TEAM_SWAP = {"M_GND_PavingSage": "M_GND_PavingClay", "M_GND_PaintSage": "M_GND_PaintClay",
             "M_GND_CladSage": "M_GND_CladClay"}
# textures without alignment needs get world UVs again after mirroring (no Rorschach seam on the axis)
WORLD_UV = {"M_GND_Asphalt": 4.0, "M_GND_AsphaltOld": 4.0, "M_GND_Grass": 2.0, "M_GND_GrassFar": 5.0,
            "M_GND_Soil": 1.0, "M_GND_SoilFar": 3.0, "M_GND_Gravel": 1.0, "M_GND_Sand": 6.0,
            "M_GND_Concrete": 2.0}
PAVE_O = (27.35, 24.9)     # paving joints (0.6 m slabs, joints at origin + 0.3 + 0.6k) on the sidewalk edge x 27.65
#                            and the front-path edge y 25.2; the mirror keeps them aligned on the east side


def uv_of(S, x, y):
    mode, rep = S["uv"]
    if mode == "pave":
        return ((x - PAVE_O[0]) / rep, (y - PAVE_O[1]) / rep)
    if mode == "along_y":
        return (y / rep, x / rep)
    return (x / rep, y / rep)


def nz(x, y, f, s):
    return noise.noise(V((x * f + s * 17.31, y * f + s * 5.13, s * 3.71)))


# contact darkening near tall collision (walls, hedges, fences, props) - 2D footprints
TALL = np.array([[b["min"][0], b["min"][1], b["max"][0], b["max"][1]] for b in L.visible()
                 if b["kind"] == "Solid" and b["min"][2] < 0.05 and b["max"][2] >= 0.9
                 and b["look"] not in ("Ground", "TeamA", "TeamB", "Floor")])
_AO = {}


def contact_ao(x, y):
    if not (-3.0 < x < 75.0 and -3.0 < y < 51.0):
        return 1.0
    k = (round(x, 3), round(y, 3))
    v = _AO.get(k)
    if v is None:
        dx = np.maximum(np.maximum(TALL[:, 0] - x, x - TALL[:, 2]), 0.0)
        dy = np.maximum(np.maximum(TALL[:, 1] - y, y - TALL[:, 3]), 0.0)
        d = float(np.min(np.hypot(dx, dy)))
        t = min(1.0, d / 0.9)
        v = 0.80 + 0.20 * t * t * (3 - 2 * t)
        _AO[k] = v
    return v


def colour(kind, x, y, cx, cy):
    cm = SURF[kind]["cm"]
    if cm == "asphalt":
        v = 0.95 + 0.06 * nz(x, y, 0.07, 1) + 0.03 * nz(x, y, 0.35, 2)
    elif cm == "pave":
        v = 0.97 + 0.05 * nz(x, y, 0.11, 3)
    elif cm in ("grass", "stripes_x", "stripes_y"):
        v = 0.95 + 0.07 * nz(x, y, 0.09, 4) + 0.03 * nz(x, y, 0.45, 5)
        if cm == "stripes_x":
            v *= 1.0 if math.floor(cx / 1.25) % 2 == 0 else 0.88
        elif cm == "stripes_y":
            v *= 1.0 if math.floor(cy / 1.25) % 2 == 0 else 0.88
    elif cm == "grass_far":
        v = 0.90 + 0.10 * nz(x, y, 0.03, 6) + 0.04 * nz(x, y, 0.2, 7)
    elif cm == "soil":
        v = 0.95 + 0.07 * nz(x, y, 0.2, 8)
    elif cm == "sand":
        v = 0.93 + 0.09 * nz(x, y, 0.035, 9) + 0.05 * nz(x, y, 0.16, 10)
    elif cm == "kerb":
        v = 0.97 + 0.04 * nz(x, y, 0.3, 11)
    elif cm == "paint":
        v = 0.95 + 0.06 * nz(x, y, 0.8, 12)
    else:
        v = 0.96 + 0.05 * nz(x, y, 0.15, 13)
    v *= contact_ao(x, y)
    return (v, v, v)


# ---------------------------------------------------------------------------- mounds on the construction plots
MOUNDS = []


def make_mounds():
    """Low earth mounds inside the sand plots (well away from every plot edge, so the edges stay at z 0)."""
    import random
    r = random.Random(23)
    plots = [(-80, 18, -50, 40), (-46.5, 18, -13.1, 40), (-80, 43.5, -50, 110), (-46.5, 43.5, -13.1, 110),
             (-13.1, 61.1, 8, 84), (11.5, 61.1, 36, 84), (-13.1, 87.5, 8, 110), (11.5, 87.5, 36, 110)]
    for (x0, y0, x1, y1) in plots:
        n = max(1, int((x1 - x0) * (y1 - y0) / 260))
        for _ in range(n):
            rad = r.uniform(4.5, 8.0)
            m = 1.7 * rad
            if x1 - x0 < 2 * m + 1 or y1 - y0 < 2 * m + 1:
                continue
            MOUNDS.append((r.uniform(x0 + m, x1 - m), r.uniform(y0 + m, y1 - m), rad, r.uniform(0.6, 1.9)))


def mound(x, y):
    h = 0.0
    for (cx, cy, rad, hh) in MOUNDS:
        d2 = ((x - cx) ** 2 + (y - cy) ** 2) / (rad * rad)
        if d2 < 2.6:
            t = max(0.0, 1.0 - d2 / 2.6)
            h += hh * t * t * (3 - 2 * t)
    return h


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
    """Polygons with a material, per-corner UV and colour."""

    def __init__(self):
        self.P = []

    def poly(self, pts, mat, uvs, cols, want=None):
        pts = [V(p) for p in pts]
        if len(pts) < 3:
            return
        n = newell(pts)
        if n.length < 1e-10:
            return
        uvs, cols = list(uvs), [tuple(c[:4]) if len(c)>3 else (*c[:3],1.) for c in cols]
        if want is not None and n.dot(V(want)) < 0:
            pts.reverse(), uvs.reverse(), cols.reverse()
            n = -n
        if len(pts) > 4:
            for a, b, c in tessellate_polygon([pts]):
                if newell([pts[a], pts[b], pts[c]]).dot(n) < 0:
                    a, c = c, a
                self.P.append(([pts[a], pts[b], pts[c]], mat, [uvs[a], uvs[b], uvs[c]], [cols[a], cols[b], cols[c]]))
            return
        self.P.append((pts, mat, uvs, cols))

    def extend(self, o):
        self.P += o.P

    def mirrored(self):
        out = Acc()
        for pts, mat, uvs, cols in self.P:
            pts2 = [V((2 * AXIS - p.x, p.y, p.z)) for p in reversed(pts)]
            m2 = TEAM_SWAP.get(mat, mat)
            if mat in WORLD_UV:
                rep = WORLD_UV[mat]
                uv2 = [(p.x / rep, p.y / rep) for p in pts2]
            else:
                uv2 = list(reversed(uvs))
            out.P.append((pts2, m2, uv2, list(reversed(cols))))
        return out

    def tris(self):
        return sum(len(p[0]) - 2 for p in self.P)


def make_object(name, acc, coll, sharp_deg=30.0):
    verts, faces, mi, uvl, cl = [], [], [], [], []
    names = sorted({p[1] for p in acc.P})
    for pts, mat, uvs, cols in acc.P:
        base = len(verts)
        verts += [tuple(p) for p in pts]
        faces.append(tuple(range(base, base + len(pts))))
        mi.append(names.index(mat))
        for u in uvs:
            uvl += [u[0], u[1]]
        for c in cols:
            cl += [c[0], c[1], c[2], c[3]]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("material_index", mi)
    uv = me.uv_layers.new(name="UVMap")
    uv.data.foreach_set("uv", uvl)
    ca = me.color_attributes.new("Col", "FLOAT_COLOR", "CORNER")
    ca.data.foreach_set("color", cl)
    me.color_attributes.active_color = ca
    # weld coincident corners (UV / colour stay per corner), smooth + sharp edges (mounds smooth, steps crisp)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    try:
        me.set_sharp_from_angle(angle=math.radians(sharp_deg))
    except Exception:  # noqa: BLE001
        pass
    for m in names:
        me.materials.append(PL.M(m))
    me.update()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob["kit"] = "showhome_ground"
    return ob


# ============================================================================================ zone lists (west half)
KW = 0.25          # skirt kerb width
SKW = 0.20         # street kerb width (in the map)
RJ = 3.0           # skirt junction kerb radius


def block_corner(Z, OV, P, q, s=RJ, w=KW, inner="pave"):
    """Rounded corner of a pavement block at a junction: the block occupies quadrant q from corner P (kerb outer
    corner). The square P..P+q*s becomes road; an overlay draws the paving sector + kerb ring."""
    x0, x1 = sorted((P[0], P[0] + q[0] * s))
    y0, y1 = sorted((P[1], P[1] + q[1] * s))
    Z.append(("road", x0, y0, x1, y1))
    OV.append(dict(type="corner", P=P, q=q, s=s, inner=(inner, s - w), ring=("kerb", s - w, s), outer=None))


def road_corner(Z, OV, P, q, r, w=SKW, outer="pave"):
    """Rounded convex corner of a road: the road occupies quadrant q from P (P = kerb outer corner); the kerb runs
    outside the road. The square P..P+q*(r+w) becomes road; overlays draw the kerb ring and the outer paving."""
    s = r + w
    x0, x1 = sorted((P[0], P[0] + q[0] * s))
    y0, y1 = sorted((P[1], P[1] + q[1] * s))
    Z.append(("road", x0, y0, x1, y1))
    OV.append(dict(type="corner", P=P, q=q, s=s, inner=None, ring=("kerb", r, s), outer=outer))


def zones_skirt(Z, OV):
    z = lambda k, x0, y0, x1, y1: Z.append((k, x0, y0, x1, y1))  # noqa: E731
    # ---- 1. bases: finished lots (S / SW), sand construction plots (W, N), tracks, earth, driveways
    z("grass", -80, -60, AXIS, 110)
    z("sand", -80, 18, -13.1, 110)
    z("sand", -13.1, 61.1, AXIS, 110)
    for (x0, y0, x1, y1) in ((-38, 64, -26, 74), (-74, 24, -62, 32), (-30, 95, -18, 104), (18, 66, 28, 76),
                             (-8, 92, 4, 101)):
        z("earth", x0, y0, x1, y1)
    z("gravel", -80, 40, -13.1, 43.5)
    z("gravel", -50, 18, -46.5, 110)
    z("gravel", -13.1, 84, AXIS, 87.5)
    z("gravel", 8, 61.1, 11.5, 110)
    for x in (-66, -48, -30, -12, 6, 24):
        z("conc", x, -26, x + 3.4, -13.1)
    for x in (-57, -39, -21, -3, 15, 33):
        z("edge_ns", x - 0.1, -60, x + 0.1, -14.6)
    for y in (-1.0, 9.0):
        z("conc", -26, y, -13.1, y + 3.4)
    z("edge_ew", -80, 5.4, -13.1, 5.6)
    # ---- 2. pavements and verges
    z("verge", -80, -14.6, AXIS, -13.1)
    z("pave", -80, -13.1, AXIS, -11.1)            # south road, far side
    z("pave", -80, -2.6, -10.85, -0.6)             # south road, near side west of the junction
    z("pave", -2.6, -2.6, AXIS, 0)                 # site south pavement (to the boundary wall)
    z("pave", -13.1, -60, -11.1, 110)              # west road, far side
    z("pave", -2.6, -60, -0.6, -2.6)               # west road, east side south of the south road
    z("pave", -2.6, -2.6, 0, 50.6)                 # site west pavement (to the boundary hedge)
    z("pave", -2.6, 50.6, -0.6, 110)               # west road, east side north of the site road
    z("pave", -2.6, 48, AXIS, 50.6)                # site north pavement (to the acoustic fence)
    z("pave", -80, 48.6, -10.85, 50.6)             # site road, south side west of the junction
    z("pave", -80, 59.1, AXIS, 61.1)               # site road, far side
    # ---- 3. kerbs
    z("kerb_ew", -80, -11.1, AXIS, -10.85)
    z("kerb_ew", -80, -2.85, AXIS, -2.6)
    z("kerb_ns", -11.1, -60, -10.85, 110)
    z("kerb_ns", -2.85, -60, -2.6, 110)
    z("kerb_ew", -80, 50.6, AXIS, 50.85)
    z("kerb_ew", -80, 58.85, AXIS, 59.1)
    # ---- 4. roads (they win every crossing)
    z("lane", -80, 50.85, AXIS, 58.85)             # north site road (older asphalt)
    z("road", -80, -10.85, AXIS, -2.85)            # south road
    z("road", -10.85, -60, -2.85, 110)             # west road
    # ---- 5. rounded block corners at the two junctions (SW and NW)
    for P, q in (((-2.85, -2.85), (1, 1)), ((-10.85, -2.85), (-1, 1)), ((-10.85, -10.85), (-1, -1)),
                 ((-2.85, -10.85), (1, -1)), ((-2.85, 50.85), (1, -1)), ((-10.85, 50.85), (-1, -1)),
                 ((-10.85, 58.85), (-1, 1)), ((-2.85, 58.85), (1, 1))):
        block_corner(Z, OV, P, q)


SPAWN_A = [tuple(v) for k, v in L.data["design_markers"]["spawn_zones"].items() if k.startswith("W_")]


def zones_map(Z, OV):
    z = lambda k, x0, y0, x1, y1: Z.append((k, x0, y0, x1, y1))  # noqa: E731
    # ---- base lawns
    z("lawn", 0, 0, AXIS, 48)
    z("lawn_ns", 21.0, 14.4, 27.35, 32.0)          # Sage front lawn (mowing stripes N-S)
    z("lawn_ns", 26.6, 32.0, 27.35, 36.0)
    z("lawn_ew", 1.4, 36.0, 27.35, 46.6)           # back garden (stripes E-W)
    # ---- boundary feet
    z("mulch", 0, 0, 1.4, 48)                      # bark mulch under boundary hedge
    z("gravel", 0, 0, AXIS, 1.4)                   # south wall foot (y 1..1.4)
    z("gravel", 0, 46.6, AXIS, 48)                 # north fence foot (y 46.6..47)
    # ---- south lane (shared drive), garage apron, bin store pad
    z("lane", 8.6, 1.4, 26.1, 13.6)
    z("lane", 8.85, 13.6, 21.15, 15.85)
    z("lane", 21.15, 13.6, 23.0, 14.4)
    z("conc", 11.6, 10.6, 16.4, 15.85)
    z("conc", 11.8, 3.8, 15.2, 10.2)
    # ---- alley, gap, forecourt, sidewalk, verges
    z("pave", 26.1, 1.4, 30.0, 6.1)                # Sage Alley (studio <-> office)
    z("pave", 26.3, 6.1, AXIS, 10.0)               # Sage Gap + office forecourt / shuttle stop
    z("pave", 26.3, 10.0, 27.65, 13.6)
    z("kerb_ns", 26.1, 6.1, 26.3, 13.6)            # lane -> gap edge
    z("pave", 27.65, 8.0, 30.0, 47.0)              # sidewalk
    for (y0, y1) in ((18.6, 24.6), (27.4, 29.8), (34.8, 41.6)):
        z("verge", 29.35, y0, 29.95, y1)
    # ---- front lawn details
    z("gravel", 21.0, 14.4, 21.5, 32.15)           # pebble strip along the house front
    z("mulch", 22.85, 13.45, 28.35, 14.55)         # lawn hedge bed
    z("edge_ew", 21.5, 14.4, 22.85, 14.45)         # 5 cm restraint strip
    z("edge_ns", 27.60, 14.4, 27.65, 46.6)         # 5 cm strip under solid fence backing
    z("pave", 21.15, 25.2, 27.65, 26.8)            # front path through the gate gap
    # ---- house surroundings, back garden
    z("pave", 8.85, 32.15, 21.0, 36.0)             # patio
    z("gravel", 11.6, 35.85, 15.4, 39.4)           # rain tank pad
    z("pave", 17.4, 36.0, 18.6, 42.8)              # garden path patio -> shed
    z("pave", 11.0, 41.4, 27.35, 42.6)             # garden path arbour -> sidewalk
    z("conc", 16.8, 42.8, 21.2, 46.6)              # shed base
    z("gravel", 23.9, 44.4, 26.1, 46.6)            # pylon base
    z("gravel", 21.8, 39.3, 25.2, 40.7)            # around the veg beds
    z("soil", 7.85, 38.85, 11.15, 45.15)           # arbour bed
    # ---- spawn yard, gates
    z("gravel", 8.6, 12.15, 9.0, 35.85)
    z("gravel", 3.5, 12.15, 9.0, 12.4)
    z("gravel", 3.5, 35.6, 9.0, 35.85)
    z("pave", 1.4, 7.6, 8.6, 12.4)                 # S gate court (low wall)
    z("pave", 1.4, 11.85, 3.5, 12.4)
    z("pave", 1.4, 35.6, 2.9, 41.0)                # N gate path
    z("gravel", 2.8, 39.3, 7.2, 40.7)              # around the veg beds
    for (x0, y0, x1, y1) in SPAWN_A:               # team spawn zones: tinted paving + teal band
        z("pave_A", x0, y0, x1, y1)
        a, w = 0.15, 0.25
        z("band_A", x0 + a, y0 + a, x1 - a, y0 + a + w)
        z("band_A", x0 + a, y1 - a - w, x1 - a, y1 - a)
        z("band_A", x0 + a, y0 + a, x0 + a + w, y1 - a)
        z("band_A", x1 - a - w, y0 + a, x1 - a, y1 - a)
    # ---- the street
    z("kerb_ns", 30.0, 10.0, 30.0 + SKW, 46.55)
    z("kerb_ew", 30.0, 10.0, AXIS, 10.0 + SKW)
    z("kerb_ew", 30.0, 46.35, AXIS, 46.35 + SKW)
    z("pave", 27.65, 46.55, AXIS, 47.0)
    z("road", 30.2, 10.2, AXIS, 46.35)
    road_corner(Z, OV, (30.0, 10.0), (1, 1), 1.5)
    road_corner(Z, OV, (30.0, 46.55), (1, -1), 4.0)
    # ---- building floors (houses kit / pod kits draw them)
    z("none", 9.0, 16.0, 21.0, 32.0)               # Sage House (houses.glb has the floor)
    z("none", 21.0, 32.0, 26.5, 36.0)              # greenhouse (pod floor placeholder)
    z("none", 20.0, 1.0, 26.0, 6.0)                # studio
    z("none", 30.0, 1.0, AXIS, 8.0)                # sales office


# ============================================================================================ partition
def partition(zones, ext, grid, hole=None, extra=()):
    """zones: [(kind, x0, y0, x1, y1)] in priority order (later wins). Returns xs, ys, G (zone index per cell,
    -1 = nothing, -2 = hole)."""
    X0, Y0, X1, Y1 = ext
    xs, ys = {X0, X1}, {Y0, Y1}

    def add(s, v, lo, hi):
        v = round(v, 4)
        if lo < v < hi:
            s.add(v)
    for (_, x0, y0, x1, y1) in zones:
        add(xs, x0, X0, X1), add(xs, x1, X0, X1), add(ys, y0, Y0, Y1), add(ys, y1, Y0, Y1)
    if hole:
        add(xs, hole[0], X0, X1), add(xs, hole[2], X0, X1), add(ys, hole[1], Y0, Y1), add(ys, hole[3], Y0, Y1)
    for g in (grid,) + tuple(extra):
        v = math.ceil(X0 / g) * g
        while v < X1:
            add(xs, v, X0, X1)
            v += g
        v = math.ceil(Y0 / g) * g
        while v < Y1:
            add(ys, v, Y0, Y1)
            v += g
    xs, ys = np.array(sorted(xs)), np.array(sorted(ys))
    G = np.full((len(xs) - 1, len(ys) - 1), -1, dtype=np.int32)

    def rng(a, lo, hi):
        i0 = int(np.searchsorted(a, round(lo, 4) - 1e-5))
        i1 = int(np.searchsorted(a, round(hi, 4) - 1e-5))
        return max(i0, 0), min(i1, len(a) - 1)
    for idx, (_, x0, y0, x1, y1) in enumerate(zones):
        i0, i1 = rng(xs, max(x0, X0), min(x1, X1))
        j0, j1 = rng(ys, max(y0, Y0), min(y1, Y1))
        if i1 > i0 and j1 > j0:
            G[i0:i1, j0:j1] = idx
    if hole:
        i0, i1 = rng(xs, max(hole[0], X0), min(hole[2], X1))
        j0, j1 = rng(ys, max(hole[1], Y0), min(hole[3], Y1))
        G[i0:i1, j0:j1] = -2
    return xs, ys, G


def merged_rects(xs, ys, G, zones):
    """Merge cells of one zone inside its kind's bucket grid. -> [(kind, x0, y0, x1, y1)]"""
    nx, ny = G.shape
    out = []
    active = {}
    for j in range(ny + 1):
        runs = {}
        if j < ny:
            i = 0
            while i < nx:
                idx = int(G[i, j])
                if idx < 0 or SURF[zones[idx][0]] is None:
                    i += 1
                    continue
                bx, by = SURF[zones[idx][0]]["b"]
                bk = math.floor((xs[i] + 1e-4) / bx)
                i1 = i + 1
                while i1 < nx and int(G[i1, j]) == idx and math.floor((xs[i1] + 1e-4) / bx) == bk:
                    i1 += 1
                runs[(i, i1, idx)] = math.floor((ys[j] + 1e-4) / by)
                i = i1
        new = {}
        for key, ybk in runs.items():
            if key in active and active[key][1] == ybk:
                new[key] = active[key]
            else:
                new[key] = (j, ybk)
        for key, (j0, _) in active.items():
            if key not in new or new[key][0] != j0:
                i0, i1, idx = key
                out.append((zones[idx][0], float(xs[i0]), float(ys[j0]), float(xs[i1]), float(ys[j])))
        active = new
    return out


def risers(xs, ys, G, zones):
    """Vertical faces where neighbouring cells sit at different heights. -> [(x0, y0, x1, y1, zlo, zhi, mat, n)]"""
    nx, ny = G.shape

    def zk(idx):
        if idx < 0:
            return None
        S = SURF[zones[idx][0]]
        return None if S is None else S

    out = []
    for axis in (0, 1):
        n_lines = nx if axis == 0 else ny
        n_along = ny if axis == 0 else nx
        for i in range(1, n_lines):
            cur = None
            for j in range(n_along + 1):
                key = None
                if j < n_along:
                    a = int(G[i - 1, j]) if axis == 0 else int(G[j, i - 1])
                    b = int(G[i, j]) if axis == 0 else int(G[j, i])
                    Sa, Sb = zk(a), zk(b)
                    if Sa is not None and Sb is not None and abs(Sa["z"] - Sb["z"]) > 1e-4:
                        hi, lo, sgn = (Sa, Sb, 1) if Sa["z"] > Sb["z"] else (Sb, Sa, -1)
                        key = (lo["z"], hi["z"], hi["mat"], sgn)
                if cur is not None and (key is None or key != cur[0]):
                    zlo, zhi, mat, sgn = cur[0]
                    c = float(xs[i]) if axis == 0 else float(ys[i])
                    a0 = float(ys[cur[1]]) if axis == 0 else float(xs[cur[1]])
                    a1 = float(ys[j]) if axis == 0 else float(xs[j])
                    out.append((axis, c, a0, a1, zlo, zhi, mat, sgn))
                    cur = None
                if key is not None and cur is None:
                    cur = (key, j)
    return out


def emit_partition(acc_in, acc_out, zones, ext, grid, hole=None, extra=()):
    xs, ys, G = partition(zones, ext, grid, hole, extra)
    borders = GE.register_partition(xs,ys,G,zones)
    rects = merged_rects(xs, ys, G, zones)
    for (kind, x0, y0, x1, y1) in rects:
        S = SURF[kind]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        acc = acc_in if (0 <= cx <= 72 and 0 <= cy <= 48) else acc_out
        if kind.startswith(('kerb','edge')):
            GE.straight_stones(acc,kind,x0,y0,x1,y1,S['mat'] if kind.startswith('kerb') else 'M_GND_Edging')
        # The playable area and the first 3m of the skirt use 25cm mask interpolation.
        # Larger skirt cells are one metre across, with 25cm vertices along their borders.
        def cuts(lo,hi,near,axis):
            spacing=.25 if near else 4.
            values={lo,hi}
            if not near:
                for end,sign in ((lo,1),(hi,-1)):
                    pts=[(end,y) for y in(y0,cy,y1)]if axis==0 else[(x,end)for x in(x0,cx,x1)]
                    if any(max(GE.mask(kind,x,y))>.025 for x,y in pts):
                        values.update(max(lo,min(hi,end+sign*d))for d in(.25,.5,.75))
            values.update(float(v) for v in np.arange(lo+spacing,hi,spacing))
            return sorted(values)
        xx,yy=cuts(x0,x1,-3<=cx<=39 and -3<=cy<=51,0),cuts(y0,y1,-3<=cx<=39 and -3<=cy<=51,1)
        for xa,xb in zip(xx[:-1],xx[1:]):
            for ya,yb in zip(yy[:-1],yy[1:]):
                pts2=[(xa,ya),(xb,ya),(xb,yb),(xa,yb)]
                pts=[(x,y,S['z']+(mound(x,y)if S.get('mound')else 0.))for x,y in pts2]
                acc.poly(pts,S['mat'],[uv_of(S,x,y)for x,y in pts2],[GE.mask(kind,x,y)for x,y in pts2],want=(0,0,1))
    GE.edging_lines(acc_in,[row for row in borders if row[1]==0 and 0<=row[2]<=36 and 0<=row[3] and row[4]<=48 or
                                               row[1]==1 and 0<=row[2]<=48 and 0<=row[3] and row[4]<=36],
                    'M_GND_Edging','M_GND_SteelEdging')
    GE.edging_lines(acc_out,[row for row in borders if row[1]==0 and (row[2]<0 or row[3]<0 or row[4]>48) or
                                                row[1]==1 and (row[2]<0 or row[2]>48 or row[3]<0)],
                    'M_GND_Edging','M_GND_SteelEdging')
    nr = 0
    for (axis, c, a0, a1, zlo, zhi, mat, sgn) in risers(xs, ys, G, zones):
        if axis == 0:     # line x = c, faces toward the lower side: sgn=1 -> upper on the -x side, normal +x
            pts = [(c, a0, zlo), (c, a1, zlo), (c, a1, zhi), (c, a0, zhi)]
            want = (sgn, 0, 0)
            mid = (c, (a0 + a1) / 2)
        else:
            pts = [(a0, c, zlo), (a1, c, zlo), (a1, c, zhi), (a0, c, zhi)]
            want = (0, sgn, 0)
            mid = ((a0 + a1) / 2, c)
        acc = acc_in if (0 <= mid[0] <= 72 and 0 <= mid[1] <= 48) else acc_out
        uvs = [((p[1] if axis == 0 else p[0]) / 2.0, p[2] / 2.0) for p in pts]
        acc.poly(pts, mat, uvs, [(0.7, 0.7, 0.7)] * 4, want=want)
        nr += 1
    log(f"partition {ext}: {len(xs) - 1} x {len(ys) - 1} cells -> {len(rects)} rects, {nr} risers")


# ============================================================================================ overlays
def arc_pts(C, r, a0, a1, n):
    return [(C[0] + r * math.cos(a0 + (a1 - a0) * k / n), C[1] + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def flat_poly(acc, pts2, kind, dz=0.0, mat=None, uvs=None):
    S = SURF[kind]
    z = S["z"] + dz
    cx = sum(p[0] for p in pts2) / len(pts2)
    cy = sum(p[1] for p in pts2) / len(pts2)
    acc.poly([(x, y, z) for x, y in pts2], mat or S["mat"], uvs or [uv_of(S, x, y) for x, y in pts2],
             [GE.mask(kind,x,y) for x,y in pts2], want=(0, 0, 1))


def riser_line(acc, pts2, zlo, zhi, mat, toward):
    """Vertical strip under a polyline; `toward(p)` -> 2D direction the face should look at."""
    for a, b in zip(pts2[:-1], pts2[1:]):
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        d = toward(m)
        pts = [(a[0], a[1], zlo), (b[0], b[1], zlo), (b[0], b[1], zhi), (a[0], a[1], zhi)]
        L_ = math.hypot(b[0] - a[0], b[1] - a[1])
        acc.poly(pts, mat, [(0, zlo / 2), (L_ / 2, zlo / 2), (L_ / 2, zhi / 2), (0, zhi / 2)], [(0.7, 0.7, 0.7)] * 4,
                 want=(d[0], d[1], 0))


def ring(acc, inner, outer, kind, rep=2.0):
    """Quads between two corresponding polylines (kerb along an arc): U = arc length / rep."""
    S = SURF[kind if kind != "kerb" else "kerb_ew"]
    u = 0.0
    for k in range(len(inner) - 1):
        a, b, c, d = inner[k], inner[k + 1], outer[k + 1], outer[k]
        du = math.hypot(c[0] - d[0], c[1] - d[1])
        w = math.hypot(d[0] - a[0], d[1] - a[1])
        uvs = [(u / rep, 0.0), ((u + du) / rep, 0.0), ((u + du) / rep, w / rep), (u / rep, w / rep)]
        cx, cy = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
        pts = [(p[0], p[1], S["z"]) for p in (a, b, c, d)]
        acc.poly(pts, S["mat"], uvs, [(0,0,0,0)]*4, want=(0, 0, 1))
        u += du
    if kind == 'kerb':
        GE.curved_stones(acc,inner,outer,S['mat'])


def emit_corner(acc, o, n=12):
    P, q, s = o["P"], o["q"], o["s"]
    C = (P[0] + q[0] * s, P[1] + q[1] * s)
    a0 = math.atan2(0.0, -q[0])          # direction C -> (P.x, C.y)
    a1 = math.atan2(-q[1], 0.0)          # direction C -> (C.x, P.y)
    if a1 - a0 > math.pi:
        a1 -= 2 * math.pi
    if a0 - a1 > math.pi:
        a1 += 2 * math.pi
    kz = SURF["kerb_ew"]["z"]
    rk, r0, r1 = o["ring"]
    inner_arc = arc_pts(C, r0, a0, a1, n)
    outer_arc = arc_pts(C, r1, a0, a1, n)
    ring(acc, inner_arc, outer_arc, rk)
    away = lambda m: (m[0] - C[0], m[1] - C[1])  # noqa: E731
    toward = lambda m: (C[0] - m[0], C[1] - m[1])  # noqa: E731
    if o["inner"]:
        ik, ir = o["inner"]
        flat_poly(acc, [C] + arc_pts(C, ir, a0, a1, n), ik)
        riser_line(acc, inner_arc, SURF[ik]["z"], kz, SURF["kerb_ew"]["mat"], toward)
    else:
        riser_line(acc, inner_arc, 0.0, kz, SURF["kerb_ew"]["mat"], toward)
    if o["outer"]:
        ok = o["outer"]
        pts = [P, (C[0], P[1])] + list(reversed(arc_pts(C, r1, a0, a1, n))) + [(P[0], C[1])]
        # pts: P -> (C.x, P.y) -> arc from a1 back to a0 -> (P.x, C.y): ensure it is a simple polygon
        pts = [P, (C[0], P[1])] + arc_pts(C, r1, a1, a0, n)[1:-1] + [(P[0], C[1])]
        flat_poly(acc, pts, ok)
        riser_line(acc, outer_arc, SURF[ok]["z"], kz, SURF["kerb_ew"]["mat"], away)
    else:
        riser_line(acc, outer_arc, 0.0, kz, SURF["kerb_ew"]["mat"], away)


def rrect(x0, y0, x1, y1, r, n=6):
    pts = []
    for cx, cy, a in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for k in range(n + 1):
            t = math.radians(a + 90 * k / n)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts


def clip_x(pts, xmax=AXIS):
    """Sutherland-Hodgman clip of a 2D polygon to x <= xmax."""
    out = []
    n = len(pts)
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        ia, ib = a[0] <= xmax + 1e-9, b[0] <= xmax + 1e-9
        if ia:
            out.append(a)
        if ia != ib:
            t = (xmax - a[0]) / (b[0] - a[0])
            out.append((xmax, a[1] + t * (b[1] - a[1])))
    return out


def island(acc, x0, y0, x1, y1, r, w=SKW, fills=()):
    """Kerbed island on the road, centred on the axis: kerb ring + nested fills [(kind, inset, radius)]. West half."""
    outer = rrect(x0, y0, x1, y1, r)
    inner = rrect(x0 + w, y0 + w, x1 - w, y1 - w, max(r - w, 0.02))
    kz = SURF["kerb_ew"]["z"]
    cxy = ((x0 + x1) / 2, (y0 + y1) / 2)
    for k in range(len(outer)):
        a, b = inner[k], inner[(k + 1) % len(inner)]
        c, d = outer[(k + 1) % len(outer)], outer[k]
        quad = clip_x([a, b, c, d])
        if len(quad) >= 3:
            flat_poly(acc, quad, "kerb_ew")
            GE.stone(acc,quad,.11,SURF['kerb_ew']['mat'],lambda x,y:(x/2,y/2),'island kerb')
    away = lambda m: (m[0] - cxy[0], m[1] - cxy[1])  # noqa: E731
    toward = lambda m: (cxy[0] - m[0], cxy[1] - m[1])  # noqa: E731
    west = lambda pl: [p for p in pl if p[0] <= AXIS + 1e-6]  # noqa: E731
    riser_line(acc, west(outer + outer[:1]), 0.0, kz, SURF["kerb_ew"]["mat"], away)
    prev_z = kz
    for (kind, inset, rad) in fills:
        poly = rrect(x0 + inset, y0 + inset, x1 - inset, y1 - inset, rad)
        fz = SURF[kind]["z"] + 0.001 * (1 + fills.index((kind, inset, rad)))
        flat_poly(acc, clip_x(poly), kind, dz=fz - SURF[kind]["z"])
        riser_line(acc, west(poly + poly[:1]), fz, prev_z, SURF["kerb_ew"]["mat"] if prev_z == kz else
                   SURF[fills[fills.index((kind, inset, rad)) - 1][0]]["mat"], toward)
        prev_z = fz


def mark_rect(acc, x0, y0, x1, y1, mat, base="road"):
    z = SURF[base]["z"] + 0.002
    x1 = min(x1, AXIS)
    if x1 <= x0:
        return
    pts2 = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    n = 0.95 + 0.06 * nz(x0, y0, 0.9, 14)
    acc.poly([(x, y, z) for x, y in pts2], mat, [(x, y) for x, y in pts2], [(n, n, n)] * 4, want=(0, 0, 1))


def mark_seg(acc, a, b, w, mat, base="road"):
    z = SURF[base]["z"] + 0.002
    d = V((b[0] - a[0], b[1] - a[1], 0)).normalized()
    nrm = V((-d.y, d.x, 0)) * (w / 2)
    pts2 = [(a[0] - nrm.x, a[1] - nrm.y), (b[0] - nrm.x, b[1] - nrm.y), (b[0] + nrm.x, b[1] + nrm.y),
            (a[0] + nrm.x, a[1] + nrm.y)]
    pts2 = clip_x(pts2)
    if len(pts2) < 3:
        return
    acc.poly([(x, y, z) for x, y in pts2], mat, [(x, y) for x, y in pts2], [(0.97, 0.97, 0.97)] * len(pts2),
             want=(0, 0, 1))


def decal_disc(acc, cx, cy, r, mat, base, n=20):
    z = SURF[base]["z"] + 0.003
    pts2 = [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    acc.poly([(x, y, z) for x, y in pts2], mat, [(0.5 + (x - cx) / (2 * r), 0.5 + (y - cy) / (2 * r)) for x, y in pts2],
             [(1, 1, 1)] * n, want=(0, 0, 1))


def decal_rect(acc, x0, y0, x1, y1, mat, base, along_y=False):
    z = SURF[base]["z"] + 0.003
    pts2 = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if along_y:
        uvs = [(0, 0), (0, 1), (1, 1), (1, 0)]
    else:
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
    acc.poly([(x, y, z) for x, y in pts2], mat, uvs, [(1, 1, 1)] * 4, want=(0, 0, 1))


def markings_west(acc):
    W, Y = "M_GND_LineWhite", "M_GND_LineYellow"
    # zebra crossing (Sage Gap <-> Clay Gap), stripes along the traffic, 0.5 m on 1.0 m centres
    for k in range(-5, 1):
        mark_rect(acc, AXIS - 0.25 + k, 12.0, AXIS + 0.25 + k, 14.4, W)
    # centre line south of the Mover tail, and between the charger hatch and the hub island
    y = 15.2
    while y < 16.2:
        mark_rect(acc, AXIS - 0.06, y, AXIS + 0.06, min(y + 1.0, 16.2), W)
        y += 2.0
    # double yellow lines along the kerb (no waiting) except at the pod bay
    for (y0, y1) in ((14.8, 29.7), (34.9, 41.8)):
        mark_rect(acc, 30.35, y0, 30.45, y1, Y)
        mark_rect(acc, 30.55, y0, 30.65, y1, Y)
    # kerb-pod bay (white outline)
    mark_rect(acc, 32.3, 30.0, 32.4, 34.6, W)
    mark_rect(acc, 30.2, 29.95, 32.4, 30.05, W)
    mark_rect(acc, 30.2, 34.55, 32.4, 34.65, W)
    for k in range(5):                                   # bay infill chevrons
        yy = 30.55 + k * 0.85
        mark_seg(acc, (30.35, yy), (31.1, yy + 0.35), 0.1, W)
    # hatched taper north of the charger island
    a, b = (34.8, 35.35), (AXIS, 38.0)
    mark_seg(acc, a, b, 0.12, W)
    for t in (0.22, 0.45, 0.68):
        p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        mark_seg(acc, p, (AXIS, p[1] - (AXIS - p[0]) * 0.9), 0.14, W)
    # skirt: centre dashes on the south and west ring roads (skip the junction)
    x = -80.0
    while x < AXIS:
        if not (-14.0 < x < 0.5):
            mark_rect(acc, x, -6.91, x + 2.0, -6.79, W)
        x += 5.0
    y = -60.0
    while y < 110:
        if not (-14.0 < y < 0.5) and not (47.5 < y < 62.0):
            mark_rect(acc, -6.91, y, -6.79, y + 2.0, W)
        y += 5.0
    # give-way lines at the junction mouths
    for (x0, y0, x1, y1) in ((-11.0, -2.75, -2.75, -2.6), ):
        pass


def decals_west(acc):
    for (x, y) in ((32.9, 16.6), (33.0, 37.4), (-20.0, -6.85), (-52.0, -6.85), (14.0, -6.85)):
        decal_disc(acc, x, y, 0.34, "M_GND_Manhole", "road")
    for (x, y) in ((-6.85, 24.0), (-6.85, 80.0)):
        decal_disc(acc, x, y, 0.34, "M_GND_Manhole", "road")
    decal_disc(acc, 18.5, 8.2, 0.34, "M_GND_Manhole", "lane")
    for (x, y, s) in ((28.75, 21.6, 0.6), (28.75, 39.4, 0.6), (12.6, 34.0, 0.6), (2.15, 38.6, 0.5), (16.0, -1.6, 0.6)):
        decal_rect(acc, x - s / 2, y - s / 2, x + s / 2, y + s / 2, "M_GND_Inspection", "pave")
    for y in (16.2, 23.6, 37.6):                         # kerbside gullies on the street
        decal_rect(acc, 30.2, y, 30.52, y + 0.6, "M_GND_Gully", "road", along_y=True)
    for x in (-40.0, -16.0, 8.0, 30.0):                  # kerbside gullies on the south road
        decal_rect(acc, x, -3.17, x + 0.6, -2.85, "M_GND_Gully", "road")


def overlays_west(acc, OV):
    for o in OV:
        emit_corner(acc, o)
    island(acc, 34.7, 30.7, 37.3, 35.3, 0.6, fills=(("pave", SKW, 0.4),))                  # charger island
    island(acc, 33.3, 38.3, 38.7, 44.7, 1.2, fills=(("soil", SKW, 1.0), ("pave", 0.75, 0.3)))  # hub island
    markings_west(acc)
    decals_west(acc)


def pod_floors_west(acc):
    """Placeholder floors for the enterable pods (greenhouse, studio, office): the pod kits replace them."""
    for b in L.brushes(part="building_floor"):
        x0, y0 = b["min"][0], b["min"][1]
        x1, y1 = b["max"][0], b["max"][1]
        if x0 >= AXIS - 1e-6 or (x0 <= 9.01 and x1 >= 20.99):    # east half, or the house (houses kit)
            continue
        x1 = min(x1, AXIS)
        mat = "M_GND_Paving" if y0 > 30 else "M_GND_FloorPlaceholder"
        pts2 = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        rep = 2.4 if mat == "M_GND_Paving" else 2.0
        acc.poly([(x, y, 0.005) for x, y in pts2], mat, [(x / rep, y / rep) for x, y in pts2], [(0.95, 0.95, 0.95)] * 4,
                 want=(0, 0, 1))


def horizon(acc, ext=(-80, -60, 152, 110), R=2000.0):
    x0, y0, x1, y1 = ext
    S = dict(mat="M_GND_GrassFar")
    for (a, b, c, d) in ((-R, -R, R, y0), (-R, y1, R, R), (-R, y0, x0, y1), (x1, y0, R, y1)):
        pts2 = [(a, b), (c, b), (c, d), (a, d)]
        acc.poly([(x, y, 0.0) for x, y in pts2], S["mat"], [(x / 5.0, y / 5.0) for x, y in pts2],
                 [(0.9, 0.9, 0.9)] * 4, want=(0, 0, 1))


def build_ground(coll):
    GE.reset()
    MOUNDS.clear()
    make_mounds()
    Zs, OVs = [], []
    zones_skirt(Zs, OVs)
    Zm, OVm = [], []
    zones_map(Zm, OVm)
    zones = Zs + Zm
    inner_ext = (-3.0, -3.0, AXIS, 51.0)
    acc_in, acc_out, acc_ov, acc_pod, acc_far = Acc(), Acc(), Acc(), Acc(), Acc()
    emit_partition(acc_in, acc_out, zones, inner_ext, 1.25, extra=(2.5, 4.0))
    emit_partition(acc_in, acc_out, Zs, (-80.0, -60.0, AXIS, 110.0), 4.0, hole=inner_ext)
    overlays_west(acc_ov, OVs + OVm)
    horizon(acc_far)
    acc_far.P=[(p,m,u,[(0,0,0,0)]*len(p))for p,m,u,c in acc_far.P]
    steps=GE.write_steps(KIT+'/ground_steps.json')
    log('registered',len(steps['runs']),'raised kerb/edging units')
    objs = []
    for name, acc in (("GND_Ground", acc_in), ("GND_Skirt", acc_out), ("GND_Overlays", acc_ov),
                      ):
        full = Acc()
        full.extend(acc)
        full.extend(acc.mirrored())
        ob = make_object(name, full, coll)
        ob['COLOR_0_semantics']='linear RGBA: worn dirt, gravel spill, moss/wet, sand/mud; no albedo tint'
        ob['ground_blend_contract']='kit/ground_blend_contract.json'
        objs.append(ob)
        log(f"  {name}: {full.tris()} tris")
    ob = make_object("GND_FarPlane", acc_far, coll)
    objs.append(ob)
    return objs


# ============================================================================================ walls, fences, planters
def brush(tag, part=None):
    bs = [b for b in L.brushes(tag=tag, part=part) if b["kind"] != "PlayerClip"]
    if not bs:
        raise KeyError(tag)
    return bs[0]


def garden_wall(P, b, face=None, clad=None, cop=0.08, pl=0.16, ins=0.012):
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    P.box(x0, y0, z0, x1, y1, z0 + pl, "M_GND_Plinth", bev=0.012)
    P.box(x0 + ins, y0 + ins, z0 + pl, x1 - ins, y1 - ins, z1 - cop, "M_GND_WallPrinted", bev=0.02)
    P.box(x0, y0, z1 - cop, x1, y1, z1, "M_GND_Coping", bev=0.02)
    if face:
        axis, val = face
        za, zb = z0 + pl + 0.03, z1 - cop - 0.03
        if axis == "y":
            ya, yb = sorted((val, val - 0.012 if val == y1 else val + 0.012))
            P.box(x0 + 0.1, ya, za, x1 - 0.1, yb, zb, clad, bev=0.004)
        else:
            xa, xb = sorted((val, val - 0.012 if val == x1 else val + 0.012))
            P.box(xa, y0 + 0.1, za, xb, y1 - 0.1, zb, clad, bev=0.004)


def yard_face(b, side):
    cx, cy = (5.0, 24.0) if side == "W" else (67.0, 24.0)
    (x0, y0, _), (x1, y1, _) = b["min"], b["max"]
    if x1 - x0 > y1 - y0:
        return ("y", y0 if cy < y0 else y1)
    return ("x", x0 if cx < x0 else x1)


def boundary_wall_s(P):
    """South boundary wall (C_SWALL, 72 x 1 x 2.4): printed concrete between cream pilasters every 6 m, team
    cladding panels on the inside face (sage west of the axis, clay east), flat cream coping."""
    b = brush("C_SWALL")
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    pl, cop, ins, pw = 0.16, 0.08, 0.006, 0.5
    P.box(x0, y0, z0, x1, y1, z0 + pl, "M_GND_Plinth", bev=0.012)
    P.box(x0, y0, z1 - cop, x1, y1, z1, "M_GND_Coping", bev=0.025)
    xs = [x0 + 6.0 * k for k in range(int((x1 - x0) / 6.0) + 1)]
    for xc in xs:
        P.box(max(xc - pw / 2, x0), y0, z0 + pl, min(xc + pw / 2, x1), y1, z1 - cop, "M_GND_Pilaster", bev=0.02)
    for xa, xb in zip(xs[:-1], xs[1:]):
        a, c = xa + pw / 2, xb - pw / 2
        P.box(a, y0 + ins, z0 + pl, c, y1 - ins, z1 - cop, "M_GND_WallPrinted", bev=0.006)
        clad = "M_GND_CladSage" if (a + c) / 2 < AXIS else "M_GND_CladClay"
        P.box(a + 0.06, y1 - ins, z0 + pl + 0.04, c - 0.06, y1, z1 - cop - 0.04, clad, bev=0.004)


def acoustic_fence_n(P):
    """North acoustic fence (C_NWALL, 72 x 1 x 2.4): stained vertical boards between dark posts every 2.4 m, a
    concrete gravel board and a timber cap. Solid (no gaps)."""
    b = brush("C_NWALL")
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    gb, cap, ins, pw = 0.25, 0.07, 0.012, 0.16
    P.box(x0, y0, z0, x1, y1, z0 + gb, "M_GND_Plinth", bev=0.012)
    P.box(x0, y0, z1 - cap, x1, y1, z1, "M_GND_TimberDark", bev=0.02)
    n = int(round((x1 - x0) / 2.4))
    xs = [x0 + (x1 - x0) * k / n for k in range(n + 1)]
    for xc in xs:
        P.box(max(xc - pw / 2, x0), y0, z0 + gb, min(xc + pw / 2, x1), y1, z1 - cap, "M_GND_TimberDark", bev=0.015)
    for xa, xb in zip(xs[:-1], xs[1:]):
        P.box(xa + pw / 2, y0 + ins, z0 + gb, xb - pw / 2, y1 - ins, z1 - cap, "M_WoodStained", bev=0.008)


def planter(P, b, hedge_block, seed):
    """Lawn planter (3 x 1 x 1): printed-concrete trough + cream lip, filled with a clipped box hedge trimmed flush
    with the trough (top = brush top, so nothing grows above the collision)."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    P.box(x0, y0, z0, x1, y1, z0 + 0.58, "M_GND_WallPrinted", bev=0.03)
    P.box(x0, y0, z0 + 0.58, x1, y1, z0 + 0.64, "M_GND_Coping", bev=0.02)
    hedge_block(P, x0 + 0.002, y0 + 0.002, z0 + 0.64, x1 - 0.002, y1 - 0.002, z1, step=0.24, amp=0.014, seed=seed,
                bev=0.05)
    # Flush top/backing keeps the clipped hedge solid up to the collision cover plane.
    P.box(x0,y0,z1-.014,x1,y1,z1+.002,'M_Hedge',bev=.002)


def veg_bed(P, b, seed):
    """Raised timber veg bed (1 m tall box): corner posts and boards flush with the brush, soil 2 cm below the top,
    low crops that stay under the top + 2 cm."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    t, pst = 0.045, 0.09
    for (xa, ya) in ((x0, y0), (x1 - pst, y0), (x0, y1 - pst), (x1 - pst, y1 - pst)):
        P.box(xa, ya, z0, xa + pst, ya + pst, z1, "M_GND_TimberDark", bev=0.01)
    P.box(x0 + pst, y0, z0, x1 - pst, y0 + t, z1 - 0.04, "M_WoodStainedH", bev=0.006)
    P.box(x0 + pst, y1 - t, z0, x1 - pst, y1, z1 - 0.04, "M_WoodStainedH", bev=0.006)
    P.box(x0, y0 + pst, z0, x0 + t, y1 - pst, z1 - 0.04, "M_WoodStainedH", bev=0.006)
    P.box(x1 - t, y0 + pst, z0, x1, y1 - pst, z1 - 0.04, "M_WoodStainedH", bev=0.006)
    for (xa, ya, xb, yb) in ((x0, y0, x1, y0 + 0.07), (x0, y1 - 0.07, x1, y1), (x0, y0, x0 + 0.07, y1),
                             (x1 - 0.07, y0, x1, y1)):
        P.box(xa, ya, z1 - 0.04, xb, yb, z1, "M_GND_TimberDark", bev=0.008)
    P.box(x0 + t, y0 + t, z1 - 0.25, x1 - t, y1 - t, z1 - 0.018, "M_Soil")
    r = PL.rng(seed)
    nrow = 2
    ncol = int((x1 - x0) / 0.38)
    for i in range(ncol):
        for j in range(nrow):
            cx = x0 + 0.2 + (x1 - x0 - 0.4) * (i + 0.5) / ncol + r.uniform(-0.03, 0.03)
            cy = y0 + 0.3 + (y1 - y0 - 0.6) * j + r.uniform(-0.03, 0.03)
            P.blob((cx, cy, z1 - 0.03), 0.10, r.choice(("M_Crop", "M_CropDark")), scale=(1.0, 1.0, 0.42), sub=1,
                   amp=0.14, seed=seed * 31 + i * 7 + j)


def finish(P, coll, name, meta=None, ao=(0.45, 0.72), ao_fn=None):
    ob = P.finish(coll, meta=meta or {}, ao=ao, ao_fn=ao_fn)
    ob.name = name
    c = ob.users_collection[0]
    c.name = name
    ob["kit"] = "showhome_ground"
    return ob


def build_structures(ns, coll):
    objs = []
    hb = ns["hedge_block"]
    P = PL.Prop("GardenWalls")
    for side in "WE":
        clad = "M_GND_CladSage" if side == "W" else "M_GND_CladClay"
        for tag in ("YARD_N", "YARD_S", "YARD_EN", "YARD_ES"):
            b = brush(f"{side}_{tag}")
            garden_wall(P, b, yard_face(b, side), clad)
        garden_wall(P, brush(f"{side}_LOWWALL"))
    objs.append(finish(P, coll, "GND_GardenWalls", dict(brushes="W/E_YARD_N,S,EN,ES; W/E_LOWWALL")))
    P = PL.Prop("BoundaryWall_S")
    boundary_wall_s(P)
    objs.append(finish(P, coll, "GND_BoundaryWall_S", dict(brushes="C_SWALL")))
    P = PL.Prop("AcousticFence_N")
    acoustic_fence_n(P)
    objs.append(finish(P, coll, "GND_AcousticFence_N", dict(brushes="C_NWALL")))
    P = PL.Prop("Planters")
    for k, tag in enumerate(("W_PLANTER_1", "W_PLANTER_2", "E_PLANTER_1", "E_PLANTER_2")):
        planter(P, brush(tag), hb, 40 + k)
    objs.append(finish(P, coll, "GND_LawnPlanters", dict(brushes="W/E_PLANTER_1,2"),
                       ao_fn=ns["hedge_ao"](z_dark=0.5, lo=0.66)))
    P = PL.Prop("VegBeds")
    for k, tag in enumerate(("W_BEDS_1", "W_BEDS_3", "E_BEDS_1", "E_BEDS_3")):
        veg_bed(P, brush(tag), 60 + k)
    objs.append(finish(P, coll, "GND_VegBeds", dict(brushes="W/E_BEDS_1,3")))
    for o in objs:
        log(f"  {o.name}: {sum(len(p.vertices) - 2 for p in o.data.polygons)} tris")
    return objs


# ============================================================================================ props (build_props.py)
PROP_SET = ["MoverTruck", "KerbPod", "Fence_Run_S", "Fence_Run_N", "Hedge_Boundary", "Hedge_Lawn", "Arbour", "Pylon",
            "Zipline_Cable"]


def props_namespace():
    """Execute build_props.py as a library (everything except its trailing main() call)."""
    path = SH + "/build_props.py"
    src = open(path, encoding="utf-8").read().rstrip()
    src = re.sub(r"\nmain\(\)\s*$", "\n", src)
    ns = {"__name__": "build_props_lib", "__file__": path}
    exec(compile(src, path, "exec"), ns)
    return ns


def place_props(ns, coll):
    built = ns["build"]({"only": set(PROP_SET)})
    rows = ns["placements"](built)
    byname = {"PROP_" + r["name"]: r["obj"] for r in built}
    placed = []
    for row in rows:
        src = byname.get(row["prop"])
        if src is None:
            continue
        o = src.copy()                      # linked mesh data: east / west instances share one glTF mesh
        o.name = f"{row['prop']}__{row['anchor']}"
        o.location = row["design_loc"]
        o.rotation_euler = (0.0, 0.0, math.radians(row["yaw_deg"]))
        coll.objects.link(o)
        o["anchor"] = row["anchor"]
        o["brushes_covered"] = json.dumps(row["brushes"])
        o["kit"] = "showhome_ground"
        placed.append(o)
    for r in built:
        ob = r["obj"]
        cols = list(ob.users_collection)
        bpy.data.objects.remove(ob, do_unlink=True)
        for c in cols:
            if not c.objects and not c.children:
                bpy.data.collections.remove(c)
    for c in [c for c in bpy.data.collections if c.name == "PROPS" and not c.objects and not c.children]:
        bpy.data.collections.remove(c)
    json.dump(dict(doc="Brush-matched props placed by build_ground.py (geometry from build_props.py). design_loc: "
                       "metres, x east, y north, z up (Blender / layout frame). bevy_translation = (x, z, -y); "
                       "bevy rotation = Quat::from_rotation_y(bevy_yaw_rad). In ground.glb the node of each placement "
                       "is named <prop>__<anchor>.", placements=rows),
              open(KIT + "/ground_placements.json", "w"), indent=1)
    log(f"placed {len(placed)} props")
    return placed


# ============================================================================================ export + check
def export(objs,ns):
    import ground_blend as GB
    GB.prepare_export()
    bpy.context.view_layer.update()
    col=bpy.data.collections.new('_GROUND_EXPORT')
    bpy.context.scene.collection.children.link(col)
    parts=[]
    for source in objs:
        group=ns['material_parts'](source,col,source.name+'_Root')
        group[0].matrix_world=source.matrix_world.copy()
        for ob in group[1:]:
            bm=bmesh.new();bm.from_mesh(ob.data)
            bmesh.ops.triangulate(bm,faces=list(bm.faces))
            bm.to_mesh(ob.data);bm.free()
            attrs=ob.data.color_attributes
            if attrs.get('Col'):
                attrs.active_color_index=attrs.find('Col')
                attrs.render_color_index=attrs.find('Col')
        parts+=group
    bpy.ops.object.select_all(action="DESELECT")
    for o in parts:
        o.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    glb = KIT + "/ground.glb"
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_tangents=True, export_vertex_color="NAME",
                              export_vertex_color_name='Col',export_all_vertex_colors=False,
                              export_normals=True, export_extras=True)
    log("exported", glb, f"{os.path.getsize(glb) / 1e6:.1f} MB")
    for ob in parts:
        data=ob.data if ob.type=='MESH' else None
        bpy.data.objects.remove(ob,do_unlink=True)
        if data and data.users==0:bpy.data.meshes.remove(data)
    bpy.data.collections.remove(col)
    GB.restore_preview()
    blend = KIT + "/ground.blend"
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True, relative_remap=False)
    log("saved", blend)
    return glb


# brushes this kit is responsible for (INVISIBLE mismatches on any other brush belong to other kits)
OWN_TAGS = {"C_SWALL", "C_NWALL", "C_MOVER_BOX", "C_MOVER_CAB"}
for _s in "WE":
    OWN_TAGS |= {f"{_s}_{t}" for t in ("HEDGE", "HEDGE_LAWN", "FENCE_FS", "FENCE_FN", "YARD_N", "YARD_S", "YARD_EN",
                                       "YARD_ES", "LOWWALL", "PLANTER_1", "PLANTER_2", "BEDS_1", "BEDS_3", "KERBPOD",
                                       "ARBOUR", "PYLON_MAST", "PYLON_PAD")}


def check(glb):
    out = KIT + "/ground_alignment.json"
    cmd = [BLENDER, "-b", "--factory-startup", "-P", SH+'/check_assembled.py']
    log("alignment check ...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3000)
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("alignment", "    ["))]
    for ln in lines[:6]:
        log(ln)
    if r.returncode:
        raise RuntimeError(r.stdout[-3000:]+r.stderr[-3000:])
    rep=json.load(open(KIT+'/assembled_alignment.json'))
    json.dump(rep,open(out,'w'),indent=1)
    house_floor = lambda m: m["tag"] == "GROUND" and 9.0 <= m["hit"][0] <= 21.0 or (  # noqa: E731
        m["tag"] == "GROUND" and 51.0 <= m["hit"][0] <= 63.0) if m["kind"] == "INVISIBLE" else False
    mine, other_inv, ghosts = [], {}, []
    for m in rep["items"]:
        if m["kind"] == "GHOST":
            ghosts.append(m)
        elif m["tag"] in OWN_TAGS or (m["tag"] == "GROUND" and not (
                (9.0 <= m["hit"][0] <= 21.0 or 51.0 <= m["hit"][0] <= 63.0) and 16.0 <= m["hit"][1] <= 32.0)):
            mine.append(m)
        else:
            other_inv[m["tag"]] = other_inv.get(m["tag"], 0) + 1
    del house_floor

    def by_tag(items):
        d = {}
        for m in items:
            k = (m["tag"], m["kind"])
            d[k] = d.get(k, 0) + 1
        return sorted(([k[0], k[1], n] for k, n in d.items()), key=lambda r_: -r_[2])
    summ = dict(rays=rep["rays"], total=rep["mismatches"], ghost=len(ghosts), invisible_own=len(mine),
                invisible_other_kits=sum(other_inv.values()), ghost_by_tag=by_tag(ghosts), own_by_tag=by_tag(mine),
                other_kits_by_tag=sorted(([k, n] for k, n in other_inv.items()), key=lambda r_: -r_[1]),
                ghost_items=ghosts[:200], own_items=mine[:200])
    json.dump(summ, open(KIT + "/ground_alignment_summary.json", "w"), indent=1)
    log(f"ALIGNMENT: {rep['rays']} rays; GHOST {len(ghosts)}; INVISIBLE on this kit's brushes {len(mine)}; "
        f"INVISIBLE on other kits' brushes (not built here) {sum(other_inv.values())}")
    for r_ in summ["ghost_by_tag"][:15]:
        log("   ghost near", r_)
    for r_ in summ["own_by_tag"][:15]:
        log("   own invisible", r_)
    return summ


# ============================================================================================ renders
def aim(ob, loc, tgt):
    ob.location = loc
    ob.rotation_euler = (V(tgt) - V(loc)).to_track_quat("-Z", "Y").to_euler()


def sun_dir(so, el, az):
    e, a = math.radians(el), math.radians(az)
    d = V((math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def setup_render(quick):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("_Sky")
    w.use_nodes = True
    nt = w.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    # sky gradient: pale warm horizon -> soft blue zenith
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mp = nt.nodes.new("ShaderNodeMapRange")
    mp.inputs["From Min"].default_value = -0.05
    mp.inputs["From Max"].default_value = 0.6
    nt.links.new(sep.outputs["Z"], mp.inputs["Value"])
    nt.links.new(mp.outputs["Result"], ramp.inputs["Fac"])
    ramp.color_ramp.elements[0].color = (*PL.lin((236, 222, 206)), 1)
    ramp.color_ramp.elements[1].color = (*PL.lin((120, 160, 214)), 1)
    tcw = nt.nodes.new("ShaderNodeTexCoord")
    del tcw
    # Generated coords of the world are the view direction: use Normal-like via the "Generated" Z component
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    sc.world = w
    sd = bpy.data.lights.new("_Sun", "SUN")
    sd.energy = 4.4
    sd.color = (1.0, 0.84, 0.66)
    sd.angle = math.radians(2.0)
    so = bpy.data.objects.new("_Sun", sd)
    sc.collection.objects.link(so)
    bc._set_engine(sc)
    try:
        sc.eevee.taa_render_samples = 16 if quick else 48
    except Exception:  # noqa: BLE001
        pass
    for attr, val in (("use_shadows", True), ("use_raytracing", True), ("use_fast_gi", True),
                      ("shadow_ray_count", 2), ("shadow_step_count", 8)):
        try:
            setattr(sc.eevee, attr, val)
        except Exception:  # noqa: BLE001
            pass
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except Exception:  # noqa: BLE001
        pass
    sc.render.image_settings.file_format = "PNG"
    cd = bpy.data.cameras.new("_Cam")
    cam = bpy.data.objects.new("_Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cd.clip_start, cd.clip_end = 0.1, 4500
    return cam, so


def context_objects(covered):
    """houses.glb (the architecture kit) + neutral boxes for every visible brush no kit draws yet."""
    ctx = bpy.data.collections.new("_CONTEXT")
    bpy.context.scene.collection.children.link(ctx)
    houses = KIT + "/houses.glb"
    if os.path.exists(houses):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=houses)
        for o in set(bpy.data.objects) - before:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            ctx.objects.link(o)
            o.name = "_" + o.name
    path = LAYOUT_DIR + "/showhome_collision_preview.blend"
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("COL_")]
    grey = bc.material("_M_Unbuilt", PL.lin((196, 190, 182)), rough=0.85)
    dark = bc.material("_M_UnbuiltRoof", PL.lin((96, 92, 94)), rough=0.8)
    for o in dst.objects:
        if o is None:
            continue
        bi = o.get("brush_index")
        b = L.all[bi] if bi is not None else None
        drop = (b is None or b["kind"] == "PlayerClip" or b["look"] in ("Ground", "TeamA", "TeamB", "Invisible")
                or bi in covered or b["tag"]["structure"] in ("SAGE_HOUSE", "CLAY_HOUSE", "SAGE_HOUSE_PROPS",
                                                              "CLAY_HOUSE_PROPS")
                or b["tag"].get("part") == "building_floor")
        if drop:
            bpy.data.objects.remove(o, do_unlink=True)
            continue
        o.name = "_" + o.name
        o.data.materials.clear()
        o.data.materials.append(dark if b["look"] == "Roof" else grey)
        ctx.objects.link(o)
    return ctx


VIEWS = {
    # name: (location, target, lens (or ('ortho', scale)), resolution, sun elevation)
    "top": ((AXIS, 24.0, 160.0), (AXIS, 24.0, 0.0), ("ortho", 104.0), (1800, 1200), 62),
    "aerial_s11": ((AXIS, -26.0, 40.0), (AXIS, 25.0, 0.0), 30.0, (1600, 900), 28),
    "aerial_s12": ((4.0, -16.0, 30.0), (40.0, 28.0, 0.0), 28.0, (1600, 900), 28),
    "street": ((AXIS, 11.5, 1.6), (AXIS, 30.0, 2.6), 16.0, (1600, 900), 28),
    "lawn": ((22.6, 26.0, 1.6), (56.0, 26.0, 3.0), 18.0, (1600, 900), 28),
    "edge_nw": ((AXIS, 24.0, 9.5), (-20.0, 64.0, 0.0), 20.0, (1600, 900), 28),
    "edge_se": ((AXIS, 24.0, 9.5), (96.0, -24.0, 0.0), 20.0, (1600, 900), 28),
    "far": ((-60.0, -70.0, 60.0), (AXIS, 30.0, 0.0), 24.0, (1600, 900), 28),
}


def render_all(quick, views, covered):
    import lookdev_common as LD
    cam,sun=LD.setup(quick=quick,fog=True)
    sc = bpy.context.scene
    os.makedirs(RENDERS, exist_ok=True)
    context_objects(covered)
    out = []
    for name, (loc, tgt, lens, res, el) in VIEWS.items():
        if views and name not in views:
            continue
        aim(cam, loc, tgt)
        if isinstance(lens, tuple):
            cam.data.type = "ORTHO"
            cam.data.ortho_scale = lens[1]
            cam.data.clip_start = 1.0
        else:
            cam.data.type = "PERSP"
            cam.data.lens = lens
            cam.data.clip_start = 0.1 if loc[2] < 12 else 0.5
        sun.rotation_euler=(-LD.sun_direction()).to_track_quat('-Z','Y').to_euler()
        sc.render.resolution_x, sc.render.resolution_y = res if not quick else (res[0] * 3 // 4, res[1] * 3 // 4)
        p = f"{RENDERS}/ground_{name}.png"
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
        out.append(p)
        log("rendered", p)
    return out


def compare_sheets():
    code = r'''
import sys, os
from PIL import Image, ImageDraw, ImageFont
R, C = sys.argv[1], sys.argv[2]
pairs = [("A_showhome_aerial_s11.png", "ground_aerial_s11.png"), ("A_showhome_aerial_s12.png", "ground_aerial_s12.png"),
         ("A_showhome_ground_s11.png", "ground_street.png")]
W = 960
try:
    f = ImageFont.truetype("arial.ttf", 22)
except Exception:
    f = ImageFont.load_default()
tiles = []
for cn, rn in pairs:
    if not os.path.exists(os.path.join(R, rn)):
        continue
    a = Image.open(os.path.join(C, cn)).convert("RGB"); a = a.resize((W, int(a.height * W / a.width)))
    b = Image.open(os.path.join(R, rn)).convert("RGB"); b = b.resize((W, int(b.height * W / b.width)))
    tiles.append((a, cn, b, rn))
h = sum(max(a.height, b.height) + 34 for a, _, b, _ in tiles)
sheet = Image.new("RGB", (2 * W + 10, max(h, 10)), (24, 24, 28)); d = ImageDraw.Draw(sheet); y = 0
for a, cn, b, rn in tiles:
    d.text((8, y + 6), "CONCEPT  " + cn, fill=(235, 235, 235), font=f)
    d.text((W + 18, y + 6), "GROUND KIT + houses (grey = not built yet)  " + rn, fill=(235, 235, 235), font=f)
    sheet.paste(a, (0, y + 34)); sheet.paste(b, (W + 10, y + 34)); y += max(a.height, b.height) + 34
p = os.path.join(R, "ground_compare_concept.png"); sheet.save(p); print("wrote", p)
'''
    try:
        r = subprocess.run(["python", "-c", code, RENDERS, CONCEPTS], capture_output=True, text=True, timeout=120)
        log(r.stdout.strip(), r.stderr.strip()[-400:])
    except Exception as e:  # noqa: BLE001
        log("compare sheet skipped:", e)


# ============================================================================================ main
def covered_brushes():
    cov = set()
    for b in L.all:
        t = b["tag"]
        if t["id"] in OWN_TAGS or t["structure"] == "GROUND":
            cov.add(b["i"])
    return cov


def main():
    a = args()
    if not all(os.path.exists(os.path.join(GTEX, n)) for n in ("manhole.png", "gully.png", "inspection.png")):
        subprocess.run(["python", SH + "/ground_textures.py"], check=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    ns = props_namespace()
    ns["materials"]()
    materials()
    root = bpy.data.collections.new("SHOWHOME_GROUND")
    bpy.context.scene.collection.children.link(root)
    c_ground = bpy.data.collections.new("GND_Surfaces")
    c_struct = bpy.data.collections.new("GND_Boundaries")
    c_props = bpy.data.collections.new("GND_PlacedProps")
    for c in (c_ground, c_struct, c_props):
        root.children.link(c)
    log("ground surfaces ...")
    objs = build_ground(c_ground)
    log("walls, fences, planters ...")
    objs += build_structures(ns, c_struct)
    log("props ...")
    objs += place_props(ns, c_props)
    tot = 0
    for o in objs:
        if o.type == "MESH":
            tot += sum(len(p.vertices) - 2 for p in o.data.polygons)
    log(f"total {tot} tris (instances counted) in {len(objs)} objects")
    import ground_blend as GB
    GB.setup_preview()
    GB.write_contract()
    json.dump(dict(triangles=tot,objects=len(objs),
                   meshes=[dict(name=o.name,triangles=sum(len(p.vertices)-2 for p in o.data.polygons))for o in objs],
                   materials=sorted({m.name for o in objs for m in o.data.materials}),
                   frame='design X east Y north Z up; glTF=(x,z,-y); load identity'),
              open(KIT+'/ground_stats.json','w'),indent=2)
    glb = export(objs,ns)
    if a["check"]:
        check(glb)
    if a["render"]:
        render_all(a["quick"], a["views"], covered_brushes())
        compare_sheets()
    log("done")


main()
