"""Part builders for the HALO kit: core arcs, weight bands, pips, power cell, shards, pickup cores, far LOD.

Every arc/band object has its origin at the halo centre.  Material slots:
  arcs        : 0 = glass (swap per arc: M_HALO_Glass_T<tier> / _Off / _Broken_T<tier>), 1 = graphite,
                2 = edge (M_HALO_Edge, always-on frame light)
  bands       : 0 = graphite, 1 = gunmetal (bolts), 2 = lip glass (highest arc tier), 3 = edge
  far glass   : 0 = glass (same swap as the arc)
  far frame   : 0 = graphite, 1 = edge, 2 = lip glass (Medium/Heavy only)
  cell        : 0 = glass (highest tier / status colour), 1 = graphite
  pickup      : 0 = window glass (tier), 1 = graphite, 2 = bone

Readability rules baked in (review 2026-10-07, see NOTES.md "Review fixes"):
  * every core has an EDGE-ON signature that reads from 1-10 deg below the ring:
      Bulwark = tall faceted glass wall + corner posts, Mender = two rings stacked 14 mm apart in Z,
      Volt = crown teeth, Phase = an electrode fork rising either side of the back gap;
  * each arc body is ONE swept shell whose profile edges carry glass / graphite frame / edge-light stripes:
    glass on the outer wall, top, inner wall and underside (tier colour from any angle), graphite frame lines
    and keel, and thin always-on edge lines that draw the ring outline even when no arc is covered;
  * bands clamp around the ring's lower outer wall (hang below the ring <= 30 mm), lip glass underneath.
"""
import math

import bmesh
from mathutils import Matrix

from halo_lib import (D, HEX_CORNERS, MB, ZONES, SegProfile, add_glyph, arc_angles, circ, ellipse, frame_at,
                      hex_angles, hexs, rounded_rect)

GAP = 0.7          # deg, half-gap between arcs (=> ~4 mm seam)
INSET = 0.35       # deg, arc bodies stop inside the end clamps (no coplanar end caps)
G, K, E = 0, 1, 2              # arc material slots
BK, BM, BL, BE = 0, 1, 2, 3    # band material slots

# ------------------------------------------------------------------------------------------------ cores
BUL_A = 0.150                          # Bulwark hexagon apothem (flat edge to the front)
MEN_RI, MEN_RO = 0.143, 0.177          # Mender ring radii
MEN_ZI, MEN_ZO = 0.0070, -0.0070       # Mender ring centre heights: inner ring high, outer ring low
MEN_HW, MEN_HH = 0.0045, 0.0055        # Mender ring half width / half height
VOLT_R = 0.160
PHASE_R = 0.160
PHASE_GAP = 15.0                       # half-angle of the Phase gap at the back (deg)
SHAPE = {"Bulwark": hexs, "Mender": circ, "Volt": circ, "Phase": circ}
ARC_STEP = 6.0                         # deg, sampling of the round arcs

# ring envelope per core (outer distance, bottom z): the weight band clamps around it
RING_OUT = {"Bulwark": BUL_A + 0.0212, "Mender": MEN_RO + 0.0058, "Volt": VOLT_R + 0.0140, "Phase": PHASE_R + 0.0090}
RING_BOT = {"Bulwark": -0.0152, "Mender": MEN_ZO - MEN_HH, "Volt": -0.0125, "Phase": -0.0130}
# band top (z): low enough that the upper glass wall (and both Mender rings) stays visible above the band
BAND_TOP = {"Bulwark": {"Medium": -0.0060, "Heavy": -0.0015}, "Mender": {"Medium": -0.0100, "Heavy": -0.0095},
            "Volt": {"Medium": -0.0055, "Heavy": -0.0030}, "Phase": {"Medium": -0.0060, "Heavy": -0.0035}}
HANG = {"Medium": 0.010, "Heavy": 0.026}     # band bottom below the ring bottom
BAND_DEPTH = {"Medium": 0.016, "Heavy": 0.038}

# tier pips: diamond half height + where they sit on each core's Head arc (pip rail top z, distance d)
PIP_H = 0.0090
PIP_SPACING = 0.0160
PIP_SEAT = {"Bulwark": (0.0168, BUL_A + 0.0085), "Mender": (0.0140, MEN_RI + 0.0005),
            "Volt": (0.0106, VOLT_R + 0.0048), "Phase": (0.0118, PHASE_R + 0.0045)}


def pip_positions(core):
    """HALO_<Core>_PIP_1..4 (halo-local, unscaled); PIP_1 is on the viewer's left when facing the wearer."""
    z, d = PIP_SEAT[core]
    return [(-1.5 * PIP_SPACING + i * PIP_SPACING, -d, z + PIP_H + 0.0002) for i in range(4)]


def strip(d0, d1, z0, z1):
    """Plain 4-vertex rectangle profile (thin rails / ticks)."""
    return [(d1, z0), (d1, z1), (d0, z1), (d0, z0)]


def _angles(core, a0, a1, step=ARC_STEP):
    return hex_angles(a0, a1) if core == "Bulwark" else arc_angles(a0, a1, step)


def _plate_and_glyph(mb, core, zone, a, d0, d1, z0, z1, span=5.0, glyph_d=None):
    """Graphite zone plate on top of the arc + the raised glass glyph on it."""
    shape = SHAPE[core]
    prof = rounded_rect(d0, d1, z0, z1, 0.0008, 1)
    mb.sweep(shape, prof, _angles(core, a - span, a + span, min(span, 6.0)), mat=K)
    add_glyph(mb, shape, D(a), glyph_d if glyph_d is not None else (d0 + d1) / 2, z1, zone, mat=G)


