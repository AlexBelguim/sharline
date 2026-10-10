"""Render the ATT tactical set from tactical.blend (headless Blender 5.2).

  blender -b --factory-startup -P render_tactical.py -- [--parts a,b,...] [--sets alone,detail,fit,open,loadout,sight]
                                                         [--res 800] [--samples 48] [--views right,left,...]
Writes PNGs to renders/<part>/ . Contact sheets / comparisons are made by make_sheets.py (system python + PIL).
Test fits use the real gun exports (mako_default.glb, warden_default.glb) and place the parts on the socket NODES read
from those .glb files (what the engine uses); sockets.json is only the fallback. The Mako's default optic
(attachments/optics/ATT_optic_holo.glb) is mounted on its Optic socket for loadouts, wide fits and the ADS check.
The Warden uses ATT_optic_sniper.glb on its current Optic socket for the full-gun previews.
Note: bc.render_views "right" puts the camera at +X, i.e. it shows the part's +X side (the shooter's LEFT).
"""
import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path

HERE = str(Path(__file__).resolve().parent)
PROJECT = Path(HERE).parents[3]
sys.path.insert(0, str(PROJECT / "tools"))
sys.path.insert(0, HERE)
import bmesh  # noqa: E402
import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Vector  # noqa: E402

import blender_common as bc  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--parts", default="all")
ap.add_argument("--sets", default="alone,fit,detail")
ap.add_argument("--res", type=int, default=800)
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--views", default="right,left,three_quarter,front,back,top")
ap.add_argument("--out", default=os.path.join(HERE, "renders"))
ap.add_argument("--blend", default=os.path.join(HERE, "tactical.blend"))
ap.add_argument("--loadout-guns", default="mako,warden", help="Loadout gun selection: mako,warden")
a = ap.parse_args(argv)
loadout_guns = set(a.loadout_guns.split(","))
if loadout_guns - {"mako", "warden"}:
    ap.error("--loadout-guns accepts mako,warden")

bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.blend))
scene = bpy.data.scenes["Scene"]
if bpy.context.window:
    bpy.context.window.scene = scene
vl = scene.view_layers[0]
for name in ("_Proxy_Mako", "_Proxy_Warden"):
    vl.layer_collection.children[name].exclude = False
bc.setup_studio(scene)
OUT = a.out

WEAPONS = str(PROJECT / "assets" / "weapons")


def sockets_json(path, prefix):
    with open(path) as fh:
        d = json.load(fh)
    return {k.replace(prefix + "_SOCKET_", ""): Vector(v["location"]) for k, v in d.items()}


def import_glb(path, colname):
    if not os.path.exists(path):
        return None
    try:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        col = bpy.data.collections.new(colname)
        scene.collection.children.link(col)
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            col.objects.link(o)
        print("imported", path, len(new))
        return col
    except Exception as e:  # file being rewritten by another session etc.
        print("import failed", path, e)
        return None


def glb_sockets(col, prefix):
    """World positions of the imported gun's <prefix>_SOCKET_* nodes."""
    bpy.context.view_layer.update()
    out = {}
    if col is None:
        return out
    for o in col.all_objects:
        nm = o.name.split(".")[0]
        if nm.startswith(prefix + "_SOCKET_"):
            out[nm[len(prefix) + 8:]] = o.matrix_world.translation.copy()
    return out


REAL_WARDEN = import_glb(os.path.join(WEAPONS, "vk50_warden", "warden_default.glb"), "_Real_Warden")
REAL_MAKO = import_glb(os.path.join(WEAPONS, "ar7_mako", "mako_default.glb"), "_Real_Mako")
REAL_OPTIC = import_glb(os.path.join(WEAPONS, "attachments", "optics", "ATT_optic_holo.glb"), "_Real_Optic")
REAL_SNIPER = import_glb(os.path.join(WEAPONS, "attachments", "optics", "ATT_optic_sniper.glb"), "_Real_Sniper")

MAKO = sockets_json(os.path.join(WEAPONS, "ar7_mako", "sockets.json"), "MAKO")
WARDEN = sockets_json(os.path.join(WEAPONS, "vk50_warden", "sockets.json"), "WARDEN")
SOCKET_SRC = {"MAKO": "sockets.json", "WARDEN": "sockets.json"}
for gun, col, d in (("MAKO", REAL_MAKO, MAKO), ("WARDEN", REAL_WARDEN, WARDEN)):
    gs = glb_sockets(col, gun)
    if gs:
        d.update(gs)
        SOCKET_SRC[gun] = "glb nodes"
