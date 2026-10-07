"""Part builders for the HALO kit: core arcs, weight bands, pips, power cell, shards, pickup cores.

Every arc/band object has its origin at the halo centre.  Material slots:
  arcs   : 0 = glass (swap per tier / unlit), 1 = graphite
  bands  : 0 = graphite, 1 = gunmetal (bolts)
  cell   : 0 = glass (tier / status colour), 1 = graphite
  pickup : 0 = window glass (tier), 1 = graphite, 2 = bone
"""
import math

import bmesh
from mathutils import Matrix, Vector

from halo_lib import (D, MB, ZONES, add_glyph, arc_angles, circ, ellipse, frame_at, hex_angles, hexs,
                      rounded_rect, HEX_CORNERS)

GAP = 0.7          # deg, half-gap between arcs (=> ~4 mm seam)

# ------------------------------------------------------------------------------------------------ cores
# Ring centre-line distances (apothem for the hexagonal Bulwark, radius for the others)
BUL_A = 0.150
MEN_RI, MEN_RO = 0.143, 0.177
VOLT_R = 0.160
PHASE_R = 0.160
PHASE_GAP = 15.0   # half-angle of the Phase gap at the back (deg)

# ring envelope per core: inner / outer distance and bottom z (the weight band stacks under + outside it)
RING_IN = {"Bulwark": BUL_A - 0.0185, "Mender": MEN_RI - 0.0055, "Volt": VOLT_R - 0.0125, "Phase": PHASE_R - 0.0098}
RING_OUT = {"Bulwark": BUL_A + 0.0195, "Mender": MEN_RO + 0.0055, "Volt": VOLT_R + 0.0135,
            "Phase": PHASE_R + 0.0098}
RING_BOT = {"Bulwark": -0.0145, "Mender": -0.0060, "Volt": -0.0115, "Phase": -0.0040}
SHAPE = {"Bulwark": hexs, "Mender": circ, "Volt": circ, "Phase": circ}


def _angles(core, a0, a1, step=4.0):
    return hex_angles(a0, a1) if core == "Bulwark" else arc_angles(a0, a1, step)


def _plate_and_glyph(mb, core, zone, a, d0, d1, z0, z1, span=5.0):
    """Graphite zone plate on top of the arc + the raised glass glyph on it."""
    shape = SHAPE[core]
    prof = rounded_rect(d0, d1, z0, z1, 0.0008, 1)
    mb.sweep(shape, prof, _angles(core, a - span, a + span, span), mat=1)
    add_glyph(mb, shape, D(a), (d0 + d1) / 2, z1, zone, mat=0)


def _ticks(mb, core, c, offsets, d0, d1, z0, z1, width=0.7):
    """Thin graphite bars across the glass top: reads as segmented energy cells (tech, not a neon tube)."""
    shape = SHAPE[core]
    prof = rounded_rect(d0, d1, z0, z1, 0.0004, 1)
    for off in offsets:
        a = c + off
        mb.sweep(shape, prof, _angles(core, a - width / 2, a + width / 2, width), mat=1)


def arc_bulwark(mb, zone):
    c = ZONES[zone]
    A = BUL_A
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    # dark carrier tray (lower half) + faceted glass inlay (top + big outward facet)
    tray = [(A - 0.0175, -0.004), (A - 0.0175, -0.0095), (A - 0.0135, -0.0135), (A + 0.0145, -0.0135),
            (A + 0.0180, -0.0100), (A + 0.0180, -0.0058)]
    glass = [(A - 0.0125, -0.0065), (A + 0.0170, -0.0065), (A + 0.0170, 0.0060), (A + 0.0110, 0.0130),
             (A - 0.0125, 0.0130)]
    lip = rounded_rect(A - 0.0175, A - 0.0122, -0.010, 0.0138, 0.0012, 1)   # dark inner frame line
    clamp = [(A - 0.0185, -0.0145), (A + 0.0195, -0.0145), (A + 0.0195, 0.0075), (A + 0.0125, 0.0150),
             (A - 0.0105, 0.0150), (A - 0.0185, 0.0085)]
    mb.sweep(hexs, glass, hex_angles(a0, a1), mat=0)
    mb.sweep(hexs, tray, hex_angles(a0, a1), mat=1)
    mb.sweep(hexs, lip, hex_angles(a0, a1), mat=1)
    # segment ticks on the glass, kept clear of the hex corners and the zone plate
    offs = [o for o in (-34.0, -24.0, -14.0, 14.0, 24.0, 34.0)
            if min(abs(((c + o) - k + 180) % 360 - 180) for k in HEX_CORNERS) > 2.5]
    _ticks(mb, "Bulwark", c, offs, A - 0.0128, A + 0.0112, 0.0122, 0.0141, width=0.8)
    _ticks(mb, "Bulwark", c, offs, A + 0.0158, A + 0.0182, -0.0062, 0.0064, width=0.8)
    mb.sweep(hexs, clamp, hex_angles(a0, a0 + 4.0), mat=1)
    mb.sweep(hexs, clamp, hex_angles(a1 - 4.0, a1), mat=1)
    _plate_and_glyph(mb, "Bulwark", zone, c, A - 0.0075, A + 0.0090, 0.0125, 0.0150, span=5.5)


