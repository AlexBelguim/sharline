"""ATT tactical / underbarrel / shield attachment set -- re-runnable build (headless Blender 5.2).

  blender -b --factory-startup --python-exit-code 1 -P build_tactical.py -- [--out DIR]

Builds everything from scratch. Every part lives in its own collection and is modelled in MOUNT SPACE
(art/WEAPON_MODULAR_SPEC.md rail standard):
  under-mounted (grips, UGL, bipod): origin = centre of the clamp contact on the rail BOTTOM surface, part hangs -Z
  top-mounted   (shield):            origin = centre of the clamp contact on the rail TOP surface
  side-mounted  (laser, flashlight): origin = centre of the clamp contact on the rail OUTER face; _R sticks out
                                     toward the shooter's RIGHT (-X); _L is built as an exact X-mirror.
Muzzle -> -Y, Z up. Moving parts are child objects with their origin on the hinge / pivot.
Also builds Mako / Warden proxies (from the real socket files) for test fitting (scene "TestFit").
Writes tactical.blend, ATT_<part>.glb/.fbx, catalog.json and textures/ next to this file.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
PROJECT = Path(HERE).parents[3]
WEAPONS = PROJECT / "assets" / "weapons"
sys.path.insert(0, str(PROJECT / "tools"))
sys.path.insert(0, HERE)

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import blender_common as bc  # noqa: E402
import att_lib as L  # noqa: E402

M = {}
STATS = {}
BUDGET = {"grip_vertical": (500, 1500), "grip_angled": (500, 1500), "grip_stub": (500, 1500),
          "ugl_launcher": (3000, 6000), "bipod": (1500, 4000), "shield_front": (1500, 4000),
          "laser_R": (0, 1500), "laser_L": (0, 1500), "flashlight_R": (0, 1500), "flashlight_L": (0, 1500)}
MAKO_SOCKETS = str(WEAPONS / "ar7_mako" / "sockets.json")
WARDEN_SOCKETS = str(WEAPONS / "vk50_warden" / "sockets.json")
MAKO_GLB = str(WEAPONS / "ar7_mako" / "mako_default.glb")
WARDEN_GLB = str(WEAPONS / "vk50_warden" / "warden_default.glb")
GLASS_RGB = (0.020, 0.045, 0.080)
GLASS_ALPHA = 0.38
GLASS_ROUGH = 0.08
# ids exactly as in game/assets/data/attachments.ron (`fits`), which is the gameplay source of truth
GAME_FITS = {"grip_vertical": ["ar7_mako"], "grip_angled": ["ar7_mako"], "grip_stub": ["ar7_mako"],
             "ugl_launcher": ["ar7_mako"], "bipod": ["vk50_warden"],
             "laser": ["ar7_mako", "vk50_warden", "sk9_skink"], "flashlight": ["ar7_mako", "vk50_warden", "sk9_skink"],
             "shield_front": ["ar7_mako"]}
GAME_PREFIX = {"ar7_mako": "MAKO", "vk50_warden": "WARDEN", "sk9_skink": "SKINK"}
FAILED = []


# ================================================================================================ materials
def make_materials():
    G = L.gl_material
    M["graphite"] = G("M_ATT_Graphite", (0.030, 0.033, 0.040), rough=0.52, metal=0.20, tex="worn_paint", mix=0.50,
                      tile_m=0.40)
    M["gunmetal"] = G("M_ATT_Gunmetal", (0.11, 0.115, 0.12), rough=0.35, metal=0.85, tex="brushed_metal",
                      mix=0.30, tile_m=0.25)
    M["bone"] = G("M_ATT_Bone", (0.55, 0.52, 0.46), rough=0.60, metal=0.0, tex="worn_paint", mix=0.30, tile_m=0.40)
    # review v2: stipple pulled back to the bone hue (the stipple texture gives the contrast, no brown-taupe cast)
    M["bone_grip"] = G("M_ATT_BoneStipple", (0.47, 0.45, 0.40), rough=0.78, metal=0.0, tex="polymer_stipple",
                       mix=0.60, tile_m=0.10)
    M["rubber"] = G("M_ATT_Rubber", (0.022, 0.024, 0.028), rough=0.88, metal=0.0)
    M["dark"] = G("M_ATT_Bore", (0.012, 0.012, 0.014), rough=0.65, metal=0.3)
    # review v2: a DARK blue tint. A light base colour at alpha 0.4 is a bright lit veil over everything seen through
    # the viewport (black read as light blue, ~1.15:1 contrast in daylight); a dark tint keeps the scene readable.
    M["glass"] = G("M_ATT_ShieldGlass", GLASS_RGB, rough=GLASS_ROUGH, metal=0.0, alpha=GLASS_ALPHA)
    M["laser"] = G("M_ATT_LaserEmitter", (0.35, 0.010, 0.008), rough=0.25, emission=(1.0, 0.015, 0.008),
                   emission_strength=1.2)
    # review v2: near-neutral dark glass, so the red emitter dot is the part's only accent (was saturated plum)
    M["ir"] = G("M_ATT_IRWindow", (0.015, 0.017, 0.022), rough=0.06, metal=0.0, coat=1.0)
    M["lens"] = G("M_ATT_LightLens", (0.20, 0.22, 0.25), rough=0.04, metal=0.0, emission=(1.0, 0.93, 0.80),
                  emission_strength=0.20)
    M["led"] = G("M_ATT_LightLED", (0.90, 0.88, 0.82), rough=0.30, metal=0.0, emission=(1.0, 0.94, 0.82),
                 emission_strength=1.5)
    M["proxy"] = bc.material("_M_Proxy", (0.17, 0.18, 0.20), rough=0.65, metal=0.0)
    M["proxy_dark"] = bc.material("_M_ProxyDark", (0.07, 0.075, 0.085), rough=0.5, metal=0.4)
    M["proxy_bone"] = bc.material("_M_ProxyBone", (0.40, 0.38, 0.34), rough=0.6, metal=0.0)
    M["ground"] = bc.material("_M_Ground", (0.035, 0.037, 0.042), rough=0.9)


# ================================================================================================ helpers
def fin(ob, w, segs=1, angle=30, smooth_angle=30, convex=False):
    return L.finish(ob, w, segs, angle, smooth_angle, convex_only=convex)


def clamp(name, mount, y0, y1, W=0.0155, H=0.008, D=0.0083, slots=(), slot_w=0.0045, mat=None):
    """Rail clamp (U channel hooking the dovetail) + optional diagonal lightening slots on both jaw faces
    (slots = list of t positions). Returns the unfinished object."""
    f = L.mount_map(mount)
    ob = L.prism_f(name, L.clamp_profile(W, H, D), f, y0, y1, mat=mat or M["graphite"])
    if slots:
        cs = []
        v0, v1 = -D + 0.0030, H - 0.0022
        sk = 0.55 * (v1 - v0)
        for t in slots:
            pts = [(t, v1), (t + slot_w, v1), (t + slot_w + sk, v0), (t + sk, v0)]
            for s in (1, -1):
                g = (lambda a, b, u, s=s: f(s * u, b, a))
                cs.append(L.prism_f("_sl", pts, g, W - 0.0013, W + 0.004))
        L.cut(ob, cs)
    return ob


def clamp_bolts(mount, ys, W, v=-0.0042, lever_side=None, lever_len=0.030, y_lever=0.0):
    """Cross-bolt heads (hex) and nuts on the clamp jaws + optional QD throw lever on side +1/-1 (u axis)."""
    f = L.mount_map(mount)
    parts = []
    for y in ys:
        parts.append(L.cyl("_bh", 0.0031, f(W - 0.0006, v, y), f(W + 0.0020, v, y), verts=6, mat=M["gunmetal"]))
        parts.append(L.cyl("_bn", 0.0027, f(-W + 0.0006, v, y), f(-W - 0.0016, v, y), verts=8,
                           mat=M["gunmetal"]))
    for p in parts:
        if p.name.startswith("_bh"):
            fin(p, 0.0004, 1, smooth_angle=40)          # hex head: every corner chamfered
        else:
            round_fin(p, 0.0004)                       # round nut: bevel the rims only, smooth sides
    if lever_side:
        s = lever_side
        u0, u1 = s * (W - 0.0004), s * (W + 0.0032)
        pts = [(y_lever - lever_len / 2, -0.0068), (y_lever + lever_len / 2 - 0.006, -0.0068),
               (y_lever + lever_len / 2, -0.0045), (y_lever + lever_len / 2, -0.0010),
               (y_lever - lever_len / 2 + 0.004, -0.0016), (y_lever - lever_len / 2, -0.0040)]
        bmv = bmesh.new()
        lo = [bmv.verts.new(f(u0, vv, yy)) for yy, vv in pts]
        hi = [bmv.verts.new(f(u1, vv, yy)) for yy, vv in pts]
        bmv.faces.new(lo)
        bmv.faces.new(hi[::-1])
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            bmv.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bmesh.ops.recalc_face_normals(bmv, faces=bmv.faces)
        lev = L.new_obj("_lever", bmv, mat=M["gunmetal"])
        fin(lev, 0.0007, 1)
        boss = L.cyl("_boss", 0.0040, f(s * (W - 0.0004), -0.0040, y_lever + lever_len / 2 - 0.004),
                     f(s * (W + 0.0040), -0.0040, y_lever + lever_len / 2 - 0.004), verts=10, mat=M["gunmetal"])
        round_fin(boss, 0.0005)
        parts += [lev, boss]
    return parts


def screws(spots, r=0.0029, h=0.0011, verts=8, mat=None):
    """Round screw heads: spots = [(point_on_surface, outward_normal)] in R space."""
    out = []
    for p, n in spots:
        p, n = Vector(p), Vector(n).normalized()
        s = L.cyl("_scr", r, p - n * 0.0008, p + n * h, verts=verts, mat=mat or M["gunmetal"])
        round_fin(s, 0.0004)
        out.append(s)
    return out


def round_fin(ob, w):
    """Round parts (pins, screw heads, knobs): bevel only the cap rims (90 deg), keep the faceted sides smooth-shaded.
    Rounder look than chamfering every side facet, and about a third fewer triangles (pays for the UGL tube steps)."""
    return L.finish(ob, w, 1, angle=55, smooth_angle=55)


def both_sides(x, y, z, sx=(1, -1)):
    return [((s * x, y, z), (s, 0, 0)) for s in sx]


def prop_val(v):
    """Custom property -> JSON-safe value."""
    return v.to_list() if hasattr(v, "to_list") else v


def quat_gltf(axis_blender, deg):
    """Quaternion [x, y, z, w] in glTF axes (Y up) for a rotation of `deg` about a Blender-space axis."""
    ax = Vector(axis_blender).normalized()
    g = Vector((ax.x, ax.z, -ax.y))
    h = math.radians(deg) / 2
    return [round(v, 6) for v in (g.x * math.sin(h), g.y * math.sin(h), g.z * math.sin(h), math.cos(h))]


def register(pid, root, objs, extra=None):
    meshes = [o for o in objs if o.type == "MESH"]
    for o in meshes:
        L.clean_slots(o)
        L.tri_clean(o)          # explicit BEAUTY triangles (normals kept): what the exporters write
    total = sum(L.tris(o) for o in meshes)
    checks = {o.name: L.check_mesh(o) for o in meshes}
    STATS[pid] = {"root": root.name, "objects": [o.name for o in objs], "tris": total, "checks": checks}
    if extra:
        STATS[pid].update(extra)
    lo, hi = BUDGET.get(pid, (0, 1e9))
    flag = "OK" if lo <= total <= hi else "OVER" if total > hi else "UNDER"
    print(f"[{pid}] tris={total} budget={lo}-{hi} {flag}  objects={len(objs)}")
    if flag != "OK":
        FAILED.append(f"{pid}: {total} tris outside {lo}-{hi}")
    for n, c in checks.items():
        if c["failed"]:
            print(f"   !! {n}: {c}")
            FAILED.append(f"{n}: {c}")


# ================================================================================================ foregrips
def grip_frame_body(name, outline, window, half_w, grip_faces):
    """Bone skeleton body: side profile `outline` (y, z) extruded across X, with a through `window`.
    grip_faces(c, n) -> True marks hand-contact faces (stipple)."""
    body = L.prism(name, outline, "X", -half_w, half_w, mat=M["bone"])
    if window:
        L.cut(body, L.prism("_win", window, "X", -0.05, 0.05))
    k = L.add_mat(body, M["bone_grip"])
    L.set_mat_by(body, k, grip_faces)
    return body


def build_grip_vertical():
    pid = "grip_vertical"
    P = "ATT_" + pid
    col = bc.collection(P)
    cl = clamp(P + "_c", "under", -0.034, 0.034, W=0.0155, H=0.0110, slots=[-0.020, -0.008])
    fin(cl, 0.0010, 1, convex=True)
    bolts = clamp_bolts("under", [0.020], 0.0155)
    # side profile: front column (slight forward rake) + rear diagonal brace with palm grooves, triangular window
    E, F = (-0.0060, -0.0950), (0.0335, -0.0220)
    outline = ([(-0.0335, -0.0090), (-0.0370, -0.0960), (-0.0330, -0.1010), (-0.0120, -0.1010), E] +
               L.notch_edge(E, F, [0.30, 0.47, 0.64], 0.0022, half=0.0030, side=-1) + [F, (0.0335, -0.0090)])
    window = L.chamfer_poly([(-0.0205, -0.0205), (0.0215, -0.0205), (-0.0062, -0.0720), (-0.0205, -0.0800)],
                            [0.0035, 0.0035, 0.0050, 0.0040])
    d = Vector((F[0] - E[0], F[1] - E[1])).normalized()
    nb = Vector((d.y, -d.x))                       # outward normal of the rear brace (rear-down)

    def grip_faces(c, n):
        front = n.y < -0.85 and c.z < -0.020
        rear = (n.y * nb.x + n.z * nb.y) > 0.85 and abs(n.x) < 0.3
        return front or rear
    body = grip_frame_body(P + "_b", outline, window, 0.0150, grip_faces)
    fin(body, 0.0026, 2, smooth_angle=35)
    cap = L.prism(P + "_cap", [(-0.0392, -0.0965), (-0.0052, -0.0965), (-0.0040, -0.1005), (-0.0072, -0.1080),
                               (-0.0352, -0.1080), (-0.0398, -0.1030)], "X", -0.0162, 0.0162, mat=M["graphite"])
    fin(cap, 0.0016, 1)
    scr = screws(both_sides(0.0150, -0.0275, -0.0870))
    root = L.merge([cl, body, cap] + bolts + scr, P, col=col)
    sock = L.socket(P + "_SOCKET_LeftHand", (0.0, -0.0220, -0.0580), root, col)
    objs = [root, sock]
    register(pid, root, objs, {"category": "foregrip", "mount": "under"})
    return objs


def build_grip_angled():
    pid = "grip_angled"
    P = "ATT_" + pid
    col = bc.collection(P)
    cl = clamp(P + "_c", "under", -0.052, 0.050, W=0.0155, H=0.0105, slots=[0.002, 0.016])
    fin(cl, 0.0010, 1, convex=True)
    bolts = clamp_bolts("under", [0.036], 0.0155)
    D_, E = (-0.0380, -0.0590), (0.0480, -0.0160)
    outline = ([(-0.0505, -0.0090), (-0.0530, -0.0460), (-0.0480, -0.0570), D_] +
               L.notch_edge(D_, E, [0.36, 0.52, 0.68], 0.0020, half=0.0030, side=-1) + [E, (0.0500, -0.0090)])
    window = L.chamfer_poly([(-0.0395, -0.0185), (0.0200, -0.0185), (-0.0395, -0.0480)], [0.0035, 0.0045, 0.0040])
    d = Vector((E[0] - D_[0], E[1] - D_[1])).normalized()
    nb = Vector((d.y, -d.x))

    def grip_faces(c, n):
        return (n.y * nb.x + n.z * nb.y) > 0.85 and abs(n.x) < 0.3
    body = grip_frame_body(P + "_b", outline, window, 0.0145, grip_faces)
    fin(body, 0.0026, 2, smooth_angle=35)
    pad = L.prism(P + "_pad", [(-0.0545, -0.0430), (-0.0430, -0.0470), (-0.0365, -0.0560), (-0.0400, -0.0620),
                               (-0.0480, -0.0615), (-0.0545, -0.0520)], "X", -0.0156, 0.0156, mat=M["graphite"])
    fin(pad, 0.0015, 1)
    scr = screws(both_sides(0.0145, -0.0450, -0.0330))
    root = L.merge([cl, body, pad] + bolts + scr, P, col=col)
    sock = L.socket(P + "_SOCKET_LeftHand", (0.0, -0.0050, -0.0300), root, col)
    objs = [root, sock]
    register(pid, root, objs, {"category": "foregrip", "mount": "under"})
    return objs


def build_grip_stub():
    pid = "grip_stub"
    P = "ATT_" + pid
    col = bc.collection(P)
    cl = clamp(P + "_c", "under", -0.024, 0.024, W=0.0155, H=0.0105, slots=[-0.006])
    fin(cl, 0.0010, 1, convex=True)
    bolts = clamp_bolts("under", [0.014], 0.0155)
    outline = [(-0.0235, -0.0090), (-0.0258, -0.0300), (-0.0225, -0.0365), (-0.0120, -0.0365), (0.0235, -0.0150),
               (0.0235, -0.0090)]
    body = L.prism(P + "_b", outline, "X", -0.0145, 0.0145, mat=M["bone"])
    tri_ = L.chamfer_poly([(-0.0180, -0.0150), (0.0080, -0.0150), (-0.0180, -0.0295)], 0.0020)
    L.cut(body, [L.prism("_tr", tri_, "X", s * 0.0130, s * 0.03) for s in (1, -1)])
    k = L.add_mat(body, M["bone_grip"])
    L.set_mat_by(body, k, lambda c, n: abs(n.x) > 0.9 and abs(c.x) < 0.0135)
    fin(body, 0.0024, 2, smooth_angle=35)
    root = L.merge([cl, body] + bolts, P, col=col)
    # the support hand rides the handguard just behind the stop
    sock = L.socket(P + "_SOCKET_LeftHand", (0.0, 0.0450, 0.0040), root, col)
    objs = [root, sock]
    register(pid, root, objs, {"category": "foregrip", "mount": "under"})
    return objs


# ================================================================================================ UGL
# Review fixes (v2): the whole launcher sits ~20 mm further forward on the rail (grip-to-magazine gap >= 30 mm for
# mag_30 / mag_45), the tube is shorter so the muzzle ends >= 15 mm behind the front shield's back face, ribs moved
# to the mid tube with a plain stepped muzzle collar, a 20 deg raked grip with finger hook + palm swell, a hexagonal
# trigger window and raised front / rear ears on the top line (concept ugl_side_v01).
UGL_TZ = -0.0615                    # launcher tube axis (housing underside at -0.030)
UGL_R = 0.0290                      # tube outer radius (45 mm bore -> r 0.0225)
UGL_BORE = 0.0225
UGL_BREECH_Y = 0.0000               # breech face (front of the receiver)
UGL_MUZZLE_Y = -0.1500              # muzzle face. Mako: world y -0.485, 17.5 mm behind the shield's back face
UGL_HINGE = Vector((-0.0365, -0.0740, UGL_TZ))     # vertical hinge pin, shooter's right front
UGL_RAKE = 20.0                     # pistol grip rake (deg from vertical)
UGL_COLLAR_Y = -0.1180              # rear tube / muzzle collar seam
UGL_STEPS_TUBE = 24                 # lathe steps: rear tube, ribs, hinge band
UGL_STEPS_MUZZLE = 32               # lathe steps: muzzle collar + mouth (first-person close-ups)


def ugl_grip_profile():
    """Side profile (y, z) of the raked bone grip: front strap with finger hook, back strap with palm swell."""
    return [(0.0625, -0.0500), (0.1040, -0.0500), (0.1045, -0.0580), (0.1100, -0.0740), (0.1170, -0.0940),
            (0.1215, -0.1080), (0.1255, -0.1220), (0.1290, -0.1350), (0.1310, -0.1440), (0.1280, -0.1500),
            (0.0960, -0.1615), (0.0905, -0.1570), (0.0880, -0.1450), (0.0860, -0.1310), (0.0835, -0.1190),
            (0.0795, -0.1100), (0.0720, -0.1060), (0.0700, -0.0990), (0.0745, -0.0900), (0.0740, -0.0830),
            (0.0640, -0.0560)]


def build_ugl():
    pid = "ugl_launcher"
    P = "ATT_" + pid
    col = bc.collection(P)
    R0 = UGL_BREECH_Y
    HY = UGL_HINGE.y
    cl = clamp(P + "_c", "under", -0.060, 0.060, W=0.0165, H=0.0090, slots=[-0.046, -0.032, -0.004, 0.010])
    fin(cl, 0.0010, 1, convex=True)
    bolts = clamp_bolts("under", [-0.018, 0.028], 0.0165, lever_side=1, lever_len=0.028, y_lever=0.044)

    # ---- top housing (in front of the breech face): chamfered section x slanted-nose side profile
    sec_h = [(-0.0260, -0.0075), (0.0260, -0.0075), (0.0315, -0.0130), (0.0315, -0.0255), (0.0280, -0.0300),
             (-0.0280, -0.0300), (-0.0315, -0.0255), (-0.0315, -0.0130)]
    hous = L.prism("_h", sec_h, "Y", -0.0980, R0, mat=M["graphite"])      # ends on the breech face: seam
    L.cut(hous, L.prism("_hs", [(-0.0840, -0.0060), (-0.0980, -0.0310), (R0 + 0.001, -0.0310),
                                (R0 + 0.001, -0.0060)], "X", -0.05, 0.05), op="INTERSECT")
    fin(hous, 0.0016, 1)
    # raised front / rear ears on the top line (concept's notched top), clear of the Mako rail ends (|y| > 0.065)
    ears = []
    for prof in ([(-0.0840, -0.0080), (-0.0800, 0.0025), (-0.0700, 0.0025), (-0.0665, -0.0080)],
                 [(0.0665, -0.0080), (0.0690, 0.0030), (0.0790, 0.0030), (0.0905, -0.0080)]):
        e = L.prism("_ear", prof, "X", -0.0215, 0.0215, mat=M["graphite"])
        L.cut(e, L.prism("_es", [(-0.0215, -0.009), (-0.0215, -0.002), (-0.0150, 0.0040), (0.0150, 0.0040),
                                 (0.0215, -0.002), (0.0215, -0.009)], "Y", -0.1, 0.1), op="INTERSECT")
        fin(e, 0.0010, 1)
        ears.append(e)
    # raised facet slabs on both flanks (concept: long chamfered side plate)
    slabs = []
    for s in (1, -1):
        sl = L.prism("_slab", [(-0.0760, -0.0245), (0.0600, -0.0245), (0.0700, -0.0145), (-0.0690, -0.0145)],
                     "X", s * 0.0300, s * 0.0332, mat=M["graphite"])
        fin(sl, 0.0007, 1)
        slabs.append(sl)
    # ---- receiver: breech face + chin, tail sloping down into the grip (beavertail over the back strap)
    rp = [(R0, -0.0075), (0.0880, -0.0075), (0.1110, -0.0360), (0.1110, -0.0545), (0.0220, -0.0545),
          (0.0220, -0.0840), (0.0140, -0.0950), (R0, -0.0950)]
    recv = L.prism("_r", rp, "X", -0.0315, 0.0315, mat=M["graphite"])
    secr = [(-0.0260, -0.0075), (0.0260, -0.0075), (0.0315, -0.0130), (0.0315, -0.0900), (0.0270, -0.0960),
            (-0.0270, -0.0960), (-0.0315, -0.0900), (-0.0315, -0.0130)]
    L.cut(recv, L.prism("_rs", secr, "Y", R0 - 0.005, R0 + 0.125), op="INTERSECT")
    fin(recv, 0.0016, 1)
    # panel split line between the breech block and the receiver body. Review v2: cut AFTER the bevel and run
    # through the top chamfer and the bottom edge (it used to stop 2.5 mm above the bottom edge, and the 1.6 mm bevel
    # collapsed that bridge into a self-overlapping flank n-gon = fold-over triangles at the latch).
    yl = R0 + 0.0300
    L.cut_crisp(recv, [L.boxp("_pl", (s * 0.0315 - 0.0010, yl, -0.0600), (s * 0.0315 + 0.003, yl + 0.0012, -0.0040))
                       for s in (1, -1)])
    fpin = L.cyl("_fp", 0.0110, (0, R0 + 0.0005, UGL_TZ), (0, R0 - 0.0013, UGL_TZ), verts=12, mat=M["gunmetal"])
    round_fin(fpin, 0.0004)
    # ---- hinge lug (fixed half) + pin
    lug = L.boxp("_lug", (UGL_HINGE.x - 0.0060, HY - 0.0075, -0.0400), (-0.0300, HY + 0.0075, -0.0180),
                 mat=M["graphite"])
    fin(lug, 0.0012, 1)
    pin = L.cyl("_pin", 0.0030, (UGL_HINGE.x, HY, -0.0575), (UGL_HINGE.x, HY, -0.0190), verts=10,
                mat=M["gunmetal"])
    pinh = L.cyl("_pinh", 0.0042, (UGL_HINGE.x, HY, -0.0590), (UGL_HINGE.x, HY, -0.0565), verts=10,
                 mat=M["gunmetal"])
    for o in (pin, pinh):
        round_fin(o, 0.0004)
    # ---- trigger guard: hexagonal window frame, rear wall raked into the grip's front strap
    gout = [(0.0120, -0.0500), (0.0120, -0.0870), (0.0270, -0.1040), (0.0690, -0.1040), (0.0795, -0.0880),
            (0.0680, -0.0500)]
    ghole = [(0.0215, -0.0480), (0.0215, -0.0820), (0.0315, -0.0940), (0.0630, -0.0940), (0.0705, -0.0830),
             (0.0590, -0.0480)]
    guard = L.prism("_tg", gout, "X", -0.0095, 0.0095, mat=M["graphite"])
    L.cut(guard, L.prism("_th", ghole, "X", -0.02, 0.02))
    fin(guard, 0.0014, 1)
    # ---- pistol grip (bone, 20 deg rake): finger hook, palm swell, stipple panel + triangle, graphite base pad
    grip = L.prism(P + "_grip", ugl_grip_profile(), "X", -0.0155, 0.0155, mat=M["bone"])
    pan = []
    for s in (1, -1):
        pan.append(L.prism("_gp", L.chamfer_poly([(0.0870, -0.0820), (0.1090, -0.0820), (0.1230, -0.1380),
                                                  (0.0960, -0.1440), (0.0890, -0.1150)], 0.0025),
                           "X", s * 0.0140, s * 0.03))
        pan.append(L.prism("_gt", L.chamfer_poly([(0.0760, -0.0590), (0.0980, -0.0590), (0.0950, -0.0740)],
                                                 0.0015), "X", s * 0.0135, s * 0.03))
    L.cut(grip, pan)
    k = L.add_mat(grip, M["bone_grip"])
    L.set_mat_by(grip, k, lambda c, n: abs(n.x) > 0.9 and abs(c.x) < 0.0143 and c.z < -0.080)
    fin(grip, 0.0028, 2, smooth_angle=35)
    base = L.prism("_gb", [(0.0905, -0.1540), (0.1295, -0.1400), (0.1360, -0.1460), (0.1345, -0.1545),
                           (0.0985, -0.1690), (0.0895, -0.1625)], "X", -0.0165, 0.0165, mat=M["graphite"])
    fin(base, 0.0014, 1)
    # ---- barrel release latch (shooter's LEFT, +X) and screws
    latch = L.prism("_latch", [(0.0045, -0.0400), (0.0240, -0.0400), (0.0270, -0.0460), (0.0085, -0.0500)], "X",
                    0.0305, 0.0345, mat=M["gunmetal"])      # on the breech block, ends in front of the split line
    fin(latch, 0.0006, 1)
    scr = screws(both_sides(0.0332, -0.0660, -0.0195) + both_sides(0.0315, 0.0840, -0.0420) +
                 both_sides(0.0315, 0.0090, -0.0850) + both_sides(0.0095, 0.0225, -0.0905), r=0.0024)
    scr += screws(both_sides(0.0315, -0.0790, -0.0200), r=0.0026)
    root = L.merge([cl, hous, recv, fpin, lug, pin, pinh, guard, grip, base, latch] + ears + slabs + bolts + scr,
                   P, col=col)

    # ---- swinging barrel ("Breech" child): 45 mm tube, mid-tube ribs, plain stepped muzzle collar, hinge band
    ribs = []
    for y0 in (-0.0120, -0.0250, -0.0380, -0.0510):
        ribs += [(UGL_R, y0), (0.0305, y0 - 0.0012), (0.0305, y0 - 0.0068), (UGL_R, y0 - 0.0080)]
    yb = R0 - 0.0005                      # barrel rear face (0.5 mm gap to the breech face)
    ym = UGL_MUZZLE_Y
    ys = UGL_COLLAR_Y
    # review v2: the tube was a 20-step lathe (faceted muzzle ring in first person). Now the rear tube + ribs use
    # UGL_STEPS_TUBE and the muzzle collar / mouth (the part the camera sees up close) UGL_STEPS_MUZZLE. The two
    # lathes meet on the collar step at y = ys (outer radius steps 29 -> 30 mm there, so the seam is a real edge).
    rear = ([(0.0278, yb), (UGL_R, yb - 0.0012)] + ribs +
            [(UGL_R, ys), (UGL_BORE, ys), (UGL_BORE, yb - 0.0015), (0.0238, yb), (0.0278, yb)])
    front = [(UGL_R, ys), (0.0300, ys - 0.0010), (0.0316, ys - 0.0026), (0.0316, -0.1385), (0.0306, -0.1395),
             (0.0306, ym + 0.0022), (0.0292, ym), (0.0240, ym), (UGL_BORE, ym + 0.0015), (UGL_BORE, ys), (UGL_R, ys)]
    tubes = []
    for nm, prof, steps in (("_tube", rear, UGL_STEPS_TUBE), ("_muz", front, UGL_STEPS_MUZZLE)):
        t = L.lathe_y(nm, prof, steps=steps, center=(0.0, UGL_TZ), mat=M["gunmetal"])
        k = L.add_mat(t, M["dark"])
        L.set_mat_by(t, k, lambda c, n: math.hypot(c.x, c.z - UGL_TZ) < UGL_BORE + 0.0004 and
                     (n.x * c.x + n.z * (c.z - UGL_TZ)) < 0)
        L.smooth(t, 40)
        tubes.append(t)
    band = L.lathe_y("_band", [(0.0285, HY - 0.0100), (0.0298, HY - 0.0092), (0.0306, HY - 0.0080),
                               (0.0306, HY + 0.0080), (0.0298, HY + 0.0092), (0.0285, HY + 0.0100),
                               (0.0285, HY - 0.0100)], steps=UGL_STEPS_TUBE, center=(0.0, UGL_TZ),
                     mat=M["graphite"])
    L.smooth(band, 40)
    knuck = L.boxp("_kn", (UGL_HINGE.x - 0.0060, HY - 0.0070, -0.0555), (-0.0240, HY + 0.0070, -0.0420),
                   mat=M["graphite"])
    fin(knuck, 0.0012, 1)
    br = L.merge(tubes + [band, knuck], P + "_Breech", col=col)
    L.set_origin(br, UGL_HINGE)
    br.parent = root
    br["hinge_axis"] = "Blender local +Z (vertical pin at the shooter's right front) = glTF local +Y"
    br["hinge_axis_blender"] = [0.0, 0.0, 1.0]
    br["hinge_axis_gltf"] = [0.0, 1.0, 0.0]
    br["open_angle_deg"] = -40.0
    br["closed_angle_deg"] = 0.0
    br["pose_open_quat_gltf_xyzw"] = quat_gltf((0, 0, 1), -40.0)
    br["pose_closed_quat_gltf_xyzw"] = [0.0, 0.0, 0.0, 1.0]
    br["note"] = ("rotate about the hinge axis by open_angle_deg (right-hand rule): the breech end swings out to the "
                  "shooter's LEFT (+X); every point of the tube moves forward, away from the breech face")

    # ---- trigger (child, origin at its pivot)
    tp = [(0.0295, -0.0545), (0.0375, -0.0545), (0.0385, -0.0650), (0.0365, -0.0760), (0.0320, -0.0850),
          (0.0290, -0.0840), (0.0320, -0.0750), (0.0335, -0.0650), (0.0310, -0.0580)]
    trig = L.prism(P + "_Trigger", tp, "X", -0.0028, 0.0028, mat=M["gunmetal"])
    fin(trig, 0.0006, 1)
    bc.link(trig, col)
    L.set_origin(trig, (0.0, 0.0335, -0.0560))
    trig.parent = root
    trig["pivot_axis"] = "Blender local +X = glTF local +X"
    trig["pivot_axis_gltf"] = [1.0, 0.0, 0.0]
    trig["pull_angle_deg"] = 12.0
    trig["pose_pulled_quat_gltf_xyzw"] = quat_gltf((1, 0, 0), 12.0)

    sock = L.socket(P + "_SOCKET_LeftHand", (0.0, 0.0985, -0.1000), root, col)
    muz = L.socket(P + "_SOCKET_Muzzle", Vector((0.0, UGL_MUZZLE_Y, UGL_TZ)) - UGL_HINGE, br, col)
    objs = [root, br, trig, sock, muz]
    register(pid, root, objs, {"category": "underbarrel", "mount": "under"})
    return objs


# ================================================================================================ bipod
# Review v2: the leg is built STRAIGHT and every motion is its own node rotation, so the folded pose is clean:
#   ATT_bipod_Leg_<s>       hinge (rotation about local X): knuckle + splay cross-pin caps
#   ATT_bipod_LegSplay_<s>  splay (rotation about local Y, same origin): upper beam, collar, lock button
#   ATT_bipod_LegLower_<s>  telescope (translation along local -Z): lower tube, boot, ankle pin
#   ATT_bipod_Foot_<s>      ankle swivel (rotation about local X): rubber foot
# Deployed (as exported): hinge -40, splay 12 deg outward, swivel 0 -> soles level at BP_SOLE.
# Folded: hinge BP_EULER_FOLD, splay 0 (legs parallel under the handguard), swivel = computed (soles flat).
BP_HZ = -0.0340               # hinge (cross pin) height
BP_HX = 0.0325                # leg knuckle centre |x|
BP_SPLAY = 12.0               # deployed outward splay (LegSplay node), 0 when folded
BP_EULER_DEPLOY = -40.0       # hinge rotation: leg 50 deg below the rail, pointing forward
BP_EULER_FOLD = -95.0         # hinge rotation folded: leg forward, 5 deg up, tucked under the handguard
BP_SOLE = -0.2155             # foot sole. Warden: bore 0.0545 above the origin -> bore 0.270 above ground
BP_UP = 0.1200                # upper leg length along the beam
BP_FOOT = {}                  # filled by build_bipod_leg: computed folded swivel


def bp_matrices(side, low_len=None):
    """Node matrices (parent-relative, +X/'L' build space) of one leg in the DEPLOYED pose:
    Mu hinge, Ms splay, Ml lower-leg slide origin, Mf ankle (needs low_len)."""
    Mu = Matrix.Translation((BP_HX, 0.0, BP_HZ)) @ Matrix.Rotation(math.radians(BP_EULER_DEPLOY), 4, "X")
    Ms = Matrix.Rotation(math.radians(-BP_SPLAY), 4, "Y")       # +X leg: foot swings outward to +X
    Ml = Matrix.Translation((0.0, 0.0, -BP_UP))
    Mf = Matrix.Translation((0.0, 0.0, -low_len + 0.005)) if low_len is not None else None
    return Mu, Ms, Ml, Mf


def build_bipod_leg(side, col, root):
    """side 'L' = +X (built natively), 'R' = -X (mirror). Returns (leg, splay, lower, foot)."""
    L.MIRROR = side == "R"
    P = "ATT_bipod"
    S = L.S_X
    # ---- Leg (hinge node): knuckle on the hinge pin + cross-pin caps of the splay joint (front / back)
    kn = L.cyl("_knk", 0.0160, (-0.0095, 0, 0), (0.0100, 0, 0), verts=16, mat=M["graphite"])
    fin(kn, 0.0016, 1, smooth_angle=40)
    caps = [L.cyl("_xp", 0.0046, (0.0003, s * 0.0148, 0), (0.0003, s * 0.0180, 0), verts=10, mat=M["gunmetal"])
            for s in (1, -1)]
    for o in caps:
        round_fin(o, 0.0005)
    leg = L.merge([kn] + caps, f"{P}_Leg_{side}", col=col)
    # ---- LegSplay: straight upper beam (graphite) + collar + lock button, hanging along local -Z
    beam = L.loft("_beam", [
        [(x, y, -0.002) for x, y in L.crect(0.0098, 0.0155, 0.0040)],
        [(x, y, -0.106) for x, y in L.crect(0.0088, 0.0128, 0.0034)]], mat=M["graphite"])
    L.cut(beam, L.boxp("_lg", (0.0074, -0.0048, -0.092), (0.014, 0.0048, -0.030)))
    fin(beam, 0.0016, 1)
    collar = L.prism("_col", L.crect(0.0118, 0.0168, 0.0045), "Z", -0.1300, -0.0990, mat=M["graphite"])
    fin(collar, 0.0018, 1)
    btn = L.cyl("_btn", 0.0040, (0.0110, 0, -0.1150), (0.0142, 0, -0.1150), verts=8, mat=M["gunmetal"])
    round_fin(btn, 0.0004)
    splay = L.merge([beam, collar, btn], f"{P}_LegSplay_{side}", col=col)     # beam top buried in the knuckle
    # ---- deployed pose: reach from the hinge to the ankle so the soles sit level at BP_SOLE
    Mu, Ms, Ml, _ = bp_matrices(side)
    Wl = Mu @ Ms @ Ml                                         # deployed world matrix of the lower leg (+X side)
    dirw = (Mu @ Ms).to_3x3() @ Vector((0, 0, -1))
    ank_z = BP_SOLE + 0.0135
    reach = (ank_z - BP_HZ) / dirw.z                         # along the beam from the hinge to the ankle
    low_len = reach - BP_UP
    Mf = bp_matrices(side, low_len)[3]
    Wf = Wl @ Mf
    # ---- LegLower: gunmetal octagon tube + graphite boot + ankle pin (local frame: beam along -Z)
    tube = L.prism("_lt", L.octagon(0.0094), "Z", -low_len + 0.020, 0.012, mat=M["gunmetal"])
    L.cut(tube, [L.boxp("_n", (-0.013, -0.0120, zc - 0.0010), (0.013, -0.0082, zc + 0.0010))
                 for zc in (-0.030, -0.042, -0.054)])
    fin(tube, 0.0008, 1)
    boot = L.prism("_bt", L.octagon(0.0130), "Z", -low_len - 0.002, -low_len + 0.030, mat=M["graphite"])
    fin(boot, 0.0018, 1)
    ank = L.cyl("_ank", 0.0062, (-0.0142, 0, -low_len + 0.005), (0.0142, 0, -low_len + 0.005), verts=10,
                mat=M["gunmetal"])
    round_fin(ank, 0.0005)
    lower = L.merge([tube, boot, ank], f"{P}_LegLower_{side}", col=col)
    # ---- Foot (rubber): built in the deployed world pose so the sole is level, then moved into the ankle frame
    c = Wl @ Vector((0, 0, -low_len))
    fx, fy = c.x, c.y - 0.0045
    so = BP_SOLE
    foot = L.loft("_foot", [[(fx + x, fy + y, so) for x, y in L.crect(0.0200, 0.0320, 0.0090)],
                            [(fx + x, fy + y, so + 0.0070) for x, y in L.crect(0.0200, 0.0320, 0.0090)],
                            [(fx + x, fy + 0.0040 + y, so + 0.0180) for x, y in L.crect(0.0140, 0.0200, 0.0055)]],
                  mat=M["rubber"])
    L.cut(foot, [L.boxp("_t", (fx - 0.03, fy + yy - 0.0012, so - 0.001), (fx + 0.03, fy + yy + 0.0012, so + 0.0015))
                 for yy in (-0.018, -0.006, 0.006, 0.018)])
    fin(foot, 0.0018, 1)
    L.xform(foot, Wf.inverted())
    foot = L.merge([foot], f"{P}_Foot_{side}", col=col)
    # ---- folded swivel: rotate the foot about its ankle pin so the sole lies flat (facing down) with the leg folded
    n_loc = (Wf.to_3x3().inverted() @ Vector((0, 0, -1))).normalized()
    down = Vector((0, 0, -1))

    def tilt(k):
        return (Matrix.Rotation(math.radians(BP_EULER_FOLD + k / 10.0), 3, "X") @ n_loc).angle(down)
    swivel = min(range(-1800, 1801), key=tilt) / 10.0
    BP_FOOT["swivel_folded_deg"] = swivel
    BP_FOOT["folded_sole_tilt_deg"] = round(math.degrees(tilt(swivel * 10)), 1)
    # ---- hierarchy + pose (mirror the matrices for the R leg)
    if side == "R":
        Mu, Ms, Ml, Mf = (S @ m @ S for m in (Mu, Ms, Ml, Mf))
    for o, par, m in ((leg, root, Mu), (splay, leg, Ms), (lower, splay, Ml), (foot, lower, Mf)):
        o.parent = par
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.rotation_mode = "XYZ"
        o.matrix_basis = m
    sgn = -1.0 if side == "L" else 1.0                       # Blender local-Y euler of the outward splay
    leg["hinge_axis"] = "local X (world X): the leg folds forward about it"
    leg["hinge_axis_gltf"] = [1.0, 0.0, 0.0]
    leg["deploy_angle_deg"] = 50.0
    leg["fold_angle_deg"] = BP_EULER_FOLD - BP_EULER_DEPLOY
    leg["hinge_euler_x_deployed_deg"] = BP_EULER_DEPLOY
    leg["hinge_euler_x_folded_deg"] = BP_EULER_FOLD
    leg["pose_deployed_quat_gltf_xyzw"] = quat_gltf((1, 0, 0), BP_EULER_DEPLOY)
    leg["pose_folded_quat_gltf_xyzw"] = quat_gltf((1, 0, 0), BP_EULER_FOLD)
    leg["note"] = ("delivered DEPLOYED (leg 50 deg below the rail, pointing forward). To fold: hinge euler X "
                   f"{BP_EULER_DEPLOY:g} -> {BP_EULER_FOLD:g} (fold_angle_deg), child LegSplay splay -> 0, "
                   "grandchild Foot swivel -> swivel_folded_deg. All three are plain local rotations.")
    splay["splay_axis"] = "local Y (along the rail when the leg hangs straight down)"
    splay["splay_axis_gltf"] = [0.0, 0.0, -1.0]
    splay["splay_deg"] = BP_SPLAY
    splay["splay_deployed_deg"] = BP_SPLAY
    splay["splay_folded_deg"] = 0.0
    splay["splay_euler_y_deployed_deg"] = sgn * BP_SPLAY
    splay["splay_euler_y_folded_deg"] = 0.0
    splay["pose_deployed_quat_gltf_xyzw"] = quat_gltf((0, 1, 0), sgn * BP_SPLAY)
    splay["pose_folded_quat_gltf_xyzw"] = [0.0, 0.0, 0.0, 1.0]
    splay["note"] = "outward splay of the leg; blend splay_deployed_deg -> 0 while folding so the legs end parallel"
    lower["slide_axis"] = "local -Z (along the leg)"
    lower["telescope_min_m"] = 0.0
    lower["telescope_max_m"] = 0.050
    lower["telescope_m"] = 0.0
    foot["swivel_axis"] = "local X (ankle pin)"
    foot["swivel_axis_gltf"] = [1.0, 0.0, 0.0]
    foot["swivel_deployed_deg"] = 0.0
    foot["swivel_folded_deg"] = swivel
    foot["pose_deployed_quat_gltf_xyzw"] = [0.0, 0.0, 0.0, 1.0]
    foot["pose_folded_quat_gltf_xyzw"] = quat_gltf((1, 0, 0), swivel)
    foot["note"] = "rubber foot on the ankle pin: level on the ground deployed, flat along the leg folded"
    L.MIRROR = False
    return leg, splay, lower, foot


def bipod_pose(folded):
    """Put the bipod's moving nodes in the deployed or the folded pose (build checks and renders)."""
    for side in ("L", "R"):
        leg = bpy.data.objects[f"ATT_bipod_Leg_{side}"]
        sp = bpy.data.objects[f"ATT_bipod_LegSplay_{side}"]
        ft = bpy.data.objects[f"ATT_bipod_Foot_{side}"]
        leg.rotation_euler[0] = math.radians(leg["hinge_euler_x_folded_deg" if folded else "hinge_euler_x_deployed_deg"])
        sp.rotation_euler[1] = math.radians(sp["splay_euler_y_folded_deg" if folded else "splay_euler_y_deployed_deg"])
        ft.rotation_euler[0] = math.radians(ft["swivel_folded_deg" if folded else "swivel_deployed_deg"])
    bpy.context.view_layer.update()


