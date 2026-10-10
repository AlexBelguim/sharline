"""Stage E for build_solace.py: sockets, export (.blend/.glb/.fbx), Cycles renders, pose tests, contact sheet."""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

import blender_common as bc
import sol_lib as S
import sol_rig as R
from sol_lib import log

SOCKET_SIZE = 0.03


def _empty(name, loc, rot_cols=None, size=SOCKET_SIZE):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = size
    bpy.context.scene.collection.objects.link(e)
    M = Matrix.Identity(4)
    if rot_cols is not None:
        X, Y, Z = [Vector(c).normalized() for c in rot_cols]
        M = Matrix((X, Y, Z)).transposed().to_4x4()
    M.translation = Vector(loc)
    e.matrix_world = M
    return e


def _frame(yaxis, zhint):
    Y = Vector(yaxis).normalized()
    Z = Vector(zhint)
    Z = (Z - Y * Z.dot(Y)).normalized()
    X = Y.cross(Z).normalized()
    return X, Y, Z


def make_sockets(arm, J, bloom_obj, drone=None):
    head_top = float(S.mesh_co(S.body().data)[:, 2].max())
    socks = []
    # halo: 0.22 m above the top of the head, centred over the skull; position only (stays level). It is parented to
    # the head bone for the rest position, but 0.42 m above the head joint a head pitch would swing it, so the
    # extras carry the engine rule: halo position = head-joint world position + world up * halo_offset_up_m
    hj = Vector(J["head"])
    e = _empty("SOL_SOCKET_Halo", (0.0, float(J["head"][1]), head_top + 0.22))
    e["use_position_only"] = True
    e["halo_anchor_bone"] = "head"
    e["halo_offset_up_m"] = round(float(head_top + 0.22 - hj.z), 4)
    e["note"] = ("position only, world-level: place the halo at the head joint's world position + world up * "
                 "halo_offset_up_m (do not inherit head pitch/yaw)")
    R.parent_to_bone(e, arm, "head")
    socks.append(e)
    # weapon grips: origin at the grip top where the web of the hand sits (WEAPON_MODULAR_SPEC / style guide: weapon
    # origin = pistol-grip hand position), i.e. between the index knuckle and the thumb root, lifted 1.2 cm off the
    # palm to the centre of an imagined grip. Local -Y = finger direction (muzzle), +Z = thumb side.
    for sd, nm in (("r", "SOL_SOCKET_WeaponR"), ("l", "SOL_SOCKET_WeaponL")):
        wr = Vector(J[f"hand_{sd}"])
        tip = Vector(J[f"_tip_{sd}"])
        e1 = (tip - wr).normalized()
        e2 = Vector(J[f"_hand_e2_{sd}"])
        back = Vector(J[f"_hand_e3_{sd}"])
        if back.z < 0:
            back = -back
        if f"index_01_{sd}" in J and f"thumb_02_{sd}" in J:
            web = (Vector(J[f"index_01_{sd}"]) + Vector(J[f"thumb_02_{sd}"])) / 2
        else:
            web = wr + e1 * 0.05 + e2 * 0.02
        grip = web - back * 0.012
        X, Y, Z = _frame(-e1, e2)
        e = _empty(nm, grip, (X, Y, Z))
        e["note"] = "grip point (web of the hand): local -Y along the fingers (muzzle), +Z thumb side"
        R.parent_to_bone(e, arm, f"hand_{sd}")
        socks.append(e)
    # injector: bracer muzzle, at the wrist end of the housing on top of the right forearm; -Y along the forearm
    el, wr = Vector(J["lowerarm_r"]), Vector(J["hand_r"])
    f = (wr - el).normalized()
    up = Vector((0, 0, 1))
    m = (up - f * up.dot(f)).normalized()
    m = (m + Vector((0, -0.27, 0))).normalized()
    p_axis = el + (wr - el) * 0.90
    import sol_parts as P
    surf = P.Surf(S.body())
    hit = surf.bvh.ray_cast(p_axis + m * 0.15, -m, 0.3)
    p = (hit[0] + m * 0.008) if hit[0] else p_axis + m * 0.045
    X, Y, Z = _frame(-f, m)
    e = _empty("SOL_SOCKET_Injector", p, (X, Y, Z))
    e["note"] = "heal-vial muzzle: local -Y fires along the right forearm toward the hand"
    R.parent_to_bone(e, arm, "lowerarm_r")
    socks.append(e)
    # drone dock: drone centre on her left hip; SOL_Drone (origin at its centre) becomes its child
    dc = drone.matrix_world.translation.copy() if drone is not None else Vector(R.DRONE_C)
    e = _empty("SOL_SOCKET_DroneDock", tuple(dc), ((1, 0, 0), (0, 1, 0), (0, 0, 1)))
    e["note"] = "heal-drone dock / launch point; SOL_Drone is its child (hide it or detach and fly it for MEND DRONE)"
    R.parent_to_bone(e, arm, "pelvis")
    socks.append(e)
    if drone is not None:
        mw = drone.matrix_world.copy()
        drone.parent = e
        drone.matrix_parent_inverse = Matrix.Identity(4)
        drone.matrix_world = mw
        bpy.context.view_layer.update()
    # bloom vfx: bud core centre, child of the module
    piv = bloom_obj.matrix_world.translation
    e = _empty("SOL_SOCKET_BloomVFX", (0.0, piv.y + 0.013, 1.330))
    e["note"] = "heal-aura VFX origin (bud core centre)"
    mw = e.matrix_world.copy()
    e.parent = bloom_obj
    e.matrix_parent_inverse = bloom_obj.matrix_world.inverted()
    e.matrix_world = mw
    socks.append(e)
    for s_ in socks:
        log(f"socket {s_.name}: {tuple(round(v, 3) for v in s_.matrix_world.translation)}")
    return socks


