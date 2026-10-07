"""Helpers + stages for build_solace.py (SOLACE, TRELLIS.2 s42 -> finished rigged character).

Deterministic, headless Blender 5.2. Metres, Z up, the character faces -Y, her LEFT is +X, her RIGHT is -X.
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
from mathutils.kdtree import KDTree

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

OUT = r"F:/git/val etf/assets/characters/solace"
SRC = OUT + "/trellis/solace_trellis_s42.glb"
WORK = OUT + "/_work"
TEX = OUT + "/textures"
RENDERS = OUT + "/renders"
DIAG = RENDERS + "/_diag"
HEIGHT = 1.68
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


# ============================================================================================ diagnostics
def diag(prefix, views=("front", "back"), focus=None, res=(700, 900), objs=None, engine="EEVEE", lens=70,
         samples=16):
    """Quick look renders into renders/_diag (Eevee unless asked otherwise)."""
    if not bpy.data.objects.get("L_Key"):
        bc.setup_studio()
    objs = objs or [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith("_")
                    and not o.hide_render]
    return bc.render_views(DIAG, prefix, objs=objs, views=views, res=res, engine=engine, samples=samples,
                           lens=lens, focus=focus)


# ================================================================================================ main
def save_work(name):
    os.makedirs(WORK, exist_ok=True)
    p = os.path.join(WORK, name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=p, compress=False)
    log("saved", p)


def load_work(name):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(WORK, name + ".blend"))


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


# -------------------------------------------------------------------------- the hallucinated backpack + fins
def backpack_face_mask(centres):
    """Faces to carve out of the upper back: the TRELLIS box backpack, the garbage-textured coat surface it hid
    (with a hole under the collar and the box's front-wall sheet at Y~0.127), the strap across the back at the box
    bottom, and the two shoulder fins (thin plates above the shoulder line, white in front, dark behind).
    The region is rebuilt by fill_back_hole() as a smooth radial height field."""
    x, y, z = centres.T
    ax = np.abs(x)
    box = (ax < 0.150) & (z > 1.12) & (z < 1.415) & (y > 0.127)
    back = (ax < 0.145) & (z > 1.122) & (y > 0.070) & ((z < 1.418) | ((ax > 0.09) & (z < 1.47)))
    fin = (ax > 0.095) & (ax < 0.21) & (((z > 1.405) & (z < 1.47) & (y > 0.015)) |
                                       ((z > 1.33) & (z < 1.47) & (y > 0.132)))
    return box | back | fin
