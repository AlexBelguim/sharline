"""Shared helpers for building, previewing and exporting game assets in headless Blender 5.2.

Import from a build script that is run like:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P path/to/build.py -- [args]

In the build script:
  import sys, os; sys.path.insert(0, r"F:/git/val etf/tools")
  import blender_common as bc

Conventions (see art/STYLE_GUIDE.md):
  - metres, Z up, asset FRONT faces -Y (Blender "Front" view looks at it). glTF export turns this into
    Y-up / facing +Z automatically.
  - characters: feet on Z=0, centred on X=Y=0.
  - weapons: muzzle points -Y, origin at the pistol-grip hand position.
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector

PROJECT = r"F:/git/val etf"
TEXTURES = os.path.join(PROJECT, "art", "textures")


# --------------------------------------------------------------------------------------------- scene
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    return sc


def collection(name, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    par = parent or bpy.context.scene.collection
    if col.name not in [c.name for c in par.children]:
        par.children.link(col)
    return col


def link(obj, col=None):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    (col or bpy.context.scene.collection).objects.link(obj)
    return obj


# ------------------------------------------------------------------------------------------ materials
def _principled(mat):
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def _set_input(node, names, value):
    """Set the first input that exists among `names` (socket names changed across versions)."""
    for nm in names if isinstance(names, (list, tuple)) else [names]:
        if nm in node.inputs:
            node.inputs[nm].default_value = value
            return True
    return False


def material(name, color=(0.5, 0.5, 0.5), rough=0.55, metal=0.0, emission=None, emission_strength=0.0,
             tex=None, tex_scale=1.0, tex_mix=1.0, coat=0.0, alpha=1.0):
    """Create (or reuse) a Principled material.

    color: linear RGB (0-1).  emission: RGB for glowing accents.  tex: path to an albedo image which is
    multiplied over `color` by `tex_mix` (0 = flat colour, 1 = full multiply) through UVs scaled by
    tex_scale (exported to glTF as KHR_texture_transform).
    """
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    p = _principled(mat)
    col4 = (*color[:3], 1.0)
    _set_input(p, "Base Color", col4)
    _set_input(p, "Roughness", rough)
    _set_input(p, "Metallic", metal)
    if coat:
        _set_input(p, ["Coat Weight", "Clearcoat"], coat)
    if emission is not None:
        _set_input(p, ["Emission Color", "Emission"], (*emission[:3], 1.0))
        _set_input(p, "Emission Strength", emission_strength or 3.0)
    if alpha < 1.0:
        _set_input(p, "Alpha", alpha)
        try:
            mat.surface_render_method = "BLENDED"
        except Exception:
            pass
    if tex and os.path.exists(tex):
        img = bpy.data.images.load(tex, check_existing=True)
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = img
        uv = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (tex_scale, tex_scale, tex_scale)
        nt.links.new(uv.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], ti.inputs["Vector"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = tex_mix
        mix.inputs[6].default_value = col4  # A
        nt.links.new(ti.outputs["Color"], mix.inputs[7])  # B
        nt.links.new(mix.outputs[2], p.inputs["Base Color"])
    mat.diffuse_color = col4  # viewport only
    return mat


def assign(obj, mat, slot_only=False):
    if obj.data is None:
        return obj
    if slot_only:
        obj.data.materials.append(mat)
    else:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    return obj


# ---------------------------------------------------------------------------------------- primitives
def _finish(obj, name, col, mat, smooth):
    obj.name = name
    if obj.data:
        obj.data.name = name
    if col is not None:
        link(obj, col)
    if mat is not None:
        assign(obj, mat)
    if smooth is not None and obj.type == "MESH":
        shade_smooth(obj, smooth)
    return obj


def shade_smooth(obj, angle_deg=35):
    """Smooth shading with auto-smooth by angle (Blender 4.1+ API)."""
    for p in obj.data.polygons:
        p.use_smooth = True
    try:
        obj.data.set_sharp_from_angle(angle=math.radians(angle_deg))
    except Exception:
        pass
    return obj


def box(name, size, loc=(0, 0, 0), rot=(0, 0, 0), col=None, mat=None, bevel=0.0, segments=2, smooth=30):
    """Axis-aligned box of `size` (x, y, z) centred at loc. Optional bevel modifier."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    bpy.context.scene.collection.objects.link(obj)
    if bevel:
        add_bevel(obj, bevel, segments)
    return _finish(obj, name, col, mat, smooth)