def build_bipod():
    pid = "bipod"
    P = "ATT_" + pid
    col = bc.collection(P)
    cl = clamp(P + "_c", "under", -0.024, 0.024, W=0.0190, H=0.0100, slots=[-0.014])
    fin(cl, 0.0012, 1, convex=True)
    bolts = clamp_bolts("under", [-0.016], 0.0190, lever_side=1, lever_len=0.034, y_lever=0.006)
    # hinge head: bone polymer housing (the concept's two-tone head) with a graphite belt over the pivot
    head = L.prism("_hd", [(-0.0210, -0.0080), (0.0210, -0.0080), (0.0210, -0.0300), (0.0150, -0.0500),
                           (-0.0150, -0.0500), (-0.0210, -0.0300)], "X", -0.0215, 0.0215, mat=M["bone"])
    L.cut(head, L.prism("_hc", [(-0.0215, -0.0080), (0.0215, -0.0080), (0.0215, -0.0440), (0.0170, -0.0500),
                                (-0.0170, -0.0500), (-0.0215, -0.0440)], "Y", -0.03, 0.03), op="INTERSECT")
    L.cut(head, [L.prism("_pk", L.crect(0.0140, 0.0085, 0.0030, 0.0, -0.0315), "Y", s * 0.0195, s * 0.03)
                 for s in (1, -1)])
    fin(head, 0.0024, 1)
    ins = [L.prism("_in", L.crect(0.0128, 0.0073, 0.0024, 0.0, -0.0315), "Y", s * 0.0170, s * 0.0207,
                   mat=M["graphite"]) for s in (1, -1)]
    for o in ins:
        fin(o, 0.0008, 1)
    belt = L.prism("_belt", [(-0.0222, -0.0100), (0.0222, -0.0100), (0.0222, -0.0450), (0.0180, -0.0512),
                             (-0.0180, -0.0512), (-0.0222, -0.0450)], "Y", -0.0075, 0.0075, mat=M["graphite"])
    fin(belt, 0.0012, 1)
    cant = L.cyl("_cant", 0.0085, (0, 0.0200, -0.0300), (0, 0.0300, -0.0300), verts=6, mat=M["graphite"])
    fin(cant, 0.0010, 1)
    pin = L.cyl("_pin", 0.0060, (-0.0430, 0, BP_HZ), (0.0430, 0, BP_HZ), verts=12, mat=M["gunmetal"])
    round_fin(pin, 0.0005)
    knobs = []
    for s in (1, -1):
        kb = L.cyl("_knob", 0.0110, (s * 0.0430, 0, BP_HZ), (s * 0.0505, 0, BP_HZ), verts=10, mat=M["graphite"])
        L.cut(kb, L.boxp("_ks", (s * 0.0485 - 0.003, -0.0130, BP_HZ - 0.0013), (s * 0.0485 + 0.004, 0.0130,
                                                                                  BP_HZ + 0.0013)))
        round_fin(kb, 0.0010)
        knobs.append(kb)
    root = L.merge([cl, head, belt, cant, pin] + ins + knobs + bolts, P, col=col)
    legL = build_bipod_leg("L", col, root)
    legR = build_bipod_leg("R", col, root)
    bpy.context.view_layer.update()
    objs = [root] + list(legL) + list(legR)
    ms = [o for o in objs if o.type == "MESH"]

    def wb():
        ws = [o.matrix_world @ v.co for o in ms for v in o.data.vertices]
        return ([round(min(w[i] for w in ws), 4) for i in range(3)], [round(max(w[i] for w in ws), 4) for i in range(3)])
    feet = [min((o.matrix_world @ v.co).z for v in o.data.vertices) for o in (legL[3], legR[3])]
    print("bipod foot sole z", [round(f, 4) for f in feet])
    deployed_bounds = wb()
    bipod_pose(True)
    folded_bounds = wb()
    soles_f = [round(min((o.matrix_world @ v.co).z for v in o.data.vertices), 4) for o in (legL[3], legR[3])]
    bipod_pose(False)
    print("bipod deployed bounds", deployed_bounds, "folded bounds", folded_bounds, "folded foot low z", soles_f,
          "swivel", BP_FOOT)
    register(pid, root, objs, {"category": "underbarrel", "mount": "under", "foot_sole_z": round(min(feet), 4),
                               "deployed_bounds": deployed_bounds, "folded_bounds": folded_bounds,
                               "folded_pose": {"hinge_euler_x_deg": BP_EULER_FOLD, "splay_deg": 0.0,
                                               "foot_swivel_deg": BP_FOOT["swivel_folded_deg"],
                                               "foot_sole_tilt_deg": BP_FOOT["folded_sole_tilt_deg"]}})
    return objs


