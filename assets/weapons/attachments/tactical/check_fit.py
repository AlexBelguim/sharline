"""Round-2 fit check (headless Blender): every ATT tactical part on every real gun it fits, placed on the gun .glb's
socket node (engine truth). Reports, per part x gun:
  - BVH triangle-pair overlaps between the part and each gun mesh,
  - gun vertices inside the part (depth = distance to the part surface) -- catches a rail corner buried in a clamp,
  - part vertices inside the gun (depth),
  - min gap from the part to each rail mesh.
  blender -b --factory-startup --python-exit-code 1 -P check_fit.py -- [out.json]
  Default: _work/validation/fit_check.json. Historical review reports are preserved.
"""
import json, os, sys
import hashlib
from pathlib import Path
import bpy, bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
HERE = str(Path(__file__).resolve().parent)
WEAP = str(Path(HERE).parents[1])
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else os.path.join(HERE, "_work", "validation", "fit_check.json")
os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
GUNS = {"MAKO": os.path.join(WEAP, "ar7_mako", "mako_default.glb"),
        "WARDEN": os.path.join(WEAP, "vk50_warden", "warden_default.glb")}
FITS = {"grip_vertical": [("MAKO", "Under")], "grip_angled": [("MAKO", "Under")], "grip_stub": [("MAKO", "Under")],
        "ugl_launcher": [("MAKO", "Under")], "bipod": [("WARDEN", "Under")],
        "laser_R": [("MAKO", "Side_R"), ("WARDEN", "Side_R")], "laser_L": [("MAKO", "Side_L"), ("WARDEN", "Side_L")],
        "flashlight_R": [("MAKO", "Side_R"), ("WARDEN", "Side_R")],
        "flashlight_L": [("MAKO", "Side_L"), ("WARDEN", "Side_L")], "shield_front": [("MAKO", "Shield")]}


def imp(p):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=p)
    return [o for o in bpy.data.objects if o not in before]


