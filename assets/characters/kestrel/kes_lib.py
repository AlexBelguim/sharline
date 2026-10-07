"""Helpers + stages for build_kestrel.py (KESTREL, TRELLIS.2 s123 -> finished rigged character).

Everything here is deterministic and runs headless in Blender 5.2. Coordinates are metres, Z up, character faces -Y,
her LEFT is +X. Colour values used for texture edits are sRGB-encoded 0..1 (what the 8-bit textures store).
"""
import math
import os
import sys
import time

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

OUT = r"F:/git/val etf/assets/characters/kestrel"
SRC = OUT + "/trellis/kestrel_trellis_s123.glb"
WORK = OUT + "/_work"
TEX = OUT + "/textures"
RENDERS = OUT + "/renders"
HEIGHT = 1.70
TEX_SIZE = 2048

T0 = time.time()


def log(*a):
    print(f"[kes {time.time() - T0:7.1f}s]", *a, flush=True)


# ============================================================================================ small utils
def mesh_co(me):
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def set_mesh_co(me, co):
    me.vertices.foreach_set("co", np.asarray(co, dtype=np.float64).ravel())
    me.update()


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def activate(obj):
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def body():
    return bpy.data.objects["KES_Body"]


def base_image():
    return bpy.data.images["KES_BaseColor_src"]


def img_to_np(img):
    w, h = img.size
    return np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)


def np_to_img(name, arr, colorspace="sRGB", is_float=False):
    h, w = arr.shape[:2]
    img = bpy.data.images.get(name)
    if img is None or tuple(img.size) != (w, h):
        if img:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, w, h, alpha=True, float_buffer=is_float)
    img.colorspace_settings.name = colorspace
    a = arr
    if a.shape[2] == 3:
        a = np.concatenate([a, np.ones((h, w, 1), np.float32)], axis=2)
    img.pixels.foreach_set(a.astype(np.float32).ravel())
    img.update()
    return img


