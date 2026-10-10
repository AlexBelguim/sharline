"""Preview renders for the MAKO build (called from build_mako.py; Cycles, ~48 samples)."""
import math
import os
import subprocess
import sys

import bpy
from mathutils import Vector

SOURCE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(SOURCE, "..", "..", ".."))
sys.path.insert(0, os.path.join(PROJECT, "tools"))
import blender_common as bc  # noqa: E402

HERE = os.environ.get("MAKO_OUT", SOURCE)
RD = os.environ.get("MAKO_RD") or os.path.join(HERE, "renders")   # MAKO_RD: iteration renders elsewhere
ITER = os.path.join(HERE, "_work", "iter")
BG = tuple(float(v) for v in os.environ.get("MAKO_BG", "0.55,0.55,0.55").split(","))
LIGHT = float(os.environ.get("MAKO_LIGHT", "0.28"))   # studio light strength (presentation only)
WORLD = float(os.environ.get("MAKO_WORLD", "0.90"))   # world (background) light strength
VT = os.environ.get("MAKO_VT", "Standard")
LOOK = os.environ.get("MAKO_LOOK", "None")
EXPO = float(os.environ.get("MAKO_EXPO", "0.0"))

# camera direction that matches the master concept v09 (gun's left/+X side, muzzle toward camera-left)
V09_DIR = (0.72, -0.45, 0.52)   # best silhouette IoU vs v09 over 60 candidates (_work/try_views.py)
V09_FOCUS = ((0.0, -0.16, -0.03), 0.45)  # v09 includes the optic, so its centre sits a little higher


FORCE_HIDE = set()   # object names kept hidden whatever the shot (mag-check states)


def show_only(objs):
    keep = {o.name for o in objs} - FORCE_HIDE
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = o.name not in keep


def shoot(objs, prefix, views, res, samples, focus=None, ortho=False, lens=85, margin=1.08):
    """views: names from bc.VIEW_DIRS or (name, direction) pairs. Writes {prefix}_{name}.png."""
    show_only(objs)
    paths = []
    for v in views:
        name, d = (v, bc.VIEW_DIRS[v]) if isinstance(v, str) else v
        if name == "top":
            d = (0.0005, 0.0, 1.0)  # straight down, rolled so the bore runs left-right (muzzle left)
        p = bc.render_views(RD, "_tmp", objs=objs, views=(tuple(d),), res=res, engine="CYCLES", samples=samples,
                            lens=lens, margin=margin, ortho=ortho, focus=focus)[0]
        out_dir = ITER if prefix.startswith("iter") else RD   # iteration-only renders stay out of renders/
        os.makedirs(out_dir, exist_ok=True)
        dst = os.path.join(out_dir, f"{prefix}_{name}.png")
        os.replace(p, dst)
        paths.append(dst)
    return paths


def mag_fill(objs, rounds):
    """Hide the mag-check cartridges a magazine holding `rounds` would not show (min_rounds custom property)."""
    for o in objs:
        if o.type == "MESH" and "min_rounds" in o.keys():
            if rounds < o["min_rounds"]:
                FORCE_HIDE.add(o.name)
            else:
                FORCE_HIDE.discard(o.name)


def clay(on):
    """Neutral clay override (shading check: bevels, hardened normals, no texture noise)."""
    vl = bpy.context.view_layer
    if not on:
        vl.material_override = None
        return
    m = bpy.data.materials.get("_Clay") or bpy.data.materials.new("_Clay")
    m.use_nodes = True
    pr = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    pr.inputs["Base Color"].default_value = (0.62, 0.62, 0.62, 1.0)
    pr.inputs["Roughness"].default_value = 0.45
    pr.inputs["Metallic"].default_value = 0.0
    vl.material_override = m


