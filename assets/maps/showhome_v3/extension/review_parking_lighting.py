"""Independent, read-only parking lighting/clearance/route export review.

Run with normal Python. This script never edits the builder, kit or user RONs.
Optional --output writes a separate review JSON selected by the caller.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np


def glb_json(path):
    raw = Path(path).read_bytes()
    magic, version, size = struct.unpack_from("<III", raw)
    assert magic == 0x46546c67 and version == 2 and size == len(raw)
    offset = 12
    while offset + 8 <= len(raw):
        count, kind = struct.unpack_from("<II", raw, offset)
        if kind == 0x4e4f534a:
            return json.loads(raw[offset + 8:offset + 8 + count])
        offset += count + 8
    raise ValueError("GLB JSON chunk missing")


def _inside(planes, p, epsilon=.002):
    return np.all(planes[:, :3] @ p - planes[:, 3] <= epsilon)


def routes(report):
    paths = []
    for core in report["access_cores"]:
        path = list(core["route_samples"])
        a, b = np.array(path[-1]), np.array(core["gf_exit_sample"])
        path.extend((a + (b - a) * k / 15).tolist() for k in range(16))
        paths.append((core["id"] + "_stairs", path))
        paths.append((core["id"] + "_lift", core["lift_route_samples"]))
    paths.append(("vehicle_ramp_pedestrian", report["vehicle_ramp"]["route_samples"]))
    return paths


def check_routes(report, rows):
    prepared = [(row, np.array(row["planes"]), np.array(row["aabb"]["min"]), np.array(row["aabb"]["max"])) for row in rows]
    radius, half = .32, np.array([.32, .32, .89])
    samples, failures = 0, []
    for label, path in routes(report):
        for point in path:
            foot = np.array(point, dtype=float)
            nearby = [(row, planes, lo, hi) for row, planes, lo, hi in prepared
                      if np.all(foot[:2] + radius >= lo[:2]) and np.all(foot[:2] - radius <= hi[:2])]
            support = []
            for row, planes, lo, hi in nearby:
                if not row.get("walkable", True):
                    continue
                for nx, ny, nz, d in planes:
                    if nz < .7:
                        continue
                    top = (d - nx * foot[0] - ny * foot[1]) / nz
                    if abs(top - foot[2]) <= .06 and _inside(planes, np.array([foot[0], foot[1], top])):
                        support.append(top)
            if not support:
                failures.append(dict(route=label, point=point, problem="no floor support"))
                continue
            standing = max(support)
            for row, planes, lo, hi in nearby:
                if not row.get("walkable", True):
                    continue
                for nx, ny, nz, d in planes:
                    if nz < .7:
                        continue
                    corner = (d - nx * foot[0] - ny * foot[1] + abs(nx) * radius + abs(ny) * radius) / nz
                    if foot[2] - .03 <= corner <= foot[2] + .35:
                        standing = max(standing, corner)
            centre = foot.copy()
            centre[2] = standing + .91
            for row, planes, lo, hi in nearby:
                if np.any(centre + half < lo) or np.any(centre - half > hi):
                    continue
                separation = planes[:, :3] @ centre - planes[:, 3] - np.abs(planes[:, :3]) @ half
                if np.all(separation < -.0001):
                    failures.append(dict(route=label, point=point, problem="standing box blocked", volume=row["name"]))
            samples += 1
    return dict(passed=not failures, supported_samples=samples, routes=len(routes(report)), radius_m=radius,
                height_m=1.8, failures=failures[:25])


def review(folder, expected_lights=13):
    folder = Path(folder)
    j = glb_json(folder / "extension.glb")
    rows = json.loads((folder / "collision.json").read_text())["volumes"]
    parking = json.loads((folder / "parking_report.json").read_text())
    lights = j.get("extensions", {}).get("KHR_lights_punctual", {}).get("lights", [])
    references = [node["extensions"]["KHR_lights_punctual"]["light"] for node in j["nodes"] if "KHR_lights_punctual" in node.get("extensions", {})]
    fixtures = [row for row in rows if "ParkingLightHousing" in row["name"] or "ParkingLightLens" in row["name"]]
    clearance = min(row["aabb"]["min"][2] - parking["floor_z_m"] for row in fixtures)
    route_result = check_routes(parking, rows)
    failures = []
    if len(lights) != expected_lights or len(references) != expected_lights:
        failures.append(f"Expected {expected_lights} KHR punctual lights and nodes, found {len(lights)}/{len(references)}")
    if any(index < 0 or index >= len(lights) for index in references):
        failures.append("Punctual-light node index outside extension light table")
    if any(light.get("type") != "point" or not np.isfinite(light.get("intensity", 1)) or light.get("intensity", 1) <= 0 for light in lights):
        failures.append("Parking lights must be finite positive-intensity point lights")
    if clearance < 2.7:
        failures.append(f"Minimum fixture clearance {clearance:.4f}m is below 2.7m")
    if len(fixtures) != 2 * expected_lights:
        failures.append(f"Expected {2 * expected_lights} housing/lens collision volumes, found {len(fixtures)}")
    if not route_result["passed"] or route_result["supported_samples"] != 757:
        failures.append("Basement support/headroom routes did not pass all 757 samples")
    return dict(passed=not failures, failures=failures, punctual_light_count=len(lights), light_node_count=len(references),
                extension_used="KHR_lights_punctual" in j.get("extensionsUsed", []), fixture_collision_volumes=len(fixtures),
                minimum_fixture_clearance_m=clearance, routes=route_result,
                inputs_sha256={name:hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in ("extension.glb", "collision.json", "parking_report.json")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = review(args.folder)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print(json.dumps({k:v for k,v in result.items() if k != "inputs_sha256"}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