print("SOCKETS", SOCKET_SRC, {k: tuple(round(c, 4) for c in v) for k, v in MAKO.items()})

OPTIC_ROOT = None
ADS = Vector((0.0, -0.0126, 0.045))           # holo _SOCKET_ADS relative to its mount (fallback)
if REAL_OPTIC:
    OPTIC_ROOT = next((o for o in REAL_OPTIC.all_objects if o.name.split(".")[0] == "ATT_optic_holo"), None)
    ads = next((o for o in REAL_OPTIC.all_objects if o.name.split(".")[0] == "ATT_optic_holo_SOCKET_ADS"), None)
    if OPTIC_ROOT:
        OPTIC_ROOT.location = MAKO["Optic"]
        bpy.context.view_layer.update()
        if ads:
            ADS = ads.matrix_world.translation - OPTIC_ROOT.matrix_world.translation
print("HOLO ADS offset", tuple(round(c, 4) for c in ADS))
if REAL_SNIPER:
    sniper_root = next((o for o in REAL_SNIPER.all_objects if o.name.split(".")[0] == "ATT_optic_sniper"), None)
    if sniper_root:
        sniper_root.location = WARDEN["Optic"]
        bpy.context.view_layer.update()

PARTS = {
    "grip_vertical": ("mako", "Under"), "grip_angled": ("mako", "Under"), "grip_stub": ("mako", "Under"),
    "ugl_launcher": ("mako", "Under"), "bipod": ("warden", "Under"), "laser_R": ("mako", "Side_R"),
    "laser_L": ("mako", "Side_L"), "flashlight_R": ("mako", "Side_R"), "flashlight_L": ("mako", "Side_L"),
    "shield_front": ("mako", "Shield"),
}
parts = list(PARTS) if a.parts == "all" else a.parts.split(",")
sets = a.sets.split(",")
views = a.views.split(",")


def hier(o):
    out = [o]
    for c in o.children:
        out += hier(c)
    return out


GROUND = bpy.data.objects.get("_PW_Ground")


def optic_meshes():
    return [o for o in REAL_OPTIC.all_objects if o.type == "MESH"] if REAL_OPTIC else []


def proxy(gun, ground=True, optic=True):
    if gun == "mako":
        col = REAL_MAKO or bpy.data.collections["_Proxy_Mako"]
        objs = [o for o in col.all_objects if o.type == "MESH"]
        if REAL_MAKO and optic:
            objs += optic_meshes()
        if not optic:
            objs = [o for o in objs if "Optic" not in o.name]
    else:
        if REAL_WARDEN:
            objs = [o for o in REAL_WARDEN.all_objects if o.type == "MESH"]
            if optic and REAL_SNIPER:
                objs += [o for o in REAL_SNIPER.all_objects if o.type == "MESH"]
        else:
            objs = [o for o in bpy.data.collections["_Proxy_Warden"].all_objects if o.type == "MESH"
                    and o.name != "_PW_Ground"]
        if ground and GROUND:
            objs = objs + [GROUND]
    return objs


def show_only(objs):
    keep = set(objs)
    for o in scene.objects:
        if o.type == "MESH":
            o.hide_render = o not in keep


def root_of(pid):
    return bpy.data.objects["ATT_" + pid]


def place(pid, loc):
    r = root_of(pid)
    r.location = loc
    bpy.context.view_layer.update()


def meshes(objs):
    return [o for o in objs if o.type == "MESH"]


def render(pid, prefix, objs, vws, res=None, focus=None, lens=85, frame=None):
    out = os.path.join(OUT, pid)
    return bc.render_views(out, prefix, objs=frame or objs, views=vws, res=res or (a.res, a.res), engine="CYCLES",
                           samples=a.samples, lens=lens, focus=focus)


def bounds(objs):
    mn, mx = bc.world_bounds(objs)
    return (mn + mx) / 2, (mx - mn).length / 2


