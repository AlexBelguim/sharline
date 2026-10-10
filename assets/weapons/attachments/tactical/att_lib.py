"""Helpers for the ATT tactical / underbarrel / shield attachment set (headless Blender 5.2).

Lives in the asset folder on purpose (tools/*.py are shared and must not be edited).
Import after blender_common:
    sys.path.insert(0, str(PROJECT / "tools")); sys.path.insert(0, HERE); import att_lib as L

Mirroring: set L.MIRROR = True before building a part and every primitive is mirrored across X the moment it is
created (winding reversed so normals stay outward). Booleans, bevels and hardened normals are then computed
natively on the mirrored geometry, so a `_L` side part is an exact, clean mirror of its `_R` twin.
"""
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = str(Path(__file__).resolve().parent)
PROJECT = Path(HERE).parents[3]
sys.path.insert(0, str(PROJECT / "tools"))
import blender_common as bc  # noqa: E402

TEX = str(PROJECT / "art" / "textures")
TEXOUT = os.path.join(HERE, "textures")
MIRROR = False
S_X = Matrix.Scale(-1, 4, (1, 0, 0))

# ------------------------------------------------------------------------------------------ rail standard
RAIL_W = 0.021        # rail top width
RAIL_H = 0.0095       # rail height above its base
RAIL_PITCH = 0.010    # cross slot pitch


def rail_profile():
    """Stylised Picatinny section as the real gun exports build it (Mako: measured on mako_default.glb), (u, v):
    u across the rail, v = 0 on the rail TOP surface, negative into the rail, base at v = -0.0095. The top face is
    the full 0.021 width with only a 0.6 mm corner chamfer (the Warden's rails have square top corners)."""
    return [(-0.0069, -0.0095), (0.0069, -0.0095), (0.0105, -0.0059), (0.0105, -0.0006), (0.0099, 0.0),
            (-0.0099, 0.0), (-0.0105, -0.0006), (-0.0105, -0.0059)]


def clamp_profile(W=0.0155, H=0.008, D=0.0083, cl=0.0003):
    """Clamp section that hugs the rail with `cl` clearance. v = 0 is the contact with the rail top surface
    (the part's origin), +v away from the rail. Jaws reach down to v = -D and hook under the dovetail.
    Round 2 (Warden review): the channel has SQUARE corners at the contact face. The old 1.5 mm channel chamfer
    assumed a chamfered rail top, but the real rails are the full 0.021 wide at the top face (Mako 0.6 mm corner
    chamfer, Warden square corners), so their top corners sat 0.42 / 0.85 mm inside every clamp."""
    return [(-W, H), (-W, -D + 0.001), (-W + 0.001, -D), (-0.0090, -D), (-0.0105 - cl, -0.0065),
            (-0.0105 - cl, 0.0), (0.0105 + cl, 0.0),
            (0.0105 + cl, -0.0065), (0.0090, -D), (W - 0.001, -D), (W, -D + 0.001), (W, H)]


def mount_map(mount):
    """(u, v, t) in rail space -> part space. t runs along the rail (Y).
    top:    rail below the part (part +Z)            under: rail above the part (part hangs -Z)
    side_R: rail outer face looks -X (shooter's right), part sticks out toward -X."""
    if mount == "top":
        return lambda u, v, t: Vector((u, t, v))
    if mount == "under":
        return lambda u, v, t: Vector((u, t, -v))
    if mount == "side_R":
        return lambda u, v, t: Vector((-v, t, u))
    raise ValueError(mount)


# ------------------------------------------------------------------------------------------ mesh building
def mx(p):
    """Mirror a point (R-space -> current build space)."""
    p = Vector(p)
    return Vector((-p.x, p.y, p.z)) if MIRROR else p


def new_obj(name, bm, col=None, mat=None):
    if MIRROR:
        for v in bm.verts:
            v.co.x = -v.co.x
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    if mat is not None:
        me.materials.append(mat)
    return ob


def prism_f(name, pts, f, t0, t1, col=None, mat=None):
    """Extrude a closed 2D polygon pts=[(a, b)] between t0 and t1 using mapping f(a, b, t) -> Vector."""
    bm = bmesh.new()
    v0 = [bm.verts.new(f(a, b, t0)) for a, b in pts]
    v1 = [bm.verts.new(f(a, b, t1)) for a, b in pts]
    n = len(pts)
    bm.faces.new(v0)
    bm.faces.new(v1[::-1])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, col, mat)


