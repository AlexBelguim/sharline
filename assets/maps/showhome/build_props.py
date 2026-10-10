"""Showhome PROPS KIT: every prop of the TDM map "Showhome" as one mesh per prop, built procedurally.

Run (headless Blender 5.2, re-runnable from scratch):
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      -P "F:/git/val etf/assets/maps/showhome/build_props.py" -- [--only a,b] [--no-render] [--no-export] [--check]
      [--scenes]

Outputs (assets/maps/showhome/kit/):
  props.glb / props.blend   one node per prop (PROP_<Name>), every node at the identity transform, origin at the
                            prop's base. In the .blend each prop sits in its own collection PROP_<Name>.
  props_placed.glb          the brush-matched props instanced at their layout positions. Exported +Y up, so it
                            loads in Bevy at Transform::IDENTITY (bevy = (x, z, -y) of the design frame).
  props_placements.json     every placement: prop, brush tag, design location + yaw, Bevy translation + yaw.
  props_check.json          per-placement alignment of art vs collision brush (dense ray sampling, see check()).
  renders/props/            one tile per prop, props_contact_sheet.png, hero and in-context renders.

Frames: design / Blender = metres, x east, y north, z up. Bevy = (x, z, -y). Yaw: degrees CCW about +Z in the
design frame; the Bevy rotation is Quat::from_rotation_y(radians(yaw)) (same angle, about +Y).

Brush-matched props are modelled in their placed orientation for the west (W_) or centre (C_) instance, local
origin = base centre of their anchor brush. East (E_) instances are the mirror x -> 72 - x: a prop that is
symmetric in x is placed with yaw 0; a prop whose face points along x (lockers, workbench, dresser) uses yaw 180;
props whose detail is not symmetric get their own _Clay variant built from the E_ brushes.
Free props (outside the play area or small detail) face -Y, the STYLE_GUIDE asset convention.
Gameplay rule (layout/LAYOUT.md): every face of a brush-matched prop sits on its collision brush within 2 cm;
decoration may stand proud by at most 1 cm, except a few named small details listed per prop in `ghost_ok`.
"""
import json
import math
import os
import subprocess
import struct
import sys
import time

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = r"F:/git/val etf/assets/maps/showhome"
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "layout"))
sys.path.insert(0, r"F:/git/val etf/tools")
import layout_lib as LL  # noqa: E402
import props_lib as PL  # noqa: E402
from props_lib import Prop, lin, spec, catenary, rounded_rect  # noqa: E402

KIT = os.path.join(HERE, "kit")
KTEX = os.path.join(KIT, "tex")
RENDERS = os.path.join(KIT, "renders", "props")
LAYOUT = LL.load()
V2 = os.path.join(HERE, "textures", "v2")

# Geometry ownership is explicit: loading houses + ground + props_placed must never duplicate a brush.
GROUND_OWNED = {"MoverTruck", "KerbPod", "Fence_Run_S", "Fence_Run_N", "Hedge_Boundary", "Hedge_Lawn",
                "Arbour", "Pylon", "Zipline_Cable"}
HOUSE_OWNED = {"Sofa", "KitchenIsland", "Dresser", "Shelving", "Workbench", "HeatPump", "GarageCar"}


def v2spec(name, texture, repeat=1.0, rough=0.8, fallback=None, **kw):
    """Prefer the complete v2 PBR set; keep old library generation usable during texture production."""
    path = os.path.join(V2, texture + ".png")
    maps_ready = all(os.path.exists(os.path.join(V2, texture + suf + ".png"))
                     for suf in ("", "_normal", "_orm", "_height"))
    if maps_ready:
        man = os.path.join(V2, "manifest.json")
        item = json.load(open(man, encoding="utf-8"))["materials"].get(texture, {}) if os.path.exists(man) else {}
        spec(name, tex=path, repeat=repeat, rough=rough,
             normal=os.path.join(V2, texture + "_normal.png"),
             orm=os.path.join(V2, texture + "_orm.png"), height_range=item.get("height_range_m", 0.0), **kw)
    else:
        spec(name, tex=fallback or texture + ".png", repeat=repeat, rough=rough, **kw)


def argv():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = dict(only=None, render=True, export=True, check=False, scenes=False, hero=set())
    i = 0
    while i < len(a):
        if a[i] == "--only":
            o["only"] = set(a[i + 1].split(","))
            i += 1
        elif a[i] == "--no-render":
            o["render"] = False
        elif a[i] == "--no-export":
            o["export"] = False
        elif a[i] == "--check":
            o["check"] = True
        elif a[i] == "--scenes":
            o["scenes"] = True
        elif a[i] == "--hero":
            o["hero"] = set(a[i + 1].split(","))
            i += 1
        i += 1
    return o


# =============================================================================================== materials
PAL = {k: tuple(v["albedo_linear"]) for k, v in
       json.load(open(os.path.join(HERE, "textures", "_src", "palette.json")))["materials"].items()}


def materials():
    # --- vehicles
    spec("M_TruckWhite", tex="truck_paint_white.png", repeat=3.0, rough=0.62, coat=0.05)
    spec("M_AluTrim", color=(0.50, 0.50, 0.50), rough=0.38, metal=0.35)
    spec("M_Chassis", color=(0.055, 0.055, 0.06), rough=0.62)
    spec("M_Bumper", color=(0.08, 0.08, 0.085), rough=0.7)
    spec("M_GlassDark", color=(0.022, 0.03, 0.042), rough=0.08, coat=0.6)
    spec("M_Rubber", color=(0.02, 0.02, 0.022), rough=0.8)
    spec("M_Tyre", color=(0.03, 0.03, 0.032), rough=0.88)
    spec("M_Rim", color=(0.46, 0.46, 0.47), rough=0.32, metal=0.6)
    spec("M_ArchLiner", color=(0.012, 0.012, 0.014), rough=0.9)
    spec("M_HeadLight", color=(1.0, 0.92, 0.78), emission=(1.0, 0.86, 0.62), estrength=3.0)
    spec("M_TailLight", color=(0.45, 0.02, 0.02), emission=(0.9, 0.04, 0.02), estrength=0.8)
    spec("M_Amber", color=(0.85, 0.40, 0.04), emission=(0.9, 0.38, 0.02), estrength=0.6)
    spec("M_LedIce", color=(0.45, 0.85, 1.0), emission=(0.45, 0.85, 1.0), estrength=2.5)
    spec("M_Plate", color=(0.78, 0.76, 0.70), rough=0.4)
    spec("M_DecalAccent", color=(0.62, 0.20, 0.05), rough=0.45)
    spec("M_DecalDark", color=PAL["frame_dark"], rough=0.45)
    # --- cardboard / crates
    spec("M_Cardboard", tex="cardboard.png", repeat=1.0, rough=0.85)
    spec("M_BoxFace", tex="cardboard_box_face.png", uv="face01", rough=0.85)
    spec("M_BoxDark", color=(0.035, 0.028, 0.022), rough=0.9, ao=False)
    spec("M_Plywood", tex="picket_wood_white.png", repeat=1.2, rough=0.75, tint=(0.62, 0.44, 0.26))
    spec("M_Batten", tex="picket_wood_white.png", repeat=1.0, rough=0.75, tint=(0.46, 0.30, 0.16))
    spec("M_Stencil", color=(0.05, 0.045, 0.04), rough=0.8)
    # --- furniture
    spec("M_FabricOrange", color=lin((200, 108, 66)), rough=0.85)
    spec("M_FabricOrangeDark", color=lin((168, 84, 52)), rough=0.85)
    spec("M_FabricBlue", color=lin((96, 112, 128)), rough=0.85)
    spec("M_FabricBlueDark", color=lin((76, 90, 106)), rough=0.85)
    spec("M_WoodLeg", color=lin((92, 64, 44)), rough=0.6)
    # --- fences / hedges / garden
    spec("M_Picket", tex="picket_wood_white.png", repeat=1.0, rough=0.6)
    spec("M_PicketBack", tex="picket_wood_white.png", repeat=1.0, rough=0.7, tint=(0.70, 0.70, 0.72))
    spec("M_Hedge", tex="hedge_leaves.png", repeat=1.5, rough=0.85)
    spec("M_Vine", tex="hedge_leaves.png", repeat=1.2, rough=0.85, tint=(1.0, 1.0, 0.86))
    spec("M_Flower", color=lin((222, 150, 170)), rough=0.8)
    spec("M_FlowerWhite", color=lin((236, 230, 214)), rough=0.8)
    spec("M_Timber", tex="picket_wood_white.png", repeat=1.0, rough=0.7, tint=(0.40, 0.28, 0.17))
    spec("M_Soil", tex="garden_soil.png", repeat=1.0, rough=0.95)
    spec("M_Crop", color=lin((112, 150, 62)), rough=0.8)
    spec("M_CropDark", color=lin((74, 104, 46)), rough=0.8)
    # --- concrete / metal
    spec("M_Printed", tex="printed_concrete_layers.png", repeat=1.28, rough=0.8,
         normal="printed_concrete_layers_normal.png")
    spec("M_Concrete", tex="concrete_smooth.png", repeat=2.0, rough=0.8)
    spec("M_PoleConcrete", tex="concrete_smooth.png", repeat=2.0, rough=0.8)   # already = palette pole_concrete
    spec("M_SteelGalv", color=(0.33, 0.34, 0.35), rough=0.5, metal=0.55)
    spec("M_SteelDark", color=(0.07, 0.07, 0.075), rough=0.5, metal=0.4)
    spec("M_Grating", color=(0.30, 0.31, 0.32), rough=0.55, metal=0.5)
    spec("M_SafetyYellow", tex="metal_painted_yellow.png", repeat=2.0, rough=0.5)
    spec("M_CabinetWhite", tex="truck_paint_white.png", repeat=2.0, rough=0.45)
    spec("M_Insulator", color=lin((120, 136, 120)), rough=0.3)
    # --- greenhouse / shed / garden structures
    sage, clay = (0.405, 0.454, 0.241), (0.892, 0.340, 0.165)       # README tints for the 0.70 grey panels
    spec("M_GH_Frame", color=(0.74, 0.73, 0.70), rough=0.4, metal=0.1)
    spec("M_GH_Panel", tex=os.path.join(KTEX, "greenhouse_twinwall.png"), repeat=(4.0, 2.2), offset=(0.0, 0.35),
         rough=0.22, coat=0.3, ao=False)
    spec("M_GH_Roof", tex=os.path.join(KTEX, "greenhouse_roof.png"), repeat=1.5, rough=0.22, coat=0.3, ao=False)
    spec("M_KickSage", tex="fibercement_panel.png", repeat=2.4, rough=0.65, tint=sage)
    spec("M_KickClay", tex="fibercement_panel.png", repeat=2.4, rough=0.65, tint=clay)
    spec("M_ShedSage", tex=os.path.join(KTEX, "wood_boards_grey.png"), repeat=2.0, rough=0.75,
         tint=(0.25, 0.30, 0.17))
    spec("M_ShedClay", tex="wood_boards_stained.png", repeat=2.0, rough=0.8)
    spec("M_DoorSage", tex=os.path.join(KTEX, "wood_boards_grey.png"), repeat=2.0, rough=0.7,
         tint=tuple(c / 0.7 * 1.25 for c in PAL["door_sage"]))
    spec("M_DoorClay", tex=os.path.join(KTEX, "wood_boards_grey.png"), repeat=2.0, rough=0.7,
         tint=tuple(c / 0.7 * 1.6 for c in PAL["door_clay"]))
    spec("M_TrimCream", color=PAL["trim_cream"], rough=0.5)
    spec("M_TrimDark", color=PAL["frame_dark"], rough=0.5)
    spec("M_Fascia", color=PAL["roof_dark"], rough=0.6)
    spec("M_RoofMembrane", color=(0.075, 0.07, 0.072), rough=0.85)
    spec("M_Solar", tex="solar_panel.png", uv="face01", rough=0.25, coat=0.5, ao=False)
    spec("M_Sedum", tex="hedge_leaves.png", repeat=1.0, rough=0.9, tint=(1.0, 0.86, 0.62))
    spec("M_WoodStained", tex="wood_boards_stained.png", repeat=2.0, rough=0.8)
    spec("M_WoodStainedH", tex="wood_boards_stained.png", repeat=2.0, rough=0.8, uv="boxh")
    spec("M_TimberH", tex="picket_wood_white.png", repeat=1.0, rough=0.7, tint=(0.40, 0.28, 0.17), uv="boxh")
    # --- street furniture / appliances
    spec("M_LockerBody", tex="truck_paint_white.png", repeat=2.0, rough=0.45, tint=(0.70, 0.71, 0.73))
    spec("M_LockerDoor", tex="truck_paint_white.png", repeat=2.0, rough=0.45, tint=(0.92, 0.92, 0.94))
    spec("M_Vinyl", color=(0.055, 0.058, 0.064), rough=0.6)
    spec("M_TankPaint", tex="truck_paint_white.png", repeat=2.0, rough=0.5, metal=0.15, tint=(0.17, 0.22, 0.19))
    spec("M_Stainless", color=(0.56, 0.56, 0.57), rough=0.28, metal=0.8)
    spec("M_Worktop", color=(0.055, 0.055, 0.06), rough=0.3)
    spec("M_Acrylic", color=(0.85, 0.92, 0.95), alpha=0.16, rough=0.05, cull=False, ao=False)
    spec("M_ModelGreen", color=lin((120, 150, 70)), rough=0.8)
    spec("M_ModelWhite", color=(0.80, 0.78, 0.74), rough=0.6)
    spec("M_CarSilver", color=(0.48, 0.49, 0.50), rough=0.3, metal=0.5, coat=0.6)
    spec("M_Fabric", tex=os.path.join(KTEX, "fabric_weave.png"), repeat=0.8, rough=0.9, tint=(0.5, 0.5, 0.5))
    spec("M_BinGrey", color=(0.10, 0.105, 0.11), rough=0.6)
    spec("M_BinLidGreen", color=lin((70, 110, 60)), rough=0.55)
    spec("M_BinLidBlue", color=lin((60, 90, 140)), rough=0.55)
    spec("M_BinLidBrown", color=lin((110, 80, 55)), rough=0.55)
    spec("M_Anthracite", color=(0.045, 0.047, 0.052), rough=0.45, metal=0.3)
    spec("M_Cable", color=(0.018, 0.018, 0.02), rough=0.45, ao=False)
    # Painted v2 sheets, exact metre mapping. Untextured colours remain ordinary glTF baseColorFactor.
    for name in ("M_Plywood", "M_Batten", "M_Timber", "M_TimberH"):
        v2spec(name, "timber_pallets", repeat=2.0, rough=0.78, fallback="wood_boards_stained.png",
               uv="boxh" if name.endswith("H") else "box")
    for name in ("M_WoodStained", "M_WoodStainedH", "M_ShedClay"):
        v2spec(name, "wood_boards_stained", repeat=2.0, rough=0.78,
               uv="boxh" if name.endswith("H") else "box")
    v2spec("M_Printed", "printed_concrete_layers", repeat=1.28, rough=0.8)
    v2spec("M_Concrete", "concrete_smooth", repeat=2.0, rough=0.8)
    v2spec("M_PoleConcrete", "concrete_smooth", repeat=2.0, rough=0.8)
    v2spec("M_Soil", "garden_soil", repeat=1.0, rough=0.95)
    v2spec("M_SiteDirt", "worksite_packed_dirt", repeat=6.0, rough=0.92, fallback="garden_soil.png")
    v2spec("M_SiteSand", "construction_sand", repeat=6.0, rough=0.95)
    v2spec("M_Pebble", "gravel", repeat=1.0, rough=0.86)
    v2spec("M_SiteSteel", "metal_scaffold_tube", repeat=1.0, rough=0.52, fallback="metal_painted_yellow.png")
    v2spec("M_SafetyYellow", "metal_painted_yellow", repeat=2.0, rough=0.58)
    v2spec("M_KickSage", "fibercement_sage", repeat=4.8, rough=0.65)
    v2spec("M_KickClay", "fibercement_clay", repeat=4.8, rough=0.65)
    v2spec("M_Picket", "picket_wood_white", repeat=1.0, rough=0.72)
    v2spec("M_PicketBack", "picket_wood_white", repeat=1.0, rough=0.76, tint=(0.70, 0.70, 0.72))
    v2spec("M_TruckWhite", "truck_paint_white", repeat=3.0, rough=0.62, coat=0.05)
    v2spec("M_CabinetWhite", "truck_paint_white", repeat=2.0, rough=0.62)
    v2spec("M_LockerBody", "truck_paint_white", repeat=2.0, rough=0.62, tint=(0.70, 0.71, 0.73))
    v2spec("M_LockerDoor", "truck_paint_white", repeat=2.0, rough=0.60, tint=(0.92, 0.92, 0.94))
    v2spec("M_TankPaint", "truck_paint_white", repeat=2.0, rough=0.65, tint=(0.17, 0.22, 0.19))
    v2spec("M_Cardboard", "cardboard", repeat=1.0, rough=0.85)
    v2spec("M_BoxFace", "cardboard", repeat=1.0, rough=0.85, uv="face01", fallback="cardboard_box_face.png")
    # The same cream painted sheet shades small copings and sills; average remains the trim palette.
    v2spec("M_TrimCream", "concrete_smooth", repeat=2.0, rough=0.65,
           tint=tuple(PAL["trim_cream"][i] / PAL["pole_concrete"][i] for i in range(3)))
    v2spec("M_RoofMembrane", "concrete_smooth", repeat=2.0, rough=0.85,
           tint=tuple(c / PAL["pole_concrete"][i] for i, c in enumerate((0.075, 0.07, 0.072))))
    for name, colour in (("M_FabricOrange", (200, 108, 66)), ("M_FabricOrangeDark", (168, 84, 52)),
                         ("M_FabricBlue", (96, 112, 128)), ("M_FabricBlueDark", (76, 90, 106))):
        v2spec(name, "concrete_smooth", repeat=2.0, rough=0.85,
               tint=tuple(lin(colour)[i] / PAL["pole_concrete"][i] for i in range(3)))
    spec("M_PackingTape", color=lin((190, 160, 113)), rough=0.76)
    # Tint the neutral cream painterly concrete sheet for clean boulders / site plastics.
    v2spec("M_Rock", "concrete_smooth", repeat=2.0, rough=0.9, tint=(0.78, 0.79, 0.78))
    v2spec("M_SiteOrange", "concrete_smooth", repeat=2.0, rough=0.62, tint=(1.1, 0.36, 0.15))
    v2spec("M_CementBag", "concrete_smooth", repeat=2.0, rough=0.86, tint=(0.90, 0.91, 0.88))
    spec("M_BagStripe", color=lin((116, 139, 111)), rough=0.78)
    spec("M_WaterCover", color=lin((109, 142, 135)), rough=0.7)


