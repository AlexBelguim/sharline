"""Read the actual exported GLB, validate game-facing attributes, and write its measurable delivery facts."""
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KIT = ROOT / "assets/maps/showhome/kit"


def main():
    raw = (KIT / "houses.glb").read_bytes()
    magic, version, total = struct.unpack_from("<4sII", raw)
    assert magic == b"glTF" and version == 2 and total == len(raw), "Invalid GLB header"
    n, kind = struct.unpack_from("<II", raw, 12)
    assert kind == 0x4E4F534A, "Missing GLB JSON"
    data = json.loads(raw[20:20 + n])
    accessor = data["accessors"]
    triangles = {"SAGE": 0, "CLAY": 0}
    flags = []
    for node in data["nodes"]:
        assert not any(k in node for k in ("translation", "rotation", "scale", "matrix")), "Nonidentity node"
        if "mesh" not in node:
            continue
        mesh = data["meshes"][node["mesh"]]
        assert len(mesh["primitives"]) == 1, "A mesh has multiple materials"
        primitive = mesh["primitives"][0]
        attrs = primitive["attributes"]
        assert all(k in attrs for k in ("POSITION", "NORMAL", "TEXCOORD_0", "COLOR_0")), "Missing game attribute"
        position = accessor[attrs["POSITION"]]
        assert position["min"][0] >= 8.7 and position["max"][0] <= 63.3, "Unexpected horizontal frame"
        assert position["min"][1] >= -0.01 and position["max"][1] < 14.0, "Unexpected Y-up height"
        assert position["min"][2] > -33.0 and position["max"][2] < -15.5, "Unexpected north/-Z frame"
        team = "SAGE" if "SAGE" in node["name"] else "CLAY"
        triangles[team] += accessor[primitive["indices"]]["count"] // 3
    used_materials = data["materials"]
    for material in used_materials:
        external_height = material.get("extras", {}).get("height_map")
        if external_height and not (ROOT / external_height).exists():
            flags.append("Missing external height: " + external_height)
    assert triangles["SAGE"] == triangles["CLAY"], "Mirrored house budgets differ"
    alignment = json.loads((KIT / "alignment_houses_v2.json").read_text())
    owned = {"SAGE_HOUSE", "CLAY_HOUSE", "SAGE_HOUSE_PROPS", "CLAY_HOUSE_PROPS"}
    house_mismatches = [m for m in alignment["items"] if m["structure"] in owned]
    assert not house_mismatches, "House art differs from collision"
    result = {
        "export": "houses.glb", "bytes": len(raw), "triangles": triangles,
        "meshes": len(data["meshes"]), "materials": len(used_materials),
        "all_meshes_single_material": True, "all_meshes_uv_and_color_0": True,
        "identity_nodes_y_up_design_frame": True, "house_alignment_mismatches": 0,
        "alignment_rays": alignment["rays"], "flags": flags,
        "material_names": [m["name"] for m in used_materials],
    }
    (KIT / "houses_validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
