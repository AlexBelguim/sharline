"""Render the extraction-map layout diagram (v0.2, 1300 x 1100 m) and its numbers.

    python make_diagram.py

Writes (all next to this folder's parent):
    ../diagram.svg, ../diagram.png          the top-view diagram (same matplotlib figure, two formats)
    ../data/extraction_layout.json          every zone, point, crossing and the travel-time matrix
    ../LAYOUT.md                            refreshes the <!-- AUTO:... --> tables if the file exists

Matplotlib only (no cairosvg / Inkscape needed). Line widths are given in metres and converted to points from the
fixed axes scale, so roads, the river and the highway are to scale in both the SVG and the PNG.
"""
import heapq
import json
import math
import os
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as pe            # noqa: E402
import matplotlib.pyplot as plt                # noqa: E402
import numpy as np                             # noqa: E402
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle  # noqa: E402
from matplotlib.path import Path               # noqa: E402

import geom as G                               # noqa: E402
import layout_data as D                        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, ".."))

plt.rcParams.update({
    "font.family": ["Arial", "DejaVu Sans"],
    "svg.fonttype": "none",          # keep text as editable <text> in the SVG
    "hatch.linewidth": 0.6,
})

# ------------------------------------------------------------------ canvas (pixels at DPI)
DPI = 150
FIG_W, FIG_H = 4440, 2820
MAP_X0, MAP_X1, MAP_Y0, MAP_Y1 = -40.0, D.MAP_W + 40.0, -60.0, D.MAP_H + 40.0   # map axes extent (m), incl. bands
PX_PER_M = 2.1
MAP_AX_PX = (80, 70, (MAP_X1 - MAP_X0) * PX_PER_M, (MAP_Y1 - MAP_Y0) * PX_PER_M)   # left, bottom, w, h
PANEL_PX = (3060, 70, 1360, 2700)
INSET_EXT = D.INSET_EXT                          # x0, x1, y0, y1 (m): the v0.1 inset, moved with Showhome
INSET_PX_PER_M = 4.4

# ------------------------------------------------------------------ palette
C = dict(
    meadow="#E2EAC6", arable="#EFE4BF", stripe="#D8C68C", forest="#A3C48F", tree="#6E9A5D", forest_edge="#5F8A51",
    dense="#6F9562", worksite="#E8D2A6", water="#86BEDF", water_edge="#3F82AE", bank="#C2B9A0",
    main="#575B63", main_case="#25282C", street="#8A8F97", street_case="#4B4F56", gravel="#D2BE93",
    gravel_case="#8F7A53", field="#8A6A43", cover="#24683A", deck="#4C5058", slope="#D3CCB8", tick="#8E8570",
    bldg="#575C64", tank="#CFE5EA", tank_edge="#3E6670", rampdeck="#BDB3D6", rampdeck_edge="#5E4F8A", skip="#D9772E",
    plot="#D8D2C2", pit="#B99A6A", hedge="#3F6E36", ditch="#5A9BCB", hay="#D9B44A", power="#5C5C5C",
    ink="#1F2328", grid="#000000", spawn="#1E63E9", extract="#14A04A", extract_dark="#0B6B30", sight="#E02424",
    choke="#C40000", tdm="#5B1A8C", landmark="#C88200", zip="#7A3FB8", fence="#3A3F46", dike="#B7A27C",
    industrial="#A7A9AD",
)
POI_FILL = dict(SHOWHOME="#E4572E", WORKSITE="#F2A541", FARM="#9C6B3F", HUT="#7F9A3A", CONTAINER="#8E6CCF",
                PLANT="#2A9D8F", SUBSTATION="#6C7A89", STORAGE="#C0508F", GAS="#E2B714", SLUICE="#4E93A6")
TIER = {1: "#8A99A6", 2: "#D9A520", 3: "#EC7A1C", 4: "#D7263D"}
CAR_COLS = ["#F4F4F4", "#E15B4F", "#5AA0E0", "#F2C94C", "#9FD27E", "#C7CCD3"]
HALO = [pe.withStroke(linewidth=3.2, foreground="white")]
HALO_S = [pe.withStroke(linewidth=2.4, foreground="white")]


# ================================================================== derived geometry
def resample(P, step):
    P = np.asarray(P, float)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, s[-1], step)
    return np.stack([np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])], axis=1)


def road_line(r):
    return G.catmull_rom(r["pts"], samples=10) if r["smooth"] else np.asarray(r["pts"], float)


def derive():
    river = D.river_line()
    hw = D.highway_line()
    roads = {r["id"]: dict(r, line=road_line(r)) for r in D.ROADS}
    X = dict(river=river, hw=hw, roads=roads)

    # river crossings
    cross = {}
    for c in D.RIVER_CROSSINGS:
        if c["road"]:
            hit = G.polyline_hits(roads[c["road"]]["line"], river)[0]
            d = G.direction_at(roads[c["road"]]["line"], hit)
        else:
            hit = np.array([G.x_at_y(river, c["y"]), c["y"]])
            t = G.direction_at(river, hit)
            d = np.array([t[1], -t[0]])          # perpendicular to the flow
        if d[0] < 0:
            d = -d                                # always west -> east
        half = D.RIVER_HALF_W + D.RIVER_BANK_W + 1.5
        cross[c["id"]] = dict(c, at=hit, dir=d, a=hit - d * half, b=hit + d * half, span=2 * half)
    # highway crossings
    for c in D.HIGHWAY_CROSSINGS:
        line = roads[c["road"]]["line"]
        hit = G.polyline_hits(line, hw)[0]
        d = G.direction_at(line, hit)
        if d[0] < 0:
            d = -d
        t = G.direction_at(hw, hit)
        sin = abs(d[0] * t[1] - d[1] * t[0])
        half = (D.HW_DECK_HALF + D.HW_SLOPE_W + 2.0) / max(sin, 0.2)
        cross[c["id"]] = dict(c, at=hit, dir=d, a=hit - d * half, b=hit + d * half, span=2 * half)
    X["cross"] = cross

    # X5 sits on the west hard shoulder of the deck at y = at_y
    x5c = np.array([G.x_at_y(hw, D.EXTRACTS[4]["at_y"]), D.EXTRACTS[4]["at_y"]])
    t = G.direction_at(hw, x5c)
    X["x5"] = x5c + np.array([t[1], -t[0]]) * (-(D.HW_DECK_HALF - 4.0)) * np.sign(t[1] if t[1] else 1)
    # make sure X5 is west of the centre line
    if X["x5"][0] > x5c[0]:
        X["x5"] = x5c - (X["x5"] - x5c)

    # POI polygons that follow the river bank (the plant's west fence)
    for p in D.POIS:
        if "bank" in p:
            side, off = p["bank"]
            east = np.asarray(p["poly_east"], float)
            y_hi, y_lo = east[0][1], east[1][1]
            seg = G.slice_by_y(river, y_hi, y_lo)                     # north -> south
            bank = G.offset(seg, off if side == "E" else -off)[::-1]  # south -> north
            p["poly"] = [tuple(map(float, q)) for q in np.vstack([east, bank])]

    # forest polygons
    forests = []
    for f in D.FORESTS:
        if "ribbon" in f:
            side, yhi, ylo, o1, o2 = f["ribbon"]
            seg = G.slice_by_y(river, yhi, ylo)
            poly = np.vstack([G.offset(seg, o1), G.offset(seg, o2)[::-1]])
        elif "bank" in f:
            side, ya, yb, off = f["bank"]
            seg = G.slice_by_y(river, max(ya, yb), min(ya, yb))
            bank = G.offset(seg, off)
            if ya < yb:
                bank = bank[::-1]
            poly = np.vstack([np.asarray(f["pts_before"], float), bank, np.asarray(f["pts_after"], float)])
        else:
            poly = np.asarray(f["pts"], float)
        forests.append(dict(f, poly=poly))
    X["forests"] = forests

    # towpaths (offsets of the river line)
    tow = []
    c1y, c2y = cross["C1"]["at"][1], cross["C2"]["at"][1]
    plant_top = max(q[1] for q in next(p for p in D.POIS if p["id"] == "PLANT")["poly"])
    for side, yhi, ylo, kind in [("W", c1y - 8, c2y + 8, "field"), ("W", c2y - 8, 36, "cover"),
                                 ("E", c1y - 8, 745, "cover"), ("E", 745, c2y + 8, "field"),
                                 ("E", c2y - 8, plant_top + 3, "cover"), ("E", plant_top + 3, 36, "field")]:
        seg = G.slice_by_y(river, yhi, ylo)
        off = -D.TOWPATH_OFF if side == "W" else D.TOWPATH_OFF
        tow.append(dict(side=side, kind=kind, line=G.offset(seg, off)))
    X["tow"] = tow

    # extract positions
    ext = {}
    for e in D.EXTRACTS:
        ext[e["id"]] = np.asarray(e["at"], float) if e["at"] is not None else X["x5"]
    X["ext"] = ext

    # sightline endpoints
    def endpoint(e):
        if isinstance(e[0], str):
            if e[0] == "GANTRY":
                gy = D.HW_GANTRY_Y[e[1]]
                return np.array([G.x_at_y(hw, gy), gy])
            base = cross[e[0]]["at"] if e[0] in cross else ext[e[0]]
            return np.asarray(base, float) + np.array([e[1], e[2]], float)
        return np.asarray(e, float)

    X["sight"] = {s["id"]: (endpoint(s["a"]), endpoint(s["b"])) for s in D.SIGHTLINES}
    return X


# ================================================================== travel-time graph
def build_graph(X):
    nodes = {}
    for p in D.POIS:
        if p["id"] in D.TRAVEL_POIS:
            nodes[p["id"]] = np.asarray(p["node"], float)
    for s in D.SPAWNS:
        x0, y0, x1, y1 = s["rect"]
        nodes[s["id"]] = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
    for e in D.EXTRACTS:
        nodes[e["id"]] = X["ext"][e["id"]]
    for cid, c in X["cross"].items():
        nodes[cid + "_a"] = c["a"]
        nodes[cid + "_b"] = c["b"]
    ids = list(nodes)
    edges = {i: [] for i in ids}
    v = D.SPEED["sprint"]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            p, q = nodes[a], nodes[b]
            if G.crosses(p, q, X["river"]):
                continue
            t = np.linalg.norm(q - p) * D.ROUTE_FACTOR / v
            via = None
            if G.crosses(p, q, X["hw"]):
                mid = G.polyline_hits([p, q], X["hw"])[0]
                pen = D.CLIMB_PENALTY_S["cutting"] if mid[1] > D.HW_CUT_ABOVE_Y else D.CLIMB_PENALTY_S["embankment"]
                t += 2 * pen
                via = "deck"
            edges[a].append((b, t, via))
            edges[b].append((a, t, via))
    for cid, c in X["cross"].items():
        t = c["span"] / v
        edges[cid + "_a"].append((cid + "_b", t, cid))
        edges[cid + "_b"].append((cid + "_a", t, cid))
    # X5 is on the deck in the cutting: reaching it means a slide down / climb out of the cutting
    return nodes, edges


def dijkstra(edges, src):
    dist = {src: 0.0}
    prev = {}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 1e18):
            continue
        for w, t, via in edges[u]:
            nd = d + t
            if nd < dist.get(w, 1e18):
                dist[w] = nd
                prev[w] = (u, via)
                heapq.heappush(pq, (nd, w))
    return dist, prev


def route_vias(prev, src, dst):
    vias, u = [], dst
    while u != src and u in prev:
        u, via = prev[u]
        if via:
            vias.append(via)
    return list(reversed(vias))