def end_on_focus(objs, aspect=900 / 1400):
    """Focus for an end-on (front) view of a whole gun: centred on the bore line (x 0) near the muzzle end, sized to
    the vertical extent of the cross-section (render_views fits the radius to the image WIDTH)."""
    mn, mx = bc.world_bounds(objs)
    half_h = (mx.z - mn.z) / 2
    return Vector((0.0, mn.y + 0.15, (mn.z + mx.z) / 2)), half_h / (aspect * 1.12) * 1.08


def bipod_pose(folded):
    for side in ("L", "R"):
        leg = bpy.data.objects[f"ATT_bipod_Leg_{side}"]
        sp = bpy.data.objects[f"ATT_bipod_LegSplay_{side}"]
        ft = bpy.data.objects[f"ATT_bipod_Foot_{side}"]
        leg.rotation_euler[0] = math.radians(leg["hinge_euler_x_folded_deg" if folded else "hinge_euler_x_deployed_deg"])
        sp.rotation_euler[1] = math.radians(sp["splay_euler_y_folded_deg" if folded else "splay_euler_y_deployed_deg"])
        ft.rotation_euler[0] = math.radians(ft["swivel_folded_deg" if folded else "swivel_deployed_deg"])
    bpy.context.view_layer.update()


for pid in parts:
    gun, sock = PARTS[pid]
    root = root_of(pid)
    objs = hier(root)
    ms = meshes(objs)
    if "alone" in sets:
        place(pid, Vector((0, 0, 0)))
        show_only(ms)
        render(pid, pid, ms, views)
    if "detail" in sets:
        place(pid, Vector((0, 0, 0)))
        show_only(ms)
        c, r = bounds(ms)
        render(pid, pid + "_detail", ms, ["three_quarter_back", "low", (-0.9, -0.8, 0.3)], focus=(c, r * 0.8))
    if "fit" in sets:
        loc = (MAKO if gun == "mako" else WARDEN)[sock]
        place(pid, loc)
        px = proxy(gun)
        show_only(ms + px)
        c, r = bounds(ms)
        r = max(r * 1.9, 0.16)
        fv = ["right", "left", "three_quarter", "front", "low"]
        if pid == "shield_front":
            fv = ["right", "three_quarter", "front", "three_quarter_back", "top"]
        render(pid, pid + "_fit", ms, fv, focus=(c, r))
        if gun == "warden":
            render(pid, pid + "_fit_wide", ms, ["right", "three_quarter", "front"],
                   frame=[o for o in px if o is not GROUND])
        else:
            render(pid, pid + "_fit_wide", ms, ["three_quarter", "right"], frame=px)
        place(pid, Vector((0, 0, 0)))

# ------------------------------------------------------------------------------------------- moving parts
if "open" in sets:
    pid = "ugl_launcher"
    br = bpy.data.objects["ATT_ugl_launcher_Breech"]
    ang = br.get("open_angle_deg", -40.0)
    ms = meshes(hier(root_of(pid)))
    place(pid, Vector((0, 0, 0)))
    show_only(ms)
    br.rotation_euler[2] = math.radians(ang)
    bpy.context.view_layer.update()
    render(pid, pid + "_open", ms, ["top", "three_quarter", (-0.6, -0.8, 0.5)])
    place(pid, MAKO["Under"])
    show_only(ms + proxy("mako"))
    c, r = bounds(ms)
    render(pid, pid + "_open_fit", ms, ["top", (0.7, -0.6, 0.45)], focus=(c, r * 1.6))
    br.rotation_euler[2] = 0.0
    place(pid, Vector((0, 0, 0)))
    # bipod folded (review v2: hinge -95, splay 0, feet swivelled flat) under the real Warden + alone
    pid = "bipod"
    bipod_pose(True)
    ms = meshes(hier(root_of(pid)))
    place(pid, Vector((0, 0, 0)))
    show_only(ms)
    render(pid, pid + "_folded", ms, ["right", "front", "three_quarter", (0.35, -0.5, -1.0)])
    place(pid, WARDEN["Under"])
    show_only(ms + proxy("warden", ground=False))
    c, r = bounds(ms)
    render(pid, pid + "_folded_fit", ms, ["right", "low", "front", (0.3, -0.4, -1.0)], focus=(c, r * 1.5))
    render(pid, pid + "_folded_fit_wide", ms, ["right", "three_quarter"],
           frame=[o for o in proxy("warden", ground=False)])
    bipod_pose(False)
    place(pid, Vector((0, 0, 0)))