# ================================================================================================ laser
def build_laser(side="R"):
    L.MIRROR = side == "L"
    P = f"ATT_laser_{side}"
    col = bc.collection(P)
    f = L.mount_map("side_R")
    cl = L.prism_f("_c", L.clamp_profile(0.0155, 0.0065, 0.0083), f, -0.024, 0.024, mat=M["graphite"])
    fin(cl, 0.0010, 1, convex=True)
    bolts = []
    for y in (0.012,):     # cross bolt through the jaws (along Z for a side mount)
        bolts.append(L.cyl("_bh", 0.0030, (0.0042, y, 0.0150), (0.0042, y, 0.0176), verts=6, mat=M["gunmetal"]))
        bolts.append(L.cyl("_bn", 0.0027, (0.0042, y, -0.0150), (0.0042, y, -0.0170), verts=8, mat=M["gunmetal"]))
    for b in bolts:
        if b.name.startswith("_bh"):
            fin(b, 0.0004, 1, smooth_angle=40)
        else:
            round_fin(b, 0.0004)
    # body: chamfered box beside the rail (toward -X)
    sec = [(-0.0050, -0.0150), (-0.0085, -0.0175), (-0.0300, -0.0175), (-0.0360, -0.0115), (-0.0360, 0.0105),
           (-0.0295, 0.0170), (-0.0085, 0.0170), (-0.0050, 0.0140)]
    body = L.prism("_b", sec, "Y", -0.0340, 0.0260, mat=M["graphite"])
    hexw = [(-0.0315, 0.0040), (-0.0270, 0.0120), (-0.0140, 0.0120), (-0.0095, 0.0040), (-0.0140, -0.0040),
            (-0.0270, -0.0040)]
    L.cut(body, [L.prism("_hx", hexw, "Y", -0.0360, -0.0320)])
    fin(body, 0.0014, 1)
    # panel lines cut AFTER the bevel (review v2): the top seam used to stop 0.5 mm short of the rail-side chamfer, and
    # the bevel collapsed that bridge into a self-overlapping top n-gon (black wedge in Cycles). Now it runs out on both
    # top chamfers, and neither groove limits the body bevel any more.
    L.cut_crisp(body, [L.boxp("_gv", (-0.0372, -0.0270, -0.0060), (-0.0352, 0.0200, -0.0048)),
                       L.boxp("_gt", (-0.0330, 0.0060, 0.0160), (-0.0065, 0.0072, 0.0185))])
    irw = L.prism("_ir", L.offset_poly(hexw, 0.0006), "Y", -0.0331, -0.0318, mat=M["ir"])
    fin(irw, 0.0004, 1)
    ex, ez = -0.0205, -0.0105
    ring = L.lathe_y("_er", [(0.0031, -0.0355), (0.0052, -0.0355), (0.0056, -0.0349), (0.0056, -0.0330),
                             (0.0031, -0.0330), (0.0031, -0.0355)], steps=12, center=(ex, ez), mat=M["gunmetal"])
    L.smooth(ring, 40)
    pad = L.prism("_pad", L.crect(0.0068, 0.0085, 0.0026, cx=-0.0190, cy=-0.0080), "Z", 0.0160, 0.0186,
                  mat=M["rubber"])
    fin(pad, 0.0008, 1)
    rear = L.prism("_rp", L.crect(0.0080, 0.0095, 0.0030, cx=-0.0205, cy=0.0), "Y", 0.0250, 0.0290, mat=M["rubber"])
    fin(rear, 0.0008, 1)
    scr = screws([((-0.0360, -0.0260, 0.0055), (-1, 0, 0)), ((-0.0360, 0.0170, 0.0055), (-1, 0, 0)),
                  ((-0.0360, 0.0170, -0.0115), (-1, 0, 0))], r=0.0024)
    root = L.merge([cl, body, irw, ring, pad, rear] + scr + bolts, P, col=col)
    lens = L.cyl(P + "_Emitter", 0.0032, (ex, -0.0350, ez), (ex, -0.0336, ez), verts=12, mat=M["laser"])
    L.smooth(lens, 40)
    bc.link(lens, col)
    lens.parent = root
    beam = L.socket(P + "_SOCKET_Beam", (ex, -0.0352, ez), root, col)
    objs = [root, lens, beam]
    register(f"laser_{side}", root, objs, {"category": "side_rail", "mount": "side"})
    L.MIRROR = False
    return objs