def travel(X):
    nodes, edges = build_graph(X)
    res = {}
    for a in nodes:
        dist, prev = dijkstra(edges, a)
        res[a] = {b: (dist.get(b, float("nan")), route_vias(prev, a, b)) for b in nodes}
    return nodes, res


# ================================================================== drawing helpers
class Scale:
    def __init__(self, px_per_m):
        self.k = px_per_m * 72.0 / DPI           # points per metre

    def lw(self, m):
        return max(m * self.k, 0.3)


def add_poly(ax, pts, z, **kw):
    p = Polygon(np.asarray(pts, float), closed=True, zorder=z, **kw)
    ax.add_patch(p)
    return p


def stroke(ax, P, z, color, width_pt, ls="-", cap="round", alpha=1.0, dashes=None):
    P = np.asarray(P, float)
    ln, = ax.plot(P[:, 0], P[:, 1], color=color, lw=width_pt, ls=ls, zorder=z, solid_capstyle=cap,
                  solid_joinstyle="round", dash_capstyle=cap, alpha=alpha)
    if dashes:
        ln.set_dashes(dashes)
    return ln


def text(ax, x, y, s, size=8, z=40, color=None, weight="normal", ha="center", va="center", halo=True, **kw):
    kw.setdefault("clip_on", True)
    return ax.text(x, y, s, fontsize=size, color=color or C["ink"], weight=weight, ha=ha, va=va, zorder=z,
                   path_effects=HALO if halo else None, **kw)


def poly_inside(poly, pts):
    return Path(np.asarray(poly, float)).contains_points(pts)


# ================================================================== layers
def hw_y_at_east(X):
    hw = X["hw"]
    for i in range(len(hw) - 1):
        (x0, y0), (x1, y1) = hw[i], hw[i + 1]
        if (x0 - D.MAP_W) * (x1 - D.MAP_W) <= 0 and x0 != x1:
            return float(y0 + (D.MAP_W - x0) / (x1 - x0) * (y1 - y0))
    return 0.0


def draw_base(ax, X, S, ext):
    x0, x1, y0, y1 = ext
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=C["meadow"], ec="none", zorder=0))
    # boundary bands outside the playable rect
    W, H = D.MAP_W, D.MAP_H
    ax.add_patch(Rectangle((-60, -80), W + 120, 80, fc=C["dike"], ec="none", zorder=0.5, hatch="////",
                           alpha=0.9))   # dike (south)
    rx = G.x_at_y(X["river"], H)                     # river and highway where they leave the north edge
    hx = G.x_at_y(X["hw"], H)
    hy = hw_y_at_east(X)                             # highway where it leaves the east edge
    ax.add_patch(Rectangle((-60, 0), 60, H + 60, fc=C["dense"], ec="none", zorder=0.5))   # west forest
    ax.add_patch(Rectangle((0, H), rx - 22, 60, fc=C["dense"], ec="none", zorder=0.5))     # north forest W
    ax.add_patch(Rectangle((rx + 22, H), hx - 32 - rx - 22, 60, fc=C["dense"], ec="none", zorder=0.5))  # mid
    ax.add_patch(Rectangle((hx + 32, H), W + 60 - hx - 32, 60, fc=C["dense"], ec="none", zorder=0.5))   # NE
    ax.add_patch(Rectangle((W, hy), 60, H + 60 - hy, fc=C["industrial"], ec="none", zorder=0.5, hatch="||",
                           alpha=0.9))   # industrial estate fence (east)
    ax.add_patch(Rectangle((W, -80), 60, hy + 80, fc=C["dense"], ec="none", zorder=0.5))     # SE woods
    for x in np.arange(-36, W + 40, 10.0):                                                   # dike slope ticks
        add_poly(ax, [(x - 2.0, -19), (x + 2.0, -19), (x, -4)], 0.6, fc="#8C7650", ec="none")
    ax.plot([-60, W + 60], [-20, -20], color="#6E5B3A", lw=1.2, zorder=0.6)                 # dike crest


def draw_fields(ax, X, S):
    for f in D.FIELDS:
        add_poly(ax, f["pts"], 1, fc=C["arable"], ec="none")
        add_poly(ax, f["pts"], 1.1, fc="none", ec=C["stripe"], lw=0, hatch="///" if f["stripe"] > 0 else "\\\\\\")
    # worksite ground under the worksite zone
    ws = next(p for p in D.POIS if p["id"] == "WORKSITE")
    add_poly(ax, ws["poly"], 1.2, fc=C["worksite"], ec="none")
    # nursery rows
    n = D.NURSERY
    x = n["x0"]
    while x <= n["x1"]:
        ax.add_patch(Rectangle((x, n["y0"]), n["row_w"], n["y1"] - n["y0"], fc=C["tree"], ec="none", zorder=1.3))
        x += n["row_dx"]


def draw_forests(ax, X, S, rng, spacing=9.0, ext=None):
    clear = D.CLEARINGS
    for f in X["forests"]:
        poly = f["poly"]
        add_poly(ax, poly, 2, fc=C["forest"], ec=C["forest_edge"], lw=0.8)
        bx0, by0, bx1, by1 = G.poly_bbox(poly)
        if ext:
            bx0, bx1 = max(bx0, ext[0] - 10), min(bx1, ext[1] + 10)
            by0, by1 = max(by0, ext[2] - 10), min(by1, ext[3] + 10)
            if bx0 >= bx1 or by0 >= by1:
                continue
        gx, gy = np.meshgrid(np.arange(bx0, bx1, spacing), np.arange(by0, by1, spacing))
        pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
        pts = pts + rng.uniform(-spacing * 0.35, spacing * 0.35, pts.shape)
        pts = pts[poly_inside(poly, pts)]
        for cx, cy, r in clear:
            pts = pts[np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) > r + 3]
        if len(pts):
            size = (S.k * spacing * 0.62) ** 2
            ax.scatter(pts[:, 0], pts[:, 1], s=size, c=C["tree"], edgecolors="none", zorder=2.1, alpha=0.75)
    for cx, cy, r in clear:
        ax.add_patch(Circle((cx, cy), r, fc=C["meadow"], ec=C["forest_edge"], lw=0.6, zorder=2.2))


def draw_poi_zones(ax, X, S):
    for p in D.POIS:
        col = POI_FILL[p["id"]]
        z = 3.2 if p["id"] == "SHOWHOME" else 3
        if "rect" in p:
            x0, y0, x1, y1 = p["rect"]
            pts = G.rect_poly(x0, y0, x1, y1)
        elif "circle" in p:
            pts = G.circle_poly(*p["circle"])
        else:
            pts = p["poly"]
        add_poly(ax, pts, z, fc=col, ec="none", alpha=0.30)
        add_poly(ax, pts, z + 0.05, fc="none", ec=col, lw=1.6, alpha=0.95)
    # fences around fenced POIs (thin dashed dark line)
    for pid in ("PLANT", "CONTAINER", "STORAGE", "SUBSTATION"):
        p = next(q for q in D.POIS if q["id"] == pid)
        pts = G.rect_poly(*p["rect"]) if "rect" in p else np.asarray(p["poly"], float)
        pts = np.vstack([pts, pts[:1]])
        stroke(ax, pts, 3.3, C["fence"], 0.9, ls=(0, (4, 2)))


def draw_details(ax, X, S):
    for h in D.HEDGEROWS:
        stroke(ax, h, 4, C["hedge"], S.lw(4.0))
    for d in D.DITCHES:
        stroke(ax, G.catmull_rom(d, 8), 3.9, C["ditch"], S.lw(1.6))
    hx = np.array(D.HAY, float)
    offs = np.array([[0, 0], [3.2, 0.8], [1.2, 3.0]])
    pts = (hx[:, None, :] + offs[None, :, :]).reshape(-1, 2)
    ax.scatter(pts[:, 0], pts[:, 1], s=(S.k * 2.4) ** 2, c=C["hay"], edgecolors="#8A6A1E", linewidths=0.4,
               zorder=4.1)
    # avenue trees along the west Old Road
    st = X["roads"]["OLD_ROAD"]["line"]
    west = st[(st[:, 0] > 15) & (st[:, 0] < X["cross"]["C2"]["a"][0] - 20)]
    rs = resample(west, 15.0)
    for side in (11.5, -11.5):
        tp = G.offset(rs, side)
        ax.scatter(tp[:, 0], tp[:, 1], s=(S.k * 5.0) ** 2, c=C["tree"], edgecolors=C["forest_edge"],
                   linewidths=0.4, zorder=4.2)
    # power line and pylons
    pl = np.asarray(D.POWERLINE, float)
    stroke(ax, pl, 4.3, C["power"], 0.9, ls=(0, (8, 3, 1.5, 3)))
    for x, y in pl[:-1]:
        ax.plot([x], [y], marker="X", ms=6.5, mfc="white", mec=C["power"], mew=1.2, zorder=4.4)


def draw_river(ax, X, S):
    r = X["river"]
    stroke(ax, r, 5, C["bank"], S.lw(2 * (D.RIVER_HALF_W + D.RIVER_BANK_W)))
    stroke(ax, r, 5.1, C["water_edge"], S.lw(2 * D.RIVER_HALF_W + 1.6))
    stroke(ax, r, 5.2, C["water"], S.lw(2 * D.RIVER_HALF_W - 1.0))
    # flow arrows
    for y in (1000, 680, 170):
        i = G.nearest_index(r, (G.x_at_y(r, y), y))
        p, q = r[i], r[i + 3]
        ax.annotate("", xy=q, xytext=p, zorder=5.3,
                    arrowprops=dict(arrowstyle="-|>", color="#2F6E98", lw=1.0, mutation_scale=10))


