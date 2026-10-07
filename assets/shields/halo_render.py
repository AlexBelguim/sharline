"""Showcase renders for the HALO kit (imported by build_halo.py after the kit is built and saved)."""
import math
import os
import random

import bpy
import numpy as np
from mathutils import Euler, Vector

import blender_common as bc
from halo_lib import D, PIP_POS, TIERS, WEIGHT, ZONES, _mat, set_strength

SHOW_COL = "_SHOW"
CHAR_GLB = r"F:/git/val etf/assets/characters/kestrel/trellis/kestrel_trellis_s123.glb"

# emission strengths per state
STRENGTH = {"lit": 2.4, "idle": 0.7, "flare": 6.0}
CELL_SHOW_ANGLES = {"Light": [335.0], "Medium": [335.0, 155.0], "Heavy": [95.0, 215.0, 335.0]}


# ------------------------------------------------------------------------------------------ scene utils
def show_col():
    col = bpy.data.collections.get(SHOW_COL)
    if col is None:
        col = bpy.data.collections.new(SHOW_COL)
        bpy.context.scene.collection.children.link(col)
    return col


def clear_show():
    col = bpy.data.collections.get(SHOW_COL)
    if col:
        for o in list(col.all_objects):
            bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.curves):
        if c.users == 0:
            bpy.data.curves.remove(c)


def kit_visible(flag):
    lc = bpy.context.view_layer.layer_collection.children.get("HALO_Kit")
    if lc:
        lc.exclude = not flag


_MCACHE = {}


def glass(tier, state):
    """Render-only copy of a tier material at a given emission strength (lit / idle / flare / number)."""
    if tier in (None, 0, "off"):
        return bpy.data.materials["M_HALO_Glass_Off"]
    s = STRENGTH[state] if isinstance(state, str) else float(state)
    key = (tier, round(s, 3))
    if key not in _MCACHE:
        m = bpy.data.materials[f"M_HALO_Glass_T{tier}"].copy()
        m.name = f"_SHOW_T{tier}_{s:g}"
        set_strength(m, s)
        _MCACHE[key] = m
    return _MCACHE[key]


def inst(src_name, parent, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0, slot_mats=None, name=None):
    src = bpy.data.objects[src_name]
    o = src.copy()
    o.name = name or ("_s_" + src_name)
    show_col().objects.link(o)
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    o.scale = (scale, scale, scale)
    if slot_mats:
        for i, m in slot_mats.items():
            if m is None:
                continue
            o.material_slots[i].link = "OBJECT"
            o.material_slots[i].material = m
    return o


def empty(name, loc=(0, 0, 0), rot=(0, 0, 0), scale=1.0, parent=None):
    e = bpy.data.objects.new(name, None)
    show_col().objects.link(e)
    e.location = loc
    e.rotation_euler = rot
    e.scale = (scale, scale, scale)
    e.parent = parent
    return e


def place_halo(core, weight, tier, loc=(0, 0, 0), rot_z=0.0, coverage=None, state="lit", pip_state=None,
               cell_state=None, cells=True, band=True, scale=None, cell_angles=None, tag="h"):
    """Assemble one halo instance from the kit.  coverage: zones that are lit (others = dark smoked glass);
    None = all lit.  state: 'lit' / 'idle' / 'flare' (lit arcs), pip_state & cell_state default to state."""
    w = WEIGHT[weight]
    sc = w["scale"] if scale is None else scale
    root = empty(f"_root_{tag}", loc, (0, 0, D(rot_z)), sc)
    cov = set(ZONES) if coverage is None else set(coverage)
    for z in ZONES:
        m = glass(tier, state) if z in cov else glass(None, None)
        inst(f"HALO_{core}_Arc_{z}", root, slot_mats={0: m})
    if band and w["band"]:
        inst(f"HALO_{core}_Band_{w['band']}", root)
    ps = pip_state or state
    for i, p in enumerate(PIP_POS):
        on = (i < tier)
        m = glass(tier, ps) if (on and ps != "off") else glass(None, None)
        inst("HALO_TierPip", root, loc=p, slot_mats={0: m})
    if cells:
        cs = cell_state or state
        angs = cell_angles if cell_angles is not None else CELL_SHOW_ANGLES[weight]
        for a in angs:
            r = w["orbit_r"]
            p = (r * math.cos(D(a)), r * math.sin(D(a)), w["orbit_z"])
            # cell travels counter-clockwise: local +X along the tangent
            inst("HALO_PowerCell", root, loc=p, rot=(0, 0, D(a + 90)), slot_mats={0: glass(tier, cs)})
    return root


