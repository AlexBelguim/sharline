"""Sightline, spawn-exposure and timing analysis for SHOWHOME. Pure numpy; reads showhome_layout.py.

python analyze_showhome.py            -> prints the report and writes ../data/analysis.json
"""
import json
import math
import os

import numpy as np

import showhome_layout as SL

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


# ---------------------------------------------------------------- blockers
def blockers_2d(L, eye=SL.Z["EYE"]):
    """Rects + circles that block a ground-level eye-height line (both players standing on z=0)."""
    rects, circles = [], []
    for e in L["elements"]:
        if not e.blocks or e.kind in ("terrace", "perch"):
            continue
        if not (e.z0 <= eye < e.z1):
            continue
        if e.shape == "circle":
            circles.append((e.cx, e.cy, e.r))
        else:
            rects.append((e.x0, e.y0, e.x1, e.y1))
    return np.array(rects, float), np.array(circles, float).reshape(-1, 3)


def boxes_3d(L):
    """Axis-aligned 3D boxes for elevated line checks (houses incl. a conservative roof box)."""
    B = []
    for e in L["elements"]:
        if not e.blocks or e.kind in ("terrace", "perch"):
            continue
        B.append((e.x0, e.y0, e.z0, e.x1, e.y1, e.z1, e.id))
        if e.kind == "house" and e.id.endswith("MAIN"):
            B.append((e.x0, e.y0, SL.Z["EAVES"], e.x1, e.y1, SL.Z["RIDGE"], e.id + "_ROOF"))
    for w in L["walls"]:
        if w.kind in ("parapet", "screen"):
            t = w.t / 2
            x0, x1 = sorted((w.x0, w.x1))
            y0, y1 = sorted((w.y0, w.y1))
            if x0 == x1:
                x0, x1 = x0 - t, x1 + t
            else:
                y0, y1 = y0 - t, y1 + t
            B.append((x0, y0, w.z0, x1, y1, w.z1, w.id))
    return B


# ---------------------------------------------------------------- vectorised 2D segment tests
def _seg_rects(p, d, inv, rects, eps=-0.02):
    if len(rects) == 0:
        return np.zeros(len(d), bool)
    blocked = np.zeros(len(d), bool)
    zx, zy = d[:, 0] == 0, d[:, 1] == 0
    for x0, y0, x1, y1 in rects:
        x0, y0, x1, y1 = x0 + eps, y0 + eps, x1 - eps, y1 - eps
        with np.errstate(invalid="ignore"):
            t1, t2 = (x0 - p[0]) * inv[:, 0], (x1 - p[0]) * inv[:, 0]
            tminx, tmaxx = np.minimum(t1, t2), np.maximum(t1, t2)
            t1, t2 = (y0 - p[1]) * inv[:, 1], (y1 - p[1]) * inv[:, 1]
            tminy, tmaxy = np.minimum(t1, t2), np.maximum(t1, t2)
        inx = (p[0] > x0) & (p[0] < x1)
        iny = (p[1] > y0) & (p[1] < y1)
        tminx = np.where(zx, -np.inf if inx else np.inf, tminx)
        tmaxx = np.where(zx, np.inf if inx else -np.inf, tmaxx)
        tminy = np.where(zy, -np.inf if iny else np.inf, tminy)
        tmaxy = np.where(zy, np.inf if iny else -np.inf, tmaxy)
        tmin = np.maximum(np.maximum(tminx, tminy), 0.0)
        tmax = np.minimum(np.minimum(tmaxx, tmaxy), 1.0)
        blocked |= tmin < tmax
    return blocked


def _seg_circles(p, d, circles, eps=-0.02):
    blocked = np.zeros(len(d), bool)
    dd = np.maximum((d * d).sum(1), 1e-9)
    for cx, cy, r in circles:
        c = np.array([cx, cy]) - p
        t = np.clip((d @ c) / dd, 0, 1)
        q = d * t[:, None] - c
        blocked |= (q * q).sum(1) < (r - eps) ** 2
    return blocked


def visible_from(p, P, rects, circles):
    d = P - p
    with np.errstate(divide="ignore"):
        inv = 1.0 / d
    return ~(_seg_rects(p, d, inv, rects) | _seg_circles(p, d, circles))


