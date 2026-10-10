"""Shared helpers + stage A (import / clean / back carve) for build_solace.py.

SOLACE: TRELLIS.2 seed 42 -> finished rigged character. Deterministic, headless Blender 5.2.
Metres, Z up, the character faces -Y, her LEFT is +X, her RIGHT is -X.
Texture edits work on sRGB-encoded 0..1 values (what the 8-bit textures store).
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

OUT = r"F:/git/val etf/assets/characters/solace"
SRC = OUT + "/trellis/solace_trellis_s42.glb"
WORK = OUT + "/_work"
TEX = OUT + "/textures"
RENDERS = OUT + "/renders"
DIAG = WORK + "/diag"            # scratch diagnostics (git-ignored)
HEIGHT = 1.68
BODY_TRIS = 60000          # decimation target for the TRELLIS body (module/emblem/drone come on top)
T0 = time.time()


def log(*a):
    print(f"[sol {time.time() - T0:7.1f}s]", *a, flush=True)


# ============================================================================================ small utils
def mesh_co(me):
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def set_mesh_co(me, co):
    me.vertices.foreach_set("co", np.asarray(co, dtype=np.float64).ravel())
    me.update()


def face_centres(me):
    c = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("center", c)
    return c.reshape(-1, 3)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, dtype=float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def activate(obj):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def body():
    return bpy.data.objects["SOL_Body"]


def tris_of(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


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


def img_to_np(img):
    w, h = img.size
    return np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)


def np_to_img(name, arr, colorspace="sRGB", is_float=False):
    h, w = arr.shape[:2]
    img = bpy.data.images.get(name)
    if img is None or tuple(img.size) != (w, h) or img.is_float != is_float:
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


def loop_uvs(me):
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    return uv.reshape(-1, 2)


def vertex_colors_from_texture(me, px):
    """Average texture colour per vertex (samples each loop's UV)."""
    h, w = px.shape[:2]
    lv = np.zeros(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv = loop_uvs(me)
    ix = np.clip((uv[:, 0] * w).astype(int), 0, w - 1)
    iy = np.clip((uv[:, 1] * h).astype(int), 0, h - 1)
    lc = px[iy, ix, :3]
    vc = np.zeros((len(me.vertices), 3))
    cnt = np.zeros(len(me.vertices))
    np.add.at(vc, lv, lc)
    np.add.at(cnt, lv, 1)
    return vc / np.maximum(cnt, 1)[:, None]


def save_work(name):
    os.makedirs(WORK, exist_ok=True)
    p = os.path.join(WORK, name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=p, compress=False)
    log("saved", p)


def load_work(name):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, name + ".blend"))


# ============================================================================================ diagnostics
def _cam(scene):
    cam = bpy.data.objects.get("_DiagCam")
    if cam is None:
        cam = bpy.data.objects.new("_DiagCam", bpy.data.cameras.new("_DiagCam"))
        scene.collection.objects.link(cam)
    scene.camera = cam
    return cam


DIRS = dict(bc.VIEW_DIRS)
DIRS.update({"head_front": (0, -1, 0.02), "head_tq": (0.9, -1, 0.15), "head_tq_r": (-0.9, -1, 0.15),
             "back_high": (0, 1, 0.45), "tq_r": (-0.75, -1, 0.35), "side_l": (1, 0, 0.05), "side_r": (-1, 0, 0.05)})


def shoot(prefix, views, center, radius, out_dir=DIAG, engine="WB", res=(700, 900), lens=60, samples=24,
          color_type="TEXTURE", hide=()):
    """Render views around center (frames a sphere of radius). engine 'WB' (workbench, instant), 'CYC'."""
    sc = bpy.context.scene
    os.makedirs(out_dir, exist_ok=True)
    hidden = []
    for o in sc.objects:
        if o.type == "MESH" and (o.name.startswith("_") or any(o.name.startswith(h) for h in hide)) \
                and not o.hide_render:
            o.hide_render = True
            hidden.append(o)
    if engine == "WB":
        sc.render.engine = "BLENDER_WORKBENCH"
        sh = sc.display.shading
        sh.light = "STUDIO"
        sh.color_type = color_type
        sh.show_cavity = False
        sc.display_settings.display_device = "sRGB"
        sc.view_settings.view_transform = "Standard"
    else:
        if not bpy.data.objects.get("L_Key"):
            bc.setup_studio()
        bc.setup_cycles_gpu(sc, samples)
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        try:
            sc.view_settings.view_transform = "AgX"
            sc.view_settings.look = "AgX - Medium High Contrast"
        except Exception:
            pass
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    cam = _cam(sc)
    cam.data.lens = lens
    cam.data.clip_start = 0.01
    fov = 2 * math.atan(cam.data.sensor_width / (2 * lens) * min(1.0, res[1] / res[0]))
    dist = radius / math.sin(fov / 2)
    paths = []
    c = Vector(center)
    for v in views:
        d = Vector(DIRS[v] if isinstance(v, str) else v).normalized()
        cam.location = c + d * dist
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        name = v if isinstance(v, str) else "v" + "_".join(str(round(x, 2)) for x in v)
        p = os.path.join(out_dir, f"{prefix}_{name}.png")
        sc.render.filepath = p
        try:
            bpy.ops.render.render(write_still=True)
        except RuntimeError as e:
            print("render failed, retrying on CPU:", e)
            sc.cycles.device = "CPU"
            bpy.ops.render.render(write_still=True)
        paths.append(p)
    for o in hidden:
        o.hide_render = False
    log("shot", prefix, len(paths), "views")
    return paths