# =============================================================================================== layout access
def brush(tag, part=None, idx=0):
    bs = LAYOUT.brushes(tag=tag, part=part)
    bs = [b for b in bs if b["kind"] != "PlayerClip"]
    if not bs:
        raise KeyError(tag)
    b = bs[idx]
    return Vector(b["min"]), Vector(b["max"]), b


def base_centre(tag, part=None):
    mn, mx, _ = brush(tag, part)
    return Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))


def local_box(tag, origin, part=None, idx=0):
    mn, mx, _ = brush(tag, part, idx)
    return tuple(mn - origin), tuple(mx - origin)


# =============================================================================================== registry
REG = []


def prop(name, cat="free", brushes=None, anchor=None, place=None, view=(0.8, -1.0, 0.5), ghost_ok=None,
         note="", aofn=None, ao=(0.45, 0.72)):
    """cat: 'matched' (sits on collision brushes), 'detail' (small in-bounds dressing, no brush),
    'free' (outside the play area), 'backdrop' (large out-of-bounds set dressing).
    place: list of (anchor tag, yaw_deg, brush tags covered) for every in-map instance."""
    def deco(fn):
        REG.append(dict(name=name, fn=fn, cat=cat, brushes=brushes or [], anchor=anchor, place=place or [],
                        view=view, ghost_ok=ghost_ok or [], note=note, ao_fn=aofn, ao=ao))
        return fn
    return deco


# =============================================================================================== props: vehicles
def arch_poly(cy, cz, r, zb, steps=14):
    """Points of a wheel-arch arc (in the side plane: y, z) from its left foot at z=zb over the top to the right
    foot, for an arch of radius r centred at (cy, cz)."""
    s = math.sqrt(max(r * r - (cz - zb) ** 2, 0.0))
    a0 = math.degrees(math.atan2(zb - cz, -s)) % 360
    a1 = math.degrees(math.atan2(zb - cz, s))
    sweep = (a0 - a1) % 360
    return [(cy + r * math.cos(math.radians(a0 - sweep * i / steps)),
             cz + r * math.sin(math.radians(a0 - sweep * i / steps))) for i in range(steps + 1)]


def side_profile(ya, yb, ztop, arches, zb):
    """Closed side profile (y, z) from ya to yb, z zb..ztop, with wheel arches [(cy, cz, r)] cut from the bottom."""
    pts = [(ya, zb)]
    for (cy, cz, r) in sorted(arches):
        pts += arch_poly(cy, cz, r, zb)
    return pts + [(yb, zb), (yb, ztop), (ya, ztop)]


def wheel(P, x_out, sx, cy, cz, r, width, liner_r, liner_depth, rim_r, dual=False):
    """Tyre(s) + rim + a D-shaped dark arch liner (never below the ground). x_out: outer sidewall |x|."""
    lx0, lx1 = sorted((sx * (x_out - liner_depth), sx * (x_out + 0.003)))
    P.prism(arch_poly(cy, cz, liner_r, 0.0, 16), lx0, lx1, "M_ArchLiner", axis="X")
    tyres = [(x_out - width, x_out)] if not dual else [(x_out - width / 2 + 0.01, x_out),
                                                         (x_out - width, x_out - width / 2 - 0.01)]
    for (ta, tb) in tyres:
        a, b = sorted((sx * ta, sx * tb))
        P.cyl((a, cy, cz), (b, cy, cz), r, "M_Tyre", n=28, bev=0.045, seg=3)
    a, b = sorted((sx * (x_out - 0.05), sx * (x_out + 0.002)))
    P.cyl((a, cy, cz), (b, cy, cz), rim_r, "M_Rim", n=20, bev=0.01)
    a, b = sorted((sx * (x_out + 0.002), sx * (x_out + 0.008)))
    P.cyl((a, cy, cz), (b, cy, cz), rim_r * 0.38, "M_Chassis", n=12)


@prop("MoverTruck", cat="matched", anchor="C_MOVER_BOX", view=(0.9, 1.0, 0.42),
      place=[("C_MOVER_BOX", 0, ["C_MOVER_BOX", "C_MOVER_CAB"])],
      ghost_ok=["camera wings (x 1.15..1.25 beside the cab, inside the box width)"],
      note="Mover: driverless box truck. Cab faces north (+Y). Box top z 3.2 is the J_MOVER perch, cab top 2.4.")
