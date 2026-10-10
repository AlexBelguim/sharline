"""Review round 2 (system Python + numpy): parse every shipped HALO .glb directly (no Blender) and report
structure, materials (incl. emissive textures), images, node names/transforms, primitives and bounds.
Run: python "F:/git/val etf/assets/shields/review/r2/r2_inspect_glb.py"
Writes review/r2/r2_glb_report.json.
"""
import glob
import json
import os
import struct

import numpy as np

ROOT = r"F:/git/val etf/assets/shields"
OUT = os.path.join(ROOT, "review", "r2")
FILES = sorted(glob.glob(os.path.join(ROOT, "export", "*.glb"))) + [os.path.join(ROOT, "halo_kit.glb")]
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def load(path):
    b = open(path, "rb").read()
    magic, ver, length = struct.unpack_from("<4sII", b, 0)
    assert magic == b"glTF" and ver == 2, (magic, ver)
    assert length == len(b), ("length mismatch", length, len(b))
    off, js, binc = 12, None, None
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
    n, dt = NC[a["type"]], CT[a["componentType"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    item = n * np.dtype(dt).itemsize
    if stride and stride != item:
        return np.stack([np.frombuffer(binc, dt, n, start + k * stride) for k in range(a["count"])])
    return np.frombuffer(binc, dtype=dt, count=n * a["count"], offset=start).reshape(-1, n)


report, problems = {}, []
for f in FILES:
    js, binc = load(f)
    name = os.path.relpath(f, ROOT).replace("\\", "/")
    r = {"extensionsUsed": js.get("extensionsUsed", []), "extensionsRequired": js.get("extensionsRequired", []),
         "images": [], "external_uris": [b.get("uri") for b in js.get("buffers", []) if b.get("uri")],
         "materials": [], "nodes": [], "scene_roots": [js["nodes"][i].get("name") for i in
                                                        js["scenes"][js.get("scene", 0)]["nodes"]]}
    for im in js.get("images", []):
        r["images"].append({"name": im.get("name"), "mime": im.get("mimeType"), "uri": im.get("uri"),
                            "embedded": "bufferView" in im})
        if im.get("uri"):
            problems.append(f"{name}: external image uri {im.get('uri')}")
    for m in js.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        ex = m.get("extensions", {})
        r["materials"].append({
            "name": m.get("name"), "alphaMode": m.get("alphaMode", "OPAQUE"),
            "baseColor": [round(x, 4) for x in pbr.get("baseColorFactor", [1, 1, 1, 1])],
            "baseColorTexture": "baseColorTexture" in pbr,
            "metal": pbr.get("metallicFactor", 1.0), "rough": pbr.get("roughnessFactor", 1.0),
            "emissive": [round(x, 4) for x in m.get("emissiveFactor", [0, 0, 0])],
            "emissiveTexture": m.get("emissiveTexture"),
            "emissive_strength": ex.get("KHR_materials_emissive_strength", {}).get("emissiveStrength"),
            "clearcoat": ex.get("KHR_materials_clearcoat", {}).get("clearcoatFactor"),
            "doubleSided": m.get("doubleSided", False), "ext": sorted(ex.keys())})
    for n in js["nodes"]:
        e = {"name": n.get("name"), "T": n.get("translation"), "R": n.get("rotation"), "S": n.get("scale"),
             "extras": n.get("extras"), "children": [js["nodes"][c].get("name") for c in n.get("children", [])]}
        if "mesh" in n:
            me = js["meshes"][n["mesh"]]
            prims, allp, tris = [], [], 0
            for p in me["primitives"]:
                at = p["attributes"]
                pos = acc(js, binc, at["POSITION"]).astype(np.float64)
                allp.append(pos)
                idx = acc(js, binc, p["indices"]).ravel() if "indices" in p else np.arange(len(pos))
                t = idx.reshape(-1, 3)
                tris += len(t)
                v0, v1, v2 = pos[t[:, 0]], pos[t[:, 1]], pos[t[:, 2]]
                area = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
                nrm_unit = None
                if "NORMAL" in at:
                    nn = acc(js, binc, at["NORMAL"])
                    nrm_unit = bool(np.all(np.abs(np.linalg.norm(nn, axis=1) - 1) < 1e-2))
                uv_range = None
                if "TEXCOORD_0" in at:
                    uv = acc(js, binc, at["TEXCOORD_0"])
                    uv_range = [round(float(uv[:, 0].ptp()), 2), round(float(uv[:, 1].ptp()), 2)]
                prims.append({"material": js["materials"][p["material"]]["name"] if "material" in p else None,
                              "attrs": sorted(at.keys()), "tris": int(len(t)),
                              "degenerate_tris": int((area < 1e-10).sum()), "normals_unit": nrm_unit,
                              "uv_extent": uv_range, "mode": p.get("mode", 4)})
                if "TEXCOORD_0" not in at:
                    problems.append(f"{name}:{n.get('name')}: primitive without UVs")
                if "NORMAL" not in at:
                    problems.append(f"{name}:{n.get('name')}: primitive without normals")
                if "material" not in p:
                    problems.append(f"{name}:{n.get('name')}: primitive without material")
            P = np.concatenate(allp)
            e.update({"mesh": me.get("name"), "tris": tris, "prims": prims,
                      "bbox_min": [round(float(x), 4) for x in P.min(0)],
                      "bbox_max": [round(float(x), 4) for x in P.max(0)]})
            if me.get("name") != n.get("name"):
                e["mesh_name_differs"] = True
        r["nodes"].append(e)
    report[name] = r

json.dump({"files": report, "problems": problems}, open(os.path.join(OUT, "r2_glb_report.json"), "w"), indent=1)
for name, r in report.items():
    print("=" * 110)
    print(name, "| ext:", r["extensionsUsed"], "req:", r["extensionsRequired"], "| images:", r["images"],
          "| external:", r["external_uris"], "| roots:", len(r["scene_roots"]))
    for m in r["materials"]:
        print("   MAT", f"{m['name']:<26}", m["alphaMode"], "base", m["baseColor"], "em", m["emissive"], "x",
              m["emissive_strength"], "emTex", m["emissiveTexture"], "coat", m["clearcoat"], "metal", m["metal"],
              "rough", m["rough"], "2side", m["doubleSided"])
    for n in r["nodes"]:
        tr = f" R={n['R']} S={n['S']}" if (n["R"] or n["S"]) else ""
        if "tris" in n:
            pm = "; ".join(f"{p['material'].replace('M_HALO_', '')}:{p['tris']}"
                           f"{'' if 'TEXCOORD_0' in p['attrs'] else ' NO-UV'}"
                           f"{' DEG=' + str(p['degenerate_tris']) if p['degenerate_tris'] else ''}"
                           for p in n["prims"])
            print(f"   {n['name']:<30} T={n['T']}{tr} tris={n['tris']:<5} bb={n['bbox_min']}..{n['bbox_max']} [{pm}]")
        else:
            print(f"   {n['name']:<30} (empty) T={n['T']}{tr} extras={n['extras']} children={len(n['children'])}")
print("PROBLEMS:", problems)
