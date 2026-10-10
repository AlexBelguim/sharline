"""Independent review of SOLACE: technical checks on the exported GLB imported into a fresh Blender scene.

blender -b --factory-startup -P rv_tech.py
Read-only on the asset. Prints facts; writes nothing except stdout.
"""
import math
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

GLB = r"F:/git/val etf/assets/characters/solace/solace.glb"
FBX = r"F:/git/val etf/assets/characters/solace/solace.fbx"


def P(*a):
    print("[RV]", *a)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
objs = list(bpy.context.scene.objects)
P("objects", len(objs))
for o in sorted(objs, key=lambda o: o.name):
    P("  %-22s %-8s parent=%-16s ptype=%-6s pbone=%-10s loc=%s" % (
        o.name, o.type, o.parent.name if o.parent else "-", o.parent_type, o.parent_bone,
        tuple(round(v, 4) for v in o.matrix_world.translation)))

arm = next(o for o in objs if o.type == "ARMATURE")
bones = arm.data.bones
P("bones", len(bones))
UE = ["root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head"]
for s in "lr":
    UE += [f"clavicle_{s}", f"upperarm_{s}", f"lowerarm_{s}", f"hand_{s}", f"thigh_{s}", f"calf_{s}", f"foot_{s}", f"ball_{s}"]
    for f in ("thumb", "index", "middle", "ring", "pinky"):
        UE += [f"{f}_0{i}_{s}" for i in (1, 2, 3)]
missing = [n for n in UE if n not in bones]
extra = [b.name for b in bones if b.name not in UE]
P("missing UE5 names", missing, "extra", extra)
# hierarchy check
exp_parent = {"pelvis": "root", "spine_01": "pelvis", "spine_02": "spine_01", "spine_03": "spine_02",
              "neck_01": "spine_03", "head": "neck_01", "clavicle_l": "spine_03", "clavicle_r": "spine_03",
              "upperarm_l": "clavicle_l", "lowerarm_l": "upperarm_l", "hand_l": "lowerarm_l",
              "thigh_l": "pelvis", "calf_l": "thigh_l", "foot_l": "calf_l", "ball_l": "foot_l"}
for c, p in exp_parent.items():
    b = bones.get(c)
    if b and (b.parent.name if b.parent else None) != p:
        P("HIERARCHY MISMATCH", c, "parent", b.parent.name if b.parent else None, "expected", p)

# L/R joint symmetry
P("joint symmetry (head positions, L vs mirrored R):")
for n in ["clavicle", "upperarm", "lowerarm", "hand", "thigh", "calf", "foot", "ball", "index_01", "thumb_01"]:
    bl, br = bones.get(n + "_l"), bones.get(n + "_r")
    if bl and br:
        hl = arm.matrix_world @ bl.head_local
        hr = arm.matrix_world @ br.head_local
        d = hl - Vector((-hr.x, hr.y, hr.z))
        P("  %-9s L %s  R %s  asym %.3f m" % (n, tuple(round(v, 3) for v in hl), tuple(round(v, 3) for v in hr), d.length))

# ---------------------------------------------------------------------------------------- meshes
dg = bpy.context.evaluated_depsgraph_get()
tot = 0
body = None
for o in sorted([o for o in objs if o.type == "MESH"], key=lambda o: o.name):
    me = o.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    tot += tris
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.edges.ensure_lookup_table()
    nonman = sum(1 for e in bm.edges if not e.is_manifold)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    wire = sum(1 for e in bm.edges if e.is_wire)
    # inconsistent winding: an interior edge whose two faces traverse it in the same direction
    incons = 0
    for e in bm.edges:
        if len(e.link_faces) == 2:
            f1, f2 = e.link_faces
            def dirn(f):
                vs = [v.index for v in f.verts]
                i = vs.index(e.verts[0].index)
                return vs[(i + 1) % len(vs)] == e.verts[1].index
            if dirn(f1) == dirn(f2):
                incons += 1
    degenerate = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
    # islands
    bm.verts.ensure_lookup_table()
    seen = set()
    islands = []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack = [v]
        seen.add(v.index)
        cnt = 0
        while stack:
            x = stack.pop()
            cnt += 1
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index)
                    stack.append(y)
        islands.append(cnt)
    islands.sort(reverse=True)
    small = sum(1 for c in islands if c < 12)
    bm.free()
    uvs = [l.name for l in me.uv_layers]
    mats = [m.name if m else None for m in me.materials]
    P("mesh %-18s tris %6d verts %6d nonmanifold %5d boundary %5d wire %d incons-winding %d degenerate %d islands %d (small<12v: %d) top %s uv %s mats %s" % (
        o.name, tris, len(me.vertices), nonman, boundary, wire, incons, degenerate, len(islands), small, islands[:6], uvs, mats))
    if o.name == "SOL_Body":
        body = o