# ------------------------------------------------------------------------------------------- review close-ups
# Review v2 verification shots: UGL muzzle collar / mouth (lathe steps), UGL +X flank at the latch (fold-over fix),
# laser top face (fold-over fix) and IR window colour, grip ramps (BoneStipple hue), UGL in first person on the Mako.
bc.VIEW_DIRS.setdefault("front_low_left", (0.55, -1.0, -0.22))      # +X = shooter's LEFT
bc.VIEW_DIRS.setdefault("front_high_right", (-0.75, -0.8, 0.35))
bc.VIEW_DIRS.setdefault("under_back", (-0.45, 0.9, -0.75))
bc.VIEW_DIRS.setdefault("top_front", (-0.35, -0.55, 1.0))
bc.VIEW_DIRS.setdefault("fp_left", (0.45, 1.0, 0.30))               # behind the gun, shooter's left: first person
if "closeup" in sets:
    pid = "ugl_launcher"
    ms = meshes(hier(root_of(pid)))
    place(pid, Vector((0, 0, 0)))
    show_only(ms)
    muz = Vector((0.0, -0.128, -0.0615))
    render(pid, pid + "_close_muzzle", ms, ["front_low_left", "front_high_right", "front"], focus=(muz, 0.045))
    render(pid, pid + "_close_latch", ms, ["right", (0.8, -0.35, -0.3)], focus=(Vector((0.03, 0.03, -0.045)), 0.05))
    place(pid, MAKO["Under"])
    show_only(ms + proxy("mako"))
    w = MAKO["Under"] + muz
    render(pid, pid + "_close_onmako", ms, ["front_low_left", "fp_left"], focus=(w + Vector((0, 0.06, 0.03)), 0.12))
    place(pid, Vector((0, 0, 0)))
    for pid in ("laser_R", "laser_L"):
        ms = meshes(hier(root_of(pid)))
        show_only(ms)
        render(pid, pid + "_close", ms, ["top", "top_front", "front"])
    for pid in ("grip_angled", "grip_stub", "grip_vertical"):
        ms = meshes(hier(root_of(pid)))
        show_only(ms)
        render(pid, pid + "_close", ms, ["under_back"])

# ------------------------------------------------------------------------------------------- loadouts
if "loadout" in sets and "mako" in loadout_guns:
    if REAL_MAKO is None or REAL_OPTIC is None:
        raise RuntimeError("Mako loadout previews require the current Mako and holo exports")
    px = proxy("mako")
    A = {"shield_front": MAKO["Shield"], "laser_R": MAKO["Side_R"], "flashlight_L": MAKO["Side_L"],
         "ugl_launcher": MAKO["Under"]}
    vis = list(px)
    for pid, loc in A.items():
        place(pid, loc)
        vis += meshes(hier(root_of(pid)))
    show_only(vis)
    render("loadouts", "mako_loadout_A", vis, ["three_quarter", "right", "left", "three_quarter_back"],
           res=(1400, 900))
    # round 2: the end-on view is framed on the gun's cross-section, not on its 0.8 m bounding sphere (it was tiny)
    render("loadouts", "mako_loadout_A", vis, ["front"], res=(1400, 900), focus=end_on_focus(vis))
    for pid in A:
        place(pid, Vector((0, 0, 0)))
    B = {"grip_angled": MAKO["Under"], "laser_L": MAKO["Side_L"], "flashlight_R": MAKO["Side_R"]}
    vis = list(px)
    for pid, loc in B.items():
        place(pid, loc)
        vis += meshes(hier(root_of(pid)))
    show_only(vis)
    render("loadouts", "mako_loadout_B", vis, ["three_quarter", "left"], res=(1400, 900))
    for pid in B:
        place(pid, Vector((0, 0, 0)))
    C = {"grip_vertical": MAKO["Under"]}
    vis = list(px)
    for pid, loc in C.items():
        place(pid, loc)
        vis += meshes(hier(root_of(pid)))
    show_only(vis)
    render("loadouts", "mako_loadout_C", vis, ["three_quarter"], res=(1400, 900))
    place("grip_vertical", Vector((0, 0, 0)))
    place("grip_stub", MAKO["Under"])
    vis = list(px) + meshes(hier(root_of("grip_stub")))
    show_only(vis)
    render("loadouts", "mako_loadout_D", vis, ["right"], res=(1400, 900))
    place("grip_stub", Vector((0, 0, 0)))