def sheet(paths, out, cols=None):
    """Contact sheet from same-size PNGs (numpy via Blender images)."""
    imgs = [bpy.data.images.load(p, check_existing=False) for p in paths]
    w, h = imgs[0].size
    cols = cols or len(imgs)
    rows = math.ceil(len(imgs) / cols)
    buf = np.zeros((h * rows, w * cols, 4), dtype=np.float32)
    for i, im in enumerate(imgs):
        px = np.array(im.pixels[:], dtype=np.float32).reshape(im.size[1], im.size[0], 4)
        if px.shape[:2] != (h, w):
            continue
        r, c = divmod(i, cols)
        y0 = (rows - 1 - r) * h
        buf[y0:y0 + h, c * w:(c + 1) * w] = px
    s = bpy.data.images.new("_sheet", w * cols, h * rows)
    s.pixels.foreach_set(buf.ravel())
    s.filepath_raw = out
    s.file_format = "PNG"
    s.save()
    for im in imgs:
        bpy.data.images.remove(im)
    bpy.data.images.remove(s)
    return out


def debug_colors(obj, face_rgb, name="dbg"):
    """Show per-face colours (N x 3 array, sRGB 0..1) as a corner colour attribute for workbench ATTRIBUTE mode."""
    me = obj.data
    if name in me.color_attributes:
        me.color_attributes.remove(me.color_attributes[name])
    ca = me.color_attributes.new(name, "BYTE_COLOR", "CORNER")
    tot = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", tot)
    lc = np.repeat(np.asarray(face_rgb, np.float32), tot, axis=0)
    lc = np.c_[lc, np.ones(len(lc), np.float32)]
    ca.data.foreach_set("color_srgb", lc.ravel())
    me.color_attributes.active_color = ca
    me.attributes.active_color = ca
    return ca


def face_tex_colors(me, px):
    """Texture colour at each face's first loop UV centroid (sRGB 0..1)."""
    h, w = px.shape[:2]
    uv = loop_uvs(me)
    ls = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    tot = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", tot)
    cu = np.add.reduceat(uv, ls, axis=0) / tot[:, None]
    ix = np.clip((cu[:, 0] * w).astype(int), 0, w - 1)
    iy = np.clip((cu[:, 1] * h).astype(int), 0, h - 1)
    return px[iy, ix, :3]


# ================================================================================================ STAGE A
def import_trellis():
    bc.reset_scene()
    bpy.ops.import_scene.gltf(filepath=SRC)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    assert len(meshes) == 1, meshes
    obj = meshes[0]
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.data.transform(mw)
    for o in list(bpy.context.scene.objects):
        if o is not obj:
            bpy.data.objects.remove(o, do_unlink=True)
    obj.name = obj.data.name = "SOL_Body"
    me = obj.data
    mat = me.materials[0]
    mat.name = "_trellis_src"
    for n in mat.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            for lk in n.outputs["Color"].links:
                tgt = lk.to_node
                if tgt.type == "BSDF_PRINCIPLED":
                    n.image.name = "SOL_BaseColor_src"
                elif tgt.type == "NORMAL_MAP":
                    n.image.name = "SOL_Normal_src"
                elif tgt.type == "SEPARATE_COLOR":
                    n.image.name = "SOL_ORM_src"
    for nm in ("SOL_BaseColor_src", "SOL_Normal_src", "SOL_ORM_src"):
        assert bpy.data.images.get(nm), nm
        bpy.data.images[nm].pack()
    return obj


def normalise(obj):
    """1.68 m tall (bounding box, hair included), feet on Z=0, X centred on the (symmetric) A-pose bbox,
    Y centred on the torso midline at the lower chest (front/back rays at Z 1.10)."""
    me = obj.data
    co = mesh_co(me)
    s = HEIGHT / (co[:, 2].max() - co[:, 2].min())
    co *= s
    co[:, 2] -= co[:, 2].min()
    co[:, 0] -= (co[:, 0].min() + co[:, 0].max()) / 2
    set_mesh_co(me, co)
    bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    yf = bvh.ray_cast((0, -2, 1.10), (0, 1, 0), 4)[0].y
    yb = bvh.ray_cast((0, 2, 1.10), (0, -1, 0), 4)[0].y
    co[:, 1] -= (yf + yb) / 2
    set_mesh_co(me, co)
    log(f"normalised: scale {s:.4f}, chest front/back y {yf:.3f}/{yb:.3f} -> shift {-(yf + yb) / 2:.3f}")


def weld_and_drop_bits(obj, dist=0.0002, min_verts=30, min_size=0.015):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=dist)
    isl = islands(bm)
    bm.verts.ensure_lookup_table()
    kill = []
    for i in isl:
        pts = np.array([bm.verts[j].co[:] for j in i])
        if len(i) < min_verts or np.linalg.norm(pts.max(0) - pts.min(0)) < min_size:
            kill += [bm.verts[j] for j in i]
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    log(f"weld {n0} -> {len(bm.verts) + len(kill)} verts; {len(isl)} islands, removed {len(kill)} verts of tiny bits")
    bm.to_mesh(me)
    bm.free()


def clear_custom_normals(obj):
    me = obj.data
    if me.has_custom_normals:
        activate(obj)
        with bpy.context.temp_override(object=obj, active_object=obj):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for a in ("sharp_face", "sharp_edge"):
        if a in me.attributes:
            me.attributes.remove(me.attributes[a])


