"""Scan GLB binary data: degenerate triangles, non-unit/NaN normals, UV ranges, per-primitive material, vertex counts."""
import glob, json, os, struct, sys
import numpy as np
HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
CT = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
def load(p):
    b = open(p, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + jl])
    rest = b[20 + jl:]
    bl = struct.unpack("<I", rest[:4])[0]
    return j, rest[8:8 + bl]
def acc(j, bin_, i):
    a = j["accessors"][i]; bv = j["bufferViews"][a["bufferView"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    n = NC[a["type"]]; dt = CT[a["componentType"]]
    stride = bv.get("byteStride", 0)
    arr = np.frombuffer(bin_, dtype=dt, count=a["count"] * n, offset=off).reshape(a["count"], n) if not stride else None
    return arr
out = {}
for p in sorted(glob.glob(os.path.join(HERE, "*.glb"))):
    j, bin_ = load(p)
    rep = {"degenerate_tris": 0, "bad_normals": 0, "verts": 0, "tris": 0, "uv_min": [9, 9], "uv_max": [-9, -9],
           "prims": 0, "mesh_degen": {}}
    for m in j["meshes"]:
        for pr in m["primitives"]:
            rep["prims"] += 1
            P = acc(j, bin_, pr["attributes"]["POSITION"]).astype(np.float64)
            N = acc(j, bin_, pr["attributes"]["NORMAL"]).astype(np.float64)
            UV = acc(j, bin_, pr["attributes"]["TEXCOORD_0"])
            I = acc(j, bin_, pr["indices"]).reshape(-1, 3).astype(np.int64)
            rep["verts"] += len(P); rep["tris"] += len(I)
            a = P[I[:, 1]] - P[I[:, 0]]; b = P[I[:, 2]] - P[I[:, 0]]
            area = 0.5 * np.linalg.norm(np.cross(a, b), axis=1)
            dg = int((area < 1e-10).sum())
            rep["degenerate_tris"] += dg
            if dg:
                rep["mesh_degen"][m["name"]] = rep["mesh_degen"].get(m["name"], 0) + dg
            ln = np.linalg.norm(N, axis=1)
            rep["bad_normals"] += int((~np.isfinite(ln) | (np.abs(ln - 1) > 0.01)).sum())
            rep["uv_min"] = [round(float(min(rep["uv_min"][k], UV[:, k].min())), 2) for k in range(2)]
            rep["uv_max"] = [round(float(max(rep["uv_max"][k], UV[:, k].max())), 2) for k in range(2)]
    rep["samplers"] = j.get("samplers")
    rep["textures"] = [(t.get("source"), t.get("sampler")) for t in j.get("textures", [])]
    rep["mats"] = {m["name"]: {k: v for k, v in m.items() if k != "name"} for m in j.get("materials", [])}
    out[os.path.basename(p)] = rep
    print(os.path.basename(p), {k: v for k, v in rep.items() if k not in ("mats",)})
json.dump(out, open(os.path.join(HERE, "review", "glb_scan.json"), "w"), indent=1)
print(json.dumps(out["mako_base.glb"]["mats"], indent=0)[:2500])
