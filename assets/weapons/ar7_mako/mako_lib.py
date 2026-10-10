"""Geometry helpers for the AR-7 MAKO build (kept next to build_mako.py; tools/*.py stay untouched).

All coordinates are metres in Blender axes: muzzle -Y, Z up, shooter's RIGHT = -X, LEFT = +X.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(PROJECT, "tools"))
import blender_common as bc  # noqa: E402

# ------------------------------------------------------------------------------------------- 2D helpers


def _line_isect(p1, d1, p2, d2):
    """Intersection of the lines p1 + t*d1 and p2 + s*d2 (2D)."""
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-12:
        return None
    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
    return (p1[0] + t * d1[0], p1[1] + t * d1[1])


def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2


def offset_poly(pts, d):
    """Offset a simple polygon inward by d (negative d = outward). Works for either winding."""
    ccw = poly_area(pts) > 0
    n = len(pts)
    lines = []
    for i in range(n):
        p0, p1 = pts[i], pts[(i + 1) % n]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        ln = math.hypot(dx, dy)
        # inward normal: left normal for CCW polygons
        nx, ny = (-dy / ln, dx / ln) if ccw else (dy / ln, -dx / ln)
        lines.append(((p0[0] + nx * d, p0[1] + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        a = lines[i - 1]
        b = lines[i]
        q = _line_isect(a[0], a[1], b[0], b[1])
        out.append(q if q else b[0])
    return out


def round_poly(pts, r, segs=3, radii=None):
    """Fillet every corner of a polygon with an arc of radius r (or per-corner radii)."""
    n = len(pts)
    out = []
    for i in range(n):
        rr = radii[i] if radii else r
        p = Vector((*pts[i], 0))
        a = Vector((*pts[i - 1], 0))
        b = Vector((*pts[(i + 1) % n], 0))
        if rr <= 0 or segs < 1:
            out.append(pts[i])
            continue
        va = (a - p).normalized()
        vb = (b - p).normalized()
        ang = va.angle(vb)
        if ang < 1e-3 or ang > math.pi - 1e-3:
            out.append(pts[i])
            continue
        t = rr / math.tan(ang / 2)
        t = min(t, (a - p).length * 0.49, (b - p).length * 0.49)
        rr = t * math.tan(ang / 2)
        pa = p + va * t
        pb = p + vb * t
        bis = (va + vb).normalized()
        c = p + bis * (rr / math.sin(ang / 2))
        a0 = math.atan2(pa.y - c.y, pa.x - c.x)
        a1 = math.atan2(pb.y - c.y, pb.x - c.x)
        da = a1 - a0
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        for k in range(segs + 1):
            aa = a0 + da * k / segs
            out.append((c.x + rr * math.cos(aa), c.y + rr * math.sin(aa)))
    return out


def stadium_pts(length, height, segs=4, cx=0.0, cy=0.0):
    """Pill outline (u along length, v along height) centred on (cx, cy)."""
    r = height / 2
    half = max(length / 2 - r, 0.0)
    pts = []
    for k in range(segs + 1):  # right cap
        a = -math.pi / 2 + math.pi * k / segs
        pts.append((cx + half + r * math.cos(a), cy + r * math.sin(a)))
    for k in range(segs + 1):  # left cap
        a = math.pi / 2 + math.pi * k / segs
        pts.append((cx - half + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def circle_pts(r, segs=16, cx=0.0, cy=0.0, a0=0.0):
    return [(cx + r * math.cos(a0 + 2 * math.pi * k / segs), cy + r * math.sin(a0 + 2 * math.pi * k / segs))
            for k in range(segs)]


# ------------------------------------------------------------------------------------------- objects
def new_obj(name, bm, col=None, mat=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    if mat is not None:
        ob.data.materials.append(mat)
    return ob


def _map(axis, u, v, w):
    """2D (u, v) in the plane perpendicular to `axis`, w along the axis -> (x, y, z)."""
    if axis == "X":
        return (w, u, v)
    if axis == "Y":
        return (u, w, v)
    return (u, v, w)


def prism(name, pts, axis, a0, a1, col=None, mat=None):
    """Closed polygon pts (2D) extruded along `axis` from a0 to a1.
    axis X: pts are (y, z).  axis Y: pts are (x, z).  axis Z: pts are (x, y)."""
    bm = bmesh.new()
    v0 = [bm.verts.new(_map(axis, u, v, a0)) for (u, v) in pts]
    v1 = [bm.verts.new(_map(axis, u, v, a1)) for (u, v) in pts]
    n = len(pts)
    bm.faces.new(v0)
    bm.faces.new(list(reversed(v1)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, col, mat)


def loft(name, sections, axis, col=None, mat=None, cap=True):
    """Loft between several 2D sections with equal vertex counts: sections = [(w, pts), ...]."""
    bm = bmesh.new()
    rings = [[bm.verts.new(_map(axis, u, v, w)) for (u, v) in pts] for (w, pts) in sections]
    n = len(rings[0])
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    if cap:
        bm.faces.new(rings[0])
        bm.faces.new(list(reversed(rings[-1])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, col, mat)


def tube(name, outer, inner, axis, a0, a1, col=None, mat=None):
    """Hollow prism: outer and inner 2D outlines (same vertex count, same winding)."""
    bm = bmesh.new()
    o0 = [bm.verts.new(_map(axis, u, v, a0)) for (u, v) in outer]
    o1 = [bm.verts.new(_map(axis, u, v, a1)) for (u, v) in outer]
    i0 = [bm.verts.new(_map(axis, u, v, a0)) for (u, v) in inner]
    i1 = [bm.verts.new(_map(axis, u, v, a1)) for (u, v) in inner]
    n = len(outer)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((o0[i], o0[j], o1[j], o1[i]))
        bm.faces.new((i0[j], i0[i], i1[i], i1[j]))
        bm.faces.new((o0[j], o0[i], i0[i], i0[j]))
        bm.faces.new((o1[i], o1[j], i1[j], i1[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, col, mat)


def box(name, x0, x1, y0, y1, z0, z1, col=None, mat=None):
    return prism(name, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], "Z", z0, z1, col, mat)


def cyl(name, r, axis, a0, a1, c=(0.0, 0.0), segs=16, col=None, mat=None, a_off=None):
    """Cylinder along `axis`, centred at c (2D in the perpendicular plane)."""
    if a_off is None:
        a_off = math.pi / segs
    return prism(name, circle_pts(r, segs, c[0], c[1], a_off), axis, a0, a1, col, mat)


def lathe_y(name, profile, y_ref, direction=1, c=(0.0, 0.0), steps=20, col=None, mat=None, a_off=None):
    """Revolve [(r, h), ...] around a Y-parallel axis at (x, z) = c. y = y_ref + direction * h.
    Profile must start and end at r = 0 (closed solid)."""
    if a_off is None:
        a_off = math.pi / steps
    bm = bmesh.new()
    rings = []
    for i in range(steps):
        a = a_off + 2 * math.pi * i / steps
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for (r, h) in profile:
            ring.append(bm.verts.new((c[0] + r * ca, y_ref + direction * h, c[1] + r * sa)))
        rings.append(ring)
    for i in range(steps):
        r0, r1 = rings[i], rings[(i + 1) % steps]
        for j in range(len(profile) - 1):
            try:
                bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    # degenerate quads at the poles become triangles after remove_doubles
    bmesh.ops.dissolve_degenerate(bm, dist=1e-7, edges=bm.edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, col, mat)


def apply_xform(ob):
    me = ob.data
    me.transform(ob.matrix_basis)
    ob.matrix_basis = Matrix.Identity(4)
    return ob


def rotate(ob, axis, deg, pivot=(0, 0, 0)):
    """Rotate mesh data about a world-axis line through pivot."""
    p = Vector(pivot)
    m = Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-p)
    ob.data.transform(m)
    return ob


def move(ob, d):
    ob.data.transform(Matrix.Translation(Vector(d)))
    return ob


def mirror_x_mesh(ob):
    ob.data.transform(Matrix.Scale(-1, 4, (1, 0, 0)))
    ob.data.flip_normals()
    return ob


def set_origin(ob, point):
    """Put the object origin at a world point without moving the mesh (object assumed unparented)."""
    p = Vector(point)
    mw = ob.matrix_world.copy()
    local = mw.inverted() @ p
    ob.data.transform(Matrix.Translation(-local))
    ob.matrix_world = mw @ Matrix.Translation(local)
    return ob


def join(objs, name=None):
    objs = [o for o in objs if o is not None]
    for o in objs:
        if o.modifiers:
            bc.apply_modifiers(o)
        apply_xform(o)
    bm = bmesh.new()
    base = objs[0]
    mats = []
    for o in objs:
        for m in o.data.materials:
            if m not in mats:
                mats.append(m)
    for o in objs:
        me = o.data
        remap = [mats.index(m) for m in me.materials] if me.materials else [0]
        tmp = bmesh.new()
        tmp.from_mesh(me)
        for f in tmp.faces:
            f.material_index = remap[f.material_index] if f.material_index < len(remap) else 0
        me2 = bpy.data.meshes.new("_tmp")
        tmp.to_mesh(me2)
        tmp.free()
        bm.from_mesh(me2)
        bpy.data.meshes.remove(me2)
    me = bpy.data.meshes.new(name or base.name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    keep_name = name or base.name
    cols = list(base.users_collection)
    for o in objs:
        old = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if old.users == 0:
            bpy.data.meshes.remove(old)
    ob = bpy.data.objects.new(keep_name, me)
    for c in cols or [bpy.context.scene.collection]:
        c.objects.link(ob)
    ob.name = keep_name
    ob.data.name = keep_name
    return ob


def boolean(ob, cutters, op="DIFFERENCE", transfer=True, solver="EXACT"):
    """Boolean ob with one or many cutters (joined into one temporary operand). Cutters are deleted.
    transfer=True gives cut faces the cutter's material."""
    if not isinstance(cutters, (list, tuple)):
        cutters = [cutters]
    cutters = [c for c in cutters if c is not None]
    if not cutters:
        return ob
    cut = join(cutters, "_cutter") if len(cutters) > 1 else cutters[0]
    if cut.modifiers:
        bc.apply_modifiers(cut)
    apply_xform(cut)
    m = ob.modifiers.new("Bool", "BOOLEAN")
    m.object = cut
    m.operation = op
    m.solver = solver
    try:
        m.use_self = True  # joined cutters may overlap each other
    except Exception:
        pass
    try:
        m.material_mode = "TRANSFER" if transfer else "INDEX"
    except Exception:
        pass
    # keep any modifiers already stacked (none expected) - apply only this one
    bc.apply_modifiers(ob, only=[m.name])
    old = cut.data
    bpy.data.objects.remove(cut, do_unlink=True)
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return ob