def truck(P):
    W, T = "M_TruckWhite", "M_AluTrim"
    zf = 1.05                       # cargo floor / top of the chassis skirts
    hx, y0, y1, H = 1.25, -4.0, 4.0, 3.2
    # ---------------- cargo box: corner posts and rails flush with the brush, panels 3 mm in
    P.box(-hx + 0.003, y0 + 0.003, zf, hx - 0.003, y1 - 0.003, H - 0.003, W, bev=0.035)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x = sx * (hx - 0.045)
            y = sy * (y1 - 0.045) if sy > 0 else y0 + 0.045
            P.boxc((x, y, (zf + H) / 2), (0.09, 0.09, H - zf), T, bev=0.012)
    for z0, z1 in ((H - 0.11, H), (zf, zf + 0.10)):
        P.box(-hx, y0, z0, hx, y1, z1, T, bev=0.012, edges=lambda a, b: abs(a.z - b.z) < 1e-6)
    # roof: two very shallow lighter panels to break the big white top (flush, 2 mm proud of the shell)
    P.box(-hx + 0.09, y0 + 0.12, H - 0.002, hx - 0.09, y1 - 0.12, H, "M_TruckWhite")
    # The standable perch continues right to the collision edges. A flat cap avoids down-rays falling
    # through a bevel at x +/- 1.25 to lower side details.
    P.box(-hx, y0, H - 0.014, hx, y1, H, "M_TruckWhite")
    # side stripe + logo (decals, 4 mm proud of the panel = still inside the brush)
    for sx in (-1, 1):
        xo = sx * (hx - 0.001)
        xi = sx * (hx - 0.006)
        P.box(min(xo, xi), y0 + 0.12, 1.30, max(xo, xi), y1 - 0.12, 1.36, "M_DecalDark")
        P.box(min(xo, xi), y0 + 0.12, 1.39, max(xo, xi), y1 - 0.12, 1.41, "M_DecalAccent")
        # logo: rounded tile with a house glyph near the cab end
        cy = 2.55
        tile = rounded_rect(cy - 0.42, 1.78, cy + 0.42, 2.62, 0.12, 4)
        P.prism(tile, min(xo, xi), max(xo, xi), "M_DecalAccent", axis="X")
        house = [(cy - 0.24, 1.94), (cy + 0.24, 1.94), (cy + 0.24, 2.24), (cy, 2.46), (cy - 0.24, 2.24)]
        xh0 = sx * (hx - 0.0005)
        P.prism(house, min(xo, xh0), max(xo, xh0), "M_TruckWhite", axis="X")
        door = [(cy - 0.06, 1.94), (cy + 0.06, 1.94), (cy + 0.06, 2.10), (cy - 0.06, 2.10)]
        xd = sx * (hx + 0.0002)
        P.prism(door, min(xh0, xd), max(xh0, xd), "M_DecalAccent", axis="X")
        # amber side marker lights along the lower rail
        for y in (-3.4, -0.6, 2.2):
            P.box(min(sx * hx, sx * (hx + 0.006)), y - 0.05, zf + 0.025, max(sx * hx, sx * (hx + 0.006)), y + 0.05,
                  zf + 0.075, "M_Amber")
    # front wall marker lights above the cab
    for sx in (-1, 1):
        P.box(sx * 0.95 - 0.06, y1, H - 0.2, sx * 0.95 + 0.06, y1 + 0.006, H - 0.14, "M_Amber")
    # ---------------- rear: roll-up door raised, cargo boxes packed flush to the tail
    yr = y0
    P.box(-hx, yr, H - 0.26, hx, yr + 0.05, H, T, bev=0.01)              # door header
    P.box(-hx, yr, zf, hx, yr + 0.05, zf + 0.16, T, bev=0.01)             # sill
    P.box(-1.16, yr + 0.02, zf + 0.16, 1.16, yr + 0.06, H - 0.26, "M_BoxDark")  # dark backing
    # raised door: slats visible under the header
    zt = H - 0.26
    for k in range(4):
        za = zt - 0.115 * (k + 1)
        P.box(-1.16, yr + 0.010, za + 0.008, 1.16, yr + 0.03, za + 0.115, "M_CabinetWhite", bev=0.006)
    zd = zt - 0.46
    P.box(-1.16, yr + 0.004, zd - 0.05, 1.16, yr + 0.03, zd, "M_Bumper")   # door bottom bar
    P.box(-0.03, yr + 0.003, zd - 0.38, 0.03, yr + 0.012, zd - 0.05, "M_Rubber")  # pull strap
    # cargo: two rows of boxes, faces 1-2 cm behind the tail plane
    rows = [((zf + 0.16, zf + 0.78), [(-1.16, -0.38), (-0.36, 0.40), (0.42, 1.16)]),
            ((zf + 0.80, zd - 0.06), [(-1.16, -0.55), (-0.53, 0.30), (0.32, 1.16)])]
    for ri, ((za, zb), cols) in enumerate(rows):
        for ci, (xa, xb) in enumerate(cols):
            dy = 0.008 + 0.006 * ((ri * 3 + ci) % 3)
            P.box(xa + 0.004, yr + dy, za, xb - 0.004, yr + dy + 0.45, zb - 0.004, "M_BoxFace", bev=0.012)
    # tail lights in the corner posts
    for sx in (-1, 1):
        P.box(sx * (hx - 0.075) - 0.035, yr - 0.006, zf + 0.20, sx * (hx - 0.075) + 0.035, yr, zf + 0.62,
              "M_TailLight")
    # ---------------- chassis skirts (closed to the ground: the collision box is solid down to z 0)
    ra, wy, wz = 0.58, -2.55, 0.50                   # rear arch radius / axle y / wheel centre z
    zb = 0.012
    for sx in (-1, 1):
        xa, xb = sorted((sx * (hx - 0.035), sx * hx))
        P.prism(side_profile(y0, y1, zf, [(wy, wz, ra)], zb), xa, xb, "M_Chassis", axis="X", bev=0.006)
        # battery pack panel with vent lines between the cab and the rear wheel (decal-flush)
        xo, xi = sorted((sx * hx, sx * (hx + 0.004)))
        P.box(xo, -1.75, 0.32, xi, 3.6, 0.92, "M_Bumper")
        for k in range(5):
            a, b = sorted((sx * hx, sx * (hx + 0.007)))
            P.box(a, 2.6 + k * 0.17, 0.48, b, 2.66 + k * 0.17, 0.80, "M_Rubber")
        wheel(P, hx - 0.012, sx, wy, wz, wz, 0.54, ra - 0.004, 0.30, 0.29, dual=True)
    # rear lower skirt + bumper + plate, and the hidden wall behind the cab
    P.box(-hx, y0, zb, hx, y0 + 0.04, zf, "M_Chassis", bev=0.008)
    P.box(-hx + 0.02, y0 - 0.008, 0.30, hx - 0.02, y0 + 0.16, 0.56, "M_Bumper", bev=0.03)
    P.box(-0.26, y0 - 0.012, 0.60, 0.26, y0 - 0.002, 0.74, "M_Plate", bev=0.005)
    for sx in (-1, 1):
        P.box(sx * 0.95 - 0.12, y0 - 0.014, 0.38, sx * 0.95 + 0.12, y0 - 0.004, 0.48, "M_TailLight")
    P.box(-hx, y1 - 0.04, zb, hx, y1, zf, "M_Chassis")
    # ---------------- cab (cab-over, brush x +-1.15, y 4..6.5, z 0..2.4)
    cx, cy0, cy1, cH = 1.15, 4.0, 6.5, 2.4
    fy, fz, fr = 5.32, 0.48, 0.56                    # front axle y, wheel z, arch radius
    prof = [(cy0, zb)] + arch_poly(fy, fz, fr, zb)
    rr = 0.13
    prof += [(cy1, zb), (cy1, cH - rr)]
    for i in range(1, 6):
        a = math.radians(90 * i / 6)
        prof.append((cy1 - rr + rr * math.cos(a), cH - rr + rr * math.sin(a)))
    prof += [(cy1 - rr, cH), (cy0, cH)]
    P.prism(prof, -cx, cx, W, axis="X", bev=0.05, seg=3)
    # windscreen (wraps a little round the corners), header sensor strip, A-pillar dark
    P.box(-1.03, cy1 - 0.004, 1.40, 1.03, cy1 + 0.006, 2.20, "M_Rubber", bev=0.01)
    P.box(-0.99, cy1 + 0.004, 1.44, 0.99, cy1 + 0.009, 2.16, "M_GlassDark", bev=0.008)
    P.box(-0.86, cy1 - 0.004, 2.25, 0.86, cy1 + 0.007, 2.32, "M_GlassDark", bev=0.006)
    P.box(-0.62, cy1 + 0.006, 2.272, 0.62, cy1 + 0.009, 2.292, "M_LedIce")
    # front face: grille band, headlights, badge
    P.box(-0.62, cy1 - 0.004, 0.80, 0.62, cy1 + 0.005, 1.06, "M_Bumper", bev=0.01)
    for k in range(3):
        z = 0.85 + k * 0.075
        P.box(-0.58, cy1 + 0.004, z, 0.58, cy1 + 0.009, z + 0.025, "M_Chassis")
    for sx in (-1, 1):
        a, b = sorted((sx * 0.68, sx * 1.06))
        P.box(a, cy1 - 0.004, 0.80, b, cy1 + 0.006, 1.06, "M_Rubber", bev=0.012)
        a, b = sorted((sx * 0.71, sx * 1.03))
        P.box(a, cy1 + 0.004, 0.83, b, cy1 + 0.009, 1.03, "M_HeadLight", bev=0.01)
        # indicator
        a, b = sorted((sx * 1.04, sx * 1.12))
        P.box(a, cy1 - 0.01, 0.84, b, cy1 + 0.004, 1.0, "M_Amber", bev=0.006)
    P.box(-0.16, cy1 + 0.003, 1.14, 0.16, cy1 + 0.009, 1.26, "M_DecalAccent", bev=0.01)
    # bumper wraps the lower cab, fog lights, step
    P.box(-cx - 0.004, cy1 - 0.42, zb, cx + 0.004, cy1 + 0.006, 0.58, "M_Bumper", bev=0.03, seg=2)
    for sx in (-1, 1):
        a, b = sorted((sx * 0.78, sx * 1.0))
        P.box(a, cy1 + 0.004, 0.24, b, cy1 + 0.01, 0.33, "M_HeadLight", bev=0.01)
    # side: door windows, seams, handles, camera wings, front tyres
    for sx in (-1, 1):
        xo = sx * cx
        a, b = sorted((xo - sx * 0.004, xo + sx * 0.006))
        P.box(a, 4.62, 1.40, b, 6.30, 2.20, "M_Rubber", bev=0.01)
        a, b = sorted((xo + sx * 0.004, xo + sx * 0.009))
        P.box(a, 4.66, 1.44, b, 6.26, 2.16, "M_GlassDark", bev=0.008)
        a, b = sorted((xo - sx * 0.002, xo + sx * 0.004))
        P.box(a, 4.52, 0.62, b, 4.545, 2.26, "M_Chassis")              # door rear seam
        P.box(a, 4.70, 1.25, b, 4.92, 1.30, "M_Chassis")               # handle
        P.box(a, 4.20, 0.62, b, 4.45, 2.24, "M_TruckWhite")            # B-pillar panel
        # camera wing (small detail: inside the box width, beside the cab)
        a, b = sorted((xo, sx * 1.245))
        P.box(a, 6.18, 1.86, b, 6.40, 2.14, "M_Bumper", bev=0.025)
        a, b = sorted((sx * 1.18, sx * 1.248))
        P.box(a, 6.36, 1.92, b, 6.405, 2.08, "M_GlassDark", bev=0.01)
        # step below the door, behind the arch
        a, b = sorted((xo - sx * 0.08, xo + sx * 0.004))
        P.box(a, 4.10, 0.30, b, 4.66, 0.36, "M_Chassis")
        # front tyre + liner + rim
        wheel(P, cx - 0.012, sx, fy, fz, fz, 0.30, fr - 0.004, 0.32, 0.28)


@prop("KerbPod", cat="matched", anchor="W_KERBPOD", view=(1.0, 0.9, 0.45),
      place=[("W_KERBPOD", 0, ["W_KERBPOD"]), ("E_KERBPOD", 180, ["E_KERBPOD"])],
      note="Driverless parcel delivery pod parked at the kerb, nose north (+Y). Solid to the ground.")
def kerb_pod(P):
    hx, hy, H = 1.0, 1.8, 2.2
    zb, zs = 0.012, 0.56
    W = "M_TruckWhite"
    arches = [(-1.08, 0.36, 0.43), (1.08, 0.36, 0.43)]
    # lower skirt (dark, closed to the ground) and the white body above it
    P.prism(side_profile(-hy, hy, zs + 0.06, arches, zb), -hx, hx, "M_Bumper", axis="X", bev=0.05, seg=2)
    P.box(-hx, -hy, zs, hx, hy, H, W, bev=0.10, seg=4)
    # front (+Y) and rear glass: wrap-around dark band, light bars
    for sy in (-1, 1):
        y = sy * hy
        a, b = sorted((y - sy * 0.004, y + sy * 0.006))
        P.box(-0.84, a, 1.30, 0.84, b, 2.02, "M_GlassDark", bev=0.06)
        P.box(-0.72, a, 0.80, 0.72, b, 0.86, "M_LedIce" if sy > 0 else "M_TailLight", bev=0.01)
    for sx in (-1, 1):
        xo = sx * hx
        a, b = sorted((xo - sx * 0.004, xo + sx * 0.006))
        P.box(a, 0.95, 1.30, b, 1.66, 2.02, "M_GlassDark", bev=0.05)      # front side window
        P.box(a, -1.66, 1.62, b, -0.95, 2.02, "M_GlassDark", bev=0.05)    # rear side window strip
        # parcel locker doors on the side (light panels with handle slots)
        for (ya, yb) in ((-1.30, -0.66), (-0.62, 0.02), (0.06, 0.70)):
            for (za, zb2) in ((0.70, 1.12), (1.16, 1.58)):
                a, b = sorted((xo - sx * 0.002, xo + sx * 0.006))
                P.box(a, ya, za, b, yb, zb2, "M_CabinetWhite", bev=0.012)
                a, b = sorted((xo + sx * 0.005, xo + sx * 0.008))
                P.box(a, yb - 0.16, zb2 - 0.08, b, yb - 0.05, zb2 - 0.055, "M_Chassis")
        a, b = sorted((xo - sx * 0.002, xo + sx * 0.005))
        P.box(a, -1.62, 0.62, b, 1.62, 0.655, "M_DecalAccent")
        for (cy, cz, r) in arches:
            wheel(P, hx - 0.012, sx, cy, cz, 0.36, 0.26, r - 0.004, 0.26, 0.21)
    # roof sensor puck (inset) and status light
    P.box(-0.25, 1.30, H - 0.004, 0.25, 1.62, H, "M_GlassDark")
    P.box(-0.20, 1.60, H - 0.06, 0.20, hy + 0.004, H - 0.03, "M_LedIce")


# =============================================================================================== props: boxes / crates
def cardboard_box(P, x0, y0, z0, x1, y1, z1, rot=0.0):
    since = P.nverts()
    P.box(x0, y0, z0, x1, y1, z1, "M_BoxFace", bev=min(0.015, 0.1 * (x1 - x0)), seg=2)
    cx = (x0 + x1) / 2
    # Packing tape is explicit geometry over the painted paper, not an atlas decal or baked lighting.
    P.box(cx - 0.018, y0, z1 - 0.002, cx + 0.018, y1, z1 + 0.001, "M_PackingTape")
    for ya, yb in ((y0 - 0.001, y0 + 0.001), (y1 - 0.001, y1 + 0.001)):
        P.box(cx - 0.018, ya, max(z0, z1 - 0.08), cx + 0.018, yb, z1, "M_PackingTape")
    if rot:
        c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, 0))
        P.transform_last(Matrix.Translation(c) @ Matrix.Rotation(math.radians(rot), 4, "Z")
                         @ Matrix.Translation(-c), since)


@prop("Box_S", cat="detail", view=(0.8, -1.0, 0.6), note="Cardboard box 0.40 x 0.30 x 0.30 (small dressing).")
def box_s(P):
    cardboard_box(P, -0.20, -0.15, 0, 0.20, 0.15, 0.30)


@prop("Box_M", cat="detail", view=(0.8, -1.0, 0.6), note="Cardboard box 0.60 x 0.40 x 0.42.")
def box_m(P):
    cardboard_box(P, -0.30, -0.20, 0, 0.30, 0.20, 0.42)


@prop("Box_L", cat="detail", view=(0.8, -1.0, 0.6), note="Cardboard box 0.80 x 0.55 x 0.55.")
def box_l(P):
    cardboard_box(P, -0.40, -0.275, 0, 0.40, 0.275, 0.55)


@prop("Box_M_Open", cat="detail", view=(0.8, -1.0, 0.7), note="Open cardboard box with the flaps up.")
def box_m_open(P):
    hx, hy, h = 0.30, 0.20, 0.42
    t = 0.006
    for (a, b, c, d) in ((-hx, -hy, hx, -hy + t), (-hx, hy - t, hx, hy), (-hx, -hy, -hx + t, hy), (hx - t, -hy, hx, hy)):
        P.box(a, b, 0, c, d, h, "M_Cardboard")
    P.box(-hx, -hy, 0, hx, hy, 0.02, "M_Cardboard")
    P.box(-hx + t, -hy + t, 0.02, hx - t, hy - t, 0.30, "M_BoxDark")
    # flaps hinged outwards at the top edges
    for sy in (-1, 1):
        y = sy * hy
        P.quad([(-hx, y, h), (hx, y, h), (hx, y + sy * 0.17, h + 0.14), (-hx, y + sy * 0.17, h + 0.14)], "M_Cardboard")
        P.quad([(hx, y, h), (-hx, y, h), (-hx, y + sy * 0.17, h + 0.14), (hx, y + sy * 0.17, h + 0.14)], "M_Cardboard")
    for sx in (-1, 1):
        x = sx * hx
        P.quad([(x, -hy, h), (x, hy, h), (x + sx * 0.12, hy, h + 0.15), (x + sx * 0.12, -hy, h + 0.15)], "M_Cardboard")
        P.quad([(x, hy, h), (x, -hy, h), (x + sx * 0.12, -hy, h + 0.15), (x + sx * 0.12, hy, h + 0.15)], "M_Cardboard")


@prop("BoxStack_1m", cat="matched", anchor="W_CRATE", view=(0.8, -1.0, 0.55),
      place=[("W_CRATE", 0, ["W_CRATE"]), ("E_CRATE", 180, ["E_CRATE"])],
      note="Moving boxes stacked into exactly the 1 m crate brush (faces within 1.5 cm).")
def box_stack(P):
    # Opaque packing core behind the thin carton joints: the collision never has an air slit.
    P.box(-0.494, -0.494, 0, 0.494, 0.494, 1.0, "M_Cardboard", bev=0.004, seg=1)
    cardboard_box(P, -0.5, -0.5, 0.0, 0.5, 0.5, 0.53)
    cardboard_box(P, -0.497, -0.495, 0.53, -0.004, 0.497, 1.0, rot=0.8)
    cardboard_box(P, 0.004, -0.49, 0.53, 0.497, 0.49, 1.0, rot=-0.6)


@prop("Crate_Wood_1m", cat="matched", anchor="C_CRATE_T", view=(0.8, -1.0, 0.55),
      place=[("C_CRATE_T", 0, ["C_CRATE_T"])],
      note="Plywood moving crate with battens, fills the 1 m crate brush.")