# ------------------------------------------------------------------------------------------ camera / labels
def camera(name="_Cam", loc=(0, -2, 1), target=(0, 0, 0), lens=60, ortho=None):
    cd = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, cd)
        bpy.context.scene.collection.objects.link(cam)
    cd.clip_start = 0.005
    cd.clip_end = 200
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.type = "PERSP"
        cd.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def cam_from(target, elev_deg, azim_deg, dist, lens=60, ortho=None):
    """azim 0 = camera in front of the halo (at -Y) looking +Y; positive azim swings toward +X."""
    t = Vector(target)
    e, a = D(elev_deg), D(azim_deg)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    return camera(loc=t + d * dist, target=t, lens=lens, ortho=ortho)


def label_mat(color=(0.85, 0.87, 0.9), strength=1.0):
    nm = f"_SHOW_Label_{color[0]:.2f}_{strength:g}"
    return _mat(nm, (0, 0, 0), rough=1.0, emission=color, strength=strength, spec=0.0)


def hud(text, x, y, size=0.04, color=(0.85, 0.87, 0.9), align="LEFT", strength=1.0):
    """Text fixed to the camera. x, y in [-1, 1] frame coordinates (y up)."""
    sc = bpy.context.scene
    cam = sc.camera
    cd = cam.data
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    dist = 0.5
    if cd.type == "ORTHO":
        hw = cd.ortho_scale / 2 if rx >= ry else cd.ortho_scale / 2 * rx / ry
        dist = 0.5
        hh = hw * ry / rx
    else:
        half = (cd.sensor_width / 2) / cd.lens * dist
        if rx >= ry:
            hw, hh = half, half * ry / rx
        else:
            hw, hh = half * rx / ry, half
    cu = bpy.data.curves.new("_lbl", "FONT")
    cu.body = text
    cu.align_x = align
    cu.align_y = "CENTER"
    cu.size = size * max(hw, hh) * 2
    ob = bpy.data.objects.new("_lbl", cu)
    show_col().objects.link(ob)
    ob.data.materials.append(label_mat(color, strength))
    ob.parent = cam
    ob.location = (x * hw, y * hh, -dist)
    return ob


# ------------------------------------------------------------------------------------------ render setup
def setup_render(res=(1600, 1000), samples=64, bloom=0.5, bg=(0.032, 0.034, 0.04), transparent=False,
                 threshold=1.0, size=0.40):
    sc = bpy.context.scene
    try:
        sc.render.engine = "BLENDER_EEVEE"
    except TypeError:
        pass
    sc.eevee.taa_render_samples = samples
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    view = os.environ.get("HALO_VIEW", "Khronos PBR Neutral")
    try:
        sc.view_settings.view_transform = view
        if view == "AgX":
            sc.view_settings.look = os.environ.get("HALO_LOOK", "AgX - Medium High Contrast")
    except Exception as e:
        print("view transform", e)
    world = sc.world
    bgn = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bgn.inputs[0].default_value = (*bg, 1)
    # bloom through the compositor (Blender 5.x node-group compositor)
    if bloom and not transparent:
        ng = bpy.data.node_groups.get("_HaloComp")
        if ng is None:
            ng = bpy.data.node_groups.new("_HaloComp", "CompositorNodeTree")
            ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        ng.nodes.clear()
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        gl.inputs["Type"].default_value = "Bloom"
        gl.inputs["Threshold"].default_value = threshold
        gl.inputs["Strength"].default_value = bloom
        gl.inputs["Size"].default_value = size
        try:
            gl.inputs["Quality"].default_value = "High"
        except Exception:
            pass
        out = ng.nodes.new("NodeGroupOutput")
        ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
        ng.links.new(gl.outputs[0], out.inputs[0])
        sc.compositing_node_group = ng
        sc.render.use_compositing = True
    else:
        sc.render.use_compositing = False


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("EEVEE render failed, retrying on CPU Cycles:", e)
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.samples = 48
        sc.cycles.use_denoising = True
        bpy.ops.render.render(write_still=True)
        sc.render.engine = "BLENDER_EEVEE"
    print("RENDERED", path)
    return path


