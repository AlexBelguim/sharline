"""Showcase renders for the HALO kit (imported by build_halo.py after the kit is built and saved).

place_halo() is the reference assembly for the engine: the weight class is always DERIVED from the arc tiers
(sum of the arc tiers, game rule), never passed in, so a render can never disagree with the game.
"""
import math
import os
import random

import bpy
import numpy as np
from mathutils import Vector

import blender_common as bc
import halo_parts as hp
from halo_lib import D, EDGE, TIERS, WEIGHT, ZONES, _mat, preset_tiers, set_strength, weight_of

SHOW_COL = "_SHOW"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
CHAR_GLB = os.path.join(REPO, "assets", "characters", "kestrel", "trellis", "kestrel_trellis_s123.glb")

# emission strengths per state (lit arcs, pips, cells, band lip)
STRENGTH = {"lit": 2.4, "idle": 0.9, "flare": 6.0}
CORE_ORDER = ("Bulwark", "Mender", "Volt", "Phase")
WEIGHTS = ("Light", "Medium", "Heavy")
DARK_BG = (0.032, 0.034, 0.04)
DAY_BG = (0.32, 0.36, 0.42)

# game-legal coverage used in the in-play renders (sum of arc tiers -> weight class)
PLAY = {"Light": {"Head": 0, "Torso": 1, "Arms": 0, "Legs": 0},      # T1 torso only (Phase Runner style), 1
        "Medium": {"Head": 2, "Torso": 2, "Arms": 0, "Legs": 2},     # Volt Sentry style, 6
        "Heavy": {"Head": 3, "Torso": 3, "Arms": 3, "Legs": 0}}      # Bulwark Assault style, 9
UNIFORM = {"Light": 1, "Medium": 2, "Heavy": 3}                      # full coverage at T1/T2/T3 = 4 / 8 / 12


def uniform(t):
    return {z: t for z in ZONES}


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


def remove_labels():
    for o in list(show_col().objects):
        if o.name.startswith("_lbl"):
            bpy.data.objects.remove(o, do_unlink=True)


def kit_visible(flag):
    lc = bpy.context.view_layer.layer_collection.children.get("HALO_Kit")
    if lc:
        lc.exclude = not flag


_MCACHE = {}


def glass(tier, state="lit"):
    """Render material for an arc / pip / cell / band lip.
    tier 0 / None = uncovered (M_HALO_Glass_Off); ("B", t) = broken arc (M_HALO_Glass_Broken_T<t>, as shipped);
    otherwise a copy of M_HALO_Glass_T<tier> at the state's emission strength (lit / idle / flare / number)."""
    if tier in (None, 0, "off"):
        return bpy.data.materials["M_HALO_Glass_Off"]
    if isinstance(tier, tuple):
        return bpy.data.materials[f"M_HALO_Glass_Broken_T{tier[1]}"]
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
    o.hide_set(False)
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    o.scale = (scale, scale, scale)
    if slot_mats:
        for i, m in slot_mats.items():
            if m is None or i >= len(o.material_slots):
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


def arc_tier(t):
    """Arc entry -> tier number (broken arcs ("B", t) count with their tier)."""
    return t[1] if isinstance(t, tuple) else int(t or 0)


def slot_of(obj_name, mat_name):
    """Material slot index of `mat_name` in a kit object (primitives are found by material name, never by index)."""
    for i, sl in enumerate(bpy.data.objects[obj_name].material_slots):
        if sl.material and sl.material.name == mat_name:
            return i
    return None


def place_halo(core, arc_tiers, loc=(0, 0, 0), rot_z=0.0, state="lit", pip_state=None, cell_state=None,
               cells=True, band=True, pips=True, scale=None, cell_angles=None, tag="h", far=False, cell_mesh=None,
               cell_phase=15.0):
    """Assemble one halo from the kit, the way the engine does it.
    arc_tiers: {zone: tier} with 0 = uncovered and ("B", tier) = broken (pool at 0, cracked until regen).
    The weight class (scale, frame/band, cell count, orbit) is derived from the sum of the arc tiers.
    Parts: 4 x HALO_<core>_Arc_<zone> (glass only, one material per arc) + ONE HALO_<core>_Frame_<weight>
    (graphite + edge of all arcs + the weight band, its lip glass = highest arc tier) + n pips on
    HALO_<core>_PIP_<n>_<i> (n = highest arc tier, centred row) + 1/2/3 HALO_PowerCell_<core>.
    `scale`/`band`/`cells`/`pips` overrides are only for part line-ups (band=False shows Frame_Light).
    far=True assembles the far LOD (4 far glass arcs + Far_Frame_<weight>, no pips)."""
    tiers = {z: arc_tier(arc_tiers.get(z, 0)) for z in ZONES}
    weight = weight_of(tiers)
    w = WEIGHT[weight]
    top = max(tiers.values())
    sc = w["scale"] if scale is None else scale
    root = empty(f"_root_{tag}", loc, (0, 0, D(rot_z)), sc)
    root["halo_weight"] = weight
    ps = pip_state or state
    lip = glass(top, ps)
    for z in ZONES:
        t = arc_tiers.get(z, 0)
        m = glass(t, state) if t else glass(None)
        inst(f"HALO_{core}_Far_Glass_{z}" if far else f"HALO_{core}_Arc_{z}", root, slot_mats={0: m})
    fw = weight if band else "Light"
    frame = f"HALO_{core}_Far_Frame_{fw}" if far else f"HALO_{core}_Frame_{fw}"
    ls = slot_of(frame, "M_HALO_Glass_T1")
    inst(frame, root, slot_mats={ls: lip} if ls is not None else None)
    if pips and not far and top:
        for p in hp.pip_positions(core, top):   # the engine shows exactly `top` pips, centred (PIP_<top>_<i>)
            inst("HALO_TierPip", root, loc=p, slot_mats={0: glass(top, ps)})
    if cells:
        cs = cell_state or state
        n = w["cells"]
        cname = cell_mesh or f"HALO_PowerCell_{core}"
        angs = cell_angles if cell_angles is not None else [cell_phase + k * 360.0 / n for k in range(n)]
        for a in angs[:n]:
            r = w["orbit_r"]
            p = (r * math.cos(D(a)), r * math.sin(D(a)), w["orbit_z"])
            # cell travels counter-clockwise: local +X along the tangent
            inst(cname, root, loc=p, rot=(0, 0, D(a + 90)), slot_mats={0: glass(top, cs)})
    return root


def tiers_label(at):
    return "  ".join(f"{z[0]}{arc_tier(at.get(z, 0))}" for z in ("Head", "Torso", "Arms", "Legs"))


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
    nm = f"_SHOW_Label_{color[0]:.2f}_{color[1]:.2f}_{strength:g}"
    return _mat(nm, (0, 0, 0), rough=1.0, emission=color, strength=strength, spec=0.0, cull=False)


