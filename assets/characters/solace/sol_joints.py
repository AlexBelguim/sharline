"""Joint placement for SOLACE from mesh cross-sections (numpy only; works in Blender or plain Python).

Every joint is found from planar sections of the body mesh: a plane through a provisional point, perpendicular to
the limb, cuts the triangles; the cut segments are grouped into contours and the contour closest to the
provisional point gives the limb centre (length-weighted centroid) and its radius. Provisional points come from the
silhouette (fingertips, toe tips, crotch, shoulder line) measured on the same mesh, so nothing is copied from the
parametric base body.
"""
import numpy as np


def _norm(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


class Sections:
    def __init__(self, co, tris):
        self.co = np.asarray(co, float)
        self.tris = np.asarray(tris, np.int64)
        self.tc = self.co[self.tris]            # T x 3 x 3

    def cut(self, p, n, rmax=0.12):
        """Segments of the mesh cut by the plane (p, n) within rmax of p, with edge keys for exact connectivity."""
        n = _norm(n)
        d = (self.tc - p) @ n                    # T x 3
        near = np.linalg.norm(self.tc.mean(1) - p, axis=1) < rmax + 0.03
        m = near & (d.min(1) < 0) & (d.max(1) > 0)
        segs, keys = [], []
        for tri, ids, dd in zip(self.tc[m], self.tris[m], d[m]):
            pts, ks = [], []
            for a, b in ((0, 1), (1, 2), (2, 0)):
                if (dd[a] < 0) != (dd[b] < 0):
                    t = dd[a] / (dd[a] - dd[b])
                    pts.append(tri[a] + (tri[b] - tri[a]) * t)
                    ks.append((min(ids[a], ids[b]), max(ids[a], ids[b])))
            if len(pts) == 2:
                segs.append(pts)
                keys.append(ks)
        self._keys = keys
        return np.array(segs).reshape(-1, 2, 3)

    def contours(self, segs, tol=None):
        """Group segments into connected contours (segments sharing a cut mesh edge)."""
        n = len(segs)
        if n == 0:
            return []
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        table = {}
        for sidx, ks in enumerate(self._keys):
            for k in ks:
                if k in table:
                    a, b = find(sidx), find(table[k])
                    if a != b:
                        parent[a] = b
                else:
                    table[k] = sidx
        groups = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)
        self._closed = []
        out = []
        for g in groups.values():
            cnt = {}
            for i in g:
                for k in self._keys[i]:
                    cnt[k] = cnt.get(k, 0) + 1
            self._closed.append(all(v == 2 for v in cnt.values()))
            out.append(segs[g])
        return out

    def centre(self, p, n, rmax=0.12, pick="near", minlen=0.03, max_rad=1.0, closed=False):
        """Centre + mean radius of the contour of plane (p, n) best matching `pick`:
        'near' = contour whose centroid is nearest p; 'encl' = smallest contour that encloses p (in plane)."""
        segs = self.cut(p, n, rmax)
        best = None
        cs = self.contours(segs)
        for ci, c in enumerate(cs):
            if closed and not self._closed[ci]:
                continue
            mid = c.mean(1)
            ln = np.linalg.norm(c[:, 1] - c[:, 0], axis=1)
            L = ln.sum()
            if L < minlen:
                continue
            cen = (mid * ln[:, None]).sum(0) / L
            rad = (np.linalg.norm(mid - cen, axis=1) * ln).sum() / L
            if rad > max_rad:
                continue
            score = np.linalg.norm(cen - p) + (0.0 if pick == "near" else rad)
            if best is None or score < best[0]:
                best = (score, cen, rad, L)
        if best is None:
            return None, None
        return best[1], best[2]