if "loadout" in sets and "warden" in loadout_guns:
    if REAL_WARDEN is None or REAL_SNIPER is None:
        raise RuntimeError("Warden loadout previews require the current Warden and sniper exports")
    pw = proxy("warden")
    place("bipod", WARDEN["Under"])
    vis = pw + meshes(hier(root_of("bipod")))
    if GROUND:
        feet = [o for o in vis if o.type == "MESH" and "ATT_bipod_Foot_" in o.name]
        sole_z = min((o.matrix_world @ v.co).z for o in feet for v in o.data.vertices)
        GROUND.location.z = sole_z - GROUND.dimensions.z / 2
        bpy.context.view_layer.update()
    show_only(vis)
    render("loadouts", "warden_bipod", vis, ["three_quarter", "right"], res=(1400, 900),
           frame=[o for o in pw if o is not GROUND])
    render("loadouts", "warden_bipod", vis, ["front"], res=(1400, 900),
           focus=end_on_focus([o for o in vis if o is not GROUND]))
    bipod_pose(True)
    vis_f = [o for o in vis if o is not GROUND]          # carried pose: no ground (the gun is not resting on it)
    show_only(vis_f)
    render("loadouts", "warden_bipod_folded", vis_f, ["three_quarter", "right"], res=(1400, 900),
           frame=[o for o in pw if o is not GROUND])
    bipod_pose(False)
    place("bipod", Vector((0, 0, 0)))