AXMAP = {
    "Y": lambda a, b, t: Vector((a, t, b)),   # pts (x, z), extrude along Y
    "X": lambda a, b, t: Vector((t, a, b)),   # pts (y, z), extrude along X
    "Z": lambda a, b, t: Vector((a, b, t)),   # pts (x, y), extrude along Z
}


def prism(name, pts, axis, t0, t1, col=None, mat=None):
    return prism_f(name, pts, AXMAP[axis], t0, t1, col, mat)


def loft(name, loops, col=None, mat=None, cap=True):
    """Skin a list of 3D point loops (same vertex count, each planar) into a closed solid."""
    bm = bmesh.new()
    rings = [[bm.verts.new(Vector(p)) for p in loop] for loop in loops]
    n = len(loops[0])
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((r0[i], r0[j], r1[j], r1[i]))
    if cap:
        bm.faces.new(rings[0])
        bm.faces.new(rings[-1][::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, col, mat)


def crect(hw, hh, c, cx=0.0, cy=0.0):
    """Chamfered rectangle (octagon) points, counter-clockwise, starting bottom edge."""
    return [(cx - hw + c, cy - hh), (cx + hw - c, cy - hh), (cx + hw, cy - hh + c), (cx + hw, cy + hh - c),
            (cx + hw - c, cy + hh), (cx - hw + c, cy + hh), (cx - hw, cy + hh - c), (cx - hw, cy - hh + c)]


def octagon(r, cx=0.0, cy=0.0):
    c = r - r * math.tan(math.radians(22.5))
    return crect(r, r, c, cx, cy)


def ngon(r, n, cx=0.0, cy=0.0, phase=0.0):
    return [(cx + r * math.cos(phase + 2 * math.pi * i / n), cy + r * math.sin(phase + 2 * math.pi * i / n))
            for i in range(n)]


def chamfer_poly(pts, c):
    """Cut every corner of a polygon by distance c (a float, or a list with one value per corner, 0 = keep)."""
    n = len(pts)
    cs = c if isinstance(c, (list, tuple)) else [c] * n
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        ci = cs[i]
        if ci <= 0:
            out.append(tuple(p1))
            continue
        a, b = p0 - p1, p2 - p1
        ca = min(ci, a.length * 0.45)
        cb = min(ci, b.length * 0.45)
        out.append(tuple(p1 + a.normalized() * ca))
        out.append(tuple(p1 + b.normalized() * cb))
    return out


def offset_poly(poly, d):
    """Offset a polygon (any winding) inward by d (negative d grows it). Mitred corners."""
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
        if abs(den) < 1e-12:
            out.append(q)
            continue
        a = ((q[0] - p[0]) * s2[1] - (q[1] - p[1]) * s2[0]) / den
        out.append((p[0] + a * r[0], p[1] + a * r[1]))
    return out


def notch_edge(p0, p1, ts, depth, half=0.0035, side=1.0):
    """Inner points of a straight edge p0->p1 with trapezoid notches (grip grooves) cut into it. ts = centre
    positions (0..1 along the edge), depth = notch depth, side = +1/-1 picks which side of the edge the notch
    goes into (+1 = to the right of the direction p0->p1). p0 and p1 themselves are not included."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    u = d / d.length
    nrm = Vector((u.y, -u.x)) * side
    out = []
    for t in ts:
        c = p0 + d * t
        out += [c - u * (half + 0.0015), c - u * half + nrm * depth, c + u * half + nrm * depth,
                c + u * (half + 0.0015)]
    return [tuple(p) for p in out]


def lathe_y(name, prof, steps=24, center=(0.0, 0.0), col=None, mat=None, phase=None):
    """Revolve [(r, y)] around an axis parallel to Y through (x, z) = center. Profile should start/end at r=0
    for a closed solid, or repeat its first point at the end for a closed tube."""
    bm = bmesh.new()
    cx, cz = center
    if phase is None:
        phase = math.pi / steps
    rings = []
    for i in range(steps):
        a = phase + 2 * math.pi * i / steps
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((cx + r * ca, y, cz + r * sa)) for (r, y) in prof])
    for i in range(steps):
        r0, r1 = rings[i], rings[(i + 1) % steps]
        for j in range(len(prof) - 1):
            try:
                bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, col, mat)


def cyl(name, r, p0, p1, verts=16, col=None, mat=None, r2=None, phase=None):
    """Cylinder (or frustum) between two points."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r if r2 is None else r2,
                          depth=d.length)
    if phase is None:
        phase = math.pi / verts
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(phase, 3, "Z"))
    q = d.normalized().to_track_quat("Z", "Y")
    bmesh.ops.transform(bm, verts=bm.verts, matrix=Matrix.Translation((p0 + p1) / 2) @ q.to_matrix().to_4x4())
    return new_obj(name, bm, col, mat)