def save_png(img, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    return path


def vertex_colors_from_texture(me, px):
    """Average texture colour per vertex (samples each loop's UV)."""
    h, w = px.shape[:2]
    nl = len(me.loops)
    lv = np.zeros(nl, dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.zeros(nl * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    ix = np.clip((uv[:, 0] * w).astype(int), 0, w - 1)
    iy = np.clip((uv[:, 1] * h).astype(int), 0, h - 1)
    lc = px[iy, ix, :3]
    vc = np.zeros((len(me.vertices), 3))
    cnt = np.zeros(len(me.vertices))
    np.add.at(vc, lv, lc)
    np.add.at(cnt, lv, 1)
    return vc / np.maximum(cnt, 1)[:, None]


def islands(bm):
    bm.verts.ensure_lookup_table()
    seen = np.zeros(len(bm.verts), bool)
    out = []
    for v in bm.verts:
        if seen[v.index]:
            continue
        stack = [v]
        seen[v.index] = True
        isl = []
        while stack:
            a = stack.pop()
            isl.append(a.index)
            for e in a.link_edges:
                b = e.other_vert(a)
                if not seen[b.index]:
                    seen[b.index] = True
                    stack.append(b)
        out.append(isl)
    return out


# ================================================================================================ STAGE A
def stage_a_import_clean(decimate_to=66000):
    bc.reset_scene()
    bpy.ops.import_scene.gltf(filepath=SRC)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    assert len(meshes) == 1, meshes
    obj = meshes[0]
    # bake any object transform into the mesh, drop glTF helper parents
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.data.transform(mw)
    for o in list(bpy.context.scene.objects):
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.name = obj.data.name = "KES_Body"
    me = obj.data
    mat = me.materials[0]
    mat.name = "_trellis_src"
    # keep the source textures by role
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            for l in n.outputs["Color"].links:
                tgt = l.to_node
                if tgt.type == "BSDF_PRINCIPLED":
                    n.image.name = "KES_BaseColor_src"
                elif tgt.type == "NORMAL_MAP":
                    n.image.name = "KES_Normal_src"
                elif tgt.type == "SEPARATE_COLOR":
                    n.image.name = "KES_ORM_src"
    for nm in ("KES_BaseColor_src", "KES_Normal_src", "KES_ORM_src"):
        assert bpy.data.images.get(nm), nm
        bpy.data.images[nm].pack()

    # ---- normalise: 1.70 m, feet on Z=0, centred (X: bbox, Y: pelvis), facing -Y (TRELLIS already faces -Y)
    co = mesh_co(me)
    s = HEIGHT / (co[:, 2].max() - co[:, 2].min())
    co *= s
    co[:, 2] -= co[:, 2].min()
    co[:, 0] -= (co[:, 0].min() + co[:, 0].max()) / 2
    set_mesh_co(me, co)
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(obj, dg)
    yf = bvh.ray_cast((0, -2, 0.86), (0, 1, 0), 4)[0].y
    yb = bvh.ray_cast((0, 2, 0.86), (0, -1, 0), 4)[0].y
    co[:, 1] -= (yf + yb) / 2
    set_mesh_co(me, co)
    log(f"normalised: scale {s:.4f}, pelvis front/back y {yf:.3f}/{yb:.3f}")

    # ---- weld (TRELLIS splits every UV chart), loose bits, holes
    bm = bmesh.new()
    bm.from_mesh(me)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0002)
    log(f"weld {n0} -> {len(bm.verts)} verts")
    isl = islands(bm)
    bm.verts.ensure_lookup_table()
    kill = []
    for i in isl:
        pts = np.array([bm.verts[j].co[:] for j in i])
        if len(i) < 30 or np.linalg.norm(pts.max(0) - pts.min(0)) < 0.015:
            kill += [bm.verts[j] for j in i]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    log(f"islands {len(isl)}, removed {len(kill)} verts of tiny loose bits")
    bm.to_mesh(me)
    bm.free()

    remove_wire_arm(obj)
    if os.environ.get("KES_DEBUG"):
        me.materials.append(bc.material("_dbg_red", (1, 0, 0)))
        me.materials.append(bc.material("_dbg_green", (0, 1, 0)))
    if "--no-flatten" not in sys.argv:
        rebuild_left_eye(obj)

    fill_holes(obj)
    # shading: drop TRELLIS custom normals, smooth with a generous auto-smooth angle
    if me.has_custom_normals:
        bpy.context.view_layer.objects.active = obj
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for a in ("sharp_face", "sharp_edge"):
        if a in me.attributes:
            me.attributes.remove(me.attributes[a])
    bc.shade_smooth(obj, 70)

    if decimate_to and "--no-decimate" not in sys.argv:
        decimate(obj, decimate_to)
    me = obj.data
    me.validate(clean_customdata=False)
    log(f"stage A done: {len(me.vertices)} verts, {sum(len(p.vertices) - 2 for p in me.polygons)} tris")
    return obj


def remove_wire_arm(obj):
    """TRELLIS turned the eyepiece arm into a thin open wire loop sticking out of the left temple. Delete it (the
    new strap + earpiece replace it). Selection = dark neutral-grey, thin geometry in a box at the left temple,
    flood-filled through same-coloured neighbours."""
    me = obj.data
    px = img_to_np(base_image())
    vc = vertex_colors_from_texture(me, px)
    co = mesh_co(me)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    bvh = BVHTree.FromBMesh(bm)
    r, g, b = vc.T
    lum = vc.mean(1)
    grey = (np.abs(r - b) < 0.06) & (np.abs(r - g) < 0.05) & (lum > 0.06) & (lum < 0.30)
    box = (co[:, 0] > 0.072) & (co[:, 1] > -0.08) & (co[:, 1] < 0.035) & (co[:, 2] > 1.485) & (co[:, 2] < 1.548)
    seed = []
    for i in np.where(box & grey)[0]:
        v = bm.verts[i]
        n = v.normal
        hit = bvh.ray_cast(v.co - n * 0.0003, -n, 0.05)
        th = hit[3] if hit[0] else 0.05
        if th < 0.0075:
            seed.append(i)
    sel = set(seed)
    stack = list(seed)
    while stack:
        a = bm.verts[stack.pop()]
        for e in a.link_edges:
            bv = e.other_vert(a)
            j = bv.index
            if j not in sel and box[j] and grey[j]:
                sel.add(j)
                stack.append(j)
    log(f"wire arm: {len(seed)} seeds -> {len(sel)} verts deleted")
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in sel], context="VERTS")
    # remove any dangling scraps left behind near the temple
    isl = islands(bm)
    bm.verts.ensure_lookup_table()
    scraps = [bm.verts[j] for i in isl if len(i) < 60 for j in i]
    if scraps:
        bmesh.ops.delete(bm, geom=scraps, context="VERTS")
        log(f"wire arm: removed {len(scraps)} scrap verts")
    bm.to_mesh(me)
    bm.free()