def union(objs, name):
    """Exact boolean union of several closed meshes into the first one."""
    base = objs[0]
    for o in objs:
        apply_xform(o)
    if len(objs) > 1:
        boolean(base, list(objs[1:]), op="UNION")
    base.name = name
    base.data.name = name
    return base


def intersect(a, b, name=None):
    boolean(a, b, op="INTERSECT")
    if name:
        a.name = name
        a.data.name = name
    return a


def clean(ob, dist=1e-6, dissolve_angle=0.5):
    """Merge doubles and dissolve coplanar splits left by booleans (keeps materials apart)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    if dissolve_angle:
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(dissolve_angle), verts=bm.verts, edges=bm.edges,
                                 delimit={"MATERIAL", "SEAM", "SHARP"})
    bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges)
    bm.to_mesh(ob.data)
    bm.free()
    return ob


def _seg_seg_dist(p1, q1, p2, q2):
    """Shortest distance between the segments p1-q1 and p2-q2 (3D)."""
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1.dot(d1), d2.dot(d2), d2.dot(r)
    if a < 1e-18 and e < 1e-18:
        return r.length
    if a < 1e-18:
        s, t = 0.0, min(max(f / e, 0.0), 1.0)
    else:
        c = d1.dot(r)
        if e < 1e-18:
            t, s = 0.0, min(max(-c / a, 0.0), 1.0)
        else:
            b = d1.dot(d2)
            den = a * e - b * b
            s = min(max((b * f - c * e) / den, 0.0), 1.0) if den > 1e-18 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, min(max(-c / a, 0.0), 1.0)
            elif t > 1.0:
                t, s = 1.0, min(max((b - c) / a, 0.0), 1.0)
    return ((p1 + d1 * s) - (p2 + d2 * t)).length


def local_bevel_offsets(bm, flags, width, k=0.9, iters=10):
    """Per-edge bevel offsets that pass Blender's own overlap test, computed locally (round 2 of the r2 review).

    Blender's Clamp Overlap is GLOBAL: bmesh_bevel's geometry_collide_offset() is evaluated for every edge and
    the smallest result scales EVERY bevel of the modifier. Boolean slivers with 2-14 um edges therefore squashed
    whole parts: measured on the r3 build, the Upper's 1.6 mm bevel came out 0.010 mm wide, the Lower's 1.5 mm
    0.035 mm, the mags' 2 mm 0.056 mm, stock_light's 2.2 mm 0.021 mm, the dust cover's 0.002 mm, so most hard
    edges had no real chamfer, only hardened normals. Here the same test runs per edge B and per face side
    (A = B's neighbour at its start, C at its end, th1 / th2 = the corner angles, k* = offsets):
        (kA + kB cos th1) / sin th1 + (kC + kB cos th2) / sin th2 <= k * len(B)      (B collapses)
        kB <= k * len(A) * sin th1  if A is not bevelled (same for C)           (B's bevel slides along A)
    plus, for two bevelled edges of one face that share no vertex, kA + kB <= k * their distance (thin strips);
    and only the offending offsets are scaled down, a few passes until stable. With every edge inside its own
    limit, Blender's global clamp has nothing left to squash, so Clamp Overlap stays on as a safety net.
    Returns {edge index: offset}."""
    bm.edges.ensure_lookup_table()
    off = {e.index: width for e in bm.edges if flags[e.index]}
    if not off:
        return off
    # thin strips: two bevelled edges of the same face that share no vertex advance toward each other across
    # it (e.g. the 3 mm wall between stock_standard's tube channel and its top). Their offsets must sum to less
    # than k x their distance. The pairs are fixed, so collect them once.
    pairs = []
    for f in bm.faces:
        es = [e for e in f.edges if e.index in off]
        if len(es) < 2:
            continue
        for a in range(len(es)):
            ea = es[a]
            for b in range(a + 1, len(es)):
                eb = es[b]
                if set(ea.verts) & set(eb.verts):
                    continue
                d = _seg_seg_dist(ea.verts[0].co, ea.verts[1].co, eb.verts[0].co, eb.verts[1].co)
                if d < 2.2 * width:
                    pairs.append((ea.index, eb.index, d))
    for _ in range(iters):
        scale = {}

        def cut(i, fac):
            if fac < scale.get(i, 1.0):
                scale[i] = fac
        for ia, ib, d in pairs:
            tot = off[ia] + off[ib]
            if tot > k * d:
                fac = k * d / max(tot, 1e-12)
                cut(ia, fac)
                cut(ib, fac)
        for B in bm.edges:
            lb_len = B.calc_length()
            for lb in B.link_loops:
                nb = lb.link_loop_next
                A, C = lb.link_loop_prev.edge, nb.edge
                if A is B or C is B:
                    continue
                th1, th2 = lb.calc_angle(), nb.calc_angle()
                s1, s2 = math.sin(th1), math.sin(th2)
                ka, kb, kc = off.get(A.index, 0.0), off.get(B.index, 0.0), off.get(C.index, 0.0)
                proj = 0.0
                if s1 > 1e-6:
                    proj += (ka + math.cos(th1) * kb) / s1
                if s2 > 1e-6:
                    proj += (kc + math.cos(th2) * kb) / s2
                if proj > k * lb_len and proj > 1e-12:
                    fac = k * lb_len / proj
                    for e, kk in ((A, ka), (B, kb), (C, kc)):
                        if kk > 0:
                            cut(e.index, fac)
                if kb > 0:
                    for E, kk, sn in ((A, ka, s1), (C, kc, s2)):
                        if kk == 0.0:
                            lim = k * E.calc_length() * sn
                            if kb > lim:
                                cut(B.index, lim / kb)
        if not scale:
            break
        for i, fac in scale.items():
            off[i] *= fac
    return off


def finish(ob, bevel=0.0015, segs=2, angle=30, smooth_angle=30, weight_fn=None, harden=True, profile=0.5,
           uv=True, min_frac=0.06):
    """Hard-surface finish: smooth shading + sharp-by-angle + bevel modifier (hardened normals).
    The bevelled edges are weight_fn(bm_edge) -> bool, or every edge sharper than `angle`. Each gets its own
    non-overlapping offset (local_bevel_offsets) through the bevel-weight attribute, so Blender's GLOBAL Clamp
    Overlap no longer squashes the whole part to a few microns. Edges whose safe offset is under min_frac * bevel
    are left sharp."""
    me = ob.data
    if not me.has_custom_normals:
        # r2 review fix: remove what would become zero-area triangles BEFORE the bevel adds hardened custom
        # normals (editing topology afterwards re-encodes those normals against new fans -> "melted" shading)
        prebevel_clean(ob)
    for p in me.polygons:
        p.use_smooth = True
    # Custom (hardened) normals are encoded relative to the sharp-edge fans: re-marking sharp edges afterwards
    # silently rotates them (measured up to 0.6 deviation -> the "melted" castle-nut highlights). So a mesh that
    # already carries custom normals (e.g. a join of finished parts) keeps its own sharp edges.
    if not me.has_custom_normals:
        try:
            me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        except Exception:
            pass
    if bevel > 0:
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = segs
        m.profile = profile
        m.use_clamp_overlap = True     # safety net only: the per-edge offsets already pass its test
        m.harden_normals = harden
        m.miter_outer = "MITER_ARC" if segs > 1 else "MITER_SHARP"
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.edges.ensure_lookup_table()
        if weight_fn is not None:
            flags = [bool(weight_fn(e)) for e in bm.edges]
        else:
            flags = [edge_angle_deg(e) > angle for e in bm.edges]
        off = local_bevel_offsets(bm, flags, bevel) if LOCAL_OFFSETS else {i: bevel for i, f in enumerate(flags) if f}
        bm.free()
        attr = me.attributes.get("bevel_weight_edge") or me.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
        for i in range(len(me.edges)):
            w = off.get(i, 0.0) / bevel
            attr.data[i].value = w if w >= min_frac else 0.0
        m.limit_method = "WEIGHT"
        try:
            m.edge_weight = "bevel_weight_edge"
        except Exception:
            pass
        if os.environ.get("MAKO_NO_SPIKEFIX") != "1":
            BEVEL_LOG[ob.name] = fix_bevel_spikes(ob, bevel)
    if uv and not me.uv_layers:
        bc.smart_uv(ob)
    return ob


LOCAL_OFFSETS = os.environ.get("MAKO_LOCAL_OFFSETS", "1") == "1"
BEVEL_LOG = {}   # object -> (passes, edges reduced, worst overshoot mm before the fix) of fix_bevel_spikes


def _seg_dist(p, a, b):
    ab = b - a
    t = 0.0 if ab.length_squared < 1e-18 else max(0.0, min(1.0, (p - a).dot(ab) / ab.length_squared))
    return (a + ab * t - p).length


def fix_bevel_spikes(ob, bevel, max_iter=8):
    """Safety net for the per-edge bevel offsets. A correct bevel keeps every new vertex ON the original surface
    (chamfer points slide along the adjacent faces; arc points sit at most 0.3 x offset inside) and every new
    face within 0.5 x offset of it (a 1-segment chamfer's centre on a 90 deg edge). An evaluated vertex beyond
    0.35 x width is a spike; a triangle centroid beyond 0.8 x width (corner patches reach ~0.67) is a fold spanning empty space (e.g.
    across a hole); a triangle facing more than 100 deg away from the surface under it is a fold lying on it. Around each one, the bevel weights of the original edges (within 2 widths of its vertices, or within
    its distance + 2 widths of its centre) are halved; re-evaluate; zero them on the last pass.
    Returns (passes, edges reduced, worst miss in mm before the fix)."""
    from mathutils.bvhtree import BVHTree
    me = ob.data
    attr = me.attributes.get("bevel_weight_edge")
    if attr is None:
        return (0, 0, 0.0)
    me.calc_loop_triangles()   # Blender's own tessellation: a fan over a concave n-gon would flip normals
    base = BVHTree.FromPolygons([v.co.copy() for v in me.vertices], [list(t.vertices) for t in me.loop_triangles],
                                epsilon=0.0)
    E = [(me.vertices[e.vertices[0]].co.copy(), me.vertices[e.vertices[1]].co.copy()) for e in me.edges]
    tol_v = 0.35 * bevel + 2e-5
    tol_f = 0.80 * bevel + 2e-5
    reduced = set()
    worst0 = 0.0

    def dist(p):
        hit = base.find_nearest(p)
        return hit[3] if hit[3] is not None else 0.0
    for it in range(max_iter + 1):
        me.update()
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        em = ev.to_mesh()
        bad = []   # (points to search around, radius)
        vd = [dist(v.co) for v in em.vertices]
        for v, d in zip(em.vertices, vd):
            if d > tol_v:
                bad.append(([v.co.copy()], d + 2 * bevel, d))
        em.calc_loop_triangles()
        for t in em.loop_triangles:   # triangle centroids (an n-gon's own centre can sit in its hole)
            pts = [em.vertices[i].co.copy() for i in t.vertices]
            c = (pts[0] + pts[1] + pts[2]) / 3
            hit = base.find_nearest(c)
            d = hit[3] if hit[3] is not None else 0.0
            if d > tol_f:
                bad.append(([c], d + 2 * bevel, d))
                bad.append((pts, 2 * bevel, d))
                continue
            # a fold lying ON the surface: its triangle faces the other way (a chamfer or corner patch turns at
            # most ~75 deg away from the faces it replaces)
            nrm = (pts[1] - pts[0]).cross(pts[2] - pts[0])
            if hit[1] is not None and nrm.length > 2e-10 and nrm.normalized().dot(hit[1]) < -0.17:
                bad.append((pts, 2 * bevel, 0.0))
                if it == 0 and os.environ.get("MAKO_SPIKE_DEBUG") == ob.name:
                    print("FOLD", ob.name, tuple(round(v, 4) for v in c), "area mm2", round(nrm.length * 5e5, 4),
                          "tri n", tuple(round(v, 2) for v in nrm.normalized()), "surf n",
                          tuple(round(v, 2) for v in hit[1]), "d", d)
        ev.to_mesh_clear()
        if it == 0:
            worst0 = max((d for _p, _r, d in bad), default=0.0)
        if not bad:
            return (it, len(reduced), round(worst0 * 1000, 3))
        last = it >= max_iter - 1
        for i, (a, b) in enumerate(E):
            w = attr.data[i].value
            if w <= 0:
                continue
            if any(_seg_dist(q, a, b) < r for pts, r, _d in bad for q in pts):
                # halve; below 8 % of the width the strip is just a micro face, so leave the edge sharp
                attr.data[i].value = 0.0 if (last or w * 0.5 < 0.08) else w * 0.5
                reduced.add(i)
    return (max_iter, len(reduced), round(worst0 * 1000, 3))


def degenerate_tris(ob, area=1e-10):
    """Zero-area triangles the exporter would write (same test as the review's GLB scan)."""
    me = ob.data
    me.calc_loop_triangles()
    vs = me.vertices
    n = 0
    for t in me.loop_triangles:
        a, b, c = (vs[i].co for i in t.vertices)
        if (b - a).cross(c - a).length * 0.5 < area:
            n += 1
    return n


def micro_faces(ob, area=1e-10):
    """Faces under 1e-10 m^2 (0.0001 mm^2): the review's 'zero_area' mesh-health metric."""
    return sum(1 for p in ob.data.polygons if p.area < area)


def _flat_corner(f, eps=2e-10):
    """A face corner whose two edges are (nearly) collinear or zero length: its tessellation can give a zero-area
    triangle."""
    for lp in f.loops:
        a = lp.link_loop_prev.vert.co - lp.vert.co
        b = lp.link_loop_next.vert.co - lp.vert.co
        if a.length < 1e-9 or b.length < 1e-9 or a.cross(b).length < eps:
            return True
    return False


def bake_clean(ob, area=1e-10, merge=5e-5, max_dev=95.0):
    """Apply the modifier stack, then remove the micro / zero-area faces the clamped bevels leave behind WITHOUT
    touching the shading (round 2 of the r2 review fix).

    Why it is safe now: the first version edited topology after the hardened-normal bevel and let Blender
    re-encode the custom normals against the new vertex fans, which "melted" the lower, magwell and guard. Here
    the final corner normals are read first, carried through every topology edit in loop attributes, and written
    back with normals_split_custom_set(), so each surviving corner keeps exactly the normal it had.
      1. collapse edges shorter than `merge` (50 um; the finest real detail is a 0.4 mm bevel): the zero-width
         strips and 10 um corner patches of bevels
         that clamp-overlap squeezed to nothing (they shaded as nothing anyway, but cost tris);
      2. faces with a collinear corner -> explicit beauty triangulation; a remaining T-junction sliver (B on the
         long edge AC) is dropped and B is inserted into the face across AC;
      3. a carried normal more than `max_dev` off its own face normal (a back-facing bevel-corner artefact) is
         replaced by the face normal.
    Returns (micro faces + zero-area tris before, after)."""
    if ob.type != "MESH":
        return 0, 0
    if ob.modifiers:
        bc.apply_modifiers(ob)
    me = ob.data
    before = micro_faces(ob, area) + degenerate_tris(ob, area)
    if not me.polygons or os.environ.get("MAKO_NO_POSTCLEAN") == "1":
        return before, before
    cn = [Vector(me.corner_normals[i].vector) for i in range(len(me.loops))]
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = [bm.loops.layers.float.new(k) for k in ("_cnx", "_cny", "_cnz")]
    i = 0
    for f in bm.faces:
        for lp in f.loops:
            for k in range(3):
                lp[lay[k]] = cn[i][k]
            i += 1
    bmesh.ops.dissolve_degenerate(bm, dist=merge, edges=bm.edges)
    tf = [f for f in bm.faces if len(f.verts) > 3 and _flat_corner(f)]
    if tf:
        bmesh.ops.triangulate(bm, faces=tf, quad_method="BEAUTY", ngon_method="BEAUTY")
    # 2b. big n-gons (a handguard face bridged around its slots) can tessellate into zero-area triangles between
    #    collinear vertices of different outlines: triangulate those faces explicitly and rotate the long edge
    #    of each zero-area triangle into its coplanar neighbour (ABC + ACD -> ABD + BCD, same flat face)
    def tri_area(ls):
        a, b, c = (lp.vert.co for lp in ls)
        return (b - a).cross(c - a).length * 0.5
    ngons = {ls[0].face for ls in bm.calc_loop_triangles() if tri_area(ls) < area and len(ls[0].face.verts) > 3}
    if ngons:
        bmesh.ops.triangulate(bm, faces=list(ngons), quad_method="BEAUTY", ngon_method="BEAUTY")
    for it in range(8):
        bad = [f for f in bm.faces if len(f.verts) == 3 and f.calc_area() < area]
        if not bad:
            break
        touched = set()
        for f in bad:
            if not f.is_valid or f in touched:
                continue
            e = max(f.edges, key=lambda e: e.calc_length())
            if len(e.link_faces) != 2:
                continue
            A, C = e.verts
            B = next(v for v in f.verts if v not in (A, C))
            ac = C.co - A.co
            t = (B.co - A.co).dot(ac) / max(ac.length_squared, 1e-18)
            if not (1e-4 < t < 1 - 1e-4):
                continue
            other = next(g for g in e.link_faces if g is not f)
            touched.add(other)
            bmesh.ops.delete(bm, geom=[f], context="FACES_ONLY")
            _ne, V = bmesh.utils.edge_split(e, A, t)
            bmesh.ops.weld_verts(bm, targetmap={V: B})
        tf = [f for f in bm.faces if f.is_valid and len(f.verts) > 3 and _flat_corner(f)]
        if tf:
            bmesh.ops.triangulate(bm, faces=tf, quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.normal_update()
    for it in range(12):
        rot = []
        for f in bm.faces:
            if len(f.verts) != 3 or f.calc_area() >= area:
                continue
            e = max(f.edges, key=lambda e: e.calc_length())
            if len(e.link_faces) != 2 or e in rot:
                continue
            g = e.link_faces[0] if e.link_faces[1] is f else e.link_faces[1]
            if len(g.verts) == 3 and g.calc_area() >= area and g.normal.length > 0.5:
                rot.append(e)
        if not rot:
            break
        bmesh.ops.rotate_edges(bm, edges=rot, use_ccw=bool(it % 2))
        bm.normal_update()
    bm.normal_update()
    out = []
    for f in bm.faces:
        fn = f.normal
        for lp in f.loops:
            v = Vector((lp[lay[0]], lp[lay[1]], lp[lay[2]]))
            v = v.normalized() if v.length > 1e-9 else fn.copy()
            if fn.length > 0.5 and v.angle(fn, 0.0) > math.radians(max_dev):
                v = fn.copy()
            out.append(v)
    for k in ("_cnx", "_cny", "_cnz"):
        bm.loops.layers.float.remove(bm.loops.layers.float[k])
    bm.to_mesh(me)
    bm.free()
    me.normals_split_custom_set(out)
    me.update()
    return before, micro_faces(ob, area) + degenerate_tris(ob, area)


MICRO_EDGE = float(os.environ.get("MAKO_MICRO_EDGE", "5e-5"))   # 50 um


def prebevel_clean(ob, area=1e-10, flat_deg=179.0):
    """Remove what would become zero-area triangles in the GLB, on the plain boolean result (no custom normals
    yet, so topology edits are safe):
      0. collapse micro edges (< MICRO_EDGE), 1. collapse sub-micron edges,
      2. dissolve valence-2 vertices that sit on a straight line (pure redundancy),
      3. triangulate only the faces that still have a ~180 deg corner, then rotate the long edge of every
         zero-area triangle into its neighbour (B on AC: ABC + ACD -> ABD + BCD)."""
    if ob.type != "MESH" or ob.data.has_custom_normals:
        return 0, 0
    me = ob.data
    # micro edges (boolean slivers; nothing modelled is under 0.4 mm) are what made the global bevel clamp
    # squash whole parts (see local_bevel_offsets): collapse every edge under MICRO_EDGE first
    bm = bmesh.new()
    bm.from_mesh(me)
    if any(e.calc_length() < MICRO_EDGE for e in bm.edges):
        bmesh.ops.dissolve_degenerate(bm, dist=MICRO_EDGE, edges=bm.edges)
        bm.to_mesh(me)
        me.update()
    bm.free()
    before = degenerate_tris(ob, area)
    if before == 0:
        return 0, 0
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.dissolve_degenerate(bm, dist=2e-6, edges=bm.edges)

    def flat(v):
        if len(v.link_edges) != 2 or len(v.link_faces) == 0:
            return False
        a, b = (e.other_vert(v).co - v.co for e in v.link_edges)
        if a.length < 1e-9 or b.length < 1e-9:
            return False
        return a.angle(b) > math.radians(flat_deg)
    fl = [v for v in bm.verts if flat(v)]
    if fl:
        bmesh.ops.dissolve_verts(bm, verts=fl)

    def corner_flat(f):
        for lp in f.loops:
            a = lp.link_loop_prev.vert.co - lp.vert.co
            b = lp.link_loop_next.vert.co - lp.vert.co
            if a.length > 1e-9 and b.length > 1e-9 and a.angle(b) > math.radians(flat_deg):
                return True
        return False
    # only faces with a ~180 deg corner (triangulating every big n-gon here would add bevel geometry for nothing)
    tf = [f for f in bm.faces if len(f.verts) > 3 and corner_flat(f)]
    if tf:
        bmesh.ops.triangulate(bm, faces=tf, quad_method="BEAUTY", ngon_method="BEAUTY")
    for it in range(24):
        bad = [f for f in bm.faces if len(f.verts) == 3 and f.calc_area() < area]
        if not bad:
            break
        edges = []
        for f in bad:
            e = max(f.edges, key=lambda e: e.calc_length())
            if len(e.link_faces) == 2 and e not in edges:
                edges.append(e)
        if not edges:
            break
        bmesh.ops.rotate_edges(bm, edges=edges, use_ccw=bool(it % 2))
    bmesh.ops.dissolve_degenerate(bm, dist=2e-5, edges=bm.edges)
    bm.to_mesh(me)
    bm.free()
    me.update()
    return before, degenerate_tris(ob, area)


# ------------------------------------------------------------------------------------------- materials
def _srgb_to_lin(c):
    import numpy as np
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _lin_to_srgb(c):
    import numpy as np
    c = np.clip(c, 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def bake_tint(src, color, mix, out_png, size=512, stretch=False):
    """Bake color * lerp(1, tex, mix) (all linear) into an sRGB PNG, so a glTF baseColorTexture alone carries the
    full colour (the shared bc.material multiplies in the shader with a Mix node, which the glTF exporter drops).
    stretch=True levels the texture's luminance to its 2..98 % range first, so a low-contrast detail map (the
    stipple) actually shows."""
    import numpy as np
    img = bpy.data.images.load(src, check_existing=False)
    if img.size[0] != size:
        img.scale(size, size)
    px = np.array(img.pixels[:], dtype=np.float32).reshape(size, size, 4)
    lin = _srgb_to_lin(px[..., :3])
    if stretch:
        lum = lin.mean(axis=-1, keepdims=True)
        lo, hi = np.percentile(lum, 2), np.percentile(lum, 98)
        lin = np.clip((lum - lo) / max(hi - lo, 1e-6), 0.0, 1.0).repeat(3, axis=-1)
    out = np.empty_like(px)
    out[..., :3] = _lin_to_srgb(np.asarray(color[:3], dtype=np.float32) * ((1.0 - mix) + mix * lin))
    out[..., 3] = 1.0
    bpy.data.images.remove(img)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    name = os.path.splitext(os.path.basename(out_png))[0]
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    im = bpy.data.images.new(name, size, size, alpha=False)
    im.pixels = out.ravel()
    im.filepath_raw = out_png
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    return out_png


def gl_material(name, color, rough=0.5, metal=0.0, tex=None, tex_mix=0.35, bake_dir=None, emission=None,
                emission_strength=0.0, stretch=False):
    """glTF-safe material: either a flat Principled colour, or a baked tinted texture wired straight into Base
    Color (exports as baseColorTexture with factor 1, so the engine sees exactly what Blender renders).
    Texture repeats come from the UVs (see uv_density), not from a Mapping node."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        if n.type not in ("BSDF_PRINCIPLED", "OUTPUT_MATERIAL"):
            nt.nodes.remove(n)
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (*color[:3], 1.0)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if emission is not None:
        p.inputs["Emission Color"].default_value = (*emission[:3], 1.0)
        p.inputs["Emission Strength"].default_value = emission_strength
    if tex and os.path.exists(tex):
        png = bake_tint(tex, color, tex_mix, os.path.join(bake_dir, f"{name}.png"), stretch=stretch)
        img = bpy.data.images.load(png, check_existing=True)
        img.colorspace_settings.name = "sRGB"
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = img
        ti.location = (-400, 200)
        nt.links.new(ti.outputs["Color"], p.inputs["Base Color"])
    mat.use_backface_culling = True
    mat.diffuse_color = (*color[:3], 1.0)
    return mat


def tidy_materials(ob, fallback=None):
    """Drop empty (None) and unused material slots; faces on an empty slot go to `fallback` (default slot 0).
    Returns the number of faces that were on an empty slot."""
    me = ob.data
    mats = list(me.materials)
    if not mats:
        return 0
    idx = [p.material_index for p in me.polygons]
    fb = mats.index(fallback) if fallback in mats else next((i for i, m in enumerate(mats) if m), 0)
    bad = 0
    for i, k in enumerate(idx):
        if k >= len(mats) or mats[k] is None:
            idx[i] = fb
            bad += 1
    used = sorted(set(idx))
    remap = {old: new for new, old in enumerate(used)}
    keep = [mats[k] for k in used]
    me.materials.clear()
    for m in keep:
        me.materials.append(m)
    for p, k in zip(me.polygons, idx):
        p.material_index = remap[k]
    return bad


def uv_density(ob, reps_by_mat, default=0.0):
    """Rescale an object's (smart-projected, 0-1 packed) UVs so every textured material gets a constant world
    density: reps_by_mat[material_name] texture repeats per metre."""
    me = ob.data
    if not me.uv_layers or not me.polygons:
        return
    uv = me.uv_layers.active.data
    a3 = sum(p.area for p in me.polygons)
    auv = 0.0
    for p in me.polygons:
        pts = [uv[li].uv for li in p.loop_indices]
        s = 0.0
        for i in range(len(pts)):
            s += pts[i].x * pts[(i + 1) % len(pts)].y - pts[(i + 1) % len(pts)].x * pts[i].y
        auv += abs(s) / 2
    if auv <= 1e-12:
        return
    k = math.sqrt(a3 / auv)  # metres per UV unit
    for p in me.polygons:
        mname = me.materials[p.material_index].name if me.materials else ""
        reps = reps_by_mat.get(mname, default)
        if reps <= 0:
            continue
        for li in p.loop_indices:
            uv[li].uv = uv[li].uv * (k * reps)


def edge_angle_deg(e):
    if len(e.link_faces) != 2:
        return 0.0
    return math.degrees(e.link_faces[0].normal.angle(e.link_faces[1].normal))


# ------------------------------------------------------------------------------------------- rails
# dovetail base (0.015 wide at the mounting face, flaring to 0.021), flat 0.021 top; edges get a small bevel
RAIL_PROFILE = [(-0.0075, 0.0), (0.0075, 0.0), (0.0105, 0.003), (0.0105, 0.0095), (-0.0105, 0.0095),
                (-0.0105, 0.003)]
RAIL_H = 0.0095
RAIL_SLOT_PITCH = 0.010
RAIL_SLOT_W = 0.0052
RAIL_SLOT_DEPTH = 0.003


def rail(name, y0, y1, mat=None, col=None, bevel=0.0006):
    """Stylised Picatinny rail pointing +Z, base at z = 0, centred on x = 0, from y0 to y1.
    Width 0.021, height 0.0095, cross slots every 0.010 (0.0052 wide, 0.003 deep).
    Returns (object, list_of_slot_centres)."""
    L = y1 - y0
    ob = prism(name, RAIL_PROFILE, "Y", y0, y1, col, mat)
    n = int((L - 0.006) / RAIL_SLOT_PITCH) + 1
    mid = (y0 + y1) / 2
    centres = [mid + (i - (n - 1) / 2) * RAIL_SLOT_PITCH for i in range(n)]
    cutters = []
    for i, c in enumerate(centres):
        cutters.append(box(f"_rc{i}", -0.02, 0.02, c - RAIL_SLOT_W / 2, c + RAIL_SLOT_W / 2,
                           RAIL_H - RAIL_SLOT_DEPTH, 0.03))
    boolean(ob, cutters, transfer=False)
    clean(ob)
    finish(ob, bevel=bevel, segs=1, angle=40)
    return ob, centres


def place_rail(ob, base_point, direction):
    """Move a +Z rail (base at z=0) so its base sits at base_point and its top points along direction
    ('+Z', '-Z', '+X', '-X'). Mesh data is transformed (object stays at the origin)."""
    if direction == "-Z":
        rotate(ob, "Y", 180)
    elif direction == "+X":
        rotate(ob, "Y", 90)
    elif direction == "-X":
        rotate(ob, "Y", -90)
    move(ob, base_point)
    return ob


# ------------------------------------------------------------------------------------------- misc
def parent(child, par):
    # matrix_world is stale right after setting .location on a new object: refresh it first, otherwise the
    # child snaps to the parent's origin (this is what put every socket at (0,0,0) in the first exports)
    bpy.context.view_layer.update()
    mw = child.matrix_world.copy()
    child.parent = par
    child.matrix_parent_inverse = par.matrix_world.inverted()
    child.matrix_world = mw
    return child


def empty(name, loc, col=None, size=0.02, kind="PLAIN_AXES"):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = kind
    e.empty_display_size = size
    e.location = loc
    (col or bpy.context.scene.collection).objects.link(e)
    return e


def tri_count(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    total = 0
    for o in objs:
        if o.type != "MESH":
            continue
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        total += sum(len(p.vertices) - 2 for p in me.polygons)
        ev.to_mesh_clear()
    return total