def lights(kind="studio", strength=1.0, offset=(0.0, 0.0, 0.0)):
    """Replace the studio lights with a rig suited to dark glowing props."""
    for o in list(bpy.data.objects):
        if o.name.startswith("L_"):
            bpy.data.objects.remove(o, do_unlink=True)
    col = bc.collection("_Lights")
    rigs = {
        "studio": [("Key", (-2.5, -3.0, 3.0), 420, 1.2, (1.0, 0.96, 0.92)),
                   ("Fill", (3.5, -2.5, 1.0), 120, 2.0, (0.85, 0.9, 1.0)),
                   ("Rim", (1.2, 4.0, 1.6), 520, 1.0, (0.75, 0.88, 1.0)),
                   ("RimL", (-3.0, 3.0, 1.0), 260, 1.0, (1.0, 0.9, 0.85))],
    }
    for name, loc, energy, size, color in rigs[kind]:
        ld = bpy.data.lights.new("L_" + name, "AREA")
        ld.energy = energy * strength
        ld.size = size
        ld.color = color
        lo = bpy.data.objects.new("L_" + name, ld)
        lo.location = Vector(loc) + Vector(offset)
        lo.rotation_euler = (Vector((0, 0, 0.2)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        col.objects.link(lo)


def floor(z=0.0, color=(0.05, 0.055, 0.065), size=30):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2)
    me = bpy.data.meshes.new("_ShowFloor")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("_ShowFloor", me)
    show_col().objects.link(o)
    o.location = (0, 0, z)
    o.data.materials.append(_mat("_SHOW_Floor", color, rough=0.75))
    return o


def to_silhouette(src, dst, thresh=0.35):
    im = bpy.data.images.load(src, check_existing=False)
    w, h = im.size
    px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
    a = px[..., 3]
    out = np.ones_like(px)
    mask = a > thresh
    out[mask, 0:3] = 0.0
    out[..., 3] = 1.0
    o = bpy.data.images.new("_sil", w, h)
    o.pixels = out.ravel()
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(im)
    bpy.data.images.remove(o)
    print("SILHOUETTE", dst)
    return dst


def stack(paths, out, cols=2):
    return bc.contact_sheet(paths, out, cols=cols)


# ------------------------------------------------------------------------------------------ showcases
CORE_ORDER = ("Bulwark", "Mender", "Volt", "Phase")


def r_cores_grid(out_dir):
    clear_show()
    setup_render(res=(1800, 1500), bloom=0.45)
    lights()
    sx, sy = 0.50, 0.62
    for r, core in enumerate(CORE_ORDER):
        for c, t in enumerate((1, 2, 3, 4)):
            place_halo(core, "Medium", t, loc=((c - 1.5) * sx, (r - 1.5) * -sy * -1, 0), band=False,
                       cells=False, scale=1.0, state="lit", tag=f"{core}{t}")
    # camera looks from the front (-Y) and above; rows go back in +Y (Bulwark at the front)
    cam_from((0, 0, 0), 38, 0, 8.0, ortho=2.45)
    for c, t in enumerate((1, 2, 3, 4)):
        hud(f"T{t}", -0.555 + c * 0.405, 0.9, size=0.03, align="CENTER", color=TIERS[t], strength=2.0)
    for r, core in enumerate(CORE_ORDER):
        hud(core.upper(), -0.97, -0.62 + r * 0.42, size=0.022)
    return [render(os.path.join(out_dir, "01_cores_tiers_grid.png"))]


def r_weight_lineup(out_dir, core="Volt", tier=2, tag=""):
    clear_show()
    paths = []
    xs = {"Light": -0.62, "Medium": 0.0, "Heavy": 0.70}
    for wname, x in xs.items():
        place_halo(core, wname, tier, loc=(x, 0, 0), state="lit", tag=wname)
    cam_from((0.04, 0, 0.0), 20, 0, 8.0, ortho=1.95)
    # normal render
    setup_render(res=(1800, 760), bloom=0.45)
    lights()
    for wname, x in xs.items():
        hud(wname.upper(), (x + 0.0) / (1.95 / 2) - 0.04, -0.82, size=0.03, align="CENTER")
    p = render(os.path.join(out_dir, f"02_weight_lineup{tag}.png"))
    paths.append(p)
    # silhouette: transparent film, no labels
    for o in list(show_col().objects):
        if o.name.startswith("_lbl"):
            bpy.data.objects.remove(o, do_unlink=True)
    setup_render(res=(1800, 760), bloom=0, transparent=True)
    tmp = os.path.join(out_dir, "_tmp_alpha.png")
    render(tmp)
    paths.append(to_silhouette(tmp, os.path.join(out_dir, f"02_weight_lineup_silhouette{tag}.png")))
    os.remove(tmp)
    return paths


def r_weight_eyelevel(out_dir, core="Bulwark", tier=3):
    """Weight classes as seen in play: another player's eye is ~0.3 m below the halo, 2-20 m away
    (-1 to -8 deg).  Rendered at -5 deg, colour + silhouette."""
    clear_show()
    xs = {"Light": -0.62, "Medium": 0.0, "Heavy": 0.70}
    for wname, x in xs.items():
        place_halo(core, wname, tier, loc=(x, 0, 0), state="idle", pip_state="idle", cell_state=1.6, tag=wname)
    cam_from((0.06, 0, 0.0), -5, 0, 8.0, ortho=2.1)
    setup_render(res=(1800, 500), bloom=0.4)
    lights()
    for wname, x in xs.items():
        hud(wname.upper() + "  (idle)", (x - 0.06) / (2.1 / 2), -0.75, size=0.03, align="CENTER")
    hud("eye-level view from below (-5 deg), idle glow", -0.97, 0.82, size=0.028)
    p1 = render(os.path.join(out_dir, "02c_weight_eyelevel_idle.png"))
    for o in list(show_col().objects):
        if o.name.startswith("_lbl"):
            bpy.data.objects.remove(o, do_unlink=True)
    setup_render(res=(1800, 500), bloom=0, transparent=True)
    tmp = os.path.join(out_dir, "_tmp_alpha.png")
    render(tmp)
    p2 = to_silhouette(tmp, os.path.join(out_dir, "02c_weight_eyelevel_silhouette.png"))
    os.remove(tmp)
    return [p1, p2]


def r_weight_silhouette_all(out_dir):
    clear_show()
    xs = {"Light": -0.62, "Medium": 0.0, "Heavy": 0.70}
    for r, core in enumerate(CORE_ORDER):
        for wname, x in xs.items():
            place_halo(core, wname, 2, loc=(x, 0, -r * 0.30), state="lit", tag=f"{core}{wname}")
    cam_from((0.04, 0, -0.45), 20, 0, 8.0, ortho=2.05)
    setup_render(res=(1500, 1500), bloom=0, transparent=True)
    tmp = os.path.join(out_dir, "_tmp_alpha.png")
    render(tmp)
    p = to_silhouette(tmp, os.path.join(out_dir, "02b_weight_silhouette_all_cores.png"))
    os.remove(tmp)
    return [p]


def r_coverage(out_dir):
    clear_show()
    setup_render(res=(1800, 900), bloom=0.5)
    lights()
    cov = ("Head", "Torso")
    for i, core in enumerate(CORE_ORDER):
        place_halo(core, "Medium", 2, loc=((i - 1.5) * 0.56, 0, 0), coverage=cov, state="flare", pip_state="lit",
                   cell_state="lit", tag=core)
    cam_from((0, 0.0, 0), 42, 0, 8.0, ortho=2.35)
    hud("COVERAGE  HEAD + TORSO lit  /  ARMS + LEGS dark      (front = HEAD, toward camera)", -0.96, 0.88,
        size=0.022)
    for i, core in enumerate(CORE_ORDER):
        hud(core.upper(), -0.715 + i * 0.477, -0.8, size=0.024, align="CENTER")
    return [render(os.path.join(out_dir, "03_coverage_head_torso.png"))]


def import_character():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=CHAR_GLB)
    new = [o for o in bpy.data.objects if o not in before]
    col = show_col()
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    meshes = [o for o in new if o.type == "MESH"]
    roots = [o for o in new if o.parent is None]
    mn, mx = bc.world_bounds(meshes)
    s = 1.70 / (mx.z - mn.z)
    for r in roots:
        r.scale = r.scale * s
        r.location = r.location * s
    bpy.context.view_layer.update()
    mn, mx = bc.world_bounds(meshes)
    off = Vector((-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z))
    for r in roots:
        r.location += off
    bpy.context.view_layer.update()
    # head top + skull centre from the top 12 cm of vertices
    pts = []
    for o in meshes:
        mw = o.matrix_world
        for v in o.data.vertices:
            w = mw @ v.co
            pts.append((w.x, w.y, w.z))
    P = np.array(pts)
    top = P[:, 2].max()
    head = P[P[:, 2] > top - 0.12]
    cx, cy = float(np.median(head[:, 0])), float(np.median(head[:, 1]))
    print(f"CHARACTER top={top:.3f} skull centre=({cx:.3f},{cy:.3f})")
    return meshes, Vector((cx, cy, top))