EYE_C = np.array([0.047, 1.523])   # (x, z) of her LEFT eye (= mirror of the right eye), front projection
EYE_DEL_R = np.array([0.047, 0.042])  # region cut on the left (baked lens bulge, rim, wire remains)
EYE_SRC_R = np.array([0.037, 0.035])  # region copied (mirrored) from her right eye
# The face's symmetry plane is not exactly X=0: the nose ridge sits at x~+5 mm and the head is turned ~2 deg
# (measured from front-depth profiles of the cheeks). Mirror across that plane.
FACE_MID = Vector((0.005, -0.05, 0.0))
_phi = math.radians(-2.0)
FACE_N = Vector((math.cos(_phi), math.sin(_phi), 0.0))


def face_mirror(p):
    p = Vector(p)
    d = (p - FACE_MID).dot(FACE_N)
    return p - 2.0 * d * FACE_N


def face_depth(bvh, x, z):
    """Y of the first surface seen from INSIDE the head (ray from y=0 toward -Y). The TRELLIS head is a hollow
    shell ~1-2 cm thick, so this is the back side of the face shell (or the face itself near the temples)."""
    hit = bvh.ray_cast((x, 0.0, z), (0, -1, 0), 0.25)
    return hit[0].y if hit[0] else None


def is_skin(c):
    return c[0] > 0.6 and c[0] - c[2] > 0.3


def is_hair_col(c):
    return (c[2] - c[0] > 0.05) and c.mean() < 0.32


def find_skin_uv(bm, vcol, near):
    """UV of a clean skin texel: the skin-coloured, front-facing vertex closest to `near` whose texel (and its 5x5
    neighbourhood) really is skin in the source texture."""
    uvl = bm.loops.layers.uv.active
    px = img_to_np(base_image())
    h, w = px.shape[:2]
    cands = []
    for v in bm.verts:
        if v.index < len(vcol) and is_skin(vcol[v.index]) and v.normal.y < -0.3 and v.link_loops:
            cands.append(((v.co - Vector(near)).length, v))
    cands.sort(key=lambda t: t[0])
    for _, v in cands[:400]:
        for lp in v.link_loops:
            uv = lp[uvl].uv
            x, y = int(uv.x * w), int(uv.y * h)
            blk = px[max(y - 2, 0):y + 3, max(x - 2, 0):x + 3, :3].reshape(-1, 3)
            if len(blk) == 25 and all(is_skin(c) for c in blk):
                return uv.copy()
    raise RuntimeError("no clean skin texel found")


