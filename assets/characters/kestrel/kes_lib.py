"""Shared helpers + stage A (import / normalise / clean-up) for build_kestrel.py.

KESTREL: TRELLIS.2 image-to-3D model (seed 123) -> finished, rigged game character.
Everything runs headless in Blender 5.2 and is deterministic. Coordinates are metres, Z up, the character faces -Y,
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

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

OUT = r"F:/git/val etf/assets/characters/kestrel"
SRC = OUT + "/trellis/kestrel_trellis_s123.glb"
WORK = OUT + "/_work"
TEX = OUT + "/textures"
RENDERS = OUT + "/renders"
HEIGHT = 1.70
TEX_SIZE = 2048
DECIMATE_TO = 66000   # style-guide hard max for a character is 70k; the eyepiece adds ~1k

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
    t = np.clip((np.asarray(x, dtype=np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def activate(obj):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
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
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


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


def edge_array(me):
    e = np.zeros(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# colour classes (sRGB 0..1)
def is_skin(c):
    return c[0] > 0.6 and c[0] - c[2] > 0.3


def is_hair_col(c):
    return (c[2] - c[0] > 0.05) and c.mean() < 0.32


def hair_mask_np(c):
    """Vectorised hair test: blue-black (blue >= red) and dark, or clearly navy."""
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    lum = c[..., :3].mean(-1)
    return ((b - r > 0.03) & (lum < 0.34)) | ((b >= r - 0.005) & (lum < 0.11))


def skin_mask_np(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    return (r > 0.55) & (r - b > 0.25) & (r > g)


# The face's symmetry plane is not exactly X=0: the nose ridge sits at x~+5 mm and the head is turned ~2 deg
# (measured from front-depth profiles of the cheeks). Mirror across that plane.
FACE_MID = Vector((0.005, -0.05, 0.0))
_phi = math.radians(-2.0)
FACE_N = Vector((math.cos(_phi), math.sin(_phi), 0.0))


def face_mirror(p):
    p = Vector(p)
    d = (p - FACE_MID).dot(FACE_N)
    return p - 2.0 * d * FACE_N


def face_mirror_np(P):
    """Vectorised face_mirror for an (..., 3) array."""
    m = np.array(FACE_MID[:])
    n = np.array(FACE_N[:])
    d = ((P - m) * n).sum(-1, keepdims=True)
    return P - 2.0 * d * n


# ================================================================================================ STAGE A
def stage_a_import_clean(decimate_to=DECIMATE_TO):
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
            for lk in n.outputs["Color"].links:
                tgt = lk.to_node
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

    # ---- weld (TRELLIS splits every UV chart), loose bits
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
    fill_holes(obj)
    smooth_face_folds(obj)
    # review fixes: rebuild her left eye area / temple from the mirrored right side, flatten the pout
    import kes_geo
    if not os.environ.get("KES_DEV_RAW_FACE"):          # development switch: keep the raw TRELLIS face
        kes_geo.rebuild_left_eye(obj)
        kes_geo.smooth_patch_rim(obj)
        kes_geo.flatten_lips(obj)
    log(f"boundary edges after the face rebuild: {count_boundary(obj)}")
    # the inner shell's hole under the new eye patch stays open (inside the head, never seen): a flat fill of it
    # would cut through the patch
    fill_holes(obj, skip=None if os.environ.get("KES_DEV_RAW_FACE") else kes_geo.under_patch)

    # shading: drop TRELLIS custom normals, smooth with a generous auto-smooth angle
    if me.has_custom_normals:
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for a in ("sharp_face", "sharp_edge"):
        if a in me.attributes:
            me.attributes.remove(me.attributes[a])
    bc.shade_smooth(obj, 70)

    if decimate_to:
        decimate(obj, decimate_to)
    me = obj.data
    me.validate(clean_customdata=False)
    log(f"stage A done: {len(me.vertices)} verts, {tri_count(obj)} tris")
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


# The baked lens disc over her left eye (a ~5 mm thin shell standing 6-12 mm proud of the eye area). It is kept as
# the eye surface seen through the new glass lens; the eyepiece frame encloses its rim (see kes_eyepiece.py).
LENS_C = (0.052, 1.512)
LENS_R = (0.032, 0.027)


def orient_like_neighbours(new_faces):
    """Flip new faces whose winding disagrees with the faces they border (no global recalc: the TRELLIS shell is
    non-manifold and a global recalc can flip whole regions)."""
    newset = set(new_faces)
    for _ in range(6):
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


def fill_holes(obj, skip=None):
    """Close every open boundary (wire-arm attachment holes on the left temple, TRELLIS pin-holes). Each connected
    boundary is triangulated with a beauty fill. The new faces take the UV of one texel of the surrounding surface
    (flat colour, no texture space) and their winding from their neighbours."""
    me = obj.data
    px = img_to_np(base_image())
    ph, pw = px.shape[:2]
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uvl = bm.loops.layers.uv.active
    nb = [e for e in bm.edges if e.is_boundary]
    # connected groups of boundary edges
    groups, seen = [], set()
    for e0 in nb:
        if e0 in seen:
            continue
        grp, stack = [], [e0]
        seen.add(e0)
        while stack:
            e = stack.pop()
            grp.append(e)
            for v in e.verts:
                for e2 in v.link_edges:
                    if e2.is_boundary and e2 not in seen:
                        seen.add(e2)
                        stack.append(e2)
        groups.append(grp)
    newf = []
    for grp in groups:
        if len(grp) > 300:
            continue
        if skip is not None and skip(np.array([v.co[:] for e in grp for v in e.verts])):
            continue
        verts = {v for e in grp for v in e.verts}
        nrm = sum((v.normal for v in verts), Vector()).normalized()
        # UV of one old loop on the boundary: prefer a skin texel (the holes are on the face), else the vertex
        # nearest to the hole centre
        c = sum((v.co for v in verts), Vector()) / len(verts)
        cand = sorted(verts, key=lambda v: (v.co - c).length)
        uv = None
        for v in cand:
            for lp in v.link_loops:
                u = lp[uvl].uv
                col = px[min(int(u.y * ph), ph - 1), min(int(u.x * pw), pw - 1), :3]
                if is_skin(col):
                    uv = u.copy()
                    break
            if uv is not None:
                break
        if uv is None:
            uv = cand[0].link_loops[0][uvl].uv.copy() if cand[0].link_loops else Vector((0.5, 0.5))
        res = bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=grp, normal=nrm)
        fs = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
        if not fs:
            # non-simple boundary (figure-8 / dangling chain): fan-fill to a centre vertex, winding taken from
            # each edge's existing face
            cv = bm.verts.new(c)
            for e in grp:
                if not e.is_boundary or not e.link_faces:
                    continue
                f0 = e.link_faces[0]
                lp = next(q for q in f0.loops if q.edge is e)
                a, b = lp.vert, lp.link_loop_next.vert
                try:
                    fs.append(bm.faces.new((b, a, cv)))
                except ValueError:
                    pass
        for f in fs:
            f.smooth = True
            for lp in f.loops:
                lp[uvl].uv = uv
        newf += fs
    orient_like_neighbours(newf)
    left = [e for e in bm.edges if e.is_boundary]
    log(f"filled {len(groups)} holes with {len(newf)} faces; boundary edges left {len(left)}")
    bm.to_mesh(me)
    bm.free()


def count_boundary(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    n = sum(1 for e in bm.edges if e.is_boundary)
    bm.free()
    return n


def front_layer_mask(obj, verts_idx, tol=0.004):
    """True for vertices that are (within tol) the first surface seen from the front at their own (x, z)."""
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(obj, dg)
    co = mesh_co(obj.data)
    out = np.zeros(len(verts_idx), bool)
    for k, i in enumerate(verts_idx):
        x, y, z = co[i]
        h = bvh.ray_cast((x, -1.0, z), (0, 1, 0), 2.0)
        out[k] = h[0] is not None and y - h[0].y < tol
    return out


def smooth_heightfield(obj, center, radii, iters=30, strength=0.5):
    """Relax the front skin surface along Y only inside an ellipsoidal (x, z) region (weight falls off to the edge).
    Removes TRELLIS creases/folds without sliding texture across the face."""
    me = obj.data
    co = mesh_co(me)
    cx, cz = center
    rx, rz = radii
    d = np.hypot((co[:, 0] - cx) / rx, (co[:, 2] - cz) / rz)
    cand = np.where((d < 1.0) & (co[:, 1] < 0.0))[0]
    fl = front_layer_mask(obj, cand)
    sel = cand[fl]
    w = np.zeros(len(co))
    w[sel] = strength * (1.0 - smoothstep(0.55, 1.0, d[sel]))
    e = edge_array(me)
    y = co[:, 1].copy()
    for _ in range(iters):
        s = np.zeros(len(co))
        n = np.zeros(len(co))
        np.add.at(s, e[:, 0], y[e[:, 1]])
        np.add.at(n, e[:, 0], 1)
        np.add.at(s, e[:, 1], y[e[:, 0]])
        np.add.at(n, e[:, 1], 1)
        avg = np.where(n > 0, s / np.maximum(n, 1), y)
        y = y + w * (avg - y)
    co[:, 1] = y
    set_mesh_co(me, co)
    return len(sel)


def smooth_face_folds(obj):
    """Relax the creases TRELLIS left around the old (baked) lens on her left cheek/temple."""
    n2 = smooth_heightfield(obj, (0.062, 1.495), (0.030, 0.040), iters=25, strength=0.45)
    log(f"face creases relaxed: {n2} verts")


def decimate(obj, target_tris):
    me = obj.data
    tris = tri_count(obj)
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
    log(f"decimate {tris} -> {tri_count(obj)} tris")


# ================================================================================================== work files
def save_work(name):
    os.makedirs(WORK, exist_ok=True)
    p = os.path.join(WORK, name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=p, compress=False)
    log("saved", p)


def load_work(name):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, name + ".blend"))
