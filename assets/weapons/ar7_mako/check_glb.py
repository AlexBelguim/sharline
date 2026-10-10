"""Validate the MAKO GLB exports (system python, no deps): structure, names, sockets, materials, textures, engine
extras, and (r2 round 2) zero-area triangles.
Run: python check_glb.py            (exit code 1 on any error)"""
import glob
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if "--out" in sys.argv:
    HERE = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
SOCKETS = ["MAKO_SOCKET_Optic", "MAKO_SOCKET_Stock", "MAKO_SOCKET_Mag", "MAKO_SOCKET_Under", "MAKO_SOCKET_Side_R",
           "MAKO_SOCKET_Side_L", "MAKO_SOCKET_Shield", "MAKO_SOCKET_Muzzle", "MAKO_SOCKET_LeftHand"]


BIN = {}


def load(path):
    b = open(path, "rb").read()
    magic, ver, total = struct.unpack("<4sII", b[:12])
    assert magic == b"glTF" and ver == 2, "not a glTF 2 binary"
    jl, jt = struct.unpack("<I4s", b[12:20])
    assert jt == b"JSON"
    j = json.loads(b[20:20 + jl])
    rest = b[20 + jl:]
    binlen = struct.unpack("<I4s", rest[:8])[0] if rest else 0
    BIN[id(j)] = rest[8:8 + binlen]
    return j, binlen, total


def accessor(j, i):
    """Read accessor i as a list of tuples (float VEC3 positions or scalar indices)."""
    a = j["accessors"][i]
    bv = j["bufferViews"][a["bufferView"]]
    data = BIN[id(j)]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    fmt = {5126: "f", 5125: "I", 5123: "H", 5121: "B"}[a["componentType"]]
    size = struct.calcsize("<" + fmt)
    stride = bv.get("byteStride", size * ncomp)
    return [struct.unpack_from("<" + fmt * ncomp, data, off + k * stride) for k in range(a["count"])]


def zero_area_tris(j, area=1e-10):
    """Triangles under 1e-10 m^2 (0.0001 mm^2) in every primitive (the review's zero_area health metric)."""
    n = 0
    for m in j.get("meshes", []):
        for p in m["primitives"]:
            if "indices" not in p:
                continue
            P = accessor(j, p["attributes"]["POSITION"])
            idx = [t[0] for t in accessor(j, p["indices"])]
            for k in range(0, len(idx) - 2, 3):
                a, b, c = P[idx[k]], P[idx[k + 1]], P[idx[k + 2]]
                u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
                v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
                x = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                if 0.5 * (x[0] * x[0] + x[1] * x[1] + x[2] * x[2]) ** 0.5 < area:
                    n += 1
    return n


def tris(j):
    t = 0
    for m in j.get("meshes", []):
        for p in m["primitives"]:
            if "indices" in p:
                t += j["accessors"][p["indices"]]["count"] // 3
    return t


def world_pos(j, name):
    """Translation of a node composed up its parent chain (no rotation/scale expected on the MAKO nodes)."""
    parent = {}
    for i, n in enumerate(j["nodes"]):
        for c in n.get("children", []):
            parent[c] = i
    idx = next(i for i, n in enumerate(j["nodes"]) if n.get("name") == name)
    pos = [0.0, 0.0, 0.0]
    while idx is not None:
        n = j["nodes"][idx]
        t = n.get("translation", [0, 0, 0])
        if n.get("rotation") and any(abs(v) > 1e-6 for v in n["rotation"][:3]):
            print(f"   note: {n['name']} has rotation {n['rotation']}")
        pos = [pos[k] + t[k] for k in range(3)]
        idx = parent.get(idx)
    # glTF Y-up -> Blender Z-up: (x, y, z)_gl = (x, z, -y)_bl
    return (pos[0], -pos[2], pos[1])