def arc_mender(mb, zone):
    c = ZONES[zone]
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    angs = arc_angles(a0, a1, 5.5)
    for R in (MEN_RI, MEN_RO):
        mb.sweep(circ, rounded_rect(R - 0.0042, R + 0.0042, -0.0010, 0.0068, 0.0022, 1), angs, mat=0)
        mb.sweep(circ, [(R - 0.0052, 0.0005), (R - 0.0052, -0.004), (R - 0.0032, -0.0058), (R + 0.0032, -0.0058),
                        (R + 0.0052, -0.004), (R + 0.0052, 0.0005)], angs, mat=1)
    bridge = rounded_rect(MEN_RI - 0.0055, MEN_RO + 0.0055, -0.0060, 0.0040, 0.0015, 1)
    mb.sweep(circ, bridge, arc_angles(a0, a0 + 2.6, 2.6), mat=1)
    mb.sweep(circ, bridge, arc_angles(a1 - 2.6, a1, 2.6), mat=1)
    # thin secondary rungs (tech ladder feel)
    rung = rounded_rect(MEN_RI + 0.002, MEN_RO - 0.002, -0.0035, 0.0012, 0.0008, 1)
    for off in (-24.0, 24.0):
        mb.sweep(circ, rung, arc_angles(c + off - 1.0, c + off + 1.0, 2.0), mat=1)
    _plate_and_glyph(mb, "Mender", zone, c, MEN_RI + 0.0025, MEN_RO - 0.0025, -0.0005, 0.0036, span=4.2)


def arc_volt(mb, zone):
    c = ZONES[zone]
    R = VOLT_R
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    angs = arc_angles(a0, a1, 5.0)
    glass = [(R - 0.0080, -0.0060), (R + 0.0110, -0.0060), (R + 0.0110, 0.0040), (R + 0.0070, 0.0090),
             (R - 0.0080, 0.0090)]
    lip = rounded_rect(R - 0.0120, R - 0.0078, -0.008, 0.0098, 0.001, 1)
    tray = [(R - 0.0115, -0.004), (R - 0.0115, -0.0080), (R - 0.0085, -0.0105), (R + 0.0095, -0.0105),
            (R + 0.0125, -0.0080), (R + 0.0125, -0.0052)]
    clamp = [(R - 0.0125, -0.0115), (R + 0.0135, -0.0115), (R + 0.0135, 0.0050), (R + 0.0090, 0.0105),
             (R - 0.0075, 0.0105), (R - 0.0125, 0.0065)]
    mb.sweep(circ, glass, angs, mat=0)
    mb.sweep(circ, tray, angs, mat=1)
    mb.sweep(circ, lip, angs, mat=1)
    _ticks(mb, "Volt", c, (-36.0, -10.5, 10.5, 36.0), R + 0.0100, R + 0.0124, -0.0056, 0.0042, width=0.8)
    mb.sweep(circ, clamp, arc_angles(a0, a0 + 3.5, 3.5), mat=1)
    mb.sweep(circ, clamp, arc_angles(a1 - 3.5, a1, 3.5), mat=1)
    # sawtooth teeth (lean counter-clockwise = the "spin" direction), glass blade in a graphite collar
    tooth = [(-0.021, 0.004), (0.012, 0.004), (0.012, 0.027), (0.0085, 0.041), (0.0025, 0.041)]
    for off in (-22.5, 22.5):
        a = D(c + off)
        o, t, n, up = frame_at(circ, a, R, 0.0)
        mb.prism(tooth, o, t, up, n, -0.0045, 0.0060, mat=0)
        cap = [(-0.0005, 0.0335), (0.0128, 0.0335), (0.0128, 0.0285), (0.0090, 0.0435), (0.0015, 0.0435)]
        mb.prism(cap, o, t, up, n, -0.0055, 0.0070, mat=1)
        collar = rounded_rect(R - 0.0075, R + 0.0120, 0.006, 0.0135, 0.0015, 1)
        mb.sweep(circ, collar, arc_angles(c + off - 8.4, c + off + 5.4, 4.6), mat=1)
    _plate_and_glyph(mb, "Volt", zone, c, R - 0.0065, R + 0.0075, 0.0085, 0.0108, span=5.0)


