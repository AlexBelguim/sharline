"""Independent review renders for KESTREL (read-only on the asset; writes only to review/renders/).

blender -b --factory-startup -P render_review.py -- <set> [<set> ...]
sets: silhouette, gameplay, closeups, faceorient, wire, poses, grip, metrics, glb_eevee
"""
import math
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, r"F:/git/val etf/tools")
import bpy
import numpy as np
from mathutils import Matrix, Vector

import blender_common as bc

A = r"F:/git/val etf/assets/characters/kestrel/"
OUT = A + "review/renders/"
os.makedirs(OUT, exist_ok=True)
SETS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["closeups"]


def P(*a):
    print("[REV]", *a)


def load():
    bpy.ops.wm.open_mainfile(filepath=A + "kestrel.blend")
    sc = bpy.context.scene
    arm = bpy.data.objects["KES_Armature"]
    body = bpy.data.objects["KES_Body"]
    ep = bpy.data.objects["KES_Eyepiece"]
    return sc, arm, body, ep


def camera(center, direction, radius=None, dist=None, lens=85, ortho_scale=None, roll_up=(0, 0, 1)):
    sc = bpy.context.scene
    cd = bpy.data.cameras.get("_RevCam") or bpy.data.cameras.new("_RevCam")
    cam = bpy.data.objects.get("_RevCam") or bpy.data.objects.new("_RevCam", cd)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cd.lens = lens
    cd.clip_start = 0.005
    cd.clip_end = 200
    d = Vector(direction).normalized()
    c = Vector(center)
    if ortho_scale:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho_scale
        dist = dist or 6.0
    else:
        cd.type = "PERSP"
        if dist is None:
            fov = 2 * math.atan(cd.sensor_width / (2 * lens))
            dist = radius / math.sin(fov / 2)
    cam.location = c + d * dist
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    return cam


def render(path, res=(900, 900), samples=64, engine="CYCLES"):
    sc = bpy.context.scene
    if engine == "CYCLES":
        bc.setup_cycles_gpu(sc, samples)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("GPU render failed, CPU fallback", e)
        sc.cycles.device = "CPU"
        sc.cycles.samples = min(samples, 48)
        bpy.ops.render.render(write_still=True)
    P("rendered", path)
    return path