def check(path, expect_sockets=False, expect_root=False):
    errs = []
    j, binlen, total = load(path)
    names = [n.get("name", "") for n in j["nodes"]]
    mats = j.get("materials", [])
    imgs = j.get("images", [])
    for m in j.get("meshes", []):
        for p in m["primitives"]:
            if "material" not in p:
                errs.append(f"mesh {m.get('name')} has a primitive without material")
            if "TEXCOORD_0" not in p["attributes"]:
                errs.append(f"mesh {m.get('name')} has no UVs")
            if "NORMAL" not in p["attributes"]:
                errs.append(f"mesh {m.get('name')} has no normals")
    for im in imgs:
        if "bufferView" not in im:
            errs.append(f"image {im.get('name')} is not embedded")
    for m in mats:
        e = m.get("emissiveFactor")
        if e and any(v > 0 for v in e):
            errs.append(f"material {m['name']} is emissive (base guns have no emissive)")
        pbr = m.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr and pbr.get("baseColorFactor", [1, 1, 1, 1])[:3] != [1, 1, 1]:
            errs.append(f"material {m['name']} mixes a texture with a factor (check)")
    for n in names:
        if n.startswith("_") or n.startswith("L_"):
            errs.append(f"helper node exported: {n}")
    if expect_root and "MAKO_Root" not in names:
        errs.append("MAKO_Root missing")
    if expect_sockets:
        for s in SOCKETS:
            if s not in names:
                errs.append(f"socket missing: {s}")
    za = zero_area_tris(j)
    if za:
        errs.append(f"{za} zero-area triangles (< 1e-10 m^2)")
    print(f"{os.path.basename(path)}: {total / 1024:.0f} KB, nodes {len(names)}, meshes {len(j.get('meshes', []))}, "
          f"materials {[m['name'] for m in mats]}, images {len(imgs)}, tris {tris(j)}, zero-area tris {za}")
    if expect_sockets:
        ref = json.load(open(os.path.join(HERE, "sockets.json")))
        for s in SOCKETS:
            if s in names:
                p = world_pos(j, s)
                want = ref[s]["location"]
                bad = max(abs(p[k] - want[k]) for k in range(3)) > 1e-4
                print(f"   {s:24s} ({p[0]:+.4f}, {p[1]:+.4f}, {p[2]:+.4f})" + ("   <-- MISMATCH" if bad else ""))
                if bad:
                    errs.append(f"{s} at {p}, sockets.json says {want}")
    errs += check_extras(path, j)
    for e in errs:
        print("   ERROR", e)
    return errs


def extras(j, name):
    n = next((n for n in j["nodes"] if n.get("name") == name), None)
    return None if n is None else n.get("extras", {})


def check_extras(path, j):
    """Engine data that travels as glTF extras (r2 review): moving-part strokes, stock travel, mag-check rounds."""
    errs = []
    base = os.path.basename(path)
    names = [n.get("name", "") for n in j["nodes"]]
    if base in ("mako_base.glb", "mako_default.glb"):
        ch = extras(j, "MAKO_ChargingHandle") or {}
        if abs(ch.get("stroke_m", 0) - 0.05) > 1e-6:
            errs.append(f"MAKO_ChargingHandle extras stroke_m = {ch.get('stroke_m')} (want 0.05)")
        if "push_m" not in (extras(j, "MAKO_ForwardAssist") or {}):
            errs.append("MAKO_ForwardAssist has no push_m extra")
    if base in ("MAKO_stock_standard.glb", "mako_default.glb"):
        st = extras(j, "MAKO_stock_standard") or {}
        tr, ch = st.get("travel_positions_m"), st.get("ch_stroke_max_m")
        if not tr or not ch or len(tr) != len(ch):
            errs.append(f"MAKO_stock_standard extras travel_positions_m / ch_stroke_max_m missing ({tr}, {ch})")
        else:
            print(f"   stock travel {tr}, CH stroke per position {ch}")
    for key, cap in (("mag_30", 30), ("mag_45", 45), ("mag_drum60", 60)):
        if base not in (f"MAKO_{key}.glb",) and not (key == "mag_30" and base == "mako_default.glb"):
            continue
        stack = [n for n in names if n.startswith(f"MAKO_{key}_Stack_")]
        mins = sorted((extras(j, n) or {}).get("min_rounds", -1) for n in stack)
        if not stack or min(mins) < 2 or max(mins) > cap:
            errs.append(f"{key}: Stack_NN nodes / min_rounds extras wrong: {len(stack)} nodes, {mins}")
        if (extras(j, f"MAKO_{key}_Round") or {}).get("min_rounds") != 1:
            errs.append(f"{key}: _Round has no min_rounds = 1 extra")
        if (extras(j, f"MAKO_{key}_Stack") or {}).get("capacity") != cap:
            errs.append(f"{key}: _Stack empty has no capacity = {cap} extra")
        else:
            print(f"   {key}: {len(stack)} mag-check rounds, min_rounds {mins[0]}..{mins[-1]}")
    return errs


def main():
    errs = []
    errs += check(os.path.join(HERE, "mako_base.glb"), expect_sockets=True, expect_root=True)
    errs += check(os.path.join(HERE, "mako_default.glb"), expect_sockets=True, expect_root=True)
    for p in sorted(glob.glob(os.path.join(HERE, "MAKO_*.glb"))):
        errs += check(p)
    print("OK" if not errs else f"{len(errs)} error(s)")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