def crate_wood(P):
    h = 0.5
    P.box(-h + 0.012, -h + 0.012, 0.0, h - 0.012, h - 0.012, 1.0 - 0.012, "M_Plywood", bev=0.01)
    w = 0.085
    # battens: frame on every vertical face + a diagonal brace, flush with the brush faces
    for ax in ("x", "y"):
        for s in (-1, 1):
            for (u0, u1, z0, z1) in ((-h, -h + w, 0, 1.0), (h - w, h, 0, 1.0), (-h + w, h - w, 0, w),
                                     (-h + w, h - w, 1.0 - w, 1.0)):
                if ax == "y":
                    a, b = sorted((s * h, s * (h - 0.013)))
                    P.box(u0, a, z0, u1, b, z1, "M_Batten", bev=0.006)
                else:
                    a, b = sorted((s * h, s * (h - 0.013)))
                    P.box(a, u0, z0, b, u1, z1, "M_Batten", bev=0.006)
            # diagonal
            L = math.hypot(1.0 - 2 * w, 1.0 - 2 * w)
            # the brace runs corner to corner inside the frame (thickness along the face normal)
            if ax == "y":
                y = s * (h - 0.0065)
                P.bar((-h + w + 0.03, y, w + 0.03), (h - w - 0.03, y, 1.0 - w - 0.03), 0.013, w * 0.85,
                      "M_Batten", up=(0, 1, 0))
            else:
                x = s * (h - 0.0065)
                P.bar((x, h - w - 0.03, w + 0.03), (x, -h + w + 0.03, 1.0 - w - 0.03), 0.013, w * 0.85,
                      "M_Batten", up=(1, 0, 0))
    # top: two battens + stencil arrows (paint)
    for u in (-h + 0.06, h - 0.06 - w):
        P.box(-h, u, 1.0 - 0.013, h, u + w, 1.0, "M_Batten", bev=0.005)
    # "this way up" arrows painted on the plywood (beside the brace)
    for sy in (-1, 1):
        a, b = sorted((sy * (h - 0.012), sy * (h - 0.0105)))
        for xo in (-0.22,):
            P.prism([(xo - 0.035, 0.62), (xo + 0.035, 0.62), (xo + 0.035, 0.72), (xo + 0.075, 0.72), (xo, 0.80),
                     (xo - 0.075, 0.72), (xo - 0.035, 0.72)], a, b, "M_Stencil", axis="Y")


# =============================================================================================== props: furniture
def club_seat(P, w, d, H, fab, fab_dark, boxes):
    """Chunky club-style seat that fills a w x d x H box: arms and back at full height, seat cushion lower and a
    moving box (or several) on the seat so the top stays at H (the collision box is solid up to H)."""
    hx, hy = w / 2, d / 2
    aw, bd = 0.22, 0.22
    # An upholstered seat front and carton packing core close thin seams, while retaining the chair silhouette.
    P.box(-hx + aw, -hy + 0.004, 0.08, hx - aw, hy - bd, 0.46, fab_dark, bev=0.005, seg=1)
    P.box(-hx + aw + 0.003, -hy + 0.005, 0.46, hx - aw - 0.003, hy - bd - 0.005, H - 0.005,
          "M_Cardboard", bev=0.003, seg=1)
    P.box(-hx, -hy, 0.0, hx, hy, 0.08, "M_WoodLeg", bev=0.015)
    for sx in (-1, 1):
        a, b = sorted((sx * hx, sx * (hx - aw)))
        P.box(a, -hy, 0.06, b, hy, H, fab, bev=0.018, seg=2)
    P.box(-hx + aw - 0.02, hy - bd, 0.06, hx - aw + 0.02, hy, H, fab, bev=0.018, seg=2)
    P.box(-hx + aw, -hy + 0.005, 0.06, hx - aw, hy - bd, 0.30, fab_dark, bev=0.012)
    P.box(-hx + aw + 0.005, -hy + 0.005, 0.30, hx - aw - 0.005, hy - bd + 0.02, 0.46, fab, bev=0.015, seg=2)
    for (x0, x1, rot) in boxes:
        cardboard_box(P, x0, -hy + 0.012, 0.46, x1, hy - bd - 0.01, H, rot=rot)


@prop("Armchair", cat="matched", anchor="W_ARMCHAIR", view=(0.8, -1.0, 0.55),
      place=[("W_ARMCHAIR", 0, ["W_ARMCHAIR"]), ("E_ARMCHAIR", 180, ["E_ARMCHAIR"])],
      note="Orange club armchair with a moving box on the seat (fills the 1.2 x 1.2 x 0.8 brush). Faces -Y.")
def armchair(P):
    club_seat(P, 1.2, 1.2, 0.8, "M_FabricOrange", "M_FabricOrangeDark", [(-0.37, 0.37, 1.5)])


@prop("Sofa", cat="matched", anchor="W_SOFA", view=(0.8, -1.0, 0.55),
      place=[("W_SOFA", 0, ["W_SOFA"]), ("E_SOFA", 0, ["E_SOFA"])],
      note="Moving-day couch: club sofa with two boxes on the seat, fills the 2.5 x 0.9 x 0.8 brush. Faces -Y.")
def sofa(P):
    club_seat(P, 2.5, 0.9, 0.8, "M_FabricBlue", "M_FabricBlueDark", [(-1.03, -0.02, -1.0), (0.02, 1.03, 0.8)])


# =============================================================================================== props: fences
def picket_strip(P, x_face, sx, ya, yb, mat="M_Picket", pw=0.088, gap=0.034, z0=0.05, zs=1.115, zt=1.2):
    """Pickets on one face of a fence core: the outer face at x_face, 2 cm thick, pointing outward along sx."""
    span = yb - ya
    n = max(1, int((span + gap) / (pw + gap)))
    used = n * pw + (n - 1) * gap
    y = ya + (span - used) / 2
    xa, xb = sorted((x_face, x_face - sx * 0.016))
    for _ in range(n):
        poly = [(y, z0), (y + pw, z0), (y + pw, zs), (y + pw / 2, zt), (y, zs)]
        P.prism(poly, xa, xb, mat, axis="X", bev=0.004, seg=1)
        y += pw + gap


def fence_run(P, L, t=0.3, H=1.2, gate_ends=(), post_every=2.0):
    """Solid picket fence slab: x +-t/2, y 0..L (local), z 0..H. Core (shadowed white) + pickets on both faces +
    posts. gate_ends: subset of {'s', 'n'} that get a taller gate post look (still within H)."""
    hx = t / 2
    P.box(-hx + 0.015, 0.0, 0.0, hx - 0.015, L, H - 0.012, "M_PicketBack", bev=0.008)
    nseg = max(1, math.ceil(L / post_every - 1e-6))
    pts = [L * i / nseg for i in range(nseg + 1)]
    pw = 0.10
    for i, yp in enumerate(pts):
        ya = max(0.0, yp - pw / 2)
        yb = min(L, yp + pw / 2)
        if i == 0:
            ya, yb = 0.0, pw if "s" not in gate_ends else 0.14
        if i == len(pts) - 1:
            ya, yb = (L - pw, L) if "n" not in gate_ends else (L - 0.14, L)
        P.box(-hx, ya, 0.0, hx, yb, H, "M_Picket", bev=0.014)
    for i in range(nseg):
        ya = pts[i] + (pw / 2 if i else (0.14 if "s" in gate_ends else pw)) + 0.012
        yb = pts[i + 1] - (pw / 2 if i + 1 < nseg else (0.14 if "n" in gate_ends else pw)) - 0.012
        for sx in (-1, 1):
            picket_strip(P, sx * hx, sx, ya, yb)
        # hidden rails behind the pickets (visible through the gaps as darker bands)
        for z in (0.25, 0.92):
            P.box(-hx + 0.009, ya, z, hx - 0.009, yb, z + 0.09, "M_PicketBack")


@prop("Fence_Run_S", cat="matched", anchor="W_FENCE_FS", view=(1.0, -0.6, 0.35),
      place=[("W_FENCE_FS", 0, ["W_FENCE_FS"]), ("E_FENCE_FS", 0, ["E_FENCE_FS"])],
      note="Picket fence 10.6 m (lawn south run, y 14.4..25), gate post at its north end. Symmetric in x.")
def fence_s(P):
    mn, mx, _ = brush("W_FENCE_FS")
    L = mx.y - mn.y
    since = P.nverts()
    fence_run(P, L, gate_ends=("n",))
    P.transform_last(Matrix.Translation((0, -L / 2, 0)), since)


@prop("Fence_Run_N", cat="matched", anchor="W_FENCE_FN", view=(1.0, -0.6, 0.35),
      place=[("W_FENCE_FN", 0, ["W_FENCE_FN"]), ("E_FENCE_FN", 0, ["E_FENCE_FN"])],
      note="Picket fence 5 m (lawn north run, y 27..32), gate post at its south end. Symmetric in x.")
def fence_n(P):
    mn, mx, _ = brush("W_FENCE_FN")
    L = mx.y - mn.y
    since = P.nverts()
    fence_run(P, L, gate_ends=("s",))
    P.transform_last(Matrix.Translation((0, -L / 2, 0)), since)


@prop("Fence_Picket_2m", cat="free", view=(1.0, -0.7, 0.4),
      note="Modular picket fence, 2 m long along Y (y -1..1), 0.3 thick, 1.2 tall, posts at both ends.")
def fence_2m(P):
    since = P.nverts()
    fence_run(P, 2.0)
    P.transform_last(Matrix.Translation((0, -1.0, 0)), since)


@prop("Fence_Picket_1m", cat="free", view=(1.0, -0.7, 0.4), note="Modular picket fence, 1 m (y -0.5..0.5).")
def fence_1m(P):
    since = P.nverts()
    fence_run(P, 1.0)
    P.transform_last(Matrix.Translation((0, -0.5, 0)), since)


@prop("Fence_Gate_1m", cat="free", view=(1.0, -0.7, 0.4),
      note="Picket gate leaf 1 m wide (hinge at y=0, leaf along +Y). For backdrop fences: the in-map gate gap "
           "(y 25..27) is open in collision, so leave it empty.")
def fence_gate(P):
    t = 0.05
    for z in (0.18, 0.86):
        P.box(-0.012, 0.03, z, 0.012, 0.97, z + 0.08, "M_PicketBack", bev=0.006)
    P.bar((0, 0.08, 0.24), (0, 0.92, 0.88), 0.07, 0.024, "M_PicketBack", up=(0, 0, 1))
    y = 0.02
    pw, gap = 0.088, 0.034
    while y + pw <= 0.99:
        poly = [(y, 0.06), (y + pw, 0.06), (y + pw, 1.04), (y + pw / 2, 1.12), (y, 1.04)]
        P.prism(poly, 0.012, 0.012 + 0.02, "M_Picket", axis="X", bev=0.004, seg=1)
        y += pw + gap
    P.box(0.032, 0.80, 0.62, 0.05, 0.88, 0.66, "M_SteelDark")


@prop("Fence_Post", cat="free", view=(1.0, -0.7, 0.4), note="Single picket fence post 0.3 x 0.14 x 1.2.")
def fence_post(P):
    P.box(-0.15, -0.07, 0, 0.15, 0.07, 1.2, "M_Picket", bev=0.012)
    P.box(-0.15, -0.07, 1.16, 0.15, 0.07, 1.2, "M_Picket", bev=0.018, seg=1)


# =============================================================================================== props: hedges
def hedge_block(P, x0, y0, z0, x1, y1, z1, mat="M_Hedge", step=0.32, amp=0.016, seed=0, bev=0.06):
    """Clipped hedge: bevelled box, sliced into a grid and pushed INWARD by leafy noise (never past the box)."""
    t = bmesh.new()
    bmesh.ops.create_cube(t, size=1.0)
    c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    s = Vector((x1 - x0, y1 - y0, z1 - z0))
    for v in t.verts:
        v.co = Vector((c.x + v.co.x * s.x, c.y + v.co.y * s.y, c.z + v.co.z * s.z))
    PL.bevel_bm(t, min(bev, 0.45 * min(s)), 2)
    for axis, lo, hi in ((0, x0, x1), (1, y0, y1), (2, z0, z1)):
        n = int((hi - lo) / step)
        for k in range(1, n + 1):
            co = [0, 0, 0]
            co[axis] = lo + (hi - lo) * k / (n + 1)
            no = [0, 0, 0]
            no[axis] = 1
            bmesh.ops.bisect_plane(t, geom=list(t.verts) + list(t.edges) + list(t.faces), plane_co=co, plane_no=no)
    bmesh.ops.triangulate(t, faces=[f for f in t.faces if len(f.verts) > 4])
    t.normal_update()
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    from mathutils import noise
    for v in t.verts:
        nv = v.normal
        k = 0.5 + 0.5 * noise.noise(v.co * 2.2 + off)
        k2 = 0.5 + 0.5 * noise.noise(v.co * 6.0 + off * 0.5)
        v.co = v.co - nv * amp * (0.65 * k + 0.35 * k2)
    P.merge(t, mat)


def hedge_ao(z_dark=0.55, lo=0.62, top=1.0, seed=1):
    from mathutils import noise

    def fn(co, n, mat):
        t = max(0.0, min(1.0, co.z / z_dark))
        t = t * t * (3 - 2 * t)
        f = lo + (1 - lo) * t
        f *= 0.86 + 0.14 * (0.5 + 0.5 * noise.noise(co * 0.9 + Vector((seed, 2 * seed, 0))))
        if n.z > 0.7:
            f = min(1.0, f * 1.08)
        return max(0.0, min(1.0, f * top))
    return fn


@prop("Hedge_Boundary", cat="matched", anchor="W_HEDGE", view=(1.0, -0.35, 0.3),
      place=[("W_HEDGE", 0, ["W_HEDGE"]), ("E_HEDGE", 0, ["E_HEDGE"])],
      note="Boundary hedge 1 x 46 x 3 m along Y (the player clip above it is invisible).")
def hedge_boundary(P):
    mn, mx, _ = brush("W_HEDGE")
    L = mx.y - mn.y
    hedge_block(P, -0.5, -L / 2, 0, 0.5, L / 2, 3.0, step=0.36, seed=3)


@prop("Hedge_Lawn", cat="matched", anchor="W_HEDGE_LAWN", view=(0.7, -1.0, 0.4),
      place=[("W_HEDGE_LAWN", 0, ["W_HEDGE_LAWN"]), ("E_HEDGE_LAWN", 0, ["E_HEDGE_LAWN"])],
      note="Lawn hedge 5.2 x 0.8 x 2.0 m along X.")
def hedge_lawn(P):
    hedge_block(P, -2.6, -0.4, 0, 2.6, 0.4, 2.0, step=0.3, seed=5)


@prop("Hedge_Block_2m", cat="free", view=(0.7, -1.0, 0.45), note="Garden hedge module 2 x 0.8 x 1.2 m along X.")
def hedge_2m(P):
    hedge_block(P, -1.0, -0.4, 0, 1.0, 0.4, 1.2, step=0.28, seed=7)