def review_fix_renders(default, base_m, po, R, smp):
    """Close-ups that verify the r2 review fixes (renders/fix_*.png). Camera directions match the review's."""
    out = []
    ch = bpy.data.objects["MAKO_ChargingHandle"]
    dc = bpy.data.objects["MAKO_DustCover"]
    stroke = ch.get("stroke_m", 0.05)
    res = R(1500, 1000)
    # 1. shading of the receiver after the bevel (bake_clean regression): clay, same angles as the review
    clay(True)
    out += shoot(default, "fix_clay_receiver", (("3q", (0.8, -0.7, 0.35)), ("plusX", (1.0, -0.1, 0.15)),
                                                 ("minusX", (-1.0, -0.1, 0.15))),
                 res, smp, focus=((0, -0.06, 0.0), 0.12))
    out += shoot(default, "fix_clay_magwell", (("front_low", (0.6, -0.9, -0.35)),), res, smp,
                 focus=((0, -0.13, -0.03), 0.06))
    out += shoot(default, "fix_clay_rear", (("minusX", (-0.75, 0.85, 0.55)),), res, smp,
                 focus=((0.0, 0.035, 0.058), 0.040))
    clay(False)
    # 2. player-facing receiver (+X): shoulder pad, swept rear contour, bolt-catch paddle, magwell, mag window
    out += shoot(default, "fix_receiver", (("plusX", (1.0, -0.1, 0.15)), ("minusX", (-1.0, -0.1, 0.15)),
                                           ("v09", (0.72, -0.45, 0.52))), res, smp,
                 focus=((0, -0.07, 0.01), 0.11))
    # 3. charging handle / forward assist / castle nut: at rest and fully pulled (dust cover open)
    rear = ((0.0, 0.035, 0.058), 0.042)
    out += shoot(default, "fix_rear", (("rest_minusX", (-0.75, 0.85, 0.55)), ("rest_top", (0.001, 0.25, 1.0))),
                 R(1200, 900), smp, focus=rear)
    ch.location.y += stroke
    dc.rotation_euler.y = math.radians(-100)
    bpy.context.view_layer.update()
    out += shoot(default, "fix_rear", (("pulled_minusX", (-0.75, 0.85, 0.55)),), R(1200, 900), smp, focus=rear)
    out += shoot(default, "fix_motion", (("ch_pulled_dc_open", (-0.8, 0.6, 0.45)),), R(1200, 900), smp,
                 focus=((0.0, 0.0, 0.05), 0.09))
    ch.location.y -= stroke
    dc.rotation_euler.y = 0.0
    bpy.context.view_layer.update()
    # 4. stock_standard fully collapsed with the CH pulled as far as the stock allows (engine clamp)
    st = po("stock_standard")[0]
    lim = list(st.get("ch_stroke_max_m", [stroke] * 4))
    trav = list(st.get("travel_positions_m", [0.0, 0.0145, 0.029, 0.0435]))
    loc = st.location.copy()
    st.location.y -= trav[-1]
    ch.location.y += lim[-1]
    bpy.context.view_layer.update()
    out += shoot(default, "fix_stock_collapsed", (("ch_clamped_minusX", (-0.6, 0.8, 0.45)),), R(1200, 900), smp,
                 focus=((0.0, 0.06, 0.05), 0.07))
    out += shoot(default, "fix_stock_collapsed", ("right",), R(1600, 700), smp, margin=1.02)
    st.location = loc
    ch.location.y -= lim[-1]
    bpy.context.view_layer.update()
    # 5. precision cheek comb seated on the stock
    prec = base_m + po("stock_precision") + po("mag_30")
    out += shoot(prec, "fix_precision", (("cheek", (0.8, 0.3, 0.35)), ("cheek_rear", (-0.4, 1.0, 0.35)),
                                         ("side", (1.0, 0.0, 0.02))), R(1200, 900), smp,
                 focus=((0, 0.165, 0.045), 0.105))
    # 6. magazine window + per-round mag-check states
    m30 = po("mag_30")
    out += shoot(m30, "fix_mag30_30rounds", (("window_plusX", (1.0, -0.05, -0.05)),), R(900, 1100), smp,
                 margin=1.05)
    for n in (20, 10, 3):
        mag_fill(m30, n)
        out += shoot(m30, f"fix_mag30_{n}rounds", (("window_plusX", (1.0, -0.05, -0.05)),), R(900, 1100), smp,
                     margin=1.05)
    mag_fill(m30, 99)
    out += shoot(default, "fix_magwell", (("front_low", (0.6, -0.9, -0.35)),), R(1200, 900), smp,
                 focus=((0, -0.13, -0.03), 0.06))
    # 7. drum windows both sides, handguard slots, flash hider slots
    drum = po("mag_drum60")
    out += shoot(drum, "fix_drum", (("plusX", (1.0, 0.05, 0.0)), ("minusX", (-1.0, 0.05, 0.0))), R(900, 1000), smp,
                 margin=1.05)
    out += shoot(default, "fix_handguard", (("slots_plusX", (1.0, -0.25, -0.30)), ("slots_3q", (0.8, -0.6, 0.3))),
                 R(1400, 900), smp, focus=((0, -0.36, 0.045), 0.09))
    out += shoot(default, "fix_muzzle", (("3q", (0.7, -0.8, 0.3)),), R(1100, 900), smp,
                 focus=((0, -0.54, 0.05), 0.035))
    # 8. r3: first-person angle (handguard rear bulkhead closes the joint), stock fronts (key slot floor)
    out += shoot(default, "fix_fp", (("hip", (0.30, 1.0, 0.28)), ("reload", (0.75, 0.45, 0.10))), R(1600, 900), smp,
                 lens=35, focus=((0, -0.12, 0.03), 0.20))
    out += shoot(po("stock_standard"), "fix_stock_standard", (("front", (0.35, -1.0, 0.35)),), R(1000, 900), smp,
                 margin=1.05)
    out += shoot(po("stock_light"), "fix_stock_light", (("front", (0.3, -1.0, 0.1)),), R(1000, 900), smp,
                 margin=1.05)
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = False
    return out