def find_joints(co, tris, log=print):
    co = np.asarray(co, float)
    S = Sections(co, tris)
    x, y, z = co.T
    J = {}
    # ---------------------------------------------------------------- legs (horizontal sections)
    for s, sd in ((1, "l"), (-1, "r")):
        cs = []
        for zz in np.arange(0.10, 0.60, 0.02):
            m = (s * x > 0.02) & (s * x < 0.30) & (np.abs(z - zz) < 0.01)
            guess = np.array([np.median(x[m]), np.median(y[m]), zz])
            c, r = S.centre(guess, (0, 0, 1), rmax=0.12)
            if c is not None and r < 0.09:
                cs.append((zz, c, r))
        zz_, c_, r_ = zip(*cs)
        c_ = np.array(c_)
        r_ = np.array(r_)
        # ankle: narrowest leg section between 0.06 and 0.22 (boot shaft)
        k = [i for i, q in enumerate(zz_) if 0.07 <= q <= 0.20]
        ka = k[int(np.argmin(r_[k]))]
        # knee: knee-pad height, centre found at z 0.47-0.52 (sections are clean below the coat)
        kk = [i for i, q in enumerate(zz_) if 0.44 <= q <= 0.52]
        knee = c_[kk].mean(0)
        knee[1] += 0.008                          # joint sits a little behind the section centre (pad in front)
        ankle = c_[ka].copy()
        ankle[2] = max(0.075, zz_[ka])
        # thigh line from the clean sections 0.52..0.60, extrapolated to the hip height
        kt = [i for i, q in enumerate(zz_) if 0.52 <= q <= 0.60]
        tdir = _norm(knee - c_[kt].mean(0)) if len(kt) else _norm((0, 0, -1))
        J["calf_" + sd] = knee
        J["foot_" + sd] = ankle
        J["_shin_dir_" + sd] = _norm(knee - ankle)
        # foot: toe tip and heel from the boot verts
        m = (s * x > 0.0) & (z < 0.06)
        fp = co[m]
        toe = fp[np.argmin(fp[:, 1])]
        fwd = _norm([toe[0] - ankle[0], toe[1] - ankle[1], 0])
        along = (fp - ankle) @ fwd
        heel = fp[np.argmin(along)]
        flen = along.max() - along.min()
        ball = ankle + fwd * (along.max() * 0.62)
        ball[2] = 0.030
        J["ball_" + sd] = ball
        J["_toe_" + sd] = np.array([toe[0], toe[1], 0.02])
        J["_heel_" + sd] = heel
        log(f"leg {sd}: ankle {np.round(ankle, 3)} knee {np.round(knee, 3)} foot len {flen:.3f}")
    # hips: crotch height = lowest z where the inner pants surface crosses x=0 near the body centre
    crotch = None
    for zz in np.arange(0.62, 0.95, 0.005):
        segs = S.cut(np.array([0.0, 0.03, zz]), (0, 0, 1), rmax=0.10)
        if not len(segs):
            continue
        P = segs.reshape(-1, 3)
        if np.any((np.abs(P[:, 0]) < 0.006) & (np.abs(P[:, 1] - 0.03) < 0.08)):
            crotch = zz
            break
    crotch = crotch or 0.78
    hip_z = crotch + 0.075
    tops = {}
    for s, sd in ((1, "l"), (-1, "r")):
        knee = J["calf_" + sd]
        cs = []
        for zz in np.arange(crotch - 0.14, crotch - 0.015, 0.015):
            guess = np.array([knee[0] + (s * 0.10 - knee[0]) * (zz - knee[2]) / (hip_z - knee[2]), knee[1], zz])
            c, r = S.centre(guess, (0, 0, 1), rmax=0.12, max_rad=0.075, closed=True)
            if c is not None:
                cs.append(c)
        tops[sd] = np.mean(cs, 0) if cs else np.array([s * 0.10, knee[1], crotch - 0.06])
    # symmetric hip joints about the pelvis centre (the TRELLIS stance is a little asymmetric)
    hx = {}
    for s, sd in ((1, "l"), (-1, "r")):
        knee = J["calf_" + sd]
        d = _norm(tops[sd] - knee)
        hx[sd] = knee + d * (hip_z - knee[2]) / d[2]
    cx = (hx["l"][0] + hx["r"][0]) / 2
    half = max(0.085, min(0.11, (hx["l"][0] - hx["r"][0]) / 2))
    hy = (hx["l"][1] + hx["r"][1]) / 2
    J["thigh_l"] = np.array([cx + half, hy, hip_z])
    J["thigh_r"] = np.array([cx - half, hy, hip_z])
    log(f"hips: crotch {crotch:.3f}, thigh tops l {np.round(tops['l'], 3)} r {np.round(tops['r'], 3)} -> "
        f"hip_l {np.round(J['thigh_l'], 3)} hip_r {np.round(J['thigh_r'], 3)}")
    # ---------------------------------------------------------------- torso (horizontal sections around x=0)
    sp = {}
    for zz in (0.92, 0.98, 1.06, 1.14, 1.22, 1.30, 1.36):
        segs = S.cut(np.array([0, 0, zz]), (0, 0, 1), rmax=0.25)
        P = segs.reshape(-1, 3) if len(segs) else np.zeros((0, 3))
        P = P[np.abs(P[:, 0]) < 0.05]
        if len(P) == 0:
            continue
        front, back = P[:, 1].min(), P[:, 1].max()
        sp[zz] = (front, back)
    def spine_y(zz):
        ks = sorted(sp)
        fr = np.interp(zz, ks, [sp[k][0] for k in ks])
        bk = np.interp(zz, ks, [sp[k][1] for k in ks])
        return fr + 0.60 * (bk - fr)
    hipc = (J["thigh_l"] + J["thigh_r"]) / 2
    J["pelvis"] = np.array([0.0, hipc[1], hip_z + 0.02])
    for name, zz in (("spine_01", 0.985), ("spine_02", 1.105), ("spine_03", 1.235)):
        J[name] = np.array([0.0, spine_y(zz), zz])
    # neck: mock-neck section
    nz = []
    for zz in (1.43, 1.45, 1.47):
        c, r = S.centre(np.array([0.0, 0.02, zz]), (0, 0, 1), rmax=0.07, pick="near")
        if c is not None:
            nz.append(c)
    nc = np.mean(nz, 0) if nz else np.array([0, 0.02, 1.45])
    J["neck_01"] = np.array([0.0, nc[1] + 0.004, 1.395])
    J["head"] = np.array([0.0, nc[1] + 0.006, 1.480])
    J["_head_top"] = np.array([0.0, nc[1], co[:, 2].max()])
    log(f"spine: pelvis {np.round(J['pelvis'], 3)} s1 {np.round(J['spine_01'], 3)} s3 {np.round(J['spine_03'], 3)} "
        f"neck {np.round(J['neck_01'], 3)} head {np.round(J['head'], 3)}")
    # ---------------------------------------------------------------- arms
    for s, sd in ((1, "l"), (-1, "r")):
        arm = (s * x > 0.20 + np.maximum(0, 1.0 - z) * 0.6) & (z > 0.75) & (z < 1.42)
        P = co[arm]
        tip = P[np.argmax(s * P[:, 0] - P[:, 2] * 0.6)]
        top = (s * x > 0.13) & (s * x < 0.19) & (z > 1.33) & (z < 1.42)
        sh = np.array([s * 0.168, np.median(y[top]), 1.362])
        L = np.linalg.norm(tip - sh)
        wr = tip + (sh - tip) / L * 0.19
        for _ in range(2):
            # wrist: narrowest closed section 0.15..0.23 m back from the fingertip
            best = None
            dirw = _norm(tip - wr)
            for back in np.arange(0.15, 0.235, 0.008):
                p = tip - dirw * back
                c, r = S.centre(p, dirw, rmax=0.08, max_rad=0.05, closed=True)
                if c is not None and (best is None or r < best[1]):
                    best = (c, r, back)
            if best is not None:
                wr = best[0]
            # elbow: section centroid at 53 % shoulder->wrist
            el = sh + (wr - sh) * 0.53
            c, r = S.centre(el, _norm(wr - sh), rmax=0.10, max_rad=0.07, closed=True)
            if c is None:
                c, r = S.centre(el, _norm(wr - sh), rmax=0.10, max_rad=0.07)
            if c is not None:
                el = c
            # shoulder: section 0.07 down the upper arm, moved back up along the upper arm direction
            ua = _norm(el - sh)
            c, r = S.centre(sh + ua * 0.07, ua, rmax=0.09, max_rad=0.065, closed=True)
            if c is not None:
                sh = c - ua * 0.07
                sh[0] = s * max(abs(sh[0]), 0.160)
                sh[2] = min(max(sh[2], 1.345), 1.38)
        elbow = el.copy()
        elbow[1] += 0.006                         # joint toward the back of the arm (elbow point)
        J["upperarm_" + sd] = sh
        J["lowerarm_" + sd] = elbow
        J["hand_" + sd] = wr
        J["_tip_" + sd] = tip
        J["clavicle_" + sd] = np.array([s * 0.022, sh[1] - 0.004, sh[2] + 0.018])
        log(f"arm {sd}: shoulder {np.round(sh, 3)} elbow {np.round(elbow, 3)} wrist {np.round(wr, 3)} "
            f"tip {np.round(tip, 3)}")
        J.update(find_fingers(co, wr, tip, s, sd, log))
    # shoulders (review round 2): the upper-arm sections put her left shoulder joint 4 cm behind her right one
    # (the TRELLIS left arm hung back), although the shoulder girdle itself is symmetric. Both shoulder joints go to
    # the mid-depth of the upper torso beside the armpit (left side, clear of the ponytail), at the mean |x| / z.
    segs = S.cut(np.array([0.14, 0.03, 1.31]), (0, 0, 1), rmax=0.25)
    P = segs.reshape(-1, 3) if len(segs) else np.zeros((0, 3))
    P = P[(P[:, 0] > 0.12) & (P[:, 0] < 0.15)]
    if len(P) > 4:
        ym = 0.5 * (P[:, 1].min() + P[:, 1].max())
        hx = 0.5 * (abs(J["upperarm_l"][0]) + abs(J["upperarm_r"][0]))
        hz = 0.5 * (J["upperarm_l"][2] + J["upperarm_r"][2])
        for s, sd in ((1, "l"), (-1, "r")):
            J["upperarm_" + sd] = np.array([s * hx, ym, hz])
            J["clavicle_" + sd] = np.array([s * 0.022, ym - 0.004, hz + 0.018])
        log(f"shoulders symmetrised: (+-{hx:.3f}, {ym:.3f}, {hz:.3f})")
    return J


