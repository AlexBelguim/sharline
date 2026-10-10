"""Independent review of SOLACE: raw glTF/GLB inspection (pure Python + numpy, no Blender).

python glb_inspect.py  ->  prints facts about solace.glb (nodes, skin, materials, primitives, extras, images).
Read-only: writes nothing next to the asset.
"""
import json
import struct
import sys

import numpy as np

GLB = r"F:/git/val etf/assets/characters/solace/solace.glb"

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def load(path):
    b = open(path, "rb").read()
    magic, ver, length = struct.unpack("<III", b[:12])
    assert magic == 0x46546C67, "not a glb"
    jl, jt = struct.unpack("<II", b[12:20])
    js = json.loads(b[20:20 + jl])
    off = 20 + jl
    bl, bt = struct.unpack("<II", b[off:off + 8])
    binc = b[off + 8:off + 8 + bl]
    return js, binc, ver, length, len(b)


def acc(js, binc, i):
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    dt = CT[a["componentType"]]
    n = NC[a["type"]]
    stride = bv.get("byteStride", 0)
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    itemsize = np.dtype(dt).itemsize * n
    if stride and stride != itemsize:
        raw = np.frombuffer(binc, np.uint8, count=stride * a["count"], offset=start).reshape(a["count"], stride)
        arr = raw[:, :itemsize].copy().view(dt).reshape(a["count"], n)
    else:
        arr = np.frombuffer(binc, dt, count=a["count"] * n, offset=start).reshape(a["count"], n)
    if a.get("normalized"):
        arr = arr.astype(np.float32) / np.iinfo(dt).max
    return arr