@prop("Hedge_Block_4m_Tall", cat="free", view=(0.7, -1.0, 0.45), note="Tall hedge module 4 x 1.0 x 2.4 m along X.")
def hedge_4m(P):
    hedge_block(P, -2.0, -0.5, 0, 2.0, 0.5, 2.4, step=0.32, seed=9)


@prop("Arbour", cat="matched", anchor="W_ARBOUR", view=(0.8, -1.0, 0.5),
      place=[("W_ARBOUR", 0, ["W_ARBOUR"]), ("E_ARBOUR", 0, ["E_ARBOUR"])],
      note="Vine-covered timber arbour, a solid 3 x 6 x 2.4 mass (posts and beams flush with the brush).")
def arbour(P):
    hx, hy, H = 1.5, 3.0, 2.4
    hedge_block(P, -hx + 0.003, -hy + 0.003, 0, hx - 0.003, hy - 0.003, H - 0.006, mat="M_Vine", step=0.3,
                amp=0.014, seed=11, bev=0.08)
    p = 0.14
    for sx in (-1, 1):
        for ya in (-hy, -hy / 3 - p / 2, hy / 3 - p / 2, hy - p):
            a, b = sorted((sx * hx, sx * (hx - p)))
            P.box(a, ya, 0, b, ya + p, H - 0.16, "M_Timber", bev=0.012)
        # long beam along the top edge
        a, b = sorted((sx * hx, sx * (hx - 0.12)))
        P.box(a, -hy, H - 0.16, b, hy, H, "M_Timber", bev=0.012)
    for k in range(9):
        y = -hy + 0.1 + k * (2 * hy - 0.2 - 0.08) / 8
        P.box(-hx, y, H - 0.09, hx, y + 0.08, H, "M_Timber", bev=0.01)
    # flower clusters set into the foliage (never proud of the brush)
    r = PL.rng(4)
    for i in range(60):
        side = r.choice(("x", "y", "z"))
        if side == "z":
            c = (r.uniform(-hx + 0.3, hx - 0.3), r.uniform(-hy + 0.3, hy - 0.3), H - 0.05)
        elif side == "x":
            c = (r.choice((-1, 1)) * (hx - 0.05), r.uniform(-hy + 0.3, hy - 0.3), r.uniform(0.7, H - 0.3))
        else:
            c = (r.uniform(-hx + 0.3, hx - 0.3), r.choice((-1, 1)) * (hy - 0.05), r.uniform(0.7, H - 0.3))
        P.blob(c, 0.065, r.choice(("M_Flower", "M_FlowerWhite")), scale=(1, 1, 0.8), sub=1, amp=0.2, seed=i)


# =============================================================================================== props: pylon + cables
@prop("Pylon", cat="matched", anchor="W_PYLON_MAST", view=(0.9, -1.0, 0.35),
      place=[("W_PYLON_MAST", 0, ["W_PYLON_MAST", "W_PYLON_PAD"]), ("E_PYLON_MAST", 180, ["E_PYLON_MAST", "E_PYLON_PAD"])],
      ghost_ok=["crossarm + insulators at z 5.8-6.1", "zipline clamp", "transformer box on the north face z 4.8-5.5",
                "pad brackets under the pad", "step bolts"],
      note="Square concrete utility pylon (0.5 x 0.5 x 6.6) with the 2 x 2 m service pad (top z 4.0, perch) and the "
           "zipline anchor at z 6.3 on its +X (street) side.")
def pylon(P):
    h = 0.25
    P.box(-h, -h, 0, h, h, 6.6, "M_PoleConcrete", bev=0.035, seg=2)
    P.box(-h, -h, 0, h, h, 0.35, "M_Concrete", bev=0.008)   # footing collar inside the mast collision
    P.box(-h + 0.03, -h + 0.03, 6.58, h - 0.03, h - 0.03, 6.6, "M_SteelDark")
    # pad: steel deck 2 x 2 at 3.85..4.0, grating top, yellow toe edge
    P.box(-1.0, -1.0, 3.85, 1.0, 1.0, 3.93, "M_SteelGalv", bev=0.01)
    P.box(-0.985, -0.985, 3.93, 0.985, 0.985, 4.0, "M_Grating", bev=0.004)
    for k in range(9):
        u = -0.9 + k * 0.225
        P.box(u - 0.012, -0.985, 3.995, u + 0.012, 0.985, 4.0, "M_SteelDark")
    for (a, b, c, d) in ((-1.0, -1.0, 1.0, -0.94), (-1.0, 0.94, 1.0, 1.0), (-1.0, -0.94, -0.94, 0.94),
                         (0.94, -0.94, 1.0, 0.94)):
        P.box(a, b, 3.85, c, d, 4.0, "M_SafetyYellow", bev=0.006)
    # brackets under the pad (close to the mast)
    for ang in (0, 90, 180, 270):
        rot = Matrix.Rotation(math.radians(ang), 4, "Z")
        p0 = rot @ Vector((h, 0, 3.25))
        p1 = rot @ Vector((0.85, 0, 3.85))
        P.bar(p0, p1, 0.07, 0.07, "M_SteelGalv")
    # step bolts up the -X face
    for k in range(10):
        z = 1.9 + k * 0.42
        if 3.7 < z < 4.15:
            continue
        sy = 0.09 if k % 2 else -0.09
        P.cyl((-h, sy, z), (-h - 0.14, sy, z), 0.014, "M_SteelGalv", n=6)
    # crossarm (N-S, perpendicular to the zipline) with insulators
    P.box(-0.07, -0.85, 5.82, 0.07, 0.85, 5.96, "M_SteelGalv", bev=0.01)
    for y in (-0.72, 0.72):
        P.lathe([(0.0, 0.0), (0.045, 0.0), (0.06, 0.05), (0.04, 0.08), (0.06, 0.12), (0.04, 0.15), (0.06, 0.19),
                 (0.03, 0.24), (0.0, 0.24)], "M_Insulator", n=10, c=(0, y, 5.96))
    # zipline anchor clamp on +X (the street side)
    P.box(h, -0.11, 6.18, h + 0.12, 0.11, 6.42, "M_SteelDark", bev=0.02)
    P.cyl((h + 0.12, 0, 6.3), (h + 0.2, 0, 6.3), 0.04, "M_SteelDark", n=10)
    # transformer box on the north face (+Y) high up, with a yellow band (concept)
    P.box(-0.23, h, 4.85, 0.23, h + 0.26, 5.5, "M_CabinetWhite", bev=0.03)
    P.box(-0.235, h + 0.0, 4.95, 0.235, h + 0.265, 5.03, "M_SafetyYellow", bev=0.006)
    P.box(-0.18, h + 0.26, 4.88, 0.18, h + 0.268, 4.92, "M_SteelDark")
    P.tube([(0.12, h + 0.15, 4.85), (0.12, h + 0.15, 4.6), (0.1, h + 0.03, 4.3)], 0.022, "M_Cable", n=6)


@prop("Zipline_Cable", cat="matched", view=(0.0, -1.0, 0.25),
      note="Sagging zipline cable between the pylon anchors (25, 45.5, 6.3) -> (47, 45.5, 6.3), 0.8 m sag. "
           "Origin = west anchor; place at (25, 45.5, 6.3) with yaw 0. Thin cable = allowed small detail.")
def zipline(P):
    pts = catenary((0.2, 0, 0), (22.0 - 0.2, 0, 0), 0.8, n=48)
    P.tube(pts, 0.022, "M_Cable", n=8)


@prop("Wire_Span_20m", cat="free", view=(0.0, -1.0, 0.25),
      note="Sagging overhead wire, 20 m along +X from the origin, 0.55 m sag, r 1.5 cm. Scale X for other spans.")
def wire_span(P):
    P.tube(catenary((0, 0, 0), (20.0, 0, 0), 0.55, n=40), 0.015, "M_Cable", n=6)


# =============================================================================================== completed fixtures
def paired(name, tag, yaw=0, note="", **kw):
    return prop(name, cat="matched", anchor="W_" + tag,
                place=[("W_" + tag, 0, ["W_" + tag]), ("E_" + tag, yaw, ["E_" + tag])], note=note, **kw)


def cabinet(P, w, d, h, body="M_CabinetWhite", top="M_Worktop", face="Y", n=4):
    """Solid-backed cabinetry: 8 mm recesses, bevelled doors and a proud worktop, all inside the brush."""
    x, y = w / 2, d / 2
    P.box(-x, -y, 0, x, y, h - 0.05, body, bev=0.008, seg=1)
    P.box(-x, -y, h - 0.05, x, y, h, top, bev=0.008, seg=1)
    if face == "Y":
        P.box(-x + 0.03, -y - 0.004, 0.08, x - 0.03, -y + 0.006, h - 0.08, "M_TrimDark")
        for k in range(n):
            a, b = -x + 0.035 + k * (w - 0.07) / n, -x + 0.035 + (k + 1) * (w - 0.07) / n
            P.box(a + 0.006, -y - 0.008, 0.09, b - 0.006, -y + 0.005, h - 0.09, body, bev=0.003, seg=1)
            P.box(b - 0.11, -y - 0.014, h - 0.18, b - 0.045, -y - 0.008, h - 0.165, "M_SteelDark")
    else:
        P.box(x - 0.006, -y + 0.03, 0.08, x + 0.004, y - 0.03, h - 0.08, "M_TrimDark")
        for k in range(n):
            a, b = -y + 0.035 + k * (d - 0.07) / n, -y + 0.035 + (k + 1) * (d - 0.07) / n
            P.box(x - 0.005, a + 0.006, 0.09, x + 0.008, b - 0.006, h - 0.09, body, bev=0.003, seg=1)
            P.box(x + 0.008, b - 0.13, h - 0.18, x + 0.014, b - 0.04, h - 0.165, "M_SteelDark")


@paired("HotTub", "HOTTUB", note="Closed insulated hot-tub cover; cap fills the 2.5 m square collision, no false opening.")
def hot_tub(P):
    P.box(-1.25, -1.25, 0, 1.25, 1.25, 0.86, "M_WoodStainedH", bev=0.016, seg=1)
    P.box(-1.25, -1.25, 0.86, 1.25, 1.25, 1.0, "M_WaterCover", bev=0.018, seg=2)
    for k in (-1, 1):
        P.box(-1.21, k * 0.56 - 0.015, 0.997, 1.21, k * 0.56 + 0.015, 1.004, "M_TrimDark")
    P.box(-0.19, -1.254, 0.71, 0.19, -1.248, 0.77, "M_TrimCream", bev=0.006)


@paired("OutdoorKitchen", "BBQ", yaw=180, note="Solid printed-concrete outdoor kitchen / storage wall, capped at collision height 2.2 m.")
def outdoor_kitchen(P):
    cabinet(P, 3.0, 1.0, 2.2, "M_Printed", "M_TrimCream", face="Y", n=4)
    P.box(-0.65, -0.512, 0.97, 0.70, -0.506, 1.48, "M_Anthracite", bev=0.008)
    for z in (1.05, 1.10, 1.15, 1.20, 1.25):
        P.box(-0.59, -0.519, z, 0.64, -0.512, z + 0.012, "M_SteelGalv", bev=0.003)


@paired("KitchenIsland", "ISLAND", note="Alternative library cabinet; houses.glb owns the placed island.")
def kitchen_island(P):
    cabinet(P, 2.0, 2.5, 1.0, "M_CabinetWhite", "M_Worktop", face="X", n=4)


@paired("Workbench", "WORKBENCH", yaw=180, note="Solid tool cupboard with proud timber top; placed fixture belongs to houses.glb.")
def workbench(P):
    cabinet(P, 0.7, 4.0, 1.0, "M_Anthracite", "M_TimberH", face="X", n=4)


@paired("Dresser", "DRESSER", yaw=180, note="Four inset timber drawer fronts. Alternative library fixture; placed dresser in houses.glb.")
def dresser(P):
    P.box(-0.30, -1.0, 0, 0.30, 1.0, 1.2, "M_WoodStained", bev=0.006, seg=1)
    for k in range(4):
        z = 0.08 + k * 0.27
        P.box(0.295, -0.955, z, 0.308, 0.955, z + 0.255, "M_TimberH", bev=0.004, seg=1)
        P.box(0.308, -0.16, z + 0.13, 0.315, 0.16, z + 0.15, "M_SteelDark", bev=0.002)


@paired("Shelving", "SHELF", note="Solid-backed stocked garage shelving; original houses.glb placement retained.")
def shelving(P):
    P.box(-2.0, -0.275, 0, 2.0, 0.275, 2.2, "M_Anthracite", bev=0.006, seg=1)
    for level in range(4):
        z = level * 0.54 + 0.03
        P.box(-2.0, -0.282, z, 2.0, -0.273, z + 0.04, "M_SteelGalv")
        for k in range(6):
            x = -1.91 + k * 0.64
            P.box(x, -0.284, z + 0.04, x + 0.56, -0.277, min(z + 0.50, 2.2), "M_Cardboard", bev=0.002)
    for x in (-1.99, -1.0, 0, 1.0, 1.99):
        P.box(x - 0.015, -0.289, 0, x + 0.015, -0.275, 2.2, "M_SteelGalv")


@paired("HeatPump", "HEATPUMP", note="Slatted heat-pump cabinet alternative; houses.glb owns the terrace fixture.")
def heat_pump(P):
    P.box(-1, -0.5, 0, 1, 0.5, 1.2, "M_CabinetWhite", bev=0.012, seg=2)
    P.cyl((-0.38, -0.509, 0.61), (-0.38, -0.501, 0.61), 0.41, "M_SteelDark", n=24)
    for k in range(15):
        z = 0.22 + k * 0.055
        half = math.sqrt(max(0.0, 0.40 ** 2 - (z - 0.61) ** 2))
        if half:
            P.box(-0.38 - half, -0.516, z, -0.38 + half, -0.507, z + 0.011, "M_SteelGalv")
    for k in range(13):
        z = 0.16 + k * 0.065
        P.box(0.30, -0.512, z, 0.87, -0.501, z + 0.033, "M_TrimDark", bev=0.004, seg=1)