def _ticks(mb, core, c, offsets, d0, d1, z0, z1, width=0.8):
    """Thin graphite bars across the glass: reads as segmented energy cells (tech, not a neon tube)."""
    shape = SHAPE[core]
    for off in offsets:
        a = c + off
        mb.sweep(shape, strip(d0, d1, z0, z1), _angles(core, a - width / 2, a + width / 2, width), mat=K)


# ---- Bulwark: thick faceted hexagon, tall glass outer wall, corner posts break the edge-on line
def bul_profile():
    A = BUL_A
    return SegProfile([
        ((A + 0.0195, -0.0152), K), ((A + 0.0205, -0.0142), K),     # outer skirt rail
        ((A + 0.0205, -0.0132), E), ((A + 0.0205, -0.0110), K),     # edge line on the skirt
        ((A + 0.0205, -0.0098), K),
        ((A + 0.0190, -0.0092), G),                                 # glass outer wall (24 mm)
        ((A + 0.0190, 0.0125), G),                                  # top chamfer facet
        ((A + 0.0165, 0.0150), E),                                  # edge line on the top outer edge
        ((A + 0.0125, 0.0150), G),                                  # glass top
        ((A - 0.0112, 0.0150), K), ((A - 0.0118, 0.0162), K),       # graphite inner frame line
        ((A - 0.0180, 0.0162), K), ((A - 0.0188, 0.0154), K), ((A - 0.0188, 0.0042), K),
        ((A - 0.0175, 0.0035), G),                                  # glass inner wall
        ((A - 0.0175, -0.0095), G),
        ((A - 0.0135, -0.0135), G),                                 # glass underside, inner strip
        ((A - 0.0030, -0.0135), K), ((A - 0.0030, -0.0150), K),     # keel
        ((A + 0.0050, -0.0150), K),
        ((A + 0.0050, -0.0135), G),                                 # glass underside, outer strip
        ((A + 0.0145, -0.0135), K), ((A + 0.0145, -0.0152), K),     # skirt
    ]).check("bulwark")


BUL_FAR_GLASS = [(BUL_A + 0.0190, -0.0115), (BUL_A + 0.0190, 0.0125), (BUL_A + 0.0165, 0.0150),
                 (BUL_A - 0.0130, 0.0150), (BUL_A - 0.0175, 0.0105), (BUL_A - 0.0175, -0.0095),
                 (BUL_A - 0.0135, -0.0135), (BUL_A + 0.0165, -0.0135)]


def arc_bulwark(mb, zone):
    c = ZONES[zone]
    A = BUL_A
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    mb.sweep(hexs, bul_profile(), hex_angles(a0 + INSET, a1 - INSET), cap_mat=K)
    # segment ticks on the glass (top + outer wall), clear of the corners and the zone plate
    span = 12.0 if zone == "Head" else 5.5
    offs = [o for o in (-34.0, -25.0, -16.0, 16.0, 25.0, 34.0)
            if min(abs(((c + o) - k + 180) % 360 - 180) for k in HEX_CORNERS) > 4.5 and abs(o) > span + 1.5]
    _ticks(mb, "Bulwark", c, offs, A - 0.0110, A + 0.0120, 0.0144, 0.0157)
    _ticks(mb, "Bulwark", c, offs, A + 0.0184, A + 0.0198, -0.0086, 0.0118)
    # end clamps at the arc seams
    clamp = [(A - 0.0196, -0.0158), (A + 0.0215, -0.0158), (A + 0.0215, 0.0135), (A + 0.0185, 0.0170),
             (A - 0.0185, 0.0170), (A - 0.0196, 0.0160)]
    mb.sweep(hexs, clamp, hex_angles(a0, a0 + 3.5), mat=K)
    mb.sweep(hexs, clamp, hex_angles(a1 - 3.5, a1), mat=K)
    # corner posts (8.5 mm above the ring top) with a small edge light on top
    post = rounded_rect(A - 0.0205, A + 0.0228, -0.0160, 0.0235, 0.0015)
    lamp = strip(A - 0.0020, A + 0.0120, 0.0232, 0.0246)
    for k in HEX_CORNERS:
        for kk in (k - 360, k, k + 360):
            if a0 + 3 < kk < a1 - 3:
                mb.sweep(hexs, post, hex_angles(kk - 3.0, kk + 3.0), mat=K)
                mb.sweep(hexs, lamp, hex_angles(kk - 1.6, kk + 1.6), mat=E)
    if zone == "Head":   # wide pip rail: glyph on the inner half, tier pips on the outer half
        _plate_and_glyph(mb, "Bulwark", zone, c, A - 0.0125, A + 0.0150, 0.0142, 0.0168, span=span,
                         glyph_d=A - 0.0058)
    else:
        _plate_and_glyph(mb, "Bulwark", zone, c, A - 0.0080, A + 0.0090, 0.0142, 0.0168, span=span)


