"""Look-dev check for the Showhome texture library: a small street vignette (NOT the map; the map kit is built
elsewhere) with every texture applied at its README UV scale under a warm late-afternoon sun, rendered from an
aerial three-quarter view and a street-level view like the concept art.

Run:  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup -P preview_render.py
Writes _src/preview/lookdev_aerial.png and _src/preview/lookdev_street.png.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.dirname(HERE)
PREV = os.path.join(HERE, "preview")
TRIMS = json.load(open(os.path.join(TEX, "trims.json")))
STRIP = {s["name"]: s for s in TRIMS["strips"]}


# ------------------------------------------------------------------------------------------------ materials
def _img(name, colour=True):
    img = bpy.data.images.load(os.path.join(TEX, name), check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return img


def mat(name, tex, rough=0.7, metal=0.0, normal=None, nstrength=1.0, orm=None, alpha=False, tint=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = _img(tex)
    col_out = t.outputs["Color"]
    if tint is not None:
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 1.0
        mix.inputs["Color2"].default_value = (*tint, 1.0)
        nt.links.new(col_out, mix.inputs["Color1"])
        col_out = mix.outputs["Color"]
    nt.links.new(col_out, bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if normal:
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = _img(normal, colour=False)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = nstrength
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if orm:
        to = nt.nodes.new("ShaderNodeTexImage")
        to.image = _img(orm, colour=False)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(to.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs[1], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs[2], bsdf.inputs["Metallic"])
    if alpha:
        nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
        try:
            m.surface_render_method = "BLENDED"
        except Exception:
            pass
        bsdf.inputs["Transmission Weight"].default_value = 0.0
    return m


# ------------------------------------------------------------------------------------------------ geometry
def box_uv(obj, repeat_m, offset=(0.0, 0.0)):
    """World-space box projection UVs: 1 UV unit = repeat_m metres; on walls V follows +Z (image up = world up)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uv = bm.loops.layers.uv.verify()
    mw = obj.matrix_world
    for f in bm.faces:
        n = (mw.to_3x3() @ f.normal).normalized()
        ax = max(range(3), key=lambda i: abs(n[i]))
        if repeat_m is None:  # per-face 0-1 UVs (non-tiling face textures, e.g. cardboard_box_face)
            pts = []
            for lp in f.loops:
                co = mw @ lp.vert.co
                pts.append((co.x, co.y) if ax == 2 else ((co.x, co.z) if ax == 1 else (co.y, co.z)))
            u0, u1 = min(p[0] for p in pts), max(p[0] for p in pts)
            v0, v1 = min(p[1] for p in pts), max(p[1] for p in pts)
            for lp, (pu, pv) in zip(f.loops, pts):
                lp[uv].uv = ((pu - u0) / max(u1 - u0, 1e-6), (pv - v0) / max(v1 - v0, 1e-6))
            continue
        for lp in f.loops:
            co = mw @ lp.vert.co
            if ax == 2:
                u, v = co.x, co.y
            elif ax == 1:
                u, v = (co.x if n.y < 0 else -co.x), co.z
            else:
                u, v = (-co.y if n.x < 0 else co.y), co.z
            lp[uv].uv = (u / repeat_m + offset[0], v / repeat_m + offset[1])
    bm.to_mesh(me)
    bm.free()


def add_box(name, x0, y0, z0, x1, y1, z1, material, repeat_m, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object
    o.name = name
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        mod = o.modifiers.new("bev", "BEVEL")
        mod.width = bevel
        mod.segments = 6
        mod.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=mod.name)
    box_uv(o, repeat_m)
    o.data.materials.append(material)
    return o