def draw_highway(ax, X, S):
    hw = X["hw"]
    full = D.HW_DECK_HALF + D.HW_SLOPE_W
    stroke(ax, hw, 6, C["slope"], S.lw(2 * full), cap="butt")
    # embankment / cutting wedges (tick = downhill)
    pts = resample(hw, 9.0)
    nrm = G.left_normals(pts)
    for p, n in zip(pts, nrm):
        if not (-10 < p[0] < D.MAP_W + 10 and -10 < p[1] < D.MAP_H + 10):
            continue
        if p[1] > D.HW_CUT_ABOVE_Y:
            kind = "cut"
        elif p[1] < D.HW_EMB_BELOW_Y:
            kind = "emb"
        else:
            continue
        for sgn in (1, -1):
            if kind == "emb":       # high at the deck edge, pointing outward
                base, tip = p + n * sgn * (D.HW_DECK_HALF + 0.5), p + n * sgn * (D.HW_DECK_HALF + 9.5)
            else:                   # high at the outer edge, pointing in toward the deck
                base, tip = p + n * sgn * (full - 0.5), p + n * sgn * (full - 9.5)
            t = np.array([-n[1], n[0]]) * 1.8
            add_poly(ax, [base + t, base - t, tip], 6.1, fc=C["tick"], ec="none")
    stroke(ax, hw, 6.2, "#2B2E33", S.lw(2 * D.HW_DECK_HALF + 1.2), cap="butt")
    stroke(ax, hw, 6.3, C["deck"], S.lw(2 * D.HW_DECK_HALF - 0.6), cap="butt")
    stroke(ax, hw, 6.4, "#C9CDD2", S.lw(1.2), cap="butt")                                   # median barrier
    for off in (-11.0, -5.5, 5.5, 11.0):
        stroke(ax, G.offset(hw, off), 6.4, "#E8E8E8", S.lw(0.35), ls=(0, (6, 6)), cap="butt")
    for off in (-14.5, 14.5):
        stroke(ax, G.offset(hw, off), 6.4, "#E8E8E8", S.lw(0.35), cap="butt")
    # stalled traffic
    rng = np.random.default_rng(7)
    stations = resample(hw, 31.0)
    ou = [X["cross"]["O1"]["at"], X["cross"]["U1"]["at"]]
    for k, p in enumerate(stations):
        if not (8 < p[0] < D.MAP_W and 8 < p[1] < D.MAP_H - 8):
            continue
        if min(np.linalg.norm(p - o) for o in ou) < 34:
            continue
        d = G.direction_at(hw, p)
        nrm1 = np.array([-d[1], d[0]])
        for lane in rng.choice([-11.0, -5.5, 0.0, 5.5, 11.0], size=2, replace=False):
            if lane == 0.0:
                continue
            truck = rng.random() < 0.22
            L, Wd = (12.0, 2.8) if truck else (5.2, 2.5)
            c = p + nrm1 * lane + d * rng.uniform(-8, 8)
            col = "#EFE9DA" if truck else CAR_COLS[int(rng.integers(len(CAR_COLS)))]
            add_poly(ax, G.oriented_rect(c[0], c[1], L, Wd, d), 6.5, fc=col, ec="#15171A", lw=0.7)
    # jackknifed lorry (embankment section) - a landmark and the big piece of deck cover
    c = np.array([G.x_at_y(hw, D.HW_LORRY_Y), D.HW_LORRY_Y])
    d = G.direction_at(hw, c)
    rot = np.array([[math.cos(0.9), -math.sin(0.9)], [math.sin(0.9), math.cos(0.9)]]) @ d
    add_poly(ax, G.oriented_rect(c[0] - 3, c[1] + 2, 14, 2.8, rot), 6.6, fc="#F0E6CF", ec="#2B2E33", lw=0.6)
    add_poly(ax, G.oriented_rect(c[0] + 6, c[1] - 6, 5, 2.6, d), 6.6, fc="#E0A15A", ec="#2B2E33", lw=0.6)
    # gantries
    for gy in D.HW_GANTRY_Y:
        p = np.array([G.x_at_y(hw, gy), gy])
        d = G.direction_at(hw, p)
        n = np.array([-d[1], d[0]])
        a, b = p + n * (D.HW_DECK_HALF + 2), p - n * (D.HW_DECK_HALF + 2)
        stroke(ax, [a, b], 6.7, "#1B4F8F", S.lw(2.2), cap="butt")
        stroke(ax, [a, b], 6.71, "#FFFFFF", S.lw(0.5), cap="butt", ls=(0, (3, 3)))


def draw_roads(ax, X, S, which):
    widths = dict(main=(9.0, 1.6), street=(6.5, 1.2), gravel=(4.0, 1.0))
    for rid, r in X["roads"].items():
        if (which == "old_road") != (rid == "OLD_ROAD"):
            continue
        w, case = widths[r["kind"]]
        col, ccol = C[r["kind"]], C[r["kind"] + "_case"]
        stroke(ax, r["line"], 7, ccol, S.lw(w + case))
        stroke(ax, r["line"], 7.1, col, S.lw(w))
        if r["kind"] == "main":
            stroke(ax, r["line"], 7.2, "#F2F2F2", S.lw(0.3), ls=(0, (8, 8)), cap="butt")


def draw_paths(ax, X, S):
    for p in D.PATHS + [dict(kind=t["kind"], pts=t["line"]) for t in X["tow"]]:
        P = G.catmull_rom(p["pts"], 8) if len(p["pts"]) > 2 else np.asarray(p["pts"], float)
        if p["kind"] == "cover":
            stroke(ax, P, 7.5, "white", 3.4, alpha=0.6)
            stroke(ax, P, 7.6, C["cover"], 2.2, ls=(0, (0.1, 2.2)))
        else:
            stroke(ax, P, 7.5, C["field"], 1.4, ls=(0, (4, 2.5)), cap="butt")


def draw_crossings(ax, X, S):
    cr = X["cross"]
    # road + dirt bridge parapets
    for cid, w in (("C2", 13.0), ("C1", 4.6)):
        c = cr[cid]
        n = np.array([-c["dir"][1], c["dir"][0]])
        for sgn in (1, -1):
            a = c["a"] + n * sgn * (w / 2 + 0.6)
            b = c["b"] + n * sgn * (w / 2 + 0.6)
            stroke(ax, [a, b], 8, "#1B1D21", S.lw(1.0), cap="butt")
    # weir: concrete sill, gates, catwalk
    c = cr["C3"]
    n = np.array([-c["dir"][1], c["dir"][0]])
    add_poly(ax, G.oriented_rect(c["at"][0], c["at"][1], c["span"] + 2, 5.0, c["dir"]), 8, fc="#A4A7AB",
             ec="#2B2E33", lw=0.8)
    for k in range(-3, 4):
        p = c["at"] + c["dir"] * k * 5.6
        add_poly(ax, G.oriented_rect(p[0], p[1], 2.2, 5.6, c["dir"]), 8.1, fc="#3D4148", ec="none")
    stroke(ax, [c["a"] + n * 3.6, c["b"] + n * 3.6], 8.2, "#F4F4F4", S.lw(1.4), cap="butt")
    # white water below the weir
    for k in range(-3, 4):
        p = c["at"] + c["dir"] * k * 5.6 - n * 7
        stroke(ax, [p, p - n * 7], 5.4, "white", S.lw(0.8), alpha=0.8)
    # underpass: tunnel walls drawn dashed over the deck
    u = cr["U1"]
    n = np.array([-u["dir"][1], u["dir"][0]])
    for sgn in (1, -1):
        stroke(ax, [u["a"] + n * sgn * 6.2, u["b"] + n * sgn * 6.2], 8.3, "#F7E27A", S.lw(1.3), ls=(0, (3, 2)),
               cap="butt")
    # overpass parapets
    o = cr["O1"]
    n = np.array([-o["dir"][1], o["dir"][0]])
    for sgn in (1, -1):
        stroke(ax, [o["a"] + n * sgn * 3.2, o["b"] + n * sgn * 3.2], 8.3, "#1B1D21", S.lw(1.0), cap="butt")


def draw_structures(ax, X, S):
    for s in D.STRUCTURES:
        st = s["style"]
        if "circle" in s:
            cx, cy, r = s["circle"]
            if st == "tank":
                ax.add_patch(Circle((cx, cy), r, fc=C["tank"], ec=C["tank_edge"], lw=1.0, zorder=9))
                if r > 6:
                    ax.add_patch(Circle((cx, cy), r * 0.18, fc=C["tank_edge"], ec="none", zorder=9.1))
                    stroke(ax, [(cx - r, cy), (cx + r, cy)], 9.1, C["tank_edge"], 0.7)
            elif st == "egg":
                ax.add_patch(Circle((cx, cy), r, fc="#D9DEE3", ec="#3A3F46", lw=1.2, zorder=9))
                ax.add_patch(Circle((cx - r * 0.25, cy + r * 0.25), r * 0.35, fc="white", ec="none", zorder=9.1))
            elif st == "heap":
                ax.add_patch(Circle((cx, cy), r, fc=C["pit"], ec="#7A5F38", lw=0.6, zorder=9))
            continue
        x0, y0, x1, y1 = s["rect"]
        kw = dict(zorder=9)
        if st == "bldg":
            kw.update(fc=C["bldg"], ec="#202328", lw=0.6)
        elif st == "low":
            kw.update(fc="#9A9FA6", ec="#3A3F46", lw=0.5)
        elif st == "vehicle":
            kw.update(fc="#F2F2F2", ec="#202328", lw=0.6)
        elif st == "canopy":
            kw.update(fc="#C9CBD0", ec="#3A3F46", lw=0.6, hatch="xx")
        elif st == "shell":
            kw.update(fc="#C4C0B6", ec="#202328", lw=0.9, hatch="++")
        elif st == "deck":
            kw.update(fc=C["rampdeck"], ec=C["rampdeck_edge"], lw=0.7)
        elif st == "ramp":
            kw.update(fc="#DCD5EA", ec=C["rampdeck_edge"], lw=0.7, hatch="---")
        elif st == "skip":
            kw.update(fc=C["skip"], ec="#5A3010", lw=0.4)
        elif st == "plot":
            kw.update(fc=C["plot"], ec="#7A7466", lw=0.6, hatch="..")
        elif st == "pit":
            kw.update(fc=C["pit"], ec="#6E5530", lw=0.6, hatch="\\\\")
        elif st == "basin":
            kw.update(fc=C["tank"], ec=C["tank_edge"], lw=1.0)
        elif st == "bed":
            kw.update(fc="#B9A47E", ec="#6E5530", lw=0.5)
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, **kw))
        if st == "basin":
            for k in range(1, 4):
                yy = y0 + k * (y1 - y0) / 4
                stroke(ax, [(x0, yy), (x1, yy)], 9.1, C["tank_edge"], 0.7)
        if st == "shell":
            for k in range(1, 4):
                xx = x0 + k * (x1 - x0) / 4
                stroke(ax, [(xx, y0), (xx, y1)], 9.1, "#202328", 0.9)
    # crane jibs
    for lm in D.LANDMARKS:
        if "jib_to" in lm:
            stroke(ax, [lm["counter"], lm["at"], lm["jib_to"]], 9.5, "#C88200", S.lw(1.6))
            ax.add_patch(Rectangle((lm["at"][0] - 3, lm["at"][1] - 3), 6, 6, fc="#C88200", ec="#202328",
                                   lw=0.6, zorder=9.6))


def draw_tdm(ax, X, S):
    x0, y0, x1, y1 = D.TDM["rect"]
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="none", ec="white", lw=4.2, zorder=20))
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="none", ec=C["tdm"], lw=2.4, ls=(0, (5, 3)), zorder=20.1))


def draw_ziplines(ax, X, S):
    for z in D.ZIPLINES:
        stroke(ax, [z["a"], z["b"]], 19, C["zip"], 1.6, ls=(0, (1, 1.6)))
        for p in (z["a"], z["b"]):
            ax.plot([p[0]], [p[1]], marker="o", ms=4, mfc=C["zip"], mec="white", mew=0.6, zorder=19.1)


def draw_sightlines(ax, X, S, ids=None):
    for s in D.SIGHTLINES:
        if ids and s["id"] not in ids:
            continue
        a, b = X["sight"][s["id"]]
        stroke(ax, [a, b], 21, "white", 2.6, alpha=0.7)
        stroke(ax, [a, b], 21.1, C["sight"], 1.2)
        ax.plot([a[0]], [a[1]], marker="o", ms=3.6, mfc=C["sight"], mec="white", mew=0.5, zorder=21.2)
        ax.plot([b[0]], [b[1]], marker="o", ms=3.6, mfc=C["sight"], mec="white", mew=0.5, zorder=21.2)


def sight_len(X, s):
    a, b = X["sight"][s["id"]]
    return float(np.linalg.norm(b - a))


def choke_at(X, k):
    return X["cross"][k["at"]]["at"] if isinstance(k["at"], str) else np.asarray(k["at"], float)


def draw_chokepoints(ax, X, S):
    for k in D.CHOKEPOINTS:
        p = choke_at(X, k)
        ax.add_patch(Circle(p, k["r"], fc="none", ec="white", lw=4.0, zorder=22))
        ax.add_patch(Circle(p, k["r"], fc="none", ec=C["choke"], lw=2.2, zorder=22.1))