# ---- Mender: twin thin rings, the outer ring 14 mm lower (edge-on: two parallel lines)
def men_ring(R, zc):
    hw, hh, c = MEN_HW, MEN_HH, 0.0020
    return SegProfile([
        ((R + hw, zc - 0.0011), E),                                 # edge belt on the outer face
        ((R + hw, zc + 0.0011), G), ((R + hw, zc + hh - c), G), ((R + hw - c, zc + hh), G),
        ((R - hw + c, zc + hh), G), ((R - hw, zc + hh - c), G),
        ((R - hw, zc + 0.0016), K),                                 # graphite belt on the inner face
        ((R - hw, zc - 0.0016), G), ((R - hw, zc - hh + c), G), ((R - hw + c, zc - hh), G),
        ((R + hw - c, zc - hh), G), ((R + hw, zc - hh + c), G),
    ]).check("mender")


def _men_line(d):
    """z of the line joining the two ring centres at distance d."""
    return MEN_ZI + (MEN_ZO - MEN_ZI) * (d - MEN_RI) / (MEN_RO - MEN_RI)


MEN_BRIDGE = [(MEN_RI - 0.0058, MEN_ZI + 0.0040), (MEN_RI - 0.0058, MEN_ZI - 0.0050),
              (MEN_RO + 0.0058, MEN_ZO - 0.0050), (MEN_RO + 0.0058, MEN_ZO + 0.0040)]


def arc_mender(mb, zone):
    c = ZONES[zone]
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    angs = arc_angles(a0 + INSET, a1 - INSET, ARC_STEP)
    for R, zc in ((MEN_RI, MEN_ZI), (MEN_RO, MEN_ZO)):
        mb.sweep(circ, men_ring(R, zc), angs)
    # slanted bridges at the arc ends (tie the two rings together)
    mb.sweep(circ, MEN_BRIDGE, arc_angles(a0, a0 + 2.6, 2.6), mat=K)
    mb.sweep(circ, MEN_BRIDGE, arc_angles(a1 - 2.6, a1, 2.6), mat=K)
    # thin slanted rungs (tech ladder feel)
    d0, d1 = MEN_RI + 0.0020, MEN_RO - 0.0020
    rung = [(d0, _men_line(d0) + 0.0015), (d0, _men_line(d0) - 0.0015), (d1, _men_line(d1) - 0.0015),
            (d1, _men_line(d1) + 0.0015)]
    for off in (-24.0, 24.0):
        mb.sweep(circ, rung, arc_angles(c + off - 1.0, c + off + 1.0, 2.0), mat=K)
    # zone bridge: sits on top of BOTH rings (1.5 mm above the inner ring top), glyph on top
    top = MEN_ZI + MEN_HH + 0.0015
    zb = [(MEN_RO + 0.0060, MEN_ZO - 0.0035), (MEN_RO + 0.0060, top), (MEN_RI - 0.0060, top),
          (MEN_RI - 0.0060, top - 0.0035), (MEN_RO - 0.0050, top - 0.0035), (MEN_RO - 0.0050, MEN_ZO - 0.0035)]
    mb.sweep(circ, zb, arc_angles(c - 4.2, c + 4.2, 4.2), mat=K)
    add_glyph(mb, circ, D(c), (MEN_RI + MEN_RO) / 2 + 0.001, top, zone, mat=G)
    if zone == "Head":   # pip rail on the (higher) inner ring, flush with the bridge top
        mb.sweep(circ, rounded_rect(MEN_RI - 0.0050, MEN_RI + 0.0050, top - 0.0030, top - 0.0001, 0.0008),
                 arc_angles(c - 12.5, c + 12.5, 5.0), mat=K)


# ---- Volt: crown ring with short upward sawtooth teeth
def volt_profile():
    R = VOLT_R
    return SegProfile([
        ((R + 0.0115, -0.0118), K), ((R + 0.0125, -0.0108), K),     # outer skirt rail
        ((R + 0.0125, -0.0102), E), ((R + 0.0125, -0.0084), K),     # edge line on the skirt
        ((R + 0.0125, -0.0074), K),
        ((R + 0.0110, -0.0068), G),                                 # glass outer wall
        ((R + 0.0110, 0.0040), G),                                  # big top facet
        ((R + 0.0072, 0.0090), E),                                  # edge line, top outer edge
        ((R + 0.0042, 0.0090), G),                                  # glass top
        ((R - 0.0072, 0.0090), K), ((R - 0.0076, 0.0100), K),       # graphite inner frame line
        ((R - 0.0105, 0.0100), K), ((R - 0.0113, 0.0092), K), ((R - 0.0113, 0.0030), K),
        ((R - 0.0100, 0.0025), G),                                  # glass inner wall
        ((R - 0.0100, -0.0070), G),
        ((R - 0.0070, -0.0100), G),                                 # glass underside, inner strip
        ((R - 0.0015, -0.0100), K), ((R - 0.0015, -0.0115), K),     # keel
        ((R + 0.0035, -0.0115), K),
        ((R + 0.0035, -0.0100), G),                                 # glass underside, outer strip
        ((R + 0.0075, -0.0100), K), ((R + 0.0075, -0.0118), K),     # skirt
    ]).check("volt")


VOLT_FAR_GLASS = [(VOLT_R + 0.0110, -0.0080), (VOLT_R + 0.0070, 0.0090), (VOLT_R - 0.0070, 0.0090),
                  (VOLT_R - 0.0100, -0.0070), (VOLT_R - 0.0070, -0.0100), (VOLT_R + 0.0080, -0.0100)]