if "loadout" in sets:
    # Record precisely which gun export each refreshed row used, so stale loadouts can be identified later.
    source_path = Path(OUT) / "loadouts" / "sources.json"
    sources = json.loads(source_path.read_text()) if source_path.exists() else {}
    for gun in sorted(loadout_guns):
        folder, filename = {"mako": ("ar7_mako", "mako_default.glb"),
                            "warden": ("vk50_warden", "warden_default.glb")}[gun]
        source = Path(WEAPONS) / folder / filename
        sources[gun] = {"gun": str(source), "gun_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "tactical_blend_sha256": hashlib.sha256(Path(a.blend).read_bytes()).hexdigest(),
                        "image_prefix": "warden_bipod" if gun == "warden" else "mako_loadout"}
        sources[gun]["images_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                          for path in sorted(source_path.parent.glob(sources[gun]["image_prefix"] + "*.png"))}
        optic = Path(WEAPONS) / "attachments" / "optics" / ("ATT_optic_sniper.glb" if gun == "warden" else "ATT_optic_holo.glb")
        if optic.exists():
            sources[gun]["optic"] = str(optic)
            sources[gun]["optic_sha256"] = hashlib.sha256(optic.read_bytes()).hexdigest()
    source_path.write_text(json.dumps(sources, indent=2) + "\n")

# ------------------------------------------------------------------------------------------- shield sight line
if "sight" in sets:
    pid = "shield_front"
    S = MAKO["Shield"]
    place(pid, S)
    ms = meshes(hier(root_of(pid)))
    glass = bpy.data.objects["ATT_shield_front_Glass"]
    gm = glass.material_slots[0].material
    gp = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    out = os.path.join(OUT, pid)
    os.makedirs(out, exist_ok=True)
    # side view of the sight band (studio light, as before)
    px_side = proxy("mako", optic=False)
    rods = []
    grn = bc.material("_M_Band", (0.1, 1.0, 0.2), emission=(0.1, 1.0, 0.2), emission_strength=4)
    eye_y = MAKO["Optic"].y + 0.060
    for dz in (0.040, 0.075):
        bpy.ops.mesh.primitive_cylinder_add(radius=0.0007, depth=0.9, location=(0, eye_y - 0.45, S.z + dz),
                                            rotation=(math.radians(90), 0, 0))
        rd = bpy.context.active_object
        rd.data.materials.append(grn)
        rods.append(rd)
    cam_d = bpy.data.cameras.new("_EyeCam")
    cam = bpy.data.objects.new("_EyeCam", cam_d)
    scene.collection.objects.link(cam)
    scene.camera = cam
    bc.setup_cycles_gpu(scene, a.samples)
    show_only(ms + px_side + rods)
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 0.66
    cam.location = (1.0, S.y + 0.17, S.z + 0.02)
    cam.rotation_euler = (math.radians(90), 0, math.radians(90))
    scene.render.resolution_x, scene.render.resolution_y = 1400, 700
    scene.render.filepath = os.path.join(out, "shield_front_sight_side.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", scene.render.filepath)
    for rd in rods:
        rd.hide_render = True

    # ---- review v2: DAYLIGHT range (sun + sky, ground, checker board and an orange post 6 m out)
    for o in scene.objects:
        if o.type == "LIGHT":
            o.hide_render = True
    day = bpy.data.worlds.new("_Day")
    day.use_nodes = True
    bgn = next(n for n in day.node_tree.nodes if n.type == "BACKGROUND")
    bgn.inputs[0].default_value = (0.55, 0.68, 0.86, 1.0)
    bgn.inputs[1].default_value = 1.1
    scene.world = day
    sd = bpy.data.lights.new("_Sun", "SUN")
    sd.energy = 4.0
    sd.angle = math.radians(2.0)
    sun = bpy.data.objects.new("_Sun", sd)
    scene.collection.objects.link(sun)
    sun.rotation_euler = Vector((0.35, -0.55, -0.75)).to_track_quat("-Z", "Y").to_euler()
    tmp = []
    gz = S.z - 1.80
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, -20, gz))
    gnd = bpy.context.active_object
    gnd.data.materials.append(bc.material("_M_Dirt", (0.13, 0.14, 0.10), rough=0.95))
    tmp.append(gnd)
    BY = eye_y - 6.0
    BZ = S.z + 0.06 - 0.25
    bpy.ops.mesh.primitive_plane_add(size=3.0, location=(0, BY, BZ), rotation=(math.radians(90), 0, 0))
    board = bpy.context.active_object
    bm_ = bpy.data.materials.new("_M_Checker")
    bm_.use_nodes = True
    bp = next(n for n in bm_.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    ck = bm_.node_tree.nodes.new("ShaderNodeTexChecker")
    ck.inputs["Color1"].default_value = (0.02, 0.02, 0.02, 1)
    ck.inputs["Color2"].default_value = (0.80, 0.80, 0.80, 1)
    ck.inputs["Scale"].default_value = 12.0                      # 3 m / 12 = 0.25 m squares
    bm_.node_tree.links.new(ck.outputs["Color"], bp.inputs["Base Color"])
    bp.inputs["Roughness"].default_value = 0.85
    board.data.materials.append(bm_)
    tmp.append(board)
    POST_X = -0.55
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(POST_X, BY + 0.3, BZ))
    post = bpy.context.active_object
    post.scale = (0.20, 0.20, 3.0)
    post.data.materials.append(bc.material("_M_Post", (0.80, 0.30, 0.08), rough=0.6))
    tmp.append(post)
    bpy.context.view_layer.update()

    def sample(path, pts, cam_obj, k=3):
        """Average sRGB 8-bit colour of a (2k+1)^2 pixel patch around each world point."""
        img = bpy.data.images.load(path, check_existing=False)
        w, h = img.size
        pix = list(img.pixels[:])
        res = {}
        for name, p in pts.items():
            uv = world_to_camera_view(scene, cam_obj, Vector(p))
            cx, cy = int(uv.x * w), int(uv.y * h)
            acc = [0.0, 0.0, 0.0]
            n = 0
            for yy in range(cy - k, cy + k + 1):
                for xx in range(cx - k, cx + k + 1):
                    if 0 <= xx < w and 0 <= yy < h:
                        i = (yy * w + xx) * 4
                        for c in range(3):
                            acc[c] += pix[i + c]
                        n += 1
            res[name] = [int(round(255 * v / max(n, 1))) for v in acc]   # loaded PNG pixels are display (sRGB)
        bpy.data.images.remove(img)
        return res

    def lum(c):
        lin = [(v / 255 / 12.92) if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    def board_pts(eye):
        """Points to sample: two neighbouring checker squares + the post seen through the glass centre, the post
        seen through the port."""
        plate_y = S.y - 0.034
        g = Vector((0.0, plate_y, S.z + 0.065))                  # glass centre
        d = (g - eye).normalized()
        t = (BY - eye.y) / d.y
        hit = eye + d * t
        sq = 0.25
        ix, iz = math.floor(hit.x / sq), math.floor((hit.z - (BZ - 1.5)) / sq)
        c0 = Vector(((ix + 0.5) * sq, BY + 0.001, BZ - 1.5 + (iz + 0.5) * sq))
        c1 = c0 + Vector((sq, 0, 0))
        tp = (BY + 0.2 - eye.y) / d.y
        post_g = Vector((POST_X, BY + 0.2, (eye + d * tp).z))
        pp = Vector((0.0, plate_y, S.z - 0.037))                 # port centre
        d2 = (pp - eye).normalized()
        t2 = (BY + 0.2 - eye.y) / d2.y
        post_p = Vector((POST_X, BY + 0.2, (eye + d2 * t2).z))
        return {"square_a": c0, "square_b": c1, "post_through_glass": post_g, "post_through_port": post_p}

    px = proxy("mako", optic=False)
    report = {"scene": "sun 4.0 + sky (0.55,0.68,0.86) x1.1, board 6 m out, 0.25 m checker 2%/80%, orange post",
              "glass_material": {"base": list(gp.inputs["Base Color"].default_value)[:3],
                                 "alpha": gp.inputs["Alpha"].default_value,
                                 "roughness": gp.inputs["Roughness"].default_value}, "views": {}}
    cam_d.type = "PERSP"
    cam_d.lens = 30
    cam_d.clip_start = 0.005
    scene.render.resolution_x, scene.render.resolution_y = 1200, 800
    cam.rotation_euler = (math.radians(90), 0, math.radians(180))   # look down -Y (muzzle)

    def eye_render(fname, eye, vis, label):
        show_only(vis + tmp)
        cam.location = eye
        bpy.context.view_layer.update()
        p = os.path.join(out, fname)
        scene.render.filepath = p
        bpy.ops.render.render(write_still=True)
        print("rendered", p)
        smp = sample(p, board_pts(Vector(eye)), cam)
        a_, b_ = lum(smp["square_a"]), lum(smp["square_b"])
        smp["checker_contrast"] = round((max(a_, b_) + 0.05) / (min(a_, b_) + 0.05), 2)
        report["views"][label] = smp
        return p

    for dz in (0.040, 0.0575, 0.075):
        eye_render(f"shield_front_sight_eye_{int(dz * 10000):03d}.png", (0, eye_y, S.z + dz), ms + px,
                   f"eye_{dz:.4f}")
    E = (0, eye_y, S.z + 0.0575)
    eye_render("shield_front_sight_eye_575_noglass.png", E, [o for o in ms if o is not glass] + px,
               "eye_0.0575_no_glass")
    old = (tuple(gp.inputs["Base Color"].default_value), gp.inputs["Alpha"].default_value)
    gp.inputs["Base Color"].default_value = (0.24, 0.50, 0.85, 1.0)        # pre-review glass, for comparison
    gp.inputs["Alpha"].default_value = 0.40
    eye_render("shield_front_sight_eye_575_oldglass.png", E, ms + px, "eye_0.0575_old_glass_pre_review")
    gp.inputs["Base Color"].default_value = old[0]
    gp.inputs["Alpha"].default_value = old[1]
    # ADS through the real holo optic (default Mako optic), first-person lens
    if OPTIC_ROOT:
        ads_eye = (0, MAKO["Optic"].y + ADS.y + 0.075, MAKO["Optic"].z + ADS.z)
        cam_d.lens = 40
        eye_render("shield_front_sight_ads_holo.png", ads_eye, ms + px + optic_meshes(), "ads_holo")
    report["socket_source"] = SOCKET_SRC
    with open(os.path.join(out, "shield_front_sight_daylight.json"), "w") as fh:
        json.dump(report, fh, indent=1)
    print("SIGHT", json.dumps(report["views"]))
    place(pid, Vector((0, 0, 0)))
print("RENDER DONE")