def draw_landmarks(ax, X, S):
    for lm in D.LANDMARKS:
        x, y = lm["at"]
        ax.plot([x], [y], marker="*", ms=15, mfc="#FFC72C", mec="#5A3A00", mew=0.9, zorder=23)
    hw = X["hw"]
    for gy in D.HW_GANTRY_Y:
        x = G.x_at_y(hw, gy)
        ax.plot([x], [gy], marker="*", ms=15, mfc="#FFC72C", mec="#5A3A00", mew=0.9, zorder=23)


def draw_spawns(ax, X, S):
    for s in D.SPAWNS:
        x0, y0, x1, y1 = s["rect"]
        if s.get("only16"):
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=C["spawn"], ec="none", alpha=0.22, zorder=24))
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="none", ec="#0B3FA8", lw=1.6, ls=(0, (3, 2)),
                                   zorder=24.1))
            continue
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=C["spawn"], ec="#0B3FA8", lw=1.4, alpha=0.55,
                               zorder=24))
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="none", ec="#0B3FA8", lw=1.4, zorder=24.1))


def draw_extracts(ax, X, S):
    for e in D.EXTRACTS:
        p = X["ext"][e["id"]]
        ax.add_patch(Circle(p, D.EXTRACT_R, fc=C["extract"], ec="white", lw=3.2, alpha=0.95, zorder=25))
        ax.add_patch(Circle(p, D.EXTRACT_R, fc=C["extract"], ec=C["extract_dark"], lw=1.6, zorder=25.1))
        text(ax, p[0], p[1], e["id"], size=7.5, color="white", weight="bold", z=25.2, halo=False)


def draw_edge(ax):
    ax.add_patch(Rectangle((0, 0), D.MAP_W, D.MAP_H, fc="none", ec="#111111", lw=2.2, zorder=30))


def draw_grid(ax, ext, step, label_step, fs=7.5):
    x0, x1, y0, y1 = ext
    for x in np.arange(math.ceil(x0 / step) * step, x1 + 0.1, step):
        major = abs(x % label_step) < 1e-6
        ax.plot([x, x], [y0, y1], color=C["grid"], lw=0.8 if major else 0.45, alpha=0.30 if major else 0.16,
                zorder=12)
    for y in np.arange(math.ceil(y0 / step) * step, y1 + 0.1, step):
        major = abs(y % label_step) < 1e-6
        ax.plot([x0, x1], [y, y], color=C["grid"], lw=0.8 if major else 0.45, alpha=0.30 if major else 0.16,
                zorder=12)
    ax.set_xticks(np.arange(math.ceil(x0 / label_step) * label_step, x1 + 0.1, label_step))
    ax.set_yticks(np.arange(math.ceil(y0 / label_step) * label_step, y1 + 0.1, label_step))
    ax.tick_params(labelsize=fs, length=3, top=True, right=True, labeltop=True, labelright=True)


# ================================================================== labels (main map)
def poi_label(ax, x, y, name, tier, sub=None, size=10.5, z=45, renderer=None, ppm=PX_PER_M):
    """Bold name + loot-tier badge, centred on (x, y); optional sub line below."""
    t = text(ax, x, y, name, size=size, weight="bold", z=z, ha="center")
    badge = f"L{tier}"
    if renderer is not None:
        bb = t.get_window_extent(renderer=renderer)
        w = bb.width / ppm
        bx = x + w / 2 + 3.0 / ppm * 10
        ax.text(bx, y, badge, fontsize=size * 0.78, weight="bold", color="white", ha="left", va="center",
                zorder=z + 1, bbox=dict(boxstyle="round,pad=0.22", fc=TIER[tier], ec="white", lw=0.8))
    if sub:
        text(ax, x, y - size * 1.25 * 2.0 / ppm * 2.2, sub, size=size * 0.72, z=z, color="#33373D",
             style="italic")
    return t


def hw_point(X, y, off=0.0):
    """Point on the highway at latitude y, offset sideways (+ = left of travel, i.e. west/south-west side)."""
    hw = X["hw"]
    p = np.array([G.x_at_y(hw, y), y])
    d = G.direction_at(hw, p)
    n = np.array([-d[1], d[0]])
    ang = math.degrees(math.atan2(d[1], d[0]))
    if ang > 90:
        ang -= 180
    elif ang <= -90:
        ang += 180
    return p + n * off, ang