@paired("GarageCar", "GARAGE_CAR", note="Boxy silver compact electric pod, closed skirts and collision-height roof; library variant.")
def garage_car(P):
    P.box(-0.95, -2.2, 0, 0.95, 2.2, 0.81, "M_CarSilver", bev=0.012, seg=2)
    P.box(-0.95, -2.2, 0.81, 0.95, 2.2, 1.4, "M_GlassDark", bev=0.012, seg=2)
    P.box(-0.95, -2.2, 1.4, 0.95, 2.2, 1.5, "M_CarSilver", bev=0.012, seg=2)
    for side in (-1, 1):
        x0, x1 = sorted((side * 0.95, side * 0.965))
        for y in (-1.48, 1.48):
            P.cyl((x0, y, 0.34), (x1, y, 0.34), 0.32, "M_Tyre", n=16)
            P.cyl((x0, y, 0.34), (x1 + 0.001, y, 0.34), 0.16, "M_Rim", n=12)
        for y in (-1.20, 0, 1.20):
            P.box(x0, y - 0.035, 0.82, x1, y + 0.035, 1.4, "M_CarSilver")
    for x in (-0.62, 0.62):
        P.box(x - 0.14, 2.2, 0.60, x + 0.14, 2.212, 0.71, "M_HeadLight", bev=0.01)


@paired("RainTank", "TANK", note="Square rain-water tank matches the solid 3.2 x 3.2 x 2.8 brush, painted sage.")
def rain_tank(P):
    P.box(-1.6, -1.6, 0, 1.6, 1.6, 2.8, "M_TankPaint", bev=0.012, seg=2)
    for k in range(1, 12):
        z = k * 0.22
        P.box(-1.607, -1.607, z, 1.607, 1.607, z + 0.020, "M_TankPaint", bev=0.008, seg=1)
    P.box(-0.38, -0.38, 2.794, 0.38, 0.38, 2.808, "M_TrimDark", bev=0.01)
    P.box(-0.14, -1.614, 0.16, 0.14, -1.604, 0.40, "M_SteelDark", bev=0.006)


@paired("BinStore", "BINS", yaw=180, note="Closed timber bin store fills full solid brush; bin lids are relief, not false enterable recesses.")
def bin_store(P):
    P.box(-1.5, -3.0, 0, 1.5, 3.0, 2.12, "M_WoodStained", bev=0.010, seg=1)
    P.box(-1.5, -3.0, 2.12, 1.5, 3.0, 2.2, "M_TimberH", bev=0.01, seg=1)
    for k, mat in enumerate(("M_BinLidGreen", "M_BinLidBlue", "M_BinLidBrown")):
        ya, yb = -2.8 + k * 1.9, -1.05 + k * 1.9
        P.box(1.499, ya, 0.18, 1.508, yb, 1.70, "M_BinGrey", bev=0.008, seg=1)
        P.box(1.500, ya - 0.02, 1.70, 1.514, yb + 0.02, 1.88, mat, bev=0.008, seg=1)
        P.box(1.508, (ya + yb) / 2 - 0.18, 1.54, 1.516, (ya + yb) / 2 + 0.18, 1.58, "M_SteelDark")


@paired("ParcelLockers", "LOCKERS", yaw=180, note="Eight-metre parcel bank, deeply inset doors with dark 12 mm joints and tiny proud pulls.")
def parcel_lockers(P):
    P.box(-1, -4, 0, 1, 4, 2.2, "M_LockerBody", bev=0.006, seg=1)
    P.box(0.992, -3.92, 0.10, 1.002, 3.92, 2.10, "M_TrimDark")
    for col in range(8):
        ya = -3.916 + col * 0.979
        for row in range(3):
            za = 0.11 + row * 0.655
            P.box(0.996, ya + 0.006, za + 0.006, 1.008, ya + 0.967, za + 0.644,
                  "M_LockerDoor", bev=0.003, seg=1)
            P.box(1.008, ya + 0.86, za + 0.24, 1.016, ya + 0.905, za + 0.34, "M_Anthracite", bev=0.003)
    P.box(1.009, -0.18, 0.90, 1.016, 0.18, 1.31, "M_GlassDark", bev=0.004)


@prop("ChargerIsland", cat="matched", anchor="C_CHARGER", place=[("C_CHARGER", 0, ["C_CHARGER"])],
      note="Closed service / charging cabinet island, footprint 2 x 4 m. Opaque to its collision faces.")
def charger(P):
    P.box(-1, -2, 0, 1, 2, 0.18, "M_Concrete", bev=0.01, seg=1)
    P.box(-1, -2, 0.18, 1, 2, 2.4, "M_CabinetWhite", bev=0.012, seg=2)
    for side in (-1, 1):
        xa, xb = sorted((side * 1.0, side * 1.012))
        for y in (-1.06, 1.06):
            P.box(xa, y - 0.32, 1.05, xb, y + 0.32, 1.75, "M_Anthracite", bev=0.005)
            P.box(xa, y - 0.24, 1.22, xb, y + 0.24, 1.59, "M_GlassDark", bev=0.003)
            P.tube([(side * 1.009, y - 0.24, 1.05), (side * 1.010, y - 0.28, 0.43),
                    (side * 1.010, y + 0.22, 0.43), (side * 1.009, y + 0.24, 1.04)],
                   0.006, "M_Cable", n=6)


@prop("ModelTable", cat="matched", anchor="C_MODEL", place=[("C_MODEL", 0, ["C_MODEL"])],
      note="Solid sales-office plinth / display table. Map model is flat original geometric relief under a flush lid.")
def model_table(P):
    P.box(-2, -1, 0, 2, 1, 0.94, "M_TrimCream", bev=0.012, seg=1)
    P.box(-2, -1, 0.94, 2, 1, 1.0, "M_ModelGreen", bev=0.008, seg=1)
    for x in (-0.95, 0.95):
        P.box(x - 0.32, -0.40, 0.991, x + 0.32, 0.40, 1.008, "M_ModelWhite", bev=0.005)
    P.box(-0.24, -0.86, 0.999, 0.24, 0.86, 1.010, "M_TrimDark")


@prop("ShuttleStop", cat="matched", anchor="C_SHUTTLE", place=[("C_SHUTTLE", 0, ["C_SHUTTLE"])],
      note="Closed opaque shuttle shelter / service screen. The collision is a solid box, so no ghost interior.")
def shuttle(P):
    P.box(-2, -1, 0, 2, 1, 2.50, "M_CabinetWhite", bev=0.006, seg=1)
    P.box(-2, -1, 2.5, 2, 1, 2.6, "M_TrimDark", bev=0.006, seg=1)
    P.box(-1.87, 0.997, 0.32, 1.87, 1.009, 2.32, "M_GH_Panel", bev=0.004, seg=1)
    for x in (-1.40, 0, 1.40):
        P.box(x - 0.025, 1.004, 0.20, x + 0.025, 1.012, 2.45, "M_GH_Frame")
    P.box(-1.55, 1.01, 0.42, 1.55, 1.016, 0.51, "M_WoodStainedH", bev=0.003)


# =============================================================================================== small painted site kit
def pallet(P, c=(0, 0, 0), w=1.2, d=0.8):
    x, y, z = c
    for sx in (-1, 0, 1):
        P.boxc((x + sx * (w / 2 - 0.12), y, z + 0.065), (0.15, d, 0.13), "M_TimberH", bev=0.005, seg=1)
    for k in range(5):
        yy = y - d / 2 + 0.067 + k * (d - 0.134) / 4
        P.boxc((x, yy, z + 0.148), (w, 0.12, 0.036), "M_TimberH", bev=0.004, seg=1)


@prop("Pallet", note="Original reusable 1.2 x 0.8 m timber pallet. Outside-play dressing only.")
def site_pallet(P):
    pallet(P)


@prop("PrintedBlockStack", note="Layer-beaded printed blocks stacked on a timber pallet; site dressing only.")
def printed_block_stack(P):
    pallet(P)
    for level in range(3):
        z = 0.167 + level * 0.27
        for ix in range(2):
            for iy in range(2):
                x, y = -0.57 + ix * 0.585, -0.37 + iy * 0.385
                for bead in range(6):
                    P.box(x, y, z + bead * 0.04, x + 0.555, y + 0.355, z + bead * 0.04 + 0.034,
                          "M_Printed", bev=0.006, seg=1)
    for x in (-0.34, 0.34):
        P.box(x - 0.01, -0.398, 0.15, x + 0.01, -0.389, 0.966, "M_SteelDark")
        P.box(x - 0.01, -0.398, 0.958, x + 0.01, 0.398, 0.966, "M_SteelDark")
        P.box(x - 0.01, 0.389, 0.15, x + 0.01, 0.398, 0.966, "M_SteelDark")


@prop("RebarBundle", note="18 six-metre rebar rods with two packing straps and bearers, 8-sided cylinders.")
def rebar_bundle(P):
    for x in (-2.1, 2.1):
        P.boxc((x, 0, 0.06), (0.14, 0.65, 0.12), "M_TimberH", bev=0.004, seg=1)
    for row, count in enumerate((6, 5, 4, 3)):
        for k in range(count):
            y = (k - (count - 1) / 2) * 0.061
            z = 0.152 + row * 0.052
            P.cyl((-3, y, z), (3, y, z), 0.029, "M_SiteSteel", n=8, flat=True)
    for x in (-1.85, 1.85):
        P.tube([(x, -0.21, 0.13), (x, -0.21, 0.34), (x, 0.21, 0.34),
                (x, 0.21, 0.13), (x, -0.21, 0.13)], 0.008, "M_SteelDark", n=4)


@prop("CementBag", note="Soft painted cement bag with paper folds and original two-bar colour mark, no text.")
def cement_bag(P):
    P.box(-0.31, -0.18, 0.006, 0.31, 0.18, 0.16, "M_CementBag", bev=0.06, seg=2)
    for x in (-0.27, 0.27):
        P.box(x - 0.015, -0.145, 0.08, x + 0.015, 0.145, 0.156, "M_CementBag", bev=0.012, seg=1)
    for y in (-0.035, 0.03):
        P.box(-0.19, y - 0.015, 0.151, 0.19, y + 0.015, 0.163, "M_BagStripe", bev=0.004, seg=1)


@prop("CementBagPallet", note="Sixteen clean paper cement bags with quiet sage bands on a timber pallet.")
def cement_bag_pallet(P):
    pallet(P)
    for level in range(4):
        for i in range(2):
            for j in range(2):
                since = P.nverts()
                cement_bag(P)
                mx = Matrix.Translation(((i - 0.5) * 0.57, (j - 0.5) * 0.36, 0.165 + level * 0.15))
                P.transform_last(mx, since)


@prop("TrafficCone", note="Low-poly orange safety cone, two cream bands, heavy bevelled rubber base. Height 0.75 m.")
def traffic_cone(P):
    P.box(-0.24, -0.24, 0, 0.24, 0.24, 0.055, "M_Rubber", bev=0.026, seg=1)
    levels = ((0.055, 0.25, 0.18, 0.135, "M_SiteOrange"), (0.25, 0.34, 0.135, 0.114, "M_TrimCream"),
              (0.34, 0.47, 0.114, 0.084, "M_SiteOrange"), (0.47, 0.55, 0.084, 0.065, "M_TrimCream"),
              (0.55, 0.75, 0.065, 0.020, "M_SiteOrange"))
    for za, zb, ra, rb, mat in levels:
        P.cyl((0, 0, za), (0, 0, zb), ra, mat, n=12, r2=rb)


@prop("PlasticBarrier", note="Chunky 2 m water-filled site barrier with recessed grips, feet and cream chevron strips.")
def plastic_barrier(P):
    profile = [(-0.32, 0), (0.32, 0), (0.32, 0.17), (0.22, 0.47), (0.12, 0.98),
               (-0.12, 0.98), (-0.22, 0.47), (-0.32, 0.17)]
    P.prism(profile, -1, 1, "M_SiteOrange", axis="X", bev=0.025, seg=1)
    for side in (-1, 1):
        for x in (-0.72, -0.24, 0.24, 0.72):
            P.boxc((x, side * 0.122, 0.84), (0.28, 0.016, 0.10), "M_TrimDark", bev=0.009, seg=1)
        for x in (-0.6, 0, 0.6):
            P.quad([(x - 0.11, side * 0.20, 0.48), (x + 0.10, side * 0.20, 0.48),
                    (x + 0.21, side * 0.142, 0.74), (x, side * 0.142, 0.74)], "M_TrimCream", flat=True)
    for x in (-0.82, 0.82):
        P.boxc((x, 0, 0.03), (0.25, 0.76, 0.06), "M_SiteOrange", bev=0.012, seg=1)


@prop("Rock_Low", note="Original broad stylized boulder, faceted clean painted planes, no photo noise.")
def rock_low(P):
    P.blob((0, 0, 0.12), 0.65, "M_Rock", scale=(1.0, 0.78, 0.58), sub=1, amp=0.12, seed=311,
           flat=True, zclip=-0.11)


@prop("Rock_Tall", note="Asymmetric angular garden / plot rock, broad low-poly silhouette.")
def rock_tall(P):
    P.blob((0, 0, 0.22), 0.58, "M_Rock", scale=(0.74, 0.85, 1.0), sub=1, amp=0.16, seed=512,
           flat=True, zclip=-0.21)


@prop("PebbleCluster", note="Nine painted low-poly pebbles; library dressing outside the play area or inside planter collision.")
def pebble_cluster(P):
    rr = PL.rng(28)
    for k in range(9):
        r = rr.uniform(0.055, 0.13)
        P.blob((rr.uniform(-0.40, 0.40), rr.uniform(-0.30, 0.30), r * 0.27), r, "M_Pebble",
               scale=(1.0, rr.uniform(0.65, 0.85), 0.58), sub=1, amp=0.12, seed=k + 331, flat=True,
               zclip=-r * 0.25)


@prop("DirtMound", note="Two-metre low-poly trodden earth mound, painted v2 packed dirt, plot dressing only.")
def dirt_mound(P):
    P.blob((0, 0, 0.03), 1.1, "M_SiteDirt", scale=(1.15, 0.72, 0.35), sub=2, amp=0.17, seed=491,
           flat=True, zclip=-0.029)


@prop("SandMound", note="Broad construction sand pile with calm warm colour and large facets.")
def sand_mound(P):
    P.blob((0, 0, 0.03), 1.3, "M_SiteSand", scale=(1.0, 0.95, 0.42), sub=2, amp=0.11, seed=513,
           flat=True, zclip=-0.029)


