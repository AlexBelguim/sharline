"""Review pass 2 renders for KESTREL (read-only on the asset; writes only to review/renders/rv2_*).

blender -b --factory-startup -P rv2_render.py -- <set> [<set> ...]
sets: halo, lens, clay, sprint, compare
"""
import math
import sys

sys.dont_write_bytecode = True
_sets = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["lens"]
sys.argv = [sys.argv[0], "--", "none"]
exec(open(r"F:/git/val etf/assets/characters/kestrel/review/render_review.py", encoding="utf-8").read().split("FN = {")[0])
SETS2 = _sets
OUT2 = OUT + "rv2_"
CONCEPT = r"F:/git/val etf/art/concepts/kestrel/"


def import_halo():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=r"F:/git/val etf/assets/shields/export/HALO_Bulwark.glb")
    new = [o for o in bpy.data.objects if o not in before]
    P("halo objects", sorted(o.name for o in new)[:40])
    keep = [o for o in new if o.type == "MESH" and ("Arc" in o.name or "Band_Medium" in o.name)]
    for o in new:
        if o not in keep and o.type == "MESH":
            o.hide_render = True
    holder = bpy.data.objects.new("_halo_holder", None)
    bpy.context.scene.collection.objects.link(holder)
    for o in keep:
        mw = o.matrix_world.copy()
        o.parent = holder
        o.matrix_world = mw
    return holder, keep


def place_halo(holder):
    s = bpy.data.objects["KES_SOCKET_Halo"]
    bpy.context.view_layer.update()
    holder.matrix_world = Matrix.Translation(s.matrix_world.translation)  # position only, stays level
    bpy.context.view_layer.update()


def set_halo(sc, arm, body, ep):
    """Halo attached at KES_SOCKET_Halo (position only) at rest, head pitched down 30 deg and head turned 45 deg."""
    bc.setup_studio(floor=True)
    holder, keep = import_halo()
    paths = []
    for nm, fn in (("rest", None),
                   ("head_down30", lambda: (rot_world(arm, "neck_01", (1, 0, 0), 10), rot_world(arm, "head", (1, 0, 0), 20))),
                   ("head_up25", lambda: (rot_world(arm, "neck_01", (1, 0, 0), -8), rot_world(arm, "head", (1, 0, 0), -17))),
                   ("rifle_spine", lambda: pose_rifle(arm))):
        reset(arm)
        if fn:
            fn()
        place_halo(holder)
        top = arm.matrix_world @ arm.pose.bones["head"].tail
        hp = holder.matrix_world.translation
        P(f"halo {nm}: socket {tuple(round(v, 3) for v in hp)}, skull-top {tuple(round(v, 3) for v in top)}, "
          f"horizontal offset from skull top {math.hypot(hp.x - top.x, hp.y - top.y) * 100:.1f} cm, height above {(hp.z - top.z) * 100:.1f} cm")
        camera((0.0, 0.0, 1.62), (1.0, -0.15, 0.12), radius=0.42, lens=85)
        paths.append(render(OUT2 + f"halo_side_{nm}.png", res=(800, 800), samples=48))
    reset(arm)
    place_halo(holder)
    camera((0.0, 0.02, 1.55), (-0.35, 1, 0.55), radius=0.55, lens=50)
    paths.append(render(OUT2 + "halo_tpcam_rest.png", res=(800, 800), samples=48))
    camera((0.0, 0.0, 1.0), (0.6, -1, 0.15), radius=1.15, lens=85)
    paths.append(render(OUT2 + "halo_full_34.png", res=(800, 800), samples=48))
    bc.contact_sheet(paths, OUT2 + "halo_sheet.png", cols=3)


def set_lens(sc, arm, body, ep):
    """Orthographic front of the face with and without the eyepiece, to measure lens coverage vs brow/cheek."""
    bc.setup_studio()
    paths = []
    for nm, hide in (("with", False), ("without", True)):
        ep.hide_render = hide
        camera((0.0, -0.05, 1.515), (0, -1, 0), ortho_scale=0.24, lens=85)
        paths.append(render(OUT2 + f"lens_front_ortho_{nm}.png", res=(900, 900), samples=48))
    ep.hide_render = False
    # her left profile, ortho, to see the lens stand-off
    camera((0.03, -0.05, 1.515), (1, 0, 0), ortho_scale=0.24, lens=85)
    paths.append(render(OUT2 + "lens_side_ortho.png", res=(900, 900), samples=48))
    bc.contact_sheet(paths, OUT2 + "lens_sheet.png", cols=3)
    # measure: lens frame z/x extents vs. the eye
    dg = bpy.context.evaluated_depsgraph_get()
    import bmesh
    for mi, slot in enumerate(ep.material_slots):
        vs = [ep.matrix_world @ v.co for p in ep.data.polygons if p.material_index == mi for v in [ep.data.vertices[i] for i in p.vertices]]
        if vs:
            xs = [v.x for v in vs]; zs = [v.z for v in vs]; ys = [v.y for v in vs]
            P(f"eyepiece {slot.material.name}: x {min(xs):.4f}..{max(xs):.4f}  y {min(ys):.4f}..{max(ys):.4f}  z {min(zs):.4f}..{max(zs):.4f}")