P("TOTAL TRIS", tot)

# bbox in rest
allco = []
for o in objs:
    if o.type == "MESH":
        oe = o.evaluated_get(dg)
        m = oe.to_mesh()
        allco += [o.matrix_world @ v.co for v in m.vertices]
        oe.to_mesh_clear()
A = np.array([tuple(v) for v in allco])
P("bbox min", A.min(0).round(4), "max", A.max(0).round(4), "dims", (A.max(0) - A.min(0)).round(4))

# ---------------------------------------------------------------------------------------- weights
names = [g.name for g in body.vertex_groups]
V = len(body.data.vertices)
W = np.zeros((V, len(names)))
for v in body.data.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
co = np.array([v.co[:] for v in body.data.vertices])
co = (np.array(body.matrix_world) @ np.c_[co, np.ones(V)].T).T[:, :3]
idx = {n: i for i, n in enumerate(names)}
# cross-side contamination
for side, sgn in (("_l", 1), ("_r", -1)):
    other = [i for n, i in idx.items() if n.endswith("_r" if side == "_l" else "_l")]
    mask = co[:, 0] * sgn > 0.06
    bad = mask & (W[:, other].sum(1) > 0.05)
    P(f"verts at {'+' if sgn > 0 else '-'}X>0.06 with >5% weight on opposite-side bones: {int(bad.sum())}")
    if bad.sum():
        P("   sample", co[bad][:5].round(3).tolist())
# leg weights on arm bones and vice versa
arm_b = [i for n, i in idx.items() if any(n.startswith(k) for k in ("upperarm", "lowerarm", "hand", "thumb", "index", "middle", "ring", "pinky"))]
leg_b = [i for n, i in idx.items() if any(n.startswith(k) for k in ("thigh", "calf", "foot", "ball"))]
m = (co[:, 2] < 0.80) & (W[:, arm_b].sum(1) > 0.02)
P("verts below Z 0.80 with arm/hand weight >2%:", int(m.sum()), co[m][:5].round(3).tolist())
m = (co[:, 2] > 1.05) & (W[:, leg_b].sum(1) > 0.02)
P("verts above Z 1.05 with leg weight >2%:", int(m.sum()), co[m][:5].round(3).tolist())
# head weight on body below the collar
hi = idx.get("head")
m = (co[:, 2] < 1.30) & (W[:, hi] > 0.05)
P("verts below Z 1.30 with head weight >5% (ponytail expected):", int(m.sum()))
# finger weights reaching the wrist/forearm
fing = [i for n, i in idx.items() if any(n.startswith(k) for k in ("thumb", "index", "middle", "ring", "pinky"))]
for s, hand in (("l", "hand_l"), ("r", "hand_r")):
    hb = arm.data.bones[hand]
    hh = arm.matrix_world @ hb.head_local
    ht = arm.matrix_world @ hb.tail_local
    ax = (ht - hh).normalized()
    t = (co - np.array(hh)) @ np.array(ax)
    f_s = [i for n, i in idx.items() if n.endswith("_" + s) and i in fing]
    m = (t < -0.02) & (W[:, f_s].sum(1) > 0.05)
    P(f"hand_{s}: verts >2cm behind the wrist with finger weight >5%:", int(m.sum()))
# bones with no weights
used = (W > 0.001).sum(0)
P("deform bones with zero weighted verts:", [n for n in names if used[idx[n]] == 0])
P("bones without a vertex group:", [b.name for b in bones if b.name not in idx])
# influences
nz = (W > 0.001).sum(1)
P("max influences", nz.max(), "unweighted verts", int((W.sum(1) < 1e-4).sum()))

# ---------------------------------------------------------------------------------------- sockets
def nearest_dist(obj, p):
    oe = obj.evaluated_get(dg)
    m = oe.to_mesh()
    bvh = BVHTree.FromPolygons([obj.matrix_world @ v.co for v in m.vertices], [tuple(p.vertices) for p in m.polygons])
    oe.to_mesh_clear()
    loc, nrm, i, d = bvh.find_nearest(p)
    return d, loc


for o in objs:
    if "SOCKET" in o.name:
        p = o.matrix_world.translation
        d, loc = nearest_dist(body, p)
        R = o.matrix_world.to_3x3()
        P("socket %-20s pos %s  nearest body surface %.3f m  axes X%s Y%s Z%s" % (
            o.name, tuple(round(v, 4) for v in p), d, tuple(round(v, 2) for v in R.col[0]),
            tuple(round(v, 2) for v in R.col[1]), tuple(round(v, 2) for v in R.col[2])))
