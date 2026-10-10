"""Reviewer renders for the ATT optics (read-only on the asset; writes PNGs into review/renders/).

  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P review_render.py -- <pass>

passes: extra   - worst angles from the EXPORTED .glb (low/under/rear-right/hip-POV) per optic
        gloss   - glossy clay override (exposes shading / n-gon / bevel artefacts) per optic
        wire    - wireframe overlay on the source optics.blend meshes (pre-triangulation)
        sil     - 64 px black silhouettes (right / three_quarter / front) per optic
        ads     - first-person ADS + hip views on the real MAKO / WARDEN exports at the game FOV (78 deg vertical)
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
REV = os.path.join(OUT, "review")
RD = os.path.join(REV, "renders")
OPTICS = ["optic_reddot", "optic_holo", "optic_3x", "optic_sniper", "optic_thermal"]
CAT = {e["id"]: e for e in json.load(open(os.path.join(OUT, "catalog.json")))["optics"]}
ZOOM = {"optic_reddot": 1.15, "optic_holo": 1.25, "optic_3x": 3.0, "optic_sniper": 6.0, "optic_thermal": 4.0}
GUNS = {"MAKO": (r"F:/git/val etf/assets/weapons/ar7_mako/mako_default.glb",
                 r"F:/git/val etf/assets/weapons/ar7_mako/sockets.json", "MAKO_SOCKET_Optic"),
        "WARDEN": (r"F:/git/val etf/assets/weapons/vk50_warden/warden_default.glb",
                   r"F:/git/val etf/assets/weapons/vk50_warden/sockets.json", "WARDEN_SOCKET_Optic")}


def wipe():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def shot(name, d, objs, res=800, lens=85, samples=40, focus=None, margin=1.12):
    p = bc.render_views(RD, "_tmp", objs, views=[tuple(d)], res=(res, res), engine="CYCLES", samples=samples,
                        lens=lens, focus=focus, margin=margin)[0]
    dst = os.path.join(RD, name + ".png")
    os.replace(p, dst)
    return dst


def p_extra():
    for oid in OPTICS:
        wipe()
        bc.setup_studio()
        objs = [o for o in import_glb(os.path.join(OUT, "ATT_%s.glb" % oid)) if o.type == "MESH"]
        for nm, d in (("low_front_right", (-0.7, -1.0, -0.45)), ("under", (0.25, -0.35, -1.0)),
                      ("rear_right_high", (-0.65, 1.0, 0.6)), ("hip_pov", (0.3, 1.0, 0.42)),
                      ("rear_left_low", (0.8, 0.9, -0.2))):
            shot("%s_%s" % (oid, nm), d, objs)


def clay():
    m = bpy.data.materials.new("_GlossClay")
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bc._set_input(p, "Base Color", (0.35, 0.36, 0.38, 1))
    bc._set_input(p, "Roughness", 0.16)
    bc._set_input(p, "Metallic", 0.6)
    return m


def p_gloss():
    for oid in OPTICS:
        wipe()
        bc.setup_studio()
        objs = [o for o in import_glb(os.path.join(OUT, "ATT_%s.glb" % oid)) if o.type == "MESH"]
        cm = clay()
        for o in objs:
            if o.name.endswith("_Body"):
                for s in o.material_slots:
                    s.material = cm
        for nm, d in (("three_quarter", (0.75, -1, 0.35)), ("rear_right_high", (-0.65, 1.0, 0.6)),
                      ("left", (-1, 0, 0.05))):
            shot("%s_gloss_%s" % (oid, nm), d, objs)


def p_wire():
    bpy.ops.wm.open_mainfile(filepath=os.path.join(OUT, "optics.blend"))
    sc = bpy.context.scene
    wm = bpy.data.materials.new("_Wire")
    wm.use_nodes = True
    p = next(n for n in wm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bc._set_input(p, "Base Color", (0.0, 0.0, 0.0, 1))
    bc._set_input(p, ["Emission Color", "Emission"], (1.0, 0.55, 0.1, 1))
    bc._set_input(p, "Emission Strength", 2.0)
    for o in sc.objects:
        o.hide_render = True
    for l in sc.objects:
        if l.type == "LIGHT":
            l.hide_render = False
    for oid in OPTICS:
        meshes = [o for o in sc.objects if o.type == "MESH" and o.name.startswith("ATT_%s_" % oid)]
        wires = []
        for o in meshes:
            o.hide_render = False
            w = o.copy()
            w.data = o.data.copy()
            w.name = "_wire_" + o.name
            sc.collection.objects.link(w)
            md = w.modifiers.new("w", "WIREFRAME")
            md.thickness = 0.00010
            md.use_replace = True
            md.use_even_offset = False
            w.data.materials.clear()
            w.data.materials.append(wm)
            w.hide_render = False
            wires.append(w)
        for nm, d in (("three_quarter", (0.75, -1, 0.35)), ("left", (-1, 0, 0.05)), ("rear_right_high", (-0.65, 1.0, 0.6))):
            shot("%s_wire_%s" % (oid, nm), d, meshes, res=1000, samples=24)
        for o in meshes + wires:
            o.hide_render = True


def p_sil():
    for oid in OPTICS:
        wipe()
        sc = bpy.context.scene
        objs = [o for o in import_glb(os.path.join(OUT, "ATT_%s.glb" % oid)) if o.type == "MESH"]
        blk = bpy.data.materials.new("_Black")
        blk.use_nodes = True
        p = next(n for n in blk.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bc._set_input(p, "Base Color", (0, 0, 0, 1))
        bc._set_input(p, "Roughness", 1.0)
        for o in objs:
            for s in o.material_slots:
                s.material = blk
        w = bpy.data.worlds.new("W")
        w.use_nodes = True
        bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
        bg.inputs[0].default_value = (1, 1, 1, 1)
        bg.inputs[1].default_value = 1.0
        sc.world = w
        sc.view_settings.view_transform = "Standard"
        for nm, d in (("right", (1, 0, 0.05)), ("three_quarter", (0.75, -1, 0.35)), ("front", (0, -1, 0.08)),
                      ("hip_pov", (0.3, 1.0, 0.42))):
            shot("%s_sil64_%s" % (oid, nm), d, objs, res=64, samples=8, margin=1.05)


def look_cam(name, loc, target_dir, vfov_deg, res=(1280, 720)):
    cd = bpy.data.cameras.new(name)
    cd.sensor_fit = "VERTICAL"
    cd.angle_y = math.radians(vfov_deg)
    cd.clip_start = 0.005
    cd.clip_end = 500
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = Vector(target_dir).to_track_quat("-Z", "Y").to_euler()
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    return cam


def range_scene(origin_z):
    """Sky-ish world like the game fog colour, a ground plane, and a man-sized target 25 m down range
    (head sphere r 0.11 at the sight line) plus a 10 m one, so the reticle size and the window can be judged."""
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Sky")
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (0.40, 0.52, 0.70, 1)
    bg.inputs[1].default_value = 1.0
    sc.world = w
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.0
    so = bpy.data.objects.new("Sun", sun)
    so.rotation_euler = (math.radians(50), 0, math.radians(30))
    sc.collection.objects.link(so)
    bpy.ops.mesh.primitive_plane_add(size=400, location=(0, -150, origin_z - 1.5))
    gr = bpy.context.active_object
    gr.data.materials.append(bc.material("_Ground", (0.18, 0.17, 0.15), rough=0.9))
    tm = bc.material("_Target", (0.55, 0.12, 0.08), rough=0.6)
    for dist, x in ((25.0, 0.0), (10.0, 1.2)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, -dist, origin_z - 0.45))
        b = bpy.context.active_object
        b.scale = (0.45, 0.25, 1.1)
        b.data.materials.append(tm)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.11, location=(x, -dist, origin_z + 0.0))
        h = bpy.context.active_object
        h.data.materials.append(tm)


def p_ads():
    for g, (glb, sj, sock) in GUNS.items():
        s = Vector(json.load(open(sj))[sock]["location"])
        for oid in OPTICS:
            if g not in CAT[oid]["compatible_weapons"]:
                continue
            wipe()
            sc = bpy.context.scene
            bc.setup_cycles_gpu(sc, 48)
            sc.view_settings.view_transform = "AgX"
            gnew = import_glb(glb)
            # hide whatever optic the default gun ships with (keep only the gun meshes)
            for o in gnew:
                if o.type == "MESH" and o.name.startswith("ATT_"):
                    o.hide_render = True
            onew = import_glb(os.path.join(OUT, "ATT_%s.glb" % oid))
            root = bpy.data.objects.get("ATT_" + oid)
            root.location = s
            bpy.context.view_layer.update()
            ads = bpy.data.objects.get("ATT_%s_SOCKET_ADS" % oid).matrix_world.translation.copy()
            er = CAT[oid]["eye_relief_m"]
            range_scene(ads.z)
            eye = ads + Vector((0, er, 0))
            vf = 78.0 / ZOOM[oid]
            look_cam("_ADS", eye, (0, -1, 0), vf)
            sc.render.filepath = os.path.join(RD, "%s_on%s_ADS_fov%.0f.png" % (oid, g.lower(), vf))
            bpy.ops.render.render(write_still=True)
            # hip-fire point of view (gun to the lower right of the eye, like the game's viewmodel offset)
            hip = Vector((0.13, 0.42, 0.20)) + Vector((0, 0, 0))
            look_cam("_HIP", hip, Vector((0.0, -1.0, -0.12)) - Vector((0.05, 0, 0)), 78.0)
            sc.render.filepath = os.path.join(RD, "%s_on%s_HIP_fov78.png" % (oid, g.lower()))
            bpy.ops.render.render(write_still=True)
            print("ADS", oid, g, "eye", tuple(round(v, 4) for v in eye))


PASSES = {"extra": p_extra, "gloss": p_gloss, "wire": p_wire, "sil": p_sil, "ads": p_ads}

if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["extra"]
    os.makedirs(RD, exist_ok=True)
    for a in argv:
        PASSES[a]()
