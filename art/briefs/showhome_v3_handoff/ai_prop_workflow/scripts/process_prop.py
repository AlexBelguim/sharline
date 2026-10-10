"""Blender (headless) per-prop processing for the TRELLIS.2 test.

  blender -b --factory-startup --python process_prop.py -- <name> <full.glb> <test_dir> [yaw_deg] [target_tris]

1. import the TRELLIS.2 GLB, stand it on the ground (Z=0), centre it, turn it so its front faces -Y
2. measure it: triangles, components, non-manifold / boundary edges, UV islands, UV coverage, textures
3. budget version A ("uvkeep"): Blender Decimate (collapse) to ~target tris, keeping TRELLIS's own UVs + textures
4. budget version B ("rebake"): same decimated mesh, fresh Smart-UV, base colour / normal / roughness / metallic
   baked from the full mesh at 2048 (Cycles, selected-to-active)
5. EEVEE renders: 4 angles for full, budget A and budget B; clay renders (front 3/4) and a budget wireframe
Writes models/<name>_budget_uvkeep.glb, models/<name>_budget_rebake.glb, renders/<name>/*.png, models/<name>_stats.json
"""
import bpy
import bmesh
import json
import math
import os
import sys
import time

import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
NAME, FULL, T = argv[0], argv[1], argv[2]
YAW = float(argv[3]) if len(argv) > 3 else 0.0
TARGET = int(argv[4]) if len(argv) > 4 else 4500
ONLY_RENDER = os.environ.get("ONLY_RENDER") == "1"
RDIR = os.path.join(T, "renders", NAME)
MDIR = os.path.join(T, "models")
os.makedirs(RDIR, exist_ok=True)
RES = int(os.environ.get("RES", "900"))
BAKE_RES = int(os.environ.get("BAKE_RES", "2048"))

t_start = time.time()
stats = {"name": NAME, "source": os.path.basename(FULL)}


def log(*a):
    print(f"[{NAME} {time.time() - t_start:6.1f}s]", *a, flush=True)


