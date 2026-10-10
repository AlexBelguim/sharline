"""True cross-sections of every clamp on the real gun rails (headless Blender 5.2).

  blender -b --factory-startup -P render_railfit.py -- [<glb_dir> [<out_dir>]]   (defaults: this folder, renders/railfit)

Imports the gun .glb and the part .glb (from <glb_dir>), puts the part on the gun's socket node, boolean-cuts copies of
the part and the rail at a plane through a rail TOOTH next to the socket, and renders the cut faces head-on with an
orthographic camera: rail = orange, part = blue, background (= clearance) dark. Writes <out_dir>/<pid>_<gun>.png.
"""
import math, os, sys
from pathlib import Path
import bpy, bmesh
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HERE = Path(__file__).resolve().parent
SRC = argv[0] if argv else str(HERE)
OUT = argv[1] if len(argv) > 1 else os.path.join(SRC, "renders", "railfit")
os.makedirs(OUT, exist_ok=True)
WEAP = str(HERE.parents[1])
GUNS = {"MAKO": os.path.join(WEAP, "ar7_mako", "mako_default.glb"),
        "WARDEN": os.path.join(WEAP, "vk50_warden", "warden_default.glb")}
JOBS = [("bipod", "WARDEN", "Under", "WARDEN_RailBottom"), ("grip_vertical", "MAKO", "Under", "MAKO_RailBottom"),
        ("ugl_launcher", "MAKO", "Under", "MAKO_RailBottom"), ("laser_R", "MAKO", "Side_R", "MAKO_RailSide_R"),
        ("laser_R", "WARDEN", "Side_R", "WARDEN_RailSide_R"), ("flashlight_L", "WARDEN", "Side_L", "WARDEN_RailSide_L"),
        ("shield_front", "MAKO", "Shield", "MAKO_Rail")]
# mount axis: direction from the rail face toward the part
AXIS = {"Under": Vector((0, 0, -1)), "Side_R": Vector((-1, 0, 0)), "Side_L": Vector((1, 0, 0)),
        "Shield": Vector((0, 0, 1))}


def imp(p):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=p)
    return [o for o in bpy.data.objects if o not in before]


def flat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*rgb, 1)
    e.inputs["Strength"].default_value = 1.0
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def baked_copy(o, mat):
    me = o.data.copy()
    me.transform(o.matrix_world)
    c = bpy.data.objects.new(o.name + "_sec", me)
    bpy.context.scene.collection.objects.link(c)
    me.materials.clear()
    me.materials.append(mat)
    for p in me.polygons:
        p.material_index = 0
    return c


def section(objs, plane_y, mat):
    """Join world-space copies, keep y >= plane_y (EXACT boolean with a big box)."""
    cs = [baked_copy(o, mat) for o in objs]
    bpy.ops.object.select_all(action="DESELECT")
    for c in cs:
        c.select_set(True)
    bpy.context.view_layer.objects.active = cs[0]
    if len(cs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, plane_y - 5.0, 0))
    box = bpy.context.active_object
    box.scale = (10, 10, 10)
    m = ob.modifiers.new("cut", "BOOLEAN")
    m.object = box
    m.operation = "DIFFERENCE"
    m.solver = "EXACT"
    m.use_self = True              # the part is several touching / overlapping closed pieces joined together
    m.use_hole_tolerant = True
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(box, do_unlink=True)
    for p in ob.data.polygons:
        p.material_index = 0
    return ob


for pid, gun, slot, rail_name in JOBS:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    go = imp(GUNS[gun])
    bpy.context.view_layer.update()
    sock = next(o for o in go if o.name == f"{gun}_SOCKET_{slot}").matrix_world.translation.copy()
    po = imp(os.path.join(SRC, f"ATT_{pid}.glb"))
    root = next(o for o in po if o.name == f"ATT_{pid}")
    root.location = sock
    bpy.context.view_layer.update()
    rail = next(o for o in go if o.name == rail_name)
    ax = AXIS[slot]
    # a rail tooth near the socket: rail face polygons on the mount plane, facing the part
    best = None
    for p in rail.data.polygons:
        c = rail.matrix_world @ p.center
        n = (rail.matrix_world.to_3x3() @ p.normal).normalized()
        if n.dot(ax) > 0.99 and abs((c - sock).dot(ax)) < 1e-4 and abs(c.y - sock.y) < 0.012:
            if best is None or abs(c.y - sock.y) < abs(best - sock.y):
                best = c.y
    plane_y = (best if best is not None else sock.y) + 0.0
    gm = flat("_rail", (0.85, 0.45, 0.12))
    pmat = flat("_part", (0.25, 0.55, 0.95))
    other = flat("_gun", (0.30, 0.22, 0.16))
    near = [o for o in go if o.type == "MESH" and o is not rail]
    rs = section([rail], plane_y, gm)
    ps = section([o for o in po if o.type == "MESH"], plane_y, pmat)
    for o in list(sc.objects):
        if o not in (rs, ps):
            o.hide_render = True
    # camera: ortho, looking +Y from the muzzle side, clip plane just in front of the cut
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 0.050
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    centre = sock + ax * 0.004
    cam.location = (centre.x, plane_y - 0.3, centre.z)
    cam.rotation_euler = (math.radians(90), 0, 0)
    cam_d.clip_start = 0.3 - 0.0004
    cam_d.clip_end = 2.0
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    next(n for n in w.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (0.02, 0.02, 0.025, 1)
    sc.world = w
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 16
    sc.cycles.use_denoising = False
    sc.render.resolution_x = sc.render.resolution_y = 1000
    sc.view_settings.view_transform = "Standard"
    p = os.path.join(OUT, f"{pid}_{gun}.png")
    sc.render.filepath = p
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError:
        sc.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    print("SECTION", p, "plane_y", round(plane_y, 5), "socket", tuple(round(c, 5) for c in sock))
