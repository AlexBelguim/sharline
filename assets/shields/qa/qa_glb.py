"""Pure-Python glTF check of every exported .glb (no Blender): node names vs the spec, primitives, materials.

  python "F:/git/val etf/assets/shields/qa/qa_glb.py"

Writes qa/qa_glb_report.json and prints FAIL lines (exit code 1 when anything fails).
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXP = os.path.join(ROOT, "export")
CORES = ("Bulwark", "Mender", "Volt", "Phase")
ZONES = ("Head", "Arms", "Torso", "Legs")


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, ver, length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and ver == 2, path
    off, js, binlen = 12, None, 0
    while off < length:
        clen, ctype = struct.unpack_from("<I4s", data, off)
        if ctype == b"JSON":
            js = json.loads(data[off + 8: off + 8 + clen])
        elif ctype == b"BIN\x00":
            binlen = clen
        off += 8 + clen
    return js, binlen


def main():
    fails = []
    report = {}
    expected = {f"HALO_{c}.glb": [f"HALO_{c}_Arc_{z}" for z in ZONES] + [f"HALO_{c}_Band_{w}" for w in ("Medium", "Heavy")]
                + [f"HALO_{c}_PIP_{i}" for i in range(1, 5)] + [f"HALO_{c}_Far_Glass_{z}" for z in ZONES]
                + [f"HALO_{c}_Far_Frame_{w}" for w in ("Light", "Medium", "Heavy")] for c in CORES}
    expected["HALO_Common.glb"] = ["HALO_TierPip", "HALO_PowerCell", "HALO_Shard_A", "HALO_Shard_B", "HALO_Shard_C"] + \
        [f"HALO_PIP_{i}" for i in range(1, 5)]
    expected["HALO_Pickups.glb"] = [f"HALO_Core_{c}" for c in CORES]
    want_mats = ["M_HALO_Glass_T1", "M_HALO_Glass_T2", "M_HALO_Glass_T3", "M_HALO_Glass_T4", "M_HALO_Glass_Off",
                 "M_HALO_Glass_Broken_T1", "M_HALO_Glass_Broken_T2", "M_HALO_Glass_Broken_T3",
                 "M_HALO_Glass_Broken_T4", "M_HALO_Edge", "M_HALO_Graphite", "M_HALO_Gunmetal", "M_HALO_Bone"]
    files = sorted(f for f in os.listdir(EXP) if f.endswith(".glb")) + ["../halo_kit.glb"]
    for fn in files:
        js, binlen = read_glb(os.path.join(EXP, fn))
        nodes = {n.get("name"): n for n in js.get("nodes", [])}
        mats = js.get("materials", [])
        r = {"nodes": len(nodes), "meshes": len(js.get("meshes", [])), "materials": [m["name"] for m in mats],
             "images": len(js.get("images", [])), "bin_bytes": binlen, "issues": []}
        for img in js.get("images", []):
            if "uri" in img:
                r["issues"].append(f"external image uri {img['uri']}")
        for name in expected.get(fn, []):
            if name not in nodes:
                r["issues"].append(f"missing node {name}")
        for n in js.get("nodes", []):
            if "rotation" in n or "scale" in n:
                if not n.get("name", "").startswith("HALO_Swatch"):
                    r["issues"].append(f"node {n.get('name')} has rotation/scale")
        for m in js.get("meshes", []):
            for p in m["primitives"]:
                a = p["attributes"]
                if "NORMAL" not in a or "TEXCOORD_0" not in a:
                    r["issues"].append(f"mesh {m['name']} primitive without NORMAL/TEXCOORD_0")
                if "material" not in p:
                    r["issues"].append(f"mesh {m['name']} primitive without material")
        mat_info = {}
        for m in mats:
            ext = m.get("extensions", {})
            pbr = m.get("pbrMetallicRoughness", {})
            mat_info[m["name"]] = {
                "doubleSided": m.get("doubleSided", False), "alphaMode": m.get("alphaMode", "OPAQUE"),
                "emissiveFactor": [round(x, 3) for x in m.get("emissiveFactor", [0, 0, 0])],
                "emissive_strength": ext.get("KHR_materials_emissive_strength", {}).get("emissiveStrength"),
                "emissiveTexture": "emissiveTexture" in m, "baseColorFactor":
                    [round(x, 3) for x in pbr.get("baseColorFactor", [1, 1, 1, 1])],
                "clearcoat": "KHR_materials_clearcoat" in ext}
            if m.get("doubleSided"):
                r["issues"].append(f"material {m['name']} is double-sided")
            if m.get("alphaMode", "OPAQUE") != "OPAQUE" and m["name"].startswith("M_HALO"):
                r["issues"].append(f"material {m['name']} alphaMode {m.get('alphaMode')}")
            if m["name"].startswith("M_HALO_Glass_Broken") and "emissiveTexture" not in m:
                r["issues"].append(f"material {m['name']} has no emissive (crack) texture")
        r["material_info"] = mat_info
        if fn == "HALO_Materials.glb":
            for mn in want_mats:
                if mn not in mat_info:
                    r["issues"].append(f"material library lacks {mn}")
        # per-arc meshes: primitive 0 must be the glass
        for m in js.get("meshes", []):
            if "_Arc_" in m["name"] or "_Far_Glass_" in m["name"]:
                first = mats[m["primitives"][0]["material"]]["name"]
                if not first.startswith("M_HALO_Glass"):
                    r["issues"].append(f"{m['name']}: primitive 0 is {first}, not glass")
        report[fn] = r
        for i in r["issues"]:
            fails.append(f"{fn}: {i}")
    out = os.path.join(HERE, "qa_glb_report.json")
    json.dump(report, open(out, "w"), indent=1)
    for f in fails:
        print("FAIL", f)
    print(f"{len(files)} files checked, {len(fails)} issues -> {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
