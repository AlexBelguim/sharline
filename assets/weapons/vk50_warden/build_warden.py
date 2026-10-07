"""VK-50 "WARDEN" heavy-calibre bolt-action sniper -- modular build (base + stocks + magazines).

Re-runnable from scratch. Builds everything procedurally, saves warden.blend and exports (glTF extras + FBX user
properties carry the moving-part data):
  warden_base.glb/.fbx                       base gun (WARDEN_Root + meshes + socket empties)
  WARDEN_stock_standard.glb/.fbx             default stock      (origin = stock mount point)
  WARDEN_stock_folding.glb/.fbx              folding stock      (origin = stock mount point)
  WARDEN_mag_5.glb/.fbx, WARDEN_mag_8.glb/.fbx  magazines        (origin = mag socket point)
  warden_default.glb                          base + stock_standard + mag_5 assembled on their sockets
  sockets.json, warden_anim.json              socket positions; moving-part pivots / axes / travels

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P build_warden.py -- [--render none|quick|full|fitcheck] [--samples 48] [--no-export]
  then: python compare.py   (concept comparison, silhouettes, contact sheets; system python + PIL)

Conventions (art/STYLE_GUIDE.md, art/WEAPON_MODULAR_SPEC.md, art/DIRECTION_LOG.md):
  metres, Z up, muzzle -Y, origin = top centre of the pistol grip, bore axis x=0 z=0.075.
  Shooter's RIGHT = -X (bolt handle, ejection port), LEFT = +X.
  No ammo counter, no emissive anywhere on the gun. Scope and bipod are separate attachments (other agents).
"""
import argparse
import json
import math
import os
import sys
import time

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402
import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

OUT = r"F:/git/val etf/assets/weapons/vk50_warden"
REN = os.path.join(OUT, "renders")
P = "WARDEN"
BZ = 0.075            # bore axis height
RAIL_TOP_Z = 0.1375   # top rail top surface
HANDLE_Y = 0.096      # bolt-handle root centre (on the shroud, y 0.085..0.107, behind the receiver rear face 0.080)
BOLT_LIFT_DEG = 60.0  # bolt cycle: lift about the bore axis ...
BOLT_TRAVEL = 0.130   # ... then slide toward the butt (full 12.7 mm case length); the stocks keep this path clear
T0 = time.time()

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--render", default="none", help="none | quick | full | compare | fitcheck")
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--no-export", action="store_true")
ARGS = ap.parse_args(argv)


def log(*a):
    print(f"[warden {time.time() - T0:6.1f}s]", *a, flush=True)


# =============================================================================================== helpers
def _new_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def prism(name, pts, axis, a0, a1, mat=None):
    """Extrude a closed 2D polygon along an axis.
    axis 'X': pts are (y, z); 'Y': pts are (x, z); 'Z': pts are (x, y). The prism spans a0..a1 on that axis."""
    def p3(u, v, a):
        return {"X": (a, u, v), "Y": (u, a, v), "Z": (u, v, a)}[axis]
    bm = bmesh.new()
    vs = [bm.verts.new(p3(u, v, a0)) for (u, v) in pts]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    d = {"X": (a1 - a0, 0, 0), "Y": (0, a1 - a0, 0), "Z": (0, 0, a1 - a0)}[axis]
    bmesh.ops.translate(bm, vec=Vector(d), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _new_obj(name, bm)
    if mat:
        bc.assign(obj, mat)
    return obj


def hull(name, points, mat=None):
    bm = bmesh.new()
    for p in points:
        bm.verts.new(p)
    bmesh.ops.convex_hull(bm, input=bm.verts)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = _new_obj(name, bm)
    if mat:
        bc.assign(obj, mat)
    return obj


def rounded_rect(cu, cv, w, h, r, n=4):
    """Closed polygon (u, v) of a w x h rectangle centred at (cu, cv) with corner radius r."""
    r = min(r, w / 2 * 0.999, h / 2 * 0.999)
    pts = []
    for (ccx, ccy, a0) in [(cu + w / 2 - r, cv + h / 2 - r, 0), (cu - w / 2 + r, cv + h / 2 - r, 90),
                           (cu - w / 2 + r, cv - h / 2 + r, 180), (cu + w / 2 - r, cv - h / 2 + r, 270)]:
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return pts


def stadium(cu, cv, w, h, n=5):
    return rounded_rect(cu, cv, w, h, min(w, h) / 2, n)


def band(pts, w):
    """Polygon outlining a polyline with width w (mitred joins) -- for panel-line groove cutters."""
    def nrm(a, b):
        d = Vector((b[0] - a[0], b[1] - a[1])).normalized()
        return Vector((-d.y, d.x))
    left, right = [], []
    for i, p in enumerate(pts):
        pv = Vector(p)
        if i == 0:
            n = nrm(pts[0], pts[1])
        elif i == len(pts) - 1:
            n = nrm(pts[-2], pts[-1])
        else:
            n1, n2 = nrm(pts[i - 1], p), nrm(p, pts[i + 1])
            n = (n1 + n2).normalized()
            n = n / max(0.3, n.dot(n1))
        left.append(tuple(pv + n * w / 2))
        right.append(tuple(pv - n * w / 2))
    return left + right[::-1]


def bake(obj):
    """Apply the object transform into the mesh (object ends at identity, origin = world 0)."""
    obj.data.transform(obj.matrix_basis)
    obj.matrix_basis = Matrix.Identity(4)
    return obj


def set_origin(obj, point):
    """Move the object origin to world `point` without moving the geometry (object must be un-parented)."""
    point = Vector(point)
    mw = obj.matrix_world.copy()
    local = mw.inverted() @ point
    obj.data.transform(Matrix.Translation(-local))
    obj.matrix_world = mw @ Matrix.Translation(local)
    return obj


def cut(obj, *cutters):
    for c in cutters:
        bc.boolean(obj, c, "DIFFERENCE")
    return obj


def union(obj, *others):
    for c in others:
        bc.boolean(obj, c, "UNION")
    return obj


def intersect(obj, other):
    return bc.boolean(obj, other, "INTERSECT")


def degen(obj, dist=1e-5):
    """Collapse the zero-length edges / zero-area faces EXACT booleans leave behind (before bevelling them)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.dissolve_degenerate(bm, dist=dist, edges=bm.edges[:])
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def wnormals(obj, weight=100):
    """Face-area weighted normals (keep sharp): big planar faces shade perfectly flat, so the long fan triangles a
    boolean leaves between slot corners cannot bend the shading into soft diagonal wedges."""
    m = obj.modifiers.new("WN", "WEIGHTED_NORMAL")
    m.mode = "FACE_AREA"
    m.weight = weight
    m.keep_sharp = True
    m.thresh = 0.01
    bc.apply_modifiers(obj)
    return obj


def flat_big_faces(obj, angle=40, min_area=4e-5, crease=4):
    """Shading clean-up for long boolean-cut panels: every edge sharper than `angle`, AND every edge where a big
    planar face (> min_area m^2) meets anything bent by more than `crease` degrees, is marked sharp; custom normals
    are rebuilt with face-area weighted normals. The big faces then shade dead flat even where a bevel corner is
    twisted (the cause of the soft diagonal wedge the review found between handguard slot columns 3 and 4)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    flags = []
    for e in bm.edges:
        s = True
        if len(e.link_faces) == 2:
            f1, f2 = e.link_faces
            a = f1.normal.angle(f2.normal, 0.0)
            big = f1.calc_area() > min_area or f2.calc_area() > min_area
            s = a > math.radians(angle) or (big and a > math.radians(crease))
        flags.append(s)
    bm.free()
    if me.has_custom_normals:
        me.normals_split_custom_set([(0.0, 0.0, 0.0)] * len(me.loops))
    att = me.attributes.get("sharp_edge") or me.attributes.new("sharp_edge", "BOOLEAN", "EDGE")
    att.data.foreach_set("value", flags)
    return wnormals(obj)


def finish(obj, width, segs=1, angle=30, harden=True):
    """Hard-surface finish: smooth shading + angle-based sharp edges + bevel (harden normals), applied."""
    degen(obj)
    for p in obj.data.polygons:
        p.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(angle))
    if width > 0:
        m = obj.modifiers.new("Bevel", "BEVEL")
        m.width = width
        m.segments = segs
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(angle)
        m.harden_normals = harden
        m.miter_outer = "MITER_ARC"
        m.use_clamp_overlap = True
        bc.apply_modifiers(obj)
        degen(obj)          # clamp-overlap / arc-miter corners can leave zero-area faces (review topology item)
    return obj


def finish_outer(obj, width, segs, inner, angle=30):
    """finish() variant that bevels only the edges a player can see: edges whose midpoint satisfies inner(co) (inside
    a hollow shell, e.g. the slot rims on the handguard's inner wall) keep a plain hard corner. Saves the triangles
    of bevels nobody can see (triangle-budget review item)."""
    degen(obj)
    me = obj.data
    for p in me.polygons:
        p.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(angle))
    bm = bmesh.new()
    bm.from_mesh(me)
    w = []
    for e in bm.edges:
        mid = (e.verts[0].co + e.verts[1].co) / 2
        sharp = len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(angle)
        w.append(1.0 if sharp and not inner(mid) else 0.0)
    bm.free()
    att = me.attributes.get("bevel_weight_edge") or me.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
    att.data.foreach_set("value", w)
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segs
    m.limit_method = "WEIGHT"
    m.harden_normals = True
    m.miter_outer = "MITER_ARC"
    m.use_clamp_overlap = True
    bc.apply_modifiers(obj)
    degen(obj)
    att = obj.data.attributes.get("bevel_weight_edge")
    if att is not None:
        obj.data.attributes.remove(att)
    return obj


def smooth(obj, angle=35):
    for p in obj.data.polygons:
        p.use_smooth = True
    obj.data.set_sharp_from_angle(angle=math.radians(angle))
    return obj


def lathe_y(name, prof_ry, x=0.0, z=BZ, steps=24, mat=None, angle=40):
    """Lathe around an axis parallel to Y through (x, z). prof_ry = [(r, y), ...] (open or closed at r=0)."""
    obj = bc.lathe(name, [(r, -y) for (r, y) in prof_ry], rot=(90, 0, 0), loc=(x, 0, z), steps=steps, mat=mat,
                   smooth=None)
    bake(obj)
    smooth(obj, angle)
    return obj


def lathe_dir(name, prof_rt, center, direction, steps=16, mat=None, angle=40):
    """Lathe around an arbitrary axis through `center` pointing along `direction`; prof = [(r, t), ...]."""
    obj = bc.lathe(name, prof_rt, steps=steps, mat=mat, smooth=None)
    q = Vector(direction).normalized().to_track_quat("Z", "Y")
    obj.matrix_basis = Matrix.Translation(Vector(center)) @ q.to_matrix().to_4x4()
    bake(obj)
    smooth(obj, angle)
    return obj


