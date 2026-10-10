"""Stage C for build_kestrel.py: KESTREL's recon eyepiece (DIRECTION_LOG item 3, concept v06).

A SMALL translucent TEAL hexagonal lens over her LEFT eye (+X): a 3 mm glowing teal rim on a slim graphite frame
(no deep housing), see-through tinted glass, about 1 cm in front of the eye. Thin dark straps hold it: two run
along the left temple to a compact earpiece on her left ear, one runs diagonally up across the forehead and tucks
under the fringe on her right (as in v06). Stage A rebuilt her left eye socket (kes_geo) and stage B painted the
mirrored eye on it, so the lens no longer has to hide the old baked TRELLIS disc and can be the size v06 shows:
it covers the eye only, not the brow or the cheek.

Result: one mesh object KES_Eyepiece with three materials (M_KES_EyeGlass, M_KES_EyeGlow, M_KES_Graphite);
stage D skins it rigidly to the head bone.
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import blender_common as bc
import kes_lib as K
from kes_lib import log

TEAL = (0.0, 0.70, 0.62)
GLASS_TINT = (0.0, 0.42, 0.37)            # a darker teal for the glass, so the eye behind it reads
GRAPHITE = (0.030, 0.033, 0.040)

# lens layout (metres). Centred on her painted left eye: the mirror of the right eye (iris x -0.028, z 1.5186;
# corners x -0.0045 / -0.0515) across the face plane is iris x ~0.038, corners 0.0145 / 0.0615.
LENS_C = Vector((0.0380, -0.030, 1.5175))   # y is solved so the glass clears the face
LENS_W = 0.052
LENS_H = 0.036
LENS_CHAMFER = 0.0115
LENS_YAW = math.radians(15.0)            # outer edge swings back to follow the face
RIM_W = 0.0030                           # glowing front lip width (the "3 mm frame")
FRAME_D = 0.0035                         # frame depth behind the glass plane (slim, no goggle cup)
GLASS_BULGE = 0.0012
CLEAR = 0.0030                           # every face vertex inside the outline stays this far behind the glass
EAR = Vector((0.1135, 0.064, 1.507))     # outer surface of her left ear (measured from skin texels)
HEAD_C = Vector((0.005, 0.015, 1.545))
STRAP_OFF = 0.0015                       # strap centre-line offset over the skin / hair surface


def materials():
    glass = bpy.data.materials.get("M_KES_EyeGlass")
    if glass is None:
        glass = bc.material("M_KES_EyeGlass", GLASS_TINT, rough=0.1, emission=GLASS_TINT, emission_strength=0.08,
                            alpha=0.38)
        glass.use_backface_culling = False
        try:
            glass.surface_render_method = "BLENDED"
        except Exception:
            pass
    glow = bc.material("M_KES_EyeGlow", TEAL, rough=0.4, emission=TEAL, emission_strength=1.2)
    graph = bc.material("M_KES_Graphite", GRAPHITE, rough=0.55)
    return glass, glow, graph


def lens_frame():
    U = Vector((math.cos(LENS_YAW), math.sin(LENS_YAW), 0.0))        # lens width axis (her left = +)
    V = Vector((0.0, 0.0, 1.0))
    Nf = Vector((math.sin(LENS_YAW), -math.cos(LENS_YAW), 0.0))      # glass normal, pointing out of the face
    return U, V, Nf


def hex_outline(w, h, ch):
    """Elongated hexagon (flat top/bottom, pointed sides) as (u, v) points, counter-clockwise seen from the front."""
    return [(w / 2, 0.0), (w / 2 - ch, h / 2), (-w / 2 + ch, h / 2), (-w / 2, 0.0), (-w / 2 + ch, -h / 2),
            (w / 2 - ch, -h / 2)]


def inset_poly(pts, d):
    """Inset a convex polygon by d (offset each edge inward, intersect neighbours)."""
    n = len(pts)
    P = [np.array(p) for p in pts]
    # orientation (signed area) so 'inward' is consistent
    area = sum(P[i][0] * P[(i + 1) % n][1] - P[(i + 1) % n][0] * P[i][1] for i in range(n))
    sgn = 1.0 if area > 0 else -1.0
    lines = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        t = (b - a) / np.linalg.norm(b - a)
        nrm = np.array([-t[1], t[0]]) * sgn       # inward normal for CCW
        lines.append((a + nrm * d, t))
    out = []
    for i in range(n):
        (p1, t1), (p2, t2) = lines[i - 1], lines[i]
        A = np.array([t1, -t2]).T
        s = np.linalg.solve(A, p2 - p1)
        out.append(tuple(p1 + t1 * s[0]))
    return out


def solve_plane(body, U, V, Nf, c):
    """Push the glass plane forward until every body vertex inside the lens outline is >= CLEAR behind it.
    Returns the plane centre and the glass-to-eye distance at the lens centre."""
    co = K.mesh_co(body.data)
    d = co - np.array(c[:])
    u = d @ np.array(U[:])
    v = d @ np.array(V[:])
    n = d @ np.array(Nf[:])
    inside = (np.abs(u) < LENS_W / 2 + 0.002) & (np.abs(v) < LENS_H / 2 + 0.002) & (co[:, 1] < 0.0) & (n > -0.03)
    front = n[inside].max() if inside.any() else 0.0
    # move the plane straight forward (-Y) so the lens stays centred where it was designed in x
    O = c + Vector((0.0, -(front + CLEAR) / max(-Nf.y, 0.5), 0.0))
    eye = (np.abs(u) < 0.004) & (np.abs(v) < 0.004) & (co[:, 1] < 0.0) & (n > -0.03)
    gap = float((O - c).dot(Nf) - n[eye].max()) if eye.any() else float("nan")
    return O, gap


def build_lens(bm, O, U, V, Nf, mi_glass, mi_glow, mi_graph):
    """Thin hex frame: glowing front lip (RIM_W wide), graphite outer wall / back ring / inner wall FRAME_D deep,
    and a single slightly bulged glass layer just behind the lip."""
    def P(u, v, n=0.0):
        return O + U * u + V * v + Nf * n

    outer = hex_outline(LENS_W, LENS_H, LENS_CHAMFER)
    inner = inset_poly(outer, RIM_W)
    glass = inset_poly(outer, RIM_W * 0.6)
    k = len(outer)
    lip = 0.0008
    vo = [bm.verts.new(P(u, v, lip)) for u, v in outer]
    vi = [bm.verts.new(P(u, v, lip)) for u, v in inner]
    vo2 = [bm.verts.new(P(u, v, -FRAME_D)) for u, v in outer]
    vi2 = [bm.verts.new(P(u, v, -FRAME_D)) for u, v in inner]
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((vo[i], vo[j], vi[j], vi[i])).material_index = mi_glow        # front lip (glow)
        bm.faces.new((vo[j], vo[i], vo2[i], vo2[j])).material_index = mi_graph     # outer wall
        bm.faces.new((vo2[j], vo2[i], vi2[i], vi2[j])).material_index = mi_graph   # back ring
        bm.faces.new((vi[i], vi[j], vi2[j], vi2[i])).material_index = mi_graph     # inner wall
    rings = [glass, [(u * 0.55, v * 0.55) for u, v in glass]]
    vs = [[bm.verts.new(P(u, v, -0.0006 + bul)) for u, v in pts]
          for pts, bul in zip(rings, (0.0, GLASS_BULGE * 0.75))]
    ctr = bm.verts.new(P(0.0, 0.0, -0.0006 + GLASS_BULGE))
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((vs[0][i], vs[0][j], vs[1][j], vs[1][i])).material_index = mi_glass
        bm.faces.new((vs[1][i], vs[1][j], ctr)).material_index = mi_glass
    return outer


def surface_projector(body):
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(body, dg)

    def proj(p, offset):
        loc, nrm, _, _ = bvh.find_nearest(p)
        out = (loc - HEAD_C)
        if nrm.dot(out) < 0:
            nrm = -nrm
        # blend with the radial direction: TRELLIS normals are noisy
        n = (nrm * 0.6 + out.normalized() * 0.4).normalized()
        return loc + n * offset, n
    return proj


def catmull(points, samples=10):
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(points[-1])
    return out


def build_strap(bm, proj, guide, width, thick, offset, mi, tuck_end=0.0, free_start=0):
    """Flat strap following the head surface through the guide points (first `free_start` points are used as-is,
    e.g. the attachment on the lens housing). Rectangular section, wide face tangent to the surface."""
    pts = catmull([Vector(g) for g in guide], 8)
    nfree = free_start * 8

    def project_all(pts):
        path, nrms = [], []
        for i, p in enumerate(pts):
            q, n = proj(p, offset)
            w = min(i / max(nfree, 1), 1.0) if nfree else 1.0
            path.append(p.lerp(q, w * w))
            nrms.append(n)
        return path, nrms

    path, nrms = project_all(pts)
    # the head surface (hair strands, TRELLIS facets) is noisy: relax the path and the normals, re-project, repeat
    for _ in range(4):
        sm = [path[0]] + [(path[i - 1] + path[i] * 2 + path[i + 1]) / 4 for i in range(1, len(path) - 1)] + [path[-1]]
        path, nrms2 = project_all(sm)
        nrms = [nrms2[0]] + [(nrms2[i - 1] + nrms2[i] * 2 + nrms2[i + 1]).normalized() for i in range(1, len(nrms2) - 1)] + [nrms2[-1]]
    for _ in range(3):
        path = [path[0]] + [(path[i - 1] + path[i] * 2 + path[i + 1]) / 4 for i in range(1, len(path) - 1)] + [path[-1]]
    # final re-projection: the strap hugs the skin / hair (review: the straps floated off the temple)
    path, nrms2 = project_all(path)
    nrms = [nrms2[0]] + [(nrms2[i - 1] + nrms2[i] * 2 + nrms2[i + 1]).normalized()
                         for i in range(1, len(nrms2) - 1)] + [nrms2[-1]]
    if tuck_end:
        path[-1] = path[-1] - nrms[-1] * tuck_end
        path[-2] = path[-2] - nrms[-2] * tuck_end * 0.4
    secs = []
    for i, (p, n) in enumerate(zip(path, nrms)):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        b = n.cross(t).normalized()
        n2 = t.cross(b).normalized()
        sec = [p + b * (width / 2) + n2 * (thick / 2), p - b * (width / 2) + n2 * (thick / 2),
               p - b * (width / 2) - n2 * (thick / 2), p + b * (width / 2) - n2 * (thick / 2)]
        secs.append([bm.verts.new(s) for s in sec])
    for a, b2 in zip(secs[:-1], secs[1:]):
        for k in range(4):
            f = bm.faces.new((a[k], a[(k + 1) % 4], b2[(k + 1) % 4], b2[k]))
            f.material_index = mi
            f.smooth = True
    for cap, flip in ((secs[0], True), (secs[-1], False)):
        f = bm.faces.new(cap if not flip else list(reversed(cap)))
        f.material_index = mi
    return path


def build_earpiece(bm, mi_graph, mi_glow):
    """Compact rounded pod on the outside of her left ear, with a small teal status light."""
    tmp = bc.box("_earpiece_tmp", (0.016, 0.027, 0.036), loc=EAR + Vector((0.007, -0.002, 0.0)),
                 rot=(0, 0, -8), bevel=0.0055, segments=3)
    bc.apply_modifiers(tmp)
    me = tmp.data
    me.transform(tmp.matrix_world)
    led = bc.cylinder("_earpiece_led", 0.0028, 0.0016, loc=EAR + Vector((0.0155, -0.006, 0.006)), rot=(0, 90, -8),
                      verts=12)
    bpy.context.view_layer.update()          # matrix_world is stale until the depsgraph updates
    led.data.transform(led.matrix_world)
    base = len(bm.verts)
    for ob, mi in ((tmp, mi_graph), (led, mi_glow)):
        vmap = [bm.verts.new(v.co) for v in ob.data.vertices]
        for p in ob.data.polygons:
            try:
                f = bm.faces.new([vmap[i] for i in p.vertices])
                f.material_index = mi
                f.smooth = mi == mi_graph
            except ValueError:
                pass
        bpy.data.objects.remove(ob, do_unlink=True)
    return base


def build_eyepiece():
    body = K.body()
    glass, glow, graph = materials()
    U, V, Nf = lens_frame()
    O, gap = solve_plane(body, U, V, Nf, LENS_C)
    log(f"eyepiece: glass plane centre {tuple(round(c, 4) for c in O)}, {gap * 1000:.1f} mm in front of the eye, "
        f"lens {LENS_W * 100:.1f} x {LENS_H * 100:.1f} cm")
    me = bpy.data.meshes.new("KES_Eyepiece")
    ob = bpy.data.objects.new("KES_Eyepiece", me)
    bpy.context.scene.collection.objects.link(ob)
    for m in (glass, glow, graph):
        me.materials.append(m)
    bm = bmesh.new()
    build_lens(bm, O, U, V, Nf, 0, 1, 2)

    def P(u, v, n=0.0):
        return O + U * u + V * v + Nf * n

    build_earpiece(bm, 2, 1)
    proj = surface_projector(body)
    # temple straps: from the frame's outer (temple-side) walls to the front of the earpiece
    w2 = LENS_W / 2
    up_a = P(w2 - LENS_CHAMFER * 0.45, LENS_H * 0.36, -FRAME_D * 0.5)
    lo_a = P(w2 - LENS_CHAMFER * 0.45, -LENS_H * 0.36, -FRAME_D * 0.5)
    ear_up = EAR + Vector((0.004, -0.016, 0.011))
    ear_lo = EAR + Vector((0.004, -0.016, -0.010))
    up_mid = Vector((0.090, -0.006, 1.528))
    lo_mid = Vector((0.090, -0.004, 1.500))
    build_strap(bm, proj, [up_a, up_a + U * 0.006, up_mid, ear_up], 0.0040, 0.0012, STRAP_OFF, 2, free_start=1)
    build_strap(bm, proj, [lo_a, lo_a + U * 0.006, lo_mid, ear_lo], 0.0040, 0.0012, STRAP_OFF, 2, free_start=1)
    # forehead strap: from the upper inner corner of the lens diagonally up across the forehead, tucking under
    # the fringe on her right
    fh_a = P(-w2 + LENS_CHAMFER * 0.6, LENS_H * 0.5 - 0.0015, -FRAME_D * 0.5)
    fh = [fh_a, Vector((0.012, -0.074, 1.550)), Vector((-0.004, -0.073, 1.561)), Vector((-0.019, -0.070, 1.570))]
    build_strap(bm, proj, fh, 0.0038, 0.0011, STRAP_OFF, 2, tuck_end=0.003, free_start=1)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    bc.shade_smooth(ob, 35)
    bc.smart_uv(ob, angle=60, margin=0.02)
    log(f"eyepiece: {K.tri_count(ob)} tris")
    return ob
