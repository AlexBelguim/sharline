"""SOLACE - verification of the exported solace.glb (read-only; prints a report, writes nothing).

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup
      -P "F:/git/val etf/assets/characters/solace/check_solace.py"

Checks (review round 2):
  [RIG]   rest local rotations vs kestrel.glb (one glTF animation set must drive both agents; target < 10 deg on
          every non-finger joint)
  [CLIP]  hair/head region vs the Bloom vanes and module for head pitch 0..45 deg (split 45 % neck / 55 % head)
          and head yaw +-45..90 deg (face pairs overlapping; target 0)
  [WGT]   weight leaks: leg weight above the belt, cross-side weights, finger weight behind the wrist
  [OPEN]  vane extents at the open angles (L/R must not read as wings)
  [NODES] the drone / sockets hierarchy
  [SYM]   L/R rest joint symmetry
  [MESH]  triangles, degenerate faces and materials per mesh
"""
import json
import math
import struct

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

GLB = r"F:/git/val etf/assets/characters/solace/solace.glb"
KES = r"F:/git/val etf/assets/characters/kestrel/kestrel.glb"


def glb_json(p):
    b = open(p, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + jl])


def rest_locals(js):
    nodes = js["nodes"]
    return {nodes[j]["name"]: np.array(nodes[j].get("rotation", [0, 0, 0, 1]), float) for j in js["skins"][0]["joints"]}


def rig_compare():
    try:
        a, b = rest_locals(glb_json(GLB)), rest_locals(glb_json(KES))
    except FileNotFoundError as e:
        print("[RIG] skipped:", e)
        return
    worst = []
    for n, qa in a.items():
        if n not in b:
            continue
        qb = b[n]
        d = abs(float(np.dot(qa / np.linalg.norm(qa), qb / np.linalg.norm(qb))))
        ang = math.degrees(2 * math.acos(min(1.0, d)))
        finger = n.startswith(("index", "middle", "ring", "pinky", "thumb"))
        worst.append((ang, n, finger))
    body = sorted([w for w in worst if not w[2]], reverse=True)
    fing = sorted([w for w in worst if w[2]], reverse=True)
    print("[RIG] non-finger joints: max %.1f deg (%s), median %.1f, > 10 deg: %d / %d" % (
        body[0][0], body[0][1], float(np.median([w[0] for w in body])), sum(w[0] > 10 for w in body), len(body)))
    print("[RIG]   " + ", ".join("%s %.1f" % (w[1], w[0]) for w in body[:8]))
    print("[RIG] finger joints: max %.1f deg (%s), median %.1f" % (fing[0][0], fing[0][1],
                                                                  float(np.median([w[0] for w in fing]))))


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=GLB)
    return bpy.data.objects["SOL_Armature"]


def rot_world(arm, bone, axis, deg):
    pb = arm.pose.bones[bone]
    bpy.context.view_layer.update()
    M = arm.matrix_world @ pb.matrix
    h = M.translation.copy()
    R = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, Vector(axis)) @ Matrix.Translation(-h)
    pb.matrix = arm.matrix_world.inverted() @ (R @ M)
    bpy.context.view_layer.update()


