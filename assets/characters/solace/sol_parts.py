"""Stage C for build_solace.py: procedural parts on the finished TRELLIS body.

  SOL_Bloom           the regen module (rigid, parented to spine_03 later): graphite mount plate conformed to the
                      coat back, 7 spine vertebrae, yoke arms + shoulder clamps with two coral status LEDs, hub with a
                      glowing ring, and the glowing core spindle (seen only through the vane seams)
  SOL_Bloom_Vane_C/L/R  three ivory petal shells with coral rims that close into a teardrop bud: sectors of the
                      elliptic bud surface (brief bud_r table, Y depth 0.62) with two narrow back seams where the
                      glowing core shows; L/R flare outward over their upper part so the tips rise above both
                      shoulders in the front view. Each has its origin on its hinge, local +X = hinge axis, positive
                      rotation about local X opens it (custom props: open_angle_deg, closed_angle_deg,
                      hinge_axis_local)
  SOL_Gear            skinned extras: harness straps from the yoke clamps over the shoulders to the TRELLIS chest
                      straps, and the "Bloom" emblem (sand hex patch + three coral petals) on her LEFT upper arm

Brief coordinates (art/concepts/solace/BRIEF.md 4i) are used with a Y offset measured from the rebuilt coat back.
Materials are flat colours (no texture multiplies, so glTF and Blender look the same).
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

import blender_common as bc
from sol_lib import log, body, img_to_np, face_tex_colors

# ---------------------------------------------------------------------------------------------- materials
LIN = dict(
    graphite=(0.030, 0.033, 0.040), gunmetal=(0.11, 0.115, 0.12), ivory=(0.70, 0.67, 0.60),
    sand=(0.36, 0.28, 0.18), charcoal=(0.035, 0.037, 0.045), coral=(1.0, 0.36, 0.30))


def materials():
    mats = dict(
        ivory_hard=bc.material("M_SOL_IvoryHard", LIN["ivory"], rough=0.42),
        graphite=bc.material("M_SOL_Graphite", LIN["graphite"], rough=0.55),
        gunmetal=bc.material("M_SOL_Gunmetal", LIN["gunmetal"], rough=0.35, metal=0.85),
        charcoal=bc.material("M_SOL_Charcoal", LIN["charcoal"], rough=0.72),
        sand=bc.material("M_SOL_Sand", LIN["sand"], rough=0.78),
        # deeper than the palette coral (which renders as pale pink on ivory): matches the coat piping
        coral=bc.material("M_SOL_Coral", (0.80, 0.16, 0.10), rough=0.60),
        glow=bc.material("M_SOL_Glow", LIN["coral"], rough=0.40, emission=LIN["coral"], emission_strength=4.0),
    )
    for m in mats.values():
        m.use_backface_culling = True      # closed meshes -> single-sided in glTF
    return mats


# ---------------------------------------------------------------------------------------------- helpers
class Surf:
    """Ray/nearest queries on the body surface (optionally without hair faces)."""

    def __init__(self, obj, no_hair=False):
        if not no_hair:
            dg = bpy.context.evaluated_depsgraph_get()
            self.bvh = BVHTree.FromObject(obj, dg)
            return
        from sol_lib import hair_like
        me = obj.data
        px = img_to_np(bpy.data.images["SOL_BaseColor"])
        fc = face_tex_colors(me, px)
        keep = ~hair_like(fc)
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        polys = [tuple(p.vertices) for p, k in zip(me.polygons, keep) if k]
        self.bvh = BVHTree.FromPolygons([tuple(c) for c in co], polys)

    def back_y(self, x, z, y0=0.6):
        hit = self.bvh.ray_cast(Vector((x, y0, z)), Vector((0, -1, 0)), 1.0)
        return hit[0].y if hit[0] else None

    def down_z(self, x, y, z0=1.62):
        hit = self.bvh.ray_cast(Vector((x, y, z0)), Vector((0, 0, -1)), 1.0)
        return hit[0].z if hit[0] else None

    def nearest(self, p):
        loc, nrm, idx, d = self.bvh.find_nearest(Vector(p))
        return loc, nrm, d

    def push_out(self, p, clear):
        """Move p along the surface normal so it is at least `clear` outside the surface."""
        p = Vector(p)
        for _ in range(4):
            loc, nrm, d = self.nearest(p)
            if loc is None:
                break
            side = (p - loc).dot(nrm)
            if side >= clear - 1e-5:
                break
            p = loc + nrm * clear
        return p


def mesh_obj(name, verts, faces, mat_idx=None, mats=(), smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    for m in mats:
        me.materials.append(m)
    if mat_idx is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_idx, np.int32))
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return obj


def catmull(pts, n):
    """Centripetal-ish Catmull-Rom resample of a polyline to n points (ends kept)."""
    P = np.asarray(pts, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    seg = len(P) - 3
    out = []
    for i in range(n):
        t = i / (n - 1) * seg
        k = min(int(t), seg - 1)
        u = t - k
        p0, p1, p2, p3 = P[k], P[k + 1], P[k + 2], P[k + 3]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3))
    return np.array(out)


def sweep(name, path, width, thick, up_fn, mats, mat=0, n=24, closed=False, cap=True):
    """Rectangular-section sweep along a polyline (width along up_fn(p) x tangent, thickness along up)."""
    P = catmull(path, n)
    verts, faces = [], []
    for i, p in enumerate(P):
        t = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        t /= np.linalg.norm(t)
        up = np.asarray(up_fn(p), float)
        up = up - t * up.dot(t)
        up /= np.linalg.norm(up)
        side = np.cross(t, up)
        for (a, b) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            verts.append(p + side * a * width / 2 + up * b * thick / 2)
    for i in range(n - 1):
        for k in range(4):
            a, b = i * 4 + k, i * 4 + (k + 1) % 4
            faces.append((a, b, b + 4, a + 4))
    if cap:
        faces.append((3, 2, 1, 0))
        o = (n - 1) * 4
        faces.append((o, o + 1, o + 2, o + 3))
    obj = mesh_obj(name, verts, faces, mats=[mats[mat]] if not isinstance(mat, (list, tuple)) else mats)
    bc.shade_smooth(obj, 40)
    return obj


# ---------------------------------------------------------------------------------------------- vanes
BUD_R = [(1.150, 0.018), (1.190, 0.050), (1.250, 0.075), (1.320, 0.082), (1.400, 0.072), (1.470, 0.050),
         (1.530, 0.025), (1.565, 0.000)]
# vane hinge pivots (brief 4l, SOL_PIVOT_Vane_*); R mirrors L
VANE_C = dict(pivot=(0, 0.172, 1.150))
VANE_L = dict(pivot=(0.015, 0.167, 1.150))


def bud_r(z):
    """Bud radius table (brief 4i), smooth (monotone cubic through the keys)."""
    zs = np.array([k[0] for k in BUD_R])
    rs = np.array([k[1] for k in BUD_R])
    z = float(np.clip(z, zs[0], zs[-1]))
    i = int(np.clip(np.searchsorted(zs, z) - 1, 0, len(zs) - 2))
    t = (z - zs[i]) / (zs[i + 1] - zs[i])
    # finite-difference slopes, Fritsch-Carlson limited
    d = np.diff(rs) / np.diff(zs)
    m = np.r_[d[0], (d[:-1] + d[1:]) / 2, d[-1]]
    for k in range(len(d)):
        if d[k] == 0:
            m[k] = m[k + 1] = 0
    h = zs[i + 1] - zs[i]
    t2, t3 = t * t, t * t * t
    return float((2 * t3 - 3 * t2 + 1) * rs[i] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * rs[i + 1]
                 + (t3 - t2) * h * m[i + 1])


# Bud vanes as sectors of the elliptic bud (X radius bud_r(z), Y depth 0.62 x): angle th is measured in the XY
# plane from +X toward +Y (the back). C covers the back, L/R the sides; two narrow back seams (where the glowing
# core shows) and a hidden front gap where the spine enters. Each vane puffs out a little between its edges, so
# the seams sit in shallow valleys like a real flower bud.
BUD_Z0, BUD_ZT = 1.150, 1.565
BUD_VANES = dict(
    C=dict(th=(58.5, 121.5), puff=0.10, ztip=1.555, tip=None),
    L=dict(th=(-66.0, 48.5), puff=0.07, ztip=1.540, tip=(0.142, 0.150), curl0=1.28, keep=1.35),
    R=dict(th=(131.5, 246.0), puff=0.07, ztip=1.540, tip=(-0.142, 0.150), curl0=1.28, keep=1.35),
)
# Review round 2: the upper bud bends back (a smooth Y shear that starts at Z 1.33 and reaches BUD_BEND_DY at the C
# tip), so the back of the hair clears vane C when she looks up 45 deg (aiming at roofs / ziplines). The lower bud,
# the hinges and the front-view L/R tips stay where they were (a rigid lean opened a gap to her back in side view).
BUD_BEND_Z0, BUD_BEND_Z1, BUD_BEND_DY = 1.33, 1.555, 0.045
CORE_TOP = 1.425         # the glowing core spindle ends here (the seams that show it run Z 1.20-1.42)
# coral edge band on the OUTER face of every vane along both side edges (fraction of the vane span): with the 6 mm
# coral rim this gives the bold coral seams of concept v04 instead of a thin pink line (ivory-on-ivory from behind)
EDGE_BAND = dict(C=0.115, L=0.075, R=0.075)
OPEN_DEG = dict(C=30.0, L=21.0, R=21.0)     # L/R open 21 deg (32 read as wings, X +-0.32 m)


def bud_bend_dy(z):
    t = np.clip((np.asarray(z, float) - BUD_BEND_Z0) / (BUD_BEND_Z1 - BUD_BEND_Z0), 0.0, None)
    return BUD_BEND_DY * t * t


def bend_mesh(obj):
    """Apply the upper-bud back bend to a mesh whose vertices are in world coordinates (object at identity)."""
    me = obj.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    co[:, 1] += bud_bend_dy(co[:, 2])
    me.vertices.foreach_set("co", co.ravel())
    me.update()


def bud_axis_y(z):
    return 0.178 + (0.190 - 0.178) * (z - BUD_Z0) / (BUD_ZT - BUD_Z0)


def bud_vane(name, key, mats, dy, rings=24, cols=15, thick=0.006):
    """One vane of the bud: outer surface sampled on (height u, span v), tip collapsed to a point, solidified toward
    the core with a coral rim (material_offset_rim). L/R curl outward over the upper part so their tips rise above
    the shoulders (front view), C closes the back."""
    V = BUD_VANES[key]
    th0, th1 = (math.radians(a) for a in V["th"])
    bf = EDGE_BAND.get(key, 0.0)
    vs = sorted(set(np.round(np.r_[np.linspace(0, 1, cols), [bf, 1 - bf] if bf else []], 6)))
    cols = len(vs)
    verts, faces = [], []
    for i in range(rings):
        u = i / (rings - 1)
        u = 1 - (1 - u) ** 1.15                         # a little denser toward the tip
        z = BUD_Z0 + (V["ztip"] - BUD_Z0) * u
        # radius profile remapped so the vane closes at its tip; L/R keep their width longer (broad petal tips)
        zr = BUD_Z0 + (BUD_ZT - BUD_Z0) * blend_keep(u, V.get("keep", 1.0))
        a = bud_r(zr)
        b = 0.62 * a
        yc = bud_axis_y(zr) + dy
        off = np.zeros(2)
        if V["tip"] is not None:
            w = min(max((z - V["curl0"]) / (V["ztip"] - V["curl0"]), 0.0), 1.0) ** 2.2
            axis_top = np.array([0.0, bud_axis_y(BUD_ZT) + dy])
            off = w * (np.array([V["tip"][0], V["tip"][1] + dy]) - axis_top)
        for j in range(cols):
            v = vs[j]
            th = th0 + (th1 - th0) * v
            k = 1 + V["puff"] * math.sin(math.pi * v) ** 0.8
            verts.append((a * k * math.cos(th) + off[0], yc + b * k * math.sin(th) + off[1], z))
    mi = []
    for i in range(rings - 1):
        for j in range(cols - 1):
            a_ = i * cols + j
            faces.append((a_, a_ + cols, a_ + cols + 1, a_ + 1))       # outward (counter-clockwise from outside)
            vc = 0.5 * (vs[j] + vs[j + 1])
            mi.append(1 if bf and (vc < bf or vc > 1 - bf) else 0)
    obj = mesh_obj(name, verts, faces, mat_idx=mi, mats=[mats["ivory_hard"], mats["coral"]])
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=2e-5)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-6)
    # make normals point away from the bud axis
    bm.faces.ensure_lookup_table()
    mid = bm.faces[len(bm.faces) // 2]
    c = mid.calc_center_median()
    ax = Vector((0, bud_axis_y(c.z) + dy, c.z))
    if mid.normal.dot(c - ax) < 0:
        for f in bm.faces:
            f.normal_flip()
    bm.to_mesh(obj.data)
    bm.free()
    so = obj.modifiers.new("Solidify", "SOLIDIFY")
    so.thickness = thick
    so.offset = -1.0
    so.use_rim = True
    so.material_offset_rim = 1
    so.use_even_offset = True
    bc.apply_modifiers(obj)
    me = obj.data
    mi = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", mi)
    me.polygons.foreach_set("material_index", np.minimum(mi, 1))      # rim next to a coral band face -> coral
    bv = obj.modifiers.new("Bevel", "BEVEL")
    bv.width = 0.0010
    bv.segments = 1
    bv.limit_method = "ANGLE"
    bv.angle_limit = math.radians(50)
    bc.apply_modifiers(obj)
    drop_degenerate(obj)
    bc.shade_smooth(obj, 50)
    return obj


def drop_degenerate(obj, area=1e-8):
    """Collapse zero-area faces (the collapsed vane tips leave a few after solidify + bevel)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    # weld coincident verts (the solidified shell meets itself at the collapsed tips), then triangulate here
    # (beauty), so the exporter's own triangulation cannot create zero-area slivers at the tips
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="BEAUTY")
    for _ in range(3):
        bad = [f for f in bm.faces if f.calc_area() < area]
        if not bad:
            break
        bmesh.ops.dissolve_degenerate(bm, edges=list({e for f in bad for e in f.edges}), dist=2e-5)
        bad = [f for f in bm.faces if f.calc_area() < area]
        if bad:
            bmesh.ops.delete(bm, geom=bad, context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    n = sum(1 for f in bm.faces if f.calc_area() < area)
    bm.to_mesh(obj.data)
    bm.free()
    if n:
        log(f"  {obj.name}: {n} degenerate faces left")


def blend_keep(u, p):
    """Height remap for the radius profile: p > 1 keeps the petal wide longer and closes it late (only above the
    bud's widest ring, so the lower bud stays identical for all vanes)."""
    um = (1.320 - BUD_Z0) / (BUD_ZT - BUD_Z0)
    if p == 1.0 or u <= um:
        return u
    t = (u - um) / (1 - um)
    return um + (1 - um) * t ** p


def smooth01(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def set_local_frame(obj, origin, xaxis, zaxis=(0, 0, 1)):
    """Give obj a rest transform with origin at `origin` and local X = xaxis (hinge), keeping the mesh in place."""
    X = Vector(xaxis).normalized()
    Z = Vector(zaxis)
    Z = (Z - X * Z.dot(X)).normalized()
    Y = Z.cross(X).normalized()
    R = Matrix((X, Y, Z)).transposed()
    M = Matrix.Translation(Vector(origin)) @ R.to_4x4()
    obj.data.transform(M.inverted())
    obj.matrix_world = M


# ---------------------------------------------------------------------------------------------- the module
def build_bloom(mats):
    S = Surf(body())
    yb = S.back_y(0.0, 1.25)
    dy = yb - 0.0915
    log(f"bloom: coat back at x=0 z=1.25 -> y {yb:.4f}; brief Y offset {dy:+.4f}")
    parts = []
    # ---- mount plate conformed to the back (+0.003), 0.012 thick, rounded rectangle 0.085 x 0.340
    W, H, r = 0.085, 0.315, 0.020          # top at Z 1.395 (brief 1.420): clear of the collar when she looks up
    zc = 1.2375
    nx, nz = 9, 25
    verts = []
    grid = []
    for j in range(nz):
        row = []
        for i in range(nx):
            u = -W / 2 + W * i / (nx - 1)
            v = -H / 2 + H * j / (nz - 1)
            # round the corners: pull the corner verts onto a radius
            cu, cv = max(abs(u) - (W / 2 - r), 0), max(abs(v) - (H / 2 - r), 0)
            if cu > 0 and cv > 0:
                k = r / math.hypot(cu, cv) if math.hypot(cu, cv) > r else 1.0
                u = math.copysign(W / 2 - r + cu * k, u)
                v = math.copysign(H / 2 - r + cv * k, v)
            y = S.back_y(u, zc + v)
            row.append((u, (y if y is not None else yb) + 0.003, zc + v))
        grid.append(row)
    front = np.array(grid).reshape(-1, 3)
    back = front + np.array([0, 0.012, 0])
    verts = list(front) + list(back)
    faces = []
    nf = nx * nz
    for j in range(nz - 1):
        for i in range(nx - 1):
            a = j * nx + i
            faces.append((a, a + nx, a + nx + 1, a + 1))
            faces.append((nf + a, nf + a + 1, nf + a + nx + 1, nf + a + nx))
    ring = [(0, i) for i in range(nx)] + [(j, nx - 1) for j in range(1, nz)] + \
           [(nz - 1, i) for i in range(nx - 2, -1, -1)] + [(j, 0) for j in range(nz - 2, 0, -1)]
    for k in range(len(ring)):
        j0, i0 = ring[k]
        j1, i1 = ring[(k + 1) % len(ring)]
        a, b = j0 * nx + i0, j1 * nx + i1
        faces.append((a, b, nf + b, nf + a))
    mount = mesh_obj("_mount", verts, faces, mats=[mats["graphite"]])
    bm = bmesh.new()
    bm.from_mesh(mount.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mount.data)
    bm.free()
    bc.add_bevel(mount, 0.003, 2, angle=50)
    bc.shade_smooth(mount, 40)
    parts.append(mount)
    mount_back = float(np.median(back[:, 1]))
    # ---- spine vertebrae (7), on the mount
    ys = mount_back + 0.011
    for i in range(7):
        z = 1.090 + 0.048 * i                # top vertebra ends at Z 1.394 (round 2: collar clearance)
        yl = S.back_y(0, z)
        yv = max(ys, (yl or yb) + 0.015 + 0.011)
        v = bc.box(f"_vert{i}", (0.040, 0.022, 0.032), loc=(0, yv, z), mat=mats["graphite"], bevel=0.006,
                   segments=2)
        parts.append(v)
    # ---- yoke arms + clamps + LEDs
    for sx in (1, -1):
        zs = S.down_z(sx * 0.108, 0.080 + dy * 0.5) or 1.40
        clamp = Vector((sx * 0.108, 0.080 + dy * 0.5, zs + 0.010))
        clamp = S.push_out(clamp, 0.014)
        # seat the tilted clamp ON the shoulder: lift it until every point of its underside clears the coat (and
        # the hair resting there) by 2 mm; the centre push-out alone left its corners in the right shoulder
        Rc = Matrix.Rotation(math.radians(-25), 3, "X")
        lift = 0.0
        for u in np.linspace(-0.020, 0.020, 5):
            for w in np.linspace(-0.0225, 0.0225, 5):
                p = clamp + Rc @ Vector((u, w, -0.007))
                zt = S.down_z(p.x, p.y, z0=p.z + 0.05)
                if zt is not None and zt > p.z + lift - 0.002 and zt - p.z < 0.03:
                    lift = zt - p.z + 0.002
        clamp.z += lift
        cl = bc.box(f"_clamp{sx}", (0.040, 0.045, 0.014), loc=clamp, rot=(-25, 0, 0), mat=mats["graphite"],
                    bevel=0.004, segments=2)
        parts.append(cl)
        p0 = Vector((0, ys, 1.385))
        p1 = S.push_out(Vector((sx * 0.045, 0.126 + dy, 1.394)), 0.013)
        p2 = S.push_out(Vector((sx * 0.085, 0.090 + dy * 0.7, 1.400)), 0.013)
        # resample, then keep every ring centre 0.013 off the coat (half the 0.014 arm + 6 mm): the plain spline
        # dipped through the collar root (review round 2)
        dense = catmull([tuple(p0), tuple(p1), tuple(p2), tuple(clamp)], 14)
        path = [tuple(dense[0])] + [tuple(S.push_out(Vector(p), 0.013)) for p in dense[1:-1]] + [tuple(dense[-1])]
        arm = sweep(f"_yoke{sx}", path, 0.022, 0.014, lambda p: (0, 0.35, 1.0), [mats["graphite"]], n=14)
        bc.add_bevel(arm, 0.003, 2, angle=40)
        parts.append(arm)
        led = bc.sphere(f"_led{sx}", 0.0035, loc=tuple(clamp + Vector((0, 0.020, 0.008))), segments=12, rings=8,
                        mat=mats["glow"])
        parts.append(led)
    # ---- hub (graphite collar) + glow ring
    hb = Vector((0, 0.180 + dy, 1.140))
    hub = bc.lathe("_hub", [(0.0, 0.0), (0.030, 0.0), (0.031, 0.006), (0.026, 0.022), (0.022, 0.030), (0.0, 0.030)],
                   loc=tuple(hb), steps=28, mat=mats["graphite"], smooth=40)
    hub.scale = (1, 0.72, 1)
    bc.apply_modifiers(hub)
    parts.append(hub)
    ringo = _torus("_ring", 0.026, 0.0035, (0, hb.y, 1.155), mats["glow"], sy=0.72)
    parts.append(ringo)
    # ---- core spindle (glow), elliptic (Y 0.62)
    # core capped (round 2): above it the hair reaches into the front gap of the bud on a 45 deg look-up
    zz = np.linspace(BUD_Z0 + 0.004, CORE_TOP - 0.004, 24)
    prof = [(0.0, BUD_Z0)] + [(0.78 * bud_r(z) * (1 - 0.6 * smooth01((z - 1.36) / (CORE_TOP - 1.36))), z) for z in zz] + [(0.0, CORE_TOP)]
    core = bc.lathe("_core", [(r, z - 1.150) for r, z in prof], loc=(0, 0.178 + dy, 1.150), steps=24,
                    mat=mats["glow"], smooth=180)
    core.scale = (1, 0.62, 1)
    core.rotation_euler = (math.atan2(-0.012, 0.415) * -1, 0, 0)
    bc.apply_modifiers(core)
    _apply_xform(core)
    parts.append(core)
    bc.apply_modifiers(core)
    _apply_xform(core)
    bend_mesh(core)
    for p in parts:
        bc.apply_modifiers(p)
        _apply_xform(p)
    bloom = bc.join(parts, "SOL_Bloom")
    bc.uv_all([bloom])
    # origin at the bud base (module pivot), on the spine
    piv = Vector((0, 0.172 + dy, 1.150))
    bloom.data.transform(Matrix.Translation(-piv))
    bloom.location = piv
    # ---- vanes
    vanes = []
    vc = bud_vane("SOL_Bloom_Vane_C", "C", mats, dy)
    bend_mesh(vc)
    set_local_frame(vc, Vector(VANE_C["pivot"]) + Vector((0, dy, 0)), (-1, 0, 0))
    vl = bud_vane("SOL_Bloom_Vane_L", "L", mats, dy)
    bend_mesh(vl)
    set_local_frame(vl, Vector(VANE_L["pivot"]) + Vector((0, dy, 0)), (0, 1, 0))
    vr = bud_vane("SOL_Bloom_Vane_R", "R", mats, dy)
    bend_mesh(vr)
    pr = VANE_L["pivot"]
    set_local_frame(vr, Vector((-pr[0], pr[1] + dy, pr[2])), (0, -1, 0))
    for v, ang in ((vc, OPEN_DEG["C"]), (vl, OPEN_DEG["L"]), (vr, OPEN_DEG["R"])):
        v["open_angle_deg"] = ang
        v["closed_angle_deg"] = 0.0
        v["hinge_axis_local"] = "X"
        bc.uv_all([v])
        vanes.append(v)
    for v in vanes:
        mw = v.matrix_world.copy()
        v.parent = bloom
        v.matrix_parent_inverse = bloom.matrix_world.inverted()
        v.matrix_world = mw
    log(f"bloom: module {sum(len(p.vertices) - 2 for p in bloom.data.polygons)} tris, vanes "
        f"{[sum(len(p.vertices) - 2 for p in v.data.polygons) for v in vanes]}")
    return bloom, vanes, dy


def _torus(name, R, r, loc, mat, seg=28, rseg=8, sy=1.0):
    verts, faces = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            rr = R + r * math.cos(b)
            verts.append((rr * math.cos(a), rr * math.sin(a) * sy, r * math.sin(b)))
    for i in range(seg):
        for j in range(rseg):
            a = i * rseg + j
            b = ((i + 1) % seg) * rseg + j
            c = ((i + 1) % seg) * rseg + (j + 1) % rseg
            d = i * rseg + (j + 1) % rseg
            faces.append((a, b, c, d))
    o = mesh_obj(name, verts, faces, mats=[mat])
    o.location = loc
    _apply_xform(o)
    return o


def _apply_xform(o):
    bpy.context.view_layer.update()
    o.data.transform(o.matrix_world)
    o.matrix_world = Matrix.Identity(4)


# ---------------------------------------------------------------------------------------------- gear
def strap_tops(obj):
    """Where the TRELLIS chest straps were cut by the shoulder-cap rebuild: dark bluish verts just below the cap."""
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor"])
    fc = face_tex_colors(me, px)
    c = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("center", c)
    c = c.reshape(-1, 3)
    out = {}
    for sx in (1, -1):
        m = (sx * c[:, 0] > 0.06) & (sx * c[:, 0] < 0.18) & (c[:, 2] > 1.33) & (c[:, 2] < 1.385) & (c[:, 1] < 0.01) \
            & (fc.mean(1) < 0.25) & (fc[:, 2] >= fc[:, 0] - 0.01)
        if m.sum() < 3:
            out[sx] = None
            continue
        sel = c[m]
        top = sel[sel[:, 2] > np.percentile(sel[:, 2], 70)]
        out[sx] = top.mean(0)
        log(f"strap top side {sx:+d}: {np.round(out[sx], 3)} ({m.sum()} faces)")
    return out


def build_gear(mats, bloom_dy, drone_cen=None, drone_n=None):
    S = Surf(body(), no_hair=True)
    tops = strap_tops(body())
    parts = []
    for sx in (1, -1):
        zs = S.down_z(sx * 0.108, 0.080 + bloom_dy * 0.5) or 1.40
        start = Vector((sx * 0.112, 0.068 + bloom_dy * 0.5, zs + 0.004))
        end = Vector(tops[sx]) if tops[sx] is not None else Vector((sx * 0.112, -0.045, 1.365))
        mid1 = Vector((sx * 0.115, 0.035, 0.0))
        mid2 = Vector((sx * 0.115, -0.010, 0.0))
        mid1.z = (S.down_z(mid1.x, mid1.y) or 1.41)
        mid2.z = (S.down_z(mid2.x, mid2.y) or 1.41)
        pts = [start, mid1, mid2, end + Vector((0, -0.004, 0.012))]
        pts = [S.push_out(p, 0.0045) for p in pts]

        def up_fn(p):
            loc, nrm, d = S.nearest(p)
            return tuple(nrm)
        st = sweep(f"_strap{sx}", [tuple(p) for p in pts], 0.028, 0.005, up_fn, [mats["charcoal"]], n=16)
        parts.append(st)
    emb = build_emblem(mats, S)
    parts += emb
    parts += build_glow_props(mats)
    if drone_cen is not None:
        parts.append(build_dock(mats, drone_cen, drone_n))
    for p in parts:
        bc.apply_modifiers(p)
    gear = bc.join(parts, "SOL_Gear")
    bc.uv_all([gear])
    log(f"gear: {sum(len(p.vertices) - 2 for p in gear.data.polygons)} tris")
    return gear


def build_emblem(mats, S):
    """Bloom mark on her LEFT upper arm: flat-top hexagon (0.052 across corners) in sand + three coral almond petals
    (centre petal 0.026 x 0.011, side petals 0.021 x 0.009 at +-42 deg from a common base 0.012 below centre).
    Three petals, never four: it must not read as a cross."""
    n = Vector((0.473, -0.708, 0.526)).normalized()
    c0 = Vector((0.272, -0.030, 1.331))
    # land on the actual sleeve surface: walk to the nearest surface point
    loc, nrm, _d = S.nearest(c0)
    nrm = Vector(nrm).normalized()
    if nrm.dot(n) < 0.3:
        nrm = n
    up = Vector((-0.743, 0, 0.669))
    up = (up - nrm * up.dot(nrm)).normalized()
    right = up.cross(nrm).normalized()
    parts = []

    def place(o, lift):
        """Wrap the flat slab onto the sleeve keeping its thickness: every vertex goes to the nearest sleeve point
        (of its footprint) + normal * (lift + its height in the slab)."""
        me = o.data
        for v in me.vertices:
            u, w_, h = v.co.x, v.co.y, v.co.z
            p0 = loc + right * u + up * w_
            sl, sn, _d = S.nearest(p0)
            sn = Vector(sn).normalized()
            if sn.dot(nrm) < 0.2:
                sn = nrm
            v.co = Vector(sl) + sn * (lift + h)
        me.update()

    # hex patch: flat-top (corners at 0 / 60 / ...), rounded a little by a bevel, 0.0025 thick
    R = 0.026
    hexp = [(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in range(0, 360, 60)]
    o = _slab("_hex", hexp, 0.0025, mats["sand"], sub=3)
    place(o, 0.0014)
    parts.append(o)

    def lens(L, w, ang, nseg=10):
        pts = []
        for k in range(nseg + 1):
            t = k / nseg
            pts.append((w / 2 * math.sin(math.pi * t), L * t))
        for k in range(nseg - 1, 0, -1):
            t = k / nseg
            pts.append((-w / 2 * math.sin(math.pi * t), L * t))
        a = math.radians(ang)
        return [(px_ * math.cos(a) - pz * math.sin(a), px_ * math.sin(a) + pz * math.cos(a) - 0.012) for px_, pz in pts]

    for i, (L, w, ang) in enumerate(((0.026, 0.011, 0.0), (0.021, 0.009, 42.0), (0.021, 0.009, -42.0))):
        o = _slab(f"_petal{i}", lens(L, w, ang), 0.0015, mats["coral"], sub=1)
        place(o, 0.0042)
        parts.append(o)
    return parts


def build_glow_props(mats):
    """The injector vial (brief 4j) as an M_SOL_Glow overlay in the coral channel of the TRELLIS bracer (RIGHT
    forearm). It lives in SOL_Gear and inherits rigid lowerarm_r weights from the body. (The heal drone and its
    lens are the separate procedural SOL_Drone since review round 2.)"""
    from sol_rig import vertex_tex_colors
    b = body()
    co = np.array([v.co[:] for v in b.data.vertices])
    vc = np.nan_to_num(vertex_tex_colors(b), nan=0.5)
    lum = vc.mean(1)
    out = []
    # ---- vial: PCA of the coral verts of the bracer channel
    m = (co[:, 0] < -0.33) & (co[:, 2] > 0.98) & (co[:, 2] < 1.12) & (vc[:, 0] > 0.6) & (vc[:, 0] - vc[:, 1] > 0.25)
    P = co[m]
    if len(P) > 10:
        c = P.mean(0)
        u, sv, vt = np.linalg.svd(P - c, full_matrices=False)
        ax = vt[0]
        nrm = vt[2]
        # forearm axis point: push the normal outward
        from sol_joints import _norm  # noqa
        t = (P - c) @ ax
        L = (np.percentile(t, 95) - np.percentile(t, 5)) * 0.9
        wpos = c - np.array([-0.40, 0.02, 1.05])
        side = np.array([-0.39, 0.03, 1.05])
        if nrm @ (c - side) < 0:
            nrm = -nrm
        r = 0.0082
        cen = c + nrm * r * 0.25
        vial = bc.cylinder("_vial", r, L, loc=(0, 0, 0), verts=16, mat=mats["glow"], smooth=40)
        cap1 = bc.cylinder("_vcap1", r * 1.12, 0.005, loc=(0, 0, L / 2), verts=16, mat=mats["gunmetal"], bevel=0.001)
        cap2 = bc.cylinder("_vcap2", r * 1.12, 0.005, loc=(0, 0, -L / 2), verts=16, mat=mats["gunmetal"],
                           bevel=0.001)
        Z = Vector(ax).normalized()
        X = Vector(nrm).cross(Z).normalized()
        Y = Z.cross(X)
        M = Matrix((X, Y, Z)).transposed().to_4x4()
        M.translation = Vector(cen)
        for o in (vial, cap1, cap2):
            bc.apply_modifiers(o)
            _apply_xform(o)
            o.data.transform(M)
            out.append(o)
        log(f"vial: centre {np.round(cen, 3)}, axis {np.round(ax, 2)}, length {L:.3f}")
    return out


# ---------------------------------------------------------------------------------------------- heal drone
DRONE_R = 0.050            # shell radius (brief 4k: 0.040; larger so the hip ball and its eye read at 64 px)
DRONE_EYE = (0.707, -0.707, 0.0)   # eye faces forward-out (brief 4k)
DRONE_GAP = 0.004          # shell to coat


def drone_frame():
    """Drone centre + hip normal: the drone sits DRONE_GAP off the coat patch that replaced the TRELLIS drone."""
    from sol_lib import DRONE_SPHERE_C
    me = body().data
    pf = np.zeros(len(me.polygons), np.int32)
    me.attributes["sol_patch"].data.foreach_get("value", pf)
    c = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("center", c)
    c = c.reshape(-1, 3)
    nr = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", nr)
    nr = nr.reshape(-1, 3)
    sel = pf == 5
    n = nr[sel].mean(0)
    n /= np.linalg.norm(n)
    S = Surf(body())
    hit = S.bvh.ray_cast(Vector(DRONE_SPHERE_C + n * 0.25), Vector(-n), 0.5)
    p = np.array(hit[0]) if hit[0] else c[sel].mean(0)
    # radius of the (Z-scaled) shell along n
    rz = DRONE_R * 0.92
    r_n = 1.0 / math.sqrt((n[0] ** 2 + n[1] ** 2) / DRONE_R ** 2 + n[2] ** 2 / rz ** 2)
    cen = p + n * (r_n + DRONE_GAP)
    return Vector(cen), Vector(n)


def build_drone(mats):
    """SOL_Drone (brief 4k): a separate object (origin at its centre, world-aligned) that the game can hide or
    launch for MEND DRONE. Ivory shell (Z 0.92), graphite thruster band low on the shell, graphite eye bezel with a
    coral Glow lens ring around a dark pupil facing forward-out, a dim Glow vent underneath, a short graphite
    antenna tilted 15 deg back. Parented to SOL_SOCKET_DroneDock in stage E."""
    cen, n = drone_frame()
    r = DRONE_R
    parts = []
    shell = bc.sphere("_dr_shell", r, scale=(1, 1, 0.92), segments=24, rings=12, mat=mats["ivory_hard"])
    parts.append(shell)
    hb = -0.58 * r * 0.92                                  # band height (clear of the eye bezel)
    rb = r * math.sqrt(max(0.0, 1 - (hb / (0.92 * r)) ** 2))
    parts.append(_torus("_dr_band", rb + 0.0010, 0.0055, (0, 0, hb), mats["graphite"], seg=28, rseg=8))
    e = Vector(DRONE_EYE).normalized()
    Z = e
    X = Vector((0, 0, 1)).cross(Z).normalized()
    Y = Z.cross(X)
    Me = Matrix((X, Y, Z)).transposed().to_4x4()
    # bezel ring (lathe along the eye axis; heights measured from the drone centre): the lens sits 1.8 mm deep in it
    bez = bc.lathe("_dr_bezel", [(0.0, r - 0.008), (0.0250, r - 0.008), (0.0250, r + 0.0040), (0.0234, r + 0.0056),
                                 (0.0186, r + 0.0056), (0.0180, r + 0.0018), (0.0, r + 0.0018)], steps=32,
                   mat=mats["graphite"], smooth=40)
    lens = bc.cylinder("_dr_lens", 0.0179, 0.0020, verts=32, mat=mats["glow"])
    pup = bc.cylinder("_dr_pupil", 0.0085, 0.0012, verts=24, mat=mats["graphite"])
    for o, d in ((bez, 0.0), (lens, r + 0.0030), (pup, r + 0.0046)):
        bc.apply_modifiers(o)
        _apply_xform(o)
        M = Me.copy()
        M.translation = e * d
        o.data.transform(M)
        parts.append(o)
    vent = bc.cylinder("_dr_vent", 0.0150, 0.0024, loc=(0, 0, -0.92 * r + 0.0004), verts=24, mat=mats["glow"])
    parts.append(vent)
    ant = bc.cylinder("_dr_ant", 0.0022, 0.020, verts=10, mat=mats["graphite"])
    tipb = bc.sphere("_dr_anttip", 0.0034, segments=10, rings=6, mat=mats["graphite"])
    for o, d in ((ant, 0.010), (tipb, 0.0205)):
        bc.apply_modifiers(o)
        _apply_xform(o)
        M = Matrix.Rotation(math.radians(15), 4, "X") @ Matrix.Translation((0, 0, d))
        M = Matrix.Translation((0, 0.006, 0.92 * r - 0.003)) @ M
        o.data.transform(M)
        parts.append(o)
    for p in parts:
        bc.apply_modifiers(p)
        _apply_xform(p)
    drone = bc.join(parts, "SOL_Drone")
    bc.uv_all([drone])
    drone.location = cen
    drone["note"] = "heal drone (MEND DRONE): origin at its centre; child of SOL_SOCKET_DroneDock"
    log(f"drone: centre {np.round(cen[:], 3)}, hip normal {np.round(n[:], 2)}, "
        f"{sum(len(p.vertices) - 2 for p in drone.data.polygons)} tris")
    return drone, cen, n


def build_dock(mats, cen, n):
    """Graphite cradle cup on the hip that holds the docked drone (part of SOL_Gear, pelvis-skinned): a spherical
    cap shell, half-angle 55 deg, opening away from the hip."""
    r_in, r_out = DRONE_R + 0.0022, DRONE_R + 0.0060
    prof = []
    for k in range(9):
        a = math.radians(55.0 * k / 8)
        prof.append((r_out * math.sin(a), -r_out * math.cos(a)))
    for k in range(8, -1, -1):
        a = math.radians(55.0 * k / 8)
        prof.append((r_in * math.sin(a), -r_in * math.cos(a)))
    cup = bc.lathe("_dock", prof, steps=28, mat=mats["graphite"], smooth=40)
    bc.apply_modifiers(cup)
    _apply_xform(cup)
    Z = -Vector(n).normalized()          # cup axis: the pole points at the hip
    Z = -Z
    X = Vector((0, 0, 1)).cross(Z).normalized()
    Y = Z.cross(X)
    M = Matrix((X, Y, Z)).transposed().to_4x4()
    M.translation = cen
    cup.data.transform(M)
    # flatten the cup's Z the way the drone shell is flattened (keeps the gap even)
    S = Matrix.Translation(cen) @ Matrix.Diagonal((1, 1, 0.92, 1)) @ Matrix.Translation(-cen)
    cup.data.transform(S)
    return cup


def _slab(name, poly2d, thick, mat, sub=1):
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, 0)) for x, y in poly2d]
    f = bm.faces.new(vs)
    bmesh.ops.triangulate(bm, faces=[f])
    ext = bmesh.ops.extrude_face_region(bm, geom=list(bm.faces))
    nv = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=Vector((0, 0, thick)), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    me.materials.append(mat)
    # subdivide the big faces a bit so the shrinkwrap can follow the sleeve curvature
    if sub:
        bm = bmesh.new()
        bm.from_mesh(me)
        top = [e for e in bm.edges if all(abs(v.co.z) < 1e-6 or abs(v.co.z - thick) < 1e-6 for v in e.verts)]
        bmesh.ops.subdivide_edges(bm, edges=top, cuts=sub, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
        bm.to_mesh(me)
        bm.free()
    bc.shade_smooth(o, 30)
    return o


def stage_c():
    mats = materials()
    bloom, vanes, dy = build_bloom(mats)
    drone, dcen, dn = build_drone(mats)
    gear = build_gear(mats, dy, dcen, dn)
    return bloom, vanes, gear, drone