# ================================================================================================ flashlight
def build_flashlight(side="R"):
    L.MIRROR = side == "L"
    P = f"ATT_flashlight_{side}"
    col = bc.collection(P)
    f = L.mount_map("side_R")
    AX, AZ = -0.0265, 0.0
    cl = L.prism_f("_c", L.clamp_profile(0.0155, 0.0060, 0.0083), f, -0.020, 0.020, mat=M["graphite"])
    fin(cl, 0.0010, 1, convex=True)
    bolts = [L.cyl("_bh", 0.0030, (0.0042, 0.010, 0.0150), (0.0042, 0.010, 0.0176), verts=6, mat=M["gunmetal"]),
             L.cyl("_bn", 0.0027, (0.0042, 0.010, -0.0150), (0.0042, 0.010, -0.0170), verts=8, mat=M["gunmetal"])]
    for b in bolts:
        if b.name.startswith("_bh"):
            fin(b, 0.0004, 1, smooth_angle=40)
        else:
            round_fin(b, 0.0004)
    arm = L.prism("_arm", [(-0.0045, -0.0115), (-0.0160, -0.0085), (-0.0160, 0.0085), (-0.0045, 0.0115)], "Y",
                  -0.0180, 0.0180, mat=M["graphite"])
    fin(arm, 0.0012, 1)
    prof = [(0.0, 0.0535), (0.0098, 0.0535), (0.0125, 0.0508), (0.0125, 0.0420), (0.0116, 0.0412),
            (0.0116, 0.0396), (0.0125, 0.0388), (0.0125, -0.0215), (0.0168, -0.0315), (0.0168, -0.0480),
            (0.0, -0.0480)]
    body = L.lathe_y("_body", prof, steps=16, center=(AX, AZ), mat=M["graphite"])
    L.smooth(body, 40)
    tail = L.lathe_y("_tail", [(0.0, 0.0595), (0.0052, 0.0595), (0.0066, 0.0580), (0.0066, 0.0525), (0.0, 0.0525)],
                     steps=12, center=(AX, AZ), mat=M["rubber"])
    L.smooth(tail, 40)
    pts = []
    N = 16
    for i in range(N):
        for fa, rr in ((0.00, 0.0186), (0.32, 0.0186), (0.50, 0.0173), (0.82, 0.0173)):
            a = 2 * math.pi * (i + fa) / N
            pts.append((AX + rr * math.cos(a), AZ + rr * math.sin(a)))
    knurl = L.prism("_kn", pts, "Y", -0.0595, -0.0470, mat=M["gunmetal"])
    L.smooth(knurl, 20)
    front = L.lathe_y("_fr", [(0.0138, -0.0592), (0.0184, -0.0592), (0.0184, -0.0606), (0.0174, -0.0622),
                              (0.0146, -0.0622), (0.0138, -0.0612), (0.0138, -0.0592)], steps=16, center=(AX, AZ),
                      mat=M["gunmetal"])
    sc = []
    for k in range(6):
        c = L.boxp("_sc", (AX - 0.0024, -0.0640, AZ + 0.0150), (AX + 0.0024, -0.0612, AZ + 0.0230))
        L.xform(c, L.rot("Y", 60 * k + 30, (AX, 0, AZ)))
        sc.append(c)
    L.cut(front, sc)
    L.smooth(front, 40)
    root = L.merge([cl, arm, body, tail, knurl, front] + bolts, P, col=col)
    lens = L.cyl(P + "_Lens", 0.0141, (AX, -0.0599, AZ), (AX, -0.0589, AZ), verts=16, mat=M["lens"])
    rim = L.lathe_y("_rf", [(0.0075, -0.0601), (0.0098, -0.0601), (0.0098, -0.0597), (0.0075, -0.0597),
                            (0.0075, -0.0601)], steps=16, center=(AX, AZ), mat=M["lens"])
    led = L.lathe_y("_led", [(0.0, -0.0606), (0.0040, -0.0604), (0.0052, -0.0598), (0.0, -0.0598)], steps=12,
                    center=(AX, AZ), mat=M["led"])
    lens = L.merge([lens, rim, led], P + "_Lens")
    L.smooth(lens, 40)
    bc.link(lens, col)
    lens.parent = root
    beam = L.socket(P + "_SOCKET_Beam", (AX, -0.0625, AZ), root, col)
    objs = [root, lens, beam]
    register(f"flashlight_{side}", root, objs, {"category": "side_rail", "mount": "side"})
    L.MIRROR = False
    return objs