def reset(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def bvh(o, zmin=None):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    m = oe.to_mesh()
    vs = [o.matrix_world @ v.co for v in m.vertices]
    polys = [tuple(p.vertices) for p in m.polygons if zmin is None or (o.matrix_world @ p.center).z > zmin]
    t = BVHTree.FromPolygons(vs, polys)
    oe.to_mesh_clear()
    return t


def clip_tests(arm):
    body = bpy.data.objects["SOL_Body"]
    parts = [bpy.data.objects[n] for n in ("SOL_Bloom_Vane_C", "SOL_Bloom_Vane_L", "SOL_Bloom_Vane_R", "SOL_Bloom")]
    cases = [("rest", 0, 0)] + [(f"look up {p}", p, 0) for p in (20, 30, 40, 45)] + \
            [(f"turn {'left' if y > 0 else 'right'} {abs(y)}", 0, y) for y in (45, -45, 70, -70, 90, -90)] + \
            [("up 25 + turn left 60", 25, 60), ("up 25 + turn right 60", 25, -60)]
    tot = 0
    for label, pitch, yaw in cases:
        reset(arm)
        if yaw:
            rot_world(arm, "neck_01", (0, 0, 1), yaw * 0.45)
            rot_world(arm, "head", (0, 0, 1), yaw * 0.55)
        if pitch:
            rot_world(arm, "neck_01", (1, 0, 0), -pitch * 0.45)
            rot_world(arm, "head", (1, 0, 0), -pitch * 0.55)
        hb = bvh(body, zmin=1.35)
        per = [len(hb.overlap(bvh(p))) for p in parts]
        tot += sum(per)
        print("[CLIP] %-24s overlaps (C, L, R, module) = %s" % (label, per))
    reset(arm)
    print("[CLIP] total overlapping face pairs:", tot)


def weights():
    body = bpy.data.objects["SOL_Body"]
    me = body.data
    names = [g.name for g in body.vertex_groups]
    W = np.zeros((len(me.vertices), len(names)))
    for v in me.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    co = np.array([body.matrix_world @ v.co for v in me.vertices])
    x, y, z = co.T
    col = {n: i for i, n in enumerate(names)}
    leg = W[:, [col[n] for n in names if n.startswith(("thigh", "calf", "foot", "ball"))]].sum(1)
    print("[WGT] leg weight above Z 1.05: %d verts (max %.3f); above Z 1.00: %d verts" % (
        int(((z > 1.05) & (leg > 0.01)).sum()), float(leg[z > 1.05].max(initial=0)), int(((z > 1.0) & (leg > 0.01)).sum())))
    for s, own, other in ((1, "l", "r"), (-1, "r", "l")):
        ow = W[:, [col[n] for n in names if n.endswith("_" + other)]].sum(1)
        m = (s * x > 0.06)
        print("[WGT] her %s side (|x| > 6 cm): %d verts with > 1 %% %s-side weight (max %.3f)" % (
            "left" if s > 0 else "right", int((m & (ow > 0.01)).sum()), other.upper(), float(ow[m].max(initial=0))))
    infl = (W > 1e-4).sum(1)
    print("[WGT] max influences %d, unweighted verts %d" % (int(infl.max()), int((W.sum(1) < 1e-4).sum())))


def open_extents():
    for nm in ("SOL_Bloom_Vane_C", "SOL_Bloom_Vane_L", "SOL_Bloom_Vane_R"):
        v = bpy.data.objects[nm]
        rest = v.matrix_basis.copy()
        ang = float(v.get("open_angle_deg", 0))
        v.matrix_basis = rest @ Matrix.Rotation(math.radians(ang), 4, "X")
        bpy.context.view_layer.update()
        P = np.array([v.matrix_world @ p.co for p in v.data.vertices])
        print("[OPEN] %s open %.0f deg: x %.3f..%.3f  y %.3f..%.3f  z %.3f..%.3f" % (
            nm, ang, P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(), P[:, 2].min(), P[:, 2].max()))
        v.matrix_basis = rest
    bpy.context.view_layer.update()


def symmetry(arm):
    """L/R rest joint symmetry (head positions; L vs mirrored R)."""
    bones = arm.data.bones
    worst = 0.0
    rows = []
    for n in ("clavicle", "upperarm", "lowerarm", "hand", "thigh", "calf", "foot", "ball"):
        hl = arm.matrix_world @ bones[n + "_l"].head_local
        hr = arm.matrix_world @ bones[n + "_r"].head_local
        d = (hl - Vector((-hr.x, hr.y, hr.z))).length
        worst = max(worst, d)
        rows.append("%s %.3f" % (n, d))
    print("[SYM] L/R joint asymmetry (m): " + ", ".join(rows) + "; max %.3f" % worst)


def mesh_stats():
    import bmesh
    tot = 0
    for o in sorted([o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("SOL_")], key=lambda o: o.name):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)      # undo the glTF split at UV seams
        deg = sum(1 for f in bm.faces if f.calc_area() < 1e-9)
        tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
        tot += tris
        print("[MESH] %-18s tris %6d  degenerate faces %d  materials %s" % (o.name, tris, deg,
                                                                         [m.name for m in o.data.materials]))
        bm.free()
    print("[MESH] total tris", tot)


def nodes():
    for n in ("SOL_Drone", "SOL_SOCKET_DroneDock", "SOL_SOCKET_Halo", "SOL_SOCKET_WeaponR", "SOL_SOCKET_WeaponL",
              "SOL_SOCKET_Injector", "SOL_SOCKET_BloomVFX"):
        o = bpy.data.objects.get(n)
        if o is None:
            print("[NODES] MISSING", n)
            continue
        print("[NODES] %-22s parent %-22s bone %-8s at %s" % (n, o.parent.name if o.parent else "-", o.parent_bone or "-",
                                                         tuple(round(c, 3) for c in o.matrix_world.translation)))


if __name__ == "__main__":
    rig_compare()
    arm = setup()
    nodes()
    symmetry(arm)
    mesh_stats()
    clip_tests(arm)
    weights()
    open_extents()