def orient_like_neighbours(new_faces):
    """Flip new faces whose winding disagrees with the faces they border (no global recalc: the TRELLIS shell is
    non-manifold and a global recalc can flip whole regions)."""
    newset = set(new_faces)
    for _ in range(4):
        for f in new_faces:
            if not f.is_valid:
                continue
            votes = 0.0
            for lp in f.loops:
                e = lp.edge
                for g in e.link_faces:
                    if g is f:
                        continue
                    glp = next((q for q in g.loops if q.edge is e), None)
                    if glp is None:
                        continue
                    w = 1.0 if g not in newset else 0.3
                    # consistent winding: the shared edge is walked in opposite directions
                    votes += -w if glp.vert is lp.vert else w
            if votes < 0:
                f.normal_flip()


def rebuild_left_eye(obj):
    """TRELLIS baked the eyepiece as an opaque grey bulge with a rim wall and layered shards over her left eye. Cut the
    whole left eye area out (both layers of the face shell) and replace it with a mirrored copy of her right eye area
    (geometry AND UVs, so the left eye shows the mirrored right-eye texture), then zip the gap with a ring of skin."""
    me = obj.data
    vcol = vertex_colors_from_texture(me, img_to_np(base_image()))
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = bm.faces.layers.int.get("kes_patch") or bm.faces.layers.int.new("kes_patch")
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    uvl = bm.loops.layers.uv.active
    bvh = BVHTree.FromBMesh(bm)
    src_c = face_mirror((EYE_C[0], -0.04, EYE_C[1]))

    def ell_l(co):
        return math.hypot((co.x - EYE_C[0]) / EYE_DEL_R[0], (co.z - EYE_C[1]) / EYE_DEL_R[1])

    def ell_r(co):
        return math.hypot((co.x - src_c.x) / EYE_SRC_R[0], (co.z - src_c.z) / EYE_SRC_R[1])

    def face_hair(f):
        return is_hair_col(np.mean([vcol[v.index] for v in f.verts], axis=0))

    # ---- source: first NON-HAIR front-facing surface seen from the front (the fringe hangs in front of the outer
    #      corner of her right eye), closed morphologically so eyelid creases are included
    src = set()
    for f in bm.faces:
        cc = f.calc_center_median()
        if cc.x >= 0 or ell_r(cc) >= 1.0:
            continue
        org = Vector((cc.x, -0.4, cc.z))
        for _ in range(6):
            hit = bvh.ray_cast(org, Vector((0, 1, 0)), 1.0)
            if hit[0] is None:
                break
            hf = bm.faces[hit[2]]
            if face_hair(hf):
                org = hit[0] + Vector((0, 0.0003, 0))
                continue
            if hf is f and f.normal.y < -0.1:
                src.add(f)
            break
    for _ in range(3):
        add = [f for f in bm.faces if f not in src and f.normal.y < 0.35 and ell_r(f.calc_center_median()) < 1.0
               and sum(1 for e in f.edges for g in e.link_faces if g is not f and g in src) >= 2]
        src.update(add)
    # reject strands of the fringe that hang in front of the face: fit a smooth depth surface y(x, z) to the source
    # face centres and drop faces more than 10 mm in front of it
    for _ in range(3):
        fl = list(src)
        C = np.array([f.calc_center_median()[:] for f in fl])
        A = np.c_[np.ones(len(C)), C[:, 0], C[:, 2], C[:, 0] ** 2, C[:, 2] ** 2, C[:, 0] * C[:, 2]]
        coef, *_ = np.linalg.lstsq(A, C[:, 1], rcond=None)
        res = C[:, 1] - A @ coef
        src = {f for f, r in zip(fl, res) if r > -0.010}
    src_faces = list(src)
    # ---- cut on the left: both shell layers + everything stuck in front (lens disc, rim walls, wire remains)
    dele = []
    for v in bm.verts:
        if v.co.x > 0.0 and ell_l(v.co + Vector((-0.003, 0, 0))) < 1.0:
            m = face_mirror(v.co)
            ty = face_depth(bvh, m.x, m.z)
            if ty is not None and -0.06 < v.co.y - ty < 0.005:
                dele.append(v)
    # ---- copy + mirror the source patch
    vmap = {}
    patch = []
    for f in src_faces:
        nvs = []
        for v in f.verts:
            if v.index not in vmap:
                vmap[v.index] = bm.verts.new(face_mirror(v.co))
            nvs.append(vmap[v.index])
        uvs = [lp[uvl].uv.copy() for lp in f.loops]
        nf = bm.faces.new(list(reversed(nvs)))
        for lp, uv in zip(nf.loops, reversed(uvs)):
            lp[uvl].uv = uv
        nf.smooth = True
        patch.append(nf)
    bmesh.ops.delete(bm, geom=dele, context="VERTS")
    pverts = {v for f in patch for v in f.verts}
    isl = islands(bm)
    bm.verts.ensure_lookup_table()
    scraps = [bm.verts[j] for i in isl if len(i) < 60 for j in i if bm.verts[j] not in pverts]
    if scraps:
        bmesh.ops.delete(bm, geom=scraps, context="VERTS")
    patch = [f for f in patch if f.is_valid]
    pverts = {v for f in patch for v in f.verts}
    # ---- zip the front-layer hole rim (outer) to the patch rim (inner)
    loops = boundary_loops([e for e in bm.edges if e.is_boundary and all(ell_l(v.co) < 1.8 for v in e.verts)])
    inner = max([lp for lp in loops if all(v in pverts for v in lp)], key=len)
    py = float(np.mean([v.co.y for v in inner]))
    cands = [lp for lp in loops if not any(v in pverts for v in lp) and len(lp) > 8]
    # front layer = the big loop closest in depth to the patch rim (the back-layer loop sits ~1-2 cm behind)
    outer = min(cands, key=lambda lp: abs(float(np.mean([v.co.y for v in lp])) - py) - 0.0004 * len(lp))
    ring = zip_loops(bm, outer, inner, EYE_C)
    for f in ring:
        f.normal_update()
        if f.normal.y > 0:
            f.normal_flip()
    for f in patch:
        f.normal_update()
    pf = sum(1 for f in patch if f.normal.y < 0)
    skin_uv = find_skin_uv(bm, vcol, (0.05, -0.045, 1.47))
    for f in ring:
        f.smooth = True
        for lp in f.loops:
            lp[uvl].uv = skin_uv
    for f in patch:
        f[lay] = 1
    for f in ring:
        f[lay] = 2
    if os.environ.get("KES_DEBUG"):
        for f in patch:
            f.material_index = 1
        for f in ring:
            f.material_index = 2
    bm.to_mesh(me)
    bm.free()
    log(f"left eye rebuilt: {len(src_faces)} mirrored faces ({pf} facing front), {len(dele)} verts cut, "
        f"ring {len(ring)} faces (loops {len(loops)}: outer {len(outer)} / inner {len(inner)} verts)")