def hud(text, x, y, size=0.04, color=(0.85, 0.87, 0.9), align="LEFT", strength=1.0):
    """Text fixed to the camera. x, y in [-1, 1] frame coordinates (y up)."""
    sc = bpy.context.scene
    cam = sc.camera
    cd = cam.data
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    dist = 0.5
    if cd.type == "ORTHO":
        hw = cd.ortho_scale / 2 if rx >= ry else cd.ortho_scale / 2 * rx / ry
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


def dark_text():
    return (0.04, 0.045, 0.06)


# ------------------------------------------------------------------------------------------ render setup
def setup_render(res=(1600, 1000), samples=64, bloom=0.5, bg=DARK_BG, transparent=False, threshold=1.0, size=0.40,
                 bg_strength=1.0):
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
    bgn.inputs[1].default_value = bg_strength
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
    """Replace the studio lights: 'studio' (dark props) or 'day' (sun, for the daylight readability renders)."""
    for o in list(bpy.data.objects):
        if o.name.startswith("L_"):
            bpy.data.objects.remove(o, do_unlink=True)
    col = bc.collection("_Lights")
    if kind == "day":
        ld = bpy.data.lights.new("L_Sun", "SUN")
        ld.energy = 3.5 * strength
        ld.angle = D(2.0)
        lo = bpy.data.objects.new("L_Sun", ld)
        lo.rotation_euler = (D(40), D(10), D(-35))
        col.objects.link(lo)
        return
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
        lo.rotation_euler = (Vector((0, 0, 0.2)) + Vector(offset) - lo.location).to_track_quat("-Z", "Y").to_euler()
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
    # pure black on white, anti-aliased: alpha >= thresh*1.4 is solid black, the soft edge keeps the AA
    v = 1.0 - np.clip(a / (thresh * 1.4), 0.0, 1.0)
    out = np.ones_like(px)
    for c in range(3):
        out[..., c] = v
    o = bpy.data.images.new("_sil", w, h)
    o.pixels = out.ravel()
    o.filepath_raw = dst
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(im)
    bpy.data.images.remove(o)
    print("SILHOUETTE", dst)
    return dst


def silhouette_pass(out_dir, name, res):
    remove_labels()
    setup_render(res=res, bloom=0, transparent=True)
    tmp = os.path.join(out_dir, "_tmp_alpha.png")
    render(tmp)
    p = to_silhouette(tmp, os.path.join(out_dir, name))
    os.remove(tmp)
    return p


def stack(paths, out, cols=2):
    return bc.contact_sheet(paths, out, cols=cols)


def vstack(paths, out, bg=(14, 15, 18)):
    """Stack images vertically (same width after scaling) with a thin gap (PIL-free, via Blender images)."""
    ims = [bpy.data.images.load(p, check_existing=False) for p in paths]
    W = max(i.size[0] for i in ims)
    arrs = []
    for im in ims:
        w, h = im.size
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
        if w != W:   # nearest resample to the common width
            s = W / w
            nh = int(round(h * s))
            yi = np.clip((np.arange(nh) / s).astype(int), 0, h - 1)
            xi = np.clip((np.arange(W) / s).astype(int), 0, w - 1)
            a = a[yi][:, xi]
        arrs.append(a)
    gap = np.zeros((12, W, 4), np.float32)
    gap[..., :3] = np.array(bg) / 255.0
    gap[..., 3] = 1
    parts = []
    for a in reversed(arrs):          # Blender images are stored bottom-up
        parts += [a, gap]
    full = np.concatenate(parts[:-1], axis=0)
    o = bpy.data.images.new("_vstack", W, full.shape[0])
    o.pixels = full.ravel()
    o.filepath_raw = out
    o.file_format = "PNG"
    o.save()
    for im in ims:
        bpy.data.images.remove(im)
    bpy.data.images.remove(o)
    print("STACKED", out)
    return out


def merge_columns(paths, out):
    """Same-size renders -> one image whose k-th column band (width / n) comes from the k-th render."""
    ims = [bpy.data.images.load(p, check_existing=False) for p in paths]
    w, h = ims[0].size
    n = len(ims)
    full = np.zeros((h, w, 4), np.float32)
    for k, im in enumerate(ims):
        a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)
        x0, x1 = round(k * w / n), round((k + 1) * w / n)
        full[:, x0:x1] = a[:, x0:x1]
    o = bpy.data.images.new("_cols", w, h)
    o.pixels = full.ravel()
    o.filepath_raw = out
    o.file_format = "PNG"
    o.save()
    for im in ims:
        bpy.data.images.remove(im)
    bpy.data.images.remove(o)
    for p in paths:
        os.remove(p)
    return out


# ------------------------------------------------------------------------------------------ showcases
def r_cores_grid(out_dir):
    clear_show()
    setup_render(res=(1800, 1500), bloom=0.45)
    lights()
    sx, sy = 0.50, 0.62
    for r, core in enumerate(CORE_ORDER):
        for c, t in enumerate((1, 2, 3, 4)):
            place_halo(core, uniform(t), loc=((c - 1.5) * sx, (r - 1.5) * sy, 0), band=False, cells=False,
                       scale=1.0, state="lit", tag=f"{core}{t}")
    cam_from((0, 0, 0), 38, 0, 8.0, ortho=2.45)
    for c, t in enumerate((1, 2, 3, 4)):
        hud(f"T{t}", -0.555 + c * 0.405, 0.9, size=0.03, align="CENTER", color=TIERS[t], strength=2.0)
    for r, core in enumerate(CORE_ORDER):
        hud(core.upper(), -0.97, -0.62 + r * 0.42, size=0.022)
    return [render(os.path.join(out_dir, "01_cores_tiers_grid.png"))]


LINEUP_PRESETS = [("Light", "Phase", "arm_phase_runner"), ("Medium", "Volt", "arm_volt_line"),
                  ("Heavy", "Bulwark", "arm_bulwark_assault")]


