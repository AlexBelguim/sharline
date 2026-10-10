"""Inspect serialized Showhome deliverables, rather than just the Blender scene.

Run with normal Python: python assets/maps/showhome/verify_kit.py
Writes kit/export_validation.json. Missing work in progress is reported explicitly.
"""
from pathlib import Path
import hashlib
import json
import math
import struct

HERE = Path(__file__).resolve().parent


def read_glb(path):
    blob = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", blob)
    assert magic == b"glTF" and version == 2 and length == len(blob), path
    pos, doc, binary = 12, None, b""
    while pos < len(blob):
        size, kind = struct.unpack_from("<I4s", blob, pos)
        payload = blob[pos + 8:pos + 8 + size]
        if kind == b"JSON":
            doc = json.loads(payload)
        elif kind == b"BIN\0":
            binary = payload
        pos += size + 8
    assert doc and pos == len(blob)
    return doc, binary


def accessor(doc, binary, index):
    a = doc["accessors"][index]
    view = doc["bufferViews"][a["bufferView"]]
    sizes = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
    fmt, width = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2), 5123: ("H", 2),
                  5125: ("I", 4), 5126: ("f", 4)}[a["componentType"]]
    count = sizes[a["type"]]
    start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", count * width)
    unpack = struct.Struct("<" + fmt * count)
    for i in range(a["count"]):
        row = unpack.unpack_from(binary, start + i * stride)
        if a.get("normalized"):
            limit = {5120: 127, 5121: 255, 5122: 32767, 5123: 65535}[a["componentType"]]
            row = tuple(max(-1, x / limit) for x in row)
        yield row


def audit(path):
    if not path.exists():
        return {"path": str(path.relative_to(HERE)), "status": "MISSING"}
    d, binary = read_glb(path)
    problems, per_mesh, materials = [], [], d.get("materials", [])
    for i, mesh in enumerate(d.get("meshes", [])):
        primitives = mesh["primitives"]
        if len(primitives) != 1:
            problems.append(f"{mesh.get('name', i)} has {len(primitives)} material primitives; separate meshes required")
        triangles = 0
        for p in primitives:
            if p.get("mode", 4) != 4:
                problems.append(f"{mesh.get('name', i)} is not triangles")
            at = p["attributes"]
            for key in ("POSITION", "NORMAL", "TEXCOORD_0"):
                if key not in at:
                    problems.append(f"{mesh.get('name', i)} missing {key}")
            triangles += d["accessors"][p.get("indices", at["POSITION"])]["count"] // 3
            if "COLOR_0" in at and mesh.get("name", "").startswith("GND_Ground"):
                rows = list(accessor(d, binary, at["COLOR_0"]))
                if not rows or len(rows[0]) != 4:
                    problems.append("Ground blend mask COLOR_0 must be RGBA")
                elif not any(r[3] < .99 for r in rows):
                    problems.append("Ground blend mask alpha appears forced to opaque")
        per_mesh.append({"name": mesh.get("name", str(i)), "triangles": triangles,
                         "material": materials[primitives[0].get("material", 0)].get("name", "") if materials else ""})
    nodes = d.get("nodes", [])
    instance_triangles = sum(per_mesh[n["mesh"]]["triangles"] for n in nodes if "mesh" in n)
    for m in materials:
        if m.get("alphaMode", "OPAQUE") == "BLEND":
            problems.append(f"{m.get('name')} uses alpha blending")
    for s in d.get("samplers", []):
        if s.get("wrapS", 10497) != 10497 or s.get("wrapT", 10497) != 10497:
            problems.append("A sampler clamps a repeating texture")
    return {"path": str(path.relative_to(HERE)), "status": "PASS" if not problems else "REVIEW",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
            "meshes": len(per_mesh), "materials": len(materials), "images": len(d.get("images", [])),
            "unique_triangles": sum(m["triangles"] for m in per_mesh), "instanced_triangles": instance_triangles,
            "roots": [nodes[i].get("name", str(i)) for i in d["scenes"][d.get("scene", 0)]["nodes"]],
            "problems": problems, "mesh_counts": per_mesh}


def main():
    report = {"frame": "GLB: x=east,y=up,z=south; identity load; design=(x,-z,y)",
              "assets": [audit(HERE / p) for p in ("kit/houses.glb", "kit/ground.glb", "kit/props.glb",
                                                   "kit/props_placed.glb", "backdrop/backdrop.glb")]}
    path = HERE / "kit/export_validation.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    for a in report["assets"]:
        print(a["path"], a["status"], a.get("instanced_triangles", ""), "tris", a.get("problems", []))
    print("wrote", path)


if __name__ == "__main__":
    main()