# -------------------------------------------------------------------------- the hallucinated backpack + fins
def backpack_face_mask(centres):
    """Faces to carve out of the upper back: the TRELLIS box backpack, the garbage-textured coat surface it hid
    (with a hole under the collar and the box's front-wall sheet at Y~0.127), the strap across the back at the box
    bottom, and the two shoulder fins (thin plates above the shoulder line, white in front, dark behind)."""
    x, y, z = centres.T
    ax = np.abs(x)
    box = (ax < 0.150) & (z > 1.12) & (z < 1.415) & (y > 0.127)
    back = (ax < 0.145) & (z > 1.122) & (y > 0.070) & ((z < 1.418) | ((ax > 0.09) & (z < 1.47)))
    fin = (ax > 0.095) & (ax < 0.21) & (((z > 1.405) & (z < 1.47) & (y > 0.015)) |
                                       ((z > 1.33) & (z < 1.47) & (y > 0.132)))
    return box | back | fin


def hair_like(c):
    """Dark warm hair texels (vs bluish charcoal cloth)."""
    c = np.asarray(c)
    lum = c[..., :3].mean(-1)
    return (lum < 0.30) & (c[..., 0] >= c[..., 2] - 0.005)


def grid_filter(a, r, fn):
    """Flat disc min/max filter of radius r cells (NaN-free array)."""
    out = a.copy()
    h, w = a.shape
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            sh = np.full_like(a, np.nan)
            ys0, ys1 = max(0, dy), min(h, h + dy)
            xs0, xs1 = max(0, dx), min(w, w + dx)
            sh[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
            sh = np.where(np.isnan(sh), a, sh)
            out = fn(out, sh)
    return out


SH_X = np.arange(0.050, 0.290, 0.003)
SH_Y = np.arange(-0.110, 0.215, 0.003)


def shoulder_heightfields(obj, skip_faces):
    """Top-surface height maps over both shoulders (rays straight down from Z 1.56, passing through hair faces and
    faces in skip_faces), and their morphological opening (removes plates thinner than ~3.6 cm: the fins)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    res = {}
    for side in (1, -1):
        H = np.full((len(SH_Y), len(SH_X)), np.nan)
        for j, yy in enumerate(SH_Y):
            for i, xx in enumerate(SH_X):
                org = Vector((side * xx, yy, 1.56))
                for _ in range(12):
                    hit = bvh.ray_cast(org, Vector((0, 0, -1)), 0.4)
                    if hit[0] is None:
                        break
                    if skip_faces[hit[2]]:
                        org = hit[0] - Vector((0, 0, 0.0004))
                        continue
                    H[j, i] = hit[0].z
                    break
        Hf = np.where(np.isnan(H), 1.20, H)
        r = 6
        Ho = grid_filter(grid_filter(Hf, r, np.minimum), r, np.maximum)
        res[side] = (H, Ho)
    return res


def sample_grid(G, x, y):
    """Bilinear sample of a shoulder grid at (|x|, y) arrays."""
    fx = np.clip((np.abs(x) - SH_X[0]) / (SH_X[1] - SH_X[0]), 0, len(SH_X) - 1.001)
    fy = np.clip((y - SH_Y[0]) / (SH_Y[1] - SH_Y[0]), 0, len(SH_Y) - 1.001)
    i0 = fx.astype(int)
    j0 = fy.astype(int)
    tx = fx - i0
    ty = fy - j0
    return (G[j0, i0] * (1 - tx) * (1 - ty) + G[j0, i0 + 1] * tx * (1 - ty) + G[j0 + 1, i0] * (1 - tx) * ty
            + G[j0 + 1, i0 + 1] * tx * ty)


# -------------------------------------------------------------------------- hidden inner sheet culling
def fib_dirs(n, zmin=-1.0, zmax=1.0):
    out = []
    ga = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        zz = zmax - (zmax - zmin) * (i + 0.5) / n
        r = math.sqrt(max(0.0, 1 - zz * zz))
        out.append(Vector((r * math.cos(ga * i), r * math.sin(ga * i), zz)))
    return out


def visible_faces(obj, view_sets, res=2048):
    """Face ids seen from outside: workbench flat renders of a face-id colour attribute (6 bits per channel)
    from many orthographic views. view_sets: [(center, ortho_scale, [dirs])]."""
    me = obj.data
    nf = len(me.polygons)
    ids = np.arange(nf) + 1
    rgb = np.stack([(ids >> 12) & 63, (ids >> 6) & 63, ids & 63], 1) * 4 + 2
    debug_colors(obj, rgb / 255.0, name="_fid")
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "VERTEX"
    sh.show_specular_highlight = False
    sh.show_cavity = False
    sh.show_shadows = False
    sh.show_object_outline = False
    sh.show_backface_culling = False
    sh.show_xray = False
    sc.display.render_aa = "OFF"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0
    sc.view_settings.gamma = 1
    sc.render.dither_intensity = 0
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    cam = _cam(sc)
    cam.data.type = "ORTHO"
    cam.data.clip_start = 0.01
    cam.data.clip_end = 50
    seen = np.zeros(nf + 1, bool)
    tmp = os.path.join(WORK, "_vis.png")
    k = 0
    for center, scale, dirs in view_sets:
        cam.data.ortho_scale = scale
        c = Vector(center)
        for d in dirs:
            cam.location = c + d.normalized() * 6.0
            up = "Y" if abs(d.normalized().z) < 0.999 else "X"
            cam.rotation_euler = (c - cam.location).to_track_quat("-Z", up).to_euler()
            sc.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            im = bpy.data.images.load(tmp, check_existing=False)
            px = np.empty(res * res * 4, np.float32)
            im.pixels.foreach_get(px)
            bpy.data.images.remove(im)
            px = px.reshape(-1, 4)
            px = px[px[:, 3] > 0.5]
            q = np.clip(np.round((np.round(px[:, :3] * 255) - 2) / 4), 0, 63).astype(np.int64)
            fid = (q[:, 0] << 12) | (q[:, 1] << 6) | q[:, 2]
            seen[fid[fid <= nf]] = True
            k += 1
    me.color_attributes.remove(me.color_attributes["_fid"])
    cam.data.type = "PERSP"
    sc.render.film_transparent = False
    log(f"visibility: {k} views, {seen[1:].sum()} / {nf} faces seen")
    return seen[1:]


def cull_hidden(obj, quick=False):
    """TRELLIS.2 shells are double-walled (outer surface + an inner sheet ~3-6 mm inside). Delete every face that
    no outside view can see (plus keep a 1-ring safety band), then drop the leftover scraps."""
    n = 40 if quick else 110
    sets = [((0, 0, 0.84), 1.90, fib_dirs(n)),
            ((0, 0.02, 1.52), 0.46, fib_dirs(n // 2)),
            ((0, 0, 0.78), 0.95, fib_dirs(n // 2, -1.0, 0.3)),
            ((0.40, -0.02, 0.96), 0.36, fib_dirs(n // 3)),
            ((-0.40, -0.02, 0.96), 0.36, fib_dirs(n // 3)),
            ((0, 0.0, 0.10), 0.70, fib_dirs(n // 3, -0.6, 1.0))]
    seen = visible_faces(obj, sets)
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    keep = seen.copy()
    for _ in range(1):
        grow = keep.copy()
        for f in bm.faces:
            if keep[f.index]:
                for v in f.verts:
                    for g in v.link_faces:
                        grow[g.index] = True
        keep = grow
    kill = [f for f in bm.faces if not keep[f.index]]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    isl = islands(bm)
    bm.verts.ensure_lookup_table()
    scraps = [bm.verts[j] for i in isl if len(i) < 25 for j in i]
    bmesh.ops.delete(bm, geom=scraps, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    log(f"cull hidden: removed {len(kill)} faces + {len(scraps)} scrap verts -> {len(me.polygons)} faces")


def face_thickness(bm, bvh, idx, maxd=0.3):
    """Distance from each listed face centre to the next surface straight behind it (along -normal)."""
    th = {}
    bm.faces.ensure_lookup_table()
    for i in idx:
        f = bm.faces[i]
        n = f.normal
        c = f.calc_center_median()
        hit = bvh.ray_cast(c - n * 0.0005, -n, maxd)
        th[i] = hit[3] if hit[0] else maxd
    return th


def _face_normals(me):
    n = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", n)
    return n.reshape(-1, 3)


def patch_flags(me):
    a = me.attributes.get("sol_patch")
    out = np.zeros(len(me.polygons), np.int32)
    if a is not None:
        a.data.foreach_get("value", out)
    return out


def back_mask(obj):
    """The box backpack + the coat back panel behind/under it (rebuilt as a patch)."""
    cen = face_centres(obj.data)
    x, y, z = cen.T
    return (np.abs(x) < 0.150) & (z > 1.12) & (z < 1.418) & (y > 0.070) & (patch_flags(obj.data) == 0)


def fin_mask(obj):
    """The two shoulder fins: steep or thin (plate-like) non-hair faces above the shoulder line."""
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    fc = face_tex_colors(me, px)
    cen = face_centres(me)
    nrm = _face_normals(me)
    x, y, z = cen.T
    ax = np.abs(x)
    hair = hair_like(fc)
    free = (patch_flags(me) == 0) & ~hair
    region = (ax > 0.088) & (ax < 0.24) & (z > 1.385) & (y > -0.095) & (y < 0.22) & free
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    th = face_thickness(bm, bvh, np.where(region)[0])
    thin = np.zeros(len(cen), bool)
    for i, t in th.items():
        thin[i] = t < 0.034
    steep = np.abs(nrm[:, 2]) < 0.55
    fin = region & (z > 1.392) & (steep | thin)
    grow = fin.copy()
    for i in np.where(fin)[0]:
        for v in bm.faces[i].verts:
            for g in v.link_faces:
                if region[g.index]:
                    grow[g.index] = True
    bm.free()
    log(f"fin mask: {fin.sum()} faces, grown {grow.sum()}")
    return grow


def carve_masks(obj):
    """Face masks (on the culled single-sheet mesh): back = the box backpack + the coat back panel behind/under it;
    fin = the two thin shoulder fins (thin plates above the shoulders, grown from their tips)."""
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    fc = face_tex_colors(me, px)
    cen = face_centres(me)
    x, y, z = cen.T
    ax = np.abs(x)
    hair = hair_like(fc)
    back = (ax < 0.150) & (z > 1.12) & (z < 1.418) & (y > 0.070)
    region = (ax > 0.092) & (ax < 0.24) & (z > 1.355) & (y > -0.095) & (y < 0.22) & ~hair & ~back
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    th = face_thickness(bm, bvh, np.where(region)[0])
    thin = np.zeros(len(cen), bool)
    for i, t in th.items():
        thin[i] = t < 0.034
    seeds = [i for i in np.where(region & thin & (z > 1.412))[0]]
    fin = np.zeros(len(cen), bool)
    fin[seeds] = True
    stack = list(seeds)
    while stack:
        f = bm.faces[stack.pop()]
        for e in f.edges:
            for g in e.link_faces:
                j = g.index
                if not fin[j] and region[j] and thin[j]:
                    fin[j] = True
                    stack.append(j)
    # one ring of dilation (clean cut line), staying inside the region
    grow = fin.copy()
    for i in np.where(fin)[0]:
        for v in bm.faces[i].verts:
            for g in v.link_faces:
                if region[g.index]:
                    grow[g.index] = True
    fin = grow
    bm.free()
    log(f"carve masks: back {back.sum()} faces, fins {fin.sum()} faces ({len(seeds)} seeds)")
    return back, fin


def _delete_and_fill(obj, mask, axis, zone, uv_pin, patch_id, edge_len=0.010, lam=2e-3, ring=0.035, bulge=0.0,
                     loose_near=None):
    """Delete the masked faces and close the resulting holes whose centroid lies in zone(centroid) with TPS patches.
    loose_near=(point, radius, max_verts): also drop pieces cut loose near point (e.g. the drone's antenna)."""
    import sol_geo as G
    me = obj.data
    if "sol_patch" not in me.attributes:
        me.attributes.new("sol_patch", "INT", "FACE")
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    lay = bm.faces.layers.int.get("sol_patch")
    kill = [bm.faces[i] for i in np.where(mask)[0]]
    touched = {v for f in kill for v in f.verts}
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # scraps cut loose by the deletion
    isl = islands(bm)
    bm.verts.ensure_lookup_table()
    scraps = [bm.verts[j] for i in isl if len(i) < 40 for j in i]
    if loose_near is not None:
        pc, rad, nmax = loose_near
        for i in isl:
            if 40 <= len(i) < nmax:
                c = np.mean([bm.verts[j].co[:] for j in i], axis=0)
                if np.linalg.norm(c - np.asarray(pc)) < rad:
                    scraps += [bm.verts[j] for j in i]
                    log(f"  dropped a loose piece of {len(i)} verts at {np.round(c, 3)}")
    bmesh.ops.delete(bm, geom=scraps, context="VERTS")
    touched = {v for v in touched if v.is_valid}
    bm.normal_update()
    nb = [e for e in bm.edges if e.is_boundary]
    loops = [lp for lp, closed in G.boundary_loops_directed(nb) if closed and len(lp) >= 3
             and any(v in touched for v in lp)]
    log(f"  hole loops: {[len(lp) for lp in loops]}")
    total = 0
    for lp in sorted(loops, key=len, reverse=True):
        c = np.mean([v.co[:] for v in lp], axis=0)
        if not zone(c):
            continue
        patch = G.fill_loop_tps(bm, lp, axis, uv_pin, ring_radius=ring, edge_len=edge_len, lam=lam,
                                patch_layer=lay, patch_id=patch_id, bulge=bulge if len(lp) > 16 else 0.0)
        total += len(patch)
    bm.to_mesh(me)
    bm.free()
    log(f"deleted {len(kill)} faces, filled {len(loops)} loops with {total} faces")


def cap_mask(obj, zc=1.378):
    """Shoulder-top caps (fins, fin bases, strap stubs): every non-hair face above the shoulder line."""
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    fc = face_tex_colors(me, px)
    cen = face_centres(me)
    x, y, z = cen.T
    ax = np.abs(x)
    pf = patch_flags(me)
    m = (ax > 0.082) & (ax < 0.235) & (y > -0.10) & (y < 0.20) & (z > zc) & (z < 1.50) & ~hair_like(fc) & (pf != 2)
    log(f"cap mask: {m.sum()} faces")
    return m


def carve_backpack(obj):
    """Remove the hallucinated box backpack + the shoulder fins and rebuild the coat surface under them."""
    import sol_geo as G
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    bm = bmesh.new()
    bm.from_mesh(me)
    uv_pin, col = G.find_clean_uv(bm, px, G.is_ivory, (0.0, 0.09, 1.05))
    bm.free()
    log(f"patch texel uv {tuple(round(v, 4) for v in uv_pin)} colour {np.round(col, 3)}")
    _delete_and_fill(obj, back_mask(obj), (0, 1, 0), lambda c: c[1] > 0.0 and c[2] > 1.05, uv_pin, 1, bulge=0.018)
    _delete_and_fill(obj, cap_mask(obj), (0, 0, 1), lambda c: c[2] > 1.33, uv_pin, 2, edge_len=0.008, ring=0.03,
                     bulge=0.018)
    return uv_pin


def fill_small_holes(obj, max_len=10):
    """Close tiny leftover holes (culling pin-holes) with plain fills (UV of the first loop vert's corner)."""
    import sol_geo as G
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    uvl = bm.loops.layers.uv.active
    lay = bm.faces.layers.int.get("sol_patch")
    nb = [e for e in bm.edges if e.is_boundary]
    n = 0
    for lp, _ in G.boundary_loops_directed(nb):
        if len(lp) > max_len:
            continue
        uv = lp[0].link_loops[0][uvl].uv.copy() if lp[0].link_loops else Vector((0, 0))
        # winding: new face must agree with neighbours -> walk direction already opposite to the face loops
        try:
            f = bm.faces.new(lp)
        except ValueError:
            continue
        for l_ in f.loops:
            l_[uvl].uv = uv
        if lay is not None:
            f[lay] = 3
        f.smooth = True
        n += 1
    bm.to_mesh(me)
    bm.free()
    log(f"filled {n} small holes (<= {max_len} edges)")


def smooth_eye_zones(obj, iters=40):
    """TRELLIS modelled the smeared eyeliner as geometry: a lash ridge (strongest on her left eye, running out to the
    temple). Taubin-smooth the face surface inside two ellipses around the eyes (front-facing verts only) so the
    painted eyes sit on a clean lid surface; the big socket shape survives (low frequencies are kept)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    co = np.array([v.co[:] for v in bm.verts])
    nz = np.array([v.normal[:] for v in bm.verts])
    x, y, z = co.T
    w = np.zeros(len(co))
    for (cx, cz, rx, rz) in ((0.046, 1.5515, 0.030, 0.0125), (-0.037, 1.5490, 0.022, 0.0115)):
        d = np.sqrt(((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2)
        w = np.maximum(w, 1 - smoothstep(0.7, 1.0, d))
    w *= (nz[:, 1] < 0.1) & (y < -0.02)
    idx = np.where(w > 0)[0]
    nbr = {i: [e.other_vert(bm.verts[i]).index for e in bm.verts[i].link_edges] for i in idx}
    P = co.copy()
    for it in range(iters):
        for lam in (0.5, -0.53):
            L = np.array([P[nbr[i]].mean(0) - P[i] if nbr[i] else np.zeros(3) for i in idx])
            P[idx] += lam * w[idx, None] * L
    for i in idx:
        bm.verts[i].co = P[i]
    bm.to_mesh(me)
    bm.free()
    log(f"eye zones smoothed: {len(idx)} verts")


def rebuild_eye_zones(obj):
    """Replace the TRELLIS eye geometry (closed-lid creases + the lash-smear ridge on her left eye) with clean,
    slightly convex lid patches; the eyes are painted onto them in the face texture."""
    import sol_geo as G
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    bm = bmesh.new()
    bm.from_mesh(me)
    uv_pin, _c = G.find_clean_uv(bm, px, lambda c: (c[..., 0] - c[..., 2] > 0.2) & (c[..., 0] > 0.35) & (c[..., 0] < 0.7),
                                 (0.045, -0.06, 1.52), k=2)
    bm.free()
    cen = face_centres(me)
    nrm = _face_normals(me)
    x, y, z = cen.T
    m = np.zeros(len(cen), bool)
    for (cx, cz, rx, rz) in ((0.047, 1.5515, 0.0225, 0.0118), (-0.040, 1.5505, 0.0255, 0.0115)):
        m |= (((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 < 1.0)
    m &= (y < -0.038) & (x < 0.067) & (x > -0.067)
    m |= (x > 0.055) & (x < 0.0755) & (z > 1.5405) & (z < 1.5565) & (y < -0.0315)   # lash-ridge stub by the lock
    _delete_and_fill(obj, m, (0, -1, 0), lambda c: c[2] > 1.5 and c[1] < 0, uv_pin, 4, edge_len=0.0035, ring=0.012,
                     bulge=0.0012)


# TRELLIS heal drone on her LEFT hip (sphere fitted to the stage-A shell): cut out of the body, so the procedural
# SOL_Drone (sol_parts) can be a separate object the game hides / launches (MEND DRONE)
DRONE_SPHERE_C, DRONE_SPHERE_R = np.array([0.1606, -0.0627, 1.0238]), 0.058


def drone_masks(obj):
    """Faces of the TRELLIS drone: the shell + eye recess + the coat inside it (within 1.10 R of the fitted sphere
    centre) and the dark antenna stub on top."""
    me = obj.data
    cen = face_centres(me)
    px = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    fc = face_tex_colors(me, px)
    x, y, z = cen.T
    d = np.linalg.norm(cen - DRONE_SPHERE_C, axis=1)
    shell = d < 1.10 * DRONE_SPHERE_R
    ant = (fc.mean(1) < 0.25) & (x > 0.13) & (x < 0.25) & (y > -0.11) & (y < 0.04) & (z > 1.04) & (z < 1.17) \
        & (d < 2.4 * DRONE_SPHERE_R) & (patch_flags(me) == 0)
    ring = (d > 1.15 * DRONE_SPHERE_R) & (d < 1.6 * DRONE_SPHERE_R) & ~ant
    nrm = _face_normals(me)[ring].mean(0)
    nrm /= np.linalg.norm(nrm)
    log(f"drone: {shell.sum()} shell faces, {ant.sum()} antenna faces, hip normal {np.round(nrm, 3)}")
    return shell | ant, nrm


def remove_drone(obj):
    import sol_geo as G
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    bm = bmesh.new()
    bm.from_mesh(me)
    uv_pin, col = G.find_clean_uv(bm, px, G.is_ivory, (0.20, -0.02, 0.93))
    bm.free()
    mask, nrm = drone_masks(obj)
    _delete_and_fill(obj, mask, tuple(nrm), lambda c: np.linalg.norm(np.asarray(c) - DRONE_SPHERE_C) < 0.14,
                     uv_pin, 5, edge_len=0.008, ring=0.03, bulge=0.0, loose_near=(DRONE_SPHERE_C, 0.15, 600))
    return nrm


def stage_a(quick=False):
    obj = import_trellis()
    normalise(obj)
    weld_and_drop_bits(obj)
    clear_custom_normals(obj)
    cull_hidden(obj, quick=quick)
    carve_backpack(obj)
    rebuild_eye_zones(obj)
    remove_drone(obj)
    fill_small_holes(obj)
    bc.shade_smooth(obj, 180)
    me = obj.data
    me.validate(clean_customdata=False)
    log(f"stage A done: {len(me.vertices)} verts, {tris_of(obj)} tris")
    return obj


# ================================================================================================ STAGE B bakes
TEX_SIZE = 2048


def _cycles_bake_setup(samples=1):
    sc = bpy.context.scene
    bc.setup_cycles_gpu(sc, samples)
    if os.environ.get("VALETF_BAKE_GPU") is None:
        sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.bake.margin = 4
    sc.render.bake.margin_type = "EXTEND"
    sc.render.bake.use_clear = True
    sc.render.bake.target = "IMAGE_TEXTURES"
    return sc


def bake_emit(obj, build, name, size=TEX_SIZE, margin=4, float_buffer=True, skip_patch=True):
    """Bake an emission shader built by build(nt) -> socket into a new image (EMIT pass, exact values).
    Patch faces (sol_patch != 0) share one pinned texel and are routed to a dummy image."""
    me = obj.data
    sc = _cycles_bake_setup(1)
    sc.render.bake.margin = margin
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=float_buffer)
    img.colorspace_settings.name = "Non-Color"
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
    m_dummy = mk("_bake_dummyM", dummy)
    saved = list(me.materials)
    idx = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("material_index", idx)
    me.materials.clear()
    me.materials.append(m_main)
    me.materials.append(m_dummy)
    flag = (patch_flags(me) != 0) if skip_patch else np.zeros(len(me.polygons), bool)
    me.polygons.foreach_set("material_index", flag.astype(np.int32))
    me.update()
    activate(obj)
    bpy.ops.object.bake(type="EMIT", margin=margin, use_clear=True)
    me.materials.clear()
    for m in saved:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", idx)
    me.update()
    bpy.data.materials.remove(m_main)
    bpy.data.materials.remove(m_dummy)
    return img


def _geo(nt, socket):
    return nt.nodes.new("ShaderNodeNewGeometry").outputs[socket]


def _attr(nt, name):
    a = nt.nodes.new("ShaderNodeAttribute")
    a.attribute_name = name
    return a.outputs["Color"]


def _white(nt):
    r = nt.nodes.new("ShaderNodeRGB")
    r.outputs[0].default_value = (1, 1, 1, 1)
    return r.outputs[0]


def bake_maps(obj):
    """Texel-space maps: object position, smooth normal and coverage (patch faces excluded)."""
    t = time.time()
    pos = img_to_np(bake_emit(obj, lambda nt: _geo(nt, "Position"), "_pos"))[..., :3].copy()
    nrm = img_to_np(bake_emit(obj, lambda nt: _geo(nt, "Normal"), "_nrm"))[..., :3].copy()
    cov = img_to_np(bake_emit(obj, _white, "_cov", margin=0))[..., 0] > 0.5
    for nm in ("_pos", "_nrm", "_cov"):
        bpy.data.images.remove(bpy.data.images[nm])
    log(f"baked maps in {time.time() - t:.1f}s; coverage {cov.mean():.3f}")
    return pos, nrm, cov


# ================================================================================================ face texture
FACE_X0, FACE_Z0, FACE_S, FACE_RES = 0.001 - 0.105, 1.42, 0.21, 1024


def face_face_mask(obj):
    """Front-facing face faces (skin, painted features, eye patches); excludes hair / the hair lock."""
    me = obj.data
    px = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    fc = face_tex_colors(me, px)
    cen = face_centres(me)
    nrm = _face_normals(me)
    x, y, z = cen.T
    pf = patch_flags(me)
    box = (np.abs(x - 0.001) < 0.072) & (z > 1.425) & (z < 1.625) & (y < -0.02) & (nrm[:, 1] < -0.22)
    skinlike = (fc[:, 0] - fc[:, 2] > 0.12) & (fc[:, 0] > 0.25)
    feat = np.zeros(len(x), bool)
    for (cx, cz, rx, rz) in ((0.038, 1.553, 0.026, 0.020), (-0.036, 1.553, 0.026, 0.020)):
        feat |= ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 < 1.0
    m = box & (skinlike | (pf == 4) | (feat & (y < -0.045) & (np.abs(x) < 0.056)))
    # TRELLIS fringe flakes over her right temple stay on the atlas (recoloured to hair there)
    m &= ~((x < -0.050) & (z > 1.535) & (pf != 4))
    # close one-face gaps, drop strays
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    for _ in range(2):
        add = np.zeros_like(m)
        rem = np.zeros_like(m)
        for f in bm.faces:
            nb = [g.index for e in f.edges for g in e.link_faces if g is not f]
            k = sum(m[j] for j in nb)
            if not m[f.index] and box[f.index] and k >= 2:
                add[f.index] = True
            if m[f.index] and k == 0:
                rem[f.index] = True
        m = (m | add) & ~rem
    bm.free()
    # rebuilt eye-zone patch faces (one pinned skin texel on the atlas) that fold into the TRELLIS fringe flakes at
    # her right temple: give them the face texture, which paints the flake polygons hair-dark (sol_face)
    from sol_tex import in_shards
    fl = (pf != 0) & in_shards(x, z) & (y < -0.01)
    m |= fl
    log(f"face material faces: {m.sum()} ({fl.sum()} temple-flake patch faces)")
    return m


def render_face_capture(obj, mask, path):
    """Orthographic front capture of the (already regraded) base texture on the face faces only (flat shading)."""
    sc = bpy.context.scene
    tmp = obj.copy()
    tmp.data = obj.data.copy()
    tmp.name = "_facecap"
    sc.collection.objects.link(tmp)
    bm = bmesh.new()
    bm.from_mesh(tmp.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not mask[f.index]], context="FACES")
    bm.to_mesh(tmp.data)
    bm.free()
    hidden = [o for o in sc.objects if o is not tmp and not o.hide_render]
    for o in hidden:
        o.hide_render = True
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "TEXTURE"
    sh.show_specular_highlight = False
    sh.show_cavity = False
    sh.show_shadows = False
    sh.show_backface_culling = False
    sc.display.render_aa = "16"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = FACE_RES
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    cam = _cam(sc)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = FACE_S
    cam.location = (FACE_X0 + FACE_S / 2, -2.0, FACE_Z0 + FACE_S / 2)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in hidden:
        o.hide_render = False
    bpy.data.objects.remove(tmp, do_unlink=True)
    cam.data.type = "PERSP"
    sc.render.film_transparent = False
    im = bpy.data.images.load(path, check_existing=False)
    a = img_to_np(im).copy()
    bpy.data.images.remove(im)
    return a


# ================================================================================================ STAGE B
def _img_from(name, arr, colorspace):
    a = np.asarray(arr, np.float32)
    if a.shape[2] == 3:
        a = np.concatenate([a, np.ones(a.shape[:2] + (1,), np.float32)], 2)
    img = bpy.data.images.get(name)
    h, w = a.shape[:2]
    if img is None or tuple(img.size) != (w, h):
        if img:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(a.ravel())
    img.update()
    os.makedirs(TEX, exist_ok=True)
    img.filepath_raw = os.path.join(TEX, name + ".png")
    img.file_format = "PNG"
    img.save()
    img.pack()
    return img


def _tex_node(nt, img, loc, noncolor=False):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    t.location = loc
    t.interpolation = "Linear"
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    return t


def face_orm(n=FACE_RES):
    """ORM for the front-projected face texture: skin roughness 0.52, matte hair roughness on the temple-flake
    polygons (painted hair-dark), metal 0."""
    from sol_tex import in_shards, HAIR_ROUGH
    jj, ii = np.mgrid[0:n, 0:n]
    px = FACE_X0 + (ii + 0.5) / n * FACE_S
    pz = FACE_Z0 + (jj + 0.5) / n * FACE_S
    m = in_shards(px, pz).astype(np.float32)
    orm = np.zeros((n, n, 3), np.float32)
    orm[..., 0] = 1.0
    orm[..., 1] = 0.52 + (HAIR_ROUGH - 0.52) * m
    return orm


def body_materials(base_img, orm_img, nrm_img, face_img, face_orm_img=None):
    """M_SOL_Body (TRELLIS atlas: base, ORM, normal) and M_SOL_Face (front-projected face texture)."""
    out = []
    for name in ("M_SOL_Body", "M_SOL_Face"):
        old = bpy.data.materials.get(name)
        if old:
            bpy.data.materials.remove(old)
    m = bpy.data.materials.new("M_SOL_Body")
    m.use_nodes = True
    nt = m.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tb = _tex_node(nt, base_img, (-600, 300))
    nt.links.new(tb.outputs["Color"], p.inputs["Base Color"])
    to = _tex_node(nt, orm_img, (-600, 0), noncolor=True)
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.location = (-300, 0)
    nt.links.new(to.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], p.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], p.inputs["Metallic"])
    tn = _tex_node(nt, nrm_img, (-600, -300), noncolor=True)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (-300, -300)
    nm.inputs["Strength"].default_value = 0.8
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    out.append(m)
    f = bpy.data.materials.new("M_SOL_Face")
    f.use_nodes = True
    nt = f.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tf = _tex_node(nt, face_img, (-400, 200))
    nt.links.new(tf.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.52
    if face_orm_img is not None:
        tfo = _tex_node(nt, face_orm_img, (-600, -100), noncolor=True)
        sepf = nt.nodes.new("ShaderNodeSeparateColor")
        sepf.location = (-300, -100)
        nt.links.new(tfo.outputs["Color"], sepf.inputs["Color"])
        nt.links.new(sepf.outputs["Green"], p.inputs["Roughness"])
        nt.links.new(sepf.outputs["Blue"], p.inputs["Metallic"])
    out.append(f)
    return out


def stage_b(obj):
    import sol_tex
    import sol_face
    pos, nrm, cov = bake_maps(obj)
    src = img_to_np(bpy.data.images["SOL_BaseColor_src"])
    base, orm, _ = sol_tex.process(src, pos, nrm, cov, log=log)
    base_img = _img_from("SOL_BaseColor", base, "sRGB")
    orm_img = _img_from("SOL_ORM", orm, "Non-Color")
    nsrc = bpy.data.images["SOL_Normal_src"]
    nrm_img = _img_from("SOL_Normal", img_to_np(nsrc)[..., :3], "Non-Color")
    # face: capture the regraded base on the front face faces, repaint, project
    tmpm = bc.material("_cap", (1, 1, 1))
    tmpm.use_nodes = True
    ntc = tmpm.node_tree
    pc = next(n for n in ntc.nodes if n.type == "BSDF_PRINCIPLED")
    tcap = ntc.nodes.new("ShaderNodeTexImage")
    tcap.image = base_img
    ntc.links.new(tcap.outputs["Color"], pc.inputs["Base Color"])
    me = obj.data
    me.materials.clear()
    me.materials.append(tmpm)
    mask = face_face_mask(obj)
    cap = render_face_capture(obj, mask, os.path.join(WORK, "facecap.png"))
    face = sol_face.paint_face(cap, log=log)
    face_img = _img_from("SOL_Face", face, "sRGB")
    face_orm_img = _img_from("SOL_FaceORM", face_orm(), "Non-Color")
    mats = body_materials(base_img, orm_img, nrm_img, face_img, face_orm_img)
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    bpy.data.materials.remove(tmpm)
    mi = mask.astype(np.int32)
    me.polygons.foreach_set("material_index", mi)
    # planar UVs for the face faces
    uv = loop_uvs(me)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    lp_face = np.repeat(mask, [len(p_.vertices) for p_ in me.polygons])
    co = mesh_co(me)
    fx = (co[lv, 0] - FACE_X0) / FACE_S
    fz = (co[lv, 2] - FACE_Z0) / FACE_S
    uv[lp_face, 0] = fx[lp_face]
    uv[lp_face, 1] = fz[lp_face]
    me.uv_layers.active.data.foreach_set("uv", uv.ravel())
    me.update()
    for nm_ in ("SOL_BaseColor_src", "SOL_ORM_src", "SOL_Normal_src", "_bake_dummy"):
        if bpy.data.images.get(nm_):
            bpy.data.images.remove(bpy.data.images[nm_])
    srcm = bpy.data.materials.get("_trellis_src")
    if srcm:
        bpy.data.materials.remove(srcm)
    log("stage B done")
