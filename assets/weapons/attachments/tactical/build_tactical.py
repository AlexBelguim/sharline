"""ATT tactical / underbarrel / shield attachment set -- re-runnable build (headless Blender 5.2).

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/weapons/attachments/tactical/build_tactical.py"

Builds from scratch, every part in its own collection, modelled in MOUNT SPACE (origin = clamp contact centre,
see art/WEAPON_MODULAR_SPEC.md rail standard), plus Mako / Warden proxies for test fitting (scene "TestFit").
Writes tactical.blend, ATT_<part>.glb/.fbx and catalog.json next to this file.
Handedness: shooter's RIGHT = -X. Side parts are modelled for the right (_R, sticking out toward -X);
_L is the X-mirror with normals flipped back outward.
"""
import json
import math
import os
import sys

HERE = r"F:/git/val etf/assets/weapons/attachments/tactical"
sys.path.insert(0, r"F:/git/val etf/tools")
sys.path.insert(0, HERE)

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import blender_common as bc  # noqa: E402
import att_lib as L  # noqa: E402

M = {}
STATS = {}


# ================================================================================================ materials
def make_materials():
    worn = os.path.join(L.TEX, "worn_paint.png")
    stip = os.path.join(L.TEX, "polymer_stipple.png")
    brush = os.path.join(L.TEX, "brushed_metal.png")
    M["graphite"] = bc.material("M_ATT_Graphite", (0.030, 0.033, 0.040), rough=0.50, metal=0.25,
                                tex=worn, tex_scale=1.0, tex_mix=0.30)
    M["gunmetal"] = bc.material("M_ATT_Gunmetal", (0.11, 0.115, 0.12), rough=0.35, metal=0.85,
                                tex=brush, tex_scale=2.0, tex_mix=0.25)
    M["bone"] = bc.material("M_ATT_Bone", (0.55, 0.52, 0.46), rough=0.60, metal=0.0,
                            tex=worn, tex_scale=1.0, tex_mix=0.25)
    M["bone_grip"] = bc.material("M_ATT_BoneStipple", (0.46, 0.435, 0.385), rough=0.75, metal=0.0,
                                 tex=stip, tex_scale=6.0, tex_mix=0.55)
    M["rubber"] = bc.material("M_ATT_Rubber", (0.030, 0.033, 0.040), rough=0.85, metal=0.0)
    M["dark"] = bc.material("M_ATT_Dark", (0.035, 0.037, 0.045), rough=0.70, metal=0.0)
    M["glass"] = bc.material("M_ATT_ShieldGlass", (0.22, 0.48, 0.82), rough=0.04, metal=0.0, alpha=0.40)
    M["laser"] = bc.material("M_ATT_LaserRed", (1.0, 0.03, 0.02), rough=0.25, metal=0.0,
                             emission=(1.0, 0.02, 0.01), emission_strength=8.0)
    M["ir"] = bc.material("M_ATT_IRWindow", (0.035, 0.012, 0.040), rough=0.06, metal=0.0, coat=1.0)
    M["lens"] = bc.material("M_ATT_LightLens", (0.80, 0.82, 0.85), rough=0.10, metal=0.0,
                            emission=(1.0, 0.95, 0.86), emission_strength=1.5)
    M["proxy"] = bc.material("_M_Proxy", (0.17, 0.18, 0.20), rough=0.65, metal=0.0)
    M["proxy_dark"] = bc.material("_M_ProxyDark", (0.09, 0.095, 0.105), rough=0.55, metal=0.3)
    M["ground"] = bc.material("_M_Ground", (0.30, 0.31, 0.33), rough=0.9)