# ---------------------------------------------------------------- 3D single segment test
def seg_hits_box(p, q, b):
    tmin, tmax = 0.0, 1.0
    for k in range(3):
        dk = q[k] - p[k]
        lo, hi = b[k] - 0.02, b[k + 3] + 0.02
        if abs(dk) < 1e-12:
            if p[k] <= lo or p[k] >= hi:
                return False
        else:
            t1, t2 = (lo - p[k]) / dk, (hi - p[k]) / dk
            if t1 > t2:
                t1, t2 = t2, t1
            tmin, tmax = max(tmin, t1), min(tmax, t2)
            if tmin >= tmax:
                return False
    return True


def first_hit(p, q, B):
    for b in B:
        if seg_hits_box(p, q, b):
            return b[6]
    return None


# ---------------------------------------------------------------- sample points
def walkable_points(L, step=1.0, margin=0.3):
    xs = np.arange(1.5, SL.MAP_W - 1.0, step)
    ys = np.arange(1.5, SL.MAP_H - 1.0, step)
    X, Y = np.meshgrid(xs, ys)
    P = np.c_[X.ravel(), Y.ravel()]
    keep = np.ones(len(P), bool)
    for e in L["elements"]:
        if e.z0 > 1.0 or e.kind in ("terrace",):
            continue
        if e.shape == "circle":
            keep &= ((P[:, 0] - e.cx) ** 2 + (P[:, 1] - e.cy) ** 2) > (e.r + margin) ** 2
        else:
            keep &= ~((P[:, 0] > e.x0 - margin) & (P[:, 0] < e.x1 + margin) &
                      (P[:, 1] > e.y0 - margin) & (P[:, 1] < e.y1 + margin))
    return P[keep]


def area_of(x, y):
    if x < 9 and 12 < y < 36:
        return "W-Yard"
    if x > 63 and 12 < y < 36:
        return "E-Yard"
    side = "W" if x < 28 else ("E" if x > 44 else "St")
    band = "N" if y >= 32 else ("S" if y < 16 else "M")
    return f"{side}-{band}"


# ---------------------------------------------------------------- routes
def route_metrics(route):
    rid, name, pts = route
    dist, t, prev, mode, extra = 0.0, 0.0, None, None, []
    for p in pts:
        if isinstance(p, str):
            if p == "STAIR":
                mode = "stair"
            elif p.startswith("JET:"):
                h = float(p[4:])
                t += h / SL.MOVE["jet_ascent_speed"]
                extra.append(f"jet {h:.1f} m")
            elif p.startswith("ZIP:"):
                m = float(p[4:])
                mode = "zip"
                extra.append(f"zipline {m:.0f} m")
            continue
        if prev is not None:
            seg = math.dist(prev, p)
            if mode == "stair":
                run = seg
                seg3 = math.hypot(run, SL.Z["UF"])
                dist += seg3
                t += run / (SL.MOVE["sprint"] * SL.MOVE["stair_factor"])
            elif mode == "zip":
                dist += seg
                t += seg / SL.MOVE["zipline_speed"] + SL.MOVE["zipline_attach_s"]
            else:
                dist += seg
                t += seg / SL.MOVE["sprint"]
            mode = None
        prev = p
    return dict(id=rid, name=name, length_m=round(dist, 1), time_s=round(t, 1), extra=extra)