# =============================================================================================== remaining architecture
def flat_roof(P, mn, mx, glazed=False):
    """Flush standable cap: recessed surface, wide proud coping with bevelled underside / drip, corner outlet.
    The 12 mm coping-to-surface step stays under the existing 2 cm alignment allowance."""
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    lip = 0.12
    P.box(x0, y0, z0, x1, y1, z1 - 0.018, "M_TrimCream", bev=0.006, seg=1)
    P.box(x0 + lip, y0 + lip, z1 - 0.018, x1 - lip, y1 - lip, z1 - 0.012,
          "M_GH_Roof" if glazed else "M_RoofMembrane", bev=0.002, seg=1)
    for xa, ya, xb, yb in ((x0, y0, x1, y0 + lip), (x0, y1 - lip, x1, y1),
                          (x0, y0 + lip, x0 + lip, y1 - lip), (x1 - lip, y0 + lip, x1, y1 - lip)):
        P.box(xa, ya, z1 - 0.028, xb, yb, z1, "M_TrimCream", bev=0.004, seg=1)
    # Physical drip below the coping, and an opaque drain grate in the recessed surface.
    for xa, xb in ((x0 + 0.008, x0 + 0.015), (x1 - 0.015, x1 - 0.008)):
        P.box(xa, y0 + 0.04, z1 - 0.033, xb, y1 - 0.04, z1 - 0.027, "M_TrimDark")
    dx, dy = x1 - lip - 0.18, y1 - lip - 0.18
    P.box(dx, dy, z1 - 0.012, dx + 0.15, dy + 0.15, z1 - 0.008, "M_SteelDark", bev=0.004)
    for k in range(4):
        xx = dx + 0.025 + k * 0.032
        P.box(xx, dy + 0.008, z1 - 0.008, xx + 0.006, dy + 0.142, z1 - 0.006, "M_SteelGalv")


def beaded_wall(P, mn, mx):
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    # 4 cm printing courses retain the exact collision footprint. Rounded beads expose recessed joints.
    za = z0
    while za < z1 - 0.001:
        zb = min(z1, (math.floor((za + 0.001) / 0.04) + 1) * 0.04)
        P.box(x0, y0, za, x1, y1, zb, "M_Printed", bev=min(0.006, (zb - za) * 0.20), seg=1)
        za = zb


def structure_model(P, sid, anchor):
    origin = base_centre(anchor)
    bs = [b for b in LAYOUT.brushes(structure=sid) if b["kind"] != "PlayerClip"
          and b["look"] in ("Wall", "Roof")]
    greenhouse = "GREENHOUSE" in sid
    shed = "SHED" in sid
    st = LAYOUT.structure(sid)
    # These replace ground's former pod-floor placeholders. Under-wall overlap is harmless; the top is
    # only 8 mm above the flat ground collision and the interior receives an actual UV'd v2 floor.
    fmn, fmx = Vector(st["min"]) - origin, Vector(st["max"]) - origin
    P.box(fmn.x + 0.1, fmn.y + 0.1, -origin.z, fmx.x - 0.1, fmx.y - 0.1, 0.008 - origin.z,
          "M_Concrete", bev=0.0)
    for b in bs:
        mn, mx = Vector(b["min"]) - origin, Vector(b["max"]) - origin
        if b["look"] == "Roof":
            flat_roof(P, mn, mx, glazed=greenhouse)
        elif greenhouse:
            x0, y0, z0 = mn
            x1, y1, z1 = mx
            if z0 < 0.35:
                P.box(x0, y0, z0, x1, y1, min(0.35, z1), "M_KickClay" if sid.startswith("CLAY") else "M_KickSage",
                      bev=0.004, seg=1)
            if z1 > 0.35:
                P.box(x0, y0, max(z0, 0.35), x1, y1, z1, "M_GH_Panel", bev=0.004, seg=1)
                # Frame borders lie on the wall's opaque panel, never across an opening.
                if x1 - x0 > y1 - y0:
                    for x in (x0, x1 - 0.035):
                        P.box(x, y0 - 0.006, max(z0, 0.35), x + 0.035, y1 + 0.006, z1, "M_GH_Frame")
                else:
                    for y in (y0, y1 - 0.035):
                        P.box(x0 - 0.006, y, max(z0, 0.35), x1 + 0.006, y + 0.035, z1, "M_GH_Frame")
        elif shed:
            P.box(*mn, *mx, "M_ShedClay" if sid.startswith("CLAY") else "M_WoodStained", bev=0.008, seg=1)
        else:
            beaded_wall(P, mn, mx)
    # Window/door reveals: border inset into solid wall, leaving the collision opening empty.
    for op in LAYOUT.openings(structure=sid):
        wall = LAYOUT.brushes(tag=op["wall"])[0]
        axis = "x" if wall["max"][0] - wall["min"][0] < wall["max"][1] - wall["min"][1] else "y"
        u0, u1 = op["span"]
        za, zb = op["sill"], op["head"]
        if axis == "x":
            x0, x1 = wall["min"][0] - origin.x, wall["max"][0] - origin.x
            for ua, ub in ((u0 - 0.045, u0 + 0.006), (u1 - 0.006, u1 + 0.045)):
                P.box(x0 - 0.006, ua - origin.y, za - origin.z, x1 + 0.006, ub - origin.y,
                      zb - origin.z, "M_TrimCream", bev=0.003, seg=1)
            P.box(x0 - 0.006, u0 - origin.y, zb - origin.z - 0.006, x1 + 0.006, u1 - origin.y,
                  zb - origin.z + 0.045, "M_TrimCream", bev=0.003, seg=1)
        else:
            y0, y1 = wall["min"][1] - origin.y, wall["max"][1] - origin.y
            for ua, ub in ((u0 - 0.045, u0 + 0.006), (u1 - 0.006, u1 + 0.045)):
                P.box(ua - origin.x, y0 - 0.006, za - origin.z, ub - origin.x, y1 + 0.006,
                      zb - origin.z, "M_TrimCream", bev=0.003, seg=1)
            P.box(u0 - origin.x, y0 - 0.006, zb - origin.z - 0.006, u1 - origin.x, y1 + 0.006,
                  zb - origin.z + 0.045, "M_TrimCream", bev=0.003, seg=1)
            if op["kind"] == "window":
                P.box(u0 - origin.x - 0.02, y0 - 0.008, za - origin.z - 0.055, u1 - origin.x + 0.02,
                      y1 + 0.008, za - origin.z + 0.006, "M_TrimCream", bev=0.004, seg=1)


def register_structure(name, sid, anchor):
    tags = sorted({b["tag"]["id"] for b in LAYOUT.brushes(structure=sid) if b["look"] in ("Wall", "Roof")})
    def fn(P):
        structure_model(P, sid, anchor)
    prop(name, cat="matched", anchor=anchor, place=[(anchor, 0, tags)],
         note="Complete " + sid + ": exact collision wall pieces / open holes, flush recessed flat roof with coping and drain.")(fn)


for _name, _sid, _anchor in (("Greenhouse_Sage", "SAGE_GREENHOUSE", "W_GH_WALL_S"),
                            ("Greenhouse_Clay", "CLAY_GREENHOUSE", "E_GH_WALL_S"),
                            ("Studio_Sage", "SAGE_STUDIO", "W_ST_WALL_S"),
                            ("Studio_Clay", "CLAY_STUDIO", "E_ST_WALL_S"),
                            ("Shed_Sage", "SAGE_SHED", "W_SHED"), ("Shed_Clay", "CLAY_SHED", "E_SHED"),
                            ("SalesOffice", "SALES_OFFICE", "C_OF_WALL_S"), ("ParcelHub", "HUB", "C_HUB")):
    register_structure(_name, _sid, _anchor)


# =============================================================================================== build / export
def build(opts):
    root = bpy.data.collections.new("PROPS")
    bpy.context.scene.collection.children.link(root)
    out = []
    for r in REG:
        if opts["only"] and r["name"] not in opts["only"]:
            continue
        t0 = time.time()
        P = Prop(r["name"])
        r["fn"](P)
        ao = r["ao"]
        aofn = r.get("ao_fn")
        if aofn is None and r["name"].startswith(("Hedge", "Arbour")):
            aofn = hedge_ao()
        meta = dict(category=r["cat"], note=r["note"], brushes=json.dumps(r["place"]),
                    ghost_ok=json.dumps(r["ghost_ok"]))
        ob = P.finish(root, meta=meta, ao=ao, ao_fn=aofn)
        r["obj"] = ob
        tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        mn = Vector([min(v.co[i] for v in ob.data.vertices) for i in range(3)])
        mx = Vector([max(v.co[i] for v in ob.data.vertices) for i in range(3)])
        r["tris"], r["bbox"] = tris, (tuple(round(c, 3) for c in mn), tuple(round(c, 3) for c in mx))
        ob["tris"] = tris
        ob["size_m"] = [round(mx[i] - mn[i], 3) for i in range(3)]
        print(f"built {r['name']:24s} {tris:7d} tris  bbox {r['bbox']}  ({time.time() - t0:.1f}s)")
        out.append(r)
    return out


def placements(built):
    """World placements of the brush-matched props (design frame + Bevy)."""
    rows = []
    for r in built:
        for (anchor, yaw, tags) in r["place"]:
            if r["name"] == "Zipline_Cable":
                continue
            loc = base_centre(anchor)
            rows.append(dict(prop="PROP_" + r["name"], anchor=anchor, brushes=tags,
                             design_loc=[round(c, 4) for c in loc], yaw_deg=yaw,
                             bevy_translation=[round(c, 4) for c in LL.to_bevy(tuple(loc))],
                             bevy_yaw_rad=round(math.radians(yaw), 6),
                             owner="ground.glb" if r["name"] in GROUND_OWNED else
                                   "houses.glb" if r["name"] in HOUSE_OWNED else "props_placed.glb"))
        if r["name"] == "Zipline_Cable":
            z = LAYOUT.data.get("ziplines") or []
            a = (25.0, 45.5, 6.3)
            if z:
                a = tuple(z[0]["design"]["a"])
            rows.append(dict(prop="PROP_Zipline_Cable", anchor="ZIPLINE", brushes=[], design_loc=list(a), yaw_deg=0,
                             bevy_translation=list(LL.to_bevy(a)), bevy_yaw_rad=0.0, owner="ground.glb"))
    return rows


def material_parts(source, coll, name, loc=(0, 0, 0), yaw=0, meta=None):
    """Export one glTF mesh per material under a prop root. Source bmesh/API stays unchanged."""
    root = bpy.data.objects.new(name, None)
    root.location = loc
    root.rotation_euler.z = math.radians(yaw)
    coll.objects.link(root)
    for k in source.keys():
        root[k] = source[k]
    for k, v in (meta or {}).items():
        root[k] = v
    out = [root]
    for mi, mat in enumerate(source.data.materials):
        bm = bmesh.new()
        bm.from_mesh(source.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != mi], context="FACES")
        for f in bm.faces:
            f.material_index = 0
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        if not bm.faces:
            bm.free()
            continue
        me = bpy.data.meshes.new(name + "__" + mat.name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        if me.color_attributes:
            me.color_attributes.active_color = me.color_attributes.get("Col") or me.color_attributes[0]
        ob = bpy.data.objects.new(me.name, me)
        ob.parent = root
        coll.objects.link(ob)
        out.append(ob)
    return out


def glb_audit(path):
    """Validate the actual serialized GLB contract, not just the source objects."""
    raw = open(path, "rb").read()
    magic, version, size = struct.unpack_from("<4sII", raw)
    assert magic == b"glTF" and version == 2 and size == len(raw)
    jl = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20 + jl])
    tris = 0
    for me in doc.get("meshes", []):
        assert len(me["primitives"]) == 1, "Separate meshes required per material: " + me.get("name", "")
        for pr in me["primitives"]:
            assert "TEXCOORD_0" in pr["attributes"], "Missing UVs"
            tris += doc["accessors"][pr["indices"]]["count"] // 3
    return dict(file=os.path.basename(path), triangles_unique_meshes=tris,
                meshes=len(doc.get("meshes", [])), materials=[m.get("name") for m in doc.get("materials", [])],
                textures=len(doc.get("textures", [])), root_nodes=[doc["nodes"][n].get("name")
                    for n in doc["scenes"][doc.get("scene", 0)]["nodes"]],
                uv_verified=True, one_material_per_mesh_verified=True,
                normal_materials=sum("normalTexture" in m for m in doc.get("materials", [])),
                orm_materials=sum("occlusionTexture" in m for m in doc.get("materials", [])))