VOLT_TOOTH = [(-0.021, 0.004), (0.012, 0.004), (0.012, 0.027), (0.0085, 0.041), (0.0025, 0.041)]


def arc_volt(mb, zone):
    c = ZONES[zone]
    R = VOLT_R
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    mb.sweep(circ, volt_profile(), arc_angles(a0 + INSET, a1 - INSET, ARC_STEP), cap_mat=K)
    _ticks(mb, "Volt", c, (-36.0, -10.5, 10.5, 36.0) if zone != "Head" else (-36.0, 36.0),
           R + 0.0104, R + 0.0118, -0.0062, 0.0036)
    clamp = [(R - 0.0125, -0.0125), (R + 0.0140, -0.0125), (R + 0.0140, 0.0050), (R + 0.0090, 0.0108),
             (R - 0.0110, 0.0108), (R - 0.0125, 0.0095)]
    mb.sweep(circ, clamp, arc_angles(a0, a0 + 3.5, 3.5), mat=K)
    mb.sweep(circ, clamp, arc_angles(a1 - 3.5, a1, 3.5), mat=K)
    # sawtooth teeth (lean counter-clockwise = the "spin" direction), glass blade in a graphite collar
    for off in (-22.5, 22.5):
        a = D(c + off)
        o, t, n, up = frame_at(circ, a, R, 0.0)
        mb.prism(VOLT_TOOTH, o, t, up, n, -0.0045, 0.0060, mat=G)
        cap = [(-0.0005, 0.0335), (0.0128, 0.0335), (0.0128, 0.0285), (0.0090, 0.0435), (0.0015, 0.0435)]
        mb.prism(cap, o, t, up, n, -0.0055, 0.0070, mat=K)
        collar = rounded_rect(R - 0.0080, R + 0.0120, 0.0060, 0.0135, 0.0015)
        mb.sweep(circ, collar, arc_angles(c + off - 8.4, c + off + 5.4, 4.6), mat=K)
    if zone == "Head":
        _plate_and_glyph(mb, "Volt", zone, c, R - 0.0082, R + 0.0085, 0.0082, 0.0106, span=11.5,
                         glyph_d=R - 0.0030)
    else:
        _plate_and_glyph(mb, "Volt", zone, c, R - 0.0065, R + 0.0075, 0.0082, 0.0106, span=5.0)


# ---- Phase: smooth round ring, gap at the back marked by an electrode fork
def phase_profile():
    R, hw, hh = PHASE_R, 0.0075, 0.0100

    def p(a):
        return (R + hw * math.cos(D(a)), hh * math.sin(D(a)))
    items = [(p(-6.0), E)]                                          # edge belt on the outer face
    items += [(p(a), G) for a in [6.0] + [360.0 * i / 14 for i in range(1, 10)]]
    items += [((R - 0.0030, -0.0104), K), ((R - 0.0022, -0.0130), K), ((R + 0.0022, -0.0130), K),  # keel fin
              ((R + 0.0030, -0.0104), G)]
    items += [(p(360.0 * i / 14), G) for i in (12, 13)]
    return SegProfile(items).check("phase")


PHASE_COLLAR = ellipse(PHASE_R, -0.0010, 0.0090, 0.0125, 14)
# prong blade in (into-the-gap, up): rises ~28 mm above the ring and leans into the gap at the top
PHASE_PRONG = [(-0.0045, 0.0060), (0.0025, 0.0060), (0.0030, 0.0240), (0.0068, 0.0330), (0.0062, 0.0388),
               (0.0010, 0.0398), (-0.0030, 0.0335), (-0.0045, 0.0240)]
PHASE_SLEEVE = [(-0.0058, 0.0040), (0.0038, 0.0040), (0.0040, 0.0165), (-0.0058, 0.0165)]


def _phase_prong(mb, edge, into):
    """Electrode prong at the gap edge `edge` (deg); `into` = +1 when the gap lies counter-clockwise."""
    a = D(edge - into * 1.2)
    o, t, n, up = frame_at(circ, a, PHASE_R, 0.0)
    g = t * into
    mb.prism(PHASE_PRONG, o, g, up, n, -0.0032, 0.0032, mat=G)
    mb.prism(PHASE_SLEEVE, o, g, up, n, -0.0042, 0.0042, mat=K)


def arc_phase(mb, zone):
    c = ZONES[zone]
    R = PHASE_R
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    pieces = [(a0, a1)]
    if zone == "Torso":  # gap opposite the front
        pieces = [(a0, c - PHASE_GAP), (c + PHASE_GAP, a1)]
    for p0, p1 in pieces:
        mb.sweep(circ, phase_profile(), arc_angles(p0 + INSET, p1 - INSET, ARC_STEP), cap_mat=K)
    # seam collars at the arc ends
    mb.sweep(circ, PHASE_COLLAR, arc_angles(a0, a0 + 1.8, 1.8), mat=K)
    mb.sweep(circ, PHASE_COLLAR, arc_angles(a1 - 1.8, a1, 1.8), mat=K)
    if zone == "Torso":
        for edge, into in ((c - PHASE_GAP, 1), (c + PHASE_GAP, -1)):
            mb.sweep(circ, PHASE_COLLAR, arc_angles(edge - into * 3.0, edge, 3.0), mat=K)
            _phase_prong(mb, edge, into)
        for pc in (c - 29.5, c + 29.5):
            _plate_and_glyph(mb, "Phase", zone, pc, R - 0.0058, R + 0.0058, 0.0055, 0.0118, span=4.5)
    elif zone == "Head":
        _plate_and_glyph(mb, "Phase", zone, c, R - 0.0085, R + 0.0075, 0.0055, 0.0118, span=12.0,
                         glyph_d=R - 0.0035)
    else:
        _plate_and_glyph(mb, "Phase", zone, c, R - 0.0058, R + 0.0058, 0.0055, 0.0118, span=4.5)