# ================================================================================================ shield
SH_Y0, SH_Y1 = -0.0410, -0.0270     # plate front / back (centre panel)
SH_YM = (SH_Y0 + SH_Y1) / 2
SH_FOLD_X = 0.100
SH_FOLD_DEG = 20.0
SH_OUTLINE = [(-0.088, 0.160), (0.088, 0.160), (0.160, 0.068), (0.160, -0.014), (0.118, -0.100), (-0.118, -0.100),
              (-0.160, -0.014), (-0.160, 0.068)]
SH_VIEW = L.chamfer_poly([(-0.092, 0.030), (0.092, 0.030), (0.092, 0.100), (-0.092, 0.100)],
                         [0.020, 0.020, 0.012, 0.012])                  # glass opening z 0.030 .. 0.100
SH_PORT = L.chamfer_poly([(-0.080, -0.066), (0.080, -0.066), (0.080, -0.008), (-0.080, -0.008)], 0.012)


def bend_wings(ob, xc=SH_FOLD_X, ang=SH_FOLD_DEG, ymid=SH_YM):
    """Fold everything beyond |x| = xc back toward the shooter (+Y) by `ang`, keeping plate thickness
    (mitred crease). Faces are split on the crease planes first so every face stays planar."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for sx in (1, -1):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(sx * xc, 0, 0), plane_no=(1, 0, 0), dist=1e-7)
    th = math.radians(ang)
    for v in bm.verts:
        x, y = v.co.x, v.co.y
        ax = abs(x)
        if ax < xc - 1e-6:
            continue
        s = 1.0 if x >= 0 else -1.0
        t = y - ymid
        nw = Vector((-s * math.sin(th), math.cos(th)))
        dw = Vector((s * math.cos(th), math.sin(th)))
        c = Vector((s * xc, ymid))
        if ax <= xc + 1e-6:
            m = Vector((0, 1)) + nw
            m = m / (m.length * math.cos(th / 2))
            p = c + t * m
        else:
            p = c + (ax - xc) * dw + t * nw
        v.co.x, v.co.y = p.x, p.y
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def build_shield():
    pid = "shield_front"
    P = "ATT_" + pid
    col = bc.collection(P)
    rim = 0.0055                      # heavy 45-degree chamfer round the front edge (concept)
    plate = L.loft("_plate", [[(x, SH_Y1, z) for x, z in SH_OUTLINE],
                              [(x, SH_Y0 + rim, z) for x, z in SH_OUTLINE],
                              [(x, SH_Y0, z) for x, z in L.offset_poly(SH_OUTLINE, rim)]], mat=M["graphite"])
    adds = []
    for poly, w in ((SH_VIEW, 0.0120), (SH_PORT, 0.0110)):
        fr = L.loft("_ff", [[(x, SH_Y0 + 0.002, z) for x, z in L.offset_poly(poly, -w)],
                            [(x, SH_Y0 - 0.0020, z) for x, z in L.offset_poly(poly, -w)],
                            [(x, SH_Y0 - 0.0048, z) for x, z in L.offset_poly(poly, -(w - 0.0030))]])
        adds.append(fr)
        adds.append(L.prism("_bf", L.offset_poly(poly, -(w - 0.0030)), "Y", SH_Y1 - 0.002, SH_Y1 + 0.0035))
    # back stiffeners: horizontal rib between window and port, vertical wing ribs, mount boss
    adds.append(L.boxp("_rib", (-0.146, SH_Y1 - 0.002, 0.0060), (0.146, SH_Y1 + 0.0050, 0.0160)))
    for s in (1, -1):
        adds.append(L.boxp("_vr", (s * 0.136 - 0.005, SH_Y1 - 0.002, -0.040), (s * 0.136 + 0.005, SH_Y1 + 0.0050,
                                                                                 0.110)))
    adds.append(L.boxp("_boss", (-0.042, SH_Y1 - 0.002, -0.0010), (0.042, SH_Y1 + 0.0070, 0.0240)))
    L.union(plate, adds)
    # openings (the frames get a 2 mm inner chamfer from the bevel)
    L.cut(plate, [L.prism("_o1", SH_VIEW, "Y", -0.08, 0.02), L.prism("_o2", SH_PORT, "Y", -0.08, 0.02)])
    bend_wings(plate)
    fin(plate, 0.0018, 1, smooth_angle=15)
    bl = []
    for x, z in ((0.092, 0.134), (-0.092, 0.134), (0.140, 0.025), (-0.140, 0.025), (0.104, -0.075),
                 (-0.104, -0.075)):
        bl.append(L.cyl("_bolt", 0.0042, (x, SH_Y0 + 0.001, z), (x, SH_Y0 - 0.0026, z), verts=6))
    bolts = L.join_raw(bl, "_bolts")
    bolts.data.materials.append(M["gunmetal"])
    bend_wings(bolts)
    fin(bolts, 0.0006, 1, smooth_angle=40)
    # arm (clamp -> boss) + clamp on the top rail
    arm = L.prism("_arm", [(-0.0215, 0.0020), (-0.0215, 0.0235), (-0.0080, 0.0235), (0.0100, 0.0125),
                           (0.0100, 0.0080), (-0.0160, 0.0080), (-0.0160, 0.0020)], "X", -0.0140, 0.0140,
                  mat=M["graphite"])
    fin(arm, 0.0016, 1)
    gus = []
    for s in (1, -1):
        gp = L.prism("_gus", [(SH_Y1 + 0.0060, 0.0030), (SH_Y1 + 0.0060, 0.0200), (-0.0080, 0.0030)], "X",
                     s * 0.0290, s * 0.0230, mat=M["graphite"])
        fin(gp, 0.0010, 1)
        gus.append(gp)
    cl = clamp("_c", "top", -0.0160, 0.0340, W=0.0165, H=0.0100, slots=[0.012])
    fin(cl, 0.0012, 1, convex=True)
    cb = clamp_bolts("top", [0.0000, 0.0260], 0.0165, lever_side=1, lever_len=0.026, y_lever=0.013)
    root = L.merge([plate, bolts, arm, cl] + gus + cb, P, col=col)
    glass = L.prism(P + "_Glass", L.offset_poly(SH_VIEW, -0.0030), "Y", SH_Y0 + 0.0040, SH_Y1 - 0.0030,
                    mat=M["glass"])
    fin(glass, 0.0008, 1)
    bc.link(glass, col)
    glass.parent = root
    objs = [root, glass]
    register(pid, root, objs, {"category": "shield", "mount": "top", "glass_z": [0.030, 0.100],
                               "glass_material": {"base_color": list(GLASS_RGB), "alpha": GLASS_ALPHA,
                                                  "roughness": GLASS_ROUGH, "alpha_mode": "BLEND"},
                               "plate_z": [-0.100, 0.160], "plate_x": [-0.160, 0.160],
                               "port": {"x": [-0.080, 0.080], "z": [-0.066, -0.008]}})
    return objs


# ================================================================================================ proxies
def rail(name, mount, y0, y1, offset, col, mat):
    f0 = L.mount_map(mount)
    off = Vector(offset)
    f = lambda u, v, t: f0(u, v, t) + off  # noqa: E731
    ob = L.prism_f(name, L.rail_profile(), f, y0, y1, col, mat)
    cutters = []
    yc = y0 + 0.0060
    while yc + 0.0025 < y1 - 0.002:
        cutters.append(L.prism_f("_s", [(-0.013, -0.0030), (0.013, -0.0030), (0.013, 0.002), (-0.013, 0.002)], f,
                                 yc - 0.0025, yc + 0.0025))
        yc += L.RAIL_PITCH
    L.cut(ob, cutters)
    fin(ob, 0.0007, 1)
    return ob


def side_rail(name, sx, y0, y1, col, mat):
    """Side rail on the Mako handguard: base at x = sx*0.023, outer face at sx*0.0325, centred on the bore."""
    f0 = L.mount_map("side_R")
    off = Vector((sx * 0.0325, 0, 0.050))
    if sx < 0:
        f = lambda u, v, t: f0(u, v, t) * 1 + off  # noqa: E731
    else:
        f = lambda u, v, t: Vector((v, t, u)) + off  # noqa: E731
    ob = L.prism_f(name, L.rail_profile(), f, y0, y1, col, mat)
    fin(ob, 0.0007, 1)
    return ob


def build_proxy_mako():
    """Mako stand-in matching build_mako.py dimensions (bore z 0.050, rail top 0.084, handguard to y -0.495,
    barrel r 0.0095 to -0.513, flash hider r 0.0126 -0.509..-0.565, side rails y -0.474..-0.424)."""
    col = bc.collection("_Proxy_Mako")
    pm, pd, pb = M["proxy"], M["proxy_dark"], M["proxy_bone"]
    fallback = {"Optic": (0, -0.0855, 0.084), "Under": (0, -0.335, 0.0155), "Side_R": (-0.0325, -0.449, 0.050),
                "Side_L": (0.0325, -0.449, 0.050), "Shield": (0, -0.4755, 0.084), "Muzzle": (0, -0.565, 0.050),
                "LeftHand": (0, -0.330, 0.0155)}
    socks, src, mis = L.gun_sockets(MAKO_GLB, MAKO_SOCKETS, "MAKO", fallback)
    bc.profile_extrude("_PX_Upper", [(-0.168, 0.024), (-0.168, 0.0745), (0.022, 0.0745), (0.030, 0.066),
                                     (0.030, 0.046), (0.014, 0.046), (0.008, 0.024)], 0.032, col=col, mat=pm,
                       bevel=0.002)
    bc.profile_extrude("_PX_Lower", [(-0.160, 0.024), (-0.162, -0.026), (-0.168, -0.032), (-0.168, -0.038),
                                     (-0.080, -0.038), (-0.078, -0.030), (-0.080, -0.006), (-0.072, 0.000),
                                     (0.018, 0.000), (0.030, 0.008), (0.036, 0.020), (0.036, 0.046), (0.014, 0.046),
                                     (0.008, 0.024)], 0.030, col=col, mat=pm, bevel=0.002)
    hg_sec = [(0.013, 0.0745), (-0.013, 0.0745), (-0.023, 0.0655), (-0.023, 0.0345), (-0.0135, 0.025),
              (0.0135, 0.025), (0.023, 0.0345), (0.023, 0.0655)]
    hg = L.prism("_PX_Handguard", hg_sec, "Y", -0.495, -0.168, col=col, mat=pm)
    slots = []
    for yc in [-0.462 + 0.032 * k for k in range(9)]:
        if -0.480 < yc < -0.418:
            continue
        for zc in (0.0405, 0.0595):
            slots.append(L.boxp("_sl", (-0.03, yc - 0.010, zc - 0.0035), (0.03, yc + 0.010, zc + 0.0035)))
    L.cut(hg, slots)
    fin(hg, 0.0015, 1)
    rail("_PX_RailTop", "top", -0.493, 0.022, (0, 0, 0.084), col, pm)
    rail("_PX_RailBottom", "under", -0.400, -0.270, (0, 0, socks["Under"][2]), col, pm)
    side_rail("_PX_RailSide_R", -1, -0.474, -0.424, col, pm)
    side_rail("_PX_RailSide_L", 1, -0.474, -0.424, col, pm)
    bar = L.cyl("_PX_Barrel", 0.0095, (0, -0.513, 0.050), (0, -0.150, 0.050), verts=20, col=col, mat=pd)
    L.smooth(bar, 40)
    hid = L.cyl("_PX_Hider", 0.0126, (0, -0.565, 0.050), (0, -0.509, 0.050), verts=20, col=col, mat=pd)
    cuts = []
    for k in range(5):
        c = L.boxp("_hs", (-0.0018, -0.557, 0.060), (0.0018, -0.532, 0.070))
        L.xform(c, L.rot("Y", 60 * k - 120, (0, 0, 0.050)))
        cuts.append(c)
    L.cut(hid, cuts)
    fin(hid, 0.0008, 1, smooth_angle=40)
    bc.profile_extrude("_PX_Grip", [(-0.020, 0.002), (0.022, 0.002), (0.030, 0.008), (0.035, 0.000), (0.044, -0.030),
                                    (0.054, -0.062), (0.066, -0.100), (0.064, -0.108), (0.026, -0.111),
                                    (0.021, -0.104), (0.008, -0.064), (-0.004, -0.034), (-0.020, -0.006)], 0.030,
                       col=col, mat=pb, bevel=0.003)
    bc.profile_extrude("_PX_Mag", [(-0.152, 0.012), (-0.152, -0.020), (-0.1532, -0.0494), (-0.1567, -0.0786),
                                   (-0.1626, -0.1075), (-0.1707, -0.1358), (-0.1745, -0.1345), (-0.1783, -0.1459),
                                   (-0.1099, -0.1686), (-0.1061, -0.1572), (-0.1099, -0.1559), (-0.1004, -0.1227),
                                   (-0.0935, -0.0888), (-0.0894, -0.0545), (-0.088, -0.020), (-0.088, 0.012)],
                       0.025, col=col, mat=pb, bevel=0.002)
    tb = L.cyl("_PX_Tube", 0.016, (0, 0.030, 0.050), (0, 0.215, 0.050), verts=20, col=col, mat=pd)
    L.smooth(tb, 40)
    bc.profile_extrude("_PX_Stock", [(0.098, 0.034), (0.098, 0.064), (0.110, 0.074), (0.136, 0.078), (0.262, 0.078),
                                     (0.262, -0.056), (0.240, -0.056), (0.164, 0.020), (0.150, 0.025),
                                     (0.106, 0.026)], 0.034, col=col, mat=pb, bevel=0.003)
    # holo optic stand-in on the optic socket, sight line = rail top + 0.045
    op = bc.profile_extrude("_PX_Optic", [(-0.040 - 0.0855, 0.084), (0.036 - 0.0855, 0.084),
                                          (0.036 - 0.0855, 0.104), (0.032 - 0.0855, 0.146), (-0.0855, 0.148),
                                          (-0.032 - 0.0855, 0.140), (-0.040 - 0.0855, 0.110)], 0.036, col=col,
                            mat=pb)
    L.cut(op, L.prism("_ow", L.crect(0.013, 0.012, 0.004, 0.0, 0.129), "Y", -0.2, 0.0))
    fin(op, 0.002, 1)
    for k, v in socks.items():
        L.socket("_PX_SOCKET_" + k, v, None, col)
    print("MAKO sockets from", src, "json/glb mismatch:", mis)
    return col, socks, src, mis


def build_proxy_warden():
    col = bc.collection("_Proxy_Warden")
    pm, pd = M["proxy"], M["proxy_dark"]
    fallback = {"Under": (0, -0.600, 0.0205), "Side_R": (-0.0455, -0.645, 0.079), "Side_L": (0.0455, -0.645, 0.079),
                "Optic": (0, -0.080, 0.1375), "Muzzle": (0, -1.100, 0.075)}
    socks, src, mis = L.gun_sockets(WARDEN_GLB, WARDEN_SOCKETS, "WARDEN", fallback)
    hg = bc.box("_PW_Handguard", (0.072, 0.390, 0.098), loc=(0, -0.495, 0.079), col=col, mat=pm, bevel=0.012,
                segments=1)
    bc.apply_modifiers(hg)
    L.cut(hg, [L.boxp("_sl", (-0.05, yc - 0.0275, 0.074), (0.05, yc + 0.0275, 0.094))
               for yc in (-0.370, -0.445, -0.520, -0.595)])
    rail("_PW_RailTop", "top", -0.690, 0.078, (0, 0, 0.1375), col, pm)
    rail("_PW_RailBottom", "under", -0.650, -0.540, (0, 0, socks["Under"][2]), col, pm)
    bar = L.cyl("_PW_Barrel", 0.022, (0, -0.950, 0.075), (0, -0.680, 0.075), verts=24, col=col, mat=pd)
    L.smooth(bar, 40)
    br = bc.box("_PW_Brake", (0.070, 0.150, 0.062), loc=(0, -1.025, 0.075), col=col, mat=pd, bevel=0.006,
                segments=1)
    bc.apply_modifiers(br)
    L.cut(br, [L.boxp("_p", (-0.05, -1.022, 0.053), (0.05, -0.985, 0.097)),
               L.boxp("_p", (-0.05, -1.074, 0.053), (0.05, -1.035, 0.097))])
    bc.profile_extrude("_PW_Receiver", [(0.080, 0.035), (0.080, 0.112), (0.064, 0.128), (-0.292, 0.128),
                                        (-0.300, 0.120), (-0.300, 0.033), (-0.292, 0.025), (0.072, 0.025)], 0.078,
                       col=col, mat=pm, bevel=0.004)
    bc.profile_extrude("_PW_Chassis", [(0.080, 0.025), (-0.340, 0.025), (-0.296, -0.040), (-0.290, -0.058),
                                       (-0.282, -0.068), (-0.112, -0.068), (-0.104, -0.060), (-0.104, -0.010),
                                       (-0.030, 0.000), (0.040, 0.000), (0.080, -0.010)], 0.070, col=col, mat=pm,
                       bevel=0.004)
    bc.profile_extrude("_PW_Mag", [(-0.270, 0.000), (-0.120, 0.000), (-0.118, -0.168), (-0.276, -0.168)], 0.052,
                       col=col, mat=pm, bevel=0.004)
    bc.profile_extrude("_PW_Grip", [(-0.026, 0.004), (0.030, 0.004), (0.042, -0.018), (0.064, -0.110),
                                    (0.062, -0.124), (0.052, -0.132), (0.020, -0.132), (0.010, -0.124),
                                    (-0.004, -0.072), (-0.010, -0.054), (-0.020, -0.036), (-0.026, -0.012)], 0.034,
                       col=col, mat=pm, bevel=0.004)
    bc.profile_extrude("_PW_Stock", [(0.080, 0.045), (0.122, 0.045), (0.140, 0.080), (0.150, 0.088),
                                     (0.282, 0.092), (0.292, 0.100), (0.320, 0.100), (0.320, -0.126), (0.240, -0.126),
                                     (0.100, -0.032), (0.080, -0.012)], 0.046, col=col, mat=pm, bevel=0.004)
    sc = L.lathe_y("_PW_Scope", [(0.0, 0.065), (0.020, 0.065), (0.025, 0.060), (0.025, 0.012), (0.0185, -0.012),
                                 (0.0185, -0.165), (0.034, -0.212), (0.034, -0.300), (0.0, -0.300)], steps=24,
                   center=(0, 0.178), col=col, mat=pd)
    L.smooth(sc, 40)
    for yy in (-0.020, -0.140):
        bc.box("_PW_Ring", (0.034, 0.024, 0.040), loc=(0, yy, 0.1575), col=col, mat=pd, bevel=0.003, segments=1)
    bc.box("_PW_Ground", (0.9, 1.9, 0.004), loc=(0, -0.42, -0.195 - 0.002), col=col, mat=M["ground"])
    for k, v in socks.items():
        L.socket("_PW_SOCKET_" + k, v, None, col)
    print("WARDEN sockets from", src, "json/glb mismatch:", mis)
    return col, socks, src, mis


# ================================================================================================ main
def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=HERE, help="Build directory (defaults to this asset folder)")
    output = Path(parser.parse_args(argv).out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "_work").mkdir(exist_ok=True)
    L.TEXOUT = str(output / "textures")
    bc.reset_scene()
    scene = bpy.context.scene
    make_materials()
    parts = {}
    parts["grip_vertical"] = build_grip_vertical()
    parts["grip_angled"] = build_grip_angled()
    parts["grip_stub"] = build_grip_stub()
    parts["ugl_launcher"] = build_ugl()
    parts["bipod"] = build_bipod()
    parts["laser_R"] = build_laser("R")
    parts["laser_L"] = build_laser("L")
    parts["flashlight_R"] = build_flashlight("R")
    parts["flashlight_L"] = build_flashlight("L")
    parts["shield_front"] = build_shield()
    if FAILED:
        # nothing is exported or saved: the previous deliverables stay as they were
        print("BUILD FAILED (mesh checks / budgets):")
        for f in FAILED:
            print("   ", f)
        raise SystemExit("build_tactical: mesh checks failed")

    # glTF hygiene: UVs per material density, mesh data named like the object, no empty slots
    for pid, objs in parts.items():
        for o in objs:
            if o.type == "MESH":
                L.clean_slots(o)
                L.world_box_uv(o)
                o.data.name = o.name

    pm_col, mako_socks, mako_src, mako_mis = build_proxy_mako()
    pw_col, warden_socks, warden_src, warden_mis = build_proxy_warden()
    for o in list(pm_col.objects) + list(pw_col.objects):
        if o.type == "MESH" and not o.data.uv_layers:
            L.world_box_uv(o)

    # ---------------------------------------------------------------- exports (each part at its own origin)
    catalog = []
    socket_for = {"grip_vertical": "Under", "grip_angled": "Under", "grip_stub": "Under", "ugl_launcher": "Under",
                  "bipod": "Under", "laser_R": "Side_R", "laser_L": "Side_L", "flashlight_R": "Side_R",
                  "flashlight_L": "Side_L", "shield_front": "Shield"}
    # review v2: compatibility follows game/assets/data/attachments.ron (`fits`); grips are Mako-only there
    game_ids = {pid: GAME_FITS[pid.rsplit("_", 1)[0] if pid.endswith(("_R", "_L")) else pid] for pid in parts}
    compat = {pid: [GAME_PREFIX[g] for g in ids] for pid, ids in game_ids.items()}
    origin_doc = {"under": "centre of clamp contact on the rail BOTTOM surface (part hangs -Z)",
                  "top": "centre of clamp contact on the rail TOP surface",
                  "side": "centre of clamp contact on the rail outer face (part sticks out sideways)"}
    for pid, objs in parts.items():
        base = str(output / ("ATT_" + pid))
        L.export_part(base, objs)
        st = STATS[pid]
        socks = [o.name for o in objs if o.type == "EMPTY"]
        moving = {o.name: {k: prop_val(o[k]) for k in o.keys() if not k.startswith("_")}
                  for o in objs if o.parent is not None and len(o.keys())}
        bpy.context.view_layer.update()
        ws = [o.matrix_world @ v.co for o in objs if o.type == "MESH" for v in o.data.vertices]
        mn = [min(w[i] for w in ws) for i in range(3)]
        mxv = [max(w[i] for w in ws) for i in range(3)]
        sk = socket_for[pid]
        entry = {
            "id": "ATT_" + pid, "category": st["category"], "mount": st["mount"],
            "file": f"assets/weapons/attachments/tactical/ATT_{pid}.glb",
            "fbx": f"assets/weapons/attachments/tactical/ATT_{pid}.fbx",
            "sockets_accepted": ["_SOCKET_" + sk],
            "socket_names": {w: f"{w}_SOCKET_{sk}" for w in compat[pid]},
            "compatible_weapons": compat[pid], "compatible_weapon_ids": game_ids[pid],
            "game_attachment_id": pid.rsplit("_", 1)[0] if pid.endswith(("_R", "_L")) else pid,
            "tris": st["tris"], "objects": st["objects"],
            "child_sockets": socks, "moving_parts": moving, "origin": origin_doc[st["mount"]],
            "bounds_min": [round(v, 4) for v in mn], "bounds_max": [round(v, 4) for v in mxv],
        }
        if pid.endswith(("_R", "_L")):
            entry["mirror_of"] = "ATT_" + pid[:-1] + ("L" if pid.endswith("R") else "R")
        for k in ("foot_sole_z", "deployed_bounds", "folded_bounds", "folded_pose", "glass_z", "plate_z", "plate_x",
                  "port", "glass_material"):
            if k in st:
                entry[k] = st[k]
        catalog.append(entry)
    with open(output / "catalog.json", "w") as fh:
        json.dump({"prefix": "ATT", "set": "tactical / underbarrel / shield",
                   "units": "metres, Blender axes (Z up, muzzle -Y); shooter's right = -X",
                   "rail_standard": {"top_width": L.RAIL_W, "height": L.RAIL_H, "slot_pitch": L.RAIL_PITCH},
                   "parts": catalog,
                   "notes": {"SKINK": "sk9_skink (game id) has no art export yet; its prefix SKINK is assumed",
                             "compatibility": "compatible_weapon_ids mirror game/assets/data/attachments.ron fits"},
                   "test_sockets": {"MAKO": mako_socks, "WARDEN": warden_socks},
                   "test_socket_source": {"MAKO": mako_src, "WARDEN": warden_src},
                   "test_socket_json_vs_glb_mismatch": {"MAKO": mako_mis, "WARDEN": warden_mis}}, fh, indent=2)

    # ---------------------------------------------------------------- TestFit scene (instances on the proxies)
    fit = bpy.data.scenes.new("TestFit")
    fit.collection.children.link(pm_col)
    fit.collection.children.link(pw_col)
    tf = bpy.data.collections.new("_TestFit_Instances")
    fit.collection.children.link(tf)
    placements = [("ATT_ugl_launcher", mako_socks["Under"]), ("ATT_laser_R", mako_socks["Side_R"]),
                  ("ATT_flashlight_L", mako_socks["Side_L"]), ("ATT_shield_front", mako_socks["Shield"]),
                  ("ATT_bipod", warden_socks["Under"])]
    for cname, loc in placements:
        e = bpy.data.objects.new("_inst_" + cname, None)
        e.instance_type = "COLLECTION"
        e.instance_collection = bpy.data.collections[cname]
        e.location = loc
        tf.objects.link(e)
    vl = scene.view_layers[0]
    for name in ("_Proxy_Mako", "_Proxy_Warden"):
        vl.layer_collection.children[name].exclude = True
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "tactical.blend"), compress=True)
    print("saved tactical.blend")
    print("STATS", json.dumps({k: v["tris"] for k, v in STATS.items()}))
    with open(output / "_work" / "build_stats.json", "w") as fh:
        json.dump(STATS, fh, indent=1)


main()