def world_bm(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    return bm


def tree(o):
    bm = world_bm(o)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


DIRS = [Vector((0.0123, 0.0456, 1.0)).normalized(), Vector((0.71, -0.031, 0.05)).normalized(),
        Vector((-0.03, 0.97, -0.21)).normalized()]


def inside(t, p):
    votes = 0
    for d in DIRS:
        hits, q = 0, p.copy()
        for _ in range(64):
            h = t.ray_cast(q, d)
            if h[0] is None:
                break
            hits += 1
            q = h[0] + d * 1e-6
        votes += hits % 2
    return votes >= 2


def bbox(objs):
    ws = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    return Vector([min(w[i] for w in ws) for i in range(3)]), Vector([max(w[i] for w in ws) for i in range(3)])


res = {"inputs_sha256": {str(Path(path).relative_to(Path(WEAP))): hashlib.sha256(Path(path).read_bytes()).hexdigest()
                        for path in list(GUNS.values()) + [os.path.join(HERE, f"ATT_{pid}.glb") for pid in FITS]}}
for pid, fits in FITS.items():
    for gun, slot in fits:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        go = imp(GUNS[gun])
        bpy.context.view_layer.update()
        sock = next(o for o in go if o.name == f"{gun}_SOCKET_{slot}").matrix_world.translation.copy()
        po = imp(os.path.join(HERE, f"ATT_{pid}.glb"))
        root = next(o for o in po if o.name == f"ATT_{pid}")
        root.location = sock
        bpy.context.view_layer.update()
        pm = [o for o in po if o.type == "MESH"]
        gm = [o for o in go if o.type == "MESH"]
        pmn, pmx = bbox(pm)
        r = {"socket": [round(c, 5) for c in sock], "overlaps": {}, "gun_verts_in_part": {}, "part_verts_in_gun": {},
             "rail_gap_mm": {}}
        ptrees = {o.name: tree(o) for o in pm}
        for g in gm:
            gmn, gmx = bbox([g])
            if any(gmx[i] < pmn[i] - 0.01 or gmn[i] > pmx[i] + 0.01 for i in range(3)):
                continue
            gt = tree(g)
            gws = [g.matrix_world @ v.co for v in g.data.vertices]
            gws = [w for w in gws if all(pmn[i] - 1e-4 <= w[i] <= pmx[i] + 1e-4 for i in range(3))]
            for o in pm:
                pt = ptrees[o.name]
                ov = pt.overlap(gt)
                if ov:
                    r["overlaps"][f"{o.name} x {g.name}"] = len(ov)
                deep = []
                for w in gws:
                    if inside(pt, w):
                        deep.append(pt.find_nearest(w)[3])
                if deep:
                    r["gun_verts_in_part"][f"{g.name} in {o.name}"] = {"n": len(deep),
                                                                     "max_mm": round(max(deep) * 1000, 3)}
                deep2 = []
                for v in o.data.vertices:
                    w = o.matrix_world @ v.co
                    if all(gmn[i] <= w[i] <= gmx[i] for i in range(3)) and inside(gt, w):
                        deep2.append(gt.find_nearest(w)[3])
                if deep2:
                    r["part_verts_in_gun"][f"{o.name} in {g.name}"] = {"n": len(deep2),
                                                                     "max_mm": round(max(deep2) * 1000, 3)}
            if "Rail" in g.name:
                gap = 1e9
                for o in pm:
                    pt = ptrees[o.name]
                    for w in gws[::1]:
                        n = pt.find_nearest(w)
                        if n[0] is not None:
                            gap = min(gap, n[3])
                if gap < 1e8:
                    r["rail_gap_mm"][g.name] = round(gap * 1000, 3)
        # touching faces (clamp contact face on the rail face) register as BVH overlaps and depth-0 "inside" vertices;
        # only a real penetration (> 0.02 mm) fails
        depths = [d["max_mm"] for d in list(r["gun_verts_in_part"].values()) + list(r["part_verts_in_gun"].values())]
        r["max_penetration_mm"] = max(depths, default=0.0)
        r["clean"] = r["max_penetration_mm"] <= 0.02
        res[f"{pid}@{gun}"] = r
        print("FIT", pid, gun, "clean" if r["clean"] else "HIT", "pen_mm", r["max_penetration_mm"], json.dumps({k: r[k] for k in
              ("overlaps", "gun_verts_in_part", "part_verts_in_gun", "rail_gap_mm")}))
# ---------------------------------------------------------------- loadouts: parts against each other and the gun
LOADOUTS = {"mako_A": ("MAKO", {"shield_front": "Shield", "laser_R": "Side_R", "flashlight_L": "Side_L",
                                "ugl_launcher": "Under"}),
            "mako_B": ("MAKO", {"shield_front": "Shield", "flashlight_R": "Side_R", "laser_L": "Side_L",
                                "grip_angled": "Under"}),
            "mako_C": ("MAKO", {"shield_front": "Shield", "flashlight_R": "Side_R", "flashlight_L": "Side_L",
                                "grip_vertical": "Under"}),
            "warden_A": ("WARDEN", {"bipod": "Under", "laser_R": "Side_R", "flashlight_L": "Side_L"})}


def min_dist(objs_a, objs_b):
    """Approximate minimum distance between two object sets: vertices of each against the other's surface."""
    ta = [tree(o) for o in objs_a]
    tb = [tree(o) for o in objs_b]
    best = 1e9
    for src, dst in ((objs_a, tb), (objs_b, ta)):
        for o in src:
            for v in o.data.vertices:
                w = o.matrix_world @ v.co
                for t in dst:
                    n = t.find_nearest(w, best)
                    if n[0] is not None:
                        best = min(best, n[3])
    return best


lo_res = {}
for name, (gun, parts) in LOADOUTS.items():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    go = imp(GUNS[gun])
    bpy.context.view_layer.update()
    socks = {o.name.split("_SOCKET_")[1]: o.matrix_world.translation.copy() for o in go if "_SOCKET_" in o.name}
    gun_body = [o for o in go if o.type == "MESH" and "Rail" not in o.name]
    pm = {}
    for pid, slot in parts.items():
        po = imp(os.path.join(HERE, f"ATT_{pid}.glb"))
        next(o for o in po if o.name == f"ATT_{pid}").location = socks[slot]
        pm[pid] = [o for o in po if o.type == "MESH"]
    bpy.context.view_layer.update()
    r = {}
    ids = list(pm)
    for i, a in enumerate(ids):
        r[f"{a} vs gun (no rails)"] = round(min_dist(pm[a], gun_body) * 1000, 2)
        for b in ids[i + 1:]:
            r[f"{a} vs {b}"] = round(min_dist(pm[a], pm[b]) * 1000, 2)
    lo_res[name] = r
    print("LOADOUT", name, json.dumps(r))
res["loadout_min_gaps_mm"] = lo_res
with open(OUT, "w") as fh:
    json.dump(res, fh, indent=1)
print("FITCHECK DONE", OUT)
if any(not result["clean"] for key, result in res.items() if "@" in key):
    raise RuntimeError("Tactical fit validation failed; see " + OUT)
