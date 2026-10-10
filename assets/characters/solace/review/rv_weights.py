"""Independent review of SOLACE: weight / joint-placement details on the exported glb. Prints only."""
import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

GLB = r"F:/git/val etf/assets/characters/solace/solace.glb"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
arm = bpy.data.objects["SOL_Armature"]
body = bpy.data.objects["SOL_Body"]
names = [g.name for g in body.vertex_groups]
idx = {n: i for i, n in enumerate(names)}
V = len(body.data.vertices)
W = np.zeros((V, len(names)))
for v in body.data.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
co = np.array([tuple(body.matrix_world @ v.co) for v in body.data.vertices])


def P(*a):
    print("[RW]", *a)


# leg weights high on the torso
leg = [i for n, i in idx.items() if n.startswith(("thigh", "calf"))]
for z0 in (0.95, 1.0, 1.05, 1.10, 1.15):
    m = (co[:, 2] > z0) & (W[:, leg].sum(1) > 0.05)
    P(f"verts above Z {z0} with thigh/calf weight >5%: {int(m.sum())}  max weight {W[m][:, leg].sum(1).max() if m.any() else 0:.2f}")
m = (co[:, 2] > 1.05) & (W[:, leg].sum(1) > 0.05)
if m.any():
    c = co[m]
    P("   where:", "x", c[:, 0].min().round(3), c[:, 0].max().round(3), "y", c[:, 1].min().round(3), c[:, 1].max().round(3),
      "z", c[:, 2].min().round(3), c[:, 2].max().round(3))
# cross-side detail on the coat tail
for side, sgn in (("l", 1), ("r", -1)):
    opp = [i for n, i in idx.items() if n.endswith("_r" if side == "l" else "_l")]
    for x0 in (0.06, 0.09, 0.12):
        m = (co[:, 0] * sgn > x0) & (W[:, opp].sum(1) > 0.05)
        P(f"side {side}: |x|>{x0} with >5% opposite-side weight: {int(m.sum())}, max {W[m][:, opp].sum(1).max() if m.any() else 0:.2f}")
    m = (co[:, 0] * sgn > 0.09) & (W[:, opp].sum(1) > 0.05)
    if m.any():
        c = co[m]
        bones = sorted({names[j] for j in opp if (W[m][:, j] > 0.05).any()})
        P("   region x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f bones %s" % (c[:, 0].min(), c[:, 0].max(), c[:, 1].min(),
                                                                       c[:, 1].max(), c[:, 2].min(), c[:, 2].max(), bones))
# arm weights onto the torso side (armpit bleed): verts with |x| < 0.12 and upperarm weight
for s, sg in (("l", 1), ("r", -1)):
    ua = idx[f"upperarm_{s}"]
    m = (co[:, 0] * sg < 0.11) & (co[:, 2] < 1.25) & (W[:, ua] > 0.1)
    P(f"upperarm_{s} weight >10% on torso verts (|x|<0.11, z<1.25): {int(m.sum())}")
# spine/pelvis weights reaching the arms
for s, sg in (("l", 1), ("r", -1)):
    tor = [idx[n] for n in ("spine_01", "spine_02", "spine_03", "pelvis")]
    m = (co[:, 0] * sg > 0.30) & (W[:, tor].sum(1) > 0.1)
    P(f"torso weight >10% on arm verts beyond |x|>0.30 ({s}): {int(m.sum())}")

# joint centring: rays perpendicular to the bone from its head
me = body.data
bvh = BVHTree.FromPolygons([tuple(c) for c in co], [tuple(p.vertices) for p in me.polygons])
for bn in ("upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r", "thigh_l", "thigh_r",
           "calf_l", "calf_r", "foot_l", "foot_r", "neck_01", "head", "spine_03", "pelvis"):
    b = arm.data.bones[bn]
    h = arm.matrix_world @ b.head_local
    t = arm.matrix_world @ b.tail_local
    ax = (t - h).normalized()
    ref = Vector((0, 0, 1)) if abs(ax.z) < 0.9 else Vector((0, 1, 0))
    u = ax.cross(ref).normalized()
    v = ax.cross(u).normalized()
    ds = []
    for k in range(12):
        a = 2 * math.pi * k / 12
        d = u * math.cos(a) + v * math.sin(a)
        hit = bvh.ray_cast(h, d, 0.5)
        ds.append(hit[3] if hit[0] else float("nan"))
    ds = np.array(ds)
    opp = np.array([ds[k] - ds[(k + 6) % 12] for k in range(6)])
    P("joint %-11s head %s  ray dists min %.3f max %.3f  worst opposite imbalance %.3f m" % (
        bn, tuple(round(x, 3) for x in h), np.nanmin(ds), np.nanmax(ds), np.nanmax(np.abs(opp))))
# bone roll comparison L vs R (local X axis in world)
for n in ("upperarm", "lowerarm", "hand", "thigh", "calf", "foot"):
    bl, br = arm.data.bones[n + "_l"], arm.data.bones[n + "_r"]
    xl = (arm.matrix_world.to_3x3() @ bl.matrix_local.to_3x3()).col[0]
    xr = (arm.matrix_world.to_3x3() @ br.matrix_local.to_3x3()).col[0]
    zl = (arm.matrix_world.to_3x3() @ bl.matrix_local.to_3x3()).col[2]
    zr = (arm.matrix_world.to_3x3() @ br.matrix_local.to_3x3()).col[2]
    P("roll %-9s L x%s z%s | R x%s z%s" % (n, tuple(round(a, 2) for a in xl), tuple(round(a, 2) for a in zl),
                                         tuple(round(a, 2) for a in xr), tuple(round(a, 2) for a in zr)))
# small islands location summary
import bmesh
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
seen = np.zeros(V, bool)
small = []
for v in bm.verts:
    if seen[v.index]:
        continue
    stack = [v]
    seen[v.index] = True
    ids = []
    while stack:
        x = stack.pop()
        ids.append(x.index)
        for e in x.link_edges:
            y = e.other_vert(x)
            if not seen[y.index]:
                seen[y.index] = True
                stack.append(y)
    if len(ids) < 40:
        c = co[ids]
        small.append((len(ids), c.mean(0), (c.max(0) - c.min(0)).max()))
bm.free()
P("islands < 40 verts:", len(small))
zs = np.array([s[1][2] for s in small])
for lo, hi, lab in ((1.45, 2, "head/hair"), (1.0, 1.45, "torso/arms"), (0.5, 1.0, "hips/thighs"), (0, 0.5, "legs/feet")):
    sel = [s for s in small if lo <= s[1][2] < hi]
    P("   %-12s %3d islands, max extent %.3f m" % (lab, len(sel), max([s[2] for s in sel]) if sel else 0))