def r_weight_lineup(out_dir, core="Volt"):
    """Light / Medium / Heavy, 20 deg above.  Row 1: one core with full coverage at T1/T2/T3 (= 4 / 8 / 12, the
    only uniform tiers that are game-legal per weight).  Row 2: the game presets."""
    clear_show()
    xs = {"Light": -0.66, "Medium": 0.0, "Heavy": 0.74}
    for wname, x in xs.items():
        place_halo(core, uniform(UNIFORM[wname]), loc=(x, 0, 0.17), state="lit", tag="u" + wname)
    for wname, pcore, pid in LINEUP_PRESETS:
        place_halo(pcore, preset_tiers(pid), loc=(xs[wname], 0, -0.25), state="lit", tag="p" + wname)
    cam_from((0.06, 0, -0.04), 20, 0, 8.0, ortho=2.3)
    res = (1800, 1000)
    setup_render(res=res, bloom=0.45)
    lights()
    half = 2.3 / 2
    hud(f"WEIGHT CLASS  (20 deg above)   top: {core.upper()} full coverage T1 / T2 / T3   "
        "bottom: game presets", -0.97, 0.9, size=0.02)
    for wname, x in xs.items():
        hud(wname.upper(), (x - 0.06) / half, 0.06, size=0.026, align="CENTER")
    for wname, pcore, pid in LINEUP_PRESETS:
        at = preset_tiers(pid)
        hud(f"{pid} ({pcore})", (xs[wname] - 0.06) / half, -0.82, size=0.016, align="CENTER",
            color=(0.6, 0.63, 0.68))
        hud(f"{tiers_label(at)} = {sum(at.values())}", (xs[wname] - 0.06) / half, -0.89, size=0.016,
            align="CENTER", color=(0.6, 0.63, 0.68))
    paths = [render(os.path.join(out_dir, "02_weight_lineup.png"))]
    paths.append(silhouette_pass(out_dir, "02_weight_lineup_silhouette.png", res))
    return paths


def r_weight_silhouette_all(out_dir):
    """All four cores x Light/Medium/Heavy, full coverage at T1/T2/T3, 20 deg above, pure silhouette."""
    clear_show()
    xs = {"Light": -0.66, "Medium": 0.0, "Heavy": 0.74}
    for r, core in enumerate(CORE_ORDER):
        for wname, x in xs.items():
            place_halo(core, uniform(UNIFORM[wname]), loc=(x, 0, -r * 0.32), state="lit", tag=f"{core}{wname}")
    cam_from((0.04, 0, -0.45), 20, 0, 8.0, ortho=2.15)
    return [silhouette_pass(out_dir, "02b_weight_silhouette_all_cores.png", (1500, 1200))]


def r_weight_eyelevel(out_dir, core="Bulwark"):
    """Weight classes as seen in play (eye 5 deg below the halo), idle.  Top row: one core at full coverage
    T1/T2/T3; bottom row: the game presets.  Dark scene + daylight + silhouette."""
    clear_show()
    xs = {"Light": -0.72, "Medium": -0.03, "Heavy": 0.72}
    for wname, x in xs.items():
        place_halo(core, uniform(UNIFORM[wname]), loc=(x, 0, 0.13), state="idle", cell_state=1.4, tag="u" + wname)
    for wname, pcore, pid in LINEUP_PRESETS:
        place_halo(pcore, preset_tiers(pid), loc=(xs[wname], 0, -0.13), state="idle", cell_state=1.4,
                   tag="p" + wname)
    ow = 2.36                                    # wide enough for the Heavy orbit (cells at r 0.33 m)
    cam_from((0.0, 0, 0.0), -5, 0, 8.0, ortho=ow)
    res = (1800, 860)
    half = ow / 2
    paths = []
    for bgname, bg, rig, txt in (("", DARK_BG, "studio", (0.85, 0.87, 0.9)), ("_day", DAY_BG, "day", dark_text())):
        remove_labels()
        setup_render(res=res, bloom=0.4, bg=bg, threshold=0.8)
        lights(rig)
        hud(f"IN PLAY: eye 5 deg below the halo, IDLE glow ({'daylight' if bgname else 'dark scene'})   "
            f"top: {core.upper()} full coverage T1/T2/T3   bottom: game presets", -0.97, 0.88, size=0.019, color=txt)
        for wname, pcore, pid in LINEUP_PRESETS:
            at = preset_tiers(pid)
            hud(wname.upper(), xs[wname] / half, 0.66, size=0.026, align="CENTER", color=txt)
            hud(f"{pcore} {tiers_label(at)}", xs[wname] / half, -0.84, size=0.017, align="CENTER",
                color=txt)
        paths.append(render(os.path.join(out_dir, f"02c_weight_eyelevel_idle{bgname}.png")))
    paths.append(silhouette_pass(out_dir, "02c_weight_eyelevel_silhouette.png", res))
    return paths


def r_core_read_eyelevel(out_dir):
    """Can the core be named edge-on?  All four cores (rows) x Light/Medium/Heavy (columns, game-legal coverage),
    idle, at -2 deg (enemy ~10 m away) and -8 deg (~2.5 m), colour + silhouette, plus a side view at -2 deg."""
    paths = []
    xs = {"Light": -0.75, "Medium": 0.0, "Heavy": 0.86}
    res = (2000, 1240)
    half = 2.3 / 2
    for view, elev, azim in (("front", -2, 0), ("front", -8, 0), ("side", -2, 90)):
        clear_show()
        for r, core in enumerate(CORE_ORDER):
            for wname, x in xs.items():
                loc = (x, 0, -r * 0.30) if view == "front" else (0, -x, -r * 0.30)
                place_halo(core, PLAY[wname], loc=loc, state="idle", cell_state=1.4, tag=f"{core}{wname}")
        tgt = (0.05, 0, -0.47) if view == "front" else (0, -0.05, -0.47)
        cam_from(tgt, elev, azim, 12.0, ortho=2.3)
        tag = f"{view}_{abs(elev)}deg" if view == "side" else f"{abs(elev)}deg"
        hdr = (f"CORE READ: eye {abs(elev)} deg below the halo ({'~10 m' if elev == -2 else '~2.5 m'}), "
               f"{'from the side (+X)' if view == 'side' else 'from the front'}, idle")
        sub = "columns: Light (T1 torso only) / Medium (H2 T2 L2) / Heavy (H3 T3 A3), game-legal coverage"
        if view == "front":
            setup_render(res=res, bloom=0.35, threshold=0.6)
            lights()
            hud(hdr, -0.97, 0.93, size=0.017)
            hud(sub, -0.97, 0.87, size=0.0135, color=(0.6, 0.63, 0.68))
            hh = 2.3 / 2 * res[1] / res[0]
            for r, core in enumerate(CORE_ORDER):
                hud(core.upper(), -0.97, (0.47 - r * 0.30 - 0.06) / hh, size=0.02)
            for wname, x in xs.items():
                hud(wname.upper(), (x - 0.05) / half, -0.93, size=0.02, align="CENTER", color=(0.6, 0.63, 0.68))
            paths.append(render(os.path.join(out_dir, f"02d_core_read_{tag}.png")))
        paths.append(silhouette_pass(out_dir, f"02d_core_read_{tag}_silhouette.png", res))
    return paths