def arc_phase(mb, zone):
    c = ZONES[zone]
    R = PHASE_R
    lens = ellipse(R, 0.003, 0.0085, 0.0055, 12)
    collar = ellipse(R, 0.003, 0.0098, 0.0068, 12)
    keel = [(R - 0.0050, 0.0), (R + 0.0050, 0.0), (R + 0.0035, -0.004), (R - 0.0035, -0.004)]
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    pieces = [(a0, a1)]
    if zone == "Torso":  # gap opposite the front
        pieces = [(a0, c - PHASE_GAP), (c + PHASE_GAP, a1)]
    for p0, p1 in pieces:
        mb.sweep(circ, lens, arc_angles(p0, p1, 5.0), mat=0)
        mb.sweep(circ, keel, arc_angles(p0, p1, 5.0), mat=1)
    # seam collars at the arc ends
    mb.sweep(circ, collar, arc_angles(a0, a0 + 1.8, 1.8), mat=1)
    mb.sweep(circ, collar, arc_angles(a1 - 1.8, a1, 1.8), mat=1)
    if zone == "Torso":
        # electrode tips facing each other across the gap
        for sgn, edge in ((-1, c - PHASE_GAP), (1, c + PHASE_GAP)):
            mb.sweep(circ, collar, arc_angles(edge + sgn * 3.2, edge, 3.2), mat=1)
            tip_angs = arc_angles(edge, edge - sgn * 4.0, 1.0)

            def sfn(a, e0=edge):
                t = min(1.0, abs(math.degrees(a) - e0) / 4.0)
                return 1.0 - 0.72 * t ** 1.6
            mb.sweep(circ, collar, tip_angs, mat=1, scale_fn=sfn)
        for pc in (c - 29.5, c + 29.5):
            _plate_and_glyph(mb, "Phase", zone, pc, R - 0.006, R + 0.006, 0.0066, 0.0092, span=4.5)
    else:
        _plate_and_glyph(mb, "Phase", zone, c, R - 0.006, R + 0.006, 0.0066, 0.0092, span=4.5)


ARC_BUILDERS = {"Bulwark": arc_bulwark, "Mender": arc_mender, "Volt": arc_volt, "Phase": arc_phase}


def build_arc(core, zone, mats, col):
    mb = MB()
    ARC_BUILDERS[core](mb, zone)
    smooth = 20 if core == "Bulwark" else 35
    return mb.finish(f"HALO_{core}_Arc_{zone}", mats, smooth_angle=smooth, col=col)


# ------------------------------------------------------------------------------------------------ bands
# The weight band stacks UNDER and OUTSIDE the ring, so the glowing glass stays visible at eye level.
def _band_spans(core):
    """Angular spans (deg) the band covers (Phase keeps its gap at the back)."""
    if core == "Phase":
        g = PHASE_GAP + 2.0
        return [(90 + g, 450 - g)]
    return [(0.0, 360.0)]


def _sweep_spans(mb, core, prof, mat=0, step=6.0):
    shape = SHAPE[core]
    for s0, s1 in _band_spans(core):
        angs = _angles(core, s0, s1, step)
        if s1 - s0 >= 359.9:
            mb.sweep(shape, prof, angs[:-1], mat=mat, loop=True)
        else:
            mb.sweep(shape, prof, angs, mat=mat)