# ----------------------------------------------------------------------------------------------- helpers
def select_only(*objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def import_glb(path, label):
    before = set(bpy.data.objects)
    try:  # glTF splits vertices at every UV seam; weld them back so topology / decimation are honest
        bpy.ops.import_scene.gltf(filepath=path, merge_vertices=True)
    except TypeError:
        bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    for o in meshes:  # flatten hierarchy, keep world transform
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    select_only(*meshes)
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.name = label
    return ob


def label_propagate(n, a, b):
    """connected components of an undirected graph with n nodes and edge arrays a, b -> labels"""
    lab = np.arange(n, dtype=np.int64)
    while True:
        m = np.minimum(lab[a], lab[b])
        old = lab.copy()
        np.minimum.at(lab, a, m)
        np.minimum.at(lab, b, m)
        lab = lab[lab]  # pointer jumping
        lab = lab[lab]
        if np.array_equal(lab, old):
            return lab


def mesh_stats(ob):
    me = ob.data
    me.calc_loop_triangles()
    s = {"tris": len(me.loop_triangles), "verts": len(me.vertices), "faces": len(me.polygons)}
    sizes = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_total", sizes)
    s["quads"] = int((sizes == 4).sum())
    s["ngons"] = int((sizes > 4).sum())
    ev = np.zeros(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    s["components"] = int(len(np.unique(label_propagate(len(me.vertices), ev[:, 0], ev[:, 1]))))
    bm = bmesh.new()
    bm.from_mesh(me)
    s["boundary_edges"] = sum(1 for e in bm.edges if e.is_boundary)
    s["nonmanifold_edges"] = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    # UV islands = connected components of UV vertices (loops welded by identical UV + vertex)
    if me.uv_layers.active:
        nl = len(me.loops)
        uv = np.zeros(nl * 2, dtype=np.float64)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        lv = np.zeros(nl, dtype=np.int64)
        me.loops.foreach_get("vertex_index", lv)
        key = np.column_stack([lv, np.round(uv * 1e5).astype(np.int64)])
        _, uid = np.unique(key, axis=0, return_inverse=True)
        uid = uid.ravel()
        starts = np.zeros(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("loop_start", starts)
        idx = np.arange(nl)
        poly_of = np.repeat(np.arange(len(starts)), sizes)
        nxt = idx + 1
        ends = starts + sizes
        nxt[ends - 1] = starts
        lab = label_propagate(int(uid.max()) + 1, uid[idx], uid[nxt])
        s["uv_islands"] = int(len(np.unique(lab[uid])))
        # UV area used (sum of triangle areas in UV space; >1 would mean overlaps)
        lt = np.zeros(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("loops", lt)
        p = uv[lt.reshape(-1, 3)]
        area = 0.5 * np.abs((p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) -
                            (p[:, 2, 0] - p[:, 0, 0]) * (p[:, 1, 1] - p[:, 0, 1]))
        s["uv_area_used"] = round(float(area.sum()), 3)
        # seam edges: mesh edges whose two loops disagree in UV
        s["uv_seam_edge_share"] = None
        _ = poly_of
    d = ob.dimensions
    s["dims_m"] = [round(d.x, 3), round(d.y, 3), round(d.z, 3)]
    return s


def material_images(ob):
    out = {}
    for slot in ob.material_slots:
        m = slot.material
        if not m or not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                tgt = [l.to_socket.name for l in n.outputs[0].links] + [l.to_socket.name for l in n.outputs[1].links]
                out[n.image.name] = {"size": list(n.image.size), "feeds": tgt}
    return out


def principled(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def save_basecolor(ob, path):
    m = ob.material_slots[0].material
    bsdf = principled(m)
    lk = bsdf.inputs["Base Color"].links
    if not lk:
        return
    n = lk[0].from_node
    while n.type != "TEX_IMAGE" and n.inputs and any(i.links for i in n.inputs):
        n = next(i for i in n.inputs if i.links).links[0].from_node
    if n.type == "TEX_IMAGE":
        img = n.image
        img2 = img.copy()
        img2.scale(1024, 1024)
        img2.filepath_raw = path
        img2.file_format = "PNG"
        img2.save()
        bpy.data.images.remove(img2)


def setup_gpu():
    if os.environ.get("BAKE_DEVICE") == "CPU":
        bpy.context.scene.cycles.device = "CPU"
        return
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for t in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = t
                break
            except TypeError:
                continue
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type != "CPU"
        bpy.context.scene.cycles.device = "GPU"
    except Exception as e:  # noqa
        log("GPU setup failed, CPU bake", e)


def tri_count(ob):
    ob.data.calc_loop_triangles()
    return len(ob.data.loop_triangles)


def decimate_copy(src, target, label, strip_uv=False, voxel=None):
    """Blender collapse decimate. TRELLIS meshes are not fully manifold (edges shared by 3-4 faces), and the
    collapse decimator stalls near those (~20k tris for the duffel) whether UVs are kept or not.
    For the rebake path: strip UVs, voxel-remesh (watertight, manifold) and then decimate to the target."""
    ob = src.copy()
    ob.data = src.data.copy()
    ob.name = label
    bpy.context.scene.collection.objects.link(ob)
    select_only(ob)
    if strip_uv:
        me = ob.data
        while me.uv_layers:
            me.uv_layers.remove(me.uv_layers[0])
        try:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        except Exception:
            pass
    if voxel:
        mod = ob.modifiers.new("vox", "REMESH")
        mod.mode = "VOXEL"
        mod.voxel_size = voxel
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for i in range(4):
        got = tri_count(ob)
        if got <= target * 1.12:
            break
        mod = ob.modifiers.new(f"dec{i}", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = target / got
        mod.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob


def exterior_copy(src, label, proxy_tris=90000, ndirs=48):
    """TRELLIS.2 (template UDF remesh) outputs every surface as a ~3 mm double-layer sheet around a hollow
    inside. Keep only faces that can be seen from outside (rays that escape sideways/upwards; the ground
    hides everything below), so the budget triangles go to visible surfaces only."""
    from mathutils.bvhtree import BVHTree
    ob = src.copy()
    ob.data = src.data.copy()
    ob.name = label
    bpy.context.scene.collection.objects.link(ob)
    select_only(ob)
    me = ob.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    try:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except Exception:
        pass
    mod = ob.modifiers.new("pre", "DECIMATE")
    mod.ratio = min(1.0, proxy_tris / tri_count(ob))
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bvh = BVHTree.FromBMesh(bm)
    size = max(ob.dimensions)
    eps = 2e-4 * size
    # fixed direction set (Fibonacci sphere), ground hides rays pointing down
    dirs = []
    for i in range(ndirs * 2):
        z = 1 - (i + 0.5) / ndirs
        if z < -0.08:
            continue
        r = math.sqrt(max(0.0, 1 - z * z))
        a = i * 2.399963
        dirs.append(Vector((r * math.cos(a), r * math.sin(a), z)))
    hidden = []
    casts = 0
    for f in bm.faces:
        n = f.normal
        c = f.calc_center_median() + n * eps
        cand = sorted((d for d in dirs if d.dot(n) > 0.05), key=lambda d: -d.dot(n))
        if n.z > -0.08:
            cand.insert(0, n.copy())
        seen = False
        for d in cand:
            casts += 1
            if bvh.ray_cast(c, d)[0] is None:
                seen = True
                break
        if not seen:
            hidden.append(f)
    nh = len(hidden)
    bmesh.ops.delete(bm, geom=hidden, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    log(f"exterior cull: removed {nh} of {nh + len(ob.data.polygons)} proxy faces ({casts} rays)")
    for i in range(5):
        got = tri_count(ob)
        if got <= TARGET * 1.12:
            break
        mod = ob.modifiers.new(f"dec{i}", "DECIMATE")
        mod.ratio = TARGET / got
        mod.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return ob, nh


def export_glb(ob, path):
    select_only(ob)
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_format="GLB", export_yup=True,
                              export_apply=True, export_image_format="AUTO")


# ---------------------------------------------------------------------------------- bake budget B
def bake_to(low, high, size):
    """Fresh UVs on low; bake base colour, normal, roughness, metallic from high (selected to active)."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    setup_gpu()
    sc.cycles.samples = 4
    sc.render.bake.use_selected_to_active = True
    r = max(high.dimensions)
    sc.render.bake.cage_extrusion = 0.015 * r
    sc.render.bake.max_ray_distance = 0.04 * r
    sc.render.bake.margin = 8
    # fresh UVs
    me = low.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name="UVMap")
    select_only(low)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    # fresh material with image targets
    m = bpy.data.materials.new(f"M_{NAME}_budget")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = principled(m)
    low.data.materials.clear()
    low.data.materials.append(m)
    imgs = {}
    for key, cs in (("basecolor", "sRGB"), ("normal", "Non-Color"), ("roughness", "Non-Color"),
                    ("metallic", "Non-Color")):
        img = bpy.data.images.new(f"{NAME}_budget_{key}", size, size, alpha=False, float_buffer=False)
        img.colorspace_settings.name = cs
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
        n.name = f"T_{key}"
        imgs[key] = (img, n)

    def bake(key, btype, **kw):
        for n in nt.nodes:
            n.select = False
        nt.nodes.active = imgs[key][1]
        imgs[key][1].select = True
        select_only(low)
        high.select_set(True)
        bpy.context.view_layer.objects.active = low
        t0 = time.time()
        bpy.ops.object.bake(type=btype, **kw)
        log("baked", key, f"{time.time() - t0:.1f}s")

    # every channel goes through emission: a DIFFUSE/COLOR bake would come out as base*(1-metallic), and
    # TRELLIS paints high metallic on fabric (armchair ~0.8), which darkened the first rebake
    hm = high.material_slots[0].material
    hb = principled(hm)
    hnt = hm.node_tree
    ec, es = hb.inputs["Emission Color"], hb.inputs["Emission Strength"]
    old_ec = list(ec.default_value)
    old_es = es.default_value
    old_ec_link = ec.links[0].from_socket if ec.links else None
    for key, inp in (("basecolor", "Base Color"), ("roughness", "Roughness"), ("metallic", "Metallic")):
        for l in list(ec.links):
            hnt.links.remove(l)
        src_link = hb.inputs[inp].links
        if src_link:
            lk = hnt.links.new(src_link[0].from_socket, ec)
        else:
            v = hb.inputs[inp].default_value
            ec.default_value = tuple(v) if inp == "Base Color" else (v, v, v, 1.0)
            lk = None
        es.default_value = 1.0
        bake(key, "EMIT")
        if lk:
            hnt.links.remove(lk)
    ec.default_value = old_ec
    es.default_value = old_es
    if old_ec_link:
        hnt.links.new(old_ec_link, ec)
    bake("normal", "NORMAL", normal_space="TANGENT")
    # wire the baked maps
    L = nt.links
    L.new(imgs["basecolor"][1].outputs["Color"], bsdf.inputs["Base Color"])
    L.new(imgs["roughness"][1].outputs["Color"], bsdf.inputs["Roughness"])
    L.new(imgs["metallic"][1].outputs["Color"], bsdf.inputs["Metallic"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    L.new(imgs["normal"][1].outputs["Color"], nm.inputs["Color"])
    L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    for key, (img, n) in imgs.items():
        p = os.path.join(MDIR, "budget_tex", f"{NAME}_budget_{key}.png")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        img.filepath_raw = p
        img.file_format = "PNG"
        img.save()
    return m


# ----------------------------------------------------------------------------------------- rendering
CLAY = None


def build_stage():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    try:
        sc.eevee.taa_render_samples = 64
    except Exception:
        pass
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.5, 0.5, 0.52, 1)
    bg.inputs["Strength"].default_value = 1.0
    # soft key + fill (neutral white)
    def light(name, typ, energy, rot, size=None):
        ld = bpy.data.lights.new(name, typ)
        ld.energy = energy
        if typ == "SUN":
            ld.angle = math.radians(25)
        if size:
            ld.size = size
        lo = bpy.data.objects.new(name, ld)
        sc.collection.objects.link(lo)
        lo.rotation_euler = [math.radians(x) for x in rot]
        return lo
    light("key", "SUN", 3.0, (45, 0, -35))
    light("rim", "SUN", 1.0, (60, 0, 150))
    # ground
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = "_ground"
    gm = bpy.data.materials.new("M_ground")
    gm.use_nodes = True
    gb = principled(gm)
    gb.inputs["Base Color"].default_value = (0.32, 0.32, 0.33, 1)
    gb.inputs["Roughness"].default_value = 0.85
    g.data.materials.append(gm)
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 50
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    global CLAY
    CLAY = bpy.data.materials.new("M_clay")
    CLAY.use_nodes = True
    cb = principled(CLAY)
    cb.inputs["Base Color"].default_value = (0.22, 0.22, 0.23, 1)
    cb.inputs["Roughness"].default_value = 0.55
    return cam


ANGLES = {  # name: (azimuth from front (-Y) toward +X, elevation)
    "1_front34": (40, 18),
    "2_back34": (220, 18),
    "3_side": (90, 6),
    "4_top45": (-35, 45),
}


def aim(cam, ob, az, el, margin=0.86):
    """place the camera on a ray from the bbox centre and fit the projected bbox to `margin` of the frame"""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    c = sum(corners, Vector()) / 8
    a, e = math.radians(az), math.radians(el)
    ray = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    dist = max((p - c).length for p in corners) * 3
    for _ in range(4):
        cam.location = c + dist * ray
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        pts = [world_to_camera_view(sc, cam, p) for p in corners]
        ext = max(max(abs(p.x - 0.5), abs(p.y - 0.5)) for p in pts) * 2
        dist *= ext / margin
    cam.location = c + dist * ray
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()


def render_views(ob, cam, prefix, angles=ANGLES, clay=False):
    sc = bpy.context.scene
    for o in sc.objects:
        if o.type == "MESH" and o.name != "_ground":
            o.hide_render = o is not ob
    saved = [s.material for s in ob.material_slots]
    if clay:
        for s in ob.material_slots:
            s.material = CLAY
    for nm, (az, el) in angles.items():
        aim(cam, ob, az, el)
        sc.render.filepath = os.path.join(RDIR, f"{prefix}_{nm}.png")
        bpy.ops.render.render(write_still=True)
    for s, m in zip(ob.material_slots, saved):
        s.material = m


# --------------------------------------------------------------------------------------------- main
bpy.ops.wm.read_factory_settings(use_empty=True)
full = import_glb(FULL, f"{NAME}_full")
full.rotation_euler = (0, 0, math.radians(YAW))
select_only(full)
bpy.ops.object.transform_apply(rotation=True)
corners = [full.matrix_world @ Vector(c) for c in full.bound_box]
mn = Vector((min(p.x for p in corners), min(p.y for p in corners), min(p.z for p in corners)))
mx = Vector((max(p.x for p in corners), max(p.y for p in corners), max(p.z for p in corners)))
full.location -= Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
bpy.ops.object.transform_apply(location=True)
bm = bmesh.new()
bm.from_mesh(full.data)
nv0 = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6 * max(full.dimensions))
stats["weld_removed_verts"] = nv0 - len(bm.verts)
bm.to_mesh(full.data)
bm.free()
log("imported", len(full.data.polygons), "faces; extra weld removed", stats["weld_removed_verts"])

stats["full"] = mesh_stats(full)
stats["full"]["images"] = material_images(full)
log("full stats", json.dumps(stats["full"]))
save_basecolor(full, os.path.join(RDIR, "atlas_full_basecolor.png"))

# budget A: decimate, keep TRELLIS UVs / textures
t0 = time.time()
budA = decimate_copy(full, TARGET, f"{NAME}_budget_uvkeep")
stats["decimate_secs"] = round(time.time() - t0, 1)
stats["budget_uvkeep"] = mesh_stats(budA)
log("budget A", json.dumps(stats["budget_uvkeep"]))
export_glb(budA, os.path.join(MDIR, f"{NAME}_budget_uvkeep.glb"))

# budget B: decimate without UVs to the target, fresh UVs + maps baked from the full mesh
t0 = time.time()
if os.environ.get("BUDGET_MODE", "cull") == "voxel":
    VOX = max(full.dimensions) / 250
    stats["budget_mode"] = f"voxel remesh {VOX:.4f} m + collapse"
    budB = decimate_copy(full, TARGET, f"{NAME}_budget_rebake", strip_uv=True, voxel=VOX)
else:
    budB, nh = exterior_copy(full, f"{NAME}_budget_rebake")
    stats["budget_mode"] = "collapse to 90k proxy, delete faces not visible from outside, collapse to target"
    stats["hidden_faces_removed_of_90k"] = nh
select_only(budB)
bpy.ops.object.shade_smooth()
stats["decimate_noUV_secs"] = round(time.time() - t0, 1)
t0 = time.time()
bake_to(budB, full, BAKE_RES)
stats["bake_secs"] = round(time.time() - t0, 1)
stats["budget_rebake"] = mesh_stats(budB)
log("budget B", json.dumps(stats["budget_rebake"]))
export_glb(budB, os.path.join(MDIR, f"{NAME}_budget_rebake.glb"))
save_basecolor(budB, os.path.join(RDIR, "atlas_budget_basecolor.png"))

# renders
cam = build_stage()
t0 = time.time()
render_views(full, cam, "full")
render_views(budA, cam, "budgetA")
render_views(budB, cam, "budgetB")
two = {k: ANGLES[k] for k in ("1_front34", "4_top45")}
render_views(full, cam, "clay_full", two, clay=True)
render_views(budB, cam, "clay_budget", two, clay=True)
# budget wireframe over clay
wire = budB.copy()
wire.data = budB.data.copy()
bpy.context.scene.collection.objects.link(wire)
wm = wire.modifiers.new("w", "WIREFRAME")
wm.thickness = 0.0025 * max(full.dimensions)
wm.use_replace = True
wm.use_even_offset = False
wm.use_relative_offset = False
dark = bpy.data.materials.new("M_wire")
dark.use_nodes = True
principled(dark).inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
wire.data.materials.clear()
wire.data.materials.append(dark)
wm.material_offset = 0
sc = bpy.context.scene
vl = bpy.context.view_layer
for o in sc.objects:
    if o.type == "MESH" and o.name != "_ground":
        o.hide_render = o not in (budB, wire)
aim(cam, budB, 40, 18)
budB_mats = list(budB.data.materials)
budB.data.materials.clear()
budB.data.materials.append(CLAY)
sc.render.filepath = os.path.join(RDIR, "wire_budget_1_front34.png")
bpy.ops.render.render(write_still=True)
stats["render_secs"] = round(time.time() - t0, 1)
stats["total_blender_secs"] = round(time.time() - t_start, 1)
json.dump(stats, open(os.path.join(MDIR, f"{NAME}_stats.json"), "w"), indent=1)
log("done")