def trim_bar(name, p0, p1, w, d, strip, material, up=(0, 0, 1)):
    """A bar from p0 to p1 (w wide across, d deep) whose faces all show one trim-sheet strip: U along the bar
    (4 m per repeat), V across the strip."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = (p1 - p0)
    L = ax.length
    ax.normalize()
    upv = Vector(up)
    side = ax.cross(upv).normalized()
    upv = side.cross(ax).normalized()
    bm = bmesh.new()
    corners = []
    for (a, b) in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
        corners.append(upv * (a * w) + side * (b * d))
    vs0 = [bm.verts.new(p0 + c) for c in corners]
    vs1 = [bm.verts.new(p1 + c) for c in corners]
    faces = [bm.faces.new((vs0[i], vs0[(i + 1) % 4], vs1[(i + 1) % 4], vs1[i])) for i in range(4)]
    bm.faces.new(vs0[::-1])
    bm.faces.new(vs1)
    bm.normal_update()
    uvl = bm.loops.layers.uv.verify()
    s = STRIP[strip]
    v0, v1 = s["uv_blender"][1] + 0.002, s["uv_blender"][3] - 0.002
    for f in bm.faces:
        for lp in f.loops:
            rel = lp.vert.co - p0
            along = rel.dot(ax)
            across = (rel.dot(upv) / w + 0.5) if f in faces[0::2] else (rel.dot(side) / d + 0.5)
            lp[uvl].uv = (along / TRIMS["u_repeat_m"], v0 + (v1 - v0) * min(max(across, 0), 1))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(material)
    return o


def gable_roof(name, x0, x1, y0, y1, z_eave, z_ridge, material, repeat_m, solar=None):
    """Gable roof with the ridge along X; UV V runs up the slope toward the ridge."""
    ym = (y0 + y1) / 2
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.verify()
    slope_len = math.hypot(ym - y0, z_ridge - z_eave)
    for (ya, sgn) in ((y0, 1), (y1, -1)):
        a = bm.verts.new((x0, ya, z_eave))
        b = bm.verts.new((x1, ya, z_eave))
        c = bm.verts.new((x1, ym, z_ridge))
        dd = bm.verts.new((x0, ym, z_ridge))
        f = bm.faces.new((a, b, c, dd) if sgn > 0 else (b, a, dd, c))
        for lp in f.loops:
            co = lp.vert.co
            vv = slope_len * (1 - abs(co.y - ym) / abs(ym - ya))
            uu = co.x if sgn > 0 else -co.x
            lp[uvl].uv = (uu / repeat_m, vv / repeat_m)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(material)
    sol = o.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = 0.12
    if solar:
        # 2 rows x 4 modules (1.0 x 1.65 m, short side along X) on the front (y0) slope
        ang = math.atan2(z_ridge - z_eave, ym - y0)
        for r in range(2):
            for cidx in range(4):
                s0 = 0.5 + r * 1.75
                cx = x0 + 1.0 + cidx * 1.05 + 0.5
                cy = y0 + (s0 + 0.825) * math.cos(ang)
                cz = z_eave + (s0 + 0.825) * math.sin(ang) + 0.08
                bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
                p = bpy.context.object
                p.scale = (1.0, 1.65, 0.04)
                p.rotation_euler = (ang, 0, 0)
                bpy.ops.object.transform_apply(scale=True, rotation=True)
                me = p.data
                me.uv_layers.new()
                for f in me.polygons:
                    for li in f.loop_indices:
                        vco = me.vertices[me.loops[li].vertex_index].co
                        local_u = (vco.x - cx) / 1.0 + 0.5
                        # distance up the slope from the module centre
                        dy, dz = vco.y - cy, vco.z - cz
                        local_v = (dy * math.cos(ang) + dz * math.sin(ang)) / 1.65 + 0.5
                        me.uv_layers[0].data[li].uv = (local_u, local_v)
                p.data.materials.append(solar)
    return o


# ------------------------------------------------------------------------------------------------ scene
def build():
    sc = bc.reset_scene()
    M = {
        "asphalt": mat("M_asphalt", "asphalt.png", 0.85),
        "asphalt_cr": mat("M_asphalt_cr", "asphalt_cracked.png", 0.85),
        "kerb": mat("M_kerb", "kerb_concrete.png", 0.8),
        "paving": mat("M_paving", "paving_slabs.png", 0.8, normal="paving_slabs_normal.png"),
        "grass": mat("M_grass", "grass_lawn.png", 0.9),
        "hedge": mat("M_hedge", "hedge_leaves.png", 0.85),
        "picket": mat("M_picket", "picket_wood_white.png", 0.6),
        "printed": mat("M_printed", "printed_concrete_layers.png", 0.8, normal="printed_concrete_layers_normal.png"),
        "sage": mat("M_sage", "fibercement_sage.png", 0.65, normal="fibercement_panel_joints_normal.png"),
        "clay": mat("M_clay", "fibercement_clay.png", 0.65, normal="fibercement_panel_joints_normal.png"),
        "roof": mat("M_roof", "roof_shingle_dark.png", 0.7, normal="roof_shingle_dark_normal.png"),
        "solar": mat("M_solar", "solar_panel.png", 0.25),
        "truck": mat("M_truck", "truck_paint_white.png", 0.4),
        "card": mat("M_card", "cardboard_box_face.png", 0.85),
        "sand": mat("M_sand", "construction_sand.png", 0.95),
        "gravel": mat("M_gravel", "gravel.png", 0.9),
        "soil": mat("M_soil", "garden_soil.png", 0.95),
        "yellow": mat("M_yellow", "metal_painted_yellow.png", 0.5),
        "glass": mat("M_glass", "glass_frost.png", 0.1, alpha=True),
        "concrete": mat("M_concrete", "concrete_smooth.png", 0.8),
        "wood": mat("M_wood", "wood_boards_stained.png", 0.8),
        "trim": mat("M_trim", "trim_sheet_house.png", 0.6, normal="trim_sheet_house_normal.png",
                    orm="trim_sheet_house_orm.png"),
        "window": mat("M_window", "glass_frost.png", 0.05, tint=(0.15, 0.17, 0.2)),
    }
    # ground: road (asphalt + cracked patch), kerb, pavement, lawn, plots
    add_box("road", -14, -9, -0.2, 2, -2.0, 0.0, M["asphalt"], 4.0)
    add_box("road_cracked", 2, -9, -0.2, 14, -2.0, 0.0, M["asphalt_cr"], 4.0)
    add_box("kerb", -14, -2.0, 0.0, 14, -1.85, 0.15, M["kerb"], 2.0)
    add_box("pavement", -14, -1.85, -0.1, 14, 0.0, 0.15, M["paving"], 2.4)
    add_box("lawn_a", -14, 0.0, -0.1, -1.2, 12, 0.15, M["grass"], 2.0)
    add_box("lawn_b", 1.2, 0.0, -0.1, 14, 12, 0.15, M["grass"], 2.0)
    add_box("drive_gravel", -1.2, 0.0, -0.1, 1.2, 12, 0.13, M["gravel"], 1.0)
    add_box("soil_bed", 9.5, 1.2, 0.0, 13.0, 2.4, 0.2, M["soil"], 1.0)
    add_box("plots", -40, 12, -0.3, 40, 40, 0.05, M["sand"], 4.0)
    # hedge + picket fence along the pavement
    add_box("hedge", 1.6, 0.25, 0.15, 8.5, 1.05, 1.5, M["hedge"], 1.5, bevel=0.12)
    for i in range(48):
        x = -12.5 + i * 0.22
        add_box(f"picket_{i}", x, 0.35, 0.15, x + 0.09, 0.38, 1.05, M["picket"], 1.0, bevel=0.01)
    add_box("rail_a", -12.6, 0.38, 0.35, -2.0, 0.42, 0.42, M["picket"], 1.0)
    add_box("rail_b", -12.6, 0.38, 0.8, -2.0, 0.42, 0.87, M["picket"], 1.0)
    # house A (sage) with a curved printed-concrete lower volume and a printed corner tower
    add_box("houseA_body", -12, 5.0, 0.15, -4.0, 11, 6.2, M["sage"], 4.8)
    add_box("houseA_lower", -12.4, 2.4, 0.15, -6.0, 6.0, 3.1, M["printed"], 1.28, bevel=0.9)
    add_box("houseA_tower", -4.6, 4.6, 0.15, -3.0, 6.4, 6.2, M["printed"], 1.28, bevel=0.6)
    gable_roof("houseA_roof", -12.6, -3.4, 4.4, 11.6, 6.2, 9.0, M["roof"], 2.0, solar=M["solar"])
    # house A window with trim frame
    add_box("houseA_win", -10.5, 4.97, 3.6, -7.5, 5.0, 5.6, M["window"], 4.0)
    trim_bar("winA_top", (-10.6, 4.9, 5.7), (-7.4, 4.9, 5.7), 0.2, 0.25, "window_surround_cream", M["trim"],
             up=(0, -1, 0))
    trim_bar("winA_sill", (-10.7, 4.85, 3.5), (-7.3, 4.85, 3.5), 0.2, 0.3, "sill_cream", M["trim"], up=(0, -1, 0))
    trim_bar("winA_l", (-10.6, 4.9, 3.5), (-10.6, 4.9, 5.8), 0.2, 0.25, "window_surround_cream", M["trim"],
             up=(0, -1, 0))
    trim_bar("winA_r", (-7.4, 4.9, 3.5), (-7.4, 4.9, 5.8), 0.2, 0.25, "window_surround_cream", M["trim"],
             up=(0, -1, 0))
    trim_bar("winA_mull", (-9.0, 4.95, 3.6), (-9.0, 4.95, 5.6), 0.07, 0.06, "window_frame_dark", M["trim"],
             up=(0, -1, 0))
    trim_bar("gutterA", (-12.6, 4.35, 6.1), (-3.4, 4.35, 6.1), 0.14, 0.14, "gutter_dark", M["trim"], up=(0, -1, 0))
    trim_bar("copingA", (-12.0, 2.45, 3.15), (-6.4, 2.45, 3.15), 0.2, 0.2, "coping_cream", M["trim"], up=(0, 0, 1))
    trim_bar("railA", (-12.0, 2.6, 4.1), (-6.4, 2.6, 4.1), 0.06, 0.06, "railing_cap_steel", M["trim"])
    # house B (clay)
    add_box("houseB_body", 4.0, 5.0, 0.15, 12, 11, 6.2, M["clay"], 4.8)
    add_box("houseB_lower", 6.0, 2.4, 0.15, 12.4, 6.0, 3.1, M["printed"], 1.28, bevel=0.9)
    gable_roof("houseB_roof", 3.4, 12.6, 4.4, 11.6, 6.2, 9.0, M["roof"], 2.0, solar=M["solar"])
    add_box("houseB_door", 4.8, 4.97, 0.15, 5.8, 5.0, 2.3, M["window"], 4.0)
    trim_bar("doorB_top", (4.65, 4.92, 2.4), (5.95, 4.92, 2.4), 0.13, 0.1, "door_frame_cream", M["trim"],
             up=(0, -1, 0))
    add_box("houseB_vent", 9.0, 4.96, 4.0, 9.8, 5.0, 4.4, M["trim"], 4.0)
    # street props
    add_box("truck_box", -6.5, -6.2, 0.6, -1.0, -3.8, 3.4, M["truck"], 3.0, bevel=0.08)
    add_box("truck_cab", -1.0, -6.1, 0.4, 0.8, -3.9, 2.6, M["truck"], 3.0, bevel=0.15)
    for i, (x, y, z, s) in enumerate([(1.4, -3.4, 0.0, 0.55), (2.1, -3.0, 0.0, 0.5), (1.6, -2.8, 0.55, 0.45),
                                      (2.9, -4.2, 0.0, 0.6)]):
        add_box(f"box_{i}", x, y, z, x + s, y + s * 0.8, z + s * 0.75, M["card"], None, bevel=0.01)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.16, depth=8.0, location=(-1.6, -1.2, 4.1))
    pole = bpy.context.object
    box_uv(pole, 2.0)
    pole.data.materials.append(M["concrete"])
    add_box("shed", 9.6, 7.5, 0.15, 12.4, 10.0, 2.4, M["wood"], 2.0)
    add_box("crane_mast", 16, 18, 0.0, 17.2, 19.2, 18.0, M["yellow"], 2.0)
    add_box("crane_jib", 2.0, 18.2, 17.0, 26.0, 19.0, 17.8, M["yellow"], 2.0)
    bpy.ops.mesh.primitive_cylinder_add(radius=1.2, depth=3.0, location=(10.8, 3.6, 0.15), rotation=(0, math.pi / 2, 0))
    gh = bpy.context.object
    box_uv(gh, 1.5)
    gh.data.materials.append(M["glass"])
    add_box("planter", 10.0, 3.0, 0.15, 11.6, 4.2, 0.45, M["soil"], 1.0)
    return sc


def light_and_render(sc):
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.50, 0.56, 0.72, 1.0)
    bg.inputs["Strength"].default_value = 0.7
    # low warm sun from the south-west (camera side, left), like the concept's sun-lit faces
    bpy.ops.object.light_add(type="SUN", rotation=(math.radians(64), 0, math.radians(-38)))
    sun = bpy.context.object
    sun.data.energy = 4.6
    sun.data.color = (1.0, 0.84, 0.66)
    sun.data.angle = math.radians(2.0)
    eng = bc._set_engine(sc)
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 1536, 864
    if eng == "CYCLES":
        bc.setup_cycles_gpu(sc, 48)
    try:
        sc.eevee.use_shadows = True
        sc.eevee.taa_render_samples = 32
    except Exception:
        pass
    cam_data = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    shots = {
        "aerial": ((0.0, -26.0, 20.0), (0.0, 3.0, 1.5), 32),
        "street": ((4.2, -8.6, 1.7), (2.0, 6.0, 3.0), 18),
    }
    os.makedirs(PREV, exist_ok=True)
    for name, (loc, target, lens) in shots.items():
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        cam_data.lens = lens
        sc.render.filepath = os.path.join(PREV, f"lookdev_{name}.png")
        try:
            bpy.ops.render.render(write_still=True)
        except RuntimeError as e:
            print("render failed, retrying on CPU Cycles:", e)
            bc._set_engine(sc, ("CYCLES",))
            sc.cycles.device = "CPU"
            sc.cycles.samples = 32
            bpy.ops.render.render(write_still=True)
        print("rendered", sc.render.filepath)


if __name__ == "__main__":
    light_and_render(build())