def draw_main_labels(ax, X, R):
    ppm = PX_PER_M
    P = D.P
    W, H = D.MAP_W, D.MAP_H
    river = X["river"]
    # --- POIs (name + loot badge + sub line)
    L = {
        "WORKSITE": P("WS", 300, 684), "FARM": P("FARM", 172, 350), "HUT": P("HUT", 200, 836),
        "CONTAINER": P("CP", 646, 600), "PLANT": P("PLANT", 598, 372), "SUBSTATION": P("SUB", 890, 222),
        "STORAGE": P("STO", 882, 762), "GAS": P("GAS", 952, 560), "SLUICE": (800, 94),
    }
    for p in D.POIS:
        if p["id"] == "SHOWHOME":
            continue
        x, y = L[p["id"]]
        poi_label(ax, x, y, p["label"], p["tier"], p["sub"] or None, size=10.0 if p["kind"] != "micro" else 8.5,
                  renderer=R, ppm=ppm)
    x, y = P("WS", 290, 476)
    poi_label(ax, x, y, "SHOWHOME", 4, None, size=10.5, renderer=R, ppm=ppm)
    x, y = P("WS", 290, 462)
    text(ax, x, y, "TDM / FFA cut-out 80 × 60 m (dashed)", size=7.2, color=C["tdm"], weight="bold")

    # --- small feature labels
    def tow(y, side):
        return G.x_at_y(river, y) + (D.TOWPATH_OFF if side == "E" else -D.TOWPATH_OFF)

    small = [
        (*P("WS", 212, 548), "site office"), (*P("WS", 372, 536), "material yard"), (*P("WS", 306, 623), "the Shells"),
        (*P("WS", 370, 596), "Crane 1"), (*P("WS", 240, 638), "Crane 2"), (*P("WS", 380, 574), "back road"),
        (*P("WS", 218, 484), "front street"),
        (422, 404, "tree nursery"), (*P("MAP", 134, 152), "South Woods"), (*P("MAP", 90, 760), "North Woods"),
        (*P("MAP", 562, 830), "Riverside Woods"), (772, 528, "plant woods"), (*P("MAP", 803, 196), "pylon woods"),
        (*P("FARM", 240, 300), "silo"), (*P("FARM", 200, 262), "courtyard"),
        (*P("PLANT", 762, 254), "digester eggs"), (*P("PLANT", 643, 272), "aeration"),
        (*P("PLANT", 648, 162), "sludge beds"), (*P("PLANT", 527, 312), "pump house"),
        (*P("PLANT", 607, 236), "clarifiers"), (*P("GAS", 954, 470), "price pylon"),
        (172, 472, "Old Road"), (782, 547, "Old Road"), (*P("MAP", 602, 772), "Forest Track"),
        (tow(470, "W") - 2, 470, "towpath"), (tow(330, "W") - 10, 345, "poplar row"),
        (120, 610, "field lane"), (1012, 512, "field lane"),
    ]
    for x, y, s in small:
        text(ax, x, y, s, size=7.0, color="#30343A", style="italic", z=44)
    text(ax, 288, 533, "chapel", size=7.0, color="#30343A", style="italic", z=44, ha="left")
    for f in D.FIELD_STRUCTURES:
        x0, y0, x1, y1 = f["rect"]
        dx, dy = f.get("lab", (0, y1 - y0 + 8))
        text(ax, (x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy, f["name"], size=6.6, color="#3A3020", style="italic", z=44)
    x, y = P("PLANT", 707, 316)
    text(ax, x, y, "control\nbldg", size=6.6, color="white", weight="bold", halo=False, z=44)
    text(ax, 430, 266, "drainage ditch", size=6.8, color="#2E6E99", style="italic", z=44, rotation=-5)
    text(ax, 1000, 236, "drainage ditch", size=6.8, color="#2E6E99", style="italic", z=44, rotation=-10)
    text(ax, 390, 156, "power line", size=6.8, color="#444", style="italic", z=44, rotation=7)

    # --- highway (labels placed on the deck and the slopes)
    p, ang = hw_point(X, 500, 0.0)
    text(ax, p[0], p[1], "HIGHWAY", size=10.5, weight="bold", rotation=ang, z=45, color="white", halo=False)
    p, ang = hw_point(X, 850, 25.0)
    text(ax, p[0], p[1], "cutting −6 m", size=7.0, rotation=ang, z=44, style="italic")
    p, ang = hw_point(X, 390, -25.0)
    text(ax, p[0], p[1], "embankment +6 m", size=7.0, rotation=ang, z=44, style="italic")
    p, _ = hw_point(X, D.HW_LORRY_Y, -31.0)
    text(ax, p[0] - 2, p[1], "jackknifed lorry", size=6.8, z=44, style="italic", ha="right")
    p, _ = hw_point(X, D.HW_GANTRY_Y[0], -30.0)
    text(ax, p[0] - 4, p[1], "gantry", size=6.8, z=44, style="italic", ha="right")
    hx = G.x_at_y(X["hw"], H)
    text(ax, hx, H + 24, "player_clip across the deck", size=6.6, z=31, color="white", halo=False)
    text(ax, W + 22, hw_y_at_east(X), "clip", size=6.6, z=31, rotation=-90, color="white", halo=False)

    # --- crossings
    cr = X["cross"]
    cl = dict(C1=(-74, 24, "center", "C1 DIRT BRIDGE", "out of the way, forest cover"),
              C2=(0, -42, "center", "C2 ROAD BRIDGE", "fast, exposed"),
              C3=(-32, -12, "right", "C3 WEIR", "single-file catwalk"),
              U1=(-52, -54, "center", "U1 UNDERPASS", "Old Road under the highway"),
              O1=(-56, 42, "center", "O1 OVERPASS", "farm bridge over the cutting"))
    for cid, (dx, dy, ha, name, sub) in cl.items():
        p = cr[cid]["at"]
        text(ax, p[0] + dx, p[1] + dy, name, size=8.8, weight="bold", color="#0E2A47", z=46, ha=ha)
        text(ax, p[0] + dx, p[1] + dy - 12, sub, size=7.0, color="#0E2A47", style="italic", z=46, ha=ha)
    text(ax, G.x_at_y(river, 1050) - 40, 1050, "RIVER", size=10, weight="bold", color="#1F5F8B", rotation=-75,
         z=45)
    y = 735
    text(ax, G.x_at_y(river, y) + 38, y, "RIVER (40 m, not crossable)", size=7.4, color="#1F5F8B", rotation=-60,
         z=45, style="italic")

    # --- spawns
    sp = dict(S1=(32, 720, 90), S2=(375, 28, 0), S3=(405, 1070, 0), S4=(1145, 1070, 0), S5=(1268, 740, 90),
              S6=(1080, 28, 0), S7=(32, 300, 90), S8=(700, 1070, 0))
    for s in D.SPAWNS:
        x, y, rot = sp[s["id"]]
        side = "west side" if s["side"] == "W" else "east side"
        extra = ", 16 players only" if s.get("only16") else ""
        text(ax, x, y, f"{s['id']} {s['name']}  ({side}{extra})", size=8.2, weight="bold", color="#0B3FA8",
             rotation=rot, z=46)

    # --- extracts
    x5 = X["ext"]["X5"]
    xl = dict(X1=(14, 1029, "left"), X2=(*P("WS", 160, 526), "right"), X3=(*P("SLU", 616, 38), "left"),
              X4=(1290, 114, "right"), X5=(x5[0] + 54, x5[1] + 2, "left"), X6=(141, 30, "left"))
    for e in D.EXTRACTS:
        x, y, ha = xl[e["id"]]
        who = {"E": "E-spawns", "W": "W-spawns", "ALL": "all"}[e["for_side"]]
        text(ax, x, y, f"{e['id']} {e['name'].upper()}", size=8.4, weight="bold", color=C["extract_dark"], ha=ha,
             z=46)
        text(ax, x, y - 12, f"{e['cond']} · {who}", size=7.0, color=C["extract_dark"], ha=ha, z=46)

    # --- chokepoint ids (angle of the label around the circle) and sightline ids
    kang = dict(K1=40, K2=40, K3=140, K4=40, K5=40, K6=-40, K7=40, K8=40, K9=140)
    for k in D.CHOKEPOINTS:
        p = choke_at(X, k)
        ang = math.radians(kang[k["id"]])
        q = p + np.array([math.cos(ang), math.sin(ang)]) * (k["r"] + 4)
        text(ax, q[0], q[1], k["id"], size=7.6, weight="bold", color=C["choke"], z=47,
             ha="left" if math.cos(ang) >= 0 else "right")
    soff = dict(L1=(0.62, 4, "left"), L2=(0.5, -4, "right"), L3=(0.35, 3, "left"), L4=(0.5, 4, "left"),
                L5=(0.5, 4, "left"), L6=(0.45, 5, "left"), L7=(0.45, -4, "right"), L8=(0.62, 4, "left"),
                L9=(0.6, 4, "left"), L10=(0.8, 4, "left"), L11=(0.45, 4, "left"))
    for s in D.SIGHTLINES:
        a, b = X["sight"][s["id"]]
        t, dx, ha = soff[s["id"]]
        m = a + (b - a) * t
        ln = np.linalg.norm(b - a)
        text(ax, m[0] + dx, m[1] + 3, f"{s['id']} {ln:.0f} m", size=6.8, weight="bold", color=C["sight"], z=47,
             ha=ha)

    # --- boundary bands
    rx = G.x_at_y(river, H)
    hy = hw_y_at_east(X)
    text(ax, -20, 550, "BOUNDARY: dense West Woods forest", size=7.6, rotation=90, color="white", weight="bold",
         halo=False, z=31)
    text(ax, 290, H + 20, "BOUNDARY: dense North Woods forest", size=7.6, color="white", weight="bold", halo=False,
         z=31)
    text(ax, (hx + 32 + W) / 2, H + 20, "BOUNDARY: NE woods + deer fence", size=7.6, color="white", weight="bold",
         halo=False, z=31)
    text(ax, W + 20, (hy + H) / 2 + 60, "BOUNDARY: industrial-estate palisade fence", size=7.6, rotation=-90,
         weight="bold", z=31)
    text(ax, W + 20, hy / 2, "dense woods", size=7.6, rotation=-90, color="white", weight="bold", halo=False, z=31)
    text(ax, 380, -34, "BOUNDARY: flood dike (+5 m crest, fenced); ticks point downhill", size=7.6, weight="bold",
         z=31)
    oy = G.x_at_y(np.asarray(X["roads"]["OLD_ROAD"]["line"])[:, ::-1], W)     # y of the Old Road at the east edge
    text(ax, W + 22, oy, "roadblock", size=6.6, rotation=-90, z=31)
    text(ax, G.x_at_y(river, 0.0), -34, "dike sluice", size=6.6, z=31)
    text(ax, rx, H + 24, "river: clip", size=6.6, z=31, color="white", halo=False)


def scale_bar(ax, x, y, length=200, h=6, fs=7.5):
    n = 4
    for i in range(n):
        ax.add_patch(Rectangle((x + i * length / n, y), length / n, h, fc=C["ink"] if i % 2 == 0 else "white",
                               ec=C["ink"], lw=0.8, zorder=50))
    for i in range(n + 1):
        text(ax, x + i * length / n, y + h + 7, f"{i * length / n:.0f}", size=fs, z=50)
    text(ax, x + length + 14, y + h / 2, "m", size=fs, z=50, ha="left")


def north_arrow(ax, x, y, size=36):
    add_poly(ax, [(x, y + size), (x - size * 0.32, y - size * 0.15), (x, y + size * 0.12)], 50, fc=C["ink"],
             ec=C["ink"], lw=0.8)
    add_poly(ax, [(x, y + size), (x + size * 0.32, y - size * 0.15), (x, y + size * 0.12)], 50, fc="white",
             ec=C["ink"], lw=0.8)
    text(ax, x, y + size + 12, "N", size=11, weight="bold", z=50)


# ================================================================== inset (Showhome hot zone)
def draw_inset(fig, X, R, rect_px):
    x0, x1, y0, y1 = INSET_EXT
    ax = fig.add_axes(px_rect(rect_px))
    S = Scale(INSET_PX_PER_M)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ext = (x0, x1, y0, y1)
    rng = np.random.default_rng(3)
    draw_base(ax, X, S, ext)
    draw_fields(ax, X, S)
    draw_forests(ax, X, S, rng, spacing=7.0, ext=ext)
    draw_poi_zones(ax, X, S)
    draw_details(ax, X, S)
    draw_river(ax, X, S)
    draw_roads(ax, X, S, "old_road")
    draw_roads(ax, X, S, "other")
    draw_paths(ax, X, S)
    draw_crossings(ax, X, S)
    draw_structures(ax, X, S)
    draw_tdm(ax, X, S)
    draw_ziplines(ax, X, S)
    draw_sightlines(ax, X, S, ids={"L7", "L8"})
    draw_chokepoints(ax, X, S)
    draw_landmarks(ax, X, S)
    draw_extracts(ax, X, S)
    draw_grid(ax, ext, 10, 50, fs=7)
    ax.tick_params(labeltop=False, labelright=False)

    tx0, ty0, tx1, ty1 = D.TDM["rect"]

    def w(x, y):                       # v0.1 inset coordinates -> v0.2 (the inset moved with Showhome)
        return D.P("WS", x, y)

    # invisible walls (player_clip) on the 4 edges
    for (a, b) in [((tx0, ty0), (tx1, ty0)), ((tx0, ty0), (tx0, ty1)), ((tx1, ty0), (tx1, ty1)),
                   ((tx0, ty1), (tx1, ty1))]:
        stroke(ax, [a, b], 20.5, "#E040FB", 4.0, alpha=0.55, cap="butt")
    text(ax, *w(290, 497.2), "player_clip: ROAD SIDE (street open, visible)", size=7.0, color=C["tdm"],
         weight="bold", z=48)
    text(ax, *w(246.5, 530), "clip: FIELD EDGE (Sage hedge)", size=7.0, color=C["tdm"], weight="bold", rotation=90,
         z=48)
    text(ax, *w(333.5, 530), "clip: FIELD EDGE (Clay hedge)", size=7.0, color=C["tdm"], weight="bold",
         rotation=-90, z=48)
    text(ax, *w(290, 563.8), "clip: PLOT EDGE (site fence behind carports)", size=7.0, color=C["tdm"],
         weight="bold", z=48)
    text(ax, *w(269, 526), "SAGE\nhouse", size=7.2, color="white", weight="bold", halo=False, z=48)
    text(ax, *w(311, 526), "CLAY\nhouse", size=7.2, color="white", weight="bold", halo=False, z=48)
    text(ax, *w(297, 521), "truck", size=6.5, z=48, ha="left")
    text(ax, *w(290, 552.5), "carports", size=6.2, z=48)
    text(ax, *w(256, 548), "garden", size=6.4, z=48, style="italic")
    text(ax, *w(324, 548), "garden", size=6.4, z=48, style="italic")
    text(ax, *w(256, 528), "A", size=10, weight="bold", color="#00806F", z=48)
    text(ax, *w(324, 528), "B", size=10, weight="bold", color="#C2361B", z=48)

    # edge hand-off arrows, with the distances measured on the v0.2 layout
    mid_n, mid_e = np.array([(tx0 + tx1) / 2, ty1]), np.array([tx1, (ty0 + ty1) / 2])
    mid_s, mid_w = np.array([(tx0 + tx1) / 2, ty0]), np.array([tx0, (ty0 + ty1) / 2])
    cr = X["cross"]
    s3 = next(s for s in D.SPAWNS if s["id"] == "S3")["rect"]
    s1 = next(s for s in D.SPAWNS if s["id"] == "S1")["rect"]
    d_c1 = np.linalg.norm(cr["C1"]["at"] - mid_n)
    d_s3 = np.linalg.norm(np.array([(s3[0] + s3[2]) / 2, s3[1]]) - mid_n)
    d_c2 = np.linalg.norm(cr["C2"]["at"] - mid_e)
    d_bh = np.linalg.norm(np.asarray(D.P("MAP", 460, 460)) - mid_s)
    d_x2 = np.linalg.norm(X["ext"]["X2"] - mid_w)
    d_s1 = np.linalg.norm(np.array([s1[2], (s1[1] + s1[3]) / 2]) - mid_w)
    arrows = [
        (w(290, 562), w(290, 648), f"N edge → back road → the Shells, Crane 1; forest path\n"
                                   f"→ C1 Dirt Bridge (~{d_c1:.0f} m), S3 North Woods (~{d_s3:.0f} m)",
         w(290, 656), "center", "bottom"),
        (w(331, 524), w(380, 492), f"E edge → material yard →\nopen field → C2 Road Bridge\n(~{d_c2:.0f} m)",
         w(372, 486), "left", "top"),
        (w(290, 499), w(290, 476), f"S edge → front street (open)\n→ Old Road, Bridgehead W (~{d_bh:.0f} m)",
         w(290, 472), "center", "top"),
        (w(249, 524), w(190, 486), f"W edge → site office → West Gate\n(X2, ~{d_x2:.0f} m) → West Fields (S1, ~{d_s1:.0f} m)",
         w(166, 480), "left", "top"),
    ]
    for (a, b, s, tp, ha, va) in arrows:
        ax.annotate("", xy=b, xytext=a, zorder=49,
                    arrowprops=dict(arrowstyle="-|>", color="#111", lw=2.0, mutation_scale=16))
        ax.text(tp[0], tp[1], s, fontsize=7.6, ha=ha, va=va, zorder=49, weight="bold", color="#111", clip_on=True,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#555", lw=0.6, alpha=0.94))
    text(ax, *w(184, 522), "X2 cement truck", size=7, weight="bold", color=C["extract_dark"], z=48)
    for lm, (dx, dy) in (("CRANE1", (12, 8)), ("CRANE2", (-14, 8))):
        p = next(l for l in D.LANDMARKS if l["id"] == lm)["at"]
        text(ax, p[0] + dx, p[1] + dy, "Crane " + lm[-1], size=7, weight="bold", z=48)
    text(ax, *w(290, 603), "the Shells (3 floors, scaffold)", size=7, weight="bold", z=48)
    text(ax, *w(212, 545), "site office", size=7, weight="bold", z=48)
    text(ax, *w(372, 538), "material yard", size=7, weight="bold", z=48)
    text(ax, *w(416, 548), "pit", size=6.6, z=48)
    text(ax, *w(358, 649), "pit", size=6.6, z=48)
    text(ax, *w(252, 652), "pit", size=6.6, z=48)
    text(ax, *w(360, 579), "plots", size=6.6, z=48)
    text(ax, *w(201, 600), "plots", size=6.6, z=48)
    text(ax, *w(440, 506), "L8 → C2", size=7, weight="bold", color=C["sight"], z=48)
    text(ax, *w(296, 580), "L7", size=7, weight="bold", color=C["sight"], z=48, ha="left")
    text(ax, *w(300, 509), "K6", size=7, weight="bold", color=C["choke"], z=48, ha="left")
    for sp in ax.spines.values():
        sp.set_linewidth(1.4)
    return ax


# ================================================================== legend panel
def px_rect(r):
    x, y, w, h = r
    return [x / FIG_W, y / FIG_H, w / FIG_W, h / FIG_H]


def draw_panel(fig, X, R, T):
    px0, py0, pw, ph = PANEL_PX
    ax = fig.add_axes(px_rect(PANEL_PX))
    ax.set_xlim(0, pw)
    ax.set_ylim(0, ph)
    ax.axis("off")
    k = 72.0 / DPI   # points per pixel

    def t(x, y, s, size=8.6, **kw):
        kw.setdefault("va", "center")
        kw.setdefault("ha", "left")
        return ax.text(x, y, s, fontsize=size, color=kw.pop("color", C["ink"]), zorder=10, **kw)

    def sample_line(x, y, color, w, ls="-", case=None, cap="butt", length=70):
        if case:
            ax.plot([x, x + length], [y, y], color=case[0], lw=case[1], solid_capstyle="butt", zorder=5)
        ax.plot([x, x + length], [y, y], color=color, lw=w, ls=ls, solid_capstyle=cap, dash_capstyle=cap,
                zorder=6)

    def sample_box(x, y, fc, ec="none", hatch=None, alpha=1.0, w=70, h=22, lw=1.0):
        ax.add_patch(Rectangle((x, y - h / 2), w, h, fc=fc, ec=ec, hatch=hatch, alpha=alpha, lw=lw, zorder=5))

    top = ph - 10
    t(0, top - 12, "LEGEND", 12, weight="bold")
    rows1 = [
        ("box", dict(fc=C["forest"], ec=C["forest_edge"]), "forest / woods (concealed movement)"),
        ("box", dict(fc=C["arable"], ec=C["stripe"], hatch="///"), "open field, arable (meadow = plain green)"),
        ("box", dict(fc=C["worksite"], ec="#B08A52"), "worksite ground (dirt, plots, pits)"),
        ("river", None, "river: 40 m water, banks; not crossable"),
        ("hw", None, "highway deck (2×3 lanes, stalled traffic)"),
        ("wedge", None, "slope ticks point downhill: embankment / cutting"),
        ("line", dict(color=C["main"], w=9 * PX_PER_M * k, case=(C["main_case"], 10.6 * PX_PER_M * k)),
         "main road (Old Road)"),
        ("line", dict(color=C["street"], w=6.5 * PX_PER_M * k, case=(C["street_case"], 7.7 * PX_PER_M * k)),
         "street / access road"),
        ("line", dict(color=C["gravel"], w=4 * PX_PER_M * k, case=(C["gravel_case"], 5 * PX_PER_M * k)),
         "gravel / site track / field lane"),
        ("line", dict(color=C["field"], w=1.4, ls=(0, (4, 2.5)), cap="butt"), "field path / towpath"),
        ("line", dict(color=C["cover"], w=2.2, ls=(0, (0.1, 2.2)), cap="round"),
         "cover route (forest path, poplar row)"),
        ("line", dict(color=C["hedge"], w=4 * PX_PER_M * k), "hedgerow (cover rhythm)"),
        ("line", dict(color=C["ditch"], w=1.6 * PX_PER_M * k), "drainage ditch (crouch cover)"),
        ("power", None, "power line + pylons"),
    ]
    rows2 = [
        ("poi", None, "POI zone (colour per POI) + loot tier"),
        ("tiers", None, ""),
        ("box", dict(fc=C["bldg"], ec="#202328"), "building / structure (simplified)"),
        ("cross", None, "crossing: C = river, U / O = highway"),
        ("box", dict(fc=C["spawn"], ec="#0B3FA8", alpha=0.6), "spawn zone (blue), S1–S6"),
        ("spawn16", None, "spawn zone used at 16 players only: S7, S8"),
        ("extract", None, "extract (green), X1–X6 + condition"),
        ("tdm", None, "TDM / FFA cut-out, 80 × 60 m"),
        ("sight", None, "key sightline (thin red), L1–L11"),
        ("choke", None, "chokepoint (red circle), K1–K9"),
        ("star", None, "landmark (cranes, eggs, gantries, ...)"),
        ("zip", None, "zipline (suggestion)"),
        ("edge", None, "playable edge (natural boundary outside)"),
        ("fence", None, "perimeter fence of a POI"),
        ("hay", None, "hay bales / stacks (field cover)"),
    ]
    y = top - 46
    dy = 33
    for col, rows in ((0, rows1), (1, rows2)):
        x = 0 if col == 0 else 660
        yy = y
        for kind, kw, label in rows:
            if kind == "box":
                sample_box(x, yy, **kw)
            elif kind == "line":
                sample_line(x, yy, **kw)
            elif kind == "river":
                sample_box(x, yy, C["water"], ec=C["water_edge"], h=20, lw=1.5)
                ax.plot([x, x + 70], [yy + 12, yy + 12], color=C["bank"], lw=2.5, zorder=4)
                ax.plot([x, x + 70], [yy - 12, yy - 12], color=C["bank"], lw=2.5, zorder=4)
            elif kind == "hw":
                sample_box(x, yy, C["deck"], ec="#2B2E33", h=22)
                ax.plot([x + 2, x + 68], [yy, yy], color="#E8E8E8", lw=0.6, ls=(0, (4, 4)), zorder=6)
                for cx in (x + 14, x + 44):
                    ax.add_patch(Rectangle((cx, yy + 3), 10, 4.5, fc="#B9C3CF", ec="#2B2E33", lw=0.4, zorder=7))
            elif kind == "wedge":
                sample_box(x, yy, C["slope"], h=22, w=32)
                ax.add_patch(Polygon([(x + 2, yy + 9), (x + 2, yy - 9), (x + 26, yy)], fc=C["tick"], zorder=6))
                sample_box(x + 38, yy, C["slope"], h=22, w=32)
                ax.add_patch(Polygon([(x + 68, yy + 9), (x + 68, yy - 9), (x + 44, yy)], fc=C["tick"], zorder=6))
            elif kind == "power":
                ax.plot([x, x + 70], [yy, yy], color=C["power"], lw=0.9, ls=(0, (8, 3, 1.5, 3)), zorder=5)
                ax.plot([x + 35], [yy], marker="X", ms=6.5, mfc="white", mec=C["power"], mew=1.2, zorder=6)
            elif kind == "poi":
                sample_box(x, yy, POI_FILL["PLANT"], alpha=0.3)
                sample_box(x, yy, "none", ec=POI_FILL["PLANT"], lw=1.6)
            elif kind == "tiers":
                for i, tr in enumerate((1, 2, 3, 4)):
                    ax.text(x + 4 + i * 62, yy, f"L{tr}", fontsize=8.4, weight="bold", color="white", va="center",
                            bbox=dict(boxstyle="round,pad=0.22", fc=TIER[tr], ec="white", lw=0.8), zorder=8)
                t(x + 250, yy, "loot tier: L1 low … L4 highest", 8.6)
                yy -= dy
                continue
            elif kind == "cross":
                sample_box(x, yy, C["water"], ec=C["water_edge"], h=20)
                ax.plot([x + 18, x + 52], [yy, yy], color=C["gravel"], lw=5, zorder=6)
                ax.plot([x + 18, x + 52], [yy + 4.5, yy + 4.5], color="#1B1D21", lw=1, zorder=7)
                ax.plot([x + 18, x + 52], [yy - 4.5, yy - 4.5], color="#1B1D21", lw=1, zorder=7)
            elif kind == "extract":
                ax.add_patch(Circle((x + 35, yy), 12, fc=C["extract"], ec=C["extract_dark"], lw=1.6, zorder=6))
                ax.text(x + 35, yy, "X", fontsize=7, color="white", weight="bold", ha="center", va="center",
                        zorder=7)
            elif kind == "tdm":
                ax.add_patch(Rectangle((x, yy - 11), 70, 22, fc="none", ec=C["tdm"], lw=2.4, ls=(0, (5, 3)),
                                       zorder=6))
            elif kind == "sight":
                ax.plot([x, x + 70], [yy, yy], color=C["sight"], lw=1.2, zorder=6, marker="o", ms=3.6,
                        markevery=[0, 1])
            elif kind == "choke":
                ax.add_patch(Circle((x + 35, yy), 12, fc="none", ec=C["choke"], lw=2.2, zorder=6))
            elif kind == "star":
                ax.plot([x + 35], [yy], marker="*", ms=15, mfc="#FFC72C", mec="#5A3A00", mew=0.9, zorder=6)
            elif kind == "zip":
                ax.plot([x, x + 70], [yy, yy], color=C["zip"], lw=1.6, ls=(0, (1, 1.6)), zorder=6)
            elif kind == "edge":
                ax.plot([x, x + 70], [yy, yy], color="#111", lw=2.2, zorder=6)
            elif kind == "fence":
                ax.plot([x, x + 70], [yy, yy], color=C["fence"], lw=0.9, ls=(0, (4, 2)), zorder=6)
            elif kind == "spawn16":
                sample_box(x, yy, C["spawn"], alpha=0.22)
                ax.add_patch(Rectangle((x, yy - 11), 70, 22, fc="none", ec="#0B3FA8", lw=1.6, ls=(0, (3, 2)),
                                       zorder=6))
            elif kind == "hay":
                for hx in (x + 22, x + 30, x + 38, x + 46):
                    ax.plot([hx], [yy], marker="o", ms=5, mfc=C["hay"], mec="#8A6A1E", mew=0.4, zorder=6)
            t(x + 84, yy, label, 8.6)
            yy -= dy
    ybot = y - dy * max(len(rows1), len(rows2)) - 6

    # ---------------- extracts table
    yy = ybot - 18
    t(0, yy, "EXTRACTS (green)", 11, weight="bold", color=C["extract_dark"])
    t(330, yy, "each player sees the shared ones + the set for their spawn side", 8.2, style="italic")
    yy -= 30
    cols = [0, 46, 196, 446, 560, 700]
    for cx, h in zip(cols, ["id", "name", "condition", "kind", "for", "where"]):
        t(cx, yy, h, 8.4, weight="bold")
    yy -= 6
    ax.plot([0, pw - 10], [yy, yy], color="#999", lw=0.6)
    yy -= 18
    where = dict(X1="NW edge, North Woods (W bank)", X2="Worksite West Gate (W bank)", X3="sluice jetty, S edge (E bank)",
                 X4="SE edge behind the substation (E bank)", X5="highway cutting, N edge (E of river)",
                 X6="dike culvert, SW edge (W bank)")
    for e in D.EXTRACTS:
        who = {"E": "east spawns", "W": "west spawns", "ALL": "everyone"}[e["for_side"]]
        t(cols[0], yy, e["id"], 8.6, weight="bold", color=C["extract_dark"])
        t(cols[1], yy, e["name"], 8.6)
        t(cols[2], yy, e["cond"], 8.6)
        t(cols[3], yy, e["kind"], 8.6, style="italic")
        t(cols[4], yy, who, 8.6)
        t(cols[5], yy, where[e["id"]], 8.6)
        yy -= 27
    t(0, yy, "Every spawn's always-open extract is across the river, so everyone crosses at least once.", 8.4,
      style="italic")
    yy -= 40

    # ---------------- spawns / chokepoints / sightlines (three columns)
    ytop = yy
    t(0, yy, "SPAWNS (blue)", 11, weight="bold", color="#0B3FA8")
    yy -= 28
    nodes, res = T
    for s in D.SPAWNS:
        tt = res[s["id"]]["SHOWHOME"][0]
        t(0, yy, f"{s['id']} {s['name']} ({s['side']}{', 16p' if s.get('only16') else ''})", 8.6, weight="bold")
        t(0, yy - 19, f"to Showhome ≈ {tt:.0f} s", 8.0, color="#444")
        yy -= 44
    y_spawn_end = yy
    yy = ytop
    t(330, yy, "CHOKEPOINTS (red circles)", 11, weight="bold", color=C["choke"])
    yy -= 28
    for kp in D.CHOKEPOINTS:
        t(330, yy, f"{kp['id']}  {kp['name']}", 8.6)
        yy -= 25
    yy = ytop
    t(690, yy, "KEY SIGHTLINES (thin red)", 11, weight="bold", color=C["sight"])
    yy -= 28
    for s in D.SIGHTLINES:
        ln = sight_len(X, s)
        t(690, yy, f"{s['id']}", 8.4, weight="bold", color=C["sight"])
        t(735, yy, f"{ln:>4.0f} m  {s['note']}", 8.0)
        yy -= 22

    # ---------------- travel-time matrix
    yy = min(yy, y_spawn_end) - 20
    t(0, yy, "TRAVEL TIMES ON FOOT (s)", 11, weight="bold")
    yy -= 22
    t(0, yy, "sprint 7.0 m/s (no / Light halo; Heavy ≈ +14 %) · straight across open ground × 1.12 · river only at "
             "C1–C3 · highway at U1, O1 or over the deck (+8–12 s) · blue = crosses the river", 8.0, style="italic")
    short = dict(SHOWHOME="Showhome", FARM="Farm", CONTAINER="Cont. park", PLANT="Plant", STORAGE="Storage",
                 GAS="Gas stn", SUBSTATION="Substation", SLUICE="Sluice", HUT="Hut")
    ids = D.TRAVEL_POIS
    cw, x0 = 128, 118
    yy -= 28
    for j, b in enumerate(ids):
        t(x0 + j * cw + cw / 2, yy, short[b], 8.2, weight="bold", ha="center")
    yy -= 6
    ax.plot([0, x0 + len(ids) * cw], [yy, yy], color="#999", lw=0.6)
    yy -= 15
    for a in ids:
        t(0, yy, short[a], 8.2, weight="bold")
        for j, b in enumerate(ids):
            cx = x0 + j * cw + cw / 2
            if a == b:
                t(cx, yy, "–", 8.2, ha="center", color="#999")
                continue
            tt, vias = res[a][b]
            river = any(v.startswith("C") for v in vias)
            if river:
                ax.add_patch(Rectangle((cx - cw / 2 + 4, yy - 10), cw - 8, 20, fc="#D6E9F7", ec="none", zorder=4))
            via = " " + "/".join(vias) if vias else ""
            t(cx, yy, f"{tt:.0f}", 8.4, ha="right", weight="bold")
            t(cx + 3, yy, via, 6.8, ha="left", color="#33556E")
        yy -= 22
    return ax


# ================================================================== main figure
def make_figure(X, T):
    fig = plt.figure(figsize=(FIG_W / DPI, FIG_H / DPI), dpi=DPI)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes(px_rect(MAP_AX_PX))
    ax.set_xlim(MAP_X0, MAP_X1)
    ax.set_ylim(MAP_Y0, MAP_Y1)
    ax.set_aspect("equal")
    S = Scale(PX_PER_M)
    ext = (MAP_X0, MAP_X1, MAP_Y0, MAP_Y1)
    rng = np.random.default_rng(11)
    R = fig.canvas.get_renderer()

    draw_base(ax, X, S, ext)
    draw_fields(ax, X, S)
    draw_forests(ax, X, S, rng)
    draw_poi_zones(ax, X, S)
    draw_details(ax, X, S)
    draw_river(ax, X, S)
    draw_roads(ax, X, S, "old_road")
    draw_highway(ax, X, S)
    draw_roads(ax, X, S, "other")
    draw_paths(ax, X, S)
    draw_crossings(ax, X, S)
    draw_structures(ax, X, S)
    draw_grid(ax, ext, D.GRID, 100)
    draw_tdm(ax, X, S)
    draw_ziplines(ax, X, S)
    draw_sightlines(ax, X, S)
    draw_chokepoints(ax, X, S)
    draw_landmarks(ax, X, S)
    draw_spawns(ax, X, S)
    draw_extracts(ax, X, S)
    draw_edge(ax)
    draw_main_labels(ax, X, R)
    scale_bar(ax, D.MAP_W - 240, -50, 200, h=7)
    north_arrow(ax, D.MAP_W - 10, -48, size=26)
    for sp in ax.spines.values():
        sp.set_linewidth(1.0)

    # titles
    fig.text(80 / FIG_W, (FIG_H - 46) / FIG_H, "SHARD/LINE · EXTRACTION MAP · layout diagram v0.2 (no modelling yet)",
             fontsize=20, weight="bold", color=C["ink"], va="center")
    fig.text(80 / FIG_W, (FIG_H - 92) / FIG_H,
             f"Top view, north up · playable {D.MAP_W:.0f} × {D.MAP_H:.0f} m · design frame: metres, x east, y north, origin = SW corner "
             "(Bevy: (x, z, −y)) · grid 50 m, labels every 100 m · Showhome is the hot zone; its TDM/FFA arena is "
             "the dashed 80 × 60 m cut-out",
             fontsize=10.5, color="#333", va="center")
    fig.text(80 / FIG_W, (FIG_H - 126) / FIG_H,
             "Zones and rough points only: the user sets exact spawns, extracts, loot spots and invisible walls in "
             "build mode. Source: design/maps/extraction/src/layout_data.py",
             fontsize=9.5, color="#555", va="center", style="italic")

    draw_panel(fig, X, R, T)
    ix, iy = PANEL_PX[0], PANEL_PX[1]
    iw = (INSET_EXT[1] - INSET_EXT[0]) * INSET_PX_PER_M
    ih = (INSET_EXT[3] - INSET_EXT[2]) * INSET_PX_PER_M
    inset_rect = (ix + 46, iy + 20, iw, ih)
    draw_inset(fig, X, R, inset_rect)
    fig.text((ix + 46) / FIG_W, (iy + 20 + ih + 24) / FIG_H,
             "INSET · Showhome hot zone + TDM / FFA cut-out (grid 10 m) · edges the rebuild must connect · "
             "A / B = TDM team sides", fontsize=10.5, weight="bold", va="center")
    # inset frame on the main map
    x0, x1, y0, y1 = INSET_EXT
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="none", ec="#111", lw=1.0, ls=(0, (2, 2)), zorder=29))
    text(ax, x1 - 2, y1 - 7, "inset", size=7, ha="right", z=29)
    return fig



