"""Pure-Python glTF check of every exported .glb (no Blender): node names and hierarchy vs the kit layout,
primitives, materials, zero-area triangles and the draw count of an assembled halo.

  python "F:/git/val etf/assets/shields/qa/qa_glb.py"

Writes qa/qa_glb_report.json and prints FAIL lines (exit code 1 when anything fails).  Needs numpy.
"""
import json
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXP = os.path.join(ROOT, "export")
CORES = ("Bulwark", "Mender", "Volt", "Phase")
ZONES = ("Head", "Arms", "Torso", "Legs")
WEIGHTS = ("Light", "Medium", "Heavy")
CELLS = {"Light": 1, "Medium": 2, "Heavy": 3}
GROUPS = ("Near", "Frames", "Bands", "Pips", "Cells", "Far")
CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
AREA_MIN = 1e-10          # m^2: below this a triangle counts as zero-area (review r2 #2)


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, ver, length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and ver == 2, path
    off, js, binc = 12, None, b""
    while off < length:
        clen, ctype = struct.unpack_from("<I4s", data, off)
        if ctype == b"JSON":
            js = json.loads(data[off + 8: off + 8 + clen])
        elif ctype == b"BIN\x00":
            binc = data[off + 8: off + 8 + clen]
        off += 8 + clen
    return js, binc


