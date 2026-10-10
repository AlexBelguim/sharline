"""Review helper: parse kestrel.glb directly (no Blender) and print structural facts."""
import json, struct, sys
import numpy as np

P = sys.argv[1] if len(sys.argv) > 1 else r"F:/git/val etf/assets/characters/kestrel/kestrel.glb"
data = open(P, "rb").read()
magic, ver, length = struct.unpack_from("<III", data, 0)
off = 12
chunks = []
while off < length:
    cl, ct = struct.unpack_from("<II", data, off)
    chunks.append((ct, data[off + 8: off + 8 + cl]))
    off += 8 + cl
js = json.loads(chunks[0][1])
binb = chunks[1][1] if len(chunks) > 1 else b""
print("glb version", ver, "bytes", length, "extensionsUsed", js.get("extensionsUsed"), "required", js.get("extensionsRequired"))
print("asset", js["asset"])
nodes = js["nodes"]
parent = {}
for i, n in enumerate(nodes):
    for c in n.get("children", []):
        parent[c] = i
print("scenes", [(s.get("name"), s["nodes"]) for s in js["scenes"]])
def path(i):
    p = []
    while i is not None:
        p.append(nodes[i].get("name"))
        i = parent.get(i)
    return "/".join(reversed(p))
for i, n in enumerate(nodes):
    if "mesh" in n or "skin" in n or "SOCKET" in n.get("name", "") or i in js["scenes"][0]["nodes"] or n.get("name") in ("root", "pelvis", "head", "hand_r", "hand_l"):
        print(i, path(i), {k: v for k, v in n.items() if k not in ("children",)})
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
def acc(i):
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    dt = CT[a["componentType"]]
    n = NC[a["type"]]
    stride = bv.get("byteStride")
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    if stride and stride != np.dtype(dt).itemsize * n:
        raw = np.frombuffer(binb, dtype=np.uint8, count=stride * a["count"], offset=start).reshape(a["count"], stride)
        arr = raw[:, : np.dtype(dt).itemsize * n].copy().view(dt).reshape(a["count"], n)
    else:
        arr = np.frombuffer(binb, dtype=dt, count=a["count"] * n, offset=start).reshape(a["count"], n)
    if a.get("normalized"):
        arr = arr.astype(np.float32) / np.iinfo(dt).max
    return arr
tot = 0
for mi, m in enumerate(js["meshes"]):
    print("mesh", mi, m.get("name"), "primitives", len(m["primitives"]))
    for p in m["primitives"]:
        at = p["attributes"]
        ntri = js["accessors"][p["indices"]]["count"] // 3
        tot += ntri
        mat = js["materials"][p["material"]] if "material" in p else None
        print("  prim mat", mat and mat.get("name"), "attrs", sorted(at), "verts", js["accessors"][at["POSITION"]]["count"], "tris", ntri, "mode", p.get("mode", 4))
        pos = acc(at["POSITION"])
        print("   pos min", pos.min(0).round(4), "max", pos.max(0).round(4))
        if "WEIGHTS_0" in at:
            w = acc(at["WEIGHTS_0"]).astype(np.float64)
            s = w.sum(1)
            print("   weight sums min %.5f max %.5f, n(|s-1|>1e-3)=%d, zero-weight verts=%d" % (s.min(), s.max(), (abs(s - 1) > 1e-3).sum(), (s < 1e-6).sum()))
            j = acc(at["JOINTS_0"])
            print("   joint idx max", j.max(), "nonzero influences per vert hist", np.bincount((w > 1e-6).sum(1)))
            print("   has JOINTS_1", "JOINTS_1" in at)
        if "NORMAL" in at:
            nn = acc(at["NORMAL"])
            ln = np.linalg.norm(nn, axis=1)
            print("   normal length min %.4f max %.4f" % (ln.min(), ln.max()))
        if "TEXCOORD_0" in at:
            uv = acc(at["TEXCOORD_0"])
            print("   uv min", uv.min(0).round(3), "max", uv.max(0).round(3))
        if "TANGENT" in at:
            print("   has tangents")
print("TOTAL tris", tot)
for i, m in enumerate(js["materials"]):
    print("material", i, json.dumps(m)[:600])
for i, t in enumerate(js.get("textures", [])):
    print("texture", i, t)
for i, im in enumerate(js.get("images", [])):
    bv = js["bufferViews"][im["bufferView"]] if "bufferView" in im else None
    print("image", i, im.get("name"), im.get("mimeType"), "embedded" if bv else im.get("uri"), bv and bv["byteLength"])
print("samplers", js.get("samplers"))
for si, s in enumerate(js.get("skins", [])):
    names = [nodes[j]["name"] for j in s["joints"]]
    print("skin", si, s.get("name"), "joints", len(names), "skeleton", s.get("skeleton"))
    print("  ", names)
    ibm = acc(s["inverseBindMatrices"]).reshape(-1, 4, 4)
    print("   ibm count", len(ibm))
# world matrices of nodes
def local(n):
    M = np.eye(4)
    if "matrix" in n:
        return np.array(n["matrix"]).reshape(4, 4).T
    t = n.get("translation", [0, 0, 0]); r = n.get("rotation", [0, 0, 0, 1]); s = n.get("scale", [1, 1, 1])
    x, y, z, w = r
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M[:3, :3] = R * np.array(s)
    M[:3, 3] = t
    return M
def world(i):
    M = local(nodes[i])
    p = parent.get(i)
    while p is not None:
        M = local(nodes[p]) @ M
        p = parent.get(p)
    return M
print("--- world transforms (glTF Y-up; blender = (x, -z, y))")
for i, n in enumerate(nodes):
    nm = n.get("name", "")
    if "SOCKET" in nm or nm in ("root", "pelvis", "head", "hand_r", "hand_l", "neck_01", "KES_Armature", "KES_Body", "KES_Eyepiece"):
        W = world(i)
        t = W[:3, 3]
        print(f"{nm:22s} parent={str(nodes[parent[i]]['name'] if i in parent else None):14s} pos_gltf={t.round(4)} blender=({t[0]:.3f},{-t[2]:.3f},{t[1]:.3f})")
        if "SOCKET" in nm:
            R = W[:3, :3]
            # local axes in blender coords
            def b(v): return np.array([v[0], -v[2], v[1]]).round(3)
            print("    local X", b(R[:, 0]), "local Y", b(R[:, 1]), "local Z", b(R[:, 2]), "scale", np.linalg.norm(R, axis=0).round(4), "extras", n.get("extras"))
# check the bind pose: IBM * world(joint) == I
s = js["skins"][0]
ibm = acc(s["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
err = max(np.abs(ibm[k] @ world(j) - np.eye(4)).max() for k, j in enumerate(s["joints"]))
print("max |IBM*jointWorld - I| (0 = rest pose matches bind pose):", err)