def export_objects():
    names = ["SOL_Armature", "SOL_Body", "SOL_Gear", "SOL_Bloom", "SOL_Bloom_Vane_C", "SOL_Bloom_Vane_L",
             "SOL_Bloom_Vane_R", "SOL_Drone"] + [o.name for o in bpy.data.objects if o.name.startswith("SOL_SOCKET_")]
    return [bpy.data.objects[n] for n in names if bpy.data.objects.get(n)]


def export_all(base):
    objs = export_objects()
    for o in objs:
        if o.type == "MESH" and o.data.name != o.name:
            o.data.name = o.name
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["SOL_Armature"]
    R.reset_pose(bpy.data.objects["SOL_Armature"])
    bpy.ops.export_scene.gltf(filepath=base + ".glb", export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=False, export_skins=True, export_extras=True, export_animations=False,
                              export_materials="EXPORT", export_image_format="AUTO")
    log("exported", base + ".glb")
    bpy.ops.export_scene.fbx(filepath=base + ".fbx", use_selection=True, apply_unit_scale=True,
                             apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             use_mesh_modifiers=False, add_leaf_bones=False, path_mode="COPY", embed_textures=True,
                             object_types={"ARMATURE", "MESH", "EMPTY"}, use_custom_props=True,
                             bake_anim=False, primary_bone_axis="Y", secondary_bone_axis="X")
    log("exported", base + ".fbx")



# ------------------------------------------------------------------------------------------------ renders
def _hide_helpers():
    for o in bpy.data.objects:
        if o.name.startswith(("VIZ_", "_")) and o.type == "MESH":
            o.hide_render = True


def beauty(out_dir, samples=96):
    _hide_helpers()
    views = ["front", "three_quarter", "right", "back", "left", "three_quarter_back"]
    paths = S.shoot("solace", views, (0, 0.03, 0.86), 0.93, out_dir=out_dir, engine="CYC", samples=samples,
                    res=(900, 1200), lens=70)
    return paths


def head_closeups(out_dir, samples=96):
    return S.shoot("head", ["head_front", "head_tq", "head_tq_r", "side_l"], (0, -0.015, 1.55), 0.105,
                   out_dir=out_dir, engine="CYC", samples=samples, res=(800, 800), lens=85)


def set_vanes(angle_frac):
    for nm in ("SOL_Bloom_Vane_C", "SOL_Bloom_Vane_L", "SOL_Bloom_Vane_R"):
        v = bpy.data.objects[nm]
        if "_rest" not in v:
            v["_rest"] = [list(r) for r in v.matrix_basis]
        rest = Matrix(v["_rest"])
        a = math.radians(v["open_angle_deg"] * angle_frac)
        v.matrix_basis = rest @ Matrix.Rotation(a, 4, "X")
    bpy.context.view_layer.update()


def bloom_closeups(out_dir, samples=96):
    paths = []
    c = (0, 0.15, 1.33)
    set_vanes(0.0)
    paths += S.shoot("bloom_closed", ["back", "three_quarter_back", "side_l"], c, 0.27, out_dir=out_dir,
                     engine="CYC", samples=samples, res=(800, 800), lens=70)
    set_vanes(1.0)
    paths += S.shoot("bloom_open", ["back", "three_quarter_back", "side_l"], c, 0.27, out_dir=out_dir,
                     engine="CYC", samples=samples, res=(800, 800), lens=70)
    set_vanes(0.0)
    for nm in ("SOL_Bloom_Vane_C", "SOL_Bloom_Vane_L", "SOL_Bloom_Vane_R"):
        v = bpy.data.objects[nm]
        if "_rest" in v:
            del v["_rest"]
    return paths


POSES = [("arms_down", ["front", "three_quarter"], (0, 0.02, 0.88), 0.9),
         ("crouch", ["three_quarter", "right"], (0, -0.08, 0.55), 0.70),
         ("run", ["right", "three_quarter"], (0, 0.0, 0.86), 0.93),
         ("head_turn", ["front", "three_quarter"], (0, 0.02, 1.40), 0.36),
         ("grip", [(0.7, -1, 0.1), (-0.7, -1, 0.1)], (0, -0.02, 1.0), 0.55)]