# ------------------------------------------------------------------------------------------------ posing helpers
def reset(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def _apply(pb, rot):
    M = pb.matrix.copy()
    h = M.translation.copy()
    pb.matrix = Matrix.Translation(h) @ rot @ Matrix.Translation(-h) @ M
    bpy.context.view_layer.update()


def aim(arm, name, target_dir, frac=1.0):
    """Rotate bone about its head so its direction points along world target_dir (frac of the way)."""
    pb = arm.pose.bones[name]
    d = (pb.tail - pb.head).normalized()
    t = Vector(target_dir).normalized()
    ax = d.cross(t)
    if ax.length < 1e-6:
        return
    ang = math.acos(max(-1, min(1, d.dot(t)))) * frac
    _apply(pb, Matrix.Rotation(ang, 4, ax.normalized()))


def rot_world(arm, name, axis, deg):
    _apply(arm.pose.bones[name], Matrix.Rotation(math.radians(deg), 4, Vector(axis).normalized()))


def twist_bone(arm, name, deg):
    pb = arm.pose.bones[name]
    rot_world(arm, name, (pb.tail - pb.head).normalized(), deg)


def drop_to_floor(arm, objs):
    dg = bpy.context.evaluated_depsgraph_get()
    zmin = 1e9
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        mw = np.array(o.matrix_world)
        co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        zmin = min(zmin, float(co[:, 2].min()))
        ev.to_mesh_clear()
    pb = arm.pose.bones["root"]
    M = pb.matrix.copy()
    M.translation.z -= zmin
    pb.matrix = M
    bpy.context.view_layer.update()


def curl(arm, s, deg=(75, 90, 60), thumb=(30, 40, 40)):
    """Curl the fingers toward the palm. Palm normal = cross of (hand dir, index->pinky)."""
    hand = arm.pose.bones[f"hand_{s}"]
    hd = (hand.tail - hand.head).normalized()
    lat = (arm.pose.bones[f"index_01_{s}"].head - arm.pose.bones[f"pinky_01_{s}"].head).normalized()
    # palm normal: for the right hand cross(hd, lat) or the opposite; pick the side away from the back-of-hand
    n = hd.cross(lat).normalized()
    if s == "l":
        n = -n
    for f in ("index", "middle", "ring", "pinky"):
        for k, a in zip((1, 2, 3), deg):
            pb = arm.pose.bones[f"{f}_0{k}_{s}"]
            d = (pb.tail - pb.head).normalized()
            ax = d.cross(n)
            if ax.length > 1e-6:
                _apply(pb, Matrix.Rotation(math.radians(a), 4, ax.normalized()))
    return n


POSES = {}


def pose_rifle(arm):
    """Rifle ready: both upper arms down-forward, elbows bent ~95 deg, forearms forward; head slightly down."""
    aim(arm, "upperarm_r", (0.25, -0.45, -1.0))
    aim(arm, "lowerarm_r", (0.35, -1.0, 0.05))
    aim(arm, "upperarm_l", (0.05, -0.75, -0.6))
    aim(arm, "lowerarm_l", (-0.35, -1.0, 0.15))
    for s in ("l", "r"):
        aim(arm, f"hand_{s}", (0.0, -1.0, -0.2), 0.5)
    rot_world(arm, "spine_02", (0, 0, 1), -8)
    rot_world(arm, "spine_03", (0, 0, 1), -8)


def pose_zipline(arm):
    """Zipline hang: both arms straight up, slightly forward; legs bent a little."""
    for s, x in (("l", 1), ("r", -1)):
        aim(arm, f"clavicle_{s}", (x * 0.8, 0.0, 0.6), 0.6)
        aim(arm, f"upperarm_{s}", (x * 0.18, -0.15, 1.0))
        aim(arm, f"lowerarm_{s}", (x * 0.05, -0.2, 1.0))
        aim(arm, f"thigh_{s}", (x * 0.1, -0.5, -1.0))
        aim(arm, f"calf_{s}", (x * 0.05, 0.6, -1.0))


def pose_crouch_aim(arm):
    """Tactical crouch: one knee down (left), right foot planted, torso upright-ish."""
    rot_world(arm, "spine_01", (1, 0, 0), 10)
    aim(arm, "thigh_r", (-0.12, -1.0, -0.2))
    aim(arm, "calf_r", (-0.05, 0.05, -1.0))
    aim(arm, "thigh_l", (0.1, -0.05, -1.0))
    aim(arm, "calf_l", (0.05, 1.0, -0.15))
    aim(arm, "foot_l", (0.0, 0.3, -1.0), 0.6)
    pose_rifle(arm)


def pose_deep_squat(arm):
    """Builder-style deep crouch, both heels down."""
    rot_world(arm, "spine_01", (1, 0, 0), 15)
    rot_world(arm, "spine_02", (1, 0, 0), 10)
    for s, x in (("l", 1), ("r", -1)):
        aim(arm, f"thigh_{s}", (x * 0.35, -1.0, 0.05))
        aim(arm, f"calf_{s}", (x * 0.1, 0.55, -1.0))
        aim(arm, f"upperarm_{s}", (x * 0.3, -0.6, -1.0))
        aim(arm, f"lowerarm_{s}", (x * 0.2, -1.0, 0.0))


def pose_twist(arm):
    """Stress: forearms pronated 90 deg, wrists bent 60 deg, head pitched down 30 deg, arms down."""
    for s, x in (("l", 1), ("r", -1)):
        aim(arm, f"upperarm_{s}", (x * 0.25, 0.0, -1.0))
        aim(arm, f"lowerarm_{s}", (x * 0.1, -1.0, -0.2))
        twist_bone(arm, f"lowerarm_{s}", 90 * x)
        rot_world(arm, f"hand_{s}", (1, 0, 0), -60)
    rot_world(arm, "head", (1, 0, 0), 30)


def pose_slide(arm):
    """Slide: torso leaned back, left leg extended forward, right leg folded under."""
    rot_world(arm, "pelvis", (1, 0, 0), -25)
    aim(arm, "thigh_l", (0.1, -1.0, 0.15))
    aim(arm, "calf_l", (0.1, -1.0, 0.0))
    aim(arm, "thigh_r", (-0.15, -1.0, -0.3))
    aim(arm, "calf_r", (-0.1, 0.7, -0.6))
    for s, x in (("l", 1), ("r", -1)):
        aim(arm, f"upperarm_{s}", (x * 0.6, 0.4, -0.7))
        aim(arm, f"lowerarm_{s}", (x * 0.4, -0.3, -0.8))


POSES = {"rifle": pose_rifle, "zipline": pose_zipline, "kneel": pose_crouch_aim, "squat": pose_deep_squat,
         "stress": pose_twist, "slide": pose_slide}


# ------------------------------------------------------------------------------------------------ sets
def set_silhouette(sc, arm, body, ep):
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "SINGLE"
    sh.single_color = (0, 0, 0)
    sh.background_type = "VIEWPORT"
    sh.background_color = (1, 1, 1)
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = "Standard"
    except Exception:
        pass
    world = bpy.data.worlds.new("_white")
    world.color = (1, 1, 1)
    sc.world = world
    paths = []
    for nm, d in (("front", (0, -1, 0)), ("her_left_side", (1, 0, 0)), ("back", (0, 1, 0)), ("her_right_side", (-1, 0, 0)),
                  ("three_quarter", (0.75, -1, 0.15))):
        camera((0, 0.05, 0.86), d, ortho_scale=1.95, lens=85)
        paths.append(render(OUT + f"sil_{nm}.png", res=(600, 900), engine="WB"))
    # the 64 px test: same frames, tiny
    for nm, d in (("front", (0, -1, 0)), ("her_left_side", (1, 0, 0)), ("back", (0, 1, 0)), ("three_quarter", (0.75, -1, 0.15))):
        camera((0, 0.05, 0.86), d, ortho_scale=1.95, lens=85)
        render(OUT + f"sil64_{nm}.png", res=(43, 64), engine="WB")
    bc.contact_sheet(paths, OUT + "sil_sheet.png", cols=5)


def set_gameplay(sc, arm, body, ep):
    """Small renders from typical third-person / enemy distances with EEVEE (closer to a raster engine)."""
    bc.setup_studio(floor=True)
    try:
        sc.render.engine = "BLENDER_EEVEE"
    except TypeError:
        sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.eevee.taa_render_samples = 32
    sc.render.film_transparent = False
    out = []
    for nm, d, dist in (("15m_front34", (0.6, -1, 0.12), 15), ("15m_back34", (-0.6, 1, 0.12), 15),
                        ("8m_left", (1, -0.2, 0.08), 8), ("4m_tpcam", (-0.35, 1, 0.55), 3.2)):
        cd = bpy.data.cameras.get("_RevCam") or bpy.data.cameras.new("_RevCam")
        cam = camera((0, 0, 1.0), d, dist=dist, lens=50)
        cam.data.lens = 50
        out.append(render(OUT + f"game_{nm}.png", res=(480, 270), engine="EEVEE"))
    bc.contact_sheet(out, OUT + "game_sheet.png", cols=2)


def set_closeups(sc, arm, body, ep):
    bc.setup_studio()
    objs = [body, ep]
    shots = [
        ("face_low", (0.03, -0.03, 1.52), (0.25, -1, -0.45), 0.12),
        ("face_high_tpcam", (0.02, -0.0, 1.55), (0.3, -0.6, 1.0), 0.15),
        ("head_her_left_back34", (0.04, 0.03, 1.53), (0.9, 0.7, 0.15), 0.15),
        ("head_top", (0.0, 0.03, 1.62), (0.0, -0.15, 1.0), 0.16),
        ("lens_closeup", (0.05, -0.06, 1.512), (0.25, -1, 0.05), 0.05),
        ("lens_side_her_left", (0.07, -0.04, 1.512), (1, -0.35, 0.05), 0.06),
        ("mouth_closeup", (0.0, -0.07, 1.46), (0.1, -1, 0.0), 0.05),
        ("hand_r_palm", (-0.55, -0.04, 0.86), (0.6, -0.3, -0.75), 0.08),
        ("hand_r_back", (-0.55, -0.04, 0.86), (-0.55, -0.2, 0.8), 0.08),
        ("hand_l_palm", (0.56, -0.04, 0.87), (-0.6, -0.3, -0.75), 0.08),
        ("jetpack_below_back", (0.0, 0.25, 1.12), (0.15, 0.9, -0.55), 0.2),
        ("jetpack_side", (0.0, 0.22, 1.2), (1.0, 0.25, 0.1), 0.2),
        ("collar_front_above", (0.0, -0.03, 1.40), (0.1, -0.8, 0.6), 0.12),
        ("chest_plate", (0.0, -0.1, 1.24), (0.2, -1, 0.15), 0.16),
        ("armpit_below", (0.18, 0.0, 1.25), (0.4, -0.6, -0.8), 0.14),
        ("crotch_front_low", (0.0, -0.05, 0.82), (0.1, -1, -0.35), 0.18),
        ("boots_front_low", (0.0, -0.05, 0.1), (0.3, -1, 0.15), 0.25),
        ("belt_pouches", (0.06, -0.1, 0.96), (0.4, -1, 0.1), 0.13),
    ]
    paths = []
    for nm, c, d, r in shots:
        camera(c, d, radius=r, lens=85)
        paths.append(render(OUT + f"cu_{nm}.png", res=(800, 800), samples=64))
    bc.contact_sheet(paths, OUT + "cu_sheet.png", cols=6)


def set_faceorient(sc, arm, body, ep):
    """Backfaces red, frontfaces blue (Cycles, override material)."""
    bc.setup_studio()
    m = bpy.data.materials.new("_faceorient")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (0.1, 0.25, 0.9, 1)
    mix.inputs[7].default_value = (0.95, 0.05, 0.05, 1)
    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(geo.outputs["Backfacing"], mix.inputs[0])
    nt.links.new(mix.outputs[2], bsdf.inputs[0])
    nt.links.new(bsdf.outputs[0], outn.inputs[0])
    sc.view_layers[0].material_override = m
    paths = []
    for nm, c, d, r in (("full_front", (0, 0.05, 0.86), (0.3, -1, 0.1), 0.95),
                        ("full_back", (0, 0.05, 0.86), (-0.3, 1, 0.1), 0.95),
                        ("head", (0.02, -0.0, 1.53), (0.5, -1, 0.1), 0.16)):
        camera(c, d, radius=r, lens=85)
        paths.append(render(OUT + f"orient_{nm}.png", res=(700, 900) if "full" in nm else (800, 800), samples=16))
    sc.view_layers[0].material_override = None
    pass


def _wire_material(src):
    """Copy of the body material with a Cycles Wireframe overlay mixed in."""
    m = src.copy()
    m.name = "_wire_" + src.name
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    base_in = bsdf.inputs["Base Color"]
    wf = nt.nodes.new("ShaderNodeWireframe")
    wf.use_pixel_size = True
    wf.inputs[0].default_value = 0.6
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[7].default_value = (0.0, 0.0, 0.0, 1)
    if base_in.is_linked:
        nt.links.new(base_in.links[0].from_socket, mix.inputs[6])
    else:
        mix.inputs[6].default_value = base_in.default_value
    nt.links.new(wf.outputs[0], mix.inputs[0])
    nt.links.new(mix.outputs[2], base_in)
    return m


def set_wire(sc, arm, body, ep):
    bc.setup_studio()
    body.material_slots[0].material = _wire_material(body.material_slots[0].material)
    paths = []
    for nm, c, d, r, res in (("head_front", (0.02, -0.03, 1.53), (0.15, -1, 0.05), 0.13, (900, 900)),
                             ("head_her_left", (0.05, 0.0, 1.53), (1, -0.3, 0.05), 0.13, (900, 900)),
                             ("hand_r", (-0.56, -0.04, 0.86), (0.4, -0.5, -0.7), 0.08, (900, 900)),
                             ("full_front", (0, 0.05, 0.86), (0.2, -1, 0.05), 0.92, (1200, 1600))):
        camera(c, d, radius=r, lens=85)
        paths.append(render(OUT + f"wire_{nm}.png", res=res, samples=32))


def set_poses(sc, arm, body, ep):
    bc.setup_studio(floor=True)
    objs = [body, ep]
    paths = []
    shots = {
        "rifle": [("34", (0.7, -1, 0.25), None, 1.0), ("shoulder_r", (-0.9, -0.6, 0.35), (-0.2, -0.05, 1.25), 0.25),
                  ("elbow_r_below", (-0.6, -0.4, -0.5), (-0.28, -0.12, 1.05), 0.2),
                  ("back34", (-0.6, 1, 0.3), "spine_03", 0.35)],
        "zipline": [("34", (0.7, -1, 0.2), None, 1.15), ("shoulders_back", (-0.3, 1, 0.3), (0, 0.05, 1.45), 0.35),
                    ("armpit_l", (1, -0.4, -0.1), (0.15, 0.0, 1.45), 0.25)],
        "kneel": [("34", (0.7, -1, 0.25), None, 0.85), ("side_her_right", (-1, -0.1, 0.1), None, 0.85),
                  ("knee_l", (0.8, -0.6, 0.2), "calf_l", 0.22)],
        "squat": [("34", (0.7, -1, 0.3), None, 0.75), ("side", (-1, -0.15, 0.1), None, 0.75),
                  ("hips_back", (-0.3, 1, 0.2), "pelvis", 0.3)],
        "stress": [("34", (0.6, -1, 0.2), None, 1.0), ("forearm_r", (-0.8, -0.8, 0.1), "lowerarm_r", 0.2),
                   ("neck", (0.6, -1, 0.1), "neck_01", 0.2), ("nape_back", (0.5, 1, 0.25), "neck_01", 0.2)],
        "slide": [("side", (-1, -0.2, 0.15), None, 0.95), ("34", (0.6, -1, 0.3), None, 0.95)],
    }
    for pname, fn in POSES.items():
        reset(arm)
        fn(arm)
        drop_to_floor(arm, objs)
        bpy.context.view_layer.update()
        for vn, d, focus, r in shots[pname]:
            if focus is None:
                mn, mx = bc.world_bounds(objs)
                c = (mn + mx) / 2
            elif isinstance(focus, str):
                pb = arm.pose.bones[focus]
                c = arm.matrix_world @ pb.head
            else:
                c = Vector(focus)
                # follow the pose: keep absolute
            camera(c, d, radius=r, lens=85)
            paths.append(render(OUT + f"pose_{pname}_{vn}.png", res=(800, 800), samples=48))
    reset(arm)
    bc.contact_sheet(paths, OUT + "pose_sheet.png", cols=4)


def set_grip(sc, arm, body, ep):
    """Snap the real Mako (mako_default.glb, origin = pistol-grip hand position) to KES_SOCKET_WeaponR and _L."""
    bc.setup_studio()
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=r"F:/git/val etf/assets/weapons/ar7_mako/mako_default.glb")
    new = [o for o in bpy.data.objects if o not in before]
    roots = [o for o in new if o.parent is None]
    P("mako roots", [o.name for o in roots])
    holder = bpy.data.objects.new("_mako_holder", None)
    sc.collection.objects.link(holder)
    for o in roots:
        o.parent = holder
    sock = bpy.data.objects["KES_SOCKET_WeaponR"]
    paths = []
    for side in ("R", "L"):
        sock = bpy.data.objects[f"KES_SOCKET_Weapon{side}"]
        holder.matrix_world = sock.matrix_world.copy()
        bpy.context.view_layer.update()
        c = sock.matrix_world.translation
        x = -1 if side == "R" else 1
        for vn, d in (("front", (0.0, -1, 0.1)), ("out", (x, -0.3, 0.2)), ("in", (-x, -0.6, -0.1))):
            camera(c, d, radius=0.14, lens=85)
            paths.append(render(OUT + f"grip_{side}_{vn}.png", res=(700, 700), samples=48))
    bc.contact_sheet(paths, OUT + "grip_sheet.png", cols=3)


