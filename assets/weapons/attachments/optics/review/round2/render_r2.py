"""Round-2 reviewer renders (read-only on the asset; writes review/round2/renders/).

"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P render_r2.py -- <mode>
modes: angles | wire | sil | hip | ads | far | close
Everything is rendered from the EXPORTED .glb files (fresh import), in EEVEE so glTF backface culling
(doubleSided false on the reticle / glint decals) behaves like the engine.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

OUT = r"F:/git/val etf/assets/weapons/attachments/optics"
R2 = os.path.join(OUT, "review", "round2")
REN = os.path.join(R2, "renders")
OPTICS = ["optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"]
CAT = {e["id"]: e for e in json.load(open(os.path.join(OUT, "catalog.json")))["optics"]}
GUNS = {"MAKO": (r"F:/git/val etf/assets/weapons/ar7_mako/mako_default.glb", "MAKO_SOCKET_Optic"),
        "WARDEN": (r"F:/git/val etf/assets/weapons/vk50_warden/warden_default.glb", "WARDEN_SOCKET_Optic")}
DEFAULT_ON = {"optic_reddot": "MAKO", "optic_holo": "MAKO", "optic_3x": "MAKO", "optic_sniper": "WARDEN",
              "optic_thermal": "WARDEN"}
ZOOM = {"optic_reddot": 1.15, "optic_holo": 1.25, "optic_3x": 3.0, "optic_sniper": 6.0, "optic_thermal": 4.0}
MODE = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "angles"
os.makedirs(REN, exist_ok=True)


def wipe():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def eevee(scene, samples=32):
    for e in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            scene.render.engine = e
            break
        except TypeError:
            continue
    try:
        scene.eevee.taa_render_samples = samples
    except Exception:
        pass
    scene.render.image_settings.file_format = "PNG"


def cam(scene, loc, target=None, vfov=None, lens=None, direction=None):
    cd = bpy.data.cameras.get("_RCam") or bpy.data.cameras.new("_RCam")
    co = bpy.data.objects.get("_RCam") or bpy.data.objects.new("_RCam", cd)
    if co.name not in scene.collection.objects:
        scene.collection.objects.link(co)
    cd.clip_start = 0.005
    cd.clip_end = 2000
    if vfov:
        cd.sensor_fit = "VERTICAL"
        cd.angle_y = math.radians(vfov)
    if lens:
        cd.sensor_fit = "AUTO"
        cd.lens = lens
    co.location = Vector(loc)
    d = (Vector(target) - co.location) if target is not None else Vector(direction)
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    scene.camera = co
    return co


def render(scene, path, res=(900, 900)):
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def range_scene(scene):
    """Outdoor-ish range: sky world, sun, grey ground, red target posts at 10 / 25 / 50 m (for ADS + hip)."""
    w = bpy.data.worlds.new("_Sky")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.42, 0.55, 0.75, 1)
    bg.inputs[1].default_value = 1.0
    scene.world = w
    sd = bpy.data.lights.new("_Sun", "SUN")
    sd.energy = 3.0
    so = bpy.data.objects.new("_Sun", sd)
    so.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.collection.objects.link(so)
    bpy.ops.mesh.primitive_plane_add(size=600, location=(0, -250, 0))
    g = bpy.context.active_object
    gm = bpy.data.materials.new("_Ground")
    gm.diffuse_color = (0.3, 0.3, 0.3, 1)
    g.data.materials.append(gm)
    red = bpy.data.materials.new("_Red")
    red.use_nodes = True
    next(n for n in red.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs[0].default_value = (0.6, 0.05, 0.03, 1)
    for dist, x in ((10, -0.8), (25, 0.0), (50, 1.5)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -dist, 0.9))
        t = bpy.context.active_object
        t.scale = (0.45, 0.3, 1.8)
        t.data.materials.append(red)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.13, location=(x, -dist, 1.95))
        bpy.context.active_object.data.materials.append(red)
    try:
        scene.view_settings.view_transform = "Standard"
    except Exception:
        pass


def place_optic_on_gun(oid, gun):
    glb, sock = GUNS[gun]
    gobjs = imp(glb)
    s = bpy.data.objects[sock].matrix_world.translation.copy()
    oobjs = imp(os.path.join(OUT, "ATT_%s.glb" % oid))
    root = bpy.data.objects["ATT_" + oid]
    root.location = s
    bpy.context.view_layer.update()
    return gobjs, oobjs, s


def meshes(objs):
    return [o for o in objs if o.type == "MESH"]


# ------------------------------------------------------------------------------------------------ modes
def mode_angles():
    """Angles the builder did not show: shooter's-right front 3/4 (-X), the hip-fire view (+X rear high),
    underside, straight-down rear, worm's eye front."""
    views = {"frontR_-X": (-0.85, -0.8, 0.3), "hipview_+Xrear_high": (0.55, 1.0, 0.75),
             "under_front": (0.45, -0.8, -0.65), "rear_high": (0.0, 1.0, 1.1), "worm_front_left": (0.9, -0.6, -0.15)}
    for oid in OPTICS:
        wipe()
        sc = bpy.context.scene
        bc.setup_studio(sc)
        objs = imp(os.path.join(OUT, "ATT_%s.glb" % oid))
        ms = meshes(objs)
        bc.render_views(REN, "r2_%s" % oid, objs=ms, views=list(views.values()), res=(800, 800), engine="EEVEE",
                        samples=48, lens=85)


