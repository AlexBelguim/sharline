"""QA copy of review/review_render.py (the reviewer's in-play renders), reading the kit's CURRENT parameters:
orbit height + weight visuals from halo_data.py, per-core pip empties HALO_<Core>_PIP_*, band lip glass.
Raw renders go to qa/renders/_raw; qa/qa_compose.py builds the sheets.

Original reviewer docstring:
Reviewer renders of the HALO kit, assembled from the EXPORTED .glb files (fresh scene, engine-style assembly).

Run (one job per call keeps scenes simple):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/review/review_render.py" -- <job>
jobs: eyelevel | distance | underside | closeups | wire | ingame
Raw renders go to review/renders/_raw/, sheets are composed afterwards by review/compose.py (system Python).
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = r"F:/git/val etf/assets/shields"
EXP = os.path.join(ROOT, "export")
RAW = os.path.join(ROOT, "qa", "renders", "_raw")
CHAR = r"F:/git/val etf/assets/characters/kestrel/trellis/kestrel_trellis_s123.glb"
os.makedirs(RAW, exist_ok=True)
JOB = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "eyelevel"

CORES = ("Bulwark", "Mender", "Volt", "Phase")
ZONES = ("Head", "Arms", "Torso", "Legs")
ZANG = {"Arms": 0.0, "Torso": 90.0, "Legs": 180.0, "Head": 270.0}
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
from halo_data import WEIGHT_VISUALS as _WV  # noqa: E402
WEIGHT = {k: (v["scale"], v["band"], v["orbit_r"], v["cells"]) for k, v in _WV.items()}
ORBIT_Z = {k: v["orbit_z"] for k, v in _WV.items()}
IDLE, LIT, FLARE = 0.9, 2.4, 6.0

bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene


# ------------------------------------------------------------------------------------------ import kit
def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    return new


KIT = {}
for f in ("HALO_Materials", "HALO_Bulwark", "HALO_Mender", "HALO_Volt", "HALO_Phase", "HALO_Common", "HALO_Pickups"):
    for o in imp(os.path.join(EXP, f + ".glb")):
        KIT[o.name] = o
for o in KIT.values():
    if o.type == "MESH":
        o.data.transform(o.matrix_world)
    for c in list(o.users_collection):
        c.objects.unlink(o)
bpy.context.view_layer.update()
PIPS = {c: [KIT[f"HALO_{c}_PIP_{i}"].matrix_world.translation.copy() for i in range(1, 5)] for c in CORES}
BASE_MATS = {n: bpy.data.materials[n] for n in ("M_HALO_Glass_T1", "M_HALO_Glass_T2", "M_HALO_Glass_T3",
                                                "M_HALO_Glass_T4", "M_HALO_Glass_Off")}
_MC = {}


def principled(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def glass(tier, strength):
    if not tier:
        return BASE_MATS["M_HALO_Glass_Off"]
    key = (tier, strength)
    if key not in _MC:
        m = BASE_MATS[f"M_HALO_Glass_T{tier}"].copy()
        p = principled(m)
        # re-imported T1 carries a normalised colour * 2.208; set every tier to spec colour * strength
        col = {1: (0.85, 0.88, 0.92), 2: (0.10, 0.45, 1.0), 3: (0.55, 0.15, 1.0), 4: (1.0, 0.62, 0.08)}[tier]
        p.inputs["Emission Color"].default_value = (*col, 1)
        p.inputs["Emission Strength"].default_value = strength
        _MC[key] = m
    return _MC[key]


def glass_slot(o):
    for i, s in enumerate(o.material_slots):
        if s.material and s.material.name.startswith("M_HALO_Glass"):
            return i
    return None


def inst(name, parent, loc=(0, 0, 0), rot_z=0.0, scale=1.0, mat=None):
    src = KIT[name]
    o = src.copy()
    SC.collection.objects.link(o)
    o.parent = parent
    o.matrix_parent_inverse = Matrix.Identity(4)
    o.location = loc
    o.rotation_euler = (0, 0, rot_z)
    o.scale = (scale,) * 3
    if mat is not None:
        gs = glass_slot(o)
        o.material_slots[gs].link = "OBJECT"
        o.material_slots[gs].material = mat
    return o


def halo(core, weight, arc_tiers, loc=(0, 0, 0), s=IDLE, rot_z=0.0, cell_angles=None, cell_s=1.4, band=True,
         cells=True, pips=True, far=False, zscale=1.0):
    """far=True: far LOD set; zscale stretches the root vertically (engine min-thickness trick at range)."""
    sc, b, orb, n = WEIGHT[weight]
    root = bpy.data.objects.new("_root", None)
    SC.collection.objects.link(root)
    root.location = loc
    root.rotation_euler = (0, 0, rot_z)
    root.scale = (sc, sc, sc * zscale)
    top = max(arc_tiers.values())
    for z in ZONES:
        inst(f"HALO_{core}_Far_Glass_{z}" if far else f"HALO_{core}_Arc_{z}", root, mat=glass(arc_tiers.get(z, 0), s))
    if far:
        fr = f"HALO_{core}_Far_Frame_{weight}"
        inst(fr, root, mat=glass(top or 1, s) if glass_slot(KIT[fr]) is not None else None)
        pips = False
    elif band and b:
        inst(f"HALO_{core}_Band_{b}", root, mat=glass(top or 1, s))
    if pips and top:
        for p in PIPS[core][:top]:
            inst("HALO_TierPip", root, loc=p, mat=glass(top, s))
    if cells:
        angs = cell_angles if cell_angles is not None else [15.0 + k * 360.0 / n for k in range(n)]
        for a in angs:
            r = math.radians(a)
            inst("HALO_PowerCell", root, loc=(orb * math.cos(r), orb * math.sin(r), ORBIT_Z[weight]), rot_z=r + math.pi / 2,
                 mat=glass(top or 1, cell_s))
    return root


# ------------------------------------------------------------------------------------------ render setup
def world(bg):
    w = bpy.data.worlds.get("W") or bpy.data.worlds.new("W")
    w.use_nodes = True
    bgn = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bgn.inputs[0].default_value = (*bg, 1)
    bgn.inputs[1].default_value = 1.0
    SC.world = w


def lights(center=(0, 0, 0), k=1.0, sun=False):
    for o in list(bpy.data.objects):
        if o.name.startswith("L_"):
            bpy.data.objects.remove(o, do_unlink=True)
    c = Vector(center)
    if sun:
        ld = bpy.data.lights.new("L_Sun", "SUN")
        ld.energy = 3.0 * k
        lo = bpy.data.objects.new("L_Sun", ld)
        lo.rotation_euler = (math.radians(40), math.radians(10), math.radians(-35))
        SC.collection.objects.link(lo)
        return
    for name, off, e, size in (("Key", (-2.5, -3.0, 3.0), 420, 1.2), ("Fill", (3.5, -2.5, 1.0), 120, 2.0),
                               ("Rim", (1.2, 4.0, 1.6), 520, 1.0), ("RimL", (-3.0, 3.0, 1.0), 260, 1.0)):
        ld = bpy.data.lights.new("L_" + name, "AREA")
        ld.energy = e * k
        ld.size = size
        lo = bpy.data.objects.new("L_" + name, ld)
        lo.location = c + Vector(off)
        lo.rotation_euler = (c - lo.location).to_track_quat("-Z", "Y").to_euler()
        SC.collection.objects.link(lo)


def setup(res, transparent=False, bloom=0.0, samples=32, bg=(0.032, 0.034, 0.04), threshold=1.0):
    try:
        SC.render.engine = "BLENDER_EEVEE"
    except TypeError:
        pass
    SC.eevee.taa_render_samples = samples
    SC.render.resolution_x, SC.render.resolution_y = res
    SC.render.resolution_percentage = 100
    SC.render.film_transparent = transparent
    SC.render.image_settings.file_format = "PNG"
    SC.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    try:
        SC.view_settings.view_transform = "Khronos PBR Neutral"
    except Exception:
        SC.view_settings.view_transform = "AgX"
    world(bg)
    if bloom and not transparent:
        ng = bpy.data.node_groups.get("_C") or bpy.data.node_groups.new("_C", "CompositorNodeTree")
        if not ng.interface.items_tree:
            ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        ng.nodes.clear()
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        gl.inputs["Type"].default_value = "Bloom"
        gl.inputs["Threshold"].default_value = threshold
        gl.inputs["Strength"].default_value = bloom
        gl.inputs["Size"].default_value = 0.4
        out = ng.nodes.new("NodeGroupOutput")
        ng.links.new(rl.outputs["Image"], gl.inputs["Image"])
        ng.links.new(gl.outputs[0], out.inputs[0])
        SC.compositing_node_group = ng
        SC.render.use_compositing = True
    else:
        SC.render.use_compositing = False


def camera(loc, target, lens=50.0, ortho=None, vfov=None):
    cd = bpy.data.cameras.get("_Cam") or bpy.data.cameras.new("_Cam")
    cam = bpy.data.objects.get("_Cam")
    if cam is None:
        cam = bpy.data.objects.new("_Cam", cd)
        SC.collection.objects.link(cam)
    cd.clip_start, cd.clip_end = 0.005, 500
    if ortho:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
    else:
        cd.type = "PERSP"
        if vfov:
            cd.sensor_fit = "VERTICAL"
            cd.angle_y = math.radians(vfov)
        else:
            cd.sensor_fit = "AUTO"
            cd.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    SC.camera = cam
    return cam


def cam_dir(target, elev, azim, dist, **kw):
    e, a = math.radians(elev), math.radians(azim)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    return camera(Vector(target) + d * dist, target, **kw)


def render(name):
    p = os.path.join(RAW, name + ".png")
    SC.render.filepath = p
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        print("EEVEE failed, CPU Cycles:", e)
        SC.render.engine = "CYCLES"
        SC.cycles.device = "CPU"
        SC.cycles.samples = 32
        bpy.ops.render.render(write_still=True)
        SC.render.engine = "BLENDER_EEVEE"
    print("RENDERED", p)
    return p


def clear():
    for o in list(SC.collection.objects):
        if o.name.startswith(("_root", "HALO_", "_w", "_char", "_floor")) or o.parent is not None:
            pass
    for o in list(bpy.data.objects):
        if o.users_collection and o.name not in ("_Cam",) and not o.name.startswith("L_"):
            bpy.data.objects.remove(o, do_unlink=True)


# realistic idle presets (sum of arc tiers decides the weight class, game/assets/data/armor.ron)
PRESET = {
    "Light": {"Head": 0, "Torso": 1, "Arms": 0, "Legs": 0},      # Phase Runner style, sum 1
    "Medium": {"Head": 2, "Torso": 2, "Arms": 0, "Legs": 2},     # Volt Sentry style, sum 6
    "Heavy": {"Head": 3, "Torso": 3, "Arms": 3, "Legs": 0},      # Bulwark Assault style, sum 9
}


# ------------------------------------------------------------------------------------------ jobs
def job_eyelevel():
    """All 4 cores x 3 weights at in-play angles: -2 deg (enemy ~10 m away) and -8 deg (~2.5 m)."""
    xs = {"Light": -0.75, "Medium": 0.0, "Heavy": 0.85}
    for elev in (-2, -8):
        clear()
        for r, core in enumerate(CORES):
            for w, x in xs.items():
                halo(core, w, PRESET[w], loc=(x, 0, -r * 0.30), s=IDLE)
        lights(center=(0, 0, -0.45))
        cam_dir((0.05, 0, -0.45), elev, 0, 12.0, ortho=2.3)
        setup((2000, 1100), bloom=0.35, threshold=0.6)
        render(f"eyelevel_{abs(elev)}_idle")
        setup((2000, 1100), transparent=True)
        render(f"eyelevel_{abs(elev)}_alpha")
    # same, from the side (+X): the Phase gap and Volt teeth profile
    clear()
    for r, core in enumerate(CORES):
        for w, x in xs.items():
            halo(core, w, PRESET[w], loc=(0, -x, -r * 0.30), s=IDLE)
    lights(center=(0, 0, -0.45))
    cam_dir((0, -0.05, -0.45), -2, 90, 12.0, ortho=2.3)
    setup((2000, 1100), transparent=True)
    render("eyelevel_side_2_alpha")


def job_distance():
    """Game camera: vertical FOV 78 deg (render.rs), 1080p -> 667/d px per metre; eye 1.6 m, halo ~1.92 m."""
    order = [(c, w) for c in CORES for w in ("Light", "Medium", "Heavy")]
    for d in (10, 25, 50):
        clear()
        for i, (core, w) in enumerate(order):
            halo(core, w, PRESET[w], loc=((i - 5.5) * 0.8, 0, 0), s=IDLE)
        ppm = 667.0 / d
        width_m = 10.0
        res = (int(round(width_m * ppm)), max(8, int(round(0.5 * ppm))))
        elev = -math.degrees(math.atan(0.32 / d))
        lights()
        cam_dir((0, 0, 0.0), elev, 0, 30.0, ortho=width_m)
        for bgname, bg in (("dark", (0.02, 0.022, 0.026)), ("day", (0.32, 0.36, 0.42))):
            setup(res, bloom=0.3, threshold=0.8, samples=64, bg=bg)
            render(f"dist_{d}m_{bgname}")
        setup(res, transparent=True, samples=64)
        render(f"dist_{d}m_alpha")


def job_distance_far():
    """Same strips as job_distance with the far LOD; beyond 20 m the root is stretched vertically by d / 20
    (the NOTES.md min-thickness recommendation), so the ring keeps about 1 px of height."""
    order = [(c, w) for c in CORES for w in ("Light", "Medium", "Heavy")]
    for d in (25, 50):
        clear()
        for i, (core, w) in enumerate(order):
            halo(core, w, PRESET[w], loc=((i - 5.5) * 0.8, 0, 0), s=IDLE, far=True, zscale=max(1.0, d / 20.0))
        ppm = 667.0 / d
        width_m = 10.0
        res = (int(round(width_m * ppm)), max(8, int(round(0.5 * ppm))))
        elev = -math.degrees(math.atan(0.32 / d))
        lights()
        cam_dir((0, 0, 0.0), elev, 0, 30.0, ortho=width_m)
        for bgname, bg in (("dark", (0.02, 0.022, 0.026)), ("day", (0.32, 0.36, 0.42))):
            setup(res, bloom=0.3, threshold=0.8, samples=64, bg=bg)
            render(f"distfar_{d}m_{bgname}")
        setup(res, transparent=True, samples=64)
        render(f"distfar_{d}m_alpha")


def job_underside():
    clear()
    cfg = [("Bulwark", "Medium"), ("Bulwark", "Heavy"), ("Volt", "Heavy"), ("Phase", "Light"), ("Mender", "Heavy")]
    for i, (core, w) in enumerate(cfg):
        halo(core, w, PRESET[w], loc=((i - 2) * 0.75, 0, 0), s=IDLE)
    lights()
    cam_dir((0, 0, 0), -35, 15, 12, ortho=3.9)
    setup((2200, 800), bloom=0.35, threshold=0.6)
    render("underside_35")
    # top-down 60 deg, own-halo HUD angle, rendered tiny like a HUD widget (128 px each)
    clear()
    hud = [("Mender", "Medium", {"Head": 1, "Torso": 3, "Arms": 1, "Legs": 1}),
           ("Volt", "Medium", {"Head": 0, "Torso": 3, "Arms": 3, "Legs": 0}),
           ("Bulwark", "Heavy", {"Head": 2, "Torso": 4, "Arms": 2, "Legs": 1}),
           ("Phase", "Light", {"Head": 0, "Torso": 1, "Arms": 0, "Legs": 0})]
    for i, (core, w, at) in enumerate(hud):
        halo(core, w, at, loc=((i - 1.5) * 0.8, 0, 0), s=LIT, cells=False)
    lights()
    cam_dir((0, 0, 0), 60, 0, 10, ortho=3.2)
    setup((512, 128), bloom=0.3, threshold=0.8, samples=64)
    render("hud_128px")


def job_closeups():
    shots = []
    # 1. pips over each core's Head arc (front, 10 deg above), T4 = 4 pips
    for core in CORES:
        clear()
        halo(core, "Light", {"Head": 4, "Torso": 4, "Arms": 4, "Legs": 4}, s=LIT, cells=False, band=False)
        o = bpy.data.objects["_root"]
        o.scale = (1, 1, 1)
        lights(center=(0, -0.15, 0))
        cam_dir((0, -0.155, 0.012), 10, 0, 1.0, ortho=0.11)
        setup((900, 500), bloom=0.25, threshold=1.0)
        shots.append(render(f"close_pips_{core}"))
    # 2. Phase gap electrodes (back, from above-behind)
    clear()
    halo("Phase", "Medium", {"Head": 2, "Torso": 2, "Arms": 2, "Legs": 2}, s=LIT, cells=False)
    bpy.data.objects["_root"].scale = (1, 1, 1)
    lights(center=(0, 0.16, 0))
    cam_dir((0, 0.16, 0.0), 25, 180, 1.0, ortho=0.16)
    setup((900, 600), bloom=0.25)
    render("close_phase_gap")
    # 3. Volt tooth + Bulwark corner seam + Mender joint
    clear()
    halo("Volt", "Heavy", {"Head": 3, "Torso": 3, "Arms": 3, "Legs": 3}, s=LIT, cells=False)
    bpy.data.objects["_root"].scale = (1, 1, 1)
    a = math.radians(270 - 22.5)
    c = Vector((0.16 * math.cos(a), 0.16 * math.sin(a), 0.02))
    lights(center=c)
    cam_dir(c, 12, -35, 1.0, ortho=0.13)
    setup((900, 600), bloom=0.25)
    render("close_volt_tooth")
    clear()
    halo("Bulwark", "Heavy", {"Head": 2, "Torso": 2, "Arms": 2, "Legs": 2}, s=LIT, cells=False)
    bpy.data.objects["_root"].scale = (1, 1, 1)
    a = math.radians(315)
    c = Vector((0.17 * math.cos(a), 0.17 * math.sin(a), -0.02))
    lights(center=c)
    cam_dir(c, 22, -45, 1.0, ortho=0.17)
    setup((900, 600), bloom=0.25)
    render("close_bulwark_seam")
    clear()
    halo("Mender", "Medium", {"Head": 1, "Torso": 1, "Arms": 1, "Legs": 1}, s=LIT, cells=False)
    bpy.data.objects["_root"].scale = (1, 1, 1)
    a = math.radians(315)
    c = Vector((0.16 * math.cos(a), 0.16 * math.sin(a), 0.0))
    lights(center=c)
    cam_dir(c, 30, -45, 1.0, ortho=0.12)
    setup((900, 600), bloom=0.25)
    render("close_mender_joint")
    # 4. power cell side + top, at the Heavy orbit next to the heavy band
    clear()
    halo("Bulwark", "Heavy", {"Head": 4, "Torso": 4, "Arms": 4, "Legs": 4}, s=LIT, cell_angles=[300.0], cell_s=LIT)
    bpy.data.objects["_root"].scale = (1, 1, 1)
    a = math.radians(300)
    c = Vector((0.275 * math.cos(a), 0.275 * math.sin(a), 0.0))
    lights(center=c)
    cam_dir(c, 8, 0, 1.0, ortho=0.20)
    setup((900, 600), bloom=0.25)
    render("close_cell_side")
    cam_dir(c, 70, 20, 1.0, ortho=0.20)
    render("close_cell_top")


def wire_overlay(o, thick=0.00025):
    w = o.copy()
    w.data = o.data.copy()
    SC.collection.objects.link(w)
    w.parent = o.parent
    w.matrix_parent_inverse = Matrix.Identity(4)
    w.location, w.rotation_euler, w.scale = o.location, o.rotation_euler, o.scale
    w.data.materials.clear()
    m = bpy.data.materials.get("_wire") or bpy.data.materials.new("_wire")
    m.use_nodes = True
    p = principled(m)
    p.inputs["Base Color"].default_value = (0, 0, 0, 1)
    p.inputs["Emission Color"].default_value = (1.0, 0.45, 0.1, 1)
    p.inputs["Emission Strength"].default_value = 1.5
    w.data.materials.append(m)
    mod = w.modifiers.new("wf", "WIREFRAME")
    mod.thickness = thick
    mod.use_replace = True
    mod.use_even_offset = False
    return w


def job_wire():
    for name, tgt, elev, azim, ortho, thick in (
            ("HALO_Volt_Arc_Head", (0, -0.16, 0.01), 30, 0, 0.30, 0.00022),
            ("HALO_Mender_Arc_Head", (0, -0.16, 0.0), 35, 0, 0.30, 0.00022),
            ("HALO_Bulwark_Band_Heavy", (0, 0, -0.03), 25, 20, 0.55, 0.0004),
            ("HALO_Core_Phase", (0, 0, 0.026), 30, 15, 0.11, 0.00012),
            ("HALO_PowerCell", (-0.01, 0, 0), 25, 30, 0.10, 0.0001)):
        clear()
        o = inst(name, None, mat=glass(2, 0.6) if glass_slot(KIT[name]) is not None else None)
        wire_overlay(o, thick)
        lights(center=tgt, k=0.6)
        cam_dir(tgt, elev, azim, 2.0, ortho=ortho)
        setup((1000, 650), samples=32, bg=(0.02, 0.02, 0.024))
        render("wire_" + name.replace("HALO_", ""))


def import_char(offset_x=0.0):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=CHAR)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    roots = [o for o in new if o.parent is None]
    bpy.context.view_layer.update()

    def bounds():
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        return (Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)]))
    mn, mx = bounds()
    s = 1.70 / (mx.z - mn.z)
    for r in roots:
        r.scale = r.scale * s
        r.location = r.location * s
    bpy.context.view_layer.update()
    mn, mx = bounds()
    off = Vector((offset_x - (mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z))
    for r in roots:
        r.location += off
    bpy.context.view_layer.update()
    top = max((o.matrix_world @ v.co).z for o in meshes for v in o.data.vertices)
    return Vector((offset_x, 0.0, top))


def job_ingame():
    """Three Kestrels with realistic presets, seen by a standing player (eye 1.6 m, vfov 78 deg, 1080p)."""
    clear()
    cfg = [("Phase", "Light", PRESET["Light"]), ("Volt", "Medium", PRESET["Medium"]),
           ("Bulwark", "Heavy", PRESET["Heavy"])]
    tops = []
    for i, (core, w, at) in enumerate(cfg):
        t = import_char((i - 1) * 1.1)
        tops.append(t)
        halo(core, w, at, loc=t + Vector((0, 0, 0.22)), s=IDLE, cell_angles=[40 + k * 360 / WEIGHT[w][3]
                                                                           for k in range(WEIGHT[w][3])])
    # floor
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60)
    me = bpy.data.meshes.new("_floor")
    bm.to_mesh(me)
    bm.free()
    fl = bpy.data.objects.new("_floor", me)
    SC.collection.objects.link(fl)
    fm = bpy.data.materials.new("_floorm")
    fm.use_nodes = True
    principled(fm).inputs["Base Color"].default_value = (0.09, 0.09, 0.1, 1)
    me.materials.append(fm)
    lights(sun=True)
    for d in (5, 15):
        for bgname, bg in (("day", (0.30, 0.34, 0.40)),):
            camera((0.4, -d, 1.6), (0.0, 0.0, 1.55), vfov=78)
            setup((1920, 1080), bloom=0.3, threshold=0.8, samples=48, bg=bg)
            render(f"ingame_{d}m_{bgname}")
    # night-ish
    for o in list(bpy.data.objects):
        if o.name.startswith("L_"):
            o.data.energy *= 0.08
    camera((0.4, -5, 1.6), (0.0, 0.0, 1.55), vfov=78)
    setup((1920, 1080), bloom=0.3, threshold=0.8, samples=48, bg=(0.012, 0.013, 0.018))
    render("ingame_5m_night")


{"eyelevel": job_eyelevel, "distance": job_distance, "distance_far": job_distance_far, "underside": job_underside, "closeups": job_closeups,
 "wire": job_wire, "ingame": job_ingame}[JOB]()
print("JOB DONE", JOB)
