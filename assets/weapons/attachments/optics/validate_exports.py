"""validate_exports.py - structural glTF / FBX checks for the ATT optics exports (system python, no deps).

  python "F:/git/val etf/assets/weapons/attachments/optics/validate_exports.py"

Checks per ATT_<optic>.glb: GLB header/chunks, required nodes (root, _Body, _SOCKET_ADS and every role node the
catalog lists: _Glass, _Objective, _Ocular, _Display, _Reticle, _Glint, _StatusLight), the root's <role>_node extras,
ADS socket position (glTF is Y-up: Blender (x, y, z) -> glTF (x, z, -y)) and eye_relief_m against catalog.json,
every primitive has a material and indices, lens / display nodes have their OWN material (not shared with any
other node, so the engine can bind a scope view or glint shader), emissive materials only on _Reticle / _Glint /
_StatusLight, reticle / glint materials single-sided, every image embedded (bufferView, no external uri), no
KHR_texture_transform, triangle budget 1.5k-5k, and the .fbx exists with its textures embedded (PNG payloads).
Exit code 1 on any failure.
"""
import json
import math
import os
import struct
import sys

OUT = os.path.dirname(os.path.abspath(__file__))
if "--out" in sys.argv:
    OUT = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
OWN_MATERIAL_ROLES = ("objective", "ocular", "display")
EMISSIVE_ROLES = ("reticle", "glint", "status_light", "hologram", "flap_l", "flap_r")


def load_glb(path):
    b = open(path, "rb").read()
    magic, ver, length = struct.unpack("<4sII", b[:12])
    assert magic == b"glTF" and ver == 2 and length == len(b), "bad GLB header"
    jl, jt = struct.unpack("<I4s", b[12:20])
    assert jt == b"JSON"
    j = json.loads(b[20:20 + jl])
    off = 20 + jl
    bin_len = 0
    if off < len(b):
        bl, bt = struct.unpack("<I4s", b[off:off + 8])
        assert bt == b"BIN\x00"
        bin_len = bl
    return j, bin_len


def node_materials(j, node):
    if "mesh" not in node:
        return []
    return [pr.get("material") for pr in j["meshes"][node["mesh"]]["primitives"]]


def triangle_geometry(path, j):
    """Check the delivered float32 positions directly, before Blender import can
    obscure tiny triangle areas through its own float arithmetic."""
    raw = open(path, "rb").read()
    json_size = struct.unpack_from("<I", raw, 12)[0]
    binary = raw[28 + json_size:]

    def accessor(index):
        acc = j["accessors"][index]
        view = j["bufferViews"][acc["bufferView"]]
        fmt = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}[acc["componentType"]]
        size = {"SCALAR": 1, "VEC3": 3}[acc["type"]]
        unpack = struct.Struct("<" + fmt * size)
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride", unpack.size)
        return [unpack.unpack_from(binary, start + i * stride) for i in range(acc["count"])]

    count, opposing, minimum = 0, 0, math.inf
    for mesh in j["meshes"]:
        for primitive in mesh["primitives"]:
            positions = accessor(primitive["attributes"]["POSITION"])
            normals = accessor(primitive["attributes"]["NORMAL"])
            indices = [x[0] for x in accessor(primitive["indices"])]
            for i in range(0, len(indices), 3):
                a, b, c = (positions[v] for v in indices[i:i + 3])
                u, v = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
                cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
                         u[0] * v[1] - u[1] * v[0])
                area = math.sqrt(sum(x * x for x in cross)) / 2
                minimum = min(minimum, area)
                count += area < 1e-11
                normal = [sum(normals[v][k] for v in indices[i:i + 3]) for k in range(3)]
                norm_len = math.sqrt(sum(x * x for x in normal))
                if area >= 1e-11 and norm_len:
                    cosine = sum(cross[k] * normal[k] for k in range(3)) / (2 * area * norm_len)
                    opposing += cosine < -0.5
    return {"degenerate_triangles": count, "opposing_normal_triangles": opposing,
            "min_triangle_area_m2": minimum}