ARC_BUILDERS = {"Bulwark": arc_bulwark, "Mender": arc_mender, "Volt": arc_volt, "Phase": arc_phase}


def build_arc(core, zone, mats, col):
    mb = MB()
    ARC_BUILDERS[core](mb, zone)
    smooth = 20 if core == "Bulwark" else 35
    return mb.finish(f"HALO_{core}_Arc_{zone}", mats, smooth_angle=smooth, col=col)


# ------------------------------------------------------------------------------------------------ bands
# The weight band clamps around the ring's LOWER OUTER wall: its mass goes outward, it hangs at most
# HANG below the ring and its top stays below the ring's upper glass, so the lit glass reads at eye level.
BAND_STEP = 7.5


def _band_spans(core):
    """Angular spans (deg) the band covers (Phase keeps its gap at the back)."""
    if core == "Phase":
        g = PHASE_GAP + 2.0
        return [(90 + g, 450 - g)]
    return [(0.0, 360.0)]


def _sweep_spans(mb, core, prof, mat=BK, step=BAND_STEP):
    shape = SHAPE[core]
    for s0, s1 in _band_spans(core):
        angs = _angles(core, s0, s1, step)
        if s1 - s0 >= 359.9:
            mb.sweep(shape, prof, angs[:-1], mat=mat, loop=True)
        else:
            mb.sweep(shape, prof, angs, mat=mat, cap_mat=BK)


def band_dims(core, weight):
    T = BAND_TOP[core][weight]
    B = RING_BOT[core] - HANG[weight]
    din = RING_OUT[core] - 0.0040
    dout = RING_OUT[core] + BAND_DEPTH[weight]
    return T, B, din, dout


def band_medium(mb, core):
    shape = SHAPE[core]
    T, B, din, dout = band_dims(core, "Medium")
    zm = (T + B) / 2
    _sweep_spans(mb, core, SegProfile([
        ((din, B + 0.0015), BK), ((din + 0.0015, B), BL),            # lip glass on the underside
        ((din + 0.0065, B), BK), ((dout - 0.004, B), BK), ((dout, B + 0.004), BK),
        ((dout, zm - 0.0011), BE),                                   # edge line round the outer face
        ((dout, zm + 0.0011), BK), ((dout, T - 0.004), BK), ((dout - 0.004, T), BK), ((din, T), BK),
    ]).check("band medium"))
    # four clamp fingers rising to hug the ring's outer face at the arc joints
    ro = RING_OUT[core]
    fing = [(ro - 0.0050, T - 0.008), (dout + 0.003, T - 0.008), (dout + 0.003, T - 0.001),
            (ro + 0.004, T + 0.009), (ro - 0.0050, T + 0.009)]
    for a in (45, 135, 225, 315):
        mb.sweep(shape, fing, _angles(core, a - 3.5, a + 3.5, 7.0), mat=BK)


def band_heavy(mb, core):
    shape = SHAPE[core]
    T, B, din, dout = band_dims(core, "Heavy")
    # continuous inner rail that ties the slabs together, lip glass on its underside
    _sweep_spans(mb, core, SegProfile([
        ((din, B + 0.0015), BK), ((din + 0.0015, B), BL), ((din + 0.0090, B), BK), ((din + 0.012, B + 0.003), BK),
        ((din + 0.012, T), BK), ((din, T), BK)]).check("band heavy rail"))

    def face_d(z):   # outer slab face runs from (dout, T-0.010) down to (dout+0.001, B+0.010)
        return dout + 0.001 * ((T - 0.010) - z) / ((T - 0.010) - (B + 0.010))
    plate = SegProfile([
        ((din + 0.006, B + 0.006), BK), ((din + 0.010, B + 0.001), BK), ((dout - 0.008, B + 0.001), BK),
        ((dout + 0.001, B + 0.010), BK),
        ((face_d(T - 0.0138), T - 0.0138), BE),                      # edge line along the top of each slab
        ((face_d(T - 0.0114), T - 0.0114), BK),
        ((dout, T - 0.010), BK), ((dout - 0.012, T - 0.001), BK), ((din + 0.006, T + 0.001), BK),
    ]).check("band heavy plate")
    ridge = [(dout - 0.004, T - 0.006), (dout + 0.007, T - 0.011), (dout + 0.008, B + 0.010),
             (dout - 0.003, B + 0.003)]
    if core == "Bulwark":
        centres, half = [30 + 60 * k for k in range(6)], 26.5
    else:
        centres, half = [270 + 36 * k for k in range(10)], 16.0
    zb = (T + B) / 2 - 0.002
    for cc in centres:
        if core == "Phase" and abs(((cc - 90) + 180) % 360 - 180) < 1:
            continue
        mb.sweep(shape, plate, _angles(core, cc - half, cc + half, 8.0), cap_mat=BK)
        # raised centre ridge = armour keel (breaks the silhouette into plates)
        mb.sweep(shape, ridge, _angles(core, cc - 2.6, cc + 2.6, 5.2), mat=BK)
        for off in (-half * 0.6, half * 0.6):   # bolts on the outer armour face
            a = D(cc + off)
            o, t, n, up = frame_at(shape, a, dout + 0.0005, zb)
            hexb = [(0.0034 * math.cos(D(30 + 60 * i)), 0.0034 * math.sin(D(30 + 60 * i))) for i in range(6)]
            mb.prism(hexb, o, t, up, n, -0.002, 0.0022, mat=BM)
    if core == "Bulwark":  # corner blocks lock the slabs together
        corner = rounded_rect(din - 0.002, dout + 0.007, B - 0.003, T + 0.004, 0.003)
        for k in range(6):
            a = HEX_CORNERS[k]
            mb.sweep(shape, corner, hex_angles(a - 3.4, a + 3.4), mat=BK)
    else:  # clamp fingers at the plate joints, hugging the ring's outer face
        ro = RING_OUT[core]
        fing = [(ro - 0.0050, T - 0.010), (ro + 0.010, T - 0.010), (ro + 0.010, T + 0.002), (ro + 0.004, T + 0.010),
                (ro - 0.0050, T + 0.010)]
        for cc in centres:
            j = cc + 18.0
            if core == "Phase" and abs(((j - 90) + 180) % 360 - 180) < PHASE_GAP + 3:
                continue
            mb.sweep(shape, fing, _angles(core, j - 2.5, j + 2.5, 5.0), mat=BK)