def review2_renders(default, R, smp):
    """Round-2 verification renders (renders/fix2_*.png, contact_sheet_review_fixes_r2.png): real per-edge bevels
    in clay on every major part, the grip's finger knuckle and beavertail, the chunky sling swivel, the flared
    magazine, the drum's primed case heads."""
    O = bpy.data.objects
    out = []

    def part(n):
        m = O[n]
        return [m] + [c for c in m.children_recursive if c.type == "MESH"]
    clay(True)
    for n in ("MAKO_Upper", "MAKO_Lower", "MAKO_Handguard", "MAKO_stock_standard", "MAKO_stock_precision",
              "MAKO_stock_light", "MAKO_mag_30", "MAKO_mag_drum60"):
        out += shoot(part(n), f"fix2_bevel_{n[5:]}", (("3q", (0.8, -0.7, 0.45)),), R(1000, 750), smp, margin=1.05)
    out += shoot(default, "fix2_bevel_receiver", (("minusX", (-1.0, -0.1, 0.15)),), R(1500, 1000), smp,
                 focus=((0, -0.06, 0.02), 0.08))
    clay(False)
    out += shoot(default, "fix2_grip", (("plusX_ortho", (1.0, 0.0, 0.0)),), R(1000, 1000), smp, ortho=True,
                 focus=((0, 0.015, -0.05), 0.075))
    out += shoot(default, "fix2_grip", (("v09", V09_DIR),), R(1000, 1000), smp, focus=((0, 0.01, -0.05), 0.07))
    out += shoot(part("MAKO_stock_standard"), "fix2_sling", (("3q", (0.8, -0.4, -0.35)),), R(1000, 800), smp,
                 focus=((0, 0.20, -0.025), 0.035))
    out += shoot(default, "fix2_mag_flare", (("plusX", (1.0, 0.0, 0.0)),), R(1000, 1000), smp, ortho=True,
                 focus=((0, -0.125, -0.085), 0.10))
    out += shoot(part("MAKO_mag_drum60"), "fix2_drum_window", (("minusX", (-1.0, 0.05, 0.0)),), R(1000, 1000), smp,
                 focus=((0, -0.121, -0.093), 0.04))
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = False
    return out