def main():
    cat = json.load(open(os.path.join(OUT, "catalog.json")))
    ok = True
    for e in cat["optics"]:
        oid = e["id"]
        p = os.path.join(OUT, e["file"])
        errs = []
        j, bin_len = load_glb(p)
        geometry = triangle_geometry(p, j)
        if geometry["degenerate_triangles"]:
            errs.append("%d degenerate exported triangles" % geometry["degenerate_triangles"])
        if geometry["opposing_normal_triangles"]:
            errs.append("%d exported triangles have opposing corner normals" % geometry["opposing_normal_triangles"])
        names = [n.get("name") for n in j["nodes"]]
        byname = {n.get("name"): n for n in j["nodes"]}
        roles = {r: nm for r, nm in e.get("nodes", {}).items() if nm}
        for req in ["ATT_" + oid, "ATT_%s_SOCKET_ADS" % oid] + list(roles.values()):
            if req not in names:
                errs.append("missing node " + req)
        root = byname.get("ATT_" + oid, {})
        rx = root.get("extras", {})
        for r, nm in roles.items():
            if rx.get(r + "_node") != nm:
                errs.append("root extras %s_node = %s, catalog says %s" % (r, rx.get(r + "_node"), nm))
        for k in ("ocular_node", "objective_node", "reticle_node", "glint_node"):
            if e.get(k) and e[k] not in names:
                errs.append("%s %s is not a node" % (k, e[k]))
        ads = byname.get("ATT_%s_SOCKET_ADS" % oid, {})
        t = ads.get("translation", [0, 0, 0])
        blender = (t[0], -t[2], t[1])
        want = e["ads_location_m"]
        if max(abs(a - b) for a, b in zip(blender, want)) > 1e-4:
            errs.append("ADS socket at %s, catalog says %s" % (blender, want))
        if abs(ads.get("extras", {}).get("eye_relief_m", -1) - e["eye_relief_m"]) > 1e-6:
            errs.append("ADS socket eye_relief_m does not match the catalog")
        if any(k in root for k in ("translation", "rotation", "scale")):
            errs.append("root node is not at the identity (mount point must be the origin)")
        # materials per role node
        mats = j.get("materials", [])
        users = {}
        for n in j["nodes"]:
            for mi in node_materials(j, n):
                users.setdefault(mi, set()).add(n["name"])
        for r in OWN_MATERIAL_ROLES:
            if r in roles:
                for mi in node_materials(j, byname[roles[r]]):
                    if users.get(mi, set()) != {roles[r]}:
                        errs.append("%s node %s shares material %s with %s" % (
                            r, roles[r], mats[mi]["name"], sorted(users[mi] - {roles[r]})))
        emissive_ok = {roles[r] for r in EMISSIVE_ROLES if r in roles}
        for mi, m in enumerate(mats):
            emis = any(c > 0 for c in m.get("emissiveFactor", [0, 0, 0]))
            if emis and not users.get(mi, set()) <= emissive_ok:
                errs.append("emissive material %s on %s" % (m["name"], sorted(users.get(mi, set()))))
            if users.get(mi, set()) & {roles.get("reticle"), roles.get("glint")} and m.get("doubleSided"):
                errs.append("reticle / glint material %s is double-sided" % m["name"])
        if roles.get("hologram"):                       # optic_projector: flip-up flaps + hologram plane
            for r in ("flap_l", "flap_r"):
                ex = byname.get(roles.get(r, ""), {}).get("extras", {})
                if "fold_angle_deg" not in ex or "open_angle_deg" not in ex:
                    errs.append("%s node lacks fold_angle_deg / open_angle_deg extras" % r)
                if any(k in byname.get(roles.get(r, ""), {}) for k in ("rotation", "scale")):
                    rot = byname[roles[r]].get("rotation", [0, 0, 0, 1])
                    if max(abs(a - b) for a, b in zip(rot, [0, 0, 0, 1])) > 1e-5:
                        errs.append("%s rest rotation is not identity (rest pose must be folded)" % r)
            hn = byname.get(roles["hologram"], {})
            hm = [mats[mi] for mi in node_materials(j, hn)]
            if not hm or not all(m.get("alphaMode") == "BLEND" and "emissiveTexture" in m and
                                 "baseColorTexture" in m.get("pbrMetallicRoughness", {}) for m in hm):
                errs.append("hologram material must be alpha-blended with base + emissive textures")
            if not any(a.get("name") == "ADS_Open" for a in j.get("animations", [])):
                errs.append("missing ADS_Open flap animation")
            else:
                an = next(a for a in j["animations"] if a.get("name") == "ADS_Open")
                tgt = {j["nodes"][c["target"]["node"]]["name"] for c in an["channels"]}
                if tgt != {roles["flap_l"], roles["flap_r"]}:
                    errs.append("ADS_Open animates %s, expected both flaps" % sorted(tgt))
                tmax = max(j["accessors"][smp["input"]]["max"][0] for smp in an["samplers"])
                print("               ADS_Open: %d channels, %.3f s" % (len(an["channels"]), tmax))
        tris = 0
        for m in j["meshes"]:
            for pr in m["primitives"]:
                if "material" not in pr:
                    errs.append("primitive without material in mesh " + m.get("name", "?"))
                if "indices" not in pr:
                    errs.append("primitive without indices in mesh " + m.get("name", "?"))
                else:
                    tris += j["accessors"][pr["indices"]]["count"] // 3
        for im in j.get("images", []):
            if "uri" in im or "bufferView" not in im:
                errs.append("image not embedded: %s" % im.get("name"))
        if "KHR_texture_transform" in j.get("extensionsUsed", []):
            errs.append("uses KHR_texture_transform")
        if not 1500 <= tris <= 5000:
            errs.append("tri count %d outside 1.5k-5k" % tris)
        fbx = os.path.join(OUT, e["file_fbx"])
        npng = 0
        if not os.path.exists(fbx):
            errs.append("missing fbx")
        else:
            npng = open(fbx, "rb").read().count(b"\x89PNG\r\n\x1a\n")
            if npng < len(j.get("images", [])):
                errs.append("fbx embeds %d PNG textures, the glb has %d images" % (npng, len(j.get("images", []))))
        emissive = [m["name"] for m in mats if any(c > 0 for c in m.get("emissiveFactor", [0, 0, 0]))]
        print("%-14s %s  tris=%d  nodes=%s" % (oid, "OK  " if not errs else "FAIL", tris, names))
        print("               materials=%s" % [m["name"] for m in mats])
        print("               emissive=%s images=%d fbx_png=%d ext=%s bin=%d B" % (
            emissive, len(j.get("images", [])), npng, j.get("extensionsUsed", []), bin_len))
        print("               ADS(blender)=%s extras=%s" % (tuple(round(v, 4) for v in blender), ads.get("extras")))
        for er in errs:
            print("    ERROR:", er)
        ok = ok and not errs
    print("ALL OK" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
