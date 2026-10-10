"""Find the non-deterministic step: rebuild the brake N times, fingerprint after every step."""
import runpy, sys
import bpy
sys.argv = [sys.argv[0], "--", "--no-export", "--no-det-check", "--no-gate"]
ns = runpy.run_path(r"F:/git/val etf/assets/weapons/vk50_warden/build_warden.py", run_name="warden_defs")
g = ns
BZ = g["BZ"]; prism = g["prism"]; intersect = g["intersect"]; cut = g["cut"]; cyl = g["cyl"]; join = g["join"]
rounded_rect = g["rounded_rect"]; finish = g["finish"]; seal = g["seal"]; tri_clean = g["tri_clean"]
import blender_common as bc
import os
SOLVER = os.environ.get("SOLVER", "EXACT")
def _boolean(obj, cutter, op="DIFFERENCE", apply=True, hide_cutter=True):
    m = obj.modifiers.new("Bool_" + cutter.name, "BOOLEAN")
    m.object = cutter
    m.operation = op
    m.solver = SOLVER
    bc.apply_modifiers(obj, only=[m.name])
    bpy.data.objects.remove(cutter, do_unlink=True)
    return obj
bc.boolean = _boolean

def fp(o):
    co = [0.0] * (len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", co)
    return (len(o.data.polygons), len(o.data.vertices), round(sum(abs(c) for c in co), 7))

res = []
for run in range(int(__import__("os").environ.get("NRUNS", "6"))):
    bc.reset_scene()
    steps = []
    BH, BW = 0.0235, 0.026
    bs = prism("WARDEN_Brake", [(-0.992, BZ - 0.020), (-0.992, BZ + 0.020), (-0.996, BZ + BH), (-1.092, BZ + BH),
                                (-1.100, BZ + BH - 0.008), (-1.100, BZ - BH + 0.008), (-1.092, BZ - BH),
                                (-0.996, BZ - BH)], "X", -BW, BW)
    intersect(bs, prism("_btop", [(-BW, -0.990), (BW, -0.990), (BW, -1.093), (BW - 0.007, -1.100),
                                  (-BW + 0.007, -1.100), (-BW, -1.093)], "Z", BZ - 0.05, BZ + 0.05)); steps.append(fp(bs))
    intersect(bs, prism("_bsec", [(-BW + 0.005, BZ - BH), (BW - 0.005, BZ - BH), (BW, BZ - BH + 0.005),
                                  (BW, BZ + BH - 0.005), (BW - 0.005, BZ + BH), (-BW + 0.005, BZ + BH),
                                  (-BW, BZ + BH - 0.005), (-BW, BZ - BH + 0.005)], "Y", -1.11, -0.98)); steps.append(fp(bs))
    cut(bs, cyl("_bore", 0.0090, 0.2, (0, -1.04, BZ), "Y", 20)); steps.append(fp(bs))
    for sx in (1, -1):
        cut(bs, prism("_pCr", rounded_rect(-1.0325, BZ, 0.017, 0.032, 0.004, 2), "X", sx * (BW - 0.0015), sx * 0.05))
    steps.append(fp(bs))
    cut(bs, join([prism("_pA", rounded_rect(-1.0785, BZ, 0.019, 0.026, 0.0045, 2), "X", -0.06, 0.06),
                  prism("_pB", rounded_rect(-1.0535, BZ, 0.013, 0.027, 0.0040, 2), "X", -0.06, 0.06),
                  prism("_pC", rounded_rect(-1.0325, BZ, 0.0065, 0.022, 0.0030, 2), "X", -0.06, 0.06)], "_ports"))
    steps.append(fp(bs))
    g["degen"](bs); steps.append(fp(bs))
    finish(bs, 0.0020, 1); steps.append(fp(bs))
    seal(bs); steps.append(fp(bs))
    tri_clean(bs); steps.append(fp(bs))
    res.append(steps)
for i, s in enumerate(res):
    print("RUN", i, s)