def r_coverage(out_dir):
    clear_show()
    setup_render(res=(1800, 900), bloom=0.5)
    lights()
    cov = {"Head": 3, "Torso": 3, "Arms": 0, "Legs": 0}      # 6 -> Medium
    for i, core in enumerate(CORE_ORDER):
        place_halo(core, cov, loc=((i - 1.5) * 0.56, 0, 0), state="flare", pip_state="lit", cell_state="lit",
                   tag=core, cell_phase=62.0)       # cells front-left / back-right: clear of the neighbours
    cam_from((0, 0.0, 0), 42, 0, 8.0, ortho=2.35)
    hud("COVERAGE  HEAD + TORSO lit (T3)  /  ARMS + LEGS dark (smoked glass + edge line)", -0.96, 0.88, size=0.02)
    hud("front = HEAD arc, toward the camera;  H3 T3 = 6 -> MEDIUM (band, 2 cells)", -0.96, 0.80, size=0.016,
        color=(0.6, 0.63, 0.68))
    for i, core in enumerate(CORE_ORDER):
        hud(core.upper(), -0.715 + i * 0.477, -0.8, size=0.024, align="CENTER")
    return [render(os.path.join(out_dir, "03_coverage_head_torso.png"))]


ARC_TIER_EXAMPLES = ["arm_phase_ghost", "arm_mender_medic", "arm_volt_line", "arm_bulwark_vanguard"]


def r_arc_tiers(out_dir):
    """Per-arc tiers (game DESIGN_DELTAS #2): each arc glows in its own tier colour; pips = highest tier;
    weight class from the sum of the arc tiers.  Second panel: the three arc states (lit / broken / off)."""
    from halo_data import PRESETS
    paths = []
    clear_show()
    setup_render(res=(2000, 900), bloom=0.5)
    lights()
    sx = 0.70
    for i, pid in enumerate(ARC_TIER_EXAMPLES):
        p = PRESETS[pid]
        place_halo(p["core"], preset_tiers(pid), loc=((i - 1.5) * sx, 0, 0), state="flare", pip_state="lit",
                   cell_state="lit", tag=f"at{i}")
    cam_from((0, 0.0, 0), 42, 0, 8.0, ortho=2.9)
    hud("PER-ARC TIERS  (each arc its own tier colour; pips = highest arc tier; front = HEAD)   game presets",
        -0.96, 0.88, size=0.02)
    half = 2.9 / 2
    for i, pid in enumerate(ARC_TIER_EXAMPLES):
        at = preset_tiers(pid)
        x = (i - 1.5) * sx / half
        hud(PRESETS[pid]["name"].upper(), x, -0.70, size=0.022, align="CENTER")
        hud(f"{tiers_label(at)}   = {sum(at.values())} -> {weight_of(at).upper()}", x, -0.80, size=0.016,
            align="CENTER", color=(0.6, 0.63, 0.68))
    paths.append(render(os.path.join(out_dir, "_03b_top.png")))
    # arc states: the same Bulwark Vanguard with an intact, a broken and an uncovered Head arc.  Each halo is
    # rendered on its own with the lights moved along with it (ortho camera), so all three get the SAME light;
    # in one shared shot the right-hand halo caught a grazing rim light that washed its glass out.
    base = {"Head": 3, "Torso": 4, "Arms": 3, "Legs": 2}            # 12; without the Head arc 9: still Heavy
    states = [("HEAD ARC LIT", "M_HALO_Glass_T3", dict(base)),
              ("HEAD ARC BROKEN (pool 0)", "_Broken_T3: cracked + dim until regen", dict(base, Head=("B", 3))),
              ("HEAD ARC UNCOVERED", "_Glass_Off (unlit): smoked glass + edge line", dict(base, Head=0))]
    cols = []
    for k, (_, _, at) in enumerate(states):
        clear_show()
        setup_render(res=(2000, 900), bloom=0.5)
        lights(offset=((k - 1) * 0.86, 0.0, 0.0))
        place_halo("Bulwark", at, loc=((k - 1) * 0.86, 0, 0), state="lit", cell_state="lit", tag=f"st{k}",
                   cell_angles=[330.0, 90.0, 210.0])
        cam_from((0, -0.04, 0), 30, 0, 8.0, ortho=2.75)
        hud("ARC STATES  (Bulwark, H3 T4 A3 L2, front = HEAD arc; each halo lit identically)", -0.96, 0.88,
            size=0.02)
        for i, (lbl, sub_lbl, _) in enumerate(states):
            hud(lbl, (i - 1) * 0.86 / (2.75 / 2), -0.74, size=0.019, align="CENTER")
            hud(sub_lbl, (i - 1) * 0.86 / (2.75 / 2), -0.82, size=0.015, align="CENTER", color=(0.6, 0.63, 0.68))
        cols.append(render(os.path.join(out_dir, f"_03b_states_{k}.png")))
    paths.append(merge_columns(cols, os.path.join(out_dir, "_03b_states.png")))
    out = vstack(paths, os.path.join(out_dir, "03b_per_arc_tiers.png"))
    for p in paths:
        os.remove(p)
    return [out]


def r_underside(out_dir):
    """From below (-35 deg: player on lower ground / under a jetpacker), idle, game-legal coverage."""
    clear_show()
    cfg = [("Bulwark", "Medium"), ("Bulwark", "Heavy"), ("Volt", "Heavy"), ("Phase", "Light"), ("Mender", "Heavy")]
    for i, (core, w) in enumerate(cfg):
        place_halo(core, PLAY[w], loc=((i - 2) * 0.75, 0, 0), state="idle", cell_state=1.4, tag=f"u{i}")
    cam_from((0, 0, 0), -35, 15, 12, ortho=3.9)
    setup_render(res=(2200, 900), bloom=0.35, threshold=0.6)
    lights()
    hud("FROM BELOW (-35 deg), idle: glass wraps the underside + inner wall, band lip in the top tier colour",
        -0.97, 0.88, size=0.019)
    for i, (core, w) in enumerate(cfg):
        hud(f"{core} {w}", -0.78 + i * 0.355, -0.80, size=0.017, align="CENTER", color=(0.6, 0.63, 0.68))
    return [render(os.path.join(out_dir, "03c_underside_-35deg.png"))]


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


def spawn_shards(hit, tier, n=34, seed=7, scale=1.0):
    """Hex shards bursting from a hit on the front (Head) arc."""
    rnd = random.Random(seed)
    names = ["HALO_Shard_A", "HALO_Shard_B", "HALO_Shard_C"]
    out = []
    for i in range(n):
        th = D(rnd.uniform(-80, 80))
        ph = D(rnd.uniform(-22, 38))
        d = Vector((math.sin(th) * math.cos(ph), -math.cos(th) * math.cos(ph), math.sin(ph)))
        dist = 0.02 + 0.20 * rnd.random() ** 1.3
        p = hit + d * dist
        s = rnd.uniform(0.45, 1.0) * (1.1 - 0.55 * dist / 0.22)
        strength = 10.0 * (1.1 - dist / 0.24) + 2.0
        o = inst(names[i % 3], None, loc=p, rot=(rnd.uniform(0, 6.28), rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)),
                 scale=s * scale, slot_mats={0: glass(tier, max(2.0, strength))}, name=f"_shard{i}")
        out.append(o)
    return out


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