def find_fingers(co, wrist, tip, s, sd, log=print):
    """Finger chains from the hand verts: fingers are clustered across the hand (e2) beyond the knuckle line, the
    thumb is the cluster that leaves the hand on the thumb side near the wrist."""
    J = {}
    x, y, z = co.T
    d = co - wrist
    e1 = _norm(tip - wrist)
    t = d @ e1
    Lh = t.max() if False else np.linalg.norm(tip - wrist)
    hand = (t > -0.005) & (np.linalg.norm(d - np.outer(t, e1), axis=1) < 0.075) & (t < Lh + 0.02)
    H = co[hand]
    Hc = H.mean(0)
    u, sv, vt = np.linalg.svd(H - Hc, full_matrices=False)
    e3 = vt[2]                               # palm normal (thickness)
    e2 = _norm(np.cross(e3, e1))
    # thumb side = the side facing forward (-Y)
    if e2[1] > 0:
        e2 = -e2
        e3 = -e3
    th = (H - wrist) @ e1
    w2 = (H - wrist) @ e2
    w3 = (H - wrist) @ e3
    # knuckle line ~ 45 % of the hand length; fingers beyond it
    fing = th > 0.46 * Lh
    F = H[fing]
    fw = w2[fing]
    # 1D k-means into 4 fingers across the hand (thumb excluded: it does not reach this far)
    qs = np.percentile(fw, [12, 37, 63, 88])
    for _ in range(30):
        lab = np.argmin(np.abs(fw[:, None] - qs[None, :]), axis=1)
        qs = np.array([fw[lab == k].mean() if np.any(lab == k) else qs[k] for k in range(4)])
    order = np.argsort(-qs)                  # most thumb-side first: index, middle, ring, pinky
    names = ["index", "middle", "ring", "pinky"]
    kn = 0.44 * Lh
    for nm, k in zip(names, order):
        Pk = F[lab == k]
        if len(Pk) < 6:
            continue
        tk = (Pk - wrist) @ e1
        wk = (Pk - wrist) @ e2
        hk = (Pk - wrist) @ e3
        b, a0 = np.polyfit(tk, wk, 1)
        tipk = Pk[np.argmax(tk)]
        basek = wrist + e1 * kn + e2 * (a0 + b * kn) + e3 * np.median(hk)
        seg = tipk - basek
        J[f"{nm}_01_{sd}"] = basek
        J[f"{nm}_02_{sd}"] = basek + seg * 0.45
        J[f"{nm}_03_{sd}"] = basek + seg * 0.75
        J[f"_{nm}_tip_{sd}"] = tipk - seg * 0.06
    # thumb: verts that leave the palm plane on the thumb side between the wrist and the knuckles
    idx_w = qs[order[0]]
    h0 = np.median(w3)
    zone = (th > 0.0) & (th < 0.55 * Lh) & (w2 > 0.012)
    sgn = 1.0 if np.sum(zone & (w3 - h0 > 0.018)) >= np.sum(zone & (w3 - h0 < -0.018)) else -1.0
    thumb = zone & (sgn * (w3 - h0) > 0.018)
    T = H[thumb]
    if len(T) > 8:
        tw3 = (T - wrist) @ e3
        tb = wrist + e1 * (0.10 * Lh) + e2 * 0.022 + e3 * (h0 + 0.35 * (np.median(tw3) - h0))
        score = sgn * (tw3 - h0) + 0.5 * ((T - wrist) @ e1)
        ttip = T[np.argmax(score)]
        seg = ttip - tb
        J[f"thumb_01_{sd}"] = tb
        J[f"thumb_02_{sd}"] = tb + seg * 0.42
        J[f"thumb_03_{sd}"] = tb + seg * 0.72
        J[f"_thumb_tip_{sd}"] = ttip - seg * 0.06
    J[f"_hand_e2_{sd}"] = e2
    J[f"_hand_e3_{sd}"] = e3
    log(f"hand {sd}: fingers at e2 {np.round(np.sort(qs)[::-1], 3)}, thumb verts {len(T)}")
    return J