def band_medium(mb, core):
    shape = SHAPE[core]
    T = RING_BOT[core] + 0.0015
    din, dout = RING_IN[core] + 0.004, RING_OUT[core] + 0.016
    prof = [(din, T), (dout - 0.005, T), (dout, T - 0.005), (dout, T - 0.015), (dout - 0.006, T - 0.022),
            (din + 0.004, T - 0.022), (din, T - 0.017)]
    _sweep_spans(mb, core, prof)
    # four clamp fingers rising to hug the ring's outer face at the arc joints
    fing = [(RING_OUT[core] - 0.001, T - 0.014), (dout + 0.003, T - 0.014), (dout + 0.003, T - 0.001),
            (RING_OUT[core] + 0.005, T + 0.009), (RING_OUT[core] - 0.001, T + 0.009)]
    for a in (45, 135, 225, 315):
        mb.sweep(shape, fing, _angles(core, a - 3.5, a + 3.5, 7.0), mat=0)


def band_heavy(mb, core):
    shape = SHAPE[core]
    T = RING_BOT[core] + 0.0015
    din, dout = RING_IN[core] + 0.003, RING_OUT[core] + 0.038
    rail = [(din, T), (din + 0.016, T), (din + 0.016, T - 0.040), (din + 0.004, T - 0.040), (din, T - 0.036)]
    _sweep_spans(mb, core, rail)
    plate = [(din + 0.006, T), (dout - 0.011, T - 0.002), (dout, T - 0.013), (dout + 0.001, T - 0.032),
             (dout - 0.009, T - 0.050), (din + 0.012, T - 0.050), (din + 0.006, T - 0.040)]
    ridge = [(dout - 0.004, T - 0.007), (dout + 0.007, T - 0.013), (dout + 0.008, T - 0.033),
             (dout - 0.003, T - 0.045)]
    if core == "Bulwark":
        centres, half = [30 + 60 * k for k in range(6)], 26.5
    else:
        centres, half = [270 + 36 * k for k in range(10)], 16.0
    for cc in centres:
        if core == "Phase" and abs(((cc - 90) + 180) % 360 - 180) < 1:
            continue
        mb.sweep(shape, plate, _angles(core, cc - half, cc + half, 6.4), mat=0)
        # raised centre ridge = armour keel (breaks the silhouette into plates)
        mb.sweep(shape, ridge, _angles(core, cc - 2.6, cc + 2.6, 5.2), mat=0)
        # bolts on the outer armour face
        for off in (-half * 0.6, half * 0.6):
            a = D(cc + off)
            o, t, n, up = frame_at(shape, a, dout + 0.0005, T - 0.023)
            hexb = [(0.0034 * math.cos(D(30 + 60 * i)), 0.0034 * math.sin(D(30 + 60 * i))) for i in range(6)]
            mb.prism(hexb, o, t, up, n, -0.002, 0.0022, mat=1)
    if core == "Bulwark":  # corner blocks lock the slabs together
        corner = rounded_rect(din - 0.002, dout + 0.007, T - 0.057, T + 0.004, 0.003, 1)
        for k in range(6):
            a = HEX_CORNERS[k]
            mb.sweep(shape, corner, hex_angles(a - 3.4, a + 3.4), mat=0)
    else:  # clamp fingers at the plate joints
        fing = [(RING_OUT[core] - 0.001, T - 0.010), (RING_OUT[core] + 0.010, T - 0.010),
                (RING_OUT[core] + 0.010, T + 0.002), (RING_OUT[core] + 0.004, T + 0.010),
                (RING_OUT[core] - 0.001, T + 0.010)]
        for cc in centres:
            j = cc + 18.0
            if core == "Phase" and abs(((j - 90) + 180) % 360 - 180) < PHASE_GAP + 3:
                continue
            mb.sweep(shape, fing, _angles(core, j - 2.5, j + 2.5, 5.0), mat=0)


def build_band(core, weight, mats, col):
    mb = MB()
    (band_medium if weight == "Medium" else band_heavy)(mb, core)
    return mb.finish(f"HALO_{core}_Band_{weight}", mats, smooth_angle=25, col=col)