CHAR_CAM = (0.88, -1.70, 2.46)   # third-person-ish: ~15 deg above the halo so the ring shape reads
CHAR_PRESET = "arm_bulwark_assault"


def r_character(out_dir, sprites_dir, preset=CHAR_PRESET):
    """Kestrel with ONE game preset in both states (idle and hit), so idle and hit show the same armor."""
    from halo_data import PRESETS
    core = PRESETS[preset]["core"]
    at = preset_tiers(preset)
    weight = weight_of(at)
    top = max(at.values())
    ws = WEIGHT[weight]["scale"]
    clear_show()
    meshes, head_top = import_character()
    sock = head_top + Vector((0, 0, 0.22))
    paths = []
    tgt = Vector((sock.x, sock.y, sock.z - 0.19))
    title = f"{PRESETS[preset]['name'].upper()}  ({tiers_label(at)} = {sum(at.values())} -> {weight.upper()})"
    lit = " + ".join(z for z in ("Head", "Torso", "Arms", "Legs") if at[z])
    dark = " + ".join(z for z in ("Head", "Torso", "Arms", "Legs") if not at[z]) or "none"
    n = WEIGHT[weight]["cells"]
    for state in ("idle", "hit"):
        for o in list(show_col().objects):
            if o.name.startswith(("_root", "_s_", "_shard", "_flash", "_crack", "_lbl")):
                bpy.data.objects.remove(o, do_unlink=True)
        if state == "idle":   # dim, with a small glow (low bloom threshold, small radius)
            setup_render(res=(1200, 1400), bloom=0.35, bg=(0.05, 0.055, 0.068), threshold=0.45, size=0.3)
        else:
            setup_render(res=(1200, 1400), bloom=0.55, bg=(0.05, 0.055, 0.068))
        lights(offset=(0.0, 0.0, 1.7))
        if state == "idle":
            place_halo(core, at, loc=sock, state="idle", cell_state=1.4,
                       cell_angles=[330.0 + k * 360.0 / n for k in range(n)], tag="char")
        else:
            place_halo(core, at, loc=sock, state="flare", pip_state="flare", cell_state=6.0,
                       cell_angles=[342.0 + k * 360.0 / n for k in range(n)], tag="char")
            wall = (hp.RING_OUT[core] - 0.002) * ws
            hit = Vector((sock.x + 0.03, sock.y - wall, sock.z + 0.004 * ws))
            spawn_shards(hit, top, n=30, seed=11)
            sprite_plane(os.path.join(sprites_dir, "hex_hit_flash.png"), hit + Vector((0, -0.012, 0)), 0.15 * ws, top,
                         strength=4.0, face=Vector(CHAR_CAM), name="_flash")
            crack_at = Vector((sock.x - 0.045 * ws, sock.y - wall - 0.0006, sock.z + 0.002 * ws))
            sprite_plane(os.path.join(sprites_dir, "crack_overlay.png"), crack_at, 0.06 * ws, top, strength=7.0,
                         face=crack_at + Vector((0, -1, 0)), name="_crack", color=(0.95, 0.9, 1.0))
        camera(loc=CHAR_CAM, target=tgt, lens=58)
        hud(f"{title}  -  {'IDLE (dim)' if state == 'idle' else 'HIT (flare)'}", -0.92, 0.9, size=0.024)
        hud(f"lit: {lit}   dark: {dark}   ({n} cells, {weight.lower()} band)", -0.92, 0.83, size=0.019,
            color=(0.6, 0.63, 0.68))
        paths.append(render(os.path.join(out_dir, f"04_character_{state}.png")))
    stack(paths, os.path.join(out_dir, "04_character_idle_vs_hit.png"), cols=2)
    for o in list(show_col().objects):
        if o.name.startswith(("_root", "_s_", "_shard", "_flash", "_crack", "_lbl")):
            bpy.data.objects.remove(o, do_unlink=True)
    setup_render(res=(1000, 1400), bloom=0.35, bg=(0.05, 0.055, 0.068), threshold=0.45, size=0.3)
    lights(offset=(0.0, 0.0, 1.2))
    place_halo(core, at, loc=sock, state="idle", cell_state=1.4,
               cell_angles=[330.0 + k * 360.0 / n for k in range(n)], tag="char")
    camera(loc=(1.9, -3.6, 1.85), target=(0, 0, 1.08), lens=50)
    hud("Kestrel 1.70 m, halo socket 0.22 m above the head (idle)", -0.92, 0.93, size=0.026)
    hud(f"{PRESETS[preset]['name']}: {tiers_label(at)} -> {weight}", -0.92, 0.88, size=0.021,
        color=(0.6, 0.63, 0.68))
    paths.append(render(os.path.join(out_dir, "04_character_fullbody_idle.png")))
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


def r_turnaround(out_dir, preset="arm_bulwark_jugg"):
    from halo_data import PRESETS
    clear_show()
    setup_render(res=(900, 900), bloom=0.45)
    lights()
    place_halo(PRESETS[preset]["core"], preset_tiers(preset), state="lit", tag="turn")
    paths = []
    for v, (el, az) in {"front": (8, 0), "right": (8, 90), "back": (8, 180), "three_quarter": (35, 40)}.items():
        cam_from((0, 0, 0.004), el, az, 6.0, ortho=0.82)
        paths.append(render(os.path.join(out_dir, f"halo_{v}.png")))
    stack(paths, os.path.join(out_dir, "halo_sheet.png"), cols=2)
    return paths