def export(built, rows, opts):
    os.makedirs(KIT, exist_ok=True)
    sc = bpy.context.scene
    suffix = "" if not opts["only"] else "_partial"
    lcol = bpy.data.collections.new("_LIBRARY_EXPORT")
    sc.collection.children.link(lcol)
    library = []
    for r in built:
        library += material_parts(r["obj"], lcol, "PROP_" + r["name"] + "_Root")
    def save_parts(objs, path):
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                                  export_yup=True, export_apply=True, export_extras=True,
                                  export_vertex_color="MATERIAL")
        print("exported", path)
        return glb_audit(path)
    audits = [save_parts(library, os.path.join(KIT, f"props{suffix}.glb"))]
    for ob in library:
        me = ob.data if ob.type == "MESH" else None
        bpy.data.objects.remove(ob, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    bpy.data.collections.remove(lcol)
    # Geometry already owned by the house / ground GLBs is excluded from this placed scene.
    pcol = bpy.data.collections.new("_PLACED")
    sc.collection.children.link(pcol)
    byname = {"PROP_" + r["name"]: r["obj"] for r in built}
    placed = []
    for row in rows:
        if row.get("owner", "props_placed.glb") != "props_placed.glb":
            continue
        src = byname.get(row["prop"])
        if src is None:
            continue
        placed += material_parts(src, pcol, f"{row['prop']}__{row['anchor']}", row["design_loc"], row["yaw_deg"],
                                 dict(anchor=row["anchor"], brushes_covered=json.dumps(row["brushes"])))
    if placed:
        audits.append(save_parts(placed, os.path.join(KIT, f"props_placed{suffix}.glb")))
    json.dump(dict(doc="Placements of the brush-matched Showhome props. design_loc: metres, x east, y north, z up "
                       "(Blender/layout frame). bevy_translation = (x, z, -y); bevy rotation = "
                       "Quat::from_rotation_y(bevy_yaw_rad). props.glb node = 'prop'.",
                   placements=rows, library_only=["PROP_" + r["name"] for r in built if not r["place"]
                   and r["name"] != "Zipline_Cable"],
                   game_load="Load houses.glb + ground.glb + props_placed.glb at identity. props.glb is a reusable "
                             "library of local-origin props and must not be loaded as a map scene. owner gives "
                             "the sole GLB that draws each placement."),
              open(os.path.join(KIT, f"props_placements{suffix}.json"), "w"), indent=1)
    json.dump(audits, open(os.path.join(KIT, f"props_export_audit{suffix}.json"), "w"), indent=2)
    json.dump(dict(total_library_triangles=sum(r["tris"] for r in built),
                   placed_triangles=sum(next(r["tris"] for r in built if "PROP_" + r["name"] == row["prop"])
                                        for row in rows if row.get("owner") == "props_placed.glb"),
                   props=[dict(name=r["name"], category=r["cat"], triangles=r["tris"], bounds=r["bbox"],
                               materials=[m.name for m in r["obj"].data.materials]) for r in built]),
              open(os.path.join(KIT, f"props_manifest{suffix}.json"), "w"), indent=2)
    return pcol, placed


# =============================================================================================== alignment check
def check(built, rows):
    """Dense art-vs-brush check for every placement. For each face of each covered brush, rays are cast from
    0.4 m outside toward the face on a 10 cm grid; the art must be hit within tol (2 cm; 12 cm within 6 cm of a
    face edge). Faces lying on the ground or on other collision are skipped. Ghosts: art vertices farther than
    2 cm outside every covered brush."""
    vis = LAYOUT.visible()
    byname = {"PROP_" + r["name"]: r for r in built}
    report = []
    for row in rows:
        r = byname.get(row["prop"])
        if r is None or not row["brushes"]:
            continue
        ob = r["obj"]
        mw = Matrix.Translation(row["design_loc"]) @ Matrix.Rotation(math.radians(row["yaw_deg"]), 4, "Z")
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.transform(mw)
        bvh = BVHTree.FromBMesh(bm)
        verts = [v.co.copy() for v in bm.verts]
        bm.free()
        bs = [b for tag in row["brushes"] for b in LAYOUT.brushes(tag=tag) if b["kind"] != "PlayerClip"]
        n = bad = 0
        worst = 0.0
        fails = []
        for b in bs:
            mn, mx = Vector(b["min"]), Vector(b["max"])
            for axis in range(3):
                for side in (0, 1):
                    nrm = Vector((0, 0, 0))
                    nrm[axis] = 1 if side else -1
                    plane = mx[axis] if side else mn[axis]
                    if axis == 2 and side == 0 and plane <= 0.001:
                        continue
                    u, v = [i for i in range(3) if i != axis]
                    nu = max(2, int((mx[u] - mn[u]) / 0.1))
                    nv = max(2, int((mx[v] - mn[v]) / 0.1))
                    for iu in range(nu + 1):
                        for iv in range(nv + 1):
                            p = Vector((0, 0, 0))
                            p[axis] = plane
                            p[u] = mn[u] + (mx[u] - mn[u]) * (0.002 + 0.996 * iu / nu)
                            p[v] = mn[v] + (mx[v] - mn[v]) * (0.002 + 0.996 * iv / nv)
                            q = p + nrm * 0.004
                            covered = False
                            for o in vis:
                                if o is b:
                                    continue
                                if all(o["min"][k] - 1e-4 <= q[k] <= o["max"][k] + 1e-4 for k in range(3)):
                                    covered = True
                                    break
                            if covered:
                                continue
                            edge_d = min(p[u] - mn[u], mx[u] - p[u], p[v] - mn[v], mx[v] - p[v])
                            tol = 0.12 if edge_d < 0.06 else 0.02
                            o0 = p + nrm * 0.4
                            hit = bvh.ray_cast(o0, -nrm, 0.8)
                            n += 1
                            dev = (hit[3] - 0.4) if hit[0] is not None else 0.4
                            if abs(dev) > tol and edge_d < 0.06:
                                # bevelled edge / corner: the art only has to be within tol of the face point
                                nb = bvh.find_nearest(p, tol)
                                if nb[0] is not None:
                                    dev = nb[3]
                            if abs(dev) > tol:
                                bad += 1
                                worst = max(worst, abs(dev))
                                if len(fails) < 12:
                                    fails.append(dict(p=[round(c, 3) for c in p], n=list(nrm), dev=round(dev, 3)))
        # ghosts
        gh = []
        for co in verts:
            inside = any(all(bb["min"][k] - 0.02 <= co[k] <= bb["max"][k] + 0.02 for k in range(3)) for bb in bs)
            if not inside:
                gh.append(co)
        gbox = None
        if gh:
            gbox = [[round(min(c[k] for c in gh), 3) for k in range(3)], [round(max(c[k] for c in gh), 3) for k in range(3)]]
        rep = dict(prop=row["prop"], anchor=row["anchor"], samples=n, fail=bad,
                   coverage=round(1 - bad / max(n, 1), 4), worst_dev=round(worst, 3), ghost_verts=len(gh),
                   ghost_bbox=gbox, examples=fails)
        report.append(rep)
        print(f"CHECK {row['prop']:26s} {row['anchor']:14s} samples {n:6d} fail {bad:5d} "
              f"({100 * rep['coverage']:.2f}% ok, worst {worst:.3f}) ghost verts {len(gh)} {gbox or ''}")
    json.dump(report, open(os.path.join(KIT, "props_check.json"), "w"), indent=1)
    return report


def check_exported(rows, opts):
    """Run the layout ray checker on the actual GLB and explicitly scope missing brushes to this kit."""
    suffix = "" if not opts["only"] else "_partial"
    art = os.path.join(KIT, f"props_placed{suffix}.glb")
    out = os.path.join(KIT, f"props_alignment{suffix}.json")
    blender = r"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
    with open(os.path.join(KIT, "props_alignment.log"), "w", encoding="utf-8") as logf:
        subprocess.run([blender, "-b", "--factory-startup", "-P", os.path.join(HERE, "layout", "check_alignment.py"),
                        "--", "--art", art, "--out", out], stdout=logf, stderr=subprocess.STDOUT, check=True)
    report = json.load(open(out, encoding="utf-8"))
    tags = {tag for row in rows if row.get("owner") == "props_placed.glb" for tag in row["brushes"]}
    ghosts = [m for m in report["items"] if m["kind"] == "GHOST"]
    inv = [m for m in report["items"] if m["kind"] == "INVISIBLE" and m["tag"] in tags]
    summary = dict(file=os.path.basename(art), rays=report["rays"], ghost=len(ghosts), invisible_owned=len(inv),
                   invisible_other_kits=report["invisible"] - len(inv), owned_tags=sorted(tags),
                   mismatches=ghosts + inv,
                   doc="Standalone actual GLB audit. Ground/houses are not loaded here; missing faces on their "
                       "tags are reported separately and are not failures of this placed props file.")
    json.dump(summary, open(os.path.join(KIT, f"props_alignment_summary{suffix}.json"), "w"), indent=2)
    print("EXPORTED CHECK", summary["file"], "GHOST", len(ghosts), "INVISIBLE own", len(inv))
    return summary


# =============================================================================================== rendering
def lighting(sc):
    w = bpy.data.worlds.new("W_Props")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.50, 0.56, 0.72, 1.0)
    bg.inputs["Strength"].default_value = 0.65
    sd = bpy.data.lights.new("_Sun", "SUN")
    sd.energy = 2.5
    sd.color = (1.0, 0.84, 0.66)
    sd.angle = math.radians(2.0)
    sun = bpy.data.objects.new("_Sun", sd)
    sc.collection.objects.link(sun)
    bc_engine(sc)
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium Low Contrast"
    except TypeError:
        pass
    return sun


def bc_engine(sc):
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    try:
        sc.eevee.taa_render_samples = 48
    except Exception:
        pass
    for attr, val in (("use_shadows", True), ("use_raytracing", True), ("use_gtao", True)):
        if hasattr(sc.eevee, attr):
            try:
                setattr(sc.eevee, attr, val)
            except Exception:
                pass


def ground_plane(sc, size=400.0):
    spec("_M_Ground", tex="concrete_smooth.png", repeat=6.0, rough=0.85, vc=False, tint=(0.92, 0.92, 0.95))
    me = bpy.data.meshes.new("_Ground")
    s = size / 2
    me.from_pydata([(-s, -s, -0.002), (s, -s, -0.002), (s, s, -0.002), (-s, s, -0.002)], [], [(0, 1, 2, 3)])
    me.materials.append(PL.M("_M_Ground"))
    PL.compute_uvs(me)
    ob = bpy.data.objects.new("_Ground", me)
    sc.collection.objects.link(ob)
    return ob


def aim(obj, loc, target):
    obj.location = loc
    obj.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def fit_camera(cam, cd, c, d, corners, aspect=1.0, fill=0.90):
    """Place the camera along direction d from c so every corner fits the frame (binary search on distance)."""
    fovx = 2 * math.atan(36 / (2 * cd.lens)) if aspect >= 1 else 2 * math.atan(36 * aspect / (2 * cd.lens))
    tx = math.tan(fovx / 2) * fill
    ty = tx / aspect if aspect >= 1 else tx
    lo, hi = 0.1, 5000.0
    for _ in range(40):
        mid = (lo + hi) / 2
        aim(cam, c + d * mid, c)
        bpy.context.view_layer.update()
        inv = cam.matrix_world.inverted()
        ok = True
        for p in corners:
            q = inv @ p
            if q.z > -0.05 or abs(q.x) / -q.z > tx or abs(q.y) / -q.z > ty:
                ok = False
                break
        if ok:
            hi = mid
        else:
            lo = mid
    aim(cam, c + d * hi, c)


def render_setup(res):
    sc = bpy.context.scene
    sun = bpy.data.objects.get("_Sun") or lighting(sc)
    ground = bpy.data.objects.get("_Ground") or ground_plane(sc)
    cam = bpy.data.objects.get("_Cam")
    if cam is None:
        cd = bpy.data.cameras.new("_Cam")
        cam = bpy.data.objects.new("_Cam", cd)
        sc.collection.objects.link(cam)
    cd = cam.data
    sc.camera = cam
    cd.lens = 50
    cd.clip_start, cd.clip_end = 0.02, 3000
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.image_settings.file_format = "PNG"
    return sc, sun, ground, cam, cd


def sun_from(sun, d, side=55, elev=34):
    # Game sun: 188 degrees clockwise from design north, 54 degrees elevation.
    az = math.radians(188)
    ldir = Vector((math.sin(az), math.cos(az), math.tan(math.radians(54))))
    sun.rotation_euler = (-ldir).to_track_quat("-Z", "Y").to_euler()


def bbox_corners(mn, mx):
    return [Vector((x, y, z)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for z in (mn.z, mx.z)]


def render_tiles(built, res=560):
    sc, sun, ground, cam, cd = render_setup((res, res))
    os.makedirs(RENDERS, exist_ok=True)
    allp = [r["obj"] for r in built]
    tiles = []
    for r in built:
        for o in allp:
            o.hide_render = o is not r["obj"]
        mn, mx = (Vector(r["bbox"][0]), Vector(r["bbox"][1]))
        c = (mn + mx) / 2
        d = Vector(r["view"]).normalized()
        cd.lens = 50
        fit_camera(cam, cd, c, d, bbox_corners(mn, mx), 1.0, 0.86)
        sun_from(sun, d)
        ground.hide_render = mn.z < -0.5
        p = os.path.join(RENDERS, f"tile_{r['name']}.png")
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        tiles.append(dict(path=p, name=r["name"], cat=r["cat"], tris=r["tris"],
                          size=[round(mx[i] - mn[i], 2) for i in range(3)]))
    for o in allp:
        o.hide_render = False
    return tiles


HERO_VIEWS = {"front_right": (0.75, -1.0, 0.28), "rear_left": (-0.8, 0.9, 0.3), "side": (1.0, -0.05, 0.12),
              "high": (0.55, -0.7, 1.1), "eye": (0.35, -1.0, 0.05)}


def render_hero(built, names, res=(1100, 760)):
    sc, sun, ground, cam, cd = render_setup(res)
    allp = [r["obj"] for r in built]
    tiles = []
    for r in built:
        if r["name"] not in names:
            continue
        for o in allp:
            o.hide_render = o is not r["obj"]
        mn, mx = (Vector(r["bbox"][0]), Vector(r["bbox"][1]))
        c = (mn + mx) / 2
        base = Vector(r["view"])
        rot = math.atan2(base.y, base.x) - math.atan2(-1.0, 0.75)
        for vn, v in HERO_VIEWS.items():
            d = Matrix.Rotation(rot, 3, "Z") @ Vector(v)
            d.normalize()
            cd.lens = 40 if vn != "eye" else 28
            fit_camera(cam, cd, c, d, bbox_corners(mn, mx), res[0] / res[1], 0.9)
            sun_from(sun, d)
            p = os.path.join(RENDERS, f"hero_{r['name']}_{vn}.png")
            sc.render.filepath = p
            bpy.ops.render.render(write_still=True)
            tiles.append(dict(path=p, name=f"{r['name']} {vn}", cat=r["cat"], tris=r["tris"],
                              size=[round(mx[i] - mn[i], 2) for i in range(3)]))
    for o in allp:
        o.hide_render = False
    return tiles


def contact_sheet(tiles, name="props_contact_sheet.png", cols=8, tw=300):
    man = os.path.join(RENDERS, "_tiles.json")
    json.dump(dict(tiles=tiles, out=os.path.join(RENDERS, name), cols=cols, tw=tw), open(man, "w"), indent=1)
    subprocess.run(["python", os.path.join(HERE, "props_sheet.py"), man], check=False)


# =============================================================================================== main
def main():
    opts = argv()
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    materials()
    built = build(opts)
    rows = placements(built)
    if opts["export"]:
        export(built, rows, opts)
        for c in [c for c in bpy.data.collections if c.name == "_PLACED"]:
            for o in list(c.objects):
                bpy.data.objects.remove(o, do_unlink=True)
            bpy.data.collections.remove(c)
    if opts["check"]:
        check(built, rows)
        if opts["export"]:
            check_exported(rows, opts)
    if opts["render"]:
        tiles = render_tiles(built)
        contact_sheet(tiles, "props_contact_sheet.png" if not opts["only"] else "props_contact_sheet_partial.png")
    if opts["hero"]:
        ht = render_hero(built, opts["hero"])
        contact_sheet(ht, "props_hero_sheet.png", cols=3, tw=640)
    for c in [c for c in bpy.data.collections if c.name == "_PLACED"]:
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(c)
    if opts["export"]:
        for o in [o for o in sc.objects if o.name.startswith("_")]:
            bpy.data.objects.remove(o, do_unlink=True)
        try:
            bpy.ops.file.pack_all()
        except Exception as e:
            print("pack failed", e)
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(KIT, "props.blend" if not opts["only"] else
                                                          "props_partial.blend"), compress=True)
    total = sum(r["tris"] for r in built)
    print(f"DONE {len(built)} props, {total} tris, {time.time() - t0:.1f}s")


main()
