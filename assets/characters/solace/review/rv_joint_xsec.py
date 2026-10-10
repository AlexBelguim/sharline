"""Independent review of SOLACE: compare joint positions with the mesh cross-section centroids (pure numpy, prints)."""
import numpy as np
import glb_inspect as G

js, binc, *_ = G.load(G.GLB)
nodes = js["nodes"]
prim = js["meshes"][[i for i, m in enumerate(js["meshes"]) if m["name"] == "SOL_Body"][0]]["primitives"]
P = np.vstack([G.acc(js, binc, p["attributes"]["POSITION"]).astype(float) for p in prim])
P = np.c_[P[:, 0], -P[:, 2], P[:, 1]]   # to Blender axes
J = {}
import json
# reuse world() from glb_inspect by re-implementing quickly
parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
def local(n):
    T = np.eye(4); x, y, z, w = n.get("rotation", [0, 0, 0, 1])
    T[:3, :3] = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    T[:3, 3] = n.get("translation", [0, 0, 0]); return T
def world(i):
    m = local(nodes[i]); return world(parent[i]) @ m if i in parent else m
for j in js["skins"][0]["joints"]:
    p = world(j)[:3, 3]; J[nodes[j]["name"]] = np.array([p[0], -p[2], p[1]])
def xsec(a, b, t, width=0.012, rad=0.12):
    """centroid of the mesh verts in a slab perpendicular to a->b at fraction t, within rad of the axis"""
    d = (b - a) / np.linalg.norm(b - a); c = a + (b - a) * t
    s = (P - c) @ d; r = np.linalg.norm((P - c) - np.outer(s, d), axis=1)
    m = (np.abs(s) < width) & (r < rad)
    return P[m].mean(0) if m.sum() > 10 else None, int(m.sum())
for side in "lr":
    for a, b, t, lab in (("upperarm", "lowerarm", 0.15, "upper arm near shoulder"), ("upperarm", "lowerarm", 1.0, "elbow"),
                         ("lowerarm", "hand", 1.0, "wrist"), ("thigh", "calf", 1.0, "knee"), ("calf", "foot", 1.0, "ankle")):
        A, B = J[f"{a}_{side}"], J[f"{b}_{side}"]
        c, n = xsec(A, B, t, rad=0.07 if lab != "knee" else 0.09)
        jp = A + (B - A) * t
        if c is not None:
            print("[RX] %s %-24s joint %s  section centroid %s  offset %.3f m (n=%d)" % (side, lab, jp.round(3), c.round(3), np.linalg.norm(c - jp), n))
print("[RX] shoulder Y: L %.3f R %.3f ; torso back/front Y at Z 1.30:" % (J["upperarm_l"][1], J["upperarm_r"][1]),
      P[(np.abs(P[:, 2] - 1.30) < 0.01) & (np.abs(P[:, 0]) < 0.05)][:, 1].min().round(3),
      P[(np.abs(P[:, 2] - 1.30) < 0.01) & (np.abs(P[:, 0]) < 0.05)][:, 1].max().round(3))
for side, sg in (("l", 1), ("r", -1)):
    m = (np.abs(P[:, 2] - 1.36) < 0.015) & (P[:, 0] * sg > 0.14) & (P[:, 0] * sg < 0.21)
    print("[RX] shoulder slab Z1.36 |x| .14-.21 side %s: Y range %.3f..%.3f centre %.3f" % (side, P[m][:, 1].min(), P[m][:, 1].max(), (P[m][:, 1].min() + P[m][:, 1].max()) / 2))