def r_parts(out_dir):
    """Close-up of the small parts (x1.5): tier pips, the generic cell and the shards on top; below, the four core
    cells from the side (how they read at range) and from above (each is a miniature of its core's ring)."""
    clear_show()
    W, res = 0.84, (2200, 1430)
    H = W * res[1] / res[0]
    setup_render(res=res, bloom=0.45)
    lights()
    sc = 1.5
    zc, z1, z2, z3 = 0.02, 0.185, 0.040, -0.120
    k = math.cos(D(18))

    def sx(x):
        return x / (W / 2)

    def sy(z):
        return (z - zc) * k / (H / 2)

    for i in range(4):
        inst("HALO_TierPip", None, loc=(-0.300 + i * 0.022, 0, z1), scale=sc, slot_mats={0: glass(i + 1, 2.4)})
    inst("HALO_PowerCell", None, loc=(-0.030, 0, z1), rot=(0, 0, D(-20)), scale=sc, slot_mats={0: glass(2, 2.4)})
    for i, nm in enumerate(("A", "B", "C")):
        inst(f"HALO_Shard_{nm}", None, loc=(0.215 + i * 0.048, 0, z1), rot=(D(60), D(10), D(20 * i)), scale=1.3,
             slot_mats={0: glass(3, 2.4)})
    xs = {"Bulwark": -0.285, "Mender": -0.095, "Volt": 0.095, "Phase": 0.285}
    for core, x in xs.items():
        inst(f"HALO_PowerCell_{core}", None, loc=(x, 0, z2), rot=(0, 0, D(-25)), scale=sc,
             slot_mats={0: glass(2, 2.4)})
        top = empty(f"_top_{core}", loc=(x, 0, z3), rot=(D(72), 0, 0))     # tilted to face the camera: top view
        inst(f"HALO_PowerCell_{core}", top, scale=sc, slot_mats={0: glass(2, 2.4)})
    cam_from((0, 0, zc), 18, 0, 2.0, ortho=W)
    grey = (0.6, 0.63, 0.68)
    hud("PARTS  (x1.5)", -0.96, 0.92, size=0.018)
    hud("TIER PIPS T1-T4", sx(-0.267), sy(z1 - 0.040), size=0.014, align="CENTER")
    hud("HALO_PowerCell (generic, spec)", sx(-0.030), sy(z1 - 0.040), size=0.014, align="CENTER")
    hud("travels +X, trail fin behind", sx(-0.030), sy(z1 - 0.054), size=0.012, align="CENTER", color=grey)
    hud("HALO_Shard_A / B / C", sx(0.263), sy(z1 - 0.040), size=0.014, align="CENTER")
    sub = {"Bulwark": "wide hex puck", "Mender": "twin stacked rings", "Volt": "crown + energy spike",
           "Phase": "orb in an open ring"}
    hud("core cells HALO_PowerCell_<Core>: side view (as they orbit) and from above. One shape per core, the "
        "same from every side, so the core reads at range", -0.96, sy(z2 + 0.075), size=0.013, color=grey)
    for core, x in xs.items():
        hud(f"HALO_PowerCell_{core}", sx(x), sy(z2 - 0.056), size=0.014, align="CENTER")
        hud(sub[core], sx(x), sy(z2 - 0.070), size=0.012, align="CENTER", color=grey)
        hud("from above", sx(x), sy(z3 - 0.066), size=0.012, align="CENTER", color=grey)
    return [render(os.path.join(out_dir, "06_parts.png"))]


def r_far_lod(out_dir):
    """Near kit vs far LOD (glass arcs + one frame per weight), Heavy presets, at eye level and 20 deg above."""
    clear_show()
    at = PLAY["Heavy"]
    for i, core in enumerate(CORE_ORDER):
        x = (i - 1.5) * 0.70
        place_halo(core, at, loc=(x, 0, 0.16), state="idle", cell_state=1.4, tag=f"n{i}")
        place_halo(core, at, loc=(x, 0, -0.16), state="idle", cell_state=1.4, tag=f"f{i}", far=True)
    cam_from((0, 0, 0.0), 12, 0, 8.0, ortho=2.9)
    setup_render(res=(2000, 900), bloom=0.35, threshold=0.6)
    lights()
    hud("FAR LOD (> ~20 m)   top: near kit   bottom: HALO_<Core>_Far_Glass_<Zone> x4 + HALO_<Core>_Far_Frame_Heavy",
        -0.97, 0.90, size=0.016)
    hud("far signatures ~2x the near kit: Bulwark posts 18 mm, Mender ring step 28 mm, Volt teeth 45 mm, "
        "Phase prongs 47 mm", -0.97, 0.82, size=0.014, color=(0.6, 0.63, 0.68))
    tris = {}
    for core in CORE_ORDER:
        def tc(name):
            o = bpy.data.objects[name]
            return sum(len(p.vertices) - 2 for p in o.data.polygons)
        near = sum(tc(f"HALO_{core}_Arc_{z}") for z in ZONES) + tc(f"HALO_{core}_Frame_Heavy")
        far = sum(tc(f"HALO_{core}_Far_Glass_{z}") for z in ZONES) + tc(f"HALO_{core}_Far_Frame_Heavy")
        tris[core] = (near, far)
    half = 2.9 / 2
    for i, core in enumerate(CORE_ORDER):
        x = (i - 1.5) * 0.70 / half
        hud(core.upper(), x, 0.68, size=0.022, align="CENTER")
        hud(f"near {tris[core][0]} tris", x, -0.78, size=0.016, align="CENTER", color=(0.6, 0.63, 0.68))
        hud(f"far {tris[core][1]} tris  (+ cells)", x, -0.86, size=0.016, align="CENTER", color=(0.6, 0.63, 0.68))
    return [render(os.path.join(out_dir, "07_far_lod.png"))]


# ------------------------------------------------------------------------------------------ true-pixel checks
# In-play pixel scale: 1080p, vertical FOV 78 deg -> 1080 / (2 d tan 39) = 667 / d pixels per metre at d metres.
# Eye 1.60 m, halo ~1.92 m: the halo is seen atan(0.32 / d) above the eye.
DAY_SKY = (0.32, 0.36, 0.42)
NIGHT = (0.02, 0.022, 0.026)


def compose(spec, out):
    """Lay out a review sheet with compose_sheet.py (system Python + PIL, like make_sprites.py)."""
    import json
    import shutil
    import subprocess
    sp = out + ".json"
    spec["out"] = out
    json.dump(spec, open(sp, "w", encoding="utf-8"), indent=1)
    py = shutil.which("python") or shutil.which("py")
    try:
        subprocess.run([py, "-B", os.path.join(HERE, "compose_sheet.py"), sp], check=True, timeout=300)
    finally:
        os.remove(sp)
    return out


def true_pixel_cam(d, center_z, width_m, height_m, azim=0.0):
    ppm = 667.0 / d
    res = (int(round(width_m * ppm)), int(round(height_m * ppm)))
    elev = -math.degrees(math.atan(0.32 / d))
    cam_from((0, 0, center_z), elev, azim, 40.0, ortho=width_m)
    return res


def raw_triplet(raw_dir, name, res, center=(0, 0, 0)):
    """Daylight, dark scene and pure silhouette of the current scene at true pixel size (no labels)."""
    out = []
    for bgname, bg, rig in (("day", DAY_SKY, "day"), ("dark", NIGHT, "studio")):
        setup_render(res=res, bloom=0.3, bg=bg, threshold=0.8, samples=64)
        lights(rig, offset=center)
        out.append(render(os.path.join(raw_dir, f"{name}_{bgname}.png")))
    setup_render(res=res, bloom=0, transparent=True, samples=64)
    tmp = render(os.path.join(raw_dir, f"{name}_alpha.png"))
    out.append(to_silhouette(tmp, os.path.join(raw_dir, f"{name}_sil.png")))
    os.remove(tmp)
    return out


BLIND_ROWS = [("Light T1 torso", PLAY["Light"]), ("Light H2 T2", {"Head": 2, "Torso": 2, "Arms": 0, "Legs": 0}),
              ("Medium H2 T2 L2", PLAY["Medium"]), ("Heavy H3 T3 A3", PLAY["Heavy"])]
