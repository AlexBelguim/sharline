"""Round-2 probes: the chassis/handguard coincident face, handguard sliver holes, stock/riser geometry
numbers, receiver/handguard joint step, grip angle, handguard top-slot see-through height vs barrel."""
import bpy, bmesh, math, os
from mathutils import Vector
D = r"F:/git/val etf/assets/weapons/vk50_warden"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(D, "warden_default.glb"))
by = {o.name: o for o in bpy.data.objects}
def faces(o):
    me = o.data; mw = o.matrix_world
    return [(mw @ p.center, (mw.to_3x3() @ p.normal).normalized(), p.area, [mw @ me.vertices[i].co for i in p.vertices]) for p in me.polygons]
P = Vector((-0.0115, -0.3, 0.0308))
for nm in ("WARDEN_Chassis", "WARDEN_Handguard", "WARDEN_Receiver"):
    for c, n, a, vs in faces(by[nm]):
        if (c - P).length < 0.02 and a > 2e-5:
            print(nm, "face c", [round(x,4) for x in c], "n", [round(x,3) for x in n], "area mm2", round(a*1e6,1),
                  "verts", [[round(x,4) for x in v] for v in vs])
# handguard slot rows: z ranges of the side-slot openings (faces whose normal is +-Z inside the slot) -> see-through?
hg = by["WARDEN_Handguard"]
zs = sorted({round(c.z,4) for c,n,a,vs in faces(hg) if abs(n.z) > 0.99 and abs(c.x) > 0.025 and -0.62 < c.y < -0.34})
print("handguard horizontal faces z (|x|>0.025):", zs)
bar = by["WARDEN_Barrel"]
bz = [ (bar.matrix_world @ v.co).z for v in bar.data.vertices if -0.70 < (bar.matrix_world @ v.co).y < -0.23]
print("barrel z range under handguard slots:", round(min(bz),4), round(max(bz),4))
# side slot vertical extents
for c,n,a,vs in faces(hg):
    pass
# cheek riser + stock upright + bolt numbers
for nm in ("WARDEN_StockStandard_CheekRiser", "WARDEN_StockStandard", "WARDEN_Bolt", "WARDEN_Grip"):
    o = by[nm]
    vs = [o.matrix_world @ v.co for v in o.data.vertices]
    print(nm, "x", round(min(v.x for v in vs),4), round(max(v.x for v in vs),4), "y", round(min(v.y for v in vs),4), round(max(v.y for v in vs),4),
          "z", round(min(v.z for v in vs),4), round(max(v.z for v in vs),4))
# stock top beam height between y 0.10 and 0.23 (max z of stock verts with |x|<0.02 in that band)
st = by["WARDEN_StockStandard"]
for y0 in (0.10, 0.13, 0.16, 0.19, 0.22, 0.25, 0.28):
    zz = [ (st.matrix_world @ v.co).z for v in st.data.vertices if abs((st.matrix_world @ v.co).y - y0) < 0.006 and abs((st.matrix_world @ v.co).x) < 0.02]
    print("stock top z at y", y0, round(max(zz),4) if zz else None, "min", round(min(zz),4) if zz else None)
# knob position
bo = by["WARDEN_Bolt"]
vs = [bo.matrix_world @ v.co for v in bo.data.vertices]
kn = [v for v in vs if v.x < -0.07]
c = sum(kn, Vector())/len(kn)
print("knob centre approx", [round(x,4) for x in c], "x extent", round(min(v.x for v in kn),4), round(max(v.x for v in kn),4), "z", round(min(v.z for v in kn),4), round(max(v.z for v in kn),4))