# ================================================================== cover-rhythm check
def poi_poly(p):
    if "rect" in p:
        return G.rect_poly(*p["rect"])
    if "circle" in p:
        return G.circle_poly(*p["circle"])
    return np.asarray(p["poly"], float)


def cover_points(X):
    """Everything a player on open ground can duck behind (sampled points, v0.2 metres)."""
    pts = []
    for h in D.HEDGEROWS:
        pts.append(resample(np.asarray(h, float), 4.0))
    for d in D.DITCHES:
        pts.append(resample(G.catmull_rom(d, 8), 4.0))
    pts.append(np.asarray(D.HAY, float))
    st = X["roads"]["OLD_ROAD"]["line"]
    west = st[(st[:, 0] > 15) & (st[:, 0] < X["cross"]["C2"]["a"][0] - 20)]
    rs = resample(west, 15.0)
    pts += [G.offset(rs, 11.5), G.offset(rs, -11.5)]                      # avenue trees
    for s in D.STRUCTURES:
        if "rect" in s:
            x0, y0, x1, y1 = s["rect"]
            ring = np.vstack([G.rect_poly(x0, y0, x1, y1), [[x0, y0]]])
            pts.append(resample(ring, 4.0) if (x1 - x0) + (y1 - y0) > 8 else ring)
        else:
            pts.append(np.asarray([s["circle"][:2]], float))
    for f in X["forests"]:
        pts.append(resample(np.vstack([f["poly"], f["poly"][:1]]), 6.0))
    for p in D.POIS:
        poly = poi_poly(p)
        pts.append(resample(np.vstack([poly, poly[:1]]), 6.0))
    n = D.NURSERY
    pts.append(resample(G.rect_poly(n["x0"], n["y0"], n["x1"], n["y1"]).tolist() + [[n["x0"], n["y0"]]], 6.0))
    pts.append(np.asarray(D.POWERLINE, float))
    # terrain cover: the dike foot along the south edge and the highway slopes (6 m embankment / cutting)
    pts.append(np.stack([np.arange(0.0, D.MAP_W, 6.0), np.zeros(int(np.ceil(D.MAP_W / 6.0)))], axis=1))
    for off in (D.HW_DECK_HALF + D.HW_SLOPE_W, -(D.HW_DECK_HALF + D.HW_SLOPE_W)):
        pts.append(resample(G.offset(X["hw"], off), 6.0))
    return np.vstack([np.asarray(q, float).reshape(-1, 2) for q in pts if len(q)])