def main():
    js, binc, ver, length, flen = load(GLB)
    print("[GLB] version", ver, "declared length", length, "file", flen, "MB %.2f" % (flen / 1e6))
    print("[GLB] generator", js["asset"].get("generator"), "extensionsUsed", js.get("extensionsUsed"),
          "extensionsRequired", js.get("extensionsRequired"))
    nodes = js["nodes"]
    print("[GLB] nodes", len(nodes), "meshes", len(js["meshes"]), "materials", len(js["materials"]),
          "images", len(js.get("images", [])), "textures", len(js.get("textures", [])), "skins", len(js.get("skins", [])))
    # parent map
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    scene_roots = js["scenes"][js.get("scene", 0)]["nodes"]
    print("[GLB] scene roots:", [nodes[r]["name"] for r in scene_roots])
    skin = js["skins"][0]
    joints = skin["joints"]
    jn = [nodes[j]["name"] for j in joints]
    print("[GLB] skin joints", len(joints), "skeleton root", nodes[skin.get("skeleton", joints[0])]["name"] if "skeleton" in skin else None)
    print("[GLB] joint names:", jn)

    # world matrices
    def local(n):
        if "matrix" in n:
            return np.array(n["matrix"], float).reshape(4, 4).T
        T = np.eye(4)
        t = n.get("translation", [0, 0, 0])
        r = n.get("rotation", [0, 0, 0, 1])
        s = n.get("scale", [1, 1, 1])
        x, y, z, w = r
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        T[:3, :3] = R * np.array(s)
        T[:3, 3] = t
        return T

    W = {}

    def world(i):
        if i in W:
            return W[i]
        m = local(nodes[i])
        if i in parent:
            m = world(parent[i]) @ m
        W[i] = m
        return m

    def to_blender(p):  # glTF Y-up -> Blender Z-up: (x, y, z) -> (x, -z, y)
        return np.array([p[0], -p[2], p[1]])

    # IBM check
    ibm = acc(js, binc, skin["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
    err = max(np.abs(world(j) @ ibm[k] - np.eye(4)).max() for k, j in enumerate(joints))
    print("[GLB] inverse-bind vs rest world max err %.2e" % err)
    for k in ("head", "neck_01", "spine_03", "pelvis", "hand_r", "hand_l", "lowerarm_r", "thigh_l", "calf_l",
              "foot_l", "upperarm_r", "upperarm_l", "clavicle_r", "lowerarm_l", "foot_r", "thigh_r"):
        j = joints[jn.index(k)]
        print("[GLB] joint %-11s blender pos %s" % (k, np.round(to_blender(world(j)[:3, 3]), 3)))

    # non-joint nodes
    for i, n in enumerate(nodes):
        if i in joints:
            continue
        p = to_blender(world(i)[:3, 3])
        R = world(i)[:3, :3]
        print("[GLB] node %-22s parent %-18s mesh %-4s skin %-4s pos %s extras %s" % (
            n["name"], nodes[parent[i]]["name"] if i in parent else "-", n.get("mesh"), n.get("skin"),
            np.round(p, 4), json.dumps(n.get("extras", {}))[:220]))
        if n["name"].startswith("SOL_SOCKET") or n["name"].startswith("SOL_Bloom_Vane"):
            print("        world rot (glTF axes) rows", np.round(R, 3).tolist())

    # materials
    for i, m in enumerate(js["materials"]):
        pbr = m.get("pbrMetallicRoughness", {})
        print("[GLB] mat %-16s base %s metal %s rough %s baseTex %s mrTex %s nrm %s emis %s emisTex %s ext %s ds %s alpha %s" % (
            m["name"], np.round(pbr.get("baseColorFactor", [1, 1, 1, 1]), 3).tolist(), pbr.get("metallicFactor", 1),
            pbr.get("roughnessFactor", 1), "baseColorTexture" in pbr, "metallicRoughnessTexture" in pbr,
            "normalTexture" in m, m.get("emissiveFactor"), "emissiveTexture" in m, m.get("extensions"),
            m.get("doubleSided", False), m.get("alphaMode", "OPAQUE")))
    # images
    for i, im in enumerate(js.get("images", [])):
        bv = js["bufferViews"][im["bufferView"]] if "bufferView" in im else None
        print("[GLB] image", i, im.get("name"), im.get("mimeType"), "embedded" if bv else "EXTERNAL " + str(im.get("uri")),
              bv["byteLength"] if bv else "")
    # meshes / primitives
    tot_tris = 0
    for mi, me in enumerate(js["meshes"]):
        for pi, pr in enumerate(me["primitives"]):
            at = pr["attributes"]
            nidx = js["accessors"][pr["indices"]]["count"] if "indices" in pr else js["accessors"][at["POSITION"]]["count"]
            tris = nidx // 3
            tot_tris += tris
            pos = acc(js, binc, at["POSITION"])
            line = "[GLB] mesh %-18s prim %d mat %-16s verts %6d tris %6d attrs %s" % (
                me["name"], pi, js["materials"][pr["material"]]["name"] if "material" in pr else None, len(pos), tris,
                sorted(at.keys()))
            print(line)
            if "JOINTS_0" in at:
                J = acc(js, binc, at["JOINTS_0"]).astype(int)
                Wt = acc(js, binc, at["WEIGHTS_0"]).astype(float)
                s = Wt.sum(1)
                nz = (Wt > 1e-4).sum(1)
                print("        weights sum min %.4f max %.4f  zero-weight verts %d  max influences %d  mean infl %.2f" % (
                    s.min(), s.max(), int((s < 1e-4).sum()), nz.max(), nz.mean()))
            if "TEXCOORD_0" in at:
                uv = acc(js, binc, at["TEXCOORD_0"])
                print("        uv range u[%.3f, %.3f] v[%.3f, %.3f]" % (uv[:, 0].min(), uv[:, 0].max(), uv[:, 1].min(), uv[:, 1].max()))
            if "NORMAL" in at:
                nr = acc(js, binc, at["NORMAL"])
                ln = np.linalg.norm(nr, axis=1)
                print("        normal length min %.3f max %.3f" % (ln.min(), ln.max()))
    print("[GLB] TOTAL TRIS", tot_tris)
    # bbox of skinned body in bind pose: use mesh node world (skinned meshes ignore node transform in glTF)
    allp = []
    for i, n in enumerate(nodes):
        if "mesh" in n:
            for pr in js["meshes"][n["mesh"]]["primitives"]:
                p = acc(js, binc, pr["attributes"]["POSITION"]).astype(float)
                if "skin" in n:
                    M = np.eye(4)
                else:
                    M = world(i)
                pw = p @ M[:3, :3].T + M[:3, 3]
                allp.append(np.c_[pw[:, 0], -pw[:, 2], pw[:, 1]])
                if "skin" not in n:
                    q = allp[-1]
                    print("[GLB] rigid %-18s bbox blender min %s max %s" % (n["name"], np.round(q.min(0), 3), np.round(q.max(0), 3)))
    A = np.vstack(allp)
    print("[GLB] overall bbox (blender axes) min", np.round(A.min(0), 4), "max", np.round(A.max(0), 4),
          "dims", np.round(A.max(0) - A.min(0), 4))


if __name__ == "__main__":
    main()