def build_band(core, weight, mats, col):
    mb = MB()
    (band_medium if weight == "Medium" else band_heavy)(mb, core)
    return mb.finish(f"HALO_{core}_Band_{weight}", mats, smooth_angle=25, col=col)


# ------------------------------------------------------------------------------------------------ far LOD
# One cheap set per core for > ~20 m: 4 glass-only arcs (swap per arc exactly like the near arcs) plus one
# frame mesh per weight class (graphite + edge lines + band).  No ticks, bolts, glyphs or plates; the core
# signature (posts / offset rings / teeth / prongs), the band mass and the edge outline are kept.
FAR_STEP = 20.0


def _tri(d, z):
    """3-vertex edge-light ridge on an outer face at (d, z)."""
    return [(d - 0.0006, z - 0.0012), (d + 0.0010, z), (d - 0.0006, z + 0.0012)]


def far_glass(mb, core, zone):
    c = ZONES[zone]
    a0, a1 = c - 45 + GAP, c + 45 - GAP
    if core == "Bulwark":
        mb.sweep(hexs, BUL_FAR_GLASS, hex_angles(a0, a1, step=90.0), mat=0)
    elif core == "Mender":
        for R, zc in ((MEN_RI, MEN_ZI), (MEN_RO, MEN_ZO)):
            mb.sweep(circ, strip(R - MEN_HW, R + MEN_HW, zc - MEN_HH, zc + MEN_HH), arc_angles(a0, a1, FAR_STEP),
                     mat=0)
    elif core == "Volt":
        mb.sweep(circ, VOLT_FAR_GLASS, arc_angles(a0, a1, FAR_STEP), mat=0)
        for off in (-22.5, 22.5):
            o, t, n, up = frame_at(circ, D(c + off), VOLT_R, 0.0)
            mb.prism([VOLT_TOOTH[i] for i in (0, 1, 3, 4)], o, t, up, n, -0.0045, 0.0060, mat=0)
    else:
        pieces = [(a0, c - PHASE_GAP), (c + PHASE_GAP, a1)] if zone == "Torso" else [(a0, a1)]
        for p0, p1 in pieces:
            mb.sweep(circ, ellipse(PHASE_R, 0.0, 0.0075, 0.0100, 6), arc_angles(p0, p1, FAR_STEP), mat=0)
        if zone == "Torso":
            for edge, into in ((c - PHASE_GAP, 1), (c + PHASE_GAP, -1)):
                o, t, n, up = frame_at(circ, D(edge - into * 1.2), PHASE_R, 0.0)
                mb.prism([PHASE_PRONG[i] for i in (0, 1, 3, 4, 5, 7)], o, t * into, up, n, -0.0032, 0.0032, mat=0)