def spawn_shards(root_loc, tier, n=34, seed=7, scale=1.0, hit_dir=(0, -1, 0)):
    """Hex shards bursting from a hit on the front (Head) arc."""
    rnd = random.Random(seed)
    names = ["HALO_Shard_A", "HALO_Shard_B", "HALO_Shard_C"]
    hit = Vector(root_loc) + Vector((0.03, -0.165 * scale, 0.006))
    hd = Vector(hit_dir).normalized()
    out = []
    for i in range(n):
        # cone around the hit direction, biased outward + upward
        th = D(rnd.uniform(-80, 80))
        ph = D(rnd.uniform(-22, 38))
        d = Vector((math.sin(th) * math.cos(ph), -math.cos(th) * math.cos(ph), math.sin(ph)))
        dist = 0.02 + 0.20 * rnd.random() ** 1.3
        p = hit + d * dist
        s = rnd.uniform(0.45, 1.0) * (1.1 - 0.55 * dist / 0.22)
        strength = 10.0 * (1.1 - dist / 0.24) + 2.0
        m = glass(tier, max(2.0, strength))
        o = inst(names[i % 3], None, loc=p,
                 rot=(rnd.uniform(0, 6.28), rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)),
                 scale=s * scale, slot_mats={0: m}, name=f"_shard{i}")
        out.append(o)
    return hit, out