# head top
head_top = A[:, 2].max()
hz = bpy.data.objects.get("SOL_SOCKET_Halo")
if hz:
    P("halo socket height above model top: %.3f" % (hz.matrix_world.translation.z - head_top))
# hand surfaces around the weapon sockets: palm normal sanity -- cast rays from the socket in +-Z, +-X
for nm in ("SOL_SOCKET_WeaponR", "SOL_SOCKET_WeaponL"):
    s = bpy.data.objects.get(nm)
    if not s:
        continue
    oe = body.evaluated_get(dg)
    m = oe.to_mesh()
    bvh = BVHTree.FromPolygons([body.matrix_world @ v.co for v in m.vertices], [tuple(p.vertices) for p in m.polygons])
    oe.to_mesh_clear()
    R = s.matrix_world.to_3x3()
    p = s.matrix_world.translation
    for lab, d in (("+X", R.col[0]), ("-X", -R.col[0]), ("+Z", R.col[2]), ("-Z", -R.col[2]), ("-Y", -R.col[1]), ("+Y", R.col[1])):
        hit = bvh.ray_cast(p, d, 0.3)
        P("   %s ray %s: hit %s" % (nm, lab, "%.3f" % hit[3] if hit[0] else "none"))

# ---------------------------------------------------------------------------------------- bloom clearances
def bvh_of(o):
    oe = o.evaluated_get(dg)
    m = oe.to_mesh()
    b = BVHTree.FromPolygons([o.matrix_world @ v.co for v in m.vertices], [tuple(p.vertices) for p in m.polygons])
    oe.to_mesh_clear()
    return b


bb = bvh_of(body)
for nm in ("SOL_Bloom", "SOL_Bloom_Vane_C", "SOL_Bloom_Vane_L", "SOL_Bloom_Vane_R", "SOL_Gear"):
    o = bpy.data.objects.get(nm)
    if not o:
        continue
    ov = bb.overlap(bvh_of(o))
    P("overlap body x %-18s : %d face pairs" % (nm, len(ov)))
    if ov:
        me = body.data
        cs = np.array([tuple(body.matrix_world @ me.polygons[a].center) for a, b in ov])
        P("    body faces involved: z range %.3f-%.3f, x %.3f-%.3f, y %.3f-%.3f" % (
            cs[:, 2].min(), cs[:, 2].max(), cs[:, 0].min(), cs[:, 0].max(), cs[:, 1].min(), cs[:, 1].max()))
# vane vs vane overlap
vs = [bpy.data.objects.get(n) for n in ("SOL_Bloom_Vane_C", "SOL_Bloom_Vane_L", "SOL_Bloom_Vane_R")]
for i in range(3):
    for j in range(i + 1, 3):
        P("overlap %s x %s: %d" % (vs[i].name, vs[j].name, len(bvh_of(vs[i]).overlap(bvh_of(vs[j])))))
# vane extras
for v in vs:
    P("vane", v.name, {k: v[k] for k in v.keys() if not k.startswith("_")})

# open state: rotate each vane about local X by its open angle and test overlap with body and with arms raised
for v in vs:
    ang = v.get("open_angle_deg", 30)
    v.rotation_mode = "QUATERNION"
    from mathutils import Quaternion
    v.rotation_quaternion = v.rotation_quaternion @ Quaternion((1, 0, 0), math.radians(ang))
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
for v in vs:
    ob = bvh_of(v)
    P("OPEN overlap body x %s: %d" % (v.name, len(bb.overlap(ob))))
    oe = v.evaluated_get(dg)
    m = oe.to_mesh()
    c = np.array([tuple(v.matrix_world @ x.co) for x in m.vertices])
    oe.to_mesh_clear()
    P("   open bbox min", c.min(0).round(3), "max", c.max(0).round(3))

# ---------------------------------------------------------------------------------------- texture colours
img = None
mat = bpy.data.materials.get("M_SOL_Body")
for n in mat.node_tree.nodes:
    if n.type == "TEX_IMAGE" and "Base" in n.image.name:
        img = n.image
if img is None:
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE":
            P("tex node", n.image.name)