def box(name, size, loc, mat=None, rot=None):
    o = bc.box(name, size, loc=loc, mat=mat, smooth=None)
    if rot is not None:
        o.rotation_euler = rot
    return bake(o)


def cyl(name, r, depth, loc, axis="Y", verts=16, mat=None, r2=None):
    rot = {"X": (0, 90, 0), "Y": (90, 0, 0), "Z": (0, 0, 0)}[axis]
    o = bc.cylinder(name, r, depth, loc=loc, rot=rot, verts=verts, mat=mat, smooth=None, radius2=r2)
    return bake(o)


def knurl_cyl(name, r, depth, loc, axis="Z", verts=16, dent=0.001, mat=None):
    """Cylinder whose every other rim vertex is pushed in by `dent` (cheap knurl / grip ridges)."""
    o = cyl(name, r, depth, loc, axis, verts, mat)
    c = Vector(loc)
    ax = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[axis]
    rings = {}
    for v in o.data.vertices:
        d = v.co - c
        radial = d - ax * d.dot(ax)
        if radial.length < 1e-6:
            continue
        u = radial.normalized()
        ref = Vector((0, 1, 0)) if axis != "Y" else Vector((1, 0, 0))
        ref = (ref - ax * ref.dot(ax)).normalized()
        ang = math.atan2(ax.cross(ref).dot(u), ref.dot(u)) % (2 * math.pi)
        rings.setdefault(round(d.dot(ax), 5), []).append((ang, v, u))
    for ring in rings.values():
        for i, (_, v, u) in enumerate(sorted(ring, key=lambda t: t[0])):
            if i % 2:
                v.co -= u * dent
    return o


def mat_slots(obj, *mats):
    obj.data.materials.clear()
    for m in mats:
        obj.data.materials.append(m)


def join(objs, name):
    out = bc.join(objs, name)
    return out


