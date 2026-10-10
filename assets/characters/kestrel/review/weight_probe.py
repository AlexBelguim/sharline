"""Review helper: which bones drive the chest plate, jet pack and back hair (rest-pose regions)."""
import sys
sys.dont_write_bytecode = True
import bpy, numpy as np
bpy.ops.wm.open_mainfile(filepath=r"F:/git/val etf/assets/characters/kestrel/kestrel.blend")
body = bpy.data.objects["KES_Body"]
gname = {g.index: g.name for g in body.vertex_groups}
co = np.array([v.co[:] for v in body.data.vertices])
tex = None
def region(name, m):
    idx = np.where(m)[0]
    acc = {}
    for i in idx:
        for g in body.data.vertices[i].groups:
            acc.setdefault(gname[g.group], []).append(g.weight)
    summ = sorted(((k, len(v), float(np.mean(v)), float(np.max(v))) for k, v in acc.items()), key=lambda x: -x[1] * x[2])
    print("[REV]", name, "verts", len(idx), [(k, n, round(mn, 2), round(mx, 2)) for k, n, mn, mx in summ[:8]])
x, y, z = co[:, 0], co[:, 1], co[:, 2]
region("chest plate front (|x|<0.11, y<-0.115, 1.19<z<1.33)", (abs(x) < 0.11) & (y < -0.115) & (z > 1.19) & (z < 1.33))
region("chest plate right edge (-0.14<x<-0.08, y<-0.08, 1.19<z<1.33)", (x > -0.14) & (x < -0.08) & (y < -0.08) & (z > 1.19) & (z < 1.33))
region("jet pack (|x|<0.2, y>0.16, 1.05<z<1.4)", (abs(x) < 0.2) & (y > 0.16) & (z > 1.05) & (z < 1.4))
region("back hair low (|x|<0.08, y>0.08, 1.42<z<1.52)", (abs(x) < 0.08) & (y > 0.08) & (z > 1.42) & (z < 1.52))
region("back hair mid (|x|<0.08, y>0.08, 1.52<z<1.62)", (abs(x) < 0.08) & (y > 0.08) & (z > 1.52) & (z < 1.62))
region("armpit/back web L (0.15<x<0.25, 0.06<y<0.14, 1.15<z<1.3)", (x > 0.15) & (x < 0.25) & (y > 0.06) & (y < 0.14) & (z > 1.15) & (z < 1.3))
