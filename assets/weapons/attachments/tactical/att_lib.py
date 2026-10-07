"""Helpers for the ATT tactical / underbarrel / shield attachment set (headless Blender 5.2).

Lives in the asset folder on purpose (tools/*.py are shared and must not be edited).
Import after blender_common:
    sys.path.insert(0, r"F:/git/val etf/tools"); sys.path.insert(0, HERE); import att_lib as L
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

TEX = bc.TEXTURES

# ------------------------------------------------------------------------------------------ rail standard
RAIL_W = 0.021        # rail top width
RAIL_H = 0.0095       # rail height above its base
RAIL_PITCH = 0.010    # cross slot pitch
RAIL_SLOT = 0.005     # cross slot width (Y)
RAIL_SLOT_D = 0.003   # cross slot depth from the top


def rail_profile():
    """Stylised Picatinny section, (u, v): u across the rail, v = 0 on the rail TOP surface, negative into the
    rail, base at v = -0.0095 (same numbers as the Mako brief)."""
    return [(-0.0075, -0.0095), (0.0075, -0.0095), (0.0105, -0.0065), (0.0105, -0.0015), (0.009, 0.0),
            (-0.009, 0.0), (-0.0105, -0.0015), (-0.0105, -0.0065)]


def clamp_profile(W=0.0155, H=0.008, D=0.0083, cl=0.0003):
    """Clamp section that hugs the rail_profile with `cl` clearance. v = 0 is the contact with the rail top
    surface (the part's origin), +v away from the rail. Jaws reach down to v = -D and hook under the dovetail."""
    return [(-W, H), (-W, -D + 0.001), (-W + 0.001, -D), (-0.0090, -D), (-0.0105 - cl, -0.0065),
            (-0.0105 - cl, -0.0015), (-0.009 - cl, 0.0), (0.009 + cl, 0.0), (0.0105 + cl, -0.0015),
            (0.0105 + cl, -0.0065), (0.0090, -D), (W - 0.001, -D), (W, -D + 0.001), (W, H)]


def mount_map(mount):
    """(u, v, t) in rail space -> part space. t runs along the rail (Y).
    top:    rail below the part (part +Z)            under: rail above the part (part hangs -Z)
    side_R: rail outer face looks -X (shooter's right), part sticks out toward -X;  side_L: mirror (+X)."""
    if mount == "top":
        return lambda u, v, t: Vector((u, t, v))
    if mount == "under":
        return lambda u, v, t: Vector((u, t, -v))
    if mount == "side_R":
        return lambda u, v, t: Vector((-v, t, u))
    if mount == "side_L":
        return lambda u, v, t: Vector((v, t, u))
    raise ValueError(mount)


# ------------------------------------------------------------------------------------------ mesh building
def new_obj(name, bm, col=None, mat=None):
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


def ngon(r, n, cx=0.0, cy=0.0, phase=0.0):
    return [(cx + r * math.cos(phase + 2 * math.pi * i / n), cy + r * math.sin(phase + 2 * math.pi * i / n))
            for i in range(n)]


def lathe_y(name, prof, y_sign=-1, steps=24, center=(0.0, 0.0), col=None, mat=None, phase=0.0):
    """Revolve [(r, y)] around an axis parallel to Y through (x, z) = center. Profile should start/end at r=0
    for a closed solid (or form a closed loop for a tube)."""
    bm = bmesh.new()
    cx, cz = center
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


def boxp(name, mn, mx, col=None, mat=None):
    """Axis-aligned box from min/max corners."""
    mn, mx = Vector(mn), Vector(mx)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=mx - mn, verts=bm.verts)
    bmesh.ops.translate(bm, vec=(mn + mx) / 2, verts=bm.verts)
    return new_obj(name, bm, col, mat)


def xform(ob, M):
    """Bake a matrix into the mesh data."""
    ob.data.transform(M)
    if M.determinant() < 0:
        ob.data.flip_normals()
    ob.data.update()
    return ob


def rot(axis, deg, pivot=(0, 0, 0)):
    p = Vector(pivot)
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-p)