def edge_stats(body, arm):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    ev.to_mesh_clear()
    return co


def set_metrics(sc, arm, body, ep):
    """Edge-length stretch per pose, grouped by dominant bone; halo-socket travel with head pitch."""
    me = body.data
    ed = np.zeros(len(me.edges) * 2, int)
    me.edges.foreach_get("vertices", ed)
    ed = ed.reshape(-1, 2)
    gname = {g.index: g.name for g in body.vertex_groups}
    dom = []
    for v in me.vertices:
        if v.groups:
            g = max(v.groups, key=lambda g: g.weight)
            dom.append(gname[g.group])
        else:
            dom.append("-")
    dom = np.array(dom)
    reset(arm)
    rest = edge_stats(body, arm)
    L0 = np.linalg.norm(rest[ed[:, 0]] - rest[ed[:, 1]], axis=1)
    ok = L0 > 1e-5
    for pname, fn in POSES.items():
        reset(arm)
        fn(arm)
        co = edge_stats(body, arm)
        L = np.linalg.norm(co[ed[:, 0]] - co[ed[:, 1]], axis=1)
        r = np.where(ok, L / np.maximum(L0, 1e-9), 1.0)
        st = (r > 1.8) & (L - L0 > 0.004)
        cp = (r < 0.4) & (L0 > 0.003)
        bad = st | cp
        P(f"pose {pname}: edges stretched >1.8x and >4mm: {st.sum()} (max abs stretch {(L - L0).max() * 1000:.1f} mm), compressed <0.4x of >3mm edges: {cp.sum()}")
        if bad.any():
            b = dom[ed[bad, 0]]
            u, c = np.unique(b, return_counts=True)
            order = np.argsort(-c)[:8]
            P("    worst regions:", [(u[i], int(c[i])) for i in order])
    # halo travel
    reset(arm)
    h = bpy.data.objects["KES_SOCKET_Halo"]
    p0 = h.matrix_world.translation.copy()
    top0 = arm.matrix_world @ arm.pose.bones["head"].tail
    for deg in (15, 30, 45):
        reset(arm)
        rot_world(arm, "head", (1, 0, 0), deg)
        p = h.matrix_world.translation
        top = arm.matrix_world @ arm.pose.bones["head"].tail
        P(f"head pitch {deg} deg down: halo socket moves {(p - p0).length * 100:.1f} cm (dy {(p - p0).y * 100:.1f}, dz {(p - p0).z * 100:.1f}); skull top moves {(top - top0).length * 100:.1f} cm")
    reset(arm)
    POSES["squat"](arm)
    p = h.matrix_world.translation
    P(f"squat: halo socket at {tuple(round(x, 3) for x in p)}")
    reset(arm)