def mode_wire():
    """Clay + wire overlay (3/4 front and -X rear) to read the topology / bevel density."""
    for oid in OPTICS:
        wipe()
        sc = bpy.context.scene
        bc.setup_studio(sc)
        objs = imp(os.path.join(OUT, "ATT_%s.glb" % oid))
        ms = meshes(objs)
        clay = bpy.data.materials.new("_Clay")
        clay.use_nodes = True
        p = next(n for n in clay.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        p.inputs[0].default_value = (0.55, 0.55, 0.55, 1)
        p.inputs["Roughness"].default_value = 0.6
        wm = bpy.data.materials.new("_Wire")
        wm.use_nodes = True
        pw = next(n for n in wm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        pw.inputs[0].default_value = (0.0, 0.0, 0.0, 1)
        for o in ms:
            for s in o.material_slots:
                s.material = clay
            w = o.copy()
            w.data = o.data.copy()
            bpy.context.scene.collection.objects.link(w)
            w.data.materials.clear()
            w.data.materials.append(wm)
            mod = w.modifiers.new("w", "WIREFRAME")
            mod.thickness = 0.00012
            mod.use_replace = True
            mod.use_even_offset = False
        bc.render_views(REN, "r2_wire_%s" % oid, objs=ms, views=[(0.75, -1, 0.35), (-0.8, 0.9, 0.5)],
                        res=(1000, 1000), engine="EEVEE", samples=16, lens=85)


def mode_sil():
    """64 px black silhouettes: optic alone (right / front / 3/4) and the default gun+optic (right)."""
    def sil_setup(sc):
        w = bpy.data.worlds.new("_W")
        w.use_nodes = True
        next(n for n in w.node_tree.nodes if n.type == "BACKGROUND").inputs[0].default_value = (1, 1, 1, 1)
        sc.world = w
        blk = bpy.data.materials.new("_Blk")
        blk.use_nodes = True
        nt = blk.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        outn = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs[0].default_value = (0, 0, 0, 1)
        nt.links.new(em.outputs[0], outn.inputs[0])
        try:
            sc.view_settings.view_transform = "Standard"
        except Exception:
            pass
        return blk
    for oid in OPTICS:
        wipe()
        sc = bpy.context.scene
        blk = sil_setup(sc)
        objs = imp(os.path.join(OUT, "ATT_%s.glb" % oid))
        ms = meshes(objs)
        for o in ms:
            for s in o.material_slots:
                s.material = blk
        bc.render_views(REN, "r2_sil64_%s" % oid, objs=ms, views=["right", "front", "three_quarter"], res=(64, 64),
                        engine="EEVEE", samples=8, lens=85, margin=1.05)
        wipe()
        sc = bpy.context.scene
        blk = sil_setup(sc)
        gobjs, oobjs, s = place_optic_on_gun(oid, DEFAULT_ON[oid])
        allm = meshes(gobjs + oobjs)
        for o in allm:
            for sl in o.material_slots:
                sl.material = blk
        bc.render_views(REN, "r2_sil128_ongun_%s" % oid, objs=allm, views=["right"], res=(128, 128),
                        engine="EEVEE", samples=8, lens=85, margin=1.02)


def mode_hip():
    """First-person hip view at the game vFOV 78: camera left of / above / behind the grip (typical viewmodel)."""
    for oid in ("optic_holo", "optic_reddot", "optic_3x", "optic_sniper", "optic_thermal"):
        wipe()
        sc = bpy.context.scene
        eevee(sc, 32)
        range_scene(sc)
        gun = DEFAULT_ON[oid]
        place_optic_on_gun(oid, gun)
        eye = Vector((0.11, 0.42, 0.20)) if gun == "MAKO" else Vector((0.12, 0.50, 0.26))
        cam(sc, eye, direction=(-0.06, -1.0, -0.04), vfov=78)
        render(sc, os.path.join(REN, "r2_hip_%s_on%s.png" % (oid, gun.lower())), res=(1280, 720))


def mode_ads():
    """ADS at the game FOV (78 / zoom), 1920x1080, engine-like culling; plus a 1-sample (no AA) version of the
    1x sights to judge reticle aliasing."""
    for oid in OPTICS:
        for gun in CAT[oid]["compatible_weapons"]:
            if gun != DEFAULT_ON[oid] and oid not in ("optic_holo",):
                continue
            wipe()
            sc = bpy.context.scene
            eevee(sc, 32)
            range_scene(sc)
            place_optic_on_gun(oid, gun)
            ads = bpy.data.objects["ATT_%s_SOCKET_ADS" % oid].matrix_world.translation.copy()
            eye = ads + Vector((0, CAT[oid]["eye_relief_m"], 0))
            cam(sc, eye, direction=(0, -1, 0), vfov=78.0 / ZOOM[oid])
            bpy.data.cameras["_RCam"].clip_start = 0.03       # the game's near plane
            render(sc, os.path.join(REN, "r2_ads_%s_on%s_1080p.png" % (oid, gun.lower())), res=(1920, 1080))
            if CAT[oid]["magnification"] == "1.0":
                sc.eevee.taa_render_samples = 1
                render(sc, os.path.join(REN, "r2_ads_%s_on%s_1080p_noAA.png" % (oid, gun.lower())),
                       res=(1920, 1080))


def mode_far():
    """Third-person read: the default gun + optic seen at 6 m and 15 m with the game vFOV 78 at 1080p (crops)."""
    for oid in ("optic_holo", "optic_sniper", "optic_reddot", "optic_3x", "optic_thermal"):
        for dist in (6.0, 15.0):
            wipe()
            sc = bpy.context.scene
            eevee(sc, 32)
            range_scene(sc)
            gobjs, oobjs, s = place_optic_on_gun(oid, DEFAULT_ON[oid])
            # gun at chest height pointing at the camera, slightly turned (enemy aiming toward you)
            root = [o for o in gobjs if o.parent is None][0]
            for o in [o for o in gobjs + oobjs if o.parent is None]:
                o.location += Vector((0, 0, 1.35))
            bpy.context.view_layer.update()
            tgt = Vector((0, -0.1, 1.45))
            cam(sc, tgt + Vector((math.sin(math.radians(25)) * dist, -math.cos(math.radians(25)) * dist, 0.25)),
                target=tgt, vfov=78)
            render(sc, os.path.join(REN, "r2_far_%s_%dm_full.png" % (oid, dist)), res=(1920, 1080))


def mode_close():
    """Close-ups of joints the builder did not show."""
    shots = {
        "optic_holo": [("deck_tray_top", (0.0, -0.040, 0.030), 0.03, (0.3, -0.5, 1.0)),
                       ("rear_door_low", (0.0, 0.033, 0.015), 0.035, (0.5, 1.0, -0.1)),
                       ("mount_bar_-X", (-0.026, -0.010, 0.004), 0.03, (-1.0, -0.3, -0.2)),
                       ("hood_top_rear", (0.0, 0.020, 0.068), 0.03, (0.6, 0.8, 0.6))],
        "optic_sniper": [("ring_clamp_front", (0.0, -0.060, 0.012), 0.03, (0.9, -0.5, 0.2)),
                         ("ring_clamp_under", (0.0, 0.060, 0.000), 0.03, (0.6, 0.5, -0.6)),
                         ("eyepiece_rear", (0.0, 0.140, 0.040), 0.035, (0.5, 1.0, 0.3)),
                         ("bell_ring_side", (0.0, -0.180, 0.040), 0.045, (1.0, 0.0, 0.1))],
        "optic_reddot": [("emitter_deck", (0.0, 0.010, 0.035), 0.022, (0.6, 1.0, 0.7)),
                         ("riser_under", (0.0, -0.005, 0.005), 0.03, (0.7, -0.6, -0.5))],
        "optic_3x": [("qd_lever_-X", (-0.025, 0.000, 0.010), 0.03, (-1.0, 0.3, 0.2)),
                     ("eyepiece", (0.0, 0.045, 0.050), 0.035, (0.6, 1.0, 0.4))],
        "optic_thermal": [("battery_+X", (0.030, 0.000, 0.040), 0.045, (1.0, -0.4, 0.3)),
                          ("eyecup_display", (0.0, 0.085, 0.052), 0.035, (0.3, 1.0, 0.2)),
                          ("heatsink_-X", (-0.028, 0.0, 0.050), 0.05, (-1.0, 0.2, 0.3))],
    }
    for oid, lst in shots.items():
        wipe()
        sc = bpy.context.scene
        bc.setup_studio(sc)
        objs = imp(os.path.join(OUT, "ATT_%s.glb" % oid))
        ms = meshes(objs)
        for name, c, r, d in lst:
            p = bc.render_views(REN, "r2_close_%s_%s" % (oid, name), objs=ms, views=[d], res=(800, 800),
                                engine="EEVEE", samples=48, lens=85, focus=(c, r))


{"angles": mode_angles, "wire": mode_wire, "sil": mode_sil, "hip": mode_hip, "ads": mode_ads, "far": mode_far,
 "close": mode_close}[MODE]()