def cover_check(X, step=8.0):
    """Distance from every open-ground point to the nearest cover. Open ground = not woods, not a POI, not the
    nursery, not the river, not the highway corridor (whose slopes and stalled traffic are cover themselves)."""
    from scipy.spatial import cKDTree
    gx, gy = np.meshgrid(np.arange(step / 2, D.MAP_W, step), np.arange(step / 2, D.MAP_H, step))
    pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
    covered = np.zeros(len(pts), bool)
    for f in X["forests"]:
        covered |= poly_inside(f["poly"], pts)
    for p in D.POIS:
        covered |= poly_inside(poi_poly(p), pts)
    n = D.NURSERY
    covered |= (pts[:, 0] >= n["x0"]) & (pts[:, 0] <= n["x1"]) & (pts[:, 1] >= n["y0"]) & (pts[:, 1] <= n["y1"])
    river_d, _ = cKDTree(resample(X["river"], 2.0)).query(pts)
    hw_d, _ = cKDTree(resample(X["hw"], 2.0)).query(pts)
    water = river_d < D.RIVER_HALF_W + D.RIVER_BANK_W
    corridor = hw_d < D.HW_DECK_HALF + D.HW_SLOPE_W
    open_ = ~covered & ~water & ~corridor
    d, _ = cKDTree(cover_points(X)).query(pts[open_])
    return pts[open_], d


def cover_table(X):
    op, d = cover_check(X)
    area = len(op) * 64.0
    rows = ["| Open ground | Within 20 m of cover | Within 30 m | Within 40 m | Farthest point from cover |",
            "|---|---|---|---|---|"]
    far = op[int(np.argmax(d))]
    rows.append(f"| {area / 10000:.0f} ha ({100 * area / (D.MAP_W * D.MAP_H):.0f} % of the map) | "
                f"{100 * np.mean(d <= 20):.0f} % | {100 * np.mean(d <= 30):.0f} % | {100 * np.mean(d <= 40):.1f} % | "
                f"{d.max():.0f} m at ({far[0]:.0f}, {far[1]:.0f}) |")
    return "\n".join(rows), op, d