# ================================================================================================ helpers
def inset(poly, d):
    """Offset a convex polygon (any winding) inward by d (negative d grows it)."""
    n = len(poly)
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    s = 1.0 if area > 0 else -1.0
    lines = []
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        nx, ny = -dy / ln * s, dx / ln * s
        lines.append(((x0 + nx * d, y0 + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        (p, r), (q, s2) = lines[i - 1], lines[i]
        den = r[0] * s2[1] - r[1] * s2[0]
        a = ((q[0] - p[0]) * s2[1] - (q[1] - p[1]) * s2[0]) / den
        out.append((p[0] + a * r[0], p[1] + a * r[1]))
    return out


def box_uv(ob, scale=10.0):
    """World-scale box projection UVs (consistent texel density across all parts)."""
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    for p in me.polygons:
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if ax == 0:
                uv[li].uv = (co.y * scale, co.z * scale)
            elif ax == 1:
                uv[li].uv = (co.x * scale, co.z * scale)
            else:
                uv[li].uv = (co.x * scale, co.y * scale)


def clamp(name, mount, y0, y1, W=0.0155, H=0.008, D=0.0083, mat=None):
    return L.prism_f(name, L.clamp_profile(W, H, D), L.mount_map(mount), y0, y1, mat=mat or M["graphite"])


def clamp_bolts(mount, ys, W, v=-0.0042, lever_side=None, lever_len=0.030, y_lever=0.0):
    """Cross-bolt heads (hex) and nuts on the clamp jaws + optional QD throw lever on side +1/-1 (u axis)."""
    f = L.mount_map(mount)
    parts = []
    for y in ys:
        parts.append(L.cyl("_bh", 0.0031, f(W - 0.0006, v, y), f(W + 0.0020, v, y), verts=6,
                           mat=M["gunmetal"]))
        parts.append(L.cyl("_bn", 0.0027, f(-W + 0.0006, v, y), f(-W - 0.0016, v, y), verts=10,
                           mat=M["gunmetal"]))
    for p in parts:
        L.finish(p, 0.0005, 1, smooth_angle=40)
    if lever_side:
        s = lever_side
        # lever plate lying along the jaw face, with a cam boss at its pivot end
        g = lambda u, v_, t: f(u, v_, t)  # noqa: E731
        u0, u1 = s * (W - 0.0004), s * (W + 0.0032)
        pts = [(y_lever - lever_len / 2, -0.0068), (y_lever + lever_len / 2 - 0.006, -0.0068),
               (y_lever + lever_len / 2, -0.0045), (y_lever + lever_len / 2, -0.0010),
               (y_lever - lever_len / 2 + 0.004, -0.0016), (y_lever - lever_len / 2, -0.0040)]
        bmv = bmesh.new()
        lo = [bmv.verts.new(g(u0, vv, yy)) for yy, vv in pts]
        hi = [bmv.verts.new(g(u1, vv, yy)) for yy, vv in pts]
        bmv.faces.new(lo)
        bmv.faces.new(hi[::-1])
        for i in range(len(pts)):
            j = (i + 1) % len(pts)
            bmv.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bmesh.ops.recalc_face_normals(bmv, faces=bmv.faces)
        lev = L.new_obj("_lever", bmv, mat=M["gunmetal"])
        L.finish(lev, 0.0008, 1)
        boss = L.cyl("_boss", 0.0042, f(s * (W - 0.0004), -0.0040, y_lever + lever_len / 2 - 0.004),
                     f(s * (W + 0.0042), -0.0040, y_lever + lever_len / 2 - 0.004), verts=12, mat=M["gunmetal"])
        L.finish(boss, 0.0006, 1, smooth_angle=40)
        parts += [lev, boss]
    return parts


def fin(ob, w, segs=2, angle=30, smooth_angle=30):
    return L.finish(ob, w, segs, angle, smooth_angle)


def new_part(pid, col_name=None):
    col = bc.collection(col_name or ("ATT_" + pid))
    return col


def register(pid, root, objs, extra=None):
    total = sum(L.tris(o) for o in objs if o.type == "MESH")
    STATS[pid] = {"root": root.name, "objects": [o.name for o in objs], "tris": total}
    if extra:
        STATS[pid].update(extra)
    print(f"[{pid}] tris={total}  objects={len(objs)}")


# ================================================================================================ foregrips
def build_grip_vertical():
    pid = "grip_vertical"
    P = "ATT_" + pid
    col = new_part(pid)
    cl = clamp(P + "_c", "under", -0.026, 0.026, W=0.0155, H=0.0095)
    fin(cl, 0.0012, 2)
    bolts = clamp_bolts("under", [0.012], 0.0155, lever_side=None)
    # body: tapered, forward-raked octagonal loft (bone)
    st = [(-0.0070, 0.0145, 0.0185, 0.000, 0.0055),
          (-0.0170, 0.0170, 0.0205, 0.000, 0.0072),
          (-0.0885, 0.0170, 0.0190, -0.0065, 0.0068)]
    loops = [[(x, y + dy, z) for x, y in L.crect(hx, hy, c)] for z, hx, hy, dy, c in st]
    body = L.loft(P + "_b", loops, mat=M["bone"])
    # recessed stipple panels on both sides (0.0015 deep)
    pan = []
    for s in (1, -1):
        pts = L.crect(0.0125, 0.0255, 0.006, cx=-0.0035, cy=-0.052)
        x0 = s * 0.0155
        pan.append(L.prism("_pan", pts, "X", x0, s * 0.03))
    # three finger ridges on the front face, done as shallow (1.5 mm) grooves
    for z in (-0.034, -0.052, -0.070):
        k = (abs(z) - 0.017) / (0.0885 - 0.017)
        yf = -(0.0205 - 0.0015 * k) - 0.0065 * k
        pan.append(L.boxp("_gr", (-0.012, yf - 0.003, z - 0.0013), (0.012, yf + 0.0015, z + 0.0013)))
    L.cut(body, pan)
    L.set_mat_by(body, 1, lambda p: abs(p.normal.x) > 0.9 and abs(p.center.x) < 0.0160)
    body.data.materials.append(M["bone_grip"])
    fin(body, 0.0035, 3, smooth_angle=35)
    # flared bottom cap (graphite)
    cap_loops = [[(x, y - 0.0063, -0.0860) for x, y in L.crect(0.0175, 0.0195, 0.0070)],
                 [(x, y - 0.0068, -0.0950) for x, y in L.crect(0.0198, 0.0222, 0.0082)],
                 [(x, y - 0.0070, -0.1020) for x, y in L.crect(0.0186, 0.0210, 0.0078)]]
    cap = L.loft(P + "_cap", cap_loops, mat=M["graphite"])
    fin(cap, 0.0022, 2)
    root = L.merge([cl, body, cap] + bolts, P, col=col)
    sock = L.socket(P + "_SOCKET_LeftHand", (0.0, -0.0035, -0.052), root, col)
    objs = [root, sock]
    register(pid, root, objs, {"category": "foregrip", "mount": "under"})
    return objs


def build_grip_angled():
    pid = "grip_angled"
    P = "ATT_" + pid
    col = new_part(pid)
    cl = clamp(P + "_c", "under", -0.052, 0.050, W=0.0155, H=0.0095)
    fin(cl, 0.0012, 2)
    bolts = clamp_bolts("under", [-0.030, 0.026], 0.0155)
    prof = [(0.050, -0.0088), (-0.052, -0.0088), (-0.0585, -0.0140), (-0.0600, -0.0400), (-0.0560, -0.0490),
            (-0.0470, -0.0530), (-0.0360, -0.0510), (-0.0200, -0.0435), (-0.0020, -0.0335), (0.0180, -0.0230),
            (0.0360, -0.0150), (0.0500, -0.0115)]
    body = L.prism(P + "_b", [(y, z) for y, z in prof], "X", -0.0168, 0.0168, mat=M["bone"])
    pan = []
    ppts = [(-0.0500, -0.0150), (-0.0500, -0.0400), (-0.0440, -0.0455), (-0.0340, -0.0440), (-0.0180, -0.0365),
            (0.0000, -0.0270), (0.0150, -0.0190), (0.0170, -0.0150)]
    for s in (1, -1):
        pan.append(L.prism("_pan", ppts, "X", s * 0.0153, s * 0.03))
    # palm ramp: three grooves across the ramp, perpendicular to it, 1.5 mm deep
    ramp = [(-0.0360, -0.0510), (-0.0200, -0.0435), (-0.0020, -0.0335), (0.0180, -0.0230), (0.0360, -0.0150)]
    for yc in (-0.026, -0.010, 0.006):
        for (y0, z0), (y1, z1) in zip(ramp, ramp[1:]):
            if y0 <= yc <= y1:
                zr = z0 + (z1 - z0) * (yc - y0) / (y1 - y0)
                a = math.atan2(z1 - z0, y1 - y0)
                break
        g = L.boxp("_rib", (-0.0125, -0.0016, -0.0030), (0.0125, 0.0016, 0.0015))
        L.xform(g, Matrix.Translation((0, yc, zr)) @ Matrix.Rotation(a, 4, "X"))
        pan.append(g)
    L.cut(body, pan)
    L.set_mat_by(body, 1, lambda p: abs(p.normal.x) > 0.9 and abs(p.center.x) < 0.0158)
    body.data.materials.append(M["bone_grip"])
    fin(body, 0.0040, 3, smooth_angle=35)
    root = L.merge([cl, body] + bolts, P, col=col)
    sock = L.socket(P + "_SOCKET_LeftHand", (0.0, -0.004, -0.036), root, col)
    objs = [root, sock]
    register(pid, root, objs, {"category": "foregrip", "mount": "under"})
    return objs


def build_grip_stub():
    pid = "grip_stub"
    P = "ATT_" + pid
    col = new_part(pid)
    cl = clamp(P + "_c", "under", -0.026, 0.026, W=0.0155, H=0.0095)
    fin(cl, 0.0012, 2)
    bolts = clamp_bolts("under", [0.010], 0.0155)
    prof = [(0.0255, -0.0088), (-0.0225, -0.0088), (-0.0270, -0.0135), (-0.0280, -0.0270), (-0.0230, -0.0330),
            (-0.0140, -0.0335), (-0.0020, -0.0270), (0.0140, -0.0170), (0.0255, -0.0120)]
    body = L.prism(P + "_b", prof, "X", -0.0168, 0.0168, mat=M["bone"])
    pan = []
    for s in (1, -1):
        pts = [(-0.0215, -0.0140), (-0.0215, -0.0255), (-0.0160, -0.0285), (-0.0080, -0.0260), (0.0060, -0.0175),
               (0.0080, -0.0140)]
        pan.append(L.prism("_pan", pts, "X", s * 0.0153, s * 0.03))
    L.cut(body, pan)
    L.set_mat_by(body, 1, lambda p: abs(p.normal.x) > 0.9 and abs(p.center.x) < 0.0158)
    body.data.materials.append(M["bone_grip"])
    fin(body, 0.0035, 3, smooth_angle=35)
    root = L.merge([cl, body] + bolts, P, col=col)
    # the support hand rides the handguard just behind the stop
    sock = L.socket(P + "_SOCKET_LeftHand", (0.0, 0.050, 0.0035), root, col)
    objs = [root, sock]
    register(pid, root, objs, {"category": "foregrip", "mount": "under"})
    return objs


# ================================================================================================ UGL
UGL_TUBE_Z = -0.0635      # tube axis (local); housing underside at -0.034, tube top flat at -0.0345
UGL_HINGE = Vector((-0.0345, -0.101, UGL_TUBE_Z))


def build_ugl():
    pid = "ugl_launcher"
    P = "ATT_" + pid
    col = new_part(pid)
    cl = clamp(P + "_c", "under", -0.060, 0.060, W=0.0165, H=0.0090)
    fin(cl, 0.0012, 2)
    bolts = clamp_bolts("under", [-0.040, 0.040], 0.0165, lever_side=1, lever_len=0.032, y_lever=0.002)

    # --- housing top shell (cross-section x side-profile intersection)
    sec_h = [(-0.0215, -0.0060), (0.0215, -0.0060), (0.0315, -0.0150), (0.0315, -0.0275), (0.0265, -0.0340),
             (-0.0265, -0.0340), (-0.0315, -0.0275), (-0.0315, -0.0150)]
    hous = L.prism("_h", sec_h, "Y", -0.1125, 0.0800, mat=M["graphite"])
    side_h = [(-0.1000, -0.0050), (-0.1125, -0.0345), (0.0800, -0.0345), (0.0800, -0.0050)]
    L.cut(hous, L.prism("_hs", side_h, "X", -0.05, 0.05), op="INTERSECT")
    # --- receiver / breech block
    sec_r = [(-0.0215, -0.0060), (0.0215, -0.0060), (0.0335, -0.0180), (0.0335, -0.0820), (0.0265, -0.0960),
             (-0.0265, -0.0960), (-0.0335, -0.0820), (-0.0335, -0.0180)]
    recv = L.prism("_r", sec_r, "Y", 0.0745, 0.1700)
    side_r = [(0.0745, -0.0050), (0.0745, -0.0970), (0.1600, -0.0970), (0.1700, -0.0560), (0.1700, -0.0050)]
    L.cut(recv, L.prism("_rs", side_r, "X", -0.05, 0.05), op="INTERSECT")
    # hinge lug (fixed half, shooter's right / -X, front)
    lug = L.prism("_lug", L.crect(0.0075, 0.0110, 0.0035, cx=UGL_HINGE.x, cy=UGL_HINGE.y), "Z", -0.0360, -0.0200)
    L.union(hous, [recv, lug])
    # panel-line grooves along both housing flanks + a vertical split line at the breech
    gro = []
    for s in (1, -1):
        gro.append(L.boxp("_g", (s * 0.0300 - 0.004, -0.0880, -0.0222), (s * 0.0300 + 0.004, 0.0600, -0.0204)))
        gro.append(L.boxp("_g", (s * 0.0320 - 0.004, 0.0940, -0.0800), (s * 0.0320 + 0.004, 0.0960, -0.0200)))
    # dark breech recess (firing-pin face) and the trigger slot
    L.cut(hous, gro)
    fin(hous, 0.0022, 2)
    hous.name = P + "_housing"

    pin = L.cyl("_pin", 0.0046, (UGL_HINGE.x, UGL_HINGE.y, -0.0575), (UGL_HINGE.x, UGL_HINGE.y, -0.0175),
                verts=12, mat=M["gunmetal"])
    fin(pin, 0.0008, 1, smooth_angle=40)
    fpin = L.cyl("_fp", 0.0085, (0, 0.0752, UGL_TUBE_Z), (0, 0.0735, UGL_TUBE_Z), verts=16, mat=M["gunmetal"])
    L.smooth(fpin, 40)

    # --- trigger guard (U under the receiver)
    gout = [(0.0560, -0.0930), (0.0560, -0.1140), (0.0640, -0.1220), (0.1060, -0.1220), (0.1120, -0.1160),
            (0.1120, -0.0930)]
    guard = L.prism("_tg", gout, "X", -0.0065, 0.0065, mat=M["graphite"])
    ghole = [(0.0625, -0.0900), (0.0625, -0.1110), (0.0670, -0.1155), (0.1040, -0.1155), (0.1065, -0.1130),
             (0.1065, -0.0900)]
    L.cut(guard, L.prism("_th", ghole, "X", -0.02, 0.02))
    fin(guard, 0.0018, 2)

    # --- pistol grip (bone) with stipple panels
    gp = [(0.1040, -0.0920), (0.1500, -0.0920), (0.1540, -0.1010), (0.1600, -0.1640), (0.1560, -0.1720),
          (0.1260, -0.1740), (0.1200, -0.1680), (0.1150, -0.1400), (0.1090, -0.1180), (0.1040, -0.1040)]
    grip = L.prism(P + "_grip", gp, "X", -0.0145, 0.0145, mat=M["bone"])
    pan = []
    for s in (1, -1):
        pp = [(0.1170, -0.1040), (0.1450, -0.1040), (0.1500, -0.1580), (0.1290, -0.1600), (0.1230, -0.1300)]
        pan.append(L.prism("_gp", pp, "X", s * 0.0131, s * 0.03))
    L.cut(grip, pan)
    L.set_mat_by(grip, 1, lambda p: abs(p.normal.x) > 0.9 and abs(p.center.x) < 0.0138)
    grip.data.materials.append(M["bone_grip"])
    fin(grip, 0.0035, 3, smooth_angle=35)

    # --- barrel release latch (+X, shooter's left, near the breech) and ambi safety levers
    latch = L.prism("_latch", [(0.0400, -0.0300), (0.0640, -0.0300), (0.0660, -0.0230), (0.0420, -0.0200)], "X",
                    0.0280, 0.0345, mat=M["gunmetal"])
    fin(latch, 0.0007, 1)
    saf = []
    for s in (1, -1):
        sf = L.prism("_saf", [(0.0860, -0.0720), (0.1010, -0.0700), (0.1030, -0.0640), (0.0880, -0.0640)], "X",
                     s * 0.0325, s * 0.0362, mat=M["gunmetal"])
        fin(sf, 0.0006, 1)
        saf.append(sf)

    root = L.merge([cl, hous, pin, fpin, guard, grip, latch] + saf + bolts, P, col=col)

    # --- swinging barrel ("Breech" child): octagonal tube, 45 mm bore, muzzle band, breech ring, hinge knuckle
    r8 = 0.0290
    oct8 = L.crect(r8, r8, r8 - r8 * math.tan(math.radians(22.5)), cx=0.0, cy=UGL_TUBE_Z)
    tube = L.prism("_tube", oct8, "Y", -0.1240, 0.0480, mat=M["gunmetal"])
    band = L.prism("_band", L.crect(0.0308, 0.0308, 0.0308 - 0.0308 * math.tan(math.radians(22.5)), 0.0,
                                    UGL_TUBE_Z), "Y", -0.1385, -0.1220)
    ring = L.prism("_ring", L.crect(0.0312, 0.0312, 0.0312 - 0.0312 * math.tan(math.radians(22.5)), 0.0,
                                    UGL_TUBE_Z), "Y", 0.0460, 0.0740)
    knuck = L.prism("_kn", L.crect(0.0075, 0.0105, 0.0035, cx=UGL_HINGE.x, cy=UGL_HINGE.y), "Z", -0.0560,
                    -0.0365)
    arm = L.boxp("_ka", (UGL_HINGE.x, UGL_HINGE.y - 0.0105, -0.0560), (-0.0200, UGL_HINGE.y + 0.0105, -0.0365))
    # top flat must clear the housing underside (-0.034) by 0.3 mm: trim everything above -0.0343
    L.union(tube, [band, ring, knuck, arm])
    L.cut(tube, L.boxp("_trim", (-0.06, -0.2, -0.0343), (0.06, 0.2, 0.0)))
    # grooves: two rings around the tube
    rings = []
    for yc in (-0.070, -0.050):
        o = L.prism("_rg", L.crect(0.0330, 0.0330, 0.0330 - 0.0330 * math.tan(math.radians(22.5)), 0.0,
                                   UGL_TUBE_Z), "Y", yc - 0.0016, yc + 0.0016)
        i = L.prism("_rgi", L.crect(0.0276, 0.0276, 0.0276 - 0.0276 * math.tan(math.radians(22.5)), 0.0,
                                    UGL_TUBE_Z), "Y", yc - 0.003, yc + 0.003)
        L.cut(o, i)
        rings.append(o)
    L.cut(tube, rings)
    bore = L.cyl("_bore", 0.0225, (0, -0.16, UGL_TUBE_Z), (0, 0.10, UGL_TUBE_Z), verts=32)
    L.cut(tube, bore)
    tube.data.materials.append(M["dark"])

    def inner(p):
        c = p.center
        rv = Vector((c.x, 0, c.z - UGL_TUBE_Z))
        return rv.length < 0.0228 and p.normal.dot(rv.normalized()) < -0.5 if rv.length > 1e-6 else False
    L.set_mat_by(tube, 1, inner)
    fin(tube, 0.0020, 2)
    tube.name = P + "_Breech"
    tube.data.name = tube.name
    bc.link(tube, col)
    # origin at the hinge (vertical pin axis, shooter's right front), parented to the root
    tube.data.transform(Matrix.Translation(-UGL_HINGE))
    tube.parent = root
    tube.location = UGL_HINGE
    tube["hinge_axis"] = "local Z (vertical pin, shooter's right front)"
    tube["open_angle_deg"] = -35.0
    tube["closed_angle_deg"] = 0.0
    tube["note"] = "rotate about local Z by open_angle_deg: the breech end swings out to the shooter's LEFT (+X)"

    # --- trigger (child, origin at pivot)
    tp = [(0.0800, -0.0940), (0.0880, -0.0940), (0.0885, -0.1000), (0.0850, -0.1090), (0.0800, -0.1105),
          (0.0815, -0.1010)]
    trig = L.prism(P + "_Trigger", tp, "X", -0.0032, 0.0032, mat=M["gunmetal"])
    fin(trig, 0.0007, 1)
    bc.link(trig, col)
    piv = Vector((0.0, 0.0840, -0.0950))
    trig.data.transform(Matrix.Translation(-piv))
    trig.parent = root
    trig.location = piv
    trig["pivot_axis"] = "local X"
    trig["pull_angle_deg"] = 12.0

    sock = L.socket(P + "_SOCKET_LeftHand", (0.0, 0.1340, -0.1330), root, col)
    muz = L.socket(P + "_SOCKET_Muzzle", (0.0, -0.1385, UGL_TUBE_Z), tube, col)
    muz.location = Vector((0.0, -0.1385, UGL_TUBE_Z)) - UGL_HINGE
    objs = [root, tube, trig, sock, muz]
    register(pid, root, objs, {"category": "underbarrel", "mount": "under"})
    return objs


# ================================================================================================ bipod
BIPOD_HINGE_Z = -0.030
BIPOD_TOP_HW = 0.0190
BIPOD_SPLAY = 10.0
BIPOD_DEPLOY_EULER_X = -40.0     # leg 50 deg below the rail, pointing forward
BIPOD_SOLE_Z = -0.2175           # foot sole (local). Warden: bore 0.0545 above origin -> bore 0.272 above ground


def bipod_hinge_x():
    return BIPOD_TOP_HW + (abs(BIPOD_HINGE_Z) - 0.008) * math.tan(math.radians(BIPOD_SPLAY))


def build_bipod():
    pid = "bipod"
    P = "ATT_" + pid
    col = new_part(pid)
    cl = clamp(P + "_c", "under", -0.025, 0.025, W=0.0200, H=0.0100)
    fin(cl, 0.0015, 2)
    bolts = clamp_bolts("under", [-0.012], 0.0200, lever_side=1, lever_len=0.036, y_lever=0.004)
    # hinge head: trapezoid (sides lean 10 deg so the legs splay), chamfered
    t = math.tan(math.radians(BIPOD_SPLAY))
    hw_b = BIPOD_TOP_HW + (0.044 - 0.008) * t
    sec = [(-BIPOD_TOP_HW, -0.0080), (BIPOD_TOP_HW, -0.0080), (hw_b, -0.0440), (-hw_b, -0.0440)]
    head = L.prism("_hd", sec, "Y", -0.0185, 0.0185, mat=M["graphite"])
    side = [(-0.0185, -0.0080), (-0.0185, -0.0360), (-0.0100, -0.0440), (0.0130, -0.0440), (0.0185, -0.0390),
            (0.0185, -0.0080)]
    L.cut(head, L.prism("_hs", side, "X", -0.05, 0.05), op="INTERSECT")
    # cant-lock knob at the back
    knob = L.cyl("_kn", 0.0085, (0, 0.0175, -0.0270), (0, 0.0275, -0.0270), verts=10, mat=M["gunmetal"])
    fin(knob, 0.0010, 1, smooth_angle=40)
    fin(head, 0.0020, 2)
    root = L.merge([cl, head, knob] + bolts, P, col=col)

    hx = bipod_hinge_x()

    def leg_matrix(s):
        loc = Vector((s * hx, 0.0, BIPOD_HINGE_Z))
        R = (Matrix.Rotation(math.radians(-s * BIPOD_SPLAY), 4, "Y") @
             Matrix.Rotation(math.radians(BIPOD_DEPLOY_EULER_X), 4, "X"))
        return Matrix.Translation(loc) @ R

    ML = leg_matrix(1)
    AXC = 0.0054                                   # leg axis offset (local X) = middle of the beam thickness
    p0 = ML @ Vector((AXC, 0, 0))
    dz = (ML.to_3x3() @ Vector((0, 0, -1))).z      # z per metre along the leg (-0.754)

    def dist_at(z):                                # distance along the leg axis where it reaches height z
        return (z - p0.z) / dz

    d_end = dist_at(BIPOD_SOLE_Z + 0.0040)         # lower beam end (inside the foot)
    d_mid = dist_at(BIPOD_SOLE_Z + 0.0085)         # foot centre
    LOW_OFF = Matrix.Translation((0, 0, -0.1400))

    # ---- upper leg (+X / L leg, local frame: X = hinge axis = outward face normal, leg along -Z)
    kn = L.cyl("_knk", 0.0115, (0.0004, 0, 0), (0.0104, 0, 0), verts=16, mat=M["graphite"])
    beam = L.loft("_beam", [
        [(x, y, 0.0) for x, y in [(0.0004, -0.0115), (0.0104, -0.0115), (0.0104, 0.0115), (0.0004, 0.0115)]],
        [(x, y, -0.1360) for x, y in [(0.0004, -0.0100), (0.0104, -0.0100), (0.0104, 0.0100), (0.0004, 0.0100)]]])
    L.union(kn, [beam])
    L.cut(kn, L.boxp("_lg", (0.0089, -0.0032, -0.118), (0.0120, 0.0032, -0.024)))   # lightening groove
    fin(kn, 0.0016, 2)
    collar = L.boxp("_col", (-0.0002, -0.0118, -0.1500), (0.0112, 0.0118, -0.1300), mat=M["graphite"])
    fin(collar, 0.0018, 2)
    btn = L.cyl("_btn", 0.0030, (0.0108, 0, -0.1400), (0.0128, 0, -0.1400), verts=10, mat=M["gunmetal"])
    fin(btn, 0.0005, 1, smooth_angle=40)
    pinc = L.cyl("_pc", 0.0058, (0.0100, 0, 0), (0.0132, 0, 0), verts=12, mat=M["gunmetal"])
    fin(pinc, 0.0008, 1, smooth_angle=40)
    upper = L.merge([kn, collar, btn, pinc], P + "_Leg_L")
    bc.link(upper, col)

    # ---- lower telescoping leg (gunmetal) with adjustment notches + ankle boss
    low = L.boxp("_low", (0.0021, -0.0074, -d_end), (0.0087, 0.0074, -0.1200), mat=M["gunmetal"])
    notches = [L.boxp("_n", (0.0011, -0.0090, zc - 0.0011), (0.0097, -0.0060, zc + 0.0011))
               for zc in (-0.160, -0.174, -0.188, -0.202)]
    L.cut(low, notches)
    fin(low, 0.0010, 1)
    ank = L.cyl("_ank", 0.0068, (0.0006, 0, -(d_end - 0.010)), (0.0102, 0, -(d_end - 0.010)), verts=12,
                mat=M["gunmetal"])
    fin(ank, 0.0008, 1, smooth_angle=40)

    # ---- foot: built in mount space (deployed pose) so the sole is level, then moved into the lower-leg frame
    c = ML @ Vector((AXC, 0, -d_mid))
    fx, fy, sole = c.x, c.y, BIPOD_SOLE_Z
    foot_loops = [[(fx + x, fy + y, sole) for x, y in L.crect(0.0170, 0.0230, 0.0070)],
                  [(fx + x, fy + y, sole + 0.0065) for x, y in L.crect(0.0170, 0.0230, 0.0070)],
                  [(fx + x, fy + y + 0.003, sole + 0.0175) for x, y in L.crect(0.0120, 0.0170, 0.0050)]]
    foot = L.loft("_foot", foot_loops, mat=M["rubber"])
    claw = L.loft("_claw", [[(fx + x, fy - 0.0210, sole + z) for x, z in
                             [(-0.010, 0.0), (0.010, 0.0), (0.008, 0.0095), (-0.008, 0.0095)]],
                            [(fx + x, fy - 0.0350, sole + z) for x, z in
                             [(-0.003, 0.0), (0.003, 0.0), (0.002, 0.0022), (-0.002, 0.0022)]]], mat=M["rubber"])
    L.union(foot, [claw])
    tr = [L.boxp("_t", (fx - 0.03, fy + yy - 0.0012, sole - 0.001), (fx + 0.03, fy + yy + 0.0012, sole + 0.0015))
          for yy in (-0.010, 0.0, 0.010)]
    L.cut(foot, tr)
    fin(foot, 0.0016, 2)
    foot.data.transform((ML @ LOW_OFF).inverted())
    low.data.transform(LOW_OFF.inverted())
    ank.data.transform(LOW_OFF.inverted())
    lower = L.merge([low, ank, foot], P + "_LegLower_L")
    bc.link(lower, col)

    upper.parent = root
    upper.matrix_basis = ML
    lower.parent = upper
    lower.matrix_basis = LOW_OFF
    for o in (upper, lower):
        o.matrix_parent_inverse = Matrix.Identity(4)
    upper.rotation_mode = "XYZ"
    upper["hinge_axis"] = "local X (leg lies along local -Z)"
    upper["deploy_angle_deg"] = 50.0
    upper["fold_angle_deg"] = -50.0
    upper["euler_x_deployed_deg"] = BIPOD_DEPLOY_EULER_X
    upper["euler_x_folded_deg"] = BIPOD_DEPLOY_EULER_X - 50.0
    upper["splay_deg"] = BIPOD_SPLAY
    upper["note"] = ("deploy_angle_deg = legs 50 deg below the rail, forward. fold_angle_deg = extra rotation about "
                     "the hinge (local X) that folds the leg forward along -Y under the rail (euler X -40 -> -90).")
    lower["slide_axis"] = "local -Z"
    lower["telescope_min_m"] = 0.0
    lower["telescope_max_m"] = 0.060
    lower["telescope_m"] = 0.0
    # R leg = mirror of the L leg hierarchy
    legR = L.mirror_hierarchy(upper, "_L", "_R", col)
    legR.rotation_mode = "XYZ"
    lowR = [c for c in legR.children][0]
    bpy.context.view_layer.update()
    for o in (upper, legR):
        print(o.name, "euler", [round(math.degrees(a), 2) for a in o.rotation_euler],
              "loc", [round(v, 4) for v in o.location])
    objs = [root, upper, lower, legR, lowR]
    feet = []
    for o in (lower, lowR):
        mw = o.matrix_world
        zs = [(mw @ v.co).z for v in o.data.vertices]
        feet.append(min(zs))
    print("bipod foot sole z", feet)
    register(pid, root, objs, {"category": "underbarrel", "mount": "under", "foot_sole_z": round(min(feet), 4)})
    return objs


# ================================================================================================ laser
def build_laser():
    pid = "laser"
    P = "ATT_laser_R"
    col = new_part("laser_R", "ATT_laser_R")
    f = L.mount_map("side_R")
    cl = L.prism_f("_c", L.clamp_profile(0.0155, 0.0070, 0.0083), f, -0.026, 0.026, mat=M["graphite"])
    fin(cl, 0.0012, 2)
    # cross bolts through the jaws: along Z (side mount)
    bolts = []
    for y in (0.012,):
        bolts.append(L.cyl("_bh", 0.0030, (0.0042, y, 0.0150), (0.0042, y, 0.0176), verts=6, mat=M["gunmetal"]))
        bolts.append(L.cyl("_bn", 0.0027, (0.0042, y, -0.0150), (0.0042, y, -0.0170), verts=10, mat=M["gunmetal"]))
    for b in bolts:
        fin(b, 0.0005, 1, smooth_angle=40)
    # body: angular box sitting beside the rail (toward -X), big chamfers on the outer edges
    sec = [(-0.0050, -0.0150), (-0.0075, -0.0170), (-0.0262, -0.0170), (-0.0340, -0.0092), (-0.0340, 0.0092),
           (-0.0262, 0.0170), (-0.0075, 0.0170), (-0.0050, 0.0150)]
    body = L.prism("_b", sec, "Y", -0.0350, 0.0290, mat=M["graphite"])
    head = L.prism("_hd", inset(sec, -0.0013), "Y", -0.0430, -0.0335)
    L.union(body, [head])
    # front recess panel + split groove behind the head + top activation pad recess
    rec = L.prism("_fr", L.crect(0.0105, 0.0128, 0.0040, cx=-0.0195, cy=0.0), "Y", -0.0450, -0.0412)
    grv = L.prism("_gv", inset(sec, -0.003), "Y", -0.0336, -0.0322)
    grv_in = L.prism("_gvi", inset(sec, 0.0012), "Y", -0.0340, -0.0318)
    L.cut(grv, grv_in)
    L.cut(body, [rec, grv])
    fin(body, 0.0016, 2)
    # emitter ring (gunmetal) + red lens (separate child, emissive)
    ez = 0.0060
    ex = -0.0195
    ring = L.lathe_y("_er", [(0.0029, -0.0446), (0.0050, -0.0446), (0.0050, -0.0405), (0.0029, -0.0405),
                             (0.0029, -0.0446)], steps=16, center=(ex, ez), mat=M["gunmetal"])
    L.smooth(ring, 40)
    irw = L.prism("_ir", L.crect(0.0082, 0.0042, 0.0016, cx=ex, cy=-0.0062), "Y", -0.0418, -0.0405,
                  mat=M["ir"])
    fin(irw, 0.0005, 1)
    # outer face: rotary mode selector + windage screw; top: elevation screw + activation pad
    sel = L.cyl("_sel", 0.0062, (-0.0336, 0.0080, 0.0000), (-0.0372, 0.0080, 0.0000), verts=12, mat=M["gunmetal"])
    fin(sel, 0.0008, 1, smooth_angle=40)
    fin_ = L.boxp("_self", (-0.0386, 0.0030, -0.0012), (-0.0360, 0.0130, 0.0012), mat=M["gunmetal"])
    fin(fin_, 0.0005, 1)
    scr = []
    for p0, p1 in (((-0.0336, -0.0150, 0.0), (-0.0352, -0.0150, 0.0)), ((-0.0200, -0.0150, 0.0166),
                                                                            (-0.0200, -0.0150, 0.0184))):
        sc = L.cyl("_scr", 0.0034, p0, p1, verts=10, mat=M["gunmetal"])
        fin(sc, 0.0005, 1, smooth_angle=40)
        scr.append(sc)
    pad = L.prism("_pad", L.crect(0.0070, 0.0080, 0.0028, cx=-0.0170, cy=0.0160), "Z", 0.0160, 0.0186,
                  mat=M["rubber"])
    fin(pad, 0.0009, 2)
    rear = L.prism("_rp", L.crect(0.0070, 0.0085, 0.0030, cx=-0.0195, cy=0.0), "Y", 0.0280, 0.0312,
                   mat=M["rubber"])
    fin(rear, 0.0009, 2)
    root = L.merge([cl, body, ring, irw, sel, fin_, pad, rear] + scr + bolts, P, col=col)
    lens = L.cyl(P + "_Emitter", 0.0031, (ex, -0.0438, ez), (ex, -0.0420, ez), verts=12, mat=M["laser"])
    L.smooth(lens, 40)
    bc.link(lens, col)
    lens.parent = root
    beam = L.socket(P + "_SOCKET_Beam", (ex, -0.0440, ez), root, col)
    objs = [root, lens, beam]
    register("laser_R", root, objs, {"category": "side_rail", "mount": "side"})
    return objs


# ================================================================================================ flashlight
def build_flashlight():
    P = "ATT_flashlight_R"
    col = new_part("flashlight_R", "ATT_flashlight_R")
    f = L.mount_map("side_R")
    AX, AZ = -0.0265, 0.0
    cl = L.prism_f("_c", L.clamp_profile(0.0155, 0.0060, 0.0083), f, -0.022, 0.022, mat=M["graphite"])
    fin(cl, 0.0012, 2)
    bolts = []
    bolts.append(L.cyl("_bh", 0.0030, (0.0042, 0.012, 0.0150), (0.0042, 0.012, 0.0176), verts=6, mat=M["gunmetal"]))
    bolts.append(L.cyl("_bn", 0.0027, (0.0042, 0.012, -0.0150), (0.0042, 0.012, -0.0170), verts=10,
                       mat=M["gunmetal"]))
    for b in bolts:
        fin(b, 0.0005, 1, smooth_angle=40)
    arm = L.prism("_arm", [(-0.0045, -0.0115), (-0.0205, -0.0085), (-0.0205, 0.0085), (-0.0045, 0.0115)], "Y",
                  -0.0200, 0.0200, mat=M["graphite"])
    fin(arm, 0.0015, 2)
    # body lathe (graphite): tailcap, grooves, body, flared head
    prof = [(0.0, 0.0540), (0.0098, 0.0540), (0.0128, 0.0515), (0.0128, 0.0420), (0.0119, 0.0412),
            (0.0119, 0.0398), (0.0125, 0.0390), (0.0125, -0.0180), (0.0119, -0.0188), (0.0119, -0.0204),
            (0.0125, -0.0212), (0.0125, -0.0240), (0.0168, -0.0330), (0.0168, -0.0490), (0.0, -0.0490)]
    body = L.lathe_y("_body", prof, steps=24, center=(AX, AZ), mat=M["graphite"])
    L.smooth(body, 40)
    # tail switch (rubber)
    tail = L.lathe_y("_tail", [(0.0, 0.0600), (0.0050, 0.0600), (0.0066, 0.0585), (0.0066, 0.0530), (0.0, 0.0530)],
                     steps=16, center=(AX, AZ), mat=M["rubber"])
    L.smooth(tail, 40)
    # knurled bezel: crenellated 64-gon band + chamfered front ring (gunmetal)
    pts = []
    N = 16
    for i in range(N):
        for k, (fa, rr) in enumerate(((0.00, 0.0186), (0.30, 0.0186), (0.50, 0.0172), (0.80, 0.0172))):
            a = 2 * math.pi * (i + fa) / N
            pts.append((AX + rr * math.cos(a), AZ + rr * math.sin(a)))
    knurl = L.prism("_kn", pts, "Y", -0.0600, -0.0470, mat=M["gunmetal"])
    L.smooth(knurl, 20)
    front = L.lathe_y("_fr", [(0.0136, -0.0598), (0.0182, -0.0598), (0.0182, -0.0610), (0.0170, -0.0624),
                              (0.0140, -0.0624), (0.0136, -0.0614), (0.0136, -0.0598)], steps=24, center=(AX, AZ),
                      mat=M["gunmetal"])
    L.smooth(front, 40)
    root = L.merge([cl, arm, body, tail, knurl, front] + bolts, P, col=col)
    lens = L.cyl(P + "_Lens", 0.0141, (AX, -0.0612, AZ), (AX, -0.0600, AZ), verts=24, mat=M["lens"])
    L.smooth(lens, 40)
    bc.link(lens, col)
    lens.parent = root
    beam = L.socket(P + "_SOCKET_Beam", (AX, -0.0625, AZ), root, col)
    objs = [root, lens, beam]
    register("flashlight_R", root, objs, {"category": "side_rail", "mount": "side"})
    return objs


# ================================================================================================ shield
SH_Y0, SH_Y1 = -0.0400, -0.0260     # plate front / back (centre panel)
SH_YM = (SH_Y0 + SH_Y1) / 2
SH_FOLD_X = 0.100
SH_FOLD_DEG = 20.0
SH_OUTLINE = [(-0.090, -0.100), (0.090, -0.100), (0.160, -0.040), (0.160, 0.118), (0.130, 0.160),
              (-0.130, 0.160), (-0.160, 0.118), (-0.160, -0.040)]
SH_VIEW = L.crect(0.080, 0.035, 0.014, 0.0, 0.065)       # glass opening z 0.030 .. 0.100
SH_PORT = L.crect(0.078, 0.028, 0.012, 0.0, -0.036)      # barrel / light port z -0.064 .. -0.008


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
    col = new_part(pid)
    plate = L.prism("_plate", SH_OUTLINE, "Y", SH_Y0, SH_Y1, mat=M["graphite"])
    adds = []
    for poly, w in ((SH_VIEW, 0.0070), (SH_PORT, 0.0060)):
        adds.append(L.prism("_ff", inset(poly, -w), "Y", SH_Y0 - 0.0028, SH_Y0 + 0.002))
        adds.append(L.prism("_bf", inset(poly, -(w - 0.0015)), "Y", SH_Y1 - 0.002, SH_Y1 + 0.0035))
    # back stiffeners: horizontal rib under the window, vertical wing ribs, mount boss
    adds.append(L.boxp("_rib", (-0.146, SH_Y1 - 0.002, 0.0060), (0.146, SH_Y1 + 0.0055, 0.0170)))
    for s in (1, -1):
        adds.append(L.boxp("_vr", (s * 0.134 - 0.005, SH_Y1 - 0.002, -0.050), (s * 0.134 + 0.005, SH_Y1 + 0.0055,
                                                                                 0.128)))
    adds.append(L.boxp("_boss", (-0.042, SH_Y1 - 0.002, -0.0010), (0.042, SH_Y1 + 0.0070, 0.0255)))
    L.union(plate, adds)
    # front panel-line groove following the outline
    g = L.prism("_g", inset(SH_OUTLINE, 0.0150), "Y", SH_Y0 - 0.003, SH_Y0 + 0.0016)
    L.cut(g, L.prism("_gi", inset(SH_OUTLINE, 0.0180), "Y", SH_Y0 - 0.004, SH_Y0 + 0.003))
    # diagonal accent grooves on the upper wings
    chev = []
    for s in (1, -1):
        c = L.prism("_cv", [(s * 0.110, 0.058), (s * 0.116, 0.058), (s * 0.146, 0.098), (s * 0.140, 0.098)],
                    "Y", SH_Y0 - 0.003, SH_Y0 + 0.0016)
        chev.append(c)
    L.cut(plate, [g] + chev)
    L.cut(plate, [L.prism("_o1", SH_VIEW, "Y", -0.08, 0.02), L.prism("_o2", SH_PORT, "Y", -0.08, 0.02)])
    bend_wings(plate)
    fin(plate, 0.0018, 2, smooth_angle=15)
    # bolts (hex) on the front face, bent with the plate
    bl = []
    for x, z in ((0.118, 0.132), (-0.118, 0.132), (0.136, 0.020), (-0.136, 0.020), (0.124, -0.036),
                 (-0.124, -0.036), (0.050, 0.132), (-0.050, 0.132)):
        bl.append(L.cyl("_bolt", 0.0042, (x, SH_Y0 + 0.001, z), (x, SH_Y0 - 0.0028, z), verts=6))
    bolts = L.join_raw(bl, "_bolts")
    bolts.data.materials.append(M["gunmetal"])
    bend_wings(bolts)
    fin(bolts, 0.0008, 1, smooth_angle=40)
    # arm (from the clamp up/forward to the boss) + clamp on the top rail
    arm = L.prism("_arm", [(SH_Y1 + 0.0050, 0.0015), (SH_Y1 + 0.0050, 0.0250), (-0.0120, 0.0250),
                           (0.0080, 0.0105), (0.0080, 0.0060), (-0.0160, 0.0060), (-0.0160, 0.0015)],
                  "X", -0.0140, 0.0140, mat=M["graphite"])
    fin(arm, 0.0020, 2)
    gus = []
    for s in (1, -1):
        gp = L.prism("_gus", [(SH_Y1 + 0.0055, 0.0035), (SH_Y1 + 0.0055, 0.0210), (-0.0080, 0.0035)], "X",
                     s * 0.0300, s * 0.0230, mat=M["graphite"])
        fin(gp, 0.0012, 1)
        gus.append(gp)
    cl = clamp("_c", "top", -0.0160, 0.0340, W=0.0165, H=0.0100)
    fin(cl, 0.0013, 2)
    cb = clamp_bolts("top", [0.0000, 0.0240], 0.0165, lever_side=1, lever_len=0.030, y_lever=0.012)
    root = L.merge([plate, bolts, arm, cl] + gus + cb, P, col=col)
    glass = L.prism(P + "_Glass", inset(SH_VIEW, -0.0030), "Y", SH_Y0 + 0.0024, SH_Y1 - 0.0024, mat=M["glass"])
    fin(glass, 0.0010, 1)
    bc.link(glass, col)
    glass.parent = root
    objs = [root, glass]
    register(pid, root, objs, {"category": "shield", "mount": "top",
                               "glass_z": [0.030, 0.100], "plate_z": [-0.100, 0.160], "plate_x": [-0.160, 0.160]})
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
    L.finish(ob, 0.0007, 1)
    return ob


def build_proxy_mako():
    col = bc.collection("_Proxy_Mako")
    pm, pd = M["proxy"], M["proxy_dark"]
    up = bc.profile_extrude("_PX_Upper", [(-0.168, 0.024), (-0.168, 0.068), (-0.162, 0.0745), (0.022, 0.0745),
                                          (0.030, 0.066), (0.030, 0.046), (0.014, 0.046), (0.008, 0.024)], 0.032,
                            col=col, mat=pm, bevel=0.002)
    lo = bc.profile_extrude("_PX_Lower", [(-0.160, 0.024), (-0.162, -0.026), (-0.168, -0.032), (-0.168, -0.038),
                                          (-0.080, -0.038), (-0.078, -0.030), (-0.080, -0.006), (-0.072, 0.000),
                                          (0.018, 0.000), (0.030, 0.008), (0.036, 0.020), (0.036, 0.046),
                                          (0.014, 0.046), (0.008, 0.024)], 0.030, col=col, mat=pm, bevel=0.002)
    hg_sec = [(-0.012, 0.026), (0.012, 0.026), (0.022, 0.0355), (0.022, 0.0645), (0.012, 0.0745), (-0.012, 0.0745),
              (-0.022, 0.0645), (-0.022, 0.0355)]
    hg = L.prism("_PX_Handguard", hg_sec, "Y", -0.500, -0.168, col=col, mat=pm)
    slots = []
    for yc in (-0.200, -0.245, -0.290, -0.335, -0.380):
        slots.append(L.boxp("_sl", (-0.03, yc - 0.016, 0.0465), (0.03, yc + 0.016, 0.0535)))
    L.cut(hg, slots)
    L.finish(hg, 0.0015, 1)
    rail("_PX_RailTop", "top", -0.498, 0.022, (0, 0, 0.084), col, pm)
    rail("_PX_RailBottom", "under", -0.430, -0.290, (0, 0, 0.0165), col, pm)
    rail("_PX_RailSide_R", "side_R", -0.470, -0.410, (-0.0315, 0, 0.050), col, pm)
    rail("_PX_RailSide_L", "side_L", -0.470, -0.410, (0.0315, 0, 0.050), col, pm)
    bar = L.cyl("_PX_Barrel", 0.0095, (0, -0.519, 0.050), (0, -0.170, 0.050), verts=20, col=col, mat=pd)
    L.smooth(bar, 40)
    hid = L.cyl("_PX_Hider", 0.0128, (0, -0.565, 0.050), (0, -0.517, 0.050), verts=20, col=col, mat=pd)
    cuts = []
    for k in range(4):
        c = L.boxp("_hs", (-0.003, -0.560, 0.03), (0.003, -0.530, 0.07))
        L.xform(c, L.rot("Y", 45 * k, (0, 0, 0.050)))
        cuts.append(c)
    L.cut(hid, cuts)
    L.finish(hid, 0.0012, 1, smooth_angle=40)
    bc.profile_extrude("_PX_Grip", [(-0.020, 0.002), (0.022, 0.002), (0.030, 0.008), (0.035, 0.000), (0.044, -0.030),
                                    (0.054, -0.062), (0.066, -0.100), (0.064, -0.108), (0.026, -0.111),
                                    (0.021, -0.104), (0.008, -0.064), (-0.004, -0.034), (-0.020, -0.006)], 0.030,
                       col=col, mat=pm, bevel=0.003)
    bc.profile_extrude("_PX_Mag", [(-0.152, 0.012), (-0.152, -0.020), (-0.1532, -0.0494), (-0.1567, -0.0786),
                                   (-0.1626, -0.1075), (-0.1707, -0.1358), (-0.1745, -0.1345), (-0.1783, -0.1459),
                                   (-0.1099, -0.1686), (-0.1061, -0.1572), (-0.1099, -0.1559), (-0.1004, -0.1227),
                                   (-0.0935, -0.0888), (-0.0894, -0.0545), (-0.088, -0.020), (-0.088, 0.012)],
                       0.025, col=col, mat=pm, bevel=0.002)
    tb = L.cyl("_PX_Tube", 0.016, (0, 0.030, 0.050), (0, 0.215, 0.050), verts=20, col=col, mat=pd)
    L.smooth(tb, 40)
    bc.profile_extrude("_PX_Stock", [(0.098, 0.034), (0.098, 0.064), (0.110, 0.074), (0.136, 0.078), (0.262, 0.078),
                                     (0.262, -0.056), (0.240, -0.056), (0.164, 0.020), (0.150, 0.025),
                                     (0.106, 0.026)], 0.034, col=col, mat=pm, bevel=0.003)
    # proxy holo optic on the optic socket (sight line = rail top + 0.032)
    op = bc.profile_extrude("_PX_Optic", [(-0.040 - 0.085, 0.084), (0.036 - 0.085, 0.084),
                                          (0.036 - 0.085, 0.100), (0.032 - 0.085, 0.136), (-0.085, 0.138),
                                          (-0.032 - 0.085, 0.130), (-0.040 - 0.085, 0.106)], 0.036, col=col, mat=pd)
    L.cut(op, L.prism("_ow", L.crect(0.013, 0.012, 0.004, 0.0, 0.116), "Y", -0.2, 0.0))
    L.finish(op, 0.002, 1)
    socks = {"Optic": (0, -0.085, 0.084), "Under": (0, -0.360, 0.0165), "Side_R": (-0.0315, -0.440, 0.050),
             "Side_L": (0.0315, -0.440, 0.050), "Shield": (0, -0.480, 0.084), "Muzzle": (0, -0.565, 0.050),
             "LeftHand": (0, -0.330, 0.020)}
    for k, v in socks.items():
        L.socket("_PX_SOCKET_" + k, v, None, col)
    return col, socks


def build_proxy_warden():
    col = bc.collection("_Proxy_Warden")
    pm, pd = M["proxy"], M["proxy_dark"]
    hg = bc.box("_PW_Handguard", (0.072, 0.390, 0.098), loc=(0, -0.495, 0.079), col=col, mat=pm, bevel=0.012,
                segments=1)
    slots = []
    for yc in (-0.370, -0.445, -0.520, -0.595):
        slots.append(L.boxp("_sl", (-0.05, yc - 0.0275, 0.074), (0.05, yc + 0.0275, 0.094)))
    bc.apply_modifiers(hg)
    L.cut(hg, slots)
    rail("_PW_RailTop", "top", -0.690, 0.078, (0, 0, 0.1375), col, pm)
    rail("_PW_RailBottom", "under", -0.650, -0.540, (0, 0, 0.0205), col, pm)
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
    mono = L.cyl("_PW_Monopod", 0.010, (0, 0.205, -0.110), (0, 0.205, -0.198), verts=12, col=col, mat=pd, r2=0.002)
    L.smooth(mono, 40)
    sc = L.lathe_y("_PW_Scope", [(0.0, 0.065), (0.020, 0.065), (0.025, 0.060), (0.025, 0.012), (0.0185, -0.012),
                                 (0.0185, -0.165), (0.034, -0.212), (0.034, -0.300), (0.0, -0.300)], steps=24,
                   center=(0, 0.178), col=col, mat=pd)
    L.smooth(sc, 40)
    for yy in (-0.020, -0.140):
        bc.box("_PW_Ring", (0.034, 0.024, 0.040), loc=(0, yy, 0.1575), col=col, mat=pd, bevel=0.003, segments=1)
    gr = bc.box("_PW_Ground", (0.9, 1.9, 0.004), loc=(0, -0.42, -0.197 - 0.002), col=col, mat=M["ground"])
    socks = {"Under": (0, -0.600, 0.0205), "Side_R": (-0.0455, -0.645, 0.079), "Side_L": (0.0455, -0.645, 0.079),
             "Optic": (0, -0.080, 0.1375), "Muzzle": (0, -1.100, 0.075)}
    for k, v in socks.items():
        L.socket("_PW_SOCKET_" + k, v, None, col)
    return col, socks


# ================================================================================================ main
def main():
    bc.reset_scene()
    scene = bpy.context.scene
    make_materials()
    parts = {}
    parts["grip_vertical"] = build_grip_vertical()
    parts["grip_angled"] = build_grip_angled()
    parts["grip_stub"] = build_grip_stub()
    parts["ugl_launcher"] = build_ugl()
    parts["bipod"] = build_bipod()
    parts["laser_R"] = build_laser()
    parts["flashlight_R"] = build_flashlight()
    parts["shield_front"] = build_shield()
    # _L variants: mirror the whole hierarchy across X
    for base in ("laser", "flashlight"):
        src = parts[base + "_R"][0]
        col = bc.collection(f"ATT_{base}_L")
        rootL = L.mirror_hierarchy(src, "_R", "_L", col)
        objs = L.hierarchy(rootL)
        for o in objs:
            if o.type == "MESH":
                bad, vol = L.check_normals(o)
                print(f"mirror check {o.name}: bad corner normals={bad} signed volume={vol:.3e}")
        parts[base + "_L"] = objs
        register(base + "_L", rootL, objs, {"category": "side_rail", "mount": "side"})

    # UVs (world-scale box projection) on every part mesh
    for pid, objs in parts.items():
        for o in objs:
            if o.type == "MESH":
                box_uv(o, 10.0)

    pm_col, mako_socks = build_proxy_mako()
    pw_col, warden_socks = build_proxy_warden()
    for o in list(pm_col.objects) + list(pw_col.objects):
        if o.type == "MESH" and not o.data.uv_layers:
            box_uv(o, 10.0)

    # ---------------------------------------------------------------- exports (each part at its own origin)
    catalog = []
    socket_for = {"grip_vertical": "Under", "grip_angled": "Under", "grip_stub": "Under", "ugl_launcher": "Under",
                  "bipod": "Under", "laser_R": "Side_R", "laser_L": "Side_L", "flashlight_R": "Side_R",
                  "flashlight_L": "Side_L", "shield_front": "Shield"}
    compat = {"grip_vertical": ["MAKO", "WARDEN"], "grip_angled": ["MAKO", "WARDEN"], "grip_stub": ["MAKO", "WARDEN"],
              "ugl_launcher": ["MAKO"], "bipod": ["WARDEN"], "laser_R": ["MAKO", "WARDEN"],
              "laser_L": ["MAKO", "WARDEN"], "flashlight_R": ["MAKO", "WARDEN"], "flashlight_L": ["MAKO", "WARDEN"],
              "shield_front": ["MAKO"]}
    for pid, objs in parts.items():
        base = os.path.join(HERE, "ATT_" + pid)
        L.export_part(base, objs)
        st = STATS[pid]
        socks = [o.name for o in objs if o.type == "EMPTY"]
        moving = {o.name: {k: o[k] for k in o.keys() if not k.startswith("_")}
                  for o in objs if o.type == "MESH" and o.parent is not None and len(o.keys())}
        catalog.append({
            "id": "ATT_" + pid, "category": st["category"], "mount": st["mount"],
            "file": f"assets/weapons/attachments/tactical/ATT_{pid}.glb",
            "fbx": f"assets/weapons/attachments/tactical/ATT_{pid}.fbx",
            "sockets_accepted": ["_SOCKET_" + socket_for[pid]],
            "compatible_weapons": compat[pid], "tris": st["tris"], "objects": st["objects"],
            "child_sockets": socks, "moving_parts": moving,
            "origin": {"under": "centre of clamp contact on the rail BOTTOM surface (part hangs -Z)",
                       "top": "centre of clamp contact on the rail TOP surface",
                       "side": "centre of clamp contact on the rail outer face (part sticks out sideways)"}[st["mount"]],
        })
        for k in ("foot_sole_z", "glass_z", "plate_z", "plate_x"):
            if k in st:
                catalog[-1][k] = st[k]
    with open(os.path.join(HERE, "catalog.json"), "w") as fh:
        json.dump({"prefix": "ATT", "set": "tactical / underbarrel / shield",
                   "units": "metres, Blender axes (Z up, muzzle -Y); shooter's right = -X",
                   "rail_standard": {"top_width": L.RAIL_W, "height": L.RAIL_H, "slot_pitch": L.RAIL_PITCH},
                   "parts": catalog,
                   "test_sockets": {"MAKO": mako_socks, "WARDEN": warden_socks}}, fh, indent=2)

    # ---------------------------------------------------------------- TestFit scene (instances on the proxies)
    fit = bpy.data.scenes.new("TestFit")
    fit.collection.children.link(pm_col)
    fit.collection.children.link(pw_col)
    tf = bpy.data.collections.new("_TestFit_Instances")
    fit.collection.children.link(tf)
    placements = [("ATT_ugl_launcher", (0, -0.360, 0.0165)), ("ATT_laser_R", (-0.0315, -0.440, 0.050)),
                  ("ATT_flashlight_L", (0.0315, -0.440, 0.050)), ("ATT_shield_front", (0, -0.480, 0.084)),
                  ("ATT_bipod", (0, -0.600, 0.0205))]
    for cname, loc in placements:
        e = bpy.data.objects.new("_inst_" + cname, None)
        e.instance_type = "COLLECTION"
        e.instance_collection = bpy.data.collections[cname]
        e.location = loc
        tf.objects.link(e)
    # main scene: proxies excluded from the view layer (parts only, each in its own collection at the origin)
    vl = scene.view_layers[0]
    for name in ("_Proxy_Mako", "_Proxy_Warden"):
        vl.layer_collection.children[name].exclude = True
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "tactical.blend"), compress=True)
    print("saved tactical.blend")
    print("STATS", json.dumps({k: v["tris"] for k, v in STATS.items()}))


main()
