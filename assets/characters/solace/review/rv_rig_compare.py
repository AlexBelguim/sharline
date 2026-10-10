"""Independent review of SOLACE: compare the skeleton's rest local frames with Kestrel's (shared-animation check).

python rv_rig_compare.py  (pure Python + numpy, reads both glbs, prints only)
glTF animation channels store ABSOLUTE local rotations, so one clip only plays correctly on both agents when the
joints' rest local frames (bone axes / rolls) agree. Large per-joint angle differences mean per-agent clips or a
retarget step.
"""
import json
import struct

import numpy as np

FILES = {"solace": r"F:/git/val etf/assets/characters/solace/solace.glb",
         "kestrel": r"F:/git/val etf/assets/characters/kestrel/kestrel.glb"}


def load(p):
    b = open(p, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + jl])


def quat_to_m(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def world_frames(js):
    nodes = js["nodes"]
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    W = {}

    def w(i):
        if i in W:
            return W[i]
        n = nodes[i]
        M = np.eye(4)
        M[:3, :3] = quat_to_m(n.get("rotation", [0, 0, 0, 1])) * np.array(n.get("scale", [1, 1, 1]))
        M[:3, 3] = n.get("translation", [0, 0, 0])
        if i in parent:
            M = w(parent[i]) @ M
        W[i] = M
        return M
    joints = js["skins"][0]["joints"]
    return {nodes[j]["name"]: (w(j), np.array(nodes[j].get("rotation", [0, 0, 0, 1]))) for j in joints}


F = {k: world_frames(load(p)) for k, p in FILES.items()}
common = [n for n in F["solace"] if n in F["kestrel"]]
print("[RR] joints solace %d kestrel %d common %d" % (len(F["solace"]), len(F["kestrel"]), len(common)))
print("[RR] only solace:", [n for n in F["solace"] if n not in F["kestrel"]], "only kestrel:",
      [n for n in F["kestrel"] if n not in F["solace"]])
rows = []
for n in common:
    (Ms, qs), (Mk, qk) = F["solace"][n], F["kestrel"][n]
    Rs, Rk = Ms[:3, :3], Mk[:3, :3]
    # world-frame difference
    d = Rs.T @ Rk
    ang_w = np.degrees(np.arccos(np.clip((np.trace(d) - 1) / 2, -1, 1)))
    # local rotation difference
    dq = abs(np.dot(qs / np.linalg.norm(qs), qk / np.linalg.norm(qk)))
    ang_l = np.degrees(2 * np.arccos(np.clip(dq, -1, 1)))
    rows.append((n, ang_w, ang_l))
for n, aw, al in rows:
    if not any(n.startswith(f) for f in ("index", "middle", "ring", "pinky", "thumb")) or n.endswith("01_l") or n.endswith("01_r"):
        print("[RR] %-12s world-frame diff %6.1f deg   local-rotation diff %6.1f deg" % (n, aw, al))
A = np.array([r[2] for r in rows])
print("[RR] local-rotation diff: median %.1f deg, max %.1f deg, joints > 30 deg: %d / %d" % (
    np.median(A), A.max(), int((A > 30).sum()), len(A)))