def far_frame(mb, core, weight):
    shape = SHAPE[core]
    full = [(0.0, 360.0)] if core != "Phase" else [(90 + PHASE_GAP, 450 - PHASE_GAP)]

    def ring(prof, mat, spans=full):
        for s0, s1 in spans:
            angs = hex_angles(s0, s1, step=60.0) if core == "Bulwark" else arc_angles(s0, s1, FAR_STEP)
            if s1 - s0 >= 359.9:
                mb.sweep(shape, prof, angs[:-1], mat=mat, loop=True)
            else:
                mb.sweep(shape, prof, angs, mat=mat)
    if core == "Bulwark":
        ring(strip(BUL_A + 0.0145, BUL_A + 0.0205, -0.0152, -0.0092), 0)
        ring(_tri(BUL_A + 0.0205, -0.0121), 1)
        post = strip(BUL_A - 0.0205, BUL_A + 0.0228, -0.0160, 0.0235)
        for k in HEX_CORNERS:
            mb.sweep(hexs, post, hex_angles(k - 3.0, k + 3.0, step=6.0), mat=0)
    elif core == "Mender":
        for R, zc in ((MEN_RI, MEN_ZI), (MEN_RO, MEN_ZO)):
            ring(_tri(R + MEN_HW, zc), 1)
        for a in (45, 135, 225, 315):
            mb.sweep(circ, MEN_BRIDGE, arc_angles(a - 2.0, a + 2.0, 4.0), mat=0)
    elif core == "Volt":
        ring(strip(VOLT_R + 0.0075, VOLT_R + 0.0125, -0.0118, -0.0068), 0)
        ring(_tri(VOLT_R + 0.0125, -0.0093), 1)
    else:
        ring([(PHASE_R - 0.0030, -0.0090), (PHASE_R + 0.0030, -0.0090), (PHASE_R, -0.0130)], 0)
        ring(_tri(PHASE_R + 0.0075, 0.0), 1)
        for edge, into in ((90 - PHASE_GAP, 1), (90 + PHASE_GAP, -1)):
            mb.sweep(circ, ellipse(PHASE_R, -0.001, 0.0090, 0.0125, 6), arc_angles(edge - into * 3.0, edge, 3.0),
                     mat=0)
    if weight == "Light":
        return
    T, B, din, dout = band_dims(core, weight)
    if weight == "Medium":
        prof = [(din, T), (dout, T - 0.003), (dout, B + 0.003), (din, B)]
    else:
        prof = [(din, T + 0.001), (dout - 0.012, T - 0.001), (dout + 0.004, T - 0.012), (dout + 0.004, B + 0.008),
                (dout - 0.008, B), (din, B)]
    spans = list(_band_spans(core))
    ring(prof, 0, spans)
    ring(_tri(dout + (0.0040 if weight == "Heavy" else 0.0), T - 0.0126 if weight == "Heavy" else (T + B) / 2), 1,
         spans)
    ring([(din + 0.0015, B - 0.0010), (din + 0.0065, B - 0.0010), (din + 0.0040, B + 0.0010)], 2, spans)


def build_far(core, mats_glass, mats_frame, col):
    out = []
    for zone in ZONES:
        mb = MB()
        far_glass(mb, core, zone)
        out.append(mb.finish(f"HALO_{core}_Far_Glass_{zone}", mats_glass, smooth_angle=35, col=col))
    for weight in ("Light", "Medium", "Heavy"):
        mb = MB()
        far_frame(mb, core, weight)
        mats = mats_frame if weight != "Light" else mats_frame[:2]
        out.append(mb.finish(f"HALO_{core}_Far_Frame_{weight}", mats, smooth_angle=25, col=col))
    return out


# ------------------------------------------------------------------------------------------------ pip
def build_pip(mats, col):
    """Upright diamond facing -Y (the engine places 1-4 of them at HALO_<Core>_PIP_1..4)."""
    mb = MB()
    h, w, d = PIP_H, 0.0056, 0.0030
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
    crystal = [(0.0, -0.0175), (0.0078, -0.011), (0.0078, 0.011), (0.0, 0.0175)]
    mb.sweep(zc, crystal, [D(30 + 60 * i) for i in range(6)], mat=0, cap=False, loop=True, open_profile=True)
    front = [(0.0, 0.0255), (0.0042, 0.0245), (0.0080, 0.0205), (0.0098, 0.0150), (0.0098, 0.0095),
             (0.0060, 0.0080), (0.0, 0.0080)]
    rear = [(0.0, -0.0080), (0.0060, -0.0080), (0.0098, -0.0095), (0.0098, -0.0150), (0.0080, -0.0190),
            (0.0050, -0.0215), (0.0, -0.0220)]
    steps = [2 * math.pi * i / 12 for i in range(12)]
    mb.sweep(zc, front, steps, mat=1, cap=False, loop=True, open_profile=True)
    mb.sweep(zc, rear, steps, mat=1, cap=False, loop=True, open_profile=True)
    mb.sweep(zc, rounded_rect(0.0090, 0.0101, 0.0168, 0.0186, 0.0004), steps, mat=0, loop=True)
    bm = mb.bm
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(D(90), 3, "Y"))
    fin = [(-0.0150, -0.0070), (-0.0150, 0.0070), (-0.0230, 0.0058), (-0.0340, 0.0040), (-0.0440, 0.0034),
           (-0.0380, 0.0), (-0.0440, -0.0034), (-0.0340, -0.0040), (-0.0230, -0.0058)]
    fv = mb.prism(fin, (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), -0.0011, 0.0011, mat=0)
    R = 0.245 / 1.25
    for f in fv:
        for v in f.verts:
            if v.co.x < -0.0149 and not v.tag:
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
        mb._uv(f, [(l.vert.co.x, l.vert.co.y) for l in f.loops])


def build_shards(mats, col):
    out = []
    hexp = [(0.015 * math.cos(D(60 * i)), 0.015 * math.sin(D(60 * i))) for i in range(6)]
    a_poly = hexp[:1] + [(0.0105, 0.0085), (0.0035, 0.0128)] + hexp[2:]
    b_poly = [(0.0, 0.0), (0.021, -0.001), (0.0098, 0.0185), (0.0035, 0.0105)]
    c_poly = [(-0.017, -0.003), (0.011, -0.0055), (0.019, 0.0005), (0.004, 0.0052), (-0.013, 0.0032)]
    for nm, poly, th, rt in (("A", a_poly, 0.0042, 0.0016), ("B", b_poly, 0.0050, 0.0018),
                             ("C", c_poly, 0.0032, 0.0012)):
        mb = MB()
        _gem_prism(mb, poly, th, rt)
        out.append(mb.finish(f"HALO_Shard_{nm}", mats, smooth_angle=5, col=col))
    return out


