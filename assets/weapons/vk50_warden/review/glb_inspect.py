"""Independent glTF validity check (system python, no deps): parse every Warden .glb JSON chunk and report
node tree, transforms, materials, primitives, attributes, textures, extensions and position bounds."""
import json, struct, sys, os, glob
D = r"F:/git/val etf/assets/weapons/vk50_warden"

def load(p):
    b = open(p, "rb").read()
    magic, ver, length = struct.unpack_from("<4sII", b, 0)
    assert magic == b"glTF", p
    off = 12; js = None; binc = None
    while off < length:
        cl, ct = struct.unpack_from("<II", b, off)
        chunk = b[off + 8: off + 8 + cl]
        if ct == 0x4E4F534A: js = json.loads(chunk)
        elif ct == 0x004E4942: binc = chunk
        off += 8 + cl
    return js, binc, ver, length, len(b)

for p in sorted(glob.glob(D + "/*.glb")):
    js, binc, ver, length, flen = load(p)
    print("=" * 100)
    print(os.path.basename(p), "ver", ver, "len", length, "file", flen, "bin", len(binc) if binc else None)
    print(" asset", js.get("asset"), "extUsed", js.get("extensionsUsed"), "extReq", js.get("extensionsRequired"))
    nodes = js["nodes"]
    scn = js["scenes"][js.get("scene", 0)]
    def walk(i, d):
        n = nodes[i]
        extra = []
        if "translation" in n: extra.append("t=" + str([round(v, 4) for v in n["translation"]]))
        if "rotation" in n: extra.append("r=" + str([round(v, 4) for v in n["rotation"]]))
        if "scale" in n: extra.append("s=" + str([round(v, 4) for v in n["scale"]]))
        if "matrix" in n: extra.append("MATRIX")
        if "mesh" in n:
            m = js["meshes"][n["mesh"]]
            extra.append(f"mesh={m.get('name')} prims={len(m['primitives'])}")
        if n.get("extras"): extra.append("extras=" + json.dumps(n["extras"])[:160])
        print("  " * d + " -", n.get("name"), " ".join(extra))
        for c in n.get("children", []): walk(c, d + 1)
    for r in scn["nodes"]: walk(r, 1)
    # materials
    for i, m in enumerate(js.get("materials", [])):
        pbr = m.get("pbrMetallicRoughness", {})
        print(f"  MAT[{i}] {m.get('name')} bcf={[round(v,3) for v in pbr.get('baseColorFactor',[1,1,1,1])]} "
              f"tex={'baseColorTexture' in pbr} rough={pbr.get('roughnessFactor',1)} metal={pbr.get('metallicFactor',1)} "
              f"ds={m.get('doubleSided', False)} emis={m.get('emissiveFactor')} ext={list(m.get('extensions',{}).keys())} "
              f"texext={list(pbr.get('baseColorTexture',{}).get('extensions',{}).keys())}")
    # images
    for i, im in enumerate(js.get("images", [])):
        print(f"  IMG[{i}] {im.get('name')} uri={im.get('uri')} bv={im.get('bufferView')} mime={im.get('mimeType')}")
    for i, s in enumerate(js.get("samplers", [])):
        print(f"  SAMPLER[{i}] {s}")
    # primitives
    nprim = 0; nomat = 0; nouv = 0; nonorm = 0; tri = 0
    mn = [1e9] * 3; mx = [-1e9] * 3
    for m in js["meshes"]:
        for pr in m["primitives"]:
            nprim += 1
            if "material" not in pr: nomat += 1; print("   NO MATERIAL prim in", m.get("name"))
            a = pr["attributes"]
            if "TEXCOORD_0" not in a: nouv += 1; print("   NO UV prim in", m.get("name"))
            if "NORMAL" not in a: nonorm += 1
            if pr.get("mode", 4) != 4: print("   non-triangle mode", pr.get("mode"), m.get("name"))
            if "indices" in pr: tri += js["accessors"][pr["indices"]]["count"] // 3
    print(f"  prims={nprim} no_mat={nomat} no_uv={nouv} no_normal={nonorm} tris(index/3)={tri}")
