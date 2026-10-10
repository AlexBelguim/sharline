"""Review pass 2: independent weight sanity checks on kestrel.blend (read-only).

- far-field weights: vertices with weight > 0.05 on a bone but far from that bone's segment
- rigid-part claims from NOTES (chest plate, jet pack, holster, pouches, eyepiece)
- left/right weight symmetry
"""
import sys
sys.dont_write_bytecode = True
import bpy
import numpy as np
from mathutils import Vector

bpy.ops.wm.open_mainfile(filepath=r"F:/git/val etf/assets/characters/kestrel/kestrel.blend")
arm = bpy.data.objects["KES_Armature"]
body = bpy.data.objects["KES_Body"]
me = body.data
nv = len(me.vertices)
co = np.zeros(nv * 3)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)
gname = {g.index: g.name for g in body.vertex_groups}
names = [b.name for b in arm.data.bones]
W = np.zeros((nv, len(names)))
bi = {n: i for i, n in enumerate(names)}
for v in me.vertices:
    for g in v.groups:
        W[v.index, bi[gname[g.group]]] = g.weight


def P(*a):
    print("[RV2]", *a)


def seg_dist(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab[None]), axis=1)


P("=== far-field weights (w>0.05 and > X m from the bone segment)")
for n in names:
    b = arm.data.bones[n]
    a = np.array(b.head_local)
    t = np.array(b.tail_local)
    m = W[:, bi[n]] > 0.05
    if not m.any():
        continue
    d = seg_dist(co[m], a, t)
    lim = 0.12 if n not in ("spine_03", "spine_02", "pelvis", "head", "spine_01") else 0.30
    far = d > lim
    if far.any():
        pts = co[m][far]
        P(f"{n:12s} {far.sum():5d} verts > {lim:.2f} m away (max {d.max():.3f} m, max w {W[m, bi[n]][far].max():.2f}); "
          f"bbox {pts.min(0).round(3)} .. {pts.max(0).round(3)}")

P("=== lower-arm influence on the torso (|x| < 0.27, z 1.05-1.40)")
for s, sx in (("l", 1), ("r", -1)):
    for bn in (f"lowerarm_{s}", f"hand_{s}"):
        m = (np.abs(co[:, 0]) < 0.27) & (co[:, 2] > 1.05) & (co[:, 2] < 1.40) & (W[:, bi[bn]] > 0.03)
        P(f"{bn}: {m.sum()} torso verts, max w {W[m, bi[bn]].max() if m.any() else 0:.2f}, "
          f"bbox {co[m].min(0).round(3) if m.any() else '-'} .. {co[m].max(0).round(3) if m.any() else '-'}")


def region(label, mask):
    idx = np.where(mask)[0]
    tot = W[idx].sum(0)
    order = np.argsort(-tot)[:6]
    P(f"{label}: {len(idx)} verts; " + ", ".join(f"{names[i]} mean {W[idx, i].mean():.2f} max {W[idx, i].max():.2f}"
                                                for i in order if tot[i] > 0))


P("=== rigid-part claims")
x, y, z = co[:, 0], co[:, 1], co[:, 2]
region("chest plate L edge (0.08<x<0.14, y<-0.08, 1.19<z<1.33)", (x > 0.08) & (x < 0.14) & (y < -0.08) & (z > 1.19) & (z < 1.33))
region("chest plate R edge (-0.14<x<-0.08, y<-0.08, 1.19<z<1.33)", (x > -0.14) & (x < -0.08) & (y < -0.08) & (z > 1.19) & (z < 1.33))
region("holster (x<-0.17, 0.62<z<0.85)", (x < -0.17) & (z > 0.62) & (z < 0.85) & (np.abs(y) < 0.12))
region("belt pouch L (x>0.1, y<-0.05, 0.9<z<1.0)", (x > 0.1) & (y < -0.05) & (z > 0.9) & (z < 1.0))
region("jet pack pods low (y>0.18, 1.0<z<1.15)", (y > 0.18) & (z > 1.0) & (z < 1.15))

P("=== L/R weight symmetry (mirror vertex match within 4 mm)")
from mathutils import kdtree
kd = kdtree.KDTree(nv)
for i, c in enumerate(co):
    kd.insert(c, i)
kd.balance()
pairs = {}
for n in names:
    if n.endswith("_l"):
        pairs[bi[n]] = bi[n[:-2] + "_r"]
perm = np.arange(len(names))
for a, b in pairs.items():
    perm[a] = b
    perm[b] = a
diffs = []
sample = np.where((np.abs(x) > 0.05) & (np.abs(x) < 0.45))[0][::7]
for i in sample:
    c = co[i].copy()
    c[0] = -c[0]
    _, j, d = kd.find(c)
    if d < 0.004:
        diffs.append(np.abs(W[i] - W[j][perm]).sum() / 2)
diffs = np.array(diffs)
P(f"matched {len(diffs)} mirror pairs; weight difference mean {diffs.mean():.3f}, p95 {np.percentile(diffs, 95):.3f}, >0.3: {(diffs > 0.3).sum()}")
