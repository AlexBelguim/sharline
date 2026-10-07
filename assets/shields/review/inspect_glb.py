"""Review helper (system Python): parse every HALO .glb and report structure, materials, attributes, bounds.
Run: python "F:/git/val etf/assets/shields/review/inspect_glb.py"
"""
import glob
import json
import os
import struct
import sys

import numpy as np

ROOT = r"F:/git/val etf/assets/shields"
FILES = sorted(glob.glob(os.path.join(ROOT, "export", "*.glb"))) + [os.path.join(ROOT, "halo_kit.glb")]
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def load(path):
    b = open(path, "rb").read()
    magic, ver, length = struct.unpack_from("<4sII", b, 0)
    assert magic == b"glTF" and ver == 2, (magic, ver)
    off = 12
    js, binc = None, None
    while off < length:
        clen, ctype = struct.unpack_from("<I4s", b, off)
        data = b[off + 8: off + 8 + clen]
        if ctype == b"JSON":
            js = json.loads(data)
        elif ctype == b"BIN\x00":
            binc = data
        off += 8 + clen
    return js, binc


def acc(js, binc, i):
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    n = NC[a["type"]]
    dt = CT[a["componentType"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    if stride and stride != n * np.dtype(dt).itemsize:
        raw = np.frombuffer(binc, dtype=np.uint8, count=stride * a["count"], offset=start)
        arr = np.stack([np.frombuffer(raw[k * stride:k * stride + n * np.dtype(dt).itemsize].tobytes(), dt)
                        for k in range(a["count"])])
    else:
        arr = np.frombuffer(binc, dtype=dt, count=n * a["count"], offset=start).reshape(-1, n)
    return arr


report = {}
for f in FILES:
    js, binc = load(f)
    name = os.path.relpath(f, ROOT)
    r = {"extensionsUsed": js.get("extensionsUsed", []), "images": len(js.get("images", [])),
         "external_uris": [b.get("uri") for b in js.get("buffers", []) if b.get("uri")],
         "materials": [], "nodes": []}
    for m in js.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        r["materials"].append({
            "name": m.get("name"), "alphaMode": m.get("alphaMode", "OPAQUE"),
            "baseColor": [round(x, 3) for x in pbr.get("baseColorFactor", [1, 1, 1, 1])],
            "metal": pbr.get("metallicFactor", 1.0), "rough": pbr.get("roughnessFactor", 1.0),
            "emissive": [round(x, 3) for x in m.get("emissiveFactor", [0, 0, 0])],
            "emissive_strength": m.get("extensions", {}).get("KHR_materials_emissive_strength", {}).get(
                "emissiveStrength"),
            "doubleSided": m.get("doubleSided", False),
            "ext": list(m.get("extensions", {}).keys())})
    for ni, n in enumerate(js["nodes"]):
        e = {"name": n.get("name"), "T": n.get("translation"), "R": n.get("rotation"), "S": n.get("scale"),
             "extras": n.get("extras"), "children": n.get("children")}
        if "mesh" in n:
            me = js["meshes"][n["mesh"]]
            prims = []
            allp = []
            tris = 0
            for p in me["primitives"]:
                at = p["attributes"]
                pos = acc(js, binc, at["POSITION"])
                allp.append(pos)
                idx = acc(js, binc, p["indices"]).ravel() if "indices" in p else np.arange(len(pos))
                tris += len(idx) // 3
                # degenerate triangles (zero area)
                t = idx.reshape(-1, 3)
                v0, v1, v2 = pos[t[:, 0]], pos[t[:, 1]], pos[t[:, 2]]
                area = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
                nrm_ok = None
                if "NORMAL" in at:
                    nn = acc(js, binc, at["NORMAL"])
                    nrm_ok = bool(np.all(np.abs(np.linalg.norm(nn, axis=1) - 1) < 1e-2))
                prims.append({"material": js["materials"][p["material"]]["name"] if "material" in p else None,
                              "attrs": sorted(at.keys()), "tris": len(idx) // 3,
                              "degenerate_tris": int((area < 1e-10).sum()), "normals_unit": nrm_ok})
            P = np.concatenate(allp)
            e.update({"mesh": me.get("name"), "tris": tris, "prims": prims,
                      "bbox_min": [round(float(x), 4) for x in P.min(0)],
                      "bbox_max": [round(float(x), 4) for x in P.max(0)]})
        r["nodes"].append(e)
    report[name] = r

out = os.path.join(ROOT, "review", "glb_report.json")
json.dump(report, open(out, "w"), indent=1)
# concise print
for name, r in report.items():
    print("=" * 100)
    print(name, "| ext:", r["extensionsUsed"], "| images:", r["images"], "| external:", r["external_uris"])
    for m in r["materials"]:
        print("   MAT", m["name"], m["alphaMode"], "base", m["baseColor"], "em", m["emissive"], "x",
              m["emissive_strength"], "metal", m["metal"], "rough", m["rough"], "2side", m["doubleSided"], m["ext"])
    for n in r["nodes"]:
        tr = ""
        if n["R"] or n["S"]:
            tr = f" R={n['R']} S={n['S']}"
        if "tris" in n:
            pm = "; ".join(f"{p['material']}:{p['tris']}{'' if 'TEXCOORD_0' in p['attrs'] else ' NO-UV'}"
                           f"{'' if 'NORMAL' in p['attrs'] else ' NO-NRM'}"
                           f"{' DEG=' + str(p['degenerate_tris']) if p['degenerate_tris'] else ''}"
                           for p in n["prims"])
            print(f"   {n['name']:<28} T={n['T']}{tr} tris={n['tris']:<5} bbox={n['bbox_min']}..{n['bbox_max']}"
                  f"  [{pm}]")
        else:
            print(f"   {n['name']:<28} (empty) T={n['T']}{tr} extras={n['extras']}")
print("wrote", out)
