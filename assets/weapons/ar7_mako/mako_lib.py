"""Geometry helpers for the AR-7 MAKO build (kept next to build_mako.py; tools/*.py stay untouched).

All coordinates are metres in Blender axes: muzzle -Y, Z up, shooter's RIGHT = -X, LEFT = +X.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, r"F:/git/val etf/tools")
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


def finish(ob, bevel=0.0015, segs=2, angle=30, smooth_angle=30, weight_fn=None, harden=True, profile=0.5,
           uv=True):
    """Hard-surface finish: smooth shading + sharp-by-angle + bevel modifier (hardened normals).
    weight_fn(bm_edge) -> bool marks edges for a weight-limited bevel instead of angle-limited."""
    me = ob.data
    for p in me.polygons:
        p.use_smooth = True
    try:
        me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    except Exception:
        pass
    if bevel > 0:
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = segs
        m.profile = profile
        m.use_clamp_overlap = True
        m.harden_normals = harden
        m.miter_outer = "MITER_ARC" if segs > 1 else "MITER_SHARP"
        if weight_fn is not None:
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.edges.ensure_lookup_table()
            flags = [bool(weight_fn(e)) for e in bm.edges]
            bm.free()
            attr = me.attributes.get("bevel_weight_edge") or me.attributes.new("bevel_weight_edge", "FLOAT",
                                                                                "EDGE")
            for i, f in enumerate(flags):
                attr.data[i].value = 1.0 if f else 0.0
            m.limit_method = "WEIGHT"
            try:
                m.edge_weight = "bevel_weight_edge"
            except Exception:
                pass
        else:
            m.limit_method = "ANGLE"
            m.angle_limit = math.radians(angle)
    if uv and not me.uv_layers:
        bc.smart_uv(ob)
    return ob


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
