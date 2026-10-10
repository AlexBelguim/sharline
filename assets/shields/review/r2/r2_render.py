"""Review round 2: reviewer renders of the HALO kit, assembled engine-style from the EXPORTED .glb files
(fresh factory scene, materials as shipped in HALO_Materials.glb).

Run one job per call:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/shields/review/r2/r2_render.py" -- <job>
jobs: blind | edgeon | closeups | wire | states | char | farlod
Raw renders -> review/r2/renders/_raw/ ; sheets are composed by review/r2/r2_compose.py (system Python).
"""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = r"F:/git/val etf/assets/shields"
EXP = os.path.join(ROOT, "export")
RAW = os.path.join(ROOT, "review", "r2", "renders", "_raw")
CHAR = r"F:/git/val etf/assets/characters/kestrel/trellis/kestrel_trellis_s123.glb"
os.makedirs(RAW, exist_ok=True)
JOB = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "blind"

CORES = ("Bulwark", "Mender", "Volt", "Phase")
ZONES = ("Head", "Arms", "Torso", "Legs")
# scale, band, orbit radius, cells  (orbit height 0.058 halo-local: NOTES.md / catalog weight_class_visuals)
WEIGHT = {"Light": (0.85, None, 0.215, 1), "Medium": (1.0, "Medium", 0.245, 2), "Heavy": (1.2, "Heavy", 0.275, 3)}
ORBIT_Z = 0.058
BANDS = [("Light", 1, 4), ("Medium", 5, 8), ("Heavy", 9, 16)]
IDLE, LIT, FLARE = 0.9, 2.4, 6.0
TIERC = {1: (0.85, 0.88, 0.92), 2: (0.10, 0.45, 1.0), 3: (0.55, 0.15, 1.0), 4: (1.0, 0.62, 0.08)}

bpy.ops.wm.read_factory_settings(use_empty=True)
SC = bpy.context.scene


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


KIT = {}
for f in ("HALO_Materials", "HALO_Bulwark", "HALO_Mender", "HALO_Volt", "HALO_Phase", "HALO_Common",
          "HALO_Pickups"):
    for o in imp(os.path.join(EXP, f + ".glb")):
        KIT[o.name] = o
for o in KIT.values():
    if o.type == "MESH":
        o.data.transform(o.matrix_world)
    for c in list(o.users_collection):
        c.objects.unlink(o)
bpy.context.view_layer.update()
MAT = {m.name: m for m in bpy.data.materials}
_MC = {}