def sprite_plane(img_path, loc, size, tier, strength=6.0, face=None, name="_flash", color=None):
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.uv_layers.new(name="UV")
    uv = me.uv_layers[0].data
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv[li].uv = (v.x / size + 0.5, v.y / size + 0.5)
    o = bpy.data.objects.new(name, me)
    show_col().objects.link(o)
    o.location = loc
    if face is not None:
        o.rotation_euler = (Vector(face) - Vector(loc)).to_track_quat("Z", "Y").to_euler()
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(img_path, check_existing=True)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*(color or TIERS[tier]), 1)
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], mul.inputs[0])
    nt.links.new(mul.outputs[0], em.inputs["Strength"])
    nt.links.new(tex.outputs["Alpha"], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], outn.inputs["Surface"])
    try:
        mat.surface_render_method = "BLENDED"
    except Exception:
        pass
    o.data.materials.append(mat)
    return o


def r_character(out_dir, sprites_dir, core="Bulwark", weight="Medium", tier=3,
                coverage=("Head", "Torso", "Arms")):
    clear_show()
    meshes, head_top = import_character()
    sock = head_top + Vector((0, 0, 0.22))
    paths = []
    tgt = Vector((sock.x, sock.y, sock.z - 0.21))
    for state in ("idle", "hit"):
        for o in list(show_col().objects):
            if o.name.startswith(("_root", "_s_", "_shard", "_flash", "_crack", "_lbl")):
                bpy.data.objects.remove(o, do_unlink=True)
        setup_render(res=(1200, 1400), bloom=0.55 if state == "hit" else 0.4, bg=(0.05, 0.055, 0.068))
        lights(offset=(0.0, 0.0, 1.7))
        if state == "idle":
            place_halo(core, weight, tier, loc=sock, coverage=None, state="idle", pip_state="idle",
                       cell_state=1.6, cell_angles=[50.0, 230.0], tag="char")
        else:
            place_halo(core, weight, tier, loc=sock, coverage=coverage, state="flare", pip_state="flare",
                       cell_state=6.0, cell_angles=[62.0, 242.0], tag="char")
            hit, _ = spawn_shards(sock, tier, n=30, seed=11)
            cam_loc = Vector((0.85, -1.95, 1.66))
            sprite_plane(os.path.join(sprites_dir, "hex_hit_flash.png"), hit + Vector((0, -0.012, 0)), 0.15, tier,
                         strength=4.0, face=cam_loc, name="_flash")
            # crack decal on the struck arc's outer glass wall (remaining shield shown as cracks)
            ws = WEIGHT[weight]["scale"]
            crack_at = Vector((sock.x - 0.035 * ws, sock.y - 0.1685 * ws, sock.z + 0.001 * ws))
            sprite_plane(os.path.join(sprites_dir, "crack_overlay.png"), crack_at, 0.075 * ws, tier, strength=7.0,
                         face=crack_at + Vector((0, -1, 0)), name="_crack", color=(0.95, 0.9, 1.0))
        cam = camera(loc=(0.85, -1.95, 1.66), target=tgt, lens=62)
        hud(f"{core.upper()}  T{tier}  {weight.upper()}  -  {'IDLE (dim)' if state == 'idle' else 'HIT (flare)'}",
            -0.92, 0.9, size=0.03)
        if state == "hit":
            hud("lit: " + " + ".join(coverage) + "   dark: " + " + ".join(z for z in ZONES if z not in coverage),
                -0.92, 0.82, size=0.022, color=(0.6, 0.63, 0.68))
        paths.append(render(os.path.join(out_dir, f"04_character_{state}.png")))
    stack(paths, os.path.join(out_dir, "04_character_idle_vs_hit.png"), cols=2)
    # wide shot showing the whole agent with the halo
    for o in list(show_col().objects):
        if o.name.startswith(("_root", "_s_", "_shard", "_flash", "_lbl")):
            bpy.data.objects.remove(o, do_unlink=True)
    setup_render(res=(1000, 1400), bloom=0.4, bg=(0.05, 0.055, 0.068))
    lights(offset=(0.0, 0.0, 1.2))
    place_halo(core, weight, tier, loc=sock, state="idle", pip_state="idle", cell_state=1.6,
               cell_angles=[50.0, 230.0], tag="char")
    camera(loc=(1.9, -3.6, 1.60), target=(0, 0, 1.05), lens=50)
    hud("Kestrel 1.70 m  -  halo socket 0.22 m above head (idle)", -0.92, 0.92, size=0.03)
    paths.append(render(os.path.join(out_dir, "04_character_fullbody_idle.png")))
    for o in meshes:
        pass
    return paths