def boundary_loops(edges):
    """Group boundary edges into ordered vertex loops (open chains are returned too)."""
    es = set(edges)
    adj = {}
    for e in es:
        for v in e.verts:
            adj.setdefault(v, []).append(e)
    loops = []
    used = set()
    for e0 in es:
        if e0 in used:
            continue
        used.add(e0)
        chain = [e0.verts[0], e0.verts[1]]
        while True:
            v = chain[-1]
            nxt = [e for e in adj.get(v, []) if e not in used]
            if not nxt:
                break
            e = nxt[0]
            used.add(e)
            w = e.other_vert(v)
            if w is chain[0]:
                break
            chain.append(w)
        loops.append(chain)
    return loops


def zip_loops(bm, outer, inner, c2):
    """Triangulate the band between two loops (front projection, ordered by angle around c2=(x,z))."""
    def ang(v):
        return math.atan2(v.co.z - c2[1], v.co.x - c2[0])

    def orient(lp):
        a = 0.0
        for i in range(len(lp)):
            p, q = lp[i].co, lp[(i + 1) % len(lp)].co
            a += (p.x - c2[0]) * (q.z - c2[1]) - (q.x - c2[0]) * (p.z - c2[1])
        lp = lp if a > 0 else list(reversed(lp))
        k = min(range(len(lp)), key=lambda i: abs(ang(lp[i])))
        lp = lp[k:] + lp[:k]
        out, prev, off = [], None, 0.0
        for v in lp:
            t = ang(v)
            if prev is not None:
                while t + off < prev - math.pi:
                    off += 2 * math.pi
            out.append(t + off)
            prev = t + off
        return lp, out

    O, ao = orient(outer)
    I, ai = orient(inner)
    O.append(O[0])
    ao.append(ao[0] + 2 * math.pi)
    I.append(I[0])
    ai.append(ai[0] + 2 * math.pi)
    i = j = 0
    faces = []
    while i < len(I) - 1 or j < len(O) - 1:
        adv_inner = j >= len(O) - 1 or (i < len(I) - 1 and ai[i + 1] < ao[j + 1])
        if adv_inner:
            tri = (O[j], I[i], I[i + 1])
            i += 1
        else:
            tri = (O[j], I[i], O[j + 1])
            j += 1
        if len({*tri}) == 3:
            try:
                faces.append(bm.faces.new(tri))
            except ValueError:
                pass
    return faces