def principled(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def glass(tier, strength=IDLE):
    """tier 0 = uncovered (shipped Glass_Off), ('B', t) = shipped Broken_T<t>, else tier glass at strength."""
    if not tier:
        return MAT["M_HALO_Glass_Off"]
    if isinstance(tier, tuple):
        return MAT[f"M_HALO_Glass_Broken_T{tier[1]}"]
    key = (tier, strength)
    if key not in _MC:
        m = MAT[f"M_HALO_Glass_T{tier}"].copy()
        p = principled(m)
        p.inputs["Emission Color"].default_value = (*TIERC[tier], 1)
        p.inputs["Emission Strength"].default_value = strength
        _MC[key] = m
    return _MC[key]


def glass_slots(o):
    return [i for i, s in enumerate(o.material_slots) if s.material and s.material.name.startswith("M_HALO_Glass")]


def inst(name, parent, loc=(0, 0, 0), rot_z=0.0, scale=1.0, mat=None):
    o = KIT[name].copy()
    SC.collection.objects.link(o)
    o.parent = parent
    o.matrix_parent_inverse = Matrix.Identity(4)
    o.location = loc
    o.rotation_euler = (0, 0, rot_z)
    o.scale = (scale,) * 3
    if mat is not None:
        for gs in glass_slots(o):
            o.material_slots[gs].link = "OBJECT"
            o.material_slots[gs].material = mat
    return o


def tnum(t):
    return t[1] if isinstance(t, tuple) else int(t or 0)


def weight_of(at):
    s = sum(tnum(v) for v in at.values())
    for n, lo, hi in BANDS:
        if lo <= s <= hi:
            return n
    raise ValueError(s)


def halo(core, at, loc=(0, 0, 0), s=IDLE, rot_z=0.0, cell_phase=40.0, cell_s=1.4, far=False, pips=True,
         cells=True, vstretch=1.0):
    weight = weight_of(at)
    sc, b, orb, n = WEIGHT[weight]
    root = bpy.data.objects.new("_root", None)
    SC.collection.objects.link(root)
    root.location = loc
    root.rotation_euler = (0, 0, math.radians(rot_z))
    root.scale = (sc, sc, sc * vstretch)
    top = max(tnum(v) for v in at.values())
    for z in ZONES:
        nm = f"HALO_{core}_Far_Glass_{z}" if far else f"HALO_{core}_Arc_{z}"
        inst(nm, root, mat=glass(at.get(z, 0), s))
    if far:
        o = inst(f"HALO_{core}_Far_Frame_{weight}", root)
        if b:
            for gs in glass_slots(o):
                o.material_slots[gs].link = "OBJECT"
                o.material_slots[gs].material = glass(top, s)
    elif b:
        inst(f"HALO_{core}_Band_{b}", root, mat=glass(top, s))
    if pips and not far:
        for i in range(1, top + 1):
            inst("HALO_TierPip", root, loc=KIT[f"HALO_{core}_PIP_{i}"].matrix_world.translation.copy(),
                 mat=glass(top, s))
    if cells:
        for k in range(n):
            a = math.radians(cell_phase + k * 360.0 / n)
            inst("HALO_PowerCell", root, loc=(orb * math.cos(a), orb * math.sin(a), ORBIT_Z), rot_z=a + math.pi / 2,
                 mat=glass(top, cell_s))
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


def setup(res, transparent=False, bloom=0.0, samples=32, bg=(0.032, 0.034, 0.04), threshold=1.0, holdout=False):
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
    """azim 0 = camera in front of the wearer (-Y), 90 = on the wearer's left (+X), 180 = behind."""
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
    for o in list(bpy.data.objects):
        if o.users_collection and o.name != "_Cam" and not o.name.startswith("L_"):
            bpy.data.objects.remove(o, do_unlink=True)


PRESET = {   # game-legal coverage (sum of arc tiers -> weight class)
    "Light": {"Head": 0, "Torso": 1, "Arms": 0, "Legs": 0},       # arm_phase_runner, 1
    "LightH": {"Head": 2, "Torso": 2, "Arms": 0, "Legs": 0},      # arm_mender_scout, 4
    "Medium": {"Head": 2, "Torso": 2, "Arms": 0, "Legs": 2},      # 6
    "Heavy": {"Head": 3, "Torso": 3, "Arms": 3, "Legs": 0},       # arm_bulwark_assault, 9
}
DAY, DARK = (0.32, 0.36, 0.42), (0.02, 0.022, 0.026)


# ------------------------------------------------------------------------------------------ jobs
def job_blind():
    """'Name the core' test at TRUE game pixel size (vfov 78, 1080p -> 667/d px per metre), eye 1.6 m, halo 1.92 m.
    One row per weight preset, the 4 cores side by side, wearer yaw 0 (front), 90 (side), 180 (back)."""
    for d in (5, 10):
        for yaw in (0, 90, 180):
            clear()
            for r, pre in enumerate(("Light", "LightH", "Medium", "Heavy")):
                for i, core in enumerate(CORES):
                    halo(core, PRESET[pre], loc=((i - 1.5) * 0.9, 0, -r * 0.35), rot_z=yaw, s=IDLE,
                         cell_phase=40.0 + 23 * i)
            ppm = 667.0 / d
            width_m, height_m = 3.8, 1.55
            res = (int(round(width_m * ppm)), int(round(height_m * ppm)))
            elev = -math.degrees(math.atan(0.32 / d))
            lights(center=(0, 0, -0.5))
            cam_dir((0, 0, -0.52), elev, 0, 40.0, ortho=width_m)
            for bgname, bg in (("day", DAY), ("dark", DARK)):
                setup(res, bloom=0.3, threshold=0.8, samples=64, bg=bg)
                render(f"blind_{d}m_yaw{yaw}_{bgname}")
            setup(res, transparent=True, samples=64)
            render(f"blind_{d}m_yaw{yaw}_alpha")


def job_edgeon():
    """Worst angles the builder did not show: exactly edge-on (0 deg), from BEHIND and three-quarter, and +4 deg
    (viewer slightly above, e.g. on stairs). Medium preset H2 T2 L2 for every core, large and in silhouette."""
    for tag, elev, azim in (("back_m2", -2, 180), ("q34_m2", -2, 45), ("front_0", 0, 0), ("front_p4", 4, 0)):
        clear()
        for r, core in enumerate(CORES):
            for c, pre in enumerate(("Light", "Medium", "Heavy")):
                halo(core, PRESET[pre], loc=((c - 1) * 0.85, 0, -r * 0.3), s=IDLE, cell_phase=40)
        # rotate halos instead of the camera so every row is seen at the same azimuth
        for o in bpy.data.objects:
            if o.name.startswith("_root"):
                o.rotation_euler = (0, 0, math.radians(-azim))
        lights(center=(0, 0, -0.45))
        cam_dir((0, 0, -0.45), elev, 0, 12.0, ortho=2.6)
        setup((1800, 1150), bloom=0.35, threshold=0.6, samples=48)
        render(f"edge_{tag}")
        setup((1800, 1150), transparent=True, samples=32)
        render(f"edge_{tag}_alpha")


def job_closeups():
    # 1. pips: T1 and T2 at eye level from the front, Bulwark + Volt, unscaled
    for core in ("Bulwark", "Volt"):
        for t in (1, 2):
            clear()
            halo(core, {"Head": t, "Torso": t, "Arms": 0, "Legs": 0} if t == 1 else
                 {"Head": t, "Torso": t, "Arms": 0, "Legs": 0}, s=LIT, cells=False)
            bpy.data.objects["_root"].scale = (1, 1, 1)
            lights(center=(0, -0.15, 0))
            cam_dir((0, -0.16, 0.012), 3, 0, 1.5, ortho=0.36)
            setup((1000, 360), bloom=0.25, threshold=1.0)
            render(f"close_pips_{core}_T{t}")
    # 2. arc seams from a low three-quarter (where an arc ends next to its neighbour)
    for core, a_deg, rad, z in (("Bulwark", 315, 0.17, 0.0), ("Mender", 315, 0.16, 0.0), ("Volt", 315, 0.165, 0.01),
                                ("Phase", 315, 0.16, 0.0)):
        clear()
        halo(core, {"Head": 3, "Torso": 3, "Arms": 0, "Legs": 3}, s=LIT, cells=False)   # Head lit / Arms off
        bpy.data.objects["_root"].scale = (1, 1, 1)
        a = math.radians(a_deg)
        c = Vector((rad * math.cos(a), rad * math.sin(a), z))
        lights(center=c)
        cam_dir(c, 18, 45, 1.0, ortho=0.13)
        setup((900, 600), bloom=0.25)
        render(f"close_seam_{core}")
    # 3. Phase fork from behind at eye level, Light scale (the edge-on signature)
    clear()
    halo("Phase", PRESET["Light"], s=IDLE, cells=False)
    lights(center=(0, 0.14, 0.01))
    cam_dir((0, 0.14, 0.012), -3, 180, 1.0, ortho=0.36)
    setup((1000, 400), bloom=0.25)
    render("close_phase_fork_back")
    # 4. heavy band clamp under the ring, from below the ring line
    for core in ("Bulwark", "Volt"):
        clear()
        halo(core, PRESET["Heavy"], s=IDLE, cells=False)
        bpy.data.objects["_root"].scale = (1, 1, 1)
        c = Vector((0.0, -0.19, -0.02))
        lights(center=c)
        cam_dir(c, -12, 20, 1.0, ortho=0.26)
        setup((1000, 560), bloom=0.25)
        render(f"close_band_{core}")


def wire_overlay(o, thick=0.00025):
    w = o.copy()
    w.data = o.data.copy()
    SC.collection.objects.link(w)
    w.parent = o.parent
    w.matrix_parent_inverse = Matrix.Identity(4)
    w.location, w.rotation_euler, w.scale = o.location, o.rotation_euler, o.scale
    w.data.materials.clear()
    # the Heavy bands contain zero-area sliver triangles that make the Wireframe modifier explode (verts at ~900 m);
    # dissolve them on this display copy only
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(w.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-5)
    bm.to_mesh(w.data)
    bm.free()
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
    return w


def job_wire():
    for name, tgt, elev, azim, ortho, thick in (
            ("HALO_Bulwark_Arc_Head", (0, -0.16, 0.0), 25, 15, 0.30, 0.0002),
            ("HALO_Mender_Arc_Head", (0, -0.16, 0.0), 30, 15, 0.30, 0.0002),
            ("HALO_Phase_Arc_Torso", (0, 0.15, 0.01), 20, 160, 0.30, 0.0002),
            ("HALO_Volt_Band_Heavy", (0, 0, -0.02), 25, 20, 0.50, 0.00035),
            ("HALO_PowerCell", (-0.012, 0, 0), 25, 30, 0.11, 0.0001),
            ("HALO_Core_Mender", (0, 0, 0.028), 30, 15, 0.11, 0.00012)):
        clear()
        o = inst(name, None, mat=glass(2, 0.6) if glass_slots(KIT[name]) else None)
        wire_overlay(o, thick)
        lights(center=tgt, k=0.6)
        cam_dir(tgt, elev, azim, 2.0, ortho=ortho)
        setup((1000, 650), samples=32, bg=(0.02, 0.02, 0.024))
        render("wire_" + name.replace("HALO_", ""))


def job_states():
    """Arc states at true game pixels (5 m, 10 m) in daylight + dark: lit (idle 0.9), broken, uncovered.
    Bulwark Medium H2 T2 L2, the struck arc = Head (front) in each column."""
    cols = [("idle", {"Head": 2, "Torso": 2, "Arms": 0, "Legs": 2}),
            ("broken", {"Head": ("B", 2), "Torso": 2, "Arms": 0, "Legs": 2}),
            ("uncovered", {"Head": 0, "Torso": 2, "Arms": 2, "Legs": 2})]
    for d in (5, 10):
        clear()
        for r, core in enumerate(("Bulwark", "Volt")):
            for i, (_, at) in enumerate(cols):
                halo(core, at, loc=((i - 1) * 0.9, 0, -r * 0.35), s=IDLE)
        ppm = 667.0 / d
        res = (int(round(2.8 * ppm)), int(round(0.9 * ppm)))
        elev = -math.degrees(math.atan(0.32 / d))
        lights(center=(0, 0, -0.17))
        cam_dir((0, 0, -0.2), elev, 0, 40.0, ortho=2.8)
        for bgname, bg in (("day", DAY), ("dark", DARK)):
            setup(res, bloom=0.3, threshold=0.8, samples=64, bg=bg)
            render(f"states_{d}m_{bgname}")
    # large reference
    clear()
    for r, core in enumerate(("Bulwark", "Volt")):
        for i, (_, at) in enumerate(cols):
            halo(core, at, loc=((i - 1) * 0.9, 0, -r * 0.35), s=IDLE)
    lights(center=(0, 0, -0.17))
    cam_dir((0, 0, -0.2), -6, 0, 12.0, ortho=2.8)
    setup((1800, 640), bloom=0.3, threshold=0.8, samples=48, bg=DAY)
    render("states_large_day")


def import_char(offset=(0.0, 0.0), yaw=0.0):
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
    off = Vector((offset[0] - (mn.x + mx.x) / 2, offset[1] - (mn.y + mx.y) / 2, -mn.z))
    for r in roots:
        r.location += off
    bpy.context.view_layer.update()
    if yaw:
        piv = bpy.data.objects.new("_charpivot", None)
        SC.collection.objects.link(piv)
        piv.location = (offset[0], offset[1], 0)
        bpy.context.view_layer.update()
        for r in roots:
            mw = r.matrix_world.copy()
            r.parent = piv
            r.matrix_world = mw
        piv.rotation_euler = (0, 0, math.radians(yaw))
        bpy.context.view_layer.update()
    top = max((o.matrix_world @ v.co).z for o in meshes for v in o.data.vertices)
    return Vector((offset[0], offset[1], top))


def job_char():
    """Kestrel with three presets: (a) from a ledge 3 m above, 8 m away (looking down ~20 deg);
    (b) third-person over-the-shoulder style 4 m behind/above; (c) close front at 1.8 m, eye level (1.6 m)."""
    cfg = [("Phase", PRESET["Light"]), ("Volt", PRESET["Medium"]), ("Bulwark", PRESET["Heavy"])]
    clear()
    for i, (core, at) in enumerate(cfg):
        t = import_char(((i - 1) * 1.2, 0.0))
        halo(core, at, loc=t + Vector((0, 0, 0.22)), s=IDLE, cell_phase=40 + 30 * i)
    fl = bpy.data.meshes.new("_floor")
    fl.from_pydata([(-20, -20, 0), (20, -20, 0), (20, 20, 0), (-20, 20, 0)], [], [(0, 1, 2, 3)])
    fo = bpy.data.objects.new("_floor", fl)
    SC.collection.objects.link(fo)
    fm = bpy.data.materials.new("_floorm")
    fm.use_nodes = True
    principled(fm).inputs["Base Color"].default_value = (0.18, 0.19, 0.2, 1)
    principled(fm).inputs["Roughness"].default_value = 0.9
    fl.materials.append(fm)
    lights(sun=True, k=1.0)
    # (a) from a ledge: eye at (0, -8, 4.6)
    camera((0.0, -8.0, 4.6), (0.0, 0.0, 1.6), vfov=78)
    setup((1920, 1080), bloom=0.3, threshold=0.8, samples=48, bg=DAY)
    render("char_ledge_8m")
    # (b) behind and above (third-person / spectator), 4 m
    camera((1.2, 4.0, 2.6), (0.0, 0.0, 1.7), vfov=60)
    render("char_behind_4m")
    # (c) eye-level close front, 1.8 m, centre character (Volt Medium)
    camera((0.0, -1.8, 1.6), (0.0, 0.0, 1.65), vfov=78)
    render("char_front_1p8m")
    setup((1920, 1080), bloom=0.3, threshold=0.8, samples=48, bg=DARK)
    lights(sun=True, k=0.15)
    camera((0.0, -1.8, 1.6), (0.0, 0.0, 1.65), vfov=78)
    render("char_front_1p8m_dark")


def job_farlod():
    """Near kit vs far LOD at 20 m (the switch distance) in daylight, true pixels; plus a 2 m reference."""
    clear()
    for r, pre in enumerate(("Light", "Medium", "Heavy")):
        for i, core in enumerate(CORES):
            halo(core, PRESET[pre], loc=((i - 1.5) * 0.9 - 0.0, 0, -r * 0.4), s=IDLE, cell_phase=40)
            halo(core, PRESET[pre], loc=((i - 1.5) * 0.9, 0, -r * 0.4 - 1.4), s=IDLE, far=True, cell_phase=40)
    lights(center=(0, 0, -1.2))
    for d in (20,):
        ppm = 667.0 / d
        res = (int(round(3.9 * ppm)), int(round(2.8 * ppm)))
        elev = -math.degrees(math.atan(0.32 / d))
        cam_dir((0, 0, -1.2), elev, 0, 40.0, ortho=3.9)
        setup(res, bloom=0.3, threshold=0.8, samples=64, bg=DAY)
        render(f"farlod_{d}m_day")
    cam_dir((0, 0, -1.2), -6, 0, 40.0, ortho=3.9)
    setup((1950, 1400), bloom=0.3, threshold=0.8, samples=48, bg=DAY)
    render("farlod_large_day")


{"blind": job_blind, "edgeon": job_edgeon, "closeups": job_closeups, "wire": job_wire, "states": job_states,
 "char": job_char, "farlod": job_farlod}[JOB]()
print("JOB DONE", JOB)
