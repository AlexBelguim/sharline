"""Collision preview: the game's Showhome brushes as coloured boxes / wedges in Blender, plus renders.

Run (headless):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/maps/showhome/layout/collision_preview.py" -- [--no-render] [--views top,aerial_s11,...]

Reads showhome_annotated.json (run annotate_layout.py first). Writes, next to this script:
  showhome_collision_preview.blend   one object per brush, in a collection per structure; clips hidden
  showhome_collision_preview.glb     the same (visible brushes only), glTF Y-up = Bevy frame exactly
  renders/collision_<view>.png       top-down ortho, aerial views matching the concept cameras, ground views

Object naming: COL_<structure>__<tag id>[_<part>]_<brush index>, e.g. COL_SAGE_HOUSE__W_GF_E_lintel_57.
Every object's origin is its brush centre, so in the .glb a node's translation is the brush centre in Bevy
coordinates (x, z, -y) and its mesh spans exactly the brush.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, r"F:/git/val etf/tools")
sys.path.insert(0, r"F:/git/val etf/assets/maps/showhome/layout")
import blender_common as bc  # noqa: E402
import layout_lib as LL  # noqa: E402

HERE = r"F:/git/val etf/assets/maps/showhome/layout"
ANN = os.path.join(HERE, "showhome_annotated.json")
RENDERS = os.path.join(HERE, "renders")
BASE = os.path.join(HERE, "showhome_collision_preview")

LOOK_SRGB = {  # game/crates/val_etf/src/render.rs look_color (sRGB)
    "Ground": (0.42, 0.47, 0.36), "Floor": (0.58, 0.52, 0.44), "Wall": (0.88, 0.83, 0.74),
    "Roof": (0.32, 0.30, 0.33), "Trim": (0.93, 0.91, 0.87), "Prop": (0.60, 0.49, 0.37),
    "Hedge": (0.24, 0.40, 0.22), "Fence": (0.82, 0.80, 0.74), "Glass": (0.60, 0.80, 0.92),
    "Vehicle": (0.80, 0.76, 0.66), "Metal": (0.36, 0.38, 0.42), "Concrete": (0.64, 0.64, 0.62),
    "Water": (0.22, 0.46, 0.56), "TeamA": (0.0, 0.62, 0.56), "TeamB": (0.93, 0.38, 0.32),
    "Accent": (0.95, 0.74, 0.22), "Target": (0.86, 0.86, 0.84), "Invisible": (1.0, 0.0, 1.0),
}


def lin(c):
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def args():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    views = None
    if "--views" in a:
        views = a[a.index("--views") + 1].split(",")
    return dict(render="--no-render" not in a, views=views)


def mesh_obj(name, verts, faces, center, col, mat):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(Vector(v) - center) for v in verts], [], faces)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    ob.location = center
    col.objects.link(ob)
    if mat:
        ob.data.materials.append(mat)
    return ob


def build(ann):
    bc.reset_scene()
    root = bc.collection("Showhome_Collision")
    mats = {}

    def mat(look, kind):
        key = look if kind != "PlayerClip" else "_Clip"
        if key not in mats:
            if kind == "PlayerClip":
                m = bc.material("M_COL_PlayerClip", lin((1.0, 0.0, 1.0)), rough=0.5, alpha=0.18)
            else:
                rough = 0.45 if look in ("Metal", "Vehicle") else 0.8
                m = bc.material("M_COL_" + look, lin(LOOK_SRGB.get(look, (0.5, 0.5, 0.5))), rough=rough)
            mats[key] = m
        return mats[key]

    cols = {}
    clip_col = bc.collection("_Clips", root)
    objs = []
    for b in ann["brushes"]:
        t = b["tag"]
        sid = t["structure"]
        if b["kind"] == "PlayerClip":
            col = clip_col
        else:
            if sid not in cols:
                cols[sid] = bc.collection("S_" + sid, root)
            col = cols[sid]
        part = f"_{t['part']}" if t.get("part") and t["part"] not in ("solid",) else ""
        name = f"COL_{sid}__{t['id']}{part}_{b['i']}"
        mn, mx = Vector(b["min"]), Vector(b["max"])
        center = (mn + mx) / 2
        v, f = LL.brush_polys(b)
        ob = mesh_obj(name, v, f, center, col, mat(b["look"], b["kind"]))
        ob["brush_index"] = b["i"]
        ob["tag_id"] = t["id"]
        ob["part"] = t.get("part") or ""
        ob["kind"] = b["kind"]
        ob["look"] = b["look"]
        objs.append(ob)
    clip_col.hide_render = True
    for o in clip_col.objects:
        o.hide_render = True

    # markers: spawns (arrow cones), zipline (sagging cable), pylon cable anchor spheres
    mcol = bc.collection("_Markers", root)
    for s in ann["spawns"]:
        c = (0.0, 0.62, 0.56) if s["team"] == "A" else (0.93, 0.38, 0.32)
        m = bc.material("M_SPAWN_" + s["team"], lin(c), rough=0.4, emission=lin(c), emission_strength=1.5)
        x, y, z = s["pos"]
        yaw = math.radians(s["yaw_deg"])
        cone = bc.cylinder(f"_SPAWN_{s['id']}", 0.35, 0.9, loc=(x, y, z + 0.05), verts=12, col=mcol, mat=m,
                           radius2=0.0, rot=(0, 90, math.degrees(yaw)))
        cone.location = (x, y, z + 0.4)
    cable = bc.material("M_ZIPLINE", lin((0.05, 0.05, 0.06)), rough=0.4)
    for z in ann["ziplines"]:
        a, bb = Vector(z["design"]["a"]), Vector(z["design"]["b"])
        sag = ann["design_markers"]["zipline_design"]["sag_m"]
        pts = []
        n = 24
        for k in range(n + 1):
            s = k / n
            p = a.lerp(bb, s)
            p.z -= 4 * sag * s * (1 - s)
            pts.append(p)
        cd = bpy.data.curves.new("_ZIPLINE", "CURVE")
        cd.dimensions = "3D"
        cd.bevel_depth = 0.04
        sp = cd.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for k, p in enumerate(pts):
            sp.points[k].co = (p.x, p.y, p.z, 1)
        co = bpy.data.objects.new("_ZIPLINE", cd)
        co.data.materials.append(cable)
        mcol.objects.link(co)
    return objs


def aim_sun(so, elevation_deg, azimuth_deg=235):
    """Sun direction: it shines FROM azimuth (deg, counter-clockwise from east; 235 = south-west)."""
    el, az = math.radians(elevation_deg), math.radians(azimuth_deg)
    d = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def lighting(scene):
    """Warm late-afternoon sun from the south-west (concept: long soft shadows) + a soft sky."""
    world = bpy.data.worlds.new("Sky")
    world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (*lin((0.62, 0.72, 0.85)), 1)
    bg.inputs[1].default_value = 0.9
    scene.world = world
    sd = bpy.data.lights.new("Sun", "SUN")
    sd.energy = 4.0
    sd.color = (1.0, 0.86, 0.7)
    sd.angle = math.radians(2.5)
    so = bpy.data.objects.new("_Sun", sd)
    aim_sun(so, 28)
    scene.collection.objects.link(so)
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        pass


CAMS = {
    # name: (location, target, lens_mm or ortho scale, res, ortho?)
    "top": ((36.0, 24.0, 120.0), (36.0, 24.0, 0.0), 80.0, (1800, 1240), True),
    # concept A_showhome_aerial_s11: high, from the south (street end), looking north up the street
    "aerial_s11": ((36.0, -26.0, 40.0), (36.0, 25.0, 0.0), 30.0, (1600, 900), False),
    # concept A_showhome_aerial_s12: three-quarter from the south-west corner
    "aerial_s12": ((4.0, -16.0, 30.0), (40.0, 28.0, 0.0), 28.0, (1600, 900), False),
    # opposite three-quarter (from the north-east, over the Clay garden)
    "aerial_ne": ((70.0, 66.0, 32.0), (34.0, 22.0, 0.0), 28.0, (1600, 900), False),
    # concept A_showhome_ground_*: eye height in the street south of the Mover, looking north
    "ground_street": ((36.0, 11.5, 1.6), (36.0, 30.0, 2.6), 16.0, (1600, 900), False),
    # eye height on the Sage lawn looking across the street at Clay House
    "ground_lawn": ((22.6, 26.0, 1.6), (56.0, 26.0, 3.0), 18.0, (1600, 900), False),
}


def render(views):
    scene = bpy.context.scene
    lighting(scene)
    try:
        bc._set_engine(scene)
        scene.eevee.taa_render_samples = 32
    except Exception:
        pass
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    cd = bpy.data.cameras.new("_Cam")
    cam = bpy.data.objects.new("_Cam", cd)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cd.clip_start, cd.clip_end = 0.05, 1000
    os.makedirs(RENDERS, exist_ok=True)
    out = []
    for v in views:
        loc, tgt, lens, res, ortho = CAMS[v]
        # top-down: high sun so shadows do not hide the plan; everything else: late-afternoon sun
        aim_sun(bpy.data.objects["_Sun"], 68 if v == "top" else 28)
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        if ortho:
            cd.type = "ORTHO"
            cd.ortho_scale = lens
        else:
            cd.type = "PERSP"
            cd.lens = lens
        scene.render.resolution_x, scene.render.resolution_y = res
        p = os.path.join(RENDERS, f"collision_{v}.png")
        scene.render.filepath = p
        try:
            bpy.ops.render.render(write_still=True)
        except RuntimeError as e:
            print("render failed, retrying on CPU Cycles:", e)
            bc._set_engine(scene, ("CYCLES",))
            scene.cycles.device = "CPU"
            scene.cycles.samples = 24
            scene.cycles.use_denoising = True
            bpy.ops.render.render(write_still=True)
        out.append(p)
        print("rendered", p)
    return out


def export(objs):
    scene = bpy.context.scene
    bpy.ops.object.select_all(action="DESELECT")
    vis = [o for o in objs if o["kind"] != "PlayerClip"]
    for o in vis:
        o.select_set(True)
    bpy.context.view_layer.objects.active = vis[0]
    bpy.ops.export_scene.gltf(filepath=BASE + ".glb", export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_extras=True)
    print("exported", BASE + ".glb")
    bpy.context.preferences.filepaths.save_version = 0  # no .blend1 backups
    bpy.ops.wm.save_as_mainfile(filepath=BASE + ".blend", compress=True)
    print("saved", BASE + ".blend")


def main():
    a = args()
    ann = json.load(open(ANN, encoding="utf-8"))
    objs = build(ann)
    print(f"built {len(objs)} brush objects")
    if a["render"]:
        render(a["views"] or list(CAMS))
    export(objs)


main()
