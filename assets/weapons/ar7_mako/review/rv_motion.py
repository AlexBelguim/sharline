"""Sweep each moving part through its stated motion (NOTES.md) and count NEW overlaps vs the rest pose."""
import json, math, os
import bmesh, bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
HERE = r"F:/git/val etf/assets/weapons/ar7_mako"
bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, "mako.blend"))
dg = bpy.context.evaluated_depsgraph_get()
def bm_world(o, extra=Matrix.Identity(4)):
    oe = o.evaluated_get(dg); me = oe.to_mesh(); bm = bmesh.new(); bm.from_mesh(me)
    bm.transform(extra @ o.matrix_world); oe.to_mesh_clear(); return bm
base = [o for o in bpy.data.collections["MAKO_Base"].objects if o.type == "MESH"]
others = base + [o for c in ("MAKO_stock_standard", "MAKO_mag_30") for o in bpy.data.collections[c].objects if o.type == "MESH"]
static = {o.name: BVHTree.FromBMesh(bm_world(o)) for o in others}
def about(pivot, axis, deg):
    p = Vector(pivot)
    return Matrix.Translation(p) @ Matrix.Rotation(math.radians(deg), 4, axis) @ Matrix.Translation(-p)
def test(name, mats):
    o = bpy.data.objects[name]
    rest = BVHTree.FromBMesh(bm_world(o))
    rest_hits = {k: len(rest.overlap(v)) for k, v in static.items() if k != name}
    out = []
    for label, M in mats:
        t = BVHTree.FromBMesh(bm_world(o, M))
        hits = {k: len(t.overlap(v)) for k, v in static.items() if k != name}
        new = {k: v for k, v in hits.items() if v > rest_hits.get(k, 0) + 2}
        out.append((label, new))
    return {"rest": {k: v for k, v in rest_hits.items() if v}, "sweep": out}
R = {}
ch = bpy.data.objects["MAKO_ChargingHandle"].matrix_world.translation
R["ChargingHandle +Y"] = test("MAKO_ChargingHandle", [(f"+{d:.3f}", Matrix.Translation((0, d, 0))) for d in (0.01, 0.02, 0.04, 0.06)])
piv = bpy.data.objects["MAKO_Trigger"].matrix_world.translation
R["Trigger rotX"] = test("MAKO_Trigger", [(f"{a}deg", about(piv, "X", a)) for a in (-15, -8, 8, 15)])
piv = bpy.data.objects["MAKO_DustCover"].matrix_world.translation
R["DustCover rotY"] = test("MAKO_DustCover", [(f"{a}deg", about(piv, "Y", a)) for a in (-100, -45, 45, 100)])
piv = bpy.data.objects["MAKO_BoltCatch"].matrix_world.translation
R["BoltCatch rotX"] = test("MAKO_BoltCatch", [(f"{a}deg", about(piv, "X", a)) for a in (-10, 10)])
R["MagRelease +X"] = test("MAKO_MagRelease", [("+0.003", Matrix.Translation((0.003, 0, 0)))])
piv = bpy.data.objects["MAKO_Selector"].matrix_world.translation
R["Selector rotX"] = test("MAKO_Selector", [(f"{a}deg", about(piv, "X", a)) for a in (-90, -45, 45, 90)])
R["ForwardAssist -Y"] = test("MAKO_ForwardAssist", [("-0.004", Matrix.Translation((0, -0.004, 0)))])
# standard stock collapse: 6 positions, 0.0165 apart toward -Y
st = bpy.data.collections["MAKO_stock_standard"].objects
o = bpy.data.objects["MAKO_stock_standard"]
R["Stock collapse -Y"] = test("MAKO_stock_standard", [(f"-{d:.4f}", Matrix.Translation((0, -d, 0))) for d in (0.0165, 0.033, 0.0495, 0.066, 0.083)])
print("MOTION", json.dumps(R, indent=0))
json.dump(R, open(os.path.join(HERE, "review", "motion_report.json"), "w"), indent=1)