# ---------------------------------------------------------------- main analysis
def run(L=None, step=1.0, verbose=True):
    L = L or SL.build()
    rects, circles = blockers_2d(L)
    P = walkable_points(L, step)
    N = len(P)
    maxvis = np.zeros(N)
    best = {}          # (areaA, areaB) -> (len, i, j)
    yard_hits = []     # lines from outside the own half into a spawn yard
    areas = [area_of(x, y) for x, y in P]
    for i in range(N):
        vis = visible_from(P[i], P, rects, circles)
        vis[i] = False
        dist = np.hypot(*(P - P[i]).T)
        dv = np.where(vis, dist, 0.0)
        maxvis[i] = dv.max()
        for j in np.nonzero(dv > 24.0)[0]:
            if j < i:
                continue
            key = tuple(sorted((areas[i], areas[j])))
            if key not in best or dv[j] > best[key][0]:
                best[key] = (float(dv[j]), i, int(j))
        # spawn exposure: a point in a yard seen from beyond the own house line
        if areas[i] == "W-Yard":
            bad = np.nonzero(vis & (P[:, 0] > 28.0))[0]
            yard_hits += [(i, int(j)) for j in bad]
        if areas[i] == "E-Yard":
            bad = np.nonzero(vis & (P[:, 0] < 44.0))[0]
            yard_hits += [(i, int(j)) for j in bad]

    long_lines = sorted(
        [dict(a=k[0], b=k[1], length_m=round(v[0], 1), p=P[v[1]].tolist(), q=P[v[2]].tolist())
         for k, v in best.items()], key=lambda r: -r["length_m"])

    # named sightlines (3D)
    B = boxes_3d(L)
    named = []
    for sid, name, p, q, note in L["sightlines"]:
        hit = first_hit(p, q, B)
        named.append(dict(id=sid, name=name, p=p, q=q, length_m=round(math.dist(p, q), 1), clear=hit is None,
                          blocked_by=hit, note=note))

    # elevated spawn exposure: enemy-side high positions -> own spawn points (chest height)
    W_spawns = [s for s in L["spawns"] if s["zone"] == "W_YARD"]
    sources = []
    def grid(x0, y0, x1, y1, z, s=1.0, tag=""):
        for x in np.arange(x0, x1 + 1e-6, s):
            for y in np.arange(y0, y1 + 1e-6, s):
                sources.append((float(x), float(y), z, tag))
    uf_eye = SL.Z["UF"] + SL.Z["EYE"]
    grid(51.6, 16.6, 62.4, 21.4, uf_eye, 1.2, "E terrace")
    grid(9.6, 16.6, 20.4, 21.4, uf_eye, 1.2, "W terrace (captured)")
    grid(34.9, 19.2, 37.1, 26.8, 3.2 + SL.Z["EYE"], 0.7, "Mover Top")
    grid(30.2, 1.2, 41.8, 7.8, 3.0 + SL.Z["EYE"], 1.0, "Office Roof")
    grid(24.1, 44.6, 25.9, 46.4, 4.0 + SL.Z["EYE"], 0.6, "W pad")
    grid(46.1, 44.6, 47.9, 46.4, 4.0 + SL.Z["EYE"], 0.6, "E pad")
    for y in (23.4, 24.2, 25.0, 28.6, 29.4, 30.2):
        sources.append((50.8, y, uf_eye, "E UF street windows"))
    grid(28.5, 2.0, 43.5, 46.0, 9.0, 1.5, "jetpack at soft ceiling (9 m) over street")
    exposure = {}
    for (x, y, z, tag) in sources:
        for s in W_spawns:
            q = (s["x"], s["y"], SL.Z["CHEST"])
            if first_hit((x, y, z), q, B) is None:
                exposure.setdefault(tag, set()).add(s["id"])
    exposure = {k: sorted(v) for k, v in exposure.items()}

    routes = [route_metrics(r) for r in L["routes"]]

    res = dict(sample_step_m=step, n_points=int(N), max_ground_sightline_m=round(float(maxvis.max()), 1),
               long_lines=long_lines[:25], named_sightlines=named,
               ground_yard_exposure_pairs=len(yard_hits),
               ground_yard_exposure_examples=[[P[i].tolist(), P[j].tolist()] for i, j in yard_hits[:10]],
               elevated_spawn_exposure=exposure, routes=routes)
    if verbose:
        print(f"points {N}, max ground sightline {res['max_ground_sightline_m']} m")
        print("--- longest ground lines by area pair")
        for r in long_lines[:18]:
            print(f"  {r['length_m']:5.1f}  {r['a']:7s} <-> {r['b']:7s}  {r['p']} -> {r['q']}")
        print("--- named sightlines")
        for n in named:
            print(f"  {n['name']:14s} {n['length_m']:5.1f} m  clear={n['clear']}  {n['blocked_by'] or ''}")
        print("--- ground-level yard exposure pairs:", len(yard_hits), res["ground_yard_exposure_examples"][:4])
        print("--- elevated exposure of W_YARD spawns:", exposure)
        print("--- routes (west team)")
        for r in routes:
            print(f"  {r['time_s']:5.1f} s  {r['length_m']:5.1f} m  {r['name']}  {', '.join(r['extra'])}")
    return res, P, maxvis


if __name__ == "__main__":
    res, P, maxvis = run()
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "analysis.json"), "w") as f:
        json.dump(res, f, indent=1)
