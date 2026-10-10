"""Round-2 reviewer: glTF JSON-level checks (system python, read-only on the asset).

python "F:/git/val etf/assets/weapons/attachments/optics/review/round2/gltf_json_r2.py"
Writes review/round2/gltf_json_r2.json and prints a summary.
"""
import io
import json
import os
import struct

from PIL import Image

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
R2 = os.path.join(OUT, "review", "round2")
OPTICS = ("optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal")


def load(p):
    b = open(p, "rb").read()
    jl, _ = struct.unpack("<I4s", b[12:20])
    j = json.loads(b[20:20 + jl])
    off = 20 + jl
    bl, _ = struct.unpack("<I4s", b[off:off + 8])
    return j, b[off + 8:off + 8 + bl]


def acc_read(j, binb, ai):
    a = j["accessors"][ai]
    bv = j["bufferViews"][a["bufferView"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    fmt = {5126: "f", 5123: "H", 5125: "I", 5121: "B"}[a["componentType"]]
    size = struct.calcsize(fmt)
    stride = bv.get("byteStride", ncomp * size)
    out = []
    for i in range(a["count"]):
        o = start + i * stride
        out.append(struct.unpack("<" + fmt * ncomp, binb[o:o + ncomp * size]))
    return out


report = {}
for oid in OPTICS:
    p = os.path.join(OUT, "ATT_%s.glb" % oid)
    j, binb = load(p)
    r = {"file_bytes": os.path.getsize(p), "generator": j["asset"].get("generator"),
         "extensionsUsed": j.get("extensionsUsed", []), "extensionsRequired": j.get("extensionsRequired", [])}
    scene_roots = [j["nodes"][i]["name"] for i in j["scenes"][j.get("scene", 0)]["nodes"]]
    r["scene_roots"] = scene_roots
    nodes = {}
    for n in j["nodes"]:
        nodes[n["name"]] = {"children": [j["nodes"][c]["name"] for c in n.get("children", [])],
                            "mesh": j["meshes"][n["mesh"]]["name"] if "mesh" in n else None,
                            "T": n.get("translation"), "R": n.get("rotation"), "S": n.get("scale"),
                            "extras": n.get("extras")}
    r["nodes"] = nodes
    mats = []
    for m in j["materials"]:
        pbr = m.get("pbrMetallicRoughness", {})
        tex = pbr.get("baseColorTexture")
        mats.append({"name": m["name"], "alphaMode": m.get("alphaMode", "OPAQUE"),
                     "doubleSided": m.get("doubleSided", False),
                     "baseColorFactor": [round(c, 4) for c in pbr.get("baseColorFactor", [1, 1, 1, 1])],
                     "baseColorTexture": tex is not None,
                     "tex_transform": bool(tex and "extensions" in tex and "KHR_texture_transform" in tex["extensions"]),
                     "metallic": pbr.get("metallicFactor", 1.0), "roughness": pbr.get("roughnessFactor", 1.0),
                     "mr_texture": "metallicRoughnessTexture" in pbr, "normal_texture": "normalTexture" in m,
                     "emissive": m.get("emissiveFactor"), "ext": m.get("extensions", {})})
    r["materials"] = mats
    prims = []
    for me in j["meshes"]:
        for pr in me["primitives"]:
            a = pr["attributes"]
            pos = acc_read(j, binb, a["POSITION"])
            xs, ys, zs = zip(*pos)
            # glTF is Y-up: Blender (x, y, z) -> glTF (x, z, -y)
            ent = {"mesh": me["name"], "material": j["materials"][pr["material"]]["name"] if "material" in pr else None,
                   "attrs": sorted(a.keys()), "tris": j["accessors"][pr["indices"]]["count"] // 3,
                   "mode": pr.get("mode", 4),
                   "bbox_gltf_min": [round(min(xs), 4), round(min(ys), 4), round(min(zs), 4)],
                   "bbox_gltf_max": [round(max(xs), 4), round(max(ys), 4), round(max(zs), 4)]}
            if "NORMAL" in a:
                nrm = acc_read(j, binb, a["NORMAL"])
                bad = sum(1 for n in nrm if abs((n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 - 1) > 0.01)
                ent["bad_normals"] = bad
                if me["name"].endswith(("Reticle", "Glint")) or "Reticle" in me["name"] or "Glint" in me["name"]:
                    # average facing in Blender axes: glTF +Z = Blender -Y
                    avg = [sum(n[k] for n in nrm) / len(nrm) for k in range(3)]
                    ent["avg_normal_blender"] = [round(avg[0], 3), round(-avg[2], 3), round(avg[1], 3)]
            if "TEXCOORD_0" in a:
                uv = acc_read(j, binb, a["TEXCOORD_0"])
                us, vs = zip(*uv)
                ent["uv_range"] = [round(min(us), 3), round(max(us), 3), round(min(vs), 3), round(max(vs), 3)]
            prims.append(ent)
    r["primitives"] = prims
    r["tris_total"] = sum(p["tris"] for p in prims)
    imgs = []
    for im in j.get("images", []):
        if "bufferView" in im:
            bv = j["bufferViews"][im["bufferView"]]
            data = binb[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
            pil = Image.open(io.BytesIO(data))
            imgs.append({"name": im.get("name"), "mime": im.get("mimeType"), "bytes": bv["byteLength"],
                         "size": pil.size, "mode": pil.mode,
                         "mean_rgb_srgb": [round(c, 1) for c in
                                           Image.open(io.BytesIO(data)).convert("RGB").resize((1, 1),
                                                                                              Image.BOX).getpixel((0, 0))]})
        else:
            imgs.append({"name": im.get("name"), "uri": im.get("uri"), "EXTERNAL": True})
    r["images"] = imgs
    r["samplers"] = j.get("samplers")
    report[oid] = r
    print("=" * 10, oid, "tris", r["tris_total"], "roots", scene_roots, "ext", r["extensionsUsed"])
    for n, v in nodes.items():
        print("   node %-34s mesh=%-30s T=%s R=%s S=%s" % (n, v["mesh"], v["T"], v["R"], v["S"]))
    for m in mats:
        print("   mat %-24s %-6s dbl=%s base=%s tex=%s xf=%s m=%s r=%s emis=%s ext=%s" % (
            m["name"], m["alphaMode"], m["doubleSided"], m["baseColorFactor"], m["baseColorTexture"],
            m["tex_transform"], m["metallic"], m["roughness"], m["emissive"], list(m["ext"].keys())))
    for pr in prims:
        print("   prim %-28s %-24s tris=%-5d attrs=%s %s %s" % (pr["mesh"], pr["material"], pr["tris"], pr["attrs"],
                                                         pr.get("avg_normal_blender", ""), pr.get("uv_range", "")))
    for im in imgs:
        print("   img", im)

with open(os.path.join(R2, "gltf_json_r2.json"), "w") as f:
    json.dump(report, f, indent=1)
print("WROTE", os.path.join(R2, "gltf_json_r2.json"))
