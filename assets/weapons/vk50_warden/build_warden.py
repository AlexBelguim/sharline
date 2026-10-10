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

Proportions: art/concepts/warden/concept_main.png at 1 px = 1 mm (DIRECTION_LOG item 13 -- the first build followed the
BRIEF's bulky profile sketch). compare.py traces the concept outline and reports the silhouette IoU.

Build safety: every boolean uses Blender's MANIFOLD solver (EXACT is not deterministic in 5.2); the script builds
twice and refuses to export unless both builds match, every mesh passes a closed-mesh gate (no boundary /
non-manifold edges, no zero-area triangles), the handguard slots and the magwell are ray-checked as open, and the
exported glb files are re-imported and gated again.

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

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--render", default="none", help="none | quick | full | compare | fitcheck")
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--no-export", action="store_true")
ap.add_argument("--out", default=r"F:/git/val etf/assets/weapons/vk50_warden",
                help="output folder (default: the asset folder; a scratch folder for determinism rebuilds)")
ap.add_argument("--no-det-check", action="store_true", help="skip the build-twice determinism check")
ap.add_argument("--no-gate", action="store_true", help="report mesh-gate failures but export anyway")
ARGS = ap.parse_args(argv)

OUT = os.path.abspath(ARGS.out)
REN = os.path.join(OUT, "renders")
WIP = os.path.join(OUT, "_wip")
P = "WARDEN"
# ---- layout: concept_main.png proportions at 1 px = 1 mm (DIRECTION_LOG item 13: "follow the concept, the first
# build was bulky and stumpy"). Origin = top centre of the pistol grip, muzzle -Y, bore x=0 z=BZ.
BZ = 0.075                          # bore axis height
RAIL_TOP_Z = 0.117                  # top rail top surface (42 mm over the bore, like the concept)
RAIL_BASE_Z = RAIL_TOP_Z - 0.0095   # rail base = top of the receiver / handguard spine
HG_Y0, HG_Y1 = -0.677, -0.336       # handguard nose tip / rear end (= upper receiver front face)
HG_W, HG_BOT = 0.028, 0.037         # handguard half width / underside (slim: 56 x 70 mm incl. the spine)
HG_SLOT_L, HG_SLOT_H = 0.055, 0.010
HG_SLOTS = [(-0.555, 0.086), (-0.485, 0.086), (-0.415, 0.086),        # upper row (staggered; concept slot centres
            (-0.585, 0.0645), (-0.515, 0.0645), (-0.445, 0.0645)]   # -0.559/-0.488/-0.416 and -0.589/-0.515/-0.441)
HG_BSLOTS = (-0.505, -0.435)
REC_Y0, REC_Y1 = -0.336, -0.100     # upper receiver front / rear face
CH_Y0, CH_W = -0.3375, 0.0275       # chassis (lower receiver) front face (1.5 mm into the handguard: no slit) / half width
CH_BOT, CH_TOP_REAR = 0.010, 0.063  # chassis underside behind the magwell / chassis top line (concept 0.061)
CHANNEL_R = 0.0165                  # bolt channel along the chassis / stock top: the shroud (r 0.015) sits 3 mm
                                    # down in it, so no daylight shows under it and the bolt still slides free
STOCK_Y = 0.022                     # chassis rear face = stock interface (concept: sand starts here)
TOPRAIL_Y0, TOPRAIL_Y1 = -0.640, -0.110
UNDER_Y = -0.600                    # bottom rail centre (bipod)
SIDE_Y, SIDE_Z, SIDE_L = -0.643, 0.066, 0.040   # short side rails in the nose, ahead of the lower slot row
OPTIC_Y = -0.190                    # default optic clamp centre (concept: rings at -0.215 / -0.150)
BAR_R = 0.0175                      # exposed barrel radius (concept: 35 mm)
RACE_R, BOLT_R = 0.016, 0.0142      # raceway / bolt body radius (bolt body bottom 0.0608: clears the chassis top)
SH_R, SH_Y1 = 0.015, -0.045         # bolt shroud radius (concept: 30 mm) / rear face (closed)
HANDLE_Y = -0.085                   # bolt-handle root centre (on the shroud, behind the receiver rear face -0.100)
KNOB_R = 0.0175                     # hex knob circumradius (35 mm, concept)
BOLT_LIFT_DEG = 60.0                # bolt cycle: lift about the bore axis ...
BOLT_TRAVEL = 0.130                 # ... then slide 0.13 m toward the butt (shroud rear face -0.045 -> +0.085)
EPORT_Y = -0.200                    # ejection port centre (-X)
BWIN_Y, BWIN_Z, BWIN_L, BWIN_H = -0.215, 0.0825, 0.110, 0.015   # +X bolt window (concept's gunmetal strip)
SAFETY_Y, SAFETY_Z = -0.036, 0.034  # rotary safety hub (+X)
TRIG_PIVOT = (0, -0.090, 0.012)
MAG_Y0, MAG_Y1, MAG_TOP_Z = -0.299, -0.154, 0.046   # magazine front / rear face, top of the feed lips
# (145 mm: the shortest box that holds a real 138 mm 12.7 mm cartridge; concept 130 mm, rear face matched)
MAG_W, MAG_CH, MAGWELL_W = 0.0195, 0.0169, 0.0205   # mag outer half width / channel half width / magwell half width
MAG_WIN_Y = -0.2265                 # mag-check window centre
MONO_Y = 0.2335                     # monopod axis (inside the stock's rear upright)
RISER_POSTS = (0.135, 0.195)        # cheek-riser posts (spread 60 mm under the pad)
T0 = time.time()


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
    r = min(r, w / 2, h / 2)
    pts = []
    for (ccx, ccy, a0) in [(cu + w / 2 - r, cv + h / 2 - r, 0), (cu - w / 2 + r, cv + h / 2 - r, 90),
                           (cu - w / 2 + r, cv - h / 2 + r, 180), (cu + w / 2 - r, cv - h / 2 + r, 270)]:
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    # a stadium (r = half the short side) has no straight segment there: drop the doubled apex points, which made
    # zero-length cutter edges and left sliver / non-manifold seams in the boolean result
    out = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > 1e-6:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= 1e-6:
        out.pop()
    return out


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


BOOL_SOLVER = "MANIFOLD"
BOOL_LOG = []


def boolean(obj, cutter, op):
    """Local boolean (bc.boolean hard-codes the EXACT solver). Blender 5.2's EXACT solver is not deterministic: the
    same two prisms gave different vertex positions in about 1 run in 4 (even with -t 1), which broke the
    build-twice determinism gate. The MANIFOLD solver is deterministic, faster and leaves fewer stray vertices.
    It refuses non-manifold operands (returns the input unchanged), so a boolean whose cutter overlaps the object
    but changes nothing fails the build instead of silently shipping an uncut part."""
    me0 = obj.data
    n0 = len(me0.vertices)
    co0 = [0.0] * (n0 * 3)
    me0.vertices.foreach_get("co", co0)
    s0 = sum(abs(c) for c in co0)
    m = obj.modifiers.new("Bool_" + cutter.name, "BOOLEAN")
    m.object = cutter
    m.operation = op
    m.solver = BOOL_SOLVER
    bc.apply_modifiers(obj, only=[m.name])
    me = obj.data
    co = [0.0] * (len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    unchanged = len(me.vertices) == n0 and abs(sum(abs(c) for c in co) - s0) < 1e-9
    if unchanged:
        # did the cutter actually reach the object? (bounding-box test in world space)
        def bb(o):
            ps = [o.matrix_world @ Vector(c) for c in o.bound_box]
            return [min(p[i] for p in ps) for i in range(3)], [max(p[i] for p in ps) for i in range(3)]
        (a0, a1), (b0, b1) = bb(obj), bb(cutter)
        if all(a0[i] < b1[i] and b0[i] < a1[i] for i in range(3)):
            BOOL_LOG.append((obj.name, cutter.name, op))
    bpy.data.objects.remove(cutter, do_unlink=True)
    if not me.polygons:
        raise SystemExit(f"[warden] boolean {op} {cutter.name} emptied {obj.name}")
    return obj


def cut(obj, *cutters):
    for c in cutters:
        boolean(obj, c, "DIFFERENCE")
    return obj


def union(obj, *others):
    for c in others:
        boolean(obj, c, "UNION")
    return obj


def intersect(obj, other):
    return boolean(obj, other, "INTERSECT")


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


def finish_outer(obj, width, segs, inner, angle=30, ddist=1e-5):
    """finish() variant that bevels only the edges a player can see: edges whose midpoint satisfies inner(co) (inside
    a hollow shell, e.g. the slot rims on the handguard's inner wall) keep a plain hard corner. Saves the triangles
    of bevels nobody can see (triangle-budget review item). ddist = dissolve_degenerate distance (review r2: on the
    handguard the default 1e-5 collapsed the walls of two +X top vents and closed them over -> 1e-6 there)."""
    degen(obj, ddist)
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
    degen(obj, ddist)
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
    backface-culls): merge near-coincident verts of the open edges (< 0.12 mm) and fill any remaining small boundary loops.
    Review r2 (determinism): the vertex list is sorted by index -- a Python set of BMVerts iterates in id/address
    order, which differs between runs and made remove_doubles pick different survivors (receiver 1,824 vs 1,836 tris)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.index_update()
    nm = [e for e in bm.edges if not e.is_manifold]
    if nm:
        vs = sorted({v.index: v for e in nm for v in e.verts}.items())
        bmesh.ops.remove_doubles(bm, verts=[v for _, v in vs], dist=0.00012)
        bnd = [e for e in bm.edges if e.is_boundary]
        if bnd:
            bmesh.ops.holes_fill(bm, edges=bnd, sides=12)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
    bm.free()
    return obj


def tri_clean(obj):
    """Review r2 (minor 6): triangulate in Blender with BEAUTY (instead of the exporter's plain fan/polyfill split of
    the long boolean n-gons), keeping the custom (hardened / weighted) normals, then remove every zero-area triangle:
    edges shorter than 1e-6 m are collapsed, and collinear 'needle' triangles get their longest edge rotated so both
    neighbours become real triangles. The glb then ships exactly these triangles."""
    m = obj.modifiers.new("Tri", "TRIANGULATE")
    m.quad_method = "BEAUTY"
    m.ngon_method = "BEAUTY"
    m.min_vertices = 4
    m.keep_custom_normals = True
    bc.apply_modifiers(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
    for _ in range(16):
        ng = [f for f in bm.faces if len(f.verts) > 3]      # dissolve_degenerate / face_join leave n-gons behind
        if ng:
            bmesh.ops.triangulate(bm, faces=ng, quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.faces.index_update()
        bm.edges.index_update()
        bad = sorted((f for f in bm.faces if f.calc_area() < 1e-10), key=lambda f: f.index)
        if not bad:
            break
        for f in bad:
            if not f.is_valid or f.calc_area() >= 1e-10:
                continue
            es = sorted(f.edges, key=lambda e: (-e.calc_length(), e.index))
            if es[0].calc_length() < 5e-5:
                # sub-0.05 mm crumb (bevel corner at a slot tip): collapse it to a point
                bmesh.ops.collapse(bm, edges=list(f.edges), uvs=False)
                continue
            # needle (one vertex on the opposite edge): rotate that longest edge, so the needle and its neighbour
            # become two real triangles (rotate_edges keeps the mesh manifold; the old join + connect could not)
            e = es[0]
            if len(e.link_faces) == 2 and all(len(g.verts) == 3 for g in e.link_faces):
                bmesh.ops.rotate_edges(bm, edges=[e], use_ccw=False)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def mesh_gate(obj):
    """Closed-mesh gate (review r2): weld by POSITION ONLY at 1e-6 m (what an importer sees), then count boundary
    edges, non-manifold edges and zero-area (< 1e-10 m^2) triangles. All three must be 0 for an exported mesh."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.index_update()
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    r = dict(boundary=sum(1 for e in bm.edges if e.is_boundary),
             nonmanifold=sum(1 for e in bm.edges if not e.is_manifold),
             zero_area=sum(1 for f in bm.faces if f.calc_area() < 1e-10),
             tiny_lt_0_01mm2=sum(1 for f in bm.faces if f.calc_area() < 1e-8),
             ngons=sum(1 for f in bm.faces if len(f.verts) > 3))
    bad = [e for e in bm.edges if not e.is_manifold][:3]
    r["examples"] = [[round(c, 4) for c in (e.verts[0].co + e.verts[1].co) / 2] for e in bad]
    bm.free()
    return r


def world_uvs(obj):
    """One fresh smart-projected UV layer, rescaled to a constant world texel density: 1 UV unit = tile_m metres
    of the face's material (so wear / brushing / stipple have the same scale on every part and every export)."""
    me = obj.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    try:
        bc.smart_uv(obj, angle=66, margin=0.01)
    except RuntimeError:
        log("smart_uv failed on", obj.name, "faces", len(me.polygons), "in view layer",
            obj.name in bpy.context.view_layer.objects, "mode", bpy.context.mode)
        raise
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


def rail(name, length, mat, bevel=0.0, ends=False):
    """Stylised Picatinny along local Y, centred at y=0, base z=0, top z=0.0095, top width 0.021,
    cross slots 0.0045 long x 0.003 deep every 0.010 m (centred so both ends keep a full tooth).
    ends=True ramps both ends down 45 degrees (concept: sloped rail ends, no sharp blunt block)."""
    obj = prism(name, RAIL_SEC, "Y", -length / 2, length / 2, mat)
    if ends:
        h = length / 2
        intersect(obj, prism("_rends", [(-h - 0.001, -0.003), (h + 0.001, -0.003), (h + 0.001, 0.0035),
                                        (h - 0.006, 0.0105), (-h + 0.006, 0.0105), (-h - 0.001, 0.0035)],
                             "X", -0.02, 0.02))
    n = int((length - 0.008) / 0.010) + 1
    first = -(n - 1) * 0.010 / 2
    cs = [box("_slot", (0.03, 0.0045, 0.006), (0, first + i * 0.010, 0.0095 - 0.003 + 0.003)) for i in range(n)]
    cutter = join(cs, "_slots")
    cut(obj, cutter)
    finish(obj, bevel, 1)
    return obj


def slot_check(hg):
    """Review r2 (major 1, generalised to every handguard opening): each slot must be a clean through-cut.
    A ray along -X through the centre of a side slot must cross the whole shell without touching it (+X slot, bore
    cavity, -X slot); a ray straight up through a bottom slot must first hit the cavity ROOF. Fails the build
    otherwise, so a half-applied EXACT boolean (the r2 'ghost pocket' bug) can never ship again."""
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    bm.from_mesh(hg.data)
    bm.transform(hg.matrix_world)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    bad = []
    for (yc, zc) in HG_SLOTS:
        loc, _, _, _ = t.ray_cast(Vector((0.06, yc, zc)), Vector((-1, 0, 0)))
        if loc is not None:
            bad.append(("side", yc, zc, tuple(round(c, 4) for c in loc)))
    for yc in HG_BSLOTS:
        loc, _, _, _ = t.ray_cast(Vector((0.0, yc, 0.0)), Vector((0, 0, 1)))
        if loc is None or loc.z < 0.090:
            bad.append(("bottom", yc, None if loc is None else round(loc.z, 4)))
    if bad:
        raise SystemExit(f"[warden] SLOT CHECK FAILED (slot not cut through): {bad}")
    log(f"slot check: all {len(HG_SLOTS)} side slots and {len(HG_BSLOTS)} bottom slots cut through")


def magwell_check(cha):
    """Rays straight up through the magwell (3 x 3 grid) must cross the open well and first meet the bridge under
    the receiver (z >= 0.045). Catches a face spanning the opening (a 1 mm rear wall once made the bevel do that,
    which no closed-mesh gate notices because the mesh stays manifold)."""
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    bm.from_mesh(cha.data)
    bm.transform(cha.matrix_world)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    bad = []
    for x in (-0.012, 0.0, 0.012):
        for y in (MAG_Y0 + 0.012, (MAG_Y0 + MAG_Y1) / 2, MAG_Y1 - 0.012):
            loc, _, _, _ = t.ray_cast(Vector((x, y, -0.08)), Vector((0, 0, 1)))
            if loc is None or loc.z < 0.045:
                bad.append((x, y, None if loc is None else round(loc.z, 4)))
    if bad:
        raise SystemExit(f"[warden] MAGWELL CHECK FAILED (something spans the opening): {bad}")
    log("magwell check: open (9 rays)")


def place(obj, rot_y_deg=0.0, loc=(0, 0, 0)):
    obj.matrix_basis = Matrix.Translation(Vector(loc)) @ Matrix.Rotation(math.radians(rot_y_deg), 4, "Y")
    return bake(obj)


# =========================================================================================== BASE GUN
# Proportions follow art/concepts/warden/concept_main.png at 1 px = 1 mm (DIRECTION_LOG item 13), mapped to gun
# coordinates as  y = px_x / 1000 - 1.156,  z = 0.335 - px_y / 1000  (brake front -1.100, bore z 0.075).
def build_base(M, col):
    G, GM, S, SS = M["G"], M["GM"], M["S"], M["SS"]
    parts = []

    # ------------------------------------------------------------------ upper receiver (monolithic)
    # section: flat sides x +-0.030, 10 mm top chamfers, the rail spine on top (x +-0.013, up to the rail base)
    rsec = [(-0.027, 0.054), (0.027, 0.054), (0.030, 0.057), (0.030, 0.090), (0.020, 0.100), (0.013, 0.100),
            (0.013, RAIL_BASE_Z), (-0.013, RAIL_BASE_Z), (-0.013, 0.100), (-0.020, 0.100), (-0.030, 0.090),
            (-0.030, 0.057)]
    rec = prism("WARDEN_Receiver", rsec, "Y", REC_Y0, REC_Y1, G)
    # the spine ramps down into the rear face (concept: sloped rail end over the bolt shroud)
    intersect(rec, prism("_rside", [(REC_Y0 - 0.01, 0.04), (REC_Y0 - 0.01, 0.13), (REC_Y1 - 0.0085, 0.13),
                                    (REC_Y1, 0.1015), (REC_Y1, 0.04)], "X", -0.05, 0.05))
    # bolt raceway (open at the rear face, the bolt body slides in it)
    cut(rec, cyl("_race", RACE_R, 0.200, (0, -0.190, BZ), "Y", 24))
    # ejection port, shooter's RIGHT (-X)
    ep = rounded_rect(EPORT_Y, BZ + 0.001, 0.100, 0.024, 0.006, 3)
    cut(rec, prism("_eport", ep, "X", -0.05, -0.008))
    # same 45-degree lead-in chamfer as the +X bolt window (3 mm)
    cut(rec, hull("_epch", [(-0.027, y, z) for (y, z) in ep] + [(-0.031, y, z) for (y, z) in offset_poly(ep, 0.004)]))
    # bolt window, LEFT (+X): the concept's gunmetal strip. A real opening into the raceway: the player sees the
    # bolt body (and its +X flutes) slide back when cycling. Replaces the removed ammo counter as this side's focus.
    bw = rounded_rect(BWIN_Y, BWIN_Z, BWIN_L, BWIN_H, 0.006, 3)
    cut(rec, prism("_bwin", bw, "X", 0.008, 0.05))
    # 45-degree, 4 mm chamfer round the window: it opens the slot to the light, so the gunmetal bolt reads as the
    # concept's bright strip instead of a black slit
    cut(rec, hull("_bwch", [(0.026, y, z) for (y, z) in bw] + [(0.031, y, z) for (y, z) in offset_poly(bw, 0.005)]))
    # bevel what a player sees; the raceway interior (and the port / window rims where they meet it) stays hard
    finish_outer(rec, 0.0032, 1, lambda c: c.x * c.x + (c.z - BZ) ** 2 < (RACE_R + 0.0007) ** 2 and c.y > -0.30)
    parts.append(rec)

    # bolt-release button (LEFT, +X), behind the bolt window
    btn = cyl("WARDEN_BoltRelease", 0.0045, 0.005, (0.0315, -0.122, 0.068), "X", 12, GM)
    finish(btn, 0.001, 1)
    parts.append(btn)
    # rotary safety lever (LEFT, +X, above the grip, under the thumb); origin at its pivot
    hub = cyl("_sfh", 0.0055, 0.004, (0.0300, SAFETY_Y, SAFETY_Z), "X", 14, GM)   # 0.5 mm off the chassis side
    finish(hub, 0.001, 1)
    pad = prism("_sfp", round_poly(band([(SAFETY_Y, SAFETY_Z), (SAFETY_Y + 0.007, SAFETY_Z - 0.015)], 0.0062),
                                   0.002, 2), "X", 0.0283, 0.0310, GM)
    finish(pad, 0.0008, 1)
    saf = join([hub, pad], "WARDEN_Safety")
    set_origin(saf, (0.0280, SAFETY_Y, SAFETY_Z))
    parts.append(saf)

    # ------------------------------------------------------------------ chassis (lower receiver, magwell, chin,
    # trigger area and the rear extension that carries the grip and the stock)
    cprof = [(STOCK_Y, CH_TOP_REAR), (CH_Y0, CH_TOP_REAR), (CH_Y0, 0.032), (-0.325, 0.022), (-0.311, 0.017),
             (-0.1475, -0.0055), (-0.144, 0.004), (-0.140, CH_BOT), (STOCK_Y, CH_BOT)]
    # (the magwell's rear wall is 5.5 mm at the bottom: a 1 mm sliver there made the bevel span the opening)
    cha = prism("WARDEN_Chassis", cprof, "X", -CH_W, CH_W, G)
    # chin under the handguard rear (concept: dark wedge stepping down from the handguard bottom)
    chin = prism("_chin", [(-0.328, 0.040), (-0.405, 0.040), (-0.391, 0.026), (-0.328, 0.026)], "X", -0.020, 0.020)
    union(cha, chin)
    # magwell (the mag's top-front lip seats at the Mag socket, 4 mm under the raceway)
    cut(cha, box("_mw", (2 * MAGWELL_W, MAG_Y1 - MAG_Y0 + 0.002, 0.090), (0, (MAG_Y0 + MAG_Y1) / 2,
                                                                         MAG_TOP_Z + 0.003 - 0.045)))
    # trigger slot
    cut(cha, box("_tslot", (0.010, 0.024, 0.030), (0, -0.090, 0.012)))
    # bolt channel: under the receiver it continues the raceway (hidden), behind it the shroud and the open bolt
    # body ride in it
    # (starts at y -0.285, inside the raceway's span, so its end cap is not coplanar with the raceway's end face)
    cut(cha, cyl("_bch", CHANNEL_R, STOCK_Y + 0.002 + 0.285, (0, (STOCK_Y + 0.002 - 0.285) / 2, BZ), "Y", 24))
    # rear stock-adapter lug: every stock clamps over it (hidden inside the stock's front block when assembled)
    lug = prism("_lug", [(STOCK_Y - 0.004, 0.046), (STOCK_Y + 0.011, 0.046), (STOCK_Y + 0.014, 0.043),
                         (STOCK_Y + 0.014, 0.021), (STOCK_Y + 0.011, 0.018), (STOCK_Y - 0.004, 0.018)],
                "X", -0.012, 0.012)
    cut(lug, cyl("_lugh", 0.003, 0.05, (0, STOCK_Y + 0.007, 0.032), "X", 12))
    union(cha, lug)
    for sx in (1, -1):
        # trapezoid relief panel on the lower receiver front (concept)
        cut(cha, prism("_trap", round_poly([(-0.300, 0.042), (-0.238, 0.042), (-0.247, 0.051), (-0.291, 0.051)],
                                           0.0015, 1), "X", sx * (CH_W - 0.0012), sx * 0.05))
        # stock-release latch recess on the rear extension
        cut(cha, prism("_latch", rounded_rect(0.002, 0.033, 0.018, 0.016, 0.003, 2), "X", sx * (CH_W - 0.0012),
                       sx * 0.05))
        # long panel groove under the receiver overhang, ahead of the magwell
        cut(cha, prism("_cg", band([(CH_Y0 - 0.005, 0.047), (-0.312, 0.047)], 0.0022), "X", sx * (CH_W - 0.0012),
                       sx * 0.05))
    # maker plate recess on the hero side (+X) where the concept's counter was (no screen, no emissive)
    cut(cha, prism("_plate", rounded_rect(-0.176, 0.034, 0.046, 0.016, 0.004, 2), "X", CH_W - 0.0012, 0.05))
    finish(cha, 0.0030, 1)       # crisp single chamfers on the hard metal parts (stylized; tri budget)
    # take-down pins (heads on both sides), gunmetal
    pins = []
    for sx in (1, -1):
        for (yp, zp) in ((-0.321, 0.044), (-0.072, 0.040)):
            pn = cyl("_pin", 0.0042, 0.003, (sx * (CH_W + 0.0005), yp, zp), "X", 10, GM)
            finish(pn, 0.0009, 1)
            pins.append(pn)
    cha = join([cha] + pins, "WARDEN_Chassis")
    parts.append(cha)

    # ------------------------------------------------------------------ handguard (slim free-float shell)
    hsec = [(-0.021, HG_BOT), (0.021, HG_BOT), (HG_W, HG_BOT + 0.007), (HG_W, 0.088), (0.016, 0.100),
            (0.0125, 0.100), (0.0125, RAIL_BASE_Z), (-0.0125, RAIL_BASE_Z), (-0.0125, 0.100), (-0.016, 0.100),
            (-HG_W, 0.088), (-HG_W, HG_BOT + 0.007)]
    hg = prism("WARDEN_Handguard", hsec, "Y", -0.700, HG_Y1, G)
    # nose: the concept's raked front (tip at y -0.677, z 0.050), barrel leaves through the sloped face
    intersect(hg, prism("_hside", [(HG_Y1 + 0.01, 0.020), (HG_Y1 + 0.01, 0.130), (-0.6367, 0.130), (HG_Y0, 0.050),
                                   (-0.654, 0.020)], "X", -0.05, 0.05))
    # inner cavity (5 mm wall), open at the rear where the receiver front face closes it
    isec = [(-0.0175, 0.042), (0.0175, 0.042), (0.023, 0.0475), (0.023, 0.086), (0.0135, 0.0955), (-0.0135, 0.0955),
            (-0.023, 0.086), (-0.023, 0.0475)]
    cav = prism("_cav", isec, "Y", -0.668, HG_Y1 + 0.005)
    intersect(cav, prism("_cavs", [(-0.300, 0.020), (-0.300, 0.140), (-0.626, 0.140), (-0.6727, 0.0503),
                                   (-0.6476, 0.020)], "X", -0.05, 0.05))
    cut(hg, cav)
    # barrel exit hole in the nose face
    cut(hg, cyl("_bh", 0.0200, 0.06, (0, -0.670, BZ), "Y", 24))   # r 0.020: not tangent to the cavity roof
    # side slots: two staggered rows of three (concept rhythm), one joined cutter. Review r2 (major 2): both rows
    # lie inside the barrel's side silhouette (z 0.0565-0.0935), so no slot looks through the gun (no light pills)
    slots = [prism("_s", stadium(yc, zc, HG_SLOT_L, HG_SLOT_H, 3), "X", -0.06, 0.06) for (yc, zc) in HG_SLOTS]
    cut(hg, join(slots, "_slots"))
    # bottom slots
    cut(hg, join([prism("_sb", stadium(0.0, yc, 0.014, 0.045, 3), "Z", 0.030, 0.045) for yc in HG_BSLOTS],
                 "_bslots"))
    # bevel the outer shell only: the cavity corners and the slot rims on the inner wall stay hard
    finish_outer(hg, 0.0022, 1, lambda c: abs(c.x) < 0.0236 and 0.0414 < c.z < 0.0961 and c.y > -0.6735,
                 ddist=1e-6)
    flat_big_faces(hg)
    slot_check(hg)
    parts.append(hg)
    # clamp screws at the receiver joint (hex heads, both sides)
    for sx in (1, -1):
        for zc in (0.052, 0.075):
            s = cyl("_scr", 0.0036, 0.003, (sx * (HG_W + 0.0005), -0.352, zc), "X", 6, GM)
            finish(s, 0.0007, 1)
            parts.append(s)

    # ------------------------------------------------------------------ rails
    rt = rail("WARDEN_RailTop", TOPRAIL_Y1 - TOPRAIL_Y0, G, ends=True)
    place(rt, 0, (0, (TOPRAIL_Y0 + TOPRAIL_Y1) / 2, RAIL_BASE_Z))
    parts.append(rt)
    rb = rail("WARDEN_RailBottom", 0.110, G, ends=True)
    place(rb, 180, (0, UNDER_Y, HG_BOT))
    parts.append(rb)
    for sx, nm in ((-1, "WARDEN_RailSide_R"), (1, "WARDEN_RailSide_L")):
        rs = rail(nm, SIDE_L, G, ends=True)
        place(rs, 90 * sx, (sx * HG_W, SIDE_Y, SIDE_Z))
        parts.append(rs)

    # ------------------------------------------------------------------ barrel (slim, fluted) + brake
    bar = lathe_y("WARDEN_Barrel", [(0, -0.295), (0.0185, -0.295), (0.0185, -0.600), (BAR_R, -0.608),
                                    (BAR_R, -0.990), (0.0125, -0.992), (0.0125, -1.004), (0, -1.004)], steps=24,
                  mat=GM)
    for i in range(6):
        a = math.radians(30 + 60 * i)
        c = prism("_fl", stadium(0.0, -0.8235, 0.0060, 0.303, 4), "Z", 0.0, 0.010)  # local: tangential x, y
        # local x -> tangent, local y -> Y, local z -> radial (cos a, sin a) in the XZ plane; cuts 3 mm deep
        rmat = Matrix(((math.sin(a), 0, math.cos(a), 0),
                       (0, 1, 0, 0),
                       (-math.cos(a), 0, math.sin(a), 0),
                       (0, 0, 0, 1)))
        c.matrix_basis = Matrix.Translation(Vector((0.0145 * math.cos(a), 0, BZ + 0.0145 * math.sin(a)))) @ rmat
        cut(bar, c)
    smooth(bar, 40)
    parts.append(bar)

    # muzzle brake (concept: 108 x 47 mm block, three see-through ports getting smaller toward the rear)
    BH, BW = 0.0235, 0.026
    bs = prism("WARDEN_Brake", [(-0.992, BZ - 0.020), (-0.992, BZ + 0.020), (-0.996, BZ + BH), (-1.092, BZ + BH),
                                (-1.100, BZ + BH - 0.008), (-1.100, BZ - BH + 0.008), (-1.092, BZ - BH),
                                (-0.996, BZ - BH)], "X", -BW, BW, GM)
    intersect(bs, prism("_btop", [(-BW, -0.990), (BW, -0.990), (BW, -1.093), (BW - 0.007, -1.100),
                                  (-BW + 0.007, -1.100), (-BW, -1.093)], "Z", BZ - 0.05, BZ + 0.05))
    intersect(bs, prism("_bsec", [(-BW + 0.005, BZ - BH), (BW - 0.005, BZ - BH), (BW, BZ - BH + 0.005),
                                  (BW, BZ + BH - 0.005), (BW - 0.005, BZ + BH), (-BW + 0.005, BZ + BH),
                                  (-BW, BZ + BH - 0.005), (-BW, BZ - BH + 0.005)], "Y", -1.11, -0.98))
    # bore first: cut after the ports, the EXACT solver returned an empty mesh (the bore lies inside the port voids)
    cut(bs, cyl("_bore", 0.0090, 0.2, (0, -1.04, BZ), "Y", 20))
    # shallow frame around the small rear port (concept: a darker inset panel). Cut before the ports: cutting it
    # after them left a 3-edge non-manifold seam at the port corner
    for sx in (1, -1):
        cut(bs, prism("_pCr", rounded_rect(-1.0325, BZ, 0.017, 0.032, 0.004, 2), "X", sx * (BW - 0.0015),
                      sx * 0.05))
    # three see-through ports as ONE joined cutter (no top vents: the concept has none, and on this 52 mm block
    # they left non-manifold seams under the bevel)
    cut(bs, join([prism("_pA", rounded_rect(-1.0785, BZ, 0.019, 0.026, 0.0045, 2), "X", -0.06, 0.06),
                  prism("_pB", rounded_rect(-1.0535, BZ, 0.013, 0.027, 0.0040, 2), "X", -0.06, 0.06),
                  prism("_pC", rounded_rect(-1.0325, BZ, 0.0065, 0.022, 0.0030, 2), "X", -0.06, 0.06)],
                 "_ports"))
    finish(bs, 0.0020, 1)
    parts.append(bs)
    collar = lathe_y("WARDEN_BrakeCollar", [(0, -0.981), (0.0182, -0.981), (0.0200, -0.983), (0.0200, -0.9925),
                                            (0, -0.9925)], steps=8, mat=GM, angle=30)
    finish(collar, 0.0007, 1)
    parts.append(collar)

    # ------------------------------------------------------------------ pistol grip (sand) + stipple panels
    gp = [(-0.059, 0.012), (0.010, 0.012), (0.004, 0.004), (-0.001, -0.008), (0.000, -0.020), (0.040, -0.098),
          (0.039, -0.106), (0.032, -0.111), (-0.029, -0.119), (-0.036, -0.116), (-0.036, -0.109), (-0.031, -0.100),
          (-0.048, -0.040), (-0.054, -0.034), (-0.059, -0.032)]
    grip = prism("WARDEN_Grip", gp, "X", -0.016, 0.016, S)
    finish(grip, 0.0055, 3)
    parts.append(grip)
    pad_pts = round_poly([(-0.042, -0.036), (-0.004, -0.024), (0.029, -0.088), (-0.026, -0.094)], 0.004, 2)
    for sx in (1, -1):
        pad = prism("_gpad", pad_pts, "X", sx * 0.0145, sx * 0.0172, SS)
        finish(pad, 0.0009, 1)
        parts.append(pad)
        gs = cyl("_gscr", 0.0032, 0.003, (sx * 0.0162, 0.006, -0.104), "X", 12, GM)
        finish(gs, 0.0007, 1)
        parts.append(gs)

    # ------------------------------------------------------------------ trigger guard (open-top U) + trigger
    tg = prism("WARDEN_TriggerGuard", [(-0.140, 0.012), (-0.140, -0.016), (-0.132, -0.030), (-0.118, -0.037),
                                       (-0.066, -0.037), (-0.056, -0.029), (-0.056, 0.012)], "X", -0.0095, 0.0095, G)
    cut(tg, prism("_tgh", round_poly([(-0.128, 0.020), (-0.128, -0.020), (-0.116, -0.027), (-0.072, -0.027),
                                      (-0.068, -0.022), (-0.068, 0.020)], 0.006, 3), "X", -0.05, 0.05))
    finish(tg, 0.0022, 2)
    parts.append(tg)
    # mag release paddle (between the mag and the guard)
    mr = prism("WARDEN_MagRelease", [(-0.1505, 0.004), (-0.1435, 0.004), (-0.143, -0.029), (-0.147, -0.035),
                                     (-0.151, -0.033)], "X", -0.008, 0.008, GM)
    finish(mr, 0.0010, 1)
    parts.append(mr)
    # curved trigger blade (concept hook), origin at its pivot
    trig = prism("WARDEN_Trigger", [(-0.093, 0.018), (-0.086, 0.018), (-0.086, 0.000), (-0.088, -0.010),
                                    (-0.094, -0.019), (-0.102, -0.024), (-0.1045, -0.0215), (-0.098, -0.015),
                                    (-0.0935, -0.007), (-0.0925, 0.003)], "X", -0.0035, 0.0035, GM)
    finish(trig, 0.0010, 1)

    # ------------------------------------------------------------------ bolt (separate, origin = bolt-axis rear)
    # shroud: flat rear face with ONE crisp 45-degree chamfer (review r2 minor 4: no dome next to the knob)
    bolt = lathe_y("WARDEN_Bolt", [(0, SH_Y1), (SH_R - 0.004, SH_Y1), (SH_R, SH_Y1 - 0.004), (SH_R, -0.0985),
                                   (BOLT_R, -0.1000), (BOLT_R, -0.271), (BOLT_R - 0.002, -0.275), (0, -0.275)],
                   steps=24, mat=GM, angle=35)
    # bolt-body flutes: three facing the ejection port (-X), two facing the +X bolt window
    for ang in (150, 180, 210, 18, 48):   # angle around the bore in the XZ plane, 0 = +X, 180 = -X
        a = math.radians(ang)
        c = box("_bfl", (0.0040, 0.120, 0.006), (0, 0, 0))
        c.matrix_basis = (Matrix.Translation(Vector((BOLT_R * math.cos(a), -0.200, BZ + BOLT_R * math.sin(a)))) @
                          Matrix.Rotation(math.radians(90) - a, 4, "Y"))
        bake(c)
        cut(bolt, c)
    gpro = [(0.025, -0.0605), (SH_R - 0.0015, -0.0605), (SH_R - 0.0015, -0.0575), (0.025, -0.0575)]
    cut(bolt, lathe_y("_bg", gpro + [gpro[0]], steps=24))
    smooth(bolt, 35)
    # handle root on the shroud's -X side, BEHIND the receiver rear face: the 60-degree lift happens in free air
    root = box("_broot", (0.020, 0.016, 0.018), (-0.019, HANDLE_Y, 0.077), GM)
    finish(root, 0.0025, 1)
    # handle arm: out and down along the shooter's RIGHT (-X), clear of the chassis side
    # (leans out 32 deg: 7.8 mm from the chassis' top -X edge at z 0.063, so the closed handle clears it)
    p0, p1 = Vector((-0.028, HANDLE_Y, 0.077)), Vector((-0.054, HANDLE_Y + 0.001, 0.035))
    d = p1 - p0
    arm = bc.box("_barm", (0.0105, 0.0095, d.length + 0.008), loc=(0, 0, 0), smooth=None, mat=GM)
    arm.matrix_basis = Matrix.Translation((p0 + p1) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bake(arm)
    finish(arm, 0.0028, 1)
    # oversized chamfered HEX knob (BRIEF 4.1 option; review r2 minor 4) with a grip groove
    dn = d.normalized()
    kc = p1 + dn * 0.012
    R, KL, KC = KNOB_R, 0.0145, 0.0032     # circumradius, half length, end chamfer
    kprof = [(0, -0.024), (0.0050, -0.024), (0.0050, -KL), (R - KC, -KL), (R, -KL + KC), (R, -0.0030),
             (R - 0.0022, -0.0010), (R - 0.0022, 0.0010), (R, 0.0030), (R, KL - KC), (R - KC, KL), (0, KL)]
    knob = lathe_dir("_bknob", kprof, kc, dn, steps=6, mat=GM, angle=25)
    # cocking indicator: a short graphite stub in the centre of the flat shroud end
    ci = lathe_y("_bci", [(0, SH_Y1 + 0.005), (0.0034, SH_Y1 + 0.005), (0.0045, SH_Y1 + 0.0039),
                          (0.0045, SH_Y1 - 0.001), (0, SH_Y1 - 0.001)], steps=12, mat=G, angle=35)
    bolt = join([bolt, root, arm, knob, ci], "WARDEN_Bolt")
    set_origin(bolt, (0, SH_Y1, BZ))

    # merge small static detail bits into their host objects to keep the hierarchy clean
    screws = [o for o in parts if o.name.startswith("_scr")]
    gbits = [o for o in parts if o.name.startswith(("_gpad", "_gscr"))]
    others = [o for o in parts if not o.name.startswith(("_scr", "_gpad", "_gscr")) and o not in (hg, grip)]
    hg = join([hg] + screws, "WARDEN_Handguard")
    grip = join([grip] + gbits, "WARDEN_Grip")
    statics = others + [hg, grip]
    set_origin(trig, TRIG_PIVOT)
    return statics, trig, bolt


# ================================================================================================ STOCKS
STOCK_MOUNT = Vector((0, STOCK_Y, BZ))
SF = STOCK_Y - 0.0002   # stock front face: 0.2 mm inside the chassis rear face (no crack, no coplanar faces)
BEAM_TOP = CH_TOP_REAR  # stock top line = chassis top (concept 0.060-0.062), bolt channel continued to CHANNEL_END
CHANNEL_END = 0.093     # end of the bolt channel in the stock tops (open shroud + cocking stub reach y 0.090)
STOCK_BOT = 0.0105      # front-block underside (0.5 mm above the chassis underside: no coplanar sliver)
RISER_Z0, RISER_Z1 = 0.0725, 0.1025   # concept: riser pad floats ~18 mm over the beam on two posts
RISER_Y0 = 0.087        # riser pad nose: 2 mm behind the open shroud's rear face (0.085); underside chamfered
KX, KY = 0.030, 0.034   # folding-stock hinge axis (vertical, on the LEFT +X side)


def chamfered_window(obj, poly, half_w, depth):
    """Cut a through-window (side profile polygon, axis X) and a 45-degree chamfer `depth` deep on both faces."""
    cut(obj, prism("_win", poly, "X", -0.06, 0.06))
    # the 45-degree hull reaches only 1 mm past the outer face, so it cannot graze the face beside the window
    big = offset_poly(poly, depth + 0.001)
    for sx in (1, -1):
        pts = ([(sx * (half_w - depth), y, z) for (y, z) in poly] +
               [(sx * (half_w + 0.001), y, z) for (y, z) in big])
        cut(obj, hull("_wch", pts))
    return obj


def build_stock_standard(M, col):
    """Angular sand skeleton chassis stock (concept_main.png): long low top beam level with the chassis, a big
    chamfered window over a thick diagonal brace, rear upright, LOP spacer rods to a sand plate + thick rubber pad,
    a dark cheek riser floating on two posts and three lock pieces, and a monopod that retracts completely into the
    rear upright (only its knurled foot shows, flush in a pocket under the upright: the concept has no spike). The
    open bolt (lifted 60 deg, 0.13 m back) passes over the beam (1 mm clear) and stops 2 mm short of the riser."""
    G, GM, S, R = M["G"], M["GM"], M["S"], M["R"]
    bits = []
    # concept outline: the brace's underside runs down at ~42 deg, then a steeper step to the flat bottom
    outer = [(SF, BEAM_TOP), (0.243, BEAM_TOP), (0.2475, BEAM_TOP - 0.0045), (0.2475, -0.0755), (0.243, -0.080),
             (0.171, -0.080), (0.157, -0.046), (0.094, STOCK_BOT), (SF, STOCK_BOT)]
    st = prism("_frame", outer, "X", -0.020, 0.020, S)
    win = round_poly([(0.138, 0.034), (0.2195, 0.034), (0.2195, -0.041), (0.209, -0.050), (0.138, 0.021)], 0.007, 3)
    chamfered_window(st, win, 0.020, 0.004)
    cut(st, cyl("_bch", CHANNEL_R, CHANNEL_END - SF + 0.002, (0, (CHANNEL_END + SF - 0.002) / 2, BZ), "Y", 24))
    # sling slot through the front block
    cut(st, prism("_sls", stadium(0.047, 0.036, 0.026, 0.011, 3), "X", -0.05, 0.05))
    # pocket under the rear upright for the retracted monopod foot (flush: nothing below the stock line)
    cut(st, cyl("_mpk", 0.0098, 0.010, (0, MONO_Y, -0.080), "Z", 16))
    for sx in (1, -1):
        # joint seam between the front block and the frame
        cut(st, prism("_seam", band([(0.068, 0.006), (0.068, 0.058)], 0.0018), "X", sx * 0.0190, sx * 0.03))
        # small triangular lightening pockets in the top corners (concept)
        cut(st, prism("_tp", round_poly([(0.121, BEAM_TOP - 0.0095), (0.134, BEAM_TOP - 0.0095), (0.121, BEAM_TOP - 0.0205)], 0.0012, 1), "X",
                      sx * 0.0188, sx * 0.03))
        cut(st, prism("_tp", round_poly([(0.2255, BEAM_TOP - 0.0095), (0.2425, BEAM_TOP - 0.0095), (0.2425, BEAM_TOP - 0.0205)], 0.0012, 1), "X",
                      sx * 0.0188, sx * 0.03))
    finish(st, 0.0045, 1)       # one flat chamfer: the concept paints crisp chamfer bands (and -1k tris)
    bits.append(st)
    # riser posts: fixed collars on the beam top + central lock block with a knurled knob on +X
    for yp in RISER_POSTS:
        cl = cyl("_pcol", 0.0085, 0.0045, (0, yp, BEAM_TOP + 0.0012), "Z", 16, GM)
        finish(cl, 0.0010, 1)
        bits.append(cl)
    blk = box("_rlb", (0.020, 0.022, 0.0075), (0, 0.165, BEAM_TOP + 0.003), G)   # top 2.7 mm under the riser
    finish(blk, 0.0022, 1)
    bits.append(blk)
    kb = knurl_cyl("_rk", 0.0045, 0.007, (0.0135, 0.165, BEAM_TOP + 0.0035), "X", 14, 0.0007, GM)
    finish(kb, 0.0008, 1)
    bits.append(kb)
    # QD sling cups on the rear upright
    for sx in (1, -1):
        prof = [(0.0, -0.002), (0.0057, -0.002), (0.0065, -0.0012), (0.0065, 0.0012), (0.0057, 0.002),
                (0.0035, 0.002), (0.0035, 0.0), (0.0, 0.0)]
        bits.append(lathe_dir("_qd", prof, (sx * 0.0195, 0.2335, -0.058), (sx, 0, 0), steps=12, mat=GM, angle=40))
    # length-of-pull spacer rods, sand spacer plate and the thick rubber pad
    for zc in (0.038, -0.060):
        rod = cyl("_rod", 0.0055, 0.012, (0, 0.2515, zc), "Y", 12, GM)
        smooth(rod, 40)
        bits.append(rod)
    plate = prism("_plate", [(0.2555, 0.082), (0.2615, 0.090), (0.280, 0.090), (0.280, -0.086), (0.2615, -0.086),
                             (0.2555, -0.080)], "X", -0.022, 0.022, S)
    finish(plate, 0.0030, 2)
    bits.append(plate)
    pad = prism("_pad", [(0.2795, 0.090), (0.312, 0.090), (0.320, 0.082), (0.320, -0.078), (0.312, -0.086),
                         (0.2795, -0.086)], "X", -0.023, 0.023, R)
    for zc in (-0.060, -0.020, 0.020, 0.060):
        cut(pad, box("_pg", (0.06, 0.006, 0.0035), (0, 0.3205, zc)))
    for sx in (1, -1):
        cut(pad, box("_pgs", (0.003, 0.0022, 0.2), (sx * 0.023, 0.2915, 0.0)))
    finish(pad, 0.0035, 2)
    bits.append(pad)
    stock = join(bits, "WARDEN_StockStandard")
    set_origin(stock, STOCK_MOUNT)

    # cheek riser (child, slides up on its posts) -- dark pad like the concept, origin at the beam top centre
    z0, z1 = RISER_Z0, RISER_Z1
    # the nose reaches over the open shroud's rear face (0.085, top 0.086) with a steep underside chamfer, so the
    # pad starts 9 mm further forward than a flat-bottomed pad could (concept: pad front at y 0.076)
    cr = prism("WARDEN_StockStandard_CheekRiser", [(RISER_Y0, z1 - 0.003), (RISER_Y0 + 0.003, z1), (0.2435, z1),
                                                   (0.2475, z1 - 0.004), (0.2475, 0.089), (0.231, z0), (0.108, z0),
                                                   (RISER_Y0 + 0.0035, 0.093)], "X", -0.020, 0.020, G)
    finish(cr, 0.0040, 2)
    posts = []
    for yp in RISER_POSTS:
        p = cyl("_post", 0.0050, z0 + 0.003 - 0.038, (0, yp, (0.038 + z0 + 0.003) / 2), "Z", 12, GM)
        finish(p, 0.0007, 1)
        posts.append(p)
    cr = join([cr] + posts, "WARDEN_StockStandard_CheekRiser")
    set_origin(cr, (0, 0.165, BEAM_TOP))
    cr["slide_axis"] = "Z"
    cr["travel_min_m"] = 0.0
    cr["travel_max_m"] = 0.012

    # monopod (optional child, extends along -Z): retracted, the column hides inside the rear upright and only the
    # knurled foot shows, flush in its pocket (0.5 mm above the stock's underside). Origin = foot underside centre.
    col_ = cyl("_mcol", 0.0060, 0.120, (0, MONO_Y, -0.0775 + 0.060), "Z", 12, GM)
    smooth(col_, 40)
    knurl = knurl_cyl("_mknurl", 0.0090, 0.004, (0, MONO_Y, -0.0775), "Z", 16, 0.0007, GM)
    finish(knurl, 0.0008, 1)
    mono = join([col_, knurl], "WARDEN_StockStandard_Monopod")
    set_origin(mono, (0, MONO_Y, -0.0795))
    mono["slide_axis"] = "Z"
    mono["travel_min_m"] = -0.105     # extended: foot at z -0.185 (column still 15 mm inside the upright)
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


def build_stock_folding(M, col):
    """Lighter folding skeleton stock: graphite hinge block with two fixed knuckles on the LEFT (+X), a thinner
    sand frame with one big window and a front slot, a rubber pad straight on the upright, no riser, no monopod.
    Folds -180 deg about the vertical hinge axis so it lies along the LEFT side, clear of the bolt handle (-X)."""
    G, GM, S, R = M["G"], M["GM"], M["S"], M["R"]
    blk = prism("_hingeF", [(SF, BEAM_TOP), (0.044, BEAM_TOP), (0.044, STOCK_BOT), (SF, STOCK_BOT)], "X", -0.020,
                0.020, G)
    for sx in (1, -1):
        cut(blk, prism("_hbg", band([(0.018, 0.032), (0.048, 0.032)], 0.0022), "X", sx * 0.0190, sx * 0.03))
    cut(blk, cyl("_bch", CHANNEL_R, 0.050, (0, 0.040, BZ), "Y", 24))
    finish(blk, 0.0028, 2)
    bits = [blk]
    for (za, zb) in ((0.0115, 0.0245), (0.0395, 0.0525)):
        kn = cyl("_kn", 0.0085, zb - za, (KX, KY, (za + zb) / 2), "Z", 16, GM)
        finish(kn, 0.0012, 1)
        bits.append(kn)
        # knuckle web back to the block
        wb = prism("_kw", [(0.019, KY - 0.007), (KX, KY - 0.007), (KX, KY + 0.007), (0.019, KY + 0.007)], "Z", za, zb,
                   G)
        finish(wb, 0.0012, 1)
        bits.append(wb)
    fixed = join(bits, "WARDEN_StockFolding")
    set_origin(fixed, STOCK_MOUNT)
    # folding arm (child), origin on the hinge axis
    outer = [(0.046, BEAM_TOP - 0.0005), (0.243, BEAM_TOP - 0.0005), (0.2475, BEAM_TOP - 0.005), (0.2475, -0.072),
             (0.243, -0.0765), (0.190, -0.0765),
             (0.090, STOCK_BOT), (0.046, STOCK_BOT)]
    fr = prism("_ffr", outer, "X", -0.016, 0.016, S)
    winA = round_poly([(0.118, 0.045), (0.2275, 0.045), (0.2275, -0.062), (0.207, -0.062), (0.1185, 0.0335)], 0.006,
                      3)
    chamfered_window(fr, winA, 0.016, 0.0035)
    cut(fr, cyl("_bch", CHANNEL_R, CHANNEL_END - 0.040, (0, (CHANNEL_END + 0.040) / 2, BZ), "Y", 24))
    cut(fr, prism("_fwb", stadium(0.073, 0.032, 0.034, 0.012, 3), "X", -0.05, 0.05))
    finish(fr, 0.0040, 2)
    pad = prism("_fpad", [(0.2470, 0.078), (0.298, 0.078), (0.304, 0.072), (0.304, -0.076), (0.298, -0.082),
                          (0.2470, -0.082)], "X", -0.018, 0.018, R)
    for zc in (-0.055, -0.015, 0.025, 0.060):
        cut(pad, box("_pg", (0.06, 0.006, 0.0035), (0, 0.3045, zc)))
    finish(pad, 0.0035, 2)
    knA = cyl("_knA", 0.0085, 0.013, (KX, KY, 0.032), "Z", 16, GM)
    finish(knA, 0.0012, 1)
    leaf = prism("_leaf", [(0.0205, KY), (0.031, KY), (0.031, 0.054), (0.010, 0.054), (0.010, 0.0455),
                           (0.0205, 0.0455)], "Z", 0.0255, 0.0385, G)
    finish(leaf, 0.0012, 1)
    arm = join([fr, pad, knA, leaf], "WARDEN_StockFolding_Arm")
    set_origin(arm, (KX, KY, 0.032))
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
MAG_MOUNT = Vector((0, MAG_Y0, MAG_TOP_Z))
ROUND_TIP_Y = -0.2955     # bullet tip (gun coords); rim at -0.1575 (1 mm clear of both channel walls)
FEED_LIP_GAP = 0.016      # lip-to-lip gap at the top face (narrower than the 0.0207 case: the lips hold it)
STAGGER_X = 0.0060        # double-stack column offset (rounds 2.. alternate -X / +X); the top round is centred
PITCH_1, PITCH = 0.0198, 0.0170   # centred top round -> first staggered round; staggered pitch


def round_centres(cap):
    """(x, z) of every cartridge axis, round 1 = top (centred, 2.9 mm proud of the feed lips)."""
    c0 = MAG_TOP_Z - 0.0075
    out = [(0.0, c0)]
    for i in range(1, cap):
        out.append((-STAGGER_X if i % 2 else STAGGER_X, c0 - PITCH_1 - PITCH * (i - 1)))
    return out


def cartridge(name, tip_y, x, z, steps, M, simple=False):
    """12.7 mm-class cartridge lying along Y, bullet tip toward -Y at tip_y, axis at (x, z) (gun coords).
    Two materials: gunmetal bullet, light steel case (reads clearly at the feed lips and in the window).
    simple=True: reduced profile for the rounds that are only ever seen through the window slot."""
    prof = [(0, 0.0), (0.0022, 0.003), (0.0046, 0.012), (0.0062, 0.026), (0.0066, 0.039), (0.0076, 0.039),
            (0.0078, 0.056), (0.0099, 0.066), (0.0103, 0.128), (0.0090, 0.130), (0.0090, 0.1335),
            (0.0103, 0.1345), (0.0103, 0.138), (0, 0.138)]
    if simple:     # window-only rounds (review r2 budget): 9-point profile
        prof = [(0, 0.0), (0.0046, 0.011), (0.0066, 0.039), (0.0099, 0.062), (0.0103, 0.128), (0.0090, 0.131),
                (0.0103, 0.134), (0.0103, 0.138), (0, 0.138)]
    o = lathe_y(name, [(r, tip_y + s) for (r, s) in prof], x=x, z=z, steps=steps, mat=M["C"], angle=40)
    o.data.materials.append(M["GM"])
    for p in o.data.polygons:
        if p.center.y - tip_y < 0.0385:      # bullet ogive ahead of the case mouth
            p.material_index = 1
    return o


def build_mag(M, col, cap, front_bottom):
    """mag_5 (cap 5) or mag_8 (cap 8): a slim double-stack 12.7 mm box magazine (concept: small dark mag whose
    bottom follows the chassis' downward slope). The top round sits centred in real feed lips and stands 2.9 mm
    proud of them; the rest of the column is staggered +-6 mm and shows through a vertical window slot on each
    side (physical mag check, DIRECTION_LOG item 8). Origin = top-front of the mag (Mag socket)."""
    G, GM = M["G"], M["GM"]
    top = MAG_TOP_Z
    zf, zr = front_bottom, front_bottom - 0.012
    body = prism("_mbody", [(MAG_Y0, top), (MAG_Y1, top), (MAG_Y1, zr), (MAG_Y0 + 0.008, zf),
                            (MAG_Y0, zf + 0.008)], "X", -0.03, 0.03, G)
    # section: 7.5 mm chamfer on the top outer edges so the feed lips read as a narrower ridge
    intersect(body, prism("_msec", [(-0.012, top + 0.01), (0.012, top + 0.01), (0.012, top), (MAG_W, top - 0.0075),
                                    (MAG_W, zr - 0.02), (-MAG_W, zr - 0.02), (-MAG_W, top - 0.0075), (-0.012, top)],
                          "Y", MAG_Y0 - 0.01, MAG_Y1 + 0.01))
    y0, y1 = MAG_Y0 + 0.0025, MAG_Y1 - 0.0025    # internal channel (2.5 mm front / rear walls, 140 mm long)
    rc = round_centres(cap)
    fol_top = rc[-1][1] - 0.0104                 # follower top, full mag
    fol_z = fol_top - 0.0035                     # follower centre (7 mm thick: keeps the mag as shallow as the concept)
    ch_top, ch_bot = top - 0.008, fol_z - 0.005
    cut(body, box("_mch", (2 * MAG_CH, y1 - y0, ch_top - ch_bot), (0, (y0 + y1) / 2, (ch_top + ch_bot) / 2)))
    # feed lips: FEED_LIP_GAP wide at the top face, undercut at 45 degrees down to the channel
    g = FEED_LIP_GAP / 2
    cut(body, prism("_mfl", [(-g, top + 0.012), (g, top + 0.012), (g, top), (0.0108, top - 0.0045),
                             (0.0108, top - 0.0085), (-0.0108, top - 0.0085), (-0.0108, top - 0.0045), (-g, top)],
                    "Y", y0, y1))
    # window slot both sides; ends at the follower's bottom in its FULL position (review r2 minor 9: a full seated
    # mag shows rounds + follower and no daylight)
    # top at z 0.027: out of the gun the window shows round 2 too (mag check reads 2 left / 1 left); seated, the
    # part above the magwell lip (z ~0.005 here) stays hidden behind the magwell walls, so nothing shows through
    wz0, wz1 = 0.027, fol_z - 0.004
    cut(body, prism("_mw", stadium(MAG_WIN_Y, (wz0 + wz1) / 2, 0.019, wz0 - wz1, 4), "X", -0.04, 0.04))
    # rear catch notch (inside the magwell)
    cut(body, box("_mcn", (0.016, 0.006, 0.008), (0, MAG_Y1, 0.022)))
    finish(body, 0.0020, 1)
    # raised ribs flanking the window below the magwell (concept: vertical ribs)
    ribs = []
    for sx in (1, -1):
        for yc in (MAG_Y0 + 0.024, MAG_Y1 - 0.024):
            zb = zf + (zr - zf) * (yc - MAG_Y0) / (MAG_Y1 - MAG_Y0)
            h = -0.010 - (zb + 0.006)
            rb = box("_mrib", (0.0045, 0.008, h), (sx * (MAG_W + 0.0003), yc, -0.010 - h / 2), G)
            finish(rb, 0.0015, 1)
            ribs.append(rb)
    # base plate (graphite like the concept's all-dark mag), follows the sloped bottom
    base = prism("_mbase", [(MAG_Y0 - 0.0035, zf + 0.009), (MAG_Y0 + 0.004, zf + 0.002), (MAG_Y1 + 0.0035, zr + 0.002),
                            (MAG_Y1 + 0.0035, zr - 0.009), (MAG_Y0 - 0.0035, zf - 0.009)], "X", -0.0215, 0.0215, G)
    for sx in (1, -1):
        cut(base, prism("_mbg", band([(MAG_Y0 - 0.01, zf - 0.0035), (MAG_Y1 + 0.01, zr - 0.0035)], 0.0024), "X",
                        sx * 0.0205, sx * 0.04))
    finish(base, 0.0030, 1)
    mag = join([body] + ribs + [base], f"WARDEN_Mag{cap}")
    set_origin(mag, MAG_MOUNT)
    bc.link(mag, col)
    mag["part"] = f"mag_{cap}"
    mag["capacity"] = cap
    mag["socket"] = "WARDEN_SOCKET_Mag"
    # follower: separate child so the engine can push it up under the lowest remaining round
    fol = box(f"WARDEN_Mag{cap}_Follower", (2 * MAG_CH - 0.0006, y1 - y0 - 0.010, 0.007), (0, (y0 + y1) / 2, fol_z), G)
    cut(fol, prism("_mfr", [(y0 - 0.001, fol_z + 0.0045), (y0 + 0.016, fol_z + 0.0045), (y0 - 0.001, fol_z - 0.001)],
                   "X", -0.03, 0.03))       # nose ramp
    finish(fol, 0.0015, 1)
    set_origin(fol, (0, (y0 + y1) / 2, fol_z))
    # exact offsets (metres up along local +Z) for 0..cap rounds left; the top round needs 2.8 mm more than the
    # staggered pitch because it sits centred
    offs = []
    for n in range(cap + 1):
        if n == 0:
            offs.append(round((top - 0.0090) - fol_top, 5))          # empty: right under the feed lips
        else:
            offs.append(round(rc[n - 1][1] - rc[-1][1], 5))
    fol["slide_axis"] = "Z"
    fol["travel_per_round_m"] = PITCH
    fol["travel_max_m"] = offs[0]
    fol["offset_by_rounds_left_m"] = ",".join(f"{v:.5f}" for v in offs)   # index = rounds left (FBX-safe string)
    bc.link(fol, col)
    bc.parent_keep(fol, mag)
    for i, (xc, zc) in enumerate(rc):
        nm = f"WARDEN_Mag{cap}_Round" if i == 0 else f"WARDEN_Mag{cap}_Round_{i + 1:02d}"
        # the top round reads at the feed lips (16 sides); the rest are only seen through the window (8 sides)
        r = cartridge(nm, ROUND_TIP_Y, xc, zc, 16 if i == 0 else 8, M, simple=i > 0)
        set_origin(r, (xc, ROUND_TIP_Y + 0.069, zc))
        r["round_index"] = i + 1
        bc.link(r, col)
        bc.parent_keep(r, mag)
    return mag


# ================================================================================================ SOCKETS
SOCKETS = {
    "Optic": (0, OPTIC_Y, RAIL_TOP_Z),
    "Stock": (0, STOCK_Y, BZ),
    "Mag": (0, MAG_Y0, MAG_TOP_Z),
    "Under": (0, UNDER_Y, HG_BOT - 0.0095),
    "Side_R": (-(HG_W + 0.0095), SIDE_Y, SIDE_Z),   # shooter's RIGHT = -X (modular spec handedness)
    "Side_L": (HG_W + 0.0095, SIDE_Y, SIDE_Z),
    "Muzzle": (0, -1.100, BZ),
    "LeftHand": (0, -0.450, HG_BOT),
}


def build_all():
    bc.reset_scene()
    BOOL_LOG.clear()
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
    m5 = build_mag(M, c_m5, 5, -0.0545)     # base plate bottom z -0.0635 (front) .. -0.0755 (rear), like the concept
    m8 = build_mag(M, c_m8, 8, -0.1055)

    for o in sorted(bpy.data.objects, key=lambda o: o.name):
        if o.type == "MESH" and not o.name.startswith("_"):
            seal(o)
            clean_slots(o)
            tri_clean(o)
            world_uvs(o)
    for b in BOOL_LOG:
        log("  BOOLEAN NO-OP (cutter overlaps the bounds but changed nothing):", b)
    # opening checks on the FINAL meshes (after seal / tri_clean)
    slot_check(bpy.data.objects["WARDEN_Handguard"])
    magwell_check(bpy.data.objects["WARDEN_Chassis"])
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
            "follower_offset_by_rounds_left_m": [float(v) for v in fol["offset_by_rounds_left_m"].split(",")],
            "follower_rule": "raise the follower along local +Z by follower_offset_by_rounds_left_m[rounds_left] "
                             "(index 0 = empty: right under the feed lips). The step under the centred top round is "
                             "larger than travel_per_round_m, so use the table rather than n * travel_per_round_m",
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
    os.makedirs(WIP, exist_ok=True)
    with open(os.path.join(WIP, "tris.json"), "w") as f:
        json.dump(rows, f, indent=2)
    return rows


def signature():
    """Per-mesh fingerprint (tris, verts, sum |coords|) -- two builds must produce identical values."""
    sig = {}
    for o in sorted(bpy.data.objects, key=lambda o: o.name):
        if o.type != "MESH" or o.name.startswith("_"):
            continue
        co = [0.0] * (len(o.data.vertices) * 3)
        o.data.vertices.foreach_get("co", co)
        sig[o.name] = [tris(o), len(o.data.vertices), round(sum(abs(c) for c in co), 6)]
    return sig


def gate_all():
    """Pre-export mesh gate on every exported mesh (review r2): 0 boundary, 0 non-manifold, 0 zero-area triangles
    after a 1e-6 positional weld, and triangles only. Fails the build (no export) unless --no-gate."""
    res, bad = {}, {}
    for o in sorted(bpy.data.objects, key=lambda o: o.name):
        if o.type != "MESH" or o.name.startswith("_"):
            continue
        r = mesh_gate(o)
        res[o.name] = r
        if r["boundary"] or r["nonmanifold"] or r["zero_area"] or r["ngons"]:
            bad[o.name] = r
    os.makedirs(WIP, exist_ok=True)
    with open(os.path.join(WIP, "gate_blend.json"), "w") as f:
        json.dump(res, f, indent=1)
    tiny = sum(r["tiny_lt_0_01mm2"] for r in res.values())
    log(f"mesh gate: {len(res)} meshes, {len(bad)} failing, {tiny} faces < 0.01 mm^2 (not zero-area)")
    for k, v in bad.items():
        log("  GATE FAIL", k, v)
    if bad and not ARGS.no_gate:
        raise SystemExit("[warden] MESH GATE FAILED -- nothing exported")
    return res


EXPORTED_GLB = ["warden_base.glb", "warden_default.glb"] + [fn + ".glb" for fn in
                                                            ("WARDEN_stock_standard", "WARDEN_stock_folding",
                                                             "WARDEN_mag_5", "WARDEN_mag_8")]


def reimport_gate():
    """Export gate (review r2): re-import every exported glb into an empty file, weld each mesh by position at
    1e-6 m in world space and require 0 boundary edges, 0 non-manifold edges and 0 zero-area triangles. Writes
    _wip/gate_glb.json. Resets the Blender session, so it runs last."""
    out, fails = {}, []
    for fn in EXPORTED_GLB:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.join(OUT, fn))
        for o in sorted([o for o in bpy.data.objects if o.type == "MESH"], key=lambda o: o.name):
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bm.transform(o.matrix_world)
            bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
            r = dict(tris=sum(len(f.verts) - 2 for f in bm.faces),
                     boundary=sum(1 for e in bm.edges if e.is_boundary),
                     nonmanifold=sum(1 for e in bm.edges if not e.is_manifold),
                     zero_area=sum(1 for f in bm.faces if f.calc_area() < 1e-10),
                     materials=[m.name if m else None for m in o.data.materials])
            bm.free()
            out[f"{fn}:{o.name}"] = r
            if r["boundary"] or r["nonmanifold"] or r["zero_area"] or None in r["materials"]:
                fails.append((fn, o.name, r))
    with open(os.path.join(WIP, "gate_glb.json"), "w") as f:
        json.dump(out, f, indent=1)
    log(f"re-import gate: {len(out)} meshes in {len(EXPORTED_GLB)} glb files, {len(fails)} failing")
    for f_ in fails:
        log("  GLB GATE FAIL", f_)
    return not fails


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
              focus=((0, -0.39, -0.03), 0.20))
    for o in added:
        bpy.data.objects.remove(o, do_unlink=True)
    return out


def bright_bg(on=True):
    """Swap the camera-ray background to a bright snow/sky value (The Yard range is a snowy fjord): see-through
    holes then show as white pills. Used for the review-r2 'no light strips' check renders."""
    nt = bpy.context.scene.world.node_tree
    cam_bg = [n for n in nt.nodes if n.type == "BACKGROUND"][-1]
    if not hasattr(bright_bg, "keep"):
        bright_bg.keep = tuple(cam_bg.inputs[0].default_value)
    cam_bg.inputs[0].default_value = (6.0, 6.2, 6.6, 1) if on else bright_bg.keep


def do_renders(B, mode):
    render_world()
    for p, sk in ((B["ss"], "Stock"), (B["sf"], "Stock"), (B["m5"], "Mag"), (B["m8"], "Mag")):
        if p.parent is None:
            p.matrix_world = Matrix.Translation(Vector(SOCKETS[sk]))
    bpy.context.view_layer.update()
    base = base_objs(B)
    default = base + tree(B["ss"]) + tree(B["m5"])
    out = []
    smp = None if mode != "quick" else 24
    if mode in ("quick", "full", "compare"):
        out += rv("warden", default, ("right", "left"), samples=smp, margin=1.04)
        out += rv("warden", default, ("three_quarter",), samples=smp, margin=0.86, focus=((0, -0.40, 0.0), 0.70))
        out += [exact_side(default, "warden_exact_side.png")]
    if mode == "full":
        out += rv("warden", default, (TOP,), res=(1600, 640), rename=["top"], margin=1.02)
        out += rv("warden", default, ("front", "back"), res=(900, 900), focus=((0, -0.39, 0.0), 0.16),
                  ortho=True, margin=1.0)
        out += rv("warden", default, ("three_quarter_back",), margin=0.86, focus=((0, -0.38, 0.0), 0.74))
        out += rv("warden", default, ("low",), margin=0.86, focus=((0, -0.40, 0.0), 0.70))
        # roughly what the player sees: from behind/above the right shoulder, down the rail
        out += rv("warden", default, ((-0.22, 1.0, 0.40),), res=(1600, 900), lens=40, margin=0.80,
                  focus=((0, -0.36, 0.05), 0.55), rename=["fpv"])
        # close-ups
        out += rv("warden_cu", default, ((0.9, -0.8, 0.45),), res=(1200, 900), focus=((0, -1.046, BZ), 0.075),
                  rename=["brake"])
        out += rv("warden_cu", default, ((-1.0, 0.55, 0.45),), res=(1200, 900),
                  focus=((-0.03, -0.075, 0.055), 0.10), rename=["bolt"])
        # bolt cycle: lifted in place (the root turns behind the receiver, in free air), then fully open (0.13 m
        # back) -- the shroud stops 11 mm short of the cheek riser
        bolt = B["bolt"]
        loc0, rot0 = bolt.location.copy(), bolt.rotation_euler.copy()
        bolt.rotation_euler[1] = math.radians(bolt["lift_deg"])
        bpy.context.view_layer.update()
        out += rv("warden_cu", default, ((-0.6, 1.0, 0.55),), res=(1200, 900),
                  focus=((-0.02, -0.07, 0.075), 0.10), rename=["bolt_lifted"])
        bolt.location.y += bolt["travel_m"]
        bpy.context.view_layer.update()
        out += rv("warden_cu", default, ((-1.0, 0.55, 0.45),), res=(1200, 900),
                  focus=((-0.02, 0.0, 0.065), 0.16), rename=["bolt_open"])
        out += rv("warden_bolt_open", default, ("left",), res=(1400, 900), focus=((0, -0.02, 0.05), 0.19))
        out += rv("warden_bolt_open", default, ("right",), res=(1400, 900), focus=((0, -0.12, 0.06), 0.19))
        out += rv("warden_bolt_open", default, ((-0.22, 1.0, 0.40),), res=(1400, 900), lens=40, margin=0.8,
                  focus=((0, -0.06, 0.08), 0.30), rename=["fpv"])
        alt0 = base + tree(B["sf"]) + tree(B["m8"])
        out += rv("warden_bolt_open", alt0, ((-1.0, 0.55, 0.45),), res=(1200, 900),
                  focus=((-0.02, 0.0, 0.05), 0.17), rename=["folding_stock"])
        bolt.location, bolt.rotation_euler = loc0, rot0
        bpy.context.view_layer.update()
        out += rv("warden_cu", default, ((-1.0, -0.25, 0.25),), res=(1400, 900), focus=((0, -0.20, 0.05), 0.17),
                  rename=["receiver_right"])
        out += rv("warden_cu", default, ((1.0, -0.35, 0.3),), res=(1400, 900), focus=((0, -0.20, 0.05), 0.17),
                  rename=["receiver_left"])
        out += rv("warden_cu", default, ((0.8, -0.6, -0.35),), res=(1400, 900), focus=((0, -0.52, 0.06), 0.19),
                  rename=["handguard_under"])
        out += rv("warden_cu", default, ((0.9, -0.35, 0.25),), res=(1400, 900), focus=((0, -0.50, 0.07), 0.15),
                  rename=["handguard_left"])
        out += rv("warden_cu", default, ((0.75, -0.55, -0.45),), res=(1400, 900),
                  focus=((0, -0.23, -0.01), 0.12), rename=["magwell"])
        out += rv("warden_cu", default, ((0.9, 0.3, 0.35),), res=(1400, 900), focus=((0, 0.17, 0.02), 0.16),
                  rename=["stock_left"])
        # underside: monopod foot flush in its pocket (retracted), then extended
        out += rv("warden_cu", default, ((0.5, 0.45, -1.0),), res=(1400, 900), focus=((0, 0.20, -0.07), 0.10),
                  rename=["stock_under"])
        mono = next(o for o in B["ss"].children if o.name.endswith("Monopod"))
        mono.location.z += mono["travel_min_m"]
        bpy.context.view_layer.update()
        out += rv("warden_cu", default, ("left",), res=(1400, 900), focus=((0, 0.20, -0.09), 0.17),
                  rename=["monopod_extended"])
        mono.location.z -= mono["travel_min_m"]
        bpy.context.view_layer.update()
        # review r2 major 2 check: side views against a bright snow background -- the slots must stay dark
        bright_bg(True)
        out += rv("warden_check_brightbg", default, ("right", "left"), res=(1600, 800), margin=1.04)
        out += rv("warden_check_brightbg", default, ("right",), res=(1400, 800), focus=((0, -0.48, 0.07), 0.16),
                  rename=["handguard_right"])
        bright_bg(False)
        # variants: stocks + mags alone
        for key, nm in (("ss", "stock_standard"), ("sf", "stock_folding")):
            objs = tree(B[key])
            out += rv(f"warden_{nm}", objs, ("three_quarter", "right", "left", "three_quarter_back"),
                      res=(1200, 900), margin=1.25)
        for key, nm in (("m5", "mag_5"), ("m8", "mag_8")):
            objs = tree(B[key])
            out += rv(f"warden_{nm}", objs, ("three_quarter", "right", (0.6, -0.5, 1.0)), res=(900, 1000),
                      margin=1.25, rename=["three_quarter", "right", "top_feedlips"])
        # mag check with 2 rounds left (rounds 3..5 hidden, follower raised by its table value): the follower sits
        # right under the remaining rounds; empty: the follower right under the feed lips
        m5 = B["m5"]
        fol = next(o for o in m5.children if o.name.endswith("Follower"))
        offs = [float(v) for v in fol["offset_by_rounds_left_m"].split(",")]
        rounds = sorted([o for o in m5.children if "_Round" in o.name], key=lambda o: o["round_index"])
        fz = fol.location.z
        fol.location.z = fz + offs[2]
        bpy.context.view_layer.update()
        out += rv("warden_mag_5_check", [m5, fol] + rounds[:2], ("right", (0.6, -0.5, 0.25)), res=(900, 1000),
                  margin=1.25, rename=["two_left", "two_left_three_quarter"])
        fol.location.z = fz + offs[0]
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
        out += rv("warden_alt", alt, ("right", "three_quarter"), margin=1.04)
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
def main():
    global B
    B = build_all()
    log("built")
    if not ARGS.no_det_check:
        # review r2 (minor 5): build a second time from scratch and require identical meshes before anything is exported
        sig1 = signature()
        B = build_all()
        sig2 = signature()
        def same(a, b):     # identical topology; coordinates equal to float noise (sum |co| within 1e-5 m)
            return a is not None and b is not None and a[:2] == b[:2] and abs(a[2] - b[2]) < 1e-5
        diff = {k: (sig1.get(k), sig2.get(k)) for k in sorted(set(sig1) | set(sig2)) if not same(sig1.get(k),
                                                                                                  sig2.get(k))}
        if diff:
            for k, v in diff.items():
                log("  DETERMINISM DIFF", k, v)
            raise SystemExit("[warden] DETERMINISM CHECK FAILED -- nothing exported")
        log(f"determinism check: two builds identical ({len(sig2)} meshes)")
    os.makedirs(WIP, exist_ok=True)
    with open(os.path.join(WIP, "signature.json"), "w") as f:
        json.dump(signature(), f, indent=1)
    rows = report(B)
    gate_all()
    if not ARGS.no_export:
        do_exports(B)
    if ARGS.render != "none":
        do_renders(B, ARGS.render)
    if not ARGS.no_export:
        ok = reimport_gate()
        if not ok and not ARGS.no_gate:
            raise SystemExit("[warden] RE-IMPORT GATE FAILED")
    log("done")



if __name__ in ("__main__", "warden_build"):     # runpy(..., run_name="warden_defs") = definitions only
    main()