# ------------------------------------------------------------------------------------------------ pip
def build_pip(mats, col):
    """Upright diamond facing -Y (the engine places 4 of them at HALO_PIP_1..4)."""
    mb = MB()
    h, w, d = 0.0090, 0.0056, 0.0030
    verts = [(0, 0, h), (0, 0, -h), (-w, 0, 0), (w, 0, 0), (0, -d, 0), (0, d, 0)]
    faces = [(0, 4, 3), (0, 3, 5), (0, 5, 2), (0, 2, 4), (1, 3, 4), (1, 5, 3), (1, 2, 5), (1, 4, 2)]
    mb.raw(verts, faces, mat=0)
    return mb.finish("HALO_TierPip", mats, smooth_angle=10, col=col)


# ------------------------------------------------------------------------------------------------ power cell
def build_cell(mats, col):
    """Capsule cell travelling along local +X: graphite end caps, hexagonal glass crystal window in the
    middle and a swept glass 'orbit-trail' fin trailing toward -X."""
    mb = MB()
    zc = circ
    # glass crystal (6 sides), along Z for now
    crystal = [(0.0, -0.0175), (0.0078, -0.011), (0.0078, 0.011), (0.0, 0.0175)]
    mb.sweep(zc, crystal, [D(30 + 60 * i) for i in range(6)], mat=0, cap=False, loop=True, open_profile=True)
    # graphite caps (front = +Z before rotation = +X after)
    front = [(0.0, 0.0255), (0.0042, 0.0245), (0.0080, 0.0205), (0.0098, 0.0150), (0.0098, 0.0095),
             (0.0060, 0.0080), (0.0, 0.0080)]
    rear = [(0.0, -0.0080), (0.0060, -0.0080), (0.0098, -0.0095), (0.0098, -0.0150), (0.0080, -0.0190),
            (0.0050, -0.0215), (0.0, -0.0220)]
    steps = [2 * math.pi * i / 12 for i in range(12)]
    mb.sweep(zc, front, steps, mat=1, cap=False, loop=True, open_profile=True)
    mb.sweep(zc, rear, steps, mat=1, cap=False, loop=True, open_profile=True)
    # thin glowing ring on the nose
    mb.sweep(zc, rounded_rect(0.0090, 0.0101, 0.0168, 0.0186, 0.0004, 1), steps, mat=0, loop=True)
    bm = mb.bm
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(D(90), 3, "Y"))
    # swept trail fin: tall at the root, tapering to a point behind the cell
    fin = [(-0.016, -0.0060), (-0.016, 0.0092), (-0.026, 0.0090), (-0.040, 0.0060), (-0.072, 0.0000),
           (-0.072, -0.0020), (-0.040, -0.0035)]
    fv = mb.prism(fin, (0, 0, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), -0.0013, 0.0013, mat=0)
    # bend the fin along a ~0.25 m orbit (centre at local +Y) so it reads as an orbit trail
    R = 0.25
    for f in fv:
        for v in f.verts:
            if v.co.x < -0.0159 and not v.tag:
                v.tag = True
                x, y = v.co.x, v.co.y
                ph = x / R
                v.co.x = (R - y) * math.sin(ph)
                v.co.y = R - (R - y) * math.cos(ph)
    for v in mb.bm.verts:
        v.tag = False
    bmesh.ops.scale(mb.bm, vec=(1.25, 1.25, 1.25), verts=mb.bm.verts)   # ~6 cm capsule, readable at range
    return mb.finish("HALO_PowerCell", mats, smooth_angle=25, col=col)


# ------------------------------------------------------------------------------------------------ shards
def _gem_prism(mb, poly, th, raise_top, mat=0):
    bm = mb.bm
    bot = [bm.verts.new((u, v, -th / 2)) for u, v in poly]
    top = [bm.verts.new((u * 0.9, v * 0.9, th / 2)) for u, v in poly]
    cu = sum(p[0] for p in poly) / len(poly)
    cv = sum(p[1] for p in poly) / len(poly)
    apex = bm.verts.new((cu, cv, th / 2 + raise_top))
    faces = [bm.faces.new(list(reversed(bot)))]
    n = len(poly)
    for i in range(n):
        faces.append(bm.faces.new((bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i])))
        faces.append(bm.faces.new((top[i], top[(i + 1) % n], apex)))
    for f in faces:
        f.material_index = mat


