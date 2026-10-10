"""Reviewer: parse every ATT_*.glb container directly (no Blender) and report node tree, extras, materials,
textures (embedded?), primitives per mesh, attributes (UV / normals), alpha modes, emissive. System python."""
import glob
import json
import os
import struct
import sys

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
OUT = os.path.join(HERE, "review", "glb_json_report.json")


def read_glb(p):
    with open(p, "rb") as f:
        data = f.read()
    magic, ver, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not glb"
    off = 12
    js = None
    binc = None
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk.decode("utf8"))
        elif ctype == 0x004E4942:
            binc = chunk
        off += 8 + clen
    return js, binc, ver, length


report = {}
for p in sorted(glob.glob(os.path.join(HERE, "ATT_*.glb"))):
    js, binc, ver, length = read_glb(p)
    name = os.path.basename(p)
    r = {"bytes": length, "gltf_version": js["asset"].get("version"), "generator": js["asset"].get("generator")}
    nodes = js.get("nodes", [])
    # parent map
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    tree = []
    for i, n in enumerate(nodes):
        tree.append({
            "name": n.get("name"), "parent": nodes[parent[i]]["name"] if i in parent else None,
            "mesh": js["meshes"][n["mesh"]]["name"] if "mesh" in n else None,
            "t": [round(v, 5) for v in n.get("translation", [0, 0, 0])],
            "r": [round(v, 5) for v in n.get("rotation", [0, 0, 0, 1])],
            "s": [round(v, 5) for v in n.get("scale", [1, 1, 1])],
            "extras": n.get("extras"),
        })
    r["nodes"] = tree
    r["scene_roots"] = [nodes[i]["name"] for i in js["scenes"][js.get("scene", 0)]["nodes"]]
    mats = js.get("materials", [])
    r["materials"] = []
    for m in mats:
        pbr = m.get("pbrMetallicRoughness", {})
        r["materials"].append({
            "name": m.get("name"), "alphaMode": m.get("alphaMode", "OPAQUE"), "doubleSided": m.get("doubleSided", False),
            "baseColorFactor": [round(v, 3) for v in pbr.get("baseColorFactor", [1, 1, 1, 1])],
            "baseColorTexture": pbr.get("baseColorTexture", {}).get("index"),
            "mr_tex": pbr.get("metallicRoughnessTexture", {}).get("index"),
            "metallic": pbr.get("metallicFactor", 1.0), "roughness": pbr.get("roughnessFactor", 1.0),
            "emissive": m.get("emissiveFactor"), "ext": list(m.get("extensions", {}).keys()),
            "normalTexture": m.get("normalTexture", {}).get("index"),
        })
    imgs = js.get("images", [])
    r["images"] = [{"name": im.get("name"), "embedded": "bufferView" in im, "uri": im.get("uri"),
                    "mime": im.get("mimeType")} for im in imgs]
    r["textures"] = js.get("textures", [])
    r["samplers"] = js.get("samplers", [])
    meshes = []
    for m in js.get("meshes", []):
        prims = []
        for pr in m["primitives"]:
            acc = js["accessors"][pr["indices"]] if "indices" in pr else None
            prims.append({"attrs": sorted(pr["attributes"].keys()), "material": mats[pr["material"]]["name"]
                          if "material" in pr else None, "tris": (acc["count"] // 3) if acc else None,
                          "mode": pr.get("mode", 4)})
        meshes.append({"name": m["name"], "prims": prims, "tris": sum(p["tris"] or 0 for p in prims)})
    r["meshes"] = meshes
    r["total_tris"] = sum(m["tris"] for m in meshes)
    r["extensionsUsed"] = js.get("extensionsUsed", [])
    report[name] = r

with open(OUT, "w") as f:
    json.dump(report, f, indent=1)

for name, r in report.items():
    print("=" * 100)
    print(name, r["bytes"], "bytes", "tris", r["total_tris"], "roots", r["scene_roots"], "ext", r["extensionsUsed"])
    for n in r["nodes"]:
        print(f"  node {n['name']:<40} parent={n['parent']} mesh={n['mesh']} t={n['t']} r={n['r']} s={n['s']}"
              + (f" extras={list(n['extras'].keys())}" if n['extras'] else ""))
    for m in r["meshes"]:
        print(f"  mesh {m['name']:<36} tris={m['tris']}")
        for pr in m["prims"]:
            print(f"      prim mat={pr['material']} tris={pr['tris']} attrs={pr['attrs']} mode={pr['mode']}")
    for m in r["materials"]:
        print(f"  mat {m['name']:<24} alpha={m['alphaMode']} ds={m['doubleSided']} bcf={m['baseColorFactor']} "
              f"bct={m['baseColorTexture']} met={m['metallic']} rough={m['roughness']} em={m['emissive']} "
              f"ext={m['ext']} mr={m['mr_tex']} nrm={m['normalTexture']}")
    print("  images", r["images"])