def tris(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ============================================================================================== materials
TEXDIR = os.path.join(OUT, "textures")
TILE = {}                         # material name -> metres per texture repeat (see world_uvs)


def detail_texture(src_name, mix, size=512):
    """glTF-safe detail texture: glTF can only do base = factor x texture (no 'mix strength'), so the subtle
    multiply is baked into the image: linear  t = 1 - mix * (1 - src / src_p99.5).  Written to textures/ and
    embedded in every export.  The flat palette colour (the material factor) still carries the look."""
    import numpy as np
    os.makedirs(TEXDIR, exist_ok=True)
    nm = f"warden_{src_name}_{int(round(mix * 100)):02d}"
    path = os.path.join(TEXDIR, nm + ".png")
    src = bpy.data.images.load(os.path.join(bc.TEXTURES, src_name + ".png"), check_existing=False)
    src.scale(size, size)
    px = np.array(src.pixels[:], dtype=np.float32).reshape(size, size, 4)[..., :3]  # sRGB-encoded bytes / 255
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


def wmat(name, color, rough, metal=0.0, tex=None, mix=0.0, tile_m=0.3):
    """Principled material that exports cleanly to glTF: baseColorFactor = palette colour, optional
    baseColorTexture = baked detail texture (Mix MULTIPLY with factor 1.0 is what the glTF exporter maps to
    factor x texture).  Texture tiling (tile_m = metres per texture repeat) is baked into the UVs per face
    (see world_uvs), not a Mapping node, so no KHR_texture_transform is needed.  Closed meshes only, so
    backface culling is on (glTF doubleSided false)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    col4 = (*color, 1.0)
    p.inputs["Base Color"].default_value = col4
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if tex:
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = detail_texture(tex, mix)
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "MULTIPLY"
        mx.inputs[0].default_value = 1.0
        mx.inputs[6].default_value = col4
        nt.links.new(ti.outputs["Color"], mx.inputs[7])
        nt.links.new(mx.outputs[2], p.inputs["Base Color"])
    mat.use_backface_culling = True
    mat.diffuse_color = col4
    TILE[name] = tile_m          # build-time only (kept off the material so it does not leak into glTF extras)
    return mat


def mats():
    if os.path.isdir(TEXDIR):        # derived textures are rebuilt every run (no stale variants left behind)
        for fn in os.listdir(TEXDIR):
            if fn.startswith("warden_") and fn.endswith(".png"):
                os.remove(os.path.join(TEXDIR, fn))
    return dict(
        G=wmat("M_Warden_Graphite", (0.030, 0.033, 0.040), 0.55, 0.15, "worn_paint", 0.35, 0.30),
        GM=wmat("M_Warden_Gunmetal", (0.11, 0.115, 0.12), 0.35, 0.85, "brushed_metal", 0.30, 0.16),
        S=wmat("M_Warden_Sand", (0.36, 0.28, 0.18), 0.70, 0.0, "worn_paint", 0.30, 0.30),
        SS=wmat("M_Warden_SandStipple", (0.36, 0.28, 0.18), 0.78, 0.0, "polymer_stipple", 0.50, 0.07),
        R=wmat("M_Warden_Rubber", (0.035, 0.037, 0.045), 0.90),
        # steel-cased 12.7 mm rounds: a lighter, less metallic steel so they read through the mag window;
        # the bullet (ogive) uses gunmetal
        C=wmat("M_Warden_Cartridge", (0.36, 0.34, 0.30), 0.38, 0.35, "brushed_metal", 0.30, 0.16),
    )


def clean_slots(obj):
    """glTF hygiene: every face gets a real material (faces left on an empty slot by booleans/unions take the
    object's dominant material), unused/empty slots are dropped, mesh data is named like the object."""
    me = obj.data
    old = list(me.materials)
    count = {}
    for p in me.polygons:
        m = old[p.material_index] if p.material_index < len(old) else None
        if m is not None:
            count[m.name] = count.get(m.name, 0) + 1
    if count:
        primary = bpy.data.materials[max(count, key=count.get)]
        order, idx = [], []
        for p in me.polygons:
            m = old[p.material_index] if p.material_index < len(old) else None
            m = m or primary
            if m not in order:
                order.append(m)
            idx.append(order.index(m))
        me.materials.clear()
        for m in order:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", idx)
    me.name = obj.name
    return obj


def seal(obj):
    """Close the rare sliver holes an EXACT boolean + bevel can leave (meshes must be closed, the engine
    backface-culls): merge near-coincident verts of the open edges (< 0.12 mm) and fill any remaining small boundary loops."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    nm = [e for e in bm.edges if not e.is_manifold]
    if nm:
        bmesh.ops.remove_doubles(bm, verts=list({v for e in nm for v in e.verts}), dist=0.00012)
        bnd = [e for e in bm.edges if e.is_boundary]
        if bnd:
            bmesh.ops.holes_fill(bm, edges=bnd, sides=12)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
    bm.free()
    return obj


def world_uvs(obj):
    """One fresh smart-projected UV layer, rescaled to a constant world texel density: 1 UV unit = tile_m metres
    of the face's material (so wear / brushing / stipple have the same scale on every part and every export)."""
    me = obj.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    bc.smart_uv(obj, angle=66, margin=0.01)
    uv = me.uv_layers.active.data
    a3 = auv = 0.0
    for p in me.polygons:
        a3 += p.area
        li = list(p.loop_indices)
        s = 0.0
        for k in range(len(li)):
            u0, u1 = uv[li[k]].uv, uv[li[(k + 1) % len(li)]].uv
            s += u0.x * u1.y - u1.x * u0.y
        auv += abs(s) / 2
    k_m = math.sqrt(a3 / auv) if auv > 1e-12 else 1.0      # metres per UV unit after smart project
    for p in me.polygons:
        m = me.materials[p.material_index] if me.materials else None
        f = k_m / TILE.get(m.name, 0.3) if m else k_m / 0.3
        for li in p.loop_indices:
            uv[li].uv = uv[li].uv * f


# ================================================================================================= rails
RAIL_SEC = [(-0.0075, -0.0012), (0.0075, -0.0012), (0.0075, 0.0030), (0.0105, 0.0060), (0.0105, 0.0095),
            (-0.0105, 0.0095), (-0.0105, 0.0060), (-0.0075, 0.0030)]


def rail(name, length, mat, bevel=0.0):
    """Stylised Picatinny along local Y, centred at y=0, base z=0, top z=0.0095, top width 0.021,
    cross slots 0.0045 long x 0.003 deep every 0.010 m (centred so both ends keep a full tooth)."""
    obj = prism(name, RAIL_SEC, "Y", -length / 2, length / 2, mat)
    n = int((length - 0.008) / 0.010) + 1
    first = -(n - 1) * 0.010 / 2
    cs = [box("_slot", (0.03, 0.0045, 0.006), (0, first + i * 0.010, 0.0095 - 0.003 + 0.003)) for i in range(n)]
    cutter = join(cs, "_slots")
    cut(obj, cutter)
    finish(obj, bevel, 1)
    return obj


def place(obj, rot_y_deg=0.0, loc=(0, 0, 0)):
    obj.matrix_basis = Matrix.Translation(Vector(loc)) @ Matrix.Rotation(math.radians(rot_y_deg), 4, "Y")
    return bake(obj)


# =========================================================================================== BASE GUN
def build_base(M, col):
    G, GM, S, SS = M["G"], M["GM"], M["S"], M["SS"]
    parts = []

    # ------------------------------------------------------------------ receiver (monolithic upper)
    side = prism("WARDEN_Receiver", [(0.080, 0.035), (0.080, 0.112), (0.064, 0.128), (-0.292, 0.128),
                                     (-0.300, 0.120), (-0.300, 0.033), (-0.292, 0.025), (0.072, 0.025)],
                 "X", -0.045, 0.045, G)
    sec = prism("_rsec", [(-0.020, 0.010), (0.020, 0.010), (0.039, 0.029), (0.039, 0.117), (0.016, 0.140),
                          (-0.016, 0.140), (-0.039, 0.117), (-0.039, 0.029)], "Y", -0.32, 0.10)
    rec = intersect(side, sec)
    # bolt raceway (internal, shows through the port and at the rear face)
    cut(rec, cyl("_race", 0.0205, 0.27, (0, -0.050, BZ), "Y", 24))
    # ejection port, shooter's RIGHT (-X)
    cut(rec, prism("_eport", rounded_rect(-0.1075, 0.081, 0.135, 0.040, 0.006), "X", -0.06, -0.010))
    # bolt-handle relief (-X), open to the rear: a shallow stepped seat in front of the handle root. The root itself
    # sits on the bolt shroud BEHIND the receiver rear face (y > 0.080), so the 60-degree lift happens in free air
    # (review fix: the old root block sat in a closed-position notch and swept 16 mm into the receiver).
    cut(rec, prism("_notch", [(0.071, 0.080), (0.090, 0.080), (0.090, 0.108), (0.079, 0.108)], "X", -0.06, -0.027))
    # panel-line grooves, LEFT (+X): stepped line running from the chin up to the rear
    gl = [(-0.305, 0.050), (-0.226, 0.050), (-0.204, 0.068), (0.085, 0.068)]
    cut(rec, prism("_gL", band(gl, 0.0028), "X", 0.0365, 0.05))
    gl2 = [(-0.305, 0.108), (-0.045, 0.108), (-0.029, 0.097), (0.085, 0.097)]
    cut(rec, prism("_gL2", band(gl2, 0.0028), "X", 0.0365, 0.05))
    # RIGHT (-X): line under the ejection port
    gr = [(-0.305, 0.050), (0.006, 0.050), (0.020, 0.042), (0.085, 0.042)]
    cut(rec, prism("_gR", band(gr, 0.0028), "X", -0.05, -0.0365))
    finish(rec, 0.0035, 2)
    parts.append(rec)

    # bolt-release button (LEFT, +X)
    btn = cyl("WARDEN_BoltRelease", 0.0055, 0.006, (0.0395, 0.040, 0.0825), "X", 12, GM)
    finish(btn, 0.0012, 1)
    parts.append(btn)
    # rotary safety lever (LEFT, +X, under the shooter's thumb above the grip); origin at its pivot
    hub = cyl("_sfh", 0.0068, 0.0045, (0.0412, 0.018, 0.041), "X", 14, GM)
    finish(hub, 0.0012, 1)
    pad = prism("_sfp", round_poly(band([(0.018, 0.041), (0.037, 0.0335)], 0.0072), 0.0022, 2), "X", 0.0395,
                0.0428, GM)
    finish(pad, 0.0010, 1)
    saf = join([hub, pad], "WARDEN_Safety")
    set_origin(saf, (0.039, 0.018, 0.041))
    parts.append(saf)

    # ------------------------------------------------------------------ chassis (lower bed + magwell + chin)
    cha = prism("WARDEN_Chassis", [(0.080, 0.025), (-0.300, 0.025), (-0.300, 0.034), (-0.340, 0.034),
                                   (-0.296, -0.040), (-0.290, -0.058), (-0.282, -0.068), (-0.112, -0.068),
                                   (-0.104, -0.060), (-0.104, -0.010), (-0.030, 0.000), (0.040, 0.000),
                                   (0.080, -0.010)], "X", -0.035, 0.035, G)
    # magwell opening + flared entrance
    cut(cha, box("_mw", (0.054, 0.1575, 0.090), (0, -0.19575, -0.041)))
    fl = hull("_mwfl", [(sx * 0.031, y, -0.0705) for sx in (1, -1) for y in (-0.2785, -0.1130)] +
              [(sx * 0.027, y, -0.0625) for sx in (1, -1) for y in (-0.2745, -0.1170)])
    cut(cha, fl)
    # trigger slot
    cut(cha, box("_tslot", (0.011, 0.030, 0.030), (0, -0.057, -0.004)))
    # rear stock-adapter lug: the interface every stock clamps over (sits inside the stocks' hinge block)
    lug = prism("_lug", [(0.076, 0.038), (0.090, 0.038), (0.094, 0.034), (0.094, -0.004), (0.090, -0.008),
                         (0.076, -0.008)], "X", -0.019, 0.019)
    cut(lug, cyl("_lugh", 0.0045, 0.05, (0, 0.086, 0.015), "X", 12))
    union(cha, lug)
    # side lightening pockets on the magwell block
    for sx in (1, -1):
        cut(cha, prism("_pk", [(-0.262, -0.012), (-0.140, -0.012), (-0.140, -0.052), (-0.250, -0.052),
                               (-0.262, -0.040)], "X", sx * 0.033, sx * 0.050))
    finish(cha, 0.003, 2)
    parts.append(cha)

    # ------------------------------------------------------------------ handguard (free-float, slotted shell)
    hsec = [(-0.024, 0.030), (0.024, 0.030), (0.036, 0.042), (0.036, 0.116), (0.024, 0.128), (-0.024, 0.128),
            (-0.036, 0.116), (-0.036, 0.042)]
    hg = prism("WARDEN_Handguard", hsec, "Y", -0.700, -0.300, G)
    # front profile: vertical upper front face, chamfered lower front
    k = (0.692 - 0.656) / (0.068 - 0.030)
    hside = prism("_hside", [(-0.290, 0.010), (-0.290, 0.150), (-0.690, 0.150), (-0.690, 0.068),
                             (-0.690 + k * (0.068 - 0.010), 0.010)], "X", -0.05, 0.05)
    intersect(hg, hside)
    # inner cavity (wall 5 mm), open at the rear where the receiver closes it
    isec = [(-0.021, 0.035), (0.021, 0.035), (0.031, 0.045), (0.031, 0.113), (0.021, 0.123), (-0.021, 0.123),
            (-0.031, 0.113), (-0.031, 0.045)]
    cav = prism("_cav", isec, "Y", -0.681, -0.296)
    cav_side = prism("_cavs", [(-0.280, 0.020), (-0.280, 0.140), (-0.681, 0.140), (-0.681, 0.075),
                               (-0.681 + k * (0.075 - 0.020), 0.020)], "X", -0.05, 0.05)
    intersect(cav, cav_side)
    cut(hg, cav)
    # barrel exit hole in the front cap
    cut(hg, cyl("_bh", 0.0265, 0.05, (0, -0.690, BZ), "Y", 24))
    # side slots: 2 rows x 4, rounded
    for yc in (-0.372, -0.437, -0.502, -0.567):
        cut(hg, prism("_s", stadium(yc, 0.1035, 0.050, 0.0145, 3), "X", -0.06, 0.06))
        cut(hg, prism("_s", stadium(yc, 0.0640, 0.050, 0.0145, 3), "X", -0.06, 0.06))
    # bottom slots
    for yc in (-0.405, -0.480):
        cut(hg, prism("_sb", stadium(0.0, yc, 0.022, 0.055, 3), "Z", 0.020, 0.040))
    # top vent slots either side of the rail
    for yc in (-0.405, -0.470, -0.535):
        for sx in (1, -1):
            cut(hg, prism("_st", stadium(sx * 0.0175, yc, 0.007, 0.040, 2), "Z", 0.118, 0.140))
    # bevel the outer shell only: the rims of the slots on the INNER wall face (x +-0.031, z 0.035 / 0.123) and
    # the cavity corners stay hard (never seen, ~1k triangles saved)
    finish_outer(hg, 0.0025, 1, lambda c: abs(c.x) < 0.0318 and 0.0342 < c.z < 0.1238 and c.y > -0.6818)
    # review fix (soft diagonal wedge between slot columns 3 and 4): big planar faces become their own smooth fans
    flat_big_faces(hg)
    parts.append(hg)

    # handguard clamp screws at the receiver joint (hex heads, both sides)
    for sx in (1, -1):
        for zc in (0.052, 0.104):
            s = cyl("_scr", 0.0042, 0.004, (sx * 0.0365, -0.316, zc), "X", 6, GM)
            finish(s, 0.0008, 1)
            parts.append(s)

    # ------------------------------------------------------------------ rails
    rt = rail("WARDEN_RailTop", 0.752, G)
    place(rt, 0, (0, (0.062 - 0.690) / 2, 0.128))
    parts.append(rt)
    rb = rail("WARDEN_RailBottom", 0.110, G)
    place(rb, 180, (0, -0.595, 0.030))
    parts.append(rb)
    for sx, nm in ((-1, "WARDEN_RailSide_R"), (1, "WARDEN_RailSide_L")):
        rs = rail(nm, 0.060, G)
        place(rs, 90 * sx, (sx * 0.036, -0.645, 0.079))
        parts.append(rs)

    # ------------------------------------------------------------------ barrel (fluted, step-down) + brake
    bar = lathe_y("WARDEN_Barrel", [(0, -0.240), (0.023, -0.240), (0.023, -0.600), (0.021, -0.680),
                                    (0.021, -0.940), (0.016, -0.942), (0.016, -0.965), (0.009, -0.965),
                                    (0.009, -0.955), (0, -0.955)], steps=24, mat=GM)
    for i in range(6):
        a = math.radians(30 + 60 * i)
        c = prism("_fl", stadium(0.0, -0.8125, 0.0078, 0.225, 4), "Z", 0.0, 0.012)  # local: tangential x, y
        # local x -> tangent t, local y -> Y, local z -> radial r (right-handed: t x Y = r);
        # radial direction r=(cos a, sin a) in the XZ plane; cutter spans radius 0.018..0.030
        rmat = Matrix(((math.sin(a), 0, math.cos(a), 0),
                       (0, 1, 0, 0),
                       (-math.cos(a), 0, math.sin(a), 0),
                       (0, 0, 0, 1)))
        c.matrix_basis = Matrix.Translation(Vector((0.018 * math.cos(a), 0, BZ + 0.018 * math.sin(a)))) @ rmat
        cut(bar, c)
    smooth(bar, 40)
    parts.append(bar)

    # muzzle brake: big blocky dual-chamber, see-through ports
    bs = prism("WARDEN_Brake", [(-0.950, BZ - 0.025), (-0.950, BZ + 0.025), (-0.956, BZ + 0.031),
                                (-1.090, BZ + 0.031), (-1.100, BZ + 0.021), (-1.100, BZ - 0.021),
                                (-1.090, BZ - 0.031), (-0.956, BZ - 0.031)], "X", -0.035, 0.035, GM)
    bt = prism("_btop", [(-0.035, -0.950), (0.035, -0.950), (0.035, -1.090), (0.025, -1.100), (-0.025, -1.100),
                         (-0.035, -1.090)], "Z", BZ - 0.05, BZ + 0.05)
    intersect(bs, bt)
    # long-edge chamfers (front section octagon)
    bsec = prism("_bsec", [(-0.029, BZ - 0.031), (0.029, BZ - 0.031), (0.035, BZ - 0.025), (0.035, BZ + 0.025),
                           (0.029, BZ + 0.031), (-0.029, BZ + 0.031), (-0.035, BZ + 0.025), (-0.035, BZ - 0.025)],
                 "Y", -1.11, -0.94)
    intersect(bs, bsec)
    cut(bs, prism("_pA", rounded_rect(-1.0035, BZ, 0.037, 0.044, 0.005, 2), "X", -0.06, 0.06))
    cut(bs, prism("_pB", rounded_rect(-1.0545, BZ, 0.039, 0.044, 0.005, 2), "X", -0.06, 0.06))
    cut(bs, prism("_pC", rounded_rect(-0.9685, BZ, 0.013, 0.026, 0.004, 2), "X", -0.06, 0.06))
    # top compensator vents (into the chambers)
    for yc in (-1.0035, -1.0545):
        for sx in (1, -1):
            cut(bs, prism("_pv", stadium(sx * 0.0125, yc, 0.008, 0.026, 2), "Z", BZ, BZ + 0.05))
    cut(bs, cyl("_bore", 0.0105, 0.2, (0, -1.02, BZ), "Y", 20))
    finish(bs, 0.0022, 1)
    parts.append(bs)
    collar = lathe_y("WARDEN_BrakeCollar", [(0, -0.937), (0.021, -0.937), (0.0245, -0.940), (0.0245, -0.949),
                                            (0.022, -0.952), (0, -0.952)], steps=8, mat=GM, angle=30)
    finish(collar, 0.0008, 1)
    parts.append(collar)

    # ------------------------------------------------------------------ pistol grip (sand) + stipple panels
    gp = [(-0.026, 0.004), (0.030, 0.004), (0.042, -0.018), (0.064, -0.110), (0.062, -0.124), (0.052, -0.132),
          (0.020, -0.132), (0.010, -0.124), (-0.004, -0.072), (-0.010, -0.054), (-0.020, -0.036), (-0.026, -0.012)]
    grip = prism("WARDEN_Grip", gp, "X", -0.018, 0.018, S)
    # gentle palm-swell: narrow the front strap with an intersect section (top view)
    finish(grip, 0.0065, 3)
    parts.append(grip)
    pad_pts = [(0.006, -0.026), (0.030, -0.026), (0.050, -0.104), (0.046, -0.114), (0.024, -0.114),
               (0.014, -0.100), (0.002, -0.056)]
    for sx in (1, -1):
        pad = prism("_gpad", pad_pts, "X", sx * 0.0165, sx * 0.0195, SS)
        finish(pad, 0.0012, 1)
        parts.append(pad)

    # ------------------------------------------------------------------ trigger guard + trigger
    tg = prism("WARDEN_TriggerGuard", [(-0.106, -0.004), (-0.106, -0.062), (-0.094, -0.072), (-0.026, -0.072),
                                       (-0.004, -0.064), (-0.010, -0.030), (-0.014, -0.004)], "X", -0.010, 0.010, G)
    cut(tg, prism("_tgh", [(-0.092, 0.010), (-0.092, -0.056), (-0.086, -0.062), (-0.030, -0.062),
                           (-0.022, -0.054), (-0.024, 0.010)], "X", -0.05, 0.05))
    finish(tg, 0.0025, 2)
    parts.append(tg)

    # mag release paddle (ahead of the trigger guard, under the magwell rear)
    mr = prism("WARDEN_MagRelease", [(-0.116, -0.064), (-0.107, -0.064), (-0.104, -0.084), (-0.112, -0.086)],
               "X", -0.011, 0.011, GM)
    finish(mr, 0.0012, 1)
    parts.append(mr)

    trig = prism("WARDEN_Trigger", [(-0.058, 0.004), (-0.049, 0.004), (-0.051, -0.030), (-0.059, -0.048),
                                    (-0.066, -0.046), (-0.060, -0.028)], "X", -0.004, 0.004, GM)
    finish(trig, 0.0012, 1)

    # ------------------------------------------------------------------ bolt (separate, origin = bolt-axis rear)
    bolt = lathe_y("WARDEN_Bolt", [(0, 0.112), (0.0170, 0.112), (0.0205, 0.1105),
                                   (0.024, 0.1070), (0.024, 0.0855), (0.0225, 0.0820), (0.0185, 0.0820),
                                   (0.0185, -0.171), (0.0160, -0.175), (0, -0.175)], steps=24, mat=GM, angle=35)
    # shroud ring groove + bolt-body flutes visible in the port (facing -X / up)
    for ang in (150, 180, 210):   # angle around the bore in the XZ plane, 180 = straight toward -X
        a = math.radians(ang)
        c = box("_bfl", (0.0042, 0.105, 0.006), (0, 0, 0))
        # rotation about Y by (90 - a) maps local Z onto the radial direction (cos a, 0, sin a)
        c.matrix_basis = (Matrix.Translation(Vector((0.0185 * math.cos(a), -0.105, BZ + 0.0185 * math.sin(a)))) @
                          Matrix.Rotation(math.radians(90) - a, 4, "Y"))
        bake(c)
        cut(bolt, c)
    gpro = [(0.030, 0.094), (0.0225, 0.094), (0.0225, 0.0975), (0.030, 0.0975)]
    cut(bolt, lathe_y("_bg", gpro + [gpro[0]], steps=24))
    smooth(bolt, 35)
    # handle root block on the shroud, behind the receiver rear face (y 0.080): clears the receiver during the lift
    root = box("_broot", (0.030, 0.022, 0.022), (-0.020, HANDLE_Y, 0.0915), GM)
    finish(root, 0.003, 1)
    # oversized handle arm, angled down/out to the shooter's right
    p0, p1 = Vector((-0.030, HANDLE_Y - 0.001, 0.092)), Vector((-0.082, HANDLE_Y + 0.013, 0.048))
    d = p1 - p0
    arm = bc.box("_barm", (0.017, 0.015, d.length + 0.010), loc=(0, 0, 0), smooth=None, mat=GM)
    arm.matrix_basis = Matrix.Translation((p0 + p1) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bake(arm)
    finish(arm, 0.004, 1)
    # big knob, lathed along the arm direction
    dn = d.normalized()
    kc = p1 + dn * 0.016
    R = 0.024
    kprof = [(0, -0.030), (0.0065, -0.030), (0.0065, -0.020)]
    for deg in (-58, -40, -20, 0, 20, 38, 52):
        a = math.radians(deg)
        kprof.append((R * math.cos(a), R * math.sin(a)))
    kprof += [(0.0125, R * math.sin(math.radians(56))), (0.0080, 0.0205), (0, 0.0205)]
    knob = lathe_dir("_bknob", kprof, kc, dn, steps=20, mat=GM, angle=32)
    bolt = join([bolt, root, arm, knob], "WARDEN_Bolt")
    set_origin(bolt, (0, 0.112, BZ))

    # merge small static detail bits into their host objects to keep the hierarchy clean
    screws = [o for o in parts if o.name.startswith("_scr")]
    pads = [o for o in parts if o.name.startswith("_gpad")]
    others = [o for o in parts if not o.name.startswith(("_scr", "_gpad")) and o not in (hg, grip)]
    hg = join([hg] + screws, "WARDEN_Handguard")
    grip = join([grip] + pads, "WARDEN_Grip")
    statics = others + [hg, grip]
    set_origin(trig, (0, -0.054, 0.0))
    return statics, trig, bolt


# ================================================================================================ STOCKS
STOCK_MOUNT = Vector((0, 0.080, BZ))
KNUCKLE_X = 0.0315    # folding-stock hinge axis: folded, the arm's inner face sits at x 0.045 (clear of the +X safety
                      # lever at 0.0435 and the receiver side at 0.039)


def hinge_block(M, name, fold_knuckle=False):
    G, GM = M["G"], M["GM"]
    hb = prism(name, [(0.078, 0.045), (0.110, 0.045), (0.114, 0.041), (0.114, -0.011), (0.110, -0.015),
                      (0.078, -0.015)], "X", -0.026, 0.026, G)
    for sx in (1, -1):
        cut(hb, prism("_hbg", band([(0.074, 0.016), (0.118, 0.016)], 0.0025), "X", sx * 0.0238, sx * 0.03))
    finish(hb, 0.003, 2)
    bits = [hb]
    for sx in (1, -1):
        for (yy, zz) in ((0.087, 0.032), (0.087, 0.000)):
            s = cyl("_hs", 0.0038, 0.004, (sx * 0.0255, yy, zz), "X", 6, GM)
            finish(s, 0.0007, 1)
            bits.append(s)
    if fold_knuckle:
        kn = cyl("_kn", 0.0085, 0.066, (KNUCKLE_X, 0.111, 0.015), "Z", 16, GM)
        finish(kn, 0.0015, 1)
        bits.append(kn)
        for zz in (0.044, -0.014):
            cap = cyl("_kc", 0.0095, 0.004, (KNUCKLE_X, 0.111, zz), "Z", 16, GM)
            finish(cap, 0.001, 1)
            bits.append(cap)
    return bits


BOLT_PATH_Y = 0.112 + BOLT_TRAVEL     # rear face of the open bolt shroud (0.242)
BEAM_Z = 0.045                        # stock top beam: below the shroud bottom (0.051) all along the bolt path
UPRIGHT_Z = 0.112                     # top of the rear upright that carries the riser posts (12 mm visible gap)
RISER_Z0, RISER_Z1 = 0.124, 0.146     # cheek riser underside / top: the lifted handle (max z 0.118 in |x|<0.026) passes under


def build_stock_standard(M, col):
    """Skeleton chassis stock. Review fix: the open bolt (lifted 60 deg, 0.13 m back) sweeps the space above the
    bore line up to y 0.242, so the top beam stays LOW (z 0.045) back to y 0.238 and the comb rises only in the rear
    upright behind the bolt path. The cheek riser is carried on two posts on that upright and overhangs forward,
    high enough that the lifted handle root and arm pass underneath it."""
    G, GM, S, R = M["G"], M["GM"], M["S"], M["R"]
    bits = hinge_block(M, "_hinge")
    st = prism("_frame", [(0.090, BEAM_Z), (0.238, BEAM_Z), (0.252, 0.064), (0.252, 0.104), (0.260, UPRIGHT_Z),
                          (0.284, UPRIGHT_Z), (0.292, 0.104), (0.292, -0.118), (0.282, -0.126), (0.240, -0.126),
                          (0.100, -0.032), (0.090, -0.020)], "X", -0.023, 0.023, S)
    # big triangular window with rounded corners (top beam 0.016 thick, rear post 0.024)
    tri = [(0.142, 0.029), (0.268, 0.029), (0.268, -0.096)]
    chamfered_window(st, round_poly(tri, 0.008, 3), 0.023, 0.0045)
    # lightening pockets on the rear post and the front web (both sides)
    for sx in (1, -1):
        cut(st, prism("_pp", rounded_rect(0.2805, -0.019, 0.010, 0.118, 0.004, 2), "X", sx * 0.0205, sx * 0.04))
        cut(st, prism("_pf", round_poly([(0.120, 0.016), (0.130, 0.016), (0.165, -0.020), (0.150, -0.040),
                                         (0.120, -0.016)], 0.004, 2), "X", sx * 0.0205, sx * 0.04))
    finish(st, 0.005, 2)
    bits.append(st)
    # riser-height knob (+X, on the rear upright) and QD sling cups
    kb = knurl_cyl("_rk", 0.0085, 0.008, (0.027, 0.272, 0.080), "X", 16, 0.0008, GM)
    finish(kb, 0.001, 1)
    bits.append(kb)
    for sx in (1, -1):
        # QD sling cup: lathed ring with a socket recess (same look as the old boolean version, ~half the tris)
        prof = [(0.0, -0.002), (0.0057, -0.002), (0.0065, -0.0012), (0.0065, 0.0012), (0.0057, 0.002),
                (0.0035, 0.002), (0.0035, 0.0), (0.0, 0.0)]
        qd = lathe_dir("_qd", prof, (sx * 0.0235, 0.2805, -0.090), (sx, 0, 0), steps=12, mat=GM, angle=40)
        bits.append(qd)
    # recoil pad
    pad = prism("_pad", [(0.290, 0.104), (0.312, 0.100), (0.320, 0.082), (0.320, -0.110), (0.312, -0.126),
                         (0.290, -0.130)], "X", -0.025, 0.025, R)
    for zc in (-0.080, -0.040, 0.000, 0.040):
        cut(pad, box("_pg", (0.06, 0.006, 0.0035), (0, 0.3205, zc)))
    finish(pad, 0.004, 2)
    bits.append(pad)
    # monopod housing (fixed)
    mh = box("_mh", (0.034, 0.030, 0.024), (0, 0.205, -0.105), G)
    finish(mh, 0.003, 2)
    bits.append(mh)
    stock = join(bits, "WARDEN_StockStandard")
    set_origin(stock, STOCK_MOUNT)

    # cheek riser (child, slides up on its posts) -- origin at the upright top centre between the posts.
    # Posts stand behind the bolt path (y >= 0.256); the pad overhangs forward over the open bolt.
    z0, z1 = RISER_Z0, RISER_Z1
    cr = prism("WARDEN_StockStandard_CheekRiser", [(0.160, z0 + 0.004), (0.166, z1 - 0.009), (0.178, z1),
                                                   (0.280, z1), (0.290, z1 - 0.010), (0.290, z0)],
               "X", -0.020, 0.020, S)
    finish(cr, 0.005, 3)
    posts = []
    for yp in (0.263, 0.281):
        p = cyl("_post", 0.005, z0 + 0.004 - 0.100, (0, yp, (0.100 + z0 + 0.004) / 2), "Z", 12, GM)
        finish(p, 0.0008, 1)
        posts.append(p)
    cr = join([cr] + posts, "WARDEN_StockStandard_CheekRiser")
    set_origin(cr, (0, 0.272, UPRIGHT_Z))
    cr["slide_axis"] = "Z"
    cr["travel_min_m"] = 0.0
    cr["travel_max_m"] = 0.030

    # monopod (child, extends along -Z) -- origin at the housing bottom
    col_ = cyl("_mcol", 0.0095, 0.070, (0, 0.205, -0.150), "Z", 14, GM)
    smooth(col_, 40)
    knurl = knurl_cyl("_mknurl", 0.0135, 0.014, (0, 0.205, -0.140), "Z", 16, 0.0012, GM)
    finish(knurl, 0.0012, 1)
    spike = cyl("_mspike", 0.0105, 0.020, (0, 0.205, -0.189), "Z", 14, GM, r2=0.0012)
    spike.data.transform(Matrix.Translation(Vector((0, 0.205, -0.189))) @ Matrix.Rotation(math.pi, 4, "X") @
                         Matrix.Translation(-Vector((0, 0.205, -0.189))))
    smooth(spike, 40)
    mono = join([col_, knurl, spike], "WARDEN_StockStandard_Monopod")
    set_origin(mono, (0, 0.205, -0.117))
    mono["slide_axis"] = "Z"
    mono["travel_min_m"] = -0.045
    mono["travel_max_m"] = 0.0

    for o in (stock, cr, mono):
        bc.link(o, col)
    bc.parent_keep(cr, stock)
    bc.parent_keep(mono, stock)
    stock["part"] = "stock_standard"
    stock["socket"] = "WARDEN_SOCKET_Stock"
    return stock


def round_poly(pts, r, n=4):
    """Round the corners of a convex/concave polygon by radius r (fillet arcs inside each corner)."""
    out = []
    N = len(pts)
    for i in range(N):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % N])
        a, b = (p0 - p1).normalized(), (p2 - p1).normalized()
        ang = math.acos(max(-1.0, min(1.0, a.dot(b))))
        t = r / math.tan(ang / 2)
        t = min(t, (p0 - p1).length * 0.45, (p2 - p1).length * 0.45)
        rr = t * math.tan(ang / 2)
        s, e = p1 + a * t, p1 + b * t
        bis = (a + b).normalized()
        c = p1 + bis * (rr / math.sin(ang / 2))
        a0 = math.atan2(s.y - c.y, s.x - c.x)
        a1 = math.atan2(e.y - c.y, e.x - c.x)
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in range(n + 1):
            aa = a0 + da * k / n
            out.append((c.x + rr * math.cos(aa), c.y + rr * math.sin(aa)))
    return out


def offset_poly(pts, d):
    """Offset a convex polygon outward by d (vertex-normal offset with miter compensation)."""
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    out = []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        e1, e2 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n1, n2 = Vector((e1.y, -e1.x)), Vector((e2.y, -e2.x))
        if n1.dot(p1 - Vector((cx, cy))) < 0:
            n1, n2 = -n1, -n2
        nb = (n1 + n2).normalized()
        out.append(tuple(p1 + nb * d / max(0.3, nb.dot(n1))))
    return out


def chamfered_window(obj, poly, half_w, depth):
    """Cut a through-window (side profile polygon, axis X) and a 45-degree chamfer `depth` deep on both faces."""
    cut(obj, prism("_win", poly, "X", -0.06, 0.06))
    # the 45-degree hull reaches only 1 mm past the outer face, so it cannot graze the face beside the window
    # (review fix: depth + 0.004 left a hairline crease and a sliver along the stock top beam)
    big = offset_poly(poly, depth + 0.001)
    for sx in (1, -1):
        pts = ([(sx * (half_w - depth), y, z) for (y, z) in poly] +
               [(sx * (half_w + 0.001), y, z) for (y, z) in big])
        cut(obj, hull("_wch", pts))
    return obj


def build_stock_folding(M, col):
    G, GM, S, R = M["G"], M["GM"], M["S"], M["R"]
    fixed = join(hinge_block(M, "_hingeF", fold_knuckle=True), "WARDEN_StockFolding")
    set_origin(fixed, STOCK_MOUNT)
    # folding arm: lighter Z-frame skeleton (w 0.036), no riser, no monopod. Same review fix as stock_standard:
    # the top beam stays at z 0.044 under the bolt path and rises only behind the open shroud (y > 0.242).
    outer = [(0.116, 0.044), (0.240, 0.044), (0.256, 0.068), (0.264, 0.076), (0.288, 0.076), (0.288, -0.104),
             (0.278, -0.114), (0.246, -0.114), (0.128, -0.026), (0.116, -0.016)]
    fr = prism("_ffr", outer, "X", -0.018, 0.018, S)
    winA = round_poly([(0.134, 0.030), (0.216, 0.030), (0.134, -0.011)], 0.006)
    winB = round_poly([(0.272, 0.030), (0.272, -0.094), (0.164, -0.028)], 0.006)
    chamfered_window(fr, winA, 0.018, 0.0035)
    chamfered_window(fr, winB, 0.018, 0.0035)
    finish(fr, 0.0045, 2)
    pad = prism("_fpad", [(0.286, 0.084), (0.304, 0.080), (0.310, 0.066), (0.310, -0.104), (0.302, -0.118),
                          (0.286, -0.120)], "X", -0.022, 0.022, R)
    for zc in (-0.070, -0.030, 0.010, 0.050):
        cut(pad, box("_pg", (0.06, 0.006, 0.0035), (0, 0.3105, zc)))
    finish(pad, 0.004, 2)
    # hinge leaf (graphite) joining the arm to the knuckle on the LEFT (+X)
    leaf = prism("_leaf", [(0.104, 0.040), (0.132, 0.040), (0.132, -0.012), (0.104, -0.012)], "X", 0.016,
                 KNUCKLE_X + 0.0045, G)
    finish(leaf, 0.002, 2)
    core = prism("_fcore", [(0.1155, 0.044), (0.132, 0.044), (0.132, -0.016), (0.1155, -0.016)], "X", -0.017,
                 0.017, G)
    finish(core, 0.002, 2)
    arm = join([fr, pad, leaf, core], "WARDEN_StockFolding_Arm")
    set_origin(arm, (KNUCKLE_X, 0.111, 0.015))
    arm["fold_axis"] = "Z"
    arm["fold_angle_deg"] = -180.0
    arm["note"] = "rotate about local Z by fold_angle_deg: stock swings out to +X and lies along the LEFT side"
    for o in (fixed, arm):
        bc.link(o, col)
    bc.parent_keep(arm, fixed)
    fixed["part"] = "stock_folding"
    fixed["socket"] = "WARDEN_SOCKET_Stock"
    return fixed


# ============================================================================================= MAGAZINES
MAG_MOUNT = Vector((0, -0.270, 0.0))


ROUND_TOP_Z = -0.0075     # axis of the top cartridge: it stands ~3 mm proud of the feed lips
ROUND_PITCH = 0.021       # single-stack column pitch (case diameter)
ROUND_TIP_Y = -0.2655     # bullet tip (gun coords); rim at -0.1275
FEED_LIP_GAP = 0.016      # lip-to-lip gap at the top face (narrower than the 0.021 case: the lips hold it)


def cartridge(name, tip_y, z, steps, M, simple=False):
    """12.7 mm-class cartridge lying along Y, bullet tip toward -Y at tip_y, axis at height z (gun coords).
    Two materials: gunmetal bullet, light steel case (reads clearly at the feed lips and in the window).
    simple=True: reduced profile for the rounds that are only ever seen through the window slot."""
    prof = [(0, 0.0), (0.0022, 0.003), (0.0046, 0.012), (0.0062, 0.026), (0.0066, 0.039), (0.0076, 0.039),
            (0.0078, 0.056), (0.0099, 0.066), (0.0105, 0.128), (0.0090, 0.130), (0.0090, 0.1335),
            (0.0104, 0.1345), (0.0104, 0.138), (0, 0.138)]
    if simple:
        prof = [(0, 0.0), (0.0040, 0.009), (0.0062, 0.026), (0.0066, 0.039), (0.0077, 0.040), (0.0099, 0.066),
                (0.0105, 0.128), (0.0090, 0.131), (0.0104, 0.134), (0.0104, 0.138), (0, 0.138)]
    o = lathe_y(name, [(r, tip_y + s) for (r, s) in prof], x=0.0, z=z, steps=steps, mat=M["C"], angle=40)
    o.data.materials.append(M["GM"])
    for p in o.data.polygons:
        if p.center.y - tip_y < 0.0385:      # bullet ogive ahead of the case mouth
            p.material_index = 1
    return o


def build_mag(M, col, cap, body_bottom):
    """mag_5 (cap 5, body bottom -0.150) or mag_8 (cap 8, body bottom -0.200). Single-stack 12.7 mm column
    seen through a vertical window slot on each side; the top round sits in real feed lips (45-degree lip
    undercut, FEED_LIP_GAP at the top face) and stands proud of them so it reads when the mag is out. The upper
    0.072 m (inside the magwell) is 0.052 wide; below the well the body steps out to 0.056."""
    G, GM, S = M["G"], M["GM"], M["S"]
    zb = body_bottom
    fr = 0.006 * (abs(zb) / 0.150)          # front face rakes forward toward the bottom
    body = prism("_mbody", [(-0.270, 0.000), (-0.120, 0.000), (-0.118, zb), (-0.270 - fr, zb)], "X", -0.035,
                 0.035, G)
    # section: 6 mm 45-degree chamfer on the top outer edges so the feed lips read as a narrower ridge
    msec = prism("_msec", [(-0.020, 0.010), (0.020, 0.010), (0.020, 0.0), (0.026, -0.006), (0.026, -0.0725),
                           (0.028, -0.0745), (0.028, zb - 0.01), (-0.028, zb - 0.01), (-0.028, -0.0745),
                           (-0.026, -0.0725), (-0.026, -0.006), (-0.020, 0.0)], "Y", -0.30, -0.10)
    intersect(body, msec)
    y0, y1 = -0.2665, -0.1255               # cartridge column length (+1 mm at the tip, +2 mm at the rim)
    # internal channel for the cartridge column (narrow so the rounds sit right behind the window)
    ch_top, ch_bot = -0.0045, zb + 0.008
    cut(body, box("_mch", (0.025, y1 - y0, ch_top - ch_bot), (0, (y0 + y1) / 2, (ch_top + ch_bot) / 2)))
    # feed lips: opening FEED_LIP_GAP wide at the top face, undercut at 45 degrees down to the channel width
    g = FEED_LIP_GAP / 2
    lips = prism("_mfl", [(-g, 0.012), (g, 0.012), (g, 0.0), (0.0125, -0.0045), (0.0125, -0.008),
                          (-0.0125, -0.008), (-0.0125, -0.0045), (-g, 0.0)], "Y", y0, y1)
    cut(body, lips)
    # window slots both sides (physical mag-check window)
    wz0, wz1 = -0.018, zb + 0.020
    cut(body, prism("_mw", stadium(-0.181, (wz0 + wz1) / 2, 0.023, wz0 - wz1, 4), "X", -0.04, 0.04))
    # rear catch notch
    cut(body, box("_mcn", (0.020, 0.008, 0.010), (0, -0.120, -0.030)))
    finish(body, 0.0022, 1)
    # raised ribs flanking the window on the lower (wider) section
    ribs = []
    for sx in (1, -1):
        for yc in (-0.232, -0.132):
            h = abs(zb) - 0.084
            rb = box("_mrib", (0.006, 0.010, h), (sx * 0.0285, yc, -0.080 - h / 2), G)
            finish(rb, 0.0018, 1)
            ribs.append(rb)
    base = box("_mbase", (0.060, 0.172, 0.018), (0, -0.197 - fr / 2, zb - 0.009), S)
    cut(base, prism("_mbg", band([(-0.30, zb - 0.009), (-0.09, zb - 0.009)], 0.003), "X", 0.028, 0.04))
    cut(base, prism("_mbg2", band([(-0.30, zb - 0.009), (-0.09, zb - 0.009)], 0.003), "X", -0.04, -0.028))
    finish(base, 0.004, 2)
    mag = join([body] + ribs + [base], f"WARDEN_Mag{cap}")
    set_origin(mag, MAG_MOUNT)
    bc.link(mag, col)
    mag["part"] = f"mag_{cap}"
    mag["capacity"] = cap
    mag["socket"] = "WARDEN_SOCKET_Mag"
    # follower: separate child (review fix) so the engine can push it up under the lowest remaining round.
    # Full mag: its top touches the bottom round. n rounds left: raise it min((cap - n) * travel_per_round_m,
    # travel_max_m) along local +Z; empty: travel_max_m puts it right under the feed lips.
    follower_z = ROUND_TOP_Z - ROUND_PITCH * (cap - 1) - 0.0105 - 0.006
    fol = box(f"WARDEN_Mag{cap}_Follower", (0.0245, 0.136, 0.012), (0, -0.197, follower_z), G)
    cut(fol, prism("_mfr", [(-0.2655, follower_z + 0.006), (-0.2475, follower_z + 0.006),
                            (-0.2655, follower_z - 0.001)], "X", -0.02, 0.02))      # nose ramp
    finish(fol, 0.0015, 1)
    set_origin(fol, (0, -0.197, follower_z))
    fol["slide_axis"] = "Z"
    fol["travel_per_round_m"] = ROUND_PITCH
    fol["travel_max_m"] = round(ROUND_PITCH * (cap - 1) + 0.010, 4)
    bc.link(fol, col)
    bc.parent_keep(fol, mag)
    rounds = []
    for i in range(cap):
        nm = f"WARDEN_Mag{cap}_Round" if i == 0 else f"WARDEN_Mag{cap}_Round_{i + 1:02d}"
        zc = ROUND_TOP_Z - ROUND_PITCH * i
        # the top round reads at the feed lips (16 sides); the rest are only seen through the window (8 sides,
        # simplified profile) -- review fix for the triangle budget
        r = cartridge(nm, ROUND_TIP_Y, zc, 16 if i == 0 else 8, M, simple=i > 0)
        set_origin(r, (0, ROUND_TIP_Y + 0.069, zc))
        r["round_index"] = i + 1
        bc.link(r, col)
        bc.parent_keep(r, mag)
        rounds.append(r)
    return mag


# ================================================================================================ SOCKETS
SOCKETS = {
    "Optic": (0, -0.080, RAIL_TOP_Z),
    "Stock": (0, 0.080, BZ),
    "Mag": (0, -0.270, 0.0),
    "Under": (0, -0.600, 0.0205),
    "Side_R": (-0.0455, -0.645, 0.079),   # shooter's RIGHT = -X (modular spec handedness)
    "Side_L": (0.0455, -0.645, 0.079),
    "Muzzle": (0, -1.100, BZ),
    "LeftHand": (0, -0.380, 0.030),
}


def build_all():
    bc.reset_scene()
    M = mats()
    c_base = bc.collection("WARDEN_Base")
    c_ss = bc.collection("WARDEN_Stock_Standard")
    c_sf = bc.collection("WARDEN_Stock_Folding")
    c_m5 = bc.collection("WARDEN_Mag_5")
    c_m8 = bc.collection("WARDEN_Mag_8")

    root = bpy.data.objects.new("WARDEN_Root", None)
    root.empty_display_type = "ARROWS"
    root.empty_display_size = 0.05
    c_base.objects.link(root)
    root["weapon"] = "VK-50 WARDEN"
    root["default_stock"] = "stock_standard"
    root["default_mag"] = "mag_5"
    root["default_optic"] = "optic_sniper"
    root["default_under"] = "bipod"

    log("building base")
    statics, trig, bolt = build_base(M, c_base)
    for o in statics + [trig, bolt]:
        bc.link(o, c_base)
        bc.parent_keep(o, root)
    trig["pivot_axis"] = "X"
    trig["pull_deg"] = 12.0
    trig["note"] = "pull = rotate +12 deg about local +X (blade tip moves rearward); same axis in glTF"
    # bolt cycle (verified sign): lift = +60 deg about local +Y in Blender (handle swings up from the -X side),
    # then slide 0.13 m toward the butt (+Y). In glTF/Bevy axes (Y-up, Blender +Y -> glTF -Z) that is
    # -60 deg about local +Z, then translate -Z 0.13.
    bolt["lift_axis"] = "+Y (Blender) / -Z (glTF)"
    bolt["lift_deg"] = BOLT_LIFT_DEG
    bolt["travel_axis"] = "+Y (Blender) / -Z (glTF)"
    bolt["travel_m"] = BOLT_TRAVEL
    bolt["note"] = ("cycle: rotate lift_deg about the bore axis (Blender +Y = glTF -Z; positive = handle swings up from "
                    "the -X side), then translate travel_m toward the butt; close in reverse. Clear of every stock.")
    saf = next(o for o in statics if o.name == "WARDEN_Safety")
    saf["pivot_axis"] = "X"
    saf["fire_deg"] = -45.0
    saf["note"] = "SAFE = as modelled (lever points rearward); FIRE = rotate fire_deg about local +X (tip swings down)"
    sockets = {}
    for nm, loc in SOCKETS.items():
        e = bpy.data.objects.new(f"WARDEN_SOCKET_{nm}", None)
        e.empty_display_type = "PLAIN_AXES"
        e.empty_display_size = 0.02
        e.location = loc
        c_base.objects.link(e)
        e.parent = root
        sockets[nm] = e

    log("building stocks")
    ss = build_stock_standard(M, c_ss)
    sf = build_stock_folding(M, c_sf)
    log("building mags")
    m5 = build_mag(M, c_m5, 5, -0.150)
    m8 = build_mag(M, c_m8, 8, -0.200)

    for o in list(bpy.data.objects):
        if o.type == "MESH" and not o.name.startswith("_"):
            seal(o)
            clean_slots(o)
            world_uvs(o)
    return dict(root=root, statics=statics, trig=trig, bolt=bolt, sockets=sockets, ss=ss, sf=sf, m5=m5, m8=m8,
                cols=dict(base=c_base, ss=c_ss, sf=c_sf, m5=c_m5, m8=c_m8))


def tree(o):
    out = [o]
    for c in o.children:
        out += tree(c)
    return out


def base_objs(B):
    return list(B["cols"]["base"].objects)


def tri_count(objs):
    return sum(tris(o) for o in objs if o.type == "MESH")


# ================================================================================================= EXPORT
def export_files(path_noext, objs, glb=True, fbx=True):
    """Like bc.export_all (same axes / settings) but WITH custom properties: glTF node `extras` and FBX user
    properties carry the engine-facing animation data (lift_deg, travel_m, pull_deg, round_index, ...).
    Review fix: bc.export_all does not set export_extras / use_custom_props (tools/ is read-only)."""
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if glb:
        bpy.ops.export_scene.gltf(filepath=path_noext + ".glb", export_format="GLB", use_selection=True,
                                  export_apply=True, export_yup=True, export_extras=True)
    if fbx:
        bpy.ops.export_scene.fbx(filepath=path_noext + ".fbx", use_selection=True, apply_unit_scale=True,
                                 apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                                 use_mesh_modifiers=True, add_leaf_bones=False, path_mode="COPY",
                                 embed_textures=True, use_custom_props=True)
    log("exported", os.path.basename(path_noext))


def export_part(root_obj, path_noext):
    """Export a part whose root object's origin is its mount point: temporarily put it at world origin."""
    mw = root_obj.matrix_world.copy()
    root_obj.matrix_world = Matrix.Identity(4)
    bpy.context.view_layer.update()
    export_files(path_noext, tree(root_obj))
    root_obj.matrix_world = mw
    bpy.context.view_layer.update()


PART_FILES = {"ss": "WARDEN_stock_standard", "sf": "WARDEN_stock_folding", "m5": "WARDEN_mag_5",
              "m8": "WARDEN_mag_8"}     # <prefix>_<part> (WEAPON_MODULAR_SPEC "Exports"), like MAKO_stock_standard


def anim_sidecar(B):
    """warden_anim.json: every engine-facing moving-part number in one place, in Blender AND glTF/Bevy axes
    (glTF = Blender (x, z, -y)). The same values ride along as glTF extras / FBX user properties."""
    bolt, trig = B["bolt"], B["trig"]
    ss = B["ss"]
    riser = next(o for o in ss.children if o.name.endswith("CheekRiser"))
    mono = next(o for o in ss.children if o.name.endswith("Monopod"))
    arm = B["sf"].children[0]

    def gl(v):
        return [round(v[0], 5), round(v[2], 5), round(-v[1], 5)]

    def origin(o):
        return {"blender": [round(c, 5) for c in o.matrix_world.translation], "gltf": gl(o.matrix_world.translation)}

    mags = {}
    for key in ("m5", "m8"):
        m = B[key]
        fol = next(o for o in m.children if o.name.endswith("Follower"))
        mags[m.name] = {
            "capacity": m["capacity"],
            "rounds": sorted([o.name for o in m.children if "_Round" in o.name]),
            "round_index_rule": "round_index 1 = top round at the feed lips; hide the highest indices first",
            "follower": fol.name, "follower_axis": {"blender": "+Z", "gltf": "+Y"},
            "follower_travel_per_round_m": fol["travel_per_round_m"], "follower_travel_max_m": fol["travel_max_m"],
            "follower_rule": "offset = min((capacity - rounds_left) * travel_per_round_m, travel_max_m)",
        }
    data = {
        "_about": "VK-50 WARDEN moving parts. Origins are pivots; rotations are about the object's local axis.",
        "axes": "Blender Z-up, muzzle -Y.  glTF/Bevy Y-up, muzzle +Z: (x, y, z)_blender -> (x, z, -y)_gltf",
        "WARDEN_Bolt": {"origin": origin(bolt), "lift_deg": bolt["lift_deg"],
                        "lift_axis": {"blender": "+Y", "gltf": "-Z"}, "travel_m": bolt["travel_m"],
                        "travel_dir": {"blender": "+Y", "gltf": "-Z"},
                        "sequence": "open: lift, then slide back; close: slide forward, then lower"},
        "WARDEN_Trigger": {"origin": origin(trig), "pull_deg": trig["pull_deg"],
                           "axis": {"blender": "+X", "gltf": "+X"}},
        "WARDEN_Safety": {"fire_deg": -45.0, "axis": {"blender": "+X", "gltf": "+X"}},
        riser.name: {"slide": {"blender": "+Z", "gltf": "+Y"}, "travel_min_m": riser["travel_min_m"],
                     "travel_max_m": riser["travel_max_m"]},
        mono.name: {"slide": {"blender": "+Z", "gltf": "+Y"}, "travel_min_m": mono["travel_min_m"],
                    "travel_max_m": mono["travel_max_m"]},
        arm.name: {"origin_rel_stock_mount": {"blender": [round(c, 5) for c in (arm.matrix_world.translation -
                                                                               B["sf"].matrix_world.translation)]},
                   "fold_angle_deg": arm["fold_angle_deg"], "axis": {"blender": "+Z", "gltf": "+Y"},
                   "note": arm["note"]},
        "magazines": mags,
    }
    with open(os.path.join(OUT, "warden_anim.json"), "w") as f:
        json.dump(data, f, indent=2)


def attach(part, socket):
    part.parent = socket
    part.matrix_parent_inverse = Matrix.Identity(4)
    part.matrix_basis = Matrix.Identity(4)


def detach(part):
    mw = part.matrix_world.copy()
    part.parent = None
    part.matrix_world = mw


def do_exports(B):
    s = B["sockets"]
    # parts sit on their sockets in the .blend (variants hidden)
    for p, sk in ((B["ss"], "Stock"), (B["sf"], "Stock"), (B["m5"], "Mag"), (B["m8"], "Mag")):
        p.matrix_world = Matrix.Translation(Vector(SOCKETS[sk]))
    bpy.context.view_layer.update()
    # old lower-case part files (pre-review names) are removed so no stale duplicates ship
    # (Windows is case-insensitive: delete only when the on-disk name really is the old lower-case one, otherwise
    # the exporter would keep writing into the old-cased file name)
    on_disk = set(os.listdir(OUT))
    for nm in ("stock_standard", "stock_folding", "mag_5", "mag_8"):
        for ext in (".glb", ".fbx"):
            if f"warden_{nm}{ext}" in on_disk:
                os.remove(os.path.join(OUT, f"warden_{nm}{ext}"))
    export_files(os.path.join(OUT, "warden_base"), base_objs(B))
    for key, fn in PART_FILES.items():
        export_part(B[key], os.path.join(OUT, fn))
    # assembled default: parts parented to their sockets
    attach(B["ss"], s["Stock"])
    attach(B["m5"], s["Mag"])
    bpy.context.view_layer.update()
    objs = base_objs(B) + tree(B["ss"]) + tree(B["m5"])
    export_files(os.path.join(OUT, "warden_default"), objs, fbx=False)
    anim_sidecar(B)
    # keep the default assembled in the .blend; variants placed on the sockets but hidden
    for p in (B["sf"], B["m8"]):
        for o in tree(p):
            o.hide_render = False
    data = {f"WARDEN_SOCKET_{k}": {"location": [round(v, 5) for v in loc], "rotation_deg": [0, 0, 0]}
            for k, loc in SOCKETS.items()}
    with open(os.path.join(OUT, "sockets.json"), "w") as f:
        json.dump(data, f, indent=2)
    vl = bpy.context.view_layer.layer_collection
    for cname in ("WARDEN_Stock_Folding", "WARDEN_Mag_8"):
        vl.children[cname].exclude = True
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0      # no warden.blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "warden.blend"), compress=True)
    vl.children["WARDEN_Stock_Folding"].exclude = False
    vl.children["WARDEN_Mag_8"].exclude = False
    log("saved blend + exports")


def report(B):
    base = [o for o in base_objs(B) if o.type == "MESH"]
    ss, sf, m5, m8 = (tree(B[k]) for k in ("ss", "sf", "m5", "m8"))
    rows = {
        "base": tri_count(base), "stock_standard": tri_count(ss), "stock_folding": tri_count(sf),
        "mag_5": tri_count(m5), "mag_8": tri_count(m8),
    }
    rows["default (base+stock_standard+mag_5)"] = rows["base"] + rows["stock_standard"] + rows["mag_5"]
    for o in sorted(base + ss + m5, key=lambda o: -tris(o) if o.type == "MESH" else 0):
        if o.type == "MESH":
            print(f"    {tris(o):>6}  {o.name}")
    for k, v in rows.items():
        print(f"  TRIS {k:<40} {v}")
    # mesh hygiene: closed (backface-culled in engine), every face has a material, no stray helpers
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        if o.name.startswith("_"):
            print("  WARN leftover helper mesh", o.name)
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
        empty = [i for i, m in enumerate(o.data.materials) if m is None]
        if nm or empty or not o.data.uv_layers:
            print(f"  WARN {o.name}: non-manifold edges {nm}, empty slots {empty}, uv {len(o.data.uv_layers)}")
    with open(os.path.join(OUT, "_wip", "tris.json"), "w") as f:
        json.dump(rows, f, indent=2)
    return rows


# ================================================================================================= RENDER
def render_world():
    bc.setup_studio(bg=(0.24, 0.25, 0.27))
    w = bpy.context.scene.world
    nt = w.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_WORLD")
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    if not any(n.type == "LIGHT_PATH" for n in nt.nodes):
        bg2 = nt.nodes.new("ShaderNodeBackground")
        bg2.inputs[0].default_value = (1.9, 1.92, 1.96, 1)
        bg2.inputs[1].default_value = 1.0
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(bg.outputs[0], mix.inputs[1])
        nt.links.new(bg2.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs[0])
    vs = bpy.context.scene.view_settings
    vs.exposure = float(os.environ.get("WARDEN_EXPOSURE", "-0.2"))
    try:
        vs.look = os.environ.get("WARDEN_LOOK", "AgX - Punchy")
    except TypeError:
        pass


def show_only(objs):
    keep = set(o.name for o in objs)
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.hide_render = o.name not in keep


def rv(prefix, objs, views, res=(1600, 800), focus=None, margin=1.10, samples=None, lens=85, rename=None,
       ortho=False):
    show_only(objs)
    paths = bc.render_views(REN, prefix, objs=[o for o in objs if o.type == "MESH"], views=views, res=res,
                            engine="CYCLES", samples=samples or ARGS.samples, lens=lens, margin=margin, focus=focus,
                            ortho=ortho)
    if rename:
        out = []
        for p, nm in zip(paths, rename):
            q = os.path.join(REN, f"{prefix}_{nm}.png")
            if os.path.normcase(os.path.abspath(p)) != os.path.normcase(os.path.abspath(q)):
                os.replace(p, q)
            out.append(q)
        return out
    return paths


TOP = (0.001, 0.0, 1.0)  # camera above; screen-up = -X (shooter's right), muzzle to the left


def exact_side(objs, name, side="+X"):
    """1 px = 1 mm orthographic side render matching art/concepts/warden/profile_sketch.png (top panel)."""
    show_only(objs)
    sc = bpy.context.scene
    bc.setup_cycles_gpu(sc, ARGS.samples)
    cam_data = bpy.data.cameras.get("_PreviewCam") or bpy.data.cameras.new("_PreviewCam")
    cam = bpy.data.objects.get("_PreviewCam") or bpy.data.objects.new("_PreviewCam", cam_data)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    sc.camera = cam
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 1.6
    sc.render.resolution_x, sc.render.resolution_y = 1600, 640
    sc.render.resolution_percentage = 100
    if side == "+X":
        cam.location = (2.0, -0.39, 0.015)
        cam.rotation_euler = (math.radians(90), 0, math.radians(90))
    sc.render.filepath = os.path.join(REN, name)
    sc.render.film_transparent = True
    sc.render.image_settings.color_mode = "RGBA"
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError:
        sc.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    cam_data.type = "PERSP"
    sc.render.film_transparent = False
    sc.render.image_settings.color_mode = "RGB"
    return sc.render.filepath


def socket_debug(B, objs):
    """Temporary coloured markers on every socket (not exported) -> renders/warden_sockets_*.png."""
    cols = {"Optic": (0.1, 0.9, 1.0), "Stock": (1.0, 0.8, 0.1), "Mag": (1.0, 0.4, 0.1), "Under": (0.2, 1.0, 0.2),
            "Side_R": (1.0, 0.1, 0.1), "Side_L": (0.2, 0.3, 1.0), "Muzzle": (1.0, 1.0, 1.0),
            "LeftHand": (1.0, 0.2, 1.0)}
    marks = []
    for nm, c in cols.items():
        m = bc.material("_dbg_" + nm, c, rough=0.4, emission=c, emission_strength=4.0)
        o = bc.sphere("_dbg_" + nm, 0.007, loc=B["sockets"][nm].matrix_world.translation, segments=16, rings=8, mat=m)
        marks.append(o)
    paths = rv("warden_sockets", objs + marks, ("left", "right", TOP, (0.7, -1.0, -0.4)), res=(1600, 800),
               margin=1.0, samples=24, rename=["left", "right", "top", "below"])
    for o in marks:
        bpy.data.objects.remove(o, do_unlink=True)
    return paths


ATT_DIR = r"F:/git/val etf/assets/weapons/attachments/tactical"


def fitcheck(B, default):
    """Read-only fit check against the shared attachments other agents built (if their exports exist):
    bipod on _Under, laser_R on _Side_R (-X), flashlight_L on _Side_L (+X). Imported only for these renders;
    nothing is exported or saved with them."""
    plan = (("ATT_bipod.glb", "Under"), ("ATT_laser_R.glb", "Side_R"), ("ATT_flashlight_L.glb", "Side_L"))
    added = []
    for fn, sk in plan:
        p = os.path.join(ATT_DIR, fn)
        if not os.path.exists(p):
            log("fitcheck: missing", fn)
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=p)
        new = [o for o in bpy.data.objects if o not in before]
        roots = [o for o in new if o.parent is None or o.parent not in new]
        for r in roots:
            r.matrix_world = Matrix.Translation(B["sockets"][sk].matrix_world.translation) @ r.matrix_world
        added += new
    bpy.context.view_layer.update()
    objs = default + [o for o in added if o.type == "MESH"]
    out = rv("warden_fitcheck", objs, ("right", "left"), margin=1.04)
    out += rv("warden_fitcheck", objs, ("three_quarter",), margin=0.86, focus=((0, -0.40, -0.03), 0.72))
    out += rv("warden_fitcheck", objs, ("front",), res=(900, 900), ortho=True, margin=1.0,
              focus=((0, -0.39, -0.04), 0.22))
    for o in added:
        bpy.data.objects.remove(o, do_unlink=True)
    return out