def pose_tests(out_dir, samples=48, J=None):
    arm = bpy.data.objects["SOL_Armature"]
    if J is not None:
        R.set_palms(J)
    paths = []
    for name, views, c, r in POSES:
        R.pose(arm, name)
        paths += S.shoot("pose_" + name, views, c, r, out_dir=out_dir, engine="CYC", samples=samples,
                         res=(600, 800), lens=60)
    R.reset_pose(arm)
    return paths


def silhouettes(out_dir):
    """Brief section 9 / style guide: flat black silhouettes (front, her-left side, back), shown at 64 px tall
    (nearest-upscaled x4 so the pixels are visible) above the 300 px originals."""
    sc = bpy.context.scene
    keep = (sc.render.engine, sc.render.resolution_x, sc.render.resolution_y)
    _hide_helpers()
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "FLAT"
    sh.color_type = "SINGLE"
    sh.single_color = (0, 0, 0)
    sh.background_type = "VIEWPORT"
    sh.background_color = (1, 1, 1)
    sh.show_cavity = False
    sh.show_shadows = False
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.film_transparent = False
    W, H = 240, 300
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 100
    cam = S._cam(sc)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 1.9
    tiles = []
    os.makedirs(S.DIAG, exist_ok=True)
    for nm, d in (("front", (0, -1, 0)), ("side", (1, 0, 0)), ("back", (0, 1, 0))):
        cam.location = (d[0] * 4, d[1] * 4, 0.9)
        cam.rotation_euler = (Vector((0, 0, 0.9)) - cam.location).to_track_quat("-Z", "Y").to_euler()
        p = os.path.join(S.DIAG, f"_sil_{nm}.png")
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(p, check_existing=False)
        tiles.append(np.array(im.pixels[:], np.float32).reshape(H, W, 4)[..., 0])
        bpy.data.images.remove(im)
    cam.data.type = "PERSP"
    sc.render.engine, sc.render.resolution_x, sc.render.resolution_y = keep
    # 64 px versions: area-average down to 64 rows (51 cols), then x4 nearest
    sh_, sw = 64, int(round(64 * W / H))
    smalls = []
    for t in tiles:
        yi = (np.arange(sh_ + 1) * H / sh_).astype(int)
        xi = (np.arange(sw + 1) * W / sw).astype(int)
        s = np.array([[t[yi[r]:yi[r + 1], xi[c]:xi[c + 1]].mean() for c in range(sw)] for r in range(sh_)])
        smalls.append(np.repeat(np.repeat(s, 4, 0), 4, 1))
    gap = 40
    top = np.ones((sh_ * 4, 3 * sw * 4 + 2 * gap))
    bot = np.ones((H, 3 * W + 2 * gap))
    for i in range(3):
        top[:, i * (sw * 4 + gap):i * (sw * 4 + gap) + sw * 4] = smalls[i]
        bot[:, i * (W + gap):i * (W + gap) + W] = tiles[i]
    cw = max(top.shape[1], bot.shape[1])
    buf = np.ones((top.shape[0] + bot.shape[0] + gap, cw))
    buf[bot.shape[0] + gap:, :top.shape[1]] = top          # row 0 = bottom: the 64 px row goes on top
    buf[:bot.shape[0], :bot.shape[1]] = bot
    rgba = np.dstack([buf, buf, buf, np.ones_like(buf)]).astype(np.float32)
    img = bpy.data.images.new("_sil", rgba.shape[1], rgba.shape[0])
    img.pixels.foreach_set(rgba.ravel())
    out = os.path.join(out_dir, "silhouette_64.png")
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    log("silhouette sheet", out)
    return out


def contact(paths, out, cols):
    """Contact sheet; images of different sizes are fitted into equal cells."""
    imgs = [bpy.data.images.load(p, check_existing=False) for p in paths]
    cw, ch = 450, 600
    rows = math.ceil(len(imgs) / cols)
    buf = np.full((ch * rows, cw * cols, 4), 0.1, np.float32)
    buf[..., 3] = 1
    for i, im in enumerate(imgs):
        w, h = im.size
        px = np.array(im.pixels[:], np.float32).reshape(h, w, 4)
        s = min(cw / w, ch / h)
        nw, nh = int(w * s), int(h * s)
        yi = (np.arange(nh) / s).astype(int).clip(0, h - 1)
        xi = (np.arange(nw) / s).astype(int).clip(0, w - 1)
        small = px[yi][:, xi]
        r, c = divmod(i, cols)
        y0 = (rows - 1 - r) * ch + (ch - nh) // 2
        x0 = c * cw + (cw - nw) // 2
        buf[y0:y0 + nh, x0:x0 + nw] = small
        bpy.data.images.remove(im)
    img = bpy.data.images.new("_contact", cw * cols, ch * rows)
    img.pixels.foreach_set(buf.ravel())
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    log("contact sheet", out)
    return out