P("base image", img.name if img else None, img.size[:] if img else None, img.colorspace_settings.name if img else None)
if img:
    w, h = img.size
    px = np.array(img.pixels[:]).reshape(h, w, 4)
    me = body.data
    uv = me.uv_layers.active.data
    # per-loop sample
    def region(pred, label):
        cols = []
        for poly in me.polygons:
            if me.materials[poly.material_index].name != "M_SOL_Body":
                continue
            c = body.matrix_world @ poly.center
            if not pred(c, poly):
                continue
            for li in poly.loop_indices:
                u, vv = uv[li].uv
                x = min(w - 1, max(0, int(u * w)))
                y = min(h - 1, max(0, int(vv * h)))
                cols.append(px[y, x, :3])
        cols = np.array(cols)
        med = np.median(cols, 0)
        P("region %-28s n %5d median sRGB %s" % (label, len(cols), med.round(3)))
    nrm = lambda poly: body.matrix_world.to_3x3() @ poly.normal
    region(lambda c, p: 0.30 < c.z < 0.42 and c.y < 0 and (nrm(p)).y < -0.5, "pants front shin")
    region(lambda c, p: 0.55 < c.z < 0.75 and c.y < 0 and (nrm(p)).y < -0.5 and abs(c.x) < 0.15, "pants front thigh")
    region(lambda c, p: 0.55 < c.z < 0.75 and c.y > 0.04 and (nrm(p)).y > 0.5, "back thigh/tail")
    region(lambda c, p: 1.10 < c.z < 1.30 and c.y < 0 and (nrm(p)).y < -0.6 and abs(c.x) < 0.12, "jacket chest")
    region(lambda c, p: 1.10 < c.z < 1.30 and c.y > 0.05 and (nrm(p)).y > 0.6 and abs(c.x) < 0.15, "jacket back")
    region(lambda c, p: 1.45 < c.z < 1.52 and c.y < -0.05 and abs(c.x) < 0.04, "lower face (atlas)")
    region(lambda c, p: 1.40 < c.z < 1.46 and c.y < -0.0 and abs(c.x) < 0.04, "neck front")
    region(lambda c, p: 1.62 < c.z and c.y > 0.0, "hair crown back")
    region(lambda c, p: 0.02 < c.z < 0.10, "boots")
    region(lambda c, p: 0.98 < c.z < 1.0 and c.y < -0.05 and abs(c.x) < 0.06, "belt front")
P("palette sRGB refs: ivory", np.round(np.array([0.70, 0.67, 0.60]) ** (1 / 2.2), 3),
  "sand", np.round(np.array([0.36, 0.28, 0.18]) ** (1 / 2.2), 3),
  "skin deep", np.round(np.array([0.26, 0.14, 0.085]) ** (1 / 2.2), 3),
  "charcoal", np.round(np.array([0.035, 0.037, 0.045]) ** (1 / 2.2), 3))
fimg = None
fm = bpy.data.materials.get("M_SOL_Face")
for n in fm.node_tree.nodes:
    if n.type == "TEX_IMAGE":
        P("face tex node", n.image.name, n.image.size[:])
        if "ORM" not in n.image.name:
            fimg = n.image
if fimg:
    w, h = fimg.size
    px = np.array(fimg.pixels[:]).reshape(h, w, 4)
    c = px[int(h * 0.3):int(h * 0.7), int(w * 0.3):int(w * 0.7), :3].reshape(-1, 3)
    P("face texture centre median sRGB", np.median(c, 0).round(3))
# ORM metal channel
for n in mat.node_tree.nodes:
    if n.type == "TEX_IMAGE" and "ORM" in n.image.name:
        w, h = n.image.size
        px = np.array(n.image.pixels[:]).reshape(h, w, 4)
        P("ORM", n.image.name, "R mean %.3f G(rough) min %.3f mean %.3f B(metal) max %.3f" % (
            px[..., 0].mean(), px[..., 1].min(), px[..., 1].mean(), px[..., 2].max()))

# ---------------------------------------------------------------------------------------- FBX load
bpy.ops.wm.read_factory_settings(use_empty=True)
try:
    bpy.ops.import_scene.fbx(filepath=FBX)
    fo = list(bpy.context.scene.objects)
    P("FBX imported:", len(fo), "objects:", sorted(o.name for o in fo))
    a = next((o for o in fo if o.type == "ARMATURE"), None)
    P("FBX bones", len(a.data.bones) if a else None, "leaf bones:", [b.name for b in a.data.bones if b.name.endswith("_end")] if a else None)
    for o in fo:
        if o.type == "MESH":
            P("  FBX mesh %s dims %s mats %s" % (o.name, tuple(round(x, 3) for x in o.dimensions), [m.name for m in o.data.materials]))
        if "SOCKET" in o.name or "Vane" in o.name:
            P("  FBX node %s parent %s/%s props %s" % (o.name, o.parent.name if o.parent else None, o.parent_bone,
                                                       {k: o[k] for k in o.keys()}))
except Exception as e:
    P("FBX import FAILED", e)
P("done")