# ================================================================== numbers -> JSON and LAYOUT.md
def tables(X, T):
    nodes, res = T
    v = D.SPEED["sprint"]
    names = {p["id"]: p["name"] for p in D.POIS}
    out = {}

    # POIs
    rows = ["| POI | Loot | Footprint (design m) | Area | Travel-time node |", "|---|---|---|---|---|"]
    for p in D.POIS:
        if "rect" in p:
            x0, y0, x1, y1 = p["rect"]
            fp = f"x {x0:.0f}..{x1:.0f}, y {y0:.0f}..{y1:.0f} ({x1 - x0:.0f} × {y1 - y0:.0f})"
            area = (x1 - x0) * (y1 - y0)
        elif "circle" in p:
            cx, cy, r = p["circle"]
            fp = f"clearing r {r:.0f} at ({cx:.0f}, {cy:.0f})"
            area = math.pi * r * r
        else:
            bx0, by0, bx1, by1 = G.poly_bbox(p["poly"])
            fp = f"polygon, bbox x {bx0:.0f}..{bx1:.0f}, y {by0:.0f}..{by1:.0f}"
            area = G.poly_area(p["poly"])
        rows.append(f"| {p['name']} | L{p['tier']} | {fp} | {area / 10000:.2f} ha | "
                    f"({p['node'][0]:.0f}, {p['node'][1]:.0f}) |")
    out["pois"] = "\n".join(rows)

    # crossings
    rows = ["| Id | Crossing | Centre (design m) | Length | Note |", "|---|---|---|---|---|"]
    for cid in ("C1", "C2", "C3", "U1", "O1"):
        c = X["cross"][cid]
        rows.append(f"| {cid} | {c['name']} | ({c['at'][0]:.0f}, {c['at'][1]:.0f}) | {c['span']:.0f} m | {c['note']} |")
    d12 = np.linalg.norm(X["cross"]["C1"]["at"] - X["cross"]["C2"]["at"])
    d23 = np.linalg.norm(X["cross"]["C2"]["at"] - X["cross"]["C3"]["at"])
    rows.append("")
    rows.append(f"Straight-line spacing: C1 ↔ C2 {d12:.0f} m, C2 ↔ C3 {d23:.0f} m. River length in the map: "
                f"{G.length(G.slice_by_y(X['river'], 900, 0)):.0f} m. Highway length in the map: "
                f"{G.length(clip_line(X['hw'])):.0f} m.")
    out["crossings"] = "\n".join(rows)

    # travel matrix
    ids = D.TRAVEL_POIS
    head = "| from \\ to | " + " | ".join(names[i] for i in ids) + " |"
    rows = [head, "|---" * (len(ids) + 1) + "|"]
    for a in ids:
        cells = []
        for b in ids:
            if a == b:
                cells.append("–")
                continue
            tt, vias = res[a][b]
            via = "/".join(vias)
            cells.append(f"{tt:.0f}" + (f" ({via})" if via else ""))
        rows.append(f"| **{names[a]}** | " + " | ".join(cells) + " |")
    out["travel"] = "\n".join(rows)

    # spawns
    rows = ["| Spawn | Side | Zone (design m) | → Showhome | → nearest POI | Extract set (time, crossings) |",
            "|---|---|---|---|---|---|"]
    for s in D.SPAWNS:
        x0, y0, x1, y1 = s["rect"]
        tt, vias = res[s["id"]]["SHOWHOME"]
        near = min((res[s["id"]][p][0], p) for p in ids if p != "SHOWHOME")
        ex = []
        for e in D.EXTRACTS:
            if e["for_side"] in (s["side"], "ALL"):
                et, ev = res[s["id"]][e["id"]]
                ex.append(f"{e['id']} {et:.0f} s" + (f" via {'/'.join(ev)}" if ev else ""))
        side = s["side"] + (" (16 players only)" if s.get("only16") else "")
        rows.append(f"| {s['id']} {s['name']} | {side} | x {x0:.0f}..{x1:.0f}, y {y0:.0f}..{y1:.0f} | "
                    f"{tt:.0f} s" + (f" ({'/'.join(vias)})" if vias else "") +
                    f" | {names[near[1]]} {near[0]:.0f} s | " + "; ".join(ex) + " |")
    out["spawns"] = "\n".join(rows)

    # extracts
    rows = ["| Extract | Kind | Condition | For | Point (design m) | From Showhome |", "|---|---|---|---|---|---|"]
    for e in D.EXTRACTS:
        p = X["ext"][e["id"]]
        tt, vias = res["SHOWHOME"][e["id"]]
        who = {"E": "east spawns", "W": "west spawns", "ALL": "everyone"}[e["for_side"]]
        rows.append(f"| {e['id']} {e['name']} | {e['kind']} | {e['cond']}: {e['note']} | {who} | "
                    f"({p[0]:.0f}, {p[1]:.0f}) r {D.EXTRACT_R:.0f} | {tt:.0f} s" +
                    (f" via {'/'.join(vias)}" if vias else "") + " |")
    out["extracts"] = "\n".join(rows)

    # sightlines
    rows = ["| Id | From → to | Length | Read |", "|---|---|---|---|"]
    for s in D.SIGHTLINES:
        ln = sight_len(X, s)
        if ln <= 60:
            band = "AR full damage zone (≤ 60 m)"
        elif ln <= 90:
            band = "AR still strong (60–90 m)"
        elif ln <= 150:
            band = "AR falloff; scoped guns favoured"
        else:
            band = "sniper lane (> 150 m): needs cover breaks"
        rows.append(f"| {s['id']} | {s['note']} | {ln:.0f} m | {band} |")
    out["sightlines"] = "\n".join(rows)
    # land cover (areas inside the playable rect, sampled on a 4 m grid)
    gx, gy = np.meshgrid(np.arange(2.0, D.MAP_W, 4.0), np.arange(2.0, D.MAP_H, 4.0))
    pts = np.stack([gx.ravel(), gy.ravel()], axis=1)
    cell = 16.0
    role = dict(NORTH_WOODS="NW woods: S3 and X1, cover from the worksite's north to the Dirt Bridge",
                RIVERSIDE_WOODS="east-bank woods: Dirt Bridge to the Overpass and the container park",
                WEST_WOODS="west boundary strip: S1 to X6 along the edge",
                SOUTH_WOODS="SW patch: cover between the farm and X6",
                POPLARS="poplar row on the west bank: Road Bridge to the Weir and the sluice, under cover",
                PLANTWOOD="screen between the Road Bridge and the plant fence",
                PYLONWOOD="S6 to the substation", SE_WOOD="SE corner behind the substation",
                NE_WOOD="S4 to the storage rear gate", COPSE_W="field copse in the West Fields",
                COPSE_FARM="field copse between the farm and the Old Road",
                COPSE_EAST="field copse in the pylon field, east of the plant",
                EAST_WOODS="pocket east of the highway: cover to U1's east mouth and the gas station",
                COPSE_NE="field copse between the highway cutting and the storage")
    rows = ["| Land cover (forest unless noted) | Area in the map | Role |", "|---|---|---|"]
    total_forest = 0.0
    for f in X["forests"]:
        a = float(poly_inside(f["poly"], pts).sum()) * cell
        total_forest += a
        rows.append(f"| {f['name']} | {a / 10000:.1f} ha | {role.get(f['id'], '')} |")
    arable = sum(float(poly_inside(f["pts"], pts).sum()) * cell for f in D.FIELDS)
    rows.append(f"| Arable fields (striped) | {arable / 10000:.1f} ha | open ground with hedgerows, ditches, hay |")
    rows.append(f"| **All forest** | **{total_forest / 10000:.1f} ha** "
                f"({100 * total_forest / (D.MAP_W * D.MAP_H):.0f} % of the map) | |")
    out["landcover"] = "\n".join(rows)
    out["cover"] = cover_table(X)[0]
    out["_meta"] = f"sprint {v} m/s (no / Light halo), route factor {D.ROUTE_FACTOR}"
    return out


def clip_line(P):
    P = np.asarray(P, float)
    return P[(P[:, 0] >= 0) & (P[:, 0] <= D.MAP_W) & (P[:, 1] >= 0) & (P[:, 1] <= D.MAP_H)]


def write_json(X, T):
    nodes, res = T

    def r2(v):
        return [round(float(a), 1) for a in v]

    data = dict(
        frame="design: metres, x east, y north, z up, origin SW corner; bevy = (x, z, -y)",
        playable=dict(x0=0, y0=0, x1=D.MAP_W, y1=D.MAP_H),
        speeds=D.SPEED, route_factor=D.ROUTE_FACTOR,
        river=dict(centre=[r2(p) for p in D.RIVER_PTS], half_width=D.RIVER_HALF_W, bank=D.RIVER_BANK_W),
        highway=dict(centre=[r2(p) for p in D.HIGHWAY_PTS], deck_half=D.HW_DECK_HALF, slope=D.HW_SLOPE_W,
                     cutting_north_of_y=D.HW_CUT_ABOVE_Y, embankment_south_of_y=D.HW_EMB_BELOW_Y),
        crossings={cid: dict(name=c["name"], centre=r2(c["at"]), end_a=r2(c["a"]), end_b=r2(c["b"]),
                             length=round(c["span"], 1), note=c["note"]) for cid, c in X["cross"].items()},
        pois=[{k: v for k, v in p.items()} for p in D.POIS],
        tdm=D.TDM,
        spawns=D.SPAWNS,
        extracts=[dict(e, at=r2(X["ext"][e["id"]]), radius=D.EXTRACT_R) for e in D.EXTRACTS],
        roads=[dict(id=r["id"], kind=r["kind"], name=r["name"], pts=r["pts"]) for r in D.ROADS],
        sightlines=[dict(s, a=r2(X["sight"][s["id"]][0]), b=r2(X["sight"][s["id"]][1]), length=round(sight_len(X, s), 1))
                    for s in D.SIGHTLINES],
        chokepoints=[dict(k, at=r2(choke_at(X, k))) for k in D.CHOKEPOINTS],
        landmarks=D.LANDMARKS, ziplines=D.ZIPLINES,
        travel_s={a: {b: round(res[a][b][0], 1) for b in D.TRAVEL_POIS} for a in D.TRAVEL_POIS},
    )
    path = os.path.join(OUT, "data", "extraction_layout.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, "tolist")
                  else str(o))
    return path


def refresh_layout_md(tabs):
    path = os.path.join(OUT, "LAYOUT.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        s = f.read()
    for k, v in tabs.items():
        if k.startswith("_"):
            continue
        pat = re.compile(rf"(<!-- AUTO:{k} -->\n)(?:.*?\n)?(<!-- /AUTO:{k} -->)", re.S)
        s, n = pat.subn(lambda m: m.group(1) + v + "\n" + m.group(2), s)
        if n != 1:
            print(f"warning: AUTO block {k!r} found {n} times in LAYOUT.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(s)
    return path


def main():
    X = derive()
    T = travel(X)
    fig = make_figure(X, T)
    svg = os.path.join(OUT, "diagram.svg")
    png = os.path.join(OUT, "diagram.png")
    fig.savefig(svg, dpi=DPI)
    fig.savefig(png, dpi=DPI)
    plt.close(fig)
    tabs = tables(X, T)
    jp = write_json(X, T)
    md = refresh_layout_md(tabs)
    print("wrote", svg, png, jp, md or "(no LAYOUT.md yet)")
    for k, v in tabs.items():
        print(f"\n## {k}\n{v}")


if __name__ == "__main__":
    main()