BLIND_VIEWS = [("10m_front", 10.0, 0.0, False, 5), ("10m_side", 10.0, -90.0, False, 5),
               ("25m_front", 25.0, 0.0, True, 12), ("25m_side", 25.0, -90.0, True, 12)]


def r_core_blind(out_dir):
    """Name-the-core blind test at TRUE in-play pixel size (review r2 #1c).  Rows = Light T1 / Light H2T2 /
    Medium / Heavy (game-legal coverage), the four cores shuffled per row (the key is in
    02e_core_blind_key.json), idle glow.  10 m uses the near kit, 25 m the far LOD.  Front = the wearer faces
    you, side = the wearer's left (Arms arc) toward you."""
    import json
    raw = os.path.join(out_dir, "_raw")
    os.makedirs(raw, exist_ok=True)
    key, blocks = {}, []
    width_m, height_m, dz = 3.8, 1.55, 0.36
    for vname, d, yaw, far, k in BLIND_VIEWS:
        rng = random.Random("halo-blind-" + vname)
        clear_show()
        key[vname] = []
        for r, (rname, at) in enumerate(BLIND_ROWS):
            cores = list(CORE_ORDER)
            rng.shuffle(cores)
            key[vname].append({"row": rname, "columns_left_to_right": cores})
            for i, core in enumerate(cores):
                place_halo(core, at, loc=((i - 1.5) * 0.9, 0, -r * dz), rot_z=yaw, state="idle", cell_state=1.4,
                           cell_phase=40.0 + 23.0 * i + 11.0 * r, far=far, tag=f"b{r}{i}")
        res = true_pixel_cam(d, -1.5 * dz, width_m, height_m)
        paths = raw_triplet(raw, f"blind_{vname}", res, center=(0, 0, -1.5 * dz))
        kit = "far LOD" if far else "near kit"
        view = "FRONT (the wearer faces you)" if yaw == 0 else "SIDE (the wearer's left toward you)"
        blocks.append({"title": f"{d:g} m, {view}, {kit}  -  true 1080p pixels (vfov 78), shown x{k} nearest",
                       "subtitle": "rows: " + " / ".join(r for r, _ in BLIND_ROWS) + "   columns: the 4 cores, "
                                   "SHUFFLED per row (key: 02e_core_blind_key.json)   [daylight | dark | silhouette]",
                       "panels": [{"img": p, "scale": k} for p in paths]})
    json.dump(key, open(os.path.join(out_dir, "02e_core_blind_key.json"), "w"), indent=1)
    out = compose({"blocks": blocks, "notes": [
        "Name each halo's core before opening the key.  Cues: Bulwark = wide flat hex-puck cells (a dash) + the "
        "thickest, boxy ring with corner posts;  Mender = twin stacked-disc cells ('=' / 'I') + thin double ring;",
        "Volt = tall pointed crown cells + crown teeth on the ring;  Phase = round orb cells with thin wings + the "
        "electrode fork at the back gap."]},
        os.path.join(out_dir, "02e_core_blind_10m_25m.png"))
    return [out]


def _halo_luma(img_path, boxes):
    """Alpha-weighted mean display luminance (Rec. 709 luma of the saved sRGB values) per pixel box."""
    im = bpy.data.images.load(img_path, check_existing=False)
    w, h = im.size
    px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]     # top-down rows
    bpy.data.images.remove(im)
    out = []
    for x0, y0, x1, y1 in boxes:
        p = px[max(0, y0):min(h, y1), max(0, x0):min(w, x1)]
        a = p[..., 3]
        luma = 0.2126 * p[..., 0] + 0.7152 * p[..., 1] + 0.0722 * p[..., 2]
        solid = a > 0.5
        white = float(((luma > 0.85) & solid).sum() / max(solid.sum(), 1))      # near-white pixel share
        out.append((float((luma * a).sum() / max(a.sum(), 1e-6)), white))
    return out


def r_far_lod_switch(out_dir):
    """Near kit vs far LOD at the 20 m switch distance (review r2 #5): true pixels in daylight, plus the mean
    halo luminance of each near/far pair (alpha-weighted, film-transparent render with the day lighting).
    Target: the far LOD within ~10 % of the near kit, so the swap does not pop."""
    import json
    raw = os.path.join(out_dir, "_raw")
    os.makedirs(raw, exist_ok=True)
    clear_show()
    rows = [("Light", PLAY["Light"]), ("Medium", PLAY["Medium"]), ("Heavy", PLAY["Heavy"])]
    dz, sx = 0.40, 0.9
    for far in (False, True):
        for r, (wname, at) in enumerate(rows):
            for i, core in enumerate(CORE_ORDER):
                z = -r * dz - (1.4 if far else 0.0)
                place_halo(core, at, loc=((i - 1.5) * sx, 0, z), state="idle", cell_state=1.4, cell_phase=40.0,
                           far=far, tag=f"l{int(far)}{r}{i}")
    cz, width_m, height_m = -1.2, 3.9, 2.8
    d = 20.0
    res = true_pixel_cam(d, cz, width_m, height_m)
    setup_render(res=res, bloom=0.3, bg=DAY_SKY, threshold=0.8, samples=64)
    lights("day")
    true_px = render(os.path.join(raw, "lodswitch_20m_day.png"))
    # measurement: the same view 4x larger with a transparent film (more pixels, same lighting)
    big = (res[0] * 4, res[1] * 4)
    setup_render(res=big, bloom=0, transparent=True, samples=64)
    lights("day")
    meas = render(os.path.join(raw, "lodswitch_measure.png"))
    ppm = big[0] / width_m
    boxes, labels = [], []
    for far in (False, True):
        for r, (wname, at) in enumerate(rows):
            for i, core in enumerate(CORE_ORDER):
                x = (i - 1.5) * sx
                z = -r * dz - (1.4 if far else 0.0)
                cx = (x + width_m / 2) * ppm
                cy = (cz + height_m / 2 - z) * ppm
                boxes.append((int(cx - 0.42 * ppm), int(cy - 0.17 * ppm), int(cx + 0.42 * ppm), int(cy + 0.15 * ppm)))
                labels.append((far, wname, core))
    lum = _halo_luma(meas, boxes)
    os.remove(meas)
    table, worst = {}, 0.0
    for (far, wname, core), (v, wf) in zip(labels, lum):
        rec = table.setdefault(f"{core}_{wname}", {})
        rec["far" if far else "near"] = round(v, 4)
        rec["white_px_pct_far" if far else "white_px_pct_near"] = round(100.0 * wf, 2)
    for k, v in table.items():
        v["far_vs_near_pct"] = round(100.0 * (v["far"] - v["near"]) / v["near"], 1)
        worst = max(worst, abs(v["far_vs_near_pct"]))
    json.dump({"what": "alpha-weighted mean display luminance per halo, daylight, idle, 20 m view (camera 0.9 deg "
                       "below the halo); white_px_pct = share of halo pixels with luma > 0.85 (white bloom risk)",
               "worst_abs_pct": worst, "pairs": table},
              open(os.path.join(out_dir, "07b_far_lod_switch_luma.json"), "w"), indent=1)
    # large reference of the same scene
    setup_render(res=(1800, 1300), bloom=0.3, bg=DAY_SKY, threshold=0.8, samples=48)
    lights("day")
    cam_from((0, 0, cz), -6, 0, 12.0, ortho=width_m)
    large = render(os.path.join(raw, "lodswitch_large.png"))
    lines = ["mean halo luminance, far vs near (target within 10 %):"]
    for wname, _ in rows:
        lines.append("  " + wname.upper() + ":  " + "   ".join(
            f"{c} {table[f'{c}_{wname}']['far_vs_near_pct']:+.1f} %" for c in CORE_ORDER))
    out = compose({"blocks": [
        {"title": "LOD SWITCH at 20 m: near kit (top 3 rows) vs far LOD (bottom 3 rows), daylight, idle",
         "subtitle": "columns: Bulwark / Mender / Volt / Phase   rows: Light / Medium / Heavy game presets   "
                     "true 1080p pixels x6 nearest  |  the same scene large (6 deg below)",
         "panels": [{"img": true_px, "scale": 6}, {"img": large, "scale": 0.72}]}], "notes": lines},
        os.path.join(out_dir, "07b_far_lod_switch_20m.png"))
    print("LOD SWITCH worst", worst, "%")
    return [out]