def run(flag, base, parts, sock_objs, root):
    os.makedirs(RD, exist_ok=True)
    quick = bool(flag.get("--quick"))
    groups = (flag.get("--renders") or "main,closeups,stocks,mags,fixes,compare").split(",")
    smp = 16 if quick else 48
    k = 0.6 if quick else 1.0

    def R(w, h):
        return (int(w * k), int(h * k))

    bc.setup_studio(bg=BG, strength=LIGHT)
    # presentation only: keep the lights near neutral so the bone furniture keeps its warm tint
    for nm, colr in (("L_Key", (1.0, 0.97, 0.93)), ("L_Fill", (0.97, 0.97, 1.0)), ("L_Rim", (0.95, 0.97, 1.0)),
                     ("L_RimL", (1.0, 0.95, 0.92))):
        lo = bpy.data.objects.get(nm)
        if lo:
            lo.data.color = colr
    w = bpy.context.scene.world
    bgn = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bgn.inputs[1].default_value = WORLD
    vs = bpy.context.scene.view_settings
    try:
        vs.view_transform = VT
        vs.look = LOOK
    except TypeError as e:
        print("view transform", e)
    vs.exposure = EXPO
    base_m = [o for o in base if o.type == "MESH"]

    def po(key):
        m, kids = parts[key]
        return [m] + list(kids)

    default = base_m + po("stock_standard") + po("mag_30")
    out = {}
    FB = ((0.0, -0.02, -0.040), 0.150)   # front/back framing: the cross-section, long lens from outside the gun
    if "main" in groups:
        out["main"] = []
        out["main"] += shoot(default, "mako_default", ("right", "left"), R(1800, 760), smp, margin=1.02)
        out["main"] += shoot(default, "mako_default", ("three_quarter", "three_quarter_back", "low"),
                             R(1500, 1000), smp, margin=1.0)
        out["main"] += shoot(default, "mako_default", (("front", (0, -1, 0)), ("back", (0, 1, 0))), R(900, 900), smp,
                             ortho=True, margin=1.12,
                             focus=FB)
        out["main"] += shoot(default, "mako_default", ("top",), R(1800, 600), smp, margin=1.02)
        out["main"] += shoot(default, "mako_default_ortho", ("right", "left"), R(1800, 760), smp, ortho=True,
                             margin=1.0)
    if "closeups" in groups:
        out["closeups"] = []
        out["closeups"] += shoot(default, "close_receiver", ("right", "left", ("v09", V09_DIR),
                                                              ("front_right", (-0.8, -0.9, 0.45))), R(1300, 1000),
                                 smp, focus=((0, -0.055, 0.0), 0.115))
        out["closeups"] += shoot(default, "close_handguard", (("v09", V09_DIR), ("under", (0.9, -0.35, -0.35))),
                                 R(1300, 1000), smp, focus=((0, -0.36, 0.045), 0.10))
        out["closeups"] += shoot(default, "close_muzzle", ("three_quarter", "right", ("front", (0.25, -1, 0.2))),
                                 R(1100, 900), smp, focus=((0, -0.525, 0.050), 0.045))
        out["closeups"] += shoot(default, "close_stock", ("right", ("rear", (0.6, 0.9, 0.3))), R(1100, 900), smp,
                                 focus=((0, 0.19, 0.01), 0.10))
        out["closeups"] += shoot(default, "close_mag", ("right", ("front", (1.0, -0.4, -0.1))), R(1000, 1000), smp,
                                 focus=((0, -0.125, -0.085), 0.085))
    if "stocks" in groups:
        out["stocks"] = []
        for key in ("stock_standard", "stock_precision", "stock_light"):
            out["stocks"] += shoot(base_m + po(key) + po("mag_30"), f"ongun_{key}", ("right",), R(1600, 700),
                                   smp, margin=1.02)
            out["stocks"] += shoot(po(key), f"part_{key}", ("right", "three_quarter", "three_quarter_back"),
                                   R(1000, 900), smp, margin=1.05)
    if "mags" in groups:
        out["mags"] = []
        for key in ("mag_30", "mag_45", "mag_drum60"):
            out["mags"] += shoot(base_m + po("stock_standard") + po(key), f"ongun_{key}", ("right",),
                                 R(1600, 800), smp, margin=1.02)
            out["mags"] += shoot(po(key), f"part_{key}", ("right", "three_quarter", "left"), R(900, 1000), smp,
                                 margin=1.05)
    if "side" in groups:
        out["side"] = shoot(default, "iter_side", ("right", "left"), R(1800, 760), smp, ortho=True, margin=1.0)
        out["side"] += shoot(default, "iter", ("three_quarter",), R(1500, 1000), smp, margin=1.0)
    if "iterc" in groups:
        out["iterc"] = shoot(default, "iterc_recv", ("right", "left", ("v09", V09_DIR),
                                                      ("front_right", (-0.8, -0.9, 0.45))), R(1300, 1000),
                             smp, focus=((0, -0.05, -0.005), 0.12))
    if "fixes" in groups:
        out["fixes"] = review_fix_renders(default, base_m, po, R, smp)
        out["fixes"] += review2_renders(default, R, smp)
    if "compare" in groups:
        out["compare"] = []
        out["compare"] += shoot(default, "cmp", (("v09", V09_DIR),), R(1536, 896), smp, lens=50, margin=1.04,
                                focus=V09_FOCUS)
        out["compare"] += shoot(default, "cmp_side_ortho", ("right",), R(1536, 768), smp, ortho=True,
                                margin=1.0)
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = False
    # contact sheets + comparison (system python with PIL)
    try:
        subprocess.run(["python", os.path.join(SOURCE, "make_sheets.py"), "--out", HERE], check=True)
    except Exception as e:  # noqa: BLE001
        print("sheet step failed", e)
    return out