def boxp(name, mn, mx_, col=None, mat=None):
    """Axis-aligned box from min/max corners."""
    mn, mx_ = Vector(mn), Vector(mx_)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=mx_ - mn, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(mn + mx_) / 2, verts=bm.verts)
    return new_obj(name, bm, col, mat)


def xform(ob, M):
    """Bake a matrix (given in R space) into the mesh data. Mirror-aware."""
    if MIRROR:
        M = S_X @ M @ S_X
    ob.data.transform(M)
    if M.determinant() < 0:
        ob.data.flip_normals()
    ob.data.update()
    return ob


def rot(axis, deg, pivot=(0, 0, 0)):
    p = Vector(pivot)
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-p)


def set_origin(ob, p):
    """Move the object origin to p (R-space point) without moving the geometry."""
    p = mx(p)
    ob.data.transform(Matrix.Translation(-p))
    ob.location = p
    return ob


# ------------------------------------------------------------------------------------------ modifiers
def cut(ob, cutters, op="DIFFERENCE"):
    """EXACT boolean with one or several cutters (joined first). Cutters are deleted."""
    cutters = [c for c in (cutters if isinstance(cutters, (list, tuple)) else [cutters]) if c]
    if not cutters:
        return ob
    multi = len(cutters) > 1
    c = join_raw(cutters, "_cutter") if multi else cutters[0]
    m = ob.modifiers.new("Bool", "BOOLEAN")
    m.object = c
    m.operation = op
    m.solver = "EXACT"
    try:
        m.use_hole_tolerant = True
        m.use_self = multi
    except Exception:
        pass
    bc.apply_modifiers(ob, only=[m.name])
    bpy.data.objects.remove(c, do_unlink=True)
    clean_slots(ob)
    return ob


def union(ob, others):
    return cut(ob, others, op="UNION")


def cut_crisp(ob, cutters):
    """Cut thin details (panel lines, seams) AFTER the bevel. Blender's bevel clamp is global, so a narrow groove cut
    before the bevel shrinks every bevel on the object, and a groove that ends close to an edge collapses the bevel
    into self-overlapping n-gons (fold-over triangles). Cutting afterwards keeps the full bevel and a crisp groove.
    The original corner normals (hardened by the bevel) are restored; corners the cut creates are flat-shaded."""
    rec = _record_normals(ob.data)
    cut(ob, cutters)
    _restore_normals(ob.data, rec)
    return ob


def _record_normals(me):
    """{rounded vertex co: [(polygon normal, corner normal)]} of the current mesh."""
    rec = {}
    cn = me.corner_normals
    for p in me.polygons:
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            rec.setdefault((round(co.x, 6), round(co.y, 6), round(co.z, 6)), []).append(
                (p.normal.copy(), Vector(cn[li].vector)))
    return rec


def _restore_normals(me, rec):
    """Re-apply recorded corner normals after a topology change: each corner takes the recorded normal of the same
    vertex whose polygon normal matches best (falls back to its own polygon normal)."""
    out = [None] * len(me.loops)
    for p in me.polygons:
        p.use_smooth = True
        pn = p.normal.copy()
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            cands = rec.get((round(co.x, 6), round(co.y, 6), round(co.z, 6)), ())
            best, bd = None, 0.98
            for fn, n in cands:
                d = fn.dot(pn)
                if d > bd:
                    best, bd = n, d
            out[li] = tuple(best if best is not None else pn)
    me.normals_split_custom_set(out)
    me.update()


def tri_clean(ob):
    """Explicit BEAUTY triangulation of quads + n-gons (what the exporters will write), then removal of zero-area
    triangles: the long edge of a collinear sliver is rotated into its neighbour (two proper triangles), zero-length
    edges are collapsed. Hardened corner normals are recorded first and restored afterwards."""
    if ob.type != "MESH" or not ob.data.polygons:
        return ob
    me = ob.data
    rec = _record_normals(me)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
    bmesh.ops.dissolve_degenerate(bm, dist=1e-7, edges=bm.edges[:])
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3], quad_method="BEAUTY",
                          ngon_method="BEAUTY")
    for _ in range(6):
        bad = [f for f in bm.faces if f.calc_area() < 1e-10 and len(f.verts) == 3]
        if not bad:
            break
        for f in bad:
            if not f.is_valid:
                continue
            e = max(f.edges, key=lambda ed: ed.calc_length())
            if len(e.link_faces) == 2:
                bmesh.ops.rotate_edges(bm, edges=[e], use_ccw=False)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3], quad_method="BEAUTY",
                              ngon_method="BEAUTY")
    bm.to_mesh(me)
    bm.free()
    _restore_normals(me, rec)
    return ob