def cylinder(name, radius, depth, loc=(0, 0, 0), rot=(0, 0, 0), verts=24, col=None, mat=None, bevel=0.0,
             segments=2, smooth=40, radius2=None):
    """Cylinder (or cone/frustum when radius2 given) along local Z, centred at loc."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=radius,
                          radius2=radius if radius2 is None else radius2, depth=depth)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    bpy.context.scene.collection.objects.link(obj)
    if bevel:
        add_bevel(obj, bevel, segments)
    return _finish(obj, name, col, mat, smooth)


def sphere(name, radius, loc=(0, 0, 0), scale=(1, 1, 1), segments=32, rings=16, col=None, mat=None, smooth=180):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    obj.scale = scale
    bpy.context.scene.collection.objects.link(obj)
    return _finish(obj, name, col, mat, smooth)


def profile_extrude(name, points, width, axis="X", loc=(0, 0, 0), col=None, mat=None, bevel=0.0,
                    segments=2, smooth=30):
    """Extrude a closed 2D side-profile polygon into a slab — the workhorse for gun parts.

    points: [(y, z), ...] in the side (YZ) plane, counter-clockwise or clockwise, not closed.
    width: thickness along X (the slab is centred on X=0 then moved to loc).
    """
    bm = bmesh.new()
    vs = [bm.verts.new((-width / 2, y, z)) for (y, z) in points]
    face = bm.faces.new(vs)
    bmesh.ops.recalc_face_normals(bm, faces=[face])
    ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    nv = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=Vector((width, 0, 0)), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    bpy.context.scene.collection.objects.link(obj)
    if bevel:
        add_bevel(obj, bevel, segments)
    return _finish(obj, name, col, mat, smooth)


def lathe(name, profile, axis="Y", loc=(0, 0, 0), rot=(0, 0, 0), steps=32, col=None, mat=None, smooth=60):
    """Revolve a profile [(r, h), ...] around the local Z axis (barrels, scopes, muzzle brakes).
    Rotate with rot=(90,0,0) etc. to lay it along Y. Profile should start/end at r=0 to be closed."""
    bm = bmesh.new()
    rings = []
    for i in range(steps):
        a = 2 * math.pi * i / steps
        ca, sa = math.cos(a), math.sin(a)
        rings.append([bm.verts.new((r * ca, r * sa, h)) for (r, h) in profile])
    for i in range(steps):
        r0, r1 = rings[i], rings[(i + 1) % steps]
        for j in range(len(profile) - 1):
            try:
                bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = loc
    obj.rotation_euler = [math.radians(a) for a in rot]
    bpy.context.scene.collection.objects.link(obj)
    return _finish(obj, name, col, mat, smooth)


def add_bevel(obj, width, segments=2, limit="ANGLE", angle=30):
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = limit
    if limit == "ANGLE":
        m.angle_limit = math.radians(angle)
    m.harden_normals = False
    return m


def add_subsurf(obj, levels=2):
    m = obj.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    return m


def boolean(obj, cutter, op="DIFFERENCE", apply=True, hide_cutter=True):
    m = obj.modifiers.new("Bool_" + cutter.name, "BOOLEAN")
    m.object = cutter
    m.operation = op
    m.solver = "EXACT"
    if apply:
        apply_modifiers(obj, only=[m.name])
        if hide_cutter:
            bpy.data.objects.remove(cutter, do_unlink=True)
    else:
        cutter.hide_render = True
        cutter.display_type = "WIRE"
    return obj


def apply_modifiers(obj, only=None):
    dg = bpy.context.evaluated_depsgraph_get()
    if only is not None:
        keep = [m for m in obj.modifiers if m.name not in only]
        states = {m.name: (m.show_viewport, m.show_render) for m in keep}
        for m in keep:
            m.show_viewport = m.show_render = False
        dg = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev)
        for m in keep:
            m.show_viewport, m.show_render = states[m.name]
        for nm in only:
            obj.modifiers.remove(obj.modifiers[nm])
    else:
        ev = obj.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev)
        obj.modifiers.clear()
    old = obj.data
    obj.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def join(objs, name):
    """Join meshes into one object (applies their modifiers first). Returns the joined object."""
    objs = [o for o in objs if o.type == "MESH"]
    for o in objs:
        apply_modifiers(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    out = bpy.context.view_layer.objects.active
    out.name = name
    out.data.name = name
    return out


def mirror_x(obj, apply=False):
    m = obj.modifiers.new("MirrorX", "MIRROR")
    m.use_axis[0] = True
    m.use_clip = True
    if apply:
        apply_modifiers(obj, only=[m.name])
    return obj


def smart_uv(obj, angle=66, margin=0.02):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def uv_all(objs=None):
    for o in objs or [o for o in bpy.data.objects if o.type == "MESH"]:
        if not o.data.uv_layers:
            smart_uv(o)


def parent_keep(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    return child


def world_bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    mn = Vector((1e9, 1e9, 1e9))
    mx = Vector((-1e9, -1e9, -1e9))
    for o in objs:
        if o.type not in {"MESH", "CURVE", "SURFACE", "META", "FONT"}:
            continue
        ev = o.evaluated_get(dg)
        for c in ev.bound_box:
            w = ev.matrix_world @ Vector(c)
            mn = Vector(map(min, mn, w))
            mx = Vector(map(max, mx, w))
    return mn, mx


def stats(objs=None):
    """Print triangle counts per object and total (evaluated, i.e. after modifiers)."""
    dg = bpy.context.evaluated_depsgraph_get()
    total = 0
    rows = []
    for o in objs or [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render]:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        ev.to_mesh_clear()
        total += tris
        rows.append((tris, o.name))
    for t, n in sorted(rows, reverse=True)[:40]:
        print(f"  {t:>8} tris  {n}")
    print(f"TOTAL TRIS: {total}")
    mn, mx = world_bounds(objs or bpy.context.scene.objects)
    print(f"BOUNDS min={tuple(round(v, 3) for v in mn)} max={tuple(round(v, 3) for v in mx)} "
          f"size={tuple(round(v, 3) for v in (mx - mn))}")
    return total


# ------------------------------------------------------------------------------------------ rendering
def _set_engine(scene, prefer=("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "CYCLES")):
    for eng in prefer:
        try:
            scene.render.engine = eng
            return eng
        except TypeError:
            continue
    return scene.render.engine


def setup_cycles_gpu(scene, samples=64):
    _set_engine(scene, ("CYCLES",))
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    if os.environ.get("VALETF_RENDER_CPU"):
        scene.cycles.device = "CPU"
        return
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = dev_type
                prefs.get_devices()
                for d in prefs.devices:
                    d.use = d.type == dev_type
                scene.cycles.device = "GPU"
                break
            except Exception:
                continue
    except Exception:
        scene.cycles.device = "CPU"


def setup_studio(scene=None, bg=(0.10, 0.11, 0.13), strength=1.0, floor=False):
    """3-point studio light rig + soft world, stylised readable lighting like an agent-select screen."""
    scene = scene or bpy.context.scene
    world = bpy.data.worlds.get("Studio") or bpy.data.worlds.new("Studio")
    world.use_nodes = True
    bgn = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bgn.inputs[0].default_value = (*bg, 1)
    bgn.inputs[1].default_value = 0.6 * strength
    scene.world = world
    col = collection("_Lights")
    for name, loc, energy, size, color in [
        ("Key", (-3.0, -4.0, 4.0), 900, 3.0, (1.0, 0.96, 0.92)),
        ("Fill", (4.0, -3.0, 2.0), 350, 4.0, (0.85, 0.9, 1.0)),
        ("Rim", (1.5, 4.5, 3.5), 900, 2.0, (0.75, 0.9, 1.0)),
        ("RimL", (-2.5, 4.0, 2.0), 500, 2.0, (1.0, 0.85, 0.8)),
    ]:
        if bpy.data.objects.get("L_" + name):
            continue
        ld = bpy.data.lights.new("L_" + name, "AREA")
        ld.energy = energy * strength
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new("L_" + name, ld)
        lo.location = loc
        d = Vector((0, 0, 1.0)) - Vector(loc)
        lo.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        col.objects.link(lo)
    if floor and not bpy.data.objects.get("_Floor"):
        bpy.ops.mesh.primitive_plane_add(size=40)
        fl = bpy.context.active_object
        fl.name = "_Floor"
        assign(fl, material("_FloorMat", (0.08, 0.085, 0.1), rough=0.8))
        link(fl, col)
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass


VIEW_DIRS = {
    "front": (0, -1, 0.08),
    "back": (0, 1, 0.08),
    "right": (1, 0, 0.05),
    "left": (-1, 0, 0.05),
    "top": (0, -0.001, 1),
    "three_quarter": (0.75, -1, 0.35),
    "three_quarter_back": (-0.8, 0.9, 0.35),
    "low": (0.6, -1, -0.15),
}


def render_views(out_dir, prefix, objs=None, views=("front", "right", "three_quarter", "back"),
                 res=(900, 900), engine="EEVEE", samples=32, lens=85, margin=1.12, ortho=False,
                 focus=None):
    """Render the given objects from several directions, auto-framed. Writes {prefix}_{view}.png.

    engine: "EEVEE" (fast) or "CYCLES" (GPU, nicer). focus: optional (center, radius) to frame a detail.
    Returns list of file paths. out_dir is made absolute (relative render paths land in odd places).
    """
    scene = bpy.context.scene
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    if engine.upper().startswith("CYC"):
        setup_cycles_gpu(scene, samples)
    else:
        _set_engine(scene)
        try:
            scene.eevee.taa_render_samples = samples
        except Exception:
            pass
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    objs = objs or [o for o in scene.objects if o.type == "MESH" and not o.name.startswith("_")
                    and not o.hide_render]
    if focus:
        center, radius = Vector(focus[0]), focus[1]
    else:
        mn, mx = world_bounds(objs)
        center = (mn + mx) / 2
        radius = (mx - mn).length / 2
    cam_data = bpy.data.cameras.get("_PreviewCam") or bpy.data.cameras.new("_PreviewCam")
    cam = bpy.data.objects.get("_PreviewCam") or bpy.data.objects.new("_PreviewCam", cam_data)
    if cam.name not in scene.collection.objects:
        scene.collection.objects.link(cam)
    cam_data.lens = lens
    cam_data.clip_start = 0.01
    cam_data.clip_end = 1000
    scene.camera = cam
    paths = []
    for v in views:
        d = Vector(VIEW_DIRS[v] if isinstance(v, str) else v).normalized()
        if ortho:
            cam_data.type = "ORTHO"
            cam_data.ortho_scale = radius * 2 * margin
            dist = radius * 4
        else:
            cam_data.type = "PERSP"
            fov = 2 * math.atan(cam_data.sensor_width / (2 * lens))
            dist = radius * margin / math.sin(fov / 2)
        cam.location = center + d * dist
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        name = v if isinstance(v, str) else "v" + "_".join(str(round(x, 2)) for x in v)
        p = os.path.join(out_dir, f"{prefix}_{name}.png")
        scene.render.filepath = p
        try:
            bpy.ops.render.render(write_still=True)
        except RuntimeError as e:  # GPU busy / out of memory (ComfyUI shares the GPU): fall back to CPU Cycles
            print("render failed, retrying on CPU Cycles:", e)
            _set_engine(scene, ("CYCLES",))
            scene.cycles.device = "CPU"
            scene.cycles.samples = min(samples, 48)
            scene.cycles.use_denoising = True
            bpy.ops.render.render(write_still=True)
        paths.append(p)
        print("rendered", p)
    return paths


def contact_sheet(paths, out, cols=2, label=True):
    """Combine preview renders into one image (needs nothing but Blender's image API)."""
    imgs = [bpy.data.images.load(p, check_existing=False) for p in paths]
    w, h = imgs[0].size
    rows = math.ceil(len(imgs) / cols)
    sheet = bpy.data.images.new("_sheet", w * cols, h * rows)
    import numpy as np
    buf = np.zeros((h * rows, w * cols, 4), dtype=np.float32)
    for i, im in enumerate(imgs):
        px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
        r, c = divmod(i, cols)
        y0 = (rows - 1 - r) * h
        buf[y0:y0 + h, c * w:(c + 1) * w] = px
    sheet.pixels = buf.ravel()
    sheet.filepath_raw = out
    sheet.file_format = "PNG"
    sheet.save()
    print("sheet", out)
    return out


# --------------------------------------------------------------------------------------------- export
def export_all(base_path, objs=None, glb=True, fbx=True, blend=True):
    """Save .blend and export .glb / .fbx next to base_path (no extension).
    objs: restrict export to these objects (default: every visible non-helper object)."""
    os.makedirs(os.path.dirname(base_path), exist_ok=True)
    scene = bpy.context.scene
    objs = objs or [o for o in scene.objects if not o.name.startswith(("_", "L_")) and o.type in
                    {"MESH", "ARMATURE", "EMPTY"}]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]
    if glb:
        bpy.ops.export_scene.gltf(filepath=base_path + ".glb", export_format="GLB", use_selection=True,
                                  export_apply=True, export_yup=True)
        print("exported", base_path + ".glb")
    if fbx:
        bpy.ops.export_scene.fbx(filepath=base_path + ".fbx", use_selection=True, apply_unit_scale=True,
                                 apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                                 use_mesh_modifiers=True, add_leaf_bones=False, path_mode="COPY",
                                 embed_textures=True)
        print("exported", base_path + ".fbx")
    if blend:
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=base_path + ".blend", compress=True)
        print("saved", base_path + ".blend")
