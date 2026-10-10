"""Reviewer's glTF JSON-level checks (system python). Read-only on the asset."""
import json, os, struct, sys
OUT = r"F:/git/val etf/assets/weapons/attachments/optics"

def load(p):
    b = open(p, "rb").read()
    jl, jt = struct.unpack("<I4s", b[12:20])
    return json.loads(b[20:20 + jl])

for oid in ("optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"):
    j = load(os.path.join(OUT, "ATT_%s.glb" % oid))
    print("=" * 20, oid)
    print(" asset:", j["asset"].get("generator"), "scenes:", len(j["scenes"]), "root nodes:", [j["nodes"][i]["name"] for i in j["scenes"][0]["nodes"]])
    for i, n in enumerate(j["nodes"]):
        print("  node %-32s children=%s mesh=%s T=%s R=%s S=%s extras=%s" % (n["name"], [j["nodes"][c]["name"] for c in n.get("children", [])],
              n.get("mesh"), n.get("translation"), n.get("rotation"), n.get("scale"), list(n.get("extras", {}).keys())))
    root = next(n for n in j["nodes"] if n["name"] == "ATT_" + oid)
    print("  root extras:", root.get("extras"))
    for m in j["materials"]:
        pbr = m.get("pbrMetallicRoughness", {})
        print("  mat %-18s alpha=%s dbl=%s base=%s tex=%s metal=%s rough=%s emis=%s ext=%s" % (
            m["name"], m.get("alphaMode", "OPAQUE"), m.get("doubleSided", False),
            [round(c, 3) for c in pbr.get("baseColorFactor", [1, 1, 1, 1])], "baseColorTexture" in pbr,
            pbr.get("metallicFactor", 1), pbr.get("roughnessFactor", 1), m.get("emissiveFactor"), list(m.get("extensions", {}).keys())))
    for mi, me in enumerate(j["meshes"]):
        for pr in me["primitives"]:
            a = pr["attributes"]
            print("  mesh %-26s mat=%-18s attrs=%s tris=%d" % (me["name"], j["materials"][pr["material"]]["name"], sorted(a.keys()), j["accessors"][pr["indices"]]["count"] // 3))
    for im in j.get("images", []):
        bv = j["bufferViews"][im["bufferView"]]
        print("  image", im.get("name"), im.get("mimeType"), bv["byteLength"], "B")
    print("  samplers:", j.get("samplers"))