def r_pickups(out_dir):
    clear_show()
    setup_render(res=(1800, 800), bloom=0.45)
    lights()
    floor(0.0, color=(0.006, 0.0065, 0.008))
    tiers = {"Bulwark": 3, "Mender": 1, "Volt": 2, "Phase": 4}
    for i, core in enumerate(CORE_ORDER):
        inst(f"HALO_Core_{core}", None, loc=((i - 1.5) * 0.125, 0, 0), rot=(0, 0, D(-20)),
             slot_mats={0: glass(tiers[core], 3.0)})
    cam_from((0, 0, 0.026), 24, 10, 1.5, lens=85)
    for i, core in enumerate(CORE_ORDER):
        hud(f"{core.upper()}  T{tiers[core]}", -0.66 + i * 0.44, -0.80, size=0.024, align="CENTER")
    return [render(os.path.join(out_dir, "05_pickup_cores.png"))]


def r_turnaround(out_dir, core="Bulwark", weight="Heavy", tier=4):
    clear_show()
    setup_render(res=(900, 900), bloom=0.45)
    lights()
    place_halo(core, weight, tier, state="lit", tag="turn")
    paths = []
    for v, (el, az) in {"front": (8, 0), "right": (8, 90), "back": (8, 180), "three_quarter": (35, 40)}.items():
        cam_from((0, 0, 0), el, az, 6.0, ortho=0.82)
        paths.append(render(os.path.join(out_dir, f"halo_{v}.png")))
    stack(paths, os.path.join(out_dir, "halo_sheet.png"), cols=2)
    return paths


def r_parts(out_dir):
    """Close-up of the small parts: pip row, power cell, shards."""
    clear_show()
    setup_render(res=(1600, 800), bloom=0.45)
    lights()
    for i in range(4):
        inst("HALO_TierPip", None, loc=(-0.215 + i * 0.020, 0, 0.0), scale=1.6, slot_mats={0: glass(i + 1, 2.4)})
    inst("HALO_PowerCell", None, loc=(-0.005, 0, 0), scale=1.6, slot_mats={0: glass(2, 2.4)})
    for i, nm in enumerate(("A", "B", "C")):
        inst(f"HALO_Shard_{nm}", None, loc=(0.085 + i * 0.05, 0, 0), rot=(D(60), D(10), D(20 * i)), scale=1.4,
             slot_mats={0: glass(3, 2.4)})
    cam_from((-0.02, 0, 0.0), 25, 0, 2.0, ortho=0.50)
    hud("TIER PIPS T1-T4", -0.88, -0.75, size=0.022)
    hud("POWER CELL  (travels +X, trail fin behind)", -0.42, -0.75, size=0.022)
    hud("SHARDS A / B / C", 0.5, -0.75, size=0.022)
    return [render(os.path.join(out_dir, "06_parts.png"))]