def do_renders(B, mode):
    render_world()
    s = B["sockets"]
    for p, sk in ((B["ss"], "Stock"), (B["sf"], "Stock"), (B["m5"], "Mag"), (B["m8"], "Mag")):
        if p.parent is None:
            p.matrix_world = Matrix.Translation(Vector(SOCKETS[sk]))
    bpy.context.view_layer.update()
    base = base_objs(B)
    default = base + tree(B["ss"]) + tree(B["m5"])
    out = []
    if mode in ("quick", "full", "compare"):
        out += rv("warden", default, ("right", "left"), samples=None if mode != "quick" else 24)
        out += rv("warden", default, ("three_quarter",), samples=None if mode != "quick" else 24, margin=0.86,
                  focus=((0, -0.40, 0.0), 0.70))
        out += [exact_side(default, "warden_exact_side.png")]
    if mode == "full":
        out += rv("warden", default, (TOP,), res=(1600, 640), rename=["top"])
        out += rv("warden", default, ("front", "back"), res=(900, 900), focus=((0, -0.39, -0.02), 0.22),
                  ortho=True, margin=1.0)
        out += rv("warden", default, ("three_quarter_back",), margin=0.86, focus=((0, -0.38, -0.035), 0.82))
        out += rv("warden", default, ("low",), margin=0.86, focus=((0, -0.40, 0.0), 0.70))
        # roughly what the player sees: from behind/above the right shoulder, down the rail
        out += rv("warden", default, ((-0.22, 1.0, 0.40),), res=(1600, 900), lens=40, margin=0.80,
                  focus=((0, -0.36, 0.06), 0.55), rename=["fpv"])
        # close-ups
        out += rv("warden_cu", default, ((0.9, -0.8, 0.45),), res=(1200, 900), focus=((0, -1.02, BZ), 0.11),
                  rename=["brake"])
        out += rv("warden_cu", default, ((-1.0, 0.55, 0.45),), res=(1200, 900), focus=((-0.04, 0.03, 0.06), 0.13),
                  rename=["bolt"])
        # bolt cycle (review fix check): lifted in place (handle root rotates behind the receiver, in free air),
        # then fully open (0.13 m back) -- the shroud stops in front of the stock upright, the handle passes
        # under the cheek riser. Also checks the pivot/origin and the documented animation signs.
        bolt = B["bolt"]
        loc0, rot0 = bolt.location.copy(), bolt.rotation_euler.copy()
        bolt.rotation_euler[1] = math.radians(bolt["lift_deg"])
        bpy.context.view_layer.update()
        out += rv("warden_cu", default, ((-0.6, 1.0, 0.55),), res=(1200, 900), focus=((0, 0.09, 0.09), 0.11),
                  rename=["bolt_lifted"])
        bolt.location.y += bolt["travel_m"]
        bpy.context.view_layer.update()
        out += rv("warden_cu", default, ((-1.0, 0.55, 0.45),), res=(1200, 900), focus=((-0.02, 0.15, 0.07), 0.20),
                  rename=["bolt_open"])
        out += rv("warden_bolt_open", default, ("left",), res=(1400, 900), focus=((0, 0.15, 0.05), 0.21))
        out += rv("warden_bolt_open", default, ((-0.22, 1.0, 0.40),), res=(1400, 900), lens=40, margin=0.8,
                  focus=((0, 0.05, 0.08), 0.30), rename=["fpv"])
        alt0 = base + tree(B["sf"]) + tree(B["m8"])
        out += rv("warden_bolt_open", alt0, ((-1.0, 0.55, 0.45),), res=(1200, 900), focus=((-0.02, 0.15, 0.05), 0.20),
                  rename=["folding_stock"])
        bolt.location, bolt.rotation_euler = loc0, rot0
        bpy.context.view_layer.update()
        out += rv("warden_cu", default, ((-1.0, -0.25, 0.25),), res=(1400, 900), focus=((0, -0.12, 0.05), 0.20),
                  rename=["receiver_right"])
        out += rv("warden_cu", default, ((1.0, -0.35, 0.3),), res=(1400, 900), focus=((0, -0.12, 0.05), 0.20),
                  rename=["receiver_left"])
        out += rv("warden_cu", default, ((0.8, -0.6, -0.35),), res=(1400, 900), focus=((0, -0.50, 0.06), 0.24),
                  rename=["handguard_under"])
        out += rv("warden_cu", default, ((0.75, -0.55, -0.45),), res=(1400, 900), focus=((0, -0.16, -0.06), 0.16),
                  rename=["magwell"])
        # variants: stocks + mags alone
        for key, nm in (("ss", "stock_standard"), ("sf", "stock_folding")):
            objs = tree(B[key])
            out += rv(f"warden_{nm}", objs, ("three_quarter", "right", "left", "three_quarter_back"),
                      res=(1200, 900), margin=1.25)
        for key, nm in (("m5", "mag_5"), ("m8", "mag_8")):
            objs = tree(B[key])
            out += rv(f"warden_{nm}", objs, ("three_quarter", "right", (0.6, -0.5, 1.0)), res=(900, 1000),
                      margin=1.25, rename=["three_quarter", "right", "top_feedlips"])
        # mag check with 2 rounds left (rounds 3..5 hidden, follower raised 3 x travel_per_round_m): the follower
        # sits right under the remaining rounds (review fix), the window shows daylight below it
        m5 = B["m5"]
        fol = next(o for o in m5.children if o.name.endswith("Follower"))
        rounds = sorted([o for o in m5.children if "_Round" in o.name], key=lambda o: o["round_index"])
        fz = fol.location.z
        fol.location.z += 3 * fol["travel_per_round_m"]
        bpy.context.view_layer.update()
        out += rv("warden_mag_5_check", [m5, fol] + rounds[:2], ("right", (0.6, -0.5, 0.25)), res=(900, 1000),
                  margin=1.25, rename=["two_left", "two_left_three_quarter"])
        fol.location.z = fz + fol["travel_max_m"]
        bpy.context.view_layer.update()
        out += rv("warden_mag_5_check", [m5, fol], ((0.6, -0.5, 1.0),), res=(900, 1000), margin=1.25,
                  rename=["empty_top"])
        fol.location.z = fz
        bpy.context.view_layer.update()
        # base gun alone (no stock / mag): shows the stock-adapter lug and the empty magwell
        out += rv("warden_base_only", base, ("left", "three_quarter_back", (0.4, 0.9, -0.5)), res=(1600, 900),
                  margin=0.95, rename=["left", "three_quarter_back", "rear_low"])
        out += socket_debug(B, default)
        # the alternative loadout on the gun: folding stock + mag_8
        alt = base + tree(B["sf"]) + tree(B["m8"])
        out += rv("warden_alt", alt, ("right", "three_quarter"))
        # folded pose preview
        arm = B["sf"].children[0]
        arm.rotation_euler[2] = math.radians(arm["fold_angle_deg"])
        bpy.context.view_layer.update()
        out += rv("warden_alt_folded", alt, ("three_quarter", TOP), rename=["three_quarter", "top"])
        arm.rotation_euler[2] = 0
        bpy.context.view_layer.update()
        out += fitcheck(B, default)
    if mode == "fitcheck":
        out += fitcheck(B, default)
    log("rendered", len(out))
    return out


# =================================================================================================== MAIN
B = build_all()
log("built")
rows = report(B)
if not ARGS.no_export:
    do_exports(B)
if ARGS.render != "none":
    do_renders(B, ARGS.render)
log("done")