def accessor(js, binc, i):
    a = js["accessors"][i]
    bv = js["bufferViews"][a["bufferView"]]
    n, dt = NC[a["type"]], CT[a["componentType"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    item = n * np.dtype(dt).itemsize
    if stride and stride != item:
        return np.stack([np.frombuffer(binc, dt, n, start + k * stride) for k in range(a["count"])])
    return np.frombuffer(binc, dtype=dt, count=n * a["count"], offset=start).reshape(-1, n)


def expected_nodes(fn):
    if fn.startswith("HALO_") and fn[5:-4] in CORES:
        c = fn[5:-4]
        names = [f"HALO_{c}_{g}" for g in GROUPS]
        names += [f"HALO_{c}_Arc_{z}" for z in ZONES] + [f"HALO_{c}_Frame_{w}" for w in WEIGHTS]
        names += [f"HALO_{c}_Band_{w}" for w in ("Medium", "Heavy")] + [f"HALO_{c}_PIP_Centre"]
        names += [f"HALO_{c}_PIP_{n}_{i}" for n in range(1, 5) for i in range(1, n + 1)]
        names += [f"HALO_PowerCell_{c}"] + [f"HALO_{c}_Far_Glass_{z}" for z in ZONES]
        names += [f"HALO_{c}_Far_Frame_{w}" for w in WEIGHTS]
        return names
    if fn == "HALO_Common.glb":
        return ["HALO_TierPip", "HALO_PowerCell", "HALO_Shard_A", "HALO_Shard_B", "HALO_Shard_C"] + \
            [f"HALO_PIP_{i}" for i in range(1, 5)]
    if fn == "HALO_Pickups.glb":
        return [f"HALO_Core_{c}" for c in CORES]
    return []


def main():
    fails = []
    report = {}
    want_mats = ["M_HALO_Glass_T1", "M_HALO_Glass_T2", "M_HALO_Glass_T3", "M_HALO_Glass_T4", "M_HALO_Glass_Off",
                 "M_HALO_Glass_Broken_T1", "M_HALO_Glass_Broken_T2", "M_HALO_Glass_Broken_T3",
                 "M_HALO_Glass_Broken_T4", "M_HALO_Edge", "M_HALO_Graphite", "M_HALO_Graphite_Far",
                 "M_HALO_Gunmetal", "M_HALO_Bone"]
    files = sorted(f for f in os.listdir(EXP) if f.endswith(".glb")) + ["../halo_kit.glb"]
    for fn in files:
        js, binc = read_glb(os.path.join(EXP, fn))
        nodes = {n.get("name"): n for n in js.get("nodes", [])}
        mats = js.get("materials", [])
        roots = [js["nodes"][i].get("name") for i in js["scenes"][js.get("scene", 0)]["nodes"]]
        r = {"nodes": len(nodes), "meshes": len(js.get("meshes", [])), "scene_roots": roots,
             "materials": [m["name"] for m in mats], "images": len(js.get("images", [])), "bin_bytes": len(binc),
             "issues": [], "mesh_info": {}}
        for img in js.get("images", []):
            if "uri" in img:
                r["issues"].append(f"external image uri {img['uri']}")
        for b in js.get("buffers", []):
            if b.get("uri"):
                r["issues"].append(f"external buffer uri {b['uri']}")
        for name in expected_nodes(fn):
            if name not in nodes:
                r["issues"].append(f"missing node {name}")
        if fn[5:-4] in CORES:           # per-core file: exactly the six group nodes at the root (review r2 #8)
            c = fn[5:-4]
            if sorted(roots) != sorted(f"HALO_{c}_{g}" for g in GROUPS):
                r["issues"].append(f"scene roots {roots} are not the six HALO_{c}_<group> nodes")
        for n in js.get("nodes", []):
            if ("rotation" in n or "scale" in n) and not n.get("name", "").startswith("HALO_Swatch"):
                r["issues"].append(f"node {n.get('name')} has rotation/scale")
        mesh_node = {n["mesh"]: n.get("name") for n in js.get("nodes", []) if "mesh" in n}
        for mi, m in enumerate(js.get("meshes", [])):
            nm = mesh_node.get(mi, m.get("name"))
            info = {"prims": [], "tris": 0, "zero_area_tris": 0}
            for p in m["primitives"]:
                a = p["attributes"]
                if "NORMAL" not in a or "TEXCOORD_0" not in a:
                    r["issues"].append(f"mesh {nm} primitive without NORMAL/TEXCOORD_0")
                if "material" not in p:
                    r["issues"].append(f"mesh {nm} primitive without material")
                pos = accessor(js, binc, a["POSITION"]).astype(np.float64)
                idx = accessor(js, binc, p["indices"]).ravel() if "indices" in p else np.arange(len(pos))
                t = idx.reshape(-1, 3)
                v0, v1, v2 = pos[t[:, 0]], pos[t[:, 1]], pos[t[:, 2]]
                area = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
                zero = int((area < AREA_MIN).sum())
                info["tris"] += len(t)
                info["zero_area_tris"] += zero
                info["prims"].append(mats[p["material"]]["name"] if "material" in p else None)
                if zero:
                    r["issues"].append(f"mesh {nm}: {zero} zero-area triangles (area < {AREA_MIN:g} m2)")
            r["mesh_info"][nm] = info
            # arcs and far glass: glass only (the frame lives in HALO_<Core>_Frame_<Weight>)
            if "_Arc_" in nm or "_Far_Glass_" in nm:
                if len(info["prims"]) != 1 or not info["prims"][0].startswith("M_HALO_Glass"):
                    r["issues"].append(f"{nm}: primitives {info['prims']} (expected one glass primitive)")
            # banded frames and bands carry the lip glass, found by material name
            if any(k in nm for k in ("_Frame_Medium", "_Frame_Heavy", "_Band_")):
                if "M_HALO_Glass_T1" not in info["prims"]:
                    r["issues"].append(f"{nm}: no lip glass primitive (M_HALO_Glass_T1)")
        mat_info = {}
        for m in mats:
            ext = m.get("extensions", {})
            pbr = m.get("pbrMetallicRoughness", {})
            mat_info[m["name"]] = {
                "doubleSided": m.get("doubleSided", False), "alphaMode": m.get("alphaMode", "OPAQUE"),
                "roughness": round(pbr.get("roughnessFactor", 1.0), 3),
                "metallic": round(pbr.get("metallicFactor", 1.0), 3),
                "emissiveFactor": [round(x, 3) for x in m.get("emissiveFactor", [0, 0, 0])],
                "emissive_strength": ext.get("KHR_materials_emissive_strength", {}).get("emissiveStrength"),
                "emissiveTexture": "emissiveTexture" in m, "baseColorFactor":
                    [round(x, 3) for x in pbr.get("baseColorFactor", [1, 1, 1, 1])],
                "clearcoat": ext.get("KHR_materials_clearcoat", {}).get("clearcoatFactor")}
            if m.get("doubleSided"):
                r["issues"].append(f"material {m['name']} is double-sided")
            if m.get("alphaMode", "OPAQUE") != "OPAQUE" and m["name"].startswith("M_HALO"):
                r["issues"].append(f"material {m['name']} alphaMode {m.get('alphaMode')}")
            if m["name"].startswith("M_HALO_Glass_Broken") and "emissiveTexture" not in m:
                r["issues"].append(f"material {m['name']} has no emissive (crack) texture")
            if m["name"] == "M_HALO_Glass_Off":      # satin, not a mirror (review r2 #4)
                cc = mat_info[m["name"]]["clearcoat"] or 0.0
                if pbr.get("roughnessFactor", 1.0) < 0.3 or cc > 0.35:
                    r["issues"].append(f"M_HALO_Glass_Off too glossy: rough {pbr.get('roughnessFactor')}, coat {cc}")
        r["material_info"] = mat_info
        if fn == "HALO_Materials.glb":
            for mn in want_mats:
                if mn not in mat_info:
                    r["issues"].append(f"material library lacks {mn}")
        # draw calls / triangles of an assembled near halo (4 arc glass + 1 frame + cells; pips are instanced)
        if fn[5:-4] in CORES:
            c = fn[5:-4]
            mi = r["mesh_info"]
            arcs = [mi[f"HALO_{c}_Arc_{z}"] for z in ZONES]
            cell = mi[f"HALO_PowerCell_{c}"]
            r["assembled"] = {}
            for w in WEIGHTS:
                fr = mi[f"HALO_{c}_Frame_{w}"]
                ff = mi[f"HALO_{c}_Far_Frame_{w}"]
                far_glass = [mi[f"HALO_{c}_Far_Glass_{z}"] for z in ZONES]
                r["assembled"][w] = {
                    "near_draws_ring": 4 + len(fr["prims"]),
                    "near_draws_with_cells": 4 + len(fr["prims"]) + CELLS[w] * len(cell["prims"]),
                    "near_tris_with_cells": sum(a["tris"] for a in arcs) + fr["tris"] + CELLS[w] * cell["tris"],
                    "far_draws_ring": 4 + len(ff["prims"]),
                    "far_tris_with_cells": sum(a["tris"] for a in far_glass) + ff["tris"] + CELLS[w] * cell["tris"]}
        report[fn] = r
        for i in r["issues"]:
            fails.append(f"{fn}: {i}")
    out = os.path.join(HERE, "qa_glb_report.json")
    json.dump(report, open(out, "w"), indent=1)
    for fn, r in report.items():
        for w, a in r.get("assembled", {}).items():
            print(f"  {fn:<18} {w:<6} near: {a['near_draws_ring']} ring draws, {a['near_draws_with_cells']} with cells, "
                  f"{a['near_tris_with_cells']} tris | far: {a['far_draws_ring']} ring draws, "
                  f"{a['far_tris_with_cells']} tris")
    zt = sum(i["zero_area_tris"] for r in report.values() for i in r["mesh_info"].values())
    print(f"  zero-area triangles in all files: {zt}")
    for f in fails:
        print("FAIL", f)
    print(f"{len(files)} files checked, {len(fails)} issues -> {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