def build_shards(mats, col):
    out = []
    hexp = [(0.015 * math.cos(D(60 * i)), 0.015 * math.sin(D(60 * i))) for i in range(6)]
    # A: hex chip with one corner snapped off
    a_poly = hexp[:1] + [(0.0105, 0.0085), (0.0035, 0.0128)] + hexp[2:]
    # B: one sixth wedge of a hex cell, slightly irregular
    b_poly = [(0.0, 0.0), (0.021, -0.001), (0.0098, 0.0185), (0.0035, 0.0105)]
    # C: long sliver broken off a cell edge
    c_poly = [(-0.017, -0.003), (0.011, -0.0055), (0.019, 0.0005), (0.004, 0.0052), (-0.013, 0.0032)]
    for nm, poly, th, rt in (("A", a_poly, 0.0042, 0.0016), ("B", b_poly, 0.0050, 0.0018),
                             ("C", c_poly, 0.0032, 0.0012)):
        mb = MB()
        _gem_prism(mb, poly, th, rt)
        o = mb.finish(f"HALO_Shard_{nm}", mats, smooth_angle=5, col=col)
        out.append(o)
    return out


# ------------------------------------------------------------------------------------------------ pickups
# Hand-sized core canisters (~0.09 m wide, ~0.06 m tall), origin at the bottom centre, front = -Y.
# The top window repeats the ring silhouette; side windows show the tier glow from any angle.
def _angles_any(shape, a0, a1):
    return hex_angles(a0, a1) if shape is hexs else arc_angles(a0, a1, 3.0)


def _side_windows(mb, shape, d, z0, z1, angles, half=9.0, depth=0.0025):
    """Glass window slots on the canister wall (slightly proud of the wall)."""
    for a in angles:
        prof = rounded_rect(d - 0.002, d + depth, z0, z1, 0.0012, 1)
        mb.sweep(shape, prof, _angles_any(shape, a - half, a + half), mat=0)


def _disc_window(mb, shape, d, z0, z1, mat, steps=48):
    prof = [(0.0, z0), (d, z0), (d, z1 - 0.0012), (d - 0.0012, z1), (0.0, z1)]
    mb.lathe(shape, prof, steps=steps, mat=mat)


def pickup_bulwark(mb):
    # armoured hex canister: foot, body with bone band, faceted hex glass crown in a graphite rim
    body = [(0.0, 0.0), (0.036, 0.0), (0.041, 0.004), (0.041, 0.050), (0.037, 0.054), (0.029, 0.054),
            (0.027, 0.051), (0.0, 0.051)]
    mb.lathe(hexs, body, mat=1, corners=HEX_CORNERS)
    band = [(0.0, 0.010), (0.0418, 0.010), (0.0418, 0.017), (0.0, 0.017)]
    mb.lathe(hexs, band, mat=2, corners=HEX_CORNERS)
    gem = [(0.0, 0.048), (0.0262, 0.048), (0.0262, 0.056), (0.017, 0.063), (0.0, 0.063)]
    mb.lathe(hexs, gem, mat=0, corners=HEX_CORNERS)
    _side_windows(mb, hexs, 0.041, 0.023, 0.043, (270, 30, 150), half=16.0)
    for k in range(6):   # vertical corner armour lugs
        a = HEX_CORNERS[k]
        lug = rounded_rect(0.037, 0.0465, 0.002, 0.056, 0.002, 1)
        mb.sweep(hexs, lug, hex_angles(a - 4.5, a + 4.5), mat=1)


