"""Review r2: pure-python GLB scan (no Blender). Parses every MAKO glb, reports node tree, sockets
(converted back to Blender axes) vs sockets.json, materials, textures, emissive, extras, tri counts."""
import json, struct, os, sys, math
HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
OUT = os.path.join(HERE, "review", "r2")

def load(p):
    b = open(p, "rb").read()
    magic, ver, ln = struct.unpack_from("<III", b, 0)
    assert magic == 0x46546C67
    off = 12; js = None; binc = None
    while off < ln:
        cl, ct = struct.unpack_from("<II", b, off); off += 8
        chunk = b[off:off + cl]; off += cl
        if ct == 0x4E4F534A: js = json.loads(chunk)
        elif ct == 0x004E4942: binc = chunk
    return js, binc

def qmat(q):
    x, y, z, w = q
    return [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],[2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],[2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]

def world(js):
    nodes = js["nodes"]; res = {}
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []): parent[c] = i
    def local(n):
        t = n.get("translation", [0,0,0]); r = n.get("rotation", [0,0,0,1]); s = n.get("scale", [1,1,1])
        return t, r, s
    def wpos(i):
        # compose translations/rotations (scale assumed 1)
        chain = []; k = i
        while k is not None: chain.append(k); k = parent.get(k)
        pos = [0,0,0]; R = [[1,0,0],[0,1,0],[0,0,1]]
        for k in reversed(chain):
            t, r, s = local(nodes[k])
            tt = [sum(R[a][b]*t[b] for b in range(3)) for a in range(3)]
            pos = [pos[a]+tt[a] for a in range(3)]
            M = qmat(r); R = [[sum(R[a][c]*M[c][b] for c in range(3)) for b in range(3)] for a in range(3)]
        return pos, R
    for i, n in enumerate(nodes):
        p, R = wpos(i)
        # glTF Y-up -> Blender: (x, -z, y)
        res[n.get("name", f"node{i}")] = {"blender_loc": [round(p[0],5), round(-p[2],5), round(p[1],5)],
                                         "rot_identity": all(abs(R[a][b]-(a==b))<1e-5 for a in range(3) for b in range(3)),
                                         "parent": nodes[parent[i]].get("name") if i in parent else None,
                                         "mesh": n.get("mesh"), "extras": n.get("extras")}
    return res

sockets_json = json.load(open(os.path.join(HERE, "sockets.json")))
report = {}
for fn in sorted(os.listdir(HERE)):
    if not fn.endswith(".glb"): continue
    p = os.path.join(HERE, fn)
    js, binc = load(p)
    W = world(js)
    r = {"bytes": os.path.getsize(p), "nodes": len(js["nodes"]), "meshes": len(js.get("meshes", [])),
         "materials": [], "images": [], "issues": []}
    # tris
    tris = 0; prims_wo_mat = 0; prims_wo_uv = 0; prims_wo_normal = 0; prim_count = 0
    for m in js.get("meshes", []):
        for pr in m["primitives"]:
            prim_count += 1
            if "material" not in pr: prims_wo_mat += 1
            if "TEXCOORD_0" not in pr["attributes"]: prims_wo_uv += 1
            if "NORMAL" not in pr["attributes"]: prims_wo_normal += 1
            if "indices" in pr: tris += js["accessors"][pr["indices"]]["count"] // 3
    r.update(tris=tris, primitives=prim_count, prims_without_material=prims_wo_mat, prims_without_uv=prims_wo_uv,
             prims_without_normal=prims_wo_normal)
    for mt in js.get("materials", []):
        pbr = mt.get("pbrMetallicRoughness", {})
        r["materials"].append({"name": mt.get("name"), "baseColorFactor": pbr.get("baseColorFactor"),
                               "baseColorTexture": "baseColorTexture" in pbr,
                               "metal": pbr.get("metallicFactor"), "rough": pbr.get("roughnessFactor"),
                               "emissive": mt.get("emissiveFactor"), "doubleSided": mt.get("doubleSided", False),
                               "ext": list(mt.get("extensions", {}).keys())})
        if mt.get("emissiveFactor") and any(v > 0 for v in mt["emissiveFactor"]):
            r["issues"].append(f"emissive material {mt.get('name')}")
    for im in js.get("images", []):
        r["images"].append({"name": im.get("name"), "embedded": "bufferView" in im, "mime": im.get("mimeType")})
    r["extensionsUsed"] = js.get("extensionsUsed", [])
    r["node_names"] = sorted(W.keys())
    r["roots"] = [n for n, v in W.items() if v["parent"] is None]
    sock = {n: v for n, v in W.items() if "_SOCKET_" in n}
    r["sockets"] = {n: v["blender_loc"] for n, v in sock.items()}
    for n, v in sock.items():
        if not v["rot_identity"]: r["issues"].append(f"{n} rotated")
        if n in sockets_json:
            d = max(abs(a - b) for a, b in zip(v["blender_loc"], sockets_json[n]["location"]))
            if d > 1e-4: r["issues"].append(f"{n} glb {v['blender_loc']} != sockets.json {sockets_json[n]['location']} (d {d*1000:.1f} mm)")
    r["extras_nodes"] = {n: v["extras"] for n, v in W.items() if v["extras"]}
    r["helper_nodes"] = [n for n in W if n.startswith("_")]
    # node bbox via accessor min/max of positions (local) - only roots w/ origin
    report[fn] = r

json.dump(report, open(os.path.join(OUT, "r2_glb_scan.json"), "w"), indent=1)
for fn, r in report.items():
    print(f"== {fn}: {r['bytes']//1024} KB nodes {r['nodes']} prims {r['primitives']} tris {r['tris']} "
          f"noMat {r['prims_without_material']} noUV {r['prims_without_uv']} noN {r['prims_without_normal']}")
    print("   roots", r["roots"], "helpers", r["helper_nodes"], "extras", list(r["extras_nodes"].keys())[:5])
    print("   mats", [(m["name"], m["baseColorFactor"], m["baseColorTexture"], m["emissive"]) for m in r["materials"]])
    print("   images", [(i["name"], i["embedded"]) for i in r["images"]], "ext", r["extensionsUsed"])
    for i in r["issues"]: print("   ISSUE", i)
    if r["sockets"]: print("   sockets", r["sockets"])
