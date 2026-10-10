"""Geometry, material and UV helpers for the Showhome props kit (used by build_props.py, runs inside Blender 5.2).

Every prop is built into ONE bmesh (class Prop) in its own local frame: metres, Z up, origin at the prop's base.
Primitives (boxes with real bevels, cylinders, tubes, prisms, lathes, noisy blobs) are merged into that bmesh
with a material slot each, then `Prop.finish()` turns it into one mesh object, computes UVs from each material's
mapping rule (world-metre box projection, per-face 0-1, ...), writes an AO vertex colour and smooth shading.

Materials are declared once with `spec(name, ...)` and created lazily with `M(name)`.
Textured materials multiply  image x tint x vertex colour  into Base Color, which the glTF exporter writes as
baseColorTexture + baseColorFactor + COLOR_0 (verified with Blender 5.2's exporter).
"""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector, noise

ROOT = r"F:/git/val etf/assets/maps/showhome"
TEX = os.path.join(ROOT, "textures")
KIT = os.path.join(ROOT, "kit")
KTEX = os.path.join(KIT, "tex")


def lin1(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lin(rgb):
    """sRGB 0-255 triple -> linear 0-1 triple."""
    return tuple(lin1(c) for c in rgb)


# ------------------------------------------------------------------------------------------------ materials
_SPECS = {}


def spec(name, color=(0.8, 0.8, 0.8), tex=None, repeat=1.0, offset=(0.0, 0.0), rough=0.6, metal=0.0, tint=None,
         normal=None, nstrength=1.0, uv="box", vc=None, alpha=None, emission=None, estrength=1.0, cull=True,
         smooth=True, ao=True, coat=0.0, orm=None, height_range=0.0):
    """Declare a material. tex: file in textures/ (or an absolute path). repeat: metres per texture repeat
    (number or (u, v)). uv: 'box' (world-metre box projection, V up on walls), 'face01' (each face 0-1),
    'none'. tint: linear RGB multiplied over the texture (glTF baseColorFactor). vc: multiply the 'Col'
    vertex colour (default: on for textured materials). alpha: 'tex' (image alpha, blended) or a float.
    ao: whether the prop's ground-AO vertex colour applies to faces of this material."""
    _SPECS[name] = dict(color=color, tex=tex, repeat=repeat if isinstance(repeat, (tuple, list)) else (repeat, repeat),
                        offset=offset, rough=rough, metal=metal, tint=tint, normal=normal, nstrength=nstrength,
                        uv=uv, vc=(tex is not None) if vc is None else vc, alpha=alpha, emission=emission,
                        estrength=estrength, cull=cull, smooth=smooth, ao=ao, coat=coat, orm=orm,
                        height_range=height_range)


def _img(path, colour=True):
    if not os.path.isabs(path):
        path = os.path.join(TEX, path)
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return img


def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def M(name):
    m = bpy.data.materials.get(name)
    if m is not None:
        return m
    s = _SPECS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = _principled(m)
    out = None
    if s["tex"]:
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = _img(s["tex"])
        ti.location = (-700, 300)
        out = ti.outputs["Color"]
        if s["tint"] is not None:
            mx = nt.nodes.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.blend_type = "MULTIPLY"
            mx.inputs[0].default_value = 1.0
            nt.links.new(out, mx.inputs[6])
            mx.inputs[7].default_value = (*s["tint"], 1.0)
            out = mx.outputs[2]
        if s["alpha"] == "tex":
            nt.links.new(ti.outputs["Alpha"], p.inputs["Alpha"])
    else:
        p.inputs["Base Color"].default_value = (*s["color"], 1.0)
    if s["vc"]:
        va = nt.nodes.new("ShaderNodeVertexColor")
        va.layer_name = "Col"
        va.location = (-500, 0)
        if out is None:
            rgb = nt.nodes.new("ShaderNodeRGB")
            rgb.outputs[0].default_value = (*s["color"], 1.0)
            out = rgb.outputs[0]
        mx2 = nt.nodes.new("ShaderNodeMix")
        mx2.data_type = "RGBA"
        mx2.blend_type = "MULTIPLY"
        mx2.inputs[0].default_value = 1.0
        nt.links.new(out, mx2.inputs[6])
        nt.links.new(va.outputs["Color"], mx2.inputs[7])
        out = mx2.outputs[2]
    if out is not None:
        nt.links.new(out, p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = s["rough"]
    p.inputs["Metallic"].default_value = s["metal"]
    if s.get("orm"):
        to = nt.nodes.new("ShaderNodeTexImage")
        to.image = _img(s["orm"], colour=False)
        to.label = "Linear ORM: AO / roughness / metalness"
        split = nt.nodes.new("ShaderNodeSeparateColor")
        split.mode = "RGB"
        nt.links.new(to.outputs["Color"], split.inputs["Color"])
        nt.links.new(split.outputs["Green"], p.inputs["Roughness"])
        nt.links.new(split.outputs["Blue"], p.inputs["Metallic"])
        # The Blender glTF exporter recognises this named socket as occlusionTexture.
        group = bpy.data.node_groups.get("glTF Material Output")
        if group is None:
            # Importing another GLB into this scene also needs the official volume / iridescence sockets.
            from io_scene_gltf2.blender.com.material_helpers import create_settings_group
            group = create_settings_group("glTF Material Output")
        oc = nt.nodes.new("ShaderNodeGroup")
        oc.node_tree = group
        nt.links.new(split.outputs["Red"], oc.inputs["Occlusion"])
    if s["coat"]:
        p.inputs["Coat Weight"].default_value = s["coat"]
    if s["normal"]:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = _img(s["normal"], colour=False)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = s["nstrength"]
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    if s["emission"] is not None:
        p.inputs["Emission Color"].default_value = (*s["emission"], 1.0)
        p.inputs["Emission Strength"].default_value = s["estrength"]
    if isinstance(s["alpha"], float):
        p.inputs["Alpha"].default_value = s["alpha"]
    if s["alpha"] is not None:
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
    m.use_backface_culling = bool(s["cull"])
    m.diffuse_color = (*(s["tint"] or s["color"]), 1.0)
    m["uv"] = s["uv"]
    m["repeat"] = list(s["repeat"])
    m["offset"] = list(s["offset"])
    m["smooth"] = bool(s["smooth"])
    m["ao"] = bool(s["ao"])
    m["height_range_m"] = float(s.get("height_range", 0.0))
    return m


# ------------------------------------------------------------------------------------------------ geometry
def _edges_where(bm, fn):
    out = []
    for e in bm.edges:
        a, b = e.verts[0].co, e.verts[1].co
        if fn(a, b):
            out.append(e)
    return out


def bevel_bm(bm, width, seg=2, edges=None, profile=0.5):
    if width <= 0:
        return
    geom = edges if edges is not None else list(bm.edges)
    if not geom:
        return
    bmesh.ops.bevel(bm, geom=geom, offset=width, offset_type="OFFSET", segments=seg, profile=profile,
                    affect="EDGES", clamp_overlap=True)


def vertical_edges(a, b):
    return abs(a.x - b.x) < 1e-6 and abs(a.y - b.y) < 1e-6


def top_edges(zmax):
    return lambda a, b: abs(a.z - zmax) < 1e-5 and abs(b.z - zmax) < 1e-5


class Prop:
    """One prop = one bmesh + a list of material names."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []

    # -- internals
    def _mi(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def merge(self, t, mat, mx=None, flat=False, recalc=False):
        """Merge temp bmesh `t` into the prop with material `mat` (frees t)."""
        if recalc:
            bmesh.ops.recalc_face_normals(t, faces=t.faces)
        if mx is not None:
            t.transform(mx)
        mi = self._mi(mat)
        vm = {v: self.bm.verts.new(v.co) for v in t.verts}
        for f in t.faces:
            try:
                nf = self.bm.faces.new([vm[v] for v in f.verts])
            except ValueError:
                continue
            nf.material_index = mi
            nf.smooth = not flat
        t.free()
        return self

    # -- primitives
    def box(self, x0, y0, z0, x1, y1, z1, mat, bev=0.0, seg=2, edges=None, mx=None, flat=False):
        """Box by min/max corners. bev: bevel width on all (or `edges(a, b)`-selected) edges."""
        t = bmesh.new()
        bmesh.ops.create_cube(t, size=1.0)
        c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        s = Vector((x1 - x0, y1 - y0, z1 - z0))
        for v in t.verts:
            v.co = Vector((c.x + v.co.x * s.x, c.y + v.co.y * s.y, c.z + v.co.z * s.z))
        if bev > 0:
            bev = min(bev, 0.49 * min(abs(s.x), abs(s.y), abs(s.z)))
            bevel_bm(t, bev, seg, _edges_where(t, edges) if edges else None)
        return self.merge(t, mat, mx, flat)

    def boxc(self, c, s, mat, **kw):
        return self.box(c[0] - s[0] / 2, c[1] - s[1] / 2, c[2] - s[2] / 2, c[0] + s[0] / 2, c[1] + s[1] / 2,
                        c[2] + s[2] / 2, mat, **kw)

    def cyl(self, p0, p1, r, mat, n=16, r2=None, bev=0.0, seg=2, cap=True, flat=False, rot=0.0):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        L = d.length
        t = bmesh.new()
        bmesh.ops.create_cone(t, cap_ends=cap, cap_tris=False, segments=n, radius1=r,
                              radius2=r if r2 is None else r2, depth=L)
        if bev > 0:
            bevel_bm(t, bev, seg, _edges_where(t, lambda a, b: abs(a.z - b.z) < 1e-6))
        if abs(rot) > 0:
            t.transform(Matrix.Rotation(rot, 4, "Z"))
        q = Vector((0, 0, 1)).rotation_difference(d.normalized())
        mx = Matrix.Translation((p0 + p1) / 2) @ q.to_matrix().to_4x4()
        return self.merge(t, mat, mx, flat)

    def sphere(self, c, r, mat, scale=(1, 1, 1), seg=16, rings=8, flat=False):
        t = bmesh.new()
        bmesh.ops.create_uvsphere(t, u_segments=seg, v_segments=rings, radius=r)
        for v in t.verts:
            v.co = Vector((v.co.x * scale[0], v.co.y * scale[1], v.co.z * scale[2])) + Vector(c)
        return self.merge(t, mat, None, flat)

    def blob(self, c, r, mat, scale=(1, 1, 1), sub=2, amp=0.18, freq=1.6, seed=0, flat=False, zclip=None):
        """Noisy icosphere clump (tree canopies, shrubs). zclip: flatten verts below this local z."""
        t = bmesh.new()
        bmesh.ops.create_icosphere(t, subdivisions=sub, radius=r)
        off = Vector((seed * 7.31, seed * 3.17, seed * 5.53))
        for v in t.verts:
            n = v.co.normalized()
            k = 1.0 + amp * noise.noise(n * freq + off) + 0.5 * amp * noise.noise(n * freq * 2.3 + off * 1.7)
            co = n * r * k
            co = Vector((co.x * scale[0], co.y * scale[1], co.z * scale[2]))
            if zclip is not None and co.z < zclip:
                co.z = zclip + (co.z - zclip) * 0.15
            v.co = co + Vector(c)
        return self.merge(t, mat, None, flat, recalc=True)

    def prism(self, poly, a0, a1, mat, axis="Z", bev=0.0, seg=2, mx=None, flat=False, edges=None):
        """Extrude a closed 2D polygon. axis 'Z': poly in (x, y), from z=a0 to a1. axis 'X': poly in (y, z), from
        x=a0 to a1. axis 'Y': poly in (x, z), from y=a0 to a1."""
        t = bmesh.new()

        def P(u, v, w):
            if axis == "Z":
                return Vector((u, v, w))
            if axis == "X":
                return Vector((w, u, v))
            return Vector((u, w, v))

        lo = [t.verts.new(P(u, v, a0)) for (u, v) in poly]
        hi = [t.verts.new(P(u, v, a1)) for (u, v) in poly]
        n = len(poly)
        t.faces.new(lo[::-1])
        t.faces.new(hi)
        for i in range(n):
            j = (i + 1) % n
            t.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bmesh.ops.recalc_face_normals(t, faces=t.faces)
        if bev > 0:
            bevel_bm(t, bev, seg, _edges_where(t, edges) if edges else None)
        return self.merge(t, mat, mx, flat)

    def lathe(self, prof, mat, n=24, c=(0, 0, 0), flat=False, mx=None):
        """Revolve [(r, z), ...] around local Z (profile from bottom to top; r=0 ends close the shape)."""
        t = bmesh.new()
        rings = []
        for i in range(n):
            a = 2 * math.pi * i / n
            rings.append([t.verts.new((r * math.cos(a) + c[0], r * math.sin(a) + c[1], z + c[2])) for (r, z) in prof])
        for i in range(n):
            r0, r1 = rings[i], rings[(i + 1) % n]
            for j in range(len(prof) - 1):
                try:
                    t.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))
                except ValueError:
                    pass
        if prof[0][0] > 1e-6:
            t.faces.new([rg[0] for rg in rings][::-1])
        if prof[-1][0] > 1e-6:
            t.faces.new([rg[-1] for rg in rings])
        bmesh.ops.remove_doubles(t, verts=t.verts, dist=1e-5)
        return self.merge(t, mat, mx, flat, recalc=True)

    def tube(self, pts, r, mat, n=8, cap=True, flat=False):
        """Sweep a circle of radius r along a polyline (cables, rails, arches)."""
        pts = [Vector(p) for p in pts]
        t = bmesh.new()
        rings = []
        prev_n = None
        for i, p in enumerate(pts):
            if i == 0:
                tan = pts[1] - pts[0]
            elif i == len(pts) - 1:
                tan = pts[-1] - pts[-2]
            else:
                tan = (pts[i + 1] - pts[i - 1])
            tan.normalize()
            if prev_n is None:
                ref = Vector((0, 0, 1)) if abs(tan.z) < 0.9 else Vector((1, 0, 0))
                nrm = tan.cross(ref).normalized()
            else:
                nrm = (prev_n - tan * prev_n.dot(tan)).normalized()
            prev_n = nrm
            bi = tan.cross(nrm)
            rings.append([t.verts.new(p + (nrm * math.cos(2 * math.pi * k / n) + bi * math.sin(2 * math.pi * k / n)) * r)
                          for k in range(n)])
        for i in range(len(rings) - 1):
            for k in range(n):
                t.faces.new((rings[i][k], rings[i][(k + 1) % n], rings[i + 1][(k + 1) % n], rings[i + 1][k]))
        if cap:
            t.faces.new(rings[0][::-1])
            t.faces.new(rings[-1])
        return self.merge(t, mat, None, flat, recalc=True)

    def bar(self, p0, p1, w, d, mat, up=(0, 0, 1), bev=0.0, flat=False):
        """Rectangular bar from p0 to p1, w wide (along `up`-ish) and d deep (lattice members, beams, arms)."""
        p0, p1 = Vector(p0), Vector(p1)
        ax = p1 - p0
        L = ax.length
        ax.normalize()
        upv = Vector(up)
        if abs(ax.dot(upv.normalized())) > 0.98:
            upv = Vector((1, 0, 0)) if abs(ax.x) < 0.9 else Vector((0, 1, 0))
        side = ax.cross(upv).normalized()
        upv = side.cross(ax).normalized()
        t = bmesh.new()
        bmesh.ops.create_cube(t, size=1.0)
        for v in t.verts:
            v.co = Vector((v.co.x * d, v.co.y * w, (v.co.z + 0.5) * L))
        if bev > 0:
            bevel_bm(t, min(bev, 0.45 * min(w, d)), 1, _edges_where(t, lambda a, b: abs(a.z - b.z) > 1e-6))
        rot = Matrix((side, upv, ax)).transposed().to_4x4()
        return self.merge(t, mat, Matrix.Translation(p0) @ rot, flat)

    def quad(self, pts, mat, flat=False):
        t = bmesh.new()
        t.faces.new([t.verts.new(p) for p in pts])
        return self.merge(t, mat, None, flat)

    def transform_last(self, mx, since):
        """Transform verts created after vertex-count `since` (to place a group of primitives)."""
        self.bm.verts.ensure_lookup_table()
        for v in self.bm.verts[since:]:
            v.co = mx @ v.co
        return self

    def nverts(self):
        return len(self.bm.verts)

    # -- finish
    def finish(self, parent_col, meta=None, ao=(0.45, 0.72), ao_fn=None, sharp_deg=38.0):
        """Build the mesh object PROP_<name> in collection PROP_<name> (child of parent_col).
        ao: (height, darkest) ground-contact darkening on materials with ao=True, or None.
        ao_fn(co, normal, matname) -> float overrides it."""
        name = "PROP_" + self.name
        bm = self.bm
        bm.normal_update()
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for mn in self.mats:
            me.materials.append(M(mn))
        ob = bpy.data.objects.new(name, me)
        col = bpy.data.collections.new(name)
        parent_col.children.link(col)
        col.objects.link(ob)
        compute_uvs(me)
        compute_vc(me, ao, ao_fn)
        flat_mats = {i for i, mn in enumerate(self.mats) if not _SPECS[mn]["smooth"]}
        for p in me.polygons:
            p.use_smooth = p.material_index not in flat_mats
        try:
            me.set_sharp_from_angle(angle=math.radians(sharp_deg))
        except Exception:
            pass
        for k, v in (meta or {}).items():
            ob[k] = v
        return ob


# ------------------------------------------------------------------------------------------------ UV + VC
def compute_uvs(me):
    uvl = me.uv_layers.get("UVMap") or me.uv_layers.new(name="UVMap")
    data = uvl.data
    verts = me.vertices
    loops = me.loops
    for poly in me.polygons:
        mat = me.materials[poly.material_index]
        mode = mat.get("uv", "box")
        ru, rv = mat.get("repeat", [1.0, 1.0])
        ou, ov = mat.get("offset", [0.0, 0.0])
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        pts = []
        for li in poly.loop_indices:
            co = verts[loops[li].vertex_index].co
            if ax == 2:
                u, v = (co.x, co.y) if n.z >= 0 else (co.x, -co.y)
            elif ax == 1:
                u, v = (co.x if n.y < 0 else -co.x), co.z
            else:
                u, v = (-co.y if n.x < 0 else co.y), co.z
            pts.append((li, u, v))
        if mode == "boxh" and ax != 2:
            # horizontal grain on walls (planks, boards laid flat): V runs along the face, U up
            pts = [(li, v, u) for (li, u, v) in pts]
        if mode == "face01":
            us = [p[1] for p in pts]
            vs = [p[2] for p in pts]
            u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
            for li, u, v in pts:
                data[li].uv = ((u - u0) / max(u1 - u0, 1e-6), (v - v0) / max(v1 - v0, 1e-6))
        else:
            for li, u, v in pts:
                data[li].uv = (u / ru + ou, (v - ov) / rv)


def compute_vc(me, ao, ao_fn):
    ca = me.color_attributes.get("Col") or me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
    data = ca.data
    verts = me.vertices
    loops = me.loops
    for poly in me.polygons:
        mat = me.materials[poly.material_index]
        use = mat.get("ao", True)
        for li in poly.loop_indices:
            co = verts[loops[li].vertex_index].co
            f = 1.0
            if use:
                if ao_fn is not None:
                    f = ao_fn(co, poly.normal, mat.name)
                elif ao is not None:
                    h, lo = ao
                    t = max(0.0, min(1.0, co.z / h))
                    t = t * t * (3 - 2 * t)
                    f = lo + (1 - lo) * t
            data[li].color = (f, f, f, 1.0)


# ------------------------------------------------------------------------------------------------ misc
def catenary(p0, p1, sag, n=24):
    """Points of a hanging cable from p0 to p1 with `sag` metres of drop at mid-span (parabolic approx)."""
    p0, p1 = Vector(p0), Vector(p1)
    out = []
    for k in range(n + 1):
        s = k / n
        p = p0.lerp(p1, s)
        p.z -= 4 * sag * s * (1 - s)
        out.append(p)
    return out


def rounded_rect(x0, y0, x1, y1, r, steps=6):
    """Closed polygon of a rounded rectangle (counter-clockwise)."""
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for i in range(steps + 1):
            a = math.radians(a0 + 90 * i / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def rng(seed):
    return random.Random(seed)
