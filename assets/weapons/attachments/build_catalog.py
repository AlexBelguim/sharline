"""Merge the optics and tactical catalogs into the shared asset handoff."""

import argparse
import json
import re
import struct
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUTPUT = HERE.parent / "attachments.json"
SOURCES = ((HERE / "optics/catalog.json", "optics"),
           (HERE / "tactical/catalog.json", "parts"))
WEAPON_IDS = {"MAKO": "ar7_mako", "WARDEN": "vk50_warden", "SKINK": "sk9_skink"}
GAME_DATA = ROOT / "game/assets/data/attachments.ron"
GUN_EXPORTS = {
    "MAKO": ROOT / "assets/weapons/ar7_mako/mako_default.glb",
    "WARDEN": ROOT / "assets/weapons/vk50_warden/warden_default.glb",
}


def relative_file(value, catalog):
    """Accept either local catalog filenames or repository-relative paths."""
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"{catalog.name}: expected a relative asset path: {value}")
    base = ROOT if path.parts[0] == "assets" else catalog.parent
    resolved = (base / path).resolve()
    try:
        relative = resolved.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"Asset path leaves the repository: {value}") from exc
    if not resolved.is_file():
        raise ValueError(f"Missing export: {relative.as_posix()}")
    return relative.as_posix()


def read_glb(path):
    data = path.read_bytes()
    if len(data) < 20:
        raise ValueError(f"{path.name}: truncated GLB")
    magic, version, length, json_length, chunk_type = struct.unpack_from("<5I", data)
    if (magic != 0x46546C67 or version != 2 or length != len(data)
            or chunk_type != 0x4E4F534A or 20 + json_length > len(data)):
        raise ValueError(f"{path.name}: invalid GLB header")
    return json.loads(data[20:20 + json_length])


def check_fit_metadata(catalog):
    """Catch fit catalogs left over from an earlier gun proportion revision."""
    for prefix, sockets in catalog["test_sockets"].items():
        document = read_glb(GUN_EXPORTS[prefix])
        nodes = document["nodes"]
        root = next((node for node in nodes if node.get("name") == prefix + "_Root"), None)
        if root is None:
            raise ValueError(f"{prefix}: gun root is missing from the export")
        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        if (root.get("translation", [0, 0, 0]) != [0, 0, 0]
                or root.get("rotation", [0, 0, 0, 1]) != [0, 0, 0, 1]
                or root.get("scale", [1, 1, 1]) != [1, 1, 1]
                or root.get("matrix", identity) != identity):
            raise ValueError(f"{prefix}: gun root must be at the mount-space origin")
        children = {nodes[index].get("name"): nodes[index] for index in root["children"]}
        for socket, expected in sockets.items():
            name = prefix + "_SOCKET_" + socket
            position = children[name].get("translation", [0, 0, 0])
            # glTF (x, y, z) = Blender (x, z, -y).
            actual = [position[0], -position[2], position[1]]
            if len(expected) != 3 or any(abs(a - b) > 1e-6 for a, b in zip(actual, expected)):
                raise ValueError(f"Stale tactical fit metadata for {name}; rebuild tactical assets")


def check_glb(entry):
    """Reject catalog rows whose root or triangle count differs from the export."""
    document = read_glb(ROOT / entry["file"])
    if entry["root_node"] not in {node.get("name") for node in document.get("nodes", [])}:
        raise ValueError(f"{entry['id']}: root node missing from GLB")
    triangles = 0
    for mesh in document.get("meshes", []):
        for primitive in mesh["primitives"]:
            if primitive.get("mode", 4) != 4:
                raise ValueError(f"{entry['id']}: export contains non-triangle geometry")
            accessor = primitive.get("indices", primitive["attributes"]["POSITION"])
            count = document["accessors"][accessor]["count"]
            if count % 3:
                raise ValueError(f"{entry['id']}: incomplete triangle")
            triangles += count // 3
    if triangles != entry["tris"]:
        raise ValueError(f"{entry['id']}: catalog has {entry['tris']} tris; GLB has {triangles}")


def build_catalog():
    # Read the id/fits fields used by this data file; this is not a general RON parser.
    game_text = re.sub(r"//[^\n]*", "", GAME_DATA.read_text(encoding="utf-8"))
    game_fits = {match[0]: re.findall(r'"([^\"]+)"', match[1]) for match in re.findall(
        r'\(\s*id:\s*"([^\"]+)"\s*,\s*cat:\s*\w+\s*,\s*fits:\s*\[([^\]]*)\]', game_text)}
    entries = []
    seen = set()
    for source, key in SOURCES:
        catalog = json.loads(source.read_text(encoding="utf-8"))
        if key == "parts":
            check_fit_metadata(catalog)
        for row in catalog[key]:
            entry = dict(row)
            if entry["id"] in seen:
                raise ValueError(f"Duplicate asset ID: {entry['id']}")
            seen.add(entry["id"])
            if not entry["category"] or not entry["sockets_accepted"] or not entry["compatible_weapons"]:
                raise ValueError(f"{entry['id']}: incomplete mount/compatibility metadata")
            entry["source_catalog"] = source.relative_to(ROOT).as_posix()
            entry["file"] = relative_file(entry["file"], source)
            entry["file_fbx"] = relative_file(entry.pop("fbx", None) or entry["file_fbx"], source)
            entry.setdefault("root_node", entry["id"])
            entry.setdefault("game_attachment_id", entry["id"])
            game_id = entry["game_attachment_id"]
            if game_id in game_fits:
                entry["compatible_weapon_ids"] = game_fits[game_id]
                entry["game_data_status"] = "registered"
            elif game_id == "optic_projector":
                entry["compatible_weapon_ids"] = [WEAPON_IDS[w] for w in entry["compatible_weapons"]]
                entry["game_data_status"] = "pending"
            else:
                raise ValueError(f"{entry['id']}: game attachment id not found in attachments.ron")
            entry["tested_weapon_prefixes"] = [w for w in entry["compatible_weapons"] if w != "SKINK"]
            check_glb(entry)
            entries.append(entry)
    return {
        "schema_version": 1,
        "prefix": "ATT",
        "units": "metres; Blender Z up, muzzle -Y, shooter's right -X",
        "path_base": "repository root",
        "sources": [source.relative_to(ROOT).as_posix() for source, _ in SOURCES],
        "game_data": GAME_DATA.relative_to(ROOT).as_posix(),
        "attachments": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate exports and fail if the shared catalog is stale")
    args = parser.parse_args()
    try:
        catalog = build_catalog()
        content = json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != content:
                raise ValueError("Shared catalog is missing or stale; run build_catalog.py")
        else:
            OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    except (OSError, ValueError, KeyError, struct.error) as exc:
        parser.exit(1, f"Catalog validation failed: {exc}\n")
    print(f"{'Checked' if args.check else 'Wrote'} {OUTPUT}: {len(catalog['attachments'])} attachment exports")


if __name__ == "__main__":
    main()