def clean_slots(ob):
    """Drop empty (None) material slots that booleans add, remapping faces onto the first real slot."""
    me = ob.data
    mats = list(me.materials)
    if all(m is not None for m in mats):
        return ob
    keep = [i for i, m in enumerate(mats) if m is not None]
    remap = {old: new for new, old in enumerate(keep)}
    idx = [remap.get(p.material_index, 0) for p in me.polygons]
    me.materials.clear()
    for i in keep:
        me.materials.append(mats[i])
    for p, i in zip(me.polygons, idx):
        p.material_index = i
    return ob


def join_raw(objs, name):
    """Join meshes (modifiers applied). First object survives."""
    objs = [o for o in objs if o is not None]
    for o in objs:
        if o.modifiers:
            bc.apply_modifiers(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    out = bpy.context.view_layer.objects.active
    out.name = name
    out.data.name = name
    return out


def smooth(ob, angle=30):
    for p in ob.data.polygons:
        p.use_smooth = True
    try:
        ob.data.set_sharp_from_angle(angle=math.radians(angle))
    except Exception:
        pass
    return ob


def mark_convex(ob, angle=30):
    """Bevel weight 1 on convex edges sharper than `angle` (concave edges stay crisp and add no geometry, so
    e.g. a clamp channel never grows fillets into the rail it hugs)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    lay = bm.edges.layers.float.get("bevel_weight_edge") or bm.edges.layers.float.new("bevel_weight_edge")
    lim = math.radians(angle)
    for e in bm.edges:
        w = 0.0
        if len(e.link_faces) == 2:
            try:
                a = e.calc_face_angle_signed()
            except ValueError:
                a = 0.0
            w = 1.0 if a > lim else 0.0
        e[lay] = w
    bm.to_mesh(ob.data)
    bm.free()


def finish(ob, width, segs=1, angle=30, smooth_angle=30, harden=True, profile=0.5, convex_only=False):
    """Bevel (angle-limited, clamped, sharp miters) + hardened normals, applied."""
    smooth(ob, smooth_angle)
    if width > 0:
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width = width
        m.segments = segs
        if convex_only:
            mark_convex(ob, angle)
            m.limit_method = "WEIGHT"
            try:
                m.edge_weight = "bevel_weight_edge"
            except Exception:
                pass
        else:
            m.limit_method = "ANGLE"
            m.angle_limit = math.radians(angle)
        m.profile = profile
        m.use_clamp_overlap = True
        m.harden_normals = harden
        m.miter_outer = "MITER_SHARP"
        bc.apply_modifiers(ob)
        # drop zero-area slivers the clamped bevel can leave behind (custom normals are kept per loop)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
        bm.to_mesh(ob.data)
        bm.free()
    if not ob.data.has_custom_normals:
        smooth(ob, smooth_angle)
    return ob


def merge(objs, name, parent=None, col=None):
    """Join finished pieces (materials preserved) into one object named `name`."""
    ob = join_raw(objs, name)
    if col is not None:
        bc.link(ob, col)
    if parent is not None:
        ob.parent = parent
    return ob


def set_mat_by(ob, mat_index, pred):
    """Assign material index to polygons where pred(centre, normal) is True. Centre/normal are given in R space
    (mirror-aware) so predicates written for the right-hand part also work on its mirror."""
    for p in ob.data.polygons:
        c, n = p.center.copy(), p.normal.copy()
        if MIRROR:
            c.x, n.x = -c.x, -n.x
        if pred(c, n):
            p.material_index = mat_index


def add_mat(ob, mat):
    ob.data.materials.append(mat)
    return len(ob.data.materials) - 1


def socket(name, loc, parent, col, size=0.012):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "PLAIN_AXES"
    e.empty_display_size = size
    col.objects.link(e)
    e.parent = parent
    e.location = mx(loc)
    return e


def tris(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    t = sum(len(p.vertices) - 2 for p in me.polygons)
    ev.to_mesh_clear()
    return t


def hierarchy(root):
    out = [root]
    for c in root.children:
        out += hierarchy(c)
    return out


def check_mesh(ob, limit=0.6):
    """Sanity report on the triangles the exporters will write (loop triangles):
    non_manifold edges, max |coordinate| (exploded vertices), faces without material, degenerate polygons,
    zero_area_tris (< 1e-4 mm2), flipped_tris (winding disagrees with the averaged corner normals by > 120 deg: a
    fold-over that renders black in Cycles and z-fights double-sided), ngon_folds (a triangle wound against its own
    polygon = self-overlapping n-gon). Any non-zero value except non_manifold fails the build (see `failed`)."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    mxc = max((max(abs(c) for c in v.co) for v in me.vertices), default=0.0)
    nomat = sum(1 for p in me.polygons if p.material_index >= len(me.materials) or
                me.materials[p.material_index] is None)
    degen = sum(1 for p in me.polygons if p.area < 1e-10)
    me.calc_loop_triangles()
    cn = [Vector(c.vector) for c in me.corner_normals]
    zero = flipped = folds = 0
    for t in me.loop_triangles:
        if t.area < 1e-10:
            zero += 1
            continue
        avg = Vector((0, 0, 0))
        for li in t.loops:
            avg += cn[li]
        if avg.length > 1e-9 and math.degrees(avg.angle(t.normal)) > 120:
            flipped += 1
        if t.normal.dot(me.polygons[t.polygon_index].normal) < 0:
            folds += 1
    r = {"non_manifold": nm, "max_coord": round(mxc, 4), "no_mat": nomat, "degenerate": degen,
         "zero_area_tris": zero, "flipped_tris": flipped, "ngon_folds": folds, "exploded": mxc > limit}
    r["failed"] = bool(r["exploded"] or nomat or degen or zero or flipped or folds)
    return r


# ------------------------------------------------------------------------------------------ gun sockets
def glb_socket_nodes(path, prefix):
    """World positions (Blender axes) of the `<prefix>_SOCKET_*` nodes inside a .glb, read straight from its glTF
    JSON (what the engine uses). Returns {slot: (x, y, z)} or {} if the file is missing/unreadable."""
    import json
    import struct
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        clen, ctype = struct.unpack_from("<II", data, 12)
        js = json.loads(data[20:20 + clen].decode("utf-8"))
    except Exception as e:  # missing, or being rewritten by another session
        print("glb socket read failed:", path, e)
        return {}
    nodes = js.get("nodes", [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i

    def local(n):
        if "matrix" in n:
            m = n["matrix"]
            return Matrix([[m[0], m[4], m[8], m[12]], [m[1], m[5], m[9], m[13]], [m[2], m[6], m[10], m[14]],
                           [m[3], m[7], m[11], m[15]]])
        t = n.get("translation", [0, 0, 0])
        q = n.get("rotation", [0, 0, 0, 1])
        s = n.get("scale", [1, 1, 1])
        from mathutils import Quaternion
        return (Matrix.Translation(t) @ Quaternion((q[3], q[0], q[1], q[2])).to_matrix().to_4x4() @
                Matrix.Diagonal((s[0], s[1], s[2], 1.0)))

    def world(i):
        m = local(nodes[i])
        while i in parent:
            i = parent[i]
            m = local(nodes[i]) @ m
        return m

    out = {}
    tag = prefix + "_SOCKET_"
    for i, n in enumerate(nodes):
        nm = n.get("name", "")
        if nm.startswith(tag):
            g = world(i).translation          # glTF Y-up -> Blender Z-up: (x, y, z)_b = (x, -z, y)_g
            out[nm[len(tag):]] = (round(g.x, 5), round(-g.z, 5), round(g.y, 5))
    return out


def gun_sockets(glb_path, json_path, prefix, fallback):
    """Socket positions for test fits: the gun .glb's socket nodes first (engine truth), then sockets.json, then the
    fallback. Returns (sockets, source, mismatch) where mismatch lists slots whose json and glb disagree > 0.5 mm."""
    import json
    js = {}
    try:
        with open(json_path) as fh:
            d = json.load(fh)
        js = {k.replace(prefix + "_SOCKET_", ""): tuple(v["location"]) for k, v in d.items()}
    except Exception as e:
        print("socket json unavailable:", json_path, e)
    gl = glb_socket_nodes(glb_path, prefix)
    mismatch = {k: {"glb": gl[k], "json": js[k]} for k in gl if k in js and
                max(abs(a - b) for a, b in zip(gl[k], js[k])) > 0.0005}
    if gl:
        socks = dict(fallback)
        socks.update(js)
        socks.update(gl)
        return socks, "glb:" + os.path.basename(glb_path), mismatch
    if js:
        socks = dict(fallback)
        socks.update(js)
        return socks, "json:" + os.path.basename(json_path), mismatch
    return dict(fallback), "fallback", mismatch


# ------------------------------------------------------------------------------------------ materials
def detail_texture(src_name, mix, size=512):
    """glTF-safe detail texture: glTF can only do base = factor x texture, so the subtle multiply is baked into
    a grey image: linear t = 1 - mix * (1 - src / src_p99.5). The palette colour stays the material factor."""
    import numpy as np
    os.makedirs(TEXOUT, exist_ok=True)
    nm = f"att_{src_name}_{int(round(mix * 100)):02d}"
    path = os.path.join(TEXOUT, nm + ".png")
    src = bpy.data.images.load(os.path.join(TEX, src_name + ".png"), check_existing=False)
    src.scale(size, size)
    px = np.array(src.pixels[:], dtype=np.float32).reshape(size, size, 4)[..., :3]
    bpy.data.images.remove(src)
    lin = np.where(px <= 0.04045, px / 12.92, ((px + 0.055) / 1.055) ** 2.4).mean(axis=2)
    n = np.clip(lin / np.percentile(lin, 99.5), 0.0, 1.0)
    t = 1.0 - mix * (1.0 - n)
    s = np.where(t <= 0.0031308, t * 12.92, 1.055 * np.power(t, 1 / 2.4) - 0.055)
    img = bpy.data.images.new("_" + nm, size, size, alpha=False)
    rgba = np.ones((size, size, 4), np.float32)
    rgba[..., :3] = s[..., None]
    img.pixels = rgba.ravel()
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    out = bpy.data.images.load(path, check_existing=True)
    out.name = nm
    return out


def gl_material(name, color, rough=0.55, metal=0.0, tex=None, mix=0.0, tile_m=0.3, emission=None,
                emission_strength=0.0, alpha=1.0, coat=0.0, cull=True):
    """Principled material that exports cleanly to glTF: baseColorFactor = palette colour; optional
    baseColorTexture = baked detail texture joined by Mix MULTIPLY at factor 1 (exported as factor x texture).
    Texture tiling (tile_m = metres per repeat) is baked into the UVs (world_box_uv), so no texture transform."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    col4 = (*color[:3], 1.0)
    p.inputs["Base Color"].default_value = col4
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if coat:
        p.inputs["Coat Weight"].default_value = coat
    if emission is not None:
        p.inputs["Emission Color"].default_value = (*emission[:3], 1.0)
        p.inputs["Emission Strength"].default_value = emission_strength or 3.0
    if alpha < 1.0:
        p.inputs["Alpha"].default_value = alpha
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:
            pass
    if tex:
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = detail_texture(tex, mix)
        m = nt.nodes.new("ShaderNodeMix")
        m.data_type = "RGBA"
        m.blend_type = "MULTIPLY"
        m.inputs[0].default_value = 1.0
        m.inputs[6].default_value = col4
        nt.links.new(ti.outputs["Color"], m.inputs[7])
        nt.links.new(m.outputs[2], p.inputs["Base Color"])
    mat.use_backface_culling = cull
    mat.diffuse_color = (*color[:3], alpha)
    mat["tile_m"] = tile_m
    return mat


def world_box_uv(ob):
    """Box-projected UVs at a constant world texel density per material (1 UV unit = material tile_m metres)."""
    me = ob.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    for p in me.polygons:
        m = me.materials[p.material_index] if me.materials else None
        k = 1.0 / float(m.get("tile_m", 0.3)) if m else 1.0 / 0.3
        n = p.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if ax == 0:
                uv[li].uv = (co.y * k, co.z * k)
            elif ax == 1:
                uv[li].uv = (co.x * k, co.z * k)
            else:
                uv[li].uv = (co.x * k, co.y * k)


# ------------------------------------------------------------------------------------------ export
def export_part(base_path, objs):
    """Export exactly these objects to <base>.glb and <base>.fbx (custom props kept as extras)."""
    os.makedirs(os.path.dirname(base_path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.hide_viewport = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=base_path + ".glb", export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True, export_extras=True)
    bpy.ops.export_scene.fbx(filepath=base_path + ".fbx", use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             use_mesh_modifiers=True, add_leaf_bones=False, path_mode="COPY",
                             embed_textures=True, use_custom_props=True)
    print("exported", base_path)
