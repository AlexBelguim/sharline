"""Preview renders for the MAKO build (called from build_mako.py; Cycles, ~48 samples)."""
import os
import subprocess
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, r"F:/git/val etf/tools")
import blender_common as bc  # noqa: E402

HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
RD = os.path.join(HERE, "renders")
BG = (0.40, 0.40, 0.40)

# camera direction that matches the master concept v09 (gun's left/+X side, muzzle toward camera-left)
V09_DIR = (0.80, -0.52, 0.38)


def show_only(objs):
    keep = {o.name for o in objs}
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = o.name not in keep


def shoot(objs, prefix, views, res, samples, focus=None, ortho=False, lens=85, margin=1.08):
    show_only(objs)
    return bc.render_views(RD, prefix, objs=objs, views=views, res=res, engine="CYCLES", samples=samples,
                           lens=lens, margin=margin, ortho=ortho, focus=focus)


def run(flag, base, parts, sock_objs, root):
    os.makedirs(RD, exist_ok=True)
    quick = bool(flag.get("--quick"))
    groups = (flag.get("--renders") or "main,closeups,stocks,mags,compare").split(",")
    smp = 16 if quick else 48
    k = 0.6 if quick else 1.0

    def R(w, h):
        return (int(w * k), int(h * k))

    bc.setup_studio(bg=BG, strength=0.8)
    # presentation only: keep fill/rim close to neutral so the bone furniture keeps its warm tint
    for nm, colr in (("L_Fill", (0.96, 0.96, 1.0)), ("L_Rim", (0.92, 0.95, 1.0))):
        lo = bpy.data.objects.get(nm)
        if lo:
            lo.data.color = colr
    base_m = [o for o in base if o.type == "MESH"]

    def po(key):
        m, kids = parts[key]
        return [m] + list(kids)

    default = base_m + po("stock_standard") + po("mag_30")
    out = {}
    if "main" in groups:
        out["main"] = []
        out["main"] += shoot(default, "mako_default", ("right", "left"), R(1800, 760), smp, margin=1.02)
        out["main"] += shoot(default, "mako_default", ("three_quarter", "three_quarter_back", "low"),
                             R(1500, 1000), smp, margin=1.0)
        if not quick:
            out["main"] += shoot(default, "mako_default", ("front", "back"), R(900, 900), smp, margin=0.30,
                                 focus=((0, 0.0, -0.03), 0.17))
            out["main"] += shoot(default, "mako_default", ("top",), R(1800, 600), smp, margin=1.02)
    if "closeups" in groups:
        out["closeups"] = []
        out["closeups"] += shoot(default, "close_receiver", ("right", "left", "three_quarter",
                                                              (-0.8, -0.9, 0.45)), R(1300, 1000), smp,
                                 focus=((0, -0.055, 0.005), 0.115))
        out["closeups"] += shoot(default, "close_handguard", ("three_quarter", (0.9, -0.35, -0.35)),
                                 R(1300, 1000), smp, focus=((0, -0.36, 0.045), 0.10))
        out["closeups"] += shoot(default, "close_muzzle", ("three_quarter", "right", "front"), R(1100, 900), smp,
                                 focus=((0, -0.525, 0.050), 0.045))
        out["closeups"] += shoot(default, "close_stock", ("right", (0.6, 0.9, 0.3)), R(1100, 900), smp,
                                 focus=((0, 0.19, 0.01), 0.10))
        out["closeups"] += shoot(default, "close_mag", ("right", (1.0, -0.4, -0.1)), R(1000, 1000), smp,
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
    if "compare" in groups:
        out["compare"] = []
        out["compare"] += shoot(default, "cmp_v09", (V09_DIR,), R(1536, 896), smp, lens=35, margin=0.92)
        out["compare"] += shoot(default, "cmp_side_ortho", ("right",), R(1536, 768), smp, ortho=True,
                                margin=1.0)
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.hide_render = False
    # contact sheets + comparison (system python with PIL)
    try:
        subprocess.run(["python", os.path.join(HERE, "make_sheets.py")], check=False)
    except Exception as e:  # noqa: BLE001
        print("sheet step failed", e)
    return out
