"""Small 2D geometry helpers for the extraction-map diagram (numpy only, no shapely)."""
import math

import numpy as np


def catmull_rom(pts, samples=10, closed=False):
    """Uniform Catmull-Rom spline through `pts`. Returns an (N, 2) array that passes through every point."""
    P = np.asarray(pts, float)
    if len(P) < 3:
        return P.copy()
    if closed:
        P = np.vstack([P[-1], P, P[0], P[1]])
    else:
        P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for t in np.linspace(0.0, 1.0, samples, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    if not closed:
        out.append(P[-2])
    return np.array(out)


def left_normals(P):
    """Unit normals pointing LEFT of the direction of travel along P (for a southward river: east)."""
    d = np.gradient(np.asarray(P, float), axis=0)
    d /= np.linalg.norm(d, axis=1)[:, None]
    return np.stack([-d[:, 1], d[:, 0]], axis=1)


def offset(P, dist):
    """Offset a polyline sideways. dist > 0 = left of the direction of travel."""
    P = np.asarray(P, float)
    dist = np.asarray(dist, float)
    if dist.ndim == 0:
        dist = np.full(len(P), float(dist))
    return P + left_normals(P) * dist[:, None]


def ribbon(P, left, right):
    """Closed polygon between offset(+left) and offset(-right)."""
    return np.vstack([offset(P, left), offset(P, -right)[::-1]])


def length(P):
    P = np.asarray(P, float)
    return float(np.sum(np.linalg.norm(np.diff(P, axis=0), axis=1)))


def seg_intersect(p, q, a, b):
    """Intersection point of segments pq and ab, or None."""
    p, q, a, b = (np.asarray(v, float) for v in (p, q, a, b))
    r, s = q - p, b - a
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12:
        return None
    t = ((a - p)[0] * s[1] - (a - p)[1] * s[0]) / den
    u = ((a - p)[0] * r[1] - (a - p)[1] * r[0]) / den
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return p + t * r
    return None


def polyline_hits(A, B):
    """All intersection points between polylines A and B (list of np arrays)."""
    hits = []
    A, B = np.asarray(A, float), np.asarray(B, float)
    for i in range(len(A) - 1):
        for j in range(len(B) - 1):
            x = seg_intersect(A[i], A[i + 1], B[j], B[j + 1])
            if x is not None:
                hits.append(x)
    return hits


def crosses(p, q, B):
    """True if segment pq crosses polyline B."""
    B = np.asarray(B, float)
    for j in range(len(B) - 1):
        if seg_intersect(p, q, B[j], B[j + 1]) is not None:
            return True
    return False


def nearest_index(P, pt):
    P = np.asarray(P, float)
    return int(np.argmin(np.linalg.norm(P - np.asarray(pt, float), axis=1)))


def x_at_y(P, y):
    """x of the first crossing of the horizontal line `y` by polyline P (P runs roughly north-south)."""
    P = np.asarray(P, float)
    for i in range(len(P) - 1):
        (x0, y0), (x1, y1) = P[i], P[i + 1]
        if (y0 - y) * (y1 - y) <= 0 and y0 != y1:
            return float(x0 + (y - y0) / (y1 - y0) * (x1 - x0))
    raise ValueError(f"y={y} not on polyline")


def slice_by_y(P, y_hi, y_lo):
    """Part of a north-to-south polyline between y_hi and y_lo (inclusive, interpolated ends)."""
    P = np.asarray(P, float)
    keep = [p for p in P if y_lo < p[1] < y_hi]
    return np.array([[x_at_y(P, y_hi), y_hi]] + keep + [[x_at_y(P, y_lo), y_lo]])


def direction_at(P, pt):
    """Unit tangent of polyline P at its point nearest `pt`."""
    P = np.asarray(P, float)
    i = nearest_index(P, pt)
    i0, i1 = max(i - 1, 0), min(i + 1, len(P) - 1)
    d = P[i1] - P[i0]
    return d / np.linalg.norm(d)


def rect_poly(x0, y0, x1, y1):
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], float)


def circle_poly(cx, cy, r, n=48):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.stack([cx + r * np.cos(a), cy + r * np.sin(a)], axis=1)


def poly_area(poly):
    P = np.asarray(poly, float)
    x, y = P[:, 0], P[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def poly_bbox(poly):
    P = np.asarray(poly, float)
    return float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max())


def oriented_rect(cx, cy, length_m, width_m, direction):
    """Rectangle centred at (cx, cy), long side along `direction` (unit vector)."""
    d = np.asarray(direction, float)
    d = d / np.linalg.norm(d)
    n = np.array([-d[1], d[0]])
    hl, hw = length_m / 2.0, width_m / 2.0
    c = np.array([cx, cy], float)
    return np.array([c + d * hl + n * hw, c - d * hl + n * hw, c - d * hl - n * hw, c + d * hl - n * hw])
