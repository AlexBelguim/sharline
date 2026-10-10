"""Stage E for build_kestrel.py: final scale, sockets, export (.blend/.glb/.fbx), renders, pose tests, contact sheets.

Review round 2:
  - scale: the style guide's 1.70 m is WITHOUT hair volume, so the finished rig is scaled about the origin until
    the hair top is at 1.72 m (skull crown ~1.70). Stages A-D keep working at the 1.70 m hair-top size their
    measured coordinates were tuned for; the scale is applied here to the mesh data, the bones and the hand data.
  - halo: KES_SOCKET_HaloAnchor (on `head`, at the top of the hair over the skull) defines the halo exactly:
    halo position = anchor world position + 0.22 m world up, halo kept level. KES_SOCKET_Halo (the spec's
    socket, 0.22 m above the head at rest) now hangs on `neck_01`, so code that just copies its position no longer
    swings the halo 0.45 m around the head joint when she looks up or down.
  - weapon sockets at the web of each hand (between the thumb and index knuckles), 1.2 cm in toward the palm (the
    top-centre of a pistol grip, WEAPON_MODULAR_SPEC origin), mirror-symmetric.
  - the FBX gets separate roughness / metallic images (FBX has no packed-ORM slot), one base-colour image.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

import blender_common as bc
import kes_lib as K
import kes_pose as PZ
from kes_lib import log

HALO_ABOVE = 0.22
HAIR_TOP = 1.72          # final height to the top of the hair (skull crown ~1.70, style guide "1.70 m without hair")
WEB_INSET = 0.012        # weapon socket: from the web of the hand toward the palm (into the grip)


def _empty(name, mw, arm, bone, size=0.05):
    ob = bpy.data.objects.get(name) or bpy.data.objects.new(name, None)
    if ob.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(ob)
    ob.empty_display_type = "ARROWS"
    ob.empty_display_size = size
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    ob.matrix_parent_inverse = Matrix.Identity(4)
    bpy.context.view_layer.update()
    ob.matrix_world = mw          # Blender solves the local (bone-tail relative) transform
    bpy.context.view_layer.update()
    return ob


def scale_to_height(arm):
    """Uniformly scale the rig (bones, skinned meshes, hand data) about the origin so the hair top is HAIR_TOP."""
    PZ.reset(arm)
    body = K.body()
    top = float(K.mesh_co(body.data)[:, 2].max())
    s = HAIR_TOP / top
    if abs(s - 1.0) < 1e-5:
        return 1.0
    for ob in (body, bpy.data.objects.get("KES_Eyepiece")):
        if ob is not None:
            ob.data.transform(Matrix.Scale(s, 4))
            ob.data.update()
    K.activate(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    for eb in arm.data.edit_bones:
        eb.head = eb.head * s
        eb.tail = eb.tail * s
    bpy.ops.object.mode_set(mode="OBJECT")
    for k in [k for k in arm.keys() if k.startswith("kes_hand_")]:
        d = arm[k].to_dict()
        for f in ("wrist", "thumb_tip", "index_mcp", "pinky_mcp", "middle_mcp"):
            d[f] = [c * s for c in d[f]]
        arm[k] = d
    bpy.context.view_layer.update()
    log(f"scaled x{s:.4f}: hair top {top:.3f} -> {HAIR_TOP:.3f} m")
    return s


def add_sockets(arm):
    PZ.reset(arm)
    body = K.body()
    co = K.mesh_co(body.data)
    top = co[:, 2].max()
    # top of the hair over the skull centre (x 0.005, y 0.02 at the 1.70 build scale -> scaled with the rig)
    s = top / 1.70
    anchor = Vector((0.005 * s, 0.02 * s, top))
    a = _empty("KES_SOCKET_HaloAnchor", Matrix.Translation(anchor), arm, "head", 0.04)
    a["usage"] = "halo position = this node's world position + halo_offset_up_m along WORLD up; keep the halo level"
    a["halo_offset_up_m"] = HALO_ABOVE
    h = _empty("KES_SOCKET_Halo", Matrix.Translation(anchor + Vector((0, 0, HALO_ABOVE))), arm, "neck_01", 0.08)
    h["usage"] = ("position only, keep the halo level. Parented to neck_01 (not the head) so head pitch does not "
                  "swing it; for exact tracking of the skull use KES_SOCKET_HaloAnchor + halo_offset_up_m")
    h["use_position_only"] = True
    bones = arm.data.bones
    for sd, nm in (("r", "KES_SOCKET_WeaponR"), ("l", "KES_SOCKET_WeaponL")):
        hf = arm[f"kes_hand_{sd}"]
        a_ = Vector(hf["a"]).normalized()          # wrist -> knuckles
        lat = Vector(hf["lat"]).normalized()       # toward the thumb
        palm = Vector(hf["n"]).normalized()        # palm side (kes_skin flips it per hand)
        web = (bones[f"thumb_02_{sd}"].head_local + bones[f"index_01_{sd}"].head_local) / 2
        p = web + palm * WEB_INSET
        # socket axes: -Y = forward (muzzle convention), +Z = thumb side ("up" of a gripped weapon)
        yax = -a_
        zax = (lat - lat.dot(yax) * yax).normalized()
        xax = yax.cross(zax).normalized()
        M = Matrix((xax, yax, zax)).transposed().to_4x4()
        M.translation = p
        e = _empty(nm, M, arm, f"hand_{sd}", 0.06)
        e["usage"] = ("weapon origin (top-centre of the pistol grip, where the web of the hand sits) snaps here; "
                      "-Y = hand forward (muzzle direction), +Z = thumb side")
    log(f"sockets: halo anchor z {top:.3f}, halo z {top + HALO_ABOVE:.3f} (neck_01), weapon sockets at the web")


def _fbx_material_pass(restore=None):
    """FBX has no packed ORM slot: link separate roughness / metallic images straight to the BSDF for the FBX
    export, then restore the glTF material (call again with the returned state)."""
    mat = bpy.data.materials["M_KES_Body"]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if restore is not None:
        for n in restore["nodes"]:
            nt.nodes.remove(n)
        for sock, src in restore["links"]:
            nt.links.new(src, bsdf.inputs[sock])
        return None
    orm = bpy.data.images["KES_ORM"]
    px = K.img_to_np(orm)
    state = {"nodes": [], "links": []}
    for ch, nm, sock in ((1, "KES_Roughness", "Roughness"), (2, "KES_Metallic", "Metallic")):
        g = np.repeat(px[..., ch:ch + 1], 3, axis=2)
        img = K.np_to_img(nm, np.concatenate([g, np.ones_like(g[..., :1])], -1), colorspace="Non-Color")
        p = os.path.join(K.TEX, nm + ".png")
        K.save_png(img, p)
        img.pack()
        old = bsdf.inputs[sock].links[0].from_socket if bsdf.inputs[sock].is_linked else None
        state["links"].append((sock, old))
        tn = nt.nodes.new("ShaderNodeTexImage")
        tn.image = img
        nt.links.new(tn.outputs["Color"], bsdf.inputs[sock])
        state["nodes"].append(tn)
    return state


def export_files(arm):
    PZ.reset(arm)
    base = os.path.join(K.OUT, "kestrel")
    for o in (K.body(), bpy.data.objects["KES_Eyepiece"]):
        o.data.name = o.name
    # build-time helper data (hand frames for sockets / pose tests) stays out of the exported files
    stash = {k: arm[k].to_dict() for k in list(arm.keys()) if k.startswith("kes_hand_")}
    for k in stash:
        del arm[k]
    objs = [arm, K.body(), bpy.data.objects["KES_Eyepiece"]] + \
        [o for o in bpy.data.objects if o.name.startswith("KES_SOCKET_")]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(filepath=base + ".glb", export_format="GLB", use_selection=True, export_yup=True,
                              export_apply=False, export_skins=True, export_animations=False,
                              export_morph=False, export_extras=True)
    log("exported", base + ".glb")
    state = _fbx_material_pass()
    try:
        bpy.ops.export_scene.fbx(filepath=base + ".fbx", use_selection=True,
                                 object_types={"ARMATURE", "MESH", "EMPTY"}, apply_unit_scale=True,
                                 apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                                 use_mesh_modifiers=False, add_leaf_bones=False, bake_anim=False,
                                 use_armature_deform_only=False, path_mode="COPY", embed_textures=True,
                                 mesh_smooth_type="FACE", use_custom_props=True)
    finally:
        _fbx_material_pass(restore=state)
    for nm in ("KES_Roughness", "KES_Metallic"):          # FBX-only images: not kept in the .blend
        if nm in bpy.data.images and bpy.data.images[nm].users == 0:
            bpy.data.images.remove(bpy.data.images[nm])
    log("exported", base + ".fbx")
    for k, v in stash.items():
        arm[k] = v


def save_blend():
    # drop helper objects/materials, pack, save
    for o in list(bpy.data.objects):
        if o.name.startswith("_"):
            bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.materials):
        if m.users == 0:
            bpy.data.materials.remove(m)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0   # no kestrel.blend1 backups
    p = os.path.join(K.OUT, "kestrel.blend")
    bpy.ops.wm.save_as_mainfile(filepath=p, compress=True, copy=True)
    log("saved", p)


def stats():
    tris = {o.name: K.tri_count(o) for o in (K.body(), bpy.data.objects["KES_Eyepiece"])}
    log("tris:", tris, "total", sum(tris.values()))
    return tris


def _import_halo():
    """The real halo (assets/shields/export/HALO_Bulwark.glb, arcs + medium band) for the halo socket checks."""
    path = r"F:/git/val etf/assets/shields/export/HALO_Bulwark.glb"
    if not os.path.exists(path):
        return None, []
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    keep = [o for o in new if o.type == "MESH" and ("Arc" in o.name or "Band_Medium" in o.name)]
    holder = bpy.data.objects.new("_halo_holder", None)
    bpy.context.scene.collection.objects.link(holder)
    for o in new:
        if o.type == "MESH" and o not in keep:
            o.hide_render = True
        o.name = "_" + o.name if not o.name.startswith("_") else o.name
    for o in keep:
        mw = o.matrix_world.copy()
        o.parent = holder
        o.matrix_world = mw
    return holder, new


def _place_halo(holder):
    a = bpy.data.objects["KES_SOCKET_HaloAnchor"]
    bpy.context.view_layer.update()
    holder.matrix_world = Matrix.Translation(a.matrix_world.translation + Vector((0, 0, a["halo_offset_up_m"])))
    bpy.context.view_layer.update()


def _cam_render(path, center, direction, radius, res=(900, 900), samples=48, lens=85):
    sc = bpy.context.scene
    cd = bpy.data.cameras.get("_KesCam") or bpy.data.cameras.new("_KesCam")
    cam = bpy.data.objects.get("_KesCam") or bpy.data.objects.new("_KesCam", cd)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cd.lens = lens
    cd.clip_start = 0.005
    d = Vector(direction).normalized()
    fov = 2 * math.atan(cd.sensor_width / (2 * lens))
    cam.location = Vector(center) + d * (radius / math.sin(fov / 2))
    cam.rotation_euler = (Vector(center) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    bc.setup_cycles_gpu(sc, samples)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = path
    try:
        bpy.ops.render.render(write_still=True)
    except RuntimeError as e:
        log("GPU render failed, CPU fallback:", e)
        sc.cycles.device = "CPU"
        bpy.ops.render.render(write_still=True)
    return path


def renders(arm):
    out = K.RENDERS
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):                       # no stale renders from an earlier build
        if f.lower().endswith(".png"):
            os.remove(os.path.join(out, f))
    PZ.reset(arm)
    bc.setup_studio()
    objs = [K.body(), bpy.data.objects["KES_Eyepiece"]]
    views = ("front", "three_quarter", "right", "back", "left", "three_quarter_back")
    paths = bc.render_views(out, "kestrel", objs, views=views, res=(900, 1200), engine="CYCLES", samples=64)
    bc.contact_sheet(paths, os.path.join(out, "kestrel_sheet.png"), cols=3)
    s = HAIR_TOP / 1.70
    head = bc.render_views(out, "kestrel_head", objs, views=("front", "three_quarter", (-0.75, -1, 0.2), "right"),
                           res=(900, 900), engine="CYCLES", samples=64, focus=((0.01, -0.02, 1.555 * s), 0.135))
    bc.contact_sheet(head, os.path.join(out, "kestrel_head_sheet.png"), cols=2)
    # socket check: the real halo at the anchor (+0.22 m), a gold ring on KES_SOCKET_Halo, block "pistols" (muzzle
    # along the socket's -Y) in the hands
    probes = []
    bpy.ops.mesh.primitive_torus_add(major_radius=0.16, minor_radius=0.006, major_segments=48, minor_segments=8)
    ring = bpy.context.active_object
    ring.name = "_probe_ring"
    ring.matrix_world = Matrix.Translation(bpy.data.objects["KES_SOCKET_Halo"].matrix_world.translation)
    bc.assign(ring, bc.material("_probe_gold", (1.0, 0.62, 0.08), emission=(1.0, 0.62, 0.08), emission_strength=4))
    probes.append(ring)
    for nm in ("KES_SOCKET_WeaponR", "KES_SOCKET_WeaponL"):
        g = bc.box("_probe_" + nm, (0.03, 0.20, 0.045), loc=(0, -0.07, 0.03),
                   mat=bc.material("_probe_red", (0.8, 0.1, 0.05), rough=0.5))
        grip = bc.box("_probe_grip_" + nm, (0.028, 0.035, 0.09), loc=(0, 0.01, -0.035), rot=(-15, 0, 0),
                      mat=bc.material("_probe_red", (0.8, 0.1, 0.05), rough=0.5))
        for o in (g, grip):
            o.matrix_world = bpy.data.objects[nm].matrix_world @ o.matrix_world
            probes.append(o)
    bc.render_views(out, "sockets", objs + probes, views=("front", (0.9, -1, 0.3)), res=(900, 1200),
                    engine="CYCLES", samples=32)
    for o in probes:
        bpy.data.objects.remove(o, do_unlink=True)
    # pose tests (review round 2 poses first)
    pp = []
    shots = [
        ("rifle", [((0.5, -1, 0.3), (0.0, -0.05, 1.2 * s), 0.34), ((-0.4, 1, 0.3), (0.0, 0.1, 1.2 * s), 0.40)]),
        ("zipline", [((0.5, -1, 0.2), (0.0, 0.0, 1.38 * s), 0.46), ((-0.3, 1, 0.3), (0.0, 0.05, 1.45 * s), 0.44),
                     ((1, -0.4, -0.1), (0.15, 0.0, 1.45 * s), 0.32)]),
        ("zipline_one", [((-0.6, -1, 0.2), (0.0, 0.0, 1.38 * s), 0.46)]),
        ("head_down", [((0.5, 1, 0.25), (0.0, 0.02, 1.47 * s), 0.20)]),
        ("head_yaw60", [((0.4, 1, 0.3), (0.0, 0.02, 1.47 * s), 0.20)]),
        ("crouch", [((0.9, -1, 0.25), None, None)]),
        ("run", [((0.9, -1, 0.25), None, None)]),
        ("fists", [((0.6, -1, 0.3), "hand_l", 0.10), ((-0.6, -1, 0.3), "hand_r", 0.10)]),
    ]
    for p, views_ in shots:
        PZ.pose(arm, p)
        PZ.drop_to_floor(arm, objs)
        for k, (d, c, r) in enumerate(views_):
            path = os.path.join(out, f"pose_{p}_{k}.png")
            if c is None:
                mn, mx = bc.world_bounds(objs)
                c, r = (mn + mx) / 2, (mx - mn).length * 0.5
            elif isinstance(c, str):
                c = arm.matrix_world @ arm.pose.bones[c].tail
            pp.append(_cam_render(path, c, d, r))
    PZ.reset(arm)
    bc.contact_sheet(pp, os.path.join(out, "kestrel_pose_sheet.png"), cols=4)
    # halo: the real halo placed by the anchor rule at rest, head down 30 deg, head up 25 deg, rifle-ready
    holder, imported = _import_halo()
    if holder is not None:
        bc.setup_studio(floor=True)
        hp = []
        for nm in ("rest", "head_down", "head_up", "rifle"):
            PZ.reset(arm)
            if nm == "head_down":
                PZ.pose(arm, "head_down")
            elif nm == "head_up":
                PZ.twist(arm, "neck_01", (1, 0, 0), -8)
                PZ.twist(arm, "head", (1, 0, 0), -17)
            elif nm == "rifle":
                PZ.pose(arm, "rifle")
            _place_halo(holder)
            hp.append(_cam_render(os.path.join(out, f"halo_{nm}.png"), (0.0, 0.0, 1.66 * s), (1.0, -0.15, 0.12),
                                  0.42, res=(800, 800)))
        PZ.reset(arm)
        _place_halo(holder)
        hp.append(_cam_render(os.path.join(out, "halo_tpcam.png"), (0.0, 0.02, 1.58 * s), (-0.35, 1, 0.55), 0.58,
                              res=(800, 800)))
        bc.contact_sheet(hp, os.path.join(out, "kestrel_halo_sheet.png"), cols=5)
        for o in imported + [holder]:
            if o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)
    # weapon grip: the real Mako snapped to the sockets, fingers curled around the grip
    mako = r"F:/git/val etf/assets/weapons/ar7_mako/mako_default.glb"
    if os.path.exists(mako):
        bc.setup_studio()
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=mako)
        new = [o for o in bpy.data.objects if o not in before]
        holder = bpy.data.objects.new("_mako_holder", None)
        bpy.context.scene.collection.objects.link(holder)
        for o in new:
            if o.parent is None:
                o.parent = holder
        PZ.pose(arm, "grip")
        gp = []
        for side, x in (("R", -1), ("L", 1)):
            sock = bpy.data.objects[f"KES_SOCKET_Weapon{side}"]
            bpy.context.view_layer.update()
            holder.matrix_world = sock.matrix_world.copy()
            bpy.context.view_layer.update()
            c = sock.matrix_world.translation
            for vn, d in (("out", (x, -0.3, 0.2)), ("in", (-x, -0.6, -0.1)), ("top", (x * 0.3, 0.2, 1.0))):
                gp.append(_cam_render(os.path.join(out, f"grip_{side}_{vn}.png"), c, d, 0.13, res=(700, 700)))
        bc.contact_sheet(gp, os.path.join(out, "kestrel_grip_sheet.png"), cols=3)
        PZ.reset(arm)
        for o in new + [holder]:
            if o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)
    return paths


def finish(renders_on=True):
    arm = bpy.data.objects["KES_Armature"]
    scale_to_height(arm)
    add_sockets(arm)
    stats()
    export_files(arm)
    if renders_on:
        renders(arm)
    save_blend()