STATE_COLS = [("lit", {"Head": 2, "Torso": 2, "Arms": 0, "Legs": 2}),
              ("broken", {"Head": ("B", 2), "Torso": 2, "Arms": 0, "Legs": 2}),
              ("uncovered", {"Head": 0, "Torso": 2, "Arms": 2, "Legs": 2})]


def r_arc_states_range(out_dir):
    """The Head arc lit (idle) / broken / uncovered at TRUE in-play pixels, 5 m and 10 m, daylight + dark
    (review r2 #4: the old mirror-like M_HALO_Glass_Off threw near-white glints that could pass for T1 glass at
    range).  Measured per halo on the Head-arc pixels only (mask = the render with minus without the Head arc,
    4x pixels, no bloom, day light): mean display luma and the share of near-white pixels (luma > 0.85)."""
    import json
    raw = os.path.join(out_dir, "_raw")
    os.makedirs(raw, exist_ok=True)
    cores = CORE_ORDER
    dz, sx, width_m, height_m = 0.36, 0.9, 2.8, 1.62
    cz = -1.5 * dz
    blocks, table = [], {}
    for d, k in ((5.0, 3), (10.0, 5)):
        clear_show()
        heads = {}
        for r, core in enumerate(cores):
            for i, (cname, at) in enumerate(STATE_COLS):
                root = place_halo(core, at, loc=((i - 1) * sx, 0, -r * dz), state="idle", cell_state=1.4,
                                  cell_phase=40.0, tag=f"s{r}{i}")
                heads[(core, cname)] = [o for o in root.children if o.name.startswith(f"_s_HALO_{core}_Arc_Head")]
        res = true_pixel_cam(d, cz, width_m, height_m)
        paths = []
        for bgname, bg, rig in (("day", DAY_SKY, "day"), ("dark", NIGHT, "studio")):
            setup_render(res=res, bloom=0.3, bg=bg, threshold=0.8, samples=64)
            lights(rig, offset=(0, 0, cz))
            paths.append(render(os.path.join(raw, f"states_{d:g}m_{bgname}.png")))
        # measurement: 4x pixels, transparent film, day light; Head arcs hidden for the second pass
        big = (res[0] * 4, res[1] * 4)
        setup_render(res=big, bloom=0, transparent=True, samples=64)
        lights("day")
        full_p = render(os.path.join(raw, "_states_full.png"))
        for objs in heads.values():
            for o in objs:
                o.hide_render = True
        noh_p = render(os.path.join(raw, "_states_nohead.png"))
        px = []
        for p in (full_p, noh_p):
            im = bpy.data.images.load(p, check_existing=False)
            w, h = im.size
            px.append(np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1])
            bpy.data.images.remove(im)
            os.remove(p)
        full, noh = px
        diff = np.abs(full - noh).max(axis=2) > 0.03
        luma = 0.2126 * full[..., 0] + 0.7152 * full[..., 1] + 0.0722 * full[..., 2]
        ppm = big[0] / width_m
        for r, core in enumerate(cores):
            for i, (cname, _) in enumerate(STATE_COLS):
                cx, cy = (((i - 1) * sx) + width_m / 2) * ppm, (cz + height_m / 2 + r * dz) * ppm
                box = (slice(int(cy - 0.17 * ppm), int(cy + 0.17 * ppm)), slice(int(cx - 0.42 * ppm),
                                                                                int(cx + 0.42 * ppm)))
                m = diff[box] & (full[box][..., 3] > 0.5)
                n = int(m.sum())
                lv = luma[box][m]
                rec = table.setdefault(f"{d:g}m", {}).setdefault(core, {})
                rec[cname] = {"head_px_4x": n, "mean_luma": round(float(lv.mean()), 3) if n else None,
                              "near_white_pct": round(100.0 * float((lv > 0.85).mean()), 2) if n else None}
        blocks.append({"title": f"ARC STATES at {d:g} m, true 1080p pixels (vfov 78) x{k} nearest, idle",
                       "subtitle": "columns: Head arc LIT (T2, idle) / BROKEN (Broken_T2) / UNCOVERED (Glass_Off)   "
                                   "rows: " + " / ".join(cores) + "   [daylight | dark]",
                       "panels": [{"img": p, "scale": k} for p in paths]})
    json.dump({"what": "Head-arc pixels only (4x true pixels, day light, no bloom): mean display luma and share "
                       "of near-white pixels (luma > 0.85).  Uncovered must stay far below lit and never near-white.",
               "states": table}, open(os.path.join(out_dir, "03d_arc_states_range.json"), "w"), indent=1)
    notes = ["Head-arc pixels (day light, 4x true pixels, no bloom): mean luma  lit / broken / uncovered,  "
             "near-white share of the uncovered arc"]
    for dk, recs in table.items():
        for core, rec in recs.items():
            notes.append(f"  {dk} {core:<8} " + "  /  ".join(
                f"{rec[c]['mean_luma']:.2f}" if rec[c]["mean_luma"] is not None else "-" for c, _ in STATE_COLS)
                + f"     uncovered near-white {rec['uncovered']['near_white_pct']} %")
    out = compose({"blocks": blocks, "notes": notes}, os.path.join(out_dir, "03d_arc_states_range.png"))
    return [out]
