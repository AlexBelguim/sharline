"""Round-2 review: raw glTF JSON validity check for every Warden .glb (system python, no deps).
Reports node tree, transforms, extras, materials (factor/texture/emissive/doubleSided), images (embedded?,
size), samplers, primitives (material / UV / normal / tangent), extensions, tri counts, accessor bounds."""
import json, struct, os, glob, sys
D = r"F:/git/val etf/assets/weapons/vk50_warden"
OUT = os.path.join(D, "review", "r2", "glb_json_report.txt")
lines = []
def P(*a):
    s = " ".join(str(x) for x in a); lines.append(s); print(s)

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

def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n": return None
    w, h = struct.unpack(">II", data[16:24]); return (w, h)

for p in sorted(glob.glob(D + "/*.glb")):
    js, binc, ver, length, flen = load(p)
    P("=" * 110)
    P(os.path.basename(p), "glTF ver", ver, "declared", length, "file", flen, "bin", len(binc) if binc else None,
      "OK" if length == flen else "LENGTH MISMATCH")
    P(" asset", js.get("asset"), "extUsed", js.get("extensionsUsed"), "extReq", js.get("extensionsRequired"))
    nodes = js["nodes"]
    scn = js["scenes"][js.get("scene", 0)]
    P(" scene roots:", [nodes[i].get("name") for i in scn["nodes"]])
    names = [n.get("name") for n in nodes]
    dup = {n for n in names if names.count(n) > 1}
    if dup: P(" DUPLICATE NODE NAMES", dup)
    def walk(i, d):
        n = nodes[i]; extra = []
        if "translation" in n: extra.append("t=" + str([round(v, 4) for v in n["translation"]]))
        if "rotation" in n: extra.append("r=" + str([round(v, 4) for v in n["rotation"]]))
        if "scale" in n: extra.append("s=" + str([round(v, 4) for v in n["scale"]]))
        if "matrix" in n: extra.append("MATRIX")
        if "mesh" in n:
            m = js["meshes"][n["mesh"]]
            extra.append(f"mesh={m.get('name')} prims={len(m['primitives'])}")
        if n.get("extras"): extra.append("extras=" + json.dumps(n["extras"])[:200])
        P("  " * d + " -", n.get("name"), " ".join(extra))
        for c in n.get("children", []): walk(c, d + 1)
    for r in scn["nodes"]: walk(r, 1)
    for i, m in enumerate(js.get("materials", [])):
        pbr = m.get("pbrMetallicRoughness", {})
        P(f"  MAT[{i}] {m.get('name')} bcf={[round(v,3) for v in pbr.get('baseColorFactor',[1,1,1,1])]} "
          f"bctex={'baseColorTexture' in pbr} mrtex={'metallicRoughnessTexture' in pbr} rough={pbr.get('roughnessFactor',1)} "
          f"metal={pbr.get('metallicFactor',1)} doubleSided={m.get('doubleSided', False)} emissive={m.get('emissiveFactor')} "
          f"emtex={'emissiveTexture' in m} alpha={m.get('alphaMode','OPAQUE')} ext={list(m.get('extensions',{}).keys())} "
          f"texext={list(pbr.get('baseColorTexture',{}).get('extensions',{}).keys())} normtex={'normalTexture' in m}")
    for i, im in enumerate(js.get("images", [])):
        sz = None
        if "bufferView" in im and binc is not None:
            bv = js["bufferViews"][im["bufferView"]]
            sz = png_size(binc[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]])
        P(f"  IMG[{i}] {im.get('name')} uri={im.get('uri')} embedded={'bufferView' in im} mime={im.get('mimeType')} size={sz}")
    for i, s in enumerate(js.get("samplers", [])):
        P(f"  SAMPLER[{i}] {s}")
    nprim = nomat = nouv = nonorm = tri = 0; tan = 0; col = 0
    for m in js["meshes"]:
        for pr in m["primitives"]:
            nprim += 1
            a = pr["attributes"]
            if "material" not in pr: nomat += 1; P("   NO MATERIAL prim in", m.get("name"))
            if "TEXCOORD_0" not in a: nouv += 1; P("   NO UV prim in", m.get("name"))
            if "NORMAL" not in a: nonorm += 1; P("   NO NORMAL prim in", m.get("name"))
            if "TANGENT" in a: tan += 1
            if "COLOR_0" in a: col += 1
            if pr.get("mode", 4) != 4: P("   non-triangle mode", pr.get("mode"), m.get("name"))
            if "indices" in pr: tri += js["accessors"][pr["indices"]]["count"] // 3
    P(f"  meshes={len(js['meshes'])} prims={nprim} no_mat={nomat} no_uv={nouv} no_normal={nonorm} tangents={tan} vcol={col} tris={tri}")
open(OUT, "w").write("\n".join(lines))
