"""Pure-Python access to the Showhome collision layout (no bpy needed; also importable inside Blender).

    import sys; sys.path.insert(0, r"F:/git/val etf/assets/maps/showhome/layout")
    import layout_lib as LL
    L = LL.load()                                   # showhome_annotated.json
    for b in L.brushes(structure="SAGE_HOUSE", part="lintel"): print(b["tag"]["id"], b["min"], b["max"])
    L.structure("SAGE_GREENHOUSE")["min"]           # visible bounds of a structure
    L.openings(structure="SAGE_HOUSE")              # every door / window with span, sill, head
    LL.to_bevy((x, y, z))                           # design (Blender Z-up) -> Bevy (Y-up)

Everything is in the DESIGN frame (metres, x = east, y = north, z = up), the frame to build the Blender kit in.
A glTF export with +Y up of that scene lands exactly on the game's Bevy coordinates: bevy = (x, z, -y).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ANNOTATED = os.path.join(HERE, "showhome_annotated.json")


def to_bevy(p):
    return (p[0], p[2], -p[1])


def to_design(p):
    return (p[0], -p[2], p[1])


# ------------------------------------------------------------------------------------------ geometry
def box_polys(mn, mx):
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1),
         (x0, y1, z1)]
    # outward winding (counter-clockwise seen from outside)
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, f


def wedge_polys(mn, mx, rise):
    """Ramp brush: triangular prism inside mn..mx; the top rises from z0 at the edge opposite `rise` (N/S/E/W)
    to z1 at the `rise` edge. Returns verts, faces (outward winding)."""
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    b = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]
    if rise == "N":
        hi, under, lo = [(x0, y1, z1), (x1, y1, z1)], (3, 2), (0, 1)
    elif rise == "S":
        hi, under, lo = [(x1, y0, z1), (x0, y0, z1)], (1, 0), (2, 3)
    elif rise == "E":
        hi, under, lo = [(x1, y1, z1), (x1, y0, z1)], (2, 1), (3, 0)
    else:  # W
        hi, under, lo = [(x0, y0, z1), (x0, y1, z1)], (0, 3), (1, 2)
    v = b + hi
    f = [(0, 3, 2, 1), (under[0], under[1], 5, 4), (4, 5, lo[1], lo[0]), (under[0], 4, lo[0]),
         (under[1], lo[1], 5)]
    return v, fix_winding(v, f)


def fix_winding(v, faces):
    """Flip faces whose normal points toward the centroid."""
    c = [sum(p[k] for p in v) / len(v) for k in range(3)]
    out = []
    for f in faces:
        n = poly_normal([v[i] for i in f])
        p = v[f[0]]
        if sum(n[k] * (p[k] - c[k]) for k in range(3)) < 0:
            f = tuple(reversed(f))
        out.append(tuple(f))
    return out


def poly_normal(pts):
    nx = ny = nz = 0.0
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    ln = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
    return (nx / ln, ny / ln, nz / ln)


def brush_polys(b):
    if b["shape"] == "ramp":
        return wedge_polys(b["min"], b["max"], b["ramp"]["rise_toward"])
    return box_polys(b["min"], b["max"])


def surface_z(b, x, y):
    """Top surface height of a brush at (x, y) (ramps: the slope), ignoring whether (x, y) is inside."""
    if b["shape"] != "ramp":
        return b["max"][2]
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    d = b["ramp"]["rise_toward"]
    f = {"N": (y - y0) / (y1 - y0), "S": (y1 - y) / (y1 - y0), "E": (x - x0) / (x1 - x0),
         "W": (x1 - x) / (x1 - x0)}[d]
    return z0 + max(0.0, min(1.0, f)) * (z1 - z0)


def inside(b, p, eps=1e-4):
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    x, y, z = p
    if not (x0 + eps < x < x1 - eps and y0 + eps < y < y1 - eps and z0 + eps < z < z1 - eps):
        return False
    return b["shape"] != "ramp" or z < surface_z(b, x, y) - eps


def box_distance(b, p):
    d2 = 0.0
    for k in range(3):
        lo, hi = b["min"][k], b["max"][k]
        if p[k] < lo:
            d2 += (lo - p[k]) ** 2
        elif p[k] > hi:
            d2 += (p[k] - hi) ** 2
    return d2 ** 0.5


# ------------------------------------------------------------------------------------------ data access
class Layout:
    def __init__(self, data):
        self.data = data
        self._structs = {s["id"]: s for s in data["structures"]}

    @property
    def all(self):
        return self.data["brushes"]

    def visible(self):
        """Brushes the art must cover (drawn by the game today): not player clips, not invisible."""
        return [b for b in self.all if b["kind"] != "PlayerClip" and b["look"] != "Invisible"]

    def brushes(self, structure=None, tag=None, part=None, look=None, kind=None, prefix=None):
        out = []
        for b in self.all:
            t = b["tag"]
            if structure and t["structure"] != structure:
                continue
            if tag and t["id"] != tag:
                continue
            if prefix and not t["id"].startswith(prefix):
                continue
            if part and t.get("part") != part:
                continue
            if look and b["look"] != look:
                continue
            if kind and b["kind"] != kind:
                continue
            out.append(b)
        return out

    def structure(self, sid):
        return self._structs[sid]

    def structures(self):
        return self.data["structures"]

    def openings(self, structure=None, wall=None):
        return [o for o in self.data["openings"] if (not structure or o["structure"] == structure)
                and (not wall or o["wall"] == wall)]

    def heights(self):
        return self.data["heights"]

    def spawns(self, team=None):
        return [s for s in self.data["spawns"] if not team or s["team"] == team]


def load(path=ANNOTATED):
    with open(path, encoding="utf-8") as f:
        return Layout(json.load(f))