# ------------------------------------------------------------------------------------------------ pickups
# Hand-sized core canisters (~0.09 m wide, ~0.06 m tall), origin at the bottom centre, front = -Y.
# The top window repeats the ring silhouette; side windows show the tier glow from any angle.
def _angles_any(shape, a0, a1, step=4.0):
    return hex_angles(a0, a1) if shape is hexs else arc_angles(a0, a1, step)


def _side_windows(mb, shape, d, z0, z1, angles, half=9.0, depth=0.0025, step=4.0):
    """Glass window slots on the canister wall (slightly proud of the wall)."""
    for a in angles:
        prof = strip(d - 0.002, d + depth, z0, z1)
        mb.sweep(shape, prof, _angles_any(shape, a - half, a + half, step), mat=0)


def _disc_window(mb, shape, d, z0, z1, mat, steps=48):
    prof = [(0.0, z0), (d, z0), (d, z1 - 0.0012), (d - 0.0012, z1), (0.0, z1)]
    mb.lathe(shape, prof, steps=steps, mat=mat)


def pickup_bulwark(mb):
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
        lug = rounded_rect(0.037, 0.0465, 0.002, 0.056, 0.002)
        mb.sweep(hexs, lug, hex_angles(a - 4.5, a + 4.5), mat=1)


def pickup_mender(mb):
    body = [(0.0, 0.0), (0.037, 0.0), (0.042, 0.005), (0.042, 0.046), (0.039, 0.050), (0.0, 0.050)]
    mb.lathe(circ, body, steps=24, mat=1)
    band = [(0.0, 0.009), (0.0425, 0.009), (0.0425, 0.015), (0.0, 0.015)]
    mb.lathe(circ, band, steps=24, mat=2)
    angs = [2 * math.pi * i / 24 for i in range(24)]
    # twin glass rings on the lid, the outer one lower (echoes the stepped Mender halo)
    for r, z0 in ((0.0195, 0.0475), (0.0325, 0.0455)):
        mb.sweep(circ, strip(r - 0.0038, r + 0.0038, z0, z0 + 0.0085), angs, mat=0, loop=True)
    cap = [(0.0, 0.049), (0.0105, 0.049), (0.0105, 0.055), (0.0085, 0.057), (0.0, 0.057)]
    mb.lathe(circ, cap, steps=12, mat=1)
    for k in range(4):  # bridges between the twin rings
        a = 45 + 90 * k
        mb.sweep(circ, rounded_rect(0.014, 0.038, 0.049, 0.0565, 0.001), arc_angles(a - 4, a + 4, 8), mat=1)
    _side_windows(mb, circ, 0.042, 0.020, 0.040, (270, 90), half=7.0, step=7.0)
    _side_windows(mb, circ, 0.042, 0.020, 0.040, (255, 285, 75, 105), half=2.2, step=4.4)


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
    for i in range(4):
        t = D(-90 + 90 * i / 3)
        prof.append((0.031 + 0.010 * math.cos(t), 0.010 + 0.010 * math.sin(t)))
    for i in range(1, 4):
        t = D(90 * i / 3)
        prof.append((0.031 + 0.010 * math.cos(t), 0.038 + 0.010 * math.sin(t)))
    prof.append((0.0, 0.048))
    mb.lathe(circ, prof, steps=20, mat=1)
    foot = [(0.0, 0.0005), (0.0330, 0.0005), (0.0330, 0.0045), (0.0, 0.0045)]
    mb.lathe(circ, foot, steps=20, mat=2)
    lens = ellipse(0.024, 0.048, 0.0062, 0.0042, 6)
    mb.sweep(circ, lens, arc_angles(90 + 24, 450 - 24, 12.0), mat=0)
    for e, sgn in ((90 + 24, 1), (450 - 24, -1)):
        mb.sweep(circ, ellipse(0.024, 0.048, 0.0072, 0.0050, 6), arc_angles(e, e + sgn * 3.5, 3.5), mat=1)
    cap = [(0.0, 0.047), (0.010, 0.047), (0.010, 0.0505), (0.0075, 0.0525), (0.0, 0.0525)]
    mb.lathe(circ, cap, steps=12, mat=0)
    eq = strip(0.0405, 0.0425, 0.026, 0.032)
    mb.sweep(circ, eq, arc_angles(90 + 24, 450 - 24, 12.0), mat=0)
    # the Phase fork, small: two glass prongs either side of the back gap
    for edge, into in ((90 - 24 - 2.0, 1), (90 + 24 + 2.0, -1)):   # on the lens end collars
        o, t, n, up = frame_at(circ, D(edge), 0.024, 0.048)
        mb.prism([(-0.002, 0.0), (0.0015, 0.0), (0.0030, 0.0090), (0.0005, 0.0105), (-0.002, 0.0085)],
                 o, t * into, up, n, -0.0016, 0.0016, mat=0)


PICKUPS = {"Bulwark": pickup_bulwark, "Mender": pickup_mender, "Volt": pickup_volt, "Phase": pickup_phase}


def build_pickup(core, mats, col):
    mb = MB()
    PICKUPS[core](mb)
    return mb.finish(f"HALO_Core_{core}", mats, smooth_angle=30, col=col)
