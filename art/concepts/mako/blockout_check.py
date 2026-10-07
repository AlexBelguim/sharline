"""Quick proportion check: extrude the BRIEF profiles into a grey-box MAKO and render it.
NOT the asset - only a sanity check of the numbers in BRIEF.md / profile_sketch.py.
Run: blender -b --factory-startup -P blockout_check.py
"""
import math
import os
import sys

sys.path.insert(0, r"F:/git/val etf/tools")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import blender_common as bc  # noqa: E402
import profile_sketch as P  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blockout")

bc.reset_scene()
G = bc.material("M_G", (0.030, 0.033, 0.040), 0.5, 0.25)
GM = bc.material("M_GM", (0.11, 0.115, 0.12), 0.35, 0.85)
B = bc.material("M_B", (0.55, 0.52, 0.46), 0.6, 0.0)
R = bc.material("M_R", (0.030, 0.033, 0.040), 0.85, 0.0)
ICE = bc.material("M_I", (0.45, 0.85, 1.0), 0.3, 0.0, emission=(0.45, 0.85, 1.0), emission_strength=4)
DK = bc.material("M_D", (0.035, 0.037, 0.045), 0.7, 0.0)

pe = bc.profile_extrude
pe("Upper", P.UPPER, 0.032, mat=G, bevel=0.002)
pe("Lower", P.LOWER, 0.030, mat=G, bevel=0.002)
bc.box("Magwell", (0.034, 0.084, 0.062), loc=(0, -0.122, -0.007), mat=G, bevel=0.002)
tg = pe("TG", P.TRIGGER_GUARD, 0.014, mat=G, bevel=0.0015)
hole = pe("_TGH", P.TRIGGER_GUARD_HOLE, 0.03)
bc.boolean(tg, hole)
pe("Trigger", P.TRIGGER, 0.007, mat=GM)
pe("Grip", P.GRIP, 0.030, mat=B, bevel=0.004, segments=3)
mag = pe("Mag", P.MAG, 0.025, mat=B, bevel=0.002)
pe("MagWin", P.MAG_WINDOW, 0.0262, mat=DK)
# handguard: octagon prism along Y, hollowed
import bmesh  # noqa: E402
from mathutils import Vector  # noqa: E402


def prism_y(name, pts_xz, y0, y1, mat=None):
    bm = bmesh.new()
    vs = [bm.verts.new((x, y0, z)) for (x, z) in pts_xz]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    nv = [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=Vector((0, y1 - y0, 0)), verts=nv)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if mat:
        bc.assign(o, mat)
    return o


OCT = [(0.012, 0.0745), (0.022, 0.0645), (0.022, 0.0355), (0.012, 0.026), (-0.012, 0.026), (-0.022, 0.0355),
       (-0.022, 0.0645), (-0.012, 0.0745)]
OCT_IN = [(x * 0.86, 0.050 + (z - 0.050) * 0.87) for x, z in OCT]
hg = prism_y("Handguard", OCT, -0.500, -0.168, mat=G)
bc.boolean(hg, prism_y("_hin", OCT_IN, -0.51, -0.16))
bc.boolean(hg, bc.box("_hgchamf", (0.08, 0.03, 0.03), loc=(0, -0.500, 0.026), rot=(45, 0, 0)))
cut = []
for yc in P.SLOT_Y:
    cut.append(bc.box(f"_s{yc}", (0.08, 0.032, 0.007), loc=(0, yc, 0.05)))
    for a in (48.6, -48.6):
        cut.append(bc.box(f"_d{yc}{a}", (0.08, 0.024, 0.005), loc=(0, yc, 0.05), rot=(0, a, 0)))
cj = bc.join(cut, "_slots")
bc.boolean(hg, cj)
bc.box("Rail", (0.021, 0.520, 0.0095), loc=(0, -0.238, 0.07925), mat=G)
rc = [bc.box(f"_r{i}", (0.03, 0.005, 0.004), loc=(0, -0.493 + i * 0.010, 0.0845)) for i in range(52)]
bc.boolean(bpy.data.objects["Rail"], bc.join(rc, "_rs"))
bc.box("RailB", (0.021, 0.14, 0.0095), loc=(0, -0.36, 0.02125), mat=G)
for s in (1, -1):
    bc.box(f"RailS{s}", (0.0095, 0.06, 0.021), loc=(s * 0.02675, -0.44, 0.05), mat=G)
bc.cylinder("Barrel", 0.0095, 0.359, loc=(0, -0.3395, 0.05), rot=(90, 0, 0), mat=GM)
comp = bc.cylinder("Comp", 0.0145, 0.048, loc=(0, -0.541, 0.05), rot=(90, 22.5, 0), verts=8, mat=GM, bevel=0.002)
for y0, y1 in P.COMP_PORTS:
    bc.boolean(comp, bc.box("_p", (0.06, y1 - y0, 0.013), loc=(0, (y0 + y1) / 2, 0.05)))
bc.cylinder("Tube", 0.016, 0.185, loc=(0, 0.1225, 0.05), rot=(90, 0, 0), mat=G)
bc.cylinder("Nut", 0.0195, 0.010, loc=(0, 0.041, 0.05), rot=(90, 0, 0), mat=GM)
st = pe("Stock", P.STOCK, 0.028, mat=B, bevel=0.003)
bc.box("StockHousing", (0.040, 0.164, 0.052), loc=(0, 0.180, 0.052), mat=B, bevel=0.004)
for sx in (0.0165, -0.0165):
    bc.boolean(st, pe("_sw", P.STOCK_PANEL, 0.006, loc=(sx, 0, 0)))
pe("ButtPad", P.BUTT_PAD, 0.042, mat=R, bevel=0.003)
pe("CH", P.CHARGING_HANDLE, 0.012, mat=G)
bc.box("CHwings", (0.048, 0.012, 0.010), loc=(0, 0.036, 0.067), mat=G, bevel=0.002)
opt = pe("Optic", P.OPTIC, 0.036, mat=G, bevel=0.002)
bc.boolean(opt, bc.box("_win", (0.026, 0.2, 0.024), loc=(0, P.OPTIC_Y, 0.116)))
bc.cylinder("Reticle", 0.002, 0.001, loc=(0, P.OPTIC_Y - 0.030, 0.116), rot=(90, 0, 0), verts=12, mat=ICE)
bc.box("Bezel", (0.0025, 0.036, 0.024), loc=(0.01725, -0.012, 0.052), mat=G, bevel=0.0008)
bc.box("Screen", (0.0006, 0.028, 0.016), loc=(0.0187, -0.012, 0.052), mat=ICE)
bc.box("RearPin", (0.034, 0.006, 0.006), loc=(0, 0.024, 0.034), mat=GM)
bc.box("FwdAssist", (0.010, 0.034, 0.016), loc=(-0.019, 0.013, 0.058), mat=G, bevel=0.003)
bc.cylinder("FAcap", 0.0065, 0.008, loc=(-0.019, 0.034, 0.058), rot=(90, 0, 0), mat=GM)
bc.box("DustCover", (0.002, 0.068, 0.025), loc=(-0.017, -0.060, 0.0535), mat=G, bevel=0.0006)

bc.stats()
bc.setup_studio(bg=(0.55, 0.56, 0.58))
paths = bc.render_views(OUT, "mako_blockout", views=("right", "left", "three_quarter", "three_quarter_back"),
                        res=(1400, 700), lens=85, margin=1.05)
bc.contact_sheet(paths, os.path.join(OUT, "mako_blockout_sheet.png"), cols=2)
