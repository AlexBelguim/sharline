"""Stage B for build_kestrel.py: texture fixes on the TRELLIS base-colour atlas.

The TRELLIS atlas is cut into hundreds of tiny charts, so every edit is done in OBJECT space: Cycles bakes the
object-space position / normal of every texel, numpy edits the colours with masks defined on the 3D body (and on a
front-projected "face canvas" for the face, see kes_face.py), and a final Cycles bake mixes the teal hair-tip dye
into the new base colour.
"""
import os
import time

import bpy
import numpy as np

import blender_common as bc
import kes_face
import kes_lib as K
from kes_lib import log

TEXN = K.TEX_SIZE


def _cycles(samples=1):
    sc = bpy.context.scene
    bc.setup_cycles_gpu(sc, samples)
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.render.bake.margin = 6
    sc.render.bake.margin_type = "EXTEND"
    sc.render.bake.use_clear = True
    sc.render.bake.target = "IMAGE_TEXTURES"
    return sc


def bake_emit(obj, build, name, size=TEXN, margin=6, float_buffer=True, colorspace=None):
    """Bake an emission shader built by build(nt) -> output socket into a new image (EMIT pass, exact values)."""
    me = obj.data
    sc = _cycles(1)
    sc.render.bake.margin = margin
    img = bpy.data.images.get(name)
    if img:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, size, size, alpha=True, float_buffer=float_buffer)
    img.colorspace_settings.name = colorspace or ("Non-Color" if float_buffer else "sRGB")
    m = bpy.data.materials.new("_bake_" + name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    nt.links.new(build(nt), em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    ti = nt.nodes.new("ShaderNodeTexImage")
    ti.image = img
    nt.nodes.active = ti
    saved = list(me.materials)
    idx = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", idx)
    me.materials.clear()
    me.materials.append(m)
    me.polygons.foreach_set("material_index", np.zeros(len(me.polygons), np.int32))
    me.update()
    K.activate(obj)
    try:
        bpy.ops.object.bake(type="EMIT", margin=margin, use_clear=True)
    except RuntimeError as e:  # GPU busy (shared with ComfyUI): retry on the CPU
        log("bake failed on GPU, retrying on CPU:", e)
        sc.cycles.device = "CPU"
        bpy.ops.object.bake(type="EMIT", margin=margin, use_clear=True)
    me.materials.clear()
    for mm in saved:
        me.materials.append(mm)
    me.polygons.foreach_set("material_index", idx)
    me.update()
    bpy.data.materials.remove(m)
    return img


def bake_ao(obj, samples=48, distance=0.12):
    """Cycles ambient-occlusion bake (0..1) for the glTF occlusion channel."""
    sc = _cycles(samples)
    if sc.world is None:
        sc.world = bpy.data.worlds.new("_bake_world")
    sc.world.light_settings.distance = distance
    img = bpy.data.images.new("_ao", TEXN, TEXN, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    m = bpy.data.materials.new("_bake_ao")
    m.use_nodes = True
    ti = m.node_tree.nodes.new("ShaderNodeTexImage")
    ti.image = img
    m.node_tree.nodes.active = ti
    me = obj.data
    saved = list(me.materials)
    me.materials.clear()
    me.materials.append(m)
    K.activate(obj)
    t = time.time()
    try:
        bpy.ops.object.bake(type="AO", margin=6, use_clear=True)
    except RuntimeError as e:
        log("AO bake failed on GPU, retrying on CPU:", e)
        sc.cycles.device = "CPU"
        bpy.ops.object.bake(type="AO", margin=6, use_clear=True)
    me.materials.clear()
    for mm in saved:
        me.materials.append(mm)
    bpy.data.materials.remove(m)
    ao = K.img_to_np(img)[..., 0].copy()
    bpy.data.images.remove(img)
    log(f"AO baked in {time.time() - t:.1f}s (median {np.median(ao):.2f})")
    return ao


def hand_islands(obj):
    """Vertex islands of the two hands (TRELLIS made each glove+fingers a separate island). Returns
    {label: vertex index array} with 1 = her left hand (+X), 2 = her right hand, and the per-hand axis data
    (wrist point, unit axis wrist->fingertips, length, knuckle fraction) used by the glove fix."""
    import bmesh
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    isl = K.islands(bm)
    bm.free()
    co = K.mesh_co(me)
    out, axes = {}, {}
    for i in isl:
        idx = np.array(i)
        c = co[idx].mean(0)
        if abs(c[0]) > 0.45 and 0.75 < c[2] < 1.0 and len(idx) > 100:
            lab = 1 if c[0] > 0 else 2
            p = co[idx]
            mu = p.mean(0)
            _, _, vt = np.linalg.svd(p - mu, full_matrices=False)
            ax = vt[0] * np.sign(vt[0][0] * (1 if lab == 1 else -1))
            t = (p - mu) @ ax
            wrist = mu + ax * t.min()
            out[lab] = idx
            axes[lab] = (wrist, ax, float(t.max() - t.min()), 0.50)
    return out, axes


def hand_joints(obj):
    """Per hand (1 = her left, 2 = her right): wrist, hand frame and the finger / thumb joint chains from the
    same mesh analysis the rig uses (kes_rig.analyse_hand), as numpy arrays."""
    import kes_rig
    co = K.mesh_co(obj.data)
    isl, _ = hand_islands(obj)
    out = {}
    for lab, side in ((1, 1), (2, -1)):
        Hd = kes_rig.analyse_hand(co, isl[lab], side)
        J = {k: np.array([v[:] for v in Hd[k]]) for k in kes_rig.FINGERS + ("thumb",)}
        J["wrist"] = np.array(Hd["wrist"][:])
        J["axis"] = np.array(Hd["frame"][0][:])
        out[lab] = J
    return out


def bake_parts(obj):
    """Per-texel part label (0 rest, 1 left hand, 2 right hand) via a baked point attribute."""
    me = obj.data
    isl, axes = hand_islands(obj)
    vals = np.zeros(len(me.vertices))
    for lab, idx in isl.items():
        vals[idx] = lab / 4.0
    at = me.attributes.get("_kes_part") or me.attributes.new("_kes_part", "FLOAT_COLOR", "POINT")
    col = np.zeros((len(me.vertices), 4))
    col[:, 0] = vals
    col[:, 3] = 1
    at.data.foreach_set("color", col.ravel())

    def build(nt):
        a = nt.nodes.new("ShaderNodeAttribute")
        a.attribute_type = "GEOMETRY"
        a.attribute_name = "_kes_part"
        return a.outputs["Color"]

    img = bake_emit(obj, build, "_part", margin=2)
    part = np.rint(K.img_to_np(img)[..., 0] * 4.0).astype(np.int32)
    bpy.data.images.remove(img)
    me.attributes.remove(me.attributes["_kes_part"])
    log(f"part labels baked: hands {sorted(isl)}; texels {[(int((part == k).sum())) for k in (1, 2)]}")
    return part, axes


def bake_face_flag(obj, attr):
    """Texel mask of the faces flagged by a FACE-domain float attribute (e.g. the new left-eye patch from stage A).
    The flag is copied to a face-corner colour attribute and baked (closest texel per face, no margin)."""
    me = obj.data
    if attr not in me.attributes:
        return np.zeros((TEXN, TEXN), bool)
    f = np.zeros(len(me.polygons), np.float32)
    me.attributes[attr].data.foreach_get("value", f)
    lt = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_total", lt)
    col = np.zeros((len(me.loops), 4), np.float32)
    col[:, 0] = np.repeat(f, lt)
    col[:, 3] = 1.0
    tmp = "_kes_flagc"
    at = me.attributes.get(tmp) or me.attributes.new(tmp, "FLOAT_COLOR", "CORNER")
    at.data.foreach_set("color", col.ravel())

    def build(nt):
        a = nt.nodes.new("ShaderNodeAttribute")
        a.attribute_type = "GEOMETRY"
        a.attribute_name = tmp
        return a.outputs["Color"]

    img = bake_emit(obj, build, "_flag", margin=0)
    m = K.img_to_np(img)[..., 0] > 0.5
    bpy.data.images.remove(img)
    me.attributes.remove(me.attributes[tmp])
    log(f"face flag {attr}: {int(m.sum())} texels")
    return m


def _geo(nt, socket):
    return nt.nodes.new("ShaderNodeNewGeometry").outputs[socket]


def _const(nt, rgb):
    r = nt.nodes.new("ShaderNodeRGB")
    r.outputs[0].default_value = (*rgb, 1.0)
    return r.outputs[0]


def bake_geometry_maps(obj):
    """Object-space position / true-normal maps (+ coverage) for texel-space editing."""
    t = time.time()
    pos = K.img_to_np(bake_emit(obj, lambda nt: _geo(nt, "Position"), "_pos"))[..., :3].copy()
    nrm = K.img_to_np(bake_emit(obj, lambda nt: _geo(nt, "True Normal"), "_nrm"))[..., :3].copy()
    cov = K.img_to_np(bake_emit(obj, lambda nt: _const(nt, (1, 1, 1)), "_cov", margin=0))[..., 0] > 0.5
    for nm in ("_pos", "_nrm", "_cov"):
        bpy.data.images.remove(bpy.data.images[nm])
    log(f"baked position/normal/coverage maps in {time.time() - t:.1f}s; coverage {cov.mean():.3f}")
    return pos, nrm, cov


# ------------------------------------------------------------------------------------------- hair-tip dye bake
TEAL_SRGB = (0.10, 0.80, 0.72)     # dyed-tip colour (sRGB); a touch lighter than the palette teal so it reads on hair
HAIR_Z_TOP = 1.452                 # dye gradient starts here on the long right side / back ...
HAIR_Z_FULL = 1.392                # ... and is full below this
HAIR_LEFT_LIFT = 0.040             # the short left side ends ~4 cm higher


def bake_hair_tips(obj, src_img, name="KES_BaseColor"):
    """Cycles bake: base colour = mix(src, teal-dyed src, mask) where
         mask = hairness(src colour) x tip(object-space position)
       hairness: blue-black texels (blue ~2x red/green in linear, dark); tip: low on the hair, from object-space Z
       with a per-side height (the long bob on her right and the back reach Z ~1.37, the short left side ~1.41).
    The dye keeps the hair's light/dark pattern (teal multiplied by the source luminance, lifted)."""
    def build(nt):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = src_img
        tex.interpolation = "Closest"
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep_c = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tex.outputs["Color"], sep_c.inputs[0])
        sep_p = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(geo.outputs["Position"], sep_p.inputs[0])

        def math(op, a, b=None, clamp=False):
            n = nt.nodes.new("ShaderNodeMath")
            n.operation = op
            n.use_clamp = clamp
            for i, v in enumerate((a, b)):
                if v is None:
                    continue
                if isinstance(v, (int, float)):
                    n.inputs[i].default_value = v
                else:
                    nt.links.new(v, n.inputs[i])
            return n.outputs[0]

        # NB: the image node outputs LINEAR values (sRGB texture decoded), so hairness is a colour RATIO test:
        # blue-black hair has blue ~2x red/green (linear); the charcoal jacket / collar is neutral (~1.0).
        r, g, b = sep_c.outputs[0], sep_c.outputs[1], sep_c.outputs[2]
        lum = math("MULTIPLY", math("ADD", math("ADD", r, g), b), 1.0 / 3.0)
        ratio = math("DIVIDE", b, math("ADD", math("MAXIMUM", r, g), 0.0015))
        h1 = math("MULTIPLY", math("SUBTRACT", ratio, 1.30), 2.5, clamp=True)
        dark = math("SUBTRACT", 1.0, math("MULTIPLY", math("SUBTRACT", lum, 0.05), 20.0, clamp=True), clamp=True)
        hairness = math("MULTIPLY", h1, dark)
        # tip height from object-space Z; the hair hangs to Z ~1.37 on her right side and at the back, ~1.415 on
        # her short left side, so the band moves up there
        x, z = sep_p.outputs[0], sep_p.outputs[2]
        side = math("MULTIPLY", math("SUBTRACT", x, 0.03), 1.0 / 0.06, clamp=True)  # 0 right/back .. 1 left
        z_top = math("ADD", HAIR_Z_TOP, math("MULTIPLY", side, HAIR_LEFT_LIFT))     # dark above
        z_full = math("ADD", HAIR_Z_FULL, math("MULTIPLY", side, HAIR_LEFT_LIFT))   # fully dyed below
        span = math("SUBTRACT", z_top, z_full)
        tip = math("DIVIDE", math("SUBTRACT", z_top, z), span)
        tip = math("MINIMUM", math("MAXIMUM", tip, 0.0), 1.0)
        tip = math("MULTIPLY", tip, math("SUBTRACT", 3.0, math("MULTIPLY", tip, 2.0)))  # smoothstep
        tip = math("MULTIPLY", tip, tip)
        # only the head/hair region (not the jacket or the jet pack)
        head = math("GREATER_THAN", z, 1.33)
        dy = math("SUBTRACT", sep_p.outputs[1], 0.01)
        radial = math("LESS_THAN", math("ADD", math("MULTIPLY", x, x), math("MULTIPLY", dy, dy)), 0.15 ** 2)
        # the navy collar lining in front of the throat has the same colour as the hair but no hair hangs there
        throat = math("MULTIPLY", math("MULTIPLY", math("LESS_THAN", sep_p.outputs[1], -0.015),
                                       math("LESS_THAN", math("ABSOLUTE", math("SUBTRACT", x, 0.005)), 0.062)),
                      math("LESS_THAN", z, 1.475))
        mask = math("MULTIPLY", math("MULTIPLY", math("MULTIPLY", hairness, tip), head), radial)
        mask = math("MULTIPLY", mask, math("SUBTRACT", 1.0, throat))
        # ... nor inside the collar funnel (its inner back wall shows through the V-opening)
        dx5 = math("SUBTRACT", x, 0.005)
        dy5 = math("SUBTRACT", sep_p.outputs[1], 0.005)
        inner = math("MULTIPLY", math("LESS_THAN", math("ADD", math("MULTIPLY", dx5, dx5), math("MULTIPLY", dy5, dy5)),
                                      0.078 ** 2), math("LESS_THAN", z, 1.475))
        mask = math("MULTIPLY", mask, math("SUBTRACT", 1.0, inner))
        # dyed colour: teal x (0.35 + 1.6 * source luminance) keeps the strand pattern
        shade = math("ADD", 0.32, math("MULTIPLY", lum, 8.0))
        shade = math("MINIMUM", shade, 1.0)
        teal = nt.nodes.new("ShaderNodeRGB")
        lin = [((c + 0.055) / 1.055) ** 2.4 for c in TEAL_SRGB]
        teal.outputs[0].default_value = (*lin, 1.0)
        dyed = nt.nodes.new("ShaderNodeMix")
        dyed.data_type = "RGBA"
        dyed.blend_type = "MULTIPLY"
        dyed.inputs[0].default_value = 1.0
        nt.links.new(teal.outputs[0], dyed.inputs[6])
        cs = nt.nodes.new("ShaderNodeCombineColor")
        for i in range(3):
            nt.links.new(shade, cs.inputs[i])
        nt.links.new(cs.outputs[0], dyed.inputs[7])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(mask, mix.inputs[0])
        nt.links.new(tex.outputs["Color"], mix.inputs[6])
        nt.links.new(dyed.outputs[2], mix.inputs[7])
        return mix.outputs[2]

    img = bake_emit(obj, build, name, float_buffer=False, colorspace="sRGB", margin=8)
    return img


# ================================================================================================ STAGE B driver
def srgb_to_lin(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def stage_b_textures(obj):
    """Face repaint, normal/AO flattening where the paint changed, misc fixes, then the Cycles hair-tip dye bake.
    Leaves images KES_BaseColor (sRGB), KES_Normal and KES_ORM (non-colour) packed in the file and saved to
    textures/."""
    pos, nrm, cov = bake_geometry_maps(obj)
    patch = bake_face_flag(obj, "_kes_patch")      # the rebuilt left-eye area (stage A): new UV islands, no paint yet
    base = K.img_to_np(K.base_image())
    t = time.time()
    C, dbg = kes_face.repaint_face(pos, nrm, base[..., :3].astype(np.float64), cov, patch=patch)
    log(f"face repainted in {time.time() - t:.1f}s")
    import kes_fix
    part, axes = bake_parts(obj)
    hands = hand_joints(obj)
    C, emit = kes_fix.misc_fixes(pos, nrm, C, cov, part, axes, hands=hands, log=log)
    em = np.zeros(C.shape[:2] + (4,))
    em[..., :3] = emit[..., None] * np.array(kes_fix.TEAL)
    em[..., 3] = 1.0
    # normal map + AO: flatten where the paint was replaced (the TRELLIS maps carry the old lens rim / strap)
    fw = dbg["flat_w"][..., None]
    nm = K.img_to_np(bpy.data.images["KES_Normal_src"]).copy()
    nm[..., :3] = nm[..., :3] * (1 - fw) + np.array([0.5, 0.5, 1.0]) * fw
    # review round 2: the TRELLIS normal map is noisy - 5 % of the texels tilt more than 53 deg (worst along chart
    # borders), which rendered as rows of dark dots along the jaw, cheeks and forehead. The face / neck skin gets a
    # flat normal (painted, stylized skin) and everywhere else the tilt is clamped to 35 deg (directions kept).
    v = nm[..., :3].astype(np.float64) * 2.0 - 1.0
    v /= np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-6)
    nz_min = 0.82
    xy = np.linalg.norm(v[..., :2], axis=-1, keepdims=True)
    steep = v[..., 2:3] < nz_min
    v_cl = np.concatenate([v[..., :2] / np.maximum(xy, 1e-6) * np.sqrt(1 - nz_min ** 2),
                           np.full(xy.shape, nz_min)], -1)
    v = np.where(steep, v_cl, v)
    skin_face = cov & (pos[..., 2] > 1.38) & (np.abs(pos[..., 0]) < 0.13) & kes_face.skin_mask(C)
    for _ in range(2):                      # + a 2-texel rim so the border texels of the skin charts go flat too
        skin_face = skin_face | (np.roll(skin_face, 1, 0) & cov) | (np.roll(skin_face, -1, 0) & cov) | \
            (np.roll(skin_face, 1, 1) & cov) | (np.roll(skin_face, -1, 1) & cov)
    v[skin_face] = (0.0, 0.0, 1.0)
    nm[..., :3] = (v * 0.5 + 0.5).astype(nm.dtype)
    log(f"normal map: {int((steep[..., 0] & cov).sum())} steep texels clamped to 35 deg, "
        f"{int(skin_face.sum())} face/neck skin texels flat")
    orm = K.img_to_np(bpy.data.images["KES_ORM_src"]).copy()
    # the patch texels sit in formerly unused atlas space: give them the face skin's roughness / metalness
    skin_t = cov & ~patch & (pos[..., 2] > 1.44) & (pos[..., 1] < -0.04) & kes_face.skin_mask(C)
    pd = patch.copy()                               # + the 2-texel gutter that bilinear filtering reaches
    for _ in range(2):
        pd = pd | np.roll(pd, 1, 0) | np.roll(pd, -1, 0) | np.roll(pd, 1, 1) | np.roll(pd, -1, 1)
    pd &= ~cov | patch
    if skin_t.any():
        orm[pd, 1] = np.median(orm[skin_t, 1])
        orm[pd, 2] = np.median(orm[skin_t, 2])
    nm[pd, :3] = (0.5, 0.5, 1.0)
    em[pd] = (0.0, 0.0, 0.0, 1.0)
    img_e = K.np_to_img("KES_Emission", em)
    # TRELLIS's R channel is not occlusion (per-chart black/white blobs): replace it with a real AO bake
    ao = bake_ao(obj)
    orm[..., 0] = np.where(cov, 0.30 + 0.70 * ao, 1.0)
    img_n = K.np_to_img("KES_Normal", nm, colorspace="Non-Color")
    img_o = K.np_to_img("KES_ORM", orm, colorspace="Non-Color")
    # hair-tip dye: Cycles bake of mix(base, teal, hairness x tip) into a new image on the same UVs
    src = K.np_to_img("_base_fixed", np.concatenate([C, np.ones(C.shape[:2] + (1,))], -1))
    t = time.time()
    baked = bake_hair_tips(obj, src, "_base_baked")
    B = K.img_to_np(baked)[..., :3]
    # keep the source texels outside the baked coverage (the TRELLIS gutter padding helps mip-mapping)
    covd = cov.copy()
    for _ in range(2):
        covd = covd | np.roll(covd, 1, 0) | np.roll(covd, -1, 0) | np.roll(covd, 1, 1) | np.roll(covd, -1, 1)
    final = np.where(covd[..., None], B, C)
    diff = np.abs(B - C)[cov].max(-1)
    log(f"hair-tip bake {time.time() - t:.1f}s: {np.mean(diff > 0.02) * 100:.2f}% of texels dyed "
        f"(round-trip error elsewhere {np.median(diff):.4f})")
    img_b = K.np_to_img("KES_BaseColor", np.concatenate([final, np.ones(final.shape[:2] + (1,))], -1))
    for im in (src, baked):
        bpy.data.images.remove(im)
    os.makedirs(K.TEX, exist_ok=True)
    for im, nm_ in ((img_b, "KES_BaseColor.png"), (img_n, "KES_Normal.png"), (img_o, "KES_ORM.png"),
                    (img_e, "KES_Emission.png")):
        K.save_png(im, os.path.join(K.TEX, nm_))
        im.pack()
    return img_b, img_n, img_o, img_e


# ================================================================================================== material
def make_body_material(obj, img_b, img_n, img_o, img_e=None, emit_strength=4.0):
    """M_KES_Body: one glTF-friendly Principled material. Base colour = fixed atlas; roughness / metallic / AO from
    the TRELLIS ORM (G / B / R) with roughness lifted for a painted, non-plastic look; TRELLIS normal map."""
    mat = bpy.data.materials.get("M_KES_Body") or bpy.data.materials.new("M_KES_Body")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    tb = nt.nodes.new("ShaderNodeTexImage")
    tb.image = img_b
    nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
    to = nt.nodes.new("ShaderNodeTexImage")
    to.image = img_o
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(to.outputs["Color"], sep.inputs[0])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = img_n
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = 1.0
    nt.links.new(tn.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    # glTF occlusion: the exporter reads it from a "glTF Material Output" group node
    grp = bpy.data.node_groups.get("glTF Material Output")
    if grp is None:
        grp = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        grp.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    gn = nt.nodes.new("ShaderNodeGroup")
    gn.node_tree = grp
    sep2 = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(to.outputs["Color"], sep2.inputs[0])
    nt.links.new(sep2.outputs["Red"], gn.inputs["Occlusion"])
    if img_e is not None:
        te = nt.nodes.new("ShaderNodeTexImage")
        te.image = img_e
        nt.links.new(te.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit_strength
    bc._set_input(bsdf, ["Specular IOR Level", "Specular"], 0.35)
    me = obj.data
    me.materials.clear()
    me.materials.append(mat)
    return mat