def fill_holes(obj):
    """Close remaining holes (wire-arm attachment points, the back layer behind the rebuilt eye, TRELLIS pin-holes).
    New faces get their UVs pinned to one clean skin texel of the left cheek (they take no texture space) and their
    winding from their neighbours."""
    me = obj.data
    vcol = vertex_colors_from_texture(me, img_to_np(base_image()))
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uvl = bm.loops.layers.uv.active
    skin_uv = find_skin_uv(bm, vcol, (0.05, -0.045, 1.47))
    nb = [e for e in bm.edges if e.is_boundary]
    res = bmesh.ops.holes_fill(bm, edges=nb, sides=200)
    tri = bmesh.ops.triangulate(bm, faces=res["faces"])
    newf = [f for f in (tri["faces"] or res["faces"]) if f.is_valid]
    for f in newf:
        f.smooth = True
        for lp in f.loops:
            lp[uvl].uv = skin_uv
    orient_like_neighbours(newf)
    left = [e for e in bm.edges if e.is_boundary]
    log(f"filled holes with {len(newf)} faces; boundary edges left {len(left)}")
    for e in left[:12]:
        log("  open edge at", tuple(round(c, 3) for c in (e.verts[0].co + e.verts[1].co) / 2))
    bm.to_mesh(me)
    bm.free()