def _clay():
    m = bpy.data.materials.new("_clay")
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.55, 0.55, 0.57, 1)
    b.inputs["Roughness"].default_value = 0.6
    return m


def set_clay(sc, arm, body, ep):
    """Untextured clay: judge the face/hand/hair geometry on its own."""
    bc.setup_studio()
    sc.view_layers[0].material_override = _clay()
    paths = []
    for nm, c, d, r in (("face_front", (0.0, -0.04, 1.53), (0.05, -1, 0.05), 0.12),
                        ("face_34_her_right", (-0.02, -0.03, 1.53), (-0.7, -1, 0.1), 0.12),
                        ("hand_r", (-0.56, -0.04, 0.86), (0.3, -0.6, 0.6), 0.08),
                        ("torso_front", (0.0, -0.05, 1.2), (0.15, -1, 0.1), 0.3)):
        camera(c, d, radius=r, lens=85)
        paths.append(render(OUT2 + f"clay_{nm}.png", res=(800, 800), samples=32))
    sc.view_layers[0].material_override = None
    bc.contact_sheet(paths, OUT2 + "clay_sheet.png", cols=4)


def pose_sprint(arm):
    """Sprint stride: left knee high (thigh 70 deg forward), right leg extended back, arms swinging."""
    aim(arm, "thigh_l", (0.08, -1.0, -0.35))
    aim(arm, "calf_l", (0.05, 0.25, -1.0))
    aim(arm, "thigh_r", (-0.08, 0.45, -1.0))
    aim(arm, "calf_r", (-0.05, 0.9, -0.6))
    aim(arm, "upperarm_l", (0.15, 0.45, -1.0))
    aim(arm, "lowerarm_l", (0.1, -0.3, -1.0))
    aim(arm, "upperarm_r", (-0.15, -0.6, -1.0))
    aim(arm, "lowerarm_r", (-0.1, -1.0, 0.3))
    rot_world(arm, "spine_01", (1, 0, 0), 8)


def set_sprint(sc, arm, body, ep):
    bc.setup_studio(floor=True)
    reset(arm)
    pose_sprint(arm)
    drop_to_floor(arm, [body, ep])
    paths = []
    for nm, c, d, r in (("full_her_left", None, (1, -0.25, 0.1), 1.0),
                        ("pouch_l", "thigh_l", (0.8, -0.8, 0.2), 0.2),
                        ("hip_front", "pelvis", (0.2, -1, 0.1), 0.3),
                        ("holster_r", "thigh_r", (-1, -0.4, 0.1), 0.22)):
        if c is None:
            mn, mx = bc.world_bounds([body, ep])
            cc = (mn + mx) / 2
        else:
            cc = arm.matrix_world @ arm.pose.bones[c].head
        camera(cc, d, radius=r, lens=85)
        paths.append(render(OUT2 + f"sprint_{nm}.png", res=(800, 800), samples=48))
    reset(arm)
    bc.contact_sheet(paths, OUT2 + "sprint_sheet.png", cols=4)


def set_compare(sc, arm, body, ep):
    """Same-size renders next to the concept images (v06 head, front_apose full body)."""
    bc.setup_studio()
    p_head = render_at(OUT2 + "cmp_head_v06_angle.png", (0.0, -0.03, 1.52), (-0.35, -1, 0.05), 0.15, (1024, 1024))
    bc.contact_sheet([CONCEPT + "v06.png", p_head], OUT2 + "cmp_head_vs_v06.png", cols=2)
    p_full = render_at(OUT2 + "cmp_full_apose_angle.png", (0.0, 0.0, 0.88), (-0.25, -1, 0.05), 0.98, (1024, 1280))
    bc.contact_sheet([CONCEPT + "ref_sheet/front_apose.png", p_full], OUT2 + "cmp_full_vs_front_apose.png", cols=2)


def render_at(path, c, d, r, res):
    camera(c, d, radius=r, lens=85)
    return render(path, res=res, samples=64)


FN2 = {"halo": set_halo, "lens": set_lens, "clay": set_clay, "sprint": set_sprint, "compare": set_compare}
for s in SETS2:
    sc, arm, body, ep = load()
    FN2[s](sc, arm, body, ep)
P("done", SETS2)