def set_glb_eevee(sc, arm, body, ep):
    """Import the exported glb into an empty scene and render with EEVEE (closest to a realtime PBR engine)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    bpy.ops.import_scene.gltf(filepath=A + "kestrel.glb")
    for o in list(bpy.data.objects):
        if o.name.startswith("Icosphere"):
            o.hide_render = True
    bc.setup_studio(floor=True)
    try:
        sc.render.engine = "BLENDER_EEVEE"
    except TypeError:
        sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.eevee.taa_render_samples = 64
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and not o.name.startswith("Ico") and not o.name.startswith("_")]
    paths = []
    for nm, c, d, r, res in (("full_34", (0, 0.05, 0.86), (0.7, -1, 0.25), 0.95, (900, 1200)),
                             ("head_34", (0.02, -0.02, 1.53), (0.6, -1, 0.15), 0.14, (900, 900)),
                             ("back_34", (0, 0.1, 1.0), (-0.6, 1, 0.3), 0.8, (900, 1200))):
        camera(c, d, radius=r, lens=85)
        paths.append(render(OUT + f"glb_eevee_{nm}.png", res=res, engine="EEVEE"))
    bc.contact_sheet(paths, OUT + "glb_eevee_sheet.png", cols=3)


FN = {"silhouette": set_silhouette, "gameplay": set_gameplay, "closeups": set_closeups, "faceorient": set_faceorient,
      "wire": set_wire, "poses": set_poses, "grip": set_grip, "metrics": set_metrics, "glb_eevee": set_glb_eevee}

for s in SETS:
    sc, arm, body, ep = load()
    FN[s](sc, arm, body, ep)
P("done", SETS)