def decimate(obj, target_tris):
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    if tris <= target_tris:
        return
    co = mesh_co(me)
    # protect the face and hands (weight 1 = keep detail)
    vg = obj.vertex_groups.new(name="_protect")
    head = smoothstep(1.40, 1.46, co[:, 2]) * (np.abs(co[:, 0]) < 0.16)
    hands = smoothstep(0.42, 0.48, np.abs(co[:, 0])) * (co[:, 2] < 1.1)
    w = np.maximum(head, hands)
    for val in np.unique(np.round(w, 2)):
        idx = np.where(np.round(w, 2) == val)[0].tolist()
        if idx and val > 0:
            vg.add(idx, float(val), "REPLACE")
    m = obj.modifiers.new("Decimate", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = target_tris / tris
    m.vertex_group = vg.name
    m.vertex_group_factor = 4.0
    m.invert_vertex_group = True  # bmesh collapse: LOW weight = expensive = kept
    m.use_collapse_triangulate = True
    bc.apply_modifiers(obj, only=[m.name])
    if obj.vertex_groups.get("_protect"):
        obj.vertex_groups.remove(obj.vertex_groups["_protect"])
    log(f"decimate {tris} -> {sum(len(p.vertices) - 2 for p in obj.data.polygons)} tris")


# ================================================================================================ STAGE B
def _cycles(samples=1):
    sc = bpy.context.scene
    bc.setup_cycles_gpu(sc, samples)
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.bake.margin = 6
    sc.render.bake.margin_type = "EXTEND"
    sc.render.bake.use_clear = True
    sc.render.bake.target = "IMAGE_TEXTURES"
    return sc


def bake_emit(obj, build, name, size=TEX_SIZE, margin=6, float_buffer=True, patch_to_dummy=True):
    """Bake an emission shader built by build(nt) -> output socket into a new image (EMIT pass, exact values).
    Faces of the mirrored eye patch (attribute kes_patch==1) share UVs with the right eye; they are routed to a
    dummy image so the right-eye texels keep their own (right-side) values."""
    me = obj.data
    sc = _cycles(1)
    sc.render.bake.margin = margin
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=float_buffer)
    img.colorspace_settings.name = "Non-Color" if float_buffer else "sRGB"
    dummy = bpy.data.images.get("_bake_dummy") or bpy.data.images.new("_bake_dummy", 64, 64, float_buffer=True)

    def mk(nm, im):
        m = bpy.data.materials.new(nm)
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        nt.links.new(build(nt), em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = im
        nt.nodes.active = ti
        return m

    m_main = mk("_bake_main", img)
    m_dummy = mk("_bake_dummy", dummy)
    saved_mats = list(me.materials)
    idx = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", idx)
    me.materials.clear()
    me.materials.append(m_main)
    me.materials.append(m_dummy)
    flag = np.zeros(len(me.polygons), dtype=np.int32)
    if patch_to_dummy and "kes_patch" in me.attributes:
        me.attributes["kes_patch"].data.foreach_get("value", flag)
    me.polygons.foreach_set("material_index", (flag == 1).astype(np.int32))
    me.update()
    activate(obj)
    bpy.ops.object.bake(type="EMIT", margin=margin, use_clear=True)
    me.materials.clear()
    for m in saved_mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", idx)
    me.update()
    bpy.data.materials.remove(m_main)
    bpy.data.materials.remove(m_dummy)
    return img


def _geo(nt, socket):
    g = nt.nodes.new("ShaderNodeNewGeometry")
    return g.outputs[socket]


def _const(nt, rgb):
    r = nt.nodes.new("ShaderNodeRGB")
    r.outputs[0].default_value = (*rgb, 1.0)
    return r.outputs[0]


def bake_geometry_maps(obj):
    """Object-space position / true-normal maps (+ coverage) for texel-space editing."""
    t = time.time()
    pos = img_to_np(bake_emit(obj, lambda nt: _geo(nt, "Position"), "_pos"))[..., :3].copy()
    nrm = img_to_np(bake_emit(obj, lambda nt: _geo(nt, "True Normal"), "_nrm"))[..., :3].copy()
    cov = img_to_np(bake_emit(obj, lambda nt: _const(nt, (1, 1, 1)), "_cov", margin=0))[..., 0] > 0.5
    log(f"baked position/normal/coverage maps in {time.time() - t:.1f}s; coverage {cov.mean():.3f}")
    return pos, nrm, cov


# ================================================================================================== main
def save_work(name):
    os.makedirs(WORK, exist_ok=True)
    p = os.path.join(WORK, name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=p, compress=False)
    log("saved", p)


def load_work(name):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, name + ".blend"))


def main(argv):
    start = "A"
    stop = "Z"
    if "--from" in argv:
        start = argv[argv.index("--from") + 1]
    if "--to" in argv:
        stop = argv[argv.index("--to") + 1]
    if start <= "A" <= stop:
        stage_a_import_clean()
        save_work("A")
    if start <= "B" <= stop:
        if start == "B":
            load_work("A")
        obj = body()
        pos, nrm, cov = bake_geometry_maps(obj)
        base = img_to_np(base_image())
        np.savez_compressed(os.path.join(WORK, "maps.npz"), pos=pos, nrm=nrm, cov=cov, base=base)
        log("dumped maps")
    log("finished")