# ------------------------------------------------------------------------------------------ modifiers
def cut(ob, cutters, op="DIFFERENCE"):
    """EXACT boolean with one or several cutters (joined first). Cutters are deleted."""
    cutters = [c for c in (cutters if isinstance(cutters, (list, tuple)) else [cutters]) if c]
    if not cutters:
        return ob
    multi = len(cutters) > 1
    if multi:
        c = join_raw(cutters, "_cutter")
    else:
        c = cutters[0]
    m = ob.modifiers.new("Bool", "BOOLEAN")
    m.object = c
    m.operation = op
    m.solver = "EXACT"
    try:
        m.use_hole_tolerant = True
        m.use_self = multi          # joined operands may overlap each other
    except Exception:
        pass
    bc.apply_modifiers(ob, only=[m.name])
    bpy.data.objects.remove(c, do_unlink=True)
    clean_slots(ob)
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


def union(ob, others):
    return cut(ob, others, op="UNION")


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


def bevel(ob, width, segs=2, angle=30, harden=True, limit="ANGLE", profile=0.5, clamp=True):
    for p in ob.data.polygons:
        p.use_smooth = True
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segs
    m.limit_method = limit
    if limit == "ANGLE":
        m.angle_limit = math.radians(angle)
    m.profile = profile
    m.use_clamp_overlap = clamp
    m.harden_normals = harden
    m.miter_outer = "MITER_ARC"
    return m


def smooth(ob, angle=30):
    for p in ob.data.polygons:
        p.use_smooth = True
    try:
        ob.data.set_sharp_from_angle(angle=math.radians(angle))
    except Exception:
        pass
    return ob


def bake(ob, angle=30):
    """Apply all modifiers (keeps custom normals) and set sharp edges by angle."""
    bc.apply_modifiers(ob)
    if not ob.data.has_custom_normals:
        smooth(ob, angle)
    return ob


def finish(ob, width, segs=2, angle=30, smooth_angle=30, harden=True, profile=0.5):
    smooth(ob, smooth_angle)
    bevel(ob, width, segs, angle, harden=harden, profile=profile)
    bake(ob, smooth_angle)
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
    """Assign material index to polygons where pred(polygon) is True."""
    for p in ob.data.polygons:
        if pred(p):
            p.material_index = mat_index


def socket(name, loc, parent, col, size=0.012):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "PLAIN_AXES"
    e.empty_display_size = size
    col.objects.link(e)
    e.parent = parent
    e.location = loc
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


def check_normals(ob):
    """Return (bad corner normals, signed volume) as a sanity check after mirroring."""
    me = ob.data
    bad = 0
    cn = me.corner_normals
    for p in me.polygons:
        for li in p.loop_indices:
            if cn[li].vector.dot(p.normal) < 0.0:
                bad += 1
    bm = bmesh.new()
    bm.from_mesh(me)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return bad, vol


def mirror_hierarchy(root, src_tag, dst_tag, col):
    """Duplicate a part hierarchy mirrored across X (mesh data mirrored, normals flipped back outward,
    locations mirrored, rotations mirrored). Names: src_tag -> dst_tag."""
    import re
    S = Matrix.Scale(-1, 4, (1, 0, 0))
    mapping = {}
    for o in hierarchy(root):
        n = o.copy()
        n.name = re.sub(re.escape(src_tag) + r"(?=_|$)", dst_tag, o.name)
        if o.data is not None:
            n.data = o.data.copy()
            n.data.name = n.name
            n.data.transform(S)
            n.data.flip_normals()
            n.data.update()
        col.objects.link(n)
        mapping[o] = n
    for o, n in mapping.items():
        n.parent = mapping.get(o.parent, o.parent)
        # mirror the local transform: M' = S M S
        n.matrix_basis = S @ o.matrix_basis @ S
        n.matrix_parent_inverse = Matrix.Identity(4)
        for k in list(o.keys()):
            n[k] = o[k]
    return mapping[root]


# ------------------------------------------------------------------------------------------ export
def export_part(base_path, objs):
    """Export exactly these objects to <base>.glb and <base>.fbx (custom props kept as extras)."""
    os.makedirs(os.path.dirname(base_path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    vis = []
    for o in objs:
        if o.hide_get() or o.hide_viewport:
            vis.append(o)
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