def pickup_mender(mb):
    body = [(0.0, 0.0), (0.037, 0.0), (0.042, 0.005), (0.042, 0.046), (0.039, 0.050), (0.0, 0.050)]
    mb.lathe(circ, body, steps=40, mat=1)
    band = [(0.0, 0.009), (0.0425, 0.009), (0.0425, 0.015), (0.0, 0.015)]
    mb.lathe(circ, band, steps=40, mat=2)
    angs = [2 * math.pi * i / 40 for i in range(40)]
    for r in (0.0195, 0.0325):    # twin glass rings on the lid
        mb.sweep(circ, rounded_rect(r - 0.0038, r + 0.0038, 0.046, 0.0545, 0.0016, 1), angs, mat=0, loop=True)
    cap = [(0.0, 0.049), (0.0105, 0.049), (0.0105, 0.055), (0.0085, 0.057), (0.0, 0.057)]
    mb.lathe(circ, cap, steps=20, mat=1)
    for k in range(4):  # bridges between the twin rings
        a = 45 + 90 * k
        mb.sweep(circ, rounded_rect(0.014, 0.038, 0.049, 0.0565, 0.001, 1), arc_angles(a - 4, a + 4, 2), mat=1)
    _side_windows(mb, circ, 0.042, 0.020, 0.040, (270, 90), half=7.0)
    _side_windows(mb, circ, 0.042, 0.020, 0.040, (255, 285, 75, 105), half=2.2)


def pickup_volt(mb):
    body = [(0.0, 0.0), (0.035, 0.0), (0.040, 0.005), (0.040, 0.044), (0.037, 0.047), (0.0, 0.047)]
    mb.lathe(circ, body, steps=40, mat=1)
    band = [(0.0, 0.009), (0.0405, 0.009), (0.0405, 0.015), (0.0, 0.015)]
    mb.lathe(circ, band, steps=40, mat=2)
    _disc_window(mb, circ, 0.024, 0.042, 0.051, 0, steps=32)
    tooth = [(-0.012, 0.0), (0.007, 0.0), (0.007, 0.0095), (0.0045, 0.0150), (0.0005, 0.0150)]
    for k in range(6):  # sawtooth crown: glass blades in graphite collars (echoes the Volt ring)
        a = D(30 + 60 * k)
        o, t, n, up = frame_at(circ, a, 0.034, 0.044)
        mb.prism(tooth, o, t, up, n, -0.0035, 0.0035, mat=0)
        collar = [(-0.0135, -0.001), (0.0085, -0.001), (0.0085, 0.0045), (-0.0105, 0.0045)]
        mb.prism(collar, o, t, up, n, -0.0045, 0.0045, mat=1)
    _side_windows(mb, circ, 0.040, 0.020, 0.038, (270, 30, 150), half=10.0)


def pickup_phase(mb):
    prof = [(0.0, 0.0)]
    for i in range(7):
        t = D(-90 + 90 * i / 6)
        prof.append((0.031 + 0.010 * math.cos(t), 0.010 + 0.010 * math.sin(t)))
    for i in range(1, 7):
        t = D(90 * i / 6)
        prof.append((0.031 + 0.010 * math.cos(t), 0.038 + 0.010 * math.sin(t)))
    prof.append((0.0, 0.048))
    mb.lathe(circ, prof, steps=32, mat=1)
    foot = [(0.0, 0.0005), (0.0330, 0.0005), (0.0330, 0.0045), (0.0, 0.0045)]
    mb.lathe(circ, foot, steps=32, mat=2)
    lens = ellipse(0.024, 0.048, 0.0062, 0.0042, 10)
    mb.sweep(circ, lens, arc_angles(90 + 24, 450 - 24, 5.0), mat=0)
    for e, sgn in ((90 + 24, 1), (450 - 24, -1)):
        mb.sweep(circ, ellipse(0.024, 0.048, 0.0072, 0.0050, 10), arc_angles(e, e + sgn * 3.5, 1.0), mat=1)
    cap = [(0.0, 0.047), (0.010, 0.047), (0.010, 0.0505), (0.0075, 0.0525), (0.0, 0.0525)]
    mb.lathe(circ, cap, steps=20, mat=0)
    # a glowing equator ring with the same gap at the back
    eq = rounded_rect(0.0405, 0.0425, 0.026, 0.032, 0.0008, 1)
    mb.sweep(circ, eq, arc_angles(90 + 24, 450 - 24, 5.0), mat=0)


PICKUPS = {"Bulwark": pickup_bulwark, "Mender": pickup_mender, "Volt": pickup_volt, "Phase": pickup_phase}


def build_pickup(core, mats, col):
    mb = MB()
    PICKUPS[core](mb)
    return mb.finish(f"HALO_Core_{core}", mats, smooth_angle=30, col=col)
